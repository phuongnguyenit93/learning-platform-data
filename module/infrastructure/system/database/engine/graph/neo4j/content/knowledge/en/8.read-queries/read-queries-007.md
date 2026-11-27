# ORDER BY, SKIP, and LIMIT for Sorting and Pagination

## 1. Why Sort Before Paginating?

In Neo4j, Cypher queries typically return multiple **result rows** after `MATCH` finds nodes, relationships, or paths matching a pattern. When building screens for lists of posts, users, transactions, or related nodes, applications commonly need to:

- **Sort** by timestamp, score, name, or multiple criteria.
- **Paginate** to fetch only a right-sized slice of results each time.
- **Ensure deterministic ordering** to avoid skipping or duplicating records when users navigate between pages.

Cypher provides three core clauses:

| Clause | Function | Example |
| --- | --- | --- |
| `ORDER BY` | Sorts result rows by one or more expressions | `ORDER BY createdAt DESC, postId ASC` |
| `SKIP` | Skips the first N rows of the result set at that point | `SKIP 20` |
| `LIMIT` | Limits the number of rows returned or passed to the next stage | `LIMIT 10` |

For a typical paginated list, the clause order is:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP 20
LIMIT 10;
```

The query sorts newest to oldest, uses `postId` to break ties among posts with the same timestamp, skips the first 20 rows, and returns at most the next 10 rows. **Without `ORDER BY`, Neo4j makes no guarantee on return order**, even if a small query occasionally happens to produce the same order across runs.

> **Lesson scope:** Examples use Neo4j's property graph model and Cypher syntax common in Neo4j 5. Exercises focus on read queries; nodes, relationships, indexes, constraints, the Java Driver, and Spring Data Neo4j are covered where they directly affect sorting or pagination.

## 2. Preparing a Re-Runnable Sample Dataset

Suppose an application has `:Post` nodes with properties `id`, `title`, `category`, and `createdAt`. Each post has a unique code; two posts can be created at the exact same timestamp.

Run the following in a **practice database**:

```cypher
CREATE CONSTRAINT post_id_unique IF NOT EXISTS
FOR (p:Post) REQUIRE p.id IS UNIQUE;

UNWIND [
  {id: 'P101', title: 'Khởi đầu với Neo4j', category: 'Graph', createdAt: '2026-11-10T10:00:00Z'},
  {id: 'P102', title: 'Node và relationship', category: 'Graph', createdAt: '2026-11-09T09:00:00Z'},
  {id: 'P103', title: 'Đọc dữ liệu bằng Cypher', category: 'Graph', createdAt: '2026-11-09T09:00:00Z'},
  {id: 'P104', title: 'Tối ưu truy vấn', category: 'Graph', createdAt: '2026-11-08T13:00:00Z'},
  {id: 'P105', title: 'Java Driver', category: 'Java', createdAt: '2026-11-08T12:00:00Z'},
  {id: 'P106', title: 'Spring Data Neo4j', category: 'Java', createdAt: '2026-11-07T09:00:00Z'},
  {id: 'P107', title: 'Index và constraint', category: 'Graph', createdAt: '2026-11-06T10:00:00Z'},
  {id: 'P108', title: 'Vận hành Neo4j', category: 'Ops', createdAt: '2026-11-05T11:00:00Z'}
] AS item
MERGE (p:Post {id: item.id})
SET p.title = item.title,
    p.category = item.category,
    p.createdAt = datetime(item.createdAt);
```

`MERGE` uses `id` to avoid duplicating nodes when re-running the sample setup; `SET` updates the post's properties. `datetime()` parses ISO 8601 strings into temporal values so sorting reflects chronological order. **Do not store dates as arbitrarily formatted strings** if queries need accurate temporal comparisons.

To verify the data:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC;
```

With just the eight sample nodes above and no other `:Post` nodes, the order is `P101, P102, P103, P104, P105, P106, P107, P108`. Both `P102` and `P103` share the same `createdAt`; the post ID determines their relative order.

## 3. ORDER BY: Sorting by One or More Criteria

### 3.1. ASC and DESC

`ASC` is ascending and is the default direction; `DESC` is descending.

```cypher
// Newest first.
MATCH (p:Post)
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC;
```

```cypher
// Post ID ascending; write ASC explicitly for readability.
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title
ORDER BY postId ASC;
```

Criteria are applied **from left to right**: only when two rows tie on the first criterion does the next criterion decide their order. This is crucial when designing stable pagination.

### 3.2. A Tie-Breaker Is Needed When Values Repeat

Look at the following query:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC
LIMIT 2;
```

`P101` is guaranteed to precede the remaining posts in the sample set, but `P102` and `P103` share the exact same timestamp. There is no guarantee Neo4j will always pick the same one as the second row when sorting solely by `createdAt`. If a page boundary falls between tied values, you can encounter duplicate or missing records even when data has not changed because the order within tied rows is undefined.

Add a unique tie-breaker key:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 2;
```

Now the result on the sample set is `P101`, `P102`; the next row will be `P103`. The `id` property is enforced as unique by a constraint, making it suitable for deterministic ordering. In real data, use a **unique and immutable** key appropriate for the domain.

**Note:** Total ordering fixes the order of data at a single point in time. It does not prevent rows from shifting across pages when new posts are inserted, records are deleted, or sort values change; that issue is addressed separately in the cursor pagination section.

### 3.3. Sorting Aggregated Results

`ORDER BY` can also sort results of `count()`, `sum()`, or computed expressions, not only direct node properties.

```cypher
MATCH (p:Post)
RETURN p.category AS category, count(*) AS totalPosts
ORDER BY totalPosts DESC, category ASC;
```

In the sample set, `Graph` has 5 posts, `Java` has 2 posts, and `Ops` has 1 post. When paginating **after aggregation**, each row represents a category group; `SKIP` and `LIMIT` then apply to the number of **groups**, not the original post count.

### 3.4. Missing Values and Mixed Data Types

If some posts lack `createdAt`, define a clear business policy: exclude them from the list, place them last, or use a fallback timestamp. For example, selecting only posts with a creation timestamp:

```cypher
MATCH (p:Post)
WHERE p.createdAt IS NOT NULL
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC;
```

Do not rely on the incidental placement of `null` values in a query where business rules are unspecified. Avoid mixing strings, numbers, and temporal values in the same sorted property: ordering across heterogeneous types may follow Cypher rules yet make no sense to users. For Vietnamese titles, test string comparison and case sensitivity against product requirements; standard `ORDER BY` is not a substitute for dedicated natural-language collation rules.

## 4. SKIP and LIMIT: Offset Pagination

### 4.1. How It Works

`SKIP n` skips the first `n` rows of the sorted set; `LIMIT m` keeps at most the next `m` rows. When `SKIP` follows `ORDER BY`, the application can fetch pages 1, 2, 3 with a fixed page size.

If users select 1-based page numbers:

```text
offset = (pageNumber - 1) * pageSize
```

Example with `pageSize = 3` across the eight sample posts:

| Page | `SKIP` | `LIMIT` | Returned Post IDs |
| ---: | ---: | ---: | --- |
| 1 | 0 | 3 | P101, P102, P103 |
| 2 | 3 | 3 | P104, P105, P106 |
| 3 | 6 | 3 | P107, P108 |
| 4 | 9 | 3 | No rows |

Query for page 2:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP 3
LIMIT 3;
```

Without `SKIP`, `LIMIT 3` takes the first three rows of the sort order. Without `LIMIT`, `SKIP 3` returns all remaining rows. `LIMIT 0` produces an empty result; values for `SKIP` and `LIMIT` must be valid non-negative integers.

### 4.2. Using Parameters Instead of Query String Concatenation

When users change page numbers or page sizes, pass `offset` and `pageSize` via Cypher parameters:

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

For example, the backend passes `{offset: 3, pageSize: 3}` for page 2. On the application side, validate `pageNumber >= 1`, `pageSize >= 1`, cap `pageSize` with an upper bound, and guard multiplication when computing `offset` to avoid overflow or excessively deep page requests. Never concatenate input directly into Cypher strings.

With filters, keep the exact same condition across all pages:

```cypher
MATCH (p:Post)
WHERE p.category = $category
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

If `category = 'Graph'`, only the five posts in the `Graph` category participate in sorting and pagination. Keep both the **filter predicate and the sort order** identical across page fetches.

### 4.3. Counting Total Rows to Display Page Count

`LIMIT` does not automatically return the total number of rows matching the filter. If the UI needs to show "5 results / 2 pages", run a companion count query:

```cypher
MATCH (p:Post)
WHERE p.category = $category
RETURN count(*) AS total;
```

The count query must use the **same filter** as the page query. With `total = 5` and `pageSize = 3`, the page count is `ceil(5 / 3) = 2` on the application side. Two separate queries can observe two different database states if writes/deletes happen in between; never assume total count and page data always reflect the exact same snapshot.

In UIs that only need a "Load more" button, you can fetch `pageSize + 1` rows, display `pageSize` rows, and use the extra row to determine whether a next page exists. That avoids a `count(*)` query in many situations, though it still does not prevent data drift across requests.

## 5. Clause Order Changes Query Meaning

In Cypher, `WITH` creates an intermediate boundary for rows; `ORDER BY`, `SKIP`, and `LIMIT` apply at their position in the query pipeline. The two queries below have different meanings.

**Get the three newest posts:**

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 3;
```

**Pick any three arbitrary posts first, then sort just those three:**

```cypher
MATCH (p:Post)
WITH p
LIMIT 3
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC;
```

In the second query, the earlier `LIMIT` shrinks the row set while **no order is defined**. The later `ORDER BY` cannot turn those three arbitrarily chosen rows into the three newest posts of the entire dataset. This is a very common bug when splitting queries across multiple `WITH` clauses.

`WITH ... ORDER BY` is also useful when preparing order for the next stage. For instance, `ORDER BY` inside `WITH` ensures rows are passed to the next clause in a deterministic order; this is especially important when the next clause uses an order-sensitive aggregation like `collect()`.

### LIMIT Counts Result Rows, Not Distinct Nodes

If a query expands across multiple relationships, a node can appear in multiple rows:

```cypher
MATCH (u:User {id: $userId})-[:FOLLOWS]->(a:Author)-[:WROTE]->(p:Post)
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 10;
```

If a post is reached via multiple paths or multiple `:Author` nodes, the result can contain multiple rows with the same `postId`. When the requirement is **10 distinct posts**, deduplicate before sorting and paginating:

```cypher
MATCH (u:User {id: $userId})-[:FOLLOWS]->(a:Author)-[:WROTE]->(p:Post)
WITH DISTINCT p
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 10;
```

Using `DISTINCT` can increase execution cost; use it only when the pattern can genuinely produce multiple rows for the same entity and deduplication is required.

## 6. Drawbacks of OFFSET on Large or Rapidly Changing Data

### 6.1. Deep Pages Can Be Expensive

With `SKIP 100000 LIMIT 20`, the database still has to locate and skip all preceding rows according to the chosen query plan. `LIMIT 20` **does not mean the entire query only processes 20 rows**. When many candidate rows must be sorted, sorting can consume significant memory and time.

The actual impact depends on indexes, filter predicates, execution plans, and data distribution. Before concluding a query is slow because of `SKIP`, inspect the plan with `EXPLAIN` and real cost with `PROFILE` in a test environment.

### 6.2. New Records Can Shift Pages

Suppose `pageSize = 3` and page 1 returns `P101, P102, P103`. Immediately afterward, a new post `P109` with a newer `createdAt` than all existing posts is added. Page 2 with `SKIP 3` now starts at `P103`, causing **`P103` to repeat** even though each individual query has a full `ORDER BY`.

Similarly, when a record on an earlier page is deleted or its sort key changes, subsequent pages can skip data. Sorting by a unique key stabilizes ordering **within a single data state**, not across separate requests.

When lists change infrequently and users need to jump directly to any page number, offset pagination remains convenient. For continuously growing feeds, heavy traffic, or "Load more" navigation, consider cursor-based pagination.

## 7. Cursor Pagination (Keyset Pagination)

Instead of saying "skip 1,000 rows", the application passes the key of the **last seen row** and asks for rows that come after that key in the same sort order.

Suppose the sort order is defined as:

```cypher
ORDER BY createdAt DESC, postId ASC
```

That means timestamp descending; if timestamps match, post ID ascending. Thus, a post comes **after** the cursor row when:

1. Its `createdAt` is **less than** the cursor's timestamp; or
2. Its `createdAt` **equals** the cursor's timestamp and its `postId` is **greater than** the cursor's ID.

### 7.1. First Page

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $pageSize;
```

With `$pageSize = 2`, the result is `P101, P102`. The application stores the key of the **last row**: `(createdAt = 2026-11-09T09:00:00Z, postId = 'P102')`.

### 7.2. Next Page

```cypher
MATCH (p:Post)
WHERE p.createdAt < datetime($cursorCreatedAt)
   OR (p.createdAt = datetime($cursorCreatedAt) AND p.id > $cursorPostId)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $pageSize;
```

Example parameters:

```json
{
  "cursorCreatedAt": "2026-11-09T09:00:00Z",
  "cursorPostId": "P102",
  "pageSize": 2
}
```

The next page returns `P103, P104`. `P103` still appears because it shares the same timestamp as `P102` but has a larger ID. Using only `p.createdAt < $cursorCreatedAt` would **miss `P103`**.

Points to remember:

- The cursor must include **all fields that define the sort order**; when multiple posts share the same creation date, date alone is insufficient.
- When filters or sort order change, an old cursor may no longer apply. APIs should treat cursors as bound to a specific query configuration.
- For posts missing `createdAt`, establish a clear policy before applying the comparison above; the sample query assumes this property is always present and of type `datetime`.
- New records inserted **ahead of** the cursor generally do not shift subsequent pages as in offset pagination. However, if a sort property of an existing record is modified, or records are deleted/updated, keyset pagination still does not guarantee an immutable snapshot.
- Keyset pagination fits "Load more" navigation well; jumping straight to page 50 is less convenient than `SKIP`.

### 7.3. Choosing Between the Two Approaches

| Criterion | Offset (`SKIP`) | Keyset (Cursor) |
| --- | --- | --- |
| Jumping to an arbitrary page number | Easy | Requires extra state or mechanism |
| Initial query | Simple | Requires comparison predicates on sort keys |
| Very deep pages | May have to skip many rows | Does not skip all rows before the cursor |
| New data inserted at top of list | Prone to duplicates or skips across pages | Usually more stable if sort keys do not change |
| Prerequisites | Consistent `ORDER BY` | Consistent `ORDER BY`, unique tie-breaker, matching cursor |
| Typical use cases | Admin tables needing page numbers | News feeds, transaction logs, "Load more" |

## 8. Optimizing Queries with ORDER BY, SKIP, LIMIT

### 8.1. Filter Before Sorting Large Sets

When only `Graph` posts are needed, place the filter before `RETURN`:

```cypher
MATCH (p:Post)
WHERE p.category = 'Graph'
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 10;
```

Filtering early reduces the candidate set to sort, depending on the execution plan. Return only needed properties and avoid expanding relationships that are not used by the screen being loaded.

### 8.2. Exploring Appropriate Indexes

The uniqueness constraint on `:Post(id)` created in setup protects data integrity and supports lookups by `id`. For queries that frequently search or sort by timestamp, evaluate a range index:

```cypher
CREATE RANGE INDEX post_created_at IF NOT EXISTS
FOR (p:Post) ON (p.createdAt);
```

If the system frequently filters by `category` and sorts by timestamp, a composite index may be worth testing:

```cypher
CREATE RANGE INDEX post_category_created_at IF NOT EXISTS
FOR (p:Post) ON (p.category, p.createdAt);
```

**Do not assume** that simply having an index guarantees Neo4j will eliminate the sort step. Index eligibility depends on filter predicates, how `ORDER BY` is written, sort directions, property order, Neo4j version, and the query optimizer. In the example, the secondary criterion `postId ASC` also needs to be satisfied, so inspect the actual plan.

### 8.3. EXPLAIN and PROFILE

```cypher
EXPLAIN
MATCH (p:Post)
WHERE p.category = $category
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

`EXPLAIN` shows the estimated plan without executing the query. When you need to measure in an appropriate environment:

```cypher
PROFILE
MATCH (p:Post)
WHERE p.category = $category
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

Inspect input/output row counts, DB hits, any relationship expansion steps, and operators like `Sort`, `Top`, `Skip`, or index-backed operators. Operator names and selection vary across versions. Compare latency across multiple `offset` values, page sizes, and data distributions before drawing optimization conclusions.

A query with `LIMIT 20` can still be resource-intensive if it must materialize millions of intermediate rows from path matches or sort a huge set before taking 20 rows. **Limiting returned rows is not a hard cap on total query work.**

## 9. Integrating Pagination with Java Driver and Spring Data Neo4j

With the **Neo4j Java Driver**, pass pagination values via parameters to keep queries clean and reusable. The Java example below assumes the application has initialized `Driver driver`:

```java
int pageNumber = 2; // 1-based page number.
int pageSize = 3;

if (pageNumber < 1 || pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException("Invalid pagination request");
}

long offset = Math.multiplyExact((long) pageNumber - 1L, (long) pageSize);

String cypher = """
    MATCH (p:Post)
    RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
    ORDER BY createdAt DESC, postId ASC
    SKIP $offset
    LIMIT $pageSize
    """;

var result = driver.executableQuery(cypher)
    .withParameters(java.util.Map.of("offset", offset, "pageSize", pageSize))
    .execute();

for (var record : result.records()) {
    System.out.println(record.get("postId").asString());
}
```

The example uses the `executableQuery` API of Java Driver 5.x and Java text blocks. Real applications must manage `Driver` lifecycle, connection configuration, error handling, and appropriate access control.

With **Spring Data Neo4j**, you can use `Pageable`/`Sort` when supported by repository methods and actual mappings, or write explicit `@Query` queries when custom relationship traversal and ordering are needed. Never assume a custom Cypher query has the exact same pagination/counting behavior as an auto-generated repository query; verify how SDN handles `Pageable`, count queries, and node deduplication after mapping. In particular, test against data with multiple relationships to avoid discrepancies between Cypher row counts and expected entity counts.

For cursor pagination APIs, the backend can return `items` and `nextCursor` (derived from the last row's keys) instead of `pageNumber`. If the cursor is exposed to clients, encode/validate the cursor and bind it to the request's filter, sort direction, and access permissions.

## 10. Common Mistakes and Fixes

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Same query returns rows in changing order | Missing `ORDER BY` | Define explicit ordering on displayed results |
| Rows repeat across pages even with static data | Sorted by a non-unique property | Add a unique tie-breaker key like `postId` |
| New posts cause next page to repeat old posts | Offset shifts when dataset changes | Consider keyset pagination or an appropriate snapshot |
| "Top 10" query returns wrong items | Applied `LIMIT` before `ORDER BY` | Sort the full candidate set before limiting |
| Expected 10 nodes, got only 6 distinct nodes | One node matched multiple paths, yielding multiple rows | Use `WITH DISTINCT p` before paginating if appropriate |
| Later pages are very slow | Very large `SKIP`, sorting many rows, or wide graph traversal | Filter early, check `PROFILE`, consider cursor and indexes |
| Total page count mismatches displayed entities | Count query uses different filter or multiple rows per node | Align conditions; consider `count(DISTINCT p)` per business intent |
| Date sorting is incorrect | Property stored with wrong or mixed types | Normalize to a consistent temporal type |

## 11. Practice Exercises

### Exercise 1: Newest to Oldest

Write a query to retrieve the four newest posts in the `Graph` category, returning `postId`, `title`, and `createdAt`. If two posts share the same timestamp, the one with the smaller `postId` comes first.

<details>
<summary>Suggested Solution</summary>

```cypher
MATCH (p:Post)
WHERE p.category = 'Graph'
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 4;
```

With the sample data: `P101`, `P102`, `P103`, `P104`.

</details>

### Exercise 2: Numbered Pagination

Each page holds two posts. Query page 3 of the full list, sorted newest to oldest using `postId` as a tie-breaker.

<details>
<summary>Suggested Solution</summary>

```cypher
MATCH (p:Post)
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP 4
LIMIT 2;
```

With the sample data: `P105`, `P106`.

</details>

### Exercise 3: Cursor Pagination with Equal Timestamps

The first page of size two contains `P101`, `P102`. Write the `WHERE` condition to fetch the next page, and explain why `createdAt < cursorCreatedAt` alone is insufficient.

<details>
<summary>Suggested Solution</summary>

```cypher
MATCH (p:Post)
WHERE p.createdAt < datetime('2026-11-09T09:00:00Z')
   OR (p.createdAt = datetime('2026-11-09T09:00:00Z') AND p.id > 'P102')
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 2;
```

The result is `P103`, `P104`. `P103` shares the same timestamp as the cursor, so comparing `id` as well is necessary to avoid skipping it.

</details>

### Exercise 4: Choosing a Strategy for Real Requirements

Application A has an admin table of 2,000 products with direct navigation to any page number. Application B has a continuously growing event stream with only a "Load more" button. Choose `SKIP/LIMIT` or keyset for each application. Name at least two measurements to perform before deployment.

**Hint:** A can start with offset if benchmarks meet requirements. B is typically better suited for keyset. For both, measure first-page/deep-page latency and sort or traversal cost, while also testing data insertion/deletion scenarios during page navigation.

## 12. Pre-Production Self-Check

- [ ] Query has an explicit `ORDER BY` with enough keys to break ties for equal values.
- [ ] `SKIP`/`LIMIT` is applied **after** sorting the exact entity grain being paginated.
- [ ] Pagination parameters are validated and bounded on the backend.
- [ ] Filters, sort order, count queries, and cursor keys are consistent with one another.
- [ ] Handled the possibility of a node appearing across multiple paths if paginating distinct nodes.
- [ ] Measured queries on deep pages and tested scenarios where data changes between page requests.
- [ ] Indexes/constraints are chosen based on `EXPLAIN`/`PROFILE` and realistic data.

## Conclusion

`ORDER BY` defines row ordering, `SKIP` skips a leading slice, and `LIMIT` caps the subsequent rows returned. For reliable Neo4j pagination, you need **deterministic ordering with a unique tie-breaker**, awareness that `LIMIT` caps **rows** rather than automatically deduplicating nodes, and the right choice between offset and cursor pagination based on how users navigate the list. As data grows or changes rapidly, performance and stability must be verified with realistic queries alongside Neo4j's execution plans.
