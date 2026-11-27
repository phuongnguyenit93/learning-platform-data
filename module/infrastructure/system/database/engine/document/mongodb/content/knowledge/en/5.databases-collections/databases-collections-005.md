# Read-Only Views: Definition, Querying, and Limitations in MongoDB

## 1. The Concept of Views in MongoDB

A **view (standard view)** in MongoDB is a queryable object similar to a collection, whose contents are **defined by an aggregation pipeline** over another collection or view. When a client queries a view, MongoDB executes the view's defining pipeline, combines it with the client's query criteria, and returns the results.

A standard view has three key characteristics:

1. **Read-only:** supports queries, while disallowing direct `insert`, `update`, `replace`, or `delete` operations against the view itself.
2. **Stores no materialized copy of results:** MongoDB stores the view's **definition**, not all documents returned by the view.
3. **Results reflect source data at query time:** after the source collection changes, subsequent queries on the view return updated results without requiring a manual "refresh."

Conceptual diagram:

~~~text
Application
   |
   |  find() / aggregate()
   v
VIEW: paid_orders_public
  pipeline: $match(status=PAID) -> $project(public fields)
   |
   v
COLLECTION: orders (stores real documents; can be updated)
   |
   v
Query results computed on demand
~~~

For example, an `orders` collection contains pending orders, paid orders, and internal notes. We can create a `paid_orders_public` view that presents only paid orders and exposes only the fields needed by a reporting screen.

### How Do Views Differ from Collections?

| Criterion | Collection | Standard View |
| --- | --- | --- |
| Stores actual documents | Yes | No; stores only the pipeline definition |
| `find()`, `aggregate()` | Yes | Yes, with certain limitations |
| `insertOne()`, `updateOne()`, `deleteOne()` | Yes, if permitted | No |
| Standard B-tree/compound indexes | Created directly | Cannot be created directly; relies on source indexes |
| When source data changes | Documents in the collection change | View results reflect changes on the next read |
| Best suited for | Operational data, source of truth | Reusable query layer, field filtering, data presentation |
| Query cost | Depends on query and collection indexes | Includes executing the view pipeline plus the client query |

**Note:** "View" here refers to a *standard view*. MongoDB also supports **on-demand materialized views**, created by writing aggregation output into a collection. The two concepts differ in storage, updating, and optimization; see Section 10.

## 2. Preparing Practice Data

You can run these examples on MongoDB Community/Enterprise or MongoDB Atlas via **mongosh**. Practice in a dedicated database named `views_lab` to avoid affecting other data.

In `mongosh`:

~~~javascript
use views_lab

// Collection storing actual data.
db.orders.drop();

db.orders.insertMany([
  {
    _id: "O-1001",
    customerId: "C01",
    status: "PAID",
    amount: 250000,
    createdAt: ISODate("2026-01-10T08:00:00Z"),
    customerEmail: "a@example.test",
    internalNote: "Ad source A"
  },
  {
    _id: "O-1002",
    customerId: "C02",
    status: "PENDING",
    amount: 180000,
    createdAt: ISODate("2026-01-11T09:00:00Z"),
    customerEmail: "b@example.test",
    internalNote: "Awaiting payment confirmation"
  },
  {
    _id: "O-1003",
    customerId: "C01",
    status: "PAID",
    amount: 125000,
    createdAt: ISODate("2026-02-02T10:00:00Z"),
    customerEmail: "a@example.test",
    internalNote: "Returning customer"
  },
  {
    _id: "O-1004",
    customerId: "C03",
    status: "PAID",
    amount: 300000,
    createdAt: ISODate("2026-02-08T13:00:00Z"),
    customerEmail: "c@example.test",
    internalNote: "Priority shipping"
  }
]);

db.orders.find().sort({ _id: 1 });
~~~

The `orders` collection has four documents, three of which have `status: "PAID"`. The two fields `customerEmail` and `internalNote` will not appear in the view defined below.

> The sample data and `example.test` email addresses here are purely illustrative placeholders. To demonstrate field masking, we omit fields unnecessary for a reporting UI; this lesson does not create users or configure authentication.

## 3. Creating a View with `db.createView()`

General syntax:

~~~javascript
db.createView(
  "<viewName>",
  "<sourceCollectionOrView>",
  [ /* aggregation pipeline */ ],
  { collation: { /* optional */ } }
);
~~~

Parameters:

- `viewName`: name of the view used for querying.
- `sourceCollectionOrView`: name of the source collection or view **within the same database**, not a database-prefixed name.
- `pipeline`: array of aggregation stages describing how to filter, compute, or transform source data.
- `collation`: optional default string comparison/sorting rules for the view.

Create a view showing only paid orders:

~~~javascript
db.createView(
  "paid_orders_public",
  "orders",
  [
    { $match: { status: "PAID" } },
    {
      $project: {
        _id: 1,
        customerId: 1,
        amount: 1,
        createdAt: 1,
        month: {
          $dateToString: {
            format: "%Y-%m",
            date: "$createdAt",
            timezone: "UTC"
          }
        }
      }
    }
  ]
);
~~~

The pipeline has two stages:

1. `$match` keeps documents whose status is `PAID`.
2. `$project` restricts returned fields and derives `month` from `createdAt`.

A document returned from the view looks like:

~~~javascript
{
  _id: "O-1001",
  customerId: "C01",
  amount: 250000,
  createdAt: ISODate("2026-01-10T08:00:00.000Z"),
  month: "2026-01"
}
~~~

Neither `customerEmail` nor `internalNote` is present because they were omitted from `$project`. MongoDB still preserves both fields in the `orders` collection; the view only shapes **the data presented to readers**.

### Equivalent Creation Using `db.createCollection()`

You can also use `db.createCollection()` with `viewOn` and `pipeline`. Example creating another view:

~~~javascript
db.createCollection("pending_orders_public", {
  viewOn: "orders",
  pipeline: [
    { $match: { status: "PENDING" } },
    { $project: { _id: 1, customerId: 1, amount: 1 } }
  ]
});
~~~

Both approaches produce a **read-only standard view**, not a physical collection. You cannot use the same name for a view and a collection because both share the database's namespace.

## 4. Querying a View Like a Collection

Views support many familiar query operations such as `find()`, `findOne()`, `aggregate()`, `distinct()`, and `countDocuments()`.

### 4.1. `find()` and Filter Predicates

~~~javascript
// Read all paid orders.
db.paid_orders_public.find().sort({ createdAt: 1 });

// Find paid orders for customer C01.
db.paid_orders_public.find(
  { customerId: "C01" },
  { _id: 1, amount: 1, month: 1 }
).sort({ amount: -1 });

// Retrieve a single specific order.
db.paid_orders_public.findOne({ _id: "O-1001" });
~~~

The second query returns orders `O-1001` and `O-1003`, with amounts 250,000 and 125,000 respectively. Order `O-1002` does not appear because its status is `PENDING`, even though a client could query the source collection directly if granted permission.

### 4.2. Using `aggregate()` on a View

Views are very useful when multiple screens share the same filtering/projection logic while each screen performs its own aggregation.

~~~javascript
db.paid_orders_public.aggregate([
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { totalAmount: -1 } }
]);
~~~

Expected output from the initial sample data:

| `_id` | `orderCount` | `totalAmount` |
| --- | ---: | ---: |
| `C01` | 2 | 375000 |
| `C03` | 1 | 300000 |

If a monthly report is needed, use the `month` field already computed by the view:

~~~javascript
db.paid_orders_public.aggregate([
  {
    $group: {
      _id: "$month",
      totalAmount: { $sum: "$amount" },
      orders: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

From the initial four sample documents, `2026-01` has one PAID order totaling 250,000, and `2026-02` has two PAID orders totaling 425,000.

### 4.3. `countDocuments()` and `distinct()`

~~~javascript
// There are 3 paid orders in the initial dataset.
db.paid_orders_public.countDocuments({});

// There are 2 paid orders for C01.
db.paid_orders_public.countDocuments({ customerId: "C01" });

// Distinct customerIds appearing in PAID orders.
db.paid_orders_public.distinct("customerId");
~~~

These operations query the **logical result of the view**. Do not mistake it for a separate pre-computed table.

### 4.4. Combining the View Pipeline with the Client Query

When a client invokes:

~~~javascript
db.paid_orders_public.find({ customerId: "C01" });
~~~

Logically, MongoDB evaluates the sequence of conditions:

~~~text
Source orders
  -> $match {status: "PAID"}       (view definition pipeline)
  -> $project {customerId, ...}    (view definition pipeline)
  -> $match {customerId: "C01"}    (client condition)
  -> return results
~~~

The query engine can **optimize and reorder** stages to reduce the volume of data processed while preserving equivalent results. This is a logical mental model for understanding queries, not a claim of exact physical execution order across all MongoDB versions.

## 5. Views Reflect Live Data, Not Snapshots

To see that a view stores no copy of the data, insert a new PAID order into the source collection:

~~~javascript
db.orders.insertOne({
  _id: "O-1005",
  customerId: "C02",
  status: "PAID",
  amount: 90000,
  createdAt: ISODate("2026-02-12T09:00:00Z"),
  customerEmail: "b@example.test",
  internalNote: "New order"
});

db.paid_orders_public.find({ _id: "O-1005" });
~~~

Querying the view returns `O-1005` even though no insert was performed on the view. Now try updating `O-1002` from `PENDING` to `PAID`:

~~~javascript
db.orders.updateOne(
  { _id: "O-1002" },
  { $set: { status: "PAID" } }
);

db.paid_orders_public.find({ _id: "O-1002" });
~~~

Now `O-1002` satisfies the view filter and appears in the results. Conversely, changing an order's status from `PAID` to `CANCELLED` removes it from view results on subsequent reads.

**Key takeaway:** A view needs no "sync data" button because every query reads the source data. However, whether changes are visible across separate queries also depends on read timing, read concern, replica lag, and transaction semantics; a view does not itself provide a fixed or consistent cross-query snapshot.

## 6. Why Are Views Read-Only?

MongoDB cannot assume how to map a pipeline output document back to a source document. For instance, a view might:

- Filter out documents with `$match`.
- Strip fields required to update a record via `$project`.
- Aggregate multiple documents into one output via `$group`.
- Compute derived fields via `$addFields` or `$project`.
- Join data across multiple collections via `$lookup`.

In those cases, `updateOne()` on a "view result" would lack unambiguous rules for identifying the source document or propagating changes back. MongoDB therefore enforces **read-only semantics at the view object level**.

The following operations are invalid on a standard view:

~~~javascript
// Illustrating DISALLOWED operations on a view.
db.paid_orders_public.insertOne({
  _id: "O-9999",
  customerId: "C09",
  amount: 1000
});

db.paid_orders_public.updateOne(
  { _id: "O-1001" },
  { $set: { amount: 1 } }
);

db.paid_orders_public.deleteOne({ _id: "O-1001" });
~~~

Every write attempt against a view raises an error. The snippets above illustrate the restriction; do not run all three sequentially in a script without error handling.

To modify data, write to the **source collection**, then re-query the view:

~~~javascript
db.orders.updateOne(
  { _id: "O-1001" },
  { $set: { amount: 260000 } }
);

// The view automatically reflects the updated amount on the next query.
db.paid_orders_public.findOne({ _id: "O-1001" });
~~~

A view's read-only nature is distinct from **access permissions**. A user granted write permission on the source collection can still modify the source directly; a view does not "lock" underlying source data.

## 7. Inspecting, Modifying, and Dropping View Definitions

### 7.1. Listing Views and Definitions

Views appear alongside collections when listing namespaces:

~~~javascript
db.getCollectionNames();

// Retrieve metadata for a specific view.
db.getCollectionInfos({ name: "paid_orders_public" });
~~~

In metadata, a view object has `type: "view"` and an `options` field containing `viewOn` and `pipeline`. To verify whether a namespace is actually a view, inspect `type` in `getCollectionInfos()` rather than relying on naming conventions alone.

You can inspect the query execution plan:

~~~javascript
db.paid_orders_public.find({ customerId: "C01" }).explain("executionStats");
~~~

Depending on MongoDB version and query shape, `explain` output structures vary. The goal is to observe the expanded pipeline and verify whether the query leverages indexes on the source collection.

**Security note:** A view's pipeline definition is visible via `getCollectionInfos()` and `explain`. Never embed secrets, tokens, or sensitive values directly inside a pipeline definition assuming they are hidden from users with metadata access.

### 7.2. Modifying a View with `collMod`

To add a rule requiring `amount >= 200000`, use the `collMod` command:

~~~javascript
db.runCommand({
  collMod: "paid_orders_public",
  viewOn: "orders",
  pipeline: [
    { $match: { status: "PAID", amount: { $gte: 200000 } } },
    {
      $project: {
        _id: 1,
        customerId: 1,
        amount: 1,
        createdAt: 1,
        month: {
          $dateToString: {
            format: "%Y-%m",
            date: "$createdAt",
            timezone: "UTC"
          }
        }
      }
    }
  ]
});
~~~

After the change, the view returns only PAID orders meeting the amount threshold. In deployments with **access control**, modifying a view requires appropriate privileges; both `viewOn` and `pipeline` must be supplied in the updated definition.

When editing a view, provide the entire desired pipeline because this is a **definition replacement**, not a partial document update on a source collection.

### 7.3. Dropping and Recreating

If you need to rename a view, MongoDB has no **direct rename** operation for views. The standard workflow is to create a new view under the new name with the same definition, switch clients to the new name, and drop the old view once nothing depends on it.

To drop the view created earlier in this lesson:

~~~javascript
// Drops only the view; the orders collection remains intact.
db.pending_orders_public.drop();
~~~

For any view used by applications, verify dependencies before dropping it. Dropping a view does not delete source collection data, though queries targeting the old view name will immediately fail.

## 8. View Limitations: Operations, Indexes, and Performance

### 8.1. Restricted Operations

| Category | Behavior for Standard Views | Approach |
| --- | --- | --- |
| Direct `insert` / `update` / `delete` / `replace` | Not supported | Write to the source collection |
| `$out`, `$merge` inside the **view definition pipeline** | Not supported, including in nested pipelines | Run aggregation on the collection to produce materialized data |
| `renameCollection` / rename view | Not supported | Create a view with the new name, migrate clients, drop the old name |
| `mapReduce` on a view | Not supported | Use aggregation with supported stages |
| Queries using `$text` on a view | Not supported | Query the source collection or use an appropriate Search solution |
| `$` positional, `$elemMatch`, `$slice`, `$meta` projections in `find()` | Not supported on views | Express `$project`, `$filter`, `$slice`, etc. inside the aggregation pipeline where supported |
| Creating **general indexes** directly on a standard view | Not supported | Create indexes on the source collection |

Note exceptions for MongoDB Search / Vector Search on **compatible views** in versions and tiers that support those features. Those do not represent general-purpose B-tree indexes across all standard views. Always check documentation for your exact deployed MongoDB version when designing.

In addition, the source collection or view must reside in **the same database** as the view being created. A view can query another view; nested views increase reuse but also make pipeline execution more complex.

### 8.2. No Separate Standard Indexes on a View

B-tree indexes live on physical collections. For example:

~~~javascript
db.orders.createIndex({
  status: 1,
  customerId: 1,
  createdAt: -1
});
~~~

A view query filtering on `status` and `customerId` can leverage this index once the optimizer merges the view pipeline with the client query. However, **index usage depends on the actual pipeline**, stage order, index structure, and query predicates; simply having an index on the source does not guarantee every view query will be fast.

To verify, run `explain("executionStats")` and look for `IXSCAN`, `COLLSCAN`, documents examined, and execution time.

### 8.3. View Pipelines Incur Cost on Every Read

Because a view does not store result documents, complex queries using `$group`, `$lookup`, `$sort`, or heavy field transformations can consume significant CPU, RAM, and I/O.

MongoDB imposes memory limits on blocking stages such as blocking sorts and groups; spilling temporary files to disk depends on version and `allowDiskUseByDefault`/`allowDiskUse` settings. Starting in MongoDB 6.0, stages exceeding memory thresholds can generally spill to disk under default settings. If queries routinely process very large datasets, monitor disk usage and inspect execution plans.

Common optimizations:

1. Filter with `$match` as early as reasonable, especially on indexed source fields.
2. Keep `$project` lean; avoid expensive expressions unless needed.
3. Tune indexes on the source collection based on actual workload patterns.
4. Measure costs using `explain`, the profiler, and metrics rather than guessing.
5. Consider an **on-demand materialized view** or dedicated reporting collection when the same expensive result is recomputed repeatedly.

### 8.4. Snapshots and Read Concern

A standard view does not record per-change timestamps on the view itself and does not provide an independent **point-in-time / snapshot isolation** mechanism. Reading a view does not create a fixed "historical snapshot" you can revisit arbitrarily.

When the business requires a consistent snapshot or multi-collection transactions, evaluate **read concern**, transactions, deployment topology, and driver APIs directly rather than treating a view as a snapshot.

## 9. Collation, Access Control, and Data Safety

### 9.1. View Collation

**Collation** defines string comparison rules such as case sensitivity or Vietnamese diacritic sensitivity. When creating a view, you can specify a collation:

~~~javascript
db.createView(
  "paid_orders_collated",
  "orders",
  [{ $match: { status: "PAID" } }],
  { collation: { locale: "en", strength: 2 } }
);
~~~

Rules to remember:

- If no collation is specified, the view defaults to **simple binary comparison**; it does not automatically inherit the source collection's collation.
- Queries against the view must use the view's configured collation; attempting to override it with a different collation in a query raises an error.
- A view built on another view must maintain a collation compatible with the source view.
- Aggregations spanning multiple views, such as `$lookup` between views, require compatible collations.

Because `status` in our example uses fixed uppercase codes, a custom collation is unnecessary. For personal names or natural-language text, choose a locale and strength matching business rules.

### 9.2. Granting Read Access Only to a View

When MongoDB authentication and authorization are enabled, an account can be granted **`find`** access on a view **without granting `find` directly** on the underlying source collection. This is why views are helpful for applications that should only see a subset of data.

Conceptual access-control layout:

~~~text
Source: orders
  - contains customerEmail, internalNote, and detailed fields

View: paid_orders_public
  - contains only _id, customerId, amount, createdAt, month

Reporting account:
  - granted find on paid_orders_public
  - not granted find on orders
~~~

This model helps restrict what data an application can query through that account. Keep in mind, however:

- **A view is a read-only object; it does not create permissions by itself**—access is governed by MongoDB RBAC.
- Creating or modifying views under access control requires appropriate privileges, typically namespace management rights and source-read privileges per MongoDB's rules.
- View definitions can be exposed via metadata and `explain`; never hardcode secrets inside pipelines.
- Audit other views, direct source collection read rights, aggregation permissions, and other roles assigned to the account. A field-hiding view is ineffective if the same account can still read the source collection directly.

Views help limit **exposed fields**, but they do not replace comprehensive data security policies—especially when sensitive data is referenced inside pipelines or accessible via other paths.

## 10. Standard Views vs. On-Demand Materialized Views

Both models can represent aggregation results, yet their storage mechanisms differ:

| Property | Standard View | On-Demand Materialized View |
| --- | --- | --- |
| Definition | `db.createView` or `db.createCollection` with `viewOn` | Aggregation writing output via `$merge` or `$out` |
| Stores output | No; computed on read | Yes; stored in a physical collection |
| Updates when source changes | New queries re-read source | Must be re-run or refreshed via a scheduled/triggered workflow |
| Cost of frequent reads | Can be high if pipeline is heavy | Generally lower since results are pre-computed |
| Standard indexes | Cannot be created directly on the view | Can be created on the target collection |
| Direct writes to output | No | Target collection can be written to, depending on design |
| Best suited for | Shared filtering/projection, live dynamic queries | Complex reports, pre-aggregated metrics, read optimization |

Example creating a collection holding total paid amount per customer from `orders`:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$customerId",
      totalPaid: { $sum: "$amount" }
    }
  },
  {
    $merge: {
      into: "paid_totals_snapshot",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
~~~

The output resides in the **physical collection** `paid_totals_snapshot`, which can be queried with `find()` and indexed like any normal collection.

~~~javascript
db.paid_totals_snapshot.find().sort({ totalPaid: -1 });
~~~

Important: this is **the result as of that pipeline run**, not auto-synchronized when `orders` changes. If a customer no longer has any PAID orders and disappears from the latest aggregation output, `$merge` configured as above **does not automatically delete** that customer's stale document in the target collection. To keep output accurate to business rules, design a refresh mechanism, prune stale records, or rebuild the snapshot cleanly.

**Never place `$merge` or `$out` inside a standard view's defining pipeline.** When your goal is persisting aggregation output to a collection, run the aggregation against the source and write output via a dedicated pipeline.

## 11. Common Errors When Using Views

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `insertOne`/`updateOne` on a view fails | Standard views are read-only | Write to the source collection |
| Creating view fails due to `$merge`/`$out` | View pipeline contains a write stage | Remove the write stage from the view definition; use a materialized collection if needed |
| Creating a view referencing a source in another database | Views require the source to be in the same database | Place the view in the same DB as the source or redesign the data/pipeline |
| `$text` query on a view is rejected | `$text` is not supported on views | Query the source collection or use an appropriate Search solution |
| Cannot create a B-tree index on a view | Views do not store physical documents | Create indexes on the source collection and check `explain` |
| View queries are slow | Pipeline recomputes on every read; source indexes are suboptimal | Tune the pipeline/indexes or consider materialization |
| View omits expected new orders | New data does not satisfy `$match`, or fields were stripped by `$project` | Inspect source documents and the defining pipeline |
| Unexpected string comparison results | View collation differs from assumptions | Check collation specified at view creation and verify comparison semantics |
| `Unauthorized` when creating/modifying/querying view | Account lacks required namespace privileges | Review privileges and roles on the view, source collection, and database |
| View breaks after renaming/dropping source collection | View definition still points to the old namespace | Update `viewOn`/pipeline or restore the source per dependency requirements |

When troubleshooting, a solid diagnostic sequence is to inspect `db.getCollectionInfos({name: ...})`, verify the `viewOn` namespace, read each pipeline stage, check source data, verify permissions, and finally inspect `explain` for performance issues. Never alter source data just to "make a view return rows" before understanding its filter logic.

## 12. Hands-On Exercises

### Exercise 1 — Status-Filtering View

Create a view `pending_orders_view` from `orders` containing only orders with `status: "PENDING"`, projecting `_id`, `customerId`, and `amount`. Query the list, insert a new PENDING order into the source collection, and query again to observe dynamic updates.

### Exercise 2 — Customer Summary View

Create a view `paid_amount_by_customer` from `orders` using this pipeline:

~~~javascript
db.createView(
  "paid_amount_by_customer",
  "orders",
  [
    { $match: { status: "PAID" } },
    {
      $group: {
        _id: "$customerId",
        orderCount: { $sum: 1 },
        totalPaid: { $sum: "$amount" }
      }
    }
  ]
);
~~~

Try running `find({ totalPaid: { $gte: 200000 } })` on the view. Explain why this query does not automatically benefit from an index on `totalPaid`, since it is computed during aggregation.

### Exercise 3 — Permissions and Read-Only Limits

List the operations supported directly on a standard view, try `distinct` and `countDocuments`, and predict what happens if you run `updateOne` on the view. Demonstrate how to change data **through the source collection** so the view reflects the new state.

### Exercise 4 — Observing the Optimizer

Create indexes on `orders.status` and `orders.customerId`, then run `explain("executionStats")` on a query against `paid_orders_public`. Compare documents examined, winning plan stages, and execution plan before and after indexing. Only evaluate index effectiveness on a sufficiently large dataset or with proper profiling tools; a four-document collection can easily cause the optimizer to pick a collection scan even when indexes exist.

### Exercise 5 — Choosing the Right Approach

A dashboard needs a revenue-per-customer report every 15 minutes. The aggregation uses multiple `$lookup` stages, takes a long time to run, and order volume keeps growing. Analyze when to use a standard view to avoid repeating pipeline definitions and when to materialize results into a collection using `$merge` or `$out`. If using `$merge`, explain how to handle customers who no longer appear in the source output so stale report entries are avoided.

## 13. Key Takeaways Summary

A MongoDB standard view is a **named query layer** defined by an aggregation pipeline. Views are computed on demand, making them well suited for reusing filtering/projection logic, offering a uniform read interface, and restricting visible fields for authorized accounts. Because they do not store results in a separate collection, views cannot accept direct writes, cannot have their own standard indexes, and rely on the pipeline and source collection for performance.

When computations are heavy yet read repeatedly, consider materializing results into a collection with an explicit synchronization strategy. Effective view usage always pairs with access control, pipeline discipline, and execution plan inspection.

### Official Documentation for Further Reference

- [Views — MongoDB Manual](https://www.mongodb.com/docs/manual/core/views/): standard view concepts, read-only behavior, indexes, and limitations.
- [Create and Query a View](https://www.mongodb.com/docs/manual/core/views/create-view/): `db.createView`, `db.createCollection`, query examples, and pipeline restrictions.
- [Supported Operations for Views](https://www.mongodb.com/docs/manual/core/views/supported-operations/): list of commands supported on views.
- [Modify or Remove a View](https://www.mongodb.com/docs/manual/core/views/update-view/): updating pipelines with `collMod` and dropping views.
- [Create a View with Default Collation](https://www.mongodb.com/docs/manual/core/views/specify-collation/): collation rules.
- [On-Demand Materialized Views](https://www.mongodb.com/docs/manual/core/materialized-views/): persisting aggregation results with `$merge` and `$out`.
