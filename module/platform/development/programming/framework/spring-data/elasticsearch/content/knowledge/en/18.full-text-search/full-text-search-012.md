# Designing Queries Combining Keywords and Business Filters

A search screen in an application typically has to satisfy two requirements at once: finding content matching keywords and narrowing results according to business rules. For example, a user types "mechanical keyboard", then filters by category, price range, brand, stock availability, and update timestamp.

In Elasticsearch, text search is usually built with **match** or **multi_match**. Business conditions such as category, status, price range, and date are placed inside **bool.filter**. Conditions affecting relevance can live in **must** or **should**, while documents to exclude go into **must_not**.

Good design clearly separates which conditions decide whether a document appears at all, which only influence relevance scoring, which fields need analyzers, and which fields need exact matching. This lesson shows how to combine those parts using Query DSL and how to implement them in Spring Data Elasticsearch.

## 1. Separating Keyword Search and Business Filters

Keyword search answers: "Which documents have content relevant to the phrase the user entered?"

Business filters answer: "Among those documents, which ones satisfy the screen's filters or product rules?"

For example, a product catalog entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String brand;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Date)
    private Instant updatedAt;
}
~~~

The user types the keyword "mechanical keyboard", chooses category accessories, sets price from 50 to 150, and views only in-stock products.

Conditions can be categorized as follows:

| Condition | Role | Commonly used query |
|---|---|---|
| Keywords in name/description | Find relevant content | match, multi_match |
| Category | Exact filter | term or terms |
| Brand | Exact filter | term or terms |
| Min/max price | Numeric range filter | range |
| In stock | Boolean filter | term |
| Allowed statuses | Value-set filter | terms |
| Updated timestamp | Date range filter | range |

A useful design rule is to use full-text queries to evaluate content relevance while placing mandatory business constraints in filter context.

## 2. Bool Query Structure

A bool query combines multiple clauses:

- **must**: clause must match and usually participates in scoring.
- **filter**: clause must match but does not contribute to score.
- **should**: matching clause increases score; depending on configuration, it can also be a mandatory condition.
- **must_not**: documents matching the clause are excluded from results.

General structure:

~~~json
{
  "query": {
    "bool": {
      "must": [],
      "filter": [],
      "should": [],
      "must_not": []
    }
  }
}
~~~

You do not need to declare all four arrays. Include only the clauses the use case actually needs.

### Why does filter fit business conditions?

Filter context checks whether a document satisfies a condition without computing a relevance score for it. Category, brand, boolean flags, status, and price ranges generally do not need scoring. A product with the right category does not need to be considered more relevant than another solely because the category value matched.

Filters also suit conditions that Elasticsearch can optimize and cache internally. Do not take this to mean every filter is guaranteed to be cached; caching depends on the query, data, and cluster state.

### When to use must?

Use must when a text condition must both match obligatorily and participate in relevance scoring. For example, the user's phrase must appear in the name or description per full-text query semantics.

If a query has only filters and no scoring part, results can still be ordered by field sorting. When relevance ordering is needed, place full-text clauses in must or configure appropriate scoring.

## 3. Basic Query Combining Keywords and Filters

Complete Query DSL example:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "mechanical keyboard",
            "fields": [
              "name^3",
              "description"
            ],
            "type": "best_fields"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "term": {
            "available": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 50,
              "lte": 150
            }
          }
        }
      ]
    }
  }
}
~~~

This query does three things:

1. Finds products whose content relates to "mechanical keyboard".
2. Prioritizes matches in name over description thanks to boost 3.
3. Keeps only products in category accessories, available, and priced between 50 and 150.

Boost only adjusts relative score within the query. name^3 does not mean a name match is guaranteed to rank linearly three times higher in every situation.

Because name and description are text fields, analyzers process the keywords. Because category is keyword, term matches the exact indexed value.

## 4. Choosing match, multi_match, and match_phrase

### match for a single field

Use match when keywords only need to search one field:

~~~json
{
  "match": {
    "name": {
      "query": "mechanical keyboard",
      "operator": "and"
    }
  }
}
~~~

operator and requires analyzed tokens to satisfy the field condition per match query semantics. If operator is omitted, the default is usually OR. Pick AND or OR based on the desired search experience.

### multi_match for multiple fields

Use multi_match when the same phrase needs to search across multiple fields:

~~~json
{
  "multi_match": {
    "query": "mechanical keyboard",
    "fields": [
      "name^3",
      "description",
      "brand^2"
    ],
    "type": "best_fields"
  }
}
~~~

You can boost each field to express relative importance. For instance, product name matters more than description; brand may matter more than part of the description text.

Different multi_match types have distinct semantics:

- **best_fields**: takes the best match across fields, fitting when a single field can contain most of the query.
- **most_fields**: combines scores across fields, useful when data is analyzed multiple ways or stored across multi-fields.
- **cross_fields**: treats fields as parts of the same content, fitting patterns like first and last name.
- **phrase** and **phrase_prefix**: searches phrases or prefixes per their respective semantics.

Do not pick a type by name alone. Verify analyzers, data, and how scores are computed in your use case.

### match_phrase for phrases

If users need words to appear close together in order, use match_phrase:

~~~json
{
  "match_phrase": {
    "name": {
      "query": "mechanical keyboard"
    }
  }
}
~~~

match_phrase is usually stricter than match. It works well for product names, titles, or phrases whose word order is meaningful. If non-adjacent words should still match, consider match or slop, or another query type.

## 5. Designing Filters Around Field Mappings

Exact queries depend on mappings. Do not use the same query type for every field.

### Keyword fields

Fields such as category, brand, status, and SKU are usually mapped as keyword:

~~~java
@Field(type = FieldType.Keyword)
private String category;
~~~

Use term for a single value:

~~~json
{
  "term": {
    "category": "accessories"
  }
}
~~~

Use terms for multiple values:

~~~json
{
  "terms": {
    "category": [
      "accessories",
      "office"
    ]
  }
}
~~~

terms has OR semantics across values: a document only needs to match one value in the list.

### Text fields and keyword subfields

A name may need both full-text search and exact filtering/sorting:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Then:

- Search name content with match on name.
- Filter or sort exactly on name.keyword if the mapping defines that subfield.

Do not use term on an analyzed text field when the goal is exact whole-string matching. Term queries operate on indexed terms and do not run the analyzer like match queries.

### Numeric and date fields

Prices, quantities, ratings, and timestamps are usually filtered with range:

~~~json
{
  "range": {
    "price": {
      "gte": 50,
      "lt": 150
    }
  }
}
~~~

You can use gt, gte, lt, and lte. Pick inclusive/exclusive boundaries per business rules. Half-open intervals gte + lt are often convenient when splitting adjacent buckets.

### Boolean fields

Boolean filters use term:

~~~json
{
  "term": {
    "available": true
  }
}
~~~

Booleans must be literal true or false, not the string "true".

## 6. Handling Optional Filters

Search screens often have many optional filters. A user may enter only keywords, or enter keywords and pick category, brand, and price range.

Do not build a fixed query where every filter is mandatory if inputs can be absent. Define the semantics of each state clearly:

| Input | Suggested behavior |
|---|---|
| Null or blank keyword | Omit full-text query or require keyword, depending on product |
| Null category | Omit category filter |
| Empty brand list | Omit brand filter if empty means unselected |
| Null min price | No lower bound |
| Null max price | No upper bound |
| Null available | Do not filter by stock availability |
| False available | Include only out-of-stock documents |
| Empty status list | Per policy: omit filter or return no results |

The key point is that false differs from null, and an empty collection does not automatically mean omitting a filter.

### Query DSL example with optional filters

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "mechanical keyboard",
            "fields": ["name^3", "description"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  }
}
~~~

When the user does not pick a brand, do not add a brand clause to filter. When minPrice is not entered, omit the lower bound. The final query contains only active conditions.

### Do not mechanically substitute match_all for optional filters

If the keyword is empty, the application may drop must and keep only filter. You can build a query with just bool.filter. If both keyword and filters are absent, decide whether to allow browsing the entire catalog or require at least one condition.

Returning every document on an empty form can generate very broad requests. Enforce page size caps and search rules tailored to the product.

## 7. Combining must, filter, should, and must_not

A realistic query may require all four clause types:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless keyboard",
            "fields": ["name^3", "description"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "available": true
          }
        },
        {
          "terms": {
            "category": ["accessories", "computer"]
          }
        },
        {
          "range": {
            "price": {
              "gte": 30,
              "lte": 200
            }
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": {
              "value": "KeyPro",
              "boost": 2
            }
          }
        },
        {
          "match": {
            "description": "wireless"
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "status": "DISCONTINUED"
          }
        }
      ]
    }
  }
}
~~~

Here:

- must requires content matches and computes score.
- filter applies mandatory business constraints.
- should boosts score for preferred brands or better-matching descriptions.
- must_not excludes discontinued products.

### Is should mandatory or only score-boosting?

This point deserves careful attention. In a bool query containing must or filter, should clauses are usually optional by default; they only boost score. If a bool query lacks must and filter, the default typically requires at least one should to match.

To control this explicitly, set minimum_should_match:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "keyboard"
        }
      }
    ],
    "should": [
      {
        "term": {
          "brand": "KeyPro"
        }
      },
      {
        "term": {
          "category": "accessories"
        }
      }
    ],
    "minimum_should_match": 1
  }
}
~~~

In this example, besides matching product name, at least one of the two should conditions must match. If the intent is purely to boost preferred results, omit minimum_should_match or set it according to requirements.

### When to use must_not?

Use must_not for exclusion conditions such as:

- Deleted or discontinued statuses.
- Products hidden from the catalog.
- A disallowed category.
- Documents with forbidden fields or values.

Do not push every exclusion into must_not when it is actually an allowlist filter. For instance, allowing only status ACTIVE or BACKORDER is more clearly expressed with terms in filter.

## 8. Searching Multiple Fields and Prioritizing Fields

A query often searches across multiple fields with varying importance. Use boost to adjust each field's impact:

~~~json
{
  "multi_match": {
    "query": "wireless keyboard",
    "fields": [
      "name^4",
      "brand^2",
      "description"
    ],
    "type": "best_fields"
  }
}
~~~

Product name gets highest priority, brand gets intermediate priority, and description acts as a supporting field.

Boost is not a fixed sort order. A document with a boosted field can still rank lower if other query terms and content give another document a higher total score. If business rules require hard prioritization—such as featured products always appearing first—consider sorting by field or using function_score rather than relying solely on boost.

### Multi-fields and analyzers

A field can be indexed in multiple ways:

- name as text with a standard analyzer for full-text search.
- name.keyword as keyword for sorting or exact filtering.
- A lowercase subfield or custom analyzer for specialized search needs.

Queries must target the right field for each purpose. Do not use a keyword field for long natural-language queries when you expect the analyzer to tokenize words.

## 9. Filtering by Price and Time Ranges

Range filters often have two bounds. Example:

~~~json
{
  "range": {
    "price": {
      "gte": 50,
      "lte": 150
    }
  }
}
~~~

If only minPrice is present:

~~~json
{
  "range": {
    "price": {
      "gte": 50
    }
  }
}
~~~

If only maxPrice is present:

~~~json
{
  "range": {
    "price": {
      "lte": 150
    }
  }
}
~~~

If neither is present, omit the range filter.

For dates/times, normalize time zones and use ISO 8601:

~~~json
{
  "range": {
    "updatedAt": {
      "gte": "2026-01-01T00:00:00Z",
      "lt": "2026-02-01T00:00:00Z"
    }
  }
}
~~~

The range from the start of January to the start of February includes instants within January and excludes the exact start of February. When inputs are local dates, the service should convert boundaries to a unified time zone before building the query.

## 10. Sorting Results After Combining Keywords and Filters

When a full-text query is present, Elasticsearch typically sorts by descending `_score` unless another sort is specified. Adding a field sort can make relevance no longer the primary ordering criterion.

Example sorting by relevance then price:

~~~json
{
  "sort": [
    { "_score": "desc" },
    { "price": "asc" }
  ]
}
~~~

Example sorting by price first, then relevance:

~~~json
{
  "sort": [
    { "price": "asc" },
    { "_score": "desc" }
  ]
}
~~~

These two requirements produce different user experiences. If the user chooses "price low to high", prioritize price. If the user chooses "most relevant", prioritize `_score`.

For text fields, sort on a keyword subfield rather than the text field. For dynamic sorting, enforce an allowlist of valid field names and directions; never inject raw field names from arbitrary user input into Query DSL.

## 11. Pagination and Result Limits

Search results should cap the number of returned documents. For standard pagination, use from and size, or Pageable in Spring Data:

~~~json
{
  "from": 0,
  "size": 20,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "available": true
          }
        }
      ]
    }
  }
}
~~~

Never let clients send arbitrarily huge page sizes. Enforce a maximum page size at the API layer.

For large result sets and deep pagination, consider search_after with a stable sort and Point in Time (PIT) if a consistent view is required. Keep the sort values of the last hit on the previous page as the cursor. Do not reconstruct cursors manually from entity fields when you can use the sort values returned directly by Elasticsearch.

## 12. Implementing in Spring Data Elasticsearch with `@Query`

If query structure is fixed, repository methods can use `@Query`:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "bool": {
            "must": [
              {
                "multi_match": {
                  "query": "?0",
                  "fields": ["name^3", "description"]
                }
              }
            ],
            "filter": [
              {
                "term": {
                  "available": true
                }
              },
              {
                "term": {
                  "category": "?1"
                }
              },
              {
                "range": {
                  "price": {
                    "gte": ?2,
                    "lte": ?3
                  }
                }
              }
            ]
          }
        }
        """)
    List<Product> searchCatalog(
        String keyword,
        String category,
        Double minPrice,
        Double maxPrice
    );
}
~~~

This method illustrates a query with a fixed structure: keyword, category, and both price bounds are mandatory. If category or prices can be absent, do not pass null into placeholders expecting clauses to vanish automatically.

`@Query` fits when queries have few variants, are concise, and are easy to test. As the number of optional filters grows, method annotations become harder to maintain.

## 13. Building Dynamic Queries with ElasticsearchOperations

For optional filters, use ElasticsearchOperations to construct queries from runtime inputs. CriteriaQuery fits simple conditions; NativeQuery fits when detailed Query DSL control is needed.

Example service structure:

~~~java
public SearchHits<Product> search(ProductSearchCriteria criteria) {
    // Add full-text clause if keyword has content.
    // Add category filter if category is selected.
    // Add brand terms filter if brand list is non-empty.
    // Add range filter for minPrice/maxPrice when values are present.
    // Add boolean filter if available is non-null.
    // Combine clauses into a bool query and call operations.search(...).
}
~~~

A simple Criteria query can be built condition by condition:

~~~java
Criteria criteria = new Criteria();

if (criteriaInput.category() != null) {
    criteria.and("category").is(criteriaInput.category());
}

if (criteriaInput.minPrice() != null) {
    criteria.and("price")
        .greaterThanEqual(criteriaInput.minPrice());
}

if (criteriaInput.maxPrice() != null) {
    criteria.and("price")
        .lessThanEqual(criteriaInput.maxPrice());
}

Query query = new CriteriaQuery(criteria);
SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

This snippet shows how to build dynamic filters with Criteria. For multi-field full-text queries, boosts, nested queries, or complex bool branches, NativeQuery is usually more suitable. Builder syntax varies across Spring Data Elasticsearch and Elasticsearch Java API Client versions, so use the API matching your project's dependencies.

### Separating SearchCriteria from Query DSL

Do not expose raw JSON Query DSL in controllers. Create an input object representing business criteria:

~~~java
public record ProductSearchCriteria(
    String keyword,
    String category,
    List<String> brands,
    Double minPrice,
    Double maxPrice,
    Boolean available,
    int page,
    int size
) {}
~~~

The service is responsible for:

1. Validating inputs.
2. Normalizing keywords and values.
3. Deciding which filters apply.
4. Selecting valid sorting and pagination.
5. Building the query.
6. Executing via Operations.
7. Mapping results to appropriate DTOs.

This structure keeps controllers and the domain independent of Query DSL details.

## 14. Designing Condition Ordering and Scoring

A query combining keywords and filters should have a clear scoring rule.

Example:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "gaming keyboard",
            "fields": ["name^4", "description", "brand^2"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "available": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 40,
              "lte": 250
            }
          }
        }
      ],
      "should": [
        {
          "term": {
            "featured": {
              "value": true,
              "boost": 1.5
            }
          }
        }
      ]
    }
  }
}
~~~

In-stock status and price range are mandatory conditions. Featured status only boosts score and is not mandatory. Therefore, non-featured products can still appear if they match the keyword and filters.

If the requirement is to show only featured products, move that condition into filter. If the requirement is that at least one of several preference conditions must match, configure minimum_should_match.

Do not use should when the business rule is mandatory without configuring it explicitly. That is a frequent reason queries return documents that appear to violate constraints.

## 15. Optimization and Common Design Mistakes

### Putting all conditions in must

If category, price, and available are all placed in must, they can participate in scoring unnecessarily. Using filter for business constraints makes the query express its intent clearly.

### Using term on text fields

Text fields are tokenized into tokens by analyzers. term does not analyze the query string like match. For exact filters, use keyword fields; for full-text, use match.

### Using should while forgetting minimum_should_match

When a bool query has must/filter, should can act merely as a score-boosting clause. If one of the shoulds must match, set minimum_should_match.

### Using wildcards for natural keywords

Wildcards do not replace full-text search. Use match or multi_match for natural text. Wildcards are only for suitable patterns and require bounding their breadth.

### Adding empty or null filters

Do not build terms from empty collections or ranges with null bounds without defining semantics. Construct queries from active conditions.

### Sorting wiping out relevance priority

If you sort solely by price, results may no longer be ordered by score. Decide the priority order between relevance and business sorting before implementing.

### Overly broad queries when keyword is blank

If both keyword and filters are absent, the query can return almost the entire index. Define clear policies for empty searches, page sizes, and result limits.

## 16. Testing Combined Queries

Test queries against data representing every condition branch:

- Keyword matches name but not description.
- Keyword matches only description.
- Matching and non-matching category.
- Brand inside and outside the list.
- Price inside range, on boundaries, and outside range.
- Available true, false, and null/missing per mapping.
- Status excluded by must_not.
- Document matching only should while failing must/filter.
- Blank keyword and empty collection filters.
- Multiple documents with close scores and identical sort field values.

An integration test should assert both the result set and ordering:

~~~java
@Test
void combinesKeywordAndBusinessFilters() {
    // Index products with varying names, categories, prices, and availability.
    // Build query for keyword "mechanical keyboard".
    // Apply category accessories, price range, and available=true.
    // Execute search.
    // Verify only documents satisfying filters are returned.
    // Verify score/sort order matches requirements.
}
~~~

This is a test skeleton. Test setup and index creation depend on your Spring Data Elasticsearch version and project Elasticsearch environment. Tests should use mappings compatible with production because analyzers and field types directly affect results.

When diagnosing scores, you can enable explain in development to inspect which clauses contribute points. Do not enable explain for every production request due to large responses and added processing cost.

## 17. Search Query Design Checklist

- [ ] Keywords are searched on appropriate text fields using match or multi_match.
- [ ] Fields needing exact matching are mapped as keyword.
- [ ] Mandatory business constraints are placed in filter.
- [ ] Relevance-affecting conditions are deliberately placed in must/should.
- [ ] must_not contains only genuine exclusion conditions.
- [ ] should defines minimum_should_match if matching is mandatory.
- [ ] Optional filters are added only when inputs have values.
- [ ] false is distinguished from null for nullable Booleans.
- [ ] Empty collections have clear semantics.
- [ ] Numeric and date intervals use proper inclusive/exclusive boundaries.
- [ ] Sorting does not accidentally override relevance priority.
- [ ] Pagination and page sizes are bounded.
- [ ] Dynamic field names are selected from an allowlist.
- [ ] Queries are integration-tested against real mappings and data.

A well-designed search query combines two clear layers: the full-text layer identifies relevant content and scoring, while the filter layer restricts results according to business rules. When must, filter, should, and must_not are used accurately and query types match field mappings, applications deliver flexible search experiences that remain accurate and maintainable.
