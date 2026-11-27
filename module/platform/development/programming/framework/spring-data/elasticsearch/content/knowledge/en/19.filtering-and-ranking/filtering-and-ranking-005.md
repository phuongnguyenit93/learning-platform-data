# Function Score for Adding Business Signals

In full-text search, Elasticsearch typically ranks documents based on how well they match the user's input text. However, the best keyword match is not necessarily the best result from a business standpoint. A store might want to favor items on sale, popular products, or newly updated products. A recruiting platform might want to favor postings whose application deadline has not expired. A content portal might want to combine text relevance with recency and engagement.

Elasticsearch provides the `function_score` query to add such signals into the relevance score. The inner query still finds documents by content, while the functions add to or adjust the score based on fields, conditions, or formulas. As a result, applications can combine relevance with business signals in a single query.

Function score is useful when you want to tune result order while keeping content-driven search results. It must be designed carefully so business signals support relevance rather than overpowering it, and you must distinguish ranking from mandatory conditions such as access rights, display eligibility, or item existence.

## 1. Why Add Business Signals?

Suppose a user searches for `wireless keyboard`. Elasticsearch might find three products:

| Product | Content Match | Business Signal |
|---|---|---|
| Keyboard A | Very high | Few views, low stock |
| Keyboard B | High | Popular, in stock |
| Keyboard C | High | Newly updated, currently promoted |

Based on text relevance alone, Keyboard A might rank first because its name matches more closely. Yet the product team might prefer B or C at the top, provided they remain relevant to the query.

Common signals:

- **Popularity:** views, purchases, saves, or ratings.
- **Freshness:** publish time, update time, or event date.
- **Business priority:** campaigns, promoted product groups, or importance levels.
- **Inventory:** in-stock status or stock quantity.
- **Quality:** review score, trustworthiness, or data quality.
- **User context:** region, segment, or preferences permitted for ranking.

Not every signal belongs in the score. Mandatory constraints such as blocked products, expired listings, or items the user lacks permission to view must be handled by filters or authorization before ranking. Function score should only reorder documents that are already eligible to appear.

## 2. What Is Function Score?

`function_score` wraps a base query and one or more scoring functions. The base query determines which documents match; the functions determine how to add to or adjust the score for those documents.

Example:

    GET products/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "name": "wireless keyboard"
            }
          },
          "functions": [
            {
              "field_value_factor": {
                "field": "popularity",
                "factor": 1.2,
                "modifier": "log1p",
                "missing": 0
              }
            }
          ],
          "boost_mode": "multiply"
        }
      }
    }

In this example:

1. `match` finds products relevant to `wireless keyboard`.
2. `field_value_factor` reads each document's `popularity` value.
3. The `log1p` modifier transforms the popularity value to curb excessive influence from products with very high view counts.
4. `boost_mode` `multiply` combines the function score with the base query score.

Documents that do not match the base query will not be included merely because they have high popularity. Function score adjusts the scores of documents selected by the base query.

## 3. Structure of function_score

A function score query typically consists of these parts:

| Component | Role |
|---|---|
| query | Base query to select documents and calculate initial relevance |
| functions | List of functions that supply additional scores |
| filter inside each function | Condition deciding whether that function applies to a document |
| score_mode | How scores from multiple applicable functions are combined |
| boost_mode | How the combined function score is combined with the base query score |
| max_boost | Caps the function score after functions are combined |
| min_score | Excludes results whose final score is below a threshold |

You can visualize the scoring flow as:

    Base query
        |
        v
    Select matching documents
        |
        v
    Compute content score (query score)
        |
        +---------------------------+
        |                           |
        v                           v
    Function 1                  Function 2
    popularity                  freshness
        |                           |
        +-------------+-------------+
                      |
                      v
               score_mode
                      |
                      v
              function score
                      |
                      v
                max_boost
                      |
                      v
          boost_mode with query score
                      |
                      v
                final score
                      |
                      v
               Rank results

A key point is that `score_mode` and `boost_mode` handle two distinct steps. `score_mode` combines functions with one another; `boost_mode` combines the function result with the base query's score.

## 4. Commonly Used Functions

Elasticsearch provides several scoring functions:

| Function | Suitable Signal | How It Works |
|---|---|---|
| weight | Favoring a group of documents | Multiplies the function score by a fixed weight |
| field_value_factor | Popularity, rating, purchase count | Uses a numeric field value to produce a score |
| gauss | Recency, distance, or time | Score decays along a Gaussian curve away from origin |
| exp | Recency or distance | Score decays exponentially |
| linear | Recency or distance | Score decays linearly |
| random_score | Controlled result shuffling | Generates pseudo-random scores, optionally with a seed |
| script_score | Custom business formula | Computes score using a script |

Multiple functions can be used in a single query. Each function can apply to all matching documents or only when that function's own filter evaluates to true.

You do not need a script for every scenario. Built-in functions such as `field_value_factor` and decay functions are generally easier to understand, easier to optimize, and safer than custom script formulas.

## 5. Weight Function: Favoring a Group of Documents

`weight` assigns a fixed weight to documents satisfying the function's filter. For example, to boost products in an active campaign:

    GET products/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "name": "wireless keyboard"
            }
          },
          "functions": [
            {
              "filter": {
                "term": {
                  "campaign": "featured"
                }
              },
              "weight": 2.0
            }
          ],
          "boost_mode": "multiply"
        }
      }
    }

Documents with `campaign = featured` receive a function weight of 2.0. With `boost_mode` `multiply`, their base score is multiplied by the function score; documents not matching the function's filter do not receive this boost.

Weight fits group-based signals:

- Products participating in a campaign.
- Articles in a prioritized category.
- Verified documents.
- Suppliers in a preferred tier.

Fixed weights are easy to explain, though you should avoid creating overly huge gaps. If the weight is much larger than content score differences, a weakly matching document can overtake a more relevant one.

### Function Filter vs. Base Query Filter

Filters in these two places play different roles:

- A filter inside the base query's `bool` restricts which documents are allowed to appear.
- A filter inside a function only decides whether that function affects the document.

For instance, if out-of-stock products must be excluded from results, put `status` or `in_stock` in the query filter. If you only put the in-stock condition in a function filter, out-of-stock items can still appear—they simply won't get the bonus points.

## 6. Field Value Factor: Using Numeric Values for Scoring

`field_value_factor` reads a numeric field value from the document to compute a function score. It is a common choice for popularity, purchase counts, ratings, or other numeric signals.

Example:

    GET products/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "name": "wireless keyboard"
            }
          },
          "field_value_factor": {
            "field": "popularity",
            "factor": 1.2,
            "modifier": "log1p",
            "missing": 0
          },
          "boost_mode": "sum"
        }
      }
    }

In this case:

- `field` specifies the numeric field.
- `factor` multiplies the field value before the modifier is applied per Elasticsearch's formula.
- `modifier` transforms the value to adjust its distribution.
- `missing` is the fallback value if a document lacks the field.

Common modifiers:

| Modifier | General Meaning | Notes |
|---|---|---|
| none | Keeps the value after multiplying by factor | Large values can dominate the score |
| log | Base-10 logarithm | Can be negative or invalid for unsuitable inputs |
| log1p | Logarithm of 1 plus the value | Usually suitable for non-negative counts |
| log2p | Logarithm of 2 plus the value | Avoids issues in the small-value region |
| ln | Natural logarithm | Watch the input domain |
| ln1p | Natural logarithm of 1 plus the value | Often used with non-negative counts |
| ln2p | Natural logarithm of 2 plus the value | Smooth transformation near small values |
| sqrt | Square root | Slows growth of large values |
| square | Square | Makes large values grow faster |
| reciprocal | Reciprocal | Larger values yield smaller scores |

### Why Is log Commonly Used for Popularity?

Suppose product A has 10 purchases, B has 100 purchases, and C has 100,000 purchases. Using raw purchase counts directly could let C produce a drastically larger score and drown out text matching.

Logarithms compress gaps between large values. They still reflect that more popular items carry a stronger signal, while curbing the impact of extreme values.

For non-negative counts, `log1p` or `ln1p` is often convenient because it handles zero values. Even so, still verify missing data, negative values, and mapping types.

### Limitations of field_value_factor

- The field must have an appropriate numeric type.
- Field values must be controlled so they do not yield negative or invalid scores.
- For multi-valued fields, `field_value_factor` picks one value according to Elasticsearch rules rather than aggregating all elements like arbitrary business logic.
- `missing` should be declared whenever the field might be absent.
- When using fields with very large values, choose a modifier or factor to keep scores within expected bounds.

If you need to combine multiple fields or complex formulas, you can use multiple functions or `script_score`; however, prefer normalizing data before increasing query complexity.

## 7. Decay Functions: Reducing Score by Recency or Distance

Decay functions give documents higher scores when close to a reference value (`origin`) and lower scores further away. They are commonly used for:

- Newly published articles.
- Recently updated products.
- Upcoming events.
- Locations near the search position.
- Documents with deadlines or effective dates.

Elasticsearch supports three common decay shapes:

- `gauss`: decays along a Gaussian curve, gentle near the origin.
- `exp`: decays exponentially.
- `linear`: decays linearly.

Common parameters:

| Parameter | Role |
|---|---|
| origin | Reference value where the decay score reaches 1 |
| scale | Distance at which the score drops to the `decay` level |
| offset | Region around `origin` where no decay occurs |
| decay | Score level at distance `scale`, typically between 0 and 1 |

Example favoring recent articles within 30 days:

    GET articles/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "title": "spring data"
            }
          },
          "functions": [
            {
              "gauss": {
                "published_at": {
                  "origin": "2026-11-13T00:00:00Z",
                  "scale": "30d",
                  "offset": "2d",
                  "decay": 0.5
                }
              }
            }
          ],
          "boost_mode": "multiply"
        }
      }
    }

With this configuration:

- Articles near `origin` receive a decay score close to 1.
- Within the two-day `offset`, the score does not drop.
- At distance `scale` beyond the offset boundary, the score decays to `decay` according to the chosen curve.
- Articles further from the reference timestamp receive lower scores.

The `origin` value in the example is hardcoded for illustration. In real applications, the reference timestamp should usually be generated from the current request time or a specific business milestone. Avoid hardcoding a fixed current date in source code.

### Choosing Decay by Business Needs

`gauss` typically fits when you want gentle decay around `origin`. `exp` drops faster with distance. `linear` produces a steady downward slope until reaching the boundary region. No single curve is always best; test with real time horizons and inspect the result ordering.

### Decay for Geographic Distance

Decay can also be applied to `geo_point` fields, for instance to prefer places near a user's location. There `origin` is a coordinate and `scale`/`offset` use distance units.

If location is a hard requirement within a search radius, use a geo filter to restrict results; decay should only rank closer places higher within the eligible set.

## 8. Combining Multiple Functions

A query can combine popularity, freshness, and campaign priority. Each function can have its own filter:

    GET products/_search
    {
      "query": {
        "function_score": {
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
                    "status": "ACTIVE"
                  }
                },
                {
                  "term": {
                    "in_stock": true
                  }
                }
              ]
            }
          },
          "functions": [
            {
              "field_value_factor": {
                "field": "popularity",
                "modifier": "log1p",
                "missing": 0
              },
              "weight": 1.0
            },
            {
              "filter": {
                "term": {
                  "campaign": "featured"
                }
              },
              "weight": 1.5
            },
            {
              "gauss": {
                "updated_at": {
                  "origin": "2026-11-13T00:00:00Z",
                  "scale": "30d",
                  "decay": 0.5
                }
              }
            }
          ],
          "score_mode": "sum",
          "boost_mode": "sum",
          "max_boost": 8
        }
      }
    }

The base query allows only active and in-stock products. Three functions supply popularity, campaign, and freshness signals.

In this example:

- The popularity function uses the numeric value transformed by `log1p`.
- The campaign function applies only to documents with `campaign = featured`.
- The `gauss` function evaluates freshness based on `updated_at`.
- `score_mode` `sum` adds scores from applicable functions.
- `boost_mode` `sum` adds the function score to the query score.
- `max_boost` caps the function score before combining with the query score.

This example illustrates structure. Weights and combination rules must be tuned on actual data. Do not copy numbers like 1.5, 8, or a 30-day scale as universal defaults for every business case.

## 9. score_mode: Combining Multiple Functions Together

When there are multiple functions, `score_mode` defines how scores from functions applying to a document are combined.

| score_mode | Meaning |
|---|---|
| multiply | Multiplies function scores |
| sum | Sums function scores |
| avg | Takes the average |
| first | Uses the first function whose filter matches |
| max | Takes the highest function score |
| min | Takes the lowest function score |

Example:

    "functions": [
      {
        "filter": { "term": { "campaign": "featured" } },
        "weight": 2
      },
      {
        "field_value_factor": {
          "field": "popularity",
          "modifier": "log1p",
          "missing": 0
        }
      }
    ],
    "score_mode": "sum"

With `sum`, campaign and popularity scores are added. With `multiply`, the two functions are multiplied together; if one function evaluates to 0, the product can become 0. This can produce unexpected results when a signal can be absent or zero.

`first` is useful when functions are ordered by priority and their filters are mutually exclusive. Elasticsearch applies the first function whose filter matches. Order `functions` deliberately when using this mode.

`avg` in `function_score` accounts for function weights per Elasticsearch semantics. When exact control over the formula is needed, consult the documentation for your running version and inspect with the Explain API.

## 10. boost_mode: Combining Function Score with Relevance

Once the function score is computed, `boost_mode` determines how it combines with the base query's score.

| boost_mode | Meaning |
|---|---|
| multiply | Multiplies query score by function score |
| sum | Adds query score and function score |
| avg | Takes the average |
| max | Takes the larger value |
| min | Takes the smaller value |
| replace | Uses function score in place of query score |

Example:

    "boost_mode": "multiply"

With `multiply`, a document with low text relevance yet a very high function score can still be pushed upward. Conversely, a low function score can drag down a well-matching document.

With `sum`, the function score acts as an additive signal. This can sometimes be easier to control if business scores are normalized to a suitable range.

With `replace`, the content score is completely replaced by the function score. Use this only when ranking intentionally depends solely on the function formula, or when the base query acts purely as a filter. If you want to preserve text relevance, avoid picking `replace` accidentally.

### Distinguishing score_mode and boost_mode

Suppose there are two functions:

    popularity score = 2
    freshness score = 3

If `score_mode = sum`, the function score is 5. If `score_mode = multiply`, the function score is 6.

Suppose the query score is 4:

- With function score 5 and `boost_mode = sum`, the final score is 9.
- With function score 5 and `boost_mode = multiply`, the final score is 20.
- With function score 5 and `boost_mode = replace`, the final score is 5.

This arithmetic example clarifies the two combination steps; real scores also depend on how Elasticsearch evaluates each function and caps scores.

## 11. max_boost and min_score

### max_boost

`max_boost` caps the function score after functions are combined via `score_mode`. It prevents an unusually large business signal from inflating the final score beyond expected bounds.

Example:

    "score_mode": "sum",
    "max_boost": 5,
    "boost_mode": "sum"

If the summed function score exceeds 5, the function portion is capped at 5 before combining with the query score.

`max_boost` does not normalize source data. If `popularity` has extreme outliers, you should still address them in the data layer or pick an appropriate modifier.

### min_score

`min_score` drops documents whose final score is below a threshold:

    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "name": "keyboard"
            }
          },
          "min_score": 0.8
        }
      }
    }

When using `min_score`, Elasticsearch must compute scores for matching documents before dropping those below the threshold. This can make queries more resource-intensive, especially on large result sets.

Do not use `min_score` as a substitute for filtering mandatory conditions. If a product must be in stock, use a `term` filter `in_stock: true`. A score threshold is better suited to ranking or pruning very low-relevance results after scoring.

## 12. Script Score: Custom Business Formulas

When built-in functions cannot express a formula, `script_score` can be used. Scripts can combine multiple fields, parameters, and transformations.

Example combining popularity and rating:

    GET products/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "name": "wireless keyboard"
            }
          },
          "script_score": {
            "script": {
              "source": "Math.log(1 + doc['popularity'].value) + doc['rating'].value",
              "params": {}
            }
          },
          "boost_mode": "replace"
        }
      }
    }

In this example, the script computes a score from `popularity` and `rating`, and `replace` uses the script output instead of the query score. To preserve text relevance, choose another `boost_mode` such as `sum` or `multiply` and adjust the formula.

### Use params Instead of Concatenating Script Strings

If the formula takes per-request parameters, pass them through `params`:

    "script": {
      "source": "Math.log(1 + doc['popularity'].value) * params.popularityWeight",
      "params": {
        "popularityWeight": 0.4
      }
    }

Parameters enable reuse of compiled scripts and avoid embedding input values into the script source. Never insert user-supplied content directly into script source.

### Handling Missing Fields

Before reading `doc['field'].value`, check whether the field can be missing. You can use a size check:

    "source": "doc['popularity'].size() == 0 ? 0 : Math.log(1 + doc['popularity'].value)"

If a field can be negative or hold out-of-range values, validate beforehand or handle it explicitly in the script. The final score must be valid, non-negative, and within numeric limits supported by Elasticsearch.

### Cost and Safety of Scripts

`script_score` is flexible, but generally more expensive than built-in functions. Scripts run during document scoring; with large candidate sets, the cost can be substantial.

Best practices:

- Use `field_value_factor` or decay functions whenever sufficient for business needs.
- Keep scripts short and avoid unnecessary operations.
- Use `params` to pass variables.
- Never allow users to submit arbitrary scripts.
- Verify that fields exist and have suitable data types.
- Measure latency and load on a representative dataset.

## 13. Random Score: Controlled Result Shuffling

`random_score` generates a pseudo-random score per document. It can be useful when you want to avoid results always appearing in the exact same order, for example:

- Shuffling products with comparable relevance.
- Sampling randomly for a recommendation list.
- Introducing diversity in certain content discovery flows.

Example:

    GET products/_search
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "category": "accessories"
            }
          },
          "random_score": {
            "seed": 42
          },
          "boost_mode": "replace"
        }
      }
    }

A seed helps produce repeatable results under matching conditions, though stability also depends on how Elasticsearch generates random scores and which field is used. If consistent ordering across paginated requests is required, design a stable seed and field and verify version-specific semantics.

Do not use `random_score` to replace relevance in primary search. You can combine `random_score` with query score using a suitable `boost_mode` if you only want a small degree of diversity.

## 14. Designing the Popularity Signal

Popularity is often an easy business signal to start with, though raw view counts can introduce heavy skew.

A sensible process:

1. Define which events count toward popularity: view, click, add-to-cart, or purchase.
2. Choose a time window: all-time history, last 30 days, or last 7 days.
3. Normalize values so older products do not permanently outrank newer ones.
4. Cap impact with a modifier, factor, or `max_boost`.
5. Ensure documents with missing data receive a sensible default.
6. Evaluate results across representative queries.

Example mapping:

    {
      "properties": {
        "popularity_30d": {
          "type": "long"
        }
      }
    }

Query:

    {
      "field_value_factor": {
        "field": "popularity_30d",
        "factor": 1.0,
        "modifier": "log1p",
        "missing": 0
      }
    }

Using a rolling window like 30 days helps the signal reflect current trends better. Popularity calculation should be handled in a data pipeline or ingestion service; avoid running expensive aggregations over the entire dataset on every search request unnecessarily.

## 15. Designing the Freshness Signal

Freshness is commonly used for articles, recently updated products, job listings, or events. A common approach is decay over a date field.

Example:

    {
      "gauss": {
        "published_at": {
          "origin": "now",
          "scale": "14d",
          "offset": "1d",
          "decay": 0.5
        }
      }
    }

With `origin` set to `now`, documents closer to the present receive higher scores. A `scale` of 14 days and `decay` of 0.5 define the decay rate. A 1-day `offset` keeps very recent items from decaying.

Freshness should not always carry a heavy weight. In technical documentation search, an older accurate article may be far more helpful than a newer low-quality one. Let text relevance and quality retain a substantial role.

If a query searches for events within a date range, use a `range` filter to exclude past or overly distant events. Decay should only rank valid events by proximity to the desired time.

## 16. Should a Business Signal Be a Score or a Filter?

This is the most critical design decision when using `function_score`.

| Business Requirement | Usually Suitable Approach |
|---|---|
| Show only active products | Filter |
| Users may only view documents belonging to their tenant | Mandatory authorization/filter |
| Show only in-stock products | Filter if mandatory |
| Prefer more popular products | Function score |
| Prefer newer articles while still allowing older ones | Decay function |
| Promote a campaign during a time period | Filter inside function + weight |
| Only return events within a certain radius | Geo filter |
| Within a valid radius, prefer closer places | Geo decay |

Never use scoring to enforce data protection. A document that a user is unauthorized to view must be excluded via authorization or an appropriate filter; you cannot simply assign it a low score and hope it stays off the first page.

## 17. Function Score in Spring Data Elasticsearch

Modern Spring Data Elasticsearch lets you construct `function_score` using `NativeQuery` and the Elasticsearch Java API Client builders.

Example boosting popular products:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .functionScore(fs -> fs
                .query(q2 -> q2
                    .match(m -> m
                        .field("name")
                        .query(keyword)
                    )
                )
                .functions(fn -> fn
                    .fieldValueFactor(fvf -> fvf
                        .field("popularity")
                        .factor(1.0)
                        .modifier(FieldValueFactorModifier.Log1p)
                        .missing(0.0)
                    )
                )
                .scoreMode(FunctionScoreMode.Sum)
                .boostMode(FunctionBoostMode.Sum)
                .maxBoost(5.0)
            )
        )
        .withPageable(pageable)
        .build();

The base query is a `match` on `name`. The function reads `popularity`, applies `log1p`, and combines with the query score via `sum`. `maxBoost` caps the function score portion.

Types typically imported from the Elasticsearch Java API Client:

    import co.elastic.clients.elasticsearch._types.query_dsl.FieldValueFactorModifier;
    import co.elastic.clients.elasticsearch._types.query_dsl.FunctionBoostMode;
    import co.elastic.clients.elasticsearch._types.query_dsl.FunctionScoreMode;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Enum names and builder overloads depend on the Java API Client version used by Spring Data. Check your actual dependency if your IDE reports different signatures. Avoid mixing legacy `NativeSearchQuery` and `QueryBuilders` from older Spring Data generations with modern `NativeQuery`/Java API Client code in the same snippet.

### Adding a Filtered Function

Example adding a campaign weight:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .functionScore(fs -> fs
                .query(q2 -> q2
                    .match(m -> m
                        .field("name")
                        .query(keyword)
                    )
                )
                .functions(fn -> fn
                    .filter(f -> f
                        .term(t -> t
                            .field("campaign")
                            .value(FieldValue.of("featured"))
                        )
                    )
                    .weight(1.5)
                )
                .scoreMode(FunctionScoreMode.Sum)
                .boostMode(FunctionBoostMode.Sum)
            )
        )
        .build();

The function applies only when `campaign` is `featured`. Other documents can still appear if the base query matches, without receiving this function's weight.

### Combining Multiple Functions

The Java API Client allows adding multiple functions to the `functions` list. You can build each `FunctionScore` individually and pass them to the builder for readability, especially when each function has a distinct filter or score type.

General structural example:

    List<FunctionScore> functions = List.of(
        FunctionScore.of(fn -> fn
            .fieldValueFactor(fvf -> fvf
                .field("popularity")
                .modifier(FieldValueFactorModifier.Log1p)
                .missing(0.0)
            )
        ),
        FunctionScore.of(fn -> fn
            .filter(f -> f
                .term(t -> t
                    .field("campaign")
                    .value(FieldValue.of("featured"))
                )
            )
            .weight(1.5)
        )
    );

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .functionScore(fs -> fs
                .query(q2 -> q2
                    .match(m -> m
                        .field("name")
                        .query(keyword)
                    )
                )
                .functions(functions)
                .scoreMode(FunctionScoreMode.Sum)
                .boostMode(FunctionBoostMode.Sum)
            )
        )
        .build();

This is how you organize it when your Java API Client version provides an overload accepting a `List<FunctionScore>`. Some versions also offer builder-lambda overloads for `functions`; use whichever matches your installed API.

## 18. Keep the Base Query Selective Enough

`function_score` normally has to evaluate scores for documents matching the base query. If the base query is too broad, many documents must pass through scoring functions, increasing cost.

Bad example:

    {
      "query": {
        "function_score": {
          "query": {
            "match_all": {}
          },
          "field_value_factor": {
            "field": "popularity"
          }
        }
      }
    }

If the index holds tens of millions of documents, this query can force Elasticsearch to score a massive candidate set.

Use an appropriate base query:

- `match` or `multi_match` on the target search text.
- Filters on tenant, status, document type, and mandatory constraints.
- Range filters on time or values when required by business logic.
- Keep the candidate set wide enough not to miss good results, while avoiding unnecessary `match_all`.

Function score adjusts ordering; it does not replace sound base query design.

## 19. Controlling Scores and Preventing Signals from Overpowering Relevance

Elasticsearch scores are not probabilities. Scores can change when:

- Index contents change.
- Term frequencies or document distributions change.
- Analyzers change.
- Shard counts and data distribution change.
- `function_score`, boosts, or query clauses change.

Therefore, do not pick an arbitrary score cutoff and treat it as a fixed quality bar across all indexes or over time.

Ways to keep scores under control:

1. Use modifiers to compress skewed numeric values.
2. Normalize signals in the data layer.
3. Start with small weights and increase gradually through evaluation.
4. Cap function scores with `max_boost`.
5. Choose an appropriate `boost_mode` to preserve the query score's role.
6. Use filters for mandatory conditions.
7. Evaluate result ordering with a real query set.

If popularity ranges from 0 to millions while text scores are much smaller, direct `sum` can let popularity dominate. Use `log1p`, a small scale factor, or prior normalization.

## 20. Explain and Profile for Understanding Results

When a document ranks surprisingly high or low, the Explain API shows the score breakdown:

    GET products/_explain/p-101
    {
      "query": {
        "function_score": {
          "query": {
            "match": {
              "name": "wireless keyboard"
            }
          },
          "field_value_factor": {
            "field": "popularity",
            "modifier": "log1p",
            "missing": 0
          },
          "boost_mode": "sum"
        }
      }
    }

Explain helps identify:

- How much the base query contributed.
- Which functions were applied.
- What field value was used in the function.
- How `boost_mode` produced the final score.

The Profile API helps inspect execution time across query components, though it increases request overhead and produces large responses. Use them during investigation or benchmarking, not enabled by default on every production request.

## 21. Performance Considerations

`function_score` can make queries more expensive, particularly when functions run across large numbers of documents.

Contributing factors:

- Number of documents matching the base query.
- Number of functions in the list.
- Complexity of any scripts.
- Whether fields have doc values.
- Number of fields read during scoring.
- Decay type and data structure.
- Request rate and concurrency.

To keep performance in check:

- Use filters to narrow the candidate set before scoring.
- Prefer built-in functions over scripts whenever possible.
- Do not add functions that make no practical difference to relevance.
- Normalize and precompute expensive signals.
- Benchmark on production-like data and concurrency.
- Monitor p95/p99 latency, CPU, heap, and throughput.

For simple numeric signals, consider the `rank_feature` field type and `rank_feature` query instead of `function_score`. They are built specifically for certain ranking signals and can be more efficient. The choice depends on signal type, mapping constraints, and Elasticsearch version.

## 22. Function Score vs. Sort

`sort` and `function_score` solve two different problems:

- **Sort:** orders by one or more fields in a fixed sequence.
- **Function score:** adjusts scores to combine relevance with business signals.

Example sorting by popularity:

    "sort": [
      { "popularity": "desc" }
    ]

Results can place the most popular product at the top even if it matches the keywords poorly.

With `function_score`, popularity is blended with text relevance. A product needs both good query match and strong business signals to earn a high score.

Use `sort` when field order is a hard rule—such as newest first or lowest price first. Use `function_score` when you want a composite ranking across multiple signals. You can combine score and sort, provided you understand that sorting by a field can override score-based ranking.

## 23. Testing Relevance Before Deployment

`function_score` is a product decision, not just a syntax change. Before shipping, prepare a representative query set and define expected ordering.

Practical workflow:

1. Save baseline results using only the base query.
2. Pick one business signal and add a single function.
3. Compare before and after result ordering.
4. Check popular queries, rare queries, and queries without strong matches.
5. Test different `weight`, `factor`, `modifier`, or decay values.
6. Test documents with missing fields, zero values, and outliers.
7. Measure latency and load as candidate counts grow.
8. Add the next signal only after the previous one shows an observable improvement.

Evaluation metrics can include:

- Precision@k: fraction of relevant results in top k.
- Recall@k: fraction of relevant documents retrieved in top k.
- nDCG@k: evaluates ranked ordering accounting for graded relevance.
- MRR: position of the first relevant result.
- Conversion rate or business metrics suited to the product.

Do not optimize solely for clicks. A signal might increase short-term clicks while hurting quality, diversity, or result trustworthiness.

## 24. Common Mistakes

### Using function_score Instead of Mandatory Conditions

If a document must not appear, exclude it via authorization or a filter. Giving it a low score does not guarantee it disappears from results.

### Confusing Function Filter with Query Filter

A filter inside a function only controls whether that function applies. It does not remove documents from the results. Mandatory conditions belong in the base query.

### Using Raw Popularity

Huge popularity numbers can drown out text relevance. Use a log modifier, a factor, or pre-normalize data before scoring.

### Choosing boost_mode Without Understanding Scores

`multiply`, `sum`, and `replace` yield very different results. Decide whether the function score acts as an additive signal or replaces relevance.

### Confusing score_mode with boost_mode

`score_mode` combines functions with each other. `boost_mode` combines the function score with the query score. These two steps are not interchangeable.

### Omitting missing

Documents missing a field can trigger errors or fail to score as intended. Specify `missing` appropriately and define the business fallback value.

### Using a log Modifier with Unsuitable Values

Zero or negative values can make `log` invalid or yield negative scores. For non-negative counts, `log1p` is usually safer; still validate input data.

### Adding Too Many Functions

Many functions make queries hard to reason about and raise execution cost. Add signals one by one, measure outcomes, and drop functions that fail to improve relevance.

### Using script_score for Simple Formulas

If `field_value_factor` or decay already meets the need, using a script adds unnecessary cost and complexity.

### Using min_score as a Business Filter

Scores are not a consistent metric across all queries. Status, tenant, access control, or inventory constraints should use dedicated filters.

### Using sort When Blended Relevance Is Actually Needed

Sorting by popularity or update date can push weak keyword matches to the top. If you need to combine text relevance with business signals, consider `function_score`.

## 25. Workflow for Designing a Function Score

When adding business signals to search, follow this order:

1. Define the base query and ensure it returns the right set of relevant documents.
2. Classify each rule as either a mandatory condition or a ranking signal.
3. For mandatory conditions, use `bool` filters or authorization.
4. For simple numeric signals, try `field_value_factor`.
5. For recency or distance, try decay functions.
6. For group-based boosting, use a function filter paired with `weight`.
7. Use `script_score` only when built-in functions fall short.
8. Choose `score_mode` to combine functions.
9. Choose `boost_mode` to preserve or replace query relevance as intended.
10. Cap with `max_boost` if needed, and be cautious with `min_score`.
11. Use the Explain API to inspect scores when results look unexpected.
12. Evaluate relevance and performance on representative data before release.

## Conclusion

`function_score` blends text relevance with business signals such as popularity, freshness, campaign priority, or distance. The base query selects eligible documents; functions add points based on fields, conditions, or formulas. `score_mode` combines functions with each other, while `boost_mode` combines the resulting function score with the base query's score.

In Spring Data Elasticsearch, you can construct `function_score` using `NativeQuery` and the Elasticsearch Java API Client builders. Use filters for mandatory conditions, `function_score` for ranking signals, normalize numeric values, pick suitable modifiers/decays, and keep signal influence bounded. Start with one function, evaluate ordering and latency, and only then add additional signals. The goal is to align results more closely with business needs while preserving strong full-text search quality.
