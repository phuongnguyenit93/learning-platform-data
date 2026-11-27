# Access Transparency and Access Approval

In a Google Cloud environment, an organization's data operates on infrastructure managed by Google. There are situations where Google personnel need to access customer content to handle support requests, investigate incidents, or maintain services. For systems containing sensitive data, organizations need to know when such access occurs and, in supported scenarios, have the right to review requests before access takes place.

Google Cloud provides two complementary mechanisms: **Access Transparency** logs Google personnel access to customer content; **Access Approval** lets organizations approve or deny certain access requests before Google personnel carry them out. Combining both mechanisms with IAM, Cloud Logging, and incident response workflows strengthens security teams' visibility and ability to demonstrate data control.

## 1. Access Transparency and Access Approval Answer Two Different Questions

| Mechanism | Question to Answer | How It Works |
| --- | --- | --- |
| Access Transparency | When did Google personnel access customer content, why, and for which resource? | Generates logs of access actions within supported scope; the organization queries and retains logs in Cloud Logging |
| Access Approval | Does the organization consent to Google personnel performing this access request? | Sends a request for authorized personnel to review, approve, or deny before covered access is executed |

Access Transparency focuses on visibility and auditing. Access Approval focuses on access authorization decisions. Access Approval does not replace audit logs; Access Transparency does not by itself block an access action. Deploying both enables organizations to observe activity that occurred while also gating requests covered by Access Approval beforehand.

These two mechanisms govern Google personnel accessing **customer content** during service operations. They do not replace the organization's IAM, do not govern internal employees' access to projects, and do not grant applications permission to read data. Those access flows must still be controlled with IAM, Cloud Audit Logs, and corresponding security policies.

## 2. Access Transparency Logs Access Activity

Access Transparency provides logs describing customer content access performed by Google personnel across supported Google Cloud services. Logs are delivered into Cloud Logging under the Access Transparency log type, enabling operations teams to query them, create filters, set alerts, and forward audit data to archives or a SIEM.

A log entry can provide details such as:

- **Actor identity:** Google-side employee or identity information recorded in the event.
- **Timestamp:** when the activity was recorded.
- **Affected resource:** project, service, or resource whose content was accessed.
- **Operation:** access method or operation described in the log.
- **Access reason:** context explaining why the activity was performed, such as handling a support case or operating the service.
- **Additional metadata:** operation ID, request details, or other metadata fields depending on the service and event type.

Not every action by Google personnel on every product appears in Access Transparency. Logging scope depends on the service, content type, and product eligibility conditions. Therefore, before using logs as compliance evidence, confirm the services in use are on the supported list and the organization meets the corresponding activation requirements.

### Querying Logs in Cloud Logging

In Logs Explorer, filter for Access Transparency logs using the expression:

~~~text
log_id("cloudaudit.googleapis.com/access_transparency")
~~~

To focus on a specific project, select the right project in the query scope or add appropriate resource conditions. When investigating an event, read the entire log record rather than relying on a single field. Correlate timestamps, resources, access justification, and request IDs with support tickets or internal incident records.

For example, the operations team opened a support case for a BigQuery query issue. After resolution, the security team searches Access Transparency logs in the relevant time window, identifies affected resources, and verifies whether the access justification matches the open support ticket. If the log does not match expected work scope, the security team can open an investigation and request clarification from Google or support contacts.

### Log Retention and Monitoring

Logs provide value only when protected and retained per audit requirements. Organizations should:

1. Grant log viewing permissions to security and audit teams following least privilege.
2. Configure log sinks to route logs to centralized storage or analytics systems when longer retention is needed.
3. Restrict permissions to modify sink configurations, delete logs, and access archive storage.
4. Create filters or alerts for events involving sensitive resources, unexpected access reasons, or activity outside normal operational windows.
5. Periodically verify queryability, log coverage completeness, and alert handling workflows.

Access Transparency improves traceability but does not replace incident management processes. Security teams still need defined reviewers, response SLAs, and evidence preservation procedures.

## 3. Access Approval Controls Requests Prior to Access

Access Approval lets organizations require prior approval for Google personnel accesses to customer content within supported services. When a request arises, designated approvers receive information to review and decide whether to approve or deny.

A request can provide context such as:

- Reason Google personnel need access.
- Affected resource or data scope.
- Target service and intended operation.
- Expiration or time window during which access is valid.
- Support case or related reference identifier, if applicable.

Approvers must evaluate requests against operational context and organizational policy. Approvals should be deliberate, accountable, and auditable. If a request lacks clear purpose, does not match a ticket, or exceeds agreed support scope, approvers should deny it or request clarification per procedure.

An approval decision applies only within the stated scope and conditions. Never treat a single approval as blanket permission for all future accesses. Exceptions defined for emergencies, legal obligations, or specialized operational activities may follow Google's dedicated mechanisms; read each service's terms and do not assume every scenario can be blocked via Access Approval.

## 4. Coordination Flow Between the Two Mechanisms

The diagram below illustrates a typical flow when an access request requires approval:

~~~mermaid
flowchart TD
  A["Google personnel need access to customer content"] --> B["Access Approval generates a request"]
  B --> C["Notification sent to organization's approver group"]
  C --> D{"Approver reviews request"}
  D -->|"Deny"| E["Request is denied"]
  D -->|"Approve"| F["Access permitted within request scope"]
  F --> G["Access Transparency records activity within supported scope"]
  G --> H["Cloud Logging, alerting, and auditing"]
  E --> I["Store decision and handling record"]
  H --> I
~~~

Actual flows depend on the service and request type. Access Approval handles authorization before supported accesses occur; Access Transparency provides evidence of access activity that took place. Security teams should link approval requests, decisions, and corresponding logs via request IDs, timestamps, and resources to form a complete audit trail.

## 5. Example: Protecting Customer Data in BigQuery

Suppose an e-commerce company stores order data and customer information in BigQuery. During a service issue, Google support proposes inspecting a specific dataset.

The organization can handle this as follows:

1. Support submits an access request and justification for inspecting the data.
2. Access Approval delivers the request to the designated approver group.
3. Approvers cross-check project, dataset, purpose, and incident ticket. If scope aligns, they approve; if the request is overly broad or lacks justification, they deny or ask for clarification.
4. After support work occurs, the security team retrieves Access Transparency logs in Cloud Logging.
5. Security compares the logs against the approved request, notes any discrepancies, and archives records under audit policy.

In this example, Access Approval governs Google personnel access requests; IAM and BigQuery policies continue governing internal users and application service accounts. Access Transparency supplies the audit trail for security to verify what actually occurred.

## 6. Organization-Wide Implementation

Before configuring, identify which services and data types require protection. Access Transparency and Access Approval do not share identical support coverage across all Google Cloud products. Eligibility also depends on service terms, organizational configuration, and applicable support tier or compliance program requirements. Review current documentation for each service before committing to these features in compliance controls.

An implementation workflow may include:

1. **Define scope:** list projects, services, and data types needing control; confirm services support Access Transparency and Access Approval.
2. **Verify prerequisites:** check organizational, service, regional, support tier, or compliance program requirements in current Google Cloud documentation.
3. **Enable and configure features:** configure Access Transparency across supported organization scope; enable the Access Approval API and configure enforcement scope and notifications per product guidance.
4. **Assign approvers:** designate responsible security teams, data owners, or compliance teams. Designate backups so requests are not missed when primary approvers are unavailable.
5. **Establish monitoring:** ensure logs are queryable, configure log sinks and alerts, and restrict access to audit data.
6. **Test the workflow:** use appropriate test environments or scenarios to verify notifications, approval permissions, denial handling, and log querying.
7. **Operationalize:** publish approver guidelines, response SLAs, escalation paths, and evidence storage procedures.

You can enable the Access Approval API in a project using the Google Cloud CLI:

~~~bash
gcloud services enable accessapproval.googleapis.com \
  --project=PROJECT_ID
~~~

Replace `PROJECT_ID` with the project used to configure the API. Enabling the API is only a preparatory step; the organization still must configure Access Approval at the appropriate resource scope, set up notifications, assign approver roles, and verify whether target services are supported.

## 7. Assigning Configuration and Approval Roles

Permissions to configure Access Approval and permissions to decide on a request should be clearly separated. Google Cloud provides predefined IAM roles for Access Approval:

| IAM Role | Purpose | Typical Owning Team |
| --- | --- | --- |
| **roles/accessapproval.configEditor** | Manages Access Approval configuration | Platform or security administration team |
| **roles/accessapproval.approver** | Reviews and decides on requests within granted scope | Security team, data owners, or authorized delegates |
| **roles/accessapproval.viewer** | Views configuration and request details without admin or approval rights | Audit or monitoring team |

Grant roles at the narrowest scope fulfilling the task and inspect inherited permissions from organization, folders, or projects. Configurers should be separated from approvers when compliance requires dual control. Do not grant approver permissions to every project administrator merely for notification convenience.

For Access Transparency, grant log read permissions to teams needing monitoring and auditing. Separate log viewing permissions from permissions to alter log sink configurations or delete archived data to reduce the risk that one individual can alter audit trails and review their own changes.

## 8. Criteria for Evaluating an Access Approval Request

Before approving, approvers should check:

- Does the request reference a valid support ticket or case ID?
- Does the access reason relate directly to the active incident or task?
- Are the specified project, service, and resources within the exact scope needed?
- Are the proposed operation and access duration reasonable?
- Does the request comply with data policies, contracts, and internal regulations?
- Should data owners or compliance officers be consulted before deciding?
- After the decision, who will reconcile Access Transparency logs and archive evidence?

If denying, document the reason per internal workflow and notify the support contact if appropriate. If approving, approve only the specific request after verifying full context. Never use approvals as a substitute for restricting application or internal employee access permissions.

## 9. Common Limitations and Mistakes

| Mistake | Consequence | How to Address |
| --- | --- | --- |
| Treating Access Transparency as an access-blocking control | Organization has logs but no prior control over requests | Pair Access Transparency with Access Approval and response workflows |
| Treating Access Approval as a complete audit log | Missing evidence reconciling actual activity after approval | Collect and retain Access Transparency logs alongside request records |
| Assuming every service supports both features | Actual control coverage is smaller than compliance commitments | Verify current supported service lists and applicability terms |
| Approving requests based solely on requester name | Risks approving overly broad or unjustified requests | Verify justification, ticket, resources, and duration |
| Granting approver permissions to too many people | Hard to maintain accountability and separation of duties | Limit approver group and periodically review membership |
| Failing to configure log retention or forwarding | Evidence may be unavailable during audits | Configure log sinks, retention policies, and verify retrievability |
| Ignoring exception or emergency cases | Internal workflows may misunderstand protection boundaries | Establish exception review processes and post-event log reconciliation |

## 10. Operational and Audit Checklist

Periodically, security and compliance teams should confirm:

- Have services holding sensitive data been checked for Access Transparency and Access Approval support?
- Is Access Approval configured at the right organization, folder, or project scope?
- Does the approver group have sufficient coverage, backup approvers, and periodic access reviews?
- Do request notifications reach the right recipients and get handled within internal SLAs?
- Are Access Transparency logs queryable, retained, and routed to centralized monitoring?
- Can approval or denial decisions be correlated with corresponding access logs?
- Do exceptions, emergencies, and legal requests have clear handling, documentation, and post-event audit procedures?
- Is audit evidence protected against unauthorized modification or deletion?

Access Transparency and Access Approval help organizations increase transparency and control over Google personnel access to customer content. When deployed alongside IAM, Cloud Logging, approval workflows, and evidence retention mechanisms, these two features help manage operational risk, satisfy audit requirements, and build confidence while operating on Google Cloud.
