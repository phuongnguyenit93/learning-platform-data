# Building Category Filters, Price Ranges, and Faceted Search Statistics

## 1. The Faceted Search Problem on a Product Listing Page

Faceted search is a search pattern in which users view a list of results while narrowing them down using filter groups that show matching counts. An e-commerce page typically includes facets such as:

- Category: phones, computers, audio.
- Brand: Acme, Nova, Zenith.
- Price range: under 500,000, 500,000–2,000,000, over 2,000,000.
- Availability: in stock, out of stock.
- Other attributes: color, size, material, or rating.

An option inside a facet usually displays both its label and the number of matching products:

~~~text
Category
[ ] Phones                 128
[ ] Computers               74
[x] Audio                   36

Brand
[ ] Acme                    18
[ ] Nova                    11
[ ] Zenith                   7

Price range
[ ] Under 500,000           12
[ ] 500,000 - 2,000,000     25
[ ] Over 2,000,000           9
~~~

When the user selects Audio and the price range from 500,000 to 2,000,000, the list displays only products satisfying both conditions. The other facets also update their counts so the user knows how they can continue narrowing the results.

A faceted search request typically needs to return simultaneously:

1. Products matching all selected filters.
2. Total number of matching products.
3. List of values for each facet.
4. Number of documents belonging to each value or price range.
5. Optionally minimum, maximum, average price, or other statistics.

Elasticsearch can compute hits and multiple aggregations in a single Search API request. Spring Data Elasticsearch provides NativeQuery to combine Java API Client query DSL with those aggregations.

The detail that requires careful design is the document scope each facet uses for counting. If every filter is placed in the top-level query, the category facet may end up returning only the already selected category. Faceted search often requires a different rule: the hit list obeys all filters, while each facet can ignore its own filter when computing counts.

## 2. Designing Documents and Mappings for Filters

Fields used for filtering and statistics must have appropriate data types. For products, a basic mapping might look like this:

~~~json
PUT /products
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "brand": {
        "type": "keyword"
      },
      "price": {
        "type": "long"
      },
      "active": {
        "type": "boolean"
      },
      "inStock": {
        "type": "boolean"
      },
      "tenantId": {
        "type": "keyword"
      }
    }
  }
}
~~~

Purpose of each field:

| Field | Mapping | Used for |
|---|---|---|
| name | text + keyword subfield | Full-text search and exact sort/group if needed |
| category | keyword | Term/terms filter and terms aggregation |
| brand | keyword | Term/terms filter and terms aggregation |
| price | long | Range query, range aggregation, min/max/avg |
| active | boolean | Include only active products |
| inStock | boolean | In-stock filter |
| tenantId | keyword | Restrict data by tenant |

Categories and brands are usually identifier-like values. Use keyword so Elasticsearch matches the whole value instead of tokenizing the string like a text field.

Price must be a numeric field. Do not store price as a string like "1.500.000 VND", because range queries and range aggregations cannot compare strings numerically. For currencies with fractional units, you can store the smallest unit as a long, such as cents, or use scaled_float with an appropriate scaling factor. In this lesson, price is an integer in the currency unit defined by the application.

A corresponding Spring Data Elasticsearch entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(type = FieldType.Text),
        otherFields = {
            @InnerField(suffix = "keyword", type = FieldType.Keyword)
        }
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String brand;

    @Field(type = FieldType.Long)
    private Long price;

    @Field(type = FieldType.Boolean)
    private boolean active;

    @Field(type = FieldType.Boolean)
    private boolean inStock;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    // Constructors, getters and setters
}
~~~

If you want full-text search on name while still needing sorting or aggregations on the intact value, declare a keyword multi-field for name. Do not run terms aggregations on a regular text field without considering fielddata and heap cost.

Sample data:

~~~json
POST /products/_bulk?refresh=true
{"index":{"_id":"p-1"}}
{"name":"Wireless Headphones","category":"audio","brand":"Acme","price":1200000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-2"}}
{"name":"Bluetooth Speaker","category":"audio","brand":"Acme","price":1800000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-3"}}
{"name":"Studio Earbuds","category":"audio","brand":"Nova","price":850000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-4"}}
{"name":"Workstation Laptop","category":"computers","brand":"Acme","price":1900000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-5"}}
{"name":"Monitor","category":"computers","brand":"Nova","price":4200000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-6"}}
{"name":"Office Keyboard","category":"accessories","brand":"Acme","price":650000,"active":true,"inStock":false,"tenantId":"t-01"}
{"index":{"_id":"p-7"}}
{"name":"Studio Headphones","category":"audio","brand":"Acme","price":3200000,"active":true,"inStock":true,"tenantId":"t-01"}
{"index":{"_id":"p-8"}}
{"name":"Clearance Headphones","category":"audio","brand":"Acme","price":1500000,"active":false,"inStock":true,"tenantId":"t-01"}
~~~

In the example, product p-8 is inactive so it should not appear on user-facing listing pages. The active condition will be applied to both hits and aggregations so counts reflect only active products.

## 3. Modeling Filters from User Requests

The API should not accept arbitrary query DSL directly from the browser. Define a DTO containing the criteria allowed by the application.

~~~java
import java.util.List;

public record ProductSearchCriteria(
    List<String> categories,
    List<String> brands,
    Long minPrice,
    Long maxPrice,
    Boolean inStock,
    int page,
    int size
) {
}
~~~

Example request:

~~~http
GET /api/products?categories=audio,computers&brands=Acme&minPrice=500000&maxPrice=2000000&inStock=true&page=0&size=20
~~~

Meaning:

- categories can contain multiple values.
- brands can contain multiple values.
- minPrice and maxPrice form a price range.
- inStock is an optional filter.
- page and size control result pagination.

Before building the query, normalize and validate inputs:

~~~java
public ProductSearchCriteria normalize(ProductSearchCriteria criteria) {
    if (criteria.page() < 0) {
        throw new IllegalArgumentException("page must be >= 0");
    }

    int safeSize = Math.min(Math.max(criteria.size(), 1), 100);

    if (criteria.minPrice() != null && criteria.minPrice() < 0) {
        throw new IllegalArgumentException("minPrice must be >= 0");
    }

    if (criteria.maxPrice() != null && criteria.maxPrice() < 0) {
        throw new IllegalArgumentException("maxPrice must be >= 0");
    }

    if (criteria.minPrice() != null
            && criteria.maxPrice() != null
            && criteria.minPrice() > criteria.maxPrice()) {
        throw new IllegalArgumentException(
            "minPrice must be <= maxPrice"
        );
    }

    return new ProductSearchCriteria(
        criteria.categories() == null
            ? List.of()
            : criteria.categories().stream().distinct().toList(),
        criteria.brands() == null
            ? List.of()
            : criteria.brands().stream().distinct().toList(),
        criteria.minPrice(),
        criteria.maxPrice(),
        criteria.inStock(),
        criteria.page(),
        safeSize
    );
}
~~~

In a real system, you should also validate categories and brands against allowed catalogs, limit the number of filter values, allowlist sort fields, and cap page size. Security filters like tenantId must come from the server security context, never trusting a client-supplied tenantId.

Important conventions for multiple selections within the same facet:

- Selecting multiple categories usually means OR: audio or computers.
- Combining category and brand usually means AND: in audio and by brand Acme.
- MinPrice and maxPrice both apply to the price field, forming a range condition.
- The inStock=true filter combines with category and price using AND.

For a single-valued category field, a terms query with a list of categories matches documents whose category is one of the selected values. If business rules require a document to match all selected values, express each condition as separate term queries inside bool.filter or adjust the data model accordingly. Do not confuse OR among values of the same facet with AND across different facets.

## 4. Creating Category and Brand Filters with the terms Query

A term query matches a single exact value:

~~~json
{
  "term": {
    "category": "audio"
  }
}
~~~

When the user selects multiple categories, use a terms query:

~~~json
{
  "terms": {
    "category": ["audio", "computers"]
  }
}
~~~

The query above matches documents whose category is audio or computers. It does not require a single document to belong to both categories simultaneously.

A request with multiple facets:

~~~http
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "tenantId": "t-01"
          }
        },
        {
          "terms": {
            "category": ["audio", "computers"]
          }
        },
        {
          "terms": {
            "brand": ["Acme"]
          }
        }
      ]
    }
  }
}
~~~

Conditions inside bool.filter are combined with AND. A document must be active, belong to tenant t-01, have one of the selected categories, and have brand Acme.

Filter context does not calculate relevance scores. It is the right choice for category, brand, status, tenant, and structured conditions. If there is a search keyword, you can put a match query in must and structured conditions in filter.

Example combining text search and filters:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless headphones"
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
          "terms": {
            "category": ["audio"]
          }
        }
      ]
    }
  }
}
~~~

The match condition searches for matching text; filters narrow results by status and category. Facet aggregations in the same request run by default over documents matching the entire top-level query.

## 5. Creating Price Range Filters with the range Query

A range query restricts values using lower and upper bounds.

~~~json
{
  "range": {
    "price": {
      "gte": 500000,
      "lte": 2000000
    }
  }
}
~~~

Operators:

| Operator | Meaning |
|---|---|
| gt | Greater than, exclusive |
| gte | Greater than or equal to, inclusive |
| lt | Less than, exclusive |
| lte | Less than or equal to, inclusive |

If the UI says "500,000 to 2,000,000" and wants both bounds included, use gte and lte. If splitting into contiguous intervals, make the upper bound of the previous range exclusive so documents are not counted twice.

Example adding a price range to the query:

~~~http
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 500000,
              "lte": 2000000
            }
          }
        }
      ]
    }
  }
}
~~~

When only minPrice is present, build a gte condition. When only maxPrice is present, build an lte condition. When both are null, omit the range query. Never build a range query with null bounds or empty strings.

A helper can construct the query for optional inputs:

~~~java
private Query priceRange(Long minPrice, Long maxPrice) {
    return Query.of(q -> q.range(r -> r.number(n -> {
        n.field("price");

        if (minPrice != null) {
            n.gte(minPrice.doubleValue());
        }

        if (maxPrice != null) {
            n.lte(maxPrice.doubleValue());
        }

        return n;
    })));
}
~~~

The Java API Client uses typed range variants for numeric fields. Depending on the client version in use, use the number range variant for a long/numeric price field. If the application uses a date field, use the corresponding date range variant.

Do not convert prices to strings before building the query. Also never send locale-formatted values like "1.500.000" into Elasticsearch.

## 6. Combining Optional Filters in bool.filter

When a criterion is not selected, omit it from the filter list. This keeps the query clean and avoids confusing an empty filter with a populated one.

An illustrative builder:

~~~java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

public class ProductQueryFactory {

    public Query buildSelectedFilters(ProductSearchCriteria criteria) {
        List<Query> filters = new ArrayList<>();

        if (criteria.categories() != null
                && !criteria.categories().isEmpty()) {
            filters.add(Query.of(q -> q.terms(t -> t
                .field("category")
                .terms(tf -> tf.value(
                    criteria.categories().stream()
                        .map(FieldValue::of)
                        .toList()
                ))
            )));
        }

        if (criteria.brands() != null
                && !criteria.brands().isEmpty()) {
            filters.add(Query.of(q -> q.terms(t -> t
                .field("brand")
                .terms(tf -> tf.value(
                    criteria.brands().stream()
                        .map(FieldValue::of)
                        .toList()
                ))
            )));
        }

        if (criteria.minPrice() != null
                || criteria.maxPrice() != null) {
            filters.add(priceRange(
                criteria.minPrice(),
                criteria.maxPrice()
            ));
        }

        return and(filters);
    }

    private Query and(List<Query> filters) {
        if (filters.isEmpty()) {
            return Query.of(q -> q.matchAll(m -> m));
        }

        return Query.of(q -> q.bool(b -> b.filter(filters)));
    }

    private Query priceRange(Long minPrice, Long maxPrice) {
        return Query.of(q -> q.range(r -> r.number(n -> {
            n.field("price");
            if (minPrice != null) {
                n.gte(minPrice.doubleValue());
            }
            if (maxPrice != null) {
                n.lte(maxPrice.doubleValue());
            }
            return n;
        })));
    }
}
~~~

The and() helper returns match_all when there are no selected filters. In a real request, you can also omit withFilter when there are no filters; match_all yields the same logical result.

Rules to keep consistent:

- Each filter is an independent Query.
- Filters across different facets are combined with AND.
- Multiple values within the same category or brand go into a single terms query for OR semantics.
- A price range is added only when at least one bound is present.
- Tenant and active filters always reside in the server's base query.
- Never allow clients to supply raw field names directly into the query builder.

In this example, inStock is an additional base condition rather than a facet with its own counts. If the user filters for in-stock items, add that condition to the base query so every facet respects that status. If you want to show counts for both in-stock and out-of-stock, create a separate facet scope for inStock just like category and brand.

This structure separates request parsing from Elasticsearch DSL construction. It also makes each helper easy to test independently: category query, brand query, price range query, and how they are combined.

## 7. From Search Filters to Faceted Search

If you only need to filter the list, putting every condition in query.bool.filter suffices. However, a faceted search page also needs to display counts for other options so users can continue filtering.

Suppose the user selects:

- Brand = Acme.
- Category = audio.
- Price from 500,000 to 2,000,000.

If all three filters are placed in the top-level query, Elasticsearch computes aggregations only over documents satisfying all three conditions. The category aggregation will then essentially return only audio. The user will not see how many Acme computers or accessories exist in that price range.

There are two common ways to display facets:

**Approach A: Facets independent of all facet selections.** The top-level query holds fixed conditions such as tenant, active, and text search. Category, brand, and price selections go into post_filter. Aggregations are unaffected by any facet selection. This displays overall counts across the base set.

**Approach B: Each facet ignores its own filter while respecting other facets.** Category counts reflect the selected brand and price, but are not restricted by the selected category. Brand counts reflect the selected category and price, but ignore the selected brand. Price ranges reflect the selected category and brand, but are not restricted by the selected price range. This is usually the more natural e-commerce experience.

Approach B is called disjunctive faceting or self-excluding facets. It requires filter aggregations with a dedicated scope for each facet.

## 8. Distinguishing Query Filter and post_filter

Elasticsearch has two important places for filtering:

- bool.filter inside query.
- post_filter at the Search API request level.

bool.filter applies to both hits and aggregations. post_filter applies only after aggregations have been computed, so it narrows search hits without narrowing aggregation results.

Example:

~~~http
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "tenantId": "t-01"
          }
        }
      ]
    }
  },
  "post_filter": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "audio"
          }
        },
        {
          "range": {
            "price": {
              "gte": 500000,
              "lte": 2000000
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    },
    "brands": {
      "terms": {
        "field": "brand"
      }
    }
  }
}
~~~

In this request:

- Query restricts to active products belonging to tenant t-01.
- post_filter selects category audio and price within the range.
- Hits contain only audio products within the price range.
- The categories and brands aggregations run over all active products of tenant t-01, including other categories and prices.

This is Approach A: every facet ignores all selected facet filters.

Never place tenant or access-control filters only in post_filter. Aggregations run before post_filter and could aggregate data outside the user's authorized scope. Mandatory security and data-scope conditions must reside in the top-level query, or be equivalently enforced in every aggregation scope if global aggregations are used.

## 9. Creating a Dedicated Scope for Each Facet

To achieve Approach B, the top-level query still holds the base conditions. post_filter holds all user-selected filters to filter the hits. Each aggregation is wrapped in a filter aggregation containing only the selected filters other than the facet being computed.

Suppose the user selected:

~~~json
{
  "categories": ["audio"],
  "brands": ["Acme"],
  "minPrice": 500000,
  "maxPrice": 2000000
}
~~~

Scopes needed:

| Aggregation | Applied filter scope | Ignored filter |
|---|---|---|
| category facet | brand Acme + price 500,000–2,000,000 | category |
| brand facet | category audio + price 500,000–2,000,000 | brand |
| price facet | category audio + brand Acme | price |

Complete request:

~~~http
GET /products/_search
{
  "size": 20,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "tenantId": "t-01"
          }
        }
      ]
    }
  },
  "post_filter": {
    "bool": {
      "filter": [
        {
          "terms": {
            "category": ["audio"]
          }
        },
        {
          "terms": {
            "brand": ["Acme"]
          }
        },
        {
          "range": {
            "price": {
              "gte": 500000,
              "lte": 2000000
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "category_scope": {
      "filter": {
        "bool": {
          "filter": [
            {
              "terms": {
                "brand": ["Acme"]
              }
            },
            {
              "range": {
                "price": {
                  "gte": 500000,
                  "lte": 2000000
                }
              }
            }
          ]
        }
      },
      "aggs": {
        "categories": {
          "terms": {
            "field": "category",
            "size": 30
          }
        }
      }
    },
    "brand_scope": {
      "filter": {
        "bool": {
          "filter": [
            {
              "terms": {
                "category": ["audio"]
              }
            },
            {
              "range": {
                "price": {
                  "gte": 500000,
                  "lte": 2000000
                }
              }
            }
          ]
        }
      },
      "aggs": {
        "brands": {
          "terms": {
            "field": "brand",
            "size": 30
          }
        }
      }
    },
    "price_scope": {
      "filter": {
        "bool": {
          "filter": [
            {
              "terms": {
                "category": ["audio"]
              }
            },
            {
              "terms": {
                "brand": ["Acme"]
              }
            }
          ]
        }
      },
      "aggs": {
        "price_ranges": {
          "range": {
            "field": "price",
            "keyed": true,
            "ranges": [
              {
                "key": "under-500k",
                "to": 500000
              },
              {
                "key": "500k-2m",
                "from": 500000,
                "to": 2000000
              },
              {
                "key": "2m-5m",
                "from": 2000000,
                "to": 5000000
              },
              {
                "key": "5m-plus",
                "from": 5000000
              }
            ]
          }
        }
      }
    }
  }
}
~~~

How to read the request:

1. Query restricts the entire request to active products of tenant t-01.
2. post_filter applies the selected category, brand, and price to hits.
3. category_scope applies brand and price, then groups by category.
4. brand_scope applies category and price, then groups by brand.
5. price_scope applies category and brand, then divides price into ranges.
6. Each aggregation returns document counts for its own scope.

A global aggregation is not needed here because the top-level query already defines the right base document set. Filter aggregations simply narrow that base set further for each facet.

If you use a global aggregation, it bypasses the top-level query. In that case, you must repeat security filters such as tenant, access status, and data permissions inside every scope. That easily causes cross-tenant count leakage, so use global only when you genuinely need to escape the top-level query and have carefully redesigned the data scope.

## 10. Understanding Counts in Each Facet

Suppose the dataset has the following active products:

| ID | Category | Brand | Price |
|---|---|---|---:|
| p-1 | audio | Acme | 1,200,000 |
| p-2 | audio | Acme | 1,800,000 |
| p-3 | audio | Nova | 850,000 |
| p-4 | computers | Acme | 1,900,000 |
| p-5 | computers | Nova | 4,200,000 |
| p-6 | accessories | Acme | 650,000 |
| p-7 | audio | Acme | 3,200,000 |

The user selects category audio, brand Acme, and price range 500,000–2,000,000.

Hits are reduced to p-1 and p-2.

However, the facet counts under self-excluding scopes will be:

**Category facet** applies brand Acme and the price range:

- audio: 2.
- computers: 1.
- accessories: 1.

**Brand facet** applies category audio and the price range:

- Acme: 2.
- Nova: 1.

**Price facet** applies category audio and brand Acme:

- under 500,000: 0.
- 500,000–2,000,000: 2.
- 2,000,000–5,000,000: 1.
- 5,000,000 and above: 0.

Thus, the product list obeys all selections. The counts in each facet reflect what happens if the user changes that single selection while keeping all other selections fixed.

If instead of self-excluding facets you run a plain terms aggregation after post_filter, category counts will cover all active products of the tenant regardless of selected brand or price. Both approaches are valid as long as they match the intended UX; the key is not confusing the semantics of the counts.

## 11. Terms Aggregation for Categories and Brands

A terms aggregation groups documents by the values of a keyword field.

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 30,
        "order": {
          "_count": "desc"
        }
      }
    }
  }
}
~~~

The response looks like:

~~~json
{
  "categories": {
    "doc_count_error_upper_bound": 0,
    "sum_other_doc_count": 0,
    "buckets": [
      {
        "key": "audio",
        "doc_count": 42
      },
      {
        "key": "computers",
        "doc_count": 27
      },
      {
        "key": "accessories",
        "doc_count": 18
      }
    ]
  }
}
~~~

Each bucket contains:

- key: the category value.
- doc_count: number of documents in the bucket.
- Optionally distributed error bounds depending on terms aggregation configuration.

size limits the number of returned buckets. If you only display the top 10 brands, do not fetch tens of thousands of buckets and slice the list in Java.

By default, terms aggregation prioritizes buckets with high document counts. When data is distributed across multiple shards, counts can have error bounds if a shard does not send enough candidate buckets to the coordinating node. You can tune shard_size to increase candidate buckets, balancing memory, network, and reduce cost.

If categories are a business-managed set of values and the UI needs to show options with count 0 as well, do not rely solely on a terms aggregation. Terms aggregations normally return only values present in the matching documents. You can use a filters aggregation with a fixed list of categories, or fetch categories from a catalog service and merge counts from Elasticsearch.

Example filters aggregation for a fixed set of categories:

~~~json
{
  "aggs": {
    "category_counts": {
      "filters": {
        "filters": {
          "audio": {
            "term": {
              "category": "audio"
            }
          },
          "computers": {
            "term": {
              "category": "computers"
            }
          },
          "accessories": {
            "term": {
              "category": "accessories"
            }
          }
        }
      }
    }
  }
}
~~~

A filters aggregation returns a bucket for every declared filter, including buckets with doc_count equal to 0. This is a good fit when the UI needs a fixed facet list managed outside the index.

## 12. Range Aggregation for Price Ranges

A range aggregation splits numeric values into application-defined buckets.

~~~json
{
  "aggs": {
    "price_ranges": {
      "range": {
        "field": "price",
        "keyed": true,
        "ranges": [
          {
            "key": "under-500k",
            "to": 500000
          },
          {
            "key": "500k-2m",
            "from": 500000,
            "to": 2000000
          },
          {
            "key": "2m-5m",
            "from": 2000000,
            "to": 5000000
          },
          {
            "key": "5m-plus",
            "from": 5000000
          }
        ]
      }
    }
  }
}
~~~

Each range includes the lower bound and excludes the upper bound:

- under-500k: price < 500,000.
- 500k-2m: 500,000 <= price < 2,000,000.
- 2m-5m: 2,000,000 <= price < 5,000,000.
- 5m-plus: price >= 5,000,000.

Because the upper bound is exclusive, a product priced at exactly 2,000,000 belongs to bucket 2m-5m under the definition above. If the UI expects "500,000 to 2,000,000" to include 2,000,000, pick the next boundary according to the smallest currency unit or define buckets consistently with the business convention. Never let display labels and query boundaries diverge.

In a range aggregation, ranges can overlap. A document can be counted in multiple buckets if its price falls into intersecting ranges. For contiguous price facets, design non-overlapping ranges with no gaps between adjacent buckets.

If the UI displays localized labels, use stable keys like under-500k and 500k-2m and map them to labels in the application. Do not rely on the key as the sole display text because language, currency, and number formatting can change.

## 13. Histogram or Range Aggregation?

These two aggregations are often confused:

| Aggregation | How buckets are split | When appropriate |
|---|---|---|
| range | Application defines each interval | Business-meaningful price groups |
| histogram | Fixed numeric interval | Price distribution charts or continuous metrics |
| terms | Group by categorical value | Category, brand, status |

Example histogram with interval 500,000:

~~~json
{
  "aggs": {
    "price_histogram": {
      "histogram": {
        "field": "price",
        "interval": 500000,
        "min_doc_count": 0
      }
    }
  }
}
~~~

Histograms are useful for distribution charts or trend analysis. Range aggregations fit better when the UI has fixed options like "Under 500,000", "500,000–2,000,000", and "Over 2,000,000".

Histograms create equally spaced intervals. If business price brackets have unequal widths, use a range aggregation to define them precisely.

## 14. Adding Statistical Metrics to Facets

Beyond doc_count, the application may need the minimum, maximum, or average price of products in the current scope.

Example:

~~~json
{
  "aggs": {
    "price_stats": {
      "stats": {
        "field": "price"
      }
    },
    "average_price": {
      "avg": {
        "field": "price"
      }
    },
    "minimum_price": {
      "min": {
        "field": "price"
      }
    },
    "maximum_price": {
      "max": {
        "field": "price"
      }
    }
  }
}
~~~

If the metrics must respect selected facets, place them inside the appropriate scoped filter aggregation, such as price_scope. If the metrics summarize the tenant's entire active product catalog, place them as top-level aggregations on the base query.

Metrics have distinct meanings:

- avg: arithmetic mean of present price values.
- min: smallest price.
- max: largest price.
- stats: count, min, max, avg, and sum.
- value_count: number of field values, which does not necessarily equal the document count if a field is multi-valued.

Do not use average price to infer the median. If the UI needs median or percentiles, use a percentiles aggregation and account for algorithmic cost and accuracy.

## 15. Handling Missing Values and Inconsistent Data

A document may lack a category, brand, or price. Default aggregations usually skip documents without a value in the grouped or measured field.

This can make the sum of bucket counts smaller than the total number of documents in scope.

If you need to represent uncategorized products, you can use a missing aggregation or configure a missing value on supported aggregations. In a terms aggregation, the missing parameter assigns a fallback value to documents lacking the field.

Example:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "missing": "uncategorized"
      }
    }
  }
}
~~~

Distinguish two situations:

- The field does not exist.
- The field exists but has an empty or non-standard value.

Normalize data at the ingest or application layer. Do not let "Audio", "audio", " AUDIO ", and "audio " become separate buckets when the business considers them the same category.

If legacy data has the wrong field type or was not indexed as keyword/numeric, you may need to reindex into a new mapping. You cannot arbitrarily convert an existing text field into keyword simply by changing code annotations.

## 16. Sorting and Pagination Alongside Faceted Search

A faceted search request typically returns both hits and aggregations. You can use Pageable to limit hits:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(baseQuery)
    .withFilter(postFilter)
    .withPageable(PageRequest.of(0, 20))
    .withAggregation("category_scope", categoryScope)
    .withAggregation("brand_scope", brandScope)
    .withAggregation("price_scope", priceScope)
    .build();
~~~

Aggregations are computed over the documents in their respective scopes; page size limits only the returned hits. Never set search size to control how many facet buckets appear. Bucket count is controlled by the size of the terms aggregation or the defined ranges.

Sorting can be declared separately:

~~~java
.withSort(SortOptions.of(s -> s.field(f -> f
    .field("price")
    .order(SortOrder.Asc)
)))
~~~

When sorting by price, add a tie-breaker if using cursor pagination to avoid unstable ordering among documents with equal prices. For shallow pagination, PageRequest is suitable; if users paginate very deeply, consider search_after and PIT as a separate pagination strategy.

If the UI requires exact page counts, explicitly decide whether to track exact total hits. If only a "next page" button is needed, you can avoid unnecessary exact counting. Facet aggregation counts do not replace the total hits of the search request.

## 17. SearchHits Results in Spring Data Elasticsearch

SearchOperations returns SearchHits<T>, which contains:

- List of SearchHit<T>.
- Total hits and relation.
- Execution time.
- Aggregations.
- Suggest results if present.
- Other search metadata.

Example:

~~~java
SearchHits<Product> searchHits =
    operations.search(nativeQuery, Product.class);

List<Product> products = searchHits.getSearchHits().stream()
    .map(SearchHit::getContent)
    .toList();

long totalHits = searchHits.getTotalHits();

AggregationsContainer<?> aggregationContainer =
    searchHits.getAggregations();
~~~

Aggregation container is a Spring Data abstraction. With the Elasticsearch Java Client, the concrete implementation is ElasticsearchAggregations. You can look up an aggregation by name and convert it into an application DTO.

~~~java
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);

ElasticsearchAggregations aggregations =
    (ElasticsearchAggregations) hits.getAggregations();

var categoryScope = aggregations.get("category_scope")
    .aggregation()
    .getAggregate();

var categoryBuckets = categoryScope.filter()
    .aggregations()
    .get("categories")
    .sterms()
    .buckets()
    .array();
~~~

For a terms aggregation on a keyword field, the response variant is string terms. The Java API Client can represent keys as FieldValue; in recent client versions, retrieve the string via key().stringValue(). The variant type must match the sent aggregation. If you change the field to long or the aggregation to range, the response parsing must change accordingly.

Example converting buckets to DTOs:

~~~java
public record FacetOption(
    String value,
    long count
) {
}
~~~

~~~java
List<FacetOption> categoryOptions = categoryBuckets.stream()
    .map(bucket -> new FacetOption(
        bucket.key().stringValue(),
        bucket.docCount()
    ))
    .toList();
~~~

Do not return deep Java Client types directly from controllers unless needed. Create stable application DTOs so the UI does not depend on Elasticsearch's internal response structure.

## 18. Building Aggregations with the Java API Client

Spring Data NativeQuery supports aggregations from the Elasticsearch Java API Client. A helper can create a terms facet inside a filter scope:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

private Aggregation termsFacet(
        Query scope,
        String field,
        int size) {

    return Aggregation.of(a -> a
        .filter(scope)
        .aggregations("values", values -> values
            .terms(t -> t
                .field(field)
                .size(size)
            )
        )
    );
}
~~~

With the helper above, the outer aggregation is a filter aggregation. The terms aggregation lives in a sub-aggregation named values.

A helper for price ranges:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import co.elastic.clients.elasticsearch._types.aggregations.AggregationRange;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

private Aggregation priceRangeFacet(Query scope) {
    return Aggregation.of(a -> a
        .filter(scope)
        .aggregations("ranges", ranges -> ranges
            .range(r -> r
                .field("price")
                .keyed(true)
                .ranges(
                    AggregationRange.of(b -> b
                        .key("under-500k")
                        .to(500000.0)
                    ),
                    AggregationRange.of(b -> b
                        .key("500k-2m")
                        .from(500000.0)
                        .to(2000000.0)
                    ),
                    AggregationRange.of(b -> b
                        .key("2m-plus")
                        .from(2000000.0)
                    )
                )
            )
        )
    );
}
~~~

AggregationRange.from is an inclusive lower bound and to is an exclusive upper bound. Keys help the application identify buckets without parsing Elasticsearch-generated strings.

Building the complete query:

~~~java
List<Query> baseFilters = new ArrayList<>(List.of(
    term("active", true),
    term("tenantId", currentTenantId)
));

if (criteria.inStock() != null) {
    baseFilters.add(term("inStock", criteria.inStock()));
}

Query baseQuery = and(baseFilters);

Query categoryScope = and(concat(
    selectedBrandFilters,
    selectedPriceFilters
));

Query brandScope = and(concat(
    selectedCategoryFilters,
    selectedPriceFilters
));

Query priceScope = and(concat(
    selectedCategoryFilters,
    selectedBrandFilters
));

Query postFilter = and(concat(
    selectedCategoryFilters,
    selectedBrandFilters,
    selectedPriceFilters
));

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(baseQuery)
    .withFilter(postFilter)
    .withPageable(PageRequest.of(criteria.page(), criteria.size()))
    .withAggregation(
        "category_scope",
        termsFacet(categoryScope, "category", 30)
    )
    .withAggregation(
        "brand_scope",
        termsFacet(brandScope, "brand", 30)
    )
    .withAggregation(
        "price_scope",
        priceRangeFacet(priceScope)
    )
    .build();
~~~

In the snippet above, selectedCategoryFilters, selectedBrandFilters, and selectedPriceFilters are constructed from the validated DTO. The concat helper combines whichever queries are present. The and helper returns match_all when the list is empty.

NativeQueryBuilder provides separate methods for withQuery, withFilter, and withAggregation. In NativeQuery, withFilter represents the Search API's post_filter. Mistakenly putting selected facets in withQuery causes them to restrict aggregations, making facet counts behave differently from the self-excluding design.

## 19. Separating Query Construction from Result Mapping

Avoid stuffing request parsing, DSL building, Elasticsearch execution, and aggregation mapping into the controller.

You can separate responsibilities:

- ProductSearchCriteria: validated filter data.
- ProductQueryFactory: builds the base query, post-filter, and aggregation scopes.
- ProductSearchService: invokes ElasticsearchOperations.
- FacetMapper: converts aggregation buckets into DTOs.
- ProductSearchResponse: structure returned by the API.

Example response DTOs:

~~~java
import java.util.List;

public record ProductSearchResponse(
    List<Product> items,
    long totalHits,
    List<FacetOption> categories,
    List<FacetOption> brands,
    List<PriceFacetOption> priceRanges
) {
}

public record FacetOption(
    String value,
    long count
) {
}

public record PriceFacetOption(
    String key,
    long count,
    Double from,
    Double to
) {
}
~~~

The service can execute:

~~~java
public ProductSearchResponse search(ProductSearchCriteria criteria) {
    NativeQuery query = queryFactory.build(criteria, currentTenantId());

    SearchHits<Product> hits =
        operations.search(query, Product.class);

    List<Product> products = hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();

    FacetResult facets = facetMapper.map(hits.getAggregations());

    return new ProductSearchResponse(
        products,
        hits.getTotalHits(),
        facets.categories(),
        facets.brands(),
        facets.priceRanges()
    );
}
~~~

FacetMapper handles aggregation names and typed variants. If an expected aggregation is missing from the response, fail loudly or provide an intentional default. Never cast a terms aggregation as a range aggregation or vice versa.

If the application uses a reactive stack, you can use ReactiveElasticsearchOperations and return publishers. Query building and aggregation definitions remain similar; only the execution API and return types change. Never call block on a WebFlux request path to turn a reactive operation synchronous.

## 20. Optimizing Bucket Counts and Aggregation Cost

Faceted search often runs every time a user toggles a filter. A single request may carry multiple aggregations, so bucket counts and document scopes must be controlled.

Guidelines:

- Cap terms aggregation size to the number of options the UI actually renders.
- Use keyword or numeric fields that have doc values.
- Narrow the base set using tenant, active, access permissions, and base text query.
- Do not aggregate on a text field without a keyword subfield.
- Use range aggregations for business-meaningful price brackets.
- Use filters aggregations when the option list is fixed and 0-count buckets are needed.
- Avoid deeply nested high-cardinality terms aggregations if the UI does not need them.
- Consider caching facet results when queries and data change infrequently.

Do not set an enormous size just to guarantee every category appears. If a catalog has thousands of categories, fetch the category list from the catalog source and use aggregations for counts or paginate facet options separately.

If buckets must appear in a business order such as category priority, do not rely on terms aggregation's default ordering. Fetch bucket counts and sort according to catalog order in the application, or use a keyed filters aggregation for a small fixed set.

## 21. Choosing Exact Semantics for Prices and Buckets

Price is one of the easiest places to introduce bugs because a range slider filter and a price facet can easily use different boundary rules.

Suppose the UI offers three choices:

| Label | Condition |
|---|---|
| Under 500,000 | price < 500,000 |
| 500,000 to under 2,000,000 | 500,000 <= price < 2,000,000 |
| From 2,000,000 | price >= 2,000,000 |

These conditions neither overlap nor leave gaps.

If the UI lets users enter arbitrary min and max values, a slider query can use gte and lte to include both bounds. Document this contract clearly in the API so frontend and backend do not interpret boundaries differently.

Do not use bucket values as slider min/max bounds if products can lack a price or have outlier values. You can run dedicated min/max aggregations paired with business limits and validation.

For currency, perform number formatting only in the UI or presentation layer. Elasticsearch stores integers or scaled numerics for reliable comparison and aggregation.

## 22. Testing Filters and Facet Counts

You can verify the query factory with unit tests, but proving that mappings, query DSL, and aggregations actually work requires integration tests against Elasticsearch.

Use a small dataset with known counts:

| ID | Category | Brand | Price | Active |
|---|---|---|---:|---|
| p-1 | audio | Acme | 1,200,000 | true |
| p-2 | audio | Acme | 1,800,000 | true |
| p-3 | audio | Nova | 850,000 | true |
| p-4 | computers | Acme | 1,900,000 | true |
| p-5 | computers | Nova | 4,200,000 | true |
| p-6 | accessories | Acme | 650,000 | true |
| p-7 | audio | Acme | 3,200,000 | true |
| p-8 | audio | Acme | 1,500,000 | false |

Test cases should verify:

1. Only active products are included in the base query.
2. Selecting audio and computers returns products in either category.
3. Selecting multiple brands uses OR semantics.
4. minPrice and maxPrice enforce boundaries accurately.
5. post_filter filters hits without altering aggregation scopes.
6. The category facet ignores category selection while applying brand and price.
7. The brand facet ignores brand selection while applying category and price.
8. The price facet ignores price selection while applying category and brand.
9. Empty buckets are represented according to the UI contract.
10. Tenant filters are never bypassed in any aggregation.

Example test asserting query results:

~~~java
@Test
void shouldReturnHitsAndSelfExcludingCategoryCounts() {
    ProductSearchCriteria criteria = new ProductSearchCriteria(
        List.of("audio"),
        List.of("Acme"),
        500000L,
        2000000L,
        null,
        0,
        20
    );

    ProductSearchResponse response = searchService.search(criteria);

    assertThat(response.items())
        .extracting(Product::getId)
        .containsExactlyInAnyOrder("p-1", "p-2");

    assertThat(response.categories())
        .contains(
            new FacetOption("audio", 2),
            new FacetOption("computers", 1),
            new FacetOption("accessories", 1)
        );
}
~~~

The test assumes the dataset has been indexed and refreshed before running the search. In integration tests, create the index/mapping, seed documents, refresh, and then call the service. Never use Thread.sleep to wait for data to become searchable.

If tests only cover the query factory, you can verify that filter lists are built properly without a container. However, those unit tests do not prove Elasticsearch interprets the query and aggregations with the right semantics.

## 23. Common Pitfalls When Implementing Faceted Search

**Putting every filter in query.bool.filter.** Both hits and aggregations are constrained by all filters. The category facet may show only the selected category.

**Using post_filter and expecting aggregations to be filtered too.** post_filter only narrows hits after aggregations run. If facet counts must respect certain other filters, you must define explicit filter aggregation scopes.

**Putting tenant filters in post_filter.** Aggregations run before post_filter and could count data outside the tenant. Tenant and access controls must be enforced in the base query or every equivalent scope.

**Confusing OR within a facet with AND across facets.** Multiple categories typically use a terms query; category combines with brand and price via AND.

**Using a term query on a text field.** Full-text mappings analyze strings. Exact filters should target keyword fields.

**Storing formatted price strings.** Range queries and numeric aggregations require numeric fields.

**Leaving overlaps or gaps in price ranges.** A product could be counted twice or fall into no bucket. The inclusive-from, exclusive-to convention must align with UI labels.

**Assuming terms aggregation always returns every value.** Terms returns top buckets up to size. Use a filters aggregation or a catalog service when a fixed facet list is required.

**Using search hit size to control facet option count.** Search size and terms aggregation size are independent parameters.

**Adding too many unnecessary aggregations.** Each facet scope adds cluster work. Compute only the facets the UI actually displays or requires.

**Using a global aggregation and forgetting the tenant filter.** Global bypasses the top-level query. If used, all data-scope and security filters must be reapplied.

**Exposing raw Elasticsearch aggregation objects in the API.** This couples your application contract tightly to the client library. Map results into stable DTOs.

**Ignoring documents missing fields.** Documents lacking category, brand, or price may be omitted from buckets. Decide explicitly whether an "Uncategorized" bucket is needed.

**Failing to bound inputs.** A request with thousands of categories or a huge page size can create heavy queries and oversized responses. Validate and cap inputs on the server.

**Computing facet counts via multiple separate requests.** This introduces extra round trips and numbers from different points in time. When appropriate, combine hits and aggregations in a single Search API request.

## 24. Workflow for Building a Faceted Search Endpoint

You can implement it in this sequence:

1. Identify filterable fields and choose appropriate mappings.
2. Design DTOs for category, brand, price, status, page, and sort.
3. Validate inputs, normalize values, and cap page size.
4. Build the base query containing tenant, permissions, active, and base keywords.
5. Build selected facet filters for category, brand, and price.
6. Put all selected facet filters into post_filter to filter hits.
7. Build the category aggregation scope excluding the category filter.
8. Build the brand aggregation scope excluding the brand filter.
9. Build the price aggregation scope excluding the price filter.
10. Add terms aggregations for category and brand.
11. Add a range aggregation for price brackets.
12. Send a single NativeQuery via ElasticsearchOperations.
13. Read hits, total hits, and aggregations from SearchHits.
14. Map buckets into application DTOs.
15. Test every filter and facet's semantics against real Elasticsearch.
16. Monitor latency and bucket limits when rolling out to production.

## Conclusion

A faceted search endpoint brings together three elements: filters for the document list, aggregations to count options, and rules defining the document set for each facet. Category and brand typically use terms queries; price ranges use range queries. Terms aggregations produce counts per categorical value, while range aggregations partition prices into well-defined intervals.

In Elasticsearch, bool.filter affects both hits and aggregations. post_filter affects only hits after aggregations have executed. For interfaces requiring self-excluding facets, keep tenant, status, and base conditions in the query; place all facet selections in post_filter; and create a filter aggregation scope for each facet that applies all selected filters except that facet's own filter.

Spring Data Elasticsearch NativeQueryBuilder supports combining withQuery, withFilter, and withAggregation in a single request. SearchHits provides hits, total count, and the aggregation container. Map aggregation buckets into application DTOs so controllers and UIs depend only on business contracts. When field mappings, price boundaries, and OR/AND semantics are designed consistently, faceted search returns both matching items and meaningful facet counts for subsequent filtering.

## References

- [Elasticsearch — Filter search results and post_filter](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/filter-search-results)
- [Elasticsearch — Boolean query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-bool-query)
- [Elasticsearch — Terms aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-terms-aggregation)
- [Elasticsearch — Range aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-range-aggregation)
- [Elasticsearch — Filters aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-filters-aggregation)
- [Elasticsearch — Aggregations](https://www.elastic.co/docs/explore-analyze/query-filter/aggregations)
- [Elasticsearch Java API Client — Aggregations](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/aggregations)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — NativeQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch — ElasticsearchAggregations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchAggregations.html)
