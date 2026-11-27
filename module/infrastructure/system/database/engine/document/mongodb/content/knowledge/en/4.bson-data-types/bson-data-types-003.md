# Numeric Precision, Currency, and Data Type Conversion in MongoDB

## 1. Why Can Numeric Types Corrupt Data?

MongoDB stores documents in BSON (Binary JSON). BSON distinguishes multiple numeric types with different **precision, value ranges, and representations**. Seeing the same value on screen, such as `100`, does not mean those fields share the same BSON type or fit the same business requirements.

In systems storing prices, invoices, taxes, transaction counts, or identifiers, choosing the wrong type can lead to:

- Addition, multiplication, or comparison results drifting due to binary floating-point rounding.
- Digit loss when large integers pass through a JavaScript `Number` or a JSON layer that does not preserve types.
- String inputs failing to convert to numbers due to bad formatting, out-of-range values, or fractional parts.
- Documents in the same collection having an `amount` field with mixed `double`, `int`, `long`, and `decimal` types, complicating application logic, analytics, and data governance.
- Monetary amounts being rounded at the wrong step or with the wrong number of decimal places for the currency.

This lesson focuses on the four BSON numeric types, principles for representing currency, and **safe, controlled** type conversion techniques in `mongosh`, aggregation pipelines, and Java applications.

After this lesson, you will be able to inspect the actual BSON type of a field, select numeric types by range and business requirements, convert values using `$convert` and `$to...`, define rounding policies, and audit data before normalization.

## 2. Distinguishing BSON Numeric Types

| BSON Type | Typical Label from `$type` | Characteristics | Use Cases |
|---|---|---|---|
| **Int32** | `int` | 32-bit signed integer, from `-2,147,483,648` to `2,147,483,647` | Small counters, quantities, or small integer values |
| **Int64** | `long` | 64-bit signed integer, from `-9,223,372,036,854,775,808` to `9,223,372,036,854,775,807` | Large counters, numeric timestamps, monetary amounts in minor units within range |
| **Double** | `double` | IEEE 754 binary floating-point number, typically ~15–17 significant decimal digits | Measurements, statistics, scientific data tolerant of representation error |
| **Decimal128** | `decimal` | IEEE 754 **decimal** floating-point number with up to 34 significant decimal digits | Prices, taxes, exchange rates, calculations needing deterministic decimal precision |

The BSON value payload sizes are 4 bytes, 8 bytes, 8 bytes, and 16 bytes respectively; each BSON field also incurs overhead for storing the field name and accompanying metadata.

**Precision and value range are two distinct concepts.** Double can represent numbers of huge magnitude, yet it cannot store every decimal fraction or every large integer accurately. Int64 preserves exact **integer** values across its 64-bit range, but cannot represent fractions. Decimal128 represents many decimal numbers accurately, yet still has a 34-significant-digit limit and exponent bounds.

### 2.1. Int32 and Int64: Exact for In-Range Integers

In `mongosh`, you can use explicit BSON constructors:

~~~javascript
NumberInt(100)                 // BSON Int32
NumberLong("100")              // BSON Int64
NumberLong("9007199254740993") // Int64 larger than JS safe integer limit
~~~

The reason for passing large Int64 values as **strings** is that JavaScript `Number` only represents every integer accurately up to:

~~~javascript
Number.MAX_SAFE_INTEGER; // 9007199254740991 = 2^53 - 1
~~~

If you write the literal `9007199254740993` as a JavaScript number, the digits may already be rounded **before MongoDB receives the data**. Converting to Int64 at a later stage cannot guess the original value.

Use Int32 when values are guaranteed to stay within the 32-bit range; use Int64 for integers requiring a wider range. Both still require overflow checks when accumulating sums or multiplying near bounds.

### 2.2. Double: Not Every Decimal Can Be Represented Exactly

Double stores numbers in base 2. Familiar decimal fractions such as `0.1` and `0.2` generally do not have finite binary representations.

Try in `mongosh`:

~~~javascript
0.1 + 0.2;          // typically displays 0.30000000000000004
(0.1 + 0.2) === 0.3; // false
~~~

These operations are evaluated in JavaScript on the `Number` type; they illustrate the behavior of binary floating-point arithmetic. Do not store the results of such additions in monetary fields expecting a later conversion to Decimal128 to fix the accumulated discrepancy.

Double remains useful for measurements or calculations where representation error is understood and acceptable, such as coordinates, temperatures, or statistical models.

### 2.3. Decimal128: Base-10 Precision Within Format Limits

In `mongosh`, construct Decimal128 from **decimal strings**:

~~~javascript
NumberDecimal("0.1")
NumberDecimal("0.2")
NumberDecimal("19.99")
NumberDecimal("1234567890.123456789")
~~~

You can have the server execute Decimal128 addition:

~~~javascript
db.runCommand({
  aggregate: 1,
  pipeline: [
    {
      $documents: [
        {
          a: NumberDecimal("0.1"),
          b: NumberDecimal("0.2")
        }
      ]
    },
    { $project: { _id: 0, total: { $add: ["$a", "$b"] } } }
  ],
  cursor: {}
});
~~~

The resulting `total` is a Decimal128 value equivalent to `0.3`. In some server versions, the `$documents` stage may not fit every context or version; a more portable practice is storing a document and running `aggregate` against a collection as shown in Section 3.

The crucial point is **bringing exact decimal values into the system from the very beginning** using strings or your programming language's decimal type. For instance, `NumberDecimal("19.99")` preserves the intended decimal representation, whereas a JavaScript expression like `19.99 + 0.01` already performed Double arithmetic before type conversion.

Decimal128 does not mean "infinite precision": results with more than 34 significant digits must be rounded within format limits. For financial data, the application still has to specify allowed decimal places and rounding behavior.

## 3. Hands-On Inspection of Actual BSON Numeric Types

Use an isolated database to avoid touching other data:

~~~javascript
use numeric_precision_lab

db.numericSamples.replaceOne(
  { _id: "sample-1" },
  {
    _id: "sample-1",
    quantity32: NumberInt(12),
    quantity64: NumberLong("12"),
    priceDouble: 19.99,
    priceDecimal: NumberDecimal("19.99"),
    bigIdLong: NumberLong("9007199254740993"),
    bigIdAsJsNumber: 9007199254740993,
    textAmount: "19.99"
  },
  { upsert: true }
);
~~~

Using `replaceOne` with `upsert: true` lets you reliably reload a single practice document. Keep in mind that re-running it **overwrites the fields in the sample document** with their initial values.

Check types using the aggregation operator `$type`:

~~~javascript
db.numericSamples.aggregate([
  {
    $project: {
      _id: 1,
      type32: { $type: "$quantity32" },
      type64: { $type: "$quantity64" },
      typeDouble: { $type: "$priceDouble" },
      typeDecimal: { $type: "$priceDecimal" },
      typeText: { $type: "$textAmount" }
    }
  }
]);
~~~

The corresponding output should be:

~~~json
{
  "_id": "sample-1",
  "type32": "int",
  "type64": "long",
  "typeDouble": "double",
  "typeDecimal": "decimal",
  "typeText": "string"
}
~~~

Filter by a field's BSON type:

~~~javascript
db.numericSamples.find({
  priceDecimal: { $type: "decimal" }
});

db.numericSamples.find({
  priceDouble: { $type: "double" }
});
~~~

The `$type` operator reveals the **stored type**, which is more reliable than visually inspecting how MongoDB Compass or a terminal prints a value. BSON wrapper classes in the shell also make JavaScript's `typeof` insufficient on its own to distinguish all BSON numeric types.

### 3.1. Observing an Integer Rounded on the Client Side

~~~javascript
const unsafeId = 9007199254740993;

print(unsafeId); // may display 9007199254740992

db.numericSamples.findOne(
  { _id: "sample-1" },
  { _id: 0, bigIdLong: 1, bigIdAsJsNumber: 1 }
);
~~~

`bigIdLong` was constructed from a string and retains `9,007,199,254,740,993`; `bigIdAsJsNumber` passed through a JavaScript `Number` and may become `9,007,199,254,740,992`. This is **pre-write data loss**, not MongoDB altering an Int64 value.

### 3.2. Extended JSON for Preserving Type Information During Exchange

Plain JSON only has a single generic number syntax. MongoDB provides **Extended JSON** with explicit expressions marking BSON types. Example in Canonical Extended JSON:

~~~json
{
  "_id": "sample-2",
  "quantity32": { "$numberInt": "12" },
  "quantity64": { "$numberLong": "12" },
  "priceDouble": { "$numberDouble": "19.99" },
  "priceDecimal": { "$numberDecimal": "19.99" },
  "bigIdLong": { "$numberLong": "9007199254740993" }
}
~~~

You can inspect Extended JSON output directly from `mongosh`:

~~~javascript
const document = db.numericSamples.findOne({ _id: "sample-1" });
print(EJSON.stringify(document, null, 2, { relaxed: false }));
~~~

**Canonical** mode (e.g., `relaxed: false`) prioritizes preserving types. **Relaxed** mode may emit regular JSON numbers for certain types, which is easier to read but risks losing type metadata when passing through environments that do not understand BSON.

**Do not pass the object `{"$numberDecimal":"19.99"}` directly into an `insertOne` command in mongosh as a normal way to create a Decimal128.** That is Extended JSON notation; when writing directly from the JavaScript shell, use `NumberDecimal("19.99")` or parse Extended JSON with an appropriate API such as `EJSON.parse`.

## 4. Two Strategies for Representing Currency

Currency requires clear rules on **units, currency codes, and rounding**. Both common approaches work well when applied consistently.

| Storage Approach | Sample Document | Advantages | Trade-offs to Control |
|---|---|---|---|
| **Integer in minor units** | `{currency:"USD",scale:2,amountMinor:NumberLong("1299")}` | Exact integer addition/subtraction; fits cent-based systems well | Must track scale/unit clearly; must fit Int64; requires handling division and remainder allocation |
| **Decimal128 in major currency units** | `{currency:"USD",amount:NumberDecimal("12.99")}` | Directly expresses decimal money amounts; convenient for tax, FX rates, and fractional prices | Must define precision, scale, rounding, and arithmetic result handling |

There is no rule stating "all currencies have 2 decimal places." Some currencies typically have no fractional unit in transactions, while others use three decimal places or special rules. Your application's scale table must reflect business requirements, settlement units, and the currency standards supported by the product.

### 4.1. Storing Monetary Amounts as Minor-Unit Int64

For example, a USD invoice has `12.99 USD` in goods and `2.50 USD` in shipping. Using `scale = 2`, values are stored in cents:

~~~javascript
db.invoices.replaceOne(
  { _id: "inv-minor-001" },
  {
    _id: "inv-minor-001",
    currency: "USD",
    scale: NumberInt(2),
    itemMinor: NumberLong("1299"),
    shippingMinor: NumberLong("250"),
    totalMinor: NumberLong("1549")
  },
  { upsert: true }
);
~~~

Unit interpretation formula:

\[
\text{amountMajor} = \frac{\text{amountMinor}}{10^{\text{scale}}}
\]

With `1549` cents and `scale=2`, the displayed amount is `15.49 USD`. Adding these integers is exact within the Int64 range. However, **division**, **discount rates**, **taxes**, and **remainder allocation** still require explicit rounding rules before producing integer cents.

Because BSON types have finite bounds, validate maximum totals and multiplications before writing to Int64. Never arbitrarily convert `amountMinor` to Double to avoid integer overflow errors.

### 4.2. Storing Decimal128 in Major Currency Units

~~~javascript
db.invoices.replaceOne(
  { _id: "inv-decimal-001" },
  {
    _id: "inv-decimal-001",
    currency: "USD",
    unitPrice: NumberDecimal("12.99"),
    quantity: NumberInt(3),
    taxRate: NumberDecimal("0.0825")
  },
  { upsert: true }
);
~~~

Calculate subtotal and tax in aggregation:

~~~javascript
db.invoices.aggregate([
  { $match: { _id: "inv-decimal-001" } },
  {
    $set: {
      subtotal: { $multiply: ["$unitPrice", "$quantity"] }
    }
  },
  {
    $set: {
      taxExact: { $multiply: ["$subtotal", "$taxRate"] }
    }
  },
  {
    $project: {
      _id: 1,
      currency: 1,
      subtotal: 1,
      taxExact: 1,
      taxRounded: { $round: ["$taxExact", 2] }
    }
  }
]);
~~~

With price `12.99` and quantity `3`, the pre-tax subtotal is `38.97`. Unrounded tax is `3.215025`, and rounding to two decimal places with `$round` gives `3.22`.

**This is only an illustration of the rounding mechanism.** In practice, you must specify whether tax is rounded per line item or on the invoice total, before or after discounts, and according to applicable legal rules. Rounding at the wrong step still produces incorrect totals even when using Decimal128.

Never add amounts in two different currencies directly. When performing currency conversion, record/define the exchange rate, effective timestamp, source/target currency units, and post-conversion rounding policy.

## 5. Rounding and Precision Rules in MongoDB

### 5.1. `$round` and `$trunc`

Two commonly used aggregation expressions:

~~~javascript
{ $round: [<number>, <place>] }
{ $trunc: [<number>, <place>] }
~~~

- `$round` rounds to the specified decimal place. At an exact midpoint (when the dropped digit is `5` with appropriate trailing digits), MongoDB uses **round half to even**: selecting the even digit for the last retained place.
- `$trunc` truncates fractional digits at the specified place toward `0`, without performing arithmetic round-up.
- `place = 2` keeps two decimal places; `0` rounds/truncates to an integer; negative values round at the tens, hundreds, etc.
- The output type of `$round`/`$trunc` depends on the input type; with Decimal128 input, the result remains Decimal128.

Concrete example with Decimal128 data:

~~~javascript
db.roundingSamples.replaceOne(
  { _id: "round-1" },
  {
    _id: "round-1",
    a: NumberDecimal("2.345"),
    b: NumberDecimal("2.355"),
    c: NumberDecimal("-2.349")
  },
  { upsert: true }
);

db.roundingSamples.aggregate([
  { $match: { _id: "round-1" } },
  {
    $project: {
      _id: 0,
      roundA: { $round: ["$a", 2] },
      roundB: { $round: ["$b", 2] },
      truncC: { $trunc: ["$c", 2] }
    }
  }
]);
~~~

Expected values:

| Operation | Decimal128 Result | Explanation |
|---|---|---|
| `$round("2.345", 2)` | `2.34` | Midpoint tie: selects the even hundredths digit `4` |
| `$round("2.355", 2)` | `2.36` | Midpoint tie: selects the even hundredths digit `6` |
| `$trunc("-2.349", 2)` | `-2.34` | Truncates toward 0, rather than rounding down to `-2.35` |

If your business logic requires **half up** or **half away from zero**, do not assume `$round` satisfies it. Implement the required rule explicitly, test with negative numbers and edge cases, and apply it consistently in the server/backend.

### 5.2. At Which Step Should Rounding Occur?

Suppose there are three line items, each generating an unrounded tax of `0.005 USD`:

- Rounding per line using half-to-even: each `0.005` may become `0.00`, totaling `0.00`.
- Summing first: `0.005 + 0.005 + 0.005 = 0.015`, then rounding to two decimal places with half-to-even yields `0.02`.

This is not a calculation bug: **line-level rounding** and **invoice-total rounding** are two different policies. The application must specify which policy applies; avoid ad-hoc rounding across multiple layers (frontend, backend, and database).

When using Int64 cents, results of division or percentage multiplication must be quantized per policy before storage. When using Decimal128, a quantization step is still required prior to settlement or reconciliation.

## 6. Data Type Conversion with Aggregation

MongoDB supports specialized conversion operators as well as a general-purpose operator:

| Operator | Purpose | Notes |
|---|---|---|
| `$toInt` | Converts compatible input to BSON Int32 | Fails if unconvertible or outside 32-bit range |
| `$toLong` | Converts to BSON Int64 | Fails if unconvertible or outside 64-bit range |
| `$toDouble` | Converts to BSON Double | May lose precision due to binary representation |
| `$toDecimal` | Converts to BSON Decimal128 | Useful for normalizing valid decimal strings |
| `$toString` | Converts supported values to strings | Suitable for display/exchange; does not replace currency formatting |
| `$convert` | Explicitly specifies target type and error/null handling | Most useful for untrusted input data |
| `$type` | Inspects the BSON type of an expression | Used for profiling and post-conversion verification |

The `$to...` operators are shorthand forms of `$convert` and can **abort the pipeline with an error** upon encountering an unconvertible value. To handle dirty data per document, use `$convert` with `onError` and `onNull`.

### 6.1. Converting Strings to Decimal128 and Int64

Load sample raw data simulating an import table from an external system:

~~~javascript
const rawRows = [
  { _id: "r1", priceText: "125.50", quantityText: "3" },
  { _id: "r2", priceText: "0.10", quantityText: "2" },
  { _id: "r3", priceText: "12,50", quantityText: "3" },
  { _id: "r4", priceText: null, quantityText: "1" },
  { _id: "r5", priceText: "30.00", quantityText: "abc" }
];

rawRows.forEach(row => {
  db.rawAmounts.replaceOne({ _id: row._id }, row, { upsert: true });
});
~~~

Test conversion results with `$convert`:

~~~javascript
db.rawAmounts.aggregate([
  {
    $project: {
      _id: 1,
      priceText: 1,
      quantityText: 1,
      priceDecimal: {
        $convert: {
          input: "$priceText",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      quantityLong: {
        $convert: {
          input: "$quantityText",
          to: "long",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

For `r1` and `r2`, the price strings have valid decimal format and convert to Decimal128; valid integer `quantityText` values convert to Int64. Cases `"12,50"`, `null`, and `"abc"` map to `null` via `onError`/`onNull`.

Strings containing commas as decimal separators or thousands separators generally need **format normalization at the ingestion layer** based on a valid locale before type conversion. Do not blindly strip all commas without knowing whether they represent decimal separators or thousands grouping.

### 6.2. Calculating After Conversion

Multiply only when both price and quantity have converted successfully:

~~~javascript
db.rawAmounts.aggregate([
  {
    $set: {
      priceDecimal: {
        $convert: {
          input: "$priceText",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      quantityLong: {
        $convert: {
          input: "$quantityText",
          to: "long",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      lineTotal: {
        $cond: [
          {
            $and: [
              { $ne: ["$priceDecimal", null] },
              { $ne: ["$quantityLong", null] }
            ]
          },
          { $multiply: ["$priceDecimal", "$quantityLong"] },
          null
        ]
      }
    }
  },
  {
    $project: {
      priceText: 1,
      quantityText: 1,
      priceDecimal: 1,
      quantityLong: 1,
      lineTotal: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

For `r1`, the line total is `376.50`. For `r2`, the total is `0.20`. Invalid rows are preserved for investigation rather than failing the whole pipeline.

**Never silently turn all errors into `0` in monetary workflows.** Using `null` in the example distinguishes "could not be computed" from an actual monetary amount of `0`. In production systems, also record error codes, ingestion sources, and formatting failure reasons.

### 6.3. Distinguishing Conversion Errors from Null Data

When auditing raw data, you can return distinct markers for conversion errors and null inputs:

~~~javascript
db.rawAmounts.aggregate([
  {
    $project: {
      _id: 1,
      originalType: { $type: "$priceText" },
      parsed: {
        $convert: {
          input: "$priceText",
          to: "decimal",
          onError: "INVALID_NUMBER",
          onNull: "MISSING_VALUE"
        }
      }
    }
  }
]);
~~~

The operator returns Decimal128 for valid strings, while sentinel strings `"INVALID_NUMBER"` and `"MISSING_VALUE"` distinguish the two failure modes. **This is a diagnostic pipeline**; do not feed mixed number/string `parsed` values into arithmetic or persist them as production currency fields.

### 6.4. Conversion Edge Cases Requiring Special Attention

| Source and Target Type | Example | Consequence |
|---|---|---|
| Integer string → Int64 | `"42"` → `$toLong` | Succeeds if valid and within range |
| Fractional string → Int64 | `"42.5"` → `$toLong` | Conversion error; string must represent a valid integer |
| Fractional Decimal128 → Int64 | `NumberDecimal("42.9")` → `$toLong` | Truncates fraction toward 0 if in range; does not apply monetary rounding |
| Large Int64 → Double | `9007199254740993` → `$toDouble` | May lose digits because Double cannot represent all large integers |
| Inaccurate Double → Decimal128 | Double result after arithmetic → `$toDecimal` | Cannot recover precision already lost earlier |
| Malformed string → Decimal128 | `"12,50"` → `$toDecimal` | Fails unless input is normalized first |
| Out-of-range value → Int32/Int64 | `"999999999999999999999999"` → `$toLong` | Overflow error |
| Null/missing → `$convert` | Empty or missing input | Handled by `onNull`; defaults to null if omitted |

Truncating fractions when converting a **numeric value** to an integer behaves differently from directly converting a **string containing a decimal point**. To convert Decimal128 currency amounts into Int64 cents, multiply by the scale factor, round per policy, validate bounds, and then convert to integer.

Example demonstrating converting USD amounts to cents:

~~~javascript
db.invoices.aggregate([
  { $match: { _id: "inv-decimal-001" } },
  {
    $project: {
      _id: 1,
      unitPriceMinor: {
        $toLong: {
          $round: [
            { $multiply: ["$unitPrice", NumberDecimal("100")] },
            0
          ]
        }
      }
    }
  }
]);
~~~

Here `12.99 × 100` becomes `1299` before casting to Int64. For negative values, rules other than half-to-even, or very large numbers, verify policies and bounds before automating. Treat minor units and scale as part of your **data contract**, not merely display formatting.

## 7. Conversions, Arithmetic, and Return Types

MongoDB applies numeric type promotion rules in many aggregation operators such as `$add`, `$multiply`, and `$sum`. When inputs have mixed types, the result can be promoted to a wider type—such as from Int32 to Int64, Double, or Decimal128 depending on the operator and data; overflow can also alter type handling.

This leads to three design principles:

1. **Define one canonical type for each business field.** For example, all `unitPrice` fields in a collection are Decimal128; all `quantity` fields are Int32/Int64 as required; all `amountMinor` fields are Int64.
2. **Convert at the ingestion boundary.** When receiving price strings, parse and validate before saving. Avoid mixing strings, Doubles, and Decimal128 and deferring conversion until reporting time.
3. **Verify result types.** Calculations can yield an unexpected type when inputs are mixed; use `$type` to inspect.

Example inspecting the result type of Decimal128 multiplication:

~~~javascript
db.invoices.aggregate([
  { $match: { _id: "inv-decimal-001" } },
  {
    $project: {
      _id: 0,
      lineTotal: { $multiply: ["$unitPrice", "$quantity"] },
      lineTotalType: {
        $type: { $multiply: ["$unitPrice", "$quantity"] }
      }
    }
  }
]);
~~~

Since `unitPrice` is Decimal128, the result is expected to be `decimal` in this calculation. For monetary fields, knowing the **type of the result** is just as important as the displayed number.

### 7.1. Summing Monetary Values Across Multiple Documents

Suppose a collection holds multiple invoice line items:

~~~javascript
const lines = [
  {
    _id: "line-1",
    invoiceId: "invoice-A",
    unitPrice: NumberDecimal("19.99"),
    quantity: NumberInt(2)
  },
  {
    _id: "line-2",
    invoiceId: "invoice-A",
    unitPrice: NumberDecimal("5.25"),
    quantity: NumberInt(3)
  },
  {
    _id: "line-3",
    invoiceId: "invoice-B",
    unitPrice: NumberDecimal("8.50"),
    quantity: NumberInt(1)
  }
];

lines.forEach(row => {
  db.invoiceLines.replaceOne({ _id: row._id }, row, { upsert: true });
});
~~~

Total amount per invoice:

~~~javascript
db.invoiceLines.aggregate([
  {
    $set: {
      lineTotal: { $multiply: ["$unitPrice", "$quantity"] }
    }
  },
  {
    $group: {
      _id: "$invoiceId",
      total: { $sum: "$lineTotal" },
      numberOfLines: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 1,
      numberOfLines: 1,
      total: { $round: ["$total", 2] },
      totalType: { $type: "$total" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

With only these three sample lines, the pre-tax total for `invoice-A` is `55.73` (`19.99 × 2 + 5.25 × 3`), and `invoice-B` is `8.50`. Storing Decimal128 enables decimal addition with the precision of that type.

For transactions involving discounts, taxes, and multiple currencies, group by **both `invoiceId` and `currency`** or validate that each invoice contains only one currency, then apply rounding rules at the proper business step.

## 8. Storing Exact Types from Java Applications

In a Java project, the type of a value **before it reaches the MongoDB Driver** is just as important as the BSON type. Java `double` shares the same representation limitations as BSON Double; Java `BigDecimal` represents decimal numbers and is much better suited for prices, taxes, and currency.

Example using the MongoDB Java Driver:

~~~java
import java.math.BigDecimal;
import org.bson.Document;
import org.bson.types.Decimal128;

BigDecimal exactPrice = new BigDecimal("19.99");

Document product = new Document("_id", "product-001")
    .append("currency", "USD")
    .append("unitPrice", new Decimal128(exactPrice))
    .append("quantity", 3);

Decimal128 storedPrice = product.get("unitPrice", Decimal128.class);
BigDecimal valueForBusinessLogic = storedPrice.bigDecimalValue();
~~~

Calling `new BigDecimal("19.99")` captures the exact decimal value from a **string**. Avoid `new BigDecimal(19.99)` if you intend the monetary value `19.99`, because the `double` constructor transfers the input's binary floating-point error into the `BigDecimal`.

`BigDecimal` can hold higher precision than Decimal128. When storing a `BigDecimal` that exceeds Decimal128's representation limits, check/quantize or reject the value per business rules; do not assume every `BigDecimal` can be stored losslessly.

With Java `Long`, exact integer values span the 64-bit range, matching BSON Int64. When exchanging large integer values over a JSON API to a JavaScript frontend, use type-preserving serialization or decimal strings under an explicit contract; never coerce all large integers into JavaScript `Number`.

### 8.1. API Boundaries and Polyglot Applications

A safe flow typically follows:

~~~text
HTTP/CSV/Input
    |
    v
Validate currency unit + format + source type
    |
    v
Convert to exact BigDecimal / Int64
    |
    v
Check range, scale, and rounding policy
    |
    v
Write BSON Decimal128 or BSON Int64
    |
    v
Read back → calculate/display by currency + scale
~~~

If the frontend sends `"19.99"` as a contracted string, the backend can parse it directly into an exact `BigDecimal`. If the frontend evaluates `19.99 + 0.01` in JavaScript and then sends a JSON number, inaccuracy may already exist before the backend begins processing.

Never trust display formatting: a UI can print `19.99` even when the underlying type is Double. Storage types and rounding belong to the system's data contract.

## 9. MongoDB Compass: Viewing and Editing Numeric Fields Without Changing Types

Compass helps inspect BSON types inside documents. Depending on the version, the document editor may provide type selectors such as Int32, Int64, Double, Decimal128, String, or Extended JSON views.

Connect to the same `numeric_precision_lab` database and open the `numericSamples` collection:

1. Open document `sample-1` and inspect `quantity32`, `quantity64`, `priceDouble`, and `priceDecimal`.
2. If the UI displays type badges, cross-check them against the `$type` results from Section 3.
3. When editing `priceDecimal`, confirm that it stays **Decimal128**. Replacing `NumberDecimal("19.99")` with a plain JSON number in an environment that does not preserve types may save the field under an unintended type.
4. If Compass uses Extended JSON mode, you can rely on wrappers such as `{"$numberDecimal":"19.99"}` or `{"$numberLong":"9007199254740993"}` as supported by that version's UI.
5. After saving, return to `mongosh` and run:

~~~javascript
db.numericSamples.aggregate([
  { $match: { _id: "sample-1" } },
  {
    $project: {
      _id: 0,
      priceDecimalType: { $type: "$priceDecimal" },
      quantity64Type: { $type: "$quantity64" }
    }
  }
]);
~~~

When entering monetary fields in Compass, verify the **BSON type**, **exact value**, and **currency unit**. Seeing a field displayed with two decimal places does not prove it is stored as Decimal128.

## 10. Auditing and Normalizing Collections with Mixed Types

Historical data may hold monetary values across multiple types. Load a sample set:

~~~javascript
const legacyRows = [
  { _id: "l1", amount: NumberDecimal("10.50"), currency: "USD" },
  { _id: "l2", amount: 10.50, currency: "USD" },
  { _id: "l3", amount: "10.50", currency: "USD" },
  { _id: "l4", amount: NumberInt(11), currency: "USD" },
  { _id: "l5", amount: "invalid", currency: "USD" }
];

legacyRows.forEach(row => {
  db.legacyPayments.replaceOne({ _id: row._id }, row, { upsert: true });
});
~~~

Group and count by BSON type:

~~~javascript
db.legacyPayments.aggregate([
  {
    $group: {
      _id: { $type: "$amount" },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Preview conversion outcomes **without modifying data**:

~~~javascript
db.legacyPayments.aggregate([
  {
    $project: {
      _id: 1,
      amount: 1,
      amountType: { $type: "$amount" },
      candidateDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: "INVALID_NUMBER",
          onNull: "MISSING_VALUE"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

From the preview output, compile a list of invalid documents or records needing reconciliation. **Do not bulk-convert and overwrite immediately** just because most documents convert cleanly: values originating from Double may already have undergone imprecise arithmetic prior to storage. Cross-check business sources, settle on a scale policy, define discrepancy handling, and prepare an appropriate backup/rollback plan before migrating.

Once the canonical type is defined, enforce validation at the application layer; if needed, also apply a MongoDB JSON Schema validator requiring `amount` to be BSON `decimal` or `long` and requiring `currency`. A validator prevents **wrong types** in new writes, though it does not replace rounding-policy or currency-unit checks.

An example schema that can be applied to a **new collection** when adopting a Decimal128 storage policy:

~~~javascript
db.createCollection("paymentsValidated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["currency", "amount"],
      properties: {
        currency: {
          bsonType: "string",
          description: "Currency code"
        },
        amount: {
          bsonType: "decimal",
          description: "Monetary amount in major currency units"
        }
      }
    }
  }
});
~~~

`createCollection` only runs when the collection does not yet exist. This example demonstrates the validation mechanism; real business rules may also need positive/non-negative amount checks, valid currency codes, maximum decimal places, and transaction status constraints.

## 11. Common Bugs and Troubleshooting

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `0.1 + 0.2` does not equal `0.3` in exact comparison | Binary representation of Double | For money, use Decimal128 from strings or minor-unit Int64 |
| Large Int64 changes to another number after frontend submission | Passed through a JavaScript `Number` above `2^53 - 1` | Transmit as strings or type-preserving formats; parse directly to Int64 |
| Converting `"12,50"` to Decimal128 fails | String does not match the decimal format MongoDB expects | Normalize according to locale before parsing |
| `$toInt` or `$toLong` aborts aggregation | Unconvertible or out-of-range value | Use `$convert` with error handling while logging bad records |
| Negative amounts round differently than expected | Differing rounding policies | Standardize on half-even, half-up, or another policy and test negative numbers |
| Same field holds multiple BSON types | Inconsistent data writers | Profile with `$type` and normalize at the ingestion boundary |
| Converting to Decimal128 does not recover original value | Precision was already lost while in Double/JS Number | Recover from authoritative source data instead of merely casting |
| Invoices differ by a few cents across systems | Rounding at different stages or mismatched scales | Reconcile tax/discount calculation steps, currency units, and remainder allocation rules |
| Driver throws error when saving `BigDecimal` | Value exceeds Decimal128 limits | Validate precision, scale, range, and rounding rules before creating Decimal128 |
| Compass shows the price, but editing changes its type | Editor/JSON entered a different BSON type than intended | Use the typed editor/EJSON and re-verify with `$type` |

## 12. Self-Check Exercises

Practice inside the `numeric_precision_lab` database:

1. Create `numericSamples` from Section 3, then query with `$type` to distinguish `int`, `long`, `double`, `decimal`, and `string`.
2. Compare `bigIdLong` and `bigIdAsJsNumber`. Explain why Int64 initialized from a string preserves integers beyond 53 bits accurately, whereas a JavaScript numeric literal does not.
3. Evaluate `0.1 + 0.2` in the shell, then sum two Decimal128 values using aggregation. Note the difference in representation.
4. Create invoices `inv-minor-001` (Int64 cents) and `inv-decimal-001` (Decimal128 USD). Clearly explain the unit of every field.
5. Compute `subtotal`, `taxExact`, and `taxRounded`, and identify which operation applies half-to-even rounding.
6. Run `roundingSamples` and compare `$round` vs. `$trunc` on positive and negative numbers.
7. Load `rawAmounts`, use `$convert` with `onError` and `onNull`, and identify valid vs. invalid values.
8. Use `$type` to group `legacyPayments` by type and preview normalization without updating the collection directly.
9. In Compass, open `numericSamples` and inspect the type of `priceDecimal` before and after editing; verify again in `mongosh`.
10. Explain which type to choose for: item quantities (0–10,000), USD monetary amounts, integer counters that may exceed Int32, and scientific measurements with acceptable error margins.

### Applied Questions

**Question 1.** An API returns `{"amount":19.99}`. From this JSON alone, can you confirm MongoDB stores the `amount` field as Decimal128?

*Answer:* No. A JSON number does not fully express BSON types; you must know the serialization contract or inspect the source data with `$type`/Extended JSON.

**Question 2.** Should you convert a Double field containing monetary totals to Decimal128 using `$toDecimal` and treat the result as completely exact data?

*Answer:* No. Type conversion cannot reverse rounding errors or lost digits introduced during earlier operations.

**Question 3.** When a system must charge fees accurately to the cent, should you choose Int64 cents or Decimal128 USD?

*Answer:* Both can work well; decide based on tax calculation, FX rates, value bounds, API integrations, and rounding policies. The prerequisite is keeping units and types consistent system-wide.

**Question 4.** Does applying `$toLong` directly to Decimal128 `12.99` produce `1299` cents?

*Answer:* No. Converting directly to an integer truncates the fractional part and produces `12` if within bounds. You must convert units explicitly: multiply by `100`, apply intentional rounding, and then cast to Int64.

## 13. Principles for MongoDB Systems

- **BSON stores true numeric types:** Int32, Int64, Double, and Decimal128 have distinct semantics; confirm with `$type`.
- **Money requires precision from the point of entry:** pass decimal strings → `BigDecimal`/Decimal128, or minor-unit integers → Int64. Never expect casting to repair an already inaccurate number.
- **Precision and rounding are business contracts:** specify currency, scale, rounding timing, and policies for negative numbers, taxes, and discounts.
- **Conversions can fail:** `$convert` handles errors per document; invalid records must be flagged and investigated rather than treated as `0`.
- **Prevent mixed types:** enforce controls at the API/driver layer, validate schemas, and audit existing data prior to migrations.
- **Calculation paths must preserve types end-to-end:** from client to Java backend, MongoDB, aggregation, and reporting outputs.

By combining appropriate BSON types, controlled conversions, and consistent currency rules, MongoDB can store and process financial values clearly, verifiably, and in line with application precision requirements.
