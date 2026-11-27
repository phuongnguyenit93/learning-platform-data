# Routing Telemetry from IoT Hub to Processing Services

A factory deploys thousands of sensors measuring temperature, vibration, and electrical power. Each device sends data every few seconds to **Azure IoT Hub**. Operations wants instant alerts when temperature crosses thresholds; the analytics team wants raw telemetry archived for investigation and model training; a reporting system needs minute-by-minute averages. If every message had to pass through a custom-written Java application just to be fanned out to downstream systems, that application could become a bottleneck forced to handle complex retry, connection, and scaling logic.

**Azure IoT Hub message routing** lets you direct **device-to-cloud (D2C)** messages to supported endpoints based on **message source and filter conditions**. A telemetry message can be sent to a streaming endpoint for real-time processing, to Azure Storage for archiving, or to a queue/topic for business workflows. However, a route only chooses the **destination**—it does not replace ETL, schema validation, duplicate event handling, downstream processor authorization, or analytics systems.

This lesson belongs to the **IoT and Edge Computing** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, and data, while teaching how to deploy, monitor, secure, and control the cost of application architectures. This lesson connects **device → IoT Hub → routing → processing services → storage/alerting/analytics**, using Java examples and practical production principles.

**Technical scope:** focuses on **Azure IoT Hub device telemetry message routing**, not to be confused with cloud-to-device commands, device twins, internal IoT Edge routing, or Azure Event Grid subscriptions. APIs, endpoint types, identity features, Azure CLI command names, and quotas can vary by IoT Hub tier/region/version; before running in a live subscription, verify official documentation and enabled features. Resource names in this lesson are **fictional for lab use**.

## 1. Learning Objectives

After this lesson, you can:

- Distinguish **D2C telemetry**, **cloud-to-device messages**, **device twins**, **direct methods**, and **routing**.
- Explain **IoT Hub routes**, **message sources**, **routing queries/conditions**, **custom endpoints**, **built-in endpoints**, and the **fallback route**.
- Design routes to **Event Hubs, Service Bus queues/topics, Azure Storage, and Azure Cosmos DB** where endpoint types are supported by IoT Hub.
- Choose **Azure Functions, Stream Analytics, Java workers**, or analytics services as appropriate consumers.
- Send JSON telemetry with the right **contentType** and **contentEncoding** to filter on message body content.
- Write routing queries using **application properties, system properties, and JSON body**.
- Understand **multiple matching routes**, default/fallback behavior, and how to avoid accidentally losing expected data streams.
- Design streaming, alerting, historical data, and dead-letter/replay paths appropriately.
- Control device identities, endpoint authorization, managed identities, Key Vault, and private networking.
- Write Java skeletons to send data from a device and process messages from a streaming endpoint.
- Measure delivery failures, throttling, latency, backlog, and costs, and test negative scenarios.
- Deploy versioned route changes, validate them, and roll back without disrupting production.

## 2. Where IoT Hub Fits in the Architecture

**Azure IoT Hub** is a cloud service capable of ingesting and managing communications with many IoT devices, supporting device authentication, device-to-cloud telemetry, and device management communication patterns.

~~~mermaid
flowchart LR
    D1[Sensor A] -->|MQTT / AMQP / HTTPS D2C| H[Azure IoT Hub]
    D2[Sensor B] -->|D2C telemetry| H
    H -->|Rule: alert| E[Service Bus queue]
    H -->|Rule: all telemetry| V[Event Hubs]
    H -->|Rule: archive| S[Azure Blob Storage]
    H -->|Rule: selected JSON| C[Azure Cosmos DB]
    E --> F[Azure Functions / Java alert worker]
    V --> A[Stream Analytics / Java streaming consumer]
    S --> L[Data lake / offline processing]
    C --> Q[Operational query API]
~~~

The diagram shows **architectural options**: it does not mean a single IoT Hub/account/tier always uses every endpoint at once, or that every message route type works with every target. Choose based on actual capabilities, permissions, networking, and cost.

### D2C vs. C2D

| Stream | Direction | Used For |
|---|---|---|
| **Device-to-cloud telemetry** | Device → IoT Hub → processing | Temperature, vibration, location, network quality |
| **Cloud-to-device messages** | Service → IoT Hub → device | Simple notices/configs per capabilities |
| **Direct methods** | Backend invokes device method expecting response | Controlled reboot, command execution |
| **Device twins** | Desired/reported properties and state metadata | Device configuration, reported state |
| **IoT Hub message routing** | IoT Hub → processing/storage endpoint | Fan-out/filtering data by source/query |

**Routing telemetry does not automatically send a command back to the device.** If an alert needs to trigger device control, the backend must run a separate control workflow with authorization, safety checks, and device capabilities.

## 3. Data Model of a Telemetry Message

Example sensor payload:

~~~json
{
  "schemaVersion": 1,
  "messageId": "sensor-a-0000182",
  "temperatureC": 81.4,
  "vibrationMmS": 12.3,
  "humidityPct": 57.2,
  "recordedAtUtc": "2026-11-20T08:15:30Z",
  "locationId": "factory-hcm-line-2"
}
~~~

An **IoT Hub message** also carries metadata outside the body:

~~~text
System properties:
  connectionDeviceId = sensor-a
  messageId          = sensor-a-0000182
  contentType        = application/json
  contentEncoding    = utf-8
  enqueuedTime       = set by IoT Hub in service format

Application properties assigned by device/app:
  messageType = telemetry
  site = factory-hcm
  severity = normal

Body:
  {"schemaVersion":1,"temperatureC":81.4,...}
~~~

This is a **data-layer illustration**, not an exact raw protocol frame. Some system properties are set by IoT Hub or mapped differently across SDKs; **never trust a device-supplied application property as security identity proof**.

### Why Include schemaVersion and messageId?

- **schemaVersion** helps consumers recognize payload format and migrate safely.
- **messageId** or a stable event ID supports deduplication/idempotency.
- **recordedAtUtc** captures measurement time on the device, distinct from **IoT Hub enqueued time**.
- **locationId** is business data requiring verification against trusted sources/permissions.
- Measurement fields should use **numeric types** and explicit units, avoiding strings with embedded units that complicate filtering/math.

Offline devices can resend old data; consumers must separate **event time**, **ingestion time**, and **processing time**, never assuming every message arrives in chronological measurement order.

## 4. Device Identity Is Not an Application Property

IoT Hub enforces device identity via a device identity registry with methods like SAS/tokens or X.509 by design. When a device connects and sends a message, the Hub knows the connection identity at the protocol layer.

Do not judge a telemetry message's authorization solely from its body:

~~~json
{"deviceId": "admin-sensor", "temperatureC": 90}
~~~

A `deviceId` field in the JSON body can be spoofed by a misbehaving device. Consumers should rely on the **device connection identity from trusted IoT Hub metadata**, combined with registry/twin/asset mappings if required by business logic. If forwarding across an endpoint drops or alters metadata, explicitly design preservation/normalization and verify it.

### Identity Layers

| Layer | Who Is Authenticated? | Example |
|---|---|---|
| **Device → IoT Hub** | Specific device | Device SAS/X.509 credential |
| **IoT Hub → custom endpoint** | Hub service via SAS/managed identity config | Event Hubs/Service Bus/Storage permissions |
| **Consumer → endpoint** | Azure Function/Java worker | Managed identity or consumer credential |
| **Processor → database/action** | Worker/backend workload | SQL/Cosmos data-plane permission |
| **Operator → control plane** | Person/process managing routes | Azure RBAC on the target resource |

An **IoT Hub Contributor** role on the management plane does not automatically grant read access to custom Event Hubs/Storage or device update rights.

## 5. What Components Make Up a Route?

With message routing, operators define:

1. **Name** — independent, auditable route name.
2. **Data source** — e.g., **Device Telemetry Messages**.
3. **Condition/query** — filter expression over message properties/body.
4. **Endpoint** — built-in or configured custom endpoint.
5. **Enabled** — whether the route is active.

~~~text
Route: route-high-temperature
  Source: Device Telemetry Messages
  Condition: $body.temperatureC > 80
  Endpoint: servicebus-alerts
  Enabled: true

Route: route-all-telemetry
  Source: Device Telemetry Messages
  Condition: true
  Endpoint: eventhub-telemetry
  Enabled: true
~~~

This is a **configuration description**, not directly deployable YAML. Check **IoT Hub Message routing query syntax** for exact routing query/body syntax and endpoint types, including contentType/contentEncoding requirements.

### Source Matters

To route sensor readings, select the **device telemetry messages** source. A route using **device lifecycle events** will not automatically receive telemetry; verify supported event sources and features against your Hub tier/config.

## 6. Built-in Endpoint and Custom Endpoints

IoT Hub includes a **built-in endpoint** compatible with Azure Event Hubs so consumers can read inbound Hub messages in a streaming model.

Supported custom endpoint types for routing can include:

- **Azure Event Hubs** — message streams for streaming consumers/analytics.
- **Azure Service Bus queue** — independent job processing with downstream retries/dead-lettering.
- **Azure Service Bus topic** — fan-out events to subscriptions with distinct filters.
- **Azure Storage container** — batch message archival for analytics/retention.
- **Azure Cosmos DB** — land matching records into a NoSQL operational store when supported as a routing endpoint.

| Destination | Processing Pattern | What It Is Not |
|---|---|---|
| **Built-in events endpoint** | Event Hubs-compatible consumer | A self-managed custom Event Hubs namespace |
| **Custom Event Hubs** | Stream Analytics, Java processors, multiple consumer groups | A query database or work queue |
| **Service Bus queue** | Java/Function per-item processing, retries/DLQ | An ultra-high-throughput time-series store |
| **Service Bus topic** | Multiple business subscribers | Self-managed WebSocket client connections |
| **Azure Storage** | Archive, replay, data lake | A real-time alerting engine |
| **Cosmos DB** | JSON documents for queries/state | A durable message broker for multiple consumers |

**A consumer does not automatically receive from a route just because an endpoint exists.** You must configure the route, endpoint connectivity, consumer group/subscription/trigger, identity, and explicit permissions.

## 7. Built-in Event Hubs-Compatible Endpoint

The built-in endpoint is typically referenced in IoT Hub as **messages/events** and exposes an **Event Hubs-compatible name/endpoint**, partition count, and retention policy managed by IoT Hub.

~~~text
Device
  |
  v
IoT Hub
  |
  +-- Built-in events endpoint
  |       |
  |       +-- Consumer group: analytics
  |       +-- Consumer group: diagnostics
  |       +-- Java/Event Hubs SDK processor
  |
  +-- Custom routes -> other endpoints
~~~

### Key Points to Remember

- This is an **Event Hubs protocol-compatible** endpoint provided by IoT Hub, not an independent Event Hubs namespace you own.
- Compatible client SDKs/consumers work, provided you fetch the exact **Event Hubs-compatible endpoint/name** from the Hub.
- Consumers should use **separate consumer groups** when reading independently.
- Data is kept only for the **retention window**—do not treat it as an infinite history store.
- Reading an event does not delete it for other consumer groups; each consumer tracks its own offsets/checkpoints.

### Default/Fallback Route

Automatic delivery to the built-in endpoint **can change once you add routes/custom routing**. Inspect the **fallback route** and existing routes rather than assuming every telemetry message is always copied to the built-in endpoint.

**Safe practice:** If a business requirement states "all telemetry must reach analytics," define an **explicit route** to the built-in or custom Event Hubs endpoint with the right condition and verify delivery. Never rely purely on defaults once custom routes are configured.

## 8. Multiple Routes Can Match One Message

Routing queries **do not act like an if/else chain picking only the first matching route**. If multiple routes match, the message can be routed to multiple endpoints per service configuration and limits.

~~~text
Input: temperatureC = 85.4

Route A: true                         -> Event Hubs
Route B: $body.temperatureC > 80      -> Service Bus alerts
Route C: messageType = 'telemetry'    -> Storage archive

Expected result:
  A + B + C all match; endpoints receive messages per rules
~~~

This enables **fan-out**: alerting, archiving raw telemetry, and feeding analytics simultaneously. However, it can introduce:

- Duplicate business processing if two routes feed the same pipeline.
- Higher costs from multiplying data paths.
- Independent permissions, networking, and health per endpoint.
- No shared ordering guarantee across endpoints.

Do not build logic assuming "if the alert route matches, the storage route won't run" without explicit exclusion conditions.

## 9. Fallback Route: Handling Unmatched Messages

The **fallback route** sends messages that **match no custom routes** to the built-in endpoint per IoT Hub configuration. It helps catch unclassified telemetry, yet is not a general-purpose **dead-letter queue** for downstream failures.

Example:

~~~text
Message = {"temperatureC": 22}

route-high-temperature:  condition temperatureC > 80
  -> no match

route-raw-type-alarm:     condition messageType = 'alarm'
  -> no match

fallback route enabled:
  -> built-in events endpoint per config
~~~

### Distinguishing Fallback from Delivery Failure

| Scenario | What to Understand |
|---|---|
| No route matches | Fallback may receive it if enabled/per config |
| Both Route A and Route B match | Corresponding endpoints can both receive copies |
| Route matches yet endpoint has an outage | This is a **delivery/retry/expiration** issue, not auto-fallback for "unmatched" |
| Consumer receives then fails processing | Needs consumer/broker retry/DLQ/replay, not IoT Hub fallback |

**Never call the fallback route a 100% zero-data-loss guarantee.** Monitor route deliveries, endpoint health, and maintain a proper archive/replay path.

## 10. Routing Queries Filtering on Application Properties

Application properties are client-assigned metadata outside the JSON body:

~~~text
messageType = telemetry
severity = critical
site = factory-hcm
~~~

Example conditions in IoT Hub routing query syntax:

~~~sql
messageType = 'telemetry'
~~~

~~~sql
severity = 'critical' AND site = 'factory-hcm'
~~~

Key details:

- Property names and values must match naming conventions and types.
- **Device-supplied** application properties are untrusted for authorization decisions.
- Routing queries do not turn a property into a Microsoft Entra ID-signed claim.
- Missing properties may cause queries not to match; write tests for undefined/null fields.
- If a client SDK maps properties differently, inspect the actual received message with a device simulator.

**Routing by application properties** is often more predictable than body parsing when payload schemas evolve, though ingestion validation downstream is still required.

## 11. Routing Queries Filtering on JSON Body

When routing by content, IoT Hub needs to know the message body is **UTF-8 JSON** via appropriate properties.

Example message:

~~~json
{
  "temperatureC": 82.7,
  "vibrationMmS": 15.8,
  "recordedAtUtc": "2026-11-20T08:15:30Z"
}
~~~

System properties from the device SDK must specify:

~~~text
contentType = application/json
contentEncoding = utf-8
~~~

Illustrative routing queries:

~~~sql
$body.temperatureC > 80
~~~

~~~sql
$body.temperatureC > 80 AND $body.vibrationMmS > 10
~~~

### Why Might a Route Not Match Even When Data Looks Right?

- Missing **contentType** or **contentEncoding**, preventing IoT Hub from evaluating the body as JSON.
- **temperatureC** sent as a string instead of a number.
- Device sends **TemperatureC** instead of **temperatureC**.
- Malformed JSON syntax/encoding.
- Nested schema where the query uses the wrong path.
- Route targets the wrong message source or is disabled.

**IoT Hub routing queries are not a general-purpose ETL engine.** If you need Fahrenheit → Celsius conversion, complex JSON Schema validation, or asset metadata joins, use Stream Analytics, Azure Functions, or a Java processor downstream of the endpoint.

## 12. System Properties and Device Connection Identity

IoT Hub attaches system metadata covering **connection device ID**, enqueue time, message type, and service-defined fields. A routing query can reference `$`-prefixed system properties where supported:

~~~sql
$connectionDeviceId = 'sensor-a'
~~~

However, available system properties vary by message source, context, and API; check **routing query syntax** for the exact source and property types.

### Is Filtering by Device ID Enough?

Fine for routing a few test devices. Avoid creating thousands of **one-route-per-device** rules when you can group by **site, device twin metadata, message type**, or downstream logic. Keep route/endpoint quotas and IaC maintainability in mind.

### System Time vs. Device Time

- **recordedAtUtc** in the body is sent by the device and may suffer from clock skew.
- **IoT Hub enqueued time** is stamped by the Hub upon ingestion.
- **processedAtUtc** is stamped by the worker during processing.

In Stream Analytics, windowing and late/out-of-order handling depend on whether you use **event time** or **arrival time**. Do not assume old events are dropped automatically without configuring watermarks/late-arrival policies.

## 13. Endpoint Selection Table by Business Goal

Suppose a system needs **instant alerts**, **windowed metrics**, and **12-month raw data storage**. You do not have to force one endpoint to do all three.

| Need | Endpoint/Pipeline to Evaluate | Why | What Else Is Needed |
|---|---|---|---|
| High-temperature alerts | Service Bus queue → Java worker/Function | Work distribution, retries, and downstream DLQ | Threshold check, dedup, alert cooldown |
| Near-real-time dashboard | Event Hubs → Stream Analytics/Java consumer | High-volume streaming with consumer groups | Windows, late arrivals, data sink |
| Audit/replay | Azure Storage container | Raw data retention in batches/formats | Retention, immutable policies if needed, date partitioning |
| Querying device JSON | Cosmos DB | Queries, TTL, partitioning, and app access | Partition key, RU, indexing, schema migration |
| Multiple microservices receiving alerts | Service Bus topic | Independent subscriber processing | Subscription filters, DLQ, and permissions |
| Real-time web notifications | Alert worker → Web PubSub | Push to browsers | Auth/authz, reconnects |

**Endpoint routing and downstream processing are distinct responsibilities.** Routing to Event Hubs does not generate reports; routing to Service Bus does not run Java logic; routing to Storage does not build query indexes.

### When to Use Multiple Endpoints?

A practical architecture might look like:

~~~text
IoT Hub -- all telemetry --> Event Hubs --> Stream Analytics
       |
       +-- all telemetry --> Storage archive
       |
       +-- hot readings --> Service Bus queue --> Java alerts
~~~

This decouples pipelines while introducing **per-target cost, IAM, operations, and potential timing skew across systems**.

## 14. Custom Event Hubs Endpoint: Built for Streaming

**Azure Event Hubs** is a high-throughput event ingestion platform using a partitioned log. Use a dedicated Event Hubs endpoint when:

- You need consumer groups/retention/throughput managed independently of IoT Hub.
- Multiple Java apps/Stream Analytics/analytics jobs read concurrently.
- You want to decouple stream lifecycles from IoT Hub, or manage specific networking/IAM.
- You need to scale partitions/throughput by load and chosen Event Hubs SKU.

~~~text
IoT Hub route "all-telemetry"
              |
              v
Custom Event Hubs endpoint: eh-telemetry
       |
       +-- consumer group: stream-analytics
       |
       +-- consumer group: java-aggregator
       |
       +-- consumer group: diagnostics
~~~

### Consumer Groups and Checkpoints

Each consumer group provides an independent view of the stream. Within a single consumer group, processor instances coordinate partition ownership. Across consumer restarts, **checkpoints/offsets** track where to resume reading.

**Event Hubs retention is not a permanent archive.** If a processor stops longer than the retention window, expired data cannot be replayed from Event Hubs; a separate Storage archive may be required.

### Partition Keys and Ordering

Events are distributed across partitions per service behavior. Ordering should only be expected **within a single partition and sequence of messages sharing routing conditions**, not globally across partitions/regions/routes. Any business logic requiring per-device order should use **device sequence numbers + checkpoints + deduplication**.

### Built-in or Custom Event Hubs?

The built-in endpoint is convenient when learning or for small pipelines, while custom endpoints allow **independent Event Hubs management**. Do not switch to custom merely because it says "Event Hubs": consider quotas, costs, security, operations, and consumer migration downtime.

## 15. Service Bus Queue: Processing Individual Alerts

When a sensor emits a high-temperature reading, a **conditional route** delivers it to a Service Bus queue. A Java worker consumes the message and executes business logic.

~~~text
Sensor: temperatureC=85
       |
       v
IoT Hub route hot-reading
       |
       v
Service Bus queue: telemetry-alerts
       |
       v
Java AlertProcessor
  +-- Validate telemetry schema
  +-- Lookup trusted asset/device mapping
  +-- Deduplicate event
  +-- Check alert state / cooldown
  +-- Persist alarm + notify operator
~~~

### Why Not Send SMS/Email Directly from an IoT Hub Route?

Routing does not run arbitrary Java handlers. Queuing before processing provides:

- Backpressure and isolation between telemetry spikes and SMS/email providers.
- Retries on transient downstream failures.
- Dead-lettering when an event cannot be processed per policy.
- Traceability of message IDs, worker attempts, and business states.

### Service Bus Does Not Replace IoT Hub

IoT Hub handles **device connectivity/identity**, while Service Bus queues handle **enterprise messaging** between cloud services. Do not make devices send directly to Service Bus instead of IoT Hub when provisioning, twins, device security, and IoT protocol support are needed.

### Dead-Letter Queue (DLQ)

Service Bus provides a DLQ. Messages failing due to bad schemas, missing asset permissions, or exhausted retries may require manual inspection. **Never auto-complete and discard an event when the business transaction actually failed**—nor retry an unfixable invalid schema forever.

## 16. Service Bus Topic: One Event for Multiple Domains

When the same alert must be processed independently by maintenance, safety, and reporting systems, topics/subscriptions can fit better than a queue:

~~~text
IoT Hub route severe-events
          |
          v
Service Bus topic: factory-events
          |
          +-- subscription maintenance
          |        -> Java CMMS integration
          |
          +-- subscription safety
          |        -> Incident processing
          |
          +-- subscription reporting
                   -> Analytics projection
~~~

The **IoT Hub routing query** determines which messages reach the **topic endpoint**. **Service Bus subscription rules/filters** further partition messages per subscriber based on broker-received properties—two distinct configuration layers.

### Fan-Out and Duplicates

One event can be delivered to multiple subscriptions intentionally. Still, retries within a single subscription can cause reprocessing, so business actions require **idempotency** keyed by eventId and business entity.

### When Not to Use a Topic?

If there is only one worker and no pub-sub requirement, a queue is simpler. Topics add costs/limits, subscription lifecycle management, and more complex permissions.

## 17. Azure Storage Endpoint: Archiving Telemetry

A route to an **Azure Storage container** archives raw telemetry using formats/partitioning supported by IoT Hub.

~~~text
IoT Hub -- route archive --> Blob Storage container
                                    |
                                    +-- time-partitioned blobs
                                    +-- batch/format configured by route
                                    +-- lifecycle retention rules
                                    |
                                    v
                          Data lake / Spark / SQL analytics
~~~

### Decisions to Make

| Decision | Example/Meaning |
|---|---|
| **Storage account region** | Same region or one meeting data residency |
| **Container name** | telemetry-raw |
| **Encoding/format** | JSON or AVRO per endpoint support |
| **Blob naming/partitioning** | Organized by date/hour/IoT Hub metadata |
| **Batch/aggregation time** | Trade-off between file size and arrival latency |
| **Retention/lifecycle** | Hot → Cool/Archive → delete per policy |
| **Network/IAM** | Managed identity or keys/SAS per endpoint mechanism |
| **Integrity/replay** | Event counting, dedup, and verification |

### Do Not Mistake a Storage Route for Real-Time Alerting

IoT Hub can **batch messages into blobs**, so an event does not necessarily appear as a separate blob immediately after sending. Systems needing alerts within seconds must use a separate streaming/queue path rather than waiting for archive batches.

### File Formats and Schemas

If choosing AVRO, consumers must use a compatible decoder/schema. If choosing JSON, inspect how IoT Hub wraps **metadata, messages, and body** inside the file rather than assuming a file holds a bare sensor JSON object. Downstream ETL may be needed to normalize records.

**Azure Storage lifecycle rules do not provide infinite retention.** Regularly verify retention and legal requirements; deleting archives can eliminate replay capability if Event Hubs retention has also expired.

## 18. Azure Cosmos DB Endpoint: Queryable Telemetry Storage

Some IoT designs use **Azure Cosmos DB for NoSQL** to query data by device, time, location, or status. When IoT Hub routing supports Cosmos DB endpoints per config, plan:

- JSON schema and property types.
- **Partition key** with even distribution across workloads.
- TTL/retention and RU/s or autoscale.
- Indexing policy matching query patterns (avoid indexing huge payloads unnecessarily).
- Data-plane roles and network controls.
- Duplicate/late messages and item identity.

### Read Model Example

~~~json
{
  "id": "sensor-a-0000182",
  "deviceId": "sensor-a",
  "siteId": "factory-hcm",
  "temperatureC": 81.4,
  "recordedAtUtc": "2026-11-20T08:15:30Z",
  "ingestedAtUtc": "2026-11-20T08:15:31Z"
}
~~~

This is the **desired query shape**, not a promise that IoT Hub automatically populates all fields or maps JSON bodies identically. If you need trusted **deviceId, ingestedAtUtc, schema normalization, or deterministic item IDs**, place an **Azure Function/Java transformation processor** between the IoT Hub route and Cosmos DB.

### When Should a Processor Sit Before Cosmos DB?

- Invalid payloads or devices running multiple schema versions.
- Mapping device IDs to verified tenants/assets.
- Idempotent upserts.
- Encryption/redaction/normalization.
- Custom partition key/ID transformations.
- Pre-aggregating readings to cut RU consumption.

**Cosmos DB is not a message queue guaranteeing every consumer reads each message once.** If the source requires replays and multiple independent consumers, Event Hubs or Service Bus paired with archives/processors fits better.

## 19. Azure Functions Consuming Telemetry via Endpoints

**Azure Functions** can be triggered by:

- **Event Hubs trigger** reading custom or built-in Event Hubs-compatible endpoints where supported.
- **Service Bus trigger** reading alerting queues/subscriptions.
- **Blob trigger** or pipelines once data is archived.

### Java Event Hubs Trigger Example

~~~java
package com.example.iot;

import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.EventHubTrigger;
import com.microsoft.azure.functions.annotation.FunctionName;

public class TelemetryFunctions {

    @FunctionName("processTelemetry")
    public void processTelemetry(
        @EventHubTrigger(
            name = "telemetryEvent",
            eventHubName = "%EVENT_HUB_NAME%",
            connection = "EVENT_HUB_CONNECTION",
            consumerGroup = "%EVENT_HUB_CONSUMER_GROUP%"
        ) String message,
        ExecutionContext context) {

        // Message may be an envelope/body depending on binding configuration.
        // Parse, validate, verify metadata/identity, and enforce idempotency.
        context.getLogger().info("Telemetry event received");
        // Do not log raw payloads if they contain sensitive data.
    }
}
~~~

**This code is a function skeleton:** it requires the **azure-functions-java-library** Maven dependency, compatible Function host and bindings config, local.settings.json/app settings, and Event Hubs read permissions. **EVENT_HUB_CONNECTION** is a binding setting name, not a URL/secret hardcoded in source. Check how IoT Hub's Event Hubs-compatible endpoint is configured if using the built-in route, since its endpoint/name differs from a self-managed Event Hubs namespace.

### Function Execution Is Not Exactly-Once

Triggers can rerun after failures, rebalances, or timeouts. Use messageId/deviceId/sequence numbers for deduplication, let the processor checkpoint cleanly, and make database writes idempotent.

### Under Very High Traffic

Serverless systems have scale limits, concurrency settings, cold starts, and downstream constraints. Never blindly scale Functions instances if Azure SQL/Cosmos DB/notification APIs are the bottleneck; apply throttling/backpressure and budgets.

## 20. Java Worker Processing a Service Bus Queue

To consume alerts routed from IoT Hub to a Service Bus queue, a Java service can use the **Azure Service Bus SDK** with a processor client.

~~~java
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusProcessorClient;
import com.azure.messaging.servicebus.models.ServiceBusErrorContext;
import com.azure.messaging.servicebus.models.ServiceBusReceivedMessageContext;

public class AlertWorker {
    public static void main(String[] args) throws Exception {
        String connection = System.getenv("SERVICE_BUS_CONNECTION_STRING");
        if (connection == null || connection.isBlank()) {
            throw new IllegalStateException("Missing Service Bus credential");
        }

        ServiceBusProcessorClient processor =
            new ServiceBusClientBuilder()
                .connectionString(connection)
                .processor()
                .queueName("telemetry-alerts")
                .processMessage(AlertWorker::handle)
                .processError(AlertWorker::onError)
                .buildProcessorClient();

        processor.start();
        // Worker host keeps the process alive and manages shutdown.
        // In a real app: close the processor when the host stops.
    }

    private static void handle(ServiceBusReceivedMessageContext ctx) {
        String payload = ctx.getMessage().getBody().toString();
        // Parse JSON, validate, enforce idempotency, and commit business work.
        // Do not log sensitive payloads or handle alerts directly here without guards.
    }

    private static void onError(ServiceBusErrorContext ctx) {
        // Log redacted operation/entity/error code.
        System.err.println("Service Bus processing error");
    }
}
~~~

This is an **architectural template**, not a complete production worker: pin **com.azure:azure-messaging-servicebus**, handle concurrency, lock renewal, settlement modes, dead-lettering, graceful shutdown, and monitoring. **Never put real namespace connection strings in code or Git**; in production, prefer supported credential/token identities.

### Auto-Complete and Business Errors

With SDK processors defaulting to auto-complete, returning normally from the callback marks the message complete. If the callback skips validation or swallows exceptions and returns, the system can **complete the message without ever recording the alert**. Configure settlement mode, retries, and DLQ properly to prevent silent data loss.

### Java Consumers Must Understand Route Sources

Service Bus messages arriving from IoT Hub routing carry **body and metadata** formatted by the endpoint. Inspect actual metadata (device ID, message ID, content type) in a lab and normalize it; do not assume every message has a bare JSON body if the SDK/binding wraps a different envelope.

## 21. Stream Analytics for Cleaning and Aggregating Telemetry

**Azure Stream Analytics** can consume streams from IoT Hub or Event Hubs via supported input configurations, process time windows, and write to sinks.

Conceptual query for 1-minute average temperature:

~~~sql
SELECT
    deviceId,
    System.Timestamp() AS windowEnd,
    AVG(CAST(temperatureC AS float)) AS avgTemperatureC,
    COUNT(*) AS sampleCount
INTO
    [temperature-averages]
FROM
    [telemetry-input] TIMESTAMP BY recordedAtUtc
GROUP BY
    deviceId,
    TumblingWindow(minute, 1)
~~~

**This is a Stream Analytics query model**, not an IoT Hub routing query or Azure SQL T-SQL. Configure input/output aliases, event-time mapping, data types, late-arrival/out-of-order policies, and partitioning; verify `CAST`/types and field names against the real schema.

### Separation of Responsibilities

- **IoT Hub routing query:** filter and forward messages to endpoints.
- **Stream Analytics SQL:** transform, aggregate/window, and join streams/reference data under conditions.
- **Java downstream service:** custom business logic, enrichment, persistence, and notifications.

If minute averages are required, IoT Hub will not compute `AVG`/`COUNT` merely because a route checks `temperature > 80`.

## 22. Azure Event Grid and IoT Events

**Azure Event Grid** is commonly used for event-driven subscriptions/filters/handlers. IoT Hub integrates specific **event types** such as device lifecycle changes and documented telemetry-related capabilities.

### Do Not Conflate Three Concepts

| Component | Function |
|---|---|
| **IoT Hub message routing** | Routes D2C messages by rules to supported endpoints |
| **Event Grid event subscription** | Delivers publisher event types to handlers using the Event Grid schema |
| **Stream Analytics/Event Hubs** | Continuous stream consumption/analytics |

If the goal is **high-throughput streaming ingestion of all telemetry**, the Event Hubs-compatible endpoint or custom Event Hubs is the natural path. If the goal is **reacting to device lifecycle events**, Event Grid may fit well.

**Do not treat Event Grid as a custom routing endpoint alongside Event Hubs/Service Bus/Storage** if the IoT Hub Portal does not list that endpoint type. Wire Event Grid through its supported event subscription feature.

## 23. IoT Edge: Processing at the Edge Before Cloud Routing

In factories with unstable networks, gateways/edge devices can process locally:

~~~text
Sensors -> Edge gateway / local processor
           |
           +-- Local validation / aggregation / anomaly flag
           +-- Store-and-forward on network loss per edge capability
           |
           v
        IoT Hub
           |
           +-- Routes -> cloud processors
~~~

The IoT Edge runtime/module ecosystem has its own **local edge routing and store-and-forward**, distinct from **IoT Hub cloud message routing**. An event sent by edge to IoT Hub gets evaluated by IoT Hub routes; a message sitting inside an edge local queue has not yet been accepted by IoT Hub.

### When Does Edge Processing Help?

- Constrained WAN bandwidth: send **aggregates** instead of continuous raw samples.
- Need local alerts even when Internet drops.
- Heavy camera/audio data requiring inference near the source.
- Filtering anomalies before shipping to the cloud.

### Trade-Offs

- Raw data may never reach the cloud if only aggregates are sent.
- Must manage versions, identities, disk buffers, and edge power loss.
- Late-arriving data in the cloud requires event-time handling.
- Edge device security/patching remains an operational duty.

## 24. Java Device Simulator Sending D2C Telemetry

In a lab, a **Java simulator** acts as a test device with its own identity in IoT Hub. It uses the **Azure IoT device SDK for Java** with a device-scoped credential; **never use an iothubowner/service-wide key** on a device.

### Send Flow

~~~text
Java simulator
  |
  +-- Read device identity credential securely
  +-- Construct JSON telemetry
  +-- Set contentType=application/json
  +-- Set contentEncoding=utf-8
  +-- Add application property messageType=telemetry
  +-- Send D2C event asynchronously
  |
  v
Azure IoT Hub (authenticated device)
  |
  v
Routing engine evaluates message source/query
~~~

Illustrative Java skeleton using the classic device SDK pattern:

~~~java
import com.microsoft.azure.sdk.iot.device.DeviceClient;
import com.microsoft.azure.sdk.iot.device.IotHubClientProtocol;
import com.microsoft.azure.sdk.iot.device.Message;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class TelemetryDeviceSimulator {
    public static void main(String[] args) throws Exception {
        String deviceConnectionString =
            System.getenv("IOTHUB_DEVICE_CONNECTION_STRING");
        if (deviceConnectionString == null ||
                deviceConnectionString.isBlank()) {
            throw new IllegalStateException(
                "Missing device-scoped credential");
        }

        DeviceClient client = new DeviceClient(
            deviceConnectionString, IotHubClientProtocol.MQTT);

        client.open();
        try {
            String json = """
                {
                  "schemaVersion": 1,
                  "messageId": "sensor-lab-001",
                  "temperatureC": 85.0,
                  "vibrationMmS": 11.0,
                  "recordedAtUtc": "2026-11-20T08:15:30Z"
                }
                """;
            Message message = new Message(
                json.getBytes(StandardCharsets.UTF_8));
            message.setContentType("application/json");
            message.setContentEncoding("utf-8");
            message.setProperty("messageType", "telemetry");
            message.setProperty("site", "factory-lab");

            CountDownLatch completed = new CountDownLatch(1);
            AtomicReference<String> status = new AtomicReference<>("pending");
            client.sendEventAsync(message, (result, context) -> {
                status.set(String.valueOf(result));
                completed.countDown();
            }, null);

            if (!completed.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Send acknowledgement timed out");
            }
            System.out.println("IoT Hub send status: " + status.get());
            // Real apps must inspect the result enum and retry policy.
        } finally {
            // Example awaited callback or timeout; real apps must handle
            // timeouts/pending sends and graceful shutdown cleanly.
            client.closeNow();
        }
    }
}
~~~

**This snippet is a conceptual example of the Azure IoT Java device SDK.** Pin a supported **com.microsoft.azure.sdk.iot:iot-device-client** version and verify **Message.setContentType/setContentEncoding/sendEventAsync/closeNow** signatures, callback semantics, and credentials in your project. The sample waits up to 30 seconds for the callback, yet **printing a status does not guarantee send success**: inspect the result enum, callback errors, retry counts, and timeout/pending-send cases per your pinned SDK. In long-lived apps, reuse `DeviceClient` instead of opening/closing per event.

### Practical SDK Send Pattern

1. Connect with **device-scoped authentication** and TLS.
2. Generate a **fresh messageId** per real sample; the fixed ID above is illustrative only.
3. Set **JSON UTF-8 headers** properly so body filters match.
4. Send and await **IoT Hub ingress** acknowledgment, logging status safely.
5. On network loss, use an offline queue/store-and-forward if required.
6. Close/clean up resources per SDK lifecycle.

**IoT Hub ingress acknowledgment only proves the Hub accepted the message per protocol—not that downstream routes/consumers processed it successfully.**

## 25. Message Enrichments and Asset Metadata

**Message enrichments** let IoT Hub stamp extra information onto messages routed to configured endpoints, depending on metadata type/tier and service support.

Desired example:

~~~text
Original device message:
  body: {"temperatureC": 82}
  app property: messageType=telemetry

Trusted metadata configured in IoT Hub:
  assetSite = factory-hcm
  assetClass = refrigeration

Routed message:
  body: same JSON telemetry
  properties: additional enrichment information
~~~

### Why Enrich Before Routing?

- Analytics teams want Hub/tenant/site context without joining every message.
- Multiple consumers need the same tag from a source more trustworthy than device-supplied properties.
- Reduces duplicate metadata lookup logic across downstream services.

### Limitations to Remember

- Enrichment sources can be a **constant value, IoT Hub name, device twin data**, or other service-supported options.
- Only supported paths/properties can be added; do not turn enrichments into general ETL.
- Device twin tags/properties may be missing or stale; design defaults/validation.
- Enrichments do not replace authorization when one consumer serves multiple tenants.
- If a route query relies on an enrichment, verify **when routing queries evaluate relative to enrichments** in the service. Do not assume filters automatically see properties added only at endpoint dispatch.

**Do not conflate enrichment metadata with device-reported body fields.** Track the provenance and trust level of every field.

## 26. Schema Evolution, Versioning, and Type Safety

Factory devices often roll out firmware in waves. On the same day, a consumer may receive both schema version 1 and version 2.

~~~json
{
  "schemaVersion": 2,
  "deviceMessageId": "sensor-a-0000183",
  "measurements": {
    "temperatureC": 84.1,
    "vibrationMmS": 12.5
  },
  "recordedAtUtc": "2026-11-20T08:15:40Z"
}
~~~

Between v1 and v2, the temperature path moved from **$body.temperatureC** to **$body.measurements.temperatureC**. A route filtering v1 will not automatically understand v2.

### Three Migration Options

1. **Preserve backward compatibility:** v2 continues emitting the legacy field during transition if size/format permit.
2. **Expand route conditions:** support v1/v2 using OR conditions and type checks without guessing missing fields.
3. **Normalize downstream:** route broadly by `messageType`, use a Function/Java processor to convert v1/v2 into a canonical schema, then evaluate alerts.

Pseudo-condition example (verify exact route engine syntax and property types):

~~~text
version 1: $body.temperatureC > 80
version 2: $body.measurements.temperatureC > 80

Desired: (v1_condition) OR (v2_condition)
~~~

**Never delete the v1 route immediately upon deploying firmware v2.** Offline devices can keep sending v1 for a long time; check rollout inventory and live message traffic first.

### Use a Schema Registry?

Schema registries/contract governance can be built into processors or analytics pipelines depending on stack. IoT Hub routing does not validate full JSON Schemas for every device event. Backends must still validate schemas and enforce payload size limits.

## 27. Delivery Semantics: Ingress, Routing, and Downstream

Distinguish three moments:

~~~text
(1) Device -> IoT Hub ingress accepted
                |
                v
(2) IoT Hub routing -> endpoint accepted
                |
                v
(3) Consumer processed -> DB/business effect committed
~~~

### One Acknowledgment Does Not Cover Everything

| Level | Evidence | What It Does Not Prove |
|---|---|---|
| **Device send acknowledged** | Hub received the message | Endpoint persisted or processed it |
| **Route delivery succeeded** | Endpoint accepted per service semantics | Java consumer committed business work |
| **Broker message completed/checkpointed** | Consumer confirmed position/handling | SMS/email alert reached the user |
| **Business effect recorded** | DB transaction/audit | User saw the alert |

In message-driven architectures, design **at-least-once-compatible processing** and deduplication. Never assume messages arrive once or in global order.

### Message ID and Device Sequence

Devices should keep a **stable eventId** for a measurement across retries; minting a new ID on every retry prevents backend deduplication. One design uses:

~~~text
idempotencyKey = hubId + deviceId + deviceSequence
~~~

where **deviceSequence** increments per device/session with documented reset/reboot behavior. If uniqueness isn't guaranteed, pair timestamps with generated IDs or a stronger idempotency contract. **Never use timestamp alone as a unique ID** when multiple readings can share a timestamp.

### When an Endpoint Fails

IoT Hub applies retries/expiration on route deliveries per service rules and configured timeouts/retention. **Never assume infinite retries or automatic fallback to another route if a matched endpoint stops responding.** Use metrics, alerts, endpoint health checks, and archive/replay designs to recover from outages exceeding retention windows.

## 28. Duplicate Delivery and Event Ordering

Suppose a device sends:

~~~text
seq=101 temperature=78 C
seq=102 temperature=85 C
seq=103 temperature=83 C
~~~

A Java worker might receive **102 twice** after a retry or process **103 before 102** across multiple partitions/instances. If business logic sends a new email for every reading >80, operators will get spammed.

### How to Handle It

- Use **eventId/deviceSequence** as a deduplication key.
- Keep only one active alert per **deviceId + alertType** within a cooldown window.
- Use compare-and-set/versions or transactions when updating last processed sequence.
- Write events to databases with appropriate unique constraints/upserts.
- Apply event-time windows and late-arrival policies for aggregates.
- Retain raw streams/archives if forensic reconciliation is needed.

### Devices with Wrong Clocks

If `recordedAtUtc` is in the past or future, use IoT Hub enqueued time to measure ingestion delay and enforce clock-skew policies. Avoid overwriting the device timestamp if preserving the original value aids tracing.

## 29. Backpressure, Throttling, and Poison Messages

IoT Hub enforces limits on units, message ingress/egress, routing endpoints, and throughput by tier. Downstream endpoints have their own limits too.

### Typical Bottleneck Path

~~~text
10,000 devices -> IoT Hub ingress
                       |
                       v
               Service Bus queue
                       |
                       v
                Java workers
                       |
                       v
                   Azure SQL

When DB writes slowly:
  queue backlog grows
  message age grows
  lock timeouts/retries may increase
~~~

### Fundamental Controls

1. Measure message rates/sizes and peaks per site/device.
2. Pinpoint bottlenecks at **ingress**, **route**, **endpoint**, or **consumer**.
3. Cap concurrency on Java workers to match database capacity.
4. Retry transient errors with backoff/jitter and max attempts.
5. Quarantine/dead-letter invalid schemas ("poison messages") per broker capabilities.
6. Never auto-complete messages while business transactions fail.
7. Scale endpoints/consumers after measuring resource limits and costs.

**Do not add IoT Hub units to fix unrelated downstream bugs.** If Service Bus permissions are wrong, Azure SQL lacks indexes, or the Java parser crashes, scaling the Hub fixes nothing.

## 30. Managed Identity for IoT Hub Routing Endpoints

In supported configurations, **IoT Hub can use a managed identity** to connect to custom endpoints instead of connection strings/keys. This is the **IoT Hub → destination service** identity, distinct from device identities and Java consumer identities.

~~~text
IoT Hub managed identity
       |
       | Data-plane role on destination
       v
Custom Event Hubs / Service Bus / Storage / Cosmos DB
       |
       | Different identity and permission
       v
Java consumer / Azure Function
~~~

### Permissions by Destination

| Destination | Permission to Evaluate |
|---|---|
| Event Hubs | Send events permission on the specific Event Hub |
| Service Bus queue/topic | Send permission on the target entity |
| Azure Storage | Write blob permission on the configured container/account |
| Cosmos DB | Data-plane write permission on database/container per API |

Built-in Azure RBAC roles can have names like **Azure Event Hubs Data Sender**, **Azure Service Bus Data Sender**, **Storage Blob Data Contributor**, or an appropriate Cosmos DB data-plane role. **There is no single "Contributor" role covering every destination data plane.** Verify how IoT Hub endpoints support managed identities and exact role definitions.

### Management vs. Data Plane Relationships

- An operator permitted to create routes in IoT Hub may not have access to view storage keys.
- IoT Hub managed identity having **send** permission on a queue does not give the Java worker **receive** permission.
- A Java worker able to read an event stream is not automatically authorized to write SQL or invoke device methods.

Apply **least privilege** at every hop and test with real identities instead of granting Owner/admin everywhere.

## 31. Networking: Firewalls, Private Endpoints, and Hub Traffic Paths

A custom endpoint may enforce firewalls/private network restrictions. IoT Hub routing must be granted **appropriate service access** via supported networking/managed identity features.

~~~text
IoT devices
    |
    | TLS to IoT Hub public/private ingress as configured
    v
Azure IoT Hub
    |
    | Service-to-service routing
    v
Azure Event Hubs / Service Bus / Storage endpoint
    |
    | Private endpoint/VNet integration for Java consumer
    v
Azure Function / AKS / App Service
~~~

### Separate Hops Are Not Identical

1. **Device → IoT Hub:** MQTT/AMQP/HTTPS, DNS, TLS, device auth, IoT Hub network restrictions.
2. **IoT Hub → custom endpoint:** service-managed routing path and endpoint network policy.
3. **Consumer → endpoint:** Java process/Function VNet, DNS, firewall, SDK identity.

An AKS worker reaching Service Bus over a Private Endpoint **does not prove IoT Hub routing can deliver to Service Bus**; IoT Hub → Service Bus is a separate hop. A consumer-only Private Endpoint also does not open the routing path if the target blocks Hub access.

### Moving Safely to Private Networking

- Verify resource SKU/network support, managed identities, and policies.
- Configure destinations to accept IoT Hub routing via Azure-supported mechanisms.
- Test message delivery from a real lab device.
- Verify consumer private DNS/networking.
- Disable public access only after every hop works.
- Prepare admin/emergency access paths and rollback configs.

Do not blindly enable "allow all trusted Microsoft services": this setting has specific scope and conditions requiring security review.

## 32. Protecting Devices and Telemetry Data

Devices can be compromised, inject spoofed data, or drop offline. Cloud security starts on the device:

1. Use **device-level identities**; grant minimal permissions per device.
2. Prefer **DPS (Device Provisioning Service)** for structured bulk provisioning.
3. Protect keys/certificates with TPM/HSM or equivalent secure storage where available.
4. Rotate/revoke credentials when devices are replaced or compromised.
5. Enforce TLS and restrict inbound cloud control per policy.
6. Verify device-to-asset mappings on the backend.
7. Apply schema validation, bounds checks, and anomaly detection.
8. Enforce retention/PII policies for location/serial number/user-linked telemetry.
9. Never store IoT Hub owner/shared access policy keys in firmware.
10. Maintain firmware updates, signed packages, and inventory monitoring per device platform.

### Data Integrity and Trust

A compromised sensor can send **temperatureC=999** even while authenticating with a valid device key. Authentication proves credential identity, not physical reading accuracy. Dangerous actions like halting machinery must go through safety policies and OT/industrial control interlocks.

### Keep Secrets Out of Logs

IoT device connection strings, SAS tokens, X.509 private keys, Event Hubs/Service Bus credentials, and Blob SAS tokens must never appear in Java console logs, dead-letter diagnostics, or tickets.

## 33. Retention, Replay, and Data Reconciliation

A pipeline consisting solely of IoT Hub → Function → dashboard easily loses replayability after an incident. When retention matters, design an independent **archive path**.

~~~text
IoT Hub
   |
   +-- Event Hubs --> Stream Analytics --> Dashboard
   |
   +-- Storage archive --> Offline replay/reprocess
                                |
                                v
                         Java batch processor
~~~

### Replay Has Limits

- Event Hubs holds data only for its **retention window**.
- Service Bus queues do not keep completed messages for historical replay; DLQs hold only failed events.
- Azure Storage archives retain longer yet require clear file naming, schemas, deduplication, and integrity checks.
- Cosmos DB has TTL/retention and does not automatically retain raw telemetry forever.

**"Sent to two endpoints" does not automatically mean two 100% identical data copies.** Routes can have different retries, lag, and endpoint failures; reconcile by messageId/time-window to spot drops or duplicates.

### A Reconciliation Process

1. Count readings by device/site over 10-minute windows at ingress where metrics exist.
2. Count messages delivered per endpoint from Hub metrics/diagnostics.
3. Count messages processed/checkpointed in consumers.
4. Count rows/items persisted in sinks.
5. Use `eventId` to detect duplicates and gaps.
6. On discrepancies, inspect retries, dead-letters, schema errors, retention, and networking.

**Counts do not always match** if routes filter/fan-out, Storage batches, or validation drops bad events; document expected ratios per route before comparing.

## 34. Configuring Routes in Azure Portal

With an authorized **IoT Hub sandbox** and budget, the general workflow is:

1. Open [Azure Portal](https://portal.azure.com), navigate to the target subscription and **IoT Hub**.
2. Open **Message routing/Routing** per the current UI.
3. Review existing routes, endpoints, and **fallback route** status.
4. Create the **custom endpoint** first if the target isn't the built-in endpoint.
5. Select source **Device Telemetry Messages**.
6. Give the route a meaningful name, e.g., **route-hot-temperature-lab**.
7. Enter query `$body.temperatureC > 80` or the appropriate condition.
8. Select the **Service Bus queue** target after verifying networking/permissions.
9. Enable the route; use **Test route** if supported in Portal/API.
10. Send simulated telemetry messages from a test device and observe endpoints and metrics.

### Checks Before Clicking Save

- Right **hub/subscription/resource group**—not production.
- Route source matches device telemetry.
- Condition syntax is valid and JSON fields have expected types.
- Custom endpoint exists with proper **authorization/networking**.
- Fallback behavior for unmatched messages is understood.
- Checked whether other routes also match, avoiding unintended double processing.
- Rollback plan ready if the route causes errors or cost spikes.

**Never edit a production Hub directly** without change approval. A bad route condition or changed fallback can drop expected streams across thousands of devices.

### Testing a Route vs. Testing Delivery

Query testing against a sample verifies **route condition matching**, not that the endpoint actually received the message and the consumer committed it. After testing the condition, send real telemetry from a test device/simulator and verify end-to-end.

## 35. Azure CLI: Inspecting Hub, Routes, and Endpoints

Illustrative commands run via **Azure CLI in Bash/Azure Cloud Shell**; if using the IoT extension, verify your CLI/extension version supports the subcommands.

~~~bash
az login
az account list --output table
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<IOT_HUB_RESOURCE_GROUP>"
HUB="<LAB_IOT_HUB_NAME>"

az iot hub show \
  --resource-group "$RG" \
  --name "$HUB" \
  --query "{name:name,location:location,sku:sku.name}" \
  --output json

az iot hub route list \
  --hub-name "$HUB" \
  --output json

az iot hub routing-endpoint list \
  --hub-name "$HUB" \
  --output json
~~~

**Note:** **route/routing-endpoint** commands depend on Azure CLI/azure-iot extension and may require flags or have different names by version. Check:

~~~bash
az extension list --output table
az iot hub route --help
az iot hub routing-endpoint --help
~~~

These commands only read metadata; the CLI does not automatically hold data-plane permissions for Service Bus/Storage or device credentials. **Never run commands dumping hub keys/policies into publicly logged terminals.**

### Never Create/Edit Production Routes Just to Test Syntax

Commands like **az iot hub route create/update/delete** (when provided by the extension) modify live data paths. Instead:

1. Inspect current state and save configs from the management API.
2. Author route specs in reviewed IaC.
3. Use a lab environment or supported query-testing features.
4. Obtain owner sign-off and monitoring before applying.

## 36. Infrastructure as Code and Versioned Routing

**Routing configuration is part of the architecture** and should be managed like code:

~~~yaml
# CONCEPTUAL manifest - not deployable ARM/Bicep/Terraform.
iotHub: iothub-factory-prod
messageRouting:
  endpoints:
    - name: eh-telemetry
      type: eventHubs
      target: <APPROVED_EVENT_HUB_RESOURCE>
    - name: sb-alerts
      type: serviceBusQueue
      target: <APPROVED_QUEUE_RESOURCE>
    - name: blob-archive
      type: storageContainer
      target: <APPROVED_STORAGE_CONTAINER>
  routes:
    - name: all-telemetry
      source: DeviceMessages
      condition: "true"
      endpoint: eh-telemetry
      enabled: true
    - name: hot-reading
      source: DeviceMessages
      condition: "$body.temperatureC > 80"
      endpoint: sb-alerts
      enabled: true
    - name: raw-archive
      source: DeviceMessages
      condition: "true"
      endpoint: blob-archive
      enabled: true
  fallback:
    enabled: true
~~~

**Do not run the YAML above as an Azure command.** Reference the Bicep/ARM resource schema (`Microsoft.Devices/IotHubs` routing routes/endpoints) or matching Terraform AzureRM provider to author deployable specs with exact schema/versions, managed identities, and endpoint-specific properties.

### Deployment Workflow

~~~mermaid
flowchart TD
    A[Commit route spec + tests] --> B[Static validation + approval]
    B --> C[Deploy lab hub/endpoints]
    C --> D[Send synthetic telemetry]
    D --> E[Test matching + nonmatching]
    E --> F[Test destination + Java consumer]
    F --> G[Check metrics and cost]
    G --> H{Production approval?}
    H -- No --> I[Stop / fix]
    H -- Yes --> J[Apply approved change]
    J --> K[Monitor routing deliveries]
    K --> L{Errors or regressions?}
    L -- Yes --> M[Rollback previous route spec]
    L -- No --> N[Record change evidence]
~~~

### Drift and Conflicts

If an admin edits a route in the Portal and a pipeline later applies older IaC, manual edits get overwritten. Establish a clear **source of truth**, review IAM, and formalize emergency changes; inspect route diffs, conditions, and impact before rolling out.

## 37. Monitoring IoT Hub Routing and Downstream Health

An effective dashboard links at least three layers:

| Layer | Signals | Question |
|---|---|---|
| **Device → IoT Hub** | D2C ingress, errors, connections, auth failures | Can devices send? |
| **Routing** | Matched/unmatched messages, routing deliveries, endpoint delivery errors | Do routes match and dispatch? |
| **Endpoint** | Event Hubs incoming/throughput, Service Bus active/DLQ, Storage blobs, Cosmos RU | Are targets receiving? |
| **Processor** | Java Function invocations, retries, failures, checkpoint lag | Are consumers keeping up? |
| **Business sink** | Stored rows, alerts, dashboard latency | Did business outcomes happen? |
| **Capacity** | Throttled requests, peak/sustained rates, queue depth | Where is the bottleneck? |
| **Cost** | IoT Hub units, downstream charges, storage/lifecycle, logs | Is the flow within budget? |

Azure Monitor **Metrics, Diagnostic settings, Log Analytics, and Application Insights** provide observability depending on resource/tier/features. **Exact metric names vary by product**; inspect current metric definitions rather than assuming every table entry appears automatically.

### Correlation ID

An event can be traced across:

~~~text
Device identity / eventId
      |
      +-- IoT Hub enqueued time / diagnostic ID
      |
      +-- Route name / destination
      |
      +-- Event Hubs partition+offset OR Service Bus message ID
      |
      +-- Java Function/worker invocation ID
      |
      +-- DB row / alert ID
~~~

Never log device connection strings, SAS tokens, raw confidential payloads, or all user locations. At high device counts, use **sampling/counters**, keep essential correlation metadata, and enforce retention policies.

### Actionable Alerts

- Abnormal drop in D2C ingress per site compared to baseline.
- Rising route delivery failures or unhealthy endpoints.
- Service Bus queue backlog/oldest message age breaching SLO.
- Event Hubs consumer lag rising across multiple intervals.
- Rising consumer exception rates or DLQ counts.
- Storage archive producing no blobs within expected intervals.
- Rising IoT Hub throttling during peak fleet activity.

**Zero deliveries on a metric can be normal** if a route's filter matches no messages. Alert logic must reflect expected traffic rather than treating every quiet route as an outage.

## 38. Capacity Planning: Telemetry, Ingress, and Fan-Out

Assume **8,000 devices**, each sending **1 message/10 seconds**, 700-byte payload:

~~~text
Incoming message rate:
  8,000 / 10 = 800 messages/second

In 1 hour:
  800 × 3,600 = 2,880,000 messages

Payload bytes/second (excluding protocol overhead):
  800 × 700 = 560,000 bytes/second
~~~

This is **illustrative math**, not a free IoT Hub allowance. IoT Hub message accounting depends on **message size chunks, tier/units, operations, and quotas**; downstream endpoints carry separate billing rules.

### Fan-Out Multiplies Downstream Traffic

If all telemetry matches:

~~~text
Route A -> Event Hubs:         800 events/second
Route B -> Storage archive:    800 events/second (can batch)

5% of messages exceed threshold:
Route C -> Service Bus alerts: 40 messages/second
~~~

These rates are independent assumptions excluding duplicates, retries, and system overhead. Across 1,000 factories, evaluate limits at **IoT Hub ingress, routing endpoints, Event Hubs throughput/partitions, Storage writes, Service Bus queues, Functions/Java consumers, and databases**.

### Peaks and Downtime

- Devices offline for 30 minutes can replay backlogs simultaneously on reconnect.
- A firmware upgrade can triple message sizes.
- Endpoint outages build queue lag, causing replay bursts on recovery.
- A firmware bug sending every 100 ms instead of 10 seconds can blow past budgets.

Enforce **rate limiting/device policies** and keep capacity headroom. Never size solely on average traffic from a quiet day.

## 39. Cost Management for IoT Pipelines

| Component | Cost Factors |
|---|---|
| **Azure IoT Hub** | Tier, units, metered messages/operations per service rules |
| **Custom Event Hubs** | Throughput/capacity, retention, partitions, capture if enabled |
| **Service Bus** | Tier, messaging operations, topics/subscriptions |
| **Storage** | Blob capacity, transactions, redundancy, lifecycle, egress |
| **Cosmos DB** | RU/s or serverless usage, data/index storage |
| **Functions/AKS/App Service** | Execution count, CPU/memory, nodes/plans |
| **Stream Analytics** | Streaming units/compute per configuration |
| **Network** | Inter-region egress, Private Link, VNet resolvers, NAT |
| **Monitoring** | Log ingestion, retention, alerts, traces |
| **Security** | Key Vault operations, identity/credential management |

### Reasonable Estimation Process

1. Determine device count, send frequency, peaks, and payload-size distribution.
2. Calculate billable messages/operations per the actual **IoT Hub SKU**.
3. Estimate route match percentages per endpoint.
4. Add endpoint writes/reads, retention, and consumer counts.
5. Add Java/Functions compute, database writes, storage, and networking.
6. Include observability/log costs, especially if logging full telemetry bodies.
7. Add peak/backlog headroom and verify in the Azure Pricing Calculator.

**Enabling a new route to Storage or Cosmos DB can generate immediate charges**; budget alerts do not automatically stop resources. Apply owner/environment/costCenter tags and clean up sandboxes after labs.

## 40. Routing and Telemetry Diagnostic Table

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Device send fails | Expired/wrong credential, disabled device, network/TLS | Device identity, callback status, IoT Hub ingress, firewall |
| Hub receives message yet route doesn't match | Bad query, disabled route, wrong source | Routing rules, test condition on actual sample |
| Body-based route doesn't match | Missing contentType/contentEncoding, bad JSON, type mismatch | Body and system headers in device SDK |
| Application-property route doesn't match | Wrong property name/case/value | Actual sent metadata, not just JSON body |
| Built-in endpoint stops receiving data | Modified routes/fallback/default behavior | Built-in route and fallback status |
| Storage archive appears delayed | Batch/file publishing behavior | Endpoint batch config, storage metrics, and blobs |
| Event Hubs has messages yet Java doesn't read | Wrong hub name/namespace/consumer group/permission | Event Hubs-compatible metadata, consumer offsets/checkpoints |
| Service Bus queue backlog grows | Slow worker, DB errors, insufficient max concurrency | Oldest message age, DLQ, worker failures |
| Duplicate alerts sent | At-least-once retries/duplicate device messages | `eventId`, sequence, dedup/cooldown |
| Sensor from another tenant written to wrong DB | Trusted device-supplied tenant/site | System device identity, asset registry mapping |
| Route delivery fails with 401/403 | Hub managed identity/SAS lacks permission | Data-plane RBAC and credential rotation |
| Route delivery times out/forbidden | Target firewall/private network blocks Hub | Hub → endpoint network path, endpoint diagnostics |
| Java processor throws JSON parse error | Schema version/type changed, envelope differs | Payload sample, contentType, decoder |
| 429 from Hub or endpoint | Ingress/quota/throughput or consumer overload | SKU limits, per-resource metrics, peak rate |
| Messages overly stale | Offline replay, event-time drift, backlog | `recordedAtUtc`, enqueued time, `processedAtUtc` |
| Cosmos DB RUs spike | Hot partition, indexing, heavy writes | RU/partition key, SDK query metrics |
| Stream Analytics window wrong | Wrong event-time/late-arrival policy | `TIMESTAMP BY`, watermark, data types |
| Endpoint outage drops events | Retention/route delivery expiration | Archive path, retries, outage duration |

### Stage-by-Stage Analysis Method

**Do not change multiple components at once.** Start at:

1. **Ingress:** can the device send and does IoT Hub accept?
2. **Match:** was the route condition tested on a sample from the right source?
3. **Delivery:** can IoT Hub deliver to the endpoint?
4. **Consumption:** does the consumer have permissions, the right consumer group/subscription, and active reads?
5. **Commit:** did business processing/database writes succeed?
6. **Observation:** do metrics/alerts reflect accurate timing and counts?

If the alert worker isn't sending SMS, adding another IoT Hub route only duplicates messages without fixing the Service Bus consumer or SMS provider.

## 41. Scenario A: JSON Message Has 85°C Yet Route Doesn't Match

**Context:** Sensor-A sends:

~~~json
{"temperatureC": 85, "recordedAtUtc": "2026-11-20T08:20:00Z"}
~~~

Hub has route:

~~~sql
$body.temperatureC > 80
~~~

The device gets a send acknowledgment, yet the Service Bus queue receives no alerts.

### Possible Causes

- Device omitted **contentType=application/json** and **contentEncoding=utf-8**.
- Body is actually a double-encoded JSON string instead of an object.
- Property is **TemperatureC**, or **temperatureC** is a string.
- Route is disabled or points to the wrong source.
- Route matched yet **Service Bus endpoint delivery failed**.
- A consumer already dequeued/completed the message before the operator checked queue depth.

### Runbook

1. Use a lab-credential device simulator to send a fresh event with a unique `eventId`.
2. Confirm the device SDK sets content properties and UTF-8 body bytes.
3. Test query matching against the JSON/sample in route testing.
4. Check endpoint health and routing delivery/error metrics.
5. Check Service Bus queue active/dead-letter counts and consumer logs.
6. If the route matches yet the queue stays empty, inspect **IoT Hub → Service Bus** RBAC/networking.
7. Fix the exact cause, send a new event, and reconcile `eventId` end-to-end.

**Do not lower thresholds or add catch-all routes** just to make message counts appear, as that can cause false alerts.

## 42. Scenario B: Adding a Storage Route Caused Analytics to Lose Telemetry

**Context:** Previously, Java analytics read from the built-in Event Hubs-compatible endpoint. The team added a custom route to Storage; afterward, dashboards stopped updating while blobs kept appearing.

### Hypothesis

When message routing configuration changes, **default/built-in/fallback behavior** changes too. Messages matching the Storage route are **no longer sent via fallback to the built-in endpoint**, leaving the Java consumer polling with no new messages.

### Investigation Path

1. Snapshot current routes/endpoints/fallback state and check Git/IaC diffs.
2. Check whether an explicit route to the built-in endpoint exists and is enabled.
3. Send a test telemetry event with a known `messageId`.
4. Verify arrival at Storage and the built-in endpoint separately.
5. If fan-out to both is required, add/ensure an explicit route to the built-in endpoint with the needed condition.
6. Check consumer group/offset/retention so "missing route" isn't confused with "consumer reading the wrong offset."
7. Run analytics smoke tests and document the behavior in the change request.

### Lesson

**Fallback handles only unmatched messages** per configuration—it is not an automatic duplicator for all messages. Whenever adding a route, regression-test existing consumers, especially built-in events.

## 43. Scenario C: Service Bus Endpoint Rejects After Enabling Private Access

**Context:** The alert route used to work. Security switched the Service Bus namespace to network-restricted and enabled managed identity on IoT Hub. Afterward, IoT Hub logs routing delivery failures and the queue gets no new messages.

### Why?

- IoT Hub managed identity has not been granted **sender** role at the right scope.
- New role assignment hasn't finished propagating.
- Service Bus network rules block the routing path under the supported mechanism.
- Endpoint configuration still references an old credential/connection string after rotation.
- Hub or endpoint SKU/region lacks support for the desired setup.

### Runbook

1. Inspect route endpoint identity mode and authorization config.
2. Confirm the managed identity of the **exact IoT Hub** is active.
3. Verify data-plane RBAC on the target Service Bus entity/namespace.
4. Verify network support and trusted-services/private-endpoint firewall design.
5. Test one event in a similarly configured sandbox.
6. Restore prior network settings per change plan if causing a production outage.
7. Check retries/retention during the outage window; identify events needing replay from archive.

**Never grant broad Owner/RootManageSharedAccessKey just to clear a 403.** Identify the minimal send permission and valid network path.

## 44. Scenario D: Duplicate Alerts After Java Worker Restart

**Context:** A Java worker pulls from a Service Bus queue, creates an incident in the maintenance system, and restarts before completing the message. The broker redelivers the event and creates a second incident.

### Cause

Service Bus and consumers allow **redelivery** when settlement hasn't completed. IoT Hub routing also does not guarantee exactly-once downstream side effects.

### Fix

- Define an idempotency key from **Hub/deviceId/eventId** or a trusted business event identity.
- Enforce a unique constraint/upsert on incidents in the database.
- Complete the broker message only after verifying the business commit.
- Retry transient errors within bounds; send invalid schemas to DLQ.
- If the worker crashes after DB commit yet before complete, the rerun detects the existing incident.

~~~text
Service Bus eventId=evt-42
    |
    v
Java worker
    |
    +-- INSERT Incident with UNIQUE(eventId)
    +-- If duplicate: treat as already handled
    +-- Commit business transaction
    +-- Complete broker message
~~~

**Counting queue messages alone will not catch duplicate business incidents.** Monitor idempotency conflicts alongside business records.

## 45. Scenario E: Late Telemetry Skews Minute-Level Dashboards

**Context:** A sensor goes offline for 20 minutes and flushes thousands of old samples upon recovery. A Stream Analytics dashboard windows by event time; results arrive late or get dropped depending on the late-arrival policy.

### What to Do

1. Track **device recordedAtUtc**, **IoT Hub enqueued time**, and **processor arrival time**.
2. Inspect firmware clock skew and source time quality.
3. Verify Stream Analytics **`TIMESTAMP BY`** and late/out-of-order policies.
4. Decide how long to accept late events based on business SLOs.
5. Route expired events to an archive/backfill pipeline for reconciliation.
6. Display a dashboard watermark/`lastUpdatedAt` instead of assuming numbers are always final.
7. Separate real-time anomaly alerting from historical data corrections.

### Lesson

A healthy route can still deliver messages to processors **long after measurement time**. **Routing success does not guarantee accurate event-time windows** when devices go offline or have skewed clocks.

## 46. Hands-On Lab: Routing Telemetry in an IoT Hub Sandbox

### Requirements

Design a **Factory Monitoring** setup with:

- A **lab IoT Hub** and two simulated devices: **sensor-lab-a**, **sensor-lab-b**.
- Event JSON containing **schemaVersion, messageId, temperatureC, vibrationMmS, recordedAtUtc**.
- A custom **Event Hubs endpoint** or built-in endpoint for analytics.
- A **Service Bus queue** for telemetry with temperature >80°C.
- A **Storage container** for raw data when budget/permissions allow.
- A **Java consumer/Azure Function** reading the stream or queue and validating records.
- Tests for **matching, non-matching, wrong type, missing headers, and missing endpoint permissions**.

You do not need to provision every resource if the sandbox lacks budget; you can still complete the **design, route matrix, test cases, and runbooks**. Never use a production Hub/queue to inject faults.

### Part A: Designing the Route Matrix

| Route | Source | Condition | Destination | Purpose |
|---|---|---|---|---|
| **all-telemetry** | Device telemetry | true | Event Hubs/built-in | Stream analytics |
| **hot-temperature** | Device telemetry | $body.temperatureC > 80 | Service Bus queue | Alert worker |
| **raw-archive** | Device telemetry | true | Storage | Replay/retention |
| **fallback** | Unmatched custom routes | Per Hub config | Built-in endpoint | Catch unclassified events |

Because **all-telemetry** has condition `true`, fallback may **no longer receive unmatched device telemetry** since at least one route already matches. Explain this clearly—fallback is not a fourth copy of every event.

### Part B: Sending Simulated Messages

Create payloads for four test cases:

~~~json
{"messageId":"lab-001","temperatureC":25,"vibrationMmS":3,"recordedAtUtc":"2026-11-20T10:00:00Z"}
~~~

~~~json
{"messageId":"lab-002","temperatureC":85,"vibrationMmS":12,"recordedAtUtc":"2026-11-20T10:00:10Z"}
~~~

~~~json
{"messageId":"lab-003","temperatureC":"85","vibrationMmS":12,"recordedAtUtc":"2026-11-20T10:00:20Z"}
~~~

~~~json
{"messageId":"lab-004","measurements":{"temperatureC":85},"recordedAtUtc":"2026-11-20T10:00:30Z"}
~~~

Every message can carry **messageType=telemetry** in application properties. For body queries to work, set **contentType=application/json** and **contentEncoding=utf-8** via the SDK.

### Part C: Testing Routing

1. For **lab-001**, verify **analytics + archive**, not the high-temperature queue.
2. For **lab-002**, verify **analytics + archive + alert queue**.
3. For **lab-003**, verify string types are not assumed to evaluate as numbers; record actual routing query engine behavior rather than treating type coercion as a contract.
4. For **lab-004**, old queries checking root `temperatureC` miss the nested value; schema versioning is needed.
5. Send a copy of **lab-002** without JSON content headers to observe body conditions failing to evaluate.
6. Test a missing endpoint role/permission **in sandbox only**; verify metrics/error handling.
7. Verify the Java consumer or Function actually processes and persists the event.
8. Resend duplicate **lab-002** to test idempotency—no duplicate incident created.

### Part D: End-to-End Measurements

| Metric | How to Record |
|---|---|
| Device send acknowledgment | Callback status and timestamp |
| IoT Hub ingress | Matching metric/receipt timestamp |
| Route matched | Route test or routing metrics/logs |
| Endpoint delivery | Message count/ID, errors |
| Processor execution | Invocation ID, retry count |
| Business result | Incident ID or aggregate record |
| End-to-end latency | Processed time minus ingested/event time per definition |
| Duplicate count | Number of idempotency conflicts |
| Cost estimate | Message rate, Hub/endpoint/compute/storage |

Do not treat device timestamps as strictly authoritative for end-to-end latency; use IoT Hub enqueued time as a complementary measurement.

### Part E: Safe Fault Injection Testing

Only in an **authorized lab**:

- Stop the Java consumer for a few minutes and restart; observe backlog/retention.
- Feed the parser JSON missing `schemaVersion`; expect error handling/DLQ.
- Send 2 events with identical `eventId`; expect no duplicate business side effect.
- Temporarily point to a test endpoint with intentionally missing IAM; verify route delivery errors.
- Simulate a device sending delayed timestamps; observe Stream Analytics behavior.

Never disable firewalls, revoke roles, or delete production endpoints to simulate faults. If an action could affect another team in a shared resource, replace it with a mock/tabletop exercise.

### Part F: Evidence to Submit

~~~text
Hub (sandbox): ...
Subscription/resource group/region: ...
Device IDs (no credentials): ...
Route names/source/query/endpoint: ...
Fallback status: ...
JSON schema + message headers: ...
Matching and nonmatching test IDs: ...
Consumer app/SDK version: ...
Message ingress/delivery/process counts: ...
Retry/idempotency result: ...
Monitoring dashboard and alert rules: ...
Cost estimate and cleanup: ...
Secrets in report: NONE
~~~

### Part G: Cleanup

- Delete only test devices, routes, endpoints, or resources **created specifically for the lab** and owned by you.
- Never delete shared IoT Hubs/resource groups or production routes.
- Revoke/rotate lab credentials per procedure.
- Purge blobs/queue messages/test data per approved retention.
- Verify billable resources (Hub, Event Hubs, Storage, Service Bus, Stream Analytics, logs) are stopped/cleaned up when appropriate.
- Verify billable resources (Hub, Event Hubs, Storage, Service Bus, Stream Analytics, logs) are stopped/cleaned up when appropriate.

## 47. Production Design and Operations Checklist

- [ ] Clearly identified **message source** as D2C telemetry, distinct from C2D/twin/Edge events.
- [ ] Route matrix mapped from use cases: alerting, real-time analytics, historical archiving.
- [ ] Decided **built-in vs. custom Event Hubs** with consumer groups and retention.
- [ ] Selected **Service Bus queue vs. topic** based on consumer counts and retry/DLQ policies.
- [ ] Storage archive has clear encoding, file partitioning, retention, and replay capability.
- [ ] Cosmos DB endpoint/processor has partition key, indexing, TTL, and RU budget if used.
- [ ] Device SDK sets `contentType=application/json` and `contentEncoding=utf-8` when routes inspect JSON bodies.
- [ ] Routing queries tested for **matching, nonmatching, missing, null, and wrong types**.
- [ ] Route conditions verified against actual `schemaVersion` and firmware versions.
- [ ] Multiple matching routes do not cause unintended double alerts.
- [ ] Fallback route and built-in events path regression-tested after every change.
- [ ] Never use **device-supplied tenantId/site** as authorization proof.
- [ ] Device-level identities/certificates/SAS protected; no owner keys in firmware.
- [ ] Hub → custom endpoints use managed identities/credentials and minimal data-plane RBAC.
- [ ] Java consumers use dedicated identities/permissions, never IoT Hub's send identity.
- [ ] Networking and private connectivity verified independently per hop.
- [ ] `eventId`/sequence, deduplication, and business idempotency in place.
- [ ] Java Functions/workers handle retries, checkpoints/settlement, DLQs, and graceful shutdown.
- [ ] Event time vs. enqueue time and late/out-of-order policies defined.
- [ ] Monitoring covers device ingress through routing delivery to business sinks.
- [ ] Alert rules have owners, runbooks, and avoid false positives on low-traffic routes.
- [ ] Archive/replay and recovery tested within retention windows.
- [ ] IaC/source-of-truth, change reviews, rollbacks, and staging environments in place.
- [ ] Capacity plans cover peaks/offline replays and message sizes, not averages alone.
- [ ] Tags/budgets, full-pipeline estimates, and lab cleanup plans defined.
- [ ] No credentials, raw PII, or private payloads in Git or logs.

## 48. Self-Check Questions

1. How does IoT Hub D2C telemetry differ from cloud-to-device messages and device twins?
2. What core fields make up an IoT Hub route?
3. Why can't IoT Hub routing compute minute-level AVG on its own?
4. When should you use the built-in Event Hubs-compatible endpoint vs. custom Event Hubs?
5. If two routes match the same telemetry message, what happens?
6. When is the fallback route used? Is it a dead-letter queue?
7. Why can adding a Storage route affect a built-in endpoint consumer?
8. How do application-property filters differ from JSON body filters?
9. To use `$body.temperatureC`, how must the device set `contentType` and `contentEncoding`?
10. If `temperatureC` is a string yet the query compares numbers, what should be checked?
11. Can a device-supplied `tenantId` in the body be trusted for authorization?
12. How is the IoT Hub system property for device connection identity useful?
13. When choose a Service Bus queue over Event Hubs?
14. How does a Service Bus topic fit multi-subscriber scenarios?
15. Why don't Event Hubs messages disappear when a consumer reads them?
16. What problems do consumer groups and checkpoints solve?
17. Why isn't a Storage route suitable for alerts needing sub-second or few-second latency?
18. When storing telemetry in Cosmos DB, which partitioning/indexing decisions matter?
19. Why place a Function/Java processor in front of Cosmos DB in some use cases?
20. Are Event Grid subscriptions and IoT Hub custom routing endpoints the same list?
21. How does IoT Edge offline processing differ from IoT Hub cloud routing?
22. Why doesn't send acknowledgment prove data was written to the database?
23. Which fields can deduplicate a reading on worker retry?
24. When a processor crashes after DB commit yet before broker complete, how do you prevent duplicate incidents?
25. How do event time, enqueued time, and processing time differ?
26. If route delivery fails with 403, whose roles and networking must be checked?
27. Must IoT Hub's managed identity and the Java consumer's managed identity be the same principal?
28. Does a consumer's Private Endpoint automatically allow IoT Hub to send to Service Bus?
29. Why can 429s still happen even after adding Hub units if the database is the bottleneck?
30. When should poison/invalid messages go to DLQ, and who owns handling them?
31. How does an archive help once Event Hubs retention expires?
32. What must be tested before switching from JSON v1 to v2?
33. Why do a `true`-condition route and the fallback route interact specifically?
34. Can IoT Hub message routing directly issue machine-shutdown commands on a temperature threshold?
35. Which metrics prove a telemetry reading traveled from sensor to business alert?
36. How does a factory with thousands of devices simultaneously replaying backlogs affect capacity?
37. What review/rollback steps should an IaC deployment changing route conditions include?
38. Why shouldn't device connection strings or full location payloads be logged?
39. When should alerts evaluate event time vs. enqueue time?
40. Given alerting, analytics, and archival requirements, which endpoints would you choose and why?

## 49. References

- [Azure IoT Hub documentation](https://learn.microsoft.com/azure/iot-hub/) — IoT Hub overview, device management, messaging, and routing.
- [IoT Hub device-to-cloud communication guidance](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-messages-d2c) — D2C messages and cloud flows.
- [IoT Hub message routing](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-messages-d2c#message-routing) — messages to endpoints, routing/fallback concepts.
- [IoT Hub message routing query syntax](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-routing-query-syntax) — sources, body/properties, and query conditions.
- [IoT Hub message enrichments](https://learn.microsoft.com/azure/iot-hub/iot-hub-message-enrichments-overview) — stamping metadata onto routed messages.
- [IoT Hub quotas and throttling](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-quotas-throttling) — service limits and capacity.
- [Monitor Azure IoT Hub](https://learn.microsoft.com/azure/iot-hub/monitor-iot-hub) — Azure Monitor metrics/diagnostics.
- [Azure Event Hubs overview](https://learn.microsoft.com/azure/event-hubs/event-hubs-about) — partitioned streaming/event ingestion.
- [Azure Service Bus overview](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview) — queues/topics and durable messaging.
- [Azure Storage Blob overview](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-overview) — archiving/retention/data lake.
- [Azure Cosmos DB for NoSQL overview](https://learn.microsoft.com/azure/cosmos-db/nosql/overview) — NoSQL target, partitions, RUs.
- [Azure Functions Event Hubs trigger](https://learn.microsoft.com/azure/azure-functions/functions-bindings-event-hubs-trigger) — event-processing functions.
- [Azure Functions Service Bus trigger](https://learn.microsoft.com/azure/azure-functions/functions-bindings-service-bus-trigger) — message processors for queues/topics.
- [Azure Stream Analytics overview](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-introduction) — event-time windows, transformations, and sinks.
- [Azure Event Grid overview](https://learn.microsoft.com/azure/event-grid/overview) — event subscription model.
- [Azure IoT Edge documentation](https://learn.microsoft.com/azure/iot-edge/) — edge processing and cloud connectivity.
- [Azure IoT SDKs](https://learn.microsoft.com/azure/iot-hub/iot-hub-devguide-sdks) — device and service SDKs, versions.
- [Azure CLI IoT Hub reference](https://learn.microsoft.com/cli/azure/iot/hub) — inspecting Hub metadata, route commands/extensions.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating IoT Hub and downstream services.

**Conclusion:** Routing telemetry from Azure IoT Hub is an IoT data-infrastructure design step, not merely filling in a filter expression. Define **message sources, metadata and schemas, route conditions, built-in/custom endpoints, fallback behavior, and consumer ownership** clearly. Use **Event Hubs** for streaming, **Service Bus** for jobs and alerts needing retries/DLQ, **Storage** for archiving/replay, and **Cosmos DB** for operational state queries where appropriate. Ensure **per-hop identities and permissions, JSON headers, idempotency, late-data handling, monitoring, testing, and cost controls** before going to production. A trustworthy pipeline is one where you can explain **where every message was ingested, routed, processed, and recorded**, even when an endpoint suffers an outage.
