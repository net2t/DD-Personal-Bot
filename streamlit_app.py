import streamlit as st

from dashboard_utils import require_config, status_metrics, worksheet_to_df


def main() -> None:
    st.set_page_config(page_title="DD Dashboard", layout="wide")
    st.title("DD Dashboard")

    try:
        sheet_id, credentials_file = require_config()
    except Exception as e:
        st.error(str(e))
        st.stop()

    st.caption("Use the left sidebar to navigate pages: MsgList, PostQueue, InboxQueue, MsgHistory")

    sheets = ["MsgList", "PostQueue", "InboxQueue", "MsgHistory"]

    cols = st.columns(4)
    for i, name in enumerate(sheets):
        df = worksheet_to_df(sheet_id, name, credentials_file)
        m = status_metrics(df)
        with cols[i]:
            st.subheader(name)
            if m:
                st.metric("Total", m["total"])
                st.metric("Pending", m["pending"])
                st.metric("Failed", m["failed"])
            else:
                st.metric("Rows", len(df))

    st.divider()
    st.subheader("Quick exports")
    exp_cols = st.columns(4)
    for i, name in enumerate(sheets):
        df = worksheet_to_df(sheet_id, name, credentials_file)
        with exp_cols[i]:
            st.caption(name)
            st.download_button(
                label="Download CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"{name}.csv",
                mime="text/csv",
            )


if __name__ == "__main__":
    main()
