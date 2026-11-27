# Debezium Inbound Channel Adapter in Spring Integration

## 1. The Problem: Receiving Database Changes Without Continuous SELECT Polling

An application has an `orders` table in PostgreSQL. Whenever an `INSERT`, `UPDATE`, or `DELETE` occurs, the system needs to update a cache, a search index, a read model table, or publish events to Kafka/JMS/AMQP. A simple approach is to write a JDBC inbound adapter that continuously runs `SELECT ... WHERE updated_at > :cursor`. However, this approach has many limitations: choosing a poll interval, handling clock skew or duplicate timestamps, updates to older rows, deletes no longer being visible, and contention across multiple instances.

**Change Data Capture (CDC)** solves this problem differently: reading the database's durable change stream (for example, PostgreSQL logical decoding/WAL or MySQL binlog), instead of querying for changed rows with an application `SELECT`. **Debezium** provides CDC connectors, and Spring Integration provides the **Debezium inbound channel adapter** to feed those change events into a `MessageChannel`.

~~~mermaid
flowchart LR
    W["Application writes to database"] --> DB[("PostgreSQL tables")]
    DB --> LOG["WAL / logical replication"]
    LOG --> CON["Debezium PostgreSQL connector"]
    CON --> ENG["Debezium Engine"]
    ENG --> SI["DebeziumMessageProducer"]
    SI --> CH["MessageChannel"]
    CH --> FLOW["Filter / Transform / Route"]
    FLOW --> SINK["Cache / Outbox / Kafka / JMS"]
~~~

This lesson belongs to the **Adapter Debezium** chapter of the **SPRING_INTEGRATION_ADAPTERS** module: connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; with a focus on message contracts, error handling, and connection lifecycles.

**Objective:** Understand the roles of the Debezium Engine and `DebeziumMessageProducer`, configure Java DSL or Java beans, read and classify events, manage snapshots/offsets/tombstones, design for recoverability, and monitor operations. This lesson focuses on **inbound CDC**; writing to Kafka/JMS/HTTP is a separate downstream flow.

## 2. How Does CDC Differ from JDBC Inbound Polling and Domain Events?

| Mechanism | Event Source | Advantages | Limitations |
|---|---|---|---|
| JDBC inbound polling | Time-based SQL `SELECT` | Easy to set up, no replication privileges required | May scan duplicates or skip late commits; `DELETE` is hard to detect |
| Debezium CDC | Database log + initial snapshot | Sees row-level INSERT/UPDATE/DELETE, minimal application polling | Requires replication, log retention, offset, and DDL handling |
| Application domain event | Explicitly published by business service | Rich business semantics | Events can be lost if DB commits and publishing fails |
| Transactional outbox + Debezium | Outbox row written in the same business transaction; Debezium reads log | Durable and relayable business events | Downstream retry and deduplication are still required |
| Kafka Connect Debezium | Connector running on a Connect cluster | Managed connector/offset/scaling via Connect | Must operate Connect/Kafka infrastructure |
| Debezium Server | Standalone CDC runtime, many sink integrations | Decouples CDC lifecycle from the service | Separate deployment infrastructure |

Spring Integration's `Debezium inbound channel adapter` uses an **embedded Debezium Engine inside the Java application**. It does not mean you have deployed a Kafka Connect cluster, nor does it automatically create a Kafka topic. It converts DB changes into **Spring Messages** for downstream flows to process.

**CDC row event ≠ business command:** `UPDATE orders SET status='PAID'` produces a technical change event, which may not clearly explain why the order was paid. When business-level events such as `OrderPaid` are needed, consider using an outbox to decouple the business contract from arbitrary column changes in the source table.

## 3. Modules, Versions, and Actual APIs

Spring Integration introduced the Debezium inbound channel adapter in **Spring Integration 6.2**. Key classes:

| Class/API | Role |
|---|---|
| `org.springframework.integration.debezium.inbound.DebeziumMessageProducer` | Message producer/endpoint backed by Debezium Engine |
| `org.springframework.integration.debezium.dsl.Debezium` | Java DSL factory with `inboundChannelAdapter(...)` |
| `org.springframework.integration.debezium.dsl.DebeziumMessageProducerSpec` | Builder for configuring the adapter in `IntegrationFlow` |
| `org.springframework.integration.debezium.support.DebeziumHeaders` | Message header names such as `KEY` and `DESTINATION` |
| `io.debezium.engine.DebeziumEngine` | Engine that reads the connector and emits `ChangeEvent` |
| `io.debezium.engine.ChangeEvent<K,V>` | Event containing the serialized key/value |
| `io.debezium.connector.postgresql.PostgresConnector` | PostgreSQL source connector |

Do not confuse this with the JDBC Java DSL `Jdbc.inboundAdapter(...)` introduced later: **the Debezium Java DSL has been available since 6.2**. These examples target Spring Integration 6.2+ (including the 6.4, 6.5, and 7.x lines) with a **compatible Debezium version**; actual versions should follow the Spring Boot BOM and dependency resolution.

### 3.1. Required Dependencies on the Classpath

~~~groovy
// Gradle: use the Spring Boot BOM to select a compatible Spring Integration
// version. The Debezium connector version must be aligned separately.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-debezium'
    implementation 'org.springframework.boot:spring-boot-starter-json'

    runtimeOnly 'io.debezium:debezium-connector-postgres:COMPATIBLE_VERSION'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    // If using Testcontainers 2.x for integration tests in section 30:
    testImplementation 'org.testcontainers:testcontainers-postgresql'
    testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
}
~~~

`COMPATIBLE_VERSION` is a **placeholder that must be replaced with a Debezium connector version compatible** with the Spring Integration/BOM version in use, not a literal artifact coordinate to run as-is. You can use an appropriate platform/BOM matching your application's dependency set. Avoid arbitrarily mixing Debezium Engine, connectors, Kafka Connect API, Jackson, and Spring Integration across multiple major versions.

**Another point:** reading from PostgreSQL requires `debezium-connector-postgres`, not just `spring-integration-debezium`. For MySQL, you must add the corresponding MySQL connector; the connector class name and configuration vary by database.

## 4. Architecture: Engine → Adapter → Message

Execution flow:

1. PostgreSQL writes row changes to the WAL when a transaction commits.
2. Logical decoding with a replication slot/publication lets the connector read changes.
3. The Debezium Engine receives `ChangeEvent` records along with source metadata.
4. `DebeziumMessageProducer` converts events into Spring messages.
5. Spring Integration sends messages to the output channel.
6. Downstream handlers parse, transform, route, and persist/publish according to the application's contract.

~~~mermaid
sequenceDiagram
    participant App as Business app
    participant DB as PostgreSQL
    participant Rep as Replication slot
    participant Engine as Debezium Engine
    participant Adapter as Spring Integration adapter
    participant Handler as Downstream handler
    App->>DB: BEGIN; INSERT / UPDATE / DELETE; COMMIT
    DB->>Rep: WAL records visible for logical decoding
    Engine->>Rep: Read changes from source offset
    Rep-->>Engine: ChangeEvent
    Engine->>Adapter: Callback event/batch
    Adapter->>Handler: Message via MessageChannel
    Handler-->>Adapter: Return / exception (policy-dependent)
    Engine->>Engine: Offset bookkeeping / periodic flush
~~~

**Debezium is message-driven from the Engine**, not a Spring `SourcePollingChannelAdapter`. You **do not need to configure `Pollers.fixedDelay(...)`** for the Engine to "go read the DB"; the connector manages its own streaming lifecycle. The Spring `MessageChannel` remains the link connecting CDC logic to downstream adapters.

## 5. Preparing PostgreSQL: Data and Logical Replication

Create a sample table in the practice database:

~~~sql
CREATE TABLE public.orders (
    id          BIGINT PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    status      VARCHAR(24) NOT NULL,
    total_cents BIGINT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO public.orders(id, customer_id, status, total_cents)
VALUES (101, 'C-001', 'CREATED', 125000),
       (102, 'C-002', 'CREATED', 89000);
~~~

PostgreSQL must have logical replication configured for your environment. Example DBA configuration:

~~~conf
# postgresql.conf (illustrative; requires admin privileges and restart if DB requires it)
wal_level = logical
max_replication_slots = 5
max_wal_senders = 5
~~~

The DBA creates a user with replication privileges and read access to the target tables; this illustrates the privilege structure:

~~~sql
-- Example for a lab environment; actual password must come from a secret manager.
CREATE ROLE cdc_reader WITH LOGIN REPLICATION PASSWORD 'REPLACE_ME';

GRANT CONNECT ON DATABASE appdb TO cdc_reader;
GRANT USAGE ON SCHEMA public TO cdc_reader;
GRANT SELECT ON TABLE public.orders TO cdc_reader;

-- DBA/owner pre-creates the publication so the connector does not require elevated privileges.
CREATE PUBLICATION orders_publication FOR TABLE public.orders;
~~~

**Operational notes:**
- Modifying `postgresql.conf`, replication roles, and publications requires DBA privileges or specific cloud provider policies.
- Apply least privilege; do not use a superuser account for the service if not necessary.
- Set `publication.autocreate.mode=disabled` (or the equivalent mechanism for your version) when the publication is pre-created by a DBA.
- Replication slots/offsets require retention, backup, and failover planning; an unconsumed slot can retain WAL segments and fill up the disk.
- Schema changes or primary key changes affect the event key and consumer contract; versioning is required.

**Note:** creating a publication is **different** from creating a replication slot. A connector can typically create/manage a slot at startup if it has permissions; in production, DBAs should decide ownership and lifecycle management to avoid duplicate slots created across pods.

## 6. Important PostgreSQL Connector Properties

| Property | Example | Role |
|---|---|---|
| `name` | `spring-orders-cdc` | Logical name of the engine/connector |
| `connector.class` | `io.debezium.connector.postgresql.PostgresConnector` | Debezium connector class |
| `database.hostname` | `db.internal` | PostgreSQL host address |
| `database.port` | `5432` | Port |
| `database.user` / `database.password` | From secrets | Replication credentials |
| `database.dbname` | `appdb` | Source database |
| `plugin.name` | `pgoutput` | Logical decoding plugin |
| `slot.name` | `spring_orders_slot` | PostgreSQL replication slot |
| `publication.name` | `orders_publication` | Publication containing observed tables |
| `publication.autocreate.mode` | `disabled` | Do not auto-create the publication when it already exists |
| `table.include.list` | `public.orders` | Read only permitted tables |
| `topic.prefix` | `orders_source` | Connector's logical event destination namespace |
| `snapshot.mode` | `initial` | Take an initial snapshot then stream |
| `offset.storage` | `org.apache.kafka.connect.storage.FileOffsetBackingStore` | Offset storage implementation |
| `offset.storage.file.filename` | `/var/lib/app/cdc/orders-offset.dat` | Path for durable offsets |
| `offset.flush.interval.ms` | `10000` | Interval to attempt offset flush |

**`topic.prefix` in the Embedded Engine does not mean the adapter automatically publishes to Kafka.** It is a logical name used to build the destination/topic field of change events. To send to Kafka, you need a downstream Kafka outbound adapter or to deploy the connector via Kafka Connect.

`offset.storage.file.filename` is only suitable for environments with a **durable filesystem dedicated to the engine**. A container with ephemeral disk loses the file when recreated; multiple pods sharing a single offset file without coordination is also not a safe HA design.

## 7. Configuring the Application with Spring Boot Properties

Example `application.yml` for the practice application:

~~~yaml
cdc:
  postgres:
    hostname: "localhost"
    port: 5432
    database: "appdb"
    username: "${CDC_DB_USER}"
    password: "${CDC_DB_PASSWORD}"
  slot: "spring_orders_slot"
  publication: "orders_publication"
  offset-file: "${CDC_OFFSET_FILE}"
~~~

`CDC_DB_USER` and `CDC_DB_PASSWORD` must be supplied outside Git, such as from a secret manager. `CDC_OFFSET_FILE` must point to a writable volume that persists across restarts if you want to resume. For local testing, you can use a dedicated directory like `./runtime/orders-offset.dat`, though the directory should be created beforehand.

**Do not copy this example as a complete production configuration**: you still need DB privileges, WAL settings, slot cleanup, TLS/certificates, lag monitoring, timeouts, shutdown handling, and retry policies.

## 8. Java DSL: A Spring IntegrationFlow Using the Debezium Inbound Adapter

The `Debezium.inboundChannelAdapter(Properties)` factory uses native Debezium configuration with appropriate JSON serialization, without requiring you to build a `DebeziumEngine.Builder` yourself.

~~~java
package com.example.cdc;

import java.util.Properties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.debezium.dsl.Debezium;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrdersCdcFlow {

    @Bean
    public IntegrationFlow ordersDebeziumInbound(
            @Value("${cdc.postgres.hostname}") String host,
            @Value("${cdc.postgres.port}") int port,
            @Value("${cdc.postgres.database}") String database,
            @Value("${cdc.postgres.username}") String username,
            @Value("${cdc.postgres.password}") String password,
            @Value("${cdc.slot}") String slotName,
            @Value("${cdc.publication}") String publication,
            @Value("${cdc.offset-file}") String offsetFile) {

        Properties config = new Properties();
        config.setProperty("name", "spring-orders-cdc");
        config.setProperty("connector.class",
            "io.debezium.connector.postgresql.PostgresConnector");
        config.setProperty("database.hostname", host);
        config.setProperty("database.port", Integer.toString(port));
        config.setProperty("database.dbname", database);
        config.setProperty("database.user", username);
        config.setProperty("database.password", password);
        config.setProperty("plugin.name", "pgoutput");
        config.setProperty("slot.name", slotName);
        config.setProperty("publication.name", publication);
        config.setProperty("publication.autocreate.mode", "disabled");
        config.setProperty("table.include.list", "public.orders");
        config.setProperty("topic.prefix", "orders_source");
        config.setProperty("snapshot.mode", "initial");

        config.setProperty("offset.storage",
            "org.apache.kafka.connect.storage.FileOffsetBackingStore");
        config.setProperty("offset.storage.file.filename", offsetFile);
        config.setProperty("offset.flush.interval.ms", "10000");

        return IntegrationFlow
            .from(Debezium.inboundChannelAdapter(config)
                .contentType("application/json")
                .enableBatch(false))
            .channel("ordersCdcInput")
            .get();
    }
}
~~~

The configuration above is **an embedded Debezium pipeline without a Spring poller**. When the application context starts, Spring manages the producer/engine lifecycle. The output channel `ordersCdcInput` needs a downstream consumer/handler; otherwise, sending messages may fail depending on the channel type.

**Version caution:** connector property lists and dependencies change across Debezium 2.x, 3.x, and different DB vendors. Cross-check the documentation for the exact version pinned by your dependency resolution; this example describes the PostgreSQL contract with `pgoutput` and a file offset store.

## 9. Receiving Change Events with ServiceActivator and DebeziumHeaders

In the default mode `enableBatch(false)` with JSON byte-array serialization, each event is typically converted into a Spring message with a `byte[]` payload. The `DebeziumHeaders.KEY` header holds the serialized key; `DebeziumHeaders.DESTINATION` indicates the logical destination.

~~~java
package com.example.cdc;

import java.nio.charset.StandardCharsets;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.debezium.support.DebeziumHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrdersCdcLogger {

    @ServiceActivator(inputChannel = "ordersCdcInput")
    public void onChange(Message<?> message) {
        Object destination =
            message.getHeaders().get(DebeziumHeaders.DESTINATION);

        Object keyHeader =
            message.getHeaders().get(DebeziumHeaders.KEY);
        String key = keyHeader instanceof byte[] data
            ? new String(data, StandardCharsets.UTF_8)
            : String.valueOf(keyHeader);

        Object payload = message.getPayload();
        if (payload instanceof byte[] bytes) {
            String json = new String(bytes, StandardCharsets.UTF_8);
            System.out.printf("destination=%s key=%s payload=%s%n",
                destination, key, json);
        } else {
            // E.g., tombstone / another payload format; do not cast blindly.
            System.out.printf("destination=%s key=%s type=%s%n",
                destination, key, payload.getClass().getSimpleName());
        }
    }
}
~~~

**This logger is for lab use.** In production, do not log full `customer_id`/`total_cents`/JSON payloads that may contain PII, customer identifiers, or secrets. The `payload` is not guaranteed to always be `byte[]` if batching, tombstones, or a different serialization format is enabled.

These headers are metadata from the Debezium change event, **not trusted OAuth/JWT headers for authorization**. Routing by destination and key should also use an allowlist because schemas/topics can change after migrations.

## 10. JSON Contract: Before/After, Operation Types, and Source Metadata

Debezium produces a **change event envelope**. For PostgreSQL, the serialized value typically contains `before`, `after`, `op`, `source`, `ts_ms`, and optionally transaction metadata. When JSON schemas are enabled, a `schema`/`payload` wrapper may be present:

~~~json
{
  "schema": {
    "type": "struct",
    "name": "orders_source.public.orders.Envelope"
  },
  "payload": {
    "before": null,
    "after": {
      "id": 101,
      "customer_id": "C-001",
      "status": "CREATED",
      "total_cents": 125000
    },
    "source": {
      "connector": "postgresql",
      "db": "appdb",
      "schema": "public",
      "table": "orders",
      "snapshot": "true",
      "lsn": 123456789
    },
    "op": "r",
    "ts_ms": 1730000000000
  }
}
~~~

This is an **abbreviated illustrative JSON**, not an exact copy of every field/schema for a specific connector version. In practice, schemas can be verbose and event formats vary by `converter.schemas.enable` and Debezium serialization settings. Do not hardcode the `root.payload` path while ignoring cases where the schema wrapper has been omitted.

Common `op` codes:

| `op` | Meaning | `before` | `after` |
|---|---|---|---|
| `r` | Snapshot read event | Usually null | Snapshotted row |
| `c` | CREATE/INSERT | Usually null | New row |
| `u` | UPDATE | Previous row, depending on config/replica identity | New row |
| `d` | DELETE | Old row (if source captures enough data) | Null |
| `t` | TRUNCATE if supported by connector and config | Not a normal row payload | Not a normal row payload |

**Note on PostgreSQL `REPLICA IDENTITY`:** if set to `DEFAULT`, `before` on UPDATE/DELETE may only contain key columns or limited data; do not assume the full pre-UPDATE row is always present. If business logic needs the entire before image, consider `REPLICA IDENTITY FULL` along with its WAL/storage cost.

**DELETE and tombstone are different:** an `op="d"` event has a payload with `before` and `after=null`; it may be followed by a **tombstone event** with a null/empty value used for log compaction. Both events must be handled according to distinct contracts.

## 11. Safely Parsing JSON and Creating a Domain Change Event

The handler uses Jackson to parse the event; before accessing `after.id`, it must check `op`, the schema wrapper, and nulls:

~~~java
package com.example.cdc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.stereotype.Component;

@Component
public class CdcJsonParser {

    private final ObjectMapper mapper;

    public CdcJsonParser(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public CdcOperation parse(byte[] jsonBytes) throws IOException {
        JsonNode root = mapper.readTree(jsonBytes);
        JsonNode envelope = root.hasNonNull("payload")
            ? root.path("payload") : root;

        String op = envelope.path("op").asText("");
        JsonNode before = envelope.path("before");
        JsonNode after = envelope.path("after");

        if (op.isBlank()) {
            throw new IllegalArgumentException(
                "Missing Debezium operation");
        }

        return new CdcOperation(
            op,
            before.isMissingNode() || before.isNull()
                ? null : before,
            after.isMissingNode() || after.isNull()
                ? null : after);
    }

    public record CdcOperation(
        String operation, JsonNode before, JsonNode after) { }
}
~~~

**Parse `DebeziumHeaders.KEY` separately** if you need the primary key. The key may be structured JSON containing `schema/payload`, not automatically plain text `101`. Use `StandardCharsets.UTF_8` and check for null/empty; do not rely on the platform default encoding.

Business routing example:

~~~java
CdcJsonParser.CdcOperation event = parser.parse(bytes);

switch (event.operation()) {
    case "r", "c" -> upsertProjection(event.after());
    case "u" -> upsertProjection(event.after());
    case "d" -> deleteProjection(event.before());
    default -> auditUnknownOperation(event.operation());
}
~~~

This is **pseudocode inside a method where `parser`, `bytes`, and the services are already defined**, not a standalone runnable application. When a snapshot re-runs, `r` events may overlap with already-staged data; `upsertProjection` should be idempotent and use versioning/ordering if concurrency exists.

## 12. Snapshot Then Streaming: First Startup

Debezium typically requires an **initial snapshot** to obtain the state of existing rows, then follows the transaction log for subsequent changes.

~~~mermaid
stateDiagram-v2
    [*] --> START
    START --> SNAPSHOT: snapshot.mode=initial, no offset yet
    SNAPSHOT --> STREAM: Snapshot completed
    START --> STREAM: Durable offset exists, can resume
    STREAM --> STREAM: WAL INSERT/UPDATE/DELETE
    STREAM --> STOP: Graceful shutdown
    STOP --> START: Restart using offset
~~~

| Scenario | Behavior to Understand |
|---|---|
| First start with `snapshot.mode=initial` | Connector normally snapshots existing data then streams |
| Restart with valid offset | Resumes from saved offset (with possible replay) |
| Offset file deleted | Risk of re-snapshotting or re-establishing an incorrect position |
| Required replication slot/WAL missing | Connector may fail to resume and require recovery |
| `snapshot.mode=no_data` | Only monitors changes from an appropriate position; does **not** capture pre-existing rows |
| Changing `table.include.list` | Capture scope changes; requires a migration/backfill plan |
| Initial snapshot under heavy DB writes | Requires understanding snapshot consistency and connector log catch-up |

Do not treat an `op="r"` event as a new business INSERT if it comes from a snapshot. If consumers must distinguish "already existed beforehand" from "created after connector startup", use `op` and the `source.snapshot` metadata accordingly.

**Do not use a manual `MAX(id)` cursor to replace Debezium's replication offset**. The offset belongs to the connector's log/snapshot position and has DB-vendor-specific semantics; manually editing the offset file without a runbook can cause lost or duplicate events.

## 13. Alternative Configuration: DebeziumEngine.Builder and DebeziumMessageProducer

Besides passing `Properties` to the DSL, Spring Integration accepts a **pre-configured `DebeziumEngine.Builder<ChangeEvent<byte[],byte[]>>`**. This is useful when the application has a dedicated service providing the engine builder, or when you need to customize serialization options, Debezium SMTs/predicates, or engine lifecycle settings.

~~~java
package com.example.cdc;

import io.debezium.engine.ChangeEvent;
import io.debezium.engine.DebeziumEngine;
import io.debezium.engine.format.JsonByteArray;
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DebeziumEngineBuilderConfiguration {

    @Bean
    public DebeziumEngine.Builder<ChangeEvent<byte[], byte[]>>
            postgresEngineBuilder(Properties postgresCdcProperties) {

        return DebeziumEngine.create(JsonByteArray.class)
            .using(postgresCdcProperties);
    }
}
~~~

**Prerequisite:** `postgresCdcProperties` is an application-provided `Properties` bean containing `name`, `connector.class`, `offset.storage`, and PostgreSQL connector properties similar to section 8. This is an **alternative configuration**, not a complete standalone class from just the snippet above.

Once you have the builder, create the message producer:

~~~java
package com.example.cdc;

import io.debezium.engine.ChangeEvent;
import io.debezium.engine.DebeziumEngine;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.debezium.inbound.DebeziumMessageProducer;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageProducer;

@Configuration
public class DebeziumProducerBeans {

    @Bean
    public MessageChannel ordersCdcDirect() {
        return new DirectChannel();
    }

    @Bean
    public MessageProducer ordersDebeziumProducer(
            DebeziumEngine.Builder<ChangeEvent<byte[], byte[]>> builder,
            @Qualifier("ordersCdcDirect") MessageChannel channel) {
        DebeziumMessageProducer producer =
            new DebeziumMessageProducer(builder);
        producer.setContentType("application/json");
        producer.setEnableBatch(false);
        producer.setOutputChannel(channel);
        return producer;
    }
}
~~~

**Important:** `DebeziumEngine.create(JsonByteArray.class)` selects `byte[]`-based JSON and is compatible with `ChangeEvent<byte[],byte[]>`. If you use Debezium Engine's `Json.class`, the event type is typically `ChangeEvent<String,String>`; do not cast a `String` builder to `byte[]` and pass it to the constructor above. Debezium may choose a different asynchronous engine implementation depending on the version, but the builder API must still match the generic format.

This is an **alternative setup** to `IntegrationFlow.from(Debezium.inboundChannelAdapter(config))`. Do not register both producers on the same slot/config simultaneously; two engines competing for the same replication slot and offset can cause errors or duplicates.

### 13.1. Connecting the Producer to a Handler

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;

@ServiceActivator(inputChannel = "ordersCdcDirect")
public void consume(Message<?> message) {
    // Parse JSON bytes, classify op, and durably persist work.
}
~~~

This is a **method snippet** to place inside a Spring `@Component` or appropriate bean. If you want to attach a filter/router/service activator using the DSL, you can use `IntegrationFlow.from("ordersCdcDirect")...` in a separate configuration, ensuring you have the **exact intended subscriber** on the `DirectChannel`.

## 14. Configuring Headers, Content Type, and Routing

`DebeziumMessageProducer` supports these options:

| Option | Default / Meaning |
|---|---|
| `contentType` | Defaults to JSON; can be AVRO/PROTOBUF, must match Engine's `SerializationFormat` |
| `enableBatch(false)` | Each `ChangeEvent` becomes a separate message |
| `enableBatch(true)` | One message containing the Engine batch's `List<ChangeEvent>` |
| `enableEmptyPayload(false)` | Drops/skips tombstone empty-value events |
| `headerMapper` | Maps Debezium event headers into Spring message headers |
| `headerNames(...)` DSL | Selects event header names to map |
| `taskExecutor(...)` | Uses a `TaskExecutor` for the Engine |
| `errorChannel(...)` | Configures the message producer error channel mechanism per framework capabilities |

Java DSL example:

~~~java
// Snippet placed inside IntegrationFlow.from(...).
Debezium.inboundChannelAdapter(config)
    .contentType("application/json")
    .enableBatch(false)
    .enableEmptyPayload(true)
    .headerNames("trace*", "tenant*");
~~~

The patterns in `headerNames` filter **Debezium event headers**, not which tables to CDC. To choose tables, configure `table.include.list` on the connector; to route or filter messages by `DebeziumHeaders.DESTINATION`, use a Spring Integration filter or router downstream.

`DebeziumHeaders.KEY` holds the event key, and `DebeziumHeaders.DESTINATION` is the logical destination name (typically derived from `topic.prefix`, schema, and table). Do not assume every Debezium event header is a business header; enforce trust, size, and serialization rules.

### 14.1. Content Type Must Match Serialization

If the engine builder uses `JsonByteArray`, the handler can receive `byte[]`. If you switch to `Avro` or `Protobuf`, do not run `new String((byte[]) payload)` and treat it as JSON; you need the proper deserializer/schema registry or mapping.

**Do not set `contentType("application/avro")` just to change a header while the Engine still serializes JSON.** Content type is a contract between the producer and downstream consumers and must match the actual bytes.

## 15. Batch Mode: A List<ChangeEvent>, Not a List<byte[]>

The Spring Integration Debezium adapter has two message-emission modes:

~~~text
enableBatch(false): default
  Debezium ChangeEvent 1 -> Message<byte[]> 1
  Debezium ChangeEvent 2 -> Message<byte[]> 2
  Debezium ChangeEvent 3 -> Message<byte[]> 3

enableBatch(true):
  Debezium batch [event1,event2,event3]
       -> one Message<List<ChangeEvent>>
~~~

**Limitation highlighted by the official documentation:** when `enableBatch(true)` is enabled, the payload is a **non-serializable `List<ChangeEvent>`** per the adapter contract. By default, it is unsuitable for sending through a persistent message store, a Redis/JMS serializer, or a JSON transformer expecting a simple Java bean.

To process in-process:

~~~java
package com.example.cdc;

import io.debezium.engine.ChangeEvent;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class BatchCdcHandler {

    @ServiceActivator(inputChannel = "ordersCdcBatches")
    public void onBatch(Message<?> message) {
        if (!(message.getPayload() instanceof List<?> events)) {
            throw new IllegalArgumentException("Expected List");
        }
        for (Object candidate : events) {
            if (!(candidate instanceof ChangeEvent<?, ?> event)) {
                throw new IllegalArgumentException(
                    "Expected Debezium ChangeEvent");
            }
            Object value = event.value();
            if (value instanceof byte[] bytes) {
                String json =
                    new String(bytes, StandardCharsets.UTF_8);
                // Parse/store/idempotent handler: don't just print.
                handleJson(json);
            } else {
                handleTombstoneOrFormat(value);
            }
        }
    }

    private void handleJson(String json) {
        // Application-specific durable processing.
    }

    private void handleTombstoneOrFormat(Object value) {
        // Handle empty value / other format per contract.
    }
}
~~~

**This snippet only applies when the flow is configured with `enableBatch(true)` and an output channel named `ordersCdcBatches`.** The `ordersCdcInput` example in sections 8/9 uses `enableBatch(false)`, so do not connect a batch-style handler directly to it. If you need to turn the list into individual messages, write a splitter/transformer with explicit tombstone and serialization policies.

### 15.1. Do Not Confuse Debezium Batch with JdbcMessageHandler Batch

| Component | What Does "Batch" Mean? |
|---|---|
| Debezium Engine | Multiple change records delivered to a single callback |
| Debezium inbound `enableBatch(true)` | One `Message<List<ChangeEvent>>` |
| Spring `Aggregator` | Groups messages according to custom rules |
| JDBC outbound `JdbcMessageHandler` | Can run `batchUpdate` when payload is an `Iterable` per the JDBC contract |
| Kafka producer | Batches records for network/protocol efficiency |

`Message<List<ChangeEvent>>` **is not a `List<InventoryUpdate>`** ready for JDBC outbound SQL. You must parse, validate, transform, and extract keys/types before passing data to a JDBC batch. Never pass raw `ChangeEvent` objects directly into a `PreparedStatement` setter designed for domain DTOs.

## 16. DELETE and Tombstone: Do Not Conflate the Two Events

When a row is deleted (`DELETE`), Debezium can emit:

1. **Delete event:** an envelope with `op="d"`, `before` populated (depending on connector/replica identity), and `after=null`.
2. **Tombstone event:** the same key with a null/empty value, used for Kafka log compaction or other downstream protocols.

Depending on Debezium connector settings, tombstones can be enabled or disabled. In the Spring Integration adapter, **`enableEmptyPayload(false)` is the default**, meaning tombstones are not forwarded automatically. When you need to forward this event type, enable:

~~~java
Debezium.inboundChannelAdapter(config)
    .enableEmptyPayload(true);
~~~

**Note:** Spring Messaging does not allow a plain `null` payload; according to the Debezium adapter API, a tombstone/empty value is represented by contract as **`Optional.empty()`**. Handlers must check the type before casting to `byte[]`.

~~~java
import java.util.Optional;
import org.springframework.messaging.Message;

void handle(Message<?> message) {
    Object payload = message.getPayload();
    if (payload instanceof Optional<?> option && option.isEmpty()) {
        // Tombstone: handle per compaction / cache entry deletion policy.
    } else if (payload instanceof byte[] bytes) {
        // Change-event JSON; check op, before/after.
    } else {
        // Unexpected format: log metadata safely and classify.
    }
}
~~~

This is a **method snippet**, not a full class. Do not assume every empty/null payload represents a DELETE: an unexpected value can also result from serialization, converter, or schema errors.

If the downstream sink is a cache or search index, `op="d"` is usually enough to delete by business key; if the downstream sink is a log-compacted Kafka topic, tombstones serve a distinct role. Define a policy per sink and never silently drop DELETEs.

## 17. Offset Store: Replacing "Last Read Position" in JDBC Polling

The Debezium Engine must persist a **source offset** to track how far it has read/marked processing. On PostgreSQL, this position relates to WAL/LSN, snapshot state, and connector metadata; it is unlike `last_id` in JDBC polling.

~~~text
PostgreSQL WAL change stream:
    ... LSN A --- LSN B --- LSN C ...
                   |
                   +--- Debezium Engine offset
                          |
                          +--- FileOffsetBackingStore / other durable store
~~~

Lab configuration:

~~~properties
offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
offset.storage.file.filename=/var/lib/app/cdc/orders-offset.dat
offset.flush.interval.ms=10000
~~~

**Important on restart:**
- The file requires a **durable volume**. If a pod is deleted along with an ephemeral local disk, the offset is lost.
- The Engine flushes offsets periodically; a process crash can cause some change records to be **replayed**.
- An offset file does not protect downstream Kafka/HTTP/DB commits; the offset and business side effects belong to two independent resources.
- Do not share the same offset file concurrently across multiple engines without locking/ownership coordination.
- Do not manually edit offsets or drop a replication slot to "fix lag" without a reconciliation runbook.

Debezium supports other offset backing stores (such as JDBC, Kafka, or Redis depending on version and dependencies). Pick the right storage for your connector/engine version and system; `FileOffsetBackingStore` is only suited to simple workloads/lifecycles or environments with controlled persistent volumes.

## 18. Engine Acknowledgment Does Not Mean Downstream Has Committed

The Debezium Engine has an advanced processing API with `ChangeConsumer<R>` and `RecordCommitter<R>`. When managing the Engine directly, the consumer calls `markProcessed(record)` per record and `markBatchFinished()` after a batch to inform the Engine that processing succeeded, allowing the Engine to flush offsets according to its policy.

~~~java
// Pseudocode when using DebeziumEngine.ChangeConsumer directly;
// NOT a callback exposed by the DebeziumMessageProducer public API.
for (ChangeEvent<?, ?> event : records) {
    durableStage(event);  // write DB/outbox or remote confirmation per policy
    committer.markProcessed(event);
}
committer.markBatchFinished();
~~~

`DebeziumMessageProducer` **wraps the Engine** and does not automatically turn every `MessageChannel`, executor, or Kafka outbound into a single unified transaction. You must check the implementation/version of the adapter and Debezium Engine to determine exactly when callbacks/offsets are marked. Never assume `message sent` = `consumer business commit`.

Example of three failure windows:

| Point in Time | What Can Happen | Mitigation |
|---|---|---|
| Event read, offset not yet flushed | Event is re-read after restart | Idempotency/deduplication |
| Offset advanced/flushed, async work not yet durable | Work lost after crash | Durable staging before async boundary or custom ack design |
| Downstream Kafka receives message, app dies before ack/offset | May be republished | Stable event ID, idempotent consumer |

**Safety principle:** treat a CDC source as **at-least-once** unless an end-to-end contract is proven. Avoid fire-and-forget into an in-memory queue and relying on offsets to guarantee zero record loss.

## 19. Transaction Boundaries with DirectChannel, ExecutorChannel, and Brokers

~~~mermaid
flowchart LR
    A["Debezium Engine callback"] --> B["DebeziumMessageProducer"]
    B --> C["DirectChannel"]
    C --> D["Synchronous JDBC stage/outbox"]
    D --> E[("Local DB commit")]
    B --> X["ExecutorChannel"]
    X --> Y["Async worker"]
    Y --> Z["Separate TX / separate retry"]
~~~

| Stage | What Can Be Guaranteed | What Is Not Automatically Guaranteed |
|---|---|---|
| `DirectChannel` to JDBC handler | Handler runs synchronously on the caller thread | An active JDBC transaction without opening one |
| `@Transactional` service in handler | Service DML shares a local DB transaction | Atomicity between Debezium offset and DB commit |
| `ExecutorChannel` | Offloads compute/I/O to a worker | Engine offset waiting until the worker finishes |
| In-memory `QueueChannel` | Buffers between producer and consumer | Durability across a JVM crash |
| Kafka outbound adapter | Sends events to broker per client contract | Downstream consumer finishing processing |
| JMS outbound adapter | Sends messages to JMS broker | Atomicity between local PostgreSQL offset/LSN and JMS commit |

**There is no single Spring transaction that automatically spans the PostgreSQL logical replication offset, a target database SQL UPDATE, and a Kafka/JMS ACK**. If the business cannot tolerate lost events, persist a durable inbox/outbox and design explicit retry/ack handling.

A common strategy: keep the CDC handler **fast**, parse/validate, write an `inbox_event` to the database with a unique event identifier, commit, and let another worker publish to Kafka/HTTP. Keep in mind, however, that **inbox durability must be guarded relative to offset acknowledgment**, rather than merely placing `@Transactional` on an arbitrary method.

## 20. Idempotency: CDC Does Not Default to Exactly-Once Business Effects

When offset flushing and downstream commits are two separate steps, events may be replayed. A safe consumer must determine an **event/version identifier**.

**Do not use only the row's primary key as the event ID** if multiple distinct UPDATEs happen on the same row. Primary key `orders.id=101` only identifies the **aggregate**, not the transition from CREATED → PAID versus PAID → SHIPPED.

| Key | Suitable For | Notes |
|---|---|---|
| `DebeziumHeaders.KEY` | Identifying the row/partition | Does not distinguish separate UPDATEs on its own |
| `source.lsn` | WAL position/connector metadata | A single LSN is not always a unique event ID across all connectors |
| `source.txId` + order metadata | Assisting ordering/reconciliation | Check uniqueness/scoping per connector |
| Business `event_id` in outbox | Business event deduplication | Stable and unique across retries |
| `(aggregateId, version)` | Idempotent versioned projection/upsert | Requires a monotonically increasing version per aggregate |

When business events are needed, a **transactional outbox** lets you write `event_id` in the same business transaction. Debezium captures the outbox table and downstream consumers deduplicate using that `event_id`, optionally adding Debezium's EventRouter SMT if it fits the contract.

Idempotent inbox example:

~~~sql
CREATE TABLE processed_cdc_event (
    event_id     VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Within **a single local consumer DB transaction**:
1. Check/insert the processed event ID using the unique constraint.
2. If it already exists and the payload matches, treat it as a redelivery (no second side effect).
3. If it is new, apply the business UPDATE and insert the marker in the **same transaction**.
4. Commit before ACKing the source according to the actual delivery policy.
5. For remote Kafka/HTTP side effects, use an outbox or remote idempotency key.

Do not `INSERT` into `processed_cdc_event` and commit separately **before** the business operation: crashing between the two steps would cause a retry to be treated as a duplicate even though the business change was never applied.

## 21. Deploying Multiple Replicas: One CDC Source Is Not Multiple Work-Sharing Pollers

A system with three Spring Boot pods all auto-starting `DebeziumMessageProducer` with the **same `slot.name`** will contend for the logical replication slot or fail because the slot is already active. If each pod uses its own slot on the same DB/tables, all three will receive the **same changes**, causing duplicate publishes and increased WAL retention.

| Architecture | Recommendation |
|---|---|
| Single app instance with embedded Engine | Simplest for small workloads |
| Multiple app pods, only one active engine | Leader election/lock with controlled failover |
| Multiple independent CDC pipelines | Each pipeline has its own identity/slot/offset and downstream contract |
| Dedicated HA/connector orchestration needed | Kafka Connect cluster or Debezium Server/Operator depending on goals |
| High downstream throughput needed | Single CDC reader → durable queue/Kafka → multiple partitioned consumers |

**Do not create an Engine per HTTP request or per integration message.** The Engine is a long-running component with startup, snapshot, replication slot, offset, and shutdown lifecycles; Spring manages the producer's `SmartLifecycle`.

**Standby/failover setups must keep offsets and slots consistent.** Starting a standby while the primary is still running is not safe HA if two engines can simultaneously emit the same stream. Establish single-reader ownership and define how to verify failover before restarting.

## 22. Graceful Shutdown and Startup Lifecycle

`DebeziumMessageProducer` extends `MessageProducerSupport` and is a Spring-managed lifecycle endpoint. When started, the engine runs on a `TaskExecutor` (default decided by the adapter); when stopped, the engine needs time to complete callbacks and flush offsets.

**For Kubernetes:**
- Configure a graceful termination period long enough for the Engine to stop, close connections, and flush offsets.
- Do not force-kill immediately on SIGTERM; the pod may replay records on restart.
- Configure liveness/readiness probes based on actual connector/lag state; avoid overly sensitive liveness probes that trigger restart loops.
- Do not leave unused replication slots around indefinitely; maintain a runbook and DBA permissions for proper cleanup.
- Persistent offset storage (if file-based) must be mounted before the Engine starts; verify read/write permissions.
- If PostgreSQL requires mTLS/TLS, configure the connector/driver and secret rotation for your version.

### 22.1. Specifying a TaskExecutor

~~~java
import org.springframework.core.task.TaskExecutor;

// Java bean configuration snippet from section 13:
producer.setTaskExecutor(debeziumTaskExecutor);
~~~

In Java DSL, use `.taskExecutor(debeziumTaskExecutor)`. `debeziumTaskExecutor` should be a Spring `TaskExecutor` bean suitable for long-running tasks; do not use an executor that can be saturated by request handlers or lacks capacity. With Debezium 3.x, the default Engine implementation may be **AsyncEmbeddedEngine**, so check the Engine's own concurrency model, not just the Spring executor name.

### 22.2. Do Not Confuse Thread Management with Delivery Guarantees

Switching `TaskExecutor` to a large thread pool **does not** allow a single PostgreSQL logical slot to distribute records evenly across multiple reader instances, nor does it guarantee ordering or exactly-once delivery. Improving throughput requires measuring bottlenecks in source decoding, serialization, transformation, channels, DB sinks, and brokers.

## 23. When to Choose Batch Mode vs. Per-Message Mode

| Criterion | `enableBatch(false)` | `enableBatch(true)` |
|---|---|---|
| Payload | Typically JSON `byte[]` | `List<ChangeEvent>` |
| Isolating per-event errors | Easier | Requires a batch error policy |
| Passing each event through router/filter | Direct | Requires a splitter or batch processor |
| Memory | Lower batch retention | Can hold many events in RAM |
| Serialization across channels/stores | Easy to map to a JSON domain DTO | Raw `List` is not serializable |
| Throughput | Spring message overhead per event | Fewer Spring messages, but custom batch parsing |
| Retry | Per-event policy | Must distinguish single-record vs. full-batch failure |
| Tombstones | Per-event handler | Must handle null/empty values inside the list |

**Concrete scenario:** a CDC batch has 200 events, and event #73 has an invalid schema. If the adapter emits the list and the handler throws an exception, the business must choose whether to roll back the entire batch, quarantine event #73, or split items. Never decide simply by raising `enableBatch` without handling poison messages and offset consistency.

A batch from the Debezium Engine **does not correspond to a single source DB transaction**: batch sizes and transaction boundaries can differ. When a consumer requires atomicity per business transaction, use source transaction metadata/aggregation rather than treating every batch as one source transaction.

## 24. Schema Compatibility: Update, Rename, Add Column

CDC consumers are often coupled to row structure. When a DBA alters a schema:

- Adding a nullable column: parsers should ignore unknown fields or handle defaults.
- Adding a NOT NULL column: snapshots/streams may contain two shapes over time; versioning rules are needed.
- Renaming a column: `after.oldName` disappears and `after.newName` appears; consumers hardcoding the old field will fail.
- Changing numeric/timestamp types: Java `long`/`BigDecimal`/ISO timestamps may become incompatible.
- Changing the primary key: `DebeziumHeaders.KEY` and compacted Kafka topic semantics may change.
- Changing `REPLICA IDENTITY`: `before` data for UPDATE/DELETE may change.
- Connector schema history: MySQL/SQL Server/Oracle may require a dedicated history store to decode events at the schema point in time.

**Distinguish offset from schema history:** PostgreSQL `pgoutput` generally does not need a MySQL-style schema history store in the embedded engine example; however, with the MySQL connector you must configure `schema.history.internal` and durable history storage. Do not copy `schema.history.internal.file.filename` from MySQL to PostgreSQL assuming it is required for every DB vendor.

For JSON with a schema wrapper, version/validate the full event contract, not just `after.id` via a hardcoded path.

## 25. Connection Errors, Handler Exceptions, and Retries

A CDC pipeline can fail at multiple layers:

| Layer | Typical Failure | Response |
|---|---|---|
| PostgreSQL | DB unreachable, missing replication privilege | Alert, bounded connection retries |
| Logical replication | Slot active in another process, wrong publication | Check ownership/DBA; do not blindly drop the slot |
| WAL retention | Offset points to purged log segments | Re-snapshot/rebuild/reconcile per runbook |
| Debezium Engine | Serializer/connector crash, config mismatch | Capture diagnostics, manage Engine lifecycle |
| Spring adapter | Header/payload/tombstone mapping error | Ensure handler matches message/serialization format |
| Downstream parser | Invalid JSON/schema, missing op/id | Validation/quarantine; avoid infinite retry loops |
| JDBC sink | Deadlock/constraint/connection timeout | Roll back unit of work, retry with backoff |
| Kafka/JMS outbound | ACK timeout or uncertain outcome | Outbox, stable event ID, reconciliation |
| Async channel | Full queue or worker dies after handoff | Bounded buffer, durable staging |
| Shutdown | Killed before offset flush | Graceful stop and idempotent replay |

**Do not assume every exception in a `@ServiceActivator` turns into a business reply.** Inbound CDC is a stream/producer, not a request-reply gateway. Some errors may be logged, routed to `errorChannel`, or cause the connector to stop or continue depending on the API/version; test on your exact version and classify failures.

### 25.1. An Error Channel Does Not Replace Durable Retry

`DebeziumMessageProducer` extends `MessageProducerSupport` and can be configured with an `errorChannel`. This is Spring Integration's error-reporting mechanism, but it **does not** guarantee a Debezium change record will be redelivered before the Engine advances its offset.

Conceptual example:

~~~java
// Java DSL snippet in source configuration:
Debezium.inboundChannelAdapter(config)
    .errorChannel("cdcErrors");
~~~

A `cdcErrors` handler can log the exception type, `failedMessage` metadata, and send alerts. Do not merely call `logger.error(...)` and ACK away the event. If losing business effects is unacceptable, design durable staging/idempotency before the async boundary, or manage the Engine directly with `ChangeConsumer/RecordCommitter` under a tested protocol.

### 25.2. Preventing Poison Messages from Blocking Indefinitely

When an event fails to parse due to a schema mismatch:
- **Do not** retry the same JSON 1,000 times per second; that causes a retry storm.
- Do not discard the event and mark it succeeded if the domain requires retaining the data.
- Record event metadata, destination, key, source position, and root cause into a **durable** quarantine/DLQ; avoid logging PII.
- Choose a policy that supports replay after fixing the schema, preserving source offset or unique event ID where appropriate.
- For transient DB/broker errors, use exponential backoff + jitter and circuit breakers/rate limiting when needed.

**Define "processed" upfront:** parsed? staged in inbox? committed to read model? published to Kafka? Which milestone authorizes the connector to advance its offset?

## 26. Backpressure and Memory: Being Too Fast Is Also Dangerous

A CDC stream can arrive faster than downstream processing can keep up. If the adapter connects to a `DirectChannel` with a slow JDBC/HTTP handler, the callback thread stalls while WAL/offset lag grows. Conversely, routing immediately into an unbounded `ExecutorChannel` can spawn thousands of queued tasks in memory and trigger an OOM crash.

~~~mermaid
flowchart LR
    E["Engine callback"] --> M["Spring Message"]
    M --> D{"Downstream"}
    D -->|"DirectChannel"| S["Synchronous handler / latency"]
    D -->|"Async channel"| Q["Executor queue (bounded)"]
    Q --> W["Workers"]
    W --> B[("DB / Kafka sink")]
    S --> B
~~~

**Backpressure policies must be chosen explicitly:**
1. Use a bounded executor/queue when offloading I/O; define behavior when the queue is full.
2. Persist to a **durable inbox/outbox** before considering a record durably received.
3. Measure source/handler throughput and lag, not only executor queue depth.
4. Avoid holding entire `List<ChangeEvent>` payloads across stages that cannot serialize them.
5. Tune Debezium Engine/connector batch, queue, and poll/heartbeat settings **for your exact connector version**.
6. If a sink is down for an extended time, manage WAL retention; never expand in-memory buffers indefinitely just to hide lag.

**Do not treat `FluxMessageChannel` or Reactor types as a non-blocking magic wand.** PostgreSQL connector/replication clients and JDBC sinks have blocking parts; thread-bound JDBC transactions do not automatically propagate across reactive/async boundaries.

## 27. Monitoring Replication Slots, WAL, and Offset Lag on PostgreSQL

A stalled CDC subscription can cause a replication slot to retain WAL segments. Monitor:
- Whether the slot is `active`, and which process is consuming it.
- `restart_lsn` and `confirmed_flush_lsn`.
- Potentially retained WAL size (`pg_wal_lsn_diff` against `restart_lsn`).
- Snapshot duration / stream lag; source DB CPU and network.
- Debezium Engine errors and last successfully processed record timestamp.
- Spring Integration message throughput and latency.
- Downstream inbox/outbox pending age and DLQ counts.
- Failover results, offset restores, and replayed duplicates.

~~~sql
-- PostgreSQL; requires permission to query pg_replication_slots.
SELECT slot_name,
       plugin,
       active,
       restart_lsn,
       confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_name = 'spring_orders_slot';
~~~

~~~sql
-- Estimate WAL bytes retained in connection with this slot.
SELECT slot_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
           AS retained_wal_bytes
FROM pg_replication_slots
WHERE slot_name = 'spring_orders_slot'
  AND restart_lsn IS NOT NULL;
~~~

These are **supporting alert indicators**, not the sole definition of CDC lag. Actual behavior depends on replication state, lag, and WAL retention policies; also check `pg_stat_replication`, DB metrics, and Debezium connector metrics. Never drop a replication slot holding WAL just because disk alerts fire: if the offset still points to purged logs, the connector may fail to resume and unread events can be lost.

### 27.1. Application Metrics

| Metric | Meaning |
|---|---|
| `cdc_messages_received` | Number of Spring Messages emitted by the producer |
| `cdc_operations` by `r/c/u/d` | Distribution of snapshot/stream/change operations |
| `cdc_parse_failures` | Schema/format errors |
| `cdc_ingest_latency` | Time from source timestamp to inbox commit |
| `cdc_snapshot_progress` | Snapshot progress reported by the connector |
| `cdc_offset_flush_errors` | Failures persisting offsets |
| `cdc_slot_wal_retained_bytes` | WAL retention risk caused by the replication slot |
| `cdc_inbox_oldest_age` | Slow downstream processing |
| `cdc_outbox_publish_retries` | Broker/sink delivery issues |
| `cdc_duplicate_detected` | Replay/idempotency activity |
| `cdc_engine_running` | Engine liveness (distinct from HTTP app health) |

Do not use `orderId`/`customerId` as high-cardinality metric tags. IDs belong in controlled logs/traces only; avoid printing sensitive full `payload_json` when debugging a CDC case.

## 28. Security and Compliance for CDC

CDC can replicate **entire rows and sensitive data** outside the database. Before enabling `table.include.list`:

- Inventory PII, secrets, tokens, and payment data in the tables.
- Use table/column include/exclude options or SMT masking to transmit only necessary fields.
- Block or encrypt/tokenize fields before they reach Kafka/JMS/search indexes.
- Grant least-privilege DB `REPLICATION` and `SELECT` rights; never embed passwords in source repositories.
- Protect offset files and schema history with filesystem permissions and encryption where appropriate.
- Connect to the DB using TLS/certificate verification, and manage certificate and secret rotation.
- Define retention/TTL policies for inbox/outbox/replicated data to meet regulatory requirements.
- Apply destination/schema allowlists and validate JSON before triggering side effects.
- Verify tombstone/delete policies when data must be purged from caches, indexes, and sink storage.

**A schema change can accidentally expose a newly added sensitive column into the CDC stream** if consumers/loggers serialize the whole `after` object. Versioning and data classification must be part of deployment reviews, not left solely to the Java parser.

## 29. Unit Testing: Parser, Operations, and Tombstones

You do not need a real database to test a parser handling `r/c/u/d` and schema wrappers. A unit test using Jackson:

~~~java
package com.example.cdc;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class CdcJsonParserTest {

    @Autowired
    CdcJsonParser parser;

    @Test
    void parsesAnUpdateEnvelope() throws Exception {
        String json = """
            {
              "payload": {
                "before": {"id":101, "status":"CREATED"},
                "after":  {"id":101, "status":"PAID"},
                "op":"u",
                "source":{"table":"orders"}
              }
            }
            """;

        var change = parser.parse(
            json.getBytes(StandardCharsets.UTF_8));

        assertEquals("u", change.operation());
        assertEquals("CREATED",
            change.before().path("status").asText());
        assertEquals("PAID",
            change.after().path("status").asText());
    }
}
~~~

Similarly, test:
1. Event `op="r"` with `before=null`.
2. Event `op="c"` with `after` and a key.
3. Event `op="d"` with `after=null`.
4. Tombstone values that are not JSON bytes; the handler must branch before calling the parser.
5. JSON missing `op` or missing `id` must be clearly classified.
6. JSON without a `schema/payload` wrapper must also parse.
7. UPDATE event where `before` lacks non-key columns.
8. `after` containing a new column without causing unexpected parser errors.
9. `DebeziumHeaders.KEY` containing a JSON schema/value instead of a plain `long`.
10. Sensitive fields not appearing verbatim in error logs.

**This is a unit/bean-context test of the parser; it does not prove the Debezium Engine can actually read WAL.** Replication tests require PostgreSQL or a real test database.

## 30. PostgreSQL CDC Integration Testing with Testcontainers

Prerequisites before end-to-end testing:
- PostgreSQL running with `wal_level=logical` and sufficient `max_replication_slots`/`max_wal_senders`.
- User/role with replication and SELECT privileges on the target table.
- Valid publication, replication slot, and `table.include.list`.
- Offset store placed in an isolated test directory with read/write permissions.
- Only **one Debezium Engine** consuming the test slot.
- Tests use an asynchronous wait mechanism for events rather than guessing with fixed `Thread.sleep` calls.

### 30.1. PostgreSQL Container with Logical Replication

~~~java
// Template test setup, not a complete test class.
import org.junit.jupiter.api.Test;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class PostgresDebeziumCdcIT {

    @Container
    static final PostgreSQLContainer postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("appdb")
            .withUsername("testuser")
            .withPassword("testpass")
            .withCommand("postgres",
                "-c", "wal_level=logical",
                "-c", "max_replication_slots=5",
                "-c", "max_wal_senders=5");

    @Test
    void capturesInsertUpdateDelete() {
        // Initialize schema/role/publication in the test DB,
        // build separate Engine config with an ephemeral test offset,
        // start the integration context, execute SQL changes,
        // await messages via a bounded QueueChannel/test probe,
        // assert op c/u/d + headers, then stop the engine.
    }
}
~~~

**This is a directional template for Testcontainers 2.x**; it omits bootstrap SQL/roles, dynamic properties, test probes, and assertions. If your application uses Testcontainers 1.x, dependency coordinates and legacy imports differ (e.g., `org.testcontainers:postgresql`, `org.testcontainers.containers.PostgreSQLContainer<?>`); do not mix two major versions. In particular, `testuser` may not have full replication/publication rights across all images/environments. Use appropriate lab privileges or run setup via an admin connection, and never carry a test-only superuser into production.

### 30.2. Integration Test Matrix

| Scenario | What to Verify |
|---|---|
| First start with `snapshot.mode=initial` | Receives `r` events for existing rows |
| INSERT after snapshot | Receives `op="c"` with `after` |
| UPDATE | Receives `op="u"`; handles `before` per replica identity |
| DELETE | Receives `op="d"`; tombstone per config |
| `enableBatch(false)` | Single-event `byte[]` payload |
| `enableBatch(true)` | `List<ChangeEvent>` payload |
| Durable offset across process restart | Valid resume, with controlled replay if applicable |
| Offset file missing | Resnapshot/recovery behavior is defined |
| Engine already holding slot | Second engine must not be assumed to share the slot |
| Publication omits table | Detect zero events caused by DB config |
| Event contains added column | Consumer does not break on unused fields |
| Handler failure / transient DB outage | Actual error policy, offset/retry/idempotency behavior |
| Full queue under slow sink | Bounded buffer, no OOM |
| Kafka/JMS sink timeout | Reconciliation / durable inbox-outbox guarantees |
| Increasing WAL lag | Alerts fire before retention causes an outage |

**Do not run multiple integration tests in parallel sharing the same `slot.name` and offset file** unless intentionally testing collisions. Give each test suite its own slot/publication/offset path or an isolated database. Clean up test slots and volumes after safely stopping the Engine.

## 31. Crash/Restart and Redelivery: The Most Reliable Test

~~~mermaid
sequenceDiagram
    participant DB as PostgreSQL
    participant C as Debezium + Spring Integration
    participant I as Durable inbox
    participant S as Downstream service
    DB-->>C: Change event E1
    C->>I: INSERT inbox(E1)
    I-->>C: COMMIT
    Note over C: Process killed before offset flush
    DB-->>C: Replays E1 after restart
    C->>I: INSERT inbox(E1) second time
    I-->>C: Unique event ID conflict (valid duplicate)
    I->>S: One worker processes E1 per policy
~~~

Fault-injection tests should simulate:
1. Crash **before** the handler receives the event: Engine resumes and re-reads from the saved offset.
2. Crash **after inbox COMMIT before offset flush**: event replays; inbox unique constraint prevents duplicate staging.
3. Crash **after offset flush but before async worker processes**: if the inbox is not durable, work can be lost; verify the design does not rely on an in-RAM queue.
4. Kafka receives the message but publisher crashes **before** marking the outbox published: may republish; consumer is idempotent.
5. Replication slot dropped or WAL purged: re-snapshot/backfill runbook protects against missing data.
6. Leader pod dies and standby starts: never run two engines using the same slot concurrently and never skip offsets.
7. Schema changes during snapshot/streaming: consumer handles format evolution.
8. Network failure between snapshot and streaming: connector resumes accurately per version semantics.

**Do not conclude end-to-end exactly-once just because a single test produced no duplicates.** Separate commit/ACK/offset windows make at-least-once plus idempotency the safer assumption.

## 32. Quick Troubleshooting by Symptom

| Symptom | Possible Cause | Inspection Step |
|---|---|---|
| No events at all | Publication/slot/table include, DB permissions, or snapshot mode | DB logs, connector startup, `pg_replication_slots` |
| Only `r` snapshots, no `c/u/d` | WAL streaming not running / connector error | Connector metrics, slot confirmed flush, WAL |
| Java `ClassCastException` on payload | Batch/tombstone/different format enabled | Check `enableBatch`, `enableEmptyPayload`, `contentType` |
| Null key header | Source table lacks PK / different format | Key mapping, table key constraint |
| `before` missing columns | PostgreSQL replica identity/config | Check `REPLICA IDENTITY` and connector docs |
| Duplicate events on restart | Offset not yet flushed / at-least-once delivery | Deduplicate via event ID / aggregate version |
| Database disk growing | Replication slot retaining WAL | WAL retained bytes, lag, and consumer health |
| Multiple pods fail with slot active | Duplicate CDC engine / ownership conflict | Single-leader protocol |
| Consumer backlog growing | Slow JDBC/Kafka sink | Queue, pool, sink latency, rate limiting |
| Avro/Protobuf deserialization error | `contentType` mismatches Engine serialization | Converter/format and schema registry |
| Consumer drops DELETEs | `op=d` / tombstone not handled | Check stream and `enableEmptyPayload` |
| Infinite retries on same event | Poison message / schema conflict | Quarantine and error-type policy |
| `topic.prefix` changed | Destination/key mapping changed | Check migration; never rename arbitrarily |
| Offset file deleted | No persistent store | Restore/backfill/snapshot per runbook |

A CDC incident typically spans **three areas of responsibility**: DBAs manage WAL/slots/publications; platform engineers manage Engine lifecycle/offsets and deployment; application engineers manage downstream idempotency/transactions. Troubleshooting checklists must cover all three instead of repeatedly restarting pods.

## 33. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| "Debezium adapter is just a JDBC inbound poller with a small interval" | Debezium uses CDC/log streaming and needs no Spring poller |
| "Having `spring-integration-debezium` means no connector is needed" | A database-specific connector (PostgreSQL, MySQL, etc.) is required |
| "Java DSL `Debezium` was only added in 7.0" | It has existed since Spring Integration 6.2 |
| "`topic.prefix` means automatically sending to Kafka" | It is only a logical namespace; a downstream Kafka adapter is a separate step |
| "A table update is always a complete business event" | Row change events have technical semantics; consider an outbox |
| "Snapshot `r` is a newly occurred real INSERT" | It is an initial state read |
| "`op=d` is the same as a tombstone" | Delete envelopes and tombstones are two distinct events |
| "`before` always contains the full row" | Depends on DB and replica identity |
| "Payload is always `byte[]`" | Batch mode, tombstones, and other serializations produce different types |
| "`enableBatch(true)` produces a serializable `List<byte[]>`" | It produces a `List<ChangeEvent>` that is not serializable by default |
| "Changing `contentType` to Avro converts JSON to Avro" | Engine serialization and `contentType` must match |
| "`headerNames` selects which tables Debezium reads" | It selects event headers to map; tables are set via connector config |
| "Once an offset file is saved, duplicates never happen" | Crash windows, replays, and at-least-once semantics still apply |
| "`MessageChannel.send()` means Kafka has ACKed" | Spring channel delivery differs from broker ACK |
| "Synchronous `DirectChannel` provides a built-in DB transaction" | Explicit transaction boundaries are still required |
| "`ExecutorChannel` holds the Engine ack until the worker finishes" | There is no automatic guarantee |
| "3 pods on the same slot will split events evenly" | They contend for the slot; there is no automatic work partitioning |
| "One slot per pod prevents duplicate data" | Separate slots can all read the exact same changes |
| "WAL/replication slots need no monitoring" | A stalled slot can retain WAL and fill the disk |
| "Dropping a slot to fix lag is harmless" | It can lose logs required to resume |
| "CDC captures changes outside configured permissions/tables" | Depends on capture list, permissions, and log availability |
| "Adding a column never affects consumers" | Schema evolution can break parsers or contracts |

## 34. Hands-On Exercises

1. Create the `public.orders` table in PostgreSQL and insert two sample orders.
2. Configure `wal_level=logical`, the replication user, publication, and slot ownership for the lab.
3. Add compatible versions of `spring-integration-debezium` and `debezium-connector-postgres`.
4. Build `Properties` with PostgreSQL connector config, `topic.prefix`, and a durable file offset store.
5. Write `IntegrationFlow.from(Debezium.inboundChannelAdapter(props))` using `enableBatch(false)`.
6. Attach a `@ServiceActivator` to the output channel and read `DebeziumHeaders.KEY` and `DESTINATION`.
7. Read the `byte[]` payload as UTF-8 and parse `r/c/u/d` with Jackson.
8. Enable initial snapshot and verify `op=r` events for existing rows.
9. Execute INSERT, UPDATE, and DELETE after the snapshot; verify events and expected ordering.
10. Change PostgreSQL `REPLICA IDENTITY` in the lab and compare `before` data on UPDATE/DELETE.
11. Enable `enableEmptyPayload(true)`, trigger a DELETE producing a tombstone, and handle `Optional.empty()`.
12. Enable `enableBatch(true)` in a separate flow and verify the payload is `List<ChangeEvent>`.
13. Attempt to serialize the batch payload into a persistent `MessageStore`, then design a mapper to a serializable DTO.
14. Create a `DebeziumEngine.Builder<ChangeEvent<byte[],byte[]>>` from `JsonByteArray` and configure the producer with Java beans.
15. Test `contentType` JSON/AVRO/PROTOBUF only when Engine format matches; observe the error when mismatched.
16. Configure `headerNames("trace*")`, distinguishing it from `table.include.list`.
17. Restart Spring Boot with a durable offset file; observe resuming and possible replays.
18. Delete the offset file **only in a backed-up lab**, and analyze re-snapshotting or duplicate emission.
19. Launch two Engine instances sharing the same `slot.name` in a test and analyze slot active/collision errors.
20. Run one Engine feeding two downstream consumers via Kafka/JMS instead of one independent connector per pod.
21. Create `inbox_event` with a unique business event ID and simulate event redelivery after a crash.
22. Write a transactional outbox alongside order writes and use Debezium to capture changes from the outbox table.
23. Simulate a sink DB/Kafka outage; monitor WAL retention, lag, bounded queues, and error policies.
24. Write a Testcontainers PostgreSQL test with `wal_level=logical` and verify `r/c/u/d`.
25. Create a migration adding a `discount_cents` column and verify consumer schema evolution.
26. Stop the Engine gracefully vs. force-kill it; compare replayed records and offset behavior.
27. Build a dashboard for slot active status, WAL retained bytes, CDC messages/s, snapshot duration, and inbox lag.
28. Write a recovery runbook for a dropped slot, offset mismatch, or purged WAL.
29. Design a leader/standby setup for two pods ensuring only one reader is active at a time.
30. Write an async test: `ExecutorChannel` + durable inbox; verify no event is ACKed away before inbox commit.

**Capstone scenario:** a Spring Boot service reads CDC from PostgreSQL via the Debezium inbound adapter to send orders to Kafka. Pod A writes an inbox event and successfully sends to Kafka, but is killed before the Engine flushes its offset; standby Pod B starts up on the same replication slot. Meanwhile, a DBA alters the schema to add a sensitive column, and a slow processing queue increases WAL retention. Design **leadership, offset persistence, inbox/outbox/idempotency, schema filtering/masking, graceful shutdown, metrics, and recovery** so no business events are lost and no uncontrolled duplicate business effects occur.

## 35. References

- [Spring Integration Reference — Debezium Support](https://docs.spring.io/spring-integration/reference/debezium.html): `DebeziumMessageProducer`, Java DSL, batch, tombstone, header mapper, JSON/Avro/Protobuf.
- [Spring Integration API — DebeziumMessageProducer](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/debezium/inbound/DebeziumMessageProducer.html): constructor, `setEnableBatch`, `setEnableEmptyPayload`, `setTaskExecutor`.
- [Spring Integration API — DebeziumMessageProducerSpec](https://docs.spring.io/spring-integration/docs/6.5.1/api/org/springframework/integration/debezium/dsl/DebeziumMessageProducerSpec.html): Java DSL methods `headerNames`, `enableBatch`, `contentType`, and lifecycle.
- [Spring Integration API — Debezium DSL Factory](https://docs.spring.io/spring-integration/docs/6.5.1/api/org/springframework/integration/debezium/dsl/Debezium.html): `inboundChannelAdapter(Properties)` and `inboundChannelAdapter(Builder)`.
- [Spring Integration API — DebeziumHeaders](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/debezium/support/DebeziumHeaders.html): `KEY` and `DESTINATION`.
- [Spring Integration Reference — Changes 6.1 to 6.2](https://docs.spring.io/spring-integration/reference/changes-6.1-6.2.html): Debezium inbound adapter introduced in 6.2.
- [Debezium Documentation — Debezium Engine](https://debezium.io/documentation/reference/stable/development/engine.html): Engine, JSON/JsonByteArray, offset store, callbacks, `ChangeConsumer/RecordCommitter`, lifecycle.
- [Debezium Documentation — PostgreSQL Connector](https://debezium.io/documentation/reference/stable/connectors/postgresql.html): logical replication, `pgoutput`, publication, slot, snapshot, change event envelope.
- [Debezium Documentation — Storage Configuration](https://debezium.io/documentation/reference/stable/configuration/storage.html): file/JDBC/Kafka offset stores and schema history.
- [Debezium Documentation — Outbox Event Router SMT](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): using Debezium to capture a transactional outbox.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel, and async boundaries.
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): handler transactions, scope, and error behavior.
- [PostgreSQL Documentation — Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html): publications, subscriptions, WAL/logical decoding.
- [PostgreSQL Documentation — pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html): slot information and WAL retention.

> **Key Takeaway:** The **Debezium inbound channel adapter** bridges **CDC from database logs → Debezium Engine → Spring `MessageChannel`**, rather than acting as a JDBC poller. In Spring Integration 6.2+, `DebeziumMessageProducer`/`Debezium.inboundChannelAdapter(...)` supports JSON, Avro/Protobuf, batching, and tombstones as configured. Always distinguish **snapshot `r`, stream `c/u/d`, tombstones, source offsets, broker ACKs, and downstream transactions**; they do not commit atomically together. Safe operations require durable offset storage, replication slot/WAL management, a single coordinated active CDC reader, schema/PII policies, inbox/outbox patterns, retries, and idempotency.
