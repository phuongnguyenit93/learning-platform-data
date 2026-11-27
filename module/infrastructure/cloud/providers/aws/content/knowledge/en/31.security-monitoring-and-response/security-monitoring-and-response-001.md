# Amazon GuardDuty and Anomaly Detection

An AWS account can generate millions of activity events every day: users signing in, roles being assumed, APIs being called, servers connecting to the Internet, containers launching processes, and applications accessing data. Security teams can hardly read every single log to detect a stolen credential, a remotely controlled server, or a bucket being accessed abnormally. They need a service that continuously analyzes signals, identifies suspicious behavioral patterns, and produces contextualized alerts for investigation.

**Amazon GuardDuty** is AWS's managed threat detection service. It analyzes data sources such as CloudTrail events, VPC Flow Logs, DNS logs, and enabled protection telemetry to identify activity indicating compromise or abuse. GuardDuty uses threat intelligence, detection rules, and machine learning to generate findings when it detects suspicious behavior.

Within the **CLOUD_PROVIDERS_AWS** ecosystem, GuardDuty helps protect accounts, workloads, data, and container environments across multiple Regions. Learners need to understand how to enable the service, read findings, distinguish severity levels, configure multi-account organizations, integrate with EventBridge, and build response workflows. GuardDuty assists with detection; operations teams still must verify, contain, remediate, and preserve evidence to maintain a secure, resilient, and cost-controlled system.

## 1. What Problems Does GuardDuty Solve?

GuardDuty analyzes activity in an AWS environment to look for signs that may relate to:

- Compromised or abnormally used credentials.
- API calls showing signs of being executed by an attacker.
- EC2 instances communicating with IP addresses or domains associated with malicious activity.
- Servers being scanned, exploited, or remotely controlled.
- S3 buckets being accessed in suspicious patterns or at risk of data exposure.
- Containers or Kubernetes workloads exhibiting anomalous behavior.
- Activity related to malware or suspicious processes on supported workloads.
- Signs of compromise or unusual access to certain GuardDuty-supported data services.

GuardDuty generates a **finding** to describe the detected behavior, affected resources, timestamp, severity level, and supporting details. A finding is an investigative signal. It neither proves on its own that a system has been successfully compromised nor fully determines the blast radius.

GuardDuty can help detect behaviors that are hard to spot in raw logs alone. For example, an IAM user that normally operates only in one Region suddenly calls administrative APIs from an unfamiliar IP address; an EC2 instance begins connecting to a domain associated with command-and-control; or a principal reads S3 data in an unusual pattern. The service aggregates signals and delivers findings so security teams can prioritize investigations.

GuardDuty does not replace:

- CloudTrail, VPC Flow Logs, or CloudWatch Logs as log sources for detailed investigation.
- IAM, SCPs, security groups, network firewalls, or preventive control mechanisms.
- Amazon Inspector, vulnerability scanning tools, and patching processes.
- Security Hub, which aggregates and manages posture and findings across multiple security services.
- Incident response processes, on-call responders, and business decisions.

GuardDuty is a detection layer within a defense-in-depth architecture. To reduce risk, organizations must combine detection, prevention, monitoring, investigation, and recovery.

## 2. How GuardDuty Analyzes Signals

GuardDuty creates a detector in each account and Region. A detector is the entity that manages detection in that Region. When GuardDuty is enabled, the service uses supported foundational data sources to analyze activity. Some protection plans may need to be enabled separately to expand protection coverage.

### Foundational Data Sources

| Data Source | Signals Analyzed | Detection Examples |
|---|---|---|
| CloudTrail management events | AWS administrative operations such as creating users, modifying policies, and changing service configurations | Suspicious API calls, abnormally used credentials |
| VPC Flow Logs | Inbound/outbound VPC network flow metadata | Connections to malicious IPs, scanning activity, or unusual communication |
| DNS query logs | DNS queries from supported workloads | Queries to domains associated with malware or command-and-control |
| AWS threat intelligence feeds | IPs, domains, or infrastructure patterns identified as suspicious | Connections to threat-related infrastructure |
| Protection plan telemetry | Additional data from S3, EKS, runtime, malware, or supported services | Unusual data access, process behavior, or malware |

GuardDuty manages the analysis of foundational data sources; customers do not have to build their own pipelines to feed CloudTrail management events, VPC Flow Logs, and DNS logs into a separate analytics system just to enable GuardDuty. However, customers still need to configure independent logging when they want to store, query, and investigate raw logs according to organizational policy.

Some telemetry types and protection plans may depend on configuration, operating system, Region, or resource type. Do not assume that enabling the default detector means all extended features are already enabled.

### High-Level Workflow

~~~mermaid
flowchart TD
    A[Account and workload activity] --> B[CloudTrail, VPC Flow Logs, DNS, and telemetry]
    B --> C[GuardDuty analyzes signals]
    C --> D{Suspicious behavior detected?}
    D -->|No| E[Continue monitoring]
    D -->|Yes| F[Generate finding]
    F --> G[EventBridge and Security Hub]
    G --> H[Security team triages and investigates]
    H --> I[Contain, remediate, and preserve evidence]
~~~

## 3. Finding Categories and Their Meaning

Each finding has a type describing the detection category. Type names typically follow a hierarchical structure by service or resource, such as UnauthorizedAccess, Recon, Backdoor, CryptoCurrency, or Policy. The list of types and specific details change with GuardDuty features and are updated by AWS over time.

| Detection Category | General Meaning | Initial Investigative Actions |
|---|---|---|
| UnauthorizedAccess | Signs of unauthorized access or credential abuse | Check principal, source IP, API events, MFA, and IAM changes |
| Recon | Signs of scanning or information gathering | Identify scanned resources, connection sources, and network scope |
| Backdoor | Signs of communication with command-and-control or backdoor infrastructure | Isolate the workload as appropriate, preserve network and process evidence |
| CryptoCurrency | Workload may be performing cryptocurrency mining | Check CPU, processes, image, user data, and network connections |
| Trojan or malware-related | Signals related to malware or malicious behavior | Preserve snapshots/logs, identify download source and spread scope |
| Persistence | Signs of establishing mechanisms to maintain access | Review IAM, startup scripts, scheduled tasks, and configuration changes |
| Policy | Policy configuration or behavior that may increase risk | Check bucket policy, IAM policy, security groups, or related configuration |
| Exfiltration | Signs of unusual data retrieval or outbound transfer | Identify data, principal, destination, and access timestamp |
| Impact | Signs of impact on availability or integrity | Assess affected services, resources, and business impact |

A finding can belong to different contexts depending on the resource. When reading a finding, do not rely solely on the type name; inspect the description, resource, service action, evidence, timestamp, account, Region, and additional fields.

## 4. Severity and Prioritization

GuardDuty assigns a severity level to findings to support prioritization. The severity level is a signal of the risk a finding represents; organizations need to combine it with asset context, environment, and business impact.

| Level | Reference Score Range | Handling Approach |
|---|---:|---|
| Low | 1.0 to 3.9 | Review on schedule, determine whether activity is approved or requires monitoring |
| Medium | 4.0 to 6.9 | Investigate promptly, determine scope, and decide on action |
| High | 7.0 to 8.9 | Prioritize response, check for compromise, and contain if necessary |

GuardDuty uses three primary severity levels: Low, Medium, and High. If an internal SIEM/SOAR system maps an additional Critical label, that is an organizational prioritization convention, not a fourth native GuardDuty severity level.

Severity is not an exact probability that a system has been compromised. For example, a High finding involving a production account with administrative privileges may require immediate action; a finding with the same score in an isolated sandbox may have lower impact. Conversely, a Medium finding involving specially classified data may warrant high priority under internal policy.

Build a prioritization matrix based on:

- Finding severity.
- Value and sensitivity of the resource.
- Environment: production, staging, or sandbox.
- Permissions of the associated principal or role.
- Likelihood of data being accessed or exfiltrated.
- Corroborating signals from CloudTrail, VPC Flow Logs, EDR, and other security services.
- Business operational status and blast radius.

## 5. Reading a Finding Properly

A GuardDuty finding contains many fields useful for investigation and automation. Fields to pay attention to include:

| Field | Meaning |
|---|---|
| id | Finding identifier |
| type | Detection type |
| title and description | Summary and explanation of the behavior |
| severity | Severity score |
| accountId | Account where the finding originated |
| region | Associated Region |
| createdAt / updatedAt | Creation and update timestamps |
| resource | Affected or associated resource |
| service | Detecting service details, action, and evidence |
| schemaVersion | Finding schema version |
| partition | Associated AWS partition |

The resource field can contain different details depending on the finding type. For EC2, inspect the instance ID, image, instance type, network interface, security group, subnet, VPC, and tags. For IAM, check the access key, user/role, principal ID, session context, and source IP. For S3, look at the bucket, object, or principal described in the finding. For EKS, inspect the cluster, namespace, workload, pod, and runtime details if available.

### Triage Process

1. Confirm which account and Region the finding belongs to.
2. Review type, severity, title, description, and timestamp.
3. Identify the associated principal or resource.
4. Correlate with CloudTrail, VPC Flow Logs, DNS logs, and application logs over the same timeframe.
5. Check recent changes: deployments, scaling, scheduled jobs, approved penetration tests, or network changes.
6. Determine whether the activity is legitimate, a false positive, requires monitoring, or indicates compromise.
7. Document conclusions, evidence, assignee, and next steps.

Do not archive a finding simply because you do not yet understand its cause. If noise reduction is needed, create a suppression rule with narrow conditions, an owner, and a review expiration date.

## 6. Enabling GuardDuty in an Account and Region

GuardDuty maintains a separate detector per Region. An organization operating across multiple Regions must enable and manage detectors in all Regions within scope. Enabling it in one Region does not automatically enable detectors in other Regions.

Example of creating a detector and enabling GuardDuty using the AWS CLI:

~~~bash
aws guardduty create-detector \
  --enable \
  --finding-publishing-frequency FIFTEEN_MINUTES
~~~

The command returns a detector ID. You can check existing detectors:

~~~bash
aws guardduty list-detectors
~~~

Once you have the detector ID, retrieve findings by criteria:

~~~bash
aws guardduty list-findings \
  --detector-id "DETECTOR_ID" \
  --finding-criteria '{"Criterion":{"severity":{"Gte":7}}}'
~~~

Then retrieve finding details:

~~~bash
aws guardduty get-findings \
  --detector-id "DETECTOR_ID" \
  --finding-ids "FINDING_ID"
~~~

These examples use placeholder values for detector and finding IDs. Commands must be run in the right account and Region; the caller needs corresponding GuardDuty permissions. In practice, store detector IDs per Region and do not hardcode IDs in pipelines shared across multiple accounts.

## 7. Managing Multi-Account GuardDuty with AWS Organizations

In a multi-account environment, enabling and maintaining GuardDuty manually on each account easily leads to inconsistent configurations. GuardDuty supports centralized management through AWS Organizations.

An account can be designated as the **delegated administrator** for GuardDuty. This account manages member accounts within the organization scope, enables GuardDuty and protection plans according to policy, monitors status, and centralizes findings. The management account can register the delegated administrator; use a dedicated security account rather than using the management account for day-to-day operations.

Reference model:

~~~mermaid
flowchart TD
    A[AWS Organizations Management Account] --> B[Register GuardDuty delegated administrator]
    B --> C[Security Tooling Account]
    C --> D[Member Account Development]
    C --> E[Member Account Staging]
    C --> F[Member Account Production]
    D --> G[GuardDuty detectors per Region]
    E --> G
    F --> G
    G --> H[Centralized findings]
    H --> I[Security Hub / EventBridge / SIEM]
~~~

Administrative steps:

1. Choose a security account as the delegated administrator.
2. Register the delegated administrator for GuardDuty from the management account.
3. Enable automatic member account addition or invite accounts per the organizational model.
4. Select the Regions and protection plans to enable.
5. Configure auto-enable for existing and new accounts as required.
6. Verify that each member account has an active detector and synchronized status.
7. Verify centralized findings and operator access permissions.

GuardDuty is a Regional service. The delegated administrator needs appropriate configuration in every Region in use. New accounts joining the organization or accounts moving between OUs must be checked under onboarding and offboarding policies.

## 8. Protection Plans Expanding Detection Scope

Beyond foundational data sources, GuardDuty offers protection plans to expand monitoring. Names, scope, and support conditions may change; verify the actual configuration in your Region.

### 8.1. S3 Protection

S3 Protection analyzes supported S3 data events to identify unusual or potentially malicious access behavior. For example, a principal accessing objects atypically or showing signs of bulk data collection.

S3 Protection focuses on behavioral detection. It does not replace bucket policies, Block Public Access, IAM, access point policies, encryption, or data classification processes. To prevent unauthorized access, preventive controls and access permissions monitoring are still required.

### 8.2. EKS Protection and Runtime Monitoring

EKS Protection can analyze Kubernetes audit logs to detect unusual control-plane behavior, such as suspicious API requests, permission changes, or cluster-related activity.

Runtime Monitoring extends behavioral monitoring of supported workloads at runtime, including processes, network, and OS/container-level activity. Depending on the environment, GuardDuty may require deploying or managing a security agent on nodes. Check OS requirements, architecture, versions, and agent management methods in the cluster.

Kubernetes audit findings and runtime findings reflect two different layers: one observes API/control-plane actions, while the other observes behavior inside workloads. Combining them helps investigate both cluster administration operations and activity inside nodes/containers.

### 8.3. Malware Protection for EC2

Malware Protection for EC2 supports scanning EC2 EBS volumes for malware under AWS-supported conditions and triggers. Scanning may create snapshots for analysis. Understand the snapshot mechanism, service-linked role permissions, volume encryption, key policies, snapshot costs, and data protection requirements.

Malware-related findings should be handled as security incidents: verify the workload, preserve evidence, isolate when appropriate, and evaluate whether to rebuild from a clean image. Do not delete snapshots or volumes before the response team completes the investigation.

### 8.4. Malware Protection for S3

Malware Protection for S3 scans objects uploaded to protected buckets according to the configured scope. Organizations can use scan results to integrate with object moderation workflows, quarantine data, or trigger notifications. Verify buckets, prefixes, roles, object access permissions, KMS keys, and how unscanned files are handled.

Downstream applications should not process untrusted files before scanning and acceptance workflows complete. Malware scanning does not replace format validation, content controls, and business validation.

### 8.5. RDS Protection and Supported Data Sources

GuardDuty can provide detections related to login activity or unusual behavior on certain supported database services. This capability depends on database type, Region, configuration, and active protection plans. Do not assume every engine or account is automatically protected.

### 8.6. Lambda Protection

Lambda Protection analyzes signals related to network activity from supported Lambda execution environments to identify suspicious behavior, such as a function connecting to domains or IP addresses linked to threats. Evaluate cost impact and function scope before enabling this protection plan.

## 9. Anomaly Detection Using Machine Learning

Not all attacks use IPs or domains already listed in threat intelligence. Attackers may use valid credentials, access from normal infrastructure, or alter behavior in ways that do not match known signatures. Therefore, GuardDuty combines behavioral analysis and machine learning to find patterns that deviate from typical activity.

Examples of anomalous signals:

- An IAM principal calls an API it has never used before or uses it in an unusual context.
- Credentials are used from a location, ASN, device, or source IP differing from historical patterns.
- An instance begins sending unusual network traffic volume or connecting to unusual destinations.
- A workload accesses sensitive resources in a pattern not seen before.
- A role executes a sequence of operations potentially linked to privilege escalation or persistence.

Behavior-based detection can help identify attack techniques without specific indicators. However, baselines are not immutable rules. A new deployment, autoscaling, batch jobs, backups, or security testing activities can legitimately alter normal behavior.

### Baselines and Context

GuardDuty analyzes data according to the service's implementation; customers do not need to manually build baselines for each principal to enable detection. Still, security teams must supply internal context:

- Workload owner and purpose.
- Deployment, backup, batch, and maintenance schedules.
- Legitimate source IPs, VPNs, NAT gateways, and administrative access systems.
- IAM roles, expected permissions, and data scope.
- Production resources and sensitivity levels.
- Dates/times of approved penetration tests or red team exercises.

If a finding matches legitimate activity, record the evidence and evaluate whether a suppression rule is appropriate. Avoid overly broad allowlists, as they can mask genuine compromise behavior.

## 10. Integrating GuardDuty with EventBridge

GuardDuty emits finding events to Amazon EventBridge. EventBridge enables routing findings to SNS, Lambda, SQS, Step Functions, Systems Manager Automation, Security Hub, or SIEM/SOAR systems.

A finding event typically has:

- source as aws.guardduty.
- detail-type as GuardDuty Finding.
- detail containing finding ID, type, severity, account, Region, resource, and other fields.

Example event pattern selecting only findings with severity 7 or higher:

~~~json
{
  "source": ["aws.guardduty"],
  "detail-type": ["GuardDuty Finding"],
  "detail": {
    "severity": [{"numeric": [">=", 7]}]
  }
}
~~~

This pattern only illustrates filtering by severity. During implementation, verify the actual event schema, finding types, resource fields, and conditions for each workflow.

A rule can send High findings to SQS for sequential processing, notify on-call teams, or invoke Lambda to enrich with tags and owner details. For resource isolation actions, include condition checks and approval steps proportional to the risk level.

### Safe Workflow Design

~~~mermaid
flowchart LR
    A[GuardDuty Finding] --> B[EventBridge Rule]
    B --> C[Enrichment Lambda]
    C --> D[SQS Incident Queue]
    D --> E[SOAR / Security Team]
    E --> F{Automated action needed?}
    F -->|Yes, approved| G[SSM Automation / Lambda]
    F -->|Needs verification| H[Analyst investigates]
    G --> I[Verify outcome and store audit]
    H --> I
~~~

EventBridge delivery and target invocation may be retried. Workflows require idempotency so a single finding does not trigger multiple service-disrupting actions. Store the finding ID or correlation key in the incident system to recognize duplicate events and update existing cases.

## 11. Suppression Rules and False Positive Management

Not every finding requires opening an incident. Some findings may recur due to approved operations or a test environment. GuardDuty supports filters and suppression rules to reduce noise.

A suppression rule should have:

- Clear conditions based on type, resource, severity, or specific attributes.
- An owner and business justification.
- Narrow account/Region/resource scope.
- An expiration date or review schedule.
- A way to verify the rule does not hide meaningful new findings.

You can archive a specific finding after investigation, or use a filter rule to automatically archive findings matching criteria. Archiving does not delete original evidence from all related systems and does not mean the issue has been remediated.

Do not suppress all Low findings or all findings from a subnet simply because alerts are noisy. An attacker may use that very subnet or a legitimate workload as a pivot point. It is better to pinpoint the exact approved activity, principal, process, or destination.

## 12. Responding to Findings: From Triage to Recovery

Response procedures should be prepared before an incident occurs. When a High or Critical finding appears, the on-call team should execute the approved playbook.

### Step 1: Receive and Confirm

Record the finding ID, type, severity, account, Region, resource, timestamp, and detection source. Verify the finding is not already being handled in another incident. Assess whether the activity coincides with a deployment, penetration test, or approved change.

### Step 2: Expand the Investigation

Correlate with CloudTrail management/data events, VPC Flow Logs, DNS logs, application logs, EDR, IAM Access Analyzer, Security Hub, and related findings. Identify the principal, source IP, session, resource, and timeframe. Look for signs of persistence, privilege escalation, lateral movement, or data exfiltration.

### Step 3: Preserve Evidence

Save the finding JSON, CloudTrail events, related logs, IAM and network configurations, resource metadata, and collection timestamps. For EC2, create EBS snapshots per the forensic procedure before modifying or terminating the instance. Protect snapshots and logs with IAM, KMS, retention policies, and restricted access.

### Step 4: Containment

Actions depend on the resource and confidence level:

- For IAM credentials: disable access keys, revoke sessions, or update policies under emergency procedures; review role trust policies and user access.
- For EC2: apply an isolating security group or move to a quarantine subnet per architecture; keep necessary forensic management paths.
- For S3: block suspicious principals or access paths, review bucket policies, access points, and object ACLs if still in use.
- For EKS/containers: isolate workloads or nodes per playbook, inspect service accounts, RBAC, and images.
- For Lambda: consider disabling triggers or restricting execution role permissions if the function shows signs of abuse.

Do not apply a single automated action to every finding. Accidentally isolating a database, load balancer, or control-plane node can cause a larger outage than the incident itself.

### Step 5: Eradication and Recovery

Remove persistence mechanisms, rotate credentials, fix IAM/network policies, update images, or rebuild workloads from trusted sources. If a host cannot be proven clean, prefer recreating it from a verified image or artifact rather than only deleting suspicious files.

### Step 6: Verification and Incident Closure

Monitor for new GuardDuty findings, CloudTrail activity, network telemetry, health checks, and business operations. Document blast radius, root cause, actions taken, evidence, approvers, and lessons learned. Do not close an incident merely because the finding has been archived.

## 13. Example: Abused IAM Credential Finding

Suppose GuardDuty generates a finding involving an IAM access key used from an unfamiliar IP address to call administrative APIs. The security team needs to determine whether this is legitimate automation.

Reference workflow:

1. Retrieve the finding and identify the access key ID, principal, source IP, Region, API action, and timestamp.
2. Search CloudTrail events by access key ID around the finding timestamp.
3. Check the user/role owner, last known legitimate usage, and whether any CI/CD system uses this key.
4. Look for subsequent changes such as CreateAccessKey, AttachUserPolicy, PutRolePolicy, CreateLoginProfile, or trust policy updates.
5. Inspect newly created resources, accessed data, and related accounts/Regions.
6. If credential compromise is suspected, disable the key and revoke sessions as appropriate; issue new credentials through secure processes.
7. Review workloads using keys, migrating to IAM roles or federation to reduce reliance on long-lived access keys.
8. Monitor subsequent findings and verify no abnormal activity remains.

Response diagram:

~~~mermaid
flowchart TD
    A[Unusual IAM credential finding] --> B[Correlate with CloudTrail]
    B --> C{Approved activity?}
    C -->|Yes| D[Record evidence and evaluate suppression]
    C -->|No / unclear| E[Assess compromise severity]
    E --> F[Disable key or revoke session]
    F --> G[Check IAM and resource changes]
    G --> H[Remediate, rotate credentials, remove persistence]
    H --> I[Monitor and confirm clean]
    D --> J[Close or monitor incident]
    I --> J
~~~

Disabling credentials can impact running workloads. If evidence is insufficient, coordinate with the owner to rotate credentials safely; if active attack behavior is underway, prioritize containment per the emergency playbook.

## 14. Integrating Security Hub, Detective, and Other Services

GuardDuty is one detection source. To manage diverse alert types, organizations can integrate:

| Service | Role When Coordinating with GuardDuty |
|---|---|
| AWS Security Hub | Centralizes security findings, standardizes and prioritizes by posture |
| Amazon Detective | Explores relationships between findings, principals, IPs, instances, and activity to aid investigation |
| Amazon EventBridge | Routes findings to workflows, queues, Lambda, or external systems |
| Amazon SNS | Sends notifications to on-call teams or alerting systems |
| AWS Systems Manager Automation | Executes response runbooks under approved conditions and permissions |
| AWS CloudTrail | Queries API activity and administrative changes to determine actual actions |
| Amazon CloudWatch | Tracks workflow status, metrics, and automation logs |
| AWS Organizations | Manages detectors and protection plans across multiple accounts |
| SIEM/SOAR | Correlates findings with logs and incidents from other systems |

Security Hub aggregates posture and findings; Detective helps analyze relationships; EventBridge delivers findings to response systems. Avoid building multiple pipelines that send the same finding to multiple systems without a correlation identifier, as this can create duplicate incidents and conflicting actions.

## 15. Securing GuardDuty Administrative Permissions

GuardDuty uses a service-linked role to perform required service tasks. Administrators need permissions to enable/disable detectors, manage member accounts, protection plans, finding filters, and exports/integrations within their assigned scope.

Reference permissions model:

| Role | Appropriate Permissions |
|---|---|
| Security administrator | Manage detectors, delegated admin, protection plans, and organization-wide configuration |
| Incident responder | Read findings, view resources, and run approved response actions |
| Workload owner | View findings related to their account/application and provide context |
| Auditor | Read findings, policies, configurations, and evidence; no permission to disable the service |
| Automation role | Run only specific actions such as isolating instances or disabling keys per playbook |

Do not grant permissions to disable GuardDuty or modify broad suppression rules to all developers. Such actions can remove detection capability or hide abnormal activity. Use CloudTrail to monitor changes to detector configurations, member accounts, protection plans, and filters.

## 16. Cost and Performance

GuardDuty charges based on data sources and enabled protection plans. Pricing may be based on CloudTrail event volume, analyzed VPC Flow Logs/DNS data volume, number of protected workloads or objects, and feature-specific factors. Rates vary by Region and are subject to change.

To control costs:

1. Enable protection plans based on risk requirements and resource scope.
2. Monitor usage and estimated costs by account/Region.
3. Categorize workloads, accounts, and Regions to see where costs originate.
4. Evaluate S3, EKS, Runtime, Malware, and Lambda protection against actual needs.
5. Integrate billing alerts and AWS Cost Explorer.
6. Include GuardDuty in new account onboarding baselines to avoid late enablement or missing configurations.
7. Do not disable detectors purely to cut costs without a risk assessment and formal approval.

GuardDuty is a managed service, yet detector health, coverage, member accounts, protection plans, and response workflows still require monitoring. An enabled detector that fails to cover required accounts/Regions still leaves security gaps.

## 17. Testing and Validating GuardDuty Operations

Do not simulate real attacks in production to test GuardDuty. AWS provides a way to generate sample findings in GuardDuty to test visibility pipelines, EventBridge, Security Hub, and incident systems.

Example of generating sample findings:

~~~bash
aws guardduty create-sample-findings \
  --detector-id "DETECTOR_ID"
~~~

Sample findings test the processing pipeline and are typically marked as samples. They do not confirm that every telemetry source, protection plan, or detection model is functioning properly. Separately verify detector status, feature configuration, member accounts, and event delivery.

Testing checklist:

- Detector is Enabled in every Region in scope.
- Member accounts are managed and synchronized properly.
- Required protection plans are enabled.
- Sample findings appear in the console/API.
- EventBridge rules match events with the expected pattern.
- Targets process events successfully without creating duplicate incidents.
- Responder/automation permissions work properly.
- Suppression rules do not hide sample or critical findings.
- Logs and evidence are stored in locations with restricted access.
- Procedures exist for handling EventBridge target failures or unresponsive workflows.

## 18. Common Implementation Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No findings seen in a Region | Detector not enabled or viewing the wrong Region | Check list-detectors and account/Region |
| New account has no detector | Auto-enable or delegated admin not properly configured | Check AWS Organizations integration and member status |
| No S3 findings | S3 Protection not enabled or bucket out of scope | Check feature status, bucket, and Region |
| No runtime findings from EKS/EC2 | Runtime Monitoring not enabled or agent/OS requirements not met | Check coverage and agent status |
| EventBridge does not receive findings | Wrong event pattern, rule in wrong Region, or target policy lacks permissions | Check event history, rule, target, and IAM |
| Findings archived too early | Suppression/filter rule too broad | Review criteria, owner, and rule history |
| Too many alerts | Missing context, poorly tuned rules, or workflow lacks deduplication | Enrich findings, group by resource and incident key |
| Cannot read findings via CLI | Missing IAM permissions or wrong detector ID | Check role, policy, Region, and detector |
| Automation fails to isolate EC2 | Role lacks permissions, resource changed state, or action is not idempotent | Inspect execution logs, check preconditions and permissions |
| Findings do not reflect full incident | GuardDuty detects only partial signals and has latency | Correlate with CloudTrail, logs, EDR, and business data |

## 19. GuardDuty Operational Checklist

- [ ] GuardDuty is enabled across all accounts and Regions requiring protection.
- [ ] Delegated administrator and AWS Organizations integration are configured.
- [ ] Auto-enable for new accounts has been verified.
- [ ] Protection plans appropriate for EC2, S3, EKS, RDS, Lambda, and workloads requiring protection have been evaluated.
- [ ] Detector and feature coverage are monitored periodically.
- [ ] Findings are routed via EventBridge to on-call teams or SIEM/SOAR systems.
- [ ] Workflows implement deduplication and idempotency.
- [ ] Severity is combined with resource criticality and owner context.
- [ ] Suppression rules have narrow criteria, justification, and review dates.
- [ ] Playbooks exist for IAM credentials, EC2, S3, EKS, and malware.
- [ ] Logs and evidence snapshots are protected via IAM/KMS/retention.
- [ ] Automation includes preconditions, appropriate approvals, and rollback capability.
- [ ] CloudTrail records changes to GuardDuty configuration.
- [ ] Costs per Region/account are tracked.
- [ ] Sample findings are used to periodically test pipelines.

## 20. Takeaways

Amazon GuardDuty analyzes signals from account, network, DNS activity, and protection plans to detect signs of compromise or anomalous behavior. Detectors are managed per Region; AWS Organizations and delegated administrators simplify multi-account management. Findings describe the detection type, severity, resource, and evidence for security teams to triage.

Automated detection must be paired with internal context and raw log sources. EventBridge routes findings to Security Hub, Detective, SQS, Lambda, Systems Manager Automation, or SIEM/SOAR. Response workflows must verify, preserve evidence, contain, eradicate causes, and confirm the system is clean.

GuardDuty produces valuable detection signals; protection quality depends on coverage, administrative permissions, finding prioritization, and organizational response capability. Maintain detectors across all necessary accounts/Regions, review protection plans, control noise carefully, and rehearse incident response to detect early, respond accurately, and recover safely.

## References

- [What is Amazon GuardDuty?](https://docs.aws.amazon.com/guardduty/latest/ug/what-is-guardduty.html)
- [How Amazon GuardDuty Uses Its Data Sources](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_data-sources.html)
- [Understanding GuardDuty Findings](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings.html)
- [Finding Severity Levels](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings-severity.html)
- [Managing GuardDuty Accounts with AWS Organizations](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_organizations.html)
- [Managing GuardDuty Findings](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings-manage.html)
- [Filtering and Suppressing Findings](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_filter-findings.html)
- [GuardDuty Findings and Amazon EventBridge](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty_findings_eventbridge.html)
- [GuardDuty S3 Protection](https://docs.aws.amazon.com/guardduty/latest/ug/s3-protection.html)
- [GuardDuty EKS Protection](https://docs.aws.amazon.com/guardduty/latest/ug/kubernetes-protection.html)
- [GuardDuty Runtime Monitoring](https://docs.aws.amazon.com/guardduty/latest/ug/runtime-monitoring.html)
- [GuardDuty Malware Protection for EC2](https://docs.aws.amazon.com/guardduty/latest/ug/malware-protection.html)
- [GuardDuty Malware Protection for S3](https://docs.aws.amazon.com/guardduty/latest/ug/guardduty-malware-protection-s3.html)
- [Creating Sample Findings](https://docs.aws.amazon.com/guardduty/latest/ug/sample_findings.html)
- [GuardDuty Pricing](https://aws.amazon.com/guardduty/pricing/)
