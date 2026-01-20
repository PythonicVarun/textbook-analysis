import asyncio
import time
from typing import Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from fake_useragent import UserAgent


def _get_or_create_loop():
    """Return an event loop with a Windows-friendly policy.

    Playwright on Windows needs a subprocess-capable loop. This helper ensures
    we are using a compatible policy before creating or returning the loop.
    """

    if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        # Ensure proactor policy for subprocess support on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class WebCrawler:
    """
    A tool for fetching website content and converting it to markdown using crawl4ai.
    """

    def __init__(self, headless: bool = True, verbose: bool = False):
        """
        Initialize the web crawler.

        Args:
            headless: Run browser in headless mode (default: True)
            verbose: Enable verbose logging (default: False)
        """
        self.headless = headless
        self.verbose = verbose
        self._request_count = 0
        self._last_request_time = 0

        # User agent rotator
        self._ua = UserAgent()

        # Crawl4Ai browser configuration
        self.browser_config = BrowserConfig(
            headless=headless,
            verbose=verbose,
            enable_stealth=True,
        )

    def _get_user_agent(self) -> str:
        """Rotate through user agents."""
        return self._ua.random

    def _apply_rate_limiting(self, delay: float = 1.5):
        """Apply rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < delay:
            time.sleep(delay - time_since_last)

        self._last_request_time = time.time()
        self._request_count += 1

    async def _fetch_url_async(
        self,
        url: str,
        timeout: int = 30000,
        wait_for_selector: Optional[str] = None,
    ) -> dict:
        """
        Asynchronously fetch a URL and return its content as markdown.

        Args:
            url: The URL to fetch
            timeout: Timeout in milliseconds (default: 30000)
            wait_for_selector: Optional CSS selector to wait for before extracting content

        Returns:
            dict with 'success', 'markdown', 'html', 'url', and 'error' keys
        """
        try:
            user_agent = self._get_user_agent()

            browser_config = BrowserConfig(
                headless=self.headless,
                verbose=self.verbose,
                user_agent=user_agent,
                enable_stealth=True,
                light_mode=True,
            )

            run_config = CrawlerRunConfig(
                page_timeout=timeout,
                wait_for=wait_for_selector,  # type:ignore[invalid-argument-type]
                cache_mode=CacheMode.BYPASS,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)

                if result.success:
                    return {
                        "success": True,
                        "markdown": result.markdown,
                        "html": result.html,
                        "url": result.url,
                        "title": getattr(result, "title", ""),
                        "error": None,
                    }
                else:
                    return {
                        "success": False,
                        "markdown": None,
                        "html": None,
                        "url": url,
                        "title": None,
                        "error": (
                            result.error_message
                            if hasattr(result, "error_message")
                            else "Failed to fetch URL"
                        ),
                    }

        except Exception as e:
            return {
                "success": False,
                "markdown": None,
                "html": None,
                "url": url,
                "title": None,
                "error": str(e),
            }

    def fetch_url(
        self,
        url: str,
        timeout: int = 30000,
        wait_for_selector: Optional[str] = None,
    ) -> dict:
        """
        Fetch a URL and return its content as markdown (synchronous wrapper).

        Args:
            url: The URL to fetch
            timeout: Timeout in milliseconds (default: 30000)
            wait_for_selector: Optional CSS selector to wait for before extracting content

        Returns:
            dict with 'success', 'markdown', 'html', 'url', and 'error' keys
        """
        # Apply rate limiting
        self._apply_rate_limiting()

        loop = _get_or_create_loop()
        return loop.run_until_complete(
            self._fetch_url_async(url, timeout, wait_for_selector)
        )

    async def _fetch_multiple_urls_async(
        self,
        urls: list[str],
        timeout: int = 30000,
    ) -> list[dict]:
        """
        Asynchronously fetch multiple URLs concurrently.

        Args:
            urls: List of URLs to fetch
            timeout: Timeout in milliseconds (default: 30000)

        Returns:
            List of result dicts
        """
        results = []
        for url in urls:
            try:
                user_agent = self._get_user_agent()

                browser_config = BrowserConfig(
                    headless=self.headless,
                    verbose=self.verbose,
                    user_agent=user_agent,
                    enable_stealth=True,
                    light_mode=True,
                )

                run_config = CrawlerRunConfig(
                    page_timeout=timeout,
                    cache_mode=CacheMode.BYPASS,
                )

                async with AsyncWebCrawler(config=browser_config) as crawler:
                    result = await crawler.arun(url=url, config=run_config)
                    if result.success:
                        results.append(
                            {
                                "success": True,
                                "markdown": result.markdown,
                                "html": result.html,
                                "url": result.url,
                                "title": getattr(result, "title", ""),
                                "error": None,
                            }
                        )
                    else:
                        results.append(
                            {
                                "success": False,
                                "markdown": None,
                                "html": None,
                                "url": url,
                                "title": None,
                                "error": getattr(
                                    result, "error_message", "Failed to fetch URL"
                                ),
                            }
                        )
            except Exception as e:
                results.append(
                    {
                        "success": False,
                        "markdown": None,
                        "html": None,
                        "url": url,
                        "title": None,
                        "error": str(e),
                    }
                )

        return results

    def fetch_multiple_urls(
        self,
        urls: list[str],
        timeout: int = 30000,
    ) -> list[dict]:
        """
        Fetch multiple URLs and return their content as markdown (synchronous wrapper).

        Args:
            urls: List of URLs to fetch
            timeout: Timeout in milliseconds (default: 30000)

        Returns:
            List of result dicts with 'success', 'markdown', 'html', 'url', and 'error' keys
        """
        # Apply rate limiting for each URL
        for _ in urls:
            self._apply_rate_limiting()

        loop = _get_or_create_loop()
        return loop.run_until_complete(self._fetch_multiple_urls_async(urls, timeout))

    def get_markdown_content(self, url: str, max_length: Optional[int] = None) -> str:
        """
        Convenience method to get just the markdown content from a URL.

        Args:
            url: The URL to fetch
            max_length: Optional maximum length of returned markdown

        Returns:
            Markdown content as string, or error message if failed
        """
        result = self.fetch_url(url)

        if result["success"] and result["markdown"]:
            markdown = result["markdown"]
            if max_length and len(markdown) > max_length:
                return markdown[:max_length] + "\n\n... [Content truncated]"
            return markdown
        else:
            return f"Error fetching {url}: {result['error']}"
