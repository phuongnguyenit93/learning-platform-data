# Impact of Array Structure on Multikey Indexes and MongoDB Query Plans

## 1. Why Does Array Structure Change Indexing Strategy?

MongoDB allows a document to store an array of scalar values or an array of embedded documents. That fits information frequently read together—such as product tags, color variants, review scores, or order line items. However, an **array is not like a scalar field** when MongoDB builds an index: a single document can contribute multiple index keys, and two conditions on an array can be satisfied by two different elements.

Example:

~~~javascript
{
  _id: "p001",
  category: "tech",
  tags: ["mongodb", "backend"],
  variants: [
    { color: "red", stock: 0 },
    { color: "blue", stock: 6 }
  ]
}
~~~

A query **has tag mongodb** can benefit from an index on tags. However, a requirement **has a variant that is both red and in stock** must use a condition binding the same element; you cannot simply match two independent subpaths and assume they belong to the same variant.

After this lesson, you will:

- Understand how a **multikey index** is formed from an Array and generates multiple keys per document.
- Distinguish **scalar Arrays** from **Arrays of embedded documents** when indexing and querying.
- Use **$elemMatch** to apply conditions to the same element and support index bound compounding.
- Understand limitations of **compound multikey indexes**, especially two independent Arrays.
- Read **IXSCAN**, **FETCH**, **SORT**, **indexBounds**, **isMultiKey**, and executionStats metrics.
- Weigh array length, index update costs, document size limits, and how to model growing data.

Examples use **mongosh** and a dedicated database **mongo_multikey_lab**. The dataset is fixed so it can be re-run cleanly. Real performance evaluations must be based on representative data and traffic, never treating results from a handful of documents as a benchmark.

## 2. How Do Multikey Indexes Work?

### 2.1. Scalar Fields vs. Array Fields

For a document:

~~~javascript
{ _id: "p001", category: "tech" }
~~~

A standard index on **category** stores one key for that document's tech value. For an Array:

~~~javascript
{ _id: "p001", tags: ["mongodb", "backend", "tutorial"] }
~~~

An index on **tags** must allow lookups by each element of the array:

~~~javascript
db.products.createIndex({ tags: 1 });
~~~

MongoDB **automatically creates a multikey index** when an indexed field contains an Array; no special multikey-type option is required when creating the index. Conceptually:

~~~text
Index value       Document pointed to
"backend"         -> p001
"mongodb"         -> p001
"tutorial"        -> p001
~~~

MongoDB creates entries for distinct values in the array. If the same value repeats inside one Array, it does not need to create duplicate entries pointing to that exact document. One document may appear under multiple different index keys, yet the result of find is **documents**, not multiplied index entries.

### 2.2. Subfields in Document Arrays

~~~javascript
{
  _id: "p001",
  variants: [
    { color: "red", stock: 0 },
    { color: "blue", stock: 6 }
  ]
}
~~~

You can index a subfield using dot notation:

~~~javascript
db.products.createIndex({ "variants.color": 1 });
~~~

The query:

~~~javascript
db.products.find({ "variants.color": "red" });
~~~

matches documents that have at least one variants element with color equal to red. When a field has multiple embedded elements, the index generates keys corresponding to element values along that path. There is no need to split out a separate collection solely to query by a subfield, though array size and update frequency still dictate which design is appropriate.

### 2.3. Array Shape Determines Cost

| Field Shape | Example | Impact on Index |
| --- | --- | --- |
| Scalar | category: "tech" | One key value per field |
| Scalar Array | tags: ["mongodb", "backend"] | Multiple keys from element values |
| Embedded Array | variants: [{color: "red"}, {color: "blue"}] | Index on path variants.color becomes multikey |
| Empty Array | tags: [] | No elements match tag equality checks |
| Array with duplicates | tags: ["sale", "sale"] | Does not emit two result documents for tag sale |
| Continuously growing Array | events: [unbounded events] | Key count and document size can grow rapidly |

MongoDB enforces a **16 MiB limit per BSON document**. Even before hitting that limit, oversized arrays increase write overhead, index size, network bandwidth, and contention when multiple operations update the same document.

## 3. Reproducible Sample Dataset and Indexes

We use six products under a single tenant. Each product has **tags** (String Array), **scores** (Number Array), and **variants** (document Array containing color and stock). The dataset intentionally includes a product where red is out of stock while blue is in stock to observe the effect of $elemMatch.

Run the entire block below in mongosh:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_multikey_lab");
  const products = lab.getCollection("lab_products");
  const tag = "multikey-practice-v1";
  const tenant = "lab-shop";

  // Clean up only documents belonging to this lesson's dataset.
  products.deleteMany({ dataset: tag });

  products.insertMany([
    {
      _id: "p001", dataset: tag, tenantId: tenant,
      category: "tech", name: "Backend Learning Kit",
      price: NumberDecimal("100.00"),
      tags: ["mongodb", "backend"],
      scores: [65, 95],
      variants: [
        { color: "red", stock: NumberInt(0) },
        { color: "blue", stock: NumberInt(6) }
      ]
    },
    {
      _id: "p002", dataset: tag, tenantId: tenant,
      category: "tech", name: "Database Learning Kit",
      price: NumberDecimal("130.00"),
      tags: ["database", "backend"],
      scores: [85, 91],
      variants: [{ color: "red", stock: NumberInt(7) }]
    },
    {
      _id: "p003", dataset: tag, tenantId: tenant,
      category: "books", name: "MongoDB Book",
      price: NumberDecimal("40.00"),
      tags: ["mongodb", "tutorial"],
      scores: [80],
      variants: [{ color: "green", stock: NumberInt(5) }]
    },
    {
      _id: "p004", dataset: tag, tenantId: tenant,
      category: "tech", name: "MongoDB Practice Kit",
      price: NumberDecimal("85.00"),
      tags: ["mongodb", "backend", "sale"],
      scores: [70, 88],
      variants: [
        { color: "black", stock: NumberInt(12) },
        { color: "red", stock: NumberInt(2) }
      ]
    },
    {
      _id: "p005", dataset: tag, tenantId: tenant,
      category: "books", name: "Introductory Book",
      price: NumberDecimal("65.00"),
      tags: [], scores: [], variants: []
    },
    {
      _id: "p006", dataset: tag, tenantId: tenant,
      category: "tech", name: "Frontend Learning Kit",
      price: NumberDecimal("120.00"),
      tags: ["frontend", "sale"],
      scores: [99],
      variants: [{ color: "red", stock: NumberInt(0) }]
    }
  ]);

  // One Array paired with two scalar equality conditions.
  products.createIndex(
    { tenantId: 1, category: 1, tags: 1 },
    { name: "ix_tenant_category_tags" }
  );

  // Two subfields inside the SAME Array path variants.
  products.createIndex(
    { tenantId: 1, "variants.color": 1, "variants.stock": 1 },
    { name: "ix_tenant_variant_color_stock" }
  );

  // Scalar index supporting category filter and price sort.
  products.createIndex(
    { tenantId: 1, category: 1, price: 1 },
    { name: "ix_tenant_category_price" }
  );

  // Separate Array index for interval exercises.
  products.createIndex(
    { scores: 1 },
    { name: "ix_scores" }
  );

  print("Total products: " +
    products.countDocuments({ dataset: tag }));
})();
~~~

**Expected result: 6 documents.** IDs and values do not depend on execution time; if you have modified tags or stock, re-running this block restores the data. deleteMany and insertMany are not wrapped in a transaction, so use only in a dedicated learning environment.

For concise outputs, define a helper function in the mongosh session:

~~~javascript
function showProductIds(label, filter) {
  const c = db.getSiblingDB("mongo_multikey_lab")
    .getCollection("lab_products");

  const ids = c.find(
      {
        $and: [
          { dataset: "multikey-practice-v1", tenantId: "lab-shop" },
          filter
        ]
      },
      { _id: 1 }
    )
    .sort({ _id: 1 })
    .toArray()
    .map(doc => doc._id);

  print(label + ": " + JSON.stringify(ids));
  return ids;
}
~~~

This helper keeps every example scoped to the dataset and tenant. If you open a new mongosh session, re-run the function definition before calling it.

## 4. Scalar Array Queries and Index Implications

### 4.1. Finding One Element

~~~javascript
showProductIds("Has mongodb", { tags: "mongodb" });
// ["p001", "p003", "p004"]
~~~

MongoDB matches when the array contains an element equal to mongodb. An index on tags lets MongoDB look up mongodb keys and find candidate documents without scanning the whole collection. Effectiveness still depends on how many documents share that tag.

### 4.2. Finding Multiple Elements with $all

~~~javascript
showProductIds(
  "Has both mongodb and backend",
  { tags: { $all: ["mongodb", "backend"] } }
);
// ["p001", "p004"]
~~~

**$all** requires the Array to contain all listed elements, without requiring exact order. However, do not assume every $all condition is always intersected completely at the index level: inspect **indexBounds** and FETCH in explain to see what MongoDB evaluated in the index versus after reading documents.

### 4.3. Whole-Array Equality vs. Single-Element Equality

~~~javascript
showProductIds(
  "Exact whole Array",
  { tags: ["mongodb", "backend"] }
);
// ["p001"]

showProductIds(
  "Contains backend",
  { tags: "backend" }
);
// ["p001", "p002", "p004"]
~~~

Whole-Array queries check the **array's exact order and values**, unlike checking for an arbitrary element. A multikey index can help locate candidates by an array element, yet it cannot by itself verify every whole-Array equality case solely from individual index entries. MongoDB may need to **FETCH** documents to compare the intact array structure.

### 4.4. $size Is Not Directly Resolved by the tags Index

~~~javascript
showProductIds("Empty tags", { tags: { $size: 0 } });
// ["p005"]
~~~

**$size** compares the number of elements in an Array. A multikey index stores element values rather than directly exposing element counts in a way that resolves $size alone. If business logic frequently filters by array length, consider a scalar **tagsCount** field kept consistent with tags and appropriately indexed. Adding a derived count field also adds write overhead, so it must be justified by access patterns.

## 5. $elemMatch on Document Arrays: Same Element or Multiple Elements?

### 5.1. Independent Dotted-Path Conditions

Business requirement: **products with a red variant and stock greater than 0**. Query:

~~~javascript
showProductIds(
  "Two conditions on variants",
  {
    "variants.color": "red",
    "variants.stock": { $gt: 0 }
  }
);
// ["p001", "p002", "p004"]
~~~

Why is **p001** included? This document has a red element with stock 0, alongside a blue element with stock 6. The two conditions are satisfied by **two different elements**. A query without $elemMatch only asserts that both attributes appear somewhere in the document, without binding them to one variant.

~~~text
p001.variants
  +--------------------+    +--------------------+
  | color: red         |    | color: blue        |
  | stock: 0           |    | stock: 6           |
  +--------------------+    +--------------------+
        |                          |
        +-- matches color          +-- matches stock > 0

Overall document matches two independent conditions.
No single variant satisfies both conditions.
~~~

### 5.2. $elemMatch Requires Both Simultaneously on One Element

~~~javascript
showProductIds(
  "One red variant in stock",
  {
    variants: {
      $elemMatch: {
        color: "red",
        stock: { $gt: 0 }
      }
    }
  }
);
// ["p002", "p004"]
~~~

**$elemMatch** matches only when there exists **one variants element** simultaneously satisfying color red and stock > 0. Therefore p001 is excluded; p006 also does not match because its red variant is out of stock.

This is a **business correctness** issue, not just a performance optimization. If an application sells products based on independent queries, it could show a red variant as in stock when in fact only another color has inventory.

## 6. Index Bounds on Arrays and the Role of $elemMatch

**Index bounds** describe the range of key values MongoDB scans inside an index. When a field is scalar, two range conditions can intersect into a narrow interval. When a field is an Array, range conditions can be satisfied by different elements, so bounds cannot always be intersected while preserving the exact result set.

### 6.1. Score Range Without $elemMatch

Product p001 has **scores = [65, 95]**.

~~~javascript
showProductIds(
  "scores >= 80 and <= 90",
  { scores: { $gte: 80, $lte: 90 } }
);
// ["p001", "p002", "p003", "p004"]
~~~

p001 matches because 95 satisfies $gte: 80 and 65 satisfies $lte: 90. No single element lies inside [80, 90]. If an index scan only read keys in [80, 90], p001 would be wrongly excluded. Without $elemMatch, MongoDB must preserve those semantics; the planner may use one bound and evaluate the remaining condition on the document.

### 6.2. Score Range with $elemMatch

~~~javascript
showProductIds(
  "Has a score in [80, 90]",
  {
    scores: {
      $elemMatch: { $gte: 80, $lte: 90 }
    }
  }
);
// ["p002", "p003", "p004"]
~~~

This is the query requiring **a single score inside the interval**. $elemMatch allows MongoDB to **intersect bounds** on the multikey index into a tighter range because there is no longer a risk of missing documents matched across separate elements.

### 6.3. Observing indexBounds Directly

~~~javascript
(() => {
  const c = db.getSiblingDB("mongo_multikey_lab")
    .getCollection("lab_products");

  const withoutElemMatch = c.find({
    dataset: "multikey-practice-v1",
    scores: { $gte: 80, $lte: 90 }
  }).hint("ix_scores").explain("executionStats");

  const withElemMatch = c.find({
    dataset: "multikey-practice-v1",
    scores: { $elemMatch: { $gte: 80, $lte: 90 } }
  }).hint("ix_scores").explain("executionStats");

  print("Without $elemMatch:");
  printjson(withoutElemMatch);
  print("With $elemMatch:");
  printjson(withElemMatch);
})();
~~~

Locate **indexBounds** inside IXSCAN in both plans. Also inspect **totalKeysExamined**, **totalDocsExamined**, **nReturned**, and whether a FETCH stage is present. **hint** is used in the lab to inspect the same index; in real applications, avoid forcing hints by default before measuring optimal plans on representative data.

### 6.4. Compounding Bounds for Subfields Sharing an Array Path

Index:

~~~javascript
{
  tenantId: 1,
  "variants.color": 1,
  "variants.stock": 1
}
~~~

Both color and stock sit inside the **variants** Array path. To give MongoDB the basis to **compound bounds** across these two fields, the query must express same-element conditions:

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .find({
    tenantId: "lab-shop",
    variants: {
      $elemMatch: {
        color: "red",
        stock: { $gt: 0 }
      }
    }
  })
  .hint("ix_tenant_variant_color_stock")
  .explain("executionStats");
~~~

This is the case where **two subfields share the same Array path prefix**. With two independent dotted predicates, MongoDB may not be able to compound both bounds as tightly as with $elemMatch. The path where $elemMatch is placed must be **variants**, the shared prefix before color and stock.

## 7. Compound Multikey Indexes: Capabilities and Limits

### 7.1. One Array Combined with Multiple Scalars

The index **{ tenantId: 1, category: 1, tags: 1 }** is a valid compound multikey index on this lesson's data: tenantId/category are scalars, tags is an Array. It supports the filter pattern:

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .find({
    tenantId: "lab-shop",
    category: "tech",
    tags: "mongodb"
  });
// p001 and p004.
~~~

In a compound index, **field order** determines how well prefixes can be leveraged. Queries filtering by tenant and category can utilize the leading two fields and then narrow further with tags. You do not need to create an index for every possible combination if real queries concentrate on a few access patterns.

### 7.2. Two Independent Arrays in the Same Compound Index Are Restricted

Example:

~~~javascript
{
  _id: "example",
  tags: ["mongodb", "backend"],
  regions: ["north", "south"]
}
~~~

You cannot arbitrarily create a compound multikey index on **tags** and **regions** if the same document holds both fields as Arrays:

~~~javascript
// Illustrative invalid configuration when two parallel Arrays exist:
// db.products.createIndex({ tags: 1, regions: 1 });
~~~

MongoDB restricts **parallel arrays** in a compound multikey index. If an existing document already has both Arrays, creating the index will be rejected. If the index is created first, an insert or update causing a document to hold two indexed arrays will fail.

**Do not confuse this with variants.color + variants.stock**: those two fields lie within the same Array of embedded documents and can be compounded when same-path and $elemMatch conditions are met. What matters is the **Array path structure**, not merely seeing two multivalued subfields.

### 7.3. Unique Multikey Does Not Substitute for Uniqueness Within One Array

With a unique multikey index, uniqueness is enforced on keys across **different documents**. Duplicate elements inside a single array of the same document do not by themselves cause the unique index to reject duplicate index keys within that document.

Example:

~~~javascript
{ _id: "p001", tags: ["sale", "sale"] }
~~~

You cannot rely on a unique multikey index to ensure a document contains no duplicate tags. If business logic treats tags as a set, validate inputs and consider using **$addToSet** when adding elements; cleaning legacy duplicates remains a separate responsibility.

A unique multikey index on tags would also forbid **two different products from sharing the same tag**, which is rarely what a catalog wants. Never set unique: true merely hoping to deduplicate elements inside each Array.

### 7.4. Additional Limitations to Remember

- **Hashed indexes** do not support multikey; do not build a hashed index directly on an Array.
- **Shard key indexes** cannot be multikey, though a compound index with the shard key as a prefix can include a trailing multikey field outside the shard key.
- Multikey indexes have specific restrictions on **sorts**, **covered queries**, and **index bounds**.
- A query using **$expr** cannot expect a multikey index to support it the same way a standard predicate on an Array uses an index.

## 8. Reading explain to Understand Query Plans

### 8.1. Key Details

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .find({
    tenantId: "lab-shop",
    category: "tech",
    tags: "mongodb"
  })
  .hint("ix_tenant_category_tags")
  .explain("executionStats");
~~~

Stage names and nesting can vary across server versions and query engines, yet the concepts to read usually include:

| Field | Meaning |
| --- | --- |
| **winningPlan** | Execution plan chosen by the optimizer |
| **IXSCAN** | Reading keys from an index |
| **indexName** | Index used in the stage |
| **isMultiKey** | Indicates whether the index in the stage is multikey |
| **multiKeyPaths** | Paths that made the index multikey, when reported |
| **indexBounds** | Key ranges scanned per index field |
| **FETCH** | Reads actual documents from the collection, e.g., to check remaining predicates |
| **SORT** | Blocking sort when index ordering cannot be fully leveraged |
| **COLLSCAN** | Collection scan |
| **totalKeysExamined** | Number of index keys examined |
| **totalDocsExamined** | Number of documents examined |
| **nReturned** | Number of documents returned |

Because a single document can produce multiple index keys, **totalKeysExamined** exceeding **nReturned** can occur naturally on a multikey index. Judging whether an index is good or bad requires considering selectivity, fetched document count, latency, and total resource usage.

### 8.2. Comparing Two Indexes for the Same Predicate

~~~javascript
const c = db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products");

const filter = {
  tenantId: "lab-shop",
  category: "tech",
  tags: "mongodb"
};

printjson(
  c.find(filter)
    .hint("ix_tenant_category_tags")
    .explain("executionStats")
);

printjson(
  c.find(filter)
    .hint("ix_tenant_category_price")
    .explain("executionStats")
);
~~~

The first index includes tags so it has the opportunity to filter by tag via index keys. The second index supports tenant/category/price but **does not include tags**, so it may need to FETCH documents to inspect tags. In a six-document lab, the difference will not represent a multi-million-product system.

### 8.3. Multikey Indexes Can Cover Queries, Under Conditions

A **covered query** is a query where the index satisfies both filter and projection without reading the underlying documents. A multikey index can still cover certain queries if:

- The projection **does not return an Array field**.
- The query **does not use $elemMatch**.
- All fields needed for filter/projection and standard covered-query conditions are met, such as excluding _id when _id is not in the index.

Example likely to be covered:

~~~javascript
c.find(
  {
    tenantId: "lab-shop",
    category: "tech",
    tags: "mongodb"
  },
  { _id: 0, category: 1 }
)
  .hint("ix_tenant_category_tags")
  .explain("executionStats");
~~~

By contrast, if the projection returns **tags**, a multikey index cannot fully cover the query under the same conditions:

~~~javascript
c.find(
  {
    tenantId: "lab-shop",
    category: "tech",
    tags: "mongodb"
  },
  { _id: 0, tags: 1 }
)
  .hint("ix_tenant_category_tags")
  .explain("executionStats");
~~~

Seeing **IXSCAN** in the plan does not guarantee the query is covered; check whether a FETCH stage remains.

### 8.4. Sort and Array Fields

Multikey indexes have special rules when sorting. In some cases MongoDB must perform a blocking **SORT** even when the sorted field is indexed, because multikey field boundaries and path prefixes do not satisfy index-order requirements.

~~~javascript
c.find(
  { tenantId: "lab-shop", scores: { $gte: 80 } },
  { _id: 1, scores: 1 }
)
  .sort({ scores: 1 })
  .hint("ix_scores")
  .explain("executionStats");
~~~

When sorting ascending on an Array, MongoDB uses an array sort-value rule (typically the minimum value when sorting ascending). Filter predicates do not necessarily dictate which element acts as the sort key. If business logic requires the **lowest price**, **highest score**, or **latest update timestamp** across elements, consider a dedicated scalar summary field with explicit semantics.

## 9. Index Costs, Concurrent Writes, and Data Modeling

### 9.1. Array Fan-Out Increases Cost

A product with 2 tags differs from a product with 200 distinct tags. With a multikey index, the more distinct values an array holds, the more index keys a single document contributes. This can increase:

- Index storage size on disk and cache memory required for the index.
- Number of keys MongoDB must scan on insufficiently selective queries.
- Number of index updates when adding, removing, or modifying elements.
- Write latency and replication/backup volume in production systems.

Do not estimate index size simply by multiplying element count by a constant; key structure, duplicates, compression, and compound indexing all affect footprint.

### 9.2. Array Updates Must Also Maintain Indexes

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .updateOne(
    { _id: "p001", dataset: "multikey-practice-v1" },
    { $addToSet: { tags: "performance" } }
  );
~~~

This command adds a tag that is not yet present. Because tags is indexed, corresponding keys must be maintained accordingly. $addToSet prevents adding new duplicate elements per the operation's semantics, though it does not automatically clean up duplicates already present in an old array.

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .updateOne(
    {
      _id: "p002",
      dataset: "multikey-practice-v1",
      "variants.color": "red"
    },
    { $inc: { "variants.$.stock": 1 } }
  );
~~~

Stock is part of an index on variants, so this change updates both the document and potentially index keys. Single-document updates are atomic within document scope; if the application must enforce non-negative inventory or prevent duplicate order writes, business conditions and appropriate concurrency controls are still required.

### 9.3. When Should You Avoid Embedding a Very Large Array?

| Data Type | When Embedding Usually Fits | When to Consider a Separate Collection |
| --- | --- | --- |
| Product tags | Few elements, clear cap, read with product | Tag set grows huge, changes frequently |
| Product variants | Finite variants, read with product | Many variants, high-frequency independent stock updates |
| Order line items | Line count bounded by business rules | Orders can have thousands or unbounded lines |
| Comments, events, logs | Small count, lifecycle tied to parent | Continuous growth, needs independent pagination/search |
| Linked ID lists | Few values, rarely changing | Can scale to millions of relationships |

Beyond the 16 MiB limit, evaluate **read paths**, **write paths**, **update frequency**, **lifecycle**, **element counts**, and **indexes to maintain**. Just because an array is easy to query with a multikey index does not make it a good choice for an unboundedly growing relationship.

### 9.4. Indexes Should Follow Access Patterns

Suppose an application has three features:

1. Find products by tenant/category/tag.
2. Find variants by color and stock within the same element.
3. Sort products by tenant/category/price.

The three indexes created in the lab reflect those three needs. You do not need to cram everything into one index; combining the **tags Array** and **variants Array** in one compound index would also hit parallel-array restrictions. Any index unused by queries still incurs maintenance overhead on every write.

## 10. Cleaning Up Data and Inspecting Index Configuration

To reset data after updating tags or stock, re-run the seed script in Section 3. Documents use fixed IDs, and indexes use stable names and definitions. You can verify:

~~~javascript
const c = db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products");

print(c.countDocuments({ dataset: "multikey-practice-v1" }));
// 6 if seed was just run.

printjson(c.getIndexes());
~~~

**getIndexes()** displays index definitions, whereas to inspect **isMultiKey** and **multiKeyPaths** used in a query plan, check the corresponding query's explain output.

When finished with the lesson, remove only the documents tagged with the lab dataset:

~~~javascript
db.getSiblingDB("mongo_multikey_lab")
  .getCollection("lab_products")
  .deleteMany({ dataset: "multikey-practice-v1" });
~~~

There is no need to drop the collection or database to clean up; indexes remain intact if you want to continue practicing.

## 11. Common Mistakes

| Symptom | Cause | How to Handle |
| --- | --- | --- |
| Red is out of stock, yet query still returns the product | Two dotted-path conditions matched two different elements | Use $elemMatch on variants |
| [65,95] matches interval 80–90 | Range predicates can match different elements | Use $elemMatch to require one element in the interval |
| Creating index on tags + regions fails | Two independent Arrays indexed together in a compound index | Change indexes or data model |
| IXSCAN still has high totalKeysExamined | One document has many index keys; index bounds not selective | Inspect isMultiKey, multiKeyPaths, indexBounds, and FETCH results |
| Query with $elemMatch still requires FETCH | Multikey covered queries have restrictions with $elemMatch | Weigh query/projection and document read cost |
| Index contains tags, yet projecting tags is not covered | An Array field is returned | Conclude covered only when explain has no FETCH |
| Sort by Array shows blocking SORT | Multikey bounds and sort rules are not satisfied | Check explain or use a scalar sort key |
| Unique multikey still accepts duplicate tags in one document | Uniqueness does not deduplicate elements inside one array | Validate arrays and control writes with $addToSet |
| $size query is not faster just from a tags index | Index stores element values, not array length directly | Evaluate whether a dedicated count field is needed |
| Array updates increase write latency | MongoDB must maintain additional index keys | Control Array size, index count, and update frequency |
| 6-document lab uses COLLSCAN | Data is so small that COLLSCAN can be cheaper than IXSCAN | Measure on representative data volume and load |

## 12. Self-Practice Exercises

**Exercise 1 — Sketch the multikey index.** Using p001.tags and p004.tags, map out the index keys on tags and explain why find({tags:"mongodb"}) returns a document once even when the index has multiple entries.

**Exercise 2 — Fix the red-in-stock query.** Write two queries for color red and stock > 0: one using independent dotted paths and one using $elemMatch. Record the differing results and explain why p001 behaves differently.

**Exercise 3 — Range bounds.** Predict the results of two queries for scores >= 80 and <= 90, with and without $elemMatch. Use hint("ix_scores") and explain("executionStats") to inspect indexBounds.

**Exercise 4 — Compound indexes.** Given tenantId, category, tags, variants, and price, pick suitable indexes for searching by tag, searching variants on the same element, and sorting by price. Explain why a compound index containing two independent Arrays is unsuitable.

**Exercise 5 — Covered queries.** Compare a projection returning only category against a projection returning tags when using ix_tenant_category_tags. Inspect FETCH and explain why returning an Array prevents covering.

**Exercise 6 — Growing arrays.** If a product has 10,000 distinct tags changing continuously, list the multikey index costs and propose a cleaner document/collection boundary if tags actually represent an independent relationship.

**Exercise 7 — Reading explain.** Run one query on tags and one query on variants, recording indexName, indexBounds, isMultiKey, totalKeysExamined, totalDocsExamined, and nReturned. Explain the numbers based on Array structure without drawing broad conclusions from six documents.

## 13. MongoDB Documentation

- MongoDB Manual — [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/).
- MongoDB Manual — [Multikey Index Bounds](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/multikey-index-bounds/).
- MongoDB Manual — [Create an Index on an Array Field](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/create-multikey-index-basic/).
- MongoDB Manual — [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/).
- MongoDB Manual — [Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).

When working with arrays, **multikey indexes enable element-level lookups**, yet also multiply index keys per document. **$elemMatch** specifies conditions that must hold on the same element, directly impacting **index bounds** and result sets. **Compound multikey indexes** must respect Array path structure and parallel-array limits. To decide whether an index is appropriate, read **explain** output and weigh read, write, sort, and array-growth costs together.
