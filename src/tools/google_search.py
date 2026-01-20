import asyncio
import os
import time
import urllib.parse
from typing import Optional

import requests
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from fake_useragent import UserAgent


def _get_or_create_loop():
    """Return an event loop with a Windows-friendly policy.

    Playwright on Windows needs a subprocess-capable loop. This helper ensures
    we are using a compatible policy before creating or returning the loop.
    """

    if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class GoogleSearchTool:
    """
    A tool for performing Google searches and extracting results using crawl4ai.
    Falls back to serper.dev API if crawl4ai fails (e.g., CAPTCHA blocking).
    """

    GOOGLE_SEARCH_URL = "https://www.google.com/search"
    SERPER_API_URL = "https://google.serper.dev/search"

    def __init__(
        self,
        headless: bool = True,
        verbose: bool = False,
        serper_api_key: Optional[str] = None,
    ):
        """
        Initialize the Google search tool.

        Args:
            headless: Run browser in headless mode (default: True)
            verbose: Enable verbose logging (default: False)
            serper_api_key: Optional serper.dev API key (falls back to SERPER_API_KEY env var)
        """
        self.headless = headless
        self.verbose = verbose
        self._request_count = 0
        self._last_request_time = 0

        # Serper.dev API key for fallback
        self.serper_api_key = serper_api_key or os.environ.get("SERPER_API_KEY")

        # User agent rotator
        self._ua = UserAgent()

        # Crawl4Ai browser configuration
        self.browser_config = BrowserConfig(
            headless=headless,
            verbose=verbose,
            enable_stealth=True,
        )

    def _build_search_url(self, query: str, num_results: int = 10) -> str:
        """
        Build a Google search URL from a query.

        Args:
            query: The search query
            num_results: Number of results to request (default: 10)

        Returns:
            Complete Google search URL
        """
        params = {
            "q": query,
            "num": num_results,
            "hl": "en",  # English results
        }
        return f"{self.GOOGLE_SEARCH_URL}?{urllib.parse.urlencode(params)}"

    def _get_user_agent(self) -> str:
        """Rotate through user agents to avoid detection."""
        return self._ua.random

    def _apply_rate_limiting(self):
        """Apply rate limiting between requests to avoid bot detection."""
        # Minimum 2-4 seconds between requests
        min_delay = 2
        max_delay = 4

        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < min_delay:
            delay = min_delay + (self._request_count % 2)  # Vary delay slightly
            time.sleep(delay - time_since_last)

        self._last_request_time = time.time()
        self._request_count += 1

    def _search_with_serper(self, query: str, num_results: int = 10) -> dict:
        """
        Fallback search using serper.dev API.

        Args:
            query: The search query
            num_results: Number of results to fetch

        Returns:
            dict with 'success', 'query', 'markdown', 'results', and 'error' keys
        """
        if not self.serper_api_key:
            return {
                "success": False,
                "query": query,
                "markdown": None,
                "results": [],
                "url": None,
                "error": "Serper API key not configured. Set SERPER_API_KEY environment variable.",
            }

        try:
            headers = {
                "X-API-KEY": self.serper_api_key,
                "Content-Type": "application/json",
            }

            payload = {
                "q": query,
                "num": num_results,
                "hl": "en",
            }

            response = requests.post(
                self.SERPER_API_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "query": query,
                    "markdown": None,
                    "results": [],
                    "url": None,
                    "error": f"Serper API error: {response.status_code} - {response.text}",
                }

            data = response.json()

            # Parse organic results
            results = []
            organic = data.get("organic", [])
            for item in organic[:num_results]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                    }
                )

            # Build markdown from results
            markdown = f"# Search Results for: {query}\n\n"
            for i, r in enumerate(results, 1):
                markdown += f"## {i}. {r['title']}\n"
                markdown += f"**URL:** {r['url']}\n\n"
                if r["snippet"]:
                    markdown += f"{r['snippet']}\n\n"
                markdown += "---\n\n"

            # Add knowledge graph if available
            if "knowledgeGraph" in data:
                kg = data["knowledgeGraph"]
                markdown += "\n## Knowledge Graph\n\n"
                if "title" in kg:
                    markdown += f"**{kg['title']}**\n\n"
                if "description" in kg:
                    markdown += f"{kg['description']}\n\n"

            # Add answer box if available
            if "answerBox" in data:
                ab = data["answerBox"]
                markdown = (
                    f"## Quick Answer\n\n{ab.get('answer', ab.get('snippet', ''))}\n\n"
                    + markdown
                )

            return {
                "success": True,
                "query": query,
                "markdown": markdown,
                "results": results,
                "url": f"https://google.com/search?q={urllib.parse.quote(query)}",
                "error": None,
                "source": "serper",
            }

        except Exception as e:
            return {
                "success": False,
                "query": query,
                "markdown": None,
                "results": [],
                "url": None,
                "error": f"Serper API error: {str(e)}",
            }

    def _is_blocked_response(self, markdown: str) -> bool:
        """Check if the response indicates we've been blocked by Google."""
        if not markdown:
            return False

        blocked_indicators = [
            "unusual traffic",
            "automated requests",
            "CAPTCHA",
            "captcha",
            "robot",
            "sorry/index",
            "detected unusual traffic",
        ]

        return any(
            indicator.lower() in markdown.lower() for indicator in blocked_indicators
        )

    async def _search_async(
        self,
        query: str,
        num_results: int = 10,
        timeout: int = 30000,
    ) -> dict:
        """
        Asynchronously perform a Google search and return results as markdown.

        Args:
            query: The search query
            num_results: Number of results to fetch (default: 10)
            timeout: Timeout in milliseconds (default: 30000)

        Returns:
            dict with 'success', 'query', 'markdown', 'results', and 'error' keys
        """
        try:
            search_url = self._build_search_url(query, num_results)
            user_agent = self._get_user_agent()

            # Create browser config with rotating user agent
            browser_config = BrowserConfig(
                headless=self.headless,
                verbose=self.verbose,
                user_agent=user_agent,
                enable_stealth=True,
                light_mode=True,  # Faster, lighter crawling
            )

            run_config = CrawlerRunConfig(
                page_timeout=timeout,
                cache_mode=CacheMode.BYPASS,  # Don't use cache to get fresh results
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=search_url, config=run_config)

                if result.success:
                    # Parse the markdown to extract search results
                    parsed_results = self._parse_search_results(result.markdown)

                    return {
                        "success": True,
                        "query": query,
                        "markdown": result.markdown,
                        "results": parsed_results,
                        "url": search_url,
                        "error": None,
                    }
                else:
                    return {
                        "success": False,
                        "query": query,
                        "markdown": None,
                        "results": [],
                        "url": search_url,
                        "error": getattr(
                            result, "error_message", "Failed to perform search"
                        ),
                    }

        except Exception as e:
            return {
                "success": False,
                "query": query,
                "markdown": None,
                "results": [],
                "url": None,
                "error": str(e),
            }

    def _parse_search_results(self, markdown: str) -> list[dict]:
        """
        Parse search results from the markdown content.

        Args:
            markdown: The markdown content from Google search page

        Returns:
            List of result dicts with 'title', 'url', 'snippet' keys
        """
        results = []

        if not markdown:
            return results

        # Split by lines and look for patterns
        lines = markdown.split("\n")
        current_result = {}

        for line in lines:
            line = line.strip()

            # Look for markdown links which often contain titles and URLs
            if line.startswith("[") and "](" in line:
                try:
                    # Extract title and URL from markdown link format [title](url)
                    title_end = line.index("](")
                    title = line[1:title_end]
                    url_start = title_end + 2
                    url_end = line.index(")", url_start)
                    url = line[url_start:url_end]

                    # Skip Google internal links
                    if (
                        url.startswith("http")
                        and "google.com" not in url
                        and "gstatic.com" not in url
                    ):
                        if current_result:
                            results.append(current_result)
                        current_result = {
                            "title": title,
                            "url": url,
                            "snippet": "",
                        }
                except (ValueError, IndexError):
                    pass

            # Add text as snippet if we have a current result
            elif current_result and line and not line.startswith(("#", "[", "!", "*")):
                if len(line) > 20:  # Skip very short lines
                    if current_result["snippet"]:
                        current_result["snippet"] += " " + line
                    else:
                        current_result["snippet"] = line

        # Add the last result
        if current_result:
            results.append(current_result)

        return results[:10]  # Limit to top 10 results

    def search(
        self,
        query: str,
        num_results: int = 10,
        timeout: int = 30000,
    ) -> dict:
        """
        Perform a Google search and return results (synchronous wrapper).

        Args:
            query: The search query
            num_results: Number of results to fetch (default: 10)
            timeout: Timeout in milliseconds (default: 30000)

        Returns:
            dict with 'success', 'query', 'markdown', 'results', and 'error' keys
        """
        # Apply rate limiting before the request
        self._apply_rate_limiting()

        loop = _get_or_create_loop()
        result = loop.run_until_complete(
            self._search_async(query, num_results, timeout)
        )

        # Check if we got blocked and need to fall back to serper.dev
        if not result["success"] or self._is_blocked_response(
            result.get("markdown", "")
        ):
            if self.serper_api_key:
                if self.verbose:
                    print(f"crawl4ai blocked, falling back to serper.dev for: {query}")
                return self._search_with_serper(query, num_results)

        return result

    def search_and_get_markdown(
        self,
        query: str,
        num_results: int = 10,
        max_length: Optional[int] = None,
    ) -> str:
        """
        Convenience method to perform a search and return formatted markdown.

        Args:
            query: The search query
            num_results: Number of results to fetch (default: 10)
            max_length: Optional maximum length of returned content

        Returns:
            Formatted markdown string with search results
        """
        result = self.search(query, num_results)

        if not result["success"]:
            return f"Search failed for '{query}': {result['error']}"

        # Format results as clean markdown
        output = f"# Search Results for: {query}\n\n"

        if result["results"]:
            for i, r in enumerate(result["results"], 1):
                output += f"## {i}. {r['title']}\n"
                output += f"**URL:** {r['url']}\n\n"
                if r["snippet"]:
                    output += f"{r['snippet']}\n\n"
                output += "---\n\n"
        else:
            # Fall back to raw markdown if parsing didn't work well
            output += result["markdown"] or "No results found."

        if max_length and len(output) > max_length:
            return output[:max_length] + "\n\n... [Results truncated]"

        return output

    def search_for_verification(
        self,
        claim: str,
        additional_context: str = "",
    ) -> str:
        """
        Search specifically for fact verification purposes.

        Args:
            claim: The claim to verify
            additional_context: Additional context to include in search

        Returns:
            Formatted markdown with search results for verification
        """
        # Build a verification-focused query
        query = claim
        if additional_context:
            query = f"{claim} {additional_context}"

        result = self.search(query, num_results=5)

        if not result["success"]:
            return f"Could not search for verification: {result['error']}"

        output = f"## Verification Search: {claim}\n\n"
        output += f"**Query:** {query}\n\n"

        if result["results"]:
            output += "### Sources Found:\n\n"
            for i, r in enumerate(result["results"], 1):
                output += f"**{i}. [{r['title']}]({r['url']})**\n"
                if r["snippet"]:
                    output += f"> {r['snippet']}\n\n"
        else:
            output += "No relevant sources found.\n"

        return output
