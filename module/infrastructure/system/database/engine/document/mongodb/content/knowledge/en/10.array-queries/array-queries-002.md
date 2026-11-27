# Element Set Conditions with $all, $in, and $nin in MongoDB Array Queries

## 1. The Problem: Finding Documents Based on Array Elements

MongoDB stores data as BSON documents. A field in a document can be an array containing multiple elements of the same or different types. For example, a content system stores **tags** attached to articles:

~~~javascript
{
  _id: "A01",
  title: "MongoDB with Java",
  tags: ["mongodb", "java", "backend"]
}
~~~

From this data, an application may pose three very different requirements:

1. **The article must have both the mongodb and java tags.**
2. **The article has at least one of the mongodb or java tags.**
3. **The article must not have the blocked or spam tags.**

MongoDB provides three query operators commonly used to express these conditions:

- **$all:** the array field contains **all** required values.
- **$in:** the field's value equals **at least one** value in the list; for an array field, **at least one element** must match.
- **$nin:** the field **matches none** of the values in the list; for an array field, **no element** may match. This operator also matches documents that **lack the queried field**.

All three operators take an **array of condition values** in their syntax, yet their semantics differ. In particular, **$in** and **$nin** are not limited to array fields: they also work on single-valued (scalar) fields.

~~~text
                 Querying the tags field
                           |
              +------------+------------+
              |            |            |
             $all         $in          $nin
              |            |            |
         REQUIRES ALL  REQUIRES AT    MUST NOT
         elements      LEAST ONE      MATCH any
                       element        element
              |            |            |
          AND on        OR on         NOT IN on
          membership    membership    membership
~~~

The goal of this lesson is to use these three operators accurately in array queries, handle missing fields, empty arrays, null values, and nested elements, and then apply them in MongoDB Shell and Java/Spring Data applications.

## 2. Preparing the Dataset Used Throughout the Lesson

In **mongosh**, select a dedicated database for experimenting:

~~~javascript
use array_query_lab
~~~

Run once on an **articles** collection that does not yet contain the **_id** values below:

~~~javascript
db.articles.insertMany([
  {
    _id: "A01",
    tenantId: "T1",
    title: "MongoDB for Java",
    tags: ["mongodb", "java", "backend"]
  },
  {
    _id: "A02",
    tenantId: "T1",
    title: "MongoDB for Node.js",
    tags: ["mongodb", "node"]
  },
  {
    _id: "A03",
    tenantId: "T1",
    title: "Java Backend",
    tags: ["java", "backend"]
  },
  {
    _id: "A04",
    tenantId: "T1",
    title: "MongoDB tags repeated",
    tags: ["mongodb", "java", "mongodb"]
  },
  {
    _id: "A05",
    tenantId: "T1",
    title: "Empty tags",
    tags: []
  },
  {
    _id: "A06",
    tenantId: "T1",
    title: "Tags missing"
  },
  {
    _id: "A07",
    tenantId: "T1",
    title: "Null tags",
    tags: null
  },
  {
    _id: "A08",
    tenantId: "T1",
    title: "Legacy scalar tag",
    tags: "mongodb"
  },
  {
    _id: "A09",
    tenantId: "T1",
    title: "Blocked article",
    tags: ["mongodb", "blocked"]
  },
  {
    _id: "A10",
    tenantId: "T1",
    title: "MongoDB and Python",
    tags: ["mongodb", "python"]
  }
]);
~~~

**Note:** Re-running **insertMany** with duplicate **_id** values will cause a **duplicate key** error. If you need to start over, use a new lab database/collection or clean up your test data explicitly. Do not run collection drop commands on production systems.

### 2.1. Quick Data Inspection

~~~javascript
db.articles.find(
  { tenantId: "T1" },
  { _id: 1, title: 1, tags: 1 }
).sort({ _id: 1 });
~~~

Cases to keep in mind:

| Document | **tags** value | Meaning |
|---|---|---|
| A01 | **["mongodb", "java", "backend"]** | Has both mongodb and java. |
| A02 | **["mongodb", "node"]** | Has mongodb, does not have java. |
| A03 | **["java", "backend"]** | Has java, does not have mongodb. |
| A04 | **["mongodb", "java", "mongodb"]** | Has duplicate elements. |
| A05 | **[]** | Has tags field, but the array is empty. |
| A06 | **no tags field** | Missing field. |
| A07 | **null** | Field exists with BSON null value. |
| A08 | **"mongodb"** | Single-valued string field, not an array. |
| A09 | **["mongodb", "blocked"]** | Has a blocked tag. |
| A10 | **["mongodb", "python"]** | Has the python tag. |

The dataset intentionally includes values that deviate from the expected schema to illustrate each operator's behavior. In production applications, consider **schema validation** so the tags field is always an array of strings rather than mixing null, scalar, and missing values.

## 3. $all: Requiring All Elements

### 3.1. Syntax

~~~javascript
db.collection.find({
  arrayField: {
    $all: [requiredValue1, requiredValue2]
  }
});
~~~

For standard value arrays, **$all** requires the field to contain **all** listed values, regardless of their order in the array and without forbidding other elements.

Example finding articles with both mongodb and java:

~~~javascript
db.articles.find(
  {
    tenantId: "T1",
    tags: { $all: ["mongodb", "java"] }
  },
  { _id: 1, tags: 1 }
);
~~~

**Result on the sample dataset:** **A01** and **A04**.

| Document | Has mongodb? | Has java? | Matches $all? |
|---|---|---|---|
| A01 | Yes | Yes | Yes |
| A02 | Yes | No | No |
| A03 | No | Yes | No |
| A04 | Yes | Yes | Yes |
| A09 | Yes | No | No |
| A10 | Yes | No | No |

In A01, the extra **backend** tag does not cause the document to be excluded. **$all does not mean “the array may only contain these exact elements”**.

### 3.2. Element Order Does Not Matter

The following two conditions have the same meaning for string arrays:

~~~javascript
db.articles.find({
  tags: { $all: ["mongodb", "java"] }
});

db.articles.find({
  tags: { $all: ["java", "mongodb"] }
});
~~~

The array in a document can store tags in any order; **$all** checks value containment, not positions.

If business logic requires comparing **exact array order and contents**, use the appropriate whole-array match condition:

~~~javascript
db.articles.find({
  tags: ["mongodb", "java"]
});
~~~

This query requires the array to match the stated order, so it is not equivalent to **$all**. For example, A01 also has the **backend** tag, so it does not match that two-element whole array.

### 3.3. Duplicate Elements Do Not Create a Count Requirement

~~~javascript
db.articles.find({
  tags: { $all: ["mongodb", "mongodb"] }
});
~~~

**$all does not count repetitions of an element.** This condition requires the mongodb element to appear, not to appear at least twice. Thus A01 with one mongodb tag still qualifies; A04 with two mongodb tags also qualifies.

If business logic actually needs counting or repetition constraints, you must use other logic such as aggregation with **$filter/$size** or redesign the data model to store counts explicitly.

### 3.4. A Single Value in $all

~~~javascript
db.articles.find({
  tags: { $all: ["java"] }
});
~~~

For a string array field, this operator requires the array to contain java. Sample results: A01, A03, and A04. If a simple query only needs to check for the element java:

~~~javascript
db.articles.find({
  tags: "java"
});
~~~

An equality condition on an array field can also find documents containing the corresponding element. However, equality also has semantics for scalar fields; if data mixes scalars and arrays, you must explicitly decide which document types are acceptable.

### 3.5. $all with an Empty List

~~~javascript
db.articles.find({
  tags: { $all: [] }
});
~~~

**$all: [] matches no documents** in MongoDB. Do not infer this operator's behavior from the mathematical rule “every set contains the empty set”.

This matters when a UI lets users select “must have all” tags:

- User selects 2 tags: build an **$all** condition with 2 values.
- User selects 0 tags: you must decide as a business rule whether to **not filter by tags** or **return no results**.
- If the intent is “no filter”, **omit the $all condition from the query** when the input is empty instead of passing **$all: []**.

### 3.6. $all Does Not Replace Every Kind of AND Condition

**$all** checks **the presence of values** in an array field. It does not by itself express operations like:

- Every element must be greater than 0;
- Every element must belong to an allowlist;
- Two conditions must occur **on the same subobject**;
- The array must have an exact size.

Those requirements may require **$elemMatch**, **$not**, **$size**, **$expr**, or aggregation and schema validation.

## 4. $in: At Least One Matching Value

### 4.1. Syntax

~~~javascript
db.collection.find({
  field: {
    $in: [value1, value2, value3]
  }
});
~~~

For an array field, **$in** matches a document if **at least one element of the array** equals a value in the condition list. For a scalar field, it matches if the **scalar value** is in the list.

Example finding articles with **mongodb or java**:

~~~javascript
db.articles.find(
  {
    tenantId: "T1",
    tags: { $in: ["mongodb", "java"] }
  },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

**Result on the sample dataset:** **A01, A02, A03, A04, A08, A09, A10**.

Why is **A08** included? Because A08's **tags** is the string **"mongodb"**, not an array, yet **$in** can still compare a scalar field against the listed values.

### 4.2. $in Is OR Across Options

For simple conditions on the same field:

~~~javascript
db.articles.find({
  $or: [
    { tags: "mongodb" },
    { tags: "java" }
  ]
});
~~~

in terms of value-selection meaning, this is equivalent to:

~~~javascript
db.articles.find({
  tags: { $in: ["mongodb", "java"] }
});
~~~

**$in** is usually more concise and easier to generate programmatically when selecting multiple values on the **same field**. Do not use **$in** when business logic requires **both** values, because that is the role of **$all**.

### 4.3. $in on a Scalar Field

Suppose a document has **status**:

~~~javascript
{
  _id: "P01",
  status: "ACTIVE",
  tags: ["mongodb", "java"]
}
~~~

The application can filter:

~~~javascript
db.products.find({
  status: { $in: ["ACTIVE", "DRAFT"] }
});
~~~

Here **status** is a single-valued string. **$in** simply checks whether status equals ACTIVE or DRAFT. So although this lesson focuses on array queries, remember that **$in** has broader applicability.

### 4.4. Empty Input Value Array

~~~javascript
db.articles.find({
  tags: { $in: [] }
});
~~~

**$in: [] matches no documents**, because there is no allowed value to match against.

For a multi-select filter in the UI, an empty list can carry two business meanings:

- **No tags selected, so do not filter by tags:** omit the **$in** condition.
- **No values are allowed:** keep **$in: []** to obtain an empty result.

Distinguish these two meanings right in the request-handling layer rather than letting MongoDB dictate UX.

### 4.5. Using Regular Expressions Inside $in

MongoDB supports regex literals inside the **$in** list:

~~~javascript
db.articles.find({
  tags: {
    $in: [/^mongo/i, "java"]
  }
});
~~~

This matches an element starting with **mongo** (case-insensitive via the **i** flag) or an element equal to **java**. When using regex in **$in**, use a regex expression in the supported syntax; do not drop a **{$regex: "..."}** document as an element of the list and assume it has the same semantics.

Regex query cost depends on the pattern and indexes. Never allow users to send unbounded-length or arbitrary-complexity regex patterns directly into production queries.

### 4.6. Overly Long $in Lists Can Be Expensive

Example:

~~~javascript
db.articles.find({
  tags: { $in: largeListOfThousandsOfTags }
});
~~~

A list of thousands or tens of thousands of choices can increase parsing, planning, and index lookup costs. There is no single fixed optimal threshold for every cluster. For frequent queries, keep the list at a reasonable scale, cap client inputs, and measure with **explain("executionStats")**.

## 5. $nin: Excluding a List of Values

### 5.1. Syntax

~~~javascript
db.collection.find({
  field: {
    $nin: [blockedValue1, blockedValue2]
  }
});
~~~

For an array field, **$nin** selects a document when **no element** of the field matches an excluded value. For a scalar field, it selects the document when the value is not in the list.

Example excluding all articles containing the **blocked** or **python** tag:

~~~javascript
db.articles.find(
  {
    tenantId: "T1",
    tags: { $nin: ["blocked", "python"] }
  },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

**Result on the sample dataset:** **A01, A02, A03, A04, A05, A06, A07, A08**.

**A09** is excluded because it has blocked, and **A10** is excluded because it has python. Notably:

- **A05** has **tags: []**, so it contains no forbidden tags.
- **A06** **lacks the tags field** yet still matches **$nin**.
- **A07** has **tags: null**, which equals neither blocked nor python, so it still matches.
- **A08** is the string mongodb, which is not in the forbidden list, so it still matches.

### 5.2. $nin Matches Documents Missing the Field

This is a critical distinction to remember:

~~~javascript
db.articles.find({
  tags: { $nin: ["blocked"] }
});
~~~

Document **A06**, which lacks the tags field, is still returned. MongoDB specifies that **$nin** also selects documents where the field **does not exist**. If the business rule is “only accept articles that have a valid tags list and do not contain blocked”, that condition is **not enough**.

Requiring the field to exist:

~~~javascript
db.articles.find({
  tags: {
    $exists: true,
    $nin: ["blocked", "python"]
  }
});
~~~

This excludes **A06**, but **can still keep A07** because **null** is the value of an existing field; it also keeps A08 because it is a scalar.

If the schema requires **tags to always be an array**:

~~~javascript
db.articles.find({
  tags: {
    $type: "array",
    $nin: ["blocked", "python"]
  }
});
~~~

On the sample dataset, adding **$type: "array"** yields **A01, A02, A03, A04, A05**. A06 is missing the field, A07 is null, and A08 is a string, so none of them match. **A05** still matches because an empty array is valid by type, even if not necessarily valid by business rules.

### 5.3. $nin Is NOT IN, Not a Requirement to Contain Another Element

Compare:

~~~javascript
// Must not have the blocked element.
db.articles.find({
  tags: { $nin: ["blocked"] }
});

// Must have at least one element other than blocked.
db.articles.find({
  tags: { $elemMatch: { $ne: "blocked" } }
});
~~~

These two queries are **not equivalent**. An array **["mongodb", "blocked"]** has an element other than blocked, so it can match the second query, yet it is still excluded by **$nin**. To express **“does not have any forbidden element”**, **$nin** is more natural.

### 5.4. $nin with an Empty List

~~~javascript
db.articles.find({
  tags: { $nin: [] }
});
~~~

**$nin: []** excludes no values, so it matches every document for this field condition, including documents missing the field. It differs completely from **$in: []** and **$all: []**.

### 5.5. Excluding Multiple Scalar Statuses

~~~javascript
db.orders.find({
  status: { $nin: ["CANCELLED", "DELETED"] }
});
~~~

If an order is **missing status**, it can also be selected. When business logic only accepts known statuses, an **allowlist using $in** is usually easier to control:

~~~javascript
db.orders.find({
  status: { $in: ["NEW", "PAID", "SHIPPED"] }
});
~~~

Choosing an **allowlist** vs. a **denylist** depends on the domain. With heterogeneous data or potentially missing fields, a **$nin** denylist easily produces broader results than intended.

## 6. Direct Comparison of $all, $in, and $nin

Consider the list **["mongodb", "java"]** and the tags field:

| Operator | Question | Condition Model | On **["mongodb", "java", "backend"]** |
|---|---|---|---|
| **$all: ["mongodb", "java"]** | Does it have **both**? | AND across presence requirements. | Matches. |
| **$in: ["mongodb", "java"]** | Does it have **at least one**? | OR across allowed values. | Matches. |
| **$nin: ["mongodb", "java"]** | Does it contain **neither of these two values**? | No element is in the list. | Does not match. |

### 6.1. Full Result Table on the Lab Data

| _id | **$all: ["mongodb","java"]** | **$in: ["mongodb","java"]** | **$nin: ["blocked","python"]** |
|---|---|---|---|
| A01 | Yes | Yes | Yes |
| A02 | No | Yes | Yes |
| A03 | No | Yes | Yes |
| A04 | Yes | Yes | Yes |
| A05 | No | No | Yes |
| A06 | No | No | Yes |
| A07 | No | No | Yes |
| A08 | No | Yes | Yes |
| A09 | No | Yes | No |
| A10 | No | Yes | No |

Distinguishing **A05**, **A06**, and **A07** is especially useful in practice: an empty array, a missing field, and a null value are **not the same state**, even though all three are excluded by the **$all/$in** examples above.

### 6.2. Case of an Empty Condition List

| Condition | Result |
|---|---|
| **{tags: {$all: []}}** | Matches no documents. |
| **{tags: {$in: []}}** | Matches no documents. |
| **{tags: {$nin: []}}** | Matches all documents, even when tags is missing. |

Do not automatically pass all three operators into a query with an empty array when the user has not chosen a filter. The intended API behavior must be explicitly defined.

### 6.3. Which Operator Should You Choose?

~~~text
Find candidates with all required skills
    -> skills: {$all: requiredSkills}

Find products in any preferred category
    -> categories: {$in: selectedCategories}

Hide articles with any forbidden tag
    -> tags: {$nin: forbiddenTags}

Find articles with a valid tag list and no forbidden tags
    -> tags: {$type: "array", $nin: forbiddenTags}
~~~

**$all = must have all**, **$in = may have one of**, **$nin = must not have any listed value**. This is a quick mnemonic, but you still have to consider field types and missing-field cases.

## 7. Combined Queries: Must Have A/B and Must Not Have C

Many problems require both inclusion and exclusion conditions simultaneously.

### 7.1. Has Both mongodb and java, Without blocked

MongoDB does not allow putting two keys **$all** and **$nin** twice in the same JSON document where one overwrites the other. A clear way is to use **$and**:

~~~javascript
db.articles.find({
  tenantId: "T1",
  $and: [
    { tags: { $all: ["mongodb", "java"] } },
    { tags: { $nin: ["blocked"] } }
  ]
});
~~~

On the sample data, A01 and A04 match. If A01 also had blocked, even with all required tags present, it would be excluded.

With operators of different names, you can combine them inside the same field condition object:

~~~javascript
db.articles.find({
  tenantId: "T1",
  tags: {
    $all: ["mongodb", "java"],
    $nin: ["blocked"]
  }
});
~~~

Both approaches are easy to understand. **$and** is useful when conditions are constructed dynamically from independent filter modules, or when multiple expressions must be imposed on the same field.

### 7.2. Has mongodb or java, Without python

~~~javascript
db.articles.find({
  tenantId: "T1",
  tags: {
    $in: ["mongodb", "java"],
    $nin: ["python"]
  }
});
~~~

The inclusion condition requires **at least one** preferred tag; the exclusion condition requires **not containing python**. A10 has mongodb but also has python, so it is excluded.

### 7.3. Combining with Other Conditions

~~~javascript
db.articles.find({
  tenantId: "T1",
  status: { $in: ["PUBLISHED", "SCHEDULED"] },
  tags: { $all: ["mongodb", "java"] }
});
~~~

This example assumes the collection also has a **status** field. If run directly against the Section 2 lab data, documents lack status and therefore will not match that **$in**. The purpose is to illustrate combining an **array** condition with a **scalar** condition.

### 7.4. When to Use $or Instead of $in?

If the options apply to **different fields**, **$or** is the appropriate way to express it:

~~~javascript
db.articles.find({
  $or: [
    { tags: { $in: ["mongodb", "java"] } },
    { category: "DATABASE" }
  ]
});
~~~

You cannot replace this condition with **$in** on tags, because one branch is based on **category**.

## 8. Arrays of Objects: Must Conditions Hold on the Same Element?

Given an **orders** collection with line items:

~~~javascript
db.orders.insertMany([
  {
    _id: "O01",
    tenantId: "T1",
    items: [
      { sku: "A", qty: NumberInt(1), color: "red" },
      { sku: "B", qty: NumberInt(10), color: "blue" }
    ]
  },
  {
    _id: "O02",
    tenantId: "T1",
    items: [
      { sku: "A", qty: NumberInt(5), color: "blue" }
    ]
  },
  {
    _id: "O03",
    tenantId: "T1",
    items: [
      { sku: "A", qty: NumberInt(5), color: "red" },
      { sku: "B", qty: NumberInt(2), color: "green" }
    ]
  }
]);
~~~

### 8.1. Dotted Paths Can Match Different Elements

~~~javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 5 }
});
~~~

This query can match **O01**, even though O01's A line only has qty = 1, because **sku = A** matches the first element and **qty >= 5** matches the second element (sku B, qty = 10).

If the requirement is **a single line item with sku = A and qty >= 5**, you must bind the conditions to the **same element**.

### 8.2. Using $elemMatch for the Same Embedded Document

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 5 }
    }
  }
});
~~~

In the sample data, this query matches **O02** and **O03**, not O01.

**$elemMatch** expresses “there exists at least one array element satisfying all conditions placed inside it”.

### 8.3. $in on a Field of Objects in an Array

~~~javascript
db.orders.find({
  "items.sku": { $in: ["A", "C"] }
});
~~~

Here **items.sku** is the path to the **sku** field of objects inside the **items** array. The query matches if one of the sku values belongs to the A/C list. O01, O02, and O03 all have A.

With this data shape, **$in** is still a condition of **at least one matching value**, with no same-element semantics relative to conditions on other fields.

### 8.4. $all with a Dotted Path

~~~javascript
db.orders.find({
  "items.sku": { $all: ["A", "B"] }
});
~~~

The query finds orders that have **both SKU A and SKU B** among their items. On the sample data, **O01** and **O03** match; O02 does not.

This condition differs from asking “an item has both sku A and sku B”, because a single-valued sku field cannot equal two different values in the same element.

### 8.5. Combining $all with Multiple $elemMatch to Require Multiple Element Types

For example, needing orders that have:

- **One item with sku = A and qty >= 2**;
- **One item with sku = B and qty >= 2**.

~~~javascript
db.orders.find({
  items: {
    $all: [
      {
        $elemMatch: {
          sku: "A",
          qty: { $gte: 2 }
        }
      },
      {
        $elemMatch: {
          sku: "B",
          qty: { $gte: 2 }
        }
      }
    ]
  }
});
~~~

The sample result is **O03**. O01 has B with qty = 10 but A only has qty = 1, while O02 is missing B.

The **$all** syntax with multiple **$elemMatch** expressions is useful when multiple condition groups must be satisfied across **array elements**, where each group can apply to a separate element. It differs from **a single $elemMatch with multiple conditions**, which requires **the same element** to satisfy the entire group.

### 8.6. Comparing Whole Objects vs. Matching by Field

For arrays of embedded documents, an equality condition on the **whole object** has specific BSON matching rules, including structure and field order. Do not use a list of objects in **$in/$all** as a general substitute for attribute-based conditions.

For example, to find an item with **sku = A** and **qty >= 5**, use **$elemMatch** as above instead of trying to compare against an incomplete object literal:

~~~javascript
// Not a general way to express "item A with qty >= 5".
db.orders.find({
  items: {
    $in: [{ sku: "A", qty: 5 }]
  }
});
~~~

The object inside **$in** in this example represents one specific value to match against, not a range condition expression for qty. With embedded documents, prefer **dotted path + $elemMatch** according to business semantics.

## 9. Nested Arrays and Limits of “Set” Intuition

An array field can contain **other arrays**:

~~~javascript
{
  _id: "N01",
  groups: [
    ["admin", "write"],
    ["reader", "view"]
  ]
}
~~~

When needing to match a **subarray as an element**, the query must clearly distinguish the **outer array** from the **subarray value**. Do not assume a nested array is automatically “flattened” into a set of all elements at every depth.

MongoDB supports matching nested array values through certain equality, **$all**, and **$elemMatch** expressions, but special rules apply when the condition value itself is also an array. Therefore, before relying on a complex array-of-arrays query pattern, create representative data and verify the results against your exact server version.

If business logic needs to operate on **permission groups**, a clearer model is often:

~~~javascript
{
  _id: "N01",
  groups: [
    { name: "admin", permissions: ["write"] },
    { name: "reader", permissions: ["view"] }
  ]
}
~~~

Then you can query:

~~~javascript
db.accounts.find({
  groups: {
    $elemMatch: {
      name: "admin",
      permissions: { $in: ["write", "delete"] }
    }
  }
});
~~~

The condition is clearly stated: a group named admin has **at least one permission** in write/delete. A well-structured document makes queries far easier to understand than trying to force array-of-arrays into set syntax.

## 10. Missing, Null, Empty Arrays, and Mismatched Data Types

Array query operators easily cause confusion when data has an inconsistent schema.

### 10.1. Four Distinct States

~~~javascript
{ _id: "X1", tags: ["a", "b"] }
{ _id: "X2", tags: [] }
{ _id: "X3", tags: null }
{ _id: "X4" }
~~~

Respectively, they represent:

1. The field is an array with elements;
2. The field is an empty array;
3. The field exists with a null value;
4. The field does not exist.

If business logic requires **tags** to be a valid array, using **$exists: true** alone is insufficient because null and scalars are also existing fields.

### 10.2. Combining $type to Block Wrong Types

~~~javascript
db.articles.find({
  tags: {
    $type: "array",
    $nin: ["blocked"]
  }
});
~~~

This condition simultaneously checks that the field is an array and has no blocked element. As a result, documents with missing/null/scalar tags are excluded.

If business logic also requires a **non-empty** array, you can add a size check distinct from null/missing. For example, checking for the existence of an element at index 0:

~~~javascript
db.articles.find({
  "tags.0": { $exists: true },
  tags: { $nin: ["blocked"] }
});
~~~

The path **tags.0** can represent the existence of the first element in an array structure. Combine this with schema validation if data can mix types or have special field names.

### 10.3. Note on Null in Value Filters

MongoDB has **null-matching rules** involving documents missing the field in certain condition forms. When constructing a query with **null** inside an **$in/$nin** list, do not rely on SQL **IN/NOT IN** intuition to guess the outcome.

If the question is **“this field must exist and be a valid array of strings”**, use schema validation and explicit type conditions; test missing/null cases separately. **$nin** in particular always requires careful scrutiny because it can include documents missing the field.

### 10.4. Do Not Treat an Array as a Pure Mathematical Set

A MongoDB **array is an ordered sequence of elements** that can contain duplicates and multiple BSON types. **$all/$in/$nin** have semantics for checking values in a sequence, rather than turning an array into a true **set** data type.

Example:

~~~javascript
{
  tags: ["mongodb", "mongodb", "java"]
}
~~~

This document has three elements, in which mongodb appears twice. The condition **$all: ["mongodb", "java"]** matches, but tells you nothing about occurrence counts. You need validation or update logic to prevent duplicates if business logic treats tags as a duplicate-free set.

## 11. Distinguishing $all from $size and Whole-Array Matching

The following three requirements are different:

| Requirement | Representation |
|---|---|
| Has **both a and b**, allowing other values. | **{tags: {$all: ["a","b"]}}** |
| Array has **exactly 2 elements**, regardless of which elements. | **{tags: {$size: 2}}** |
| Array equals **["a","b"] in exact order**. | **{tags: ["a","b"]}** |

Combine **$all** and **$size** when you want all required tags present and want to cap the total number of elements:

~~~javascript
db.articles.find({
  tags: {
    $all: ["mongodb", "java"],
    $size: 2
  }
});
~~~

For a string array of two distinct values, this condition only accepts arrays containing strictly mongodb and java in any order, with no third element. In the sample dataset, **A01** has an extra backend and **A04** has a repeated mongodb element, so neither matches.

**$size** compares array size against a specific value; if you need a range size condition or must handle missing fields, you may need aggregation **$expr/$size** alongside a type-checking step.

## 12. Using $all, $in, and $nin with Properly Typed BSON Values

MongoDB matches according to BSON semantics, including data types and comparison rules. Conditions on an **ObjectId** array must use proper ObjectIds; do not pass hex strings and assume the database will convert them automatically.

### 12.1. ObjectId Arrays

~~~javascript
db.projects.insertOne({
  _id: "PR01",
  memberIds: [
    ObjectId("507f1f77bcf86cd799439011"),
    ObjectId("507f1f77bcf86cd799439012")
  ]
});
~~~

Querying for both members:

~~~javascript
db.projects.find({
  memberIds: {
    $all: [
      ObjectId("507f1f77bcf86cd799439011"),
      ObjectId("507f1f77bcf86cd799439012")
    ]
  }
});
~~~

If the application sends the string **"507f1f77bcf86cd799439011"** instead of an ObjectId, the condition does not have the same meaning. Java/Spring Data applications need converters matching the field type.

### 12.2. Numeric Arrays

~~~javascript
db.measurements.insertOne({
  _id: "M01",
  levels: [NumberInt(10), NumberInt(20), NumberInt(30)]
});

db.measurements.find({
  levels: { $in: [10, 30] }
});
~~~

MongoDB has comparison rules across BSON numeric types. Even so, in systems requiring precision for decimal/int64, use the appropriate data types and avoid passing large 64-bit integers through JavaScript Number before building conditions.

### 12.3. Collation and String Comparison

By default, string comparisons may be case-sensitive depending on the collation in use. For example, **"MongoDB"** and **"mongodb"** are not by default treated as identical tags in every query.

If business logic requires case-insensitive comparisons, you can:

- Normalize tags to a canonical form such as lowercase on write;
- Use an appropriate **collation** on the query and index;
- For certain queries, use a controlled regex.

This decision affects indexes and consistency. Do not slap **/i** onto dozens of queries while ignoring performance consequences.

## 13. How Multikey Indexes Help Array Queries

MongoDB uses a **multikey index** when indexing a field that holds an array value. Each element in the array can contribute appropriate index keys.

### 13.1. Creating an Index for tags

~~~javascript
db.articles.createIndex(
  { tags: 1 },
  { name: "ix_articles_tags" }
);
~~~

If the collection has **tags** arrays, this is a **multikey index**. For example, a document:

~~~javascript
{ _id: "A01", tags: ["mongodb", "java", "backend"] }
~~~

is indexed by the necessary values so documents with corresponding tags can be found without always reading the entire collection.

### 13.2. $in Is Often Suitable for Index Usage

~~~javascript
db.articles.find({
  tags: { $in: ["mongodb", "java"] }
}).explain("executionStats");
~~~

The query planner can choose an index scan if beneficial. When **$in** contains multiple values, MongoDB may need to look up multiple ranges/points in the index and then aggregate matching documents.

### 13.3. $all Can Also Benefit from a Multikey Index

~~~javascript
db.articles.find({
  tags: { $all: ["mongodb", "java"] }
}).explain("executionStats");
~~~

MongoDB can use a multikey index to narrow down candidates and then check the remaining values. **Do not assume** the database necessarily intersects index sets in a simple “one scan per tag then AND” fashion: the actual plan is decided by the query planner.

### 13.4. $nin Often Has Low Selectivity

~~~javascript
db.articles.find({
  tags: { $nin: ["blocked"] }
}).explain("executionStats");
~~~

If most documents are **not blocked**, the query may have to return the majority of the collection. An index on tags does not necessarily help much because **a negation condition does not select a small subset**. MongoDB may have to scan many index keys or documents, or even choose a collection scan.

If the application frequently fetches “all eligible articles”, consider an explicitly managed status field such as **visibilityStatus: "VISIBLE"** with a corresponding index, rather than expecting **$nin** on a blacklist to always run fast. However, you must ensure the derived status is always kept consistent on updates.

### 13.5. Compound Index with a Tenant Condition

In a multi-tenant application:

~~~javascript
db.articles.createIndex(
  { tenantId: 1, tags: 1 },
  { name: "ix_tenant_tags" }
);
~~~

Query:

~~~javascript
db.articles.find({
  tenantId: "T1",
  tags: { $in: ["mongodb", "java"] }
}).explain("executionStats");
~~~

A compound index helps combine tenant filtering with tag lookup. However, choosing field order in a compound index must be based on actual query shapes, filter frequency, and sorts.

An important limitation: MongoDB has rules for **compound multikey indexes** and indexing multiple array fields in the same document. Do not arbitrarily create a compound index covering two independent arrays without checking your MongoDB version's constraints.

### 13.6. Metrics to Read in explain

When using **explain("executionStats")**, pay attention to:

- **winningPlan:** did the query planner choose an index scan or a collection scan?
- **totalKeysExamined:** number of index keys read;
- **totalDocsExamined:** number of documents read;
- **nReturned:** actual number of documents returned;
- Latency and actual runtime conditions if measured at the application layer.

On a small lab dataset, MongoDB may choose **COLLSCAN** because it is cheaper than using an index. Do not conclude an index is useless from just 10 documents; measure on data with representative size and distribution.

## 14. Keeping Queries Correct When Inputs Come from an API

An API might receive:

~~~json
{
  "requiredTags": ["mongodb", "java"],
  "anyTags": ["backend", "tutorial"],
  "excludedTags": ["blocked"]
}
~~~

Business meaning:

- **requiredTags:** must have all.
- **anyTags:** has at least one from the list.
- **excludedTags:** has none of the excluded values.

A filter builder can construct:

~~~javascript
const requiredTags = ["mongodb", "java"];
const anyTags = ["backend", "tutorial"];
const excludedTags = ["blocked"];

const clauses = [
  { tenantId: "T1" }
];

if (requiredTags.length > 0) {
  clauses.push({ tags: { $all: requiredTags } });
}

if (anyTags.length > 0) {
  clauses.push({ tags: { $in: anyTags } });
}

if (excludedTags.length > 0) {
  clauses.push({ tags: { $nin: excludedTags } });
}

const filter = { $and: clauses };
printjson(filter);

db.articles.find(filter);
~~~

**Empty arrays are intentionally skipped** because this API specifies “not selecting that filter means not constraining by it”. Another application might want different semantics, which must be declared explicitly.

### 14.1. Never Let Clients Send Arbitrary MongoDB Query Operators

Do not take a raw JSON body from the client directly as a filter if the API only allows selecting tags:

~~~javascript
// Do not let a user-submitted rawFilter dictate the entire MongoDB query:
db.articles.find(rawFilterFromRequest);
~~~

Instead:

1. Read allowed fields such as **requiredTags, anyTags, excludedTags**.
2. Verify they are string arrays, with bounds on element count and string length.
3. Normalize and deduplicate according to the contract.
4. Attach **tenantId** from the server-side authentication context; never trust a client-supplied tenantId.
5. Build the filter object yourself using only allowed operators.

This construction protects query correctness and limits the risk of users manipulating behavior through unintended MongoDB operators.

### 14.2. Overly Large Value Lists

Limit API filter lists according to business needs. A list of thousands of conditions can increase CPU usage, request size, and query time. If the filterable set is genuinely huge, consider an alternative representation such as a pre-stored group/tag set queried by group ID.

## 15. Usage in the MongoDB Java Sync Driver

The MongoDB Java Sync Driver provides builders in **com.mongodb.client.model.Filters**, making it easy to build BSON filters without assembling JSON strings manually.

### 15.1. $all in Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

// MongoDatabase database has already been initialized from MongoClient.
MongoCollection<Document> articles =
        database.getCollection("articles");

Bson filter = Filters.and(
        Filters.eq("tenantId", "T1"),
        Filters.all("tags", "mongodb", "java")
);

for (Document article : articles.find(filter)) {
    System.out.println(article.getString("_id"));
}
~~~

**Filters.all** creates an **$all** condition. If the collection uses String **_id** as in the lab, you can read it with **getString("_id")**; for ObjectId, use the corresponding type.

### 15.2. $in in Java

~~~java
Bson filter = Filters.and(
        Filters.eq("tenantId", "T1"),
        Filters.in("tags", "mongodb", "java")
);

articles.find(filter).forEach(
        article -> System.out.println(article.getString("title"))
);
~~~

Every document with at least one mongodb or java tag matches. Remember that in the lab data, A08 with a string field still matches **$in**.

### 15.3. $nin in Java

~~~java
Bson filter = Filters.and(
        Filters.eq("tenantId", "T1"),
        Filters.nin("tags", "blocked", "python")
);

articles.find(filter).forEach(
        article -> System.out.println(article.getString("_id"))
);
~~~

Results also include documents without tags. If the domain requires tags to be an array, combine with a BSON type condition in the filter or prevent invalid schema data at the database level.

### 15.4. A Java Filter Combining All Three Groups

~~~java
import static com.mongodb.client.model.Filters.all;
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.in;
import static com.mongodb.client.model.Filters.nin;

Bson filter = and(
        eq("tenantId", "T1"),
        all("tags", "mongodb", "java"),
        in("tags", "backend", "tutorial"),
        nin("tags", "blocked")
);

articles.find(filter).forEach(System.out::println);
~~~

**Filters.and** keeps each condition as a separate clause, avoiding key-overwriting bugs when assembling JSON objects via `put` operations on the same field.

In large applications, constrain filter lists using typed DTOs, validate input values, and enforce query limits (pagination, timeout, projection) per API.

## 16. Usage in Spring Data MongoDB

Spring Data MongoDB provides **Criteria**, **Query**, and **MongoTemplate** to build conditions.

### 16.1. Finding Documents with All Tags

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// MongoTemplate mongoTemplate is injected by Spring.
Query query = new Query(
        Criteria.where("tenantId").is("T1")
                .and("tags").all("mongodb", "java")
);

List<Document> result =
        mongoTemplate.find(query, Document.class, "articles");
~~~

**Criteria.all** is a convenient representation of **$all**. If the application uses an entity class, replace **Document.class** with the appropriate entity type and declare field mappings.

### 16.2. Finding Documents with Any Selected Tag

~~~java
Query query = new Query(
        Criteria.where("tenantId").is("T1")
                .and("tags").in("mongodb", "java")
);

List<Document> result =
        mongoTemplate.find(query, Document.class, "articles");
~~~

### 16.3. Excluding Forbidden Tags

~~~java
Query query = new Query(
        Criteria.where("tenantId").is("T1")
                .and("tags").nin("blocked", "python")
);

List<Document> result =
        mongoTemplate.find(query, Document.class, "articles");
~~~

**Criteria.nin** does not automatically exclude documents missing tags. If the application requires the tags field to be present and an array, add appropriate type/schema controls.

### 16.4. Building Dynamic Filters

Do not try calling **Criteria.where("tags")** repeatedly and attaching multiple criteria on the same field with incompatible APIs. A simple pattern is to build a **list of Criteria**, then combine them with **andOperator**:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

List<String> requiredTags = List.of("mongodb", "java");
List<String> anyTags = List.of("backend", "tutorial");
List<String> forbiddenTags = List.of("blocked");

List<Criteria> clauses = new ArrayList<>();
clauses.add(Criteria.where("tenantId").is("T1"));

if (!requiredTags.isEmpty()) {
    clauses.add(Criteria.where("tags").all(requiredTags));
}

if (!anyTags.isEmpty()) {
    clauses.add(Criteria.where("tags").in(anyTags));
}

if (!forbiddenTags.isEmpty()) {
    clauses.add(Criteria.where("tags").nin(forbiddenTags));
}

Criteria combined = new Criteria().andOperator(
        clauses.toArray(new Criteria[0])
);

Query query = new Query(combined);
~~~

This snippet assumes the DTO has been validated and lists are bounded. **tenantId** must come from the real application's authorization context.

### 16.5. Notes on Mapping and BSON Types

If **tags** in a Java entity is declared as **List<String>**, Spring Data maps fields according to conventions and configured converters. However, legacy documents storing tags as a string or null can still exist in the collection; code should not assume every result conforms to the new model without migration or validation.

For lists of **ObjectId** or converted enums, inspect the representation stored in MongoDB and use the matching Java type. A list of hex strings will not necessarily match a BSON ObjectId array.

## 17. Performance When Combining Condition Sets and Indexes

### 17.1. Comparing Selectivity

Suppose a collection has 1 million articles:

- 2% contain both mongodb and java;
- 40% contain at least one of the two tags;
- 98% do not contain blocked.

These are **hypothetical numbers**, not measured metrics.

**$all** can return a small set when combining rare tags. **$in** can return many more documents. **$nin** with blocked only excludes 2% of the data, so it has very low selectivity and may end up reading nearly the entire collection.

Even with the same multikey index on tags, the three queries still have different costs.

### 17.2. Using Positive Conditions to Narrow Scope

Instead of:

~~~javascript
db.articles.find({
  tags: { $nin: ["blocked"] }
});
~~~

If the API already knows the tenant and status, include them:

~~~javascript
db.articles.find({
  tenantId: "T1",
  status: "PUBLISHED",
  tags: { $nin: ["blocked"] }
});
~~~

The **tenantId/status** conditions can help shrink the examined dataset, provided the fields/indexes and actual data fit. You cannot claim a new query is always faster without measuring.

### 17.3. Never Treat $nin as the Sole Security Mechanism

For example, an application hides content using **tags: {$nin:["private"]}**. If a record lacks the tags field, it is still returned. This is a logic vulnerability if **private** represents access control.

Access permissions should be modeled with a reliable **authorization/visibility** mechanism featuring safe defaults and server-side checks; **$nin** on an optional field cannot replace authorization logic.

### 17.4. Inspecting Query Plans

~~~javascript
const candidates = [
  { tags: { $all: ["mongodb", "java"] } },
  { tags: { $in: ["mongodb", "java"] } },
  { tags: { $nin: ["blocked", "python"] } }
];

for (const filter of candidates) {
  const plan = db.articles.find(filter).explain("executionStats");
  printjson({
    filter: filter,
    returned: plan.executionStats.nReturned,
    keysExamined: plan.executionStats.totalKeysExamined,
    docsExamined: plan.executionStats.totalDocsExamined
  });
}
~~~

On a small dataset, metrics may be too small to draw performance conclusions. When benchmarking for real, check data volume, cardinality, indexes, projections, sorts, and cache effects.

## 18. Common Mistakes

### 18.1. Using $in When All Values Are Required

**Wrong intent:**

~~~javascript
// Wants both mongodb and java,
// but $in only requires one of the two.
db.articles.find({
  tags: { $in: ["mongodb", "java"] }
});
~~~

**Right intent:**

~~~javascript
db.articles.find({
  tags: { $all: ["mongodb", "java"] }
});
~~~

### 18.2. Using $nin to Prove a Field Is Valid

~~~javascript
db.articles.find({
  tags: { $nin: ["blocked"] }
});
~~~

This query **does not prove** that the tags field is present, non-null, and an array. Schema validation and type conditions are required based on business rules.

### 18.3. Believing $all Counts Occurrences

~~~javascript
db.articles.find({
  tags: { $all: ["mongodb", "mongodb"] }
});
~~~

This does not enforce having **two** mongodb elements. To count, you must use a different expression.

### 18.4. Passing an Empty Condition List Without Defining Its Meaning

~~~javascript
{ tags: { $all: [] } } // no results
{ tags: { $in: [] } }  // no results
{ tags: { $nin: [] } } // excludes nothing
~~~

When a user deselects a filter, do not accidentally produce empty results or return all data unexpectedly.

### 18.5. Using Multiple Dotted-Path Conditions and Assuming Same Element

~~~javascript
{
  "items.sku": "A",
  "items.qty": { $gte: 5 }
}
~~~

The two conditions can match two different items. If the same item is required, use **$elemMatch**.

### 18.6. Unintentionally Mixing Scalars and Arrays

~~~javascript
{ tags: "mongodb" }
{ tags: ["mongodb"] }
~~~

**$in** can match both. If the business schema only permits arrays, validate/migrate; do not assume query results prove documents have the right shape.

### 18.7. Assuming $nin Uses Indexes as Effectively as $in

**$nin** usually has low selectivity. If results comprise most of the collection, an index does not guarantee improvement. Measure in practice and consider a positive-state field if appropriate for the domain.

### 18.8. Querying with the Wrong ObjectId Type

~~~javascript
{ memberIds: { $in: ["507f1f77bcf86cd799439011"] } }
~~~

When memberIds holds ObjectIds, do not substitute hex strings; construct proper ObjectIds.

### 18.9. Assembling JSON Queries by Overwriting Fields

~~~javascript
const filter = { tags: { $all: ["mongodb", "java"] } };

// Overwrites the tags field, losing the $all condition!
filter.tags = { $nin: ["blocked"] };
~~~

Merge differently named operators in the same object or use **$and**:

~~~javascript
const filter = {
  tags: {
    $all: ["mongodb", "java"],
    $nin: ["blocked"]
  }
};
~~~

### 18.10. Passing Raw MongoDB Queries from Client to Database

Do not allow users to submit arbitrary operator objects if the API only needs a list of tags. Use typed DTOs, allowlist fields, validate element counts, and build the query server-side.

## 19. Comprehensive Practice

### Exercise 1 — Has Both Tags

Find articles with **mongodb** and **java**:

~~~javascript
db.articles.find(
  { tags: { $all: ["mongodb", "java"] } },
  { _id: 1, tags: 1 }
);
~~~

**Expected result:** A01, A04.

### Exercise 2 — Has Either Tag

~~~javascript
db.articles.find(
  { tags: { $in: ["mongodb", "java"] } },
  { _id: 1, tags: 1 }
);
~~~

**Expected result:** A01, A02, A03, A04, A08, A09, A10.

### Exercise 3 — Contains No Forbidden Tags

~~~javascript
db.articles.find(
  { tags: { $nin: ["blocked", "python"] } },
  { _id: 1, tags: 1 }
);
~~~

**Expected result:** A01, A02, A03, A04, A05, A06, A07, A08. Explain why A06, which lacks tags, is still selected.

### Exercise 4 — Contains No Forbidden Tags, and tags Must Be an Array

~~~javascript
db.articles.find(
  {
    tags: {
      $type: "array",
      $nin: ["blocked", "python"]
    }
  },
  { _id: 1, tags: 1 }
);
~~~

**Expected result:** A01, A02, A03, A04, A05. Explain why A05 still remains.

### Exercise 5 — Must Have a Required Set of Tags, Without Excluded Tags

~~~javascript
db.articles.find(
  {
    tags: {
      $all: ["mongodb", "java"],
      $nin: ["blocked"]
    }
  },
  { _id: 1, tags: 1 }
);
~~~

**Expected result:** A01, A04.

### Exercise 6 — Find Orders with Both SKU A and B

~~~javascript
db.orders.find({
  "items.sku": { $all: ["A", "B"] }
});
~~~

**Expected result:** O01 and O03.

### Exercise 7 — Find Orders Where the Same Item A Has qty >= 5

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 5 }
    }
  }
});
~~~

**Expected result:** O02, O03; explain why O01 is excluded despite having an item B with qty = 10.

### Exercise 8 — Compare Query Plans

Create a tags index, and run **explain("executionStats")** for **$all/$in/$nin**. Record **nReturned**, **totalDocsExamined**, and **totalKeysExamined**. Then use a larger dataset with a representative tag distribution to observe selectivity differences.

## 20. Self-Check Questions

1. How does **$all** differ from **$in** in terms of AND/OR logic?
2. Given tags = **["mongodb", "java", "backend"]**, why does **$all: ["mongodb","java"]** match despite the third tag?
3. Given tags = **["mongodb","mongodb"]**, does **$all: ["mongodb","mongodb"]** prove the element appears at least twice?
4. Why can **$in** match a document whose tags field is a scalar string?
5. Does **$nin** return documents missing the tags field? What must be added if you do not want that?
6. What is the difference between **$exists: true** and **$type: "array"**?
7. How do the results of **$all: []**, **$in: []**, and **$nin: []** differ?
8. When should you use **$elemMatch** instead of multiple dotted-path conditions?
9. How do you find orders with **at least one SKU A item** and **at least one SKU B item**?
10. How do you ensure that both **sku = A** and **qty >= 5** hold on the same item?
11. How does a **multikey index** help array queries, and why can **$nin** still be slow?
12. If tags holds **ObjectId** values, what can happen when an application passes a list of hex strings to **$in**?
13. For a dynamic filter API, why must the meaning of an empty list be explicitly defined?
14. Why should a denylist filter never be the sole access-control mechanism?

## 21. Key Takeaways for Application Development

~~~text
Business Requirement                           Operator
-----------------------------------------------------------
Has all required skills                        $all
Has at least one selected category             $in
Contains no forbidden tags                     $nin
Has one item satisfying multiple conditions    $elemMatch
Array has exactly N elements                   $size
Accept only documents where field is an array  $type: "array"
~~~

Practical rules:

1. **Choose $all** when every value in the list must be present, regardless of order and allowing extra elements.
2. **Choose $in** when at least one value matches; remember it can also match scalar fields.
3. **Choose $nin** when forbidden values must be excluded; always account for missing fields and low selectivity.
4. **Use $elemMatch** when multiple conditions must apply to the same element of an object array.
5. **Distinguish missing, null, empty arrays, and scalars**. Schema validation keeps data consistent.
6. **Handle empty condition lists intentionally**, preventing the UI from returning unexpected results.
7. **Preserve proper BSON types** when passing conditions, especially ObjectId, Date, and large numbers.
8. **Measure indexes/queries with explain** on representative data; do not assume all three operators perform identically.
9. **Build filters server-side** from DTOs/allowlists, keeping tenant isolation and access control independent of client-selected tag filters.

### Official MongoDB Documentation

- [$all Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/all/) — full-presence semantics, empty arrays, and combining with **$elemMatch**.
- [$in Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/in/) — matching at least one value and usage with arrays.
- [$nin Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/nin/) — excluding values and handling missing fields.
- [Query an Array](https://www.mongodb.com/docs/manual/tutorial/query-arrays/) — basic array query patterns.
- [Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/) — distinguishing dotted paths and **$elemMatch**.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — how indexes support array fields.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — querying with **Filters** in Java.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — using **Criteria**, **Query**, and **MongoTemplate** with MongoDB.

The three operators **$all**, **$in**, and **$nin** often differ by just one character in a query, yet can drastically alter the result set. When designing array queries, first clarify the **“all / at least one / none”** intent, then verify edge cases such as missing fields, null, nested objects, and empty condition lists.
