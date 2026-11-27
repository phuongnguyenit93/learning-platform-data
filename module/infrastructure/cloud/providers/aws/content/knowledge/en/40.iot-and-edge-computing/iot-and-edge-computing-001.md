# AWS IoT Core and Device Connectivity Architecture

An IoT system typically has hundreds to millions of devices in factories, retail stores, vehicles, buildings, or out in the field. Each device needs to send telemetry, receive commands, update configurations, and maintain its own identity. Connectivity must work over unstable networks, devices have constrained resources, and operations teams need to manage the device lifecycle over many years. If every application builds its own message broker, authentication, and device management mechanisms from scratch, operational costs and security risks escalate rapidly.

AWS IoT Core provides a cloud platform to connect devices with applications and AWS services. The service includes a device gateway to accept secure connections, a message broker for publish/subscribe, a rules engine to route data, Device Shadow to synchronize state, and fleet management capabilities. Devices can use MQTT, MQTT over WebSocket Secure (WSS), or HTTPS depending on the appropriate communication pattern and authentication mechanism.

A complete IoT architecture must also address device registration, certificate issuance and revocation, per-device permission scoping, disconnect handling, firmware management, telemetry storage, and fleet health monitoring. For edge processing needs, AWS IoT Greengrass adds a runtime to run components, filter data, and process locally on a gateway or edge device. AWS IoT Core and Greengrass serve two complementary parts of the same system: connectivity and management in the cloud, along with processing where the data is generated.

This lesson falls within the CLOUD_PROVIDERS_AWS scope: exploring AWS services and selecting architectures that are secure, observable, resilient, and cost-controlled. The focus is on designing device connectivity with AWS IoT Core, organizing identities and topics, routing telemetry, synchronizing state, managing fleets, and combining edge computing when needed.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the role of AWS IoT Core and its components: device gateway, message broker, rules engine, registry, and Device Shadow.
- Distinguish between Thing Registry, X.509 certificates, AWS IoT policies, and IAM policies.
- Choose MQTT, MQTT over WSS, or HTTPS based on device communication needs.
- Design endpoints, TLS, ports, SNI, and device authentication workflows.
- Organize MQTT topics, QoS, persistent sessions, retained messages, and Last Will and Testament.
- Provision devices using an initial registration workflow or Fleet Provisioning.
- Use the Rules Engine to filter, transform, and route telemetry to AWS services.
- Use Device Shadow to synchronize desired state and reported state when devices go online/offline.
- Manage firmware and remote tasks with AWS IoT Jobs.
- Combine AWS IoT Greengrass for local processing and operation during cloud disconnects.
- Protect the fleet with certificate lifecycle management, least privilege, logging, and Device Defender.
- Estimate costs and build operational procedures for an IoT system.

## 2. What Is AWS IoT Core?

### 2.1. Device Connectivity Platform

AWS IoT Core is a managed service that enables devices and applications to communicate securely with the AWS Cloud. Devices can send data to the cloud, receive messages from applications or other devices, and interact with AWS services through the rules engine and APIs.

Key capabilities:

- Connect devices via MQTT, MQTT over WSS, or HTTPS using supported authentication mechanisms.
- Authenticate devices using X.509 client certificates, custom authorizers, or other supported methods.
- Authorize publish, subscribe, receive, and connect operations with AWS IoT Core policies.
- Manage Thing Registry, Thing Groups, and device metadata.
- Store device state with Device Shadow.
- Route messages to S3, Lambda, SQS, SNS, Kinesis, DynamoDB, OpenSearch, CloudWatch, and other supported targets.
- Provision devices at scale with Fleet Provisioning.
- Manage firmware and remote operations with AWS IoT Jobs.
- Search and aggregate fleet information with Fleet Indexing.
- Protect the fleet with AWS IoT Device Defender.

AWS IoT Core manages connectivity and the message broker. The service does not replace firmware, operating systems, control applications, factory network design, or downstream analytics storage systems. Those components must be built or selected as separate services.

### 2.2. Components of AWS IoT Core

| Component | Role |
|---|---|
| Device Gateway | Accepts secure connections from devices |
| Message Broker | Receives publishes and distributes messages to subscribers |
| Rules Engine | Filters, transforms, and routes messages to other services |
| Thing Registry | Stores logical identity, type, and attributes of devices |
| Device Shadow | Stores desired/reported state to synchronize when devices are offline |
| Device Management | Provisioning, Jobs, Fleet Indexing, and fleet management |
| Device Defender | Audits configurations and detects anomalous fleet behavior |

### 2.3. Control Plane and Data Plane

The control plane manages resources and configurations such as Things, Thing Groups, certificates, policies, rules, jobs, and provisioning templates. These operations are typically called via the AWS Console, AWS CLI, SDKs, or APIs with IAM permissions.

The data plane handles device communication, such as MQTT publish/subscribe, Device Shadow, and certain device-facing APIs. Devices typically authenticate with X.509 certificates and are authorized via AWS IoT Core policies.

Separating these two layers helps design permissions properly:

- Operators need IAM permissions to create, update, or delete IoT resources.
- Devices need certificates and IoT policies to connect, publish, or subscribe.
- Backend services can use IAM roles to call AWS APIs or communicate with the IoT data plane via supported mechanisms.

IAM policies and AWS IoT Core policies are two different types of policies. Do not attach an IAM policy to a certificate the way you grant permissions to a role; a device's certificate is associated with an IoT policy.

## 3. Device Connectivity Architecture

### 3.1. General Data Flow

A common IoT architecture follows these steps:

1. The device boots up and reads the certificate/private key protected inside the device.
2. The device connects to the AWS IoT Core endpoint for the account and Region.
3. Device Gateway authenticates the connection and checks permissions against the IoT policy.
4. The device publishes telemetry to an MQTT topic.
5. Message Broker distributes the message to subscribers and the Rules Engine.
6. Rules Engine filters or transforms the message and sends it to storage/processing services.
7. Backend applications query the data, display dashboards, or issue commands.
8. Commands can be sent over an MQTT topic or by updating a Device Shadow.
9. The device receives the command, executes it, and publishes its new state.

~~~mermaid
flowchart LR
    D[IoT device] -->|MQTT / TLS| G[Device Gateway]
    G --> B[Message Broker]
    B --> R[Rules Engine]
    B <--> S[Device Shadow]
    R --> K[Kinesis / Firehose]
    R --> L[Lambda]
    R --> Q[SQS / SNS]
    K --> T[S3 data lake]
    L --> DB[DynamoDB / application API]
    APP[Web / mobile / backend] --> S
    APP --> B
    M[Thing Registry / IoT policies] -. identity and authorization .-> G
    JOB[AWS IoT Jobs] --> B
~~~

The diagram shows the logical flows. In real-world deployments, the Rules Engine can have multiple rules, targets can reside across multiple accounts or VPCs, and applications can use APIs instead of subscribing directly.

### 3.2. Device Gateway

Device Gateway is the entry point for devices connecting to AWS IoT Core. The gateway supports the protocols published by the service, handles secure connections, and authenticates devices. Each account in each Region has dedicated IoT endpoints for data plane, credential provider, or Jobs purposes.

Devices should store the endpoint hostname once provisioned. You can retrieve the endpoint using the AWS CLI:

~~~bash
aws iot describe-endpoint --endpoint-type iot:Data-ATS
~~~

The result returns a hostname in the form:

~~~text
xxxxxxxxxxxxxx-ats.iot.ap-southeast-1.amazonaws.com
~~~

The ATS data endpoint uses a server certificate signed by Amazon Trust Services. An account's endpoint does not change after AWS IoT Core creates it; devices can cache the hostname and do not need to call DescribeEndpoint on every connection.

Do not hard-code another account's or another Region's endpoint into shared firmware. When deploying across multiple Regions, configure endpoints per environment and follow a tested failover strategy.

### 3.3. Message Broker

Message Broker receives messages from publishers and forwards them to subscribers based on MQTT topics or the corresponding messaging mechanism. Devices can send telemetry, state events, or receive commands without knowing the network addresses of individual consumers.

The broker decouples producers from consumers:

- Devices only need to publish to agreed-upon topics.
- Dashboards or backends subscribe to the appropriate topics.
- Rules Engine can process the same message to store or forward it.
- Multiple consumers can receive the same event according to granted permissions.

Message Broker does not inherently guarantee application-level business logic such as long-term storage, cross-service transactions, or end-to-end exactly-once processing. Consumers must design retries, deduplication, and persistence according to requirements.

### 3.4. Rules Engine

Rules Engine uses SQL-like statements to filter and transform messages by topic, then execute actions. For example, accepting only telemetry with a valid temperature field, adding metadata, or forwarding messages to S3, Kinesis Data Streams, Data Firehose, Lambda, DynamoDB, SQS, SNS, OpenSearch, CloudWatch, or AWS IoT SiteWise depending on service capabilities and Regional availability.

A simple rule:

~~~sql
SELECT
    deviceId,
    temperature,
    humidity,
    timestamp() AS receivedAt
FROM 'factory/+/+/telemetry'
WHERE temperature IS NOT NULL
~~~

The topic filter in a rule can use MQTT wildcards such as the plus sign to match a single topic level. A rule can select fields, create derived fields, and filter messages before invoking an action.

Each action typically requires an IAM role allowing AWS IoT to perform the operation on the target. If the role lacks permissions, the message can still reach the broker, but the rule action will fail. Enable appropriate logging and monitor rule errors.

### 3.5. Thing Registry

Thing Registry stores the logical representation of a device, called a Thing. A Thing has a name, type, and attributes such as model, serial number, site, firmware channel, or business unit. Thing Groups help organize a fleet by site, model, environment, or deployment group.

Thing Registry is not a standalone authentication mechanism. A Thing can be associated with an X.509 certificate or appropriate principal; the certificate authenticates the connection, while the IoT policy determines what the device is allowed to do.

Example:

| Thing | Attributes | Thing Group |
|---|---|---|
| pump-001 | model=pump-v2, site=hcm-01 | pumps-production |
| pump-002 | model=pump-v2, site=hcm-01 | pumps-production |
| meter-014 | model=meter-v1, site=dn-02 | meters-production |

Attributes help with searching and applying attribute-based policies. Do not store private keys, passwords, or secrets in Thing attributes.

## 4. Protocols and Network Connectivity

### 4.1. MQTT

MQTT is a lightweight publish/subscribe protocol suited for devices with constrained bandwidth, CPU, RAM, or power. AWS IoT Core supports MQTT 3.1.1 and MQTT 5.0 with the differences documented by AWS.

Characteristics:

- Publishers send messages to topics.
- Subscribers register topic filters to receive messages.
- The broker distributes messages based on subscriptions and authorization.
- Clients do not need to maintain direct connections with one another.
- MQTT supports QoS, retained messages, persistent sessions, and Last Will and Testament per service features.

MQTT is usually the right choice for bidirectional telemetry, device state, and commands. For large payloads or firmware files, use a separate upload/download flow instead of sending the entire payload through the message broker.

### 4.2. MQTT over WebSocket Secure

MQTT over WSS allows clients to use secure WebSockets over HTTPS/TLS. This is useful for web applications or network environments that only allow outbound HTTPS. Authentication can use AWS Signature Version 4 or another supported mechanism based on the endpoint/domain configuration.

WSS does not turn a browser into a device with its own certificate by default. Web applications typically authenticate users on the backend or use Cognito/IAM and issue appropriate connection permissions. Do not embed long-term AWS secret access keys in client-side JavaScript.

### 4.3. HTTPS

HTTPS is suitable for devices that only need to publish data or send a single request without maintaining a continuous bidirectional subscription. AWS IoT Core supports HTTPS publish using authentication mechanisms such as SigV4, X.509, or custom authentication in supported configurations.

HTTPS does not provide a bidirectional subscribe/push model like MQTT. If a device needs to receive commands continuously, MQTT or WSS is generally more suitable.

### 4.4. Protocol Comparison

| Criterion | MQTT | MQTT over WSS | HTTPS |
|---|---|---|---|
| Model | Publish/subscribe | Publish/subscribe over WebSocket | Request/response, publish |
| Long-lived connection | Yes | Yes | Not for subscription model |
| Best suited for | IoT devices, gateways | Web apps, HTTPS-preferred networks | Request-based data submission |
| Authentication | X.509 or supported mechanisms | SigV4, custom auth, or X.509 per config | SigV4, X.509, or custom auth |
| Message direction | Bidirectional via broker | Bidirectional via broker | Primarily publish to IoT Core |

Choose the protocol based on device capabilities, command-receiving requirements, firewalls, certificate management, and connection costs. There is no need to keep an MQTT connection open continuously if a device only sends a small batch once a day.

### 4.5. TLS, SNI, and ALPN

AWS IoT Core uses TLS 1.2 and TLS 1.3 to protect connections. Devices must verify the server certificate and hostname to avoid connecting to spoofed servers. AWS IoT requires SNI for connections depending on the endpoint/domain configuration, including features such as custom domains and VPC endpoints.

For the default endpoint:

| Protocol | Authentication | Common Port | Notes |
|---|---|---:|---|
| MQTT | X.509 client certificate | 8883 | MQTT over TLS |
| MQTT | X.509 client certificate | 443 | Requires ALPN x-amzn-mqtt-ca |
| MQTT over WSS | SigV4 or supported mechanism | 443 | Uses WebSocket Secure |
| HTTPS publish | SigV4 | 443 | HTTP API |
| HTTPS publish | X.509 client certificate | 8443 | TLS mutual authentication |
| HTTPS publish | X.509 client certificate | 443 | Requires ALPN x-amzn-http-ca |

Organizations must verify the exact combination of protocol, port, authentication, and ALPN. Opening TCP 443 does not automatically ensure every connection type works if the device lacks SNI, ALPN, or the proper certificate chain.

### 4.6. Network Design

Devices typically initiate outbound connections to the AWS IoT endpoint. Inside a factory network:

- Allow DNS resolution of the endpoint.
- Allow required outbound TCP ports for the chosen protocol.
- Synchronize time with NTP so certificate validation works properly.
- Verify that firewalls/proxies do not perform improper TLS interception.
- Ensure MTU and network paths do not cause fragmentation or timeouts.
- Implement retry with backoff to prevent massive numbers of devices from reconnecting simultaneously.
- Use Direct Connect or Site-to-Site VPN when the system requires private connectivity to AWS.

Devices do not need inbound public ports to receive MQTT messages; the established connection with the broker allows receiving data via subscriptions. If using a proxy, verify support for MQTT/WSS and certificate handling.

## 5. MQTT Topics and Message Semantics

### 5.1. Designing the Topic Namespace

Topics form the communication contract between firmware, backend, and Rules Engine. One usable structure is:

~~~text
factory/{siteId}/{deviceId}/telemetry
factory/{siteId}/{deviceId}/status
factory/{siteId}/{deviceId}/events
factory/{siteId}/{deviceId}/commands
factory/{siteId}/{deviceId}/acks
~~~

Example:

~~~text
factory/hcm-01/pump-001/telemetry
factory/hcm-01/pump-001/status
factory/hcm-01/pump-001/commands
~~~

Naming rules:

- Use consistent, structured naming.
- Avoid embedding secrets or PII in topics.
- Separate telemetry, events, commands, and acknowledgements.
- Clearly define publishers and subscribers for each topic.
- Standardize payload schema, timestamps, units, and versions.
- Have a versioning strategy when changing message structures.

### 5.2. Wildcards in MQTT Subscriptions

MQTT supports:

- Plus sign (+): matches a single topic level.
- Hash sign (#): matches multiple remaining levels and must be at the end of the topic filter.

Example:

~~~text
factory/hcm-01/+/telemetry
factory/+/+/status
factory/#
~~~

Wildcards help the backend subscribe to many devices. However, do not grant subscribe permissions for all factory topics to every device if each device should only read its own commands.

### 5.3. QoS 0 and QoS 1

AWS IoT Core supports MQTT QoS 0 and QoS 1; QoS 2 is not supported.

| QoS | Meaning | When Appropriate |
|---|---|---|
| 0 | Best-effort message delivery without QoS 1 acknowledgement | High-frequency telemetry where missing some samples is acceptable |
| 1 | At least once; publisher waits for PUBACK and may resend | Commands or events requiring confirmed delivery to the broker |

QoS 1 can produce duplicates because messages are retransmitted if acknowledgements do not arrive in time. Consumers should process idempotently using a message ID, sequence number, or event key. QoS 1 does not mean a message has been durably stored in a database or that business processing is complete.

### 5.4. Persistent Sessions

Persistent sessions retain subscriptions and certain unacknowledged QoS 1 messages while a client is offline, subject to service limits. When the device reconnects with the same session, subscriptions are restored and queued messages can be redelivered.

MQTT 3.1.1 uses the `cleanSession` flag; MQTT 5 uses Clean Start and Session Expiry Interval. Persistent sessions are useful for mobile devices or intermittent connections. However, stored messages and redelivery rates are subject to service limits; do not treat sessions as an infinite storage queue.

### 5.5. Retained Messages

A retained message stores the last message published to a topic. New subscribers can receive the latest value immediately upon subscribing. This fits configuration or current state, such as the last operational status.

Retained messages differ from persistent sessions:

- A retained message is the latest value attached to a topic.
- A persistent session holds subscription state and pending QoS 1 messages for a specific client.

Do not use retained messages for all historical telemetry. Continuous publishing overwrites previous values; historical data should be stored in a data service.

### 5.6. Last Will and Testament

Last Will and Testament (LWT) is a message that the broker publishes on behalf of a client if the connection drops unexpectedly. You can use LWT to update offline status:

~~~text
factory/hcm-01/pump-001/status
~~~

Example payload:

~~~json
{
  "connectionState": "offline",
  "reason": "unexpected_disconnect"
}
~~~

During normal connection, the device publishes an online status. LWT helps detect disconnects, but it does not replace application-layer heartbeats and health checks. Networks can suffer transient drops; the system should implement appropriate timeouts and stale states.

### 5.7. Payload Design

Telemetry payloads should include a message ID, measurement timestamp, sequence number, schema version, and units:

~~~json
{
  "schemaVersion": 1,
  "messageId": "pump-001-00004567",
  "deviceId": "pump-001",
  "measuredAt": "2026-11-20T10:15:30Z",
  "sequence": 4567,
  "temperatureC": 68.4,
  "vibrationMmPerS": 2.1
}
~~~

The measurement timestamp at the device and the receipt timestamp in the cloud have different meanings. If the device clock is unreliable, Rules Engine or consumers can add `receivedAt` to aid reconciliation. Never rely solely on device timestamps for event ordering if clocks can drift.

## 6. Device Identity and Provisioning

### 6.1. Thing, Certificate, and IoT Policy

A well-managed device typically has:

- A Thing representing the device in the registry.
- An X.509 certificate to authenticate the device.
- A corresponding private key kept securely on the device.
- An AWS IoT Core policy restricting allowed operations.
- An association between the certificate/principal and the Thing.

The certificate proves identity during TLS mutual authentication. The IoT policy determines which client ID the certificate may connect with, which topics it may publish to, which topic filters it may subscribe to, and which messages it may receive.

A created certificate without an attached policy can authenticate, but it lacks permissions to perform required IoT operations. Similarly, if a policy exists but the certificate is invalid or inactive, the device cannot connect.

### 6.2. X.509 Mutual TLS

In mutual TLS:

1. The device verifies the AWS IoT server certificate.
2. The device presents its own client certificate.
3. AWS IoT validates the certificate, status, and trust chain.
4. AWS IoT evaluates the policy attached to the certificate/principal.
5. The connection is allowed or rejected.

Each device should have its own certificate. Do not share a single certificate and private key across an entire fleet, because one compromised device exposes the identity of all devices.

Private keys should be protected by a secure element, TPM, or equivalent hardware mechanism when supported by the device. If stored in the filesystem, use least-privilege access permissions, appropriate encryption, and procedures to protect boot/debug interfaces.

### 6.3. AWS IoT Core Policy

An IoT policy restricts permissions on IoT resources such as clients, topics, topic filters, and shadows. An example policy for device pump-001:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-southeast-1:123456789012:client/pump-001"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": "arn:aws:iot:ap-southeast-1:123456789012:topic/factory/hcm-01/pump-001/telemetry"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Subscribe",
      "Resource": "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/factory/hcm-01/pump-001/commands"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Receive",
      "Resource": "arn:aws:iot:ap-southeast-1:123456789012:topic/factory/hcm-01/pump-001/commands"
    }
  ]
}
~~~

This is an illustrative example; account ID, Region, topic, and resource ARNs must be replaced with your environment values. Production policies should scope each device to its own topics and grant only the required actions.

MQTT subscriptions use plus and hash wildcards, whereas wildcards in AWS IoT policy resource ARNs follow AWS policy rules. Do not assume that MQTT wildcard characters work the same way inside policy resource strings.

### 6.4. Thing Policy Variables

AWS IoT Core supports policy variables such as ThingName, ThingTypeName, and Thing attributes in supported scenarios. This allows a single policy template to cover many devices rather than creating a separate policy for every Thing.

To use thing policy variables properly:

- The certificate/principal must be attached to the Thing according to the chosen model.
- The MQTT client ID must match the Thing name when using Thing-connection-dependent variables.
- The topic namespace must follow consistent rules.
- Test both valid devices and devices attempting to access another Thing/topic.

Do not use overly broad wildcard policies just to reduce policy count. You can standardize policy templates while still scoping each device via ThingName or CertificateId.

### 6.5. Small-Scale Device Onboarding Workflow

For a small number of devices or a pilot:

1. Create the Thing in the registry.
2. Create or register an X.509 certificate.
3. Download the certificate, private key, and required CA certificate through a secure workflow.
4. Attach the certificate to the Thing.
5. Attach the IoT policy to the certificate.
6. Store the private key on the device.
7. Configure endpoint, client ID, and topics.
8. Verify TLS handshake, connect, publish, and subscribe.
9. Record serial number, Thing name, and certificate ID in inventory.

Private keys must only be downloaded and stored via secure workflows; never put them into tickets, emails, or repositories. If a private key is compromised, deactivate/revoke the certificate and issue new credentials.

### 6.6. Fleet Provisioning

At large device scale, manually creating Things and certificates is impractical. AWS IoT Core Fleet Provisioning supports automated provisioning using provisioning templates.

Common patterns:

- **Provisioning by claim:** the device carries a temporary claim certificate to initiate the registration flow and receive its unique certificate.
- **Provisioning by trusted user:** a trusted application or workflow generates a provisioning claim and passes it to the device over a secure channel.
- **Just-in-time provisioning/registration:** uses certificates signed by a registered CA or corresponding provisioning mechanism to automatically create resources when a device connects for the first time.

A provisioning template describes the resources to create, such as Things, certificates, and policies. Templates can use parameters to apply across many devices.

High-level provisioning-by-claim flow:

1. The device connects using a protected claim certificate.
2. The device sends a provisioning request with permitted identifying information.
3. AWS IoT validates the provisioning template and claim policy.
4. The service creates a unique certificate and Thing.
5. The new certificate is associated with the Thing and policy.
6. The device stores its unique credentials and switches to normal connectivity.
7. The claim certificate is governed by policy to prevent unintended reuse.

A claim certificate is a bootstrap credential with special privileges. Restrict allowed operations and scope, protect the private key, monitor usage counts, and disable it if abuse is suspected. Never give a claim certificate broad publish/subscribe permissions on production topics.

## 7. Device Shadow and State Synchronization

### 7.1. Why Do We Need Device Shadow?

Devices can go offline due to network loss, battery depletion, maintenance, or movement. Applications still need to know the latest state and set desired configurations for the device to apply when it reconnects.

Device Shadow stores device state in AWS IoT Core. Applications can update the desired state even while the device is offline; when the device connects and syncs, it reads the changes and updates the reported state.

Shadow is not a full replica of a telemetry database. It is meant for storing current state or configuration, not full measurement history.

### 7.2. Desired, Reported, and Delta

A Shadow document has three key sections:

- desired: the state that applications want the device to reach.
- reported: the state that the device reports it currently has.
- delta: the difference between desired and reported calculated by AWS IoT.

Example:

~~~json
{
  "state": {
    "desired": {
      "samplingIntervalSeconds": 30,
      "operatingMode": "eco"
    },
    "reported": {
      "samplingIntervalSeconds": 60,
      "operatingMode": "normal"
    }
  }
}
~~~

The device receives the delta, applies the configuration if valid, and publishes the new reported state. Once desired and reported match, the corresponding delta disappears.

### 7.3. Shadow MQTT Topics

Shadow has dedicated topics for operations like get, update, delete, and accepted/rejected/delta responses. Example with a named shadow:

~~~text
$aws/things/pump-001/shadow/name/config/update
$aws/things/pump-001/shadow/name/config/update/delta
$aws/things/pump-001/shadow/name/config/update/accepted
$aws/things/pump-001/shadow/name/config/update/rejected
~~~

Named shadows allow separating multiple state groups, such as config, maintenance, or diagnostics. A Thing can only have one classic unnamed shadow; if you anticipate needing multiple independent state groups, consider named shadows from the start.

### 7.4. Versioning and Concurrent Updates

Shadow documents have a version that increments with each update. Clients can use the version to avoid overwriting a newer state with stale data. If an update specifies an outdated version, the service can reject it so the client re-reads and syncs.

Delta messages may arrive out of the order expected by the application. Devices should track versions and ignore messages older than the already processed state.

### 7.5. Shadow Does Not Replace Command Workflows

Shadow fits persistent desired state, such as sampling configurations or operating modes. For commands requiring execution confirmation, progress tracking, retries, timeouts, or fleet-wide rollouts, use MQTT command patterns or AWS IoT Jobs.

Example:

| Need | Suitable Approach |
|---|---|
| Set a new sampling interval | Desired state in Shadow |
| Report current temperature and firmware | Reported state/telemetry |
| Run a fleet-wide firmware update | AWS IoT Jobs |
| Send an urgent command needing a response | Command topic with correlation ID and acknowledgement |

## 8. Rules Engine and AWS Service Integrations

### 8.1. Filtering and Routing Telemetry

Rules Engine allows using SQL to select only necessary messages and invoke actions. For example:

- Store telemetry in S3 via Firehose.
- Send events needing fast processing to Lambda.
- Forward messages to SQS for asynchronous consumer processing.
- Record metrics in CloudWatch.
- Send time-series data to an appropriate analytics service.
- Write device data to DynamoDB.

A good design avoids sending every message to every service. Filtering at the Rules Engine reduces downstream load and costs.

### 8.2. Data Storage Rule Example

Suppose devices publish telemetry to `factory/{site}/{device}/telemetry`. A rule can select the data:

~~~sql
SELECT
    deviceId,
    measuredAt,
    temperatureC,
    vibrationMmPerS
FROM 'factory/+/+/telemetry'
WHERE temperatureC >= -40
  AND temperatureC <= 150
~~~

The rule can forward filtered messages to Data Firehose to buffer and write to S3. Firehose can partition prefixes by date or site depending on delivery stream configuration. Data is then processed with Glue or queried with Athena.

### 8.3. IAM Role for Rule Actions

Rules Engine needs permissions to perform actions on target services. Typically, you configure an IAM role assumed by AWS IoT with least-privilege permissions like `PutRecord` to a Firehose stream or `PutObject` on a specified bucket/prefix.

Do not grant `*` permissions to a shared role across all rules. Separate roles per action or rule group to minimize blast radius. If a rule invokes Lambda, restrict permission to that exact function; if writing to S3, restrict bucket and prefix.

### 8.4. Rule Error Handling

A rule may trigger, yet its action fails due to missing IAM permissions, incorrect ARNs, nonexistent resources, or target service errors. You should:

- Enable AWS IoT logging at an appropriate level.
- Monitor error metrics and CloudWatch Logs.
- Use an error action or dead-letter pattern where the workflow supports it.
- Design idempotent consumers.
- Track messages received versus messages successfully written at the destination.
- Have a data replay procedure for downstream failures.

Do not assume the rule engine replaces a durable queue for every workflow. For critical processing, route through SQS/Kinesis or a storage layer with proper replay capability.

## 9. Fleet, Firmware, and Device Management

### 9.1. AWS IoT Jobs

AWS IoT Jobs enables sending and tracking remote operations for a Thing or group of devices. A job document can describe:

- Firmware package URL or location.
- Software version to install.
- Upgrade or configuration commands.
- Parameters and execution steps.
- Retry, timeout, or rollout rules.

Devices receive job notifications over MQTT or poll the Jobs API, download the job document, perform the task, and update execution status such as `IN_PROGRESS`, `SUCCEEDED`, `FAILED`, or other appropriate statuses.

### 9.2. OTA Firmware Update

A secure OTA workflow:

1. Build firmware and verify signature/hash.
2. Upload the package to a protected storage location.
3. Create a job document with version, URL, and verification metadata.
4. Select a Thing Group or target device list.
5. Roll out in batches/canary stages.
6. Device downloads the package and verifies the signature before installing.
7. Device reboots, performs health checks, and reports the result.
8. Monitor success rates and halt the rollout if errors exceed a threshold.

Firmware should include rollback or recovery partition mechanisms if hardware supports it. Do not treat completing a file download as a successful upgrade; verify boot and post-update health checks.

### 9.3. Fleet Indexing

Fleet Indexing allows searching and aggregating device information based on registry data, Device Shadow, connectivity, package catalog, and Device Defender violations in supported configurations.

Example fleet queries:

- Find devices by model or site.
- Find currently offline devices.
- Find devices running outdated firmware versions.
- Aggregate device counts by status or violation.
- Create dynamic thing groups from queries.

Fleet Indexing is valuable for operations and troubleshooting. Enable only the index sources you need, as indexing incurs extra costs and requires query access controls.

### 9.4. AWS IoT Device Defender

Device Defender helps protect the fleet with:

- **Audit:** checks configurations and security posture of IoT resources, certificates, policies, and supported components.
- **Detect:** detects anomalous behavior based on device-side or cloud-side metrics.
- **Mitigation actions:** executes configured responses, such as updating policies, quarantining certificates, or placing devices into remediation groups per workflow.

Device Defender does not replace secure boot, patching, firmware signing, or hardware protection. It is a monitoring and detection layer that helps operations teams identify weak configurations and anomalous behavior.

### 9.5. Device Advisor

AWS IoT Device Advisor provides test suites to verify that devices are compatible with AWS IoT Core against supported connectivity and protocol criteria. It should be used during firmware development and device certification before moving to a production fleet.

Early testing catches issues with TLS, certificates, MQTT behavior, reconnects, and protocol handling before mass production.

## 10. AWS IoT Greengrass and Edge Computing

### 10.1. When Is Edge Processing Needed?

Not all data should be sent to the cloud. Edge computing is appropriate when:

- Devices require low-latency responses or local control.
- Internet connectivity is unreliable.
- Data volume is large and only aggregated summaries need to be sent.
- There are requirements to keep data on-site or reduce bandwidth.
- Inference needs to run close to cameras, machinery, or sensors.

For example, a factory gateway can read data from PLCs and sensors, compute rolling averages, detect threshold anomalies, and forward only important events to the cloud.

### 10.2. AWS IoT Greengrass

AWS IoT Greengrass is an edge runtime that lets you run components on local core devices. Components can be native processes, containers, Lambda functions, or supported runtimes. Greengrass manages deployment, configuration, and lifecycle of edge software from the cloud.

Common capabilities:

- Local MQTT message processing.
- Data filtering, aggregation, and buffering.
- Executing business logic when cloud connectivity is interrupted.
- Running model inference at the edge using an appropriate architecture.
- Managing component deployments and versions.
- Connecting local client devices and synchronizing data/shadows with AWS IoT Core.

A Greengrass core device must be provisioned and connected to AWS IoT. Client devices can connect to the core via MQTT to send data or interact with local components.

### 10.3. How Do AWS IoT Core and Greengrass Differ?

| Criterion | AWS IoT Core | AWS IoT Greengrass |
|---|---|---|
| Primary location | AWS Cloud | Gateway/edge device |
| Role | Connectivity, broker, registry, rules, shadow, fleet management | Local runtime and processing |
| Communication | Devices with cloud and cloud services | Edge components and local client devices |
| Offline | Supports sessions/shadows per service mechanisms | Can continue local processing per components and design |
| Deployment | Managed service | Install runtime and deploy components on core devices |

Both services are commonly used together. IoT Core manages cloud connectivity and the fleet; Greengrass executes logic near the data source.

### 10.4. Edge-Gateway Architecture

~~~mermaid
flowchart TB
    subgraph EDGE["Factory / edge site"]
        S1[Sensors and PLC]
        S2[Camera / measurement device]
        G[Greengrass Core]
        C[Local components]
        Q[Local buffer]
        S1 --> G
        S2 --> G
        G --> C
        C --> Q
    end
    Q -->|MQTT/TLS when online| I[AWS IoT Core]
    I --> R[Rules Engine]
    R --> D[S3 / Kinesis / Lambda]
    I <--> SH[Device Shadow]
    I --> J[IoT Jobs deployment]
    J --> G
~~~

When Internet access drops, the edge application must continue acting safely based on local data and cached policies. When connectivity returns, data is synchronized in order within storage limits. Never depend on a cloud round-trip for an industrial control loop requiring ultra-low latency or functional safety.

## 11. Connection and Device Security

### 11.1. Server and Client Authentication

Devices must verify the AWS IoT server certificate against a trusted CA, while AWS IoT authenticates the device's client certificate. Verifying hostname, certificate validity, and system clock is essential.

Measures:

- Use a unique certificate per device.
- Protect private keys in hardware when available.
- Validate the certificate chain and hostname.
- Use TLS 1.2 or 1.3 as supported.
- Configure SNI and ALPN when connecting over port 443.
- Never disable certificate validation to work around connection errors.

### 11.2. Certificate Lifecycle

Certificates follow a lifecycle:

1. Generate or issue from a trusted CA.
2. Register with AWS IoT.
3. Attach Thing and IoT policy.
4. Distribute securely to the device.
5. Monitor status and expiration.
6. Rotate before expiration or when compromise is suspected.
7. Deactivate/revoke the old certificate.
8. Verify the device has transitioned to the new certificate.

A compromised certificate must be disabled promptly. Maintain an inventory mapping certificate IDs to serial numbers, owners, and device locations to avoid revoking the wrong one or missing any.

### 11.3. Least Privilege for IoT Policies

Each device should only:

- Connect using its own client ID.
- Publish to its own telemetry/status topics.
- Subscribe to required command or shadow topics.
- Receive messages on granted topics.
- Access exact Job/Shadow resources if required by the workflow.

Do not allow every device to subscribe to all topics or publish arbitrary commands. Separate device, backend, operator, and provisioning role permissions.

### 11.4. Credentials and Secrets

Do not embed long-term IAM access keys in firmware. If a device needs to access other AWS services, evaluate IoT Credential Provider to exchange an X.509 identity for temporary credentials based on a configured role alias and policy.

Temporary credentials must be scoped per device and allow only required resources. Never grant account-admin roles to devices.

### 11.5. Anti-Spoofing and Replay Protection

Beyond TLS, payloads should include:

- A unique message ID.
- A per-device monotonically increasing sequence number.
- Timestamp and clock information.
- Schema version.
- Application-level signatures if end-to-end integrity beyond the TLS session is required.

Consumers can detect duplicates or stale messages using sequence numbers and event IDs. For critical commands, include a command ID, expiry, acknowledgement, and execution status.

### 11.6. Logging and Auditing

AWS IoT logging can record broker events, connections, and errors according to configured log levels. CloudTrail records control-plane activity such as Thing creation, certificate changes, policy edits, or rule updates. Device Defender helps audit configurations and detect anomalous behavior.

Logs should be protected in a dedicated account/bucket with appropriate retention and access controls. Avoid logging private keys, secrets, or payloads containing PII or sensitive production data without a clear purpose and controls.

## 12. Reliability and Disconnect Handling

### 12.1. Reconnect Strategy

Mobile or edge devices frequently experience intermittent networks. Use exponential backoff with jitter to prevent the entire fleet from reconnecting simultaneously after a network or broker outage. Set a maximum retry interval and reset backoff once the connection stabilizes.

### 12.2. Store-and-Forward

If data loss is unacceptable, the device or edge gateway needs a local buffer. During a disconnect:

1. Write events to a durable queue/buffer.
2. Record sequence numbers and timestamps.
3. Enforce capacity and retention limits.
4. When connectivity returns, replay in batches with rate limits.
5. Consumers deduplicate using message IDs.
6. Confirm data has been processed before deleting from the buffer.

Do not rely on MQTT QoS 1 as an infinite storage mechanism. QoS 1 handles delivery to the broker under protocol semantics, whereas guaranteed zero-loss data requires persistence and replay logic on the device or downstream.

### 12.3. Persistent Sessions and Shadow

Persistent sessions can retain subscriptions and pending QoS 1 messages within service limits. Shadow maintains desired/reported state for devices to synchronize after reconnecting. The two mechanisms solve different problems:

- Sessions maintain messaging state.
- Shadows synchronize application state.

If a device stays offline longer than the session expiry or exceeds message queue limits, messages can expire or be dropped. For critical commands, use Jobs or workflows with explicit state and timeouts.

### 12.4. Backpressure and Rate Control

When thousands of devices flush telemetry simultaneously after an outage, downstream services can become overwhelmed. Design for:

- Randomized reconnect and publish schedules.
- Appropriate data batching.
- Rate-limited buffer flushing.
- SQS/Kinesis as downstream buffering layers when needed.
- Retries and DLQs.
- Monitoring throttling and queue depth.
- Prioritizing command/control traffic over non-critical telemetry.

### 12.5. Multi-Region

If DR or geographic fleet distribution is needed, an IoT architecture can be deployed across multiple Regions. However, Thing Registry, certificates, policies, rules, shadows, and Jobs must be managed under a multi-Region design; do not assume resources automatically replicate completely.

Define:

- Primary and secondary Regions.
- Endpoint and DNS strategy.
- Synchronization method for registry/certificates/policies.
- Synchronization method for data and shadow state.
- Procedure to switch devices to the backup endpoint.
- Ways to avoid split-brain if both Regions receive commands.
- RPO/RTO and failover testing.

## 13. Fleet Monitoring and Operations

### 13.1. CloudWatch Metrics

Monitor relevant metrics:

- Number of active connections.
- Connect/disconnect events and authentication errors.
- Number of published/received messages.
- Message throttling or quota-related errors.
- Rules Engine invocations and action errors.
- Device Shadow requests and errors.
- Jobs execution statuses.
- Fleet indexing and Device Defender findings.

Metric names and dimensions may vary by component and Region. Select metrics aligned with operational goals rather than enabling verbose logging/metrics everywhere.

### 13.2. CloudWatch Logs

AWS IoT logging can be enabled to investigate:

- Devices failing to connect.
- Rejected certificates or policies.
- Unauthorized topic publish/subscribe attempts.
- Failed rule actions.
- Abnormal message broker behavior.

Verbose logging across an entire fleet can generate significant costs and capture sensitive data. Use sampling, per-device-group log levels, and retention limits.

### 13.3. Fleet Health Dashboard

A fleet dashboard can display:

| Metric | Meaning |
|---|---|
| Online devices | Number of currently connected devices |
| Offline duration | Time since a device was last online |
| Firmware distribution | Distribution of firmware versions |
| Telemetry freshness | Age of the latest received data |
| Job success rate | Completion rate of OTA/configuration jobs |
| Certificate expiry | Devices with certificates nearing expiration |
| Defender violations | Number of devices with findings |
| Rule delivery errors | Message routing failures |

Combine Fleet Indexing, CloudWatch, Device Defender, and business data to identify which devices require maintenance.

### 13.4. Incident Procedure

When a large portion of the fleet disconnects:

1. Check AWS Health Dashboard and CloudWatch metrics.
2. Distinguish between cloud, DNS, ISP, firewall, or on-site power outages.
3. Inspect Connect/Disconnect logs and certificate errors.
4. Check endpoint, TLS, SNI, ALPN, and device clocks.
5. Assess reconnect storms and throttling.
6. Throttle reconnect or publish rates if downstream services are overloaded.
7. Recover site-by-site or group-by-group and verify telemetry.
8. Document root cause, affected devices, and preventive measures.

## 14. AWS IoT Core Pricing

### 14.1. Billing Components

AWS IoT Core charges based on usage components, typically including:

- Connectivity: device connection duration.
- Messaging: number and size of messages as measured by the service.
- Device Shadow and registry operations.
- Rules Engine: number of rules triggered and actions executed.
- Management/observability features or related services per pricing tables.

Beyond IoT Core, total costs may include Lambda, S3, Kinesis, Firehose, DynamoDB, CloudWatch, KMS, Greengrass, networking, and downstream storage. Prices vary by Region and workload type; always consult the current pricing page or AWS Pricing Calculator.

### 14.2. Cost Drivers

- Maintaining persistent connections for devices that do not need to stay online.
- Publishing messages too frequently or with oversized payloads.
- Sending duplicate copies of the same telemetry across multiple topics.
- Calling Device Shadow updates continuously even when state has not changed.
- Triggering too many rules/actions per message.
- Enabling verbose logging across the entire fleet.
- Retaining historical data too long in S3 or hot databases.
- Running Greengrass/edge compute on oversized resources.

### 14.3. Cost Optimization

- Match telemetry intervals to business requirements.
- Batch multiple samples when acceptable.
- Minimize payloads and drop unnecessary fields.
- Update Shadow only when state actually changes.
- Filter messages in the Rules Engine.
- Use Firehose to buffer and write data in batches.
- Transition historical data to appropriate storage classes.
- Turn off verbose logs once investigations are complete.
- Use edge filtering to transmit only needed data.
- Track costs by site, Thing Group, and device type.

### 14.4. Estimation Example

Suppose a site has 1,000 sensors, each sending one 1 KB message per minute while maintaining a persistent connection. Daily messages:

\[
1,000 \times 60 \times 24 = 1,440,000\ \text{messages/day}
\]

Over 30 days:

\[
1,440,000 \times 30 = 43,200,000\ \text{messages/month}
\]

This represents only message volume, excluding connectivity minutes, rules, actions, Shadow, registry, downstream storage, and related services. When building an estimate, calculate each component using the Region and current unit rates.

## 15. Architecture Example: Industrial Pump Monitoring

### 15.1. Context

A factory has 500 pumps, each equipped with temperature, pressure, and vibration sensors. The system must:

- Send periodic telemetry.
- Alert when temperature or vibration exceeds thresholds.
- Allow engineers to change the sampling interval from a dashboard.
- Track online/offline status.
- Update firmware by machine group.
- Continue recording data during brief Internet outages.

### 15.2. Device and Connectivity Design

- Each pump has its own Thing and certificate.
- Client ID matches the Thing name.
- MQTT over TLS using X.509 certificates.
- Devices publish telemetry and status to dedicated topics.
- IoT policy allows publishing only the device's own telemetry/status and subscribing to required command/shadow topics.
- Site gateway runs Greengrass to buffer data and evaluate local thresholds.

### 15.3. Data Routing

- Rules Engine filters valid telemetry.
- Normal messages go to Data Firehose to store in S3 partitioned by site/date.
- Threshold-breach events route to Lambda or SQS for alert processing.
- Glue/Athena use S3 data for trend analysis and predictive maintenance.
- CloudWatch monitors connections, rule errors, and throughput.

### 15.4. Control and Management

- The dashboard updates the desired sampling interval in a named Shadow config.
- Devices receive the delta, apply the configuration, and update reported state.
- AWS IoT Jobs deploys firmware by Thing Group, starting with a canary group.
- Fleet Indexing finds offline devices or outdated firmware.
- Device Defender audits policies/certificates and detects anomalous behavior.

### 15.5. Handling Outages

When Internet connectivity drops:

- Greengrass continues reading sensors and applying local safety thresholds.
- Telemetry is persisted in a local buffer.
- The dashboard displays stale/offline status.
- When connectivity returns, the gateway sends data in rate-limited batches.
- Consumers use message IDs/sequences to deduplicate.
- Shadow synchronizes the latest desired/reported state.

Pump safety control systems must still operate locally; never rely on a round-trip to AWS IoT Core for emergency stop operations.

## 16. Common Troubleshooting

| Symptom | Possible Cause | What to Check |
|---|---|---|
| TLS handshake fails | Wrong CA, clock drift, hostname/SNI, or TLS config | Check server certificate, system time, SNI, and TLS version |
| Certificate rejected | Inactive certificate, wrong chain, or unregistered | Check certificate status and registration |
| Connects but publish is denied | IoT policy missing iot:Publish or wrong topic ARN | Check policy attached to certificate and resource ARN |
| Subscribe succeeds but no messages arrive | Missing iot:Receive, publisher on wrong topic, or no messages | Check policy, topic, and broker logs |
| Device ID conflict | Multiple clients using the same client ID | Use unique client IDs tied to each Thing |
| Connection drops repeatedly | Unstable network, keepalive, clock, or credentials | Check network, keepalive, backoff, and certificate |
| Rule does not write data | IAM role missing permissions or misconfigured action | Check rule logs, role trust, and target ARN |
| Shadow out of sync | Wrong topic, stale version, or invalid payload | Check named shadow, version, and rejected responses |
| OTA job fails | Unreachable URL, bad signature, or insufficient storage | Check job document, download, signature, and device logs |
| Fleet falsely reports offline | Thing name mismatches client ID or disconnect delay | Check association, lifecycle events, and heartbeat |
| Duplicate messages | QoS 1 retries or consumer reprocessing | Use message IDs, sequences, and idempotency |
| Sudden cost spike | Surge in messages/rules/actions/logs or reconnect storm | Analyze billing dimensions, CloudWatch, and rule metrics |

## 17. AWS IoT Core Design Checklist

### Before Deployment

1. Identify device types, firmware, OS, network, and latency requirements.
2. Choose Region and endpoints.
3. Choose MQTT, WSS, or HTTPS.
4. Design topic namespace and payload schemas.
5. Define Thing Registry, Thing Groups, and naming conventions.
6. Design certificate issuance, rotation, and revocation.
7. Write least-privilege IoT policies.
8. Select a provisioning workflow suitable for fleet scale.
9. Determine whether Shadow, Jobs, and Greengrass are required.
10. Estimate connectivity, messaging, rules, storage, and logging costs.

### During Deployment

1. Create Things, certificates, and policies.
2. Verify TLS, SNI, ALPN, and ports.
3. Test connect, publish, subscribe, and reconnect.
4. Create Rules Engine rules and IAM roles for actions.
5. Configure Shadow and test desired/reported/delta flows.
6. Set up Jobs and OTA canary rollouts.
7. Configure CloudWatch logging/metrics and CloudTrail.
8. Verify access controls and run negative tests.

### In Operations

1. Monitor online/offline counts, telemetry freshness, and message rates.
2. Track certificate expirations and policy changes.
3. Review Device Defender audit/detect findings.
4. Monitor Job success rates and firmware distribution.
5. Test outages, local buffers, and reconnects.
6. Monitor rule failures, queue depth, and downstream throttling.
7. Review costs by site, device type, and workload.
8. Test certificate rotation, decommissioning, and revocation.

## 18. Conclusion

AWS IoT Core provides a device connectivity platform via its device gateway, message broker, and Rules Engine, alongside Thing Registry, Device Shadow, and fleet management capabilities. MQTT suits lightweight publish/subscribe communication; WSS is useful for web clients or HTTPS-preferred networks; HTTPS fits devices that only publish on a request basis. TLS, X.509 certificates, and IoT policies form the authentication and authorization layer for each device.

A production IoT architecture must manage the full lifecycle: onboarding, certificates, topics, telemetry, commands, shadows, firmware, monitoring, outages, and decommissioning. Rules Engine routes data to AWS services; Jobs and Fleet Indexing support large-scale management; Device Defender adds auditing and anomaly detection. For on-site processing requirements, AWS IoT Greengrass runs local components and logic, synchronizing data with AWS IoT Core when connected.

Good designs scope permissions per Thing, use message IDs and sequence numbers to handle duplicates, buffer data when offline, and never depend on the cloud for safety-critical control loops. By combining device security, resilience, fleet observability, and cost control, AWS IoT Core serves as a solid foundation for connecting and operating devices at scale.

## 19. Official References

- [How AWS IoT Core works](https://docs.aws.amazon.com/iot/latest/developerguide/aws-iot-how-it-works.html)
- [Connect devices to AWS IoT](https://docs.aws.amazon.com/iot/latest/developerguide/iot-connect-devices.html)
- [Device communication protocols](https://docs.aws.amazon.com/iot/latest/developerguide/protocols.html)
- [MQTT in AWS IoT Core](https://docs.aws.amazon.com/iot/latest/developerguide/mqtt.html)
- [Security best practices in AWS IoT Core](https://docs.aws.amazon.com/iot/latest/developerguide/security-best-practices.html)
- [AWS IoT Core policies and authorization](https://docs.aws.amazon.com/iot/latest/developerguide/iot-authorization.html)
- [Device provisioning](https://docs.aws.amazon.com/iot/latest/developerguide/iot-provision.html)
- [AWS IoT Rules Engine](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html)
- [AWS IoT Device Shadows](https://docs.aws.amazon.com/iot/latest/developerguide/iot-device-shadows.html)
- [AWS IoT Jobs](https://docs.aws.amazon.com/iot/latest/developerguide/iot-jobs.html)
- [AWS IoT Greengrass – How it works](https://docs.aws.amazon.com/greengrass/v2/developerguide/how-it-works.html)
- [AWS IoT Core pricing](https://aws.amazon.com/iot-core/pricing/)
