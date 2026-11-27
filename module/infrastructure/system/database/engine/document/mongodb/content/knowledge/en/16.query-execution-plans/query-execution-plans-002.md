# Reading COLLSCAN, IXSCAN, FETCH, and SORT in MongoDB Query Plans

## 1. Goal: Understand What MongoDB Did to Return Results

A MongoDB query can return the right results and still be very slow. For instance, an API only needs the 20 newest orders for a customer, yet the database has to read hundreds of thousands of documents, sort them, and only then pick 20 records. Conversely, a query can sometimes be fast even if MongoDB scans the collection, because the collection is tiny or most of the data must be read anyway.

To decide whether to add an index, change the field order in an index, or optimize pagination, developers must **read the execution plan** rather than merely observing response times.

The four most important foundational stages are:

- **COLLSCAN — Collection Scan:** scans the documents in a collection.
- **IXSCAN — Index Scan:** traverses keys in an index to locate candidate documents.
- **FETCH:** reads the source documents, typically to retrieve fields absent from the index or evaluate conditions not resolved by the index.
- **SORT:** sorts results in a separate step when the desired order cannot be read directly from an index.

They appear as a **tree or chain of stages** in **`explain()`** output. Depending on the MongoDB version and whether the classic or slot-based execution engine (SBE) is used, the plan representation may vary, but the core concepts of index scanning, document fetching, and sorting remain essential.

After this lesson, you will be able to:

1. Run explain at the **queryPlanner**, **executionStats**, and **allPlansExecution** levels.
2. Read a plan tree from child stages upward, understanding processing order and where filter conditions are applied.
3. Identify when a query performs a COLLSCAN and when it uses IXSCAN yet still performs many FETCHes.
4. Distinguish between an **index supporting a filter** and an **index supporting a sort**.
5. Recognize a **covered query** that avoids FETCH thanks to a matching projection and index.
6. Compare **totalKeysExamined**, **totalDocsExamined**, and **nReturned** to pinpoint bottlenecks.
7. Use **hint** in a test environment, avoiding performance conclusions drawn from a handful of documents or a single run.

> Examples run in **mongosh** against a dedicated database **mongo_plan_lab**. The lesson uses illustrative sample plans; actual stages and numbers may vary with server version, query engine, indexes, data, and statistics.

## 2. What Is a Query Plan?

Upon receiving a `find` command, MongoDB must decide on a sequence of operations:

~~~text
Receive filter + sort + projection + limit
                |
                v
        Check available indexes
                |
                v
      Estimate / select a plan
                |
                v
   Scan index keys or scan collection
                |
                v
   Evaluate unresolved conditions
                |
                v
       Sort, projection, limit...
                |
                v
           Return documents
~~~

The **query planner** chooses how to access the data; the **execution engine** carries out that plan. `explain` lets you inspect part of the selection process and execution metrics for evaluation.

### 2.1. Distinguishing the Plan from the Query Text

Two queries look quite similar:

~~~javascript
db.orders.find({ tenantId: "tA", status: "pending" });

db.orders.find({ tenantId: "tA", status: "pending" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Yet their requirements differ. The first query only needs to find matching documents; the second also requires **ordering** and **limiting the record count**. A good index for the first query may fail to provide the sort order needed by the second.

Beyond the filter, index and plan selection are influenced by:

- The data and condition selectivity.
- Presence or absence of sort, limit, skip, and projection.
- Field order in a compound index.
- Arrays and multikey indexes.
- Collation and index options such as partial/sparse.
- Data distribution, document count, and cache state.
- Replica set/sharded cluster topology and MongoDB version.

**A plan is considered good when it satisfies the query requirements at low total cost**, not simply because it contains an IXSCAN stage.

### 2.2. Stages Are Execution Steps, Not Error Messages

Illustrative tree example:

~~~text
LIMIT
  |
  +-- FETCH
        |
        +-- IXSCAN
~~~

You can read from the **bottom up** to trace data flow: **IXSCAN** locates keys in the index, **FETCH** retrieves the corresponding documents, and **LIMIT** caps the returned results. This is a conceptual diagram; MongoDB may place projection, limit, or filter in different positions depending on the plan and representation.

Similarly:

~~~text
SORT
  |
  +-- COLLSCAN
~~~

means the database scans documents and then performs a separate sort. With large data and no suitable index, both the scan and the sort can be resource-intensive.

## 3. How to Call `explain` and Read the Returned Structure

### 3.1. Three Verbosity Levels

In mongosh:

~~~javascript
db.orders.find({ status: "pending" })
  .explain("queryPlanner");

db.orders.find({ status: "pending" })
  .explain("executionStats");

db.orders.find({ status: "pending" })
  .explain("allPlansExecution");
~~~

| Level | Primary Information | When to Use |
| --- | --- | --- |
| **queryPlanner** | Chosen plan, candidate/rejected plan details | Want to see plan structure without needing execution metrics |
| **executionStats** | Adds execution metrics for the winning plan | Diagnose keys/documents examined and result counts |
| **allPlansExecution** | Adds trial execution details for candidate plans, when available | Deep analysis of plan selection decisions |

In many situations, calling **.explain("executionStats")** is the most useful starting point: you see both the plan structure and the evaluation numbers.

Notes:

- **Explain executes through a diagnostic mechanism**, which is not identical to a normal application call.
- Explain bypasses or does not warm up the plan cache the way regular commands do, so never use a single explain run as a production latency benchmark.
- To measure real latency, use application metrics, the profiler, or an appropriate observability system in addition to reading explain.
- Queries may execute fast on the database yet seem slow due to network or serialization; server metrics in explain do not cover every part of an API call.

### 3.2. Common Places to Read in the Output

An explain result for `find` typically includes these branches:

~~~text
explain
  queryPlanner
    namespace
    parsedQuery
    winningPlan
    rejectedPlans
  executionStats
    nReturned
    executionTimeMillis
    totalKeysExamined
    totalDocsExamined
    executionStages
  serverInfo
  ...
~~~

In the classic engine, stages usually appear under **winningPlan.stage** and nested **inputStage** or **inputStages**. With SBE, you may see **winningPlan.queryPlan** alongside a **slotBasedPlan** representation, or different detailed stages inside **executionStats.executionStages**.

Therefore, **do not write parsing tools assuming stages always live at a single fixed JSON path**. When inspecting directly, look at **queryPlanner.winningPlan** and **executionStats.executionStages**, following the plan branches actually returned by the server.

### 3.3. Reading Stages Bottom-Up

Illustrative example, not copied from a specific server output:

~~~json
{
  "stage": "FETCH",
  "inputStage": {
    "stage": "IXSCAN",
    "indexName": "ix_tenant_status_created",
    "indexBounds": {
      "tenantId": ["[\"tA\", \"tA\"]"],
      "status": ["[\"pending\", \"pending\"]"]
    }
  }
}
~~~

Interpretation:

1. **IXSCAN** reads the index named `ix_tenant_status_created`.
2. **indexBounds** shows the key range scanned for each field.
3. **FETCH** retrieves documents to complete work that cannot be satisfied directly from the index.

This illustrates how to read a plan, not a promise that MongoDB will always emit those exact two stages for every similar indexed query.

## 4. Lab: Creating Re-runnable Data and Indexes

The dataset consists of **36 orders** with fixed IDs from **o001** to **o036**; tenant **tA** has 24 orders and tenant **tB** has 12 orders. Data includes statuses pending/paid/shipped/cancelled, `createdAt` timestamps, `total` amounts, and `customerId`.

The indexes are chosen to demonstrate multiple scenarios: collection scans, index scans with FETCH, index scans that can cover a query, and sorts supported or unsupported by an index.

### 4.1. Data Setup Script

Run the following block in mongosh. The script cleans up only documents tagged with **dataset: "plan-stages-v1"** in **mongo_plan_lab.lab_orders**, then recreates the data.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_plan_lab");
  const orders = lab.getCollection("lab_orders");
  const tag = "plan-stages-v1";

  orders.deleteMany({ dataset: tag });

  const statuses = ["pending", "paid", "shipped", "cancelled"];
  const documents = [];

  for (let i = 1; i <= 36; i++) {
    const id = "o" + String(i).padStart(3, "0");

    documents.push({
      _id: id,
      dataset: tag,
      tenantId: i <= 24 ? "tA" : "tB",
      customerId: "c" + String(((i - 1) % 3) + 1),
      status: statuses[(i - 1) % statuses.length],
      createdAt: new Date(Date.UTC(2026, 3, 1, 0, i, 0)),
      total: NumberInt(60 + ((i * 7) % 19) * 13),
      note: i % 5 === 0 ? "manual-review" : "normal",
      lines: [
        { sku: "SKU-" + String(i).padStart(3, "0"), qty: 1 }
      ]
    });
  }

  orders.insertMany(documents);

  // Can filter by tenant then fetch newest orders.
  orders.createIndex(
    { dataset: 1, tenantId: 1, createdAt: -1, _id: -1 },
    { name: "ix_tenant_created" }
  );

  // Filter by tenant, status and sort by time.
  orders.createIndex(
    {
      dataset: 1, tenantId: 1, status: 1,
      createdAt: -1, _id: -1
    },
    { name: "ix_tenant_status_created" }
  );

  // Filter by customer, does not contain note/lines.
  orders.createIndex(
    { dataset: 1, tenantId: 1, customerId: 1 },
    { name: "ix_tenant_customer" }
  );

  // Filter/sort by amount within a tenant.
  orders.createIndex(
    { dataset: 1, tenantId: 1, total: 1 },
    { name: "ix_tenant_total" }
  );

  printjson({
    all: orders.countDocuments({ dataset: tag }),
    tenantA: orders.countDocuments({ dataset: tag, tenantId: "tA" }),
    pendingTenantA: orders.countDocuments({
      dataset: tag, tenantId: "tA", status: "pending"
    })
  });
})();
~~~

Expected counts:

| Filter | Document Count |
| --- | ---: |
| dataset = plan-stages-v1 | 36 |
| dataset and tenantId = tA | 24 |
| dataset, tenantId = tA, status = pending | 6 |

Because IDs and values are generated deterministically, re-running the script resets the practice data to its initial state. Never run this script on a production database or a collection holding important shared data.

### 4.2. Checking Existing Indexes

~~~javascript
const orders = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

printjson(orders.getIndexes());
~~~

You will see the default **_id_** index and the four indexes just created. **getIndexes** shows index definitions; to know whether a query **actually uses** an index, inspect explain rather than inferring from index existence.

### 4.3. Helper Function for Concise Stats

Explain output is verbose. The following function extracts **operation-level** statistics and prints the winningPlan shape for easier inspection:

~~~javascript
function inspectExplain(label, cursor) {
  const e = cursor.explain("executionStats");
  const stats = e.executionStats || {};

  print("== " + label + " ==");
  printjson({
    nReturned: stats.nReturned,
    totalKeysExamined: stats.totalKeysExamined,
    totalDocsExamined: stats.totalDocsExamined,
    executionTimeMillis: stats.executionTimeMillis
  });

  print("Winning plan:");
  printjson(e.queryPlanner && e.queryPlanner.winningPlan);
  return e;
}
~~~

This helper is meant for **unsharded find** queries in the lab. For `aggregate` with `$cursor`, sharded environments, or complex SBE outputs, information may reside in other branches and requires inspecting the actual server structure; do not treat this helper as a universal multi-version explain library.

## 5. COLLSCAN: Reading Documents Directly from the Collection

### 5.1. What Does COLLSCAN Mean?

**COLLSCAN** stands for collection scan: MongoDB iterates through documents in the collection to evaluate criteria. If the filter has no suitable index, or the collection is very small, the planner may pick COLLSCAN.

One way to visualize it:

~~~text
COLLSCAN:
  read document 1 -> check filter
  read document 2 -> check filter
  read document 3 -> check filter
  ...
~~~

If a collection has 10 million documents, a query looking for one rare document by scanning most of the collection can be extremely expensive. Yet if you genuinely need to read most of the collection to generate a report, a sequential scan can be more sensible than traversing an index and FETCHing nearly every document.

**COLLSCAN does not automatically mean a bad query.** Consider data size, result selectivity, latency targets, and resource usage.

### 5.2. Forcing COLLSCAN to Study the Mechanism

In the lab, use **hint({ $natural: 1 })** to request scanning in the collection's natural order instead of letting the planner choose an index:

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

inspectExplain(
  "Force collection scan",
  c.find({
    dataset: "plan-stages-v1",
    tenantId: "tA",
    status: "pending"
  }).hint({ $natural: 1 })
);
~~~

Expect to see **COLLSCAN** or its equivalent in the plan. From the seed data, the query returns **6** documents, yet to find them, the scan may examine virtually all **36** documents.

**Do not use `$natural` as a default optimization trick**; it is used here to create a comparison case. Never rely on natural order for stable pagination.

### 5.3. When Is COLLSCAN a Red Flag?

COLLSCAN warrants investigation if:

- An API runs frequently, returning only a few documents from a very large collection.
- `totalDocsExamined` is many times higher than `nReturned`.
- p95/p99 latency is high or grows alongside collection size.
- The filter is selective yet lacks an appropriate index.
- Downstream blocking sort/aggregation stages must process a large set.

Conversely, COLLSCAN can be normal for tiny collections or queries that genuinely retrieve nearly all data.

## 6. IXSCAN: Using Index Keys to Pick Candidates

### 6.1. IXSCAN Does Not Mean "Read Once and You Have the Document"

**IXSCAN** traverses index entries. If an index has the keys:

~~~javascript
{
  dataset: 1,
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

and the query has:

~~~javascript
{
  dataset: "plan-stages-v1",
  tenantId: "tA",
  status: "pending"
}
~~~

MongoDB can restrict the scan to the key slice matching that dataset, tenant, and status; it does not need to scan every document in the collection.

### 6.2. Using `hint` to Observe a Specific Index

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

inspectExplain(
  "Index on tenant + status",
  c.find({
      dataset: "plan-stages-v1",
      tenantId: "tA",
      status: "pending"
    })
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .hint("ix_tenant_status_created")
);
~~~

From the seed data, the three newest pending orders for tenant `tA` are **o021**, **o017**, and **o013**.

In the plan, look for:

- **IXSCAN**: traversing index keys.
- **indexName**: name of the index used.
- **keyPattern**: field order and sort directions in the index.
- **indexBounds**: key ranges examined for each field.
- **direction**: scan direction, when shown in the plan.
- **isMultiKey/multiKeyPaths**: multikey info if the index includes an Array field.

Example of **conceptual indexBounds** (actual field names and notation may vary):

~~~text
dataset:   exact "plan-stages-v1"
tenantId:  exact "tA"
status:    exact "pending"
createdAt: scan in descending order
_id:       scan in descending order when needed
~~~

Equality conditions narrow the index range scanned; `createdAt`/`_id` preserve result order. However, **IXSCAN only produces candidates**. If the query needs fields not present in the index, MongoDB still has to FETCH the documents.

### 6.3. Scanning Many Index Keys Does Not Guarantee Few Documents

Suppose an index on `tags` is multikey and one document has dozens of tags. A single document can contribute many index keys. A query scanning many keys yet returning few documents can happen due to:

- Multiple index keys pointing to the same document.
- Broad `indexBounds`.
- Part of the filter not being applied during IXSCAN and checked later.
- Many entries eliminated while scanning the index.

Therefore, **totalKeysExamined** and **totalDocsExamined** must be read alongside **nReturned**; never judge from a single number alone.

## 7. FETCH: When Source Documents Must Be Read

### 7.1. Why Still FETCH After Using an Index?

An index stores indexed field values and pointers needed to locate documents—it **does not automatically store every field of the document**. For example, the index:

~~~javascript
{
  dataset: 1, tenantId: 1, status: 1,
  createdAt: -1, _id: -1
}
~~~

does not contain **note** or **lines**. If the application needs `note` or `lines` returned, MongoDB generally must read the document from the collection after IXSCAN identifies candidates.

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

inspectExplain(
  "IXSCAN then FETCH to retrieve note",
  c.find(
      {
        dataset: "plan-stages-v1",
        tenantId: "tA",
        status: "pending"
      },
      {
        _id: 1,
        createdAt: 1,
        note: 1,
        lines: 1
      }
    )
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .hint("ix_tenant_status_created")
);
~~~

In the classic plan representation, you may see **FETCH > IXSCAN** along with a projection stage above it. With SBE, FETCH or equivalent operations may appear in different layers; inspect the actual plan output.

### 7.2. FETCH Can Also Evaluate Unindexed Filter Conditions

Beyond projection, a filter condition **not covered by the index** may be evaluated after fetching the document.

~~~javascript
inspectExplain(
  "note condition not in index",
  c.find({
      dataset: "plan-stages-v1",
      tenantId: "tA",
      status: "pending",
      note: "manual-review"
    })
    .hint("ix_tenant_status_created")
);
~~~

With that index, the first three equality conditions narrow the candidate set, but **note** must be checked afterward. In a classic plan, the residual filter typically appears on FETCH; in SBE, the representation may differ.

Suppose the query ultimately returns one document, yet MongoDB has to FETCH thousands of candidate documents just to check `note`. That is a signal to evaluate:

- Is `note` an important filter field queried frequently?
- Should `note` be added to a compound index, or should a partial index be used?
- Can the filter be written more selectively on leading index fields?
- Is this query critical enough to justify extra index maintenance cost on every write?

**FETCH is not automatically a bug to eliminate at all costs.** A query returning 20 documents that needs a large `lines` field outside the index can FETCH 20 documents and easily meet its SLA. Adding `lines` to the index just to cover it could bloat the index or hit Array indexing limitations.

### 7.3. Distinguishing FETCH from COLLSCAN

Both shapes read documents, but they select candidates differently:

~~~text
COLLSCAN
  -> scan collection documents to find matches

FETCH
  +-- IXSCAN
  -> scan index to find candidates, then fetch needed documents
~~~

If IXSCAN is highly selective, FETCHing a few documents is usually great. If IXSCAN returns nearly the whole collection and FETCH reads all of them, total work may be no better than COLLSCAN—or even worse.

## 8. Covered Query: IXSCAN Without FETCH

### 8.1. When Is a Query Covered?

A **covered query** can obtain all information needed for filtering, sorting, and projection directly from the index without reading source documents. For example, given the index:

~~~javascript
{
  dataset: 1,
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

and a query requiring only fields already in that index:

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

inspectExplain(
  "Potentially covered query",
  c.find(
      {
        dataset: "plan-stages-v1",
        tenantId: "tA",
        status: "pending"
      },
      {
        _id: 0,
        status: 1,
        createdAt: 1
      }
    )
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .hint("ix_tenant_status_created")
);
~~~

The query still sorts by `_id`, which is already at the trailing position of the index. The projection returns only `status`/`createdAt`, and the filter fields are also in the index.

When truly covered, typical indicators include:

- **totalDocsExamined = 0**.
- **IXSCAN** present, with no FETCH reading source documents.
- **PROJECTION_COVERED** or an equivalent projection structure may appear in the plan.

**A covered query is a property of both the query and the index**, not a permanent "covered" label attached to an index.

### 8.2. Just Changing Projection Can Introduce FETCH

Keep the exact same filter and sort, but add **note**:

~~~javascript
inspectExplain(
  "Adding note requires reading documents",
  c.find(
      {
        dataset: "plan-stages-v1",
        tenantId: "tA",
        status: "pending"
      },
      {
        _id: 0,
        status: 1,
        createdAt: 1,
        note: 1
      }
    )
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .hint("ix_tenant_status_created")
);
~~~

Because `note` is not in the index, the document must be fetched to return that field. Comparing **totalDocsExamined** between the two explains demonstrates why projection directly affects the plan and I/O.

### 8.3. Exceptions to Watch Out For

Mentioning only indexed fields in filter/projection does not guarantee a covered query:

- If the projection returns **_id** while the index does not include `_id`, FETCH is usually required; exclude `_id` with **_id: 0** when the API does not need it.
- With **Array/multikey indexes**, covered queries have additional restrictions: you cannot return Array fields or use `$elemMatch` in ways that prevent covering.
- **Collation**, **partial indexes**, null/missing values, and conditions that cannot be fully resolved from the index can affect eligibility.
- Queries with filter predicates outside the index may require FETCH to evaluate them.

Therefore, only conclude a query is covered after checking the actual explain output—specifically **totalDocsExamined = 0** and the winning plan structure.

## 9. SORT: Separate Sorting vs. Index-Assisted Sorting

### 9.1. What Is SORT?

If no index provides the requested sort order, MongoDB must collect/evaluate candidates and then **sort** them. A **SORT** stage is typically a **blocking stage**: it must consume sufficient relevant input before emitting ordered output.

~~~text
SORT by total descending
  |
  +-- FETCH
        |
        +-- IXSCAN using index ordered by createdAt
~~~

A query can still use IXSCAN yet include SORT because **an index used for filtering may not help with sorting**. SORT can consume memory or spill to temporary disk space if volume is large and server settings/version permit spilling.

### 9.2. Forcing an Index with Mismatched Sort Order

In the lab:

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

inspectExplain(
  "createdAt index but sorting by total",
  c.find(
      {
        dataset: "plan-stages-v1",
        tenantId: "tA"
      },
      {
        _id: 1,
        total: 1,
        createdAt: 1
      }
    )
    .sort({ total: -1 })
    .limit(5)
    .hint("ix_tenant_created")
);
~~~

Index **ix_tenant_created** orders keys after dataset/tenant by **createdAt**, not `total`. MongoDB must re-sort by `total`, so **SORT** or an equivalent stage may appear in the plan.

**LIMIT does not mean MongoDB only looks at five documents.** To find the five highest `total` values, the query may have to examine many candidates first; when combining sort and limit, MongoDB uses optimizations like top-k sort, yet still performs work proportional to the input set.

### 9.3. Using an Index That Supports Sort

Another existing index is:

~~~javascript
{ dataset: 1, tenantId: 1, total: 1 }
~~~

Once equality on dataset/tenant is fixed, MongoDB can walk the index in **reverse direction** to satisfy **total: -1** without a separate SORT stage:

~~~javascript
inspectExplain(
  "total index supports sort",
  c.find(
      {
        dataset: "plan-stages-v1",
        tenantId: "tA"
      },
      {
        _id: 1,
        total: 1,
        createdAt: 1
      }
    )
    .sort({ total: -1 })
    .limit(5)
    .hint("ix_tenant_total")
);
~~~

Because the projection requests **createdAt**, the `total` index may still need FETCH. However, **avoiding FETCH is not a prerequisite for eliminating SORT**: an index can supply the exact sort order even when MongoDB must fetch documents for other fields.

### 9.4. Compound Index Field Order Determines SORT

Suppose an index is:

~~~javascript
{ dataset: 1, tenantId: 1, status: 1, createdAt: -1 }
~~~

Query:

~~~javascript
{
  dataset: "plan-stages-v1",
  tenantId: "tA",
  status: "pending"
}
// sort: { createdAt: -1 }
~~~

has equality predicates before `createdAt`; the index can provide the exact order for the `pending` status slice.

However, the query:

~~~javascript
{
  dataset: "plan-stages-v1",
  tenantId: "tA"
}
// sort: { createdAt: -1 }
~~~

does not fix `status`. Inside the index, keys are grouped by `status` first and then `createdAt`, so `createdAt` order is **not a global order across the entire tenant**. MongoDB may need SORT if it uses that index.

That is why a separate index **{dataset, tenantId, createdAt}** may still be needed for a screen listing all orders of a tenant.

### 9.5. A SORT Is Not Always Severe

Sorting a few dozen documents can be very cheap. Sorting millions of documents or large fields can be costly. When evaluating:

- How many documents enter SORT?
- Is there a sufficiently selective filter before SORT?
- Does sort combine with limit to reduce memory usage?
- How frequently is the query executed?
- Can an index supply the order, or would changing the index hurt filtering?

Do not create dedicated indexes for every rare sort just because you see a SORT stage in explain.

## 10. Four Scenarios on the Same Collection

From one dataset, you can compare four plan patterns:

| Case | Query / Index | Key Stages | What to Verify |
| --- | --- | --- | --- |
| A | Tenant/status filter, **hint $natural** | COLLSCAN | `totalDocsExamined` vs. `nReturned` |
| B | Tenant/status filter, status index, projection needs **lines** | IXSCAN + FETCH | Keys reduced, yet documents still fetched |
| C | Tenant/status filter, status index, projection only indexed fields | IXSCAN, possibly no FETCH | Is `totalDocsExamined` equal to 0? |
| D | Tenant filter, createdAt index, but sort by total | IXSCAN/FETCH + SORT | Does SORT disappear when switching to the total index? |

In a 36-document lab, measurements are purely instructional. A plan without FETCH might still be suboptimal on a different workload, and a COLLSCAN over a few dozen documents can be a completely sensible planner choice.

### 10.1. Quick Comparison Script

Run after defining **inspectExplain** in section 4.3:

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

const queue = {
  dataset: "plan-stages-v1",
  tenantId: "tA",
  status: "pending"
};

inspectExplain(
  "A - COLLSCAN",
  c.find(queue).hint({ $natural: 1 })
);

inspectExplain(
  "B - IXSCAN + FETCH",
  c.find(queue, { _id: 0, status: 1, lines: 1 })
    .hint("ix_tenant_status_created")
);

inspectExplain(
  "C - Potentially covered",
  c.find(queue, { _id: 0, status: 1, createdAt: 1 })
    .hint("ix_tenant_status_created")
);

inspectExplain(
  "D - SORT by total",
  c.find({
      dataset: "plan-stages-v1",
      tenantId: "tA"
    })
    .sort({ total: -1 })
    .limit(5)
    .hint("ix_tenant_created")
);
~~~

Result ordering can be non-deterministic for queries **without a sort**. Never rely on unsorted output order as the basis for pagination.

## 11. executionStats Metrics: Read by Ratios, Not Just Stage Names

### 11.1. Three Core Numbers

**nReturned:** number of documents returned by the operation after applying all required plan steps.

**totalDocsExamined:** number of document inspections performed during execution. Not necessarily equal to distinct documents if a plan can examine the same document multiple times.

**totalKeysExamined:** number of index entries examined during execution. For a pure COLLSCAN, this can be 0.

Suppose an illustrative explain for a query returning 20 documents shows:

~~~text
nReturned         = 20
totalKeysExamined = 50000
totalDocsExamined = 12000
~~~

These are **hypothetical numbers**, not lab output. The query examined very many keys and documents to return 20 results; inspect `indexBounds`, residual filters on FETCH, and sorting.

Another case:

~~~text
nReturned         = 20
totalKeysExamined = 20
totalDocsExamined = 20
~~~

is typically a healthy sign for a query returning 20 documents, though you still need to consider latency, document size, resource usage, and real system impact.

### 11.2. Scan Ratios for Diagnosis

You can track these reference ratios:

~~~text
documentsExamined / max(nReturned, 1)
keysExamined      / max(nReturned, 1)
~~~

High ratios indicate MongoDB is doing substantial work per returned result. However, there is no universal "bad" threshold for all queries:

- **Aggregations** summing across all documents intentionally return one row after scanning millions of documents.
- **countDocuments** also differs from a top-20 query.
- **Pagination with a large skip** may traverse many keys before returning 20 items.
- **Multikey indexes** can have many keys per document due to arrays.
- **Covered queries** can have `totalDocsExamined = 0` yet still scan very many keys.

Thus, ratios are signals for asking questions, not an absolute quality score.

### 11.3. `nReturned` Differs Per Stage

Inside explain, an IXSCAN stage may emit many candidates; FETCH or FILTER discards some; LIMIT keeps only the requested count. Hence **nReturned** at individual stages does not always match operation-level **executionStats.nReturned**.

Conceptual example:

~~~text
IXSCAN:  1,000 candidate index entries
FETCH:     200 matching candidate documents after filtering
LIMIT:      20 documents returned to client
~~~

If you only read the number 20 and assume the database performed 20 units of work, you overlook the scanning volume happening in lower stages.

### 11.4. `executionTimeMillis` vs. Real Time

**executionTimeMillis** is reported by MongoDB inside explain, but it does not fully represent:

- Network or connection pool wait time.
- Document serialization/deserialization and application mapping.
- API gateway or authentication overhead.
- Warm vs. cold cache differences across runs.
- Concurrent workload and real traffic fluctuations.

Therefore, performance evaluation must combine explain with **application p50/p95/p99 latency**, server metrics, and resource utilization.

## 12. When Explain Differs from Documentation Examples: SBE, Aggregation, and Sharding

### 12.1. Classic Engine and Slot-Based Execution (SBE)

MongoDB has multiple plan representations depending on version and query characteristics. You may encounter:

- **queryPlanner.winningPlan.stage** in classic representation.
- **queryPlanner.winningPlan.queryPlan** and **slotBasedPlan** in SBE cases.
- **executionStats.executionStages** with differing stages/inputs.
- Specialized optimized stages for simple patterns that do not always print the exact sequence COLLSCAN/IXSCAN/FETCH/SORT.

Do not tie monitoring logic to one hardcoded JSON path without handling variants. A query may still use an index even if explain shows a specialized optimized stage name rather than the literal string **IXSCAN** where you expect it.

**Core concepts to keep constant:** whether the query scans the collection or an index, whether it fetches source documents, whether there is a blocking sort, and how many keys/documents are examined overall.

### 12.2. Aggregation Pipelines

Example:

~~~javascript
db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders")
  .explain("executionStats")
  .aggregate([
    {
      $match: {
        dataset: "plan-stages-v1",
        tenantId: "tA",
        status: "pending"
      }
    },
    { $sort: { createdAt: -1, _id: -1 } },
    { $limit: 3 },
    { $project: { _id: 1, status: 1, createdAt: 1 } }
  ]);
~~~

When MongoDB can push **$match**, **$sort**, and **$limit** down to the query layer, the plan can leverage indexes similarly to `find`. When a pipeline contains **$group**, **$lookup**, **$unwind**, or other stages, explain may include both a **$cursor** stage and separate aggregation stages.

An aggregation-layer SORT is not necessarily described identically to SORT in `find`. Inspect the corresponding sections, each stage's input volume, and how the optimizer reordered or pushed down stages to reduce work.

### 12.3. Sharded Clusters

For a sharded collection, a query may run across multiple shards and merge results:

~~~text
mongos / router
     |
     +---- shard A: IXSCAN -> FETCH
     |
     +---- shard B: IXSCAN -> FETCH
     |
     +---- merge / sort / limit
                  |
                  v
               results
~~~

Explain may include a **shards** branch, merge-related stages, and per-shard metrics. Total work does not reside in a single `winningPlan`. For queries missing the shard key, MongoDB may have to scatter across multiple shards; an index on each shard alone is not enough if routing and merging are costly.

Before concluding "the plan only reads 20 documents," check totals and per-shard breakdowns if the real system is sharded.

## 13. Optimization Workflow Starting from a Specific Explain

Suppose a screen needs the 20 newest pending orders for tenant `tA` yet p95 latency is high. Follow this sequence:

**Step 1 — Capture the real query shape.** Record filter, sort, projection, limit, collation, read preference, and server version. Note whether `skip` or array operations are involved.

**Step 2 — Collect explain("executionStats").** Inspect the winning plan, stages, `indexBounds`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`.

**Step 3 — Form hypotheses from the plan.**

- If **COLLSCAN** on a large collection with a selective filter → possibly missing an index.
- If **IXSCAN + FETCH** with many documents discarded after FETCH → filter is not sufficiently supported by the index.
- If **IXSCAN + SORT** on a large input set → index does not satisfy the sort.
- If **IXSCAN without FETCH** yet scanning too many keys → `indexBounds` may lack selectivity, or array structure causes fan-out.

**Step 4 — Propose candidate indexes** based on equality, sort, range fields, and other queries sharing the collection. Never pick an index for one query without assessing its impact on write workloads.

**Step 5 — Compare using `hint` in lab/staging.** Force two candidate indexes to understand stage-level differences; then remove the hint and verify what the planner chooses automatically. Hints in production should only be used with a verified operational reason.

**Step 6 — Measure latency and representative load.** Adding an index is not a win if one query speeds up by a few ms while inserts/updates slow excessively or index memory footprint balloons.

**Step 7 — Roll out with monitoring.** Watch other queries, behavior under changing workloads, drop redundant overlapping indexes once verified, and keep a rollback plan.

### 13.1. Example Index for a Pending Queue

Query:

~~~javascript
db.orders.find({
  dataset: "plan-stages-v1",
  tenantId: "tA",
  status: "pending"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Suitable index for the lab:

~~~javascript
{
  dataset: 1,
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

However, if another page needs **all statuses** sorted by `createdAt`, an index placing `status` before `createdAt` will not naturally provide a global order; a separate index may be needed. **A good query plan must be evaluated in the context of the full set of access patterns.**

### 13.2. Indexes and Sorting with Pagination

Paginating via:

~~~javascript
.skip(100000).limit(20)
~~~

can force MongoDB to traverse many records before returning the page. An index supporting sort avoids a blocking SORT, yet **does not eliminate the cost of skipping 100,000 results**. When deep pagination is frequent, keyset/cursor pagination on `(createdAt, _id)` can be more suitable.

In explain, compare keys examined against the mere 20 documents finally returned; understanding this gap is often more important than merely looking for a SORT stage.

## 14. Common Mistakes When Reading Plans

| Mistake | Why Is It Incorrect? | Proper Reading Approach |
| --- | --- | --- |
| Seeing COLLSCAN means you must add an index | Small collections or queries reading most data may sensibly use COLLSCAN | Check `totalDocsExamined`, `nReturned`, latency, and load |
| Seeing IXSCAN guarantees it is fast | It may scan huge key ranges or FETCH many documents | Read `indexBounds`, `totalKeysExamined`, and `totalDocsExamined` |
| Seeing FETCH means the index is useless | FETCH may retrieve just a few docs for fields outside the index | Check FETCHed doc count, projection, and SLA |
| No FETCH means the query is strictly optimal | A covered query can still scan a massive number of keys | Compare `keysExamined` with `nReturned` |
| Having SORT means a missing index | A small SORT can be cheaper than maintaining an extra index | Measure SORT input volume and query frequency |
| `Limit(10)` means only 10 documents are read | Filter/sort/skip may examine many candidates first | Read examined counts across stages |
| A sort in the query guarantees a SORT stage | An index can already provide the order | Check compound indexes and the winning plan |
| Having an index guarantees MongoDB uses it | The planner may pick COLLSCAN or another index | Inspect `winningPlan`, optionally test with `hint` |
| Measuring performance with one explain run | Explain does not replace benchmarks and production workloads | Combine app p95/p99, profiler, and server metrics |
| Stage missing at a familiar JSON path | Classic/SBE/aggregation/sharding format plans differently | Read the actual tree and `queryPlan`/`slotBasedPlan` branches |
| `totalDocsExamined` must always equal `nReturned` | Many candidate documents are filtered out after reading | Check filter stages and index bounds |
| `totalKeysExamined` must equal `totalDocsExamined` | Multikey, index-only queries, and scan/filter yield different ratios | Understand index keys, FETCH, and projection |
| Using `hint` guarantees an optimal plan | A hint can force a poor index or fail if the index is missing | Use in controlled experiments and remove when unneeded |
| If the query returns right results, the plan is fine | A correct query might read/sort huge data volumes | Combine correctness with execution metrics |
| Same query shape always gets the same plan | Data, indexes, plan cache, and server versions can change | Monitor for regressions and update measurements |

## 15. Practice Exercises

### Exercise 1 — Reading a Stage Tree

Given the diagram:

~~~text
PROJECTION_SIMPLE
   |
   +-- FETCH
         |
         +-- IXSCAN
~~~

Describe the order data flows from the index to the output. Why is FETCH present, and what must change in the projection/index for some queries to become covered?

### Exercise 2 — Comparing COLLSCAN and IXSCAN

In the lab, find `pending` orders for tenant `tA`. First force **hint({$natural:1})**, then force **ix_tenant_status_created**. Record `winningPlan`, `nReturned`, `totalDocsExamined`, and `totalKeysExamined`. Explain the difference without drawing production conclusions from timings on 36 documents.

### Exercise 3 — Projection and FETCH

Run the same tenant/status filter with two projections:

~~~javascript
{ _id: 0, status: 1, createdAt: 1 }

{ _id: 0, status: 1, createdAt: 1, lines: 1 }
~~~

Use hint **ix_tenant_status_created**. Predict which can be covered and which must FETCH, then compare the explains and `totalDocsExamined`.

### Exercise 4 — SORT with a Misaligned Index

Filter tenant `tA` then sort by `total` descending, limit 5. Compare plans when hinting **ix_tenant_created** versus **ix_tenant_total**. Why can both indexes assist filtering yet only one provide the required sort order?

### Exercise 5 — Conditions Evaluated at FETCH

Filter tenant/status/`note = manual-review` using index **ix_tenant_status_created**. Is `note` in the index? Measure documents examined. If this query ran hundreds of times per second, which index would you consider and what would you measure before adding it?

### Exercise 6 — Compound Index with an Intermediate Field

Index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Query A filters tenant/status and sorts by `createdAt`; query B filters only tenant and sorts by `createdAt`. Explain why query B may need SORT if forced onto the index above. Propose an appropriate index if query B is a hot screen.

### Exercise 7 — Scan Ratios

Three queries have illustrative numbers:

| Query | nReturned | totalKeysExamined | totalDocsExamined |
| --- | ---: | ---: | ---: |
| A | 20 | 20 | 20 |
| B | 20 | 100000 | 20000 |
| C | 1 | 1000000 | 0 |

For each query, calculate `keysExamined/nReturned` and `docsExamined/nReturned`, and suggest next investigation steps. Why can C avoid FETCHing documents yet still be expensive?

### Exercise 8 — Structural Plan Differences Due to SBE

Compare two hypothetical examples: one explain with **winningPlan.stage = "FETCH"** and **inputStage.stage = "IXSCAN"**, and another with **winningPlan.queryPlan** plus a **slotBasedPlan** branch. Explain how to identify the same underlying behavior ("reads an index and may fetch documents") without depending strictly on one JSON path.

### Exercise 9 — Aggregation and Sharding

Suppose an aggregation uses `$match`, `$sort`, and `$group` on a sharded collection. Distinguish per-shard plans from the merge phase. Why is seeing an IXSCAN on a single shard insufficient to conclude the entire query is fast?

### Exercise 10 — Slow Query Resolution Workflow

An API listing orders by tenant/status has p95 = 2 seconds, `nReturned = 20`, yet `totalDocsExamined = 100,000` and a SORT stage over a large set. Outline a plan: capture query shape, check index bounds/filters, design a compound index, benchmark on staging, compare with hint, and execute a monitored rollout.

## 16. MongoDB Reference Documentation

- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [cursor.explain()](https://www.mongodb.com/docs/manual/reference/method/cursor.explain/).
- MongoDB Manual — [Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/).
- MongoDB Manual — [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/).
- MongoDB Manual — [The ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/).
- MongoDB Manual — [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/).
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/).

**Conclusion:** **COLLSCAN** indicates MongoDB is scanning the collection; **IXSCAN** indicates it is traversing index keys; **FETCH** indicates it needs to read source documents or evaluate additional conditions; **SORT** indicates data must be sorted in a separate step when no suitable order is available from an index. Yet stage names are only the starting point. To evaluate a query, combine **indexBounds, totalKeysExamined, totalDocsExamined, nReturned, projection, sort, and workload context**. By reading explain as a tree of work rather than just hunting for the letters IXSCAN, you can choose indexes and tune queries based on evidence instead of guesswork.
