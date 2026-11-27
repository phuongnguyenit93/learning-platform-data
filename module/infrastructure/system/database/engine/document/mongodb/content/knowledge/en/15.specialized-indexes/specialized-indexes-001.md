# Multikey Indexes for Arrays and Compound Array Index Limitations in MongoDB

## 1. Why Do Arrays Change How MongoDB Indexes Data?

MongoDB stores data as BSON documents. A field can be a single value or an **array** containing multiple values. For example, a product can have multiple tags, multiple colors, or multiple variants:

```javascript
{
  _id: "P100",
  name: "Windbreaker jacket",
  category: "OUTERWEAR",
  tags: ["outdoor", "waterproof", "sale"],
  variants: [
    { color: "black", size: "M", stock: 12 },
    { color: "blue", size: "L", stock: 4 }
  ]
}
```

For a single field `category`, one document typically contributes one key value to the index `{ category: 1 }`. However, for an array field `tags`, a single document can contain multiple searchable elements. MongoDB uses a **multikey index** to generate index keys from array elements, enabling queries such as:

```javascript
db.products.find({ tags: "waterproof" });
```

without necessarily having to scan every document in the collection.

In the *Specialized Indexes* chapter, what matters is not only knowing `createIndex()`, but also understanding:

- Why an index on an array field is called **multikey**.
- When a **compound index** contains both scalar fields and an array field.
- Why MongoDB restricts compound indexes across multiple **independent arrays**.
- How an array containing **embedded documents** differs from two independent arrays.
- The role of `$elemMatch` in ensuring multiple conditions match **the same element**.
- The trade-offs regarding index size, array updates, sorting, covered queries, and uniqueness.

## 2. What Is a Multikey Index?

A **multikey index** is an index that MongoDB uses to generate keys from array values. When creating an index on a field path where the actual data contains an array, MongoDB determines that the index is multikey; there is no need to specify a `multikey: true` option in `createIndex()`.

### 2.1. Indexing a Single Array Field

Suppose we have a sample collection:

```javascript
db.products.insertMany([
  {
    _id: "P100",
    name: "Windbreaker jacket",
    category: "OUTERWEAR",
    tags: ["outdoor", "waterproof", "sale"],
    price: NumberDecimal("750000")
  },
  {
    _id: "P101",
    name: "Running shoes",
    category: "FOOTWEAR",
    tags: ["running", "outdoor"],
    price: NumberDecimal("1200000")
  },
  {
    _id: "P102",
    name: "Laptop bag",
    category: "BAGS",
    tags: [],
    price: NumberDecimal("350000")
  },
  {
    _id: "P103",
    name: "Office desk",
    category: "FURNITURE",
    tags: ["office"],
    price: NumberDecimal("1600000")
  }
]);

db.products.createIndex({ tags: 1 });
```

MongoDB can generate logical keys for each element of the `tags` array:

| Document | `tags` Elements | Search-Relevant Index Key Values |
|---|---|---|
| P100 | outdoor, waterproof, sale | outdoor, waterproof, sale |
| P101 | running, outdoor | running, outdoor |
| P102 | Empty array | No individual tag element to search |
| P103 | office | office |

The table only illustrates **the element values that generate keys**, not an exact replica of the B-tree structure or how MongoDB represents special keys for empty/missing arrays. Each index entry is also associated with the corresponding record so the server can locate the source document.

With the query:

```javascript
db.products.find({ tags: "outdoor" });
```

MongoDB can use the multikey index to find **P100** and **P101**. The user does not have to write special syntax to indicate that `tags` is an array: MongoDB interprets the expression matching an array element according to query rules.

### 2.2. One-Document-to-Many-Keys Model

```text
Document P100
  tags = ["outdoor", "waterproof", "sale"]
            |          |         |
            v          v         v
         index key  index key  index key
         "outdoor"  "waterproof" "sale"
            \          |         /
             \         |        /
               all point to P100
```

Each distinct element can generate an index key to serve searches. If an array has duplicate values within **the same document**, MongoDB does not need to store multiple identical entries for the same key and record ID combination. Nevertheless, the number of array elements and their diversity still significantly impact index size.

### 2.3. Not Just String Arrays

Multikey indexes also apply to arrays of numbers, dates, and arrays of embedded documents:

```javascript
db.students.insertOne({
  _id: "S01",
  scores: [72, 85, 96]
});

db.students.createIndex({ scores: 1 });

db.students.find({ scores: { $gte: 90 } });
```

Here, the query can find students who have **at least one score** of 90 or higher. However, if you want two conditions to apply together to **a single element** of an array or an embedded document, you need to understand `$elemMatch` in a later section.

## 3. How MongoDB Determines an Index Is Multikey

### 3.1. Create the Index First or Insert Arrays First?

Both scenarios can result in a multikey index:

**Scenario A — the collection already has arrays, and the index is created afterward:**

```javascript
db.preExistingArray.insertOne({
  _id: 1,
  topics: ["mongodb", "index"]
});

db.preExistingArray.createIndex({ topics: 1 });
```

**Scenario B — the index is created first, and documents with arrays are inserted afterward:**

```javascript
db.laterArray.createIndex({ topics: 1 });

db.laterArray.insertOne({
  _id: 1,
  topics: ["mongodb", "index"]
});
```

MongoDB manages the multikey property of an index when it encounters array values at the indexed path. The application does not have to drop and recreate the index just because a previously scalar field begins containing an array, **as long as the operation still complies with index limitations**.

### 3.2. Arrays of Nested Objects

Given the document:

```javascript
{
  _id: "O01",
  items: [
    { sku: "BOOK", quantity: 2 },
    { sku: "PEN", quantity: 5 }
  ]
}
```

The following index will be multikey because the path `items.sku` traverses the `items` array:

```javascript
db.orders.createIndex({ "items.sku": 1 });

db.orders.find({ "items.sku": "BOOK" });
```

There is no need to index the entire `items` field to query `items.sku`. The dotted path specifies the exact value to look up within the embedded document elements.

### 3.3. Inspecting with `explain()`

```javascript
db.products.find({ tags: "outdoor" })
  .explain("executionStats");
```

Depending on the version and execution engine, the explain output may show:

- `IXSCAN`: the stage that reads keys from the index.
- `FETCH`: the stage that retrieves documents when index information is insufficient.
- `isMultiKey`: information about the multikey property when the relevant stage provides this field.
- `multiKeyPaths`: the array paths that make the index multikey, if present in explain.
- `totalKeysExamined`: the number of index keys examined.
- `totalDocsExamined`: the number of documents that had to be read.
- `nReturned`: the number of returned documents.

You should not expect every MongoDB version to print the exact same explain structure. For very small collections, the planner may even choose `COLLSCAN` despite an existing index; the goal here is to understand how to observe behavior, not to draw performance conclusions from a handful of documents.

## 4. Compound Multikey Index: One Regular Field and One Array Field

A compound index has multiple keys in a specific order. A pattern that is often very useful is **a scalar field used for equality filtering, followed by an array field**.

### 4.1. Category + Tags Example

```javascript
db.products.createIndex({
  category: 1,
  tags: 1
});
```

This index can generate logical keys such as:

```text
P100 -> ("OUTERWEAR", "outdoor")
        ("OUTERWEAR", "waterproof")
        ("OUTERWEAR", "sale")

P101 -> ("FOOTWEAR", "running")
        ("FOOTWEAR", "outdoor")
```

The query:

```javascript
db.products.find({
  category: "OUTERWEAR",
  tags: "waterproof"
});
```

can use the components of the compound index to narrow the range of keys to scan. A document's `category` value is combined with each element of `tags` to produce keys.

### 4.2. Field Order in a Compound Index Still Matters

These two indexes:

```javascript
{ category: 1, tags: 1 }
{ tags: 1, category: 1 }
```

do not always have the same query plan and performance. You need to consider common query patterns: whether there is a condition on `category`, the comparison operators on each field, sorting requirements, and selectivity.

For example, if most queries filter by **a specific category** and then search for a tag, `{ category: 1, tags: 1 }` is a natural candidate. If queries mainly search for a tag across the whole collection and only occasionally filter by category, you should benchmark to decide the index order.

### 4.3. A Compound Index Can Only Leverage Indexed Information

With:

```javascript
db.products.find(
  { category: "OUTERWEAR", tags: "waterproof" },
  { _id: 0, name: 1, price: 1 }
);
```

The index `{ category: 1, tags: 1 }` does not contain `name` and `price`, so MongoDB may have to read the original document to complete the projection. A multikey index **does not automatically turn every query into a covered query**.

## 5. Core Limitation: Cannot Index Two Independent Arrays in One Compound Index on the Same Document

This is the most common pitfall when designing indexes for documents with multiple arrays.

Suppose a product stores two independent lists:

```javascript
{
  _id: "P200",
  tags: ["sale", "winter"],
  availableSizes: ["M", "L", "XL"]
}
```

You might consider:

```javascript
db.catalog.createIndex({
  tags: 1,
  availableSizes: 1
});
```

However, when a document contains **both indexed fields as independent arrays**, MongoDB does not allow such a compound multikey index. The error is commonly described as **cannot index parallel arrays**.

### 5.1. Why Do Two Independent Arrays Cause Problems?

If MongoDB had to combine every tag with every size in a document, the key pairs would be:

```text
tags = ["sale", "winter"]
sizes = ["M", "L", "XL"]

Hypothetical Cartesian product:
  ("sale",   "M")
  ("sale",   "L")
  ("sale",   "XL")
  ("winter", "M")
  ("winter", "L")
  ("winter", "XL")
```

The two arrays have no positional element-to-element relationship to represent meaningful business pairs. This example is **an intuition explaining combinatorial explosion**, not a statement that MongoDB actually generates six keys and accepts the index: MongoDB enforces the constraint and can reject the operation.

When the two arrays have `m` and `n` elements respectively, the hypothetical number of pairs is `m × n`. With multiple arrays or large arrays, the key count can grow rapidly. MongoDB restricts this **parallel arrays** pattern to avoid unsuitable compound index structures.

### 5.2. Error When Creating an Index on Existing Data

```javascript
db.parallelArraysDemo.insertOne({
  _id: "P200",
  tags: ["sale", "winter"],
  availableSizes: ["M", "L", "XL"]
});

// Invalid for the document above.
db.parallelArraysDemo.createIndex({
  tags: 1,
  availableSizes: 1
});
```

Because document P200 has **two independent array paths** included in the same index specification, the index creation operation is rejected.

### 5.3. Error When Inserting After the Index Already Exists

The constraint is not checked only at index creation time. Suppose the collection initially only contains scalar fields:

```javascript
db.parallelInsertDemo.insertOne({
  _id: "P201",
  tags: "sale",
  availableSizes: "M"
});

db.parallelInsertDemo.createIndex({
  tags: 1,
  availableSizes: 1
});

// New document has two independent arrays; the write operation may be rejected.
db.parallelInsertDemo.insertOne({
  _id: "P202",
  tags: ["sale", "winter"],
  availableSizes: ["M", "L"]
});
```

Once the compound index exists, subsequent inserts or updates must also obey the constraint. A `$set` operation that turns the second scalar field into an array can fail if it causes a document to have two independent arrays in the paths of the same index.

### 5.4. The Rule Is Not Simply "Each Collection May Only Have One Array Field"

This is an important distinction to get right. The limitation applies to **array paths combined by a compound index within a single document**; it does not mean:

- A MongoDB collection can only have one array field.
- A single document cannot contain two arrays.
- Only one multikey index may be created in a collection.
- A compound index is never allowed to include fields that can be arrays in different documents.

For example, the following pattern can be valid for a compound index `{ a: 1, b: 1 }` when **each document has only one of the two indexed fields as an array**:

```javascript
db.separateArrayDocs.insertMany([
  { _id: 1, a: [1, 2], b: 5 },
  { _id: 2, a: 3, b: [7, 8] }
]);

db.separateArrayDocs.createIndex({ a: 1, b: 1 });
```

However, inserting:

```javascript
db.separateArrayDocs.insertOne({
  _id: 3,
  a: [1, 2],
  b: [7, 8]
});
```

will violate the compound multikey index limitation because **the same document** contains two independent arrays on those paths.

**Practical rule:** a single document must not require a compound index to combine keys from **two independent array paths**. When reviewing multi-field indexes involving arrays, examine the actual array paths, rather than merely counting field names starting with `$` or looking at only one document's data.

## 6. Important Case: Multiple Attributes Within the Same Array of Embedded Documents

The "cannot index parallel arrays" limitation can easily lead to the misconception that two paths sharing the same array prefix are always prohibited as well. However, an **array of embedded documents** expresses a relationship between attributes within **the same element** and can support a compound multikey index across multiple paths of the shared array.

### 6.1. Product Variant Model

```javascript
db.variantCatalog.insertMany([
  {
    _id: "P300",
    variants: [
      { color: "black", size: "M", stock: 10 },
      { color: "blue", size: "L", stock: 3 }
    ]
  },
  {
    _id: "P301",
    variants: [
      { color: "black", size: "L", stock: 7 },
      { color: "red", size: "M", stock: 2 }
    ]
  },
  {
    _id: "P302",
    variants: [
      { color: "blue", size: "M", stock: 5 }
    ]
  }
]);

db.variantCatalog.createIndex({
  "variants.color": 1,
  "variants.size": 1
});
```

Here, `variants.color` and `variants.size` both traverse **the same `variants` array path**, not two independent top-level arrays like `tags` and `availableSizes`.

### 6.2. Keys Represent Attribute Pairs Within an Element

For P300, we care about the pairs:

```text
variants[0] = { color: "black", size: "M" }
variants[1] = { color: "blue",  size: "L" }

Data pairs from each element:
    ("black", "M")
    ("blue",  "L")
```

This is different from generating all non-existent color/size combinations:

```text
("black", "L")  <- NOT a variant present in P300
("blue",  "M")  <- NOT a variant present in P300
```

When building an index on attributes of the same array of embedded documents, MongoDB can leverage the relationship between these paths. However, **whether a query guarantees that two conditions hold on the same element depends on the filter syntax**.

### 6.3. Without `$elemMatch`: Conditions Can Match Two Different Elements

```javascript
db.variantCatalog.find({
  "variants.color": "black",
  "variants.size": "L"
});
```

This query can match **P300** even though P300 has no variant that is both black and size L:

- The first element has `color: "black"`.
- The second element has `size: "L"`.
- Conditions on separate dotted paths can be satisfied by **different elements**.

P301 also matches because it actually has an element `{ color: "black", size: "L" }`. If the business requirement is "color black and size L of **the same variant**", returning P300 is a **business-logic false positive**, even though MongoDB processed the written query expression completely accurately.

### 6.4. Using `$elemMatch` to Require the Same Element

```javascript
db.variantCatalog.find({
  variants: {
    $elemMatch: {
      color: "black",
      size: "L"
    }
  }
});
```

The intended result is returned: **P301**, not P300.

`$elemMatch` guarantees that there exists **a single element of the `variants` array** satisfying both conditions simultaneously. This is a fundamental requirement when filtering on related attribute pairs such as:

- `color + size` of a variant.
- `sku + quantity` of an order line item.
- `examType + score` of an exam attempt.
- `warehouseId + stock` of a warehouse location.

### 6.5. `$elemMatch` Also Affects How the Compound Index Is Used

Beyond fixing result semantics, `$elemMatch` on a **shared array path** can also allow the query planner to **compound index bounds** across multiple related paths.

With the index:

```javascript
{ "variants.color": 1, "variants.size": 1 }
```

and the query:

```javascript
{
  variants: {
    $elemMatch: {
      color: "black",
      size: "L"
    }
  }
}
```

MongoDB can evaluate both the color and size conditions in a same-element relationship. If there are only two separate dotted-path predicates, the planner cannot arbitrarily assume they apply to the same element, so bound compounding may be restricted.

**Note:** simply adding `$elemMatch` does not guarantee that a query will use a specific index. Plan selection still depends on version, data, indexes, sort, and other predicates. Read `explain()` to inspect the actual bounds.

## 7. Index Bounds with Multiple Conditions on a Single Array Field

### 7.1. When Two Conditions Can Match Two Different Elements

Suppose each student has an array of scores:

```javascript
db.examResults.insertMany([
  { _id: "S01", scores: [65, 98] },
  { _id: "S02", scores: [75, 82] },
  { _id: "S03", scores: [45, 55] }
]);

db.examResults.createIndex({ scores: 1 });
```

The query:

```javascript
db.examResults.find({
  scores: { $gte: 70, $lte: 90 }
});
```

can match S01, even though S01 has no score in the 70–90 range:

- `98 >= 70` is true.
- `65 <= 90` is also true.
- The two conditions can be satisfied by two different elements.

S02 also matches because it has 75 and 82 within the range, while S03 does not match.

### 7.2. Using `$elemMatch` for Two Conditions on the Same Element

```javascript
db.examResults.find({
  scores: {
    $elemMatch: {
      $gte: 70,
      $lte: 90
    }
  }
});
```

The result is **S02**. This query requires at least one score element that is simultaneously >= 70 and <= 90.

With the multikey index `{ scores: 1 }`, `$elemMatch` also enables MongoDB to **intersect index bounds** for the same array path—for example, the interval `[70, 90]`—instead of having to use one bound and then verify the remaining condition under multi-element matching rules.

### 7.3. Two Terms Worth Distinguishing

| Concept | Meaning in a Multikey Context |
|---|---|
| **Bounds intersection** | Intersecting range bounds on **a single index field** when they must be satisfied by the same element |
| **Bounds compounding** | Combining conditions across **multiple fields** in a compound index into a single search key range |
| **`$elemMatch`** | Expresses the "same array element" constraint, giving the planner a basis to intersect/compound bounds in supported cases |

Not every `$elemMatch` yields the same index advantage. The path where `$elemMatch` is placed must match the array structure and the index field paths.

## 8. Things Indexes Do Not Solve Automatically

### 8.1. `$all`, `$size`, and the Semantics of an Array

```javascript
// Has both tags, possibly in two different elements.
db.products.find({
  tags: { $all: ["outdoor", "waterproof"] }
});

// The tags array has exactly 3 elements.
db.products.find({
  tags: { $size: 3 }
});
```

A multikey index can help queries that search for array elements by value. However, `$size` asks for **array length**, whereas a multikey index does not store an "element count" field in a way that can always be used directly to resolve that predicate.

If the system frequently filters by element count:

```javascript
{
  _id: "P100",
  tags: ["outdoor", "waterproof", "sale"],
  tagCount: 3
}
```

you can consider a derived field `tagCount` and an index `{ tagCount: 1 }`, **if** the application keeps `tagCount` accurate whenever the array changes. You should only make the trade-off of adding a derived field when actual query demand and data volume are large enough to justify the synchronization cost.

### 8.2. An Index on an Array Does Not Automatically Enforce Uniqueness per Sub-Element

Consider a shopping cart:

```javascript
{
  _id: "C01",
  items: [
    { sku: "P01", quantity: 1 },
    { sku: "P01", quantity: 2 }
  ]
}
```

If the business rule states that **one SKU may appear only once in a cart**, an index on `items.sku`—even a **unique multikey index**—should not be treated as a tool that automatically enforces this constraint inside the same document. A unique multikey index has **cross-document** semantics, explained in Section 10.

### 8.3. Indexes Do Not Fix Data Model Bugs

A query asking for color black and size L of the same variant will be wrong if the filter merely combines two independent dotted paths. Adding an index only changes the execution plan the query uses; **it does not automatically fix the meaning of the filter**. Before optimizing performance, you must accurately express the relationship between array elements.

## 9. Multikey Indexes with Sort

Sorting data involving arrays can be more complex than sorting scalar fields.

### 9.1. Queries with Both an Array Filter and a Sort

```javascript
db.products.find({ tags: "outdoor" })
  .sort({ price: 1 });
```

An index candidate:

```javascript
db.products.createIndex({
  tags: 1,
  price: 1
});
```

This compound index has **one array field** `tags` and one scalar field `price`, so it can be a valid design. It can support filtering by tag and sorting by price depending on how the planner uses the index and other predicates.

### 9.2. Sorting Directly on an Array Field

If you run:

```javascript
db.products.find().sort({ tags: 1 });
```

array ordering semantics and the ability to leverage index order follow specific rules. Under MongoDB's array comparison semantics, for an ascending sort, the smallest element can determine the array's sort key; for a descending sort, the largest element can determine it. Sorting directly on an array should not be thought of as "take the first element of the array and sort".

In many cases, sort queries involving a multikey index may need an **in-memory SORT stage**, even when the index exists, because conditions on index bounds and array path prefixes do not satisfy the requirements for using index order.

When optimizing:

1. Identify which field **documents** actually need to be sorted by.
2. If you need to sort by an attribute of an array element, determine **which element** represents the document.
3. If you need to sort **elements inside an array**, use aggregation or update the array with the appropriate semantics, rather than confusing it with sorting documents.
4. Inspect `SORT`, `IXSCAN`, and index bounds in `explain()`.

**There is no universal rule that every multikey index can sort or that none can sort.** Support depends on the specific query.

## 10. Unique Multikey Index: Unique Across Documents, Not Deduplicating Within an Array

This is a very important limitation in data design.

### 10.1. Unique Index on an Array Field

Consider a new collection:

```javascript
db.uniqueTagDemo.createIndex(
  { tags: 1 },
  { unique: true }
);

db.uniqueTagDemo.insertOne({
  _id: "A",
  tags: ["mongodb", "index", "mongodb"]
});
```

Within the scope of the same document, duplicate `"mongodb"` elements **do not automatically trigger an index uniqueness error** just because they appear twice. MongoDB does not need multiple identical entries for the same key and same document.

However, if you insert:

```javascript
db.uniqueTagDemo.insertOne({
  _id: "B",
  tags: ["mongodb", "storage"]
});
```

the operation may be rejected because the `"mongodb"` key of **document B** collides with the key already belonging to **document A**.

In other words, a unique multikey index prevents **two documents from owning the same index value**; it does **not** guarantee that a document's array contains only one copy of each value.

### 10.2. Should You Put a Unique Index on `tags`?

Usually **no**, because two different products can completely legitimately share the tag `"mongodb"` or `"sale"`. A unique multikey index like this example is useful for understanding the rule, but rarely appropriate as a practical product tag index.

If you want multiple products to share tags, create a regular index:

```javascript
db.products.createIndex({ tags: 1 });
```

If you want a child record to have a unique code within the scope of a parent, consider a separate collection with an appropriate unique compound index:

```javascript
// Each orderId + sku pair is a separate document.
db.orderItems.createIndex(
  { orderId: 1, sku: 1 },
  { unique: true }
);
```

An index on the child collection can enforce a clear rule **across line-item documents**, instead of trying to infer sub-field uniqueness inside a document containing an array.

## 11. Covered Queries: Multikey Indexes Can Cover Queries Under Conditions

A **covered query** is a query that can be satisfied from the index without having to fetch the original document to return the requested fields, when the necessary conditions are met.

### 11.1. One Array Field Used for Filtering, Scalar Field Used for Return

Suppose we have the index:

```javascript
db.products.createIndex({
  tags: 1,
  category: 1
});
```

The query only requests `category`:

```javascript
db.products.find(
  { tags: "outdoor" },
  { _id: 0, category: 1 }
);
```

Under suitable conditions, MongoDB can retrieve the scalar field `category` from the index after looking up the tag without needing to return the full document. Therefore, **a multikey index can still support a covered query**.

### 11.2. Why Returning the Array Field Itself Is Usually Not Covered

```javascript
db.products.find(
  { tags: "outdoor" },
  { _id: 0, tags: 1 }
);
```

The query asks to return **the entire `tags` array**. Multikey keys are only search representations; they do not provide all the information needed to reconstruct the array document like the original data in all cases. Consequently, covered query conditions for a multikey index **do not allow the projection to return that array field**.

In addition, queries using `$elemMatch` have their own restrictions and cannot act as multikey covered queries under standard index-coverage rules.

### 11.3. Observing `totalDocsExamined`

```javascript
db.products.find(
  { tags: "outdoor" },
  { _id: 0, category: 1 }
).explain("executionStats");
```

If the plan uses the index and `totalDocsExamined` equals 0, that is a sign the query did not need to fetch documents from the storage engine to produce the result. You should still read the entire plan to ensure the conclusion fits the context.

## 12. Options When Hitting the Compound Multi-Array Index Limit

You should not simply try recreating or dropping indexes every time you see `cannot index parallel arrays`. First, examine the **data model** and **query patterns**.

### 12.1. Create Two Separate Indexes

For a document with:

```javascript
{
  _id: "P400",
  tags: ["sale", "winter"],
  availableSizes: ["M", "L", "XL"]
}
```

two independent indexes are valid:

```javascript
db.catalog.createIndex({ tags: 1 });
db.catalog.createIndex({ availableSizes: 1 });
```

The query:

```javascript
db.catalog.find({
  tags: "sale",
  availableSizes: "L"
});
```

can use one of the two indexes, consider index intersection if the planner supports it and finds it beneficial, or choose another plan. **Do not assume by default** that MongoDB will intersect two indexes into an optimal intersection in every case.

When there are many common queries, two separate indexes with residual filtering sometimes have a better overall cost than a complex document design created solely to get a compound index.

### 12.2. Pair an Array with a Scalar Field Useful for Query Partitioning

If queries commonly include `tenantId` or `category`, you can create:

```javascript
db.catalog.createIndex({
  tenantId: 1,
  tags: 1
});

db.catalog.createIndex({
  tenantId: 1,
  availableSizes: 1
});
```

Each index contains only **one array path**; the two independent indexes coexist on the collection. This is a common strategy when data is filtered by tenant or category and then by one of the arrays.

### 12.3. Convert Two Independent Lists into One Array of Embedded Documents When Paired

Suppose what users want to find is not "products with tag sale and any size L" independently, but **a black variant in size L that is in stock**. In that case, the model:

```javascript
{
  _id: "P500",
  colors: ["black", "blue"],
  sizes: ["M", "L"]
}
```

is not enough to determine which color-size pairs are actually sold. You should store:

```javascript
{
  _id: "P500",
  variants: [
    { color: "black", size: "M", stock: 12 },
    { color: "blue", size: "L", stock: 4 }
  ]
}
```

and use:

```javascript
db.catalog.createIndex({
  "variants.color": 1,
  "variants.size": 1
});

db.catalog.find({
  variants: {
    $elemMatch: {
      color: "black",
      size: "M"
    }
  }
});
```

This approach lets you express **the pairs that actually exist**. However, you should not mechanically turn two independent sets into an array of pairs; if business logic allows all combinations, consider the number of combinations, array bloat risk, and maintenance cost.

### 12.4. Extract the Relationship into a Child Collection

With a very large number of variants or frequent stock updates per variant:

```javascript
// products
{
  _id: "P500",
  name: "Windbreaker jacket"
}

// productVariants
{
  _id: "P500-black-M",
  productId: "P500",
  color: "black",
  size: "M",
  stock: 12
}
```

You can index:

```javascript
db.productVariants.createIndex({
  color: 1,
  size: 1,
  stock: 1
});
```

In the `productVariants` collection, each attribute in a document can be a scalar value, avoiding the parallel arrays limitation. You can apply a unique index on `productId, color, size` if business rules require each variant to be unique and the topology permits:

```javascript
db.productVariants.createIndex(
  { productId: 1, color: 1, size: 1 },
  { unique: true }
);
```

In return, reading a product together with all its variants may require multiple queries or `$lookup`. This is a **trade-off between embedding and referencing**, not a rule that "splitting collections is always better".

### 12.5. Normalize Conditions into an Intentional Search Key

If the application frequently searches for exact known pairs and the set of pairs is small, you can store a derived field such as `variantKeys`:

```javascript
{
  _id: "P500",
  variants: [
    { color: "black", size: "M" },
    { color: "blue", size: "L" }
  ],
  variantKeys: ["black|M", "blue|L"]
}
```

```javascript
db.catalog.createIndex({ variantKeys: 1 });
db.catalog.find({ variantKeys: "black|M" });
```

This solution requires designing an **unambiguous** pair-key encoding, handling delimiter characters, and keeping `variantKeys` synchronized with `variants` in the same operation when needed. If the array data already works cleanly with `$elemMatch` and subfield indexes, there is no need to add a derived field just for shorter syntax.

## 13. Performance: A Long Array Does Not Mean an Index Is Always Good

### 13.1. Multikey Indexes Increase Key Count and Write Cost

A document with thousands of distinct tags can contribute many entries to an index. When updating tags, MongoDB must maintain the corresponding index keys. The cost is not just the size of the original document:

- **Index size** grows with the number of distinct indexed values.
- **Memory cache** must serve more index keys.
- **Writes** can incur extra I/O and CPU to update keys.
- **Index builds** on large collections can consume substantial time and resources.
- **Queries** may have to read many keys if the predicate has low selectivity, and then deduplicate documents.

A tag value like `"sale"` that appears in most products has low selectivity. An index on that tag may not save much work compared to a collection scan, especially if the query returns a huge number of documents.

### 13.2. One Document Can Match Multiple Keys

With an array predicate such as:

```javascript
db.products.find({
  tags: { $in: ["outdoor", "waterproof"] }
});
```

P100 can match **two index keys**, yet `find()` still returns **one P100 document**, not two copies of the same document just because two elements satisfy the condition. Query execution must handle record deduplication when an index scan produces multiple keys pointing to the same document.

### 13.3. Multikey Indexes and Unbounded Arrays

If a document stores an activity history with millions of elements:

```javascript
{
  _id: "U01",
  activityIds: [ /* grows without bound */ ]
}
```

then even if an `activityIds` index helps locate elements, the design is still problematic:

- BSON documents have a **16 MiB** size limit.
- Very large documents make reads and writes heavy.
- An array with an enormous number of index keys increases resource consumption.
- Many concurrent writes to a single document can create a hotspot.

In this situation, splitting activities into a separate collection keyed by `userId` and `activityId` is usually worth considering. A multikey index cannot substitute for proper data lifecycle design.

## 14. Index Evaluation Workflow Before Deployment

For a requirement like "filter products by tag, category, size, and color", you can follow these steps:

### Step 1 — Clarify Predicate Semantics

Are you looking for:

- Products that have the `sale` tag **and** any size `L`?
- Or products that have **a single variant** simultaneously satisfying `color = black`, `size = L`, `stock > 0`?

If it is the second case, you need a data structure that preserves the relationship between attributes of the same variant, and you will typically need `$elemMatch`.

### Step 2 — Identify Which Field Paths Traverse Arrays

For example:

```text
category                 scalar
tags                     array #1
availableSizes           array #2
variants                 array #3 (embedded documents)
variants.color           belongs to the variants array path
variants.size            belongs to the same variants array path
```

Count the **independent arrays indexed within the same document**, rather than simply counting fields in the index key.

### Step 3 — Propose a Small Set of Targeted Indexes

```javascript
// Filter by category and tag.
{ category: 1, tags: 1 }

// Filter by category and independent size.
{ category: 1, availableSizes: 1 }

// Filter by attribute pairs within the same variant.
{ "variants.color": 1, "variants.size": 1 }
```

Avoid proposing `{ tags: 1, availableSizes: 1 }` when actual documents contain two independent arrays.

### Step 4 — Use `explain()`

```javascript
db.variantCatalog.find({
  variants: {
    $elemMatch: {
      color: "black",
      size: "L"
    }
  }
}).explain("executionStats");
```

Inspect the chosen index, `IXSCAN`, `FETCH`, index bounds, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`. Do not look solely at execution time from a single run, especially when cache warmth and data sizes vary.

### Step 5 — Measure Write Load and Storage Size

On large collections, index costs can arise primarily when adding elements to arrays, updating variants, or rebuilding many keys. Consider:

- Frequency of array-updating writes.
- Average element count and extreme tail distribution.
- Query selectivity.
- Number of indexes each write operation must update.
- Index build time and required storage resources.

### Step 6 — Manage Indexes According to Topology

On a sharded collection, you must also consider shard key constraints, unique indexes, and data distribution. Do not infer from the ability to create a compound multikey index on an unsharded collection that it is automatically suitable as a **shard key index**. These rules differ and must be reviewed separately before deploying to a sharded cluster.

## 15. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| You must enable `multikey: true` when creating the index | MongoDB automatically marks an index as multikey when an indexed path contains an array |
| Each document contributes exactly one key to an index | An array field can generate multiple keys corresponding to its elements |
| A document having two arrays is invalid | A document can certainly have multiple arrays; the limit applies to a compound index across independent array paths |
| A collection may have only one multikey index | You can have multiple separate indexes on different array fields |
| `{ tags: 1, sizes: 1 }` is always valid because each field is indexable | Invalid for documents that contain both independent arrays |
| The constraint is checked only when creating the index | Later inserts/updates can also be rejected if they create parallel arrays |
| Two fields from the same array of embedded documents are also always forbidden | You can create a compound multikey index on related paths within the same array path |
| Dotted predicates always match the same embedded document | They can match two different elements; `$elemMatch` is required to bind them to the same element |
| Multikey indexes can always compound all bounds | You must consider `$elemMatch`, array paths, and predicate semantics |
| A unique multikey index removes duplicates within an array | It enforces uniqueness across documents, not deduplication of elements within a single document |
| Multikey indexes can never cover any query | They can cover queries when conditions are met, though usually not when projections return the array or queries use `$elemMatch` |
| Having an index on an array makes `$size` immediately fast | `$size` cannot automatically resolve array length from element entries |
| Creating as many array indexes as possible is better | Indexes increase write overhead, storage size, and maintenance cost |
| `IXSCAN` means the query is optimal | You must examine keys/documents scanned and actual results |

## 16. Practice Exercises

### Exercise 1 — Predict Multikey Index Keys

Given:

```javascript
{
  _id: "P1",
  category: "BOOK",
  tags: ["mongodb", "database", "mongodb"]
}
```

Describe the search-relevant key values when creating:

```javascript
db.exercise.createIndex({ tags: 1 });
db.exercise.createIndex({ category: 1, tags: 1 });
```

Explain why the same value `"mongodb"` appearing twice in the array **does not necessarily create two duplicate entries for the same document**.

### Exercise 2 — Detect Parallel Arrays

Given three documents:

```javascript
{ _id: 1, a: [1, 2], b: 5 }
{ _id: 2, a: 3,      b: [7, 8] }
{ _id: 3, a: [1, 2], b: [7, 8] }
```

Explain:

1. When only the first two documents exist, can the index `{ a: 1, b: 1 }` be created?
2. When the third document is added before creating the index, what happens if you create the index?
3. If the index already exists beforehand, what happens when inserting the third document?
4. Why does this rule not mean "a collection can contain only one array field"?

### Exercise 3 — Conditions on the Same Embedded Document Element

Given:

```javascript
{
  _id: "P2",
  variants: [
    { color: "black", size: "M" },
    { color: "blue", size: "L" }
  ]
}
```

Predict whether P2 matches each of the following filters:

```javascript
// A
{
  "variants.color": "black",
  "variants.size": "L"
}

// B
{
  variants: {
    $elemMatch: {
      color: "black",
      size: "L"
    }
  }
}
```

Explain the difference and propose an appropriate compound multikey index for case B.

### Exercise 4 — Intersecting Conditions on a Numeric Array

With:

```javascript
{ _id: "A", scores: [65, 98] }
{ _id: "B", scores: [75, 82] }
```

Compare:

```javascript
db.exams.find({
  scores: { $gte: 70, $lte: 90 }
});

db.exams.find({
  scores: {
    $elemMatch: { $gte: 70, $lte: 90 }
  }
});
```

Which condition lets MongoDB understand that **the same element** must fall within the range? How does that affect how multikey index bounds are intersected?

### Exercise 5 — Unique Multikey

Given the index:

```javascript
db.tagsDemo.createIndex({ tags: 1 }, { unique: true });
```

Predict:

```javascript
db.tagsDemo.insertOne({ _id: 1, tags: ["a", "a", "b"] });
db.tagsDemo.insertOne({ _id: 2, tags: ["b", "c"] });
```

Why can the first document be accepted even though `"a"` repeats twice, whereas the second document may be rejected? If the business requirement is **each document has no duplicate tags**, where should that be handled?

### Exercise 6 — Covered Queries and Projections

Create data and index:

```javascript
db.coveredDemo.insertOne({
  _id: "D1",
  tags: ["a", "b"],
  category: "C1",
  description: "Long text"
});

db.coveredDemo.createIndex({ tags: 1, category: 1 });
```

Compare:

```javascript
db.coveredDemo.find(
  { tags: "a" },
  { _id: 0, category: 1 }
);

db.coveredDemo.find(
  { tags: "a" },
  { _id: 0, tags: 1 }
);
```

Which query has the potential to be covered by the index? Why is returning the `tags` array different from returning only the scalar field `category`?

### Exercise 7 — Designing for an E-Commerce System

A product has:

- `tags`: multiple marketing tags.
- `availableSizes`: list of sellable sizes.
- `variants`: individual color-size-stock variants.
- `categoryId`: a single category.

The application frequently runs three queries:

1. Find products by `categoryId` and tag `"sale"`.
2. Find products that have any size `"L"`, independent of color.
3. Find products that have **a single variant** with color black, size L, and in stock.

Propose indexes for each query. Explain why you should not necessarily put `tags` and `availableSizes` into **one compound index**. Which case requires `$elemMatch`?

### Exercise 8 — When Should You Split into a Separate Collection?

A product has 30,000 variants and inventory changes continuously. Compare:

- Embedding all `variants` into a single `products` document and using a multikey index.
- Creating a `productVariants` collection where each variant is a document with `productId, color, size, stock`.

Evaluate document size, indexes, write contention, query requirements, atomicity guarantees, and data joining costs. Do not choose a model merely because one `find()` command looks shorter.

## 17. Key Takeaways

**Multikey indexes allow MongoDB to index array elements.** One document can contribute multiple index keys; this capability makes queries by tag, score, or attributes inside embedded documents more efficient under the right conditions.

**The most important compound multikey limitation is parallel arrays.** You cannot compound-index two independent array paths that appear simultaneously in the same document within a single compound index. The rule is enforced both at index creation time and on subsequent writes; it does not forbid a collection from having multiple arrays or multiple separate multikey indexes.

**Arrays of embedded documents have a same-element relationship.** Attributes traversing the same array path can participate in a compound multikey index; when a query requires conditions to hold on **the same element**, use `$elemMatch` to express the right semantics and support bound handling.

**Indexes do not replace data design.** Unique multikey indexes do not prevent duplicate elements inside a single document, `$size` is not automatically resolved by an index, and sorting/covered queries have specific conditions. When you hit the compound multi-array index limit, consider separate indexes, scalar + array, an array of embedded documents, or a child collection based on actual access patterns.
