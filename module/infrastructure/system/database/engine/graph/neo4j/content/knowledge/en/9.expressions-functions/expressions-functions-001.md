# Arithmetic, Comparison, String, and Boolean Expressions in Cypher

In Neo4j, data is organized as a **property graph**: nodes represent entities, relationships represent connections, and properties store information on both. When querying with **Cypher**, we often need to do more than just find nodes and relationships—we also need to calculate prices, compare properties, filter names by keyword, and combine multiple conditions. Those tasks rely on **expressions**.

This lesson belongs to the **Expressions and Functions** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. The focus is on how to write, combine, and control arithmetic, comparison, string, and logical expressions when querying connected data in Neo4j. The examples also lay the groundwork for using Cypher with the Java Driver and Spring Data Neo4j.

## 1. Objectives and Background Knowledge

After this lesson, you will be able to:

- Distinguish expressions from query clauses and identify the data types that expressions produce.
- Perform calculations with integers and floating-point numbers, and use parentheses to control operator precedence.
- Compare properties of nodes and relationships, and check for missing values using `IS NULL`.
- Concatenate, normalize, and search strings using Cypher operators and functions.
- Combine `AND`, `OR`, `NOT`, and `XOR`; understand the impact of `null` on filtering results.
- Write practical queries with parameters, computed expressions, and conditions suited to the database optimizer.

### 1.1. Where Do Expressions Appear?

An expression is a construct evaluated to produce a value. For example, `p.price` reads a property, `p.price * 2` computes a number, `p.price > 100000` produces a boolean value, and `toLower(p.name)` produces a lowercase string.

Expressions appear in many clauses:

| Location | Example | Purpose |
| --- | --- | --- |
| `RETURN` | `RETURN p.price * 2 AS doublePrice` | Create a result column from a calculation |
| `WHERE` | `WHERE p.price <= 500000` | Filter nodes by a condition |
| `WITH` | `WITH p, p.price * 0.9 AS salePrice` | Name and pass forward intermediate values |
| `SET` | `SET p.stock = p.stock + 1` | Update a property from an expression |
| `ORDER BY` | `ORDER BY p.price DESC` | Sort by an expression value |

In this lesson, `INTEGER` represents integers, `FLOAT` represents floating-point numbers, `STRING` represents strings, and `BOOLEAN` represents `true` or `false`. In addition, `null` represents **no value** or **unknown**; it requires special handling during calculations and filtering.

### 1.2. Sample Data for Practice

Most arithmetic, string, and logical examples can be run standalone using `RETURN`. For `MATCH` queries, you can create a small dataset in a practice database. Do not run this initialization snippet on active production data.

~~~cypher
MERGE (an:Customer {customerId: 'C001'})
SET an.name = 'An', an.active = true
MERGE (binh:Customer {customerId: 'C002'})
SET binh.name = 'Binh', binh.active = false
MERGE (chi:Customer {customerId: 'C003'})
SET chi.name = 'Chi', chi.active = true

MERGE (book:Product {sku: 'P001'})
SET book.name = 'Cypher Book',
    book.price = 320000, book.stock = 12, book.active = true
MERGE (course:Product {sku: 'P002'})
SET course.name = 'Neo4j Course',
    course.price = 850000, course.stock = 4, course.active = true
MERGE (note:Product {sku: 'P003'})
SET note.name = 'Notebook',
    note.price = 95000, note.stock = 0, note.active = false

MERGE (an)-[purchase1:BOUGHT]->(book)
SET purchase1.quantity = 2, purchase1.discount = 0.1
MERGE (binh)-[purchase2:BOUGHT]->(course)
SET purchase2.quantity = 1, purchase2.discount = 0.0;
~~~

The sample graph has three `Customer` nodes, three `Product` nodes, and two `BOUGHT` relationships. The `discount` property on the relationship is a discount rate from 0 to 1. Customer Chi has no transactions yet, which helps illustrate `OPTIONAL MATCH` and `null`.

## 2. Arithmetic Expressions

### 2.1. Arithmetic Operators

| Operator | Meaning | Example | Result |
| --- | --- | --- | --- |
| `+` | Addition | `8 + 3` | `11` |
| `-` | Subtraction | `8 - 3` | `5` |
| `*` | Multiplication | `8 * 3` | `24` |
| `/` | Division | `8 / 2` | `4` |
| `%` | Modulo (remainder) | `8 % 3` | `2` |
| `^` | Exponentiation | `2 ^ 3` | `8` |
| Unary `-` | Negation | `-8` | `-8` |

You can test multiple expressions in a single query:

~~~cypher
RETURN
  2 + 3 * 4 AS defaultOrder,
  (2 + 3) * 4 AS groupedOrder,
  10 / 4 AS integerDivision,
  10 / 4.0 AS decimalDivision,
  10 % 4 AS remainder,
  2 ^ 3 AS power;
~~~

The results are `14`, `20`, `2`, `2.5`, `2`, and `8`, respectively. Key point to remember: when **both operands are integers**, standard division returns an integer result with the fractional part truncated; to divide into a floating-point result, make at least one operand a `FLOAT`, such as `4.0`, or cast it with `toFloat(...)`.

Standard operator precedence is exponentiation, then multiplication/division/modulo, then addition/subtraction. **Parentheses** make intent clearest, especially for discount formulas or long expressions.

### 2.2. Calculations on Graph Properties

Suppose the total amount payable is unit price multiplied by quantity, minus the discount recorded on the relationship:

~~~cypher
MATCH (c:Customer)-[r:BOUGHT]->(p:Product)
RETURN
  c.name AS customer,
  p.name AS product,
  p.price AS unitPrice,
  r.quantity AS quantity,
  p.price * r.quantity AS subtotal,
  p.price * r.quantity * (1 - r.discount) AS finalAmount
ORDER BY customer;
~~~

For An's transaction, the subtotal before discount is `320000 * 2 = 640000`, and after a 10% discount it is approximately `576000`. The result may be represented as a `FLOAT` because `r.discount` is a floating-point number.

For monetary amounts requiring exact precision, you should standardize the storage unit before computing. For example, whole VND amounts can be stored as `INTEGER`; if using a `FLOAT` discount rate, clearly define the rounding step before posting to a ledger. Do not assume all floating-point calculations are exact, because they use floating-point representation.

### 2.3. Mathematical and Type Conversion Functions

| Function | Purpose | Example |
| --- | --- | --- |
| `abs(x)` | Absolute value | `abs(-12)` → `12` |
| `ceil(x)` | Round up | `ceil(4.1)` → `5.0` |
| `floor(x)` | Round down | `floor(4.9)` → `4.0` |
| `round(x, n)` | Round to `n` decimal places | `round(3.14159, 2)` → `3.14` |
| `sqrt(x)` | Square root | `sqrt(81)` → `9.0` |
| `toFloat(x)` | Convert a compatible value to float | `toFloat(7)` → `7.0` |
| `toInteger(x)` | Convert a compatible value to integer | `toInteger('42')` → `42` |

~~~cypher
WITH 7 AS items, 2 AS boxes
RETURN
  items / boxes AS integerResult,
  toFloat(items) / boxes AS decimalResult,
  ceil(toFloat(items) / boxes) AS boxesNeeded;
~~~

The results are `3`, `3.5`, and `4.0` respectively: four boxes are needed if each box holds two items. You must explicitly convert types when data comes from parameters or properties with a different type than expected; do not rely on the database implicitly converting strings to numbers.

**Note:** division by zero and invalid type conversions are not meaningful business formulas. Validate inputs or use `CASE` to define how they should be handled, rather than expecting a valid numeric result.

## 3. Comparison Expressions

### 3.1. Common Comparison Operators

| Operator | Meaning | Example |
| --- | --- | --- |
| `=` | Equal to | `p.sku = 'P001'` |
| `<>` | Not equal to | `p.sku <> 'P001'` |
| `>` | Greater than | `p.price > 300000` |
| `>=` | Greater than or equal to | `p.stock >= 1` |
| `<` | Less than | `p.price < 500000` |
| `<=` | Less than or equal to | `p.price <= 500000` |
| `IS NULL` | Has no value | `p.description IS NULL` |
| `IS NOT NULL` | Has a value | `p.price IS NOT NULL` |

~~~cypher
MATCH (p:Product)
WHERE p.price >= 100000
  AND p.price <= 500000
RETURN p.sku, p.name, p.price
ORDER BY p.price;
~~~

With the sample dataset, only `P001` falls within this price range. Cypher uses **`=`** for equality comparison; **`==`** is not the comparison syntax to use here. To check inequality, use `<>`.

### 3.2. String Comparison and Data Types

String comparison is case-sensitive. For example:

~~~cypher
RETURN
  'Neo4j' = 'Neo4j' AS sameText,
  'Neo4j' = 'neo4j' AS differentCase,
  10 > 3 AS greaterThan;
~~~

The three results are `true`, `false`, and `true`. If case-insensitive search is required, normalize both sides using string-processing functions before comparing. Converting letter case is **not the same** as removing Vietnamese diacritics or normalizing all Unicode variants.

You should compare values of compatible types. For instance, the `price` property is numeric, so the `$minPrice` parameter should also be passed as a number; do not pass the string `'300000'` and expect numeric comparisons to work as intended.

### 3.3. Why Can't Equality Be Used to Check for null?

A property that does not exist on a node generally evaluates to `null`. In Cypher's three-valued logic, `null` means unknown, so:

~~~cypher
RETURN
  null = null AS equalityUnknown,
  null <> 5 AS inequalityUnknown,
  null IS NULL AS missingValue,
  5 IS NOT NULL AS presentValue;
~~~

The results are `null`, `null`, `true`, and `true`. To find products without a description:

~~~cypher
MATCH (p:Product)
WHERE p.description IS NULL
RETURN p.sku, p.name;
~~~

Do not write `WHERE p.description = null`: that expression evaluates to `null` and does not satisfy the filter condition.

## 4. String Expressions

### 4.1. Strings and String Concatenation

Cypher strings are enclosed in single or double quotes; in these examples, we use single quotes consistently. You can concatenate strings with `||`; to combine numbers with text, convert the number to a string explicitly.

~~~cypher
RETURN
  'Neo' || '4j' AS databaseName,
  'Quantity: ' || toString(12) AS quantityLabel;
~~~

The results are `'Neo4j'` and `'Quantity: 12'`. Cypher also supports `+` for string concatenation in certain cases, but `||` clearly expresses text concatenation intent and avoids confusion with numeric addition.

When a property may be absent, use `coalesce` to provide a fallback string:

~~~cypher
MATCH (p:Product)
RETURN
  p.sku,
  p.name || ' - ' || coalesce(p.description, 'No description') AS displayName;
~~~

Without handling `null`, a string concatenation expression with a `null` operand can also produce `null`.

### 4.2. String Matching Operators

| Operator | Meaning | Example |
| --- | --- | --- |
| `STARTS WITH` | String begins with a prefix | `p.name STARTS WITH 'Cypher'` |
| `ENDS WITH` | String ends with a suffix | `p.name ENDS WITH 'Neo4j'` |
| `CONTAINS` | String contains a substring | `p.name CONTAINS 'Cypher'` |
| `=~` | String matches a regular expression (regex) | `p.name =~ '(?i).*neo4j.*'` |

~~~cypher
MATCH (p:Product)
WHERE p.name CONTAINS 'Cypher'
RETURN p.sku, p.name;
~~~

Sample result: `P001` – `Cypher Book`. Standard string matching checks are case-sensitive.

When using `=~`, the regex is matched against the **entire string**. Therefore, to find a keyword inside a name, use `.*` on both sides. The `(?i)` flag enables case-insensitive matching:

~~~cypher
MATCH (p:Product)
WHERE p.name =~ '(?i).*neo4j.*'
RETURN p.sku, p.name;
~~~

Sample result: `P002` – `Neo4j Course`. For user-supplied input, do not arbitrarily concatenate that input into a regex: characters such as `.`, `*`, and `[` have special meaning. If you only need substring matching, prefer `CONTAINS` with a parameter.

### 4.3. Important String Functions

| Function | Purpose | Example |
| --- | --- | --- |
| `toLower(s)` | Convert to lowercase | `toLower('Neo4j')` → `'neo4j'` |
| `toUpper(s)` | Convert to uppercase | `toUpper('neo4j')` → `'NEO4J'` |
| `trim(s)` | Remove leading and trailing whitespace | `trim('  Neo4j  ')` → `'Neo4j'` |
| `substring(s, start, length)` | Extract a substring, 0-based start index | `substring('Cypher', 0, 3)` → `'Cyp'` |
| `replace(s, old, new)` | Replace occurrences of a substring | `replace('Neo-4j', '-', '')` → `'Neo4j'` |
| `split(s, delimiter)` | Split into a list of strings | `split('a,b', ',')` → `['a', 'b']` |
| `size(s)` | Number of characters in the string | `size('Neo4j')` → `5` |
| `toString(x)` | Convert a compatible value to string | `toString(120)` → `'120'` |

Example of normalizing input strings for filtering:

~~~cypher
WITH '   cYpHeR   ' AS rawKeyword
WITH toLower(trim(rawKeyword)) AS keyword
MATCH (p:Product)
WHERE toLower(p.name) CONTAINS keyword
RETURN p.sku, p.name;
~~~

The result includes the product `Cypher Book`. Because `toLower` is applied directly to the property, the optimizer may not be able to use an index lookup the way it would for a condition on the raw property. For large systems, consider normalizing data on write, using an appropriate index, or adopting a full-text search solution for the specific use case.

## 5. Logical Expressions: true, false, and null

### 5.1. Logical Operators and Parentheses

| Operator | Interpretation | Example | Result |
| --- | --- | --- | --- |
| `NOT` | Negation | `NOT true` | `false` |
| `AND` | Both conditions are true | `true AND false` | `false` |
| `OR` | At least one condition is true | `true OR false` | `true` |
| `XOR` | True when the two sides differ in boolean value | `true XOR false` | `true` |

~~~cypher
MATCH (p:Product)
WHERE p.active = true
  AND (p.price < 500000 OR p.stock >= 10)
RETURN p.sku, p.name, p.price, p.stock;
~~~

The sample result contains only `P001`. Parentheses are critical: **`AND` has higher precedence than `OR`**. Writing `a AND (b OR c)` is not equivalent to `(a AND b) OR c`.

Cypher requires logical conditions to be proper Boolean expressions. Do not use numbers `1`, `0` or the string `'true'` in place of an actual Boolean.

### 5.2. Three-Valued Logic

Cypher uses three possible states for filter evaluation: `true`, `false`, and `null` (unknown). When `null` is involved, logical operations do not always evaluate to `null`:

| Expression | Result | Explanation |
| --- | --- | --- |
| `true AND null` | `null` | Unknown whether the other side is true or false |
| `false AND null` | `false` | One side is false, so the entire expression is false |
| `true OR null` | `true` | One side is true, so the entire expression is true |
| `false OR null` | `null` | Result depends on the unknown side |
| `NOT null` | `null` | Negating an unknown value remains unknown |
| `true XOR null` | `null` | Cannot determine whether the two sides differ |

~~~cypher
RETURN
  true AND null AS andUnknown,
  false AND null AS andFalse,
  true OR null AS orTrue,
  false OR null AS orUnknown,
  NOT null AS notUnknown;
~~~

In `WHERE`, **only records where the condition expression evaluates to `true` are kept**. Records whose condition evaluates to `false` or `null` are excluded from the results. This is especially important for optional properties.

### 5.3. Missing Values in OPTIONAL MATCH

`OPTIONAL MATCH` preserves result rows even when the graph pattern has no matching relationships; unmatched variables take the value `null`.

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[:BOUGHT]->(p:Product)
RETURN
  c.name AS customer,
  p.name AS product,
  p.price > 300000 AS isExpensive,
  coalesce(p.price > 300000, false) AS isExpensiveOrFalse
ORDER BY customer;
~~~

For Chi, `product` and `isExpensive` are `null` because Chi has made no purchases; `isExpensiveOrFalse` is `false`. These carry two different business meanings:

- `null`: insufficient information to conclude whether the product is expensive or inexpensive.
- `false`: the application convention treats having no product as making the “more expensive than 300000” condition false.

Do not overuse `coalesce` to replace every missing value with `false` or `0`; only choose a default value when it accurately reflects the business requirement.

### 5.4. CASE: Conditional Branching

`CASE` is an **expression** that can be used in `RETURN`, `WITH`, or other places expecting an expression:

~~~cypher
MATCH (p:Product)
RETURN
  p.name AS product,
  p.stock AS stock,
  CASE
    WHEN p.stock = 0 THEN 'Out of stock'
    WHEN p.stock < 5 THEN 'Low stock'
    ELSE 'In stock'
  END AS stockStatus
ORDER BY p.sku;
~~~

With the sample data, `Notebook` is “Out of stock”, `Neo4j Course` is “Low stock”, and `Cypher Book` is “In stock”. `WHEN` branches are evaluated in order and the first branch whose condition is `true` is selected; if no branch matches, `ELSE` is used. If `ELSE` is omitted, the result can be `null`.

`CASE` is also useful for expressing safe division rules:

~~~cypher
WITH 100.0 AS total, 0 AS count
RETURN
  CASE
    WHEN count = 0 THEN null
    ELSE total / count
  END AS average;
~~~

Do not rely solely on writing `count <> 0 AND total / count > 5` to guard every division: the optimizer may reorder expression evaluation. When guarding a calculation is mandatory, express it directly with `CASE`.

## 6. Combining Expression Types in a Graph Query

A business query often combines all four groups:

~~~cypher
MATCH (c:Customer)-[r:BOUGHT]->(p:Product)
WHERE c.active = true
  AND p.active = true
  AND toLower(p.name) CONTAINS 'cypher'
WITH
  c, p, r,
  p.price * r.quantity *
    (1 - coalesce(r.discount, 0.0)) AS amount
RETURN
  c.name AS customer,
  p.name AS product,
  r.quantity AS quantity,
  round(amount, 0) AS amount,
  CASE
    WHEN amount >= 500000 THEN 'High-value order'
    ELSE 'Regular order'
  END AS orderGroup
ORDER BY amount DESC;
~~~

This query executes in sequence:

1. `MATCH` finds `(:Customer)-[:BOUGHT]->(:Product)` paths.
2. `WHERE` checks active status and filters product names using a string expression.
3. `WITH` calculates the amount from properties on nodes and relationships; `coalesce` handles missing discounts.
4. `RETURN` assigns aliases, rounds the amount for display, and classifies the order with `CASE`.

With the sample data, An bought `Cypher Book` with quantity 2, resulting in an amount around 576000, classified as “High-value order”. Try changing the threshold or keyword to observe how logical conditions affect the result set.

Note: `WITH` splits a query into processing stages; only variables declared or passed forward after `WITH` are available in subsequent clauses. The `amount` expression creates an alias for the calculation, avoiding repeating long formulas.

## 7. Query Parameters and Performance

### 7.1. Passing Values via Parameters

In Java Driver or Spring Data Neo4j applications, values that vary per user request should be passed as **parameters**, such as `$minPrice` and `$prefix`:

~~~cypher
MATCH (p:Product)
WHERE p.price >= $minPrice
  AND p.name STARTS WITH $prefix
  AND p.active = true
RETURN p.sku, p.name, p.price
ORDER BY p.price;
~~~

For example, an application passing `minPrice = 200000` and `prefix = 'Cypher'` receives product `P001`. Parameters separate data from the query text, facilitate query plan reuse, and avoid concatenating user input into Cypher syntax. Maintain the proper data type for each parameter, especially `INTEGER`, `FLOAT`, `STRING`, and `BOOLEAN`.

### 7.2. Writing Expressions So the Optimizer Can Leverage Indexes

Conditions on raw properties are generally easier for indexes to utilize than conditions wrapping a property in a function. For example:

~~~cypher
// Usually easy to optimize when an appropriate index exists on :Product(sku)
MATCH (p:Product)
WHERE p.sku = $sku
RETURN p.name, p.price;
~~~

~~~cypher
// Requires evaluating the query plan, especially on large datasets
MATCH (p:Product)
WHERE toLower(p.name) = toLower($name)
RETURN p.sku, p.name;
~~~

Neo4j has multiple index types suited to different search patterns. Whether an index can be used depends on the index type, data statistics, condition form, and Neo4j version. Do not conclude based on syntax alone; use `EXPLAIN` to inspect the estimated plan and `PROFILE` to inspect actual execution, for example:

~~~cypher
PROFILE
MATCH (p:Product)
WHERE p.sku = $sku
RETURN p.name;
~~~

When reading the plan, look for access operators such as `NodeIndexSeek` or label scans, and compare data access counts (`DB Hits`). For a fair evaluation, pass valid parameters and test on a representative dataset. Only create indexes/constraints according to your environment's policies, as they are schema changes rather than simple computations.

## 8. Common Pitfalls and How to Avoid Them

| Situation | Correct Understanding or Fix |
| --- | --- |
| Writing `p.price == 100000` | Use `p.price = 100000`. |
| Writing `p.description = null` | Use `p.description IS NULL`. |
| Writing `7 / 2` expecting `3.5` | Use `7 / 2.0` or `toFloat(7) / 2`. |
| Concatenating strings with a missing property | Use `coalesce(property, 'Fallback value')` if appropriate for business logic. |
| Filtering `WHERE NOT p.active` expecting missing properties to be kept | `NOT null` is still `null`; explicitly define how missing values should be handled. |
| Writing `a OR b AND c` when wanting `(a OR b) AND c` | Add parentheses to express the exact intended logic. |
| Using `CONTAINS` expecting case-insensitivity | Normalize strings or use an appropriate search mechanism. |
| Comparing a numeric price against a string parameter | Pass parameters with consistent numeric types. |
| Expecting every `FLOAT` calculation to be exact | Design storage units and rounding rules for financial data. |
| Using regex for substring search without `.*` | `=~` matches the entire string; use `CONTAINS` if regex is unnecessary. |

## 9. Self-Check Practice Exercises

**Exercise 1 – Order of operations.** Predict the three result columns:

~~~cypher
RETURN
  3 + 2 * 5 AS a,
  (3 + 2) * 5 AS b,
  9 / 2.0 AS c;
~~~

Answer: `a = 13`, `b = 25`, `c = 4.5`. Parentheses change precedence; a floating-point denominator produces floating-point division.

**Exercise 2 – Filtering products on sale.** Write a query returning only products with `active = true`, `stock > 0`, and `price <= 400000`. One solution:

~~~cypher
MATCH (p:Product)
WHERE p.active = true
  AND p.stock > 0
  AND p.price <= 400000
RETURN p.sku, p.name, p.price, p.stock;
~~~

With the sample dataset, the result is `P001`.

**Exercise 3 – Case-insensitive search.** Find products whose name contains `'NEO4J'` regardless of letter casing in the stored data:

~~~cypher
WITH 'NEO4J' AS keyword
MATCH (p:Product)
WHERE toLower(p.name) CONTAINS toLower(keyword)
RETURN p.sku, p.name;
~~~

The sample result is `P002`. Search design for large datasets can be improved by choosing appropriate storage/indexing strategies.

**Exercise 4 – Customers with no purchases.** Use `OPTIONAL MATCH` and `IS NULL` / counting:

~~~cypher
MATCH (c:Customer)
OPTIONAL MATCH (c)-[r:BOUGHT]->(:Product)
WITH c, count(r) AS purchaseCount
WHERE purchaseCount = 0
RETURN c.customerId, c.name;
~~~

The sample result is customer Chi. `count(r)` counts non-`null` relationships, so it returns 0 for customers with no `BOUGHT` relationships. This is a clear way to distinguish “no transactions” from “has a transaction with a missing property”.

## 10. Key Takeaways

- Arithmetic expressions allow calculations on both node and relationship properties; pay attention to numeric types and parentheses.
- Comparison expressions use `=`, `<>`, `<`, `>`, `<=`, `>=`; use `IS NULL` or `IS NOT NULL` to check for missing values.
- String expressions use `||`, `STARTS WITH`, `ENDS WITH`, `CONTAINS`, `=~`, and appropriate normalization/conversion functions.
- Logical expressions have three states: `true`, `false`, and `null`; in `WHERE`, only `true` retains result rows.
- Use `coalesce` when there is a clear default rule, `CASE` for conditional branching, and `$name` parameters when queries are invoked from applications.
- For large graph datasets, inspect query plans with `EXPLAIN`/`PROFILE` to understand the impact of expressions on index usage.

Mastering these rules helps you write clear Cypher queries, safely handle optional properties, and perform reliable calculations on connected data in Neo4j.
