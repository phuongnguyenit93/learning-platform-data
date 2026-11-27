# Amazon Detective and Event Relationship Investigation

In the AWS ecosystem, a security incident often leaves traces across multiple places: login and API activity in AWS CloudTrail, network connections in VPC Flow Logs, Kubernetes workload activity in EKS audit logs, and alerts from Amazon GuardDuty. Each source shows part of the story. When investigators must manually piece together fragmented records, they easily miss links between identities, IP addresses, sessions, hosts, and affected resources.

Amazon Detective shortens that process. The service collects and analyzes security data from supported sources, builds a behavior graph for the AWS environment, and presents entities and their relationships over time. Investigators can start from a finding, trace related entities, compare current activity against typical behavior, and form hypotheses about root cause and blast radius.

This lesson falls within the scope of CLOUD_PROVIDERS_AWS: exploring how AWS services coordinate in security monitoring and response. The focus is on using Amazon Detective to investigate event relationships, combining context across IAM, VPC networking, compute resources, and log sources. Detective supports analysis; decisions to isolate, revoke permissions, or recover systems still rely on the organization's incident response procedures.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the role of Amazon Detective in AWS security monitoring and incident response workflows.
- Describe how Detective builds a behavior graph from security data and represents entities, activities, and relationships.
- Trace a GuardDuty finding to investigate related identities, IPs, sessions, and resources.
- Read entity profiles, time scopes, anomalous activity, and finding groups to build an incident timeline.
- Distinguish Detective's responsibilities from GuardDuty, AWS CloudTrail, VPC Flow Logs, and AWS Security Hub.
- Recognize data limitations, Regional scope, access permissions, and costs when deploying Detective.

## 2. What Problems Does Amazon Detective Solve?

### 2.1. Fragmented Logs Slow Down Investigations

Suppose GuardDuty detects an IAM role exhibiting unusual API activity. To confirm the incident, the security team must answer several questions:

1. Which identity performed the action? Was it an IAM user, an assumed role session, or an AWS service?
2. From which IP address, at what time, and in which Region did the session originate?
3. Which APIs did that identity call before and after the finding?
4. Did the session interact with EC2 instances, S3 buckets, EKS workloads, or other resources?
5. Does this behavior differ from normal activity for that identity or resource?
6. Are there other findings associated with the same IP, identity, or resource?

Inspecting individual CloudTrail events, network records, and separate findings forces investigators to connect the dots manually. This takes time and risks overlooking activity occurring prior to the alert timestamp.

### 2.2. Detective Provides Context and Relationships

Amazon Detective analyzes data from supported sources to build a behavior graph. The graph models entities in the AWS environment, their activities, and observable relationships. Detective also applies statistical analysis and machine learning to help investigators understand activity over time, including comparisons against behavioral baselines.

For instance, when inspecting an IAM role, investigators can trace role sessions used, associated IP addresses, API calls, and the resources those sessions interacted with. When inspecting an IP, they can check which identities or workloads communicated with that IP within the available data window.

Detective helps answer the question "how are these events and entities related?". It neither automatically concludes that every unusual activity is an attack nor replaces investigators in verifying evidence.

## 3. Behavior Graph and Input Data

### 3.1. What Is a Behavior Graph?

A behavior graph is Detective's analytical model for an AWS environment within a Region. The graph is built from data of the account that enabled Detective and member accounts shared into the administrator graph. Detective analyzes activity over time and links data to relevant entities.

Key characteristics to remember:

- **Per Region:** Detective operates at Regional scope. When investigating a multi-Region environment, ensure Detective is enabled and required data is present in each relevant Region.
- **Per account:** A graph can include an administrator account and member accounts. Multi-account organizations can designate a delegated Detective administrator account to coordinate investigation scope.
- **Accumulated data:** Analytical value depends on collection duration and data source coverage. A newly enabled graph may not yet have enough history to form a rich behavioral picture.
- **Not a universal log archive:** Detective analyzes only the data sources it supports. For deep forensics, operators still need access to raw log sources or organizational log archives.

### 3.2. Primary Data Sources

Core data sources commonly encountered in AWS investigations include:

| Source | Information Provided | Investigative Value |
|---|---|---|
| AWS CloudTrail | AWS management events and API activity, calling identity, timestamp, Region, access source, and related resources | Reconstructs the action sequence of a user, role, or service session |
| VPC Flow Logs | VPC IP network flow metadata such as source/destination addresses, ports, protocols, and flow status | Identifies network links, abnormal traffic, and connections between workloads and external addresses |
| EKS audit logs | Kubernetes API calls in EKS clusters when configured and supported | Investigates actions targeting clusters, workloads, and Kubernetes resources |
| Amazon GuardDuty findings | Security detections generated by GuardDuty | Provides a starting point for investigation and context on detected threats |

Data source scope and integration capabilities may vary by feature, Region, and account configuration. During deployment, check the Detective configuration page in the target Region to confirm which sources are being ingested and enabled.

CloudTrail, VPC Flow Logs, and EKS audit logs provide distinct perspectives. CloudTrail describes AWS control-plane activity; VPC Flow Logs describe network flows; EKS audit logs describe Kubernetes API requests. GuardDuty adds security findings generated from the data it analyzes. Combining these views helps investigators understand both the actions and the path of suspicious activity.

### 3.3. Entities and Relationships

Depending on observed data types and activity, Detective can link entities such as:

- AWS accounts.
- IAM users, IAM roles, and assumed role sessions.
- IP addresses.
- EC2 instances.
- S3 buckets.
- EKS clusters and supported Kubernetes entities.

Consider an illustrative relationship chain:

~~~text
External IP address
        |
        | initiates access activity
        v
IAM role session
        |
        | performs API calls
        v
S3 bucket
        |
        | appears in same activity chain
        v
GuardDuty finding
~~~

This is a conceptual illustration, not a guarantee that every relationship type appears as a dedicated graph edge. Detective can only link what its source data and analytical models support. Investigators should open each entity profile and examine detailed activity rather than inferring relationships solely from a diagram.

### 3.4. Baselines and Anomalies

A single event is rarely enough to draw conclusions. For example, a role calling `ListBuckets` may be routine administrative behavior. However, if that role normally operates only from a workload inside a VPC and suddenly appears from an unfamiliar IP at an unusual hour calling sensitive APIs, that sequence warrants scrutiny.

Detective provides charts and metrics allowing investigators to view activity over time, observe frequency shifts, and compare against baseline behavior. Pay attention to:

- Sudden spikes in activity or activity appearing at unusual times.
- New IPs, Regions, user agents, or access sources in an entity's context.
- An identity beginning to access resource types it has never interacted with before.
- Multiple findings clustering around an identity, IP, or resource.
- Activity before and after the finding timestamp that may indicate reconnaissance, privilege escalation, or data access.

Baselines are analytical signals, not allow or deny policies. Unusual activity may be legitimate during a deployment, test, or emergency operation. Always cross-check against change schedules, system owners, and raw evidence.

## 4. Investigation Workflow with Amazon Detective

### 4.1. Prepare Observational Scope

Before investigating, verify the following prerequisites:

1. Detective is enabled in the Region containing the resources or activity under investigation.
2. Relevant AWS accounts have joined the appropriate behavior graph.
3. Required data sources are being collected, such as CloudTrail, VPC Flow Logs, and EKS audit logs if EKS workloads exist.
4. GuardDuty is enabled if investigations start from GuardDuty findings.
5. Investigators hold necessary IAM permissions to view behavior graphs, findings, and entity profiles.

In AWS Organizations environments, designate the delegated Detective administrator account, member onboarding process, and security team responsibilities. Centralized governance supports cross-account investigations, while viewing permissions should still be scoped by job role.

### 4.2. Starting from a Finding

A common workflow starts from a GuardDuty finding:

1. Open the finding in GuardDuty or open the corresponding finding in Detective.
2. Confirm the finding type, timestamp, Region, account, and cited entities.
3. Set a time window wide enough to inspect activity before and after detection.
4. Open linked entities, such as an IAM role, IP, or EC2 instance.
5. Examine each entity's activity and any other linked findings.

Do not inspect only the exact minute the finding was created. An attacker may have compromised credentials earlier, probed permissions prior to acting, or continued operating after the alert fired. The time scope should be broad enough to reconstruct the event chain yet narrow enough to keep investigators focused on relevant signals.

### 4.3. Reading Entity Profiles

An entity profile aggregates information and activity charts associated with an entity. Depending on entity type, investigators can view:

- Identity and identifying attributes of the entity.
- API activity or network activity over time.
- Associated IPs, accounts, roles, or resources.
- Findings linked to the entity.
- Activity frequency shifts relative to baseline behavior.

When viewing an IAM role, examine role sessions, access sources, and called APIs. When viewing an IP, identify which identities or workloads interacted with that IP. When viewing an EC2 instance, combine network activity with instance management actions in CloudTrail. Each view answers part of the story.

### 4.4. Building a Timeline

A strong timeline shows the sequence and relationships among events. For example:

| Illustrative Time | Event | Investigative Question |
|---|---|---|
| 09:02 | A role session is used from an unfamiliar IP | Which workload or operator owns this session? |
| 09:04 | Session calls resource enumeration APIs | Is this routine behavior for the role? |
| 09:07 | Session accesses a sensitive S3 bucket | Is this bucket within the role's intended scope? |
| 09:10 | GuardDuty generates a related finding | Which signals triggered the finding and what else is linked? |
| 09:14 | Additional activity appears from the same IP | Is this a continuing session or another identity? |

Timestamps in the table merely illustrate the method. In real investigations, use timestamps from source data, normalize time zones, and cross-check against times displayed in each service.

### 4.5. Pivoting from One Entity to Related Entities

After identifying the focal entity, follow meaningful relationships:

- From finding to IAM principal or role session.
- From role session to source IP and API call sequence.
- From IP to other identities or workloads that communicated with that IP.
- From EC2 instance to network flows and instance management actions.
- From EKS activity to the associated cluster or workload.

When an IP connects to multiple roles, check whether it is a NAT gateway, corporate proxy, VPN, or shared service. A shared IP alone is insufficient to conclude multiple identities are controlled by the same actor. Likewise, two events occurring close in time are not necessarily causally related.

### 4.6. Verifying Hypotheses with Raw Data

Detective helps uncover links and guide investigations. When confirming a specific action, cross-check against raw sources:

- Use CloudTrail event history or saved trails to verify APIs, principals, request parameters, and outcomes.
- Use VPC Flow Logs to check network flows, addresses, ports, and timestamps.
- Use EKS audit logs to verify Kubernetes API requests.
- Check relevant IAM configurations, resource policies, security groups, and deployment schedules.
- Consult workload owners to confirm legitimate operational activity.

If evidence preservation is needed, follow your organization's evidence handling procedures: keep records intact, and document retrieval time, source, scope, and collector. Never modify or delete raw logs during an investigation.

### 4.7. Handing Off Results to Incident Response

Once sufficient evidence is gathered, the response team can decide appropriate actions, such as disabling an exposed access key, tightening a role trust policy, blocking network traffic, isolating an EC2 instance, or restricting access to data resources. Specific actions must reflect impact severity, responder authority, and incident approval workflows.

Amazon Detective focuses on investigation and analysis. It does not replace response execution tools. Coordinate with IAM, EC2, VPC security groups, AWS Systems Manager, AWS Security Hub, EventBridge, or your organization's SOAR platform to execute and track remediation measures.

## 5. Example: Investigating a Suspicious IAM Role Session

### 5.1. Context

An internal application uses an IAM role to read data from S3. GuardDuty detects suspicious activity involving the role's credentials. The security team must determine whether this is a legitimate deployment or an abused session.

Illustrative initial details:

- Account: application account in AWS Organizations.
- Region: Region running the application.
- Identity: an assumed role session of the application role.
- Access source: an IP never seen before in the role's routine activity.
- Resource: an S3 bucket containing internal data.

### 5.2. Inspecting the CloudTrail Event

A CloudTrail event might contain important fields as shown in the abbreviated example below:

~~~json
{
  "eventTime": "2026-11-20T02:04:12Z",
  "eventSource": "s3.amazonaws.com",
  "eventName": "PutBucketPolicy",
  "awsRegion": "ap-southeast-1",
  "sourceIPAddress": "198.51.100.24",
  "userIdentity": {
    "type": "AssumedRole",
    "arn": "arn:aws:sts::111122223333:assumed-role/AppDataReader/session-example",
    "sessionContext": {
      "sessionIssuer": {
        "arn": "arn:aws:iam::111122223333:role/AppDataReader"
      }
    }
  },
  "requestParameters": {
    "bucketName": "internal-data-bucket"
  },
  "recipientAccountId": "111122223333"
}
~~~

The IP and account values in the example are illustrative only. When analyzing, examine:

- **eventTime:** when the event occurred; normalize time zones when correlating across sources.
- **eventSource and eventName:** the service and API invoked.
- **awsRegion:** Region handling the operation.
- **sourceIPAddress:** source address recorded by CloudTrail; could be a NAT, proxy, or intermediary service IP.
- **userIdentity.type and arn:** identity type and ARN of the session that executed the action.
- **sessionIssuer.arn:** parent role that issued the assumed role session.

### 5.3. Tracing Relationships in Detective

The investigator opens the finding, inspects the role and IP, and sets a time range surrounding the event. Reasoning steps might proceed as follows:

1. **Check the role:** Does this role normally call S3 APIs? Did activity spike or appear outside operational windows?
2. **Check the IP:** Which roles or workloads has this IP interacted with previously? Is it a legitimate NAT gateway or VPN egress IP?
3. **Check the API sequence:** Prior to PutBucketPolicy, were there unusual AssumeRole or management actions? Afterward, were there GetObject calls, bucket policy changes, or other sensitive actions?
4. **Check the resource:** Does the bucket belong to the application served by the role? Did the bucket policy change around that time?
5. **Check related findings:** Are other findings attached to the same role, IP, or resource?
6. **Cross-check changes:** Does a deployment ticket, operational task, or network change explain the source IP and timing?

Conclusions can branch two ways. If the IP is a newly deployed NAT gateway, the API activity matches a change schedule, and no out-of-scope access appears, the team can document this as legitimate activity after verification. If the IP does not belong to trusted infrastructure, the role session acted outside its function, and signs of unusual data access exist, the team must expand the investigation and consider isolating access.

### 5.4. Documenting Findings

An investigation record should include:

| Field | Content to Document |
|---|---|
| Finding ID | Finding ID or type and detecting service |
| Scope | Account, Region, timeframe |
| Focal entities | Role, session, IP, instance, or resource |
| Event sequence | Verified activities in chronological order |
| Evidence | References to CloudTrail, VPC Flow Logs, EKS audit logs, and related data |
| Assessment | Legitimate activity, suspicious, or confirmed incident; state confidence level |
| Actions | Measures taken, owner, and timestamp |
| Next steps | Open questions, systems to inspect, and follow-up deadline |

Distinguish clearly between observed events, hypotheses, and verified conclusions. This documentation practice helps subsequent responders continue investigating without mistaking speculation for evidence.

## 6. Finding Groups and Investigating Multiple Findings

An incident can generate multiple findings at different times or across multiple entities. Detective groups related findings into a finding group so investigators can inspect them in shared context.

When analyzing a finding group:

1. Review the constituent findings and alerted behavior types.
2. Identify shared entities such as IPs, roles, EC2 instances, or resources.
3. Compare timestamps across findings to determine operational sequence.
4. Open entity profiles to inspect activity beyond the grouped findings.
5. Verify whether the finding group stems from one behavioral chain or merely overlaps on an attribute like a shared IP.

Finding groups reduce isolated alert-by-alert triage. However, a finding group is an investigative lead suggesting correlation, not conclusive proof that all findings share a single root cause or actor.

## 7. Detective Coordinating with Other AWS Services

Each service plays a distinct role in the monitoring and response chain:

| Service | Primary Role | How It Coordinates with Detective |
|---|---|---|
| Amazon GuardDuty | Detects threats from supported data and signals | Supplies findings as starting points; Detective adds context and entity relationships |
| AWS CloudTrail | Records AWS API activity and account events | Provides evidence of who called which API, when, and from where |
| VPC Flow Logs | Records VPC network flow metadata | Adds visibility into connections between workloads and IP addresses |
| Amazon Security Hub | Aggregates and manages security findings from multiple sources | Supports centralized posture and finding management; can hand off investigations to appropriate tools |
| AWS Config | Records configurations and configuration changes of supported resources | Helps verify resource state or configuration changes around incident time |
| AWS Systems Manager | Operates and manages supported nodes | Can support verification or remediation tasks once responders decide on action |
| Amazon EventBridge | Routes events between services | Can trigger workflows or notifications when matching findings appear |

A helpful way to remember the workflow:

- GuardDuty detects threat signals.
- Detective investigates relationships and behavioral context.
- CloudTrail, VPC Flow Logs, and EKS audit logs provide raw activity evidence.
- Security Hub aggregates findings and tracks security posture.
- Operational services or SOAR systems execute approved response actions.

~~~mermaid
flowchart TD
    A[CloudTrail] --> D[Amazon Detective]
    B[VPC Flow Logs] --> D
    C[EKS audit logs] --> D
    G[Amazon GuardDuty findings] --> D
    D --> E[Behavior graph]
    E --> F[Entities and relationships]
    F --> H[Investigate and build timeline]
    H --> I[Verify with raw logs]
    I --> J[Assess blast radius and impact]
    J --> K[Organizational response workflow]
~~~

## 8. Deploying and Operating in Multi-Account Environments

### 8.1. Choosing an Administrator Account

In multi-account environments, the security team should agree on the Detective administrator account and delegation flow in AWS Organizations. The administrator account manages adding member accounts to the behavior graph per organizational structure. Clearly define who may modify settings, who may investigate, and who may execute response actions.

Avoid granting broad Detective administrative privileges to everyone who only needs to view findings. Separate graph management, investigative data viewing, and AWS resource modification permissions.

### 8.2. Planning by Region

Detective is Regional in scope. For workloads deployed across multiple Regions:

- List Regions hosting critical resources and where GuardDuty detects issues.
- Enable Detective in the Regions requiring investigation.
- Verify member accounts and data sources in each Region.
- Include Region and account mappings in on-call runbooks so responders open the right graph.
- Verify access and data ingestion after adding accounts or changing configurations.

Do not assume enabling Detective in one Region automatically generates investigative data for every other Region.

### 8.3. IAM Permissions and Separation of Duties

Apply IAM policies following least privilege. Analysts may need permissions to read graphs, findings, and entity profiles. Service administrators need permissions to configure graphs or manage members. Responders may need separate permissions on IAM, EC2, VPC, or data services to handle incidents.

Separating these permission groups prevents an analyst account from arbitrarily modifying production resources. Review Detective access periodically, especially when personnel change teams or rotate off incident response duties.

### 8.4. Verifying Data Coverage

A graph can be active yet still lack context if critical data sources are disabled or relevant accounts have not joined. Maintain an operational checklist:

- Detective is enabled in required Regions.
- Critical AWS accounts are included in graph scope.
- Required data sources are actively collected.
- GuardDuty findings are accessible within expected investigation workflows.
- Security teams have appropriate access permissions.
- Procedures for opening findings, investigating, and preserving evidence have been rehearsed.

Whenever accounts, Regions, VPCs, or EKS clusters change, re-evaluate data coverage rather than waiting for an incident.

## 9. Costs, Limitations, and Interpreting Results

### 9.1. Monitoring Costs

Detective costs depend on the volume of data processed by the service and Regional usage scope. When planning deployment:

- Estimate the number of accounts, Regions, and workloads brought into investigative scope.
- Track Detective usage and costs in AWS Billing and Cost Management.
- Evaluate which data sources provide genuine investigative value for your workloads.
- Include monitoring costs in security budgets and periodic review processes.

Do not hardcode fixed prices in operational runbooks because pricing and billing dimensions can change. Check the Amazon Detective pricing page at deployment time against your target Regions.

### 9.2. Data Limitations

Detective analyzes only the sources and activity types it supports. If CloudTrail, VPC Flow Logs, or EKS audit logs lack required data, the graph cannot reconstruct missing activity on its own. Newly ingested data also takes time to be collected and analyzed.

Additionally, Detective is scoped by Region and account. A cross-Region or cross-account investigation is only complete when all necessary scopes are configured properly.

### 9.3. Do Not Confuse Correlation with Causation

Two entities exhibiting activity near each other in time or appearing together in a finding group does not prove one controls the other. An IP may represent a NAT gateway, proxy, or shared infrastructure. A role may be used by multiple workloads by design.

Combine the following factors before drawing conclusions:

- Chronological sequence and ordering of events.
- Identity, session issuer, and access source.
- Specific APIs or network activity.
- IAM permissions and resource policies.
- Deployment, change, and operational task schedules.
- Raw evidence from logging systems.

## 10. Common Investigation Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Looking only at the finding timestamp | Misses preparatory or follow-on activity | Expand the time window and build a timeline |
| Assuming an unfamiliar IP is always malicious | Misclassifies new NATs, VPNs, or proxies | Cross-check network diagrams and IP ownership |
| Inspecting only the role without the session | Fails to identify which specific session acted | Inspect assumed role session, session issuer, and timing |
| Overlooking accounts or Regions | Graph misses linked entities | Confirm graph coverage across each account and Region |
| Treating a finding group as proof | May conflate unrelated activity sharing an attribute | Inspect each finding and raw evidence |
| Believing Detective replaces raw logs | Lacks granular details needed for verification | Cross-check CloudTrail, VPC Flow Logs, and EKS audit logs |
| Remediating immediately without verification | May disrupt legitimate workloads | Assess impact, follow response workflows and approvals |

## 11. Quick Investigation Checklist

When receiving a finding requiring investigation, follow this checklist:

1. Confirm account, Region, finding ID, and timestamp.
2. Open the finding in Detective and select an appropriate time window.
3. Identify focal entities: principal, role session, IP, instance, cluster, or data resource.
4. Inspect each entity's profile and baseline activity.
5. Trace relationships to connected entities.
6. Construct a timeline from verifiable events.
7. Check other related findings and finding groups.
8. Cross-check evidence with raw logs and change schedules.
9. Assess blast radius, confidence level, and remaining open questions.
10. Document findings and hand off to the appropriate response workflow.

## 12. Conclusion

Amazon Detective helps security teams understand a finding in broader context by linking data, entities, and activity over time in a behavior graph. Its greatest value is enabling investigators to trace relationships across identities, IPs, workloads, and resources to reconstruct event chains and determine inspection scope.

To use Detective effectively, organizations must enable the service in the right Regions, enroll the right accounts in the graph, ensure key data sources are collected, and grant appropriate investigative permissions. Investigators must check baseline behavior, verify correlations against raw logs, and document evidence before reaching conclusions. Following analysis, containment, credential revocation, or system recovery actions are executed through response workflows and corresponding AWS services.

By combining GuardDuty for detection, Detective for investigation, CloudTrail and VPC Flow Logs for verification, and operational tools for remediation, teams can move from isolated alerts to an evidence-based, auditable response process.
