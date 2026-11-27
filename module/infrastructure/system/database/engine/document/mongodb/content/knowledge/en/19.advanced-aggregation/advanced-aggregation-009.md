# Writing Results with `$out`, `$merge`, and Controlling Target Data Impact in MongoDB

## 1. Problem: Aggregation Results Can Become Stored Data

The aggregation pipeline is commonly introduced as a tool for **reading, filtering, transforming, and summarizing documents**:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$channel",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  }
]);
```

This pipeline returns aggregated documents to the application. In practice, however, many systems want to **persist the aggregated results** to power dashboards, reports, or downstream jobs:

- Recompute daily revenue tables by date and sales channel each night.
- Write normalized data into a dedicated lookup collection.
- Add or update metrics for one day without overwriting metrics for other days.
- Replace an entire reporting collection after a full recalculation.
- Merge results from a source into an existing collection by business key.

MongoDB provides two **write-output aggregation pipeline stages**:

- **`$out`**: writes the entire pipeline output to a target collection; if the target already exists, it finishes by **replacing the target collection**.
- **`$merge`**: writes each output document into the target collection according to rules for **key matching, updating, preserving, discarding, inserting, or failing**.

Both stages perform **real data writes**. They are fundamentally different from `$project` or `$group`, which only transform the result stream. Therefore, the question is not just "did the pipeline compute the right numbers?" but also:

> **Which target documents will be created, replaced, preserved, or left partially affected if the pipeline re-runs or fails midway?**

### 1.1. A Diagram to Remember

```text
                     Source collection
                            |
                            v
                 $match / $group / $project
                            |
                     Aggregation output
                            |
                   +--------+--------+
                   |                 |
                   v                 v
                  $out             $merge
                   |                 |
       Creates new collection   Matches each document
       or replaces entire       by key `on`
       target collection             |
                   |          +------+-----+
                   |          |            |
                   |       Matched     Not matched
                   |          |            |
                   |     whenMatched  whenNotMatched
                   |          |            |
                   +----------+------------+
                              |
                          Target data
```

**First design rule:** if the goal is **replacing a full reporting snapshot**, think `$out`; if the goal is **syncing individual records by key**, think `$merge`. Never treat these two stages as interchangeable syntax variants.

## 2. General Rules Before Writing

### 2.1. Both `$out` and `$merge` Must Be the Final Stage

Valid example:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$channel", orderCount: { $sum: 1 } } },
  { $out: "paidOrdersByChannel" }
]);
```

Structurally invalid example:

```javascript
// Do not place $project after a write-output stage.
db.orders.aggregate([
  { $out: "paidOrdersByChannel" },
  { $project: { _id: 0 } }
]);
```

`$out` and `$merge` are **terminal stages**: they finalize delivering results to the target collection. Do not place processing stages after them.

### 2.2. They Do Not Return Aggregated Documents Like a Read Pipeline

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "total" }
]);
```

This pipeline returns `{ total: ... }` via the result cursor. Conversely:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "total" },
  { $out: "paidOrderCount" }
]);
```

The second pipeline **writes** the count document into the `paidOrderCount` collection. Do not expect the application to receive the count document as a normal read result; to view its contents, query the target collection.

### 2.3. They Are Not Read-Only Operations

A read-only account can run pipelines containing `$match` or `$group`, yet that does not grant permission to run `$out` or `$merge`. Write stages require **write privileges and target-collection permissions**, which may include creating or replacing collections depending on the stage.

These write operations also **cannot be used inside multi-document transactions**. If readers need safe report publication, design a mechanism aligned with each stage's semantics instead of trying to wrap `$out`/`$merge` in a transaction.

### 2.4. Choose Target Names Carefully

Running `$out: "orders"` by mistake in a production database can replace the critical `orders` collection. Therefore:

- Use distinct names for source collections and reporting collections.
- Separate test, staging, analytics, and production databases where appropriate.
- Double-check target collection name, target database, and permissions before running.
- Never copy an `$out` command pointing to a real collection name without understanding its impact.

## 3. Test Dataset Used Throughout This Lesson

All write examples use the **`mongo_training_208`** database and collections suffixed with `208` to avoid confusion with real data. Run via **mongosh** on a practice MongoDB instance—never a production database.

```javascript
const demo = db.getSiblingDB("mongo_training_208");
const source = demo.salesOrders208;

// Stop if data already exists to avoid duplicates or mixing datasets.
if (source.countDocuments({}) !== 0) {
  throw new Error(
    "salesOrders208 already contains data; use an empty test database"
  );
}

source.insertMany([
  {
    _id: "O01",
    status: "PAID",
    channel: "web",
    amount: 100000,
    createdAt: ISODate("2026-11-01T02:00:00Z")
  },
  {
    _id: "O02",
    status: "PAID",
    channel: "web",
    amount: 200000,
    createdAt: ISODate("2026-11-01T06:00:00Z")
  },
  {
    _id: "O03",
    status: "PENDING",
    channel: "app",
    amount: 50000,
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: "O04",
    status: "PAID",
    channel: "app",
    amount: 300000,
    createdAt: ISODate("2026-11-01T11:00:00Z")
  },
  {
    _id: "O05",
    status: "PAID",
    channel: "web",
    amount: 150000,
    createdAt: ISODate("2026-11-02T03:00:00Z")
  },
  {
    _id: "O06",
    status: "CANCELLED",
    channel: "app",
    amount: 90000,
    createdAt: ISODate("2026-11-02T05:00:00Z")
  },
  {
    _id: "O07",
    status: "PAID",
    channel: "app",
    amount: 70000,
    createdAt: ISODate("2026-11-02T07:00:00Z")
  },
  {
    _id: "O08",
    status: "PAID",
    channel: "web",
    amount: 80000,
    createdAt: ISODate("2026-11-02T08:00:00Z")
  }
]);
```

This sample set contains **eight orders**, of which **six are paid**. Amounts are represented as **integers in a hypothetical currency unit** for clarity. Production systems must standardize monetary storage, rounding, and cancellation/refund handling per business policy.

### 3.1. Reporting Normalization Pipeline

We want one reporting document per **business day + sales channel**, counting only `PAID` orders. Days are evaluated in the `Asia/Ho_Chi_Minh` timezone.

```javascript
const dailyPipeline = [
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: {
        day: {
          $dateToString: {
            format: "%Y-%m-%d",
            date: "$createdAt",
            timezone: "Asia/Ho_Chi_Minh"
          }
        },
        channel: "$channel"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  {
    $project: {
      _id: 0,
      day: "$_id.day",
      channel: "$_id.channel",
      orderCount: 1,
      totalAmount: 1
    }
  }
];
```

**Important note:** `_id: 0` in `$project` intentionally drops the composite grouping `_id`; in later `$merge` examples we use the **`day + channel`** pair as the business key. Leaving `$group`'s `_id` intact while picking a different `on` key can trigger immutable-field conflicts during replacements.

### 3.2. Previewing Results Before Writing Anything

```javascript
source.aggregate([
  ...dailyPipeline,
  { $sort: { day: 1, channel: 1 } }
]).toArray();
```

Expected output:

| `day` | `channel` | `orderCount` | `totalAmount` |
|---|---|---:|---:|
| 2026-11-01 | app | 1 | 300000 |
| 2026-11-01 | web | 2 | 300000 |
| 2026-11-02 | app | 1 | 70000 |
| 2026-11-02 | web | 2 | 230000 |

Total revenue across the six PAID orders is **900000**. `PENDING` and `CANCELLED` orders are excluded.

This is a vital workflow habit: **before adding a write stage, run the read/compute pipeline alone and verify group counts, keys, and totals**. With `$out`, a filter bug can replace the entire target collection with bad data; with `$merge`, a bad key can overwrite the wrong documents.

## 4. `$out`: Writing the Entire Output as a Collection

### 4.1. Syntax

Two common forms:

```javascript
// Collection in the same database as the source collection.
{ $out: "dailyReportOut208" }

// Explicit target database and collection.
{
  $out: {
    db: "mongo_training_208",
    coll: "dailyReportOut208"
  }
}
```

In our example, results are written to `dailyReportOut208`:

```javascript
source.aggregate([
  ...dailyPipeline,
  { $out: "dailyReportOut208" }
]).toArray();

demo.dailyReportOut208.find(
  {},
  { _id: 0, day: 1, channel: 1, orderCount: 1, totalAmount: 1 }
).sort({ day: 1, channel: 1 });
```

If the target collection **does not exist**, MongoDB creates it to hold the output. If the target collection **already exists**, `$out` does not merely append new documents: it builds the new output and **replaces the target collection's contents**.

### 4.2. Write Mechanics When Target Already Exists

Conceptually, `$out` works as follows:

```text
Source collection -> aggregation -> temporary collection
                                           |
                                    Write all results
                                           |
                                    Satisfy target write
                                    and index checks
                                           |
                                    Replace target with
                                      new collection
                                           |
                                    New report snapshot
```

When the target collection already exists, MongoDB builds results into a **temporary collection**, recreates matching indexes from the existing target, and swaps/renames it into place upon completion. This avoids exposing readers to a half-populated collection like manual delete-then-insert would.

**Atomicity of the target swap** does not mean the overall *read source + aggregate + publish* process is a snapshot transaction immune to concurrent writes on the source. If another app modifies orders while the job runs, design appropriate read concerns, cutoffs, or data-locking protocols.

### 4.3. `$out` Replaces All Contents: Old Documents Absent from Output Are Lost

Suppose `dailyReportOut208` currently contains an extra manual document:

```javascript
demo.dailyReportOut208.insertOne({
  day: "2026-10-31",
  channel: "web",
  orderCount: 99,
  totalAmount: 999999,
  note: "Manual note"
});
```

After re-running:

```javascript
source.aggregate([
  ...dailyPipeline,
  { $out: "dailyReportOut208" }
]).toArray();
```

the target collection contains **only documents emitted by the current pipeline**. The `2026-10-31` document and manual `note` are gone.

This is the **intended behavior of `$out`**, not a bug. Never run `$out` targeting a collection that holds source records or manual edits that must be preserved unless full replacement is genuinely intended.

### 4.4. What If Pipeline Output Is Empty?

Suppose a filter matches zero orders:

```javascript
source.aggregate([
  { $match: { status: "REFUNDED" } },
  { $project: { _id: 0, status: 1 } },
  { $out: "emptyReportOut208" }
]).toArray();
```

The target collection ends up with **zero documents**. If the target already existed with prior data, emitting an empty snapshot **replaces it with an empty collection**. Never treat "zero matches" as harmless when using `$out`.

A reporting system may need to **block publishing an empty snapshot** unless emptiness is a valid business outcome. That check must run **before the write stage**, governed by explicit policy.

### 4.5. Indexes and Constraints on the Target Collection

When `$out` replaces an existing collection, MongoDB recreates corresponding indexes from the target during temporary collection build. If the new output **violates a unique index** or fails applicable constraints, the operation fails; do not assume every computed document will be accepted.

Example unique index:

```javascript
demo.dailyReportOut208.createIndex(
  { day: 1, channel: 1 },
  { unique: true }
);
```

If a buggy pipeline produces **two documents with the same `day + channel`** and different `_id` values, the unique index causes `$out` to fail. The old target collection remains intact if the failure occurs prior to the swap; never assume success just because earlier stages ran.

### 4.6. Notable Limitations of `$out`

- Must be the final stage.
- Writes to a collection in the same database or another database on the same MongoDB deployment in supported forms.
- **Cannot write to a sharded target collection** under standard rules; to write per record into a sharded target, use `$merge` subject to sharding rules.
- Cannot be used inside multi-document transactions.
- Not a way to return read documents to the application.
- For special target collection types (such as time-series), support and syntax depend on server version; do not apply standard collection assumptions blindly.

## 5. `$merge`: Writing Each Document by Business Key

Unlike `$out`, `$merge` **does not replace the entire target collection**. It inspects each output document from the pipeline and determines whether a matching document already exists in the target.

### 5.1. Syntax

```javascript
{
  $merge: {
    into: "targetCollection",
    on: ["keyA", "keyB"],
    whenMatched: "replace",
    whenNotMatched: "insert"
  }
}
```

Components:

| Field | Meaning |
|---|---|
| `into` | Target collection name, or `{ db, coll }` document |
| `on` | Field or array of fields used as the **key identifying the target document** |
| `whenMatched` | Action when target already contains a document matching `on` |
| `whenNotMatched` | Action when target has no matching document |
| `let` | Optional variables exposed to an update pipeline inside `whenMatched` |

Full form example:

```javascript
{
  $merge: {
    into: {
      db: "mongo_training_208",
      coll: "dailyReportMerge208"
    },
    on: ["day", "channel"],
    whenMatched: "replace",
    whenNotMatched: "insert"
  }
}
```

### 5.2. Defaults

On an **unsharded** collection, omitting `on` defaults to matching on **`_id`**. On sharded collections, defaults also involve the **shard key**. Never rely on defaults when a report has a natural business key like `day + channel`.

When the other two options are omitted, the defaults are:

- `whenMatched: "merge"`.
- `whenNotMatched: "insert"`.

This means MongoDB **merges fields** when a target document matches, and **inserts a new document** when none matches.

When the goal is updating an exact per-key snapshot, specify `whenMatched: "replace"` explicitly to avoid leaving stale fields behind.

## 6. Preparing a Unique Index for `on`

MongoDB requires custom `on` fields to be backed by an **appropriate unique index** on the target collection. That index guarantees each business key maps to at most one document. A non-unique index **does not satisfy** this requirement.

For our daily/channel report:

```javascript
const mergeTarget = demo.dailyReportMerge208;

mergeTarget.createIndex(
  { day: 1, channel: 1 },
  { unique: true }
);
```

This also creates the target collection if it does not exist yet. Thus, before running `$merge`, the collection has a unique compound index on `day` and `channel`.

### 6.1. Why Is Uniqueness Required?

Suppose the target collection accidentally held:

```javascript
{ _id: 1, day: "2026-11-01", channel: "web", totalAmount: 100 }
{ _id: 2, day: "2026-11-01", channel: "web", totalAmount: 200 }
```

With `on: ["day", "channel"]`, MongoDB would not have a single deterministic target document for `("2026-11-01", "web")`. The unique index prevents duplicate key rows in the target.

### 6.2. Additional Rules for `on`

When designing the `on` key, keep in mind:

- Key fields must be present and typed consistently per version and unique-index rules; **null/missing** values carry restrictions depending on MongoDB version and index properties.
- Field values in `on` **cannot be arrays**; do not use a tags array as a composite key here.
- The unique index backing `on` must match the fields appropriately; a **partial unique index** cannot automatically substitute for the required index.
- **Collation** of the aggregation and the unique index must match. A case-sensitive index will not satisfy an `on` lookup under a different pipeline collation.
- When the target is sharded, `on` and its unique index must also satisfy shard-key constraints.

**Recommendation:** for reports, build **explicit, non-null, consistently typed** summary key fields and specify `on` explicitly. Avoid relying on optional or mutable fields.

### 6.3. `on` Does Not Have to Be `_id`

In our example, the target key is `(day, channel)`, while `_id` is an internal document identifier. They can be two completely separate keys.

When a pipeline uses `$group`, output normally has an object `_id`:

```javascript
{
  _id: {
    day: "2026-11-01",
    channel: "web"
  },
  totalAmount: 300000
}
```

To use `on: ["day", "channel"]`, lift **`day` and `channel` to top-level fields**. `dailyPipeline` does this in `$project` and **drops the source `_id`** so `$merge` does not try to overwrite an immutable `_id` that differs from the existing target document.

## 7. Complete `$merge` Example: Refreshing Individual Report Groups

Using the collection/index prepared in Section 6:

```javascript
source.aggregate([
  ...dailyPipeline,
  {
    $merge: {
      into: "dailyReportMerge208",
      on: ["day", "channel"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]).toArray();

demo.dailyReportMerge208.find(
  {},
  { _id: 0, day: 1, channel: 1, orderCount: 1, totalAmount: 1 }
).sort({ day: 1, channel: 1 });
```

Initial output contains the four groups computed by `dailyPipeline`. Compared to `$out`, here MongoDB:

1. Reads one output document, e.g., `{ day: "2026-11-01", channel: "web", orderCount: 2, totalAmount: 300000 }`.
2. Looks up the target document matching `(day, channel)`.
3. If found, **`replace`**s the target document with the new report data without altering immutable keys.
4. If absent, **`insert`**s a new reporting document.
5. Continues across remaining pipeline documents.

### 7.1. Re-Running on Unchanged Data

If no orders changed, re-running this pipeline produces **business-equivalent** report data: no duplicate document is created just because the same day/channel key was processed again.

This gives `whenMatched: "replace"` + `whenNotMatched: "insert"` **key- and data-level idempotency**.

**Do not confuse safe re-runnability of this pattern with whole-pipeline atomicity.** Documents are written individually; if the pipeline fails midway after writing some documents, the target may reflect a partial update.

### 7.2. After Source Data Changes

Insert a new `PAID` web order on 2026-11-01:

```javascript
source.insertOne({
  _id: "O09",
  status: "PAID",
  channel: "web",
  amount: 25000,
  createdAt: ISODate("2026-11-01T12:00:00Z")
});
```

Re-run `$merge`:

```javascript
source.aggregate([
  ...dailyPipeline,
  {
    $merge: {
      into: "dailyReportMerge208",
      on: ["day", "channel"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]).toArray();
```

The `2026-11-01 + web` group updates from:

```javascript
{ day: "2026-11-01", channel: "web", orderCount: 2, totalAmount: 300000 }
```

to:

```javascript
{ day: "2026-11-01", channel: "web", orderCount: 3, totalAmount: 325000 }
```

Other groups keep their respective numbers. Because `dailyPipeline` recomputes **full group totals from the source**, `replace` does not add onto the old value and never double-counts on re-runs.

**Practice note:** inserting O09 alters the base dataset; later examples may assume the original eight documents and will note when a specific state is assumed.

## 8. Full Reference for `whenMatched` and `whenNotMatched`

### 8.1. `whenMatched`: When a Target Document Matches

| Value | Behavior |
|---|---|
| `"replace"` | Replaces the target document with the output document; must not violate immutable fields like `_id` or shard key |
| `"merge"` | Merges fields from output document into target document; keeps target fields not overwritten |
| `"keepExisting"` | Leaves target document untouched, discards output document |
| `"fail"` | Throws an error when a matching target document already exists |
| Update pipeline | Computes how to update the target document using supported update stages |

### 8.2. `whenNotMatched`: When No Target Document Matches

| Value | Behavior |
|---|---|
| `"insert"` | Inserts the output document into the target collection |
| `"discard"` | Ignores the output document without inserting |
| `"fail"` | Throws an error when no matching target document exists |

Defaults are `whenMatched: "merge"` and `whenNotMatched: "insert"`. Other values are **choices about update semantics**, not performance knobs.

### 8.3. Scenario Table

Suppose the pipeline produces:

```javascript
{
  day: "2026-11-01",
  channel: "web",
  orderCount: 3,
  totalAmount: 325000
}
```

and the target currently holds:

```javascript
{
  _id: ObjectId("64b000000000000000000001"),
  day: "2026-11-01",
  channel: "web",
  orderCount: 2,
  totalAmount: 300000,
  owner: "analytics",
  note: "Manual approval"
}
```

With `on: ["day", "channel"]`:

- `replace`: count and revenue become 3 / 325000; old `owner` and `note` fields **are removed** since they are absent from the new document; existing `_id` is preserved per immutable-field rules.
- `merge`: count and revenue become 3 / 325000, while `owner` and `note` **remain intact** because the incoming document does not overwrite them.
- `keepExisting`: the entire target document stays at 2 / 300000.
- `fail`: errors upon matching.
- Update pipeline: you specify explicitly which fields update and how new values are computed.

### 8.4. `merge` Does Not Mean Numeric Accumulation

This is a very common misinterpretation:

```javascript
whenMatched: "merge"
```

does **not** mean `totalAmount_new = totalAmount_old + totalAmount_incoming`. It means **merging document fields**—the incoming `totalAmount` **overwrites** the field of the same name in the target.

To accumulate onto existing target values on match, write **`whenMatched` as an update pipeline** or design a different update operation. Note that accumulation risks double-counting on retries, explained in Section 10.

## 9. Key Differences Between `replace` and `merge`

### 9.1. Full Per-Key Snapshot Replacement

On each run, `dailyPipeline` emits a complete document:

```javascript
{
  day: "2026-11-01",
  channel: "web",
  orderCount: 3,
  totalAmount: 325000
}
```

If this represents the **new source of truth** for that reporting row, `whenMatched: "replace"` fits well: every pipeline-owned field reflects fresh calculations, and obsolete fields are not accidentally left behind.

However, `replace` will also **wipe out extra target fields** such as `reviewedBy` or `manualComment`. Never use `replace` carelessly if humans edit fields on the target collection.

### 9.2. Updating a Few Fields While Keeping Others

Suppose the target stores:

```javascript
{
  day: "2026-11-01",
  channel: "web",
  orderCount: 2,
  totalAmount: 300000,
  reviewedBy: "analyst-01",
  reviewNote: "Reviewed"
}
```

The pipeline emits only `day`, `channel`, `orderCount`, and `totalAmount`. With `whenMatched: "merge"`, `reviewedBy` and `reviewNote` survive while the two metrics update.

This works when a reporting collection **intentionally mixes automated and manual fields**. The trade-off: if pipeline schemas evolve and drop an old automated field, stale fields can **linger in the target**.

**Define explicit field ownership:** which fields are pipeline-owned, which are user-owned, and which must be cleared on refresh.

### 9.3. Separating Automated Metrics from Manual Annotations

An easier-to-govern design is:

```text
dailyReport208
  day, channel, orderCount, totalAmount

dailyReportAnnotations208
  day, channel, reviewedBy, note, approvalStatus
```

Automated summaries can refresh cleanly without risking overwrites, while annotations live by business key in a separate collection. The read API joins them as needed, trading off join complexity, key alignment, and permissions.

This is **data modeling to eliminate overwrite risk**, rather than relying solely on a `whenMatched` option.

## 10. Pipeline-Style `whenMatched`: Computed Updates

A major strength of `$merge` is customizing how matched documents update using an **aggregation update pipeline**.

### 10.1. Incremental Counter Example

Suppose the input stream emits only **newly arrived deltas** per `(day, channel)`, not full historical sums. Then:

```javascript
{
  $merge: {
    into: "dailyReportMerge208",
    on: ["day", "channel"],
    whenMatched: [
      {
        $set: {
          orderCount: {
            $add: ["$orderCount", "$$new.orderCount"]
          },
          totalAmount: {
            $add: ["$totalAmount", "$$new.totalAmount"]
          }
        }
      }
    ],
    whenNotMatched: "insert"
  }
}
```

Here:

- `"$orderCount"` and `"$totalAmount"` reference fields **already stored in the target document**.
- `"$$new.orderCount"` and `"$$new.totalAmount"` reference the **incoming output document from the source pipeline** using the default variable context.
- `$add` computes the incremented values stored back into the target.

This is a **delta pattern**—never combine it with `dailyPipeline` which emits **full snapshots** from the source, or re-running the snapshot will add the entire revenue over again.

### 10.2. Why Does Accumulation Easily Double-Count?

Suppose the target currently holds:

```javascript
{ day: "2026-11-01", channel: "web", orderCount: 5, totalAmount: 500000 }
```

An incoming delta is:

```javascript
{ day: "2026-11-01", channel: "web", orderCount: 1, totalAmount: 100000 }
```

Run 1 increments to `6 / 600000`. If the job times out and the app **replays the same delta**, the target becomes `7 / 700000`.

It is **not idempotent**.

To build reliable event-driven counters:

- Every event/delta needs a **unique ID** and a processed-event ledger.
- Apply increments only if that event ID has not been processed yet.
- Ensure atomicity between recording the event ID and updating the counter; never assume `$merge` alone guarantees exactly-once semantics.
- Maintain a reconciliation or full recomputation job from the source of truth when drift occurs.

For most dashboards, **recomputing full group snapshots and using `replace` by key** is far easier to recover than unguarded delta accumulation.

### 10.3. Allowed Stages Inside a `whenMatched` Pipeline

A `whenMatched` pipeline is not a general-purpose aggregation pipeline. MongoDB supports only a restricted set of **document-transformation update stages**, such as `$set`/`$addFields`, `$project`/`$unset`, and `$replaceRoot`/`$replaceWith` per server version rules.

Never place `$group`, `$out`, or `$merge` inside this update pipeline expecting a nested aggregation flow.

The update pipeline also cannot mutate **`on` key fields**, `_id`, or shard keys in ways that violate immutability. Changing a business key requires explicit delete/create handling with careful consistency design.

### 10.4. `let` Variables When Referencing Incoming Data

`$merge` allows declaring variables in `let` so update expressions can reference source pipeline fields. When using `let`, understand variable scope and `$$variableName` syntax for your MongoDB version, and avoid mixing default `$$new` with custom variables without testing actual behavior.

For standard `replace` and `merge` modes, `let` is **not needed**.

## 11. Failure Semantics and Atomicity: Two Very Different Stages

### 11.1. `$out`: Publishes the Whole Snapshot at the Swap Step

For standard target collections, `$out` builds the replacement dataset and performs a final publication swap. If the aggregation fails **before the swap succeeds**, the existing target collection remains intact for readers.

This is a major advantage of `$out` for **full refreshes**. Still:

- It cannot restore old contents **once you have published a syntactically valid but logically wrong snapshot**.
- Do not assume reading the source is an isolated snapshot transaction if source documents mutate during execution.
- Target collection permissions and collection-type constraints must still be met.

Once bad data is published, recovery requires backups, versioned snapshots, or controlled recomputation.

### 11.2. `$merge`: Written Document by Document, Not a Single Atomic Swap

`$merge` applies write rules document by document. Individual document writes obey MongoDB's **single-document** atomicity, yet **an entire `$merge` pipeline is not an atomic multi-document transaction**.

Suppose a pipeline emits 1,000 documents:

```text
Output document #1   -> written successfully
Output document #2   -> written successfully
...
Output document #600 -> written successfully
Output document #601 -> hits duplicate key / validation / write error
                         |
                         v
              Pipeline terminates with error
                         |
                         v
       Earlier writes may already be in target
```

There is no automatic guarantee that "any error rolls back all 600 previously written documents."

That is why `whenMatched: "fail"` or `whenNotMatched: "fail"` is **not** a pre-flight dry-run check that guarantees all-or-nothing writes. It fails upon encountering the offending document after prior documents may have already been applied.

### 11.3. When Source Data Changes During Execution

An aggregation can take seconds or minutes to scan the source collection. Meanwhile, other applications can insert, update, or delete orders.

Interpret pipeline output under the configured **read concern and consistency semantics**, rather than assuming a business cutoff snapshot at an exact instant.

For end-of-day reports, define:

- Cutoff window and timezone.
- Whether backdated writes or edits to historical orders are permitted.
- When source data is considered settled.
- Whether prior days' groups must be re-run when refunds or edits arrive late.
- How source versions, cutoffs, or watermarks are logged.

Safe result writing is only **one part** of a consistent reporting architecture.

## 12. `$merge` Does Not Automatically Delete Groups That Vanished from Source

This is one of the most dangerous business differences between `$out` and `$merge`.

Suppose after the previous run, the target contains:

```javascript
{ day: "2026-11-02", channel: "app", orderCount: 1, totalAmount: 70000 }
```

Later, order O07 changes from `PAID` to `CANCELLED`. Now zero PAID orders exist for `2026-11-02 + app` in the original dataset.

When `dailyPipeline` re-runs:

- The pipeline **emits no document** for `2026-11-02 + app`.
- `$merge` **is never invoked** for that key because no source output arrived.
- The stale document in the target collection **remains**, even though its metrics are no longer valid.

This is a **stale target row**.

### 12.1. Demonstrating on the Dataset

The snippet below mutates the source; run only after observing initial results:

```javascript
source.updateOne(
  { _id: "O07" },
  { $set: { status: "CANCELLED" } }
);

source.aggregate([
  ...dailyPipeline,
  {
    $merge: {
      into: "dailyReportMerge208",
      on: ["day", "channel"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]).toArray();
```

`$merge` does not delete the `2026-11-02 / app` target row. By contrast, a successful `$out` re-run builds the collection fresh from **only the groups currently present in the source**, so vanished groups disappear from the new snapshot.

### 12.2. Strategies When Full Synchronization Is Required

Depending on the goal:

1. **Full refresh:** prefer `$out` when the reporting collection should mirror the exact current pipeline output.
2. **Scoped partial refresh:** define which days/tenants/channels are recomputed, how stale rows in that scope are cleared, and how to handle errors between delete and write. **Never run a raw `deleteMany()` in production before writing without guarding against partial failures.**
3. **Staging then publish:** write into a staging collection, validate, and publish via an appropriate collection swap/rename pattern for your deployment.
4. **Version or active marker:** stamp each run with a version and query only the active version, paired with version-switching and cleanup jobs.

No `$merge` parameter automatically means "delete any target document absent from the source output."

## 13. Risks of Reading and Writing the Same Collection

MongoDB may allow pipelines that write back into the collection they read from, yet this should never be your default approach.

### 13.1. Why Is Same-Source Same-Target Risky with `$merge`?

Conceptual example:

```javascript
db.someCollection.aggregate([
  { $match: { active: true } },
  { $set: { updatedAt: new Date() } },
  {
    $merge: {
      into: "someCollection",
      on: "_id",
      whenMatched: "merge",
      whenNotMatched: "insert"
    }
  }
]);
```

When a pipeline reads a collection and writes back to the same collection, updates can move documents in storage or index order. Under certain conditions, the read cursor can encounter an updated document again, risking duplicate processing—commonly known as the **Halloween problem**.

Do not treat the snippet above as a safe migration recipe.

### 13.2. Practical Alternatives

- For large transformations, write to a **new collection** and publish it.
- For conditional bulk updates, consider a direct **update pipeline** with an appropriate filter.
- If you must `$merge` back into the source collection, understand reprocessing risks, keys, query conditions, and re-runnability, and test thoroughly on representative data.
- Never assume `on: "_id"` automatically eliminates all same-collection read-write hazards.

## 14. Choosing Between `$out` and `$merge`

| Criterion | `$out` | `$merge` |
|---|---|---|
| Primary purpose | Publish **entire result set** as a collection | Sync **individual documents** by key |
| Existing target collection | Replaces entire dataset upon completion | Preserves collection, applying inserts/updates per rules |
| Old groups absent from new output | Dropped from target snapshot | **Remain in target**, unless handled separately |
| `on` key | No `on` parameter | Has `on`, requires matching unique index |
| Handling matched documents | Not per-document | `replace`, `merge`, `keepExisting`, `fail`, or pipeline |
| Handling unmatched documents | Created from output | `insert`, `discard`, or `fail` |
| Risk of partial writes visible in target | Swaps collection after building output | Earlier writes can persist if an error hits midway |
| Existing indexes | Rebuilds/copies matching target indexes on normal swap | Uses existing target indexes; `on` needs unique index |
| Sharded destination | Not supported under standard rules | Supported subject to shard key and unique index rules |
| Preserve target fields absent from source | No | Yes, with `whenMatched: "merge"` |
| Re-runnability | Rebuilds full snapshot; old copy replaced | Policy-dependent: snapshot `replace` is safer than delta add |
| Best suited for | Full materialization, batch snapshots, full report rebuilds | Upserts, key-based sync, incremental/scoped group updates |

**Neither option is universally "safer."** `$out` excels at publishing whole snapshots yet destroys un-emitted target data. `$merge` is flexible yet can leave stale rows behind or stop with partial writes on failure.

## 15. Key Design and Uniqueness of Aggregated Results

### 15.1. Summary Keys Must Match the Exact Reporting Grain

For a **day + channel** report, the key is:

```javascript
{ day: "2026-11-01", channel: "web" }
```

In a multi-tenant system, the same day and channel appear for many tenants. The key must become:

```javascript
{
  tenantId: "T01",
  day: "2026-11-01",
  channel: "web"
}
```

with the matching index:

```javascript
demo.someTenantReport208.createIndex(
  { tenantId: 1, day: 1, channel: 1 },
  { unique: true }
);
```

Omitting `tenantId` from `on` lets different tenants **overwrite each other's reports** or collide on keys. That is far worse than a performance bug.

### 15.2. Keep Key Types Consistent

Never let one job output:

```javascript
{ day: "2026-11-01", channel: "web" }
```

while another outputs:

```javascript
{ day: ISODate("2026-11-01T00:00:00Z"), channel: "web" }
```

Because `day` is a String in the first job and a BSON Date in the second, the keys are not equal. The result is duplicate **business records** or missed updates.

Pick one standard:

- Store `day` as a BSON Date truncated to start-of-day in the target timezone.
- Or store `day` as an ISO `YYYY-MM-DD` string computed under an explicit timezone rule.

Never let different jobs pick key representations ad hoc.

### 15.3. Do Not Mutate `on` Keys During Updates

With `$merge`, the fields identifying a target document are the **row's immutable identity**, not attributes an update pipeline freely edits. If an order changes `channel` from `"web"` to `"app"`:

- One source document changed an attribute.
- An old reporting group needs its totals reduced or removed.
- A new reporting group needs its totals increased.

Snapshot `$merge` updates the new group, yet **does not automatically shrink or delete the old group**. Section 12 showed why full synchronization rules are needed.

## 16. Protecting Target Collections Before Running Jobs

### 16.1. Using a Staging Collection

A common workflow:

```text
orders
  |
  v
Read + transform aggregation
  |
  v
report_daily_staging_<run_id>
  |
  +-- verify key set, group count, total revenue, constraints
  |
  +-- if checks fail: keep existing production version
  |
  +-- if checks pass: publish via appropriate replacement step
  |
  v
report_daily_current
```

Staging lets the system **inspect the generated write set** before swapping out the collection serving live users.

While `$out` already uses an internal temporary collection before swapping, an **internal temp collection** does not replace an explicit named staging collection when operators or automated checks must review numbers before publication.

### 16.2. Preview with a Read-Only Pipeline

Before attaching `$out` or `$merge`, run:

```javascript
const preview = source.aggregate([
  ...dailyPipeline,
  { $sort: { day: 1, channel: 1 } }
]).toArray();

printjson(preview);
```

Verify:

- Is the output group count reasonable?
- Does every group have `day`, `channel`, `orderCount`, and `totalAmount`?
- Does the sum of `orderCount` match the expected PAID order count?
- Does the sum of `totalAmount` match expected revenue per business rules?
- Are any keys null/missing, mistyped, or missing `tenantId`?
- Are any groups outside the expected date window?

On large datasets, never call `toArray()` on **millions of output documents**. Run a summary verification pipeline against staging or inspect a representative sample instead of pulling millions of docs into RAM.

### 16.3. Check Source and Output Counts at the Right Grain

Count PAID orders:

```javascript
source.countDocuments({ status: "PAID" });
// 6 on the initial eight-order dataset.
```

Count aggregated groups:

```javascript
source.aggregate([
  ...dailyPipeline,
  { $count: "groups" }
]).toArray();
// [{ groups: 4 }] on the initial dataset.
```

These two counts differ because **one group collapses multiple orders**. Never use `countDocuments()` on the source to assert how many rows `$group` should write to the target.

If the input is empty, `$count` emits no document; verification code must handle empty results explicitly and check whether an empty snapshot is allowed.

## 17. Enforcing Constraints and Privileges When Writing

### 17.1. Unique Indexes and Schema Validation

A calculation pipeline can emit syntactically valid yet schema-invalid documents:

```javascript
{
  day: null,
  channel: ["web", "app"],
  orderCount: "two",
  totalAmount: -100
}
```

These violate the `on` key and reporting semantics. Before writing:

- Normalize types for `day` and `channel`.
- Assert keys are non-null, non-missing scalars.
- Ensure `orderCount` and `totalAmount` have proper numeric types.
- Consider collection schema validation to reject malformed documents.
- Check unique index and collation rules.

If a unique key or validation error hits during `$merge`, **updates before the failing document may already be committed**. With `$out`, the swap aborts before publication. Hence the two stages require different operational recovery plans.

### 17.2. Least Privilege Principle

The reporting job account should only have **read access on source collections** and **write access on the specific target collection/database**. With `$out`, privileges to create, rename, or replace collections can be required; never grant full database drop/admin privileges to a job account merely for convenience.

When an account only needs to upsert into a reporting collection, `$merge` with tightly scoped privileges reduces blast radius compared to allowing full collection replacement—though key-based overwrite risks must still be controlled.

### 17.3. Record Job Metadata Separately

A batch job should maintain operational metadata such as:

```javascript
{
  job: "dailyRevenue",
  runId: "run-2026-11-03-001",
  sourceFrom: ISODate("2026-11-01T00:00:00Z"),
  sourceTo: ISODate("2026-11-03T00:00:00Z"),
  startedAt: ISODate("2026-11-03T01:00:00Z"),
  completedAt: ISODate("2026-11-03T01:00:12Z"),
  status: "COMPLETED",
  expectedGroups: 4
}
```

This is a **metadata log pattern**, not something `$out` or `$merge` writes automatically. Store job logs in a dedicated collection or monitoring store with proper retry and access controls.

Never rely solely on an application `"COMPLETED"` log line to assume publication succeeded: verify target collection state or version markers after job completion.

## 18. Preventing Concurrent Runs and Handling Retries

### 18.1. Two Jobs Writing to the Same Target

Suppose:

- Job A computes the report from data up to 10:00.
- Job B computes the report from data up to 10:05.
- B finishes first; A finishes second.

If both write to the same collection, final state reflects A's **older** snapshot even though B already processed newer data.

With `$out`, both try to swap the entire collection. With `$merge`, interleaved writes per group can leave the target holding a **mixed patchwork of versions**.

### 18.2. Preventing Out-of-Order Overwrites

Consider:

- Allowing **only one job of a given type/scope** to run at a time (distributed lock / scheduler serialization).
- Using a run ID, watermark, or monotonic version to decide which run may publish.
- Writing to run-scoped staging collections and publishing only the verified newest run.
- With `$merge`, if keeping multi-version history, include `version` in the key and switch an active pointer—though that alone does not solve all race conditions.

Concurrency control belongs in the **orchestration layer** or data architecture; `$merge` does not know which job is "newer."

### 18.3. Distinguishing Different Kinds of Re-Runs

| Scenario | Operational Consequence to Note |
|---|---|
| Re-running `$out` on the same snapshot | Target is replaced with business-equivalent data; still pays rebuild/swap cost |
| Re-running `$merge` with `replace` on the same snapshot | Matched keys are replaced with equivalent data |
| Re-running `$merge` with `merge` | Pipeline fields overwrite; older non-pipeline fields remain |
| Re-running delta-accumulating `$merge` | Can **double-count** if the delta was already applied |
| Re-running after mid-flight `$merge` failure | Needs recovery handling for already-updated vs. unapplied rows |
| Re-running after source state transitions | Vanished source groups are not removed by `$merge` |

A job can be **safe to retry** in one mode and unsafe in another. Define idempotency explicitly from `whenMatched`, `on`, and source semantics.

## 19. What Happens When Source or Target Is Sharded?

MongoDB runs aggregations on sharded deployments, yet **reading from shards and writing to a sharded target are two separate questions**.

### 19.1. `$out` and Sharded Destinations

`$out` does not support directly replacing **a sharded target collection** under standard rules. It can read from a sharded source, while the destination remains bound by stage restrictions.

To refresh a sharded target collection, evaluate `$merge` or a dedicated staging/publication architecture depending on snapshot needs and shard key design.

### 19.2. `$merge` and Sharded Destinations

`$merge` can write to a sharded collection when required conditions are satisfied. The default or custom `on` key must align with the **shard key** and target unique index rules.

You cannot supply an arbitrary `on` key that cannot route or lacks unique-index backing on a sharded collection and expect MongoDB to locate a unique record across all shards.

### 19.3. Multi-Tenant Reporting Keys

When sharded by `tenantId`, ensure the aggregation preserves `tenantId`:

```javascript
{
  $group: {
    _id: {
      tenantId: "$tenantId",
      day: "$day",
      channel: "$channel"
    },
    orderCount: { $sum: 1 },
    totalAmount: { $sum: "$amount" }
  }
}
```

Then project the key fields to top-level for use in `on`. Exact design depends on sharding strategy and MongoDB version; verify before production rollout.

## 20. Performance and Operational Impact

### 20.1. Work on the Source

Before writing anything, MongoDB still executes all read and compute stages:

```text
$match -> $group -> $project -> write stage
```

If `$match` scans the full collection, `$group` buffers huge numbers of groups, or the pipeline sorts massive datasets, scaling target capacity will not eliminate source execution cost.

Example index supporting status and time filtering:

```javascript
source.createIndex({
  status: 1,
  createdAt: 1
});
```

Test candidate indexes against real `$match` shapes, such as `PAID` over a date window. An index does not automatically make every `$group` by day/channel fast. Use `explain("executionStats")` on the **read-only pipeline** to inspect `COLLSCAN`/`IXSCAN`, resources, and input counts.

### 20.2. Work on the Target

`$out`:

- Builds a brand-new result collection.
- Recreates/copies target indexes.
- Incurs collection-swap and cache/index-refresh overhead.
- Fits large full snapshots when rebuild cost is acceptable.

`$merge`:

- Looks up the `on` key for every emitted document.
- Incurs index-lookup and per-document insert/update overhead.
- Additional secondary indexes on the target add write amplification.
- Can touch only changed groups, while requiring stale-row and late-data handling.

There is no universal rule that "`$merge` is always faster than `$out`." For a full refresh of millions of rows, per-document upserts can be much slower than rebuilding; for updating a few hundred groups in a massive historical table, replacing the entire table via `$out` is wasteful.

### 20.3. `allowDiskUse` Does Not Fix Target Data Errors

```javascript
source.aggregate(
  [
    ...dailyPipeline,
    { $out: "dailyReportOut208" }
  ],
  { allowDiskUse: true }
).toArray();
```

In supported versions/configurations, `allowDiskUse` lets memory-intensive stages spill temporary data to disk. It **does not**:

- Turn `$merge` into an all-or-nothing transaction.
- Bypass unique index or schema validation checks.
- Allow `$out` to write to an unsupported sharded target.
- Fix a wrong filter or unstable `on` key.

### 20.4. Read Concern and Write Concern

Correctness and durability also depend on MongoDB policies:

- **Read concern:** isolation/durability guarantees when reading source data.
- **Write concern:** acknowledgment level required when writing target data.
- **Read preference:** which deployment members serve source reads, subject to operation rules.
- **Sessions, topology, and failovers:** long-running jobs can be interrupted by infrastructure failovers.

Never conclude from a successful `aggregate()` return alone that every replica has applied the writes or that source reads formed a single point-in-time snapshot. Configure those guarantees explicitly per deployment and SLA.

## 21. Java MongoDB Driver: Running Pipelines with Write Stages

In Java apps using the **MongoDB Sync Driver**, build aggregation pipelines from `Bson` stages. Concise example writing to a target collection with `$merge`:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public class MergeExample {
    public static void main(String[] args) {
        try (MongoClient client = MongoClients.create(
                "mongodb://localhost:27017")) {

            MongoCollection<Document> source = client
                    .getDatabase("mongo_training_208")
                    .getCollection("salesOrders208");

            // Simple example: write PAID order counts per channel.
            List<Bson> pipeline = List.of(
                    new Document("$match",
                            new Document("status", "PAID")),

                    new Document("$group",
                            new Document("_id", "$channel")
                                    .append("orderCount",
                                            new Document("$sum", 1))),

                    new Document("$project",
                            new Document("_id", 0)
                                    .append("channel", "$_id")
                                    .append("orderCount", 1)),

                    new Document("$merge",
                            new Document("into", "channelSummary208")
                                    .append("on", "channel")
                                    .append("whenMatched", "replace")
                                    .append("whenNotMatched", "insert"))
            );

            // Unique index {channel: 1} must exist on target beforehand.
            source.aggregate(pipeline).toCollection();
        }
    }
}
```

Before running the Java snippet, create the unique index:

```javascript
demo.channelSummary208.createIndex(
  { channel: 1 },
  { unique: true }
);
```

Key takeaways:

- Java calls `aggregate(pipeline)`, yet the **effect is a write** because of `$merge`.
- `toCollection()` is the Sync Driver method for executing write-output pipelines; do not expect a list of returned documents.
- The driver credentials need permissions on both source and target.
- Handle duplicate-key, validation, authorization, and network exceptions properly; never mark a job successful unless the write command completed cleanly.
- When an error leaves write progress uncertain, rely on workflow idempotency and inspect target state before retrying.

The Java snippet uses a simplified schema to demonstrate the driver API; for the day/channel job, plug in the stages from `dailyPipeline` with the matching unique compound index.

## 22. Anti-Patterns to Avoid

### 22.1. Running `$out` Back onto the Source Collection Just to "Update a Few Fields"

```javascript
// Dangerous if orders is a business collection that must be preserved.
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $project: { customerId: 1, amount: 1 } },
  { $out: "orders" }
]);
```

If this succeeds, `orders` is replaced with only `PAID` documents containing just the projected fields. Unmatched orders and omitted fields **vanish**. This is not a safe column-update statement.

### 22.2. Using `$merge` with an Under-Specified `on` Key

```javascript
// Wrong if the report must distinguish each day AND channel.
{
  $merge: {
    into: "dailyReport",
    on: "day",
    whenMatched: "replace",
    whenNotMatched: "insert"
  }
}
```

On the same day, web and app need two separate documents. Using only `day` causes uniqueness collisions or overwrites one channel with another. Use `on: ["day", "channel"]` with a matching unique index.

### 22.3. Assuming `whenMatched: "merge"` Accumulates Sums

Here `merge` means **field merging**, not numeric addition. To accumulate, use an explicit update pipeline expression and duplicate-prevention logic for retries.

### 22.4. Assuming `$merge` Deletes Groups Removed from Source

`$merge` never visits target documents that **have no matching source output**. A full-refresh upsert can leave obsolete report groups behind, skewing dashboards.

### 22.5. Assuming a Late Pipeline Error Leaves Target Untouched

With `$merge`, earlier documents may already be inserted or updated before a later document fails. Never blindly retry non-idempotent accumulations or treat an error as proof that "nothing was written."

### 22.6. Treating Pipeline Sort Order as Collection Storage Order

`$sort` before `$out` does not guarantee `find()` on the target collection will always return documents in that order. **Collections have no business-guaranteed default read order.** Always specify `sort()` on read queries when order matters.

### 22.7. Arbitrarily Using `$group`'s `_id` as the Target Key

`$group` can emit an object `_id`. Mixing inconsistent key structures or wrong `on` fields causes unintended inserts or immutable-field errors. **Design the key intentionally** and project a clean top-level schema.

### 22.8. Overwriting User-Managed Fields

Never let a `replace` reporting pipeline wipe out analyst approval comments stored in the same document. Separate field ownership or use an appropriate `merge` strategy.

## 23. A Controlled Operational Workflow

For a nightly summary job, organize execution as follows:

### Step 1 — Define the Target Data Contract

Example:

```javascript
{
  day: "YYYY-MM-DD",
  channel: "web | app | partner",
  orderCount: Number,
  totalAmount: Number
}
```

Clarify:

- Who owns the target collection?
- Is it a full snapshot or per-key upserts?
- Which fields may be edited manually?
- What is the unique identifying key?
- How are late arrivals or historical edits handled?

### Step 2 — Run the Read-Only Pipeline First

```javascript
source.aggregate(dailyPipeline).toArray();
```

On large datasets, verify summary totals in read-only mode rather than loading every row into RAM.

### Step 3 — Choose Snapshot vs. Upsert Policy

- If the target must match **the exact full current output**, use `$out` or controlled staging/swap.
- If updating/inserting **per key**, use `$merge` with `on` and a matching unique index.
- If the pipeline emits **deltas**, build idempotency before using additive updates.

### Step 4 — Verify Target Constraints

Check target namespace, privileges, unique indexes, and schema validation. For sharded targets or special collection types, verify write-stage support.

### Step 5 — Guard Against Concurrent Runs

Assign a run ID and prevent two overlapping jobs from publishing out of order. With staging, give each run a distinct staging name and clean-up policy.

### Step 6 — Write Results

Attach `$out` or `$merge` only once source scope and write policy are verified. Set write concern to match durability SLAs.

### Step 7 — Reconcile After Writing

Example on the initial snapshot:

```javascript
demo.dailyReportOut208.countDocuments({});
// 4 on the initial eight-order dataset.

demo.dailyReportMerge208.countDocuments({});
// 4 on the first run into an empty collection.
```

After running examples that insert O09 or update O07, counts may differ. Always reconcile against the **current dataset state**, not stale initial numbers.

### Step 8 — Log Run Success and Maintain a Recovery Plan

Log the run ID, completion time, group count, and source version/cutoff. Rolling back a published snapshot requires source recomputation or a pre-swap backup; `$out` has no built-in "undo to previous version" button.

## 24. Practice Exercises

### Exercise 1 — Building a Snapshot Report with `$out`

From the eight-order dataset:

1. Filter only `PAID` orders.
2. Group by `day` in timezone `Asia/Ho_Chi_Minh` and `channel`.
3. Compute `orderCount` and `totalAmount`.
4. Write to `dailyReportOut208` with `$out`.
5. Query the target collection and verify the initial four groups.

Explain why putting `$sort` before `$out` does not replace `sort()` on downstream `find()` queries.

### Exercise 2 — Observing `$out` Re-Run Impact

After Exercise 1, insert a dummy report document **only inside the test target collection**:

```javascript
demo.dailyReportOut208.insertOne({
  day: "2026-10-31",
  channel: "web",
  orderCount: 99,
  totalAmount: 999999
});
```

Re-run `$out` from the source. Does the 2026-10-31 document still exist? If not, which `$out` semantics does this illustrate? Why is this dangerous if the target holds manual user annotations?

### Exercise 3 — Setting Up `$merge` on a Composite Key

Create collection `dailyReportMerge208` and a unique index on `{ day: 1, channel: 1 }`. Write a `$merge` pipeline with:

```javascript
on: ["day", "channel"],
whenMatched: "replace",
whenNotMatched: "insert"
```

Run it twice with unchanged source data and verify why duplicate documents do not appear for the same day/channel pair.

### Exercise 4 — Comparing `replace` and `merge`

In a separate test collection, create a target document:

```javascript
{
  day: "2026-11-01",
  channel: "web",
  orderCount: 2,
  totalAmount: 300000,
  note: "Checked"
}
```

Compare results when an incoming document with the same key has only `day`, `channel`, `orderCount`, and `totalAmount`, under:

1. `whenMatched: "replace"`.
2. `whenMatched: "merge"`.
3. `whenMatched: "keepExisting"`.

Does `note` survive? Do the totals update?

### Exercise 5 — Checking Vanished Groups

After generating the initial report:

1. Update O07 from `PAID` to `CANCELLED`.
2. Re-run `$merge` with `replace`.
3. Inspect `2026-11-02 + app` in the target.
4. Re-run `$out` into another test snapshot collection.
5. Explain why the two target collections now differ.

Propose an appropriate synchronization strategy if the report must reflect **all and only currently active groups**.

### Exercise 6 — Spotting a Flawed `on` Key Design

A multi-tenant system emits:

```javascript
{
  tenantId: "T01",
  day: "2026-11-01",
  channel: "web",
  totalAmount: 1000
}
```

but `$merge` uses `on: ["day", "channel"]`. Explain the risk when two tenants share a day/channel. Fix `on`, the unique index, and `$group`.

### Exercise 7 — Why Is Delta Accumulation Unsafe on Retries?

Suppose the target has total `500`, and an incoming delta is `+100`. Using an additive `whenMatched` pipeline, the app retries the same delta after a timeout.

1. What can the total become after the first and second runs?
2. Where must processed event/delta IDs be stored?
3. What goes wrong if the ID is recorded without updating the counter?
4. What goes wrong if the counter updates without recording the ID?
5. When should full snapshot recomputation be preferred?

### Exercise 8 — Guarding Against Partial Writes

A `$merge` emits 100 documents. On document 61, it hits a unique index error.

Answer:

- Can you assume the first 60 documents were not written?
- Is `whenMatched: "fail"` a transaction mechanism?
- How can you recover from a partial write?
- Why do staging/versioning and job logs make operations safer?

### Exercise 9 — Targets with Manual Fields

A reporting collection stores `day`, `channel`, `orderCount`, `totalAmount`, `approvalStatus`, and `reviewNote`. Automated metrics refresh hourly, while analysts update `approvalStatus`/`reviewNote`.

Compare:

- Single collection using `whenMatched: "merge"`.
- Two collections separating automated metrics and approvals.
- Full `$out` onto the shared collection.

Which design best prevents losing approval metadata? What are the query and synchronization trade-offs?

### Exercise 10 — Designing an Auditable Operational Plan

Design a nightly job over 50 million orders:

1. Choose date scope, timezone, and watermark.
2. Identify `$match` predicates able to use indexes.
3. Choose full refresh via `$out` vs. key-based upsert via `$merge`.
4. Define target keys and unique indexes.
5. Specify handling for late refunds or backdated entries.
6. Specify how to prevent two runs publishing out of order.
7. Define group-count and total-revenue reconciliation checks.
8. Plan retries, staging, error alerting, and recovery.

Explain why writing a pipeline that succeeds once is **not enough** to guarantee a trustworthy reporting table.

## 25. Key Takeaways

**`$out` publishes the entire pipeline output as a collection.** When the target exists, it builds the new output and swaps it in; old documents absent from the new snapshot are discarded. It fits **full refreshes** where the pipeline owns 100% of the target's contents.

**`$merge` writes per `on` key.** It can insert, replace, merge fields, keep existing, discard, or fail based on `whenMatched`/`whenNotMatched`. The `on` key must reflect true business identity backed by an appropriate unique index; target documents **that disappear from source output** are not deleted automatically.

**Failure semantics differ:** `$out` publishes via a snapshot replacement step, whereas `$merge` can commit partial writes before failing midway. Never treat `$merge` as a multi-document transaction, and never assume additive delta pipelines are retry-safe.

**Controlling target data impact is integral to aggregation design.** Preview results, verify keys and schemas, define field ownership, prevent concurrent overlapping runs, enforce idempotency on retries, track versions, and prepare recovery paths before deploying write stages to production. Choosing wisely between full snapshots and key-based upserts lets MongoDB both compute metrics and maintain reporting collections under clear data contracts.
