# Numeric Functions, Rounding, and Data Type Conversions in Cypher

In Neo4j's **property graph**, each node and relationship can store numeric, string, Boolean, or temporal properties. A retail management application might store unit prices as integers and review scores as floating-point numbers, whereas CSV imports arrive as strings. When querying with **Cypher**, arithmetic, rounding, and type conversions govern both result accuracy and the ability to filter data using indexes.

This lesson belongs to the **Expressions and Functions** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. The focus is on numeric functions, rounding rules, converting values across common types, and applying them to nodes and relationships. The examples also demonstrate passing parameters from the Java Driver, consuming results in Spring Data Neo4j, and considerations for processing imported data.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish `INTEGER` and `FLOAT` types in Cypher; recognize how numeric types affect division and precision.
- Use `abs()`, `ceil()`, `floor()`, `round()`, `sign()`, `sqrt()`, and other appropriate math functions.
- Explain why **rounding**, **truncating the fractional part**, and **casting to an integer** are three distinct operations.
- Convert between numbers, strings, and Booleans using `toInteger()`, `toFloat()`, `toString()`, and `toBoolean()`, while handling missing or invalid data.
- Combine `CASE`, `coalesce()`, and `IS NULL` with calculations that may encounter `null` or a zero denominator.
- Compute values from node and relationship properties, build aggregate reports, and validate CSV import inputs.
- Write parameterized queries, map results in the Java Driver, and evaluate currency storage, rounding, and index optimization strategies.

## 2. Preparing Practice Graph Data

Examples starting with `RETURN` or `WITH` can run standalone. To practice `MATCH` queries, initialize the graph in a **learning database**, never on production data.

~~~cypher
MERGE (an:NumericDemoCustomer {customerId: 'NC-001'})
SET an.name = 'An', an.active = true

MERGE (binh:NumericDemoCustomer {customerId: 'NC-002'})
SET binh.name = 'Binh', binh.active = false

MERGE (chi:NumericDemoCustomer {customerId: 'NC-003'})
SET chi.name = 'Chi', chi.active = true

MERGE (book:NumericDemoProduct {sku: 'NP-001'})
SET book.name = 'Cypher Book',
    book.priceVnd = 320000,
    book.stock = 12,
    book.rating = 4.37

MERGE (course:NumericDemoProduct {sku: 'NP-002'})
SET course.name = 'Neo4j Course',
    course.priceVnd = 850000,
    course.stock = 4,
    course.rating = 4.85

MERGE (mouse:NumericDemoProduct {sku: 'NP-003'})
SET mouse.name = 'Computer Mouse',
    mouse.priceVnd = 199000,
    mouse.stock = 0
REMOVE mouse.rating

MERGE (an)-[purchase1:NUMERIC_DEMO_BOUGHT]->(book)
SET purchase1.quantity = 2,
    purchase1.discountPercent = 10

MERGE (binh)-[purchase2:NUMERIC_DEMO_BOUGHT]->(course)
SET purchase2.quantity = 1
REMOVE purchase2.discountPercent;
~~~

Data model:

~~~mermaid
flowchart LR
    A["An:NumericDemoCustomer"] -->|"BOUGHT: quantity=2, discountPercent=10"| P1["Cypher Book:NumericDemoProduct"]
    B["Binh:NumericDemoCustomer"] -->|"BOUGHT: quantity=1"| P2["Neo4j Course:NumericDemoProduct"]
    C["Chi:NumericDemoCustomer"] 
    P3["Computer Mouse:NumericDemoProduct"]
~~~

| Product | `priceVnd` (INTEGER) | `stock` (INTEGER) | `rating` (FLOAT) |
| --- | ---: | ---: | ---: |
| Cypher Book | 320,000 | 12 | 4.37 |
| Neo4j Course | 850,000 | 4 | 4.85 |
| Computer Mouse | 199,000 | 0 | *No property* |

The `NUMERIC_DEMO_BOUGHT` relationship holds quantity and discount percentage. Binh's transaction has no `discountPercent`, and Chi has no purchase relationship. These two cases help test `null` handling.

## 3. Numeric Types in Cypher and Basic Operators

### 3.1. INTEGER and FLOAT

Cypher distinguishes two key numeric types:

| Type | Nature | Examples | Use Cases |
| --- | --- | --- | --- |
| `INTEGER` | Signed integer, typically 64-bit | `42`, `-7`, `320000` | Quantities, sequential codes, currency in smallest unit |
| `FLOAT` | Double-precision floating-point number | `3.14`, `-0.25`, `4.85` | Ratios, measurements, ratings, decimal calculations |

Illustrative operations:

~~~cypher
RETURN
  8 + 3 AS total,
  8 - 3 AS difference,
  8 * 3 AS product,
  8 / 3 AS integerDivision,
  8 / 3.0 AS floatingDivision,
  8 % 3 AS remainder,
  2 ^ 3 AS power;
~~~

Here `integerDivision = 2`, `floatingDivision` is approximately `2.6666666666666665`, and `remainder = 2`. When both operands are integers, integer division discards the fractional part. If you want a `FLOAT` result, use a floating-point literal on at least one side or convert explicitly.

~~~cypher
RETURN
  7 / 2 AS resultA,
  7 / 2.0 AS resultB,
  toFloat(7) / 2 AS resultC;
~~~

Results are `3`, `3.5`, and `3.5`.

### 3.2. Operator Precedence and Parentheses

~~~cypher
RETURN
  2 + 3 * 4 AS withoutParentheses,
  (2 + 3) * 4 AS withParentheses,
  100 * (1 - 0.15) AS afterDiscount;
~~~

The results are `14`, `20`, and approximately `85.0`, respectively. In business formulas, parentheses are usually more valuable than memorizing every precedence level.

Prefer immediately readable formulas:

~~~cypher
WITH 320000 AS price, 2 AS quantity, 10 AS discountPercent
RETURN
  price * quantity AS subtotal,
  price * quantity * (100 - discountPercent) / 100 AS payableVnd;
~~~

Under integer division rules, `payableVnd = 576000`. In real payment systems, explicitly specify what happens when division does not yield an integer and evaluate overflow risks in intermediate expressions.

### 3.3. Numeric Bounds and Precision

64-bit `INTEGER` has a finite range. An intermediate product like `price * quantity * rate` can overflow integer bounds even if the final value after division is small. `FLOAT` has a wider range but cannot represent every decimal fraction exactly; calculations like `0.1 + 0.2` should not be tested for exact equality against `0.3`.

~~~cypher
RETURN
  0.1 + 0.2 AS computed,
  0.3 AS expected,
  abs((0.1 + 0.2) - 0.3) AS difference;
~~~

For measurements, you can compare the difference against an acceptable tolerance. For monetary data, choose the appropriate **storage unit** and **rounding rules** before designing formulas.

## 4. Common Mathematical Functions

### 4.1. Absolute Value and Sign Functions

| Function | Purpose | Example | Result |
| --- | --- | --- | --- |
| `abs(x)` | Absolute value | `abs(-12)` | `12` |
| `sign(x)` | Sign of a number: negative, 0, or positive | `sign(-3.5)` | `-1` |

~~~cypher
RETURN
  abs(-120) AS distanceFromZero,
  sign(-8) AS negativeSign,
  sign(0) AS zeroSign,
  sign(8) AS positiveSign;
~~~

The results are `120`, `-1`, `0`, and `1`, respectively. In business logic, `abs` can measure the discrepancy between actual and expected inventory; `sign` helps classify changes as increase, decrease, or unchanged.

### 4.2. Square Root, Exponentiation, and Logarithms

| Expression | Meaning | Example |
| --- | --- | --- |
| `sqrt(x)` | Square root | `sqrt(81)` → `9.0` |
| `x ^ y` | Exponentiation | `2 ^ 4` → `16.0` or an equivalent numeric representation depending on display |
| `log(x)` | Natural logarithm | `log(1)` → `0.0` |
| `log10(x)` | Base-10 logarithm | `log10(1000)` → `3.0` |
| `exp(x)` | Base-`e` exponential | `exp(0)` → `1.0` |

~~~cypher
RETURN
  sqrt(144) AS root,
  2 ^ 5 AS power,
  log10(100) AS baseTenLog,
  exp(0) AS expZero;
~~~

These functions are useful in weight calculations, data analysis, and graph scoring models. Mind the **domain**: the square root of a negative number or logarithm of a non-positive number is not a valid real result for business formulas. Guard inputs with `CASE` and handle special values per application policy.

### 4.3. Random Numbers and Trigonometric Functions

`rand()` generates a pseudo-random `FLOAT` in the range from 0 (inclusive) to 1 (exclusive):

~~~cypher
RETURN rand() AS randomValue;
~~~

The output changes across executions. It can be used to generate sample data, but is unsuitable for stable identifier keys or cryptographic randomness.

Cypher also includes trigonometric functions such as `sin()` and `cos()` for angle data or scientific computations:

~~~cypher
RETURN
  sin(0.0) AS sineZero,
  cos(0.0) AS cosineZero;
~~~

The two results are `0.0` and `1.0`. For map routing or spatial distance problems, consider Neo4j's `point` type and spatial functions instead of writing simple trigonometric approximations manually.

## 5. Rounding and Controlling Decimal Places

### 5.1. How Do ceil(), floor(), and round() Differ?

| Expression | Meaning | Result |
| --- | --- | --- |
| `ceil(3.2)` | Smallest integer value not less than 3.2 | `4.0` |
| `floor(3.8)` | Largest integer value not greater than 3.8 | `3.0` |
| `round(3.8)` | Round to the nearest integer value | `4.0` |
| `ceil(-3.2)` | Round toward positive infinity | `-3.0` |
| `floor(-3.2)` | Round toward negative infinity | `-4.0` |

Especially with negative numbers, `ceil` and `floor` are not equivalent to “dropping the decimal part”:

~~~cypher
RETURN
  ceil(-3.8) AS roundedUp,
  floor(-3.8) AS roundedDown,
  toInteger(-3.8) AS truncated;
~~~

Results: `roundedUp = -3.0`, `roundedDown = -4.0`, `truncated = -3`. `toInteger(-3.8)` truncates toward 0, whereas `floor(-3.8)` moves toward negative infinity.

### 5.2. round() with Decimal Precision

`round(number)` rounds to the nearest integer as a numeric value; `round(number, precision)` lets you specify the number of decimal places.

~~~cypher
RETURN
  round(4.376) AS zeroDecimalPlaces,
  round(4.376, 1) AS oneDecimalPlace,
  round(4.376, 2) AS twoDecimalPlaces;
~~~

The results are `4.0`, `4.4`, and `4.38`, respectively.

Applying this to ratings:

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  p.sku,
  p.name,
  p.rating AS exactStoredRating,
  round(p.rating, 1) AS displayedRating
ORDER BY p.sku;
~~~

Cypher Book has `displayedRating = 4.4`, Neo4j Course has `displayedRating` around `4.9` per rounding rules and floating-point representation, and Computer Mouse has `null` because `rating` is missing.

**Note on exact boundary values:** values with `5` at the rounding cutoff digit can be affected by *rounding mode* and `FLOAT` representation. Do not infer monetary rounding rules from non-boundary examples.

### 5.3. Rounding Modes

Modern Cypher versions support `round(value, precision, mode)` to specify a rounding mode, such as `HALF_UP` or `HALF_EVEN` passed as a string. For example:

~~~cypher
RETURN
  round(2.5, 0, 'HALF_UP') AS halfUp,
  round(2.5, 0, 'HALF_EVEN') AS halfEven;
~~~

Here, `HALF_UP` returns `3.0` and `HALF_EVEN` returns `2.0`. `HALF_EVEN` favors the even digit at the rounding position on exact ties; this rule is commonly used to reduce cumulative bias in statistical computations.

No single rule fits every domain. Tax, banking, accounting, and grading systems may mandate different rules. Define the rule first, test exact midpoint values, and verify behavior against your **running Neo4j version**.

### 5.4. Rounding Is Not the Same as Type Casting

~~~cypher
RETURN
  toInteger(3.9) AS truncatePositive,
  toInteger(-3.9) AS truncateNegative,
  round(3.9) AS roundPositive,
  floor(3.9) AS floorPositive,
  ceil(3.1) AS ceilPositive;
~~~

Results: `3`, `-3`, `4.0`, `3.0`, `4.0`.

- `toInteger(x)` takes the integer part toward 0 for standard floating-point values.
- `round(x)` takes the nearest value according to rounding rules.
- `floor(x)` always rounds toward negative infinity.
- `ceil(x)` always rounds toward positive infinity.

If an API requires an **`INTEGER` after rounding**, write `toInteger(round(x, 0))`; ensure the rounded result remains within integer range.

### 5.5. Practical Example: Required Boxes

Suppose each box holds at most 6 items. To pack 17 items:

~~~cypher
WITH 17 AS itemCount, 6 AS capacity
RETURN
  toFloat(itemCount) / capacity AS rawBoxes,
  toInteger(ceil(toFloat(itemCount) / capacity)) AS requiredBoxes;
~~~

The result is approximately `2.8333333333333335` boxes and **3 boxes** required. `ceil` fits when capacity cannot fall short. If item count or capacity can be zero or missing, add a guard check before dividing.

### 5.6. Distinguishing Stored Data from Presentation Data

If `rating = 4.376`, displaying `round(rating, 1) = 4.4` is reasonable for the UI. However, **overwriting** `rating` with `4.4` loses precision needed for more accurate downstream aggregations.

Instead:

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  p.name,
  p.rating AS storedRating,
  round(p.rating, 1) AS ratingForDisplay;
~~~

Only persist rounded properties when business requirements explicitly call for changing stored data.

## 6. Converting Between Data Types

### 6.1. Common Conversion Functions

| Function | Target Type | Example | Result |
| --- | --- | --- | --- |
| `toInteger(x)` | `INTEGER` | `toInteger('42')` | `42` |
| `toFloat(x)` | `FLOAT` | `toFloat('3.75')` | `3.75` |
| `toString(x)` | `STRING` | `toString(42)` | `'42'` |
| `toBoolean(x)` | `BOOLEAN` | `toBoolean('true')` | `true` |

~~~cypher
RETURN
  toInteger('120') AS quantity,
  toFloat('4.25') AS score,
  toString(320000) AS priceText,
  toBoolean('false') AS disabled;
~~~

The results have the respective types `INTEGER`, `FLOAT`, `STRING`, and `BOOLEAN`. When importing CSV data, these functions are especially important because input column values are usually read as strings.

### 6.2. Converting Strings to Numbers

~~~cypher
RETURN
  toInteger('320000') AS priceVnd,
  toFloat('4.85') AS rating,
  toInteger('007') AS sequenceNumber,
  toFloat('2') AS decimalNumber;
~~~

The results are `320000`, `4.85`, `7`, and `2.0`, respectively. Converting `'007'` to a number drops leading zeros; if `'007'` is an **identifier code** rather than a quantity, store it as `STRING`.

Decimal strings should use a **period** matching the numeric format accepted by Cypher's parser. Never assume `'1,25'` or `'1.250,00'` will be parsed according to locale conventions; normalize and validate first.

Example with extra whitespace:

~~~cypher
WITH '   320000   ' AS rawPrice
RETURN
  toInteger(trim(rawPrice)) AS normalizedPriceVnd;
~~~

Result: `320000`. `trim()` removes leading/trailing spaces; if data includes thousands separators or currency symbols, add appropriate preprocessing rules.

### 6.3. Converting FLOAT to INTEGER

~~~cypher
RETURN
  toInteger(3.9) AS positive,
  toInteger(-3.9) AS negative,
  toInteger(round(3.9)) AS roundThenConvert;
~~~

Results: `positive = 3`, `negative = -3`, and `roundThenConvert = 4`. Avoid using `toInteger()` to “round” a payment amount: it performs truncation with rules distinct from `round()`.

### 6.4. Converting to String for UI and APIs

~~~cypher
WITH 320000 AS priceVnd, 12 AS stock
RETURN
  'Price: ' || toString(priceVnd) || ' VND' AS priceLabel,
  'Stock: ' || toString(stock) AS stockLabel;
~~~

Results: `Price: 320000 VND` and `Stock: 12`. `toString()` is **not a locale-aware currency formatter**; inserting thousands separators, currency symbols, or locale-specific formatting should be handled consistently in the presentation layer.

When an application needs both numeric values for computation and strings for display, return two separate columns instead of converting a numeric property to a string and reusing it in math:

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  p.sku,
  p.priceVnd AS numericPrice,
  toString(p.priceVnd) AS priceText
ORDER BY p.sku;
~~~

### 6.5. Converting Strings to Boolean

~~~cypher
RETURN
  toBoolean('true') AS enabled,
  toBoolean('false') AS disabled;
~~~

Results: `true` and `false`. If an input field uses values like `'yes'`, `'no'`, `'1'`, or `'0'`, do not assume `toBoolean()` understands your business rules. Map them explicitly:

~~~cypher
WITH 'yes' AS rawFlag
WITH toLower(trim(rawFlag)) AS normalized
RETURN
  CASE
    WHEN normalized IN ['true', 'yes', '1'] THEN true
    WHEN normalized IN ['false', 'no', '0'] THEN false
    ELSE null
  END AS activeFlag;
~~~

With `rawFlag = 'yes'`, the result is `true`. Unrecognized inputs return `null` so the application layer can report a data error or request clarification.

### 6.6. The “OrNull” Conversion Functions

Cypher provides functions such as `toIntegerOrNull()`, `toFloatOrNull()`, `toStringOrNull()`, and `toBooleanOrNull()` to convert values by returning `null` when an input cannot be parsed into the target type, rather than letting an incompatible input type break the whole query.

~~~cypher
RETURN
  toIntegerOrNull('120') AS validInteger,
  toIntegerOrNull('not a number') AS invalidInteger,
  toFloatOrNull('4.25') AS validFloat,
  toFloatOrNull('invalid') AS invalidFloat;
~~~

Results: `validInteger = 120`, `invalidInteger = null`, `validFloat = 4.25`, `invalidFloat = null`. Standard conversion functions may also return `null` for **some** invalid strings; the advantage of the `OrNull` variants is more consistent handling across non-castable input types. When implementing in production, check signatures and support in your Neo4j version.

**Do not conflate “conversion failed” with “value not provided”.** Both can yield `null`, yet their business meanings differ. You can retain the raw string and return an error flag to track data quality.

### 6.7. Null and Type Conversions

~~~cypher
RETURN
  toInteger(null) AS a,
  toFloat(null) AS b,
  toString(null) AS c,
  coalesce(toIntegerOrNull(null), 0) AS d;
~~~

The first three columns are `null`; column `d = 0`. Only use `coalesce(..., 0)` if missing data may legitimately be interpreted as zero. When a price is missing, **“no price yet”** is not **“price is 0”**.

### 6.8. Converting to Temporal Types

“Type conversion” is not limited to numbers and strings. When data contains ISO 8601 timestamps, Cypher provides functions to construct temporal values:

~~~cypher
RETURN
  date('2026-11-25') AS orderDate,
  datetime('2026-11-25T09:00:00+07:00') AS orderTime,
  duration('P2D') AS shippingDuration;
~~~

`date(...)` creates a `DATE`, `datetime(...)` creates a date-time with timezone or offset when supplied, and `duration(...)` creates a duration. This is **parsing into a target temporal type**, not using `toInteger()` on date strings. Real-world temporal data requires standardized timezones and input formats.

## 7. Handling null, Missing Types, and Invalid Calculations

### 7.1. Non-Existent Properties Yield null

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  p.sku,
  p.rating AS rating,
  round(p.rating, 1) AS roundedRating,
  coalesce(round(p.rating, 1), 0.0) AS ratingOrZero
ORDER BY p.sku;
~~~

For Computer Mouse, `rating` and `roundedRating` are `null`. `ratingOrZero` becomes `0.0` per the query's fallback rule, but that **does not mean** the product actually received a 0-star rating. When you need to distinguish both cases, also return `p.rating IS NULL AS missingRating`.

### 7.2. Using CASE to Avoid Division by Zero

An average calculation may have a denominator of 0 or `null`:

~~~cypher
WITH 1000.0 AS total, 0 AS countItems
RETURN
  CASE
    WHEN countItems IS NULL OR countItems = 0 THEN null
    ELSE total / countItems
  END AS averagePerItem;
~~~

The query returns `null` per the rule “average is undefined”. Placing the guard condition directly inside `CASE` is clearer and safer than assuming an `AND` expression will always evaluate in a fixed order.

### 7.3. Using CASE to Guard Against Invalid Inputs Before Square Root

~~~cypher
UNWIND [9.0, 0.0, -4.0, null] AS value
RETURN
  value,
  CASE
    WHEN value IS NULL OR value < 0 THEN null
    ELSE sqrt(value)
  END AS validRoot;
~~~

Results: `sqrt(9) = 3.0`, `sqrt(0) = 0.0`; inputs `-4.0` and `null` return `null` according to the query's policy. You can replace `null` with a separate status column if you need to explain why an input is invalid to users.

### 7.4. Type Checking and Dirty Data

A property may be stored with the wrong type when data arrives from multiple sources. For example, an application expects `priceVnd` to be numeric, but ingested data contains the string `'320000'`. A query like `WHERE p.priceVnd > 200000` should not rely on Neo4j implicitly converting types.

Best practices are:

1. Validate and convert values during data ingestion.
2. Store numeric properties using true numeric types.
3. Pass query parameters with matching types.
4. Maintain constraints or data validation rules in the system.

Property types should remain consistent for fast queries, predictable outputs, and stable Java Driver/SDN mapping.

## 8. Calculations on Nodes and Relationships

### 8.1. Calculating Total Amount from quantity and discountPercent

Product price lives on the `NumericDemoProduct` node, while quantity and discount percentage live on the `NUMERIC_DEMO_BOUGHT` relationship:

~~~cypher
MATCH (c:NumericDemoCustomer)-[r:NUMERIC_DEMO_BOUGHT]->(p:NumericDemoProduct)
WITH
  c, p, r,
  p.priceVnd * r.quantity AS subtotalVnd,
  coalesce(r.discountPercent, 0) AS discountPercent
RETURN
  c.name AS customer,
  p.name AS product,
  subtotalVnd,
  discountPercent,
  subtotalVnd * (100 - discountPercent) / 100 AS payableVnd
ORDER BY customer;
~~~

Expected result:

| Customer | Subtotal Before Discount | Discount | Amount Payable |
| --- | ---: | ---: | ---: |
| An | 640,000 VND | 10% | 576,000 VND |
| Binh | 850,000 VND | 0% (default per example rule) | 850,000 VND |

If you want to compute using floating-point math and round to whole VND:

~~~cypher
MATCH (c:NumericDemoCustomer)-[r:NUMERIC_DEMO_BOUGHT]->(p:NumericDemoProduct)
WITH
  c, p,
  toFloat(p.priceVnd) * r.quantity *
    (1.0 - coalesce(r.discountPercent, 0) / 100.0) AS rawPayable
RETURN
  c.name AS customer,
  p.name AS product,
  rawPayable,
  toInteger(round(rawPayable, 0)) AS roundedPayableVnd
ORDER BY customer;
~~~

In this example, currency is rounded to whole VND units. **In a real production system**, accounting rules may require different conventions; floating-point numbers and `round` do not replace an exact monetary calculation model. Store currency in the smallest integer unit and apply standardized calculation/rounding rules; for operations requiring high decimal precision, process them in the Java layer using `BigDecimal`.

### 8.2. Rounding Ratings for Presentation

~~~cypher
MATCH (p:NumericDemoProduct)
WHERE p.rating IS NOT NULL
RETURN
  p.sku,
  p.name,
  p.rating AS rawRating,
  round(p.rating, 1) AS ratingOneDecimal
ORDER BY p.sku;
~~~

Only the two products that have ratings are returned. Filtering with `IS NOT NULL` prevents dashboards from confusing “no reviews yet” with “0 rating”.

### 8.3. OPTIONAL MATCH and Transaction Counts

~~~cypher
MATCH (c:NumericDemoCustomer)
OPTIONAL MATCH (c)-[r:NUMERIC_DEMO_BOUGHT]->(:NumericDemoProduct)
WITH
  c,
  count(r) AS purchaseRelations,
  sum(coalesce(r.quantity, 0)) AS purchasedUnits
RETURN
  c.name AS customer,
  purchaseRelations,
  purchasedUnits,
  CASE
    WHEN purchaseRelations = 0 THEN 'No purchases yet'
    ELSE 'Has purchased'
  END AS purchaseStatus
ORDER BY customer;
~~~

Chi has `purchaseRelations = 0` and `purchasedUnits = 0`. `count(r)` ignores `null` values from unmatched relationships; `coalesce(r.quantity, 0)` enables summing quantities per the example rule.

**Distinction:** if a relationship exists but lacks `quantity`, the expression above also counts that relationship's quantity as 0. When auditing data quality, also return `sum(CASE WHEN r IS NOT NULL AND r.quantity IS NULL THEN 1 ELSE 0 END)` to count transactions missing a quantity.

## 9. Aggregation Functions and Rounding Results

Aggregation functions `sum()`, `avg()`, `min()`, `max()`, and `count()` often pair with arithmetic expressions in reports.

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  count(*) AS productCount,
  sum(p.stock) AS totalStock,
  min(p.priceVnd) AS lowestPrice,
  max(p.priceVnd) AS highestPrice,
  round(avg(p.priceVnd), 2) AS averagePrice;
~~~

Sample results: `productCount = 3`, `totalStock = 16`, `lowestPrice = 199000`, `highestPrice = 850000`, and `averagePrice = 456333.33`.

### 9.1. Aggregations and null

For aggregations over expressions, `null` values are generally ignored:

~~~cypher
UNWIND [4.0, 5.0, null] AS score
RETURN
  count(*) AS totalRows,
  count(score) AS recordedScores,
  avg(score) AS averageRecorded,
  avg(coalesce(score, 0.0)) AS averageMissingAsZero;
~~~

Results:

- `totalRows = 3` because there are three rows;
- `recordedScores = 2` because only two scores are non-`null`;
- `averageRecorded = 4.5`;
- `averageMissingAsZero = 3.0`.

Therefore, do not wrap `coalesce(score, 0)` inside `avg()` merely to avoid a `null` result: it changes the denominator and statistical meaning.

### 9.2. When You Round Can Change the Sum

Computing per row and rounding **before summing** can differ from summing all values first and then rounding:

~~~cypher
UNWIND [1.26, 1.26, 1.26] AS amount
RETURN
  sum(round(amount, 1)) AS sumOfRounded,
  round(sum(amount), 1) AS roundedSum;
~~~

With single-decimal rounding: `sumOfRounded = 3.9` and `roundedSum = 3.8` (`FLOAT` values may have floating-point representations close to these numbers). The difference reflects **when the rule is applied**.

In billing or reporting, decide whether rounding occurs at the **transaction item**, **line item**, or **invoice total** level. The two strategies can accumulate discrepancies over large row counts.

## 10. Importing CSV Data and Validating Numbers

### 10.1. Why Does CSV Data Need Type Conversion?

When using `LOAD CSV WITH HEADERS`, cell values are read as **strings**. Storing `row.price` directly into `priceVnd` risks saving the string `'320000'` instead of the integer `320000`.

Import structure example (replace the path with your environment's actual CSV URL):

~~~cypher
LOAD CSV WITH HEADERS FROM $csvUrl AS row
WITH
  trim(row.sku) AS sku,
  toIntegerOrNull(trim(row.priceVnd)) AS priceVnd
WHERE sku IS NOT NULL AND sku <> '' AND priceVnd IS NOT NULL
MERGE (p:NumericDemoProduct {sku: sku})
SET p.priceVnd = priceVnd
RETURN count(p) AS processedRows;
~~~

In this sample query, `$csvUrl` is a URL parameter permitted by the Neo4j environment. For production, add error-row handling, input validation, and file/URL access policies. Do not silently drop rows with invalid numbers without logging them for investigation.

### 10.2. Classifying Valid and Invalid Strings Before Ingestion

~~~cypher
UNWIND [
  {code: 'A', rawPrice: '320000'},
  {code: 'B', rawPrice: '850000'},
  {code: 'C', rawPrice: 'unknown'},
  {code: 'D', rawPrice: ''}
] AS row
WITH row, trim(row.rawPrice) AS cleanText
WITH row,
     CASE
       WHEN cleanText = '' THEN null
       WHEN cleanText =~ '[0-9]+' THEN toIntegerOrNull(cleanText)
       ELSE null
     END AS parsedPrice
RETURN
  row.code AS code,
  row.rawPrice AS original,
  parsedPrice,
  CASE
    WHEN parsedPrice IS NULL THEN 'Needs review'
    ELSE 'Valid'
  END AS dataStatus
ORDER BY code;
~~~

Results: `A` and `B` are valid; `C` and `D` need review. The regex `[0-9]+` in this example accepts only **non-negative integers**—not minus signs, thousands separators, decimals, or currency symbols. If your domain allows other formats, adjust the validation rules to match your input specification.

### 10.3. Distinguishing Zero from Missing Values

~~~cypher
UNWIND ['0', '', '15'] AS input
RETURN
  input,
  CASE
    WHEN trim(input) = '' THEN null
    ELSE toIntegerOrNull(trim(input))
  END AS quantity;
~~~

Results: `'0' → 0`, `'' → null`, and `'15' → 15`. In inventory reporting, **missing quantity** and **quantity of 0** are two distinct states.

## 11. Integrating with the Java Driver and Spring Data Neo4j

### 11.1. Passing Properly Typed Parameters

Example query using integer VND prices, floating-point discount rate, and a minimum price threshold:

~~~cypher
MATCH (p:NumericDemoProduct)
WHERE p.priceVnd >= $minPriceVnd
RETURN
  p.sku AS sku,
  p.priceVnd AS originalPriceVnd,
  toInteger(
    round(p.priceVnd * (1.0 - $discountRate), 0)
  ) AS discountedPriceVnd
ORDER BY sku;
~~~

Here `$minPriceVnd` should be an integer and `$discountRate` a floating-point number between 0 and 1. For instance, `minPriceVnd = 200000` and `discountRate = 0.1` select Cypher Book and Neo4j Course.

Passing `'200000'` as a string may not behave as expected against the numeric predicate `p.priceVnd >= $minPriceVnd`. Convert values to the proper type **before** calling the driver rather than relying on implicit casting.

### 11.2. Java Driver Example

The code below illustrates querying and mapping; assume `Driver driver` is configured and lifecycle-managed in the infrastructure layer:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;
import java.util.List;

record PriceQuote(String sku, long originalVnd, long discountedVnd) {}

try (Session session = driver.session()) {
    List<PriceQuote> prices = session.executeRead(tx ->
        tx.run(
            """
            MATCH (p:NumericDemoProduct)
            WHERE p.priceVnd >= $minPriceVnd
            RETURN
              p.sku AS sku,
              p.priceVnd AS originalVnd,
              toInteger(
                round(p.priceVnd * (1.0 - $discountRate), 0)
              ) AS discountedVnd
            ORDER BY sku
            """,
            Values.parameters(
                "minPriceVnd", 200000L,
                "discountRate", 0.10
            )
        ).list(row -> new PriceQuote(
            row.get("sku").asString(),
            row.get("originalVnd").asLong(),
            row.get("discountedVnd").asLong()
        ))
    );

    prices.forEach(System.out::println);
}
~~~

Java's `long` fits 64-bit integers, while `double` fits floating-point numbers. For nullable fields, check `Value.isNull()` before calling `asLong()` or `asDouble()` and use nullable Java types when appropriate.

This example demonstrates query mechanics, not formal accounting rules. If a financial system requires exact precision to the smallest currency unit, design calculations with `BigDecimal` and explicit rounding rules in the business layer, then store the validated result as an `INTEGER` if within range.

### 11.3. Notes for Spring Data Neo4j

In Spring Data Neo4j, an entity can map:

- `Long` / `long` to integer properties, depending on nullability requirements;
- `Double` / `double` to floating-point properties;
- `String` to string properties;
- `Boolean` / `boolean` to Boolean properties.

When a property may be missing, prefer boxed types (such as `Long`, `Double`, `Boolean`) over primitives that cannot represent `null`.

For computed aliases in `RETURN`, define projections/DTOs with consistent column names and types. Avoid returning an `INTEGER` in one branch and a `STRING` in another for the same alias when the API expects a fixed type.

## 12. Optimizing Queries and Numeric Data

### 12.1. Filtering on Raw Numeric Properties

When searching for products above a minimum price, a direct predicate on the property is generally much easier for a **range index** to optimize than a condition wrapping the property in a calculation:

~~~cypher
MATCH (p:NumericDemoProduct)
WHERE p.priceVnd >= $minPriceVnd
RETURN p.sku, p.name, p.priceVnd
ORDER BY p.priceVnd;
~~~

Compare with:

~~~cypher
MATCH (p:NumericDemoProduct)
WHERE round(toFloat(p.priceVnd) * 0.9, 0) >= $minPriceVnd
RETURN p.sku, p.name;
~~~

The second condition requires evaluating an expression over the property during filtering, changing index usability. That is not a reason to omit needed calculations; instead, structure queries and schema so the optimizer can filter early using simple predicates.

### 12.2. Inspecting the Actual Execution Plan

You can create a practice index in an appropriate environment:

~~~cypher
CREATE RANGE INDEX numeric_demo_price IF NOT EXISTS
FOR (p:NumericDemoProduct) ON (p.priceVnd);
~~~

Then use `EXPLAIN` to inspect the estimated plan:

~~~cypher
EXPLAIN
MATCH (p:NumericDemoProduct)
WHERE p.priceVnd >= $minPriceVnd
RETURN p.sku, p.name, p.priceVnd;
~~~

`PROFILE` executes the query and reports row counts, DB hits, and index operators. The optimizer may prefer a label scan on a tiny three-product dataset; test on a sufficiently large dataset with representative parameters before drawing conclusions.

### 12.3. Normalize Numeric Data at Ingestion Time

If `priceVnd` is sometimes `INTEGER` and sometimes a string, every query must perform conversions and performance becomes unpredictable. If `FLOAT` values are mixed into a property meant for integers, aggregations and filter predicates are easily misinterpreted.

Therefore, you should:

1. Define the type and unit for every property before importing data.
2. Convert and validate types in the ETL or application layer.
3. Protect identifier keys with appropriate constraints; never use rounded numbers as unique keys if collisions are possible.
4. Preserve raw values where needed and compute rounded columns only for reporting.
5. Inspect plans with `EXPLAIN` and `PROFILE` when real performance issues arise.

## 13. Common Mistakes

| Mistake / Misconception | Consequence | How to Fix |
| --- | --- | --- |
| Computing `7 / 2` expecting `3.5` | Integer division drops the fractional part | Use `7 / 2.0` or `toFloat(7) / 2` |
| Using `toInteger(3.9)` to round | Result is `3` | Use `round()`, then convert type if needed |
| Assuming `ceil(-3.8) = -4` | Wrong rounding direction | `ceil(-3.8) = -3.0` |
| Rounding ratings and overwriting the raw value | Loses precision for downstream calculations | Round inside `RETURN` for display |
| Using `coalesce(price, 0)` when price is missing | Equates “no price” with “free” | Return a status column or keep `null` |
| Adding floats and checking exact `=` | `FLOAT` representation inaccuracy | Compare with tolerance if suitable; use exact rules for money |
| Converting `'007'` to a number as an ID | Drops leading zeros | Keep identifier codes as `STRING` |
| Passing `'200000'` as a string for a numeric parameter | Wrong filtering or type mismatch | Pass numeric types from the application |
| Assuming `'1,25'` parses as a float everywhere | Invalid or misinterpreted | Normalize input format and validate |
| Using `round(sum(x))` instead of `sum(round(x))` unintentionally | Totals may differ | Define rounding stage per business policy |
| Failing to check for a zero denominator | Calculation lacks valid business meaning | Guard division with `CASE` |
| Using `rand()` to generate primary keys | Value changes and may collide | Use a proper ID generation strategy |
| Ignoring missing properties in Java | Converting `null` to non-nullable Java types can fail | Check `Value.isNull()` and DTO contracts |
| Wrapping numeric properties in functions inside `WHERE` | Can prevent index usage | Filter directly on raw properties where appropriate |

## 14. Practice Exercises with Solutions

### Exercise 1. Integer and Floating-Point Division

**Requirement:** Divide `23` items into boxes holding `5` each. Calculate how many boxes are needed if each box holds at most 5 items:

~~~cypher
WITH 23 AS totalItems, 5 AS capacity
RETURN
  totalItems / capacity AS integerQuotient,
  toFloat(totalItems) / capacity AS exactRatio,
  toInteger(ceil(toFloat(totalItems) / capacity)) AS boxesNeeded;
~~~

**Solution:** `integerQuotient = 4`, `exactRatio = 4.6`, `boxesNeeded = 5`. To ensure sufficient capacity, use `ceil()` instead of `floor()`.

### Exercise 2. Distinguishing floor, ceil, and toInteger on Negative Numbers

~~~cypher
RETURN
  floor(-4.2) AS a,
  ceil(-4.2) AS b,
  toInteger(-4.2) AS c;
~~~

**Solution:** `a = -5.0`, `b = -4.0`, `c = -4`. `floor` and `ceil` round along the number line; `toInteger` truncates the fractional part of standard floating-point numbers.

### Exercise 3. Rounding Ratings

**Requirement:** Return SKU, raw rating, and rating rounded to one decimal place. Include only products that have a rating:

~~~cypher
MATCH (p:NumericDemoProduct)
WHERE p.rating IS NOT NULL
RETURN
  p.sku,
  p.rating AS rawRating,
  round(p.rating, 1) AS displayRating
ORDER BY p.sku;
~~~

**Solution:** `NP-001` displays roughly `4.4`; `NP-002` displays roughly `4.9`; `NP-003` is excluded because it has no rating.

### Exercise 4. Validating Numeric Input

**Requirement:** Convert price strings to integers, returning `null` and an error label if invalid:

~~~cypher
UNWIND ['320000', 'abc', '199000'] AS raw
WITH raw, toIntegerOrNull(raw) AS price
RETURN
  raw,
  price,
  CASE
    WHEN price IS NULL THEN 'Invalid'
    ELSE 'Valid'
  END AS status;
~~~

**Solution:** `'320000'` → `320000`, `'abc'` → `null`, `'199000'` → `199000`. Invalid strings should be tracked in the ingestion workflow rather than silently converted to 0.

### Exercise 5. Calculating Amount After Discount

**Requirement:** Use product nodes and purchase relationships. For transactions missing a discount percentage, treat discount as 0; return whole VND results:

~~~cypher
MATCH (c:NumericDemoCustomer)-[r:NUMERIC_DEMO_BOUGHT]->(p:NumericDemoProduct)
WITH
  c, p,
  toFloat(p.priceVnd) * r.quantity *
    (1.0 - coalesce(r.discountPercent, 0) / 100.0) AS amount
RETURN
  c.name AS customer,
  p.name AS product,
  toInteger(round(amount, 0)) AS payableVnd
ORDER BY customer;
~~~

**Solution:** An → `576000 VND`; Binh → `850000 VND`. This is an illustrative formula; for real billing systems, standardize units, currency storage, and rounding rules.

### Exercise 6. Distinguishing null from 0 in Aggregations

~~~cypher
UNWIND [2, 0, null, 5] AS quantity
RETURN
  count(*) AS rows,
  count(quantity) AS recordedValues,
  sum(quantity) AS totalQuantity,
  avg(quantity) AS averageRecorded;
~~~

**Solution:** `rows = 4`, `recordedValues = 3`, `totalQuantity = 7`, `averageRecorded` approximately `2.3333333333333335`. Zero is counted as a valid value; `null` is excluded from `count(quantity)` and `avg(quantity)`.

### Exercise 7. Product Price Summary Report

**Requirement:** Retrieve the lowest, highest, and average price rounded to whole VND:

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  min(p.priceVnd) AS minimumVnd,
  max(p.priceVnd) AS maximumVnd,
  toInteger(round(avg(p.priceVnd), 0)) AS roundedAverageVnd;
~~~

**Solution:** `minimumVnd = 199000`, `maximumVnd = 850000`, and `roundedAverageVnd = 456333`.

### Exercise 8. Designing Return Values for a Java Application

**Requirement:** An API needs whole VND prices and one-decimal ratings. Missing ratings must be accompanied by a flag indicating missing data.

~~~cypher
MATCH (p:NumericDemoProduct)
RETURN
  p.sku AS sku,
  p.priceVnd AS priceVnd,
  round(p.rating, 1) AS rating,
  p.rating IS NULL AS ratingMissing
ORDER BY sku;
~~~

**Suggested solution:** In Java, map `priceVnd` to `long`/`Long`, `rating` to `Double` when nullable, and `ratingMissing` to `boolean`/`Boolean`. Do not default `rating = 0` merely to use a primitive type.

### Exercise 9. Converting Status Flags from Imported Data

**Requirement:** Normalize `'YES'`, `'no'`, and `'unknown'` into Booleans:

~~~cypher
UNWIND ['YES', 'no', 'unknown'] AS raw
WITH raw, toLower(trim(raw)) AS flag
RETURN
  raw,
  CASE
    WHEN flag IN ['true', 'yes', '1'] THEN true
    WHEN flag IN ['false', 'no', '0'] THEN false
    ELSE null
  END AS active;
~~~

**Solution:** `YES → true`, `no → false`, `unknown → null`. Unrecognized values remain missing/invalid for downstream workflow handling.

## 15. Key Takeaways

- `INTEGER` suits quantities and currency in smallest units; `FLOAT` suits measurements and ratios but has representation inaccuracies that are critical in financial math.
- `abs()`, `sign()`, `sqrt()`, and other math functions build expressions over node and relationship properties.
- `ceil()`, `floor()`, `round()`, and `toInteger()` have distinct meanings. Always verify exact rules for negative numbers and rounding boundaries.
- `toInteger()`, `toFloat()`, `toString()`, `toBoolean()`, and their `OrNull` variants convert types; never confuse failed conversions with zero.
- Handle `null` explicitly using `IS NULL`, `CASE`, or `coalesce()` when business rules allow. Never automatically default missing scores, prices, or quantities to 0.
- In aggregations, **per-row rounding** and **post-sum rounding** can produce different totals; define the rounding point before building reports.
- From the Java Driver or Spring Data Neo4j, pass properly typed parameters, check nullable values, and maintain stable DTO contracts.
- For efficient graph queries, store numeric properties with consistent types, design appropriate indexes, and verify execution plans with `EXPLAIN` / `PROFILE`.

Mastering numeric functions, rounding, and type conversions helps you write semantically accurate Cypher queries, stay consistent across connected data, and integrate smoothly into Java-based Neo4j applications.
