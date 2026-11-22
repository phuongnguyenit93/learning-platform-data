# Coordinating schema changes with expand-and-contract

In **Java Advance Compatibility Migration**, an upgrade of the JDK, framework, ORM, serializer, or protocol may need to be accompanied by data changes. Renaming a column, adding a new constraint, or changing a JSON property name seems simple, yet becomes dangerous if old and new application versions are still operating simultaneously.

The **expand-and-contract** strategy — *expand first, contract later* — lets components transition through a compatibility window instead of requiring every producer, consumer, and database to change at the exact same moment.

**Principle:** expand the schema in a way that does not break old consumers, migrate code and data through verified milestones, and only contract once no supported component still depends on the old structure.

This lesson belongs to the **Data and Protocol** group. The focus is coordinating databases, HTTP/JSON, events, Avro/Protobuf, and independent Java consumers. Expand-and-contract is not a guarantee that any arbitrary change is compatible. It is a process for managing coexistence, consistency, and when a breaking change is permitted.

## 1. Why can a schema change break the system?

Suppose version A of the Java application reads the **customer_name** column:

~~~sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);
~~~

Version B wants to rename it to **recipient_name**. If applied directly:

~~~sql
ALTER TABLE customer_profile
    RENAME COLUMN customer_name TO recipient_name;
~~~

still-running A containers may fail when executing SQL or loading entities with the old mapping. If B is deployed before changing the schema, B can also fail because the recipient_name column does not exist yet.

A rollout window typically looks like this:

~~~text
Time ----------------------------------------------->

App A:     [old][old][old] ---> drain
App B:          [new][new][new][new]
Batch A:            [scheduled run]
Queue:     [old events][old + new events]
Database:  [one shared schema]
~~~

Even when old HTTP instances have stopped, the queue may still hold old messages or an old batch job running only once a week may still depend on the pre-migration data contract.

### 1.1. Schemas are not just the database

| Schema type | Example change | Affected consumers |
|---|---|---|
| SQL database | Rename/drop column, change type, NOT NULL | Repository, ORM, reports, batch jobs |
| JSON/REST | Rename field, change required/optional | Mobile/web clients, partners |
| XML | Change element, namespace, schema | Parsers, integration adapters |
| Event/message | Add field or message version | Producers, Kafka consumers, replay |
| Avro | Field/default/schema registry compatibility | Stream processors, serializers |
| Protobuf | Field number, oneof, enum | gRPC clients/services |
| Cache/session | Key/shape of cached objects | Multiple runtime versions |
| File/snapshot | Historical data format | Import/export, recovery jobs |

The same Java property can appear at multiple boundaries. Renaming **recipientName** in an entity does not automatically update a JSON contract, an event payload, or native SQL in another system.

### 1.2. Types of compatibility to distinguish

- **Source compatibility:** does old source code still compile against the new API?
- **Binary compatibility:** do compiled classes/JARs link against the new dependency?
- **Data compatibility:** can old/new data still be read, written, and interpreted correctly?
- **Protocol compatibility:** can producers and consumers on different versions communicate?
- **Behavioral compatibility:** does the same data still lead to the right business outcome?
- **Operational compatibility:** can versions run concurrently and roll back?

Expand-and-contract primarily addresses data, protocol, and operational compatibility. It does not by itself resolve binary errors when the JDK or framework changes classes/methods.

## 2. Three phases: Expand, Migrate/Coexist, Contract

### 2.1. Expand — add first, do not break upfront

The **expand** phase prepares the new structure while keeping the old structure usable:

- Add nullable columns.
- Add new tables alongside old tables.
- Add optional properties to payloads.
- Add a new message version or new endpoint.
- Add indexes for new query paths.
- Teach consumers to understand the new type/field before producers emit it.
- Deploy readers capable of accepting both old and new payloads.

The specific choice must suit the database and protocol. A new field in JSON is not always compatible with clients using strict validation. A new column can affect **SELECT *** queries or column-order-based mappers.

### 2.2. Migrate/Coexist — migrate gradually, keep consistent

During the transition phase:

- Backfill historical data.
- Define the source of truth.
- Ensure data written by old and new writers does not conflict.
- Switch readers/consumers to the new schema.
- Monitor fallbacks and mismatches.
- Test version combinations.
- Maintain a suitable rollback path.

This is usually the most labor-intensive phase. Simply adding a new column and calling it expand-and-contract leaves the problem of concurrently updated data unsolved.

### 2.3. Contract — remove the old part when no dependencies remain

Contract can include:

- Dropping old columns/tables.
- Applying NOT NULL or final constraints.
- Removing old JSON properties.
- Stopping publishing v1 events.
- Removing old fields from published schemas.
- Removing fallbacks, dual-writes, sync triggers, and adapter code.
- Stopping acceptance of legacy formats that are no longer supported.

**Contract must be a separate milestone with Go/No-Go criteria**, not merely the final SQL step inside the same deployment.

~~~text
Baseline
  DB: customer_name
  App A: reads/writes customer_name
           |
           v
EXPAND
  DB: customer_name + recipient_name
  App A still runs
           |
           v
COEXIST / MIGRATE
  App B understands both
  Writer sync + backfill + reconciliation
           |
           v
CUTOVER
  No app/job needs customer_name
  New source of truth = recipient_name
           |
           v
CONTRACT
  Remove legacy reader/writer
  Drop customer_name when rollback window allows
           |
           v
Target
~~~

## 3. Compatibility when multiple versions run concurrently

Suppose there are three application capabilities:

- **A:** only reads/writes customer_name.
- **B:** understands both customer_name and recipient_name.
- **C:** only reads/writes recipient_name.

| Application | Old schema | Expanded schema | Contracted schema |
|---|---|---|---|
| A | Valid | Usually valid while old column exists | No longer supported |
| B | May fail if queries require the new column | Valid during transition | May fail if still querying old column |
| C | Invalid | Valid once data is ready | Valid at target |

Therefore, the typical order is:

1. Expand the database.
2. Deploy B with compatibility support.
3. Backfill and manage all active writers.
4. Cut over to C.
5. Observe and confirm no A/B components still need the old column.
6. Contract.

If step 3 is skipped, the application may run yet read wrong data. If step 5 is skipped, rollback or legacy batch jobs may fail after dropping the column.

### 3.1. Do not use a version number as proof

Two artifacts both labeled **version 2.3** may differ in feature flag configuration and behavior. A v1.9 consumer running in a batch job might execute only once a month.

Track concrete **capabilities**: which consumer reads which field, which writer can produce new data, which job needs the old schema, and whether they remain within support scope.

## 4. PostgreSQL example: renaming a column while still supporting rollback

Suppose we want to transition from **customer_name** to **recipient_name**. The SQL examples below illustrate PostgreSQL; do not apply them verbatim to every database or version.

### 4.1. Milestone E1: expand the schema

~~~sql
ALTER TABLE customer_profile
    ADD COLUMN recipient_name VARCHAR(200);
~~~

The new column temporarily allows null. The old column remains so application A keeps running.

Do not add **NOT NULL** to the new column immediately if writer A does not know about it. Do not drop or rename customer_name in this migration.

**Operational note:** DDL can require locks, affecting running transactions and replication. Duration/load depend on database version, table size, constraints, and execution method. Evaluate on a representative workload.

### 4.2. Milestone E2: entity supports both names

JPA example with transitional mapping:

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_profile")
public class CustomerProfile {
    @Id
    private Long id;

    @Column(name = "customer_name")
    private String legacyCustomerName;

    @Column(name = "recipient_name")
    private String recipientName;

    protected CustomerProfile() {
    }

    public String displayName() {
        return recipientName != null
            ? recipientName
            : legacyCustomerName;
    }

    public void changeName(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("name");
        }
        legacyCustomerName = value;
        recipientName = value;
    }
}
~~~

This is a temporary **dual-read/dual-write** representation when code B performs changes. It is not yet sufficient to keep both columns synchronized if code A is still updating the old column.

### 4.3. Milestone M1: backfill old data

Example updating in primary-key batches:

~~~sql
UPDATE customer_profile
SET recipient_name = customer_name
WHERE recipient_name IS NULL
  AND id >= 100001
  AND id < 110001;
~~~

Large systems typically need many bounded, checkpointed, and throttled batches. Do not assume a full-table UPDATE is safe while production is under load.

Required properties:

- **Idempotent:** can be re-run after failure.
- **Resumable:** can resume from an appropriate checkpoint.
- **Bounded:** batches do not hold locks/transactions for too long.
- **Observable:** exposes counts, rate, errors, and remaining data.
- **Conflict-aware:** does not overwrite valid new data.
- **Auditable:** tracks job version and processed data range.

The statement above only updates when recipient_name has no value yet. It does not handle the case where writer A changes customer_name after recipient_name has already been backfilled.

### 4.4. Counterexample: COALESCE can read old data

~~~text
T0: customer_name = "An";  recipient_name = "An"
T1: App A changes customer_name to "Bình"
T2: recipient_name is still "An"
T3: App B uses COALESCE(recipient_name, customer_name)
T4: App B returns "An" (stale)
~~~

**COALESCE** returns the first non-null value; it does not know which value was updated most recently.

The same happens if code B always prefers recipient_name when the two columns diverge. Fallback only handles **missing values**; it does not solve **freshness/concurrency**.

### 4.5. Choosing a writer synchronization strategy

| Strategy | When to use | Risks to test |
|---|---|---|
| Single-writer cutover | Writer A can be stopped before B writes new schema | Transition window and rollback |
| Database sync trigger | DDL, row updates, and transactions are controlled | Recursion, locks, conflicts, update logic |
| Shared write service | All writers go through a service supporting both fields | Legacy batch/direct SQL bypass |
| CDC/event sync | Reliable change-capture pipeline exists | Lag, ordering, duplicates, retries |
| Version/optimistic locking | Reliable version exists for updates | Lost updates, conflict resolution |
| Periodic reconciliation | Controlled divergence window is acceptable | Stale reads during lag window |

For critical data, the choice must match actual update characteristics. For example, a naive trigger that "always copies the old column to the new column" will break writer B updating the new column unless sync direction is designed properly.

**There is no single dual-write SQL snippet that works for every system.** Determine the single source of truth, conflict ordering, and rollback protocol before applying one.

### 4.6. Milestone M2: data reconciliation

Example:

~~~sql
SELECT COUNT(*) AS missing_new_value
FROM customer_profile
WHERE recipient_name IS NULL;
~~~

For two columns carrying the same meaning, PostgreSQL lets you find mismatches including nulls:

~~~sql
SELECT COUNT(*) AS mismatch
FROM customer_profile
WHERE customer_name IS DISTINCT FROM recipient_name;
~~~

A result of **0** at one point in time is not enough if writer A can still introduce new mismatches. Continuous metric monitoring and a pre-cutover reconciliation pass are needed.

If the new schema changes data semantics, do not compare directly. Build an invariant or published conversion function, such as currency-unit normalization or a new address model.

### 4.7. Milestone C1: switch readers and add constraint

Once all writers comply with the new data and backfill passes:

~~~sql
ALTER TABLE customer_profile
    ALTER COLUMN recipient_name SET NOT NULL;
~~~

This is still DDL that may involve locks/scans depending on database version. Apply the constraint after confirming old writers no longer insert nulls and historical data meets the condition.

Afterward, code C can be deployed to read/write recipient_name, while not yet dropping the old column if rollback to A or B is needed.

### 4.8. Milestone C2: contract

Only when no supported old consumers remain:

~~~sql
ALTER TABLE customer_profile
    DROP COLUMN customer_name;
~~~

This operation can render app A completely unable to run. It must be separated from the initial expand release, with a Go/No-Go decision, backup, and suitable recovery plan.

## 5. More schema change patterns than a single rename

### 5.1. Adding a required field

Wanting to add **order_status NOT NULL**, while old writers do not supply it yet:

1. Add a nullable column or intentional default.
2. Deploy the new writer that begins writing status.
3. Backfill historical data.
4. Confirm no old writer violates it.
5. Check null records and business invariants.
6. Add NOT NULL in a later milestone.

A technical default does not automatically ensure a business-meaningful value. Setting all old orders to **COMPLETED** merely because it makes the migration easy to write can corrupt data.

### 5.2. Changing numeric types or IDs

For example, changing **INT** to **BIGINT**, or money from floating-point to **DECIMAL**:

- Expand the new column.
- Determine whether conversion loses precision or overflows.
- Backfill in batches and reconcile totals.
- Switch Java/JDBC mapping code.
- Check JSON/message types if values leave the DB.
- Do not contract until every consumer understands the new representation.

A direct type-altering DDL may sometimes fit small systems, yet locks, duration, data range, and coexistence with old applications must be considered.

### 5.3. Splitting one field into multiple fields

For example, changing **full_name** to **first_name** and **last_name**:

~~~sql
ALTER TABLE person
    ADD COLUMN first_name VARCHAR(100);

ALTER TABLE person
    ADD COLUMN last_name VARCHAR(100);
~~~

Name splitting is not always unique. Some data cannot be split accurately. Define the semantics of the new fields, unknown state, and how old consumers are maintained. Do not treat this merely as a technical JPA mapping change.

### 5.4. Adding a unique constraint

Before adding **UNIQUE(email)**:

- Inspect duplicate data.
- Define merge/handling rules.
- Deploy new writers capable of handling conflicts.
- Check races between two transactions inserting concurrently.
- Choose an index/constraint creation method suited to the DB.
- Test exception mapping and retry behavior.

Java validation alone does not replace a DB constraint when multiple writers run concurrently.

### 5.5. Splitting a table

For example, moving **shipping_address** from a column in orders to the **order_address** table:

~~~text
orders.shipping_address
          |
          v
Expand: create order_address, keep old column
          |
          v
Migrate: dual read/write with appropriate synchronization
          |
          v
Backfill + verify each order has the correct address
          |
          v
Cutover queries and ORM mappings
          |
          v
Contract: drop old column
~~~

Test transactions, orphan data, foreign keys, and join performance. For large tables, plan batching/reindexing and replication lag.

## 6. HTTP/JSON: changing fields compatibly

Old response:

~~~json
{
  "orderId": "O-100",
  "customerName": "An"
}
~~~

Target response:

~~~json
{
  "orderId": "O-100",
  "recipientName": "An"
}
~~~

Changing directly can cause old clients not to find customerName.

### 6.1. Expanding with a dual-field response

During the transition phase:

~~~json
{
  "orderId": "O-100",
  "customerName": "An",
  "recipientName": "An"
}
~~~

Old clients keep reading customerName; new clients move to recipientName.

However, a client using a strict deserializer or schema validator may reject unknown fields. Therefore, actually test old consumers; **adding an optional field is not safe by default in every protocol**.

### 6.2. Accepting both old and new requests

The server can accept:

~~~json
{"customerName":"An"}
~~~

or:

~~~json
{"recipientName":"An"}
~~~

Define the case where both are present with different values:

~~~json
{
  "customerName": "An",
  "recipientName": "Bình"
}
~~~

Options include rejecting conflicts, choosing documented precedence, or requiring a separate API version. Do not silently pick a value based on JSON field order when the data is important.

### 6.3. Jackson alias

Example supporting the old name when deserializing:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public record RecipientRequest(
    @JsonProperty("recipientName")
    @JsonAlias("customerName")
    String recipientName
) {
}
~~~

**@JsonAlias** supports alternative names on the read side; it does not automatically produce a response containing both old and new names. If a dual-field response is desired, design the DTO and serialization contract explicitly.

If a client sends both the alias and the canonical name, establish a clear conflict policy rather than relying on incidental mapper behavior.

### 6.4. Not just renaming, semantics must also be preserved

Consumers care about:

- Required/optional.
- Null versus absent field.
- Number/string types.
- Enums and new values.
- Defaults.
- Business meaning.
- HTTP status/error codes.
- Authorization rules.
- Retryability and idempotency.

A new field with the same String type whose meaning changed from "account holder name" to "recipient name" can break business logic even while the parser still runs.

## 7. Event schemas and multiple independent consumers

With queues or Kafka, events may be retained and replayed after the old producer has stopped.

~~~text
Producer A ----+
               |
               +--> Topic/Queue --> Consumer A
               |                --> Consumer B
Producer B ----+                --> Batch/replay
~~~

The coexistence window must account for:

- Event retention.
- Consumer lag.
- Dead-letter queues.
- Replay/reprocessing.
- Offline consumers.
- Partners with different release cycles.
- Schema registry compatibility mode.
- Stored historical data.

### 7.1. Consumer-first when adding new fields or values

A common approach:

1. Design the new schema and how old consumers handle unknown fields.
2. Upgrade consumers to understand the new payload.
3. Confirm producer A is still supported by the new consumers.
4. Only then let producer B emit the new field/value.
5. Monitor decode errors, lag, DLQ, and business invariants.
6. Stop the old field/event once the support/replay window ends.

If an old consumer does not understand the new payload and cannot be upgraded in time, maintaining event v1 or a new versioned topic may be necessary. The choice depends on semantics and operational cost.

### 7.2. Dual-publishing requires duplicate protection

A producer emitting both V1 and V2 events can cause a consumer subscribed to both to process the same transaction twice.

Needed:

- Stable business event ID.
- Idempotent consumers.
- Deduplication rules.
- Subscription migration plan.
- Defining how many representations one business event has.
- A replay plan that does not repeat side effects.

**Two message versions do not automatically represent two distinct business events.**

### 7.3. Transactional outbox

If the application must update the DB and publish an event, the two operations may not share a transaction:

~~~text
UPDATE database: success
PUBLISH event: failure
=> Database and event are out of sync
~~~

Transactional outbox writes the business update alongside an outbox record in a single DB transaction, then a publisher forwards the outbox record to the broker. Consumers still need to handle duplicates because delivery may repeat.

Expand-and-contract lets schemas coexist, yet does not replace consistency, ordering, and retry design in distributed systems.

## 8. Avro and Schema Registry

Avro uses writer schemas and reader schemas to interpret payloads. When adding a field, an appropriate default can let a new reader process old data.

Initial schema:

~~~json
{
  "type": "record",
  "name": "OrderEvent",
  "namespace": "com.example.event",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "customerName", "type": "string"}
  ]
}
~~~

Expanded schema:

~~~json
{
  "type": "record",
  "name": "OrderEvent",
  "namespace": "com.example.event",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "customerName", "type": "string"},
    {"name": "recipientName", "type": ["null", "string"], "default": null}
  ]
}
~~~

A null default can help a new reader when reading old records missing recipientName, but business logic still must decide fallbacks and validation.

### 8.1. Distinguishing compatibility directions

| Concept | Meaning |
|---|---|
| Backward | New reader reads data created by old writer |
| Forward | Old reader reads data created by new writer |
| Full | Both directions according to defined policy |
| Transitive | Checks compatibility across multiple historical versions, not just the immediately preceding one |

Exact mode names and enforcement levels belong to the schema registry in use. Do not assume a **BACKWARD** mode suffices if a rolling deployment requires producer B to emit data for consumer A.

### 8.2. A valid schema does not guarantee valid business logic

A new reader may successfully parse an event with a null recipientName, yet if v2 business code treats recipientName as required, the program can still fail.

Need to test:

- Old payload → new reader.
- New payload → old reader, if coexisting.
- Default/null semantics.
- Conflicting old/new fields.
- Unknown enums.
- Replayed events from multiple releases.
- Batch consumers with historical payloads.

## 9. Protocol Buffers: do not reuse field numbers

Protobuf identifies fields on the wire by **field number**. When removing a field, do not reuse its number for a different meaning.

v1 example:

~~~proto
syntax = "proto3";

package example.orders;

message Order {
  string order_id = 1;
  string customer_name = 2;
}
~~~

Expand:

~~~proto
syntax = "proto3";

package example.orders;

message Order {
  string order_id = 1;
  string customer_name = 2 [deprecated = true];
  string recipient_name = 3;
}
~~~

During transition, producers/consumers may read both fields. Rules are needed when values differ.

After contract, keep the old identifier reserved:

~~~proto
syntax = "proto3";

package example.orders;

message Order {
  reserved 2;
  reserved "customer_name";

  string order_id = 1;
  string recipient_name = 3;
}
~~~

**Do not reuse number 2 for a new field with different semantics.** Old consumers could misinterpret new data without detecting a parse error.

### 9.1. Presence and default values

In Protobuf, distinguish an absent field from a default value according to its specific presence mechanism. With proto3, a scalar such as an empty string or 0 does not always prove the producer explicitly assigned the value.

If business logic needs to distinguish missing/explicit, use **optional** or an appropriate shape and test the relevant codegen/consumer versions. Do not infer required semantics purely from assumptions about default values.

## 10. The role of Java, Spring Boot, Hibernate, and migration tools

Upgrading the JDK does not automatically change the database schema. However, Java migrations often bring along upgrades to Spring, Hibernate/Jakarta Persistence, JDBC drivers, Jackson, and Flyway/Liquibase.

Changes that can have an impact:

- Naming strategy in the ORM.
- Data types and mappings.
- Enum persistence.
- Framework-suggested DDL.
- Query generation.
- Default serialization.
- Schema validation in the application.
- How connections/transactions are acquired.

Therefore, separate **code/runtime changes** from **schema changes**, with a controlled execution order.

### 10.1. Reference order

~~~text
Inventory producers/consumers
           |
           v
Expand schema additive
           |
           v
Deploy compatible application
           |
           v
Backfill + data synchronization
           |
           v
Cutover readers/writers
           |
           v
Verify no legacy consumers
           |
           v
Contract schema
~~~

Steps may span multiple releases. An intermediate technical state might serve only as a test checkpoint rather than running long-term in production.

### 10.2. Flyway

Example:

~~~text
V101__add_recipient_name.sql
V102__support_recipient_name_index.sql
V103__enforce_recipient_name_not_null.sql
V104__drop_customer_name.sql
~~~

**Splitting files is not enough** if the migration runner applies all pending versions in a single startup. Manage release gates: only distribute/execute contract scripts once conditions are met after coexist/cutover.

### 10.3. Liquibase

Liquibase changesets must likewise be split by deployment milestone with appropriate preconditions. A DDL rollback script is not equivalent to recovering data lost after **DROP COLUMN**.

### 10.4. Do not let the ORM break the production schema automatically

Schema generation/auto-DDL settings must be tightly controlled. Avoid letting a new application automatically alter/drop the schema at startup without an explicit decision, because still-running app A may still need the old column.

Production migrations should have versioned artifacts/scripts, owners, reviews, evidence, and a recovery plan.

## 11. Backfilling at large scale

A production backfill needs more than a syntactically valid UPDATE statement.

### 11.1. Requirements

- **Idempotency:** re-running after a crash does not produce bad values.
- **Batching:** limits rows/time/transaction size.
- **Checkpoint:** tracks progress and how to resume.
- **Throttling:** avoids overloading I/O, CPU, and WAL/binlog.
- **Concurrency control:** handles updates from running writers.
- **Reconciliation:** verifies the migrated data.
- **Observability:** provides logs, metrics, and alerts.

### 11.2. Operational risks

A large UPDATE can cause lock contention, transaction log growth, replication lag, or slow down production queries. Choose batch size based on actual load; do not hardcode one fixed number for every table.

If using a primary key window:

~~~sql
UPDATE customer_profile
SET recipient_name = customer_name
WHERE recipient_name IS NULL
  AND id > 200000
  AND id <= 210000;
~~~

the job can store the last processed key, yet **a watermark does not replace reconciliation**. Updates occurring after a batch passes can create new mismatches. Re-verify against invariants after writers have been coordinated.

### 11.3. Do not overwrite new values

Dangerous statement:

~~~sql
UPDATE customer_profile
SET recipient_name = customer_name;
~~~

can erase valid recipient_name values newly written by code B. Even a **WHERE recipient_name IS NULL** condition is insufficient if writer A keeps changing customer_name on already-backfilled rows.

The solution must start with the writer synchronization strategy, not merely tweaking SQL statements.

### 11.4. Aggregate verification and sampling

PostgreSQL example:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(recipient_name) AS filled_rows,
    COUNT(*) FILTER (WHERE recipient_name IS NULL) AS missing_rows
FROM customer_profile;
~~~

You can use sampling, ID-based reconciliation, normalized hash comparison, or business invariants. Two datasets with the same row count do not necessarily have equivalent content.

## 12. Rollback at each phase

| State | Can roll back application? | Data conditions |
|---|---|---|
| Before expand | To baseline | Old data untouched |
| After expand | Usually easier | Old column still exists |
| Coexist | Possible, if writers/new data remain understandable by old code | Must maintain sync and old format |
| After cutover | Not automatic | New data may not be representable in old schema |
| After contract | Old app usually can no longer run | Restoring column/data may need backup/forward-fix |

**Rolling back code does not mean rolling back data.**

If B has already emitted new events or written values invalid for A, merely redeploying A can cause errors. Similarly, do not drop the new column just to restore old code during an incident if the expand change is safe and can stay in place.

### 12.1. Feature flags are not a cure-all for every problem

Feature flags can help switch read paths or write paths, yet:

- Do not restore dropped data.
- Do not delete already-published events.
- Do not guarantee writer A understands new values.
- Do not replace data recovery migrations.

Clearly identify points of **no simple return**.

### 12.2. Recommended rollback runbook

~~~text
Rollback candidate artifact:
Current schema version:
Old schema fields still available:
New-only data already written:
Old app understands new-only data: yes/no
Producer versions to pause:
Queue/DLQ/replay plan:
Backups and restore location:
Forward-fix option:
Go/No-Go owner:
Evidence:
~~~

## 13. Test matrix to execute

### 13.1. Application against DB schema

| Test | Application | DB schema | Objective |
|---|---|---|---|
| T1 | Old A | Old | Baseline |
| T2 | Old A | Expanded | Old reader/writer does not break |
| T3 | Compatible B | Expanded | New reader/writer and fallback |
| T4 | A + B concurrently | Expanded | Sync, races, lost updates |
| T5 | New-only C | Expanded after backfill | Cutover works |
| T6 | New-only C | Contracted | Target works |
| T7 | Old A | Contracted | Explicitly confirm no longer supported |

T7 is not an acceptance test for A continuing to run after contract; it demonstrates the breaking boundary and prevents accidental deployment.

### 13.2. Producer against consumer

~~~text
                   Consumer A       Consumer B
Producer A           A -> A           A -> B
Producer B           B -> A           B -> B
~~~

If **B → A** is unsupported, specify clearly how to prevent it before producer B emits new data.

### 13.3. Edge-case tests

- New field absent/null.
- Old and new fields have different values.
- Writer A writes after backfill.
- Writer B writes and rolls back.
- Two writers update the same ID concurrently.
- Transaction fails mid-way.
- Duplicate/out-of-order events.
- DLQ replaying old events.
- Unknown enum/field.
- Scheduled legacy batch runs.
- Unexpired cache/session entries.
- Large datasets or missing historical data.
- Schema registry rejects invalid version.
- Strict JSON consumer disallowing unknown fields.
- Rolling back to artifact A after B has already written new data.

Do not run only code B against a test fixture created by B and conclude compatibility with A. Real golden payloads/artifacts from the old version are required.

## 14. Decision criteria for each milestone

### M0 — Baseline

- List of schemas, producers, consumers, and owners.
- Baseline artifacts/tests.
- Historical data and retention.
- Contract defining old/new semantics.
- Rollout/rollback plan.

**Go:** enough information to know which components will be affected.

### M1 — Expand

- Additive DDL/fields/schemas deployed.
- App A still runs.
- No destructive DDL.
- Lock/performance impact controlled.
- Tests for A against expanded schema pass.

**Go:** new structure ready without breaking the old one.

### M2 — Coexist

- App B handles old/new.
- Write consistency designed and tested.
- Checkpointed backfill.
- Mixed-version tests pass.
- Fallback/mismatch telemetry in place.

**Go:** both versions run concurrently within expected scope.

### M3 — Cutover

- Backfill and reconciliation pass.
- No writer A remaining.
- New consumer is the source of truth.
- New-only path operates stably.
- Rollback plan suited to new data.

**Go:** new structure can stand independently.

### M4 — Contract

- No supported old readers, writers, reports, or batches remaining.
- Legacy queues/DLQ/replays/caches handled.
- No remaining dependencies within the rollback window.
- Approvals obtained from owners.
- Contract DDL/protocol deployed separately.
- Backup or recovery plan available.

**Go:** removing old structures does not break any remaining supported component.

**PENDING must not be treated as GO.**

## 15. Observability to know when it is safe to contract

Some signals:

| Metric | Purpose |
|---|---|
| Old field reads/writes | Know if legacy path is still active |
| Fallback reads | Assess whether old data still exists |
| Mismatch count | Whether the two representations diverge |
| Backfill remaining | Data progress |
| Backfill latency/errors | Operational risk |
| Old app instances | Whether all old runtimes have been replaced |
| Queue consumer lag | Whether old messages still need processing |
| DLQ age/count | Whether unresolved historical messages exist |
| Schema decode errors | Whether new protocol breaks readers |
| Legacy API requests | Whether old consumers still call endpoints |
| Rollback eligibility | Whether old artifacts can still be run |

A zero metric does not prove by itself that no consumers remain. It might miss monthly batch jobs, offline reports, uninstrumented native SQL, or paused queues.

Combine metrics, logs, query inventories, owner confirmations, and an observation window matching real operational cycles.

### 15.1. Sample contract gate

~~~text
Gate ID: REMOVE_CUSTOMER_NAME

[ ] App A instances = 0
[ ] Old DB writer = 0
[ ] Old DB reader/report/batch = 0
[ ] Fallback count = 0 during observation window
[ ] Backfill completed
[ ] Missing/mismatch rows resolved
[ ] DLQ/replay/cache legacy addressed
[ ] Consumer owners acknowledged cutover
[ ] Rollback window closed or recovery approved
[ ] DDL lock/performance reviewed
[ ] Backup/recovery evidence available

Decision: GO / NO-GO / PENDING
Owner:
Evidence:
Time:
~~~

Do not open the gate merely because a day has passed. The observation window must match batch schedules, message retention, client release cycles, and support policies.

## 16. Coordinating across multiple teams

| Role | Primary responsibility |
|---|---|
| DBA/Data | DDL, locks, indexes, constraints, backups, backfill |
| Java application | Entities, repositories, read/write migration |
| API team | JSON/HTTP schemas, SDKs, compatibility |
| Messaging | Event versions, schema registry, retries, DLQ |
| Consumer owners | Confirm changes and cutover |
| SRE/Operations | Monitoring, canary, rollback, incidents |
| QA/Integration | Mixed-version tests, golden fixtures |
| Security/Governance | Data retention, sensitive data, ownership |

A migration may require distinct approval gates:

1. DBA approves additive DDL.
2. App team deploys compatible readers/writers.
3. Consumer owners confirm understanding of the new schema.
4. Data team reconciles backfill.
5. Operations confirms old traffic/instances are gone.
6. Owners approve destructive contract.

Do not treat "DBA has run the script" as proof that the entire system has finished migrating.

## 17. Common mistakes

### 17.1. Renaming/dropping in the same release as new code

Old systems may still be running, or rolling back to old code will fail.

**How to handle:** add first, migrate/coexist, then contract separately.

### 17.2. Relying solely on COALESCE

COALESCE solves missing values, not stale values after writer A keeps updating.

**How to handle:** establish a source of truth and writer synchronization strategy.

### 17.3. Dual-write lacking transaction/consistency

Writing two columns or two systems can fail partway through.

**How to handle:** appropriate transactions, reconciliation, outbox/idempotency for cross-system writes.

### 17.4. Adding NOT NULL too early

Old writers do not know the new column, so inserts begin failing.

**How to handle:** nullable/intentional default, backfill and switch writers first.

### 17.5. Backfill overwriting new data

Unconditional UPDATE can erase values newly written by app B.

**How to handle:** conflict-aware migration, snapshot/source-of-truth, and verification.

### 17.6. Testing only old producer → new consumer

During rolling upgrades, new producer → old consumer can also occur.

**How to handle:** test both directions or block the unsupported direction.

### 17.7. Ignoring batch jobs, reports, and replays

Shutting down old web instances does not mean all old consumers are gone.

**How to handle:** inventory SQL/reports, cron jobs, DLQs, caches, backups, and retention too.

### 17.8. Protobuf reusing field numbers

Old consumers can misinterpret new data.

**How to handle:** reserve retired field identifiers.

### 17.9. Dual-publishing without deduplication

One business action gets processed twice.

**How to handle:** stable event identity and idempotent consumers.

### 17.10. Migration tools running contract immediately

Splitting DDL into multiple files creates no release gate if the runner applies every file on a single startup.

**How to handle:** control when destructive migrations are distributed or executed.

### 17.11. Misusing code rollback after data has changed

Redeploying A does not turn B data back into a format A can read.

**How to handle:** have a separate data rollback or forward-fix plan.

### 17.12. Treating a zero metric as zero dependencies

A monthly consumer may not have appeared in the metric window.

**How to handle:** obtain owner confirmations and cross-check real operational schedules.

## 18. Migration documentation template

~~~text
Migration ID:
Business goal:
Schema baseline:
Schema target:
Producer versions:
Consumer versions:
Owner list:
Supported coexist window:
Data retention/replay:

Expand operations:
Compatibility readers:
Write synchronization strategy:
Backfill plan:
Conflict resolution:
Reconciliation criteria:
Cutover switch:
Contract operations:

Old artifacts still supported:
Rollback-compatible schema states:
Data rollback / forward-fix:
Evidence location:
Observability:
Go/No-Go gates:
Approvals:
Residual risks:
~~~

Illustrative example:

~~~text
ID: CUSTOMER-RECIPIENT-01
Baseline: customer_profile.customer_name
Target: customer_profile.recipient_name
Expand: add nullable recipient_name
Coexist: B reads both; writer synchronization required
Backfill: bounded, resumable, non-overwriting
Cutover: all writers use recipient_name; mismatch = 0
Contract: drop customer_name in later release
Rollback: A only before contract and while data compatible
Evidence: SQL checks + A/B integration + owner confirmations
~~~

This template must be adapted to specific data risks and systems. No single fixed duration fits every consumer.

## 19. Pre-completion migration checklist

### Assessment

- [ ] Identified all relevant database, JSON, and event schemas.
- [ ] Listed consumers, producers, and owners.
- [ ] Documented historical data/retention/replay policy.
- [ ] Distinguished source, binary, data, and protocol compatibility.
- [ ] Finalized semantics of old/new fields.

### Expand

- [ ] Initial changes are additive and do not break old readers/writers.
- [ ] New columns/fields have appropriate nullability/defaults.
- [ ] DDL locks and performance have been evaluated.
- [ ] Old consumers accept the expanded schema, or producers do not emit the new parts yet.
- [ ] Expand migration is separated from destructive contract.

### Coexist

- [ ] Defined source of truth for mutable data.
- [ ] Verified dual-write/sync strategy.
- [ ] Tested concurrency and stale reads.
- [ ] Backfill is idempotent, bounded, and resumable.
- [ ] Reconciliation is independent of job progress.
- [ ] Tested A→B and B→A where needed.
- [ ] Dual-published messages have idempotency.
- [ ] Telemetry in place for fallbacks/mismatches/errors.

### Contract

- [ ] No remaining readers, writers, reports, or batch jobs using the old schema.
- [ ] Legacy queues/DLQ/caches/replays have been handled.
- [ ] New data satisfies invariants and constraints.
- [ ] Rollback window closed or clear recovery exists.
- [ ] Owners approved the GO decision.
- [ ] Contract DDL/protocol has a plan and evidence.
- [ ] Retired field identifiers are not misused/reused.
- [ ] Temporary adapters/fallbacks/triggers removed at a safe time.

## 20. Reference documentation for real-world implementation

Read documentation matching the exact database, ORM, and protocol versions:

- **PostgreSQL ALTER TABLE:** https://www.postgresql.org/docs/current/sql-altertable.html
- **PostgreSQL transactions:** https://www.postgresql.org/docs/current/transaction-iso.html
- **Flyway:** https://documentation.red-gate.com/fd/
- **Liquibase:** https://docs.liquibase.com/
- **Jakarta Persistence:** https://jakarta.ee/specifications/persistence/
- **Spring Boot database initialization:** https://docs.spring.io/spring-boot/reference/howto/data-initialization.html
- **Apache Avro specification:** https://avro.apache.org/docs/current/specification/
- **Protocol Buffers schema evolution:** https://protobuf.dev/programming-guides/proto3/#updating
- **Protocol Buffers reserved values:** https://protobuf.dev/programming-guides/proto3/#reserved

Do not apply online DDL, transaction, or lock strategy syntax verbatim from one database engine to another. Schema compatibility rules also vary by registry mode and serialization library.

---

**Conclusion:** Expand-and-contract is not two SQL add/drop commands run minutes apart. It is **an evidence-backed compatibility roadmap**: open the new structure without breaking the old one, synchronize writers, migrate data, verify both old and new producers/consumers, and only contract once no supported component still needs the old schema. In Java migrations, properly managing release gates, historical data, transactions, retries, rollbacks, and API boundaries reduces the risk of a single schema change disrupting the entire system.
