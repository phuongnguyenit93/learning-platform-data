# CloudTrail Lake and account activity investigation

> **Chapter:** Auditing and Compliance  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem across Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless; build the ability to choose services, design, and deploy secure applications with monitoring, resilience, and cost control.

When an AWS account has hundreds of workloads and multiple operators, the critical question during an incident is often: **who called which API, at what time, from where, on which resource, and with what outcome?** AWS CloudTrail records API activity and account activity. CloudTrail Lake adds an Event Data Store (EDS) and SQL querying capability to analyze events across multiple fields, accounts, or Regions.

This lesson explains how to read CloudTrail event structures, organize Event Data Stores, select data to collect, write SQL queries, and investigate a suspicious sequence of activities. It also covers permissions, retention, cost, Athena federation, and the workflow for migrating data to AWS's currently recommended architecture.

> **Service availability note (updated 20-11-2026):** AWS CloudTrail Lake closed to new customers as of **31-05-2026**. Customers who used it prior to that date can continue using existing Event Data Stores; AWS states CloudTrail Lake only receives critical bug fixes and security updates. AWS CloudTrail Trails, Event history, Insights, and Aggregated Events remain supported. AWS recommends customers migrate to Amazon CloudWatch for similar collection, storage, and analytics capabilities. Accordingly, the CloudTrail Lake sections below support understanding and operating existing systems; new learners should review the replacement architecture in section 17. [CloudTrail Lake availability notice](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-service-availability-change.html).

## 1. Learning objectives

After this lesson, you can:

1. Distinguish between CloudTrail Event history, Trails, and CloudTrail Lake Event Data Stores.
2. Explain management events, data events, network activity events, and Insights events.
3. Read key fields in a CloudTrail event to identify the actor, action, target, source, and outcome.
4. Understand how an EDS collects events using advanced event selectors.
5. Distinguish between an account-level EDS and an organization EDS in AWS Organizations.
6. Write time-bounded SQL to find IAM activity, sign-ins, resource changes, and data access.
7. Build a timeline and test hypotheses during an investigation.
8. Manage retention, ingestion, query costs, access permissions, and query results.
9. Understand federation to AWS Glue, Lake Formation, and Amazon Athena.
10. Plan evidence preservation and migration to Amazon CloudWatch when appropriate.

## 2. What does CloudTrail record?

AWS CloudTrail records activity performed by users, roles, AWS services, or workloads through AWS APIs and supported event sources. An event typically describes:

- **Who:** the principal or identity that performed the action.
- **What:** the API/action called.
- **When:** the timestamp when the event occurred.
- **Where:** the Region and source address.
- **On what:** the affected resource or object.
- **Outcome:** success or failure, and error code/message if applicable.

For example, when a role calls `iam:CreateAccessKey`, CloudTrail can record `eventSource`, `eventName`, `userIdentity`, `sourceIPAddress`, `requestParameters`, `responseElements`, and `eventTime`. These fields allow investigating who created an access key, for which IAM user, and in which login session.

### 2.1. CloudTrail Event history

Event history is the lookup interface for recent management events in a single account and a single Region. Event history:

- Is available without creating a Trail.
- Displays management events over the last 90 days.
- Searches by a few simple attributes such as event name, user name, or resource.
- Is suitable for quickly checking a recent operation.

Event history is not a long-term analytics store, does not replace data event logging, and does not support multi-field SQL queries across multiple accounts/Regions.

### 2.2. CloudTrail Trail

A Trail configures the collection and delivery of CloudTrail events to Amazon S3; it can integrate with CloudWatch Logs and other services. A Trail is suitable for:

- Storing long-term records in S3.
- Centralizing logs from multiple accounts using an organization trail.
- Analyzing with Athena, a SIEM, or processing pipelines.
- Setting up log file validation and bucket protection as required.

A Trail can be single-Region or multi-Region. For production environments, a multi-Region trail is usually a good baseline to avoid missing activity in other Regions. Also consider opt-in Regions and the AWS partitions in use.

### 2.3. CloudTrail Lake Event Data Store

CloudTrail Lake is an analytics service built around Event Data Stores. An EDS collects selected event categories, retains data according to configured retention, and allows querying with SQL.

An EDS can centralize events from multiple accounts/Regions (depending on EDS type and configuration), while supporting multi-field queries and joining EDSs using supported SQL capabilities. CloudTrail Lake does not require a separate Trail to ingest events into an EDS.

### 2.4. Quick comparison

| Mechanism | Purpose | Scope and querying |
| --- | --- | --- |
| Event history | Quick lookup of recent activity | 90 days of management events, current account/Region |
| Trail → S3 | Long-term audit log collection and storage | Multi-Region/organization; analyzed with Athena or other tools |
| CloudTrail Lake EDS | Event store with built-in SQL queries | Multiple event types, retention, and selectors per EDS |
| CloudWatch architecture | AWS-recommended replacement architecture for CloudTrail Lake for new customers | Centralizes security/operations/compliance telemetry and analytics |

These mechanisms should not be treated as mutually exclusive. An organization can use a Trail to store records in S3, Event history for quick checks, and an analytics platform for long-term investigations.

## 3. Types of CloudTrail events

Choosing the right event category is the first step of a useful audit system. Missing required events means no query can recover activity that was never recorded.

### 3.1. Management events

Management events (control plane events) record AWS resource management operations, for example:

- `CreateRole`, `AttachRolePolicy`, `PutRolePolicy` in IAM.
- `RunInstances`, `AuthorizeSecurityGroupIngress`, `CreateVpc` in EC2/VPC.
- `CreateBucket`, `PutBucketPolicy` in the S3 control plane.
- `CreateFunction`, `UpdateFunctionConfiguration` in Lambda.
- `CreateTrail`, `StopLogging`, `DeleteEventDataStore` in CloudTrail.

Management events are usually collected by default by CloudTrail. They can be read-only or write management events. Read-only events such as `DescribeInstances` help understand query/discovery activity; write events such as `ModifySecurityGroupRules` help detect configuration changes.

### 3.2. Data events

Data events record operations on data or inside resources, for example:

- Reading/writing objects in S3: `GetObject`, `PutObject`, `DeleteObject`.
- Invoking a Lambda function.
- Reading/writing items in DynamoDB when supported by configuration.
- Certain data operations of services supported by CloudTrail.

Data events typically have high volume and can incur charges. Do not enable all data events on all resources without a use case. Identify sensitive buckets, functions, tables, or resources needing auditing; choose read/write operations and specific selectors.

### 3.3. Network activity events

Network activity events record certain network activities supported by CloudTrail, typically related to VPC endpoint policies or access through endpoints. They are not a replacement for VPC Flow Logs. Network activity events can help investigate API/network access within supported services; VPC Flow Logs remain necessary for network flow analysis.

### 3.4. CloudTrail Insights events

CloudTrail Insights detects certain unusual API activity compared to a baseline, such as sudden spikes in API call rates or error rates. Insights events are signals for deeper investigation; they do not prove an action is malicious.

When you see an Insights event:

1. Identify the event type/insight source and anomalous time window.
2. Query related management events within the same timeframe.
3. Compare actor, source IP, user agent, Region, and resource.
4. Check change windows, deployments, or valid operational activity.
5. Expand to VPC Flow Logs, GuardDuty, IAM Access Analyzer, or workload logs if needed.

### 3.5. Event category and event type

`eventCategory` distinguishes event groups such as `Management`, `Data`, `NetworkActivity`, `Insight`, or `ConfigurationItem` depending on the EDS type. `eventType` describes a more detailed event type, such as `AwsApiCall` or a type of service event. Do not confuse `eventCategory` with `eventSource`: category describes the group, while source indicates the service generating the API event.

## 4. Reading CloudTrail event structure

A CloudTrail event is a JSON record. Fields commonly used during investigations:

| Field | Meaning | Supporting question |
| --- | --- | --- |
| `eventTime` | Time the event occurred | When did the event happen? |
| `eventSource` | Service receiving the API request | Which service does the API belong to? |
| `eventName` | API/action name | What did the caller do? |
| `awsRegion` | Region processing the request | Where did the activity occur? |
| `userIdentity` | Identity performing the request | Who or which role performed it? |
| `sourceIPAddress` | Request source address | Where did the request come from? |
| `userAgent` | Client/SDK/console context | Which tool issued the request? |
| `requestParameters` | Request parameters | Which resource/value was requested? |
| `responseElements` | Recorded portion of the response | What result did the API return? |
| `errorCode`, `errorMessage` | Error details | Why did the request fail? |
| `resources` | Related resources if recorded | Which target was affected? |
| `eventID` | Unique ID of the event | Used to identify the event when cross-referencing |
| `requestID` | Service request ID | Helps correlate with service/support logs |

### 4.1. Abbreviated event example

~~~json
{
  "eventVersion": "1.09",
  "userIdentity": {
    "type": "AssumedRole",
    "principalId": "AROAEXAMPLE:deployment-session",
    "arn": "arn:aws:sts::111122223333:assumed-role/DeploymentRole/deployment-session",
    "accountId": "111122223333",
    "sessionContext": {
      "sessionIssuer": {
        "type": "Role",
        "arn": "arn:aws:iam::111122223333:role/DeploymentRole",
        "userName": "DeploymentRole"
      },
      "attributes": {
        "mfaAuthenticated": "true"
      }
    }
  },
  "eventTime": "2026-11-20T03:15:22Z",
  "eventSource": "iam.amazonaws.com",
  "eventName": "AttachRolePolicy",
  "awsRegion": "ap-southeast-1",
  "sourceIPAddress": "198.51.100.25",
  "userAgent": "aws-cli/2.x",
  "requestParameters": {
    "roleName": "ApplicationRole",
    "policyArn": "arn:aws:iam::aws:policy/AdministratorAccess"
  },
  "responseElements": null,
  "requestID": "example-request-id",
  "eventID": "example-event-id",
  "readOnly": false,
  "eventType": "AwsApiCall",
  "managementEvent": true,
  "recipientAccountId": "111122223333",
  "eventCategory": "Management"
}
~~~

In this example, an assumed role attached the AWS managed policy `AdministratorAccess` to `ApplicationRole`. This is a high-impact permission change. Investigators should determine who assumed `DeploymentRole`, whether the session was approved, whether the change fell within a deployment window, and which roles received new permissions.

### 4.2. Distinguishing the actor from the assumed role

When `userIdentity.type` is `AssumedRole`, the ARN typically looks like:

~~~text
arn:aws:sts::<account-id>:assumed-role/<role-name>/<session-name>
~~~

`userIdentity.arn` identifies the assumed-role session. `userIdentity.sessionContext.sessionIssuer.arn` identifies the IAM role that issued the credentials. If `sourceIdentity`, `onBehalfOf`, `inScopeOf`, or session tags are present, those fields can provide additional context about the original user, workload, or delegated session.

Do not conclude that the role name is the human performing the action. A role can be assumed by an IAM Identity Center user, automation, Lambda, EC2, CI/CD, or an AWS service.

### 4.3. Limitations when reading events

- Not every API returns full `requestParameters`/`responseElements`.
- Some fields may be omitted or redacted for security reasons.
- `sourceIPAddress` can be an AWS service address, proxy, NAT, endpoint, or client; do not automatically infer a user's geographic location from it.
- `userAgent` is a signal, not absolute proof of identity.
- `eventTime` is when the event occurred; log ingestion or delivery time can be later.
- Event schemas may add new fields; parsers should ignore unknown fields and check major versions per AWS recommendations.

## 5. Event Data Store and advanced event selectors

An Event Data Store is an event repository managed by CloudTrail Lake. When creating an EDS, you choose the event category, source, account/Region scope, selectors, and retention. An EDS collects events matching its configuration; it does not automatically contain all history prior to its creation time.

### 5.1. Common EDS types

Depending on requirements, an EDS can be created for:

- CloudTrail management events.
- CloudTrail data events.
- CloudTrail network activity events.
- CloudTrail Insights events.
- AWS Config configuration items.
- Non-AWS events from supported applications or partner integrations.

Each EDS type has its own schema and event categories. You cannot assume a single EDS will combine incompatible data types into the same schema.

### 5.2. Advanced event selectors

Advanced event selectors allow filtering by fields and conditions, for example:

- `eventCategory`.
- `eventSource`.
- `eventName`.
- `resources.type`.
- `resources.ARN`.
- `readOnly`.
- `userIdentity.arn`.
- `eventType`.

For example, an EDS for data events of an S3 bucket can select only object operations on that bucket:

~~~json
[
  {
    "Name": "Sensitive bucket object events",
    "FieldSelectors": [
      {
        "Field": "eventCategory",
        "Equals": ["Data"]
      },
      {
        "Field": "resources.type",
        "Equals": ["AWS::S3::Object"]
      },
      {
        "Field": "resources.ARN",
        "StartsWith": [
          "arn:aws:s3:::company-sensitive-data/"
        ]
      }
    ]
  }
]
~~~

This is an illustrative selector example; confirm supported fields, operators, and resource ARN patterns for the specific event source before applying. If you need both read and write data events, do not filter to only one direction using `readOnly`.

### 5.3. Selecting data by investigation goal

| Goal | Event types/selectors to consider |
| --- | --- |
| Investigate IAM changes | Management events for `iam.amazonaws.com`, including write and necessary read events |
| Investigate logins | Sign-in/STS management events and identity/session fields |
| Investigate network changes | EC2/VPC management events; supplement with VPC Flow Logs for traffic |
| Investigate object reads/deletes | S3 data events for sensitive buckets/prefixes |
| Investigate Lambda invocations | Lambda data events if invocation auditing is needed |
| Investigate API anomalies | Management events and Insights events where the feature applies |

Do not choose selectors so narrow that you miss the chain of events needed for investigation. For example, collecting only `PutBucketPolicy` might miss `GetBucketPolicy` or earlier IAM changes that granted access.

### 5.4. EDS does not retroactively collect data

An EDS begins ingesting from when it is configured. If you need to analyze history already recorded by a Trail, existing CloudTrail Lake customers can copy trail events into an EDS using the AWS-supported workflow. Copying can incur ingestion charges and depends on data in S3, bucket/KMS permissions, and EDS retention.

## 6. Account-level and organization Event Data Stores

With AWS Organizations, determine whether an EDS belongs to a single account or applies to the entire organization.

### 6.1. Account-level EDS

An account-level EDS collects events for the account owning the EDS as configured. It fits when:

- An independent account needs its own investigation store.
- A workload/team has separate ownership and retention.
- Data scope does not need organization-wide consolidation.

### 6.2. Organization EDS

An organization EDS is created by the management account or an authorized delegated administrator. When applied to the organization, the EDS automatically covers member accounts as configured and can collect across multiple Regions.

Member accounts cannot directly view, modify, or delete an organization EDS. Query permissions must be granted separately; by default, member accounts do not have permission to query the organization's EDS.

~~~mermaid
flowchart TD
    ORG["AWS Organizations"]
    ORG --> MGMT["Management account"]
    ORG --> A["Member account A"]
    ORG --> B["Member account B"]
    ORG --> C["Member account C"]
    MGMT --> EDS["Organization Event Data Store"]
    A --> EDS
    B --> EDS
    C --> EDS
    EDS --> QUERY["Central investigation queries"]
~~~

### 6.3. Management account and delegated administrator

The management account retains ownership of the organization EDS. A delegated administrator can perform many administrative and query operations as defined by AWS permissions, though some actions are restricted to the management account, such as copying trail events into an organization EDS and certain EDS type conversion operations.

Design delegated administrators with least privilege. Do not grant organization-wide permissions just because a team needs to run a few queries.

### 6.4. Important note after 31-05-2026

AWS announced that existing customers continue to be supported for existing EDSs. However, if an organization only has account-level EDSs, CloudTrail Lake does not ingest for new member accounts added after the new-customer closure date. To cover new accounts, existing organizations need an organization EDS or to transition to the AWS-recommended Amazon CloudWatch architecture. Do not assume an account-level EDS automatically expands to every account joining the organization after this milestone.

## 7. Creating and configuring an Event Data Store

This section applies to accounts that already have access to CloudTrail Lake. Before creating an EDS, clearly define:

- What data needs investigation and which event categories must be collected.
- Which accounts/Regions are in scope.
- Which selectors capture sufficient evidence without ingesting unnecessary data.
- Retention period and pricing option.
- Who can create, edit, query, and delete the EDS.
- Whether an organization EDS, federation, or resource-based access is needed.

### 7.1. Creating an EDS for management events via AWS CLI

~~~bash
aws cloudtrail create-event-data-store \
  --name security-management-events \
  --advanced-event-selectors '[{"Name":"Management events","FieldSelectors":[{"Field":"eventCategory","Equals":["Management"]}]}]' \
  --multi-region-enabled \
  --retention-period 366 \
  --billing-mode EXTENDABLE_RETENTION_PRICING \
  --termination-protection-enabled \
  --region ap-southeast-1
~~~

This example illustrates an account-level EDS for management events across multiple Regions, with a default retention of 366 days under the extendable retention pricing option. Check supported CLI options in your account/Region and current pricing before running. Do not use EDS creation commands as a sign-up guide for new customers after 31-05-2026.

### 7.2. Creating an EDS for data events

An EDS can use advanced selectors to collect data events for resources requiring auditing. The JSON selector example in section 5.2 can be passed to `--advanced-event-selectors`. When designing, verify:

- Exact resource ARN and event source.
- Whether to select read, write, or both.
- Whether selectors accidentally exclude valid operations needed for investigation.
- Whether expected volume fits the budget.
- Whether service/Region data event coverage meets requirements.

### 7.3. Creating an organization EDS

For organizations already using CloudTrail Lake, the management account or delegated administrator can create an organization EDS using `--organization-enabled` per AWS permission rules. General example:

~~~bash
aws cloudtrail create-event-data-store \
  --name organization-management-events \
  --organization-enabled \
  --multi-region-enabled \
  --retention-period 366 \
  --billing-mode EXTENDABLE_RETENTION_PRICING \
  --termination-protection-enabled \
  --region ap-southeast-1
~~~

The example illustrates default management events configuration. If data events, network activity events, or Insights are needed, add appropriate event selectors. An organization EDS is owned in the management account even when initiated by a delegated administrator.

### 7.4. Inspecting the created EDS

~~~bash
aws cloudtrail list-event-data-stores \
  --region ap-southeast-1

aws cloudtrail get-event-data-store \
  --event-data-store <event-data-store-arn-or-id> \
  --region ap-southeast-1
~~~

Check status, ARN, organization setting, multi-Region setting, advanced selectors, retention, billing mode, termination protection, and ingestion status. Record the EDS ARN/ID in your operational inventory.

### 7.5. Ingestion status and termination protection

An EDS can be configured to start or stop ingesting events. Stopping ingestion does not delete existing data; it prevents the EDS from receiving new events. Termination protection helps prevent accidental EDS deletion, especially for central audit stores.

Do not stop ingestion during an incident just to save costs without assessing impact: stopping can create an audit gap right when evidence is needed. If cost reduction is required, review selectors and event volume under a change plan.

## 8. Retention, pricing, and cost control

CloudTrail Lake incurs ingestion, retention, and query costs. Costs depend on event volume/type, pricing option, retention duration, and data scanned by queries. There is no single fixed number across all Regions and event types.

### 8.1. Two pricing options

CloudTrail Lake has two retention pricing options:

| Pricing option | Characteristics | When to consider |
| --- | --- | --- |
| One-year extendable retention | Includes an initial one-year storage period; retention can be extended up to about 10 years within service limits | Workloads ingesting less than about 25 TB/month and needing flexible retention |
| Seven-year retention | Includes long-term retention of about 7 years; cannot extend beyond option limits | Workloads ingesting more than about 25 TB/month and needing long-term retention |

These thresholds/retentions are guidelines based on AWS's pricing model at the time of writing. Check the current pricing page before deciding; the minimum EDS retention period is 7 days, and pricing is calculated by data type/volume.

### 8.2. Cost drivers

- **Ingestion:** data ingested into the EDS.
- **Retention:** data volume stored according to pricing option and retention period.
- **Query:** volume of data scanned by SQL queries.
- **Federation:** enabling federation itself incurs no CloudTrail Lake fee; queries run in Athena incur Athena charges.
- **Historical copy:** copying trail events into an EDS is billed by uncompressed volume ingested.

Do not assume gzip object size in S3 equals CloudTrail Lake ingestion volume. When copying trail events, data is decompressed; AWS provides rough estimates indicating uncompressed size can be significantly larger than compressed objects.

### 8.3. Reducing cost with selectors

- Collect data events for critical buckets/tables/functions.
- Enable only event sources needed for the use case.
- Avoid ingesting every resource in every account if unnecessary.
- Review selectors periodically as workloads change.
- Use an organization EDS when centralized coverage is needed and fits permissions/availability.
- Separate short-term investigation stores from long-term archives if architecture and policy require.

### 8.4. Reducing query cost

- Always filter `eventTime` to a specific time window.
- Select only needed columns instead of `SELECT *`.
- Add filters on `eventSource`, `eventName`, `awsRegion`, `userIdentity.arn` to narrow the result set.
- Start with a small time window, then expand as hypotheses require.
- Monitor `BytesScanned` and runtime in query metadata.
- Avoid repeatedly running store-wide queries in dashboards or automation.

Filtering on `eventTime` reduces scanning on a best-effort basis; it does not guarantee every query only reads data within the time range. Some queries may still scan more data than expected.

### 8.5. Retention and historical copy

When copying historical trail events into an EDS, CloudTrail only copies events whose `eventTime` falls within the EDS's retention period. If you want to copy events 45 days old and keep them for another 45 days after copying, retention must cover both the data's age at copy time and the additional retention duration.

If an EDS is used solely for historical analysis, you can stop ingesting new events after copying completes to avoid unintended ingestion. Check copy duration, failed record status, and avoid copying periods overlapping with direct ingestion.

## 9. CloudTrail Lake SQL: structure and rules

CloudTrail Lake queries use SQL with Trino-based syntax. Only `SELECT` statements are permitted; queries cannot modify or delete data in an EDS.

Query template:

~~~sql
SELECT
    eventTime,
    eventSource,
    eventName,
    userIdentity.arn AS actor
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
ORDER BY
    eventTime DESC
LIMIT 100;
~~~

Replace `event-data-store-id` with the ID (the trailing portion of the ARN) of the EDS. The CloudTrail console usually populates FROM automatically when you pick an EDS in the query editor.

### 9.1. SQL constraints

- Use SELECT statements only.
- Use syntax and functions supported by CloudTrail Lake; do not assume all Trino features are available.
- `FROM` specifies the EDS ID; multiple EDSs can be queried using supported JOINs when needed.
- Use `LIMIT` to avoid returning overly large results.
- Use `eventTime` to bound the time window; an EDS has a minimum 7-day retention, so valid time windows must also be considered.
- Nested fields like `userIdentity.arn` can be accessed according to the event schema.

### 9.2. Choosing the right timestamp field

`eventTime` is when the AWS API event occurred. During investigations, use it as the primary timeline axis. Do not confuse it with when the object was delivered to S3, ingested into the EDS, or when the query ran.

Timestamps in CloudTrail are typically represented in UTC. Convert to the incident timeline's timezone consistently and explicitly note the timezone.

### 9.3. Queries can time out or return too much data

Queries running longer than the runtime limit may time out; in some cases partial results may still exist. Queries returning too many rows or overly large aggregations may hit response size/resource exhaustion errors. Split into smaller time ranges, select fewer columns, and aggregate early.

## 10. Common investigation queries

The following queries are templates for an EDS already collecting the right event category. Replace EDS ID, account, Region, actor, and time window with incident specifics. Field names/casing and nested paths must match the EDS schema.

### 10.1. Listing a principal's activity

~~~sql
SELECT
    eventTime,
    eventSource,
    eventName,
    awsRegion,
    sourceIPAddress,
    userAgent,
    errorCode,
    eventID
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND userIdentity.arn =
        'arn:aws:sts::111122223333:assumed-role/DeploymentRole/deployment-session'
ORDER BY
    eventTime DESC
LIMIT 500;
~~~

Use this query to list a session's activities. If the session ARN changes, search additionally by role issuer ARN or principal ID; do not assume a user always uses the same session name.

### 10.2. Finding successful and failed console logins

~~~sql
SELECT
    eventTime,
    userIdentity.type,
    userIdentity.arn,
    sourceIPAddress,
    userAgent,
    responseElements,
    errorCode,
    errorMessage
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND eventSource = 'signin.amazonaws.com'
    AND eventName = 'ConsoleLogin'
ORDER BY
    eventTime DESC
LIMIT 500;
~~~

`ConsoleLogin` typically has a status field in the response or error fields depending on the outcome. Check both `responseElements.ConsoleLogin` and `errorMessage` if present; do not assume every event without `errorCode` is a successful login without checking schema/context.

### 10.3. Finding IAM privilege creation or changes

~~~sql
SELECT
    eventTime,
    userIdentity.arn AS actor,
    eventName,
    requestParameters,
    responseElements,
    sourceIPAddress,
    userAgent,
    errorCode
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-19 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND eventSource = 'iam.amazonaws.com'
    AND eventName IN (
        'CreateAccessKey',
        'CreateLoginProfile',
        'CreatePolicy',
        'CreatePolicyVersion',
        'AttachRolePolicy',
        'AttachUserPolicy',
        'PutRolePolicy',
        'PutUserPolicy',
        'AddUserToGroup',
        'UpdateAssumeRolePolicy'
    )
ORDER BY
    eventTime DESC
LIMIT 1000;
~~~

Focus on permission changes that can escalate privileges. Read `requestParameters` to identify the policy/role/user; if a `policyArn` or policy document is present, compare it against the approved baseline.

### 10.4. Investigating AssumeRole

~~~sql
SELECT
    eventTime,
    userIdentity.arn AS caller,
    userIdentity.type AS callerType,
    requestParameters.roleArn AS targetRole,
    requestParameters.roleSessionName AS sessionName,
    requestParameters.externalId AS externalId,
    sourceIPAddress,
    userAgent,
    errorCode
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND eventSource = 'sts.amazonaws.com'
    AND eventName = 'AssumeRole'
ORDER BY
    eventTime DESC
LIMIT 500;
~~~

This query finds role assumptions. To trace actions after assuming the role, subsequent queries should search for events with the corresponding assumed-role ARN/principal ID in `userIdentity`.

### 10.5. Finding security group changes

~~~sql
SELECT
    eventTime,
    userIdentity.arn AS actor,
    eventName,
    requestParameters,
    sourceIPAddress,
    awsRegion,
    errorCode
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND eventSource = 'ec2.amazonaws.com'
    AND eventName IN (
        'AuthorizeSecurityGroupIngress',
        'AuthorizeSecurityGroupEgress',
        'RevokeSecurityGroupIngress',
        'RevokeSecurityGroupEgress',
        'ModifySecurityGroupRules'
    )
ORDER BY
    eventTime DESC
LIMIT 500;
~~~

Inspect CIDR, port range, protocol, and security group ID in request parameters. A `0.0.0.0/0` rule opening administrative or database ports requires urgent verification.

### 10.6. Finding S3 object access

~~~sql
SELECT
    eventTime,
    userIdentity.arn AS actor,
    eventName,
    requestParameters.bucketName,
    requestParameters.key,
    sourceIPAddress,
    userAgent,
    errorCode
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND eventSource = 's3.amazonaws.com'
    AND eventCategory = 'Data'
    AND eventName IN ('GetObject', 'PutObject', 'DeleteObject')
ORDER BY
    eventTime DESC
LIMIT 1000;
~~~

This query only returns results if the EDS has ingested corresponding S3 data events. S3 management events are insufficient to prove who read an object.

### 10.7. Finding failed API calls

~~~sql
SELECT
    eventTime,
    userIdentity.arn AS actor,
    eventSource,
    eventName,
    sourceIPAddress,
    errorCode,
    errorMessage
FROM
    event-data-store-id
WHERE
    eventTime >= TIMESTAMP '2026-11-20 00:00:00'
    AND eventTime < TIMESTAMP '2026-11-21 00:00:00'
    AND errorCode IS NOT NULL
ORDER BY
    eventTime DESC
LIMIT 500;
~~~

Errors can reflect legitimate activity such as policy evaluation denials, nonexistent resources, or quotas. Group by actor, source, API, and error code before concluding malicious activity.

## 11. Building a timeline and correlating events

A single isolated event rarely tells the whole story. Good investigations combine multiple events across actor, session, resource, and time.

### 11.1. Starting from a suspicious event

When detecting a sensitive change, record:

- `eventID`, `requestID`, and `eventTime`.
- `eventSource`, `eventName`, `awsRegion`.
- `userIdentity.type`, `userIdentity.arn`, `principalId`.
- `sessionContext.sessionIssuer.arn` if present.
- `sourceIPAddress`, `userAgent`.
- `requestParameters`, `responseElements`, `errorCode`.
- Affected resource ARN/ID.

This serves as the anchor to expand queries. Do not rely on display names or session names alone because they can be reused.

### 11.2. Tracing the AssumeRole chain

An investigation may require tracing a chain:

~~~mermaid
flowchart TD
    LOGIN["ConsoleLogin / Identity Center sign-in"]
    STS["STS AssumeRole"]
    SESSION["Assumed-role session"]
    ACTION["IAM / EC2 / S3 API calls"]
    CHANGE["Sensitive resource change"]
    LOGIN --> STS --> SESSION --> ACTION --> CHANGE
~~~

Investigation sequence:

1. Find the related sign-in or federation event.
2. Find `AssumeRole` in STS and identify the caller, target role, session name, and external ID if present.
3. Find API events with `userIdentity.arn` or principal ID matching the assumed-role session.
4. Check `sessionIssuer` to identify the IAM role that issued the credentials.
5. Compare `sourceIPAddress`, `userAgent`, MFA context, and session time.
6. Cross-reference with deployment pipelines, change tickets, or approved automation activities.

With IAM Identity Center, web identity, service roles, or chained role sessions, the root actor may appear in `onBehalfOf`, `sourceIdentity`, `inScopeOf`, or an earlier STS event. Not every session type has the exact same fields.

### 11.3. Finding actions occurring around an event

Once you have the event time, run queries with a narrow window before/after the event, such as 15 minutes. Expand the window if:

- There are multi-step provisioning or deployment tasks.
- A role was assumed much earlier.
- Event delivery was delayed.
- The event spans multiple Regions or accounts.

Preserve UTC event times, not just ingestion/query times. Sort the timeline by `eventTime` and retain event IDs so records can be retrieved again.

### 11.4. Correlating with other data sources

CloudTrail is a control-plane audit trail, not complete workload telemetry. Depending on the hypothesis, correlate with:

| Source | Supplementary evidence |
| --- | --- |
| AWS Config | Current resource configuration and recorded change history |
| GuardDuty | Behavioral findings or threat indicators |
| VPC Flow Logs | Network flows, source/destination IPs, ports, bytes |
| CloudWatch Logs | Application/system logs and runtime errors |
| IAM Access Analyzer | External access, policy exposure, and trust relationships |
| S3 server access logs / S3 data events | Object access activity per configuration |
| CI/CD audit logs | Who triggered which pipeline, commit, and deployment |

Do not draw conclusions from a single IP, user agent, or event. Combine multiple sources and verify change management context.

## 12. Running queries and managing results

The CloudTrail console provides a Query Editor, Sample queries, and Saved queries. The AWS CLI can be used to run queries in automation or incident runbooks.

### 12.1. Running queries in the console

1. Open the CloudTrail console and select Lake → Query.
2. Choose Sample queries or create a new query.
3. Select the EDS to analyze.
4. Add `eventTime` start/end and filters by event source/action/actor.
5. Run the query and monitor status.
6. Review Query results, row count, and execution metadata.
7. Save the query as a saved query if it needs reuse.

Sample queries are a starting point. Adjust actor, time range, event source, and account to the incident; do not run unbounded queries verbatim against large stores.

### 12.2. Running queries with the AWS CLI

~~~bash
aws cloudtrail start-query \
  --query-statement "SELECT eventTime, eventSource, eventName, userIdentity.arn FROM event-data-store-id WHERE eventTime >= TIMESTAMP '2026-11-20 00:00:00' AND eventTime < TIMESTAMP '2026-11-21 00:00:00' LIMIT 100" \
  --region ap-southeast-1
~~~

The command returns a `QueryId`. Use this ID to track progress:

~~~bash
aws cloudtrail describe-query \
  --query-id <query-id> \
  --region ap-southeast-1

aws cloudtrail get-query-results \
  --query-id <query-id> \
  --region ap-southeast-1
~~~

Check query status, error message, result count, runtime, and `BytesScanned`. If a query runs too long, consider cancelling or splitting the time range.

### 12.3. Cancelling a query

~~~bash
aws cloudtrail cancel-query \
  --query-id <query-id> \
  --region ap-southeast-1
~~~

Cancelling a query does not delete data in the EDS. Use it when a query runs with the wrong scope or scans more data than intended.

### 12.4. Saving results to S3

Query results can be saved to S3 for sharing with the incident response team or archiving with investigation records. When delivering to S3:

- The bucket must be in a Region/account supported for the operation.
- The bucket policy must allow CloudTrail to write results.
- Encryption, bucket ownership, and lifecycle must follow security standards.
- Restrict read permissions on results since they may contain principal ARNs, IPs, resource names, and request parameters.
- Record the query statement, EDS ID, time range, query ID, and export timestamp.

Do not treat exported CSV files as self-authenticating evidence. Use CloudTrail's validation mechanism and the organization's evidence handling procedures.

### 12.5. Saved queries and runbooks

Name queries after investigation questions, for example:

~~~text
IR-01-ConsoleLoginFailures
IR-02-IAMPrivilegeChanges
IR-03-AssumeRoleChain
IR-04-PublicSecurityGroupChanges
IR-05-S3SensitiveObjectAccess
~~~

Document the event coverage scope, EDS ID, time range, and fields to substitute. Query templates do not replace incident-specific validation.

## 13. Federation to Athena

CloudTrail Lake can federate an Event Data Store to query event data with Amazon Athena. Federation registers EDS metadata in the AWS Glue Data Catalog and uses AWS Lake Formation to manage permissions to federated data.

~~~mermaid
flowchart LR
    EDS["CloudTrail Lake EDS"]
    GLUE["AWS Glue Data Catalog"]
    LF["AWS Lake Formation"]
    ATHENA["Amazon Athena"]
    EDS --> GLUE
    GLUE --> LF
    LF --> ATHENA
    ATHENA --> RESULTS["Query results in S3"]
~~~

### 13.1. How federation works

- CloudTrail creates or uses the managed database `aws:cloudtrail` in the Glue Data Catalog.
- A federated table is created for the EDS.
- CloudTrail registers the federation role and EDS with Lake Formation.
- Athena uses that metadata to locate, read, and process data.

Federation is useful when a team already has Athena workflows, needs to join data with other tables, or wants to use existing analytics tools.

### 13.2. Access permissions

Athena query users need:

- Athena permissions to run queries and read results.
- Appropriate Glue Data Catalog permissions.
- Lake Formation permissions on the federated database/table and data access.
- IAM permission `lakeformation:GetDataAccess` per AWS guidance.
- Permissions to write query results to the Athena result bucket.

The federation role requires minimal permissions to manage Glue/Lake Formation resources. If the role is deleted or Lake Formation/Glue permissions are revoked, Athena queries may fail.

### 13.3. Cost and lifecycle

Enabling federation incurs no CloudTrail Lake charge; queries in Athena incur charges based on data scanned by Athena. Optimize Athena queries and S3 result storage separately.

When federation is enabled, an EDS cannot be deleted directly. Before deleting, you must disable federation and turn off termination protection if enabled. Disabling federation only turns off the Glue/Lake Formation/Athena integration; CloudTrail Lake data is not deleted and can still be queried in CloudTrail Lake.

### 13.4. When is federation unnecessary?

If analysts only need SQL queries inside CloudTrail Lake, using the Query Editor directly can be simpler. Only enable federation when there is an actual Athena/Lake Formation requirement; adding another integration layer adds roles, policies, catalogs, and costs to manage.

## 14. Resource-based policies and cross-account queries

An Event Data Store supports a resource-based policy to allow principals in another account to perform certain operations on the EDS. This fits when the security account owns the EDS, while analysts or a delegated team in another account need to query it.

### 14.1. Actions grantable via an EDS resource policy

CloudTrail supports a specific set of actions on an EDS, including:

- `cloudtrail:StartQuery`.
- `cloudtrail:CancelQuery`.
- `cloudtrail:ListQueries`.
- `cloudtrail:DescribeQuery`.
- `cloudtrail:GetQueryResults`.
- `cloudtrail:GenerateQuery`.
- `cloudtrail:GenerateQueryResultsSummary`.
- `cloudtrail:GetEventDataStore`.

A resource policy does not grant full EDS administrative permissions. Permissions to create, edit, or delete the EDS and the caller's IAM permissions must still be managed separately.

### 14.2. Example allowing an account to query an EDS

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSecurityAnalystAccountToQuery",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::444455556666:root"
      },
      "Action": [
        "cloudtrail:StartQuery",
        "cloudtrail:CancelQuery",
        "cloudtrail:ListQueries",
        "cloudtrail:DescribeQuery",
        "cloudtrail:GetQueryResults",
        "cloudtrail:GetEventDataStore"
      ],
      "Resource": "arn:aws:cloudtrail:ap-southeast-1:111122223333:eventdatastore/example-eds-id"
    }
  ]
}
~~~

This example allows principals in account `444455556666` who hold identity permissions to use the listed query actions on the EDS owned by account `111122223333`. In production, you can specify a concrete role ARN instead of the account root to narrow the trust boundary. The shared account still needs an identity policy allowing the corresponding actions.

### 14.3. Attaching a resource policy via CLI

~~~bash
aws cloudtrail put-resource-policy \
  --resource-arn arn:aws:cloudtrail:ap-southeast-1:111122223333:eventdatastore/example-eds-id \
  --resource-policy file://eds-resource-policy.json \
  --region ap-southeast-1
~~~

Ensure the policy targets the exact EDS ARN, Region, and approved principal. After sharing, test using a test role in the consumer account; verify both the identity policy and resource policy.

### 14.4. Resource policy vs. organization delegated access

An organization EDS may have a default resource policy managed by CloudTrail to reflect delegated administrator permissions in AWS Organizations. When delegated administrators or organization configuration change, this policy can be updated automatically.

Do not overwrite the CloudTrail-managed policy without understanding its impact on delegated administrators and dashboards.

### 14.5. Principles for safe sharing

- Only share the necessary query/read actions.
- Do not grant delete or ingestion modification permissions to analysts who only need to investigate.
- Use specific roles, short session durations, and MFA/Identity Center per policy.
- Monitor query usage and scan costs.
- Restrict access to EDSs containing the exact required data scope; separate EDSs if different security boundaries are needed.

## 15. Preserving and verifying query results

In incident response, query results are often attached to tickets, forensic records, or compliance reports. You must protect both the result contents and proof that the files were not altered after CloudTrail generated them.

### 15.1. CloudTrail query results integrity validation

When saving query results to S3, CloudTrail can write:

- One or more gzipped CSV result files.
- A signature file `result_sign.json` containing the hash of each result file and a digital signature.

CloudTrail uses SHA-256 to hash file contents and SHA-256 with RSA to sign the hash information. This mechanism helps detect result files that were modified, deleted, or have an invalid signature after CloudTrail delivered them.

### 15.2. Verifying with the AWS CLI

~~~bash
aws cloudtrail verify-query-results \
  --s3-bucket audit-evidence-bucket \
  --s3-prefix cloudtrail-lake/query/incident-2026-11-20/ \
  --region ap-southeast-1
~~~

If you have downloaded both the result files and the signature file locally, you can verify locally:

~~~bash
aws cloudtrail verify-query-results \
  --local-export-path ./incident-query-results/ \
  --region ap-southeast-1
~~~

The command requires AWS CLI v2. When verifying locally, keep the original filenames and place the result files together with the signature file in the specified directory. When verifying in S3, the prefix must contain the original files and signature file; do not rename them.

### 15.3. Interpreting validation results

| Result | Meaning |
| --- | --- |
| Sign file validated successfully | Signature file is valid; each result file's hash can be checked |
| Hash mismatch | Result file content does not match the hash in the signature file |
| Invalid signature | Signature of the sign file is invalid |
| File missing | A file referenced by the sign file is no longer at the expected location |

Validation proves the integrity of the query result files signed by CloudTrail; it does not prove the query selected the right EDS, time range, selectors, or investigative hypothesis. Save the query statement, EDS ID, query ID, event time window, operator, and query rationale alongside the files.

### 15.4. Chain of custody for evidence

- Store originals in a dedicated S3 bucket with encryption enabled and restricted write/delete permissions.
- Use S3 Versioning/Object Lock when compliance requirements and the storage model fit.
- Keep `result_sign.json` together with result files.
- Record who ran the query, when, which EDS, and which query statement.
- Log all download, copy, transfer, or data processing actions.
- Verify integrity before using results in forensic reports.
- Restrict sharing raw event payloads since they may contain sensitive details.

Query result integrity validation does not replace CloudTrail Trail log file integrity validation. The two mechanisms apply to two different types of evidence: query outputs and log files delivered by a Trail.

## 16. Account activity investigation workflow

An incident runbook should start with a hypothesis and evidence, not by running a massive query. The workflow below fits suspected events such as unauthorized access key creation, attaching admin policies, opening security groups, or reading sensitive data.

### 16.1. Triage and scoping

1. Record the alert/finding, reporting source, and detection timestamp.
2. Identify the relevant account, Region, resource, actor, or API.
3. Choose an initial time window before/after the event.
4. Check whether the EDS collects the necessary event categories and selectors.
5. Determine whether data might be delayed in ingestion or uncollected due to selectors.

Do not conclude "no events" means "no activity" before confirming event coverage, Region, account, retention, and ingestion status.

### 16.2. Building the initial timeline

Find the primary event, then expand:

- 15–30 minutes before the event to find sign-ins, AssumeRole, or permission changes.
- During the event window to find API calls by the same actor/resource.
- 15–60 minutes after the event to find follow-up actions or cleanup.
- Longer time windows if the session was assumed earlier or event delivery was delayed.

Save query statements and event IDs. Use UTC as the standard and note any timezone conversions.

### 16.3. Identifying actor and session

- Inspect `userIdentity.type`, `arn`, `principalId`, `accountId`.
- If `AssumedRole`, inspect `sessionIssuer`, `sourceIdentity`, session name, and STS events.
- Check `mfaAuthenticated` if present.
- Cross-check `sourceIPAddress`, `userAgent`, `awsRegion`, and session creation time.
- Determine whether the activity came from a human, CI/CD, workload, or AWS service.

An unfamiliar `userAgent` or new IP is a signal to investigate, not a standalone conclusion. Compare against baselines and change schedules.

### 16.4. Determining impact

Answer:

- Which APIs were called and did they succeed?
- Which resources were created, modified, deleted, or accessed?
- Which policies/roles/permissions changed?
- Were there data events involving objects, tables, or functions?
- Were there network changes or anomalous traffic?
- Were subsequent API calls made using the newly granted permissions?

Read `requestParameters` to understand intent and `responseElements` to understand outcome if those fields are recorded. Cross-check resource state with AWS Config/current APIs when needed.

### 16.5. Testing hypotheses and expanding

Example hypothesis: "A role was attached `AdministratorAccess` outside a change window".

1. Find the `AttachRolePolicy` or `PutRolePolicy` event.
2. Identify the actor/session and target role.
3. Find the STS AssumeRole event that created that session.
4. Find preceding sign-in activity or pipeline triggers.
5. Find API calls made after the privilege change.
6. Check for created resources, read data, or disabled security controls.
7. Cross-reference CloudTrail with GuardDuty, Config, CloudWatch Logs, and CI/CD audit logs.
8. Verify whether the change has a valid ticket/approval and owner.

### 16.6. Containment and evidence

If there are signs of compromise, coordinate with the incident commander/security owner to:

- Disable or rotate credentials per approved runbooks.
- Revoke session/role access where appropriate.
- Restore policies or network rules to a safe baseline.
- Preserve EDSs, Trail logs, query results, Config history, and workload evidence.
- Avoid deleting resources or logs before collecting needed evidence.
- Document who performed containment, when, and why.

CloudTrail Lake is an investigation tool, not a containment tool. Actions changing IAM/networking must follow incident response and change control procedures.

### 16.7. Closing the incident

The closure record should include:

- Incident timeline with UTC timestamps and event IDs.
- Actor/session chain and account/Region scope.
- Affected resources and actions taken.
- Query statements and verified query results.
- Evidence from other sources and confidence level for each finding.
- Root cause, containment/recovery actions, and preventive controls.
- Logging/selector gaps discovered and remediation plans.

## 17. Current availability and transition path to CloudWatch

As of 31-05-2026, CloudTrail Lake is closed to new customers. AWS CloudTrail itself remains supported; Trails, Event history, Insights, and Aggregated Events are unaffected. Existing CloudTrail Lake deployments continue operating, though they only receive critical bug fixes and security updates. AWS recommends Amazon CloudWatch for similar collection, storage, and analytics capabilities.

### 17.1. Which architecture should new customers learn?

Organizations that have never used CloudTrail Lake should design CloudTrail Trails and an Amazon CloudWatch architecture per current AWS documentation. CloudWatch can unify security, operations, and compliance telemetry; it supports OCSF/OTel, pipelines/transformations, OpenSearch-backed analytics, Logs Insights, and broad data source integrations.

CloudWatch is the AWS-recommended replacement architecture, though it is not an exact feature-for-feature replica:

| Capability | CloudTrail Lake | CloudWatch architecture |
| --- | --- | --- |
| CloudTrail management/data events | Yes | Yes via supported ingestion mechanisms |
| Network activity and Insights events | Yes within supported EDS scope | Not listed as equivalent coverage in current migration comparisons |
| SQL analytics | SQL in EDS, supporting complex nested queries | Logs QL, SQL, and PPL with analytics/OpenSearch |
| Data normalization | More limited | Supports OCSF/OTel and supported transformations |
| Third-party sources | Integrations per CloudTrail Lake | Published CloudWatch pipelines/connectors |
| Cross-account/Region | Has organization EDS mechanism | Has centralization; enablement may require per-Region configuration |

Before designing a new setup, build a coverage matrix based on actual event sources. If your use case requires Network Activity or Insights events, keep CloudTrail Trails/Insights and select additional appropriate data sources; do not assume a CloudWatch pipeline automatically replaces every event category.

CloudWatch pipelines and certain connectors are only available in Regions published by AWS. Check Region availability and service quotas where workloads reside before finalizing architecture; Singapore (`ap-southeast-1`) is in the current supported Region list for CloudWatch pipelines.

### 17.2. Existing CloudTrail Lake customers

AWS recommends migrating log data from CloudTrail Lake to Amazon CloudWatch. A safe plan:

1. Inventory EDSs, event categories, selectors, account/Region scope, and retention.
2. List saved queries, dashboards, federation, cross-account policies, and downstream consumers.
3. Choose a small EDS or short time window for a migration pilot.
4. Export historical EDS data into a CloudWatch log group using the AWS-supported workflow.
5. Verify schemas/fields, retention, IAM permissions, and query results.
6. Measure sample ingestion volume/cost before migrating everything.
7. Transition dashboards, alerts, query runbooks, and access roles.
8. Enable live CloudTrail ingestion into CloudWatch per the AWS-recommended architecture.
9. Retain the EDS/S3 archive per legal requirements and for unmigrated data windows.
10. Only retire legacy integrations after consumers, evidence, and retention are verified.

### 17.3. Pilot migration and historical limits

AWS recommends piloting with a small dataset to verify:

- Logs appear properly in the CloudWatch log group.
- Schema/field mappings satisfy queries and dashboards.
- IAM roles and permissions work.
- Ingestion cost is estimated from a sample, such as 24 hours.
- Logs Insights queries can replace key investigative questions.

Under current migration guidance, pre-2023 data is not migrated from CloudTrail Lake to CloudWatch via this import workflow. If you need access to older data, continue querying it directly in the existing EDS or transfer/archive it to S3 under a separate plan.

### 17.4. Importing historical EDS data via AWS CLI

AWS provides an API to import from an EDS into CloudWatch Logs. Example:

~~~bash
aws logs create-import-task \
  --import-source-arn arn:aws:cloudtrail:ap-southeast-1:111122223333:eventdatastore/example-eds-id \
  --import-role-arn arn:aws:iam::111122223333:role/CloudTrailLakeExportRole \
  --import-filter '{"startEventTime":1795046400000,"endEventTime":1795132800000}' \
  --region ap-southeast-1
~~~

`startEventTime` and `endEventTime` are Unix epoch milliseconds, not ISO-8601 strings. The example above scopes roughly from 19-11-2026 00:00 UTC to 20-11-2026 00:00 UTC. The import task runs asynchronously; monitor it using `aws logs describe-import-tasks` with the returned import ID.

The import role must trust the `cloudtrail.amazonaws.com` principal and have least-privilege permissions to read the EDS and create log groups/streams and write resource policies; if the EDS uses a customer-managed KMS key, corresponding KMS permissions are required. The API caller needs access to the source EDS, `logs:CreateImportTask`, and `iam:PassRole` permissions. AWS limits accounts to at most three active import tasks at a time; the source EDS must be ACTIVE and the time range must fall within retention. Check prerequisites, role trust/policies, and quotas in the [CreateImportTask API](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_CreateImportTask.html) before running.

### 17.5. What not to do during migration

- Do not delete the old EDS immediately after creating an import task.
- Do not disable Trail logging before verifying CloudWatch live ingestion receives full event coverage.
- Do not assume all event categories and schemas map one-to-one.
- Do not ignore pre-2023 data if investigation/retention obligations apply.
- Do not migrate dashboards/queries before the pilot confirms field mappings.
- Do not retire federation, resource policies, or saved queries before a replacement owner is in place.

### 17.6. Official migration documentation

AWS maintains guidance on [CloudTrail Lake availability change and migration options](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-service-availability-change.html). Use this guide as the authoritative reference for export/import steps, role permissions, data scope, and currently supported limitations.

## 18. Investigation troubleshooting

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| **Event not found** | Wrong EDS/Region, selector not capturing event, wrong time range, or event not yet ingested | Verify EDS ARN, event coverage, UTC time range, and ingestion status |
| **Management events exist, but S3 object access is missing** | EDS/Trail does not have S3 data events enabled for the bucket/prefix | Check advanced event selectors and data event configuration |
| **Query returns 0 rows** | Wrong filter on `eventSource`, `eventName`, actor ARN, or casing/field path | Run a narrow query by time range, remove filters one by one, and inspect a sample event |
| **Query scans too much data** | Missing `eventTime`, using `SELECT *`, or overly broad time range | Bound the time range, select only needed columns, add filters early |
| **Query response too large** | Too many rows or aggregation producing an oversized result | Add `LIMIT`, split time range, drop redundant `array_agg`, or aggregate concisely |
| **Query exhausted resources** | Joins/aggregations/window functions processing too large a dataset | Split into smaller time windows, reduce joins, and retry per AWS guidance |
| **Cannot query organization EDS** | Member account principal lacks permissions or delegated admin not configured | Check management/delegated administrator, resource policy, and identity policy |
| **Cross-account query gets AccessDenied** | EDS resource policy or identity policy missing action | Check principal, EDS ARN, supported actions, and account ID |
| **Athena cannot see EDS table** | Federation not enabled or Glue/Lake Formation permissions incorrect | Check federation role, Glue database/table, and Lake Formation grants |
| **Cannot delete EDS** | Federation or termination protection still enabled | Disable federation first, then turn off termination protection per procedure |
| **Cannot change retention/export** | Export in use or configuration locked by pricing/lifecycle | Check importers, EDS settings, and pricing option constraints |
| **Historical copy failed** | Incorrect S3 bucket/KMS policy, object storage class, or role permissions | Check `GetObject`, KMS decrypt, S3 bucket policy, and object restore |
| **Query results cannot be verified** | File renamed, missing sign file, or content modified | Use original files and sign file; check S3 prefix, Region, and AWS CLI v2 |
| **CloudWatch import task error** | Role lacks permissions, wrong source ARN, or invalid import filter | Check role trust/policy, EDS ARN, and task status |

### 18.1. Query returns 0 rows: step-by-step troubleshooting

1. Run a query filtering only on `eventTime` for a window guaranteed to have activity.
2. Add only `eventSource`.
3. Add `eventName`.
4. Add actor ARN after verifying the actual value in an event.
5. Verify the event category matches what the EDS is ingesting.
6. Verify account/Region and event delivery timing.

Do not fix a query by immediately opening an unbounded time range. Identify which condition drops the results and inspect a sample event.

### 18.2. Checking event coverage before concluding

If there is no S3 `GetObject` event, possible reasons include:

- Data events are not enabled for the bucket/prefix.
- The selector only captures write events.
- The EDS was created after the action occurred.
- The EDS is ingesting in a different Region/account.
- The event is outside retention.

CloudTrail Lake can only query data that was ingested or historical data that was successfully copied.

### 18.3. Investigating missing data during copy

When copying Trail events from S3 into an EDS:

- CloudTrail reads gzip-compressed CloudTrail log files in S3.
- Some archived storage classes require restoring objects before reading.
- The bucket policy must allow CloudTrail to read objects.
- If S3 uses SSE-KMS, the key policy must allow required decrypt/generate data key operations.
- Choose a time range fitting within the EDS retention.
- Check copy status and retry failures per guidance.

## 19. Case study: investigating an unplanned admin privilege grant

### 19.1. Context

The security team receives an alert that `ApplicationRole` just had `AdministratorAccess` attached in the evening, outside the deployment window. An organization EDS is collecting management events across multiple accounts/Regions; S3 data events are enabled for sensitive data buckets.

### 19.2. Investigative hypotheses

- An actor attached the admin policy.
- The actor used an assumed-role session from an unfamiliar source.
- The newly privileged role was used to modify resources or read data.

### 19.3. Step 1 — find the IAM change event

Run the IAM privilege change query in section 10.3, scoped to 1–2 hours prior to the alert. Identify:

- Event ID and timestamp.
- Actor ARN and principal ID.
- Target role name.
- Policy ARN/document.
- Source IP, user agent, and Region.
- Whether the API succeeded or returned an error.

### 19.4. Step 2 — trace the session origin

Extract the assumed-role ARN from the event. Search `AssumeRole` in STS to determine:

- The caller identity that assumed `DeploymentRole` or an intermediate role.
- Target role ARN and session name.
- External ID/source identity if present.
- Source IP and user agent at the time of assumption.

Next, cross-reference sign-in/Identity Center events and check MFA context. If the session was created by CI/CD, identify the pipeline run, repository, commit, and deployment approval.

### 19.5. Step 3 — find actions after gaining privilege

Find events after `AttachRolePolicy` performed by that actor/assumed-role session:

- IAM: creating users/access keys, altering trust policies, or attaching more policies.
- EC2/VPC: launching instances, opening security groups, or changing routes.
- S3: `GetObject`, `PutObject`, `DeleteObject` on sensitive buckets.
- CloudTrail: stopping trails, changing selectors, or altering EDS ingestion settings.

If S3 data events were not collected for a relevant bucket, record this as a coverage gap; do not assert that data was not accessed.

### 19.6. Step 4 — verify and contain

The security team confirms the session does not belong to an approved pipeline, then executes containment per the incident runbook:

1. Collect and verify query results.
2. Save event IDs, role/session ARNs, source IPs, and resource IDs.
3. Revoke privileges/credentials or sessions per approved procedures.
4. Restore `ApplicationRole`'s policy to baseline.
5. Check resource/data changes made during the session.
6. Add selectors for sensitive resources if coverage gaps were found.

### 19.7. Outcome and lessons learned

The timeline should clearly show sign-in → AssumeRole → AttachRolePolicy → post-escalation API calls → containment. If no events are found at a link in the chain, explicitly document it as "no data in collected sources" rather than "did not occur."

This case study shows CloudTrail Lake is valuable when event coverage is designed before an incident. SQL helps narrow and correlate data; conclusions still require cross-checking with other sources and verification workflows.

## 20. Reinforcement exercises

### Exercise 1 — Event history or CloudTrail Lake?

An operator needs to quickly check who just called `StopLogging` in the current account. If a deep investigation across multiple accounts and multiple days is needed, which mechanism should be used?

**Hint:** Event history fits quick lookups of recent management events; EDS/Trail analytics fits SQL and long-term scope if the account already has CloudTrail Lake. For new customers, use the AWS-recommended CloudWatch architecture.

### Exercise 2 — Management event or data event?

You need to know who called `GetObject` on an object in a sensitive data bucket. Are management events enough?

**Hint:** No. You must enable S3 data events for the bucket/prefix and operations requiring auditing.

### Exercise 3 — Actor is an assumed role

An event has `userIdentity.type = AssumedRole`. Which field identifies the role that issued the credentials?

**Hint:** `userIdentity.sessionContext.sessionIssuer.arn`; then search STS AssumeRole to trace the caller.

### Exercise 4 — Choosing selectors

An organization wants to audit all object operations in the `finance-data` bucket, without needing data events for other buckets. Which fields should the selector restrict on?

**Hint:** `eventCategory=Data`, `resources.type=AWS::S3::Object`, and `resources.ARN` starting with the bucket/prefix to monitor.

### Exercise 5 — Expensive query

A query uses `SELECT *` on a multi-TB EDS with no time range. What is the first optimization?

**Hint:** Add `eventTime` start/end, select only required columns, and add filters on event source/name/actor.

### Exercise 6 — No S3 GetObject event

An investigator finds no `GetObject` events. Can they conclude nobody read the object?

**Hint:** No. Check S3 data event selectors, bucket/prefix, Region, retention, and when the EDS began ingesting.

### Exercise 7 — Cross-account query

An analyst in account A needs to query an organization EDS owned by the security account. Which two permission layers must be reviewed?

**Hint:** The resource-based policy on the EDS and the identity policy of the principal in account A; additionally, proper organization/delegated administrator permissions if it is an organization EDS.

### Exercise 8 — Athena federation

A team queried an EDS using Athena. They want to delete the EDS, but the delete command is rejected. What needs to be checked?

**Hint:** Federation must be disabled first; if termination protection is enabled, it must be turned off per procedure before deletion.

### Exercise 9 — Evidence integrity

Query results were exported to S3 and sent to the incident commander. How do you verify the files were not altered?

**Hint:** Keep the signature file `result_sign.json` and run `aws cloudtrail verify-query-results` on the S3 prefix or local files.

### Exercise 10 — CloudTrail Lake availability

An organization created a new AWS account after 31-05-2026 and wants to start with CloudTrail Lake. What should they do?

**Hint:** CloudTrail Lake is not open to new customers; use CloudTrail Trails and the AWS-recommended Amazon CloudWatch architecture, while verifying coverage of needed event categories.

## 21. Operations and investigation checklist

- [ ] Identify whether Event history, Trails, EDS, and CloudWatch architecture are in use.
- [ ] Explicitly note CloudTrail Lake availability status; only operate existing EDSs if the organization was an existing customer before closure.
- [ ] Multi-Region Trail or EDS coverage reviewed for active Regions.
- [ ] Event categories fit the use case: management, data, network activity, Insights, or Config.
- [ ] Advanced event selectors do not omit critical resources/actions.
- [ ] Data events intentionally enabled for sensitive buckets, tables, functions, or resources.
- [ ] Organization EDS or central architecture covers new accounts as required.
- [ ] Retention and pricing option approved; ingestion/query volume monitored.
- [ ] Query templates include time ranges, event source/action filters, and result limits.
- [ ] Saved queries versioned/reviewed with owners/runbooks.
- [ ] Permissions to create/edit/delete EDS separated from query/read permissions.
- [ ] Cross-account access uses resource policies/identity policies following least privilege.
- [ ] Delegated administrators only hold required permissions.
- [ ] Federation role, Glue catalog, and Lake Formation grants managed.
- [ ] Query results saved in a protected S3 bucket with encryption, retention, and access logging.
- [ ] `result_sign.json` retained alongside result files and validation run when evidence must be preserved.
- [ ] Incident timeline uses UTC, preserves event IDs, and traces assumed-role sessions.
- [ ] CloudTrail cross-referenced with Config, GuardDuty, VPC Flow Logs, CloudWatch, and CI/CD evidence.
- [ ] Do not conclude missing events before checking selectors, account, Region, retention, and ingestion.
- [ ] Migration plan to CloudWatch exists for existing CloudTrail Lake organizations.
- [ ] Unmigrated historical data has a clear retention/archive path.
- [ ] Containment runbooks executed under incident/change-control processes.

## 22. Key takeaways

1. **CloudTrail records account and API activity**; Event history enables quick lookup, Trails deliver logs to S3, and CloudTrail Lake EDS provides SQL analytics for existing customers.
2. **Management events and data events differ.** To know who read an object or invoked a function, configure data events on the right resources.
3. **An Event Data Store only contains ingested or copied data.** Without appropriate selectors, missed activity cannot be queried retroactively.
4. **`userIdentity` is the key to tracing actors.** For assumed roles, combine session issuer, STS AssumeRole, source IP, user agent, and MFA context.
5. **SQL must be time-bounded.** Use `eventTime`, select fewer columns, add filters, and watch `BytesScanned` to control costs.
6. **Organization EDS and cross-account access require centralized governance.** Resource policies, identity policies, and delegated administrator permissions are distinct permission layers.
7. **Query results can be verified.** Keep the signature file and use `verify-query-results` to check integrity after CloudTrail delivers the files.
8. **CloudTrail Lake closed to new customers as of 31-05-2026.** AWS recommends CloudWatch architecture for new deployments and existing customer migrations; verify event coverage since not all capabilities are identical.

Effective investigations start with proper event coverage, identifying actors/sessions, building a timeline, and validating hypotheses across multiple sources. CloudTrail provides audit evidence; conclusions and containment still require controlled security processes.

### Official documentation

- [CloudTrail Lake availability change](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-service-availability-change.html) — new customer closure milestone, existing support, and migration to CloudWatch.
- [Working with AWS CloudTrail Lake](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake.html) — overview of Event Data Stores, queries, and federation.
- [CloudTrail concepts](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-concepts.html) — event categories, trails, and EDS.
- [CloudTrail event record contents](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-record-contents.html) — event schema and fields.
- [CloudTrail userIdentity element](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-user-identity.html) — identity/session fields.
- [Create an event data store for CloudTrail events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/query-event-data-store-cloudtrail.html) — EDS and advanced event selectors.
- [Organization event data stores](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-organizations.html) — management account, delegated administrator, and organization scope.
- [CloudTrail Lake queries](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-queries.html) — SQL query editor and time filters.
- [CloudTrail Lake SQL constraints](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/query-limitations.html) — SELECT syntax and SQL constraints.
- [Optimize CloudTrail Lake queries](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/lake-queries-optimization.html) — query optimization and error handling.
- [Resource-based policy examples](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/security_iam_resource-based-policy-examples.html) — cross-account EDS access.
- [Federate an event data store](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/query-federation.html) — Glue, Lake Formation, and Athena.
- [Copying trail events to CloudTrail Lake](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-copy-trail-to-lake.html) — historical event copy.
- [Validate CloudTrail Lake saved query results](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-query-results-validation.html) — signature file and integrity verification.
- [AWS CloudTrail pricing](https://aws.amazon.com/cloudtrail/pricing/) — ingestion, retention, and query charges.
- [CloudTrail organization trails](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html) — organization trails and multi-Region logging.
- [Amazon CloudWatch pipelines](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-pipelines.html) — replacement CloudWatch architecture.