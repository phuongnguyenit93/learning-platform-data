# Comparing Values with $eq, $ne, $gt, $gte, $lt, and $lte in MongoDB

When querying documents in MongoDB, one of the most common tasks is **comparing a field's value against a reference value**: finding products priced from 20 to under 50, finding stock equal to 0, filtering orders not in the CANCELLED state, or retrieving events that occurred within a time range. MongoDB provides six basic comparison operators in query filters:

- **$eq**: equal to.
- **$ne**: not equal to.
- **$gt**: greater than.
- **$gte**: greater than or equal to.
- **$lt**: less than.
- **$lte**: less than or equal to.

These operators appear in the filter criteria of **find()**, **findOne()**, **countDocuments()**, **updateOne()**, **updateMany()**, **deleteMany()**, and many other operations that accept a filter parameter. Results depend on the actual stored **value and BSON type**, whether the field exists, and how MongoDB handles arrays.

This lesson progresses from basic syntax, sample data, and concrete results to common pitfalls such as **null versus missing fields**, **String versus Number**, **multiple conditions on the same field**, **multi-element arrays**, **Date**, **collation**, and index utilization. Examples use mongosh and include translations to the Java MongoDB Driver and Spring Data MongoDB.

## 1. Comparison Filter Syntax

A MongoDB query typically takes the form:

~~~javascript
db.collection.find(
  { field: { $operator: value } },
  { fieldToReturn: 1 }
)
~~~

Where:

| Component | Meaning |
|---|---|
| db.collection | Collection to query |
| field | Field name to inspect; dot notation can be used for nested fields |
| $operator | One of the six comparison operators |
| value | Reference value compared against field |
| Second argument to find | Projection, deciding which fields are returned; optional |

Example finding products priced greater than 100:

~~~javascript
db.products.find({
  price: { $gt: 100 }
})
~~~

MongoDB evaluates **price > 100** against documents whose value belongs to a comparable BSON type group under query rules. The returned result consists of matching documents, not a single true/false value for the entire collection.

### 1.1. Equality Can Be Shorthand

The following two queries have the same intent for a simple string value:

~~~javascript
db.products.find({
  status: "ACTIVE"
})

db.products.find({
  status: { $eq: "ACTIVE" }
})
~~~

MongoDB supports **direct equality matching**, so when you only need to check equality against a simple value, writing **status: "ACTIVE"** is usually more concise.

The explicit **$eq** syntax is especially useful when explaining operators, building dynamic filters, or keeping code consistent with other comparison operators.

### 1.2. Comparison Is Not Assignment

In a filter:

~~~javascript
{ stock: { $gte: 10 } }
~~~

This is a **read and condition-checking** expression; it does not modify stock. To update data, the application needs an update operation with an update operator such as **$set** or **$inc**. Distinguish query operators from document update operators even though both start with a dollar sign.

## 2. Consistent Sample Dataset for Practice

The examples below use a dedicated database **comparison_lab** and collection **comparisonProducts**. Run the command once in mongosh on an empty test database:

~~~javascript
use comparison_lab

db.comparisonProducts.insertMany([
  {
    _id: "P01",
    name: "Notebook",
    category: "stationery",
    price: NumberDecimal("20.00"),
    stock: NumberInt(0),
    rating: 4.2,
    tags: ["paper", "school"],
    createdAt: ISODate("2026-11-10T08:00:00Z")
  },
  {
    _id: "P02",
    name: "Pen",
    category: "stationery",
    price: NumberDecimal("5.00"),
    stock: NumberInt(35),
    rating: 4.8,
    tags: ["office", "blue"],
    createdAt: ISODate("2026-11-11T08:00:00Z")
  },
  {
    _id: "P03",
    name: "Mouse",
    category: "electronics",
    price: NumberDecimal("25.00"),
    stock: NumberInt(12),
    rating: 4.5,
    tags: ["desk", "usb"],
    createdAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: "P04",
    name: "Keyboard",
    category: "electronics",
    price: NumberDecimal("55.00"),
    stock: NumberInt(7),
    rating: 3.9,
    tags: ["desk", "usb"],
    createdAt: ISODate("2026-11-13T08:00:00Z")
  },
  {
    _id: "P05",
    name: "Desk Lamp",
    category: "home",
    price: NumberDecimal("30.00"),
    stock: NumberInt(2),
    rating: 4.1,
    tags: ["desk", "lighting"],
    createdAt: ISODate("2026-11-14T08:00:00Z")
  },
  {
    _id: "P06",
    name: "Old Book",
    category: "stationery",
    price: NumberDecimal("12.00"),
    stock: NumberInt(3),
    rating: null,
    tags: ["paper"],
    createdAt: ISODate("2026-11-15T08:00:00Z")
  },
  {
    _id: "P07",
    name: "Scratch Pad",
    category: "stationery",
    price: NumberDecimal("9.00"),
    stock: NumberInt(1),
    tags: ["paper", "school"],
    createdAt: ISODate("2026-11-16T08:00:00Z")
  }
])
~~~

**P06** has a rating field with value **null**; **P07 does not have a rating field**. This intentional difference illustrates $eq and $ne with null.

The **price** field is created using **NumberDecimal()** to store BSON Decimal128, **stock** uses BSON Int32, **createdAt** is a BSON Date, and **tags** is an array. Explicit type selection avoids assuming that MongoDB will automatically cast numeric strings or date strings.

Quick reference table:

| _id | name | price | stock | rating | category |
|---|---|---:|---:|---:|---|
| P01 | Notebook | 20.00 | 0 | 4.2 | stationery |
| P02 | Pen | 5.00 | 35 | 4.8 | stationery |
| P03 | Mouse | 25.00 | 12 | 4.5 | electronics |
| P04 | Keyboard | 55.00 | 7 | 3.9 | electronics |
| P05 | Desk Lamp | 30.00 | 2 | 4.1 | home |
| P06 | Old Book | 12.00 | 3 | null | stationery |
| P07 | Scratch Pad | 9.00 | 1 | *missing field* | stationery |

To keep query output concise and in a deterministic order during practice:

~~~javascript
db.comparisonProducts
  .find(
    { stock: { $gt: 0 } },
    { _id: 1, name: 1, stock: 1 }
  )
  .sort({ _id: 1 })
~~~

**Projection** selects which fields to display, while **sort()** determines result ordering. Never assume the default order of find() is always insertion order.

## 3. $eq: Equal to a Value

The **$eq** operator selects documents whose field value equals the requested value under MongoDB comparison semantics.

### 3.1. Equal to a String

~~~javascript
db.comparisonProducts.find({
  category: { $eq: "electronics" }
})
~~~

Result on the sample dataset: **P03 (Mouse)** and **P04 (Keyboard)**.

Equivalent shorthand syntax:

~~~javascript
db.comparisonProducts.find({
  category: "electronics"
})
~~~

Both the field name and data type must match. A document with category as the string "electronics" differs from a document where category is an unrelated object or array.

### 3.2. Equal to a Number

~~~javascript
db.comparisonProducts.find({
  stock: { $eq: NumberInt(0) }
})
~~~

Result: **P01 (Notebook)**. You can also write:

~~~javascript
db.comparisonProducts.find({ stock: 0 })
~~~

For BSON numeric types, MongoDB has numeric comparison semantics that allow comparisons across different numeric types, such as Int32, Int64, Double, and Decimal128 when their numeric values match. However, **BSON String "0" does not equal BSON Number 0**.

If the system stores currency or large numbers requiring precision, use the most appropriate type for both writes and comparisons instead of relying on implicit conversion from String.

### 3.3. Equal to Decimal128

~~~javascript
db.comparisonProducts.find({
  price: { $eq: NumberDecimal("25.00") }
})
~~~

Result: **P03 (Mouse)**. This query does not match documents where price equals the string "25.00"; that is a different value type.

**Note on currency:** Using Decimal128 consistently avoids surprises when converting decimal values through Double. If a Java application uses BigDecimal, configure the mapping/codec to Decimal128 according to the schema.

### 3.4. Equal to Date and ObjectId

Example BSON Date field:

~~~javascript
db.comparisonProducts.find({
  createdAt: {
    $eq: ISODate("2026-11-12T08:00:00Z")
  }
})
~~~

Result: **P03 (Mouse)**.

If another collection has **_id** as an ObjectId:

~~~javascript
db.customers.find({
  _id: {
    $eq: ObjectId("66f1c2a4b1d2e3f405162738")
  }
})
~~~

An ObjectId value does not automatically equal its corresponding hex string. Likewise, a Date does not automatically equal an ISO-8601 formatted String. MongoDB compares BSON values rather than inferring types from string formatting.

## 4. $ne: Not Equal to a Value

The **$ne** operator selects documents whose field is **not equal** to the reference value. A very important detail: **$ne also typically matches documents that do not contain the inspected field**.

### 4.1. Not Equal to a String

~~~javascript
db.comparisonProducts.find({
  category: { $ne: "electronics" }
})
~~~

Result: **P01, P02, P05, P06, P07**. Only P03 and P04 are excluded because their category equals "electronics".

If a document does not have a category field, it is also generally selected by **category: { $ne: "electronics" }**, because it does not contain a value equal to "electronics".

### 4.2. Not Equal to a Number

~~~javascript
db.comparisonProducts.find({
  stock: { $ne: NumberInt(0) }
})
~~~

Result on the sample dataset: **P02 through P07**, because only P01 has stock equal to 0.

In business logic, "stock not equal to 0" does not necessarily mean "in stock": negative stock, null, or a missing field must all have defined handling. If you want positive stock, use **$gt: 0** instead of **$ne: 0**.

### 4.3. Missing Field: An Important Distinction

Try:

~~~javascript
db.comparisonProducts.find(
  { rating: { $ne: 4.8 } },
  { _id: 1, rating: 1 }
).sort({ _id: 1 })
~~~

The result includes **P01, P03, P04, P05, P06, and P07**. P02 is excluded because its rating equals 4.8.

P06 has rating equal to null and P07 does not contain rating, yet both are still selected when comparing not equal to 4.8.

To consider only documents that **have the rating field** and are not equal to 4.8:

~~~javascript
db.comparisonProducts.find({
  rating: {
    $ne: 4.8,
    $exists: true
  }
})
~~~

Result: **P01, P03, P04, P05, and P06**. P07 is excluded because it lacks the rating field. **P06 is still selected** because null is not equal to 4.8.

To exclude both null and missing fields, the condition **$ne: null** has special semantics, covered in a later section.

### 4.4. $ne May Have Poor Selectivity

A condition like **status != "CANCELLED"** may match most of the collection. In that case, the query has to read many documents and an index may not provide significant improvement.

If business logic only requires specific states such as NEW and PAID, an **$in** condition with an explicit list of valid states is often clearer and more selective. However, do not alter semantics silently: the enumerated states must match business rules, and missing fields must be handled intentionally.

## 5. $gt: Strictly Greater Than

**$gt** stands for *greater than*. It requires the field value to be **greater than** the reference value; equal values are excluded.

### 5.1. Comparing Prices

~~~javascript
db.comparisonProducts.find({
  price: {
    $gt: NumberDecimal("25.00")
  }
})
~~~

Result: **P04 (55.00)** and **P05 (30.00)**. **P03 (25.00)** is not selected because it equals the threshold rather than exceeding it.

### 5.2. Finding Items in Stock

~~~javascript
db.comparisonProducts.find({
  stock: { $gt: 0 }
})
~~~

Result: **P02, P03, P04, P05, P06, P07**. P01 has stock equal to 0 and is excluded.

This is an example where **$gt** fits better than **$ne**: "in stock" typically requires **positive stock**, not merely "not equal to 0".

### 5.3. Comparing with Date

~~~javascript
db.comparisonProducts.find({
  createdAt: {
    $gt: ISODate("2026-11-13T08:00:00Z")
  }
})
~~~

Result: **P05, P06, P07**. P04 has createdAt equal to the exact timestamp provided, so it is not selected.

Date in MongoDB represents a point in time. If you want to query from the **start of the day** rather than exactly 08:00:00 UTC, choose the start-of-day timestamp and specify the corresponding time zone and business semantics.

## 6. $gte: Greater Than or Equal To

**$gte** stands for *greater than or equal*. The difference from $gt is that it includes **equality**.

~~~javascript
db.comparisonProducts.find({
  price: {
    $gte: NumberDecimal("25.00")
  }
})
~~~

Result: **P03 (25.00), P04 (55.00), and P05 (30.00)**.

Comparison with $gt from the previous section:

| Operator | Mathematical condition | Is price 25.00 selected? |
|---|---|---|
| $gt: 25 | price > 25 | No |
| $gte: 25 | price ≥ 25 | Yes |

Another example, finding products with stock of at least 10:

~~~javascript
db.comparisonProducts.find({
  stock: { $gte: 10 }
})
~~~

Result: **P02 (35)** and **P03 (12)**.

In business requirements, phrases such as **"at least"**, **"from ... upward"**, and **"no less than"** usually map to $gte. Always confirm whether the exact boundary value is included before choosing the operator.

## 7. $lt: Strictly Less Than

**$lt** stands for *less than*. It selects values **less than** the reference value and excludes equality.

~~~javascript
db.comparisonProducts.find({
  price: {
    $lt: NumberDecimal("12.00")
  }
})
~~~

Result: **P02 (5.00)** and **P07 (9.00)**. P06 has a price of exactly 12.00 and is excluded.

Example finding products with stock below 3:

~~~javascript
db.comparisonProducts.find({
  stock: { $lt: 3 }
})
~~~

Result: **P01 (0), P05 (2), P07 (1)**.

Note: a condition **stock < 3** can also match negative stock if negative numbers exist in the data. If you only want values from 0 to 2, combine it with $gte: 0.

## 8. $lte: Less Than or Equal To

**$lte** stands for *less than or equal*. It includes the boundary value as well.

~~~javascript
db.comparisonProducts.find({
  price: {
    $lte: NumberDecimal("12.00")
  }
})
~~~

Result: **P02 (5.00), P06 (12.00), and P07 (9.00)**.

Comparison with $lt:

| Operator | Mathematical condition | Is price 12.00 selected? |
|---|---|---|
| $lt: 12 | price < 12 | No |
| $lte: 12 | price ≤ 12 | Yes |

Example products with stock at most 2:

~~~javascript
db.comparisonProducts.find({
  stock: { $lte: 2 }
})
~~~

Result: **P01, P05, P07**.

Phrases such as **"at most"**, **"not exceeding"**, and **"up to ... inclusive"** usually map to $lte.

## 9. Result Summary of the Six Operators

Applied to the sample dataset:

| Filter | Meaning | Expected _id |
|---|---|---|
| { stock: { $eq: 0 } } | Stock equals 0 | P01 |
| { category: { $ne: "electronics" } } | Not in electronics | P01, P02, P05, P06, P07 |
| { price: { $gt: NumberDecimal("25") } } | Price over 25 | P04, P05 |
| { price: { $gte: NumberDecimal("25") } } | Price 25 or more | P03, P04, P05 |
| { price: { $lt: NumberDecimal("12") } } | Price under 12 | P02, P07 |
| { price: { $lte: NumberDecimal("12") } } | Price at most 12 | P02, P06, P07 |

You can visualize this on a number line:

~~~text
                       Threshold = 25
      5        12      20      25      30          55
      |--------|-------|-------|-------|-----------|
                                ^
                    $gt 25:     to the right only
                    $gte 25:    25 and to the right
                    $lt 25:     to the left only
                    $lte 25:    25 and to the left
                    $eq 25:     exactly 25
                    $ne 25:     all values other than 25
~~~

The diagram illustrates semantics on a number line. For BSON, values must be compared within data-type context and MongoDB rules; a single numeric chart cannot be used to infer all comparisons across String, ObjectId, Date, and Null.

## 10. Combining Multiple Operators on the Same Field

A very common requirement is filtering values **within a range**. Place multiple operators inside the same field's object:

~~~javascript
db.comparisonProducts.find({
  price: {
    $gte: NumberDecimal("12.00"),
    $lt: NumberDecimal("30.00")
  }
})
~~~

This condition means:

\[
12 \leq price < 30
\]

Result: **P01 (20.00), P03 (25.00), P06 (12.00)**. P05 has price 30.00 and falls outside the range.

### 10.1. Basic Interval Types

| Interval | Syntax | Endpoints |
|---|---|---|
| (a, b) | { $gt: a, $lt: b } | Excludes a and b |
| [a, b] | { $gte: a, $lte: b } | Includes both a and b |
| [a, b) | { $gte: a, $lt: b } | Includes a, excludes b |
| (a, b] | { $gt: a, $lte: b } | Excludes a, includes b |

For time-based queries, the **half-open interval [start, end)** is especially useful. It lets you chain consecutive intervals without double-counting boundary instants:

~~~text
Day 1: [00:00 Day 1, 00:00 Day 2)
Day 2: [00:00 Day 2, 00:00 Day 3)
~~~

### 10.2. Mistake of Repeating the Field Key

Do not write:

~~~javascript
// Wrong: the same JavaScript object declares price twice.
{
  price: { $gte: 12 },
  price: { $lt: 30 }
}
~~~

In a JavaScript object, declaring a duplicate property name causes the later value to overwrite the earlier one. Only one half of the condition remains, causing silent bugs.

Write it properly by **placing both operators inside the same object**:

~~~javascript
{
  price: {
    $gte: NumberDecimal("12.00"),
    $lt: NumberDecimal("30.00")
  }
}
~~~

### 10.3. Using $ne with Range Operators

For example, select stock greater than 0 but not equal to 2:

~~~javascript
db.comparisonProducts.find({
  stock: {
    $gt: 0,
    $ne: 2
  }
})
~~~

Result: **P02, P03, P04, P06, P07**. P01 is excluded for being 0, and P05 is excluded for being 2.

Conditions on **a scalar value** must all be satisfied together. For array fields, applying multiple operators has additional element-matching rules, explained in the array section.

## 11. Combining Conditions Across Multiple Fields

In MongoDB, multiple conditions on different fields within the same filter are combined with **AND** logic by default.

Example:

~~~javascript
db.comparisonProducts.find({
  category: "electronics",
  price: {
    $gte: NumberDecimal("25.00"),
    $lte: NumberDecimal("55.00")
  },
  stock: { $gt: 0 }
})
~~~

Meaning:

1. category equals "electronics";
2. price lies in the range [25.00, 55.00];
3. stock is greater than 0.

Result: **P03 and P04**.

### 11.1. Explicit AND with $and

You can use **$and** when building complex conditions or combining expressions that are awkward to write inline:

~~~javascript
db.comparisonProducts.find({
  $and: [
    { category: "electronics" },
    { price: { $gte: NumberDecimal("25.00") } },
    { stock: { $gt: 0 } }
  ]
})
~~~

On the sample dataset, the result is still **P03 and P04**. In simple cases, placing fields side by side is usually easier to read than using $and.

### 11.2. OR with $or

Suppose you want products that are **out of stock** or **priced at 50 or above**:

~~~javascript
db.comparisonProducts.find({
  $or: [
    { stock: { $eq: 0 } },
    { price: { $gte: NumberDecimal("50.00") } }
  ]
})
~~~

Result: **P01 (stock = 0)** and **P04 (price = 55.00)**.

Do not write multiple conditions on different fields expecting MongoDB to treat them as OR; by default they are combined with AND.

### 11.3. Comparison with $in and $nin

When comparing against **multiple discrete values**, the $in and $nin operators are usually a better fit:

~~~javascript
db.comparisonProducts.find({
  category: { $in: ["electronics", "home"] }
})
~~~

Result: **P03, P04, P05**.

$eq checks one value at a time; $in fits an allowed set of values. $ne means "not equal to one value", while $nin means "not in a list". Like $ne, $nin has specific behavior for missing fields, so define the semantics clearly when designing filters.

## 12. Null and Missing Fields: Special Handling of $eq and $ne

In a MongoDB document, the following three states are distinct:

~~~javascript
{ rating: 4.5 }
{ rating: null }
{ /* rating field omitted */ }
~~~

**null** is a stored BSON value. A missing field means the key does not exist in the document.

### 12.1. $eq: null Matches Both Null and Missing

Query:

~~~javascript
db.comparisonProducts.find({
  rating: { $eq: null }
})
~~~

Result: **P06 and P07**.

Here:

- **P06** has rating: null.
- **P07** does not contain the rating field.

MongoDB has a special rule: **an equality condition with null** matches both fields whose value is null and fields that do not exist. The shorthand syntax:

~~~javascript
db.comparisonProducts.find({ rating: null })
~~~

also carries this same meaning.

### 12.2. $ne: null Selects Fields That Exist and Are Not Null

Query:

~~~javascript
db.comparisonProducts.find({
  rating: { $ne: null }
})
~~~

Result: **P01, P02, P03, P04, P05**.

Remember this alongside the general $ne rule: **$ne: null** has special semantics that select documents where the field exists and its value is not null; it does not select P06 or P07.

### 12.3. Combining with $exists for Clear Distinction

| Goal | Filter | Sample result |
|---|---|---|
| Rating is null **or field is missing** | { rating: null } | P06, P07 |
| Rating is not null and field must exist | { rating: { $ne: null } } | P01–P05 |
| Has rating field, including null | { rating: { $exists: true } } | P01–P06 |
| Does not have rating field | { rating: { $exists: false } } | P07 |
| Rating is not 4.8, including missing field | { rating: { $ne: 4.8 } } | P01, P03–P07 |
| Rating is not 4.8 **and field exists** | { rating: { $ne: 4.8, $exists: true } } | P01, P03–P06 |

In production code, write conditions according to the exact business question: **"has no rating"**, **"rating not yet entered"**, and **"rating exists and differs from 4.8"** can be three distinct requirements.

### 12.4. Do Not Infer Null Ordering in Range Filters

Do not use $gt/$gte/$lt/$lte with a null threshold as a vague way to express "has data". Range comparisons are governed by **type bracketing** rules and BSON-specific behavior. To check that a field has a non-null value, use **$ne: null**; to check only that the field is present, use **$exists: true**.

## 13. BSON Type Comparisons: Do Not Confuse Strings with Numbers

MongoDB stores values in BSON types such as String, Int32, Int64, Double, Decimal128, Date, ObjectId, Boolean, Array, and Object. Query comparisons generally follow **type bracketing**: comparisons are evaluated only within the matching type group, with specific defined exceptions, notably for the numeric type group.

Sample data:

~~~javascript
db.typeExamples.insertMany([
  { _id: "T01", amount: NumberInt(20) },
  { _id: "T02", amount: NumberLong("20") },
  { _id: "T03", amount: NumberDecimal("20.00") },
  { _id: "T04", amount: NumberDouble("20.0") },
  { _id: "T05", amount: "20" },
  { _id: "T06", amount: "100" }
])
~~~

Numeric query:

~~~javascript
db.typeExamples.find({
  amount: { $gte: 20 }
})
~~~

The numeric values in T01–T04 belong to the numeric comparison group; T05 and T06 are **Strings**, so they are not treated as the numbers 20 or 100 when evaluating a numeric filter.

### 13.1. Conversely, Strings Compare as Strings

~~~javascript
db.typeExamples.find({
  amount: { $gt: "20" }
})
~~~

This condition compares string values according to the active collation rules rather than casting strings to numbers. **"100"** can sort before **"20"** under default lexicographical comparison, even though 100 is numerically greater than 20.

If a field must be numeric, store it consistently as a BSON number and configure proper schema validation instead of expecting query operators to fix mistyped data.

### 13.2. Different BSON Numeric Types

MongoDB has numeric types such as:

| BSON type | Characteristics | mongosh example |
|---|---|---|
| Int32 | 32-bit signed integer | NumberInt(20) |
| Int64 | 64-bit signed integer | NumberLong("20") |
| Double | Binary floating-point number | NumberDouble("20.0") |
| Decimal128 | Decimal number with Decimal128 precision | NumberDecimal("20.00") |

Numeric types can be compared by **numeric value** under MongoDB rules, but converting through JavaScript Number or another application layer still risks precision loss for large integers and decimal values. For currency, use consistently constructed types and reference values, such as **NumberDecimal("25.00")**.

### 13.3. Inspecting Actual Data Types

To inspect BSON types in a collection:

~~~javascript
db.typeExamples.aggregate([
  {
    $project: {
      amount: 1,
      amountType: { $type: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

You can see types such as **int**, **long**, **decimal**, **double**, and **string**. This is a reliable way to investigate why values that all look like "20" in the UI produce different query results.

## 14. String Comparison and Collation

String comparison is not just "equal" or "not equal": with **$gt, $gte, $lt, $lte**, MongoDB also needs to determine ordering between strings.

Under simple collation, ordering is based on the binary representation of strings. When language rules, case sensitivity/insensitivity, diacritics, or locale sorting are needed, MongoDB supports **collation**.

Example finding the name "pen" case-insensitively:

~~~javascript
db.comparisonProducts.find({
  name: { $eq: "pen" }
}).collation({
  locale: "en",
  strength: 2
})
~~~

With the sample data, the query matches **P02 (Pen)** thanks to English collation at a case-insensitive comparison strength.

If no collation is specified and the collection uses simple collation, the string **"Pen"** differs from **"pen"**.

**Note when creating indexes:** Indexes have their own collation. A query using a different collation from the index may not be able to use that index as expected for string comparison or sorting. Collation must therefore be planned together with the indexing strategy and application search behavior.

Do not use string ranges such as **name >= "A" and name < "Z"** assuming they match every string starting with A through Z in all languages. Diacritics, casing, Unicode, and collation can cause comparison rules to behave differently from expectations.

## 15. Comparing on Arrays: Easily Confused Element Rules

A MongoDB field can be an array. With regular query conditions, MongoDB can match an array based on **one or more elements of the array**, depending on the expression.

### 15.1. $eq on an Array Element

In the sample data, P03, P04, and P05 all have the tag **"desk"**:

~~~javascript
db.comparisonProducts.find({
  tags: { $eq: "desk" }
})
~~~

Result: **P03, P04, P05**.

This does not require the entire array to equal the string "desk"; it only requires the array to contain a matching element. The shorthand:

~~~javascript
db.comparisonProducts.find({ tags: "desk" })
~~~

is also used to check whether the array contains the element "desk".

### 15.2. Whole-Array Equality vs. Element Containment

~~~javascript
db.comparisonProducts.find({
  tags: { $eq: ["desk", "usb"] }
})
~~~

Result: **P03 and P04**, because they store that exact array in the declared order. This is a different requirement from finding a single element.

For whole-array comparison, element order matters. The array **["usb", "desk"]** is not equal under whole-array equality to **["desk", "usb"]**.

### 15.3. $ne with Arrays

~~~javascript
db.comparisonProducts.find({
  tags: { $ne: "desk" }
})
~~~

This condition selects documents that do not have an element value matching "desk", and may also select documents missing tags. On the sample dataset, the result is **P01, P02, P06, P07**.

If you only want documents that have tags without containing "desk", combine it with **$exists: true** or an array type condition if data-type control is needed.

### 15.4. Range Conditions on an Array Can Be Satisfied by Different Elements

Create test data:

~~~javascript
db.arrayExamples.insertMany([
  { _id: "A", scores: [40, 90] },
  { _id: "B", scores: [60, 70] },
  { _id: "C", scores: [20, 30] },
  { _id: "D", scores: [] },
  { _id: "E", scores: [85, 95] }
])
~~~

Query:

~~~javascript
db.arrayExamples.find({
  scores: {
    $gte: 80,
    $lt: 90
  }
})
~~~

The result can include **A and E**:

- **A** has element 90 satisfying **>= 80**, and element 40 satisfying **< 90**. The two conditions are satisfied by **two different elements**.
- **E** has element 85 satisfying both conditions.

This is a critical point: when combining multiple conditions on an array, MongoDB does not necessarily require **the same element** to satisfy every condition.

If the goal is **at least one element lies in [80, 90)**, use **$elemMatch**:

~~~javascript
db.arrayExamples.find({
  scores: {
    $elemMatch: {
      $gte: 80,
      $lt: 90
    }
  }
})
~~~

Result: **E**. A is not selected because it has no **single element** that is both >= 80 and < 90.

**Remember:** Range conditions on a **scalar** inspect the same single value. Range conditions on an **array** follow element-matching rules; use $elemMatch when constraints must apply together to a single element.

### 15.5. Arrays Containing Documents

Example:

~~~javascript
{
  orderId: "O-001",
  items: [
    { sku: "A", quantity: 1, price: 10 },
    { sku: "B", quantity: 5, price: 50 }
  ]
}
~~~

To find orders with **one item** that has both quantity >= 3 and price < 60:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      quantity: { $gte: 3 },
      price: { $lt: 60 }
    }
  }
})
~~~

Do not write separate dot-notation conditions assuming they always inspect the same item:

~~~javascript
// These two conditions can be satisfied by two different items.
{
  "items.quantity": { $gte: 3 },
  "items.price": { $lt: 60 }
}
~~~

For arrays of objects, **$elemMatch** is the explicit way to require conditions to hold simultaneously on a single element.

## 16. Comparing Nested Fields

MongoDB supports dot-notation field paths, such as **dimensions.width** or **address.zipCode**.

Suppose a document is:

~~~javascript
{
  _id: "P100",
  name: "Storage Box",
  dimensions: {
    width: 30,
    height: 20,
    depth: 15
  }
}
~~~

Query products with width at least 25:

~~~javascript
db.products.find({
  "dimensions.width": { $gte: 25 }
})
~~~

This query inspects the **width** field inside **dimensions**.

### 16.1. Matching an Entire Embedded Document

If comparing the entire nested document:

~~~javascript
db.products.find({
  dimensions: {
    width: 30,
    height: 20,
    depth: 15
  }
})
~~~

MongoDB may require **the embedded document to match the exact contents and field order** when comparing an entire object for equality. If you only need a condition on a child field, use dot notation instead of comparing the whole object.

Example:

~~~javascript
db.products.find({
  "dimensions.width": { $eq: 30 }
})
~~~

This approach depends far less on additional child fields and object key order.

## 17. Time Ranges with $gte and $lt

Date-range queries are an important application of comparison operators. Store timestamps as **BSON Date** and compare against real Date boundaries.

Suppose you want all products created during the three UTC days **November 11, 12, and 13, 2026**:

~~~javascript
db.comparisonProducts.find({
  createdAt: {
    $gte: ISODate("2026-11-11T00:00:00Z"),
    $lt: ISODate("2026-11-14T00:00:00Z")
  }
}).sort({ createdAt: 1 })
~~~

Result: **P02, P03, P04**.

### 17.1. Why Use [start, end)?

An error-prone approach is using an end-of-day timestamp such as **23:59:59**:

~~~javascript
{
  createdAt: {
    $gte: ISODate("2026-11-11T00:00:00Z"),
    $lte: ISODate("2026-11-13T23:59:59Z")
  }
}
~~~

This can miss records created during the final second's milliseconds, such as **23:59:59.500Z**.

To avoid manually determining the "last millisecond of the day", use the start of the next day with **$lt**:

~~~javascript
{
  createdAt: {
    $gte: ISODate("2026-11-11T00:00:00Z"),
    $lt: ISODate("2026-11-14T00:00:00Z")
  }
}
~~~

This is a **start-inclusive, end-exclusive** interval, making it easy to chain consecutive ranges and avoid boundary double-counting.

### 17.2. Time Zones Determine Comparison Boundaries

If a user asks for "November 14 in Vietnam time", the local day begins at **2026-11-14T00:00:00+07:00**, which equals **2026-11-13T17:00:00Z**.

Example:

~~~javascript
db.comparisonProducts.find({
  createdAt: {
    $gte: ISODate("2026-11-13T17:00:00Z"),
    $lt: ISODate("2026-11-14T17:00:00Z")
  }
})
~~~

The range above represents November 14, 2026 in UTC+07:00. In systems with time zones and daylight saving transitions, compute boundaries using a standard time-zone library rather than always hardcoding +24 hours.

**BSON Date stores an instant in time**, not a time-zone name string. The time zone is used to interpret business dates and construct the two Date boundaries passed into the query.

### 17.3. Timestamp Strings Do Not Equal Dates

A document with:

~~~javascript
{ createdAt: "2026-11-14T08:00:00Z" }
~~~

is not the same as a document with:

~~~javascript
{ createdAt: ISODate("2026-11-14T08:00:00Z") }
~~~

Therefore, a Date filter will skip records stored with the wrong String type. This is one reason to use schema validation to ensure createdAt is a BSON Date upon write.

## 18. Using Comparison Operators in Update and Delete

These six operators are also used as **document selection criteria** before updating or deleting.

For example, marking products with stock of at most 2 as needing restock:

~~~javascript
db.comparisonProducts.updateMany(
  { stock: { $lte: 2 } },
  { $set: { needsRestock: true } }
)
~~~

On the sample dataset, the filter selects **P01, P05, P07**. The **$lte** part only selects the records; the **$set** part actually modifies the data.

An example expiring stale pending jobs can be written as:

~~~javascript
db.jobs.updateMany(
  {
    status: "PENDING",
    createdAt: { $lt: ISODate("2026-11-01T00:00:00Z") }
  },
  { $set: { status: "EXPIRED" } }
)
~~~

The status condition is needed to avoid modifying jobs that already completed before the cutoff.

### 18.1. Read-Check Before Deleting

A delete filter also uses the same comparison operators:

~~~javascript
// Check scope before deleting in an environment with real data.
db.sessionCache.find({
  expiresAt: { $lt: new Date() }
})
~~~

Only when business logic truly requires deletion and the condition has been verified should you run:

~~~javascript
db.sessionCache.deleteMany({
  expiresAt: { $lt: new Date() }
})
~~~

In systems with a TTL index, expiration may be processed asynchronously by MongoDB depending on configuration. Do not use $lt as a guarantee that every session will be deleted at the exact millisecond of expiration; if sessions affect security, the application must still check expiresAt during authentication.

### 18.2. Conditional Updates Help Prevent Invalid State Transitions

A conditional update helps prevent unexpected state overwrites:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-001",
    status: { $eq: "NEW" },
    total: { $gte: NumberDecimal("0") }
  },
  { $set: { status: "PAID" } }
)
~~~

The filter selects the order only when its status and total currently satisfy the rules. However, complex payment rules, user permissions, and cross-document consistency also require proper domain design, transactions, or dedicated mechanisms when needed.

## 19. MongoDB Java Driver: Building Filters Safely

When using the Java MongoDB Sync Driver, the **com.mongodb.client.model.Filters** package provides builder methods for these operators, avoiding manual BSON object construction from strings everywhere.

Assume the application has the appropriate **mongodb-driver-sync** dependency and the **MONGODB_URI** environment variable configured.

### 19.1. Building a Price Range

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.Decimal128;

import java.math.BigDecimal;

public class ComparePriceDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Decimal128 min = new Decimal128(new BigDecimal("12.00"));
        Decimal128 max = new Decimal128(new BigDecimal("30.00"));

        Bson filter = Filters.and(
                Filters.gte("price", min),
                Filters.lt("price", max)
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> products = client
                    .getDatabase("comparison_lab")
                    .getCollection("comparisonProducts");

            try (MongoCursor<Document> cursor = products
                    .find(filter)
                    .projection(Projections.include("_id", "name", "price"))
                    .sort(Sorts.ascending("_id"))
                    .iterator()) {

                while (cursor.hasNext()) {
                    System.out.println(cursor.next().toJson());
                }
            }
        }
    }
}
~~~

Equivalent Java filter condition:

~~~javascript
{
  price: {
    $gte: NumberDecimal("12.00"),
    $lt: NumberDecimal("30.00")
  }
}
~~~

On the sample dataset, the result is **P01, P03, P06**. The **Decimal128** class constructs comparison values matching how the application stores prices.

### 19.2. Mapping All Six Operators to Filters

~~~java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.ne;
import static com.mongodb.client.model.Filters.gt;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Filters.lt;
import static com.mongodb.client.model.Filters.lte;

// Equal
var equalsZero = eq("stock", 0);

// Not equal
var notElectronics = ne("category", "electronics");

// Greater than
var greaterThanZero = gt("stock", 0);

// Greater than or equal
var atLeastTen = gte("stock", 10);

// Less than
var belowThree = lt("stock", 3);

// Less than or equal
var atMostTwo = lte("stock", 2);
~~~

Each variable above represents a **BSON filter**; none of them executes a query on its own until passed into an API such as find(), countDocuments(), updateOne(), or deleteMany().

### 19.3. Be Careful with Null in Java

A filter such as **Filters.eq("rating", null)** follows MongoDB's null semantics: it matches fields that are null or missing. **Filters.ne("rating", null)** selects fields that exist and are not null.

If Java logic wants to check that a field **exists regardless of value**, use **Filters.exists("rating", true)**. Do not use ne with an arbitrary value and assume all returned documents contain the field.

## 20. Spring Data MongoDB: Criteria and Query

With Spring Data MongoDB, the **Criteria** class provides corresponding methods:

| MongoDB operator | Spring Data Criteria |
|---|---|
| $eq | is(value) |
| $ne | ne(value) |
| $gt | gt(value) |
| $gte | gte(value) |
| $lt | lt(value) |
| $lte | lte(value) |

Example filtering stock in the range [2, 12]:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import java.util.List;

public class ProductQueryService {
    private final MongoTemplate mongoTemplate;

    public ProductQueryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> findMediumStock() {
        Query query = new Query(
                Criteria.where("stock").gte(2).lte(12)
        );

        return mongoTemplate.find(
                query,
                Document.class,
                "comparisonProducts"
        );
    }
}
~~~

Equivalent filter:

~~~javascript
{ stock: { $gte: 2, $lte: 12 } }
~~~

Result on the sample dataset: **P03, P04, P05, P06**.

Example checking not null:

~~~java
Query ratedOnly = new Query(
        Criteria.where("rating").ne(null)
);
~~~

The query above selects documents where rating exists and is not null. When designing repositories, use Java types and mappings consistent with the field's BSON type; a syntactically valid comparison can still fail to return expected results if legacy data was stored with the wrong type.

## 21. Indexes and Comparison Query Performance

MongoDB can use **indexes** to limit the number of documents read when evaluating filters. Equality and range comparison operators are typically key building blocks when designing indexes.

For example, if an application frequently queries products by category and then filters by price:

~~~javascript
db.comparisonProducts.createIndex({
  category: 1,
  price: 1
})
~~~

Query:

~~~javascript
db.comparisonProducts.find({
  category: "electronics",
  price: {
    $gte: NumberDecimal("20.00"),
    $lt: NumberDecimal("60.00")
  }
})
~~~

The compound index **category, price** can support finding the exact category and then scanning a price range. Even so, which index MongoDB actually chooses depends on statistics, collection size, filter selectivity, and the query planner.

### 21.1. Equality First, Range Second

For many queries, a compound index is designed around access patterns such as:

~~~text
category = "electronics"      -> equality
price >= 20 and price < 60    -> range
~~~

Depending on the workload, the index:

~~~javascript
{ category: 1, price: 1 }
~~~

may be appropriate. However, do not apply one index order mechanically to every case: sorts, cardinality, data distribution, and additional conditions all affect efficiency.

### 21.2. Inspecting the Query Plan with explain()

~~~javascript
db.comparisonProducts
  .find({
    category: "electronics",
    price: {
      $gte: NumberDecimal("20.00"),
      $lt: NumberDecimal("60.00")
    }
  })
  .explain("executionStats")
~~~

Pay attention to these metrics:

- **winningPlan:** the execution strategy chosen.
- **totalKeysExamined:** number of index entries scanned.
- **totalDocsExamined:** number of documents inspected.
- **nReturned:** number of documents returned.

On a sample dataset with only seven documents, a collection scan may be reasonable. Do not conclude an index is useless in production just because MongoDB does not pick it when test data is tiny.

### 21.3. $ne Is Usually Less Selective Than $eq

For example, if 99% of products do **not** have category equal to "obsolete", the filter:

~~~javascript
{ category: { $ne: "obsolete" } }
~~~

will select nearly the entire collection. An index may not significantly reduce read work.

Conversely:

~~~javascript
{ category: { $eq: "electronics" } }
~~~

is likely more selective if electronics accounts for a small fraction. Measure with **explain()** rather than guessing from the operator name alone.

### 21.4. Indexes Do Not Fix Wrong Data Types

If some documents store **price: "25.00"** as a String and others store **price: NumberDecimal("25.00")**, the index still stores values in their actual BSON types. A numeric threshold filter will not cast strings into numbers.

Schema validation, application mapping rules, and migrating legacy data are the way to resolve type inconsistencies. Adding an index on mistyped data does not unify them into a single value domain.

## 22. Common Pitfalls When Using the Six Operators

| Symptom | Cause | Resolution |
|---|---|---|
| Price of exactly 25 does not appear | Used $gt: 25 instead of $gte: 25 | Confirm whether the boundary is inclusive |
| Price of exactly 30 still appears when expecting under 30 | Used $lte: 30 instead of $lt: 30 | Use an exclusive upper bound |
| Range filter only applies the last condition | Repeated field key in the same object | Merge $gte/$lt into one object for the field |
| $ne also returns documents missing the field | This is $ne semantics for ordinary values | Combine with $exists: true when the field must be present |
| Null equality returns documents missing the field | $eq: null has special rules | Use $exists to distinguish absent fields |
| Query price > 20 misses "25.00" | price stored as String, filter uses Number | Fix schema and migrate data to BSON numbers |
| _id query finds nothing despite matching hex string | _id is ObjectId but filter passes String | Construct an ObjectId matching the schema |
| Date filter misses end-of-day records | Used $lte 23:59:59 and missed milliseconds | Use [start, nextDayStart) |
| Array [40, 90] matches >=80 and <90 | Two conditions can match two different elements | Use $elemMatch to enforce the same element |
| Name comparison fails on case differences | Default collation does not match expectations | Check collection/query/index collation |
| $ne runs slowly on large data | Low-selectivity condition matching most documents | Inspect plan with explain and adjust filter/index |
| find() result order changes | No explicit sort | Sort by business key and tie-breaker key if needed |

### 22.1. Input Value vs. Operator Expression

In JavaScript code, for example:

~~~javascript
const minPrice = NumberDecimal("20.00");

db.comparisonProducts.find({
  price: { $gte: minPrice }
})
~~~

is a valid filter because **minPrice** is a variable holding a BSON Decimal128 value. By contrast:

~~~javascript
db.comparisonProducts.find({
  price: { $gte: "minPrice" }
})
~~~

compares against the literal string **"minPrice"** rather than reading the variable. This is a common mistake when building dynamic filters.

### 22.2. Both Field Name and Data Type Matter

The following two filters access different fields:

~~~javascript
{ stock: { $gt: 0 } }
{ "inventory.stock": { $gt: 0 } }
~~~

The second query matches only when the document has an **inventory** object with a child field **stock**. MongoDB does not search everywhere in a document for a field of the same name.

### 22.3. Filter Operators vs. Aggregation Expression Operators

In a standard query:

~~~javascript
db.items.find({
  stock: { $gt: 10 }
})
~~~

**$gt** takes a reference value of 10 in the condition for the stock field.

If you need to compare **two fields within the same document**, you typically use **$expr** with expression operator syntax:

~~~javascript
db.items.find({
  $expr: {
    $gt: ["$stock", "$reorderLevel"]
  }
})
~~~

Here the two arguments are field-reference expressions placed inside an array. Both use the name $gt, but **the syntax and context differ**. Never drop $expr syntax directly into an ordinary field filter.

## 23. Practice Exercises

Use the **comparisonProducts** collection created at the beginning, run each filter, and verify the actual _id values.

### Exercise 1. Choosing the Exact Operator

Write a filter for each requirement:

1. Stock equals 0.
2. Price not equal to 20.00.
3. Price greater than 25.00.
4. Price at least 25.00.
5. Stock below 3.
6. Stock at most 3.

**Reference answers:**

~~~javascript
// 1. Equal to 0
{ stock: { $eq: 0 } }

// 2. Not equal to 20.00
{ price: { $ne: NumberDecimal("20.00") } }

// 3. Above 25.00
{ price: { $gt: NumberDecimal("25.00") } }

// 4. 25.00 or more
{ price: { $gte: NumberDecimal("25.00") } }

// 5. Below 3
{ stock: { $lt: 3 } }

// 6. At most 3
{ stock: { $lte: 3 } }
~~~

### Exercise 2. Filtering Within a Price Range

Requirement: products with **price from 10.00 to 30.00, inclusive on both ends**.

~~~javascript
db.comparisonProducts.find({
  price: {
    $gte: NumberDecimal("10.00"),
    $lte: NumberDecimal("30.00")
  }
}).sort({ _id: 1 })
~~~

Result: **P01, P03, P05, P06**.

If you replace **$lte: 30.00** with **$lt: 30.00**, P05 is excluded. Explain why a small change in the operator alters the result set.

### Exercise 3. Finding Missing Ratings

Write queries for three cases:

1. Rating is null or the field is missing.
2. Rating exists and is not null.
3. Rating exists and is not 4.8 (null allowed).

**Reference answers:**

~~~javascript
// 1. Null or missing field
{ rating: { $eq: null } }

// 2. Field exists and is not null
{ rating: { $ne: null } }

// 3. Field exists and is not 4.8, may be null
{ rating: { $ne: 4.8, $exists: true } }
~~~

The sample results are **P06/P07**, **P01–P05**, and **P01/P03/P04/P05/P06**, respectively.

### Exercise 4. Time Comparison Using Half-Open Intervals

Requirement: documents created **from the start of 2026-11-12 to before the start of 2026-11-15 in UTC**.

~~~javascript
db.comparisonProducts.find({
  createdAt: {
    $gte: ISODate("2026-11-12T00:00:00Z"),
    $lt: ISODate("2026-11-15T00:00:00Z")
  }
})
~~~

Result: **P03, P04, P05**.

Explain why you do not need to manually compute **23:59:59.999** on November 14.

### Exercise 5. Arrays and $elemMatch

Given the arrayExamples collection:

~~~javascript
{ _id: "A", scores: [40, 90] }
{ _id: "E", scores: [85, 95] }
~~~

Compare two filters:

~~~javascript
// Filter A
{ scores: { $gte: 80, $lt: 90 } }

// Filter B
{ scores: { $elemMatch: { $gte: 80, $lt: 90 } } }
~~~

Why does filter A match **A and E**, while filter B matches only **E**? Answer by naming the **specific elements** that satisfy each condition.

### Exercise 6. Combining Multiple Conditions

Requirement: products in **stationery**, **price under 15.00**, **positive stock**.

~~~javascript
db.comparisonProducts.find({
  category: { $eq: "stationery" },
  price: { $lt: NumberDecimal("15.00") },
  stock: { $gt: 0 }
}).sort({ _id: 1 })
~~~

Result: **P02, P06, P07**.

Explain how MongoDB combines the three conditions with AND and why P01 is not selected.

### Exercise 7. Interpreting a Query Plan

Create an index:

~~~javascript
db.comparisonProducts.createIndex({
  category: 1,
  price: 1
})
~~~

Then run:

~~~javascript
db.comparisonProducts.find({
  category: "stationery",
  price: { $gte: NumberDecimal("10.00") }
}).explain("executionStats")
~~~

Identify **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, and **nReturned**. Explain why having an index does not guarantee the query planner will use it on a collection with only a few documents, and why testing should use data with a realistic distribution.

## 24. Choosing Operators from Business Requirements

| Phrasing | Appropriate operator |
|---|---|
| Equal to / exact value | $eq or field: value syntax |
| Different / not equal to a value | $ne |
| Greater than / above / after a threshold | $gt |
| Minimum / at least / from a threshold upward | $gte |
| Less than / below / before a threshold | $lt |
| Maximum / not exceeding / up to an inclusive threshold | $lte |
| Within a range including both ends | $gte combined with $lte |
| Within a range excluding both ends | $gt combined with $lt |
| Within a range from start to before end | $gte combined with $lt |
| Multiple discrete allowed values | Consider $in |
| One array element must satisfy multiple constraints | $elemMatch combined with comparison operators |
| Check if a field exists | $exists |

To use the six comparison operators properly in MongoDB, always confirm **whether the boundary value is included**, **whether the field is a scalar or an array**, **whether the field can be null or missing**, and **what the actual BSON type is**. Then, for frequent queries on large datasets, design indexes around real filters and inspect them with explain().

Once these factors are clearly defined, simple conditions such as **price >= 20 and price < 50** become readable, accurate MongoDB filters that scale safely in Java applications.
