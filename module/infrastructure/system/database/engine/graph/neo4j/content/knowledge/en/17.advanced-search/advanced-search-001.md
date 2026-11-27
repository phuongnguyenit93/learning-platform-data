# Full-Text Index for Text Search on Nodes and Relationships

In the **Neo4j** graph database, nodes store entities and relationships store connections. Properties on both types of entities can contain text: article titles, product descriptions, review contents, transaction notes, or comments on a relationship. When users want to search for "articles talking about Cypher" or "reviews mentioning delivery", exact equality comparison with `=` usually does not meet the requirement.

A **full-text index** supports searching by *words* or *phrases* in tokenized text, returning matching entities along with a **relevance score** (`score`). Neo4j builds full-text indexes on top of Lucene text search technology. This is a tool in the **Advanced Search** chapter of the **DATABASE_ENGINE_GRAPH_NEO4J** module, working alongside the property graph model, Cypher, indexes/constraints, the Java Driver, Spring Data Neo4j, and graph system operations.

After this lesson, you will be able to create full-text indexes for **both nodes and relationships**, query them safely using Cypher procedures, understand the role of analyzers and Lucene queries, evaluate when to use a full-text index instead of other index types, and handle performance and consistency issues.

## 1. What Problem Does a Full-Text Index Solve?

Suppose the data contains a node:

```text
(:Article {
  articleId: 'A-001',
  title: 'Introduction to Cypher Queries',
  body: 'Cypher helps find relationships and paths in a Neo4j graph.'
})
```

Users might enter `cypher`, `"paths"`, or a multi-word search expression. They expect to find the document even though the input string does not exactly equal `title` or `body`.

Different goals require different tools:

| Requirement | Usually Suitable Tool | Reason |
| --- | --- | --- |
| Find an article with `articleId = 'A-001'` | Regular index, uniqueness constraint | Exact identifier matching |
| Find titles starting with `'Cypher'` | `TEXT INDEX` or a predicate-compatible index | Search on property strings |
| Find articles containing the word `'Cypher'` by token | **Full-text index** | Analyzes text and calculates relevance |
| Search phrases using search syntax | **Full-text index** | Supports Lucene text query syntax |
| Find all articles written by author A within 2 relationship hops | Cypher `MATCH` and supporting lookup indexes | Graph structure constraints |
| Find reviews on `:REVIEWED` relationships mentioning "delivery" | **Full-text index on relationships** | Returns the relationship itself carrying the text property |

**Key distinction:** a full-text index does not replace Cypher's graph traversal capabilities. A typical workflow finds textually matching nodes/relationships **first**, then uses `MATCH` to check relationships, status, ownership, or other business conditions.

## 2. How a Full-Text Index Works

When creating an index on one or more text properties, Neo4j uses an **analyzer** to convert the content into tokens for lookup. Depending on the analyzer, the steps may include tokenization, lowercasing, stop-word removal, or stemming/morphological normalization.

```text
Node/relationship with text properties
                  |
                  v
         Analyzer processes text
                  |
                  v
       Tokens -> list of entities
                  |
                  v
       Full-text inverted index
                  ^
                  |
          Lucene text query
                  |
                  v
       Matching entities + score
```

For example, an analyzer might turn `'Cypher and Neo4j'` into tokens close to `cypher` and `neo4j`. However, **you should not assume that every analyzer handles Vietnamese diacritics, compound words, or stop words in the same way**. Only testing queries against your actual data and chosen analyzer reveals the real behavior.

Key characteristics:

- A full-text index **does not require every node or relationship to have the same set of properties**; any entity with at least one indexed text property can participate.
- A full-text index can declare **multiple node labels or multiple relationship types**, as well as multiple text properties.
- Only values of types suitable for text indexing, such as strings or lists of strings, contribute to a full-text index. Numeric values do not automatically become searchable strings.
- The `score` represents relevance according to the search engine's scoring mechanism. It is **not an accuracy percentage, probability, business confidence, or proximity in the graph**.
- Full-text queries are invoked **explicitly** using dedicated procedures; you should not assume that `WHERE a.title CONTAINS ...` will automatically choose a full-text index.

## 3. Preparing Sample Data

The following examples target Neo4j 5 and versions with corresponding syntax. Procedure names, options, or execution permissions may vary by server version; verify against your target environment before deploying to production.

In your practice database, create several articles and two product reviews:

```cypher
CREATE CONSTRAINT article_id_unique IF NOT EXISTS
FOR (a:Article)
REQUIRE a.articleId IS UNIQUE;

CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.userId IS UNIQUE;

CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.sku IS UNIQUE;
```

```cypher
MERGE (a:Article {articleId: 'A-001'})
SET a.title = 'Introduction to Cypher Queries',
    a.body = 'Cypher helps find relationships and paths in a Neo4j graph.',
    a.status = 'PUBLISHED',
    a.language = 'vi';

MERGE (b:Article {articleId: 'A-002'})
SET b.title = 'Optimizing Neo4j Queries',
    b.body = 'Read the execution plan to optimize MATCH, indexes, and path queries.',
    b.status = 'PUBLISHED',
    b.language = 'vi';

MERGE (c:Article {articleId: 'A-003'})
SET c.title = 'Draft introduction to graph systems',
    c.body = 'Searching with Cypher in connected data.',
    c.status = 'DRAFT',
    c.language = 'vi';

MERGE (u:User {userId: 'U-001'})
MERGE (p:Product {sku: 'P-001'})
MERGE (u)-[r:REVIEWED {reviewId: 'R-001'}]->(p)
SET r.title = 'Fast delivery',
    r.comment = 'On-time delivery, carefully packaged.',
    r.rating = 5;

MERGE (v:User {userId: 'U-002'})
MERGE (u2:Product {sku: 'P-002'})
MERGE (v)-[r2:REVIEWED {reviewId: 'R-002'}]->(u2)
SET r2.title = 'Decent quality',
    r2.comment = 'Good product, but delivery was quite slow.',
    r2.rating = 3;
```

These `MERGE` statements only illustrate repeatable sample data using the stated identifier keys. In a real application, guaranteeing uniqueness for `reviewId` typically requires a dedicated data model and constraints appropriate for relationships.

## 4. Creating a Full-Text Index on Nodes

### 4.1. Index for a Single Label and Multiple Properties

To search across both the title and body of articles:

```cypher
CREATE FULLTEXT INDEX articleFulltext IF NOT EXISTS
FOR (a:Article)
ON EACH [a.title, a.body];
```

The syntax consists of:

- `articleFulltext`: **index name**, used when calling query procedures.
- `(a:Article)`: selects nodes with the `:Article` label.
- `ON EACH [a.title, a.body]`: indexes two text properties.
- `IF NOT EXISTS`: prevents an error if a matching index already exists; this clause **does not mean** an existing index will automatically have its configuration updated if it differs from what you intended.

With a multi-property index, an entity can still appear in results if only `title` or only `body` is indexed text. Both properties do not need to exist simultaneously.

### 4.2. Index for Multiple Labels

If the system has both articles and FAQs, and both entity types share the same text fields:

```cypher
CREATE FULLTEXT INDEX knowledgeFulltext IF NOT EXISTS
FOR (n:Article|FAQ)
ON EACH [n.title, n.body];
```

This is **one** full-text index over the set of nodes labeled `:Article` **or** `:FAQ`, not a requirement that every node have both labels. After searching, you should check the label or apply business filters if the UI only displays one entity type.

If the two entity types have different text structures, update frequencies, or search rules, consider splitting the indexes so you can tune analyzers and search scope independently.

## 5. Creating a Full-Text Index on Relationships

Relationships in Neo4j have properties just like nodes. A review is modeled by a relationship:

```text
(:User {userId: 'U-001'})
   -[:REVIEWED {
       title: 'Fast delivery',
       comment: 'On-time delivery...',
       rating: 5
     }]->
(:Product {sku: 'P-001'})
```

Create the index:

```cypher
CREATE FULLTEXT INDEX reviewFulltext IF NOT EXISTS
FOR ()-[r:REVIEWED]-()
ON EACH [r.title, r.comment];
```

The `()-[r:REVIEWED]-()` part specifies the **relationship type to be indexed**, not a concrete path pattern. The full-text index reads text from the `title` and `comment` properties of the relationship; numeric properties such as `rating` are not full-text searchable content.

When your data has multiple relationship types carrying text content, you can declare the supported types using relationship type union syntax:

```cypher
CREATE FULLTEXT INDEX feedbackFulltext IF NOT EXISTS
FOR ()-[r:REVIEWED|COMMENTED]-()
ON EACH [r.title, r.comment];
```

This example is an **alternative** design to an index covering only `:REVIEWED`. You should not create all overlapping indexes in production, because every index increases storage requirements and maintenance overhead.

## 6. Waiting for the Index to Be Ready and Checking Status

Creating an index on a large dataset can take time to **populate**. To check its status:

```cypher
SHOW FULLTEXT INDEXES
YIELD name, state, populationPercent
RETURN name, state, populationPercent
ORDER BY name;
```

Important states include `POPULATING` (currently building), `ONLINE` (ready for use), and `FAILED` (index build failed). In a practice environment, you can wait for a specific index to finish:

```cypher
CALL db.awaitIndex('articleFulltext', 300);
```

The second parameter is the timeout in seconds. If the index does not transition to `ONLINE`, check the logs and index status instead of repeatedly running search queries and concluding "no data found".

The following sections assume `articleFulltext` and `reviewFulltext` are already in the `ONLINE` state.

## 7. Querying a Node Full-Text Index with Cypher

### 7.1. Searching by Keyword

```cypher
CALL db.index.fulltext.queryNodes(
  'articleFulltext',
  'cypher'
)
YIELD node, score
RETURN node.articleId AS id,
       node.title AS title,
       score
ORDER BY score DESC;
```

The `db.index.fulltext.queryNodes` procedure yields two primary values:

- `node`: the node matching the query.
- `score`: the relevance score calculated by the search engine.

Sample results will include articles containing tokens matching "cypher". **Do not hardcode specific score values or tie-breaking orders** in business specifications: results depend on content, analyzer, Lucene scoring, and index state.

### 7.2. Combining Text Search with Business Conditions

Only published articles should be shown to readers:

```cypher
CALL db.index.fulltext.queryNodes(
  'articleFulltext',
  $luceneQuery
)
YIELD node AS a, score
WHERE a.status = 'PUBLISHED'
RETURN a.articleId AS id,
       a.title AS title,
       score
ORDER BY score DESC, a.articleId ASC
LIMIT 20;
```

For example, with parameter `$luceneQuery = 'cypher'`. The `a.status = 'PUBLISHED'` filter is a **Cypher condition** applied to the nodes returned by the full-text procedure. You can add a language condition as well:

```cypher
CALL db.index.fulltext.queryNodes('articleFulltext', $luceneQuery)
YIELD node AS a, score
WHERE a.status = 'PUBLISHED' AND a.language = $language
RETURN a.articleId AS id, a.title AS title, score
ORDER BY score DESC, a.articleId ASC
LIMIT $limit;
```

`$language` and `$limit` are parameters validated by the application. If different user roles have different viewing permissions, the system must enforce **access-control filtering** at the appropriate layer—never treat an index match as proof that the user is authorized to read that node.

### 7.3. Traversing the Graph After Text Search

For example, finding an `:Author` who wrote published articles mentioning Cypher:

```cypher
CALL db.index.fulltext.queryNodes('articleFulltext', $luceneQuery)
YIELD node AS a, score
MATCH (author:Author)-[:WROTE]->(a)
WHERE a.status = 'PUBLISHED'
RETURN author.name AS author,
       a.title AS article,
       score
ORDER BY score DESC
LIMIT 20;
```

Results depend on whether the data contains matching `:WROTE` relationships. In the initial sample dataset, no `:WROTE` relationships were created yet, so this query returns no rows until authors and those relationships are added.

This is the strength of combining Neo4j with full-text search: find **content** via the index, then analyze **connections** with Cypher patterns.

## 8. Querying a Relationship Full-Text Index

To find reviews mentioning "delivery":

```cypher
CALL db.index.fulltext.queryRelationships(
  'reviewFulltext',
  $luceneQuery
)
YIELD relationship AS r, score
RETURN r.reviewId AS reviewId,
       r.title AS title,
       r.comment AS comment,
       startNode(r).userId AS reviewerId,
       endNode(r).sku AS productSku,
       score
ORDER BY score DESC;
```

With `$luceneQuery = '"delivery"'` (or `"on-time delivery"`), results depend on how the analyzer tokenizes and interprets phrases. The example above applies when `:REVIEWED` goes from `:User` to `:Product` as in the sample data; if your system stores the reverse direction, the meaning of `startNode(r)` and `endNode(r)` will swap.

You can attach the start and end nodes in a Cypher pattern for further filtering:

```cypher
CALL db.index.fulltext.queryRelationships(
  'reviewFulltext',
  $luceneQuery
)
YIELD relationship AS r, score
MATCH (u:User)-[r]->(p:Product)
WHERE r.rating >= $minRating
RETURN u.userId AS userId,
       p.sku AS sku,
       r.comment AS comment,
       score
ORDER BY score DESC
LIMIT 10;
```

Here, the full-text index selects candidates based on **the relationship's text properties**. Conditions on the reviewer node, product node, and star rating remain Cypher logic.

## 9. Lucene Query Syntax and Analyzers

The search parameter of full-text procedures is a **Lucene query syntax string**, not a Cypher `WHERE` expression. This determines how multiple words, phrases, and special characters are handled.

| Example Query String | Search Intent | Things to Watch |
| --- | --- | --- |
| `cypher` | Search for token "cypher" | Depends on analyzer tokenization |
| `"graph path"` | Search for ordered phrase | Depends on tokenization and token positions |
| `cypher AND neo4j` | Require both terms | `AND` is a Lucene operator |
| `cypher OR neo4j` | Either term | May return a broader result set |
| `title:cypher` | Search only on the indexed `title` field | Field name must be an indexed property |
| `neo4*` | Prefix/wildcard query example | Can be expensive; not a drop-in replacement for `STARTS WITH` |
| `cypher~1` | Fuzzy search by character edit distance | Does not automatically fix all typos |
| `title:cypher^3 OR body:cypher` | Boost weight of title match | `score` remains a relative Lucene score |

These strings illustrate the syntax. Actual behavior varies by analyzer, the Lucene version bundled with Neo4j, and index contents.

### 9.1. Choosing an Analyzer

Neo4j provides a list of available analyzers via a procedure:

```cypher
CALL db.index.fulltext.listAvailableAnalyzers();
```

A common option is `standard-no-stop-words`, often used to tokenize with general rules without removing stop words. You can specify an analyzer when creating the index:

```cypher
CREATE FULLTEXT INDEX articleWithAnalyzer IF NOT EXISTS
FOR (a:Article)
ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    'fulltext.analyzer': 'standard-no-stop-words'
  }
};
```

This example uses a different name to explain the analyzer option. In a real deployment, decide on a single consistent index strategy and avoid maintaining unnecessary duplicates.

**For Vietnamese content**, you should test at least these cases:

- Words with and without diacritics, e.g. `'đồ thị'` and `'do thi'`.
- Multi-syllable compound words, e.g. `'giao hàng'` and `'giao nhanh'`.
- Uppercase/lowercase and abbreviations.
- Vietnamese text mixed with English proper nouns: `Neo4j`, `Cypher`, `Graph Data Science`.
- Exact phrases, punctuation, and text containing special characters.

Not every general-purpose analyzer automatically folds Vietnamese diacritics or treats multi-syllable compounds as single words. If business requirements call for accent-insensitive search, you may need to implement normalization and design an additional searchable property while preserving the original text for display. Normalization must be tested consistently across both indexed data and search queries.

### 9.2. Do Not Pass Raw User Input as Arbitrary Lucene Expressions

A query may contain Lucene syntax control characters such as `:`, `"`, `*`, `~`, `(`, `)`, `+`, or `-`. If the UI is a **simple free-text search box**, the application should define escaping rules for special characters and construct a true "plain text" query string, rather than accidentally interpreting user characters as operators.

**Cypher parameters** like `$luceneQuery` prevent concatenating user data directly into the Cypher query string, but **they do not automatically make a Lucene query syntactically safe**. These are two independent syntax layers.

If the product **intentionally** supports advanced syntax such as `AND`, `OR`, or `title:...`, document it clearly for users, enforce length/breadth limits, and handle syntax errors gracefully when the parser rejects invalid input.

## 10. How Full-Text Indexes Differ from TEXT, RANGE, and Constraints

Although all are called "indexes", different types serve different purposes:

| Type | Typical Query | Semantics |
| --- | --- | --- |
| Uniqueness constraint / backing index | `a.articleId = $id` | Exact identifier lookup, unique if constrained |
| Range index | `a.createdAt >= $time`, general comparisons | Value and range filtering |
| Text index | `a.title CONTAINS $fragment` or supported string predicates | String operation matching on a property |
| **Full-text index** | `db.index.fulltext.queryNodes('...', $query)` | Analyzer-based token/phrase search with `score` |

Example of creating a TEXT INDEX to support string predicates on `title`:

```cypher
CREATE TEXT INDEX articleTitleText IF NOT EXISTS
FOR (a:Article)
ON (a.title);
```

You can then write property-based predicates:

```cypher
MATCH (a:Article)
WHERE a.title CONTAINS $fragment
RETURN a.articleId AS id, a.title AS title;
```

Whether the query planner selects the text index depends on the predicate, Neo4j version, data characteristics, and statistics; verify with `EXPLAIN` or `PROFILE` in an appropriate environment. A `TEXT INDEX` does not produce a `score` or process Lucene operators.

**Do not try to replace a full-text index by forcing** `toLower(a.body) CONTAINS toLower($term)` across millions of nodes and expect fast performance. Applying functions to properties can prevent efficient index usage. Choose the index type and data design according to the exact search functionality required.

## 11. Data Freshness: Synchronous vs. Eventually Consistent

By default, full-text index updates are tied to data updates within the transaction. Neo4j also supports an **eventually consistent** mode: index changes are applied asynchronously afterward. This mode reduces indexing work inside write transactions, at the trade-off that **searches may temporarily miss newly created or recently modified data**.

Configuration example illustrating the option:

```cypher
CREATE FULLTEXT INDEX articleAsyncFulltext IF NOT EXISTS
FOR (a:Article)
ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    'fulltext.analyzer': 'standard-no-stop-words',
    'fulltext.eventually_consistent': true
  }
};
```

This is an **alternative configuration choice**, not a required next step in the practice exercise. You can inspect indexes with:

```cypher
SHOW FULLTEXT INDEXES
YIELD name, state, options
RETURN name, state, options
ORDER BY name;
```

Neo4j provides a procedure to wait until queued eventually-consistent updates have been applied, useful in tests or tasks requiring explicit synchronization:

```cypher
CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh();
```

Do not call this wait procedure on every online search request because it can increase latency. Instead, align on freshness requirements: for example, "an author who just published an article must see it immediately" versus "a brief delay before search results reflect updates is acceptable".

Additional note: an uncommitted transaction should not be treated as ready data for an independent search query. When testing, commit changes first and then observe when the index reflects the data.

## 12. Integrating with Java Driver and Spring Data Neo4j

Java applications typically receive `query` from an API, validate length/search rules, and pass it as a **parameter** to Cypher. Example using the Neo4j Java Driver:

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Record;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;

import java.util.Map;

public class ArticleSearchExample {
    public static void main(String[] args) {
        String uri = "neo4j://localhost:7687";
        String username = "neo4j";
        String password = System.getenv("NEO4J_PASSWORD");
        String luceneQuery = "cypher"; // Already sanitized according to search policy

        try (Driver driver = GraphDatabase.driver(
                 uri, AuthTokens.basic(username, password));
             Session session = driver.session()) {

            String cypher = """
                CALL db.index.fulltext.queryNodes(
                    'articleFulltext', $luceneQuery
                )
                YIELD node AS a, score
                WHERE a.status = 'PUBLISHED'
                RETURN a.articleId AS id, a.title AS title, score
                ORDER BY score DESC, a.articleId
                LIMIT $limit
                """;

            Result result = session.run(
                cypher,
                Map.of("luceneQuery", luceneQuery, "limit", 20)
            );

            while (result.hasNext()) {
                Record row = result.next();
                System.out.println(
                    row.get("id").asString() + " | " +
                    row.get("title").asString() + " | " +
                    row.get("score").asDouble()
                );
            }
        }
    }
}
```

This example uses Java text blocks (Java 15+) and requires a compatible Neo4j and Java Driver environment. Never hardcode passwords in source code or logs; the snippet reads the password from an environment variable for illustration. In applications with connection pooling, manage the `Driver` lifecycle at the application level rather than opening and closing it per HTTP request.

With **Spring Data Neo4j**, you can use a repository or `Neo4jClient` with custom Cypher queries to invoke the procedure and map both `node` and `score` into a DTO. An `Article` entity representing only node properties is insufficient if the API needs to return the relevance score; the DTO should include `score`, pagination details, and required business metadata.

In a production service, separate responsibilities cleanly:

1. **Request normalization and validation**: empty queries, excessive length, special characters, allowed indexes or result types.
2. **Search execution**: invoke the full-text procedure with parameters and filter by permissions, status, and language.
3. **Response construction**: return stable IDs, titles, scores if useful, along with sort criteria and result limits.
4. **Operational observability**: record result counts, latency, Lucene syntax errors, and index change timestamps, while avoiding logging raw sensitive information.

## 13. Performance, Pagination, and Maintenance

Full-text indexes typically reduce work compared to scanning all text properties, but they do not guarantee every query will be fast. Pay special attention to:

### 13.1. Limiting and Sorting Results

```cypher
CALL db.index.fulltext.queryNodes('articleFulltext', $luceneQuery)
YIELD node AS a, score
WHERE a.status = 'PUBLISHED'
RETURN a.articleId AS id, a.title AS title, score
ORDER BY score DESC, a.articleId ASC
SKIP $offset
LIMIT $pageSize;
```

When data or indexes change between requests, search ordering can shift, causing `SKIP`-based pagination to produce unstable pages. Large `SKIP` values can also be expensive. Large-scale search systems should choose pagination and consistency strategies suited to the product, while capping `pageSize` and query depth.

`score` values from **two different queries** or **two different indexes** are not directly comparable by default. When merging article and review results, design an explicit cross-type ranking method if required.

### 13.2. Write Overhead and Storage

Every change to an indexed property can trigger index structure updates. A full-text index covering many labels/relationship types and many text fields requires more cache memory, disk space, and update work. Only index properties that are genuinely searched.

### 13.3. Monitoring and Troubleshooting

- Check `SHOW FULLTEXT INDEXES` to see whether the index is `ONLINE`.
- When text is not found, test a simple single word known to exist in the data and inspect the analyzer.
- Verify that the node has the expected label, the relationship has the expected type, and the property has an appropriate data type.
- Check whether `status`, `language`, access-control filters, or the `MATCH` pattern filtered out all results.
- If using eventually consistent mode, evaluate update lag and wait for synchronization in test environments if needed.
- For Cypher queries with multi-hop traversals after search, use `EXPLAIN` or `PROFILE` to inspect graph expansion; fast full-text lookup does not automatically guarantee the subsequent `MATCH` is cheap.

### 13.4. Index Lifecycle Management

When changing the analyzer, label set, or indexed property list, plan a proper index rollout: verify the new index is `ONLINE` and switch the application to the new name. Drop an index only when certain no queries depend on it:

```cypher
DROP INDEX articleFulltext IF EXISTS;
```

This command **only drops the index**; it does not delete nodes or relationships. However, applications calling `db.index.fulltext.queryNodes('articleFulltext', ...)` will no longer be able to use that index name after dropping it. Do not run this command on a shared environment just to clean up examples without verifying impact.

## 14. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `WHERE a.title = $q` for multi-word search | Matches only the entire string, misses token search | Create a full-text index and call the appropriate procedure |
| Creating a full-text index on nodes and calling `queryRelationships` | Wrong entity/index type | Use `queryNodes` for nodes and `queryRelationships` for relationships |
| Indexing numeric `rating` to search for "5 stars" | Full-text is not designed for numeric matching | Use numeric predicates and a suitable index |
| Choosing an analyzer unsuitable for Vietnamese text | Tokenization or diacritic matching behaves unexpectedly | Test tokenization, choose an appropriate analyzer, and apply controlled normalization |
| Naming the index properly but omitting a label/type | Intended entities are excluded from the index | Cross-check index scope against the data model |
| Querying immediately while the index is `POPULATING` | Index may not be usable yet | Wait for `ONLINE` and check index status |
| Setting `LIMIT` without access-control filtering | May leak content or metadata | Enforce permission checks before returning results |
| Sending raw user input into advanced Lucene syntax | Special characters alter meaning or cause parse errors | Implement dedicated Lucene escaping/validation policies |
| Treating `score` as an accuracy probability | Incorrect ranking and result interpretation | Use it only as a relative relevance signal |
| Assuming an eventually consistent index always sees new writes | UI may display stale results | Choose appropriate consistency and design UX/notifications accordingly |
| Directly combining scores from multiple indexes | Cross-type ranking order lacks a valid basis | Design a dedicated aggregation/reranking strategy |

## 15. Practice Exercises

**Exercise 1 — Search articles by text.** Create the `articleFulltext` index on `:Article(title, body)`, search for `'cypher'`, and return ID, title, and score for published articles. Explain why draft articles should not appear in public results.

**Exercise 2 — Search reviews on relationships.** Create `reviewFulltext` for `:REVIEWED(title, comment)` relationships. Write a query searching for `'delivery'` and return the reviewer ID and product SKU. Add a condition to include only reviews with 4 stars or higher.

**Exercise 3 — Compare two index types.** Write one query using `title CONTAINS $fragment` and one query using `queryNodes`. Explain the differences in matching semantics, score computation, and which index type to consider.

**Exercise 4 — Supporting accent-insensitive Vietnamese.** Users type `'do thi'` while data stores `'đồ thị'`. Propose how to test the analyzer and a normalization approach if the business requires both query forms to match equivalently. State the risk if normalization loses the original content.

**Exercise 5 — Freshness and pagination.** An API just updated an article title, and the index has `eventually_consistent` enabled; pages 1 and 2 are fetched in two consecutive requests. Analyze why the results might shift and propose how to design the user experience.

### Checklist Before Deploying Full-Text Search to Production

- [ ] Identified entity target: **node** or **relationship**, label/type, and text properties.
- [ ] Selected an analyzer and tested real keywords, especially for **Vietnamese**.
- [ ] Index is `ONLINE`; monitoring and rollout strategy exist for index changes.
- [ ] Queries use **Cypher parameters** and handle Lucene control characters separately.
- [ ] Applied **status, language, access-control** filters and result limits.
- [ ] Understand that `score` is relative relevance and should not be arbitrarily merged across indexes.
- [ ] Agreed on **freshness** requirements if eventually consistent mode is enabled.
- [ ] Measured search latency, index maintenance overhead, and post-search graph traversal cost.

**Remember:** a full-text index helps find *text content* attached to nodes or relationships, while Cypher helps inspect and traverse the *connected structure* of a property graph. Choosing the right analyzer, index scope, and procedure, combined with business conditions, forms the foundation for building advanced search that is both useful and reliable in Neo4j.
