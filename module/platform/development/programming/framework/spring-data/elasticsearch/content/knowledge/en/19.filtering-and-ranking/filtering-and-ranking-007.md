# Freshness, Popularity, and Distance in Ranking Formulas

In a search system, documents satisfying query conditions are not necessarily ordered in the most useful way for users. Beyond content relevance, an application may need to prioritize newer documents, popular products, or locations close to the searcher.

Elasticsearch provides scoring mechanisms such as `function_score`, decay functions, and `rank_feature` to combine these signals with the query's relevance score. Spring Data Elasticsearch lets you send such queries via `@Query` or build queries with the Elasticsearch Java Client through `NativeQuery`.

Three commonly used signals:

- **Freshness:** newer documents are generally preferred over older ones.
- **Popularity:** content with more views, interactions, or transactions can rank higher.
- **Distance:** locations near the search point are typically preferred over distant ones.

Do not use these signals as substitutes for content relevance or business eligibility rules. First determine which documents are allowed to appear; then compute scores to order eligible results.

## 1. Separating Filter Conditions from Ranking Signals

A location search page might require:

- Location name must relate to the keywords.
- Location must be active.
- Location must lie within the maximum service radius.
- Recently updated locations are preferred.
- Locations with many good reviews are preferred.
- Locations closer to the searcher are preferred.

Conditions like active status and maximum radius decide whether a location is eligible to appear. Freshness, popularity, and distance within the radius are typically ranking signals.

The flow can be illustrated as:

~~~text
Search request
       |
       v
Mandatory query + filters
       |
       v
Eligible document set
       |
       v
Compute ranking signals
  - content relevance
  - freshness
  - popularity
  - proximity
       |
       v
Combine scores and sort
       |
       v
Returned results
~~~

For example, if you only want open restaurants within a 10 km radius, place active status and max distance inside `filter`. Within that result set, use distance decay to favor closer spots. If you only use decay without a distance cap, a very distant location can still appear with a low score.

## 2. Baseline Relevance Score

Full-text queries like `match` or `multi_match` normally produce `_score`, reflecting how well document content matches the query. This score serves as the baseline for ranking:

~~~json
{
  "query": {
    "multi_match": {
      "query": "roasted ground coffee",
      "fields": ["name^3", "description"]
    }
  }
}
~~~

In this example, location name carries higher weight than description. Elasticsearch computes the score from the query and indexed data. Score is not a probability and has no fixed scale to interpret as a match percentage.

If you sort by relevance alone, an old document matching many keywords can outrank a newer or more popular document. When business needs call for other signals, combine them with the baseline score in a controlled manner.

## 3. function_score Combining Multiple Signals

`function_score` lets you apply one or more scoring functions to documents matching the query. Available functions include:

- Numeric field values via `field_value_factor`.
- Temporal or geographic closeness via decay functions.
- A fixed weight (`weight`).
- `script_score` when a formula needs custom logic.
- Other scoring functions such as `random_score` where appropriate.

General structure:

~~~json
{
  "query": {
    "function_score": {
      "query": {
        "bool": {
          "must": [
            {
              "match": {
                "title": "search engine"
              }
            }
          ],
          "filter": [
            {
              "term": {
                "status": "published"
              }
            }
          ]
        }
      },
      "functions": [
        {
          "weight": 2
        },
        {
          "field_value_factor": {
            "field": "viewCount",
            "modifier": "log1p",
            "factor": 0.2,
            "missing": 0
          }
        },
        {
          "gauss": {
            "publishedAt": {
              "origin": "now",
              "scale": "14d",
              "offset": "1d",
              "decay": 0.5
            }
          }
        }
      ],
      "score_mode": "sum",
      "boost_mode": "sum",
      "max_boost": 10
    }
  }
}
~~~

This structure is illustrative: the inner query selects eligible documents and the functions supply ranking signals. In practice, calibrate weights, scales, and limits using your system's data.

## 4. Two Ways to Combine Scores: score_mode and boost_mode

These two properties answer different questions.

### 4.1. score_mode: Combining Multiple Functions Together

`score_mode` defines how results from functions in the `functions` array are combined.

| Value | Meaning |
|---|---|
| multiply | Multiplies scores from functions |
| sum | Sums scores from functions |
| avg | Weighted average |
| first | Uses the first matching function |
| max | Takes the highest function score |
| min | Takes the lowest function score |

For instance, if you have a freshness function and a popularity function:

- `sum` adds the contributions of both signals.
- `multiply` combines them multiplicatively; a small signal can pull the total down sharply.
- `max` keeps only the function yielding the highest score.

With multiple independent signals, `sum` is often easier to interpret once weights are calibrated. `multiply` can work when signals should all be strong simultaneously, though it must be tested carefully with zero or very small values.

### 4.2. boost_mode: Combining Function Score with Query Score

`boost_mode` defines how the combined function score combines with the base query's `_score`.

| Value | Meaning |
|---|---|
| multiply | Multiplies query score by function score |
| sum | Adds query score and function score |
| avg | Average of the two scores |
| max | Takes the larger score |
| min | Takes the smaller score |
| replace | Uses function score instead of query score |

For example, with `boost_mode: sum`, query relevance still contributes to the final score while freshness, popularity, and proximity add extra points.

If the base query contains only filters, the query score may be 0. In that case, `boost_mode: multiply` can yield a final score of 0 even when functions produce values. If the goal is to rank purely by functions, consider `replace`; if you want to keep relevance, ensure the base query generates scores or choose a suitable combination mode.

### 4.3. Capping Scores with max_boost

`max_boost` caps the maximum score that functions can contribute before combining with the query score via `boost_mode`. It helps prevent a single signal from inflating too much and overpowering relevance.

Do not choose `max_boost` by guesswork. Observe the actual score distribution, run representative queries, and check whether results are dominated by a single signal.

## 5. Freshness with Time-Based Decay Functions

Freshness is typically represented by a timestamp field such as `publishedAt`, `createdAt`, or `updatedAt`. Recent documents can earn high scores, while older documents receive progressively lower freshness scores.

Elasticsearch provides three primary decay functions:

- `gauss`: decays along a Gaussian curve.
- `exp`: decays exponentially.
- `linear`: decays linearly.

All three work on appropriate `date`, `numeric`, or `geo_point` fields. For time, parameters typically include:

- `origin`: reference timestamp, e.g., `now`.
- `scale`: characteristic decay time span.
- `offset`: region around `origin` before decay begins.
- `decay`: target score at distance `scale` from `origin` (after `offset`).

### 5.1. Freshness Example with gauss

~~~json
{
  "gauss": {
    "publishedAt": {
      "origin": "now",
      "scale": "14d",
      "offset": "1d",
      "decay": 0.5
    }
  }
}
~~~

Meaning:

- The reference point is the current time.
- Within the most recent one day, the freshness score does not decay due to `offset`.
- Beyond the offset zone, the score drops gradually along a Gaussian curve.
- At distance `scale` from `origin`, the decay score reaches 0.5 per the function definition.

If newly published articles should be favored over roughly two weeks, you might start experimenting with `scale: 14d`. This value is only an experiment starting point; minute-by-minute news feeds may need a shorter scale, while evergreen documentation may need a longer one.

### 5.2. Comparing gauss, exp, and linear

| Function | Characteristics | When to Consider |
|---|---|---|
| gauss | Curved decay, relatively gentle around origin | Freshness or distance when strongly favoring the near zone |
| exp | Exponential decay | When score should drop proportionally with distance |
| linear | Linear drop toward decay level at scale | When simple, easy-to-explain behavior is wanted |

Example switching to `exp`:

~~~json
{
  "exp": {
    "publishedAt": {
      "origin": "now",
      "scale": "30d",
      "offset": "2d",
      "decay": 0.5
    }
  }
}
~~~

Example using `linear`:

~~~json
{
  "linear": {
    "publishedAt": {
      "origin": "now",
      "scale": "30d",
      "offset": "2d",
      "decay": 0.5
    }
  }
}
~~~

No single function is universally best. Pick according to the desired ranking behavior and evaluate on a real query set and documents.

### 5.3. Freshness Is Not an Expiration Filter

Decay only lowers scores with age. It does not automatically remove old documents from results. If business logic prohibits showing articles older than one year, add a `range` filter:

~~~json
{
  "range": {
    "publishedAt": {
      "gte": "now-365d"
    }
  }
}
~~~

Combining a `range` filter with decay clarifies the separation:

- Filter sets a hard boundary: overly old documents cannot appear.
- Decay sets a soft preference: within valid documents, newer ones rank higher.

### 5.4. Time Data Must Be Normalized

Timestamp fields should use an appropriate `date` or `date_nanos` mapping and follow a consistent convention, typically absolute UTC instants. In Java, `Instant` clearly represents a point on the timeline.

If source data uses local time, convert it to an offset timestamp or `Instant` before storing. Avoid timezone-less date-time strings unless producer and consumer agree on interpretation.

## 6. Popularity with field_value_factor

Popularity usually relies on a numeric field such as:

- `viewCount`: view count.
- `clickCount`: click count.
- `purchaseCount`: transaction count.
- `favoriteCount`: favorite count.
- `ratingCount` or an aggregated review metric.

`field_value_factor` reads the field value, multiplies it by `factor`, and applies `modifier` if declared. The result becomes the function score.

Example:

~~~json
{
  "field_value_factor": {
    "field": "viewCount",
    "factor": 0.2,
    "modifier": "log1p",
    "missing": 0
  }
}
~~~

Where:

- `field`: numeric field used as signal.
- `factor`: multiplier applied to the field value before the modifier.
- `modifier`: value transformation such as `log1p`, `sqrt`, `log`, `ln`, `square`, or `reciprocal`.
- `missing`: fallback value when a document lacks the field.

### 6.1. Why Is log1p Commonly Used?

Popularity values can vary wildly. An article with 10 views versus one with 100,000 views should not necessarily create a linear 10,000x score gap.

`log1p` computes log(1 + x), compressing the value range:

| Views x | log(1 + x), approx. |
|---:|---:|
| 0 | 0 |
| 9 | 2.30 |
| 99 | 4.61 |
| 999 | 6.91 |
| 9,999 | 9.21 |

Large values still hold an advantage, but the gain grows progressively slower. This is a standard way to keep popularity from completely overriding content relevance.

### 6.2. Choosing factor and modifier

`factor` scales popularity's contribution. `modifier` shapes the growth curve.

| Modifier | Behavior |
|---|---|
| none | Keeps linear value |
| log1p | Compresses large values, handles 0 better than plain log |
| sqrt | Compresses more gently than log across many ranges |
| square | Accelerates growth of large values |
| reciprocal | Larger values produce smaller scores |

For non-negative views or interactions, `log1p` is usually a sensible starting point. Check the data domain: log modifiers require valid inputs; negative or abnormal values can break the query or produce unintended scores.

### 6.3. Missing Values and Popularity Data

If the field is missing, `missing` supplies a fallback value. For example, `missing: 0` gives documents with no recorded views a popularity of 0.

The field should have an appropriate numeric mapping. Guard against nulls, negative numbers, duplicate events, or bot views. If a document's view count updates constantly, writing counter increments directly to Elasticsearch can cause heavy write load; many systems aggregate signals in an ingestion pipeline or analytics store and sync periodically.

### 6.4. Popularity Can Use rank_feature

If a field is used primarily for ranking and holds positive values, a `rank_feature` mapping paired with a `rank_feature` query can be a specialized option:

~~~json
{
  "mappings": {
    "properties": {
      "popularity": {
        "type": "rank_feature"
      }
    }
  }
}
~~~

Query:

~~~json
{
  "rank_feature": {
    "field": "popularity",
    "saturation": {
      "pivot": 100
    }
  }
}
~~~

The `saturation` function makes scores rise quickly at low values and gradually saturate as popularity increases. `pivot` tunes where the saturation curve inflects. `rank_feature` is optimized for feature-based ranking signals; pick it when its storage and query model fit your requirements. If you also need filtering, sorting, aggregations, or general arithmetic on the field, a standard numeric type is more flexible.

## 7. Geographic Distance with Geo Decay

For location search, distance from an origin point is a natural ranking signal. Elasticsearch supports `geo_point` fields and decay functions over them.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

Document:

~~~json
{
  "name": "Central Coffee",
  "location": {
    "lat": 10.78,
    "lon": 106.69
  }
}
~~~

### 7.1. Scoring by Distance

Gaussian decay example:

~~~json
{
  "gauss": {
    "location": {
      "origin": {
        "lat": 10.78,
        "lon": 106.69
      },
      "scale": "5km",
      "offset": "500m",
      "decay": 0.5
    }
  }
}
~~~

Meaning:

- `origin` is the reference coordinate.
- `offset` creates a zone around `origin` with no decay.
- `scale` sets the characteristic decay distance.
- `decay` is the score at distance `scale` beyond `offset`.

Here, places within 500 m keep full proximity score; farther out, the score drops smoothly and hits 0.5 at distance `scale` per the decay definition.

For string coordinates, Elasticsearch normally expects `lat,lon` order; for objects, use explicit `lat` and `lon` properties. Watch coordinate order carefully because swapping latitude and longitude puts the origin in an entirely different place.

### 7.2. Limiting Radius with geo_distance Filter

Geo decay only lowers scores. If you need to exclude places outside a service radius, add a `geo_distance` filter:

~~~json
{
  "geo_distance": {
    "distance": "10km",
    "location": {
      "lat": 10.78,
      "lon": 106.69
    }
  }
}
~~~

Combined:

- The `geo_distance` filter ensures results lie within 10 km.
- `gauss` decay prioritizes closer places within those results.

This cleanly separates the business boundary from the ranking signal.

### 7.3. Distance Sort vs. Distance Score

There are two distinct needs:

- **Sort by distance:** strict ordering from nearest to farthest, typically using `_geo_distance` sort.
- **Score by distance:** blending proximity with relevance, freshness, or popularity, using decay functions or `distance_feature`.

If you sort purely by distance, content relevance scores may no longer drive the order. With distance decay, a well-matching location slightly farther away can still outrank a closer but poorly matching place, depending on the combined formula.

### 7.4. distance_feature as Another Option

When you only need to boost scores by closeness on a `date` or `geo_point` field, a `distance_feature` query can be simple and efficient:

~~~json
{
  "distance_feature": {
    "field": "location",
    "origin": "10.78,106.69",
    "pivot": "2km"
  }
}
~~~

For time:

~~~json
{
  "distance_feature": {
    "field": "publishedAt",
    "origin": "now",
    "pivot": "7d"
  }
}
~~~

`pivot` controls how quickly the score drops with distance or time. You can place `distance_feature` inside the `should` clause of a `bool` query to add proximity/freshness signals onto query relevance. Use `function_score` when you need to combine multiple functions, weights, varied decay shapes, or explicit `score_mode`/`boost_mode` rules.

## 8. Combining Freshness, Popularity, and Proximity

A composite ranking formula might include:

1. Content relevance.
2. Freshness from publish date.
3. Popularity from interactions.
4. Proximity from geographic distance.

Example Query DSL:

~~~json
{
  "query": {
    "function_score": {
      "query": {
        "bool": {
          "must": [
            {
              "multi_match": {
                "query": "roasted ground coffee",
                "fields": ["name^3", "description"]
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
              "geo_distance": {
                "distance": "10km",
                "location": {
                  "lat": 10.78,
                  "lon": 106.69
                }
              }
            }
          ]
        }
      },
      "functions": [
        {
          "gauss": {
            "publishedAt": {
              "origin": "now",
              "scale": "14d",
              "offset": "1d",
              "decay": 0.5
            }
          },
          "weight": 2
        },
        {
          "field_value_factor": {
            "field": "viewCount",
            "factor": 0.2,
            "modifier": "log1p",
            "missing": 0
          },
          "weight": 1
        },
        {
          "gauss": {
            "location": {
              "origin": {
                "lat": 10.78,
                "lon": 106.69
              },
              "scale": "5km",
              "offset": "500m",
              "decay": 0.5
            }
          },
          "weight": 2
        }
      ],
      "score_mode": "sum",
      "boost_mode": "sum",
      "max_boost": 10
    }
  }
}
~~~

In this example:

- `multi_match` establishes the baseline relevance score.
- Filters keep only active places within a 10 km radius.
- The freshness function boosts recent content.
- The popularity function adds score from `log1p`-compressed view counts.
- The proximity function favors places close to `origin`.
- `score_mode: sum` adds function contributions together.
- `boost_mode: sum` adds the function score to the relevance score.
- `max_boost` caps total function contribution.

The coordinates and parameters are sample values only. In production applications, geographic `origin` must come from a valid request search coordinate or business context; never hardcode sample coordinates in production queries.

## 9. Weights and Balancing Signals

Signals operate on different scales. Relevance varies with query and content length; popularity can span from 0 to millions; decay typically stays between 0 and 1. Summing uncalibrated values directly can let one signal overpower all others.

A conceptual formula:

\[
S = S_{\text{text}} + w_f F + w_p P + w_d D
\]

Where:

- S_text: content relevance score.
- F: freshness score.
- P: normalized popularity score.
- D: proximity score.
- w_f, w_p, w_d: weights for each signal.

This is a conceptual model. Actual `function_score` output also depends on `score_mode`, `boost_mode`, `max_boost`, and how each function evaluates.

### 9.1. Using weight for Individual Functions

You can add `weight` to raise or lower a function's impact:

~~~json
{
  "filter": {
    "term": {
      "featured": true
    }
  },
  "weight": 1.5
}
~~~

This function applies only to documents with `featured=true` and contributes weight 1.5. A function's filter determines whether the function applies to a document; it is not a filter that excludes documents from the base query.

This is helpful when certain signals only apply to a subset of documents—for example, a promotion boosting only products in an active campaign.

### 9.2. Preventing Popularity from Overpowering Relevance

Using raw views alone can keep old or heavily promoted content pinned at the top. Ways to mitigate this:

- Use `log1p` or `saturation` to compress large values.
- Cap contributions with `weight` and `max_boost`.
- Use interactions within a rolling time window rather than lifetime totals.
- Separate legitimate interactions from automated traffic or spam.
- Keep query relevance as the baseline score.
- Evaluate results across many queries rather than a single demo query.

Popularity can also create a feedback loop: top-ranked results get more clicks and then get boosted further. Monitor position bias and consider debiasing interaction data.

## 10. Using Function Filters to Apply Signals Conditionally

Each function can carry its own filter. This is useful when only some documents should receive a particular boost.

Example boosting only documents marked `featured`:

~~~json
{
  "filter": {
    "term": {
      "featured": true
    }
  },
  "weight": 1.5
}
~~~

Another function can apply to all documents:

~~~json
{
  "field_value_factor": {
    "field": "viewCount",
    "modifier": "log1p",
    "missing": 0
  }
}
~~~

Functions are evaluated against their own filters. If a function's filter does not match, that function contributes nothing for the document. The document must still satisfy the base query of `function_score`.

## 11. Integrating with Spring Data Elasticsearch

Spring Data Elasticsearch can send `function_score` queries via `@Query` JSON DSL or query objects constructed with the Elasticsearch Java Client.

### 11.1. Using @Query for Static Formulas

When a ranking formula rarely changes, `@Query` keeps the DSL close to the repository method:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ArticleRepository
        extends ElasticsearchRepository<Article, String> {

    @Query("""
        {
          "function_score": {
            "query": {
              "bool": {
                "must": [
                  {
                    "match": {
                      "title": "?0"
                    }
                  }
                ],
                "filter": [
                  {
                    "term": {
                      "status": "published"
                    }
                  }
                ]
              }
            },
            "functions": [
              {
                "gauss": {
                  "publishedAt": {
                    "origin": "now",
                    "scale": "14d",
                    "offset": "1d",
                    "decay": 0.5
                  }
                },
                "weight": 2
              },
              {
                "field_value_factor": {
                  "field": "viewCount",
                  "factor": 0.2,
                  "modifier": "log1p",
                  "missing": 0
                }
              }
            ],
            "score_mode": "sum",
            "boost_mode": "sum",
            "max_boost": 10
          }
        }
        """)
    List<Article> searchRanked(String text);
}
~~~

Placeholder `?0` receives the search keyword. Parameters like `scale`, `weight`, and field names are part of the static formula. Verify placeholder binding and query support for the Spring Data Elasticsearch release train in your project.

If scales, weights, origins, or filters vary per request, never construct JSON by string concatenation. Build the query using `NativeQuery` and the Elasticsearch Java Client.

### 11.2. Using NativeQuery When Formulas Vary Per Request

`NativeQuery` integrates Spring Data Elasticsearch with Query DSL from the Elasticsearch Java Client. You can construct the `function_score` query with client-generated builders and pass it in:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(functionScoreQuery)
        .build();

SearchHits<Article> hits =
        operations.search(query, Article.class);
~~~

Here `functionScoreQuery` is a `Query` built with the Elasticsearch Java Client builders for `function_score`, decay functions, `field_value_factor`, `score_mode`, and `boost_mode`. Exact package names, builders, and overloads depend on the Elasticsearch Java Client version used by Spring Data Elasticsearch.

This separation lets the service compute `origin` and per-request parameters while letting Spring Data manage entity mapping. Do not serialize an entity to JSON with Jackson and treat it as a query object; queries must follow the Elasticsearch Java Client structure.

### 11.3. Choosing @Query vs. NativeQuery

| Need | Suitable Approach |
|---|---|
| Static formula, only keywords change | `@Query` |
| Time origin is always `now`, fixed scale | `@Query` may suffice |
| Geographic origin varies with user location | `NativeQuery` |
| Weights vary by request type | `NativeQuery` |
| Conditionally adding/removing functions | `NativeQuery` |
| `function_score` with many filter branches | `NativeQuery`, or static JSON DSL if readable |

## 12. Entity Mapping for Ranking Signals

Example index fields required:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
      },
      "status": {
        "type": "keyword"
      },
      "publishedAt": {
        "type": "date"
      },
      "viewCount": {
        "type": "long"
      },
      "location": {
        "type": "geo_point"
      },
      "featured": {
        "type": "boolean"
      }
    }
  }
}
~~~

Corresponding Java model:

| Field | Suggested Java Type | Elasticsearch Mapping |
|---|---|---|
| title | `String` | `text` |
| status | `String` or enum | `keyword` |
| publishedAt | `Instant` | `date` or `date_nanos` if needed |
| viewCount | `Long` | `long` |
| location | `GeoPoint` or suitable coordinate type | `geo_point` |
| featured | `Boolean` | `boolean` |

Spring Data annotations can declare corresponding field types via `@Field`. For geographic fields, use `GeoPoint` and the declaration style supported by your version. Actual index mappings must still be verified; editing annotations alone does not update mappings on an existing index.

## 13. Missing Data and Unreliable Signals

A ranking formula must define how to handle documents missing data for a signal:

| Scenario | Handling to Consider |
|---|---|
| Missing `viewCount` | Use `missing: 0` or an appropriate default |
| Missing `publishedAt` | Decide whether to exclude, use a fallback, or skip decay |
| Missing `location` | Skip proximity; if location is required, filter with `exists`/filter |
| Negative popularity values | Clean data or apply business rules before scoring |
| Abnormal future timestamps | Check data sources; prevent bad values from getting excessive boosts |

Do not assume every document has all signals populated. If a field is mandatory, enforce it via `exists` or validation. If it is only a secondary signal, define a fallback and check how Elasticsearch handles missing fields for that function.

## 14. Tuning Formulas and Evaluating Quality

A formula can be syntactically valid yet rank poorly. Evaluate using representative data and queries.

Tuning workflow:

1. Create a baseline using relevance alone.
2. Add freshness and observe ranking changes.
3. Add popularity with compressed values.
4. Add proximity if the product has geographic context.
5. Change one weight or scale at a time to understand its impact.
6. Compare top-k results across formula versions.
7. Gather user feedback or existing relevance labels.
8. Monitor click-through rate, conversions, result diversity, and position bias.

Applicable metrics depend on the problem and include Precision@K, Recall@K, NDCG@K, and conversion rate. Do not optimize for clicks alone if clicks do not reflect final quality.

### 14.1. Using Explain to Understand Scores

Elasticsearch provides the Explain API for a specific document to inspect why it received a certain score:

~~~http
GET /articles/_explain/article-100
Content-Type: application/json

{
  "query": {
    "function_score": {
      "query": {
        "match": {
          "title": "search"
        }
      },
      "functions": [
        {
          "field_value_factor": {
            "field": "viewCount",
            "modifier": "log1p",
            "missing": 0
          }
        }
      ],
      "score_mode": "sum",
      "boost_mode": "sum"
    }
  }
}
~~~

Explain reveals the base score and function contributions. It helps when a document unexpectedly ranks too high or too low. Use it during investigation and development; do not enable detailed explanations on every production request due to overhead.

### 14.2. Testing with Fixed Timestamps

Queries using `origin: now` vary depending on when they run, making exact score assertions hard to reproduce in tests. When testing decay, use a fixed timestamp origin, index documents at known offsets, and verify relative ordering and score trends.

For proximity, use fixed coordinates and documents at known distances. Test cases inside `offset`, near `scale`, outside the filter radius, and missing `location`.

## 15. Common Mistakes

### 15.1. Using Decay Instead of a Limiting Filter

Decay only reduces scores; distant or old documents can still appear. When hard boundaries exist, add `range` or `geo_distance` filters.

### 15.2. Letting Popularity Overpower Relevance

Large counters can produce abnormally high scores. Use `log1p`, `saturation`, `factor`, `weight`, and `max_boost` to keep them in check.

### 15.3. Confusing score_mode with boost_mode

`score_mode` combines functions with each other. `boost_mode` combines the function score with the base query score. Choosing the wrong one can alter results substantially.

### 15.4. Using multiply with a Zero-Valued Function

A zero-valued function can pull a product down to 0. Check value domains, fallbacks, and business semantics before choosing `multiply`.

### 15.5. Filter-Only Base Query with boost_mode multiply

If the base query produces no score, multiplication can force the final score to 0. Use a scoring query, or select an appropriate `boost_mode` such as `replace` when functions are the primary score source.

### 15.6. Failing to Handle Missing Fields

Documents lacking popularity, timestamp, or location may score unexpectedly. Define fallbacks and test them.

### 15.7. Swapping Latitude and Longitude

Coordinate strings and coordinate objects have distinct conventions. Reversing the order calculates distances from the wrong spot on Earth.

### 15.8. Summing Signals on Different Scales

Adding unnormalized popularity directly onto relevance lets popularity dominate. Inspect score distributions and calibrate each signal.

### 15.9. Evaluating with a Single Query

A formula may look great for one keyword and terrible for another. Use a representative query set and evaluate top-k results.

## 16. Workflow for Designing a Ranking Formula

When adding freshness, popularity, or distance to search:

1. Identify mandatory conditions and place them in `must`/`filter`/`must_not`.
2. Establish the baseline relevance score.
3. Choose source fields for freshness, popularity, and proximity.
4. Check mappings and data quality for each field.
5. Choose decay functions and `origin`, `scale`, `offset`, `decay` parameters.
6. Choose `field_value_factor` or `rank_feature` for popularity.
7. Decide whether distance is a hard filter, distance sort, or scoring signal.
8. Choose `score_mode` and `boost_mode`.
9. Bound contributions with `weight` or `max_boost` if needed.
10. Test missing data, boundary values, and real queries.
11. Evaluate rankings across multiple queries and adjust using metrics.
12. Monitor quality after deployment.

Some sample decisions:

| Goal | Implementation |
|---|---|
| Newer articles rank higher | Date decay on `publishedAt` |
| Popular items preferred without dominating | `field_value_factor` with `log1p`, or `rank_feature` |
| Closer locations preferred | Geo decay on `geo_point` |
| Search only within a specific radius | `geo_distance` filter |
| Keep relevance and add secondary signals | `score_mode: sum`, `boost_mode: sum` after calibration |
| Rank purely by functions | `boost_mode: replace`, if required |

## 17. Conclusion

Freshness, popularity, and distance are supplementary signals that bring search results closer to real-world user needs. Date decay favors recent documents, `field_value_factor` or `rank_feature` models popularity, and geo decay or `distance_feature` favors nearby locations.

`function_score` combines multiple functions via `score_mode`, then combines that result with the query score via `boost_mode`. These two parameters serve distinct purposes and should be chosen alongside `weight`, `scale`, `offset`, `decay`, and `max_boost`.

Keep eligibility constraints inside queries/filters, use freshness/popularity/proximity to rank within that eligible set, handle missing data explicitly, and verify mappings. A good formula must be evaluated across many real queries with a baseline, Explain, and top-k metrics—never based on a single example or arbitrary weights.
