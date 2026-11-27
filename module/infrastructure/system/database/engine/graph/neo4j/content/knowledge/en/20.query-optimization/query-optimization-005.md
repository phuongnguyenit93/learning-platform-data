# Reducing Large collect() Calls, Unnecessary Sorting, and Returned Payload Size in Neo4j

When tuning Cypher queries, many people focus only on adding indexes to speed up `MATCH`. Yet even when Neo4j finds the right nodes quickly, a query can still be slow because it **generates too many intermediate rows**, **materializes huge lists via `collect()`**, **sorts too many elements with `ORDER BY`**, or **ships unnecessary nodes, relationships, and properties back to the application**.

This lesson belongs to the **Query Optimization** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The focus is on changing **how results are built and returned** when working with Neo4j property graphs: expanding only the needed portion of the graph, aggregating in a controlled way, sorting in the right place, and shrinking payload size. These principles apply to direct Cypher queries, applications using the Neo4j Java Driver, and Spring Data Neo4j.

## 1. Three Easily Overlooked Sources of Cost

| Issue | Signal in Query | Common Consequence | Mitigation |
| --- | --- | --- | --- |
| **Large `collect()`** | `collect(a)` or `collect(path)` over thousands/millions of results | Huge lists materialized for aggregation, increasing query and application memory | Narrow scope before collecting; use `count()`/`EXISTS` if a list is unneeded; stream rows if possible |
| **Unnecessary sorting** | `ORDER BY` at multiple stages, or sorting the whole set then discarding order | Extra work for `Sort`/`Top`, raising memory usage and latency | Sort only when output ordering or top-k selection requires it; leverage an appropriate index if available |
| **Returning too much data** | `RETURN a`, `RETURN *`, `RETURN path` when the UI needs only a few fields | Increases serialization, network bandwidth, allocation, and object mapping overhead | Return a slim projection, paginate, fetch only needed properties and metrics |

Distinguish **row count** (*cardinality*) from **row width**. A query returning 20 rows containing long document bodies and entire paths can still be heavier than 200 rows containing only IDs and titles.

A simple mental picture:

```text
Neo4j locates nodes
     ↓
Expands relationships → row count may grow
     ↓
Filter / DISTINCT / aggregation → may process large intermediates
     ↓
Sort / LIMIT → may buffer or sort many rows
     ↓
RETURN → builds payload over Bolt, Driver, application
```

A trailing `LIMIT` only guarantees the **final returned row count**; it does not automatically prove every prior step processed little data. Neo4j can optimize some plans to stop early, but you must inspect the execution plan to verify whether that applies.

## 2. Test Dataset: Users, Articles, Tags, and Comments

Run the following `CREATE` **once on a testing database**. Labels and relationship types prefixed with `OptDemo` separate the example from production data. Do not re-run `CREATE` in the same database if you want to reproduce the exact counts.

```cypher
CREATE
  (an:OptDemoUser {userId: 'U01', name: 'An'}),
  (binh:OptDemoUser {userId: 'U02', name: 'Bình'}),
  (chi:OptDemoUser {userId: 'U03', name: 'Chi'}),
  (a1:OptDemoArticle {
    articleId: 'A101', title: 'Neo4j and Cypher',
    body: 'Long content of article A101...',
    published: true, publishedAt: date('2026-01-10')
  }),
  (a2:OptDemoArticle {
    articleId: 'A102', title: 'Java Driver',
    body: 'Long content of article A102...',
    published: true, publishedAt: date('2026-01-09')
  }),
  (a3:OptDemoArticle {
    articleId: 'A103', title: 'Graph Modeling',
    body: 'Long content of article A103...',
    published: true, publishedAt: date('2026-01-08')
  }),
  (a4:OptDemoArticle {
    articleId: 'A104', title: 'Draft Article',
    body: 'Long content of article A104...',
    published: false, publishedAt: date('2026-01-07')
  }),
  (t1:OptDemoTag {name: 'Neo4j'}),
  (t2:OptDemoTag {name: 'Cypher'}),
  (t3:OptDemoTag {name: 'Java'}),
  (c1:OptDemoComment {commentId: 'C01', text: 'Comment 1'}),
  (c2:OptDemoComment {commentId: 'C02', text: 'Comment 2'}),
  (c3:OptDemoComment {commentId: 'C03', text: 'Comment 3'}),
  (c4:OptDemoComment {commentId: 'C04', text: 'Comment 4'}),
  (c5:OptDemoComment {commentId: 'C05', text: 'Comment 5'}),
  (an)-[:OPT_DEMO_LIKED]->(a1),
  (an)-[:OPT_DEMO_LIKED]->(a2),
  (binh)-[:OPT_DEMO_LIKED]->(a1),
  (a1)-[:OPT_DEMO_TAGGED]->(t1),
  (a1)-[:OPT_DEMO_TAGGED]->(t2),
  (a2)-[:OPT_DEMO_TAGGED]->(t3),
  (a3)-[:OPT_DEMO_TAGGED]->(t1),
  (a1)-[:OPT_DEMO_HAS_COMMENT]->(c1),
  (a1)-[:OPT_DEMO_HAS_COMMENT]->(c2),
  (a1)-[:OPT_DEMO_HAS_COMMENT]->(c3),
  (a2)-[:OPT_DEMO_HAS_COMMENT]->(c4),
  (a3)-[:OPT_DEMO_HAS_COMMENT]->(c5);
```

Diagram of the relevant data:

```text
An ────────LIKED────────► A101 ──TAGGED────► Neo4j, Cypher
  └────────LIKED────────► A102 ──TAGGED────► Java
Bình ──────LIKED────────► A101
Chi ───────(no liked articles yet)

A101 ──HAS_COMMENT─────► C01, C02, C03
A102 ──HAS_COMMENT─────► C04
A103 ──HAS_COMMENT─────► C05
A104 ──(no tags/comments)
```

In this example, An liked 2 articles, Bình liked 1 article, Chi liked none; A101 has **2 tags and 3 comments**. These one-to-many branches demonstrate why intermediate data volume can grow rapidly.

## 3. Observing Cardinality Growth Before Collecting

Consider a query fetching users who liked articles, along with each article's tags and comments:

```cypher
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
OPTIONAL MATCH (a)-[:OPT_DEMO_HAS_COMMENT]->(c:OptDemoComment)
RETURN u.userId AS userId, a.articleId AS articleId,
       t.name AS tag, c.commentId AS commentId
ORDER BY userId, articleId, tag, commentId;
```

Track row counts across the sample dataset:

| Stage | An | Bình | Chi | Total |
| --- | ---: | ---: | ---: | ---: |
| `MATCH user→liked→article` | 2 | 1 | 0 | **3** |
| `OPTIONAL MATCH article→tag` | 3 | 2 | 0 | **5** |
| `OPTIONAL MATCH article→comment` | 7 | 6 | 0 | **13** |

For A101, each user who liked it generates `2 tags × 3 comments = 6` rows. From **3 initial likes**, the query produces **13 rows** when joining two independent branches. Even if you subsequently write `collect(DISTINCT t.name)` and `collect(DISTINCT c.commentId)` to shrink final row counts, **the intermediate combinations have already been generated**.

Count each stage to verify for yourself:

```cypher
// 3 rows: likes
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
RETURN count(*) AS rows;
```

```cypher
// 5 rows: each like expands to tags
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
RETURN count(*) AS rows;
```

```cypher
// 13 rows: expanding both tags and comments simultaneously
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
OPTIONAL MATCH (a)-[:OPT_DEMO_HAS_COMMENT]->(c:OptDemoComment)
RETURN count(*) AS rows;
```

**Key lesson:** optimizing `collect` is not merely about making the final list shorter; it also requires avoiding unnecessary intermediate combinations before aggregation.

## 4. Only Use collect When You Actually Need a List

### 4.1. Anti-Pattern: Collecting Entire Nodes

Suppose an article list API only displays titles and publish dates. The following query collects **entire nodes** into a single list:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
WITH collect(a) AS articles
RETURN articles;
```

With 3 published articles in the sample data, this runs fine, but when article counts grow into the millions, `collect(a)` builds a collection of matching scale. Having **only one row containing a list** does not make it lightweight: that list holds references to every collected node, and returning it forces transferring/reading a massive payload.

If you only need the first page of a list, return **one row per article with minimal properties**, and limit the article count:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
LIMIT 20;
```

Here `LIMIT 20` is a **requirement of the paginated view**, not an arbitrary cap slapped onto a "fetch all articles" query. If the product genuinely needs to export the entire dataset, split it into controlled batches or stream result rows as appropriate.

### 4.2. Only Need a Count? Use count

```cypher
// No need to collect the entire article list just to count
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN count(*) AS publishedCount;
```

The result is **3**. Compared to `size(collect(a))`, `count(*)` directly expresses the counting intent without allocating a list of nodes in the result.

Remember to choose the right counting unit:

- `count(*)` counts rows.
- `count(a)` counts non-`null` values of `a`.
- `count(DISTINCT a)` counts distinct `a` nodes when a node appears across multiple rows after relationship expansion.

If `MATCH` already multiplied rows by tags or comments, `count(*)` may **no longer** equal the number of articles.

### 4.3. Only Need Existence? Use EXISTS

The question "does the article have at least one comment?" does not require a list of comments:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
  AND EXISTS {
    MATCH (a)-[:OPT_DEMO_HAS_COMMENT]->(:OptDemoComment)
  }
RETURN a.articleId AS articleId, a.title AS title
ORDER BY articleId;
```

The result has **A101, A102, A103**, one row per article. Instead of expanding all comments and using `collect()` or `DISTINCT` to deduplicate, an existence predicate clearly communicates the query's intent.

In Cypher 5 supporting `COUNT` subqueries, when you need **each article's comment count**, you can write:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title,
       COUNT {
         (a)-[:OPT_DEMO_HAS_COMMENT]->(:OptDemoComment)
       } AS commentCount
ORDER BY articleId;
```

The corresponding results are **A101: 3**, **A102: 1**, **A103: 1**. `COUNT { ... }` returns a single number per article without materializing comment nodes into a list. If an older Cypher version does not support count subqueries, substitute `OPTIONAL MATCH` + `count(c)` with an appropriate grouping key.

## 5. When Child Lists Are Needed, Collect After Narrowing the Parent Set

Suppose the UI only wants the **two newest articles An liked**, along with each article's tags. A wasteful approach expands all tags, collects everything, and slices the list in the application.

Instead, **select the two articles first**, and only then fetch their tags:

```cypher
MATCH (:OptDemoUser {userId: 'U01'})
      -[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
WITH DISTINCT a
ORDER BY a.publishedAt DESC, a.articleId ASC
LIMIT 2
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
WITH a, collect(t.name) AS tags
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt,
       tags
ORDER BY publishedAt DESC, articleId ASC;
```

The result has 2 rows: A101 with `['Neo4j','Cypher']` (element order is not guaranteed without sorting before `collect`) and A102 with `['Java']`. Even for an article with no tags, `OPTIONAL MATCH` preserves the article and `collect(null)` yields an empty list.

**Why does limiting at the right spot matter?** If you place `LIMIT 2` **after expanding tags**, the limit applies to **article–tag pair rows**, not "two articles." A101 could occupy both rows, making A102 disappear. To cap **parent entities**, narrow the `a` set before expanding child relationships.

`DISTINCT a` in the example guards against an article matching multiple times in the preceding step. `DISTINCT` also carries a cost; if your model and `MATCH` guarantee each article appears only once, you can remove it after verifying.

### 5.1. Avoid Combinatorial Products Across Multiple Child Lists

When an article has 2 tags and 3 comments, expanding both branches in the same pipeline can generate **6 rows**. If you only need the list of tags and the **comment count**, keep the two independent:

```cypher
MATCH (a:OptDemoArticle {articleId: 'A101'})
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
WITH a, collect(t.name) AS tags
RETURN a.articleId AS articleId,
       tags,
       COUNT {
         (a)-[:OPT_DEMO_HAS_COMMENT]->(:OptDemoComment)
       } AS commentCount;
```

The query above does not expand comments into individual rows, avoiding multiplying the tag set by the comment set. It returns **one row**: A101's tags and `commentCount = 3`.

If both lists are required, **aggregate each branch separately** and combine them per article. In Neo4j 5, for example, use subqueries with a correlated variable:

```cypher
MATCH (a:OptDemoArticle {articleId: 'A101'})
CALL {
  WITH a
  OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
  RETURN collect(t.name) AS tags
}
CALL {
  WITH a
  OPTIONAL MATCH (a)-[:OPT_DEMO_HAS_COMMENT]->(c:OptDemoComment)
  RETURN collect(c.commentId) AS commentIds
}
RETURN a.articleId AS articleId, tags, commentIds;
```

Each branch collects its own results and returns a single list per article; there are no 2×3 tag–comment combinations. `CALL { WITH a ... }` uses variable-import syntax compatible with many Neo4j 5 releases; newer Neo4j versions also support the variable scope clause `CALL (a) { ... }`. When tuning, inspect the execution plan because subqueries also have execution overhead.

## 6. When Does DISTINCT Help, and When Does It Only Mask Symptoms?

`DISTINCT` is useful when business logic requires **unique nodes**. For example:

```cypher
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
RETURN DISTINCT a.articleId AS articleId
ORDER BY articleId;
```

The result contains only **A101** and **A102**, even though A101 was liked by two users. However, if the query expanded both tags and comments before applying `DISTINCT a`, Neo4j might still have to process many combinations prior to deduplication.

Ask why duplicates exist:

1. Does one node have multiple valid relationships causing it to appear multiple times? If unique nodes are needed, `DISTINCT` fits.
2. Are **two independent branches** joined into a combinatorial product? Aggregate each branch separately or use `EXISTS`/`COUNT`.
3. Do patterns lack shared variables or join predicates? Check for `CartesianProduct` in the execution plan.
4. Are duplicate relationships stored in the data? Fix the model/constraints rather than defaulting to deduplication in every query.

**Do not use `DISTINCT` as a default performance band-aid.** It can alter semantics if the business logic actually needs to count matching occurrences or parallel relationships.

## 7. Only Sort When Ordering Matters

`ORDER BY` is required when business logic demands deterministic ordering—such as latest articles, alphabetical lists, top trending products, or pagination. Yet every sort can add CPU and memory overhead.

For instance, if you only need to count likes per article, **there is no reason to sort by user name before aggregating**:

```cypher
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
WITH a, count(u) AS likeCount
RETURN a.articleId AS articleId, likeCount;
```

If the UI actually asks for the most-liked articles, **sort after grouping**, then limit:

```cypher
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
WITH a, count(u) AS likeCount
RETURN a.articleId AS articleId,
       a.title AS title,
       likeCount
ORDER BY likeCount DESC, articleId ASC
LIMIT 10;
```

On the sample data, A101 has **2 likes** and A102 has **1 like**. Sorting **two aggregated rows** is vastly cheaper at scale than trying to sort all individual like rows, though on tiny datasets the difference is negligible.

### 7.1. ORDER BY Combined with LIMIT: Top-k, Not Always a Full Sort

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
LIMIT 2;
```

A plan may use `Top` or a top-k mechanism to keep only the best candidates instead of performing a full sort; if an index matches the sort order and filter, the planner can sometimes leverage index ordering directly. **Never assume that merely adding `LIMIT` avoids all reads or sorts.** Use `EXPLAIN` and `PROFILE` to check.

When **there is no `ORDER BY`**, the result set fed to `LIMIT` has no guaranteed order. This may be acceptable if the business logic just wants any arbitrary subset, but it is **unsuitable** for "most recent" lists or stable pagination.

### 7.2. Placing ORDER BY in the Right Spot

A sort placed amid large expansion steps can lose its ordering after subsequent steps generate new rows. Typically appropriate locations are:

- **Before `LIMIT`** to pick the exact top-k items by criteria.
- **After `Aggregation`** when the sort key is an aggregated value such as `likeCount`.
- **At the final `RETURN`** when the client needs results presented in order.
- **Right before `collect()`** when list element order matters, ensuring ordering feeds directly into the aggregation.

Example sorting tags by name before collecting:

```cypher
MATCH (a:OptDemoArticle {articleId: 'A101'})
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
WITH a, t
ORDER BY t.name ASC
RETURN a.articleId AS articleId,
       collect(t.name) AS orderedTags;
```

The `ORDER BY` on `WITH` provides row ordering for the aggregation immediately following it; the expected list is `['Cypher', 'Neo4j']`. With more complex data, assess whether in-list ordering is truly needed or if the UI can sort an already-bounded list.

## 8. Paginating to Avoid Collecting and Returning Everything

In web applications, users typically view only a small slice of records at a time. Pagination reduces returned data volume, lowers DTO mapping overhead, and lets the UI respond faster.

### 8.1. Simple Pagination with SKIP and LIMIT

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP $offset
LIMIT $pageSize;
```

Bind `$offset` and `$pageSize` from the application, e.g. `offset = 0` and `pageSize = 20`. Include a **stable tie-breaker key** `articleId` when two articles share the same `publishedAt` to prevent unstable ordering.

When `offset` becomes very large, the database may still need to process or skip many rows before reaching the requested page. `SKIP 100000 LIMIT 20` is rarely as cheap as `SKIP 0 LIMIT 20`; measure on real data. New records inserted between page reads can also cause `SKIP` pages to duplicate or skip items.

### 8.2. Keyset (Cursor) Pagination for Large Datasets

With ordering `publishedAt DESC, articleId ASC`, you can use the last pair of values from the previous page as a cursor:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
  AND (
    a.publishedAt < date($cursorDate)
    OR (
      a.publishedAt = date($cursorDate)
      AND a.articleId > $cursorId
    )
  )
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
LIMIT $pageSize;
```

For example, `$cursorDate` is the ISO string `'2026-01-10'` and `$cursorId = 'A101'`; the query fetches articles appearing **after** A101 in the agreed sort order. The first page has no cursor, so run the query without the cursor predicate and record the final `publishedAt` and `articleId` as the next cursor.

**Preconditions:** sort keys must be stable and populated for every record in scope; `articleId` should be business-unique. If a record's `publishedAt` is updated between page loads, page membership can still shift. Consider product consistency requirements alongside indexes suited for the predicates and sort order.

Keyset pagination does not automatically guarantee every query will be fast; it generally avoids skipping large offsets, yet you still must check indexes, selectivity, and plans.

## 9. Per-Group Limits Differ from Global Result Limits

A common mistake: wanting "**the two most recent articles for each user**" and writing `LIMIT 2` on the entire stream:

```cypher
// Wrong intent if you want 2 articles PER person
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
WITH u, a
ORDER BY a.publishedAt DESC
LIMIT 2
RETURN u.userId AS userId, a.articleId AS articleId;
```

`LIMIT 2` above returns at most **two rows total across all users**, not two articles per user.

If you genuinely need a per-user article list, you can use a correlated subquery:

```cypher
MATCH (u:OptDemoUser)
CALL {
  WITH u
  MATCH (u)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
  WITH DISTINCT a
  ORDER BY a.publishedAt DESC, a.articleId ASC
  LIMIT 2
  RETURN collect(a.articleId) AS recentLikedArticleIds
}
RETURN u.userId AS userId,
       recentLikedArticleIds
ORDER BY userId;
```

Result on sample data: An gets `['A101','A102']`, Bình gets `['A101']`, Chi gets `[]`. Because `collect()` inside the subquery executes **after `LIMIT 2`**, each user's output list contains at most two IDs. An ungrouped aggregation returns one row with `[]` even when the inner `MATCH` finds no articles, keeping Chi in the results.

**Per-group limits are not free:** a correlated subquery can execute once per outer user row; on large user sets, check the execution plan and choose an appropriate batching or query design. This example illustrates **proper `LIMIT` scoping**, without claiming it is always the fastest approach.

## 10. Reducing Returned Data Volume: Small, Purpose-Built Projections

Suppose `a.body` is a lengthy article text, while the list view only needs ID, title, and date:

```cypher
// Returning the entire node — may include a large body property
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a
ORDER BY a.publishedAt DESC
LIMIT 20;
```

The query is syntactically short yet returns entities packed with more properties than the screen needs. Return a minimal projection instead:

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
LIMIT 20;
```

Points to keep in mind:

- `RETURN a` and `RETURN *` can pull entire entities/variables in scope, producing unnecessary payload. `properties(a)` explicitly fetches all properties as well.
- `RETURN path` carries every node and relationship along the path; return paths only when the UI truly needs the path structure. For analytics, `length(path)` or aggregated values are often sufficient.
- Selecting only `a.articleId` and `a.title` does not mean Neo4j never reads other properties for filtering/sorting; this optimizes **output shape**, without guaranteeing every storage read vanishes.
- `collect({id: a.articleId, title: a.title})` is smaller than `collect(a)` when each map holds only a few fields, yet it is still **a list** that must be collected. If the application can consume rows sequentially, you may not need `collect`.
- `LIMIT 20` shrinks returned rows, but if earlier steps perform large expansions or aggregations, tune those steps separately.

When the application opens the detail page, a second query by `articleId` can fetch `body` on demand. This is an API design choice: **list views** return compact summaries, **detail views** load full content.

## 11. Java Driver, Spring Data Neo4j, and Application-Side Cost

The data pipeline does not end at `RETURN`. Neo4j also serializes results over the Bolt protocol, the Java Driver receives records, the application maps them to DTOs/entities, and the service sends JSON or equivalent content to the UI.

With the **Neo4j Java Driver**, pass `$pageSize` as a parameter and consume records iteratively as needed instead of buffering everything into a huge `List` before processing. Java example (with an existing `Driver driver`):

```java
import java.util.Map;
import org.neo4j.driver.Record;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;

// Assume driver is managed at the application lifecycle.
try (Session session = driver.session()) {
    Result result = session.run(
        "MATCH (a:OptDemoArticle) " +
        "WHERE a.published = true " +
        "RETURN a.articleId AS articleId, a.title AS title " +
        "ORDER BY a.publishedAt DESC, a.articleId ASC " +
        "LIMIT $pageSize",
        Map.of("pageSize", 20)
    );

    while (result.hasNext()) {
        Record row = result.next();
        String id = row.get("articleId").asString();
        String title = row.get("title").asString();
        // Process each record within the session scope.
        System.out.println(id + ": " + title);
    }
}
```

The query returns only **two properties** for up to 20 articles, and the code iterates record by record. Still, Driver fetching/buffering and downstream serialization carry overhead; do not assume a simple loop suffices for processing millions of rows in all scenarios. For large exports, design batching and proper transaction/session lifecycle management.

With **Spring Data Neo4j**, consider DTO projections for endpoints needing only a subset of fields and carefully check eager/nested relationship loading on entities. Example projection query (conceptual):

```cypher
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId, a.title AS title
ORDER BY a.publishedAt DESC, a.articleId
LIMIT $pageSize;
```

In Java, the mapper should extract only `articleId` and `title` for the list DTO. Returning a full entity and merely stripping fields during JSON serialization may have already incurred unnecessary query and mapping costs.

Avoid the **N+1** anti-pattern: fetching 20 articles, then issuing 20 separate queries for comment counts. Use a single aggregated query, per-article `COUNT { ... }`, or a batched query with `UNWIND $articleIds` where suitable for your data and framework.

## 12. EXPLAIN and PROFILE: Verifying Where Resources Are Actually Spent

Tuning should be grounded in plans and metrics. `EXPLAIN` shows the estimated plan without running the query; `PROFILE` **actually executes the query** and reports metrics such as **Rows**, **DB Hits**, and runtime-dependent memory/timing details.

Example inspecting row inflation:

```cypher
PROFILE
MATCH (u:OptDemoUser)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
OPTIONAL MATCH (a)-[:OPT_DEMO_TAGGED]->(t:OptDemoTag)
OPTIONAL MATCH (a)-[:OPT_DEMO_HAS_COMMENT]->(c:OptDemoComment)
RETURN u.userId AS userId,
       a.articleId AS articleId,
       collect(DISTINCT t.name) AS tags,
       collect(DISTINCT c.commentId) AS comments;
```

On the test dataset, the plan must process matches generated by both tag and comment branches; grouping by `u.userId, a.articleId` brings the final output back to **3 rows**. During execution, intermediate rows before aggregation can be **13**, while post-aggregation rows are **3**. Inspect `Expand`/`Optional`/`Aggregation` operators directly to confirm, as exact plan shapes depend on version and planner.

A query returning only needed fields:

```cypher
PROFILE
MATCH (a:OptDemoArticle)
WHERE a.published = true
RETURN a.articleId AS articleId,
       a.title AS title
ORDER BY a.publishedAt DESC, a.articleId ASC
LIMIT 2;
```

In the plan, watch for `Sort` or `Top`, index access operators, and actual **Rows**. Do not directly compare DB Hits between two queries with **different semantics** and declare one more optimal. To evaluate a rewrite, verify **equivalent business results**, use representative data, and maintain consistent measurement conditions.

### Execution Plan Reading Checklist

| Observation | Question to Answer |
| --- | --- |
| Unusually high `Estimated Rows` | Is the query starting too broadly, or is cardinality blowing up on a relationship branch? |
| Actual `Rows` spike after `Expand` | Are multiple independent branches multiplying before `collect`? |
| `Aggregation` receives many rows and outputs few | Can we count/check existence/collect earlier, or select parent entities first? |
| `Sort`/`Top` | Is this ordering truly required? Can `ORDER BY` be placed after grouping or combined with `LIMIT`? |
| `CartesianProduct` | Are patterns missing shared variables or join predicates? |
| High `DB Hits` | Can we narrow inputs, use a suitable index, or avoid unnecessary relationship traversals? |
| Result returns many properties | Can `RETURN` be slimmed down to a DTO for the current screen? |

**Limitation of `PROFILE`:** it measures work inside the database, not full network bandwidth from Neo4j to the application, JSON serialization cost, JVM object allocation, or UI rendering speed. For large-payload issues, also measure response sizes and end-to-end latency in the application.

## 13. Step-by-Step Optimization Workflow

When encountering a slow query with heavy `collect`, `ORDER BY`, and large payloads, follow this sequence:

1. **Clarify the actual output:** does the screen need the full list or just 20 records? Does it need full nodes, names, IDs, counts, or boolean existence?
2. **Measure the current shape:** run `EXPLAIN` then `PROFILE` on an appropriate read query; inspect intermediate rows, expansion operators, aggregations, and sorts.
3. **Shrink the input:** anchor the query on specific labels/keys, filter early per business semantics, and use indexes where appropriate.
4. **Avoid multiplying independent branches:** replace counting/existence `MATCH`es with `COUNT { ... }`/`EXISTS { ... }`; when two lists are needed, collect each branch separately.
5. **Limit before collecting child relationships:** select top-k articles or parent entities first with `WITH ... ORDER BY ... LIMIT` when only top-k are needed.
6. **Sort once where needed:** before `LIMIT`, after aggregation, or before `collect` if list element order is required.
7. **Shrink the projection:** return only needed fields; avoid `RETURN *`, `RETURN path`, or `collect(node)` unless required.
8. **Paginate and map cleanly:** use `SKIP/LIMIT` or keyset pagination appropriately; have Java Driver/Spring Data Neo4j load only expected results.
9. **Re-measure and compare accurately:** compare business results, **Rows**, DB Hits, memory, database execution time, and application-side response size.

## 14. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "`collect()` returns one row, so it must be lightweight." | One row can contain an enormous list; memory and payload scale with element count. |
| "Just adding `DISTINCT` at the end solves performance." | `DISTINCT` deduplicates final output but does not remove the cost of intermediate combinations already generated. |
| "`LIMIT 10` at the end guarantees only 10 rows are processed." | Prior steps may still read, expand, aggregate, or sort many rows; the planner can stop early only in certain cases. |
| "`ORDER BY` anywhere has the same effect." | Ordering must be placed properly before top-k, after grouping, or right before list collection. |
| "Without `ORDER BY`, data has a stable default order." | Neo4j does not guarantee result order when unspecified. |
| "`RETURN a` is just as light as `RETURN a.articleId`." | Returning a node can ship far more properties than the DTO needs, increasing transfer and processing cost. |
| "Limiting two rows after joining tags means limiting two articles." | Two rows can belong to the same article; limit the parent set before expanding. |
| "`PROFILE` only views the plan." | `PROFILE` executes the query; on write statements, it modifies data. |

## 15. Practice Exercises with the Sample Dataset

**Exercise 1.** Write a Cypher query listing the three most recent published articles, returning only `articleId` and `title`. Order by `publishedAt DESC, articleId ASC`.

**Exercise 2.** Count how many articles each user liked, including users who liked none, returning only `userId` and `likeCount`. Hint: use `OPTIONAL MATCH` and `count(a)`:

```cypher
MATCH (u:OptDemoUser)
OPTIONAL MATCH (u)-[:OPT_DEMO_LIKED]->(a:OptDemoArticle)
RETURN u.userId AS userId, count(a) AS likeCount
ORDER BY userId;
```

Result: `U01 = 2`, `U02 = 1`, `U03 = 0`. If you used `count(*)`, Chi's `OPTIONAL MATCH` row with `a = null` would still count as one row; hence `count(a)` is more accurate.

**Exercise 3.** Fix a query fetching both tags and comments so it does not create a combinatorial product between the two branches. Use `COUNT { ... }` for comment counts if the screen does not need comment contents.

**Exercise 4.** Fetch the newest article for **each** user, including users who have not liked any article. Explain why a global `LIMIT 1` across the entire query fails this requirement.

**Exercise 5.** Run `EXPLAIN` and `PROFILE` for a query returning whole nodes versus one returning only IDs/titles for 2 articles. Record **Rows**, DB Hits, measured time, and application-side payload size. Note which savings come from query execution and which come from data transfer.

## References

- [Neo4j Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/): `collect()`, `count()`, and aggregation behavior.
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/): sorting and ordering guarantees.
- [Neo4j Cypher Manual — LIMIT](https://neo4j.com/docs/cypher-manual/current/clauses/limit/): limiting returned row counts.
- [Neo4j Cypher Manual — Execution plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): reading operators and `EXPLAIN`/`PROFILE` metrics.
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/): query parameters, consuming results, and session lifecycle.

**Takeaway:** optimizing Cypher is not just about making `MATCH` faster. A well-written query **does not materialize large lists when only a count is needed**, **does not sort when ordering is unnecessary**, **limits the right entities before expanding multi-branch relationships**, and **returns only the data the application will actually use**.
