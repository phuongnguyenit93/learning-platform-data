# Numeric Types int32, int64, double, and Decimal128 in MongoDB

In BSON, a value representing a "number" does not have just a single type. MongoDB supports four commonly used numeric types: **int32**, **int64 (long)**, **double**, and **Decimal128**. They differ in range, representation, precision, storage size, and how applications manipulate the data. Choosing the wrong type can cause monetary amounts to drift by small fractions, large counters to lose digits, or applications to inadvertently convert exact integers into approximate floating-point values.

This lesson focuses on BSON numeric types, how to construct and inspect them in **mongosh**, their comparison/query/arithmetic behavior, safe type conversions, and how they map to Java.

## 1. What Is BSON and Why Are There Multiple Numeric Types?

**BSON (Binary JSON)** is the binary document format used by MongoDB. Unlike standard JSON, which has only a single syntactic number type, BSON attaches a **type code** to each value. Therefore, two documents with the same mathematical value but different BSON types can be stored distinctly:

~~~javascript
{ value: Int32(42) }
{ value: Long("42") }
{ value: Double(42) }
{ value: Decimal128("42") }
~~~

All of these documents represent the number 42; however, applications and MongoDB can inspect the different BSON types stored in each field.

| BSON Type | BSON Code | Alias Used with `$type` | Value Size | Nature |
| --- | ---: | --- | ---: | --- |
| **int32** | 16 | `"int"` | 4 bytes | 32-bit signed integer |
| **int64 / long** | 18 | `"long"` | 8 bytes | 64-bit signed integer |
| **double** | 1 | `"double"` | 8 bytes | IEEE 754 64-bit binary floating-point number |
| **Decimal128** | 19 | `"decimal"` | 16 bytes | IEEE 754 decimal128 floating-point decimal number |

The sizes in the table account only for the **numeric value**; a BSON field also includes a type identifier byte, field name, and other document overhead. Do not use this table alone to deduce the total document size.

**Core distinction:** int32 and int64 store **exact integers** within their ranges; double stores **approximate base-2 floating-point numbers**; Decimal128 stores **decimal numbers with up to 34 significant digits**. Decimal128 has finite precision, so it is not arbitrary-precision arithmetic.

## 2. Comparing Range and Precision

| Criterion | int32 | int64 (long) | double | Decimal128 |
| --- | --- | --- | --- | --- |
| Range | −2,147,483,648 to 2,147,483,647 | −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | Finite numbers up to approx. 1.797 × 10³⁰⁸; includes ±Infinity, NaN | Up to 34 significant digits, very wide exponent range; can represent NaN/Infinity |
| Precision | Every integer in range | Every integer in range | Approx. 15–17 significant decimal digits; inexact for most decimal fractions such as 0.1 | Exact for decimal values representable within 34 significant digits |
| Integer precision | Full range | Full range | Contiguously exact from −2⁵³ to 2⁵³; larger values may skip odd integers | Integers within 34 significant digits |
| Use cases | Small quantities, age, numeric status codes, small counters | Very large counters, integer IDs, byte sizes | Measurements, ratios, statistics tolerant of rounding error | Currency, tax, unit prices, rates requiring deterministic decimal arithmetic |

### 2.1. int32: 32-Bit Integer

Int32 is a **signed** integer. The maximum value is **2³¹ − 1**, and the minimum value is **−2³¹**.

Appropriate examples:

- Number of items in an order.
- Remaining retry attempts.
- Priority levels within a bounded range.
- Years or quantities guaranteed never to exceed the int32 range.

If a system might increment a counter past 2,147,483,647, consider int64 or a separate strategy. Naming a field **count** does not automatically mean int32 is sufficient.

### 2.2. int64 (long): 64-Bit Integer

Int64 expands the range while still representing **every integer exactly** within its bounds. Use it when values can exceed the int32 limit: cumulative view counts, storage sizes in bytes, monotonic counters, or large integer identifiers.

JavaScript, however, uses **Number** (double) for regular numbers. You must never assume from the size of the int64 range that any int64 value can be passed safely through a `Number` variable. For example:

~~~javascript
// Run in mongosh (JavaScript):
Number.MAX_SAFE_INTEGER;              // 9007199254740991
Number.isSafeInteger(9007199254740991); // true
Number.isSafeInteger(9007199254740993); // false

// Correct: pass a decimal string to preserve the large value exactly.
const exactLong = Long("9007199254740993");

// Dangerous: the Number argument is already rounded before Long receives it.
const unsafeLong = Long(9007199254740993);
~~~

**Rule:** when writing 64-bit integers that may exceed **Number.MAX_SAFE_INTEGER = 2⁵³ − 1**, pass them as a **string** or via the driver's **Long** object instead of going through a JavaScript `Number`.

### 2.3. double: Binary Floating-Point Number

Double fits scientific calculations, measurements, and metrics where rounding tolerance is controlled. Double stores sign, significand, and exponent in base 2. Because **0.1** has no finite representation in base 2, arithmetic can produce surprising results:

~~~javascript
0.1 + 0.2;                // 0.30000000000000004
0.1 + 0.2 === 0.3;        // false
~~~

This is a property of **IEEE 754 binary64**, not a bug specific to MongoDB. Temperature readings or statistical outputs typically tolerate tiny errors. Conversely, comparing payment totals derived from double addition can introduce logic bugs.

Large integers are another hazard with double: beyond **2⁵³ − 1**, consecutive integers can no longer all be distinguished. A number that looks like an "integer" in JSON or JavaScript may still be stored as a double.

### 2.4. Decimal128: 128-Bit Decimal Floating-Point Number

Decimal128 follows **IEEE 754 decimal128**, representing numbers in base 10 with **34 significant digits** and a specification exponent range of roughly **−6143 to +6144**. Values such as **0.1**, **0.2**, and **19.99** can be represented exactly in decimal as long as the digit count does not exceed the limit.

Common examples:

~~~javascript
Decimal128("0.1")
Decimal128("19.99")
Decimal128("12345678901234567890.01")
~~~

Pass strings to preserve exact decimal intent. If you construct Decimal128 from an already-rounded JavaScript number, the target type cannot recover the original value.

Decimal128 is not a silver bullet for every calculation: operations whose results exceed 34 significant digits still undergo rounding; values exceeding the range can raise errors or yield infinity depending on the operation. For currency, applications still need to define the **unit**, **number of decimal places**, and business **rounding rules**.

## 3. Creating and Inspecting Each Type in mongosh

### 3.1. Setting Up a Demo Collection

The following examples run in **mongosh** connected to a running MongoDB instance. Use a dedicated collection for this lesson so other data is unaffected:

~~~javascript
const lab = db.getSiblingDB("bson_numeric_lab");
lab.numeric_examples.drop();

lab.numeric_examples.insertMany([
  { _id: "int32",    value: Int32(42) },
  { _id: "int64",    value: Long("9007199254740993") },
  { _id: "double",   value: Double(0.1) },
  { _id: "decimal",  value: Decimal128("0.10") }
]);

lab.numeric_examples.find().sort({ _id: 1 }).toArray();
~~~

The recommended constructors in **mongosh** are:

| Type | Explicit Constructor | Legacy Names Still Commonly Seen |
| --- | --- | --- |
| int32 | `Int32(42)` | `NumberInt(42)` |
| int64 | `Long("9007199254740993")` | `NumberLong("9007199254740993")` |
| double | `Double(0.1)` | — |
| Decimal128 | `Decimal128("0.10")` | `NumberDecimal("0.10")` |

**Note on mongosh vs. legacy mongo shell:** in modern mongosh, JavaScript numbers that are integers within the int32 range are typically written as **Int32**; numbers not representable as int32 are typically written as **Double**. The shell **does not automatically choose int64** for an oversized integer. The legacy **mongo** shell defaulted to writing numbers as double. Always use explicit constructors when the storage type is part of your data contract.

### 3.2. Checking the Stored Type

MongoDB provides the aggregation operator **`$type`**, which returns the actual BSON type name of a value:

~~~javascript
lab.numeric_examples.aggregate([
  {
    $project: {
      _id: 1,
      value: 1,
      bsonType: { $type: "$value" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

The expected **bsonType** values are **decimal**, **double**, **int**, and **long** for the documents above, respectively.

The **`$type`** operator in **find** also filters by type:

~~~javascript
lab.numeric_examples.find({ value: { $type: "int" } });
lab.numeric_examples.find({ value: { $type: "long" } });
lab.numeric_examples.find({ value: { $type: "double" } });
lab.numeric_examples.find({ value: { $type: "decimal" } });

// Alias matching all four BSON numeric types:
lab.numeric_examples.find({ value: { $type: "number" } });
~~~

Using **`$type: "number"`** is handy when you want to exclude strings, nulls, or booleans without yet distinguishing among numeric types. For data already stored with mixed types, inspect each type before designing a migration.

## 4. Does Value Equality Mean Type Equality?

MongoDB can **compare values across BSON numeric types**. When two numbers of different types represent the exact same mathematical value, an equality condition can match both. However, **`$type`** still distinguishes the stored type.

Create four documents holding the value one:

~~~javascript
lab.numeric_equal.drop();
lab.numeric_equal.insertMany([
  { _id: "a", value: Int32(1) },
  { _id: "b", value: Long("1") },
  { _id: "c", value: Double(1) },
  { _id: "d", value: Decimal128("1.00") }
]);

// Query by value: can match all four documents.
lab.numeric_equal.find({ value: 1 }).toArray();

// Query specifically for documents stored as Decimal128.
lab.numeric_equal.find({ value: { $type: "decimal" } }).toArray();
~~~

For decimal fractions, **double** and **Decimal128** may not compare equal even if they look identical when printed, because double stores a binary approximation:

~~~javascript
lab.numeric_fraction.drop();
lab.numeric_fraction.insertMany([
  { _id: "double", value: Double(1.01) },
  { _id: "decimal", value: Decimal128("1.01") }
]);

lab.numeric_fraction.find({
  value: Double(1.01)
}).toArray();

// Do not assume that Decimal128("1.01")
// will match a Double(1.01) predicate.
~~~

Implication: **value equality** and **type verification** are two separate concerns. If a **price** field must always be Decimal128, a normal equality query does not guarantee every document was stored with the right type; you need write conventions, schema validation, and/or `$type` checks.

## 5. Arithmetic: Precision and Type Promotion

### 5.1. Comparing Addition with double and Decimal128

Perform addition **on MongoDB** using aggregation so operands retain their BSON types:

~~~javascript
lab.numeric_examples.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      doubleSum: {
        $add: [Double(0.1), Double(0.2)]
      },
      decimalSum: {
        $add: [Decimal128("0.1"), Decimal128("0.2")]
      },
      doubleType: { $type: Double(0.1) },
      decimalType: { $type: Decimal128("0.1") }
    }
  }
]);
~~~

You will observe that the double result may display the approximation **0.30000000000000004**, while the Decimal128 addition yields the exact decimal **0.3** in this example.

**Do not test addition using JavaScript's `+` operator directly on two Decimal128 objects** and treat it as MongoDB decimal addition. JavaScript's operator follows JavaScript type coercion rules; for real calculations, use MongoDB aggregation or an appropriate decimal type in your application language.

### 5.2. Type Promotion Rules of `$sum`

With **`$sum`** in aggregation, when inputs mix types, MongoDB follows an ascending range hierarchy:

~~~text
int32 → int64 → double → Decimal128
~~~

This rule **determines the result type of the addition**, which does not mean every promotion preserves absolute precision:

- Adding **int32** values that exceed the int32 range may promote the result to **int64**.
- When an **int64** result overflows its range, MongoDB may promote it to **double**, risking loss of integer precision.
- When a double or Decimal128 result overflows its range, the sum can become **±Infinity**.
- If you mix an already-rounded double with a decimal, later promotion will not recover the previously lost precision.

Example calculating revenue with Decimal128:

~~~javascript
lab.orders.drop();
lab.orders.insertMany([
  { _id: 1, price: Decimal128("19.90") },
  { _id: 2, price: Decimal128("10.10") }
]);

lab.orders.aggregate([
  {
    $group: {
      _id: null,
      total: { $sum: "$price" },
      count: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      total: 1,
      count: 1,
      totalType: { $type: "$total" }
    }
  }
]);
~~~

The **total** field has decimal value **30.00** and type **decimal**. Displayed trailing zeros may vary, but the arithmetic value is 30.

To keep data clean, avoid inserting **some prices as Decimal128 and others as double** and relying on MongoDB's automatic promotion. Aggregations should start from data with consistent units and types.

### 5.3. When Is Rounding Needed?

Even Decimal128 cannot decide on its own whether currency should be rounded to two or four decimal places. Depending on business requirements, MongoDB can use **`$round`** or **`$trunc`**, or a Java application can use **`BigDecimal.setScale(...)`** with an appropriate **`RoundingMode`**.

Example rounding a decimal value to two decimal places:

~~~javascript
lab.numeric_examples.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      rounded: {
        $round: [Decimal128("12.345"), 2]
      }
    }
  }
]);
~~~

Note that MongoDB's **`$round`** uses **round half to even** for exact midpoint ties. Accounting or tax rules may differ; specify the required rounding mode before implementation.

## 6. Converting Between Numeric Types

MongoDB supports the following expressions:

| Aggregation Operator | Intended Result | Risks to Control |
| --- | --- | --- |
| `$toInt` | int32 | Errors if out of range; fractional part is truncated when converting from supported numeric types |
| `$toLong` | int64 | Errors if out of range; fractional part is truncated |
| `$toDouble` | double | May lose precision when converting from long or decimal |
| `$toDecimal` | Decimal128 | Does not restore original value from an already-rounded double |
| `$convert` | Specified type | Can configure `onError` and `onNull` for dirty input data |

Example converting decimal strings to Decimal128 while handling invalid values without aborting the entire pipeline:

~~~javascript
lab.raw_prices.drop();
lab.raw_prices.insertMany([
  { _id: 1, raw: "12.50" },
  { _id: 2, raw: "7.30" },
  { _id: 3, raw: "invalid" },
  { _id: 4, raw: null }
]);

lab.raw_prices.aggregate([
  {
    $project: {
      _id: 1,
      raw: 1,
      value: {
        $convert: {
          input: "$raw",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
~~~

The first two documents yield **Decimal128("12.50")** and **Decimal128("7.30")**; the remaining two have **value: null**. In production workflows, quarantine bad records to fix the data source rather than defaulting unparseable values to zero.

If the input is already known to be clean, you can use the shorthand:

~~~javascript
lab.raw_prices.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      original: "$raw",
      decimalValue: { $toDecimal: "$raw" }
    }
  }
]);
~~~

**Converting `Double(0.1)` to Decimal128 is not the same as parsing the string `"0.1"` directly into Decimal128.** Double stores an approximation; converting after storage generally cannot reconstruct the exact decimal input the user originally provided. Convert directly from an exact string or `BigDecimal` representation at data ingestion if exact decimal semantics are required.

## 7. Extended JSON: Preserving Types During Data Exchange

Plain JSON has no syntax to distinguish int32, int64, double, and Decimal128. MongoDB provides **Extended JSON (EJSON) v2** to describe BSON types inside JSON strings. In **Canonical** mode, the four numeric types look like:

~~~json
{
  "i32": { "$numberInt": "42" },
  "i64": { "$numberLong": "9007199254740993" },
  "dbl": { "$numberDouble": "0.1" },
  "dec": { "$numberDecimal": "0.10" }
}
~~~

Distinguishing the two modes:

- **Canonical EJSON:** prioritizes preserving type information; useful for data tests, round-trip data exchange, and export/import requiring exact BSON types.
- **Relaxed EJSON:** prioritizes readability; int32, int64, or finite double values may appear as regular JSON numbers, so numeric sub-types are not guaranteed to survive an arbitrary JSON parser.

Example generating EJSON for a document retrieved from MongoDB:

~~~javascript
const sample = lab.numeric_examples.findOne({ _id: "int64" });

// Canonical EJSON preserves the Long type tag:
EJSON.stringify(sample, null, 2, { relaxed: false });
~~~

When passing data through a plain JSON REST API, a JavaScript consumer may parse a large integer into a `Number` and lose digits. Interfaces that must preserve exact longs typically transmit them as **strings** or **EJSON** and reconstruct `Long`/`BigInt` according to the API contract. Do not assume arbitrary REST clients automatically understand EJSON keys without a decoding step.

## 8. Mapping BSON Numeric Types in Java

With the **MongoDB Java Driver**, the four types can be represented using their corresponding Java types:

| Java | Typical BSON Type Written | Notes |
| --- | --- | --- |
| `int` / `Integer` | int32 | Signed, 32-bit |
| `long` / `Long` | int64 | Signed, 64-bit, exact integer |
| `double` / `Double` | double | IEEE 754 binary64 |
| `org.bson.types.Decimal128` | Decimal128 | Constructed with `BigDecimal` |
| `java.math.BigDecimal` | Depends on codec/mapping configuration | Check the framework; do not assume every mapper writes Decimal128 |

Example using the Java Driver with explicit types:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.Decimal128;
import java.math.BigDecimal;

public class NumericTypesExample {
    public static void main(String[] args) {
        try (MongoClient client = MongoClients.create("mongodb://localhost:27017")) {
            MongoCollection<Document> collection = client
                    .getDatabase("bson_numeric_lab")
                    .getCollection("java_numeric_types");

            Document document = new Document("_id", "java-example")
                    .append("quantity", 42)                      // BSON int32
                    .append("totalBytes", 9007199254740993L)    // BSON int64
                    .append("measurement", 0.1d)                 // BSON double
                    .append("amount",
                            new Decimal128(new BigDecimal("19.90"))); // Decimal128

            collection.replaceOne(
                    new Document("_id", "java-example"),
                    document,
                    new com.mongodb.client.model.ReplaceOptions().upsert(true)
            );

            System.out.println(collection.find(
                    new Document("_id", "java-example")).first());
        }
    }
}
~~~

Explanation:

- The **L** suffix on the Java literal specifies a `long`; Java preserves **9007199254740993L** accurately.
- **0.1d** is an approximate binary floating-point number.
- **`new BigDecimal("19.90")`** builds a decimal value from a string. Avoid **`new BigDecimal(0.1)`** when you intend the exact decimal **0.1**, because that constructor captures the binary approximation of the `double`.
- **Decimal128** is limited to 34 digits; Java's **BigDecimal** can hold higher precision. Control conversions from `BigDecimal` to `Decimal128` when numbers exceed the target limits.

In **Spring Data MongoDB**, a Java **BigDecimal** field may need an explicit BSON target type declaration to avoid the framework's default conversion. For example:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public class ProductPrice {
    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

Actual mapping behavior depends on the Spring Data version and configured codecs/converters. When monetary fields require a strict contract, verify the stored BSON type using **`$type`**.

## 9. Choosing Types by Use Case

### 9.1. Quantities and Counters

**int32** is appropriate when the business domain guarantees values below 2³¹, such as item quantity on an order line. **int64** is appropriate for high-volume traffic counts, total processed messages, or file sizes in bytes. If a counter could conceivably exceed the `long` range in the distant future, design a specialized representation.

When executing the **`$inc`** update operator, monitor the stored type and overflow potential; do not assume values will always remain in their initial numeric type after many increments.

### 9.2. Unit Prices and Monetary Amounts

Two approaches are common:

1. **Decimal128:** store monetary amounts in the major currency unit (e.g., `Decimal128("125.50")`) and calculate in decimal; suitable for prices with fractional sub-units and explicit rounding requirements.
2. **int64 in minor units:** store **12,550 cents** instead of **125.50 currency units** if one major unit equals 100 minor units. Integer addition and subtraction are exact, though the application must manage scaling factors, overflow bounds, and currency rules.

Not every currency has two decimal places. Financial designs should store the **currency code** alongside the amount and define unit scaling consistently.

**Double is generally unsuitable for monetary values requiring exact reconciliation**. Even if the UI always rounds to two decimal places, inaccuracies can accumulate before display.

### 9.3. Measurements, Ratios, and Data Science

Double is typically the natural choice for temperatures, coordinates, sensor readings, model scores, percentages, and statistics. When comparing floating-point values, use an appropriate tolerance rather than always demanding exact equality.

For example, if a business rule checks "temperature between 20 and 30 degrees," a range query is usually much more meaningful than comparing a double result against a single fractional literal:

~~~javascript
lab.sensor_readings.find({
  temperature: { $gte: 20.0, $lte: 30.0 }
});
~~~

The **sensor_readings** collection here is an illustrative name for a telemetry application; it was not created in the earlier hands-on section.

### 9.4. When Should Numeric Types Be Normalized?

If an **amount** field contains int32 in some documents, double in others, and Decimal128 elsewhere, the application cannot easily guarantee consistent calculations. Choose a **canonical type at the write boundary**, run controlled migrations for legacy data, and apply MongoDB schema validation where appropriate.

Example validator requiring the **amount** field to be Decimal128 (not applied to the other example collections):

~~~javascript
lab.createCollection("decimal_only", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["amount"],
      properties: {
        amount: {
          bsonType: "decimal",
          description: "amount must be written as Decimal128"
        }
      }
    }
  }
});

lab.decimal_only.insertOne({
  amount: Decimal128("15.75")
});

// Rejected by the validator because the stored type is int32:
lab.decimal_only.insertOne({
  amount: Int32(15)
});
~~~

In production systems, evaluate **validationAction**, **validationLevel**, legacy records, and schema update policies before enabling validators. If the **decimal_only** collection already exists, use the validator modification mechanism instead of re-running **createCollection**.

## 10. Common Pitfalls

| Pitfall | Consequence | Mitigation |
| --- | --- | --- |
| "All JSON numbers are the same" | Type information is lost during serialization/deserialization | Use BSON constructors or Canonical EJSON when round-tripping is needed |
| "Integers beyond int32 automatically become long" | mongosh may write them as double, losing precision | Explicitly construct with `Long("...")` |
| "Double is fine if formatted to 2 decimal places" | Errors accumulate before display | Use Decimal128 or minor-unit integers for money |
| "Converting double to Decimal128 recovers the original value" | Input was already rounded earlier | Ingest directly from exact string or `BigDecimal` values |
| "Java BigDecimal always becomes Decimal128" | May be stored as a different BSON type if mapper config differs | Explicitly declare target type/codec and verify with `$type` |
| "Equal numbers share the same BSON type" | Querying for `1` can match int32, int64, double, and decimal | Use `$type` to distinguish types |
| "Decimal128 has infinite precision" | Rounding/overflow still occurs beyond 34 digits | Define scale, rounding rules, and range checks |
| "Any long fits cleanly in a JavaScript Number" | Digits are lost past the safe integer range | Use strings, `Long` objects, or safe `BigInt` APIs |

## 11. Self-Check Exercises

Using the **numeric_examples** collection created in Section 3, complete the following tasks:

1. Write an aggregation that outputs `_id`, `value`, and `$type` for each document. Clearly distinguish **long** and **double** even though both occupy 8 bytes of value storage.
2. Insert a document with `Long("9223372036854775807")`. Read it back without coercing to a JavaScript `Number` and explain why this is the upper bound of int64.
3. Compute `0.1 + 0.2` using double and using Decimal128 with `$add`. Observe the results and explain the role of the base representation.
4. Create two documents with **Decimal128("19.90")** and **Decimal128("10.10")**, use `$sum` to total them, and verify the result type with `$type`.
5. Convert the string `"42"` to int32, long, double, and decimal using the four conversion operators. Then test an invalid string to observe the difference between `$toDecimal` and `$convert` with `onError`.
6. Create documents holding `Int32(1)`, `Long("1")`, `Double(1)`, and `Decimal128("1")` and compare value-based queries against BSON-type queries.

Questions to answer for yourself: **Which type stores large integers accurately? Which type fits currency? When is Decimal128 needed? Why can't a post-hoc type conversion recover exact precision once data has been rounded?**

## 12. Takeaways for MongoDB Schema Design

Choosing numeric types is part of your **data contract**, not merely a storage optimization detail. Define value ranges, units, precision requirements, arithmetic/aggregation behavior, Java/JavaScript representations, and API transport formats when designing fields.

- Use **int32** for small integers with a bounded range.
- Use **int64** for large integers where every unit must remain exact.
- Use **double** for floating-point measurements tolerant of binary rounding error.
- Use **Decimal128** for decimal numbers requiring exact decimal representation and explicit rounding rules.

### Official References

- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — type codes, numeric type aliases, and BSON specifications.
- [mongosh Data Types](https://www.mongodb.com/docs/mongodb-shell/reference/data-types/) — creating Int32, Long, Double, Decimal128 and default mongosh numeric behavior.
- [Extended JSON (v2)](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/) — numeric representations in Canonical and Relaxed JSON.
- [`$sum` (accumulator)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/) — type promotion and overflow handling.
- [`$convert`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/) — conversion and error/null handling.
