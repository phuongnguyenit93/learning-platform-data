# Refine shard key, resharding, and support conditions in MongoDB

## 1. The problem: a shard key that used to make sense is no longer suitable

A SaaS application stores enterprise customer orders in the `orders` collection. Initially, the development team chose the shard key:

```javascript
{ tenantId: 1 }
```

Because the application mostly queries by tenant, this choice seemed reasonable. After some time, the largest tenant grew to tens of millions of orders, generating most of the write traffic for the entire system. While other shards still had spare capacity, the shard holding this tenant's key range became a hotspot.

Several options were proposed:

1. **Append `orderId` after `tenantId`** so the key has higher cardinality while keeping tenant as the first field.
2. **Switch completely to `{orderId: "hashed"}`** to distribute writes across the entire cluster.
3. **Change the order to `{regionId: 1, tenantId: 1}`** because product queries are now mostly region-based.

These three options cannot be performed with the same command. MongoDB distinguishes between:

- **Refine shard key**: extend the existing shard key by **appending fields at the end**, preserving the existing key prefix.
- **Resharding**: reorganize a sharded collection according to a **new shard key**, allowing changes to fields, field order, and range/hashed distribution when supported by the MongoDB version.

Both affect routing, indexes, query patterns, and operations; however, **refining a shard key is typically a metadata change that does not immediately redistribute documents**, whereas **resharding is an actual data distribution transition process**.

After this lesson in MongoDB's **Sharding** chapter, you will be able to:

1. Explain what a shard key is and why you should not choose one based solely on a single query.
2. Distinguish refining a shard key from resharding and know when each approach is needed.
3. Understand the **prefix + suffix** rule of `refineCollectionShardKey`.
4. Know what conditions to review before making changes: topology, version/FCV, indexes, data, unique indexes, collation, zones, and system load.
5. Understand the resharding phases, required resources, and the limits of "online" execution.
6. Examine impacts on query routing, scatter-gather, chunks, jumbo/hotspots, and application writes.
7. Run a `mongosh` example on an **isolated test** sharded cluster.
8. Design an appropriate rollout, monitoring, and recovery plan for production.

## 2. Reviewing essential components of sharding

### 2.1. The shard key determines how data is partitioned

In a MongoDB sharded cluster, a collection is distributed according to its **shard key**. For example:

```javascript
{ tenantId: 1, orderId: 1 }
```

These two fields form a **compound shard key**. The fields and their order directly affect:

- How the value space is split into key ranges/chunks.
- How `mongos` routes queries and write operations.
- How data volume and write load are distributed across shards.
- The ability to use the shard key to filter queries.
- Unique index constraint requirements in a sharded collection.

A shard key is not merely an index to speed up lookups: it is part of the **data distribution architecture**.

### 2.2. Components in a cluster

```text
             Application / MongoDB Driver
                         |
                         v
                       mongos
                         |
                Shard metadata/routing
                         |
        +----------------+----------------+
        |                |                |
        v                v                v
    Shard A          Shard B          Shard C
  (replica set)    (replica set)    (replica set)
        |                |                |
      Data             Data             Data
```

The components:

- **`mongos`**: the router that directs queries to the appropriate shards based on metadata and the query.
- **Shards**: where documents are stored; typically deployed as replica sets.
- **Config server replica set**: maintains sharding metadata.
- **Balancer and chunk/range distribution mechanisms**: help distribute data according to current policies.

Each tenant does not correspond to a fixed shard. Data/chunks can be allocated, migrated, or reorganized over time.

### 2.3. Ranged and hashed shard keys

**Ranged sharding** uses key value ordering:

```javascript
{ orderId: 1 }
{ tenantId: 1, orderId: 1 }
```

It can support range queries and key-based locality, but risks hotspots if the key portion being written increases monotonically or has low cardinality.

**Hashed sharding** uses the hash value of a key field:

```javascript
{ orderId: "hashed" }
```

Hashing helps scatter many distinct values across the key space, but alters the advantage of range queries over the original values. Choosing hashed does not mean every query will be better targeted, and **a hashed index does not directly support unique constraints**.

### 2.4. A good shard key must be evaluated on real workloads

| Factor | Question to answer |
| --- | --- |
| Cardinality | Are there enough distinct shard key values? |
| Frequency/skew | Does one value or group of values account for most of the data? |
| Monotonicity | Do values increase sequentially, creating a hotspot at one end of the range? |
| Query routing | Do critical APIs know the shard key for targeted routing instead of scatter-gather? |
| Write distribution | Is the write rate evenly distributed across shards? |
| Data growth | How are tenants, regions, or the collection expected to grow? |
| Uniqueness | Are required unique indexes compatible with the shard key? |
| Zones | Are there regional data residency or tier requirements? |
| Migration cost | Is there sufficient disk capacity, network bandwidth, and time to perform the change? |

Changing a shard key without measuring the workload may simply move a hotspot from one place to another.

## 3. Two different operations: refine and reshard

### 3.1. Refine means appending a suffix

Suppose the current shard key is:

```javascript
{ tenantId: 1 }
```

A structurally valid refined shard key is:

```javascript
{ tenantId: 1, orderId: 1 }
```

Because the new key **preserves the prefix** `tenantId:1` and appends `orderId:1` at the end.

Example with multiple suffixes:

```javascript
// Old
{ regionId: 1, tenantId: 1 }

// Refine by appending two fields at the end
{
  regionId: 1,
  tenantId: 1,
  orderMonth: 1,
  orderId: 1
}
```

Key point: refine **does not replace, remove, or reorder** existing shard key fields. Nor does it change a component from `1` to `"hashed"`.

### 3.2. Reshard means choosing a new key and reorganizing data

If you need to go from:

```javascript
{ tenantId: 1 }
```

to:

```javascript
{ orderId: "hashed" }
```

this is **resharding**, not refinement, because the new key does not keep the old prefix.

Resharding is also appropriate when you want to:

- Replace `tenantId` with `customerId`.
- Change the field order in a compound key.
- Remove an unnecessary field from the shard key.
- Change the partitioning method between range and hash, if supported by the feature/version.
- Redistribute the collection according to a newly designed key.

Resharding is not a simple index rename operation. The system must transform data and metadata so the collection operates under the new distribution.

### 3.3. Comparison table

| Criterion | Refine shard key | Resharding |
| --- | --- | --- |
| Purpose | Add cardinality at the **end** of the existing key | Change how the collection is sharded |
| Can old fields be removed/reordered? | No | A new key can be chosen subject to support conditions |
| Can `{a:1}` change to `{a:1,b:1}`? | Yes, if conditions are met | Can be considered, though usually unnecessary if refine suffices |
| Can `{a:1}` change to `{b:1}`? | No | Yes |
| Immediately redistributes all data automatically? | No | Goes through a redistributing/resharding process |
| Large network/storage cost | Usually lower; still requires index and metadata | Can be very high; requires capacity planning |
| Reversible by simply dropping the suffix? | No | No instant "undo"; requires another reshard plan or recovery |
| Requires server/FCV support | Yes | Yes |
| Impacts queries/uniques/zones? | Yes | Yes |
| Should it be run casually in production? | No | No |

**Quick selection rule:** if the requirement is only to **append fields to the tail of the shard key** while keeping the existing fields in order, investigate **refine** first. If the requirement is to **change the fundamental structure of the key**, you need to evaluate **resharding**.

## 4. Prefix rules of refining a shard key

### 4.1. Field order is mandatory

Given the current shard key:

```javascript
{ tenantId: 1, regionId: 1 }
```

candidate new keys under the prefix-preservation rule:

```javascript
// Valid refinement structure: preserves old prefix, appends suffix.
{ tenantId: 1, regionId: 1, orderId: 1 }

// Appending multiple suffixes:
{ tenantId: 1, regionId: 1, orderMonth: 1, orderId: 1 }
```

Keys that are **not refinements**:

```javascript
// Drops regionId
{ tenantId: 1, orderId: 1 }

// Reorders existing fields
{ regionId: 1, tenantId: 1, orderId: 1 }

// Inserts a field in the middle of the existing prefix
{ tenantId: 1, orderId: 1, regionId: 1 }

// Changes the leading field
{ customerId: 1, regionId: 1 }

// Changes the type of the leading field
{ tenantId: "hashed", regionId: 1 }
```

Whether these keys can be used in a **resharding operation** must be checked against version limits, indexes, topology, and actual data. What is certain is that they **do not satisfy the suffix-only rule of refine**.

### 4.2. Why does MongoDB restrict refine this way?

Refining extends the key space by placing suffix values after the existing prefix:

```text
Old key:

  tenantId
  T1 | T2 | T3 | ...

Refined key:

  (tenantId, orderId)
  (T1, O001) (T1, O002) ... (T2, O001) ...
```

Keeping the prefix allows MongoDB to transition existing range/chunk metadata to the longer key form **without immediately having to copy every document elsewhere into an unrelated key space**.

If you change the leading field or field order, documents that were previously adjacent under the old key may need to be ordered/distributed completely differently; that is the job of resharding.

### 4.3. Refine is not just adding a compound index

The command:

```javascript
db.orders.createIndex({ tenantId: 1, orderId: 1 });
```

only creates an **index**. It does not automatically update the collection's shard key metadata.

After preparing the index, the refine operation requires a separate administrative command:

```javascript
sh.refineCollectionShardKey(
  "sales.orders",
  { tenantId: 1, orderId: 1 }
);
```

Conversely, `refineCollectionShardKey` does not automatically create every auxiliary index needed for business queries. You must check the **supporting index for the new shard key** requirement before running it.

### 4.4. Metadata is updated, data is not immediately rebalanced automatically

After refining:

- The collection's shard key metadata uses the new key.
- Existing ranges/chunks can be represented with the longer key.
- Existing data is **not automatically copied in full to new locations just because the refine command returned success**.
- Distribution may gradually change through split/move/chunk balancing mechanisms depending on the features and conditions of the running version.
- Queries and writes after refinement must be compatible with the new key, especially when targeted routing is needed.

If the mandatory goal is to **immediately redistribute a severely skewed collection**, refining alone may not resolve the imbalance. You must monitor chunk/range distribution and evaluate next steps.

## 5. Support conditions for refine

### 5.1. Version and feature compatibility

MongoDB introduced the ability to **refine a shard key** starting in the **4.4** release series. However, before applying it to a real cluster, verify:

- Are all components of the sharded cluster running a compatible version?
- Does the **Feature Compatibility Version (FCV)** meet the feature's requirement?
- Do your driver and `mongosh` support the syntax?
- Is the collection of a type allowed to be refined in that release?
- Is the cluster in any special DDL/resharding/balancing state that could conflict with refinement?
- If using a managed service, is the operation supported by the provider for that tier/deployment?

A cluster with newer binaries whose FCV has not been upgraded accordingly may still disallow newer features. Do not rely solely on the version number of a single connected `mongod` to conclude cluster-wide availability.

### 5.2. The collection must already be sharded

Refinement is an operation **on an existing sharded collection**. It is not used to turn an unsharded collection into a sharded one.

If a collection is not yet sharded, evaluate the initial shard key creation workflow with `sh.shardCollection` or the corresponding administrative command.

```javascript
// Initial collection sharding (example only, do not run in production).
sh.shardCollection(
  "sales.orders",
  { tenantId: 1 }
);

// Only afterward can refine be considered.
sh.refineCollectionShardKey(
  "sales.orders",
  { tenantId: 1, orderId: 1 }
);
```

Do not call `sh.shardCollection` a second time with a new key expecting it to act like a reshard command. Those are two different operations.

### 5.3. There must be an index supporting the new shard key

Before refining, MongoDB requires an **index supporting the extended shard key** according to the current version's rules. For example:

```javascript
use sales

db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "tenant_order_refined" }
);

// Only after verifying all conditions, run:
sh.refineCollectionShardKey(
  "sales.orders",
  { tenantId: 1, orderId: 1 }
);
```

The supporting index generally needs to:

- Have a key pattern compatible with the refined shard key.
- Not rely on a sparse/partial index that omits documents that can be sharded.
- Not be multikey on components that are not allowed in a shard key.
- Satisfy collation and index-type requirements.
- Not conflict with existing unique constraints.

Do not treat `createIndex()` succeeding as proof that refine will definitely succeed; it is only **one part of preflight**.

### 5.4. The suffix field must suit the data

If you want to add `orderId`:

```javascript
{ tenantId: 1, orderId: 1 }
```

inspect:

- How many documents are missing `orderId`?
- Are there documents with `orderId: null` or inconsistent types?
- Are there documents where `orderId` is an array?
- Does `orderId` have enough cardinality within each tenant?
- Is this field modified frequently?
- Do new write APIs ensure the field exists with the proper type?

Do not assume every version rejects all documents missing a suffix in the exact same way: MongoDB has changed how it handles **missing shard key fields** across releases. Check the specific release capabilities and collection characteristics. Even when the server allows missing/null values, large numbers of documents missing the suffix may sit in the same value range and **fail to improve distribution**.

For legacy data, a migration may be needed to backfill the key **according to a defined policy** before or after the operation. Migrations must use safely scoped commands and avoid fabricating dummy values that violate business semantics.

### 5.5. Unique indexes and the shard-key-prefix rule

For ranged sharded collections, **unique indexes** generally must have the **entire shard key as a prefix** so MongoDB can enforce uniqueness across shards. The default `_id` index has scope caveats if `_id` is not part of the shard key.

Example before refine:

```javascript
// Shard key:
{ tenantId: 1 }

// Unique on business key:
{ tenantId: 1, externalOrderId: 1 }
```

If you want to refine to:

```javascript
{ tenantId: 1, orderMonth: 1 }
```

then the existing unique index `{tenantId, externalOrderId}` **does not have the entire new key as a prefix**. This is a design conflict that must be resolved **before refining**, not a reason to drop the unique index without a replacement.

Analyze:

1. Which unique invariant is the index protecting?
2. After adding the shard key suffix, which unique indexes remain compatible?
3. If you use `{tenantId, orderMonth, externalOrderId}` unique, does that break the rule that "externalOrderId is unique per tenant across all months"?
4. Can another refined key be chosen that preserves the invariant?
5. If not, do you need to reshard with an appropriate key or design a registry/proxy collection to enforce global/business uniqueness?

**A syntactically valid unique index does not mean it protects the right business scope.** For instance, adding `orderMonth` to a unique key allows the same order code to appear in two different months.

Never choose or refine a shard key based purely on performance while ignoring uniqueness and authorization.

### 5.6. Zone sharding and data residency policies

A cluster may use **zones** to constrain shard key ranges to specific sets of shards; for example, `regionId:"EU"` data must only be allocated on shards within the appropriate zone.

When refining:

- Zone ranges defined under the old key may need adjustment/handling per version rules.
- Bounds must match the shape of the new shard key according to the relevant administrative commands.
- The key change must not cause data to violate residency policies.
- Check zone constraints and other DDL operations before changing the shard key.

Consult the zone-range handling sequence **for your MongoDB version**, because automatic bound extension vs. advance preparation requirements can vary across releases and use cases.

### 5.7. Hashed shard keys and related limits

The general rule of refine remains **preserving existing components and only appending a suffix**. If the old key contains `"hashed"`, you cannot use refine to turn that component into `1` or vice versa.

Whether a suffix can be appended to a hashed/compound shard key must be checked **specifically against the version's index and shard key limits**, rather than inferred from a ranged key example.

In particular:

- **Hashed indexes do not directly support unique constraints**.
- Refining does not automatically add uniqueness for a hashed key.
- If the main goal is switching between range ↔ hashed models, you must evaluate resharding.

## 6. Example of refining from tenant to tenant + order

### 6.1. Before refinement

The `sales.orders` collection is sharded by:

```javascript
{ tenantId: 1 }
```

One tenant has many orders:

```javascript
{ tenantId: "T1", orderId: "O-100", amount: 120000 }
{ tenantId: "T1", orderId: "O-101", amount:  50000 }
{ tenantId: "T1", orderId: "O-102", amount:  88000 }
{ tenantId: "T2", orderId: "O-200", amount:  35000 }
```

When distinguishing only by `tenantId`, all documents for the same tenant share the same shard key value. For a large tenant, data and write volume can concentrate in a single key range.

### 6.2. After refinement

New key:

```javascript
{ tenantId: 1, orderId: 1 }
```

Each order's shard key value now includes `orderId`:

```text
(T1, O-100)
(T1, O-101)
(T1, O-102)
(T2, O-200)
```

Potential benefits:

- Enables finer splitting/distinction among orders within the same tenant.
- Read/write operations providing **both fields** can target more accurately under the new metadata.
- Under suitable conditions, subsequent data movement/balancing can distribute smaller key ranges.

However:

- Refining alone **does not immediately spread T1 documents evenly across all shards**.
- Queries specifying only `tenantId:"T1"` may need to touch multiple ranges/chunks and potentially multiple shards once distributed.
- An overly hot tenant still requires measuring actual write distribution.
- If `orderId` increases monotonically, a write hotspot can occur at the upper tail of the range within a tenant; adding a suffix does not automatically guarantee load balance.

### 6.3. How does query routing change?

Before refinement:

```javascript
db.orders.find({ tenantId: "T1" });
```

could typically be routed to a specific tenant key range. After refinement, a `tenantId` filter is still a **prefix**, so MongoDB can use it to narrow the range, though the tenant may become spread across multiple chunks/shards.

The query:

```javascript
db.orders.findOne({
  tenantId: "T1",
  orderId: "O-101"
});
```

includes the **full new key**, helping the router pinpoint the range more accurately. To see how many shards are actually touched, run `explain()` on a representative workload rather than guessing from index names.

### 6.4. Limits of refinement with very large tenants

If the new requirement is to distribute a massive tenant's writes while balancing across shards, refining to `{tenantId,orderId}` may help, yet it still keeps tenant as the leading field. If the workload mainly generates monotonically increasing keys within each tenant, consider whether a hashed key or another shard key design solves the issue better.

If `tenantId` must be removed from the start of the key, refine **cannot** perform that change. Compare the benefits of **resharding** against the cost of increased fanout for tenant-scoped queries.

## 7. Resharding: genuinely changing the shard key

### 7.1. Why is resharding needed?

Common reasons:

- The initial shard key has low cardinality.
- A few key values account for most of the storage or traffic.
- The application's dominant query pattern has changed.
- A monotonically increasing key causes write hotspots.
- Zone or geographic residency strategy is redesigned.
- You want to switch from range to hashed or change field ordering.
- You need to replace the old shard key where appending a suffix is not enough.

Resharding moves the collection into a **new shard key space**. It can substantially change document placement, chunk counts, the number of shards queried, and operation performance.

### 7.2. Basic syntax

MongoDB has supported **reshardCollection** since the **5.0** release series. Example in `mongosh`:

```javascript
sh.reshardCollection(
  "sales.orders",
  { orderId: "hashed" }
);
```

Or the supported command form:

```javascript
db.adminCommand({
  reshardCollection: "sales.orders",
  key: { orderId: "hashed" }
});
```

This is a **high-impact DDL command**, not an example to run casually on a live collection. Namespace, new key, privileges, feature conditions, and optional parameters must be verified for your server version.

### 7.3. Changes that cannot be done with refine

| Current shard key | Desired key | Can refine? | Direction to explore |
| --- | --- | --- | --- |
| `{tenantId:1}` | `{tenantId:1,orderId:1}` | Structurally yes; still requires meeting conditions | Refine |
| `{tenantId:1}` | `{orderId:1}` | No | Reshard |
| `{tenantId:1}` | `{orderId:"hashed"}` | No | Reshard |
| `{regionId:1,tenantId:1}` | `{tenantId:1,regionId:1}` | No | Reshard |
| `{tenantId:1,orderId:1}` | `{tenantId:1}` | No; refine does not remove suffixes | Reshard or redesign |
| `{tenantId:1}` | `{regionId:1,tenantId:1}` | No; prepends a prefix rather than appending a suffix | Reshard |

Marking "Reshard" in the table is not a guarantee that any new key will be accepted by the server: you still must check **support conditions, unique indexes, collection type, data, and resources**.

### 7.4. Conceptual phases of resharding

An online resharding process typically includes:

```text
Application continues reads/writes (with caveats)
                     |
                     v
       Prepare / initialize metadata
                     |
                     v
      Copy existing data to new layout
                     |
                     v
       Catch up writes during copying
                     |
                     v
      Final commit / critical section
                     |
                     v
        New shard key becomes active
                     |
                     v
            Cleanup old layout
```

This is a **conceptual diagram**, not a fixed list of internal state names across all releases. Depending on version, MongoDB uses different donor/recipient mechanisms, temporary collections, oplog application, and commit coordination.

The crucial point is that resharding:

- Reads/copies the existing data volume.
- Tracks ongoing writes occurring during the copy.
- Must switch to the new layout at a consistent point in time.
- May involve a **critical section** during which some operations are temporarily blocked or delayed.
- Needs rollback/abort capability for the resharding operation itself before commit within version-supported boundaries.

Therefore, "online resharding" **does not mean zero-cost or guaranteed zero interruption** for every workload.

### 7.5. After resharding, the application must use the new key

If the key changes from:

```javascript
{ tenantId: 1 }
```

to:

```javascript
{ orderId: "hashed" }
```

then `find({tenantId:"T1"})` may have to reach **multiple shards** if it lacks the new shard key field, whereas `find({orderId:"O-101"})` can target more efficiently.

Reducing a write hotspot may come with higher tenant-query costs. You need to:

- Update critical query patterns.
- Review indexes serving tenant queries after resharding.
- Update updates/deletes/upserts requiring targeted routing per your version.
- Adjust telemetry and runbooks for the new shard key.
- Test on both read and write workloads, not just inserts.

## 8. Support conditions for resharding

### 8.1. Server version and FCV

Resharding was introduced in MongoDB **5.0**, with ongoing improvements and revised limits in subsequent releases.

Before using it:

1. Identify the versions of **`mongos`, config servers, and all shard replica sets**.
2. Check the **cluster's FCV**.
3. Verify whether an upgrade/downgrade is in progress.
4. Identify whether the deployment is self-managed or a managed service.
5. Verify that the version supports resharding that collection/namespace type.
6. Check release-specific behavior for write blocking duration, state recovery, abort/commit, zones, and reshard options.

Do not apply MongoDB 8.x instructions verbatim to a 5.x cluster, or vice versa.

### 8.2. The collection and new key must be valid

The collection must be sharded and in a state permitting the operation. The new shard key must satisfy limits regarding:

- Supported field types and index types.
- Not using invalid shard key fields such as arrays under multikey restrictions.
- Handling of missing fields, `null`, legacy data, and collation.
- Existing unique constraints or collection uniqueness requirements.
- Zone ranges and distribution policies.
- Hashed/ranged properties of the key.
- Version-specific restrictions on time-series, special collections, views, or other namespace types.

A syntactically valid key can still perform **very poorly**. For example, `status` with only three values is a low-cardinality shard key that rarely yields effective data distribution.

### 8.3. Unique indexes are architectural constraints

Suppose the collection currently has a unique index:

```javascript
{ tenantId: 1, externalOrderId: 1 }
```

and the product requires **order codes to be unique per tenant**.

The operations team wants to reshard on:

```javascript
{ regionId: 1 }
```

The old unique index does not have the new shard key `regionId` as a prefix. Under sharded collection uniqueness limits, this plan is **incompatible unless the invariant and appropriate indexes are resolved**.

Options:

- Choose a new key that can still represent the uniqueness to be protected.
- Adjust the unique scope if the product permits, with an explicit migration.
- Use a **registry/proxy collection** with an appropriate unique index to enforce the global business key.
- Keep the collection on the old key or split the data model instead of resharding purely for distribution.

**Never drop a unique index just to get past a DDL command and hope the application catches all duplicates under concurrent writes.** That trades away data correctness.

### 8.4. Does lacking a new shard key index matter?

Requirements around pre-created indexes, server-created indexes during transition, and related options **differ by version and reshard type**. Never blindly assume "reshard always creates every index automatically" or "you must create the index first" without verification.

Before production:

- List existing indexes and related hidden/unique indexes.
- Identify which new shard key index your version requires.
- Evaluate the duration and impact of index builds on each shard.
- Measure the additional write overhead of the new index.
- Test preflight commands and error messages on a staging cluster running the same version.

At minimum, plan **indexes serving queries after resharding**, even if the DDL operation can prepare the base shard key index automatically.

### 8.5. Zones and placement

If the collection uses **zone sharding**, resharding must check:

- Which regions/tiers must reside on which shards?
- Are the new zone ranges compatible with the new key?
- Do zone ranges need to be supplied to the operation in supported versions?
- Can data temporarily appear on other recipient shards during the transition, and would that violate residency requirements?
- Is cross-region bandwidth/data transfer constrained?

Residency policies are **security and compliance requirements**, not merely performance requirements. If data must remain within a specific region, obtain review from the data owner before resharding.

### 8.6. DDL, balancer, and ongoing cluster activity

Resharding can interact with:

- Chunk migrations / the balancer.
- Other DDL operations (create/drop/rename/index).
- Long-running transactions.
- Oplog retention and replication lag.
- Backups/PITR, change streams, and cluster resources.
- Metadata updates in config servers.

Depending on the version, some operations are coordinated automatically, some are blocked, and some are unsupported while resharding is running. Do not assume you can run arbitrary concurrent DDL simply because the cluster remains online for reads/writes.

## 9. Why does resharding require heavy resources?

### 9.1. Data copying and network

Resharding must construct a new data distribution according to the new shard key. If a large fraction of documents changes location, the cluster must transfer data over the network and write it onto recipient shards.

Illustrative example:

```text
Collection size:       2 TiB
Current distribution:  Shard A 1.3 TiB
                       Shard B 0.4 TiB
                       Shard C 0.3 TiB

Proposed new key:      { orderId: "hashed" }
```

You cannot estimate reshard duration simply as 2 TiB / theoretical bandwidth. Total cost also depends on:

- How much data actually needs copying.
- Shard read/write speeds.
- Network and disk IOPS.
- Index builds.
- Transactions / majority commit overhead.
- Write rate during resharding and catch-up backlog.
- Chunk placement and temporary resources.

### 9.2. Temporary storage capacity

The transition process may require **extra storage** to hold the new distribution/dataset copy and related temporary structures before old data is cleaned up.

Therefore, never reshard when shards are nearly out of disk space. Plan capacity for **peak disk usage**, including indexes, oplog, and a safety margin for active work.

Fixed rules of thumb like "you only need 10% extra" or "you always need double on every shard" can both be wrong. Calculate headroom based on the **projected new distribution, per-shard sizes, version, and actual workflow**.

### 9.3. CPU, cache, oplog, and replication

Resharding must scan/copy documents, apply concurrent writes, and build related structures. It competes with application workloads for:

- CPU for BSON processing, routing, and indexing.
- WiredTiger cache.
- Disk reads/writes and checkpoints.
- Inter-shard network bandwidth.
- Oplog replication throughput and secondary catch-up capacity.
- Transaction or DDL coordinator resources.

If the write rate is very high, the change backlog needing catch-up can be large; resharding may therefore take longer or put pressure on secondaries.

### 9.4. Critical section and user latency

Even when the system supports **online resharding**, the final phase of switching over may require a coordination window during which some reads/writes or DDL are blocked/queued.

Application-level consequences can include:

- Increased P99 latency.
- Elevated server selection / command timeouts.
- Some transactions needing retries.
- Temporary throughput drops.
- Operation log / monitoring recording transition states.

This is why the runbook needs **defined SLOs**, deployment windows, rollback/abort criteria, and assigned owners—not just running a command and waiting.

## 10. How do refine and reshard impact queries?

### 10.1. Targeted queries vs. scatter-gather

MongoDB `mongos` tries to send queries to the appropriate shards based on the shard key and query predicates. If it cannot narrow down the key range, the router may have to send the query to multiple shards.

Example after resharding to `{orderId:"hashed"}`:

```javascript
// Contains the new shard key; can be targeted.
db.orders.findOne({ orderId: "O-100" });

// Only has tenantId; may scatter-gather.
db.orders.find({ tenantId: "T1" });
```

If 90% of traffic is still "list orders for tenant T1", the new key can force most queries across multiple shards, increasing network and merge costs.

Do not focus only on write distribution; query fanout can cost more than the write gains.

### 10.2. Shard key index vs. query-serving indexes

A collection sharded by `orderId` can still have an index:

```javascript
{ tenantId: 1, createdAt: -1 }
```

to speed up tenant queries *on each individual shard*. However, this index **does not help the router know which shard holds a tenant** if the query lacks the shard key. The query may still fan out, only each shard reads its local data more efficiently.

Distinguish between:

- **Shard key**: determines distribution and routing.
- **Secondary indexes**: speed up queries on the involved shards.

Simply adding an index does not turn a query missing the shard key into a targeted query.

### 10.3. Write routing, upserts, and single-document operations

After changing the shard key, operations such as:

```javascript
updateOne(...)
deleteOne(...)
findOneAndUpdate(...)
upsert: true
```

may have different routing requirements depending on the MongoDB version and query filter. In particular, upserts may require shard key information or exhibit newer behaviors in recent releases.

Before resharding, check **every write path**, not just read queries:

1. Does the API know the new shard key?
2. Does the filter contain enough fields to target under the version's rules?
3. If the key field is absent, is the operation supported or must it scatter across multiple shards?
4. Do unique indexes prevent duplicates during concurrent upserts?
5. Are there data-import scripts or background workers using old filters?

**Do not guess routing rules from examples written for another version.** MongoDB has evolved update/upsert support on sharded collections over time.

### 10.4. Modifying shard key values in documents is a different problem

MongoDB has capabilities for updating the **value** of a shard key on a document subject to version conditions and limits. However, that is **neither refining a shard key nor resharding**:

- Updating a shard key value: changes a field on **a single document**.
- Refine: changes the **shard key definition** by appending a suffix.
- Reshard: changes the **definition and collection distribution** according to a new key.

Do not run `updateMany` to alter a shard key field and treat the collection as resharded.

## 11. Designing a preflight plan before changing keys

### 11.1. Step 1: describe the problem with metrics

For example:

```text
P95 list-orders latency:        280 ms
P99 list-orders latency:        2.4 s
Shard A write utilization:      92%
Shard B write utilization:      35%
Shard C write utilization:      28%
Tenant T1 share of writes:      64%
Scatter-gather share:           18%
```

These numbers are **hypothetical data** illustrating how to state the problem. A plan might aim to:

- Reduce hot-shard write utilization.
- Balance data size/chunks.
- Keep P95/P99 query latency within SLO.
- Reduce scatter-gather.
- Preserve uniqueness and residency invariants.

Without a baseline, it is hard to tell after the change whether resharding helped or hurt the system.

### 11.2. Step 2: evaluate candidate shard keys

For each candidate:

```javascript
{ tenantId: 1, orderId: 1 }
{ orderId: "hashed" }
{ regionId: 1, tenantId: 1 }
```

ask:

- Cardinality?
- Value frequency skew?
- Monotonicity/hotspots?
- Do common queries include the corresponding fields?
- Are many documents missing key fields?
- Existing unique constraints?
- Do any key fields mutate frequently?
- Are zones/residency needed?
- Estimated chunk sizes / data movement?

In supported MongoDB versions, the **`analyzeShardKey`** command and query sampling can help evaluate candidate keys against the workload. Check release-specific usage, privileges, and syntax; do not treat analysis results as a guaranteed proof of post-migration performance.

### 11.3. Step 3: inspect data structure

Example inspecting a specific collection:

```javascript
const sales = db.getSiblingDB("sales");

// Note: can be resource-intensive on large collections;
// run only after evaluating scope and cost.
const sample = sales.orders.find(
  {},
  {
    _id: 1,
    tenantId: 1,
    orderId: 1,
    regionId: 1
  }
).limit(20).toArray();

printjson(sample);
```

Check the rate of missing `orderId` using a sample aggregation:

```javascript
sales.orders.aggregate([
  { $sample: { size: 1000 } },
  {
    $group: {
      _id: { $type: "$orderId" },
      documents: { $sum: 1 }
    }
  },
  { $sort: { documents: -1 } }
]);
```

`$sample` is an initial exploration technique and **does not guarantee finding every malformed document**. For production decisions, inspect the full dataset using an appropriate workflow with schema statistics and counts of legacy documents.

Do not modify real data merely to "populate missing fields" without an agreed business contract.

### 11.4. Step 4: check metadata and indexes

In `mongosh` with appropriate privileges:

```javascript
sh.status();

const sales = db.getSiblingDB("sales");
printjson(sales.orders.getIndexes());
```

DBAs can inspect config collection metadata and distribution using version-supported tools/commands. Never edit `config` collections directly to change a shard key.

Focus on answering:

- What pattern is the collection currently sharded on?
- What unique indexes exist?
- Which index supports the refined key?
- What zone ranges exist?
- Are there jumbo chunks / hot ranges?
- Is the cluster currently running resharding or other DDL?

### 11.5. Step 5: resource and SLO conditions

Before resharding:

- Sufficient **disk headroom on every recipient**.
- Adequate inter-shard network bandwidth for data movement.
- Healthy replica sets with safe oplog window / replication lag.
- No conflicting backups, migrations, or large index builds scheduled.
- Observability for progress, errors, and duration.
- Runbook for timeout/abort/recovery.
- Checkpoints to verify the application functions properly after switchover.

Refining involves less data movement yet still requires preflight: large index builds consume I/O; metadata updates and constraint checks can cause the operation to fail.

## 12. Hands-on refine on a test sharded cluster

### 12.1. Safe scope

**Requirements:** a **dedicated test sharded cluster**, `mongosh` connected to `mongos`, and `shardCollection`/`createIndex`/`refineCollectionShardKey` privileges. Do not run this DDL on production or shared staging clusters just to learn.

Test database name:

```text
mongo_shardkey_row266_lab
```

If the database/collection already exists with someone else's data, **do not reuse it**; choose an isolated authorized test environment, and do not drop namespaces yourself to reset them.

### 12.2. Connect to `mongos`

```bash
mongosh "mongodb://mongos.example.internal:27017/"
```

The URI is a placeholder: substitute hostname/TLS/authentication for your environment.

```javascript
sh.status();
printjson(db.adminCommand({ hello: 1 }));
```

Verify you are connected to the router of the test sharded cluster. If privileges are missing, stop before running DDL.

### 12.3. Prepare an empty demo collection

Run only when you are sure the namespace does not exist and belongs to you:

```javascript
const lab = db.getSiblingDB("mongo_shardkey_row266_lab");
const name = "orders_refine_demo";

if (lab.getCollectionNames().includes(name)) {
  throw new Error("Namespace already exists; do not overwrite the test.");
}

lab.createCollection(name);
const orders = lab.getCollection(name);

// Index supporting the initial shard key.
orders.createIndex(
  { tenantId: 1 },
  { name: "tenant_shard_key" }
);

// Shard the collection while empty.
sh.shardCollection(
  "mongo_shardkey_row266_lab.orders_refine_demo",
  { tenantId: 1 }
);
```

Some environments/versions may automatically create the supporting index when sharding an empty collection; the snippet above creates it explicitly to teach the structure. Do not assume every DDL error is caused by a missing index: permissions, FCV, namespace, and cluster state also apply.

### 12.4. Insert documents specific to this lab run

```javascript
const runId = "row266-" + new ObjectId().toHexString();
const tenantA = runId + "-T1";
const tenantB = runId + "-T2";

const docs = [
  {
    _id: new ObjectId(),
    runId,
    tenantId: tenantA,
    orderId: "O-100",
    status: "NEW"
  },
  {
    _id: new ObjectId(),
    runId,
    tenantId: tenantA,
    orderId: "O-101",
    status: "PAID"
  },
  {
    _id: new ObjectId(),
    runId,
    tenantId: tenantB,
    orderId: "O-200",
    status: "PAID"
  }
];

printjson(orders.insertMany(docs));
printjson(orders.find({ runId }).toArray());
```

Three documents are not enough to measure sharding performance or demonstrate balancing. The goal is to illustrate changing the **shard key definition**, not to benchmark chunk distribution.

### 12.5. Create the supporting index for the refined key

```javascript
printjson(orders.getIndexes());

orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { name: "tenant_order_refined" }
);
```

Create the index first to satisfy the key precondition for refine. With real data, index builds consume resources and should be scheduled separately.

### 12.6. Perform the refinement

```javascript
sh.refineCollectionShardKey(
  "mongo_shardkey_row266_lab.orders_refine_demo",
  { tenantId: 1, orderId: 1 }
);
```

If the cluster/test version is compatible and all conditions are satisfied, the collection's shard key metadata transitions to the compound key with the `orderId` suffix.

**Do not** expect after the command:

- The three demo documents to immediately sit on three different shards.
- Chunks to immediately rebalance.
- Query speed to automatically improve.
- A unique index to be added automatically.
- Documents missing `orderId` to be automatically fixed according to business rules.

### 12.7. Observe after refinement

```javascript
sh.status();
printjson(orders.getIndexes());

// Query with the full refined key.
printjson(
  orders.findOne({
    tenantId: tenantA,
    orderId: "O-101"
  })
);

// Query with only the old prefix remains valid.
printjson(
  orders.find({ tenantId: tenantA }).toArray()
);
```

If you want to inspect the routing plan:

```javascript
printjson(
  orders.find({
    tenantId: tenantA,
    orderId: "O-101"
  }).explain("queryPlanner")
);
```

The displayed plan may vary by version and chunk distribution. With three documents, you cannot conclude that the new key is better for real workloads.

### 12.8. Safely clean up demo documents

Only when sure `runId` and the `docs` list match this test run:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);

const owned = orders.find(
  { runId },
  { _id: 1, tenantId: 1, orderId: 1, runId: 1 }
).toArray();

printjson(owned);

for (const doc of owned) {
  const result = orders.deleteOne({
    _id: doc._id,
    tenantId: doc.tenantId,
    orderId: doc.orderId,
    runId
  });
  print(doc.orderId + ": deleted=" + result.deletedCount);
}

print("remaining=" + orders.countDocuments({ runId }));
```

Deleting the documents **does not undo the refinement**. The collection, indexes, and sharding metadata remain. If you need to reclaim the test cluster namespace, follow the authorized environment's DDL procedure and confirm no one else is using it. **Do not run `dropDatabase()` or edit `config` collections directly to clean up examples.**

## 13. Hands-on resharding: preparing a separate collection

### 13.1. Do not test resharding on refined collections shared with others

Because resharding can move data and temporarily affect reads/writes, this section is only an **optional exercise** on an isolated sharded cluster with spare capacity and no real application traffic.

You do not have to run `reshardCollection` to learn the concepts; reading the phases and preflight planning is sufficient when an isolated environment is unavailable.

### 13.2. Create a separate demo collection

```javascript
const lab = db.getSiblingDB("mongo_shardkey_row266_lab");
const reshardName = "orders_reshard_demo";

if (lab.getCollectionNames().includes(reshardName)) {
  throw new Error("Reshard demo namespace already exists.");
}

lab.createCollection(reshardName);
const reorders = lab.getCollection(reshardName);

reorders.createIndex(
  { tenantId: 1 },
  { name: "tenant_key" }
);

sh.shardCollection(
  "mongo_shardkey_row266_lab.orders_reshard_demo",
  { tenantId: 1 }
);

const reshardRunId = "row266-reshard-" + new ObjectId().toHexString();

reorders.insertMany([
  {
    _id: new ObjectId(),
    runId: reshardRunId,
    tenantId: reshardRunId + "-T1",
    orderId: "O-301",
    status: "NEW"
  },
  {
    _id: new ObjectId(),
    runId: reshardRunId,
    tenantId: reshardRunId + "-T2",
    orderId: "O-302",
    status: "PAID"
  }
]);
```

There is no secondary unique index on `{tenantId, orderId}` in this example to avoid adding another invariant requiring evaluation when resharding to a new key. In production, unique indexes are a mandatory part of preflight and must not be ignored.

### 13.3. Switch to a hashed shard key

After confirming cluster/FCV support and following the test environment's DDL procedure:

```javascript
sh.reshardCollection(
  "mongo_shardkey_row266_lab.orders_reshard_demo",
  { orderId: "hashed" }
);
```

Unlike refine, this command requests **switching to hash-based distribution on `orderId`**. With small datasets, the entire operation may complete quickly without exposing production costs; with large collections, the cost can be substantial.

Do not expect this operation to modify the values of `tenantId` or `orderId` inside documents. It changes **how the collection is sharded**.

### 13.4. Inspect and clean up demo data

```javascript
sh.status();
printjson(reorders.getIndexes());

printjson(
  reorders.find({ runId: reshardRunId }).toArray()
);
```

When cleaning up records:

```javascript
const owned = reorders.find(
  { runId: reshardRunId },
  { _id: 1, runId: 1, orderId: 1 }
).toArray();

printjson(owned);

for (const doc of owned) {
  printjson(
    reorders.deleteOne({
      _id: doc._id,
      orderId: doc.orderId,
      runId: reshardRunId
    })
  );
}

print("remaining=" + reorders.countDocuments({
  runId: reshardRunId
}));
```

Sharding metadata and the collection still exist after deleting documents. Do not treat cleaning up data as undoing resharding; reclaiming DDL resources must be performed by cluster administrators under a separate runbook.

## 14. Keeping the application safe during shard key changes

### 14.1. Inventory read and write paths

Suppose a service has these flows:

```text
GET /tenants/:tenantId/orders
GET /orders/:orderId
PATCH /orders/:orderId/status
POST /orders
Worker: sync order state
Worker: expire old orders
Job: monthly reporting
```

For each flow:

- Does the filter contain the old/new shard key?
- Will the query become scatter-gather after the change?
- Are upserts properly targeted and deduplicated via unique indexes?
- Does it rely on the old key's order/fields for sorting and pagination?
- Are downstream jobs reading data via old pipelines?
- Does auth/tenant scoping need updates when the new key no longer starts with tenant?

A reshard intended to speed up `GET /orders/:orderId` can slow down `GET /tenants/:tenantId/orders` many times over if you change the key without redesigning queries.

### 14.2. Compatibility across deployed application versions

In practice, multiple application versions may run simultaneously during a rolling deployment.

Plan for:

1. Can the older version still write valid data once the shard key is refined?
2. Do new requests include the required suffix fields?
3. After resharding, might older code emit suboptimal or restricted queries?
4. Are data migrations and application deployments sequenced properly?
5. Are there feature flags to switch routing/query patterns when metadata flips?

Do not run DDL only to discover afterward that an older worker uses filters lacking the new shard key.

### 14.3. Unique keys and concurrent upserts

Suppose order codes must be unique per tenant:

```javascript
{
  tenantId: "T1",
  externalOrderId: "E-100"
}
```

If the new shard key is incompatible with the unique index `{tenantId, externalOrderId}`, concurrent upsert requests can compromise correctness or cause DDL rejection.

There is no "use upsert and hope MongoDB never creates duplicates" solution when an appropriate unique constraint is missing. You must align **routing + business uniqueness + idempotency** before changing the key.

### 14.4. Change streams and data consumers

If the application uses change streams, Debezium, or other synchronization tools, verify limits and resume behavior during resharding for your MongoDB version.

Do not assume every resume token, transaction, or tailing workflow is unaffected across all releases. Prepare by:

- Saving checkpoints.
- Monitoring errors/resumes and backlog.
- Having restart/reconciliation capability.
- Monitoring the oplog window during the operation.

If a critical consumer breaks during migration, resharding succeeding by itself does not mean the application ecosystem is safe.

## 15. Production rollout process: from design to verification

### 15.1. Phase A — Design and review

- Specify the pain point and target KPIs to improve.
- Collect candidate shard keys.
- Analyze cardinality, skew, growth, hotspots, and query routing.
- Classify whether the requirement calls for **refine** or **reshard**.
- Inventory unique constraints, zones, and data characteristics.
- Review with DBA/SRE, application teams, and business owners.

The output should be a **measured architectural decision**, not just a `mongosh` command.

### 15.2. Phase B — Staging/preflight

- Stand up an environment matching version/FCV/topology.
- Use representative data and load ratios, with sensitive data protected.
- Check supporting indexes and legacy data issues.
- Test all read/write paths.
- Run tests covering updates, upserts, transactions, and unique conflicts.
- Measure duration, peak disk, network, CPU, and latency.
- Identify DDL/zone constraint risks.

Do not extrapolate production performance from an example with a few documents on a test cluster.

### 15.3. Phase C — Preparing rollback/abort

For **refine**:

- There is no simple "remove suffix" operation to revert to the old shard key.
- Plan query/index fixes if performance degrades.
- If the old key is truly needed again, evaluate resharding or the appropriate recovery plan.

For **reshard**:

- Understand abort capabilities while the operation is **not yet committed**, per your version.
- After committing to the new key, do not assume an instant "undo" syntax exists.
- Recovery may require **another resharding**, application changes, or runbook-based restoration.
- Backups are essential data protection, not an instant shard-key architecture rollback when the system is taking continuous writes.

Clearly define **before/during/after commit** boundaries to avoid taking the wrong abort/rollback action.

### 15.4. Phase D — Monitored rollout

Monitor:

| Metric | Why it must be observed |
| --- | --- |
| Resharding or refine DDL progress/state | Know where the operation stands and whether errors occur |
| Per-shard CPU/disk/cache | Detect resource bottlenecks |
| Donor/recipient disk headroom | Avoid running out of disk midway |
| Network throughput | Assess data movement and backlog |
| Oplog window/replication lag | Ensure secondaries keep up |
| P95/P99 read/write latency | Verify application SLOs |
| Error rate and timeouts | Detect client impact |
| Chunk/range distribution | Inspect actual distribution after change |
| Scatter-gather and targeted query share | Verify routing matches expectations |
| Unique conflicts/data correctness | Ensure invariants are not broken |

Set up alerts and assign incident responders before starting.

### 15.5. Phase E — Post-cutover verification

Do not check only whether "the DDL command returned success." You must:

1. Confirm the **new shard key metadata**.
2. Confirm the application continues reading/writing data accurately.
3. Verify data and business keys to an appropriate extent.
4. Inspect representative query plans.
5. Measure per-shard data/traffic distribution.
6. Verify replication lag and cache/disk stability.
7. Confirm consumers, backups, and change streams continue working.
8. Declare the goal achieved only when KPIs improve over time post-migration.

For refine, you may need to observe the balancer/chunk distribution for a period afterward because a metadata change **does not imply immediate physical redistribution**.

## 16. Common issues and troubleshooting

| Symptom | Likely cause | Remediation |
| --- | --- | --- |
| Refine reports no supporting index | Missing valid supporting index matching pattern | Create/verify valid index in the appropriate environment |
| Refine reports invalid new key | Missing old prefix, reordered fields, or changed key type | Use suffix-only or evaluate reshard |
| Refine fails due to uniqueness | Unique index incompatible with refined key | Redesign invariant/index before DDL |
| Refine succeeds but data remains skewed | Refine does not immediately redistribute data | Observe chunk/balancer behavior, evaluate placement |
| Tenant queries slower after refine | Tenant spread across chunks/shards, query lacks suffix | Inspect routing/indexes and workload |
| Reshard fails at preflight | Incompatible key/namespace/FCV/index/zone | Read error message and consult version-specific docs |
| Reshard takes too long | Large data, write churn, disk/network bottleneck | Measure progress, capacity, backlog; pick appropriate window |
| Reshard increases latency | Copy/commit coordination/critical section | Monitor and throttle/manage load per runbook |
| Writes time out during transition | Routing/topology/critical phase or load issues | Handle driver errors/idempotency; avoid unbounded retries |
| Heavy scatter-gather after reshard | Queries still rely on old key | Update queries, indexes, and/or revisit key selection |
| Hotspot still persists | New key is skewed/monotonic or single-document contention | Analyze distribution, contention, and cardinality |
| Secondary lag rises | Write load / reshard data movement | Monitor oplog window, disk/network, and capacity |
| Data residency violates expectations | Zones/placement not configured properly | Review zone ranges and compliance rules |
| Legacy data missing suffix | Poor key cardinality or version-dependent errors | Controlled migration and schema validation |
| Trying to "undo" refine with `dropIndex` | An index is not shard key metadata | Do not do this; plan resharding or remediation |
| Trying to "undo" reshard with `shardCollection` | Wrong operation type | Follow recovery/re-reshard runbook |

## 17. Dangerous misconceptions

### 17.1. "Refine can change any shard key"

False. Refine only **appends a suffix**; it does not remove, reorder, or alter old components. To get a fundamentally different key, evaluate resharding.

### 17.2. "Right after refine, data is immediately balanced"

False. Updating metadata is not equivalent to instant physical redistribution. A longer key enables finer splitting, but actual distribution must be measured.

### 17.3. "Resharding is online so it won't affect the application"

False. Online resharding still incurs costs for data copying, indexing, oplog application, commit coordination, and potential blocking/waiting in the final phase. Real impact depends on version and workload.

### 17.4. "Changing the shard key just means adding an index"

False. An index is a query structure, whereas the shard key is collection metadata/routing. You need the proper refine/reshard command.

### 17.5. "Just picking hashed eliminates hotspots"

Not necessarily. Hashing can scatter distinct values, but it does not solve two writers contending on **the same document**, does not enforce uniqueness, and can increase fanout for range/tenant queries.

### 17.6. "Replacing unique `{tenantId,orderId}` with unique `{tenantId,month,orderId}` preserves business semantics"

False. Those two unique keys protect different scopes. Adding `month` allows the same `orderId` to repeat across different months within a tenant. Define business invariants first.

### 17.7. "Reshard is a backup and rollback mechanism"

False. Resharding changes distribution structure, not backup state. After commit, reverting may require another reshard operation or a planned recovery.

### 17.8. "One shard having more data means the shard key is wrong"

You cannot conclude that from data size alone. Inspect data size, chunk distribution, read/write hotspots, workload, balancer health, and per-shard capacity. Sometimes one shard is larger intentionally due to zone placement or hardware differences.

### 17.9. "After resharding, all old queries still target a single shard"

False. Query routing depends on the **new key**. Queries providing only the old shard key may fan out; check `explain`/monitoring after migration.

### 17.10. "Backfilling the orderId field into every document is refining"

False. That is just a **data migration**. Refining must update the shard key metadata via the supported command.

## 18. Practice questions and design exercises

### Exercise A. Identify the appropriate operation

Given the current key:

```javascript
{ tenantId: 1, regionId: 1 }
```

Classify each desired key as **structurally a refine**, **requires resharding**, or **requires checking other constraints**:

```javascript
// A
{ tenantId: 1, regionId: 1, orderId: 1 }

// B
{ regionId: 1, tenantId: 1 }

// C
{ tenantId: 1 }

// D
{ tenantId: 1, regionId: 1, orderMonth: 1, orderId: 1 }

// E
{ tenantId: "hashed", regionId: 1 }
```

Hint: A and D preserve the entire old prefix and append a suffix; B/C/E are not refines.

### Exercise B. A large tenant overloads one shard

A collection is currently sharded by `{tenantId:1}`. Tenant T1 accounts for 70% of writes, while 90% of read queries are:

```javascript
db.orders.find({
  tenantId: "T1",
  status: "PAID"
}).sort({ createdAt: -1 });
```

Evaluate:

1. What benefit does refining to `{tenantId:1,orderId:1}` bring?
2. How might it affect queries filtering only by tenant?
3. How might resharding to `{orderId:"hashed"}` affect read routing?
4. Which KPIs should be measured before and after?
5. If `{tenantId:1,externalOrderId:1}` is unique, how does that constrain changing the key?

### Exercise C. Unique business ID and resharding

The application requires each `externalOrderId` to **appear only once per tenant across all months**. Proposed new key:

```javascript
{ tenantId: 1, monthBucket: 1 }
```

A developer proposes a unique index:

```javascript
{ tenantId: 1, monthBucket: 1, externalOrderId: 1 }
```

Explain why this index **does not enforce the cross-month invariant**, even though it has the shard key as a prefix. Propose at least one design that preserves the invariant, such as a different key or a registry collection with an appropriate unique key.

### Exercise D. Refine completes, but distribution does not change

After `refineCollectionShardKey`:

```text
Shard A: 800 GB
Shard B: 120 GB
Shard C:  90 GB
```

Answer:

- Is this enough to conclude that refine failed?
- Why does changing shard key metadata not imply immediate data copying?
- Which chunk/range distribution, balancer, and workload metrics should be inspected?
- When should resharding or cluster capacity expansion be considered?

### Exercise E. Resharding during peak hours

A cluster holds 2 TiB of data, replication lag is rising, disk free space on one shard is down to 12%, and a backup is about to start. The team wants to reshard immediately to alleviate a hotspot.

List:

- What are the capacity/latency/retention risks?
- Which conditions warrant postponing?
- What metrics must be collected before deciding?
- Should `reshardCollection` be treated as "zero downtime"?
- How should the runbook define pre-commit abort vs. post-commit handling?

### Exercise F. Application lifecycle

The system runs a rolling update involving two service versions:

```text
Service v1: updateOne({_id, tenantId}, ...)
Service v2: updateOne({_id, tenantId, orderId}, ...)
```

The collection is about to be refined from `{tenantId:1}` to `{tenantId:1,orderId:1}`.

Analyze router conditions, targeted operations, uniqueness, and compatibility by **MongoDB version**. Why must both v1 and v2 be tested during deployment rather than testing only the new service?

## 19. Official references

Support conditions are sensitive to MongoDB version and deployment type. Before making production changes, consult the documentation for the exact **running release/FCV**:

- [Shard Keys — MongoDB Manual](https://www.mongodb.com/docs/manual/core/sharding-shard-key/) — role and selection of shard keys.
- [Refine a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-refine-a-shard-key/) — refinement process and limitations.
- [refineCollectionShardKey command](https://www.mongodb.com/docs/manual/reference/command/refineCollectionShardKey/) — command syntax and requirements.
- [sh.refineCollectionShardKey()](https://www.mongodb.com/docs/manual/reference/method/sh.refineCollectionShardKey/) — `mongosh` helper.
- [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/) — resharding process and considerations.
- [reshardCollection command](https://www.mongodb.com/docs/manual/reference/command/reshardCollection/) — syntax, options, and version limits.
- [sh.reshardCollection()](https://www.mongodb.com/docs/manual/reference/method/sh.reshardCollection/) — resharding helper.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — unique indexes across data models.
- [Sharding Analyze Shard Key](https://www.mongodb.com/docs/manual/core/sharding-analyze-shard-key/) — analyzing candidate keys and workloads in supported versions.
- [Zone Sharding](https://www.mongodb.com/docs/manual/core/zone-sharding/) — zone-based placement rules.
- [Sharding Production Considerations](https://www.mongodb.com/docs/manual/core/sharded-cluster-requirements/) — operational and topology requirements by release.

## 20. Conclusion

Both **refining a shard key** and **resharding** help MongoDB adapt as workloads evolve, but they are not interchangeable. Refining **preserves the entire old shard key and only appends a suffix**, requiring a supporting index as well as data and uniqueness conditions; it updates metadata without **immediately redistributing all existing documents**. Resharding lets you pick a **new shard key** and reorganize data, at the cost of data copying, indexing, oplog overhead, resources, and potential latency impact during the transition.

To choose correctly, start from **performance goals and business invariants**: will the new key actually reduce skew/hotspots, will queries suffer more scatter-gather, will unique indexes and zone constraints remain valid, and is the application compatible? Before any change, verify **MongoDB version, FCV, collection type, supporting indexes, legacy data, cluster capacity, and runbooks**. Even after the command succeeds, continue measuring distribution, routing, replication, and data correctness.

**Core principle:** only *refine* when you can preserve the old prefix and append a suffix; use *resharding* when you must change the nature of the shard key itself, and always treat this as a verified architectural decision rather than an isolated DDL command.
