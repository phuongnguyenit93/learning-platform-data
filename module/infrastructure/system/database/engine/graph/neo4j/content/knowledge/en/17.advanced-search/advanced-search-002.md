# Text Analyzers, Relevance Scores, and Limitations of Full-Text Search

*Full-text search* in Neo4j helps find nodes or relationships based on **text content**: article titles, product descriptions, event notes, discussion content, and more. Instead of requiring an exact string match, the system can split text into words, process them using an **analyzer**, match them against the query, and return a **relevance score** to rank the results.

This lesson belongs to the **Advanced Search** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The module uses the **property graph** model, Cypher, indexes/constraints, the Java Driver, and Spring Data Neo4j to store and query connected data. In this context, a full-text index helps quickly locate a candidate set of nodes or relationships by keyword, and then graph relationships are used to further filter, navigate, or aggregate the results.

After this lesson, you will be able to:

- Explain how **tokenization**, case normalization, **stop words**, **stemming**, and analyzer language affect results.
- Create a full-text index, inspect available analyzers, query with Cypher, and interpret `score`.
- Design search with ranking, business filtering, and pagination.
- Identify the limitations of full-text search regarding semantics, languages, consistency, security, and performance.
- Choose when to use a full-text index, a standard index, or vector search.

## 1. Where Does Full-Text Search Fit in a Property Graph?

Suppose a content management application has these nodes:

~~~text
(:Author)-[:WROTE]->(:Article {title, body, lang, published})
(:Article)-[:TAGGED_WITH]->(:Topic {name})
(:Article)-[:RELATED_TO]->(:Article)
~~~

A request such as "find articles about Neo4j, then display related topics" has two parts:

1. **Text search:** retrieve `Article` nodes whose `title` or `body` matches the keywords, along with a relevance score.
2. **Graph traversal:** from the matched nodes, follow `TAGGED_WITH`, `RELATED_TO`, or other relationships.

This is the strength of combining full-text search with Cypher: text search identifies the candidate set, while the property graph expresses the connections and business conditions to evaluate next.

| Mechanism | Suitable When | Do Not Expect |
| --- | --- | --- |
| Property matching with `=` and standard range/text indexes | Looking up identifiers, normalized emails, time ranges, and exact conditions. | Automatic tokenization, stemming, or relevance ranking. |
| Full-text index | Searching words/phrases in titles and descriptions; supporting text query syntax, word analysis, and ranking. | Full contextual semantic understanding like a language model; uniqueness enforcement. |
| Vector index | Retrieving content similar in embedding representation, once the system has generated suitable vectors. | Guaranteed exact keyword matching or exact structured-data lookup. |

Neo4j uses Lucene for full-text indexes. Unlike some standard indexes that the Cypher query planner considers automatically, full-text indexes are typically queried **explicitly via procedures** such as `db.index.fulltext.queryNodes` or `db.index.fulltext.queryRelationships`. Creating a full-text index does not mean every `CONTAINS` expression in `MATCH ... WHERE` will automatically use that index.

## 2. Analyzer: Turning Text into Searchable Tokens

An **analyzer** is the text processor used both when indexing data and when parsing search queries. Depending on the analyzer, the pipeline may include:

~~~text
Original text
   |
   v
Tokenizer: splits into tokens
   |
   v
Token filters: lowercasing, stop-word removal, stemming...
   |
   v
Tokens stored and matched in the full-text index
~~~

The exact steps **vary by analyzer**; this diagram is a general model, not a claim that every analyzer applies all filters.

### 2.1. Tokenization

For the phrase "Graph databases and Neo4j", a word-based analyzer might split it into tokens close to `graph`, `databases`, `and`, `neo4j`. A `keyword` analyzer may treat the **entire string** as a single token. Therefore, choosing an analyzer directly affects whether partial-text or whole-string search works.

For languages such as Vietnamese, **whitespace boundaries are not always lexical word boundaries**. For example, "cơ sở dữ liệu" consists of multiple syllables yet expresses a single technical term. An analyzer that only splits on whitespace may not recognize it as a single semantic unit; this affects phrase queries, synonyms, and result evaluation.

### 2.2. Case Normalization

Many analyzers normalize `Neo4j` and `neo4j` to similar token representations, enabling case-insensitive search. However, **you must not assume all analyzers behave identically**, especially `keyword` analyzers or differently configured analyzers. Similarly, handling Vietnamese diacritics does not automatically mean "accent folding"; you must test pairs like `đồ thị`/`do thi` and `cơ sở`/`co so` on the actual analyzer in use.

### 2.3. Stop Words

Stop words are common words that an analyzer may drop from the token set, such as certain function words in English. If you choose an English analyzer with a stop-word list, a query consisting solely of removed words may return very few or no results.

Not every analyzer removes stop words. For example, the name `standard-no-stop-words` indicates processing without stop-word removal. Exact behavior also depends on the word list and implementation version.

### 2.4. Stemming

Stemming reduces morphological variants toward an approximate root form—for instance, an English analyzer may process variants such as "connect", "connected", and "connecting" in a way that broadens search matches. Stemming is **not semantic translation** and does not replace synonym search. It can also cause overly broad matches or be unsuitable for certain proper nouns and technical terms.

### 2.5. Listing Available Analyzers

Before choosing an analyzer, query the database you are running:

~~~cypher
CALL db.index.fulltext.listAvailableAnalyzers();
~~~

This procedure lists available analyzer names and descriptions (columns may vary by version). In Neo4j versions that support them, you can choose analyzers such as `english` or `standard-no-stop-words`; **do not assume a built-in Vietnamese analyzer exists** unless you see it in the output.

Analyzer selection should be based on **data language, the types of queries users enter, and empirical testing**. For example, an index for English documents may prefer an English analyzer to handle word variants. A multilingual corpus must evaluate the trade-offs between a general analyzer, language-specific splitting, or custom pre-indexing normalization.

## 3. Hands-On: Creating a Dataset and Full-Text Index

Creation/deletion commands in this lesson should only be run on a **learning database**. The example uses the `SearchDoc` label so it does not affect production business nodes.

### 3.1. Preparing Five Sample Documents

~~~cypher
UNWIND [
  {id: 'D01', title: 'Neo4j and Cypher Basics',
   body: 'Guide to querying nodes and relationships in a graph.', active: true},
  {id: 'D02', title: 'Optimizing Neo4j Queries',
   body: 'Analyzing Cypher query plans and using indexes.', active: true},
  {id: 'D03', title: 'Graph Data Modeling',
   body: 'Designing nodes, relationships, and property graphs.', active: true},
  {id: 'D04', title: 'Relational Databases',
   body: 'Introduction to SQL, tables, and foreign keys.', active: true},
  {id: 'D05', title: 'Neo4j full-text search',
   body: 'Searching text with Lucene, analyzers, and relevance scores.', active: false}
] AS row
MERGE (d:SearchDoc {docId: row.id})
SET d.title = row.title,
    d.body = row.body,
    d.active = row.active;
~~~

`MERGE` makes the exercise repeatable when each `docId` corresponds to one node. In real data, use a uniqueness constraint on the business key to protect against concurrent writes; `MERGE` alone does not replace a constraint.

### 3.2. Creating a Named Full-Text Index

~~~cypher
CREATE FULLTEXT INDEX search_docs_ft IF NOT EXISTS
FOR (d:SearchDoc)
ON EACH [d.title, d.body]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'standard-no-stop-words'
  }
};
~~~

In this snippet, `ON EACH [d.title, d.body]` specifies that both text properties are indexed. If a node lacks `title` but has a valid string `body`, it can still be indexed. This index **does not enforce uniqueness** on titles.

Neo4j indexes supported text properties (strings or supported lists of strings) for full-text search; it does not convert arbitrary data types into searchable text. When a node has multiple labels, it only needs to match the declared label scope to be indexed by the corresponding index.

The analyzer configuration key `fulltext.analyzer` is wrapped in backticks because it contains a dot. In this example, we select `standard-no-stop-words` to easily observe keyword queries on content (including Vietnamese corpora); this choice **does not mean Neo4j understands Vietnamese semantic structure**.

### 3.3. Waiting for Index Readiness and Inspecting Metadata

After creation, an index may take time to index existing data. In a practice environment, you can wait for database indexes to finish populating:

~~~cypher
CALL db.awaitIndexes();
~~~

Or inspect index metadata:

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties, options
WHERE name = 'search_docs_ft'
RETURN name, type, state, populationPercent, labelsOrTypes, properties, options;
~~~

Verify that `type` is `FULLTEXT`, `state` is `ONLINE`, the properties are correct, and `options` reflects the chosen analyzer. Values and metadata fields can vary across Neo4j versions; always check against the actual database rather than relying solely on the success message from `IF NOT EXISTS`.

### 3.4. Querying Keywords and Returning Relevance Scores

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', 'Neo4j')
YIELD node, score
RETURN node.docId AS maTaiLieu,
       node.title AS tieuDe,
       score AS diemLienQuan
ORDER BY diemLienQuan DESC, maTaiLieu ASC
LIMIT 10;
~~~

With the sample data, documents containing the word "Neo4j" such as D01, D02, and D05 are matching candidates. **Do not hardcode exact score values or rankings in study materials**, as scores depend on the analyzer, corpus characteristics, and how Lucene computes scores in the running version. D05 can still appear even though `active = false`, because a text search index does not inherently understand publication status.

## 4. What Does the Relevance Score Mean?

The `db.index.fulltext.queryNodes` procedure returns `node` along with a numeric `score`. This score is a **ranking measure of match quality according to Lucene's text search mechanism**, not a probability of content correctness, document trustworthiness, or absolute semantic similarity.

Factors that can influence the score:

- **Matched keywords:** the number and characteristics of matched tokens.
- **Token rarity:** a rare term in the indexed corpus may contribute differently than a very common term.
- **Text length and distribution:** short vs. long fields and token frequency may be weighted differently.
- **Query syntax:** keyword combinations, phrases, and *boost* weights alter how scores are computed.
- **Index state:** adding, modifying, or deleting documents, or changing analyzers/indexes, can change scores and ordering.

Therefore, interpret `score` within **the same query and the same index at a given point in time**. Do not assume that `score = 3.5` means the document is "35% relevant", or that 3.5 in two different indexes carries the same meaning.

### 4.1. Deterministic Tie-Breaking When Scores Are Equal

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', 'Cypher')
YIELD node, score
RETURN node.docId AS maTaiLieu,
       node.title AS tieuDe,
       score
ORDER BY score DESC, maTaiLieu ASC
LIMIT 5;
~~~

Sort primarily by `score DESC` to get the most relevant results, and secondarily by `docId ASC` (`maTaiLieu ASC`) to establish a deterministic order when scores tie. Using `LIMIT 5` without a deterministic order at the end of the query makes display and pagination unpredictable if additional Cypher steps are added.

### 4.2. Should You Set a Score Threshold?

You can filter by a threshold in a calibrated use case:

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', $query)
YIELD node, score
WITH node, score
WHERE score >= $minScore
RETURN node.docId AS maTaiLieu, node.title AS tieuDe, score
ORDER BY score DESC, maTaiLieu ASC
LIMIT $topN;
~~~

Parameters are supplied by the application; `$minScore` and `$topN` **have no default values** in this Cypher query. Validate data types and value ranges before calling.

A score threshold must be determined by empirical evaluation on representative queries and data. It may need adjustment when changing analyzers, indexed properties, document collections, or deployment versions. A fixed threshold copied from a tutorial example can easily drop useful results in a real system.

## 5. Search Syntax: Keywords, Phrases, and Combinations

The query parameter of full-text procedures uses Lucene-supported search syntax. Common forms include:

| Intent | Example Query String | Notes |
| --- | --- | --- |
| Keyword | `Neo4j` | Searches for matching tokens per the index analyzer. |
| Both words required | `Neo4j AND Cypher` | Both conditions must be satisfied according to query semantics. |
| Either word | `Neo4j OR Cypher` | Broadens the candidate set. |
| Phrase | `"property graph"` | Searches for a sequence of tokens/phrase; results depend on tokenization. |
| Field-specific search | `title:Neo4j` | Applies to the corresponding indexed property field. |
| Prefix | `graph*` | Expands by token prefix; can be expensive. |
| Fuzzy character match | `grahp~1` | Fuzzy matching can help with typos; not the same as semantic search. |
| Boost weight | `title:Neo4j^3 OR body:Neo4j` | Boost prioritizes title matches; does not guarantee absolute ranking. |

Direct example for phrase search:

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', '"property graph"')
YIELD node, score
RETURN node.docId AS maTaiLieu, node.title AS tieuDe, score
ORDER BY score DESC, maTaiLieu ASC;
~~~

Example prioritizing titles:

~~~cypher
CALL db.index.fulltext.queryNodes(
  'search_docs_ft',
  'title:Neo4j^3 OR body:Neo4j'
)
YIELD node, score
RETURN node.docId AS maTaiLieu, node.title AS tieuDe, score
ORDER BY score DESC, maTaiLieu ASC
LIMIT 10;
~~~

**Important distinction:** `AND` and `OR` inside the query string are Lucene query syntax, not Cypher `WHERE` clauses. Operators, special characters, wildcards, and quotation marks must be handled properly. User-entered queries should pass through syntax validation, escaping, or a query builder aligned with product features. Use Cypher parameters to avoid dynamic Cypher string concatenation:

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', $searchQuery)
YIELD node, score
RETURN node.docId AS maTaiLieu, node.title AS tieuDe, score
ORDER BY score DESC, maTaiLieu ASC
LIMIT $pageSize;
~~~

Passing `$searchQuery` protects the Cypher statement structure from direct string interpolation, **but it does not automatically neutralize Lucene operators inside the parameter value**. If the application intends to match the literal text typed by a user, it must control how special characters are interpreted by design.

## 6. Result Limits, Business Filtering, and Pagination

Search UIs usually display only the first 10–20 documents. However, you must establish the exact order of **search → filter → rank → limit**.

### 6.1. Filtering Before LIMIT

Document D05 has `active = false`. If the UI only displays active documents:

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', $searchQuery)
YIELD node, score
WITH node, score
WHERE node.active = true
RETURN node.docId AS maTaiLieu,
       node.title AS tieuDe,
       score
ORDER BY score DESC, maTaiLieu ASC
LIMIT $pageSize;
~~~

Placing `WHERE node.active = true` before the limit retrieves **up to N active documents** from the matching results. If you limit first and then filter, dropped documents can leave the page showing fewer than N results even when valid results exist further down.

However, filtering in Cypher **after** a full-text query may require processing many hits to gather enough qualifying rows. On large datasets, evaluate the query plan, access-control design, and index structure to avoid scanning too many candidates.

### 6.2. Combining Text Search with Graph Paths

Suppose a real application has `(:Article)-[:TAGGED_WITH]->(:Topic)`. A query can search articles via a full-text index `article_text_ft` and then check topics:

~~~cypher
CALL db.index.fulltext.queryNodes('article_text_ft', $query)
YIELD node AS article, score
MATCH (article)-[:TAGGED_WITH]->(topic:Topic)
WHERE article.published = true
  AND topic.name = $topicName
WITH DISTINCT article, score
RETURN article.title AS tieuDe, score
ORDER BY score DESC, tieuDe ASC
LIMIT $topN;
~~~

The index `article_text_ft` is an illustrative name for a real application, **not the index created for `SearchDoc` in Section 3**. Here, `DISTINCT` prevents duplicate articles if the model has multiple matching relationships or paths in the query. When adding `MATCH` or aggregations, verify that row multiplicity and `score` semantics are preserved before limiting.

### 6.3. Score-Based Pagination

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', $searchQuery)
YIELD node, score
WITH node, score
WHERE node.active = true
RETURN node.docId AS maTaiLieu,
       node.title AS tieuDe,
       score
ORDER BY score DESC, maTaiLieu ASC
SKIP $offset
LIMIT $pageSize;
~~~

With `$offset = 0` and `$pageSize = 10`, the application fetches the first page; `$offset = 10` fetches the next page. Parameters must be non-negative integers, and maximum `pageSize` should be capped per API policy.

Note that if data or indexes change between two reads, **scores and rankings can shift**, causing duplicate or skipped records across pages. Large `SKIP` offsets can also slow down queries. For order-sensitive results, consider load-more experiences, capping pagination depth, caching results, or snapshot/cursor solutions designed and validated against current scoring behavior. Do not treat `score` as an immutable pagination key.

## 7. Practical Limitations of Full-Text Search

### 7.1. Lexical Matching Is Not Semantic Understanding

A query like "how to speed up a graph database" might miss an article using "optimizing Cypher queries" even though their meanings are close, if there are no overlapping tokens or expansion rules. A full-text index **does not inherently understand synonyms, user intent, or paraphrased content**.

A system can combine full-text search with vector search or a reranking layer, but quality, cost, and data scope must be evaluated. Those techniques do not replace access-control checks and business conditions on the graph.

### 7.2. Analyzers Do Not Automatically Solve Every Language

Choosing `english` for Vietnamese content can cause issues with stop words, stemming, or tokenization. Conversely, a generic analyzer may lack English morphological handling. For multilingual corpora, consider splitting indexes by language-specific node sets/labels, normalizing data, configuring available analyzers, or using a specialized search tier if complex word segmentation is needed.

Build an evaluation query suite containing accent errors, proper nouns, compound words, abbreviations, and multilingual content. Never claim "full Vietnamese support" just because a single accented query returns results.

### 7.3. A Full-Text Index Is Not a Data Constraint

A full-text index does not guarantee unique emails, presence of creation dates, valid property types, or valid relationships. Those invariants require constraints, business validation, and proper data modeling. An unindexed property, null value, or unsupported type may contribute no tokens; an index does not automatically raise data-validation errors the way constraints do.

### 7.4. It Is Not an Arbitrary Substring Query

An analyzer may split strings at punctuation, drop stop words, or transform tokens. Thus, full-text search differs from checking "does string A appear verbatim inside B?". Overly broad wildcard queries (especially with empty prefixes or leading wildcards) can consume significant resources. If you need to look up order codes, normalized phone numbers, or exact identifiers, standard indexes and `=` are usually clearer and more appropriate.

### 7.5. Scores Are Not Arbitrarily Comparable Across Queries or Indexes

`score` is a ranking signal, not an absolute quality metric. Changing the document corpus, adding properties, changing analyzers, or upgrading Lucene can shift scores. Do not take `score` values from different indexes and sort them together as if they share the same scale without a calibration method.

### 7.6. Safety Controls and Resource Limits Are Mandatory

Users can enter excessively long queries, many `OR` clauses, broad wildcards/fuzzy terms, or special expressions that inflate execution cost. Applications should cap query length and complexity, validate pagination parameters, enforce timeouts and result limits, and record performance telemetry in production.

If data includes **tenants** or differing read permissions, results must be filtered by permissions and user context in a trusted layer. Never expose `score`, content, or result counts for unauthorized documents. Post-procedure tenant filtering must be evaluated for correctness, resource consumption, and potential information leakage via timing or metadata if strict isolation is required.

## 8. Consistency, Index Maintenance, and Changing Analyzers

### 8.1. Synchronous Default vs. Eventually Consistent Updates

In standard full-text index configuration, changes are applied alongside the database's index update mechanism. Neo4j also provides an **eventually consistent** option to move full-text index updates off the synchronous write path:

~~~cypher
CREATE FULLTEXT INDEX search_docs_async_ft IF NOT EXISTS
FOR (d:SearchDoc)
ON EACH [d.title, d.body]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'standard-no-stop-words',
    `fulltext.eventually_consistent`: true
  }
};
~~~

With this option, applications **must not assume writes are immediately searchable**: updates may enter the index asynchronously afterward. If a test needs to wait for eventually consistent updates to finish, Neo4j provides a procedure:

~~~cypher
CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh();
~~~

This procedure synchronizes for testing or operational purposes at the point it is called; it should not be called after every write request in a production application. Performance, update visibility, and transactional semantics should be verified on your actual Neo4j version.

### 8.2. Changing an Analyzer Is a Schema Change

The analyzer is configured when creating the index. When you need to change tokenization or stemming, plan to **create a new index with a new name**, verify it reaches `ONLINE`, test it against the evaluation query suite, switch the application to the new index, and only then drop the old index. This gradual cutover can reduce read disruption if schema and resources allow.

Example creating a second index with an English analyzer for a **language-appropriate** dataset:

~~~cypher
CREATE FULLTEXT INDEX search_docs_english_ft IF NOT EXISTS
FOR (d:SearchDoc)
ON EACH [d.title, d.body]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'english'
  }
};
~~~

This is a syntax example; **do not deploy an English analyzer across an entire Vietnamese corpus in a study exercise without measuring quality**. Even if the new index covers the same label/properties as the old index, the two indexes can still return different results because of how tokens are analyzed.

After completing the cutover and confirming no read paths still reference the old name:

~~~cypher
DROP INDEX search_docs_ft IF EXISTS;
~~~

`DROP INDEX` removes the index structure; **it does not delete nodes or underlying properties**. However, queries still referencing the dropped index name will fail. Manage index renames and updates in Java Driver / Spring Data Neo4j code through a clear migration process.

### 8.3. Troubleshooting Index Issues

When a search returns no results even though data exists, check:

1. Was the index created on the right database, label/type, and properties?
2. Is the index state `ONLINE`, or were there errors during population or updates?
3. How does the current analyzer tokenize both the document text and the query?
4. Do the properties have the right string / string-list type and non-null values?
5. Is eventual consistency enabled, delaying visibility of newly written records?
6. After candidates are found, are `WHERE`, `MATCH`, `DISTINCT`, or `LIMIT` clauses filtering rows out?

Do not start by dropping and recreating the index before identifying the root cause; rebuilding on large datasets can be time- and resource-intensive.

## 9. Searching on Relationships

Full-text indexes can also be created on text properties of relationships. For a business model storing reviews as `[:REVIEWED {comment}]`:

~~~cypher
CREATE FULLTEXT INDEX review_comments_ft IF NOT EXISTS
FOR ()-[r:REVIEWED]-()
ON EACH [r.comment]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'standard-no-stop-words'
  }
};
~~~

Query using the dedicated procedure for relationships:

~~~cypher
CALL db.index.fulltext.queryRelationships('review_comments_ft', $query)
YIELD relationship, score
RETURN relationship.comment AS binhLuan, score
ORDER BY score DESC
LIMIT $topN;
~~~

If you need to know who reviewed which product, continue from the start/end nodes of the relationship and enforce access control on the graph. Relationship scores should not be compared directly with node scores from a different index because their scoring contexts differ.

## 10. Using from Java Driver and Spring Data Neo4j

Applications can use the Java Driver to invoke procedures, pass keywords via parameters, and process the returned `node` and `score` rows. The abbreviated example below retrieves only the fields needed for display:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

import java.util.List;
import java.util.Map;

public class SearchRepository {
    private final Driver driver;

    public SearchRepository(Driver driver) {
        this.driver = driver;
    }

    public List<Record> search(String query, int limit) {
        if (query == null || query.isBlank() || limit < 1 || limit > 50) {
            throw new IllegalArgumentException("Invalid query or limit");
        }

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.run("""
                    CALL db.index.fulltext.queryNodes('search_docs_ft', $query)
                    YIELD node, score
                    WHERE node.active = true
                    RETURN node.docId AS docId, node.title AS title, score
                    ORDER BY score DESC, docId ASC
                    LIMIT $limit
                    """, Map.of("query", query, "limit", limit)).list();
        }
    }
}
~~~

This snippet assumes the application initializes and manages the `Driver` lifecycle; the `neo4j` database name is illustrative. In a real project, map `Record` to a DTO and handle observable errors and timeouts. Business-level character length caps are omitted here; production applications must control both query length and Lucene syntax complexity.

With Spring Data Neo4j, you can execute a Cypher query calling the procedure through a repository or client according to your library version. Annotating entities for object mapping does not automatically create tokenization rules, scores, or the desired full-text index; index schemas still need explicit management and verification.

## 11. Common Mistakes

| Symptom | Common Explanation | Fix |
| --- | --- | --- |
| Document contains the search term but yields no results | Analyzer dropped/transformed the token, index is not `ONLINE`, or index does not cover the property. | Inspect analyzer, index state, labels/types/properties, and test with a minimal query. |
| Searching `Neo4j` works, but unaccented Vietnamese search returns nothing | Analyzer's diacritic/language handling does not match expectations. | Test with a sample query suite; normalize or design an appropriate analyzer strategy. |
| Newly added document is not immediately searchable | Index is still populating or uses eventual consistency. | Check index state; if using eventual consistency, measure lag or await refresh when needed. |
| Scores shift as data grows | Scores depend on corpus statistics and Lucene ranking mechanics. | Evaluate ranking and search quality; avoid arbitrary fixed score thresholds. |
| Page 2 contains duplicate records from Page 1 | Scores/index/data changed between requests; tie-breaking order was not deterministic. | Add a secondary sort key, manage result stability, and refine pagination strategy. |
| Limiting to 10 then filtering permissions leaves only 2 documents | `LIMIT` was applied before business filtering. | Filter before limiting; evaluate performance and data isolation. |
| Wildcard queries run very slowly | Expression expands to too many tokens/hits. | Restrict syntax, timeouts, and data scope, and benchmark under realistic load. |
| `WHERE title CONTAINS ...` does not use the full-text index | Full-text indexes are called explicitly via procedures and work differently from Cypher string predicates. | Use `db.index.fulltext.queryNodes` or choose an index and query suited to the requirement. |
| Changed analyzer in code, but results didn't change | Updated application code/query without rebuilding the index with the new analyzer. | Create a new index with the new config, verify it, and perform a controlled cutover. |

## 12. Practice Exercises

**Exercise 1 — Explain analyzer behavior:** Given two queries `Neo4j AND Cypher` and `"Neo4j Cypher"`, explain why the same document might match the first query but not the second. Then test them on `SearchDoc` and observe the actual behavior of the selected analyzer.

**Exercise 2 — Top 3 public articles:** Use `search_docs_ft` to find documents related to `Neo4j`, keeping only nodes with `active = true`, returning at most three results ordered by descending score with ties broken by `docId`.

Hint:

~~~cypher
CALL db.index.fulltext.queryNodes('search_docs_ft', 'Neo4j')
YIELD node, score
WITH node, score
WHERE node.active = true
RETURN node.docId AS docId, node.title AS title, score
ORDER BY score DESC, docId ASC
LIMIT 3;
~~~

**Exercise 3 — Display optimization:** A search page uses `$offset = 10000` and `$pageSize = 20` while content is updated continuously. Explain two issues regarding cost and order stability, then propose how to cap pagination depth and validate the approach.

**Exercise 4 — Vietnamese document corpus:** Design a test suite covering unaccented queries, accented queries, compound words, proper nouns, and typos. Describe how to compare a generic analyzer against another analyzer (if available) based on **precision** (fraction of returned results that are useful), **recall** (fraction of useful results found), and query latency. Do not draw conclusions from a single sample query.

**Exercise 5 — Index migration:** Describe a plan to change the analyzer for a live user-facing index: create the new index, wait for `ONLINE`, run the test suite, switch read traffic, monitor quality and performance, and drop the old index once safe.

Once finished, ask yourself three questions before building any search feature in Neo4j: **Does the analyzer process text appropriately for the language and how users search? Is `score` treated as a ranking signal rather than an absolute value? Are access controls, index update semantics, and resource limits properly enforced?** When these questions are clear, full-text search becomes a practical tool to guide users from text directly into the connected data of a property graph.
