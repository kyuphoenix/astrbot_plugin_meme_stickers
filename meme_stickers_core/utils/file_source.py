from pathlib import Path
from typing import Any, TYPE_CHECKING
from contextlib import asynccontextmanager, nullcontext
import asyncio
from collections.abc import Awaitable
from typing import Generic, Literal, Protocol, TypeAlias, TypedDict, TypeVar
from typing_extensions import Unpack

from httpx import AsyncClient
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_fixed, RetryCallState
from yarl import URL

from ..config import config
from astrbot.api import logger

if TYPE_CHECKING:
    from httpx import Response


def op_retry(log_message: str = "Operation failed", **kwargs):
    def retry_log(x: RetryCallState):
        if not x.outcome:
            return
        if (e := x.outcome.exception()) is None:
            return
        logger.warning(
            f"{log_message} (attempt {x.attempt_number} / {config.retry_times}): "
            f"{type(e).__name__}: {e}",
        )

    return retry(
        **{
            "stop": stop_after_attempt(config.retry_times),
            "wait": wait_fixed(0.5),
            "before_sleep": retry_log,
            "reraise": True,
            **kwargs,
        },
    )


class FileSourceGitHubBase(BaseModel):
    type: Literal["github"] = "github"
    owner: str
    repo: str
    path: str | None = None


class FileSourceGitHubBranch(FileSourceGitHubBase):
    branch: str


class FileSourceGitHubTag(FileSourceGitHubBase):
    tag: str


FileSourceGitHub: TypeAlias = FileSourceGitHubBranch | FileSourceGitHubTag


class FileSourceURL(BaseModel):
    type: Literal["url"] = "url"
    url: str


FileSource: TypeAlias = FileSourceGitHubBranch | FileSourceGitHubTag | FileSourceURL
M = TypeVar("M", bound=FileSource)
M_contra = TypeVar("M_contra", bound=FileSource, contravariant=True)


class ReqKwargs(TypedDict, total=False):
    cli: AsyncClient | None
    sem: asyncio.Semaphore | None


class SourceFetcher(Protocol, Generic[M_contra]):
    def __call__(self, source: M_contra, *paths: str, **req_kw: Unpack[ReqKwargs]) -> Awaitable["Response"]: ...


def create_client(**kwargs):
    return AsyncClient(proxy=config.proxy, follow_redirects=True, timeout=config.req_timeout, **kwargs)


def create_req_sem():
    return asyncio.Semaphore(config.req_concurrency)


@asynccontextmanager
async def with_cli(cli: AsyncClient | None = None):
    ctx = create_client() if cli is None else nullcontext(cli)
    async with ctx as x:
        yield x


@asynccontextmanager
async def with_kw_cli(kw: ReqKwargs):
    cli = kw.get("cli")
    if cli:
        yield
        return
    cli = create_client()
    kw["cli"] = cli
    try:
        async with cli:
            yield
    finally:
        kw.pop("cli", None)


@asynccontextmanager
async def with_kw_sem(kw: ReqKwargs):
    sem = kw.get("sem")
    if not sem:
        sem = create_req_sem()
        kw["sem"] = sem
    try:
        yield
    finally:
        kw.pop("sem", None)


_fetchers: dict[str, Any] = {}


def register_fetcher(source_type: str):
    def deco(fn):
        _fetchers[source_type] = fn
        return fn
    return deco


@register_fetcher("url")
async def fetch_url_source(source: FileSourceURL, *paths: str, **req_kw: Unpack[ReqKwargs]) -> "Response":
    cli = req_kw.get("cli")
    sem = req_kw.get("sem")
    url = str(URL(source.url).joinpath(*paths))

    @op_retry(f"Fetch {url} failed")
    async def fetch(c: AsyncClient) -> "Response":
        return (await c.get(url)).raise_for_status()

    sem = sem or nullcontext()
    async with sem, with_cli(cli) as ctx_cli:
        return await fetch(ctx_cli)


def format_github_url(source: FileSourceGitHub):
    v = {
        "owner": source.owner,
        "repo": source.repo,
        "ref": source.branch if isinstance(source, FileSourceGitHubBranch) else source.tag,
        "ref_path": f"refs/heads/{source.branch}" if isinstance(source, FileSourceGitHubBranch) else f"refs/tags/{source.tag}",
        "path": source.path,
    }
    return config.github_url_template.format_map(v)


@register_fetcher("github")
async def fetch_github_source(source: FileSourceGitHub, *paths: str, **req_kw: Unpack[ReqKwargs]) -> "Response":
    return await fetch_url_source(FileSourceURL(type="url", url=format_github_url(source)), *paths, **req_kw)


async def fetch_source(source: FileSource, *paths: str, **req_kw: Unpack[ReqKwargs]) -> "Response":
    fn = _fetchers.get(source.type)
    if not fn:
        raise ValueError(f"No fetcher for source type: {source.type}")
    return await fn(source, *paths, **req_kw)
