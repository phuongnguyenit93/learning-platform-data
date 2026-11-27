# Managing Index Updates and Consistency Across Index Types in Neo4j

## 1. Problem Statement: Why Did the Graph Change While Search Results Have Not?

Neo4j stores connected data as a **property graph**: nodes, relationships, and properties. When an application adds an article, edits a title, removes a tag, or updates a vector embedding, the underlying data (*graph store*) changes; at the same time, the associated **indexes** must reflect those changes so queries still find the right entities.

Suppose a knowledge management system has:

- `Article` nodes with `id`, `title`, `body`, `category`, `location`, and `embedding`.
- `(:Article)-[:CITES]->(:Article)` relationships representing citations.
- Lookup by ID and category; substring matching, full-text content search, spatial search, and semantic vector search.

The operational question is not only **"Does the index exist?"**, but also:

1. When nodes or relationships change, **which indexes are updated**, and by what mechanism?
2. Immediately after a transaction commits, **which query types can read the changes**?
3. When creating a new index, how do you know it has **finished building**?
4. When search results are wrong or missing, is the cause **index synchronization**, **query predicates**, the **analyzer**, or **vector search approximation**?

Three concepts must be separated upfront:

| Concept | Question to Answer | Example |
| --- | --- | --- |
| **Transactional data consistency** | Did changes in a transaction commit or roll back? | `SET a.title = 'New'` commits successfully |
| **Index copy freshness** | When does the index reflect committed changes? | Eventual full-text configuration may lag briefly |
| **Search semantics / accuracy** | By what rules does the index return results? | Vector k-NN returns **approximate** nearest neighbors; full-text tokenizes via an analyzer |

Do not treat **"an item is missing from vector top-k"** as proof of index lag: approximate k-NN and top-k coverage are distinct from transaction commits and synchronization.

## 2. Comparing Consistency Across Index Types

Neo4j distinguishes **performance indexes** chosen by the Cypher planner from **search indexes** invoked explicitly to obtain ranked results.

| Index Type | Updated When Data Changes | Consistency Notes | Queries Using It |
| --- | --- | --- | --- |
| **Token lookup** (`LOOKUP`) | Automatically updated on node label / relationship type changes within the transaction | Maintained with the transaction; not a property index | `MATCH (a:Article)`, `MATCH ()-[:CITES]->()` |
| **Range** (`RANGE`) | Automatically updated on relevant property inserts, updates, deletes, and label/type changes | Performance index maintained at commit; uniqueness constraints use range indexes for enforcement | `a.id = $id`, `a.createdAt >= $from` |
| **Text** (`TEXT`) | Automatically updated when valid `STRING` values change | Performance index synchronized at commit, distinct from full-text indexes | `a.title CONTAINS 'graph'` |
| **Point** (`POINT`) | Automatically updated when `POINT` location properties change | Maintained at commit, but requires matching CRS and data types | `point.distance(...)`, `point.withinBBox(...)` |
| **Full-text** (`FULLTEXT`) default | Automatically updated when `STRING`/`LIST<STRING>` values are added, edited, or deleted | **Updated during commit by default** (`eventually_consistent = false`) | Token/analyzer search with `score` |
| **Full-text** eventual config | Committed changes are queued and applied on a background thread | **Searches may see stale results briefly after commit** | Same full-text queries; has a refresh-wait procedure |
| **Vector** (`VECTOR`) | Automatically managed when valid embeddings are added, edited, or deleted | Changes **within the current write transaction** are not visible to vector index queries in that transaction; k-NN search is **approximate** | Vector `SEARCH` or k-NN procedure depending on version |

**Important:** `fulltext.eventually_consistent` is a setting **specific to full-text indexes**, not a global switch turning all Neo4j indexes asynchronous. Vector indexes have their own query boundaries; never assume vectors share the full-text queue or the same `await` procedure.

Documentation and APIs evolve across versions. The examples below favor `CREATE ... INDEX` syntax supported across Neo4j 5.x releases and explicitly note where Cypher 25 / Neo4j 2026 is required.

## 3. How Are Indexes Updated?

### 3.1. A Transactional Change Affecting Indexes

Suppose `Article` has a range index on `category`, a text index on `title`, and a full-text index on `title`/`body`:

```cypher
MATCH (a:Article {id: 'A001'})
SET a.title = 'Optimizing Cypher Queries',
    a.category = 'DATABASE'
REMOVE a.legacyTag;
```

When the transaction commits successfully:

- The range index on `category` drops the old value (if any) and reflects `DATABASE`.
- The text index on `title` reflects the new title string.
- The full-text index updates tokens related to the title **during commit** in default mode, or **after commit via a background thread** if eventual mode is enabled.
- Any index on `legacyTag` (if present) no longer holds an entry for the removed value.
- Any modifications in a failed and rolled-back transaction **are not treated as committed data**, so they never appear as confirmed changes in indexes.

```text
                    DATA WRITE
                         |
                    Transaction
                         |
              +----------+----------+
              |                     |
           ROLLBACK               COMMIT
              |                     |
      Changes discarded      Graph store commits
                                    |
                 +------------------+---------------------+
                 |                                        |
     Indexes synced on commit                Eventual full-text (if enabled)
     LOOKUP / RANGE / TEXT / POINT           Enqueues update work
     and default full-text                              |
                                                 Background thread
                                                        |
                                                 Index refreshed
```

This diagram illustrates **update timing**, not the complete internal engine implementation.

### 3.2. Which Write Operations Modify Index Contents?

| Write Operation | Common Effect |
| --- | --- |
| `CREATE` node with matching label and properties | Adds entries to lookup index and corresponding property indexes |
| `SET a.title = '...'` | Replaces old entry with new entry in the `title` index |
| `REMOVE a.title` or `SET a.title = null` | Removes that property entry from the index; Neo4j does not store `null` property values |
| `SET a:Published` / `REMOVE a:Published` | Updates label lookup; property indexes scoped to `Published` are updated accordingly |
| `CREATE` / `DELETE` relationship | Updates relationship-type lookup index and related property indexes |
| `DELETE a` | Removes node from relevant indexes once the transaction succeeds |
| Edit `a.embedding` | Vector index processes the new vector if it meets schema/config requirements |

A relationship type cannot be modified directly like a property: to change a type, applications typically create a new relationship, copy needed properties, and delete the old relationship inside an appropriate transaction.

Indexes only include entities whose **labels/types and property values** match the schema and supported data types of that index. For instance, a text index does not index an `INTEGER` as a string; a 3-dimensional vector index does not index a 4-dimensional embedding under that configuration. Check stored values in the graph store before suspecting an index bug.

### 3.3. Do Not Confuse Indexes with Data Constraints

```cypher
CREATE CONSTRAINT article_id_unique IF NOT EXISTS
FOR (a:Article) REQUIRE a.id IS UNIQUE;
```

A uniqueness constraint creates a **constraint-owned range index** to check for duplicate keys. A plain `CREATE RANGE INDEX` accelerates queries but **does not prevent** creating two nodes with the same `id`. If a transaction violates a uniqueness constraint, the transaction fails; there is no state where "the graph writes a duplicate while the index catches up".

A constraint-owned index cannot be dropped directly with `DROP INDEX`; dropping the constraint drops its backing index as well. When building search and ingestion systems, clearly separate **access optimization** from **key integrity enforcement**.

## 4. Hands-On: Creating an Index Suite for a Knowledge Graph

### 4.1. Creating the Schema

Run each statement independently on a test database:

```cypher
CREATE CONSTRAINT article_id_unique IF NOT EXISTS
FOR (a:Article) REQUIRE a.id IS UNIQUE;
```

```cypher
CREATE RANGE INDEX idx_article_category IF NOT EXISTS
FOR (a:Article) ON (a.category);
```

```cypher
CREATE TEXT INDEX idx_article_title_text IF NOT EXISTS
FOR (a:Article) ON (a.title);
```

```cypher
CREATE POINT INDEX idx_article_location IF NOT EXISTS
FOR (a:Article) ON (a.location);
```

```cypher
CREATE FULLTEXT INDEX idx_article_fulltext IF NOT EXISTS
FOR (a:Article) ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'standard-no-stop-words',
    `fulltext.eventually_consistent`: true
  }
};
```

```cypher
CREATE VECTOR INDEX idx_article_embedding IF NOT EXISTS
FOR (a:Article) ON (a.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 3,
    `vector.similarity_function`: 'cosine'
  }
};
```

In the example above, embeddings have **3 dimensions solely for illustration**; real applications must use the embedding model's exact dimensionality, such as 768 or 1536. Cosine vector indexes require valid non-zero vectors. `IF NOT EXISTS` does not compare old vs. new options to update an existing index automatically.

Token lookup indexes for node labels and relationship types are normally created automatically by Neo4j when initializing a database, so no extra creation statement is needed here.

### 4.2. Creating Test Data

```cypher
MERGE (a:Article {id: 'A001'})
SET a.title = 'Graph and Cypher',
    a.body = 'Neo4j queries relationships with Cypher.',
    a.category = 'DATABASE',
    a.location = point({longitude: 106.7000, latitude: 10.7800}),
    a.embedding = [1.0, 0.0, 0.0];
```

```cypher
MERGE (a:Article {id: 'A002'})
SET a.title = 'Java Driver for Neo4j',
    a.body = 'Java connects to the graph and executes queries.',
    a.category = 'JAVA',
    a.location = point({longitude: 106.7200, latitude: 10.7950}),
    a.embedding = [0.8, 0.6, 0.0];
```

```cypher
MERGE (a:Article {id: 'A003'})
SET a.title = 'Paths in a Property Graph',
    a.body = 'Relationships connect nodes in a graph.',
    a.category = 'DATABASE',
    a.location = point({longitude: 106.6900, latitude: 10.7750}),
    a.embedding = [0.0, 1.0, 0.0];
```

To create a relationship for search combined with traversal:

```cypher
MATCH (a:Article {id: 'A001'})
MATCH (b:Article {id: 'A002'})
MERGE (a)-[:CITES]->(b);
```

### 4.3. Waiting for Indexes to Finish Building

Building an index and having it reflect **subsequent updates** are two separate concerns. Immediately after `CREATE ... INDEX`, an index may be in `POPULATING` state while Neo4j scans existing data to construct the access structure. Only when `ONLINE` is the index ready for queries.

```cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, labelsOrTypes, properties
RETURN name, type, state, populationPercent, labelsOrTypes, properties
ORDER BY type, name;
```

You can wait for a specific index or all indexes:

```cypher
CALL db.awaitIndex('idx_article_fulltext', 300);
```

```cypher
CALL db.awaitIndexes(300);
```

The `300` value is a maximum timeout in seconds, not a requirement that Neo4j take 300 seconds. If an index enters `FAILED` state, inspect the root cause; do not call `await` repeatedly to mask a failure.

**`db.awaitIndexes()` only waits for initial creation/population to become `ONLINE`. It does not mean pending updates in an eventual full-text queue have been applied.** Waiting for post-commit refreshes is handled separately in the next section.

## 5. Testing Updates and Observing Each Index Type

### 5.1. Range, Text, and Token Lookup

Update the title, category, and label:

```cypher
MATCH (a:Article {id: 'A001'})
SET a.title = 'Advanced Neo4j Guide',
    a.category = 'TUTORIAL',
    a:Reviewed;
```

Verify the result in a **read transaction after the write command commits**:

```cypher
MATCH (a:Article)
WHERE a.category = 'TUTORIAL'
  AND a.title CONTAINS 'Neo4j'
  AND a:Reviewed
RETURN a.id, a.title, a.category, labels(a);
```

Range, text, and lookup indexes are automatically maintained with the commit so the planner can serve confirmed data. This query **does not guarantee the planner uses all three indexes simultaneously**: on tiny datasets, the planner may choose a scan and filter. Use `EXPLAIN` or `PROFILE` to inspect the actual plan.

### 5.2. Point

Update the node's location:

```cypher
MATCH (a:Article {id: 'A001'})
SET a.location = point({longitude: 106.7100, latitude: 10.7850});
```

Search within a radius:

```cypher
MATCH (a:Article)
WHERE point.distance(
  a.location,
  point({longitude: 106.7100, latitude: 10.7850})
) <= 1000
RETURN a.id, a.location;
```

No `REINDEX` command is needed after `SET`. If expected results do not appear, verify the **CRS**, `longitude`/`latitude` coordinates, radius units (meters for WGS 84), and predicate before blaming the index.

## 6. Full-Text: Synchronous Updates vs. Eventual Consistency

### 6.1. Two Operational Modes

A full-text index tokenizes strings for word-based search and relevance scoring. It **differs from a text index** designed for `CONTAINS`, `ENDS WITH`, and `STARTS WITH` in standard Cypher predicates.

With the default `fulltext.eventually_consistent: false`, full-text updates are processed on the transaction's commit path. With `true`, Neo4j queues update work to be applied in the background, reducing commit overhead under heavy write loads.

| Criterion | Default Full-Text | Eventual Full-Text |
| --- | --- | --- |
| `fulltext.eventually_consistent` | `false` | `true` |
| When index changes are processed | During commit | After commit, via queue and background thread |
| Behavior immediately after commit | Index reflects updates synchronously | Queries may still see old tokens or miss new tokens |
| Trade-off | Commit bears index update cost | Higher write throughput on some workloads; must tolerate lag |
| When suitable | Search must immediately reflect committed data | Content search that can tolerate brief delay |

Example updating content:

```cypher
MATCH (a:Article {id: 'A001'})
SET a.title = 'Optimizing Neo4j Indexes',
    a.body = 'Guide to managing indexes and search queries.';
```

In Cypher 5 or Neo4j 5.x environments, query full-text via the procedure:

```cypher
CALL db.index.fulltext.queryNodes('idx_article_fulltext', 'Neo4j')
YIELD node, score
RETURN node.id AS articleId, node.title AS title, score
ORDER BY score DESC;
```

Because the example enabled eventual mode, running this query **immediately after commit** may not yet see all new tokens. Step to ensure queued updates are flushed:

```cypher
CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh();
```

**Correct operation order:** (1) complete and commit the `SET` statement; (2) call `awaitEventuallyConsistentIndexRefresh()` in the next command/transaction; (3) then run the full-text query you want to verify. This procedure waits for recently committed **eventual full-text** updates; it is **not** a full index rebuild command and does not apply to vector, range, text, or point indexes.

If the application requires immediate *read-your-write* semantics for critical text searches, synchronous mode is usually easier to satisfy. When choosing eventual mode, call the refresh wait only in special flows (such as confirming newly published content) rather than forcing every search request to block.

### 6.2. Newer Search Syntax by Version

Starting in **Neo4j 2026.09 with Cypher 25**, full-text indexes can be queried using the `SEARCH` clause, which is preferred in current documentation:

```cypher
CYPHER 25
MATCH (a:Article)
SEARCH a IN (
  FULLTEXT INDEX idx_article_fulltext
  FOR 'Neo4j'
  LIMIT 10
) SCORE AS score
RETURN a.id AS articleId, a.title AS title, score;
```

The `db.index.fulltext.queryNodes()` procedure remains useful for backward compatibility and Cypher 5, though it **has been marked deprecated in Cypher 25 since Neo4j 2026.10**. For new development, verify your system's Neo4j and Cypher versions before selecting an API.

### 6.3. Analyzer Behavior Is Not a Consistency Bug

Full-text uses an analyzer for tokenization, case normalization, and potentially stop words. If searching `graph` misses a string containing `graph`, the cause may be tokenization or analyzer rules, **not an un-updated index**.

```cypher
CALL db.index.fulltext.listAvailableAnalyzers()
YIELD analyzer, description
RETURN analyzer, description
ORDER BY analyzer;
```

`fulltext.analyzer` and `fulltext.eventually_consistent` values are fixed when creating the index. Changing DBMS defaults **does not alter an existing full-text index**. To change an analyzer or eventual mode, plan to recreate the index with the new settings and wait for it to reach `ONLINE`.

## 7. Vector: Embedding Updates and Consistency Limits

Vector indexes use numeric embeddings to find nodes or relationships whose representations are close in vector space. They implement **approximate nearest neighbor** (ANN) search, so results are not guaranteed to be the exact k nearest neighbors.

Three aspects to check independently:

1. **Source data:** was `a.embedding` written and committed with the right dimensionality, component order, and embedding model?
2. **Index state:** is `idx_article_embedding` `ONLINE`, and do `vector.dimensions`/`vector.similarity_function` match?
3. **ANN query:** is `k` large enough, are scores sensible, and do *recall* expectations fit approximate search behavior?

Example updating an embedding:

```cypher
MATCH (a:Article {id: 'A001'})
SET a.embedding = [0.6, 0.8, 0.0];
```

Verify the committed source data:

```cypher
MATCH (a:Article {id: 'A001'})
RETURN a.id, a.embedding;
```

Query the vector index with Neo4j 5.x compatible procedure syntax:

```cypher
CALL db.index.vector.queryNodes(
  'idx_article_embedding', 3, [0.6, 0.8, 0.0]
)
YIELD node, score
RETURN node.id AS articleId, score
ORDER BY score DESC;
```

From **Neo4j 2026.01 (Cypher 25)** onward, `SEARCH` is the preferred syntax for vector queries:

```cypher
CYPHER 25
MATCH (a:Article)
SEARCH a IN (
  VECTOR INDEX idx_article_embedding
  FOR [0.6, 0.8, 0.0]
  LIMIT 3
) SCORE AS score
RETURN a.id AS articleId, score;
```

`db.index.vector.queryNodes()` is marked deprecated starting in Neo4j 2026.04; it may still appear on Cypher 5 or older systems. More importantly, **writes performed within the current transaction are not visible to vector index queries inside that same transaction**. Commit first and then search in a subsequent read transaction; never design a flow that runs "`SET embedding` followed by vector search in the same transaction" expecting the new node to appear.

**Do not call** `db.index.fulltext.awaitEventuallyConsistentIndexRefresh()` to wait for vector indexes. That procedure applies only to eventual full-text indexes. Furthermore, missing a candidate in ANN top-k can result from approximation, data volume, or search parameters even when the embedding in the graph store is correct.

**Changing embedding models:** when moving from a 3-dimensional model to a 768-dimensional model, for example, do not overwrite the old property while keeping the 3-dimensional index. A safer migration path is to add an `embeddingV2` property, create a new vector index with matching dimensions, backfill the data, wait for `ONLINE`, verify query quality, and switch the application to the new index.

## 8. Monitoring Index Status and Diagnostics

### 8.1. Checking Schema and State

```cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties,
      state, populationPercent, owningConstraint,
      options, failureMessage
RETURN name, type, entityType, labelsOrTypes, properties,
       state, populationPercent, owningConstraint,
       options, failureMessage
ORDER BY type, name;
```

Key fields:

- **`state`**: `POPULATING` means building; `ONLINE` means ready; `FAILED` requires error investigation.
- **`populationPercent`**: initial index build progress, **not the percentage of queued eventual full-text updates refreshed**.
- **`labelsOrTypes`, `properties`**: confirm the index covers the intended label/relationship type and properties.
- **`options`**: inspect analyzer, eventual consistency, dimensions, or similarity function for configurable index types.
- **`owningConstraint`**: identifies a range index owned by a uniqueness/key constraint, which cannot be dropped independently.
- **`failureMessage`**: diagnostic cause if the index failed during creation or startup.

Quickly check indexes that are not yet active:

```cypher
SHOW INDEXES
YIELD name, type, state, populationPercent, failureMessage
WHERE state <> 'ONLINE'
RETURN name, type, state, populationPercent, failureMessage;
```

Check whether an index is chosen by the planner in a regular query:

```cypher
EXPLAIN
MATCH (a:Article)
WHERE a.category = 'DATABASE'
RETURN a.id, a.title;
```

Or execute and collect runtime metrics:

```cypher
PROFILE
MATCH (a:Article)
WHERE a.title CONTAINS 'Neo4j'
RETURN a.id;
```

Inspect index access operators, `Rows`, `DB Hits`, and actual timing. On a test graph with only a few nodes, the planner may scan directly because scanning is cheaper than using an index. Full-text and vector queries are invoked explicitly via `SEARCH` or their procedures; do not expect the planner to rewrite `CONTAINS` into full-text search automatically.

### 8.2. Understanding Resampling Properly

Neo4j provides the procedure:

```cypher
CALL db.resampleIndex('idx_article_category');
```

Resampling updates **statistics for the query planner** and can help the planner pick better plans when data distributions change. It is **not** a mechanism to flush an eventual full-text queue, regenerate embeddings, or fix an index in `FAILED` state.

### 8.3. If an Index Reports `FAILED`

1. Read `failureMessage` and Neo4j logs to determine whether it is a config error, invalid property value, key size limit, resource shortage, or storage issue.
2. Fix the root cause; if a regular index must be rebuilt, plan a migration to drop it by name, recreate it, and wait for `ONLINE`.
3. If it is a **constraint-owned index**, handle it via constraint management: never run `DROP INDEX` on a backing index.
4. If on-disk data/index corruption is suspected, use your Neo4j version's consistency checker and proper backup/maintenance procedures; never delete data just to force an index `ONLINE`.

Never run `DROP INDEX` impulsively in production because of one slow query. Dropping an index can severely slow dependent queries, and recreating it must repopulate from existing data.

## 9. Changing Configuration and Deploying Indexes Safely

Index management is part of schema management. A sound migration workflow:

1. **Capture baseline:** record index type, name, schema, configuration, `ONLINE` status, and representative query plans.
2. **Define the goal:** change analyzer, update vector configuration, add indexed properties, or retire unused indexes.
3. **Test on production-like data:** measure write cost, population duration, memory footprint, search latency, and result quality.
4. **Execute controlled migration:** create the new index appropriately or plan the replacement of the old index, accounting for any window without an equivalent index.
5. **Wait for `ONLINE` before shifting query traffic:** verify with `SHOW INDEXES`, `EXPLAIN`/`PROFILE`, or search quality checks.
6. **Monitor post-deployment:** watch error rates, write load, eventual full-text lag, hit rates, and storage growth.

You cannot create two indexes **of the same type on the exact same schema** simply by giving them different names. When changing full-text configuration on the same schema, plan an index replacement; when upgrading embeddings, you can use **a new property and new schema** to run side-by-side during cutover.

**Watch out for `IF NOT EXISTS`:**

```cypher
CREATE FULLTEXT INDEX idx_article_fulltext IF NOT EXISTS
FOR (a:Article) ON EACH [a.title, a.body]
OPTIONS {
  indexConfig: {
    `fulltext.eventually_consistent`: false
  }
};
```

If an index with that name/schema already exists with `eventually_consistent: true`, this statement **does not modify the existing index configuration**. Check `SHOW INDEXES ... options` and perform an explicit migration if your goal is to change the mode.

## 10. Integrating Java Driver, Spring Data Neo4j, and Clusters

### 10.1. Java Driver: Commit First, Then Await Eventual Full-Text

Java Driver example (assuming an existing `Driver driver`) using a **shared session** to write, wait for refresh, and search in sequence:

```java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    // Write transaction: must finish committing before awaiting refresh.
    session.executeWriteWithoutResult(tx ->
        tx.run(
            """
            MATCH (a:Article {id: $id})
            SET a.title = $title
            """,
            Map.of(
                "id", "A001",
                "title", "Updated Neo4j full-text"
            )
        ).consume()
    );

    // Run as a separate statement after the write has committed.
    session.run(
        "CALL db.index.fulltext.awaitEventuallyConsistentIndexRefresh()"
    ).consume();

    List<String> ids = session.executeRead(tx ->
        tx.run(
            """
            CALL db.index.fulltext.queryNodes(
              'idx_article_fulltext', $term
            )
            YIELD node, score
            RETURN node.id AS id
            """,
            Map.of("term", "Neo4j")
        ).list(record -> record.get("id").asString())
    );

    System.out.println(ids);
}
```

The full-text procedure in this example targets Cypher 5 compatibility; on Neo4j 2026.09+ / Cypher 25, prefer migrating the read step to `SEARCH` per your deployed version's syntax.

Calls within the same `Session` are chained by the driver via bookmarks, maintaining **causal consistency** across transactions in a cluster. Bookmarks ensure ordering and visibility of **committed graph transactions**; they do not automatically substitute for awaiting the **eventual full-text queue** on the node serving the search. In multi-server clusters, test end-to-end write/read flows and per-member replication/index lag explicitly.

### 10.2. Spring Data Neo4j

With Spring Data Neo4j, keep in mind:

- `save(...)` or `@Query` updates on nodes or relationships must complete their transaction (`@Transactional`) before an eventual search check verifies the new data.
- Call `awaitEventuallyConsistentIndexRefresh()` **after the commit boundary**, never right before `@Transactional` finishes assuming the change is already queued.
- When running raw Cypher for full-text/vector search, verify `score` and payload mapping with `Neo4jClient`, projections, or appropriate DTOs.
- Do not confuse entity/index annotations in code with the DBMS having created the proper schema: manage `CREATE ... INDEX` via migrations and verify with `SHOW INDEXES`.

Updating a Java property for `body` does not automatically regenerate `embedding` from text. When `body` changes, the application must **explicitly compute a new embedding with the matching model** and write it so the vector index updates.

## 11. Common Misdiagnoses

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| Newly created index is unusable | `POPULATING` or `FAILED` | `SHOW INDEXES`, `db.awaitIndex(...)`, inspect `failureMessage` |
| Eventual full-text write not immediately searchable | `eventually_consistent: true`, awaiting refresh | Check `options`, commit, call refresh-wait procedure |
| Full-text misses an arbitrary substring | Tokenization/analyzer differs from expectations | Check analyzer; compare with text index and `CONTAINS` |
| `CONTAINS` query does not use full-text index | Full-text is invoked explicitly | Use `SEARCH`/full-text procedures for lexical search |
| Vector search in the same write transaction misses new node | Vector index does not see same-transaction changes | Commit first, then open a new read transaction |
| Vector top-k misses the expected "k nearest results" | ANN is approximate; `k`/distribution/config matter | Verify stored embedding and evaluate recall on a baseline set |
| Coordinates not picked up by point index | Value is not `POINT` or wrong CRS | `RETURN a.location`, check schema, CRS, and predicate |
| `MERGE` creates duplicates under concurrency | Index exists without a uniqueness constraint | Verify uniqueness constraint on business key |
| Changing `OPTIONS` in `CREATE ... IF NOT EXISTS` has no effect | Index already existed | `SHOW INDEXES ... options`, run an actual migration |
| `RESAMPLE` still does not show new search results | Resampling only refreshes planner statistics | Check stored values, index state, eventual refresh, and query semantics |
| Query is slow despite `ONLINE` index | Planner chose a scan, low selectivity, or heavy traversal | `EXPLAIN`/`PROFILE`, `Rows`, `DB Hits`, query predicates |

## 12. Practice Exercises

1. Create two full-text indexes **on different schemas**: one default synchronous index (e.g., on `Article.summary`) and one eventual index (e.g., on `Article.title`, `Article.body`). After updating and committing data, observe the timing difference in when searches reflect changes.
2. Use `SHOW INDEXES` to locate a constraint-owned index. Explain why `DROP INDEX` cannot be used to remove that backing index.
3. Update `A001.location`, test a radius query, and run `EXPLAIN` to see whether the planner selects the point index.
4. Edit `A002.body` without **updating `A002.embedding`**. Explain why full-text and vector search results can diverge semantically even when both indexes are properly updated.
5. Write a rollout checklist for migrating from 3-dimensional to 768-dimensional embeddings without corrupting live traffic. Describe creating the new property/index, backfilling vectors, waiting for `ONLINE`, and switching the application.
6. Distinguish the purposes of `db.awaitIndexes()`, `db.index.fulltext.awaitEventuallyConsistentIndexRefresh()`, and `db.resampleIndex(...)`.

## 13. Remember

- Neo4j **maintains indexes automatically** as the graph changes; applications do not manually patch entries in range, text, point, token lookup, full-text, or vector indexes.
- **Transaction consistency**, **index refresh lag**, and **search accuracy** are three distinct questions.
- **Range, text, point, and token lookup** belong to performance indexes updated with the transaction. **Full-text is synchronous by default**, and can be **eventual** when `fulltext.eventually_consistent` is enabled.
- **Vector indexes** have same-transaction visibility limits and return **approximate k-NN** results; never apply full-text wait procedures to vectors.
- Always distinguish an **`ONLINE` index** from a **refreshed eventual full-text index**, and **resampling statistics** from **rebuilding an index**.
- Use **uniqueness constraints** to prevent duplicate data; regular indexes only accelerate lookups. In operations, monitor `SHOW INDEXES`, `EXPLAIN`/`PROFILE`, index configuration, logs, and migration procedures.

### Official References

- [Neo4j Cypher Manual — Indexes](https://neo4j.com/docs/cypher-manual/current/indexes/)
- [Neo4j Cypher Manual — Performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/)
- [Neo4j Cypher Manual — Full-text indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/full-text-indexes/)
- [Neo4j Cypher Manual — Vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-indexes/vector-indexes/)
- [Neo4j Cypher Manual — Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Operations Manual — Index configuration](https://neo4j.com/docs/operations-manual/current/performance/index-configuration/)
- [Neo4j Operations Manual — Built-in procedures](https://neo4j.com/docs/operations-manual/current/procedures/built-in-procedures/)
- [Neo4j Java Driver Manual — Bookmarks and causal consistency](https://neo4j.com/docs/java-manual/current/bookmarks/)
