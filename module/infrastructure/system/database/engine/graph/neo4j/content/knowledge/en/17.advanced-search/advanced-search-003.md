# Distinguishing Text Indexes from Full-Text Indexes in Neo4j

In Neo4j, both operate on `STRING` data, yet the following two requirements are **not the same**:

- **Filtering by exact string conditions:** "Get articles whose title contains the exact substring `Graph`", "Article code starts with `G-`", "Document name ends with `Guide`".
- **Searching by content:** "Find articles about `graph` whether that word appears in the title or description; rank results by relevance", "Search for the phrase `graph modeling`".

For the first requirement, Neo4j provides a **text index** — a *performance index* that accelerates string predicates in Cypher. For the second requirement, Neo4j provides a **full-text index** — a *search index* built on Apache Lucene that tokenizes content and returns a relevance score.

This lesson belongs to the **Advanced Search** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. This knowledge helps you choose the right index for a property graph composed of nodes, relationships, and text properties, and design accurate queries across Cypher, the Neo4j Java Driver, and Spring Data Neo4j.

## 1. Two Index Types Serving Two Ways of Asking Questions

| Criterion | Text Index: `CREATE TEXT INDEX` | Full-Text Index: `CREATE FULLTEXT INDEX` |
| --- | --- | --- |
| Category | *Performance index*: accelerates filter predicates | *Search index*: word search and ranking |
| How It Is Queried | `MATCH ... WHERE`; the Cypher planner decides whether to use it | Explicitly invoked via `SEARCH` (new Cypher 25) or full-text procedures |
| Matching Unit | String value, prefix, suffix, or substring per Cypher operators | **Tokens** extracted from content by an analyzer |
| Operators / Syntax | `=`, `IN`, `STARTS WITH`, `ENDS WITH`, `CONTAINS` | Lucene queries: keywords, phrases, `AND`/`OR`, etc. |
| Language Analysis | No configurable analyzer for text indexes | Has tokenizer/analyzer; word processing can be configured |
| Case Sensitivity | Results follow Cypher string comparisons; case-sensitive for standard predicates | Default analyzers lowercase text, so queries are typically case-insensitive |
| Relevance | Does not return a search score | Returns `score` to rank matching results |
| Indexing Scope | **One** string property on **one** node label or relationship type | Can span **multiple** labels/types and **multiple** properties |
| Indexed Values | `STRING` properties | `STRING` and `LIST<STRING>` lists |
| Business Role | Exact predicate filtering preserving Cypher query semantics | Discovering documents/records with relevant content, returning results by relevance |

**Do not think of "text index" as a shorthand for "full-text index".** The two types differ in internal structure, search semantics, and how they are invoked. Also do not confuse `TEXT INDEX` with `RANGE INDEX`: a range index is typically suited for equality lookups, value ranges, and prefix matching, whereas a text index is especially useful for `CONTAINS` and `ENDS WITH`. Both range and text indexes belong to the performance index category.

## 2. Building Sample Data and Defining Search Goals

To verify this yourself, run the following data setup **once on a test database**. The `SearchDemo` prefix on labels and types distinguishes them from application data. Do not run `CREATE` repeatedly if you want to compare the example counts.

```cypher
CREATE
  (a:SearchDemoArticle {
    code: 'G-101',
    title: 'Neo4j Graph Modeling',
    body: 'Learn nodes and relationships with Cypher'
  }),
  (b:SearchDemoArticle {
    code: 'G-102',
    title: 'Graph Queries in Cypher',
    body: 'Cypher matches connected data and graph paths'
  }),
  (c:SearchDemoArticle {
    code: 'J-201',
    title: 'Java Driver Guide',
    body: 'Build Java applications with the Neo4j driver'
  }),
  (d:SearchDemoArticle {
    code: 'N-301',
    title: 'Introduction to Neo4j',
    body: 'Install a graph database and learn Cypher basics'
  }),
  (a)-[:SEARCH_DEMO_RELATED {note: 'Graph patterns for Cypher readers'}]->(b),
  (d)-[:SEARCH_DEMO_RELATED {note: 'Graph database setup guide'}]->(a);
```

Visualizing the graph:

```text
G-101 "Neo4j Graph Modeling" ──SEARCH_DEMO_RELATED──► G-102 "Graph Queries in Cypher"

N-301 "Introduction to Neo4j" ──SEARCH_DEMO_RELATED──► G-101

J-201 "Java Driver Guide" (no SEARCH_DEMO_RELATED relationship)
```

In this dataset:

- Two titles, G-101 and G-102, contain the exact substring `Graph`.
- Three articles, G-101, G-102, and N-301, contain the word `graph` in at least one of `title` or `body`.
- Article J-201 does not contain the word `graph` in either property, even though it uses Neo4j.
- Only G-101 has the consecutive phrase `Graph Modeling` in its title.

The examples intentionally use simple English words to make tokenizer behavior easy to verify. When handling accented Vietnamese content, you must test the analyzer separately (Section 7).

## 3. Text Index: Accelerating Cypher String Predicates

Create a text index on **one property** `title` of the `SearchDemoArticle` label:

```cypher
CREATE TEXT INDEX search_demo_title_text IF NOT EXISTS
FOR (a:SearchDemoArticle)
ON (a.title);
```

Several Cypher queries that can be supported by a text index:

```cypher
// Title value must exactly equal the supplied string
MATCH (a:SearchDemoArticle)
WHERE a.title = 'Neo4j Graph Modeling'
RETURN a.code AS code, a.title AS title;
```

```cypher
// Prefix of the entire title string
MATCH (a:SearchDemoArticle)
WHERE a.title STARTS WITH 'Graph'
RETURN a.code AS code, a.title AS title;
```

```cypher
// Suffix of the entire title string
MATCH (a:SearchDemoArticle)
WHERE a.title ENDS WITH 'Guide'
RETURN a.code AS code, a.title AS title;
```

```cypher
// Contiguous substring, even when not at the start of a word
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'Graph'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

The last query returns **G-101** and **G-102**; the `ENDS WITH 'Guide'` query returns **J-201**. These results stem from **the semantics of the `WHERE` predicate**, and do not change depending on whether an index exists. The index simply provides an access path so the query can execute faster.

### 3.1. Why Is `CONTAINS` Different from Searching for a Word?

`CONTAINS` asks whether **a contiguous sequence of characters** appears inside a property value. It does not understand compound words, punctuation, stop words, or relevance.

```cypher
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'graph'
RETURN a.code;
```

The example above does not return G-101 or G-102 because their titles contain capitalized `Graph`, not the lowercase substring `graph`. Neo4j does not automatically turn this comparison into a case-insensitive search.

If you use `toLower(a.title) CONTAINS 'graph'`, the matching semantics change, but wrapping the property in a function can prevent the planner from using the corresponding text index. For that requirement, consider storing **a separate normalized property** and indexing it, or choosing full-text search if the goal is token-based search.

### 3.2. Why Are Text Indexes Suitable for Substrings?

In current Neo4j versions, text indexes use a **trigram** technique: decomposing strings into overlapping slices of three Unicode code points. For example, `developer` produces slices such as `dev`, `eve`, `vel`, and so on. As a result, the planner can leverage a text index for `CONTAINS` or `ENDS WITH`, which are operations poorly served by range indexes.

Text indexes support `STARTS WITH`, `ENDS WITH`, `CONTAINS`, and, when data types can be determined, `=` and `IN`. However, **being supported does not guarantee selection**. If both a range index and a text index exist on the same `STRING` property, the planner typically prefers the text index for `CONTAINS`/`ENDS WITH`, and the range index for other filters. Actual plan selection depends on statistics, expressions, and the runtime environment.

### 3.3. Do Not Use a Text Index to Produce Relevance Ranking

Both results matching `title CONTAINS 'Graph'` satisfy a Boolean condition equally. There is no `score` indicating how relevant each is to `Graph`. To sort by recency, name, or article code, you must specify an explicit sort criterion, for example:

```cypher
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'Graph'
RETURN a.code AS code, a.title AS title
ORDER BY code ASC;
```

Here, `ORDER BY code` sorts by code, not by content match quality.

## 4. Full-Text Index: Token Analysis, Word Search, and Ranking

Create a full-text index on **two properties**, `title` and `body`, of the `SearchDemoArticle` label:

```cypher
CREATE FULLTEXT INDEX search_demo_article_fulltext IF NOT EXISTS
FOR (a:SearchDemoArticle)
ON EACH [a.title, a.body];
```

Full-text indexes use Apache Lucene. An analyzer processes the content to produce searchable tokens. With the default `standard-no-stop-words` analyzer, words are typically lowercased, so querying `graph` can match `Graph`. The operation is fundamentally **searching analyzed words**, not matching contiguous substrings like `CONTAINS`.

A full-text index can search across **any of the listed properties**. It does not require every node to possess all properties in the list: a node with the matching label and **at least one** indexed property of a supported type can still be indexed.

### 4.1. Using the Procedure in Neo4j 5 / Cypher 5

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', 'graph'
)
YIELD node, score
RETURN node.code AS code,
       node.title AS title,
       score
ORDER BY score DESC;
```

Expected results include **G-101, G-102, and N-301** because each article has the `graph` token in its title or body. `score` is a relevance value computed by Lucene; do not hardcode exact numbers as they depend on data, analyzer configuration, version, and index statistics. Article ordering can change as content changes.

The procedure yields `node` and `score`; when you need to query relationships of the matched nodes, you can continue with `MATCH` or `OPTIONAL MATCH` in the same Cypher query:

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', 'graph'
)
YIELD node AS article, score
WITH article, score
ORDER BY score DESC
LIMIT 5
OPTIONAL MATCH (article)-[:SEARCH_DEMO_RELATED]->(related:SearchDemoArticle)
RETURN article.code AS code,
       article.title AS title,
       score,
       collect(related.code) AS relatedCodes
ORDER BY score DESC;
```

Joining back to the property graph after search is a practical advantage of Neo4j. Note that each `MATCH` can multiply rows if a node has multiple relationships; use `collect()` or `DISTINCT` when you need one row per document.

### 4.2. Using `SEARCH` with New Cypher 25

Starting in **Neo4j 2026.09**, Cypher 25 supports `SEARCH` for full-text indexes. On current Neo4j versions and Cypher 25 sessions, this is the recommended option:

```cypher
MATCH (article)
SEARCH article IN (
  FULLTEXT INDEX search_demo_article_fulltext
  FOR 'graph'
  LIMIT 10
)
SCORE AS score
RETURN article.code AS code, article.title AS title, score
ORDER BY score DESC;
```

**Version constraint to remember:** `SEARCH` in this example requires **Cypher 25 and Neo4j 2026.09 or later**. `db.index.fulltext.queryNodes()` remains the compatible choice for Neo4j 5 or Cypher 5 queries; this procedure has been marked **deprecated in Cypher 25 since Neo4j 2026.10**. Therefore, when maintaining Java/Spring Data applications, check both the server version **and** the active Cypher version before changing syntax.

Do not expect a `MATCH ... WHERE article.body CONTAINS 'graph'` query to automatically use a full-text index. That is a regular string predicate; **full-text search must be invoked explicitly** via `SEARCH` or the appropriate procedure.

## 5. Same Keyword, Two Searches with Different Meanings

Compare three seemingly similar queries:

```cypher
// A. Exact substring in title, case-sensitive
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'Graph'
RETURN a.code AS code;
```

```cypher
// B. Substring in title, lowercase: does not match 'Graph'
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'graph'
RETURN a.code AS code;
```

```cypher
// C. Token 'graph' in title OR body, via full-text
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', 'graph'
)
YIELD node, score
RETURN node.code AS code, score
ORDER BY score DESC;
```

| Query | Expected Result | Reason |
| --- | --- | --- |
| A: `title CONTAINS 'Graph'` | G-101, G-102 | Two titles contain the capitalized substring `Graph` |
| B: `title CONTAINS 'graph'` | No rows | No title contains the exact lowercase substring |
| C: full-text `graph` | G-101, G-102, N-301 | Default analyzer recognizes the `graph` token in `title` or `body` |

This leads to two principles:

1. **An index does not "change" the semantics of a Cypher predicate.** A `TEXT INDEX` gives `CONTAINS` a chance to run faster, but does not turn it into word or fuzzy search.
2. **Full-text search is a different kind of lookup.** It uses analyzers, Lucene queries, and scoring; results can differ in both match scope and ordering.

## 6. Words, Phrases, Boolean Conditions, and Score in Full-Text Search

In full-text search, the input string is a **Lucene search expression**. The following examples use the procedure syntax so they run on Neo4j 5; on newer Cypher 25, you can place the equivalent expression inside the `FOR` clause of `SEARCH`.

### 6.1. Searching for a Single Token

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', 'cypher'
)
YIELD node, score
RETURN node.code AS code, score
ORDER BY score DESC;
```

Returns articles containing the `cypher` token in `title` or `body`. The goal is to find content containing this word, not to check whether the entire property equals `'cypher'`.

### 6.2. Searching for an Ordered Phrase

Wrap the phrase in **Lucene double quotes**, and place the entire expression inside a Cypher string:

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', '"graph modeling"'
)
YIELD node, score
RETURN node.code AS code, node.title AS title, score;
```

In the sample data, G-101 matches because its title contains the two consecutive tokens `Graph Modeling`. Phrase search **does not** mean the entire `title` equals `'graph modeling'`; the original string may contain other words.

### 6.3. Boolean Conditions

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', 'graph AND cypher'
)
YIELD node, score
RETURN node.code AS code, score
ORDER BY score DESC;
```

`AND` requires both tokens to match according to Lucene semantics across the indexed content. There are also `OR`, `NOT`, required `+`, and exclusion `-` operators. Do not treat this syntax as if it were a Cypher `WHERE` clause.

If input comes from users, distinguish **plain text keywords** from **Lucene query syntax**. Even when passed via a parameter to avoid Cypher string concatenation, Lucene special characters still retain search meaning. The application must decide whether to allow operators or escape/normalize input to search only plain keywords.

### 6.4. Understanding Relevance Score Correctly

`score` helps order records **within the same full-text query**. This score is not a correctness percentage, not a probability confidence, and should not be compared directly against vector search scores or other scoring systems.

A search system typically follows this flow: fetch a reasonable number of results, sort by `score`, then filter by access permissions, remove unsuitable content, and display titles/snippets. Relevance scores do not replace business rules.

## 7. Analyzers, Vietnamese Text, and Text Normalization

Unlike a text index, a full-text index lets you choose an **analyzer**. The analyzer governs tokenization, case folding, and possibly stop-word removal or language-specific rules. Choosing the wrong analyzer can cause large discrepancies between what users type and the tokens actually indexed.

List available analyzers on the server:

```cypher
CALL db.index.fulltext.listAvailableAnalyzers()
YIELD analyzer, description
RETURN analyzer, description
ORDER BY analyzer;
```

Example configuring an analyzer when creating another full-text index:

```cypher
CREATE FULLTEXT INDEX search_demo_article_english IF NOT EXISTS
FOR (a:SearchDemoArticle)
ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'english'
  }
};
```

The `english` analyzer applies English stop words and stemming; you should not use it by default for Vietnamese documents. For content such as `hệ thống đồ thị`, `mô hình hóa dữ liệu`, or `truy vấn đường đi`, test directly:

- Are Vietnamese diacritics preserved or folded as required?
- Are multi-syllable compound words split into tokens that cause overly broad matches or missed results?
- Should unaccented user queries match accented stored data?
- How strictly must acronyms like `SDN`, `Cypher`, and `Neo4j` be matched?

**Do not claim that the default analyzer understands Vietnamese or strips diacritics automatically.** You may need a custom analyzer, a normalized search property, or a combination of exact filters and full-text search. Normalization must be consistent at both write time and query time.

To look up **an identifier** or business token where ambiguity is unacceptable, use an exact lookup backed by an appropriate constraint or index. A full-text analyzer can alter matching behavior and should never substitute for a uniqueness constraint.

## 8. Number of Labels/Types, Properties, and Relationship Indexes

A text index is limited to one label/type and one `STRING` property per index. A full-text index can cover multiple properties and multiple labels/types:

```cypher
// Alternative example on a model containing both Article and Guide
CREATE FULLTEXT INDEX docs_all_fulltext IF NOT EXISTS
FOR (d:SearchDemoArticle|SearchDemoGuide)
ON EACH [d.title, d.body, d.summary];
```

This is an extended schema example; the sample data in Section 2 only has `SearchDemoArticle`. With a full-text index like this, a node only needs **at least one** specified label and **at least one** valid indexed property to be discoverable. Unlike a *composite range index*, which often requires all constituent properties to be present, full-text aggregates text sources for search.

Both index types support indexing **relationship properties**. Example creating a text index on `note`:

```cypher
CREATE TEXT INDEX search_demo_note_text IF NOT EXISTS
FOR ()-[r:SEARCH_DEMO_RELATED]-()
ON (r.note);
```

```cypher
MATCH ()-[r:SEARCH_DEMO_RELATED]->()
WHERE r.note CONTAINS 'Graph'
RETURN r.note AS note;
```

If you need token search on relationship notes with `score`, use a full-text index on relationships:

```cypher
CREATE FULLTEXT INDEX search_demo_relation_fulltext IF NOT EXISTS
FOR ()-[r:SEARCH_DEMO_RELATED]-()
ON EACH [r.note];
```

```cypher
// Neo4j 5 / Cypher 5
CALL db.index.fulltext.queryRelationships(
  'search_demo_relation_fulltext', 'graph'
)
YIELD relationship, score
RETURN relationship.note AS note, score
ORDER BY score DESC;
```

Some use cases only need to search a description stored on a relationship without querying an entire path first. If you need to expand into the graph, retrieve endpoint nodes with `startNode(relationship)` and `endNode(relationship)` or bind the relationship variable in a `MATCH` pattern.

## 9. Monitoring Index Status and Viewing Execution Plans

After `CREATE INDEX`, Neo4j needs time in **POPULATING** state to build the index from existing data. Only rely on the index once it is `ONLINE`.

```cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties
RETURN name, type, state, populationPercent, labelsOrTypes, properties
ORDER BY name;
```

To filter by specific index type:

```cypher
SHOW TEXT INDEXES;
```

```cypher
SHOW FULLTEXT INDEXES;
```

When investigating whether a Cypher query uses a text index:

```cypher
EXPLAIN
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'Graph'
RETURN a.code, a.title;
```

`EXPLAIN` shows the estimated plan without executing the query. `PROFILE` executes the query and reports actual Rows and DB Hits metrics:

```cypher
PROFILE
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS 'Graph'
RETURN a.code, a.title;
```

In the actual plan, check the index access operator, the index name used, the number of Rows, and the cost. With only four sample nodes, the planner may pick a different strategy than expected; never use tiny datasets to conclude that an index will always speed up queries. Benchmark using representative data volume and distribution.

**Having both RANGE and TEXT indexes:** the same `title` property can have both index types, but adding indexes increases storage and write-update overhead. Do not duplicate indexes just because they have different names; examine your actual queries (`CONTAINS`, `ENDS WITH`, equality, prefix, sort) and planner plans.

## 10. Write Consistency and Operational Limits

Full-text indexes update as nodes and relationships change. Under standard configuration, index updates are tied to the transaction. You can **optionally enable eventual consistency** for a full-text index, offloading index updates to a background thread:

```cypher
CREATE FULLTEXT INDEX search_demo_eventual_fulltext IF NOT EXISTS
FOR (a:SearchDemoArticle)
ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    `fulltext.eventually_consistent`: true
  }
};
```

In exchange, a newly committed record may not appear immediately in full-text results. If an application flow requires **read-your-writes search visibility immediately after saving**, evaluate this setting carefully. Neo4j provides a procedure to wait for pending eventually-consistent full-text updates to be applied:

```cypher
CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh();
```

Do not equate an "eventual index" with uncommitted graph data: this concerns **when search index contents synchronize**, not replacing Neo4j's transaction guarantees.

Both text indexes and full-text indexes incur storage and update overhead when properties change. Full-text indexes also incur analyzer costs, multi-token indexing, and potential resource overhead when searching or sorting by `score`. Measure performance with realistic data and monitor disk usage, write throughput, and search latency before going to production.

## 11. Applying This in Java Driver and Spring Data Neo4j

Choosing an index depends on **query intent**, independent of the framework executing Cypher:

- **Exact key lookup or substring filter:** use Cypher `MATCH ... WHERE` with parameter `$term`; the planner chooses the appropriate index. Fields such as `code`, user IDs, or order codes are usually better suited to range indexes/constraints.
- **Searching articles by content:** use `SEARCH` in Cypher 25 environments or full-text procedures on Neo4j 5/Cypher 5; pass keywords via parameters, retrieve `score`, and map the returned results.
- **Combining content search with relationships:** obtain matched nodes from full-text search, then traverse relationships and aggregate before returning DTOs if a document has multiple paths.

Example parameterized queries for the Neo4j Java Driver (Cypher part):

```cypher
MATCH (a:SearchDemoArticle)
WHERE a.title CONTAINS $term
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

```cypher
CALL db.index.fulltext.queryNodes(
  'search_demo_article_fulltext', $query
)
YIELD node, score
RETURN node.code AS code, node.title AS title, score
ORDER BY score DESC
LIMIT $limit;
```

In the Java layer, bind `term` or `query` using Driver parameters; with Spring Data Neo4j, you can use `@Query` and map a projection containing `code`, `title`, and `score`. Parameter binding prevents arbitrary Cypher string concatenation, **but** `$query` is still interpreted as a Lucene query by the full-text parser; take special care if your application allows users to type characters like `:`, `*`, `"`, `AND`, or `OR`.

For search APIs, designing two distinct parameters is often helpful: `exactText` for literal string matching and `searchQuery` for content search. Mixing both intents behind a single `contains` flag makes search results harder to explain to users.

## 12. How to Decide in a Neo4j Project

| Business Question | Recommendation | Why |
| --- | --- | --- |
| Find product with exact code `P-004` | Range index or appropriate uniqueness constraint | Identifiers require exact matching and uniqueness guarantees |
| Find documents whose title contains substring `Graph` | Text index on `title` | Matches the `CONTAINS` operator |
| Find documents whose title ends with `Guide` | Text index on `title` | `ENDS WITH` is a case text indexes optimize well |
| Find all articles discussing `graph` in title/body, ranked by relevance | Full-text index on `title`, `body` | Tokenization, multi-property search, relevance `score` |
| Search for the phrase `graph modeling` | Full-text index + phrase query | Matches tokens in order without requiring the property to equal the whole phrase |
| Search by semantics ("passages with similar meaning using different words") | Consider vector search / dedicated hybrid design | Full-text is **lexical** search; it does not understand embeddings/meaning like vector search |
| Newly saved records must appear immediately in search | Avoid enabling full-text eventual consistency unless handled explicitly | Background indexing can lag behind transactions |

### Self-Check

1. Why can `CONTAINS 'graph'` on `title` return empty results while a full-text query `graph` finds articles containing `Graph`?
2. Why can't you simply create one text index on `title` and expect it to search `body` and return `score`?
3. If you need to look up account ID `USR-0001` with absolute precision, which index/constraint should you choose?
4. After creating a full-text index, why might `SHOW FULLTEXT INDEXES` report `POPULATING` instead of `ONLINE`?
5. Why must you review tokenization and diacritics when implementing Vietnamese search?
6. If your system runs Cypher 5, why might the new `SEARCH` example fail to run?

**Brief answers:** (1) `CONTAINS` performs a case-sensitive substring check; a full-text analyzer matches tokens and usually lowercases text. (2) A text index only accelerates Cypher predicates on a single property; it does not compute relevance scores. (3) Range index / uniqueness constraint is suited for exact keys. (4) The index is still being built from existing data. (5) The default analyzer does not guarantee your product's Vietnamese search rules. (6) Full-text `SEARCH` requires Cypher 25 and Neo4j 2026.09+; Cypher 5 uses procedures.

## 13. References

- [Neo4j Cypher Manual — Create performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/): text index syntax, scope, and supported predicates.
- [Neo4j Cypher Manual — Full-text indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/full-text-indexes/): analyzers, Lucene queries, `SEARCH`/procedures, `score`, and eventual consistency.
- [Neo4j Cypher Manual — The impact of indexes on query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/): when the planner picks text vs. range indexes, and how to read execution plans.

**Remember:** **a text index answers "does this property satisfy this string predicate?"**, whereas **a full-text index answers "which content has tokens that best match this search expression?"**. Choosing the right index type determines result semantics, how Cypher is written, and the operational cost of your graph system.
