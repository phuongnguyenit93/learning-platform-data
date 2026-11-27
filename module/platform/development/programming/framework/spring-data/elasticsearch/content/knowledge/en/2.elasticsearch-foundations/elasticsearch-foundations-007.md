# Query context, filter context, and relevance score

When searching in Elasticsearch, a document can be evaluated for two different purposes: determining whether the document satisfies a condition, and determining how well the document matches the search content. Elasticsearch calls these two evaluation modes **filter context** and **query context**.

- **Query context** checks whether a document matches a query while also calculating a *relevance score* for that document.
- **Filter context** only checks whether a document satisfies a condition. Elasticsearch does not calculate a relevance score for filter conditions.

This distinction directly affects result ordering, performance, and how queries are constructed. In a Spring Data Elasticsearch application, these remain the semantics of Elasticsearch Query DSL; Spring Data provides the APIs to build and send the query, while Elasticsearch performs the filtering and scoring.

## 1. Query context: finding matching documents and scoring

Query context is used when the goal is to find documents matching what the user is searching for. Elasticsearch both determines whether a document matches the query and computes a _score value representing relevance.

For example, a user searches for articles about spring data:

    GET articles/_search
    {
      "query": {
        "match": {
          "title": "spring data"
        }
      }
    }

The match query analyzes the input string using the title field's analyzer, then finds matching documents. Matching documents are returned with a _score. By default, search results are typically sorted by _score descending, so documents evaluated as more relevant appear first.

A query in query context answers two questions:

1. Does the document match the search condition?
2. If it matches, how relevant is the document to the query?

Scores are meaningful when comparing documents within the same search result set. They are not probabilities, accuracy percentages, or a fixed scale comparable directly across arbitrary queries.

Query context suits conditions that should influence priority order, such as:

- Full-text search on titles or content.
- Phrase searches or proximity word matching.
- Searching across multiple fields with different weights.
- Boosting documents with better-matching content.

Queries such as match, multi_match, and match_phrase are commonly used in query context to search text content. Other queries can also run in query context; scoring depends on the query type and configured similarity.

## 2. Filter context: checking only whether a document satisfies a condition

Filter context is used when a condition has only a true-or-false meaning. Elasticsearch checks whether the document satisfies the condition without calculating a relevance score for that condition.

For example, an application wants only published articles:

    GET articles/_search
    {
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "status": "PUBLISHED"
              }
            }
          ]
        }
      }
    }

The condition status = PUBLISHED is a filter condition. A published article satisfies it; a draft article does not. There is no business reason for one PUBLISHED article to be considered more relevant than another PUBLISHED article simply because they share the same field value.

Filter context is typically suitable for:

- Statuses: PUBLISHED, DRAFT, ACTIVE.
- Exact categories or identifiers.
- Date ranges and numeric ranges.
- Access permissions or data scopes.
- Other mandatory conditions that do not need to participate in ranking.

Filter conditions are usually combined using AND logic: a document must satisfy all conditions in the filter list to be retained.

Filter context can avoid scoring overhead and create opportunities to leverage Elasticsearch's query cache. However, you should not assume that every filter is automatically cached or always faster than every query. The query cache operates per segment using Elasticsearch heuristics; cacheability depends on query type, usage frequency, and data characteristics.

## 3. Comparing query context and filter context

| Criterion | Query context | Filter context |
|---|---|---|
| Purpose | Find relevant content and evaluate degree of relevance | Check true/false conditions |
| Evaluation result | Match or non-match, accompanied by _score | Match or non-match |
| Relevance scoring | Yes | No |
| Ranking impact | Can alter result order via _score | Does not contribute to relevance score |
| Example | Find titles containing spring data | Retrieve only articles with status = PUBLISHED |
| Typical placement in bool | must, should | filter, must_not |

The two contexts are not two different endpoints or connection modes. They are two execution modes for a query clause depending on where and how the clause is placed.

## 4. Clauses of a bool query

A bool query allows combining multiple conditions. The four most important clauses are must, should, filter, and must_not.

### must

Documents must match all queries in must. Each query in must runs in query context and can contribute to _score.

Example:

    {
      "bool": {
        "must": [
          {
            "match": {
              "title": "spring data"
            }
          }
        ]
      }
    }

The document must match spring data in the title field. How well it matches this query factors into the relevance score.

### should

should contains queries that boost relevance. When a query in should matches, it can contribute additional points to _score.

    {
      "bool": {
        "must": [
          {
            "match": {
              "title": "spring data"
            }
          }
        ],
        "should": [
          {
            "match": {
              "summary": "spring data"
            }
          }
        ]
      }
    }

In this example, the article must match content in title. If summary also matches, the article can receive additional score and rank higher than an article matching only title.

There is a default rule to keep in mind: if a bool query has should without must or filter, by default at least one should condition must match. If must or filter is already present, should becomes optional by default and only contributes score when matched.

You can control this behavior using minimum_should_match:

- minimum_should_match: 1 requires at least one query in should to match.
- minimum_should_match: 2 requires at least two queries in should to match.
- minimum_should_match: 0 allows all queries in should to act purely as score boosters.

When business logic requires at least one optional condition to be true, declare minimum_should_match explicitly instead of relying on the default value.

### filter

Documents must satisfy all queries in filter. These queries run in filter context, are not scored, and do not contribute to _score.

    {
      "bool": {
        "filter": [
          {
            "term": {
              "status": "PUBLISHED"
            }
          },
          {
            "term": {
              "category": "backend"
            }
          }
        ]
      }
    }

The document must have status PUBLISHED and belong to the backend category. These two conditions narrow the result set without deciding which article is more relevant.

### must_not

must_not excludes documents matching the specified queries. Queries in must_not run in filter context, so they do not compute relevance scores.

    {
      "bool": {
        "must_not": [
          {
            "term": {
              "status": "DELETED"
            }
          }
        ]
      }
    }

Documents with status DELETED are excluded from the results. This exclusion condition does not alter the scores of remaining documents.

### Overall view

| Clause | Requirement on document | Context | Contributes to _score_ |
|---|---|---|---|
| must | Must match all queries | Query | Yes |
| should | Optional or required depending on minimum_should_match | Query | Yes |
| filter | Must match all queries | Filter | No |
| must_not | Must not match queries | Filter | No |

## 5. Combining search and filtering in a single query

In real-world applications, users often want to both search for relevant content and restrict results by status, category, or price range. This is where query context and filter context should be combined within the same bool query.

Suppose there is an articles index with the following fields:

| Field | Mapping type | Meaning |
|---|---|---|
| title | text | Title used for full-text search |
| summary | text | Summary text |
| status | keyword | Article status |
| category | keyword | Category |
| price | double | Numeric price value |

The search requirements are:

- The title must match the keywords spring data.
- The article must have status PUBLISHED.
- The article must belong to the backend category.
- The price is between 100 and 1000.
- If the summary also matches spring data, boost its priority.

This can be expressed in Elasticsearch Query DSL:

    GET articles/_search
    {
      "query": {
        "bool": {
          "must": [
            {
              "match": {
                "title": "spring data"
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
                "category": "backend"
              }
            },
            {
              "range": {
                "price": {
                  "gte": 100,
                  "lte": 1000
                }
              }
            }
          ],
          "should": [
            {
              "match": {
                "summary": "spring data"
              }
            }
          ],
          "minimum_should_match": 0
        }
      }
    }

The query has three groups of responsibilities:

1. must determines whether the article matches the primary search keywords while contributing relevance score.
2. filter removes articles not matching the status, category, or price range without scoring these conditions.
3. should boosts articles whose summary matches. minimum_should_match: 0 indicates this condition is optional since the query already has must and filter.

The final results contain only documents satisfying all mandatory conditions. Within that result set, _score reflects the relevance of the queries in query context.

If business rules require the article to match at least one of title or summary, you can place both queries in should, set minimum_should_match: 1, and keep status, category, and price range conditions in filter. Then, at least one of the two fields must match for a document to be returned.

## 6. How is the _score relevance score calculated?

Elasticsearch uses a similarity algorithm to calculate scores for queries running in query context. For text fields, the default similarity is typically **BM25**. BM25 evaluates relevance based on signals such as:

- **Term frequency (TF):** how often a term appears in the document. Multiple occurrences can increase relevance, though the impact is dampened and does not grow linearly without bound.
- **Inverse document frequency (IDF):** terms that are rare across the document collection usually carry more discriminating information than terms appearing in nearly every document.
- **Field length normalization:** field length is factored in; a very long document is not automatically favored merely because it mentions a term more times.

For instance, when searching for elasticsearch, an article focused on Elasticsearch may score higher than a very long document that mentions the word only once. Actual scores also depend on the analyzer, mapping, similarity, query structure, and indexed data.

The _score has several properties:

1. It is a numeric value computed by Elasticsearch for ranking results.
2. Higher values generally indicate a document is more relevant to the current query.
3. Scores generated by multiple clauses in query context can be combined inside a bool query.
4. Clauses in filter context contribute no score.
5. Do not interpret _score = 8 as 80% accuracy, or compare scores across two different queries on the same scale.

When a bool query has multiple scoring clauses, their contributions are combined according to bool query rules. Therefore, adding a matching should clause or changing boost values can alter result ordering.

### Boosting or fixing scores

You can use boost to adjust the influence of a query during scoring. For example, titles can be weighted higher than summaries:

    {
      "bool": {
        "should": [
          {
            "match": {
              "title": {
                "query": "spring data",
                "boost": 3
              }
            }
          },
          {
            "match": {
              "summary": {
                "query": "spring data",
                "boost": 1
              }
            }
          }
        ],
        "minimum_should_match": 1
      }
    }

In the example, title matches rank higher than summary-only matches according to the assigned weights. boost affects score calculation; it does not turn a query into a filter.

If you want a filter condition to still assign a constant score, Elasticsearch provides constant_score:

    {
      "constant_score": {
        "filter": {
          "term": {
            "status": "PUBLISHED"
          }
        },
        "boost": 1.0
      }
    }

This query selects documents with status PUBLISHED using a filter, then assigns a fixed score equal to boost to matching documents. This differs from a normal filter, which contributes no score. Only use it when you specifically want a filter-like condition to participate in ranking with a fixed weight.

## 7. Using query context and filter context in Spring Data Elasticsearch

Spring Data Elasticsearch provides ElasticsearchOperations to execute queries and map results back to entities. For queries combining multiple Elasticsearch clauses, you can use NativeQuery.

Suppose the application has the entity:

    @Document(indexName = "articles")
    public class Article {

        @Id
        private String id;

        @Field(type = FieldType.Text)
        private String title;

        @Field(type = FieldType.Text)
        private String summary;

        @Field(type = FieldType.Keyword)
        private String status;

        @Field(type = FieldType.Keyword)
        private String category;

        @Field(type = FieldType.Double)
        private Double price;

        // constructors, getters and setters
    }

You can build a query searching titles while filtering by status and category:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("title")
                        .query("spring data")
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("status")
                        .value(FieldValue.of("PUBLISHED"))
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of("backend"))
                    )
                )
            )
        )
        .build();

    SearchHits<Article> hits =
        elasticsearchOperations.search(query, Article.class);

must contains a match query, so it executes in query context. The two filter clauses check status and category, so they execute in filter context. Spring Data sends the query through the client layer and maps returned documents into Article instances.

You can read the relevance score from each search hit:

    for (SearchHit<Article> hit : hits) {
        Article article = hit.getContent();
        float score = hit.getScore();

        // Use article and score
    }

SearchHit.getScore() lets the application inspect the score returned by Elasticsearch. When results are constrained solely by filters, scores do not express content relevance differences among documents. If the UI needs content-based ranking, there must be a query running in query context.

Exact API names and builder types depend on the Spring Data Elasticsearch version in use. The example above illustrates the NativeQuery API in modern versions using the Elasticsearch Java Client.

## 8. Choosing query or filter for each condition

A practical rule is to put a condition in query context if it should affect relevance; put it in filter context if it only decides whether a document is allowed in the result set.

| Business condition | Common representation | Reason |
|---|---|---|
| Title must relate to keywords | must + match | Content scoring is needed |
| Secondary content can improve ranking | should + match | Matching adds score |
| Retrieve only published status | filter + term | True/false condition |
| Retrieve only one category | filter + term | No ranking by category needed |
| Price within a range | filter + range | Only restricts the result set |
| Exclude deleted documents | must_not + term | Excludes documents from results |
| Must match one of several fields | should + minimum_should_match | Controls how many conditions must match |

It is not true that term or range queries must always go inside filter context. Context depends on where the query is placed. A query clause can run in query context or filter context depending on how it is nested in the query.

### Notes on field types and queries

Context does not substitute for choosing the right mapping and query type:

- text fields are usually tokenized. Use match when searching analyzed content.
- keyword fields retain values suited for exact matching, filtering, grouping, and aggregations. term is usually suitable here.
- Numeric or date fields can use range to bound intervals.
- Do not use term to search a natural phrase on a text field without understanding the analyzer and actual indexed values.

For example, if status is mapped as keyword, filtering with term for PUBLISHED fits the status condition. If title is text, a match query fits full-text search.

## 9. Common query design mistakes

### Putting every condition in must

If keywords, status, category, and price range are all placed in must, every condition runs in query context. Status or category conditions can then participate in scoring even though business logic does not want that.

Move conditions that only restrict the result set into filter. Keep content search and ranking conditions in must or should.

### Putting mandatory conditions in should and forgetting minimum_should_match

When bool already has must or filter, should defaults to optional. If business rules require at least one should condition to match, set minimum_should_match appropriately.

### Using filter while expecting results ranked by content

Filters only determine whether a document satisfies conditions. If the entire query consists only of filters, there is no relevance signal to rank results by content. Add an appropriate query to query context if ranking is needed.

### Confusing scores with accuracy percentages

_score is a value for relative ordering within a query. It does not represent the probability a document is right or an accuracy percentage. Do not display _score directly to users as an absolute quality metric without a dedicated interpretation model.

### Using term on text fields without considering the analyzer

term looks up an exact term in the inverted index and does not analyze the input string like match. On text fields, data may already have been split into tokens, so the raw string might not match as expected. Use match for full-text search and term for fields with suitable mappings, typically keyword.

### Assuming filters are always cached

Filter context enables Elasticsearch to consider using the query cache, but there is no guarantee every filter is cached. Do not add or split filters purely under the assumption that doing so guarantees a cache hit. Base decisions on query types, data, access frequency, and actual measurements.

## 10. How to read and inspect results

When a query returns results, you can examine _score to understand the ranking order:

    GET articles/_search
    {
      "explain": true,
      "query": {
        "bool": {
          "must": [
            {
              "match": {
                "title": "spring data"
              }
            }
          ],
          "filter": [
            {
              "term": {
                "status": "PUBLISHED"
              }
            }
          ]
        }
      }
    }

explain: true asks Elasticsearch to provide a detailed explanation of how the score was calculated for each hit. This information is helpful when investigating why one document ranked higher than another, though it can enlarge responses and add processing overhead; only enable it when testing or analyzing queries.

When debugging, check in order:

1. Was the target document actually indexed into the right index?
2. Do field mappings match the query types being used?
3. Does the query return the document when individual filter conditions are removed?
4. Are must, should, filter, and must_not clauses placed according to business semantics?
5. Does minimum_should_match turn an optional condition into a required one or vice versa?
6. If the document matches but ranking seems off, inspect analyzers, similarity, boosts, and score explanations via explain.

_score only controls ordering when results are sorted by relevance score. If the application specifies sorting by another field, results will be sorted by that field instead of defaulting to _score.

## Conclusion

Query context and filter context serve two distinct purposes in Elasticsearch. Query context both finds matching documents and computes relevance scores for ranking. Filter context only checks true/false conditions and contributes nothing to scores.

In a bool query, must and should execute in query context; filter and must_not execute in filter context. Real-world search queries typically combine both: use query context for the content users are looking for, and filter context for statuses, categories, dates, numeric ranges, and other constraining conditions.

With Spring Data Elasticsearch, you can express these clauses via NativeQuery and run them with ElasticsearchOperations. Understanding each clause's context helps build queries that match business intent, control result ordering, and avoid scoring conditions meant only for filtering.
