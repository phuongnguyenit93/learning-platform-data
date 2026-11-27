# Handling null with Explicit Checks and the coalesce Function in Cypher

In Neo4j, one node may have an `email` property while another node with the same label does not. A relationship may exist without a `quantity` property recorded; or the relationship itself may not be found. These situations are very common in a **property graph**, especially when integrating data from multiple sources, importing CSV files, querying optional paths, and building applications with the Java Driver or Spring Data Neo4j.

This lesson belongs to the **Expressions and Functions** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. The main focus is how to detect missing values in Cypher with `IS NULL` / `IS NOT NULL`, how to apply `coalesce()` for fallback values, and how to avoid business-logic errors caused by confusing `null`, `false`, `0`, and empty strings.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain what `null` means in Cypher query results and how it relates to non-existent properties in the graph.
- Explicitly check for missing values using `IS NULL` and `IS NOT NULL`.
- Predict the impact of `null` on comparisons, arithmetic operations, and `WHERE` conditions.
- Use `coalesce(expression1, expression2, ...)` to retrieve the first non-`null` value.
- Distinguish between cases that need a default value and cases where the “unknown” state must be preserved.
- Combine `OPTIONAL MATCH`, `CASE`, aggregation functions, and query parameters to safely handle missing data.
- Avoid errors when importing data, updating properties, or processing values from Neo4j in a Java application.

## 2. Understanding null Correctly in a Property Graph

### 2.1. What Is null?

`null` represents the state of **having no value** or being **unknown**. In Cypher, we commonly encounter `null` when:

1. Accessing a non-existent property, such as `c.email` on a node that has no email.
2. An `OPTIONAL MATCH` fails to find a matching node or relationship.
3. An expression depends on a `null` value and cannot compute a deterministic result.
4. A query or input data explicitly represents an unavailable value with `null`.

Standalone example:

~~~cypher
RETURN
  null AS missing,
  null + 5 AS unknownSum,
  'Neo4j' || null AS unknownText,
  null = 10 AS unknownComparison;
~~~

All four columns evaluate to `null`. Do not treat `null` as a “special number”, an empty string, or a default Boolean value.

**Neo4j storage characteristic:** properties on a node or relationship do not store `null` as an ordinary property value. Running `SET n.email = null` is equivalent to removing the `email` property from node `n`. When reading a property that does not exist, Cypher returns `null`.

### 2.2. Distinguishing null, Empty String, Zero, and false

| Value | Common Meaning | Replaced by `coalesce`? |
| --- | --- | --- |
| `null` | Missing information, unknown | Yes |
| `''` | Zero-length string | No |
| `'   '` | Whitespace-only string | No |
| `0` | Numeric zero | No |
| `false` | Boolean false | No |
| `[]` | Empty list | No |

Test directly:

~~~cypher
RETURN
  coalesce(null, 'Fallback') AS a,
  coalesce('', 'Fallback') AS b,
  coalesce(0, 99) AS c,
  coalesce(false, true) AS d,
  coalesce([], ['x']) AS e;
~~~

The results are `'Fallback'`, `''`, `0`, `false`, and `[]`, respectively. The `coalesce` function handles **`null` values**; it does not check for empty values in a business sense.

### 2.3. Sample Graph Data

Queries using `RETURN` and `UNWIND` in this lesson can run standalone. To practice `MATCH` queries, create the data in a **separate practice database** using the following Cypher snippet:

~~~cypher
MERGE (an:NullDemoCustomer {demoId: 'N-001'})
SET an.name = 'An',
    an.email = 'an@example.com',
    an.isVip = true

MERGE (binh:NullDemoCustomer {demoId: 'N-002'})
SET binh.name = 'Binh',
    binh.nickname = '',
    binh.isVip = false
REMOVE binh.email

MERGE (chi:NullDemoCustomer {demoId: 'N-003'})
SET chi.name = 'Chi'
REMOVE chi.email, chi.isVip

MERGE (book:NullDemoProduct {demoSku: 'N-P01'})
SET book.name = 'Cypher Book', book.price = 320000
MERGE (course:NullDemoProduct {demoSku: 'N-P02'})
SET course.name = 'Neo4j Course', course.price = 850000

MERGE (an)-[aOrder:NULL_DEMO_BOUGHT]->(book)
SET aOrder.quantity = 2
MERGE (binh)-[bOrder:NULL_DEMO_BOUGHT]->(course)
SET bOrder.quantity = 1;
~~~

The dataset uses dedicated labels and relationship types for clarity:

| Customer | `email` | `isVip` | Purchased Product |
| --- | --- | --- | --- |
| An | `'an@example.com'` | `true` | Cypher Book |
| Binh | No property | `false` | Neo4j Course |
| Chi | No property | No property | Not purchased |

Additionally, Binh's `nickname` is `''`, meaning the property **exists** with an empty string value. This differs from Binh's and Chi's `email`, which does not exist as a property.

## 3. Explicit Checks with IS NULL and IS NOT NULL

### 3.1. Syntax

- `expression IS NULL` returns `true` when the expression evaluates to `null`.
- `expression IS NOT NULL` returns `true` when the expression evaluates to a non-`null` value.

~~~cypher
RETURN
  null IS NULL AS a,
  null IS NOT NULL AS b,
  0 IS NULL AS c,
  '' IS NOT NULL AS d,
  false IS NOT NULL AS e;
~~~

Results: `a = true`, `b = false`, `c = false`, `d = true`, `e = true`.

This is the correct and direct way to check for missing values. Do not use standard comparison operators like `= null` or `<> null` instead.

### 3.2. Finding Nodes Missing or Having a Property

Find customers without an email:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.email IS NULL
RETURN c.demoId, c.name
ORDER BY c.demoId;
~~~

The sample result includes Binh and Chi. Find customers who **have** an email:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.email IS NOT NULL
RETURN c.demoId, c.name, c.email;
~~~

The sample result is An. When your goal is to check for the **presence** of a property in modern Cypher, `c.email IS NOT NULL` is readable and expresses the exact intent.

You can also check an expression rather than a single property:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE trim(c.email) IS NOT NULL
RETURN c.name, c.email;
~~~

However, if you only need to determine whether the `email` property exists, checking `c.email IS NOT NULL` directly makes the intent clearer.

### 3.3. Never Use = null or <> null

Consider:

~~~cypher
RETURN
  null = null AS equality,
  null <> null AS inequality,
  5 = null AS compareWithNull,
  null IS NULL AS explicitCheck;
~~~

The first three columns evaluate to `null`; only `explicitCheck` is `true`. This is **three-valued logic**: when a value is unknown, equality or inequality comparisons cannot assert true or false.

Consequently, the following query fails to find customers missing an email:

~~~cypher
// Wrong intent: the condition never evaluates to true when email is null.
MATCH (c:NullDemoCustomer)
WHERE c.email = null
RETURN c.name;
~~~

Fix it to `WHERE c.email IS NULL`.

### 3.4. Checking for null in the WHERE Clause

`WHERE` only retains rows where the condition evaluates to **`true`**. Rows where the condition evaluates to `false` or `null` are filtered out. For example:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.email <> 'blocked@example.com'
RETURN c.name, c.email;
~~~

Only An is kept. Binh and Chi do not appear because `null <> 'blocked@example.com'` evaluates to `null`, not `true`. If the business requirement is “email differs from the blocked address **or has no email**”, you must write it explicitly:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.email IS NULL
   OR c.email <> 'blocked@example.com'
RETURN c.name, c.email
ORDER BY c.name;
~~~

Now all three customers match. Parentheses matter when combining multiple `AND` / `OR` conditions.

## 4. Three-Valued Logic and Expressions Affected by null

### 4.1. Why Can't null Be Treated as false?

| Expression | Result | Reason |
| --- | --- | --- |
| `true AND null` | `null` | The other side is unknown |
| `false AND null` | `false` | One side is already false |
| `true OR null` | `true` | One side is already true |
| `false OR null` | `null` | Unknown whether the other side is true |
| `NOT null` | `null` | Negating an unknown remains unknown |
| `null = null` | `null` | Cannot conclude two unknown values are equal |

~~~cypher
RETURN
  false AND null AS a,
  true AND null AS b,
  true OR null AS c,
  false OR null AS d,
  NOT null AS e;
~~~

Results: `a = false`, `b = null`, `c = true`, `d = null`, `e = null`.

Suppose `c.isVip` has not been recorded: the condition `WHERE NOT c.isVip` does **not** automatically match that customer, because `NOT null` is still `null`. If you want to find customers who are definitely not VIP:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.isVip = false
RETURN c.name;
~~~

The result is only Binh. If the requirement is “not VIP **or unclassified**”, express it as:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.isVip = false OR c.isVip IS NULL
RETURN c.name
ORDER BY c.name;
~~~

The result includes Binh and Chi. Grouping “not VIP” and “unknown” together is a business choice; those two states may still need to be distinguished for data analysis.

### 4.2. Impact on Calculations and String Concatenation

If an operand is missing, many expressions return `null`:

~~~cypher
RETURN
  100 + null AS total,
  100 * null AS amount,
  'Customer: ' || null AS label,
  100 > null AS comparison;
~~~

To calculate a total amount, determine *why* a value is missing. For example, an unrecorded shipping fee might mean “free shipping” or “fee not yet calculated”, depending on the data design. Only in the first case should it be replaced with `0`.

## 5. The coalesce Function: Selecting the First Non-null Value

### 5.1. Syntax and Behavior

`coalesce` accepts multiple expressions and returns **the first value that is not `null`**, evaluated from left to right:

~~~cypher
coalesce(expression1, expression2, ..., expressionN)
~~~

Example:

~~~cypher
RETURN
  coalesce(null, 'Fallback email') AS example1,
  coalesce(null, null, 'Not provided') AS example2,
  coalesce(0, 99) AS example3,
  coalesce(false, true) AS example4,
  coalesce(null, null) AS example5;
~~~

The results are `'Fallback email'`, `'Not provided'`, `0`, `false`, and `null`, respectively.

If **all** arguments are `null`, the result is still `null`. `coalesce` cannot manufacture a meaningful value if you do not supply an appropriate fallback value.

### 5.2. Displaying Default Information

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.name AS customer,
  c.email AS originalEmail,
  coalesce(c.email, 'Email not provided') AS displayEmail
ORDER BY c.demoId;
~~~

| Customer | `originalEmail` | `displayEmail` |
| --- | --- | --- |
| An | `'an@example.com'` | `'an@example.com'` |
| Binh | `null` | `'Email not provided'` |
| Chi | `null` | `'Email not provided'` |

In this query, `coalesce` only transforms the **returned value**; it does not create or write an `email` property on the node. This is a clean way to format data for a UI while preserving the original information.

### 5.3. Multiple Fallback Sources in Priority Order

Suppose a user has `nickname`, `name`, and `demoId`. The display rule is: use `nickname` if available; otherwise use `name`; finally fall back to `demoId`.

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.demoId,
  coalesce(c.nickname, c.name, c.demoId, 'Anonymous customer')
    AS displayName
ORDER BY c.demoId;
~~~

An is displayed as `An` and Chi as `Chi`, while Binh is displayed as an **empty string** because `nickname = ''`. This is an important case: `coalesce` does not evaluate the usefulness of data—it only checks whether a value is `null`.

To treat an empty or whitespace-only nickname as not provided, you can use `CASE`:

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.demoId,
  CASE
    WHEN c.nickname IS NULL OR trim(c.nickname) = ''
      THEN coalesce(c.name, c.demoId)
    ELSE c.nickname
  END AS displayName
ORDER BY c.demoId;
~~~

All three now display their names An, Binh, and Chi. Treating empty strings as missing data is a **business convention**, not the default behavior of `coalesce`.

### 5.4. Coalesce with Numbers and Booleans

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.name,
  c.isVip AS rawVip,
  coalesce(c.isVip, false) AS vipAssumingMissingIsFalse
ORDER BY c.demoId;
~~~

Chi has `rawVip = null` but `vipAssumingMissingIsFalse = false`. Apply this rule only when business logic explicitly specifies “unclassified = not VIP”. If missing data needs investigation, keep `null` and represent it with an “Unknown” label.

For numbers, `coalesce(score, 0)` is convenient for certain sums, but it can skew averages, statistics, or rankings if “no score yet” differs from “score of 0”.

Fallback arguments should have consistent data types. For example, if the `price` column uses numbers, the fallback value should also be numeric; if you want to display text like “Price unavailable”, create a separate presentation column.

### 5.5. Use CASE for Complex Branching

`coalesce` fits the question “what is the first non-null value?”. `CASE` fits situations requiring multi-state classification:

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.name,
  CASE
    WHEN c.isVip IS NULL THEN 'Unclassified'
    WHEN c.isVip = true THEN 'VIP'
    ELSE 'Regular'
  END AS customerType
ORDER BY c.demoId;
~~~

Results: An → VIP; Binh → Regular; Chi → Unclassified.

For division with an unknown or zero denominator, a `CASE` expression also makes the handling policy explicit:

~~~cypher
WITH 100.0 AS total, null AS itemCount
RETURN
  CASE
    WHEN itemCount IS NULL OR itemCount = 0 THEN null
    ELSE total / itemCount
  END AS averagePerItem;
~~~

Do not automatically use `coalesce(itemCount, 0)` and then divide: that risks creating a zero denominator and hides the reason the data was missing.

## 6. Null Produced by OPTIONAL MATCH

### 6.1. Optional Graph Patterns

Standard `MATCH` only returns rows that match the graph pattern. `OPTIONAL MATCH` preserves rows from the preceding part of the query even when the additional pattern does not exist; in that case, unmatched variables take the value `null`.

~~~cypher
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[r:NULL_DEMO_BOUGHT]->(p:NullDemoProduct)
RETURN
  c.name AS customer,
  p.name AS rawProduct,
  coalesce(p.name, 'No product purchased') AS displayProduct,
  r.quantity AS rawQuantity
ORDER BY c.demoId;
~~~

With the sample data:

| Customer | `rawProduct` | `displayProduct` | `rawQuantity` |
| --- | --- | --- | --- |
| An | `Cypher Book` | `Cypher Book` | `2` |
| Binh | `Neo4j Course` | `Neo4j Course` | `1` |
| Chi | `null` | `No product purchased` | `null` |

If you only used `MATCH (c)-[:NULL_DEMO_BOUGHT]->(p)`, Chi would disappear from the results because she has no matching relationship.

### 6.2. Distinguishing a Missing Relationship from a Missing Property

These two cases are not equivalent:

1. `r IS NULL`: no relationship was found for the `OPTIONAL MATCH` pattern.
2. `r.quantity IS NULL`: either no relationship was found, **or** a relationship was found but lacks the `quantity` property.

When identifying a customer who has not purchased anything, check the relationship variable:

~~~cypher
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[r:NULL_DEMO_BOUGHT]->(:NullDemoProduct)
WITH c, r
WHERE r IS NULL
RETURN c.demoId, c.name;
~~~

The result is Chi. Using `WHERE r.quantity IS NULL` instead could also include existing purchase relationships where the quantity was left blank.

### 6.3. WHERE Placement Affects the Result

Compare these two similar queries:

~~~cypher
// Condition is part of OPTIONAL MATCH:
// keeps all three customers, but p is only matched if price > 500000.
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[:NULL_DEMO_BOUGHT]->(p:NullDemoProduct)
WHERE p.price > 500000
RETURN c.name, coalesce(p.name, 'No high-priced product') AS product
ORDER BY c.demoId;
~~~

An and Chi get `product = 'No high-priced product'`, while Binh gets `product = 'Neo4j Course'`.

~~~cypher
// Condition is applied AFTER OPTIONAL MATCH has completed:
// keeps only rows where p.price > 500000.
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[:NULL_DEMO_BOUGHT]->(p:NullDemoProduct)
WITH c, p
WHERE p.price > 500000
RETURN c.name, p.name;
~~~

This time only Binh remains. The reason: `p.price > 500000` evaluates to `null` when `p` is unmatched, so the row is discarded by `WHERE`.

Therefore, decide clearly whether you want to **keep all customers with optional details** or **only keep customers satisfying the condition on the optional relationship**.

### 6.4. Avoid Masking a Missing Relationship with Zero

~~~cypher
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[r:NULL_DEMO_BOUGHT]->(:NullDemoProduct)
RETURN
  c.name,
  r.quantity AS recordedQuantity,
  coalesce(r.quantity, 0) AS quantityOrZero
ORDER BY c.demoId;
~~~

For Chi, `quantityOrZero = 0` may be an appropriate display value for a “quantity purchased” column. However, that value would also be 0 if a purchase relationship **did** exist but the `quantity` property was missing. When auditing data quality, also include `r IS NULL AS noPurchaseRelationship` to distinguish the two origins.

## 7. Null in Aggregation Functions and Reporting

### 7.1. Counting Rows vs. Counting Present Values

`count(*)` counts the number of rows passed into the aggregation. `count(expression)` counts only the rows where the expression is **not `null`**.

~~~cypher
UNWIND [
  {score: 10},
  {score: 20},
  {}
] AS row
RETURN
  count(*) AS numberOfRows,
  count(row.score) AS numberOfRecordedScores;
~~~

Result: `numberOfRows = 3`, `numberOfRecordedScores = 2`. The third record is present but lacks the `score` property.

With `OPTIONAL MATCH`, this difference is especially noticeable:

~~~cypher
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[r:NULL_DEMO_BOUGHT]->(:NullDemoProduct)
RETURN
  c.name AS customer,
  count(*) AS preservedRows,
  count(r) AS purchaseRelationships
ORDER BY customer;
~~~

Chi has `preservedRows = 1` but `purchaseRelationships = 0`: `OPTIONAL MATCH` preserves Chi's row with `r = null`. When reporting the actual number of relationships present, `count(r)` reflects the true count.

### 7.2. Coalesce Can Alter the Average Denominator

~~~cypher
UNWIND [
  {score: 10},
  {score: 20},
  {}
] AS row
RETURN
  avg(row.score) AS averageOfRecorded,
  avg(coalesce(row.score, 0)) AS averageIncludingZero;
~~~

The results are `15.0` and `10.0`, respectively.

- `avg(row.score)` ignores missing scores: only the two scores 10 and 20 are averaged.
- `avg(coalesce(row.score, 0))` treats missing scores as 0: the average of 10, 20, and 0.

Both formulas can be right in different contexts. Decide whether “no score” means “not yet graded” or “scored 0” before using `coalesce` in statistics.

The aggregation function `collect(expression)` also skips `null` values. If you need to preserve the fact that “a row existed but lacked a property”, represent that state with another value or an appropriate map structure before aggregating.

## 8. Updating Data and Importing Missing Values

### 8.1. SET property = null Removes the Property

The snippet below demonstrates this behavior on a practice node:

~~~cypher
MATCH (c:NullDemoCustomer {demoId: 'N-001'})
SET c.email = null
RETURN c.name, c.email IS NULL AS emailMissing;
~~~

The result is `emailMissing = true`, because the `email` property was removed from An. **If you want to keep the original sample data intact for other exercises, do not run this update**; or restore it with:

~~~cypher
MATCH (c:NullDemoCustomer {demoId: 'N-001'})
SET c.email = 'an@example.com'
RETURN c.name, c.email;
~~~

In business logic, distinguish between “delete the stored email” and “no new email was provided so leave it unchanged”. These two actions should not automatically be handled identically.

### 8.2. Do Not Use null as an Identifier Key in MERGE

`MERGE` requires a determinable node or relationship pattern. A `null` value in a `MERGE` pattern property causes an error because it cannot be used to match or create a keyed entity:

~~~cypher
// DO NOT RUN: parameter $email = null will cause MERGE to fail.
MERGE (c:NullDemoCustomer {email: $email})
RETURN c;
~~~

Instead, use a **non-null** identifier key and handle optional properties separately:

~~~cypher
MERGE (c:NullDemoCustomer {demoId: $demoId})
SET c.email = $email
RETURN c.demoId, c.email;
~~~

The query above will **delete** `email` if the `$email` parameter is `null`. If `null` in a request means “do not update email”, use a different update rule, for example:

~~~cypher
MATCH (c:NullDemoCustomer {demoId: $demoId})
SET c.email = coalesce($email, c.email)
RETURN c.demoId, c.email;
~~~

This expression preserves the existing email when `$email` is `null`. However, when an application needs to support **explicitly clearing an email**, separate the clear action from the skip-update action; you cannot overload a single `null` value for both intents.

### 8.3. Empty Strings in CSV Imports Are Not Necessarily null

Different data sources may represent missing values as empty strings or whitespace. When importing data, normalize according to a clear rule:

~~~cypher
WITH {email: '   '} AS row
WITH
  CASE
    WHEN row.email IS NULL OR trim(row.email) = ''
      THEN null
    ELSE trim(row.email)
  END AS normalizedEmail
RETURN normalizedEmail, normalizedEmail IS NULL AS isMissing;
~~~

Result: `normalizedEmail = null` and `isMissing = true`.

With `LOAD CSV WITH HEADERS`, column values are strings; when a cell is blank, inspect and normalize it rather than assuming it is always `null`. If the application needs to distinguish “empty cell” from “missing field”, decide the conversion rules before importing.

## 9. Using null and coalesce in Java Applications

### 9.1. Writing Parameterized Cypher

In the Java Driver or Spring Data Neo4j custom queries, pass values as parameters:

~~~cypher
MATCH (c:NullDemoCustomer {demoId: $demoId})
RETURN
  c.email AS rawEmail,
  coalesce(c.email, $fallbackEmail) AS displayEmail,
  c.email IS NULL AS missingEmail;
~~~

If `$demoId = 'N-002'` and `$fallbackEmail = 'Not provided'`, the result has:

- `rawEmail = null`.
- `displayEmail = 'Not provided'`.
- `missingEmail = true`.

This approach preserves both the raw information and the display value. Avoid persisting UI messages like `'Not provided'` in place of actual database properties, as it later becomes difficult to distinguish user-entered data from presentation text.

### 9.2. Handling Nullable Values in the Neo4j Java Driver

The Java snippet below illustrates result handling; assume the `Driver driver` object is already configured and the sample data is intact:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;

// driver is initialized and lifecycle-managed in the application configuration layer.
try (Session session = driver.session()) {
    var row = session.executeRead(tx ->
        tx.run(
            """
            MATCH (c:NullDemoCustomer {demoId: $demoId})
            RETURN
              c.email AS rawEmail,
              coalesce(c.email, $fallback) AS displayEmail
            """,
            Values.parameters(
                "demoId", "N-002",
                "fallback", "Not provided"
            )
        ).single()
    );

    boolean emailMissing = row.get("rawEmail").isNull();
    String label = row.get("displayEmail").asString();

    System.out.println(emailMissing); // true
    System.out.println(label);        // Not provided
}
~~~

When a returned field may be `null`, check it with `Value.isNull()` before converting to a specific Java type. `coalesce` helps construct a fallback string column once you have validated the replacement rule. The example above uses `single()` because the query is expected to return exactly one row; if none or multiple rows are returned, the application must handle it according to the query contract.

With Spring Data Neo4j, the same principles apply: account for fields that can genuinely be missing, verify type mapping in entities/projections, and use parameters instead of concatenating user input directly into Cypher.

## 10. Performance, Correctness, and Choosing the Right Expression

### 10.1. Prioritize Expressing the Exact Intent

When searching for a node with a specific email:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE c.email = $email
RETURN c.demoId, c.name;
~~~

Direct conditions on a property are typically easier to analyze and more amenable to index usage than function-wrapped conditions:

~~~cypher
MATCH (c:NullDemoCustomer)
WHERE coalesce(c.email, '') = $email
RETURN c.demoId, c.name;
~~~

The two queries are also not necessarily equivalent: the second treats missing emails as empty strings. If `$email = ''`, it could return nodes that have no email, whereas the first query matches only nodes that actually store an empty string.

The actual execution plan depends on the Neo4j version, index type, statistics, and data. You can inspect it with `EXPLAIN` or `PROFILE`, for example:

~~~cypher
EXPLAIN
MATCH (c:NullDemoCustomer)
WHERE c.email IS NOT NULL
RETURN c.demoId, c.email;
~~~

Never alter the semantics of missing values merely to make a query shorter or seemingly faster.

### 10.2. Technique Selection Guidelines

| Business Requirement | Recommended Expression | Reason |
| --- | --- | --- |
| Find missing property | `n.x IS NULL` | Explicit check |
| Find present property | `n.x IS NOT NULL` | Avoids confusion with empty string |
| Display label when data is missing | `coalesce(n.x, 'Not provided')` | Produces a presentation value |
| Choose from multiple sources in order | `coalesce(n.nickname, n.name, n.id)` | Returns first non-null value |
| Distinguish missing/true/false states | `CASE WHEN n.flag IS NULL THEN ...` | Preserves business meaning |
| Absence of optional relationship | `OPTIONAL MATCH ... WHERE r IS NULL` after `WITH` | Detects non-existent relationship |
| Count records actually having a property | `count(n.x)` | Ignores null values |
| Count all input rows | `count(*)` | Does not skip rows with null properties |
| Average only over recorded values | `avg(n.score)` | Does not default missing scores to 0 |
| Update optional property | `SET n.x = $x` or `CASE/coalesce` rule | Clearly chooses delete, keep, or assign |

## 11. Practice Exercises and Solutions

### Exercise 1. Predict coalesce Results

Without running it first, predict the output:

~~~cypher
RETURN
  coalesce(null, 0, 10) AS a,
  coalesce(false, true) AS b,
  coalesce('', 'unknown') AS c,
  coalesce(null, null) AS d;
~~~

**Solution:** `a = 0`, `b = false`, `c = ''`, `d = null`. Each case demonstrates that `coalesce` checks only for non-`null`.

### Exercise 2. Classify Email Status

Requirement: distinguish **missing email**, **empty-string email**, and **non-empty valid email**.

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.name,
  CASE
    WHEN c.email IS NULL THEN 'Missing email'
    WHEN trim(c.email) = '' THEN 'Empty email'
    ELSE 'Has email'
  END AS emailStatus
ORDER BY c.demoId;
~~~

**Solution on sample data:** An → Has email; Binh → Missing email; Chi → Missing email. The “Has email” category only confirms a non-empty string, not valid email syntax.

### Exercise 3. Find Customers Who Have Not Purchased Any Product

Requirement: use `OPTIONAL MATCH` and an explicit check:

~~~cypher
MATCH (c:NullDemoCustomer)
OPTIONAL MATCH (c)-[r:NULL_DEMO_BOUGHT]->(:NullDemoProduct)
WITH c, r
WHERE r IS NULL
RETURN c.demoId, c.name;
~~~

**Solution:** Chi. If a customer has multiple purchase relationships, the query retains only customers matching none; anyone who has purchased at least once will not be returned.

### Exercise 4. Average Score With and Without a Default Value

~~~cypher
UNWIND [10, null, 20] AS score
RETURN
  count(*) AS total,
  count(score) AS recorded,
  avg(score) AS averageRecorded,
  avg(coalesce(score, 0)) AS averageWithMissingAsZero;
~~~

**Solution:** `total = 3`, `recorded = 2`, `averageRecorded = 15.0`, `averageWithMissingAsZero = 10.0`. Explain why the two averages differ before selecting a formula for an actual report.

### Exercise 5. Design a Query for an API

An API lists all customers and needs to return both the raw email and a fallback string for the UI. One solution:

~~~cypher
MATCH (c:NullDemoCustomer)
RETURN
  c.demoId AS id,
  c.name AS name,
  c.email AS email,
  c.email IS NULL AS emailMissing,
  coalesce(c.email, 'Not provided') AS emailLabel
ORDER BY id;
~~~

The query provides a display column without losing the ability to distinguish missing emails. If the UI also wants to handle empty strings, extend it with `CASE` according to UI design rules.

## 12. Summary

In Cypher, `null` is a meaningful state, particularly for non-existent properties and results from `OPTIONAL MATCH`. Three principles to remember:

1. **Check explicitly** with `IS NULL` and `IS NOT NULL`; equality comparisons like `= null` do not yield proper Boolean results.
2. **Replace values only when business logic permits:** `coalesce` picks the first non-`null` value, but does not treat `0`, `false`, empty strings, or empty lists as missing.
3. **Preserve data semantics:** note that `WHERE` keeps only `true`; `OPTIONAL MATCH` can introduce null variables; and `count(expression)`, `avg(expression)`, and aggregations handle null in ways that directly impact reports.

When modeling property graphs in Neo4j, consistently applying these rules helps you write readable Cypher, reduce errors during data import and updates, and support clean result mapping in the Java Driver and Spring Data Neo4j.
