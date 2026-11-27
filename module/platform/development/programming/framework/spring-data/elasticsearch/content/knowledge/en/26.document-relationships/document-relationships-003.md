# Nested Queries, Score Modes, and Inner Hits

When a document contains an array of objects, an application sometimes needs to evaluate multiple conditions against the same element. For example, a product has multiple offers from different sellers; a query needs to find products that have an offer from `SELLER-A` priced under 100 and currently in stock. If the mapping and query do not preserve the relationship between fields within each element, Elasticsearch can combine conditions from two different offers and return the wrong product.

`nested` is the mechanism for indexing and querying sub-objects as nested documents, preserving the relationships between fields within the same element. A `nested` query finds parent documents that have at least one matching nested document. `score_mode` determines how the scores of matching nested documents are combined into the parent document's score. `inner_hits` lets you retrieve the exact nested documents that matched so the application can display or process them.

These three concepts solve three related but distinct problems: preserving data relationships, aggregating ranking scores, and returning matching child elements.

## 1. Why is Nested mapping needed?

### 1.1. Standard object arrays can lose field relationships

Suppose a product has two offers:

~~~json
{
  "productId": "P1001",
  "name": "Wireless Keyboard",
  "offers": [
    {
      "seller": "SELLER-A",
      "price": 150,
      "available": true
    },
    {
      "seller": "SELLER-B",
      "price": 80,
      "available": false
    }
  ]
}
~~~

The business needs to find products with an offer from `SELLER-A`, priced at no more than 100, and in stock. Neither offer in the example meets all three conditions:

- `SELLER-A`'s offer is priced at 150.
- The offer priced at 80 belongs to `SELLER-B` and is out of stock.

If `offers` is mapped as a regular `object`, Elasticsearch flattens the object array's values into multi-valued fields. The relationship between the values of each individual object is no longer preserved in the way required for same-element queries.

In that case, a `bool` query can see `seller = SELLER-A`, `price <= 100`, and `available = true` all appearing somewhere in the document and return the product. This is a false positive because the conditions actually belong to different elements.

### 1.2. Nested creates a separate Lucene document for each sub-object

When a field is mapped as `nested`, each object in the array is indexed as a separate nested document linked to the parent document.

| Nested offer | Seller | Price | Available |
|---|---|---:|---|
| Offer 1 | SELLER-A | 150 | true |
| Offer 2 | SELLER-B | 80 | false |

A `nested` query can require all conditions to match on a single nested document. Because no offer matches all conditions, product `P1001` will not be returned.

Nested documents are not independent documents that an application can update individually like root documents. They are stored and queried in relation to the parent document.

### 1.3. When to use object and when to use nested?

| Need | Appropriate mapping |
|---|---|
| Store sub-fields without needing to preserve per-array-element relationships | `object` |
| Require multiple conditions to match on the same object in an array | `nested` |
| Query and retrieve the exact matching sub-objects | `nested` combined with `inner_hits` |
| Child data has an independent lifecycle, updates, and queries | Consider a separate index or parent-child |

`nested` has higher overhead than regular `object` because each nested object creates an additional hidden Lucene document. You should not convert every object array to `nested` if the application does not need these semantics.

## 2. Declaring Nested mapping in Spring Data Elasticsearch

### 2.1. Java model

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String productId;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Nested)
    private List<OfferDocument> offers = new ArrayList<>();
}

public class OfferDocument {

    @Field(type = FieldType.Keyword)
    private String seller;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private boolean available;
}
~~~

The key point is that the `offers` field is declared with `FieldType.Nested`. If you use `FieldType.Object`, Spring Data will create a standard `object` mapping and queries will not have nested semantics.

Annotation names, packages, and field declaration styles may vary across Spring Data Elasticsearch versions. Verify the API of the dependency version you are using.

### 2.2. Corresponding JSON mapping

~~~json
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "offers": {
        "type": "nested",
        "properties": {
          "seller": {
            "type": "keyword"
          },
          "price": {
            "type": "double"
          },
          "available": {
            "type": "boolean"
          }
        }
      }
    }
  }
}
~~~

The nested path is `offers`. Fields inside the nested object are referenced using paths such as `offers.seller`, `offers.price`, and `offers.available`.

The mapping must be created properly before indexing data. If the field has already been created as `object`, you cannot simply change the Java annotation and expect the existing mapping to switch to `nested` automatically. Typically, you need to create a new index with the proper mapping and reindex the data.

### 2.3. Checking the actual mapping

You can use the mapping API:

~~~http
GET /products/_mapping
~~~

Locate the `offers` field and verify that `type` is `nested`. Do not rely solely on the Java entity because the index may already exist with an old mapping or have been created by another pipeline.

When an application runs through an alias spanning multiple indexes, ensure all indexes have compatible mappings. If one index declares `offers` as `object` while another declares it as `nested`, the same query may fail or produce inconsistent results.

## 3. Basic Nested queries

### 3.1. Query structure

A `nested` query has these main components:

- `path`: path to the nested field.
- `query`: the query executed against nested documents.
- `score_mode`: how scores of matching nested documents are combined.
- `inner_hits`: optional configuration to retrieve matching nested documents in the response.

Example finding products that have an offer from Seller A:

~~~json
{
  "query": {
    "nested": {
      "path": "offers",
      "query": {
        "term": {
          "offers.seller": "SELLER-A"
        }
      }
    }
  }
}
~~~

`path` must point to a field mapped as `nested`. Fields inside the query still use their full dotted path, such as `offers.seller`.

A `nested` query returns the parent document if at least one nested document matches. It does not turn nested documents into root hits on its own.

### 3.2. Combining multiple conditions on the same nested object

Complete query for the offer example:

~~~json
{
  "query": {
    "nested": {
      "path": "offers",
      "query": {
        "bool": {
          "must": [
            {
              "term": {
                "offers.seller": "SELLER-A"
              }
            },
            {
              "range": {
                "offers.price": {
                  "lte": 100
                }
              }
            },
            {
              "term": {
                "offers.available": true
              }
            }
          ]
        }
      }
    }
  }
}
~~~

The `seller`, `price`, and `available` conditions sit inside the same `nested` query. Elasticsearch evaluates the `bool` query on each nested document individually, so all conditions must match on the same offer.

### 3.3. Mistake: splitting conditions into separate nested queries

The following example can return a product if one nested object satisfies `seller` and a different nested object satisfies `price`:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "nested": {
            "path": "offers",
            "query": {
              "term": {
                "offers.seller": "SELLER-A"
              }
            }
          }
        },
        {
          "nested": {
            "path": "offers",
            "query": {
              "range": {
                "offers.price": {
                  "lte": 100
                }
              }
            }
          }
        }
      ]
    }
  }
}
~~~

Each independent `nested` query only needs to find one matching nested document. The two `nested` queries can match two different offers.

If business logic requires the same offer to belong to Seller A and have a price of at most 100, place both conditions inside a single `nested` query and the same inner `bool`.

### 3.4. Combining root and nested conditions

You can combine conditions on the parent document with a `nested` query:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        },
        {
          "nested": {
            "path": "offers",
            "query": {
              "bool": {
                "must": [
                  {
                    "term": {
                      "offers.seller": "SELLER-A"
                    }
                  },
                  {
                    "range": {
                      "offers.price": {
                        "lte": 100
                      }
                    }
                  }
                ]
              }
            }
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
  }
}
~~~

The product name is searched on the root document, `seller`/`price` conditions are checked on a single nested offer, and `active` is a filter condition on the parent document.

### 3.5. Multi-level nested paths

If a nested object itself contains a nested array, the query must use the proper full nested path, such as `orders.items` or `comments.replies`, depending on the mapping.

Elasticsearch supports multi-level nested queries and can resolve nested contexts according to query structure. However, declaring paths explicitly keeps code readable and reduces confusion with multiple nested levels.

## 4. Bool logic inside Nested queries

### 4.1. must, filter, should, and must_not

A `nested` query accepts standard query clauses:

- `must`: the nested document must match and contributes to scoring.
- `filter`: the nested document must satisfy the condition without contributing to relevance score.
- `should`: boosts the nested document or must match depending on `minimum_should_match`.
- `must_not`: excludes nested documents matching the condition.

For example, Seller A must be in stock, while preferring lower-priced offers:

~~~json
{
  "nested": {
    "path": "offers",
    "query": {
      "bool": {
        "filter": [
          {
            "term": {
              "offers.seller": "SELLER-A"
            }
          },
          {
            "term": {
              "offers.available": true
            }
          }
        ],
        "should": [
          {
            "range": {
              "offers.price": {
                "lte": 100
              }
            }
          }
        ],
        "minimum_should_match": 0
      }
    }
  }
}
~~~

`seller` and `available` filter candidate nested documents. `should` can contribute score if the query runs in a scoring context. If price must strictly not exceed 100, move the `range` into `filter` or `must`.

### 4.2. minimum_should_match

When a `bool` query has `must` or `filter`, `should` clauses are usually optional by default. If there is no `must`/`filter`, at least one `should` clause typically must match.

Set `minimum_should_match` explicitly when business logic depends on how many `should` conditions must be satisfied. This prevents query semantics from shifting when clauses are added or removed.

### 4.3. must_not and negation semantics

If you need products that have no offers from Seller A, place the `nested` query inside `must_not` at the root level:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "nested": {
            "path": "offers",
            "query": {
              "term": {
                "offers.seller": "SELLER-A"
              }
            }
          }
        }
      ]
    }
  }
}
~~~

This query excludes the parent document if at least one nested offer from Seller A exists.

Negating inside the `nested` query means something different. A `nested` query with `must_not seller=A` can match a non-Seller-A offer even if the product still has a Seller A offer. If you mean "no Seller A offer exists at all," put a positive `nested` query inside a root-level `must_not`.

## 5. Score mode in Nested queries

### 5.1. Why is score_mode needed?

A parent document can have multiple matching nested documents. Each nested document can produce its own score. Elasticsearch needs a rule to combine those scores into the parent document's score.

`score_mode` determines how scores of matching nested documents are combined:

| score_mode | Aggregation method |
|---|---|
| `avg` | Average score of matching nested documents |
| `max` | Highest score |
| `min` | Lowest score |
| `sum` | Sum of scores of matching nested documents |
| `none` | Do not include nested document scores in the parent score |

If omitted, a `nested` query typically uses `avg`. Check the documentation for your Elasticsearch version if you rely on the default in a ranking contract.

### 5.2. avg: average score

`avg` takes the mean score of matching nested documents.

For example, a product has three matching offers with scores 2, 4, and 6:

\[
parentScore = \frac{2 + 4 + 6}{3} = 4
\]

This mode reduces the impact of how many nested documents matched. A product with many offers does not automatically get a higher total score just for having more offers.

### 5.3. max: taking the best nested match

`max` selects the highest score among matching nested documents. With scores 2, 4, and 6, the parent score is 6.

This mode fits when only the single best nested item should determine the parent document's relevance. For example, a product with one highly relevant offer can rank high even if its other offers are poor.

### 5.4. min: taking the lowest nested score

`min` selects the lowest score among matching nested documents. With scores 2, 4, and 6, the parent score is 2.

This option is less common in standard ranking, but can fit when business rules want to evaluate the parent document by its lowest-scoring nested match among the matching group.

### 5.5. sum: summing scores of nested matches

`sum` adds up the scores of all matching nested documents. With scores 2, 4, and 6, the parent score is 12.

This mode lets the number of nested matches strongly influence ordering. A product with many matching offers can score higher than one with a single offer, even if individual offer scores are similar.

Only use `sum` when the count of nested matches is genuinely a desired business signal. Otherwise, a document with many repeated elements can be boosted unintentionally.

### 5.6. none: ignoring nested scores

`none` does not pass nested document scores into the parent document's score. This mode fits when the `nested` query only checks whether the parent document satisfies a condition without letting nested relevance affect ranking.

If the `nested` query sits inside a `bool` `filter`, scores are already unused for ranking, so `score_mode` typically makes no meaningful difference to the final result. You can set `none` to make intent explicit.

### 5.7. Illustrating score modes

Suppose three matching nested documents have scores 2, 4, 6:

| Mode | Parent score |
|---|---:|
| avg | 4 |
| max | 6 |
| min | 2 |
| sum | 12 |
| none | Nested score not used |

This is a simplified illustration. Actual Elasticsearch scores depend on the query, similarity model, and other scoring factors.

### 5.8. Declaring score_mode in DSL

Example prioritizing the highest-scoring nested offer:

~~~json
{
  "nested": {
    "path": "offers",
    "score_mode": "max",
    "query": {
      "bool": {
        "must": [
          {
            "term": {
              "offers.seller": "SELLER-A"
            }
          },
          {
            "match": {
              "offers.description": "fast delivery"
            }
          }
        ]
      }
    }
  }
}
~~~

This query finds products with an offer from Seller A with a matching description. If multiple offers match, the best offer's score is used as the product's score.

### 5.9. score_mode and outer query boost

`score_mode` only determines how scores from nested matches are combined. The parent document's final score can also be affected by other clauses in the `bool` query, query boosts, and outer scoring functions.

Do not treat `score_mode` `max` as the final score of the entire search response. It only controls the nested query's contribution.

## 6. Scoring context and filter context

### 6.1. Nested query in must

If a `nested` query sits in `must` or another scoring clause, the nested score can contribute to the parent document's score.

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "nested": {
            "path": "offers",
            "score_mode": "max",
            "query": {
              "match": {
                "offers.description": "fast delivery"
              }
            }
          }
        }
      ]
    }
  }
}
~~~

The score of the best nested match influences product ordering.

### 6.2. Nested query in filter

If you only need to check that a qualifying offer exists:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "nested": {
            "path": "offers",
            "query": {
              "term": {
                "offers.available": true
              }
            },
            "score_mode": "none"
          }
        }
      ]
    }
  }
}
~~~

Filter context does not compute relevance scores for that condition. This is usually the right choice when the `nested` query is purely a business filter.

### 6.3. Separating filter conditions and ranking conditions

You can use a nested `filter` to ensure an in-stock offer exists, and a separate nested scoring query to rank by offer description:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "nested": {
            "path": "offers",
            "score_mode": "none",
            "query": {
              "term": {
                "offers.available": true
              }
            }
          }
        }
      ],
      "must": [
        {
          "nested": {
            "path": "offers",
            "score_mode": "max",
            "query": {
              "match": {
                "offers.description": "fast delivery"
              }
            }
          }
        }
      ]
    }
  }
}
~~~

Be careful: these two `nested` queries can match two different offers. If you require the same offer to be both `available` and have a matching description, put both conditions in the same `nested` query. Only split them into two queries when the business allows two different nested items to satisfy them.

## 7. Inner hits: retrieving matching nested documents

### 7.1. Nested queries only return parent documents

A standard `nested` query returns matching root documents. The `offers` field in `_source` can still contain all of the product's offers, including ones that did not match the `nested` query.

If the UI needs to display exactly which offer caused the product to be selected, you need `inner_hits`.

### 7.2. inner_hits structure

You can add `inner_hits` to a `nested` query:

~~~json
{
  "query": {
    "nested": {
      "path": "offers",
      "query": {
        "bool": {
          "must": [
            {
              "term": {
                "offers.seller": "SELLER-A"
              }
            },
            {
              "range": {
                "offers.price": {
                  "lte": 100
                }
              }
            }
          ]
        }
      },
      "inner_hits": {
        "name": "matching_offers",
        "size": 5
      }
    }
  }
}
~~~

Elasticsearch returns parent documents in `hits.hits` and groups nested matches inside `inner_hits` on each parent hit. The name `matching_offers` helps distinguish groups when a query has multiple inner-hit definitions.

`inner_hits` contains only nested documents that matched the corresponding `nested` query, not the entire nested array.

### 7.3. Response with inner hits

Conceptual response:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "P1001",
        "_source": {
          "productId": "P1001",
          "name": "Wireless Keyboard",
          "offers": [
            {
              "seller": "SELLER-A",
              "price": 150,
              "available": true
            },
            {
              "seller": "SELLER-B",
              "price": 80,
              "available": false
            },
            {
              "seller": "SELLER-A",
              "price": 90,
              "available": true
            }
          ]
        },
        "inner_hits": {
          "matching_offers": {
            "hits": {
              "hits": [
                {
                  "_nested": {
                    "field": "offers",
                    "offset": 2
                  },
                  "_source": {
                    "seller": "SELLER-A",
                    "price": 90,
                    "available": true
                  }
                }
              ]
            }
          }
        }
      }
    ]
  }
}
~~~

This is an illustrative structure. Actual `offset` and `_source` values correspond to real data. The takeaway is that the root `_source` can still hold the full array, whereas `inner_hits` provides the matching nested items separately.

### 7.4. Inner hits do not create independent document IDs

Nested objects do not have independent `_id`s like root documents. Elasticsearch uses nested metadata, such as field path and array `offset`, to indicate the nested object's position inside the parent.

The `offset` can change if the array is updated or reordered. If the application needs a stable identifier for an offer, store a business key such as `offerId` inside the nested object and return that field via `inner_hits`.

Do not use `offset` as a long-term ID or business key.

### 7.5. Inner hits have a default limit

`inner_hits` limits how many nested documents are returned per parent. If unconfigured, the default is typically small (often 3) nested hits. Declare `size` explicitly according to UI needs and check the default for your Elasticsearch version.

A query returning 20 parent hits with 100 inner hits each can produce thousands of nested items in the response. Limit parent hits, inner hit `size`, and returned fields.

## 8. Customizing inner_hits

### 8.1. Sorting nested matches

You can sort inner hits independently:

~~~json
{
  "inner_hits": {
    "name": "matching_offers",
    "size": 5,
    "sort": [
      {
        "offers.price": {
          "order": "asc"
        }
      }
    ]
  }
}
~~~

In this example, matching offers are sorted by ascending price. Sorting inside `inner_hits` only sorts nested results within each parent. It does not sort the parent products themselves.

### 8.2. Paginating inner hits

`inner_hits` supports `from` and `size` to fetch a slice of matching nested items per parent:

~~~json
{
  "inner_hits": {
    "name": "matching_offers",
    "from": 0,
    "size": 10
  }
}
~~~

These options apply to the inner hits of each parent hit, so total response elements can grow quickly when many parents are returned.

Elasticsearch enforces `index.max_inner_result_window` on the inner result window. Check your cluster configuration and avoid raising the limit just to return an excessively large volume of nested data.

### 8.3. Fetching only required fields

You can restrict the `_source` of inner hits:

~~~json
{
  "inner_hits": {
    "name": "matching_offers",
    "size": 5,
    "_source": {
      "includes": [
        "offers.seller",
        "offers.price",
        "offers.available"
      ]
    }
  }
}
~~~

Depending on version and nested context, an inner hit's `_source` may be represented as a fragment of the nested object. Verify the actual response and mapping converter before mapping to a DTO.

If you only need a few scalar fields, you can consider `docvalue_fields` for fields that support doc values. Source filtering and doc values have different semantics; choose based on data types and how the application consumes the results.

### 8.4. Highlighting inner hits

`inner_hits` can request highlighting for nested fields:

~~~json
{
  "inner_hits": {
    "name": "matching_offers",
    "highlight": {
      "fields": {
        "offers.description": {
          "pre_tags": ["<mark>"],
          "post_tags": ["</mark>"]
        }
      }
    }
  }
}
~~~

This is useful when searching products by offer description and wanting to display the matching snippet. Highlight fragments are still untrusted data; sanitize/handle them safely before rendering in a browser.

### 8.5. Explanation and extra metadata

`inner_hits` can also be configured with options such as `explain`, `version`, `seq_no_primary_term`, and applicable field options. Enable them only when the use case needs them.

Explanations can bloat responses and increase cost. Do not enable them on public search endpoints just for temporary debugging.

## 9. Multiple nested queries and multiple inner hits

### 9.1. Each nested query can have its own inner_hits name

A product might have nested `offers` and `reviews`. You can query two different nested groups:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "nested": {
            "path": "offers",
            "query": {
              "term": {
                "offers.available": true
              }
            },
            "inner_hits": {
              "name": "available_offers",
              "size": 3
            }
          }
        },
        {
          "nested": {
            "path": "reviews",
            "query": {
              "range": {
                "reviews.rating": {
                  "gte": 4
                }
              }
            },
            "inner_hits": {
              "name": "positive_reviews",
              "size": 2
            }
          }
        }
      ]
    }
  }
}
~~~

Each parent hit can include two inner hit groups under different names. Names let the application know which group came from which `nested` query.

Inner hit names must be unique within a search request if definitions could collide. Never accept arbitrary dynamic names from the client.

### 9.2. Nested within nested

With mappings that have nested objects inside nested objects, you can place `nested` queries along deep paths and request `inner_hits` at the corresponding level. Results can contain nested inner hits mirroring the query structure.

Verify the paths and how responses are mapped. If the application only needs one child level, avoid pulling an entire deep nested tree because response size and processing cost will increase.

### 9.3. Inner hits do not replace nested aggregations

`inner_hits` serves to retrieve matching nested documents per parent hit. Nested aggregations serve to compute statistics/summaries across nested documents in a dataset.

For example:

- `inner_hits`: display 3 matching offers inside each product.
- `nested` aggregation: calculate price distribution across all offers of filtered products.
- `reverse_nested` aggregation: step back from a nested bucket to parent context to count parent products.

Choose the API based on whether you need to display individual items or compute aggregate statistics.

## 10. Nested queries and Spring Data Elasticsearch

### 10.1. Using StringQuery for DSL with inner_hits

When a query has a complex nested structure, you can express the query clause using `StringQuery`:

~~~java
Query query = new StringQuery("""
{
  "nested": {
    "path": "offers",
    "score_mode": "max",
    "query": {
      "bool": {
        "filter": [
          {
            "term": {
              "offers.seller": "SELLER-A"
            }
          },
          {
            "range": {
              "offers.price": {
                "lte": 100
              }
            }
          },
          {
            "term": {
              "offers.available": true
            }
          }
        ]
      }
    },
    "inner_hits": {
      "name": "matching_offers",
      "size": 5,
      "sort": [
        {
          "offers.price": {
            "order": "asc"
          }
        }
      ]
    }
  }
}
""");

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

`StringQuery` takes a Query DSL clause in Spring Data's abstraction, not the entire search request body with an outer `query` field. Options like `pageable` can be attached separately to the `Query`.

### 10.2. Using NativeQuery

`NativeQuery` lets you build DSL with the Elasticsearch Java API Client and fits when you want a type-safe builder. The logical structure stays the same:

- Create a `nested` query with `path`.
- Place a `bool` query inside.
- Declare `score_mode`.
- Attach `inner_hits` with the required name and limits.

Builder signatures for nested queries and inner hits depend on your Spring Data Elasticsearch and Elasticsearch Java API Client versions. Use the API matching the dependency version in your project; do not blindly copy overloads from another client version.

### 10.3. Reading inner hits from SearchHit

Spring Data Elasticsearch stores inner hits in the metadata of the parent `SearchHit`. In versions supporting this API, you can access them by name:

~~~java
for (SearchHit<ProductDocument> parentHit : hits) {
    ProductDocument product = parentHit.getContent();

    Map<String, SearchHits<?>> innerHits =
        parentHit.getInnerHits();

    SearchHits<?> matchingOffers =
        innerHits.get("matching_offers");

    if (matchingOffers != null) {
        for (SearchHit<?> offerHit : matchingOffers) {
            Object content = offerHit.getContent();
            // Convert nested content to DTO based on the actual mapping type.
        }
    }
}
~~~

The data type and how the converter constructs inner hit content can depend on the version and entity configuration. You may need to inspect what type `getContent()` returns for the nested object or map via an intermediate structure. Do not blindly cast to a class without verifying the response.

### 10.4. Creating a DTO for nested matches

Example DTOs:

~~~java
public record MatchingOffer(
    String offerId,
    String seller,
    BigDecimal price,
    boolean available
) {
}

public record ProductSearchResult(
    String productId,
    String name,
    List<MatchingOffer> matchingOffers
) {
}
~~~

The mapper extracts parent content from `SearchHit<ProductDocument>` and inner hits from the `matching_offers` key. Only matching offers are placed into `matchingOffers`.

If a nested object lacks a business ID, consider adding `offerId`. Do not use the nested array `offset` as a long-term identifier.

### 10.5. Distinguishing source nested array from inner hits

The parent entity may contain all `offers` in `_source`, while `inner_hits` contains only the offers that matched the query. If a mapper uses `product.getOffers()` instead of `inner_hits`, the API can return offers that did not satisfy the criteria.

When the UI needs "matching offers," use `inner_hits`. When the UI needs all offers of the product, that is a different use case and should be clearly reflected in the response contract.

## 11. Sorting parents by a nested field

### 11.1. Sorting inner hits does not sort parents

Configuring `inner_hits.sort` only determines the order of nested documents returned within each parent hit. It does not determine the order of the parent products list.

If you need to sort products by the lowest offer price, you must use a `nested` sort at the root `sort` level:

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "offers",
          "filter": {
            "term": {
              "offers.available": true
            }
          }
        }
      }
    }
  ]
}
~~~

A nested sort has a `path` and can include a `filter` to evaluate only qualifying nested objects. `mode` here specifies how to pick a sort value from multiple nested values, such as `min` or `max`. It is distinct from a nested query's `score_mode`.

### 11.2. Distinguishing score_mode and nested sort mode

| Property | Purpose |
|---|---|
| `score_mode` | Combines nested query scores into the parent score |
| Nested sort `mode` | Chooses the nested field value used to sort parents |
| `inner_hits.sort` | Sorts nested hits returned inside each parent |

These three mechanisms are independent. Parent products can be ordered by lowest offer price, each product's inner hits sorted by ascending price, and `score_mode` used for relevance queries.

### 11.3. Aligning filters between query and sort

If the `nested` query only considers in-stock offers while the nested sort considers all offers, a parent could be sorted by the price of an out-of-stock offer. Apply a matching nested sort filter for the business rule.

Do not assume a nested sort automatically inherits filters from a `nested` query elsewhere in the request.

## 12. Nested mapping and resource limits

### 12.1. Nested objects increase the Lucene document count

A single root document with 1,000 nested objects creates many hidden Lucene documents. This impacts:

- Internal document count in the index.
- Index size.
- Indexing and update costs.
- Nested query and aggregation costs.
- Memory and search workload.

If each root document has thousands or tens of thousands of nested items, re-evaluate the data model. It may be better to split nested entities into a separate index or use parent-child when appropriate.

### 12.2. Nested field and nested object limits

Elasticsearch provides index settings to limit the number of nested field mappings and nested objects in a single document. Common setting names include:

- `index.mapping.nested_fields.limit`
- `index.mapping.nested_objects.limit`

Default values and enforcement details can vary across versions. Check your running cluster before designing the schema or changing limits.

Raising limits is not free. If data produces too many nested objects, increasing the setting can increase indexing and search load.

### 12.3. Updating nested objects

Nested objects belong to the same root document. When updating part of a nested array, Elasticsearch generally must reindex the root document and its associated nested documents.

If nested children are updated frequently or need an independent lifecycle, the `nested` model may not fit. Consider a separate index and application-level joins/queries as needed.

### 12.4. Inner result window limit

`index.max_inner_result_window` limits the `from + size` window for `inner_hits` and related constructs. The default value is usually fairly low to prevent oversized responses.

Keep `inner_hits.size` just large enough for the UI. If users need to view all nested children, use a dedicated detail endpoint or a separate paginated query instead of raising the inner result window arbitrarily.

## 13. Edge cases to watch out for

### 13.1. Missing fields or inconsistent mappings

If querying across multiple indexes and some indexes lack the corresponding nested path, a `nested` query can throw an error. You can use `ignore_unmapped: true` when business logic allows treating indexes without that path as having no matches.

~~~json
{
  "nested": {
    "path": "offers",
    "ignore_unmapped": true,
    "query": {
      "term": {
        "offers.available": true
      }
    }
  }
}
~~~

Do not use `ignore_unmapped` to mask a broken mapping on an index that is supposed to have the field. Align the mapping if it is part of the required schema.

### 13.2. Nested query not matching due to wrong path

`path` must be the nested field path in Elasticsearch, not an arbitrary Java property name. Check the mapping and actual field names, especially when an entity uses `@Field(name = "...")`.

### 13.3. Nested query returns parent but inner hits is empty

Possible causes:

- `inner_hits` was attached to a different `nested` query than the one that matched.
- The `inner_hits` name in the mapper is wrong.
- The response lacks `inner_hits` because the request DSL placed it in the wrong position.
- The API client/converter does not retain the metadata as expected.
- The query matched the parent via another `bool` branch.

Inspect Elasticsearch's raw response and the final generated query structure.

### 13.4. score_mode does not change ordering

Some causes:

- The `nested` query is inside a `filter` context.
- The inner query produces uniform scores.
- All nested matches have the same score.
- The root query has other clauses dominating the score.
- The request sorts by a field rather than `_score`.

`score_mode` only affects the score portion coming from the `nested` query. Check the scoring context and request `sort` before concluding the configuration doesn't work.

### 13.5. Parent appears even though nested item isn't what the UI expected

The `nested` query may have been split into separate branches, each matching a different nested object. Place conditions that must hold on the same element inside the same nested `bool` query.

### 13.6. Inner hits response is too large

There may be too many parent hits, each returning many inner hits with many source fields. Reduce the root page size, inner hit size, number of fields, and number of highlight fragments. If the UI needs all children, move to a separate endpoint.

## 14. Security and authorization

### 14.1. Enforcing permissions in nested queries

If nested objects contain sensitive tenant- or user-scoped information, authorization filters must be enforced in the server-side query. Do not return all nested items and filter them in Java or the frontend.

For example, nested offers belonging to a tenant:

~~~json
{
  "nested": {
    "path": "offers",
    "query": {
      "bool": {
        "filter": [
          {
            "term": {
              "offers.tenantId": "tenant-42"
            }
          },
          {
            "term": {
              "offers.available": true
            }
          }
        ]
      }
    },
    "inner_hits": {
      "name": "visible_offers",
      "size": 5
    }
  }
}
~~~

The tenant ID must come from a trusted server-side security context, never accepted arbitrarily from the client when it defines access scope.

### 14.2. Inner hits are also data to protect

`inner_hits` may contain fields that do not appear in the root DTO. Apply source filtering and DTO mapping to return only permitted fields.

Do not expose raw inner hit `_source` or `explanation` in public endpoints if they contain internal information.

### 14.3. Restricting client-controlled query parameters

Do not allow clients to supply arbitrary nested paths, inner hit names, sort fields, or raw DSL. The server should select paths and fields from a controlled allowlist/configuration, while the client only supplies validated business parameters.

## 15. Testing Nested queries, score modes, and inner hits

### 15.1. Testing the mapping

Create the index in a test and verify:

- `offers` has `type` `nested`.
- `seller` is `keyword`.
- `price` is numeric.
- `available` is `boolean`.
- Nested path and field names match the entity.

Do not just check Java annotations; inspect the actual mapping on an Elasticsearch test instance.

### 15.2. Testing object array false positives

Create two-offer test data:

- Offer A: seller A, price 150, available true.
- Offer B: seller B, price 80, available false.

A query requiring seller A, `price <= 100`, and `available = true` must not return the product.

Then add Offer C with seller A, price 90, available true. The same query must now return the product and `inner_hits` must contain Offer C.

This test confirms that conditions truly match on the same nested object.

### 15.3. Testing each score mode

Create a parent with multiple matching nested documents having distinguishable scores. Verify:

- `avg` uses the mean score.
- `max` selects the highest score.
- `min` selects the lowest score.
- `sum` sums the scores.
- `none` excludes nested scores from the parent score.

Exact scores depend on analyzers and similarity models, so integration tests should compare relative ordering or use queries with stable scoring. Do not hardcode absolute scores if the environment can vary similarity or corpus statistics.

### 15.4. Testing inner hits

Verify:

- `inner_hits` contains only matching nested items.
- The `inner_hits` name is correct.
- `size` is enforced.
- `inner_hits` sorting is correct.
- Source filtering omits unrequested fields.
- Inner hit highlights are present when requested.
- Multiple `nested` queries produce separate inner hit groups.
- Parent `_source` can still retain the full nested array.

### 15.5. Testing nested sort separately

If parents are sorted by lowest nested price, create products with multiple offers and verify:

- Parent order follows the nested sort mode.
- Inner hit order follows `inner_hits.sort`.
- Filters inside the nested sort exclude non-qualifying offers.
- Results do not depend on element order in the `_source` array.

### 15.6. Testing performance and limits

Use near-production-scale data to measure:

- Nested objects per parent.
- Parent hits count.
- `inner_hits` size.
- Response size.
- Search latency and heap usage.
- Number of nested field mappings.
- Behavior when exceeding `inner_result_window`.

Do not raise limits just to make a test pass if the query is returning too many nested items. Determine the exact count the UI needs.

## 16. Common mistakes

| Symptom | Possible cause | Fix |
|---|---|---|
| Result has the right seller but price from another offer | Array field mapped as `object`, or query split nested conditions separately | Map as `nested` and put conditions inside one `nested` query |
| Nested query fails to run | Path does not exist or field is not `nested` | Inspect the actual mapping |
| Changed annotation but query still returns wrong results | Old index still has `object` mapping | Create a new index and reindex |
| Parent score is unexpected | Wrong `score_mode` or query is in a `filter` context | Check scoring context and nested matches |
| Products with many offers are boosted too strongly | Using `sum` when match count shouldn't inflate rank | Use `avg`/`max` or tune ranking |
| Inner hits missing | Missing `inner_hits` or placed on the wrong `nested` query | Check request DSL and raw response |
| Inner hits only returns a few items | Default/capped inner hit size | Specify `size` explicitly based on need |
| Inner hit order differs from parent order | Confusing `inner_hits.sort` with root nested sort | Configure both sorts independently |
| Parent has full `_source` but UI shows wrong offer | Mapper reads the entire source array instead of `inner_hits` | Map from the appropriate inner hit group |
| Inner hit ID is unstable | Using nested `offset` as an ID | Add a business key to the nested object |
| Multi-index query fails | Inconsistent nested mappings | Align mappings or intentionally use `ignore_unmapped` |
| Response is too large | Too many parents and inner hits, unrestricted `_source` | Reduce page size, inner size, and returned fields |
| Nested updates are expensive | Nested objects are updated frequently | Consider a separate index or another data model |

## 17. Selection and implementation workflow

When designing a `nested` query, follow this order:

1. Determine whether conditions must match on the same array element.
2. Choose `nested` mapping for fields that must preserve relationships.
3. Create the proper index/mapping before indexing data.
4. Put conditions requiring the same nested object inside one `nested` query.
5. Choose scoring context: `must`/`should` when score matters, `filter` when only matching matters.
6. Choose `score_mode` according to how nested match scores should be combined.
7. Add `inner_hits` if the UI needs to know which nested items matched.
8. Name `inner_hits` clearly, cap `size`, and select needed fields.
9. Configure `inner_hits.sort` and root nested sort separately if needed.
10. Map parent and inner hits into application-owned DTOs.
11. Enforce authorization on both the `nested` query and inner-hit content.
12. Integration-test false positives, score modes, inner hits, sorts, and resource limits.
13. Benchmark performance on data with near-production nested object counts.

## 18. Key takeaways

- Standard object arrays can lose field relationships per element; `nested` preserves those relationships.
- A `nested` query returns the parent document when a nested document matches.
- Conditions that must match on the same nested item must sit inside the same `nested` query.
- `score_mode` includes `avg`, `max`, `min`, `sum`, and `none`; it combines nested match scores into the parent score.
- `score_mode` has no meaningful ranking effect when the `nested` query is solely in a `filter` context.
- `inner_hits` returns matching nested documents, not the entire nested array.
- Inner hits lack an independent `_id` like root documents; add a business ID if a stable identifier is needed.
- `inner_hits` `size`, `from`, `sort`, source filtering, and highlighting are all configurable.
- `inner_hits.sort` orders nested results; root nested sort orders parents; `score_mode` controls scoring.
- Nested queries, nested aggregations, and `inner_hits` serve different purposes.
- Nested objects increase Lucene document count and indexing/search costs; do not use `nested` for every object array.
- Mappings created as `object` generally require a new index and reindexing to switch to `nested`.
- Spring Data can store inner hits in `SearchHit` metadata; how content is unwrapped depends on the version.
- Enforce authorization on nested matches and trim inner-hit data before returning API responses.

Nested queries allow Elasticsearch to accurately handle relationships among sub-objects inside a document. When paired properly with `score_mode` and `inner_hits`, an application can both rank parent documents by their nested matches and know exactly which child elements caused the match.
