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

# Sidebar Configuration
with st.sidebar:
    st.header("Configuration")

    provider = st.selectbox(
        "AI Provider", ["Google Gemini", "OpenAI / Custom"], index=0
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
            "Base URL (Optional)", value="", placeholder="https://api.openai.com/v1"
        )
        model_name = st.text_input("Model Name", value="gpt-4o")
        st.caption("Verify against internal knowledge base.")

    st.divider()
    st.header("Processing Options")
    max_pages = st.number_input(
        "Max Pages to Process", min_value=1, max_value=50, value=3
    )
    st.caption(f"Only {max_pages} pages will be processed per analysis run.")

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

            total_pages = min(len(pages), max_pages)
            st.success(
                f"✅ Loaded {len(pages)} pages. Processing first {total_pages} pages."
            )

            # Create containers for organization
            st.divider()
            st.header("📊 Analysis Progress")

            # Overall progress
            overall_progress = st.progress(0, text="Starting analysis...")

            # Process each page
            for idx, (page_num, text) in enumerate(pages[:total_pages]):
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
                                step1_status.success(f"{icon} Step 1: Claims extracted")
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
                1.0, text=f"✅ Analysis complete! Processed {total_pages} pages."
            )

            st.divider()
            st.balloons()
            st.success(
                f"🎉 Successfully analyzed {total_pages} pages from {uploaded_file.name}"
            )

        except Exception as e:
            st.error(f"❌ An error occurred: {str(e)}")
            st.exception(e)

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                st.caption(f"🗑️ Cleaned up temporary file")
