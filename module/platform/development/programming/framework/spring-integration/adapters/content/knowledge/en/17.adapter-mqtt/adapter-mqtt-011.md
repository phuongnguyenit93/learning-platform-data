# Handling duplicate messages by QoS

## 1. Why can an MQTT message be processed multiple times?

A temperature sensor publishes `{"eventId":"evt-1001","celsius":26.5}` to MQTT at QoS 1. The broker receives the data, yet the `PUBACK` packet is lost on the return trip. The MQTT client does not know whether the broker received it, so protocol mechanics can trigger retransmission of the PUBLISH. Consequently, the Spring Integration backend may observe **two deliveries** for the same business event. If every delivery increments a counter, bills a customer, sends an email, or actuates a device, the outcome is wrong.

This lesson, **"Handling duplicate messages by QoS,"** sits in the **Adapter MQTT** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module focuses on integrating external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; and managing message contracts, errors, and connection lifecycles. In MQTT, **duplicate deliveries** are where protocol guarantees meet data consistency constraints and business side effects.

After this lesson, learners will be able to:

1. State the exact meaning of **QoS 0, 1, 2** and the acknowledgment scope of each QoS.
2. Distinguish **retransmitted MQTT packets**, **re-delivered retained snapshots**, **application re-publishes**, and **two valid events that happen to carry identical values**.
3. Understand the limits of the **DUP flag**, MQTT packet identifiers, client sessions, and Paho delivery tokens.
4. Design **business event IDs** that stay stable across reconnects/retries and are scoped by tenant/device.
5. Apply **deduplication/idempotency** using unique constraints and a shared database transaction alongside side effects.
6. Build an MQTT inbound adapter, `MessageChannel`, and `IntegrationFlow` that parses/validates events and invokes a deduplicating processor.
7. Distinguish MQTT acknowledgments from transaction commits, error handling, optional manual ACKs, and poison messages.
8. Test brokerless flows, DB concurrency, and MQTT brokers with simulated network faults.
9. Coordinate duplicates when bridging MQTT to HTTP, JMS/AMQP, Kafka, databases, or files/SFTP.

**Foundational rule:** MQTT QoS describes delivering an **MQTT publication** within protocol scope. It does not by default guarantee that **one business event causes only one side effect** in Spring Integration or target systems.

## 2. Three "once" layers that are often conflated

~~~mermaid
flowchart LR
    PUB["Publisher / device<br/>business event evt-1001"]
    BROKER[("MQTT broker")]
    IN["Spring MQTT inbound adapter"]
    CH["MessageChannel"]
    GUARD["Idempotency guard<br/>tenantId + eventId"]
    DB[("Database + business effect")]
    OUT["HTTP / JMS / Kafka / SFTP"]
    PUB -->|"MQTT PUBLISH QoS 1"| BROKER
    BROKER -->|"May redeliver"| IN
    IN --> CH --> GUARD --> DB
    DB -->|"If needed, via outbox"| OUT
~~~

Distinguish three questions:

| Question | Relevant mechanism | Where to verify |
| --- | --- | --- |
| Did the MQTT client/broker finish delivering a packet? | MQTT QoS, packet identifier, ACK/handshake. | Protocol/client/broker metrics and logs. |
| Did Spring Integration receive the callback and dispatch the message into the flow? | MQTT inbound adapter, converter, `MessageChannel`, error channel. | App logs, metrics, integration tests. |
| Did a business event produce its side effect **exactly once**? | Event ID, database uniqueness, transactions, idempotent consumer/outbox. | Database and target systems, including crash/retry scenarios. |

For example, QoS 2 suppresses protocol duplicates for **a single publication**, yet if a business service calls publish twice with the same command ID, the broker sees **two independent publications**. The receiver still must recognize duplicate commands by business ID.

### 2.1. "Duplicate message" has multiple meanings

- **Transport duplicate:** a PUBLISH belonging to the same protocol exchange retransmitted due to QoS ACKs or lifecycle state.
- **Application duplicate:** a producer/outbox/worker re-emits the same event with the same business intent.
- **Replay:** a message held in a queue, session, retained store, or archive re-delivered after a subscribe/restart.
- **Duplicate side effect:** business data or actions recorded/executed multiple times; this is what must be prevented.
- **Legitimate matching content:** two sensor readings both reporting `26.5` with different event IDs can be **two valid distinct readings**.

Never use `payload.equals(...)` to conclude two events are duplicates: a device can report a constant temperature every minute where every sample is legitimate.

## 3. QoS 0: at most once for a single MQTT PUBLISH

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    participant S as Subscriber
    P->>B: PUBLISH QoS 0
    B->>S: PUBLISH QoS 0 (if subscription matches)
    Note over P,B: No PUBACK for QoS 0
~~~

At QoS 0, the sender performs no PUBLISH acknowledgment handshake; broker/client may drop messages on network errors. The protocol **provides no guaranteed-delivery retransmission** like QoS 1/2.

**QoS 0 does not mean business events cannot duplicate.** For example:

1. A device samples reading `evt-1001`.
2. It publishes at QoS 0.
3. The device app does not know whether the broker received it, so it initiates a **new** publish call.
4. The backend receives two independent PUBLISHes with the same `eventId`.

Both publications can be QoS 0 and still cause a business duplicate. Hence an idempotent processor is valuable even for QoS 0 sources whenever out-of-protocol retries or replays exist.

### 3.1. When to use QoS 0

QoS 0 fits high-rate telemetry that can be re-sampled or where losing occasional samples is acceptable. It does not satisfy "never lose any payment command" through QoS 0 configuration alone. Critical data requires persistence and retry policies in the application/broker.

## 4. QoS 1: at least once and DUP can appear

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    participant S as Spring subscriber
    P->>B: PUBLISH QoS 1, packetId=57, DUP=0
    B->>S: PUBLISH eventId=evt-1001
    B--xP: PUBACK lost
    Note over P: Uncertain outcome
    P->>B: PUBLISH retry, packetId=57, DUP=1
    B->>S: PUBLISH may cause app to see evt-1001 again
    B-->>P: PUBACK packetId=57
~~~

This diagram shows an illustrative scenario. Whether the broker forwards redeliveries to the subscriber, how session/packet state is kept, and retry timing depend on protocol, client, broker, and connection state; **do not assume every QoS 1 retry yields exactly two callbacks**. Still, systems using QoS 1 must tolerate receiving duplicates.

QoS 1 uses `PUBLISH → PUBACK`. When a publisher has not received PUBACK, it may not know whether the broker processed the message. Similarly, broker → subscriber is its own QoS/ACK leg, so duplicates can appear at the receiver even when the publisher saw no error.

### 4.1. At least once does not mean "always duplicated"

A normal QoS 1 PUBLISH typically arrives once. **Duplication is a possibility**, not a guarantee that the system redelivers every message. Design deduplication for critical business data before an incident hits—do not wait until logs show a DUP flag.

### 4.2. Publisher and subscriber QoS can differ

If a publisher sends at QoS 1 while a subscriber registers a filter at QoS 0, the broker → subscriber leg can be delivered at QoS 0. You cannot inspect publisher QoS alone and assert subscriber delivery QoS. Moreover, overlapping subscriptions and broker policies can generate additional deliveries; test your actual topology.

## 5. QoS 2: exactly once **at the protocol layer**, not in the database

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant B as Broker
    P->>B: PUBLISH QoS 2, packetId=57
    B-->>P: PUBREC
    P->>B: PUBREL
    B-->>P: PUBCOMP
    Note over P,B: One MQTT QoS 2 publication completes handshake
~~~

QoS 2 provides once-only delivery mechanics for **one publication** within an MQTT session/handshake. Yet it shares no transaction with a Spring handler, PostgreSQL, file/SFTP, or a REST API.

Example:

~~~text
Publisher calls PUBLISH(commandId=cmd-1001, QoS 2)
→ handshake completes.

Publisher process crashes before recording sent status in DB.
→ Outbox worker restarts and issues a new PUBLISH
  with commandId=cmd-1001, QoS 2.
→ Broker sees two distinct PUBLISH operations.
→ Device still must check commandId before turning on.
~~~

Thus QoS 2 **does not replace** idempotency. It also adds control packets and protocol state compared to QoS 1, so choose it based on SLA, broker/client support, and real benchmarks.

### 5.1. Comparison matrix

| QoS | Meaning at MQTT layer | Can messages be lost? | Can business duplicates occur? |
| ---: | --- | --- | --- |
| 0 | At most once, no broker PUBACK. | Yes. | Yes, if producer/application re-issues PUBLISH. |
| 1 | At least once, with `PUBACK`. | Protocol aims for ACKed delivery; still depends on storage, session, connection, and application. | **Yes**, via retransmission, retries, and multiple sources. |
| 2 | Exactly once for one MQTT publication/handshake. | Governed by session/broker persistence and lifecycle; no absolute business transaction guarantee. | **Yes**, if multiple PUBLISHes are created for one event or replayed outside protocol. |

**Never state "QoS 2 = exactly-once processing across all target systems."** The guarantee covers only the protocol exchange under protocol conditions, not Spring side effects.

## 6. Sources of duplicates: not just MQTT retransmission

| Source | Example scenario | Protection mechanism |
| --- | --- | --- |
| QoS 1 retransmission | PUBACK lost; packet is re-sent. | Event ID + idempotent handler. |
| Session recovery/offline backlog | Subscriber reconnects and re-receives in-flight PUBLISHes. | Deduplication durable across restarts. |
| Application publisher retry | HTTP/outbox worker times out and creates a new PUBLISH. | Stable event ID across retries. |
| Multi-broker bridge | Same event crosses two bridge paths. | Source ID + namespace/tenant; loop prevention. |
| Overlapping subscriptions | `sensors/#` and `sensors/+/temperature` both match. | Avoid unnecessary overlaps; deduplicate. |
| Retained snapshot | New subscription receives retained state again. | Separate snapshots from events; versioning/freshness. |
| Processing retry | DB or handler throws; message/inbox is replayed. | Transaction + unique key. |
| Multiple app instances | Two consumers receive the same event on separate subscriptions. | Shared unique constraint in DB. |
| HTTP retry before MQTT | Client sends two HTTP requests for the same business action. | Idempotency key right at the API. |
| Device reconnect/reboot | Device re-sends a telemetry batch unsure if recorded. | Event ID persisted on device/buffer. |

### 6.1. Messages with identical payloads are not necessarily duplicates

~~~json
{"eventId":"evt-1001","deviceId":"device-17","celsius":26.5}
~~~

~~~json
{"eventId":"evt-1002","deviceId":"device-17","celsius":26.5}
~~~

Two records with identical temperatures yet different event IDs can be two legitimate readings at different times. Using payload hashes as the sole deduplication key would wrongly discard valid readings.

### 6.2. Same event ID with different content is also an error

~~~text
evt-1001 → celsius=26.5
evt-1001 → celsius=99.9
~~~

This is an **idempotency key collision or producer contract violation**, not a benign duplicate to ignore silently. When keeping event IDs fixed across retries, producers must preserve **business meaning and payload per contract**; consumers can store a hash/version to detect ID reuse with altered content.

## 7. The DUP flag: a protocol signal, not a deduplication key

MQTT PUBLISH carries a **DUP** flag in its fixed header. It is used during MQTT protocol retransmissions. However:

- `DUP=1` is not a business ID; it only states an MQTT PUBLISH is being re-sent under protocol semantics, not that a consumer already processed the payload earlier.
- `DUP=0` does not mean the business event is new: two independent PUBLISHes sharing `eventId` can both start with `DUP=0`.
- Broker receipt from a publisher and delivery to a subscriber are **two separate legs**; never assume a publisher-side DUP flag passes verbatim into a downstream header.
- Spring Integration MQTT converters/versions may expose DUP/retained/QoS metadata via different headers; check your exact API instead of basing deduplication solely on an uncertain header.

### 7.1. Why skipping messages using the DUP flag is wrong

~~~text
if (mqttDupFlag) {
    return; // WRONG if relying on this to skip the message
}
~~~

A PUBLISH carrying `DUP=1` may be the **very first time** your application actually sees the message, because the initial delivery never reached the subscriber. Dropping all `DUP=1` messages loses data.

Conversely, `DUP=0` can still share a business ID with an earlier publication. **Check persisted business identity**, not merely packet flags.

## 8. Packet identifiers and delivery tokens are not business IDs either

An MQTT packet identifier is scoped to one client connection/session and is reused after its protocol exchange finishes. Paho's `IMqttDeliveryToken` tracks a runtime client publish operation; tokens are not serialized as durable keys across restarts.

| Value | Proper use | Wrong use |
| --- | --- | --- |
| MQTT packet ID | Diagnosing handshakes/ACKs in protocol context. | Global primary key for telemetry/business events. |
| Paho delivery token | Observing publish operations/timeouts. | Identifying business messages across consumers. |
| Spring `MessageHeaders.ID` | Tracing a Spring message instance. | Deduplicating MQTT replays if newly generated during conversion. |
| `MqttHeaders.RECEIVED_TOPIC` | Validating actual topic and parsing tenant/device. | Replacing per-PUBLISH event IDs. |
| Producer `eventId` | Identifying business events across retries. | Blindly trusting without validating source/tenant and payload consistency. |

### 8.1. Designing a durable eventId

A telemetry event should carry an ID assigned by the producer **when the event is created** and kept unchanged across every attempt:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-device17-000001",
  "tenantId": "tenant-a",
  "deviceId": "device-17",
  "sequence": 1001,
  "celsius": 26.5
}
~~~

If a device reboots, never reset counters in a way that reuses old IDs for new events. Use UUIDs/ULIDs or `deviceId + bootEpoch + sequence`; ensure uniqueness within the namespace, managing clocks and persistence. A bare timestamp is insufficient if clocks skew or two events occur within the same millisecond.

## 9. Retained, sessions, and resubscribing: why re-reading is not always an error

MQTT 3.1.1 supports **retained messages** and **persistent sessions**. These are separate mechanisms:

| Mechanism | What the broker stores | Impact on consumer |
| --- | --- | --- |
| Retained | Latest PUBLISH snapshot per topic per policy. | New subscribers may receive the snapshot immediately on subscribing. |
| `cleanSession=false` | Subscriptions/session and related QoS 1/2 messages per protocol/broker policy. | Subscribers may receive pending/offline messages upon reconnecting. |
| QoS 1 in-flight | Protocol tracking of unfinished PUBLISH/PUBACK exchanges. | Redeliveries can occur. |
| Application outbox/inbox | Business records persisted by the app itself. | Application can reconcile/retry/skip duplicates across restarts. |

Never treat a retained `ONLINE` delivered upon subscribing as a "device just came online right now" event. It is a **broker snapshot**. To maintain a duplicate-free event log, define distinct schemas, freshness checks, and retained-handling rules.

### 9.1. QoS and overlapping subscription filters

One subscriber can register:

~~~text
sensors/#
sensors/+/temperature
~~~

A single PUBLISH to `sensors/device-17/temperature` matches both. Under MQTT 3.1.1, the broker may deliver separate copies when matching subscriptions overlap. Therefore, even if a publisher only publishes once, consumers must be ready for duplicates.

### 9.2. Multi-instance and Client IDs

Two app instances with **different Client IDs** subscribing to the same normal filter **both** receive events: per-subscriber fan-out, not a competing queue. They can write duplicates into the same DB unless guarded by a unique constraint.

Two active clients **sharing the same Client ID** kick each other's connections off; that is **not** a load-balancing technique. If your broker supports shared subscriptions, use them per version/broker ACLs, while still keeping idempotency because side effects can retry or applications can re-publish.

## 10. Start from the business contract: choosing an idempotency key

A sound key answers: "Is this the same **business event** as before?"—not "Are the bytes identical?". In a multi-tenant environment, for example:

~~~text
Idempotency key = (tenantId, eventId)
Topic namespace  = tenants/{tenantId}/devices/{deviceId}/temperature
Business contract = eventId remains stable across all retries of the same reading
~~~

If devices only guarantee `eventId` uniqueness per device, widen the key to `(tenantId, deviceId, eventId)`. Scope the key precisely to the producer's actual guarantee—never assume a short ID is globally unique across the entire company.

### 10.1. Do not use payload hash as the primary ID

Two readings with identical bytes can be two valid measurements. Payload hashes are useful to **detect collisions** when the same `eventId` arrives with different content, not to replace source IDs. If an application lacks an event ID, add one to the schema/producer; heuristics like topic + timestamp + hash risk dropping valid events or missing retries.

### 10.2. Why verify topic and identity before deduplicating?

An untrusted publisher could send a message with another device's `eventId` and trick the processor into ignoring real data from the legitimate device. Authenticate the broker principal/topic ACL and cross-check `tenantId` and `deviceId` from the topic against payload/owner before applying the idempotency key.

### 10.3. Deduplication window is a business decision

Keeping all event IDs forever causes unbounded DB growth. Yet if TTL is 24 hours while an outbox can replay a 7-day-old event, duplicates can re-trigger side effects. Choose retention based on:

- Maximum replay horizon in publishers/outboxes.
- Broker session/backlog/retained behavior.
- Backfill, reprocessing, and incident recovery policies.
- SLAs and side-effect risk (payments, device actuation).
- Feasibility of compacted event IDs and snapshots.

**Never purge idempotency records sooner than the same business event can return** if business rules demand long-term "once-only" effects. For historical data, use partitioning/archival and dedicated reconciliation policies.

## 11. Durable deduplication mechanism: unique constraint and single transaction

A simple yet effective pattern with PostgreSQL:

~~~mermaid
sequenceDiagram
    participant IN as Spring inbound flow
    participant DB as PostgreSQL
    IN->>DB: BEGIN
    IN->>DB: INSERT (tenantId,eventId) ON CONFLICT DO NOTHING
    alt New ID
        DB-->>IN: inserted=1
        IN->>DB: INSERT business reading
        IN->>DB: COMMIT
    else Existing ID
        DB-->>IN: inserted=0
        IN->>DB: Compare payload hash / owner
        IN->>DB: COMMIT without creating new side effect
    end
~~~

### 11.1. Illustrative PostgreSQL schema

~~~sql
CREATE TABLE IF NOT EXISTS processed_mqtt_events (
    tenant_id       VARCHAR(64) NOT NULL,
    event_id        VARCHAR(128) NOT NULL,
    device_id       VARCHAR(64) NOT NULL,
    payload_sha256  CHAR(64) NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id)
);

CREATE TABLE IF NOT EXISTS telemetry_readings (
    tenant_id       VARCHAR(64) NOT NULL,
    event_id        VARCHAR(128) NOT NULL,
    device_id       VARCHAR(64) NOT NULL,
    sequence_no     BIGINT NOT NULL,
    celsius         NUMERIC(8, 2) NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device
    ON telemetry_readings(tenant_id, device_id, sequence_no);
~~~

`processed_mqtt_events` serves as the **idempotency ledger**. `telemetry_readings` holds the business side-effect measurements. The `(tenant_id, event_id)` primary key prevents two concurrent threads/instances from committing two entries for the same key.

Inside the transaction, the application executes:

~~~sql
INSERT INTO processed_mqtt_events
    (tenant_id, event_id, device_id, payload_sha256)
VALUES
    ('tenant-a', 'evt-1001', 'device-17', 'example-hash')
ON CONFLICT (tenant_id, event_id) DO NOTHING;
~~~

Without conflict, the insert returns **1 row affected**, and the side effect executes inside **the same transaction**. If it already exists, the insert returns **0**, skips creating a side effect, and can verify the prior event's hash.

**Important:** `example-hash` is only a placeholder in illustrative SQL; the Java processor below computes a real SHA-256 hex digest. Never use a hardcoded hash in production.

### 11.2. Why is "SELECT then INSERT" insufficient?

Common mistake:

~~~text
Thread A: SELECT eventId=evt-1001 → not found
Thread B: SELECT eventId=evt-1001 → not found
Thread A: UPDATE business counter +1
Thread B: UPDATE business counter +1
Thread A/B: INSERT event ID
~~~

Both threads see "not found" before either inserts. Without a unique constraint and transaction, the counter increments twice.

The `INSERT ... ON CONFLICT DO NOTHING` pattern lets the database arbitrate races. Never replace it with a `ConcurrentHashMap` when running multiple JVM instances or needing persistence across restarts.

### 11.3. Atomicity requirements and limits

If inserting the idempotency key commits **before** writing the business reading in a separate transaction, and the business write then fails, subsequent replays get blocked even though the side effect never occurred. Therefore, **the idempotency record and DB business write must commit or roll back together**.

If side effects go **outside** that database (HTTP, Kafka, email, device commands), a PostgreSQL transaction cannot commit atomically with external systems. Use a transactional outbox for outbound emission paired with an **idempotent consumer** at the target, or appropriate reconciliation/fencing protocols.

### 11.4. What is the hash for?

Hashing raw bytes detects a producer reusing an `eventId` for different content. Under a strict contract, the same key with a different payload SHA-256 goes to quarantine/audit.

However, if a producer can vary serialization of the same event (different JSON whitespace), raw hashes can differ even when business fields are unchanged. Define a **canonical representation** or compare a normalized business fingerprint rather than prematurely treating it as an attack. For simplicity, this lesson adopts the policy that **retries must preserve raw payload bytes**.

## 12. Spring Integration architecture for inbound idempotency

~~~mermaid
flowchart LR
    DEV["Device / publisher"]
    B[("MQTT broker")]
    AD["MqttPahoMessageDrivenChannelAdapter<br/>QoS=1"]
    RAW["DefaultPahoMessageConverter<br/>payloadAsBytes=true"]
    CH["mqtt.telemetry.raw"]
    FLOW["IntegrationFlow<br/>validate topic + JSON"]
    SVC["TelemetryProcessor<br/>@Transactional"]
    LEDGER[("processed_mqtt_events")]
    READ[("telemetry_readings")]
    ERR["Error/quarantine"]
    DEV --> B --> AD --> RAW --> CH --> FLOW --> SVC
    SVC --> LEDGER
    SVC --> READ
    FLOW -. "invalid bytes/schema/topic" .-> ERR
    SVC -. "DB unavailable" .-> ERR
~~~

**Separation of responsibilities:**

1. MQTT broker and Paho manage subscriptions, delivery, and QoS.
2. `MqttPahoMessageDrivenChannelAdapter` turns PUBLISHes into Spring `Message<byte[]>`.
3. Spring `MessageChannel` delivers messages to `IntegrationFlow`.
4. The flow checks the **received topic**, parses JSON, and cross-checks tenant/device IDs.
5. `TelemetryProcessor` owns the database transaction, deduplication key, and business write.
6. Deterministic errors go to quarantine; transient DB failures require durable retry/replay policies per SLA.
7. If downstream systems beyond the DB need events, write an outbox row in the same DB transaction.

Do not add a `@Poller` to poll the MQTT broker: the inbound adapter is **message-driven**. Only if you insert an internal Spring `QueueChannel` does the downstream consumer need a poller to drain that queue.

### 12.1. Why preserve raw bytes?

An MQTT payload can be UTF-8 JSON, protobuf, or another binary format. Configuring the converter with `setPayloadAsBytes(true)` lets us:

- Check byte length before parsing.
- Compute the payload hash over the **exact received bytes**.
- Avoid a text decode/re-encode pass that could mutate bytes.
- Store raw bytes in quarantine under security policies when schemas fail.

Jackson parses JSON directly from `byte[]`. MQTT topic names and QoS/retained metadata still live in headers/transport metadata, not broker-generated JSON.

## 13. Complete Spring Boot example: receiving MQTT and deduplicating with PostgreSQL

**Context:** `tenant-a` has multiple sensors publishing to:

~~~text
tenants/tenant-a/devices/device-17/temperature
tenants/tenant-a/devices/device-21/temperature
~~~

Backend subscription filter:

~~~text
tenants/tenant-a/devices/+/temperature
~~~

Agreed JSON payload:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-device17-000001",
  "tenantId": "tenant-a",
  "deviceId": "device-17",
  "sequence": 1001,
  "celsius": 26.5
}
~~~

Receiving the same `eventId` and payload twice must **insert at most one row** in `telemetry_readings`. If the same ID arrives with different content, the processor throws a **collision** error per contract. If a publisher sends two events with different IDs and the same `celsius`, both readings are stored.

Examples use Java 17+, Spring Boot, Spring Integration MQTT/Paho MQTT v3, Jackson, Spring JDBC, and PostgreSQL. H2/in-memory DBs have different upsert/locking syntax, so **do not** assume PostgreSQL SQL runs unchanged on every database.

### 13.1. Maven dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-mqtt</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Use a compatible Spring Boot BOM to align versions. The MQTT broker and PostgreSQL must be **started separately** with proper credentials/permissions; Spring Boot does not start a broker. Never run demo SQL against production databases without approved schemas and migrations.

### 13.2. Code structure

~~~text
src/main/java/demo/mqttdedup/
    MqttDedupApplication.java
    TelemetryEvent.java
    DedupOutcome.java
    TelemetryProcessor.java
    JdbcTelemetryProcessor.java
    MqttDedupTransportConfiguration.java
    MqttDedupFlowConfiguration.java

src/main/resources/
    application.properties
    schema.sql

src/test/java/demo/mqttdedup/
    MqttDedupFlowTest.java
~~~

All classes belong to package `demo.mqttdedup`. Public classes must reside in matching filenames; helpers can stay package-private for direct testing.

### 13.3. Spring Boot application

~~~java
package demo.mqttdedup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MqttDedupApplication {

    public static void main(String[] args) {
        SpringApplication.run(MqttDedupApplication.class, args);
    }
}
~~~

### 13.4. application.properties

~~~properties
app.mqtt.broker-url=${MQTT_BROKER_URL:tcp://localhost:1883}
app.mqtt.client-id=${MQTT_CLIENT_ID:tenant-a-telemetry-local-1}
app.mqtt.tenant-id=tenant-a

spring.datasource.url=${DB_URL:jdbc:postgresql://localhost:5432/mqtt_lab}
spring.datasource.username=${DB_USER:mqtt_demo}
spring.datasource.password=${DB_PASSWORD}

# Only for lab environments with a reviewed schema.sql.
spring.sql.init.mode=always
~~~

In production, use a migration tool/schema governance instead of letting multiple replicas run schema initialization concurrently, and supply secrets from secure config infrastructure. External brokers should use TLS, broker cert verification, and ACLs instead of plaintext TCP.

`schema.sql` holds the PostgreSQL DDL from section 11. With `spring.sql.init.mode=always`, Spring Boot runs the script at startup per initialization policy; the lab DB user needs DDL privileges. In production, separate migration privileges from the runtime user.

### 13.5. Business DTO

~~~java
package demo.mqttdedup;

import java.math.BigDecimal;

record TelemetryEvent(
        int schemaVersion,
        String eventId,
        String tenantId,
        String deviceId,
        long sequence,
        BigDecimal celsius) {

    TelemetryEvent {
        if (schemaVersion != 1) {
            throw new IllegalArgumentException(
                    "Unsupported schema version");
        }
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,128}")) {
            throw new IllegalArgumentException("Invalid eventId");
        }
        if (tenantId == null
                || !tenantId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid deviceId");
        }
        if (sequence < 0) {
            throw new IllegalArgumentException("Negative sequence");
        }
        if (celsius == null
                || celsius.compareTo(new BigDecimal("-80")) < 0
                || celsius.compareTo(new BigDecimal("150")) > 0) {
            throw new IllegalArgumentException(
                    "Invalid temperature");
        }
    }
}
~~~

The `-80..150` range and ID patterns are **illustrative business constraints**, not MQTT rules. If firmware emits a different schema, use a versioned decoder/contract rather than simply widening wildcard subscriptions.

### 13.6. Processor interface and outcome

~~~java
package demo.mqttdedup;

enum DedupOutcome {
    NEW_EVENT,
    DUPLICATE_IGNORED
}

interface TelemetryProcessor {
    DedupOutcome accept(TelemetryEvent event, byte[] rawPayload);
}
~~~

Separating the interface lets flow tests run without PostgreSQL, while the production implementation uses a JDBC transaction with a unique constraint.

### 13.7. JDBC processor: deduplication and side effect in one transaction

~~~java
package demo.mqttdedup;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
class JdbcTelemetryProcessor implements TelemetryProcessor {

    private final JdbcTemplate jdbc;

    JdbcTelemetryProcessor(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional
    public DedupOutcome accept(
            TelemetryEvent event, byte[] rawPayload) {

        String hash = sha256(rawPayload);

        int inserted = jdbc.update("""
                INSERT INTO processed_mqtt_events
                    (tenant_id, event_id, device_id, payload_sha256)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (tenant_id, event_id) DO NOTHING
                """,
                event.tenantId(), event.eventId(),
                event.deviceId(), hash);

        if (inserted == 0) {
            String previousHash = jdbc.queryForObject("""
                    SELECT payload_sha256
                    FROM processed_mqtt_events
                    WHERE tenant_id = ? AND event_id = ?
                    """,
                    String.class,
                    event.tenantId(), event.eventId());

            if (!hash.equals(previousHash)) {
                throw new IllegalStateException(
                        "Event ID already exists with different payload");
            }
            return DedupOutcome.DUPLICATE_IGNORED;
        }

        jdbc.update("""
                INSERT INTO telemetry_readings
                    (tenant_id, event_id, device_id,
                     sequence_no, celsius)
                VALUES (?, ?, ?, ?, ?)
                """,
                event.tenantId(), event.eventId(),
                event.deviceId(), event.sequence(),
                event.celsius());

        return DedupOutcome.NEW_EVENT;
    }

    private static String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest
                    .getInstance("SHA-256")
                    .digest(bytes);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "JVM lacks SHA-256", ex);
        }
    }
}
~~~

**The reliability of this mechanism rests on the database unique constraint and transaction**, not on an `if (eventIdAlreadySeen)` check on the Java heap. Two threads can run concurrently; PostgreSQL resolves the unique-key conflict, and the transaction commits or rolls back both the key and the reading together.

Deployment assumptions:

- PostgreSQL uses a suitable isolation level, commonly `READ COMMITTED`; test concurrency under real load/reconnects.
- Spring's DB connection pool and transaction management are properly configured.
- `@Transactional` runs when invoked via the Spring bean/proxy, not through self-invocation that bypasses AOP advice.
- Retried raw bytes of the same event stay stable per contract; if valid representations can vary, switch the hash policy to a canonical business fingerprint.
- Side effects here write only to **the same PostgreSQL database**. Making HTTP/Kafka/JMS calls inside the transaction provides no cross-system atomicity.
- DB errors must be classified as transient vs. non-transient; throwing an exception from the service does not automatically produce durable MQTT redelivery.

### 13.8. Why insert the key before the reading and in the same transaction?

If inserting the reading commits and the app crashes before inserting the idempotency key in a **separate** transaction, replays can create duplicate side effects. If inserting the key commits in a separate transaction first and the reading fails, replays get wrongly blocked. One `@Transactional` wrapping **both INSERTs** is essential.

When `ON CONFLICT DO NOTHING` returns 0, querying the hash distinguishes a retry of the same payload from an event ID reused for different data. On hash mismatch, throw an exception to quarantine/investigate—never silently overwrite the existing row.

### 13.9. QoS and DB idempotency are two complementary layers

Whether MQTT input arrives at QoS 1 or 2, the Spring flow should process by business event ID. QoS 1 can redeliver; QoS 2 still does not protect against an outbox producer sending two independent publications or consumers receiving retained/replayed messages from another source. The unique constraint guards database state.

### 13.10. TopicScope: identifying tenant/device from the concrete topic

~~~java
package demo.mqttdedup;

record TopicScope(String tenantId) {

    TopicScope {
        if (tenantId == null
                || !tenantId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
    }

    String subscriptionFilter() {
        return "tenants/" + tenantId
                + "/devices/+/temperature";
    }

    String requireDeviceId(Object receivedTopic) {
        if (!(receivedTopic instanceof String topic)) {
            throw new IllegalArgumentException("Missing received topic");
        }

        String[] parts = topic.split("/", -1);
        if (parts.length != 5
                || !"tenants".equals(parts[0])
                || !tenantId.equals(parts[1])
                || !"devices".equals(parts[2])
                || !parts[3].matches("[A-Za-z0-9_-]{1,64}")
                || !"temperature".equals(parts[4])) {
            throw new IllegalArgumentException(
                    "Topic does not belong to valid tenant/device: " + topic);
        }
        return parts[3];
    }
}
~~~

`TopicScope` validates the **actual received topic name**, not the subscription filter. MQTT's `+` can match an empty level like `devices//temperature`; this business validator rejects empty device IDs.

### 13.11. Inbound MessageChannel and IntegrationFlow

~~~java
package demo.mqttdedup;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class MqttDedupFlowConfiguration {

    @Bean(name = "mqtt.telemetry.raw")
    MessageChannel rawTelemetryInput() {
        return new DirectChannel();
    }

    @Bean
    TopicScope topicScope(
            @Value("${app.mqtt.tenant-id}") String tenantId) {
        return new TopicScope(tenantId);
    }

    @Bean
    ObjectMapper mqttPayloadMapper() {
        return new ObjectMapper();
    }

    @Bean
    IntegrationFlow rawTelemetryFlow(
            TopicScope topicScope,
            ObjectMapper mqttPayloadMapper,
            TelemetryProcessor processor) {

        return IntegrationFlow.from("mqtt.telemetry.raw")
                .handle(byte[].class, (raw, headers) -> {
                    if (raw.length == 0 || raw.length > 16_384) {
                        throw new IllegalArgumentException(
                                "Invalid payload size");
                    }

                    String deviceId = topicScope.requireDeviceId(
                            headers.get(MqttHeaders.RECEIVED_TOPIC));

                    final TelemetryEvent event;
                    try {
                        event = mqttPayloadMapper.readValue(
                                raw, TelemetryEvent.class);
                    } catch (JsonProcessingException ex) {
                        throw new IllegalArgumentException(
                                "Failed to parse telemetry JSON", ex);
                    }

                    if (!topicScope.tenantId().equals(event.tenantId())
                            || !deviceId.equals(event.deviceId())) {
                        throw new IllegalArgumentException(
                                "Topic and payload disagree on tenant/device");
                    }

                    // Transaction lives inside the processor bean.
                    processor.accept(event, raw);
                    return null; // One-way inbound
                })
                .get();
    }
}
~~~

Boundaries:

1. Inbound converter chooses `byte[]`, so the handler uses `.handle(byte[].class, ...)`.
2. Check byte length **before** parsing; the JSON parser does not restrict topics or devices.
3. `MqttHeaders.RECEIVED_TOPIC` holds the **actual received topic**; never substitute outbound `MqttHeaders.TOPIC`.
4. Compare topic `tenantId` and `deviceId` against JSON before writing idempotency records.
5. `TelemetryProcessor.accept(...)` is invoked through the Spring bean so `@Transactional` proxy advice applies.
6. `return null` marks a one-way endpoint.
7. Demo code omits a production durable quarantine/error policy; implement per section 18.

### 13.12. Configuring the MQTT inbound adapter

~~~java
package demo.mqttdedup;

import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.messaging.MessageChannel;

@Configuration
class MqttDedupTransportConfiguration {

    @Bean
    MqttPahoClientFactory mqttClientFactory(
            @Value("${app.mqtt.broker-url}") String brokerUrl) {

        var options = new MqttConnectOptions();
        options.setServerURIs(new String[] {brokerUrl});
        options.setConnectionTimeout(10);
        options.setKeepAliveInterval(30);
        options.setCleanSession(false);
        options.setAutomaticReconnect(false);

        var factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(options);
        return factory;
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter mqttTelemetryAdapter(
            MqttPahoClientFactory mqttClientFactory,
            TopicScope topicScope,
            @Qualifier("mqtt.telemetry.raw") MessageChannel output,
            @Value("${app.mqtt.client-id}") String clientId) {

        var converter = new DefaultPahoMessageConverter();
        converter.setPayloadAsBytes(true);

        var adapter = new MqttPahoMessageDrivenChannelAdapter(
                clientId, mqttClientFactory,
                topicScope.subscriptionFilter());

        adapter.setQos(1);
        adapter.setRecoveryInterval(10000);
        adapter.setConverter(converter);
        adapter.setOutputChannel(output);
        return adapter;
    }
}
~~~

`setQos(1)` sets the **subscription** QoS for the broker → subscriber leg; the device's publish QoS is an independent value. `cleanSession=false` illustrates an MQTT 3.1.1 persistent session. To resume sessions, the Client ID must remain stable across restarts, yet **must never be shared across two active replicas**.

In this example, Paho auto-reconnect is disabled and the inbound adapter's recovery interval is used to illustrate one recovery strategy. Test real behavior on your project's Spring Integration/Paho version before combining multiple reconnect mechanisms.

### 13.13. Guarantee limits of this demo

If the broker redelivers the exact raw message for `eventId=evt-device17-000001`, PostgreSQL's unique constraint guarantees at most one ledger row and one telemetry reading commit through the processor.

However, a database deduplicating processor **does not automatically prevent MQTT message loss** if Paho/client/broker already ACKed before DB commit or no replay source remains after a crash. Idempotency solves duplicate side effects; durability and delivery guarantees require dedicated acknowledgment, inbox, and broker-storage design.

## 14. When is manual acknowledgment needed?

~~~mermaid
sequenceDiagram
    participant B as MQTT broker
    participant C as Paho / inbound adapter
    participant F as Spring flow
    participant DB as PostgreSQL
    B->>C: PUBLISH QoS 1
    C->>F: Message<byte[]>
    F->>DB: Dedup + business write
    DB-->>F: COMMIT
    Note over B,DB: MQTT ACK timing depends on Paho/Spring configuration
    C-->>B: ACK per client/adapter mode
~~~

**Boundary diagram only**—do not assume the default adapter always defers PUBACK until after DB commit. Across different QoS levels, callbacks, converters, and Spring versions, ACK timing can differ. Never assume throwing an exception from a handler automatically rolls back an already-sent PUBACK.

### 14.1. Manual ACK depends on adapter version

Some Spring Integration MQTT inbound adapter versions support manual acknowledgments:

~~~java
// Use only when supported by version and callback contract is verified.
adapter.setManualAcks(true);
~~~

When enabled, the application receives an acknowledgment callback via the corresponding message header/API. Desired sequence:

~~~text
Received PUBLISH + acknowledgment callback
    → validate topic/bytes/schema
    → @Transactional processor writes ledger + business side effect
    → transaction commits cleanly
    → acknowledge via callback per exact API version
~~~

**This is pseudocode showing order, not copy-pasteable callback code.** Exact callback/header names, how to retrieve the callback, the effect of `acknowledge()`, and when the broker treats the packet as complete must be verified against your exact dependency version. Never guess header names or invoke nonexistent ACK APIs.

### 14.2. Crash windows cannot be eliminated entirely

If the DB commits and the process dies before the MQTT ACK, the message may be redelivered upon recovery—where the unique constraint handles the duplicate safely. If the MQTT ACK completes before the DB commits and the DB fails, the message can be lost from the business store. Therefore combine **durable writes, idempotency, ACK policies, and replay** instead of flipping manual ACK on and declaring end-to-end exactly-once.

### 14.3. Poison messages and manual ACK

Schema-invalid JSON will not become valid just because the broker redelivers it. Production policies need a durable quarantine/inbox (topic, metadata, secured raw payload, reason) before acknowledging or escalating for investigation—avoiding blocked sessions or infinite retry loops.

## 15. Multi-instance: the database is the true synchronization point

~~~mermaid
flowchart TD
    B[("MQTT broker")]
    A["Subscriber A<br/>Client ID A"]
    C["Subscriber B<br/>Client ID B"]
    DB[("PostgreSQL<br/>PRIMARY KEY tenant_id,event_id")]
    B --> A
    B --> C
    A -->|"INSERT evt-1001"| DB
    C -->|"INSERT evt-1001"| DB
~~~

Two MQTT clients with different IDs subscribing to the same normal topic filter both receive PUBLISHes. When both write to the DB, per-JVM `ConcurrentHashMap` caches cannot stop duplicates. PostgreSQL's unique constraint and shared transactions arbitrate even when two processes handle the event simultaneously.

### 15.1. Shared subscriptions do not mean business exactly-once

Some brokers support shared subscriptions to deliver each message to one group member per broker/protocol rules, yet workers can still crash, duplicates can follow reconnects, or producers can re-emit the same event. Shared subscriptions reduce unwanted fan-out; they **do not replace** business IDs and idempotency.

### 15.2. Never share Client IDs for load balancing

Two active clients using the same MQTT Client ID disconnect each other, causing reconnect loops and unpredictable sessions. Use distinct Client IDs or supported shared subscriptions; never turn Client ID conflicts into a load-balancing strategy.

### 15.3. Caches are optimizations only

In-memory/Redis caches reduce DB queries, yet carry TTLs, evictions, and races, and do not share transactions with business writes. For critical business correctness, database uniqueness remains the source of truth. Even on a cache miss, correctness must hold.

## 16. Duplicates vs. out-of-order messages

Deduplication suppresses repeated deliveries of the same business event; it **does not guarantee** distinct events arrive in order.

~~~text
Publisher emits:
  evt-101 sequence=101 celsius=25
  evt-102 sequence=102 celsius=26

Backend receives:
  evt-102 first
  evt-101 second
~~~

Both events have different IDs and belong in event history. Yet updating `latest_temperature` purely in callback arrival order would overwrite `26` with `25`.

### 16.1. Event log vs. latest state

- **Event history:** keep every unique event; never discard a valid reading merely because it arrived late.
- **Latest snapshot:** perform conditional updates based on `sequence + bootEpoch` or a reliable ordering policy.
- **Alert streams:** may need watermarks, debouncing, and event-time validation to prevent duplicate or out-of-order alerts.

Example SQL for latest snapshot (create its table and dedicated sequence contract before use):

~~~sql
INSERT INTO device_latest_temperature
    (tenant_id, device_id, sequence_no, celsius)
VALUES (:tenant_id, :device_id, :sequence_no, :celsius)
ON CONFLICT (tenant_id, device_id)
DO UPDATE SET
    sequence_no = EXCLUDED.sequence_no,
    celsius = EXCLUDED.celsius
WHERE device_latest_temperature.sequence_no < EXCLUDED.sequence_no;
~~~

Never use bare `sequence` if devices reset to `0` on reboot and could overwrite newer state wrongly; include `bootEpoch`/generation and comparison rules in the contract.

### 16.2. Duplicate commands may need to re-send ACKs

If a device sees a `commandId` that already executed earlier, it must **not re-run the side effect**, yet it can re-publish its prior business ACK to help the publisher reconcile. "Idempotent" does not mean staying completely silent on duplicates; it means preserving the business outcome.

## 17. Bridging MQTT to Kafka, JMS, HTTP, files, or SFTP

When an MQTT inbound flow forwards messages to another system, PostgreSQL idempotency alone **is not enough** to guarantee target publication.

~~~text
MQTT evt-1001 received
→ DB marks processed and COMMITs
→ Java process crashes before publishing to Kafka
→ MQTT retries evt-1001, yet DB dedup skips it
→ Kafka may never receive the event
~~~

Conversely, publishing to Kafka/HTTP first and recording the dedup row second risks repeating the external side effect if a crash hits in between.

| Target system | Recommended approach |
| --- | --- |
| Same PostgreSQL database | Ledger and business rows in the same transaction. |
| Kafka | Write an **outbox event** in the DB transaction; relay publishes, and the Kafka consumer is also idempotent. |
| JMS/AMQP | Inbox/outbox, stable message IDs, dedicated ACK and retry policies. |
| HTTP | Idempotency key in request contract, bounded retries, timeouts treated as uncertain. |
| File/SFTP | Filename keyed by event ID, temp-file + atomic rename where supported, target state reconciliation. |
| MQTT outbound command | Stable command ID, proper retained policy, dedicated business ACK. |
| Notification/email | Notification ID, send log/outbox, duplicate suppression. |

### 17.1. Inbox + outbox in a single transaction

~~~mermaid
flowchart LR
    MQTT["MQTT inbound"]
    DB[("DB transaction<br/>inbox + business + outbox")]
    RELAY["Outbox relay"]
    DEST["Kafka / JMS / HTTP / SFTP"]
    MQTT --> DB --> RELAY --> DEST
    DEST -. "ACK/reconciliation" .-> RELAY
~~~

A single transaction writes the inbox event key, DB business effect, and outbox row. After commit, the relay dispatches to the target. If the relay sends successfully and crashes before marking sent, it can re-send; **downstream must still be idempotent**.

### 17.2. Preventing bridge loops

If an MQTT event is bridged to Kafka and a Kafka consumer publishes the same event back to the source MQTT topic, an infinite loop forms. Beyond idempotency keys, add source/origin metadata, explicit routing, hop limits, or loop-prevention rules. DB deduplication alone does not stop network-level looping.

## 18. Handling duplicates, collisions, and distinct errors

| Outcome | Example | Policy |
| --- | --- | --- |
| `NEW_EVENT` | New key, transaction commits. | Record side effect and increment `new` metric. |
| `DUPLICATE_IGNORED` | Existing key, matching payload hash. | Skip second side effect; optionally re-send business ACK. |
| `INVALID_TOPIC_SCHEMA` | Wrong tenant/topic, malformed JSON, missing event ID. | Quarantine; never retry deterministic errors endlessly. |
| `EVENT_ID_COLLISION` | Same key with different payload per contract. | Quarantine and investigate publisher/ACLs. |
| `TRANSIENT_DB_FAILURE` | Database unavailable/deadlock. | Bounded retry with backoff from a durable source. |
| `BROKER_CONNECTION_FAILURE` | Reconnect, inconsistent session state. | Broker monitoring; verify subscriptions/replay. |

### 18.1. A legitimate duplicate is a successful outcome

A QoS 1 redelivery with an already-committed `eventId`/payload is not necessarily an exception. Return `DUPLICATE_IGNORED` and finish cleanly instead of throwing on every duplicate and triggering log storms and retry loops.

### 18.2. Collisions must be evaluated separately

An ID once representing `26.5°C` now arriving with `99.9°C` could indicate firmware resetting IDs, a producer retry altering payloads, or spoofing. Under a byte-stable contract, a hash mismatch belongs in quarantine/audit rather than overwriting the existing row.

If business rules permit JSON whitespace/key-order differences across retries of the same event, use a canonical fingerprint instead of raw SHA-256. Pick one explicit policy and test it to avoid false collisions.

### 18.3. Throwing an exception does not mean the MQTT broker will retry

A Spring `IntegrationFlow` can forward `ErrorMessage`/exceptions to an error path per endpoint configuration, yet the MQTT client may have already sent its ACK before DB processing. Never assume a Java exception rolls back `PUBACK`. When strong delivery guarantees are required, verify manual ACK timing, sessions, durable inboxes, or replayable sources in your actual deployment.

### 18.4. Quarantine and data safety

Error-storage records should capture `receivedTopic`, parsed business ID if available, `reasonCode`, byte length, receipt time, and a secured raw payload reference. Enforce retention limits, encryption, ACLs, and avoid logging raw PII/secrets. Never re-publish poison messages endlessly onto the source topic.

## 19. Testing the flow without an MQTT broker

Brokerless tests can verify topic/JSON/deduplication contracts using `@SpringJUnitConfig` loading only `MqttDedupFlowConfiguration` and a fake `TelemetryProcessor`. They **do not** prove broker retransmission or DB transactions.

### 19.1. Inspectable fake processor for tests

~~~java
package demo.mqttdedup;

import java.util.Arrays;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

class InMemoryTestTelemetryProcessor
        implements TelemetryProcessor {

    private final Map<String, byte[]> seen =
            new ConcurrentHashMap<>();

    @Override
    public DedupOutcome accept(TelemetryEvent event, byte[] raw) {
        String key = event.tenantId() + ":" + event.eventId();
        byte[] previous = seen.putIfAbsent(key, raw.clone());

        if (previous == null) {
            return DedupOutcome.NEW_EVENT;
        }
        if (!Arrays.equals(previous, raw)) {
            throw new IllegalStateException("Collision in test");
        }
        return DedupOutcome.DUPLICATE_IGNORED;
    }

    int uniqueEvents() {
        return seen.size();
    }

    void clear() {
        seen.clear();
    }
}
~~~

This fake handles concurrent map operations within a single JVM yet has **no durability**; never substitute it for PostgreSQL unique constraints in production.

### 19.2. JUnit flow test

~~~java
package demo.mqttdedup;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        MqttDedupFlowConfiguration.class,
        DedupTestBeans.class
})
@TestPropertySource(properties = "app.mqtt.tenant-id=tenant-a")
class MqttDedupFlowTest {

    @Autowired
    @Qualifier("mqtt.telemetry.raw")
    MessageChannel input;

    @Autowired
    InMemoryTestTelemetryProcessor processor;

    @BeforeEach
    void reset() {
        processor.clear();
    }

    private static byte[] event(String id, String celsius) {
        String json = "{\"schemaVersion\":1,"
                + "\"eventId\":\"" + id + "\","
                + "\"tenantId\":\"tenant-a\","
                + "\"deviceId\":\"device-17\","
                + "\"sequence\":1001,"
                + "\"celsius\":" + celsius + "}";
        return json.getBytes(StandardCharsets.UTF_8);
    }

    private boolean send(byte[] bytes, String topic) {
        return input.send(MessageBuilder.withPayload(bytes)
                .setHeader(MqttHeaders.RECEIVED_TOPIC, topic)
                .build());
    }

    @Test
    void sameEventTwiceHasOnlyOneBusinessEffect() {
        String topic =
                "tenants/tenant-a/devices/device-17/temperature";
        byte[] payload = event("evt-1001", "26.5");

        assertTrue(send(payload, topic));
        assertTrue(send(payload, topic));
        assertEquals(1, processor.uniqueEvents());
    }

    @Test
    void sameTemperatureButDifferentIdsAreBothValid() {
        String topic =
                "tenants/tenant-a/devices/device-17/temperature";

        send(event("evt-1001", "26.5"), topic);
        send(event("evt-1002", "26.5"), topic);
        assertEquals(2, processor.uniqueEvents());
    }

    @Test
    void sameIdWithDifferentPayloadIsCollision() {
        String topic =
                "tenants/tenant-a/devices/device-17/temperature";

        send(event("evt-1001", "26.5"), topic);

        assertThrows(RuntimeException.class, () ->
                send(event("evt-1001", "99.9"), topic));
        assertEquals(1, processor.uniqueEvents());
    }

    @Test
    void wrongTenantIsRejectedBeforeSideEffect() {
        assertThrows(RuntimeException.class, () ->
                send(event("evt-1001", "26.5"),
                        "tenants/tenant-b/devices/device-17/temperature"));
        assertEquals(0, processor.uniqueEvents());
    }

    @Test
    void malformedJsonIsRejected() {
        String topic =
                "tenants/tenant-a/devices/device-17/temperature";
        assertThrows(RuntimeException.class, () ->
                send("{\"eventId\":".getBytes(StandardCharsets.UTF_8),
                        topic));
        assertEquals(0, processor.uniqueEvents());
    }
}

@Configuration
class DedupTestBeans {

    @Bean
    InMemoryTestTelemetryProcessor telemetryProcessor() {
        return new InMemoryTestTelemetryProcessor();
    }
}
~~~

With `DirectChannel`, the handler executes synchronously in these tests. `assertThrows(RuntimeException.class)` avoids coupling to a single Spring Integration version's wrapper exception class; thorough QA should also assert root causes and `errorChannel` routing.

### 19.3. Limits of brokerless tests

| Test level | What it proves | What it does NOT prove |
| --- | --- | --- |
| Brokerless Spring flow | JSON/received topic/ID/branching. | MQTT ACK, Paho callbacks, broker QoS. |
| PostgreSQL integration | Unique key, rollback, transactions, concurrency. | MQTT protocol retransmission. |
| Broker end-to-end | Subscriptions, reconnect, QoS behavior in lab. | All network failures and external-system exactly-once. |

**Testing duplicates by sending two fake Spring Messages does not test the MQTT DUP flag.** Verifying protocol retransmission requires real broker/network fault injection.

## 20. Testing real PostgreSQL and an MQTT broker

### 20.1. Concurrency test with PostgreSQL

Run an isolated PostgreSQL test instance with the `processed_mqtt_events` and `telemetry_readings` DDL. From **two transactions or two service instances**, concurrently invoke `JdbcTelemetryProcessor.accept(...)` with the same `(tenant-a, evt-1001)` and identical payload.

After both attempts finish:

~~~sql
SELECT count(*) AS ledger_count
FROM processed_mqtt_events
WHERE tenant_id = 'tenant-a' AND event_id = 'evt-1001';

SELECT count(*) AS reading_count
FROM telemetry_readings
WHERE tenant_id = 'tenant-a' AND event_id = 'evt-1001';
~~~

Expected: `ledger_count = 1` and `reading_count = 1`. One attempt returns `NEW_EVENT`, and the other returns `DUPLICATE_IGNORED` when both finish with the same payload.

Test rollback: throw an exception **after inserting into the ledger yet before inserting the reading** within one transaction, and verify no committed ledger row remains and a retry can insert both. This check is frequently missed when testing only happy paths.

**Note:** SQL using `ON CONFLICT` is PostgreSQL-specific. If using H2, Testcontainers, or another database, verify version/syntax compatibility; ideally run concurrency tests on the production database engine.

### 20.2. Sending two MQTT publications with the same business ID

Use a test broker you control, e.g., Mosquitto at `localhost:1883`. The Spring app is subscribed to `tenants/tenant-a/devices/+/temperature`. Start a CLI subscriber:

~~~bash
mosquitto_sub -h localhost -p 1883 \
  -i dedup-observer-local-1 \
  -t 'tenants/tenant-a/devices/+/temperature' \
  -q 1 -v
~~~

Publish telemetry:

~~~bash
mosquitto_pub -h localhost -p 1883 \
  -t 'tenants/tenant-a/devices/device-17/temperature' \
  -q 1 \
  -m '{"schemaVersion":1,"eventId":"evt-cli-1","tenantId":"tenant-a","deviceId":"device-17","sequence":1001,"celsius":26.5}'
~~~

Run **that exact command again**. Two MQTT publications are sent, yet PostgreSQL holds only **one** `evt-cli-1` event. If the DB shows two side effects, the idempotency guard, transaction, or unique key is broken.

**Test limitation:** running the CLI twice generates **two independent PUBLISH operations** with the same business ID. It tests application duplicate handling, **not** QoS 1 protocol retransmission with `DUP=1`.

### 20.3. Two events with the same temperature and different IDs

Publish similarly with `eventId=evt-cli-2` while keeping `celsius=26.5`. PostgreSQL should contain both `evt-cli-1` and `evt-cli-2`. If the second reading is dropped just because the temperature value matched, your dedup key is wrong.

### 20.4. Comparing QoS 0/1/2

Test `mosquitto_pub -q 0`, `-q 1`, and `-q 2` with matching broker/subscription QoS. Observe publisher logs, client sessions, and database rows:

- QoS 0 has no `PUBACK`.
- QoS 1 has `PUBACK` and can redeliver under fault scenarios.
- QoS 2 uses `PUBREC`/`PUBREL`/`PUBCOMP`; application publishers can still issue new PUBLISHes with the same business ID.
- Never treat CLI completion time as proof the business DB committed.

### 20.5. Fault injection to observe real retransmission

To test protocol-level duplicates, use a proxy or test harness that lets **PUBLISH reach the broker while dropping/delaying the return ACK to the publisher**, or inject a network partition during the in-flight window.

~~~mermaid
sequenceDiagram
    participant P as MQTT Publisher
    participant B as Test broker
    participant A as Spring inbound
    participant DB as PostgreSQL
    P->>B: PUBLISH QoS1 evt-1001
    B->>A: Delivery evt-1001
    A->>DB: BEGIN + dedup + COMMIT
    B--xP: PUBACK lost
    P->>B: Retransmit / retry
    B->>A: Event may be redelivered
    A->>DB: ON CONFLICT, no new side effect created
~~~

**This illustrates one plausible scenario, not a promise that every broker produces exactly two deliveries.** Aggressive network faults may trigger `connection lost` before completion timeouts fire. Record exact errors, packet captures where authorized, and broker/client versions.

Never disrupt production MQTT brokers or real devices. Fault testing belongs in isolated test brokers/containers.

### 20.6. Three crash points to test

| Crash point | Expected outcome |
| --- | --- |
| Before DB transaction | No business commit; if the source replays, the event can be reprocessed. |
| After ledger INSERT but before COMMIT | Rolls back both ledger and business write; replay is not wrongly blocked. |
| After DB COMMIT but before MQTT ACK | Event may redeliver; unique constraint ensures replay produces no second effect. |

For side effects outside the DB (HTTP/Kafka), add a crash test **after sending to the target yet before marking the outbox sent**, since that exact window creates downstream duplicates.

### 20.7. Complete test matrix

| Case | Expectation |
| --- | --- |
| New event, valid JSON | Writes one ledger row and one business row. |
| Same ID + same bytes received 2 or 10 times | Side effect happens only once. |
| Same ID with different payload | Collision detected; existing row not overwritten. |
| Different ID with same temperature | Both valid events are stored. |
| Tenant/topic disagrees with JSON | Rejected before dedup insert. |
| Malformed/oversized payload | Rejected without OOM or infinite retries. |
| Two instances writing same ID | Database unique key prevents duplicates. |
| Session replay after reconnect | Does not multiply business side effects. |
| Re-delivered retained message | Snapshot distinguished from live events. |
| Overlapping subscriptions | Duplicates suppressed; unnecessary overlaps removed. |
| QoS 1 lost ACK | Retries cleanly without duplicate effects. |
| QoS 2 + app publishes twice | Deduplicated by business ID. |
| Database unavailable | Marker not falsely committed; retry/recovery policy engages. |
| Outbox relay crashes after sending | Downstream is idempotent and reconcilable. |

## 21. Security: duplicate handling does not replace authorization

An untrusted publisher could send an already-seen event ID to trick the consumer into ignoring real data, or spoof `deviceId` to write into another tenant. Idempotency checks are only meaningful after **identity and permission validation**.

| Threat | Control |
| --- | --- |
| Publisher spoofs another device's event ID | Broker auth/TLS, identity-bound publish ACLs; business validator checks topic/tenant. |
| Subscriber receives another tenant's topic via `#` | Subscription ACLs, tenant-scoped filters, `RECEIVED_TOPIC` validation. |
| Reusing ID for different payload | Fingerprint/version checks, quarantine/audit. |
| Oversized payload exhausting memory | Broker/client caps; check `raw.length` before parsing. |
| Dangerous schema/untrusted deserialization | Allowlisted Jackson DTO mapping; never arbitrary Java serialization. |
| Raw payload containing PII/secrets | Redacted logs, encrypted quarantine, TTLs, and access controls. |
| Old retained command re-triggering action | Never retain one-time commands; enforce command IDs and TTLs. |
| Dedup cache poisoning | Never accept IDs before authorization; enforce DB unique keys and transactions. |

**Never use MQTT Client ID or topic name as sole proof of authentication.** They are protocol-declared identifiers; trust must come from broker identity/ACLs and business mapping.

## 22. Observability: know which layer caused the duplicate

A dashboard showing "10% MQTT duplicates" is inadequate if it fails to separate protocol redelivery from application retries.

| Suggested metric/field | Purpose |
| --- | --- |
| `mqtt_inbound_messages_total` | Total MQTT messages received by adapter. |
| `mqtt_transport_duplicate_flag_total` | Counts DUP metadata when provided by converter/version. |
| `business_new_events_total` | Count of new event IDs committed. |
| `business_duplicates_ignored_total` | Retries/replays that skipped duplicate side effects. |
| `business_id_collisions_total` | Event IDs improperly reused for different payloads. |
| `mqtt_inbound_processing_errors_total{kind}` | Topic/schema/DB/recovery errors by category. |
| `mqtt_reconnect_attempts_total` | Reconnect loops and incident correlation. |
| `idempotency_db_conflicts_total` | Unique-key conflicts measured inside the processor. |
| `mqtt_inbox_backlog` | Unprocessed durable inbound work. |
| `mqtt_outbox_oldest_age_seconds` | Downstream relay lag. |
| `business_effect_commit_latency_ms` | Business transaction latency. |
| `business_event_replay_lag_seconds` | Event age when replayed/reconciled. |

These names are **design suggestions**, not metrics automatically emitted with these exact names by Spring Integration/Paho. Avoid putting individual `eventId` or `deviceId` values into metric labels due to high cardinality; keep IDs in access-controlled logs/traces.

### 22.1. Tracing a redelivered event

~~~text
evt-1001 RECEIVED attempt=1
evt-1001 VALIDATED
evt-1001 DEDUP_NEW
evt-1001 DB_COMMITTED

evt-1001 RECEIVED attempt=2
evt-1001 VALIDATED
evt-1001 DEDUP_ALREADY_PROCESSED
evt-1001 SIDE_EFFECT_SKIPPED
~~~

Do not label the second delivery an "MQTT retransmission" merely because it shares the same business ID; the producer may have sent a brand-new PUBLISH. Log **observed facts** such as `receivedTopic`, `eventId`, source client role, timestamp, and connection/session epoch if available.

### 22.2. When duplicate rates spike suddenly

Investigate in order:

1. Is the publisher retrying due to timeouts?
2. Is the broker/client stuck in a reconnect loop, duplicate Client ID conflict, or unstable session state?
3. Does the subscriber have overlapping MQTT filters or multiple instances subscribed simultaneously?
4. Is a bridge looping or an outbox relay replaying continuously?
5. Is the consumer hitting DB timeouts that trigger upstream retries?
6. Did an idempotency key accidentally reset after device reboot or firmware update?
7. Are retained messages being mistaken for live events on resubscribe?

Simply bumping QoS from 1 to 2 rarely fixes all of these, because many duplicates originate **outside** protocol retransmission.

## 23. Anti-patterns and alternatives

| Anti-pattern | Why it fails | Alternative |
| --- | --- | --- |
| "QoS 2 means no dedup needed." | QoS 2 does not cover two app publishes or DB effects. | Stable event ID + atomic idempotent processing. |
| `if (DUP) return;` | `DUP=1` can be the first delivery your app ever sees. | Look up durable event key. |
| `if (!cache.contains(id)) {write(); cache.put(id);}` | Races; RAM cache vanishes on restart. | DB unique constraint and transaction. |
| Deduplicating solely by payload hash | Two valid readings can share identical values/bytes. | Business event ID; use hashes only for collision detection. |
| Marking processed in a separate transaction before business write | Crash can drop the event permanently. | Ledger + write in one transaction. |
| Publishing HTTP/Kafka and assuming DB commit is atomic | No default distributed atomicity. | Transactional outbox/inbox and idempotent downstream. |
| Generating a fresh `eventId` on every retry | Consumer cannot recognize retries as the same event. | Keep `eventId` stable. |
| Using MQTT packet ID as DB key | Reused and scoped to one client session. | Business ID. |
| Throwing exceptions on every duplicate | Triggers retry and log storms. | Treat valid duplicates as idempotent success. |
| Setting dedup TTL to 1 day with 7-day replays | Replays past TTL repeat side effects. | Match retention to maximum replay horizon. |
| Sharing one Client ID across two replicas | Broker kicks connections off. | Unique active Client ID or supported shared subscriptions. |
| Treating Java exceptions as MQTT ACK rollbacks | ACK timing is independent of transactions. | Verify adapter/manual ACK/version and durable inbox. |

## 24. Practice exercise: telemetry and control commands

**Context:** an IoT platform has 20,000 sensors publishing QoS 1 telemetry, a Spring Integration backend persisting to PostgreSQL, and a downstream Kafka consumer emitting alerts. Device networks are flaky and may re-send messages after reconnects or outbox retries.

### Requirements

1. Design MQTT topic `tenants/{tenantId}/devices/{deviceId}/temperature` and a JSON schema containing `schemaVersion`, `eventId`, `tenantId`, `deviceId`, `sequence`, and `celsius`.
2. Choose an event ID that survives restarts/replays; describe how to prevent collisions across firmware reboots.
3. Configure `MqttPahoMessageDrivenChannelAdapter` with a tenant-scoped filter, QoS 1, and `payloadAsBytes=true`.
4. Use `MqttHeaders.RECEIVED_TOPIC` to validate tenant/device and Jackson to parse payloads.
5. Design the dedup ledger table with a composite unique key, retention matching the replay horizon, and a hash for ID collision detection.
6. Implement a `@Transactional` processor inserting the ledger row and reading in **the same transaction**.
7. Send the same event twice; verify only one reading commits.
8. Send two events with identical temperature values and distinct IDs; verify neither is wrongly dropped.
9. Run two consumer instances writing to the same database; test concurrent duplicates and unique-key conflicts.
10. Trigger a database rollback between the ledger and business writes; verify retries are not wrongly blocked.
11. Test malformed payloads, wrong tenants, oversized frames, and ID collisions under error/quarantine policies.
12. Add an outbox row inside the transaction to relay events to Kafka; test crashing after Kafka send yet before marking sent.
13. Make the Kafka consumer idempotent on the same event ID instead of relying on MQTT deduplication as the final guarantee.
14. Test broker reconnect/session recovery, QoS 0/1/2, and overlapping subscription filters.
15. Contrast two CLI publishes with the same `eventId` against packet-level QoS retransmission using fault injection for the latter.
16. Design latest-state updates using `sequence`/`epoch` to handle out-of-order arrivals.
17. Evaluate manual ACKs per API version; measure DB commit vs. MQTT ACK ordering in fault tests.
18. Add metrics for new/duplicate/collision/error/replay lag and enforce broker ACLs/TLS.
19. Test a `TURN_ON` command arriving twice: the device must not execute the side effect twice, yet may re-emit its prior ACK.
20. Document delivery guarantees at every boundary: MQTT → Spring → PostgreSQL → Kafka.

**Completion criteria:** duplicates cause no repeated side effects; distinct-ID events are preserved; transaction rollbacks and concurrency behave properly; ACK timing is never assumed; a durable outbox and real broker tests exist; and the system can trace why an event was redelivered.

## 25. Self-check questions

1. Can QoS 0 ever produce business duplicates? Why or why not?
2. Which handshake does QoS 1 use? When `PUBACK` is lost, what can happen?
3. What scope does QoS 2 exactly-once apply to?
4. Why can two QoS 2 PUBLISHes with the same `commandId` still produce duplicate side effects?
5. Does `DUP=1` always prove the consumer already received the event earlier?
6. Does `DUP=0` always prove the event is new?
7. How do MQTT packet IDs and Paho tokens differ from `eventId`?
8. Can two readings with the same `26.5°C` value be two legitimate business events?
9. Why should a raw payload hash not serve as the sole idempotency key?
10. When the same `eventId` arrives with different bytes, what should happen?
11. Does `SELECT` followed by `INSERT` prevent races between two threads?
12. Why is a database unique constraint still needed even when using a cache?
13. Why must the ledger INSERT and business INSERT execute in the same transaction?
14. If the DB commits yet the app crashes before sending MQTT ACK, how should replays behave?
15. If MQTT ACKed yet the app crashes before DB commit, can a business event be lost?
16. Does manual ACK turn PostgreSQL and the broker into one distributed transaction?
17. How do MQTT retained messages and persistent sessions differ?
18. When re-subscribing and receiving retained `ONLINE`, should it be treated as a live online transition?
19. How can overlapping subscriptions introduce duplicates?
20. How do two distinct-ID MQTT clients subscribing to the same topic differ from a shared subscription?
21. Why is sharing one Client ID across two active instances not load balancing?
22. How are deduplication and out-of-order handling two separate problems?
23. When `sequence` resets after a reboot, what else does a latest-state update need?
24. Why must tenant/device topics be validated before recording a dedup key?
25. When forwarding MQTT events to Kafka/HTTP, why is an outbox needed?
26. Does a fake `MessageChannel` test verify the broker's DUP flag?
27. Is running `mosquitto_pub` twice with the same ID a test of QoS retransmission?
28. Should poison messages be retried infinitely?
29. How should idempotency retention compare to maximum replay horizon?
30. Which metrics distinguish business duplicates from Paho reconnect loops?

**Hint:** QoS is a protocol mechanism; deduplication is a **business contract + durable idempotency**. A stable event ID, unique constraints, transactions, and tested replay policies are indispensable.

## 26. Conclusion

**Handling duplicate messages by QoS** in Spring Integration MQTT requires separating protocol behavior from business guarantees:

- **QoS 0:** no broker ACK for PUBLISH, yet business duplicates can still arise from multiple application publishes.
- **QoS 1:** at-least-once with possible redeliveries; consumers must expect the same event ID multiple times.
- **QoS 2:** exactly-once within one MQTT publication/handshake, **not** an automatic guarantee of exactly-once business side effects.
- **DUP flag, packet ID, delivery token, Spring message UUID:** useful technical diagnostics, **not** replacements for a durable business event ID.
- **Event ID + database unique constraint + transaction:** blocks duplicate side effects across threads, instances, reconnects, and restarts.
- **Sessions, retained messages, topic overlaps, bridges, and outboxes:** distinct sources of duplicates/replays requiring explicit design.
- **Manual ACK, error channels, and retries:** verify against your Paho/Spring Integration version; never assume Java exceptions roll back MQTT ACKs.
- **Three-tier testing:** brokerless Spring flow tests, database concurrency tests, and broker end-to-end tests with fault injection.

In the **SPRING_INTEGRATION_ADAPTERS** module, combining **MQTT transport → MessageChannel → payload/topic validation → idempotent transaction → outbox/downstream** preserves correctness even across unstable connections. The goal is not to stop every PUBLISH from ever repeating, but to **ensure every valid business event takes effect exactly as permitted and remains traceable across retries**.
