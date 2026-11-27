# Changing Analyzers, Reindexing, and Search Quality Testing

In Elasticsearch, an analyzer determines how text is transformed into tokens for indexing and querying. A small change—such as removing stop words, adding stemming, changing the tokenizer, or adding synonyms—can alter the set of matched documents and result ordering. Therefore, changing an analyzer should be treated as a change to the index's search contract.

When changing how text is analyzed at index time, already-indexed data is not automatically re-analyzed. To apply a new analyzer to existing data, you need to create an index with the new settings/mapping and reindex documents. Afterward, run search quality tests before switching the application to the new index.

General workflow:

```text
Analyze the search issue
          |
          v
Design the new analyzer
          |
          v
Inspect tokens with _analyze
          |
          v
Create new index + new mapping
          |
          v
Reindex data
          |
          v
Run functional and relevance tests
          |
          v
Switch alias to the new index
          |
          v
Monitor live results and retain rollback plan
```

## 1. How does an analyzer affect search?

An analyzer is a chain of text processing steps. For `text` fields, Elasticsearch typically uses an analyzer at index time and can use a different analyzer when parsing query text.

A custom analyzer usually consists of three components, in order:

1. **Character filters:** transform input text before tokenization, such as stripping HTML or replacing characters.
2. **Tokenizer:** splits text into tokens according to rules, such as splitting on word boundaries.
3. **Token filters:** transform tokens, such as lowercasing, removing stop words, stemming, asciifolding, or synonyms.

Example with the sentence `The QUICK brown foxes!`:

```text
Input
  "The QUICK brown foxes!"
       |
       v
Tokenizer
  [The] [QUICK] [brown] [foxes]
       |
       v
Lowercase filter
  [the] [quick] [brown] [foxes]
       |
       v
Stop filter
  [quick] [brown] [foxes]
       |
       v
English stemmer
  [quick] [brown] [fox]
```

The final output consists of tokens stored in the inverted index. When a user searches for `fox`, a document containing `foxes` can be found if the index-time and search-time analyzers produce compatible tokens.

### Index analyzer and search analyzer

- `analyzer` is the analyzer used when analyzing field values at index time.
- `search_analyzer` is the analyzer used when analyzing query content for that field.

The two analyzers may be identical or different. For example, a field can be indexed with the standard tokenizer and lowercasing, while the search analyzer adds synonyms so users can match via synonymous terms.

```json
PUT /articles-v1
{
  "settings": {
    "analysis": {
      "analyzer": {
        "article_index": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        },
        "article_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "article_index",
        "search_analyzer": "article_search"
      }
    }
  }
}
```

This example declares two separate analyzers so they can be tuned independently later. When both share the exact same processing chain, a single analyzer can be reused.

## 2. When do you need to change an analyzer?

Several signs indicate the current analyzer is unsuitable:

- Users search for exact content yet miss documents due to casing or diacritic differences.
- Inflected word forms such as singular/plural fail to match as expected.
- Special characters or punctuation break tokenization for the target language and data.
- Product names, abbreviations, or synonymous terms need to match together.
- Autocomplete search needs prefix matching rather than whole-token matching only.
- Results return too many irrelevant documents because the analyzer produces overly broad tokens or keeps unnecessary stop words.

Not every search problem is solved by changing an analyzer. If a field is mapped as `keyword` while the application runs full-text queries, review the field type and query. If the query targets the wrong field name, editing the analyzer will not help. If data has not been refreshed yet, search may not see newly written documents. Identify the root cause before altering analysis configurations.

## 3. Designing a new analyzer

Suppose an English article search system wants to:

- Normalize letter casing.
- Fold accents to support unaccented queries.
- Remove certain stop words.
- Normalize word variants via stemming.

You can declare a custom analyzer:

```json
PUT /articles-analyzer-v2
{
  "settings": {
    "analysis": {
      "filter": {
        "english_stop_filter": {
          "type": "stop",
          "stopwords": "_english_"
        },
        "english_stemmer_filter": {
          "type": "stemmer",
          "language": "english"
        }
      },
      "analyzer": {
        "article_text": {
          "type": "custom",
          "char_filter": ["html_strip"],
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "asciifolding",
            "english_stop_filter",
            "english_stemmer_filter"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "article_text"
      },
      "body": {
        "type": "text",
        "analyzer": "article_text"
      },
      "category": {
        "type": "keyword"
      },
      "published_at": {
        "type": "date"
      }
    }
  }
}
```

The `article_text` analyzer executes these steps:

1. `html_strip` removes HTML markup from content.
2. `standard` splits content into tokens.
3. `lowercase` converts tokens to lowercase.
4. `asciifolding` normalizes certain accented characters to ASCII equivalents.
5. `english_stop_filter` removes English stop words.
6. `english_stemmer_filter` reduces word variants to root forms.

Filter order matters. For example, lowercasing before the stop filter ensures stop words match regardless of original capitalization. Stemming and synonyms can also interact; test with real sentences before finalizing ordering.

### Synonyms and synonym graphs

If users search for `tv` while documents use `television`, a synonym filter can be used. For search analyzers, `synonym_graph` is usually preferable when handling synonyms in multi-word queries or phrase queries.

Example search-time analyzer:

```json
PUT /articles-synonyms-v1
{
  "settings": {
    "analysis": {
      "filter": {
        "article_synonyms": {
          "type": "synonym_graph",
          "synonyms": [
            "tv, television",
            "car, automobile"
          ]
        }
      },
      "analyzer": {
        "article_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "article_synonyms"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "body": {
        "type": "text",
        "analyzer": "standard",
        "search_analyzer": "article_search"
      }
    }
  }
}
```

This example illustrates synonyms applied during query analysis. If you only change the search analyzer and indexed tokens remain compatible, full document reindexing is often unnecessary. However, check analyzer update/reload capabilities for your Elasticsearch version, because configured analyzers and filters have specific lifecycle constraints.

Do not add synonyms haphazardly. Overly broad rules increase false positives, making results drift from user intent. Maintain a curated synonym list—for example, by product domain, accepted abbreviations, or verified synonyms.

### Analyzers for autocomplete

Prefix-based autocomplete can use `edge_ngram` in the index analyzer and a simpler analyzer at search time. Example:

```json
PUT /products-suggest-v2
{
  "settings": {
    "analysis": {
      "filter": {
        "product_prefix_filter": {
          "type": "edge_ngram",
          "min_gram": 2,
          "max_gram": 15
        }
      },
      "analyzer": {
        "product_prefix_index": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "product_prefix_filter"]
        },
        "product_prefix_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "product_prefix_index",
        "search_analyzer": "product_prefix_search"
      }
    }
  }
}
```

For the word `spring`, edge n-gram can emit prefixes such as `sp`, `spr`, `spri`, ... within configured gram bounds. This enables prefix queries to match when users have typed only part of a word. In exchange, stored token count increases and the index can grow larger.

`edge_ngram` and `ngram` differ: edge n-gram emits substrings anchored at the start of a token, whereas n-gram emits substrings at multiple positions. For prefix-based autocomplete, edge n-gram is usually more suitable and economical.

## 4. Testing the analyzer with `_analyze` before reindexing

Never create a production index or reindex millions of documents just to see if an analyzer produces the expected tokens. The `_analyze` API lets you inspect processing output directly.

Test an analyzer declared in an index:

```json
POST /articles-analyzer-v2/_analyze
{
  "analyzer": "article_text",
  "text": "The QUICK brown foxes are running."
}
```

The response returns the list of tokens, positions, and offsets. You can use the output to verify lowercasing, stop words, stemming, and other filters behave as expected.

Test individual tokenizers/filters:

```json
POST /_analyze
{
  "tokenizer": "standard",
  "filter": ["lowercase", "asciifolding"],
  "text": "Crème Brûlée"
}
```

Test the search-time analyzer:

```json
POST /articles-synonyms-v1/_analyze
{
  "analyzer": "article_search",
  "text": "TV and automobiles"
}
```

Prepare an input suite representative of real data:

- Mixed casing, punctuation, and special characters.
- Accented and unaccented words.
- Abbreviations, proper nouns, and domain terms.
- Numbers, product codes, emails, or identifier strings.
- Singular/plural words and variants needing stemming.
- Multi-word phrases and phrase queries.

Do not test only one neat sample sentence. An analyzer may handle simple sentences cleanly yet break product codes, proper nouns, or domain terms.

## 5. Why do analyzer changes usually require reindexing?

When a document is indexed, the analyzer emits tokens and Elasticsearch stores them in the inverted index. `_source` still retains the original content (if `_source` is enabled), yet already-generated tokens do not change automatically when you edit an analyzer configuration.

For example, initially the analyzer did not apply stemming:

```text
Document text: "running"
Indexed token: "running"
```

Later the new analyzer applies stemming:

```text
Document text: "running"
New indexed token: "run"
```

If you only change the query-time analyzer, the query may be analyzed into `run` while old documents still hold token `running`. Results may fail to match as expected. For old documents to get the new tokens, documents must be reindexed with the new analyzer.

Key distinctions:

- **Changing the index analyzer:** affects tokens stored in the inverted index; requires reindexing existing data to apply fully.
- **Changing the search analyzer:** changes how queries are analyzed. If indexed tokens remain compatible with the new query analysis, reindexing may not be required, though mapping and analyzer update capabilities of your version must be verified.
- **Changing field mappings or data types:** cannot always be updated directly on existing fields; usually requires a new index and migration.
- **Changing `_source`:** modifies document data, not just the analyzer; requires updating/reindexing data as needed.

For significant changes, creating a new index is easier to control and roll back. Do not rely on in-place settings edits hoping Elasticsearch will rebuild the entire inverted index automatically.

## 6. Reindexing into a new index

The Reindex API reads documents from a source index and writes them into a destination index. It copies `_source` contents; it does not automatically copy settings, mappings, aliases, or templates from source to destination. Therefore, create the destination index beforehand with the desired analyzer, mapping, and settings.

Suppose the old index is `articles-v1` and the new index is `articles-v2`.

### Step 1: Create the destination index

Create `articles-v2` with the new analyzer and mapping verified via `_analyze`:

```json
PUT /articles-v2
{
  "settings": {
    "analysis": {
      "analyzer": {
        "article_text_v2": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "article_text_v2"
      },
      "body": {
        "type": "text",
        "analyzer": "article_text_v2"
      },
      "category": {
        "type": "keyword"
      }
    }
  }
}
```

### Step 2: Run reindex

```json
POST /_reindex?wait_for_completion=true
{
  "source": {
    "index": "articles-v1"
  },
  "dest": {
    "index": "articles-v2"
  }
}
```

Elasticsearch reads `_source` from each document in `articles-v1` and indexes it into `articles-v2`. The destination index's analyzer runs when writing the new documents, rebuilding the inverted index under the new configuration.

For large datasets, run reindex asynchronously with `wait_for_completion=false`. The API returns a task ID to monitor progress via the Tasks API. Watch processed document counts, failures, version conflicts, and cluster resources while running.

### Step 3: Verify reindex results

Compare document counts:

```http
GET /articles-v1/_count
GET /articles-v2/_count
```

Verify the mapping:

```http
GET /articles-v2/_mapping
```

Inspect several sample documents:

```http
GET /articles-v2/_doc/article-100
```

Matching counts are necessary but not sufficient. Inspect important documents, missing fields, data types, parsing errors, business queries, and search results. If scripts, pipelines, or transforms ran during reindex, inspect output data thoroughly.

### Step 4: Switch the alias

Applications should access indices via a stable alias, such as `articles`, rather than coupling directly to physical names like `articles-v1`. Once the new index is ready, switch the alias atomically with an `_aliases` request:

```json
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "articles-v1",
        "alias": "articles"
      }
    },
    {
      "add": {
        "index": "articles-v2",
        "alias": "articles",
        "is_write_index": true
      }
    }
  ]
}
```

Alias actions in the same request are applied atomically at the cluster state level. The application continues referencing `articles`; after switching, the alias points to the new index.

If `articles` is currently the name of a concrete index rather than an alias, you cannot add an alias with the same name while that concrete index still exists. Plan an appropriate name/alias transition before your first migration.

## 7. Preventing data loss during reindexing

Reindexing reads from source and writes to destination over a period of time. If the application keeps updating the source, changes occurring after reindex has already scanned the corresponding documents may be missing in the destination. Production workflows must therefore handle concurrent writes.

Several strategies:

### Pause writes during a cutover window

1. Block or pause write operations to the source.
2. Run reindex to completion.
3. Verify data and queries.
4. Switch the alias to the destination.
5. Re-enable writes through the alias.

This strategy is simple and clear, though it introduces write downtime during cutover.

### Sync changes during migration

For systems needing minimal downtime, use dual-write or change data capture/outbox to propagate new changes to the destination during reindex. However, you must handle event ordering, duplicate writes, deletes, retries, and version conflicts. A typical workflow includes:

1. Start capturing source changes via outbox/CDC.
2. Run background reindex to the destination.
3. Replay changes generated during reindexing.
4. Reconcile and catch up to a clear checkpoint.
5. Switch aliases and route reads/writes to the destination.

Dual-writing directly from request threads into two indices can cause drift if one succeeds and the other fails. If used, implement retries, idempotency, and reconciliation; outbox/CDC usually provides a clearer source of truth and replay mechanism.

### Retain rollback capability

Do not delete the old index immediately after switching the alias. Retain it long enough to monitor errors, cross-check results, and roll back if needed. To roll back, point the alias back to the old index via an alias request. Delete the old index only after confirming the new index is stable and backups follow operational policy.

## 8. Reindexing with additional transformations

Reindexing can combine scripts or ingest pipelines to transform data while copying. For example, renaming a field in `_source` or setting default values:

```json
POST /_reindex
{
  "source": {
    "index": "articles-v1"
  },
  "dest": {
    "index": "articles-v2"
  },
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.containsKey('old_title')) { ctx._source.title = ctx._source.remove('old_title'); }"
  }
}
```

The script is illustrative only. For complex transformations, test on a data copy and limit scope before running in production. Reindex is not a backup substitute; a buggy script can write corrupted data to the destination.

If using an ingest pipeline, define the pipeline on the destination and specify `pipeline` under `dest` in the reindex request. Verify the pipeline handles all legacy documents, including documents with missing fields or unusual data types.

## 9. Declaring analyzers in Spring Data Elasticsearch

Spring Data Elasticsearch lets you describe mappings on entities with annotations. `@Field` can specify `analyzer` and `searchAnalyzer`:

```java
@Document(indexName = "articles-spring-data-v2")
public class ArticleDocument {

    @Id
    private String id;

    @Field(
        type = FieldType.Text,
        analyzer = "article_text",
        searchAnalyzer = "article_search"
    )
    private String title;

    @Field(
        type = FieldType.Text,
        analyzer = "article_text",
        searchAnalyzer = "article_search"
    )
    private String body;

    @Field(type = FieldType.Keyword)
    private String category;
}
```

Analyzer and token filter definitions belong in index settings, not solely in field annotations. You can manage settings via JSON/YAML resources using `@Setting` or create indices via `IndexOperations` with explicit settings and mappings. Verify exact APIs against your Spring Data Elasticsearch version.

An example resource-based settings configuration might contain:

```json
{
  "analysis": {
    "analyzer": {
      "article_text": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": ["lowercase", "asciifolding"]
      },
      "article_search": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": ["lowercase", "asciifolding"]
      }
    }
  }
}
```

In the application, decide clearly who owns index creation. If Spring Data auto-creates indices from entities, ensure settings resources are applied before data is written. If indices are managed by deployment/migration tooling, disable or avoid unintended auto-creation so mappings without analyzers are never created accidentally.

`@Document(indexName = "articles-spring-data-v2")` can bind an entity to a versioned index name during migration. In environments using aliases, configure the logical index/alias name in a way compatible with your Spring Data version and index management strategy. The critical point is that the destination index's live mapping must exist before repositories write data.

## 10. Search quality testing

Testing the analyzer only confirms expected tokens are emitted. It does not prove search results are better. Search quality must be evaluated using a representative query set paired with identified relevant documents.

### Evaluation dataset

Prepare a set of queries reflecting how users actually search. For each query, record documents judged relevant and their relevance grades if available.

Example:

| Query | Expected relevant documents | Notes |
|---|---|---|
| `spring data elasticsearch` | `doc-10`, `doc-14` | Technical phrase search. |
| `tv` | `doc-21`, `doc-22` | Verify synonym with `television`. |
| `running` | `doc-31`, `doc-32` | Verify stemming. |
| `crème brûlée` | `doc-41` | Verify diacritics and asciifolding. |
| `SKU-AX100` | `doc-50` | Verify identifier is not broken by analyzer. |

This is sample data. A real test suite must reflect your application's domain, languages, data, and user behavior.

### Precision and Recall

- **Precision@k:** among the top k results, how many are relevant.
- **Recall@k:** among all known relevant documents, how many appear in the top k results.

For example, a query has 10 labeled relevant documents. Search returns the top 5 results, of which 4 are relevant:

```text
Precision@5 = 4 / 5 = 0.80
Recall@5    = 4 / 10 = 0.40
```

High precision with low recall can mean top results are very accurate yet many needed documents are missed. Balance these two metrics depending on the product.

### MRR and NDCG

- **MRR (Mean Reciprocal Rank):** evaluates the position of the first relevant result. If the first relevant result is at rank 1, reciprocal rank is 1; at rank 4, it is 1/4.
- **NDCG@k:** evaluates result ordering when documents have graded relevance levels. Highly relevant documents should rank above marginally relevant ones.

MRR is useful when users typically click the first good result. NDCG is useful when multiple relevance tiers exist and ordering within top-k matters strongly.

### Comparing old and new analyzers

Run the same query suite against both the old index and the new index. Record:

- Number of queries returning results.
- Precision@k, Recall@k, MRR, or NDCG@k.
- Queries showing clear improvement.
- Queries suffering degraded quality or new false positives.
- Response latency and index size.

Do not look only at average scores. One change might improve most queries while breaking important groups such as product codes, proper nouns, or Vietnamese queries. Slice metrics by intent/language to spot regressions.

## 11. Tools for inspecting relevance and queries

### Explain API

`_explain` helps clarify why a document matched or failed to match a query and how its score was computed:

```json
GET /articles-v2/_explain/article-100
{
  "query": {
    "match": {
      "body": "spring elasticsearch"
    }
  }
}
```

The output lets you inspect whether the document matched and individual score components. This is a diagnostic tool for a single document, not a replacement for multi-query relevance evaluation.

### Profile API

Profile lets you observe execution cost across query components on shards:

```json
GET /articles-v2/_search
{
  "profile": true,
  "query": {
    "match": {
      "body": "spring data elasticsearch"
    }
  }
}
```

Profile adds overhead and produces a large response; enable it only during diagnostics. It analyzes query performance rather than directly measuring relevance quality.

### Search analyzer in queries

You can specify an analyzer directly on a `match` query to inspect how the query is analyzed:

```json
GET /articles-v2/_search
{
  "query": {
    "match": {
      "body": {
        "query": "TV and automobiles",
        "analyzer": "article_search"
      }
    }
  }
}
```

This is useful when comparing analyzers or testing search-time synonyms. For formal evaluation, use the exact query configuration that the production application sends.

## 12. Automating tests in a Spring project

Search testing can be organized into multiple layers:

1. **Analyzer unit-like tests:** invoke `_analyze` on a test index and compare emitted tokens against expected tokens.
2. **Mapping tests:** confirm fields have expected types, analyzers, search analyzers, and settings.
3. **Integration tests:** index a sample document set, execute queries, and verify result sets.
4. **Relevance regression tests:** run a relevance-labeled query suite on both old and new indices and compute metrics.
5. **Performance tests:** measure latency, throughput, and index size with production-like data.

A simple integration test can use `ElasticsearchOperations` or a repository to write documents, then query and assert results. Refresh the index in tests when searching immediately after writes; do not rely on arbitrary sleep delays.

Illustrative test structure:

```java
@Test
void searchShouldFindStemmedTerm() {
    // Arrange: index a document containing "running".
    // Act: search using the word "run" through the configured analyzer.
    // Assert: the expected document appears in the results.
}
```

The snippet above is an illustrative skeleton; exact index creation, refresh, and query execution depend on your test infrastructure and Spring Data version. For relevance tests, externalize expected query/document judgments into data fixtures so they are easy to expand and compare across analyzer versions.

## 13. Safe analyzer deployment workflow

An analyzer change should follow repeatable, verifiable steps:

1. **Capture baseline:** save current settings, mapping, sample queries, relevance labels, and metrics.
2. **Diagnose the issue:** categorize failing queries, such as stemming, synonyms, diacritics, identifiers, or autocomplete.
3. **Design the analyzer:** make minimal necessary changes to character filters, tokenizer, and token filters.
4. **Verify with `_analyze`:** use representative sentences and confirm output tokens.
5. **Create new index:** apply new settings/mapping and verify the live mapping.
6. **Reindex:** copy documents, monitoring task progress, errors, and version conflicts.
7. **Test:** run functional tests, relevance regression tests, and performance tests.
8. **Sync new data:** ensure changes occurring during reindexing have been applied to the destination.
9. **Switch alias:** cut over reads/writes in a controlled operation.
10. **Monitor and roll back if needed:** retain the old index until the new index is confirmed stable.

Store settings, mappings, and test fixtures in source control so every index creation is reproducible. Never manually edit analyzers directly in production without a reviewed and tested migration.

## 14. Key points to remember

- Analyzers consist of character filters, a tokenizer, and token filters; processing order determines final tokens.
- `analyzer` applies at index time; `search_analyzer` applies when analyzing queries.
- `_analyze` is essential for checking tokens before creating an index or reindexing.
- Changing the index analyzer does not rebuild the inverted index for old documents; reindexing is required to apply it to existing data.
- Reindexing only copies document `_source`; the destination must be created first with desired settings and mappings.
- Use versioned indices and a stable alias for controlled cutover, testing, and rollback.
- Handle concurrent writes during reindexing via a maintenance window, dual-write, or well-designed outbox/CDC.
- Token verification alone is insufficient; build a relevance dataset and track metrics such as Precision@k, Recall@k, MRR, or NDCG.
- The Explain API helps explain document scores; the Profile API helps diagnose performance and incurs overhead.
- In Spring Data Elasticsearch, annotations and settings resources must match live mappings; editing an entity does not automatically migrate old indices.

Changing an analyzer directly affects search behavior. Combining token inspection, controlled reindexing, and a relevance test suite helps Spring Data Elasticsearch applications improve search quality while preserving verification and safe rollback capabilities.
