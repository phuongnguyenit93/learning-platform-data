# Evaluating Solutions by Correctness, Relevance, and Performance

A search solution can run fast while returning wrong documents, or return relevant documents while ranking them poorly. Another solution might look great on a few demo queries yet degrade when data grows, concurrent users spike, or the system ingests updates simultaneously.

Therefore, evaluating a Spring Data Elasticsearch solution requires examining three separate axes:

- **Correctness:** queries target the right data, enforce the right conditions, return the right structure, and obey business and security rules.
- **Relevance:** results matching user intent appear and rank in strong positions.
- **Performance:** the system meets latency, throughput, data freshness, and resource cost goals under expected load.

These three axes complement each other but cannot substitute for one another. A query returning 10 filter-compliant documents does not guarantee good ranking. High NDCG does not prove tenant filters never leak data. A low p95 benchmark does not prove the system holds up when data grows tenfold.

This lesson explains how to define criteria, build evaluation datasets, test solutions with Spring Data Elasticsearch, measure ranking quality, and run repeatable performance benchmarks.

## 1. Define the Problem Before Choosing Metrics

No single metric suite fits every search feature. First describe what users want to accomplish and how the system must respond.

For example, an e-commerce catalog has use cases such as:

| Use case | Intent | Expected behavior |
|---|---|---|
| Search by name | Find products matching user-entered phrases | Relevant names appear near the top |
| Lookup by SKU | Look up an exact code | Product with that exact SKU is returned accurately |
| Category filtering | Narrow results by category | No products outside selected categories |
| Price filtering | Find products within a price range | All results satisfy range bounds |
| Semantic search | Find products matching a need description | Relevant results appear even without exact word overlap |
| Autocomplete | Complete queries as the user types | Fast, helpful suggestions |
| Admin console | Search by status, creation date, and owner | Exact filters and access enforcement |

Each use case needs representative queries and its own success criteria. For SKU lookup, exact match is practically a correctness requirement. For natural-language queries, multiple items may be relevant to varying degrees, requiring ranking evaluation.

### 1.1. Write Testable Requirements

Avoid vague requirements like "search must be good and fast." Turn them into measurable conditions:

- An exact SKU must find the single matching active product.
- Tenant filters must exclude every document belonging to other tenants.
- Product name queries must surface relevant products in the top 10.
- p95 latency must stay within the agreed threshold at target load.
- Database mutations must appear in the search index within the committed freshness window.
- As data grows, indexing throughput must meet expected ingest rates.

Specific thresholds depend on product, infrastructure, and SLAs. Never copy a latency or relevance number from another system and treat it as a universal standard.

## 2. Three Evaluation Axes and Their Relationship

| Axis | Core question | Example evidence |
|---|---|---|
| Correctness | Do results obey rules and data integrity? | Assertions, integration tests, data reconciliation |
| Relevance | Are useful results ranked highly? | Precision@k, Recall@k, MRR, NDCG |
| Performance | At what cost does the system handle load? | p95/p99 latency, throughput, resource usage |

Think of evaluation in sequence:

~~~text
                  Search solution
                        |
                        v
               Correctness checks
                 /           \
              fail           pass
               |               |
          Fix behavior         v
                         Relevance evaluation
                           /          \
                        fail          pass
                         |              |
                   Tune ranking         v
                                  Performance benchmark
                                    /           \
                                  fail          pass
                                   |              |
                              Optimize system    v
                                           Release decision
~~~

This is the practical priority order: before measuring ranking or speed, verify that queries enforce the right rules. If a category filter is missing, a fast benchmark may simply be scanning the wrong subset; if tenant filtering is broken, strong ranking means nothing.

Never collapse all three axes into one composite score without explicit priorities and hard gates. A serious correctness flaw cannot be offset by low p95 latency.

## 3. Evaluating Solution Correctness

Correctness verifies whether the system fulfills the use case contract. In Spring Data Elasticsearch, check from input data, mappings, and queries all the way to returned results.

### 3.1. Correct Schema and Mappings

Verify:

- Text fields are indexed with the intended analyzer.
- Keyword fields handle exact matches, filters, sorts, and aggregations.
- Numeric and date fields use appropriate types and formats.
- Nested fields are queried with nested queries whenever element correlation matters.
- Dense vectors match expected dimensions and similarity functions.
- Dynamic mapping does not generate unintended field types.

You can inspect actual mappings:

~~~http
GET /products-read/_mapping
~~~

Never inspect only `@Field` annotations in Java. An index may have been created before code changed, or an index template may have produced a different mapping.

### 3.2. Correct Query Conditions

A query often combines:

- Full-text clauses.
- Exact filters.
- Ranges.
- Active status.
- Tenant or access scope.
- Sorting and pagination.

For example: find laptops relevant to "lightweight laptop", active only, belonging to the current tenant, priced between 500 and 1500.

The query must enforce business conditions across every search branch, including kNN or hybrid branches. Do not inspect only query text; verify the filters emitted to Elasticsearch and confirm no out-of-scope documents appear.

### 3.3. Correct Results and Cardinality

For some use cases, expected sets are exact:

- An exact SKU returns the document with that specific ID.
- A deleted document never appears.
- Filter status=ACTIVE excludes INACTIVE documents.
- Price ranges exclude out-of-bounds prices.
- ID lookups never return another document sharing a similar name.

Test zero-result, single-result, multi-result, duplicate-data, and missing-field cases.

### 3.4. Correct Sorting and Pagination

When multiple documents share the same sort value, ordering becomes unstable without a tie-breaker. As users page through results, documents may repeat or vanish if data changes between requests.

For deep pagination, `search_after` is usually preferable to raising `from` high. When a consistent snapshot is needed across multi-page browsing, consider Point in Time (PIT) together with `search_after` per your Elasticsearch version.

Pagination correctness includes:

- No duplicate documents within a browsing session.
- No skipped documents from non-deterministic sorting.
- A stable tie-breaker, typically a unique appropriately mapped field.
- Proper PIT/search_after lifecycle when snapshot consistency is required.

### 3.5. Correct Aggregations and Total Hits

Aggregations must target suitable fields. For instance, category counts should use keyword fields or keyword subfields rather than tokens from a text field when grouping whole values.

When `track_total_hits` is capped, total hits may be a lower bound or exact only up to the threshold. If the API needs exact counts, configure the query accordingly and measure the cost. Do not evaluate correctness solely on hit lists when responses also carry totals, facets, or aggregations.

### 3.6. Correct Freshness and Consistency

Elasticsearch is near-real-time. Newly indexed documents may not appear in search until refresh completes. Distinguish:

- Get-by-ID has different read semantics from Search.
- Search depends on refresh visibility.
- Outbox/event consumers introduce their own lag.
- Bulk indexing can partially succeed.

Define a freshness SLA, such as elapsed time from database commit until searchable visibility. Measure via timestamps or event positions; never assume save immediately makes documents visible in every search query.

### 3.7. Correct Access Control and Tenant Isolation

This is part of correctness, not optional hardening. Every query must enforce server-side tenant/ACL filters. Clients must never pass parameters to widen their access scope.

Create tests with documents across multiple tenants and verify:

- Tenant A users never see Tenant B documents.
- Filters remain enforced under hybrid search.
- Aggregations never leak cross-tenant counts.
- Autocomplete and suggestions respect permissions.
- Search after, PIT, and caches never leak data across users.

### 3.8. Correct Behavior Under Dirty Data or Concurrent Mutations

Test null or missing fields, Unicode/Vietnamese diacritics/punctuation/long strings, legacy formats, duplicate or out-of-order events, version conflicts, and documents deleted mid-query or mid-pagination.

A solution that works only on clean initial seed data is not ready for production.

## 4. Building a Correctness Test Dataset

Build small, intentional fixtures. For example:

| ID | Name | Category | Price | Status | Tenant |
|---|---|---|---:|---|---|
| p-101 | Lightweight Laptop | Computers | 899 | ACTIVE | A |
| p-102 | Gaming Laptop | Computers | 1499 | ACTIVE | A |
| p-103 | Laptop Sleeve | Accessories | 29 | ACTIVE | A |
| p-104 | Lightweight Laptop | Computers | 799 | INACTIVE | A |
| p-105 | Lightweight Laptop | Computers | 999 | ACTIVE | B |

Assertions:

- Query "lightweight laptop" for tenant A and status ACTIVE must never return p-104 or p-105.
- Price filter 500 to 1500 must exclude p-103.
- Exact SKU or ID must return the matching record.
- Query "laptop" may rank p-101 and p-102 ahead of p-103 depending on relevance labels.

For correctness, define exact expected sets or clear invariants. For relevance, multiple orderings may be reasonable and scored continuously; do not hardcode a single rigid ranking unless business rules demand it.

## 5. Testing with Spring Data Elasticsearch

Unit tests work well for query construction, mappers, normalization, and business logic. Integration tests against real Elasticsearch are required to validate mappings, analyzers, Query DSL, and cluster behavior.

### 5.1. Integration Testing with Real Elasticsearch

Use Testcontainers with an Elasticsearch image compatible with your client version:

~~~java
@Testcontainers
@SpringBootTest
class ProductSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    DockerImageName.parse(
                            "docker.elastic.co/elasticsearch/elasticsearch:8.15.5"
                    )
            );

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.elasticsearch.uris",
                elasticsearch::getHttpHostAddress
        );
    }
}
~~~

This is a structural example; image, security, credentials, and properties must match your project's Spring Boot/Elasticsearch versions. Never use the `latest` tag in integration tests because behavior can drift when new images publish.

### 5.2. Testing Filter Results

Example with `ElasticsearchOperations` and `NativeQuery`:

~~~java
Query query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("name")
                        .query("lightweight laptop")
                ))
                .filter(f -> f.term(t -> t
                        .field("tenantId")
                        .value("A")
                ))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value("ACTIVE")
                ))
                .filter(f -> f.range(r -> r
                        .number(n -> n
                                .field("price")
                                .gte(500.0)
                                .lte(1500.0)
                        )
                ))
        ))
        .build();

SearchHits<ProductSearchDocument> hits =
        operations.search(query, ProductSearchDocument.class);

assertThat(hits.getSearchHits())
        .allSatisfy(hit -> {
            assertThat(hit.getContent().getTenantId()).isEqualTo("A");
            assertThat(hit.getContent().getStatus()).isEqualTo("ACTIVE");
            assertThat(hit.getContent().getPrice())
                    .isBetween(new BigDecimal("500"), new BigDecimal("1500"));
        });
~~~

This is an illustrative snippet; field types and builder APIs vary by release train, especially range queries. The goal is verifying every hit satisfies all filters. You should also assert expected IDs to catch queries that drop conditions or omit valid hits.

### 5.3. Inspecting Actual Queries

When tests fail, inspect the actual Query DSL sent to Elasticsearch. Enable appropriate client logging or use Elasticsearch's profile/explain APIs. Never rely on Java builder code merely looking right.

`_explain` reveals why a document matched and how its score was computed. The Profile API shows which parts of query execution consumed time. Both are diagnostic tools, not representative load benchmarks.

## 6. Evaluating Relevance

Relevance answers: for a given query, which results are genuinely useful, and do useful results rank near the top?

Queries often have results with graded relevance. For example, searching "quiet keyboard for office":

- A silent-switch keyboard is highly relevant.
- A regular mechanical keyboard is partially relevant.
- A wireless mouse is irrelevant.

Therefore, relevance evaluation requires an evaluation query set and judgments of relevance.

### 6.1. Building an Evaluation Query Set

Collect queries from privacy-scrubbed search logs, real user questions, domain-expert queries, and queries covering synonyms, typos, languages, and distinct intents.

Segment queries into cohorts so averages do not hide regressions:

| Cohort | Example | What to evaluate |
|---|---|---|
| Exact term | SKU, model code | Exact match |
| Natural language | "lightweight laptop for business travel" | Meaning and context |
| Synonym | "laptop" / "notebook" | Synonym handling |
| Typo | A few mistyped characters | Typo tolerance |
| Multilingual | Accented/unaccented, English/Vietnamese | Analyzers and embeddings |
| Filtered query | "laptop under 1000" | Relevance inside filtered subset |
| Ambiguous | "apple" | Context-aware intent understanding |

### 6.2. Assigning Relevance Labels

For each query-document pair, assessors assign a relevance grade. Example 0–3 scale:

| Label | Meaning |
|---:|---|
| 0 | Not relevant |
| 1 | Marginally relevant or partial overlap |
| 2 | Relevant and potentially useful |
| 3 | Highly relevant to query intent |

Provide clear guidelines and examples so assessors score consistently. For critical queries, use two independent assessors and adjudicate disagreements.

Never label only the documents returned by a single candidate solution. Otherwise, relevant documents missed by both solutions remain invisible. Pool top candidates across BM25, vector search, hybrid search, and domain-expert picks.

### 6.3. Precision@k

Precision@k measures the fraction of relevant results in the top k positions:

\[
Precision@k =
\frac{\text{relevant results in top } k}{k}
\]

For example, if 4 out of the top 5 results are labeled relevant, Precision@5 = 0.8.

This metric fits scenarios where users inspect only the top few items. Define explicitly which labels count as relevant, such as grade 2 or 3.

### 6.4. Recall@k

Recall@k measures the fraction of known relevant documents found in the top k:

\[
Recall@k =
\frac{\text{relevant documents found in top } k}
{\text{total relevant documents in evaluation set}}
\]

Recall matters when completeness is critical, such as internal document discovery or compliance record lookup. Accuracy depends on thoroughness of relevance judgments; missing labels can distort Recall.

### 6.5. Mean Reciprocal Rank (MRR)

MRR focuses on the position of the first relevant result:

\[
MRR =
\frac{1}{|Q|}
\sum_{q \in Q}
\frac{1}{rank_q}
\]

Where `rank_q` is the rank of the first relevant result. If no relevant result appears in the list, that query's reciprocal rank is 0.

MRR fits lookup tasks where users need a single right answer early, such as locating a guide page or a specific product by name/code.

### 6.6. Mean Average Precision (MAP)

Average Precision for one query averages Precision at each rank containing a relevant item. MAP averages AP across all queries.

MAP evaluates finding and ordering multiple relevant items, though it relies on binary relevant/not-relevant labels. With graded relevance, NDCG is usually preferred.

### 6.7. Normalized Discounted Cumulative Gain (NDCG)

NDCG supports multi-grade relevance and discounts items appearing lower in the list:

\[
DCG@k =
\sum_{i=1}^{k}
\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

\[
NDCG@k =
\frac{DCG@k}{IDCG@k}
\]

`rel_i` is the relevance grade at position i; `IDCG` is the DCG of the ideal ordering. NDCG@k typically ranges from 0 to 1 under standard definitions.

For instance, a grade-3 result at rank 1 contributes far more than a grade-3 result at rank 10. NDCG works well whenever degrees of usefulness vary and display order matters.

### 6.8. Picking Metrics per Use Case

| Use case | Metrics to focus on |
|---|---|
| Single-answer lookup | MRR, Precision@1 |
| Top-10 results page | NDCG@10, Precision@10 |
| Finding all relevant documents | Recall@k |
| Many relevant results | MAP, NDCG@k |
| Autocomplete | Success rate, MRR, latency |
| Semantic retrieval | Recall@k, NDCG@k, and latency |

You do not need to report every metric for every system. Pick metrics aligned with user behavior and document clearly how they are computed.

## 7. Comparing BM25, Vector Search, and Hybrid Search

Using the same query set and relevance labels, you can compare:

1. **BM25:** lexical search baseline.
2. **Vector kNN:** semantic retrieval via embeddings.
3. **Hybrid:** combining lexical and vector rankings.
4. **Hybrid + reranker:** retrieving candidates from multiple sources and reranking with another model.

Hypothetical comparison table:

| Approach | NDCG@10 | Recall@50 | p95 query |
|---|---:|---:|---:|
| BM25 | 0.68 | 0.74 | 42 ms |
| Vector kNN | 0.71 | 0.82 | 67 ms |
| Hybrid RRF | 0.78 | 0.87 | 81 ms |
| Hybrid + reranker | 0.83 | 0.88 | 145 ms |

These figures are purely illustrative to show trade-offs, not actual Elasticsearch or Spring Data benchmarks. Measure on your project's own data and infrastructure.

### 7.1. Hybrid Ranking

BM25 scores and vector scores sit on incomparable scales. Never sum raw scores without normalization or calibration. Reciprocal Rank Fusion (RRF) combines rankings by rank position instead of raw scores:

\[
RRF(d) =
\sum_{r \in R}
\frac{1}{c + rank_r(d)}
\]

A document ranking well across multiple lists earns a strong fused score. RRF often provides a solid baseline for evaluating hybrid search.

### 7.2. Reranking

A reranker takes the query and a small candidate pool and scores fine-grained relevance. It can improve top rankings while adding inference cost and latency.

Evaluating a reranker requires checking:

- Candidate recall: did retrieval bring relevant documents into the candidate pool?
- NDCG/MRR after reranking.
- Rerank duration and total end-to-end latency.
- Inference cost and concurrency capacity.

A reranker can never promote a relevant document to the top if initial retrieval failed to put it in the candidate pool.

## 8. Evaluating Performance

Performance is not just how fast Elasticsearch responds. Users experience the full request path:

~~~text
HTTP request
    |
    v
Application validation
    |
    v
Query embedding (if any)
    |
    v
Spring Data / Java Client
    |
    v
Elasticsearch coordination + shards
    |
    v
Result mapping / response assembly
    |
    v
HTTP response
~~~

Measure end-to-end latency to see what users actually wait for. Measure each stage as well to locate bottlenecks: embedding provider, application layer, network, Elasticsearch execution, result mapping, or downstream services.

### 8.1. Latency Metrics

- **p50:** half of requests finish at or below this time.
- **p95:** 95% of requests finish at or below this time.
- **p99:** 99% of requests finish at or below this time.
- **Max:** slowest request in the measurement window; easily skewed by outliers.

Average latency hides tail latency. A system with a good average but huge p99 still triggers timeouts and erratic user experiences.

### 8.2. Throughput and Concurrency

Measure QPS, documents indexed per second, concurrent request counts, error/timeout rates, queue depth/backpressure, and bulk batch processing times.

High QPS in a single-user test does not prove concurrency resilience. Step up concurrency to projected levels and record where latency or error rates breach thresholds.

### 8.3. Indexing Latency and Freshness

For systems syncing search indices from databases or events, measure time from business commit to outbox publish, consumer pickup time, embedding time (if any), document indexing time, and time until search-visible after refresh.

Freshness is part of operational performance. A 20 ms search query over 10-minute-stale data may fail inventory-management requirements.

### 8.4. Resources and Cost

Track CPU and load on data nodes, JVM heap, garbage collection, memory pressure, disk I/O, storage, segment counts, network throughput, thread pool queues and rejections, shard counts and sizes, cache hits/misses, and embedding/reranking costs if applicable.

A faster option that multiplies memory usage or inference cost may be unviable at scale.

## 9. Designing Repeatable Benchmarks

Reliable benchmarks hold comparison variables steady.

### 9.1. Preparing Data

Datasets should reflect projected production scale in document count, field length distributions, missing/null field rates, keyword cardinalities, nested object counts, tenant/category/status distributions, update/delete churn and ingest rates, and vector counts for semantic search.

Benchmarking on 10,000 documents when production holds 100 million leads to false conclusions about shards, memory, and ANN graphs.

### 9.2. Preparing the Cluster

Record Elasticsearch and JVM versions, node counts and roles, CPU/RAM/disk specs, primary shard and replica counts, mappings/analyzers/index settings, refresh intervals, cache state where controllable, and client/app infrastructure and networking.

Never compare two designs if one ran on beefier hardware or warm caches while the other ran cold.

### 9.3. Preparing Workloads

Build workloads from realistic query distributions or weighted query cohorts. Include simple and complex queries, exact matches, full-text, filters, ranges, aggregations, sorts and pagination, vector/hybrid queries if used, zero-hit queries, high-hit queries, and realistic ratios of repeated vs. fresh queries.

Repeating a single fixed query lets caches make numbers artificially optimistic.

### 9.4. Warm-Up and Measurement Windows

A benchmark procedure:

1. Create indices and ingest data.
2. Wait for index stabilization and refresh per test conditions.
3. Run warm-up so JVMs, connection pools, and caches reach steady state.
4. Execute the workload at target concurrency.
5. Capture latency distributions, throughput, error rates, and resource usage.
6. Repeat multiple runs under identical settings.
7. Compare medians and distributions rather than cherry-picking the best run.

If cold-start behavior matters, run a separate benchmark and document cache/index state explicitly. Never mix cold-start results with steady-state results.

## 10. Using Elasticsearch Rally and Appropriate Tools

Elasticsearch Rally is Elasticsearch's dedicated benchmarking tool. Rally runs tracks with defined datasets and workloads, measuring throughput, latency, and cluster metrics. It excels at comparing cluster topologies, mappings, shard layouts, or query workloads at the Elasticsearch layer.

At the application layer, run HTTP API or service-layer load tests to measure query construction, embedding calls, serialization/deserialization, client connections, response mapping, and business logic.

JMH fits micro-benchmarking pure JVM code such as mappers or data transformations. It never replaces Elasticsearch cluster benchmarks because it omits shard coordination, disk I/O, networking, and distributed query execution.

Never use a Rally number alone to declare an end-to-end API meets its SLA. The two benchmark layers answer different questions.

## 11. Analyzing Slow Queries

When a query is slow, locate the dominant phase: shard query execution, fetch phase/source loading, aggregations, network/coordination, client-side mapping, or embedding/reranking.

The Elasticsearch Profile API pinpoints slow query components. Because it adds overhead, use it strictly for diagnostics, not as primary benchmark timings.

`_explain` explains a document's match and score. It is not a throughput benchmark tool.

Points to check:

- Are wildcards or regexes overly broad?
- Are script scores running across too many documents?
- Do filters target proper keyword/numeric fields?
- Is `_source` loading bloated fields unnecessarily?
- Are aggregations operating on ultra-high cardinality?
- Does `track_total_hits` actually need exact full counts?
- Is pagination using deep `from` offsets?
- Is the query fanning out across too many shards?

## 12. Common Optimizations

Optimize only after verifying correctness and identifying bottlenecks.

### 12.1. Use Filter Context for Non-Scoring Conditions

Conditions such as tenant, status, category, or ranges rarely need to contribute relevance scores. Putting them in bool filter context expresses exact semantics and enables filter caching where eligible.

Do not move conditions into filter if they are supposed to influence ranking. `must`/`should` and `filter` serve distinct roles.

### 12.2. Pick the Right Field Types

- `text` for full-text search.
- `keyword` for exact matching, filtering, sorting, and aggregations.
- Numeric/date for ranges and sorting.
- `nested` when element correlation inside object arrays is required.

Wrong field types make queries both slower and wrong.

### 12.3. Trim Returned Data

Use source filtering or targeted DTOs to fetch only needed fields. If search cards need only ID, name, and thumbnail, never load full descriptions, metadata, and vectors.

### 12.4. Pagination

For initial or shallow pages, `from`/`size` suffices. For deep traversal, use `search_after` and PIT. Always use deterministic sorting with a tie-breaker.

### 12.5. Bulk Indexing

The Bulk API reduces overhead for multi-document indexing. Benchmark batch sizes, monitor partial failures, retry only eligible items, and avoid oversized batches that pressure memory or time out.

### 12.6. Refresh Interval

Frequent refreshes speed up search visibility at higher indexing cost. If eventual consistency allows, tune refresh intervals within your freshness SLA.

Never disable refresh just to inflate ingest benchmarks if production demands near-real-time visibility. Benchmarks must reflect real requirements.

### 12.7. Shards and Replicas

Too many shards inflate overhead; too few limit concurrency scaling and storage capacity. Replicas boost search throughput and resilience while costing storage, CPU, and network during indexing.

No single shard/replica formula suits every dataset. Size based on shard size, query concurrency, indexing rate, and node resources.

## 13. Benchmarking Vector Search and Hybrid Search

For dense vectors, performance and relevance trade off sharply:

- Raising `num_candidates` can boost recall at higher latency/CPU cost.
- Higher dimensions increase storage and similarity cost.
- HNSW parameters affect recall, memory, and indexing duration.
- Reranking improves ordering while raising end-to-end latency.
- Chunking can raise recall while multiplying vector counts and duplicate hits.

An experiment should hold dataset, queries, and hardware constant while varying one parameter at a time:

| Experiment | Changed parameter | Measured |
|---|---|---|
| A | num_candidates | Recall@10, p95, CPU |
| B | dimensions/model | NDCG@10, memory, index size |
| C | chunk size/overlap | Recall@20, duplicate rate, storage |
| D | reranker on/off | NDCG@10, end-to-end p95, cost |
| E | HNSW/index options | Recall@k, indexing time, memory |

Changing a bundle of parameters at once obscures which factor caused an improvement or regression.

## 14. Evaluating with Baselines and Controlled Experiments

Never evaluate a solution in a vacuum. Establish baselines:

- Current production search implementation.
- Simple BM25.
- Current Query DSL.
- Current mapping/index settings.
- A proposed candidate alternative.

Evaluate each variant on identical queries, relevance labels, datasets, and load conditions.

### 14.1. Offline Evaluation

Run labeled queries across variants and compute relevance and correctness metrics. Offline tests are fast and repeatable before rollout.

Limitation: labeled query sets may miss emerging user behaviors, and labels go stale as catalogs evolve.

### 14.2. Online A/B Tests

Once variants pass correctness and offline evaluation, split live traffic between baseline and candidate. Track click-through rate, search-to-detail conversion, add-to-cart or task completion, reformulation rate, zero-result rate, latency, and error rates.

Do not treat clicks as absolute relevance ground truth: rank position bias, UI layout, price, and availability all sway clicks. Interpret metrics in context.

### 14.3. Canary Rollouts

Roll out new variants to a small slice of traffic or user cohort first. Monitor correctness, latency, error rates, and behavioral signals. Ramp traffic gradually once thresholds hold.

Never allow relevance experiments to leak tenant data or bypass security filters. Mandatory correctness invariants must remain enforced across every A/B branch.

## 15. Building a Decision Scorecard

Example scorecard:

| Criterion | Baseline | Candidate | Decision threshold |
|---|---:|---:|---|
| Correctness test pass | 100% | 100% | 100% mandatory for invariants |
| NDCG@10 | 0.72 | 0.79 | Candidate must not trail baseline |
| Recall@50 | 0.81 | 0.86 | Meets use-case target |
| p95 query latency | 65 ms | 92 ms | Within SLA |
| Error rate | 0.05% | 0.04% | Does not exceed threshold |
| Index freshness p95 | 4 s | 5 s | Within freshness SLA |
| Memory per million docs | 3.2 GB | 4.1 GB | Within budget |

Numbers above are illustrative. A candidate with better relevance and slightly higher p95 may still be acceptable if it stays inside the SLA and provides clear user value. If any hard threshold fails, optimize or reject.

Never collapse criteria into one arbitrary weighted score. Correctness and security are hard gates; relevance and performance balance against product goals; cost sets operational boundaries.

## 16. Regression Analysis

When a candidate trails the baseline, inspect cohorts instead of looking only at overall averages:

- Did exact SKU lookups regress?
- How did accented vs. unaccented Vietnamese queries shift?
- Did long queries improve while short queries degraded?
- Did category or tenant filters hurt recall?
- Are newly indexed documents appearing reliably?
- Did vector search surface irrelevant items near the top?
- Did p99 spike on a specific aggregation?

Find queries with the largest regressions, inspect top hits, and examine explanations. Trace root causes to analyzers, mappings, Query DSL, embeddings, filters, ranking, caching, or cluster resources.

Never tweak boosts or similarity parameters solely to fix a handful of demo queries. Re-evaluate every ranking change across the full query set and all key cohorts.

## 17. Post-Deployment Observability

Evaluation does not end at deployment. Data, user behavior, and traffic evolve continuously.

Monitor continuously:

- Query volume by use case.
- Zero-result rate.
- Search latency p50/p95/p99.
- Error and timeout rates.
- Repeated query / reformulation rates.
- Indexing throughput and backlog.
- Projection freshness.
- Shard and node resource utilization.
- Embedding failures and vector indexing errors.
- Search conversion or task completion.

Alert on regressions exceeding thresholds. Version configuration changes to mappings, analyzers, models, and queries so metric shifts correlate cleanly with deployments.

## 18. Complete Evaluation Workflow

Apply this workflow to any proposed search change:

1. **Define the use case:** capture users, query patterns, and expected behaviors.
2. **Define correctness:** specify invariants for filters, tenants, exact lookups, pagination, aggregations, and freshness.
3. **Build datasets:** gather representative documents and real queries, scrubbing sensitive fields.
4. **Label relevance:** apply consistent guidelines and multi-grade scales where needed.
5. **Run the baseline:** archive queries, results, metrics, and cluster configuration.
6. **Run the candidate:** keep data and test conditions identical for fair comparison.
7. **Compute relevance metrics:** choose Precision/Recall/MRR/MAP/NDCG per use case.
8. **Benchmark performance:** measure p50/p95/p99, throughput, error rates, freshness, and resource usage.
9. **Analyze cohorts:** locate query or data segments showing regressions.
10. **Decide:** enforce hard gates on correctness/security, then balance relevance, latency, and cost.
11. **Canary/A-B test:** validate on live traffic with a rollback plan.
12. **Monitor:** maintain dashboards and alerts to detect post-release drift.

## 19. Solution Evaluation Checklist

**Correctness**

- [ ] Actual mappings and analyzers match design.
- [ ] Exact lookups, full-text, filters, and ranges return accurate results.
- [ ] Tenant/ACL filters apply across every query path.
- [ ] Sorting, pagination, and tie-breakers are deterministic.
- [ ] Aggregations and total hits adhere to contract.
- [ ] Deletes, updates, and freshness have clear semantics.
- [ ] Nulls, Unicode, and legacy formats are handled properly.

**Relevance**

- [ ] Query set represents real users.
- [ ] Relevance judgments and scoring guidelines exist.
- [ ] Metrics fit the use case.
- [ ] A baseline exists for comparison.
- [ ] Query cohorts and regressions have been analyzed.
- [ ] Hybrid/reranking was evaluated on the same query set if used.

**Performance**

- [ ] Datasets and clusters reflect production scale.
- [ ] Warm-up and workload/concurrency are clearly defined.
- [ ] p50, p95, p99, throughput, and error rates have been measured.
- [ ] Indexing latency and search freshness have been measured.
- [ ] CPU, heap, GC, disk, network, and shards were monitored.
- [ ] Benchmarks are repeatable with documented configurations.
- [ ] SLAs and resource budgets are met.

**Rollout**

- [ ] Scorecard and release criteria exist.
- [ ] Canary/A-B testing planned for major ranking changes.
- [ ] Post-release dashboards and alerts are ready.
- [ ] Rollback plan exists for correctness, relevance, or performance regressions.

## 20. Conclusion

Evaluating a Spring Data Elasticsearch solution requires separating correctness, relevance, and performance into distinct axes with dedicated evidence. Correctness ensures queries, mappings, filters, access control, pagination, and freshness obey the contract. Relevance measures how well useful documents are retrieved and ranked using labeled query sets and metrics such as Precision@k, Recall@k, MRR, MAP, or NDCG. Performance measures real-world experience through latency distributions, throughput, error rates, indexing freshness, and resource cost.

Establish a baseline, hold datasets and workloads constant, vary one factor at a time, and analyze regressions by query cohort. Correctness and security are mandatory hard gates; relevance, latency, and cost are balanced against SLAs and product goals. Once offline evaluations pass, canary or A/B tests confirm impact on live traffic. Only promote a solution when results are accurate, helpful to users, and operable at target scale.
