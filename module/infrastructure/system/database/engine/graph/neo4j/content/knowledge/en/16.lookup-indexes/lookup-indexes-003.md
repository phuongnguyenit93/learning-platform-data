# Range Indexes and Suitable Filtering or Sorting Conditions

In Neo4j, a **property graph** stores data using nodes, relationships, and properties. Cypher can find nodes by label, expand relationships, and filter by properties. When the number of nodes grows large, iterating over every node carrying a label and checking each property can become expensive. A **range index** is a property index that helps the query planner quickly locate matching values and, in certain plans, read results in the existing order of the index.

This lesson belongs to the **Lookup Indexes** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The focus is on choosing **`WHERE`** and **`ORDER BY`** conditions suitable for range indexes, reading `EXPLAIN`/`PROFILE` plans, and avoiding the misconception that merely creating an index guarantees queries will use it. Examples apply to Neo4j 5 using `CREATE RANGE INDEX` syntax; for other versions, check the supported syntax and features.

## 1. Objectives

After completing this lesson, you will be able to:

1. Distinguish **range indexes** from **token lookup indexes**, **text indexes**, and **point indexes** based on query needs.
2. Write Cypher queries with equality, range, string prefix, and property existence predicates that can benefit from a range index.
3. Explain when `ORDER BY` can leverage index order and when an additional sort step is still required.
4. Design single-property or multi-property range indexes for common queries.
5. Use `SHOW INDEXES`, `EXPLAIN`, and `PROFILE` to verify how Neo4j actually executes a query.

## 2. Which Operations Does a Range Index Serve?

A range index organizes **property values** for a node label or relationship type, enabling lookups by exact value or value range. For example, `:Product` nodes with a numeric `price` can be found with `p.price >= 100000 AND p.price < 500000`.

In Neo4j 5, you can create:

~~~cypher
CREATE RANGE INDEX product_price_idx IF NOT EXISTS
FOR (p:Product) ON (p.price);
~~~

This statement creates an index on the `price` property of nodes carrying the `Product` label. It **does not** create missing properties and **does not** convert string values into numbers. Distinguish the related index types:

| Index Type | Suitable Targets and Use Cases | Example |
|---|---|---|
| **Token lookup index** | Find nodes by **label** or relationships by **type**; does not look up property values | `MATCH (p:Product)` |
| **Range index** | Filter properties by equality, value ranges, prefixes; can support ordering | `WHERE p.price >= 100000` |
| **Text index** | Optimize string searches with `CONTAINS`, `ENDS WITH`, and supported string patterns | `WHERE p.name CONTAINS 'book'` |
| **Point index** | Spatial queries with coordinates/points, geographic bounding areas, or distances | `point.distance(...)` |
| **Full-text index** | Word-based text search, language analysis, and relevance scoring | Lookups via full-text procedures |

Do not treat these index types as interchangeable: a token lookup index cannot replace a range index for filtering `price`; likewise, a range index is not a specialized tool for complex keyword searches or geographic radius queries.

### Commonly Suitable Predicate Shapes

| Predicate Shape on a Range-Indexed Property | Cypher Example | Meaning |
|---|---|---|
| Equality to a single value | `p.price = 120000` | Match an exact value |
| Multiple values | `p.category IN ['Books', 'Home']` | Match against a set of values |
| Range comparison | `p.price >= 100000 AND p.price < 500000` | Bounded interval |
| Temporal comparison | `p.createdAt >= date('2026-01-01')` | Records from a date onward |
| String prefix | `p.name STARTS WITH 'Ca'` | Match strings beginning with a prefix |
| Property existence | `p.price IS NOT NULL` | Scan entries that have an indexed value |

These are **shapes that can use** an index, not a promise that Neo4j will always choose the index. The optimizer calculates cost based on data, statistics, estimated row counts, other predicates, and required result ordering.

## 3. Preparing Illustrative Data

On a **practice database**, create a small set of products. The `price` values are **integers representing VND**, and `createdAt` uses the `DATE` type rather than date strings:

~~~cypher
UNWIND [
  {sku: 'B001', name: 'Cypher Handbook', category: 'Books',
   price: 120000, createdAt: date('2026-01-10')},
  {sku: 'B002', name: 'Data Structures', category: 'Books',
   price: 150000, createdAt: date('2026-03-05')},
  {sku: 'B003', name: 'Introduction to Graphs', category: 'Books',
   price: 90000, createdAt: date('2026-02-20')},
  {sku: 'E001', name: 'Computer Mouse', category: 'Electronics',
   price: 350000, createdAt: date('2026-04-12')},
  {sku: 'E002', name: 'Keyboard', category: 'Electronics',
   price: 950000, createdAt: date('2026-05-10')},
  {sku: 'H001', name: 'Reading Lamp', category: 'Home',
   price: 150000, createdAt: date('2026-06-01')}
] AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name,
    p.category = row.category,
    p.price = row.price,
    p.createdAt = row.createdAt;
~~~

In another database, `MERGE` on `sku` could match existing products. Run examples on an isolated database; if strict uniqueness of `sku` is required, design an appropriate **uniqueness constraint** for real data.

Create the indexes supporting the queries in this lesson:

~~~cypher
CREATE RANGE INDEX product_price_idx IF NOT EXISTS
FOR (p:Product) ON (p.price);

CREATE RANGE INDEX product_name_idx IF NOT EXISTS
FOR (p:Product) ON (p.name);

CREATE RANGE INDEX product_created_at_idx IF NOT EXISTS
FOR (p:Product) ON (p.createdAt);
~~~

`IF NOT EXISTS` avoids raising an error when an index or semantically equivalent constraint is already recognized by Neo4j; however, inspect the actual indexes rather than assuming state solely from the creation command output.

Inspect metadata and wait until the newly created indexes reach the `ONLINE` state before using them for performance measurements:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
WHERE type = 'RANGE'
RETURN name, entityType, labelsOrTypes, properties, state
ORDER BY name;
~~~

A new index may show `POPULATING` while Neo4j builds its entries. If it fails, you may see `FAILED`; in that case, inspect the error details and operational configuration before expecting queries to leverage the index.

## 4. Writing Filter Predicates Likely to Leverage a Range Index

### 4.1. Equality and Numeric Ranges

~~~cypher
// Filter products from 100,000 up to (excluding) 500,000 VND.
MATCH (p:Product)
WHERE p.price >= 100000 AND p.price < 500000
RETURN p.sku AS sku, p.name AS product, p.price AS price
ORDER BY p.price ASC;
~~~

With the sample data, the matching products are `B001` (120,000), `B002` (150,000), `H001` (150,000), and `E001` (350,000). The two products sharing the price 150,000 may swap order when sorting solely by `price`.

The predicate above compares `p.price` directly using comparison operators and numeric constants of the same type, making it favorable for the planner to build a range seek. To supply input values from an application, use **Cypher parameters**:

~~~cypher
MATCH (p:Product)
WHERE p.price >= $minPrice AND p.price < $maxPrice
RETURN p.sku AS sku, p.name AS product, p.price AS price
ORDER BY p.price ASC
LIMIT 20;
~~~

For example, a Java Driver or Spring Data Neo4j application can pass numeric `minPrice = 100000` and `maxPrice = 500000`. Parameterization enables query plan reuse and avoids concatenating input values directly into Cypher strings. Index usage still depends on actual conditions and the chosen plan.

### 4.2. Filtering Time Ranges

~~~cypher
MATCH (p:Product)
WHERE p.createdAt >= date('2026-03-01')
  AND p.createdAt < date('2026-06-01')
RETURN p.sku AS sku, p.createdAt AS createdAt
ORDER BY p.createdAt;
~~~

The predicate uses `DATE` values matching the type of `p.createdAt`. With the sample data, the matching SKUs are `B002`, `E001`, and `E002`; `H001` has date 2026-06-01 and therefore is **not** included in the half-open upper bound. Writing intervals as `[start, end)` is very useful for date/time filtering and time-based pagination.

### 4.3. String Prefix Filtering

~~~cypher
MATCH (p:Product)
WHERE p.name STARTS WITH 'C'
RETURN p.sku AS sku, p.name AS product
ORDER BY p.name;
~~~

If a range index exists on `p.name`, a **prefix** search is a suitable case to evaluate index usage. `STARTS WITH` is case-sensitive under Cypher's matching semantics; `'C'` and `'c'` are not treated as the same prefix by default.

Conversely, `CONTAINS`, `ENDS WITH`, or natural-language search have different characteristics. Evaluate a **text index** or **full-text index** based on the search pattern; do not assume a range index on `name` is the best choice for every string query.

### 4.4. Property Existence

~~~cypher
MATCH (p:Product)
WHERE p.price IS NOT NULL
RETURN p.sku AS sku, p.price AS price
ORDER BY p.price ASC
LIMIT 10;
~~~

`IS NOT NULL` expresses that only products actually having a `price` should be retrieved. Because a range index stores existing property values, Neo4j can use an **ordered index scan** when appropriate. Conversely, `WHERE p.price IS NULL` looks for nodes **missing the property or holding null**, so those nodes cannot be located directly via entries of the `price` index alone.

## 5. Range Indexes and `ORDER BY`: When Can `Sort` Be Avoided?

A range index is ordered by the indexed values. When a sort requirement **matches an order that can be read directly from the index**, Neo4j can sometimes return already-ordered rows from the index operator and omit a separate `Sort` step.

~~~cypher
EXPLAIN
MATCH (p:Product)
WHERE p.price >= 100000
RETURN p.sku AS sku, p.price AS price
ORDER BY p.price ASC
LIMIT 20;
~~~

If the plan uses the range index and preserves the `p.price ASC` ordering through subsequent operators, the sort step may be eliminated. The planner may also choose a different strategy due to estimated costs; only **inspecting the actual plan** can confirm this.

Common scenarios to consider:

| Query | Ability to Leverage Index Order |
|---|---|
| `WHERE p.price >= 100000 ORDER BY p.price` | Potentially a very good match for a range index on `price` |
| `WHERE p.price IS NOT NULL ORDER BY p.price DESC` | Can read the index in the appropriate direction |
| `ORDER BY p.price` without **filtering out nodes missing a price** | Cannot read solely from index entries if nodes without `price` must also be returned |
| `ORDER BY toString(p.price)` | String expression order differs from numeric order; does not automatically use numeric index order |
| `ORDER BY p.price, p.sku` with an index only on `price` | The index only guarantees order by `price`; additional sorting on `sku` may still be needed |
| `ORDER BY p.category, p.price` with an index only on `price` | Does not match the index key order; `Sort` may be required |

**Tied values issue:** when two nodes share the same `price`, `ORDER BY p.price` leaves their relative order unspecified. For deterministic pagination, you can add a unique identifier to the sort:

~~~cypher
MATCH (p:Product)
WHERE p.price IS NOT NULL
RETURN p.sku AS sku, p.price AS price
ORDER BY price ASC, sku ASC
LIMIT 20;
~~~

This query provides a deterministic result order **if `sku` is unique**. It may also require an additional sort step. Never sacrifice pagination correctness on the assumption that `LIMIT` with an index will always produce a stable tie-breaking order.

## 6. Multi-Property Range Indexes (Composite Range Indexes)

Suppose a business query routinely filters on an **exact category**, then filters by a **price range**, and sorts by price:

~~~cypher
MATCH (p:Product)
WHERE p.category = 'Books'
  AND p.price >= 100000
RETURN p.sku AS sku, p.price AS price
ORDER BY p.price ASC
LIMIT 20;
~~~

A composite range index can be more suitable than two single-property indexes:

~~~cypher
CREATE RANGE INDEX product_category_price_idx IF NOT EXISTS
FOR (p:Product) ON (p.category, p.price);
~~~

**Property order in the index matters.** With the key `(category, price)`, entries are organized by `category` first and then by `price` within each category group. The predicate `p.category = 'Books'` narrows down to a single category group, after which the range predicate can exploit the `price` ordering within that group. This also creates an opportunity to avoid `Sort` when using `ORDER BY p.price`.

### Choosing Property Order Based on Query Patterns

| Query Pattern | Suitability of `(category, price)` |
|---|---|
| `category = 'Books' AND price >= 100000` | Strong candidate: equality on the leading key, range on the trailing key |
| `category = 'Books' ORDER BY price` | Can leverage price ordering within the same category |
| `price >= 100000`, with no category predicate | Do not expect price lookups to be as efficient as a single-property `(price)` index |
| `category STARTS WITH 'B' AND price >= 100000` | Leading key is already a range; ability to leverage the trailing key is more limited than with exact equality |
| `category = 'Books' AND price = 150000` | Two equality predicates are a suitable pattern |

Practical guideline: when designing a composite index, place properties filtered by **exact equality** first, followed by properties filtered by **range** or used for sorting. Neo4j applies version- and statistics-specific optimizations, so treat this guideline as a starting point to verify with `PROFILE`.

Do not create every permutation of properties just to "cover all queries." Each index incurs storage overhead and build/maintenance costs whenever nodes are modified.

## 7. Range Indexes for Relationship Properties

Range indexes do not apply only to nodes. When business logic records purchase timestamps on `:PURCHASED` relationships, you can index that relationship property:

~~~cypher
CREATE RANGE INDEX purchased_at_idx IF NOT EXISTS
FOR ()-[r:PURCHASED]-() ON (r.purchasedAt);
~~~

Corresponding query:

~~~cypher
MATCH ()-[r:PURCHASED]->()
WHERE r.purchasedAt >= datetime('2026-01-01T00:00:00Z')
  AND r.purchasedAt < datetime('2027-01-01T00:00:00Z')
RETURN r.purchasedAt AS purchasedAt
ORDER BY purchasedAt DESC
LIMIT 30;
~~~

This condition works properly **if `purchasedAt` is actually stored as `DATETIME`**. If the relationship uses `DATE`, use `date(...)` to match the type. When the query also constrains endpoint nodes, the optimizer might find expanding from a pre-selected node cheaper than scanning the relationship index; measure against the actual query.

## 8. Patterns That Reduce Index Usability

### 8.1. Using the Wrong Property Data Type

If `p.price` is stored as strings like `'90000'` and `'120000'`, comparisons and sorting follow **lexicographical (string)** order rather than numeric order. For example, lexicographical order places `'120000'` before `'90000'`. Do not create a range index to patch wrongly typed data: normalize prices to **INTEGER** or an appropriate numeric type in the data model.

The same applies to dates and times: a `date('2026-03-05')` value differs from the string `'2026-03-05'`. Using Neo4j temporal types ensures date/time comparisons behave semantically.

### 8.2. Wrapping Properties in Transformations Inside `WHERE`

~~~cypher
// May make it difficult to use the range index on p.price directly:
MATCH (p:Product)
WHERE toInteger(p.price) >= 100000
RETURN p.sku, p.price;
~~~

The index stores `p.price`, not the computed result of `toInteger(p.price)`. If `price` is already numeric, write the predicate as:

~~~cypher
MATCH (p:Product)
WHERE p.price >= 100000
RETURN p.sku, p.price;
~~~

Similarly, `toLower(p.name) STARTS WITH 'c'` and `coalesce(p.price, 0) >= 100000` apply transformations to the indexed property. Depending on the plan and version, the optimizer will not necessarily translate them into a direct index seek. Normalize data or design dedicated properties for case-insensitive query requirements.

### 8.3. Index Not Matching the Label, Relationship Type, or Property

~~~cypher
CREATE RANGE INDEX product_price_idx IF NOT EXISTS
FOR (p:Product) ON (p.price);
~~~

This index is bound to `:Product(price)`. It does not directly serve patterns like `(o:Order) WHERE o.price > 0` or `(p:Product) WHERE p.cost > 0` because the label or property differs. Appropriate indexes must be chosen from **actual query patterns**, not merely by similarly named fields.

### 8.4. Low-Selectivity Filters

A predicate like `p.price > 0` may match almost every product. If Neo4j estimates a very large row count, using an index is not necessarily cheaper than an alternative scan. Likewise, an index on a property with only a few heavily repeated values may offer little benefit for queries that fail to narrow the result set.

### 8.5. `OR` and Multiple Filter Paths

~~~cypher
MATCH (p:Product)
WHERE p.price >= 500000 OR p.category = 'Books'
RETURN p.sku AS sku, p.price AS price;
~~~

The two branches of `OR` reference **two different properties**. Depending on version and cost, the optimizer may need to combine multiple access paths or perform additional filtering; you cannot assume index usage solely because a `price` index exists. When such a query is critical, inspect `EXPLAIN`/`PROFILE` before considering rewriting it into separate branches and deduplicating by identifier.

## 9. Verifying with `EXPLAIN` and `PROFILE`

Never guess whether an index is used based only on execution time over a few test nodes. Verification steps:

1. Run `SHOW INDEXES` to confirm the index has the **exact label/type, properties**, and `ONLINE` state.
2. Use `EXPLAIN` to inspect the **planned execution strategy** without running the query.
3. Use `PROFILE` on **read queries** over test/representative data to inspect row counts (`Rows`), data access counts (`DB Hits`), estimates, and execution costs.
4. Check for an appropriate index access operator; check whether `Sort` appears when ordering is requested and whether excessive intermediate rows are produced unnecessarily.
5. Compare on a sufficiently large dataset with identical parameters and index states; avoid claiming an optimization works solely because a 6-row sample query runs fast.

Example:

~~~cypher
EXPLAIN
MATCH (p:Product)
WHERE p.category = 'Books' AND p.price >= 100000
RETURN p.sku AS sku, p.price AS price
ORDER BY price ASC
LIMIT 10;
~~~

~~~cypher
PROFILE
MATCH (p:Product)
WHERE p.category = 'Books' AND p.price >= 100000
RETURN p.sku AS sku, p.price AS price
ORDER BY price ASC
LIMIT 10;
~~~

Depending on the Neo4j version, the plan may display operators such as `NodeIndexSeek`, `NodeIndexScan`, `Filter`, `Sort`, `Top`, `Projection`, or others. **Operator names and plan shapes can vary**, so read the details about the selected index, filtered properties, and actual row counts instead of looking for a single fixed operator name string.

Even a query with `LIMIT` is not guaranteed to exploit ordered index reads: if the plan must evaluate an expression or sort by a key not matching the index order, Neo4j may still need a `Top`/`Sort` step before returning N rows.

### Should You Force an Index with `USING INDEX`?

Neo4j supports **index hints** in Cypher, for example:

~~~cypher
MATCH (p:Product)
USING INDEX p:Product(price)
WHERE p.price >= $minPrice
RETURN p.sku AS sku, p.price AS price;
~~~

A hint is an investigative or tuning tool when there is concrete evidence that the automatic choice is suboptimal—**not a mandatory step** after creating an index. It can prevent the optimizer from choosing a better plan when data distributions or queries change. In production workloads, benchmark both hinted and unhinted versions before deciding to keep a hint.

## 10. Designing and Operating Range Indexes Wisely

Indexes are auxiliary structures that must be maintained. Adding indexes can speed up reads while increasing storage requirements and overhead on inserts, updates, and deletes. For systems using the Java Driver or Spring Data Neo4j, evaluate performance using the exact parameterized Cypher statements executed by the application.

Helpful principles:

- **Start from query patterns:** labels/types, properties in `WHERE`, `ORDER BY` ordering, expected row counts, and `LIMIT`.
- **Use proper data types:** numeric for prices, temporal for dates/times, point for coordinates. Avoid fixing types with repeated read-time expressions when you can normalize at write time.
- **Order composite indexes deliberately:** equality predicates before range predicates; check behavior when queries omit the leading key.
- **Account for uniqueness:** if `sku` must be unique, an appropriate **uniqueness constraint** enforces data integrity and creates the corresponding backing index. Avoid creating redundant indexes without checking existing schema.
- **Monitor index state:** indexes must be `ONLINE` to serve queries; resolve creation/population failures before benchmarking.
- **Check both sorting and pagination:** an index on price alone does not guarantee deterministic tie-breaking when multiple products share the same price; add a secondary sort key if needed.
- **Only create indexes with measurable benefit:** prioritize frequent or costly queries; review and prune unused indexes.

### Quick Decision Flow

~~~mermaid
flowchart TD
    A["Identify MATCH pattern and WHERE / ORDER BY"] --> B{"What kind of property filter?"}
    B -->|"Equality, range, STARTS WITH"| C["Evaluate RANGE index"]
    B -->|"CONTAINS / ENDS WITH"| D["Evaluate TEXT index"]
    B -->|"Distance / spatial region"| E["Evaluate POINT index"]
    B -->|"Label / relationship type only"| F["Evaluate token lookup index"]
    C --> G{"Multiple filter properties?"}
    G -->|"Yes"| H["Try composite index matching predicate order"]
    G -->|"No"| I["Try single-property index"]
    H --> J["SHOW INDEXES, EXPLAIN, PROFILE"]
    I --> J
    D --> J
    E --> J
    F --> J
    J --> K["Compare Rows, DB Hits, Sort, and runtime on representative data"]
~~~

## 11. Practice Exercises

### Exercise 1 — Choosing an Index

A system has `:Book` nodes with `genre`, `publishedAt` (`DATE`), and numeric `rating` properties. A frequent query is:

~~~cypher
MATCH (b:Book)
WHERE b.genre = $genre
  AND b.publishedAt >= $fromDate
RETURN b.title, b.publishedAt
ORDER BY b.publishedAt DESC
LIMIT 30;
~~~

Propose an index, explain the property order, and describe how to verify its effectiveness.

**Suggested solution:**

~~~cypher
CREATE RANGE INDEX book_genre_published_at_idx IF NOT EXISTS
FOR (b:Book) ON (b.genre, b.publishedAt);
~~~

`genre` is filtered with exact equality; `publishedAt` is both the range predicate and the sort key within the `genre` group. Verify index status with `SHOW INDEXES`, then run `EXPLAIN`/`PROFILE` using realistic parameters. If queries mainly filter by date without `genre`, consider another appropriate index.

### Exercise 2 — Predicting Results and Ordering

Given the product dataset in Section 3, consider the query:

~~~cypher
MATCH (p:Product)
WHERE p.price >= 120000 AND p.price < 350000
RETURN p.sku AS sku, p.price AS price
ORDER BY p.price ASC;
~~~

**Answer:** `B001` (120,000), `B002` (150,000), and `H001` (150,000). The two 150,000 products have no guaranteed relative order. `E001` (350,000) is excluded because the upper bound is `< 350000`.

### Exercise 3 — Fixing an Index-Unfriendly Query

Suppose `:Order.totalAmount` is already stored as a number. What is the issue with the query below if a range index already exists on `totalAmount`?

~~~cypher
MATCH (o:Order)
WHERE toInteger(o.totalAmount) > 500000
RETURN o;
~~~

**Suggested solution:** The expression `toInteger(o.totalAmount)` applies a transformation to the property. Since the property is already numeric, write `WHERE o.totalAmount > 500000` so the optimizer can consider using the range index directly. Verify with `EXPLAIN`/`PROFILE`; never infer solely from syntax that an index will be chosen in every case.

### Exercise 4 — Checking Sort Behavior

Suppose an index `(category, price)` exists. A query filters `category = 'Books'` and runs `ORDER BY price`. Inspect the plan to determine whether `Sort` is present; then change it to `ORDER BY price, sku` and compare plans. Explain why `sku` is required if users need deterministic pagination when multiple products share the same price.

## 12. Summary

- **Range indexes** are the standard choice for equality, range, string prefix, and property existence lookups on nodes or relationships.
- **`ORDER BY` can benefit from index order**, especially when `WHERE` predicates and index key order align; however, there is no absolute guarantee every plan will eliminate `Sort`.
- **Composite range indexes require the right property order**: the common pattern places exact-equality keys first and range/sort keys afterward.
- **Data types and query expressions matter**: storing numbers as strings or wrapping properties in functions can distort ordering or reduce index seek eligibility.
- **Verify, don't guess**: use `SHOW INDEXES`, `EXPLAIN`, and `PROFILE` on representative queries and data, while balancing index write overhead.
