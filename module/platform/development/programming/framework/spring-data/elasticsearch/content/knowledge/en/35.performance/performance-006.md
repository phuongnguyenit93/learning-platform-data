# Controlling Leading Wildcards, Scripts, and Resource-Intensive Queries

An Elasticsearch query can return accurate results yet consume far more CPU, heap, I/O, and processing time than necessary. Common examples include wildcards starting with an asterisk, regexps on high-cardinality fields, scripts evaluated over millions of documents, sorts/aggregations on fields without suitable mappings, or deep pagination using `from/size`.

In Spring Data Elasticsearch, Query DSL is simply how the application sends requests to Elasticsearch. Using `NativeQuery` or a repository method does not make an inherently expensive query cheap. To control cost, you need to understand how queries execute, choose appropriate mappings, narrow candidate sets before running heavy operations, and measure on production-like data.

This article focuses on leading wildcards, prefix/substring search, script queries and script sorts, high-cost query patterns, cluster-level guardrails, writing queries via Spring Data Elasticsearch, as well as profiling and monitoring tools.

## 1. Why are some queries resource-intensive?

Elasticsearch indexes documents into structures like inverted indexes and doc values. A simple query can look up terms directly in the inverted index. However, some queries must inspect or evaluate a large number of terms or documents before determining matches.

Factors that commonly increase cost:

- Patterns without a fixed prefix, such as `*timeout`.
- Regexes that can match a large number of terms.
- Scripts that must execute for every document in a candidate set.
- Sorts or aggregations needing to read values across many documents.
- Queries lacking selective filters.
- Pagination skipping too many results.
- Aggregations creating many buckets or dealing with high cardinality.
- Requests returning too many hits or too much `_source` data.
- Many heavy queries running concurrently on the same shard/node.

Cost does not depend solely on how many documents are finally returned. A request with `size: 10` can still consume substantial CPU if Elasticsearch has to evaluate millions of candidates to find those 10 results.

## 2. How do wildcard queries work?

Wildcard queries match terms against a pattern. Two common characters:

- `*` matches zero or more characters.
- `?` matches exactly one character.

Example:

~~~json
{
  "query": {
    "wildcard": {
      "username.keyword": {
        "value": "admin*"
      }
    }
  }
}
~~~

The pattern `admin*` has a fixed prefix. Elasticsearch can use the prefix to narrow down the terms it needs to examine.

The pattern `*admin` has no fixed prefix. To find terms ending with `admin`, the engine may have to inspect a large portion of the field's term dictionary. On high-cardinality fields, the cost can be substantial.

The pattern `*admin*` is even broader because the substring can appear at any position.

For example, a field `path.keyword` holding millions of URLs or paths:

~~~text
/api/v1/orders/timeout
/api/v1/users/timeout
/archive/timeout-report
/system/logs/timeout
...
~~~

The query:

~~~json
{
  "query": {
    "wildcard": {
      "path.keyword": "*timeout"
    }
  }
}
~~~

may need to examine very many terms in `path.keyword`.

Contributing factors:

- Number of distinct terms.
- Term length.
- Number of queried shards.
- Number of documents containing the field.
- Selectivity of accompanying filters.
- Caching and filesystem cache state.
- Concurrent load on the node.

A wildcard that looks small in JSON can still generate significant work on each shard.

### 2.1. Wildcards are not the same as full-text search

If users want to search products by keywords, use a `match` query on a `text` field:

~~~json
{
  "query": {
    "match": {
      "description": "wireless mouse"
    }
  }
}
~~~

If exact matching on codes is needed, use a `term` query on `keyword`:

~~~json
{
  "query": {
    "term": {
      "sku": "SKU-1001"
    }
  }
}
~~~

If prefixes are needed, use a `prefix` query or prefix-optimized mapping. Only use `wildcard` when pattern matching is genuinely part of the search requirement.

## 3. Why are leading wildcards especially expensive?

An inverted index is organized to locate terms and documents containing them. With a prefixed pattern, the engine can start from a narrower range of terms in the dictionary.

With a pattern starting with a wildcard, such as `*error`, there is no leading character to bound the range. The engine may have to inspect many terms to find those matching the pattern. When a field holds many distinct values, the number of terms to check can grow sharply.

For example, a `path.keyword` field containing millions of URLs or paths. A `*timeout` query may have to examine many terms on every shard.

Contributing factors include distinct term count, term length, shard count, filter selectivity, caching, and concurrent load. A wildcard that appears short in JSON can still create heavy work.

## 4. Choosing alternative queries by intent

Before optimizing a wildcard, clarify what the user actually wants to search for.

| Requirement | Mechanism to consider |
|---|---|
| Exact value | `term` query on `keyword` |
| Full-text search | `match` query on `text` |
| Starts with a prefix | `prefix` query |
| Multi-word autocomplete | `search_as_you_type` or completion suggester depending on use case |
| Arbitrary substring | `ngram` index or `wildcard` field |
| Ends with a suffix | Reversed-string field with `prefix` query, if appropriate |
| Complex pattern | Bounded `wildcard`/`regexp` with load testing |
| Business-logic comparison | Precomputed field or script after narrow filtering |

Do not replace a wildcard with a script just because a script feels easier to write. Scripts often execute per candidate document and can be even more expensive.

## 5. Using prefix queries instead of fixed-prefix wildcards

If the requirement is to match values starting with a string, use a `prefix` query:

~~~json
{
  "query": {
    "prefix": {
      "username.keyword": {
        "value": "admin"
      }
    }
  }
}
~~~

This query expresses prefix semantics clearly and is often easier to optimize than a general wildcard like `admin*`.

Prefix queries can still be expensive if the field has high cardinality or the mapping does not optimize prefixes. Elasticsearch can support `index_prefixes` on `text` fields to accelerate prefix queries within configured length bounds.

Example mapping:

~~~json
{
  "name": {
    "type": "text",
    "index_prefixes": {
      "min_chars": 2,
      "max_chars": 10
    }
  }
}
~~~

`index_prefixes` builds extra index structures for prefixes within the chosen range, increasing storage/indexing cost while reducing prefix query work.

Choose `min_chars` and `max_chars` based on actual autocomplete patterns. Do not enable this on every `text` field unless needed.

## 6. Autocomplete does not always need wildcards

For product or user name autocomplete, specialized options exist.

### 6.1. search_as_you_type

The `search_as_you_type` field type creates sub-fields supporting partial phrase matching as users type. Queries commonly use `multi_match` with type `bool_prefix`.

Mapping:

~~~json
{
  "name": {
    "type": "search_as_you_type"
  }
}
~~~

Query:

~~~json
{
  "query": {
    "multi_match": {
      "query": "wire mou",
      "type": "bool_prefix",
      "fields": [
        "name",
        "name._2gram",
        "name._3gram"
      ]
    }
  }
}
~~~

This fits word- and word-order-based autocomplete. It is not an arbitrary character-level substring matcher.

### 6.2. Edge n-gram

An edge n-gram analyzer indexes token prefixes. For example, the token `wireless` can generate terms `wi`, `wir`, `wire`, `wirel`, ... up to configured bounds.

Illustrative mapping/settings:

~~~json
{
  "settings": {
    "analysis": {
      "tokenizer": {
        "edge_prefix_tokenizer": {
          "type": "edge_ngram",
          "min_gram": 2,
          "max_gram": 12,
          "token_chars": ["letter", "digit"]
        }
      },
      "analyzer": {
        "prefix_index_analyzer": {
          "type": "custom",
          "tokenizer": "edge_prefix_tokenizer",
          "filter": ["lowercase"]
        },
        "prefix_search_analyzer": {
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
        "analyzer": "prefix_index_analyzer",
        "search_analyzer": "prefix_search_analyzer"
      }
    }
  }
}
~~~

Edge n-gram fits prefixes of individual tokens. It enlarges the index because each original token generates multiple terms. Choose gram limits and `token_chars` carefully.

### 6.3. N-gram for substrings

If the requirement is matching substrings at any position, an `ngram` tokenizer can index substrings of specified lengths.

For example, with token `mouse` and gram size 3, grams can include `mou`, `ous`, `use`. A query for `ous` can match the original token.

N-grams increase term counts and index size, especially for long strings. Consider `min_gram`/`max_gram`, language and Unicode behavior, punctuation, normalization, strings shorter than `min_gram`, index size, and indexing throughput. N-grams can be used to generate candidates followed by a full-string check if exact semantics are required.

## 7. Wildcard field type for machine-generated strings

Elasticsearch provides the `wildcard` field type for pattern searches on high-cardinality strings, such as log messages, paths, or machine-generated identifiers.

Example mapping:

~~~json
{
  "properties": {
    "message": {
      "type": "wildcard"
    }
  }
}
~~~

Query:

~~~json
{
  "query": {
    "wildcard": {
      "message": {
        "value": "*connection reset*"
      }
    }
  }
}
~~~

The `wildcard` field is designed to support grep-like wildcard/regexp searches on strings and can fit this workload better than standard `keyword`. Its internals and trade-offs differ from `keyword`; it is not a replacement for `text` full-text search.

Verify support and behavior for your Elasticsearch version. Evaluate with real data and patterns while measuring index size, indexing throughput, and query latency.

Do not assume a `wildcard` field fits sorting, terms aggregations, or exact analytics like `keyword`. If the same data serves multiple use cases, you may need multi-fields or separate fields for each access pattern.

## 8. Finding suffixes by reversing strings

If a frequent requirement is matching values ending with a suffix, you can create an auxiliary field storing the reversed string.

Example:

~~~text
Original:    service-timeout
Reversed:    tuoemit-ecivres
~~~

A suffix query for `timeout` can be rewritten as a prefix query on the reversed field:

~~~json
{
  "query": {
    "prefix": {
      "name.reversed": "tuoemit"
    }
  }
}
~~~

This approach requires a normalizer/processor or application logic to populate the reversed field during indexing. It fits when suffix searching is a common and stable pattern.

Downsides include maintaining the auxiliary field consistently, defining Unicode and normalization rules, and potentially needing to reindex if the generation logic changes. Do not use this for arbitrary substring search when n-grams or `wildcard` fields are more suitable.

## 9. Restricting expensive queries with search.allow_expensive_queries

Elasticsearch provides the `search.allow_expensive_queries` setting to control certain queries deemed expensive. When disabled, restricted query types may be rejected instead of executed.

Affected queries can include `wildcard`, `regexp`, `fuzzy`, `script` queries, and others; the exact scope depends on the query type and Elasticsearch version. Prefix queries can be optimized in configurations like `index_prefixes`, so do not treat every prefix query the same as a leading wildcard.

This setting is a cluster-level guardrail. It does not magically turn slow queries into fast ones and does not replace mapping/query design.

Example cluster setting:

~~~http
PUT _cluster/settings
{
  "persistent": {
    "search.allow_expensive_queries": false
  }
}
~~~

When enabling this guardrail, the application must know which queries could be rejected. Do not deploy the change in production without inventorying queries, dashboards, and users relying on wildcards/regexps/scripts.

If a special query pattern is needed, consider designing a dedicated index or API with appropriate limits, permissions, and resource budgets.

## 10. What is a script query?

A `script` query evaluates an expression on documents to decide whether each document matches.

Example:

~~~json
{
  "query": {
    "script": {
      "script": {
        "source": "doc['price'].size() != 0 && doc['price'].value > params.minPrice",
        "params": {
          "minPrice": 100000
        }
      }
    }
  }
}
~~~

The script checks that `price` exists and exceeds the threshold.

If the same logic can be expressed with a `range` query, use the native query instead:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gt": 100000
      }
    }
  }
}
~~~

Range queries can leverage numeric field index structures. Script queries typically evaluate the expression per candidate document with fewer equivalent optimization opportunities.

### 10.1. Narrow the document set before running scripts

If a script is genuinely necessary, combine it with selective filters:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "Accessories"
          }
        },
        {
          "range": {
            "createdAt": {
              "gte": "2026-01-01"
            }
          }
        },
        {
          "script": {
            "script": {
              "source": "doc['price'].size() != 0 && doc['price'].value * params.factor < params.limit",
              "params": {
                "factor": 1.1,
                "limit": 500000
              }
            }
          }
        }
      ]
    }
  }
}
~~~

The `category` and `createdAt` filters narrow the candidate set before the script is evaluated. Actual effectiveness depends on the query planner, shards, and data distribution; verify using profiling and metrics.

### 10.2. Check field existence before reading values

Do not assume every document contains the field. With doc values, check `size()` before accessing `.value`:

~~~painless
if (doc['price'].size() == 0) {
    return false;
}
return doc['price'].value > params.minPrice;
~~~

Accessing `.value` when a field is missing can cause the script to fail. For multi-valued fields, decide explicitly whether you need min, max, first, or all values; `.value` does not represent full array semantics.

## 11. Doc values and _source in scripts

For fields with doc values, scripts should usually use:

~~~painless
doc['price'].value
~~~

instead of reading the entire `_source` just to extract a single simple value.

Doc values are organized for per-document access. `_source` is JSON source and incurs different load/parse overhead. However, not every script context supports the same access methods; verify the context.

Some field types do not support doc values or may have `doc_values` disabled. In such cases, scripts must use another representation or the mapping must change.

Do not disable `doc_values` on fields used by script queries, sorts, or aggregations.

## 12. Differences between script query, script_score, and script sort

| Mechanism | Purpose | Typical cost |
|---|---|---|
| Script query | Decides whether a document matches | Evaluates script over candidate documents |
| script_score | Computes custom relevance score | Computes script score for documents selected by the query |
| Script sort | Computes sort key via script | Computes sort values for many hits/candidates |
| Runtime field | Computes field at query time | Repeated computation per accessed document |
| Ingest-time derived field | Precomputes before indexing | Increases write/storage cost, reduces search-time computation |

If a calculation is deterministic from source data, precomputing the field in the application or an ingest pipeline can cut per-query cost.

`script_score` is appropriate when scoring genuinely needs a custom formula. Before using it, filter candidates with native queries so the script runs only on a small subset.

Script sorting is usually more expensive than sorting on a field with doc values. Where possible, materialize a derived numeric/keyword field at index time and sort directly on it.

## 13. Script compilation cache and parameters

Elasticsearch compiles Painless scripts and caches compiled scripts. If every request builds a different source string by concatenating values into the script code, the cache can fragment and compilation overhead rises.

Do not construct script source by concatenating user input into strings. Keep the script source stable and pass values via `params`:

~~~json
{
  "script": {
    "source": "doc['price'].value > params.threshold",
    "params": {
      "threshold": 250000
    }
  }
}
~~~

Benefits:

- Stable source, easy to cache.
- Dynamic values do not change script identity.
- Reduces risk of constructing scripts from untrusted input.
- Easier to test and monitor.

You still need to limit the number of distinct scripts, control compilation rates, and use stored scripts when aligned with deployment policy.

## 14. Are runtime fields free?

Runtime fields let you define fields evaluated when queries need them, rather than storing indexed values. They are handy when flexibility or schema experimentation is needed.

Example runtime field:

~~~json
{
  "runtime_mappings": {
    "priceWithTax": {
      "type": "double",
      "script": {
        "source": "if (doc['price'].size() != 0) emit(doc['price'].value * params.factor)",
        "params": {
          "factor": 1.1
        }
      }
    }
  },
  "query": {
    "range": {
      "priceWithTax": {
        "gte": 100000
      }
    }
  }
}
~~~

Runtime fields may have to compute values for each accessed document. If queries frequently use that field over large datasets, repeated computation cost can be significant.

If the logic is stable and heavily used in filters, sorts, or aggregations, consider materializing the field at index time. Runtime fields fit flexible ad-hoc needs or fields queried infrequently that way.

## 15. Avoid scripts when native queries express the logic

Several operations have direct native query equivalents:

| Need | Native query to consider |
|---|---|
| Greater than / less than | `range` |
| Equals a value | `term` |
| One of a list | `terms` |
| String starts with | `prefix` |
| Full-text | `match` |
| Time window | `range` on `date` |
| Field exists | `exists` |
| Combining conditions | `bool` |
| Filtering nested objects | `nested` |
| Sorting numbers/dates | Sort on a field with doc values |

Example avoiding scripts:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        { "range": { "stock": { "gt": 0 } } },
        { "range": { "price": { "lte": 500000 } } }
      ]
    }
  }
}
~~~

Native queries generally leverage index structures better and are easier to read. Scripts should only be used when expressions cannot reasonably be modeled with native queries or when custom logic is justified by measurement.

## 16. Other resource-intensive queries to control

### 16.1. Regexp query

Regexps can match many terms, and complex expressions can be very costly. Avoid unbounded regexes on high-cardinality fields. If the pattern is simply a prefix, use a `prefix` query.

~~~json
{
  "query": {
    "regexp": {
      "code.keyword": {
        "value": "ORD-[0-9]{6}"
      }
    }
  }
}
~~~

Constrain input patterns and never let users submit arbitrary unvalidated regexes on public APIs.

### 16.2. Fuzzy query

Fuzzy queries find similar terms within an edit distance. They help with typo tolerance but can expand into many candidate terms.

Bound `fuzziness`, `prefix_length`, and `max_expansions`, and enable them only on fields/queries with a clear requirement.

### 16.3. Terms query with large lists

A `terms` query with a massive list can bloat the request body and increase processing cost. If the list originates from a large dataset, consider `terms` lookup or redesigning the data/index for more efficient filtering.

Do not send tens of thousands of IDs in every request if relationships or filtering can be modeled better.

### 16.4. Deep pagination

Using `from/size` to jump to very deep pages forces each shard to track many more results than the final hits returned. For instance, `from: 100000, size: 50` can consume significant memory and CPU.

For deep pagination, consider:

- `search_after` with a stable sort.
- Point in Time (PIT) to preserve a consistent snapshot while paginating.
- Scroll for appropriate batch extraction, not for typical interactive UI pagination.

Example `search_after`:

~~~json
{
  "size": 50,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "search_after": [
    "2026-11-13T08:00:00Z",
    "P-1001"
  ],
  "query": {
    "term": {
      "active": true
    }
  }
}
~~~

The `search_after` values must come from the sort values of the previous page's last hit. Sorting must include a stable tie-breaker to avoid duplicate or skipped documents.

### 16.5. Exact total hits

If you only need to know whether a next page exists, you do not necessarily have to compute exact total hits across the entire index.

You can set `track_total_hits` to `false` or cap it at an appropriate threshold. Computing exact totals on very large sets can increase cost.

### 16.6. High-cardinality aggregations

Terms aggregations with very many unique values can generate many buckets. Limit `size`, filter beforehand, use `composite` aggregations when iterating all buckets, or build summary indexes for repetitive dashboards.

### 16.7. Nested queries and joins

Nested queries must inspect internal nested documents. Parent-child joins carry their own costs and data/shard constraints. Use them only when relational semantics demand them; avoid sweeping join queries over all documents if denormalization is appropriate.

## 17. Filter context and scoring context

In a `bool` query, filter context fits conditions that only need true/false evaluation and no relevance score. For example, `category`, `active`, `tenantId`, and date ranges should usually live inside `filter`.

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "description": "wireless mouse"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "Accessories"
          }
        },
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  }
}
~~~

Filter context skips relevance scoring for those clauses. Some filters may use the query cache depending on query type, segment, and usage; do not assume every filter is cached.

Do not move every condition into `filter` mechanically. Conditions requiring scoring/relevance still belong in query context.

## 18. Placing limits on requests and query inputs

A public search API should bound what users can request:

- Page size.
- Number of sort fields.
- Number of aggregations and bucket sizes.
- Number of elements in `terms` lists.
- Length of wildcard/regexp patterns.
- Whether leading wildcards are permitted.
- Whether script queries are permitted.
- Request timeout.
- Concurrent queries per user/tenant.
- Access permissions on indexes/fields.

Do not accept arbitrary Elasticsearch DSL JSON from clients and forward it straight to the cluster. Build a search API with an explicit contract and allowlisted query features.

## 19. search timeout and cancellation

You can specify a timeout on a search request to cap wait time:

~~~json
{
  "timeout": "2s",
  "query": {
    "wildcard": {
      "message": {
        "value": "*connection reset*"
      }
    }
  }
}
~~~

A timeout does not guarantee that all work stops immediately across all shards. It bounds execution/search response time per Elasticsearch semantics; cancellation and cleanup may occur asynchronously.

At the application layer, distinguish client timeouts, Elasticsearch search timeouts, proxy timeouts, request cancellations from user disconnects, and cluster overload/rejections.

Do not treat a timeout as proof that a query had no impact. For queries involving scripts or application-side effects, design retries and cancellation explicitly.

## 20. Writing queries via Spring Data Elasticsearch

Spring Data Elasticsearch provides `NativeQuery` to send Elasticsearch Java API Client Query DSL in modern versions.

Example prefix query:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.prefix(p -> p
        .field("username.keyword")
        .value("admin")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<UserDocument> hits =
    operations.search(query, UserDocument.class);
~~~

Example wildcard query when pattern matching is a genuine requirement:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.wildcard(w -> w
        .field("message")
        .value("*connection reset*")
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Example filtering natively before full-text search:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.match(mm -> mm
            .field("description")
            .query("wireless mouse")
        ))
        .filter(f -> f.term(t -> t
            .field("category")
            .value("Accessories")
        ))
        .filter(f -> f.term(t -> t
            .field("active")
            .value(true)
        ))
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Builder names, lambdas, and overloads depend on Spring Data Elasticsearch and Java API Client versions. Verify against your project dependency's compile API. Even when constructed via `NativeQuery`, Elasticsearch semantics and execution costs match the underlying DSL.

### 20.1. Script queries via Java API Client DSL

Script queries can be expressed using the Java API Client Query DSL. The builder structure is fairly verbose, so keep the script source stable and pass `params` separately.

Illustrative Painless source:

~~~painless
doc['price'].size() != 0 &&
doc['price'].value > params.minPrice
~~~

If the query can be expressed with `range`, use `range` instead of a script. If a script is required, pair it with selective filters and verify field existence.

### 20.2. Repository methods can obscure cost

A method like `findByNameContaining` may be implemented via Spring Data query derivation. Do not assume whether it emits a `prefix`, `wildcard`, or `match` query as expected. Inspect the actual query sent or use an explicit query when semantics and performance require control.

For performance-sensitive queries, use clear method names, test the generated Query DSL, or use `NativeQuery` to express intent precisely.

## 21. Inspecting queries with the Profile API

The Profile API provides detailed per-shard query execution breakdowns.

Example:

~~~http
GET logs/_search
{
  "profile": true,
  "query": {
    "wildcard": {
      "message": {
        "value": "*connection reset*"
      }
    }
  }
}
~~~

Profiling helps identify which query node consumes time, rewrite and term expansion, expensive scoring or collectors, slow aggregations, and differences across shards.

Profiling carries overhead and does not fully represent end-to-end latency. It excludes network, queueing, fetch/serialization costs, and client load. Use it intentionally on suitable data and requests.

## 22. Slow logs, Task API, and node metrics

### 22.1. Search slow logs

Search slow logs help pinpoint slow queries per shard. Thresholds can be configured for the query phase and fetch phase in index settings, depending on Elasticsearch version.

Slow logs are useful for detecting overly broad wildcard/regexp patterns, high-cardinality aggregations, slow script queries/sorts, queries spanning many shards, and fetch phases returning oversized `_source`.

Do not set thresholds too low initially, as log volumes can grow very large.

### 22.2. Task API

Some search tasks can be inspected via the Tasks API:

~~~http
GET _tasks?detailed=true&actions=indices:data/read/search*
~~~

APIs and action filters may vary by version. Use this to inspect long-running tasks, cancel tasks when appropriate, and identify executing nodes.

Cancellation does not guarantee all work stops immediately; monitor task status after issuing a cancel request.

### 22.3. Node stats and thread pools

Monitor CPU and heap, garbage collection, search thread pool active/queue/rejected counts, search latency and request rate, circuit breaker trips, filesystem/cache, disk I/O and merge pressure, shard counts, and query fan-out.

Example API:

~~~http
GET _nodes/stats/jvm,thread_pool,indices,breaker
~~~

Stat names and response structures depend on the Elasticsearch version. Correlate metrics before, during, and after running workloads.

## 23. Controlled performance testing

Do not compare two queries based on a single run. Caches, merges, refreshes, shard placement, and background load can cause results to differ.

A benchmark process:

1. Use a dataset with production-like cardinality and scale.
2. Create a representative mapping.
3. Warm up consistently if the production workload runs with warm caches.
4. Run queries repeatedly and record p50, p95, p99.
5. Measure CPU, heap, GC, queues/rejections, and bytes transferred.
6. Compare leading wildcard, prefix, ngram, or wildcard field.
7. Compare scripts against native queries or precomputed fields.
8. Test concurrent load, not just single requests.
9. Verify that results have identical semantics.
10. Record Elasticsearch/JDK versions, shard count, mapping, and test data.

Do not benchmark in production using overly broad patterns or high concurrency without safeguards and a rollback plan.

## 24. Common pitfalls

| Symptom | Possible cause | How to address |
|---|---|---|
| `*term` query is slow | Leading wildcard inspects many terms | Use prefix/keyword design or wildcard field/ngram |
| Prefix query is still slow | High cardinality or unoptimized prefix | Check `index_prefixes`, mapping, and profile |
| Wildcard on text does not match raw string | Analyzer split tokens | Use appropriate `keyword` or `wildcard` field |
| Autocomplete generates many wildcard queries | Wrong search primitive chosen | Use `search_as_you_type` or edge n-gram |
| Script query burns CPU | Script runs over too many candidates | Use native queries or narrow filters first |
| Script sort is slow | Computes sort key per hit | Materialize field and sort with doc values |
| Script compiles repeatedly | Source changes per request | Keep source constant and pass `params` |
| Script fails on docs missing a field | Accessing `.value` without checking | Check doc field size first |
| Runtime field slows searches | Recomputed on many docs per request | Index the field if queried frequently |
| Deep `from/size` pages are slow | Each shard retains many intermediate hits | Use `search_after` and PIT |
| High-bucket aggregation uses lots of memory | High cardinality and large bucket size | Filter, top N, or composite aggregation |
| Query rejected when expensive queries disabled | Query falls under restricted category | Redesign or allow in a controlled way |
| Timeout fires yet cluster stays busy | Timeout is not immediate cancellation | Monitor tasks and bound concurrency |
| Repository query is inexplicably slow | Derived query emits unexpected DSL | Inspect actual query and use `NativeQuery` |
| Profile differs from production | Profile overhead and missing background load | Combine slow logs/metrics/benchmarks |

## 25. Process for designing and controlling expensive queries

When adding a search feature:

1. Define semantics: exact, full-text, prefix, substring, or regex.
2. Choose the matching field type and analyzer/normalizer.
3. Prefer native queries backed by index structures.
4. Avoid leading wildcards whenever possible.
5. If substrings are needed, evaluate `wildcard` fields or n-grams and their indexing costs.
6. Use scripts only when native queries cannot express the logic.
7. Use doc values when scripts access supported fields.
8. Narrow candidate sets with filters before heavy scripts/aggregations.
9. Cap page sizes, bucket sizes, `terms` lists, and pattern lengths.
10. Use `search_after`/PIT for deep pagination.
11. Set timeouts and concurrency budgets.
12. Check `search.allow_expensive_queries` against your query inventory.
13. Profile and benchmark on representative data.
14. Monitor slow logs, tasks, thread pools, heap, and circuit breakers.
15. Write integration/performance regression tests for critical queries.

## 26. Quick reference table

| Requirement | Option to consider |
|---|---|
| Exact match | `term` on `keyword` |
| Full-text search | `match` on `text` |
| Prefix | `prefix` query, `index_prefixes`, or edge n-gram |
| Word-based autocomplete | `search_as_you_type` |
| Arbitrary substring | n-gram or `wildcard` field |
| General wildcard pattern | Bounded `wildcard` with load measurement |
| Simple script logic | Replace with `range`/`term`/`bool` if possible |
| Mandatory script | Narrow filters, stable source, `params` |
| Sort on deterministic calculation | Precompute field and doc values |
| Deep pagination | `search_after` and PIT |
| Exact total hits not needed | `track_total_hits` false/threshold |
| High-cardinality aggregation | Filters, top N, or composite aggregation |
| Overly expensive queries | Expensive-query guardrail, timeouts, and rate limits |
| Diagnosing slow queries | Profile, slow logs, Tasks API, node stats |

Controlling leading wildcards and scripts starts with choosing the right search semantics. Leading wildcards such as `*term` may have to inspect many terms and become expensive on high-cardinality fields; `prefix` queries, `search_as_you_type`, n-grams, or `wildcard` fields fit better depending on requirements. Script queries, `script_score`, script sorts, and runtime fields must be used deliberately, with filters narrowing candidate sets and stable sources/params. Prefer native queries, bound pagination/aggregations/inputs, verify expensive-query guardrails, and measure with the Profile API, slow logs, task/thread-pool, and heap metrics. Spring Data Elasticsearch does not change the execution cost of the underlying DSL; inspect actual queries and benchmark on representative data before releasing search features.
