# The `_score` Value and BM25 Factors

When Elasticsearch executes a full-text search query, it not only determines which documents match but also computes a relevance score (`_score`) to rank the results. Documents with a higher score are generally considered more relevant to the query. Elasticsearch's widely used default algorithm for text ranking is BM25.

BM25 evaluates relevance based on how frequently a term appears in a document, how rare the term is across the document collection, and the content length relative to the average length. The score is also affected by query structure, analyzers, field boosts, and filter conditions. Understanding these factors helps explain why a particular document ranks at the top, why results change when keywords are added, or why the same query can produce a different order when index configuration changes.

## 1. What Is `_score`?

`_score` is the numerical score Elasticsearch calculates for a document with respect to a specific search query. In scoring queries, results are typically sorted in descending order of `_score` if the application does not specify another sort order.

For example, a user searches for `coffee maker`. Two products both contain these words, but one product is named `Automatic Coffee Maker`, while the other only mentions the phrase inside a long description. The document whose content is more focused on the query terms can receive a higher score, depending on field placement, term frequency, and field length.

Key points to remember:

- `_score` represents relative relevance to the current query.
- `_score` is not a probability that a document is correct or a percentage of accuracy.
- You should not directly compare scores from two different queries as if they were on the same scale.
- Changing analyzers, mappings, indexed data, boosts, or query structure can change the score.
- A document with a high `_score` is not necessarily the best choice from a business perspective; you may need to combine recency, popularity, inventory, or other signals.

Example search response:

```json
{
  "hits": {
    "total": {
      "value": 2,
      "relation": "eq"
    },
    "hits": [
      {
        "_id": "p-1001",
        "_score": 4.82,
        "_source": {
          "name": "Automatic Coffee Maker"
        }
      },
      {
        "_id": "p-1002",
        "_score": 1.37,
        "_source": {
          "name": "Multipurpose Grinder",
          "description": "Can be used with a coffee maker"
        }
      }
    ]
  }
}
```

The score values above are illustrative only. There is no fixed threshold such as 1, 5, or 10 to conclude whether a document is good or bad.

## 2. What Is BM25?

BM25 (Best Matching 25) is an information retrieval ranking function based on term statistics. Elasticsearch uses BM25 as the default similarity for `text` fields in modern versions.

BM25 improves relevance calculation over the classic TF-IDF model in two important ways:

1. Term frequency has diminishing returns and saturates, so repeating a word 100 times does not increase the score linearly by 100 times.
2. Document length is normalized against the average length, helping avoid overly favoring long texts just because they contain more words.

BM25 is computed from index and query statistics. A common formula for a single query term is:

\[
\operatorname{score}(q_i,d)=\operatorname{IDF}(q_i)\cdot
\frac{f(q_i,d)(k_1+1)}
{f(q_i,d)+k_1\left(1-b+b\frac{|d|}{\operatorname{avgdl}}\right)}
\]

Where:

- (q_i): a term in the query.
- (d): the document being scored.
- (f(q_i,d)): the number of times the term appears in the document's field (term frequency).
- (|d|): the length of the field/document in number of indexed tokens.
- (operatorname{avgdl}): the average length of the field across the document collection.
- (operatorname{IDF}(q_i)): the term weight based on its rarity in the document collection.
- (k_1) and (b): BM25 tuning parameters.

For queries with multiple terms, the score is typically the sum of contributions from the matching terms, which may then be influenced by boosts or other compound queries.

## 3. Term Frequency (TF)

Term frequency indicates how many times a term appears in a document's field. If a user searches for `espresso`, a document mentioning `espresso` multiple times can receive a larger score contribution than a document mentioning it only once.

However, BM25 uses term-frequency saturation. As the occurrence count increases, the additional score gain gets smaller. This prevents a document stuffed with repeated keywords from always dominating.

Intuitive example:

| Occurrences of `espresso` | TF Contribution Trend |
|---:|---|
| 0 | No contribution from this term |
| 1 | Clear contribution |
| 2 | Contribution increases |
| 5 | Still increases, but the increment is smaller |
| 20 | Continues increasing, but closer to saturation |

This is a qualitative trend, not an actual BM25 score table. The score also depends on IDF, field length, (k_1), (b), and other factors.

### When Is TF Useful?

TF helps distinguish a document whose content focuses on the query topic from a document that mentions the term only once. However, you should not intentionally repeat keywords in content to manipulate rankings. BM25 saturates, and keyword stuffing degrades reading experience without guaranteeing better relevance.

## 4. Inverse Document Frequency (IDF): Term Rarity

IDF evaluates how common or rare a term is across the document collection. A word that appears in almost every document usually has little ability to distinguish results. A rarer word can provide a stronger signal about the topic.

Example in a catalog:

- `product` might appear in very many documents.
- `espresso` appears in a smaller subset of products.
- `portafilter` might appear in very few documents.

When a user searches for `portafilter`, this term can have a higher IDF than `product`, because it is rarer in the index.

A common IDF formula used in BM25 is:

\[
\operatorname{IDF}(q_i)=
\ln\left(1+\frac{N-df(q_i)+0.5}{df(q_i)+0.5}\right)
\]

Where:

- (N): the number of documents in the statistical set.
- (df(q_i)): the number of documents containing the term (q_i).

IDF is calculated from index statistics and can be affected by shard-level statistics in distributed search. Therefore, a term that is rare in one shard but common in another shard may contribute differently depending on how statistics are collected.

### IDF Is Not Frequency Within a Single Document

TF answers "how many times does this word appear in the document under consideration?" IDF answers "how common is this word across the entire document collection?" The two components complement each other.

## 5. Document Length Normalization

If one document is several times longer than another, it has more opportunities to contain keywords. BM25 normalizes by length to reduce bias toward long texts.

In the formula, the ratio:

\[
\frac{|d|}{\operatorname{avgdl}}
\]

compares the document's field length against the average length. If the field is longer than average, the denominator in the TF component is typically larger and the TF contribution is relatively reduced. If the field is shorter than average, the document can benefit more when containing the same number of term occurrences.

Example:

- Document A has a 40-token description and contains `espresso` 2 times.
- Document B has a 1,000-token description and also contains `espresso` 2 times.
- All else being similar, field length can cause Document A to receive a higher TF contribution.

Length is measured in tokens after analysis, not simply characters or visible words in the raw string. Changing the analyzer can change token counts and length statistics.

### Length Is Computed Per Field

In multi-field search, each field has its own statistics and length. `name` is usually much shorter than `description`; merging all fields indiscriminately can cause scores to misrepresent content importance. Use field boosts or appropriate queries to express which fields matter more.

## 6. The `k1` and `b` Parameters

BM25 has two important parameters that are commonly configured:

| Parameter | Common Default | Role |
|---|---:|---|
| `k1` | `1.2` | Controls term frequency saturation |
| `b` | `0.75` | Controls field length normalization |

### `k1`: TF Saturation Level

`k1` controls how quickly the TF contribution approaches saturation.

- Lower `k1` causes diminishing returns from repeated occurrences to saturate earlier.
- Higher `k1` allows term frequency to keep influencing the score for longer before saturating.

Do not increase `k1` just because you want documents with more keyword occurrences to rank higher. Evaluate using a query set and real relevance labels.

### `b`: Effect of Length

`b` adjusts the degree of length normalization:

- `b = 0`: no field length normalization.
- `b = 1`: full length normalization according to the BM25 formula.
- Values between 0 and 1 produce an intermediate effect.

Reducing `b` can be appropriate when text length does not reflect relevance or when fields have special length structures. Increasing `b` makes length matter more strongly. The right value depends on your data and ranking goals.

### Do Not Tune Parameters by Intuition

The defaults are a good starting point for most cases. If you need to change them, prepare a representative query set, evaluate result relevance, and compare configurations on the same data. Changing `k1` or `b` can alter rankings for many queries, not just a single example.

## 7. How Do Analyzers Affect BM25?

BM25 scores on tokens produced by the analyzer, not directly on the raw character string. An analyzer typically consists of character filters, a tokenizer, and token filters.

For example, an analyzer can:

- Convert uppercase letters to lowercase.
- Split sentences into tokens.
- Remove stop words.
- Normalize accents or Unicode characters.
- Split synonyms or emit synonym tokens.
- Perform stemming or reduce words to root forms in supported languages.

These transformations directly affect TF, document frequency, and field length, and therefore affect the score.

### Lowercase Example

If an analyzer converts `Coffee`, `COFFEE`, and `coffee` into the same token `coffee`, different capitalizations can match the same term.

### Stop Words Example

If an analyzer removes `the`, that word no longer participates in scoring as a normal token. This can reduce noise, but an inappropriate stop word list can strip important domain terms.

### Vietnamese Example

For Vietnamese, the analyzer determines how diacritics, the letter `đ`, Unicode, and word segmentation are handled. If text is tokenized into separate syllables, queries and documents are scored on those tokens. If a dictionary-based segmenter or synonyms are used, TF/DF statistics and lengths also change. Therefore, changing the analyzer can significantly alter rankings and usually requires reindexing the data.

You can inspect actual tokens with `_analyze`:

```http
POST /products/_analyze
Content-Type: application/json

{
  "analyzer": "standard",
  "text": "Espresso coffee maker"
}
```

Use the field's actual analyzer rather than only testing `standard` if your mapping uses a custom analyzer.

## 8. Query Structure Affects `_score`

Not every condition in Elasticsearch contributes to the score. In a `bool` query, where you place a condition determines whether it is used for filtering or for calculating relevance.

| Bool Clause | Primary Behavior | Score Impact |
|---|---|---|
| `must` | Document must match | Child query contributes to score |
| `should` | Optional condition or minimum-match condition depending on context | Child query can increase score |
| `filter` | Document must satisfy condition | Does not contribute to score |
| `must_not` | Document must not match | Does not contribute to score |

Example:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "description": "espresso machine"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        },
        {
          "term": {
            "available": true
          }
        }
      ]
    }
  }
}
```

Here, `match` on `description` determines the relevance score. `status` and `available` only restrict the result set without increasing or decreasing the score.

### `should` and `minimum_should_match`

`should` is often used to boost scores for additional signals. For example, documents whose name matches the query are preferred, while documents matching only the description can still appear if the query allows it.

```json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "description": "espresso machine" } }
      ],
      "should": [
        { "match": { "name": "espresso machine" } }
      ],
      "minimum_should_match": 0
    }
  }
}
```

In this example, `description` is mandatory; also matching `name` can rank the document higher. When a `bool` query already has `must` or `filter`, `should` clauses are optional by default. If you want at least one `should` clause to match, set `minimum_should_match` accordingly.

If a `bool` query has only `should` and no `must`/`filter`, the default typically requires at least one branch to match. Declare `minimum_should_match` explicitly when business logic depends on it.

## 9. Field Boosts and Query Boosts

Boosts let you increase or decrease the influence of a child query on the score. For example, matching a product name is usually more important than matching a long description.

```json
{
  "query": {
    "multi_match": {
      "query": "espresso machine",
      "fields": [
        "name^4",
        "brand^2",
        "description"
      ]
    }
  }
}
```

In the example, `name` is boosted 4x, `brand` 2x, and `description` uses the default level. This is an influence factor during score computation, not a guarantee that the final score increases by exactly four times after all combinations.

You can apply a boost on a specific query:

```json
{
  "match": {
    "name": {
      "query": "espresso",
      "boost": 3
    }
  }
}
```

Boosting is a way to tune relevance according to content structure. Start with a few important fields, evaluate the results, and refine based on data rather than assigning large boosts to every field.

## 10. Combining BM25 with Business Signals

In product search, text relevance alone may not capture the entire goal. Users may want content-matching products while also favoring in-stock items, popular products, or recently updated ones.

You can combine BM25 with other signals:

- Popularity or sales count.
- Document recency.
- Rating or quality score.
- Geographic distance.
- Inventory status.
- A normalized business score.

`function_score` lets you adjust the base query score using functions such as field value factor, decay functions, or script score. For example, a BM25 query searches content, then adds a popularity signal:

```json
{
  "query": {
    "function_score": {
      "query": {
        "match": {
          "name": "espresso machine"
        }
      },
      "field_value_factor": {
        "field": "popularity",
        "modifier": "log1p",
        "factor": 1.0,
        "missing": 0
      },
      "boost_mode": "sum",
      "score_mode": "sum"
    }
  }
}
```

This example illustrates how to combine them. Choose `boost_mode`, `score_mode`, modifier, and factor based on the actual data distribution. If popularity has a very large range compared to BM25, it can overwhelm text relevance. Normalize or cap business signals to avoid unexpected dominance in the results.

### Business Filter or Business Scoring?

If out-of-stock products must never be shown, use `filter` to exclude them from results. If in-stock products should only be preferred over out-of-stock ones while still allowing out-of-stock items to appear, you can use a scoring signal or function score. Clearly distinguish mandatory requirements from preference factors.

## 11. BM25 and Field Sorting

If a query has scoring and specifies no sort, Elasticsearch normally sorts by `_score` descending. However, if the application specifies a field sort, the result order will be based on that field.

Example:

```json
{
  "query": {
    "match": {
      "name": "espresso"
    }
  },
  "sort": [
    { "priceMinorUnits": "asc" }
  ]
}
```

Results are sorted by ascending price, not by score. If you still need the score for display or downstream use, you can request score tracking when sorting by fields using the `track_scores` option in the appropriate APIs.

When you need relevance first and a field as a secondary tie-breaker, sort by `_score` first and the field second:

```json
{
  "sort": [
    { "_score": "desc" },
    { "createdAt": "desc" }
  ]
}
```

This keeps relevance as the primary order and uses `createdAt` to break ties or order further.

## 12. Reading `_score` in Spring Data Elasticsearch

When using `ElasticsearchOperations.search(...)`, the returned result is `SearchHits<T>`. Each `SearchHit<T>` contains the document content along with metadata such as ID, score, and highlights.

Example:

```java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public List<ProductResult> searchProducts(
        ElasticsearchOperations operations,
        String text) {

    Query query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(text)
        ))
        .build();

    SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

    return hits.getSearchHits().stream()
        .map(hit -> new ProductResult(
            hit.getId(),
            hit.getScore(),
            hit.getContent()
        ))
        .toList();
}
```

A DTO can hold the score:

```java
public record ProductResult(
        String id,
        float score,
        ProductDocument product) {
}
```

If you use a repository returning `List<ProductDocument>`, the application typically receives only the entity content without full per-hit metadata. When you need `_score`, highlights, or sort values, use `SearchHits`/`SearchHit` via `ElasticsearchOperations` or the appropriate result API.

## 13. Explaining Why a Document Received Its Score with `_explain`

When a document has an unexpected score, Elasticsearch provides the Explain API to break down the components that contributed to the score.

```http
GET /products/_explain/p-1001
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "espresso machine"
    }
  }
}
```

The response typically contains:

- `matched`: whether the document matched the query.
- `value`: the calculated score value.
- `description`: explanation of the calculation.
- `details`: sub-components such as IDF, TF, and normalization.

Explain is useful for understanding why a document received a high or low score. It is more expensive than a normal query, so use it to diagnose specific documents in development or controlled investigations—do not enable it for every production request.

### `explain` in a Search Request

You can ask Elasticsearch to return explain information for the hits of a search request using the `explain` option. This is helpful when comparing a group of results, though the response is larger and computation cost is higher.

## 14. Using the Profile API to Inspect Query Cost

Explain answers "why did the document get this score?" The Profile API answers "how much relative time did Elasticsearch spend executing the parts of the query?"

Example:

```http
GET /products/_search
Content-Type: application/json

{
  "profile": true,
  "query": {
    "match": {
      "name": "espresso machine"
    }
  }
}
```

Profile can reveal time spent in the query tree, collector, and across shards. This is a diagnostic tool and should not be enabled routinely on every request because profiling adds overhead. Use Explain when analyzing document scores; use Profile when analyzing query execution cost.

## 15. BM25 in Index Settings and Mappings

Elasticsearch uses BM25 by default for text fields. Typically, there is no need to redeclare similarity unless you have special requirements.

If you need a custom similarity configuration, you can declare it in index settings and attach it to a field:

```json
PUT /products-v2
{
  "settings": {
    "similarity": {
      "custom_bm25": {
        "type": "BM25",
        "k1": 1.5,
        "b": 0.65
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "similarity": "custom_bm25"
      },
      "description": {
        "type": "text"
      }
    }
  }
}
```

In the example, the `name` field uses the custom BM25, while `description` uses the default similarity. The `k1` and `b` values are examples to illustrate configuration, not optimal settings for every dataset.

Similarity is declared in index settings and attached to the field mapping. If you want to change the similarity of an already indexed field, review mapping limitations and create a new index/reindex for consistent results. You cannot assume that editing a Java annotation will update the similarity on an existing index.

### Declaring via Spring Data

Spring Data can load index settings from a file using `@Setting`:

```java
@Document(indexName = "products-v2")
@Setting(settingPath = "/elasticsearch/products-settings.json")
public class ProductDocument {
    // fields
}
```

The settings file contains the `similarity` section as shown in the JSON example above. The field mapping must reference the exact name `custom_bm25`. Ensure the index is created with the settings before indexing data.

## 16. Shard-Level Statistics and Score Differences

In a multi-shard cluster, each shard may have a different document distribution and term frequency. With standard search, relevance statistics can be gathered locally per shard; the same term may appear common on one shard yet rare on another.

Elasticsearch supports the `dfs_query_then_fetch` search type to gather distributed statistics before scoring, making scores more consistent across shards in some cases. In return, the request requires an extra round trip and is more expensive.

Do not assume every score difference across shards is a bug. Examine data distribution, routing, shard count, and ranking goals. If results require more accurate global statistics, test `dfs_query_then_fetch` on a representative workload and measure performance before rolling it out broadly.

## 17. Evaluating Ranking Quality

Do not tune BM25 based on a single sample query. You need a query set representative of user behavior and evaluate whether results are relevant.

A workflow can include:

1. Collecting real queries that have been anonymized and stripped of sensitive data.
2. Selecting a representative query set across intent groups.
3. Assigning relevance labels to candidate documents on an appropriate scale.
4. Recording a baseline with default analyzer, mapping, and BM25.
5. Testing changes to field boosts, analyzers, or `k1`/`b` incrementally.
6. Comparing rankings with metrics such as Precision@K, Recall@K, MRR, or NDCG.
7. Checking latency, resource usage, and query groups that regressed.
8. Rolling out in a controlled manner and monitoring post-change behavior.

Change only one group of factors at a time so you know what caused an improvement or regression. If you change analyzer, boost, similarity, and data all at once, it is very hard to tell which factor made the difference.

## 18. Common Mistakes When Analyzing `_score`

### Treating `_score` as a Percentage Probability

Scores are not on a 0–100 scale and are not probabilities. Do not display `4.8` as "4.8% accuracy" or compare scores across two different queries.

### Assuming Documents Mentioning a Word Most Often Always Rank First

BM25 has term-frequency saturation and length normalization. IDF, field length, analyzer, and boost also affect the score.

### Putting Mandatory Conditions in `should` Without `minimum_should_match`

When a `bool` query already has `must` or `filter`, `should` can be optional. If a condition must match, set `minimum_should_match` or use `must`/`filter`.

### Putting Every Condition in `must`

Status, inventory, or category conditions usually only need filtering. Putting them in `filter` avoids unnecessary scoring and can leverage filter caching where appropriate.

### Using a `text` Field for Exact Filters

`text` fields are tokenized by an analyzer. Use `keyword` or a keyword subfield for exact conditions and aggregations.

### Changing the Analyzer Without Reindexing

A new analyzer does not automatically re-analyze tokens already stored in the inverted index. You must create a new index and reindex data if the change affects indexing.

### Tuning `k1` and `b` Without an Evaluation Set

Changing parameters can alter results for many queries. Use a query set and relevance labels to evaluate, rather than relying on intuition from a single example.

### Sorting by a Field and Wondering Why Score Does Not Control Order

When sorting by a field, order is no longer driven purely by `_score`. Check your sort configuration and `track_scores` if you still need scores.

## 19. Workflow for Investigating an Unexpected Ranking Result

When a document ranks too high or too low, check in sequence:

1. Confirm the actual query and bound parameter values.
2. Check which `must`, `should`, and `filter` branches the document matches.
3. Check the field mapping and analyzer of the queried fields.
4. Use `_analyze` to inspect tokens of both query and document.
5. Use `_explain` on a specific document to inspect TF, IDF, length normalization, and boosts.
6. Check field boosts, query boosts, and `minimum_should_match`.
7. Verify whether `function_score`, `rescore`, or field sorting is altering the order.
8. In a multi-shard cluster, assess shard-level statistics and test a DFS query where appropriate.
9. Use the Profile API if you need to identify execution cost.
10. Test adjustments on an evaluation query set before deploying changes to production.

## 20. Conclusion

`_score` is the relevance score Elasticsearch uses to rank documents for a query. BM25 is the common default similarity for text search and computes scores from term frequency, term rarity, field length, and the two parameters `k1` and `b`. Analyzers determine which tokens are indexed, while `bool` query structure and field boosts determine which conditions contribute to the score.

In Spring Data Elasticsearch, you can retrieve the score via `SearchHit.getScore()` when using `ElasticsearchOperations.search(...)`. Use `filter` for business conditions that do not need scoring, `must` for mandatory content with scoring, and `should` to add preference signals with an explicit `minimum_should_match`. Use `_explain` when you need to explain a result, and use the Profile API when you need to inspect execution cost. Only tune BM25 or boosts after evaluating against a representative query set, because score is a relative ranking signal rather than a probability of correctness.
