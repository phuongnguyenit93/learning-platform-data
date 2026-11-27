# Pagination, Data Loading, and Identifying Unnecessary Repeated Queries

## 1. Why Is Paginating a Graph Different from Paginating a Table?

An API built with Spring Data Neo4j (SDN) frequently returns lists of objects such as articles, customers, products, or orders. In a property graph, each root node can connect to many other nodes via relationships: an `Article` has many `Tag` nodes, a `Customer` has many `Order` nodes, and a `Product` has many reviews. Loading all relationships for every result can cause payloads and intermediate data volume to explode.

For example, an admin screen wants to display **10 articles per page**, each showing its title, publication date, and tag count. Three traps arise:

- A Cypher query that paginates **rows after expanding relationships** can return fewer than 10 distinct articles.
- A query fetching full entities and deep relationships can pull thousands of nodes/relationships even though the UI only needs a few fields.
- A service calling a repository separately to look up tags **for each article** can trigger the `1 + N` repeated query pattern (commonly called the *N+1 query problem*).

This lesson belongs to the **Spring Data Neo4j** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. We use `Pageable`, `Page`, `Slice`, Cypher queries, `Neo4jClient`, `EXPLAIN`, and `PROFILE` to paginate **root nodes** accurately, load only the needed data, detect duplicate queries, and balance round trips against graph processing cost.

**After this lesson, you will be able to:**

1. Choose between `Page<T>`, `Slice<T>`, and `List<T>` based on API requirements.
2. Guarantee deterministic pagination using `ORDER BY` and a unique node tie-breaker.
3. Understand the limits of `@Relationship` and how custom queries affect entity mapping.
4. Spot N+1 issues caused by service/repository code, graph hydration queries, and Cartesian products.
5. Write queries applying `WITH … SKIP … LIMIT` **before** expanding relationships.
6. Measure Cypher query counts, `Rows`, `DB Hits`, memory, query latency, and correctness against a small dataset with known answers.

> **Technology scope:** Examples target Neo4j 5+ and Spring Data Neo4j 7.x/8.x following Spring Data Commons APIs. Verify annotation signatures and mapping capabilities against the actual Spring Boot/SDN versions in your project. Practice numbers represent **logical answers**, not measured Neo4j performance benchmarks.

## 2. Three Questions to Answer Before Writing a Repository

| Question | Good choice when | Risk if ignored |
|---|---|---|
| **What are we paginating?** | Each API item is a root node, e.g. one `Article` | Paginating relationship rows makes one article occupy multiple slots |
| **Which fields does the screen need?** | Fetch only `id`, `title`, `publishedAt`, and tag count for list views | Fetching the whole graph and mapping entities that are never displayed |
| **Is an exact total required?** | Use `Page` when the UI must display `totalElements`/`totalPages` | Extra COUNT queries add cost and latency |

Never paginate by calling `findAll()` and then `stream().skip(...).limit(...)` in Java. That forces loading every object and relationship and filtering **after the server returns all data**. Pagination must happen inside Cypher/the database, or via SDN-generated queries using `Pageable`.

### 2.1. Page Loading Structure

~~~mermaid
flowchart TD
  A["HTTP GET /articles?page=0&size=2"] --> B["Service validates page/size/sort"]
  B --> C["Repository / Neo4jClient"]
  C --> D["Cypher: filter and sort root nodes"]
  D --> E["SKIP / LIMIT on root list"]
  E --> F["Fetch only properties / relationships needed for page"]
  F --> G["DTO + Page/Slice metadata"]
  G --> H["Return bounded response"]
~~~

Remember: **filter → sort → limit root nodes → load relationships** yields completely different results from **expand relationships → sort → limit rows**.

## 3. `Page`, `Slice`, `List`, and `Pageable`

Spring Data Commons provides these common return types:

| Return type | What it provides | When appropriate | Cost to watch |
|---|---|---|---|
| `Page<T>` | Content, current page, total elements/pages, `hasNext` | Screens requiring exact page numbers or total counts | Usually requires an extra **count query**; the framework may optimize it away in a few cases |
| `Slice<T>` | Content, page number, and `hasNext`, **no exact total** | "Load more" buttons, infinite scroll | Usually avoids count; typically fetches one extra item to detect whether a next page exists |
| `List<T>` with `Pageable` | Only the slice of items for the page | APIs managing pagination metadata themselves or needing top-N only | No built-in pagination metadata or automatic total |
| `Stream<T>` | Streams results incrementally where supported | Sequential processing of large result sets | Must manage stream/transaction lifecycle carefully; never expose as an unbounded API |

`PageRequest.of(0, 20)` requests **the first page** because page indices are zero-based. `size` is the maximum number of elements per page—not relationship depth or post-expansion row count.

Example:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    0, 2,
    Sort.by(Sort.Order.desc("publishedAt"),
            Sort.Order.asc("articleId"))
);

Page<Article> page = articleRepository.findByStatus(
    "PUBLISHED", pageable
);
~~~

Assume the `Article` entity and repository declared in Section 6. This is a *derived query*: SDN generates the Cypher corresponding to the repository method. To evaluate performance, inspect the **actual generated Cypher**, not just the Java method signature.

**Count distinction:** When using `Page`, the infrastructure often needs a `COUNT` query to compute total elements. If the UI only needs a "Load more" button, `Slice` avoids the COUNT query. Do not assume every `Page` call always executes exactly two queries: SDN/Spring Data optimizations and entity hydration behavior can alter query counts.

## 4. Sorting Must Be Deterministic, Otherwise Items Duplicate or Disappear

Cypher **guarantees no ordering** without `ORDER BY`. Even `ORDER BY publishedAt DESC` remains non-deterministic when multiple articles share the same publication date. Always include a **tie-breaker**, such as `articleId ASC` backed by a unique constraint.

~~~cypher
MATCH (a:QA010Article {status: 'PUBLISHED'})
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP 0 LIMIT 2;
~~~

To fetch the next page:

~~~cypher
MATCH (a:QA010Article {status: 'PUBLISHED'})
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP 2 LIMIT 2;
~~~

Without a unique tie-breaker, nodes sharing the same `publishedAt` can swap positions across executions, causing duplicates or missing records across pages.

**Important:** deterministic `ORDER BY` does not create a snapshot across separate requests. If new articles are added or `publishedAt`/`status` changes between page requests, offsets can shift. When consistent traversal over longer intervals is needed, consider cursor/keyset pagination or application-level snapshots.

## 5. Fixture: Six Articles, Three Authors, and Tags

Use a **dedicated test database**. This lesson prefixes labels and relationships with `QA010` to avoid interfering with other lessons.

### 5.1. Answer Key Table

| Article ID | Title | Published date | Status | Tags |
|---|---|---|---|---|
| A001 | Neo4j Index | 2026-10-06 | PUBLISHED | java, neo4j |
| A002 | Cypher Basics | 2026-10-05 | PUBLISHED | neo4j |
| A003 | Java Driver | 2026-10-05 | PUBLISHED | java, performance |
| A004 | Tuning Graph | 2026-10-04 | PUBLISHED | performance |
| A005 | Spring Data Neo4j | 2026-10-03 | PUBLISHED | *(none)* |
| A006 | Internal Draft | 2026-10-07 | DRAFT | java |

The five `PUBLISHED` articles must come back in order **A001, A002, A003, A004, A005**. A002 and A003 share the **same date**, testing the tie-breaker. A006 has a newer date but is excluded because its status is `DRAFT`.

### 5.2. Creating the Data in Neo4j Browser / cypher-shell

Only clean fixture data if you are certain this is a test database with no other system sharing these labels:

~~~cypher
DROP CONSTRAINT qa010_article_id_unique IF EXISTS;
~~~

~~~cypher
MATCH (n)
WHERE n:QA010Article OR n:QA010Author OR n:QA010Tag
DETACH DELETE n;
~~~

Create a unique constraint on the identifying key:

~~~cypher
CREATE CONSTRAINT qa010_article_id_unique IF NOT EXISTS
FOR (a:QA010Article)
REQUIRE a.articleId IS UNIQUE;
~~~

Create the six articles:

~~~cypher
UNWIND [
  {id:'A001', title:'Neo4j Index',
   published:'2026-10-06', state:'PUBLISHED'},
  {id:'A002', title:'Cypher Basics',
   published:'2026-10-05', state:'PUBLISHED'},
  {id:'A003', title:'Java Driver',
   published:'2026-10-05', state:'PUBLISHED'},
  {id:'A004', title:'Tuning Graph',
   published:'2026-10-04', state:'PUBLISHED'},
  {id:'A005', title:'Spring Data Neo4j',
   published:'2026-10-03', state:'PUBLISHED'},
  {id:'A006', title:'Internal Draft',
   published:'2026-10-07', state:'DRAFT'}
] AS row
CREATE (:QA010Article {
  articleId: row.id,
  title: row.title,
  publishedAt: date(row.published),
  status: row.state
});
~~~

Create three authors and three tags:

~~~cypher
UNWIND [
  {id:'U01', name:'An'},
  {id:'U02', name:'Binh'},
  {id:'U03', name:'Chi'}
] AS row
CREATE (:QA010Author {authorId:row.id, displayName:row.name});
~~~

~~~cypher
UNWIND ['java','neo4j','performance'] AS tagName
CREATE (:QA010Tag {name:tagName});
~~~

Link tags:

~~~cypher
UNWIND [
  {article:'A001', tag:'java'},
  {article:'A001', tag:'neo4j'},
  {article:'A002', tag:'neo4j'},
  {article:'A003', tag:'java'},
  {article:'A003', tag:'performance'},
  {article:'A004', tag:'performance'},
  {article:'A006', tag:'java'}
] AS link
MATCH (a:QA010Article {articleId:link.article})
MATCH (t:QA010Tag {name:link.tag})
CREATE (a)-[:QA010_HAS_TAG]->(t);
~~~

Link authors:

~~~cypher
UNWIND [
  {article:'A001', author:'U01'},
  {article:'A002', author:'U02'},
  {article:'A003', author:'U01'},
  {article:'A004', author:'U03'},
  {article:'A005', author:'U02'}
] AS link
MATCH (a:QA010Article {articleId:link.article})
MATCH (u:QA010Author {authorId:link.author})
CREATE (a)-[:QA010_WRITTEN_BY]->(u);
~~~

Verify counts:

~~~cypher
MATCH (a:QA010Article)
RETURN count(a) AS allArticles,
       count(CASE WHEN a.status='PUBLISHED' THEN 1 END)
         AS publishedArticles;
~~~

**Answer:** `allArticles = 6` and `publishedArticles = 5`. There are also 3 authors, 3 tags, 7 `QA010_HAS_TAG` relationships, and 5 `QA010_WRITTEN_BY` relationships.

## 6. Using Repositories with `Page` and `Slice`

To illustrate **lightweight** root-node pagination, the `Article` class below maps only the fields needed for a list view and **maps no relationships**. This is a simple read model; real applications may keep full domain entities separately or use `Neo4jClient` returning DTOs.

~~~java
import java.time.LocalDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("QA010Article")
public class Article {
    @Id
    private String articleId;
    private String title;
    private String status;
    private LocalDate publishedAt;

    public Article() {} // Simple example for the mapping mechanism.

    public String getArticleId() { return articleId; }
    public String getTitle() { return title; }
    public String getStatus() { return status; }
    public LocalDate getPublishedAt() { return publishedAt; }
}
~~~

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ArticleRepository
        extends Neo4jRepository<Article, String> {

    Page<Article> findByStatus(String status, Pageable pageable);

    Slice<Article> findSliceByStatus(
        String status, Pageable pageable
    );
}
~~~

Usage:

~~~java
var sorted = PageRequest.of(
    0, 2,
    Sort.by(Sort.Order.desc("publishedAt"),
            Sort.Order.asc("articleId"))
);

Page<Article> firstPage = articleRepository.findByStatus(
    "PUBLISHED", sorted
);

// With fixture: content A001, A002 and totalElements = 5.
System.out.println(firstPage.getTotalElements());
System.out.println(firstPage.hasNext());
~~~

**Expected logical output:** page 0 contains A001, A002; `getTotalElements() = 5`; `hasNext() = true`. Page 1 contains A003, A004; page 2 contains A005 with `hasNext() = false`.

`findSliceByStatus` is an illustrative derived finder name; if your specific Spring Data version does not parse that name as expected, place `Slice<Article> findByStatus(String, Pageable)` in a separate repository or choose a Spring Data–supported finder name and inspect the generated query. Within a single interface, Java forbids overloading **differing only by return type**, which is why the example uses distinct method names.

### Note When the Entity Declares `@Relationship`

If the `Article` class in a real application includes:

~~~java
import java.util.Set;
import org.springframework.data.neo4j.core.schema.Relationship;

// Add to the Article entity if business logic manages this relationship:
@Relationship(type = "QA010_HAS_TAG",
              direction = Relationship.Direction.OUTGOING)
private Set<Tag> tags;
~~~

the cost of repository finders can change dramatically: SDN must populate the entity's relationship set per its mapping metadata. **Never assume SDN uses Hibernate/JPA-style lazy-loading proxies.** SDN may generate queries with pattern comprehensions, map projections, or additional queries for cyclic/complex schemas; exact behavior depends on the model and SDN version.

Consequently, on list endpoints needing only a few fields, never return full entity graphs automatically. Use **projections/read DTOs or custom Cypher** and measure metrics before concluding pagination actually reduced load.

## 7. Custom `@Query`: The Author Controls Paging and Count

When criteria exceed derived queries, use `@Query`.

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ArticleCustomRepository
        extends Neo4jRepository<Article, String> {

    @Query(
      value = """
        MATCH (a:QA010Article)
        WHERE a.status = $status
        RETURN a
        ORDER BY a.publishedAt DESC, a.articleId ASC
        SKIP $skip LIMIT $limit
        """,
      countQuery = """
        MATCH (a:QA010Article)
        WHERE a.status = $status
        RETURN count(a)
        """
    )
    Page<Article> findPageWithQuery(
        @Param("status") String status, Pageable pageable
    );
}
~~~

In SDN versions supporting custom page queries in this style, `$skip` and `$limit` are supplied by the framework from `Pageable`. **Never assume** that merely adding a `Pageable` parameter automatically bounds arbitrary custom Cypher if the query omits `SKIP`/`LIMIT`.

Because ordering is already written in Cypher, invoke with:

~~~java
var page = PageRequest.of(0, 2); // Unsorted Pageable
var result = customRepository.findPageWithQuery(
    "PUBLISHED", page
);
~~~

`countQuery` must apply **the exact same root-node filter** as the data query. If the data query filters for published articles while `countQuery` counts `DRAFT` articles too, `totalElements` and `totalPages` will be wrong.

When using `@Query` to return a `Slice`, `countQuery` is generally unnecessary, though explicit `SKIP/LIMIT` and deterministic ordering remain required. Verify your project's SDN version and actual generated Cypher via query logs, as custom paging support varies across versions.

> **Rule:** On custom `@Query` methods, never assume `Sort` inside `Pageable` merges safely into arbitrary Cypher. When `ORDER BY` is hardcoded in the query, pass an unsorted `Pageable` and test in practice.

## 8. Major Pitfall: Paginating Rows Expanded by Relationships

In our fixture, A001 has 2 tags, A002 has 1 tag, A003 has 2 tags, A004 has 1 tag, and A005 has 0 tags.

### 8.1. Easy-to-Write Query with Broken Semantics

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
OPTIONAL MATCH (a)-[:QA010_HAS_TAG]->(t:QA010Tag)
RETURN a.articleId AS articleId,
       a.publishedAt AS publishedAt,
       t.name AS tag
ORDER BY publishedAt DESC, articleId ASC, tag ASC
SKIP 0 LIMIT 2;
~~~

**Expected first-page output:**

| articleId | tag |
|---|---|
| A001 | java |
| A001 | neo4j |

The query returns **two rows**, yet only **one distinct article**. A002 gets pushed to the next page because A001 occupied two rows due to the one-to-many relationship. When the API contract promises "2 articles per page," this pagination result is wrong even though the Cypher is syntactically valid.

Check the counts:

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
OPTIONAL MATCH (a)-[:QA010_HAS_TAG]->(t:QA010Tag)
RETURN count(*) AS expandedRows,
       count(DISTINCT a) AS uniqueArticles,
       count(t) AS tagMatches;
~~~

**Answer:** `expandedRows = 7`, `uniqueArticles = 5`, `tagMatches = 6`. A005 has zero tags yet still produces **one row** with `t = null` due to `OPTIONAL MATCH`.

If a `countQuery` uses `count(*)` after expansion, the `Page` reports 7 total elements while content expects 5 articles—a bug caused by counting **expanded rows** rather than **root nodes**.

### 8.2. Correct: Paginate Root Nodes First, Expand Relationships Afterward

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
WITH a
ORDER BY a.publishedAt DESC, a.articleId ASC
SKIP 0 LIMIT 2
OPTIONAL MATCH (a)-[:QA010_HAS_TAG]->(t:QA010Tag)
RETURN
  a.articleId AS articleId,
  a.title AS title,
  a.publishedAt AS publishedAt,
  collect(DISTINCT t.name) AS tags
ORDER BY publishedAt DESC, articleId ASC;
~~~

**Answer:**

| articleId | tags (list order not guaranteed) |
|---|---|
| A001 | java, neo4j |
| A002 | neo4j |

Here `WITH a ORDER BY ... SKIP ... LIMIT ...` selects exactly **2 articles** first. `OPTIONAL MATCH` expands relationships only for those two articles. `collect(DISTINCT t.name)` aggregates tags so each article produces **one record**.

With zero tags, `collect(t.name)` skips nulls and returns an empty list. Note that for full SDN entity mapping, collecting only *tag name strings* is not enough to hydrate full relationships; this pattern is best suited for **read DTOs**.

### 8.3. Custom Queries Hydrating Entities Need One Record per Root

When deliberately loading relationships into an SDN entity, for example:

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
WITH a
ORDER BY a.publishedAt DESC, a.articleId ASC
SKIP $skip LIMIT $limit
OPTIONAL MATCH (a)-[rel:QA010_HAS_TAG]->(t:QA010Tag)
RETURN a, collect(rel) AS relationships,
          collect(t) AS relatedNodes;
~~~

The result set after `RETURN` emits **one record per root node** containing the nodes and relationships needed for mapping. This is the shape emphasized by SDN's custom query documentation, yet **matching that shape does not mean the query automatically supplies every relationship** when an entity defines multiple `@Relationship` types or deep paths. Returning an entity while omitting relationships expected by the mapper creates a partial entity; never edit and save a partially loaded entity back as if it represented the whole graph.

**Practical conclusion:** list endpoints should favor DTOs decoupled from write entities and fetch only the relationships needed for display.

## 9. Three Data-Loading Strategies Compared

| Strategy | Typical query count | Strengths | Risks |
|---|---|---|---|
| **Single DTO query** | 1 page query, plus optional count | Fewer round trips, exact fields, easy to control | Large aggregations or expansions can consume server RAM |
| **Two-phase batch** | 1 page query + 1 relationship query for **ID batch** (+ count if needed) | Accurate root paging, avoids repeated queries, clean separation | Must join results by ID and preserve page order |
| **One query per root** | 1 page query + N individual queries (+ count) | Simple service code | N+1 round trips; latency scales linearly with page size |

A single query is not always fastest if it builds a massive Cartesian product. Batched multi-query fetches can outperform it when there are many relationship types, strict field permissions, or a need to load summaries first and hydrate details selectively.

### 9.1. Single DTO Query Fetching Tags for the Entire Page

Use the query from Section 8.2 with `Neo4jClient` and map rows to a read DTO:

~~~java
import java.time.LocalDate;
import java.util.List;

public record ArticleRow(
    String articleId,
    String title,
    LocalDate publishedAt,
    List<String> tags
) {}
~~~

~~~java
import java.util.List;
import org.neo4j.driver.Value;
import org.springframework.data.neo4j.core.Neo4jClient;

public List<ArticleRow> loadSummaries(Neo4jClient client) {
    String cypher = """
        MATCH (a:QA010Article {status:$status})
        WITH a
        ORDER BY a.publishedAt DESC, a.articleId ASC
        SKIP $skip LIMIT $limit
        OPTIONAL MATCH (a)-[:QA010_HAS_TAG]->(t:QA010Tag)
        RETURN a.articleId AS articleId,
               a.title AS title,
               a.publishedAt AS publishedAt,
               collect(DISTINCT t.name) AS tags
        ORDER BY publishedAt DESC, articleId ASC
        """;

    var rows = client.query(cypher)
        .bind("PUBLISHED").to("status")
        .bind(0L).to("skip")
        .bind(2L).to("limit")
        .fetchAs(ArticleRow.class)
        .mappedBy((typeSystem, record) ->
            new ArticleRow(
                record.get("articleId").asString(),
                record.get("title").asString(),
                record.get("publishedAt").asLocalDate(),
                record.get("tags").asList(Value::asString)
            )
        )
        .all();

    return List.copyOf(rows);
}
~~~

This example uses a Java 17 record. `Neo4jClient` integrates with Spring Data Neo4j transaction management, and parameter binding prevents concatenating request inputs into Cypher. In real services, supply `status`/offset/limit from validated service arguments.

To return `Page<ArticleRow>` with an exact total, run a matching `status`-filtered count query and construct page metadata (e.g., via `PageImpl` in the service), or return `Slice` to avoid the count when the UI does not need it.

### 9.2. Two-Phase Fetch: Return Root IDs First, Then Batch-Fetch Relationships

**Phase 1** fetches the exact page of IDs:

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
RETURN a.articleId AS articleId
ORDER BY a.publishedAt DESC, a.articleId ASC
SKIP 0 LIMIT 2;
~~~

Answer: `['A001', 'A002']` in order.

**Phase 2** receives `$ids = ['A001','A002']`:

~~~cypher
UNWIND $ids AS articleId
MATCH (a:QA010Article {articleId:articleId})
OPTIONAL MATCH (a)-[:QA010_HAS_TAG]->(t:QA010Tag)
RETURN articleId, collect(DISTINCT t.name) AS tags;
~~~

This returns one record per article in `$ids` with its tags. **Do not rely on `UNWIND` or aggregation preserving output order**: in Java, build a `Map<String,List<String>>` keyed by `articleId` and iterate over the **Phase 1 ID list** to preserve page order.

If Phase 1 already returned `articleId,title,publishedAt`, Phase 2 only needs relationship data without re-fetching root properties. With multiple relationship types, consider separate batched queries per type or a carefully grouped Cypher query.

## 10. N+1: Not Exclusive to Relational ORMs

In Hibernate-style ORMs, developers associate N+1 with lazy loading. With Spring Data Neo4j, **never assume SDN always lazy-loads every relationship one by one**. SDN mapping is driven by Cypher/record hydration and can fetch relationships in one query or issue multiple queries when models have complex cycles and depth. However, N+1 **still happens** whenever service code issues a per-root query inside a loop.

### 10.1. Example Service Producing N+1

~~~java
Page<Article> page = articleRepository.findByStatus(
    "PUBLISHED", PageRequest.of(
        0, 2,
        Sort.by(Sort.Order.desc("publishedAt"),
                Sort.Order.asc("articleId"))
    )
);

var summaries = page.getContent().stream()
    .map(article -> new ArticleWithTags(
        article.getArticleId(),
        article.getTitle(),
        tagRepository.findNamesByArticleId(
            article.getArticleId()
        )
    ))
    .toList();
~~~

With a secondary repository query:

~~~java
@Query("""
    MATCH (a:QA010Article {articleId:$articleId})
          -[:QA010_HAS_TAG]->(t:QA010Tag)
    RETURN t.name AS name
    ORDER BY name
    """)
List<String> findNamesByArticleId(
    @Param("articleId") String articleId
);
~~~

This issues **1 page query + N tag queries**, plus a **count query** when returning `Page`. With N=2 in the fixture, code issues separate queries for A001 and A002; with `size=100`, it issues 100 tag queries.

Assuming an average sequential round-trip/overhead of 5 ms per extra query, **100 extra queries** already add ~500 ms in round-trip overhead alone, before execution, transfer, and mapping time. This is an **illustrative estimate**, not a Neo4j benchmark measurement.

### 10.2. Why Do Some SDN Designs Still Execute Many Queries?

- Services or mappers invoke repositories or `Neo4jClient` inside a loop.
- Self-referential graph models or cyclic relationships cause an SDN version's hydrator to issue follow-up queries.
- Serializers invoke computed getters that trigger separate queries.
- Endpoints return entities loaded with unneeded relationships, causing "over-fetching" even **without** N+1.

**N+1** and **over-fetching** are distinct: the first scales **round trips with N**, while the second loads **too much data per query**. An endpoint can suffer from both.

### 10.3. Detecting N+1 by Observation

1. Enable query logging/counters in test environments or inspect Neo4j query logs/tracing.
2. Call the API with `size=1,2,5,10` against a sufficiently large dataset.
3. Record **Cypher query count**, repeated query shapes, total records/bytes, and p50/p95 latency.
4. Categorize queries: root fetch, count, relationship hydration, authorization checks, and extra service calls.
5. If auxiliary queries grow roughly linearly with root count and share identical templates differing only by `articleId`, that is a strong N+1 signature.
6. Replace them with a batched **`UNWIND $ids`** query or single DTO query, then re-measure on identical data and concurrency.

**Do not count queries alone:** replacing 101 tiny queries with 1 query that generates a million-row Cartesian product can worsen server RAM and latency. Compare `Rows`, `DB Hits`, `Memory (Bytes)`, response bytes, and p95 latency together.

## 11. Avoiding Cartesian Products with Multiple One-to-Many Relationships

Suppose each `Article` has 20 tags and 30 comments; the buggy query:

~~~cypher
MATCH (a:Article {articleId:$id})
OPTIONAL MATCH (a)-[:HAS_TAG]->(t:Tag)
OPTIONAL MATCH (a)-[:HAS_COMMENT]->(c:Comment)
RETURN a, t, c;
~~~

For an article with 20 tags and 30 comments, two consecutive `OPTIONAL MATCH` clauses generate **20 × 30 = 600 intermediate rows**, repeating tag–comment pairs even though the API only wants two independent lists.

One way to avoid cross-multiplication is **aggregating each branch before expanding the next**:

~~~cypher
MATCH (a:Article {articleId:$id})
OPTIONAL MATCH (a)-[:HAS_TAG]->(t:Tag)
WITH a, collect(DISTINCT t.name) AS tagNames
OPTIONAL MATCH (a)-[:HAS_COMMENT]->(c:Comment)
RETURN a.articleId AS articleId,
       tagNames,
       collect(DISTINCT c.commentId) AS commentIds;
~~~

This is a **conceptual template** for a hypothetical `Article/Tag/Comment` schema, not the `QA010` fixture. When you only need counts, use `count` or subquery aggregations rather than collecting full nodes or comments.

Collecting large sets also consumes memory. When a single article has hundreds of thousands of relationships, **paginate child lists separately** (e.g., comments), cap display sizes, and split detail endpoints. Never return a deep graph merely because Cypher lets you write one query.

## 12. Deep Pagination: `SKIP`/Offset vs. Keyset

Offset pagination:

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
RETURN a.articleId AS articleId,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP $skip LIMIT $limit;
~~~

At `page=1000`, `size=20`, `skip=20000`. To reach deep pages, the database still scans/sorts and skips thousands of matching records even though it returns only 20. On large datasets, latency generally grows with offset depending on planner and index ordering support.

**Keyset/cursor pagination** seeks relative to the previous page's final sort key. With `ORDER BY publishedAt DESC, articleId ASC`, the page after cursor `($lastDate, $lastId)` uses:

~~~cypher
MATCH (a:QA010Article {status:'PUBLISHED'})
WHERE a.publishedAt < date($lastDate)
   OR (a.publishedAt = date($lastDate)
       AND a.articleId > $lastId)
RETURN a.articleId AS articleId,
       a.title AS title,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
LIMIT $limit;
~~~

For example, page 1 returns A001, A002. End-of-page cursor is `lastDate='2026-10-05'`, `lastId='A002'`. The next page starts with **A003**, then **A004** (with `limit=2`). The tie-breaker is mandatory so A003—which shares A002's date—is never skipped.

Notes:

- Initial request without a cursor: omit the cursor `WHERE` predicates while keeping the `status` filter and `ORDER BY`.
- Sort order must be fixed, with stable comparable cursor keys. Data mutating during pagination still requires domain consistency rules.
- Keyset pagination does not inherently provide page numbers or exact totals. It fits infinite feeds and large datasets better than arbitrary "jump to page 500" UIs.
- Pick indexes suited to filters and sort order and inspect `PROFILE` to confirm the planner uses them; never assume any index automatically optimizes arbitrary `OR` predicates.

## 13. Indexes, Count Queries, and Execution Plans

### 13.1. Indexes for Filtering and Sorting

For the fixture, you might consider a RANGE index on status and publication date:

~~~cypher
CREATE RANGE INDEX qa010_article_feed IF NOT EXISTS
FOR (a:QA010Article) ON (a.status, a.publishedAt);
~~~

This is an **illustrative index**. Key ordering and index usage depend on predicates, `ORDER BY`, cardinality, and planner choices; creating this index does not guarantee sorting is eliminated. `articleId` has its own unique constraint for identity; benchmark plans on a sufficiently large dataset to evaluate composite indexes or alternative designs.

Verify:

~~~cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties
WHERE name IN ['qa010_article_feed',
               'qa010_article_id_unique']
RETURN name, type, state, labelsOrTypes, properties;
~~~

Benchmark only after indexes reach `ONLINE`. You can skip creating this index on the six-node fixture since six nodes are too small for meaningful performance tests.

### 13.2. `EXPLAIN` Does Not Execute; `PROFILE` Does

~~~cypher
EXPLAIN
MATCH (a:QA010Article {status:'PUBLISHED'})
RETURN a.articleId AS articleId,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP 0 LIMIT 2;
~~~

~~~cypher
PROFILE
MATCH (a:QA010Article {status:'PUBLISHED'})
RETURN a.articleId AS articleId,
       a.publishedAt AS publishedAt
ORDER BY publishedAt DESC, articleId ASC
SKIP 0 LIMIT 2;
~~~

Record these metrics:

| Plan metric | Interpretation |
|---|---|
| `Rows` | Actual rows emitted per operator; easily reveals inflation from `OPTIONAL MATCH` |
| `Estimated Rows` | Cardinality estimate; large skews can cause suboptimal plans |
| `DB Hits` | Storage-engine work units; not identical to physical disk reads |
| `Memory (Bytes)` | Intermediate memory footprint, especially in `Sort`, `Aggregation`, `collect` |
| `Page Cache Hits/Misses` | Cache residency of data/indexes where supported by edition/runtime |
| `NodeIndexSeek`/`NodeByLabelScan`/`Sort` | Indicates index/scan/sort operators, though speed cannot be inferred from names alone |

When analyzing count queries, profile them separately:

~~~cypher
PROFILE
MATCH (a:QA010Article {status:'PUBLISHED'})
RETURN count(a) AS total;
~~~

The exact count is **5**. Any count query filtering by tags or expanding relationships must use `count(DISTINCT a)` when a root can match multiple edges, while matching the data query's exact filter predicates.

## 14. Benchmarking Workflow for Finding N+1 and Over-Fetching

### 14.1. Keep Workloads Fair

- Same database, schema, dataset, SDN/Neo4j versions, topology, and connection pool.
- Same endpoint contract and displayed fields; never compare a 2-field API against a full-graph API and claim "2x faster."
- Same page size, sort order, filters, index state, and warmup state.
- Collect query count, p50/p95 latency, total bytes/records, `DB Hits`, and JVM heap/GC where available.
- Track `Page COUNT` queries separately from hydrator/service queries; do not mislabel every auxiliary query as N+1.

### 14.2. Three Controlled Experiments

| Approach | Expected queries for N=20 page | What to verify |
|---|---|---|
| Service fetches tags per article | ~1 root + 20 tag (+count) | Repeated tag queries, round trips, latency scaling with N |
| Single root-scoped DTO Cypher | ~1 data (+count if needed) | Post-expand rows, memory, exact 20 roots returned |
| Two-phase root + batch tags | ~2 data (+count if needed) | No N-loop queries, preserved page order, complete tag data |

Numbers in the middle column are an **illustrative model**, not a guarantee of exact SDN query counts. SDN may emit extra queries when hydrating complex relationships or optimizing counts. Always verify against logs and tracing.

### 14.3. Observability Configuration

Increase SDN log verbosity in **staging/test**:

~~~properties
logging.level.org.springframework.data.neo4j=DEBUG
~~~

This is a starting point for inspection—it does **not guarantee** every version logs full Cypher statements and counts. Depending on your Driver/SDN/runtime, distributed tracing, Neo4j query logging, or custom instrumentation may be more informative. When enabling debug logs, guard against logging sensitive parameters or excessive I/O; never leave verbose debug logging enabled broadly in production.

An integration test using `@DataNeo4jTest` or Testcontainers can: seed data → call the endpoint with `size=1,2,5` → assert exact IDs and tags → count statements touching `QA010_HAS_TAG`. Testing both **correctness and query count** catches regressions after SDN upgrades or `@Relationship` model changes.

## 15. Common Errors and Fixes

| Symptom | Possible cause | Fix |
|---|---|---|
| Page requests 10 articles but returns only 3 distinct articles | `LIMIT` applied to relationship-expanded rows | Paginate root nodes with `WITH ... SKIP ... LIMIT` before `OPTIONAL MATCH` |
| `Page` is slower than `Slice` | Extra `COUNT` for total elements | Switch to `Slice` if the UI only needs `hasNext` |
| Duplicate articles across pages even with static data | Missing `ORDER BY` or tie-breaker | Sort deterministically by date plus unique ID |
| A003 disappears when sharing A002's date | Keyset cursor ignores secondary sort key | Filter cursor using the `(date, ID)` pair |
| Query count scales linearly with page size | Service calls relationship repository inside a loop | Batch with `UNWIND $ids` or use one DTO query |
| Low query count yet high memory/`Rows` | One Cypher expands multiple independent collections | Aggregate each relationship branch separately; avoid Cartesian products |
| Returning full entities inflates payloads | Domain `@Relationship` loads unneeded data | Use read DTOs/projections with only required fields |
| Custom `@Query` `Page` returns wrong total | `countQuery` mismatches data filter or root semantics | Count `DISTINCT` roots using identical `WHERE` clauses |
| `@Query` with `Pageable` returns the entire dataset | Missing or misconfigured `$skip`/`$limit` for SDN version | Check query template and inspect logged queries |
| Fast `PROFILE` yet slow API | Java mapping, JSON serialization, network, or N+1 outside the query | Trace end-to-end across both Java and Neo4j |
| Query count rises after SDN upgrade | Hydrator/mapping/cyclic-graph strategy changed | Use integration tests + logs; consider read DTOs |
| Using `findAll()` and `subList()` | Pulls entire dataset into JVM | Paginate in the database or use bounded cursor streaming |

## 16. Exercises with Answers

### Exercise 1 — `Page` or `Slice`?

A feed screen only needs a "Load more" button and at most 20 articles per batch, without displaying total article count. Which should you pick?

**Answer:** `Slice<Article>` or a cursor DTO is better than `Page<Article>` because no exact total count is needed. Deterministic ordering and checking `hasNext` are still required.

### Exercise 2 — Computing Fixture Pages Correctly

With `size=2`, sorted by descending date then ascending `articleId`, list the three pages of `PUBLISHED` articles.

**Answer:** page 0: A001, A002; page 1: A003, A004; page 2: A005. A006 is `DRAFT` and therefore excluded.

### Exercise 3 — Understanding Expanded Rows

Five `PUBLISHED` articles have 2, 1, 2, 1, and 0 tags respectively. How many rows does `OPTIONAL MATCH` from article to tag emit? What is `count(DISTINCT a)`?

**Answer:** 7 rows because the zero-tag article still yields 1 row with `null`; `count(DISTINCT a) = 5`. Six tag relationships match.

### Exercise 4 — N+1

A service fetches 30 articles in one query and then loops to call a tag query per article. How many queries run under a simple count (excluding `COUNT`)?

**Answer:** **31 queries**. Using `Page` with a separate count adds more; SDN may also issue additional hydration queries. Fix N+1 by loading tags for all 30 IDs in one batched query.

### Exercise 5 — Why Is `LIMIT` Wrong?

Does `MATCH (a)-[:HAS_TAG]->(t) RETURN a,t LIMIT 10` guarantee 10 distinct articles?

**Answer:** No. `LIMIT` caps **rows**, not distinct root nodes `a`; nodes with multiple tags repeat. Select roots first, then expand relationships and `collect`.

### Exercise 6 — Cursor with Duplicate Dates

Page 1 has A001/A002; the end-of-page cursor is date `2026-10-05` and ID `A002`. Which articles come next?

**Answer:** A003 (same date, higher ID than A002), then A004. The predicate must combine `publishedAt < lastDate` **or** `publishedAt = lastDate AND articleId > lastId`.

### Exercise 7 — Over-Fetching Is Not N+1

An endpoint runs only one query yet returns 15,000 relationships for 10 articles even though the API only needs titles and tag counts. Is this definitely N+1?

**Answer:** No. This is **over-fetching**, despite the low query count. Switch to scalar aggregations, DTOs, bounded collections, or separate endpoints.

### Exercise 8 — Broken Count Query

The data query returns only the 5 `PUBLISHED` articles, while `countQuery` returns 6 because it includes `DRAFT`. Is displaying `totalElements = 6` valid?

**Answer:** No. `countQuery` must apply the exact same filter criteria as the data query and count distinct root nodes when relationships are expanded. On the fixture, the true `PUBLISHED` total is **5**.

## 17. Cleaning Up Practice Data

Execute only on the **test database** containing the `QA010` fixture:

~~~cypher
DROP INDEX qa010_article_feed IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa010_article_id_unique IF EXISTS;
~~~

~~~cypher
MATCH (n)
WHERE n:QA010Article OR n:QA010Tag OR n:QA010Author
DETACH DELETE n;
~~~

Verify:

~~~cypher
MATCH (n)
WHERE n:QA010Article OR n:QA010Tag OR n:QA010Author
RETURN count(n) AS remaining;
~~~

Answer: `remaining = 0`. Never run this cleanup if `QA010` labels are shared with real data. `DETACH DELETE` also deletes relationships attached to the test nodes.

## 18. Official References

- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/): entity mapping, repositories, derived finders, projections, and SDN versions.
- [Spring Data Neo4j — Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html): record-per-root, collecting nodes/relationships, path mapping limits, and query shapes.
- [Spring Data Neo4j — FAQ: custom mappings](https://docs.spring.io/spring-data/neo4j/reference/faq.html): using `Neo4jClient` and `mappedBy` for non-entity read DTOs.
- [Spring Data Neo4j — Query Methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html): `Pageable`, `Page`, `Slice`, sorting, and count costs.
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/): result ordering guarantees.
- [Neo4j Cypher Manual — SKIP](https://neo4j.com/docs/cypher-manual/current/clauses/skip/): offset pagination and `SKIP` limits.
- [Neo4j Cypher Manual — Execution Plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): `EXPLAIN`, `PROFILE`, Rows, DB Hits, and memory.
- [Neo4j Java Driver Manual — Performance](https://neo4j.com/docs/java-manual/current/performance/): connection pooling, parameterization, latency measurement, and batching.

**Key takeaway:** in Spring Data Neo4j, pagination must bound **root nodes** with deterministic ordering before expanding relationships. `Page` provides exact totals when required, while `Slice` avoids the extra COUNT. When endpoints slow down, distinguish **N+1 queries**, **relationship expansion multiplying rows**, and **graph over-fetching**, then choose a single DTO query or two-phase batch fetch instead of querying per node.
