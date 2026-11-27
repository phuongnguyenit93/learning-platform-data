# AWS Health, Operational Notifications, and Incident Management

## Learning Objectives

After this lesson, learners will be able to:

- Distinguish AWS Health, AWS Health Dashboard, AWS Support Center, Amazon EventBridge, AWS User Notifications, and AWS Systems Manager OpsCenter.
- Distinguish public service events from account-specific events; interpret category, scope, status, and actionability of an AWS Health event.
- Monitor AWS service health, resource events, planned lifecycle changes, and security notifications across one or more AWS accounts.
- Create EventBridge rules to filter AWS Health events by service, event category, Region, actionability, and persona.
- Design notification routes via AWS User Notifications, Amazon SNS, SQS, Lambda, Amazon Q Developer chat integrations, or ITSM/on-call systems.
- Handle at-least-once delivery, duplicate events, backup Regions, event pagination, and the difference between event Region and affected Region.
- Enable organizational view in AWS Organizations and delegate administrator permissions.
- Understand AWS Health API access prerequisites, active/passive endpoint usage, and paginated event retrieval.
- Create and manage OpsItems in Systems Manager OpsCenter; link resources, operational data, deduplication, and runbooks.
- Automate responses to scheduled changes using Systems Manager Automation with appropriate IAM roles and guardrails.
- Build an incident response workflow covering detection, triage, declaration, communication, mitigation, recovery, and post-incident review.
- Understand AWS Systems Manager Incident Manager lifecycle changes and choose suitable options for new or existing customers.

**Module context:** This lesson belongs to the **Systems Manager Operations** chapter in `CLOUD_PROVIDERS_AWS`. The AWS ecosystem spans Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless. Planned maintenance, an AWS service issue, a resource fault, or a security notice can impact multiple components. AWS Health provides the signal; the notification pipeline routes it to the right people; Systems Manager and incident response processes track and resolve the operational work.

> **Scope and service milestones:** Content reflects AWS documentation as of November 2026. AWS Health email delivery migrated to AWS User Notifications effective December 15, 2025. AWS Systems Manager Incident Manager stopped onboarding new customers effective November 7, 2025; accounts that enabled the service prior to that date can continue using it. Verify your account's Support plan, Region, service availability, and pricing before deployment.

## 1. The Problem: AWS Sends Alerts, but Who Acts?

A workload runs on EC2, RDS, Lambda, and SQS. AWS notifies that an EC2 instance is scheduled for retirement; meanwhile, RDS has planned maintenance and an AWS Region is experiencing an operational issue. If operations teams only read scattered emails, they may miss deadlines, lose track of affected resources, or fail to distinguish an AWS issue from an application bug.

A sound operational process must answer:

- Does the event belong to an AWS service, a specific resource, or an account?
- Which Region, account, and resource does the event affect?
- Is this an ongoing issue, an account notification, an investigation, or a scheduled change?
- Does the event require action? What is the deadline?
- Who owns the response: operations, security, or billing?
- Did the notification reach the right owner and get acknowledged?
- Which safe actions can be automated?
- If automation fails, who takes over and recovers?

~~~mermaid
flowchart TD
    Health[AWS Health event] --> Filter[EventBridge / User Notifications]
    Filter --> Route[Route by service, category, persona]
    Route --> Notify[Email / Chat / Push / ITSM]
    Route --> Ops[Systems Manager OpsCenter]
    Route --> Auto[SSM Automation]
    Notify --> Team[On-call / Service owner]
    Ops --> Triage[Triage and assign]
    Auto --> Verify[Verify automated action]
    Team --> Incident[Incident response]
    Triage --> Incident
    Verify --> Incident
    Incident --> Recover[Mitigate / Recover]
    Recover --> Review[Post-incident review]
~~~

AWS Health provides information about events affecting AWS services/resources. It does not replace your organization's assignment, paging, incident command, communications, or post-incident review processes.

## 2. Distinguishing Components in AWS

| Component | Primary Role | Question Answered |
| --- | --- | --- |
| AWS Health | Authoritative source of events affecting AWS services/accounts/resources | What is AWS reporting? |
| AWS Health Dashboard | UI for viewing service health and account-specific events | Which accounts/resources are affected? |
| AWS Support Center | Manage support cases and communicate with AWS Support | What assistance is needed from AWS Support? |
| Amazon EventBridge | Filter, route, and trigger actions from Health events | When an event arrives, which system should run? |
| AWS User Notifications | Configure and receive notifications via console, email, chat, mobile | Who should be notified and over which channel? |
| Systems Manager OpsCenter | Track OpsItems and operational issues | Which operational work item must be resolved? |
| Systems Manager Automation | Run runbooks to perform operational tasks | Which steps can be automated? |
| Incident management platform | Paging, incident commander, escalation, timeline, and communications | Who coordinates the incident through recovery? |

CloudWatch alarms typically detect symptoms inside your workload, such as high CPU, elevated 5xx rates, or queue age exceeding thresholds. AWS Health reports events on AWS infrastructure or resource lifecycles. Correlate both sources to assess actual impact.

## 3. AWS Health Dashboard: Service Health and Account Health

The AWS Health Dashboard in the AWS Management Console provides visibility into events that may affect AWS services and resources.

Distinguish two views:

- **Service health / public events:** public information about Regional AWS service status, not tied to a specific resource in your account.
- **Account health / account-specific events:** notifications tied to your account or resources, such as EC2 instance retirement, planned maintenance, resource degradation, or required action.

A Regional public event can affect many customers. An account-specific event indicates that your specific account's workload/resource may require action.

The AWS Health Dashboard is the human starting point for inspecting event details and affected resources. For automated integrations, use EventBridge or the AWS Health API when the account meets eligibility requirements.

## 4. Event Category, Scope, and Lifecycle

AWS Health events have common categories:

| Category | Meaning | Example |
| --- | --- | --- |
| `issue` | Ongoing event affecting a service/account/resource | Operational issue, connectivity issue |
| `accountNotification` | Notice requiring account attention | Account-related change or requirement |
| `scheduledChange` | Upcoming planned change | Instance retirement, maintenance, service lifecycle |
| `investigation` | AWS is investigating a potential issue | Investigation update |

Event scope indicates reach:

- `PUBLIC`: public service event;
- `ACCOUNT_SPECIFIC`: event tied to an account/resource.

Common event statuses:

- `upcoming`: event scheduled for the future;
- `open`: event currently open or not yet closed;
- `closed`: event closed.

For scheduled changes, the start time may be in the future. Do not interpret `open` as "an active outage happening right now"; always read the category, event description, `startTime`, and affected entities.

An AWS Health event can be updated multiple times. `latestDescription` contains the latest description text; for public events, this field is not the full communication history. For full history, query the AWS Health Dashboard/API.

## 5. Actionability and Personas: Meaning-Based Routing

Some AWS Health events include metadata to support automated routing.

`actionability` can be:

| Value | Meaning | Suggested Handling |
| --- | --- | --- |
| `ACTION_REQUIRED` | Action required | Create ticket/OpsItem, notify owner, track deadline |
| `ACTION_MAY_BE_REQUIRED` | Action may be required | Triage, inspect resources and runbooks |
| `INFORMATIONAL` | Informational only | Record or send in a digest |

`personas` can indicate stakeholder groups:

- `OPERATIONAL`: operations;
- `SECURITY`: security;
- `BILLING`: billing/finance.

Not every event includes full actionability/personas metadata. Event patterns should include fallback branches for events lacking this metadata rather than silently dropping them.

You can combine event category, service, event type code, scope, actionability, and persona for routing. For instance, a scheduled EC2 lifecycle event marked `ACTION_REQUIRED` routes to platform operations; an AWS Health abuse/security event routes to security response.

## 6. Reading the AWS Health Event Schema

When an event is emitted to EventBridge, the envelope contains key fields:

| Field | Meaning |
| --- | --- |
| `version` | EventBridge event version |
| `id` | ID of the EventBridge message |
| `detail-type` | Typically `AWS Health Event` or `AWS Health Abuse Event` |
| `source` | `aws.health` |
| `account` | Account receiving the event |
| `region` | Region to which the EventBridge notification was delivered |
| `time` | Timestamp when the notification was sent |
| `resources` | Resource IDs listed in the envelope if present |
| `detail` | AWS Health event payload |

Inside `detail`:

| Field | Meaning |
| --- | --- |
| `eventArn` | ARN identifying the Health event |
| `service` | Affected AWS service |
| `eventTypeCode` | Event type code |
| `eventTypeCategory` | `issue`/`accountNotification`/`investigation`/`scheduledChange` |
| `eventScopeCode` | `PUBLIC` or `ACCOUNT_SPECIFIC` |
| `communicationId` | ID of the communication/page |
| `startTime`, `endTime` | Event start/end times if present |
| `lastUpdatedTime` | Most recent update timestamp |
| `statusCode` | `upcoming`/`open`/`closed` |
| `eventRegion` | Actual affected Region |
| `eventDescription` | Language and `latestDescription` |
| `affectedEntities` | Resource/entity IDs and status |
| `affectedAccount` | Actual affected account |
| `actionability` | Actionability level if provided |
| `personas` | Stakeholder groups if provided |
| `page`, `totalPages` | Pagination for affected resources/entities list |

### Two Easily Confused Field Pairs

**`region` vs. `detail.eventRegion`:** `region` is the Region where the notification was delivered to EventBridge; `eventRegion` is the impacted Region. Never use `region` to determine where the affected resource lives.

**`account` vs. `detail.affectedAccount`:** in organizational view, `account` may be the management/delegated administrator account receiving the feed, whereas `affectedAccount` is the actual impacted member account. Always use the right field for routing and auditing.

For planned lifecycle events, affected entity status can be `PENDING`, `IMPAIRED`, `UNIMPAIRED`, `RESOLVED`, or `UNKNOWN`. AWS notes that resource status updates occur asynchronously; in rare cases, updates can lag by up to 72 hours.

## 7. EventBridge: Notification and Automation Architecture

Amazon EventBridge receives AWS Health events and matches them against rule event patterns. When an event matches, EventBridge invokes one or more targets.

~~~mermaid
flowchart LR
    Health[AWS Health] --> EB[EventBridge default bus]
    EB --> Rule1[Issue rule]
    EB --> Rule2[Scheduled change rule]
    EB --> Rule3[Security / billing rule]
    Rule1 --> SNS[Amazon SNS]
    Rule1 --> SQS[Amazon SQS]
    Rule2 --> Ops[Systems Manager OpsCenter]
    Rule2 --> Auto[SSM Automation]
    Rule3 --> Sec[Security / ITSM]
    SNS --> Email[Email / Chat]
    SQS --> Worker[Lambda / integration worker]
~~~

Targets can include SNS, SQS, Lambda, Step Functions, Systems Manager Automation, and other integrated services. For chat notifications, you can use Amazon Q Developer in chat applications in supported setups or ITSM/partner integrations.

Separate rules by purpose:
- Incident rules: `issue` events for critical services;
- Change rules: `scheduledChange` or `accountNotification` with `ACTION_REQUIRED`;
- Security rules: `AWS Health Abuse Event` or `SECURITY` persona;
- Billing rules: `BILLING` persona;
- Informational rules: digests or archival.

Do not send every event to a high-priority paging channel. Classification and routing reduce alert fatigue.

## 8. Creating EventBridge Event Patterns for Operational Issues

Example matching only EC2 issue events:

~~~json
{
  "source": ["aws.health"],
  "detail-type": ["AWS Health Event"],
  "detail": {
    "eventTypeCategory": ["issue"],
    "service": ["EC2"]
  }
}
~~~

Example matching action-required scheduled changes/account notifications:

~~~json
{
  "source": ["aws.health"],
  "detail-type": ["AWS Health Event"],
  "detail": {
    "eventTypeCategory": [
      "accountNotification",
      "scheduledChange"
    ],
    "actionability": ["ACTION_REQUIRED"]
  }
}
~~~

Example matching the security persona:

~~~json
{
  "source": ["aws.health"],
  "detail-type": ["AWS Health Event"],
  "detail": {
    "personas": ["SECURITY"]
  }
}
~~~

To receive both public and account-specific events, specify `source: ["aws.health"]` exactly. A wildcard like `aws.health*` does not match as expected in this event pattern.

An EventBridge pattern is a filter, not an authorization policy. Target permissions, event bus policies, IAM roles, and resource policies still must be configured separately.

## 9. Creating an EventBridge Rule with the AWS CLI

Save the event pattern to `health-issue-pattern.json`, then create the rule in the Region to monitor:

~~~bash
aws events put-rule \
  --name Health-EC2-Issues \
  --event-pattern file://health-issue-pattern.json \
  --state ENABLED \
  --description "Route EC2 AWS Health issue events"
~~~

Attach an SNS topic as a target:

~~~bash
aws events put-targets \
  --rule Health-EC2-Issues \
  --targets "Id"="NotifyOperations","Arn"="arn:aws:sns:ap-southeast-1:111122223333:operations-health"
~~~

EventBridge needs permission to publish to the SNS topic. Grant this via the SNS topic policy for the appropriate service principal, scoping `aws:SourceArn` to the rule ARN and `aws:SourceAccount` where appropriate. If targeting Lambda, SQS, or Systems Manager Automation, configure the corresponding resource policy/role.

Verify the rule:

~~~bash
aws events describe-rule \
  --name Health-EC2-Issues

aws events list-targets-by-rule \
  --rule Health-EC2-Issues
~~~

An EventBridge rule begins receiving events only after it is enabled with proper Regional coverage. After creating a new rule, public Health events may take up to one hour to start arriving.

## 10. Region Coverage and Backup Regions

AWS Health EventBridge integration distributes events regionally. Organizations must choose an appropriate coverage strategy.

### Per-Region Rules

Create rules in every Region where workloads must be monitored. This makes Regional coverage explicit and suits workflows filtering events by Region.

### Backup Regions

In the AWS standard partition:
- US West (Oregon) serves as the backup Region for other Regions;
- US East (N. Virginia) serves as the backup Region for US West (Oregon).

For high availability, create rules in both the primary Region and the backup Region. AWS may deliver the same Health event to both; consumers must deduplicate using `eventArn` and `communicationId`.

If you do not want backup copies, filter `detail.backupEvent` on the backup rule using the exact payload data type. AWS Health event examples represent this value as a string; the matching event pattern is:

~~~json
{
  "detail": {
    "backupEvent": ["false"]
  }
}
~~~

Never enable backup rules without handling duplicate notifications.

### Simplified Integration

If you only need account-specific events across multiple Regions in the standard partition and do not require an HA backup setup, you can use simplified integration with a central rule in US West (Oregon). This approach does not receive public events like the AWS Health Dashboard and is recommended for action-required account-specific events.

### Global Events

Some events are not tied to a Region, such as IAM global events. To receive global events, create a rule in US East (N. Virginia).

Do not apply the same Regional assumptions across every AWS partition. Check your partition and AWS documentation for exact coverage.

## 11. Event Delivery, Duplicates, and Pagination

AWS Health delivers events to EventBridge using durable, at-least-once delivery. Therefore, consumers must tolerate duplicates.

Common causes of duplicates:
- EventBridge retries;
- Rules in both primary and backup Regions;
- Multiple communications/updates on a single Health event;
- Multiple pages of affected resources on a single event.

### Deduplication

Use a composite key of:
- `detail.affectedAccount`;
- `detail.eventArn`;
- `detail.communicationId`.

When processing pages, also include `detail.page`. Do not rely solely on EventBridge's `id`, because backup copies can carry different EventBridge message IDs for the same Health event.

Store deduplication keys in DynamoDB/a database or idempotency store with an appropriate TTL. When event status transitions `open` → `closed`, process the update as a state transition rather than ignoring it as a duplicate.

### Pagination

If `resources` or `affectedEntities` exceeds EventBridge's 256 KB message limit, AWS Health splits the event across multiple messages. Pages share the same `eventArn` and `communicationId`; `page`/`totalPages` indicate the current page and total page count.

Consumers should:
1. Persist each page;
2. Verify all `totalPages` have arrived;
3. Reconstruct the complete list of affected resources/entities;
4. Generate a single human notification or OpsItem per policy.

For simple email/chat alerts, you can filter `page = 1` to avoid sending multiple messages for one event; do not do this in consumers that need the full list of affected resources.

## 12. AWS User Notifications: Two Notification Types

AWS User Notifications provides two distinct notification types.

### AWS Managed Notifications

AWS managed notifications are emitted by AWS Health. Users can choose categories, contacts, and channels to receive notices about events affecting accounts/services. Available channels can include:
- Email;
- Chat;
- Push notifications to the AWS Console Mobile Application;
- Console Notification Center.

Effective December 15, 2025, AWS Health email delivery migrated to AWS managed notifications within User Notifications. New emails arrive from `health@aws.com` in a different format from the legacy plain-text emails. If your organization uses email rules to filter by sender or parse bodies, update those workflows.

AWS managed notifications can aggregate events impacting multiple accounts in the same AWS Organization into consolidated notifications when proper trusted access is configured.

**Public service events are not included in AWS managed notifications.** To receive public events, use EventBridge rules or user-configured notifications.

### User-Configured Notifications (UCNs)

UCNs are customer-created notification configurations. They can deliver notifications for CloudWatch alarms, Support cases, and many AWS service events via:
- Console Notification Center;
- Email;
- Amazon Q Developer chat notifications;
- AWS Console Mobile App push;
- User Notifications API.

To receive UCNs, select at least one notification hub and create a notification configuration. Notification hubs/configurations are specific to UCNs, not a prerequisite for AWS managed notifications.

## 13. Choosing Among AWS Managed Notifications, UCNs, and EventBridge

| Need | Mechanism to Consider |
| --- | --- |
| Want email/console notifications for AWS Health categories | AWS managed notifications |
| Want to receive public service health events | EventBridge or UCN |
| Want to filter notifications with custom event patterns and pick channels | UCN |
| Want to invoke Lambda/Step Functions/SSM Automation or send to SQS | EventBridge |
| Want control over dedup, enrichment, retries, and ITSM payloads | EventBridge + processing target |
| Want full affected entities/current status | AWS Health Dashboard, EventBridge, or AWS Health API |
| Want Organization-wide event aggregation | AWS Health organizational view, EventBridge org feed, or managed notification aggregation |

AWS managed notifications keep humans informed; EventBridge fits better when automation logic, payload enrichment, deduplication, and service/team routing are needed.

Never assume an email notification contains every affected resource ID or full event history. When full details are required, open Health Dashboard/API or persist EventBridge event payloads.

## 14. Notification Routing by Team and Priority

A routing matrix can be structured like this:

| Condition | Recipient Group | Channel | Action |
| --- | --- | --- | --- |
| `issue` + critical service | On-call SRE | Pager/Chat + incident platform | Triage immediately |
| `scheduledChange` + `ACTION_REQUIRED` | Resource owner | Ticket + email | Plan work before deadline |
| `personas` includes `SECURITY` | Security operations | Security queue + severity-based pager | Assess exposure |
| `personas` includes `BILLING` | FinOps/Billing | Email/Finance ticket | Check account/billing |
| `accountNotification` | Account/platform owner | Ticket/digest | Verify required action |
| `INFORMATIONAL` | Operations digest | Chat/email summary | Monitor |

Internal severity should not be derived solely from `eventTypeCategory`. A scheduled change can carry high risk if the resource is critical; a public issue may not affect your organization's workloads at all.

Enrichment should add:
- Account name/environment;
- Application/service owner;
- Tags/cost center;
- Affected Region/AZ/resource;
- Runbook link;
- Maintenance deadline;
- Dashboards/alarms;
- Escalation policy.

## 15. AWS Organizations: Organizational View

With many AWS accounts, checking individual Health Dashboards becomes unmanageable. AWS Health organizational view lets the management account or a delegated administrator receive an aggregated Health event feed across accounts in an AWS Organization.

~~~mermaid
flowchart TD
    Org[AWS Organizations] --> A1[Workload account A]
    Org --> A2[Workload account B]
    Org --> A3[Workload account C]
    A1 --> Feed[Health organizational view]
    A2 --> Feed
    A3 --> Feed
    Feed --> Admin[Management / delegated admin]
    Admin --> Rule[EventBridge rule]
    Rule --> Central[Central operations workflow]
~~~

When organizational view is enabled:
- The management account or delegated administrator can view events centrally;
- EventBridge rules in the management/delegated admin account receive organizational events;
- Events may show `account` as the feed-receiving account and `affectedAccount` as the actual impacted member account;
- EventBridge rules in member accounts are not automatically disabled;
- Establish clear ownership to avoid duplicate workflows between centralized and local rules.

AWS allows registering up to five member accounts as delegated administrators for AWS Health organizational view. Delegate to a platform/operations account instead of running day-to-day operations from the management account.

Once registered, a delegated administrator can view Health events affecting the Organization from the last 90 days or since organizational view was enabled, whichever is more recent.

## 16. Enabling a Delegated Administrator and Permissions

From the management account, register a delegated administrator using AWS Organizations:

~~~bash
aws organizations register-delegated-administrator \
  --account-id 444455556666 \
  --service-principal health.amazonaws.com
~~~

Replace the account ID with the designated member account. Beforehand, enable organizational view/trusted access per AWS Health and Organizations documentation.

Trusted access is enabled independently per service. Trusted access for AWS Health does not automatically enable trusted access for AWS User Notifications; to aggregate managed notifications in User Notifications, configure trust separately for that service.

Restrict permissions:
- Allow only the platform/operations delegated account to view organization-wide events;
- Use IAM roles and federation for operators;
- Do not grant Organizations modification permissions to users who only read Health events;
- Audit `register`/`remove` delegated administrator actions;
- Before deregistering a delegated administrator, verify all dependent workflows, EventBridge rules, and API consumers.

## 17. AWS Health API: Querying Events Programmatically

The AWS Health API is a REST API over HTTPS using JSON. SDKs/CLIs sign requests with AWS Signature Version 4.

Common operations:
- `DescribeEvents`: list events;
- `DescribeEventDetails`: retrieve event details;
- `DescribeAffectedEntities`: retrieve impacted resources/entities;
- Organizational view operations: query events/affected entities across an AWS Organization.

**Access prerequisite:** The AWS Health API requires AWS Business Support+, AWS Enterprise Support, or AWS Unified Operations. In Regions where these support plans are not yet available or during transition, Business, Enterprise On-Ramp, or Enterprise Support may apply under transition rules. Accounts without an eligible Support plan receive `SubscriptionRequiredException`.

The AWS Health Dashboard in the console and EventBridge event integration can be used per their availability without implying every account is authorized to call the AWS Health API.

### Active/Passive Endpoints

The AWS Health API uses a multi-Region active/passive architecture:
- Default active endpoint: `health.us-east-1.amazonaws.com`;
- Default passive endpoint: `health.us-east-2.amazonaws.com`;
- Global endpoint: `global.health.amazonaws.com`.

Use DNS lookup on the global endpoint to discover the currently active Region and sign requests using that signing Region. The passive endpoint can return data, but is eventually consistent; the freshest data is only on the active endpoint. When the active endpoint fails over, workflows should re-resolve the endpoint and restart in-flight queries.

Never hardcode the active Region permanently in production applications.

## 18. AWS Health API: IAM and Data Processing

Use temporary credentials from IAM roles/STS instead of long-term access keys. Never use root access keys for routine access.

API responses are paginated. Always read `nextToken` and continue calling until all pages are consumed. For organizational queries, response volumes can be large; apply time filters, event scopes, service filters, and appropriate page sizes.

Processing pattern:
1. Poll/consume events;
2. Persist raw event payloads;
3. Normalize event fields;
4. Deduplicate;
5. Enrich with account/resource metadata;
6. Route to OpsCenter/ITSM;
7. Update event state as new communications arrive;
8. Retain event history per audit policy.

Do not dump full raw payloads into tickets/chat if they contain sensitive resource metadata. Store references/event ARNs and link to access-controlled systems.

## 19. Systems Manager OpsCenter: Managing OpsItems

OpsCenter is the Systems Manager tool for tracking and resolving operational issues as **OpsItems**.

An OpsItem typically includes:
- Title and description;
- Source;
- Priority;
- Status;
- Affected/related resources;
- Operational data;
- Related OpsItems;
- Runnable runbooks;
- Owner/tags and investigation notes.

OpsCenter helps operations teams centralize work items from multiple AWS services. It is not a full paging/incident command system.

Explorer is an operations dashboard that aggregates info on AWS resources and OpsItems. OpsCenter provides Summary, OpsItems list, and OpsItem details views to track status and runbooks.

## 20. Setting Up OpsCenter and Understanding Costs

AWS Systems Manager provides Integrated Setup for OpsCenter and Explorer. This integrated setup runs in the Systems Manager console rather than as a fully programmatic configuration workflow.

When OpsCenter is enabled, default EventBridge rules can automatically create OpsItems for scenarios such as:
- Auto Scaling instance launch/termination failures;
- EBS snapshot creation/copy failures;
- EBS volume performance issues;
- EC2 issues/scheduled changes;
- RDS issues/scheduled changes;
- Systems Manager Maintenance Window execution failures/timeouts.

**Cost:** OpsItems created by default rules can incur charges. After enabling, review the EventBridge rule list, OpsItem creation frequency, deduplication, and pricing. Disable unnecessary rules; do not enable rules in bulk just because the console suggests them.

Setup steps per documentation:
1. Open the Systems Manager console;
2. Choose OpsCenter;
3. Choose Get started;
4. Enable Integrated Setup options to configure Explorer and default rules if desired;
5. Choose Enable OpsCenter;
6. Review OpsItem rules, operational insights, and CloudWatch alarm integration.

## 21. OpsItem Lifecycle, Priority, and Deduplication

OpsCenter tracks OpsItems from creation through resolution. Operators can:
- Create OpsItems manually;
- Update status/priority/description;
- Add related resources;
- Add operational data;
- Link related OpsItems;
- View executed and available runbooks;
- Inspect operational insights and duplicate items.

### Deduplication

OpsCenter uses built-in logic and configurable deduplication strings. When `CreateOpsItem` is called, Systems Manager hashes the deduplication string and originating resource. If a matching OpsItem is already `Open` or `In Progress`, no new item is created; if the prior item is `Resolved`, a new OpsItem may be created.

A deduplication key should represent the same issue class on the same resource, such as:
- Source/service;
- Event type;
- Resource ID;
- Environment.

Never use event message text that changes across updates as the dedup key. Do not merge two independent issues merely because they share a service.

## 22. Creating an OpsItem with the AWS CLI

Example creating an OpsItem for an EC2 instance needing review:

~~~bash
aws ssm create-ops-item \
  --title "EC2 instance retirement - review required" \
  --description "AWS Health reports a scheduled retirement. Review affected instance and execute the approved migration runbook." \
  --source "aws.health" \
  --priority 2 \
  --operational-data file://opsitem-data.json \
  --notifications Arn=arn:aws:sns:ap-southeast-1:111122223333:operations-health \
  --tags Key=Environment,Value=prod Key=Owner,Value=platform
~~~

Example `opsitem-data.json`:

~~~json
{
  "/aws/dedup": {
    "Value": "{\"dedupString\":\"EC2-retirement-prod-i-0123456789abcdef0\"}",
    "Type": "SearchableString"
  },
  "healthEventArn": {
    "Value": "arn:aws:health:ap-southeast-1::event/EC2/example-event",
    "Type": "SearchableString"
  },
  "changeWindow": {
    "Value": "2026-12-01T02:00:00Z",
    "Type": "SearchableString"
  }
}
~~~

Replace the event ARN, resource ID, deadline, and account/Region with real event values. Verify the CLI syntax for operational data against your AWS CLI version.

OpsItems can be created via EventBridge targets/integrations or a Lambda consumer holding `ssm:CreateOpsItem`. With a custom consumer, implement idempotency before calling `CreateOpsItem`.

## 23. From AWS Health Event to OpsCenter

An integration can use an EventBridge rule filtering action-required scheduled changes to create OpsItems.

~~~mermaid
sequenceDiagram
    participant H as AWS Health
    participant E as EventBridge
    participant L as Lambda / integration
    participant O as OpsCenter
    participant R as Resource owner
    H->>E: scheduledChange / ACTION_REQUIRED
    E->>L: Matching event
    L->>L: Deduplicate and enrich
    L->>O: CreateOpsItem
    O-->>R: Assigned operational work
    R->>O: Update status / add notes
    R->>O: Run approved Automation
    O-->>R: Record outcome and resolve
~~~

The consumer should:
- Map `affectedAccount` to the account owner;
- Map `eventRegion` to the Region owner;
- Extract affected entities/resources;
- Put `eventArn`, `communicationId`, event type, deadline, and latest description into operational data;
- Build a stable dedup key;
- Attach runbooks and dashboard links;
- Set priority by impact/deadline;
- Avoid auto-closing an OpsItem solely because an event update reached `closed` if internal remediation is unverified.

## 24. Systems Manager Automation: Operational Runbooks

Systems Manager Automation runs Automation documents to perform tasks on AWS resources or managed nodes.

Use cases:
- Inspect instance state/configuration;
- Stop/start instances per an approved scheduled retirement runbook;
- Create snapshots before maintenance;
- Collect diagnostics;
- Conditionally restart services;
- Remediate standard configuration drift;
- Run pre-checks/post-checks for maintenance.

AWS Health scheduled events can trigger an EventBridge rule that invokes a Systems Manager Automation document. AWS publishes examples that automatically stop/start EC2 instances upon receiving retirement events.

Never automatically restart/terminate a resource solely because an event has category `scheduledChange`. Check the event type code, affected resource, workload criticality, Auto Scaling/ASG membership, backups, application readiness, and maintenance policies before acting.

## 25. Guardrails for Automation

A production runbook should enforce:

- **Preconditions:** resource exists, is in the right account/Region, carries expected tags, and is in a permitted state;
- **Allowlist:** handle only approved resource types/event codes;
- **Approval:** manual approval for destructive or downtime-inducing actions;
- **Rate limits:** cap concurrency and resources per execution;
- **Idempotency:** re-runs do not corrupt state;
- **Timeouts/retries:** bounded retries with backoff;
- **Rollback/recovery:** defined path back to the prior state;
- **Post-checks:** verify service health after automation;
- **Auditing:** record Automation execution ID, actor, parameters, and outputs;
- **Escalation:** if preconditions fail or automation errors, create/retain an OpsItem and notify the owner.

Grant the EventBridge/Automation IAM role only required actions. Use resource ARN/tag conditions where supported. Scope `iam:PassRole` to the specific Automation role and permitted service principal.

## 26. Incident Response: From Event to Recovery

An AWS Health event is one input into incident response. Organizations need internal workflows to turn signals into coordinated action.

~~~mermaid
flowchart TD
    Detect[Detect: Health / alarms / customer reports] --> Triage[Triage impact and scope]
    Triage --> Declare{Incident threshold met?}
    Declare -->|No| Work[Track as OpsItem / planned work]
    Declare -->|Yes| Lead[Declare incident / assign commander]
    Lead --> Comms[Notify responders and stakeholders]
    Comms --> Mitigate[Mitigate / failover / rollback]
    Mitigate --> Recover[Restore service]
    Recover --> Validate[Validate SLI / customer impact]
    Validate --> Close[Close incident]
    Close --> PIR[Post-incident review / actions]
    Work --> Close
~~~

Steps:

1. **Detect:** AWS Health, CloudWatch alarms, Application Signals, logs, traces, or customer reports.
2. **Triage:** identify impacted services, accounts, Regions, resources, blast radius, and customer impact.
3. **Declare:** apply internal severity/incident criteria to decide whether to open an incident.
4. **Assign roles:** incident commander, technical lead, communications lead, scribe, and service owner.
5. **Communicate:** update status pages/chat/tickets on an agreed cadence.
6. **Mitigate:** reduce impact via failover, traffic shifting, rollback, capacity scaling, or workarounds.
7. **Recover:** restore dependencies and drain backlogs.
8. **Validate:** verify SLIs, business transactions, and data integrity.
9. **Close:** confirm service stability and notify stakeholders.
10. **Review:** conduct post-incident review, identify root cause/contributing factors, and track corrective actions.

Never close an incident solely because the AWS Health event turned `closed`. Verify the actual workload has recovered.

## 27. Incident Manager: Availability Changes to Know

AWS Systems Manager Incident Manager stopped accepting new customers effective **November 7, 2025**, and AWS is not adding new features/capabilities. Customers who enabled Incident Manager prior to that date can continue using it in already-enabled accounts.

Implications for tool selection:
- For new customers, do not design architectures assuming Incident Manager can be enabled;
- Existing customers can keep using it, yet should evaluate a migration plan;
- AWS recommends Systems Manager OpsCenter for managing operational issues across AWS infrastructure;
- For automated paging/incident response capabilities, AWS recommends evaluating solutions from the AWS Partner Network;
- Integrate with Jira Service Management, ServiceNow, PagerDuty, and suitable incident/ITSM platforms.

OpsCenter manages OpsItems and operational work; it does not replace all paging, escalation, on-call schedules, incident command, and stakeholder communication features of a dedicated incident platform.

When migrating off Incident Manager:
1. Export incident data for analysis/archival;
2. Map response plans/on-call contacts/runbooks to the target system;
3. Migrate EventBridge/SNS integrations;
4. Test paging, escalation, and incident lifecycles;
5. Transfer required data/documentation;
6. Once migration completes, clean up remaining Incident Manager resources to avoid ongoing charges.

## 28. Choosing an Incident Management Solution

| Need | AWS-Native Building Blocks | Potential Additional Solutions |
| --- | --- | --- |
| Receive AWS Health events | AWS Health + EventBridge | — |
| Email/chat/push notifications | AWS User Notifications, SNS, Amazon Q Developer chat integrations | — |
| Track operational work | Systems Manager OpsCenter | Jira/ServiceNow if required by enterprise workflows |
| Automate remediation | Systems Manager Automation | — |
| On-call schedules and paging | EventBridge/SNS integration | PagerDuty or APN partner |
| Incident commander and timeline | Ticket/chat/automation integrations | ServiceNow, Jira Service Management, or incident platform |
| Customer communications/status page | Notification integrations | Status-page/communications platform |

Choose based on on-call scheduling, escalation policies, acknowledgements, auditing, chatops, incident timelines, integrations, and compliance requirements. Do not pick a tool merely because it can receive an SNS notification.

## 29. Combining AWS Health with CloudWatch Alarms and Observability

AWS Health indicates AWS has published an event; CloudWatch/observability shows whether your workload is actually experiencing anomalies.

Example:
- AWS Health: RDS planned maintenance;
- CloudWatch: DB connections drop and API latency spikes;
- Logs: connection resets;
- Traces: database client timeout spans;
- OpsCenter: OpsItem linked to the RDS resource;
- Runbook: verify failover/maintenance state;
- Incident platform: declare an incident if customer SLIs breach error budget policy.

Surface AWS Health events alongside:
- Account/Region/service/resource;
- CloudWatch alarms;
- Service dashboards;
- Application Signals/trace search;
- Deployment/maintenance timelines;
- OpsItem/incident/ticket links;
- Owner and runbook.

An AWS Health event does not automatically mean your workload is down. Correlate service health with application telemetry before deciding severity.

## 30. IAM and Security for Health Notification Workflows

Separate roles by responsibility:

| Identity | Permissions |
| --- | --- |
| EventBridge service role | Invoke designated targets |
| Lambda integration role | Read events, enrich, create OpsItems, or call downstream APIs |
| SSM Automation role | Execute actions inside Automation documents |
| Operator role | View Health/OpsItems, update status, run permitted runbooks |
| Organization delegated admin | View organizational Health events under delegated permissions |
| ITSM integration role | Publish/query integrated systems within API scope |

Security practices:
- Never grant `AdministratorAccess` to a notification Lambda;
- Scope `ssm:CreateOpsItem`, `ssm:UpdateOpsItem`, and `ssm:StartAutomationExecution` per use case;
- Scope `iam:PassRole` to specific Automation roles;
- Apply resource policies to SNS/SQS/Lambda targets;
- Store ITSM API tokens in Secrets Manager/Parameter Store;
- Encrypt queues/logs and bound retention;
- Never include credentials, customer PII, or secret values in event enrichment;
- Audit role assumptions, Automation executions, and OpsItem updates with CloudTrail;
- Control read access to event descriptions and affected resource IDs.

Event payloads can expose resource identifiers and operational context. Deliver them only to authorized personnel and groups.

## 31. Cost, Quotas, and Operational Hygiene

Costs can arise from:
- OpsItems created by default EventBridge rules;
- EventBridge events/rules/targets based on usage;
- SNS, SQS, Lambda, and Step Functions;
- Systems Manager Automation executions;
- Logs, metrics, and audit storage;
- Third-party ITSM/on-call integrations.

Controls:
- Enable only necessary default OpsItem rules;
- Use deduplication to prevent multiple OpsItems for one issue;
- Filter `INFORMATIONAL` events out of paging;
- Group notifications by service/event/account;
- Apply TTLs to idempotency records;
- Bound retries/DLQs and monitor failed invocations;
- Track Automation execution volume;
- Periodically review event patterns and stale rules;
- Verify Regional pricing and quotas.

Never create an OpsItem per duplicate EventBridge delivery. Never trigger bulk automated remediation without evaluating blast radius.

## 32. Troubleshooting AWS Health Notifications

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Not receiving Health events | Rule in wrong Region or mismatched event pattern | Check `source`, `detail-type`, service/category, and Region |
| Public events missing | Rule recently created (propagation lag); missing rule in impacted Region | Wait for propagation and verify Region coverage |
| Only seeing partial account events | Organizational view/trusted access not enabled | Check Organizations, delegated admin, and Health org view |
| Event delivered twice | Primary/backup rules or at-least-once delivery | Deduplicate using `affectedAccount`/`eventArn`/`communicationId` |
| Missing affected resources | Multi-page event or public event lacking resource list | Check `page`/`totalPages`, Dashboard/API |
| Wrong Region in ticket | Used envelope `region` instead of `eventRegion` | Map `detail.eventRegion` |
| Wrong account owner | Used `account` instead of `affectedAccount` in org view | Map `detail.affectedAccount` |
| Event pattern misses security events | Filtered only `AWS Health Event` | Include `AWS Health Abuse Event` and security persona |
| AWS managed emails not arriving | Contacts/categories/channels unconfigured | Check User Notifications subscriptions and account contacts |
| Public events missing from managed emails | Public events are not sent via managed notifications | Use EventBridge or UCN |
| Email parser broken | AWS Health email migration from Dec 15, 2025 | Update sender `health@aws.com` and parser format |
| Health API returns `SubscriptionRequiredException` | Insufficient Support plan | Check AWS Support plan/Region transition |
| Health API returns stale data | Calling passive endpoint | Resolve global endpoint and sign for active Region |
| Duplicate OpsItems created | Unstable dedup string/resource | Check `/aws/dedup` and EventBridge input transformer |
| Cannot create OpsItem | Lambda/EventBridge role missing permissions | Check `ssm:CreateOpsItem` and target role |
| Automation target fails to run | Missing managed node, trust, or `PassRole` | Check SSM Agent, IAM role, trust, and Automation execution |
| EventBridge target errors | Misconfigured resource policy or retry/target settings | Inspect rule metrics, DLQ, and target permissions |
| Incident not paging | Notifications go to chat/email without on-call platform | Check acknowledgement/escalation workflow |

### Investigation Workflow

~~~text
1. Confirm AWS account, Region, and event scope.
2. Open AWS Health Dashboard to confirm the event exists.
3. Verify EventBridge rule pattern and Region coverage.
4. Inspect sample event, detail.eventRegion, and affectedAccount.
5. Check rule metrics, target invocations, and DLQ.
6. Check duplicate keys, page/totalPages, and backupEvent.
7. Verify SNS/SQS/Lambda resource policies and IAM roles.
8. Check User Notifications contacts, channels, and notification hub if using UCN.
9. If using AWS Health API, verify Support plan, active endpoint, and SigV4 signing Region.
10. If OpsItems are missing, check ssm:CreateOpsItem and deduplication.
11. If Automation fails, inspect Automation execution steps and CloudTrail.
12. Update runbooks, rule filters, and escalation ownership.
~~~

## 33. Lab: AWS Health → EventBridge → SNS → OpsCenter

### Scenario

A production workload runs EC2 and RDS in `ap-southeast-1`. The platform team wants to capture scheduled changes/issue events, notify operations, and create OpsItems for action-required events.

### Step 1 — Verify the Event Pattern

Create `health-action-required.json`:

~~~json
{
  "source": ["aws.health"],
  "detail-type": ["AWS Health Event"],
  "detail": {
    "eventTypeCategory": [
      "issue",
      "accountNotification",
      "scheduledChange"
    ],
    "actionability": [
      "ACTION_REQUIRED",
      "ACTION_MAY_BE_REQUIRED"
    ]
  }
}
~~~

In production, separate issue rules from scheduled-change rules for distinct routing. Validate sample events using EventBridge's Test event pattern tool.

### Step 2 — Create the Rule

~~~bash
aws events put-rule \
  --name Health-Action-Required \
  --event-pattern file://health-action-required.json \
  --state ENABLED
~~~

Create rules in every monitored Region or use simplified integration where suitable for account-specific events. If enabling backup Regions, implement deduplication.

### Step 3 — Add the SNS Target

~~~bash
aws events put-targets \
  --rule Health-Action-Required \
  --targets "Id"="OpsEmail","Arn"="arn:aws:sns:ap-southeast-1:111122223333:operations-health"
~~~

Configure the SNS topic policy for EventBridge and subscribe email/chat integrations. Confirm subscriptions and test notification delivery.

### Step 4 — Build the OpsItem Integration

Use a Lambda function or integration target to:
- Deduplicate events;
- Extract `affectedAccount`/`eventRegion`;
- Select affected resources;
- Create an OpsItem if actionability warrants it;
- Attach event ARN, communication ID, deadline, and runbook link;
- Send the ticket link to the service owner.

### Step 5 — Test with a Sample Event

Use an EventBridge sample event matching the AWS Health schema. Do not wait for a real AWS Health production incident to test the pipeline.

Verify:
- Rule matches;
- SNS receives the event;
- Notification reaches the right team;
- Consumer creates one OpsItem;
- Duplicate sample does not create a second OpsItem;
- `closed` updates are handled properly;
- Failed targets retry/go to DLQ;
- CloudTrail records the actions.

### Step 6 — Run a Runbook in a Sandbox

Use a non-destructive Automation document to gather instance state or verify prerequisites. Test stop/start/reboot only on authorized test instances. Record execution IDs and post-check results in the OpsItem.

## 34. Exercises and Self-Check Questions

### Exercise 1 — Public Events vs. Account-Specific Events

A public EC2 operational issue appears in `us-east-1`; meanwhile, your account also has an EC2 instance retirement in `ap-southeast-1`.

**Task:** Distinguish event scope/category, identify which event targets a specific resource, and choose separate notification routes.

### Exercise 2 — Region Coverage and Duplicates

An organization creates EventBridge rules in a primary Region and the Oregon backup Region.

**Task:** Explain why duplicates occur, choose a deduplication key, and explain the roles of `backupEvent`, `eventArn`, `communicationId`, and `eventRegion`.

### Exercise 3 — Organizational View

There are 40 AWS accounts and the platform team wants one centralized feed.

**Task:** Design organizational view, management/delegated administrator, trusted access, and a central EventBridge rule. Explain the difference between `account` and `affectedAccount`.

### Exercise 4 — User Notifications

A team previously parsed plain-text AWS Health emails to open tickets. After December 15, 2025, the workflow broke.

**Task:** Describe the email migration, sender/format changes, and propose EventBridge or UCN for a reliable workflow.

### Exercise 5 — OpsItem Deduplication

A Health event arrived across two Regions and created two OpsItems for the same EC2 instance.

**Task:** Design a deduplication string, explain behavior when the existing OpsItem is Open/In Progress/Resolved, and show how to store event communication history.

### Exercise 6 — Safe Automation

AWS Health reports a scheduled EC2 instance retirement. The team wants to automatically stop/start the instance.

**Task:** Verify event type code, EBS-backed/instance-store behavior, managed node prerequisites, Automation role, `PassRole`, preconditions, and post-checks. Identify conditions requiring manual approval.

### Exercise 7 — Incident Manager Availability

A new project plans to use Systems Manager Incident Manager; an older account enabled Incident Manager before November 7, 2025.

**Task:** Propose different approaches for the two cases, compare OpsCenter with on-call/ITSM partner solutions, and draft a migration checklist.

### Exercise 8 — AWS Health API

An integration calls `DescribeEvents` and receives `SubscriptionRequiredException`.

**Task:** Check Support plan, active/passive endpoints, SigV4 signing Region, and pagination.

### Short Questions

1. **What does AWS Health provide?** Information on events affecting AWS services, accounts, and resources.
2. **How does a public event differ from an account-specific event?** Public reflects Regional service health; account-specific is tied to your account/resources.
3. **What are the main event categories?** `issue`, `accountNotification`, `investigation`, and `scheduledChange`.
4. **What values can `eventScopeCode` take?** `PUBLIC` or `ACCOUNT_SPECIFIC`.
5. **What values can `actionability` take?** `ACTION_REQUIRED`, `ACTION_MAY_BE_REQUIRED`, and `INFORMATIONAL`.
6. **Which routing targets does `personas` support?** `OPERATIONAL`, `SECURITY`, and `BILLING`.
7. **How does `region` differ from `eventRegion`?** The Region where the notification was sent vs. the affected Region.
8. **How does `account` differ from `affectedAccount`?** The feed-receiving account vs. the impacted account.
9. **Is EventBridge delivery exactly-once?** No; consumers need idempotency/deduplication.
10. **How long can public events take to start arriving after creating a rule?** Up to one hour.
11. **Why do backup Regions exist?** To increase reliability if the primary Region experiences an outage.
12. **What should a dedup key contain?** `affectedAccount`, `eventArn`, and `communicationId`; add `page` when reconstructing pagination.
13. **Do AWS managed notifications send public events?** No.
14. **When did AWS Health emails migrate to User Notifications?** December 15, 2025.
15. **What do UCNs require to operate?** A notification hub and notification configurations.
16. **What is organizational view used for?** Aggregating Health events across an AWS Organization.
17. **Up to how many Health delegated administrators can be registered?** Five member accounts.
18. **Which Support plans does the AWS Health API require?** Business Support+, Enterprise Support, or Unified Operations per Regional availability/transition.
19. **What does OpsCenter manage?** OpsItems and operational work.
20. **How does OpsItem deduplication work?** Matches dedup key/resource; duplicate `Open`/`In Progress` items prevent creating another.
21. **What is SSM Automation used for?** Running runbooks for operational tasks.
22. **When did Incident Manager stop accepting new customers?** November 7, 2025.
23. **What does AWS recommend for operational issues for new customers?** Systems Manager OpsCenter.
24. **Does OpsCenter fully replace paging/on-call schedules?** No; an APN incident/on-call solution may be required.
25. **Does closing an AWS Health event mean the workload has recovered?** No; verify via application telemetry and business checks.

## 35. Pre-Production Checklist

- [ ] Defined the roles of Health Dashboard, EventBridge, User Notifications, and OpsCenter.
- [ ] Public events and account-specific events are separated in routing.
- [ ] Event categories, scope, status, actionability, and personas are handled.
- [ ] `region`/`eventRegion` and `account`/`affectedAccount` mappings are accurate.
- [ ] EventBridge rules are deployed across all monitored Regions.
- [ ] Backup Region strategy and `backupEvent` filters are verified.
- [ ] Consumers handle at-least-once delivery and deduplication.
- [ ] Pagination (`page`/`totalPages`) is handled when full affected entities are required.
- [ ] Event patterns are tested using sample events.
- [ ] EventBridge targets have appropriate IAM/resource policies and DLQs.
- [ ] AWS managed notifications contacts/channels are configured.
- [ ] UCNs have the required notification hub and notification configurations.
- [ ] Public events are routed via EventBridge or UCN.
- [ ] Email parsers are updated for the December 15, 2025 migration.
- [ ] Organizational view/trusted access/delegated administrator are properly configured.
- [ ] AWS Health API Support plan, active endpoint, and SigV4 Region are verified if used.
- [ ] OpsCenter default rules, OpsItem volume, and pricing have been reviewed.
- [ ] OpsItem deduplication, ownership, priority, and lifecycle are defined.
- [ ] SSM Automation runbooks enforce preconditions, allowlists, approvals, and post-checks.
- [ ] IAM roles follow least privilege; `iam:PassRole` is tightly scoped.
- [ ] Incident severity, commander, paging, escalation, and communication cadence are defined.
- [ ] An incident platform/partner solution is in place if paging and automated response are needed.
- [ ] Incident Manager availability is evaluated for existing vs. new accounts.
- [ ] An export/migration plan exists if currently using Incident Manager.
- [ ] Logs, CloudTrail, Automation execution IDs, and ticket links are retained for auditing.
- [ ] The notification pipeline has retries, DLQs, dashboards, and runbooks.
- [ ] Test events validate end-to-end delivery without waiting for a real incident.

## 36. Summary

AWS Health is the signal source for service health, account notifications, operational issues, and planned lifecycle events. The AWS Health Dashboard gives humans visibility; EventBridge turns events into triggers for notifications and automation; AWS User Notifications provides email/chat/push/console channels; Systems Manager OpsCenter manages OpsItems; and Systems Manager Automation executes controlled runbooks.

A reliable design distinguishes public from account-specific events, interprets event scope/category/actionability/persona accurately, handles `eventRegion`/`affectedAccount`, Region coverage, backup deliveries, duplicate messages, and pagination. With AWS Organizations, organizational view and delegated administrators centralize events while preserving clear boundaries of responsibility. The AWS Health API requires an eligible Support plan and must track active/passive endpoints.

Incident response is an organizational workflow: detect, triage, declare, assign, communicate, mitigate, recover, validate, and review. OpsCenter supports operational work; Automation supports remediation; paging/on-call/incident command may require a partner platform. Incident Manager stopped onboarding new customers effective November 7, 2025, so new architectures must choose suitable current alternatives.

Key takeaways:

1. An AWS Health event is a signal; never assume a workload is down or recovered from it alone.
2. EventBridge delivery is at-least-once; build idempotency and deduplication.
3. `region` differs from `eventRegion`; `account` differs from `affectedAccount`.
4. AWS managed notifications do not send public events; use EventBridge or UCN for public events.
5. AWS Health email migrated to User Notifications effective December 15, 2025.
6. Organizational view and delegated administrators manage multi-account Health events.
7. OpsCenter manages OpsItems; Automation executes runbooks with IAM guardrails.
8. Incident Manager stopped onboarding new customers on November 7, 2025; OpsCenter and APN incident solutions are AWS-cited alternatives.
9. Every incident must end with workload validation and post-incident learning, not merely AWS Health status.

### Official Documentation

- [AWS Health User Guide](https://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html)
- [AWS Health Dashboard](https://docs.aws.amazon.com/health/latest/ug/getting-started-health-dashboard.html)
- [Monitoring events in AWS Health with EventBridge](https://docs.aws.amazon.com/health/latest/ug/cloudwatch-events-health.html)
- [Configuring EventBridge rules for AWS Health](https://docs.aws.amazon.com/health/latest/ug/creating-event-bridge-events-rule-for-aws-health.html)
- [AWS Health EventBridge schema](https://docs.aws.amazon.com/health/latest/ug/aws-health-events-eventbridge-schema.html)
- [AWS Health Region coverage and backup Regions](https://docs.aws.amazon.com/health/latest/ug/choosing-a-region.html)
- [AWS Health organizational view](https://docs.aws.amazon.com/health/latest/ug/aggregating-health-events.html)
- [Delegated administrator for AWS Health](https://docs.aws.amazon.com/health/latest/ug/delegated-administrator-organizational-view.html)
- [AWS Health API access and endpoints](https://docs.aws.amazon.com/health/latest/ug/health-api.html)
- [AWS managed notifications in User Notifications](https://docs.aws.amazon.com/health/latest/ug/manage-user-notifications.html)
- [User-configured notifications](https://docs.aws.amazon.com/notifications/latest/userguide/uc-notifications.html)
- [Systems Manager OpsCenter setup](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-setup.html)
- [Manage OpsItems](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-working-with-OpsItems.html)
- [OpsItem deduplication](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter-working-deduplication.html)
- [Automating EC2 operations from AWS Health events](https://docs.aws.amazon.com/health/latest/ug/automating-instance-actions.html)
- [Incident Manager availability change](https://docs.aws.amazon.com/incident-manager/latest/userguide/incident-manager-availability-change.html)
- [Incident Manager migration guides](https://docs.aws.amazon.com/incident-manager/latest/userguide/migration-guides.html)

**Operational note:** AWS Health event schemas, notification channels, Support plans, delegated administrator setup, Systems Manager pricing, and partner integrations can change. Before production, verify service availability in your account/Region, test EventBridge event patterns with sample events, validate IAM/DLQ/deduplication, and test runbooks in a sandbox.
