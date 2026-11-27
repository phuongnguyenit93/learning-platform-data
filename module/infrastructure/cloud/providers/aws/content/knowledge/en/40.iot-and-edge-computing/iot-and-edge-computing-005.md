# IoT Rules Engine and Telemetry Routing

## Lesson Objectives

In the CLOUD_PROVIDERS_AWS ecosystem, AWS IoT Core provides an MQTT message broker for devices and applications to send telemetry, receive commands, and exchange state. When messages enter the broker, AWS IoT Rules Engine can filter and transform payloads using a simple SQL-like syntax and route the data to AWS services such as Amazon S3, Kinesis Data Streams, Amazon Data Firehose, DynamoDB, Lambda, Amazon Timestream, AWS IoT SiteWise, SNS, SQS, or OpenSearch.

Rules Engine decouples devices from backend system details. Devices simply publish to a stable topic contract; rules decide which data gets stored, analyzed, alerted on, or forwarded to external systems. However, telemetry routing still requires explicit design of topics, schemas, IAM roles, retries, error actions, and idempotency. A single rule is not a distributed transaction spanning every action.

After this lesson, learners will be able to:

- Describe the message flow from devices through the MQTT broker, Rules Engine, and rule actions.
- Design a topic namespace for tenants, sites, devices, and telemetry types.
- Distinguish MQTT topic names from topic filters; properly use `+` and `#` wildcards.
- Write AWS IoT SQL with SET, SELECT, FROM, WHERE, and functions like `topic()` or `timestamp()`.
- Extract fields from payloads and topics, filter data, and build output documents.
- Select appropriate rule actions for S3, Kinesis, Firehose, DynamoDB, Lambda, Timestream, IoT SiteWise, SQS, and SNS.
- Use substitution templates to construct partition keys, object keys, or destination topics.
- Distinguish MQTT QoS from action execution results and design duplicate handling.
- Configure Basic Ingest to reduce messaging costs when pub/sub broker delivery is unnecessary.
- Design least-privilege error actions, IAM roles, and IoT policies.
- Monitor Rules Engine with CloudWatch metrics/logs and test telemetry pipelines end to end.

## 1. Rules Engine in AWS IoT Core Architecture

AWS IoT Rules Engine receives messages from the MQTT broker or Basic Ingest, matches topic filters, executes SQL statements, and delivers results to one or more actions. SQL can select fields, rename keys, compute derived values, and conditionally filter messages.

Basic flow:

~~~mermaid
flowchart LR
    D[IoT devices and gateways] -->|MQTT publish| B[AWS IoT Core message broker]
    B --> R[Rules Engine]
    R --> F[Topic filter and IoT SQL]
    F --> A1[Kinesis Data Streams]
    F --> A2[Amazon S3 or Data Firehose]
    F --> A3[DynamoDB or Timestream]
    F --> A4[Lambda or IoT SiteWise]
    F --> E[Error action]
    A1 --> C[Stream consumers and analytics]
    A2 --> L[Data lake]
    A3 --> Q[Applications and dashboards]
    A4 --> W[Business workflows]
~~~

Components:

| Component | Role |
|---|---|
| MQTT publisher | Device/gateway publishing messages to a specific topic |
| Message broker | Authenticates, delivers messages to subscribers, and passes matching messages to Rules Engine |
| Topic filter | Defines the set of topics monitored by a rule |
| AWS IoT SQL | Selects, filters, and transforms payloads |
| Rule action | Sends results to a supported AWS service or endpoint |
| Error action | Receives failure details when one or more rule actions fail |
| IAM role | Grants Rules Engine permission to access target resources |
| CloudWatch | Stores logs, metrics, and operational signals |

A single rule can have multiple actions. For example, the same telemetry message can be written to Kinesis for real-time processing and saved to S3 for historical analysis. Actions run independently per rule configuration; there is no ACID transaction spanning all targets.

Rules Engine processes messages and routes data. It does not replace complex stream processing systems or long-running workflows. When you need custom logic, external API calls, heavy computation, or multi-step stateful workflows, route messages to Lambda, Step Functions, Kinesis consumers, or a dedicated processing pipeline.

## 2. Designing the MQTT Topic Namespace

Topics act as the routing contract between devices, Rules Engine, and MQTT subscribers. Topics should convey ownership scope and message type while remaining structurally stable as the fleet grows.

A reference structure:

~~~text
org/{tenantId}/site/{siteId}/device/{deviceId}/telemetry
org/{tenantId}/site/{siteId}/device/{deviceId}/status
org/{tenantId}/site/{siteId}/device/{deviceId}/alert
org/{tenantId}/site/{siteId}/device/{deviceId}/command
org/{tenantId}/site/{siteId}/device/{deviceId}/command/accepted
org/{tenantId}/site/{siteId}/device/{deviceId}/command/rejected
~~~

Real-world topic examples:

~~~text
org/acme/site/hcmc-01/device/pump-042/telemetry
org/acme/site/hcmc-01/device/pump-042/status
org/acme/site/hcmc-01/device/pump-042/alert
~~~

Principles:

- Use a consistent segment order so rules can reliably extract tenant, site, and device.
- Separate telemetry, status, alerts, and commands into distinct branches so subscribers can filter exact message types.
- Never include passwords, tokens, emails, or personal data in topics.
- Keep topic names stable; structural changes require compatibility planning across firmware and rules.
- Use lowercase and consistent naming conventions; MQTT topics are case-sensitive.
- Include tenant/site/device in topics when scoped routing or authorization is required.
- Avoid putting all data types on a single topic if consumers need to handle them differently.

MQTT publishers send to a concrete topic name without wildcards. Wildcards appear only in subscriber or Rules Engine topic filters.

## 3. Topic Filters and Wildcards

In AWS IoT SQL, `FROM` takes a topic filter enclosed in single quotes. The rule triggers for each message whose topic matches the filter.

Two MQTT wildcards:

| Wildcard | Meaning | Example |
|---|---|---|
| `+` | Matches exactly one topic segment | `factory/+/telemetry` |
| `#` | Matches segments at the current level and below | `factory/#` |

Rules:

- `+` must occupy an entire segment and cannot be combined with other characters in that segment.
- `#` must be the final segment and occupy the entire segment.
- `+` and `#` can be combined in the same filter.
- `factory/+/telemetry` matches `factory/line-1/telemetry`, but does not match `factory/line-1/zone-a/telemetry`.
- `factory/#` matches topics starting with `factory/`; it does not match the parent topic `factory` without a trailing `/`.

Example rule monitoring telemetry across all devices for tenant `acme`:

~~~sql
SELECT *
FROM 'org/acme/site/+/device/+/telemetry'
~~~

The rule matches only topics with that exact segment structure. Using `#` too broadly can route far more messages than intended, increasing rule evaluations, target load, and cost. Scope filters by tenant, message type, and target device range.

### 3.1. MQTT Wildcards Differ from IoT Policy Wildcards

This is a frequent source of security misconfiguration:

- MQTT topic filters use `+` and `#`.
- AWS IoT Core policies use IAM wildcards `*` and `?`.
- Inside a policy document, `+` and `#` are literal characters with no wildcard meaning.

For example, a policy resource can use `*` to permit publishing to a set of topics. Scope wildcards in policies by tenant/device; never copy `org/acme/+/telemetry` verbatim into a policy expecting `+` to act as a wildcard.

In IoT policies, `iot:Publish` and `iot:Receive` use `topic` resources; `iot:Subscribe` uses `topicfilter` resources. Granting subscribe does not automatically grant receive permission.

## 4. AWS IoT SQL Structure

AWS IoT SQL is a simplified SQL-like syntax for message payloads. Main clauses:

| Clause | Role |
|---|---|
| `SET` | Declares reusable variables for SQL and substitution templates |
| `SELECT` | Selects fields, functions, and expressions to form the output payload |
| `FROM` | Topic filter determining which messages trigger the rule |
| `WHERE` | Condition deciding whether the message is forwarded to actions |

Example:

~~~sql
SELECT temperature AS tempC, humidity
FROM 'factory/+/telemetry'
WHERE temperature > 50
~~~

If the incoming message has payload:

~~~json
{
  "temperature": 72.5,
  "humidity": 61,
  "unit": "C"
}
~~~

The output sent to actions is:

~~~json
{
  "tempC": 72.5,
  "humidity": 61
}
~~~

Key points to remember:

- `SELECT *` preserves fields from the input payload.
- `AS` renames fields in the output.
- `WHERE` filters messages; if the condition evaluates false, actions are not triggered.
- SQL comments are not supported; do not embed `-- comment` in statements.
- Field names containing spaces cannot be referenced directly as SQL identifiers; with `*`, those fields can still pass through to the output.
- Explicitly specify `awsIotSqlVersion`. The Console currently defaults to `2016-03-23`; if CLI or CloudFormation omits the version, the default may be `2015-10-08`.

For rules invoked solely via Basic Ingest, `FROM` may be omitted. For rules receiving messages via the standard MQTT broker, `FROM` is required.

## 5. Extracting Topic Data and Enriching Metadata

Topics typically carry routing metadata such as tenant, site, and device. Payloads carry measurements, timestamps, and sequence numbers. The `topic(n)` function extracts the 1-based segment at position `n`; `topic()` returns the full topic string.

Suppose a device publishes:

~~~text
org/acme/site-hcmc/device/pump-042/telemetry
~~~

Results:

| Expression | Value |
|---|---|
| `topic(1)` | `org` |
| `topic(2)` | `acme` |
| `topic(3)` | `site-hcmc` |
| `topic(4)` | `device` |
| `topic(5)` | `pump-042` |
| `topic(6)` | `telemetry` |

The `timestamp()` function returns the current Unix epoch time in milliseconds as observed by Rules Engine. The `traceid()` function returns the MQTT message's trace ID if present.

Example telemetry:

~~~json
{
  "eventId": "evt-01J8QK9M4X",
  "sequence": 18231,
  "observedAt": "2026-11-20T06:30:00Z",
  "temperature": 72.5,
  "humidity": 61,
  "pressureKpa": 101.3,
  "batteryPct": 87
}
~~~

Rule SQL:

In a topic filter, `+` must occupy an entire segment. Therefore, `org/+/site-+/device/+/telemetry` is invalid: a wildcard cannot be combined with a `site-` prefix. For a namespace without a fixed `site` segment, the valid filter matching any site is:

~~~sql
SELECT
  *,
  topic(2) AS tenantId,
  topic(3) AS siteId,
  topic(5) AS deviceId,
  timestamp() AS receivedAt,
  traceid() AS mqttTraceId
FROM 'org/+/+/device/+/telemetry'
WHERE temperature >= -40
  AND temperature <= 125
  AND humidity >= 0
  AND humidity <= 100
~~~

When the topic namespace includes a fixed `site` segment, use:

~~~sql
SELECT
  *,
  topic(2) AS tenantId,
  topic(4) AS siteId,
  topic(6) AS deviceId,
  timestamp() AS receivedAt
FROM 'org/+/site/+/device/+/telemetry'
WHERE temperature >= -40
  AND temperature <= 125
  AND humidity >= 0
  AND humidity <= 100
~~~

`topic(n)` indices must match the exact topic structure. Whenever adding or removing a segment, update SQL, substitution templates, IoT policies, and test cases together.

## 6. Filtering and Transforming Telemetry

Rules Engine can filter messages by measurement value, device state, event type, or schema version. Filtering early prevents writing bad records or forwarding unnecessary messages downstream.

Example routing only high-temperature alerts:

~~~sql
SELECT
  topic(6) AS deviceId,
  temperature,
  observedAt,
  eventId,
  timestamp() AS receivedAt
FROM 'org/+/site/+/device/+/telemetry'
WHERE temperature >= 80
~~~

Example mapping numeric values to status labels:

~~~sql
SELECT
  deviceId,
  CASE
    WHEN batteryPct < 15 THEN 'LOW'
    WHEN batteryPct < 40 THEN 'MEDIUM'
    ELSE 'NORMAL'
  END AS batteryState,
  batteryPct,
  observedAt
FROM 'factory/+/device/+/telemetry'
WHERE batteryPct >= 0 AND batteryPct <= 100
~~~

Example using `SET` to define a reusable variable:

~~~sql
SET threshold = 80
SELECT
  topic(3) AS siteId,
  topic(5) AS deviceId,
  temperature,
  timestamp() AS receivedAt
FROM 'org/+/site/+/device/+/telemetry'
WHERE temperature >= threshold
~~~

Validate schemas before referencing fields in `WHERE`. If a payload omits a field or sends an unexpected data type, conditions may not evaluate as intended. For complex JSON payloads, you can use nested object expressions or supported external functions; check the limits of the SQL version and each function.

Rules Engine excels at filtering, projection, simple enrichment, and routing. Logic requiring multi-source joins, long-lived state, or complex algorithms should be handed off to Lambda, Amazon Managed Service for Apache Flink, Step Functions, or a dedicated processing service.

## 7. Substitution Templates in Rule Actions

Substitution templates allow action parameters to vary per message. Syntax:

~~~text
${expression}
~~~

Expressions can read payload fields, invoke SQL functions, use supported operators, or reference variables declared in the `SET` clause. Examples:

- `${topic(5)}` extracts the device ID from the topic.
- `${timestamp()}` generates the current timestamp.
- `${eventId}` reads the event ID from the payload.
- `${replace(topic(), '/', '-')}` converts the topic into a string suitable for object naming.

An important limitation: substitution templates are evaluated independently of the `SELECT` clause. They cannot reference aliases created with `AS`. For example, if SQL defines `topic(5) AS deviceId`, an action cannot assume `${deviceId}` will read that alias. Use `${topic(5)}` or an existing `deviceId` field from the original payload.

Example S3 object key:

~~~text
telemetry/${topic(3)}/${topic(5)}/${timestamp()}-${newuuid()}.json
~~~

If the topic structure is `org/{tenant}/site/{site}/device/{device}/telemetry`, select the exact segment indices for tenant/site/device. Object keys should include a unique component so two messages do not overwrite the same object.

## 8. Choosing Rule Actions by Target Goal

AWS IoT Rules Engine supports many actions targeting AWS services and select external endpoints:

| Action | Target | When Appropriate |
|---|---|---|
| Kinesis Data Streams | Stream record | Real-time processing, multiple consumers, partitioning by device/site |
| Amazon Data Firehose | Delivery stream | Buffering and delivering data to S3, Redshift, OpenSearch, or supported targets |
| Amazon S3 | Object storage | Storing raw telemetry, archives, data lakes, and replay |
| DynamoDB / DynamoDBv2 | NoSQL table | Current state, metadata, or events queried by key |
| AWS Lambda | Function | Custom logic, enrichment, or API calls |
| Amazon Timestream | Time-series database | Time-series queries by device, measure, and timestamp |
| AWS IoT SiteWise | Asset properties | Industrial telemetry modeled by asset models and hierarchies |
| Amazon SQS | Queue | Decoupling producers from asynchronous workers |
| Amazon SNS | Pub/sub notification | Fan-out notifications to multiple subscribers |
| OpenSearch | Search endpoint | Searching and analyzing logs/telemetry |
| CloudWatch Logs/Metrics | Observability | Recording operational logs or metrics |
| Republish | Another MQTT topic | Normalizing or forwarding messages within the MQTT namespace |
| Step Functions | State machine | Triggering multi-step workflows |
| HTTP / Apache Kafka | Endpoint or Kafka cluster | Integrating external systems where appropriate |

Available actions vary by Region and target service. Target service resources generally must reside in the same Region as the rule for actions to connect properly. Review specific action documentation for payloads, IAM permissions, limits, batching, and retries before deploying.

### 8.1. Kinesis Data Streams

Use Kinesis when multiple consumers need to read telemetry independently or when stream processing is needed. Choose a partition key based on business ordering needs, such as device ID so records from the same device map to the same shard.

Example action:

~~~json
{
  "kinesis": {
    "roleArn": "arn:aws:iam::111122223333:role/IoTRuleKinesisRole",
    "streamName": "iot-telemetry",
    "partitionKey": "${topic(6)}"
  }
}
~~~

For topic `org/acme/site/hcmc-01/device/pump-042/telemetry`, segment 6 is `pump-042`, so `${topic(6)}` uses the device ID as the partition key. Kinesis partition keys determine shard distribution and ordering; an overly hot key can cause a hot shard.

### 8.2. Amazon Data Firehose

Use Data Firehose when you need buffering and delivery to supported destinations without operating custom consumers. Firehose batches records and delivers data according to buffer size/interval settings.

Example action:

~~~json
{
  "firehose": {
    "roleArn": "arn:aws:iam::111122223333:role/IoTRuleFirehoseRole",
    "deliveryStreamName": "iot-telemetry-delivery",
    "separator": "\n"
  }
}
~~~

Configure format, compression, buffer hints, dynamic partitioning, and error prefixes on the Firehose delivery stream itself. Rules Engine simply sends records to Firehose; schema conversion, buffering, and delivery to S3/Redshift/OpenSearch are configured in Firehose. Verify record size and throughput limits on both services.

### 8.3. Amazon S3

Use S3 to store raw telemetry or archives. Object keys should partition by tenant, site, device, or time for efficient querying with Athena/Glue.

Example:

~~~json
{
  "s3": {
    "roleArn": "arn:aws:iam::111122223333:role/IoTRuleS3Role",
    "bucketName": "company-iot-raw",
    "key": "telemetry/${topic(2)}/${topic(4)}/${topic(6)}/${timestamp()}-${newuuid()}.json"
  }
}
~~~

For topic `org/acme/site/hcmc-01/device/pump-042/telemetry`, `topic(2)` is `acme`, `topic(4)` is `hcmc-01`, and `topic(6)` is `pump-042`. Keys include a timestamp and UUID to avoid overwrites. If larger files or small-file optimization are required, consider Firehose buffering instead of creating one S3 object per message.

### 8.4. DynamoDB and Timestream

DynamoDB fits applications reading current device state or querying by partition key. The `DynamoDBv2` action can write payload fields as individual item attributes; design key schemas and write capacity for telemetry rates. Avoid using a single shared partition key for the entire fleet.

Timestream fits time-series measurements. Choose dimensions such as tenant, site, device, and measure names aligned with query patterns. Ensure consistent timestamps and data types; avoid placing rapidly changing metadata into dimensions if it creates excessive cardinality.

### 8.5. Lambda, SQS, and SNS

Lambda fits custom logic, business rule evaluation, enrichment, or calling services lacking native actions. SQS fits decoupled worker processing with visibility timeouts and DLQs. SNS fits fanning out a single event to multiple subscribers.

If Lambda performs long-running work or downstream APIs can throttle, consider sending to SQS first and letting Lambda consume the queue. This decouples telemetry ingest rates from business processing speeds.

## 9. Multiple Actions per Rule: Telemetry Fan-Out

One rule can forward the same output to multiple actions. For instance, telemetry can go to Kinesis for real-time analytics and to S3 for raw archival.

~~~mermaid
flowchart TD
    A[MQTT telemetry] --> B[IoT SQL filter and enrich]
    B --> C[Kinesis Data Streams]
    B --> D[S3 raw archive]
    B --> E[CloudWatch metric]
    C --> F[Anomaly detection consumer]
    C --> G[Operational dashboard consumer]
    D --> H[Glue and Athena analytics]
~~~

Fan-out within a single rule reduces device publishes and centralizes routing logic. However, actions succeed or fail independently. For example, Kinesis might accept the record while the S3 action fails. An error action can record the S3 failure, but it does not roll back the record already written to Kinesis.

If multiple targets must all succeed together before considering a business operation complete, build a stateful workflow or orchestrating consumer. Rules Engine does not provide distributed transactions across S3, DynamoDB, and Kinesis.

## 10. Republish and Avoiding Rule Loops

The Republish action forwards output to another MQTT topic. This is useful for normalizing topics or creating consumer-specific topics.

Example:

~~~json
{
  "republish": {
    "roleArn": "arn:aws:iam::111122223333:role/IoTRuleRepublishRole",
    "topic": "normalized/${topic(2)}/${topic(4)}/${topic(6)}",
    "qos": 1
  }
}
~~~

Ensure the destination topic does not match the same rule processing the message; otherwise it creates a republish loop, inflating rule executions and costs. AWS recommends avoiding wildcard topic patterns in republish rules, as they can cause duplicate processing or routing loops.

One organizational approach is separating input and output namespaces:

~~~text
raw/...
normalized/...
alerts/...
commands/...
~~~

The rule listens only to `raw/#`, then republishes to `normalized/...`. Consumers read the normalized topic; never create a catch-all `#` rule that re-matches all outputs.

## 11. Basic Ingest: Sending Directly to Rules Engine

Basic Ingest lets devices or applications send data directly to a rule without traversing the publish/subscribe message broker. This lowers messaging costs when messages only need to reach rule actions and do not require broker fan-out to other MQTT subscribers.

Basic Ingest topics use the prefix:

~~~text
$aws/rules/{ruleName}/{originalTopic}
~~~

For example, for a rule named `TelemetryRouter` that processes topic:

~~~text
org/acme/site/hcmc-01/device/pump-042/telemetry
~~~

Devices publish via Basic Ingest to:

~~~text
$aws/rules/TelemetryRouter/org/acme/site/hcmc-01/device/pump-042/telemetry
~~~

Key points to remember:

- The device policy must allow publishing to `$aws/rules/*` or the specific rule prefix.
- The three prefix segments `$aws/rules/{ruleName}` are excluded from the value returned by `topic()`.
- A rule triggered solely via Basic Ingest can omit `FROM`; if it also receives messages via the broker, `FROM` is still required.
- Basic Ingest does not provide broker fan-out to MQTT subscribers.
- A QoS 1 PUBACK confirms the message reached Rules Engine, not that rule actions succeeded.
- Rule action error handling still works the same as for broker-routed messages.
- Basic Ingest removes messaging charges on the broker path; rule evaluation, target service, and action costs still apply separately.

Use Basic Ingest for telemetry entering a cloud data pipeline only. Keep standard MQTT broker pub/sub when gateways or other devices need to receive the same message, such as status, alerts, or control commands.

## 12. MQTT QoS, Retries, and Duplicates

AWS IoT Core supports MQTT QoS 0 and QoS 1; QoS 2 is not supported.

| QoS | Semantics | When Appropriate |
|---|---|---|
| QoS 0 | At most once; no PUBACK confirmation | High-frequency telemetry where losing some samples is acceptable |
| QoS 1 | At least once; broker returns PUBACK | Important events requiring MQTT-layer acknowledgement |

QoS is a contract at the MQTT layer between publisher and broker or broker and subscriber. It is not an end-to-end exactly-once guarantee across rule actions and database writes.

For example, a device publishes with QoS 1 and receives PUBACK. That does not mean records were successfully written to every target like Kinesis, S3, or DynamoDB. Basic Ingest documentation also notes that PUBACK only confirms delivery to Rules Engine, not completion of actions.

Rules Engine may retry actions upon transient failures. If all retries fail, the message is dropped and the error is written to CloudWatch Logs; if an error action is configured, failure details are forwarded to the error destination. Producer retries, action retries, or consumer retries can all introduce duplicates.

To handle this safely:

- Attach a stable `eventId` generated by the device/gateway.
- Keep `eventId` unchanged when retrying the same event.
- Include `deviceId`, `sequence`, or version to detect duplicates and out-of-order arrivals.
- Use conditional writes, unique keys, or idempotency records in consumers.
- With Kinesis, pick partition keys by the entity requiring ordering.
- With S3, generate unique object keys or use batches/manifests to avoid overwrites.
- With DynamoDB, design keys and conditional updates aligned with event semantics.
- Monitor event age and sequence gaps to detect data loss.

Never assume a rule action executes exactly once merely because MQTT QoS 1 returned PUBACK.

## 13. Error Actions and Error Handling

An error action is an optional action triggered by Rules Engine when a rule action fails. Examples:

- IAM role lacks `PutObject` permission on the bucket.
- DynamoDB throttling or invalid table/key configuration.
- Target endpoint does not exist or fails to respond.
- Misnamed Kinesis stream or Firehose delivery stream.
- Target service rejects the request.

Error actions handle failures during rule action invocation. They do not replace CloudWatch logging for debugging SQL syntax errors or external function failures inside the query.

An error message can contain:

| Field | Meaning |
|---|---|
| `ruleName` | Name of the rule that failed |
| `topic` | Original topic that received the message |
| `cloudwatchTraceId` | ID correlating with corresponding logs |
| `clientId` | MQTT client that sent the message |
| `base64OriginalPayload` | Original payload encoded in Base64 |
| `failures` | List of failed actions |
| `failedAction` | Name of the failed action |
| `failedResource` | Failing target resource |
| `errorMessage` | Description of the cause |

One error message is generated per rule/message pair. If two actions in the same rule fail, the error action can receive a single message containing both failures.

Example error action writing failures to S3:

~~~json
{
  "s3": {
    "roleArn": "arn:aws:iam::111122223333:role/IoTRuleErrorRole",
    "bucketName": "company-iot-rule-errors",
    "key": "errors/${replace(topic(), '/', '-')}-${timestamp()}-${newuuid()}.json"
  }
}
~~~

The error bucket should have a lifecycle policy and restricted access permissions. Original payloads may contain sensitive data; allow only authorized operations staff to read error objects.

Remediation workflow:

1. Inspect `cloudwatchTraceId` and `ruleName`.
2. Check `failedAction`, `failedResource`, and `errorMessage`.
3. Determine whether the root cause is IAM, quota, network, target availability, or payload/schema.
4. Fix the root cause and verify permissions/targets.
5. Replay messages from the error store using original event IDs.
6. Confirm targets processed the records and mark replay complete.

Error actions do not automatically replay messages after fixes. Build a controlled redrive process if zero telemetry loss is required.

Choose an error destination independent of the primary target whenever possible. For example, if the primary action writes to S3, use SQS or Kinesis as the error destination so S3 permission, bucket, or outage issues do not simultaneously lose error records. Error destinations must be durable with their own lifecycle and redrive process.

## 14. IAM and Permissions for Rules Engine

A rule action typically uses an IAM role so Rules Engine can access the target service. The role must exist in the same AWS account as the rule and have a trust policy allowing the `iot.amazonaws.com` service principal to assume it.

Trust policies should scope `aws:SourceAccount` and `aws:SourceArn` to the specific account and rule to mitigate confused deputy risks:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "iot.amazonaws.com"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "111122223333"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:iot:ap-southeast-1:111122223333:rule/TelemetryRouter"
        }
      }
    }
  ]
}
~~~

Policies attached to the role grant only permissions needed by the actions. Example role writing to Kinesis and S3:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "kinesis:PutRecord",
      "Resource": "arn:aws:kinesis:ap-southeast-1:111122223333:stream/iot-telemetry"
    },
    {
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::company-iot-raw/telemetry/*"
    }
  ]
}
~~~

If the target bucket, stream, or database uses a customer-managed KMS key, verify key policies/grants and required encrypt/decrypt permissions for the target service. An IAM policy granting `PutObject` or `PutRecord` does not automatically grant KMS key usage.

Whoever creates or replaces a rule needs `iam:PassRole` permission for the role attached to the rule. Do not grant `iam:PassRole` for all roles in the account if only a telemetry role is needed.

Lambda actions are an exception: the Lambda function uses a resource-based policy to allow AWS IoT to invoke it. Rule creators do not pass an IAM role to a Lambda action the way other actions do.

### 14.1. Device Policy and Rule Role Are Two Separate Layers

- Device IoT policy governs which topics a device can connect, publish, subscribe, or receive on.
- Rule IAM role governs whether Rules Engine can write data to Kinesis, S3, DynamoDB, or other targets.
- Operator IAM permissions govern who can create, modify, or delete rules and who can perform `iam:PassRole`.

Example allowing a device to publish only its own Thing's telemetry:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-southeast-1:111122223333:client/${iot:Connection.Thing.ThingName}"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": "arn:aws:iot:ap-southeast-1:111122223333:topic/org/acme/site/hcmc-01/device/${iot:Connection.Thing.ThingName}/telemetry"
    }
  ]
}
~~~

This policy illustrates Thing policy variables; attach the Thing to the certificate/principal and verify the actual Thing name. Never use wildcards allowing a device to publish to command topics or another device's telemetry.

Creating or updating a rule is a sensitive administrative privilege: anyone able to alter SQL/actions can access data processed by that rule. Restrict Rules Engine admin permissions and review all changes before production deployment.

## 15. Creating Rules with AWS CLI

A rule definition contains a name, SQL statement, SQL version, one or more actions, and an optional error action.

Example `telemetry-rule.json` file:

~~~json
{
  "sql": "SELECT *, topic(2) AS tenantId, topic(4) AS siteId, topic(6) AS deviceId, timestamp() AS receivedAt FROM 'org/+/site/+/device/+/telemetry' WHERE temperature >= -40 AND temperature <= 125",
  "awsIotSqlVersion": "2016-03-23",
  "ruleDisabled": false,
  "actions": [
    {
      "kinesis": {
        "roleArn": "arn:aws:iam::111122223333:role/IoTRuleKinesisRole",
        "streamName": "iot-telemetry",
        "partitionKey": "${topic(6)}"
      }
    },
    {
      "s3": {
        "roleArn": "arn:aws:iam::111122223333:role/IoTRuleS3Role",
        "bucketName": "company-iot-raw",
        "key": "telemetry/${topic(2)}/${topic(4)}/${topic(6)}/${timestamp()}-${newuuid()}.json"
      }
    }
  ],
  "errorAction": {
    "s3": {
      "roleArn": "arn:aws:iam::111122223333:role/IoTRuleErrorRole",
      "bucketName": "company-iot-rule-errors",
      "key": "errors/${replace(topic(), '/', '-')}-${timestamp()}-${newuuid()}.json"
    }
  }
}
~~~

Create the rule:

~~~bash
aws iot create-topic-rule \
  --rule-name TelemetryRouter \
  --topic-rule-payload file://telemetry-rule.json \
  --region ap-southeast-1
~~~

List rules:

~~~bash
aws iot list-topic-rules \
  --region ap-southeast-1
~~~

Get rule details:

~~~bash
aws iot get-topic-rule \
  --rule-name TelemetryRouter \
  --region ap-southeast-1
~~~

Disable a rule when routing needs to pause:

~~~bash
aws iot disable-topic-rule \
  --rule-name TelemetryRouter \
  --region ap-southeast-1
~~~

Re-enable:

~~~bash
aws iot enable-topic-rule \
  --rule-name TelemetryRouter \
  --region ap-southeast-1
~~~

ARNs in the example are placeholders. Create the stream, bucket, IAM roles, and policies before creating the rule. When changing SQL or actions, review impact across all matching topics; broad wildcard rules can cause sudden load spikes on targets.

## 16. Monitoring Rules Engine with CloudWatch

AWS IoT emits metrics and logs to monitor the message broker, rule evaluation, and rule actions. Metrics are published under the `AWS/IoT` namespace; CloudWatch metrics are typically published on a one-minute cadence.

Key metrics:

| Metric | Meaning | How to Use |
|---|---|---|
| `TopicMatch` | Messages matching the rule's topic filter | Verify the topic filter receives expected traffic |
| `RulesExecuted` | Number of rule executions | Measure overall activity |
| `RuleNotFound` | Invoked rule was not found | Detect Basic Ingest calling wrong/nonexistent rule names |
| `ParseError` | JSON parsing error on a topic watched by a rule | Detect malformed payloads |
| `RuleExecutionThrottled` | Message throttled by Rules Engine protection, e.g. Basic Ingest flooding a nonexistent rule | Investigate Basic Ingest traffic and rule names |
| `RuleEvaluation` with Status=Throttled | Rule evaluation throttled | Check account quotas |
| `Success` | Successful rule action invocation | Track by `RuleName` and `ActionType` |
| `Failure` | Failed rule action invocation | Identify failing target/action |
| `ErrorActionSuccess` | Error action executed successfully | Confirm failures are delivered to the error store |
| `ErrorActionFailure` | Error action failed | Alert on risk of losing error records |

Enable AWS IoT logging to write message broker and Rules Engine progress events to CloudWatch Logs. The standard log group is `AWSIotLogsV2`.

Sample log events:

- `RuleMatch`: message matched a rule.
- `StartingRuleExecution`: Rules Engine started running an action.
- `RuleExecution`: records action execution result.
- `RuleEvaluation`: records rule evaluation outcome or error.
- `RuleExecutionThrottled`: rule was throttled.
- `RuleNotFound`: Basic Ingest targeted a nonexistent or inactive rule.

Each log entry can include `traceId`, `topicName`, `ruleName`, `clientId`, `principalId`, `ruleAction`, and status. Use `traceId` to correlate messages, rules, and target errors.

### 16.1. Log Levels

AWS IoT supports these levels:

| Level | Content |
|---|---|
| `ERROR` | Failed operations |
| `WARN` | Indicators of potential inconsistencies or errors |
| `INFO` | High-level operational flow information |
| `DEBUG` | Detailed diagnostic information |
| `DISABLED` | Logging turned off |

Use `DEBUG` during active investigations and return to an appropriate level afterward. Debug logs increase log volume, CloudWatch costs, and may expose sensitive metadata. Avoid logging raw payloads unless necessary.

## 17. Optimizing Cost and Throughput

The cost of a telemetry pipeline can include AWS IoT messaging, rule evaluation, rule actions, target services, CloudWatch Logs/Metrics, Kinesis/Firehose, Lambda, and S3/Timestream storage. Optimizing Rules Engine requires looking at the entire pipeline rather than a single action.

Measures:

- Use Basic Ingest when messages only need rule actions without broker fan-out.
- Narrow topic filters so out-of-scope messages do not trigger rule evaluation.
- Avoid duplicating multiple rules listening to `#` when logic can be consolidated sensibly.
- Use `WHERE` to drop messages unneeded downstream.
- Match actions to workloads: Firehose for buffering/batch delivery; Kinesis for multiple stream consumers; S3 for archives; Timestream for time-series queries.
- Avoid invoking Lambda on every message when a native action meets the need.
- Batch or aggregate telemetry at gateways when data semantics and latency permit.
- Keep payloads compact, schemas stable, and omit unnecessary fields.
- Set retention/lifecycle policies on targets aligned with analytics needs.
- Monitor throttling, action failures, and destination capacity.

Basic Ingest eliminates broker-path messaging charges, but rule evaluation, action invocations, Firehose, Kinesis, S3, Lambda, and CloudWatch still incur charges. Check pricing pages by Region and actual message/action types.

If devices send thousands of messages per second, load-test both Rules Engine evaluation quotas and target throughput. A single rule fanning out to multiple targets multiplies downstream request volume; configure alarms before scaling the fleet.

## 18. Testing and Common Troubleshooting

AWS IoT Console includes an MQTT test client to subscribe and publish test topics. Use it to verify payloads, topic filters, and republish behavior before rolling out production firmware.

Testing workflow:

1. Create the rule in a development environment with an explicit SQL version.
2. Publish a valid payload to the expected topic.
3. Confirm `TopicMatch` and `RulesExecuted` increment.
4. Verify data arrives at every target action.
5. Publish an invalid payload to verify `WHERE` filtering or parse errors.
6. Temporarily revoke target permissions in the test environment to verify the error action.
7. Inspect `cloudwatchTraceId` and corresponding logs.
8. Publish a message with the same event ID twice to verify consumer deduplication.
9. Test out-of-scope topics to ensure the rule does not match.
10. Load-test at peak fleet throughput and monitor throttling and target latency.

Troubleshooting table:

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Rule does not run | Topic misses filter or rule is disabled | Check topic spelling, case, segments, and rule state |
| Topic wildcard misses | `+` inside segment or `#` not at end | Fix topic filter per MQTT wildcard rules |
| Rule SQL parse error | Wrong SQL version, field expression, or JSON payload | Check SQL version and CloudWatch IoT logs |
| `topic(n)` extracts wrong device ID | Segment index mismatches topic schema | Count segments from 1 and test with sample topic |
| Action gets AccessDenied | IAM role policy lacks permissions or wrong trust policy | Inspect role, resource ARN, `SourceAccount`/`SourceArn` |
| Rule cannot assume role | Trust policy lacks `iot.amazonaws.com` or cross-account role | Fix trust policy and ensure role is in the same account |
| Lambda action denied | Lambda resource policy does not allow IoT invoke | Add permission for service principal and source rule ARN |
| Kinesis action fails | Wrong stream Region/name or role lacks `PutRecord` | Check stream, Region, and IAM policy |
| S3 objects overwritten | Identical object key across multiple messages | Include timestamp, event ID, or UUID in the key |
| Error action does not run | Error occurred in SQL evaluation or error action lacks permissions | Use CloudWatch logs for SQL; check error destination permissions |
| Duplicate telemetry | QoS 1/action retries/producer retries | Use event IDs and idempotent consumers |
| Rules Engine throttling | Rule evaluation rate or wildcard fan-out too high | Narrow rule matches, check quotas, scale downstream |
| Target throttling | DynamoDB/Kinesis/SQS or API lacks capacity | Increase capacity, buffer via Firehose/SQS, or reduce ingest rate |
| Republish loop | Output topic re-matches the same rule | Separate raw/normalized namespaces and narrow `FROM` filter |
| Basic Ingest `RuleNotFound` | Prefix names wrong rule or rule inactive | Check `$aws/rules/{ruleName}` and `RuleNotFound` metric |

## 19. Lab: Factory Telemetry Routing

A factory operates multiple sites, each with numerous pumps and sensors. Each device sends telemetry every few seconds. The system must:

- Store all raw telemetry in S3.
- Stream real-time telemetry to Kinesis for anomaly detection.
- Persist current device state in DynamoDB.
- Route high-temperature alerts to SQS for worker processing.
- Keep publish permissions isolated per device.

### 19.1. Topic and Payload

Topic:

~~~text
org/acme/site/hcmc-01/device/pump-042/telemetry
~~~

Payload:

~~~json
{
  "eventId": "evt-000184",
  "sequence": 184,
  "observedAt": "2026-11-20T06:30:00Z",
  "temperature": 84.2,
  "pressureKpa": 104.8,
  "vibration": 0.72,
  "batteryPct": 87
}
~~~

### 19.2. Rule Routing

- A general telemetry rule subscribes to `org/+/site/+/device/+/telemetry`.
- SQL enriches `tenantId`, `siteId`, `deviceId`, and `receivedAt`.
- Kinesis action uses `deviceId` as the partition key.
- S3 action uses `tenant/site/device/time` to generate unique object keys.
- A dedicated alert rule filters `temperature >= 80` and sends to SQS.
- A job/consumer updates DynamoDB current state keyed by `deviceId` and `sequence`.

### 19.3. Operations and Verification

1. Create the Kinesis stream, S3 bucket, SQS queue, and DynamoDB table.
2. Create dedicated IAM roles for the Kinesis, S3, and SQS actions.
3. Create a device policy permitting publishing only to the Thing's exact telemetry topic.
4. Create the SQL rules and verify `topic(n)` indices against the topic schema.
5. Configure error actions storing failures in a dedicated S3 bucket or SQS queue.
6. Publish telemetry via the MQTT test client and verify all targets.
7. Publish both normal and high-temperature readings to verify `WHERE`.
8. Send the same event ID twice to confirm consumer deduplication.
9. Revoke target permissions in a test environment to verify the error action.
10. Enable CloudWatch metrics/logs and configure alarms for `Failure`, `RuleExecutionThrottled`, and `ErrorActionFailure`.
11. Load-test with simulated devices and expected publish rates.
12. Review messaging, rule action, and target service costs before scaling the fleet.

Success criteria:

- Topic filter captures the exact tenant/site/device.
- SQL output includes complete metadata without corrupting the schema.
- Kinesis partition key keeps records from the same device on the same partition mapping.
- S3 object keys never overwrite other messages.
- Alerts fire only when business conditions hold.
- Each action's IAM role holds only required target permissions.
- Error actions capture failure details and original payloads.
- Consumers handle duplicates safely.
- CloudWatch metrics distinguish SQL errors, action failures, and throttling.

## Conclusion

AWS IoT Rules Engine connects MQTT telemetry with the AWS ecosystem through topic filters, SQL statements, and rule actions. The topic namespace defines how messages are grouped and authorized; SQL determines what data is selected, filtered, and transformed; actions deliver telemetry to Kinesis, Firehose, S3, DynamoDB, Lambda, Timestream, IoT SiteWise, or other services.

A reliable pipeline chooses accurate topic filters, specifies the SQL version, applies substitution templates appropriately, grants least-privilege IAM roles, and provides error actions for target failures. MQTT QoS 1 does not guarantee every action completes exactly once; maintain stable event IDs and design idempotent downstreams. Basic Ingest cuts messaging costs when broker fan-out is unneeded, while CloudWatch metrics/logs provide visibility into rule execution and error handling.

For production designs, test with realistic topics/payloads, measure peak throughput, monitor target capacity, control wildcard fan-out, and rehearse error redrives. Rules Engine excels at routing and lightweight transformation; dedicated workflows or stream processors should handle multi-step, stateful business logic or complex transactional semantics.

## References

- [AWS IoT Rules Engine overview](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html)
- [Creating an AWS IoT rule](https://docs.aws.amazon.com/iot/latest/developerguide/iot-create-rule.html)
- [AWS IoT SQL reference](https://docs.aws.amazon.com/iot/latest/developerguide/iot-sql-reference.html)
- [AWS IoT SQL functions](https://docs.aws.amazon.com/iot/latest/developerguide/iot-sql-functions.html)
- [FROM clause and topic filters](https://docs.aws.amazon.com/iot/latest/developerguide/iot-sql-from.html)
- [AWS IoT rule actions](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rule-actions.html)
- [Substitution templates](https://docs.aws.amazon.com/iot/latest/developerguide/iot-substitution-templates.html)
- [Error handling and error actions](https://docs.aws.amazon.com/iot/latest/developerguide/rule-error-handling.html)
- [MQTT topics and topic filters](https://docs.aws.amazon.com/iot/latest/developerguide/topics.html)
- [MQTT protocol and QoS options](https://docs.aws.amazon.com/iot/latest/developerguide/mqtt.html)
- [Reducing messaging costs with Basic Ingest](https://docs.aws.amazon.com/iot/latest/developerguide/iot-basic-ingest.html)
- [Granting an AWS IoT rule the access it requires](https://docs.aws.amazon.com/iot/latest/developerguide/iot-create-role.html)
- [Passing role permissions](https://docs.aws.amazon.com/iot/latest/developerguide/pass-role.html)
- [Publish/Subscribe policy examples](https://docs.aws.amazon.com/iot/latest/developerguide/pub-sub-policy.html)
- [Configure AWS IoT logging](https://docs.aws.amazon.com/iot/latest/developerguide/configure-logging.html)
- [AWS IoT metrics and dimensions](https://docs.aws.amazon.com/iot/latest/developerguide/metrics_dimensions.html)
- [AWS IoT Core endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/iot-core.html)
- [AWS IoT Core pricing](https://aws.amazon.com/iot-core/pricing/)
- [AWS IoT Lens: failure management and error actions](https://docs.aws.amazon.com/wellarchitected/latest/iot-lens/failure-management.html)
