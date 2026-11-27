# Type Checking and Conversion with $type, $convert, and $to*

MongoDB stores data in the BSON model. Within the same collection, documents are not required to have the exact same structure, and a field can exist with **different BSON types** if the application does not enforce a schema. This is very flexible, yet easily causes errors when aggregation needs to sum prices, filter by date, compare numbers, or concatenate identifier strings.

Suppose the `orders` collection contains these documents:

```javascript
[
  {
    _id: 1,
    total: NumberDecimal("125000.50"),
    orderedAt: ISODate("2026-03-01T09:30:00Z"),
    customerId: ObjectId("65a12f010000000000000001")
  },
  {
    _id: 2,
    total: "85000.75",
    orderedAt: "2026-03-02T10:00:00Z",
    customerId: "65a12f010000000000000002"
  },
  {
    _id: 3,
    total: "unknown",
    orderedAt: "yesterday",
    customerId: null
  },
  {
    _id: 4,
    total: null
  },
  {
    _id: 5
  }
]
```

The records above have several issues:

- `total` can be `decimal`, `string`, `null`, or missing;
- `orderedAt` can be a BSON `date`, a valid date string, an invalid string, or missing;
- `customerId` can be an `objectId`, a hex string, or `null`.

To aggregate revenue, the application must ensure `total` is actually a numeric type. To filter by time, `orderedAt` must be normalized into a BSON Date, not merely look like a date inside a string.

In aggregation, three groups of tools address this problem:

| Group | Role | Example |
|---|---|---|
| `$type` | **Inspects the BSON type** returned by an expression | `{ $type: "$total" }` |
| `$convert` | **Converts types** and defines custom error/null handling | `{ $convert: { input: "$total", to: "decimal", onError: null, onNull: null } }` |
| `$to*` | **Shorthand syntax** for common conversions | `{ $toDecimal: "$total" }`, `{ $toDate: "$orderedAt" }` |

This lesson focuses on **aggregation expressions** inside stages such as `$project`, `$addFields`/`$set`, and `$match` with `$expr`. These expressions are also used in other MongoDB contexts that support corresponding expressions.

## 1. BSON Types Differ from JSON Display Representation

A value like `125000` can be stored using different BSON types:

```javascript
{
  amountInt: NumberInt(125000),
  amountLong: NumberLong("125000"),
  amountDouble: 125000.0,
  amountDecimal: NumberDecimal("125000.00"),
  amountText: "125000",
  amountNull: null
}
```

In business terms, these values might all evoke "125,000", but MongoDB does not automatically treat the string `"125000"` as a number across all operations. The BSON type affects:

1. Addition, multiplication, comparison, and input validation of expressions;
2. Precision representation, value range, and numeric overflow;
3. Comparison order when data has mixed types;
4. Index usability in queries;
5. Mapping results to Java/JavaScript and JSON output formatting.

Common types:

| Label from aggregation `$type` | Meaning |
|---|---|
| `"double"` | IEEE 754 double-precision floating point |
| `"string"` | UTF-8 string |
| `"object"` | Embedded document |
| `"array"` | Array |
| `"binData"` | Binary data |
| `"objectId"` | BSON ObjectId |
| `"bool"` | Boolean |
| `"date"` | BSON Date |
| `"null"` | Present null value |
| `"regex"` | Regular expression |
| `"int"` | 32-bit integer |
| `"long"` | 64-bit integer |
| `"decimal"` | Decimal128 |
| `"timestamp"` | BSON Timestamp |
| `"missing"` | Referenced field does not exist |

BSON also has less common types, including legacy ones. There is no need to force all data into one single type; **types must be consistent per field and business contract**.

### 1.1. Numeric Strings Are Not BSON Numbers

```javascript
{
  _id: "A",
  price: "125000.50"
}
```

Here `price` is a String. If you run an operation requiring numeric input, MongoDB may throw an error or apply expression-specific rules rather than guaranteeing an automatic conversion from String to Decimal128.

The explicit approach is controlled conversion:

```javascript
{
  $convert: {
    input: "$price",
    to: "decimal",
    onError: null,
    onNull: null
  }
}
```

A valid string produces a Decimal128 number; an invalid string is flagged with a `null` result in this example instead of failing the entire aggregation.

### 1.2. A BSON Date Is Not an ISO-Formatted String

```javascript
{
  orderedAtDate: ISODate("2026-03-01T09:30:00Z"),
  orderedAtString: "2026-03-01T09:30:00Z"
}
```

The first value has type `date` and works cleanly with time range operations. The second value is a `string`. Although they look similar when displayed, they do not share the same BSON type. An index on a date field does not automatically turn strings into dates.

## 2. Preparing the Practice Collection

Create a separate collection to avoid altering production/business data:

```javascript
db.typeConversionLab.drop();

db.typeConversionLab.insertMany([
  {
    _id: "O-101",
    total: NumberDecimal("125000.50"),
    quantity: NumberInt(2),
    orderedAt: ISODate("2026-03-01T09:30:00Z"),
    customerId: ObjectId("65a12f010000000000000001"),
    active: true
  },
  {
    _id: "O-102",
    total: "85000.75",
    quantity: "3",
    orderedAt: "2026-03-02T10:00:00Z",
    customerId: "65a12f010000000000000002",
    active: "false"
  },
  {
    _id: "O-103",
    total: "unknown",
    quantity: "3.5",
    orderedAt: "yesterday",
    customerId: "not an objectId",
    active: ""
  },
  {
    _id: "O-104",
    total: null,
    quantity: null,
    orderedAt: null,
    customerId: null
  },
  {
    _id: "O-105"
  },
  {
    _id: "O-106",
    total: NumberLong("9000000000"),
    quantity: NumberInt(1),
    orderedAt: ISODate("2026-03-03T08:00:00Z"),
    active: false
  }
]);
```

**Note:** `db.typeConversionLab.drop()` deletes the test collection if it already exists. Use this example only in a learning environment; never run `drop()` on a production collection.

The data is intentionally inconsistent so the difference between "unconvertible", `null`, and missing fields stands out clearly. In a real application, block wrong-type data on the write path using schema validation, API validation, and controlled migrations.

## 3. $type: Inspecting the BSON Type of an Expression

Basic syntax:

```javascript
{ $type: <expression> }
```

Most commonly, pass a field path:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      total: 1,
      totalType: { $type: "$total" },
      orderedAtType: { $type: "$orderedAt" },
      customerIdType: { $type: "$customerId" }
    }
  },
  { $sort: { _id: 1 } }
]);
```

With the documents created above:

- O-101: `totalType = "decimal"`, `orderedAtType = "date"`, `customerIdType = "objectId"`.
- O-102: all three corresponding fields have type `"string"`.
- O-103: those fields are also strings, even though **the string values are invalid for conversion**.
- O-104: fields present with `null` return the `"null"` label.
- O-105: non-existent fields return the `"missing"` label.
- O-106: `totalType = "long"`.

**`$type` checks the type, not whether the value is valid per business rules.** Both `"85000.75"` and `"unknown"` return `"string"`, yet only the first string can be converted directly to Decimal128 using valid numeric syntax.

### 3.1. Distinguishing null and missing

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      typeOfTotal: { $type: "$total" }
    }
  }
]);
```

In O-104, the result contains `typeOfTotal: "null"`.

In O-105, the result contains `typeOfTotal: "missing"`.

The difference:

- **null:** the field exists, and its BSON value is `null`;
- **missing:** the field does not exist in the document.

Many other expressions handle these two states identically. For example, `$ifNull` usually treats missing and null values the same when choosing a fallback. When compiling data quality statistics, `$type` preserves that distinction.

### 3.2. $type on an Array Field

Suppose:

```javascript
db.typeConversionLab.insertOne({
  _id: "O-107",
  values: [1, "2", null],
  metadata: { source: "legacy" }
});
```

Query:

```javascript
db.typeConversionLab.aggregate([
  { $match: { _id: "O-107" } },
  {
    $project: {
      valuesType: { $type: "$values" },
      metadataType: { $type: "$metadata" }
    }
  }
]);
```

Result: `valuesType = "array"` and `metadataType = "object"`. **The aggregation expression `$type` does not automatically traverse array elements** to return `["int", "string", "null"]`.

If you want the type of each element, combine `$map` and `$type`:

```javascript
db.typeConversionLab.aggregate([
  { $match: { _id: "O-107" } },
  {
    $project: {
      _id: 0,
      elementTypes: {
        $map: {
          input: "$values",
          as: "v",
          in: { $type: "$$v" }
        }
      }
    }
  }
]);
```

Result:

```javascript
{
  elementTypes: ["int", "string", "null"]
}
```

Distinguish missing/null array fields from real arrays: `$map` has specific rules for null/missing and non-array values; use `$isArray` and `$cond` if the legacy schema is inconsistent.

## 4. $type in Aggregation Differs from $type in Query Filters

MongoDB has both a **query operator `$type`** and an **aggregation expression `$type`**. They are related, but they do not share the same syntax and do not always behave identically on arrays.

### 4.1. Query Operator in a Standard $match

```javascript
// Find documents where total is BSON String.
db.typeConversionLab.find({
  total: { $type: "string" }
});
```

This is a query-language predicate. MongoDB may use an appropriate index for such predicates depending on the query.

### 4.2. Aggregation Expression in $project

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      totalType: { $type: "$total" }
    }
  }
]);
```

This **computes the type name** for each document.

### 4.3. Using $expr to Check Types with an Expression

```javascript
db.typeConversionLab.aggregate([
  {
    $match: {
      $expr: {
        $eq: [{ $type: "$total" }, "string"]
      }
    }
  }
]);
```

The query filters documents where the expression `$type: "$total"` evaluates to `"string"`. When a query simply needs to check whether a field has a certain BSON type, the direct syntax `{ total: { $type: "string" } }` is usually easier to read; consider `$expr` when complex expression conditions are required.

### 4.4. Important Difference with Arrays

Given the document:

```javascript
{
  _id: "array-demo",
  values: [1, "abc"]
}
```

The query predicate:

```javascript
db.typeConversionLab.find({
  values: { $type: "string" }
});
```

can match the document if **at least one array element** is of type String according to query operator semantics.

Meanwhile:

```javascript
{
  $type: "$values"
}
```

in aggregation returns `"array"` because the expression value is the array itself. Do not carry over the "field type is string" intuition from array queries into aggregation without accounting for this difference.

## 5. $convert: Full Syntax and Error Control

Common syntax:

```javascript
{
  $convert: {
    input: <expression>,
    to: <targetType>,
    onError: <expression>,
    onNull: <expression>
  }
}
```

Parameters:

| Parameter | Meaning |
|---|---|
| `input` | Expression returning the value to convert |
| `to` | Target BSON type: e.g., `"int"`, `"long"`, `"double"`, `"decimal"`, `"string"`, `"date"`, `"bool"`, `"objectId"` |
| `onError` | Value/expression returned when **conversion is not possible** (if omitted, an error may abort the pipeline) |
| `onNull` | Value/expression when input is null or missing (if omitted, typically returns null) |

Newer MongoDB versions also support parameters related to BinData conversions such as `format`/`byteOrder` and advanced `to` forms. When using BinData/UUID or version-dependent syntax, check the documentation for the **running server version** instead of copying options from a newer version.

Example converting `total` to Decimal128 without crashing the pipeline on invalid strings:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      original: "$total",
      originalType: { $type: "$total" },
      totalDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Explanation:

- `NumberDecimal("125000.50")` stays the corresponding decimal value.
- The string `"85000.75"` converts to Decimal128.
- The string `"unknown"` cannot be converted, so `onError: null` turns the error into a `null` result.
- `total: null` and a missing `total` field both yield `null` via `onNull`.

This allows the **pipeline to keep running** over dirty data. However, it does not mean the bad data has been fixed. If these records are skipped during revenue calculation without logging or reconciliation, reports may undercount revenue.

### 5.1. onError Is Not the Same as onNull

Suppose:

```javascript
{
  $convert: {
    input: "$quantity",
    to: "int",
    onError: "INVALID",
    onNull: "MISSING_OR_NULL"
  }
}
```

Result semantics:

| quantity value | Result |
|---|---|
| `NumberInt(2)` | `2` |
| `"3"` | `3` |
| `"3.5"` | `"INVALID"` |
| `null` | `"MISSING_OR_NULL"` |
| Missing | `"MISSING_OR_NULL"` |

`onError` handles cases where **an input exists but cannot be converted to the target type**; `onNull` handles **null or missing input**.

If you need to distinguish `null` from `missing`, additionally use `$type` to record the original state. `$convert` itself does not have separate `onMissing` and `onNull` parameters.

### 5.2. Fallbacks Are Expressions, Not Just Constants

Example retaining error information:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      normalizedQuantity: {
        $convert: {
          input: "$quantity",
          to: "int",
          onError: -1,
          onNull: 0
        }
      }
    }
  }
]);
```

Technically this is one way to create sentinel values, but from a business perspective consider carefully: `-1` and `0` might be valid values. It is better to also return a **conversion status** or write errors to an audit/quarantine collection. If a sentinel is mistaken for real data, aggregated totals will be wrong.

### 5.3. Pipeline Aborts Without onError

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      quantityInt: {
        $convert: {
          input: "$quantity",
          to: "int"
        }
      }
    }
  }
]);
```

When encountering `quantity: "3.5"`, converting an invalidly formatted string to `int` can throw an error and **fail the entire aggregation**. There is no business-contract guarantee of "returning previously processed documents and automatically skipping faulty ones" at the aggregation API level.

For ETL on legacy data, explicitly specifying `onError` and `onNull` is a key part of the design.

## 6. The $to* Operators: Shorthand Syntax

MongoDB provides shortcuts for many common conversions:

| Shortcut | Target Type | Syntax |
|---|---|---|
| `$toInt` | BSON Int32 | `{ $toInt: "$quantity" }` |
| `$toLong` | BSON Int64 | `{ $toLong: "$views" }` |
| `$toDouble` | BSON Double | `{ $toDouble: "$ratio" }` |
| `$toDecimal` | Decimal128 | `{ $toDecimal: "$price" }` |
| `$toString` | String | `{ $toString: "$customerId" }` |
| `$toDate` | BSON Date | `{ $toDate: "$orderedAt" }` |
| `$toBool` | Boolean | `{ $toBool: "$active" }` |
| `$toObjectId` | BSON ObjectId | `{ $toObjectId: "$customerId" }` |

These shortcuts are typically equivalent to the corresponding `$convert` form containing only `input` and `to`:

```javascript
{ $toInt: "$quantity" }

{
  $convert: {
    input: "$quantity",
    to: "int"
  }
}
```

Important difference: shortcuts **do not provide slots for custom `onError` and `onNull`**. When the input is null/missing, standard conversions return null. When an unconvertible value is encountered, an error can abort the pipeline.

### 6.1. When to Choose a Shortcut?

Use `$to*` when:

- The schema is controlled and the input format is guaranteed valid;
- Data has already passed validation and concise expressions are desired;
- Conversion errors are intended to fail fast and expose anomalous data immediately.

Use `$convert` when:

- Input data has mixed types or invalid values;
- ETL must not fail completely on a single bad record;
- You need a default, error flag, or separation of records requiring inspection;
- You need to distinguish the null/missing branch from the conversion error branch.

Do not assume shortcuts are "faster" just because the syntax is shorter. The primary decision factor is the **error-handling contract**.

## 7. Converting to Integers: $toInt and $toLong

### 7.1. $toInt

Example:

```javascript
db.typeConversionLab.aggregate([
  { $match: { _id: "O-102" } },
  {
    $project: {
      quantityOriginal: "$quantity",
      quantityInt: { $toInt: "$quantity" }
    }
  }
]);
```

With `quantity: "3"`, the result has `quantityInt` of BSON type Int32 with value `3`.

Several important rules:

- Strings must represent valid integers; `"3"` is valid, whereas the decimal string `"3.5"` cannot be arbitrarily converted using `$toInt`.
- From floating-point numbers to integers, conversion may **truncate the fractional part toward zero** when the value fits within the target type limits. This is a type cast, not business rounding.
- Values outside the Int32 range throw an error.
- Null or missing values typically return null.
- Values that do not support conversion to integer can throw an error.

Example checking with a fallback:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      quantityInt: {
        $convert: {
          input: "$quantity",
          to: "int",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

If business logic requires a positive integer, converting to `int` is **not enough**; add a constraint such as `quantityInt > 0`, and check that the input did not contain a fractional part lost by truncation.

### 7.2. Int32 Range

Int32 stores integers from:

```text
-2,147,483,648 to 2,147,483,647
```

With the string:

```javascript
{ quantity: "9000000000" }
```

`$toInt` cannot represent it because it exceeds the Int32 range. Use `$toLong` if a 64-bit integer is appropriate:

```javascript
{
  $toLong: "$quantity"
}
```

### 7.3. $toLong and Int64 Limits

Int64 supports:

```text
-9,223,372,036,854,775,808
to
 9,223,372,036,854,775,807
```

`$toLong` is suitable for large counters, millisecond timestamps, or numeric IDs within this range.

```javascript
db.typeConversionLab.aggregate([
  { $match: { _id: "O-106" } },
  {
    $project: {
      originalType: { $type: "$total" },
      totalLong: { $toLong: "$total" },
      longType: { $type: { $toLong: "$total" } }
    }
  }
]);
```

Avoid routing large Int64 values through JavaScript `Number` or BSON Double if **exact unit precision** must be preserved. Double has a bounded range of exact integer representation under IEEE 754; for sufficiently large values, low-order digits can be lost.

### 7.4. Truncating Fractions Is Not Monetary Rounding

Suppose we have:

```javascript
{ units: 3.9 }
```

Converting to an integer may produce `3` via truncation. If an order must round up to `4`, use an explicit semantic operation such as `$ceil`, `$floor`, or `$round` before casting types; do not rely on `$toInt` as a substitute for business rules.

Example:

```javascript
db.lineItems.aggregate([
  {
    $project: {
      billedUnits: {
        $toInt: { $ceil: "$requestedUnits" }
      }
    }
  }
]);
```

This example assumes `requestedUnits` is a valid numeric value, containing neither null nor values outside the Int32 range.

## 8. Converting to Double and Decimal128

### 8.1. $toDouble

```javascript
db.metrics.aggregate([
  {
    $project: {
      responseSeconds: {
        $toDouble: "$responseSecondsRaw"
      }
    }
  }
]);
```

Valid numeric strings can be converted to Double. However, Double uses binary floating-point representation and cannot represent every decimal fraction exactly.

In particular, monetary values like `0.1` and `0.2` can introduce binary rounding errors during arithmetic. Do not use Double for monetary amounts requiring exact decimal-place precision unless the system has an explicit rounding and tolerance model.

### 8.2. $toDecimal

For monetary prices:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      priceDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Decimal128 stores decimal numbers with finite base-10 precision, making it suitable for many currency workflows that require exact base-10 representation.

Example computing tax from a normalized price:

```javascript
db.typeConversionLab.aggregate([
  {
    $set: {
      totalDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $match: {
      totalDecimal: { $ne: null }
    }
  },
  {
    $project: {
      _id: 1,
      totalDecimal: 1,
      tax: {
        $multiply: [
          "$totalDecimal",
          NumberDecimal("0.10")
        ]
      }
    }
  }
]);
```

The 10% tax example illustrates multiplication and does not reflect a specific country's tax rules or monetary rounding requirements.

### 8.3. Locale-Formatted Data

`$toDecimal` and `$toDouble` do not automatically understand every locale-specific number format.

Example strings:

```text
"1250.50"      // Decimal with dot separator
"1,250.50"     // Contains thousands comma separator
"1.250,50"     // Convention in some locales
"1 250,50"     // Contains space and comma
"1250 VND"     // Contains currency unit
```

Do not simply apply `$toDecimal` across all of them expecting every string to succeed or yield the same value. Identify the **data source/locale**, clean strings according to a verified rule, and then convert types. Blindly replacing every comma with a dot can turn `"1,250.50"` into a malformed string.

A high-quality ETL pipeline should preserve the original value, source name, parse status, and error record count for reconciliation.

### 8.4. Converting from Double to Decimal Does Not Restore Lost Precision

If a monetary amount was already stored as a Double and lost precision, running:

```javascript
{ $toDecimal: "$priceDouble" }
```

cannot automatically recover the **original exact monetary value** that the system discarded. Type conversion only operates on the value actually stored. For data requiring financial accuracy, normalize at ingestion time and avoid unnecessary round-trips through Double.

## 9. Converting to String: $toString

`$toString` is often useful when normalizing an identifier for data export, building string join keys, or creating display labels:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      customerIdText: {
        $convert: {
          input: "$customerId",
          to: "string",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

For a valid BSON ObjectId, converting to String typically yields its 24-character hex representation. For a string input, the string value is preserved appropriately.

Example concatenating a label:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      label: {
        $concat: [
          "Order ",
          { $toString: "$_id" }
        ]
      }
    }
  }
]);
```

In the practice dataset, `_id` is a String, so the command works straightforwardly. If documents have IDs of another type, verify conversion support and display formatting.

### 9.1. Not Every BSON Type Converts to String

Do not assume you can apply `$toString` to an array or embedded document and receive a complete JSON string:

```javascript
{
  details: { a: 1, b: 2 },
  values: [1, 2, 3]
}
```

Complex types cannot be converted directly with `$toString` under standard conversion rules. If the goal is JSON serialization, that belongs in the driver/application layer or a specifically designed pipeline, **not a guarantee of `$toString`**.

### 9.2. Converting IDs to String and $lookup Issues

If `orders.customerId` contains ObjectId and `customers._id` contains ObjectId, joins should use the ObjectId type on both sides. If one collection stores String IDs and the other stores ObjectIds, the type mismatch can prevent equality joins from matching as expected.

You can convert temporarily in aggregation, but normalizing the schema is a more sustainable solution. Converting fields dynamically at query time can reduce index usability or complicate joins.

## 10. Converting to ObjectId: $toObjectId

ObjectId is MongoDB's common BSON identifier type. A **valid 24-character hex string** can be converted to ObjectId.

```javascript
db.typeConversionLab.aggregate([
  { $match: { _id: "O-102" } },
  {
    $project: {
      _id: 1,
      original: "$customerId",
      customerObjectId: {
        $toObjectId: "$customerId"
      }
    }
  }
]);
```

With the value `"65a12f010000000000000002"`, the expression produces the corresponding BSON ObjectId.

### 10.1. Malformed Strings Cause Errors

For O-103:

```javascript
{ customerId: "not an objectId" }
```

Using:

```javascript
{ $toObjectId: "$customerId" }
```

can cause the aggregation to fail because the string is not validly formatted.

Use `$convert` if legacy data might be malformed:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      originalCustomerId: "$customerId",
      parsedCustomerId: {
        $convert: {
          input: "$customerId",
          to: "objectId",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

If parsing fails, `parsedCustomerId` becomes `null`; you can record an additional status based on the original type or route the record to an error-handling workflow.

### 10.2. ObjectId Is Not Just Any Identifier String

Example values:

```text
"user-1234"                // Business string, not an ObjectId
"65a12f010000000000000001" // 24-char hex string, can parse to ObjectId
"65a12f01000000000000000Z" // Contains 'Z', not valid hex
```

Do not force a business String ID into an ObjectId simply because MongoDB commonly uses ObjectId for `_id`. A collection may be designed with String or UUID `_id` values by contract.

### 10.3. Example Fixing a Type-Mismatched $lookup

Suppose `legacyOrders.customerId` is a hex string and `customers._id` is an ObjectId. You can normalize in aggregation:

```javascript
db.legacyOrders.aggregate([
  {
    $set: {
      customerObjectId: {
        $convert: {
          input: "$customerId",
          to: "objectId",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $lookup: {
      from: "customers",
      localField: "customerObjectId",
      foreignField: "_id",
      as: "customer"
    }
  },
  {
    $project: {
      orderNo: 1,
      customerId: 1,
      customer: 1
    }
  }
]);
```

This resolves the type mismatch for joining, though you still need to consider the query planner, the volume of data to convert, and index utilization. Migrating hex Strings to real ObjectIds in the schema typically makes subsequent queries simpler; prepare an update plan, rollback strategy, and handling for invalid data.

## 11. Converting to Date: $toDate

BSON Date represents a **point in time**. `$toDate` can convert several valid input types to Date, such as properly formatted date strings, milliseconds since the Unix epoch, or BSON ObjectIds (from the timestamp component of the ID).

Example:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      originalType: { $type: "$orderedAt" },
      parsedDate: {
        $convert: {
          input: "$orderedAt",
          to: "date",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

- O-101: valid Date is preserved as Date.
- O-102: ISO string with `Z` converts to Date.
- O-103: string `"yesterday"` is not a valid date for conversion, so the `onError` branch returns null.
- O-104/O-105: null/missing returns the `onNull` branch.

### 11.1. Numbers Converted to Date Represent Milliseconds

Example:

```javascript
db.epochLab.insertMany([
  {
    _id: 1,
    timestampMillis: NumberLong("0")
  },
  {
    _id: 2,
    timestampMillis: NumberLong("86400000")
  }
]);

db.epochLab.aggregate([
  {
    $project: {
      _id: 1,
      asDate: { $toDate: "$timestampMillis" }
    }
  }
]);
```

Semantics:

- `0` milliseconds since the Unix epoch corresponds to `1970-01-01T00:00:00Z`.
- `86400000` milliseconds corresponds to 24 hours later, `1970-01-02T00:00:00Z`.

**Common pitfall:** the source system supplies epoch **seconds**, but the application converts directly with `$toDate` and receives dates in 1970 instead of modern timestamps. When a data source stores seconds, convert to milliseconds via controlled multiplication by `1000`:

```javascript
db.epochSeconds.aggregate([
  {
    $project: {
      eventAt: {
        $toDate: {
          $multiply: [
            { $toLong: "$eventSeconds" },
            NumberLong("1000")
          ]
        }
      }
    }
  }
]);
```

This example assumes `eventSeconds` is a valid integer, stays within bounds when multiplied, and is genuinely in seconds.

### 11.2. ObjectIds Contain Timestamps, Not Authoritative Business Times

`$toDate` on an ObjectId extracts the timestamp encoded in the ObjectId. However, ObjectIds can be generated client-side, have limited time resolution, and are not guaranteed to match transaction commit time or business event time.

Do not use dates extracted from ObjectIds in place of `createdAt` when business logic requires an exact timestamp recorded by the server/application by contract.

### 11.3. Date Strings and Timezones

Strings such as:

```text
"2026-03-01T09:30:00Z"
"2026-03-01"
"01/03/2026"
"03/01/2026"
```

do not offer the same level of clarity. ISO 8601 with a timezone like `Z` or an explicit offset is the best choice for representing an instant. A string like `"01/03/2026"` is ambiguous between March 1 and January 3.

When you need to parse custom formats or specified timezones, use `$dateFromString` with `format`, `timezone`, `onError`, and `onNull` as appropriate:

```javascript
db.legacyOrders.aggregate([
  {
    $project: {
      legacyDate: 1,
      parsedAt: {
        $dateFromString: {
          dateString: "$legacyDate",
          format: "%d/%m/%Y %H:%M:%S",
          timezone: "Asia/Ho_Chi_Minh",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Here `$dateFromString` interprets the string according to the specified day/month/year format and timezone. Do not arbitrarily pass `timezone` if the input string already includes a timezone in a way that conflicts with the expression. When simply converting valid ISO strings, `$toDate` or `$convert` is more concise.

## 12. Converting to Boolean: $toBool Can Be Surprising

In many systems, legacy data contains:

```javascript
{ isActive: "true" }
{ isActive: "false" }
{ isActive: 0 }
{ isActive: 1 }
{ isActive: "" }
{ isActive: null }
```

You might expect `$toBool: "false"` to yield `false`. However, **do not think in terms of natural-language string parsing**.

Common Boolean conversion rules:

- Numeric value equal to `0` → `false`;
- Non-zero numeric value → `true`;
- Booleans keep their corresponding meaning;
- Null/missing → `null`;
- Non-null values of other types, **including empty Strings and the string `"false"`**, typically convert to `true` under `$toBool` semantics.

Example:

```javascript
db.boolLab.insertMany([
  { _id: "A", raw: false },
  { _id: "B", raw: true },
  { _id: "C", raw: 0 },
  { _id: "D", raw: 5 },
  { _id: "E", raw: "false" },
  { _id: "F", raw: "" },
  { _id: "G", raw: null },
  { _id: "H" }
]);

db.boolLab.aggregate([
  {
    $project: {
      _id: 1,
      original: "$raw",
      rawType: { $type: "$raw" },
      converted: { $toBool: "$raw" }
    }
  }
]);
```

The crucial point is that E and F are **not** parsed by string content to become `false`.

### 12.1. Parsing "true"/"false" Strings Intentionally

If the source only allows Strings `"true"`, `"false"`, or Booleans, build an expression that verifies values explicitly:

```javascript
db.boolLab.aggregate([
  {
    $project: {
      _id: 1,
      normalizedActive: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$raw", true] },
              then: true
            },
            {
              case: { $eq: ["$raw", false] },
              then: false
            },
            {
              case: { $eq: ["$raw", "true"] },
              then: true
            },
            {
              case: { $eq: ["$raw", "false"] },
              then: false
            }
          ],
          default: null
        }
      }
    }
  }
]);
```

If the source allows `"TRUE"`, `"False"`, or whitespace, you can normalize Strings using appropriate string expressions before comparing, while **checking the type** so string operations are not invoked on invalid Booleans or Numbers.

Do not use `$toBool` to "interpret" human-readable flag strings if the business requirement is accurate true/false parsing.

## 13. Building Normalization Pipelines That Preserve Error Trails

A quality ETL pipeline does not merely cast types. It should return:

- The original value;
- The original BSON type;
- The converted value;
- Status: **valid/invalid/missing/null**;
- Data source or ID for reconciliation.

Example checking `total` in `typeConversionLab`:

```javascript
db.typeConversionLab.aggregate([
  {
    $set: {
      originalTotalType: { $type: "$total" },
      totalDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      totalStatus: {
        $switch: {
          branches: [
            {
              case: {
                $eq: ["$originalTotalType", "missing"]
              },
              then: "MISSING"
            },
            {
              case: {
                $eq: ["$originalTotalType", "null"]
              },
              then: "NULL"
            },
            {
              case: {
                $eq: ["$totalDecimal", null]
              },
              then: "INVALID"
            }
          ],
          default: "VALID"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      total: 1,
      originalTotalType: 1,
      totalDecimal: 1,
      totalStatus: 1
    }
  }
]);
```

Advantages:

- Valid numeric strings are converted;
- Malformed strings do not crash the entire pipeline;
- Null fields are distinct from missing fields in the output status;
- When `totalDecimal` is `null` due to a conversion error, `totalStatus` reflects `INVALID`;
- Original information is not discarded before reconciliation.

If the schema contains Decimal128 `NaN`, `Infinity`, or special values accepted by MongoDB in certain conversions, business logic must also **check finiteness and value bounds**; "type conversion succeeded" does not equate to "valid price."

### 13.1. Counting Documents by Data Quality

```javascript
db.typeConversionLab.aggregate([
  {
    $set: {
      originalType: { $type: "$total" },
      normalized: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      status: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$originalType", "missing"] },
              then: "MISSING"
            },
            {
              case: { $eq: ["$originalType", "null"] },
              then: "NULL"
            },
            {
              case: { $eq: ["$normalized", null] },
              then: "INVALID"
            }
          ],
          default: "VALID"
        }
      }
    }
  },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Such statistics help plan migrations based on the real scale of bad data, rather than merely discovering that a total revenue aggregation is wrong.

## 14. Summing Only Over Validly Converted Values

Suppose you want to sum `total` across mixed-type data.

A safer approach for reporting is to isolate validly converted values first:

```javascript
db.typeConversionLab.aggregate([
  {
    $set: {
      totalDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $match: {
      totalDecimal: { $ne: null }
    }
  },
  {
    $group: {
      _id: null,
      totalRevenue: {
        $sum: "$totalDecimal"
      },
      includedCount: { $sum: 1 }
    }
  }
]);
```

This command sums the values convertible to Decimal128 and counts the participating documents.

**Interpretation warning:** invalid/missing/null records were excluded. If a financial report must cover all orders, handle or explicitly report the excluded record count; never label the result as "total revenue" when source data is incomplete.

### 14.1. Do Not Mask Errors with 0 When 0 Has Business Meaning

Using:

```javascript
{
  $convert: {
    input: "$total",
    to: "decimal",
    onError: NumberDecimal("0"),
    onNull: NumberDecimal("0")
  }
}
```

turns every error/null value into a monetary amount of `0`. While occasionally valid (e.g., a statistic where missing is defined as `0`), in revenue reporting it typically **masks errors**.

Separate the normalized value from the validity status, and choose a default of `0` only when officially defined by business rules.

## 15. Converting Arrays with $map Instead of Casting the Entire Array to Number

Suppose a collection stores sequences of numbers as Strings:

```javascript
db.measurements.insertOne({
  _id: "M-01",
  rawValues: ["10.5", "12.25", "bad", null, "15"]
});
```

To convert each element:

```javascript
db.measurements.aggregate([
  {
    $project: {
      convertedValues: {
        $map: {
          input: "$rawValues",
          as: "value",
          in: {
            $convert: {
              input: "$$value",
              to: "double",
              onError: null,
              onNull: null
            }
          }
        }
      }
    }
  }
]);
```

Conceptual result:

```javascript
{
  _id: "M-01",
  convertedValues: [10.5, 12.25, null, null, 15]
}
```

A common mistake is applying `$toDouble: "$rawValues"` directly to the entire array. That does not automatically map each element to Double. Use `$map`.

### 15.1. Preserving Both Original Value and Parse Status

```javascript
db.measurements.aggregate([
  {
    $project: {
      parsed: {
        $map: {
          input: "$rawValues",
          as: "v",
          in: {
            original: "$$v",
            originalType: { $type: "$$v" },
            asDouble: {
              $convert: {
                input: "$$v",
                to: "double",
                onError: null,
                onNull: null
              }
            }
          }
        }
      }
    }
  }
]);
```

The output for each element is an object containing the original value, original type, and conversion result. When an invalid element exists, the application can pinpoint the error instead of seeing an unexplained null.

### 15.2. $map with Non-Array Fields

If `rawValues` is sometimes a String or Object, `$map` can throw an error. Check `$isArray` first:

```javascript
db.measurements.aggregate([
  {
    $project: {
      parsed: {
        $cond: {
          if: { $isArray: "$rawValues" },
          then: {
            $map: {
              input: "$rawValues",
              as: "v",
              in: {
                $convert: {
                  input: "$$v",
                  to: "double",
                  onError: null,
                  onNull: null
                }
              }
            }
          },
          else: []
        }
      }
    }
  }
]);
```

Defaulting to `[]` here is merely an illustrative fallback policy. In ETL, distinguish a "valid empty array" from a "wrong type" if it affects reporting.

## 16. Type Conversion Inside $match with $expr

Sometimes you need to filter documents whose String values represent numbers greater than 100:

```javascript
db.legacyPrices.aggregate([
  {
    $set: {
      parsedPrice: {
        $convert: {
          input: "$price",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $match: {
      parsedPrice: {
        $gt: NumberDecimal("100")
      }
    }
  }
]);
```

Or using `$expr`:

```javascript
db.legacyPrices.find({
  $expr: {
    $gt: [
      {
        $convert: {
          input: "$price",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      NumberDecimal("100")
    ]
  }
});
```

Both express "convert the value before comparing," but recognize that the query has become a **computation over raw source data**.

### 16.1. Impact on Indexes

Suppose there is a B-tree index:

```javascript
db.legacyPrices.createIndex({ price: 1 });
```

This index sorts by the **original BSON value**, not by the Decimal128 value after conversion. If the data contains `price: "100"`, `price: "9"`, and `price: "200"`, String lexicographical order differs from Numeric order.

Therefore, the condition:

```javascript
{
  $expr: {
    $gt: [
      { $toDecimal: "$price" },
      NumberDecimal("100")
    ]
  }
}
```

**does not automatically become an efficient range scan on the `{ price: 1 }` index**. MongoDB may have to read and evaluate the expression across many documents. Certain `$expr` expressions can receive specific index optimizations depending on query shape and server version, but do not assume `$convert` on a field will leverage the raw index as though the field were already Decimal128.

Sustainable solution for frequent queries:

1. Normalize the field on the **write path**;
2. Migrate legacy data to a consistently typed field;
3. Create an index on the normalized field;
4. Filter directly on the normalized field.

Example schema after migration:

```javascript
{
  _id: "P-101",
  priceRaw: "125.50",
  priceDecimal: NumberDecimal("125.50")
}
```

Index:

```javascript
db.products.createIndex({ priceDecimal: 1 });
```

Query:

```javascript
db.products.find({
  priceDecimal: { $gt: NumberDecimal("100") }
});
```

This avoids parsing the entire dataset on every read request.

### 16.2. Using a Pre-Filter Without Changing Semantics

With mixed data, a type-based filter step can reduce the number of records needing conversion:

```javascript
db.legacyPrices.aggregate([
  {
    $match: {
      price: { $type: "string" }
    }
  },
  {
    $set: {
      priceDecimal: {
        $convert: {
          input: "$price",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

However, this command **excludes all `price` values that are already Number/Decimal128**. Thus it is only valid if the goal is specifically to process String fields. Do not add a pre-filter as an optimization if it drops valid data required by business logic.

## 17. Normalizing Data on Write and Migrations

Conversions in aggregation **do not automatically modify stored documents**. A pipeline:

```javascript
db.typeConversionLab.aggregate([
  {
    $set: {
      totalDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

only creates/transforms fields in the pipeline's output; the source documents do not gain a new `totalDecimal` unless an appropriate write operation is used.

### 17.1. Updating with an Aggregation Pipeline

MongoDB supports update pipelines to convert and store normalized fields:

```javascript
db.typeConversionLab.updateMany(
  {},
  [
    {
      $set: {
        totalDecimal: {
          $convert: {
            input: "$total",
            to: "decimal",
            onError: null,
            onNull: null
          }
        }
      }
    }
  ]
);
```

**Caution:** this command can write `totalDecimal: null` onto invalid/missing records. If policy requires routing faulty records to quarantine instead of writing `null`, split into batches with appropriate filters.

Converting only parseable numeric Strings without destroying original data is a multi-step migration workflow:

1. Inspect and tally `$type` statistics for the field;
2. Test `$convert` with `onError`/`onNull` to identify faulty data;
3. Export the list of records needing repair/owner intervention;
4. Run batched updates with explicit filters over eligible records;
5. Verify affected record counts and reconcile totals;
6. Enable schema validation/write-path normalization to prevent recurrence.

Per lesson guidelines, this is an **illustrative** workflow, not an instruction to run updates across production without backups and a migration plan.

### 17.2. $merge and $out Must Be Understood as Data Writes

Pure aggregation stages like `$project`/`$set` only produce output. However, `$merge` or `$out` stages can **write results into a target collection**. When designing ETL, distinguish read-only pipelines from side-effecting pipelines, decide upsert/replace policies, and restrict permissions.

Do not add `$merge` to an exploratory pipeline without specifying the target collection, uniqueness constraints, error handling, and rollback plan.

### 17.3. Post-Migration Validation

After normalization:

- Monetary fields should consistently use BSON Decimal128 or integers in minor currency units;
- Date fields should consistently use BSON Date;
- Identifier fields should consistently use ObjectId/String per schema;
- Quantity fields should be Int32/Int64 within allowed bounds;
- Boolean fields should contain real Booleans, not the String `"false"`;
- Null/missing rules must be explicit.

MongoDB JSON Schema validators and application-layer validation can block wrong-type writes. However, import pipelines and background jobs must follow the same schema so the web API isn't clean while ETL continues writing mismatched types.

## 18. Usage in Java and Spring Data MongoDB

A Java application may store money using `BigDecimal` (mapped to Decimal128 under proper configuration), timestamps using appropriate Java time types, and identifiers using `ObjectId`. Yet legacy data may have been written by multiple clients, so aggregation normalization is still useful.

### 18.1. MongoDB Java Driver: Building Stages with Document

Example building a price-checking and conversion pipeline:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

MongoCollection<Document> orders =
    database.getCollection("typeConversionLab");

Document conversion = new Document(
    "$convert",
    new Document("input", "$total")
        .append("to", "decimal")
        .append("onError", null)
        .append("onNull", null)
);

Document projection = new Document(
    "$project",
    new Document("_id", 1)
        .append("originalType",
            new Document("$type", "$total"))
        .append("totalDecimal", conversion)
);

List<Document> pipeline = Arrays.asList(projection);

for (Document result : orders.aggregate(pipeline)) {
    System.out.println(result.toJson());
}
```

This example uses `Document` directly to make the JSON/BSON expression clear. The Java Driver also provides aggregation builders, though support for individual expressions/options depends on driver version. In real implementations, use consistent helpers/abstractions to avoid mistyping operator names across files.

### 18.2. Return Types in Java Must Be Controlled

Even when MongoDB returns BSON Decimal128 properly, Java code may read it as a `Decimal128` wrapper or mapped object depending on configuration. Do not blindly cast values to `double` and then back to `BigDecimal` when monetary precision matters.

Similarly, BSON Date represents an instant in time; Java code must handle timezones and representation consistently. Formatting a date for display differs from storing an instant.

### 18.3. Spring Data MongoDB

Spring Data MongoDB provides DSLs for aggregation, projection, conversion, or custom expressions depending on version. Raw expressions can be used when the builder API lacks a method, but verify mapped field names and DTO output types.

For read models, use strongly typed DTOs:

```java
public record NormalizedOrder(
    String id,
    java.math.BigDecimal total,
    java.time.Instant orderedAt,
    String validationStatus
) {}
```

This is an example application-layer model. Mapping from BSON ObjectId/Decimal128/Date to a DTO depends on serializers and configuration; do not assume the Java code above will automatically map every field if source data still has wrong types.

## 19. Common Mistakes

| Mistake | Consequence | How to Handle |
|---|---|---|
| Thinking `$type` converts values | Only returns the BSON type name | Use `$convert` or shortcuts |
| Treating `"123"` like a BSON Number | Numeric operations may error or change semantics | Convert numbers intentionally |
| Confusing `null` with `missing` | Fails to detect legacy missing-field defects | Combine with `$type` |
| Using `$toInt` on string `"3.5"` | Pipeline fails | Use `$convert` with `onError` or parse per rules |
| Using `$toInt` for rounding | May truncate instead of round | Use `$ceil`/`$floor`/`$round` per business rules |
| Casting large Int64 to Double | Loss of integer precision | Keep Int64/Decimal128 |
| Using Double for exact currency | Binary floating-point error | Use Decimal128 or integer minor units |
| Using `$toBool` on `"false"` | Can evaluate to `true` | Parse strings with `$switch`/comparisons |
| Using `$toDate` with epoch seconds | Wrong timestamps (1970) | Multiply to milliseconds first |
| Using ambiguous date strings | Wrong locale/timezone parsing | `$dateFromString` with format/timezone |
| Using `$toObjectId` on arbitrary user IDs | Errors because not 24-char hex | Keep String ID or convert with `onError` |
| Casting an entire array with `$toDouble` | Does not map elements automatically | Use `$map` |
| Setting `onError: 0` for revenue | Masks invalid records | Record error state and reconcile |
| Using `$expr + $convert` on every query | Can reduce index effectiveness | Normalize schema, index normalized fields |
| Thinking `$set` in aggregation saves to DB | Only transforms pipeline output | Use an update pipeline or controlled write stage |
| Thinking successful conversion = valid data | Values can still be out of range, negative, or illogical | Business validation after conversion |

## 20. Practice Exercises

### Exercise 1 — Surveying Legacy Data Types

On `typeConversionLab`:

1. Use `$project` and `$type` to display the types of `total`, `quantity`, and `orderedAt`.
2. Distinguish `"null"` from `"missing"`.
3. Use `$group` to count how many documents have each `total` type.
4. Explain why `"85000.75"` and `"unknown"` have the same type yet differ in convertibility.

### Exercise 2 — Converting quantity to Integer

Try:

```javascript
{ $toInt: "$quantity" }
```

and:

```javascript
{
  $convert: {
    input: "$quantity",
    to: "int",
    onError: null,
    onNull: null
  }
}
```

Compare behavior when `quantity` is `2`, `"3"`, `"3.5"`, `null`, and missing. Explain why one pipeline can fail completely while the other returns results containing `null`.

### Exercise 3 — Calculating Revenue After Normalization

Use `$convert` to `"decimal"` to create `totalDecimal`. Write a pipeline to:

1. Preserve the original `total` value.
2. Assign `totalStatus` = `VALID`/`INVALID`/`NULL`/`MISSING`.
3. Sum only `VALID` values.
4. Count `INVALID` and `MISSING` documents separately.
5. Propose how to prevent the report from being misinterpreted as covering all orders completely.

### Exercise 4 — Dates, Timezones, and Epochs

Data:

```javascript
[
  { _id: 1, rawTime: "2026-03-01T08:30:00Z" },
  { _id: 2, rawTime: NumberLong("1772353800000") },
  { _id: 3, rawTime: "01/03/2026 15:30:00" },
  { _id: 4, rawTime: "yesterday" }
]
```

Tasks:

1. Use `$convert` to `"date"` with `onError`/`onNull`.
2. Choose a solution to parse `dd/MM/yyyy HH:mm:ss` in timezone `Asia/Ho_Chi_Minh`.
3. Explain how to distinguish epoch seconds from milliseconds.
4. Explain why date strings lacking a timezone can lead to wrong stored times.

### Exercise 5 — Converting Customer IDs

Given `customerId` values that are ObjectIds, valid hex Strings, invalid Strings, and `null`. Use `$type` to classify and `$convert` to `"objectId"` for safe conversion. Write a `$lookup` aggregation against a `customers` collection whose `_id` is ObjectId. Analyze index impact and why migrating the schema to a consistent type is advisable.

### Exercise 6 — Understanding $toBool Properly

Predict the output of:

```javascript
[
  { raw: false },
  { raw: 0 },
  { raw: 1 },
  { raw: "false" },
  { raw: "" },
  { raw: null }
]
```

when using `$toBool`. Then write a pipeline using `$switch` to parse Strings `"true"`/`"false"` by content. Why should `$toBool` not be used directly on legacy String flags?

### Exercise 7 — Converting Arrays

Data:

```javascript
{
  rawValues: ["1.5", "bad", "3", null]
}
```

Write `$map` combined with `$convert` to `"double"` to produce a converted array and a corresponding status array. If `rawValues` is occasionally not an array, add `$isArray` to avoid errors.

### Exercise 8 — Query Optimization After Migration

A collection has one million products with `price` mixing Strings and Decimal128. An API filters prices greater than 100. Compare:

- A query using `$expr` and `$toDecimal` across all documents;
- A query on a normalized `priceDecimal` field with a B-tree index.

Explain why the second approach usually has better range-scan optimization potential, and what migration/field-maintenance costs must be accounted for.

## 21. MongoDB Reference Documentation

- [Aggregation Expressions](https://www.mongodb.com/docs/manual/reference/mql/expressions/)
- [Aggregation $type Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/)
- [Query $type Operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/)
- [Aggregation $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [Aggregation $toInt](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toInt/)
- [Aggregation $toLong](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toLong/)
- [Aggregation $toDouble](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDouble/)
- [Aggregation $toDecimal](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDecimal/)
- [Aggregation $toString](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toString/)
- [Aggregation $toDate](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDate/)
- [Aggregation $toBool](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toBool/)
- [Aggregation $toObjectId](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toObjectId/)
- [Aggregation $dateFromString](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateFromString/)
- [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)

## Conclusion

When MongoDB data can contain multiple BSON types, the first step is to **accurately inspect the stored types** with `$type`. This expression distinguishes String from Number, Date from date string, ObjectId from hex string, and especially `null` from a `missing` field.

**`$convert`** solves controlled type conversion: `input` specifies the value, `to` specifies the target type, `onError` handles conversion failures, and `onNull` handles null/missing values. Shortcuts **`$toInt`, `$toLong`, `$toDouble`, `$toDecimal`, `$toString`, `$toDate`, `$toBool`, and `$toObjectId`** make code shorter when inputs are guaranteed valid, but lack flexible fallback mechanisms like `$convert`.

Successful type conversion **does not yet mean business-valid data**: you must still verify value ranges, monetary signs, Decimal128 precision, timezones, Boolean formatting, and migration failure handling. For frequently executed queries, storing consistent types from the start and indexing normalized fields is usually far more reliable than converting every record on every read. A strong pipeline does not just return new values—it helps identify, tally, and reconcile documents that could not be converted cleanly.
