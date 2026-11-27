# Handling Missing Fields, Multi-Valued Fields, and Nested Sorting

Sorting search results in Elasticsearch involves more than picking a field and setting an ascending or descending order. A document may lack a value for the sorted field; a field may contain multiple values; or the value to sort by may reside inside an array of objects mapped as nested.

Spring Data Elasticsearch provides abstractions such as Sort, Pageable, and NativeQuery to build sorts. For simple cases, Sort.by(...) is usually sufficient. When you need to specify how missing values are handled, select a representative value from a multi-valued field, or filter nested objects before sorting, the application needs to configure Elasticsearch Query DSL sort options.

This lesson explains three scenarios:

- **Missing values:** documents that have no value usable for sorting.
- **Multi-valued fields:** a field containing multiple values where one value must be chosen to represent the document.
- **Nested sort:** sorting parent documents based on fields inside child nested objects.

## 1. Sorting Operates on Indexed Fields

Elasticsearch sorts based on indexed values and the mapping's sorting capabilities. Sorting is not simply reading strings from _source and comparing them like in Java.

For example:

~~~json
{
  "sku": "KB-1042",
  "name": "Mechanical Keyboard",
  "price": 129.5,
  "createdAt": "2026-03-12T08:30:00Z"
}
~~~

Query DSL sorting by price ascending:

~~~json
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

With Spring Data Elasticsearch, basic sorting can be written as:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
    .withQuery(textQuery)
    .withSort(Sort.by(Sort.Order.asc("price")))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Sort.Order.asc("price") represents ascending order, and PageRequest limits the number of results per page. For simple field sorts, Spring Data translates this abstraction into an Elasticsearch sort request.

### 1.1. Which Fields Can Be Sorted?

| Field type | Sort capability and notes |
| --- | --- |
| keyword | Sorts in lexicographical order; commonly used for codes, statuses, normalized names |
| numeric | Sorts by numeric value |
| date/date_nanos | Sorts chronologically by timestamp |
| boolean | Sorts by boolean value |
| ip | Can sort by IP address order |
| geo_point | Uses geo distance sort instead of standard value sorting |
| text | Unsuitable for sorting by default; usually sorted on a keyword multi-field |
| object | Cannot sort directly on an entire object; specify an appropriate child field |
| nested | Requires nested sort when sorting by fields of nested objects |

Example text field with a multi-field:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Sort by name.keyword to compare keyword values. Do not enable fielddata on text solely for sorting without evaluating memory cost; a keyword multi-field is usually the better option.

## 2. Handling Documents Missing a Sort Value

A document may omit the field used for sorting. For example:

~~~json
[
  {
    "sku": "A-100",
    "price": 100
  },
  {
    "sku": "A-200",
    "price": 150
  },
  {
    "sku": "A-300"
  },
  {
    "sku": "A-400",
    "price": null
  }
]
~~~

When sorting by price, documents without an indexable value for this field need to be placed in a defined position. Elasticsearch allows configuring the missing attribute in sort.

### 2.1. Placing Missing Values Last

~~~json
{
  "sort": [
    {
      "price": {
        "order": "asc",
        "missing": "_last"
      }
    }
  ]
}
~~~

missing: "_last" places hits without a sort value at the end of the results. This is usually the right choice when sorting price ascending and wanting unpriced products to appear after priced ones.

### 2.2. Placing Missing Values First

~~~json
{
  "sort": [
    {
      "price": {
        "order": "desc",
        "missing": "_first"
      }
    }
  ]
}
~~~

missing: "_first" places hits missing a value at the beginning. This can be used when a UI wants to prioritize documents that need data completion.

### 2.3. Using a Replacement Value

Instead of placing them first or last, you can treat missing values as a specific value:

~~~json
{
  "sort": [
    {
      "price": {
        "order": "asc",
        "missing": 0
      }
    }
  ]
}
~~~

For keyword sorts, the replacement value must be compatible with the field type:

~~~json
{
  "sort": [
    {
      "status": {
        "order": "asc",
        "missing": "unknown"
      }
    }
  ]
}
~~~

The replacement value directly affects the document's position in the results. Only use a value that has business meaning and is mapping-compatible; do not choose an arbitrary sentinel that causes real data to be misordered.

### 2.4. Default Missing Behavior

If missing is not declared, Elasticsearch defaults to placing documents with missing values at the end of the sort list. However, declare it explicitly when the placement of documents lacking data is significant to the UI or API contract.

This rule applies to sorting on fields without indexable values. For specialized field types or requests, consult the documentation for your exact Elasticsearch version.

## 3. Null, Non-Existent Fields, and null_value

In Elasticsearch, the following cases are not necessarily distinguished when sorting:

- Field does not appear in JSON.
- Field has a JSON value of null.
- Field is an empty array.
- Field has an array with no indexable elements.

Typically, null values do not produce indexable values. During sorting, these cases are treated as missing values.

### 3.1. Using null_value in Mapping

A mapping can specify a replacement value when null is received:

~~~json
{
  "properties": {
    "priority": {
      "type": "integer",
      "null_value": -1
    }
  }
}
~~~

When a document sends "priority": null, Elasticsearch indexes the replacement value -1 for search and sorting. null_value does not add the field into _source; it affects how null values are indexed.

If a document omits the priority field, there is no null value to replace, and the field remains missing. Therefore, null_value is not synonymous with missing in sort.

### 3.2. Distinguishing null_value and missing

| Mechanism | When it takes effect | Meaning |
| --- | --- | --- |
| mapping null_value | When indexing a document with a null value | Indexes a replacement value for null |
| sort missing | When executing sort | Controls how hits with no sort value are ordered |

If you want every document lacking priority to be treated as priority 0 in queries and sorts, you may need to combine write-time rules or an appropriate mapping. Do not assume null_value automatically handles omitted fields as well.

## 4. Missing Values in Multi-Index Search

When searching across multiple indices, some indices may lack the field being sorted on. This case differs from a document missing a field in an index that already has the mapping.

For example:

- catalog-products-v1 has the price field.
- catalog-products-v2 has both price and discountPrice.
- A historical index has not declared discountPrice.

You can use unmapped_type in sort to specify the field type when an index lacks the corresponding mapping:

~~~json
{
  "sort": [
    {
      "discountPrice": {
        "order": "asc",
        "unmapped_type": "double",
        "missing": "_last"
      }
    }
  ]
}
~~~

unmapped_type handles the case where a field is not mapped in one of the indices in the search scope. missing handles documents that lack a value for an already-mapped field. The two attributes solve two distinct situations.

If indices declare the same field using incompatible types, standardize the mapping or use an appropriate per-index solution. unmapped_type cannot fix existing mapping type conflicts.

## 5. Multi-Valued Fields

Elasticsearch allows a field to contain multiple values of the same type without declaring a separate array type.

For example:

~~~json
{
  "sku": "KB-1042",
  "priceHistory": [120, 100, 95]
}
~~~

When sorting by priceHistory, Elasticsearch needs to pick a representative value to compare the document against others. The mode attribute controls how the value is selected or aggregated.

### 5.1. Sort Modes

| Mode | How the value is chosen | Suitable for |
| --- | --- | --- |
| min | Smallest value among elements | Lowest price, earliest date |
| max | Largest value among elements | Highest price, latest date |
| sum | Sum of values | Total quantity or total score |
| avg | Average of values | Average rating or average price |
| median | Median of values | Middle value, less affected by outliers |

min and max can be used with many sort types. sum, avg, and median are suited for numeric types; do not use them as a way to aggregate keyword strings.

### 5.2. Sorting by Lowest Price

~~~json
{
  "sort": [
    {
      "priceHistory": {
        "order": "asc",
        "mode": "min"
      }
    }
  ]
}
~~~

The document with array [120, 100, 95] is compared using the value 95.

### 5.3. Sorting by Highest Price

~~~json
{
  "sort": [
    {
      "priceHistory": {
        "order": "desc",
        "mode": "max"
      }
    }
  ]
}
~~~

The document above is compared using the value 120.

### 5.4. Sorting by Average and Median

~~~json
{
  "sort": [
    {
      "ratingHistory": {
        "order": "desc",
        "mode": "avg"
      }
    },
    {
      "responseTimes": {
        "order": "asc",
        "mode": "median"
      }
    }
  ]
}
~~~

If ratingHistory is [3, 5, 4], the value used for avg sorting is 4. Median is useful when data contains large outliers and you want the middle value as representative. Check performance cost and suitability for the array sizes in your documents.

### 5.5. Default Mode

If mode is omitted:

- Ascending sort typically uses min.
- Descending sort typically uses max.

This rule picks the value closest to the top of the list according to the sort direction. However, declare mode explicitly if the results have business significance, especially when the same query can toggle sort direction.

## 6. Multi-Valued Strings and Keywords

A keyword field can contain multiple values:

~~~json
{
  "name": "Keyboard",
  "aliases": ["keyboard", "mechanical keyboard", "key board"]
}
~~~

Sorting on a multi-valued keyword field typically uses min or max in lexicographical order. This is the order of indexed values, not order by relevance or string length.

~~~json
{
  "sort": [
    {
      "aliases": {
        "order": "asc",
        "mode": "min"
      }
    }
  ]
}
~~~

If the goal is to sort by a primary display name, store a dedicated field such as displayName.keyword instead of expecting Elasticsearch to automatically pick the alias appropriate for users.

## 7. What Is Nested Sort?

Suppose a product document contains a list of offers:

~~~json
{
  "sku": "KB-1042",
  "offers": [
    {
      "seller": "seller-a",
      "price": 120,
      "available": true
    },
    {
      "seller": "seller-b",
      "price": 95,
      "available": true
    },
    {
      "seller": "seller-c",
      "price": 80,
      "available": false
    }
  ]
}
~~~

If offers is mapped as nested, sorting by offers.price requires knowing which nested documents are evaluated and how their values are combined into a single sort value for the parent document.

Nested sort has three key parts:

1. path identifies the nested field.
2. filter restricts which nested documents are used to compute the sort value.
3. mode chooses the value or aggregation across the filtered nested documents.

Nested sort still sorts parent documents. It does not turn search results into a list of offers.

### 7.1. Nested Mapping

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

    @Field(type = FieldType.Nested)
    private List<ProductOffer> offers;

    // Constructors, getters, and setters
}

public class ProductOffer {

    @Field(type = FieldType.Keyword)
    private String seller;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private boolean available;

    // Constructors, getters, and setters
}
~~~

Corresponding JSON mapping:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
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

If offers is a regular object, Elasticsearch cannot perform nested sorting with nested document semantics. The mapping must be nested from the start. To change object to nested, create a new index and reindex the data.

### 7.2. Sorting by Cheapest Offer

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "offers"
        }
      }
    }
  ]
}
~~~

Elasticsearch inspects the nested offers of each product, takes the lowest price, and uses that price to sort the parent document.

With the sample data, the price used for sorting is 80. However, the offer priced at 80 is unavailable. If the UI wants to sort by the lowest purchasable price, a nested filter must be added.

### 7.3. Filtering Nested Documents Before Sorting

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

Now only offers with available=true are used to compute the sort value. For the example, the lowest price used becomes 95 instead of 80.

### 7.4. Nested Sort Filter Differs from Query Filter

This is an easily confused point:

- A nested query filter determines which parent documents are returned.
- A nested sort filter determines which nested documents inside a parent are used to compute the sort value.

For example, a query may require products that have at least one offer from seller-a:

~~~json
{
  "query": {
    "nested": {
      "path": "offers",
      "query": {
        "term": {
          "offers.seller": "seller-a"
        }
      }
    }
  }
}
~~~

If the sort only specifies the nested path without a seller-a filter, Elasticsearch may compute the sort value across all offers of the product, including seller-b or seller-c. Conditions inside a nested query do not automatically restrict the set of nested documents used for nested sort.

If the goal is to sort by seller-a's offer price, repeat the seller-a condition inside the nested sort filter:

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
              "offers.seller": "seller-a"
            }
          }
        }
      }
    }
  ]
}
~~~

Separating the two conditions gives exact control over both which parent documents are selected and which nested values are used to order them.

### 7.5. When No Nested Document Matches the Filter

If a parent document has offers, but none match the nested sort filter, the sort has no value for that parent. In that case, the sort's missing attribute can determine the parent document's placement.

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "missing": "_last",
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

Documents with no available offers are treated as missing a sort value and placed last. If business logic requires treating that case as a fallback price, a numeric-compatible missing sentinel can be used.

## 8. Multi-Level Nested Sorting

Mappings can contain nested objects inside nested objects—for example, an order with items where each item has discounts:

~~~json
{
  "properties": {
    "items": {
      "type": "nested",
      "properties": {
        "sku": {
          "type": "keyword"
        },
        "discounts": {
          "type": "nested",
          "properties": {
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

When sorting by a field at a deep nested level, the nested sort must express the full nested path hierarchy:

~~~json
{
  "sort": [
    {
      "items.discounts.amount": {
        "order": "desc",
        "mode": "max",
        "nested": {
          "path": "items",
          "nested": {
            "path": "items.discounts"
          }
        }
      }
    }
  ]
}
~~~

With multi-level nesting, filters at each level can restrict matching child objects. Verify the actual mapping and paths; an incorrect nested path prevents Elasticsearch from resolving the nested context.

Multi-level nested sorting is more complex and can be resource-intensive. If you frequently need to sort by a deeply aggregated value, consider maintaining a denormalized field on the parent document for direct sorting.

## 9. Sorting with NativeQuery and the Elasticsearch Java API Client

Sort.by(...) is convenient for simple fields. When you need missing, mode, unmapped_type, or a nested sort filter, the typed sort DSL of the Elasticsearch Java API Client provides finer control.

### 9.1. Numeric Sort with missing and mode

Example sorting by the lowest price in a multi-valued field, placing documents missing a price last:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.SortMode;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;

SortOptions priceSort = SortOptions.of(s -> s
    .field(f -> f
        .field("priceHistory")
        .order(SortOrder.Asc)
        .mode(SortMode.Min)
        .missing(FieldValue.of("_last"))
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(productQuery)
    .withSortOptions(priceSort)
    .build();
~~~

The types and builder methods belong to the Elasticsearch Java API Client. Overload names or how sort options lists are passed may vary across versions; use the exact client version managed by Spring Boot.

### 9.2. Nested Sort with Filter

Example sorting products by the lowest price among available offers:

~~~java
import co.elastic.clients.elasticsearch._types.SortMode;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query availableOfferFilter = Query.of(q -> q
    .term(t -> t
        .field("offers.available")
        .value(true)
    )
);

SortOptions availableOfferPriceSort = SortOptions.of(s -> s
    .field(f -> f
        .field("offers.price")
        .order(SortOrder.Asc)
        .mode(SortMode.Min)
        .missing(FieldValue.of("_last"))
        .nested(n -> n
            .path("offers")
            .filter(availableOfferFilter)
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(productQuery)
    .withSortOptions(availableOfferPriceSort)
    .build();
~~~

In some Java API Client versions, the missing parameter is represented by FieldValue; for example, you may need FieldValue.of("_last") instead of a raw string. Similarly, the withSortOptions API may accept one or multiple sort options. Check the builder signatures in your active dependencies.

### 9.3. Combining Sort with Pageable

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(productQuery)
    .withSortOptions(availableOfferPriceSort)
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Pageable limits the parent results returned. Nested sort only determines the order of parent hits based on the filtered nested values.

If you have already configured detailed sort options on NativeQuery, avoid also setting a different sort inside Pageable or Spring Data Sort without explicitly determining how the sort clauses are combined. Keep sort ordering in one place to avoid accidentally adding or altering sorting criteria.

## 10. Basic Sorting with Spring Data Sort

For simple field sorts, you can use:

~~~java
Sort sort = Sort.by(
    Sort.Order.asc("price"),
    Sort.Order.desc("createdAt")
);

PageRequest pageRequest = PageRequest.of(0, 20, sort);

NativeQuery query = NativeQuery.builder()
    .withQuery(productQuery)
    .withPageable(pageRequest)
    .build();
~~~

Sort can also be used with repositories:

~~~java
List<ProductDocument> products =
    productRepository.findByCategory(
        "accessories",
        Sort.by(Sort.Order.asc("price"))
    );
~~~

Query methods that support sorting depend on the method signature and return type. For complex sorts involving nested fields, missing values, or multi-value modes, using NativeQuery with typed sort options is usually clearer.

## 11. Sorting and Pagination Must Use the Same Stable Order

When paginating, Elasticsearch needs to determine which documents belong to the first page and subsequent pages. If multiple documents share the same sort value, the order among them may be unstable without a secondary criterion.

For example, sorting only by category:

~~~json
{
  "sort": [
    {
      "category": {
        "order": "asc"
      }
    }
  ]
}
~~~

Many products can belong to the same category. For a more stable order, add a unique keyword field as a tie-breaker:

~~~json
{
  "sort": [
    {
      "category": {
        "order": "asc"
      }
    },
    {
      "sku": {
        "order": "asc"
      }
    }
  ]
}
~~~

The tie-breaker field should have doc values and unique or sufficiently stable values within the result set. Do not assume sorting directly by _id is a good choice; _id is not designed as a general sort field. You can store a copy of a business ID in a keyword field with doc values to serve as a tie-breaker.

### 11.1. Offset Pagination

For small page counts, you can use from/size via Pageable:

~~~java
PageRequest.of(0, 20);
PageRequest.of(1, 20);
~~~

Offset pagination is simple, but becomes expensive when traversing deep into large result sets. Elasticsearch also limits the total hits accessible via from/size according to an index setting.

### 11.2. search_after

For deep pagination, use a stable sort and the sort values of the last hit of a page as a cursor:

~~~json
{
  "size": 20,
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "sku": {
        "order": "asc"
      }
    }
  ],
  "search_after": [
    129.5,
    "KB-1042"
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Values in search_after must match the exact order and types of the sort clauses. You can obtain these values from SearchHit.getSortValues() of the last hit on the page.

Do not combine a large from with search_after; the two pagination methods serve different purposes. With continuously changing data, consider pairing with Point in Time (PIT) to preserve a stable view throughout pagination.

### 11.3. Nested Sort and search_after

When sorting by a nested field, the parent hit's sort value is the value computed using the nested path, filter, and mode. search_after uses the parent hit's sort values just like any other sort.

For accurate pagination:

- Keep the nested sort path, filter, and mode identical across pages.
- Keep the sort clause order identical.
- Add a stable tie-breaker at the parent document level.
- If using PIT, use the latest PIT ID from the response and close the PIT when finished.

Do not recompute nested sort values on the Java side to use as a cursor; use the sort values returned by Elasticsearch.

## 12. Combining missing, mode, and Nested Filter

The three concepts can be combined:

- missing: placement or fallback value when no sort value exists.
- mode: how a single value is picked from multiple values.
- nested.filter: which nested objects are included in the value set used to compute the sort.

For example:

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "missing": "_last",
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

Reading in order:

1. Enter the nested path offers.
2. Consider only offers where available is true.
3. Take the lowest price among the remaining offers.
4. Sort parent documents by price ascending.
5. If no qualifying offers remain, place the parent document last.

This is a useful pattern for product catalogs: ordering products by their lowest purchasable selling price and putting products with no available offers at the end.

## 13. Sorting by Multiple Nested Fields

A query can sort by multiple nested fields:

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
    },
    {
      "offers.seller": {
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
    },
    {
      "sku": {
        "order": "asc"
      }
    }
  ]
}
~~~

Each sort clause has its own nested context. If multiple criteria must operate on the same set of nested objects, make sure their filters are consistent. Elasticsearch evaluates each sort value according to that clause's configuration; sorting by price and sorting by seller are not implicitly tied to the same selected offer if clauses use different filters or modes.

If business logic requires sorting by a specific offer—such as an offer from a user-selected seller—filter by seller in each nested sort clause rather than sorting across all offers.

## 14. Nested Sort and inner_hits Are Two Different Things

Nested sort determines the order of parent documents based on nested values. Inner hits returns the nested documents matching the query in the response.

| Mechanism | Purpose |
| --- | --- |
| Nested query | Selects parent documents that have matching nested objects |
| Nested sort | Computes parent sort value from nested objects |
| Inner hits | Returns matching nested objects in the results |

A single query can use all three:

- Nested query filters products with available offers.
- Nested sort orders products by the lowest price of available offers.
- Inner hits returns matching available offers for the UI to display.

However, filters in nested query, nested sort, and inner hits are separate configurations. If the same condition is needed, declare it consistently in each part.

## 15. Nested Sort with a Multi-Condition Filter

For example, sorting only by offers that are:

- Currently available.
- From seller-a or seller-b.
- Priced at 50 or higher.

Nested filter:

~~~json
{
  "bool": {
    "filter": [
      {
        "terms": {
          "offers.seller": ["seller-a", "seller-b"]
        }
      },
      {
        "term": {
          "offers.available": true
        }
      },
      {
        "range": {
          "offers.price": {
            "gte": 50
          }
        }
      }
    ]
  }
}
~~~

Place the filter inside nested sort:

~~~json
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "missing": "_last",
        "nested": {
          "path": "offers",
          "filter": {
            "bool": {
              "filter": [
                {
                  "terms": {
                    "offers.seller": ["seller-a", "seller-b"]
                  }
                },
                {
                  "term": {
                    "offers.available": true
                  }
                },
                {
                  "range": {
                    "offers.price": {
                      "gte": 50
                    }
                  }
                }
              ]
            }
          }
        }
      }
    }
  ]
}
~~~

The nested sort filter only affects sort value calculation. If you only want to return parent documents that have at least one such offer, add the corresponding nested query to the main query section.

## 16. Sorting by Multi-Valued Dates

A document can contain multiple timestamps, such as estimated delivery dates:

~~~json
{
  "orderId": "ORD-1001",
  "deliveryWindows": [
    "2026-03-15T09:00:00Z",
    "2026-03-17T09:00:00Z"
  ]
}
~~~

Sort by earliest delivery date:

~~~json
{
  "sort": [
    {
      "deliveryWindows": {
        "order": "asc",
        "mode": "min"
      }
    }
  ]
}
~~~

Sort by latest delivery date:

~~~json
{
  "sort": [
    {
      "deliveryWindows": {
        "order": "desc",
        "mode": "max"
      }
    }
  ]
}
~~~

For multi-valued date fields, min/max modes are usually appropriate. If you want to sort by the next available delivery date starting from the current time, you may need filtering or separate modeling; do not assume min is always the right business value.

## 17. Geo Distance Sort and Missing Locations

A geo_point field can be sorted by distance to a coordinate:

~~~json
{
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km",
        "distance_type": "arc",
        "mode": "min"
      }
    }
  ]
}
~~~

If the location field is missing, the document has no distance to sort by. Elasticsearch has missing rules for geo sort depending on the API; check the client and version documentation before configuring. If the UI needs to keep documents without coordinates, group them separately or add a business field representing location status.

Do not use a numeric sentinel like 0 for distance if it causes documents lacking coordinates to rank as if they are located right at the search origin.

## 18. Limitations and Performance Considerations

Sorting is usually more expensive than simple filtering because Elasticsearch must determine hit order. Key points to consider:

- Sort fields should have doc values. Keyword and numeric fields are typically configured appropriately by default.
- Sorting on text using fielddata can consume significant heap; prefer a keyword multi-field.
- Multi-valued sorting must aggregate multiple values for each document.
- Nested sorting must inspect nested documents and may apply a filter per parent.
- Multi-level nested sorting increases query complexity and cost.
- Many sort clauses increase comparison work and sort value storage.
- Deep pagination via from/size consumes significant resources; consider search_after and PIT.
- Do not return excessive nested inner hits just to display a few sort values.

If a nested sort is used frequently and the filter never changes, consider precomputing a field on the parent document, such as lowestAvailableOfferPrice. When writing or updating offers, the application updates this aggregated field. Sorting directly on a parent field is simpler and faster, at the trade-off of having the application maintain consistency of the aggregated data.

## 19. Common Pitfalls

**Omitting missing configuration and assuming every document has a value.** Documents missing the field may appear last by default. Declare missing explicitly if that placement is a business requirement.

**Confusing null fields with null_value.** Null is only indexed with a replacement value when the mapping declares null_value; omitted fields remain missing.

**Using unmapped_type to handle documents missing a field.** unmapped_type is for indices lacking the field mapping; missing handles documents lacking a value.

**Sorting multi-valued fields without specifying mode.** Defaults depend on sort direction. Declare min/max/avg/sum/median explicitly when business semantics matter.

**Using avg or sum for keywords.** Numeric aggregation modes are unsuitable for strings. Keywords normally use min or max.

**Sorting on text fields.** Use a keyword subfield rather than arbitrarily enabling fielddata.

**Sorting a nested field while forgetting the nested path.** Elasticsearch needs the nested context. Mapping must be nested and sort must specify path.

**Assuming a nested query filter automatically applies to nested sort.** The two configurations are independent. Repeat the filter in nested sort if you only want to sort over matching nested objects.

**Sorting by lowest price without filtering available offers.** Results may be ordered based on out-of-stock offers. Add a nested filter for available or the appropriate business status.

**Omitting missing for a nested sort with no matching elements.** Parent documents with no nested values remaining after filtering need an explicit ordering rule.

**Using nested sort on a standard object field.** Nested sort is only for nested mappings. Verify the mapping before writing the query.

**Paginating across multiple pages without a tie-breaker.** Documents with identical sort values can swap positions. Add a stable, unique keyword field.

**Using _id as a tie-breaker without checking sortability.** Copy the ID into a keyword field with doc values if stable sorting is required.

**Combining multiple sort sources without knowing clause order.** Sorts in NativeQuery and Pageable may be combined depending on builder/version. Keep sort definitions in one place and verify the generated DSL request.

## 20. Workflow for Choosing How to Sort

When designing sorting for search results:

1. Identify the field to sort on and its actual mapping type.
2. Determine whether the field can be missing, null, a multi-valued array, or a nested object.
3. For missing values, choose _first, _last, or a type-compatible replacement value.
4. For multi-valued fields, choose mode min, max, sum, avg, or median according to business semantics.
5. For nested fields, declare path and filter to identify the exact nested objects considered.
6. If the main query also has a nested filter, repeat necessary conditions in nested sort.
7. Choose Spring Data Sort for simple cases or NativeQuery typed SortOptions for advanced configuration.
8. Combine sorting with pagination; add a stable tie-breaker.
9. For large datasets, consider search_after and PIT instead of deep offsets.
10. Test edge cases: missing fields, nulls, empty arrays, unmatched nested filters, and duplicate values.
11. Benchmark performance on representative data and consider a parent aggregated field if nested sorting is too costly.

Accurate sorting requires both the right mapping and explicit value-selection rules. Missing determines the position of documents without values; mode determines the representative value for multi-valued fields; nested path and filter determine which child objects participate in sorting. When these three parts are defined properly, sort order reflects business requirements accurately and pagination operates reliably.

## 21. References

- [Elasticsearch - Sort search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/sort-search-results): missing values, multi-valued sort, sort mode, and nested sort.
- [Elasticsearch - Nested field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/nested): nested mapping and nested document limits.
- [Elasticsearch - Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results): from/size, search_after, and Point in Time.
- [Elasticsearch - Doc values](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/doc-values): data structures supporting sorting and aggregations.
- [Spring Data Elasticsearch - Query and sort](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): executing queries and using Spring Data abstractions.
- [Elasticsearch Java API Client - Sorting](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/sort): building sort options with the Java client.

Spring Data Elasticsearch and Elasticsearch Java API Client builder methods may change across versions. When implementing nested sorts or missing/mode options, check the Javadoc of your actual dependencies and inspect the JSON request sent to the cluster.
