# Nested Queries, Inner Hits, and Specialized Queries

Spring Data Elasticsearch offers multiple ways to build queries. Query methods and the Criteria API handle common conditions well, yet requirements such as searching arrays of objects while preserving per-element field relationships, retrieving the exact child elements that matched, geospatial queries, script queries, or parent/child relations typically need more direct expression in Elasticsearch Query DSL.

NativeQuery is a key option for those scenarios. It lets the application construct queries using Elasticsearch Java API Client types and execute them through ElasticsearchOperations. This allows the application to retain Spring Data's mapping metadata and conversion layer while leveraging Elasticsearch's specialized DSL queries.

This lesson focuses on three topics:

- Nested queries for accurately querying relationships between attributes of the same object in an array.
- Inner hits for retrieving the specific nested documents or child documents that matched the query.
- Specialized queries and how to choose among NativeQuery, CriteriaQuery, @Query, and the Elasticsearch Java API Client.

## 1. Why Are Nested Queries Needed?

Elasticsearch provides the `object` type for storing nested objects. However, when an `object` field holds an array of objects, Elasticsearch by default flattens child objects into multi-valued arrays of the corresponding fields. Relationships between fields within the same array element are no longer preserved in the way many business queries expect.

Suppose a product has multiple offers from different sellers:

~~~json
{
  "sku": "KB-1042",
  "name": "Mechanical Keyboard",
  "offers": [
    {
      "seller": "seller-a",
      "price": 120,
      "available": true
    },
    {
      "seller": "seller-b",
      "price": 95,
      "available": false
    }
  ]
}
~~~

Business requirement: find products that have an offer both from `seller-a` and priced less than or equal to 100.

If `offers` is mapped as `object`, Elasticsearch effectively treats the values as:

~~~text
offers.seller    = ["seller-a", "seller-b"]
offers.price     = [120, 95]
offers.available = [true, false]
~~~

The association between `seller-a` with price 120 and `seller-b` with price 95 is lost when querying fields as independent value sets. A query combining `seller-a` and price less than or equal to 100 can match the product even though no single offer satisfies both conditions.

This mismatch in relationships across array elements is commonly called cross-object matching.

## 2. How Do object and nested Differ?

The `nested` type stores each child object as a separate hidden document internally linked to the parent document. This lets Elasticsearch evaluate conditions against the same object element.

| Characteristic | object | nested |
| --- | --- | --- |
| Array of objects | Subfields become multi-valued fields | Each object element is stored as a nested document |
| Relationship between fields in one element | Not preserved for per-object correlated queries | Preserved within the nested document |
| Query | Standard field queries | Requires a `nested` query to enter the nested path |
| Results | Returns parent document | Nested query still returns parent document; `inner_hits` can return matching child objects |
| Cost | Lower, simpler structure | Additional indexing and query resource overhead |

Do not turn every object into `nested`. Use `nested` only when you need correlated queries across multiple fields belonging to the same element of an object array.

### 2.1. Declaring Nested Mapping

In Spring Data Elasticsearch, you can use `FieldType.Nested`:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Nested)
    private List<ProductOffer> offers;

    // Constructors, getters and setters
}

public class ProductOffer {

    @Field(type = FieldType.Keyword)
    private String seller;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private boolean available;

    // Constructors, getters and setters
}
~~~

The corresponding JSON mapping looks like:

~~~json
{
  "properties": {
    "sku": {
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
~~~

The mapping type must be `nested` when the field is first created. You cannot change an existing `object` field to `nested` in-place. If an index already stores data as `object` and needs nested correlation, create a new index with the proper mapping and reindex.

### 2.2. Inspecting the Actual Mapping

You can use the Elasticsearch API:

~~~http
GET /catalog-products/_mapping
~~~

Or read the mapping via Spring Data:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

Document mapping = indexOperations.getMapping();
~~~

Do not rely solely on annotations in source code. If the index already existed beforehand, the live mapping may differ from the current entity class.

## 3. Basic Nested Query

A nested query requires specifying:

- `path`: path to the field mapped as `nested`.
- `query`: query executed inside the nested documents.
- `score_mode`: how scores from matching nested documents combine to produce the parent document's score.
- `inner_hits`: optional configuration to retrieve the matching nested documents.

Query DSL example finding products with an offer from `seller-a` priced at most 100:

~~~json
{
  "query": {
    "nested": {
      "path": "offers",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "offers.seller": "seller-a"
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
      "score_mode": "none"
    }
  }
}
~~~

This query matches only when a single nested document inside `offers` satisfies both conditions. With the sample data, the product does not match because `seller-a`'s offer costs 120, while the offer priced at 95 belongs to `seller-b`.

If `seller` is changed to `seller-b`, the product matches both seller and price conditions. If the query also requires `available` true, the product again does not match because `seller-b`'s offer has `available` false.

### 3.1. Why Use bool.filter?

The seller and price conditions in the example are filtering conditions. They do not need to contribute relevance scores. Using `bool.filter` clearly communicates filtering intent and avoids unnecessary score computation for those conditions.

If the nested query is used for relevance search, you can put text conditions inside `must` or `should` so nested document scores contribute to the parent document score.

### 3.2. score_mode

`score_mode` defines how scores of matching nested documents are combined into the parent document score:

| Value | Meaning |
| --- | --- |
| avg | Average score of matching nested documents |
| max | Highest score |
| min | Lowest score |
| sum | Sum of scores |
| none | Do not compute a score from the nested query for the parent document |

For pure filtering queries, `none` is usually appropriate. For relevance queries over nested elements, choose the aggregation mode based on business semantics. Do not assume having more matching nested objects should always increase the parent score in the same way across every problem.

## 4. Nested Queries with NativeQuery

NativeQuery lets you construct queries using the Elasticsearch Java API Client's typed DSL. This is the right approach when queries require nested queries, inner hits, scripts, geo, or features that the Criteria API cannot express conveniently.

Example using the typed query builder:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.ChildScoreMode;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Query nestedQuery = Query.of(q -> q
    .nested(n -> n
        .path("offers")
        .query(inner -> inner
            .bool(b -> b
                .filter(f -> f
                    .term(t -> t
                        .field("offers.seller")
                        .value(FieldValue.of("seller-b"))
                    )
                )
                .filter(f -> f
                    .range(r -> r
                        .number(number -> number
                            .field("offers.price")
                            .lte(100.0)
                        )
                    )
                )
            )
        )
        .scoreMode(ChildScoreMode.None)
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(nestedQuery)
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Exact imports and builder overloads can vary across Elasticsearch Java API Client and Spring Data Elasticsearch versions. This snippet illustrates the modern Java client API style; use Spring Boot-managed dependencies to avoid mixing client generations.

Key points to keep in mind:

- `Query` in this example is `co.elastic.clients.elasticsearch._types.query_dsl.Query`, not `org.springframework.data.elasticsearch.core.query.Query`.
- `NativeQuery` is a Spring Data Elasticsearch query implementation that can hold Java API Client query DSL.
- `ElasticsearchOperations.search(...)` still handles mapping results into `ProductDocument`.
- Field paths must match the live mapping. If the mapping uses `offers.seller.keyword`, use that exact field name.

### 4.1. NativeQuery vs. CriteriaQuery

| Criterion | CriteriaQuery | NativeQuery |
| --- | --- | --- |
| Construction | Spring Data Criteria API | Elasticsearch Java API Client Typed Query DSL |
| Simple queries | Readable, less coupled to DSL | Can be more verbose |
| Nested queries & inner hits | Expressiveness depends on version/API | Direct access to all DSL constructs |
| Specialized queries | Limited by the abstraction | Covers queries supported by the client |
| Client coupling | Minimal exposure of Java client query types | Tied to Elasticsearch Java client API |

Choose CriteriaQuery for simple conditions easily expressed with Criteria. Choose NativeQuery when you need the full power of Elasticsearch DSL or fine-grained control over query structure.

## 5. What Is inner_hits?

A nested query returns the parent document if at least one nested document matches. In many cases, the application also needs to know which nested objects matched in order to display the right offer, address, product variant, or order line.

`inner_hits` lets Elasticsearch return the matching nested documents alongside each parent result.

Example adding `inner_hits` to a nested query:

~~~json
{
  "query": {
    "nested": {
      "path": "offers",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "offers.seller": "seller-b"
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
        "size": 5,
        "sort": [
          {
            "offers.price": {
              "order": "asc"
            }
          }
        ],
        "_source": {
          "includes": [
            "offers.seller",
            "offers.price",
            "offers.available"
          ]
        }
      }
    }
  }
}
~~~

The result includes:

- The parent hit as `ProductDocument`.
- Inside each parent hit, `inner_hits.matching_offers` containing matching nested offers.
- Each nested hit has its own metadata, such as score, source, and the nested object's offset within the parent document.

`inner_hits.name` assigns a name to the inner hits group so the application can retrieve the right group when a query defines multiple nested paths or multiple inner hit definitions.

### 5.1. inner_hits Does Not Replace the Parent Document

A nested query still returns parent documents. `inner_hits` simply attaches the matching nested documents inside the response. It does not turn search results into a standalone list of `ProductOffer`.

If the application needs the matching offers for display, read `inner_hits` from each parent hit. Do not fetch the full `offers` list from `_source` and re-filter it manually in Java when Elasticsearch already returns the exact nested matches—especially when nested objects have many fields or complex query logic.

### 5.2. size, from, sort, and Source Filtering

Common options in inner hits:

| Option | Purpose |
| --- | --- |
| name | Names the inner hits group |
| size | Maximum nested hits returned per parent hit |
| from | Skips a number of initial nested hits |
| sort | Sorts nested hits |
| _source | Returns only needed fields in nested source |
| highlight | Returns highlights for suitable nested fields |
| explain | Returns scoring details, useful for debugging |

Inner hits size can inflate responses substantially because it applies per parent hit. For example, 50 parent hits with 20 inner hits each can produce 1,000 nested hits in the response. Keep `size` only as large as the UI needs and cap overall results.

## 6. Reading Inner Hits in Spring Data Elasticsearch

Results from `ElasticsearchOperations.search(...)` are represented by `SearchHits<T>`. Each `SearchHit<T>` can contain a map of inner hits keyed by name.

Example:

~~~java
SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> productHit : results) {
    ProductDocument product = productHit.getContent();

    SearchHits<?> matchingOffers =
        productHit.getInnerHits().get("matching_offers");

    if (matchingOffers == null) {
        continue;
    }

    for (SearchHit<?> offerHit : matchingOffers.getSearchHits()) {
        Object matchedOffer = offerHit.getContent();
        // Convert or process the nested hit according to the version's return type.
    }
}
~~~

The exact content type of an inner hit depends on how Spring Data maps nested hits and the version in use. You may receive mapped objects or intermediate data structures; inspect the actual runtime type and mapping metadata of the nested class. Never cast blindly from `Object`.

If returning results from an API, map nested hits into clear response DTOs. Do not let `SearchHit<?>` or internal Elasticsearch client structures leak beyond the persistence layer.

### 6.1. Multiple Inner Hits Groups

A single query can contain multiple nested queries, each with its own inner hits:

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
                "offers.seller": "seller-a"
              }
            },
            "inner_hits": {
              "name": "seller_offers"
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
              "name": "high_rating_reviews"
            }
          }
        }
      ]
    }
  }
}
~~~

In the response, the application can retrieve the two groups via keys `seller_offers` and `high_rating_reviews`. Each group has its own meaning and bounds.

## 7. Common Logic Mistakes with Nested Queries

### 7.1. Placing Same-Object Conditions in Two Separate Nested Queries

Suppose the requirement is that a single offer must have `seller-a` and price under 100. If you write two independent nested queries inside `bool`:

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
                "offers.seller": "seller-a"
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

The two nested queries can match two different nested objects. The parent document is selected if one offer belongs to `seller-a` and another (possibly different) offer has price under 100.

If both conditions must hold on the same offer, put them inside a single nested query within a bool query:

~~~json
{
  "nested": {
    "path": "offers",
    "query": {
      "bool": {
        "must": [
          {
            "term": {
              "offers.seller": "seller-a"
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
~~~

This is the single most important rule when querying nested arrays: be explicit about whether conditions must apply to the same element or can match across different elements.

### 7.2. Forgetting Nested Mapping Declaration

Nested queries work only on fields mapped as `nested`. If the field is a regular `object`, Elasticsearch will throw an error when executing a nested query on that path. Check the mapping before modifying the query.

### 7.3. Wrong Path or Field Path

`path` must point to the nested field, such as `offers`. Fields inside the inner query typically use full dotted names like `offers.price`. Misspellings, wrong casing, or confusing a multi-field can prevent the query from matching.

### 7.4. Confusing Inner Hits with Source Filtering

Source filtering only picks which fields appear in the parent hit's `_source`. It does not filter child object arrays by query conditions. To retrieve only matching nested objects, use `inner_hits`.

### 7.5. Not Limiting Inner Hits

Do not leave a large default size if parent documents can have many nested objects. That inflates response size, network traffic, and deserialization overhead. Retrieve only needed fields, sort explicitly, and paginate nested hits where appropriate.

## 8. Nested Inside Nested: Multi-Level Nested Queries

A nested object can contain another nested object. For example, an order has an `items` array, and each item has an `adjustments` array:

~~~json
{
  "orderId": "ORD-1001",
  "items": [
    {
      "sku": "KB-1042",
      "adjustments": [
        {
          "type": "discount",
          "amount": 15
        }
      ]
    }
  ]
}
~~~

Mapping:

~~~json
{
  "properties": {
    "orderId": {
      "type": "keyword"
    },
    "items": {
      "type": "nested",
      "properties": {
        "sku": {
          "type": "keyword"
        },
        "adjustments": {
          "type": "nested",
          "properties": {
            "type": {
              "type": "keyword"
            },
            "amount": {
              "type": "double"
            }
          }
        }
      }
    }
  }
}
~~~

Query finding orders with an item of SKU `KB-1042` and an adjustment of type `discount`:

~~~json
{
  "query": {
    "nested": {
      "path": "items",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "items.sku": "KB-1042"
              }
            },
            {
              "nested": {
                "path": "items.adjustments",
                "query": {
                  "term": {
                    "items.adjustments.type": "discount"
                  }
                }
              }
            }
          ]
        }
      },
      "inner_hits": {
        "name": "matching_items"
      }
    }
  }
}
~~~

Elasticsearch supports multi-level nested queries and can resolve nested context along the corresponding path in nested queries. Still, the query structure should accurately mirror the parent-child relationship. If you need both matching items and matching adjustments, declare `inner_hits` at each nested level with distinct names.

Multi-level nesting increases mapping complexity and query cost. Use it only when data relationships truly must be preserved at each level.

## 9. Parent/Child Queries and Join Fields

Nested works well when child objects reside inside the same physical document and are usually read together with the parent. When parent-child relationships require independent documents, consider Elasticsearch's `join` field type.

Example where product is the parent and review is the child document:

~~~json
{
  "properties": {
    "relation": {
      "type": "join",
      "relations": {
        "product": "review"
      }
    },
    "sku": {
      "type": "keyword"
    },
    "rating": {
      "type": "integer"
    }
  }
}
~~~

A parent document:

~~~json
{
  "sku": "KB-1042",
  "relation": "product"
}
~~~

A child document:

~~~json
{
  "rating": 5,
  "relation": {
    "name": "review",
    "parent": "product-1001"
  }
}
~~~

Parent and child must be stored in the same index and routed to the same shard. When indexing a child, supply routing matching the parent's ID so both documents reside on the same shard.

### 9.1. has_child Query

Find parents with at least one review rated 4 or higher:

~~~json
{
  "query": {
    "has_child": {
      "type": "review",
      "query": {
        "range": {
          "rating": {
            "gte": 4
          }
        }
      },
      "score_mode": "max",
      "inner_hits": {
        "name": "matching_reviews",
        "size": 3
      }
    }
  }
}
~~~

### 9.2. has_parent Query

Find child reviews belonging to a product with SKU `KB-1042`:

~~~json
{
  "query": {
    "has_parent": {
      "parent_type": "product",
      "query": {
        "term": {
          "sku": "KB-1042"
        }
      },
      "inner_hits": {
        "name": "matched_product"
      }
    }
  }
}
~~~

Parent/child is flexible when documents have independent lifecycles, yet join queries carry significant cost. Do not use `join` merely to query an object array; `nested` is usually better when child elements belong to the same aggregate and are stored in the same document.

In Spring Data Elasticsearch, `has_child`/`has_parent` can be built with NativeQuery if your Elasticsearch Java API Client version supports the corresponding query builders. You must configure join fields, routing, and mappings properly; simply adding a nested annotation does not create a parent/child relationship.

## 10. Geo Queries

Elasticsearch provides geospatial queries for fields mapped as `geo_point` or `geo_shape`.

### 10.1. geo_point Mapping

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Field(type = FieldType.GeoPoint)
private GeoPoint location;
~~~

JSON mapping:

~~~json
{
  "properties": {
    "location": {
      "type": "geo_point"
    }
  }
}
~~~

### 10.2. Geo Distance Query

Find locations within a 5 km radius of given coordinates:

~~~json
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  }
}
~~~

### 10.3. Geo Bounding Box

~~~json
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.70,
          "lon": 106.76
        }
      }
    }
  }
}
~~~

NativeQuery lets you combine geo queries with other filters, distance sorting, and pagination. When sorting by distance, clearly define the sort order and how documents missing coordinates are handled.

## 11. Script Queries

Script queries allow evaluating conditions with a Painless script. This is a flexible tool, though it carries higher overhead than standard native queries and requires strict bounds.

Example finding products whose effective discounted price is below a threshold:

~~~json
{
  "query": {
    "script": {
      "script": {
        "lang": "painless",
        "source": "doc['price'].value * (1 - params.discount) < params.maxPrice",
        "params": {
          "discount": 0.15,
          "maxPrice": 100
        }
      }
    }
  }
}
~~~

When using script queries:

- Use parameters instead of concatenating user data into script source.
- Prefer native queries/filters whenever the same condition can be expressed natively.
- Verify that fields have appropriate doc values.
- Benchmark script overhead on realistic data and load.
- Never allow users to submit arbitrary script code.

Spring Data can express script queries via NativeQuery/Java client DSL. For complex or frequently reused scripts, consider ScriptOperations to manage stored scripts by ID rather than sending script source repeatedly in every request.

## 12. Percolate Queries: Finding Queries Matching a Document

Percolator inverts standard search:

- Standard search: given a query, find documents matching it.
- Percolate: given an input document, find previously stored queries that match it.

For example, a system stores user alert conditions and needs to determine which alerts match a newly imported product.

Mapping:

~~~json
{
  "properties": {
    "query": {
      "type": "percolator"
    },
    "name": {
      "type": "keyword"
    }
  }
}
~~~

Storing a query document:

~~~json
{
  "name": "discounted-keyboards",
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "description": "keyboard"
          }
        },
        {
          "range": {
            "price": {
              "lte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

Percolate request:

~~~json
{
  "query": {
    "percolate": {
      "field": "query",
      "document": {
        "description": "Compact mechanical keyboard",
        "price": 89
      }
    }
  }
}
~~~

Percolator is useful for alerts, saved searches, and monitoring rules. Ensure the mapping of percolated documents is compatible with the mappings used by stored queries. The number and complexity of stored queries directly impact performance.

## 13. More Like This and Related Queries

More Like This finds documents similar in content to a provided document or text. The query typically specifies which fields to compare, minimum term frequency, and frequency thresholds.

Example:

~~~json
{
  "query": {
    "more_like_this": {
      "fields": ["name", "description"],
      "like": [
        {
          "_index": "catalog-products",
          "_id": "product-1001"
        }
      ],
      "min_term_freq": 1,
      "max_query_terms": 12
    }
  }
}
~~~

This query fits "similar items" recommendation features. Results depend on analyzers, field contents, term frequencies, and tuning parameters. Test on real data to avoid results that are too broad or too narrow.

## 14. KNN and Vector Queries

For semantic search systems, Elasticsearch supports vector search through vector fields and KNN queries depending on version and configuration.

Example mapping:

~~~json
{
  "properties": {
    "embedding": {
      "type": "dense_vector",
      "dims": 3,
      "index": true,
      "similarity": "cosine"
    }
  }
}
~~~

Illustrative KNN query:

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.08, 0.91],
    "k": 10,
    "num_candidates": 100
  }
}
~~~

In real applications, vector queries must match the dimensionality, similarity metric, and embedding generation of your model. Exact KNN query syntax and support for combining with filters, hybrid search, or rescoring depend on the Elasticsearch version. Use NativeQuery/Java API Client matching your version and evaluate retrieval quality on an evaluation dataset.

## 15. Building NativeQuery for Specialized Queries

NativeQuery builds on the Elasticsearch Java API Client's typed query model. General structure:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query elasticQuery = Query.of(q -> q
    // Choose the corresponding query builder: nested, geo, script, percolate...
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(elasticQuery)
    .build();
~~~

Then execute:

~~~java
SearchHits<ProductDocument> results =
    operations.search(
        nativeQuery,
        ProductDocument.class,
        IndexCoordinates.of("catalog-products")
    );
~~~

You can combine additional options:

- `Pageable` for parent-level hit pagination when supported by the query.
- `Sort` for sorting parent results.
- Highlight fields to return highlights for matching fields.
- Aggregations to summarize data.
- Source filtering to restrict returned fields.
- Track scores or min score when relevance is needed.

With inner hits, parent-hit pagination and nested-hit pagination are two separate scopes. `Pageable` on the main query does not automatically paginate inner hits; configure `from`/`size` inside the `inner_hits` definition.

### 15.1. Using @Query for Static Queries

If a JSON query is fixed with minimal parameters and does not need dynamic DSL assembly, a repository method can use `@Query`:

~~~java
import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("""
        {
          "nested": {
            "path": "offers",
            "query": {
              "term": {
                "offers.seller": "?0"
              }
            },
            "inner_hits": {
              "name": "matching_offers"
            }
          }
        }
        """)
    SearchHits<ProductDocument> findProductsBySeller(String seller);
}
~~~

`@Query` is convenient for static queries. When there are many optional conditions, specialized queries needing typed builders, or dynamically configured inner hits, `NativeQuery` is usually more maintainable.

### 15.2. When Should You Use the Elasticsearch Java API Client Directly?

NativeQuery covers most Query DSL features, yet Spring Data abstractions may not expose every request option or newly added Elasticsearch API. When you need an API not exposed by Spring Data:

1. Create a dedicated infrastructure adapter.
2. Inject the Spring-managed Elasticsearch Java API Client.
3. Call the specific API and map the response into application types.
4. Keep mapping, exception handling, timeouts, and logging consistent with the rest of the application.
5. Do not let client request/response types spread into domain or controller layers.

Use the low-level client only when current abstractions genuinely lack required capabilities. Whenever a query is supported by NativeQuery, using `ElasticsearchOperations` reuses Spring Data's mapping converters and conventions.

## 16. Choosing the Right Query Type

| Requirement | Mechanism to Consider |
| --- | --- |
| General text search | `match`, `multi_match` |
| Exact matching | `term`, `terms` |
| Numeric/date filtering | `range` |
| Multiple logical conditions | `bool` |
| Conditions on the same object array element | `nested` |
| Returning matching nested objects | `nested` + `inner_hits` |
| Independent parent-child documents | `has_child`, `has_parent`, `join` mapping |
| Location-based search | `geo_distance`, `geo_bounding_box`, `geo_shape` |
| Expression-based condition evaluation | `script` query |
| Finding stored queries matching a new document | `percolate` |
| Finding similar documents | `more_like_this` |
| Vector search | `knn` or version-appropriate vector APIs |

Do not pick a complex query simply because it is available. Simpler native queries are usually easier to optimize, easier to observe, and less resource-intensive. Choose the mechanism that fits the data model and business semantics.

## 17. Testing and Debugging Queries

When a nested query or inner hits returns unexpected results, check in order:

1. Inspect the live mapping to confirm the field is `nested` and the path is accurate.
2. Fetch a sample document's `_source` to verify the array structure.
3. Run each condition inside the nested query individually.
4. Combine conditions inside the same nested `bool` if they must match the same object.
5. Add `inner_hits` to see which elements actually matched.
6. Check field paths, data types, analyzers, and multi-fields.
7. Check `score_mode` if results are ranked by score.
8. Use the Profile API when analyzing execution costs.
9. Reduce `inner_hits` size and source fields to evaluate response impact.
10. Benchmark with representative data rather than a single small document.

You can check Query DSL using Elasticsearch's `_validate/query` or `_search` in development:

~~~http
POST /catalog-products/_validate/query?explain=true
{
  "query": {
    "nested": {
      "path": "offers",
      "query": {
        "term": {
          "offers.seller": "seller-b"
        }
      }
    }
  }
}
~~~

`_validate/query` checks whether a query is valid and can explain how it is parsed. It does not replace executing the query on real data to verify results.

## 18. Performance and Operational Limits

Nested queries are costlier than standard `object` queries because each nested object is indexed as a hidden document. A parent with many nested elements increases internal document count, segment merge work, and search volume.

Key guidelines:

- Use `nested` only for relationships requiring per-element correlation queries.
- Limit the number of nested fields and nested objects per parent.
- Keep `inner_hits` size small and return only needed fields.
- Avoid script queries if a native query can express the same condition.
- With parent/child, account for join overhead and routing requirements.
- With geo or vector queries, benchmark against real data, shard topology, and concurrency.
- Monitor query latency, heap, CPU, segment counts, and response sizes.
- Enforce input limits on condition counts, distances, inner hits sizes, and page counts.

Nested mappings also have Elasticsearch configuration limits, such as the number of nested fields and nested objects per document. Specific defaults depend on version and index settings. If documents routinely contain thousands of large child elements per parent, revisit the document model instead of defaulting to `nested`.

## 19. Common Mistakes

**Using object for arrays that must preserve per-element field relationships.** Queries can falsely match values from two different elements. Use `nested` mapping when same-object matching is needed.

**Writing a nested query when the field is mapped as object.** Elasticsearch cannot execute a nested query on a field without nested mapping. Create a new index and reindex if the type must change.

**Splitting same-element conditions into separate nested queries.** Those conditions can match different nested objects. Group them inside a single nested `bool` query.

**Assuming a nested query returns nested objects directly.** Primary results remain parent documents. Use `inner_hits` to retrieve matching nested objects.

**Forgetting to name inner hits when multiple groups exist.** Assign distinct names to retrieve the right group from `SearchHit`.

**Letting inner_hits return excessive data.** Cap `size`, `sort`, and source fields.

**Using CriteriaQuery for specialized Query DSL that the abstraction cannot express adequately.** Choose `NativeQuery` to leverage the Elasticsearch Java API Client's typed query builders.

**Concatenating user input into scripts or JSON queries.** Use parameter binding and validation to avoid query injection or unsafe scripts.

**Using parent/child for data that is naturally a simple child array.** Nested is usually faster and more natural when child elements share the parent's lifecycle.

**Casting inner hits directly to domain objects without checks.** Content types depend on mappings and versions; verify the response and map deliberately to DTOs.

## 20. Design and Implementation Workflow

When building a specialized query for a Spring Data Elasticsearch application:

1. Determine the data relationship: standalone object, nested array, or parent/child.
2. Design the mapping before writing the query; verify nested paths and field types.
3. Write a minimal Query DSL snippet to verify semantics against sample documents.
4. If matching child elements are needed, add `inner_hits` with name, size, sort, and source filtering.
5. Choose `CriteriaQuery` for routine conditions or `NativeQuery` for advanced Query DSL.
6. Use `ElasticsearchOperations.search(...)` to execute and obtain `SearchHits`.
7. Read inner hits by name and map to appropriate DTOs.
8. For other specialized needs, choose geo, script, percolate, parent/child, more_like_this, or vector queries matching the data model.
9. Verify mappings, query validity, results, and costs on representative data.
10. Place complex queries in infrastructure adapters, enforce input bounds, and monitor performance in production.

Nested queries solve correlated matching across fields of the same array element; `inner_hits` retrieves the exact matching elements; `NativeQuery` unlocks Elasticsearch's specialized DSL queries within Spring Data applications. Choosing the right mapping and semantics before optimizing queries makes search results more accurate and easier to maintain.

## 21. References

- [Elasticsearch - Nested field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/nested): how nested documents are stored and nested mapping limits.
- [Elasticsearch - Nested query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-nested-query): nested query syntax, score mode, and inner hits.
- [Elasticsearch - Retrieve inner hits](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrieve-inner-hits): retrieving nested/child hits in results.
- [Elasticsearch - Joining queries](https://www.elastic.co/docs/reference/query-languages/query-dsl/joining-queries): nested, has_child, and has_parent.
- [Spring Data Elasticsearch - Query and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): building and executing queries via Spring Data.
- [Elasticsearch Java API Client - Query DSL](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/searching): typed query builders and executing searches with the Java client.

Builder APIs and result types can change across Spring Data Elasticsearch and Elasticsearch Java API Client versions. Cross-check your project's actual dependencies when implementing `NativeQuery` examples.
