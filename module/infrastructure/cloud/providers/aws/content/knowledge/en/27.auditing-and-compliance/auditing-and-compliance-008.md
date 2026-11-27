# AWS Audit Manager and control evidence collection

## Lesson objectives

In the CLOUD_PROVIDERS_AWS ecosystem, AWS Audit Manager supports Governance, Risk, and Compliance (GRC) activities. The service connects control requirements to operational data from AWS such as resource configurations, security findings, and change activity. As a result, engineering and audit teams can track evidence per control, review it throughout the assessment lifecycle, and prepare packages for evaluations.

After this lesson, learners can:

- Explain the relationship between frameworks, assessments, controls, and evidence in AWS Audit Manager.
- Choose appropriate evidence sources among AWS Config, AWS Security Hub CSPM, AWS CloudTrail, AWS API calls, and manual evidence.
- Design workflows to collect, review, supplement, and export control evidence.
- Recognize the limitations of automated results, especially the Inconclusive status.
- Assess the impact of AWS Audit Manager entering maintenance mode as of 30/04/2026.

> **Service status note as of 20/11/2026:** AWS has transitioned AWS Audit Manager into maintenance mode. Organizations that set up the service before 30/04/2026 can continue using it within the accounts and Regions already configured, including creating new assessments. Standalone-account customers cannot set up Audit Manager for new accounts or Regions. For customers that set up Audit Manager from the AWS Organizations management account, member accounts belonging to that same organization can still be added to assessments; it cannot be expanded to new Regions or new organizations. In maintenance mode, AWS continues fixing bugs and maintaining existing data source mappings, but does not develop new features, new frameworks, new framework versions, or new Region support. Therefore, before designing a new system, verify whether the current account is eligible to continue using Audit Manager.

## 1. Role of AWS Audit Manager

AWS Audit Manager automatically collects and organizes evidence related to control requirements in an AWS environment. The service reduces the manual effort of hunting for configuration snapshots, activity logs, and security check results across multiple places. Audit teams can inspect evidence per control, ask subject-matter experts to review it, and select appropriate items to include in an assessment report.

Audit Manager does not itself certify that an organization complies with a standard. The service assists with collecting and organizing relevant data; humans must still determine applicable requirements, inspect evidence, evaluate exceptions, and decide whether controls are operating effectively. AWS-collected evidence may also not cover all policies, procedures, and non-AWS activities required by an audit.

Key concepts:

| Component | Meaning | Role in the workflow |
|---|---|---|
| Framework | A set of controls grouped by standard, regulation, or internal requirement | Defines audit structure and scope |
| Control | A requirement or safeguard that must be demonstrated | Defines what needs to be checked |
| Assessment | An evaluation instance created from a framework, scoped to specific AWS accounts | Initiates continuous evidence collection |
| Evidence source | Source a control uses to collect data | Determines whether data comes from AWS services or users |
| Evidence | Records, check results, configuration snapshots, or documents supporting a control | Provides data for reviewers to inspect |
| Assessment report | A report generated from an assessment and selected evidence set | Shares results along with links to evidence for auditors |

A framework can be a standard framework provided by AWS or a custom framework built by the organization. Standard frameworks fit when audit requirements map to a common standard. Custom frameworks are useful when an enterprise needs to group controls around internal policies or customer requirements.

One control can use multiple data sources. For example, a data encryption control might combine AWS Config results, security checks from Security Hub CSPM, change activity recorded in CloudTrail, and manually uploaded key-management procedure documents.

## 2. Workflow from framework to report

The overall workflow consists of the following steps:

~~~mermaid
flowchart TD
    A[Audit requirement or standard] --> B[Select or create framework]
    B --> C[Create assessment and specify accounts]
    C --> D[Assessment activates controls]
    D --> E[Collect evidence from AWS sources]
    D --> F[Add manual evidence]
    E --> G[Evidence attached to control]
    F --> G
    G --> H[Owner and delegates review]
    H --> I[Select evidence for report]
    I --> J[Assessment report in Amazon S3]
~~~

Once an assessment is created, Audit Manager begins continuously collecting evidence for active controls. Collection runs according to each source's cadence: some sources record events near-continuously, some pull check results on a schedule, and some capture configuration snapshots daily, weekly, or monthly.

Evidence is mapped to the corresponding control so owners do not have to manually match every log or configuration to audit requirements. The assessment owner can assign control sets to subject-matter delegates—for example, the IAM team reviewing access permissions, the platform team reviewing network configurations, or operations reviewing backups. Delegates receive permissions only on assigned control sets and can view evidence, add comments, upload supplementary documents, and update control statuses per granted permissions.

## 3. Automated evidence sources

Audit Manager supports four main automated data source groups. Each group answers a different question, so choose sources based on the control's substance.

| Source | Data type | Collection method | Example supported question |
|---|---|---|---|
| AWS Config | Resource configuration and compliance evaluation results | Pulls results from Config rules per rule triggers | Is encryption enabled on the bucket? |
| AWS Security Hub CSPM | Security check results | Pulls results from Security Hub controls on check schedules | Does the resource violate an enabled security check? |
| AWS CloudTrail | User or service activity | Monitors supported CloudTrail events; activity evidence collected continuously | Who changed the configuration or called which API? |
| AWS API calls | Resource configuration snapshots | Calls supported AWS APIs on a daily, weekly, or monthly schedule | What is the current configuration of the resource? |

### 3.1. AWS Config

AWS Config records resource configurations and evaluates resources using Config rules. Audit Manager can retrieve rule evaluation results and attach them to the related control as compliance check evidence.

For example, a control requires Amazon S3 buckets to enable server-side encryption. An AWS Config rule checks the bucket's encryption property. Audit Manager pulls the evaluation result so reviewers see which resources meet or fail the condition.

For this source to work, the account and Region must have AWS Config properly configured, a recorder tracking the resource types to evaluate, and the corresponding rule in place. Check the list of rules supported by Audit Manager; a rule existing in AWS Config does not automatically guarantee it maps to every Audit Manager control.

### 3.2. AWS Security Hub CSPM

Security Hub CSPM aggregates results from supported security checks. Audit Manager uses Security Hub CSPM control IDs as source mappings and imports check results into the assessment.

This source fits when controls focus on resource security posture, such as encryption settings, access permissions, or foundational security practices. Results are collected on the security check schedule. Thus, when evidence appears depends on check execution schedules and integration status.

### 3.3. AWS CloudTrail

CloudTrail records API activity in an AWS account. Audit Manager can monitor supported event names and collect related activity as user activity evidence.

For example, when a principal calls an API changing a bucket's encryption configuration, CloudTrail can record the timestamp, calling identity, and corresponding event. This evidence is useful for identifying who made a change and when it occurred.

CloudTrail evidence shows that an activity was recorded; it does not itself prove the activity was properly approved or that the post-change configuration is secure. Reviewers must cross-reference change requests, approval policies, or operational documentation when the control requires it.

### 3.4. AWS API calls

With the API calls source, Audit Manager invokes a supported AWS API to capture a snapshot of resource configuration. The custom control author picks the API and collection frequency: daily, weekly, or monthly.

For example, an API reading S3 encryption configuration can provide a state snapshot at collection time. This snapshot helps prove the configuration observed at a point in time, though it does not replace historical logs of who changed the configuration.

### 3.5. AWS managed sources and customer managed sources

When creating a custom control, users can choose an AWS managed source or a customer managed source.

- **AWS managed source** is a group of sources maintained by AWS and mapped to common controls or core controls. When AWS updates a source definition, custom controls using that source receive the update accordingly. This is usually the preferred choice when a source exists and fits requirements.
- **Customer managed source** is a source defined by the organization itself, such as a custom AWS Config rule or a specific API call. The organization is responsible for maintaining mappings, verifying correctness, and updating the source when requirements change.

A control can combine multiple sources. Do not add sources merely to inflate evidence counts; each source must have a clear purpose and provide data relevant to the control requirement.

## 4. Manual evidence

Not every control requirement can be proven by AWS configuration state. Some requirements involve human activities, governance documents, or non-AWS environments. Audit Manager supports adding such evidence in three ways:

1. **Import from Amazon S3:** used when documents, reports, or artifacts are already stored in a bucket.
2. **Upload from browser:** used when documents reside on a local machine or internal network, such as scanned meeting minutes or signatures.
3. **Enter text responses:** used when a control is an assessment question and suitable evidence is an explanation or text-based information.

For example, a control requires the organization to have an access-grant approval workflow. AWS can provide evidence of IAM configuration and policy creation/change activity. However, approval procedures, lists of authorized approvers, access review minutes, and employee training records may need to be provided manually.

Manual evidence can also come from on-premises systems, SaaS platforms, or other cloud environments. When adding documents, attach them to the exact assessment control and clearly describe which requirement they prove, which period they cover, and which department is responsible.

Do not upload sensitive secrets or personally identifiable information (PII) as manual evidence. Before uploading, redact unnecessary data, verify access permissions, and confirm the document can be shared with the right audit group.

## 5. Designing a control with complete evidence

A good control starts with a verifiable requirement. Translate broad requirements into specific questions:

- Which targets are in scope?
- What state or behavior must be demonstrated?
- Must evidence show state at a point in time or change history?
- Does the requirement include policies, approvals, or human activities?
- Who will review the evidence and how often?

Example: **Controlling data encryption in Amazon S3**.

| Aspect to prove | Suitable source | Evidence obtained | What the reviewer must confirm |
|---|---|---|---|
| In-scope buckets have encryption enabled | AWS Config or Security Hub CSPM | Configuration check results | Do rules/controls cover the right buckets and Regions? |
| Encryption settings at check time | AWS API calls | Encryption configuration snapshot | Does the snapshot include all required attributes? |
| Configuration change activity | AWS CloudTrail | Change events, identity, and timestamp | Do changes have matching tickets and approvals? |
| Key management procedures and exceptions | Manual evidence | Policies, procedures, review minutes | Are documents still valid and applied to the right systems? |

This example shows one data source usually proves only part of a control. Config or Security Hub can show technical state; CloudTrail helps track activity; manual documents prove governance processes. Owners must inspect these pieces together before concluding a control operates effectively.

When creating a custom control, clearly document its objective, testing method, evidence sources, required frequency, and types of supplementary manual documents. If using a customer managed source, record who is responsible for maintaining mappings and testing sources when AWS updates APIs or rules.

## 6. Reviewing evidence and understanding result statuses

After evidence is collected, owners must review its contents rather than relying solely on aggregate status. For each piece of evidence, check:

- **Scope:** right account, Region, service, resource, and control under evaluation.
- **Timing:** evidence falls within the audit period and reflects the appropriate timestamp.
- **Source:** identify whether data came from Config, Security Hub CSPM, CloudTrail, API calls, or manual upload.
- **Completeness:** whether the data includes the attributes needed to verify the requirement.
- **Relevance:** whether the evidence proves the control's exact requirement or merely provides adjacent information.
- **Exceptions:** non-applicable resources, approved changes, or missing data must be explained and documented.

For compliance check evidence from AWS Config or Security Hub CSPM, results can show resources as compliant or non-compliant. For CloudTrail, API calls, and manual evidence, Audit Manager typically lacks an automated compliance evaluation mechanism and may display **Inconclusive**.

**Inconclusive does not mean failure.** This status indicates Audit Manager could not automatically evaluate the evidence via compliance check logic. A subject-matter reviewer must open the evidence details, compare them against the requirement, and record a conclusion. If AWS Config or Security Hub CSPM is not enabled or has no evaluation data yet, related evidence may also appear as Inconclusive.

A review workflow can assign roles as follows:

| Role | Responsibility |
|---|---|
| Audit owner | Manages assessment, scope, control sets, delegations, and reports |
| Delegate | Reviews assigned control sets, comments, and adds evidence per permissions |
| System owner | Explains architecture, configurations, changes, and exceptions |
| GRC or internal audit team | Cross-references evidence against standards, policies, and audit periods |

Document reasons for accepting exceptions, compensating evidence, approvers, and remediation deadlines. A compliant configuration status does not by itself prove that all related processes are also followed.

## 7. Selecting evidence and generating an assessment report

Newly collected evidence does not automatically appear in an assessment report. The audit owner must select which evidence to include in the report. You can add entire evidence folders or select individual evidence items within a folder.

Report preparation workflow:

1. Open the assessment and inspect the control sets to report on.
2. Browse evidence folders by control and time period.
3. Open detailed evidence and verify source, timestamp, resource, and content.
4. Add manual evidence or comments for controls needing extra explanation.
5. Select appropriate evidence folders or evidence items to add to the assessment report.
6. Review the selected evidence list before generating the report.
7. Generate the assessment report and save it to the Amazon S3 bucket configured as the report destination.
8. Download the report from Audit Manager if needed and verify access permissions to the report and referenced evidence.

The report summarizes the assessment and provides links to evidence folders organized by control. Selecting evidence is an important control step: the report must include the right relevant documents, the right assessment period, and sufficient context for recipients to understand outcomes.

The bucket storing reports must be governed like an audit data repository. Apply least-privilege access, data encryption, access monitoring, and retention policies aligned with internal requirements. Share reports only with authorized personnel and verify access permissions to the S3 objects referenced in the report.

## 8. Safe operations and common troubleshooting

### 8.1. No evidence collected

Check in order:

- Are the assessment and controls active, or have they been moved to inactive?
- Are the accounts and Regions included in the assessment scope?
- Is AWS Config or Security Hub CSPM enabled and producing data?
- Are the Config recorder, rule, or Security Hub control active and on Audit Manager's supported list?
- Is CloudTrail recording the events to track and are those events on the supported list?
- Is the selected API call supported, authorized with required permissions, and set to an appropriate collection schedule?
- Are IAM permissions and service-linked roles still valid?

### 8.2. Evidence in Inconclusive state

Identify the evidence source first. If the source is CloudTrail, API calls, or manual upload, Inconclusive can be normal because Audit Manager does not auto-evaluate that content. If the source is Config or Security Hub CSPM, verify service enablement, rules/controls, evaluation status, and returned data. Afterward, the reviewer must manually evaluate it against the control criteria.

### 8.3. Evidence exists, but report is missing data

Check the assessment report selection tab. Newly collected evidence is not automatically added to the report; the audit owner must select folders or items to include. Also verify date filters when browsing folders, as the interface may default to showing recent time windows.

### 8.4. Permissions and data protection

Use role-based IAM policies separating assessment management permissions from read-only or control-set review permissions. Delegates should only be assigned controls within their domain expertise. Restrict access to buckets storing reports and evidence, enable appropriate data protections, and maintain approval history for significant changes.

Do not use manual evidence to store secrets, credentials, tokens, or unnecessary PII. For documents supplied to auditors, prepare versions with out-of-scope information removed and clearly define who is permitted to view them.

## 9. Guidance after Audit Manager moved to maintenance mode

Because the current date is 20/11/2026, choosing Audit Manager must begin by checking existing deployment status:

- **Organizations using Audit Manager before 30/04/2026:** can continue using it within already configured accounts and Regions; if configured in the AWS Organizations management account, member accounts belonging to that same organization can be added to assessments within AWS's published limits.
- **New organizations or accounts that have not set up Audit Manager:** cannot begin deploying the service in the standard way after 30/04/2026.
- **Need to check AWS resource compliance posture:** consider AWS Config Conformance Packs. They deploy detective controls as Config rules, can be managed at account or AWS Organizations levels, and provide dashboards plus per-resource status.
- **Need full audit package management:** perform a gap assessment before transitioning. Conformance Packs are not an equivalent replacement for Audit Manager Frameworks. AWS Config focuses on Config rule results and Configuration Items; it does not collect CloudTrail logs, Security Hub controls, or call service APIs like Audit Manager does. Nor does it provide the same workflow for gathering, reviewing, and sharing non-technical evidence such as policies, interviews, or approval records. Several Audit Manager frameworks—including SOC 2 and GDPR in AWS documentation at the time of writing—do not have equivalent Conformance Packs.

When transitioning, build a mapping table matching each control to a corresponding Config rule or Conformance Pack, clearly noting which parts can be checked automatically and which still require separate documentation or processes. You can use AWS Config Advanced Queries to export current Configuration Items as CSV or JSON; if configuration history is needed, consider the `GetResourceConfigHistory` API. For broader evidence management and audit workflow requirements, evaluate an appropriate GRC solution rather than assuming Conformance Packs cover an entire standard.

## 10. Recommended practice

Suppose an organization is preparing an audit of data protection controls for an application running on AWS. The team needs to prove S3 buckets are encrypted, configuration changes are tracked, and key management procedures have approvers.

A reasonable implementation approach:

1. Select a framework matching audit requirements and identify AWS accounts in scope.
2. Create an assessment if current accounts and Regions are eligible to use Audit Manager.
3. Identify controls related to data encryption and pick AWS managed sources if available and suitable.
4. Add Config or Security Hub CSPM sources to check configurations, CloudTrail to track changes, and API calls to snapshot configurations when needed.
5. Collect manual documentation for key management procedures, change approvals, and exception handling.
6. Assign control sets to the platform and security teams for review; the audit owner tracks missing or Inconclusive evidence.
7. Reconcile results against the audit period, explain exceptions, and select only verified evidence for the report.
8. Store reports and evidence in S3 with appropriate access controls, encryption, and retention periods.

If the organization cannot set up Audit Manager, convert the problem into a list of technical checks deployable with AWS Config Conformance Packs, while separately defining requirements for CloudTrail, Security Hub, procedural documentation, and approvals. This maintains visibility into resource compliance posture while clearly calling out areas needing another GRC process or tool.

## Conclusion

AWS Audit Manager connects frameworks, assessments, controls, and evidence to assist audit preparation on AWS. Output quality depends on selecting the right controls, configuring the right data sources, adding manual evidence where needed, and having qualified reviewers inspect each piece of evidence. The Inconclusive status must be evaluated based on content and data source, rather than automatically treated as an error or failure.

Since 30/04/2026, Audit Manager has been in maintenance mode, restricting setup for new accounts, Regions, or organizations. Therefore, solution designers should verify current eligibility and evaluate AWS Config Conformance Packs alongside other GRC tools according to actual control scope.

## References

- [What is AWS Audit Manager?](https://docs.aws.amazon.com/audit-manager/latest/userguide/what-is.html)
- [Understanding AWS Audit Manager concepts and terminology](https://docs.aws.amazon.com/audit-manager/latest/userguide/concepts.html)
- [Supported data source types for automated evidence](https://docs.aws.amazon.com/audit-manager/latest/userguide/control-data-sources.html)
- [Managing assessments in AWS Audit Manager](https://docs.aws.amazon.com/audit-manager/latest/userguide/assessments.html)
- [Adding manual evidence in AWS Audit Manager](https://docs.aws.amazon.com/audit-manager/latest/userguide/upload-evidence.html)
- [Preparing an assessment report in AWS Audit Manager](https://docs.aws.amazon.com/audit-manager/latest/userguide/generate-assessment-report.html)
- [AWS Audit Manager availability change](https://docs.aws.amazon.com/audit-manager/latest/userguide/audit-manager-availability-change.html)