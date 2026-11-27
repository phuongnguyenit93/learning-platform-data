# Device Security, Telemetry Observability, and AWS Backend Integration

A production IoT system may manage thousands or millions of devices across factories, retail stores, vehicles, or remote locations. Each device sends telemetry, receives commands, installs firmware updates, and may operate over unreliable networks. If devices share credentials, MQTT topics are overly broad, or the backend fails to track connection states, a single compromised device can impact the entire fleet and operations teams will struggle to isolate whether a fault lies in the device, network, or cloud service.

AWS IoT Core provides the message broker, registry, policies, and device management capabilities to connect devices to cloud applications. AWS IoT Rules Engine can filter, transform, and route messages to backend services such as Amazon S3, Amazon Kinesis, AWS Lambda, Amazon DynamoDB, Amazon SQS, Amazon SNS, Amazon OpenSearch Service, AWS IoT SiteWise, and Amazon CloudWatch. AWS IoT Device Management provides capabilities including fleet provisioning, fleet indexing, jobs, and secure tunneling. AWS IoT Greengrass adds a runtime for edge processing and application management.

Within the **CLOUD_PROVIDERS_AWS** ecosystem, learners need to design unique identities per device, scope publish/subscribe permissions by topic, protect credentials, observe connectivity and telemetry, and integrate data into a scalable backend. This lesson focuses on three goals: ensuring devices only perform authorized actions, making device data and states observable, and enabling backends to ingest, process, and store telemetry in an operable, cost-controlled manner.

## 1. Overall Architecture of an IoT System

A reference architecture comprises devices/edge gateways, AWS IoT Core, Rules Engine, processing services, and an observability layer.

~~~mermaid
flowchart LR
    subgraph Edge["Devices and Edge"]
      A[Sensor / MCU]
      B[Industrial gateway]
      C[Greengrass components]
      A --> B
      B --> C
    end
    subgraph IoT["AWS IoT"]
      D[IoT Core MQTT broker]
      E[Thing Registry and Policies]
      F[Device Shadows]
      G[Rules Engine]
      D <--> E
      D <--> F
      D --> G
    end
    subgraph Backend["AWS Backend"]
      H[Kinesis / Firehose]
      I[Lambda / SQS]
      J[S3 data lake]
      K[DynamoDB / SiteWise / OpenSearch]
      L[CloudWatch]
      H --> J
      I --> K
    end
    C <-->|MQTT over TLS| D
    G --> H
    G --> I
    G --> K
    D --> L
    G --> L
~~~

Each component has a distinct responsibility:

- **Device identity:** identifies which device is connecting.
- **Authentication:** proves the device possesses valid credentials.
- **Authorization:** restricts which actions and topics a device may access.
- **Message broker:** ingests and distributes MQTT messages.
- **Device Shadow:** persists desired state and device-reported state.
- **Rules Engine:** routes telemetry to backend services.
- **Device Management:** provisioning, firmware/software jobs, indexing, and remote operations.
- **Observability:** tracks connections, errors, throughput, latency, data quality, and anomalous behavior.

Never share a single policy, certificate, or IAM role across all devices. Each layer needs its own permission boundaries and must be tested under scenarios such as network drops, compromised credentials, or backend unavailability.

## 2. Thing Registry and Device Identity

AWS IoT Thing Registry stores logical device metadata, represented as Things. A Thing can have a name, type, attributes, and Thing Group memberships. The registry helps organize the fleet and associate devices with certificates or principals.

Example Thing representing a temperature sensor:

~~~json
{
  "thingName": "factory-line-01-sensor-007",
  "thingTypeName": "TemperatureSensor",
  "attributePayload": {
    "site": "factory-01",
    "line": "line-01",
    "firmware": "2.4.1",
    "environment": "production"
  }
}
~~~

Thing Registry is not a telemetry store. Thing attributes describe devices and aid fleet management; continuous measurement data should flow through MQTT and Rules Engine to appropriate storage systems.

### Thing Groups

Thing Groups organize devices by site, model, environment, firmware, or operational unit. Thing Groups can be nested hierarchically, making it easier to target jobs and apply configurations across fleet scopes.

Example:

- `factory-01`
  - `line-01`
  - `line-02`
- `factory-02`
  - `line-01`

Grouping devices by production, staging, and test environments reduces the risk of accidentally pushing firmware or policies to the entire fleet.

## 3. A Unique Identity for Every Device

AWS recommends using a unique identity per device. With MQTT mutual TLS, devices typically authenticate using an X.509 client certificate and its corresponding private key.

Identity design should ensure:

- Certificates are generated individually per device or per unit with a distinct trust boundary.
- Private keys are stored in a secure element, TPM, or hardware-protected area when supported by the device.
- Certificates are attached to the appropriate Thing; consider exclusive attachment so one principal is never unintentionally shared.
- Certificate statuses (`ACTIVE`, `INACTIVE`, or `REVOKED`) are managed throughout the lifecycle.
- Procedures exist for issuance, rotation, revocation, and handling lost or stolen devices.
- Never bake a shared private key into a firmware image across an entire production batch.

Sharing a single credential makes revocation dangerous: revoking one device disrupts all other devices. Unique identities isolate incidents and provide a per-Thing audit trail.

## 4. X.509 Mutual TLS and Connection Protection

When a device connects via MQTT over TLS mutual authentication, both sides verify identity:

1. The device verifies the AWS IoT Core server certificate.
2. AWS IoT Core verifies the device's client certificate.
3. AWS IoT checks that the certificate is registered, active, and has an attached policy.
4. The policy determines which client ID the client may connect with and which topics it may publish/subscribe to.

Devices must verify the certificate chain and hostname of the AWS IoT endpoint. Never bypass certificate validation on TLS errors; doing so can allow devices to connect to spoofed servers.

### Device Clocks

Certificates carry validity windows. If a device clock is wrong, a valid certificate may appear not yet valid or expired. Devices should synchronize time via NTP before initiating TLS connections whenever hardware permits. For devices lacking an RTC or early network access, design a reliable time bootstrap step.

### On-Device Security Measures

- Secure boot so only verified firmware executes.
- Signed firmware with signature verification prior to installation.
- Disable debug interfaces or guard them with authentication.
- Encrypt sensitive data at rest on the device if stored locally.
- Restrict network services and open listening ports.
- Log security events locally and ship them when connected.
- Never log private keys, tokens, or secrets.

## 5. AWS IoT Policies and Least Privilege

AWS IoT Policies serve as the authorization layer for IoT actions such as connect, publish, subscribe, and receive. These policies are separate from backend IAM policies.

Key actions:

| Action | Purpose | Resource ARN |
|---|---|---|
| `iot:Connect` | Connect to the MQTT broker | `client` |
| `iot:Publish` | Send messages to a topic | `topic` |
| `iot:Subscribe` | Subscribe to a topic filter | `topicfilter` |
| `iot:Receive` | Receive messages from a topic | `topic` |

Policies should restrict:

- Allowed client IDs.
- Telemetry topics the device may publish to.
- Command topics the device may subscribe to.
- Shadow topics belonging to the Thing.
- Any additional APIs/operations the device strictly requires.

Do not grant wildcards across the entire topic namespace if a device needs only one branch. Overly broad policies can allow a device to read commands or data belonging to other devices.

## 6. Sample Policy Using Thing Policy Variables

Once a certificate is attached to a Thing, policy variables allow creating a reusable policy across many devices while still scoping permissions by Thing name. The example below permits a device to connect only with a client ID matching its Thing name, publish its own telemetry, and subscribe/receive its own commands.

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
      "Resource": "arn:aws:iot:ap-southeast-1:111122223333:topic/factory/${iot:Connection.Thing.ThingName}/telemetry"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Subscribe",
      "Resource": "arn:aws:iot:ap-southeast-1:111122223333:topicfilter/factory/${iot:Connection.Thing.ThingName}/commands"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Receive",
      "Resource": "arn:aws:iot:ap-southeast-1:111122223333:topic/factory/${iot:Connection.Thing.ThingName}/commands"
    }
  ]
}
~~~

Replace the account ID and Region with your environment values. Policy variables resolve only when the identity is attached to a Thing under supported conditions; if a variable fails to resolve, the request may be denied. The client ID in MQTT `CONNECT` must match the Thing name in this example.

Policies are one piece of authorization. When connections are denied, inspect certificate attachment, policy attachment, Thing Registry, and client ID in logs.

## 7. Certificate Lifecycle and Credential Rotation

Certificates should never be treated as set-and-forget configuration. Manage their lifecycle from manufacturing until end-of-life.

### Reference Rotation Workflow

1. Generate a new certificate and attach a Thing-scoped policy.
2. Deliver the new certificate to the device over an authenticated update channel.
3. Device validates the certificate/key pair and stores it securely.
4. Test connecting with the new certificate.
5. Verify telemetry, shadows, and commands operate normally.
6. Revoke or deactivate the old certificate after the device transitions successfully.
7. Record the credential version and rotation outcome in inventory.

Do not deactivate the old certificate before the device can use the new certificate, unless responding to an active compromise where temporary downtime is acceptable. For large fleets, roll out rotation in cohorts and track success rates.

### When a Device Is Lost or Suspected Compromised

- Deactivate/revoke the affected device's certificate.
- Narrow or detach related policies.
- Block or isolate the device on the local network if possible.
- Inspect client IDs, source IPs, topic activity, and message volume.
- Assess whether credentials were reused on another device.
- Re-issue identity and perform secure re-onboarding after remediation.

## 8. Fleet Provisioning: JITP and Fleet Provisioning

Manually creating Things, certificates, and policies per device does not scale for large fleets. AWS IoT supports automated provisioning options.

| Mechanism | How It Works | When Appropriate |
|---|---|---|
| Manual provisioning | Operator creates Thing/certificate/policy | Labs, prototypes, or small batches |
| Just-in-time provisioning (JITP) | Certificate signed by a registered CA; on first connect, AWS IoT registers and creates resources per template | Manufacturers with their own PKI and certificate issuance flow |
| Fleet Provisioning by claim | Device uses a narrowly scoped claim credential to obtain a unique certificate during onboarding | Mass-manufactured devices |
| Fleet Provisioning by trusted user | Trusted app/user drives onboarding flow for the device | Devices configured at point of sale or field installation |

Provisioning templates define the Thing, certificate, and policy to create. Pre-provisioning hooks can validate serial numbers, entitlements, inventory, or registration payloads before permitting resource creation.

### Protecting Claim Certificates

A claim certificate is a temporary onboarding credential and must not be used for long-term production communication. Claim policies should permit only required provisioning operations. Once the device receives its unique certificate:

1. Persist the permanent private key securely.
2. Complete `RegisterThing` per template.
3. Disconnect the claim session.
4. Reconnect using the unique certificate.
5. Verify the production policy is properly attached.

If a claim credential is extracted, attackers can attempt to register spoofed devices. Control manufacturing batches, protect claim keys, lock down templates, and validate device metadata.

### Testing Devices Before Fleet Rollout

AWS IoT Device Advisor provides test suites verifying that devices connect reliably to AWS IoT Core and meet best practices for TLS, MQTT, Device Shadow, Jobs, permissions/policies, and long-duration connections. Run tests on representative firmware and hardware prior to mass production; re-run relevant tests after updating TLS libraries, MQTT clients, or provisioning flows.

Device Advisor currently supports Regions `us-east-1`, `us-west-2`, `ap-northeast-1`, and `eu-west-1`; `ap-southeast-1` is not on the supported Region list. If your primary IoT deployment resides in Singapore, verify your connectivity design for reaching test endpoints in a supported Region before incorporating this tool into qualification workflows.

Device Advisor aids device qualification and troubleshooting. It does not replace hardware security testing, fuzzing, penetration testing, or production fleet monitoring.

## 9. MQTT and Topic Design

MQTT is a lightweight publish/subscribe protocol suited for devices constrained in CPU, memory, and bandwidth. Devices publish messages to topics; subscribers receive messages from topics or topic filters.

A topic convention should:

- Namespace by site, Thing, or message type.
- Separate telemetry, commands, status, events, and diagnostics.
- Maintain consistent casing and separators.
- Avoid embedding PII or secrets in topic names.
- Avoid overly deep nesting that complicates policy and filter management.

Example:

~~~text
factory/{thingName}/telemetry
factory/{thingName}/status
factory/{thingName}/commands
factory/{thingName}/events
factory/{thingName}/diagnostics
~~~

Topic names and payload schemas should be versioned. When changing schemas, include `schemaVersion` or topic versions so backends can handle both old and new producers during transitions.

## 10. MQTT QoS, Retained Messages, and Persistent Sessions

AWS IoT Core supports MQTT QoS 0 and QoS 1; QoS 2 is not supported.

| Mechanism | Meaning | Usage |
|---|---|---|
| QoS 0 | Delivered zero or more times; messages may be lost | High-frequency telemetry where losing occasional samples is acceptable |
| QoS 1 | Delivered at least once; duplicates possible | Commands or events needing confirmation; backend must be idempotent |
| Retained message | Broker keeps the latest message on a topic | Sending latest configuration or state to new subscribers |
| Persistent session | Preserves subscriptions and unacknowledged QoS 1 messages within service limits | Devices frequently offline needing messages upon reconnect |

QoS 1 does not mean exactly-once. Consumers can receive duplicates during retries or reconnects. Use `messageId`, sequence numbers, event timestamps, or idempotency keys to deduplicate on the backend.

Retained messages and Device Shadow serve different purposes. Retained messages store a single latest payload on a topic without standardized state schemas, automatic versioning, or deltas. Device Shadow provides desired/reported state, versioning, and timestamps.

Persistent sessions are not unlimited message queues. Stored messages have quotas, can expire, or can be dropped if limits are exceeded. Applications must still handle reconnects, replays, and state synchronization.

## 11. Standardizing Telemetry Payloads

Telemetry must carry sufficient context for the backend to identify source, timestamp, metric type, and schema. Sample payload:

~~~json
{
  "schemaVersion": "1.0",
  "deviceId": "factory-line-01-sensor-007",
  "eventId": "evt-20261120-00001234",
  "sequence": 1234,
  "eventTime": "2026-11-20T07:30:15.245Z",
  "measurements": {
    "temperatureC": 82.4,
    "humidityPct": 46.2,
    "vibrationMmS": 2.1
  },
  "quality": {
    "sensorStatus": "OK",
    "calibrationVersion": "cal-2026-04"
  }
}
~~~

Payload design guidelines:

- Use UTC and ISO 8601 for event times.
- Distinguish `eventTime` from backend ingestion time.
- Include `sequence`/`eventId` to detect duplicates and gaps.
- Specify units explicitly; avoid ambiguous field names like `temperature` without Celsius or Fahrenheit.
- Include `schemaVersion` to support schema evolution.
- Bound payload sizes and omit unneeded fields.
- Never place credentials, personal data, or secrets in telemetry.

If devices go offline, they can buffer telemetry locally and upload in batches when connectivity returns. Backends must accept late-arriving data and never assume messages arrive strictly in order.

## 12. AWS IoT Device Shadows

Device Shadow stores a device's logical state as a JSON document in AWS IoT. Applications can update the desired state even when the device is offline; the device synchronizes upon reconnecting.

Shadow documents feature three concepts:

- **desired:** the state applications want the device to achieve.
- **reported:** the current state reported by the device.
- **delta:** the difference between desired and reported.

Example where an application sets target temperature to 22°C:

~~~json
{
  "state": {
    "desired": {
      "targetTemperatureC": 22
    },
    "reported": {
      "targetTemperatureC": 24
    }
  }
}
~~~

Device Shadow emits a delta informing the device which value to change. Once applied, the device updates its reported state to 22.

### Named vs. Classic Shadows

Each Thing can have one classic unnamed shadow. Named shadows let you separate state by function, such as configuration, connectivity, or firmware. If you anticipate multiple independent state groups, consider named shadows early in the design.

### Versioning and Message Ordering

Shadow documents have a version that increments on each update. Clients can pass the current version to prevent overwriting with stale state. However, messages from AWS IoT are not guaranteed to arrive at devices in order. Devices should ignore deltas whose version is older than the last processed version.

Only trusted applications or devices should have permission to update `desired` state. If any client can alter `desired`, devices could receive unintended configurations.

## 13. AWS IoT Rules Engine

Rules Engine reads MQTT topic streams, applies SQL-like statements to filter/transform messages, and invokes one or more actions. Devices simply publish telemetry to AWS IoT Core; backends do not need to maintain dedicated MQTT subscribers for every data stream.

Processing flow:

1. Device publishes telemetry to a topic.
2. Rule filters by topic and payload conditions.
3. SQL projection selects or renames fields.
4. Rule actions forward results to backend services.
5. On action failure, an error action routes failed messages to dedicated handling.

Common actions include:

- Amazon S3 for storing raw events or files.
- Amazon Kinesis Data Streams for stream processing.
- Amazon Data Firehose for delivering data to S3 and supported targets.
- AWS Lambda for running business logic.
- Amazon DynamoDB for storing state or normalized events.
- Amazon SQS and Amazon SNS for asynchronous system integration.
- Amazon OpenSearch Service for log/event search and analytics.
- Amazon CloudWatch Logs and Metrics for observability.
- AWS IoT SiteWise for industrial data modeled by assets.
- AWS Step Functions for initiating workflows.

Action availability depends on Region and target service. Consult rule action documentation for your deployment Region.

## 14. Rule SQL and Telemetry Routing Example

Suppose devices publish to topic:

~~~text
factory/+/telemetry
~~~

The rule below extracts required fields and forwards messages only when temperature exceeds a threshold:

~~~sql
SELECT
    topic(2) AS deviceId,
    temperatureC,
    humidityPct,
    eventTime,
    sequence,
    timestamp() AS receivedAt
FROM 'factory/+/telemetry'
WHERE temperatureC >= 80
~~~

The rule can send data to Lambda to raise an alarm, or to Kinesis/Firehose for storage and analytics. `topic(2)` extracts the second segment from the topic, returning the Thing name for `factory/{thingName}/telemetry`.

### Roles for Rule Actions

Rules require IAM roles permitting AWS IoT to invoke actions on target services. For example, S3 actions require write access to the exact bucket/prefix; Lambda actions require invoke permission on the function; Kinesis actions require `PutRecord`/`PutRecords` permissions.

Separate roles by rule or data domain to limit blast radius. Never share an admin role across all rules.

## 15. Error Actions and Integration Failure Handling

A rule may match properly while the backend action fails due to missing permissions, quotas, network issues, or service unavailability. Error actions forward failure details and original payloads to a dedicated handler such as SQS, S3, or CloudWatch Logs.

Error handling design:

- Configure error actions on critical rules.
- Record rule name, action type, timestamp, and correlation ID.
- Separate bounded retries from dead-letter/error storage.
- Alert when action failure counts spike.
- Design idempotent downstream consumers.
- Maintain a message replay procedure once errors are fixed.

Never silently drop critical messages when actions fail. Non-critical telemetry may tolerate policy-driven sampling/dropping; alarms or commands require audit trails and explicit recovery mechanisms.

## 16. Backend Integration: Choosing Services by Workload

| Need | Suitable AWS Service | Design Hint |
|---|---|---|
| Long-term raw telemetry storage | Amazon S3 | Partition prefixes by time/device group and use lifecycle rules |
| Streaming analytics | Kinesis Data Streams | Consumers process near real-time |
| Managed buffering and delivery | Amazon Data Firehose | Batch writes to S3 or supported targets |
| Business logic or enrichment | AWS Lambda | Keep functions stateless and idempotent |
| Command/event queues | Amazon SQS | Decouple producers/consumers; configure retries and DLQs |
| Notifications | Amazon SNS | Fan out notifications to subscribers |
| Device state / key-value lookups | Amazon DynamoDB | Store fast-lookup current state |
| Search and log analytics | Amazon OpenSearch Service | Index searchable fields |
| Asset-modeled industrial data | AWS IoT SiteWise | Map telemetry into assets/properties |
| Operational metrics | Amazon CloudWatch | Monitor rules, broker, and backend |

Avoid piping all telemetry directly into Lambda if throughput is very high or processing is long-running. Kinesis/Firehose buffer and decouple ingestion from processing. Select services based on latency, ordering, retention, throughput, and consumption patterns.

## 17. Storing Telemetry in S3 and Building a Data Lake

S3 suits storing raw telemetry and curated data with flexible storage tiers. Use the S3 Rule Action for simple streams or Amazon Data Firehose when buffering, batch delivery, and transformations are needed.

A reference layout:

~~~text
s3://iot-data-lake/
  raw/
    site=factory-01/
      year=2026/month=11/day=20/hour=07/
  curated/
    site=factory-01/
      year=2026/month=11/day=20/
~~~

The `raw` layer retains original messages for replay; `curated` standardizes schemas, timestamps, units, and deduplicates records. AWS Glue Data Catalog stores metadata so Athena or Redshift Spectrum can query the data.

Avoid creating one S3 object per small message at high throughput. Use Firehose buffering or stream processing to compact batches into appropriately sized files, reducing request and metadata overhead.

## 18. Integrating with AWS IoT SiteWise for Industry

AWS IoT SiteWise fits industrial operational data where telemetry maps to assets, equipment, properties, and hierarchies.

Example:

- Factory is a top-level asset.
- Production line is a child asset.
- Motor is an equipment asset.
- Temperature, pressure, and vibration are asset properties.

Rules Engine can route messages into SiteWise asset properties. This binds sensor readings to an asset model, powering dashboards, metric computations, and equipment performance tracking.

If data consists only of generic events or application logs, S3/Kinesis/OpenSearch may fit better. Do not force every telemetry stream into an asset model.

## 19. AWS IoT Greengrass for Edge Processing

AWS IoT Greengrass V2 brings an edge runtime and component deployments to edge devices. Edge devices process data close to the source, react to local events, and continue critical operations when cloud connectivity drops.

Use cases:

- Filtering or aggregating sensor data on-site before sending to the cloud.
- Running inference near cameras or industrial machinery.
- Bridging legacy devices via gateways.
- Running local MQTT pub/sub among components.
- Controlling equipment or detecting anomalies with low latency.
- Managing components and configurations across fleets of edge devices.

### Components

- **Greengrass nucleus:** core runtime orchestrating components and cloud connectivity.
- **Components:** applications, Lambda functions, connectors, or dependencies running at the edge.
- **Deployments:** component/version/parameter configurations rolled out to core devices or device groups.
- **Local resources:** files, ports, device interfaces, or services accessed by components.

Greengrass does not replace AWS IoT Core. IoT Core manages cloud connectivity and the cloud message broker; Greengrass manages edge runtimes and local processing.

## 20. Edge Offline Behavior and Data Synchronization

Edge networks can be intermittent. Production systems must explicitly define what keeps running when the cloud is unreachable:

- Which local control loops must keep operating.
- Which telemetry is buffered at the edge.
- Disk capacity and offline retention windows.
- Behavior when buffers reach capacity.
- Catch-up upload and deduplication policies upon reconnect.
- How desired/reported states and configurations synchronize.
- How to prevent executing expired commands after devices come back online.

Never place cloud dependencies inside safety-critical control loops when equipment must remain safe during network loss. Design local fail-safes, watchdogs, and manual overrides per system requirements.

### Store-and-Forward

Edge gateways can write telemetry to a local queue/database and upload in batches to the cloud. Every event needs an ID, sequence, and event time. Backends should be idempotent because batches may be retransmitted after timeouts upon reconnect.

## 21. AWS IoT Jobs for Firmware and Software Updates

AWS IoT Jobs manages remote operations sent to one or more Things or Thing Groups. Job documents describe tasks devices must run, such as downloading firmware, installing software, rebooting, rotating certificates, or running diagnostics.

A deployment can configure:

- Rollout rate: speed of job distribution across the fleet.
- Abort criteria: halt rollout when error rates exceed thresholds.
- Timeout: time limit for a device to complete execution.
- Retry: re-enqueue failed job executions per policy.
- Scheduling: schedule maintenance or updates within time windows.

### Safe OTA Workflow

1. Build firmware and sign artifacts.
2. Store artifacts in a protected location.
3. Create a job document with version, checksum, and installation instructions.
4. Target a test Thing Group.
5. Devices download the artifact, verify signature/checksum, and install.
6. Devices report job execution status.
7. Monitor success rates, reboots, reconnects, and health metrics.
8. Expand rollout across cohorts.
9. Abort or roll back if failure thresholds are exceeded.

Jobs manages distribution and remote operation status; on-device firmware installers must still validate integrity, hardware compatibility, and rollback capability.

## 22. Fleet Indexing and Device Management

Fleet indexing searches Things and aggregates attributes/Shadow data according to indexing configuration. Operations teams can find devices by firmware version, site, connectivity state, or indexed attributes.

Example operational questions:

- Which devices are still running an outdated firmware version?
- Which devices at `factory-01` have been disconnected for a long time?
- Which devices report `calibration expired`?
- How many devices belong to a cohort needing updates?

Thing attributes and Shadow data can be indexed as configured. Avoid indexing every field unnecessarily; weigh limits, costs, and sensitive data exposure.

Fleet indexing finds and groups devices, while Jobs targets those groups to deploy operations. Combining both establishes a continuous discover → target → update → verify loop.

## 23. AWS IoT Device Defender: Audit and Detect

AWS IoT Device Defender provides security posture auditing and device behavior monitoring.

### Audit

Audit evaluates account/device configurations against best practices, such as:

- Multiple devices sharing a single identity/certificate.
- Overly broad policies allowing a device to access other devices' topics.
- Expired or revoked certificates still active.
- Configurations increasing unauthorized access risk.

Audits run on demand or on schedules. Findings include severity levels for operations teams to remediate.

### Detect and Availability Status

Detect uses cloud-side metrics from AWS IoT and device-side metrics from agents/SDKs to detect anomalous behavior such as traffic spikes, connections to unexpected endpoints, or changes in listening ports.

**Current availability note:** AWS announced that AWS IoT Device Defender Detect is no longer open to new customers. Eligible existing customers may continue using it under service terms; AWS IoT Device Defender Audit remains available to new customers. Therefore, new architectures should not depend on Detect as a guaranteed capability available in every account.

If an account already has Detect enabled, security profiles can monitor behavior by Thing Group and send alerts via CloudWatch/SNS. Otherwise, build custom monitoring using CloudWatch metrics/logs, Rules Engine, Kinesis, and appropriate analytics.

## 24. Observing Telemetry and Fleet Operations with CloudWatch

AWS IoT Core emits CloudWatch metrics for the message broker, rule engine, rule actions, authentication, provisioning, shadows, jobs, and other components. Metrics are published periodically, typically every minute.

Metric groups to monitor:

| Group | Metrics or Signals | Operational Question |
|---|---|---|
| Connectivity | `Connect.Success`, `Connect.AuthError`, `Connect.Throttle`, `Connection.AuthNError` | Are devices connecting; are there authentication or authorization errors? |
| Message broker | `PublishIn.Success`, `PublishIn.AuthError`, `PublishIn.Throttle`, `PublishOut.Success`, `PublishOut.Throttle` | Are messages accepted/delivered or denied/throttled? |
| Persistent sessions | `Queued.Success`, `Queued.Throttle` | Are QoS 1 messages for offline devices being queued? |
| Rules | `TopicMatch`, `RulesExecuted`, `RuleExecutionThrottled`, `ParseError`, `RuleNotFound` | Are rules matching, executing, and parsing payloads cleanly? |
| Rule actions | `Success`, `Failure`, `ErrorActionSuccess`, `ErrorActionFailure` | Are backend actions or error actions failing? |
| Shadow | `GetThingShadow.Accepted`, `UpdateThingShadow.Accepted` | Are Shadow reads and updates succeeding? |
| Jobs | `QueuedJobExecutionCount`, `InProgressJobExecutionCount`, `FailedJobExecutionCount` | Are OTA rollouts backing up or failing? |
| Provisioning | `ProvisionThing.Success`, `ProvisionThing.ClientError`, `ProvisionThing.ServerError`, `RegisterThingFailed` | Is device onboarding failing? |

Rule action metrics use `RuleName` and `ActionType` dimensions. `Connection.AuthNError` indicates connection-layer authentication failures and can include external Internet scanning activity, whereas `Connect.AuthError` indicates message-broker authorization failures. Exact metric names and dimensions vary by API, protocol, and resource type; verify current AWS IoT metrics documentation before creating alarms.

### Recommended Alarms

- Rapid increase in `Connection.AuthNError` or `Connect.AuthError`; correlate source IPs and log reasons to distinguish genuine devices from external scans.
- Abnormal spikes in `Connect.Throttle` or `PublishIn`/`PublishOut.Throttle` above baseline.
- Publish throttling or message quotas nearing limits.
- Rising rule action failures or falling `ErrorActionSuccess`.
- Increasing rejected Shadow updates.
- Job execution failures crossing rollout thresholds.
- Provisioning failures rising after publishing a new template.

## 25. AWS IoT Core V2 Logging

CloudWatch metrics reveal trends and counts; CloudWatch Logs help investigate specific events. AWS IoT Core V2 logging supports three configuration levels:

- **Account-level:** default level across the account.
- **Event-level:** customized by event type such as authentication/authorization.
- **Resource-specific:** overrides by Thing Group, source IP, client ID, or principal ID.

Event-level and resource-specific logging are V2 logging features. Accounts still on V1 logging must migrate to V2 before using these granular controls.

Log levels:

| Level | Content |
|---|---|
| `ERROR` | Failed operations, e.g., expired certificate |
| `WARN` | Risks or conditions that may cause inconsistencies |
| `INFO` | High-level operational flows, e.g., client subscribed successfully |
| `DEBUG` | Detailed diagnostic events, e.g., Rules Engine starting execution |
| `DISABLED` | Logging turned off for the configured scope |

Enabling logging requires an IAM role allowing AWS IoT to write to CloudWatch Logs. Anyone authorized to read CloudWatch Logs can view device debug details, so restrict log access carefully.

### Logging Strategy

1. Start with `INFO` or an appropriate level during testing.
2. Enable `DEBUG` only for specific resources or events under investigation.
3. Revert to `WARN`/`ERROR` once root causes are identified.
4. Configure log group retention policies.
5. Avoid logging sensitive payloads unnecessarily.
6. Monitor CloudWatch Logs ingestion costs.

During large load tests, overly verbose logging creates massive ingestion volume and impacts cost and throttling. Use resource-specific logging to narrow the scope.

## 26. Distinguishing Service Logs, Telemetry, and Device-Side Logs

These three data types answer three different questions:

| Data Type | Examples | Where Stored / Observed |
|---|---|---|
| Service logs | Authentication failures, rule action errors, disconnect reasons | CloudWatch Logs from AWS IoT Core |
| Telemetry | Temperature, vibration, battery, pressure | S3, Kinesis, SiteWise, or workload-appropriate time-series stores |
| Device-side logs | Firmware crashes, sensor driver errors, local queue full | Edge log collectors, Greengrass Log Manager, or dedicated upload pipelines |

Never substitute service logs for telemetry. AWS IoT Core logs show failed message publishes, not a full history of sensor measurements. Conversely, telemetry may show temperature rising, but it cannot explain why certificate authentication was rejected.

## 27. Security Monitoring and Anomaly Detection

Even when devices authenticate with certificates, credentials can be stolen or firmware may harbor vulnerabilities. Establish baselines per device type and Thing Group.

Signals worth monitoring:

- Hourly connect/disconnect counts.
- Authentication/authorization failures.
- Message rates and payload sizes.
- Publish/subscribe ratios per topic.
- Unusual IP or source network changes.
- Skewed device clocks or certificates nearing expiration.
- Open listening TCP/UDP ports at the edge.
- Unapproved firmware versions.
- Devices transmitting outside operating hours or expected geographic zones.

Where Detect is unavailable to new customers, you can:

1. Route events/security metrics through Rules Engine.
2. Publish metrics to CloudWatch or stream to Kinesis.
3. Compute baselines per device type/Thing Group.
4. Set CloudWatch alarms on clear thresholds.
5. Use Lambda or stream processors to detect complex patterns.
6. Send findings to SNS/SQS/ticketing workflows.
7. Run mitigation workflows to deactivate certificates, narrow policies, or trigger investigative IoT Jobs.

Do not automatically deactivate certificates from a single anomaly if false positives risk halting critical equipment. For high-impact actions, require severity tiers, secondary checks, and approval workflows.

## 28. Mitigation and Incident Response

When signs of device compromise appear:

1. Identify the Thing, certificate, principal, client ID, and source IP.
2. Inspect connection logs, policy authorizations, and topic activity.
3. Compare against Thing Group baselines.
4. Isolate the device on the edge network if possible.
5. Deactivate/revoke the certificate or narrow policies as needed.
6. Halt or cancel active Jobs targeting affected devices.
7. Preserve logs and telemetry for investigation.
8. Evaluate peer devices sharing the same firmware, claim credentials, or similar configs.
9. Re-issue credentials and deploy patched firmware once verified safe.
10. Document root cause, detection time, containment time, and blast radius.

Mitigations can be automated via AWS IoT Device Defender Audit/Detect where available to the account, or via Lambda/Step Functions and IoT APIs. Test revocation and recovery actions on a staging fleet before enabling in production.

## 29. Protecting Telemetry Data

Telemetry can reveal factory operations, device locations, production output, or user behavior. Protect it in transit, at rest, and on access:

- TLS for device-to-AWS IoT connections.
- SSE-S3 or SSE-KMS for S3 data as required.
- KMS key policies restricting which principals can decrypt.
- Rule Action IAM roles scoped strictly to target destinations.
- S3 bucket policies blocking public access and restricting prefixes.
- Lake Formation or catalog permissions for data analytics.
- CloudTrail to audit changes to IAM, IoT policies, certificates, and resources.
- Data retention and lifecycle aligned with usage needs.
- Mask or strip PII before ingesting into analytics.

Never place sensitive secrets in MQTT topic names or logged payloads. If telemetry must reference user identifiers, use tokenized/pseudonymous IDs and isolate sensitive mappings in a tightly restricted store.

## 30. Managing Quotas, Throughput, and Costs

IoT fleets can generate high traffic volumes depending on device count, publish frequency, and payload size. Costs arise from connections/messaging, Rules Engine, downstream actions, S3, Kinesis/Firehose, Lambda, CloudWatch Logs, and storage.

### Optimizing Ingestion

- Match sampling intervals to business requirements.
- Batch multiple measurements into one payload where appropriate.
- Use QoS 0 for loss-tolerant telemetry and QoS 1 for events needing confirmation.
- Bound payload sizes and avoid continuously sending unchanged fields.
- Buffer at the edge during network outages.
- Use Kinesis/Firehose to batch records before writing to S3.
- Separate high-volume telemetry from command/control topics.

### Optimizing Backends

- Use Rule SQL to project only required fields.
- Filter early before invoking Lambda or writing to databases.
- Apply S3 lifecycle policies to raw data.
- Compact small files in the data lake.
- Set sensible CloudWatch Logs retention.
- Set alarms on rule throttling, Lambda errors, and queue backlogs.
- Track costs by site, Thing Group, or data domain.

Never lower telemetry frequency if doing so blinds incident detection or violates safety requirements. Optimize around informational value and SLOs rather than message counts alone.

## 31. End-to-End Example: Production Line Temperature Monitoring

A factory operates 2,000 temperature and vibration sensors across multiple production lines. Each device sends telemetry every 30 seconds, receives cloud configuration, and requires staged firmware updates.

### Design

1. Each sensor has its own Thing and X.509 certificate.
2. Fleet Provisioning creates Things/certificates/policies during device onboarding.
3. IoT policies allow connecting only with the Thing's client ID, publishing its telemetry, and subscribing to its own commands.
4. Devices publish JSON telemetry to `factory/{thingName}/telemetry`.
5. An IoT Rule filters over-temperature readings and forwards alarm events to Lambda/SNS.
6. Firehose writes batched telemetry to an S3 raw data lake.
7. Glue Data Catalog describes curated data; Athena queries historical trends.
8. Device Shadow stores desired configurations like sampling interval alongside reported firmware/status.
9. Greengrass gateways perform local filtering and buffering during WAN outages.
10. IoT Jobs rolls out firmware by Thing Group starting with canary before factory-wide rollout.
11. CloudWatch metrics/logs monitor connections, authentication, rule actions, and backends.
12. Device Defender Audit checks policies/certificates; if Detect is unavailable in the account, custom metrics and alarms fill the gap.

### Architecture Diagram

~~~mermaid
flowchart TB
    A[Temperature / vibration sensors] --> B[Edge gateway / Greengrass]
    B -->|MQTT TLS| C[AWS IoT Core]
    C --> D[Thing Registry / X.509 / IoT Policies]
    C --> E[Device Shadow]
    C --> F[Rules Engine]
    F --> G[Lambda / SNS alarm]
    F --> H[Firehose]
    H --> I[S3 raw and curated lake]
    I --> J[Glue Catalog / Athena]
    C --> K[CloudWatch metrics and logs]
    L[IoT Jobs] --> B
    M[Device Defender Audit] --> D
~~~

### Operations

- If authentication errors rise, check certificate expiry, clocks, and policies.
- If rule action failures rise, check IAM roles, quotas, and downstream services.
- If temperatures exceed thresholds, alert operations while still persisting full telemetry.
- If canary firmware exhibits high failure rates, abort the job before wider rollout.
- If WAN disconnects, the edge continues local control and buffers telemetry within capacity limits.

## 32. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| TLS handshake fails | Clock skew, untrusted CA/server cert, or bad client cert | Sync NTP, verify server hostname/CA, and check certificate validity |
| MQTT connect denied | Inactive cert, policy missing `iot:Connect`, or wrong client ID | Check cert, Thing attachment, policy, and client ID |
| Publish gets `AccessDenied` | Topic ARN mismatch or policy lacks `iot:Publish` | Verify actual topic and policy variables |
| Subscribe succeeds but no messages arrive | Missing `iot:Receive` or publisher on different topic | Verify both `Subscribe` topicfilter and `Receive` topic |
| Duplicate messages | QoS 1 retries or reconnects | Use `eventId`/sequence and idempotent processing |
| Offline device misses commands | Expired session, QoS/queue limit, or unsaved commands | Use Shadow for desired state; design retries and expiry |
| Shadow update rejected | Stale version or missing topic permissions | Fetch latest shadow, check version and topic permissions |
| Rule does not match | Wrong topic filter or SQL expression | Test topic, payload, and Rule SQL |
| Rule action fails | IAM role lacks permissions or target throttled | Inspect Rule metrics/logs, role policy, and quotas |
| No IoT logs in CloudWatch | V2 logging disabled or bad logging role | Check V2 options, trust policy, and log group permissions |
| Job rollout stalls | Device offline, timeout, or installer fails to report | Inspect job executions, device logs, and retry policy |
| Greengrass component fails to deploy | Nucleus, dependency, artifact, or IAM role error | Check deployment status and component logs |
| Telemetry arrives late | Edge buffering or unstable network | Use `eventTime`/sequence and handle late arrivals |
| Log costs spike | Broad `DEBUG` logging or unlimited retention | Narrow resource-specific logging and set retention |

## 33. Production Checklist

- [ ] Every device has a unique identity and protected certificate/private key.
- [ ] Devices validate server certificates and synchronize clocks.
- [ ] Certificates have rotation, revocation, and expiration monitoring processes.
- [ ] Fleet Provisioning templates and claim policies have minimal scope.
- [ ] IoT policies restrict client IDs, publish topics, subscribe filters, and receive topics.
- [ ] Thing Registry and Thing Groups reflect site, model, and environment.
- [ ] Topic conventions and telemetry schemas are versioned.
- [ ] QoS 0/1 is chosen by criticality; consumers handle duplicates.
- [ ] Shadow desired/reported states have explicit owners and update permissions.
- [ ] Rule SQL filters early and Rule Actions use least-privilege IAM roles.
- [ ] Error actions and replay mechanisms are configured for critical flows.
- [ ] Backends include buffering/queues sized for throughput and bursts.
- [ ] S3, Kinesis, Lambda, DynamoDB, SiteWise, or OpenSearch is matched to the use case.
- [ ] CloudWatch metrics feature dashboards and alarms for connections, rules, jobs, and backends.
- [ ] CloudWatch IoT V2 logging has appropriate log levels and retention.
- [ ] Device Defender Audit is scheduled; Detect availability is verified for the account.
- [ ] Greengrass offline edge behavior has been tested.
- [ ] OTA Jobs define canary rollouts, timeouts, abort criteria, and rollback plans.
- [ ] Telemetry data has proper encryption, retention, and access controls.
- [ ] Certificate compromise, network outages, duplicate messages, and backend failures are tested.
- [ ] Costs across messaging, rule actions, logs, storage, and downstream services are monitored.

## 34. Key Takeaways

A secure IoT system begins with unique per-device identities, X.509 mutual TLS, server certificate verification, and least-privilege IoT policies. Fleet Provisioning automates onboarding; Device Shadows synchronize desired/reported state; MQTT provides publish/subscribe with QoS 0 and 1; Jobs manages updates and remote operations.

Rules Engine routes telemetry to AWS backends such as S3, Kinesis, Firehose, Lambda, DynamoDB, SQS/SNS, OpenSearch, CloudWatch, and IoT SiteWise. Greengrass brings processing to the edge to reduce latency and sustain local operations during network disruptions.

CloudWatch metrics and V2 logs provide service observability; telemetry and device-side logs require separate storage and monitoring pipelines. Device Defender Audit remains available, while Detect is closed to new customers. Production designs must combine IAM, KMS, certificate lifecycle management, policy scoping, fleet rollouts, error handling, retention, and cost monitoring to control risks from device to backend.

## References

- [AWS IoT Core Security Best Practices](https://docs.aws.amazon.com/iot/latest/developerguide/security-best-practices.html)
- [AWS IoT Device Advisor](https://docs.aws.amazon.com/iot/latest/developerguide/device-advisor.html)
- [AWS IoT Device Advisor Test Cases](https://docs.aws.amazon.com/iot/latest/developerguide/device-advisor-tests.html)
- [Authentication and Authorization for AWS IoT](https://docs.aws.amazon.com/iot/latest/developerguide/iot-authentication.html)
- [AWS IoT Policies](https://docs.aws.amazon.com/iot/latest/developerguide/iot-policies.html)
- [AWS IoT Policy Variables](https://docs.aws.amazon.com/iot/latest/developerguide/iot-policy-variables.html)
- [Registering a Client Certificate](https://docs.aws.amazon.com/iot/latest/developerguide/register-CA-cert.html)
- [Fleet Provisioning](https://docs.aws.amazon.com/iot/latest/developerguide/iot-provision.html)
- [Provisioning Templates](https://docs.aws.amazon.com/iot/latest/developerguide/provision-template.html)
- [Fleet Provisioning without Device Certificates](https://docs.aws.amazon.com/iot/latest/developerguide/provision-wo-cert.html)
- [MQTT Protocol and QoS](https://docs.aws.amazon.com/iot/latest/developerguide/mqtt.html)
- [AWS IoT Core Endpoints and Quotas](https://docs.aws.amazon.com/general/latest/gr/iot-core.html)
- [Device Shadow Service](https://docs.aws.amazon.com/iot/latest/developerguide/iot-device-shadows.html)
- [Device Shadow Documents](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html)
- [Device Shadow MQTT Topics](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-mqtt.html)
- [Rules for AWS IoT](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html)
- [AWS IoT Rule Actions](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rule-actions.html)
- [AWS IoT Jobs](https://docs.aws.amazon.com/iot/latest/developerguide/iot-jobs.html)
- [AWS IoT Jobs Key Concepts](https://docs.aws.amazon.com/iot/latest/developerguide/key-concepts-jobs.html)
- [AWS IoT Greengrass V2 Developer Guide](https://docs.aws.amazon.com/greengrass/v2/developerguide/what-is-iot-greengrass.html)
- [AWS IoT Greengrass Components](https://docs.aws.amazon.com/greengrass/v2/developerguide/manage-components.html)
- [AWS IoT Metrics and Dimensions](https://docs.aws.amazon.com/iot/latest/developerguide/metrics_dimensions.html)
- [Configure AWS IoT V2 Logging](https://docs.aws.amazon.com/iot/latest/developerguide/configure-logging.html)
- [Security Monitoring for IoT Fleets](https://docs.aws.amazon.com/iot/latest/developerguide/security-monitoring.html)
- [AWS IoT Device Defender Audit](https://docs.aws.amazon.com/iot-device-defender/latest/devguide/device-defender-audit.html)
- [AWS IoT Device Defender Detect Availability](https://docs.aws.amazon.com/iot-device-defender/latest/devguide/device-defender-detect.html)
- [AWS IoT Device Defender Detect Metrics](https://docs.aws.amazon.com/iot-device-defender/latest/devguide/detect-concepts.html)
- [AWS IoT Device Management Fleet Indexing](https://docs.aws.amazon.com/iot/latest/developerguide/iot-indexing.html)
