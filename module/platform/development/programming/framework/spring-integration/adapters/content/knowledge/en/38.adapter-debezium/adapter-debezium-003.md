# Database Tables and Connector Configuration in Spring Integration Debezium

## 1. The Problem: Connecting to the Right Database Is Not Enough for CDC to Work Properly

A sales system stores `orders` and `order_outbox` in PostgreSQL. When data changes, a Spring Integration application needs to receive CDC records from Debezium, convert them into `Message<?>`, and then update a read model, send to Kafka/JMS/AMQP, or sync an external system. If the connector connects successfully but the **table, replication, snapshot, or offset** configuration is wrong, the following problems still occur:

- Capturing too many tables and accidentally leaking PII to sinks.
- Reading snapshot `r` events but never receiving subsequent `c/u/d` events due to publication or replication slot issues.
- Missing a newly migrated table even though the application thinks it updated `table.include.list`.
- Running multiple pods with the same slot; one pod fails with `replication slot is active` or separate slots read duplicate copies of every change.
- Deleting the offset file or slot and restarting, causing re-snapshots, replays, or lost logs.
- Setting `topic.prefix` and mistakenly thinking the Debezium Engine automatically publishes to Kafka.

This **Database tables and connector configuration** lesson belongs to the **Adapter Debezium** chapter of the **SPRING_INTEGRATION_ADAPTERS** module: connecting external systems with inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases; focusing on message contracts, error handling, and connection lifecycles.

**Objective:** design source tables with keys, constraints, and clear CDC contracts; prepare permissions and replication logs; configure the Debezium PostgreSQL connector in Spring Integration; distinguish options across PostgreSQL, MySQL, SQL Server, and Oracle; test snapshots/streaming/filtering/schema migrations, offsets/restarts, and operational risks.

## 2. Overall Architecture: Source Tables, Connector, and IntegrationFlow

~~~mermaid
flowchart LR
    A["Business transaction"] --> B[("PostgreSQL: orders + outbox")]
    B --> C["WAL logical decoding"]
    C --> D["Publication + replication slot"]
    D --> E["Debezium PostgresConnector"]
    E --> F["Debezium Engine embedded"]
    F --> G["DebeziumMessageProducer"]
    G --> H["Spring MessageChannel"]
    H --> I["Filter / Transform / Validate"]
    I --> J["JDBC sink / Kafka / JMS / HTTP"]
~~~

There are **two independent configuration layers that must align**:

1. **Database-side:** tables and primary keys; `SELECT`/`REPLICATION` privileges; PostgreSQL `wal_level`, publication, slot; MySQL binlog; SQL Server CDC enablement; Oracle redo/LogMiner.
2. **Connector-side:** `connector.class`, host/credentials, `topic.prefix`, database/schema/table/column filters, snapshot mode, offset store, transforms, timeouts, and engine lifecycle.

`DebeziumMessageProducer` is a **message-driven inbound endpoint from the Engine**, not a `JdbcPollingChannelAdapter` using `Pollers.fixedDelay(...)`. Once converted into Spring Messages, upstream CDC events can flow into synchronous or asynchronous channels as needed.

**Guarantee scope:** Debezium reading a row change **does not** cause a JDBC sink, Kafka producer, or remote HTTP call to commit in the same transaction as the source database. Events can be replayed; idempotency or a transactional outbox/inbox is required at downstream boundaries.

## 3. Choosing How to Deploy Debezium Before Writing Properties

| Deployment Mode | Where Is the Connector Managed? | When to Choose It | What You Must Manage Yourself |
|---|---|---|---|
| **Spring Integration Debezium inbound** | Debezium Engine embedded in Spring Boot JVM | Single internal CDC stream, minimal extra infrastructure, direct processing via `MessageChannel` | Startup/shutdown, offsets, slots, HA, retries, lag |
| **Kafka Connect + Debezium connector** | Kafka Connect distributed cluster | Multiple connectors, centralized HA/operations, Kafka sink | Connect workers, connector tasks/config, Kafka/offsets/history |
| **Debezium Server** | Standalone Debezium runtime | Decouples CDC service from the app, pushes to supported sinks | Server lifecycle, offsets, sink delivery |
| **Transactional outbox + CDC** | One of the runtimes above reading an outbox table | Emitting business events after a DB transaction | Event IDs, outbox schema, sink idempotency |

In this lesson, the primary examples use the **Embedded Debezium Engine via Spring Integration**. If you deploy on Kafka Connect, many source connector properties are similar, but the Connect worker's **offset storage and lifecycle** differ from the embedded Engine. Never copy properties verbatim across runtimes without understanding ownership.

## 4. Database Schema for a Realistic CDC Flow

Create separate transactional and outbox tables. PostgreSQL example:

~~~sql
CREATE SCHEMA IF NOT EXISTS commerce;

CREATE TABLE commerce.orders (
    id              BIGINT PRIMARY KEY,
    customer_id     VARCHAR(64) NOT NULL,
    status          VARCHAR(24) NOT NULL,
    amount_cents    BIGINT NOT NULL CHECK (amount_cents >= 0),
    version         BIGINT NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE commerce.order_outbox (
    event_id        UUID PRIMARY KEY,
    aggregate_id    BIGINT NOT NULL,
    aggregate_ver   BIGINT NOT NULL,
    event_type      VARCHAR(80) NOT NULL,
    payload_json    JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (aggregate_id, aggregate_ver)
);

CREATE INDEX idx_order_outbox_created
    ON commerce.order_outbox (created_at, event_id);

INSERT INTO commerce.orders
    (id, customer_id, status, amount_cents, version)
VALUES (101, 'C-101', 'CREATED', 150000, 0);
~~~

An `INSERT` into `order_outbox` should happen **in the same business transaction** as updating `orders`. The outbox table stores a stable event ID for downstream deduplication; you should not assume Debezium emits each change only once.

### 4.1. Table Design Decisions That Directly Affect CDC

| Table Design | Impact on CDC | Recommendation |
|---|---|---|
| **Stable primary key** | Produces clean record keys, aiding routing/partitioning/dedup | Define an explicit PK; avoid frequent PK updates |
| No PK | Event key may be null; DELETE/rekeying is hard to handle | Define a custom key or adjust schema |
| Updating PK | May emit DELETE/tombstone/CREATE sequence | Define a rekey policy |
| `BIGINT amount_cents` | Preserves exact money amounts in minor units | Validate ranges and currency separately |
| `updated_at` timestamp | Useful for observability, not a Debezium offset | Never use timestamps as CDC checkpoints |
| Per-aggregate `version` | Enables idempotent read models and ordering | Increment on every business transaction |
| JSONB payload in outbox | Business event envelope decoupled from table schema | Version schemas and limit PII |
| Triggers/DDL | Can generate additional row changes | Check side effects and CDC capture scope |

**Do not rely solely on `MAX(id)` or `updated_at` to track log position:** Debezium maintains connector-managed source offsets (WAL LSN, binlog position, etc.).

## 5. Schema, Table, and Column Filtering: Which Filter Applies Where?

A connector can be filtered at multiple layers:

~~~text
PostgreSQL database 'appdb'
  schemas: commerce, audit, public
  commerce.orders
  commerce.order_outbox
  commerce.customer_private
  audit.security_log

PostgreSQL publication: [commerce.orders, commerce.order_outbox]
          |
Debezium schema/table.include.list
          |
Debezium column.include.list / column.exclude.list
          |
SMT / Spring Integration filter/router
          |
Consumer allowed destinations
~~~

The **Publication** controls which tables PostgreSQL exposes to the replication stream for that publication (with `pgoutput`). Debezium's **`table.include.list`** limits which tables the connector **emits as CDC events**. They are not the same mechanism and do not replace each other. **`column.exclude.list`** filters fields emitted in events; it does not prevent sensitive data from appearing in database logs or internal pipelines.

### 5.1. Include/Exclude Lists and Regex

Typical properties:

~~~properties
schema.include.list=commerce
table.include.list=commerce[.]orders,commerce[.]order_outbox
column.exclude.list=commerce[.]orders[.]customer_id
~~~

Debezium uses **regular expressions matched against the entire identifier**, not SQL `LIKE '%orders%'`. An unescaped regex dot `.` is a wildcard; use `[.]` for a literal dot when matching exact names. Verify regex syntax and identifier casing for your connector version.

| Property | Example | Scope | Notes |
|---|---|---|---|
| `database.include.list` | `shopdb` in MySQL | Source databases (connector-dependent) | Not supported identically across all connectors |
| `schema.include.list` | `commerce` | Schemas | Do not overlap with exclude list |
| `table.include.list` | `commerce[.]orders` | Fully qualified tables | Must align with publication |
| `table.exclude.list` | `commerce[.]debug_.*` | Excluded tables | Do not specify both include and exclude for the same scope |
| `column.include.list` | `commerce[.]orders[.]id,...` | Included columns | Do not both include and exclude for the same scope |
| `column.exclude.list` | `commerce[.]orders[.]customer_id` | Excluded columns | Avoid excluding keys needed by consumers |
| `snapshot.include.collection.list` | Connector-dependent | Tables to snapshot when configured | Distinct from streaming table list |
| `table.include.list` post-deploy | Adding a new table | Does not retroactively capture old rows | Requires incremental snapshot or backfill |

**When targeting strictly `commerce.orders`, do not write `.*orders.*`**: it can match unintended tables. In PostgreSQL, identifiers follow quoted-identifier casing rules; keep names simple lowercase and verify the actual emitted representation.

### 5.2. Publications and Debezium Filters Do Not Update Each Other Automatically

If a publication only includes `commerce.orders` while Debezium's `table.include.list` adds `commerce.order_outbox`, you cannot expect the connector to receive outbox changes just by editing Properties. A DBA must update the publication (or use an allowed auto-create/filtered mode) and run an appropriate snapshot/backfill plan.

Conversely, if a publication includes many tables while Debezium filters down to one, that does not mean the database avoids decoding logs for the other tables. Optimization and security should start at the **capture source** before application-level filters.

## 6. PostgreSQL: Enable Logical Replication Before Running the Connector

PostgreSQL logical decoding requires proper server settings and privileges. For self-managed environments, DBAs configure:

~~~conf
# postgresql.conf - illustrative lab/DBA example
wal_level = logical
max_replication_slots = 5
max_wal_senders = 5
# max_slot_wal_keep_size, wal retention, disk capacity:
# size according to actual traffic and RPO/RTO
~~~

Some server parameter changes require a restart. On managed PostgreSQL (RDS, Cloud SQL, Azure Database for PostgreSQL, etc.), enabling logical replication/parameter groups and replication privileges differs; follow provider documentation and never assume superuser access.

Verify server state:

~~~sql
SHOW wal_level;
SHOW max_replication_slots;
SHOW max_wal_senders;
SELECT current_database(), current_user;
~~~

**Conditions required to stream events:** `wal_level=logical`, available slot capacity, replication privileges, a valid publication, and log readability for the connector. A successful JDBC `SELECT 1` does not prove CDC prerequisites are met.

## 7. PostgreSQL User, SELECT Privileges, and Publication

Lab example executed by a DBA/owner:

~~~sql
-- Database appdb and schema commerce already created.
CREATE ROLE cdc_reader LOGIN REPLICATION
  PASSWORD 'REPLACE_IN_SECRETS';

GRANT CONNECT ON DATABASE appdb TO cdc_reader;
GRANT USAGE ON SCHEMA commerce TO cdc_reader;
GRANT SELECT ON commerce.orders TO cdc_reader;
GRANT SELECT ON commerce.order_outbox TO cdc_reader;

-- DBA or table owner creates the publication.
CREATE PUBLICATION commerce_cdc_pub
  FOR TABLE commerce.orders, commerce.order_outbox;
~~~

In production, **never embed passwords**. Apply least privilege and manage credentials via a secret manager; `REPLACE_IN_SECRETS` is strictly a placeholder.

### 7.1. Publication Auto-Create Mode

| Mode | Meaning | When to Use |
|---|---|---|
| `disabled` | Connector does not auto-create the publication | Preferred when DBAs pre-manage publications |
| `all_tables` | Auto-creates a publication for all tables per mechanism/version | Requires high privileges; watch data exposure |
| `filtered` | Auto-creates/updates a publication matching filters (if permitted) | Verify ownership and privileges |
| `no_tables` | Another mode that may exist in certain versions | Use only when confirmed by your version's docs |

Only use modes **supported by your connector version**. A misspelled property or unsupported mode can fail Engine startup; do not use `no_tables` unless confirmed in your specific version's documentation.

For this lab, use `publication.autocreate.mode=disabled`, keeping publication creation with the DBA so the application does not require extra `CREATE` rights. **`CREATE PUBLICATION` requires appropriate ownership and database privileges**; a `cdc_reader` role with only `SELECT`/`REPLICATION` cannot necessarily create publications on its own.

### 7.2. Inspecting the Publication

~~~sql
SELECT pubname, puballtables, pubinsert, pubupdate, pubdelete
FROM pg_publication
WHERE pubname = 'commerce_cdc_pub';

SELECT pubname, schemaname, tablename
FROM pg_publication_tables
WHERE pubname = 'commerce_cdc_pub'
ORDER BY schemaname, tablename;
~~~

If a new table is not listed in `pg_publication_tables`, adding it to Debezium's `table.include.list` will not make PostgreSQL stream its logical WAL rows through that existing publication.

## 8. Replication Slot: Read Position, Ownership, and WAL Retention

`slot.name` identifies a logical replication slot, such as `commerce_cdc_slot`. PostgreSQL retains WAL segments required by the consumer based on this slot; if the Engine stops consuming for too long, WAL accumulates and can fill the disk.

~~~sql
SELECT slot_name, plugin, slot_type, active,
       restart_lsn, confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_name = 'commerce_cdc_slot';
~~~

Estimate WAL bytes retained from `restart_lsn`:

~~~sql
SELECT slot_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
         AS retained_wal_bytes
FROM pg_replication_slots
WHERE slot_name = 'commerce_cdc_slot'
  AND restart_lsn IS NOT NULL;
~~~

This is **one indicator** to monitor, not a replacement for full connector lag metrics. `restart_lsn` and `confirmed_flush_lsn` have distinct semantics; do not treat `pg_wal_lsn_diff` as end-to-end consumer latency.

### 8.1. Slots Can Be Created by the Connector or DBA

PostgreSQL provides a SQL function to create slots manually:

~~~sql
-- Only DBAs/operators with privileges should run this,
-- and only when the slot does not exist and ownership is planned.
SELECT *
FROM pg_create_logical_replication_slot(
    'commerce_cdc_slot', 'pgoutput');
~~~

If configured and permitted, Debezium can also create the slot on startup. **Do not create two separate slots to "split work across two pods"**: two slots reading the same publication will deliver the same data changes to both engines. For HA CDC, you generally want one active/leader Engine, durable offset storage, and coordinated failover.

### 8.2. Do Not Set `slot.drop.on.stop=true` for Normal Resume

`slot.drop.on.stop` defaults to keeping the slot across shutdowns. If enabled to auto-drop the slot, on restart the WAL/position the Engine needs to resume may be gone. Use it only in labs or very specific lifecycle strategies. Dropping a production slot to fix disk pressure without checking offset and recovery plans risks **data loss**.

## 9. Replica Identity: Pre-Change Columns Depend on the DB

PostgreSQL `REPLICA IDENTITY DEFAULT` typically includes only the **primary key** as the old-row identity, without automatically supplying all `before` values on UPDATE/DELETE in CDC events.

~~~sql
-- Inspect table replica identity mode.
SELECT n.nspname, c.relname, c.relreplident
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'commerce'
  AND c.relname IN ('orders','order_outbox');
~~~

If consumers need the full before image:

~~~sql
-- Requires DBA/owner approval due to increased logical WAL volume.
ALTER TABLE commerce.orders REPLICA IDENTITY FULL;
~~~

**Trade-off:** `FULL` adds pre-change detail but increases log volume and can expose PII that downstream systems do not need. Prefer adapting the consumer contract to use `after`/business versions or an outbox when full business events are required.

Do not apply `REPLICA IDENTITY FULL` blindly across an entire database; evaluate per table based on update rate, row size, indexes, and security requirements.

## 10. Configuring the PostgreSQL Debezium Connector with Properties

An illustrative properties file for the **Embedded Engine**:

~~~properties
name=commerce-debezium-engine
connector.class=io.debezium.connector.postgresql.PostgresConnector
database.hostname=localhost
database.port=5432
database.user=cdc_reader
database.password=REPLACE_WITH_SECRET
database.dbname=appdb

plugin.name=pgoutput
slot.name=commerce_cdc_slot
publication.name=commerce_cdc_pub
publication.autocreate.mode=disabled

topic.prefix=commerce_source
schema.include.list=commerce
table.include.list=commerce[.]orders,commerce[.]order_outbox
snapshot.mode=initial

offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
offset.storage.file.filename=/var/lib/app/offsets/commerce-cdc.dat
offset.flush.interval.ms=10000
~~~

**Group-by-group explanation:**
- `name` identifies the Engine/connector; `connector.class` selects the PostgreSQL connector.
- `database.*` configures the DB connection. Avoid using the application's writer account when a dedicated CDC role is possible.
- `plugin.name=pgoutput` selects the PostgreSQL-compatible logical decoding plugin.
- `slot.name` identifies the slot, and `publication.name` specifies the server publication streaming tables to the connector.
- `topic.prefix` is the logical namespace for Debezium event destinations (e.g., `commerce_source.commerce.orders`), **not automatic Kafka publishing** in the embedded Engine.
- `schema.include.list` and `table.include.list` define Debezium's capture scope; they must match the publication.
- `snapshot.mode=initial` captures existing state on initial startup per connector semantics, then streams.
- `offset.storage` and `offset.storage.file.filename` specify where the Engine saves source offsets; this is not a Spring Integration `MessageStore`.
- `offset.flush.interval.ms` is the flush interval, **not** a Kafka/JMS consumer ACK, and does not guarantee exactly-once delivery.

**Never place `REPLACE_WITH_SECRET` in production config**: use environment variables or a secret manager. If the offset file lives on an ephemeral container disk, startup may succeed, but restarts will lose offsets; use a persistent volume or another durable offset store.

## 11. Spring Boot Config and Environment Secrets

Example operational settings in `application.yml` without storing real credentials:

~~~yaml
cdc:
  postgres:
    host: "${CDC_DB_HOST:localhost}"
    port: 5432
    db: appdb
    user: "${CDC_DB_USER}"
    password: "${CDC_DB_PASSWORD}"
  topic-prefix: commerce_source
  publication: commerce_cdc_pub
  slot: commerce_cdc_slot
  offset-file: "${CDC_OFFSET_FILE}"
  tables: "commerce[.]orders,commerce[.]order_outbox"
~~~

`${...}` in the example represents a Spring property placeholder `$...`; `CDC_DB_HOST:localhost` provides a default host for lab use, while user/password/offset file **must** be supplied outside Git. In production, tie the offset store to the container/volume lifecycle and access permissions.

Sensitive config variables must be redacted from startup logs. Never print the entire `Properties` object to logs: it contains `database.password`.

## 12. Java Config: Wiring Debezium Properties into Spring Integration

Spring Integration has supported the Debezium inbound adapter since **6.2**. The Java DSL `Debezium.inboundChannelAdapter(Properties)` accepts native Debezium connector/Engine settings. Example with a named `Properties` bean and an `IntegrationFlow`:

~~~java
package com.example.cdc;

import java.util.Properties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.debezium.dsl.Debezium;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class CommerceCdcConfiguration {

    @Bean("commerceCdcProperties")
    public Properties commerceCdcProperties(
            @Value("${cdc.postgres.host}") String host,
            @Value("${cdc.postgres.port}") int port,
            @Value("${cdc.postgres.db}") String database,
            @Value("${cdc.postgres.user}") String username,
            @Value("${cdc.postgres.password}") String password,
            @Value("${cdc.topic-prefix}") String prefix,
            @Value("${cdc.publication}") String publication,
            @Value("${cdc.slot}") String slot,
            @Value("${cdc.offset-file}") String offsetFile,
            @Value("${cdc.tables}") String tables) {

        Properties props = new Properties();
        props.setProperty("name", "commerce-embedded-cdc");
        props.setProperty("connector.class",
            "io.debezium.connector.postgresql.PostgresConnector");
        props.setProperty("database.hostname", host);
        props.setProperty("database.port", String.valueOf(port));
        props.setProperty("database.dbname", database);
        props.setProperty("database.user", username);
        props.setProperty("database.password", password);
        props.setProperty("plugin.name", "pgoutput");
        props.setProperty("publication.name", publication);
        props.setProperty("publication.autocreate.mode", "disabled");
        props.setProperty("slot.name", slot);
        props.setProperty("topic.prefix", prefix);
        props.setProperty("schema.include.list", "commerce");
        props.setProperty("table.include.list", tables);
        props.setProperty("snapshot.mode", "initial");

        props.setProperty("offset.storage",
            "org.apache.kafka.connect.storage.FileOffsetBackingStore");
        props.setProperty("offset.storage.file.filename", offsetFile);
        props.setProperty("offset.flush.interval.ms", "10000");
        return props;
    }

    @Bean
    public IntegrationFlow commerceCdcInbound(
            @Qualifier("commerceCdcProperties") Properties properties) {
        return IntegrationFlow.from(
                Debezium.inboundChannelAdapter(properties)
                    .contentType("application/json")
                    .enableBatch(false))
            .channel("commerceRawChanges")
            .get();
    }
}
~~~

This example configures **one embedded Engine**. A compatible version of `debezium-connector-postgres` must be on the classpath. The `commerceRawChanges` channel requires a downstream consumer/subscriber—typically a `@ServiceActivator(inputChannel="commerceRawChanges")` or a dedicated processing flow.

`.contentType("application/json")` declares the JSON serialization payload emitted by the adapter; do not use the content-type setter expecting it to auto-convert JSON into Avro or Protobuf. `.enableBatch(false)` emits one event at a time, simplifying key/value parsing and per-message error handling; when `true`, the payload is a `List<ChangeEvent>`, which is not serializable by default.

**Do not call `Pollers.fixedDelay(...)` on the Debezium inbound adapter:** the Debezium Engine streams internally; it is not a JDBC polling message source.

### 12.1. Avoid Running Two Engines on the Same Slot

One Spring context must not register **two flows or two producers** sharing `commerce_cdc_slot` and the same source offset. They would contend for the active replication slot. If you need two consumers for one stream, route/broadcast Spring messages **after a single Engine** (for example, a `PublishSubscribeChannel` with clear transaction/async semantics), or publish to a durable broker.

## 13. Handler Validating Table and Operation Before Processing

A Spring Integration event typically provides:
- `Message.getPayload()`: JSON value as `byte[]` in single-event JSON byte-array mode; may differ in batch/tombstone/other serializer modes.
- `DebeziumHeaders.KEY`: record key, typically JSON `byte[]`.
- `DebeziumHeaders.DESTINATION`: logical destination name such as `commerce_source.commerce.orders`.

~~~java
package com.example.cdc;

import java.nio.charset.StandardCharsets;
import java.util.Set;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.debezium.support.DebeziumHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class CommerceCdcReceiver {

    private static final Set<String> ALLOWED = Set.of(
        "commerce_source.commerce.orders",
        "commerce_source.commerce.order_outbox");

    @ServiceActivator(inputChannel = "commerceRawChanges")
    public void accept(Message<?> message) {
        Object destinationHeader =
            message.getHeaders().get(DebeziumHeaders.DESTINATION);

        if (!(destinationHeader instanceof String destination)
                || !ALLOWED.contains(destination)) {
            throw new IllegalArgumentException(
                "Unexpected Debezium destination");
        }

        Object value = message.getPayload();
        if (!(value instanceof byte[] bytes)) {
            // If enableEmptyPayload(true) is set, a tombstone may arrive
            // as Optional.empty(); handle according to policy.
            throw new IllegalArgumentException(
                "Unexpected payload type");
        }

        // Lab snippet prints only data type and size,
        // avoiding raw JSON logging that could contain PII.
        System.out.printf(
            "destination=%s, bytes=%d%n", destination, bytes.length);

        String json = new String(bytes, StandardCharsets.UTF_8);
        // Real service layer must parse the envelope before routing.
        // Avoid logging the json variable in production.
        processJson(destination, json);
    }

    private void processJson(String destination, String json) {
        // Validate op, key, schema, then stage inbox/outbox.
    }
}
~~~

**Do not turn `DESTINATION` into a SQL table name via string concatenation.** A static allowlist and preconfigured repositories are safer. When adding a new table, update the allowlist and message contract under test and governance rather than wildcard-routing into every sink.

### 13.1. Per-Table Data Contract

| Table | Key | Valid Operations | Downstream Effect |
|---|---|---|---|
| `commerce.orders` | `id BIGINT` | `r/c/u/d`; `t` if supported by connector | Version-guarded UPSERT/DELETE on read model |
| `commerce.order_outbox` | `event_id UUID` | `c`; `r` on backfill; `d` if cleaned up | Publish business event with stable `event_id` |
| `commerce.customer_private` | Not captured | None | Never route/serialize PII |
| Control/transaction topic | Key/value differ from row envelope | BEGIN/END or heartbeat | Route separately; do not parse as an order row |

If the outbox table is cleaned up with `DELETE` after publishing, raw Debezium capture will also emit `d`/tombstone events. A downstream outbox publisher should **only publish valid `op=c/r` events per the business contract**, rather than emitting a new "EventDeleted" on cleanup. Use the Outbox Event Router SMT when you want to map outbox rows directly into business events.

## 14. Snapshot Modes and Consequences When Changing Captured Tables

| Configuration | Primary Meaning | Risk if Misunderstood |
|---|---|---|
| `snapshot.mode=initial` | Snapshots existing data when no valid offset exists, then streams | Large tables can create a massive initial backlog |
| `snapshot.mode=no_data` | Skips initial row snapshot; follows streaming semantics | Read model misses pre-existing data |
| `snapshot.mode=always` | Re-snapshots on every startup where supported | Can replay large volumes of `r` events |
| Incremental snapshot | Chunked backfill while streaming (when connector/signals support it) | Does not happen automatically just by editing the include list |
| Recovery/schema-only modes | Metadata recovery depending on connector/version | Not a generic way to recover lost data |

Debezium PostgreSQL docs describe snapshot + streaming coordinated with log positions to avoid missing changes during snapshot capture. However, a restart/crash before snapshot completion can trigger a re-snapshot; consumers must handle duplicate `r` events idempotently.

**Adding a new table:** updating `table.include.list` and the publication **does not automatically** emit all existing rows of that table. Streaming typically sees only changes made after capture starts; to backfill, run a supported initial/incremental snapshot or a verified migration/backfill plan.

### 14.1. Plan for Adding `commerce.payments`

1. Create `commerce.payments` and verify PK, permissions, and replica identity.
2. Grant `SELECT` to the CDC role and add the table to the publication per DBA policy.
3. Add `commerce[.]payments` to `table.include.list`.
4. Version downstream parsers/routers and update the destination allowlist.
5. Choose an incremental snapshot or controlled backfill for pre-existing rows.
6. Verify ordering, versioning, and duplicates while snapshot and live stream overlap.
7. Monitor snapshot progress, slot WAL retention, lag, and error rates.
8. Mark rollout complete only after both old rows and live changes are processed.

**When removing a table from the capture list**, decide whether sinks retain old copies or require cleanup; removing the table name from the connector does not erase existing read-model rows.

## 15. Incremental Snapshots and Signal Tables

Several Debezium connectors support **ad hoc incremental snapshots** via signaling. The goal is to snapshot a newly added table (or subset) without halting system-wide streaming.

Illustrative **PostgreSQL signal table example**:

~~~sql
CREATE TABLE commerce.debezium_signal (
    id    VARCHAR(100) PRIMARY KEY,
    type  VARCHAR(80) NOT NULL,
    data  VARCHAR(2000)
);

-- Configure the connector's signaling settings before using this.
INSERT INTO commerce.debezium_signal(id,type,data)
VALUES (
    'snapshot-payments-001',
    'execute-snapshot',
    '{"data-collections":["commerce.payments"],"type":"incremental"}'
);
~~~

For this to take effect, the connector must be configured with **`signal.data.collection`, supported signaling channels, and appropriate publication/capture scope**. Creating a signal table alone does not trigger snapshots automatically. For PostgreSQL logical replication, check whether the signal table must be in the publication or how signals are read in your Debezium version.

**Things to check:** incremental snapshot chunks, watermarks, reconciling concurrent updates, heap usage, and event ordering between snapshot and stream. A read-model consumer must tolerate receiving `op=r` for a row that already received `u` from streaming, usually via versioning or reconciliation rules.

## 16. Connections and TLS: Connectors Need More Than a JDBC URL

Connectors take `database.hostname`/`database.port`/`database.dbname`/credentials, but they do not automatically reuse Spring Boot's `JdbcTemplate` `DataSource`. The Embedded Debezium Engine manages its own source connection and replication channel.

**Do not assume Spring Boot's `spring.datasource.url` automatically configures Debezium.** Pass the required parameters into Debezium `Properties`. If a JDBC sink writes to another DB, it needs its own `DataSource` and transaction manager.

Example PostgreSQL connector pass-through TLS configs (verify against your Debezium/PgJDBC version):

~~~properties
database.sslmode=verify-full
database.sslrootcert=/etc/cdc-certs/ca.pem
# database.sslcert=/etc/cdc-certs/client.pem
# database.sslkey=/etc/cdc-certs/client-key.pk8
~~~

`verify-full` requires a valid server certificate matching the hostname; containers must mount certificates/CAs with proper permissions. SSL settings vary by database vendor and driver; do not copy `database.sslmode` to SQL Server or Oracle.

Never log passwords, SSL private keys, or raw connection properties. Plan secret/certificate rotation around restarts/reconnects so the connector resumes from the existing offset and slot.

## 17. Embedded Debezium Offset Store and Lifecycle

In the `FileOffsetBackingStore` example:

~~~text
DB WAL  --- LSN A --- LSN B --- LSN C ...
                         |
                  Engine source offset
                         |
                  FileOffsetBackingStore
                         |
                 /var/lib/app/offsets/commerce-cdc.dat
~~~

- The offset file must live on a **persistent volume** with write permissions and a backup strategy.
- Flushing is periodic; an engine crash can **replay** events not yet durably checkpointed.
- Never share or move offset files between unrelated connectors just because they target the same DB.
- Multiple replicas must not concurrently share an offset file as a locking mechanism.
- The replication slot retains WAL tied to the offset; **a surviving slot with a lost offset**, or **a surviving offset with a purged WAL/dropped slot**, both require a recovery plan.
- Changing `topic.prefix`, `name`, `slot.name`, or source identity can break resumption or routing. Never rename them casually across deployments.

Other backing stores (Kafka/JDBC/Redis depending on Debezium modules and version) may be better suited for HA. However, switching offset storage backends requires a **migration plan**: changing `offset.storage` from file to DB during a deploy without migrating state can cause the Engine to treat startup as brand new.

## 18. MySQL: Binlog and Schema History Are Not PostgreSQL Publications

The MySQL Debezium connector reads row changes from the **binary log**, not `pgoutput`, `slot.name`, or PostgreSQL publications.

### 18.1. MySQL Server Configuration

Example DBA checks:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'server_id';
~~~

Common server settings:

~~~ini
# MySQL server / my.cnf (illustrative)
server-id=223344
log_bin=mysql-bin
binlog_format=ROW
binlog_row_image=FULL
binlog_expire_logs_seconds=604800
~~~

`binlog_format=ROW` is a key prerequisite; `binlog_row_image=FULL` ensures full row data in the log per connector expectations. Binlog retention must exceed any anticipated outage; increase retention only after sizing disk and backups.

### 18.2. MySQL Connector Properties

~~~properties
name=shop-mysql-cdc
connector.class=io.debezium.connector.mysql.MySqlConnector
database.hostname=mysql.internal
database.port=3306
database.user=cdc_reader
database.password=REPLACE_WITH_SECRET

database.server.id=5402
topic.prefix=shop_mysql
database.include.list=shopdb
table.include.list=shopdb[.]orders
snapshot.mode=initial

offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
offset.storage.file.filename=/var/lib/app/offsets/mysql-offset.dat
offset.flush.interval.ms=10000

schema.history.internal=io.debezium.storage.file.history.FileSchemaHistory
schema.history.internal.file.filename=/var/lib/app/offsets/mysql-schema-history.dat
~~~

`database.server.id` must **not conflict** with any MySQL server or replication client; it is different from PostgreSQL `slot.name`. `topic.prefix` is a logical namespace. MySQL `table.include.list` uses `database.table`, not `schema.table` as in PostgreSQL.

**Schema history is architecturally required for the MySQL connector**: Debezium needs DDL history to decode binlog events against the schema at that point in time. The file-based schema history above is an **embedded/lab** choice when dependencies provide `FileSchemaHistory`; if using a Kafka schema history store, configure topics, brokers, security, and replication accurately. Offsets and schema history are **two separate pieces of state**.

If the schema history file is lost while the offset remains, the connector may fail to decode changes or restore schemas accurately. Do not "fix" this by deleting both files without evaluating replay/snapshot impacts on sinks.

### 18.3. MySQL Privileges

The CDC account typically requires `SELECT`, `REPLICATION SLAVE`/`REPLICATION CLIENT` (or version-equivalent privileges), plus snapshot/locking privileges if needed by the connector. Configure exact privileges per your MySQL/MariaDB/cloud provider version; do not grant `ALL PRIVILEGES` out of convenience.

## 19. SQL Server: CDC Must Be Enabled on Both Database and Each Table

The Debezium SQL Server connector uses **SQL Server Change Data Capture**, not PostgreSQL WAL logical replication.

Example DBA commands:

~~~sql
USE ShopDB;
GO

EXEC sys.sp_cdc_enable_db;
GO

EXEC sys.sp_cdc_enable_table
    @source_schema = N'dbo',
    @source_name = N'orders',
    @role_name = NULL;
GO
~~~

`GO` is a **batch separator for SQL tools** like `sqlcmd`/SSMS, not a JDBC T-SQL statement. When executing from Java, split commands or use an appropriate migration/DBA script.

Once CDC is enabled, verify tracking:

~~~sql
SELECT name, is_tracked_by_cdc
FROM sys.tables
WHERE name = 'orders';

SELECT capture_instance, source_object_id, start_lsn
FROM cdc.change_tables;
~~~

Capture jobs, retention/change tables, and SQL Server Agent (or the equivalent service for your SQL Server/cloud version) must be running. If cleanup purges change tables before Debezium reads them, **the connector cannot fully recover from offsets alone**.

### 19.1. Illustrative SQL Server Connector Properties

~~~properties
name=shop-sqlserver-cdc
connector.class=io.debezium.connector.sqlserver.SqlServerConnector
database.hostname=sqlserver.internal
database.port=1433
database.user=cdc_reader
database.password=REPLACE_WITH_SECRET
database.names=ShopDB

topic.prefix=shop_sqlserver
table.include.list=dbo[.]orders
snapshot.mode=initial

offset.storage=org.apache.kafka.connect.storage.FileOffsetBackingStore
offset.storage.file.filename=/var/lib/app/offsets/sqlserver-offset.dat
offset.flush.interval.ms=10000
~~~

This is a **source configuration snippet**, not a complete SQL Server security/TLS or schema history setup if required by your version. Some Debezium SQL Server versions require separate internal schema history storage. Do not apply PostgreSQL properties like `plugin.name`, `publication.name`, or `slot.name` to SQL Server.

## 20. Oracle: Redo Logs/LogMiner and Completely Different Privileges

The Oracle Debezium connector can use LogMiner or another capture mechanism supported by the connector version (such as XStream where licensed and configured). Oracle has no `wal_level=logical`.

Typical DBA preparation steps:
- Enable supplemental logging at the database and table levels as required.
- Identify `CDB/PDB`, service name, and LogMiner privileges.
- Check redo/archive log retention and throughput.
- Finalize connector capture mode and offset/SCN semantics.
- Filter tables/schemas with accurate naming rules.
- Test DDL evolution, LONG/LOB handling, and redo log pressure.
- Secure dictionary privileges and sensitive data.

Never supply a blanket `GRANT DBA` script for the connector: Oracle privileges are broad and vary across versions, cloud services, and connector modes. Official documentation and DBAs must confirm the exact grants.

## 21. Configuration Differences Matrix Across Databases

| Aspect | PostgreSQL | MySQL | SQL Server | Oracle |
|---|---|---|---|---|
| Log source | WAL logical decoding | Binlog ROW | CDC change tables/LSN | Redo/LogMiner/SCN |
| Enable capture | `wal_level=logical`, slot, publication | Binary log/ROW | Enable CDC on database and table | Supplemental logging, LogMiner privileges |
| Connector | `PostgresConnector` | `MySqlConnector` | `SqlServerConnector` | `OracleConnector` |
| Database selection | `database.dbname` | `database.include.list` | `database.names` | Connector-specific |
| Table filter | `schema.table` | `database.table` | `schema.table` | `schema.table` per docs |
| Log identity | LSN + metadata | Binlog file/pos/GTID | Commit/change LSN | SCN/transaction metadata |
| Schema history | Differs from MySQL; do not copy MySQL config | DDL/schema history is critical | May use internal history per version | Depends on LogMiner/version |
| Snapshot | Initial/no_data/incremental as supported | Initial/no_data/incremental | Initial/no_data/incremental | Per connector mode/version |
| Retry/retention | WAL retained by slot | Binlog purge | CDC cleanup retention | Archive/redo retention |

**Only copy common properties verified for your connector version**; never copy an entire PostgreSQL config file to MySQL or SQL Server. Even identically named properties can have different conditions and defaults.

## 22. Schema Evolution: Source Tables Changing While the Connector Runs

Common schema changes:

| Migration | Connector Risk | Consumer Risk |
|---|---|---|
| Add nullable column | DDL/schema cache must update | Parsers may ignore or accept |
| Rename column | New schema alters events | Old field vanishes |
| Change datatype `INT → BIGINT` | Connector/converter changes logical type | Overflow if cast to `int` |
| Change PK | Record key format changes | Partitioning/dedup/rekey breaks |
| Drop table | Publication/history/capture mismatch | Consumers retain stale data |
| Add table | Publication/filter not updated | Missing initial rows |
| Enable `REPLICA IDENTITY FULL` | WAL grows | Larger before image / PII exposure |
| Change `topic.prefix` | Destination changes | Routers/subscriptions mismatch |
| Change outbox payload schema | Mixed old/new business events | Requires versioned contracts |

Recommended migration workflow:
1. **Expand:** add columns/tables in a backward-compatible way; grant permissions.
2. **Connector config:** update publications, filters, offsets, and history per plan.
3. **Consumer:** support both old and new schemas with contract tests and golden events.
4. **Backfill:** run an incremental snapshot or idempotent migration command.
5. **Monitor:** track snapshots, WAL/binlog lag, error rates, and backlogs.
6. **Contract:** remove old fields only after all consumers have upgraded.

**Changing `topic.prefix` or offset identity is not a harmless rename.** When a deployment changes namespaces, resumption and event routing require a data migration plan.

## 23. Transactional Outbox: Designing a Table for Debezium to Read Accurate Business Events

Raw CDC on `orders` usually tells you only that a row changed, without explaining the business reason. For messages that must reliably reach Kafka/JMS, write an **outbox row inside the same transaction that updates the order**.

~~~sql
-- PostgreSQL example; :orderId, :eventId, :newVersion, etc.
-- are bound via PreparedStatement/NamedParameterJdbcTemplate in Java.
BEGIN;

UPDATE commerce.orders
SET status = 'PAID',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND version = :expectedVersion;

-- Service must confirm UPDATE affected exactly 1 row.
-- Otherwise, ROLLBACK instead of inserting into outbox.

INSERT INTO commerce.order_outbox (
    event_id, aggregate_id, aggregate_ver, event_type, payload_json
) VALUES (
    :eventId, :orderId, :newVersion,
    'order.paid',
    CAST(:payloadJson AS jsonb)
);

COMMIT;
~~~

**SQL example warning:** `BEGIN/COMMIT` is a pseudo transaction block for readability; when Spring manages local JDBC transactions, let `@Transactional`/`TransactionTemplate` commit and do not manually nest JDBC `BEGIN`. `:newVersion` must reflect the actual updated version, not be incremented off a stale snapshot; use `UPDATE ... RETURNING version` or track the version cleanly inside the transaction.

On the Debezium source side:
- The publication and `table.include.list` must include `commerce.order_outbox`.
- The connector emits `c` events containing `after.event_id` and `after.payload_json` (per serialization).
- Downstream must publish the **stable event ID**, not generate a fresh UUID on redelivery.
- If the outbox table is re-snapshotted, `op=r` may re-emit already published events; consumers must deduplicate.
- If the outbox table is periodically purged, `d` and tombstone events are housekeeping artifacts, not new domain events.

### 23.1. Using the Outbox Event Router SMT When Contracts Match

Debezium provides the **Outbox Event Router SMT** to transform outbox rows into business messages with ID, key, type, and payload. The column names in this example (`event_id`, `aggregate_id`, `payload_json`) **differ from the SMT defaults**, so you must configure matching mapping properties or align the table schema with the outbox event router contract.

Never configure `transforms.outbox.*` without verifying version and column mappings; a misconfigured SMT can route to the wrong destination or drop keys, and raw CDC parsers expecting `before/after` will no longer apply after the transform.

## 24. When to Read `orders` Directly vs. `order_outbox`

| Need | Raw `orders` CDC | `order_outbox` CDC |
|---|---|---|
| Rebuild a current-state read model | Fits well with snapshot + upsert | Depends on event coverage; may lack full state |
| Sync cache/search index | Fits if schema is stable | Fits when business events carry sufficient projection data |
| Emit `OrderPaid` to external services | Hard to infer business cause from UPDATE | Explicit event type, contract, and version |
| Handle DELETE | Sees `op=d`/tombstone per connector | Needs an explicit business deletion event if important |
| Frequent DB schema changes | Consumers are directly impacted | Business event contract is more decoupled |
| PII in rows | Risk of leaking new columns | Deliberately choose event fields |
| Replay and idempotency | Needs source position or aggregate version | Stable/UNIQUE `event_id` |

You can run **two separate streams**: table capture for raw materialized views, and an outbox table for integration events; never expose all raw `orders` changes to external partners without data classification and a semantic contract.

## 25. Offsets, Snapshots, Publications, and Slots: Safe Startup Order

Deployment sequence for a new PostgreSQL connector:

~~~mermaid
flowchart TD
    A["DBA checks wal_level and slots"] --> B["Create tables + PK + publication"]
    B --> C["Grant replication + SELECT permissions"]
    C --> D["Provision durable offset store + secrets"]
    D --> E["Deploy one active Engine"]
    E --> F["Initial snapshot"]
    F --> G["Continuous WAL streaming"]
    G --> H["Monitor lag, slot WAL, downstream inbox"]
    H --> I["Graceful shutdown / restart"]
    I --> G
~~~

**Preflight deployment checklist:**
1. `wal_level=logical` and slot/sender capacities are properly sized.
2. Tables have PKs; `REPLICA IDENTITY` and `before` data meet requirements.
3. The publication actually contains all declared tables.
4. The CDC role has connect, `SELECT`, and replication rights; TLS/certificates are valid.
5. `slot.name` is not held by another engine.
6. `topic.prefix` and `name` are unique and stable across rollouts.
7. Snapshot mode is chosen based on whether pre-existing data needs capturing.
8. Offset store is writable and persists across restarts.
9. Downstream has allowlists, parsers, durable inbox, and idempotency.
10. SLOs for source lag, backlog, retained WAL bytes, and retries are defined.

**Changing a table or filter in application config never replaces a DBA check of the publication.**

## 26. High Availability: Single-Reader Ownership and Downstream Scaling

In PostgreSQL, a logical replication slot is actively consumed by one client at a time in the standard model. Three Spring Boot pods each auto-starting a `DebeziumMessageProducer` on one slot will **not** distribute work like a Spring Integration poller.

~~~text
PostgreSQL logical replication DB
            |
        commerce_cdc_slot
            |
       One active Engine/leader
            |
        Durable broker/inbox
          /    |    \
    worker A worker B worker C
~~~

**Options:** run one leader connector while standbys keep their Engine stopped until ownership transfers safely; or move the connector to Kafka Connect / Debezium Server for dedicated orchestration. Downstream processing can scale across broker partitions or queues without scaling connections to the same slot.

Running one Engine **per pod with separate slots** is not load balancing: each slot receives the **same row changes** from the source, multiplying storage pressure and downstream duplicates. Independent pipelines with separate slots do have valid use cases, provided you treat them as distinct subscribers.

### 26.1. Failover Checklist

- Stop the old leader or revoke its ownership before the standby starts its Engine.
- Preserve valid slot/offset identity or follow a reconciled recovery plan.
- Verify the connector actually resumes streaming after snapshot/recovery.
- Deduplicate events that may replay across failover.
- Evaluate replication slot behavior during a PostgreSQL primary failover (slot synchronization capabilities depend on PG/cloud version).
- Never auto-drop a slot just because a standby cannot connect for a few seconds.

## 27. Backpressure, Fetch/Batch Sizing, and Connector Throughput

Debezium offers parameters to manage connector queues, batches, and heartbeats depending on connector version. Common illustrative properties include:

~~~properties
max.batch.size=2048
max.queue.size=8192
poll.interval.ms=500
heartbeat.interval.ms=10000
~~~

**These are illustrative values only**; never copy them into every connector without checking defaults and constraints for your Debezium version. `max.queue.size` normally must exceed `max.batch.size` per connector constraints; these parameters govern Debezium Engine memory and throughput and are **not the same as** `maxMessagesPerPoll` on a JDBC inbound adapter.

If a downstream `DirectChannel` handler performs slow JDBC writes, the Engine callback slows down; if you switch to `ExecutorChannel`, use a bounded executor and a durable inbox before treating an event as durably handled. Never use an unbounded in-memory queue to mask broker/DB latency.

**An operational question:** if the Kafka sink is down for an hour while PostgreSQL continues writing 10,000 rows/s, where will pending data live and how long will the backlog last? Calculate WAL retention, Engine queues, persistent inbox storage, disk quotas, and SLAs; do not simply raise `max.queue.size` indefinitely.

### 27.1. Heartbeats Are Not Business Change Events

Debezium connectors support heartbeats to advance offsets and monitor liveness when captured tables receive few changes. Heartbeats have different destination/payload semantics from `before/after/op` row envelopes; consumers must not route heartbeats into the `orders` handler and fail with "missing op" as if data were corrupt. In PostgreSQL setups with quiet captured tables alongside busy uncaptured tables generating heavy WAL, heartbeat and slot monitoring are operationally critical depending on config/version.

## 28. Operational Observability with SQL and Metrics

| Signal | Source | What to Understand |
|---|---|---|
| `pg_replication_slots.active` | PostgreSQL | Whether a consumer is actively reading the slot |
| `restart_lsn` | PostgreSQL | Minimum WAL retained for the slot |
| `confirmed_flush_lsn` | PostgreSQL | WAL position confirmed by the consumer |
| `pg_wal_lsn_diff(...)` | PostgreSQL | Estimated retained WAL bytes |
| Snapshot state/duration | Debezium metrics | Whether snapshotting or streaming |
| Events/s by table/op | Spring Integration metrics | Correct capture scope and throughput |
| Source→process latency | Debezium timestamp metadata | Connector lag (not downstream end-to-end) |
| Inbox oldest pending | Application DB | Slow sink processing |
| Outbox publish retries | Kafka/JMS outbound | Broker/sink delivery failures |
| Offset flush success/failure | Engine/offset store | Resumption readiness |
| CDC user permission errors | Logs/connector status | Setup error or broken secret rotation |
| Schema history errors | MySQL/SQL Server connector | Unable to decode logs against schema |

Useful queries to inspect publications and slots:

~~~sql
SELECT pubname, schemaname, tablename
FROM pg_publication_tables
WHERE pubname='commerce_cdc_pub'
ORDER BY schemaname, tablename;

SELECT slot_name, active, restart_lsn, confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_name='commerce_cdc_slot';
~~~

**Do not use `pg_wal_lsn_diff` as a measure of whether business events were published to Kafka.** Source offset advancement, inbox commits, outbox sends, and consumer ACKs are separate milestones.

### 28.1. Worthwhile Alerts

- Slot continuously inactive while the source still has business writes.
- `retained_wal_bytes` exceeding operational/disk thresholds and growing rapidly.
- Unusually long snapshots or repeated snapshot restarts.
- Source events/s dropping to zero unexpectedly relative to DB activity.
- Captured destination outside the allowlist (indicates filter/publication mismatch).
- Parser schema errors after a migration.
- Offset store failing to flush and spiking event replays.
- Outbox/inbox backlog or oldest pending age breaching SLA.

Avoid tagging metrics with unbounded-cardinality `orderId`/`eventId` values; keep IDs inside access-controlled, masked traces and logs.

## 29. Security Configuration, Masking, and Data Governance

**CDC can replicate both old and new row values**, so creating a publication and `table.include.list` is not enough if tables hold PII or secrets.

~~~text
Database table -> Publication -> Debezium filter/SMT -> MessageChannel -> Sink
    ^               ^                  ^                    ^
  Data owner       DBA              Security rules      Consumer policy
~~~

Checklist:
- Capture only necessary tables; exclude `customer_private` from the publication.
- Use `column.exclude.list` or converter-level column masking to strip unneeded fields.
- Protect `before` images as well when using `REPLICA IDENTITY FULL`.
- Never place passwords, SSL private keys, or raw `Properties` in logs.
- Enforce TLS verification and use a secret manager.
- Use a destination allowlist; never build dynamic SQL from message headers.
- Define data retention/erasure policies across Kafka, inbox, outbox, DLQ, snapshots, and backups.
- Audit migrations that add sensitive columns (wildcard captures can leak them unintentionally).
- Ensure `topic.prefix` and routing keys do not expose tenant names or customer IDs.
- Verify the CDC role holds only required `SELECT`/`REPLICATION` grants; consumer services do not need database superuser access.

**Column filtering occurs at the connector/serialization stage; it does not remove data from WAL or stop the DB from logging the column.** Strict compliance requirements may call for changing the source schema/outbox contract or encrypting/tokenizing data before persistence.

## 30. Troubleshooting by Symptom

| Symptom | First Check | Resolution Direction |
|---|---|---|
| Engine startup `ClassNotFoundException` | Debezium connector/version/dependencies | Add the right connector and align BOM |
| Connects to DB but no CDC events | `wal_level`, REPLICATION role, publication/slot | Fix DB setup and restart safely |
| Receives snapshot `r` but no `c/u/d` | Publication, active slot, WAL/logical streaming | Inspect connector and DB logs |
| Missing new table | Not added to publication, wrong include regex | Fix both publication and filter; backfill |
| Receiving unwanted tables | Overly broad include regex, `all_tables` publication | Tighten filters; review leaked data |
| DELETE missing `before` fields | `REPLICA IDENTITY`, key contract | Use key/version or consider FULL carefully |
| Slot `already active` | Another engine is consuming | Verify leader ownership; do not drop slot |
| WAL disk growing steadily | Slot lag, Engine down, slow sink | Monitor/recover safely; do not blindly drop |
| MySQL schema history failure | Missing history file/topic, wrong permissions | Restore state per runbook |
| SQL Server emits no changes | CDC not enabled on DB/table, capture jobs | Enable CDC / check cleanup retention |
| Offset file lost after deploy | Ephemeral volume, wrong mount | Restore/backfill; use durable storage |
| Many events replayed on restart | Offset flush timing/downtime/re-snapshot | Idempotent consumer/outbox |
| Consumer JSON parse error | Converter/SMT/schema evolution | Inspect actual bytes; version parser |
| `topic.prefix` changed unexpectedly | Config drift / deployment mismatch | Reconcile destination/routing/migration |
| TLS handshake fails | CA/hostname/client cert | Verify SSL mode and certificates |
| Lag rises under normal DB writes | Slow handler, bounded queue, WAL retention | Scale downstream and tune based on metrics |

**Never run scripts that drop replication slots or delete offset files as a harmless "retry".** Those hold CDC state; losing them can force a full snapshot or manual reconciliation.

## 31. Unit Testing Configuration

You do not need PostgreSQL to test constructing `Properties`:

~~~java
package com.example.cdc;

import static org.junit.jupiter.api.Assertions.*;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class CommerceCdcPropertiesTest {

    @Test
    void capturesOnlyAllowedTables() {
        CommerceCdcConfiguration config =
            new CommerceCdcConfiguration();

        Properties p = config.commerceCdcProperties(
            "localhost", 5432, "appdb", "testuser",
            "testpass", "commerce_source",
            "commerce_cdc_pub", "commerce_cdc_slot",
            "/tmp/cdc-test-offset.dat",
            "commerce[.]orders,commerce[.]order_outbox");

        assertEquals(
            "io.debezium.connector.postgresql.PostgresConnector",
            p.getProperty("connector.class"));
        assertEquals("pgoutput", p.getProperty("plugin.name"));
        assertEquals("disabled",
            p.getProperty("publication.autocreate.mode"));
        assertEquals(
            "commerce[.]orders,commerce[.]order_outbox",
            p.getProperty("table.include.list"));
        assertEquals("commerce_cdc_slot",
            p.getProperty("slot.name"));
    }
}
~~~

This is a **unit test of Properties mapping**; it does not prove the DB role has privileges, the publication contains the tables, the slot exists, the offset store is writable, or the Engine can read events. Never commit `testpass` into production config; it is strictly a fake test fixture.

### 31.1. Testing Downstream Destination Filtering

Craft mock messages with:
- `DebeziumHeaders.DESTINATION="commerce_source.commerce.orders"` → allowed.
- `...order_outbox` → allowed and routed differently.
- `...customer_private` → rejected/quarantined.
- Missing destination / changed `topic.prefix` → rejected with metrics, no SQL concatenation.
- New table `commerce.payments` before consumer update → explicitly detected.

Verify that the consumer does not leak raw JSON containing PII when throwing exceptions; use test loggers/redaction verification if your stack provides it.

## 32. PostgreSQL Integration Testing with Testcontainers (Reference Skeleton)

**Requirements:** run PostgreSQL with `wal_level=logical`, create tables/publications/CDC role, and use an isolated offset store. Because the Spring Integration inbound producer runs the Engine asynchronously, tests should await conditions instead of calling `Thread.sleep(1000)`.

~~~java
// Testcontainers 2.x template, not a complete test class.
// Requires modules: testcontainers-postgresql, testcontainers-junit-jupiter.
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

@Testcontainers
class CommercePostgresCdcIT {

    @Container
    static final PostgreSQLContainer postgres =
        new PostgreSQLContainer("postgres:16-alpine")
            .withDatabaseName("appdb")
            .withUsername("testuser")
            .withPassword("testpass")
            .withCommand("postgres",
                "-c", "wal_level=logical",
                "-c", "max_replication_slots=5",
                "-c", "max_wal_senders=5");

    @Test
    void checksPublicationAndChangeEvents() {
        // 1. Seed tables + CREATE PUBLICATION via DB admin.
        // 2. Grant CDC privileges, create unique slot/offset path.
        // 3. Start Debezium IntegrationFlow/test probe.
        // 4. INSERT/UPDATE/DELETE commerce.orders.
        // 5. Await op=c/u/d and matching key/destination.
        // 6. Shutdown Engine, cleanup slot/offset after test.
    }
}
~~~

**Note:** container image/`testuser` privileges may differ from production; use an admin connection in tests to create publications/roles, and the CDC connection for streaming. Testcontainers 1.x uses different modules/imports (`org.testcontainers.containers.PostgreSQLContainer<?>`); do not mix 1.x and 2.x. Never run two tests in parallel sharing the same `slot.name` or offset file unless intentionally testing collisions.

### 32.1. Critical Test Matrix

| Test | Expectation |
|---|---|
| Initial snapshot | Receives `r` for existing `orders` |
| INSERT/UPDATE/DELETE | Receives `c/u/d` for captured tables |
| Table outside `table.include.list` | No raw CDC message emitted into app |
| Table in filter but not in publication | No stream changes; config mismatch flagged |
| New table added to publication/filter | Streams live changes; old rows need backfill |
| `REPLICA IDENTITY DEFAULT` vs FULL | Before image differs per DB contract |
| Column type change | Parser/schema migration handles properly |
| Engine restart with intact offset store | Resumes with controlled replay if applicable |
| Offset lost while slot remains | Resnapshot/reconciliation runbook works |
| Slot held active by another Engine | Startup/failover clearly classified |
| Outbox INSERT in business transaction | CDC carries stable event ID |
| Consumer receives duplicates | Idempotency prevents repeated business effects |
| Temporary sink outage | Backpressure/lag measurable; no OOM |
| MySQL history file lost | Recovery plan/backup tested |
| SQL Server CDC disabled | Test detects missing setup and guides DBA |
| Sensitive data in excluded tables/columns | Never reaches downstream logs or message sinks |

## 33. Hands-On Exercises

1. Create `commerce.orders` and `commerce.order_outbox` in PostgreSQL with primary keys and a unique event ID.
2. Execute a business transaction updating `orders` and inserting into `order_outbox`; verify both roll back on failure.
3. Enable `wal_level=logical` and verify `max_replication_slots` and `max_wal_senders` with a DBA.
4. Grant CONNECT/USAGE/SELECT/REPLICATION to the CDC role for the lab.
5. Create publication `commerce_cdc_pub` for just those two tables and query `pg_publication_tables` to confirm.
6. Create (or let Debezium create) replication slot `commerce_cdc_slot` per policy and inspect `pg_replication_slots`.
7. Set `table.include.list=commerce[.]orders,commerce[.]order_outbox` and `schema.include.list=commerce`.
8. Test the unescaped regex `commerce.orders` and explain the risk of overly broad matching.
9. Test `column.exclude.list` excluding `customer_id`, verify it is absent from events, and check `REPLICA IDENTITY FULL`.
10. Configure Embedded Engine `Properties` and wire Spring Integration `Debezium.inboundChannelAdapter`.
11. Write a Spring Boot `application.yml` reading CDC secrets from environment variables.
12. Write a `@ServiceActivator` checking `DebeziumHeaders.DESTINATION` against a table allowlist.
13. Run an initial snapshot to receive `op=r`; execute INSERT/UPDATE/DELETE and verify `op=c/u/d`.
14. Test `snapshot.mode=no_data` on a fresh lab DB and confirm old rows are not backfilled.
15. Create a new table `commerce.payments`, update only `table.include.list` without updating the publication, and observe the missing events.
16. Add `payments` to the publication, grant SELECT, update the consumer allowlist, and run an appropriate backfill.
17. Create a signal table, configure `signal.data.collection`, and practice an incremental snapshot on a supporting connector version.
18. Compare `REPLICA IDENTITY DEFAULT` vs. `FULL`, measuring `before` image size and WAL retained bytes.
19. Restart the container with the offset file on a persistent volume and verify resumption.
20. Delete the offset file **only on a backed-up test setup** and analyze re-snapshotting and replay.
21. Stop the Engine for a while, measure WAL retention with `pg_wal_lsn_diff`, restart, and watch lag drain.
22. Launch two Spring Boot instances on the same slot and prove they do not act as load-balanced consumers.
23. Configure leader/standby ownership ensuring one active Engine and consistent offset state.
24. Enable TLS `database.sslmode=verify-full` in an environment with certs; induce a hostname/CA error to verify security checks.
25. Put a slow sink behind `DirectChannel` and compare against a bounded `ExecutorChannel` + durable inbox.
26. Build an outbox EventRouter SMT on a separate flow, map actual columns, and verify downstream business event IDs.
27. Configure MySQL binlog ROW/FULL, a unique `database.server.id`, and a durable schema history store.
28. On SQL Server, enable CDC at DB and table levels and verify via `sys.tables.is_tracked_by_cdc`.
29. Write unit tests for `Properties` and destination filter contracts without a live DB.
30. Write a Testcontainers PostgreSQL integration test with isolated publication/slot/offset and proper async event waiting.
31. Simulate a column-rename migration and verify parser versioning and golden event tests.
32. Build a dashboard for source lag, snapshot progress, slot WAL retention, inbox/outbox backlog, and connector errors.
33. Write a recovery runbook for a dropped slot, lost offset file, missing MySQL schema history, and SQL Server CDC cleanup.
34. Perform a data governance audit: table whitelist, column masking, secrets, and PII in `before`/`after` and DLQs.

**Capstone scenario:** a sales system runs two Spring Boot pods with embedded Debezium; PostgreSQL already has `orders` and `order_outbox`; a DBA just created `payments` and renamed `customer_id`. Pod A is consuming `commerce_cdc_slot` but is killed right after sending an event to Kafka; Pod B starts up with an empty offset file. WAL retention grows and downstream hits a schema mismatch. Design the **publication/filter migration, leader failover, offset recovery, incremental snapshot, outbox idempotency, schema versioning, security, and metrics**, and build a test matrix covering crash windows before rollout.

## 34. References

- [Spring Integration Reference — Debezium Support](https://docs.spring.io/spring-integration/reference/debezium.html): `DebeziumMessageProducer` and `Debezium.inboundChannelAdapter(Properties)`, headers, batching, lifecycle.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): Direct/Executor/QueueChannel and their impact on synchronous processing.
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): local transactions and async boundary limits.
- [Debezium Documentation — PostgreSQL Connector](https://debezium.io/documentation/reference/stable/connectors/postgresql.html): roles, publications, slots, snapshots, table/column filters, replica identity, WAL retention.
- [Debezium Documentation — MySQL Connector](https://debezium.io/documentation/reference/stable/connectors/mysql.html): binlog, server ID, schema history, and capture filters.
- [Debezium Documentation — SQL Server Connector](https://debezium.io/documentation/reference/stable/connectors/sqlserver.html): enabling CDC on DB/table, capture jobs, schema/table filters.
- [Debezium Documentation — Oracle Connector](https://debezium.io/documentation/reference/stable/connectors/oracle.html): supplemental logging, LogMiner, redo/SCN, and permissions.
- [Debezium Documentation — Debezium Engine](https://debezium.io/documentation/reference/stable/development/engine.html): embedded Engine, offset stores, `ChangeEvent`, lifecycle, and serialization.
- [Debezium Documentation — Storage Configuration](https://debezium.io/documentation/reference/stable/configuration/storage.html): file/Kafka/JDBC backing stores and schema history.
- [Debezium Documentation — Incremental Snapshots](https://debezium.io/documentation/reference/stable/configuration/signalling.html): signaling channels and snapshot requests.
- [Debezium Documentation — Outbox Event Router SMT](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): mapping outbox events and message routing.
- [PostgreSQL Documentation — Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html): publications, replication slots, and logical decoding.
- [PostgreSQL Documentation — pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html): slot `active`, `restart_lsn`, `confirmed_flush_lsn`, and WAL retention.
- [PostgreSQL Documentation — Replica Identity](https://www.postgresql.org/docs/current/sql-altertable.html): `REPLICA IDENTITY` impact on old-row images.
- [Microsoft Learn — Enable and Disable CDC](https://learn.microsoft.com/en-us/sql/relational-databases/track-changes/enable-and-disable-change-data-capture-sql-server): `sys.sp_cdc_enable_db` and `sys.sp_cdc_enable_table`.
- [Testcontainers Java Documentation](https://java.testcontainers.org/modules/databases/postgres/): setting up a PostgreSQL container for integration testing.

> **Key Takeaway:** Configuring **database tables and a Debezium connector** is a two-sided contract. PostgreSQL needs **keyed tables, privileges, a publication, a replication slot, and WAL**, while the connector needs **table filters, snapshot mode, an offset store, and compatible versions**; Spring Integration receives events via `Debezium.inboundChannelAdapter(...)` and routes them into `MessageChannel`s. MySQL, SQL Server, and Oracle use different logs, CDC mechanisms, and history stores, so Properties cannot be copied verbatim. Safe rollouts require controlling **snapshots/backfills, schema evolution, single active reader ownership, persistent offsets, WAL retention, outbox/idempotency, and data governance**.

