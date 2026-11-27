# Neo4j CDC and Version or Edition Support Requirements

## Learning Objectives

After this lesson, you will be able to:

- Explain what **Change Data Capture (CDC)** in Neo4j is, and how it differs from batch imports, periodic polling, and application-level event publishing.
- Verify the **Neo4j version, edition/Aura tier, procedure names, and access permissions** before designing a CDC integration.
- Enable CDC in `DIFF` or `FULL` mode, inspect configurations, and query changes with Cypher.
- Design a consumer with **cursors/checkpoints**, retry handling, deduplication, transaction log exhaustion recovery, and post-restore recovery.
- Choose between CDC and alternative integration approaches when version, edition, or operational constraints are not met.

The **Data Integration** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module situates Neo4j within the data flow connecting Java/Spring Data Neo4j applications, message brokers, and analytics or search systems. Neo4j models relationships via a **property graph** with nodes, relationships, and properties; CDC notifies external consumers of changes to these elements as transactions commit.

> **Version scope:** This lesson uses CDC syntax for Neo4j 5.17 and later, along with notes for versions 5.13–5.16. Edition and cloud service capabilities may evolve; before deploying, always check the **version, edition/service tier, user privileges, and version-matched documentation**. Configuration examples are illustrative and require appropriate administrative privileges.

## 1. What Is CDC and What Problem Does It Solve?

**Change Data Capture** is a technique for capturing committed data changes so downstream systems can react. With official Neo4j CDC, change details are extracted from the **enriched transaction log** (*transaction-log enrichment*). A change may involve:

- **Nodes:** creating a node, updating labels/properties, deleting a node.
- **Relationships:** creating, updating properties, deleting a relationship.
- **Transaction metadata:** transaction ID, event sequence within the transaction, timestamps, and metadata provided by the CDC schema.

For example, an application uses Neo4j to manage `Customer` —`PLACED`→ `Order` relationships. When an order transitions from `PENDING` to `PAID`, the search engine can update its search index, analytics can recompute reports, and a downstream service can react to the update.

~~~mermaid
flowchart LR
    A["Java App / Spring Data Neo4j"] -->|Cypher transaction| N[("Neo4j")]
    N --> L["Transaction log<br/>CDC enrichment"]
    L --> C["CDC consumer<br/>checkpoint + retry"]
    C --> K["Kafka / event bus"]
    C --> D[("Search / Analytics")]
~~~

**Key distinction:** Neo4j CDC provides **Neo4j's own change stream**. It does not automatically emit HTTP webhooks, does not push to Kafka without a connector/consumer, and does not replace an initial snapshot load for existing historical data.

| Integration Pattern | Typical Use Case | Key Limitations |
| --- | --- | --- |
| **CDC from transaction log** | Tracking committed creates/updates/deletes, syncing downstream systems | Requires version/edition support, privileges, checkpoints, and log retention |
| **Periodic Cypher polling** | Simple needs, latency-tolerant, environments lacking CDC | Hard to detect deletes; requires manual watermarks, risks gaps/duplicates |
| **App-level events / transactional outbox** | Publishing domain events like `OrderPaid` | Application must explicitly emit events and ensure reliable publishing |
| **CSV / batch / snapshot import** | Initial data loading or full data rebuilds | Does not track continuous changes after the load |

CDC reflects **data-level mutations**, not every business semantic. Updating a `status` property to `PAID` may act as a signal, yet "validly paid" still depends on business logic outside the database.

## 2. Version and Edition Support Matrix

Check **two independent axes**: **version** and **edition/deployment tier**. Upgrading the version alone while remaining on an unsupported edition will not make CDC available.

| Environment | Official CDC Support | Notes |
| --- | --- | --- |
| **Self-managed Neo4j Community Edition** | **No** official Enterprise CDC | Similarly named procedures or third-party plugins are not equivalent to official CDC support |
| **Neo4j Enterprise Edition 5.13–5.16** | Available since **5.13**, beta stage | Uses legacy procedure names `cdc.current`, `cdc.earliest`, `cdc.query`; verify version-specific constraints |
| **Neo4j Enterprise Edition 5.17–5.22** | Available, still in beta | Procedures moved to the `db.cdc.*` namespace starting in 5.17 |
| **Neo4j Enterprise Edition 5.23+** | CDC is out of beta | Feature still must be enabled per database with permissions and retention configured |
| **Neo4j 2025.x/2026.x Enterprise** | Check corresponding release docs; CDC remains documented in current releases | Additional output fields in procedures may depend on **version and Cypher version** |
| **AuraDB Business Critical / AuraDB Virtual Dedicated Cloud** | Supported per current CDC docs | Enabled via **Edit CDC Mode** in Aura controls; do not treat self-managed DDL commands as universal instructions |
| **Other AuraDB tiers** | **Do not assume** availability | Check the official feature matrix and admin privileges for your exact subscribed tier |

Key milestones:

1. **Neo4j 5.13:** CDC officially debuted in **beta**, targeting Enterprise and AuraDB Enterprise at release time.
2. **Neo4j 5.17:** renamed `cdc.earliest/current/query` to `db.cdc.earliest/current/query`; legacy application code must be reviewed upon upgrade.
3. **Neo4j 5.23:** CDC **graduated from beta**.
4. **Neo4j 2026.06, Cypher 25:** current documentation adds `txCommitTime` to `db.cdc.current()` output; do not assume this field exists across all versions or Cypher modes.

This support overview is based on [Neo4j CDC Introduction](https://neo4j.com/docs/cdc/current/), [CDC Changelog](https://neo4j.com/docs/cdc/current/changelog/), [CDC on Neo4j DBMS](https://neo4j.com/docs/cdc/current/get-started/self-managed/), and [CDC on Aura](https://neo4j.com/docs/cdc/current/get-started/aura/). When coding against a running deployment, consult documentation matching your **exact version line** rather than blindly copying examples from the newest release.

### 2.1. Checking Your Connected Version and Environment

On a database permitting system inspection procedures:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Output might indicate version `5.2x` and edition `enterprise`. Cross-check with the matrix; **do not guess from Neo4j Browser's app name** or the Java Driver version.

Check CDC procedures registered in the catalog:

~~~cypher
SHOW PROCEDURES
YIELD name
WHERE name STARTS WITH 'db.cdc.'
RETURN name
ORDER BY name;
~~~

On 5.13–5.16, procedure names start with `cdc.`. **Seeing procedure names alone is insufficient** to conclude CDC is enabled or the user holds read permissions. In Aura, certain system queries may be restricted; rely on tier details and the official management console.

### 2.2. Mandatory Readiness Checklist

| Question | Required Confirmation |
| --- | --- |
| Which Neo4j edition/tier? | Self-managed Enterprise or a currently listed supported Aura tier |
| Exact version? | Correct procedure names/syntax for that version |
| Is CDC enabled on the **target database**? | `DIFF` or `FULL`, not `OFF` |
| User privileges? | Database access plus CDC procedure execution following least privilege |
| Log retention? | Sufficient for consumers to recover after downtime |
| Cursor storage mechanism? | Durable, scoped per database/consumer |
| Target system? | Business keys, deduplication, and error recovery |

## 3. How Neo4j Records Changes: OFF, DIFF, and FULL

Neo4j requires **transaction log enrichment** so CDC has sufficient detail to describe mutated elements. By default, CDC is **off**; creating graphs or constraints/indexes does not enable CDC automatically.

| Mode | Meaning | Best For |
| --- | --- | --- |
| `OFF` | No CDC enrichment written; default setting | Databases not using CDC |
| `DIFF` | For updates, records only the delta between before/after entity state | Incremental syncing, reducing payload size compared to FULL in many cases |
| `FULL` | Records complete before/after state of changed entities | Auditing, consumers needing full entity records |

**Example:** Node `(:Customer {customerId:'C-101', city:'Hanoi', tier:'SILVER'})` updates `tier` to `GOLD`. In `DIFF`, the update state mainly reports the change to `tier`; in `FULL`, before/after state can include all properties needed to describe the node. For **create** and **delete** operations, CDC behaves inherently by operation type: creates carry `after` data and deletes carry `before` data, even in `DIFF`.

Switching `DIFF` ↔ `FULL` while a consumer is running can **alter event structure**; decoders and downstream logic must handle both accurately. Enabling CDC writes extra transaction log data, increasing disk usage, I/O, and log rotation/pruning frequency. Measure overhead on your workload rather than assuming a fixed percentage across all systems.

## 4. Enabling and Checking CDC on Self-Managed Neo4j Enterprise

> DDL commands in this section apply only with administrative privileges on a self-managed environment supporting CDC. Execute them from the **`system` database** context according to how your client/driver selects databases. Never run them arbitrarily in production.

### 4.1. Inspecting Current Configuration

~~~cypher
SHOW DATABASES
YIELD name, options
RETURN name, options
ORDER BY name;
~~~

If unconfigured for the `neo4j` database, `options` may omit `txLogEnrichment`, meaning CDC is at the default `OFF`. Always verify the actual database name; not every deployment uses a database named `neo4j`.

### 4.2. Enabling DIFF on an Existing Database

~~~cypher
// Admin command example; run on the system database.
ALTER DATABASE neo4j
SET OPTION txLogEnrichment 'DIFF';
~~~

To capture full state for subsequent changes, use `'FULL'`:

~~~cypher
ALTER DATABASE neo4j
SET OPTION txLogEnrichment 'FULL';
~~~

Afterward, re-run `SHOW DATABASES YIELD name, options` to confirm `txLogEnrichment` reflects the intended mode. If creating a **new database** with CDC enabled immediately:

~~~cypher
// Run only when you genuinely want to create the example database.
CREATE DATABASE graph_events IF NOT EXISTS
OPTIONS {txLogEnrichment: 'DIFF'};
~~~

**Does not emit historical data:** Once CDC is enabled, only changes **from that moment onward** carry CDC enrichment. Syncing pre-existing data requires a separate **snapshot/backfill** workflow and consistent cutover into the new CDC stream.

### 4.3. Disabling CDC and Impact on Cursors

~~~cypher
// Admin command example; do not execute in the exercise if you need to preserve the event stream.
ALTER DATABASE neo4j
SET OPTION txLogEnrichment 'OFF';
~~~

Disabling CDC **breaks the continuity of change identifiers**. If re-enabled later, old cursors cannot resume seamlessly; consumers must perform a bootstrap/recovery workflow. On self-managed instances, you can also run `REMOVE OPTION txLogEnrichment` to revert to the default disabled state.

## 5. Enabling CDC on Aura

On supported AuraDB tiers, administrators use the **Edit CDC Mode** option in the instance management console to set `OFF`, `DIFF`, or `FULL`. Do not assume `ALTER DATABASE` works as in self-managed deployments; Aura lifecycle controls are managed by the service.

Aura documentation highlights:

- **New**, **cloned**, **paused**, or **snapshot-restored** instances may revert CDC to `OFF`.
- When **toggled off and back on**, prior change identifiers no longer belong to the same event sequence.
- Whenever toggling `DIFF`/`FULL`, consumers must support the corresponding change format.
- Re-verify settings after any instance lifecycle operation and before restarting connectors.

Do not rely on legacy tier names in older tutorials to assume every current Aura tier supports CDC. On Aura, verify **actual feature availability on your instance and subscription tier**.

Source: [CDC on Neo4j Aura](https://neo4j.com/docs/cdc/current/get-started/aura/).

## 6. Querying Change Events via Procedures

Once CDC is enabled, Neo4j exposes procedures for **change identifiers** (cursors) and change event streams.

| Procedure (5.17+) | Purpose |
| --- | --- |
| `db.cdc.earliest()` | Retrieves the identifier at the start of the currently retained change range |
| `db.cdc.current()` | Retrieves an identifier near the present point, suited to begin tracking **new changes** |
| `db.cdc.query(from, selectors)` | Retrieves changes **after** identifier `from`; `selectors` is optional |

On 5.13–5.16, replace `db.cdc.` with `cdc.` per that release's docs. Never mix procedure namespaces across versions.

### 6.1. Obtaining the Initial Cursor

~~~cypher
CALL db.cdc.current()
YIELD id
RETURN id;
~~~

Persist the returned `id` safely in the application. The identifier is an **opaque string**: do not parse it as a number, modify it, or compute `id + 1`. Newer versions/Cypher modes may yield additional output columns; this example intentionally uses `YIELD id` for broader compatibility.

If the application wants to read changes **still retained in the log**, use:

~~~cypher
CALL db.cdc.earliest()
YIELD id
RETURN id;
~~~

`earliest` **does not mean** the entire history since database creation; it reflects only the currently usable change window governed by log configuration and lifecycle.

### 6.2. Writing Sample Data in a Separate Transaction

Execute in a separate transaction after recording the cursor above:

~~~cypher
MERGE (c:Customer {customerId: 'C-101'})
SET c.city = 'Hanoi',
    c.tier = 'GOLD';
~~~

If the node already exists and no properties actually change, the database may not emit the expected update event. To reliably observe events in a lab environment, mutate a real property or create a new node with a dedicated exercise ID.

### 6.3. Reading Changes from the Cursor

In a **third** read transaction, pass the exact saved `id` string:

~~~cypher
CALL db.cdc.query($fromId, [])
YIELD id, txId, seq, metadata, event
RETURN id, txId, seq, metadata, event;
~~~

Example application parameter (replace the placeholder with the actual identifier):

~~~json
{
  "fromId": "opaque-change-identifier-from-db-cdc-current"
}
~~~

**Crucial semantics:** `fromId` is an **exclusive** starting point. `db.cdc.query` returns events strictly **after** that identifier, not the event at that identifier itself. Each returned event includes a new `id` to continue polling from. Calling the procedure without persisting/passing the right cursor risks starting from current and **missing earlier events**.

Reading the cursor, writing data, and calling `db.cdc.query` are **three separate transactions** in this example. Never hold one long transaction containing all three expecting it to capture events: CDC reads committed transactions.

### 6.4. Recognizing Event Fields

A CDC row typically has the structure:

~~~text
id           : opaque change identifier of the event
txId         : transaction identifier
seq          : event position within that transaction
metadata     : transaction information (e.g., commit time)
event        : changed element, operation, and before/after state
~~~

**Abbreviated illustrative** example (not the full procedure output):

~~~json
{
  "id": "<opaque-id>",
  "txId": 42,
  "seq": 0,
  "metadata": { "captureMode": "DIFF" },
  "event": {
    "eventType": "n",
    "operation": "u",
    "labels": ["Customer"],
    "keys": {},
    "state": {
      "before": { "properties": { "tier": "SILVER" } },
      "after": { "properties": { "tier": "GOLD" } }
    }
  }
}
~~~

Where:

- `eventType = 'n'` denotes a **node**, `'r'` denotes a **relationship**.
- `operation = 'c'` / `'u'` / `'d'` corresponds to **create / update / delete**.
- `state.before` and `state.after` hold contents depending on mode and operation; the non-existent side (before for create, after for delete) is `null`.
- `keys` can assist with **logical entity identification** when matching key constraints exist in the schema; `elementId` is not a business key across backups or database lifecycles.
- `txId` combined with `seq` locates an event within a transaction. Do not infer application-level statement order strictly from `seq`; observed event order does not necessarily mirror exact Cypher clause execution order inside the transaction.

In the JSON example above, `<opaque-id>` is merely an explanatory placeholder. Consumers must use the exact identifier returned by Neo4j. See [Format of change events](https://neo4j.com/docs/cdc/current/procedures/output-schema/).

## 7. Designing the Consumer: Cursors, Retries, and Deduplication

CDC is typically **polled by a consumer** periodically or handled via a connector. A clean architecture:

~~~mermaid
flowchart TB
    A["Read committed cursor"] --> B["db.cdc.query(cursor)"]
    B --> C{"New events?"}
    C -->|No| W["Wait / next poll"]
    W --> B
    C -->|Yes| D["Decode + validate event"]
    D --> E["Downstream upsert/delete using stable key"]
    E --> F{"Sink confirmed durably?"}
    F -->|No| R["Retry, do not advance cursor"]
    R --> E
    F -->|Yes| G["Save cursor of processed event"]
    G --> B
~~~

### 7.1. Mandatory Principles

1. **Persist the cursor durably** scoped to the exact database and consumer/subscription; never keep it only in RAM.
2. **Process and confirm downstream writes before advancing the cursor.** Advancing the cursor first and crashing while writing to the sink loses events.
3. **Expect replay/duplicate processing:** if the sink commits but the consumer crashes before saving the cursor, the same event arrives again on restart.
4. **Deduplication/idempotency:** use the event `id` or stable business identity combined with version/write rules to prevent duplicate records.
5. **Run only one active consumer per cursor**, or implement explicit partitioning/coordination. Multiple instances blindly overwriting checkpoints will skip events.
6. **Monitor backlog/lag:** track time from commit to processing, last checkpoint timestamp, error counts, and remaining log retention window.

If the sink and cursor reside in **the same downstream database**, you can commit both the event's effect and the checkpoint inside one downstream transaction. If they reside in separate systems, never assume distributed atomicity; rely on idempotency, replayable checkpoints, and error handling.

### 7.2. Java Driver Pseudocode

The snippet below illustrates the pattern and is **not a standalone runnable app**. `checkpointStore` and `sink` are project-implemented components; every CDC read transaction must target the CDC-enabled database with an authorized session:

~~~java
String cursor = checkpointStore.load(databaseName, consumerName);
if (cursor == null) {
    // Choose bootstrap policy deliberately:
    // current() -> track only new events;
    // earliest() -> events still remaining in the log.
    cursor = readCurrentCdcId(driver, databaseName);
    checkpointStore.save(databaseName, consumerName, cursor);
}

for (CdcChange change : readChanges(driver, databaseName, cursor)) {
    // Process idempotently. A crash may cause this event to be read again.
    sink.applyIdempotently(change.id(), change.event());

    // Acknowledge cursor ONLY AFTER the sink has written successfully and durably.
    checkpointStore.save(databaseName, consumerName, change.id());
    cursor = change.id();
}
~~~

`readChanges` can use `Session.executeRead` with Cypher:

~~~cypher
CALL db.cdc.query($cursor, [])
YIELD id, txId, seq, metadata, event
RETURN id, txId, seq, metadata, event;
~~~

Never persist `elementId` as a permanent business identifier. For updates/deletes, consumers need proper keys from domain data. **Node key/relationship key constraints** (where edition/version supports them) surface key info in CDC; otherwise use stable business ID properties validated to meet sink requirements.

### 7.3. Kafka Integration Pattern

To stream events into Apache Kafka, you can use the **Neo4j Connector for Apache Kafka** in **source mode** leveraging CDC on supported versions/editions. Kafka Connect manages publishing streams and storing connector offsets, though you must still configure topics, permissions, serialization, retention, and error policies. The **source connector** reads changes from Neo4j to Kafka; the **sink connector** flows the opposite way (Kafka → Neo4j). Never confuse the two directions.

When downstream consumers read from Kafka, **Kafka offsets** and **CDC change identifiers** are distinct concepts; recovery designs must account for both the connector and actual checkpoints. See [Kafka source CDC quickstart](https://neo4j.com/docs/kafka/current/source/quickstart-cdc/).

## 8. Transaction Log Retention and Discontinuity Scenarios

CDC relies on transaction logs. It is **not an infinite history**; logs are rotated/pruned according to configuration. If a consumer pauses longer than log retention, its cursor may point to purged entries.

| Scenario | Risk | Mitigation |
| --- | --- | --- |
| Consumer paused too long, logs pruned | `db.cdc.query` can no longer read from old cursor | Alert on lag, increase retention appropriately, or re-bootstrap |
| CDC is `OFF` | Procedures report CDC disabled | Verify edition, mode, and DB config |
| CDC toggled off then on | Old identifier is no longer valid | Initialize a fresh cursor chain, resync if needed |
| Backup/snapshot restore or clone | Target database no longer shares identifier lineage | Follow documented restore and re-bootstrap workflows |
| Switching `DIFF` to `FULL` | Event format changes | Consumer handles both formats; deploy controlled rollout |
| Sink fails and consumer restarts | Event may be re-read | Idempotent upsert/delete; advance cursor only after sink success |

Per CDC error documentation, error codes like `Neo.DatabaseError.ChangeDataCapture.Disabled`, `Neo.DatabaseError.ChangeDataCapture.ScanFailure`, and `Neo.ClientError.ChangeDataCapture.InvalidIdentifier` help distinguish disabled CDC, missing transaction log entries, and invalid identifiers. Applications must not infinitely retry the exact same cursor when logs have been pruned; raise an alert, halt, or trigger the proper re-bootstrap workflow.

### 8.1. Initial Snapshot + Ongoing CDC

To seed a downstream system with **all existing data** and continue streaming deltas, design two phases:

~~~text
Phase 1: Build a snapshot/backfill of the entire graph or relevant dataset.
Phase 2: Continuously apply CDC events after the established consistent boundary.
~~~

The hard part is the **overlap boundary** between snapshot and CDC. Exporting the snapshot first and calling `db.cdc.current()` afterward risks missing transactions committed in between. Capturing the cursor first and exporting the snapshot afterward creates overlapping events requiring version guards or idempotent upserts. Either way, establish a **consistent cutover boundary and reconciliation strategy** suited to your architecture; never glue two scripts together assuming zero data loss.

### 8.2. Log Storage and Latency Overhead

Enabling CDC enriches transaction logs with extra data, impacting disk space, I/O, write throughput, and pruning rates. Size retention by considering **maximum expected downtime + backlog catch-up time + safety margin**, then benchmark with realistic workloads. According to the [self-managed guide](https://neo4j.com/docs/cdc/current/get-started/self-managed/), log overhead can increase noticeably under `DIFF` or `FULL`; exact ratios depend on transaction shapes and data volumes.

## 9. Security and Privilege Boundaries

CDC can expose **changes across the entire database** without automatically filtering every event by standard user node/property read privileges. Therefore, grant CDC access carefully:

- `db.cdc.query` requires **appropriate administrative privileges**, or a combination of **execute procedure** and **execute boosted procedure** privileges on an authorized role, alongside database access.
- `db.cdc.current` and `db.cdc.earliest` generally require database access and standard procedure execution privileges.
- Grant permissions strictly to dedicated service accounts; safeguard PII, secrets, and sensitive data that may appear inside events.
- Separate permissions for **enabling/disabling CDC** (administrative DDL) from permissions for **reading events** in applications.
- When forwarding to Kafka or analytics, enforce access controls on brokers/topics and target systems; avoid logging raw events to unprotected application logs.

See [CDC self-managed: Security](https://neo4j.com/docs/cdc/current/get-started/self-managed/). `GRANT` syntax and support depend on edition and privileges; privilege examples in documentation are intended for administrators, not arbitrary developer execution.

## 10. Hands-On Exercise: Verifying Compatibility and Reading Events

### Scenario

You inherit a Neo4j environment of unknown edition and are asked to stream `Customer` changes to an analytics system. Follow this non-destructive verification workflow:

1. **Verify version/edition:** run `CALL dbms.components()` if authorized or inspect admin console info; record exact version.
2. **Verify CDC support:** cross-check the Enterprise/Aura matrix, version, and procedure namespace.
3. **Verify CDC status:** check `SHOW DATABASES YIELD name, options` on self-managed or **Edit CDC Mode** on Aura.
4. **On an authorized licensed environment**, enable `DIFF` or `FULL` on the practice database.
5. **Fetch the current ID** via `db.cdc.current()`; copy the exact `id` string.
6. **Modify data in another transaction**, using a dedicated test ID and an update that actually changes a property.
7. **Read events after the ID** via `db.cdc.query($fromId, [])`, verifying entity type, operation, `state`, and metadata.
8. **Test retry behavior:** process an event successfully while deliberately withholding checkpoint persistence; upon re-reading, downstream data must not duplicate.
9. **Check operational boundaries:** document log retention, service permissions, and lag alerting thresholds.

Sample write statements for testing in a lab environment only:

~~~cypher
MERGE (c:CdcPractice {practiceId: 'CDC-001'})
SET c.value = 'FIRST';

MATCH (c:CdcPractice {practiceId: 'CDC-001'})
SET c.value = 'SECOND';
~~~

If both statements are sent in a single transaction or batched by the client, emitted events may differ from a naive "one create + one update" per statement expectation. To observe separated changes, run **separate committed transactions**.

### Knowledge Check Questions

**Q1.** Can a Neo4j 5.25 Community server enable official CDC solely via `ALTER DATABASE`?

**Answer:** No. A recent version number does not override edition limits; official CDC covered here is an Enterprise/supported Aura tier feature.

**Q2.** Why might an application written for Neo4j 5.15 break when calling `cdc.query` unchanged on a newer release?

**Answer:** The namespace changed from `cdc.*` to `db.cdc.*` in 5.17. Verify procedure names and signatures for your target version.

**Q3.** For a consumer that only needs changes starting from now, should you choose `current` or `earliest`?

**Answer:** Typically `db.cdc.current()`, persisting the cursor before starting change tracking; `earliest` reads from the beginning of the currently retained log window, not necessarily the dawn of database history.

**Q4.** Why must the cursor be saved only after the sink confirms?

**Answer:** Advancing the cursor beforehand risks dropping events if the sink write fails. Saving afterward can cause reprocessing upon crash, so the sink must support idempotency.

**Q5.** Does `FULL` mean every event carries domain-level meaning like `OrderPaid`?

**Answer:** No. `FULL` defines entity before/after state verbosity; domain semantics must be inferred from the model, event contracts, or published explicitly by the application.

**Q6.** After restoring a database, can all old change IDs be reused directly?

**Answer:** Never assume so. Identifiers are tied to the database/transaction log lifecycle; follow recovery procedures supported in Neo4j documentation.

## 11. Pre-Deployment Decision Checklist

- [ ] Confirm **version, edition/Aura tier**, and CDC documentation match the actual deployment.
- [ ] Verify procedure names: `cdc.*` on 5.13–5.16 vs. `db.cdc.*` on 5.17+.
- [ ] Enable CDC on the **correct database** with `DIFF` or `FULL`, and verify mode afterward.
- [ ] Pick event mode and ensure consumers handle the corresponding `before/after` format.
- [ ] Grant least-privilege CDC access and protect events containing sensitive data.
- [ ] Design snapshot/bootstrap and reconciled cutover to CDC.
- [ ] Persist cursors durably, respect **exclusive ID** semantics, and enforce retries and sink idempotency.
- [ ] Configure log retention, lag alerts, and recovery procedures for pruned logs.
- [ ] Test toggle off/on, restore/clone/pause, mode changes, and version upgrades in staging.
- [ ] Benchmark transaction log/I/O overhead, write impact, throughput, and consumer lag.

## Official References

- [Neo4j Change Data Capture — Introduction](https://neo4j.com/docs/cdc/current/)
- [Neo4j CDC — Changelog and Version Milestones](https://neo4j.com/docs/cdc/current/changelog/)
- [CDC on Neo4j DBMS — Self-Managed Configuration](https://neo4j.com/docs/cdc/current/get-started/self-managed/)
- [CDC on Neo4j Aura — Tiers and Mode Configuration](https://neo4j.com/docs/cdc/current/get-started/aura/)
- [Use CDC to query changes — Procedures](https://neo4j.com/docs/cdc/current/procedures/)
- [Format of change events](https://neo4j.com/docs/cdc/current/procedures/output-schema/)
- [CDC troubleshooting](https://neo4j.com/docs/cdc/current/troubleshooting/)
- [Neo4j Connector for Kafka — CDC source quickstart](https://neo4j.com/docs/kafka/current/source/quickstart-cdc/)

**Conclusion:** Neo4j CDC tracks committed node/relationship mutations from enriched transaction logs. An integration design is valid only when **version and edition/tier support it**, CDC is enabled on the target database, the consumer holds proper privileges, and cursor lifecycles are tightly managed. For reliable synchronization, pair CDC with **durable checkpoints, idempotent processing, log retention sizing, initial data bootstrapping, and a tested recovery plan**.
