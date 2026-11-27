# Evaluating Relevance Using Query Sets and Expected Results

An Elasticsearch query running successfully and returning many documents does not prove that search works well. Users care about whether helpful documents appear, where they rank, and whether results align with query intent. Therefore, when building search with Spring Data Elasticsearch, you need a representative query set paired with expected results to measure ranking quality.

An evaluation process typically includes:

1. Collecting real queries or queries representative of user needs.
2. Identifying which documents are relevant to each query and their degree of relevance.
3. Running the same query set against the current search version and a candidate version.
4. Comparing result sets and ranked orders using suitable metrics.
5. Analyzing regressed queries, adjusting analyzers/queries/boosts, and re-running.

```text
Query set                  Relevance judgments
   |                              |
   | query + filters              | query ID -> document ID -> grade
   +---------------+--------------+
                   |
                   v
           Evaluation dataset
                   |
          +--------+--------+
          |                 |
          v                 v
       Search v1          Search v2
          |                 |
          v                 v
      Ranked list        Ranked list
          |                 |
          +--------+--------+
                   |
                   v
        Precision / Recall / MRR
              MAP / NDCG
                   |
                   v
       Relevance regression report
```

## 1. Why Evaluate Relevance?

A query can be syntactically valid yet perform poorly for many reasons:

- Analyzers tokenize text poorly for the language or dataset.
- Weights among `title`, `description`, and other fields are unbalanced.
- Synonyms introduce false positives.
- Filters are placed incorrectly or mandatory conditions end up in `should`.
- Overly high boosts push featured but irrelevant documents above fitting results.
- Sorting by date or price accidentally replaces relevance ordering.
- New mappings or index data diverge from old queries.

Relevance evaluation detects such regressions with repeatable data. Instead of eyeballing a handful of results, the team can see whether a new version improves or degrades quality across the entire query set.

Relevance and performance are two separate evaluation dimensions:

| Evaluation Dimension | Question | Example Metrics |
|---|---|---|
| Relevance | Are results useful and well-ordered? | Precision@k, Recall@k, MRR, MAP, NDCG@k. |
| Performance | How fast and stable are queries? | p50/p95/p99 latency, throughput, error rate, CPU, heap. |
| Correctness | Are business rules and access controls enforced properly? | Filter-matching document set, tenant isolation, expected IDs. |

A change might boost relevance while slowing down queries, or cut latency while making results less relevant. Measure each dimension independently before making decisions.

## 2. Building an Evaluation Query Set

An evaluation query set (or benchmark set) is a list of queries representative of how users search. Each query should have a stable identifier, search text, associated filters, and the context needed to reproduce the request.

Example query set for a product search system:

| Query ID | Search Text | Filters | Intent |
|---|---|---|---|
| Q001 | `mechanical keyboard` | `status=ACTIVE` | Find mechanical keyboards. |
| Q002 | `wireless mouse` | `category=ACCESSORIES` | Find wireless mice. |
| Q003 | `SKU-KB-100` | None | Exact lookup by product code. |
| Q004 | `quiet keyboard for office` | `status=ACTIVE` | Find products by usage need. |
| Q005 | `usb c hub` | `price <= 1500000` | Find USB-C hubs within budget. |
| Q006 | `bluetooth mouse` | `brand=ACME` | Find products by brand and connectivity. |

These are illustrative samples only. Real query sets should draw from search logs scrubbed for privacy, user feedback, product requirements, and queries authored by domain experts.

### 2.1. Covering Multiple Search Intents

Do not collect only the most frequent queries. A useful benchmark must cover diverse query styles:

- **Exact lookup:** product SKUs, order codes, or identifiers.
- **Full-text:** searching by title, name, description, or long content.
- **Synonym:** synonyms, abbreviations, and alternative phrasings.
- **Typo/fuzzy:** misspellings or approximate spellings.
- **Multi-field:** content spanning `title`, `description`, `category`, or `tags`.
- **Filtered search:** combining keywords with category, status, tenant, price, or time.
- **Long-tail:** less frequent queries carrying high business value.
- **No-result:** queries with no matching documents or that should return empty results.

If a benchmark contains only head queries, a change can look positive on average while breaking exact lookup, synonyms, or rare query classes. Group queries by intent so you can track quality per slice.

### 2.2. Choosing Representative Queries and Avoiding Bias

A strong query set typically combines:

1. Real user queries anonymized and stripped of unnecessary personal data.
2. Queries compiled by product/support teams from recurring user issues.
3. Challenging edge-case queries written by domain experts.
4. New queries added whenever a relevance bug is discovered.

Do not pick only queries that the current version already handles well. Include failing queries in the benchmark to prevent regressions and measure genuine progress.

Keep a core subset fixed as a regression benchmark. You can add a fresh slice periodically to reflect shifting user behavior, while recording versions and update dates so comparisons remain meaningful.

## 3. Relevance Judgments: Which Results Count as Relevant?

For each query, identify which documents are relevant. This list of assessments is commonly called relevance judgments or qrels (query relevance judgments).

Binary labels can be used:

- `0`: not relevant.
- `1`: relevant.

However, for many search systems, relevance has multiple tiers. Graded relevance scales work well:

| Grade | Example Meaning |
|---:|---|
| 0 | Not relevant or fails to meet the need. |
| 1 | Partially relevant, limited usefulness. |
| 2 | Good relevance, satisfies most of the intent. |
| 3 | Highly relevant, directly satisfies search intent. |

Example for query `mechanical keyboard`:

| Document | Content | Grade |
|---|---|---:|
| P100 | Full-size mechanical keyboard | 3 |
| P101 | Compact mechanical keyboard | 3 |
| P102 | Replacement keycaps for mechanical keyboard | 2 |
| P103 | Office membrane keyboard | 1 |
| P104 | Wireless mouse | 0 |

The grading scale must be clearly defined within the evaluation team. A grade of `2` in the product domain must carry consistent meaning across raters and benchmark versions.

### 3.1. Creating Judgments

A practical workflow can include:

1. Selecting representative queries.
2. Gathering candidate documents from multiple sources: current search results, alternative lexical queries, semantic queries, or domain-expert picks.
3. Blinding which system or ranking version produced each document wherever possible.
4. Presenting queries and candidate documents to raters with written guidelines.
5. Recording grades, rationale, and rater/team identity if the process requires it.
6. Resolving disagreements among raters on critical queries.

Do not label only the top results of a single search version. Evaluating solely what the current system already returns can miss great documents surfaced by a new version. Pool candidates from independent sources and review some items outside the current top results.

### 3.2. Unjudged Does Not Mean Irrelevant

If a document is absent from qrels, it may simply not have been judged yet rather than being irrelevant. When a benchmark is incomplete, treating every unjudged document as grade 0 can skew metrics.

Distinguish clearly between:

- **Judged irrelevant:** a rater reviewed it and assigned grade 0.
- **Unjudged:** no relevance conclusion yet.
- **Judged relevant:** assigned a grade above the relevance threshold.

When using evaluation metrics or tools, define how unjudged documents are handled. For critical benchmarks, increase judgment coverage before using scores for release gates.

## 4. Storing Query Sets and Qrels as Versioned Data

Store query sets and judgments in formats that can be reviewed, diffed, and reused in source control or a test data repository.

Example query set JSON:

```json
[
  {
    "id": "Q001",
    "text": "mechanical keyboard",
    "filters": {
      "status": "ACTIVE"
    },
    "intent": "product-category-search"
  },
  {
    "id": "Q002",
    "text": "wireless mouse",
    "filters": {
      "category": "ACCESSORIES"
    },
    "intent": "product-feature-search"
  }
]
```

Example qrels JSON:

```json
[
  {
    "queryId": "Q001",
    "documentId": "P100",
    "relevance": 3
  },
  {
    "queryId": "Q001",
    "documentId": "P101",
    "relevance": 3
  },
  {
    "queryId": "Q001",
    "documentId": "P102",
    "relevance": 2
  },
  {
    "queryId": "Q001",
    "documentId": "P104",
    "relevance": 0
  }
]
```

Each document ID must remain stable within the index snapshot used for evaluation. If reindexing changes IDs, maintain a mapping from old IDs to new IDs so qrels continue referencing the right documents.

### 4.1. Recording the Evaluation Environment

Relevance scores can only be compared fairly when data and configuration are sufficiently consistent. Each benchmark run should record:

- Version of the query set and qrels.
- Name/version of the evaluated index or alias.
- Snapshot or data checkpoint used for the benchmark.
- Mapping and analyzer version.
- Query DSL or search service version.
- Parameters such as page size, sort, filters, boosts, and similarity.
- Elasticsearch server, Spring Data Elasticsearch, and Java client versions.
- Run timestamp and cluster state if also measuring performance.

If index data mutates between two runs, metrics can shift even when the query stays identical. For benchmarks requiring high repeatability, use a fixed index snapshot or static test dataset.

## 5. Precision@k and Recall@k

Precision and Recall are two foundational metrics for evaluating result sets.

### Precision@k

Precision@k measures what fraction of the top `k` results are judged relevant:

\[
Precision@k = \frac{\text{number of relevant documents in top k}}{k}
\]

For example, if 4 out of the top 5 results are relevant:

\[
Precision@5 = \frac{4}{5} = 0.8
\]

High Precision@k matters when users mostly inspect the top few results and want minimal unhelpful noise.

### Recall@k

Recall@k measures what fraction of all known relevant documents for the query appear within the top `k`:

\[
Recall@k = \frac{\text{number of relevant documents in top k}}{\text{total judged relevant documents}}
\]

If qrels contain 10 relevant documents and the top 5 return 4 of them:

\[
Recall@5 = \frac{4}{10} = 0.4
\]

Recall matters when users need to find all relevant items—for instance, searching case files, technical docs, or records for compliance review.

### Precision and Recall Trade Off

A query returning few, highly precise results can achieve high Precision with low Recall. A query returning broad results can raise Recall while admitting irrelevant documents, lowering Precision.

Pick `k` based on the UI and user behavior. If a page displays only 10 results initially, Precision@10 and NDCG@10 are usually more meaningful than Precision across the entire index.

## 6. Mean Reciprocal Rank (MRR)

MRR evaluates the position of the first relevant result. For a single query, reciprocal rank is the reciprocal of the first relevant document's position:

\[
RR = \frac{1}{\text{rank of the first relevant result}}
\]

If the first relevant document is at rank 1, RR = 1. If at rank 4, RR = 0.25. If no relevant result appears within the evaluated cutoff, RR = 0.

MRR is the mean RR across all queries:

\[
MRR = \frac{1}{|Q|}\sum_{q \in Q} RR(q)
\]

Example where three queries find their first relevant result at ranks 1, 2, and 4:

\[
MRR = \frac{1 + 0.5 + 0.25}{3} \approx 0.583
\]

MRR fits tasks where users typically need one right answer first—such as looking up a specific document or answer. It does not fully measure the quality of results further down the list.

## 7. Average Precision and Mean Average Precision (MAP)

Average Precision (AP) combines Precision at each rank containing a relevant document. It measures how well relevant results are concentrated near the top.

For a query with `R` relevant documents:

\[
AP = \frac{1}{R}\sum_{k=1}^{n} P@k \times rel(k)
\]

Where:

- `P@k` is Precision at rank `k`.
- `rel(k)` equals 1 if the document at rank `k` is considered relevant, and 0 otherwise.
- `R` is the total number of labeled relevant documents for the query.

MAP is the mean AP across all queries:

\[
MAP = \frac{1}{|Q|}\sum_{q \in Q} AP(q)
\]

MAP fits cases with multiple relevant documents where bringing them toward top ranks matters. Standard MAP typically assumes binary relevance; if multiple tiers of relevance matter, NDCG is a better fit.

## 8. Discounted Cumulative Gain and NDCG

In many systems, relevance has multiple grades. A highly useful document should rank above a partially relevant one. NDCG (Normalized Discounted Cumulative Gain) evaluates ranking order with graded relevance.

### DCG@k

A common DCG formula:

\[
DCG@k = \sum_{i=1}^{k}\frac{2^{rel_i}-1}{\log_2(i+1)}
\]

Where `rel_i` is the relevance grade of the document at position `i`. Gain is discounted by rank because higher positions receive much more visibility.

### IDCG@k

IDCG is the ideal DCG achieved if documents were sorted from highest to lowest relevance grade. It serves as the normalization baseline.

### NDCG@k

\[
NDCG@k = \frac{DCG@k}{IDCG@k}
\]

NDCG typically lies between 0 and 1 when IDCG > 0. Values near 1 indicate the returned order closely matches the ideal order from relevance judgments.

Example qrels for a query:

| Document | Grade |
|---|---:|
| P100 | 3 |
| P101 | 2 |
| P102 | 1 |
| P103 | 0 |

If the system returns `P100, P103, P101, P102`, the ordered grades are `[3, 0, 2, 1]`. Having grade 3 first is good, yet placing grade 0 at position 2 lowers DCG compared to the ideal order `[3, 2, 1, 0]`.

NDCG suits product, document, or content search when raters can distinguish "highly relevant," "relevant," and "weakly relevant." Pick `k` according to how many results users actually inspect, such as NDCG@5 or NDCG@10.

## 9. Choosing Metrics by Product Goal

No single metric fits every search experience.

| Goal | Metrics to Consider | Reason |
|---|---|---|
| Users need one exact/right result first | MRR | Focuses on the rank of the first relevant hit. |
| First page should have minimal irrelevant noise | Precision@k | Measures fraction of good results in top-k. |
| Users need to find most/all relevant documents | Recall@k | Measures fraction of relevant documents retrieved. |
| Multiple relevance grades and order matter | NDCG@k | Uses graded relevance and penalizes good hits buried low. |
| Evaluate multiple relevant hits across the full list | MAP | Evaluates precision at every relevant rank. |
| Evaluate system speed alongside quality | Relevance metrics + latency percentiles | Quality and speed are independent dimensions. |

Examples:

- Search box looking up a document code: MRR or top-1 success can be critical.
- Internal documentation search: Recall@20 and NDCG@10 can be informative.
- E-commerce product search: NDCG@10 paired with conversion or click metrics reflects experience well.
- Compliance record search: Recall@k can be crucial because missing a relevant document carries high cost.

Choose metrics before tuning queries. Picking metrics after inspecting outcomes tempts teams to optimize toward whichever metric happened to favor their recent change.

## 10. Example Metric Calculation for One Query

Suppose qrels define two documents as relevant with a threshold grade of 2 or higher:

| Document | Grade | Relevant at threshold 2? |
|---|---:|---:|
| D1 | 3 | Yes |
| D2 | 1 | No |
| D3 | 2 | Yes |
| D4 | 0 | No |

The system returns the top 4 in order `D1, D2, D3, D4`.

- Precision@3 = 2/3 ≈ 0.667.
- Recall@3 = 2/2 = 1.0.
- Reciprocal rank = 1/1 = 1.0 because D1 is the first relevant hit.
- Average Precision = `(1/1 + 2/3) / 2` ≈ 0.833.

For NDCG, use the full grades `[3, 1, 2, 0]`. The ideal order is `[3, 2, 1, 0]`; NDCG reflects D2 (grade 1) appearing ahead of D3 (grade 2). A query can score MRR = 1 yet have NDCG below 1 because MRR cares only about the first relevant hit.

This shows why complementary metrics matter. Never declare an entire ranking good solely because MRR is high.

## 11. Elasticsearch Rank Evaluation API

Elasticsearch provides the Rank Evaluation API (`_rank_eval`) to evaluate queries against relevance judgments. The API accepts multiple search requests paired with rated documents and a target metric.

Example evaluating Precision@3:

```json
POST /products/_rank_eval
{
  "requests": [
    {
      "id": "Q001",
      "request": {
        "query": {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      },
      "ratings": [
        { "_index": "products", "_id": "P100", "rating": 3 },
        { "_index": "products", "_id": "P101", "rating": 3 },
        { "_index": "products", "_id": "P102", "rating": 2 },
        { "_index": "products", "_id": "P104", "rating": 0 }
      ]
    }
  ],
  "metric": {
    "precision": {
      "k": 3,
      "relevant_rating_threshold": 2
    }
  }
}
```

In the request:

- `id` identifies the query in the benchmark.
- `request` contains the search request under evaluation.
- `ratings` maps document IDs to relevance grades.
- `metric` specifies the evaluation formula and parameters.

The API returns an aggregate metric and per-query details. You can evaluate many queries in a single API call.

### Evaluating MRR or NDCG

Metrics can be swapped based on goals. Example MRR configuration:

```json
POST /products/_rank_eval
{
  "requests": [
    {
      "id": "Q001",
      "request": {
        "query": {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      },
      "ratings": [
        { "_index": "products", "_id": "P100", "rating": 3 },
        { "_index": "products", "_id": "P101", "rating": 3 },
        { "_index": "products", "_id": "P102", "rating": 2 },
        { "_index": "products", "_id": "P104", "rating": 0 }
      ]
    }
  ],
  "metric": {
    "mean_reciprocal_rank": {
      "k": 10,
      "relevant_rating_threshold": 2
    }
  }
}
```

NDCG example:

```json
POST /products/_rank_eval
{
  "requests": [
    {
      "id": "Q001",
      "request": {
        "query": {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      },
      "ratings": [
        { "_index": "products", "_id": "P100", "rating": 3 },
        { "_index": "products", "_id": "P101", "rating": 3 },
        { "_index": "products", "_id": "P102", "rating": 2 },
        { "_index": "products", "_id": "P104", "rating": 0 }
      ]
    }
  ],
  "metric": {
    "dcg": {
      "k": 10,
      "normalize": true
    }
  }
}
```

Verify exact metric names and options against your running Elasticsearch version. The Rank Evaluation API supports metrics such as precision, recall, mean reciprocal rank, discounted cumulative gain, and expected reciprocal rank in corresponding versions.

### Limitations of the Rank Evaluation API

- The API evaluates provided queries and judgments; it does not generate relevance labels.
- Incomplete qrels can distort metrics.
- Queries must accurately mirror production requests, including filters, sorts, and evaluated parameters.
- Fix index/data snapshots when comparing versions.
- Rank evaluation executes multiple searches; never invoke it on live user requests.

## 12. Integrating Evaluation into a Spring Data Elasticsearch Project

Spring Data Elasticsearch typically executes searches via `ElasticsearchOperations`, repositories, or the Java API Client. You can build an integration-test harness that runs the query set, collects ordered IDs, and scores them against judgments.

### Test Data Model

Example Java records:

```java
public record SearchCase(
        String id,
        String text,
        Map<String, String> filters,
        String intent
) {}

public record RelevanceJudgment(
        String queryId,
        String documentId,
        int grade
) {}
```

Query sets and qrels can be stored under `src/test/resources/search-evaluation/` as JSON/CSV files. Tests load those files to execute the benchmark.

### Running a Query via ElasticsearchOperations

Example product search service:

```java
public SearchHits<ProductDocument> search(String text, String status) {
    Query queryDsl = Query.of(q -> q
            .bool(b -> b
                    .must(m -> m.match(mm -> mm
                            .field("name")
                            .query(text)
                    ))
                    .filter(f -> f.term(t -> t
                            .field("status")
                            .value(FieldValue.of(status))
                    ))
            )
    );

    NativeQuery query = NativeQuery.builder()
            .withQuery(queryDsl)
            .withPageable(PageRequest.of(0, 20))
            .build();

    return operations.search(query, ProductDocument.class);
}
```

The harness invokes the service for each `SearchCase`, extracts ordered document IDs from `SearchHit.getId()` or entity IDs, and computes metrics test-side.

### Computing Precision@k in Tests

Example function computing Precision@k with binary relevance:

```java
static double precisionAtK(
        List<String> rankedIds,
        Set<String> relevantIds,
        int k) {

    if (k <= 0) {
        throw new IllegalArgumentException("k must be positive");
    }

    long relevantInTopK = rankedIds.stream()
            .limit(k)
            .filter(relevantIds::contains)
            .count();

    return (double) relevantInTopK / k;
}
```

Even when fewer than `k` results are returned, Precision@k still commonly divides by `k` to penalize empty slots. Some benchmarks adopt a different convention; document the convention explicitly for consistent comparisons.

### Computing Recall@k

```java
static double recallAtK(
        List<String> rankedIds,
        Set<String> relevantIds,
        int k) {

    if (relevantIds.isEmpty()) {
        return 0.0;
    }

    long relevantInTopK = rankedIds.stream()
            .limit(k)
            .filter(relevantIds::contains)
            .count();

    return (double) relevantInTopK / relevantIds.size();
}
```

In practice, distinguish queries with zero relevant documents from queries lacking judgments. Do not arbitrarily fold queries with empty qrels into averages; document whether they are excluded or scored as 0.

### Computing MRR

```java
static double reciprocalRank(
        List<String> rankedIds,
        Set<String> relevantIds) {

    for (int i = 0; i < rankedIds.size(); i++) {
        if (relevantIds.contains(rankedIds.get(i))) {
            return 1.0 / (i + 1);
        }
    }

    return 0.0;
}
```

After computing reciprocal rank per query, take the mean to obtain MRR. For graded relevance, pick a threshold defining which grades count as relevant.

### Computing NDCG with Graded Relevance

```java
static double dcgAtK(List<Integer> grades, int k) {
    double dcg = 0.0;

    for (int i = 0; i < Math.min(k, grades.size()); i++) {
        int grade = grades.get(i);
        double gain = Math.pow(2.0, grade) - 1.0;
        double discount = Math.log(i + 2.0) / Math.log(2.0);
        dcg += gain / discount;
    }

    return dcg;
}

static double ndcgAtK(
        List<Integer> rankedGrades,
        List<Integer> allJudgedGrades,
        int k) {
    double dcg = dcgAtK(rankedGrades, k);

    List<Integer> idealGrades = allJudgedGrades.stream()
            .sorted(Comparator.reverseOrder())
            .toList();

    double idcg = dcgAtK(idealGrades, k);
    return idcg == 0.0 ? 0.0 : dcg / idcg;
}
```

In a real harness, pass `rankedGrades` in returned search order and `allJudgedGrades` from **all judgments for that query**. Never compute IDCG solely from the documents returned by the search, because that ignores relevant documents the system failed to retrieve.

## 13. Example Structure of a Relevance Regression Test

A test can be structured as follows:

```java
@SpringBootTest
class ProductSearchRelevanceTest {

    @Autowired
    private ProductSearchService searchService;

    @Test
    void benchmarkQueriesShouldMeetRelevanceThresholds() {
        // 1. Load fixture data into the test index.
        // 2. Read the query set and relevance judgments.
        // 3. Run each query through searchService.
        // 4. Collect document IDs in the exact returned order.
        // 5. Compute NDCG@10, MRR, or Precision@k.
        // 6. Compare against agreed baseline thresholds.
    }
}
```

Tests should run against real Elasticsearch or Testcontainers with a compatible version. Mocking `ElasticsearchOperations` verifies how the service constructs parameters, but cannot validate analyzers, Query DSL, relevance scoring, or actual Elasticsearch ordering.

When using Testcontainers:

- Pin the Elasticsearch version for repeatable test results.
- Create indexes and mappings from fixtures or migrations.
- Index data before executing the benchmark.
- Explicitly refresh the index before searching; never rely on `Thread.sleep`.
- Delete/recreate indexes between tests when isolation is needed.
- Never include sensitive production data directly in test fixtures.

## 14. Comparing Baseline and New Query Versions

Suppose the team modifies an analyzer or adjusts boosts. Run the exact same query set and qrels on both versions:

| Metric | Baseline | Candidate | Change |
|---|---:|---:|---:|
| Precision@10 | 0.78 | 0.82 | +0.04 |
| Recall@10 | 0.61 | 0.59 | -0.02 |
| MRR | 0.74 | 0.80 | +0.06 |
| NDCG@10 | 0.76 | 0.81 | +0.05 |
| p95 latency | 85 ms | 112 ms | +27 ms |

These figures illustrate reporting format only. A candidate might improve top-rank ordering while lowering Recall@10 and increasing latency. Shipping decisions depend on product goals, Recall sensitivity, and latency budgets.

Do not inspect only overall averages across all queries. Break down comparisons by intent group:

| Query Group | Precision@10 delta | NDCG@10 delta | p95 delta |
|---|---:|---:|---:|
| Exact lookup | +0.01 | +0.00 | +5 ms |
| Full-text | +0.06 | +0.08 | +20 ms |
| Synonym | -0.04 | -0.06 | +18 ms |
| Filtered search | +0.03 | +0.02 | +10 ms |

This example shows how aggregate averages can mask a regression in the synonym slice. Inspect regressed queries specifically before concluding the candidate is better.

## 15. Per-Query Error Analysis

When metrics drop, inspect the affected queries and compare old vs. new ranked lists:

| Rank | Baseline | Grade | Candidate | Grade |
|---:|---|---:|---|---:|
| 1 | P100 | 3 | P104 | 0 |
| 2 | P101 | 3 | P100 | 3 |
| 3 | P102 | 2 | P101 | 3 |
| 4 | P104 | 0 | P102 | 2 |

The candidate still returns all relevant documents, yet an irrelevant document jumped to position 1. Top-1 NDCG and Precision drop even though overall Recall may stay unchanged.

Diagnostic steps:

1. Inspect the exact Query DSL sent.
2. Check analyzers with `_analyze` on both indexed text and query text.
3. Run the Explain API on documents ranked unexpectedly high or low.
4. Inspect mappings, synonyms, boosts, and filters.
5. Determine whether the bug lies in data, query, analyzer, or judgments.
6. Add the failing case to the regression set once expected relevance is confirmed.

Do not tune boosts solely to satisfy one individual query if doing so harms many others. Find the systemic cause and re-evaluate across the entire benchmark.

## 16. Offline vs. Online Evaluation

### Offline Evaluation

Offline evaluation runs query sets and qrels against an index snapshot without exposing changes to users. Advantages:

- Repeatable in CI or before releases.
- Compares analyzers, Query DSL, and boosts on identical data.
- Catches regressions early.
- Does not impact production user experience.

Limitations are that judgments may not cover all real intents, benchmark data can go stale, and offline metrics do not fully capture user behavior.

### Online Evaluation

Online evaluation observes real behavior or tests two versions on controlled traffic. Indicators can include:

- Click-through rate (CTR) by rank and query type.
- Zero-click query rate.
- Query reformulation or immediate re-search rate.
- Conversions or task completions where relevant to the product.
- Search task completion time.
- p95/p99 latency and error rate.

Clicks do not always equate to relevance. A document might get clicked due to a catchy title without solving the user's need; a great result might need zero clicks if a snippet already answered the question. Interpret online metrics alongside product goals and expert judgments.

### A/B Testing

When changes carry major UX impact, you can run an A/B test:

1. Split traffic randomly into baseline and candidate groups.
2. Keep user assignments consistent throughout the experiment.
3. Define primary and guardrail metrics before starting.
4. Run long enough with sufficient traffic to reduce random noise.
5. Check query/tenant/device segments to spot uneven impacts.
6. Roll out broadly only when results and guardrails satisfy agreed criteria.

Never run an A/B test where two cohorts receive mismatched data or configuration without accounting for it. In search, index distribution, caches, and personalization can also introduce bias if uncontrolled.

## 17. Common Pitfalls in Relevance Evaluation

| Pitfall | Consequence | Fix |
|---|---|---|
| Manually checking only a few queries | Fails to spot regressions in other query classes. | Build a representative query set grouped by intent. |
| No qrels or expected results | No objective basis for measuring relevance. | Label documents per query with clear guidelines. |
| Treating every unjudged document as irrelevant | Precision/Recall become skewed. | Separate unjudged from judged irrelevant and expand coverage. |
| Pooling candidates only from the current version | Misses good documents a new version could surface. | Pool candidates from multiple sources/rankers. |
| Relying on a single metric | Risks optimizing one dimension while breaking another. | Combine suitable metrics such as NDCG, MRR, Precision, and Recall. |
| Comparing across different index data | Cannot tell whether metric changes came from query or corpus. | Pin a snapshot or track data versions explicitly. |
| Looking only at overall averages | Masks regressed query slices. | Report broken down by intent, locale, tenant, and frequency. |
| Treating clicks as absolute ground truth | Clicks are biased by rank, UI, and snippet presentation. | Combine judgments, click signals, and controlled experiments. |
| Running Rank Eval API on every user request | Adds unnecessary cost and latency. | Run offline in benchmarks and test pipelines. |
| Choosing thresholds after seeing results | Tempts picking criteria that favor the candidate. | Lock metrics and thresholds before evaluating. |

## 18. Relevance Regression Workflow for Spring Data Elasticsearch

A workflow you can integrate into the development lifecycle:

1. **Establish baseline:** store query set, qrels, index snapshot, and current metrics.
2. **Modify search:** update analyzers, mappings, `CriteriaQuery`, `NativeQuery`, boosts, or sorting.
3. **Create test index:** use identical data and defined mappings/version.
4. **Run query set:** invoke the same search service or Rank Evaluation API.
5. **Compute metrics:** Precision@k, Recall@k, MRR, MAP, or NDCG@k per target goals.
6. **Compare baseline:** examine aggregate metrics and breakdowns by intent.
7. **Investigate regressions:** compare ranked lists, `_score`, Explain API, and analyzer tokens.
8. **Update qrels carefully:** add labels only after review; never treat candidate outputs as automatically expected.
9. **Save report:** record query version, index version, metrics, timestamp, and search changes.
10. **Gate CI/releases:** block releases only on agreed thresholds with an exception review process.

A release gate might require NDCG@10 not to drop beyond a set threshold, no critical query slice to suffer severe regression, and p95 latency to stay within budget. Concrete thresholds must reflect product goals and real data—there is no single universal number for all systems.

## 19. Suggested Benchmark Directory Structure

Test data can be organized as:

```text
src/test/resources/search-evaluation/
  product-search-v1/
    queries.json
    qrels.json
    README.md
  article-search-v1/
    queries.json
    qrels.json
    README.md
```

Each suite's `README.md` should document:

- Purpose and scope of the query set.
- Definitions of relevance grades.
- Data sources and anonymization method.
- Date/version of judgments.
- Primary metrics and guardrail metrics.
- Exceptions or queries requiring special interpretation.

Do not place personal information or sensitive production data into fixtures unnecessarily. When reproducing real queries, anonymize them while preserving the structure needed for evaluation.

## 20. Key Takeaways

- Relevance evaluation requires a representative query set and per-query relevance judgments.
- Relevance judgments can use binary labels or graded relevance; consistent guidelines are essential.
- Unjudged documents are not automatically irrelevant.
- Precision@k measures accuracy in top-k; Recall@k measures the proportion of relevant documents retrieved.
- MRR focuses on the first relevant hit's rank; MAP evaluates relevant positions; NDCG supports graded relevance and rank ordering.
- Pick metrics aligned with product goals rather than optimizing a single number.
- Elasticsearch's Rank Evaluation API (`_rank_eval`) can score queries against assigned ratings.
- Spring Data can run benchmarks via `ElasticsearchOperations`, repositories, or the Java API Client; mocks cannot verify real relevance scoring.
- Pin query set, qrels, index snapshot, mapping/analyzer versions, and configurations when comparing runs.
- Offline evaluation fits regression testing; online evaluation and A/B tests add real-world behavioral evidence.
- Report by intent group so averages do not hide regressions.
- Separate relevance from latency/performance and correctness; track all three dimensions.

Evaluating relevance using query sets and expected results turns search quality into something measurable, comparable, and steadily improvable across changes. When building with Spring Data Elasticsearch, maintain versioned query sets and qrels, pick metrics matching user experience, and integrate relevance regression checks into your pre-release testing workflow.
