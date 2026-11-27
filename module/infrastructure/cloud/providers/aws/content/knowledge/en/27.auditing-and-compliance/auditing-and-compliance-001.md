# CloudTrail Event history, trails, and event types

When you need to answer questions like “Who changed the Security Group?”, “Which role created an IAM access key?”, “Which application read an object in S3?”, or “Which request was denied by a VPC endpoint policy?”, operations teams need an audit source that can trace the identity, action, timestamp, and context. AWS CloudTrail records API activity and certain sign-in/service events in an AWS account, helping with incident investigation, change control, and meeting audit requirements.

CloudTrail has three concepts that are often confused:

- **Event history** is the lookup interface for management events over the last 90 days per Region, built in for an AWS account.
- **Trail** is a configuration that continuously records and delivers selected events to S3, and can also send them to CloudWatch Logs and integrate with EventBridge for alerting/response.
- **Event types** describe the categories of activity recorded: management, data, network activity, and Insights events. Not all types are enabled by default.

This lesson belongs to the **Auditing and Compliance** chapter, **CLOUD_PROVIDERS_AWS** module. It connects IAM, Region, VPC, S3, Lambda, databases, and other AWS services with the goal of maintaining audit evidence, monitoring activity, investigating changes, and controlling risk.

> **Principle:** Event history is useful for quick investigation of recent events. Only a properly configured trail creates a long-term, centralized record. To track actions on data, you must select the right data events; enabling management events does not mean every object read/write or function invocation is recorded.

## 1. Learning objectives

After this lesson, learners can:

1. Explain what types of activity CloudTrail records and why an audit trail is needed.
2. Distinguish between Event history, trails, and CloudTrail Lake event data stores.
3. Understand the 90-day scope, Region scope, and search limits of Event history.
4. Distinguish between management events, data events, network activity events, and Insights events.
5. Classify read events and write events.
6. Read important fields in a CloudTrail JSON event record.
7. Search for events using the Console and AWS CLI `lookup-events`.
8. Create a single-Region or multi-Region trail and enable logging.
9. Design an organization trail for AWS Organizations.
10. Understand basic event selectors and advanced event selectors.
11. Select data events by bucket, object prefix, Lambda function, or resource type.
12. Record network activity events through VPC endpoints and Insights events when needed.
13. Configure S3 log delivery, CloudWatch Logs, EventBridge, and log file integrity validation.
14. Manage CloudTrail retention, encryption, access control, and cost.
15. Build workflows for investigation, alerting, and checking audit coverage.

## 2. How does CloudTrail work?

CloudTrail records requests/operations in an AWS account. An event record typically shows which identity performed the action, the service that received the request, the API action, the timestamp, the Region, the source IP, the user agent, the resource, and the outcome. Events can come from the AWS Management Console, AWS CLI, SDK/API, or certain activities performed by an AWS service.

~~~mermaid
flowchart TD
    ACTOR["User / IAM role / AWS service"] --> API["AWS Console / CLI / SDK / API"]
    API --> SERVICE["AWS service processes request"]
    SERVICE --> EVENT["CloudTrail event record"]
    EVENT --> HISTORY["Event history<br/>90-day management events"]
    EVENT --> TRAIL["Trail selectors"]
    TRAIL --> S3["Amazon S3 log archive"]
    TRAIL --> CW["CloudWatch Logs"]
    TRAIL --> EB["EventBridge integration"]
    S3 --> ATHENA["Amazon Athena / SIEM"]
    CW --> ALARM["Metric filters / alarms"]
    EB --> AUTO["Alert / automation"]
~~~

Some notes:

- Event history is available for every account and records management events per Region.
- A trail determines which events are continuously delivered and where logs are sent.
- Event selectors filter event types, resource types, resource ARNs, or API names according to the selector's capabilities.
- CloudTrail is not packet capture and does not record the full application payload. It records event metadata/API context in the format supported by the service.
- CloudTrail log files are not a stack trace ordered by API call sequence; do not assume the order of records in a file represents absolute business order.
- Delivery is not real-time. Logs are typically delivered in an average of a few minutes after the API call, though there is no guarantee that an event will appear within a fixed time.

### 2.1. Event history, trails, and CloudTrail Lake

| Component | What is it used for? | Storage/querying |
|---|---|---|
| Event history | Quick lookup of recent management events | 90 days, per account and Region; Console/LookupEvents |
| Trail | Continuous event recording according to selectors | Log files in S3; can send to CloudWatch Logs |
| CloudTrail Lake event data store | Ingest and query events at higher scale/flexibility | Event data store, SQL queries in CloudTrail Lake |

CloudTrail Lake is not another name for a trail. An event data store has its own ingestion configuration, selectors, retention, and pricing; Lake data is not delivered as log files to S3 via the trail mechanism. **Service status note as of 20/11/2026:** AWS CloudTrail Lake closed sign-ups for new customers as of 31/05/2026. Existing customers can continue using it; AWS recommends considering Amazon CloudWatch for similar capabilities. Therefore, CloudTrail Lake in this lesson is a concept/option for accounts that already had access prior to the sign-up closure. For new deployments, prioritize trail + S3 archive and CloudWatch/Athena as needed.

### 2.2. Why do you need a trail if you already have Event history?

Event history only retains 90 days and does not provide data events, network activity events, or organization-wide aggregation. A trail creates a long-term record in S3 that can integrate with analytics/monitoring systems and control event selectors. If audit retention requires 1 year, 3 years, or longer, design S3 retention/lifecycle and deletion controls; do not rely on Event history.

## 3. Event history: looking up management events over 90 days

Event history is the starting point when investigating recent activity. CloudTrail automatically provides Event history for an AWS account; you do not need to create a trail first to view management events recorded in that Region. Viewing Event history incurs no CloudTrail charges.

### 3.1. Scope and limits

| Attribute | Event history |
|---|---|
| Time window | Last 90 days |
| Event type | Management events |
| Account scope | One AWS account |
| Region scope | One Region at a time |
| Filters | One attribute filter and time range |
| Data events | Not displayed |
| Network activity events | Not displayed |
| Insights events | Not displayed |
| Organization aggregation | None |
| Download | Console supports CSV/JSON; up to 200,000 events per file |

Event history cannot be configured to retain 1 year and cannot be extended by modifying a trail. A trail/event data store is what you need to create to store and query events long-term.

### 3.2. Searching in the Console

In the CloudTrail Console:

1. Select the Region where the action occurred.
2. Open **Event history**.
3. Choose an attribute filter such as Event name, Event source, Username, Resource name, or Resource type.
4. Enter the exact value and set the time range.
5. Open an event to view the event record JSON, identity, request parameters, response, and resources.
6. Download CSV/JSON if you need to save evidence or continue analysis.

By default, Event history applies the filter `Read only = false`, meaning it only displays write events. Clear this filter when investigating read events as well.

For example, to find calls to `CreateAccessKey`, choose Event name and enter the exact API name. To find login events, search for `ConsoleLogin`. To view changes in IAM, filter Event source as `iam.amazonaws.com`.

### 3.3. Searching with the AWS CLI

`lookup-events` queries Event history. The command below searches for `ConsoleLogin` calls in the specified Region:

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=ConsoleLogin \
  --region ap-southeast-1 \
  --max-results 50
~~~

Search for events from the IAM service:

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=iam.amazonaws.com \
  --region ap-southeast-1 \
  --max-results 50
~~~

Search within a specific time range:

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=CreateAccessKey \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T23:59:59Z \
  --region ap-southeast-1
~~~

`LookupEvents` only accepts one lookup attribute per request; you can add a time range. If you need to combine multiple conditions, multiple accounts/Regions, or complex queries, use trail logs with Athena or CloudTrail Lake.

### 3.4. Quick investigation example

Suppose a Security Group has a new SSH rule. Initial search workflow:

1. Get the Security Group ID and Region from the alert.
2. In Event history, filter Event source by `ec2.amazonaws.com`.
3. Narrow the time range around the detection time.
4. Look for related event names such as `AuthorizeSecurityGroupIngress`, `ModifySecurityGroupRules`, or the API corresponding to the operation.
5. Read `userIdentity`, `sourceIPAddress`, `userAgent`, `requestParameters`, `eventTime`, and `responseElements`.
6. Correlate with the change ticket, deployment pipeline, and CloudTrail trail archive if a longer investigation is needed.

Event history helps find things quickly; if the event is older than 90 days or you need data events, you must query another storage source.

## 4. Four types of CloudTrail events

CloudTrail classifies events into four groups. Trails and event data stores record management events by default; data events, network activity events, and Insights events must be configured explicitly.

| Event type | Scope | Examples | Default |
|---|---|---|---|
| Management | Control plane/resource configuration | `CreateVpc`, `PutBucketPolicy`, `AttachRolePolicy` | Yes |
| Data | Data plane/resource operations | S3 `GetObject`, Lambda `Invoke`, DynamoDB data API | No |
| Network activity | API requests traversing a VPC endpoint, especially endpoint policy denials | `VpceAccessDenied` | No |
| Insights | Anomalies in API call rate or API error rate | Sudden spike in `RunInstances` or API errors | No |

### 4.1. Management events — control plane

Management events record resource/account management activities, for example:

- Creating, modifying, or deleting a VPC, subnet, route table, or security group.
- Creating an IAM user/role, attaching a policy, changing a trust policy.
- Creating an S3 bucket, modifying a bucket policy, configuring encryption/versioning.
- Creating or updating a CloudTrail trail.
- Configuring databases, load balancers, EKS clusters, and other resources.
- Certain non-API-call events such as `ConsoleLogin`.

Management events can be classified as:

- **Read events:** operations reading metadata/configuration, such as `DescribeInstances`, `GetRole`, `ListBuckets`.
- **Write events:** operations changing state, such as `RunInstances`, `CreateRole`, `DeleteBucket`, `PutBucketPolicy`.

You can choose All, Read-only, or Write-only. Read events usually have high volume; write events are usually important for detecting infrastructure changes. In security auditing, you should not collect only write events if you need to know who read sensitive configurations or listed resources.

### 4.2. Data events — data plane

Data events record operations on or inside resources. They typically have much higher volume than management events and may incur additional charges. Examples:

- S3 object-level: `GetObject`, `PutObject`, `DeleteObject`.
- Lambda: `Invoke`.
- DynamoDB: data-plane operations such as `GetItem`, `PutItem`, `Query` (depending on resource/event support).
- SNS: `Publish`, `PublishBatch` on a topic.
- Many other resource types supported through advanced event selectors.

Event history does not display data events. To know who read an S3 object, you must enable data events for the appropriate bucket/prefix in a trail or event data store. Enabling only management events is not enough.

### 4.3. Network activity events — activity through VPC endpoints

Network activity events help the VPC endpoint owner record AWS API calls passing through an endpoint from a private VPC to an AWS service. They are especially useful when investigating requests denied by an endpoint policy.

An example event includes:

- `eventCategory: NetworkActivity`
- `eventType: AwsVpceEvent`
- `vpcEndpointId`
- `vpcEndpointAccountId`
- `errorCode: VpceAccessDenied` when the request is denied by the endpoint policy.

Not every network packet or every VPC connection is recorded by CloudTrail. Network activity events are specific supported API events passing through a VPC endpoint, and the event source must be configured using advanced event selectors. The list of supported services can change over time.

### 4.4. Insights events — anomaly detection

CloudTrail Insights analyzes your API activity baseline and detects significant changes in:

- **API call rate:** unusual spikes or drops in API call volume; this type analyzes write API calls.
- **API error rate:** unusual rate of API calls returning errors; can analyze both read and write API calls.

Insights generates events marking the anomalous time window and information for investigation. It is not an alert for every API error and does not replace CloudWatch alarms or security monitoring. Insights must be enabled explicitly and may incur separate charges. When first enabled, it may take time for CloudTrail to build a baseline and detect anomalies.

## 5. Reading a CloudTrail event record

A CloudTrail event record is a JSON object. Delivered log files typically have a JSON structure with a `Records` array containing one or more events. Event history also lets you open the raw event to inspect the same fields.

### 5.1. Important fields

| Field | Meaning | Investigation question supported |
|---|---|---|
| `eventTime` | Event timestamp in UTC | When did the action happen? |
| `eventSource` | Service receiving the request, e.g. `ec2.amazonaws.com` | Which service did the API call target? |
| `eventName` | API action or event name, e.g. `RunInstances` | What action was performed? |
| `awsRegion` | Region processing the request | Where did the action happen? |
| `userIdentity` | Identity performing the request | Who or which role performed it? |
| `sourceIPAddress` | Source IP of the request | Where did the request come from? |
| `userAgent` | Tool/client generating the request | Console, CLI, SDK, or which service? |
| `requestParameters` | Request parameters if available | Which resource/config was requested? |
| `responseElements` | Recorded response portion if available | What result did the API return? |
| `errorCode` / `errorMessage` | Error if the request failed | Why was the request denied/failed? |
| `resources` | Related resources if provided | Which resource ARN/ID is involved? |
| `readOnly` | Whether the request is classified as read or write | Is this a state-changing operation? |
| `eventCategory` | Management, Data, or NetworkActivity | What category does the event belong to? |
| `eventID` | Unique ID of the event record | Used to correlate a specific record |
| `recipientAccountId` | Account receiving the event | Which account was the event recorded for? |

Optional fields may not appear in every event. `requestParameters` or `responseElements` may be null, redacted, or omit some business details. Do not treat CloudTrail as a full copy of the request/response payload.

### 5.2. Abbreviated event record example

~~~json
{
  "eventVersion": "1.09",
  "userIdentity": {
    "type": "AssumedRole",
    "principalId": "EXAMPLE:deployment-job",
    "arn": "arn:aws:sts::123456789012:assumed-role/DeploymentRole/deployment-job",
    "accountId": "123456789012"
  },
  "eventTime": "2026-11-20T03:12:45Z",
  "eventSource": "ec2.amazonaws.com",
  "eventName": "AuthorizeSecurityGroupIngress",
  "awsRegion": "ap-southeast-1",
  "sourceIPAddress": "198.51.100.25",
  "userAgent": "aws-cli/2.x",
  "requestParameters": {
    "groupId": "sg-0123456789abcdef0",
    "ipPermissions": "..."
  },
  "responseElements": null,
  "requestID": "example-request-id",
  "eventID": "example-event-id",
  "readOnly": false,
  "eventType": "AwsApiCall",
  "managementEvent": true,
  "recipientAccountId": "123456789012",
  "eventCategory": "Management"
}
~~~

The example above is abbreviated with IDs replaced by illustrative values. In real events, `userIdentity` can be IAMUser, AssumedRole, FederatedUser, AWSService, Root, or other identity types.

### 5.3. Reading userIdentity

`userIdentity` is the most important part when tracing the actor. Common subfields:

- `type`: identity type.
- `arn`: ARN of the principal or role session.
- `principalId`: principal identifier.
- `accountId`: account owning the identity.
- `accessKeyId`: access key ID used if applicable; not the secret access key.
- `sessionContext`: session, role, MFA, and issuer details.
- `invokedBy`: service that called the API on behalf of the principal in certain cases.
- `sourceIdentity`: if configured, this value appears in `requestParameters` of STS AssumeRole calls and in `userIdentity.sessionContext` of subsequent service API calls.

If `type` is `AssumedRole`, the ARN typically contains the role name and session name. The session name helps correlate with a CI job, automation, or ticket. If `type` is `AWSService`, the action may have been performed by an AWS service via a service-linked role or service principal; examine the context before attributing responsibility to a person.

### 5.4. Correlating events

To investigate a change, combine multiple fields:

1. `eventTime` and `awsRegion` establish the timeline/scope.
2. `eventName` and `eventSource` identify the API.
3. `userIdentity.arn` and `principalId` identify the actor/role session.
4. `sourceIPAddress` and `userAgent` provide the source and client.
5. `requestParameters` identify the affected resource/property.
6. `errorCode` and `responseElements` distinguish success/failure.
7. `eventID` identifies the event; `sharedEventID` can link records of the same action delivered to multiple accounts.

Event logs can arrive late and are not guaranteed to be strictly ordered. When building a timeline, sort by `eventTime` and cross-check request IDs, service logs, deployment logs, and application telemetry.

## 6. Creating a trail for an AWS account

A trail is a CloudTrail configuration that continuously records selected events and delivers log files to S3. A trail can be single-Region or multi-Region. For an audit baseline, a multi-Region trail is usually more appropriate because it captures activity across all enabled Regions.

### 6.1. Preparing the S3 bucket

Create a dedicated S3 bucket for storing CloudTrail logs. The bucket needs:

- Block Public Access enabled.
- Bucket policy allowing the CloudTrail service principal to write to the right prefix.
- `aws:SourceArn` condition restricting to the exact trail ARN to reduce confused-deputy risk.
- Encryption at rest (SSE-S3 or SSE-KMS as required).
- Access restricted to security/audit roles and log processing roles.
- Lifecycle/retention aligned with policy.
- Protection against deletion/modification according to the required level of assurance.

CloudTrail does not require the bucket to be in the same Region as the trail. The bucket also must not be configured with Requester Pays to receive log delivery.

### 6.2. Creating a multi-Region trail with the AWS CLI

Assume the bucket `company-cloudtrail-archive` already exists and its bucket policy allows the trail to write logs:

~~~bash
aws cloudtrail create-trail \
  --name organization-audit-baseline \
  --s3-bucket-name company-cloudtrail-archive \
  --is-multi-region-trail \
  --include-global-service-events \
  --enable-log-file-validation \
  --region ap-southeast-1
~~~

The `create-trail` command creates the trail configuration. Next, you need to start logging:

~~~bash
aws cloudtrail start-logging \
  --name organization-audit-baseline \
  --region ap-southeast-1
~~~

Check status:

~~~bash
aws cloudtrail get-trail-status \
  --name organization-audit-baseline \
  --region ap-southeast-1
~~~

Check configuration:

~~~bash
aws cloudtrail get-trail \
  --name organization-audit-baseline \
  --region ap-southeast-1

aws cloudtrail get-event-selectors \
  --trail-name organization-audit-baseline \
  --region ap-southeast-1
~~~

These commands are AWS configuration operations and should only be run with approved permissions in the target account. If the trail already exists, inspect the current configuration before updating it.

### 6.3. Single-Region vs. multi-Region trails

| Attribute | Single-Region | Multi-Region |
|---|---|---|
| Coverage | One selected Region | All enabled Regions in the account |
| Configuration | Managed in that Region | One home Region, trail copy operates in enabled Regions |
| Global service events | Per trail configuration | Can record global service events |
| Risk | Misses other Regions if workloads expand | Must verify opt-in Regions and coverage |
| Use case | Labs, narrow-scope requirements | Production audit baseline |

Creating a new trail in the Console defaults to multi-Region. Using the CLI, you can create a single-Region or multi-Region trail with the corresponding parameters. When an account enables a new opt-in Region, verify trail coverage and allow time for configuration/event delivery to converge.

### 6.4. Checking log delivery

`get-trail-status` has useful fields:

- `IsLogging`: whether the trail is currently logging.
- `LatestDeliveryTime`: timestamp of the most recent log delivery.
- `LatestDeliveryError`: error when delivering to S3.
- `LatestCloudWatchLogsDeliveryError`: error delivering to CloudWatch Logs.
- `LatestDigestDeliveryTime`: timestamp of the most recent digest file delivery.
- `StartLoggingTime` and `StopLoggingTime`: timestamps when logging started/stopped.

Do not look only at `IsLogging=true`. A trail can be logging while delivery to S3/CloudWatch Logs is failing. Monitor delivery status and alert on errors as well.

## 7. Organization trails for AWS Organizations

In a multi-account environment, creating a separate trail in each account increases administrative overhead and can leave gaps when new accounts are added. An **organization trail** records activity from the management account and member accounts in an AWS Organization into the same destination.

### 7.1. Who can create an organization trail?

- The AWS Organizations management account can create an organization trail.
- The management account can designate a CloudTrail delegated administrator to manage trails/event data stores.
- Member accounts can see the organization trail but cannot modify or delete it themselves.
- An organization trail created by a delegated administrator still remains under the ownership of the management account.
- The S3 bucket policy must allow CloudTrail to write logs for the organization path/account IDs.

### 7.2. Centralized architecture

~~~mermaid
flowchart TD
    ORG["AWS Organizations"]
    ORG --> MGMT["Management account"]
    ORG --> DEV["Dev account"]
    ORG --> STG["Staging account"]
    ORG --> PROD["Production account"]
    MGMT --> TRAIL["Organization multi-Region trail"]
    DEV --> TRAIL
    STG --> TRAIL
    PROD --> TRAIL
    TRAIL --> S3["Central audit S3 bucket<br/>Security / Log Archive account"]
    S3 --> SIEM["Athena / SIEM / audit tooling"]
~~~

A common design places the bucket in a Security/Log Archive account while the trail is managed from the management account or delegated administrator. You must configure the bucket policy, KMS key policy, and access roles appropriately for cross-account delivery/reading.

### 7.3. Account lifecycle controls

When a new account joins the organization, verify that the organization trail has been applied and logs are being recorded. When an account leaves the organization, previously delivered log files remain in the S3 destination according to the retention policy. Manage archive access permissions in the central account independently from member account administrative privileges.

If the home Region of an organization multi-Region trail is an opt-in Region, member accounts must enable that Region to send activity into the organization trail. Choose the home Region and Region enablement according to organizational policy; do not assume every member account automatically enables every opt-in Region.

## 8. Event selectors: choosing which events are recorded

Event selectors determine which events CloudTrail processes for a trail. Designing selectors is a key step to balance audit coverage, cost, and log volume.

### 8.1. Management events: All, Read, and Write

For management events, you can record:

- `All`: both read and write events.
- `ReadOnly`: read events only.
- `WriteOnly`: write events only.

A new trail defaults to recording all management events (read and write). If you change the selector, make sure you understand the scope before applying it. For example, recording only write events could miss whether a principal called `GetRole`, `ListAccessKeys`, or `DescribeSecurityGroups`.

### 8.2. Basic event selectors

Basic selectors support management events and data events for several common resource types such as:

- `AWS::S3::Object`
- `AWS::Lambda::Function`
- `AWS::DynamoDB::Table`

Example `basic-selectors.json` file recording all management events and data events on one S3 bucket:

~~~json
[
  {
    "ReadWriteType": "All",
    "IncludeManagementEvents": true,
    "DataResources": [
      {
        "Type": "AWS::S3::Object",
        "Values": [
          "arn:aws:s3:::company-audit-data/"
        ]
      }
    ]
  }
]
~~~

Apply the selector:

~~~bash
aws cloudtrail put-event-selectors \
  --trail-name organization-audit-baseline \
  --event-selectors file://basic-selectors.json \
  --region ap-southeast-1
~~~

For S3 object data events, the resource value can restrict to a bucket or prefix. For example, `arn:aws:s3:::company-audit-data/finance/` tracks objects under the `finance/` prefix. Choose the right ARN pattern and test with an event after updating.

### 8.3. Advanced event selectors

Advanced selectors support more granular filtering and can configure data events for many resource types, network activity events, and management events. For CloudTrail Lake event data stores, data events also require advanced event selectors. Commonly used fields include:

- `eventCategory`
- `resources.type`
- `resources.ARN`
- `eventName`
- `eventSource`
- `readOnly`
- `userIdentity.arn` (depending on the event type/selector type supported)

Example recording only S3 object write events in the finance prefix:

~~~json
[
  {
    "Name": "S3 finance object writes",
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
          "arn:aws:s3:::company-audit-data/finance/"
        ]
      },
      {
        "Field": "readOnly",
        "Equals": ["false"]
      }
    ]
  }
]
~~~

Apply the advanced selector:

~~~bash
aws cloudtrail put-event-selectors \
  --trail-name organization-audit-baseline \
  --advanced-event-selectors file://advanced-selectors.json \
  --region ap-southeast-1
~~~

CloudTrail allows using either basic selectors or advanced selectors for a trail at one time. When switching to advanced selectors, existing basic selectors are replaced; you must recreate all required selections in the new configuration. Do not send both selector types in the same request.

### 8.4. Filtering by API name and resource scope

Advanced selectors let you restrict events by API name—for example, recording only `GetObject`, `PutObject`, or `DeleteObject`—or by prefix/ARN. However, do not narrow too aggressively if investigations require both read and write activity.

Some patterns:

| Audit requirement | Suggested selector |
|---|---|
| Who reads/writes objects in a sensitive bucket? | Data events, `AWS::S3::Object`, bucket/prefix ARN |
| Who invokes a data-processing Lambda? | Data events, `AWS::Lambda::Function`, function ARN |
| Who queries/writes to DynamoDB? | Data events, `AWS::DynamoDB::Table`, table ARN |
| Audit object deletions only | Data events + `eventName = DeleteObject` |
| Audit APIs denied by a VPC endpoint policy | NetworkActivity + eventSource + `errorCode = VpceAccessDenied` |

### 8.5. Network activity event selector

Example recording network activity events denied by a VPC endpoint policy for AWS KMS:

~~~json
[
  {
    "Name": "KMS VPC endpoint denials",
    "FieldSelectors": [
      {
        "Field": "eventCategory",
        "Equals": ["NetworkActivity"]
      },
      {
        "Field": "eventSource",
        "Equals": ["kms.amazonaws.com"]
      },
      {
        "Field": "errorCode",
        "Equals": ["VpceAccessDenied"]
      }
    ]
  }
]
~~~

Network activity events only apply to services/event sources supported by CloudTrail and must be enabled explicitly. The `errorCode` values currently usable for this event type may be limited according to AWS documentation; for instance, `VpceAccessDenied` is a common code when an endpoint policy denies a request.

### 8.6. Enabling CloudTrail Insights

Example enabling API call rate Insights on a trail:

~~~bash
aws cloudtrail put-insight-selectors \
  --trail-name organization-audit-baseline \
  --insight-selectors '[{"InsightType":"ApiCallRateInsight"}]' \
  --region ap-southeast-1
~~~

You can choose `ApiErrorRateInsight` or both types if appropriate. Input prerequisites depend on the Insights type: API call rate requires write events; API error rate requires read or write events. Insights incurs separate charges and only generates events when CloudTrail detects activity deviating significantly from the baseline.

### 8.7. Verifying selectors after changes

~~~bash
aws cloudtrail get-event-selectors \
  --trail-name organization-audit-baseline \
  --region ap-southeast-1

aws cloudtrail get-insight-selectors \
  --trail-name organization-audit-baseline \
  --region ap-southeast-1
~~~

After changing selectors, generate an intentional test activity in a sandbox and verify the event appears in the right destination. Do not infer coverage solely because `put-event-selectors` returned success.

## 9. Log delivery, destinations, and retention

A trail delivers log files to S3. You can additionally integrate CloudWatch Logs for searching/alerting, SNS for delivery notifications, and analytics tools such as Athena/SIEM.

### 9.1. S3 log object path

CloudTrail stores log files as gzipped JSON in the bucket. The standard path for an account trail typically looks like:

~~~text
s3://company-cloudtrail-archive/AWSLogs/123456789012/CloudTrail/ap-southeast-1/2026/11/20/
~~~

For an organization trail, the path contains the organization ID and account ID in its path structure. Other event categories may use dedicated prefixes such as `CloudTrail-Insight` or `CloudTrail-NetworkActivity`.

A log object may contain events that occurred before the time the object was delivered. Do not use the timestamp in the object key instead of `eventTime` to reconstruct an accurate timeline.

### 9.2. Delivery timing and retries

CloudTrail typically delivers log files an average of about 5 minutes after an API call, though this timing is not guaranteed. Some cases may be slower. Alert designs must account for delivery delay and avoid assuming logs appear instantaneously.

If a trail is misconfigured—for example, the S3 bucket policy does not allow writes or the destination is unreachable—CloudTrail may continue retrying delivery for up to 30 days; these delivery attempts may incur charges. Check `get-trail-status`, fix the destination policy, and monitor delivery errors.

### 9.3. Sending logs to CloudWatch Logs

CloudWatch Logs is useful when you need metric filters, alarms, Logs Insights, and fast alerting. Configure the trail with a log group ARN and an IAM role for CloudTrail to write logs. The role needs appropriate permissions to create a log stream and put log events.

You can use CloudWatch Logs metric filters to count sensitive events such as:

- IAM policy changes.
- Root account activity.
- Console login failures.
- CloudTrail trail stopped/updated/deleted.
- Security Group ingress widened.
- KMS key disabled or scheduled for deletion.

Metric filters need to parse the JSON event structure and verify the exact field path. For forensic audits, the S3 archive remains critical for long-term log retention and independent analysis.

### 9.4. EventBridge and event-driven response

CloudTrail integrates with EventBridge to route AWS API events onto an event bus, where rules can route them to SNS, SQS, Lambda, or automation. EventBridge is suitable for operational responses such as alerting on `StopLogging`, `DeleteTrail`, `PutBucketPolicy`, or sensitive IAM changes.

An EventBridge rule is an event-driven processing path; it does not replace the trail's S3 archive/retention. For events requiring long-term evidence retention, maintain separate trail selectors and destinations.

### 9.5. Retention and lifecycle

Choose retention based on legal, compliance, investigation, and cost requirements:

- Keep hot data in S3 Standard or an appropriate tier for frequent querying.
- Transition older logs to cheaper storage classes using S3 Lifecycle when retrieval times can be longer.
- Define retention periods and legal hold according to organizational policy.
- Control who can read, edit the bucket policy, change lifecycle rules, or delete objects.
- Use versioning/Object Lock if anti-deletion/anti-tampering requires stronger protection.
- Account for both log files and digest files in lifecycle rules.

Do not choose retention solely based on storage price. Audit evidence may need to be retained longer than the tenure of the employee or workload that generated the event.

## 10. Protecting CloudTrail logs and verifying integrity

CloudTrail logs are audit evidence. If a principal can delete, modify, or prevent log delivery, the organization may lose its ability to investigate. You need to protect the S3 destination, KMS key, trail configuration, digest files, and administrative permissions.

### 10.1. Bucket policy for an account trail

Minimal example bucket policy for an account trail. Replace the bucket, account ID, Region, and trail name with real values:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AWSCloudTrailAclCheck",
      "Effect": "Allow",
      "Principal": {
        "Service": "cloudtrail.amazonaws.com"
      },
      "Action": "s3:GetBucketAcl",
      "Resource": "arn:aws:s3:::company-cloudtrail-archive",
      "Condition": {
        "StringEquals": {
          "aws:SourceArn": "arn:aws:cloudtrail:ap-southeast-1:123456789012:trail/organization-audit-baseline"
        }
      }
    },
    {
      "Sid": "AWSCloudTrailWrite",
      "Effect": "Allow",
      "Principal": {
        "Service": "cloudtrail.amazonaws.com"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::company-cloudtrail-archive/AWSLogs/123456789012/*",
      "Condition": {
        "StringEquals": {
          "s3:x-amz-acl": "bucket-owner-full-control",
          "aws:SourceArn": "arn:aws:cloudtrail:ap-southeast-1:123456789012:trail/organization-audit-baseline"
        }
      }
    }
  ]
}
~~~

This is an example for an account trail. For an organization trail, the bucket policy needs to allow paths containing the organization ID and account IDs according to the structure AWS requires. Use the policy generated by the CloudTrail Console/AWS documentation for the right trail type and review it before applying.

### 10.2. Encryption and access control

- Enable S3 Block Public Access at the bucket/account level.
- Use SSE-S3 or SSE-KMS according to your encryption standard. With SSE-KMS, the key policy must allow CloudTrail to encrypt and audit roles to decrypt.
- Restrict permissions for `s3:GetObject`, `s3:ListBucket`, `s3:PutBucketPolicy`, `s3:PutLifecycleConfiguration`, and `s3:DeleteObject`.
- Separate the log-writing role, log-reading role, trail administration role, and KMS key administration role.
- Record changes to the bucket policy, lifecycle, KMS key policy, trail selectors, and logging status using CloudTrail/Config themselves.
- Use SCPs or appropriate controls to prevent member accounts from disabling/altering audit logging if the organization requires central governance.

Do not grant modify/delete permissions on the log archive to workload deployment roles. A role with permissions to manage the bucket or KMS key can directly compromise audit evidence.

### 10.3. Log file integrity validation

When log file integrity validation is enabled, CloudTrail generates hashes for log files and creates digest files periodically. A digest file is digitally signed and references the log files from the preceding interval; you can use the AWS CLI to check whether files were modified, deleted, or remained intact after CloudTrail delivered them.

Enable validation when creating or updating a trail:

~~~bash
aws cloudtrail update-trail \
  --name organization-audit-baseline \
  --enable-log-file-validation \
  --region ap-southeast-1
~~~

Check the configuration:

~~~bash
aws cloudtrail get-trail \
  --name organization-audit-baseline \
  --region ap-southeast-1
~~~

The `LogFileValidationEnabled` field must be `true`. CloudTrail begins delivering digest files after enabling it. Enabling validation only generates digests/signatures; to verify logs, you must run the validation workflow using the AWS CLI or an appropriate tool.

### 10.4. What does validation prove?

Integrity validation helps detect modifications to log files/digest files after CloudTrail delivers them, based on the signed digest chain. It does **not**:

- Prevent a principal with permissions from deleting objects from the bucket.
- Guarantee that every API call of every service is recorded.
- Replace encryption, access control, versioning, or Object Lock.
- Prove that trail selectors cover the right event types.
- Replace checking log delivery and alerting when a trail is stopped.

Combine digest validation with bucket versioning/Object Lock, a restrictive bucket policy, KMS key protection, CloudTrail monitoring, and retention controls.

## 11. Combining CloudTrail with audit and monitoring tools

CloudTrail provides the event record; other services help store, search, verify compliance, and respond.

| Tool | Role | Example use case |
|---|---|---|
| Amazon S3 | Long-term log archive | Retention, lifecycle, Object Lock |
| CloudWatch Logs | Search and alerting | Metric filters, Logs Insights, alarms |
| EventBridge | Route events by pattern | Alert on `StopLogging` or IAM policy changes |
| Amazon Athena | SQL queries over S3 log files | Find which role called `DeleteBucket` within a time window |
| CloudTrail Lake | SQL queries over an event data store | Correlate across event categories/accounts/Regions |
| AWS Config | Configuration history/compliance | View resource configuration before/after an event |
| Security Hub / SIEM | Correlate findings and audit signals | Combine CloudTrail with security findings |

### 11.1. CloudTrail + EventBridge

EventBridge rules can match CloudTrail events by `source`, `detail-type`, `eventSource`, `eventName`, `userIdentity`, or `requestParameters` (depending on the event pattern). The trail must be logging the corresponding management/data/network events for CloudTrail to emit the matching events to EventBridge. For example, detecting when a trail is stopped:

~~~json
{
  "source": ["aws.cloudtrail"],
  "detail-type": ["AWS API Call via CloudTrail"],
  "detail": {
    "eventSource": ["cloudtrail.amazonaws.com"],
    "eventName": ["StopLogging"]
  }
}
~~~

The rule can route to SNS, SQS, Lambda, or an incident workflow. For EventBridge to receive the right event types, the trail must be logging the corresponding management/data events; network activity events also require an appropriate selector. For read-only management events, configure the rule state as required by EventBridge so the rule matches that event type.

An EventBridge rule is an event-driven processing path; it does not replace the trail's S3 archive/retention. For events requiring long-term evidence retention, maintain separate trail selectors and destinations.

### 11.2. CloudTrail + CloudWatch Logs

Use CloudWatch Logs when you need near-real-time alerting based on log delivery. A metric filter can count events such as `ConsoleLogin` failures or `StopLogging`. Build filter patterns from actual JSON records, test against sample events, and only then create alarms.

Do not use CloudWatch Logs retention as the sole archive if policy requires long-term, independent storage. The S3 trail archive separates retention and administrative permissions from log analysis workflows.

### 11.3. CloudTrail + Athena

Once trail logs are in S3, you can use Glue/Athena to analyze by account, Region, actor, event name, and timestamp. Example questions:

- Which role executed `PutBucketPolicy` in the past week?
- Were there any `ConsoleLogin` events from unfamiliar IPs?
- Who called `CreateAccessKey` or `UpdateAssumeRolePolicy`?
- Which object prefixes received `DeleteObject` calls during the incident window?
- Was the trail stopped or were selectors modified during the audit period?

Create the table according to the CloudTrail log path structure and corresponding schema. Partition by account/Region/date to reduce data scanned and query cost.

### 11.4. CloudTrail Lake — notes for existing customers

A CloudTrail Lake event data store provides SQL queries over ingested events, filtering across multiple attributes, accounts/Regions, and combining supported sources. However, AWS closed CloudTrail Lake to new customers as of 31/05/2026. Customers who signed up before this date can continue using existing event data stores; AWS only commits to critical bug fixes and security updates, and recommends migrating to Amazon CloudWatch.

For existing organization event data stores, AWS continues to support operations and expansion to new member accounts/Regions. For account-level event data stores, data for existing accounts continues to be supported, but ingestion does not expand to new member accounts joining the organization. Verify the event data store type before adding accounts.

For new accounts, use a trail to store CloudTrail logs in S3, then analyze with Athena or send events to CloudWatch Logs for search/alerting. Do not plan new deployments on the assumption that you can create a CloudTrail Lake event data store.

Do not confuse Event history search with Lake queries: Event history has one attribute filter and one Region/account; CloudTrail Lake (for existing customers) provides more flexible SQL querying, though ingestion/retention incur costs.

## 12. Cost and optimizing audit coverage

CloudTrail has different billing components. Viewing Event history is free; management events have one free copy under CloudTrail pricing; additional copies, data events, network activity events, and Insights may incur charges. CloudTrail Lake ingestion/storage/querying applies to existing customers. Exact pricing varies by Region and pricing option, so check AWS CloudTrail Pricing before deploying.

### 12.1. Cost drivers

- Data events can be very high volume, especially S3 object reads/writes or Lambda invocations.
- Network activity events are billed when enabled.
- Insights events have separate charges; enabling Insights on both a trail and Lake can incur charges in both places.
- S3 storage, requests, replication, lifecycle retrieval, and KMS requests may incur charges.
- CloudWatch Logs ingestion/storage and metric filters have costs.
- For existing CloudTrail Lake customers, ingestion, retention, and queries depend on the pricing option.
- Athena charges per data scanned.

### 12.2. Optimizing selectors without losing audit evidence

1. Classify resources by sensitivity and compliance requirements.
2. Enable data events for buckets/prefixes, Lambda functions, tables, or resources needing investigation.
3. Use advanced selectors to limit by API name or ARN prefix when audit requirements allow.
4. Do not exclude read events if you need to investigate data access or reconnaissance.
5. Document selector decisions, owner, risk acceptance, and review schedule.
6. Test selectors using real events in a sandbox.
7. Monitor event volume and cost anomalies after deployment.

Do not optimize by disabling management events altogether, dropping log delivery validation, or omitting data events on sensitive data without a risk assessment. Coverage is a control requirement; cost must be optimized within approved coverage boundaries.

## 13. CloudTrail event investigation runbook

Example: The security team receives an alert that an IAM role modified the bucket policy on a production S3 bucket.

### 13.1. Scope the investigation

1. Identify the account ID, Region, bucket ARN, and alert timestamp.
2. Determine whether trail/event history coverage includes the event type under investigation.
3. If the event is within 90 days, start with Event history or `lookup-events`.
4. If the event is older than 90 days, query the S3 archive/Athena or CloudTrail Lake.
5. If you need object-level access details, verify that data events were enabled for the bucket/prefix.

### 13.2. Find the event

~~~bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=PutBucketPolicy \
  --region ap-southeast-1 \
  --max-results 50
~~~

Open the event record and inspect `userIdentity`, `eventTime`, `sourceIPAddress`, `userAgent`, `requestParameters`, `responseElements`, and `errorCode`.

### 13.3. Correlate actor and change

- If the actor is an assumed role, trace the role session name back to the pipeline/job/automation.
- If the actor is an IAM user, verify the owner, MFA context, and access key lifecycle.
- If the actor is an AWS service, check the service-linked role, service principal, and related workflow.
- Compare the bucket policy before/after using AWS Config or configuration snapshots.
- Check CloudTrail events for `AssumeRole`, `UpdateAssumeRolePolicy`, `AttachRolePolicy`, or credential changes around that timestamp.
- Cross-reference tickets/PRs/deployment records to distinguish approved changes from out-of-band changes.

### 13.4. Contain and preserve evidence

If the change was unauthorized:

1. Following the incident response procedure, restrict permissions or safely restore the bucket policy.
2. Preserve the relevant CloudTrail events, S3 log files, digest files, and CloudWatch logs.
3. Check object-level data events if needed to determine who read/deleted objects.
4. Verify the trail is still logging and S3 delivery has no errors.
5. Document the timeline, actor, resource, request ID, event ID, impact, and remediation.
6. Re-run checks and confirm the security posture has been restored.

Do not modify or delete log evidence to “clean up” after an incident. Restrict access to evidence copies and retain them according to retention/incident policy.

## 14. Hands-on labs in an AWS sandbox

### 14.1. Lab A — Finding a management event in Event history

1. Use a sandbox account and chosen Region.
2. Create a test resource, such as an S3 bucket or Security Group.
3. Open Event history and filter by Event source/Event name.
4. Find the resource creation event and record `eventTime`, `userIdentity`, `eventName`, `awsRegion`.
5. Run `aws cloudtrail lookup-events` with the same criteria.
6. Compare the Console and CLI results.
7. Try toggling the Read only filter to observe the difference between read/write events.

### 14.2. Lab B — Creating a multi-Region trail

1. Create a dedicated S3 archive bucket and apply a bucket policy for CloudTrail.
2. Create a multi-Region trail, enabling global service events and log file validation.
3. Run `start-logging`.
4. Check `get-trail`, `get-trail-status`, and `get-event-selectors`.
5. Trigger a management event in the sandbox.
6. Verify the log file is delivered to S3 under the account/Region/date path.
7. Enable CloudWatch Logs integration if required by the lab and verify the log group receives events.

### 14.3. Lab C — Recording S3 data events by prefix

1. Create a sandbox bucket with two prefixes: `public-test/` and `sensitive-test/`.
2. Create an advanced selector that only records `GetObject`/`PutObject` on `sensitive-test/`.
3. Upload objects to both prefixes and read the objects back.
4. Check the trail S3 logs or EventBridge events.
5. Confirm activity under the selected prefix appears while the prefix outside the selector is not recorded by that selector.
6. Estimate event volume and explain why you should not enable all buckets/objects unnecessarily.

### 14.4. Lab D — Network activity and VPC endpoint policy

1. Use a sandbox VPC with an interface/gateway endpoint for a service supported by CloudTrail network activity.
2. Configure a test endpoint policy to deny a specific API request.
3. Add an advanced selector with `eventCategory = NetworkActivity`, the corresponding `eventSource`, and `errorCode = VpceAccessDenied`.
4. Call the API through the VPC endpoint.
5. Verify the event has `eventType = AwsVpceEvent`, `vpcEndpointId`, and the corresponding error code.
6. Fix the endpoint policy and verify the request succeeds.

Only test deny policies in a sandbox; do not modify production endpoint policies for the lab.

### 14.5. Lab E — Investigating an Insights event

1. Choose a sandbox account with sufficient baseline management event activity.
2. Enable API call rate or API error rate Insights on a trail.
3. Run a test workload generating controlled API activity.
4. Wait for CloudTrail to build a baseline and detect an anomaly if triggered.
5. Inspect the Insights event, baseline/insight average, and supporting events.
6. Explain why Insights should not be treated as a real-time alarm or expected to emit events immediately.

### 14.6. Lab F — Verifying log file integrity

1. Create a trail with log file validation enabled.
2. Wait for digest files to be delivered.
3. Use the AWS CLI to validate logs for the trail and lab time range.
4. Read the validation output and note the verified files.
5. Do not modify/delete logs or digests in the bucket; test only on a test copy if demonstrating tampering detection.

## 15. Production CloudTrail review checklist

### Coverage

- [ ] Is Event history properly understood as 90 days of management events per Region?
- [ ] Does the trail have multi-Region coverage for enabled Regions requiring audit?
- [ ] Does the organization trail cover management/member accounts?
- [ ] Do management events record read/write per control requirements?
- [ ] Are data events enabled for sensitive resources/prefixes?
- [ ] Are network activity events enabled for VPC endpoints/services requiring audit?
- [ ] Is Insights enabled if there is a use case and budget?
- [ ] Have advanced/basic selectors been reviewed to avoid accidental gaps?

### Destination and delivery

- [ ] Dedicated S3 bucket, Block Public Access, and correct bucket policy?
- [ ] Does the bucket policy include `aws:SourceArn` restricting to the trail?
- [ ] S3/KMS encryption and key policy verified?
- [ ] Is `IsLogging` true and are delivery errors monitored?
- [ ] CloudWatch Logs integration/role policy working if used?
- [ ] EventBridge rules matching the right event type and event detail?
- [ ] Retention/lifecycle aligned with legal/compliance requirements?

### Integrity and access control

- [ ] Log file validation enabled?
- [ ] Digest files retained and not prematurely deleted by lifecycle rules?
- [ ] Archive read/delete/modify permissions separated by role?
- [ ] Versioning/Object Lock in place if anti-deletion/anti-tampering is required?
- [ ] KMS key administration separated from workload deployment roles?
- [ ] Changes to trails, selectors, bucket policies, and KMS key policies audited?

### Operations and cost

- [ ] Alerts configured for `StopLogging`, `DeleteTrail`, delivery failure, or selector changes?
- [ ] Process in place to verify trail coverage after adding accounts/Regions/resources?
- [ ] Data/network/Insights event cost and volume estimated?
- [ ] Athena/Lake/SIEM queries available to support investigations?
- [ ] Runbook specifies how to find events, preserve evidence, and correlate identities?
- [ ] Owner and review schedule defined for audit coverage?




## 16. Self-assessment questions

1. What activities does CloudTrail record in an AWS account?
2. How does Event history differ from a trail?
3. What event types does Event history store and for how long?
4. Why is Event history insufficient for long-term audit retention?
5. Can Event history query multiple Regions/accounts at once?
6. What is a trail used for and where are log files delivered?
7. How does a CloudTrail Lake event data store differ from a trail?
8. What are the four types of CloudTrail events?
9. Do management events belong to the control plane or data plane?
10. How do read events and write events differ?
11. Why is `GetObject` a data event while `PutBucketPolicy` is a management event?
12. Why do data events not appear in Event history?
13. What types of activity do network activity events record?
14. What does `VpceAccessDenied` indicate?
15. How do Insights API call rate and API error rate differ?
16. Which investigation question does `userIdentity` help answer?
17. What do `eventSource`, `eventName`, `awsRegion`, and `eventTime` mean?
18. Why should `requestParameters` not be treated as the full application payload?
19. Why is a CloudTrail log file not an ordered stack trace?
20. When should you choose a multi-Region trail?
21. How does an organization trail differ from an account trail?
22. Who can create an organization trail?
23. Which common data resource types do basic event selectors support?
24. What benefits do advanced event selectors provide?
25. Why can basic and advanced selectors not be applied simultaneously to a trail?
26. Why should selectors be verified after an update?
27. What primary permissions does an S3 bucket policy for CloudTrail need?
28. What does `aws:SourceArn` help protect against?
29. Why does log file integrity validation create digest files?
30. Does integrity validation prevent log deletion?
31. Why does EventBridge not replace the S3 trail archive?
32. Which event types can incur additional charges?
33. How do you optimize data events while keeping audit coverage?
34. When investigating an IAM change, which fields need to be correlated?

### Answer guide

- **Event history:** 90 days of management events, per account/Region, free to view, only one attribute filter and time range.
- **Trail:** continuously records selected events and delivers log files to S3; can send to CloudWatch Logs and integrate with EventBridge.
- **Event types:** Management is control plane; Data is resource/data plane; Network activity is APIs via VPC endpoints; Insights detects API rate/error anomalies.
- **Selectors:** Management events have All/Read/Write; data/network events must be explicitly selected, with advanced selectors enabling granular filtering.
- **Audit record:** `userIdentity`, `eventTime`, `eventSource`, `eventName`, `awsRegion`, `requestParameters`, `errorCode`, `resources`, `eventID`.
- **Integrity:** digests/signatures detect modifications after delivery; combine with S3 access control, retention, encryption, and deletion protection.
- **Operations:** verify logging/delivery status, selectors, Region/account coverage, EventBridge alerts, and cost.

## 17. Official AWS documentation

1. [Working with CloudTrail Event history](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html) — 90-day scope, filters, limitations, and Event history lookup.
2. [Understanding CloudTrail events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-events.html) — Event categories, management/data/network/Insights events, and record format.
3. [CloudTrail record contents](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-record-contents.html) — Fields in the JSON event record.
4. [How CloudTrail works](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/how-cloudtrail-works.html) — Overview of Event history, trails, Lake, and Insights.
5. [Creating a trail for your AWS account](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-create-and-update-a-trail.html) — Creating trails, multi-Region, and log delivery.
6. [Creating a trail for an organization](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html) — Organization trails and AWS Organizations.
7. [Organization delegated administrator](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-delegated-administrator.html) — Delegated administration for trails and event data stores.
8. [Logging management events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-management-events-with-cloudtrail.html) — Control plane, read/write, and management event selectors.
9. [Logging data events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html) — Data event resource types and selectors.
10. [Logging network activity events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-network-events-with-cloudtrail.html) — VPC endpoint activity and advanced selectors.
11. [Working with CloudTrail Insights](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-insights-events-with-cloudtrail.html) — API call rate/error rate anomalies.
12. [PutEventSelectors API](https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_PutEventSelectors.html) — Basic/advanced event selector API.
13. [Getting and viewing CloudTrail log files](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/get-and-view-cloudtrail-log-files.html) — S3 path, delivery, and log file organization.
14. [Amazon S3 bucket policy for CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/create-s3-bucket-policy-for-cloudtrail.html) — S3 delivery permissions and aws:SourceArn.
15. [Enabling log file integrity validation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-enabling.html) — Enabling digest/log validation.
16. [Validating CloudTrail log file integrity](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html) — Digest files and validation concepts.
17. [Sending CloudTrail events to CloudWatch Logs](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/send-cloudtrail-events-to-cloudwatch-logs.html) — CloudWatch Logs integration.
18. [AWS service events delivered via CloudTrail to EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-service-event-cloudtrail.html) — EventBridge rules for CloudTrail events.
19. [AWS CloudTrail pricing](https://aws.aws.amazon.com/cloudtrail/pricing/) — Pricing for event types, trails, and CloudTrail Lake.
20. [CloudTrail Lake availability change](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake-service-availability-change.html) — Sign-up closure for new customers as of 31/05/2026 and migration options to CloudWatch.

> **Final takeaway:** Event history enables quick lookup of management events over 90 days. Trails create long-term records in S3 and can cover multiple Regions/accounts. Management, data, network activity, and Insights events have different scopes; data/network/Insights must be enabled intentionally. Reliable auditing requires combining the right selectors, continuous log delivery, identity correlation, integrity validation, retention, and protected archive access.




