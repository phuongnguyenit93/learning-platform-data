# Log Groups, Log Streams, Retention, and Log Access Permissions

> **Chapter:** Observability with CloudWatch  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem across Regions/AZs, IAM, VPC, compute services, storage, databases, integration, and serverless; build the ability to choose services, design, and deploy secure applications with monitoring, recovery, and cost control.

When an application runs on AWS, logs are critical evidence for finding errors, understanding request behavior, monitoring security activity, and investigating incidents. Amazon CloudWatch Logs provides a central place for logs from Lambda, EC2, ECS, EKS, applications, and many AWS services. To manage logs effectively, you need to understand how log groups and log streams are organized, retention settings, permission mechanisms, and how to restrict log read access.

Logs often contain sensitive data such as email addresses, tokens, IP addresses, order details, or business data. A log configuration without retention can cause storage costs to grow unchecked; an overly broad IAM policy can let unauthorized users read sensitive data; an incorrect resource policy can allow another account to push logs in or read logs beyond the intended scope.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the relationship between log events, log streams, and log groups in CloudWatch Logs.
2. Choose how to organize log groups/streams by application, environment, and log source.
3. Configure log groups, retention, and appropriate encryption.
4. Distinguish workload log-writing permissions from log reading, querying, and administration permissions.
5. Write least-privilege IAM identity policies for CloudWatch Logs.
6. Explain the role of CloudWatch Logs resource policies in receiving logs from other services/accounts.
7. Grant permissions to use a KMS key when a log group is encrypted with a customer managed key.
8. Design cross-account logging, subscription filters, and centralized log access controls.
9. Reduce the risk of sensitive data exposure and manage storage costs.
10. Troubleshoot common errors involving log groups, log streams, retention, and AccessDenied.

## 2. How Does CloudWatch Logs Organize Data?

CloudWatch Logs has three fundamental concepts:

- **Log event:** a record consisting of a timestamp and a message. The message can be a line of text, JSON, or any format emitted by the application.
- **Log stream:** a sequence of log events from the same log source within a log group, typically tied to a specific instance, container, function execution environment, or source.
- **Log group:** a logical container for multiple log streams sharing the same purpose, retention configuration, permissions, and management policies.

~~~mermaid
flowchart TD
    APP["Application / AWS service"] --> GROUP["CloudWatch Logs log group"]
    GROUP --> S1["Log stream: instance-A"]
    GROUP --> S2["Log stream: instance-B"]
    GROUP --> S3["Log stream: container-C"]
    S1 --> E1["Timestamp + message"]
    S1 --> E2["Timestamp + message"]
    S2 --> E3["Timestamp + message"]
    S3 --> E4["Timestamp + message"]
~~~

A log group is the key unit for applying retention, encryption, data protection, tags, and many access controls. Log streams separate write streams by source; operators can inspect individual streams or query across the entire group.

### 2.1. Log Event Example

An application might write JSON logs:

~~~json
{
  "timestamp": "2026-11-20T04:30:00Z",
  "level": "ERROR",
  "service": "order-api",
  "requestId": "req-7f91",
  "message": "Payment authorization failed",
  "errorCode": "PAYMENT_PROVIDER_TIMEOUT"
}
~~~

In CloudWatch Logs, each event still consists of a timestamp and a message; the JSON resides inside the message. CloudWatch Logs Insights can parse JSON fields to query by `level`, `service`, `requestId`, or `errorCode`.

Do not include access tokens, passwords, secret keys, card data, or unnecessary personal data in messages. Mask sensitive fields in the application logger before shipping logs.

## 3. Designing Log Group and Log Stream Names

Log group names should reflect the service, environment, and purpose. A readable convention:

~~~text
/<platform>/<environment>/<service>/<purpose>

/platform/prod/order-api/application
/platform/prod/order-api/audit
/platform/staging/order-api/application
/platform/prod/payment-worker/application
~~~

For AWS services with their own conventions, keep the default group name if required by the service or if automatic integrations depend on it—for example, Lambda typically uses:

`/aws/lambda/<function-name>`

### 3.1. Naming Principles

- Include an explicit environment: `dev`, `staging`, `prod`.
- Include the service/team owner to clarify accountability.
- Separate application logs, audit logs, and security logs when retention/access requirements differ.
- Never embed email addresses, user account IDs, session IDs, or sensitive data in group/stream names.
- Never create a log group per request or per user; group counts grow rapidly and become hard to govern.
- Use a consistent naming convention across Regions and accounts.

### 3.2. Log Stream Naming

Streams can be named by source:

~~~text
instance/i-0123456789abcdef0
ecs/order-api/cluster-a/task-7d9c
lambda/order-api/2026/11/20/[$LATEST]abc123
~~~

These are illustrative examples; actual names depend on the service or agent. Do not create a new stream for every event. Each source should reuse streams as supported by the agent/service and manage stream creation properly.

### 3.3. Separating Application Logs and Audit Logs

Application logs support debugging and operations. Audit logs record activities requiring traceability, such as permission changes, order status updates, or administrative actions. These two types typically differ in:

- Read access: audit logs may be restricted to security/compliance roles.
- Retention: audit logs may need much longer retention per organizational policy.
- Integrity: audit logs may require immutable copies or forwarding to dedicated storage.
- Alerting: certain audit events require immediate alerting when they occur.

CloudWatch Logs can be part of an audit pipeline, but ordinary application logs do not automatically become a trustworthy audit record. You must explicitly design event sources, write permissions, protection, storage, and investigation workflows.

## 4. Creating Log Groups and Log Streams

Log groups can be created:

- Automatically by an AWS service when a workload starts logging, if supported by the service/configuration.
- Using AWS Console, AWS CLI, SDK, or CloudFormation.
- Via IaC before the workload is deployed.

Pre-creating log groups allows you to proactively configure retention, KMS encryption, tags, and access controls. If an application creates its own group at startup, the workload requires `logs:CreateLogGroup`; this can be omitted when the group is pre-provisioned.

### 4.1. AWS CLI: Creating a Log Group and Stream

~~~bash
aws logs create-log-group \
  --log-group-name /platform/prod/order-api/application \
  --region ap-southeast-1

aws logs create-log-stream \
  --log-group-name /platform/prod/order-api/application \
  --log-stream-name order-api-instance-a \
  --region ap-southeast-1
~~~

If the group or stream already exists, create commands may return a resource-already-exists error. In automation, handle idempotency properly: check for the resource first or catch only the already-exists error instead of ignoring all exceptions.

### 4.2. Sending a Log Event with the CLI

~~~bash
aws logs put-log-events \
  --log-group-name /platform/prod/order-api/application \
  --log-stream-name order-api-instance-a \
  --log-events timestamp=1795149000000,message="order-api started" \
  --region ap-southeast-1
~~~

Log event timestamps use Unix epoch milliseconds. In applications, prefer the AWS SDK, logging agents, or service integrations; never invoke the CLI per log message.

The CloudWatch Logs API enforces limits on event size, batch size, rate, and timestamp ordering. Check current quotas per Region/service and design batching, retries, and buffering accordingly.

### 4.3. Creating a Log Group with CloudFormation

~~~yaml
Resources:
  OrderApiLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /platform/prod/order-api/application
      RetentionInDays: 30
      Tags:
        - Key: Service
          Value: order-api
        - Key: Environment
          Value: prod
~~~

Provisioning log groups via IaC allows retention and tags to be reviewed in pull requests. If a log group is managed by CloudFormation, do not manually create one with the same name outside the stack and create conflicting ownership.

### 4.4. Pre-Creating a Log Group Before Lambda

Example of Lambda using a log group with fixed retention:

~~~yaml
Resources:
  OrderApiLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /aws/lambda/order-api
      RetentionInDays: 30

  OrderApiFunction:
    Type: AWS::Lambda::Function
    DependsOn: OrderApiLogGroup
    Properties:
      FunctionName: order-api
      Runtime: java21
      Handler: example.Handler::handleRequest
      Role: !GetAtt OrderApiExecutionRole.Arn
      Code:
        S3Bucket: deployment-artifacts
        S3Key: order-api/function.zip
      Timeout: 20
      MemorySize: 512
~~~

`OrderApiExecutionRole` and the artifact bucket/key are assumed to be defined and authorized in the actual deployment template. Naming the log group per Lambda's convention lets the function write directly into that group. If using a custom log group, configure the logging destination per Lambda's supported mechanism and verify permissions accordingly.

### 4.5. Creating Streams and Writing Logs Are Distinct Permissions

A workload may require:

- `logs:CreateLogStream` to create a new stream.
- `logs:PutLogEvents` to send events.
- `logs:CreateLogGroup` only if the workload is allowed to create groups itself.

If the group/stream is pre-created by IaC, the corresponding create permission can be removed from the runtime role. This reduces blast radius if the workload is compromised.

## 5. Retention: How Long Are Logs Kept?

Every log group has a retention policy. If retention is not configured, CloudWatch Logs keeps events indefinitely until deleted administratively or the group is deleted. This is a common reason storage costs climb steadily over time.

Retention is configured at the log group level in days. CloudWatch Logs supports predefined intervals ranging from 1 day to multiple years; choose only valid values supported by the API/service.

### 5.1. Choosing Retention by Purpose

| Log Type | Example Initial Retention | Reason |
| --- | ---: | --- |
| Development/debug | 3–14 days | Debug data is usually needed only briefly |
| Application production | 30–90 days | Sufficient window for typical operational troubleshooting |
| Security/audit | Per organizational policy, often much longer | Supports investigations, audits, or retention obligations |
| High-volume access logs | 7–30 days in CloudWatch, then archive if needed | Controls cost while keeping archived copies as needed |

These intervals are design suggestions, not compliance rules. Actual retention must follow legal, contractual, investigative, and organizational data policies.

### 5.2. Setting Retention with AWS CLI

~~~bash
aws logs put-retention-policy \
  --log-group-name /platform/prod/order-api/application \
  --retention-in-days 30 \
  --region ap-southeast-1
~~~

Inspect log group and retention details:

~~~bash
aws logs describe-log-groups \
  --log-group-name-prefix /platform/prod/order-api \
  --region ap-southeast-1
~~~

In the output, check `retentionInDays`. If this field is absent, the group has no retention policy and events are retained indefinitely.

### 5.3. Setting Retention with CloudFormation

~~~yaml
Resources:
  ApplicationLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /platform/prod/catalog-api/application
      RetentionInDays: 90
~~~

Managing retention with IaC ensures every environment's configuration is peer-reviewed and version-controlled. When changing retention, create a Change Set and confirm the new policy satisfies storage requirements.

### 5.4. Deleting a Retention Policy

~~~bash
aws logs delete-retention-policy \
  --log-group-name /platform/prod/order-api/application \
  --region ap-southeast-1
~~~

This command **deletes the expiration rule**, returning the log group to indefinite retention. It does not delete existing log events. Therefore, never use `delete-retention-policy` as a way to purge logs.

### 5.5. Expiration Does Not Mean Immediate Deletion

When an event passes its retention period, CloudWatch Logs marks it for deletion by a background process. Deletion may not occur the exact moment the cutoff passes; expiration processing is typically asynchronous and can take additional time.

Do not rely on retention expiration as a minute-accurate deletion mechanism or to fulfill immediate data erasure requests. If per-subject or per-request deletion is required, design appropriate data lifecycles and storage; logs should avoid containing unnecessary personal data in the first place.

### 5.6. Log Group Retention Is Not Archive Lifecycle Management

Retention in CloudWatch Logs governs when events expire from CloudWatch. If long-term storage at a different price tier or centralized analytics is required, ship logs to S3 or another storage system via a subscription/delivery pipeline. In that case, configure a separate lifecycle policy on the archive and verify copies do not outlive data governance policies unintentionally.

## 6. Encryption and Log Data Protection

CloudWatch Logs encrypts stored log data using default service-managed encryption. When key control is required, you can associate a log group with a supported AWS KMS customer managed key (CMK).

### 6.1. When to Use a Customer Managed Key?

A CMK may be appropriate when:

- The organization needs control over the key policy and key lifecycle.
- Key usage auditing is required.
- You want to separate key administration from log administration.
- Account-level or workload-level encryption/key ownership is mandated.

A CMK increases operational responsibility: key policies, IAM permissions, rotation, disable/delete protection, and KMS costs. If a key is disabled or its policy is misconfigured, access to encrypted data can break.

### 6.2. Associating a KMS Key with a Log Group

~~~yaml
Resources:
  ApplicationLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: /platform/prod/payment-api/application
      RetentionInDays: 90
      KmsKeyId: !GetAtt LogsKey.Arn

  LogsKey:
    Type: AWS::KMS::Key
    Properties:
      Description: Key for CloudWatch Logs encryption
      EnableKeyRotation: true
      KeyPolicy:
        Version: "2012-10-17"
        Statement:
          - Sid: EnableAccountAdministration
            Effect: Allow
            Principal:
              AWS: !Sub "arn:${AWS::Partition}:iam::${AWS::AccountId}:root"
            Action: "kms:*"
            Resource: "*"
          - Sid: AllowCloudWatchLogsUse
            Effect: Allow
            Principal:
              Service: !Sub "logs.${AWS::Region}.amazonaws.com"
            Action:
              - kms:Encrypt*
              - kms:Decrypt*
              - kms:ReEncrypt*
              - kms:GenerateDataKey*
              - kms:Describe*
            Resource: "*"
            Condition:
              ArnLike:
                kms:EncryptionContext:aws:logs:arn: !Sub "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/platform/prod/payment-api/*"
~~~

This policy example illustrates scoping the encryption context. When deploying, verify the service principal, key policy, and encryption context format for your Region/partition and current CloudWatch Logs integration. Different operations require different KMS permissions; never copy overly broad policies into production without review.

### 6.3. KMS Permissions and CloudWatch Logs Permissions Are Separate Layers

A principal reading a CMK-encrypted log group may require both the corresponding CloudWatch Logs permissions and permission to use the KMS key per service support. Granting `logs:FilterLogEvents` does not automatically grant `kms:Decrypt`; conversely, having `kms:Decrypt` does not grant permission to read the log group.

Keep these layers distinct:

- CloudWatch Logs permissions: which actions are allowed on the log group/stream.
- KMS key policy/IAM: which principals or services are allowed to use the key.
- Resource policy: whether other services/accounts can deliver logs or invoke supported actions on log resources.

### 6.4. Data Protection and Masking

CloudWatch Logs supports data protection policies to detect and mask certain sensitive data types during log access. This is an additional defense layer, not a substitute for stripping secrets/PII at the source.

Principles:

- Never log credentials, authorization headers, or secret payloads.
- Mask PII before writing logs.
- Restrict who can view unmasked/raw data if that feature is enabled.
- Test detection patterns using synthetic data.
- Account for archives, subscription destinations, and exports; masking at read time does not mean downstream copies were removed or altered.
## 7. IAM Identity Policies: Who Can Write and Read Logs?

An IAM identity policy attaches to a user, group, or role and defines which CloudWatch Logs APIs the principal may call. Separate two permission groups:

- **Writer permissions:** workloads/agents creating streams and sending log events.
- **Reader/operator permissions:** people or services querying, viewing, and configuring retention, encryption, and subscriptions.

Do not attach a broad log administration policy to every application role. Workloads only need to write logs; developers need read access to specific groups; platform/security teams handle administration or cross-group queries.

### 7.1. Writer Policy for One Log Group

Example role for a workload writing only to the order API log group:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CreateStreamsForOrderApi",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application:log-stream:*"
    }
  ]
}
~~~

If the log group is pre-created, the writer does not need `logs:CreateLogGroup`. If the workload must create groups itself, add that permission separately with an appropriate resource scope per the IAM Service Authorization Reference and naming conventions; do not default to `Resource: "*"` for all Logs actions.

Replace the account ID, Region, and log group name for your environment. The illustrative ARN is not a universal ARN across accounts.

### 7.2. Reader Policy Scoped to One Log Group

A developer who only needs to view and query order API logs can receive a narrow policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrderApiLogs",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:FilterLogEvents",
        "logs:StartQuery",
        "logs:StopQuery",
        "logs:GetQueryResults"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application:*"
    }
  ]
}
~~~

Some list/describe operations require `Resource: "*"` according to each action's resource-level permission table. If the console needs to list groups, you may need `logs:DescribeLogGroups` in a separate statement with a wildcard resource. Add only genuinely needed actions and test policies with IAM Access Analyzer or the policy simulator.

### 7.3. Reader Policy and Logs Insights

To run Logs Insights queries, users typically need:

- `logs:StartQuery` to start a query.
- `logs:GetQueryResults` to retrieve results.
- `logs:StopQuery` to stop a query.
- `logs:DescribeLogGroups`/`logs:DescribeLogStreams` if the UI needs to list groups/streams.

Query permissions can expose more data than viewing a single stream. Restrict which log groups can be queried and apply field-level/data protection controls where appropriate.

### 7.4. Log Group Administration Permissions

Administrative operations can include:

| Need | Commonly Involved IAM Actions |
| --- | --- |
| Create/delete group | `logs:CreateLogGroup`, `logs:DeleteLogGroup` |
| Create stream | `logs:CreateLogStream`, `logs:DeleteLogStream` |
| Set/delete retention | `logs:PutRetentionPolicy`, `logs:DeleteRetentionPolicy` |
| Associate/disassociate KMS key | `logs:AssociateKmsKey`, `logs:DisassociateKmsKey` |
| Configure subscription | `logs:PutSubscriptionFilter`, `logs:DeleteSubscriptionFilter`, `logs:DescribeSubscriptionFilters` |
| Configure data protection | `logs:PutDataProtectionPolicy`, `logs:DeleteDataProtectionPolicy` |
| Configure resource policy | `logs:PutResourcePolicy`, `logs:DeleteResourcePolicy`, `logs:DescribeResourcePolicies` |

Action names and resource-level support vary by operation; consult the Service Authorization Reference before writing policies. Never bundle all of these permissions into an application execution role.

### 7.5. Write and Read Permissions Should Belong to Different Roles

~~~mermaid
flowchart LR
    APP["Application role"] -->|CreateLogStream / PutLogEvents| LOGS["CloudWatch Logs"]
    DEV["Developer read role"] -->|Filter / Get / Query| LOGS
    OPS["Platform admin role"] -->|Retention / KMS / Subscription| LOGS
    SEC["Security audit role"] -->|Read audit groups| LOGS
~~~

An application role does not need to read back logs after writing them. Developers do not need permission to alter retention. Security audit roles do not need permission to deploy or delete log groups. Role separation limits blast radius if credentials are compromised.

## 8. Resource Policies and Receiving Logs from Other Services

CloudWatch Logs supports resource-based policies. Configured via `logs:PutResourcePolicy`, a resource policy can allow an AWS service principal or specified principal to perform supported actions on log resources.

Resource policies commonly appear in two scenarios:

1. An AWS service needs to deliver logs into an account's log group.
2. A destination needs to allow CloudWatch Logs from a source account to send subscription data.

Resource policies and IAM identity policies address two different sides. An identity policy states what a principal may do; a resource policy states which principals a resource accepts.

### 8.1. Resource Policies Do Not Replace Reader IAM Roles

Do not use a log-delivery resource policy as a way to grant developers read access to logs. For users to read logs, they need appropriate IAM identity policies on their principal, plus KMS permissions if the group uses a CMK.

### 8.2. Resource Policy Example for a Service Principal

An AWS service may require permission to write logs into a group per a supported integration. Illustrative policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowServiceToWriteLogs",
      "Effect": "Allow",
      "Principal": {
        "Service": "delivery.logs.amazonaws.com"
      },
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/network-flow-logs:*"
    }
  ]
}
~~~

This is an illustrative structure, not a copy-and-paste policy for every service. Service principals, `aws:SourceAccount`/`aws:SourceArn` conditions, resource ARNs, and actions must follow the specific service integration documentation. Some services use service-linked roles or dedicated delivery mechanisms.

### 8.3. Configuring a Resource Policy via CLI

~~~bash
aws logs put-resource-policy \
  --policy-name AllowApprovedLogDelivery \
  --policy-document file://logs-resource-policy.json \
  --region ap-southeast-1
~~~

View existing resource policies:

~~~bash
aws logs describe-resource-policies \
  --region ap-southeast-1
~~~

Resource policies have count, size, and scope limits. With account-level policies, avoid creating duplicate policies or granting service principals broader access than needed.

### 8.4. Distinguishing CloudWatch Logs Resource Policies from Destination Policies

In a subscription flow, the source log group has a subscription filter pointing to a destination. The destination in the receiving account has a policy allowing the source account to create subscriptions/send data via CloudWatch Logs' supported mechanism. Verify both ends:

- Source log group: `logs:PutSubscriptionFilter` permission and filter configuration.
- Destination: destination access policy, role/service permissions, and target resource policy.
- Target service: Lambda, Kinesis Data Streams, Amazon Data Firehose, or supported destination.

Configuring only the source subscription while forgetting the destination policy will cause subscription creation or delivery to fail.

## 9. Cross-Account Logging and Centralized Access

At multi-account scale, each workload account can write logs to its own log groups while a security/operations account centralizes observability or storage. Multiple models exist; choose based on your goal:

- **Cross-account observability:** use CloudWatch cross-account observability / Observability Access Manager (OAM) to share telemetry via supported link/sink configurations.
- **Subscription-based centralization:** use subscription filters to forward log events to centralized destinations such as Kinesis Data Streams, Data Firehose, or Lambda.
- **Archive:** ship logs to S3 for long-term storage, lifecycle management, or analytics outside CloudWatch.

These models differ in semantics, pricing, and permissions. OAM does not copy every log event into a central account; subscription pipelines are the mechanism for forwarding filtered log events to destinations.

### 9.1. Subscription Model

~~~mermaid
flowchart TD
    A["Workload account A"] --> G1["Application log group"]
    B["Workload account B"] --> G2["Application log group"]
    G1 --> F1["Subscription filter"]
    G2 --> F2["Subscription filter"]
    F1 --> D["Central destination"]
    F2 --> D
    D --> S["Security / analytics account"]
    S --> K["Kinesis / Firehose / Lambda"]
    K --> ARCH["S3 archive or analytics"]
~~~

### 9.2. Subscription Filters

A subscription filter selects events using a filter pattern and forwards matching events to a destination. Filter patterns can match severity or JSON fields, for example:

~~~text
{ $.level = "ERROR" }
~~~

Forwarding only events that require downstream processing reduces load and cost, but overly narrow filters can miss critical evidence. For security/audit streams, review filter patterns carefully and test them against sample logs.

### 9.3. Subscription Filter Example to Lambda

~~~yaml
Resources:
  ErrorLogSubscription:
    Type: AWS::Logs::SubscriptionFilter
    Properties:
      LogGroupName: /platform/prod/order-api/application
      FilterPattern: '{ $.level = "ERROR" }'
      DestinationArn: !GetAtt LogForwarderFunction.Arn
~~~

This example requires a Lambda resource policy allowing the CloudWatch Logs service to invoke the function, typically declared with `AWS::Lambda::Permission` specifying the appropriate `Principal` and a `SourceArn` scoped to the log group. The function receives a CloudWatch Logs subscription payload (a base64/gzip envelope); do not assume each invocation contains only one event.

### 9.4. Subscription Destinations to Kinesis/Firehose

When using Kinesis Data Streams or Data Firehose, CloudWatch Logs needs an IAM role it can assume to write to the destination. The role's trust policy must allow the correct service principal, and its permission policy must be scoped to the required stream/delivery stream ARN. Destination policies and account trusts must match your same-account or cross-account topology.

### 9.5. Key Limitations to Remember

- Each log group has a limit on the number of subscription filters; check current quotas.
- Some AWS service log groups may have restrictions on subscription filters.
- Filter patterns must be tested using actual masked events.
- Delivery may retry or be throttled by the destination; implement DLQs/reprocessing per target service capabilities.
- Do not forward the same logs to multiple pipelines without a clear purpose, as ingestion/delivery/storage can incur duplicate costs.

## 10. Reading and Querying Logs

Log access should be designed around tasks. Viewing a stream, filtering events, running Logs Insights queries, creating subscriptions, and deleting log groups are distinct operations.

### 10.1. Viewing Streams with AWS CLI

List streams:

~~~bash
aws logs describe-log-streams \
  --log-group-name /platform/prod/order-api/application \
  --order-by LastEventTime \
  --descending \
  --limit 20 \
  --region ap-southeast-1
~~~

Read events from a stream:

~~~bash
aws logs get-log-events \
  --log-group-name /platform/prod/order-api/application \
  --log-stream-name order-api-instance-a \
  --start-from-head \
  --limit 100 \
  --region ap-southeast-1
~~~

`GetLogEvents` can return a token to paginate through subsequent pages. Clients must handle pagination and stop when no new data returns; do not assume one response holds the entire stream.

### 10.2. Filtering Events in a Group

~~~bash
aws logs filter-log-events \
  --log-group-name /platform/prod/order-api/application \
  --filter-pattern '"PAYMENT_PROVIDER_TIMEOUT"' \
  --start-time 1795140000000 \
  --region ap-southeast-1
~~~

The filter pattern searches matching messages within the time window. Results may be paginated; `logs:FilterLogEvents` permissions should be restricted to authorized log groups.

### 10.3. Logs Insights Queries

Example counting errors by service and level:

~~~sql
fields @timestamp, service, level, requestId, message
| filter level = "ERROR"
| stats count(*) as errorCount by service
| sort errorCount desc
~~~

Example finding requests with timeout errors:

~~~sql
fields @timestamp, requestId, errorCode, message
| filter errorCode = "PAYMENT_PROVIDER_TIMEOUT"
| sort @timestamp desc
| limit 50
~~~

Logs Insights automatically discovers certain JSON fields. If an application uses a non-standard format, parse fields in the query or standardize the log format at the source.

### 10.4. Time Range Queries and Cost

- Choose the shortest time range sufficient to answer the question.
- Select only the necessary log groups.
- Filter early to reduce processed data volume.
- Avoid repeatedly querying across the entire retention window.
- Consider field indexes for suitable, supported query workloads.
- Save useful queries as query definitions for team reuse.

Logs Insights bills based on data scanned; unbounded time-range queries on high-volume log groups can become expensive.

## 11. Layered Access Permissions and Resource Scope

IAM policies must align actions, resource ARNs, and principals. Relying on action names alone is insufficient; some APIs are list/describe actions requiring wildcard resources, while event read/write APIs can be scoped to log group or stream ARNs.

### 11.1. Log Group and Stream ARNs

Example log group ARN:

~~~text
arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application
~~~

A log stream ARN appends the stream identifier:

~~~text
arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application:log-stream:order-api-instance-a
~~~

When a policy needs to cover all streams in a group, use a wildcard in the stream portion per IAM-supported resource ARN syntax. Avoid wildcarding accounts, Regions, or groups when only a specific service is needed.

### 11.2. Splitting Statements by Action Scope

Example policy requiring separate statements:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListLogGroups",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogGroups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadOnlyOrderApi",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogStreams",
        "logs:FilterLogEvents",
        "logs:GetLogEvents"
      ],
      "Resource": [
        "arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application",
        "arn:aws:logs:ap-southeast-1:111122223333:log-group:/platform/prod/order-api/application:log-stream:*"
      ]
    }
  ]
}
~~~

This policy illustrates separating list permissions from read permissions; exact resource ARNs must match the action/resource types in the Service Authorization Reference. Some actions have different resource ARN requirements or do not support resource-level scoping. Use the IAM policy simulator and test with a real role in a sandbox.

### 11.3. Permission Boundaries, SCPs, and Explicit Denies

An Allow in an identity policy does not guarantee an API call will succeed. Effective permissions are also constrained by:

- Role/user permission boundaries.
- Service control policies (SCPs) in AWS Organizations.
- Assumed-role session policies.
- Resource policies and KMS key policies.
- Explicit Denies in any applicable policy.

When receiving `AccessDenied`, verify the active principal with STS `GetCallerIdentity`, then inspect each policy layer. Never fix errors by attaching `AdministratorAccess` before identifying which permission is missing.

## 12. Cross-Account Access: Reading Logs and Sending Logs

Cross-account logging works in two distinct directions:

1. A principal in another account **reads** an existing log group.
2. A service/workload in another account **sends** log events to a centralized destination.

These two directions often require different mechanisms. Readers commonly assume a role into the account owning the log group or use CloudWatch cross-account observability via OAM. Delivery uses subscription destinations/resource policies or supported service integrations.

### 12.1. Assuming a Role to Read Logs

A security analyst in account A can assume `CentralLogReadRole` in account B. Role B's trust policy permits the specific principal/role in account A to assume it; the identity policy attached to role B grants read permissions on the required log groups.

~~~mermaid
sequenceDiagram
    participant Analyst as Analyst role (Account A)
    participant STS
    participant Role as CentralLogReadRole (Account B)
    participant Logs as CloudWatch Logs (Account B)
    Analyst->>STS: AssumeRole
    STS-->>Analyst: Temporary credentials
    Analyst->>Logs: FilterLogEvents / StartQuery
    Logs-->>Analyst: Log events / query results
~~~

Never place account B access keys inside account A. Use temporary credentials, tightly scoped trust policies, and appropriate session durations.

### 12.2. CloudWatch Cross-Account Observability

CloudWatch cross-account observability uses Observability Access Manager (OAM) with a sink in the monitoring account and links from source accounts. Organizations can share telemetry such as metrics, logs, and traces per OAM-supported data types and sources.

OAM shares observability visibility per configuration; it does not replace IAM authorization for viewers and does not automatically copy log data into the receiving account. Verify supported telemetry types, Region support, account relationships, and OAM policies before deploying.

### 12.3. Centralized Subscription Destinations

With cross-account subscriptions, the destination account creates a destination and an access policy allowing the source account to use it. The source account configures a subscription filter targeting the destination ARN. The role used for the destination must have trust and permissions aligned with the target service.

When troubleshooting failures, verify:

- The destination ARN specifies the correct account and Region.
- The destination policy allows the exact source account.
- The source role has permission to create the subscription filter.
- The target stream/Firehose/Lambda has permission to receive data.
- KMS key policies and destination encryption allow delivery.

### 12.4. Do Not Confuse Cross-Account Observability with Log Archiving

If the requirement is an independent log copy for centralized storage, design a subscription/export delivery pipeline to S3 or an appropriate data pipeline. If the requirement is viewing logs/metrics/traces from a monitoring account without copying all logs, evaluate OAM. Choose based on retention, access model, auditing, latency, and cost.

## 13. Lifecycle, Deletion, and Log Group Classes

Log groups have a lifecycle distinct from workloads. Deleting an application stack should not accidentally wipe out audit logs or logs that must be retained.

### 13.1. Deleting a Log Group

`DeleteLogGroup` deletes the group and all belonging log streams/events. This is a destructive operation; delete IAM permissions should be separated from read and write permissions.

If logs must survive application deletion:

- Separate the log group from the application stack or define an explicit retention strategy.
- Archive to S3 per policy and verify archive completeness.
- Use an appropriate DeletionPolicy if the group is managed by CloudFormation and must persist after stack deletion.
- Assign an owner and end-of-life deletion process for retained groups.

CloudFormation example:

~~~yaml
Resources:
  AuditLogGroup:
    Type: AWS::Logs::LogGroup
    DeletionPolicy: Retain
    UpdateReplacePolicy: Retain
    Properties:
      LogGroupName: /platform/prod/order-api/audit
      RetentionInDays: 365
~~~

`Retain` ensures the resource is kept when the stack is deleted or the resource is replaced per policy. It does not guarantee indefinite log retention if retention remains set to 365 days; retention and DeletionPolicy are two independent mechanisms.

### 13.2. Log Group Class

CloudWatch Logs provides log group classes with different feature sets and pricing, including Standard and Infrequent Access; certain delivery use cases have dedicated classes per service support. Choose a class based on how logs will be queried, filtered, and forwarded.

- Standard is suited when the full CloudWatch Logs feature set is required, including common operational features.
- Infrequent Access suits rarely accessed, cost-sensitive logs; verify feature limitations such as subscription/metric filters before choosing it.
- The class is chosen at group creation and should not be assumed directly mutable afterward. Changing classes requires creating a new group and migrating writers and consumers.

Do not pick a class based on ingestion price alone. Compare querying, filtering, data protection, Live Tail, subscriptions, and operational needs.

### 13.3. Migrating to a New Log Group

1. Create the new group with the target class, KMS key, and retention.
2. Grant writer permissions to the new group.
3. Update Lambda/agents/log drivers/service destinations.
4. Run in parallel or roll out gradually to avoid losing logs.
5. Verify event timestamps, stream creation, and query results.
6. Update reader roles, dashboards, alarms, and subscription filters.
7. Retain the old group per retention/archive policy before deleting it once no consumers remain.

## 14. Cost and Log Volume Governance

CloudWatch Logs costs can stem from ingestion, storage, Logs Insights queries, data delivery/exports, and related features. Pricing varies by Region, class, and feature; review current AWS pricing before budgeting.

### 14.1. Drivers of Rapid Log Growth

- Overly verbose debug logs in production.
- Logging large request/response bodies.
- Logging the same exception repeatedly across multiple layers.
- Retry loops generating thousands of events.
- Creating log groups per user or request.
- Retaining logs indefinitely.
- Frequently querying the full log history.
- Forwarding identical events to multiple destinations without clear justification.

### 14.2. Reducing Log Volume at the Source

- Use log levels properly and turn off DEBUG/TRACE in production.
- Log an exception once at the responsible handling layer, avoiding duplicate stack traces.
- Emit structured fields instead of repeating large payloads.
- Sample high-volume diagnostic events when business requirements allow.
- Never log secrets/PII or unnecessary payloads.
- Include request/trace IDs so each log event carries more diagnostic value.

### 14.3. Budgets and Cost Allocation

Tag log groups with `Service`, `Environment`, `Owner`, and `CostCenter`. Use AWS Budgets/Cost Explorer and CloudWatch usage metrics or billing data to monitor trends. Alert on abnormal spikes in ingestion, storage, or query scans.

Do not rely on retention alone to solve a cost spike. Identify the log producer and cut volume at the source first, then adjust retention/archiving/class per policy.

## 15. Troubleshooting Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| **Log group not found** | Wrong Region/account, group not created, or wrong name | Check caller identity, Region, group name, and service logging configuration |
| **Lambda runs with no logs** | Execution role lacks Logs permissions or function writes nothing to stdout/stderr | Check role, `CreateLogStream`, `PutLogEvents`, function execution, and log group |
| **AccessDenied on PutLogEvents** | Resource ARN mismatch on group/stream or missing action | Check stream ARN, active role, boundary/SCP, and explicit Deny |
| **AccessDenied on CreateLogGroup** | Runtime role lacks permission to create groups | Pre-provision the group via IaC or grant scoped create permissions |
| **Cannot create stream** | Wrong group, stream already exists, or missing `CreateLogStream` | Check group name, stream name, and writer permissions |
| **Reader sees group but cannot read events** | Missing `GetLogEvents`/`FilterLogEvents` or wrong resource scope | Check actions and stream/group ARNs for the API being called |
| **Logs Insights fails to run** | Missing `StartQuery`/`GetQueryResults`, wrong group/time range, or invalid query syntax | Check policy, log fields, time range, and query syntax |
| **Logs do not expire** | Retention not set or set on the wrong group | Check `retentionInDays` on the exact group and Region |
| **Logs still present after retention deadline** | Expiration/deletion runs asynchronously | Wait for background cleanup; do not treat retention as instant deletion |
| **KMS AccessDenied** | Key policy/IAM missing permissions or encryption context mismatch | Check KMS key state, policy, Region, and encryption context |
| **Cannot create subscription filter** | Missing source permission, destination policy, or target permission | Check source group, destination access policy, role trust, and target service |
| **Subscription exists but destination misses events** | Filter pattern mismatch, throttled delivery, or target error | Test pattern, inspect delivery errors/metrics, and check target logs |
| **Cross-account logs inaccessible** | Broken trust relationship, OAM link, or destination policy | Check account IDs, Region, role trust, sink/link, and resource policies |
| **Cannot delete log group** | Missing `DeleteLogGroup`, stack ownership, or resource protection | Check IAM, CloudFormation stack, and deletion policy |
| **Unusual log cost spike** | Verbose log level, retry storm, long retention, or broad query scans | Identify source, trim volume, and review retention/queries and subscriptions |

### 15.1. AccessDenied Investigation Workflow

1. Identify the failing API: `CreateLogGroup`, `CreateLogStream`, `PutLogEvents`, `FilterLogEvents`, or `StartQuery`.
2. Identify the actual principal using STS `GetCallerIdentity`.
3. Confirm Region, account ID, log group name, and stream ARN.
4. Inspect the identity policy and resource-level scope for the exact action.
5. Check permission boundaries, SCPs, session policies, and explicit Denies.
6. If using a CMK, inspect the KMS key policy, key state, and encryption context.
7. If using service delivery/subscriptions, inspect service principals, resource/destination policies, and target permissions.

Do not widen policies to `logs:*` or `Resource: "*"` just to make errors disappear. Fix the missing statement cleanly and verify with a test request in a sandbox.

### 15.2. Missing Logs Despite Successful Requests

Check in order:

- Is the application logging at the currently enabled log level?
- Is the logger writing to stdout/stderr or the exact file path tailed by the agent?
- Is the agent/log driver running with network connectivity to CloudWatch Logs endpoints?
- Does the workload role have permission to send events?
- Are the group and stream in the expected Region and account?
- Do event timestamps fall outside the viewed time range?
- Is a subscription filter dropping events before the destination?

A log event may still exist in the source group while being absent at the destination if the filter pattern does not match.

## 16. Reinforcement Exercises

### Exercise 1 — Distinguishing Groups and Streams

An ECS service runs 12 tasks in the same production environment. Should you create one log group or 12 log groups?

**Hint:** typically use one group per service/environment with separate streams per task/container per the log driver; split groups only when policies, retention, or access differ.

### Exercise 2 — Default Retention

A log group has no `RetentionInDays` configured. How long are events retained?

**Hint:** indefinitely until deleted manually or the group is deleted.

### Exercise 3 — Writer Least Privilege

A Lambda log group is pre-created by CloudFormation. Which permissions does the execution role need to create streams and send logs?

**Hint:** `logs:CreateLogStream` and `logs:PutLogEvents` on the matching group/stream ARN; `CreateLogGroup` is not needed if the group already exists.

### Exercise 4 — Reader Policy

A developer needs to run Logs Insights on the order API log group. Which primary permissions should be reviewed?

**Hint:** `StartQuery`, `GetQueryResults`, `StopQuery`, listing permissions required by the console, and scoped access to that group.

### Exercise 5 — KMS

A principal has `logs:FilterLogEvents` yet cannot read a CMK-encrypted group. Which other permission layer must be checked?

**Hint:** KMS key policy/IAM, key state, service integration, and encryption context.

### Exercise 6 — Resource Policy

An AWS service cannot deliver logs into a group. Why won't adding an IAM policy to a developer resolve this?

**Hint:** you must configure the appropriate resource policy or service delivery role for that specific service principal and integration.

### Exercise 7 — Cross-Account Log Export

A team wants to centralize log events from multiple accounts into Kinesis in a security account. Which components must be designed?

**Hint:** source subscription filters, destination, destination access policy, role trust/permissions, and Kinesis target policies.

### Exercise 8 — OAM or Subscription?

The operations team wants cross-account telemetry visibility; the security team wants an independent log copy in S3. Can the same mechanism serve both?

**Hint:** OAM serves cross-account observability; subscription/delivery pipelines suit forwarding log events to an archive.

### Exercise 9 — Log Expiration

A log group has 30-day retention set, yet some older events remain past the cutoff. Is that necessarily a misconfiguration?

**Hint:** no. Expiration/deletion runs asynchronously; verify retention on the exact group and allow background cleanup to complete.

### Exercise 10 — Cost Spike

CloudWatch Logs ingestion jumped fivefold after a deployment. Name potential causes of this change.

**Hint:** DEBUG enabled in production, retry storms, duplicate exceptions, oversized payloads, new log groups, or duplicate subscriptions.

## 17. Production Deployment Checklist

- [ ] Naming convention expresses environment, service, purpose, and owner.
- [ ] Group boundaries reflect retention, access, encryption, and lifecycle.
- [ ] Streams separate by source; never create groups/streams per request or per user.
- [ ] Log format includes timestamp, severity, service, request/trace ID, and appropriate error codes.
- [ ] Credentials, authorization headers, secrets, or unnecessary PII are never logged.
- [ ] Log groups are provisioned with IaC when stable retention, encryption, and tags are required.
- [ ] Runtime writer roles carry only required `CreateLogStream`/`PutLogEvents` permissions.
- [ ] `CreateLogGroup` is omitted when groups are pre-created and workloads do not need to create them.
- [ ] Reader roles can only access groups required for their duties.
- [ ] Query permissions, admin permissions, and delete permissions are separated.
- [ ] Resource policies restrict service principals/accounts and source ARNs/accounts where supported.
- [ ] KMS CMKs have reviewed key policies, encryption contexts, rotation, and recovery plans.
- [ ] Retention is configured per log type and data policy; production groups are not left indefinite unintentionally.
- [ ] Retention expiration is understood to be asynchronous; never used in place of immediate deletion.
- [ ] Audit/security logs have dedicated owners, retention, integrity, and archive strategies.
- [ ] Subscription destinations validate source filters, destination policies, role trusts, and target permissions.
- [ ] Cross-account observability is clearly distinguished from log event delivery/copy/archiving.
- [ ] CloudWatch Logs Insights queries restrict time ranges and target log groups.
- [ ] Log group class is chosen based on feature requirements and cost before creation.
- [ ] CloudFormation deletion/retention policies do not inadvertently lose audit logs.
- [ ] CloudWatch/Billing usage monitoring and alerts track unusual ingestion/storage/query spikes.
- [ ] Runbooks cover AccessDenied, KMS errors, missing events, retention, and subscription failures.

## 18. Key Takeaways

1. **Log events** hold timestamps/messages; **log streams** group events from one source; **log groups** group streams and act as the unit for retention, encryption, tags, and many policies.
2. A log group without a retention policy retains events indefinitely. Set retention intentionally and remember expiration happens asynchronously.
3. Workloads that only emit logs need narrow writer permissions; readers, queriers, and administrators need separate roles.
4. IAM identity policies, CloudWatch Logs resource policies, and KMS key policies protect distinct layers. None replaces the other two.
5. Cross-account observability via OAM differs from subscription pipelines forwarding log events to a destination.
6. `DeletionPolicy: Retain` preserves the log group upon stack deletion, but does not disable the group's retention period.
7. Select log group class based on required features and cost; do not assume a class can be switched in place after creation.
8. Reduce costs at the log producer, retention, query scope, and delivery duplication layers—not solely by tweaking retention days.

A solid logging system enables teams to investigate incidents rapidly, protect sensitive data, and control costs. Design permissions and retention when creating log groups, rather than waiting until logs pile up or a security incident occurs.

### Official Documentation

- [Amazon CloudWatch Logs User Guide](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/WhatIsCloudWatchLogs.html) — concepts of log groups, streams, and events.
- [CreateLogGroup API](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_CreateLogGroup.html) — creating log groups.
- [PutRetentionPolicy API](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_PutRetentionPolicy.html) — setting retention.
- [CloudWatch Logs retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Working-with-log-groups-and-streams.html) — managing groups, streams, and retention.
- [CloudWatch Logs IAM permissions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/permissions-reference-cwl.html) — IAM permissions for CloudWatch Logs.
- [CloudWatch Logs resource policies](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Subscriptions.html) — subscriptions and related resource policies.
- [Encrypt log data using AWS KMS](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/encrypt-log-data-kms.html) — encrypting log groups with KMS.
- [CloudWatch Logs Insights query syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html) — query syntax.
- [Subscription filters](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Subscriptions.html) — forwarding log events to destinations.
- [Cross-account observability](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Unified-Cross-Account.html) — sharing telemetry across accounts.
- [CloudWatch Logs pricing](https://aws.amazon.com/cloudwatch/pricing/) — ingestion, storage, and query pricing by Region.
- [CloudWatch Logs log classes](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CloudWatch_Logs_Log_Classes.html) — Standard and Infrequent Access.
