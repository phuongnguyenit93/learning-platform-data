# Reconciling, Resolving Drift, and Recovering Sync Pipelines After Incidents

When Neo4j ingests data from another system, a sync job reporting "finished" is not enough to prove the graph is accurate. Events can arrive duplicated, out of order, missing endpoint nodes, or commit to Neo4j just before the consumer loses connection prior to acknowledging the offset. Extended outages can also allow source data to keep evolving while the graph remains frozen at an older version.

This lesson belongs to the **Data Integration** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. Neo4j stores connected data using a **property graph** model, uses Cypher to mutate nodes/relationships, relies on indexes and constraints to protect keys, and is typically integrated via the Java Driver or Spring Data Neo4j. The lesson focuses on **reconciling data between source and Neo4j, classifying and repairing drift, and recovering a sync stream so it can be replayed safely**.

After this lesson, you will be able to:

- Define the authoritative *source of truth*, sync unit, identity keys, source versions, and reconciliation cutoff point.
- Reconcile counts, properties, versions, relationships, and deletions using Cypher alongside source data.
- Distinguish duplicate events, lost events, out-of-order arrivals, mapping errors, missing dependencies, and partial writes.
- Design idempotent writes, manage checkpoints/offsets, and recover from incidents without applying a business change twice.
- Build an incident runbook, write replay tests, and measure sync quality with operational metrics.

## 1. See the Entire Pipeline Before Fixing a Single Record

Suppose a transactional system stores customers and orders in a source database. Neo4j serves relationship queries across customers, orders, and related entities:

~~~text
      SOURCE SYSTEM
    (Customer, Order)
             |
   Snapshot / CDC / Event
             |
             v
       Broker / Queue
             |
             v
  Consumer + data normalization
             |
      Neo4j transaction
             |
             v
(:SyncDemoCustomer)-[:DEMO_PLACED]->(:SyncDemoOrder)
             |
             v
  Reconciliation + alerts + repair
~~~

This pipeline may use Kafka, CDC, or another queuing system; the lesson is not tied to a single vendor product. Each component holds a clear responsibility:

| Component | Role | Risks to Control |
| --- | --- | --- |
| Source database | Holds original business state when designated authoritative. | Consistent snapshot reads, capturing updates/deletes. |
| CDC/event producer | Converts mutations into events. | Identifiers, schemas, ordering, log completeness. |
| Broker/queue | Persists, delivers, and replays events. | Offsets, retention, retries, disconnects, partitioning. |
| Consumer | Maps source data into nodes/relationships. | Key normalization, stale event filtering, atomic writes. |
| Neo4j | Stores the query-serving graph projection. | Constraints, accurate endpoints, valid state and versions. |
| Reconciler | Compares source against target state at a fixed cutoff. | Surfacing true drift while avoiding false alarms from normal lag. |

In this architecture, **the transactional source is authoritative** for synchronized properties. If certain properties are mutated directly in Neo4j, define **per-field** ownership explicitly: the reconciler must never blindly overwrite data for which Neo4j itself is the source of truth.

### 1.1. Syncing Does Not Mean Copying Every Column

Example data mapping:

| Source Record | Neo4j Representation | Rule |
| --- | --- | --- |
| Customer(tenant_id, customer_id, full_name, version) | `(:SyncDemoCustomer {tenantId, customerId, name, sourceVersion})` | Customer key combines tenant and customer ID. |
| Order(tenant_id, order_id, customer_id, total_minor, status, version) | `(:SyncDemoOrder {tenantId, orderId, customerId, amountMinor, status, sourceVersion})` | Monetary values in minor units; never round arbitrarily. |
| Order.customer_id | `(:SyncDemoCustomer)-[:DEMO_PLACED]->(:SyncDemoOrder)` | Each order belongs to strictly one customer in this example model. |
| Event(event_id, aggregate_key, version, payload) | `(:SyncDemoAppliedEvent {eventId, aggregateKey, sourceVersion})` | Audit trail of events already applied in Neo4j. |

Labels/types prefixed with `SyncDemo` are used for study exercises. Production systems may pick different names while keeping an explicit **data contract** between source and graph.

## 2. Invariants to Reconcile

Reconciliation is meaningful only when you know what must hold true. For the example model:

| Code | Invariant | Verification Check |
| --- | --- | --- |
| R1 | No two `SyncDemoOrder` nodes share `(tenantId, orderId)`. | Composite uniqueness constraint on the property pair. |
| R2 | Order properties reflect the latest accepted source state. | Compare `sourceVersion`, `status`, `amountMinor`, and `customerId`. |
| R3 | Every active order has strictly one `DEMO_PLACED` relationship from the matching customer. | Count edges; verify endpoint customer key and tenant. |
| R4 | Source-deleted records obey the chosen deletion policy. | Verify tombstones, hidden flags, or physical deletes in Neo4j. |
| R5 | No business event is applied twice. | Unique `eventId` marker and idempotent replay handling. |
| R6 | A checkpoint is published only after its corresponding write is durable. | Cross-check commit state against event read position. |

**Invariants must be scoped:** by tenant, entity type, schema version, and time window. "Neo4j has 100 fewer orders than the source" does not prove data loss if the source already includes new orders not yet reached by the consumer, or if Neo4j intentionally omits deleted orders.

### 2.1. Identity Keys and Source Versions

Each event should carry at minimum:

~~~json
{
  "eventId": "orders/partition-2/offset-1042",
  "aggregateKey": "tenant-a/order-100",
  "entityType": "Order",
  "operation": "UPSERT",
  "sourceVersion": 12,
  "schemaVersion": 2,
  "payload": {
    "tenantId": "tenant-a",
    "orderId": "order-100",
    "customerId": "customer-7",
    "amountMinor": 125000,
    "status": "PAID"
  }
}
~~~

This is an **illustrative contract**, not a mandatory format for every CDC engine. `eventId` must stably identify the same event upon broker redelivery; `aggregateKey` identifies the entity requiring ordering; `sourceVersion` is a **per-entity** monotonically increasing version if supported by the source. Wall-clock timestamps emitted by multiple hosts cannot automatically substitute for ordered versions.

If the producer emits **full-state events** (*upsert snapshots*), a newer snapshot can supersede older state; if the producer emits **deltas** like "add 200 to balance," every single event must be tracked accurately without skipping intermediate versions. Recovery policies depend on event semantics.

## 3. Classify Drift Before Issuing Repairs

| Drift Type | Example | Common Cause | Remediation |
| --- | --- | --- | --- |
| **MISSING** | Source has order O3; Neo4j lacks it. | Lost event, import failure, pending dependency. | Confirm cutoff, replay/upsert order from source. |
| **EXTRA** | Neo4j still has O4 absent from full source snapshot. | Missed delete, mismatched source/target filters. | Confirm deletion policy and snapshot scope before deleting. |
| **STALE** | Source at version 8; Neo4j at version 6. | Consumer lag, DLQ, skipped offset. | Recover/replay by key or fetch latest snapshot state. |
| **VALUE_MISMATCH** | Same version, differing `amountMinor`. | Conversion bug, rounding error, broken mapping. | Quarantine; fix mapper, then resync from authoritative source. |
| **LINK_MISMATCH** | Order has two `DEMO_PLACED` edges or cross-tenant link. | Replay created duplicate edge, incomplete owner-change handling. | Fix transactionally using source keys, re-verify. |
| **DUPLICATE_EVENT** | Same `eventId` received multiple times. | At-least-once delivery, retry after timeout. | Check applied marker; never re-apply side effects. |
| **OUT_OF_ORDER** | Version 10 arrives before version 9. | Partition mixing, parallel workers, retries. | Enforce per-aggregate ordering or version rules. |
| **SCHEMA_DRIFT** | `total_minor` renamed or type changed. | Producer upgraded while consumer is stale. | Pause incompatible event type, align contract. |
| **UNKNOWN_OUTCOME** | Neo4j committed but consumer lost response. | Connection drop right at commit time. | Inspect transaction marker before deciding to replay. |

Never treat every discrepancy as a reason to wipe and reload the entire graph. For instance, Neo4j appearing to have an "extra" order might stem from a source snapshot missing one partition; deleting immediately creates real data loss from a false report.

## 4. Minimal Schema Preparation to Reduce Sync Errors

The statements below should only run in a **learning database or environment where schema changes are authorized**. Labels are isolated for this practice lesson.

~~~cypher
CREATE CONSTRAINT sync_demo_customer_unique IF NOT EXISTS
FOR (c:SyncDemoCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT sync_demo_order_unique IF NOT EXISTS
FOR (o:SyncDemoOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT sync_demo_event_unique IF NOT EXISTS
FOR (e:SyncDemoAppliedEvent)
REQUIRE e.eventId IS UNIQUE;
~~~

These uniqueness constraints prevent **duplicate key tuples when key properties are present**; they do not force all key properties to exist. Ingestion services must still reject events missing `tenantId`, `orderId`, `customerId`, or `eventId`. When both existence and uniqueness are required, evaluate key/existence constraints based on your exact Neo4j version and edition.

A `MERGE` missing the full key—such as `MERGE (o:SyncDemoOrder {orderId: $orderId})` in a multi-tenant setup—can mistakenly merge orders across two tenants. A composite constraint cannot prevent that bug when the consumer itself queries with the wrong key. **Keys inside `MERGE` must match the identity contract.**

## 5. Accurate Reconciliation Requires a Common Cutoff Point

Suppose at time T, the source holds 10,000 orders while Neo4j has caught up only to offset 9,900. Directly comparing counts on an actively written system turns 100 orders of **normal lag** into a false data-loss alarm.

A reliable workflow:

1. Capture a consistent source snapshot while recording its **corresponding watermark/LSN/offset** per source mechanics.
2. Define the exact partitions and key space covered by the snapshot, including how deleted records are represented.
3. Wait for the consumer to apply all changes up to that watermark, or build a Neo4j projection aligned at that same cutoff.
4. Stabilize the comparison scope: if Neo4j keeps receiving mutations **after** the cutoff, read versioned state or isolate the window so newer updates are not flagged as false mismatches.
5. Compare records and relationships by key, store results tagged with `batchId`, and classify drift.

**Note:** "read up to offset N" is insufficient if batches before N still contain errors or uncommitted Neo4j writes. A valid watermark must reflect **contiguous successful processing** per partition/source stream, accounting for events routed to durable error queues. When marking an event "skipped," record both the decision and its impact on completeness.

### 5.1. Multi-Layered Reconciliation

| Check Layer | Cost | Detection Capability |
| --- | --- | --- |
| Record counts by tenant/status/partition | Usually cheaper than full comparison. | Detects net missing/extra counts, but misses offsetting errors. |
| Version/`updatedAt` by key | Moderate. | Detects stale records and version skew; cannot catch wrong payloads if mapper is buggy. |
| Normalized field comparison by key | Higher. | Finds true attribute value discrepancies. |
| Edge and endpoint checks | Depends on connectivity density. | Catches valid nodes with missing, wrong, or extra relationships. |
| Per-partition/canonical checksums | Scales well to large comparisons. | Pinpoints diverging partitions; mismatches still require per-key drill-down. |

Checksums must be computed from **identical fields, identical value normalization, deterministic sorting, and matching cutoffs** on both sides. An unnormalized "catch-all" checksum cannot prove equality; hashes also carry collision probabilities.

## 6. Data Reconciliation Examples with Cypher

This section illustrates **loading a small reference snapshot** into `SyncDemoExpectedOrder` nodes to run reconciliation queries directly inside Neo4j. In production, reference data is typically reconciled **in an external tool** or loaded into a controlled staging area; avoid loading full source snapshots into a production graph solely for ad-hoc checks.

### 6.1. Creating a Fixture with Intentional Drift

On a test database, create one customer and three orders representing Neo4j's state:

~~~cypher
MERGE (c:SyncDemoCustomer {
  tenantId: 'tenant-demo', customerId: 'C1'
})
SET c.name = 'An', c.sourceVersion = 4
MERGE (o1:SyncDemoOrder {
  tenantId: 'tenant-demo', orderId: 'O1'
})
SET o1.customerId = 'C1', o1.amountMinor = 1000,
    o1.status = 'PAID', o1.sourceVersion = 3
MERGE (o2:SyncDemoOrder {
  tenantId: 'tenant-demo', orderId: 'O2'
})
SET o2.customerId = 'C1', o2.amountMinor = 700,
    o2.status = 'PENDING', o2.sourceVersion = 1
MERGE (o4:SyncDemoOrder {
  tenantId: 'tenant-demo', orderId: 'O4'
})
SET o4.customerId = 'C1', o4.amountMinor = 400,
    o4.status = 'PAID', o4.sourceVersion = 1
MERGE (c)-[:DEMO_PLACED]->(o1)
MERGE (c)-[:DEMO_PLACED]->(o2)
MERGE (c)-[:DEMO_PLACED]->(o4);
~~~

For the exercise, treat the consistent source snapshot as containing orders O1, O2, and O3. At the source, O2 has a newer version and amount; O3 has not reached Neo4j yet; O4 is no longer in the snapshot:

~~~cypher
UNWIND [
  {orderId: 'O1', customerId: 'C1', amountMinor: 1000,
   status: 'PAID', sourceVersion: 3},
  {orderId: 'O2', customerId: 'C1', amountMinor: 900,
   status: 'PAID', sourceVersion: 2},
  {orderId: 'O3', customerId: 'C1', amountMinor: 600,
   status: 'PENDING', sourceVersion: 1}
] AS src
MERGE (x:SyncDemoExpectedOrder {
  batchId: 'reconcile-demo-001',
  tenantId: 'tenant-demo',
  orderId: src.orderId
})
SET x.customerId = src.customerId,
    x.amountMinor = src.amountMinor,
    x.status = src.status,
    x.sourceVersion = src.sourceVersion;
~~~

The fixture does not purge pre-existing data that might collide in a shared environment. Use a dedicated learning database and ensure no leftover demo nodes remain from prior runs if you expect the exact illustrated output.

### 6.2. Finding Source Records Missing or Differing at the Target

Suppose the application passes `$batchId = 'reconcile-demo-001'` and `$tenantId = 'tenant-demo'`:

~~~cypher
MATCH (x:SyncDemoExpectedOrder {
  batchId: $batchId, tenantId: $tenantId
})
OPTIONAL MATCH (o:SyncDemoOrder {
  tenantId: x.tenantId, orderId: x.orderId
})
WITH x, o,
     CASE
       WHEN o IS NULL THEN 'MISSING'
       WHEN o.sourceVersion IS NULL
         OR o.sourceVersion <> x.sourceVersion
         OR o.customerId IS NULL
         OR o.customerId <> x.customerId
         OR o.amountMinor IS NULL
         OR o.amountMinor <> x.amountMinor
         OR o.status IS NULL
         OR o.status <> x.status
       THEN 'DIFFERENT'
       ELSE 'OK'
     END AS result
WHERE result <> 'OK'
RETURN x.orderId AS orderId,
       result, x.sourceVersion AS sourceVersion,
       o.sourceVersion AS neo4jVersion,
       x.amountMinor AS sourceAmount,
       o.amountMinor AS neo4jAmount
ORDER BY orderId;
~~~

Expected output: **O2 = DIFFERENT**, **O3 = MISSING**. The query explicitly compares required properties and checks for nulls; when entities have more fields, implement full normalization and comparison aligned with the data contract.

### 6.3. Finding Target Records Absent from the Source Snapshot

~~~cypher
MATCH (o:SyncDemoOrder {tenantId: $tenantId})
WHERE NOT EXISTS {
  MATCH (x:SyncDemoExpectedOrder {
    batchId: $batchId,
    tenantId: o.tenantId,
    orderId: o.orderId
  })
}
RETURN o.orderId AS extraOrderId,
       o.status AS status, o.sourceVersion AS sourceVersion
ORDER BY extraOrderId;
~~~

Expected output: **O4**. Conclude that O4 should be deleted only when the snapshot has **complete coverage** and source rules confirm O4 was genuinely deleted. A snapshot filtered to only "paid orders" cannot justify deleting every order absent from that snapshot.

### 6.4. Detecting Relationship and Endpoint Mismatches

~~~cypher
MATCH (o:SyncDemoOrder {tenantId: $tenantId})
OPTIONAL MATCH (c:SyncDemoCustomer)-[r:DEMO_PLACED]->(o)
WITH o,
     count(r) AS totalLinks,
     sum(
       CASE
         WHEN c IS NULL
           OR c.tenantId <> o.tenantId
           OR c.customerId <> o.customerId
         THEN 1 ELSE 0
       END
     ) AS wrongLinks
WHERE totalLinks <> 1 OR wrongLinks > 0
RETURN o.orderId AS orderId, totalLinks, wrongLinks
ORDER BY orderId;
~~~

In this sample model, each order must have strictly one edge from a customer in the same tenant whose ID matches the order's `customerId`. The query flags orders with missing, extra, or mislinked edges. Neo4j never stores dangling "orphan" relationships without endpoint nodes; typical bugs involve **wrong business endpoints**, not edges pointing to deleted database nodes.

### 6.5. Distinguishing Equal Counts from Accurate Data

~~~cypher
MATCH (o:SyncDemoOrder {tenantId: $tenantId})
RETURN count(o) AS targetOrders,
       count(DISTINCT o.customerId) AS distinctCustomerIds;
~~~

Counts and `DISTINCT` offer quick scale checks, yet cannot prove correctness. In the fixture above, Neo4j holds three orders (O1, O2, O4) and the source snapshot holds three orders (O1, O2, O3); **counts match while hiding two distinct drift errors**. Proving sync accuracy requires comparing keys, contents, versions, and relationships.

## 7. Fix Drift by Root Cause, Not "Blindly"

A divergent record may stem from in-flight sync lag, a buggy producer, a broken mapper, or manual ad-hoc edits in Neo4j. Remediation depends on the root cause:

1. **Scope the incident:** tenant, entity type, partition, offset/version range, and start/end timestamps.
2. **Preserve evidence before fixing:** sample keys/snapshots, diff outputs, ingest logs, event IDs, code versions, and checkpoints.
3. **Isolate broken write paths:** pause affected consumers/partitions if continued writes compound errors; avoid halting the entire platform when one isolated partition is affected.
4. **Verify the authoritative source:** if the source itself is inconsistent, fix it at the source first; avoid "fixing" Neo4j against unverified source state.
5. **Apply targeted repairs:** replay events, re-upsert specific aggregates, rebuild a partition, or add/remove relationships per policy.
6. **Re-read and reconcile:** verify invariants R1–R6 across the repaired scope before unpausing streams and closing the incident.

### 7.1. MISSING and STALE

If the source provides **full-state** events, you can re-ingest the latest version per key guarded by `sourceVersion` so stale data never overwrites newer state. If the source emits only **deltas**, replay the complete ordered event sequence or re-seed from a consistent snapshot and replay deltas after the cutoff.

When creating a relationship to `Customer` whose node is missing, never fabricate a dummy customer with placeholder values just to "keep things moving." Fix dependency ordering, load customers first, or route order events to a bounded waiting queue with alerting.

### 7.2. VALUE_MISMATCH at the Same Version

Diverging values sharing the same `sourceVersion` demand deeper investigation than normal lag. Audit:

- Currency codes, minor-unit scaling, rounding rules, and numeric types.
- Normalization of `null`, empty strings, status codes, and timezones.
- Unicode normalization and key case sensitivity.
- Schema versions and mapper logic between producer and consumer.
- Whether the record was edited manually inside Neo4j.

If the mapper is buggy, replaying the same events with old code merely reproduces the corruption. Fix the mapper, test on sample fixtures, then backfill/replay with verifiable audit trails.

### 7.3. EXTRA and DELETE

CDC may represent deletions via **tombstones** or `DELETE` events. Define an explicit policy:

- **Physical delete:** remove the node/relationship after verifying no other connected data relies on it.
- **Soft delete:** retain the node with `deleted=true` / `deletedAt` so business queries filter it out.
- **Archive:** move historical records to appropriate archive storage instead of keeping them forever in hot query paths.

Never run bulk `DETACH DELETE` on production data merely because records look "extra": it destroys every attached relationship. A **late-arriving** delete event must also never wipe out a newer version; always tie deletion rules to entity versions/sequences.

### 7.4. LINK_MISMATCH

When an order legitimately changes owning customer, running only `MERGE (newCustomer)-[:DEMO_PLACED]->(order)` leaves **the old relationship intact**. Handle both the prior link and the new link **within one transaction**, after verifying the new owner, event version, and transfer permissions. If the domain forbids reassigning order owners, treat the event as a source error instead of silently mutating the graph.

## 8. Idempotent Writes and Checkpoints Aligned to Transaction Boundaries

In replayable broker streams, practical implementations use **at-least-once delivery**. A consumer may receive the same event multiple times; the invariant to protect is that **the same business mutation must never apply twice**.

### 8.1. Writing Event Markers and Graph Updates in One Transaction

Concept:

~~~text
Receive event
   |
   v
Validate schema + keys + version
   |
   v
BEGIN TRANSACTION Neo4j
   |
   +-- CREATE marker for eventId (unique constraint)
   |
   +-- Check dependencies and update nodes/relationships
   |
   +-- COMMIT succeeded for both marker and data
   |
   v
Acknowledge offset to broker
~~~

If the update fails, the marker must roll back as well. If the DB commits and the client disconnects before acking the broker, redelivery hits the existing marker; the consumer must verify the marker matches **the same event/payload** and treat it as a safe replay instead of re-applying graph mutations.

`MERGE (o:SyncDemoOrder {tenantId, orderId})` alone does not guarantee idempotency across all patterns: calling `SET total = total + $delta` twice still adds the delta twice. Conversely, **full-state** events can upsert safely under version guards, though attached relationships and external side effects still require protection.

### 8.2. Java Driver Example for Order Upsert Events

The example below demonstrates an atomic write transaction with the Neo4j Java Driver. Events are assumed to carry **full order state** and be processed **sequentially per aggregate key**. The target customer must already exist; missing dependencies are handled by the orchestration layer.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class OrderSyncWriter {
    public static boolean applyUpsert(Driver driver, Map<String, Object> p) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> {
                // This marker and all updates below share the same transaction.
                tx.run("""
                    CREATE (:SyncDemoAppliedEvent {
                      eventId: $eventId,
                      aggregateKey: $aggregateKey,
                      sourceVersion: $sourceVersion,
                      processedAt: datetime()
                    })
                    """, p).consume();

                long customerCount = tx.run("""
                    MATCH (c:SyncDemoCustomer {
                      tenantId: $tenantId, customerId: $customerId
                    })
                    RETURN count(c) AS n
                    """, p).single().get("n").asLong();

                if (customerCount != 1L) {
                    throw new IllegalStateException(
                        "MISSING_CUSTOMER_DEPENDENCY");
                }

                return tx.run("""
                    MATCH (c:SyncDemoCustomer {
                      tenantId: $tenantId, customerId: $customerId
                    })
                    MERGE (o:SyncDemoOrder {
                      tenantId: $tenantId, orderId: $orderId
                    })
                    ON CREATE SET o.sourceVersion = -1
                    WITH c, o
                    WHERE o.sourceVersion < $sourceVersion
                    SET o.customerId = $customerId,
                        o.amountMinor = $amountMinor,
                        o.status = $status,
                        o.sourceVersion = $sourceVersion,
                        o.syncedAt = datetime()
                    MERGE (c)-[:DEMO_PLACED]->(o)
                    RETURN count(o) AS applied
                    """, p).single().get("applied").asLong() == 1L;
            });
        }
    }
}
~~~

**Preconditions for this example:**

- Constraints from Section 4 exist and `eventId` is globally unique across the stream. `p` supplies `eventId, aggregateKey, tenantId, orderId, customerId, amountMinor, status, sourceVersion` with valid types.
- The consumer uses **a single sequential processing stream per aggregate**, or equivalent locking. Checking `o.sourceVersion < $sourceVersion` alone without concurrency control is insufficient across arbitrary parallel schedules.
- This rule assumes **the order's owning customer never changes**. If `customerId` can change, delete/replace the old relationship inside the same transaction; do not use this pattern unchanged.
- When a late source version is lower than the stored version, the update query returns 0 while the event marker commits as a classified stale event. Delta events require a different policy.
- The uniqueness constraint rejects replayed `eventId`s that already committed. This snippet **does not yet catch the duplicate error branch**; the outer adapter must identify the marker uniqueness error specifically, inspect the marker/payload fingerprint to confirm a genuine replay, and avoid swallowing unrelated database errors.
- `executeWrite` may retry the callback on transient errors. Never invoke external APIs, send emails, or ack brokers **inside the callback**; external side effects do not roll back with the Neo4j transaction.

In production, add payload hashes or source metadata to catch identical `eventId`s carrying altered content, verify endpoint liveness, set timeouts, emit tracing spans, and classify errors. This example highlights the principle of **committing markers and graph mutations together**.

### 8.3. Broker Offsets Are Outside the Neo4j Transaction

There is no automatic ACID transaction spanning Neo4j and a broker simply because an application calls two APIs back to back. Compare both orderings:

| Ordering | Risk |
| --- | --- |
| Ack/commit offset **before** Neo4j commit | Worker dying after ack can lose the event from replay range even though DB never persisted it. |
| Commit Neo4j **first**, ack offset afterward | Worker dying between steps triggers replay; markers and idempotency recognize already-applied events. |

Therefore, under at-least-once delivery, choose **commit Neo4j first, then acknowledge offset**, backed by event markers and replayability. When routing an event to a DLQ/waiting queue, ack the original message only after **durably persisting the reroute decision** so no data is lost; in partitioned brokers, checkpoints must reflect contiguous prior offsets.

Never promise "end-to-end exactly-once" without proving transaction boundaries and idempotency across every participating system.

## 9. Recovering Sync Pipelines After an Incident

An incident usually has three layers of recovery: **services running again**, **every required event processed**, and **Neo4j restored to match the source**. Restarting the consumer satisfies only the first layer.

### 9.1. Sequential Runbook

| Step | Action | Exit Criterion |
| --- | --- | --- |
| 1. Scope | Record failure window, topics/partitions, tenants, code/schema versions, affected event IDs, and offsets. | Evidence-backed blast radius identified. |
| 2. Stop bleeding | Pause failing consumers or partitions; preserve logs, DLQs, and checkpoints. | Corrupt writes halted across affected scope. |
| 3. Protect source data | Verify source still retains snapshots/logs for replay; check retention, backups, and access. | Reliable recovery point secured. |
| 4. Diagnose | Inspect schema, converter, constraint, node dependency, deadlock, timeout, or network errors. | Root cause of repeatable failure identified. |
| 5. Fix and test | Fix code/mappings/configs; test on fixtures and failed sample events. | Writes accurate, idempotent, rollbacks and error classification pass. |
| 6. Choose replay point | Base on **committed** checkpoints, source watermarks, and event markers; not solely tail log offset. | Exact list of partitions/offsets or keys to replay defined. |
| 7. Controlled replay | Execute in per-aggregate order; throttle throughput to protect Neo4j. | Lag shrinking, DLQ and new errors monitored. |
| 8. Re-reconcile | Compare at a common cutoff across nodes, properties, relationships, deletes, and versions. | Drift in incident scope reduced to zero or approved exceptions. |
| 9. Resume normal flow | Unpause partitions gradually, ramp load, and continue monitoring. | Checkpoints advancing steadily with no recurring drift. |
| 10. Postmortem | Document timeline, root cause, impact, and preventive measures. | Recovery verified and follow-up actions tracked. |

If a bug wrote bad data into Neo4j, **never just replay newer events** because stale corrupted fields or edges may linger. Restore clean state from a source snapshot, replay, or execute verified per-aggregate repairs, then reconcile.

### 9.2. Illustrative Recovery Boundary

~~~text
Source:       ... 1040  1041  1042  1043  1044  1045 ...
Consumer:          OK    OK   err    ?     pend  pend
Neo4j marker:      yes   yes   no   check   -     -
Checkpoint:              1041
                             |
                    Restart from valid position
                    after 1041
~~~

When event 1042 fails to commit, never advance the checkpoint to 1044 merely because event 1043 succeeded on a parallel worker. If event 1043 committed without an ack, its replay must be caught by the marker. In Kafka and partitioned systems, tracking the **contiguous completed offset** is paramount.

### 9.3. Choosing Replay vs. Rebuild

| Situation | Strategy |
| --- | --- |
| Brief outage, intact logs, target data prior to outage is valid. | Replay from last confirmed safe point using deduplication/idempotency. |
| Subset of entities corrupted by a new mapper. | Fix mapper, re-upsert or backfill **affected key scope** from authoritative source, then resume CDC. |
| Logs expired past retention, leaving a gap in changes. | Rebuild from a consistent source snapshot and start CDC at the snapshot watermark. |
| Broad target corruption where graph state cannot be trusted. | Rebuild projection in an isolated environment, run backfill + CDC catch-up, reconcile, then switch reads. |
| Source events lost with no usable snapshot available. | Cannot claim full recovery; investigate/restore source data or backups first. |

For **snapshot + CDC**, the CDC start boundary must align with the snapshot watermark to leave zero gaps or missed mutations. Where transition overlap exists, rely on idempotency for safe replays. Verify ordering of deletes and updates around the cutover boundary as well.

## 10. Out-of-Order Data, Retries, and DLQs

### 10.1. Two Event Types Lead to Two Different Policies

**Full-state upsert:**

~~~text
Order O2, version 6: amountMinor = 900
Order O2, version 5: amountMinor = 700 (arrives late)
~~~

If version 6 is already applied, version 5 must never overwrite it. Mark the stale event processed/ignored per policy and preserve version 6 state.

**Delta:**

~~~text
Account A, version 5: +200
Account A, version 6: -50
~~~

If version 6 arrives before version 5 has applied, you cannot skip version 5 and assume the end balance is correct. Process the complete delta sequence in order, or load a consistent snapshot that already incorporates those changes.

### 10.2. Missing Endpoint Nodes

Suppose an Order event arrives before its Customer event:

~~~text
UPSERT Order O3 -> references Customer C1
UPSERT Customer C1 -> arrives later
~~~

Depending on domain rules, choose one of these patterns:

- Route the order event to a durable **dependency-wait queue** with timeouts and alerts; retry once Customer appears.
- Split into two phases: load nodes first, then link relationships using source keys.
- Design producers/brokers to preserve ordering across dependent entities where the source permits.

Creating an "empty customer" placeholder is valid only when explicit completion rules and governance exist; otherwise placeholders mask missing data. Never leave events waiting indefinitely without metrics and intervention thresholds.

### 10.3. DLQ Does Not Mean "Fixed"

A dead-letter queue (DLQ) holds events that remained unprocessable after retry policies exhausted. Record:

- Event ID, partition/offset, aggregate key, and source version.
- Failure reason, error code, retry attempts, and first/last failure timestamps.
- Schema version and source payload location for safe replay.
- Lifecycle state: pending, root cause fixed, replayed, reconciled, or approved exception.

Invalid-data failures (*poison messages*) should halt blind retries so they do not block the stream indefinitely; yet routing to a DLQ must preserve recoverability and must not let checkpoints report "fully synced" while unresolved items remain. Subsequent events for the same aggregate in the DLQ may need to pause per aggregate.

## 11. Failure Testing and Proving Recovery

An integration system must test failure modes, not just happy paths. Use an isolated environment with dedicated source and Neo4j fixtures.

| Test | Fault Injection | Expected Result |
| --- | --- | --- |
| S01 — Duplicate event | Deliver the same `eventId` twice. | Applied once logically; valid marker; replay adds no duplicate edges. |
| S02 — DB write failure | Inject failure after marker but before order update. | Both marker and update roll back; offset not falsely acked. |
| S03 — Lost commit response | Simulate disconnect right after DB may have committed. | Consumer checks marker/classifies outcome; does not apply twice. |
| S04 — Out-of-order | Emit version 6 then version 5 of same order snapshot. | Target keeps version 6; stale event logged. |
| S05 — Missing delta event | Drop a middle version in an increment/decrement chain. | Gap detected; delta stream does not falsely claim completeness. |
| S06 — Missing Customer | Order arrives before Customer node. | No bad edge committed; routed to retry/dependency queue. |
| S07 — Tombstone | Delete order at source. | Target deletes/soft-deletes per policy and version. |
| S08 — Invalid data type | `amountMinor` arrives as string instead of integer. | Rejected/quarantined; never silently writes bad value. |
| S09 — Extended outage | Pause consumer past transient retry window. | Recovers from checkpoint/logs or snapshot; reconciliation passes. |
| S10 — Extra relationship | Inject a bogus `DEMO_PLACED` edge in fixture. | Reconciliation query catches it; repair restores strictly one edge. |
| S11 — Equal count, wrong keys | Keep order count equal by swapping O3 for O4. | Key-based comparison catches MISSING and EXTRA. |
| S12 — Concurrent replay | Multiple workers receive the same aggregate/event. | Constraints and serialization/retry rules preserve valid state. |

### 11.1. Tests with Clear Oracles

Against the Section 6 fixture, a pre-repair reconciliation test must report:

| Record | Finding |
| --- | --- |
| O1 | OK |
| O2 | DIFFERENT — stale version and content |
| O3 | MISSING |
| O4 | EXTRA — flag for deletion only if snapshot is complete |

After recovering from the authoritative source, re-run the same scoped checks. The test passes only when zero drift remains **and** relationship validity passes. Never check only order counts or `sourceVersion`: a buggy mapper can write corrupt payloads even as versions increment.

### 11.2. Replay Performance Testing

Beyond correctness, measure:

| Metric | Purpose |
| --- | --- |
| Consumer lag by partition and age of oldest pending event | Predicts catch-up duration after restarts. |
| Events applied, skipped as stale, duplicates, and DLQ counts | Spots abnormal replays or stalled progress. |
| Neo4j commit time p95/p99 and error rate | Surfaces overload, lock contention, or poor batch sizing. |
| Reconciliation drift counts by type/tenant and drift age | Measures data quality post catch-up. |
| Dependency-waiting event count and max age | Detects stalled entity chains. |
| Remaining log retention margin | Shows whether logs outlast downtime before replay expires. |

Increasing concurrency does not always speed up replays: multiple workers mutating the same aggregate trigger lock contention, deadlocks, or ordering violations. Depending on scale, shard by tenant/aggregate, bound batch sizes, and throttle throughput; monitor both write latency and live read workloads.

## 12. Operating Safely with Batches and Migrations

Neo4j can process imports/batches via Cypher, the Java Driver, or dedicated tools. When a job splits work into multiple smaller transactions, **a failed batch does not roll back previously committed batches**. Therefore:

1. Assign a run ID and track per-partition/chunk status so completed segments are known.
2. Make every chunk safely replayable using canonical keys and source version checks.
3. Avoid giant single transactions exceeding memory or lock limits; equally, never split updates needing atomicity for **one entity** across separate uncompensated transactions.
4. Advance the completion watermark only after all required chunks commit, with failures classified and retained for remediation.
5. Re-reconcile after schema migrations or mapper updates, even when import commands report zero errors.

Statements using `CALL { ... } IN TRANSACTIONS` split work into multiple transactions. If batches 1–5 commit and batch 6 fails, the overall job **is not atomic across all six batches**. Maintain external checkpoints and resume logic, especially for initial loads or post-incident reloads.

Never create new constraints or indexes mid-outage while streams are overloaded without checking schema state and operational plans. Use consistent naming, monitor index online status, and verify version/edition support when adopting new features.

## 13. Security Rules and Change Auditing

Reconciliation often inspects records containing PII or financial transactions. Diff reports should store **keys, drift types, versions, and necessary hashes** instead of copying full sensitive payloads. Restrict access to source snapshots, topics/DLQs, Neo4j write accounts, and repair tools.

Every repair action should produce an audit record capturing:

- Who or which job executed it; reason, incident ticket, and timestamp.
- Mapper version, authoritative source, batch/watermark, and list of affected keys.
- Action taken: replay, re-upsert, tombstone delete, or relationship repair.
- Before/after summaries, processed record counts, remaining errors, and reconciliation proof.

In multi-tenant datasets, every inspection and repair query must constrain `tenantId`. Never "fix" records belonging to another tenant simply because `orderId` matched. Always pass parameters to Cypher via the driver; never build queries by concatenating strings from external events.

## 14. Applied Exercises

**Exercise 1 — Fixture Reconciliation.** Run Section 6 on a learning database, executing both bidirectional comparison queries and the relationship check. Explain why having three orders on both sides does not prove parity. Describe the repair workflow for O2, O3, and O4 assuming a complete source snapshot.

**Exercise 2 — Designing Idempotent Markers.** A consumer receives event 1042 again after Neo4j committed but before the broker received an ack. Describe how to inspect the marker, verify event ID/payload, and decide between acking or investigating. Show why `SET balance = balance + 200` is unsafe on replay without dedicated protection.

**Exercise 3 — Reassigning Order Ownership.** The source emits an event changing `O5`'s `customerId` from C1 to C2. Write a Cypher flow running inside **one transaction** to check version, remove the old ownership edge, and create the new edge. Propose two post-commit assertions confirming neither duplicate edges nor cross-tenant edges exist.

**Exercise 4 — CDC Gap.** A source snapshot is taken at watermark W, yet the CDC consumer starts at W+100. Identify what data may be missing, why a current record count check is insufficient, and how to rebuild the projection/log stream so W+1 through W+99 are not lost.

**Exercise 5 — Incident Runbook.** A consumer stalled for 8 hours, some events landed in the DLQ, and broker log retention is about to expire. Order these steps: isolate failing stream, preserve logs/snapshots, identify trusted checkpoint, fix mapper, replay/catch up, reconcile, and restore traffic. Explain which measurements prove true recovery.

**Exercise 6 — Distinguishing Snapshots and Deltas.** For full-state events arriving in order version 8 then 7, how do you handle them? If events are "+5" and "-3" and one is missing, how does the recovery strategy change?

## 15. Checklist for Completing a Recovery

A sync incident should be declared resolved only when evidence proves:

1. Authoritative source, tenant/entity scope, schema version, and cutoff boundary are defined.
2. Every required offset/event has committed, or resides in a durable error queue with clear ownership and a remediation plan.
3. No duplicate side effects occurred during replay; unknown-outcome failures were reconciled.
4. Nodes, properties, source versions, deletions, and relationships match the business contract.
5. Reconciliation at the cutoff passes (or has documented approved exceptions), not skewed by comparing two different points in time.
6. Lag, DLQ depth, write errors, and processing latency have returned to operational thresholds; consumers continue advancing on live offsets.
7. A root-cause report, test evidence, and preventive follow-ups are documented.

**Core takeaway:** sync recovery does not end when the consumer process restarts. With Neo4j, you must prove **nodes and relationships form a property graph matching the source at a clear cutoff**, and that every write path can replay without duplicating business effects. Checkpoints aligned to transaction boundaries, reconciliation across keys/versions/relationships, and root-cause-driven repairs are the three pillars keeping sync pipelines reliable through incidents.
