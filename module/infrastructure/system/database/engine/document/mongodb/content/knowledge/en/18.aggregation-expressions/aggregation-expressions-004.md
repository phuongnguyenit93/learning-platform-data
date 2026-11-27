# Arithmetic Expressions, Rounding, and Decimal128 Calculations in MongoDB

## 1. Why Should You Care About Numeric Types from the Moment You Write Aggregation?

MongoDB provides many expressions for addition, subtraction, multiplication, division, modulo, exponentiation, rounding, and summation over documents. They commonly appear in pipelines that calculate order totals, taxes, discounts, average scores, growth rates, or statistical reports.

For example, an invoice line item has:

```javascript
{
  quantity: 3,
  unitPrice: NumberDecimal("19.95"),
  taxRate: NumberDecimal("0.08")
}
```

The straightforward requirement is to compute:

```text
Line amount   = quantity × unitPrice
Tax           = line amount × taxRate
Total payable = line amount + tax
```

However, the choice of **numeric type** and **when rounding happens** can cause two nearly identical-looking pipelines to return different results. For approximate statistics, a tiny discrepancy might be acceptable. For currency, invoicing, and accounting, being off by a single minor currency unit can become a business defect.

This lesson clarifies:

- How to use arithmetic operators in aggregation: `$add`, `$subtract`, `$multiply`, `$divide`, `$mod`, `$abs`, `$pow`, and related operators.
- The difference between summing/counting/averaging within a single document versus across a whole group.
- How `$round`, `$trunc`, `$ceil`, and `$floor` handle positive numbers, negative numbers, and decimal places.
- Why **BSON Decimal128** is valuable for decimal values requiring high precision.
- How to handle `null`, wrong-type data, division by zero, overflow, and rounding rules.
- A complete invoice pipeline and how to exchange Decimal128 with the MongoDB Java Sync Driver.
- Trade-offs in accuracy, performance, and business rules when computing on the server.

> **Core principle:** accurate computation depends not only on the formula, but also on the numeric types of operands, units of measurement, required precision, and where rounding is performed.

---

## 2. What Is an Aggregation Expression?

In an aggregation pipeline, expressions are evaluated against the data of the document or group currently being processed. This differs from typing a JavaScript expression directly in `mongosh`.

Example:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 1,
      quantity: 1,
      unitPrice: 1,
      rawAmount: {
        $multiply: ["$quantity", "$unitPrice"]
      }
    }
  }
]);
```

In `rawAmount`:

- `$multiply` is an **expression operator**.
- `"$quantity"` references the value of the `quantity` field in the current document.
- `"$unitPrice"` references the `unitPrice` field.
- Both values are computed on the server; they are not the literal strings `"quantity"` and `"unitPrice"`.

### 2.1. Expressions Can Be Nested

```javascript
{
  $add: [
    { $multiply: ["$quantity", "$unitPrice"] },
    "$shippingFee"
  ]
}
```

Meaning:

```text
(quantity × unitPrice) + shippingFee
```

In MongoDB documentation, expressions of the form `{ $operator: ... }` can be used in stages such as `$project`, `$set`, `$addFields`, `$group` (according to accumulator/expression contracts), or inside `$expr` in a suitable query.

### 2.2. Distinguishing Stage Operators from Expression Operators

```javascript
// Here $set is a pipeline stage.
db.orderLines.aggregate([
  {
    $set: {
      lineAmount: {
        $multiply: ["$quantity", "$unitPrice"]
      }
    }
  }
]);
```

`$set` adds/replaces fields on documents passing through the pipeline. `$multiply` is the arithmetic computation expression. You must also distinguish `$sum` as an **accumulator in `$group`** versus as an **expression in other stages**; the two contexts differ in how they handle arrays.

### 2.3. Operators Are Not JavaScript Arithmetic

Do not write:

```javascript
// Does not express per-document multiplication on the server:
db.orderLines.aggregate([
  {
    $project: {
      amount: "$quantity" * "$unitPrice"
    }
  }
]);
```

Client-side JavaScript in the shell cannot access field values by multiplying two path strings. You must use:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      amount: { $multiply: ["$quantity", "$unitPrice"] }
    }
  }
]);
```

---

## 3. Preparing Sample Data

Assume the `orderLines` collection does not yet contain the IDs used here:

```javascript
db.orderLines.insertMany([
  {
    _id: "L1",
    orderId: "O100",
    sku: "PEN",
    quantity: 3,
    unitPrice: NumberDecimal("19.95"),
    discountRate: NumberDecimal("0.10")
  },
  {
    _id: "L2",
    orderId: "O100",
    sku: "NOTE",
    quantity: 2,
    unitPrice: NumberDecimal("4.20"),
    discountRate: NumberDecimal("0.00")
  },
  {
    _id: "L3",
    orderId: "O101",
    sku: "CASE",
    quantity: 1,
    unitPrice: NumberDecimal("35.50"),
    discountRate: NumberDecimal("0.05")
  }
]);
```

The data has the following attributes:

| Field | Illustrative Type | Role |
| --- | --- | --- |
| `_id` | String | Line item identifier. |
| `orderId` | String | Parent order. |
| `quantity` | BSON Int32 | Integer quantity. |
| `unitPrice` | BSON Decimal128 | Decimal unit price. |
| `discountRate` | BSON Decimal128 | Discount rate in 0–1 form. |

Subsequent examples build on this dataset or note explicitly when separate data is used. Before re-running `insertMany`, use an empty test collection or different IDs to avoid duplicate `_id` errors.

### 3.1. Creating Decimal128 Values Properly in `mongosh`

```javascript
NumberDecimal("19.95")
NumberDecimal("0.10")
NumberDecimal("123456789.012345")
```

**Passing a string** to `NumberDecimal(...)` explicitly describes the intended decimal value. Do not perform a JavaScript Double operation and assume wrapping the result in Decimal128 will erase prior floating-point errors.

Example to avoid in monetary code:

```javascript
// Addition happens first using JavaScript Number (binary floating-point).
const value = 0.1 + 0.2;

// This is not input-equivalent to passing "0.3" from the start.
```

To store monetary values consistently, accept decimals from validated strings or use `BigDecimal` in Java.

---

## 4. `$add`: Multi-Operand Addition

Syntax:

```javascript
{
  $add: [<expression1>, <expression2>, ...]
}
```

Example:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 1,
      unitPrice: 1,
      handlingFee: NumberDecimal("2.50"),
      totalForOneUnit: {
        $add: [
          "$unitPrice",
          NumberDecimal("2.50")
        ]
      }
    }
  }
]);
```

For line L1, the sum of `19.95` and `2.50` has the arithmetic value **22.45**.

### 4.1. Adding Multiple Fields

```javascript
{
  $add: [
    "$subtotal",
    "$taxAmount",
    "$shippingFee"
  ]
}
```

The operator accepts an array of expressions. If a field inside is `null` or missing, define the behavior and sanitize inputs; with arithmetic operators like `$add`, `null` can cause the result to become `null` rather than automatically defaulting to `0`.

### 4.2. Using `$ifNull` When Business Rules Specify Defaulting to 0

If shipping fee is optional:

```javascript
db.orders.aggregate([
  {
    $project: {
      payable: {
        $add: [
          "$subtotal",
          "$taxAmount",
          { $ifNull: ["$shippingFee", NumberDecimal("0.00")] }
        ]
      }
    }
  }
]);
```

Apply defaults **only when business rules allow it**. A missing `shippingFee` caused by a data bug may need to be rejected rather than silently turned into `0`. When financial auditing is required, distinguish "no fee" from "fee not yet entered."

### 4.3. `$add` with Dates

MongoDB also supports adding a Date value and a numeric value representing **milliseconds** per the operator's contract:

```javascript
db.events.aggregate([
  {
    $project: {
      scheduledAt: {
        $add: [
          "$createdAt",
          60 * 60 * 1000
        ]
      }
    }
  }
]);
```

This example adds one hour in milliseconds. Remember the numeric unit is **millisecond**, not second. When dealing with calendars, timezones, DST, or calendar months/days, prefer dedicated date operators like `$dateAdd` instead of multiplying milliseconds for a month.

---

## 5. `$subtract`: Subtraction and Time Differences

Syntax:

```javascript
{
  $subtract: [<minuend>, <subtrahend>]
}
```

Monetary example:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 1,
      afterFixedDiscount: {
        $subtract: [
          "$unitPrice",
          NumberDecimal("2.00")
        ]
      }
    }
  }
]);
```

For L1: `19.95 - 2.00 = 17.95`.

### 5.1. Operand Order Is Mandatory

```javascript
{ $subtract: [20, 5] }   // 15
{ $subtract: [5, 20] }   // -15
```

`$subtract` takes two ordered operands; unlike `$add`, which can sum multiple values commutatively.

### 5.2. Subtracting a Date from a Date

```javascript
db.deliveryEvents.aggregate([
  {
    $project: {
      elapsedMs: {
        $subtract: ["$completedAt", "$startedAt"]
      }
    }
  }
]);
```

If both operands are Dates, the result is the **elapsed duration in milliseconds**. If seconds are needed, divide the result by `1000`:

```javascript
{
  $divide: [
    { $subtract: ["$completedAt", "$startedAt"] },
    1000
  ]
}
```

When using units like seconds/minutes/hours, name fields clearly (`elapsedMs`, `elapsedSeconds`) to avoid unit-conversion bugs. For calendar-day differences, consider `$dateDiff`.

---

## 6. `$multiply`: Multi-Operand Multiplication

Syntax:

```javascript
{
  $multiply: [<expression1>, <expression2>, ...]
}
```

A line item has quantity and unit price:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      orderId: 1,
      sku: 1,
      quantity: 1,
      unitPrice: 1,
      lineSubtotal: {
        $multiply: ["$quantity", "$unitPrice"]
      }
    }
  }
]);
```

For L1: `3 × 19.95 = 59.85`.

For L2: `2 × 4.20 = 8.40`.

### 6.1. Multiplying by a Percentage Rate

A rate `discountRate = 0.10` means 10%, not the number `10`. The expression:

```javascript
{
  $multiply: [
    "$lineSubtotal",
    "$discountRate"
  ]
}
```

computes the discount amount. If a client sends `10` to mean 10%, the application must have an explicit conversion convention; never confuse percentages with ratios.

### 6.2. Integers and Decimal128 in Multiplication

In the sample data, `quantity` is Int32 and `unitPrice` is Decimal128. MongoDB uses **numeric type promotion** rules, so multiplication involving Decimal128 typically yields Decimal128. You can explicitly cast `quantity` to Decimal128 to make the contract obvious:

```javascript
{
  $multiply: [
    { $toDecimal: "$quantity" },
    "$unitPrice"
  ]
}
```

What matters is that the input `unitPrice` is already genuine Decimal128. If the unit price was stored as a Double, casting at the final step does not guarantee restoring decimal intent already distorted at ingestion.

---

## 7. `$divide`: Division and Denominator Control

Syntax:

```javascript
{
  $divide: [<dividend>, <divisor>]
}
```

Example computing average price per unit:

```javascript
db.orders.aggregate([
  {
    $project: {
      unitAverage: {
        $divide: [
          "$totalAmount",
          "$totalQuantity"
        ]
      }
    }
  }
]);
```

### 7.1. Distinguishing Double and Decimal128 in Division

Per aggregation semantics, `$divide` defaults to returning **Double** for non-Decimal128 operands; if a Decimal128 operand is present, the result uses the decimal type under numeric promotion rules.

Example:

```javascript
db.numbers.aggregate([
  {
    $project: {
      divideIntegers: { $divide: [1, 3] },
      divideDecimals: {
        $divide: [
          NumberDecimal("1"),
          NumberDecimal("3")
        ]
      }
    }
  }
]);
```

Even when represented as Decimal128, `1 / 3` **cannot contain infinitely many 3s**. Decimal128 has finite precision; it is exact for many finite decimal values, but does not turn non-terminating rational fractions into infinite-precision numbers.

### 7.2. Division by Zero Is an Error, Not a Normal Value

Do not write:

```javascript
{
  $divide: ["$amount", "$quantity"]
}
```

if `quantity` can be `0`. Division by zero can cause the aggregation to fail.

One guard pattern:

```javascript
db.orders.aggregate([
  {
    $project: {
      avgUnitAmount: {
        $cond: [
          { $eq: ["$quantity", 0] },
          null,
          {
            $divide: [
              "$amount",
              "$quantity"
            ]
          }
        ]
      }
    }
  }
]);
```

This expression illustrates the case where `quantity` is already validated as a number and may be `0`. If the field can also be **missing**, **null**, or wrong-type, check those states before dividing.

Deciding whether to return `null`, `0`, raise an error, or filter out zero-denominator documents is a **business rule**—do not pick arbitrarily just to keep the pipeline running.

### 7.3. Percentages

Completion rate:

```javascript
{
  $multiply: [
    {
      $divide: [
        "$completedTasks",
        "$totalTasks"
      ]
    },
    100
  ]
}
```

If you need to display the percentage to two decimal places, wrap `$round` around the calculation after deciding the numeric type:

```javascript
{
  $round: [
    {
      $multiply: [
        {
          $divide: [
            { $toDecimal: "$completedTasks" },
            { $toDecimal: "$totalTasks" }
          ]
        },
        NumberDecimal("100")
      ]
    },
    2
  ]
}
```

The denominator still needs guarding. In addition, a rounded display percentage should not be used as the sole input for downstream aggregations if higher precision is needed.

---

## 8. `$mod` and `$abs`: Remainder and Absolute Value

### 8.1. `$mod`

Syntax:

```javascript
{ $mod: [<dividend>, <divisor>] }
```

Example finding leftover items when packing products into boxes of 6:

```javascript
db.packages.aggregate([
  {
    $project: {
      leftover: {
        $mod: ["$itemCount", 6]
      }
    }
  }
]);
```

If `itemCount = 20`, the remainder is `2`.

Applications commonly use `$mod` for divisibility checks, cycles, or remainder-based bucketing. Never divide by `0`. With negative numbers, the remainder operation does not necessarily match the "always non-negative modulo" convention from number theory; if business logic requires bucket keys in `[0, n)`, define an appropriate normalization expression.

### 8.2. `$abs`

```javascript
{ $abs: <expression> }
```

Example:

```javascript
db.payments.aggregate([
  {
    $project: {
      absoluteDifference: {
        $abs: {
          $subtract: [
            "$actualAmount",
            "$expectedAmount"
          ]
        }
      }
    }
  }
]);
```

`$abs` returns the absolute magnitude, useful for calculating variance regardless of direction. In financial reports, the sign of a discrepancy often carries critical business meaning; do not strip minus signs just to make numbers look cleaner.

---

## 9. Exponentiation, Roots, and Logarithms

MongoDB also provides mathematical expressions useful for analytics:

| Operator | Example | Purpose |
| --- | --- | --- |
| `$pow` | `{ $pow: [2, 3] }` | Exponentiation `2^3 = 8`. |
| `$sqrt` | `{ $sqrt: 81 }` | Square root, result `9`. |
| `$exp` | `{ $exp: 1 }` | Natural exponential function. |
| `$ln` | `{ $ln: 10 }` | Natural logarithm. |
| `$log10` | `{ $log10: 100 }` | Base-10 logarithm. |
| `$log` | `{ $log: [8, 2] }` | Logarithm with specified base, result `3`. |

Example compound growth calculation:

```javascript
db.investments.aggregate([
  {
    $project: {
      futureValue: {
        $multiply: [
          "$principal",
          {
            $pow: [
              {
                $add: [
                  1,
                  "$ratePerPeriod"
                ]
              },
              "$numberOfPeriods"
            ]
          }
        ]
      }
    }
  }
]);
```

This is a theoretical growth formula model and does not account for real-world rules such as cash-flow schedules, irregular compounding, taxes, or day-count conventions.

**Domain notes:**

- `$sqrt` requires valid inputs for real square roots (non-negative, subject to special cases).
- `$ln` and `$log10` require positive arguments.
- `$log` requires a valid base (positive, not equal to 1) and appropriate argument.
- `$pow` has edge cases with `0`, negative bases, fractional exponents, and numeric types; validate inputs before using.

Do not use these expressions on financial data with rounding constraints without first specifying precision, overflow, and business rules.

---

## 10. BSON Numeric Types: Int32, Int64, Double, and Decimal128

MongoDB does not have a single "number" type.

| BSON Type | Example in mongosh | Characteristics |
| --- | --- | --- |
| Int32 | `NumberInt(25)` | 32-bit signed integer. |
| Int64 | `NumberLong("9000000000")` | 64-bit signed integer. |
| Double | `0.1` or `NumberDouble("0.1")` | IEEE 754 double-precision binary floating point. |
| Decimal128 | `NumberDecimal("0.1")` | IEEE 754 Decimal128 decimal floating point. |

### 10.1. Why Can Double Drift When Representing Money?

In binary floating point, many finite decimal fractions like `0.1` have no exact binary representation. This can lead to:

```javascript
// In JavaScript:
0.1 + 0.2
// Typically displays: 0.30000000000000004
```

Adding two Decimal128 values constructed from the strings `"0.1"` and `"0.2"` represents the mathematical value `0.3` accurately within decimal precision.

```javascript
db.decimalExamples.aggregate([
  {
    $project: {
      decimalSum: {
        $add: [
          NumberDecimal("0.1"),
          NumberDecimal("0.2")
        ]
      }
    }
  }
]);
```

**Do not equate `NumberDecimal("0.1")` with the Double value `0.1`.** They are two distinct BSON types with different representation properties.

### 10.2. Decimal128 Is Not Infinite-Precision

Decimal128 supports **34 significant digits** in decimal representation, with a wide exponent range per the IEEE 754 Decimal128 standard. It is ideal for decimal financial values, yet:

- Non-terminating decimal fractions like `1/3` still must be rounded to finite precision.
- Operations can exceed the representable range.
- `NaN` or infinity can arise under certain conditions and are unsuitable for most monetary accounting workflows.
- When an operation produces more digits than fit within precision, representation-level arithmetic rounding rules still apply.

**Decimal128 eliminates binary representation drift**; it does not replace rounding policies, validation, currency units, or magnitude controls.

### 10.3. Numeric Type Promotion

MongoDB's arithmetic operators follow type promotion rules when handling mixed numeric types:

```text
Int32 -> Int64 -> Double -> Decimal128
```

This is the general model for precision/type promotion order across many operations. Result types can be influenced by operands and overflow; **not every operator returns the same type via one single formula**.

Several key points:

- Adding/multiplying integers may promote types if results exceed Int32 or Int64 bounds.
- Dividing two integers with `$divide` typically returns Double, unless a Decimal128 operand is present to produce a decimal result.
- `$round`, `$trunc`, `$ceil`, and `$floor` generally preserve the input's numeric type per their contracts.
- When any operand is Decimal128, many arithmetic operations produce a Decimal128 result.

Do not infer return types merely because "the result looks like an integer"; check `$type` or BSON types when exact contracts matter.

### 10.4. Checking Types with `$type`

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 1,
      unitPriceType: { $type: "$unitPrice" },
      quantityType: { $type: "$quantity" },
      resultType: {
        $type: {
          $multiply: [
            "$unitPrice",
            "$quantity"
          ]
        }
      }
    }
  }
]);
```

With the sample dataset, `unitPriceType` is `"decimal"`, `quantityType` is `"int"`, and the multiplication result under promotion rules uses `"decimal"`.

---

## 11. Why Should Decimal128 Be Constructed from Strings?

In `mongosh`:

```javascript
NumberDecimal("19.95")
```

directly expresses an intentional decimal value. Conversely:

```javascript
const unitPrice = 19.95; // JavaScript Number, binary type.
```

if data has already gone through binary floating-point arithmetic, converting to decimal at the end of the pipeline does not automatically reverse all prior drift.

In Java:

```java
new BigDecimal("19.95")
```

constructs the value from a decimal string. Avoid:

```java
new BigDecimal(0.1)
```

when intending to represent exact `0.1`: the Double constructor injects the binary approximation into `BigDecimal`.

If you already have a `double` from another source, `BigDecimal.valueOf(double)` uses the Double's string representation to avoid some surprises of `new BigDecimal(double)`, yet **it does not repair semantically corrupted inputs**. For money, prefer passing decimal strings or integer minor units.

### 11.1. Decimal128 in Extended JSON

When serializing BSON data to Extended JSON, a decimal value can be represented as:

```json
{
  "unitPrice": {
    "$numberDecimal": "19.95"
  }
}
```

This representation preserves BSON type information better than forcing every value into a generic JSON number. API clients should agree on how to serialize/deserialize Decimal128; do not casually convert it to a JavaScript Number when precision is mandatory.

---

## 12. `$round`: Rounding to a Decimal Place

Syntax:

```javascript
{
  $round: [<number>, <place>]
}
```

`<place>` is optional; if omitted, MongoDB rounds to the integer position (equivalent to `0`). `place` is an integer within MongoDB's supported range.

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 1,
      roundedUnitPrice: {
        $round: ["$unitPrice", 1]
      }
    }
  }
]);
```

For `19.95`, rounding to one decimal place follows the **half-even** rule; from `19.95` to one decimal place, the result is **20.0** because the tenths digit chosen is `0` (even) in an exact midpoint tie.

### 12.1. Tie-Breaking Rule: Half to Even

MongoDB `$round` uses **"round half to even"**, often called *banker's rounding*, when a value sits exactly halfway between two candidates.

Examples with `place = 0`:

| Decimal128 Input | Numeric Result | Explanation |
| --- | --- | --- |
| `2.4` | `2` | Closer to 2. |
| `2.6` | `3` | Closer to 3. |
| `2.5` | `2` | Midpoint between 2 and 3; picks even 2. |
| `3.5` | `4` | Midpoint between 3 and 4; picks even 4. |
| `-1.5` | `-2` | Midpoint between -1 and -2; picks even -2. |
| `-2.5` | `-2` | Midpoint between -2 and -3; picks even -2. |

You can test with:

```javascript
db.roundingExamples.aggregate([
  {
    $project: {
      value: 1,
      rounded: { $round: ["$value", 0] }
    }
  }
]);
```

The table examples can be used to construct test data; there is no need to convert types to Double.

**Crucial point:** half-even is **not the same** as ".5 always rounds up" or ".5 always rounds away from zero." If regulations, tax rules, or contracts require `HALF_UP`, implement and verify the **appropriate rounding policy** rather than assuming `$round` satisfies every monetary case.

### 12.2. Rounding to Two Decimal Places

```javascript
{
  $round: [
    "$grossAmount",
    2
  ]
}
```

For monetary values needing 2 digits after the decimal point, `place = 2` is typically appropriate. However, not all currencies have two decimal places and not all calculations round at the same step. Rules must come from the domain.

### 12.3. Rounding to the Left of the Decimal Point

Negative `place` rounds to tens, hundreds, etc.:

```javascript
{ $round: [NumberDecimal("1234.56"), -1] } // 1230
{ $round: [NumberDecimal("1234.56"), -2] } // 1200
```

Do not use `place = -2` intending "keep two digits after the decimal point": that **rounds to the nearest hundred**.

### 12.4. Return Representation

When the input to `$round` is Decimal128, the output remains decimal per the operator's contract. Whether **trailing zeros** are printed can depend on encoding/formatting; to output formatted currency strings like `"20.00"`, keep formatting clearly separated in the application or presentation layer.

### 12.5. `null` and Special Values

Rounding operators return `null` for `null`/missing inputs per operator semantics and have specific rules for `NaN`/`Infinity`. With financial data, do not let such special values pass through the pipeline without validation. Do not treat `null` as `0` unless that is an explicit business decision.

---

## 13. `$trunc`: Truncating Decimals Without Rounding to Nearest

Syntax:

```javascript
{
  $trunc: [<number>, <place>]
}
```

Example:

```javascript
{ $trunc: [NumberDecimal("12.987"), 2] }
```

yields the numeric value **12.98**.

Comparison:

```javascript
{ $round: [NumberDecimal("12.987"), 2] } // 12.99
{ $trunc: [NumberDecimal("12.987"), 2] } // 12.98
```

### 13.1. For Negative Numbers, Truncation Moves Toward Zero

```javascript
{ $trunc: [NumberDecimal("-1.9"), 0] } // -1
```

It is **not** equivalent to rounding toward negative infinity. This is why `$trunc` and `$floor` are not interchangeable on negative numbers.

### 13.2. Negative `place`

```javascript
{ $trunc: [NumberDecimal("1234.56"), -2] } // 1200
```

Digits from the tens place downward are dropped when truncating to hundreds. Negative values are likewise truncated toward zero at the corresponding magnitude.

### 13.3. When to Use `$trunc`?

- Trimming precision for metrics or reports according to explicit rules.
- Extracting the integer part toward zero.
- Applying a business rule that "drops fractional parts" instead of "rounding to nearest."

**Do not use `$trunc` as a substitute for a monetary rounding policy** if half-even/half-up is required. Truncation introduces directional bias compared to rounding.

---

## 14. `$ceil` and `$floor`: Directed Rounding

Syntax:

```javascript
{ $ceil: <expression> }
{ $floor: <expression> }
```

- `$ceil`: smallest integer **greater than or equal to** the input (toward positive infinity).
- `$floor`: largest integer **less than or equal to** the input (toward negative infinity).

| Input | `$ceil` | `$floor` | `$trunc` with place 0 |
| --- | ---: | ---: | ---: |
| `1.2` | 2 | 1 | 1 |
| `1.9` | 2 | 1 | 1 |
| `-1.2` | -1 | -2 | -1 |
| `-1.9` | -1 | -2 | -1 |
| `-2.0` | -2 | -2 | -2 |

Example counting how many boxes are needed if each box holds at most 6 items:

```javascript
db.packages.aggregate([
  {
    $project: {
      boxesNeeded: {
        $ceil: {
          $divide: ["$itemCount", 6]
        }
      }
    }
  }
]);
```

If there are 13 items, 3 boxes are needed. The application must validate `itemCount >= 0` and `capacity > 0`. Otherwise, the formula can produce operationally meaningless results.

### 14.1. Do Not Use `$round` When You Always Need Sufficient Capacity

When allocating containers, pages, cartons, or vehicle trips, you usually need **ceiling**, not nearest rounding:

```text
13 / 6 = 2.166...
round -> 2  (not enough)
ceil  -> 3  (sufficient)
```

### 14.2. Do Not Use `$floor` on Negative Numbers Expecting Truncation

`floor(-1.9) = -2`, whereas `trunc(-1.9) = -1`. When data can be negative, the results clearly differ.

---

## 15. Comparison Table of Rounding Operators

| Requirement | Operator | Rule |
| --- | --- | --- |
| Round to nearest, tie to even | `$round` | Accepts optional `place`. |
| Drop digits beyond kept places | `$trunc` | Truncates toward zero; accepts optional `place`. |
| Always round up toward +∞ | `$ceil` | Does not take `place` like `$round`; returns integer value. |
| Always round down toward -∞ | `$floor` | Does not take `place` like `$round`; returns integer value. |

With Decimal128 monetary values and a two-decimal-place rule, `$round: ["$amount", 2]` is very convenient, provided **half-even** matches the payment policy.

### 15.1. Do Not Round Too Early

Suppose you have two decimal values:

```text
A = 0.005
B = 0.005
```

If you round each element to 2 decimal places using half-even:

```text
round(A, 2) = 0.00
round(B, 2) = 0.00
Sum         = 0.00
```

If you add first and then round:

```text
A + B        = 0.010
round(...,2) = 0.01
```

**Two different workflows yield different results.** Neither can be declared universally "right" for all invoices without knowing the system's rules. Business logic must decide whether to round per line item, per tax group, or per invoice total.

In accounting, you must also define how to handle remainder allocation discrepancies, foreign currencies, and exchange rates. Decimal128 merely executes calculations in an appropriate numeric type; it does not decide those policies.

---

## 16. `$sum` and `$avg`: Calculations on Arrays vs. Groups

`$sum` and `$avg` appear both in aggregation expressions and commonly in `$group`. **Context affects how they handle an array field.**

### 16.1. Summing Fields Within One Document

In `$project` or `$set`:

```javascript
db.testScores.aggregate([
  {
    $project: {
      totalScore: {
        $sum: "$scores"
      },
      avgScore: {
        $avg: "$scores"
      }
    }
  }
]);
```

If a document has `scores: [80, 90, 100]`, in an expression context with a single operand pointing to an array, `$sum` traverses numeric elements to return `270`, and `$avg` returns `90`.

### 16.2. Summing Across Multiple Documents with `$group`

With the `orderLines` collection:

```javascript
db.orderLines.aggregate([
  {
    $set: {
      lineSubtotal: {
        $multiply: [
          "$quantity",
          "$unitPrice"
        ]
      }
    }
  },
  {
    $group: {
      _id: "$orderId",
      subtotal: {
        $sum: "$lineSubtotal"
      },
      averageLineAmount: {
        $avg: "$lineSubtotal"
      },
      lineCount: { $sum: 1 }
    }
  }
]);
```

Pipeline:

1. Compute `lineSubtotal` for each line-item document.
2. Group by `orderId`.
3. Sum all values across documents in the same group.
4. Average the lines with appropriate numeric values.
5. Count line-item documents using `$sum: 1`.

In the sample dataset:

```text
L1: 3 × 19.95 = 59.85
L2: 2 ×  4.20 =  8.40
O100 Total    = 68.25
```

`$sum` in `$group` is an accumulator across **multiple documents**, not syntax for directly summing all elements of an array field the way a non-`$group` expression does.

### 16.3. Array Traversal Trap

Suppose a document has `scores: [80, 90]`.

In `$project`:

```javascript
{
  $project: {
    scoreTotal: { $sum: "$scores" }
  }
}
```

traverses the array and sums to `170`.

However, in `$group`:

```javascript
{
  $group: {
    _id: "$studentId",
    scoreTotal: { $sum: "$scores" }
  }
}
```

the `$sum` accumulator **does not automatically traverse array elements** like the single-operand expression in `$project`. An array value is not treated as a number to sum. To sum scores across documents, compute each document's array sum before `$group`, or `$unwind` appropriately.

A clear approach:

```javascript
db.students.aggregate([
  {
    $set: {
      scoreTotalOfDocument: {
        $sum: "$scores"
      }
    }
  },
  {
    $group: {
      _id: "$classId",
      classTotal: {
        $sum: "$scoreTotalOfDocument"
      }
    }
  }
]);
```

### 16.4. `null` and Non-Numeric Values in `$sum` and `$avg`

These accumulators/expressions have specific rules for ignoring non-numeric values. `$sum` can return `0` when there are no valid numeric operands, whereas `$avg` can return `null` when there are no numeric values to average.

**Do not assume identical behavior across `$add`, `$divide`, `$sum`, and `$avg`.** Each operator has its own contract for `null`, missing, and data types. If data must be decimal, block invalid data with validation rather than relying on `$sum` ignoring invalid entries.

---

## 17. Type Conversion with `$toDecimal` and `$convert`

In long-lived systems, a collection may contain:

```javascript
{ _id: "A", unitPrice: NumberDecimal("19.95") }
{ _id: "B", unitPrice: "19.95" }
{ _id: "C", unitPrice: 19.95 }
{ _id: "D", unitPrice: null }
{ _id: "E", unitPrice: "N/A" }
```

A billing pipeline should not assume every document already holds Decimal128. You could use `$toDecimal`:

```javascript
db.prices.aggregate([
  {
    $project: {
      convertedPrice: {
        $toDecimal: "$unitPrice"
      }
    }
  }
]);
```

However, if a string is `"N/A"` or an unconvertible type, the pipeline may fail. Invalid data should not be hidden by forcing it to `0`.

### 17.1. `$convert` with Conversion Error Handling

```javascript
db.prices.aggregate([
  {
    $project: {
      original: "$unitPrice",
      decimalValue: {
        $convert: {
          input: "$unitPrice",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

This deliberately yields `null` on conversion errors or null inputs. It is useful for **data auditing/cleaning**, provided you verify:

- Is a `null` from a missing value distinct from a `null` caused by `"N/A"`?
- Is the report allowed to exclude unconvertible rows?
- If monetary, should invalid data enter an error queue instead of defaulting to `0`?
- After conversion, are non-negative and upper-bound checks needed?

**Converting Double to Decimal128 after storing a Double does not guarantee recovering the original intended decimal.** It may simply retain or reinterpret the binary-approximated value. When financial accuracy is required, normalize right at data ingestion.

### 17.2. `$isNumber` and `$type`

```javascript
db.prices.aggregate([
  {
    $project: {
      sourceType: {
        $type: "$unitPrice"
      },
      numeric: {
        $isNumber: "$unitPrice"
      }
    }
  }
]);
```

`$isNumber` identifies BSON numeric types, but does not mean the unit price is Decimal128. If rules require **specifically decimal**, verify `$type` equals `"decimal"` or enforce schema validation upfront.

---

## 18. A Complete Invoice Pipeline Using Decimal128

Suppose the `invoices` collection contains a document:

```javascript
db.invoices.insertOne({
  _id: "INV-100",
  currency: "USD",
  items: [
    {
      sku: "A",
      quantity: 2,
      unitPrice: NumberDecimal("19.95")
    },
    {
      sku: "B",
      quantity: 3,
      unitPrice: NumberDecimal("4.20")
    }
  ],
  discountRate: NumberDecimal("0.10"),
  taxRate: NumberDecimal("0.08"),
  shippingFee: NumberDecimal("5.00")
});
```

**Illustrative rules:**

1. Compute each line's amount as quantity times unit price.
2. Sum all lines into `subtotal`.
3. Apply a 10% discount on `subtotal`, rounded to 2 decimal places using `$round`.
4. Compute 8% tax on `subtotal` after discount, rounded to 2 decimal places.
5. Add shipping fee `5.00`.
6. Maintain Decimal128 throughout all monetary calculations.

### 18.1. Step-by-Step Pipeline

```javascript
db.invoices.aggregate([
  {
    $match: {
      _id: "INV-100"
    }
  },
  {
    $set: {
      calculatedLines: {
        $map: {
          input: "$items",
          as: "item",
          in: {
            sku: "$$item.sku",
            quantity: "$$item.quantity",
            unitPrice: "$$item.unitPrice",
            lineAmount: {
              $multiply: [
                "$$item.unitPrice",
                { $toDecimal: "$$item.quantity" }
              ]
            }
          }
        }
      }
    }
  },
  {
    $set: {
      subtotal: {
        $sum: "$calculatedLines.lineAmount"
      }
    }
  },
  {
    $set: {
      discountAmount: {
        $round: [
          {
            $multiply: [
              "$subtotal",
              "$discountRate"
            ]
          },
          2
        ]
      }
    }
  },
  {
    $set: {
      taxableAmount: {
        $subtract: [
          "$subtotal",
          "$discountAmount"
        ]
      }
    }
  },
  {
    $set: {
      taxAmount: {
        $round: [
          {
            $multiply: [
              "$taxableAmount",
              "$taxRate"
            ]
          },
          2
        ]
      }
    }
  },
  {
    $set: {
      grandTotal: {
        $add: [
          "$taxableAmount",
          "$taxAmount",
          "$shippingFee"
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      currency: 1,
      calculatedLines: 1,
      subtotal: 1,
      discountRate: 1,
      discountAmount: 1,
      taxableAmount: 1,
      taxRate: 1,
      taxAmount: 1,
      shippingFee: 1,
      grandTotal: 1
    }
  }
]);
```

### 18.2. Detailed Explanation

**Stage 1 — `$match`**

Finds a specific invoice. Since `_id` is indexed by default, MongoDB can quickly locate the document before performing calculations.

**Stage 2 — `$map`**

Iterates over each element of the `items` array. `$$item` is the current element. Each output element adds `lineAmount`, computed in Decimal128 via `unitPrice` and converting `quantity` to decimal.

**Stage 3 — `$sum`**

Inside `$set`, `$sum: "$calculatedLines.lineAmount"` takes the array of line amounts and sums the numeric values. This is not the `$sum` accumulator in `$group`.

**Stage 4 — Discount**

Computes `subtotal × discountRate`, then applies `$round` with `place = 2`.

**Stage 5 — Taxable Amount**

Computes `subtotal - discountAmount`.

**Stage 6 — Tax**

Computes `taxableAmount × taxRate`, rounded to 2 places.

**Stage 7 — Grand Total**

Adds `taxableAmount`, `taxAmount`, and `shippingFee`.

### 18.3. Expected Arithmetic Results

| Component | Calculation | Value |
| --- | --- | ---: |
| Line A | `2 × 19.95` | 39.90 |
| Line B | `3 × 4.20` | 12.60 |
| Subtotal | `39.90 + 12.60` | 52.50 |
| Discount | `52.50 × 0.10` | 5.25 |
| Taxable amount | `52.50 - 5.25` | 47.25 |
| Tax | `round(47.25 × 0.08, 2)` | 3.78 |
| Shipping | Existing value | 5.00 |
| Grand total | `47.25 + 3.78 + 5.00` | **56.03** |

The values in the table are **mathematical values**; when inspecting BSON Decimal128, trailing-zero display formatting may vary while representing the same numeric value. The API should format currency according to its own convention.

### 18.4. Why Split the Pipeline into Multiple `$set` Stages?

Separate stages make the execution order transparent:

```text
items
  |
  v
lineAmount (Decimal128)
  |
  v
subtotal
  |
  +--> discountAmount
          |
          v
      taxableAmount
          |
          v
       taxAmount
          |
          v
       grandTotal
```

Within a single `$set` stage, do not rely on a newly computed field defined earlier in the same stage being referenceable as if the input document had already changed. Splitting stages ensures later expressions read values produced by prior stages per the pipeline contract.

### 18.5. Validation Is Needed Before the Pipeline

The pipeline assumes:

- `items` is an array.
- `quantity` is a non-negative or positive integer per business rules.
- `unitPrice`, `discountRate`, `taxRate`, and `shippingFee` are valid Decimal128 values.
- `discountRate` and `taxRate` follow the `0–1` convention.
- Required fields contain no `null`, `NaN`, or wrong-type values.

If a document violates the schema, it may need to trigger an error, be excluded from processing, or enter a data-repair workflow. Do not automatically coerce every invalid field to `0`, as that can generate wrong invoices silently.

### 18.6. Tax and Rounding Rules Are Illustrative Only

The example applies the discount before tax and calculates tax on the remainder. In practice, jurisdictions, tax types, currencies, and invoices may require **line-level rounding**, rounding by tax bracket, or rounding on the total; prices may also be tax-inclusive or involve multiple tax rates.

Do not use the example pipeline directly as a production tax engine without verifying business regulations and testing edge cases.

---

## 19. Line-Level vs. Total-Level Rounding: A Real Difference

Suppose two lines have raw tax amounts:

```text
Line 1: 0.005
Line 2: 0.005
```

**Approach A — Round each line, then sum:**

```text
round(0.005, 2) = 0.00
round(0.005, 2) = 0.00
Total tax       = 0.00
```

**Approach B — Sum raw taxes first, then round:**

```text
0.005 + 0.005   = 0.010
round(0.010, 2) = 0.01
```

The results differ by one cent. Neither can be called "correct" without defining the system's rules.

In MongoDB, this difference also shows up in where `$round` is placed:

```javascript
// Compute per-line tax, round each line,
// then $sum the rounded lines.
{
  $sum: {
    $map: {
      input: "$items",
      as: "item",
      in: {
        $round: [
          {
            $multiply: [
              "$$item.amount",
              "$taxRate"
            ]
          },
          2
        ]
      }
    }
  }
}
```

Compared with:

```javascript
// Sum raw values first, then calculate tax/round once.
{
  $round: [
    {
      $multiply: [
        { $sum: "$items.amount" },
        "$taxRate"
      ]
    },
    2
  ]
}
```

Both expressions assume `items.amount` and `taxRate` are valid Decimal128 values. They can yield different outputs because **rounding occurs at different points**, not because MongoDB calculated incorrectly.

### 19.1. Rounding Can Break Associativity

In pure real arithmetic, addition is associative. Once rounding is inserted:

```text
round(round(a, 2) + round(b, 2), 2)
```

is not necessarily equal to:

```text
round(a + b, 2)
```

If an application computes line totals first and later uses those rounded line totals to compute ratios, discrepancies can accumulate. Clearly define which fields are **raw high precision** and which fields are **display/settlement amounts**.

---

## 20. Money as Decimal128 or Integer Minor Units?

Two common approaches in financial systems are:

### 20.1. Decimal128

```javascript
{
  price: NumberDecimal("19.95"),
  currency: "USD"
}
```

Advantages:

- Fits rate calculations and decimal values naturally.
- Accurately represents common decimal values.
- Supported directly by aggregation operators.

Points to watch:

- Finite precision of 34 significant digits.
- Choose rounding policy and rounding timing.
- Check range, overflow, and special values.
- Drivers/clients must preserve the BSON type properly.

### 20.2. Integer Minor Units

```javascript
{
  priceMinor: NumberLong("1995"),
  currency: "USD"
}
```

Here the unit is **cents**, not USD. The advantage is that addition/subtraction on integer minor units is easy to control as long as amounts stay within bounds. However:

- You must know the minor unit scale for every currency.
- Tax/discount allocation still produces fractional minor units, requiring rounding rules.
- Int64 overflow is possible if sums or products grow too large.
- Never assume every currency has exactly two decimal places.

### 20.3. Converting Decimal128 to Minor Units

Example when policy establishes a currency with two decimal places:

```javascript
db.invoices.aggregate([
  {
    $project: {
      grandTotalMinor: {
        $toLong: {
          $round: [
            {
              $multiply: [
                "$grandTotal",
                NumberDecimal("100")
              ]
            },
            0
          ]
        }
      }
    }
  }
]);
```

Multiply Decimal128 by 100, round according to the chosen rule, then convert to Long. Validate that:

- The result fits within the Int64 range.
- The currency actually uses that scale.
- Business rules accept half-even rounding.
- `grandTotal` is not null, NaN, infinity, or the wrong type.

Casting directly with `$toLong` without deciding rounding can truncate fractional parts per contract, yielding unexpected totals.

---

## 21. Null, Missing, Bad Data, and Overflow

### 21.1. Operators Do Not Handle Null Identically

| Operator | Behavior to Watch |
| --- | --- |
| `$add`, `$multiply`, `$subtract`, `$divide` | Null/missing inputs can turn the result to `null` or cause issues depending on the expression; check each operator's contract. |
| `$round`, `$trunc`, `$ceil`, `$floor` | Have specific semantics for null/missing inputs and special values. |
| `$sum` | Can ignore non-numeric values and return `0` if no valid numeric values exist. |
| `$avg` | Can ignore non-numeric values; if no valid numbers exist, may return `null`. |
| `$toDecimal` | May error if string/type cannot be converted; use `$convert` for intentional handling. |

Do not write monetary pipelines treating every missing value as `0` unless the domain explicitly specifies it.

### 21.2. Collection-Level Validation

Example collection requiring non-negative decimal `unitPrice` and Int32 `quantity` of at least 1:

```javascript
db.createCollection("validatedLines", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["unitPrice", "quantity"],
      properties: {
        unitPrice: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        quantity: {
          bsonType: "int",
          minimum: 1
        }
      }
    }
  },
  validationAction: "error"
});
```

This validator illustrates just two constraints. In real usage, add rules for currency, quantity limits, monetary limits, negative refund allowances, and line-item structure.

**Collection validation does not replace business validation in Java.** It protects DB integrity even when another process writes directly through a driver.

### 21.3. Division by Zero and Out-of-Domain Operations

- `$divide` and `$mod` require valid, non-zero divisors.
- `$sqrt`, `$ln`, and `$log` have restricted input domains.
- Exponentiation/interest expressions can overflow or produce special values.
- Do not allow `NaN`/`Infinity` into monetary data undetected.

For invalid data, intentionally **reject, quarantine, or return null**. Returning `0` in all cases can silently corrupt financial reports without raising errors.

### 21.4. Decimal128 Can Overflow or Lose Significant Digits

34 significant digits is a precision limit, not "34 digits after the decimal point." Very large values or divisions with long repeating fractions may require Decimal128-level rounding. Values exceeding the representable range can hit edge-case errors.

If an application requires higher precision than Decimal128 or complex accounting logic, evaluate appropriate storage and arithmetic architectures instead of assuming Decimal128 solves everything.

---

## 22. Calculating Growth Rates and Avoiding Formula Pitfalls

A revenue report contains:

```javascript
{
  oldRevenue: NumberDecimal("1250.00"),
  newRevenue: NumberDecimal("1375.00")
}
```

Percentage growth rate:

```text
(newRevenue - oldRevenue) / oldRevenue × 100
```

Expression:

```javascript
db.revenueSnapshots.aggregate([
  {
    $project: {
      growthPercent: {
        $cond: [
          { $eq: ["$oldRevenue", NumberDecimal("0")] },
          null,
          {
            $round: [
              {
                $multiply: [
                  {
                    $divide: [
                      {
                        $subtract: [
                          "$newRevenue",
                          "$oldRevenue"
                        ]
                      },
                      "$oldRevenue"
                    ]
                  },
                  NumberDecimal("100")
                ]
              },
              2
            ]
          }
        ]
      }
    }
  }
]);
```

From 1250 to 1375, growth is **10.00%**.

This formula assumes `oldRevenue` and `newRevenue` share the same currency, accounting recognition basis, and comparison period. When the baseline is `0`, percentage growth is typically **undefined** under this formula; returning `null` is more transparent than automatically returning `100%`.

If the baseline is negative, interpreting "percentage growth" requires explicit business policy rather than relying solely on the raw math.

---

## 23. Decimal128 in the MongoDB Java Sync Driver

### 23.1. Writing Decimal128 from BigDecimal

Java uses `java.math.BigDecimal` for decimal arithmetic, while BSON uses `org.bson.types.Decimal128`.

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;

public final class DecimalWriteExample {

    public static void insertLine(MongoCollection<Document> collection) {
        BigDecimal price = new BigDecimal("19.95");
        BigDecimal rate  = new BigDecimal("0.08");

        Document document = new Document("_id", "LINE-JAVA-1")
            .append("quantity", 3)
            .append("unitPrice", new Decimal128(price))
            .append("taxRate", new Decimal128(rate));

        collection.insertOne(document);
    }
}
```

If `BigDecimal` exceeds Decimal128's representable range, conversion may be rejected per the driver contract. Never silently cast to `Double` just to force an unrepresentable financial value into the database.

### 23.2. Using `Decimal128.parse`

```java
Decimal128 amount = Decimal128.parse("123.45");
```

Useful when input is a valid decimal string, though API-layer validation is still required. For currency, inputs must not accept arbitrary strings or special values outside the contract.

### 23.3. Reading Decimal128 Back as BigDecimal

```java
Document line = collection.find(
    new Document("_id", "LINE-JAVA-1")
).first();

if (line != null) {
    Decimal128 bsonDecimal =
        line.get("unitPrice", Decimal128.class);

    BigDecimal price = bsonDecimal.bigDecimalValue();

    System.out.println(price.toPlainString());
}
```

Before calling `bigDecimalValue()`, verify the value is non-null and a finite Decimal128 supported by the application. Do not convert to `double` just to format currency, as that can lose the desired decimal representation.

### 23.4. Reading Aggregation Results in Java

Example computing line total and rounding to two decimal places on the server:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.Decimal128;

import java.math.BigDecimal;
import java.util.List;

public final class DecimalAggregationExample {

    public static BigDecimal calculate(
            MongoCollection<Document> collection,
            String lineId
    ) {
        Bson match = new Document("$match",
            new Document("_id", lineId));

        Document raw = new Document("$multiply",
            List.of("$quantity", "$unitPrice"));

        Bson project = new Document("$project",
            new Document("_id", 0)
                .append("roundedAmount",
                    new Document("$round", List.of(raw, 2))));

        Document result = collection.aggregate(
            List.of(match, project)
        ).first();

        if (result == null) {
            throw new IllegalArgumentException(
                "Line not found: " + lineId
            );
        }

        Decimal128 bsonAmount = result.get(
            "roundedAmount",
            Decimal128.class
        );

        if (bsonAmount == null) {
            throw new IllegalStateException(
                "Rounded amount missing or not decimal"
            );
        }

        return bsonAmount.bigDecimalValue();
    }
}
```

This snippet relies on a schema where `quantity` is numeric and `unitPrice` is Decimal128 so `$multiply` produces Decimal128. In production, handle special values, nulls, driver errors, and data validation policies.

### 23.5. Rounding Modes in Java Do Not Automatically Match MongoDB

Java `BigDecimal` supports multiple `RoundingMode` values, for example:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal value = new BigDecimal("2.5");

BigDecimal halfEven = value.setScale(0, RoundingMode.HALF_EVEN);
// 2

BigDecimal halfUp = value.setScale(0, RoundingMode.HALF_UP);
// 3
```

MongoDB `$round` uses **half-even** on ties. If business logic uses `HALF_UP` in Java while using `$round` in aggregation, exact midpoint values will yield different results. Standardize rounding policy across services, database, reports, import/export, and UI.

### 23.6. DTOs, JSON, and API Contracts

If an API returns:

```json
{
  "amount": 19.95
}
```

a JavaScript client will parse it as a Double-precision Number. If the system must preserve decimals end-to-end, use decimal strings:

```json
{
  "amount": "19.95",
  "currency": "USD"
}
```

or integer minor units:

```json
{
  "amountMinor": 1995,
  "currency": "USD"
}
```

Which is better depends on the system contract. Never casually pick the first format and expect every client and language to preserve Decimal128.

---

## 24. Index Utilization and Computation Cost

Aggregation lets you compute many fields directly in MongoDB, but that does not mean every expression uses indexes efficiently.

### 24.1. Place `$match` Early When Appropriate

```javascript
db.orderLines.aggregate([
  {
    $match: {
      orderId: "O100"
    }
  },
  {
    $set: {
      lineSubtotal: {
        $multiply: [
          "$quantity",
          "$unitPrice"
        ]
      }
    }
  }
]);
```

If an index exists on `orderId`, the server can narrow down the document set before multiplying values. This is generally far more efficient than computing arithmetic across the entire collection before filtering.

### 24.2. Filtering on Expressions Can Restrict Index Usage

Example:

```javascript
db.orderLines.find({
  $expr: {
    $gt: [
      {
        $multiply: [
          "$quantity",
          "$unitPrice"
        ]
      },
      NumberDecimal("100")
    ]
  }
});
```

MongoDB must evaluate the expression to know the line amount, and cannot simply use a single index on `quantity` or `unitPrice` as a direct range condition. Depending on server version and query shape, certain `$expr` expressions can be optimized, but **never assume dynamic computations are automatically indexable**.

If this is a critical, frequent filter, consider storing `lineSubtotal` as a derived field and keeping it synchronized on updates; an index on `lineSubtotal` can then be used. The trade-off is that updates to `quantity`/`unitPrice` must also update the precomputed field and its indexes.

### 24.3. `$group` Can Be Memory-Intensive

An aggregation summing millions of lines must read and group many documents. A selective index helps filter the input, yet does not make summing all matching lines zero-cost.

When dashboards repeatedly compute the same totals, pre-aggregation or the computed pattern can outperform recalculating every time; this requires update rules, reconciliation, and late-arriving data handling.

### 24.4. Arithmetic Does Not Replace Data Optimization

If a pipeline still returns too many documents, network transfer, BSON decoding, and Java mapping remain expensive. Server-side arithmetic reduces raw data transfer in some scenarios, but measure execution plans and end-to-end latency to decide where computation belongs.

---

## 25. Error-Prone Business Scenarios

### Scenario A — Total Drifts Due to Double

Unit prices arrive as JSON number `0.1` and are summed repeatedly as binary floating-point numbers. Totals can suffer minor representation drift.

**How to handle:** define a decimal contract from input onward, consistently using Decimal128/`BigDecimal` or integer minor units; never cast to decimal after Double arithmetic has introduced drift and treat it as fully fixed.

### Scenario B — Half-Even Differs from HALF_UP

Value `2.5`:

- MongoDB `$round(..., 0)` chooses **2** via half-even.
- Java `BigDecimal.setScale(0, HALF_UP)` gives **3**.

**How to handle:** standardize rounding policy at the domain level. Do not label both vaguely as "standard rounding."

### Scenario C — Truncating Negative Numbers with `$floor`

If `-1.9` is truncated toward zero, it must become `-1`. `$floor` returns `-2`.

**How to handle:** use `$trunc` when business logic requires dropping fractional digits toward zero.

### Scenario D — Division by Zero

A report calculates `completed / total` when `total = 0`. Using bare `$divide` can fail the query.

**How to handle:** define an "undefined" state, guard the denominator, and distinguish `0` from missing/null.

### Scenario E — Averaging When Data Contains Strings

A collection has `scores: [80, "90", 100]`; `$avg` ignores non-numeric values rather than automatically parsing `"90"` as intended.

**How to handle:** validate and convert types intentionally; never trust accumulators to clean dirty data.

### Scenario F — Rounding Each Line Before Summing

Two tax lines `0.005` and `0.005` sum to `0.00` if each line is rounded half-even, yet `0.01` if summed first and then rounded.

**How to handle:** specify calculation and rounding order explicitly in the invoicing engine.

### Scenario G — Integer Minor Units Overflow

Prices are stored as Int64, but multiplying by a large quantity exceeds bounds. MongoDB may promote types or hit overflow depending on the operator; if implicitly promoted to Double, exact integer precision can be lost.

**How to handle:** validate ranges, design business bounds, and convert types intentionally. Do not rely on automatic promotion/overflow to preserve financial accuracy.

### Scenario H — API Strips Decimal128

MongoDB returns Decimal128, but the JSON layer serializes it as a plain number, and the JavaScript frontend treats it as a Double for further math.

**How to handle:** define the DTO contract as decimal strings or minor units, paired with consistent client parsing/formatting rules.

---

## 26. Practice Exercises and Hints

### Exercise 1 — Line Item Total

Line item:

```javascript
{
  quantity: 4,
  unitPrice: NumberDecimal("12.75")
}
```

Write `$multiply` and determine the result.

**Hint:**

```javascript
{
  $multiply: [
    "$quantity",
    "$unitPrice"
  ]
}
```

The arithmetic result is **51.00**.

### Exercise 2 — Difference Between `$round` and `$trunc`

Given `NumberDecimal("8.987")` and `place = 2`:

- `$round` gives **8.99**.
- `$trunc` gives **8.98**.

Try the negative case `-8.987` and explain why the two operations still differ.

### Exercise 3 — Half-Even

Predict:

```javascript
{ $round: [NumberDecimal("4.5"), 0] }
{ $round: [NumberDecimal("5.5"), 0] }
{ $round: [NumberDecimal("-2.5"), 0] }
```

**Answer:** the values are **4**, **6**, and **-2** respectively; on exact midpoints, the candidate with an even units digit is chosen.

### Exercise 4 — Preventing Division by Zero

Write an expression for `completed / total × 100` rounded to 2 decimal places, returning `null` when `total` is `0`.

**Hint:** outer `$cond`, `$eq` checking the denominator, inner `$divide`, `$multiply`, `$round`, and Decimal128. Extend validation for null/missing.

### Exercise 5 — Decimal128 or Double?

A service receives prices `"0.10"` and `"0.20"` in a payload. Explain the difference between:

```javascript
NumberDecimal("0.10")
NumberDecimal("0.20")
```

and the Double values `0.1`, `0.2`. Why is converting to Decimal128 **after already computing in Double** not an optimal strategy for ensuring accuracy?

### Exercise 6 — `$sum` in `$project` vs. `$group`

Document:

```javascript
{
  studentId: "S1",
  classId: "C1",
  scores: [80, 90, 100]
}
```

Explain the difference between:

```javascript
{ $project: { total: { $sum: "$scores" } } }
```

and:

```javascript
{
  $group: {
    _id: "$classId",
    total: { $sum: "$scores" }
  }
}
```

**Hint:** expressions outside `$group` can traverse an array under single-operand rules; the `$group` accumulator does not treat an array as a number. Compute each document's sum before `$group`.

### Exercise 7 — Invoice Rounding Policy

Two lines have raw tax `0.005`, `0.005`. Compute the total when:

1. Rounding each line first, then summing.
2. Summing first, then rounding once.

Explain why policy must be defined before implementing the pipeline.

### Exercise 8 — Reading Decimal128 in Java

Write code reading a `Decimal128` `total` field from a `Document`, converting it to `BigDecimal`, and formatting it to two decimal places with `toPlainString()` after `setScale(2, ...)` using an explicit `RoundingMode`.

**Hint:** do not pass through `double` in between; check for null and special values.

### Exercise 9 — Amount After Discount

Document:

```javascript
{
  subtotal: NumberDecimal("80.00"),
  discountRate: NumberDecimal("0.125")
}
```

Write the expressions:

- `discountAmount = $round($multiply(...), 2)`.
- `net = $subtract(subtotal, discountAmount)`.

**Answer:** discount **10.00**, remaining **70.00**.

### Exercise 10 — Converting to Minor Units

Given `grandTotal = NumberDecimal("56.03")`, use `$multiply`, `$round`, and `$toLong` to produce **5603** minor units. State the assumptions regarding currency scale, range, and rounding policy.

---

## 27. Misconceptions to Avoid

| Misconception | Correct Understanding |
| --- | --- |
| "All BSON numbers are the same." | Int32, Int64, Double, and Decimal128 differ in range, precision, and conversion rules. |
| "Double stores every decimal fraction accurately." | Many values like `0.1` have no exact binary representation. |
| "Decimal128 has infinite precision." | Decimal128 has 34 significant digits and a finite range. |
| "Converting Double to Decimal128 at the end fixes all prior errors." | It does not restore intended decimals if precision was already lost or miscomputed earlier. |
| "`$round` always rounds .5 up." | MongoDB uses half-even on ties. |
| "`$round` and `$trunc` are equivalent." | One rounds to nearest; the other truncates toward zero. |
| "`$trunc` on negative numbers matches `$floor`." | For `-1.9`, trunc is `-1` while floor is `-2`. |
| "`$ceil` and `$floor` only differ from `$round` by name." | They round directionally toward +∞ and -∞. |
| "`place = -2` keeps two digits after the decimal point." | Negative `place` rounds/truncates to the left of the decimal point, e.g., hundreds. |
| "Rounding per line or after summing is always the same." | They can diverge because rounding does not distribute over addition. |
| "MongoDB automatically knows invoice rounding laws." | Rules must be defined by the domain, including taxes and currency. |
| "`$divide` by 0 automatically returns null." | Division by zero can throw an error; guard denominators. |
| "`$sum` always behaves like `$add`." | `$sum` has distinct accumulator/expression rules and non-numeric handling. |
| "`$sum` on an array in `$group` automatically sums each element." | The `$group` accumulator does not traverse arrays like a single-operand expression in `$project`. |
| "`$avg` automatically converts numeric strings to numbers." | Intentional validation/conversion is required. |
| "Dividing two integers always returns an integer." | `$divide` can return Double; a Decimal128 operand yields a decimal result. |
| "A number displayed as 20.00 means BSON stores fixed scale 2." | Presentation formatting and numeric precision/scale must be handled separately. |
| "JSON numbers preserve Decimal128 in all clients." | Many clients use binary floating point; define an explicit API contract. |
| "`$expr` computations on a field always use indexes like direct ranges." | Dynamic expressions can limit how indexes are utilized. |
| "Computing in aggregation costs no CPU." | Expressions, `$map`, `$group`, and conversions have cost; measure them. |

## 28. Process for Designing Safe Numeric Calculations

A development team should clarify step by step:

1. **Data units:** USD, VND, cents, percentage, `0–1` ratio, milliseconds, or seconds?
2. **Storage types:** Int32/Int64, Double, Decimal128; which types are allowed per field?
3. **Input sources:** decimal strings, `BigDecimal`, integer minor units; is anything converted to Double on the client?
4. **Value domain:** min/max bounds; are negative, null, zero, or missing values permitted?
5. **Business formulas:** order of discounts, taxes, fees, and exchange rates?
6. **Rounding policy:** half-even, half-up, or another rule; which `place` and at which step?
7. **Aggregation point:** round per line, per tax rate, per invoice, or only on display?
8. **Data invariants:** does the invoice total equal the sum of lines after applying policy?
9. **API contract:** decimal strings, BSON Extended JSON, or integer minor units?
10. **Performance:** does `$match` narrow the dataset before computing; are computed fields/indexes needed?
11. **Reconciliation:** do Java `BigDecimal`, aggregation, and reports agree on edge cases?
12. **Monitoring:** log error codes/record IDs instead of silently swallowing conversion errors.

Example of a clear billing workflow:

```text
Input decimal string / integer minor units
               |
               v
       Validate schema + currency
               |
               v
     Convert to standard numeric type
               |
               v
     Compute raw values with sufficient precision
               |
               v
     Apply rounding per policy
               |
               v
     Verify invariants and bounds
               |
               v
      Store/reconcile BSON Decimal128
               |
               v
    Return API response per unified contract
```

---

## 29. Official MongoDB Documentation

- [Aggregation Expressions](https://www.mongodb.com/docs/manual/reference/operator/aggregation/): list of aggregation expressions.
- [`$add`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/add/), [`$subtract`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/subtract/), [`$multiply`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/multiply/), [`$divide`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/divide/): basic arithmetic operations.
- [`$mod`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/mod/), [`$abs`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/abs/): remainder and absolute value.
- [`$round`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/round/) and [`$trunc`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/trunc/): rounding and truncation.
- [`$ceil`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/ceil/) and [`$floor`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/floor/): directed rounding.
- [`$sum`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/) and [`$avg`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/avg/): sums and averages.
- [`$toDecimal`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDecimal/) and [`$convert`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/): controlled type conversion.
- [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): Int32, Int64, Double, Decimal128, and other BSON types.
- [Decimal128 in MongoDB](https://www.mongodb.com/docs/manual/tutorial/model-monetary-data/): considerations for modeling monetary data.
- [Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/): working with BSON and aggregation in Java.

Exact behavior, range checks, and data-type details may vary by MongoDB server and driver version. In real deployments, verify documentation against your running version and test edge cases against business requirements.

## 30. Conclusion

MongoDB provides a powerful suite of arithmetic expressions for computing directly on documents and grouped results. `$add`, `$subtract`, `$multiply`, `$divide`, `$mod`, `$sum`, and `$avg` solve common computational tasks; `$round`, `$trunc`, `$ceil`, and `$floor` express **different rounding rules**.

When handling money, **Decimal128 represents decimal values accurately within 34 significant digits**, avoiding many inaccuracies inherent to binary floating point. Yet Decimal128 does not offer infinite precision and does not choose rounding policies for you. Standardize types from input to driver, guard against null/zero/overflow, decide when rounding occurs, and keep the same contract across MongoDB, Java, and APIs.

**Accurate arithmetic results = right formula + right numeric type + right unit + right rounding rule + valid input data.**
