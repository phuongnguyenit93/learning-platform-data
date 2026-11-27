# Checklist of Limits to Verify by MongoDB Version and Deployment Environment

## Lesson Objectives

MongoDB enforces several categories of limits: hard BSON format limits, feature availability gated by **server version and Feature Compatibility Version (FCV)**, aggregation memory limits, replica set/sharded cluster topology limits, index/transaction/change stream constraints, and quotas specific to **Atlas or self-managed environments**. Some values are relatively stable constants; many others vary by release, configuration, managed service tier, driver, operating system, and workload.

For instance, saying "MongoDB has a 16 MB limit" is too vague: **16 MiB applies per BSON document**, not to an entire collection or cursor. Saying "aggregation has a 100 MB limit" is also incomplete: that can refer to the memory threshold of certain stages, whereas `$facet` has its own cap and final output still cannot exceed the BSON document limit. Likewise, "Atlas allows at most N connections" cannot be looked up generically under "MongoDB"; you must know the **tier, region, service type, and quota policy at deployment time**.

This lesson belongs to **Database Engine Document MongoDB → Summary and Reference → Checklist of Limits to Verify by Version and Deployment Environment**.

This is a **reference handbook and verification procedure**. Its goal is not memorizing a table of numbers that goes stale, but knowing **what to look up, where to check, on which cluster, when, and with which verification command**.

After completing this lesson, you will be able to:

1. Classify limits into **hard limit**, **configurable limit**, **service quota**, **performance/operational limit**, and **application policy**.
2. Record a precise deployment signature: server build, FCV, topology, Atlas tier, driver, edition, and region.
3. Verify live values on the server using `hello`, `buildInfo`, `getParameter`, `collStats`, `listIndexes`, `serverStatus`, and authorized admin configs.
4. Build a lookup matrix covering limits for BSON, names, nesting, indexing, aggregation, writes, transactions, sessions, cursors, replication, sharding, change streams, TTL, time-series, and GridFS.
5. Distinguish MongoDB engine limits from Atlas Search/Vector Search quotas, managed tiers, and OS limits.
6. Apply verification checklists prior to **upgrades, migrations, production rollouts, load tests, and incident response**.
7. Prioritize the right remediation—shrinking document size, adjusting schema/indexes, paginating, batching, adding capacity, or changing topology—instead of blindly raising an unrelated parameter.
8. Record evidence and verification dates rather than repeating uncontextualized numbers by word of mouth.

> **General rule:** Any limit used to justify an architectural or deployment decision must be recorded alongside **server version + FCV + topology + tier/edition + driver + configuration + documentation source and verification date**. Never record a bare number `N` alone.

---

## 1. Five Categories of Limits to Distinguish

| Category | Meaning | Example |
|---|---|---|
| **Hard format/protocol limit** | Cannot be arbitrarily raised via configuration | 16 MiB max BSON document size |
| **Feature/version limit** | Feature or behavior changes by server/FCV | Availability of an aggregation operator |
| **Configurable resource limit** | Has tuning parameters or options within supported bounds | Connection pool, `maxTimeMS`, certain memory/disk policies |
| **Managed-service quota** | Determined by provider/plan/tier/region | Atlas connections, backup retention, Search nodes |
| **Operational/application limit** | Self-imposed by SLOs, load, resources, or contracts | Batch of 200–500 writes, p99 latency, max event payload |

### 1.1. A Hard Limit Does Not Mean the Whole System Stops There

For example, 16 MiB applies **per document**. A collection can store millions of documents. For large binary files, use GridFS or object storage instead of trying to force a 50 MiB document.

### 1.2. Configurable Does Not Mean Safe to Increase

Sort memory, connection counts, or transaction timeouts may be configurable, yet raising them indiscriminately can trigger node OOM, exhaust file descriptors, or starve competing workloads. Always weigh resource budgets and managed-service constraints.

### 1.3. Quotas Differ From Engine Capabilities

A command supported on self-managed MongoDB Enterprise might be restricted on a lower Atlas tier due to policy, capacity, or feature gates. Conversely, Atlas Search carries separate quotas that cannot be deduced from `mongod` aggregation limits.

### 1.4. Performance Limits Are Not a Single Universal Number

A cluster might handle thousands of ops/sec on small workloads yet fail to sustain that QPS when documents grow, indexes multiply, shards run hot, queries lose selectivity, disks slow down, or write concerns tighten.

### 1.5. Application Policies Should Stay Below Hard Limits

If an entity is expected to grow, set warning alerts well below 16 MiB, cap array element counts, and bound payload sizes. Never design business flows that live right against the ceiling waiting for an error.

---

## 2. The "Environment Signature" to Capture Before Looking Up Limits

Before deciding whether a number applies, record:

| Attribute | Specific Details Needed |
|---|---|
| Server version | Build version and patch level across relevant nodes |
| FCV | Effective Feature Compatibility Version |
| Deployment | Standalone, replica set, or sharded cluster |
| Edition | Community, Enterprise, managed Atlas, or other compatible offering |
| Provider/tier | Atlas shared/Flex/dedicated and actual spec where applicable |
| Region/cloud | AWS/Azure/GCP, region, and network topology |
| Storage | WiredTiger, disk/IOPS, storage quota, filesystem |
| Driver | Java Sync/Reactive, Spring Data MongoDB, Node.js, Python, etc., plus versions |
| Auth/role | Privileges to read server parameters/metrics, direct DB access |
| Workload | Document size, indexes, read/write mix, transaction rate, hot keys |
| Data placement | Shard key, replica members, zones, Search nodes |
| Versioned docs | Release-matched documentation URL and access date |
| Governance | Who approves changes, capacity, backups, and rollback |

### 2.1. Why Record FCV?

Server binaries may have been upgraded while FCV remains pinned to an older version during an upgrade window. Multiple features and behaviors depend on FCV. `db.version()` **does not substitute** for verifying FCV.

### 2.2. Why Record the Driver?

Clients maintain their own connection pools, timeouts, codecs, retry policies, cursor settings, and compatibility matrices. Two apps hitting the exact same server version with different drivers can hit client-side limits first.

### 2.3. Why Record the Tier?

In managed deployments, tier quotas and backup/network/scaling policies evolve over time and across products; never treat self-managed limits as Atlas guarantees.

---

## 3. Commands to Identify the Environment in mongosh

Run only on clusters you are authorized to access; some commands require administrative privileges.

~~~javascript
// Server version of the current connection.
db.version();

// Build metadata (do not log raw sensitive output publicly).
db.adminCommand({ buildInfo: 1 });

// Topology / primary / capabilities of the connected server.
db.adminCommand({ hello: 1 });

// FCV if permissions and deployment allow.
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});

// Replication status on member if permitted.
db.adminCommand({ replSetGetStatus: 1 });
~~~

### 3.1. Key Fields in `hello`

Depending on server and route, the response may include:

- `maxBsonObjectSize`: maximum advertised BSON document size.
- `maxMessageSizeBytes`: network protocol message size limit.
- `maxWriteBatchSize`: maximum write operations per protocol batch.
- `setName`, `hosts`, `isWritablePrimary`: replica set information.
- `msg: "isdbgrid"`: indicates a `mongos` router.
- `logicalSessionTimeoutMinutes` when available.

Never assume "large `maxWriteBatchSize`" means the app can send arbitrarily huge individual payloads; BSON, message size, driver splitting, and memory limits still apply.

### 3.2. Do Not Mistake One mongos for the Whole Cluster

In a sharded cluster, `mongos` returns routing metadata; server versions, parameter settings, and capacities of shards and config servers matter just as much. The Atlas UI/API or cluster inventory may be a better source of truth when shell permissions are restricted.

### 3.3. Permission Denied Does Not Mean Unlimited

On Atlas managed tiers, many `getParameter`, `serverStatus`, and filesystem commands are restricted. When a command is denied, rely on the Atlas UI/API, metrics, release docs, and operator runbooks rather than attempting privilege escalation.

### 3.4. Store Output Safely

Never paste raw `buildInfo`, connection strings, user/host/IP/cluster details, or secrets into public docs. Store required metadata inside an access-controlled internal registry.

---

## 4. Quick Catalog: Which Limits Have Stable Reference Points?

| Group | Common Benchmark | What to Watch When Applying |
|---|---|---|
| BSON document | **16 MiB = 16,777,216 bytes** | Applies per BSON document, not per collection |
| BSON nesting depth | **100 levels** | Deeply nested payloads can fail |
| Aggregation pipeline stages | **1,000 stages** | Pre-/post-parse/optimizer counting rules per docs |
| Many blocking aggregation stages | Typically **100 MB** memory threshold | Not universal for every stage/operation; spill depends on conditions |
| `$facet` document | **100 MB** internal | Facet does not spill; final output must still be ≤ 16 MiB |
| Indexes/collection | Docs note **64 indexes** across many server versions | Check version docs, hidden/wildcard/search indexes |
| Compound index keys | Docs note max **32 indexed fields** in compound index across many versions | Verify index type, version, and key design |
| Default transaction lifetime | Often around **60 seconds** across many server versions | Check `transactionLifetimeLimitSeconds`, Atlas rules, and workload |

**The table above is not a blanket guarantee for every deployment.** Verify the index and transaction benchmarks in **MongoDB Limits**, **Transactions**, and your exact server version's configuration before using them as deployment gates. Other limits are intentionally omitted here because they vary by topology, tier, or driver.

### 4.1. Note on Units

**MiB** = 1,048,576 bytes. **MB** = 1,000,000 bytes in SI usage, though docs and logs sometimes use units contextually. When checking sizes, rely on the server's `bytes` field or state units explicitly; never confuse 16 MiB with 16,000,000 bytes.

### 4.2. Never Apply Legacy Numbers to Newer Servers

Index key size limits, transaction oplog mechanics, aggregation spilling, and naming rules have changed across MongoDB major releases. Never rely on a 5-year-old blog post or slide deck to clear an upgrade.

---

## 5. BSON: Document, Field, and Nesting Limits

### 5.1. Document ≤ 16 MiB

Example of an order document storing all audit events:

~~~javascript
{
  _id: "ORD-101",
  status: "PAID",
  audit_events: [
    // Grows endlessly over many years.
  ]
}
~~~

A single `$push` can push the resulting document past 16 MiB even after years of succeeding writes.

### 5.2. There Is No Universal "Max Elements" Across Arrays

Array footprint depends on element size, field/key names, nested objects, and surrounding fields. An array of 100,000 small integers can weigh less than 1,000 objects holding long strings.

### 5.3. Inspect BSON Bytes With `$bsonSize`

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      bson_bytes: {
        $bsonSize: "$$ROOT"
      }
    }
  },
  { $sort: { bson_bytes: -1 } },
  { $limit: 20 }
], {
  allowDiskUse: true
});
~~~

Computing size reads the full document, making this an expensive scan on large collections. Scope by tenant/cohort, sample, or run off-peak.

### 5.4. Safely Count Array Elements

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      audit_count: {
        $cond: [
          { $isArray: "$audit_events" },
          { $size: "$audit_events" },
          0
        ]
      },
      bson_bytes: { $bsonSize: "$$ROOT" }
    }
  },
  { $sort: { audit_count: -1 } },
  { $limit: 20 }
]);
~~~

`$size` requires an array. Use `$isArray` or schema validation if fields may be missing, `null`, or mistyped.

### 5.5. Collections Larger Than 16 MiB Are Normal

A collection holds many BSON documents queried via cursors. **16 MiB restricts each individual document**, not the sum of documents streamed across cursor batches.

### 5.6. Large Binaries and Files

Files exceeding 16 MiB belong in **GridFS** or object storage depending on query and retention needs—never base64-encode them into a single document. GridFS splits files into chunk documents and metadata; it does not raise the single-BSON-document limit.

### 5.7. Related Limits to Verify

- Field name length and character restrictions (`$`, `.`) by server/driver/version.
- Maximum document nesting depth.
- BSON type/value sizes, UTF-8 encoding, and BSON numeric types.
- Post-`update` document size, not just pre-update input size.
- Schema validation and limits on indexed paths over nested arrays.

**Never estimate BSON size from `JSON.stringify().length`**, since JSON text and binary BSON differ in encoding and overhead.

---

## 6. Namespaces, Collections, Field Names, and Identifiers

### 6.1. Items to Verify by Version and Topology

- Maximum namespace length including database and collection name.
- Collection/system naming restrictions and `$` or `.` rules.
- Index name / namespace length limits under sharding.
- Database/collection naming constraints on Windows vs Linux.
- Case sensitivity and filesystem/tooling restrictions.
- BSON document nesting depth limits.

### 6.2. Why Avoid Naming Near the Ceiling?

Very long collection names can interact poorly with internal namespaces, index tooling, and older version compatibility. Adopt short, stable naming conventions with wide headroom.

### 6.3. Do Not Confuse Java Property Names With BSON Field Names

Spring Data `@Field("tenant_id")` maps a `tenantId` property to a different stored key. Limits and restrictions apply to the **actual BSON path**, not merely the Java field name.

### 6.4. Unicode and Collation

Never assume "two visually similar names are treated identically by a unique index." Collation and Unicode normalization govern equality, sorting, and uniqueness; define them explicitly.

---

## 7. Indexes: Counts, Field Counts, and Key Sizes

MongoDB enforces index limits that vary by server version and index type.

### 7.1. Items to Verify

1. Maximum number of indexes per collection.
2. Maximum number of fields in a compound index.
3. Index key/entry size limits if enforced by your target version.
4. Multikey restrictions, especially compound indexes spanning multiple array paths.
5. Unique index semantics for missing/`null` fields and collation.
6. Partial index filter expression capabilities.
7. Wildcard index restrictions.
8. Text, geo, hashed, TTL, and clustered index rules.
9. Hidden indexes, index build concurrency, and resource budgets.
10. Sharded unique index restrictions tied to shard key and topology.

### 7.2. Inspect Existing Indexes

~~~javascript
db.orders.getIndexes();
~~~

Count them:

~~~javascript
db.orders.getIndexes().length;
~~~

The output includes the `_id` index. When counting toward index quotas by type/version, consult docs rather than mixing Atlas Search indexes into B-tree index counts.

### 7.3. More Indexes Are Not Always Better

Every insert, update, or delete must maintain affected index entries. On hot inventory counters or volatile arrays, excessive indexes trigger write amplification and bloat storage.

### 7.4. Compound Multikey Indexes Across Multiple Arrays

A single document having two indexed arrays inside one compound multikey index hits restrictions (parallel arrays). Never assume "just index both arrays to speed up the query." Verify restrictions and adjust schema or queries if needed.

### 7.5. Index Size and Performance Differ From Index Count Limits

Being allowed to create an index does not prove RAM, disk, or IOPS will handle it. Check `db.collection.stats()`, `executionStats`, index sizes, benchmarks, and capacity models.

### 7.6. Index Key Limits Changed Across MongoDB Releases

Historical limits on index key lengths have evolved across major versions. Never copy a 1024-byte rule from legacy documentation onto modern servers; check versioned documentation.

---

## 8. Unique Indexes, Null/Missing Values, and Migrations

### 8.1. Single-Field Unique Index

If multiple documents omit the field or store `null`, creating a unique index may fail depending on shape and rules. Count existing duplicates and verify exact business requirements before migrating.

### 8.2. Partial Unique Index

When enforcing uniqueness only on normalized documents:

~~~javascript
db.customers.createIndex(
  {
    tenant_id: 1,
    normalized_email: 1
  },
  {
    unique: true,
    partialFilterExpression: {
      normalized_email: { $type: "string" }
    },
    name: "uq_tenant_normalized_email"
  }
);
~~~

Documents outside the partial filter **are not** constrained by this index; never mistake it for universal uniqueness.

### 8.3. Collation

Unique equality depends on collation. If emails or usernames require case-insensitive uniqueness, implement explicit normalization or matching collation instead of relying on a plain binary unique index.

### 8.4. Sharded Uniqueness

On sharded collections, unique indexes/constraints must follow supported combinations of shard key and server version. Never promise global uniqueness if an index fails sharding rules.

### 8.5. Migration Gate

Before creating or dropping a unique index, inspect existing duplicates, null/missing fields, active write paths, backups, mixed-version rollouts, and rollback steps.

---

## 9. Aggregation: 16 MiB Output vs 100 MB Memory

A pipeline can fail because:

- A resulting BSON document exceeds 16 MiB.
- A blocking stage exceeds memory and cannot or is not allowed to spill.
- A `$group` accumulator such as `$push` accumulates too many entries.
- A `$facet` output exceeds its dedicated cap.
- The pipeline exceeds 1,000 stages.
- CPU/disk/network exhaustion or timeout occurs before hitting a hard limit.

### 9.1. Using a Cursor Does Not Permit Building One Giant Document

A query returning 1 million small documents via a cursor is fine. Yet `$group: {items: {$push: "$$ROOT"}}` packs them into **one** result document that easily breaches the BSON limit.

### 9.2. `$lookup` Fan-Out

One parent joining 500,000 child documents creates a massive array. Use a foreign pipeline with `$match`, `$sort`, `$limit`, and `$project` when only top-N is needed—or paginate children directly.

### 9.3. `$unwind` Multiplies Cardinality

Each array element spawns a pipeline row. Followed by `$lookup` and `$group`, row counts and memory state explode rapidly. Measure cardinality at every stage.

### 9.4. `$facet`

`$facet` returns a single document containing arrays for each sub-pipeline, carries an internal cap around 100 MB, and **does not spill to disk**. Final output remains subject to the 16 MiB BSON limit. `allowDiskUse:true` does not turn `$facet` into an unlimited history container.

### 9.5. Stage Count

A dynamically generated pipeline exceeding 1,000 `$addFields`/`$project` stages can fail even if every stage is trivial. Consolidate expressions, use `$map`/`$reduce` cleanly, or bound pipeline generation.

---

## 10. Aggregation Memory Limits and `allowDiskUse`

### 10.1. Stages Commonly Facing Memory Pressure

- `$sort` (blocking).
- `$group`.
- `$bucket`/`$bucketAuto`.
- `$sortByCount`.
- `$setWindowFields`.
- Certain `$lookup` and accumulator patterns.

Some stages can spill to disk when server conditions allow. Do not assume every stage or every accumulator spills cleanly.

### 10.2. Server Versions and Defaults

Since MongoDB 6.0, `allowDiskUseByDefault` governs whether eligible stages use disk by default. Command-level `allowDiskUse` overrides per supported semantics. Newer MongoDB releases may introduce **per-operation** memory limits; inspect release notes.

### 10.3. Example

~~~javascript
db.sales.aggregate([
  {
    $match: {
      tenant_id: "tenant-a",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customer_id",
      total_minor: { $sum: "$amount_minor" },
      count: { $sum: 1 }
    }
  },
  { $sort: { total_minor: -1 } },
  { $limit: 100 }
], {
  allowDiskUse: true,
  maxTimeMS: 30000
});
~~~

### 10.4. When Does `allowDiskUse` Not Help?

- BSON output > 16 MiB.
- `$facet` internal cap.
- Overgrown non-spillable accumulator arrays.
- Pipeline > 1,000 stages.
- Client OOM from collecting an entire cursor into a `List`.
- Unbounded join fan-out.
- Insufficient disk I/O hardware capacity.

### 10.5. Spilling Has a Cost

Spilling increases temp disk I/O, latency, and resource contention. Monitor profiler/logs for `usedDisk` where supported; prefer fixing query plans, indexes, and limits over blindly enabling spill.

### 10.6. Do Not Tweak Internal Parameters Recklessly

Raising memory limits lets one concurrent query exhaust node RAM. Managed Atlas tiers often disallow changing them. Record approvals, benchmarks, and rollback plans before modifying supported parameters.

---

## 11. `$sort`: Indexes, Limits, and Memory

### 11.1. Unbounded Query

~~~javascript
db.events.aggregate([
  { $sort: { created_at: -1 } }
], {
  allowDiskUse: false
});
~~~

On large datasets without a supporting sort index, this risks hitting a memory error.

### 11.2. Scoped Top-K Query

~~~javascript
db.events.createIndex({
  tenant_id: 1,
  created_at: -1,
  _id: -1
});

db.events.aggregate([
  { $match: { tenant_id: "tenant-a" } },
  { $sort: { created_at: -1, _id: -1 } },
  { $limit: 50 },
  { $project: { _id: 1, type: 1, created_at: 1 } }
]);
~~~

`$sort` followed by `$limit` differs semantically from `$limit` followed by `$sort`. Never reorder `$limit` recklessly at the expense of business correctness.

### 11.3. Explain

~~~javascript
db.events.explain("executionStats").aggregate([
  { $match: { tenant_id: "tenant-a" } },
  { $sort: { created_at: -1, _id: -1 } },
  { $limit: 50 }
]);
~~~

Verify `IXSCAN` and sort behavior from the actual plan. Having an index does not guarantee the query uses it.

---

## 12. `$group` and Accumulator Memory

### 12.1. Dangerous Pipeline

~~~javascript
db.order_events.aggregate([
  {
    $group: {
      _id: "$order_id",
      events: { $push: "$$ROOT" }
    }
  }
], {
  allowDiskUse: true
});
~~~

An order with many events can push the `events` array past accumulator memory or the 16 MiB output cap. Group-state disk spill does not make a single accumulator unbounded.

### 12.2. When Only Totals Are Needed

~~~javascript
db.order_events.aggregate([
  {
    $group: {
      _id: "$order_id",
      event_count: { $sum: 1 }
    }
  }
]);
~~~

### 12.3. When Event History Is Needed

Stream events with cursors and pagination by `order_id` instead of stuffing everything into a single result document.

### 12.4. When Top-N per Group Is Needed

Check version support for top-N accumulators or suitable window functions/queries; still bound `N` and test memory usage. Do not assume top-N bypasses all limits.

---

## 13. Write Batches, Network Protocol, and Driver Splitting

### 13.1. Three Distinct Limits

- `maxBsonObjectSize`: per-document.
- `maxMessageSizeBytes`: protocol message size.
- `maxWriteBatchSize`: max write operations per batch per server capability.

Inspect live values:

~~~javascript
const hello = db.adminCommand({ hello: 1 });

printjson({
  maxBsonObjectSize: hello.maxBsonObjectSize,
  maxMessageSizeBytes: hello.maxMessageSizeBytes,
  maxWriteBatchSize: hello.maxWriteBatchSize
});
~~~

### 13.2. Driver Batch Splitting Still Leaves Application Limits

The Java Driver splits bulk writes to honor server limits. Yet the application should not accumulate 10 million write models on the JVM heap before calling `execute`. Chunk inputs into bounded batches, checkpoint progress, and throttle throughput.

### 13.3. Ordered vs Unordered

`ORDERED` stops on error per semantics; `UNORDERED` continues independent operations. **Neither is an all-or-nothing transaction.**

### 13.4. Do Not Size Batches Solely by Protocol Max

A 100,000-operation batch might fit a protocol cap yet overwhelm SLOs, heap, retry reconciliation, or MongoDB transaction budgets. Size batches from real benchmarks and environment quotas.

### 13.5. Unknown Write Outcomes

A network timeout does not prove a write failed. For `$inc`/`$push`, application-level retries without stable idempotency keys can repeat the effect; use unique operation IDs or ledgers.

---

## 14. Cursors, `batchSize`, Pagination, and Client Memory

### 14.1. Cursors Return Many Documents; Each Obeys 16 MiB

`batchSize` controls batch counts/sizes per driver/server rules without allowing a 20 MiB BSON document. `limit` bounds total returned documents without capping server memory by itself.

### 14.2. Never Collect Unboundedly Into JVM Memory

~~~java
// Dangerous on large collections:
List<Document> all =
    collection.find().into(new ArrayList<>());
~~~

Iterate cursors in batches and stream-process:

~~~java
try (MongoCursor<Document> cursor =
         collection.find()
             .batchSize(200)
             .iterator()) {

    while (cursor.hasNext()) {
        Document doc = cursor.next();
        processOne(doc);
    }
}
~~~

Java snippet for illustration; `processOne` is an application function. Client memory, GC pauses, max heap, timeouts, and downstream backpressure are limits outside MongoDB Server.

### 14.3. Keyset Pagination

On huge collections, `skip(1000000)` is costly. Use a stable sort key and cursor token—such as `created_at DESC, _id DESC` backed by an index—passing the last tuple alongside tenant and filter scope.

### 14.4. Cursor Lifetime

`noCursorTimeout`, logical session timeouts, and server resource policies all apply. Never assume a cursor left open for hours stays alive. Close cursors promptly and checkpoint progress for safe restarts.

### 14.5. Change Streams Are Also Cursor-Like Streams

`batchSize`, `maxAwaitTimeMS`, and resume tokens do not remove requirements for backpressure, oplog retention, and durable checkpoints.

---

## 15. Transactions: Support Conditions and Practical Limits

Multi-document transactions must be evaluated against:

1. Replica set vs sharded cluster.
2. Server version and FCV.
3. Driver version and session support.
4. Default/custom `transactionLifetimeLimitSeconds`.
5. Write concern, read concern, and retryable transaction errors.
6. Total read/write set size and participating documents/collections.
7. Lock contention and WiredTiger cache pressure.
8. Transaction oplog representation in your server version.
9. Cross-shard coordination cost.
10. Managed-tier restrictions and timeouts.

### 15.1. Default Lifetime Is Not an Unlimited Budget

Many MongoDB releases default transaction lifetime to roughly **60 seconds**; verify configured values and environment restrictions. Keep transactions brief—never hold them open waiting on payment providers or email servers.

### 15.2. Inspect the Parameter When Authorized

~~~javascript
db.adminCommand({
  getParameter: 1,
  transactionLifetimeLimitSeconds: 1
});
~~~

If an Atlas tier restricts reading or tuning this parameter, consult UI/API/support docs and confirm with the platform owner.

### 15.3. Never Say "Transactions Have a 16 MiB Total Cap"

MongoDB changed how transaction oplog entries are recorded across versions. Never apply a legacy total-transaction-size cap to modern servers. **Each persisted BSON document** still obeys its hard limit, while transactions face other resource constraints.

### 15.4. Unknown Commit Results

A commit can succeed while the client loses the ACK. Retry commit or reconcile via stable business ID. Never charge a payment or send messages directly inside a retryable transaction callback.

### 15.5. Transactions Are Not Atomic With External Systems

A MongoDB transaction never encompasses Kafka, email, payment gateways, or external HTTP APIs. Use transactional outbox, idempotent consumers, and sagas/compensation per business logic.

---

## 16. Sessions, Retryable Writes, and Connection Pools

### 16.1. Sessions

Logical sessions carry lifetimes and cleanup rules; never cache a `ClientSession` indefinitely or share one concurrently outside driver contract. Check `logicalSessionTimeoutMinutes` returned by `hello`.

### 16.2. Retryable Writes

Require compatible topology, version, driver support, retry policies, and wire protocol. An HTTP replay does not reuse the same DB operation identity; business-level idempotency remains mandatory.

### 16.3. Connection Pools Are Both Client and Server Limits

The Java Driver exposes `maxSize`, `minSize`, `maxConnecting`, `maxWaitTime`, and socket/connect/server selection timeouts. Exact names and defaults depend on driver version.

### 16.4. Server Connections and Atlas Quotas

Servers enforce limits via configuration, OS file descriptors, and managed tiers; Atlas quotas may sit well below theoretical hardware capacity. Never size connections by "number of users"; calculate `app instances × pool max × reachable server nodes` plus monitoring and background jobs.

### 16.5. Pool Exhaustion Symptoms

Threads waiting on connections, `MongoWaitQueueTimeoutException` or similar timeouts, and rising p99. Raising pool size when the server is already socket-starved can worsen an outage.

### 16.6. Verify

Cross-check driver config, `db.serverStatus().connections` (when permitted), Atlas connection metrics, OS file descriptors, `ulimit`/Windows limits, and process counts. Never guess a universal connection ceiling.

---

## 17. Replica Sets: Topology and Replication Limits

Verify per server release:

- Maximum replica set members.
- Supported voting members and election rules.
- Oplog size and retention window.
- Read/write concern defaults.
- Majority availability and failover behavior.
- Member priority and hidden/delayed/arbiter restrictions.
- Sync sources and network bandwidth.
- Logical session support.
- Transaction and change stream support.
- Rolling upgrade compatibility across members.

### 17.1. Members and Voters Are Not the Same Number

Across many MongoDB versions, total replica set members differ from maximum voting members; never treat max members as max voters. When designing large replica sets, consult versioned [Replica Set Limits](https://www.mongodb.com/docs/manual/reference/limits/#replica-set-limits).

### 17.2. Oplog Is a Finite Resource

Change stream resumption and replication depend on retained oplog history. Oplog size, write volume, minimum retention policy, and disk space govern actual window length—there is no universal "7-day resume guarantee."

### 17.3. Lag Is an Operational Limit

Secondary lag causes stale reads and impacts failover/RPO, backups, and change streams. Monitor lag, optime, and member health—not just primary CPU.

### 17.4. Failover Is Not Arbitrarily Instant

Election timeouts, topology/network conditions, and driver server selection timeouts govern latency during primary changes. Test stepdowns on staging; never promise zero downtime for arbitrary setups.

---

## 18. Sharded Clusters: Shard Keys, Chunks, and Quotas

Items to verify:

- Server/FCV across `mongos`, config servers, and shards.
- Shard key restrictions and hashed vs ranged keys.
- Unique indexes on sharded collections.
- Chunk size and balancer behavior per version.
- Jumbo chunks, hot shards, and zone sharding.
- Max shards/namespaces per release and managed tier.
- Cross-shard transactions and aggregations.
- Chunk migrations, disk/I/O pressure, and backup consistency.
- Shard key updates / resharding support.
- Query targeting vs scatter-gather.
- Atlas auto-scaling and shard-scaling limits.

### 18.1. Sharding Does Not Raise the 16 MiB Document Limit

A 20 MiB document remains invalid even across 100 shards. Split oversized documents into referenced documents or buckets.

### 18.2. A Hot Key Remains a Hotspot

If every request decrements stock for `SKU-01` in one document, sharding cannot split that single atomic counter into independent counters.

### 18.3. Shard Keys and Transactions

Designing `tenant+key` helps target queries and curb scatter-gather, yet still verify actual shard keys, unique index rules, and read/write workloads.

### 18.4. Chunk Size Is Not Document Size

A chunk is a logical partitioning/migration unit between shards, not a BSON document. Never infer from chunk size that a document can grow as large as a chunk.

---

## 19. Change Streams: Retention, Pre-Images, and Resume

### 19.1. Deployment Support

Change Streams run on replica sets and sharded clusters with compatible server versions. Standalone instances are not a standard deployment for change streams. Verify driver APIs and privileges.

### 19.2. No "Forever-Valid Resume Token"

A resume token is an opaque marker. Once oplog history covering that position expires, the consumer fails to resume and requires re-bootstrapping or reconciliation.

### 19.3. Event Size

Change events grow significantly with `fullDocument` update lookups and especially pre-/post-images. Event payloads, pipeline transformations, and downstream message transports all carry limits. Never assume full-document change events stay small just because an update touched one field.

### 19.4. Pre/Post Images

Storage, lifecycle, and retention follow server version and collection configuration. Pre-/post-images are not infinite backups; verify retention and storage quotas.

### 19.5. Backpressure

`batchSize` and `maxAwaitTimeMS` alter polling/batching behavior, not oplog retention. When arrival rate exceeds processing rate, lag grows; adding consumer concurrency must preserve ordering and checkpoint correctness.

### 19.6. Checkpoints and Idempotency

Persist resume tokens durably only after correct processing; consumers can receive duplicates after crashes. Use stable event IDs/versions and idempotent side effects.

### 19.7. Monitoring

Track oplog time window, consumer lag, resume failures, pre-image storage, throughput, and error rates. If history is lost, never restart from "now" and claim zero events were missed.

---

## 20. TTL Indexes and Non-Exact Second-Level Expiration

### 20.1. TTL Has Specific Rules and Limits

Verify:

- The indexed field holds valid date/time BSON types.
- `expireAfterSeconds` semantics.
- Version rules across single-field, compound, partial, and time-series indexes.
- TTL monitor cadence and deletion lag.
- Impact on writes, replication, and CPU.
- Managed backup and retention interactions.

### 20.2. TTL Does Not Perform Business Compensation

Expiring an `ACTIVE` reservation via TTL does not restore inventory counts. An expiration worker must perform state transitions and conditional inventory adjustments before cleanup.

### 20.3. TTL Is Not an Exact Scheduling SLA

TTL deletion runs in the background; documents can linger past expiration. Never treat document absence as proof a scheduled job ran on time.

### 20.4. Retention vs Idempotency

If TTL deletes a processed-event marker before a delayed queue replays, duplicates occur. Size TTL windows beyond replay windows and audit/legal retention obligations.

### 20.5. Never Confuse TTL With Backups

Data purged by TTL is not automatically recoverable to arbitrary retention targets. RPO/RTO depend on separate backup policies.

---

## 21. Time-Series Collections: Limits Distinct From Regular Collections

Time-series collections use bucketing mechanics and carry release-specific restrictions.

Checklist:

1. Server version/FCV support for used features.
2. `timeField` and optional `metaField` shape.
3. `granularity` and bucket span/rounding rules.
4. Retention and TTL behavior.
5. Allowed updates and deletes.
6. Supported indexes and secondary indexes.
7. Sharding support and restrictions.
8. Bucketing behavior and bucket size limits.
9. Query optimization using metadata and time bounds.
10. Downsampling, late-arriving measurements, and backfills.

### 21.1. Do Not Treat Time-Series as Arbitrary Mutable Document Collections

Update, delete, transaction, and sharding behaviors differ from standard collections and evolve across releases. Read versioned time-series docs before using them for inventory or reservation state.

### 21.2. Oversized Measurements

BSON document limits still apply; time-series bucketing does not legitimize giant measurement payloads. Model small, time-bounded measurements with clean metadata.

### 21.3. Bucket Size Differs From TTL Retention

Bucket span is storage layout; retention is lifecycle. Never pick granularity solely for a 30-day deletion rule without evaluating query patterns and workload.

---

## 22. GridFS: File Limits Beyond BSON Documents

GridFS splits files into file metadata and chunks. It fits file-like binaries larger than 16 MiB stored inside MongoDB; it is not a cure-all for unbounded arrays.

### 22.1. Items to Check

- Driver/GridFS API and version.
- Chunk size and collection indexes.
- Storage, backup, and restore quotas.
- File metadata and tenant ACLs.
- Incomplete uploads and cleanup.
- Retention and lifecycle.
- Byte-range read and streaming performance.
- Atlas tier disk/storage limits.

### 22.2. When Should GridFS Be Avoided?

If data consists of millions of events requiring filtering, sorting, and deduplicating by `event_id`, a dedicated indexed events collection beats stuffing giant JSON blobs into files.

### 22.3. External Object Storage

S3/GCS/Azure Blob can hold files while MongoDB stores metadata pointers. Manage consistency, retention, and ACLs across both systems—never assume MongoDB transactions cover external object storage atomically.

---

## 23. Atlas: Look Up Quotas by Product and Tier

MongoDB Atlas offers multiple deployment classes, each with distinct availability, performance, backup/network, and feature constraints.

### 23.1. Never Hardcode a Tier's Limit Forever

Quotas shift as Atlas evolves products and plan names. Legacy notes on M0/M2/M5 may not reflect Flex/dedicated tiers or current releases. Record the **current tier name from the Atlas UI/API**.

### 23.2. Mandatory Check Areas

| Area | Questions to Answer |
|---|---|
| Storage | Max allocated storage? Auto-scaling? Disk IOPS/throughput? |
| Connections | Max concurrent connections per tier and spike tolerance? |
| Compute | CPU/RAM, instance class, Search nodes? |
| Backup | Snapshot frequency, retention, PITR, restore RPO/RTO? |
| Networking | Private endpoints/peering, IP allowlists, egress policies? |
| Features | Transactions, sharding, Search, Vector Search, encryption, time-series? |
| Operations | Index build/resource limits, maintenance/upgrade windows? |
| Quotas | Cluster/project counts, API rate limits, alerts? |
| Region/cloud | Supported regions, availability zones, instance size availability? |
| Scaling | Min/max tier, auto-scaling guardrails, storage scaling policies? |
| Security | Auditing, advanced auth, encryption tiers? |
| Support | Support SLA and escalation path? |

### 23.3. Atlas Search / Vector Search Differ From `mongod` Aggregation

Search index quotas, analyzers, vector dimension ceilings, query syntax, field mappings, Search nodes, index sizes, and concurrent query limits have separate documentation. Never infer Search index capacity from MongoDB B-tree index limits.

### 23.4. Atlas Serverless / Managed Feature Names Change

Consult current [Atlas documentation](https://www.mongodb.com/docs/atlas/) matching your exact cluster type and plan rather than copying limit tables from undated blog posts.

### 23.5. Your Account May Not View Every Parameter

Rely on Atlas metrics/UI/API and your platform team. Never attempt to bypass permissions to inspect restricted server internals.

---

## 24. Self-Managed: OS and Hardware Limits

MongoDB Server supporting a feature does not mean the host has the capacity.

### 24.1. Linux / Windows

Inspect file descriptors/handles, max processes/threads, memory limits, disk space, filesystem, DNS, network sockets, TCP tuning, service supervisors, and cgroup/container limits.

### 24.2. Containers / Kubernetes

- CPU limits and throttling.
- Memory limits and OOMKills.
- Ephemeral storage.
- Persistent volume IOPS, throughput, and capacity.
- Pod eviction and node failures.
- Resource requests/limits.
- Liveness/readiness probes and rolling upgrades.
- Multi-availability-zone networking.

### 24.3. WiredTiger Cache

WiredTiger uses its internal cache plus memory outside the cache. Defaults and tuning vary by build and environment; never equate "MongoDB RAM = cache size" while ignoring OS page cache, connections, aggregations, and concurrent queries.

### 24.4. Disk Capacity

Size disks for more than raw data: include indexes, journal, oplog, temporary aggregation/index-build space, snapshots, and headroom. Storage compression separates `logical data size` from `allocated disk usage`.

### 24.5. Virtualization / Cloud

IOPS, disk throughput, network bandwidth, and burst credits often bottleneck before CPU. MongoDB limit tables never replace benchmarking on real hosts.

---

## 25. Backups, Restores, and Data Retention

Verify:

- Backup/PITR availability by tier.
- Snapshot frequency and retention.
- Target RPO/RTO.
- Backup consistency across replica sets and sharded clusters.
- Disk and network throughput for restores.
- Encryption key management.
- Cross-version restore compatibility.
- Backups of Search indexes or derived projections.
- TTL deletions and legal holds.
- Restore rehearsals and application compatibility with older schemas.

### 25.1. Backups Do Not Replace Idempotency

Restoring recovers state prior to an incident while losing valid writes made afterward. Recovery plans must include replay and reconciliation from sources of truth or outboxes.

### 25.2. Version Compatibility

Never assume a backup snapshot from a newer server version restores directly onto a much older binary. Verify supported upgrade/downgrade paths and FCV.

### 25.3. Restore Duration Is a Real Limit

A huge cluster with snapshots that take many hours to restore may still violate RTO. Test restores using realistic data sizes and network speeds.

---

## 26. Security and Encryption Carry Separate Limits

### 26.1. TLS / Authentication

Verify driver support, TLS versions, certificate chains, auth mechanisms, identity provider/session settings, and Atlas security policies. Never weaken security solely to "restore connectivity" after an upgrade.

### 26.2. Client-Side Field Level Encryption

CSFLE and Queryable Encryption impose rules on supported BSON types, operators, encrypted indexes, driver versions, key management, and payload expansion. Never assume encrypted fields support `$regex`, `$sort`, or `$lookup` identically to plaintext.

### 26.3. Encrypted Data Expansion

Encryption metadata increases BSON size. A plaintext document near 16 MiB can breach the limit once encrypted. Leave headroom and test with realistic payloads.

### 26.4. Search and Encryption

Search over encrypted fields has dedicated constraints and modes; never assume Atlas Search indexes every client-side encrypted field.

### 26.5. Key Lifecycle

Key rotation, KMS availability, and restores are operational constraints. An encrypted backup without its corresponding keys cannot be restored completely.

---

## 27. Driver, Spring Data, and API Compatibility

### 27.1. MongoDB Java Sync Driver

Check compatibility matrices across driver version, MongoDB Server versions, Java runtime versions, retryable writes, transactions, wire compression, authentication mechanisms, and codec behavior.

### 27.2. Spring Data MongoDB

Spring Data / BOM / Boot versions govern mapping APIs, `MongoTemplate`, `BulkOperations`, session/transaction integration, reactive support, and feature flags. Never drop recent code snippets onto older dependencies without checking.

### 27.3. Never Mix Blocking and Reactive Without Measuring

Reactive drivers have different connection and backpressure mechanics than synchronous drivers. Server quotas stay identical while client concurrency and memory footprints change.

### 27.4. Driver Sockets and Timeouts

Check:

- `serverSelectionTimeout`.
- `connectTimeout`.
- `socketTimeout` or read timeout.
- `maxPoolSize`, `minPoolSize`.
- `maxConnecting`, `maxWaitTime`.
- `retryReads`/`retryWrites`.
- Heartbeat and topology discovery intervals.

Defaults vary across driver versions. Record effective runtime configuration rather than inferring from sample snippets.

### 27.5. Client-Side BSON Codecs

Clients may fail to serialize oversized or unsupported objects, or hit JVM heap OOM before reaching the server. Distinguish client-side driver errors from server limits.

---

## 28. Reading `stats` Accurately

~~~javascript
db.orders.stats();
~~~

Typically reports `count`, `size`, `avgObjSize`, `storageSize`, and index sizes depending on version, engine, and topology.

### 28.1. `avgObjSize` Hides the Tail

A collection averaging 3 KiB per document can still harbor several 15 MiB outliers. Measure top-N and p95/p99 with `$bsonSize` or telemetry.

### 28.2. Logical Size Differs From Disk Size

`size` and `storageSize` diverge due to compression, fragmentation, and pre-allocation. Never calculate max document size from `storageSize / count`.

### 28.3. Index Stats

`$indexStats` and server metrics reveal index usage, yet "0 usage in 24 hours" does not justify dropping an index built for a weekly batch job. Cross-reference your workload inventory.

### 28.4. Sharded Collections

Stats may aggregate or break down per shard without guaranteeing balanced traffic. Inspect hot shards, zone placement, and query routing.

---

## 29. Limit Register Template

Teams should maintain a traceable register:

| ID | Component | Limit/Constraint | Source | Evidence | Owner | Checked At |
|---|---|---|---|---|---|---|
| LIM-001 | BSON | `maxBsonObjectSize` | `hello` + manual | command output | DBA | Check date |
| LIM-002 | Aggregation | Spill/`allowDiskUse` | server settings + docs | profiler/explain | Data team | Check date |
| LIM-003 | Transaction | Lifetime/config | `getParameter`/Atlas docs | config snapshot | Platform | Check date |
| LIM-004 | Connections | Client pool + Atlas tier | driver config + Atlas | dashboard | Backend/SRE | Check date |
| LIM-005 | Change Stream | Oplog retention | replica metrics | lag chart | SRE | Check date |
| LIM-006 | Search | Search index/vector restrictions | Atlas docs/tier | UI/API | Search team | Check date |
| LIM-007 | Disk | IOPS/storage headroom | Cloud/OS metrics | dashboard | SRE | Check date |

### 29.1. Fields to Store per Entry

~~~yaml
id: LIM-003
component: mongodb-transaction
environment: staging
server_version: "<captured-version>"
fcv: "<captured-fcv>"
topology: replica-set
tier: "<atlas-tier-or-self-managed>"
client: "<driver-and-version>"
property: transactionLifetimeLimitSeconds
effective_value: "<observed-value>"
unit: seconds
classification: configurable
reference: "<versioned-document-url>"
observed_at: "<ISO-8601 timestamp>"
verified_by: "<owner-or-team>"
action_threshold: "<application-policy>"
notes: "<what-to-watch>"
~~~

This is a **recording template**, not live cluster data. Never fill in fake versions or tiers and pass them off as evidence.

### 29.2. Stale Entries Expire

Set review dates on limits tied to tiers and service docs. Refresh the limit register whenever upgrading drivers, changing tiers, resharding, or raising FCV.

### 29.3. Attach Verifiable Evidence

A bare line reading "limit=500" missing version, cluster, docs, and timestamp is useless during an incident. Link redacted command outputs, screenshots, or authorized dashboards.

---

## 30. Limit Verification Procedure Before Production Rollout

### Step 1 — Identify the Change

For example, moving from embedded order items to 100,000 events, adding a `$lookup` aggregation, and enlarging connection pools.

### Step 2 — Map to Limit Categories

- 16 MiB document / array growth.
- Multikey index restrictions.
- Aggregation output / memory.
- Client heap / cursor handling.
- Connection pools + Atlas quotas.
- Change stream lag if CDC is involved.

### Step 3 — Capture the Environment

Server versions, FCV, topology, tier, driver, deployment settings, and workload scale.

### Step 4 — Consult Versioned Docs

Check the manual matching your exact server release, Atlas tier docs, and driver compatibility matrix. Record URLs and dates.

### Step 5 — Measure on the Cluster

Run `hello`, stats, index listings, `explain`, profiler/metrics, and resource quotas. If lacking permissions, request evidence from the platform owner.

### Step 6 — Calculate Headroom

Never ship with an average 15.9 MiB document just because the hard cap is 16 MiB. Account for growth rate, high percentiles, peak concurrency, and safety margins.

### Step 7 — Staging Load and Fault Tests

Use production-like data and cardinality; test top tenants, hot SKUs, network faults, primary stepdowns, disk pressure, and timeouts.

### Step 8 — Set Guardrails

Cap max event payloads, max array lengths, batch sizes, `maxTimeMS`, pool bounds, concurrency limits, alerts, rate limits, and retry policies.

### Step 9 — Canary Rollout

Monitor latency, errors, memory, disk spills, and replica lag; halt or roll back if internal thresholds breach.

### Step 10 — Update the Register

Record effective observed values and lessons learned post-rollout so on-call engineers know exactly which limits were verified.

---

## 31. Runbook: `BSONObjectTooLarge` or Document Exceeding 16 MiB

1. Confirm error class and message; separate insert/update failures from aggregation output failures.
2. Record server/driver versions and `hello.maxBsonObjectSize` if permitted.
3. Identify offending document ID and tenant without logging raw PII.
4. Measure `$bsonSize:"$$ROOT"` and array counts on suspect records.
5. Pinpoint the oversized field or unbounded array: events, comments, attachments, or snapshots.
6. Stop retry storms or `$push` loops continuing to bloat the document.
7. Choose bounded recent arrays, referenced collections, buckets, or GridFS per business needs.
8. Backfill using stable IDs, checkpoints, and idempotency.
9. Drain legacy writers and reconcile before removing embedded history.
10. Add size alerts well below the ceiling and update the data model.

**Never** raise `batchSize` or `allowDiskUse` to fix a document exceeding 16 MiB; neither option alters the hard document limit.

---

## 32. Runbook: Aggregation Exceeds Memory or Output Limit

### 32.1. Classify the Failure

- Single result document > 16 MiB?
- `$sort` or `$group` stage exceeding memory?
- `$group` `$push` accumulator too large?
- `$facet` intermediate > 100 MB?
- `$lookup` fan-out?
- Pipeline > 1,000 stages?
- Driver/client OOM rather than a `mongod` error?
- Timeout caused by missing indexes or IOPS bottlenecks?

### 32.2. Use Explain and Profiler Safely

Avoid enabling high-overhead full profiling continuously in production without checking PII and load impact. Gather evidence per request/pipeline ID and query shape.

### 32.3. Apply Targeted Fixes

- `$match` early.
- Index filter, sort, and join fields.
- `$project` down fields before heavy stages when semantics allow.
- Keep `$sort` + `$limit` in the right semantic order.
- Avoid `$push:"$$ROOT"` when only counts or sums are needed.
- Bound `$lookup` foreign pipelines.
- Paginate raw histories.
- Materialize summaries / `$merge` into small documents.
- Enable disk spill where supported and disk I/O budget allows.

### 32.4. Never Raise Memory Blindly

Shifting one query from RAM to disk can still exhaust disk IOPS under concurrency and trigger a broader outage. Benchmark and track `usedDisk`, IOPS, and p99.

---

## 33. Runbook: Connection Exhaustion or Timeouts

1. Distinguish server selection timeout, connect timeout, pool wait timeout, socket timeout, and `maxTimeMS`.
2. Capture driver version, pool settings, and instance count.
3. Read Atlas connection metrics or `serverStatus.connections` if permitted.
4. Inspect sockets, file descriptors, and OS/container limits.
5. Multiply service replicas × connections per node plus background workers.
6. Check for connection leaks, unclosed cursors/sessions, and retry storms.
7. Reduce concurrency and fix slow queries—do not merely increase pool size.
8. If genuine capacity is short, scale tier/nodes within allowed quotas.
9. Test failover and reconnection behavior; monitor p99, connection counts, and errors.
10. Update the limit register with observed thresholds.

### 33.1. One `maxPoolSize` Number Does Not Equal Cluster Connections

Each service instance connects to multiple server addresses, and drivers maintain monitoring connections with topology-dependent behavior. Measure actual connection counts instead of guessing roughly.

---

## 34. Runbook: Change Stream Cannot Resume

1. Record server version, FCV, topology, driver, and exact exception.
2. Check resume token validity/retention against oplog history.
3. Measure consumer lag, write/arrival rates, and backlog.
4. Distinguish transient network errors from expired oplog history.
5. Never discard the resume token and watch from "now" without assessing data loss.
6. If history is lost, re-bootstrap and reconcile from a source snapshot with a clear cutover point.
7. Enforce idempotent processing and durable checkpoints after successful side effects.
8. Tune consumer concurrency, backpressure, or oplog sizing as needed.
9. Verify pre-/post-image retention if pipelines depend on them.
10. Add alerts before consumer lag approaches the oplog window.

---

## 35. Runbook: Transaction Timeouts or Write Conflicts

1. Classify transaction lifetime limit, lock/write conflict, unknown commit, or network error.
2. Check `transactionLifetimeLimitSeconds` and Atlas tier/quotas.
3. Measure transaction duration, touched documents/collections, and retry counts.
4. Check for HTTP calls or external I/O inside the transaction.
5. Shrink read/write sets and shorten transaction duration.
6. Order touched stock buckets deterministically where appropriate.
7. Retry strictly per driver contract using the same business operation ID.
8. On unknown commit → retry commit or reconcile via durable marker.
9. Never execute non-idempotent external side effects inside a retryable callback.
10. Track p95/p99 latency, conflict rates, and primary resource headroom.

---

## 36. Verifying Limits via Commands and Cross-Checking

`mongosh` action table:

| Item | Command / Inspection Path | What to Record |
|---|---|---|
| Server version | `db.version()`, `buildInfo` | Major/minor/patch, edition |
| FCV | `getParameter featureCompatibilityVersion` | Effective FCV |
| BSON/message/batch protocol | `hello` | `maxBsonObjectSize`, `maxMessageSizeBytes`, `maxWriteBatchSize` |
| Topology | `hello`, `replSetGetStatus`, Atlas UI | Members/shards, primary, lag |
| Index count | `db.coll.getIndexes()` | Count, types, index definitions |
| Collection sizes | `db.coll.stats()` | `count`, `avgObjSize`, indexes, storage |
| Large documents | `$bsonSize:"$$ROOT"` | Top/p95/max size |
| Query/index plans | `explain("executionStats")` | `IXSCAN`/`COLLSCAN`, examined counts |
| Memory spill | Profiler/log `usedDisk` | Spill frequency and latency |
| Transactions | `getParameter transactionLifetimeLimitSeconds` | Effective limit and restrictions |
| Connections | `serverStatus().connections`, Atlas Metrics | Active/available/total |
| Oplog | Replica metrics / oplog status | Retention window, consumer lag |
| TTL | `getIndexes` + deletion monitoring | Expiry config and actual lag |
| Search/Vector | Atlas UI/API/Search docs | Index quotas, dimension/query limits |
| Backup | Atlas/self-managed backup admin | RPO/RTO/retention |
| Storage/IO | OS/Atlas/storage metrics | Disk headroom, IOPS, throughput |

### 36.1. Not Every Command Runs on Atlas

Privileges and product tiers vary. When access is denied, record "not observable with current role" rather than guessing a value.

### 36.2. A Staging Number Is Not Production

Every finding must carry its environment label. Atlas M10 staging, M40 production, sharded production, and local standalone all have distinct constraints.

---

## 37. Workload Risk Matrix

| Workload | Likely Limit Encountered | Prevention |
|---|---|---|
| User profile with audit events | BSON 16 MiB, unbounded arrays | Reference events, bounded recent preview |
| Order report of all invoices | `$group` accumulator, 16 MiB result | Scalar summaries / pagination |
| Search faceted navigation | `$facet` 100 MB, 16 MiB result | Cap arrays, selective `$match` |
| ERP bulk sync | Write batches, heap, partial errors | Bounded chunks, checkpoints, idempotency |
| Hot-SKU inventory | Single-doc contention, txn retries | Atomic conditionals, quotas, benchmarks |
| Social feed/timeline | Array growth, pagination | Separate posts/events, indexed keyset |
| Time-series telemetry | Bucket/index/TTL/version rules | Metadata/time modeling and retention |
| CDC to Kafka | Oplog retention, resume lag | Backpressure, durable checkpoints |
| Vector similarity search | Atlas Search/vector index quotas | Tier/version/dimension/index planning |
| Multi-SKU checkout | Transaction lifetime/contention | Short transactions, stable IDs |
| Large attachments | BSON 16 MiB | GridFS / object storage |
| Many microservices | Connection/server quotas | Pool sizing, per-service budgets |
| Multi-region reads | Replication lag, network latency | Read preference/consistency policy |
| Regulatory audits | TTL/backup/retention | Legal holds, immutable event logs |

### 37.1. The First Limit Hit Is the Real Bottleneck

An application may hit an HTTP gateway payload limit or JVM heap OOM well before MongoDB's 16 MiB cap. Always identify the **exact layer throwing the error**.

---

## 38. Misconceptions to Eliminate

**Misconception 1:** "MongoDB only stores 16 MiB of total data."  
No. 16 MiB applies per BSON document.

**Misconception 2:** "A cursor returns at most 16 MiB across all documents."  
No; cursors stream multiple batches, while each individual document obeys the limit.

**Misconception 3:** "Enabling `allowDiskUse` allows a 50 MiB result document."  
No; the output BSON document limit still applies.

**Misconception 4:** "`$facet` spills to disk just like `$sort`."  
No; `$facet` enforces its own cap without disk spill.

**Misconception 5:** "`$group` spills, so `$push`-ing a million records is safe."  
No; accumulator array growth and final BSON size still constrain it.

**Misconception 6:** "Max write batch size is the target size for every app batch."  
No; it is a protocol ceiling, not an application recommendation.

**Misconception 7:** "BSON 16 MiB is measured in JSON string characters."  
No; it is measured in binary BSON bytes.

**Misconception 8:** "Any syntactically valid MongoDB command works on every Atlas tier."  
No; product, tier, and version restrictions vary.

**Misconception 9:** "A newer server binary guarantees a feature because `db.version` is high."  
You must also verify FCV and feature gates.

**Misconception 10:** "Standalone tests prove production transactions and Change Streams."  
No; test against a supported topology.

**Misconception 11:** "More indexes always mean faster performance."  
Write amplification, storage overhead, and index limits carry real cost.

**Misconception 12:** "Unique indexes behave identically across all sharded collections."  
Restrictions apply based on shard key and server release.

**Misconception 13:** "TTL deletes at the exact expiration second."  
Background TTL monitoring incurs lag.

**Misconception 14:** "Oplog retains 7 days of change stream history by default on every cluster."  
Retention depends on configuration, write volume, and topology.

**Misconception 15:** "Replication lag only affects dashboards."  
It affects failovers, stale reads, backups, and CDC.

**Misconception 16:** "The 60s transaction lifetime can simply be raised for any workflow."  
Check restrictions and resource budgets; never call external APIs inside transactions.

**Misconception 17:** "Driver retryable writes replace business idempotency."  
HTTP or message replays can still apply business effects twice.

**Misconception 18:** "Having backups eliminates the need for restore drills."  
RTO, encryption keys, and version compatibility can derail untested restores.

**Misconception 19:** "`collStats` `avgObjSize` reveals the largest document."  
Averages hide outliers; measure with `$bsonSize`.

**Misconception 20:** "Search indexes and B-tree indexes share the same quota."  
Atlas Search and Vector Search follow separate limits.

**Misconception 21:** "Sharding makes a document larger than 16 MiB valid."  
No.

**Misconception 22:** "Raising `maxConnections` fixes a pool leak."  
It can exhaust server sockets even faster.

**Misconception 23:** "MongoDB server errors and JVM OOMs are the same thing."  
They occur at different layers and require separate diagnostics.

**Misconception 24:** "Numbers from older docs remain authoritative for current releases."  
Always consult versioned docs and effective runtime configs.

**Misconception 25:** "Changing one parameter never affects other workloads."  
Memory, disk, and network are shared resources; benchmark and prepare rollback plans.

---

## 39. Checklist for Upgrading MongoDB Server / FCV

- [ ] Record server versions of all relevant nodes.
- [ ] Record FCV and supported upgrade/downgrade paths.
- [ ] Verify the driver / Spring Data compatibility matrix.
- [ ] Check changed feature restrictions.
- [ ] Verify index key, compound, multikey, and unique rules.
- [ ] Check aggregation spill, memory, and stage behavior changes.
- [ ] Check transaction lifetime, retry, and commit semantics.
- [ ] Check oplog, Change Streams, and pre-image support.
- [ ] Check sharding, balancer, and resharding restrictions.
- [ ] Check time-series, TTL, and backup/restore support.
- [ ] Check Atlas plan/tier-specific constraints.
- [ ] Capture query plans, p95/p99 latencies, and error baselines.
- [ ] Test rolling upgrades with mixed versions where supported.
- [ ] Never enable FCV-gated features before upgrading FCV.
- [ ] Maintain verified backups and run a restore rehearsal.
- [ ] Record release notes, risk owner, and rollback boundary.

---

## 40. Checklist for Changing Atlas Tier or Cloud Region

- [ ] Confirm current tier/product name.
- [ ] Verify connection, storage, and compute quotas.
- [ ] Verify backup/PITR retention and restore paths.
- [ ] Verify Search / Vector Search node and index limits.
- [ ] Confirm region/cloud support and private endpoints.
- [ ] Configure auto-scaling upper and lower bounds.
- [ ] Measure throughput, IOPS, and headroom.
- [ ] Verify DNS, TLS, IP allowlists, and roles.
- [ ] Align application connection pools and retry policies.
- [ ] Verify shard/replica topology and data placement.
- [ ] Update monitoring, alerts, and on-call runbooks.
- [ ] Obtain approval for cost impact and rollback/scale-down steps.

---

## 41. Code Review Checklist Related to Limits

- [ ] No unbounded embedded arrays or raw event logs inside one document.
- [ ] Max byte/element policies enforced on client input.
- [ ] Full history is not aggregated into `$push:"$$ROOT"`.
- [ ] `$lookup` uses foreign indexes and bounded fan-out where needed.
- [ ] `$facet` avoids unbounded result arrays.
- [ ] `$sort` uses an index/top-K or has an explicit spill policy.
- [ ] Cursors are closed cleanly and never eagerly materialized into full lists.
- [ ] Bulk inputs are chunked cleanly with partial-error handling.
- [ ] Transactions stay short with zero external API calls in retry callbacks.
- [ ] Replayable requests enforce idempotency keys.
- [ ] Dynamic aggregation builders bound stage counts.
- [ ] Time-series/Search/Vector capabilities carry version/tier proof.
- [ ] Query `maxTimeMS` reflects SLA budgets—never used as a substitute for indexes.
- [ ] Driver pool sizing accounts for replica count and server capacity.
- [ ] Schema/index/TTL migrations maintain multi-version compatibility.
- [ ] Metrics and alerts trigger well below hard limits to prevent outages.

---

## 42. Practice Exercises

### Exercise 1 — Environment Identification

Run `db.version()`, `hello`, `buildInfo`, and the FCV query in a lab replica set. Build a server/FCV/topology summary table.

### Exercise 2 — BSON Limit

Create documents ranging from a few KiB to several MiB in the lab and measure with `$bsonSize`. Explain why BSON bytes differ from JSON string length.

### Exercise 3 — Array Growth

Create a document holding `audit_events`; append in batches while tracking size and count. Design a referenced collection for unbounded growth.

### Exercise 4 — Nesting

Create small nested BSON documents; research nesting depth limits and design a flatter query-friendly schema.

### Exercise 5 — Index Inventory

List `getIndexes()`; classify useful vs redundant indexes without dropping any prior to gathering workload evidence.

### Exercise 6 — Compound Multikey

Attempt designing a compound index with two array fields; identify the restriction in your lab server version.

### Exercise 7 — Unique Index

Create a partial unique index on `normalized_email`; verify whether documents excluded by the filter are constrained.

### Exercise 8 — Aggregation Output

Replace `$group + $push all events` with `$sum` plus paginated history queries.

### Exercise 9 — Sort and Index

Use `explain("executionStats")` to compare an unindexed sort against an indexed `tenant/time` sort.

### Exercise 10 — Facet

Build a facet returning page 20 + count; explain the 100 MB internal limit and 16 MiB output limit.

### Exercise 11 — Dynamic Stages

Generate 1,001 `$set` stages in a test, count them, and refactor into fewer stages.

### Exercise 12 — `allowDiskUse`

Compare `$sort`/`$group` behavior on a staging dataset with `allowDiskUse` true vs false and observe spills.

### Exercise 13 — Batch Capabilities

Read `hello.maxWriteBatchSize`, `maxMessageSizeBytes`, and `maxBsonObjectSize` and explain how the three numbers differ.

### Exercise 14 — Bulk Retry

Design a 500-write batch using checkpoints and idempotent upserts; handle partial failures and unknown outcomes.

### Exercise 15 — Cursor Memory

In Java, replace `into(new ArrayList<>())` with a streaming cursor and bounded `batchSize`.

### Exercise 16 — Transaction

On a lab replica set, create a transaction updating inventory + inserting a reservation; simulate insufficient stock and timeouts.

### Exercise 17 — Lifetime

Look up `transactionLifetimeLimitSeconds` in server/Atlas docs; explain why payment HTTP calls do not belong inside a transaction.

### Exercise 18 — Oplog Window

Measure change stream lag and lab oplog retention; design an alert before lag nears the oplog window.

### Exercise 19 — TTL

Experiment with TTL deletion on disposable logs, distinguishing business expiration from background deletion.

### Exercise 20 — Time-Series

Create a time-series collection in your lab version and look up restrictions on updates, TTL/indexes, and sharding.

### Exercise 21 — Atlas Tier

Pick an Atlas tier you can inspect and populate a register for storage, connections, backups, and Search citing current docs.

### Exercise 22 — Driver Pool

Compute the connection budget for 10 service instances with pool size `X`; measure actual connections and compare against quota.

### Exercise 23 — Restore Drill

Restore a snapshot into staging; verify server/schema compatibility, encryption keys, duration, and RTO.

### Exercise 24 — Search Quota

Check Atlas Search / Vector Search documentation for your tier; distinguish vector dimension limits from MongoDB BSON limits.

### Exercise 25 — Limit Register

Fill the template with at least 10 entries including effective values, owners, sources, dates, and re-check triggers.

### Exercise 26 — Large Document Incident

Write a runbook for `BSONObjectTooLarge` caused by an unbounded audit array; select a bounded preview plus separate event collection.

### Exercise 27 — Aggregation Incident

A `$lookup→$unwind→$group→$facet` pipeline hits a memory error. Measure fan-out per stage and propose a leaner shape.

### Exercise 28 — Connection Incident

An app hits pool wait timeouts after scaling to 20 pods. Cross-check pool settings, server quotas, connection metrics, and slow queries.

### Exercise 29 — Upgrade Gate

Draft an upgrade checklist for server/FCV while Java Driver and Spring Data remain older. Propose a testing and upgrade sequence per the support matrix.

### Exercise 30 — Architecture Review

Design a system on Atlas using documents, transactions, Search, Change Streams, and TTL. Record hard limits, tier limits, internal thresholds, test evidence, and rollback plans.

---

## 43. Review Questions

1. How do hard limits, configurable limits, quotas, and operational limits differ?
2. Why must both server version and FCV be recorded separately?
3. Why are Atlas tier and driver version part of the "environment signature"?
4. What is the maximum MongoDB BSON document size in MiB?
5. Why does 16 MiB not limit the total collection size?
6. How do BSON bytes differ from JSON character counts?
7. How do `$bsonSize` and `$size` measure two different things?
8. Why is `avgObjSize` insufficient for detecting large-document outliers?
9. Is there a single universal max element count for arrays?
10. What kind of data is GridFS designed for?
11. Can sharding store a 20 MiB BSON document?
12. Why must namespace and naming restrictions be checked per version?
13. Why is the maximum index count alone insufficient for designing an index strategy?
14. What restrictions apply to compound multikey indexes?
15. Does a partial unique index enforce uniqueness on documents excluded by its filter?
16. What must be considered for sharded unique indexes?
17. How does the aggregation output limit differ from stage memory limits?
18. What is the typical limit on pipeline stage counts?
19. What limits apply to `$facet`, and does it spill to disk?
20. Why is `$group` with `$push:"$$ROOT"` hazardous?
21. Does `allowDiskUse` make a 20 MiB result document valid?
22. Why can enabling disk spill raise disk I/O?
23. How does `$sort + $limit` differ from `$limit + $sort`?
24. Why can `$lookup` easily trigger fan-out?
25. Why can `$unwind` generate massive row counts?
26. How do `maxBsonObjectSize`, `maxMessageSizeBytes`, and `maxWriteBatchSize` differ?
27. Why should protocol maximums not be used as default application batch sizes?
28. Is an ordered bulk write an all-or-nothing atomic transaction?
29. Can a multi-batch cursor exceed 16 MiB in total returned data?
30. Why can Java `into(new ArrayList<>())` trigger an OOM?
31. Why does `maxTimeMS` not replace query optimization?
32. Which topologies support MongoDB multi-document transactions?
33. Is transaction lifetime fixed identically across every environment?
34. Why should payment APIs not be called inside a transaction callback?
35. How should an unknown commit outcome be handled?
36. Do driver retryable writes replace business idempotency?
37. Why must connection budgets be calculated across instances and servers?
38. How does a pool timeout differ from a server BSON error?
39. How does oplog retention affect Change Streams?
40. Why do resume tokens not remain valid forever?
41. Does TTL delete documents at the exact expiration second?
42. Does TTL automatically release inventory reservations?
43. Can time-series collections be updated like regular collections on every version?
44. Does GridFS allow arbitrary BSON documents larger than 16 MiB?
45. Are Atlas Search / Vector Search quotas identical to B-tree index limits?
46. Why does backup retention alone not guarantee RTO?
47. Why can raising memory limits or pool sizes worsen an incident?
48. Which limits stem from OS, containers, or disk IOPS?
49. Which feature groups require testing when raising FCV?
50. Which fields belong in a useful Limit Register?
51. What should you do when `serverStatus` returns permission denied?
52. Why does a different staging tier lead to flawed production conclusions?
53. Which workloads commonly create unbounded documents?
54. Which metrics warn before hitting hard limits?
55. How do you distinguish a MongoDB error from an HTTP gateway 413?
56. When must the driver compatibility matrix be checked?
57. When should a referenced collection replace an embedded array?
58. Why should legacy fields not be deleted before migration reconciliation?
59. When must a previously verified limit be re-verified?
60. Why is a bare number `N` without version, source, and date insufficient as a deployment gate?

---

## 44. Summary

**A MongoDB limit catalog is an environment-aware decision tool, not a static cheat sheet to memorize.**

- **BSON:** 16 MiB per document, nesting and naming restrictions; measure in BSON bytes rather than JSON text length.
- **Indexes:** counts, compound/multikey/unique/sharded rules; verify against server version and workload.
- **Aggregation:** distinguish the 16 MiB result cap, stage memory/spill, non-spilling `$facet`, accumulator growth, and 1,000-stage cap.
- **Writes/Clients:** `hello` advertises BSON/message/batch capabilities; driver pools, heap memory, retries, and operational batch sizes impose separate bounds.
- **Transactions:** topology, FCV, lifetime, resource budgets, commit uncertainty, and external idempotency.
- **Replication/CDC:** oplog retention, lag, resume history, and pre-/post-images; no single fixed retention window fits every cluster.
- **Sharding/Time-Series/TTL:** carry version-dependent compatibility rules—never assume behavior solely from the name "MongoDB."
- **Atlas/Search/Vector:** quotas vary by tier, plan, region, and feature; always verify current documentation.
- **Self-Managed:** OS, RAM, file descriptors, disk IOPS, network, and container limits can bottleneck before the database engine.
- **Operations:** maintain a Limit Register with evidence, thresholds, owners, and dates; re-verify before upgrades, cutovers, and incidents.

Sound architecture does not ask merely "What is MongoDB's maximum?"—it asks: **Which limits govern this workload on this exact server/FCV/tier/driver, how were they measured, how much headroom remains, and how will the system degrade or recover when approached?**

## Official References

- [MongoDB — Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB — BSON Documents](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB — `$bsonSize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonsize/)
- [MongoDB — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB — Aggregation Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB — `$facet`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB — `$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB — `$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB — `$sort`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB — Index Limits](https://www.mongodb.com/docs/manual/reference/limits/#index-limitations)
- [MongoDB — Compound Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB — Replica Sets](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [MongoDB — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB — Queryable Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/)
- [MongoDB — Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB Atlas Documentation](https://www.mongodb.com/docs/atlas/)
- [MongoDB Atlas — Limits](https://www.mongodb.com/docs/atlas/reference/atlas-limits/)
- [MongoDB Atlas Search](https://www.mongodb.com/docs/atlas/atlas-search/)
- [MongoDB Atlas Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/)
