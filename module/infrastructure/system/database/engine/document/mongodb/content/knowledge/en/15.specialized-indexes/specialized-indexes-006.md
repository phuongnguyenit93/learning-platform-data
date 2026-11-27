# Wildcard Indexes for Variable Field Structures in MongoDB

In an e-commerce catalog, laptop products have `attributes.ramGB` and `attributes.cpu.cores`, cameras have `attributes.sensor.megapixels`, and office chairs have `attributes.maxLoadKg`. These fields do not appear uniformly across every document. If the engineering team had to create a dedicated index every time a new attribute appeared, the number of indexes would multiply rapidly and become difficult to manage. MongoDB's **wildcard index** is designed to support queries across many different field paths, especially when field structures vary and the full set of searchable attributes cannot be known in advance.

A wildcard index is not a "index everything so every query is fast" silver bullet. It can generate many index keys per document, lacks the full capabilities of a compound index tailored for stable filter/sort patterns, and has limitations with arrays, data types, and multi-predicate combinations. This lesson helps you understand **when to use `$**`, when to restrict scope with `attributes.$**` or `wildcardProjection`, and how to evaluate effectiveness using real query workloads**.

This lesson is part of the **Specialized Indexes** chapter of the *MongoDB Document Database Engine* module. Examples use **mongosh** with the lab database `wildcard_lab`. Certain capabilities—particularly compound wildcard indexes—depend on MongoDB version; verify support in your target deployment before rolling out. Never create or drop indexes on a production collection merely to test examples.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the **dynamic schema** problem and why wildcard indexes exist.
2. Distinguish a whole-document wildcard index `{"$**":1}`, a subtree wildcard index `{"attributes.$**":1}`, and an index on a specific field.
3. Understand how wildcard indexes organize **field paths and values**, rather than behaving identically to a B-tree on one known field.
4. Create, list, and manage wildcard indexes with `createIndex()`, `getIndexes()`, and `dropIndex()`.
5. Use `wildcardProjection` to include only required subtrees or exclude data you do not want indexed.
6. Analyze equality, range, nested-field, array, and multi-field queries.
7. Identify limitations around sorting, covered queries, missing fields, complex structures, and indexing multiple attributes.
8. Understand compound wildcard indexes, particularly for use cases combining a few stable fields with many dynamic fields.
9. Measure query plans via `explain("executionStats")`, manage index footprint/usage, and choose alternative strategies when wildcard is not a good fit.

## 2. Dynamic Schemas: Why Standard Indexes Are Not Flexible Enough

Suppose the `products` collection holds three product groups:

~~~javascript
// Laptop
{
  _id: "laptop-01",
  category: "laptop",
  attributes: {
    ramGB: 16,
    cpu: { cores: 8 },
    storage: { ssdGB: 512 }
  }
}

// Camera
{
  _id: "camera-01",
  category: "camera",
  attributes: {
    sensor: { megapixels: 24 },
    stabilization: true,
    lensMount: "E"
  }
}

// Chair
{
  _id: "chair-01",
  category: "chair",
  attributes: {
    material: "mesh",
    maxLoadKg: 120,
    adjustableHeight: true
  }
}
~~~

Users may query:

~~~javascript
db.products.find({ "attributes.ramGB": { $gte: 16 } })
db.products.find({ "attributes.sensor.megapixels": { $gte: 20 } })
db.products.find({ "attributes.maxLoadKg": { $gte: 100 } })
~~~

If you use standard single-field indexes for each path:

~~~javascript
db.products.createIndex({ "attributes.ramGB": 1 })
db.products.createIndex({ "attributes.sensor.megapixels": 1 })
db.products.createIndex({ "attributes.maxLoadKg": 1 })
~~~

you must predict which fields will be queried. With hundreds of categories, thousands of attribute names, and new attributes continuously added by sellers, a "one index per field" strategy can lead to:

- Many indexes with very low usage counts.
- Large index footprint and increased write overhead.
- Frequent index migrations whenever attributes are added.
- Index builds impacting production load and requiring constant monitoring.
- Growing complexity in index selection and lifecycle management.

**Wildcard indexes** allow you to declare a range of paths to index without listing every field name upfront.

### Distinguishing "Dynamic Fields" from "Dynamic Values"

A stable field with many distinct values does not necessarily need a wildcard index:

~~~javascript
{
  category: "laptop",   // fixed field name
  status: "ACTIVE",     // fixed field name
  price: 25000000       // fixed field name
}
~~~

The value of `category` varies across laptop/camera/chair, yet **the `category` path itself does not change**. A standard single-field or compound index fits very well.

By contrast, `attributes.ramGB`, `attributes.sensor.megapixels`, and `attributes.maxLoadKg` are **different field paths**. That is the kind of variability wildcard indexes target.

## 3. How Wildcard Indexes Work Conceptually

A wildcard index uses the `$**` token to tell MongoDB to index field paths within the permitted scope rather than a single named field. Conceptually, index entries pair a **field path** with its corresponding **value**.

Example:

~~~javascript
{
  _id: "laptop-01",
  attributes: {
    ramGB: 16,
    cpu: { cores: 8 },
    color: "black"
  }
}
~~~

One way to visualize the key pairs:

~~~text
path = "attributes.ramGB"       value = 16
path = "attributes.cpu.cores"   value = 8
path = "attributes.color"       value = "black"
~~~

This is a **conceptual model**, not a raw dump of the on-disk index structure. The engine also handles BSON types, arrays, duplicate keys, path metadata, and edge cases.

~~~mermaid
flowchart TD
    Product["Product Document"] --> Attr["attributes Object"]
    Attr --> A["attributes.ramGB = 16"]
    Attr --> B["attributes.cpu.cores = 8"]
    Attr --> C["attributes.color = black"]
    A --> WI["Wildcard index: path + value"]
    B --> WI
    C --> WI
    Query["Query on attributes.cpu.cores"] --> WI
    WI --> Found["Matching document candidates"]
~~~

**One index can support multiple paths:** queries filtering `attributes.ramGB` and queries filtering `attributes.cpu.cores` can both potentially use the same wildcard index. However, this **does not mean a single wildcard index scan is always optimal for multiple predicates on different paths at once**.

### 3.1. Comparison with a Single-Field Index

| Criterion | Single-Field Index `{"attributes.ramGB":1}` | Wildcard `{"attributes.$**":1}` |
|---|---|---|
| Indexed paths | Fixed: `attributes.ramGB` | Many paths beneath `attributes` |
| Best suited for | High-frequency repeated queries on `ramGB` | Dynamic queries across varied attributes |
| Adding a new field | Must consider adding a separate index | New fields within scope can be indexed automatically |
| Index size | Usually focused on one key family | Can produce many keys per document |
| Multi-field filter + sort | Can combine via dedicated compound index | More limitations; inspect query planner |
| When to prefer | Stable workloads, critical fields | Variable, unpredictable field workloads |

## 4. Three Ways to Specify Wildcard Index Scope

### 4.1. Whole-Document Wildcard

~~~javascript
db.flex_documents.createIndex(
  { "$**": 1 },
  { name: "idx_all_dynamic_paths" }
)
~~~

The pattern `{"$**":1}` targets field paths across the entire document subject to wildcard indexing rules. It fits when **many parts of a document** contain dynamic data that needs querying.

Trade-off: stable fields, log/debug data, large payloads, or metadata never used in filters can bloat the index if left unrestricted. Therefore, never choose a whole-document wildcard merely because its syntax is short.

### 4.2. Subtree Wildcard

~~~javascript
db.products.createIndex(
  { "attributes.$**": 1 },
  { name: "idx_product_attributes" }
)
~~~

This index focuses on paths beneath `attributes`, such as:

~~~text
attributes.ramGB
attributes.cpu.cores
attributes.sensor.megapixels
attributes.material
attributes.waterproof
~~~

It **does not index** top-level filters like `tenantId`, `status`, or `price` outside that subtree.

For catalogs with stable core fields and a category-dependent `attributes` object, this is usually a far more sensible starting point than `{"$**":1}`.

### 4.3. Whole-Document Wildcard with `wildcardProjection`

When multiple subtrees hold dynamic fields yet certain subtrees should not be indexed, use `wildcardProjection`:

~~~javascript
db.flex_documents.createIndex(
  { "$**": 1 },
  {
    name: "idx_flex_without_large_payload",
    wildcardProjection: {
      rawPayload: 0,
      debugDetails: 0,
      description: 0
    }
  }
)
~~~

Here the projection excludes the named subtrees from indexing. Another option is to **include only** the subtrees needed for queries:

~~~javascript
db.flex_documents.createIndex(
  { "$**": 1 },
  {
    name: "idx_flex_selected_branches",
    wildcardProjection: {
      attributes: 1,
      customFields: 1
    }
  }
)
~~~

These two examples are **mutually exclusive alternatives**, not a recommendation to create both indexes simultaneously in production. In specific configurations, verify inclusion/exclusion rules, `_id` handling, and MongoDB version compatibility. `wildcardProjection` controls **which fields are indexed**, not the fields projected in `find()` results.

### 4.4. Which Option Should You Choose?

| Case | Suggested Scope | Reason |
|---|---|---|
| Only `attributes` varies | `{"attributes.$**":1}` | Avoids indexing core fields outside `attributes` |
| Multiple customizable subtrees | `{"$**":1}` with inclusive `wildcardProjection` | Tightly controls indexed scope |
| Most fields searchable except large payloads | `{"$**":1}` with exclusive `wildcardProjection` | Suppresses unhelpful subtrees |
| Queries mostly target one stable field | Dedicated single/compound index | Smaller, better sort/range support |
| Only need natural-language document search | Text/search index as appropriate | B-tree wildcards do not replace a search engine |

## 5. Lab Dataset: Multi-Structure Attribute Catalog

Select a dedicated database:

~~~javascript
use wildcard_lab
~~~

Create test data. Each product category has different fields inside `attributes`:

~~~javascript
db.products.insertMany([
  {
    _id: "p-101",
    tenantId: "t-01",
    category: "laptop",
    status: "ACTIVE",
    name: "Laptop Alpha",
    price: NumberDecimal("22000000"),
    attributes: {
      ramGB: 16,
      cpu: { cores: 8, family: "Core" },
      storage: { ssdGB: 512 },
      color: "gray",
      connectivity: ["wifi6", "bluetooth5"]
    }
  },
  {
    _id: "p-102",
    tenantId: "t-01",
    category: "laptop",
    status: "ACTIVE",
    name: "Laptop Beta",
    price: NumberDecimal("35000000"),
    attributes: {
      ramGB: 32,
      cpu: { cores: 16, family: "Ryzen" },
      storage: { ssdGB: 1024 },
      color: "black",
      connectivity: ["wifi7", "bluetooth5"]
    }
  },
  {
    _id: "p-201",
    tenantId: "t-01",
    category: "camera",
    status: "ACTIVE",
    name: "Camera Sigma",
    price: NumberDecimal("19500000"),
    attributes: {
      sensor: { megapixels: 24, format: "APS-C" },
      stabilization: true,
      lensMount: "E",
      iso: { max: 51200 }
    }
  },
  {
    _id: "p-202",
    tenantId: "t-02",
    category: "camera",
    status: "ACTIVE",
    name: "Camera Delta",
    price: NumberDecimal("12000000"),
    attributes: {
      sensor: { megapixels: 18, format: "Micro 4/3" },
      stabilization: false,
      lensMount: "MFT",
      iso: { max: 25600 }
    }
  },
  {
    _id: "p-301",
    tenantId: "t-01",
    category: "chair",
    status: "ACTIVE",
    name: "Chair Mesh",
    price: NumberDecimal("3200000"),
    attributes: {
      material: "mesh",
      maxLoadKg: 120,
      adjustableHeight: true,
      color: "black"
    }
  },
  {
    _id: "p-302",
    tenantId: "t-02",
    category: "chair",
    status: "INACTIVE",
    name: "Chair Oak",
    price: NumberDecimal("4600000"),
    attributes: {
      material: "wood",
      maxLoadKg: 80,
      adjustableHeight: false,
      color: "brown"
    }
  },
  {
    _id: "p-401",
    tenantId: "t-01",
    category: "shoes",
    status: "ACTIVE",
    name: "Shoes Trek",
    price: NumberDecimal("1900000"),
    attributes: {
      sizesEU: [40, 41, 42],
      upper: { material: "leather" },
      waterproof: true,
      colors: ["black", "brown"]
    }
  },
  {
    _id: "p-402",
    tenantId: "t-02",
    category: "shoes",
    status: "ACTIVE",
    name: "Shoes Run",
    price: NumberDecimal("1350000"),
    attributes: {
      sizesEU: [39, 40],
      upper: { material: "textile" },
      waterproof: false,
      colors: ["blue", "white"]
    }
  },
  {
    _id: "p-501",
    tenantId: "t-01",
    category: "phone",
    status: "ACTIVE",
    name: "Phone One",
    price: NumberDecimal("16000000"),
    attributes: {
      screen: { inches: 6.7 },
      battery: { mAh: 5000 },
      features: { eSIM: true },
      colors: ["black", "silver"]
    }
  },
  {
    _id: "p-502",
    tenantId: "t-02",
    category: "phone",
    status: "ACTIVE",
    name: "Phone Mini",
    price: NumberDecimal("9000000"),
    attributes: {
      screen: { inches: 6.1 },
      battery: { mAh: 4200 },
      features: { eSIM: false },
      colors: ["white", "green"]
    }
  }
])
~~~

This dataset is meant for **understanding semantics**, not drawing speed conclusions. Run `insertMany()` only once in a fresh lab; subsequent runs with the same `_id`s will fail with duplicate key errors. Do not drop non-test collections just to re-run examples.

Inspect:

~~~javascript
db.products.countDocuments({})

db.products.find(
  {},
  { _id: 1, tenantId: 1, category: 1, status: 1, name: 1 }
).sort({ _id: 1 })
~~~

### 5.1. Create a Wildcard Index Under `attributes`

~~~javascript
db.products.createIndex(
  { "attributes.$**": 1 },
  { name: "idx_attributes_wildcard" }
)
~~~

Inspect metadata:

~~~javascript
db.products.getIndexes()
~~~

Note: the wildcard index is declared on a single subtree. If the application frequently filters by `tenantId`, `category`, `status`, or `price`, analyze separate indexes for them; a wildcard index on `attributes` alone does not guarantee overall query performance.

## 6. Equality Queries on Dynamic Fields

### 6.1. Laptops with 16 GB RAM

~~~javascript
db.products.find(
  { "attributes.ramGB": 16 },
  { _id: 1, name: 1, category: 1, "attributes.ramGB": 1 }
)
~~~

In the sample dataset, `p-101` matches. MongoDB can consult the wildcard index to locate keys belonging to the path `attributes.ramGB` with value 16.

### 6.2. Finding Chair Material

~~~javascript
db.products.find(
  {
    category: "chair",
    "attributes.material": "mesh"
  },
  { _id: 1, name: 1, "attributes.material": 1 }
)
~~~

`p-301` matches. `category` is a core field, while `attributes.material` is a dynamic field. The wildcard index under `attributes` can assist the second predicate, yet does not combine both fields into a compound key order like a dedicated compound index.

### 6.3. Cameras with Lens Mount E

~~~javascript
db.products.find({
  "attributes.lensMount": "E"
})
~~~

`p-201` matches. There is no need to create a separate `{"attributes.lensMount":1}` index solely to provide an access path for this field if the wildcard index satisfies the workload.

### 6.4. Laptops by CPU Family Name

~~~javascript
db.products.find({
  "attributes.cpu.family": "Ryzen"
})
~~~

`p-102` matches. Deeper nested paths still fall under the `attributes` subtree.

**Takeaway from these examples:** a single wildcard index can act as an index candidate for many **separate queries across different paths**. Do not assume it simultaneously optimizes arbitrary combinations of paths within the same query.

## 7. Range Queries on Dynamic Attributes

Wildcard indexes do not serve only equality lookups. With consistent data types and compatible query shapes, they can also support range conditions.

### 7.1. Cameras with at Least 20 MP

~~~javascript
db.products.find({
  "attributes.sensor.megapixels": { $gte: 20 }
})
~~~

Result from sample data: `p-201` (24 MP); `p-202` has only 18 MP.

### 7.2. Chairs Supporting at Least 100 kg

~~~javascript
db.products.find({
  "attributes.maxLoadKg": { $gte: 100 }
})
~~~

Result: `p-301` (120 kg).

### 7.3. Laptops with at Least 16 GB RAM

~~~javascript
db.products.find({
  "attributes.ramGB": { $gte: 16 }
})
~~~

Result: `p-101` and `p-102`.

### 7.4. Data Types Must Be Consistent

If one seller writes:

~~~javascript
{ attributes: { ramGB: "16" } }
~~~

instead of:

~~~javascript
{ attributes: { ramGB: 16 } }
~~~

numeric range comparisons will not match the string value the way you expect. Indexes store BSON values with their exact types; they **do not automatically normalize `"16"` to `16`**. Having a dynamic schema does not mean every producer can pick arbitrary types.

Recommendation: maintain an **attribute dictionary** defining each attribute, its data type, unit, whether multiple values are allowed, and canonicalization rules on write.

## 8. When Filtering Multiple Dynamic Fields in One Query

A common query:

~~~javascript
db.products.find({
  category: "laptop",
  "attributes.ramGB": { $gte: 16 },
  "attributes.cpu.cores": { $gte: 8 }
})
~~~

Here there are three predicates:

1. `category` on a core field.
2. `attributes.ramGB` on one dynamic path.
3. `attributes.cpu.cores` on another dynamic path.

**You cannot treat a wildcard index like a compound index** `{category:1,"attributes.ramGB":1,"attributes.cpu.cores":1}`. A wildcard index has its own path/value organization; the optimizer does not automatically combine predicates across multiple paths into a single narrow range scan.

MongoDB may:

- Use the wildcard index for one dynamic path and then `FETCH` documents to evaluate the remaining predicates.
- Choose another index if that index is more selective.
- Use index intersection in supported cases.
- Pick a collection scan when the dataset is small or indexes offer no benefit.

These choices depend on the query planner and MongoDB version. When a multi-field query runs very frequently, consider creating a **dedicated compound index**:

~~~javascript
db.products.createIndex(
  {
    category: 1,
    "attributes.ramGB": 1,
    "attributes.cpu.cores": 1
  },
  { name: "idx_laptop_ram_cpu" }
)
~~~

The trade-off is maintaining an extra index, in exchange for giving a high-traffic laptop query a dedicated access path.

### 8.1. Filtering One Dynamic Field vs. Filtering a Dozen Fields

Wildcard indexes are attractive when there are **many varied queries**, each filtering on one or a few attributes. If a faceted-search UI routinely combines 5–10 conditions, sorts by price, and paginates, evaluate your overall search/query architecture instead of expecting one wildcard index to carry everything.

### 8.2. Stable Core Fields Still Deserve Dedicated Indexes

For instance, if queries always include:

~~~javascript
{
  tenantId: "t-01",
  status: "ACTIVE"
}
~~~

an index:

~~~javascript
db.products.createIndex(
  { tenantId: 1, status: 1, price: 1 },
  { name: "idx_tenant_status_price" }
)
~~~

can serve product listings by tenant, status, and price. The wildcard index under `attributes` complements custom attribute filters. This is a hybrid architecture: **regular indexes for core fields + wildcard for dynamic attributes**.

## 9. Compound Wildcard Indexes

In MongoDB versions supporting **compound wildcard indexes** (introduced in MongoDB 7.0), you can combine one wildcard path with one or more regular fields in the same index. For example:

~~~javascript
// Test only on deployments that support compound wildcard indexes.
db.products.createIndex(
  {
    tenantId: 1,
    "attributes.$**": 1
  },
  { name: "idx_tenant_dynamic_attributes" }
)
~~~

The idea: a multi-tenant system always filters by `tenantId`, while `attributes.*` paths vary by category. The index can support queries such as:

~~~javascript
db.products.find({
  tenantId: "t-01",
  "attributes.sensor.megapixels": { $gte: 20 }
})

db.products.find({
  tenantId: "t-01",
  "attributes.ramGB": { $gte: 16 }
})
~~~

**Things to note:**

- Older versions without compound wildcard support will reject this syntax or capability.
- A compound wildcard index is still **not equivalent** to dedicated compound indexes across multiple distinct dynamic attributes.
- Only one wildcard term is allowed in the index, and it must follow the feature's rules and limits.
- Sorting, multikey behavior, wildcard projection, and query bounds can differ from standard compound B-trees.
- Shard keys, unique constraints, and partial/sparse options must be verified separately for your version and topology.

Do not see `tenantId` at the front and conclude every tenant + multi-attribute query is optimally served. Inspect `explain()` and compare against alternative indexes.

### 9.1. Should You Create Both a Single-Subtree Wildcard and a Compound Wildcard?

Two indexes:

~~~javascript
{ "attributes.$**": 1 }
{ tenantId: 1, "attributes.$**": 1 }
~~~

can serve different query groups, yet maintaining both doubles the wildcard overhead. If nearly every query includes `tenantId`, evaluate the compound wildcard index if supported by your version. If legitimate cross-tenant queries exist, evaluate that workload explicitly. **Never create both merely because both use wildcards.**

## 10. Arrays: Multikey Behavior and Limitations to Remember

A product document may contain:

~~~javascript
{
  _id: "p-401",
  attributes: {
    sizesEU: [40, 41, 42],
    colors: ["black", "brown"],
    upper: { material: "leather" }
  }
}
~~~

Query:

~~~javascript
db.products.find({
  "attributes.sizesEU": 41
})
~~~

`p-401` matches because the array contains `41`. Wildcard indexes handle arrays/multikey values under specific rules; documents with many elements can generate many index entries. Data with very long arrays or deeply nested objects increases key counts and write costs.

### 10.1. Matching a Value Inside an Array

~~~javascript
db.products.find({
  "attributes.colors": "black"
})
~~~

This query finds products whose array contains black. In our sample dataset, `p-401` and `p-501` have black; other products store color in `attributes.color`, which is a **different path**.

This illustrates a data-modeling issue: `color` and `colors[]` are not a single unified logical path. A wildcard index does not automatically merge two fields that happen to mean similar things.

### 10.2. Conditions That Must Match the Same Array Element

Example:

~~~javascript
{
  attributes: {
    variants: [
      { color: "red", stock: 0 },
      { color: "blue", stock: 10 }
    ]
  }
}
~~~

Query:

~~~javascript
{
  "attributes.variants.color": "red",
  "attributes.variants.stock": { $gt: 0 }
}
~~~

can match the document even though no red variant is in stock, because red comes from one element and `stock > 0` comes from another.

Correct query:

~~~javascript
db.products.find({
  "attributes.variants": {
    $elemMatch: {
      color: "red",
      stock: { $gt: 0 }
    }
  }
})
~~~

`$elemMatch` enforces same-element matching. **A wildcard index does not fix incorrect semantics from two separate dotted predicates.** Likewise, do not assume a wildcard index offers the full bound-compounding capabilities of a dedicated compound multikey index for this array structure; inspect the execution plan.

### 10.3. Deeply Nested Arrays

Arrays of arrays, deeply nested objects, and mixed types complicate key generation and query bounds. Exact indexing behavior for such patterns depends on MongoDB version and multikey rules. If a use case frequently queries deeply nested structures, consider **simplifying the schema** or extracting child entities into a separate collection with stable fields rather than relying on wildcards across every layer.

## 11. Limitations to Distinguish from Standard Indexes

Wildcard indexes serve a specific goal: **unpredictable field paths**. Several expectations from B-tree compound indexes do not carry over automatically.

| Misconception | Reality to Remember |
|---|---|
| Having a wildcard means every query uses the index | The planner still evaluates selectivity, paths, values, sort, and cost |
| One wildcard scan optimizes multiple predicates across different paths | Not by default; it may scan one path and `FETCH` to check the rest |
| Wildcards replace compound indexes for stable filter + sort | No; dedicated compound indexes usually have clear advantages |
| Wildcard indexes automatically handle full-text search | No; text/search indexes use different mechanics |
| Wildcard indexes infer business schema types automatically | No; paths and types still need normalization |
| Wildcard indexes always support covered queries | Do not assume; coverage is restricted, verify with `explain()` |
| Wildcards definitely accelerate `sort` on any dynamic field | No; check query shape, `SORT` stage, and supporting indexes |
| Wildcard indexes enforce field existence or uniqueness | No; validation and uniqueness constraints require separate design |
| Indexing dynamic fields makes `$exists:false` fast | Absent fields normally lack useful index keys; verify index eligibility |

### 11.1. Querying a Whole Object vs. Querying Subfields

For example:

~~~javascript
db.products.find({
  "attributes.cpu.cores": 8
})
~~~

specifies a **concrete scalar path**, matching wildcard strengths. By contrast:

~~~javascript
db.products.find({
  "attributes.cpu": { cores: 8, family: "Core" }
})
~~~

compares an embedded object at a path. Whole-object equality has different structural/value semantics than subfield comparisons and is not optimized identically by wildcard indexes. In search designs, prefer querying explicit subfields:

~~~javascript
db.products.find({
  "attributes.cpu.cores": 8,
  "attributes.cpu.family": "Core"
})
~~~

Then measure whether the planner uses the wildcard index or whether a standard index should be added if the pattern is very hot.

### 11.2. Sorting Is Not Included for Free

Query:

~~~javascript
db.products.find({
  "attributes.ramGB": { $gte: 16 }
}).sort({
  price: 1
})
~~~

The index `{"attributes.$**":1}` covers `attributes`, whereas `price` is a different field. There is no basis to expect the wildcard index to supply price order; MongoDB may add a `SORT` stage or pick another access path.

If this query is common, consider an index:

~~~javascript
db.products.createIndex(
  {
    category: 1,
    "attributes.ramGB": 1,
    price: 1
  },
  { name: "idx_category_ram_price" }
)
~~~

Key ordering should be analyzed under equality, range, and sort; since RAM is a range condition, the index may still not provide a global sort on `price` as desired. This is where the ESR rule and benchmarking apply—not choosing indexes by field name alone.

### 11.3. Covered Queries Must Be Verified

A query projecting few fields:

~~~javascript
db.products.find(
  { "attributes.ramGB": 16 },
  { _id: 0, "attributes.ramGB": 1 }
)
~~~

is not automatically covered by a wildcard index. The engine may need to `FETCH` documents due to wildcard index layout and coverage restrictions. Measure `totalDocsExamined` and inspect plan stages instead of assuming a small projection means covered execution.

### 11.4. Null Types and Missing Fields

`attributes.ramGB` may not exist on cameras or chairs. Wildcard indexes behave similarly to sparse indexes for present field paths: if a path is absent, there is no simple value key for that path. Queries like:

~~~javascript
db.products.find({
  "attributes.ramGB": { $exists: false }
})
~~~

should not be expected to use the wildcard index to scan "every document missing the field". Queries checking for missing fields need separate planning, such as a cleaner schema or an explicit presence flag if that query pattern is critical.

In MongoDB, `{field:null}` also has different semantics from `{field:{$exists:false}}` and can match both null and missing fields where applicable. Do not deduce null/missing results solely from whether an index has a key.

### 11.5. Do Not Use Wildcards as Default Unique Business Constraints

To ensure SKU uniqueness within a tenant:

~~~javascript
db.products.createIndex(
  { tenantId: 1, sku: 1 },
  {
    unique: true,
    name: "uq_tenant_sku"
  }
)
~~~

This is an **explicit business constraint**. A wildcard index is not meant to enforce uniqueness across all dynamic fields; unique constraints must be declared on explicit fields or compound keys. The more flexible your schema, the more important it is to separate **dynamic searchable fields** from **immutable identity keys**.

## 12. `wildcardProjection`: Index the Right Subtrees, Avoid Useless Keys

Suppose a document contains:

~~~javascript
{
  _id: "flex-001",
  type: "product",
  attributes: {
    material: "steel",
    weightKg: 2.5
  },
  customFields: {
    partnerCode: "P-100"
  },
  debugDetails: {
    internalNotes: "unindexed"
  },
  rawPayload: {
    // Large import payload; no need to query directly on every field.
    source: "supplier-xyz"
  }
}
~~~

Indexing the whole document `{"$**":1}` would create low-value keys from `debugDetails` and `rawPayload`. You can index only `attributes` and `customFields`:

~~~javascript
db.flex_documents.createIndex(
  { "$**": 1 },
  {
    name: "idx_flex_selected",
    wildcardProjection: {
      attributes: 1,
      customFields: 1
    }
  }
)
~~~

Or use exclusion:

~~~javascript
db.flex_documents.createIndex(
  { "$**": 1 },
  {
    name: "idx_flex_excluding_payload",
    wildcardProjection: {
      debugDetails: 0,
      rawPayload: 0
    }
  }
)
~~~

These are **illustrative alternative configurations**. Before creating one in a real environment:

- Gather query statistics per subtree.
- Identify fields never used for filtering.
- Estimate document sizes and expected key counts.
- Verify projection syntax and constraints against your key pattern and server version.
- Never confuse `wildcardProjection` with `find()` projections or aggregation `$project`.

### 12.1. Why Is Excluding More Not Always Better?

Excluding a subtree shrinks index data, yet if an API later needs to query that subtree, the wildcard index will not support it. Maintain a catalog of UI/API-supported filters, log actual queries, and plan migrations whenever index scope evolves.

### 12.2. Avoid Indexing Sensitive Payloads Unnecessarily

A `customMetadata` branch might accidentally contain tokens, internal notes, or PII. Indexing such data creates additional physical copies/access paths that must be governed. Separate sensitive data from wildcard-indexed regions or exclude it via projection. **Indexes do not grant permissions**, yet they remain data structures carrying security, backup, and encryption responsibilities.

## 13. Measuring the Query Planner with `explain("executionStats")`

Never judge a wildcard index solely by `createIndex()` succeeding. Test representative queries:

~~~javascript
db.products.find({
  "attributes.sensor.megapixels": { $gte: 20 }
}).explain("executionStats")
~~~

And:

~~~javascript
db.products.find({
  "attributes.ramGB": { $gte: 16 }
}).explain("executionStats")
~~~

### 13.1. Metrics to Inspect

| Component | Interpretation |
|---|---|
| `queryPlanner.winningPlan` | Selected execution path |
| `IXSCAN` | Index key scan stage |
| `COLLSCAN` | Collection scan stage |
| `FETCH` | Stage reading documents to project fields or evaluate residual predicates |
| `SORT` | Separate in-memory sort stage |
| `indexName` | Index used by the plan |
| `indexBounds` | Key range examined during the index scan |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of returned documents |
| `executionTimeMillis` | Execution time recorded during explain |

Wildcard indexes carry **path** metadata in key/plan structures. Exact representations of paths and stages can vary across versions and execution engines; avoid building monitoring tools that hardcode a single JSON path inside `explain()`.

### 13.2. Three Common Plans

**A. `COLLSCAN`:** either the query does not match the index, or the collection is small enough that a scan is cheaper. Our 10-document lab dataset can show `COLLSCAN` even after creating the wildcard index.

**B. `IXSCAN` + `FETCH`:** the index locates candidates along one path, and MongoDB reads documents to return other fields or check remaining predicates. This is normal.

**C. `IXSCAN` + `SORT`:** filtering uses an index, yet results still require a separate sort stage. If sorting is expensive and the query is frequent, evaluate a dedicated index.

### 13.3. Comparing Wildcard vs. Dedicated Indexes

Suppose a laptop API commonly filters by RAM and sorts by price:

~~~javascript
const query = {
  category: "laptop",
  "attributes.ramGB": { $gte: 16 }
}

db.products.find(query)
  .sort({ price: 1 })
  .limit(20)
  .explain("executionStats")
~~~

Then create a candidate index in the lab:

~~~javascript
db.products.createIndex(
  {
    category: 1,
    "attributes.ramGB": 1,
    price: 1
  },
  { name: "idx_laptop_ram_price" }
)
~~~

Re-run with the same filter/sort/limit/projection and compare `keysExamined`, `docsExamined`, `SORT` stages, and latency on a sufficiently large dataset. **Never conclude from a single run on 10 products**; measurements on tiny datasets are dominated by fixed overhead and cache state.

### 13.4. Using `hint()` Sparingly

To test a specific index, you can hint by name:

~~~javascript
db.products.find({
  "attributes.ramGB": 16
}).hint("idx_attributes_wildcard")
  .explain("executionStats")
~~~

Whether hinting a wildcard index works and how the scan satisfies the query depend on version, query shape, and actual index existence. Use `hint` only in controlled experiments; never pin a production API to a fixed index without understanding query planner behavior and future index changes.

## 14. Footprint and Write Amplification

A wildcard index can generate keys for many fields inside its indexed subtree. A document with 5 dynamic fields has a very different index cost than one with 300 dynamic fields or a very long array.

Hypothetical scale illustration:

~~~text
100,000 products
50 indexed scalar attributes / product

Conceptual entry count on the order of:
100,000 × 50 = 5,000,000 path/value entries
~~~

This is a rough scale intuition, **not an exact formula** for WiredTiger key counts or bytes: arrays, nested fields, types, deduplication, compression, and storage layout all materially affect real footprint.

### 14.1. Cost Drivers

| Driver | Potential Impact |
|---|---|
| Many dynamic fields | More index keys, larger disk and cache usage |
| Long arrays | Multikey entries grow, queries examine more values |
| Updating dynamic fields | Adds, removes, or updates corresponding keys |
| Adding a brand-new attribute | No new index definition needed, yet extra keys must be maintained |
| Additional indexes for other queries | Total write amplification increases |
| Multi-attribute queries | May `FETCH`/scan more documents |
| Index builds on large collections | CPU, I/O, temporary space, and build duration |

### 14.2. Checking Index Size

~~~javascript
const stats = db.products.stats()

printjson({
  count: stats.count,
  size: stats.size,
  storageSize: stats.storageSize,
  totalIndexSize: stats.totalIndexSize,
  indexSizes: stats.indexSizes
})
~~~

`indexSizes` shows footprint by index name. Storage size does not equal actual RAM occupied in cache, nor does it capture full costs across replicas, backups, journals, or shards.

### 14.3. Checking Whether an Index Is Frequently Used

~~~javascript
db.products.aggregate([
  { $indexStats: {} }
])
~~~

`$indexStats` reports index access counts over the observation window. Never declare an index useless just because it saw few hits over a couple of hours: seasonal filters or admin jobs can still depend on it.

### 14.4. Weighing the Read/Write Ratio

If a system writes 100,000 products/hour while rarely querying dynamic fields, a wildcard index may impose disproportionate overhead. Conversely, if an API supports customizable attribute filtering across millions of products under heavy read load, a properly scoped wildcard index can dramatically reduce the operational burden of managing hundreds of dedicated indexes.

There is no magic "use wildcard above N fields" threshold. Measure against workload, schema shape, and SLOs.

## 15. Data Modeling Alongside Wildcard Indexes

A wildcard index works well only when **data representation is consistent enough** to query accurately.

### 15.1. Standardize Field Paths

Suppose three suppliers store RAM differently:

~~~javascript
{ attributes: { ramGB: 16 } }
{ attributes: { ram: "16GB" } }
{ attributes: { memory: { size: 16, unit: "GB" } } }
~~~

These are **three distinct paths/schemas**. A wildcard index can index whichever paths exist, yet does not know they all mean "16 GB of RAM". Querying one path will not automatically retrieve the other semantic variants.

Define canonicalization rules:

~~~javascript
{
  attributes: {
    ramGB: 16
  }
}
~~~

Alongside the canonical field, you can retain raw supplier input outside the indexed scope for auditing/import debugging if needed.

### 15.2. Data Dictionary for Dynamic Attributes

An attribute definition catalog might store:

~~~javascript
{
  _id: "ramGB",
  categories: ["laptop", "desktop"],
  valueType: "number",
  unit: "GB",
  filterable: true,
  sortable: false,
  min: 1,
  max: 2048
}
~~~

This helps you:

- Validate types, ranges, and units before writing.
- Govern which fields are searchable.
- Drive category-specific filter UIs.
- Restrict valid dynamic path names.
- Plan dedicated indexes for high-load attributes.

A wildcard index is an **access mechanism**, not a replacement for managing business schemas and metadata.

### 15.3. Field Names Containing Dots or Starting with `$`

MongoDB has special rules and APIs for field names containing dots or `$` characters. Such field names are not always addressed like ordinary dotted paths. Depending on version and expression, `$getField` or specialized accessors may be needed; wildcard indexes do not automatically resolve arbitrary query expressions on literal dotted field names.

When partners submit attribute keys, it is best to **normalize or map them to safe, stable keys**, rather than treating arbitrary user-supplied strings as direct MongoDB field paths.

### 15.4. Never Turn Unvalidated Dynamic Field Names into Raw Query Expressions

If an API accepts:

~~~http
GET /products?attribute=ramGB&min=16
~~~

the server might build a query:

~~~javascript
const attributeName = "ramGB" // Obtained after whitelist/dictionary validation.
const path = "attributes." + attributeName

db.products.find({
  [path]: { $gte: 16 }
})
~~~

In production, `attributeName` must be validated against a dictionary, character/length rules, authorization checks, and value types. **Never concatenate untrusted input directly into field paths** and allow callers to touch core fields or inject query operators.

## 16. Wildcard Indexes vs. Alternative Models

### 16.1. Small, Stable Set of Fields

If only 5–10 important fields exist and queries are stable, dedicated indexes are usually clearer:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  category: 1,
  "attributes.ramGB": 1
})
~~~

This index targets a specific access pattern. A wildcard index may carry unnecessary keys if only a single field is truly queried.

### 16.2. Entity–Attribute–Value (EAV) in a Separate Collection

When attribute counts vary wildly, you can store one document per attribute value:

~~~javascript
// Collection product_attribute_values
{
  productId: "p-101",
  tenantId: "t-01",
  attribute: "ramGB",
  numericValue: 16
}

{
  productId: "p-101",
  tenantId: "t-01",
  attribute: "cpuCores",
  numericValue: 8
}
~~~

Index:

~~~javascript
db.product_attribute_values.createIndex({
  tenantId: 1,
  attribute: 1,
  numericValue: 1,
  productId: 1
})
~~~

Pros: paths become data inside a fixed `attribute` field; easy to index by value type and control entry/partition sizes. Cons: document count multiplies, multi-attribute queries need joins/intersections or complex aggregations, increasing round-trips and synchronization overhead.

### 16.3. Materialized Search Document

Another strategy: keep the operational collection rich and normalized, while maintaining a dedicated search collection structured around selected filterable fields. This requires synchronization pipelines, versioning, and reconciliation between source data and the read model.

### 16.4. Search Engine or Faceted Search

If the application needs full-text relevance, typo tolerance, facet counts, ranking, and complex multi-predicate combinations, consider MongoDB Search or a dedicated search engine. A B-tree wildcard index serves **field predicate lookups**, not search indexes or ranking engines.

### 16.5. Choosing by Workload

| Model | Strengths | When Less Ideal |
|---|---|---|
| Single/compound index | Stable queries, strong filter/sort | Thousands of sparse, variable fields |
| Scoped wildcard index | Many custom fields within one subtree | Complex multi-field filters/sorts, write-heavy workloads |
| Global wildcard + projection | Dynamic fields across multiple subtrees, filterable via projection | Large payloads/sensitive data, excessive path counts |
| Compound wildcard | Stable core fields + one dynamic path, supported version | Multi-path/sort combinations exceeding capability |
| EAV | Tight index control over attribute names/values | Multi-attribute joins, inflated document count |
| Search/read model | Facets, relevance, specialized search UI | Sync pipelines, extra operational overhead |

## 17. Real-World Architecture Pattern: Multi-Category Product Catalog

A system has:

- `tenantId`: fixed, for tenant isolation.
- `category`: fixed, for product category filtering.
- `status`: fixed, for sale status.
- `price`: fixed, for price sorting.
- `attributes`: dynamic object, with category-specific fields.

Diagram:

~~~mermaid
flowchart TD
    API["Product Search API"] --> Auth["Verify tenant + validate filters"]
    Auth --> Planner["Select query by access pattern"]
    Planner --> Core["Core-field compound index"]
    Planner --> Dynamic["Wildcard index on attributes subtree"]
    Planner --> Specialized["Dedicated index for very hot filters"]
    Core --> Data["products collection"]
    Dynamic --> Data
    Specialized --> Data
    Data --> Response["Return product list"]
~~~

### 17.1. Never Let Clients Directly Dictate Indexes

The backend receives user-requested filters, yet must:

1. Authenticate tenant/role.
2. Check whether the attribute is published as filterable.
3. Normalize types, units, and values.
4. Bound predicate count, sort keys, and page size.
5. Construct queries only with permitted paths.
6. Monitor query shapes and performance.

A wildcard index allows many paths to be indexed, while input guardrails prevent expensive queries or unauthorized access across boundaries.

### 17.2. Key Queries Driving Index Design

| API | Typical Query | Strategy |
|---|---|---|
| Listings by tenant/category/price | `tenantId,category,status` + sort `price` | Compound index on stable fields |
| Laptops with RAM ≥ 16 | `attributes.ramGB` | Scoped wildcard, or dedicated index if very hot |
| Cameras with sensor ≥ 20 MP | `attributes.sensor.megapixels` | Scoped wildcard |
| Shoes containing size 41 | `attributes.sizesEU` | Wildcard/multikey; benchmark |
| Laptop filter on both RAM and CPU cores | Two paths inside `attributes` | Measure wildcard; consider dedicated compound index |
| Full-text name/description | Text/relevance query | Search index as needed; do not substitute wildcard |
| Cross-tenant price report | `price` range + sort | Dedicated index or reporting model |

## 18. Deployment and Index Administration

### 18.1. Listing Actual Configurations

~~~javascript
db.products.getIndexes()
~~~

Inspect key patterns and options to confirm the wildcard name/path was created properly. Never treat a migration succeeding without errors as sufficient if an environment has multiple collections or a script might target the wrong database.

### 18.2. Building Indexes on Large Datasets Has Real Costs

On a large collection, building a wildcard index requires reading many documents and generating many keys. Before rolling out:

1. Estimate collection size, dynamic fields per document, nesting depth, and array lengths.
2. Check free disk space, cache, CPU, I/O, replication headroom, and deployment window.
3. Identify which queries should benefit and baseline them first.
4. Test on staging with representative data.
5. Monitor index build progress, read/write latencies, and incidents.
6. Verify metadata and re-measure queries once finished.

Index build behavior on replica sets/sharded clusters and build limits can differ by version; check against your actual deployment.

### 18.3. Hiding an Index to Evaluate Impact

If your version supports hidden indexes:

~~~javascript
db.products.hideIndex("idx_attributes_wildcard")

// When needed for the planner to use it again:
db.products.unhideIndex("idx_attributes_wildcard")
~~~

Hidden indexes are normally still maintained on writes, so hiding is a tool for observing query planner impact—not for saving storage or write cost. Never hide a production index without checking which critical APIs depend on it.

### 18.4. Dropping an Index

~~~javascript
db.products.dropIndex("idx_attributes_wildcard")
~~~

This is a structural change, not a read operation. Run it only in a lab or a planned change window after verifying the index no longer serves important queries. Rebuilding it on a large collection can take substantial time and resources.

### 18.5. Do Not Overuse Wildcard Indexes as a "Just in Case" Fallback

If a collection already has dedicated indexes for most queries, adding a global wildcard index "just in case" can noticeably increase footprint and write latency. When evaluating a wildcard index:

- Start with a specific dynamic subtree.
- Target queries that currently lack a good index.
- Compare performance on real workloads.
- Keep the index only if its benefits outweigh its costs.

## 19. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Creating `{"$**":1}` when only `attributes` is dynamic | Indexes unqueried fields | Use `{"attributes.$**":1}` |
| Treating a wildcard as a compound index across all attributes | Expects multiple predicates to share one scan | Inspect query plans; add dedicated indexes for hot query shapes |
| Using a wildcard instead of a price-sorting index | May trigger large in-memory sorts | Index core filter/sort fields properly |
| Not restricting client-supplied dynamic paths | Unbounded queries, security/resource risks | Attribute dictionary + whitelist + auth |
| Letting one concept use multiple field names | Queries miss products or need complex `$or`s | Canonical schema/paths |
| Storing numbers as inconsistent strings | Range filters miss or misbehave | Type validation, unit normalization |
| Ignoring arrays/multikey behavior | Index bloat, hard-to-optimize queries | Bound array sizes, measure key footprint |
| Forgetting `$elemMatch` on arrays of objects | Combines conditions from two different elements | Enforce same-element matching |
| Assuming wildcards enforce uniqueness | Duplicate business keys | Separate unique index |
| Using wildcards for full-text search | No relevance or fuzzy semantics | Text/search index |
| Creating overlapping wildcards without clear goals | Multiplies write/disk costs | Audit workloads before keeping multiple indexes |
| Thinking more indexes make writes faster | Inserts/updates/deletes do more work | Minimal index set meeting SLOs |
| Benchmarking on 10 documents | Query planner reasonably chooses `COLLSCAN` | Sufficiently large, representative dataset |
| Using compound wildcard on an unsupported version | `createIndex` fails | Verify server version/feature support before rollout |
| Dropping an index without checking rare queries | Slows infrequent yet critical APIs | `$indexStats` + full business cycle observation + rollback plan |

## 20. Hands-On Exercises: Basic to Advanced

Use the `products` collection created in Section 5. Before running each query, predict which `_id`s will be returned.

### Exercise A — Create and Understand Scope

1. Run `getIndexes()` to verify the `_id_` index.
2. Create `{"attributes.$**":1}` named `idx_attributes_wildcard`.
3. Run `getIndexes()` again.
4. Explain why this index does not index `tenantId` or `price`.
5. Contrast its scope with `{"$**":1}` across the whole document.

### Exercise B — Path Equality Queries

1. Find laptops with `attributes.ramGB = 16`.
2. Find cameras with `attributes.lensMount = "E"`.
3. Find chairs with `attributes.material = "mesh"`.
4. Find phones with `attributes.features.eSIM = true`.
5. Find shoes with `attributes.waterproof = true`.

Identify which paths are indexed by the same `idx_attributes_wildcard` and which documents lack the queried field.

### Exercise C — Range Queries

1. Find cameras with `attributes.sensor.megapixels >= 20`.
2. Find chairs with `attributes.maxLoadKg >= 100`.
3. Find laptops with `attributes.cpu.cores >= 8`.
4. In a **lab copy**, change one document to `ramGB: "16"` and predict how the numeric query changes.

### Exercise D — Multiple Dynamic Fields

Query:

~~~javascript
db.products.find({
  category: "laptop",
  "attributes.ramGB": { $gte: 16 },
  "attributes.cpu.cores": { $gte: 8 }
})
~~~

Write a plan prediction: the wildcard index may assist one path while remaining predicates are checked during `FETCH`. Then create a dedicated compound index in the lab and compare `explain()`. Do not assume all predicates share a single wildcard scan.

### Exercise E — Arrays

1. Find products with `attributes.sizesEU = 41`.
2. Find products with `attributes.colors = "black"`.
3. Explain why `attributes.color` (scalar) and `attributes.colors` (array) are not the same path.
4. Given `variants` as an array of objects, write an `$elemMatch` query to find an in-stock red variant.

### Exercise F — Wildcard Projection

Suppose another dynamic collection has `attributes`, `customFields`, `rawPayload`, and `debugDetails`. Write:

- A whole-document wildcard index excluding `rawPayload`/`debugDetails`.
- A wildcard index including only `attributes`/`customFields`.
- Explain why both options should not be created simultaneously out of habit.

### Exercise G — Multi-Tenant

If MongoDB supports compound wildcard indexes, propose:

~~~javascript
{ tenantId: 1, "attributes.$**": 1 }
~~~

Compare it with `{"attributes.$**":1}` alone for queries including `tenantId`. Note version checks, index usage, and write throughput impacts.

### Exercise H — Architecture Selection

Given three workloads:

1. **A:** Only three fixed fields `brand`, `price`, `status` that rarely change.
2. **B:** 300 dynamic attribute types where the UI filters one attribute at a time.
3. **C:** Millions of products requiring multi-attribute facets, text ranking, price sorting, and deep pagination.

Recommend regular indexes, wildcards, or a search/read model for each. Explain query, write-cost, and operational trade-offs.

### Exercise I — Measurement

Execute:

~~~javascript
db.products.find({
  "attributes.ramGB": { $gte: 16 }
}).explain("executionStats")

db.products.aggregate([
  { $indexStats: {} }
])

db.products.stats().indexSizes
~~~

Record the index used, `nReturned`, `totalKeysExamined`, `totalDocsExamined`, and footprint. With a 10-document dataset, do not claim one index is meaningfully faster based on a few milliseconds difference.

## 21. Suggested Exercise Answers

**Exercise B — Equality:**

~~~javascript
db.products.find({ "attributes.ramGB": 16 })
// p-101

db.products.find({ "attributes.lensMount": "E" })
// p-201

db.products.find({ "attributes.material": "mesh" })
// p-301

db.products.find({ "attributes.features.eSIM": true })
// p-501

db.products.find({ "attributes.waterproof": true })
// p-401
~~~

**Exercise C — Range:**

~~~javascript
db.products.find({
  "attributes.sensor.megapixels": { $gte: 20 }
})
// p-201

db.products.find({
  "attributes.maxLoadKg": { $gte: 100 }
})
// p-301

db.products.find({
  "attributes.cpu.cores": { $gte: 8 }
})
// p-101, p-102
~~~

**Exercise E — Arrays:**

~~~javascript
db.products.find({ "attributes.sizesEU": 41 })
// p-401

db.products.find({ "attributes.colors": "black" })
// p-401, p-501

db.products.find({
  "attributes.variants": {
    $elemMatch: {
      color: "red",
      stock: { $gt: 0 }
    }
  }
})
// Only matches documents that actually have a red variant in stock.
~~~

**Exercise H — Architecture:** A should favor dedicated indexes aligned with filters/sorts. B can benefit from a scoped wildcard paired with an attribute dictionary and validation. C requires a search/read model plus dedicated indexes for common facets/sorts/filters; a wildcard index alone rarely solves the entire problem.

## 22. Review Questions

**1. How does a wildcard index differ from a single-field index?**

A single-field index organizes keys for one known field path. A wildcard index organizes multiple paths within its wildcard scope, fitting cases where queried field names vary.

**2. How does `{"$**":1}` differ from `{"attributes.$**":1}`?**

The first targets paths across the entire document per wildcard rules. The second targets only paths beneath `attributes`, narrowing scope when core fields do not need wildcard indexing.

**3. What is `wildcardProjection` used for?**

To include or exclude subtrees from indexing within supported scope, avoiding indexing unneeded fields. It does not control which fields are returned by a `find()` command.

**4. Can a wildcard index let you query a new field without creating a dedicated index?**

Yes, if the new field lies within the wildcard scope and the data type/query shape is supported. It still generates index keys and write overhead.

**5. Why does a wildcard index not replace compound indexes for all queries?**

Wildcards organize path/value entries rather than providing the dedicated multi-field ordering of a compound index tailored to a fixed filter/sort combination. Multi-path queries may still require `FETCH` or another index.

**6. Does a wildcard index automatically optimize sorting by price?**

No. If `price` is outside the wildcard scope and sorting is important, evaluate standard indexes aligned with your filters and sorts.

**7. Can a wildcard index search values inside arrays?**

It can support certain array/multikey queries, though indexing rules, query bounds, and overhead must be verified for your array structure and version. Do not treat wildcards as a universal fix for every nested array shape.

**8. Why does `$elemMatch` still matter when using a wildcard index?**

Because `$elemMatch` ensures multiple conditions hold on the same array object element. An index never fixes a query that accidentally matches across two different elements.

**9. Does a wildcard index enforce field names and data types?**

No. You need schema validation, an attribute dictionary, or normalization pipelines to enforce types, units, and paths.

**10. When should you use a compound wildcard index?**

When you have stable core fields like `tenantId` alongside dynamic paths like `attributes.*`, on a supported MongoDB version (7.0+). Still evaluate query/sort behavior and costs on your real deployment.

**11. If 16 GB of RAM is stored under `ramGB`, `ram`, and `memory.size`, does a wildcard treat them as one field?**

No. Those are three distinct paths. You need canonicalization or query logic aware of each variant.

**12. Does a wildcard index guarantee covered queries?**

Never assume so. Inspect `explain()` for the plan and `totalDocsExamined`; wildcard queries have coverage restrictions.

**13. Why should you avoid indexing an entire document with a wildcard when large raw payloads exist?**

It can generate many keys that never serve queries, inflating disk/cache usage and write amplification. Restrict the subtree or use `wildcardProjection`.

**14. Does MongoDB always use a wildcard index once created?**

No. The query planner may choose another index or `COLLSCAN`, especially on small datasets or when filters/sorts do not align.

**15. Does a wildcard index replace a search engine for full-text and facets?**

No. It serves field-path predicate queries; relevance scoring, linguistic analysis, rich facets, and typo tolerance need a search engine or dedicated read model.

## 23. Quick Command Reference Table

| Purpose | Command Pattern |
|---|---|
| Whole-document wildcard | `db.c.createIndex({"$**":1})` |
| Subtree wildcard under `attributes` | `db.c.createIndex({"attributes.$**":1})` |
| Wildcard on selected subtrees only | `db.c.createIndex({"$**":1},{wildcardProjection:{attributes:1,customFields:1}})` |
| Wildcard excluding payloads | `db.c.createIndex({"$**":1},{wildcardProjection:{rawPayload:0,debugDetails:0}})` |
| Compound wildcard (if version supports) | `db.c.createIndex({tenantId:1,"attributes.$**":1})` |
| Equality query on dynamic path | `db.c.find({"attributes.ramGB":16})` |
| Range query on dynamic path | `db.c.find({"attributes.sensor.megapixels":{$gte:20}})` |
| Scalar array query | `db.c.find({"attributes.sizesEU":41})` |
| Same-element array-of-objects query | `db.c.find({"attributes.variants":{$elemMatch:{color:"red",stock:{$gt:0}}}})` |
| List indexes | `db.c.getIndexes()` |
| Inspect query plan | `db.c.find(filter).explain("executionStats")` |
| View index footprint | `db.c.stats().indexSizes` |
| Monitor index usage | `db.c.aggregate([{$indexStats:{}}])` |
| Hide index (if supported) | `db.c.hideIndex("index_name")` |
| Unhide index | `db.c.unhideIndex("index_name")` |
| Drop index | `db.c.dropIndex("index_name")` |

## 24. Decision Checklist Before Using a Wildcard Index

- [ ] Are field structures genuinely variable, or do only values of fixed fields vary?
- [ ] Have you clearly identified the dynamic subtree such as `attributes`?
- [ ] Can you use a scoped wildcard instead of a global wildcard?
- [ ] Are there payload/debug/PII subtrees that should be excluded from the index?
- [ ] Are paths and data types canonicalized and validated?
- [ ] Have multi-predicate/multi-path queries and critical sorts been separated into workload groups?
- [ ] Have dedicated single/compound indexes been considered for hot filters?
- [ ] Are there missing/null queries or deeply nested array queries that need separate verification?
- [ ] Do you need a compound wildcard index, and does your deployment version support it?
- [ ] Have you inspected `explain` on a sufficiently large dataset, checking `FETCH`/`SORT` and keys/docs examined?
- [ ] Have you estimated index size, write amplification, and cache impact?
- [ ] Is monitoring in place via `getIndexes()`, `$indexStats`, and `stats()`?
- [ ] Do you have a rollout/rollback plan for index changes on replica sets/sharded clusters?
- [ ] Does the dynamic filter API enforce whitelists, authentication, query limits, and resource bounds?

## 25. Conclusion

A **wildcard index** is a valuable tool when MongoDB stores documents with **variable field paths**. The `{"$**":1}` syntax spans the whole document, while `{"attributes.$**":1}` focuses on a dynamic attribute subtree; `wildcardProjection` gives fine-grained control over which subtrees enter the index. Together, they give queries across diverse attributes a viable access path without creating hundreds of individual indexes.

However, a wildcard index **does not replace every compound index, does not guarantee sorting or coverage for every query, and does not enforce schemas or business uniqueness**. Choose a scoped wildcard when fields are truly dynamic, keep standard indexes for stable filters and sorts, pair validators with an attribute dictionary to guard correctness, and measure `explain("executionStats")`, footprint, and write load. The ultimate goal is not "indexing every field", but **giving critical queries a strong access path at a sustainable operational cost**.
