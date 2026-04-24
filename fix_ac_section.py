"""Replace the dead-code block (lines 1954-2008) in app.py with the proper Manage Access form."""

NEW_CODE = '''                st.markdown("---")

            # ── Access Management Form ──────────────────────────────────────────────
            st.markdown("##### Manage Access")
            st.caption(
                "Select an individual user **or** a user group, choose an action, "
                "then apply to all sensitive fields or specific ones."
            )

            # Step 1 — Principal selection (mutually exclusive dropdowns)
            sel_col1, sel_col2 = st.columns(2)
            user_emails = ["— Select individual user —"] + [
                f"{u['name']} ({u['email']})" for u in ac["users"]
            ]
            group_names = ["— Select group —"] + [g["name"] for g in ac["groups"]]

            with sel_col1:
                sel_user = st.selectbox(
                    "Individual User", user_emails, key="ac_sel_user",
                    help="Select a specific user. Disables group selection."
                )
            with sel_col2:
                user_chosen = sel_user != "— Select individual user —"
                sel_group = st.selectbox(
                    "User Group", group_names, key="ac_sel_group",
                    disabled=user_chosen,
                    help="Select a group. Disabled when an individual user is selected."
                )

            group_chosen = (not user_chosen) and (sel_group != "— Select group —")
            principal_ok = user_chosen or group_chosen

            if not principal_ok:
                st.info("ℹ️ Select either an individual user or a user group above to manage access.")
            else:
                principal_label = sel_user if user_chosen else sel_group
                principal_type  = "User" if user_chosen else "Group"
                st.markdown(f"✔️ **Selected {principal_type}:** `{principal_label}`")

                # Step 2 — Action
                action_choice = st.radio(
                    "Action", ["Grant Access", "Revoke Access"],
                    horizontal=True, key="ac_action_radio"
                )

                # Step 3 — Field scope
                st.markdown("**Apply to:**")
                field_scope = st.radio(
                    "Field scope", ["All sensitive fields", "Specific fields"],
                    horizontal=True, key="ac_field_scope", label_visibility="collapsed"
                )

                target_fields = detected_sens  # default: all
                if field_scope == "Specific fields":
                    if detected_sens:
                        target_fields = st.multiselect(
                            "Select sensitive fields:", options=detected_sens,
                            key="ac_specific_fields", placeholder="Choose one or more fields..."
                        )
                        if not target_fields:
                            st.warning("Please select at least one field.")
                    else:
                        st.info("No sensitive fields detected in this dataset.")
                        target_fields = []

                # Apply button
                if st.button(
                    f"▶ Apply: {action_choice} — {field_scope}",
                    key="ac_apply_btn", type="primary", use_container_width=True
                ):
                    if not target_fields:
                        st.warning("No fields selected — nothing to apply.")
                    else:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                        grant = (action_choice == "Grant Access")
                        fields_str = ", ".join(target_fields) if target_fields else "All sensitive fields"

                        if user_chosen:
                            email_key = sel_user.split("(")[1].rstrip(")") if "(" in sel_user else ""
                            for u in ac["users"]:
                                if u["email"] == email_key:
                                    u["can_view_sensitive"] = grant
                            ac["audit_log"].insert(0, {
                                "timestamp": ts,
                                "action":    "Access Granted" if grant else "Access Revoked",
                                "principal": sel_user,
                                "type":      "User",
                                "target":    fields_str,
                                "by":        "Admin",
                            })
                        else:
                            for g in ac["groups"]:
                                if g["name"] == sel_group:
                                    g["can_view_sensitive"] = grant
                            for u in ac["users"]:
                                if u["group"] == sel_group:
                                    u["can_view_sensitive"] = grant
                            ac["audit_log"].insert(0, {
                                "timestamp": ts,
                                "action":    "Access Granted" if grant else "Access Revoked",
                                "principal": sel_group,
                                "type":      "Group",
                                "target":    fields_str,
                                "by":        "Admin",
                            })

                        verb = "granted to" if grant else "revoked from"
                        st.success(f"✅ Access {verb} **{principal_label}** for: `{fields_str}`")
                        st.rerun()

'''

with open('src/app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the start of the dead block: the leftover "new_sens = st.checkbox..." after the user table
start_marker = '                new_sens   = st.checkbox("Allow access to sensitive/PII fields", key="new_u_sens",'
end_marker   = '            else:  # New Group'

start_line = None
end_line   = None
for i, line in enumerate(lines):
    if start_marker in line and start_line is None:
        start_line = i
    if '        # \u2500\u2500 AUDIT LOG TAB' in line and end_line is None:
        end_line = i  # we'll replace up to (not including) this line

if start_line is None:
    print("ERROR: Could not find start marker")
elif end_line is None:
    print("ERROR: Could not find end marker")
else:
    print(f"Replacing lines {start_line+1} to {end_line} (Python 0-indexed: {start_line}..{end_line-1})")
    new_lines = lines[:start_line] + [NEW_CODE] + lines[end_line:]
    with open('src/app.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Done!")

    # Verify syntax
    import ast
    try:
        ast.parse(open('src/app.py', encoding='utf-8').read())
        print("SYNTAX OK")
    except SyntaxError as e:
        print(f"SYNTAX ERROR: {e}")
