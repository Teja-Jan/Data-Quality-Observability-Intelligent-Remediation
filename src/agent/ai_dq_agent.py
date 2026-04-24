import json
from dataclasses import dataclass

@dataclass
class ChatMessage:
    role: str
    content: str

class AIDQAgent:
    """
    Autonomous AI Assistant for the DQ Framework.
    Manages the full lifecycle of detection, reasoning, and deterministic execution of fixes.
    """
    def __init__(self, endpoint="http://localhost:11434/v1"):
        self.endpoint = endpoint
        self.history = []

    def get_initial_greeting(self, domain, total_issues):
        msg = f"Hello! I am your Autonomous Data Quality Agent. I've successfully connected to your {domain.title()} ecosystem and discovered {total_issues} operational issues. I'm ready to manage the complete lifecycle of detection, analysis, and resolution for you. How can I help?"
        self.history.append(ChatMessage(role="assistant", content=msg))
        return msg

    def chat(self, user_message, results_context, cleaned_df=None):
        """
        Process the user message and return a response based on deterministic DQ results context.
        """
        self.history.append(ChatMessage(role="user", content=user_message))
        
        user_lower = user_message.lower()
        response = ""
        action = None
        action_payload = None

        if any(w in user_lower for w in ["fix", "remediate", "resolve"]) and any(w in user_lower for w in ["minor", "low", "all", "auto"]):
            if "specific" in user_lower or "select" in user_lower:
                response = "You can manually select specific issues to fix using the checkboxes provided in the Diagnostic Inspection tab."
                action = "DRILL_DOWN"
            elif any(w in user_lower for w in ["minor", "low", "all", "auto"]):
                response = "I will now trigger the autonomous remediation process for all minor (low-risk) issues."
                action = "APPLY_AUTO_FIX"
            else:
                response = "Are you asking me to fix all minor issues, or did you want to fix specific selected issues?"
            
        elif any(w in user_lower for w in ["approve", "send for approval", "major", "high-risk", "executive"]):
            response = "I will prepare the Major Issues manifest and escalate it for executive approval."
            action = "SEND_APPROVAL"
            
        elif any(w in user_lower for w in ["report", "export", "pdf", "excel", "download"]):
            fmt = "PDF Dashboard" if "pdf" in user_lower else "Excel Data Quality Manifest"
            response = f"I am initiating the generation of the {fmt}. Check the Reports tab for your download."
            action = "GENERATE_REPORT"
            action_payload = {"format": "pdf" if "pdf" in user_lower else "excel"}

        elif any(w in user_lower for w in ["grant", "revoke", "access", "permit"]):
            # Access Control logic
            mode = "GRANT" if any(w in user_lower for w in ["grant", "enable", "permit", "give"]) else "REVOKE"
            target_type = "GROUP" if "group" in user_lower or "team" in user_lower else "USER"
            
            # Simple named extraction (mock for demo parsing)
            target_name = None
            for p in ["alice", "bob", "carol", "john", "doe", "vendor", "devops"]:
                if p in user_lower:
                    target_name = p
                    break
            if not target_name:
                for g in ["engineering", "analytics", "compliance", "marketing", "contractors"]:
                    if g in user_lower:
                        target_name = g
                        target_type = "GROUP"
                        break
            
            if target_name:
                response = f"I am executing a {mode} operation for {target_type} '{target_name.title()}'. The Security Observability registry will be updated immediately."
                action = f"{mode}_{target_type}_ACCESS"
                action_payload = {"name": target_name}
            else:
                response = "I can manage access for users (Alice, Bob, Carol, John) or groups (Engineering, Analytics, Compliance, Marketing). Who would you like to update?"

        elif "explain" in user_lower or "what" in user_lower or "pattern" in user_lower:
            if "diagnosis pattern" in user_lower or "high success rate" in user_lower or "new pattern" in user_lower:
                response = "Diagnosis Patterns inform auto-fix reliability based on historical context. 'High Success Rate' means this exact anomaly was detected and successfully auto-fixed with management approval multiple times in the past. 'New Pattern' means the system has high confidence in a syntactic fix, but lacks long-term historical confirmation. I recommend reviewing New Patterns manually before executing."
            elif "recommendation" in user_lower and "access" in user_lower:
                response = "Access recommendations are based on role-based security policies. For example, Marketing roles are recommended for revocation if they have access to sensitive PII like SSNs, while Compliance roles are recommended for granting access to fulfill audit requirements."
            else:
                critical_dims = [dim for dim, res in results_context.items() if res and res.score < 70]
                if critical_dims:
                    response = f"The most critical areas are {', '.join([d.replace('_', ' ').title() for d in critical_dims])}. You should focus on fixing issues there first before dealing with low-risk standards."
                else:
                    response = "Currently, there are no critical dimensions (score < 70). The dataset is in relatively good health!"
                
        elif "summarize" in user_lower:
            issue_count = sum([res.issues_found for dim, res in results_context.items() if res])
            response = f"There are {issue_count} total issues spread out across {len([res for res in results_context.values() if res and res.issues_found > 0])} dimensions. You can use the checkboxes in Diagnostic Inspection to remediate problems systematically."
        
        else:
            response = "I function as an autonomous agent. You can ask me to 'summarize', 'connect to Finance', 'export PDF', 'fix minor issues', or even 'Revoke access for John Doe'."

        self.history.append(ChatMessage(role="assistant", content=response))
        
        return {
            "response": response,
            "action": action,
            "action_payload": action_payload
        }
