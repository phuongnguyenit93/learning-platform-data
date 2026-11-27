# Prioritizing, Assigning, and Tracking Finding Remediation

In AWS environments spanning multiple accounts, Regions, and services, security alerts can arrive from AWS Security Hub CSPM, Amazon GuardDuty, Amazon Inspector, Amazon Macie, IAM Access Analyzer, AWS Config, and third-party security products. An individual finding may describe a misconfiguration, software vulnerability, suspicious behavior, or an Internet-exposed resource. Handling findings strictly in arrival order or solely by severity label risks missing high-impact threats while wasting time on duplicate alerts.

AWS Security Hub aggregates and normalizes findings so security teams can search, analyze, prioritize, and orchestrate remediation. With Security Hub CSPM, findings use the AWS Security Finding Format (ASFF) and include fields such as Severity, Criticality, Workflow, and RecordState. The current AWS Security Hub also provides findings in Open Cybersecurity Schema Framework (OCSF) format, exposure findings, and remediation plans that group multiple issues sharing a root cause into a single remediation action.

This lesson presents the operational workflow from receiving a finding through verifying remediation. The process combines risk assessment, resource owner identification, ticketing, remediation execution, re-verification via the detecting source, and evidence preservation. AWS Security Hub supplies data and automation mechanisms; operations teams still define ownership, deadlines, and approval workflows suited to their systems.

## Learning Objectives

After this lesson, learners will be able to:

- Distinguish finding, severity, resource criticality, confidence, workflow status, and record state.
- Prioritize findings based on exploitability, exposure, business impact, and blast radius.
- Identify duplicate findings or findings sharing a root cause to avoid redundant work.
- Identify responsible teams or owners using accounts, resource tags, applications, and asset management systems.
- Use AWS Security Hub CSPM automation rules, EventBridge, and ticketing integrations to orchestrate work.
- Distinguish ASFF workflows in Security Hub CSPM from OCSF findings and remediation plans in the current AWS Security Hub.
- Track progress, SLAs, finding aging, verification outcomes, and recurrence risks.
- Design controlled remediation automation with auditing and rollback plans.

## 1. What Is a Finding and Where Does It Come From?

A finding is a record describing a security issue, notable event, or security control check result. Findings typically identify the affected resource, account, Region, observation timestamp, severity level, and supporting investigative details.

In the AWS ecosystem, findings can originate from:

| Source | Example Finding | Typical Follow-On Work |
|---|---|---|
| Amazon GuardDuty | Unusual credential activity, malware, suspicious access, or malicious IP behavior. | Incident investigation, workload isolation, evidence collection, and identity protection. |
| Amazon Inspector | CVE in a package, container image, or EC2 instance. | Assess exploitability, update packages, or release a new image. |
| Amazon Macie | Sensitive data in Amazon S3 and associated risks. | Verify data classification, access permissions, and data protection requirements. |
| IAM Access Analyzer | Resource policy or trust policy permitting unintended access. | Review principals, tighten permissions, and confirm sharing necessity. |
| AWS Config and Security Hub CSPM controls | Open security group ports, misconfigured S3 buckets, disabled logging, or non-compliant encryption. | Fix configurations and await the next compliance check. |
| Third-party products | Vulnerabilities, compromise indicators, or policy violations. | Investigate per detecting source and coordinate with the product owner. |

Security Hub CSPM ingests findings from integrated services and normalizes them into ASFF. The current Security Hub receives findings in OCSF, including data from Security Hub CSPM, GuardDuty, Macie, Inspector, and other supported sources. These two formats differ in field names and lifecycles; when building automation or integrations, match the exact schema of the event source.

A finding is not synonymous with an incident. A finding may represent an unexploited misconfiguration, a vulnerability awaiting scheduled patching, a compliance check result, or a signal of an active incident. Security teams must triage before selecting a response workflow.

## 2. Reading a Finding Before Deciding Priority

Do not rely solely on the title or severity label. Inspect the attributes that identify the issue, resource, and evidence.

For ASFF findings in Security Hub CSPM, key fields to inspect include:

| Field | Operational Meaning |
|---|---|
| Id and ProductArn | Identifiers for the finding and generating product; both are required when calling BatchUpdateFindings. |
| AwsAccountId | AWS account holding the associated resource or object. |
| Region | Region where the finding was recorded. |
| Title, Description, Types | Summary, details, and classification of the issue. |
| Severity.Label | Severity label: CRITICAL, HIGH, MEDIUM, LOW, or INFORMATIONAL. |
| Severity.Normalized | Normalized severity value on a 0–100 scale when available. |
| Confidence | Detection confidence on a 0–100 scale. |
| Criticality | Importance of the associated resource on a 0–100 scale. |
| Resources | Affected resources, resource types, ARNs, IDs, and available details. |
| Compliance.Status | Control compliance outcome, such as FAILED, PASSED, WARNING, or NOT_AVAILABLE. |
| Workflow.Status | Investigation status of the finding in the customer's workflow. |
| RecordState | Record state, either ACTIVE or ARCHIVED. |
| CreatedAt, UpdatedAt, FirstObservedAt, LastObservedAt | Timestamps for finding creation, updates, and observations. |
| Remediation | Remediation instructions or link if provided by the vendor/service. |
| RelatedFindings | Related findings linked to the current finding. |
| UserDefinedFields and Note | Supplemental information recorded by the customer. |

For OCSF findings in the current AWS Security Hub, inspect corresponding fields such as finding_info, resources, severity_id, confidence_score, remediation, and account/Region metadata. Do not mechanically copy ASFF paths into OCSF; use the OCSF schema and filters supported by V2 APIs.

### 2.1. Severity Is Not the Whole Risk

Severity reflects how serious an issue is according to the detecting source or control. Yet the exact same flaw can carry vastly different impact depending on the resource.

For example:

- A security group opening an admin port on a temporary test machine has different impact than one opening SSH on a production payment system.
- A CVE with a known exploit affecting an Internet-facing service requires faster handling than a hard-to-exploit CVE on an isolated workload.
- An approved public website bucket differs from a customer-data bucket accidentally granted public read access.

Security Hub CSPM distinguishes severity from Criticality. Severity does not automatically account for resource importance. The Criticality field in ASFF uses a 0–100 scale to describe the importance of the resource tied to the finding.

In the current AWS Security Hub, resources can be assigned criticality levels of Very High, High, Medium, Low, or Unknown. Security Hub can infer criticality from resource names and tags; resource-rule automation rules can override this inference. Resource criticality serves as an input when Security Hub calculates the impact and severity of exposure findings.

Do not inflate severity solely because a resource runs in production. Record resource importance in the criticality field or corresponding metadata, then use it in prioritization rules. This preserves the meaning of original severity while helping teams separate technical risk from business impact.

### 2.2. Confidence and Verification State

Confidence describes how certain the detector is that the finding accurately reflects the behavior or issue it targets. A value of 100 indicates highest confidence; lower values suggest additional verification is warranted. Confidence is not the probability that an incident will definitely occur.

VerificationState in ASFF records whether a finding has been verified as a true positive, false positive, or remains unknown under Security Hub CSPM's data model. Before suppressing, inspect evidence and verify whether a false positive stems from scanner configuration, a test environment, or an approved exception.

A high-severity finding with low confidence needs prompt investigation to confirm. Never ignore it automatically just because confidence is low; equally, never take destructive action solely on an unverified signal.

## 3. Distinguishing Workflow.Status and RecordState

These are two distinct fields in Security Hub CSPM.

- Workflow.Status reflects the customer's investigation and handling progress.
- RecordState reflects whether the finding remains active in the dataset or has been archived by the provider.

| Field | Value | Meaning |
|---|---|---|
| Workflow.Status | NEW | New finding not yet evaluated by the handling team. |
| Workflow.Status | NOTIFIED | Resource owner has been notified and action is pending. |
| Workflow.Status | SUPPRESSED | Reviewed and determined no action needed under current procedures. |
| Workflow.Status | RESOLVED | Remediated and considered resolved. |
| RecordState | ACTIVE | Finding remains active in Security Hub CSPM. |
| RecordState | ARCHIVED | Finding has been archived and hidden from certain default views. |

Do not use RecordState to represent the assignee or ticket progress. Customers update workflow via the console or BatchUpdateFindings; RecordState is updated only by the finding provider via BatchImportFindings and cannot be modified using BatchUpdateFindings.

Key lifecycle behaviors to know:

- New findings typically start with workflow NEW and record state ACTIVE.
- If a control finding's Compliance.Status transitions from FAILED to PASSED, Security Hub CSPM automatically sets workflow to RESOLVED.
- If a finding in NOTIFIED or RESOLVED transitions its record state from ARCHIVED to ACTIVE, workflow may reset to NEW.
- If compliance transitions from PASSED to FAILED, WARNING, or NOT_AVAILABLE, a control finding's workflow may revert to NEW.
- SUPPRESSED behaves independently and does not automatically reset to NEW merely because record state changes from ARCHIVED to ACTIVE.

Workflow status applies per finding. Setting a finding to RESOLVED or SUPPRESSED does not stop a provider from creating a new finding for the same issue on future scans. Therefore, if the underlying misconfiguration persists, teams must fix the root cause rather than merely flipping statuses.

## 4. Building Risk-Based Prioritization

A strong prioritization workflow combines severity, exploitability, exposure, asset criticality, and business impact. You can start with this internal classification table:

| Operational Priority | Typical Indicators | Handling Approach |
|---|---|---|
| P0 – Emergency | Signs of active compromise, unauthorized data access, exposed credentials being actively used, or critical asset under exploitation. | Trigger incident response immediately, isolate/contain per runbook, and preserve evidence. |
| P1 – Very High | Critical/High finding on Internet-facing or business-critical assets; known exploit; broad permissions; potential data leak or privilege escalation. | Assign owner immediately; resolve in an emergency window per organizational SLA. |
| P2 – High | Patchable vulnerability, production misconfiguration, or attack path requiring additional preconditions. | Schedule in the nearest sprint/maintenance window and track deadline. |
| P3 – Medium | Issue with limited impact, difficult to exploit, or affecting non-critical resources. | Plan remediation and monitor on regular cadence. |
| P4 – Low/Informational | Informational results, hardening recommendations, or controlled accepted findings. | Monitor, improve opportunistically, or retain as evidence. |

This is an example operational model, not a priority label automatically assigned by AWS Security Hub. Organizations must tailor it to legal obligations, SLAs, on-call capacity, and system criticality.

### 4.1. Factors to Weigh

When evaluating a finding, examine in turn:

1. **Severity:** is the finding Critical/High or merely informational?
2. **Exploitability:** is there a public exploit, active CVE exploitation, or an easily executed attack path?
3. **Exposure:** does the resource have a public endpoint, public IP, public policy, or path from untrusted networks?
4. **Asset criticality:** does the resource serve critical systems, hold sensitive data, or back privileged identities?
5. **Blast radius:** if exploited, which additional accounts, workloads, or data could an attacker reach?
6. **Confidence:** is finding evidence reliable enough to act upon?
7. **Compensating controls:** are WAF, network segmentation, MFA, encryption, or other mitigations already in place?
8. **Remediation effort and reversibility:** can it be fixed immediately, or does it require a deployment or maintenance window?

Avoid mechanical point-summing that ignores context. A Medium-severity finding exposing secrets across multiple production accounts may warrant higher priority than a High finding on an empty test resource.

### 4.2. Decision Matrix Examples

| Finding | Severity | Resource | Exposure/Exploitation | Suggested Priority |
|---|---|---|---|---|
| GuardDuty detects anomalous behavior on a production role access key | High/Critical depending on finding | Broadly privileged role | Signs of unauthorized usage | P0/P1; handle as incident if compromise is verified |
| Inspector detects an exploitable CVE on an Internet-facing container | Critical/High | Production service | Public exploit, direct access path | P1 |
| S3 bucket containing sensitive data becomes public | Critical | Critical data store | Public access | P0/P1 depending on access evidence |
| Security group opens a test port on an isolated EC2 instance | Medium/High | Non-production | Not public, segmented | P2/P3 after verification |
| Security Hub control flags missing tag on a sandbox resource | Low | Sandbox | No direct exposure | P4 or hygiene backlog |

The P0–P4 tiers in this table illustrate SLA design. Always cite the finding's original severity label and evidence when communicating with owners; avoid altering severity solely to force a ticket into another queue.

## 5. Grouping Duplicate Findings and Finding Root Causes

A single root cause can generate many findings:

- One security group shared by many EC2 instances or load balancers.
- One overly permissive policy affecting multiple resources.
- One base image containing a vulnerable package deployed across multiple ECS/EKS workloads.
- One Security Hub control failing across many resources produced by the same Terraform or CloudFormation module.
- One network path flaw generating multiple related exposure findings.

Creating one ticket per finding without root-cause grouping forces remediation teams to process the exact same change repeatedly. Conversely, merging unrelated findings obscures verification and ownership.

Use these attributes to identify groups:

- Account, Region, resource ARN/ID, and resource type.
- Product ARN, Generator ID, control ID, or CVE.
- Rule ID, finding type, package name, and version.
- Network path, security group, IAM role, or associated policy.
- RelatedFindings and resource relationships.
- Application or workload tags attached to resources.

Never group findings solely because they share a Title. Compare resources, evidence, control IDs, and technical root causes. Every finding must still remain traceable to its corresponding ticket or remediation plan.

### 5.1. Consolidated Control Findings

Security Hub CSPM supports consolidated control findings to reduce duplicate findings when the same control appears in multiple security standards. When enabled, Security Hub creates one standardized finding per security control rather than one per standard.

AWS recommends consolidated control findings to reduce noise. When toggling this feature, Security Hub may create new findings and archive old ones; the transition can take up to 24 hours. If automation or ticketing relies on legacy ARNs/GeneratorIds, test before switching.

### 5.2. Remediation Plans in the Current AWS Security Hub

The current AWS Security Hub can generate remediation plans from exposure findings. A plan groups exposures sharing a root cause targeting a specific resource. Fixing that resource can resolve or lower the severity of multiple exposures simultaneously.

A remediation plan includes:

| Attribute | Meaning |
|---|---|
| Priority | Handling urgency: Critical, High, Medium, or Low. |
| Status | New, Updated, or Resolved. |
| Impact | Number of exposures fully resolved, severity-reduced, or impacted without severity change. |
| Rollout | Whether changes take effect immediately or require deployment. |
| Action | Change recommended by Security Hub. |
| Trait | Exposure characteristic addressed by the plan. |
| Target resource | Resource and resource type requiring remediation. |
| Account/Region | Account and Region owning the resource. |

Security Hub sets remediation plan status automatically; users do not alter it directly. New means the plan was just created; Updated means the plan changed; Resolved means Security Hub no longer generates a plan from current exposures. Resolved plans may remain visible for about 14 days before disappearing from the list.

Distinguish plan status from finding status. A Resolved plan does not always mean every exposure finding is Resolved; for example, a finding may only drop to Informational severity or lose the specific trait targeted by the plan. Open the Affected exposures tab and inspect individual findings.

Security Hub provides phased guidance such as prerequisite, snapshot, fix, verify, and done, sometimes including CLI, Terraform, CDK, or CloudFormation snippets. Security Hub outlines the remediation steps; operators still apply the change and verify results.

## 6. Identifying Owners and Assigning Remediation

A finding gets resolved on time only when a team or individual holds clear accountability. The owner is typically the team managing the resource, application, or platform introducing the risk.

Owner identification sources include:

- AWS account owners and OUs in AWS Organizations.
- Resource tags such as Application, Owner, Team, Environment, and CostCenter.
- AWS Service Catalog AppRegistry or internal application catalogs.
- CMDBs, service ownership directories, or IaC repositories.
- Account vending metadata and resource naming conventions.

Routing examples:

| Condition | Receiving Team |
|---|---|
| Application=checkout | Checkout team |
| Environment=production and ResourceType=AWS::RDS::DBInstance | Database platform/on-call DBA |
| Finding involves an IAM role used by a pipeline | Platform security or CI/CD owner |
| EC2/ECS image has a CVE | Container/platform team or service owner |
| S3 bucket holds sensitive data | Data owner with Security/Privacy |
| GuardDuty finding indicates credential compromise | SOC/Incident Response first, then hand off to workload owner |

### 6.1. Assigning in the Ticketing System

Security Hub CSPM provides workflow status to track investigation, yet Workflow.Status is not an assignee field. Operations teams should use Jira, ServiceNow, or a work-management system as the system of record for:

- Assignee or owning team.
- Ticket ID and link to the finding.
- SLA deadline, due date, and priority.
- Remediation, deployment, and rollback plans.
- Verification evidence, approver, and closure timestamp.

If routing context needs visibility inside ASFF, use UserDefinedFields and Note to record metadata such as team, ticket ID, or assignment rationale. Never store secrets, personal data, or unnecessary sensitive information in notes.

A ticket should contain at minimum:

1. Finding ID, ProductArn, and link to Security Hub.
2. Account, Region, resource ARN/ID, and application.
3. Severity, criticality, operational priority, and evidence.
4. Required action and remediation instructions.
5. Owner, assignee, collaborators, and deadline.
6. Completion criteria and required verification evidence.
7. Rollback or escalation plan if changes impact production.

### 6.2. Never Assign Tickets Solely by Resource Name

Resource names can be outdated or non-compliant with conventions. If owner tags are missing or wrong, route the finding to an ownership triage queue and have account/CMDB administrators confirm ownership. Never guess owners from name strings, and never leave Critical/High findings stranded indefinitely due to missing metadata.

Maintain a dedicated queue for:

- Findings with unidentified owners.
- Missing or invalid resource tags.
- Accounts with no active owner.
- Resources co-managed by multiple teams.
- Findings requiring Security/Legal/Privacy or incident commander decisions.

## 7. Updating Findings in Security Hub CSPM

Customers can update specific investigation-related fields using BatchUpdateFindings. This API does not create new findings; a single request can update up to 100 existing findings. Both Id and ProductArn must be passed for each finding.

Customer-updatable fields include Confidence, Criticality, Note, RelatedFindings, Severity, Types, UserDefinedFields, VerificationState, and Workflow.

Never use BatchUpdateFindings to modify RecordState or fields owned by the finding provider. This operation also does not update the finding's UpdatedAt timestamp. To track when a ticket was acknowledged or remediation completed, record timestamps in your ticketing system or separate operational metadata.

Example updating workflow and adding a note after assigning to an owner:

~~~bash
aws securityhub batch-update-findings \
  --finding-identifiers '[{"Id":"<FINDING_ID>","ProductArn":"<PRODUCT_ARN>"}]' \
  --workflow '{"Status":"NOTIFIED"}' \
  --note '{"Text":"Assigned to Platform Team. Ticket SEC-1234. Target remediation: 2026-12-05.","UpdatedBy":"security-operations"}' \
  --region ap-southeast-1
~~~

Example setting status to RESOLVED after verifying remediation:

~~~bash
aws securityhub batch-update-findings \
  --finding-identifiers '[{"Id":"<FINDING_ID>","ProductArn":"<PRODUCT_ARN>"}]' \
  --workflow '{"Status":"RESOLVED"}' \
  --note '{"Text":"Remediation verified. Security control passed and application owner confirmed.","UpdatedBy":"security-operations"}' \
  --region ap-southeast-1
~~~

These are syntax examples. Substitute real finding IDs, Product ARNs, Regions, ticket IDs, and note contents. Check ProcessedFindings and UnprocessedFindings in the API response; never assume all findings updated successfully.

### 7.1. Notes on Control-Generated Findings

For control findings, Security Hub CSPM executes security checks on a schedule or when resource states change. When Compliance.Status transitions from FAILED to PASSED, Security Hub updates the existing finding and automatically sets workflow to RESOLVED. If status transitions from PASSED to FAILED, the finding may revert to NEW.

Therefore, for control findings, wait for the fresh check result and verify Compliance.Status. Never close a ticket merely because a remediation command ran; the control must re-evaluate the change.

## 8. Automation Rules for Normalization and Noise Reduction

Automation rules in Security Hub CSPM automatically modify finding fields based on team-defined criteria. Common use cases include:

- Raising severity for findings affecting critical production resources.
- Setting workflow to SUPPRESSED for findings approved as non-applicable in test environments.
- Adding notes explaining exceptions or application codes.
- Attaching RelatedFindings to help teams recognize links.
- Adjusting confidence or criticality based on verified data.
- Automatically normalizing findings from a third-party integration using a different severity mapping.

Multiple rules can match on account, Region, resource type, tags, product, control ID, severity, and workflow. Rule ordering matters: rules applied later can overwrite values set by earlier rules.

When writing automation for control findings, filter by SecurityControlId or SecurityControlArn rather than Title/Description, as titles and descriptions may change in documentation/control updates.

### 8.1. Automation Rules vs. EventBridge

- **Automation rules:** update or suppress finding fields inside Security Hub CSPM.
- **EventBridge rules:** react to events, invoke Lambda, Step Functions, SSM Automation, SNS/SQS, or route findings to ticketing/SIEM tools.

In Security Hub CSPM, automation rules apply before EventBridge; EventBridge receives findings after automation updates have run. Automation rules evaluate new findings or findings ingested/updated by providers via BatchImportFindings. Customer BatchUpdateFindings calls do not trigger automation rules.

This distinction matters when designing bidirectional synchronization. If a ticketing system updates workflow via BatchUpdateFindings, do not expect automation rules to re-run on that update.

### 8.2. Automation in the Current AWS Security Hub

The current AWS Security Hub uses OCSF. Automation rules can update OCSF fields such as Comment, SeverityId, and StatusId. Alongside finding rules, Security Hub offers resource rules to assign resource criticality—Very High, High, Medium, Low, or Unknown—based on criteria.

Finding rules can create tickets directly in Jira Cloud or ServiceNow ITSM when findings match criteria. Resource rules only update resource criticality; they do not simultaneously update findings or create tickets. Both rule types share a quota of up to 100 rules per account/Region.

Do not mix V2/OCSF APIs with CSPM/ASFF APIs. Choose the exact rule type, field paths, event types, and update operations matching your product.

## 9. EventBridge: Turning Findings into Actionable Work

Security Hub CSPM emits events to Amazon EventBridge whenever findings are created or updated. The standard event type is Security Hub Findings - Imported with source aws.securityhub. Events can originate from both BatchImportFindings and BatchUpdateFindings.

Example event pattern filtering active Critical/High findings:

~~~json
{
  "source": ["aws.securityhub"],
  "detail-type": ["Security Hub Findings - Imported"],
  "detail": {
    "findings": {
      "RecordState": ["ACTIVE"],
      "Severity": {
        "Label": ["CRITICAL", "HIGH"]
      }
    }
  }
}
~~~

Patterns can route events to Lambda, Step Functions, SNS, SQS, Kinesis Data Streams, or API destinations. Lambda/Step Functions can:

1. Read the finding and extract account/resource metadata.
2. Look up the owner from resource tags, account inventory, or CMDB.
3. Compute operational priority per policy.
4. Create a ticket in Jira/ServiceNow or submit a request to a workflow engine.
5. Write the ticket ID and owner into permitted metadata.
6. Notify the responsible team.
7. Archive events/evidence in S3 or an audit system.

For the current AWS Security Hub, EventBridge uses the event type Findings Imported V2 for V2 events. Payloads follow OCSF, so write event patterns against OCSF fields rather than the ASFF paths in the CSPM example.

### 9.1. Designing Reliable Event Processing

EventBridge and target services operate in a distributed model. The same finding can be redelivered when providers update it or during retries. Therefore, ticket automation must be idempotent:

- Use a stable finding key (such as ProductArn + Id for ASFF, or finding UID in OCSF) to look up existing tickets.
- If a ticket already exists, update it instead of creating a new one.
- Distinguish finding-creation events from finding-update events.
- Handle retries, throttling, dead-letter queues, and permission errors.
- Record synchronization status, last attempt timestamp, and latest error.
- Never open a P0 incident simply because the same event was redelivered.

Never automatically block, terminate, or delete resources solely based on a severity event pattern. High-impact actions require strong preconditions, resource verification, and runbook approvals.

## 10. Jira Cloud and ServiceNow Integrations

The current AWS Security Hub supports native ticketing integrations with Jira Cloud and ServiceNow ITSM. Teams can create tickets manually from findings or use automation rules to create tickets automatically when findings match criteria.

### 10.1. Jira Cloud

Jira Cloud integration sends findings into projects so development or operations teams can manage investigation and remediation. Tickets can be assigned to owners, given priorities and due dates, and tracked through Jira workflows.

Preparation steps:

- Install the AWS Security Hub for Jira Cloud app in Jira.
- Use a company-managed software project as required by the integration.
- Link the project to the AWS Security Hub for Jira Cloud app.
- Configure the OAuth connector and required permissions.
- Define the project ID, issue type, workflow, and severity/priority mapping.
- Use a dedicated integration account rather than tying OAuth to an individual employee account whose permissions might change.

Jira enforces API rate limits. Under high finding volume, ticket creation may lag; Security Hub retries throttled findings for up to 3 days. After the retry window, still-throttled findings may fail to generate tickets. Filter tickets by priority, monitor API usage, and build a reconciliation job to catch findings lacking tickets.

### 10.2. ServiceNow ITSM

ServiceNow ITSM integration can create incidents or problems from findings. Before configuring:

- Install the Security Hub findings integration for ITSM app from the ServiceNow Store.
- Configure OAuth client credentials for inbound OAuth.
- Store the client ID and client secret in AWS Secrets Manager.
- Use a customer-managed KMS key and appropriate key policy so Security Hub can access the secret.
- Create a V2 connector with the instance URL and Secret ARN.
- Select behavior upon receiving findings: do nothing, create incident, create problem, or create both.

ServiceNow fits organizations already relying on CMDB, assignment groups, change requests, incident/problem management, and SLAs. Align which ticket statuses correspond to finding workflow statuses.

### 10.3. Bidirectional Synchronization

If ticketing tools can update findings, define clearly which system is the source of truth per field:

| Information | Primary Source of Truth |
|---|---|
| Finding evidence, provider severity, and resource details | Security Hub / finding provider |
| Assignee, assignment group, due date, sprint | Jira or ServiceNow |
| Investigation workflow in CSPM | Security Hub Workflow.Status, synced per policy |
| Remediation steps, change approval, rollback | Ticketing/change management system |
| Post-remediation compliance status | Security Hub CSPM control or corresponding check source |
| Work audit history | Ticketing system and CloudTrail/EventBridge logs |

Never allow two systems to overwrite each other without rules. For instance, if a ticket moves to Done while the control remains FAILED, the finding is not yet remediated. Conversely, a RESOLVED finding where the ticket lacks evidence or an approved change record also needs review.

## 11. Remediation: Choosing Fixes and Controlling Change

Remediation changes configurations, code, permissions, or processes to eliminate a finding's root cause. Select actions based on the resource and evidence rather than applying the same action to every finding sharing a severity.

| Finding | Remediation Direction |
|---|---|
| Unintentionally public S3 bucket | Review bucket policy, ACLs, Block Public Access, access points, and sharing needs; verify with access tests. |
| Security group exposing SSH/RDP to Internet | Identify legitimate admin sources, restrict CIDR ranges, or switch to Systems Manager Session Manager. |
| CVE in EC2/AMI | Update packages, build a new AMI, deploy replacements, and verify versions post-deploy. |
| CVE in container image | Update base image/dependencies, rebuild image, rescan, and deploy the approved digest. |
| Overly permissive IAM policy | Identify required actions/resources, narrow policy, verify assume-role behavior and CloudTrail post-change. |
| GuardDuty detects credential compromise | Isolate/disable credential per incident runbook, verify sessions, rotate secrets, and monitor follow-on access signs. |
| Macie detects unexpected sensitive data | Confirm classification, restrict access, apply encryption/retention, and handle per data policy. |

### 11.1. Classifying Automation Levels

| Remediation Tier | Example | Required Controls |
|---|---|---|
| Safe automation | Standard tagging, opening tickets, enriching metadata, notifying owners. | Idempotency, least privilege, and auditing. |
| Conditional automation | Revoking a confirmed misconfigured ingress rule, fixing logging configuration per policy. | Strict preconditions, dry-run, testing, rollback, and bounded blast radius. |
| Approval required | Altering IAM trust policies, modifying route tables, changing KMS key policies, deploying production patches. | Owner approval, change record, maintenance window, and rollback plan. |
| Incident response | Isolating instances, revoking credentials, or blocking network paths during active compromise. | Incident commander, runbook, evidence preservation, and full logging. |

AWS Systems Manager Automation, Lambda, and Step Functions can orchestrate remediation. For actions touching production or identities, enforce approval and verification before applying. Never use a Lambda function with AdministratorAccess to handle all findings.

### 11.2. Remediation Runbooks

A solid runbook follows this structure:

1. Trigger conditions and resource scope.
2. Finding ID, resource ARN, and data requiring verification.
3. Minimum required IAM permissions.
4. Pre-checks: resource state, backups/snapshots, dependencies, and maintenance window.
5. Change step: CLI, API, Systems Manager Automation, or IaC.
6. Verification step: read-back API call, security check, or traffic test.
7. Rollback step: restore prior configuration if verification fails.
8. Evidence: CloudTrail event, change ID, test output, and approver.

When remediating via IaC, update the source of truth and deploy through the pipeline. Modifying resources directly in the console risks drift or being overwritten on the next deployment.

## 12. Verifying Remediation

Never close a finding solely because a ticket moved to Done. Verify with the authoritative source:

- Security Hub CSPM control finding: wait for the next security check and confirm Compliance.Status is PASSED.
- Amazon Inspector: run or wait for the next scan; check package/version and finding lifecycle.
- GuardDuty: verify provider updates or closure per detection logic; confirm no compromise indicators remain.
- Macie: re-evaluate data and policies after changes; confirm status on the subsequent scan.
- IAM Access Analyzer: re-run analysis or wait for the analyzer to update status.
- AWS Config: verify configuration items and compliance evaluations.
- Security Hub exposure finding: confirm exposure dropped or disappeared; if using a remediation plan, open the Affected exposures tab to inspect impact.

For control findings, Security Hub CSPM can automatically set Workflow.Status=RESOLVED when compliance shifts to PASSED. For findings from other services, providers update findings under their own lifecycles. Do not assume every provider closes findings identically.

### 12.1. Verifying Without False Closure

Several scenarios warrant deeper checks:

- A resource was deleted so the finding became archived, yet the remediation ticket did not intend deletion.
- A control was disabled, causing the finding to archive; this does not prove the resource configuration is safe.
- A scanner has not re-run yet, leaving the old finding visible even though configuration was fixed.
- A provider re-detects the issue after workflow was set to RESOLVED.
- A ticket was closed, yet IaC later recreated the resource with the old misconfiguration.

Record verification results, check timestamp, verifier, and data source. If a finding recurs, reopen the ticket or link a new ticket to the prior remediation to address the root cause of recurrence.

## 13. Tracking SLAs, Aging, and Remediation Effectiveness

A finding workflow must measure both handling speed and risk reduction—not just total finding counts.

| Metric | Interpretation | Purpose |
|---|---|---|
| Open findings by priority | Unresolved findings across P0–P4. | Track backlog by urgency. |
| Mean Time to Triage (MTTT) | Time from finding appearance to triage/routing. | Measure intake speed. |
| Mean Time to Assign (MTTA) | Time from finding appearance to owner assignment. | Spot ownership bottlenecks. |
| Mean Time to Remediate (MTTR) | Time from detection to verified remediation. | Measure remediation capability. |
| SLA breach rate | Percentage of findings overdue by priority. | Manage escalations. |
| Finding aging | Open findings grouped by age buckets, e.g., 0–7, 8–30, 31–60, over 60 days. | Identify stale backlogs. |
| Reopen/recurrence rate | Findings or root causes reappearing post-remediation. | Measure fix durability. |
| Suppression ratio | Ratio of suppressed findings to total findings. | Detect overly broad suppression. |
| Remediation success rate | Percentage of tickets passing verification. | Evaluate runbook quality. |
| Risk reduction | Count of exposures resolved/severity-reduced weighted by resource criticality. | Measure actual security outcomes. |

Illustrative internal SLA starting point (adjust per organization):

| Priority | Triage/Owner | Remediation Plan | Escalation |
|---|---|---|---|
| P0 | Immediately upon receipt | Immediate incident response | Incident commander/on-call lead |
| P1 | Within current shift | Emergency remediation per runbook | Security lead and service owner |
| P2 | Within 1 business day | Nearest sprint or maintenance window | Engineering manager |
| P3 | Within 5 business days | Deadline-tracked backlog | Team lead |
| P4 | Per review cycle | Hardening backlog | Security governance |

These are example internal SLAs, not AWS defaults. Organizations must adapt them to contracts, compliance policies, on-call coverage, and production change tolerance.

### 13.1. Notes on Finding Retention Limits

Security Hub CSPM automatically deletes stale findings to reduce noise:

- ACTIVE findings not updated within 90 days expire and are permanently deleted.
- ARCHIVED findings not updated within 30 days expire and are permanently deleted.

Expiration calculations depend on finding type and timestamps such as UpdatedAt/ProcessedAt. BatchUpdateFindings does not refresh UpdatedAt. When long-term evidence is required, export findings to Amazon S3 via EventBridge/custom actions or appropriate export mechanisms. Ticketing systems should also retain finding links and independent audit records.

## 14. Managing Multiple Accounts and Regions

In AWS Organizations environments, designate a delegated administrator for Security Hub and govern coverage organization-wide. The delegated administrator can view member account findings within supported scope and configure integrations, automation, and policies per permissions.

For Security Hub CSPM:

- AWS Organizations declarative policies are currently the recommended method for managing CSPM configuration organization-wide.
- Central configuration is a legacy mechanism; existing organizations may keep using it, though new deployments should not choose it without compatibility reasons.
- Cross-Region aggregation uses a home Region and linked Regions to centralize findings, insights, compliance status, and security scores.
- Enabling aggregation does not automatically enable Security Hub CSPM in those Regions; each account must be enabled/managed individually.
- Administrators must sign in to the home Region to view aggregated data from member accounts and linked Regions.

In the current AWS Security Hub, Region aggregation enables creating automation in the home Region that applies across linked Regions per configuration. Unlinked Regions may require separate rules. When altering aggregation or delegated administrators, check impacts on automation and ticketing.

### 14.1. Ownership by Account/OU

Responsibilities can be divided as follows:

- Security tooling account: manages delegated administration, policies, automation, integrations, and dashboards.
- Workload account: responsible for fixing resources and supplying evidence.
- Platform account: manages networking, foundational IAM, CI/CD, logging, and shared services.
- Data account: responsible for data classification, protection, and retention.
- Incident response: handles findings indicating active compromise or suspicious ongoing activity.

The security team coordinates and verifies; workload owners execute remediation within their application/resource scope. A clear RACI prevents findings from bouncing between teams without resolution.

## 15. End-to-End Operational Workflow

The diagram below illustrates a reference lifecycle:

~~~mermaid
flowchart TD
    A["Finding from GuardDuty / Inspector / Macie / Config"] --> B["Security Hub normalizes and aggregates"]
    B --> C["Triage: verify, enrich, deduplicate"]
    C --> D{"Signs of active compromise?"}
    D -->|"Yes"| E["Incident response / containment"]
    D -->|"No"| F["Prioritize by severity + asset criticality + exposure"]
    E --> G["Assign incident owner and preserve evidence"]
    F --> H["Look up application/resource owner"]
    H --> I["Create or update ticket"]
    I --> J["Owner prepares remediation plan and change"]
    J --> K["Execute remediation"]
    K --> L["Verify via provider/control/scan"]
    L --> M{"Is it secure?"}
    M -->|"No"| J
    M -->|"Yes"| N["Update finding/ticket and close work"]
    G --> L
    N --> O["Metrics, lessons learned, and prevent recurrence"]
~~~

Detailed operational workflow:

1. Receive finding and verify exact account, Region, resource, and provider.
2. Verify finding, evidence, confidence, and actual state.
3. Find related findings, deduplicate, and identify root cause.
4. Assess severity, exploitability, exposure, criticality, and blast radius.
5. Identify owner; if unclear, route to ownership triage.
6. Create a ticket or remediation plan; record finding ID and resource ARN.
7. Set SLA, due date, approver, and completion criteria.
8. Select appropriate remediation; include approval/rollback if needed.
9. Deploy change via IaC/pipeline/runbook.
10. Verify through the detecting source or independent checks.
11. Update workflow/ticket and archive evidence.
12. Track recurrence, aging, and backlog trends.

## 16. Practical Scenario: Public S3 Bucket in a Production Account

A Security Hub CSPM finding reports an S3 bucket may be publicly accessible. The bucket resides in a production account and carries the tag Application=customer-data. The security team must prioritize, assign, and track until verified safe.

**Step 1 – Triage**

- Read finding ID, ProductArn, resource ARN, severity, and compliance status.
- Inspect bucket policy, ACLs, Block Public Access, and access points.
- Look up owner from tags, AppRegistry, or CMDB.
- Determine whether the bucket holds sensitive data and check access logs/CloudTrail for evidence of public access.
- If signs of unauthorized data access appear, initiate incident response and preserve evidence.

**Step 2 – Prioritization**

If the bucket holds customer data and a policy accidentally permits public read access, classify as P0/P1 based on evidence and exposure scope. If the bucket is an approved public static website, verify the exception, CloudFront/OAC architecture, and finding scope before suppressing.

**Step 3 – Assignment**

- Owner: customer-data team.
- Collaborators: cloud platform and security.
- Ticket: include finding ID, bucket ARN, policy evidence, due date, and remediation steps.
- Workflow: NOTIFIED once assigned to the owner in Security Hub CSPM.

**Step 4 – Remediation**

- Identify whether public access originates from bucket policy, ACL, access point, or account-level settings.
- If public access is unnecessary, fix policy/ACL and enable Block Public Access at the appropriate scope.
- If serving public website content, front with CloudFront using origin access control and restricted policies.
- Deploy changes via IaC to prevent drift.

**Step 5 – Verification**

- Re-read bucket policy and public access block settings.
- Test access from an unauthorized client.
- Test legitimate website flow if the bucket serves public content.
- Wait for Security Hub/AWS Config re-evaluation and verify Compliance.Status=PASSED.
- Preserve CloudTrail events, test output, and ticket change records.

**Step 6 – Work Closure**

Once evidence is complete, move the ticket to Done and update the finding to RESOLVED or allow control evaluation to resolve it automatically. Monitor the next scan cycle to ensure another pipeline or policy does not re-expose the bucket.

## 17. Common Pitfalls

1. **Sorting purely by severity.** Ignores resource criticality, exposure, exploitability, and blast radius.
2. **Treating severity as priority.** Finding severity and internal SLA priority are two distinct concepts.
3. **Confusing Workflow with RecordState.** Workflow tracks investigation; RecordState is managed by the provider for record lifecycle.
4. **Assigning owners by resource name.** Names can mislead; rely on tags, AppRegistry, CMDB, or account owners.
5. **Creating one ticket per finding.** Failing to group by root cause creates duplicate backlogs.
6. **Suppressing to shrink backlogs.** Suppression does not fix configurations and requires justification, owner, and review expiry.
7. **Closing findings right after deployment.** Always verify via the check source or provider.
8. **Letting ticketing systems and Security Hub overwrite each other.** Define sources of truth for assignees, workflow, and evidence.
9. **Calling BatchUpdateFindings to change RecordState.** That API does not update RecordState.
10. **Assuming BatchUpdateFindings refreshes UpdatedAt.** That API does not alter UpdatedAt.
11. **Assuming RESOLVED findings never return.** Providers can generate or reopen findings for persistent issues.
12. **Ignoring finding retention limits.** Stale active findings can be deleted after 90 days; archived findings after 30 days.
13. **Auto-remediating every Critical finding.** Some actions can cause outages or data destruction.
14. **Ignoring automation rule order.** Later rules can overwrite values set by earlier rules.
15. **Using ASFF filters for OCSF events.** Match the exact schema and event type.
16. **Measuring success solely by closed finding counts.** Measure risk reduction, recurrence, and verification success.

## 18. Self-Check Exercises

**1. How do a finding and an incident differ?**

A finding is a record of a security issue or signal. An incident is an event requiring coordinated response, investigation, and management based on impact. A finding can serve as input to declare an incident.

**2. Why is severity insufficient to determine priority?**

Severity does not fully capture resource criticality, exposure, exploitability, blast radius, or business impact.

**3. What does Workflow.Status=NOTIFIED mean?**

The team has notified the resource owner and is waiting for them to investigate/remediate.

**4. Can RecordState=ARCHIVED be used to mark a ticket closed?**

No. RecordState is managed by the finding provider and is not a customer work status.

**5. What happens when a control finding shifts from FAILED to PASSED?**

Security Hub CSPM updates the existing finding and automatically sets workflow to RESOLVED.

**6. What does the Criticality field in ASFF describe?**

The importance of the resource associated with the finding on a 0–100 scale.

**7. Which fields can BatchUpdateFindings update?**

It can update specific customer-managed fields including Confidence, Criticality, Note, RelatedFindings, Severity, Types, UserDefinedFields, VerificationState, and Workflow.

**8. Does BatchUpdateFindings alter UpdatedAt?**

No. This API does not update a finding's UpdatedAt value.

**9. Why is idempotency required when creating tickets from EventBridge?**

A single finding can emit multiple events due to provider updates or retries. Idempotency updates the existing ticket instead of creating duplicates.

**10. When should a remediation plan be used instead of separate tickets per exposure?**

When multiple exposure findings stem from the same resource and root cause, and a single change resolves or reduces risk across many findings.

**11. Does a Resolved remediation plan always mean every finding is Resolved?**

No. A plan may resolve because exposures were suppressed/archived, lowered to Informational, or lost the relevant trait; inspect individual findings.

**12. Why should you not automatically block every resource with a Critical finding?**

Findings may be unverified or blocking actions may cause outages. Require runbooks, preconditions, approvals, and impact-appropriate rollback.

**13. When should findings be exported to S3?**

When evidence must be retained longer than Security Hub CSPM's automatic retention window or for long-term historical analysis.

**14. Why must both tickets and findings be checked after remediation?**

Tickets reflect work items, while findings reflect the detecting source's evaluation. The two systems may update at different times.

**15. Can AWS Security Hub CSPM and Security Hub OCSF share the same event pattern?**

No. CSPM uses ASFF with event type Security Hub Findings - Imported; Security Hub V2 uses OCSF with event type Findings Imported V2.

## 19. Operational Checklist

- [ ] Security Hub is enabled and receiving findings from required sources across accounts/Regions.
- [ ] Delegated administrator and multi-account/multi-Region governance processes exist.
- [ ] Conventions exist for severity, resource criticality, and internal priority.
- [ ] Findings are verified, enriched, and deduplicated prior to assignment.
- [ ] Reliable owner sources exist via tags, AppRegistry, CMDB, or account inventory.
- [ ] Tickets contain finding ID, resource ARN, priority, owner, deadline, and verification criteria.
- [ ] Workflow status and RecordState are used for their intended purposes.
- [ ] Automation rules have clear criteria, reviewed ordering, and previews.
- [ ] EventBridge processing implements idempotency, retries, and dead-letter queues.
- [ ] Ticketing integrations have OAuth/secret/KMS permissions and throttling monitoring.
- [ ] Remediation includes pre-checks, approval, rollback, and audit trails.
- [ ] Control findings are verified via compliance status; other findings via providers.
- [ ] Dashboards track backlog, aging, SLAs, MTTR, recurrence, and risk reduction.
- [ ] Long-term findings are exported before retention expiration.
- [ ] Periodic review processes exist for suppressions and exceptions.
- [ ] Post-incident lessons learned and recurrence-prevention controls are captured.

## References

- [Creating and updating findings in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings.html)
- [AWS Security Finding Format (ASFF)](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings-format.html)
- [Required top-level ASFF attributes](https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html)
- [Optional top-level ASFF attributes](https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html)
- [Setting the workflow status of findings](https://docs.aws.amazon.com/securityhub/latest/userguide/findings-workflow-status.html)
- [BatchUpdateFindings for customers](https://docs.aws.amazon.com/securityhub/latest/userguide/finding-update-batchupdatefindings.html)
- [Filtering findings in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings-manage.html)
- [Understanding automation rules in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/automation-rules.html)
- [Automatically modifying and acting on findings](https://docs.aws.amazon.com/securityhub/latest/userguide/automations.html)
- [Using EventBridge for automated response and remediation](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-cloudwatch-events.html)
- [Configuring an EventBridge rule for Security Hub CSPM findings](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-cwe-all-findings.html)
- [EventBridge event formats for Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-cwe-event-formats.html)
- [Managing Security Hub CSPM for multiple accounts with AWS Organizations](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-accounts-orgs.html)
- [Declarative policies and central configuration in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/orgs-policies-and-central-config.html)
- [Understanding cross-Region aggregation in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/finding-aggregation.html)
- [Introduction to AWS Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub-v2.html)
- [Exposure findings in Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/exposure-findings.html)
- [Resources and criticality in Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/resources-adv.html)
- [Remediation plans in Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-v2-remediation-plans.html)
- [Automations in Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-v2-automations.html)
- [Automation rules in Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-v2-automation-rules.html)
- [Integrations for AWS Security Hub Jira Cloud](https://docs.aws.amazon.com/securityhub/latest/userguide/jiracloud.html)
- [Integrations for ServiceNow](https://docs.aws.amazon.com/securityhub/latest/userguide/servicenow.html)
- [Security Hub CSPM examples using AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli_securityhub_code_examples.html)
