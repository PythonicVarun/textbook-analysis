import json
import os
import time

from google import genai
from google.genai import types
from openai import OpenAI

from src.tools import GoogleSearchTool, WebCrawler


class FactVerifier:
    def __init__(
        self,
        api_key=None,
        base_url=None,
        model_name=None,
        provider="google",
        progress_callback=None,
        use_crawl4ai=True,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.provider = provider
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        self.progress_callback = (
            progress_callback  # Callback function for progress updates
        )
        self.use_crawl4ai = use_crawl4ai

        # Initialize crawl4ai tools
        if self.use_crawl4ai:
            self.search_tool = GoogleSearchTool(headless=True, verbose=False)
            self.web_crawler = WebCrawler(headless=True, verbose=False)

        if not model_name:
            if self.provider == "google":
                self.model_name = "gemini-3-pro-preview"
            else:
                self.model_name = "gpt-5.2"
        else:
            self.model_name = model_name

        if self.provider == "google":
            if not self.api_key:
                self.api_key = self.gemini_api_key

            if self.api_key:
                self.client = genai.Client(api_key=self.api_key)

        elif self.provider == "openai":
            if not self.api_key:
                self.api_key = os.environ.get("OPENAI_API_KEY")

            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def _update_progress(self, step, status, message=""):
        """
        Update progress via callback if available.

        Args:
            step: 1, 2, or 3 (extraction, verification, analysis)
            status: 'started', 'in_progress', 'completed', 'failed'
            message: Optional detailed message
        """
        if self.progress_callback:
            self.progress_callback(step, status, message)

    def verify_chunk(self, text_chunk: str) -> str:
        """
        Verifies facts in the text chunk using a 3-step process.
        """
        if not self.api_key:
            return f"Error: API Key not provided for provider {self.provider}."

        if self.provider == "google":
            return self._verify_google(text_chunk)
        elif self.provider == "openai":
            return self._verify_openai(text_chunk)
        else:
            return "Error: Unknown provider."

    def _verify_google(self, text_chunk: str) -> str:
        try:
            # Step 1: EXTRACTION ONLY (No verification, no tools)
            self._update_progress(1, "started", "Starting claim extraction...")

            extraction_system = """You are a claim extraction specialist working in a 3-step fact-checking pipeline.

**YOUR ROLE IN THE PIPELINE:**
This is STEP 1 of 3. Your job is ONLY to extract claims. You will NOT verify them.
- Step 1 (YOU): Extract all factual claims
- Step 2 (Next): Verify claims using search tools
- Step 3 (Final): Analyze discrepancies and generate report

**YOUR WORK INSTRUCTIONS:**
1. Read the provided text carefully
2. Identify every statement that makes a verifiable factual claim
3. Extract claims about: dates, names, places, organizations, numbers/statistics, historical events, scientific facts, causal relationships, definitions
4. Write each claim as a clear, standalone statement
5. Number each claim sequentially
6. Do NOT evaluate truth or accuracy
7. Do NOT use any tools or search for information
8. Do NOT add commentary or explanations
9. Output ONLY the numbered list

**QUALITY CRITERIA:**
- Completeness: Don't miss any factual claims
- Clarity: Each claim should be understandable on its own
- Precision: Preserve specific details (exact dates, names, numbers)
- Brevity: Keep each claim to one sentence when possible"""

            extraction_prompt = f"""{extraction_system}

**Text to analyze:**
{text_chunk}

**Your output (numbered list only):**"""

            self._update_progress(1, "in_progress", "Extracting claims from text...")

            response_1 = self.client.models.generate_content(
                model=self.model_name, contents=extraction_prompt
            )
            extracted_claims = response_1.text

            # print(extracted_claims)

            self._update_progress(1, "completed", f"Extracted claims successfully")

            # Step 2: VERIFICATION WITH TOOLS (Search each claim)
            self._update_progress(2, "started", "Starting verification process...")

            verification_system = """You are a fact verification specialist working in a 3-step fact-checking pipeline.

**YOUR ROLE IN THE PIPELINE:**
This is STEP 2 of 3. You receive extracted claims and must verify them using search tools.
- Step 1 (Completed): Claims have been extracted
- Step 2 (YOU): Verify each claim with authoritative sources
- Step 3 (Next): Analyze discrepancies and generate final report

**YOUR WORK INSTRUCTIONS:**
1. Review the list of claims provided
2. For EACH claim, perform a Google Search
3. Search specifically for the factual elements (dates, names, events, numbers)
4. Identify 2-3 authoritative sources per claim when possible
5. Record the EXACT URLs of all sources used
6. Extract relevant quotes or facts from each source
7. Note if sources conflict or disagree
8. Summarize what the sources collectively indicate

**SOURCE QUALITY PRIORITY (search for these first):**
1. Government/official websites (.gov, .edu)
2. Academic institutions and peer-reviewed journals
3. Reputable news organizations (AP, Reuters, BBC, NYT, etc.)
4. Official organization websites
5. Established encyclopedias and reference works

**MANDATORY REQUIREMENTS:**
- Use Google Search for EVERY claim (no exceptions)
- Extract and record EXACT URLs (not just domain names)
- Quote specific passages that verify or contradict the claim
- If you cannot find sources, state that explicitly
- If sources conflict, document both sides

**OUTPUT FORMAT (strict):**
For each claim, use this exact structure:

---
**Claim #[N]:** [The exact claim text]

**Search Query Used:** "[Your search query]"

**Sources Found:**
1. **[Source Name/Title]**
   - URL: [Complete URL]
   - Relevant Information: "[Direct quote or specific fact]"
   - Date Published: [If available]

2. **[Source Name/Title]**
   - URL: [Complete URL]
   - Relevant Information: "[Direct quote or specific fact]"
   - Date Published: [If available]

**Verification Summary:** [What the sources indicate about this claim - does it confirm, contradict, or partially support?]
---"""

            verification_prompt = f"""{verification_system}

**Claims to verify:**
{extracted_claims}

**Begin verification (use the exact format above for each claim):**"""

            config = types.GenerateContentConfig(
                tools=[
                    types.Tool(
                        google_search=types.GoogleSearch(),
                    ),
                ],
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.HIGH
                ),
            )

            self._update_progress(2, "in_progress", "Searching and verifying claims...")

            time.sleep(1)
            response_2 = self.client.models.generate_content(
                model=self.model_name, contents=verification_prompt, config=config
            )
            verification_results = response_2.text

            self._update_progress(2, "completed", "Verification complete")

            # Step 3: FINAL ANALYSIS (Compare and categorize)
            self._update_progress(3, "started", "Starting final analysis...")

            final_system = """You are a fact-checking analyst working in a 3-step fact-checking pipeline.

**YOUR ROLE IN THE PIPELINE:**
This is STEP 3 of 3 - the FINAL step. You receive the original text and verified information, then produce the final report.
- Step 1 (Completed): Claims were extracted
- Step 2 (Completed): Claims were verified with sources
- Step 3 (YOU): Analyze discrepancies and generate final report

**CRITICAL SOURCE RESTRICTION:**
⚠️ YOU MUST ONLY USE SOURCES THAT APPEAR IN THE "VERIFIED INFORMATION" SECTION BELOW ⚠️
- DO NOT invent, fabricate, or hallucinate any URLs or sources
- DO NOT use your training data as a source - ONLY use the provided verification results
- DO NOT cite any URL that was not explicitly listed in the verified information
- If a claim was not verified in Step 2, mark it as "Unable to verify" - do NOT make up sources
- Every source URL you cite MUST be copy-pasted exactly from the verification results
- If verification results are incomplete, acknowledge this honestly

**YOUR WORK INSTRUCTIONS:**
1. Read the original text carefully
2. Review ONLY the verified information and sources provided below
3. Compare each claim in the original text against the verified facts FROM THE PROVIDED SOURCES ONLY
4. Categorize each claim using the category system below
5. Only report claims that have issues OR are particularly significant
6. If everything is accurate according to the verified sources, state that clearly
7. Provide specific corrections with source URLs FROM THE VERIFICATION RESULTS ONLY
8. Write in clear, professional language
9. Use the EXACT output format specified below
10. If a source URL was not fetched/verified in Step 2, DO NOT USE IT

**CATEGORY SYSTEM (use these exact symbols and labels):**
- ✅ **VERIFIED CORRECT**: Claim accurately matches verified sources (sources must be from Step 2)
- ❌ **FACTUAL ERROR**: Claim contradicts verified sources (wrong date, name, number, event, etc.)
- ⚠️ **OUTDATED INFORMATION**: Claim was historically correct but is no longer current
- ℹ️ **INTERPRETATIVE DIFFERENCE**: Claim involves interpretation/framing that differs from sources
- ⚡ **LACKS PRECISION**: Claim is vague, ambiguous, or missing important context
- ❓ **UNABLE TO VERIFY**: Could not find authoritative sources in Step 2 verification
- 🔴 **POTENTIALLY QUESTIONABLE (UNVERIFIED)**: Claim contradicts your training data BUT no verification sources were found to confirm/deny this. Use this category ONLY when:
  * The claim seems factually incorrect based on your training knowledge
  * NO verification sources were available in Step 2 to check the claim
  * You want to flag it for manual review
  * Mark this as speculative since you couldn't verify it externally

**QUALITY CRITERIA:**
- SOURCE INTEGRITY: NEVER cite a URL that doesn't appear in the verification results
- Accuracy: Only flag genuine issues based on fetched/verified sources
- Specificity: Explain exactly what's wrong and what's correct
- Evidence: Always include source URLs COPIED EXACTLY from verification results
- Clarity: Use simple, direct language
- Completeness: Don't miss significant issues
- Honesty: If verification was incomplete, say so

**MANDATORY OUTPUT FORMAT:**
You MUST use this exact structure:

# Fact-Checking Report

## Summary
[Write 1-2 sentences: "Verified [X] claims. Found [Y] issues: [Z] factual errors, [A] outdated information, [B] interpretative differences, [C] precision issues."]

## Detailed Analysis

### ✅ Verified Correct
[List 2-3 important claims that were verified as accurate, if any. Format: "• [Claim]: Confirmed by [source FROM VERIFICATION RESULTS]"]
[If all claims are correct, state: "All factual claims in the text have been verified as accurate."]

### ❌ Factual Errors
[For each error, use this format:]
**Claim:** "[Direct quote from original text]"
- **Issue:** [Explain specifically what is incorrect]
- **Correct Information:** [State the accurate fact FROM VERIFIED SOURCES]
- **Source:** [Source name with URL - MUST BE FROM VERIFICATION RESULTS]

[If none, write: "No factual errors found."]

### ⚠️ Outdated Information
[For each outdated item, use this format:]
**Claim:** "[Direct quote from original text]"
- **Issue:** [Explain why this is outdated]
- **Current Information:** [State the up-to-date fact FROM VERIFIED SOURCES]
- **Source:** [Source name with URL - MUST BE FROM VERIFICATION RESULTS]

[If none, write: "No outdated information found."]

### ℹ️ Interpretative Differences
[For each difference, use this format:]
**Claim:** "[Direct quote from original text]"
- **Issue:** [Explain how the interpretation differs]
- **Alternative Perspective:** [What sources emphasize or frame differently]
- **Source:** [Source name with URL - MUST BE FROM VERIFICATION RESULTS]

[If none, write: "No significant interpretative differences found."]

### ⚡ Lacks Precision
[For each imprecise claim, use this format:]
**Claim:** "[Direct quote from original text]"
- **Issue:** [Explain what is vague or missing]
- **More Precise Information:** [Provide the more accurate/complete formulation FROM VERIFIED SOURCES]
- **Source:** [Source name with URL - MUST BE FROM VERIFICATION RESULTS]

[If none, write: "No precision issues found."]

### ❓ Unable to Verify
[List any claims that could not be verified due to lack of sources in Step 2]
[If all claims were verified, write: "All claims had sufficient verification sources."]

### 🔴 Potentially Questionable (Unverified)
[List claims that seem incorrect based on your training data but couldn't be verified with external sources]
[Format: "**Claim:** [quote] - **Why Questionable:** [Explain why this contradicts your training knowledge] - **Status:** Could not find verification sources"]
[If none, write: "No unverified questionable claims identified."]
[If you list any claims here, add a disclaimer: "⚠️ Note: These are flagged based on training data only, not verified with external sources. Manual review recommended."]

## Conclusion
[Write 2-3 sentences summarizing the overall accuracy of the text. Be balanced and fair. Acknowledge any verification limitations.]"""

            final_prompt = f"""{final_system}

**ORIGINAL TEXT:**
```
{text_chunk}
```

**VERIFIED INFORMATION (USE ONLY THESE SOURCES):**
{verification_results}

⚠️ REMINDER: Only cite URLs that appear above. Do not invent or hallucinate any sources.

**Generate the final fact-checking report using the exact format specified above:**"""

            self._update_progress(3, "in_progress", "Generating final report...")

            time.sleep(1)
            response_3 = self.client.models.generate_content(
                model=self.model_name, contents=final_prompt
            )

            if response_3.text:
                self._update_progress(3, "completed", "Report generated successfully")
                return response_3.text
            else:
                self._update_progress(3, "failed", "No response generated")
                return "No response generated in final step."

        except Exception as e:
            error_msg = str(e)
            if "extraction" in error_msg.lower():
                self._update_progress(1, "failed", f"Extraction failed: {error_msg}")
            elif "verification" in error_msg.lower():
                self._update_progress(2, "failed", f"Verification failed: {error_msg}")
            else:
                self._update_progress(3, "failed", f"Analysis failed: {error_msg}")

            return f"Error verifying chunk (Gemini): {str(e)}"

    def _verify_openai(self, text_chunk: str) -> str:
        try:
            # Step 1: EXTRACTION ONLY
            self._update_progress(1, "started", "Starting claim extraction...")

            extraction_system = """You are a claim extraction specialist working in a 3-step fact-checking pipeline.

**YOUR ROLE IN THE PIPELINE:**
This is STEP 1 of 3. Your job is ONLY to extract claims. You will NOT verify them.
- Step 1 (YOU): Extract all factual claims
- Step 2 (Next): Verify claims using search tools
- Step 3 (Final): Analyze discrepancies and generate report

**YOUR WORK INSTRUCTIONS:**
1. Read the provided text carefully
2. Identify every statement that makes a verifiable factual claim
3. Extract claims about: dates, names, places, organizations, numbers/statistics, historical events, scientific facts, causal relationships, definitions
4. Write each claim as a clear, standalone statement
5. Number each claim sequentially
6. Do NOT evaluate truth or accuracy
7. Do NOT use any tools or search for information
8. Do NOT add commentary or explanations
9. Output ONLY the numbered list

**QUALITY CRITERIA:**
- Completeness: Don't miss any factual claims
- Clarity: Each claim should be understandable on its own
- Precision: Preserve specific details (exact dates, names, numbers)
- Brevity: Keep each claim to one sentence when possible"""

            extraction_messages = [
                {"role": "system", "content": extraction_system},
                {
                    "role": "user",
                    "content": f"""**Text to analyze:**
{text_chunk}

**Your output (numbered list only):**""",
                },
            ]

            self._update_progress(1, "in_progress", "Extracting claims from text...")

            resp1 = self.client.chat.completions.create(
                model=self.model_name, messages=extraction_messages
            )
            extracted_claims = resp1.choices[0].message.content

            self._update_progress(1, "completed", "Extracted claims successfully")

            # Step 2: VERIFICATION WITH TOOLS
            self._update_progress(2, "started", "Starting verification process...")

            verification_system = """You are a fact verification specialist working in a 3-step fact-checking pipeline.

**YOUR ROLE IN THE PIPELINE:**
This is STEP 2 of 3. You receive extracted claims and must verify them using search tools.
- Step 1 (Completed): Claims have been extracted
- Step 2 (YOU): Verify each claim with authoritative sources
- Step 3 (Next): Analyze discrepancies and generate final report

**YOUR WORK INSTRUCTIONS:**
1. Review the list of claims provided
2. For EACH claim, perform a Google Search using the google_search tool
3. When you find relevant URLs in search results, use the fetch_url tool to retrieve full content
4. Search specifically for the factual elements (dates, names, events, numbers)
5. Identify 2-3 authoritative sources per claim when possible
6. Record the EXACT URLs of all sources used
7. Extract relevant quotes or facts from each source BY FETCHING THE URL
8. Note if sources conflict or disagree
9. Summarize what the sources collectively indicate

**CRITICAL WORKFLOW:**
- First: Use google_search to find relevant sources
- Second: Use fetch_url on the most authoritative URLs from search results
- Third: Extract specific information from the fetched content
- Fourth: Compare information across multiple sources

**SOURCE QUALITY PRIORITY (search for these first):**
1. Government/official websites (.gov, .edu)
2. Academic institutions and peer-reviewed journals
3. Reputable news organizations (AP, Reuters, BBC, NYT, etc.)
4. Official organization websites
5. Established encyclopedias and reference works

**MANDATORY REQUIREMENTS:**
- Use google_search for EVERY claim (no exceptions)
- Use fetch_url to verify content from at least 2 URLs per claim
- Extract and record EXACT URLs (not just domain names)
- Quote specific passages that verify or contradict the claim FROM THE FETCHED CONTENT
- If you cannot find sources, state that explicitly
- If sources conflict, document both sides with quotes from actual fetched content

**OUTPUT FORMAT (strict):**
For each claim, use this exact structure:

---
**Claim #[N]:** [The exact claim text]

**Search Query Used:** "[Your search query]"

**Sources Found and Verified:**
1. **[Source Name/Title]**
- URL: [Complete URL]
- Content Fetched: Yes/No
- Relevant Information: "[Direct quote from fetched content or snippet]"
- Date Published: [If available]
- Verification Status: [Confirms/Contradicts/Partially Supports]

2. **[Source Name/Title]**
- URL: [Complete URL]
- Content Fetched: Yes/No
- Relevant Information: "[Direct quote from fetched content or snippet]"
- Date Published: [If available]
- Verification Status: [Confirms/Contradicts/Partially Supports]

**Verification Summary:** [What the sources indicate about this claim based on fetched content - does it confirm, contradict, or partially support?]
---

**IMPORTANT:** You MUST use the tools (google_search and fetch_url) for every claim. Do not just rely on snippets - fetch the actual URLs to verify content."""

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "google_search",
                        "description": "Search the web for information using Google to verify claims. Returns search results as markdown with titles, URLs, and snippets.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query.",
                                }
                            },
                            "required": ["query"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "fetch_url",
                        "description": "Fetch the content of a specific URL and return it as markdown. Use this to get detailed information from a source found via search. You MUST use this tool to verify the actual content of URLs found in search results.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "url": {
                                    "type": "string",
                                    "description": "The URL to fetch content from.",
                                }
                            },
                            "required": ["url"],
                        },
                    },
                },
            ]

            verification_messages = [
                {"role": "system", "content": verification_system},
                {
                    "role": "user",
                    "content": f"""**Claims to verify:**
{extracted_claims}

**Begin verification (use the exact format above for each claim):**

Remember to:
1. Use google_search for each claim
2. Use fetch_url on at least 2 authoritative URLs from the search results
3. Extract quotes from the fetched content, not just snippets
4. Document which URLs you actually fetched and verified""",
                },
            ]

            self._update_progress(2, "in_progress", "Searching and verifying claims...")

            iteration = 0
            max_iterations = 100
            while iteration < max_iterations:
                iteration += 1

                resp2 = self.client.chat.completions.create(
                    model=self.model_name, messages=verification_messages, tools=tools
                )

                message = resp2.choices[0].message

                # If no tool calls, we're done with this step
                if not message.tool_calls:
                    verification_results = message.content
                    break

                # Add assistant's message with tool calls
                verification_messages.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": tc.type,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in message.tool_calls
                        ],
                    }
                )

                # Process all tool calls
                for tool_call in message.tool_calls:
                    try:
                        args = json.loads(tool_call.function.arguments)
                        print(
                            f"[Iteration {iteration}] Performing tool call: {tool_call.function.name} with args {args}"
                        )

                        if tool_call.function.name == "google_search":
                            query = args.get("query")
                            tool_result = self._perform_google_search(query)
                        elif tool_call.function.name == "fetch_url":
                            url = args.get("url")
                            tool_result = self._fetch_url(url)
                        else:
                            tool_result = f"Unknown tool: {tool_call.function.name}"

                    except Exception as e:
                        tool_result = (
                            f"Error performing {tool_call.function.name}: {str(e)}"
                        )

                    # Add tool result to messages
                    verification_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result,
                        }
                    )

            if iteration >= max_iterations:
                verification_results = "Verification process reached maximum iterations. Proceeding with available data."

            self._update_progress(2, "completed", "Verification complete")

            # Step 3: FINAL ANALYSIS
            self._update_progress(3, "started", "Starting final analysis...")

            final_system = """You are a fact-checking analyst working in a 3-step fact-checking pipeline.

**YOUR ROLE IN THE PIPELINE:**
This is STEP 3 of 3 - the FINAL step. You receive the original text and verified information, then produce the final report.
- Step 1 (Completed): Claims were extracted
- Step 2 (Completed): Claims were verified with sources (URLs were actually fetched)
- Step 3 (YOU): Analyze discrepancies and generate final report

**CRITICAL SOURCE RESTRICTION - READ CAREFULLY:**
⚠️ YOU MUST ONLY USE SOURCES THAT APPEAR IN THE "VERIFIED INFORMATION" SECTION BELOW ⚠️
- DO NOT invent, fabricate, or hallucinate any URLs or sources
- DO NOT use your training data or prior knowledge as a source - ONLY use the provided verification results
- DO NOT cite any URL that was not explicitly listed and fetched in the verified information
- If a claim was not verified in Step 2, mark it as "Unable to verify" - do NOT make up sources
- Every source URL you cite MUST be copy-pasted exactly from the verification results
- Only use sources marked as "Content Fetched: Yes" - do not use unfetched URLs
- If verification results are incomplete, acknowledge this honestly
- NEVER generate fake URLs like "example.com" or "source.org"

**YOUR WORK INSTRUCTIONS:**
1. Read the original text carefully
2. Review ONLY the verified information and sources provided below (the ones that were actually fetched)
3. Compare each claim in the original text against the verified facts FROM THE PROVIDED FETCHED SOURCES ONLY
4. Categorize each claim using the category system below
5. Only report claims that have issues OR are particularly significant
6. If everything is accurate according to the verified sources, state that clearly
7. Provide specific corrections with source URLs COPIED EXACTLY FROM THE VERIFICATION RESULTS
8. Write in clear, professional language
9. Use the EXACT output format specified below
10. If a source URL was not fetched/verified in Step 2, DO NOT USE IT

**CATEGORY SYSTEM (use these exact symbols and labels):**
- ✅ **VERIFIED CORRECT**: Claim accurately matches verified sources (sources must be from Step 2 with fetched content)
- ❌ **FACTUAL ERROR**: Claim contradicts verified sources (wrong date, name, number, event, etc.)
- ⚠️ **OUTDATED INFORMATION**: Claim was historically correct but is no longer current
- ℹ️ **INTERPRETATIVE DIFFERENCE**: Claim involves interpretation/framing that differs from sources
- ⚡ **LACKS PRECISION**: Claim is vague, ambiguous, or missing important context
- ❓ **UNABLE TO VERIFY**: Could not find authoritative sources in Step 2 verification
- 🔴 **POTENTIALLY QUESTIONABLE (UNVERIFIED)**: Claim contradicts your training data BUT no verification sources were found to confirm/deny this. Use this category ONLY when:
  * The claim seems factually incorrect based on your training knowledge
  * NO verification sources with fetched content were available in Step 2 to check the claim
  * You want to flag it for manual review
  * Mark this as speculative since you couldn't verify it externally

**QUALITY CRITERIA:**
- SOURCE INTEGRITY: NEVER cite a URL that doesn't appear in the verification results with "Content Fetched: Yes"
- Accuracy: Only flag genuine issues based on fetched/verified sources
- Specificity: Explain exactly what's wrong and what's correct
- Evidence: Always include source URLs COPIED EXACTLY from verification results
- Clarity: Use simple, direct language
- Completeness: Don't miss significant issues
- Honesty: If verification was incomplete, say so

**MANDATORY OUTPUT FORMAT:**
You MUST use this exact structure:

# Fact-Checking Report

## Summary
[Write 1-2 sentences: "Verified [X] claims. Found [Y] issues: [Z] factual errors, [A] outdated information, [B] interpretative differences, [C] precision issues."]

## Detailed Analysis

### ✅ Verified Correct
[List 2-3 important claims that were verified as accurate, if any. Format: "• [Claim]: Confirmed by [source FROM VERIFICATION RESULTS]"]
[If all claims are correct, state: "All factual claims in the text have been verified as accurate."]

### ❌ Factual Errors
[For each error, use this format:]
**Claim:** "[Direct quote from original text]"
- **Issue:** [Explain specifically what is incorrect]
- **Correct Information:** [State the accurate fact FROM VERIFIED SOURCES]
- **Source:** [Source name with URL - MUST BE FROM VERIFICATION RESULTS WITH FETCHED CONTENT]

[If none, write: "No factual errors found."]

### ⚠️ Outdated Information
[For each outdated item, use this format:]
**Claim:** "[Direct quote from original text]"
- **Issue:** [Explain why this is outdated]
- **Current Information:** [State the up-to-date fact FROM VERIFIED SOURCES]
- **Source:** [Source name with URL - MUST BE FROM VERIFICATION RESULTS WITH FETCHED CONTENT]

[If none, write: "No outdated information found."]

### ℹ️ Interpretative Differences
[For each difference, use this format:]
**Claim:** "[Direct quote from original text]"
- **Issue:** [Explain how the interpretation differs]
- **Alternative Perspective:** [What sources emphasize or frame differently]
- **Source:** [Source name with URL - MUST BE FROM VERIFICATION RESULTS WITH FETCHED CONTENT]

[If none, write: "No significant interpretative differences found."]

### ⚡ Lacks Precision
[For each imprecise claim, use this format:]
**Claim:** "[Direct quote from original text]"
- **Issue:** [Explain what is vague or missing]
- **More Precise Information:** [Provide the more accurate/complete formulation FROM VERIFIED SOURCES]
- **Source:** [Source name with URL - MUST BE FROM VERIFICATION RESULTS WITH FETCHED CONTENT]

[If none, write: "No precision issues found."]

### ❓ Unable to Verify
[List any claims that could not be verified due to lack of fetched sources in Step 2]
[If all claims were verified, write: "All claims had sufficient verification sources."]

### 🔴 Potentially Questionable (Unverified)
[List claims that seem incorrect based on your training data but couldn't be verified with fetched external sources]
[Format: "**Claim:** [quote] - **Why Questionable:** [Explain why this contradicts your training knowledge] - **Status:** Could not find verification sources with fetched content"]
[If none, write: "No unverified questionable claims identified."]
[If you list any claims here, add a disclaimer: "⚠️ Note: These are flagged based on training data only, not verified with external sources. Manual review recommended."]

## Conclusion
[Write 2-3 sentences summarizing the overall accuracy of the text. Be balanced and fair. Acknowledge any verification limitations.]"""

            final_messages = [
                {"role": "system", "content": final_system},
                {
                    "role": "user",
                    "content": f"""**ORIGINAL TEXT:**
```
{text_chunk}
```

**VERIFIED INFORMATION (USE ONLY THESE SOURCES - ONLY URLs WITH "Content Fetched: Yes"):**
{verification_results}

⚠️ CRITICAL REMINDER:
- Only cite URLs that appear above with "Content Fetched: Yes"
- Do not invent, fabricate, or hallucinate any sources
- Copy-paste URLs exactly as they appear in the verification results
- If a claim wasn't verified, mark it as "Unable to Verify"

**Generate the final fact-checking report using the exact format specified above:**""",
                },
            ]

            self._update_progress(3, "in_progress", "Generating final report...")

            resp3 = self.client.chat.completions.create(
                model=self.model_name, messages=final_messages
            )

            self._update_progress(3, "completed", "Report generated successfully")

            return resp3.choices[0].message.content

        except Exception as e:
            error_msg = str(e)
            if "extraction" in error_msg.lower():
                self._update_progress(1, "failed", f"Extraction failed: {error_msg}")
            elif "verification" in error_msg.lower():
                self._update_progress(2, "failed", f"Verification failed: {error_msg}")
            else:
                self._update_progress(3, "failed", f"Analysis failed: {error_msg}")

            return f"Error verifying chunk (OpenAI): {str(e)}"

    def _perform_google_search(self, query: str) -> str:
        """
        Perform Google search using crawl4ai or fall back to Gemini API.
        """
        # Try crawl4ai first if enabled
        if self.use_crawl4ai:
            try:
                result = self.search_tool.search_and_get_markdown(
                    query, num_results=10, max_length=8000
                )
                # print(result)
                if result and not result.startswith("Search failed"):
                    return result
            except Exception as e:
                print(f"crawl4ai search failed, falling back to Gemini: {e}")

        # Fall back to Gemini API for search
        if not self.gemini_api_key:
            return (
                "Error: Search unavailable (Missing GEMINI_API_KEY for search proxy)."
            )
        try:
            # Use a temporary client for the search
            client = genai.Client(api_key=self.gemini_api_key)

            search_prompt = f"""Search for: {query}

Provide:
1. Top 3-5 most authoritative sources
2. The EXACT URL for each source
3. Relevant quotes or facts from each source
4. Publication dates if available

Focus on credible sources (government, academic, reputable news, official docs)."""

            config = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )

            response = client.models.generate_content(
                model="models/gemini-3-pro-preview",
                contents=search_prompt,
                config=config,
            )

            return response.text if response.text else "No results found."
        except Exception as e:
            return f"Search error: {str(e)}"

    def _fetch_url(self, url: str, max_length: int = 10000) -> str:
        """
        Fetch a URL and return its content as markdown using crawl4ai.

        Args:
            url: The URL to fetch

        Returns:
            Markdown content from the URL
        """
        if not self.use_crawl4ai:
            return f"Error: Web crawling not enabled. Set use_crawl4ai=True."

        try:
            result = self.web_crawler.get_markdown_content(url, max_length=max_length)
            # print(result)
            return result
        except Exception as e:
            return f"Error fetching URL {url}: {str(e)}"

    def _fetch_multiple_urls(self, urls: list[str], max_length: int = 5000) -> str:
        """
        Fetch multiple URLs and return their combined markdown content.

        Args:
            urls: List of URLs to fetch
            max_length: Maximum length per URL

        Returns:
            Combined markdown content from all URLs
        """
        if not self.use_crawl4ai:
            return "Error: Web crawling not enabled. Set use_crawl4ai=True."

        try:
            results = self.web_crawler.fetch_multiple_urls(urls)
            output = ""

            for result in results:
                if result["success"]:
                    content = result["markdown"] or ""
                    if len(content) > max_length:
                        content = content[:max_length] + "\n\n... [Content truncated]"

                    output += f"\n\n## Content from: {result['url']}\n\n"
                    output += content
                else:
                    output += f"\n\n## Failed to fetch: {result['url']}\n"
                    output += f"Error: {result['error']}\n"

            return output.strip()
        except Exception as e:
            return f"Error fetching URLs: {str(e)}"
