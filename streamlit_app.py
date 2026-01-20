import os
import tempfile

import streamlit as st

from src.pdf_processor import PDFProcessor
from src.verifier import FactVerifier

st.set_page_config(page_title="Textbook Fact Checker", page_icon="📚", layout="wide")

st.title("📚 Textbook Fact Checker")
st.markdown(
    """
This tool analyzes textbook PDFs (e.g., History) to verify facts using AI.
It extracts claims, cross-references them (using Google Search or internal knowledge), and identifies discrepancies.
"""
)

total_pages = 0
max_pages = None
custom_pages_input = ""
pages_to_process = []

# Sidebar Configuration
with st.sidebar:
    st.header("Configuration")

    provider = st.selectbox(
        "AI Provider", ["Google Gemini", "OpenAI / Custom", "LLM Foundry"], index=2
    )

    provider_key = "google" if provider == "Google Gemini" else "openai"

    if provider_key == "google":
        api_key = st.text_input(
            "Gemini API Key",
            type="password",
            value=os.environ.get("GEMINI_API_KEY", ""),
        )
        base_url = None
        model_name = st.text_input("Model Name", value="gemini-3-pro-preview")
        if not model_name.lower().startswith("gemini"):
            st.warning("For Google Gemini, please use a Gemini model name.")

        if not model_name.lower().startswith("models/"):
            model_name = f"models/{model_name}"

        st.caption("Uses Google Search Grounding for verification.")
    else:
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=os.environ.get("OPENAI_API_KEY", ""),
        )
        base_url = st.text_input(
            "Base URL (Optional)",
            value="",
            placeholder=(
                "https://api.openai.com/v1"
                if provider == "OpenAI / Custom"
                else "https://llmfoundry.straive.com/"
            ),
        )
        model_name = st.text_input("Model Name", value="gpt-4o")
        st.caption("Verify against internal knowledge base.")

    st.divider()
    st.header("Processing Options")
    process_full_textbook = st.checkbox("Process Full Textbook", value=True)
    if process_full_textbook:
        st.info(
            "⚠️ Processing the full textbook may take considerable time and resources."
        )
    else:
        pages_range = st.radio(
            "Select Pages to Process",
            ("First N Pages", "Custom Range"),
            index=0,
        )
        if pages_range == "Custom Range":
            custom_pages = st.text_input("Pages to process (e.g., 1-5,7,9)", value="")
            st.caption(
                "Note: Open-ended ranges (e.g., '5-') will be resolved after loading the PDF."
            )
            custom_pages_input = custom_pages
        else:
            max_pages = st.number_input(
                "Max Pages to Process", min_value=1, max_value=50, value=3
            )
            st.caption(f"Only the first {max_pages} page(s) will be processed.")

# Main Interface
uploaded_file = st.file_uploader("Upload Textbook PDF", type=["pdf"])

if st.button("Start Analysis", type="primary"):
    if not uploaded_file:
        st.warning("Please upload a PDF file.")
    elif not api_key:
        st.warning("Please provide an API Key.")
    else:
        # Save temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            temp_path = tmp_file.name

        try:
            # Initialize Processor
            st.info(f"📄 Loading PDF: {uploaded_file.name}")
            processor = PDFProcessor(temp_path)
            pages = list(processor.get_pages())
            total_pdf_pages = len(pages)
            if not process_full_textbook and custom_pages_input:
                try:
                    ranges = custom_pages_input.split(",")
                    for r in ranges:
                        r = r.strip()
                        if "-" in r:
                            if r.endswith("-"):
                                # "5-" format: from page 5 to end of document
                                start_page = int(r[:-1])
                                pages_to_process.extend(
                                    range(start_page, total_pdf_pages + 1)
                                )
                                continue

                            if r.startswith("-"):
                                # "-5" format : from page 1 to 5
                                pages_to_process.extend(range(1, int(r[1:]) + 1))
                                continue

                            start, end = map(int, r.split("-"))
                            pages_to_process.extend(range(start, end + 1))
                        else:
                            pages_to_process.append(int(r))
                    pages_to_process = sorted(set(pages_to_process))
                    st.info(
                        f"📋 Custom range resolved to {len(pages_to_process)} page(s): {', '.join(map(str, pages_to_process[:10]))}{' ...' if len(pages_to_process) > 10 else ''}"
                    )
                except Exception as e:
                    st.error(
                        f"Invalid page range format. Please use formats like '1-5,7,9'. Error: {str(e)}"
                    )
                    pages_to_process = []

            # Determine which pages to process
            if process_full_textbook:
                # Process all pages
                pages_to_analyze = pages
            elif pages_to_process:
                # Process custom range - filter by page numbers
                pages_to_analyze = [
                    (page_num, text)
                    for page_num, text in pages
                    if page_num in pages_to_process
                ]
            elif max_pages is not None:
                # Process first N pages
                pages_to_analyze = pages[:max_pages]
            else:
                pages_to_analyze = pages

            total_pages = len(pages_to_analyze)

            if total_pages == 0:
                st.warning(
                    "No pages selected for processing. Please adjust your page range."
                )
            else:
                st.success(
                    f"✅ Loaded {total_pdf_pages} pages from PDF. Processing {total_pages} page(s)."
                )

                # Create containers for organization
                st.divider()
                st.header("📊 Analysis Progress")

                # Overall progress
                overall_progress = st.progress(0, text="Starting analysis...")

                # Process each selected page
                for idx, (page_num, text) in enumerate(pages_to_analyze):
                    # Skip pages with minimal text
                    if len(text.strip()) < 50:
                        st.warning(f"⚠️ Page {page_num}: Skipped (insufficient text)")
                        overall_progress.progress(
                            (idx + 1) / total_pages,
                            text=f"Processing page {idx + 1}/{total_pages}",
                        )
                        continue

                    # Update overall progress
                    overall_progress.progress(
                        idx / total_pages,
                        text=f"Processing page {idx + 1}/{total_pages}: Page {page_num}",
                    )

                    # Create expander for this page
                    with st.expander(f"📄 Page {page_num}", expanded=True):
                        # Progress tracking for the 3-step process
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            step1_status = st.empty()
                            step1_status.warning("⏳ Step 1: Pending")

                        with col2:
                            step2_status = st.empty()
                            step2_status.warning("⏳ Step 2: Pending")

                        with col3:
                            step3_status = st.empty()
                            step3_status.warning("⏳ Step 3: Pending")

                        # Create a placeholder for detailed progress
                        progress_detail = st.empty()

                        # Create a placeholder for the report
                        report_placeholder = st.empty()

                        # Define progress callback function
                        def update_progress(step, status, message=""):
                            """Update the UI based on verification progress"""
                            status_icons = {
                                "started": "🔄",
                                "in_progress": "⚙️",
                                "completed": "✅",
                                "failed": "❌",
                            }

                            icon = status_icons.get(status, "🔄")

                            if step == 1:
                                if status == "started":
                                    step1_status.info(
                                        f"{icon} Step 1: Extracting claims..."
                                    )
                                    progress_detail.info(message)
                                elif status == "in_progress":
                                    step1_status.info(
                                        f"{icon} Step 1: Extracting claims..."
                                    )
                                    progress_detail.info(message)
                                elif status == "completed":
                                    step1_status.success(
                                        f"{icon} Step 1: Claims extracted"
                                    )
                                    progress_detail.success(message)
                                elif status == "failed":
                                    step1_status.error(f"{icon} Step 1: Failed")
                                    progress_detail.error(message)

                            elif step == 2:
                                if status == "started":
                                    step2_status.info(
                                        f"{icon} Step 2: Verifying with sources..."
                                    )
                                    progress_detail.info(message)
                                elif status == "in_progress":
                                    step2_status.info(
                                        f"{icon} Step 2: Searching sources..."
                                    )
                                    progress_detail.info(message)
                                elif status == "completed":
                                    step2_status.success(
                                        f"{icon} Step 2: Verification complete"
                                    )
                                    progress_detail.success(message)
                                elif status == "failed":
                                    step2_status.error(f"{icon} Step 2: Failed")
                                    progress_detail.error(message)

                            elif step == 3:
                                if status == "started":
                                    step3_status.info(
                                        f"{icon} Step 3: Generating report..."
                                    )
                                    progress_detail.info(message)
                                elif status == "in_progress":
                                    step3_status.info(
                                        f"{icon} Step 3: Analyzing results..."
                                    )
                                    progress_detail.info(message)
                                elif status == "completed":
                                    step3_status.success(f"{icon} Step 3: Report ready")
                                    progress_detail.success(message)
                                elif status == "failed":
                                    step3_status.error(f"{icon} Step 3: Failed")
                                    progress_detail.error(message)

                        try:
                            # Initialize Verifier with progress callback
                            verifier = FactVerifier(
                                api_key=api_key,
                                provider=provider_key,
                                base_url=base_url if base_url else None,
                                model_name=model_name,
                                progress_callback=update_progress,
                            )

                            # Run the verification (callback will update UI)
                            report = verifier.verify_chunk(text)

                            # Clear progress detail and display the report
                            progress_detail.empty()
                            report_placeholder.markdown("---")
                            report_placeholder.markdown(report)

                            st.success(f"✅ Page {page_num} analysis complete")

                        except Exception as e:
                            step1_status.error("❌ Step 1: Failed")
                            step2_status.error("❌ Step 2: Failed")
                            step3_status.error("❌ Step 3: Failed")
                            progress_detail.error(f"Error: {str(e)}")
                            st.error(f"Error on page {page_num}: {str(e)}")

                    # Small delay between pages for better UX
                    import time

                    time.sleep(0.5)

                # Final progress update
                overall_progress.progress(
                    1.0, text=f"✅ Analysis complete! Processed {total_pages} page(s)."
                )

                st.divider()
                st.balloons()
                st.success(
                    f"🎉 Successfully analyzed {total_pages} page(s) from {uploaded_file.name}"
                )

        except Exception as e:
            st.error(f"❌ An error occurred: {str(e)}")
            st.exception(e)

        finally:
            try:
                processor.close()
            except:
                pass

            if os.path.exists(temp_path):
                os.remove(temp_path)
                st.caption(f"🗑️ Cleaned up temporary file")
