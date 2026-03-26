# -*- coding: utf-8 -*-
"""
LazyBoy Chat File Formatter - Streamlit App
Converts Zoom/Webinar chat files into formatted Excel reports.
"""

import streamlit as st
import pandas as pd
import re
import pytz
import io
import os
import tempfile, openpyxl
from datetime import datetime

def formatChat(chats):
    data = pd.DataFrame(columns=["TimeStamp", "Comments"])
    for comments in chats:
        ValidComment = comments.decode("utf-8")
        if ValidComment.find("panelists:") > -1 or ValidComment.find(" Everyone:") > -1 or ValidComment.find("(direct message)") > -1:
            try:
                data.loc[len(data), "TimeStamp"] = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', ValidComment)
            except Exception as e:
                data.loc[len(data), "TimeStamp"] = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', e)
        else:
            try:
                data.loc[len(data)-1, "Comments"] = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', ValidComment)
            except Exception as e:
                data.loc[len(data)-1, "Comments"] = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', e)

    data["Time"] = data.TimeStamp.str.split(" ", n=1, expand=True)[0]
    data["Info"] = data.TimeStamp.str.split(" ", n=1, expand=True)[1]
    data["From"] = data["Info"].str.split(" to ", n=1, expand=True)[0]
    data["To"]   = data["Info"].str.split(" to ", n=1, expand=True)[1]
    data["From"] = data["From"].str.replace("From", "").str.strip()
    data["To"]   = data["To"].str.replace(":", "").str.strip()
    data["Comments"] = data["Comments"].str.strip()
    data["To"] = data["To"].apply(
        lambda x: x.replace(", Hosts and panelists", "").replace(", host and panelists", "")
        if x.find(",") > -1 else x
    )
    data = data.loc[:, ["Time", "From", "To", "Comments"]]

    return data 
    
st.set_page_config(
    page_title="LazyBoy Chat Formatter",
    page_icon="💬",
    layout="centered"
)

st.title("💬 Zoom Chat File Formatter")
st.markdown("Upload one or more webinar chat `.txt` files to generate a formatted Excel report.")

# --- File Upload ---
uploaded_files = st.file_uploader(
    "Upload Chat File(s)",
    type=["txt"],
    accept_multiple_files=True,
    help="Select one or more Zoom/Webinar chat export files (.txt)"
)

if uploaded_files:
    st.success(f"✅ {len(uploaded_files)} file(s) uploaded: {', '.join([f.name for f in uploaded_files])}")
    supportTeamName = st.text_input("Enter the support team name:", max_chars=25, \
                                    placeholder="Optional, enter the support team name to get the links shared, if any.")
    
    if st.button("🚀 Process Files", type="primary"):
        try:
            with st.spinner("Processing chat files..."):
    
                # Save uploaded files to a temp directory and read lines
                chats = []
                with tempfile.TemporaryDirectory() as tmpdir:
                    for uploaded_file in uploaded_files:
                        file_path = os.path.join(tmpdir, uploaded_file.name)
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.read())
                        with open(file_path, "rb+") as f:
                            chats.extend(f.readlines())
    
                # --- Original Logic (unchanged) ---
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
    
                if supportTeamName == "":
                        RecordingCondition  = ((data["Comments"].str.contains("record")) & (~data["From"].str.lower().str.contains("team be10x")))
                        chatDfCondition =  ((data["From"].str.lower().str.contains("team be10x")) | (data["From"].str.lower().str.contains("anushka")))
                else:
                    RecordingCondition  = ((data["Comments"].str.contains("record")) & (~data["From"].str.lower().str.contains(supportTeamName.lower())))
                    chatDfCondition =  (data["From"].str.lower().str.contains(supportTeamName.lower()))   
    
                RecordingMention = data[RecordingCondition]
    
                chatDf = data[chatDfCondition & data["Comments"].str.contains("://")]
                
                chatDf = chatDf.drop_duplicates(subset="Comments")
                chatDf.reset_index(drop=True, inplace=True)
                chatDf = chatDf[["Time", "Comments"]]
    
                # --- Generate Excel in memory ---
                ist_timezone = pytz.timezone('Asia/Kolkata')
                current_time_utc = datetime.now(pytz.utc)
                current_time_ist = current_time_utc.astimezone(ist_timezone)
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

                # --- Preview summaries ---
                st.markdown("---")
                st.subheader("📊 Processing Summary")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Messages", len(data))
                col2.metric("Unique Participants", data["From"].nunique())
                col3.metric("Recording Mentions", len(RecordingMention))
                col4.metric("Links Shared", len(chatDf))

            if len(ChatAnalysis) > 0:
                st.markdown("**Chat Analysis Preview**")
                st.dataframe(ChatAnalysis.head(10).reset_index(drop=True), use_container_width=True)
    
            st.markdown("---")
    
            # --- Download Button ---
            st.download_button(
                label="📥 Download Excel Report",
                data=output_buffer,
                file_name=output_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            
       except:
            print("Please upload only the Zoom meeting chat file (usually named “meeting_saved_chat.txt”).")
else:
    st.info("👆 Please upload one or more chat `.txt` files to get started.")
    st.markdown("""
    **What this tool does:**
    - Parses Zoom/Webinar chat exports
    - Identifies spam.
    - Exports results into a structured Excel file with multiple sheets
    """)
