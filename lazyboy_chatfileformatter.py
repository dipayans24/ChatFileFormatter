import streamlit as st
import pandas as pd
import re
import pytz
import io
import os
import tempfile, openpyxl
from datetime import datetime

# Pre-compile regex pattern at module level (avoids recompilation on every call)
_INVALID_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

def extractValidText(text):
    return _INVALID_CHARS.sub('', str(text))

def _submit_search():
    st.session_state["active_search"] = st.session_state.get("search_name", "")

def formatChat(chats):
    timestamps, comments = [], []
    current_comment = None

    for raw in chats:
        line = _INVALID_CHARS.sub('', raw.decode("utf-8"))

        if any(kw in line for kw in ("panelists:", " Everyone:", "(direct message)")):
            if current_comment is not None:
                timestamps.append(current_comment)
                comments.append(None)
            current_comment = line
        else:
            if current_comment is not None:
                timestamps.append(current_comment)
                comments.append(line.strip())
                current_comment = None

    if current_comment is not None:
        timestamps.append(current_comment)
        comments.append(None)

    data = pd.DataFrame({"TimeStamp": timestamps, "Comments": comments})

    ts_split = data["TimeStamp"].str.split(" ", n=1, expand=True)
    info_split = ts_split[1].str.split(" to ", n=1, expand=True)

    data["Time"] = ts_split[0]
    data["From"] = info_split[0].str.replace("From", "", regex=False).str.strip()
    data["To"]   = (
        info_split[1]
        .str.replace(":", "", regex=False)
        .str.strip()
        .str.replace(", [Hh]osts and panelists", "", regex=True)
    )
    data["Comments"] = data["Comments"].str.strip()

    return data[["Time", "From", "To", "Comments"]]


def on_file_change():
    """Called when the file uploader changes — wipes all processed output."""
    for key in ["chat_data", "output_buffer", "output_filename", "processed", "search_name", "active_search"]:
        if key in [ "search_name", "active_search"]:
            st.session_state[key] = ""
        else:
            st.session_state.pop(key, None)


st.set_page_config(
    page_title="Zoom Chat Formatter",
    page_icon="💬",
    layout="wide"
)

st.title("💬 Zoom Chat File Formatter")
st.markdown("Upload one or more webinar chat `.txt` files to generate a formatted Excel report.")

# --- File Upload ---
uploaded_files = st.file_uploader(
    "Upload Chat File(s)",
    type=["txt"],
    accept_multiple_files=True,
    help="Select one or more Zoom/Webinar chat export files (.txt)",
    on_change=on_file_change
)

if uploaded_files:
    st.success(f"✅ {len(uploaded_files)} file(s) uploaded: {', '.join([f.name for f in uploaded_files])}")
    supportTeamName = st.text_input(
        "Enter the support team name:",
        max_chars=25,
        placeholder="Optional, enter the support team name to get the links shared, if any."
    )

    if st.button("🚀 Process Files", type="primary"):
        # Clear previous results AND both search keys before processing
        on_file_change()

        try:
            with st.spinner("Processing chat files..."):

                chats = []
                with tempfile.TemporaryDirectory() as tmpdir:
                    for uploaded_file in uploaded_files:
                        file_path = os.path.join(tmpdir, uploaded_file.name)
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.read())
                        with open(file_path, "rb+") as f:
                            chats.extend(f.readlines())

                data = formatChat(chats)

                ChatAnalysis = data.groupby(by="From", as_index=False).agg(
                    UniqueCount=("Comments", "nunique"),
                    TotalCount=("Comments", "count")
                )
                ChatAnalysis["SpamPercentage"] = ChatAnalysis.apply(
                    lambda x: round(100 - ((x["UniqueCount"] * 100) / x["TotalCount"]), 2), axis=1
                )
                ChatAnalysis = ChatAnalysis[ChatAnalysis["UniqueCount"] > 1]
                ChatAnalysis["Replies"] = ChatAnalysis["From"].apply(
                    lambda x: data[data["To"] == x]["To"].count()
                )
                ChatAnalysis.sort_values(by="SpamPercentage", ascending=False, inplace=True)

                supportTeamName = "team be10x" if supportTeamName == "" else supportTeamName

                if supportTeamName == "":
                    RecordingCondition  = ((data["Comments"].str.contains("record")) & (~data["From"].str.lower().str.contains(supportTeamName)))
                    chatDfCondition =  ((data["From"].str.lower().str.contains(supportTeamName)) | (data["From"].str.lower().str.contains("anushka")))
                else:
                    RecordingCondition  = ((data["Comments"].str.contains("record")) & (~data["From"].str.lower().str.contains(supportTeamName.lower())))
                    chatDfCondition =  (data["From"].str.lower().str.contains(supportTeamName.lower()))

                RecordingMention = data[RecordingCondition]

                chatDfCondition = data["From"].str.lower().str.contains(supportTeamName.lower(), na=False)
                chatDf = data[chatDfCondition & data["Comments"].str.contains("://", na=False)]
                chatDf = chatDf.drop_duplicates(subset="Comments").reset_index(drop=True)
                chatDf = chatDf[["Time", "Comments"]]

                ist_timezone = pytz.timezone('Asia/Kolkata')
                current_time_ist = datetime.now(pytz.utc).astimezone(ist_timezone)
                output_filename = f"meeting_saved_chat_{current_time_ist.strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"

                output_buffer = io.BytesIO()
                with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
                    if len(ChatAnalysis) > 0:
                        ChatAnalysis.to_excel(writer, sheet_name="ChatAnalysis", index=False)
                    if len(RecordingMention) > 0:
                        RecordingMention.to_excel(writer, sheet_name="RecordingMention", index=False)
                    if len(chatDf) > 0:
                        chatDf.to_excel(writer, sheet_name="Links", index=False)
                    if len(data) > 0:
                        data.to_excel(writer, sheet_name="RawChat", index=False)
                output_buffer.seek(0)

                # Persist results
                st.session_state["chat_data"] = data
                st.session_state["output_buffer"] = output_buffer
                st.session_state["output_filename"] = output_filename
                st.session_state["processed"] = True
                st.session_state["support_team"] = supportTeamName
                st.session_state["metrics"] = {
                    "total": len(data),
                    "support": len(data[data["From"].str.lower().str.contains(supportTeamName.lower(), na=False)]),
                    "recording": len(RecordingMention),
                    "links": len(chatDf),
                }

                

        except Exception as e:
            st.error('Please upload only the Zoom meeting chat file (usually named "meeting_saved_chat.txt").')

    # --- Search + DataFrame: only shown after processing, persists across re-runs ---
    # Shown only when processed flag is set (hidden on file change or before first run)
    if st.session_state.get("processed"):
        st.markdown("---")
        st.subheader("📊 Processing Summary")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Messages", st.session_state["metrics"]["total"])
        col2.metric("Support Responses Count", st.session_state["metrics"]["support"])
        col3.metric("Recording Mentions", st.session_state["metrics"]["recording"])
        col4.metric("Links Shared", st.session_state["metrics"]["links"])
        data = st.session_state["chat_data"]

        if len(data) > 0:
            st.markdown("---")
            st.markdown("**Chat Analysis Preview**")

            # active_search holds the last *submitted* search term.
            # It is wiped on file change and on Process Files, so the
            # dataframe always renders unfiltered after those two actions.
            # Typing alone does NOT filter — only pressing Enter does.
            
            st.text_input(
                    "Search by name (press Enter to filter):",
                    max_chars=25,
                    key="search_name", on_change=_submit_search
                )
            # with st.form(key="search_form", border=False):
            #     text_input, submit_button = st.columns(2)
            #     text_input = st.text_input(
            #         "Search by name (press Enter to filter):",
            #         max_chars=25,
            #         key="search_name", on_change=_submit_search
            #     )
                #submit_button = st.form_submit_button("Search", type="secondary", on_click=_submit_search)

            searchName = st.session_state.get("active_search", "")
            filtered_data = (
                data[data["From"].str.lower().str.contains(searchName.lower(), na=False)]
                if searchName.strip()
                else data
            )

            st.caption(f"{len(filtered_data)} message(s) shown")
            st.dataframe(
                filtered_data.sort_values(by=["Time"], ascending=False).reset_index(drop=True),
                use_container_width=True,
                hide_index=True
            )

    st.markdown("---")

    if "output_buffer" in st.session_state:
        st.download_button(
            label="📥 Download Excel Report",
            data=st.session_state["output_buffer"],
            file_name=st.session_state["output_filename"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )

else:
    st.info("👆 Please upload one or more chat `.txt` files to get started.")
    st.markdown("""
    **What this tool does:**
    - Parses Zoom/Webinar chat exports
    - Identifies spam.
    - Exports results into a structured Excel file with multiple sheets
    """)
