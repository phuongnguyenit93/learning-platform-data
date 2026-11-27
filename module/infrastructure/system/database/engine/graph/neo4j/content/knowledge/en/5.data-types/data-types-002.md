# Strings, Numbers, Booleans, and Type Conversion in Cypher

When modeling data with **Neo4j**, nodes and relationships commonly carry properties such as identifiers, names, prices, enrollment counts, and active statuses. Cypher lets you work with these properties using the **`STRING`, `INTEGER`, `FLOAT`, and `BOOLEAN`** types, and provides type conversion functions to process data from applications, CSV, or APIs.

This lesson focuses on how to **represent, compute, compare, filter, and convert** those four value categories. This is the foundation for writing accurate Cypher queries, building data ingestion pipelines, and passing parameters with the Java Driver or Spring Data Neo4j.

## 1. Recognizing Value Types in Cypher

| Type | Example Values | Common Use Cases | Notes |
| --- | --- | --- | --- |
| `STRING` | `'Neo4j'`, `'SP-001'`, `''` | Names, business codes, emails, labels | An empty string is still a value |
| `INTEGER` | `0`, `-8`, `150000` | Ages, quantities, counters, currency amounts in smallest unit | 64-bit signed integer |
| `FLOAT` | `2.5`, `-0.75`, `1.0e3` | Measurements, ratios, continuous values | 64-bit floating-point, subject to precision error |
| `BOOLEAN` | `true`, `false` | Activation, confirmation, visibility | Not automatically equivalent to `'true'` and `'false'` |
| `null` | `null` | Missing data or expression with no value | Not `false`, `0`, or `''` |

**Important observation:** quotes affect the data type. `25` is an integer, `25.0` is a float, while `'25'` is a string. Similarly, `true` is a boolean value, whereas `'true'` is a character string.

```cypher
RETURN
  25 AS integerValue,
  25.0 AS floatValue,
  '25' AS stringValue,
  true AS booleanValue,
  'true' AS textValue;
```

In Neo4j/Cypher environments that support the `valueType()` function, you can inspect types when investigating data:

```cypher
RETURN
  valueType(25) AS integerType,
  valueType(25.0) AS floatType,
  valueType('25') AS stringType,
  valueType(true) AS booleanType;
```

Type names in the `valueType()` output may reflect details of the Cypher version's type system. When working on a real system, consult the documentation for the Neo4j version in use.

## 2. STRING: Representation and Text Manipulation

### 2.1. String Literals and Special Characters

Cypher allows either single quotes or double quotes to represent strings. In standard examples, single quotes can be used to avoid confusion with property names.

```cypher
RETURN
  'Neo4j' AS productName,
  "Cypher" AS queryLanguage,
  'Nguyen Minh Anh' AS fullName,
  '' AS emptyString;
```

Strings are stored in Unicode, so accented text or non-ASCII content can appear in property values:

```cypher
CREATE (b:Book {
  bookCode: 'SACH-001',
  title: 'Introduction to Graph Databases',
  author: 'Tran Ha'
})
RETURN b.title, b.author;
```

To place quotes inside a string, use the matching outer quote style or escape the quote:

```cypher
RETURN
  "O'Reilly" AS publisher,
  'Statement: "MATCH (n) RETURN n"' AS example,
  'It\'s a graph' AS escapedApostrophe,
  'Line 1\nLine 2' AS multilineContent;
```

In the Cypher snippet above, `\'` produces a single quote inside a single-quoted string, and `\n` represents a newline character.

### 2.2. Common String Operations

| Expression | Expected Result | Purpose |
| --- | --- | --- |
| `toUpper('Neo4j')` | `'NEO4J'` | Convert to uppercase |
| `toLower('Cypher')` | `'cypher'` | Convert to lowercase |
| `trim('  Lan  ')` | `'Lan'` | Remove leading and trailing whitespace |
| `substring('Neo4j', 0, 3)` | `'Neo'` | Extract a substring; 0-based index |
| `replace('graph-db', '-', ' ')` | `'graph db'` | Replace text segments |
| `split('java,cypher', ',')` | `['java', 'cypher']` | Split a string into a list |
| `'Neo' + '4j'` | `'Neo4j'` | Concatenate strings using supported syntax |

Example using string functions in a query:

```cypher
WITH '  Graph Database  ' AS rawTitle
RETURN
  trim(rawTitle) AS cleanTitle,
  toLower(trim(rawTitle)) AS normalizedTitle,
  replace(trim(rawTitle), ' ', '-') AS slugCandidate;
```

String concatenation with `+` is familiar syntax in Cypher; modern versions also provide the `||` concatenation operator. When choosing syntax for a project, keep it consistent with your Neo4j version and codebase conventions.

### 2.3. Comparing and Searching Strings

Common operators:

- `=` and `<>` to test equality/inequality.
- `STARTS WITH` to check a prefix.
- `ENDS WITH` to check a suffix.
- `CONTAINS` to check a substring.
- `=~` to match against a regular expression.

```cypher
MATCH (b:Book)
WHERE b.title CONTAINS 'graph'
RETURN b.bookCode, b.title;
```

```cypher
MATCH (b:Book)
WHERE b.bookCode STARTS WITH 'SACH-'
RETURN b.bookCode, b.title;
```

String comparison is performed by character value; do not assume the system automatically strips diacritics, ignores spaces, or is case-insensitive. If the business logic requires case-insensitive search, both sides can be normalized for simple queries:

```cypher
MATCH (b:Book)
WHERE toLower(b.title) CONTAINS toLower($keyword)
RETURN b.title;
```

**Performance note:** wrapping a property in a function such as `toLower(b.title)` can prevent some standard indexes from supporting the query as expected. For large-scale search requirements, consider pre-normalized properties, appropriate text/full-text indexes, and inspect with `EXPLAIN` or `PROFILE`. Advanced search strategies belong to the indexing and query tuning section.

### 2.4. Strings Are Not Numbers, Dates, or Booleans

`'00128'` is the right choice for a business code with leading zeros; converting it to `INTEGER` would lose those leading zeros. `'2026-11-25'` also remains a string until converted to `DATE` if the domain requires date calculations. When bringing data into Neo4j, the type should be decided by the **semantics** of the field rather than just how the characters look.

## 3. INTEGER and FLOAT Numbers

### 3.1. Number Representation and Type Selection

`INTEGER` is used for whole values within the 64-bit signed integer range:

- Minimum value: `-9223372036854775808`.
- Maximum value: `9223372036854775807`.

`FLOAT` is an IEEE 754 64-bit floating-point number. This type fits many measurements and ratios, but **cannot represent every decimal number exactly**.

```cypher
RETURN
  120 AS quantity,
  -15 AS adjustment,
  19.5 AS rating,
  1.0e3 AS scientificNotation;
```

Choose types based on business needs:

| Data | Recommended Type | Reason |
| --- | --- | --- |
| Login count | `INTEGER` | Counts whole values |
| Selling price in whole VND | `INTEGER` | Avoids floating-point error when the business unit is whole dong |
| Completion rate 87.5% | `FLOAT` | Has a fractional part |
| Temperature 26.4 °C | `FLOAT` | Continuous measured quantity |
| Invoice code `'000001'` | `STRING` | Code not used for arithmetic; must preserve leading zeros |

For currency with fractional units, amounts are typically stored as `INTEGER` in the currency's smallest unit (e.g., cents) and converted upon display. The unit convention must be clearly defined to avoid confusion.

### 3.2. Arithmetic Operations

Cypher supports standard arithmetic operators:

```cypher
RETURN
  8 + 3 AS addition,
  8 - 3 AS subtraction,
  8 * 3 AS multiplication,
  8 / 3 AS integerDivision,
  8 / 3.0 AS floatingDivision,
  8 % 3 AS remainder;
```

When both operands are `INTEGER`, the `/` operator performs integer division. As soon as at least one operand is `FLOAT`, the division is evaluated as floating-point.

| Expression | Result | Explanation |
| --- | --- | --- |
| `7 / 2` | `3` | Integer division |
| `7 / 2.0` | `3.5` | Floating-point division |
| `7 % 2` | `1` | Remainder |
| `3 + 2 * 4` | `11` | Multiplication before addition |
| `(3 + 2) * 4` | `20` | Parentheses determine order |

Do not divide by 0. When an operand may be missing or the denominator could be 0, validate or handle that case before executing.

Example of calculating completion rate as a percentage:

```cypher
WITH 7 AS completed, 10 AS total
RETURN
  100.0 * completed / total AS percentCompleted;
```

Multiplying by `100.0` keeps the calculation in floating-point. When rendering into a report, rounding can be applied at the display step as needed.

### 3.3. Numeric Comparisons and Filter Conditions

```cypher
MATCH (p:Product)
WHERE p.priceVnd >= 100000
  AND p.stockQuantity > 0
RETURN p.productCode, p.priceVnd, p.stockQuantity
ORDER BY p.priceVnd DESC;
```

For unreliable input data, make sure `priceVnd` and `stockQuantity` are stored as numeric types. The string `'100000'` looks like a number but does not automatically carry numeric meaning in every expression. Avoid mixing strings and numbers in the same property.

### 3.4. Floating-Point Precision Error

Strict equality comparison between two `FLOAT` calculations should not be treated as safe in all cases. Some decimal values such as `0.1` cannot be represented exactly in binary, so computed results may differ slightly from the expected value.

```cypher
WITH 0.1 + 0.2 AS calculated, 0.3 AS expected
RETURN
  calculated,
  expected,
  abs(calculated - expected) AS difference,
  abs(calculated - expected) < 0.000001 AS approximatelyEqual;
```

The tolerance threshold should be based on the range, unit of measurement, and business requirements. For financial calculations requiring exact precision, use an integer model in the smallest unit or an exact decimal arithmetic mechanism at the appropriate layer.

## 4. BOOLEAN: Truth Values and Filter Conditions

`BOOLEAN` has two defined values: `true` and `false`. In queries, conditional expressions can also yield `null` when information is missing.

```cypher
CREATE (u:User {
  userId: 'U-001',
  displayName: 'Mai',
  active: true,
  emailVerified: false
})
RETURN u.userId, u.active, u.emailVerified;
```

Comparison expressions `=`, `<>`, `<`, `<=`, `>`, `>=` on compatible types produce boolean values. To combine conditions, use `AND`, `OR`, and `NOT`:

```cypher
MATCH (u:User)
WHERE u.active = true
  AND u.emailVerified = false
RETURN u.userId, u.displayName;
```

You can write `WHERE u.active` when certain that `u.active` is a boolean property. The explicit form `u.active = true` is often easier to read in introductory material.

### 4.1. Basic Truth Table

| `a` | `b` | `a AND b` | `a OR b` |
| --- | --- | --- | --- |
| `true` | `true` | `true` | `true` |
| `true` | `false` | `false` | `true` |
| `false` | `true` | `false` | `true` |
| `false` | `false` | `false` | `false` |

`NOT true` yields `false`; `NOT false` yields `true`. Use parentheses when a condition combines multiple `AND` and `OR` operators to make intent clear and avoid relying on readers memorizing operator precedence.

```cypher
MATCH (u:User)
WHERE u.active = true
  AND (u.emailVerified = true OR u.displayName STARTS WITH 'M')
RETURN u.userId, u.displayName;
```

### 4.2. Three-Valued Logic with NULL

`null` is not synonymous with `false`. When a value is missing, many logical operations return `null` (unknown).

| Expression | Result |
| --- | --- |
| `true AND null` | `null` |
| `false AND null` | `false` |
| `true OR null` | `true` |
| `false OR null` | `null` |
| `NOT null` | `null` |
| `null = null` | `null` |

The `WHERE` clause keeps rows whose condition evaluates to `true`. Conditions evaluating to `false` or `null` are both filtered out.

```cypher
MATCH (u:User)
WHERE u.emailVerified IS NULL
RETURN u.userId, u.displayName;
```

If missing values should be treated as `false` according to business rules, use `coalesce()`:

```cypher
MATCH (u:User)
WHERE coalesce(u.emailVerified, false) = false
RETURN u.userId, u.displayName;
```

The query above retrieves both users with `emailVerified = false` **and** users without the `emailVerified` property. Only apply this approach when the two states can be treated as equivalent in the business domain.

### 4.3. Using CASE to Generate Display Labels

`CASE` maps logical expressions to human-readable outcomes:

```cypher
MATCH (u:User)
RETURN
  u.userId,
  CASE
    WHEN u.active = true THEN 'Active'
    WHEN u.active = false THEN 'Suspended'
    ELSE 'No information'
  END AS accountStatus;
```

The `ELSE` branch in this example handles missing values; distinguishing three states prevents misreporting unknown data as an inactive status.

## 5. Type Conversion: Why and When It Is Needed

Data entering Neo4j may come from CSV, JSON, HTTP requests, or Java Driver parameters. CSV typically supplies column values as strings; JSON and Java can distinguish numbers, booleans, and strings, yet still risk passing the wrong type.

Example of string-typed input:

```cypher
WITH {
  age: '29',
  rating: '4.5',
  active: 'true'
} AS raw
RETURN
  raw.age AS ageText,
  raw.rating AS ratingText,
  raw.active AS activeText;
```

To compute age, compare scores, or use status in `WHERE`, values must be converted to the appropriate type before writing and querying. Cypher **must not be assumed to implicitly coerce strings into numbers or booleans as the user intends**.

## 6. Common Type Conversion Functions

| Function | Example | Result or Meaning |
| --- | --- | --- |
| `toString(value)` | `toString(25)` | String `'25'` |
| `toString(value)` | `toString(true)` | String `'true'` |
| `toInteger(value)` | `toInteger('25')` | Integer `25` |
| `toInteger(value)` | `toInteger(3.9)` | Integer `3` |
| `toFloat(value)` | `toFloat('3.9')` | Float `3.9` |
| `toFloat(value)` | `toFloat(7)` | Float `7.0` |
| `toBoolean(value)` | `toBoolean('true')` | Value `true` |
| `toBoolean(value)` | `toBoolean('false')` | Value `false` |
| `toIntegerOrNull(value)` | `toIntegerOrNull('abc')` | `null` if conversion fails |
| `toFloatOrNull(value)` | `toFloatOrNull('abc')` | `null` if conversion fails |
| `toBooleanOrNull(value)` | `toBooleanOrNull('unknown')` | `null` if conversion fails |

The `...OrNull` functions help handle potentially invalid input; the main difference is that they return `null` when conversion fails. Keep in mind that `null` still needs to be handled afterward, especially before a `SET` operation.

### 6.1. Converting Strings to Numbers

```cypher
RETURN
  toInteger('120') AS quantity,
  toFloat('120.5') AS amount,
  toInteger(12.9) AS truncatedInteger,
  toIntegerOrNull('not a number') AS invalidInteger,
  toFloatOrNull('not a number') AS invalidFloat;
```

`toInteger(12.9)` truncates the fractional part when converting to an integer, rather than performing standard rounding. Do not use this conversion if business rules require a specific rounding rule.

Before converting, decide whether negative numbers, decimal parts, whitespace, currency symbols, or thousand separators are allowed in the input. For example, `'1,200'` should not be assumed to mean 1200 without normalizing the format first.

### 6.2. Converting Strings to BOOLEAN

```cypher
RETURN
  toBoolean('true') AS enabled,
  toBoolean('false') AS disabled,
  toBooleanOrNull('unknown') AS unknownStatus;
```

If the data source uses `'Y'`/`'N'`, `'yes'`/`'no'`, or `'1'`/`'0'`, **define an explicit business mapping** rather than assuming `toBoolean()` understands every convention:

```cypher
WITH 'Y' AS sourceFlag
RETURN
  CASE toUpper(sourceFlag)
    WHEN 'Y' THEN true
    WHEN 'N' THEN false
    ELSE null
  END AS active;
```

For blank values in a source column, determine whether blank means "unknown", "inactive", or "invalid data" to decide whether to return `null`, `false`, or reject the record.

### 6.3. Converting to STRING

```cypher
RETURN
  toString(2026) AS yearAsText,
  toString(4.5) AS ratingAsText,
  toString(false) AS falseAsText;
```

`toString()` is useful when building display text, labels, or exported data. However, **you should not convert numbers to strings just to store every property as the same type**. Doing so makes arithmetic operations and numeric comparisons harder to control.

### 6.4. NULL During Conversion

```cypher
RETURN
  toIntegerOrNull(null) AS missingInteger,
  toFloatOrNull('invalid') AS invalidMeasurement,
  coalesce(toIntegerOrNull('invalid'), 0) AS quantityWithDefault;
```

`coalesce()` picks the first non-`null` value, but defaulting to `0` can **mask bad input data**. Only use a default value if the business domain genuinely defines missing or invalid cases that way; for data requiring quality control, reject, log, or raise an error instead of silently substituting 0.

## 7. Normalizing and Validating Before Writing Properties

Suppose an application imports a product list with prices and statuses as strings. The following example converts types, filters out bad data, and only then writes to Neo4j.

```cypher
WITH [
  {code: 'SP-001', price: '125000', active: 'true'},
  {code: 'SP-002', price: 'not-a-number', active: 'false'},
  {code: 'SP-003', price: '89000', active: 'false'}
] AS rows
UNWIND rows AS row

WITH
  row,
  toIntegerOrNull(row.price) AS parsedPrice,
  toBooleanOrNull(row.active) AS parsedActive

WHERE parsedPrice IS NOT NULL
  AND parsedPrice >= 0
  AND parsedActive IS NOT NULL

MERGE (p:Product {productCode: row.code})
SET
  p.priceVnd = parsedPrice,
  p.active = parsedActive
RETURN p.productCode, p.priceVnd, p.active
ORDER BY p.productCode;
```

Expected outcome: the two valid products `SP-001` and `SP-003` are written; `SP-002` is skipped because its price cannot be converted to an integer. Note that this example **does not log rejected rows**; a production ingestion pipeline needs statistics and error-reporting mechanisms for bad records.

Why not run `SET p.priceVnd = toIntegerOrNull(row.price)` right away? If the converted value becomes `null`, Neo4j deletes the corresponding property. Checking `IS NOT NULL` before writing avoids that side effect.

### 7.1. Validating with Regular Expressions

For a positive integer string allowing only ASCII digits, you can check beforehand:

```cypher
WITH '0042' AS rawCount
RETURN
  rawCount =~ '^[0-9]+$' AS validDigits,
  toIntegerOrNull(rawCount) AS parsedCount;
```

The regular expression here validates **string format**, not that the number fits within the 64-bit `INTEGER` range. Domain range and semantic checks are still required; the string `'0042'` might still need to be kept as-is if it is an identifier.

### 7.2. Normalizing String Data Before Comparison

```cypher
WITH '  Lan@Example.Com  ' AS rawEmail
RETURN toLower(trim(rawEmail)) AS normalizedEmail;
```

Lowercasing an email in this example is a simple convention for searching or account matching; a real system must define a normalization policy matching its business rules. Handling of Unicode, whitespace, and diacritics should also be standardized if source data is diverse.

## 8. Using Correct Data Types When Passing Parameters

In a parameterized query, `$age`, `$active`, and `$name` are values supplied by the application, not strings concatenated directly into the Cypher statement.

```cypher
CREATE (u:User {
  userId: $userId,
  name: $name,
  age: $age,
  active: $active
})
RETURN u.userId, u.name, u.age, u.active;
```

Expected parameters:

| Parameter Name | Sample Value | Type to Pass |
| --- | --- | --- |
| `userId` | `'U-015'` | `STRING` |
| `name` | `'Ngoc'` | `STRING` |
| `age` | `24` | `INTEGER` |
| `active` | `true` | `BOOLEAN` |

With the **Java Driver**, use the corresponding Java types when putting values into the parameter map (e.g., `String`, `long`/`Long`, `double`/`Double`, `boolean`/`Boolean`). With **Spring Data Neo4j**, define entity field types according to data semantics and verify mapping on read/write. If HTTP input provides `"24"` or `"true"` as strings, explicitly validate/convert them in the application layer or in Cypher.

Example of filtering with numeric and boolean parameters:

```cypher
MATCH (p:Product)
WHERE p.priceVnd >= $minimumPrice
  AND p.active = $activeOnly
RETURN p.productCode, p.priceVnd
ORDER BY p.priceVnd;
```

If you also want to include inactive products, clearly define the meaning of the filter parameter rather than using `$activeOnly = false` as an implicit signal to skip the condition. Separating "active products only" from "filter by false status" prevents skewed results.

## 9. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Adding `'10'` to a number throws an error or produces an unexpected result | `'10'` is a string | Convert with `toIntegerOrNull()` / `toFloatOrNull()` before arithmetic |
| Prices `'90'` and `'100'` compare lexicographically | Data mistakenly stored as `STRING` | Standardize the property to a numeric type |
| `'true'` used as a `BOOLEAN` | Strings and booleans are different types | Pass `true` or convert explicitly |
| Division `7 / 2` returns `3` | Both operands are integers | Use `7 / 2.0` if a decimal result is needed |
| `0.1 + 0.2` differs slightly from `0.3` | Floating-point precision error | Compare with a tolerance or use integers in an appropriate unit |
| `WHERE n.flag = null` fails to find missing data | Comparing with `null` does not yield `true` | Use `n.flag IS NULL` |
| Using `coalesce(toIntegerOrNull(text), 0)` turns every error into 0 | Default value hides input errors | Validate, log, or reject invalid records |
| `SET n.count = toIntegerOrNull('bad')` deletes the existing property | Assigning `null` removes the property | Verify conversion succeeded before `SET` |
| Code `'0007'` becomes `7` | Converted an identifier to `INTEGER` | Store codes as `STRING` |
| Case-sensitive/insensitive string searches return unexpected results | No unified normalization rule | Normalize input fields and design search accordingly |

## 10. Practice Exercises

### Exercise 1 — Identifying Literals

Determine the types of the values: `'42'`, `42`, `42.0`, `false`, `'false'`, `''`, and `null`.

**Hint:** place the values in a `RETURN` clause and check with `valueType()` if your version supports it; remember `null` denotes no defined value.

### Exercise 2 — Processing API Input Values

Given the input:

```cypher
WITH {
  name: '  Khoa  ',
  age: '31',
  score: '8.75',
  subscribed: 'true'
} AS request
RETURN request;
```

Return four normalized fields: `name` trimmed of extra whitespace, `age` as an integer, `score` as a float, and `subscribed` as a boolean.

**Sample Answer:**

```cypher
WITH {
  name: '  Khoa  ',
  age: '31',
  score: '8.75',
  subscribed: 'true'
} AS request
RETURN
  trim(request.name) AS name,
  toIntegerOrNull(request.age) AS age,
  toFloatOrNull(request.score) AS score,
  toBooleanOrNull(request.subscribed) AS subscribed;
```

### Exercise 3 — Calculating Percentage with the Right Type

Given `completed = 13` and `total = 20`, return the completion rate as a floating-point percentage.

**Sample Answer:**

```cypher
WITH 13 AS completed, 20 AS total
RETURN 100.0 * completed / total AS percentCompleted;
```

The result is `65.0`. For general data, handle `total = 0` before dividing.

### Exercise 4 — Distinguishing Missing Status from False Status

A `User` node may have `emailVerified = true`, `emailVerified = false`, or lack the `emailVerified` property. Return the label `'Verified'`, `'Unverified'`, or `'Unknown'`.

**Sample Answer:**

```cypher
MATCH (u:User)
RETURN
  u.userId,
  CASE
    WHEN u.emailVerified = true THEN 'Verified'
    WHEN u.emailVerified = false THEN 'Unverified'
    ELSE 'Unknown'
  END AS verificationLabel;
```

## 11. Checklist for Using STRING, INTEGER, FLOAT, and BOOLEAN

Before storing data in Neo4j, ask yourself:

1. Is the property an identifier or a quantity for calculation? Does it need to preserve leading zeros?
2. Does the number have a fractional part? Does it require absolute precision like currency?
3. Does the status strictly have two values, or must "unknown" also be distinguished?
4. Is the input data arriving as strings, or is it already typed properly by Java/JSON?
5. Will failed conversions be dropped, logged, reported as errors, or given a default value?
6. Could using `SET` with a conversion result that might be `null` accidentally delete an existing property?
7. Have string comparison conditions defined how uppercase/lowercase and Unicode are handled?
8. Have parameterized queries been used and query results verified when integrating with the Java Driver/Spring Data Neo4j?

---

**Remember:** in Cypher, `'42'`, `42`, and `42.0` are values of different types; `'false'` is likewise different from `false`. Choose types based on business semantics, use explicit conversion functions, check for `null` before writing, and align data types between Neo4j and the calling application.
