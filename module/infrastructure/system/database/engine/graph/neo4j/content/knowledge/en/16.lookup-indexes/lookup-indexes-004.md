# Text Indexes and Supported String Search Patterns

## 1. What Problem Does a Text Index Solve in Neo4j?

In Neo4j's **property graph** model, both nodes and relationships can carry string (`STRING`) properties: article titles, movie names, product codes, emails, relationship descriptions, and so on. When a Cypher query must filter strings by prefix, suffix, or substring across many graph elements, reading all nodes or relationships and checking each value can be expensive.

A **TEXT index** is a *performance index* on **a single string property**, helping the Cypher query planner locate candidates more efficiently. It is especially useful for `CONTAINS` and `ENDS WITH`. Developers still write ordinary `MATCH ... WHERE ...` queries; the planner decides whether to use the index based on predicate type, available indexes, and estimated cost.

In the **Lookup Indexes** chapter, distinguish four concepts that are often loosely called "indexes":

| Index Type | Indexed Data | Typical Use Cases | How It Is Used |
|---|---|---|---|
| **Token lookup** (`LOOKUP`) | Node labels or relationship types | Finding nodes by label, relationships by type | Planner uses it for `MATCH (n:Label)` or `MATCH ()-[r:TYPE]->()` |
| **Text** (`TEXT`) | A single `STRING` property of a node or relationship | Substring `CONTAINS`, suffix `ENDS WITH` | Planner uses it for string predicates |
| **Range** (`RANGE`) | Properties used for comparisons and sorting | `=`, `IN`, value ranges, prefix `STARTS WITH` | Planner uses it for matching predicates |
| **Full-text** (`FULLTEXT`) | One or more text properties | Word/phrase search, text analysis, relevance scoring | Explicit full-text queries using the Neo4j version's API/syntax |

The chapter title "Lookup Indexes" **does not mean a TEXT index is a token lookup index**. Token lookup does not index property contents; meanwhile, a TEXT index does not replace ranked keyword search provided by FULLTEXT.

### Learning Outcomes

After this lesson, you will be able to:

1. Create, inspect the status of, and drop TEXT indexes for node or relationship properties.
2. Correctly write `STARTS WITH`, `ENDS WITH`, `CONTAINS`, `=`, and `IN` predicates, and predict results on sample data.
3. Distinguish conditions *supported by a TEXT index* from cases where *the planner actually selects the TEXT index*.
4. Use `EXPLAIN`/`PROFILE` to inspect plans and recognize limitations regarding data types, case sensitivity, and accent-insensitive searches.

## 2. Mechanism and Limitations of a TEXT Index

Neo4j uses **trigrams** for TEXT indexes: splitting a string into consecutive sequences of three Unicode code points. For example, the string `developer` produces the trigrams:

```text
developer
dev | eve | vel | elo | lop | ope | per
```

These chunks create an effective access path for string searches occurring in the **middle** (`CONTAINS`) or at the **end** (`ENDS WITH`) of a value. A RANGE index sorts string values lexicographically, so it is typically better suited for exact comparisons and searching from the **start of a string** (`STARTS WITH`). Trigrams explain the advantage of a TEXT index, yet do not guarantee every short-substring query will be fast: the planner still evaluates selectivity and data size.

Important constraints:

- A TEXT index targets **one property** of **one node label or one relationship type**; you cannot create a composite TEXT index across multiple properties.
- Only property values of type `STRING` are indexed; missing properties, `null`, numbers, or values of other types do not become string entries in the index.
- A TEXT index **does not create a uniqueness constraint**. To forbid duplicate identifiers, define an appropriate constraint rather than only creating a TEXT index.
- An index name must be unique in the schema; use `IF NOT EXISTS` so re-creating the same index does not fail under normal circumstances.
- Indexes are built in the background; measure performance only after the state reports `ONLINE`.
- TEXT indexes have a string key size limit of approximately **32 KiB** (depending on version/provider). For extremely long text, check operational limits rather than assuming any content can be indexed.

## 3. Practice Data: Graph Database Article Catalog

Examples use the `LI004Article` label and schema names prefixed with `li004_` for easy identification and minimal interference with other data. Run these in a practice database. The statement below creates eight nodes and can be re-run to update sample values by `code`:

```cypher
UNWIND [
  {code: 'a01', title: 'Neo4j Graph Database',
   slug: 'neo4j-graph-database'},
  {code: 'a02', title: 'Cypher Query Language',
   slug: 'cypher-query-language'},
  {code: 'a03', title: 'Spring Data Neo4j',
   slug: 'spring-data-neo4j'},
  {code: 'a04', title: 'Graph Analytics with Cypher',
   slug: 'graph-analytics-cypher'},
  {code: 'a05', title: 'Database Index Design',
   slug: 'database-index-design'},
  {code: 'a06', title: 'neo4j for beginners',
   slug: 'neo4j-for-beginners'},
  {code: 'a07', title: 'Đồ thị tri thức',
   slug: 'do-thi-tri-thuc'},
  {code: 'a08', title: 'Neo4j',
   slug: 'neo4j'}
] AS row
MERGE (a:LI004Article {code: row.code})
SET a.title = row.title,
    a.slug = row.slug;
```

Inspect the data:

```cypher
MATCH (a:LI004Article)
RETURN a.code AS code, a.title AS title, a.slug AS slug
ORDER BY code;
```

Expect eight rows from `a01` to `a08`. If the practice database already holds other nodes labeled `LI004Article`, check before relying on the expected counts below.

### 3.1. Creating a TEXT Index on a Node Property

```cypher
CREATE TEXT INDEX li004_article_title_text IF NOT EXISTS
FOR (a:LI004Article)
ON (a.title);
```

This command creates an index specifically for the `title` property of nodes with the `LI004Article` label. It **does not** automatically index `slug` or other labels. `IF NOT EXISTS` is helpful when initializing schemas repeatedly; if the index name is already used for a different schema definition, inspect the schema instead of assuming the desired index was created.

Read the index status:

```cypher
SHOW TEXT INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties
WHERE name = 'li004_article_title_text'
RETURN name, type, state, populationPercent, labelsOrTypes, properties;
```

Once the index is ready, `type = 'TEXT'`, `state = 'ONLINE'`, `labelsOrTypes = ['LI004Article']`, and `properties = ['title']`. If it is still `POPULATING`, recheck the status before comparing execution plans.

## 4. Five String Search Patterns Supported by TEXT Indexes

In Cypher, `STARTS WITH`, `ENDS WITH`, and `CONTAINS` are **case-sensitive**. Searching for `Neo4j` will not automatically match `neo4j`. Two expressions that sound similar in natural language can return different result sets.

| Pattern | Cypher Predicate | Meaning | Expected Result on Sample Data |
|---|---|---|---|
| Prefix | `a.title STARTS WITH 'Neo4j'` | Title begins with `Neo4j` | `a01`, `a08` |
| Suffix | `a.title ENDS WITH 'Neo4j'` | Title ends with `Neo4j` | `a03`, `a08` |
| Substring | `a.title CONTAINS 'Graph'` | Contains `Graph` at any position | `a01`, `a04` |
| Exact match | `a.title = 'Neo4j'` | Entire title equals `Neo4j` | `a08` |
| In string set | `a.title IN ['Neo4j', 'Cypher Query Language']` | Title matches one value in the list | `a02`, `a08` |

### 4.1. `STARTS WITH`: Prefix Search

```cypher
MATCH (a:LI004Article)
WHERE a.title STARTS WITH 'Neo4j'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Returns `a01` and `a08`. `a06` does not match because of the lowercase `n`. A TEXT index **can** resolve this condition, though if a RANGE index exists on the same property, the planner usually prefers the RANGE index thanks to its string ordering.

### 4.2. `ENDS WITH`: Suffix Search

```cypher
MATCH (a:LI004Article)
WHERE a.title ENDS WITH 'Neo4j'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Returns `a03` and `a08`. This is one of the two search patterns where a TEXT index typically has a clear advantage over a RANGE index.

### 4.3. `CONTAINS`: Substring Search

```cypher
MATCH (a:LI004Article)
WHERE a.title CONTAINS 'Graph'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Returns `a01` and `a04`. Try replacing `'Graph'` with `'neo4j'`, and the result is `a06`; `'Neo4j'` and `'neo4j'` are not equivalent.

### 4.4. `=` and `IN`: Exact String Comparison

```cypher
MATCH (a:LI004Article)
WHERE a.title = 'Neo4j'
RETURN a.code AS code, a.title AS title;
```

Result: `a08`.

```cypher
MATCH (a:LI004Article)
WHERE a.title IN ['Neo4j', 'Cypher Query Language']
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Result: `a02`, `a08`. A TEXT index can support `=` and `IN` **when the planner determines the comparison expression is a string**. If the right-hand side comes from a property of unknown type at planning time, the predicate may lack sufficient type information to leverage the TEXT index.

### 4.5. Verifying Data and Results in One Query

```cypher
MATCH (a:LI004Article)
WITH collect({code: a.code, title: a.title}) AS rows
RETURN
  size(rows) = 8
  AND size([x IN rows WHERE x.title STARTS WITH 'Neo4j']) = 2
  AND size([x IN rows WHERE x.title ENDS WITH 'Neo4j']) = 2
  AND size([x IN rows WHERE x.title CONTAINS 'Graph']) = 2
  AND size([x IN rows WHERE x.title = 'Neo4j']) = 1
  AND size([x IN rows WHERE
    x.title IN ['Neo4j', 'Cypher Query Language']]) = 2
  AS passed;
```

On the complete sample dataset, `passed` must evaluate to `true`. This tests **predicate correctness**, not query speed or proof that the planner used an index.

## 5. When Does the Cypher Planner Actually Use a TEXT Index?

**Supported does not guarantee selected.** With eight nodes, scanning by label can be cheaper than index access; on large datasets, the planner generally has a stronger basis to choose the appropriate index.

Use `EXPLAIN` to view the plan **without executing the query**:

```cypher
EXPLAIN
MATCH (a:LI004Article)
WHERE a.title CONTAINS 'Graph'
RETURN a.code AS code, a.title AS title;
```

Use `PROFILE` to both execute the read query and collect actual row counts, database hits (`DB Hits`), and per-operator cost:

```cypher
PROFILE
MATCH (a:LI004Article)
WHERE a.title ENDS WITH 'Neo4j'
RETURN a.code AS code, a.title AS title;
```

In the plan, look for an index access operator and the description `TEXT INDEX ... LI004Article(title)`. Specific operator names can vary by version and predicate; if you see a label scan, do not conclude the index syntax is wrong without checking `ONLINE` state, statistics, and selectivity.

### 5.1. Comparing with a RANGE Index on the Same Property

You can create the following additional index **purely for experimentation**:

```cypher
CREATE RANGE INDEX li004_article_title_range IF NOT EXISTS
FOR (a:LI004Article)
ON (a.title);
```

When both TEXT and RANGE indexes exist on `title`:

| Predicate | Index Type the Planner Typically Prefers | Explanation |
|---|---|---|
| `CONTAINS` | TEXT | Substring lookup suited to trigrams |
| `ENDS WITH` | TEXT | Suffix lookup suited to trigrams |
| `STARTS WITH` | RANGE | Prefix lookup using lexicographical order |
| `=`, `IN` with strings | RANGE | Access by exact value |

This reflects **selection tendencies when both indexes are available**, not a guarantee that tiny queries will use an index. When *only* a TEXT index exists, it can still resolve `STARTS WITH`, `=`, and `IN` if data type conditions are satisfied.

To demonstrate forcing an index type while learning, you can use an index hint:

```cypher
EXPLAIN
MATCH (a:LI004Article)
USING TEXT INDEX a:LI004Article(title)
WHERE a.title CONTAINS 'Graph'
RETURN a.code, a.title;
```

`USING TEXT INDEX` should only be used deliberately during plan analysis; an incorrect hint or a missing/incompatible index can prevent the query from planning or make it slower. In most applications, let the planner choose automatically first.

### 5.2. Parameterizing Queries from a Java Application

With the Java Driver or Spring Data Neo4j, pass search criteria as **parameters**; never concatenate user-supplied strings into Cypher code:

```cypher
MATCH (a:LI004Article)
WHERE a.title CONTAINS $fragment
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Assuming `fragment = "Graph"`, expect `a01` and `a04`. Parameterized queries can still leverage the appropriate index. A Java Driver example using an already-configured `driver` instance:

```java
String cypher = """
    MATCH (a:LI004Article)
    WHERE a.title CONTAINS $fragment
    RETURN a.code AS code, a.title AS title
    ORDER BY code
    """;

try (var session = driver.session()) {
    var rows = session.executeRead(tx ->
        tx.run(cypher, java.util.Map.of("fragment", "Graph")).list()
    );
    rows.forEach(row ->
        System.out.println(row.get("code").asString() + ": "
            + row.get("title").asString())
    );
}
```

This Java snippet illustrates **executing the query**; the project still needs driver initialization, authentication, and connection management according to its own setup. For case-insensitive needs, normalize data and parameters consistently instead of dynamically concatenating Cypher strings.

## 6. TEXT Indexes for Relationship Properties

Indexes are not limited to nodes. For instance, in a documentation graph, a `LI004_REFERENCES` relationship stores `context` explaining why one article links to another.

Create two sample relationships:

```cypher
MATCH (a:LI004Article {code: 'a01'})
MATCH (b:LI004Article {code: 'a02'})
MERGE (a)-[r:LI004_REFERENCES]->(b)
SET r.context = 'cypher-guide';
```

```cypher
MATCH (a:LI004Article {code: 'a03'})
MATCH (b:LI004Article {code: 'a01'})
MERGE (a)-[r:LI004_REFERENCES]->(b)
SET r.context = 'neo4j-guide';
```

Create a dedicated TEXT index for the relationship property:

```cypher
CREATE TEXT INDEX li004_relation_context_text IF NOT EXISTS
FOR ()-[r:LI004_REFERENCES]-()
ON (r.context);
```

Example finding links whose context ends with `guide`:

```cypher
MATCH (source:LI004Article)-[r:LI004_REFERENCES]->(target:LI004Article)
WHERE r.context ENDS WITH 'guide'
RETURN source.code AS sourceCode,
       target.code AS targetCode,
       r.context AS context
ORDER BY sourceCode;
```

Returns two relationships: `a01 → a02` (`cypher-guide`) and `a03 → a01` (`neo4j-guide`). This index applies to **one relationship type + one property**; it does not index the `context` string of other relationship types.

## 7. Cases a TEXT Index Does Not Solve Directly

### 7.1. Case-Insensitive and Accent-Insensitive Search

`STARTS WITH`, `ENDS WITH`, and `CONTAINS` are **case-sensitive** by default. Nor do they automatically strip diacritics; `'Đồ thị'` is not equivalent to `'Do thi'`. The following syntax produces case-insensitive results:

```cypher
MATCH (a:LI004Article)
WHERE toLower(a.title) CONTAINS 'neo4j'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

Expected output: `a01`, `a03`, `a06`, and `a08`. However, **applying `toLower()` to the indexed property** can prevent the planner from using the TEXT index on `title`.

If case-insensitive search is a frequent requirement, consider **storing a pre-normalized field** (such as `titleSearch`), creating a separate TEXT index on that field, and normalizing *both stored data and query input* with the same rule. For Vietnamese text, decide at the business level whether to strip diacritics; lowercasing is not the same as removing accents or normalizing Unicode.

### 7.2. Regex or Ranked Keyword Search

Regular expressions use the `=~` operator:

```cypher
MATCH (a:LI004Article)
WHERE a.title =~ '(?i).*neo4j.*'
RETURN a.code AS code, a.title AS title
ORDER BY code;
```

`(?i)` enables case-insensitive regex matching, but **do not expect regexes to be accelerated like `CONTAINS` via a TEXT index**. When you need tokenization, language analysis, term queries, and relevance-ranked results, consider a **FULLTEXT index**; how full-text queries are invoked depends on your Neo4j version.

A TEXT index returns values **matching the predicate**; it does not compute a *relevance score* or perform semantic fuzzy matching. For semantic similarity search, you may need a vector index and a different pipeline.

### 7.3. Wrong Data Types or Expressions Obscuring the Property

The snippet below may fail to use the TEXT index if the planner does not know the type of `input.value` ahead of time:

```cypher
WITH {value: 'Graph'} AS input
MATCH (a:LI004Article)
WHERE a.title CONTAINS input.value
RETURN a.code, a.title;
```

You can clarify the type **on the query value side**, leaving the indexed property untouched:

```cypher
WITH {value: 'Graph'} AS input
MATCH (a:LI004Article)
WHERE a.title CONTAINS toString(input.value)
RETURN a.code, a.title;
```

Note: **index eligibility** still depends on data types and the specific plan; verify with `EXPLAIN`. Avoid unnecessarily wrapping the property side as `toString(a.title)` or transforming `a.title` inside `WHERE`, because transforming the property expression can prevent index usage.

### 7.4. Indexes Do Not Replace Data Design

- A TEXT index does not accelerate path traversals (`shortest path`, multi-hop expansions) if the query has no matching string property predicate.
- Do not create a TEXT index on every string field out of habit: each index consumes disk space and write-maintenance overhead. Select properties that actually have queries needing `CONTAINS`/`ENDS WITH`.
- Do not confuse indexes with constraints: a TEXT index does not guarantee `code` or `email` uniqueness.
- With multiple filter predicates, intermediate row counts and selectivity can matter more than whether a specific index exists.

## 8. Checking Status, Cleanup, and Exercises

To list the practice lesson's indexes:

```cypher
SHOW INDEXES
YIELD name, type, state, entityType, labelsOrTypes, properties
WHERE name STARTS WITH 'li004_'
RETURN name, type, state, entityType, labelsOrTypes, properties
ORDER BY name;
```

When finished, **only in your practice database**, you can clean up the three created indexes and sample nodes (`DETACH DELETE` also removes relationships attached to those nodes):

```cypher
DROP INDEX li004_article_title_text IF EXISTS;
```

```cypher
DROP INDEX li004_article_title_range IF EXISTS;
```

```cypher
DROP INDEX li004_relation_context_text IF EXISTS;
```

```cypher
MATCH (a:LI004Article)
DETACH DELETE a;
```

### Practice Exercises

1. Create a TEXT index on `LI004Article(slug)`. Write a query to find `slug` values ending with `'neo4j'`; identify the article codes and inspect `EXPLAIN`.
2. Compare `a.title CONTAINS 'Neo4j'` with `a.title CONTAINS 'neo4j'`. Why do the two queries return different result sets? To match both, how would you design `titleSearch`?
3. Keep both TEXT and RANGE indexes on `title`; run `EXPLAIN` for `STARTS WITH`, `ENDS WITH`, and `CONTAINS`. Record the operators and actual index types used, and explain why the planner might choose a label scan.
4. Test an article whose `slug` property is `null`/missing. Why can't a TEXT index be used to directly look up a string value that was never stored?
5. Expand the two sample relationships and add a query `r.context CONTAINS 'neo4j'`. Explain why a TEXT index on node `title` does not speed up a predicate on relationship `context`.

**Post-lesson self-check:** You should be able to name the five predicate groups supported by TEXT indexes, explain why `CONTAINS`/`ENDS WITH` are standout use cases, distinguish TEXT from RANGE/LOOKUP/FULLTEXT, read the `ONLINE` status, and analyze execution plans without assuming an index is always chosen.

## 9. Reference Documentation

- [Neo4j Cypher Manual — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/): syntax, supported predicates, and trigrams.
- [Neo4j Cypher Manual — The impact of indexes on query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/): choosing TEXT/RANGE indexes and reading plans.
- [Neo4j Cypher Manual — Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/): inspecting status and statistics.
- [Neo4j Cypher Manual — Index hints](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/index-hints/): `USING TEXT INDEX` and caveats on forcing plans.
