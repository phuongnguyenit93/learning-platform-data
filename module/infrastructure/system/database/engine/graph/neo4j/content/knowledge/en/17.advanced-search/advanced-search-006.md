# Combining Search Results with Graph Filters and Relationships

In Neo4j, finding an article that "matches keywords" is not enough to return results. Applications also need to know whether the article is **published**, **tagged with which topics**, **written by whom**, **whether the searcher follows the author**, and **whether they have permission to view it**. With the **property graph** model, Cypher can receive candidate nodes from a search index and then inspect properties and relationships to decide which articles truly qualify.

This lesson belongs to the **Advanced Search** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. We will combine **full-text search**, `WHERE` conditions, `MATCH`/`EXISTS` relationship checks, ranking, pagination, and authorization. The extension section introduces **vector search** and how to integrate queries using the Java Driver or Spring Data Neo4j.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **candidate retrieval** from a search index from **candidate filtering** using graph properties and relationships.
2. Create a full-text index and use `db.index.fulltext.queryNodes` to retrieve nodes along with their relevance `score`.
3. Apply `EXISTS { MATCH ... }` for topics, followers, and access permissions without accidentally multiplying result rows.
4. Rank and paginate properly; explain why an early `LIMIT` can omit valid results.
5. Incorporate graph signals into ranking, recognize vector top-k limitations, and check performance with `EXPLAIN`/`PROFILE`.

## 2. Problem: Finding Articles Relevant to a User

Consider this knowledge graph:

~~~text
(:User)-[:FOLLOWS]->(:Author)-[:WROTE]->(:Article)
   |                                        |
   +--[:MEMBER_OF]->(:Workspace)<-[:VISIBLE_IN]-+
                                            |
                                            +--[:TAGGED_WITH]->(:Tag)
~~~

- `Article` has `articleId`, `title`, `body`, `status`, and `publishedAt`.
- `User` is the searcher; `Author` is the writer; `FOLLOWS` represents a user following an author.
- `TAGGED_WITH` links articles to topics; `MEMBER_OF` and `VISIBLE_IN` control view permissions via workspaces.

Business requirement:

> Find articles containing content about "Neo4j", published since March 2026, tagged `neo4j`, written by an author I follow, and belonging to a workspace I am a member of. Sort by relevance.

| Criterion | Corresponding Operation |
| --- | --- |
| Content matches keywords | Full-text index on `title` and `body` |
| Published, within date range | `WHERE a.status = ... AND a.publishedAt >= ...` |
| Article has the required tag | `EXISTS { MATCH (a)-[:TAGGED_WITH]->(:Tag) }` |
| Author is followed by the user | `EXISTS { MATCH (me)-[:FOLLOWS]->(:Author)-[:WROTE]->(a) }` |
| User has permission to view the article | `EXISTS { MATCH (me)-[:MEMBER_OF]->(w)<-[:VISIBLE_IN]-(a) }` |
| Rank useful results first | `ORDER BY score DESC`, with a secondary tie-breaker key |

**Principle:** search supplies **relevant candidates**; graph conditions determine **eligible candidates**. A high search `score` never substitutes for an access-control check.

~~~mermaid
flowchart TD
    A["Enter keywords"] --> B["Full-text index: node, score"]
    B --> C["Filter status and date"]
    C --> D["Check tag, author, permissions via EXISTS"]
    D --> E["Rank with tie-breaker key"]
    E --> F["LIMIT and pagination"]
    F --> G["Return authorized content"]
~~~

## 3. Preparing the Practice Graph

The examples use **Neo4j 5** syntax on a dedicated practice database. In real applications, create uniqueness constraints on identifiers such as `userId`, `articleId`, and `workspaceId`. `MERGE` in the example avoids duplicates when re-running, but does not replace proper data-integrity design.

Create the user, follow relationship, and workspace membership:

~~~cypher
MERGE (me:User {userId: 'u1'})
MERGE (alice:Author {authorId: 'alice'})
MERGE (engineering:Workspace {workspaceId: 'engineering'})
MERGE (me)-[:FOLLOWS]->(alice)
MERGE (me)-[:MEMBER_OF]->(engineering);
~~~

Create five articles and their corresponding relationships:

~~~cypher
UNWIND [
  {
    articleId: 'A01', title: 'Searching Neo4j with Cypher',
    body: 'Combining full-text indexes with graph relationships',
    authorId: 'alice', workspaceId: 'engineering',
    tag: 'neo4j', status: 'PUBLISHED',
    publishedAt: date('2026-03-10')
  },
  {
    articleId: 'A02', title: 'Neo4j and Vector Search',
    body: 'Searching embeddings in a graph database',
    authorId: 'alice', workspaceId: 'engineering',
    tag: 'neo4j', status: 'DRAFT',
    publishedAt: date('2026-03-11')
  },
  {
    articleId: 'A03', title: 'Optimizing Neo4j Queries',
    body: 'Using PROFILE to measure Cypher cost',
    authorId: 'bob', workspaceId: 'engineering',
    tag: 'neo4j', status: 'PUBLISHED',
    publishedAt: date('2026-03-12')
  },
  {
    articleId: 'A04', title: 'Neo4j and Data Security',
    body: 'Search authorization by workspace',
    authorId: 'alice', workspaceId: 'confidential',
    tag: 'neo4j', status: 'PUBLISHED',
    publishedAt: date('2026-03-13')
  },
  {
    articleId: 'A05', title: 'Integrating Neo4j with Java Driver',
    body: 'Application connecting Cypher in Java',
    authorId: 'alice', workspaceId: 'engineering',
    tag: 'java', status: 'PUBLISHED',
    publishedAt: date('2026-03-14')
  }
] AS row
MERGE (a:Article {articleId: row.articleId})
SET a.title = row.title,
    a.body = row.body,
    a.status = row.status,
    a.publishedAt = row.publishedAt
MERGE (author:Author {authorId: row.authorId})
MERGE (w:Workspace {workspaceId: row.workspaceId})
MERGE (tag:Tag {name: row.tag})
MERGE (author)-[:WROTE]->(a)
MERGE (a)-[:VISIBLE_IN]->(w)
MERGE (a)-[:TAGGED_WITH]->(tag)
RETURN a.articleId AS articleId
ORDER BY articleId;
~~~

| Article | Author | Status | Workspace | Tag |
|---|---|---|---|---|
| A01 | alice | PUBLISHED | engineering | neo4j |
| A02 | alice | DRAFT | engineering | neo4j |
| A03 | bob | PUBLISHED | engineering | neo4j |
| A04 | alice | PUBLISHED | confidential | neo4j |
| A05 | alice | PUBLISHED | engineering | java |

User `u1` follows `alice` and is a member only of `engineering`. According to the requirement in Section 2, the fully filtered result must be **A01**. The remaining articles all contain "Neo4j" yet fail at least one condition.

## 4. Retrieving Candidates from the Full-Text Index

### 4.1. Creating the Index and Checking Status

~~~cypher
CREATE FULLTEXT INDEX article_text_search IF NOT EXISTS
FOR (a:Article) ON EACH [a.title, a.body];
~~~

A full-text index uses an analyzer to process text and compute relevance. It differs from range/text indexes meant for property predicates. In Neo4j 5, querying a full-text index and retrieving `score` is typically performed via a procedure; `WHERE a.body CONTAINS 'Neo4j'` has its own string-matching semantics and does not return a full-text index `score`.

~~~cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties
WHERE name = 'article_text_search'
RETURN name, type, state, labelsOrTypes, properties;
~~~

A newly created index may be in `POPULATING` state. Wait until it reaches `ONLINE` before querying it; if `FAILED`, inspect error details and configuration before benchmarking performance.

### 4.2. Querying Full-Text

~~~cypher
CALL db.index.fulltext.queryNodes(
  'article_text_search',
  'Neo4j'
)
YIELD node, score
RETURN node.articleId AS articleId,
       node.title AS title,
       score AS textScore
ORDER BY textScore DESC, articleId ASC;
~~~

`node` is the matched node; `score` is the relevance calculated by the full-text engine. Values depend on text, analyzer, query syntax, and index statistics: **do not predict fixed numerical scores** per article. Search syntax can support Lucene operators, parentheses, phrases, and special characters; therefore, user input must be processed according to the search capabilities the application intends to allow.

Notes:

- Full-text search analyzes words/terms; it is not equivalent to `=` string equality or `CONTAINS` substring checks.
- Scores from different keywords or different indexes do not inherently share a common scale for direct addition or subtraction.
- If the index is configured in **eventually consistent** update mode, newly written data may not appear immediately in searches. Check the update mode when fresh results are required.

## 5. Complete Query: Combining Properties and Relationships

Parameters:

| Parameter | Example | Type |
|---|---|---|
| `$userId` | `'u1'` | String |
| `$searchText` | `'Neo4j'` | String |
| `$fromDate` | `'2026-03-01'` | ISO date string |
| `$tagName` | `'neo4j'` | String |
| `$pageSize` | `20` | Integer |

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search',
  $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND a.publishedAt >= date($fromDate)
  AND EXISTS {
    MATCH (a)-[:TAGGED_WITH]->(:Tag {name: $tagName})
  }
  AND EXISTS {
    MATCH (me)-[:FOLLOWS]->(:Author)-[:WROTE]->(a)
  }
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt,
       score AS textScore
ORDER BY textScore DESC, articleId ASC
LIMIT $pageSize;
~~~

With the sample data and parameters, the query returns **A01**:

| Article | Why Kept or Excluded |
|---|---|
| A01 | Kept: published, matching tag, followed author, valid workspace |
| A02 | Excluded: `status = 'DRAFT'` |
| A03 | Excluded: author `bob` is not followed by `u1` |
| A04 | Excluded: `u1` is not a member of `confidential` |
| A05 | Excluded: tag is `java`, not `neo4j` |

The initial `MATCH` finds the requesting user; the full-text procedure yields candidates; `WITH` aliases `node` as `a` and carries `score` forward; predicates check properties and relationships before sorting and limiting.

### Why Use `EXISTS { MATCH ... }`?

`EXISTS` returns a boolean: **does at least one path matching the pattern exist?** Because it only filters, each full-text candidate is not multiplied into extra rows when multiple matching relationships exist.

For example, suppose an article has 4 tags and is visible in 3 workspaces. Using two `MATCH` clauses to expand all tags and workspaces could produce `4 × 3 = 12` rows for the same article, causing duplicate results or broken pagination. Two independent `EXISTS` checks answering "does it have the required tag?" and "is there a shared workspace?" still leave a single row per candidate when both hold.

~~~cypher
// May produce multiple rows per Article.
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
) YIELD node, score
MATCH (node)-[:TAGGED_WITH]->(tag:Tag)
RETURN node.articleId AS articleId, tag.name AS tag, score;
~~~

~~~cypher
// Checks condition without multiplying rows across tags.
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
) YIELD node, score
WHERE EXISTS {
  MATCH (node)-[:TAGGED_WITH]->(:Tag {name: $tagName})
}
RETURN node.articleId AS articleId, score;
~~~

If you need to **display the list of tags**, aggregate `collect(DISTINCT tag.name)` after determining the authorized articles rather than expanding tags before pagination.

### Access Permissions Are a Mandatory Condition

The illustrative rule in this lesson is: a user can view an Article if there exists **at least one shared workspace** with that Article.

~~~cypher
EXISTS {
  MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
}
~~~

Real systems may have roles, groups, deny rules, membership statuses, time-bound validity, or organization tiers. In those cases, express **the complete permission policy** in the server-side query. Never return unauthorized nodes from the API and merely hide them in the frontend; the data would already have been sent to the user.

## 6. Filter Order, Ranking, and `LIMIT`

A common mistake: fetching the top 10 most relevant full-text articles **first**, and only then checking status, tags, or permissions:

~~~cypher
CALL db.index.fulltext.queryNodes(
  'article_text_search',
  $searchText,
  {limit: 10}
)
YIELD node, score
WITH node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (a)-[:TAGGED_WITH]->(:Tag {name: $tagName})
  }
RETURN a.articleId AS articleId, score
ORDER BY score DESC;
~~~

Among the first 10 candidates, several might be drafts, have the wrong tag, or be unauthorized for the user. After filtering, fewer than 10 results may remain **even though more valid articles exist further down**. The snippet above also omits permission and author checks, so it must not be used to satisfy the requirement in Section 2.

When the requirement is "up to 10 **valid** articles with the highest `score`", apply all mandatory filters before `LIMIT`:

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND a.publishedAt >= date($fromDate)
  AND EXISTS {
    MATCH (a)-[:TAGGED_WITH]->(:Tag {name: $tagName})
  }
  AND EXISTS {
    MATCH (me)-[:FOLLOWS]->(:Author)-[:WROTE]->(a)
  }
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId, score
ORDER BY score DESC, articleId ASC
LIMIT 10;
~~~

**Performance trade-off:** if a keyword is very common, the full-text index can generate many candidates for Cypher to verify relationships on. Fetching a larger candidate pool (*over-fetch*) and then filtering can reduce latency at scale, but **cannot guarantee** finding the full valid top-k if the candidate set is truncated too early. Design must measure both **post-filter recall** and execution cost; every approach must keep server-side permission checks intact.

## 7. Graph Signals Can Participate in Ranking

In another feature, "following the author" might be a **soft preference** rather than a hard filter. The example below keeps all viewable articles and boosts the score of articles written by authors the user follows:

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
WITH a, me, score,
     CASE
       WHEN EXISTS {
         MATCH (me)-[:FOLLOWS]->(:Author)-[:WROTE]->(a)
       }
       THEN 0.2
       ELSE 0.0
     END AS followBoost
WITH a, score, followBoost,
     score + followBoost AS finalScore
RETURN a.articleId AS articleId,
       score AS textScore,
       followBoost,
       finalScore
ORDER BY finalScore DESC, articleId ASC
LIMIT 20;
~~~

This query can show articles by **unfollowed** authors if they are authorized. Conversely, when the product requires **only** articles by followed authors, enforce `FOLLOWS` with `EXISTS` inside `WHERE` as in Section 5.

The `0.2` boost is illustrative only. Full-text `score` is not necessarily bounded to `[0, 1]`, so evaluate score distributions, ranking quality, and business parameters before choosing real weights. Interaction signals or likes must also be aggregated **at the Article unit** to avoid multiplying rows across relationships.

### Displaying Tags After Determining the Page

When returning the tag list as well, aggregate **after limiting the valid Article list**:

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
WITH a, score
ORDER BY score DESC, a.articleId ASC
LIMIT 10
CALL (a) {
  OPTIONAL MATCH (a)-[:TAGGED_WITH]->(tag:Tag)
  RETURN collect(DISTINCT tag.name) AS tags
}
RETURN a.articleId AS articleId,
       a.title AS title,
       score, tags
ORDER BY score DESC, articleId ASC;
~~~

The `CALL (a) { ... }` subquery uses the variable import syntax introduced in **Neo4j 5.23+**. Older Neo4j 5 versions can use `CALL { WITH a ... }` where subqueries are supported. `OPTIONAL MATCH` and `collect(...)` return the tag list while keeping one row per Article. This example only filters **status and permissions** to highlight tag retrieval; to enforce all requirements from Section 2, add tag, author, and date filters **before `LIMIT`**.

## 8. Pagination and Deterministic Ordering

Multiple articles can share the same `score`. `ORDER BY score DESC` alone leaves tie order undefined; add a stable tie-breaker key, such as `articleId` backed by a **uniqueness constraint**.

~~~cypher
// End of a pipeline that already has a and score.
RETURN a.articleId AS articleId,
       a.title AS title,
       score
ORDER BY score DESC, articleId ASC
SKIP $offset
LIMIT $pageSize;
~~~

`$offset` and `$pageSize` should be non-negative integers, and the application should cap page size. Even with a tie-breaker key, pages fetched at **different points in time** can shift when articles, relationships, or search scores change. Deep `SKIP` offsets also skip over many rows; large systems should consider cursors, session-scoped search snapshots, or pagination mechanisms suited to their consistency requirements.

## 9. Extension: Vector Search with Graph Relationships

Neo4j 5 supports **vector indexes** in suitable versions to find nodes whose embeddings are close to a query vector. Full-text search relies on words/terms; vector search targets **semantic** similarity from an embedding model. Both return candidates and **both must undergo status, relationship, and permission checks** before being exposed via an API.

Example creating an index for **3-dimensional** vectors used in practice (not production embeddings):

~~~cypher
CREATE VECTOR INDEX article_embedding_idx IF NOT EXISTS
FOR (a:Article) ON (a.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 3,
  `vector.similarity_function`: 'cosine'
}};
~~~

Both configuration keys above use backticks per Cypher syntax. Index size must match the dimensionality of the embeddings in use.

~~~cypher
UNWIND [
  {id: 'A01', v: [1.0, 0.1, 0.0]},
  {id: 'A02', v: [0.9, 0.2, 0.0]},
  {id: 'A03', v: [0.8, 0.1, 0.3]},
  {id: 'A04', v: [0.7, 0.1, 0.4]},
  {id: 'A05', v: [0.6, 0.5, 0.1]}
] AS row
MATCH (a:Article {articleId: row.id})
SET a.embedding = row.v;
~~~

Once the index is `ONLINE`, query nearest vectors:

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.vector.queryNodes(
  'article_embedding_idx',
  $k,
  $queryEmbedding
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId,
       a.title AS title,
       score AS vectorScore
ORDER BY vectorScore DESC, articleId ASC;
~~~

With the sample data, `$queryEmbedding = [1.0, 0.0, 0.0]` and `$k = 5` merely test the mechanism; they do not represent text-learned embeddings. Vectors must contain numbers matching the index dimensionality and similarity metric.

**The top-k trap:** the vector procedure fetches `k` nearest candidates **before** Cypher checks workspace permissions. After filtering, fewer than `k` articles may remain, even though other valid articles lie outside that initial candidate set. Increasing `k` can improve recall, but increases cost and still does not guarantee exact top-k over the entire authorized set; vector search can also be approximate.

For **hybrid search** (full-text + vector), you can combine two ranked lists using techniques such as *reciprocal rank fusion* or validated score normalization. Never add `textScore + vectorScore` directly without understanding the two scales. In all cases, never leak data, counts, or sensitive snippets from candidates that fail permission checks.

## 10. Verifying Indexes and Performance

### 10.1. Choosing Structures Matched to the Query

| Need | Choice |
|---|---|
| Search words/terms in title and body | **Full-text index** with query procedure |
| Filter status, date, or property values | **Range index** when filter patterns fit |
| Look up `User` by `userId` or `Article` by `articleId` | Appropriate uniqueness constraint / index |
| Follow author, tag, workspace | Relationship traversal and `EXISTS` |
| Search by embedding proximity | **Vector index** |
| Sort by score and paginate | `ORDER BY`, tie-breaker key, inspect `Sort`/`Top` |

Indexes do not replace designing relationship direction and query cardinality. Even a good full-text index can be slow if every candidate expands thousands of unnecessary branches; likewise, a range index on `status` does not solve content relevance ranking.

### 10.2. `EXPLAIN` and `PROFILE`

~~~cypher
EXPLAIN
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId, score
ORDER BY score DESC, articleId ASC
LIMIT 20;
~~~

~~~cypher
PROFILE
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes(
  'article_text_search', $searchText
)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId, score
ORDER BY score DESC, articleId ASC
LIMIT 20;
~~~

When reading plans, watch:

1. **Rows**: how many candidates come from full-text search and how many remain after filtering? Does any `MATCH` step unexpectedly inflate row counts?
2. **DB Hits**: are too many nodes/relationships inspected per candidate?
3. **Subquery / existence check operators**: row counts and cost where workspace, author, and tag checks execute.
4. **Sort/Top**: what extra cost does sorting by `score`, graph signals, and tie-breakers add?

`EXPLAIN` only shows the estimated plan; `PROFILE` executes the query to measure metrics. Operator names and optimizer strategies vary across Neo4j versions. Never draw conclusions from a handful of sample nodes: benchmark on representative data, diverse keywords, multiple workspaces, and realistic relationship distributions.

### 10.3. Principles for Effective Optimization

- **Filter with `EXISTS` when you only need existence checks**; use `MATCH` expansion only when you genuinely need the extra nodes or relationships.
- **Return only needed properties** for result lists; avoid sending entire `body` or `embedding` fields if the UI does not need them.
- **Guarantee unique identifiers** with constraints; do not assume data is clean just because sample queries showed no duplicates.
- **Apply eligibility criteria before truncating candidates**: top-k after permission filtering may differ from index top-k.
- **Measure on realistic data**: 5 practice articles do not reflect cost when article and relationship counts are large.
- **Keep permission checks server-side** in all cases, including when optimizing queries and caching results.

## 11. Integrating with Java Driver and Spring Data Neo4j

Applications can pass `userId`, keywords, dates, and tags as **Neo4j Java Driver** parameters, avoiding direct interpolation into Cypher syntax:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;

// Driver is initialized and lifecycle-managed by the application.
String cypher = """
    MATCH (me:User {userId: $userId})
    CALL db.index.fulltext.queryNodes('article_text_search', $searchText)
    YIELD node, score
    WITH me, node AS a, score
    WHERE a.status = 'PUBLISHED'
      AND a.publishedAt >= date($fromDate)
      AND EXISTS {
        MATCH (a)-[:TAGGED_WITH]->(:Tag {name: $tagName})
      }
      AND EXISTS {
        MATCH (me)-[:FOLLOWS]->(:Author)-[:WROTE]->(a)
      }
      AND EXISTS {
        MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
      }
    RETURN a.articleId AS id, a.title AS title, score
    ORDER BY score DESC, id ASC
    LIMIT $pageSize
    """;

Map<String, Object> params = Map.of(
    "userId", "u1",
    "searchText", "Neo4j",
    "fromDate", "2026-03-01",
    "tagName", "neo4j",
    "pageSize", 20
);

try (Session session = driver.session()) {
    var articles = session.executeRead(tx ->
        tx.run(cypher, params)
          .list((Record row) -> Map.of(
              "id", row.get("id").asString(),
              "title", row.get("title").asString(),
              "score", row.get("score").asDouble()
          ))
    );
    articles.forEach(System.out::println);
}
~~~

This example uses Java text blocks (Java 15+) and an existing `Driver`. In production, configure the target database, transaction timeout, and connection/session management per your architecture. `executeRead` is appropriate for read queries. With **Spring Data Neo4j**, you can place the same Cypher in a repository `@Query` method or use `Neo4jClient` to bind parameters.

**Distinguish two query safety layers:** passing `$searchText` as a parameter prevents **Cypher** injection, yet its contents are still parsed by **Lucene** as a full-text query. If the application only intends simple keywords, specify escaping/sanitization rules for special characters; if advanced operators are allowed, cap query length and complexity. The current user must be authenticated server-side; never trust a self-declared `userId` from an untrusted request as the sole basis for authorization.

## 12. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Unauthorized articles returned | Filtered only in frontend or relied on `score` | Enforce relationship permissions in server-side Cypher |
| Same Article appears multiple times | Expanded multiple tags/workspaces with `MATCH` | Use `EXISTS` to filter or aggregate per Article |
| Page returns fewer articles despite valid matches existing | Candidate pool truncated too early | Apply `LIMIT` after mandatory filters; measure recall |
| `CONTAINS` query has no `score` | Did not call full-text procedure | Use full-text when text relevance ranking is needed |
| New articles do not appear yet | Index not `ONLINE` or eventual consistency enabled | Check index status/configuration |
| Unstable pagination | Tied `score` values or changing data | Add a tie-breaker key and a consistency strategy |
| Combining vector and text gives hard-to-explain scores | Two scores use different scales | Use normalization or rank fusion |
| High latency | Too many candidates and traversals | Run `PROFILE`, eliminate row multiplication, review model |

## 13. Exercises

### Exercise 1: Filter Only Status and Permissions

Find articles containing "Neo4j", published, and visible in a workspace the user belongs to, **without requiring** a specific tag or followed author.

**Reference solution:**

~~~cypher
MATCH (me:User {userId: $userId})
CALL db.index.fulltext.queryNodes('article_text_search', $query)
YIELD node, score
WITH me, node AS a, score
WHERE a.status = 'PUBLISHED'
  AND EXISTS {
    MATCH (me)-[:MEMBER_OF]->(w:Workspace)<-[:VISIBLE_IN]-(a)
  }
RETURN a.articleId AS articleId, a.title AS title, score
ORDER BY score DESC, articleId ASC;
~~~

With `$userId = 'u1'` and `$query = 'Neo4j'`, the sample data returns A01, A03, and A05 (ordered by actual scores).

### Exercise 2: Limiting Too Early

A vector query retrieves top-5, then filters permissions and only 2 articles remain. Can you conclude there are only 2 valid articles?

**Hint:** No. Those two results only came from the **first 5 candidates**. Other valid articles may lie outside the vector top-5 set. Try increasing candidate count and measuring recall; never skip permission checks.

### Exercise 3: Counting Rows

An Article has 4 tags and appears in 3 workspaces. How many rows can a query produce for that same Article if it expands both branches before `RETURN a, score`?

**Answer:** `4 × 3 = 12` rows if both branches match fully. For filtering, use `EXISTS`; when list details are needed, aggregate separately per Article.

### Exercise 4: Distinguishing Mandatory Filters from Preference Signals

Design a search with the rule: "the user must have view permission; prefer articles by followed authors, but still allow other articles."

**Hint:** Permission is a mandatory `WHERE EXISTS`; `FOLLOWS` acts as a score boost inside `CASE WHEN EXISTS`. Sort by final score with a tie-breaker key, then apply `LIMIT`. If the requirement changes to "only articles by followed authors", move `FOLLOWS` into the mandatory filter conditions.

## 14. Remember

- **Full-text or vector search finds candidates; Cypher combines properties and relationships to determine valid results.**
- **Permission checks are mandatory at the server**, not a ranking signal or frontend-only logic.
- **`EXISTS { MATCH ... }` filters by relationship existence**, preventing row multiplication across multiple links.
- **Applying `LIMIT` too early can drop valid articles outside the truncated candidate set.**
- **Search scores can incorporate graph signals**, provided score scales, tie-breaking order, and cross-page drift are controlled.
- **Use `SHOW INDEXES`, `EXPLAIN`, and `PROFILE`** to evaluate plans, intermediate row counts, costs, and recall on representative data.
