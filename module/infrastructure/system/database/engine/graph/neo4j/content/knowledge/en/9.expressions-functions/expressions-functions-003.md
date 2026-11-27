# CASE for Conditional Branching in Cypher Query Results

When working with a **property graph** in Neo4j, raw data is often not ready to be sent directly to a UI or report. From the properties of nodes and relationships, an application also needs to derive values such as “Low stock”, “VIP customer”, “High-value order”, or “No transactions yet”. Cypher provides the `CASE` expression to choose **a result based on conditions** directly inside the query.

This lesson belongs to the **Expressions and Functions** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module. The content focuses on the two basic forms of `CASE`, branch evaluation order, handling `null`, combining `CASE` with `MATCH`, `OPTIONAL MATCH`, `WITH`, `RETURN`, and `ORDER BY`, and considerations when integrating results into Java Driver or Spring Data Neo4j applications.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why `CASE` is a **value-returning expression**, unlike control-flow statements in programming languages.
- Write the `CASE expression WHEN value THEN result ... ELSE ... END` form to map a value to a label.
- Write the `CASE WHEN condition THEN result ... ELSE ... END` form to express compound conditions or value ranges.
- Understand branch evaluation precedence, the `ELSE` branch, and the impact of `null`.
- Combine `CASE` with node properties, relationship properties, optional matches, and aggregations.
- Design result columns with stable types that map cleanly in Java Driver or Spring Data Neo4j queries.
- Recognize when to use `CASE`, `coalesce()`, `WHERE`, or application-layer data processing.

## 2. CASE Is an Expression, Not a Control Statement

### 2.1. Where Can a CASE Result Be Used?

In Cypher, `CASE ... END` produces **a single value**. That value can be aliased with `AS`, used for sorting, or passed forward via `WITH`:

~~~cypher
RETURN
  CASE
    WHEN 8 >= 5 THEN 'Pass'
    ELSE 'Fail'
  END AS assessment;
~~~

The result is a single column `assessment` with the value `'Pass'`. The query does not execute a `THEN` code block like in Java; it **evaluates expressions and selects a return value**.

| Location | Usage Example | Goal |
| --- | --- | --- |
| `RETURN` | `RETURN CASE WHEN p.stock = 0 THEN 'Out' ELSE 'In' END AS label` | Display a computed label |
| `WITH` | `WITH p, CASE WHEN p.price >= 500000 THEN 'High' ELSE 'Low' END AS priceGroup` | Create an intermediate value for downstream use |
| `ORDER BY` | `ORDER BY CASE WHEN p.active = false THEN 1 ELSE 0 END` | Sort according to business priority |
| `SET` | `SET p.stockStatus = CASE WHEN p.stock = 0 THEN 'Out' ELSE 'In' END` | Write a property from an expression |
| Aggregation | `sum(CASE WHEN p.active = true THEN 1 ELSE 0 END)` | Conditional counting |

`CASE` does not remove rows from the result set by itself. When you need to filter rows, `WHERE` expresses that intent directly; `CASE` primarily determines **the value of an expression**.

### 2.2. Two Basic Forms of CASE

**Simple CASE** compares one expression against a list of values:

~~~cypher
CASE expression
  WHEN value1 THEN result1
  WHEN value2 THEN result2
  ELSE fallback
END
~~~

**Generic CASE (or searched CASE)** evaluates each Boolean condition in turn:

~~~cypher
CASE
  WHEN condition1 THEN result1
  WHEN condition2 THEN result2
  ELSE fallback
END
~~~

Both evaluate `WHEN` branches sequentially and return the result of the **first matching branch**. If no branch matches, `ELSE` is used. If `ELSE` is omitted, the result is `null`.

| Criterion | Simple CASE | Generic CASE |
| --- | --- | --- |
| Evaluation method | Compares one base value against each `WHEN` value | Each `WHEN` is an independent Boolean condition |
| Best suited for | Mapping status codes, customer tiers, event types | Numeric thresholds, `AND`/`OR` combinations, `IS NULL` checks |
| Example | `CASE c.tier WHEN 'GOLD' THEN ... END` | `CASE WHEN c.score >= 80 THEN ... END` |
| Handling `null` | Must handle intentionally; `WHEN null` does not check for missing values as expected | Can directly use `WHEN c.tier IS NULL THEN ...` |
| Expressiveness | Concise when matching against fixed values | Most flexible when each branch has distinct rules |

**Convention in this lesson:** we focus on these two widely applicable forms. Some Neo4j versions support additional `CASE` syntax variations; when using version-specific features, check the Cypher documentation for your running version.

## 3. Preparing Sample Graph Data

Examples using only `RETURN` can run standalone. To try `MATCH` queries, create the sample data below in a **practice database**. This snippet intentionally prefixes labels and relationship types with `CaseDemo` to keep them distinct from production data.

~~~cypher
// Three customers, where Chi has no tier or verification status yet.
MERGE (an:CaseDemoCustomer {code: 'C001'})
SET an.name = 'An', an.tier = 'GOLD', an.verified = true

MERGE (binh:CaseDemoCustomer {code: 'C002'})
SET binh.name = 'Binh', binh.tier = 'SILVER', binh.verified = false

MERGE (chi:CaseDemoCustomer {code: 'C003'})
SET chi.name = 'Chi'
REMOVE chi.tier, chi.verified

// Four products with varying stock states.
MERGE (book:CaseDemoProduct {sku: 'P001'})
SET book.name = 'Cypher Book',
    book.price = 320000,
    book.stock = 12,
    book.active = true

MERGE (course:CaseDemoProduct {sku: 'P002'})
SET course.name = 'Neo4j Course',
    course.price = 850000,
    course.stock = 2,
    course.active = true

MERGE (notebook:CaseDemoProduct {sku: 'P003'})
SET notebook.name = 'Notebook',
    notebook.price = 90000,
    notebook.stock = 0,
    notebook.active = false

MERGE (gift:CaseDemoProduct {sku: 'P004'})
SET gift.name = 'Gift Card',
    gift.price = 150000,
    gift.active = true
REMOVE gift.stock

// Two purchase relationships; Binh's order has no discount recorded.
MERGE (an)-[r1:CASE_DEMO_BUYS]->(book)
SET r1.quantity = 2, r1.discount = 0.1

MERGE (binh)-[r2:CASE_DEMO_BUYS]->(course)
SET r2.quantity = 1
REMOVE r2.discount;
~~~

The graph looks like this:

~~~text
(An:CaseDemoCustomer {tier:'GOLD'})
      └──[:CASE_DEMO_BUYS {quantity:2, discount:0.1}]──>
                                           (Cypher Book:CaseDemoProduct)

(Binh:CaseDemoCustomer {tier:'SILVER'})
      └──[:CASE_DEMO_BUYS {quantity:1}]──────────────────>
                                           (Neo4j Course:CaseDemoProduct)

(Chi:CaseDemoCustomer {tier: <missing>})   (no purchase relationship)
~~~

Key details for the examples:

| Product | Price (VND) | `stock` | `active` |
| --- | ---: | ---: | --- |
| Cypher Book (`P001`) | 320,000 | 12 | `true` |
| Neo4j Course (`P002`) | 850,000 | 2 | `true` |
| Notebook (`P003`) | 90,000 | 0 | `false` |
| Gift Card (`P004`) | 150,000 | No property | `true` |

Specifically, `P004.stock` evaluates to `null` because the property does not exist. This is **different** from a stock count of `0`.

## 4. Simple CASE: Mapping a Value to a Label

### 4.1. Syntax and Minimal Example

~~~cypher
RETURN
  CASE 'GOLD'
    WHEN 'GOLD' THEN 'High Priority'
    WHEN 'SILVER' THEN 'Priority'
    WHEN 'BRONZE' THEN 'Standard'
    ELSE 'Unranked'
  END AS customerTier;
~~~

Result: `customerTier = 'High Priority'`.

The value `'GOLD'` after `CASE` is compared sequentially against each value after `WHEN`. When an equal value is found, Cypher returns the expression after `THEN` and skips the remaining branches.

### 4.2. Mapping a Node Property

~~~cypher
MATCH (c:CaseDemoCustomer)
RETURN
  c.code AS customerCode,
  c.name AS customer,
  c.tier AS rawTier,
  CASE c.tier
    WHEN 'GOLD' THEN 'Gold Customer'
    WHEN 'SILVER' THEN 'Silver Customer'
    WHEN 'BRONZE' THEN 'Bronze Customer'
    ELSE 'No Tier'
  END AS tierLabel
ORDER BY customerCode;
~~~

Sample result:

| `customer` | `rawTier` | `tierLabel` |
| --- | --- | --- |
| An | `GOLD` | Gold Customer |
| Binh | `SILVER` | Silver Customer |
| Chi | `null` | No Tier |

For Chi, no branch matches because `tier` is absent, so execution falls into `ELSE`. Simple `CASE` is ideal when the system stores statuses as short codes and the UI needs a human-readable label.

### 4.3. ELSE Is the Fallback Branch

~~~cypher
RETURN
  CASE 'PLATINUM'
    WHEN 'GOLD' THEN 'Gold Customer'
    WHEN 'SILVER' THEN 'Silver Customer'
    ELSE 'Other or Unspecified Tier'
  END AS tierLabel;
~~~

The result is `'Other or Unspecified Tier'`. In this example, `ELSE` merges both **new codes not in the mapping table** and **missing values**. That may be reasonable for a UI label, but insufficient if you need data quality analysis.

If `ELSE` is omitted:

~~~cypher
RETURN
  CASE 'PLATINUM'
    WHEN 'GOLD' THEN 'Gold Customer'
    WHEN 'SILVER' THEN 'Silver Customer'
  END AS tierLabel;
~~~

The returned value is `null`. This rule applies to both simple CASE and generic CASE.

### 4.4. Why Isn't WHEN null a Check for Missing Data?

~~~cypher
RETURN
  CASE null
    WHEN null THEN 'Missing value'
    ELSE 'No match'
  END AS result;
~~~

The result is `'No match'`. In standard simple CASE, value checks rely on equality comparison; in Cypher's three-valued logic, `null = null` evaluates to `null` rather than `true`. Hence, the `WHEN null` branch is not selected the way many expect.

If you want to distinguish missing values, use **generic CASE** with `IS NULL`, or apply a fallback rule right before the simple CASE.

## 5. Generic CASE: Evaluating Boolean Conditions

### 5.1. A Branch Can Contain Comparison Expressions

~~~cypher
RETURN
  CASE
    WHEN 9 >= 8 THEN 'Excellent'
    WHEN 9 >= 5 THEN 'Pass'
    ELSE 'Fail'
  END AS result;
~~~

The result is `'Excellent'`. Both of the first two conditions are true, but only the result of the **first true condition** is selected. This forms the basis for implementing threshold-based classification scales.

Example with a score parameter `$score`:

~~~cypher
WITH $score AS score
RETURN
  score,
  CASE
    WHEN score IS NULL THEN 'No score'
    WHEN score >= 8.0 THEN 'Excellent'
    WHEN score >= 6.5 THEN 'Good'
    WHEN score >= 5.0 THEN 'Average'
    ELSE 'Fail'
  END AS classification;
~~~

With `score = 7.0`, the result is `'Good'`; with `score = null`, the result is `'No score'`. The expression starts by handling `null`, then orders thresholds **from highest to lowest**.

### 5.2. Branch Order Changes the Result

These two queries are not equivalent:

~~~cypher
RETURN
  CASE
    WHEN 9 >= 5 THEN 'Pass'
    WHEN 9 >= 8 THEN 'Excellent'
    ELSE 'Fail'
  END AS classification;
~~~

The result is `'Pass'`. The `9 >= 8` branch will never be reached because `9 >= 5` already evaluated to true first.

When writing overlapping threshold scales like `>= 5` and `>= 8`, check the stricter threshold first. If conditions are mutually exclusive, order matters less, though maintaining a consistent order still makes the query easier to audit.

### 5.3. Combining AND, OR, and NOT in WHEN

`WHEN` conditions can contain any valid Boolean expression:

~~~cypher
MATCH (p:CaseDemoProduct)
RETURN
  p.name AS product,
  CASE
    WHEN p.active = false THEN 'Discontinued'
    WHEN p.stock IS NULL THEN 'Stock not updated'
    WHEN p.stock = 0 THEN 'Out of stock'
    WHEN p.stock > 0 AND p.stock <= 3 THEN 'Low stock'
    ELSE 'Available for sale'
  END AS stockStatus
ORDER BY p.sku;
~~~

Expected result:

| Product | `stockStatus` | Reason |
| --- | --- | --- |
| Cypher Book | Available for sale | Active, 12 in stock |
| Neo4j Course | Low stock | Active, 2 in stock |
| Notebook | Discontinued | `active = false` takes precedence |
| Gift Card | Stock not updated | `stock` does not exist |

Key takeaway: Notebook has both `stock = 0` and `active = false`. Because the “Discontinued” branch appears first, it is chosen. If the business wants “Out of stock” to take priority, reorder the branches or design a different rule.

### 5.4. Classifying by Multiple Properties

On a customer node, `verified` and `tier` can be combined:

~~~cypher
MATCH (c:CaseDemoCustomer)
RETURN
  c.name AS customer,
  CASE
    WHEN c.verified IS NULL THEN 'Unverified'
    WHEN c.verified = false THEN 'Needs verification'
    WHEN c.verified = true AND c.tier = 'GOLD' THEN 'Verified VIP'
    ELSE 'Verified'
  END AS customerStatus
ORDER BY c.code;
~~~

On the sample data, An is “Verified VIP”, Binh is “Needs verification”, and Chi is “Unverified”. When multiple states compete for priority, define the business policy before ordering the `WHEN` branches.

## 6. CASE and Cypher's Three-Valued Logic

### 6.1. A WHEN Condition Must Evaluate to true

In generic CASE, a branch is selected only when its `WHEN` condition evaluates to **`true`**. Conditions evaluating to `false` or `null` do not trigger that branch.

~~~cypher
RETURN
  CASE
    WHEN null = null THEN 'Equal'
    WHEN null IS NULL THEN 'Missing value'
    ELSE 'Unknown'
  END AS result;
~~~

The result is `'Missing value'`. The condition `null = null` evaluates to `null`, not `true`, so Cypher moves on to evaluate the next `WHEN`.

Another example:

~~~cypher
RETURN
  CASE
    WHEN null > 10 THEN 'Greater'
    WHEN null <= 10 THEN 'Less or equal'
    ELSE 'No data'
  END AS result;
~~~

The result is `'No data'` because neither comparison with `null` returns `true`.

### 6.2. Null Differs from false, 0, and Empty String

~~~cypher
UNWIND [
  {value: null},
  {value: false},
  {value: 0},
  {value: ''}
] AS row
RETURN
  row.value AS originalValue,
  CASE
    WHEN row.value IS NULL THEN 'Missing'
    WHEN row.value = false THEN 'Boolean false'
    WHEN row.value = 0 THEN 'Zero'
    WHEN row.value = '' THEN 'Empty string'
    ELSE 'Other value'
  END AS description;
~~~

Use this example as a data-type exercise: `null`, `false`, `0`, and `''` all carry distinct meanings. When classifying data that may have mixed types, verify your type policy and use type-appropriate conditions. In production applications, keep a **consistent type per property** instead of mixing Booleans, numbers, and strings under the same property name.

### 6.3. CASE with coalesce

These two constructs serve different purposes:

| Construct | Best Used When | Example |
| --- | --- | --- |
| `coalesce(x, fallback)` | Only the first non-null value is needed | `coalesce(c.tier, 'UNKNOWN')` |
| `CASE WHEN x IS NULL THEN ... ELSE ... END` | Distinguishing missing vs. present values | `CASE WHEN c.tier IS NULL THEN 'Unranked' ELSE c.tier END` |
| `CASE WHEN ... THEN ... WHEN ... THEN ... END` | Branching across multiple rules | `CASE WHEN p.active = false THEN ... WHEN p.stock = 0 THEN ... END` |

You can combine both to keep a simple CASE concise:

~~~cypher
MATCH (c:CaseDemoCustomer)
RETURN
  c.name,
  CASE coalesce(c.tier, 'UNKNOWN')
    WHEN 'GOLD' THEN 'Gold Customer'
    WHEN 'SILVER' THEN 'Silver Customer'
    WHEN 'UNKNOWN' THEN 'Unranked'
    ELSE 'Other tier'
  END AS tierLabel
ORDER BY c.code;
~~~

This works if `'UNKNOWN'` **cannot** be a legitimate tier code in your data. If it could be a real value, use generic CASE with `c.tier IS NULL` to avoid conflating the two cases.

### 6.4. Guarding Calculations Against Invalid Denominators with CASE

Consider calculating average revenue per product, where product count could be 0 or missing:

~~~cypher
WITH 125000.0 AS revenue, 0 AS itemCount
RETURN
  CASE
    WHEN itemCount IS NULL OR itemCount = 0 THEN null
    ELSE revenue / itemCount
  END AS averageRevenue;
~~~

The result is `null`, meaning “no defined average”. If you want to present this to a user, you can add a status column such as `'No products'`.

This explicit policy clarifies business intent far better than blindly replacing a missing denominator with 1 or performing division without guarding against zero.

## 7. CASE in Relationship and Path Queries

### 7.1. Reading Relationship Properties

Relationships in Neo4j can carry properties such as `quantity`, `discount`, and `createdAt`. They participate in `CASE` expressions just like node properties:

~~~cypher
MATCH (c:CaseDemoCustomer)-[r:CASE_DEMO_BUYS]->(p:CaseDemoProduct)
RETURN
  c.name AS customer,
  p.name AS product,
  r.quantity AS quantity,
  CASE
    WHEN r.quantity IS NULL THEN 'Missing quantity'
    WHEN r.quantity >= 2 THEN 'Bulk purchase'
    ELSE 'Single purchase'
  END AS purchaseGroup
ORDER BY c.code;
~~~

With the sample data, An is classified as “Bulk purchase” and Binh as “Single purchase”. The conditions here rely on the **relationship property** `r`, not on the product property `p`.

### 7.2. OPTIONAL MATCH: Distinguishing Missing Relationship from Missing Property

`OPTIONAL MATCH` preserves customers who have no transactions. When no matching relationship exists, the matched variables `r` and `p` become `null`:

~~~cypher
MATCH (c:CaseDemoCustomer)
OPTIONAL MATCH (c)-[r:CASE_DEMO_BUYS]->(p:CaseDemoProduct)
RETURN
  c.name AS customer,
  CASE
    WHEN r IS NULL THEN 'Never purchased'
    WHEN r.quantity IS NULL THEN 'Transaction missing quantity'
    WHEN r.quantity >= 2 THEN 'Purchased multiple'
    ELSE 'Purchased'
  END AS relationshipStatus,
  coalesce(p.name, 'No product') AS productLabel
ORDER BY c.code;
~~~

Results: An → “Purchased multiple”; Binh → “Purchased”; Chi → “Never purchased”.

**Key distinction:** `r IS NULL` means **no relationship was found**. In contrast, `r.quantity IS NULL` could mean either the relationship does not exist *or* a real relationship exists without a `quantity` property. Placing `r IS NULL` first ensures the label states the exact cause.

If a customer has multiple transactions, `OPTIONAL MATCH` produces multiple rows for that customer and `CASE` is evaluated **per row**. To produce one summary label per customer, aggregate by customer before classifying.

### 7.3. Classifying After Aggregation

~~~cypher
MATCH (c:CaseDemoCustomer)
OPTIONAL MATCH (c)-[r:CASE_DEMO_BUYS]->(:CaseDemoProduct)
WITH c, count(r) AS purchaseCount
RETURN
  c.name AS customer,
  purchaseCount,
  CASE
    WHEN purchaseCount = 0 THEN 'Not purchased'
    WHEN purchaseCount = 1 THEN 'Purchased once'
    ELSE 'Purchased multiple times'
  END AS frequencyGroup
ORDER BY c.code;
~~~

Sample results: An = 1, Binh = 1, Chi = 0. `count(r)` does not count `null` values from `OPTIONAL MATCH`, so Chi gets `purchaseCount = 0`.

Note: the query above counts `CASE_DEMO_BUYS` **relationships**, which does not necessarily equal order count in every graph model. If your model groups multiple products under a single order node or represents multiple purchases with one relationship, choose the appropriate counting unit.

## 8. Combining CASE with WITH and Computed Expressions

### 8.1. Creating Intermediate Columns to Avoid Repeating Formulas

Suppose we need to compute payment amount from unit price, quantity, and relationship discount. Because `discount` may be missing, we define **no discount** in this exercise using `coalesce(r.discount, 0.0)`:

~~~cypher
MATCH (c:CaseDemoCustomer)-[r:CASE_DEMO_BUYS]->(p:CaseDemoProduct)
WITH
  c, p, r,
  p.price * r.quantity *
    (1 - coalesce(r.discount, 0.0)) AS amount
RETURN
  c.name AS customer,
  p.name AS product,
  amount,
  CASE
    WHEN amount IS NULL THEN 'Missing amount info'
    WHEN amount >= 800000 THEN 'Very high-value order'
    WHEN amount >= 500000 THEN 'High-value order'
    ELSE 'Regular order'
  END AS orderType
ORDER BY c.code;
~~~

With the sample data, An has `amount` approximately `576000` and falls into “High-value order”; Binh has `amount = 850000` and falls into “Very high-value order”.

`WITH` lets you compute and alias `amount` first, then reference that alias inside `CASE` in `RETURN`. Calculations involving `FLOAT` rates may incur minor floating-point representation differences; for real financial data, establish proper storage units and rounding rules.

### 8.2. Checking for null Before Classifying

Suppose a product does not have `price` recorded yet:

~~~cypher
WITH {name: 'Sample product', price: null} AS p
RETURN
  p.name,
  CASE
    WHEN p.price IS NULL THEN 'No price'
    WHEN p.price >= 500000 THEN 'High price'
    ELSE 'Regular price'
  END AS priceLabel;
~~~

The result is `'No price'`. If you omitted the `null` check, the query would fall into `ELSE` and label it “Regular price”, misinterpreting missing data as low-priced data.

### 8.3. CASE and WHERE Have Different Roles

**Classify while keeping all rows:**

~~~cypher
MATCH (p:CaseDemoProduct)
RETURN
  p.name,
  CASE
    WHEN p.active = true THEN 'On sale'
    ELSE 'Not for sale'
  END AS saleStatus;
~~~

This query returns all four products. **Retrieve only products on sale:**

~~~cypher
MATCH (p:CaseDemoProduct)
WHERE p.active = true
RETURN p.name;
~~~

The second query returns only the three active products. Choose `WHERE` when your goal is to reduce the number of rows, and `CASE` when your goal is to compute a classification value per row.

## 9. CASE in Aggregations and Reporting

### 9.1. Conditional Counting

A `CASE` expression can return 1 or 0 per row, and `sum()` totals them:

~~~cypher
MATCH (p:CaseDemoProduct)
RETURN
  count(*) AS totalProducts,
  sum(CASE WHEN p.active = true THEN 1 ELSE 0 END) AS activeProducts,
  sum(CASE WHEN p.active = false THEN 1 ELSE 0 END) AS inactiveProducts,
  sum(CASE WHEN p.stock IS NULL THEN 1 ELSE 0 END) AS missingStockProducts;
~~~

Sample results: `totalProducts = 4`, `activeProducts = 3`, `inactiveProducts = 1`, and `missingStockProducts = 1`.

If one of these properties can be `null`, decide whether to count those records in an “other/unknown” bucket. Counting only `active = true` and `active = false` will **not automatically include** nodes missing `active`.

### 9.2. Grouping by a CASE Expression

~~~cypher
MATCH (p:CaseDemoProduct)
WITH
  CASE
    WHEN p.active = false THEN 'Discontinued'
    WHEN p.stock IS NULL THEN 'Stock unknown'
    WHEN p.stock = 0 THEN 'Out of stock'
    WHEN p.stock <= 3 THEN 'Low stock'
    ELSE 'In stock'
  END AS stockGroup
RETURN stockGroup, count(*) AS numberOfProducts
ORDER BY stockGroup;
~~~

The result has four groups, with one product each:

| `stockGroup` | `numberOfProducts` |
| --- | ---: |
| In stock | 1 |
| Stock unknown | 1 |
| Discontinued | 1 |
| Low stock | 1 |

In this query, records are grouped by the **result of the CASE expression**, rather than directly by raw `stock` or `active` values. This is useful for dashboards and summary reports.

### 9.3. Keeping Result Types Consistent

`CASE` can return values from different expressions. However, to simplify application handling and avoid type conversion errors, have all branches return the same **semantic type**—for example, all `STRING` for labels or all `INTEGER` for priority levels.

Write:

~~~cypher
RETURN
  CASE
    WHEN 7 >= 8 THEN 'Excellent'
    WHEN 7 >= 5 THEN 'Pass'
    ELSE 'Fail'
  END AS gradeLabel;
~~~

Avoid creating a column where one branch returns `'Pass'` and another returns `0` if your API contract expects a string. When both a code and a label are needed, return **two separate columns**, such as `gradeCode` and `gradeLabel`.

## 10. Business-Rule Sorting with CASE

Alphabetical order of status names rarely matches business priority. You can generate a **numeric sort key**:

~~~cypher
MATCH (p:CaseDemoProduct)
WITH
  p,
  CASE
    WHEN p.active = false THEN 4
    WHEN p.stock IS NULL THEN 3
    WHEN p.stock = 0 THEN 2
    WHEN p.stock <= 3 THEN 1
    ELSE 0
  END AS statusPriority
RETURN
  p.name AS product,
  p.stock AS stock,
  statusPriority
ORDER BY statusPriority ASC, product ASC;
~~~

Under this example rule, well-stocked products (level 0) appear before low-stock products (level 1), followed by unknown stock (level 3) and discontinued products (level 4).

Two points to note:

1. Priority levels are a system design choice. If you need out-of-stock products first for restocking workflows, move that group to the top.
2. Defining `CASE` inside `WITH` creates the `statusPriority` alias so it can be both returned and sorted on. This is cleaner than duplicating a long expression in multiple clauses.

## 11. Conditionally Updating Properties with CASE

In Cypher, the value of a `CASE` expression can be assigned to a property using `SET`. The following example **modifies data** in the practice database:

~~~cypher
MATCH (p:CaseDemoProduct)
SET p.stockLabel =
  CASE
    WHEN p.active = false THEN 'Discontinued'
    WHEN p.stock IS NULL THEN 'Stock unknown'
    WHEN p.stock = 0 THEN 'Out of stock'
    WHEN p.stock <= 3 THEN 'Low stock'
    ELSE 'In stock'
  END
RETURN p.sku, p.name, p.stockLabel
ORDER BY p.sku;
~~~

The `CaseDemoProduct` nodes gain a `stockLabel` property. Before persisting a derived value in a production graph, consider: when `stock` or `active` changes, does the application have a mechanism to update `stockLabel` so the data does not become stale?

For statuses derived directly from properties, many systems compute them in `RETURN` to avoid synchronizing extra properties. If you want to reset the practice dataset to its prior state, remove the demo property:

~~~cypher
MATCH (p:CaseDemoProduct)
REMOVE p.stockLabel
RETURN count(p) AS cleanedProducts;
~~~

Do not confuse `SET p.stockLabel = CASE ... END` with branching to execute two different `SET` clauses. `CASE` produces **a value to be assigned**.

## 12. CASE in the Java Driver and Spring Data Neo4j

### 12.1. Returning Classified Results Using Parameters

When a Java application queries Neo4j, pass variable values via parameters, such as `$sku` and `$lowStockThreshold`:

~~~cypher
MATCH (p:CaseDemoProduct {sku: $sku})
RETURN
  p.sku AS sku,
  p.name AS name,
  CASE
    WHEN p.active = false THEN 'INACTIVE'
    WHEN p.stock IS NULL THEN 'UNKNOWN'
    WHEN p.stock = 0 THEN 'OUT_OF_STOCK'
    WHEN p.stock <= $lowStockThreshold THEN 'LOW_STOCK'
    ELSE 'AVAILABLE'
  END AS stockStatus;
~~~

With `sku = 'P002'` and `lowStockThreshold = 3`, `stockStatus` is `'LOW_STOCK'`. Returning stable codes like `LOW_STOCK` is usually better for APIs and application logic; the UI can localize those codes into the desired language.

### 12.2. Java Driver Example

The code below illustrates querying and mapping; assume `Driver driver` has already been initialized by the application configuration layer:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;

// The driver variable is provided by the application configuration.
try (Session session = driver.session()) {
    var result = session.executeRead(tx ->
        tx.run(
            """
            MATCH (p:CaseDemoProduct {sku: $sku})
            RETURN
              p.name AS name,
              CASE
                WHEN p.active = false THEN 'INACTIVE'
                WHEN p.stock IS NULL THEN 'UNKNOWN'
                WHEN p.stock = 0 THEN 'OUT_OF_STOCK'
                WHEN p.stock <= $threshold THEN 'LOW_STOCK'
                ELSE 'AVAILABLE'
              END AS stockStatus
            """,
            Values.parameters("sku", "P002", "threshold", 3)
        ).single()
    );

    String name = result.get("name").asString();
    String status = result.get("stockStatus").asString();
    System.out.println(name + " -> " + status);
    // Neo4j Course -> LOW_STOCK
}
~~~

All return values from `CASE` in this example are `STRING` and an `ELSE` branch is always present, so converting to `String` is safe once a single record is returned. If `ELSE` is omitted or a branch can return `null`, check `Value.isNull()` before calling `asString()`.

In Spring Data Neo4j, `@Query` methods can also use `CASE` expressions to populate projection/DTO columns. Ensure alias names and return types match the mapping contract, and define how empty results are handled.

### 12.3. Where Should Classification Logic Live?

There are two common designs:

| Processing Location | Advantages | Considerations |
| --- | --- | --- |
| In Cypher using `CASE` | Applies rules during the query; reduces post-fetch transformation steps | Business rules can become scattered across many queries if not managed centrally |
| In Java after reading raw properties | Easy to encapsulate, reuse, and unit test in application code | Must fetch all raw properties and handle `null` consistently |

No single choice fits every system. For well-defined reporting queries or projections, `CASE` is often convenient; for complex, frequently changing business rules, consider centralizing them in the application layer or a shared query layer.

## 13. Performance and Maintainability

### 13.1. Prefer Simple Filter Predicates When Indexes Exist

Neo4j can optimize node access using indexes when `WHERE` conditions match the indexed property and index type. For example:

~~~cypher
EXPLAIN
MATCH (p:CaseDemoProduct)
WHERE p.sku = $sku
RETURN
  p.name,
  CASE
    WHEN p.stock <= 3 THEN 'Low stock'
    ELSE 'Other'
  END AS stockStatus;
~~~

Here, `WHERE p.sku = $sku` expresses the filter predicate directly; `CASE` only classifies matched rows. Moving filtering logic into complex expressions or wrapping lookup properties in functions can affect index utilization. When performance matters, run `EXPLAIN` or `PROFILE` with representative data and parameters to inspect the plan.

### 13.2. Avoid Duplicating Long CASE Expressions

If multiple columns or stages depend on the same classification, compute it once in `WITH`:

~~~cypher
MATCH (p:CaseDemoProduct)
WITH
  p,
  CASE
    WHEN p.active = false THEN 'INACTIVE'
    WHEN p.stock IS NULL THEN 'UNKNOWN'
    WHEN p.stock <= 3 THEN 'LOW'
    ELSE 'OK'
  END AS stockCode
RETURN
  p.sku AS sku,
  p.name AS product,
  stockCode,
  CASE stockCode
    WHEN 'INACTIVE' THEN 'Discontinued'
    WHEN 'UNKNOWN' THEN 'No inventory data'
    WHEN 'LOW' THEN 'Needs restock'
    ELSE 'On sale'
  END AS stockLabel
ORDER BY stockCode, sku;
~~~

This query illustrates combining a generic CASE to compute a code with a simple CASE to map that code to a label. For `P003.stock = 0` with `active = false`, the code is `INACTIVE` because that branch takes precedence.

In larger applications, name columns semantically and standardize classification rules. If “out of stock” must be distinguished from “low stock”, add a `stock = 0` branch before `stock <= 3`.

### 13.3. Boundaries of CASE

`CASE` expresses **value selection**, and cannot on its own:

- Switch relationship types inside `MATCH` by placing two different Cypher patterns inside `THEN`.
- Execute two distinct sequences of `CREATE`/`DELETE` clauses.
- Enforce data integrity constraints on source data.
- Create indexes or constraints; that belongs to schema management commands.

If a task requires complex conditional write paths, structure separate update steps or handle decision flow in the application layer rather than cramming everything into a single `CASE` expression.

## 14. Common Mistakes

| Mistake or Misconception | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Using `CASE x WHEN null THEN ...` to detect missing values | `null = null` does not evaluate to `true` | Use generic `CASE WHEN x IS NULL THEN ...` |
| Omitting `ELSE` and expecting an empty string | Unmatched values return `null` | Write `ELSE ''` if business logic truly wants an empty string |
| Placing `WHEN score >= 5` before `WHEN score >= 8` | The lower threshold always matches high scores first | Order conditions from most specific/strict to most general |
| Labeling `price = null` as “Low price” | Comparisons with null are not true; `ELSE` is selected | Check `price IS NULL` first |
| Checking `r.quantity IS NULL` to conclude no relationship exists | A relationship may exist without that property | Check `r IS NULL` to detect absence of a relationship |
| Expecting `CASE` to reduce row count like `WHERE` | `CASE` only computes a value per row | Use `WHERE` when filtering rows |
| Mixing `STRING` and `INTEGER` across branches of one column | Difficult to map cleanly to strongly typed DTOs/APIs | Standardize types or return two separate columns |
| Using `coalesce(x, 0)` before `CASE` when 0 differs from “unknown” | Conflates missing data with numeric zero | Keep a dedicated `WHEN x IS NULL` branch |
| Persisting derived labels via `SET` without updating them when source data changes | Labels can go stale relative to `stock` or `active` | Compute at query time or synchronize explicitly |
| Returning display labels instead of business codes in APIs | Hard to localize or change UI wording | Return stable codes and translate to labels in the UI layer when appropriate |

## 15. Self-Practice Exercises with Solutions

### Exercise 1. Predict Branch Selection Order

~~~cypher
RETURN
  CASE
    WHEN 10 >= 5 THEN 'Pass'
    WHEN 10 >= 8 THEN 'Excellent'
    ELSE 'Fail'
  END AS result;
~~~

**Solution:** `'Pass'` because the first condition is already true. To return `'Excellent'`, place `10 >= 8` before `10 >= 5`.

### Exercise 2. Compare simple CASE and generic CASE

Requirement: label customers by `tier`, returning `'Missing tier'` when `tier` is absent, and `'Other tier'` for unsupported codes.

~~~cypher
MATCH (c:CaseDemoCustomer)
RETURN
  c.name AS customer,
  CASE
    WHEN c.tier IS NULL THEN 'Missing tier'
    WHEN c.tier = 'GOLD' THEN 'Gold Customer'
    WHEN c.tier = 'SILVER' THEN 'Silver Customer'
    ELSE 'Other tier'
  END AS tierLabel
ORDER BY c.code;
~~~

**Solution:** An → Gold Customer; Binh → Silver Customer; Chi → Missing tier. Generic CASE is appropriate because an `IS NULL` branch must be separated from other tier codes.

### Exercise 3. Stock Classification

Requirement: prioritize “Discontinued” if `active = false`; next “No data” when `stock IS NULL`; “Out of stock” when `stock = 0`; “Low stock” if `stock` is from 1 to 5; otherwise “In stock”.

~~~cypher
MATCH (p:CaseDemoProduct)
RETURN
  p.sku, p.name,
  CASE
    WHEN p.active = false THEN 'Discontinued'
    WHEN p.stock IS NULL THEN 'No data'
    WHEN p.stock = 0 THEN 'Out of stock'
    WHEN p.stock >= 1 AND p.stock <= 5 THEN 'Low stock'
    ELSE 'In stock'
  END AS stockLabel
ORDER BY p.sku;
~~~

**Solution:** `P001` → In stock, `P002` → Low stock, `P003` → Discontinued, `P004` → No data.

### Exercise 4. Count Products by Price Threshold

Requirement: count products with `price >= 500000` and the remaining products in a single query.

~~~cypher
MATCH (p:CaseDemoProduct)
RETURN
  sum(CASE WHEN p.price >= 500000 THEN 1 ELSE 0 END) AS highPrice,
  sum(CASE WHEN p.price < 500000 THEN 1 ELSE 0 END) AS lowerPrice,
  sum(CASE WHEN p.price IS NULL THEN 1 ELSE 0 END) AS missingPrice;
~~~

**Solution:** `highPrice = 1`, `lowerPrice = 3`, `missingPrice = 0`. Adding a missing-price count ensures future reports do not silently drop missing data.

### Exercise 5. Classify Transactions After OPTIONAL MATCH

Requirement: keep all customers, returning “Not purchased” for those without a relationship, “Missing quantity” for relationships without `quantity`, and “Purchased” otherwise.

~~~cypher
MATCH (c:CaseDemoCustomer)
OPTIONAL MATCH (c)-[r:CASE_DEMO_BUYS]->(:CaseDemoProduct)
RETURN
  c.name,
  CASE
    WHEN r IS NULL THEN 'Not purchased'
    WHEN r.quantity IS NULL THEN 'Missing quantity'
    ELSE 'Purchased'
  END AS purchaseLabel
ORDER BY c.code;
~~~

**Solution:** An and Binh → Purchased; Chi → Not purchased. The `r IS NULL` condition precedes `r.quantity IS NULL` to distinguish the two causes clearly.

### Exercise 6. Filter Condition or Classification Expression?

Requirement: the API must return only **products on sale**, while each row includes a `stockStatus` column.

~~~cypher
MATCH (p:CaseDemoProduct)
WHERE p.active = true
RETURN
  p.sku, p.name,
  CASE
    WHEN p.stock IS NULL THEN 'UNKNOWN'
    WHEN p.stock = 0 THEN 'OUT'
    WHEN p.stock <= 3 THEN 'LOW'
    ELSE 'OK'
  END AS stockStatus
ORDER BY p.sku;
~~~

**Solution:** Only `P001`, `P002`, and `P004` remain, with codes `OK`, `LOW`, and `UNKNOWN`, respectively. `WHERE` performs filtering; `CASE` performs classification on the remaining rows.

## 16. Summary and Key Takeaways

- `CASE ... END` is a **value-selection expression** in Cypher. It is useful for turning node and relationship properties into labels, status codes, priority levels, or reporting buckets.
- **Simple CASE** fits mapping a single property against fixed values; **generic CASE** fits range checks, multiple properties, Boolean conditions, or `IS NULL`.
- The **first matching branch** is chosen. Therefore, `WHEN` order must reflect business priority; omitting `ELSE` can yield `null`.
- `null` is not equivalent to `false` or `0`; use `IS NULL` to detect missing values. With `OPTIONAL MATCH`, distinguish a missing relationship from a relationship with a missing property.
- `CASE` works well in `RETURN`, `WITH`, `ORDER BY`, aggregations, and `SET` assignments. When you need to **filter rows**, use `WHERE`.
- Standardize branch return types and consider returning **stable status codes** when data is consumed by the Java Driver, Spring Data Neo4j, or APIs.

The `CASE` expression enables property graph queries not only to find relationships and paths, but also to transform connected data into clear, consistent, and testable business results.
