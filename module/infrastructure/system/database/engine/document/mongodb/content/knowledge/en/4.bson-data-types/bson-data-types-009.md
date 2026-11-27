# BSON Type Comparison Order and Its Impact on Queries and Sorting

MongoDB stores values in **BSON types** (Binary JSON), such as `null`, integers, floating-point numbers, `Decimal128`, strings, embedded documents, arrays, `ObjectId`, Booleans, dates, and `Timestamp`. When a collection contains multiple types in the same field, the results of `sort()`, comparison operators, and indexes can differ from what someone accustomed to JavaScript or SQL expects.

The key is distinguishing **three contexts**:

1. **Global BSON sort order**: used when MongoDB sorts documents or when aggregation expressions compare values of different BSON types.
2. **Type bracketing in query predicates**: filter operators such as `$gt`, `$gte`, `$lt`, and `$lte` typically compare only values belonging to a type group compatible with the operand, rather than applying the global BSON order across all types.
3. **Specific rules for strings, arrays, and objects**: collation, array element selection for sorting, and embedded-document field order directly affect results.

This lesson uses `mongosh` syntax and covers the rules, examples, index interpretation, and common data design mistakes.

## 1. Why Does BSON Type Order Matter?

Suppose the `products` collection has an inconsistent `price` field:

```javascript
{ _id: "p1", price: NumberInt(90) }
{ _id: "p2", price: NumberDecimal("120.50") }
{ _id: "p3", price: "100" }
{ _id: "p4", price: null }
{ _id: "p5" } // missing price field
```

If you run:

```javascript
db.products.find().sort({ price: 1, _id: 1 });
```

MongoDB does not automatically convert `"100"` into the number `100`. Strings and numbers belong to **different BSON groups**. In an ascending sort, `null`/missing fields come before numbers, and strings come after numbers. Thus, `"100"` is not placed between `90` and `120.50` as it would be in numeric comparison.

If instead you run:

```javascript
db.products.find({ price: { $gt: 100 } });
```

MongoDB applies type bracketing, so filtering with a numeric operand does not simply include all strings that BSON sorts after numbers. The match covers numbers greater than `100`; `"100"` is not a number for this predicate to compare. **Sorting and filtering can follow different rules**, even on the exact same field.

## 2. Comparison Order Across BSON Types

When comparing **two values of different types** for sorting, MongoDB uses the following order (from lowest to highest):

| Order | BSON Type / Group | Typical Value |
|---:|---|---|
| 1 | `MinKey` | Lowest sentinel value in BSON order |
| 2 | `Null` | `null` |
| 3 | **Numbers** | `Int32`, `Int64/Long`, `Double`, `Decimal128` |
| 4 | `Symbol`, `String` | `"MongoDB"`, `"42"` |
| 5 | `Object` / embedded document | `{ city: "Hue" }` |
| 6 | `Array` | `[1, 2]` |
| 7 | `BinData` | Binary data |
| 8 | `ObjectId` | `ObjectId("...")` |
| 9 | `Boolean` | `false`, `true` |
| 10 | `Date` | `ISODate("2026-01-01T00:00:00Z")` |
| 11 | `Timestamp` | BSON timestamp with seconds and increment |
| 12 | `Regular Expression` | `/mongodb/i` |
| 13 | `JavaScript Code` | BSON code (specialized/legacy type) |
| 14 | `JavaScript Code with Scope` | BSON code with scope (legacy) |
| 15 | `MaxKey` | Highest sentinel value in BSON order |

This is the BSON order **from lowest to highest**, not a recommendation table for choosing schema types. Types such as `Symbol`, JavaScript code, and code-with-scope are not standard storage choices for new applications; you still need to know their positions when reading legacy or mixed-type data.

### 2.1. Integers, Doubles, and Decimal128 Share One Comparison Group

MongoDB treats numeric types as equivalent in **comparison group**. Two numbers with different representations are still evaluated by mathematical value:

```javascript
NumberInt(7)
NumberLong("7")
7.0                     // Double in standard mongosh syntax
NumberDecimal("7.0")
```

These values belong to the Numbers group and are not sorted into four separate blocks ordered `Int32` → `Int64` → `Double` → `Decimal128`.

This **does not mean all numeric types have identical precision**. `Double` is binary floating-point, whereas `Decimal128` represents decimals with IEEE 754 decimal128 precision. A large integer can also lose precision if passed through a JavaScript `Number`. For currency or data requiring exact decimal values, choose one consistent type, avoid passing through `Double`, and enforce types at the driver layer.

Example in `mongosh`:

```javascript
db.numericLab.insertMany([
  { _id: "int", value: NumberInt(7) },
  { _id: "long", value: NumberLong("7") },
  { _id: "double", value: 7.0 },
  { _id: "decimal", value: NumberDecimal("7.0") },
  { _id: "larger", value: NumberDecimal("7.5") }
]);

db.numericLab.find(
  { value: { $gt: 7 } },
  { _id: 1, value: 1 }
);
```

Numeric values equal to `7` do not satisfy `$gt`; `7.5` does. If you only want to filter for one specific numeric type, use `$type` or schema checks instead of expecting `$gt` to distinguish `Int32` from `Double`.

### 2.2. `Date` Differs from `Timestamp`

`ISODate("2026-01-01T00:00:00Z")` is a BSON `Date`; `Timestamp` is a separate BSON type commonly seen in internal mechanisms like the oplog, containing seconds and an increment. **Date sorts before Timestamp in cross-type comparison**, even when both correspond to the same calendar time.

Do not use `Timestamp` in place of order date, expiration date, or login time. Those business fields normally use `Date`; `Timestamp` carries distinct technical semantics.

### 2.3. `ObjectId` Is Neither a Number Nor a Date

`ObjectId` is a distinct type with its own position in the table. Although a standard `ObjectId` embeds a timestamp component, comparing and sorting `ObjectId` **does not replace an explicitly designed `createdAt` field**. Applications can generate ObjectIds off-server, IDs generated within the same second do not strictly match global system event order, and `_id` may even use another type.

## 3. Hands-On: Sorting a Collection with Multiple BSON Types

Create a test collection holding multiple types **without arrays yet**, so you can observe BSON ordering directly:

```javascript
db.typeSortLab.drop();

db.typeSortLab.insertMany([
  { _id: "missing" },
  { _id: "null", value: null },
  { _id: "int", value: NumberInt(10) },
  { _id: "double", value: 2.5 },
  { _id: "decimal", value: NumberDecimal("3.75") },
  { _id: "string", value: "2" },
  { _id: "object", value: { x: 1 } },
  { _id: "binary", value: BinData(0, "AQ==") },
  { _id: "objectId",
    value: ObjectId("65a12f010000000000000001") },
  { _id: "boolean", value: false },
  { _id: "date", value: ISODate("2026-04-01T00:00:00Z") },
  { _id: "timestamp",
    value: Timestamp({ t: 1711929600, i: 1 }) }
]);

db.typeSortLab.find({}, { _id: 1, value: 1 })
  .sort({ value: 1, _id: 1 });
```

Expected group order in the ascending sort:

```text
missing, null
double (2.5), decimal (3.75), int (10)
string ("2")
object
binary
objectId
boolean
date
timestamp
```

Missing fields and `null` are **treated as equivalent sort keys**; `_id` is added as a secondary key to make the example output deterministic. In practice, if multiple documents share the same sort key without a unique tie-breaker, MongoDB does not guarantee their relative order.

Reversing direction:

```javascript
db.typeSortLab.find({}, { _id: 1, value: 1 })
  .sort({ value: -1, _id: 1 });
```

The type groups reverse their relative order, though notice `_id: 1` still sorts ascending when `value` ties. With only `sort({ value: -1 })`, ordering among tied values can vary.

**Important note:** the example above intentionally omitted arrays. For Array-typed fields, MongoDB applies **array element selection** rules when sorting, so you cannot simply place all array documents into a single Array block in every result.

## 4. Comparison Queries: Type Bracketing Differs from BSON Order

Common filter predicate operators:

- `$eq`, `$ne`: value equality/inequality.
- `$gt`, `$gte`, `$lt`, `$lte`: greater than, greater than or equal, less than, less than or equal.
- `$in`, `$nin`: set membership checks (with specific rules for arrays).
- `$type`: BSON type check.

**Inequality predicates** `$gt`/`$gte`/`$lt`/`$lte` apply **type bracketing**. They evaluate only values matching the query operand's type group. Numeric types (`int`, `long`, `double`, `decimal`) form one equivalent comparison group.

### 4.1. Example Separating Numbers, Strings, and Objects

```javascript
db.typeQueryLab.drop();

db.typeQueryLab.insertMany([
  { _id: "smallNumber", score: NumberInt(8) },
  { _id: "largeNumber", score: NumberLong("20") },
  { _id: "decimalNumber", score: NumberDecimal("17.5") },
  { _id: "textNumber", score: "100" },
  { _id: "objectValue", score: { amount: 200 } },
  { _id: "missingScore" }
]);

db.typeQueryLab.find(
  { score: { $gt: 15 } },
  { _id: 1, score: 1 }
);
```

This query returns `largeNumber` and `decimalNumber`. It does not select `textNumber` or `objectValue` merely because String and Object sort after Number in BSON order. `missingScore` does not match either.

A common misconception:

```text
Wrong:   "$gt: 15" means every BSON type ordered after Number matches.
Correct: Predicates compare within the compatible type group of the operand.
```

Conversely, with **aggregation expressions**, comparison expressions such as `$gt` inside `$expr` can use global BSON order for cross-type comparison:

```javascript
db.typeQueryLab.find({
  $expr: { $gt: ["$score", 15] }
});
```

This expression has different semantics from the predicate `{ score: { $gt: 15 } }`: because String and Object follow Number in BSON order, a cross-type comparison expression can evaluate to true for `"100"` or `{ amount: 200 }`. That is why you should **never mechanically swap a predicate for `$expr`** without reviewing type semantics and index usage.

### 4.2. `$ne` and `$nin` Do Not Apply Type Bracketing Like `$gt`

Example:

```javascript
db.typeQueryLab.find({ score: { $ne: 15 } });
```

`$ne` can match documents of various types as well as documents missing the field (per `$ne` semantics). Similarly with `$nin`, negation/set predicates follow matching rules distinct from range comparisons. Therefore, to filter for **only valid numbers**, you cannot rely solely on `$ne` excluding a particular number.

### 4.3. Filtering by Type with `$type`

`$type` is useful when data contains mixed types due to migrations, dirty data, or API changes:

```javascript
// Only numeric-group values
db.typeQueryLab.find({
  score: { $type: "number" }
});

// Only BSON String
db.typeQueryLab.find({
  score: { $type: "string" }
});

// Inspect the actual type of each value in aggregation
db.typeQueryLab.aggregate([
  {
    $project: {
      _id: 1,
      score: 1,
      actualType: { $type: "$score" }
    }
  }
]);
```

In aggregation, `$type` on a non-existent field returns `"missing"`; on a `null` field it returns `"null"`. When using the `$type` query operator directly on an **array** field, MongoDB can match based on element types rather than just the container type. To inspect the type of the whole field value accurately, use the aggregation `$type` expression.

## 5. Sorting Arrays: Selecting the Minimum or Maximum Element

This is a crucial exception. When calling `sort()` on a field containing an array:

- **Ascending `1`**: MongoDB uses the **smallest element** of the array as the sort key.
- **Descending `-1`**: MongoDB uses the **largest element** of the array as the sort key in descending order.
- For an empty array `[]`, MongoDB places it **before `null` or missing fields** in an ascending sort.
- For a single-element array, sorting by that key behaves similarly to sorting a scalar of the same type.

Example:

```javascript
db.arraySortLab.drop();

db.arraySortLab.insertMany([
  { _id: "a", scores: [5, 80] },
  { _id: "b", scores: [20, 30] },
  { _id: "c", scores: [10] },
  { _id: "scalar", scores: 50 },
  { _id: "empty", scores: [] },
  { _id: "explicitNull", scores: null },
  { _id: "missing" }
]);

db.arraySortLab.find({}, { _id: 1, scores: 1 })
  .sort({ scores: 1, _id: 1 });

db.arraySortLab.find({}, { _id: 1, scores: 1 })
  .sort({ scores: -1, _id: 1 });
```

Among comparable numeric values, we observe:

| Document | `scores` | Ascending Sort Key | Descending Sort Key |
|---|---|---:|---:|
| `a` | `[5, 80]` | `5` | `80` |
| `b` | `[20, 30]` | `20` | `30` |
| `c` | `[10]` | `10` | `10` |
| `scalar` | `50` | `50` | `50` |

The **ascending** order of documents containing numbers or numeric arrays is `a → c → b → scalar`; **descending** is `a → scalar → b → c`. Because different elements are chosen, descending order is **not simply the reverse of the ascending list**.

Document `empty` with `[]` sorts before `null`/missing in ascending order, outside the numeric array comparisons in the table. For `null` and missing fields, MongoDB treats them as equal sort keys, so include a secondary `_id` key for repeatable ordering.

### 5.1. An Array Filter Does Not Choose the Sort Element

Consider:

```javascript
db.arraySortLab.find({
  scores: { $gt: 15 }
}).sort({ scores: 1 });
```

Document `a` has element `80` matching `$gt: 15`, yet the ascending sort key for `[5,80]` remains `5`. The filter condition does not turn the sort key into `80`. This is a frequent bug when assuming MongoDB sorts by **the element that matched the predicate**.

If your business logic needs "highest score" or "lowest score" deliberately, store precomputed `maxScore`/`minScore` summary fields or compute explicit sort keys in aggregation depending on workload and index requirements.

### 5.2. Comparing Two Arrays in Expressions Differs from Array Sorting

When **comparing an array with an array**, MongoDB uses lexicographic order, comparing elements pairwise from the beginning until a difference is found or one array ends:

```text
[1, 3] < [1, 5]
[1, 2] < [1, 2, 0]
```

Array-to-array comparison (such as in aggregation expressions) must be distinguished from the **min/max element** selection rule used when sorting an array-valued field. Comparison predicates on array fields also have their own element traversal and type-bracketing mechanics. Never apply one array rule universally across every MongoDB operation.

## 6. Sorting Embedded Documents: Types, Field Names, and Field Order

For BSON Objects, MongoDB compares key–value pairs in **the order they appear inside the document**. At each position, it compares the value's type, then the field name and value under BSON comparison rules; if corresponding pairs are equal, it moves to the next pair. A document that runs out of pairs is considered less than one with additional pairs.

Therefore:

```javascript
{ a: 1, b: 2 }
{ b: 2, a: 1 }
```

must not be treated as two BSON objects where field order is completely irrelevant. This is particularly important for **exact equality** queries against an entire embedded document:

```javascript
db.objectLab.insertMany([
  { _id: "first", details: { a: 1, b: 2 } },
  { _id: "second", details: { b: 2, a: 1 } }
]);

// Compares the entire embedded document; field order matters
db.objectLab.find({ details: { a: 1, b: 2 } });

// Queries individual sub-fields; independent of document field order
db.objectLab.find({ "details.a": 1, "details.b": 2 });
```

When matching attributes without caring about field declaration order, use **dot notation**, sub-field filters, or a consistent schema layout instead of passing an entire object to equality.

## 7. Strings: Binary Comparison, Collation, and `numericOrdering`

### 7.1. Default Is Simple Binary Comparison

Without another collation specified on the collection or operation, MongoDB uses **simple binary comparison** for strings. That order does not necessarily match the alphabetical order expected by Vietnamese readers:

- Uppercase and lowercase letters can sort separately.
- Accented letters have different byte representations from unaccented letters.
- The string `"10"` typically sorts before `"2"` by character-by-character lexicographic order.
- Byte order does not automatically apply dictionary linguistic rules.

Example:

```javascript
db.stringLab.drop();

db.stringLab.insertMany([
  { _id: 1, label: "2" },
  { _id: 2, label: "10" },
  { _id: 3, label: "An" },
  { _id: 4, label: "an" },
  { _id: 5, label: "Ánh" },
  { _id: 6, label: "ánh" }
]);

db.stringLab.find({}, { _id: 0, label: 1 })
  .sort({ label: 1 });
```

To achieve language-appropriate ordering, use **collation**.

### 7.2. Collation Changes How Strings Compare

Collation provides rules for case sensitivity, diacritics, and locale-specific alphabetical ordering:

```javascript
db.stringLab.find({}, { _id: 0, label: 1 })
  .sort({ label: 1 })
  .collation({
    locale: "vi",
    strength: 1
  });
```

With `strength: 1`, primary-level comparison focuses on base characters per the locale; many case and diacritic differences do not distinguish strings at this level. When two strings compare equal under the chosen collation level, **their relative order is not guaranteed** unless a suitable secondary sort key is added.

Notable collation options:

| Option | Meaning |
|---|---|
| `locale` | ICU language/rule set, such as `"vi"` or `"en"`; `"simple"` is binary comparison |
| `strength: 1` | Base-character comparison, typically ignoring case and diacritic differences |
| `strength: 2` | Considers diacritic differences per locale rules; usually still ignores case |
| `strength: 3` | Adds case/character-variant sensitivity; default for most locales |
| `caseLevel` | Enables case comparison even at `strength: 1` or `2` |
| `caseFirst` | Affects uppercase vs. lowercase ordering at appropriate strength levels |
| `numericOrdering` | Compares non-negative integer digit sequences numerically in supported cases |

### 7.3. `numericOrdering: true` Applies Only to Strings, with Limits

If `"2"` and `"10"` are stored as Strings, binary sorting puts `"10"` before `"2"`. You can use:

```javascript
db.stringLab.find({}, { _id: 0, label: 1 })
  .sort({ label: 1 })
  .collation({
    locale: "en",
    numericOrdering: true
  });
```

For simple positive integer strings, `"2"` sorts before `"10"`. However, `numericOrdering` **does not convert strings into Numbers**: it does not parse negative signs `-`, plus signs `+`, decimal points, or scientific exponents as full numbers. Nor does it **merge BSON Strings with Numbers** in the global BSON sort order.

If a field represents a quantitative value, store it with an appropriate BSON numeric type rather than relying on collation to compensate for mistyped data.

### 7.4. Collation Must Match the Index

An index can support string sorting and filtering only if the operation's collation **matches** the index's collation. Example:

```javascript
db.users.createIndex(
  { displayName: 1 },
  { collation: { locale: "vi", strength: 2 } }
);

db.users.find({ displayName: "ánh" })
  .collation({ locale: "vi", strength: 2 });

// Sorting with the same collation can leverage the matching index
db.users.find()
  .sort({ displayName: 1 })
  .collation({ locale: "vi", strength: 2 });
```

If a query uses `locale: "simple"` while the index was built with `locale: "vi"`, MongoDB generally cannot use that index for **simple-collation string comparisons**. Non-string index prefixes may still be usable depending on the query. Inspect `explain()` and check default collations at the collection, index, and operation levels.

## 8. `null`, Missing Fields, and `undefined`

### 8.1. `null` and Missing Fields in Sorting

Consider:

```javascript
db.nullSortLab.drop();

db.nullSortLab.insertMany([
  { _id: "missing" },
  { _id: "explicitNull", x: null },
  { _id: "zero", x: 0 },
  { _id: "text", x: "" }
]);

db.nullSortLab.find().sort({ x: 1, _id: 1 });
```

When sorting by `x`, a **missing** field compares like `null`; thus `missing` and `explicitNull` tie as sort keys and both precede Numbers. Include the unique secondary key `_id` to stabilize the order.

For an empty array `[]`, array sort rules place it before `null`/missing in ascending order. Therefore, never write application logic assuming every "empty" value sorts identically.

### 8.2. How to Query `null` and Missing Explicitly

```javascript
// null equality typically matches both explicit null and missing fields
db.nullSortLab.find({ x: null });

// Only documents containing field x, regardless of value
db.nullSortLab.find({ x: { $exists: true } });

// Only documents missing field x
db.nullSortLab.find({ x: { $exists: false } });

// Only documents with BSON Null type
db.nullSortLab.find({ x: { $type: "null" } });
```

Distinguishing `null`, missing, and default values in your schema makes pagination, sorting, and filtering far more predictable.

### 8.3. Version Differences with BSON Undefined

`undefined` is a BSON type deprecated from recommended usage. Starting with MongoDB **8.0+**, `{ x: null }` equality queries no longer match BSON `undefined` values; earlier versions handled `undefined` differently. If legacy data contains `undefined`, check your server version and plan a data migration rather than assuming `undefined` behaves identically to `null`.

## 9. Indexes, Sorting, and the Consequences of Mixed Data Types

MongoDB indexes store keys according to BSON value types and associated comparison rules. An index supporting `sort({ field: 1 })` reflects the BSON sort order of values in that field. However, query efficiency also depends on filters, compound index key order, collation, and array/multikey fields.

Example:

```javascript
db.events.createIndex({ category: 1, createdAt: -1, _id: 1 });

db.events.find({ category: "payment" })
  .sort({ createdAt: -1, _id: 1 })
  .limit(20)
  .explain("executionStats");
```

If every `createdAt` is a BSON Date, the index serves chronological queries efficiently. Yet if some documents store `createdAt` as an ISO String, an epoch number, or `null`, sorting splits them by **BSON type group** and may fail to reflect business chronology:

```javascript
{ createdAt: ISODate("2026-01-02T00:00:00Z") }  // Date
{ createdAt: "2026-01-01T00:00:00Z" }            // String
{ createdAt: NumberLong("1767225600000") }      // Number
```

Even though the ISO 8601 String looks like a Date visually, MongoDB does not unify them automatically. **Indexes do not fix type inconsistency**; they only accelerate access under the rules the database actually enforces.

### 9.1. When Is a Secondary Sort Key Needed for Stable Ordering?

`sort({ createdAt: -1 })` does not guarantee deterministic ordering among documents sharing the same `createdAt` or `null` key. In pagination, this can cause documents to jump across pages between reads, especially as new records arrive.

A clear ordering pattern is:

```javascript
db.events.find({ category: "payment" })
  .sort({ createdAt: -1, _id: 1 })
  .limit(20);
```

This ordering uses `_id` as a unique tie-breaker. When implementing cursor pagination, the next-page predicate must respect **both sort directions** (`createdAt` descending, `_id` ascending) and handle null/missing boundaries consistently; a large `skip()` alone does not stabilize mutating datasets.

### 9.2. When Does a Filter Use an Index Differently from a Sort?

An index can accelerate `{ score: { $gt: 20 } }` effectively when data is numeric. But if the schema allows Strings alongside Numbers, using an index does not make the predicate bypass type bracketing to match `"30"`. Indexes organize keys under BSON rules; **query semantics are governed by the operators**.

When queries require type coercion, prefer migrating the data (when feasible) or converting inside aggregation using `$convert`/`$toDecimal` with error handling. Runtime conversion adds CPU overhead and restricts index usage; never treat it as performance-equivalent to a normalized numeric field.

### 9.3. Preventing Mistyped Data with Schema Validation

Example collection accepting `price` strictly as `decimal` and `createdAt` strictly as `date`:

```javascript
db.createCollection("validatedProducts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "price", "createdAt"],
      properties: {
        name: { bsonType: "string" },
        price: { bsonType: "decimal" },
        createdAt: { bsonType: "date" }
      }
    }
  }
});
```

Depending on requirements, you can permit multiple numeric types using `bsonType: ["int", "long", "double", "decimal"]`, though for monetary amounts or fixed-precision measurements, one canonical type simplifies analytics. Validators do not replace API-level business checks or legacy data migration procedures.

## 10. Quick Reference: Sort, Predicates, and Aggregation

| Scenario | Key Rule | Pitfall to Avoid |
|---|---|---|
| `sort({ x: 1 })`, `x` has mixed scalar types | Compares by BSON order from lowest to highest | Assuming String `"10"` compares like Number `10` |
| `sort({ x: -1 })` | Reverses type/value order of the sort key | Forgetting a tie-breaker for equal values |
| `find({ x: { $gt: 10 } })` | Predicate uses type bracketing | Concluding every String/Object after Number matches |
| `$expr: { $gt: ["$x", 10] }` | Aggregation expression can compare across types via BSON order | Treating it as identical to query predicate `$gt` |
| `sort({ x: 1 })` on arrays | Uses the minimum element as sort key | Assuming it sorts by the filter-matched element |
| `sort({ x: -1 })` on arrays | Uses the maximum element as sort key | Assuming descending is always the reverse of ascending |
| Comparing nested objects | Key/value order can affect equality | Assuming two objects with identical fields in different order always match |
| `sort` on `null` and missing | Missing compares equal to `null` as a sort key | Expecting a fixed order between the two |
| Sorting Strings with `simple` | Binary byte comparison, not locale dictionary order | Using default sort for Vietnamese names when linguistic order is expected |
| Sorting Strings with collation | Follows `locale`, `strength`, and related options | Creating an index with a different collation and expecting it to serve the sort |
| Index on field mixing Date/String | Index preserves BSON type separation | Thinking the index normalizes values into one timeline |

## 11. Practice Exercises

### Exercise 1 — Create Mixed-Type Data and Predict `sort`

Insert documents whose `value` fields are `null`, `NumberInt(5)`, `NumberDecimal("5.5")`, `"1"`, `{}`, `ObjectId`, `true`, and `ISODate`. Predict the output order of `sort({ value: 1 })` before running the command. Explain why `"1"` does not precede `5`, and why `Date` sorts after `Boolean` across types.

### Exercise 2 — Distinguish Query Predicates from `$expr`

On `typeQueryLab`, run:

```javascript
db.typeQueryLab.find({ score: { $gt: 15 } }, { _id: 1 });
db.typeQueryLab.find({ $expr: { $gt: ["$score", 15] } }, { _id: 1 });
```

Compare the two result sets. Point out the role of type bracketing in the predicate vs. BSON order in the aggregation expression. Then filter for valid numbers only using `$type` or migrate to a uniform type.

### Exercise 3 — Trace Array Sort Keys

With `scores` values `[5,80]`, `[20,30]`, `[10]`, and `50`, write down the ascending and descending orders before executing. Then test filtering `scores: { $gt: 15 }` while sorting ascending. Explain why element `5` in `[5,80]` still determines the sort position even though `80` was the element matching the filter.

### Exercise 4 — Fix Product Name Sorting Issues

A system displays Vietnamese product names under `simple` collation and receives complaints that accented and mixed-case names sort out of expected order. Do the following:

1. Create a test dataset containing accented/unaccented and uppercase/lowercase names.
2. Compare `simple` against `{ locale: "vi", strength: 2 }`.
3. Create an index with a matching collation for the query.
4. Use `explain("executionStats")` to inspect the query plan and verify whether an in-memory sort stage occurs.

### Exercise 5 — Safe Schema Design

A transactions collection has `amount` mixing `"100.50"`, `NumberDecimal("100.50")`, and `100.5`. Propose a roadmap to unify on `Decimal128`, including defining currency units, handling invalid values, verified migration, adding a validator, and reviewing indexes. Explain why tweaking `sort()` or collation alone cannot fix the root cause.

## 12. MongoDB Reference Documentation

- [Comparison/Sort Order — BSON order for arrays, objects, null, and BinData](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/)
- [Type Bracketing in Query Predicates — how `$gt`/`$lt` filter by type](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/type-bracketing/)
- [Comparison Query Predicate Operators — differences between predicates and expressions](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/comparison/)
- [Collation — locale, strength, numericOrdering, and index rules](https://www.mongodb.com/docs/manual/reference/collation/)
- [Migrate Undefined Data and Queries — `null` behavior changes starting in MongoDB 8.0](https://www.mongodb.com/docs/manual/reference/bson-types/migrate-undefined/)

## Conclusion

MongoDB enforces a **well-defined BSON sort order**: `MinKey`, `Null`, numbers, strings, objects, arrays, binary, `ObjectId`, Boolean, Date, Timestamp, and specialized types. However, **query predicates use type bracketing**, aggregation expressions compare differently, arrays follow min/max element rules during sorts, and strings can apply language-aware collation.

Consequently, writing accurate MongoDB queries requires checking **the data's BSON type**, **the operator used**, **collation**, **index definitions**, and **secondary tie-breaker sort keys**. Maintaining a consistent schema for critical fields like money, timestamps, and statuses is the surest way to avoid surprising filter and sort results.
