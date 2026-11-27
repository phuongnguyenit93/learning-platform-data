# Stable Pagination and Strategy Selection for Large Datasets in Neo4j

## Learning Objectives

Neo4j is a **property graph** database: Cypher queries match node, relationship, or path patterns and then process **result rows**. Screens listing articles, products, transaction histories, or nodes related to a user all require pagination. When a dataset is large or continuously changing, a query that returns 20 rows can still be both **slow** and cause users to see duplicate or skipped items.

This lesson belongs to the **Query Optimization** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The focus is on selecting pagination approaches suited to Neo4j's connected data, from `ORDER BY`, `SKIP`, and `LIMIT` to **keyset/cursor pagination**, indexes, `EXPLAIN`/`PROFILE`, and Java Driver/Spring Data Neo4j integration.

After this lesson, you will be able to:

1. Establish a **deterministic total order** using sort keys and a unique tie-breaker key.
2. Distinguish bugs caused by **non-deterministic ordering**, **changing data**, and **row multiplication across relationships**.
3. Write offset pagination and keyset pagination with the correct comparison directions, even when multiple nodes share the same timestamp.
4. Select a strategy based on random page-jumping needs, infinite scroll/load-more flows, dataset size, and write frequency.
5. Evaluate execution plans, design indexes, restrict graph expansion steps, and return safe cursors to clients.

> **Version note:** Examples use standard Neo4j Cypher 5 and Java Driver 5.x syntax. Index utilization for `ORDER BY` and operator names in execution plans may vary across versions, configurations, and query shapes; always verify on your target system.

## 1. The Nature of Stable Pagination

Suppose the article dataset consists of:

```text
:Post {tenantId, id, title, published, createdAt}
    ↑
[:LIKED]
    │
:User {id}
```

The application wants to display the newest posts for a tenant, 2 or 20 posts per page. Before choosing `SKIP` or a cursor, **three distinct questions** must be resolved:

- **Ordering:** If two posts share the same `createdAt`, which one comes first?
- **Pagination unit:** Does one query row represent **one post** or one matched `LIKED` relationship?
- **Data snapshot:** If a post is created, edited, or deleted between two API calls, does the list stay identical to when page 1 was loaded?

Visualizing list order:

```text
ORDER BY createdAt DESC, id ASC

P101 (11-24 10:00)
P102 (11-23 09:00)  ┐ same createdAt
P103 (11-23 09:00)  ┘ tie-breaker id
P104 (11-22 08:00)
P105 (11-21 08:00)
...
```

**Deterministic ordering** is a prerequisite for reliable pagination. It does not guarantee an **immutable snapshot across requests** if the database receives writes while the user navigates pages.

## 2. Preparing Practice Data with a Unique Key

Run in a practice database. The post identifier key in this example is the pair `(tenantId, id)`, because post IDs can repeat across tenants.

```cypher
CREATE CONSTRAINT post_tenant_id_unique IF NOT EXISTS
FOR (p:Post) REQUIRE (p.tenantId, p.id) IS UNIQUE;
```

Create eight posts for tenant `T1` and one separate post for tenant `T2`. `MERGE` by key prevents duplicating nodes on re-runs; `SET` updates sample fields:

```cypher
UNWIND [
  {tenant: 'T1', id: 'P101', ts: '2026-11-24T10:00:00Z', title: 'Graph Overview'},
  {tenant: 'T1', id: 'P102', ts: '2026-11-23T09:00:00Z', title: 'Nodes and Labels'},
  {tenant: 'T1', id: 'P103', ts: '2026-11-23T09:00:00Z', title: 'Relationships'},
  {tenant: 'T1', id: 'P104', ts: '2026-11-22T08:00:00Z', title: 'Basic Cypher'},
  {tenant: 'T1', id: 'P105', ts: '2026-11-21T08:00:00Z', title: 'Index'},
  {tenant: 'T1', id: 'P106', ts: '2026-11-20T08:00:00Z', title: 'Constraint'},
  {tenant: 'T1', id: 'P107', ts: '2026-11-19T08:00:00Z', title: 'Java Driver'},
  {tenant: 'T1', id: 'P108', ts: '2026-11-18T08:00:00Z', title: 'Spring Data'},
  {tenant: 'T2', id: 'P101', ts: '2026-11-25T10:00:00Z', title: 'Another Tenant'}
] AS item
MERGE (p:Post {tenantId: item.tenant, id: item.id})
SET p.title = item.title,
    p.published = true,
    p.createdAt = datetime(item.ts);
```

Verify `T1`'s list:

```cypher
MATCH (p:Post {tenantId: 'T1'})
WHERE p.published = true
RETURN p.id AS postId, p.createdAt AS createdAt, p.title AS title
ORDER BY createdAt DESC, postId ASC;
```

With only `T1`'s sample data, the order is `P101, P102, P103, P104, P105, P106, P107, P108`. `P102` and `P103` share the same `createdAt`. If stale data exists in the test database, filter accurately by tenant/post ID before comparing results.

## 3. Mandatory Step: Establish a Total Order

### 3.1. ORDER BY on a Single Field May Not Be Enough

```cypher
MATCH (p:Post {tenantId: 'T1'})
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC
LIMIT 2;
```

In the sample set, `P101` always has the latest timestamp, while `P102` and `P103` tie. When ordering solely by `createdAt`, Neo4j **is not required** to pick any fixed order between the two tied posts. This becomes critical if a page boundary falls right between items sharing the same key.

Add a tie-breaker key:

```cypher
MATCH (p:Post {tenantId: 'T1'})
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 2;
```

Now the first two-row page is `P101, P102`; `P103` follows immediately after `P102`. Choose an `id` that is **unique within the filtered set** and immutable throughout the record's lifecycle. If paginating across multiple tenants simultaneously, `id` alone may not be unique; add another key to break ties.

### 3.2. Fields Used in ORDER BY Must Be Consistent

- Use the same data type for a property—for example, store `createdAt` as `datetime`; never mix date strings of varying formats with temporal types.
- Decide how to handle missing properties. For instance, this lesson paginates only records with `createdAt IS NOT NULL`; if business rules require displaying posts lacking timestamps, design a dedicated sort and cursor policy.
- Tie-breaker keys should be **stable**. `elementId(p)` represents a technical entity identifier and should not be used as a durable business cursor key; prefer a business ID backed by a unique constraint.
- Keep filters, sort direction, and tie-breakers identical across page requests.

## 4. Offset Pagination: ORDER BY, SKIP, and LIMIT

The traditional approach skips the first `offset = (pageNumber - 1) * pageSize` rows after sorting.

```cypher
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true
  AND p.createdAt IS NOT NULL
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

With `tenantId = 'T1'` and `pageSize = 2`, on the initial sample set:

| Page | `offset` | Returned Data |
| ---: | ---: | --- |
| 1 | 0 | `P101, P102` |
| 2 | 2 | `P103, P104` |
| 3 | 4 | `P105, P106` |
| 4 | 6 | `P107, P108` |

**Pros:** intuitive, easy to jump directly to an arbitrary page; well-suited for admin tables with relatively small or low-churn datasets.

**Two distinct limitations:**

1. **Deep page cost.** `SKIP 100000 LIMIT 20` does not mean Neo4j reads only 20 rows: the engine may have to scan/skip many candidate rows, or even sort a large set depending on the plan.
2. **Stability under data changes.** New posts inserted at the top of the list shift record positions, even when `ORDER BY` has a complete tie-breaker.

### Example of Page Drift on Inserts or Deletes

Suppose page 1 (`P101, P102`) has been displayed. Before the user requests page 2, post `P099` is inserted with a `createdAt` newer than `P101`. The new list is:

```text
P099, P101, P102, P103, P104, ...
                  ↑ SKIP 2 starts at P102
```

Page 2 under `SKIP 2 LIMIT 2` becomes `P102, P103`: **P102 is duplicated** even though the application already showed it on page 1. Conversely, if a row from page 1 is deleted, offset pagination can **skip** a row on the next page.

Before sending the request to Neo4j, the backend must validate `pageNumber >= 1`, ensure `pageSize` stays within permitted bounds, prevent integer overflow when computing `offset`, and pass all values as **parameters**. When page counts grow large, capping offset depth or recommending cursor pagination is a sound operational choice.

## 5. Keyset/Cursor Pagination: Paginating by Key Values

Keyset pagination stores the key of the **last row actually returned to the client** on the current page. Rather than asking "skip N rows," the next page asks "rows appearing **after this key** in the same order."

### 5.1. First Page

```cypher
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true
  AND p.createdAt IS NOT NULL
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $fetchSize;
```

With `tenantId = 'T1'` and `pageSize = 2`, the backend can pass `fetchSize = 3` (see section 5.3). The two **displayed** rows are `P101` and `P102`, so the cursor records:

```json
{
  "createdAt": "2026-11-23T09:00:00Z",
  "postId": "P102"
}
```

`createdAt` is the timestamp of **P102**, not the wall-clock time when the server issued the cursor. The extra `P103` row is fetched solely to check whether a next page exists.

### 5.2. Next Page with Combined DESC and ASC

Current sort order:

```cypher
ORDER BY createdAt DESC, postId ASC
```

A row comes **after** the cursor when:

1. Its `createdAt` is **less than** the cursor's `createdAt`, **or**
2. Its `createdAt` is equal, and its `postId` is **greater than** the cursor's `postId`.

Query:

```cypher
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true
  AND p.createdAt IS NOT NULL
  AND (
    p.createdAt < datetime($cursorCreatedAt)
    OR (
      p.createdAt = datetime($cursorCreatedAt)
      AND p.id > $cursorPostId
    )
  )
RETURN p.id AS postId, p.title AS title, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $fetchSize;
```

Illustrative parameters:

```json
{
  "tenantId": "T1",
  "cursorCreatedAt": "2026-11-23T09:00:00Z",
  "cursorPostId": "P102",
  "fetchSize": 3
}
```

The two **displayed** rows are `P103, P104`, even though `P103` shares `P102`'s timestamp. Filtering solely by `p.createdAt < datetime($cursorCreatedAt)` would **skip** `P103`.

> **Watch comparison direction:** Sorting `createdAt DESC` means the next page uses `createdAt < cursorCreatedAt`. Meanwhile, for secondary key `id ASC`, when timestamps match, the next page uses `id > cursorId`. Flipping a sort direction requires flipping the corresponding comparison operator.

| Sort Order | Next-Page Condition (for keys `time` and `id`) |
| --- | --- |
| `time DESC, id ASC` | `time < t OR (time = t AND id > i)` |
| `time ASC, id ASC` | `time > t OR (time = t AND id > i)` |
| `time DESC, id DESC` | `time < t OR (time = t AND id < i)` |

If more than two fields define the order, the keyset predicate must check **equality across all leading prefix fields** before comparing the next field; omitting a field can cause records to duplicate or disappear.

### 5.3. hasNext and nextCursor Using LIMIT pageSize + 1

An API typically returns:

```json
{
  "items": ["P103", "P104"],
  "hasNext": true,
  "nextCursor": "<opaque-token>"
}
```

How to handle it:

1. The backend clamps `pageSize`, computes `fetchSize = pageSize + 1`, and runs the parameterized query.
2. If more than `pageSize` rows return, set `hasNext = true`; **return only** the first `pageSize` rows.
3. Build `nextCursor` from the **last returned row**, not the extra lookahead row used to detect `hasNext`.
4. If there is no extra row, `hasNext = false`. Typically return `nextCursor = null` to indicate the end of the list.

This avoids running an extra `count(*)` on every "Load more" click. Note that `hasNext` reflects the state at the **current query's execution time**; data may change immediately afterward.

## 6. Stability Against Writes Does Not Mean an Immutable Snapshot

### 6.1. Inserting New Posts

After page 1 returns `P101, P102`, if `P099` is added with a newer timestamp, offset page 2 could repeat `P102`. Keyset still asks for rows ordered **after P102**, so in this example it returns `P103, P104`. This is a major advantage for feeds with continuous incoming writes.

However, if a **post backdated with an older timestamp** past the cursor is inserted, subsequent pages can still include that new post. Keyset does not freeze the entire dataset.

### 6.2. Deleting or Modifying Sort Keys

- If `P103` is deleted before loading the next page, keyset will not return P103; it cannot display a deleted node.
- If a post's `createdAt` is edited so it crosses the cursor boundary, that post may appear twice or be skipped.
- If filter fields such as `published` or `tenantId` change, a post may enter or leave the list between page fetches.

To minimize issues, choose **immutable** sort keys such as original creation time plus an immutable ID. Avoid `lastModifiedAt` if the UI requires non-repeating traversal while that property changes frequently.

### 6.3. When You Truly Need a Consistent Snapshot

For financial reports, reconciliation, exports, or "read the exact set as of time T," a regular cursor alone is **not enough**. You may need one of these business-level designs:

- Record a **version/snapshot ID** and query versioned data.
- Materialize a fixed list of IDs for an export job, then iterate through that list with checkpoints.
- Store an `asOf` cutoff and enforce rules on what can change before/after that point; filtering `createdAt <= asOf` only preserves a true snapshot if the data model guarantees other edits cannot alter results.

Neo4j **bookmarks** coordinate causal transaction visibility across sessions; they do not automatically turn a series of HTTP requests into **an immutable read snapshot**. Keeping a long-running read transaction open across many pages also carries operational costs and constraints and should not be used by default for an entire user browsing session.

## 7. Paginate Nodes Before Expanding Relationships

In a property graph, one node can match multiple relationships and thus appear on multiple **rows**. `SKIP` and `LIMIT` always apply to **query rows at their clause position**, not implicitly to distinct `:Post` nodes.

Example of users liking multiple posts:

```cypher
MATCH (u:User)-[:LIKED]->(p:Post {tenantId: $tenantId})
WHERE p.published = true
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 20;
```

If one post receives 100 likes, there can be 100 rows with the same `postId`, consuming all of `LIMIT 20`. If the business requirement is to paginate **20 distinct posts**, deduplicate **before** paginating:

```cypher
MATCH (:User)-[:LIKED]->(p:Post {tenantId: $tenantId})
WHERE p.published = true AND p.createdAt IS NOT NULL
WITH DISTINCT p
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $fetchSize;
```

`DISTINCT` can be costly, especially with high relationship fan-out. If the goal is "all published posts of the tenant with their like counts," a better approach is usually to **select the page's nodes first**, then expand:

```cypher
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true AND p.createdAt IS NOT NULL
WITH p
ORDER BY p.createdAt DESC, p.id ASC
SKIP $offset
LIMIT $pageSize
OPTIONAL MATCH (:User)-[r:LIKED]->(p)
WITH p, count(r) AS likes
RETURN p.id AS postId, p.title AS title,
       p.createdAt AS createdAt, likes
ORDER BY createdAt DESC, postId ASC;
```

Business-aligned execution order:

1. Select `Post` nodes matching filters and ordering.
2. Retain at most `pageSize` nodes after skipping.
3. Only then look up `LIKED` relationships and aggregate counts for **just the nodes on the page**.
4. The final `ORDER BY` re-establishes display order after aggregation; do not rely on incidental ordering from expansion.

To use **keyset**, replace `SKIP $offset` with the cursor predicate before `WITH ... ORDER BY ... LIMIT`. When the requirement is sorting by `likeCount`, computing counts for all posts **before** paginating can be very expensive. Consider maintaining a synchronized `likeCount` property governed by business rules and indexing/sorting on that property; in return, you must manage the consistency of that derived count.

## 8. Indexes and Execution Plans on Large Datasets

### 8.1. Designing Indexes for Filters and Ordering

The `(tenantId, id)` unique constraint from setup protects identity. For feed queries that always filter `tenantId`, `published` and sort by `createdAt`, you can **benchmark** a composite range index:

```cypher
CREATE RANGE INDEX post_feed_sort IF NOT EXISTS
FOR (p:Post)
ON (p.tenantId, p.published, p.createdAt, p.id);
```

An index only helps if the optimizer can leverage it for the specific query. For example, `ORDER BY createdAt DESC, id ASC` has **mixed directions**; even with a composite index, do not assume Neo4j will eliminate the sort step or always seek directly to the cursor. The `OR` condition in keyset, selectivity of `tenantId`, `published`, and `createdAt` distribution all influence the plan.

If the application supports multiple sort modes (newest, most popular, by title), avoid indexing every permutation without measurements: indexes consume storage and increase write overhead.

### 8.2. EXPLAIN First, PROFILE to Measure

To inspect the estimated plan **without executing the query**:

```cypher
EXPLAIN
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true AND p.createdAt IS NOT NULL
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP $offset
LIMIT $pageSize;
```

To measure against test data:

```cypher
PROFILE
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true AND p.createdAt IS NOT NULL
  AND (
    p.createdAt < datetime($cursorCreatedAt)
    OR (
      p.createdAt = datetime($cursorCreatedAt)
      AND p.id > $cursorPostId
    )
  )
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT $fetchSize;
```

Pay attention to:

- `NodeIndexSeek`/`NodeIndexScan`, `Sort`/`Top`/`Skip` operators, input/output row counts, and DB Hits; exact operator names depend on version and plan.
- Relationship expansion volume, intermediate row counts, and `collect()` materialization if the query traverses edges.
- Difference between the first page and deep pages (e.g., `offset = 0` vs. `offset = 100000`) with the same `pageSize` and filters.
- Latency at p50/p95/p99, memory usage, throughput, and concurrency. Conclusions are only reliable with realistic data, indexes, and configuration.

Keyset typically avoids offset's **cost of skipping prior pages**, yet it is not automatically `O(pageSize)`. If the optimizer still has to read or sort a huge candidate set, keyset can also be slow. Benchmark the cursor predicate and index choices before committing to performance targets.

### 8.3. Total Counts and "Deep Pages"

If an offset UI needs total page counts, it usually runs an additional query:

```cypher
MATCH (p:Post {tenantId: $tenantId})
WHERE p.published = true AND p.createdAt IS NOT NULL
RETURN count(p) AS totalPosts;
```

The count query must use the **exact same filters** as the data query. If the graph pattern can multiply rows, `count(DISTINCT p)` may be required to count distinct nodes accurately. Frequent large counts also consume resources; for cursor feeds, `hasNext` is usually enough and avoids counting on every load.

`totalPosts` from one request and page items from another request can diverge under concurrent writes. If exact point-in-time consistency is needed, design appropriate transaction/snapshot semantics or accept an **approximate/live** total per UI requirements.

## 9. Cursor API Design and Java Integration

### 9.1. Cursors Are Application Data That Must Be Validated

At minimum, a cursor holds `createdAt` and `postId` of the last item; a production API should also include:

```json
{
  "v": 1,
  "sort": "createdAt_desc_id_asc",
  "tenantId": "T1",
  "filtersHash": "hash-of-canonical-filters",
  "createdAt": "2026-11-23T09:00:00Z",
  "postId": "P102"
}
```

This is an **illustrative pre-encoding payload**, not a raw token to expose as-is. Encode with Base64URL and sign with HMAC, or use an opaque ID referencing server-side cursor state. **Plain Base64 provides no integrity protection.** The backend must validate and verify tenant, authorization, filter configuration, value types, and cursor version; never trust a tenant ID or security predicate merely because it came inside a token.

When a cursor is invalid or mismatches current filters/sort, return a clear error so the client reloads from page 1. If users can choose sort fields, map from a **fixed allowlist** to controlled Cypher clauses; never concatenate raw field names or clauses from user input.

### 9.2. Java Driver: Passing Parameters and Fetching One Extra Row

Java 17+, Neo4j Java Driver 5.x example. `Driver` is assumed to be initialized in application configuration; connection, auth, and cursor encoding details are omitted:

```java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class PostPaging {
    private static final String NEXT_PAGE = """
        MATCH (p:Post {tenantId: $tenantId})
        WHERE p.published = true
          AND p.createdAt IS NOT NULL
          AND (
            p.createdAt < datetime($cursorCreatedAt)
            OR (
              p.createdAt = datetime($cursorCreatedAt)
              AND p.id > $cursorPostId
            )
          )
        RETURN p.id AS postId, p.title AS title,
               p.createdAt AS createdAt
        ORDER BY createdAt DESC, postId ASC
        LIMIT $fetchSize
        """;

    public static List<Record> readNext(
        Driver driver, String tenantId,
        String cursorCreatedAt, String cursorPostId,
        int pageSize
    ) {
        if (tenantId == null || tenantId.isBlank()
            || cursorCreatedAt == null || cursorPostId == null
            || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid cursor request");
        }

        Map<String, Object> parameters = Map.of(
            "tenantId", tenantId,
            "cursorCreatedAt", cursorCreatedAt,
            "cursorPostId", cursorPostId,
            "fetchSize", pageSize + 1
        );

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeRead(
                tx -> tx.run(NEXT_PAGE, parameters).list()
            );
        }
    }
}
```

Once `readNext` returns, the application maps up to `pageSize` records into DTOs, compares the record count against `pageSize` to set `hasNext`, and constructs the next cursor from the last record **returned to the client**. Driver `Record` values can be converted to the appropriate date/time type and encoded according to a consistent API format.

For the first page, run a similar query **without the cursor predicate**. In `RETURN`, select only needed properties instead of returning whole large nodes; the driver still has to read results over the wire, so returned payload size also affects latency.

### 9.3. Spring Data Neo4j

`Pageable`/`Sort` are convenient for numbered pages on SDN-supported repository methods. `Page` can trigger an extra count query, whereas `Slice` is often better when you only need to know if a next page exists; check exact behavior for your repository and SDN version.

For multi-field keyset pagination or graph queries with fan-out, write explicit Cypher via `@Query` or `Neo4jClient`, pass cursor parameters, and assemble DTOs and `nextCursor` in the service layer. Do not assume SDN's node-and-relationship mapping automatically deduplicates in a way that matches the **Cypher row counts** used for `SKIP`/`LIMIT`. Test specifically on nodes with many relationships.

## 10. Choosing a Strategy by Scenario

| Requirement | Offset with `SKIP/LIMIT` | Keyset/Cursor |
| --- | --- | --- |
| Jump directly to "Page 57" | Convenient, computes `offset` directly | Inconvenient without intermediate cursors |
| Continuous "Load more" feed | Works, but prone to drift on new writes | Usually a better fit |
| Very deep pages on large data | May read/skip many rows | Can perform better with supporting filters and indexes |
| Needs exact total page count | Requires a filtered count query | Usually unnecessary; uses `hasNext` |
| Sort order has duplicate keys | Must add a tie-breaker key | Must add a tie-breaker key **and** store it in the cursor |
| Sort key mutated between requests | Risk of duplicates/skips | Still risks duplicates/skips |
| Needs strict snapshot across requests | Requires dedicated snapshot/version mechanism | Also requires dedicated snapshot/version mechanism |
| Paginating nodes after graph expansion | Deduplicate or select nodes first | Same; crucial to paginate the right entity |

Selection guidelines:

1. **Admin table with a few thousand rows, low churn, random page jumps needed:** start with offset, benchmark deep pages and count query cost.
2. **Feed with millions of posts, constant inserts, "Load more" navigation:** prefer keyset with immutable `createdAt` + unique ID; verify index/plan.
3. **List sorted by scores aggregated across many relationships:** consider precomputing scores, bounding expanded nodes, or introducing an indexed/materialized property; do not assume a whole-graph aggregation query will be fast.
4. **Report export or reconciliation needing exact data at a point in time:** prioritize business snapshot/version/checkpoint design first, then choose offset or keyset.

## 11. Common Mistakes and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Same data, yet rows flicker between loads | `ORDER BY` only on a non-unique field | Add a unique tie-breaker key |
| After a new post arrives, next page repeats items | Offset shifted | Switch to keyset for "Load more" flows where suitable |
| P103 skipped when P102 and P103 share timestamp | Cursor only compares `createdAt` | Also check `id > cursorId` when timestamps tie |
| Query returns 20 rows but only 3 distinct posts | Relationship fan-out multiplies rows | `WITH DISTINCT p` or paginate nodes before expanding |
| Deep pages sharply increase latency | Large `SKIP`, scanning/sorting many candidates | Measure with `PROFILE`, test keyset and filter-aligned indexes |
| Keyset is still slow despite `LIMIT 20` | Plan scans or sorts many records | Inspect operators, index selection, and selectivity |
| Posts jump back and forth across pages | Mutable sort property changed | Use immutable keys or versioning/snapshots |
| Old cursor accepted for different filters | Cursor not bound to filter/sort state | Validate and version cursor tokens |
| Wrong total page count displayed | Count query uses different filters or counts graph rows | Use identical filters and `count(DISTINCT p)` when needed |
| Index exists yet Sort still runs | Query or `ORDER BY` directions mismatch index | Inspect actual plan, test an appropriate index |

## 12. Guided Practice Exercises

### Exercise 1: Predicting an Offset Page

With `T1` data, `pageSize = 3`, and ordering `createdAt DESC, id ASC`, write the query for page 2 and state the result.

```cypher
MATCH (p:Post {tenantId: 'T1'})
WHERE p.published = true
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
SKIP 3
LIMIT 3;
```

**Answer:** `P104, P105, P106` on the initial sample dataset.

### Exercise 2: Writing a Cursor When Two Posts Share a Timestamp

Page 1 contains `P101, P102`. Write the next-page query so `P103` is not skipped.

```cypher
MATCH (p:Post {tenantId: 'T1'})
WHERE p.published = true
  AND (
    p.createdAt < datetime('2026-11-23T09:00:00Z')
    OR (
      p.createdAt = datetime('2026-11-23T09:00:00Z')
      AND p.id > 'P102'
    )
  )
RETURN p.id AS postId, p.createdAt AS createdAt
ORDER BY createdAt DESC, postId ASC
LIMIT 2;
```

**Answer:** `P103, P104`. The equal-timestamp plus greater-than-cursor-ID condition preserves P103.

### Exercise 3: Paginating on Nodes vs. Relationships?

A post has 50 `LIKED` relationships. Does `MATCH (u)-[:LIKED]->(p) ... LIMIT 10` guarantee ten distinct posts? Fix it in two steps.

**Hint:** first run `MATCH (p:Post) ... WITH p ORDER BY ... LIMIT 10`, then `OPTIONAL MATCH` to fetch needed relationships for **those ten nodes**, and finally `RETURN ... ORDER BY`. If "liked by at least one user" is mandatory, filter the qualifying node set first and use `WITH DISTINCT p` to avoid row multiplication.

### Exercise 4: Choosing a Strategy

System A displays 3,000 admin accounts and must jump directly to page 35. System B has 5 million events, only a "Load more" button, and new records every second. System C exports a report that must reflect exact data at accounting cut-off time.

**Suggested Answer:** A can try offset and benchmark deep pages; B typically suits keyset with immutable sort keys; C requires a snapshot/version or fixed ID list to guarantee the dataset, regardless of pagination style afterward.

### Exercise 5: Measure Performance Instead of Guessing

Run `EXPLAIN` and `PROFILE` (in a testing environment) for page 1, a deep page, and keyset with a valid cursor. Record:

- Input/output row counts at operators.
- Presence of large sort operators, index seeks/scans, and relationship expansion steps.
- Latency, throughput, DB Hits, and differences as `offset` grows.

Explain why a query with `LIMIT 20` can still process far more than 20 rows.

## 13. Pre-Deployment Checklist

- [ ] `ORDER BY` establishes a total order with a unique, stable tie-breaker key.
- [ ] Cursor fields have consistent data types, time zones, and `null` handling policies.
- [ ] Tenant/authorization filters apply to every page; cursors are validated and bound to filters/sort.
- [ ] Keyset next-page queries use comparison operators matching each `ASC`/`DESC` direction.
- [ ] `LIMIT pageSize+1` is calculated on the backend; the cursor is taken from the last **displayed** row.
- [ ] `SKIP`/`LIMIT` operates on the exact unit being paginated: nodes, relationships, or aggregated rows.
- [ ] Tested inserts, deletes, sort-property updates, and filter changes between requests.
- [ ] Decided explicitly whether an immutable snapshot is needed or simply more stable traversal.
- [ ] Measured `EXPLAIN`/`PROFILE` with representative data, indexes, and deep pages.
- [ ] Count and data queries share identical filters; count is only run when the UI truly requires it.

## Conclusion

Stable pagination in Neo4j begins by **defining a total order on the exact entity being paginated**. `SKIP/LIMIT` is simple and convenient for jumping to arbitrary page numbers, but costs can climb on deep pages and positions shift when data changes. **Keyset/cursor** pagination based on the last row's keys is usually better for large, continuously changing feeds; it requires accurate multi-field comparisons, cursor validation, and verifying that queries/indexes genuinely reduce work. Both strategies require an explicit snapshot model if business logic demands an immutable dataset across multiple requests. Ultimately, `EXPLAIN`, `PROFILE`, and testing relationship fan-out let you pick strategies based on actual graph behavior.

### References

- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/)
- [Neo4j Cypher Manual — SKIP](https://neo4j.com/docs/cypher-manual/current/clauses/skip/)
- [Neo4j Cypher Manual — LIMIT](https://neo4j.com/docs/cypher-manual/current/clauses/limit/)
- [Neo4j Cypher Manual — Search-performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/)
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/)
