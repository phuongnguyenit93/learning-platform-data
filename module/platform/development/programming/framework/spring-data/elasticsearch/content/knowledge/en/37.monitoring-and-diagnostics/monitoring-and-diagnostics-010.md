# Slow Logs, Profile API, and Slow Query Analysis

When Elasticsearch search is slow, the first question is not just "is the JSON query complex?" but **where time is being spent**. A request can be slow due to query execution on shards, fetching and loading `_source`, aggregations, too many shards, queues/thread pools, networking, repeated application calls, or a resource-constrained cluster. You must distinguish user-perceived latency from the time reported by Elasticsearch.

Elasticsearch has two common query-level investigation tools:

- **Slow logs** record search or indexing operations exceeding configured time thresholds. They help find genuinely slow requests inside live workloads.
- **Profile API** breaks down the execution of a single search request into query, collector, fetch, and related components. It helps explain why a specific query takes time.

The two tools complement each other. Slow logs surface problems in real environments; the Profile API performs targeted analysis on a reproduced query. Profiling adds significant overhead and should not be turned on across all production requests. Slow logs also require appropriate thresholds, log levels, and retention policies so they neither flood storage nor leak sensitive query contents.

## 1. Understanding different time measurements

Before reading logs, identify which measurement is climbing:

| Measurement | Meaning | What it does not fully represent |
|---|---|---|
| Client/end-to-end latency | Time from when the application sends a request until it receives and processes the response | Not solely Elasticsearch execution time |
| Elasticsearch `took` | Server-reported time spent processing the search request | Excludes full network time and application processing |
| Search slow log | Time one shard spent in the query or fetch phase above threshold | Not a single end-to-end record for the whole request |
| Profile timings | Detailed timings of components during search execution | Not an accurate production latency benchmark |
| Queue time / thread pool | Time waiting for resources or signs of processing pressure | Does not directly explain which query clause burns CPU |

For example, a user might wait 900 ms while Elasticsearch `took` is only 180 ms. The rest may sit in DNS, HTTP connections, gateways, application queues, serialization/deserialization, or response handling. Conversely, high `took` usually points to rising processing time inside Elasticsearch, though you still inspect slow logs and node metrics to isolate the cause.

### 1.1 Search requests pass through multiple stages

A search is typically coordinated through a coordinating node and selected shards:

1. Client sends request to a node.
2. Node receives request, identifies shards, and fans out requests.
3. Shards execute the query phase.
4. Coordinator merges results, picks top hits, and may request fetches.
5. Shards load needed documents/sources in the fetch phase.
6. Coordinator builds the response and returns it to the client.

Time can climb at any stage. A query across many shards can be dominated by the slowest shard; a query with a fast query phase can still be slow if fetching large `_source` payloads.

### 1.2 Query phase and fetch phase

- **Query phase** finds matching documents, computes scores, collects top hits, and gathers aggregation results.
- **Fetch phase** retrieves document contents for selected hits, applying source filtering, stored fields, highlighting, or requested fields.

If the query slow log shows the query phase is fast while the fetch slow log exceeds thresholds, examine `_source` size, returned hit count, highlighting, stored fields, and the number of shards fetched. If the query phase is slow, examine query clauses, scoring, filters, aggregations, and index structure.

## 2. What is a slow log?

Elasticsearch slow logs are shard-level logs for operations exceeding configured duration thresholds. For search, thresholds can be set separately for the query phase and fetch phase. For indexing, thresholds can be set for index operations.

Slow logs are useful to:

- Detect slow queries occurring in real workloads.
- Locate indices/shards experiencing frequent threshold breaches.
- Capture query sources, durations, hit counts, or metadata recorded by your Elasticsearch version.
- Spot trends over time and identify recurring queries.
- Collect sample queries to reproduce in Dev Tools or tests.

Slow logs do not automatically analyze queries or pinpoint the exact slow clause. They record threshold-breaching events; you then use Query DSL, the Profile API, and metrics to explain why.

### 2.1 Slow logs are scoped by index and shard

Slow log thresholds are configured at the index level. A search request fanning out to multiple shards can emit multiple log entries if shards exceed thresholds. Therefore:

- One request can generate multiple slow log entries.
- A hot shard can appear far more often than other shards.
- Time in each entry reflects that shard's work, not total client request time.
- Do not mechanically sum shard times to infer end-to-end latency because shards typically execute in parallel.

If a request touches 12 shards and only one exceeds the threshold, logs may show only that shard. This is valuable evidence for finding skew or shards with differing data/segments.

### 2.2 Search slow logs and indexing slow logs

Elasticsearch has distinct configuration groups:

| Group | Target |
|---|---|
| `index.search.slowlog.*` | Search query phase and fetch phase |
| `index.indexing.slowlog.*` | Indexing operations |

This lesson focuses on slow searches. Indexing slow logs help when ingest, bulk, or updates create pressure affecting search, but they do not substitute for search slow logs.

## 3. Configuring search slow logs

Thresholds are set via index settings. Example threshold settings for the `products` index:

```http
PUT /products/_settings
{
  "index.search.slowlog.threshold.query.warn": "5s",
  "index.search.slowlog.threshold.query.info": "2s",
  "index.search.slowlog.threshold.query.debug": "1s",
  "index.search.slowlog.threshold.query.trace": "500ms",
  "index.search.slowlog.threshold.fetch.warn": "2s",
  "index.search.slowlog.threshold.fetch.info": "1s",
  "index.search.slowlog.threshold.fetch.debug": "500ms",
  "index.search.slowlog.threshold.fetch.trace": "200ms"
}
```

These thresholds are illustrative, not universal recommendations. Choose thresholds based on latency objectives, cluster size, background load, and sustainable log volume. Setting thresholds too low can generate massive log volume; setting them too high can miss common slow queries.

### 3.1 warn, info, debug, and trace levels

Each phase can have thresholds at multiple levels:

- `warn`: operations breaching a severe threshold.
- `info`: slow operations needing monitoring.
- `debug`: lower threshold for controlled detailed investigation.
- `trace`: lowest threshold, usually enabled only briefly.

An operation is typically logged at the highest level matching the threshold it crossed; do not assume the same operation is always logged four times. Exact logging behavior and formatting depend on the Elasticsearch version.

Set thresholds in descending order, e.g., warn 5s, info 2s, debug 1s, trace 500ms. Confirm behavior against your running version and the log levels enabled in your logging configuration.

### 3.2 Threshold -1 and disabling slow logs

Thresholds typically default to no slow logging until configured. You can disable a threshold with `-1` per Elasticsearch settings conventions:

```http
PUT /products/_settings
{
  "index.search.slowlog.threshold.query.warn": "-1",
  "index.search.slowlog.threshold.query.info": "-1",
  "index.search.slowlog.threshold.query.debug": "-1",
  "index.search.slowlog.threshold.query.trace": "-1"
}
```

Do not disable all log levels solely to cut log volume during an active incident. Tune thresholds to the investigation target and record settings before/after changes.

### 3.3 Applying configuration to new indices

If indices are created continuously by pattern, use an index template to set defaults for new indices:

```http
PUT /_index_template/products-template
{
  "index_patterns": ["products-*"],
  "template": {
    "settings": {
      "index.search.slowlog.threshold.query.warn": "5s",
      "index.search.slowlog.threshold.query.info": "2s",
      "index.search.slowlog.threshold.fetch.warn": "2s",
      "index.search.slowlog.threshold.fetch.info": "1s"
    }
  }
}
```

Index templates apply only when an index is created. Updating a template does not automatically modify settings on existing indices; update those indices separately.

### 3.4 Configuring indexing slow logs

To investigate slow indexing, you can configure:

```http
PUT /products/_settings
{
  "index.indexing.slowlog.threshold.index.warn": "5s",
  "index.indexing.slowlog.threshold.index.info": "2s",
  "index.indexing.slowlog.threshold.index.debug": "1s",
  "index.indexing.slowlog.threshold.index.trace": "500ms"
}
```

Indexing slow logs can surface oversized documents, heavy ingest pipelines, mapping explosions, or slow shard indexing. However, do not blame indexing for every search latency spike; check CPU, disk I/O, merges, refreshes, and thread pools to verify the relationship.

## 4. What to read in slow logs

Slow log formats can vary between versions, but typically contain:

- Timestamp and log level.
- Index name and shard.
- Query or fetch duration.
- Search operation type and hit count.
- Query source or part of query source if permitted by settings.
- Routing, metadata, or shard details depending on version.

When reading logs, look for patterns:

1. The same query shape repeating frequently.
2. One index or shard repeatedly breaching thresholds.
3. Whether the query phase or fetch phase is slow.
4. Queries slow only when returning many hits or large aggregations.
5. Latency spikes coinciding with ingest, merges, GC, or thread pool queues.

Do not only sort logs by maximum duration. A 400 ms query running thousands of times per minute can hurt far more than an 8-second query running once.

### 4.1 Finding repeated queries

If many log entries share the same query shape with different literal values, group by:

- Index and shard.
- Query type/shape.
- Searched fields.
- Filters/tenant.
- Page size and hit counts.
- Aggregations/sorts.

You do not need to keep sensitive literal values when grouping statistics. Normalize queries by replacing literals with placeholders to identify common query patterns.

### 4.2 Inspecting query source

Slow logs can record query source. This helps reproduce requests, yet sources can contain usernames, emails, search phrases, tenant IDs, or sensitive data. Review log access, retention, and redaction policies before enabling in live environments.

If full query sources are unnecessary, configure source-logging modes supported by your Elasticsearch version and security policy. Do not enable full request-body logging in production just to track down a single query.

## 5. Logging configuration and where to find logs

Index settings define **thresholds**. Node logging configuration determines whether the logger emits at that level and which appender/file receives the logs. Both must be configured.

If thresholds are set yet no slow logs appear, check:

1. Whether settings were applied to the right index.
2. Whether the slow log logger is enabled at the necessary level.
3. Whether node logging configuration routes the logger to the desired appender/file.
4. Whether any query actually breached the threshold on a shard.
5. Whether the log collector/agent collects that file.

Exact logger categories and filenames depend on distribution, logging framework, and Elasticsearch version. Consult the logging docs for your exact release rather than relying on legacy paths.

### 5.1 Viewing current settings

```http
GET /products/_settings?include_defaults=true&flat_settings=true
```

Look for `index.search.slowlog.threshold.*` keys to confirm active thresholds. Across multiple indices:

```http
GET /products-*/_settings?include_defaults=true&flat_settings=true
```

Inspect templates and live indices separately; a template may be right while previously created indices retain old settings.

### 5.2 Dynamic changes vs. changes requiring restarts

Many `index.search.slowlog.threshold.*` settings are dynamic index settings changeable via `_settings` without recreating indices. Node logger/appender config is separate and has different reload/restart rules depending on version/deployment.

Do not confuse changing index thresholds with changing node log levels. Adjusting only one side can leave slow logs missing.

## 6. Reading query slow logs and fetch slow logs

Search slow logs separate the query phase and fetch phase:

| Log phase | Measured portion | Common signs |
|---|---|---|
| Query | Finding and collecting matching documents/top hits | Heavy Query DSL, many clauses, scoring, aggregations, large shard data |
| Fetch | Retrieving document contents for hits | Large `_source`, many hits, highlighting, stored fields, or fetching many shards |

### 6.1 Slow query phase

Check:

- Does the query use overly broad `wildcard`, `regexp`, `prefix`, or fuzzy searches?
- Are there `script_score`, script queries, or runtime fields?
- Does a bool query have many clauses and nested queries?
- Is `must` scoring used where `filter` suffices?
- Is a `terms` list excessively large?
- Do aggregations have high cardinality, many buckets, or nested aggregations?
- Does a single query fan out to too many shards?

These query constructs are not inherently wrong. Impact depends on data, mappings, cardinality, index layout, and resource limits. Use the Profile API to find which specific part consumes time.

### 6.2 Slow fetch phase

Check:

- Is page size too large?
- Is full `_source` returned when only a few fields are needed?
- Do documents have huge `_source` payloads or many nested objects?
- Is highlighting enabled across many fields or long fragments?
- Are unnecessary stored fields/doc values requested?
- Are many hits fetched across many shards?

You can reduce returned data with source filtering:

```http
GET /products/_search
{
  "_source": ["sku", "name", "price"],
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "size": 20
}
```

In Spring Data Elasticsearch, configure source filtering or projections/DTOs matching your API version so only needed fields are retrieved. Avoid loading huge full entities if the response uses only a few attributes.
## 7. What is the Profile API?

The Profile API provides detailed insight into how Elasticsearch executes a search request. It shows how query components form an execution tree, estimated execution times of each node, and internal counters. It is a targeted diagnostic tool for analyzing a specific query after detecting a problem.

Profiling helps answer:

- Which Lucene queries does a query rewrite into?
- Which clause inside a bool query spends the most time?
- Are collectors or scoring the expensive part?
- Do aggregations/fetch contribute significantly?
- Do shards exhibit different execution behavior?

Profiling does not automatically recommend optimizations and does not measure total user wait time. Combine it with slow logs, response `took`, client latency, thread pools, node stats, and real data.
## 8. Enabling the Profile API for a search request

Add `"profile": true` to the search body:

```http
GET /products/_search
{
  "profile": true,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  },
  "size": 20
}
```

Elasticsearch returns normal search results alongside a `profile` section containing per-shard statistics. The profile section typically includes groups such as:

- `shards`: list of shards that participated in profiling.
- `searches`: search contexts profiled on the shard.
- `query`: tree of query nodes and their breakdowns.
- `rewrite_time`: query rewrite duration if reported.
- `collector`: collector details gathering results.
- `fetch`: fetch phase details in versions supporting this section.
- `aggregations`: aggregation profiling details when the request includes aggregations and the version supports it.

Exact structure varies by Elasticsearch version and query type. Read fields against actual cluster responses rather than hardcoding one JSON shape across all releases.

### 8.1 Per-shard profiles

Profiles are generated per shard. One response may contain multiple entries in `profile.shards`, each identifying node, index, shard, and related search executions.

When comparing:

- See which shard spent the most time.
- Check whether that shard differs in document/segment counts or workload.
- See whether the same query node has wide timing variance across shards.
- Check whether any shards were skipped due to routing or query target.

Do not sum all `time_in_nanos` across the query tree or across shards to derive `took`. Some timings are inclusive (including child times), shards run in parallel, and Profile does not measure every part of the request.

### 8.2 Reading the query tree

Inside `profile.shards[].searches[].query`, each query node can contain:

- `type`: executing Lucene query type, e.g., BooleanQuery or TermQuery.
- `description`: query description and parameters.
- `time_in_nanos`: node duration recorded by the profiler.
- `breakdown`: internal measurements such as scorer creation, advance, next document, score.
- `children`: child query nodes if composed of multiple clauses.

Simplified illustrative structure example:

```json
{
  "profile": {
    "shards": [
      {
        "id": "[node-id][products][0]",
        "searches": [
          {
            "query": [
              {
                "type": "BooleanQuery",
                "description": "+name:wireless +active:true",
                "time_in_nanos": 4200000,
                "breakdown": {
                  "score": 300000,
                  "advance": 1200000,
                  "build_scorer": 700000
                },
                "children": [
                  {
                    "type": "TermQuery",
                    "description": "name:wireless",
                    "time_in_nanos": 1800000,
                    "breakdown": {},
                    "children": []
                  }
                ]
              }
            ],
            "rewrite_time": 12000,
            "collector": []
          }
        ]
      }
    ]
  }
}
```

Numbers and fields in the example illustrate how to read the structure only; they do not represent a complete response or standard Elasticsearch timings.

### 8.3 Understanding breakdowns

Breakdowns show time recorded by the profiler across internal operations. Some names you may encounter:

| Component | General interpretation |
|---|---|
| `create_weight` | Preparing query weight for execution |
| `build_scorer` | Building the scorer to match/score documents |
| `next_doc` | Moving to the next matching document |
| `advance` | Skipping to a target document ID or next position |
| `score` | Computing relevance score |
| `match` | Checking match details in certain query types |
| `shallow_advance` | Optimized advance step for certain iterators |
| `compute_max_score` | Computing max score for top-hits optimization |

Names and breakdown sets depend on query type and Lucene version. Not every query reports every counter. Read them as evidence of work type rather than treating a single counter as an overall performance metric.

### 8.4 Parent and child timings

A parent query node can include child query times. Therefore, do not sum parent `time_in_nanos` with all children to find total time. Instead, inspect the tree to see query composition and compare sibling nodes or corresponding breakdowns.

If a parent `BooleanQuery` takes a long time, expand child nodes to see which clause contributes most. If child nodes are all fast yet the parent remains high, the remaining time may sit in combination, scoring, coordination, or collectors.

## 9. Profiling collectors, fetch, and aggregations

Query nodes are not the only part of a search.

### 9.1 Collector

Collectors receive matching documents and gather outputs such as top hits, total hits, or aggregation inputs. A query may locate candidates quickly while collectors still spend significant time processing many documents, scoring, or maintaining many buckets.

In profile output, read collector details alongside the query tree. If collectors take substantial time, check:

- `size` and `track_total_hits`.
- Field sorting vs. score sorting.
- Aggregations and bucket counts.
- Whether the query scans many candidates before selecting top hits.
- Whether filter context can replace scoring for clauses not needing relevance.

### 9.2 Fetch phase

Fetch retrieves contents of selected hits. If the query tree is fast while fetch timing is significant, shrink the payload:

```http
GET /products/_search
{
  "_source": ["sku", "name", "price"],
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "size": 20
}
```

In addition to source filtering, check highlighting, stored fields, script fields, and document size. Not all versions present the fetch profile section identically; combine with fetch slow logs and request options to assess cost.

### 9.3 Aggregations

Aggregations can consume heavy resources even when few hits are returned. For example, a terms aggregation on a high-cardinality field can create many buckets and require cross-shard merging.

Example:

```http
GET /products/_search
{
  "size": 0,
  "profile": true,
  "aggs": {
    "by_sku": {
      "terms": {
        "field": "sku",
        "size": 10000
      }
    }
  }
}
```

If aggregations are the slow part:

- Confirm fields have appropriate `keyword` or numeric mappings.
- Check actual cardinality and bucket `size`.
- Consider composite aggregations when paginating across many buckets.
- Use pre-aggregations/materialized summaries for recurring workloads on large datasets.
- Avoid aggregating on text fields without appropriate subfields.

## 10. Limitations and cost of the Profile API

The Profile API incurs significant overhead because Elasticsearch instruments and records timings for many internal operations. Profiled queries can run noticeably slower than normal execution.

Limitations to keep in mind:

- Do not treat profile timings as SLOs or production benchmarks.
- Do not enable profiling for every user request.
- Profiling does not fully capture network latency, client processing, or queueing outside query execution.
- Multi-shard search requests produce many profile trees; output can be verbose and hard to read.
- Profiling can raise CPU, memory, and response payload size.
- Query/request caches or execution paths may be affected by profiling mode depending on version.
- A single profile does not represent high-concurrency workloads.

Pick a representative query, use production-like data and conditions, and run profiling in a safe environment or controlled investigation window. Once you understand the issue, disable profiling and re-measure normal queries.

## 11. Using slow logs and Profile API together

A practical workflow:

1. Use metrics/APM and slow logs to find genuinely slow query patterns.
2. Group entries by query shape, index, shard, and frequency.
3. Take a representative request and strip sensitive data.
4. Reproduce the query against the same index/mapping and similar data.
5. Run the normal query to record baseline `took` and client latency.
6. Enable `profile: true` for that request.
7. Read per-shard query trees, breakdowns, collectors, fetch, and aggregations.
8. Change one factor at a time: query clause, sort, size, source filtering, or aggregation.
9. Re-run without profiling to compare real latency.
10. Monitor slow logs/metrics after deployment to verify improvement in live workloads.

Slow logs answer "which requests breached thresholds in the running environment?". Profiling answers "how was this query executed?". Do not use Profile as a substitute for capturing real requests, and do not expect slow logs to explain root causes by themselves.
## 12. Where slow logs are emitted and how to check loggers

Slow logs are emitted into Elasticsearch logging with dataset metadata `slowlog`. Common loggers:

- `index.search.slowlog`: search slow log.
- `index.indexing.slowlog.index`: indexing slow log in current versions.

Exact log files depend on installation and node configuration. In standard Elasticsearch distributions, search slow logs typically use the `_index_search_slowlog.json` suffix, while indexing slow logs use `_index_indexing_slowlog.json`. With Elastic Stack Monitoring, events may also be observed in Stack Monitoring.

### 12.1 Two distinct configuration places

Distinguish:

- Index settings: decide which operations exceed thresholds and are emitted.
- `log4j2.properties`/node logging configuration: decides logger levels, destinations, rotation, and how logs are written to files.

Slow logs may not appear if thresholds are enabled while the node logger level blocks that level, or if the log collector does not collect the right file.

The search slow log logger is currently typically `index.search.slowlog`; indexing slow logs may have more granular logger names by operation and version. Inspect the `log.logger` field in actual events rather than guessing logger names from filenames.

### 12.2 Viewing current slow log settings

```http
GET /products/_settings?include_defaults=true&flat_settings=true
```

You can filter slow log settings across multiple indices:

```http
GET /_all/_settings?expand_wildcards=all&filter_path=*.settings.index.*.slowlog
```

All thresholds default to `-1`, meaning slow logging is off until configured. Seeing no logs under default settings is normal behavior.

### 12.3 Monitoring files and metadata

In log events, helpful fields for analysis include:

- `log.level`, `log.logger`.
- `elasticsearch.slowlog.took` and `elasticsearch.slowlog.took_millis`.
- `elasticsearch.slowlog.message` to identify index/shard.
- `elasticsearch.slowlog.source` if query source is logged.
- `elasticsearch.slowlog.total_hits`, `total_shards`, `search_type`.
- `elasticsearch.slowlog.id` if the request sent `X-Opaque-Id`.

Exact schemas depend on version and log ingestion setup. If you need to link logs to application requests, send `X-Opaque-Id` with a non-sensitive correlation ID. Avoid putting tokens, emails, or personal data into this header.

## 13. Query logging: unified option for search in newer versions

In newer Elasticsearch versions, Elastic provides **query logging** as a unified option for search operations. Query logging records end-to-end processing time measured by Elasticsearch for the request, whereas traditional slow logs record shard-level processing time. Query logging can cover multiple query languages such as Query DSL, ES|QL, EQL, and SQL with one configuration.

Per current Elastic documentation, for search operations, query logging is the recommended alternative when supported by your version/deployment. Slow logs remain the choice for indexing operations. Query logging availability and support scope depend on Elasticsearch version, license/deployment, and feature release status; check docs for your exact cluster before designing logging pipelines.

| Tool | Time scope | Request type | Purpose |
|---|---|---|---|
| Search slow log | Shard-level query/fetch | Search operations | Find slow shards/phases |
| Indexing slow log | Index operation | Indexing operations | Find slow documents/indexing operations |
| Query logging | End-to-end request duration measured by Elasticsearch | Query DSL, ES\|QL, EQL, SQL per version support | Find slow requests at Elasticsearch level |
| Profile API | Internal query execution details | Profiled search requests | Explain query component costs |

Query logging does not make the Profile API redundant. Query logging helps identify slow requests; Profile shows execution structure and costs for a specific query. Slow logs remain useful when you need to know which shard or query/fetch phase was slow.

### 13.1 When to start with query logging?

If your cluster supports query logging, prefer it to locate slow search requests by server-measured time. It helps when:

- You want full request processing duration rather than shard phases only.
- The application uses multiple query languages.
- You want to find slow requests without piecing together multiple shard log entries.
- You need to correlate requests with callers via correlation metadata.

Once a slow query is identified, you can still use slow logs to find specific shards/phases and the Profile API to analyze the corresponding Query DSL.

### 13.2 When are slow logs still necessary?

Slow logs fit when:

- Your version does not support query logging or the deployment lacks that feature.
- You need to separate the query phase from the fetch phase.
- You need to identify specific shards repeatedly exceeding thresholds.
- Investigating indexing operations, since query logging does not replace indexing slow logs.

### 13.3 Do not enable all logging at low thresholds simultaneously

Query logging, search slow logs, indexing slow logs, and audit/request-body logging can produce huge log volumes. Enable each source purposefully, pick appropriate thresholds, and enforce retention. If recording request bodies to locate query sources, limit duration and access because payloads can contain sensitive data.

## 14. Search Profiler in Kibana

If your environment has Kibana with Search Profiler installed, you can use its UI to view Profile API responses as query trees and timing charts. It makes navigating query nodes, expanding child clauses, and reading breakdowns easier for complex queries.

Search Profiler is a viewer for profiles; the underlying data still comes from Elasticsearch profiling. Therefore:

- Profile API overhead still applies.
- Timings are still not real production latency.
- Profile JSON can change across Elasticsearch/Lucene versions.
- Do not build automation depending on unstable internal debug fields.

Without Kibana Search Profiler, you can call `_search` directly with `profile: true`, save the JSON response, and inspect each shard/query tree.
## 15. Common causes of slow queries

No single query type is always slow across all datasets. Below are patterns commonly worth investigating:

| Pattern | Why it can be slow | What to inspect |
|---|---|---|
| Broad wildcard/regexp | May scan a large portion of the term dictionary | Profile query, tighten patterns, design appropriate fields/indices |
| Fuzzy query with wide edit distance | Generates many term expansions | Reduce fuzziness, prefix length, or max expansions |
| Script query/script score | Evaluates per document during search | Check candidate count, precompute indexed fields where suitable |
| Deep pagination with from/size | Holds many intermediate results on each shard | Use search_after and PIT for deep pagination |
| Exact track_total_hits on large sets | Counts many matching documents | Disable or bound total hit tracking if exact numbers are unneeded |
| High-cardinality terms aggregation | Builds/merges many buckets, uses global ordinals | Check cardinality, bucket size, and aggregation pagination |
| Suboptimal field sort | Reads many values or lacks doc values | Check mapping, sort fields, and candidate counts |
| Returning many large _sources | Fetching and transferring payloads is costly | Source filtering, DTO/projections, reduce size |
| Many small shards | Single request fans out across many shards, adding coordination overhead | Check shard count, routing, and index strategy |
| Deeply nested queries | Multiplies nested documents and query work | Check nested paths, cardinality, and query shape |
| Ingest/merge resource contention | CPU, disk I/O, heap, and refresh are shared | Correlate slow logs with indexing, merge, GC, and thread pool metrics |

### 15.1 Wildcard, prefix, and regexp

A query like:

```json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "*1001"
      }
    }
  }
}
```

can be expensive because leading wildcards prevent narrowing the term range scanned. If business requirements allow, design alternative field/search strategies such as exact keyword, prefix fields, n-grams, or normalized fields. Do not change query types if search semantics must stay identical.

### 15.2 Deep pagination

With large `from`, Elasticsearch must collect many intermediate hits on each shard before returning later pages. Use `search_after` with a deterministic sort and Point in Time (PIT) for deep pagination:

```http
POST /products/_search
{
  "size": 100,
  "sort": [
    { "createdAt": "asc" },
    { "productId": "asc" }
  ],
  "search_after": [1730000000000, "product-1000"],
  "query": {
    "match_all": {}
  }
}
```

`search_after` values must come from the sort values of the previous page's last hit. Sorts should include a deterministic tie-breaker and sortable fields. With PIT, send search requests against the PIT to hold a consistent snapshot while paginating; PIT open/close syntax varies by API/version.

### 15.3 track_total_hits

If the UI only needs to show "more results exist" instead of an exact total, consider disabling or bounding `track_total_hits`. Counting every hit adds work on large datasets:

```json
{
  "track_total_hits": false,
  "size": 20,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
```

Change this only if the product does not need exact totals. Pagination, page counts, and UIs may rely on total hits.

### 15.4 Using filter context for non-scoring conditions

Conditions on status, tenant, product category, or price ranges usually only decide inclusion. Place them inside `filter` when relevance scores are unneeded:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "category": "keyboard"
          }
        }
      ]
    }
  }
}
```

Filter context skips relevance scoring for those clauses and can leverage caching when eligible. Not every filter is cached; caching behavior depends on the query, segment, and workload.

### 15.5 Aggregation cardinality and global ordinals

Terms aggregations on keyword fields typically use global ordinals. When cardinality is high or an index just refreshed, building global ordinals can contribute to latency. The Profile API does not fully measure all global-ordinals build work, so correlate with node/index stats and refresh timing.

Mappings can use `eager_global_ordinals` to shift part of the work to refresh/segment lifecycles:

```json
{
  "mappings": {
    "properties": {
      "category": {
        "type": "keyword",
        "eager_global_ordinals": true
      }
    }
  }
}
```

This is not a free optimization: it can increase heap usage and slow down refreshes. Consider it only when aggregation workloads are frequent enough and resources can absorb the cost.

## 16. Checking the cluster when Profile does not explain enough

A query can be slow because of cluster resources or queues, even when the query tree shows no unusual clause. Broaden investigation to nodes and thread pools.

### 16.1 Thread pools

Check the search thread pool:

```http
GET /_cat/thread_pool/search?v
```

Or node stats:

```http
GET /_nodes/stats/thread_pool,jvm,fs,indices
```

Inspect active, queue, rejected, and completed counts. Rising queues/rejections indicate nodes cannot keep up with workload. Thread pool names and response fields depend on version; read current API docs.

### 16.2 Node and index stats

```http
GET /_nodes/stats/indices,thread_pool,jvm,process,fs
```

```http
GET /products/_stats/search,query_cache,request_cache,segments,merges,refresh
```

Useful metric groups:

- Search query/fetch counts and times.
- Query cache/request cache hits, misses, evictions.
- Segment counts and merge activity.
- Refresh counts/times.
- JVM heap, GC, and process CPU.
- Disk I/O, free space, and shard allocation.

Compare over time and across nodes; a single snapshot rarely explains trends.

### 16.3 Hot threads

When CPU is high or a node exhibits abnormal latency, inspect hot threads:

```http
GET /_nodes/hot_threads
```

Results identify threads burning CPU in query execution, aggregations, indexing, merges, or GC. Hot threads is a point-in-time snapshot, so capture it while the issue is occurring.

### 16.4 Tasks API

View currently running search tasks:

```http
GET /_tasks?detailed=true&actions=*search
```

The Tasks API helps spot long-running requests or high task concurrency. Not every task exposes identical detail; combine with slow logs and client correlation IDs.

## 17. Reproducing slow queries fairly

When taking a query from slow logs or query logging, reproduce it under conditions as close to reality as possible:

- Same cluster/index or equivalent mapping and data volume.
- Same alias target, routing, and preference if used.
- Same query body, sort, aggregations, and `track_total_hits`.
- Same page size, source filtering, and highlighting.
- Same tenant/security filters.
- Same cache and refresh/merge conditions if investigating those effects.

If you copy only the query body while dropping sort, aggs, size, post_filter, or source fields, benchmarks may fail to reproduce the slow request.

### 17.1 Running an unprofiled baseline

Before enabling Profile:

1. Send the original query several times in a safe environment.
2. Record `took`, client latency, and hit counts.
3. Observe multiple runs rather than a single request.
4. Note cache conditions and concurrency.

Do not judge a query as permanently slow from a single cold-start run. Segment warming, caches, and filesystem caches can cause timings to differ across runs.

### 17.2 Enabling profile for one representative request

Add `profile: true` to the exact reproduced query. Read the query tree and breakdown to find relatively expensive components. Across multiple shards, compare all shards instead of reading only the first node.

### 17.3 Changing one factor at a time

Test sequentially:

- Replace a query clause or move eligible conditions into filters.
- Reduce page size or `track_total_hits`.
- Trim source fields/highlighting.
- Split or simplify aggregations.
- Replace deep pagination with `search_after`.
- Reduce fan-out with routing if the data model supports it.

Preserve business semantics. A faster query that returns wrong results is not a successful optimization.

### 17.4 Re-measuring without profile

After each change:

1. Run the query without `profile`.
2. Measure multiple runs under comparable conditions.
3. Compare median and tail latency (p95/p99) given enough samples.
4. Verify results are business-equivalent.
5. Monitor slow/query logs after deployment.

Do not directly compare profile `time_in_nanos` against unprofiled `took`. Profiling instrumentation adds overhead and can disable certain Lucene optimizations.
## 18. Applying in Spring Data Elasticsearch applications

Spring Data Elasticsearch provides repository abstractions and ElasticsearchOperations to build queries. Once slow logs or query logging identify a slow request, locate the call site in the application and verify which method emits the request.

### 18.1 Repository query methods

Example:

```java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Page<ProductDocument> findByActiveTrue(Pageable pageable);

    List<ProductDocument> findByCategoryAndActiveTrue(String category);
}
```

Query methods keep application code concise, but do not automatically make queries cheap. Check field mappings, page sizes, sorts, and how Spring Data constructs queries. A method returning Page may require total hits for page metadata; if the UI does not need exact totals, consider APIs returning Slice or structures suited to requirements.

### 18.2 NativeQuery and ElasticsearchOperations

When custom Query DSL is needed:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.match(mm -> mm
            .field("name")
            .query("wireless keyboard")
        ))
        .filter(f -> f.term(t -> t
            .field("active")
            .value(true)
        ))
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<ProductDocument> hits = operations.search(
    query,
    ProductDocument.class,
    IndexCoordinates.of("products-read")
);
```

Record query shape, index coordinates, pageable, sort, aggregations, and source filtering when reproducing. Do not save only user-entered strings; other options can dominate execution time.

### 18.3 Sending profile with the Elasticsearch Java API Client

If you need to profile a request built inside the application, you can use the Elasticsearch Java API Client directly (if the client bean/dependency for your version is configured):

```java
SearchResponse<ProductDocument> response = elasticsearchClient.search(
    search -> search
        .index("products-read")
        .profile(true)
        .query(query -> query.match(match -> match
            .field("name")
            .query("wireless keyboard")
        )),
    ProductDocument.class
);
```

The response includes profile data per the API client version. Use the exact client generation and generated types from your project dependency. When merely analyzing a query, calling REST in Kibana Dev Tools is usually simpler than modifying production code to toggle profiling.

### 18.4 Attaching correlation IDs via X-Opaque-Id

To link server request logs to an application operation, send the X-Opaque-Id header:

```http
GET /products-read/_search
X-Opaque-Id: catalog-search-req-8f31

{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
```

Slow logs can record this ID in the corresponding correlation field. In the application, generate IDs containing no personal info, log them in application logs, and propagate them across requests under investigation. How default headers/interceptors are configured depends on the Elasticsearch Java Client/transport version.

### 18.5 Do not enable profile across all repository calls

Do not make profiling the default behavior for repository requests. Enable it only for a selected request in debug environments or via a controlled diagnostic path. Turn it back off once the profile is captured.

## 19. Reading an incident from start to finish

Suppose the product search API sees p95 jump from 120 ms to 1.2 s.

### Step 1: Locate where latency lives

Compare client latency against Elasticsearch took. If client latency is high while took is low, check gateways, connection pools, networks, application code, and response handling. If both climbed, continue inside Elasticsearch.

### Step 2: Find slow requests

Use query logging if your version supports it. Otherwise, configure search slow logs on the relevant index with controlled thresholds. Use correlation IDs to link logs to endpoints/callers.

### Step 3: Separate query and fetch

If the query phase is slow, inspect query clauses, shards, and aggregations. If the fetch phase is slow, inspect page size, source, highlighting, and document sizes.

### Step 4: Reproduce the complete query

Capture body, sort, size, routing, filters, aggregations, source filtering, and alias targets. Run against the same data or an environment with equivalent mappings/cardinality.

### Step 5: Profile one request

Enable the Profile API on a representative request. Read each shard, query tree, child clauses, collectors, fetch, and aggregations. Do not sum parent-child timings or treat profile output as end-to-end latency.

### Step 6: Inspect the cluster

If profiling does not explain the latency, check search thread pool queues/rejections, node CPU/heap/GC, disk I/O, merges, refreshes, and shard distribution. Profile does not measure network, queue time, or coordinating-node reduce/merge fully.

### Step 7: Make controlled changes

Change one factor at a time while preserving semantics. For example, shrink source payloads, cap total hits, replace deep pagination, move conditions to filters, or tune aggregations.

### Step 8: Re-measure and verify

Run unprofiled queries, measure multiple samples, verify p95/p99, confirm business results, and monitor logs after deployment.

## 20. Common mistakes

### 20.1 Treating slow logs as full request duration

Search slow logs are shard-level and can log query/fetch separately. They exclude full network, queue, and application processing time. For request-level duration, use query logging if supported by your version.

### 20.2 Treating Profile API as a benchmark

Profiling adds overhead and can disable internal optimizations. Use it only to understand relative costs across query components, then re-measure unprofiled.

### 20.3 Summing timings in the query tree

Parent timings can include child timings. Summing nodes double-counts work. Compare at matching levels and inspect breakdowns.

### 20.4 Profiling only one shard

Distributed searches can have an abnormally slow shard. Inspect all profiled shard entries and cross-check shard stats.

### 20.5 Setting slow log thresholds too low

Surging log volumes add I/O and ingest/retention costs. Start with high thresholds, specific indices, and short investigation windows.

### 20.6 Forgetting logger levels and appenders

Index thresholds and node logging configuration are two separate layers. Check both if no logs appear.

### 20.7 Using profile to find queue/network latency

Profile does not measure network, queue wait times, or coordinating-node shard response merges. Check client APM, query logging, thread pools, and node stats.

### 20.8 Optimizing queries while ignoring fetch

Query phases can be fast while returning huge payloads. Read fetch slow logs and trim source/highlighting/page size where appropriate.

### 20.9 Optimizing for a rare request

Prioritize high-frequency queries, high p95/p99 queries, or queries carrying substantial aggregate cost. A 5-second request running once per day may matter far less than a 300 ms request running thousands of times per minute.
## 21. Slow query investigation checklist

### Identify signals

- [ ] Record endpoint, timestamp, p50/p95/p99, and client latency.
- [ ] Compare Elasticsearch took with end-to-end latency.
- [ ] Identify index/alias, shards, and query type.
- [ ] Record correlation ID or X-Opaque-Id if available.

### Collect requests

- [ ] Use query logging if supported by version; otherwise enable controlled slow logs.
- [ ] Save complete query bodies, including sort, size, routing, filters, and aggregations.
- [ ] Distinguish query phase from fetch phase.
- [ ] Group by query shape and frequency, not solely highest latency.

### Analyze

- [ ] Reproduce the query on equivalent data/mappings.
- [ ] Run an unprofiled baseline.
- [ ] Enable Profile API on a representative request.
- [ ] Read each shard, query tree, breakdown, and collector.
- [ ] Inspect fetch, source payload, and aggregations.
- [ ] Check thread pools, node stats, GC, disk, merges, refreshes, and shard skew as needed.

### Remediate and verify

- [ ] Change one factor at a time.
- [ ] Preserve semantics and data access permissions.
- [ ] Re-measure unprofiled across multiple samples.
- [ ] Compare p95/p99 and throughput under comparable load.
- [ ] Monitor query/slow logs after deployment.
- [ ] Disable temporary logging/profiling and restore proper thresholds.
- [ ] Verify log retention, access controls, and redaction.

## 22. Implementation principles

- Use slow logs to catch search shards/phases and indexing operations breaching thresholds.
- Remember all slow log thresholds default to -1 and must be configured explicitly.
- Configure query phase and fetch phase separately; apply settings to the right indices.
- Distinguish index thresholds from logger levels/appenders in node logging configuration.
- Pick thresholds matching latency objectives and log budgets; avoid low thresholds across all indices.
- On supported versions, consider query logging to find slow search requests at the Elasticsearch level.
- Use the Profile API on one representative query to inspect query trees, breakdowns, collectors, fetch, and aggregations.
- Never use profile timings as benchmarks or SLOs.
- Never sum parent/child timings or shard timings mechanically.
- Inspect thread pools, node stats, hot threads, and Tasks API when latency sits outside query execution.
- Reproduce full queries and vary one factor at a time.
- Re-measure unprofiled queries and watch p95/p99 after deployment.
- Use non-sensitive correlation IDs to link logs with application requests.
- Time-bound temporary logging, protect query sources, and set proper retention.

## 23. Summary

Slow logs and the Profile API answer two different questions. Slow logs capture threshold-breaching operations at the shard level for searches and at the document/indexing operation level for indexing. Search slow logs separate query phases and fetch phases, helping pinpoint which shard or stage is slow. Thresholds default to -1, so enable them deliberately while checking node logger levels/appenders. On newer Elasticsearch versions supporting query logging, it offers a unified choice to spot slow search requests by server-measured time; slow logs remain necessary for indexing and shard/phase analysis.

The Profile API dives into how a search request executes: query trees, Lucene query nodes, breakdowns, collectors, fetch, and aggregations. It incurs significant overhead and does not measure network latency, queue times, coordinating-node merges/reduces, or all background tasks such as building global ordinals. Tree timings can include child durations, so never sum numbers mechanically. Use profiling to understand relative costs of query components, then re-measure requests without profiling.

An effective workflow starts from latency metrics and query/slow logs, reproduces the full request, profiles a sample, inspects nodes/thread pools when needed, changes one factor at a time, and re-measures under comparable load. Optimizations must preserve search semantics and be validated by real latency after deployment.

## References

- [Elasticsearch — Slow query and index logging](https://www.elastic.co/docs/deploy-manage/monitor/logging-configuration/slow-logs)
- [Elasticsearch — Slow log settings](https://www.elastic.co/docs/reference/elasticsearch/index-settings/slow-log)
- [Elasticsearch — Profile search requests](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-profile)
- [Elasticsearch — Tune for search speed](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/search-speed)
- [Elasticsearch — Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch — Nodes stats API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-nodes-stats)
- [Elasticsearch — Tasks API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-tasks-list)
- [Spring Data Elasticsearch Reference — Queries](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
