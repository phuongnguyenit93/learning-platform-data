# Terms Aggregation for Grouping and Statistical Filters

## 1. What is a Terms aggregation?

In Elasticsearch, aggregations are used to summarize search data. Instead of only fetching a list of documents, the application can ask Elasticsearch to group documents by an attribute and calculate metrics for each group.

A **Terms aggregation** is a bucket aggregation. Elasticsearch creates one bucket for each distinct value of the selected field, then counts the number of documents belonging to each bucket.

For example, the `products` index has these documents:

| ID | name | category | price |
|---|---|---|---:|
| p-01 | Wireless Headphones | audio | 1200000 |
| p-02 | Bluetooth Speaker | audio | 850000 |
| p-03 | Mechanical Keyboard | accessories | 1500000 |
| p-04 | USB Hub | accessories | 350000 |
| p-05 | Office Chair | furniture | 2400000 |
| p-06 | Standing Desk | furniture | 5200000 |

When grouped by `category`, Elasticsearch creates three buckets:

| Bucket key | doc_count |
|---|---:|
| audio | 2 |
| accessories | 2 |
| furniture | 2 |

Each bucket contains the documents with the corresponding category value. From these buckets, the application can build category filters, product distribution charts, or per-group statistics.

Terms aggregations are useful for:

- Counting products by category, brand, or status.
- Building facet lists for users to filter results.
- Summarizing orders by status, region, or sales channel.
- Grouping logs by level, service, or error code.
- Calculating metrics such as total revenue, average price, or maximum price within each group.

A terms aggregation only returns buckets selected according to its configuration. It does not automatically list every unique value if the field has very high cardinality.

## 2. Structure of a Terms aggregation in Query DSL

A basic terms aggregation has the structure:

~~~http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

In this example:

- `size: 0` at the search request level instructs Elasticsearch not to return document hits; the request only needs aggregation results.
- `aggs` declares the aggregations to execute.
- `categories` is the name chosen by the application for the aggregation.
- `terms` specifies the bucket aggregation type.
- `field` specifies the field used to create buckets.

The name `categories` is merely an identifier for the aggregation in the response. It does not have to match the field name or entity name.

Abbreviated response:

~~~json
{
  "hits": {
    "total": {
      "value": 6,
      "relation": "eq"
    },
    "hits": []
  },
  "aggregations": {
    "categories": {
      "doc_count_error_upper_bound": 0,
      "sum_other_doc_count": 0,
      "buckets": [
        {
          "key": "accessories",
          "doc_count": 2
        },
        {
          "key": "audio",
          "doc_count": 2
        },
        {
          "key": "furniture",
          "doc_count": 2
        }
      ]
    }
  }
}
~~~

Each bucket has two basic pieces of information:

- `key`: the field value forming the group.
- `doc_count`: the number of documents in the bucket.

The aggregation response resides in `aggregations`. It is independent of the document list in `hits.hits`. Therefore, a request can return 0 document hits while still returning statistical buckets.

## 3. Choosing the right field for bucketing

A terms aggregation requires a field that supports aggregations. Commonly suitable field types include:

- `keyword`.
- Numeric types such as `integer`, `long`, `float`, and `double`.
- `ip`.
- `boolean`.
- `binary` in supported cases.

You cannot run a terms aggregation on a `text` field by default. Text fields are broken into tokens by an analyzer, so grouping on such a field would group by analyzed terms rather than by the entire original value.

Example mapping:

~~~json
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
      "price": {
        "type": "double"
      },
      "active": {
        "type": "boolean"
      }
    }
  }
}
~~~

If you need to group by full name, use the `name.keyword` field:

~~~json
{
  "aggs": {
    "product_names": {
      "terms": {
        "field": "name.keyword"
      }
    }
  }
}
~~~

If you use the `text` field `name`, Elasticsearch will typically return an error stating that fielddata is disabled. You can enable fielddata, but doing so can consume significant heap memory because Elasticsearch must build data structures for aggregating over analyzed tokens. When you need to group by verbatim values, a keyword multi-field is usually the better choice.

Before writing an aggregation, check the mapping with:

~~~http
GET /products/_mapping
~~~

Do not pick a field merely because its name looks right. The data type and mapping determine bucket semantics.

## 4. Size: number of buckets returned

By default, a terms aggregation returns at most 10 buckets with the highest document counts.

Example:

~~~json
{
  "aggs": {
    "top_categories": {
      "terms": {
        "field": "category",
        "size": 5
      }
    }
  }
}
~~~

`size: 5` requests at most five buckets to be returned. By default, the order is descending by document count, meaning the bucket with the largest `doc_count` comes first.

Distinguish between the two `size` parameters:

| Location | Meaning |
|---|---|
| Search request `size` | Number of document hits returned |
| Terms aggregation `size` | Number of buckets returned |

Example:

~~~json
{
  "size": 20,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 8
      }
    }
  }
}
~~~

This request returns at most 20 document hits and at most 8 category buckets. The two limits operate independently.

If you only need statistics, set the search request `size` to 0 so unnecessary documents are not loaded:

~~~json
{
  "size": 0,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
~~~

Increasing aggregation size retrieves more buckets, but it also increases the amount of data and memory required. Elasticsearch enforces the `search.max_buckets` limit on the total number of buckets in a request. Do not set an arbitrarily huge size to try to retrieve all unique values.

## 5. Order: sorting buckets

A terms aggregation sorts buckets by `_count` descending by default:

~~~json
{
  "terms": {
    "field": "category",
    "size": 10,
    "order": {
      "_count": "desc"
    }
  }
}
~~~

You can sort by key:

~~~json
{
  "terms": {
    "field": "category",
    "size": 20,
    "order": {
      "_key": "asc"
    }
  }
}
~~~

Common options:

| Order | Meaning |
|---|---|
| `_count: desc` | Document count descending; default |
| `_count: asc` | Document count ascending |
| `_key: asc` | Bucket key ascending |
| `_key: desc` | Bucket key descending |

Sorting by key ascending or descending is a safe way to retrieve buckets ordered by value. For keyword fields, key order is lexicographical; for numeric fields, Elasticsearch sorts numerically.

Be cautious with `_count: asc`. When data is distributed across multiple shards, each shard only sends a set of candidate terms to the coordinating node. Rare terms might not be selected as candidates on all shards, leading to an incomplete result list. If you need to find rare terms, consider the `rare_terms` aggregation instead of sorting terms by count ascending.

Sorting by a sub-aggregation can also produce inaccurate results if an unsuitable metric is chosen. Elasticsearch only guarantees certain special cases, such as sorting by max descending or min ascending. Prefer the default count-descending order or key order when there is no specific requirement otherwise.

## 6. min_doc_count: only returning groups with enough documents

`min_doc_count` specifies the minimum number of documents a bucket must have to be returned. The default is 1.

For example, only returning categories with at least 5 products:

~~~json
{
  "aggs": {
    "popular_categories": {
      "terms": {
        "field": "category",
        "size": 20,
        "min_doc_count": 5
      }
    }
  }
}
~~~

If a category has only 2 products, that bucket will not appear in the response.

You can combine this with `shard_min_doc_count` to filter out candidate terms with counts that are too low directly on each shard:

~~~json
{
  "terms": {
    "field": "category",
    "size": 20,
    "min_doc_count": 10,
    "shard_min_doc_count": 2
  }
}
~~~

`min_doc_count` is evaluated after combining results across shards. `shard_min_doc_count` is applied on each shard before sending candidates to the coordinating node. Setting `shard_min_doc_count` too high can drop terms that would have met the threshold once summed across shards.

If you set `min_doc_count: 0`, Elasticsearch may return buckets with a count of 0 from terms still present in the dictionary, including some terms associated only with deleted documents. Do not treat every 0-count bucket as an active value guaranteed to have matching documents.

## 7. Include and exclude: restricting bucket values

`include` and `exclude` filter which term values are allowed to appear as buckets. They do not replace a query filter and do not remove documents from the hits results.

For example, aggregating only selected categories:

~~~json
{
  "aggs": {
    "selected_categories": {
      "terms": {
        "field": "category",
        "include": [
          "audio",
          "accessories"
        ]
      }
    }
  }
}
~~~

For example, excluding certain values:

~~~json
{
  "aggs": {
    "categories_without_test": {
      "terms": {
        "field": "category",
        "exclude": [
          "test",
          "internal"
        ]
      }
    }
  }
}
~~~

You can use regular expression patterns for include or exclude when filtering by naming rules. Check Elasticsearch's regex syntax and semantics before using them.

Distinguish clearly:

- Query filters restrict which documents enter the search and aggregation pipeline.
- Include/exclude restrict which term values are allowed to form buckets.
- If a document is omitted from buckets because its field value is not in include, that document can still appear in `hits.hits` if the main query matches it.

## 8. Missing: handling documents without the field

By default, documents without a value for the aggregated field are not placed in any bucket.

For example, some products have no category. If you want to group those documents into a bucket with a dedicated label, use `missing`:

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

Documents missing a category are then counted in the bucket with key `uncategorized`.

`missing` is a placeholder value within the aggregation. It does not write that value back into the document and does not alter the source.

If the field is numeric or another type, choose a missing value compatible with the field's data type and Elasticsearch version.

## 9. Combining Terms aggregation with metric sub-aggregations

Terms aggregations create buckets; metric aggregations compute numbers within each bucket.

For example, grouping products by category and calculating average price, total price, and maximum price:

~~~http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        },
        "total_price": {
          "sum": {
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
  }
}
~~~

Each category bucket will have:

- `doc_count`: number of products in the category.
- `average_price.value`: average price.
- `total_price.value`: sum of the price field.
- `maximum_price.value`: highest price.

Abbreviated response:

~~~json
{
  "aggregations": {
    "categories": {
      "buckets": [
        {
          "key": "audio",
          "doc_count": 2,
          "average_price": {
            "value": 1025000.0
          },
          "total_price": {
            "value": 2050000.0
          },
          "maximum_price": {
            "value": 1200000.0
          }
        },
        {
          "key": "accessories",
          "doc_count": 2,
          "average_price": {
            "value": 925000.0
          },
          "total_price": {
            "value": 1850000.0
          },
          "maximum_price": {
            "value": 1500000.0
          }
        }
      ]
    }
  }
}
~~~

Common metrics that can be placed inside a bucket:

| Metric aggregation | Meaning |
|---|---|
| `avg` | Average |
| `sum` | Sum |
| `min` | Minimum value |
| `max` | Maximum value |
| `value_count` | Count of field values |
| `stats` | Combines count, min, max, avg, and sum |
| `extended_stats` | Extended statistics such as standard deviation |
| `cardinality` | Approximate count of unique values |

`doc_count` counts documents in the bucket, whereas `value_count` counts the number of values for a field. With multi-valued fields, the two numbers can differ. `cardinality` is usually an approximation and should not be used as an exact count when the business requires exact numbers.

## 10. Combining Terms aggregation with filter aggregation

You can place a filter aggregation inside each bucket to compute metrics over a subset of documents.

For example, within each category, counting active products:

~~~json
{
  "size": 0,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "active_products": {
          "filter": {
            "term": {
              "active": true
            }
          }
        }
      }
    }
  }
}
~~~

Each category bucket gets an additional `active_products` bucket. The child bucket's `doc_count` is the number of active products in that category.

You can add metrics inside the filter bucket:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "active_products": {
          "filter": {
            "term": {
              "active": true
            }
          },
          "aggs": {
            "average_active_price": {
              "avg": {
                "field": "price"
              }
            }
          }
        }
      }
    }
  }
}
~~~

This structure returns the count of active products and the average price of active products within each category.

## 11. Filters aggregation: creating groups by business conditions

Terms aggregations create groups by field value. If you want to create groups based on custom business conditions, you can use a `filters` aggregation.

For example, dividing products into three price tiers:

~~~json
{
  "size": 0,
  "aggs": {
    "price_groups": {
      "filters": {
        "filters": {
          "budget": {
            "range": {
              "price": {
                "lt": 500000
              }
            }
          },
          "mid_range": {
            "range": {
              "price": {
                "gte": 500000,
                "lt": 2000000
              }
            }
          },
          "premium": {
            "range": {
              "price": {
                "gte": 2000000
              }
            }
          }
        }
      }
    }
  }
}
~~~

The response returns buckets named `budget`, `mid_range`, and `premium`. Each bucket has its corresponding `doc_count`.

Comparison:

| Aggregation | How groups are formed | Example |
|---|---|---|
| `terms` | One bucket per distinct field value | Grouping by category |
| `filter` | One bucket for one condition | Counting only active products |
| `filters` | Multiple buckets, each with its own condition | Grouping by price range or status |

Filter buckets can overlap. A single document can belong to multiple buckets if it satisfies multiple conditions. This differs from how users often imagine mutually exclusive groups, so design conditions carefully.

## 12. How do query filters and post_filter differ from bucket filters?

On a search page with facets, distinguish three filtering locations:

1. `query` filters documents before computing hits and aggregations.
2. `post_filter` filters hits after aggregations have already been computed.
3. `include`/`exclude` inside a terms aggregation filters which term values are allowed to create buckets.

For example, a user selects the `audio` category, yet the UI still wants to show counts for all other categories so the user can switch selections. You can use query for general filters and post_filter for the selected category:

~~~json
{
  "query": {
    "term": {
      "active": true
    }
  },
  "post_filter": {
    "term": {
      "category": "audio"
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
~~~

In this example:

- Query selects only active documents as the scope for both hits and aggregations.
- Post filter limits only the hits list to category audio.
- The `categories` aggregation still summarizes categories across active documents prior to the post filter.

If you put category audio in `query` instead of `post_filter`, the `categories` aggregation would also only see audio documents. When building faceted search, where you place a filter determines which dataset the facet numbers reflect.

## 13. Terms aggregation across multiple fields

A standard terms aggregation groups by a single field. If you need to group by a combination of multiple fields, you can use the `multi_terms` aggregation.

For example, grouping by category and brand:

~~~json
{
  "size": 0,
  "aggs": {
    "category_brand": {
      "multi_terms": {
        "terms": [
          {
            "field": "category"
          },
          {
            "field": "brand"
          }
        ],
        "size": 50
      }
    }
  }
}
~~~

Each bucket represents a pair of values, such as `audio + Acme` or `audio + Contoso`.

`multi_terms` is convenient for top groups by field combinations, though it is typically more resource-intensive than a single-field terms aggregation because Elasticsearch must construct composite keys. If you need to iterate through all bucket combinations across multiple pages, consider a composite aggregation.

Do not concatenate two fields into a single string via a script just to group by pairs if multi_terms or composite already satisfies the requirement. Scripts can increase computational overhead.

## 14. Distinguishing Terms aggregation and Composite aggregation

Terms aggregation is optimized for retrieving a limited number of prominent buckets, typically the terms with the most documents. It is not a pagination tool for iterating over very high cardinality.

If a field has hundreds of thousands or millions of unique values and the application needs to read all buckets, use a `composite` aggregation:

| Criterion | Terms aggregation | Composite aggregation |
|---|---|---|
| Goal | Top buckets by count or order | Paginate through buckets page by page |
| Quantity | Limited by size and max_buckets | Fetched in batches with after_key |
| Bucket pagination | No full cursor pagination like composite | Has after_key |
| Suitable use cases | Facets, top categories, top brands | Exporting or scanning all high-cardinality groups |

Example composite aggregation:

~~~json
{
  "size": 0,
  "aggs": {
    "all_categories": {
      "composite": {
        "size": 100,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

The response can return `after_key`. The next request passes `after` equal to that value to fetch the next batch of buckets.

If you only need the 10 most popular categories, a terms aggregation is simpler. If you need to export all category values, a composite aggregation is more suitable.

## 15. Distributed limits: size, shard_size, and accuracy

Elasticsearch typically executes aggregations across multiple shards. Each shard produces a local list of candidate buckets and sends the results to the coordinating node to merge.

By default, a terms aggregation asks each shard to send more candidates than the final bucket count. The default `shard_size` is estimated approximately as `size * 1.5 + 10`.

Example:

~~~json
{
  "terms": {
    "field": "category",
    "size": 10,
    "shard_size": 30
  }
}
~~~

- `size` is the final number of buckets returned.
- `shard_size` is the number of candidate terms each shard sends for the coordinating node to merge.

Increasing `shard_size` generally improves the accuracy of top buckets and doc counts when data is unevenly distributed across shards. However, it increases network transfer and memory usage on the coordinating node. `shard_size` cannot be smaller than `size`; Elasticsearch will raise it to equal size if needed.

Even when increasing shard_size, `doc_count` can still be approximate in some situations. Inspect the aggregation metadata instead of assuming every count is exact.

### sum_other_doc_count

`sum_other_doc_count` is the total number of documents not included in the returned buckets, either due to the top-bucket `size` limit or candidate selection on shards.

If this value is greater than 0, the aggregation excluded a portion of documents from the buckets in the response. That does not mean those documents were deleted from the index; they simply do not belong to the returned buckets.

### doc_count_error_upper_bound

You can enable `show_term_doc_count_error`:

~~~json
{
  "terms": {
    "field": "category",
    "size": 10,
    "show_term_doc_count_error": true
  }
}
~~~

Elasticsearch additionally returns `doc_count_error_upper_bound`, which is the upper bound of per-bucket doc_count error when computable.

This error information is meaningful when terms are sorted by `_count` descending. For certain other ordering modes, Elasticsearch may return `-1` to indicate that an error bound cannot be determined in that manner.

If the business requires strictly exact statistics, re-evaluate data distribution, ordering requirements, and aggregation mechanisms. Do not assume a top-N terms aggregation always returns strictly exact counts on a multi-shard cluster.

## 16. Performance limits and cardinality

Cardinality is the number of distinct values in a field. Fields with few values like order status typically have low cardinality; fields like email, transaction code, or user ID can have very high cardinality.

Some guidelines:

- Use terms aggregations for fields whose cardinality matches the number of buckets to return.
- Only increase size when the application genuinely needs more buckets.
- Monitor the `search.max_buckets` limit.
- Increase shard_size deliberately, based on error bounds and data distribution.
- Use keyword/doc_values for categorical fields.
- Avoid enabling fielddata on text just for aggregations without evaluating memory.
- Use composite aggregations when you need to iterate over all buckets.
- Do not run multiple high-cardinality aggregations in the same request unnecessarily.

Global ordinals are an optimization mechanism commonly used by Elasticsearch for terms aggregations on keyword fields. For write and search workloads with specific requirements, you can consider `eager_global_ordinals` to shift part of ordinal construction to refresh time. This setting requires balancing refresh cost against query latency and should not be enabled by default for every field.

## 17. Executing Terms aggregations with Spring Data Elasticsearch

Spring Data Elasticsearch uses `NativeQuery` when complex queries or aggregations are needed. `NativeQuery` lets you build aggregations using Elasticsearch Java API Client types.

Suppose the entity is:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String brand;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // Constructors, getters and setters
}
~~~

Create a terms aggregation by category:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withAggregation(
        "categories",
        Aggregation.of(a -> a
            .terms(t -> t
                .field("category")
                .size(20)
            )
        )
    )
    .build();

SearchHits<Product> searchHits = operations.search(
    query,
    Product.class
);
~~~

The aggregation name is `categories`. The grouped field is `category`. Size 20 limits the number of buckets returned.

You can combine a query filter to aggregate only active products:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q
        .term(t -> t
            .field("active")
            .value(true)
        )
    )
    .withAggregation(
        "categories",
        Aggregation.of(a -> a
            .terms(t -> t
                .field("category")
                .size(20)
            )
        )
    )
    .build();
~~~

When a query filter is present, the aggregation only computes over documents matching the query. If you only need aggregations without document hits, you can use a request size of 0 via the appropriate query option in your version or call the Search API directly with `size: 0`.

Relevant imports in Spring Data Elasticsearch using the Elasticsearch Java API Client:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
~~~

`Aggregation` here is the builder class from the Elasticsearch Java API Client. Do not confuse it with legacy aggregation classes from older Elasticsearch clients.

## 18. Reading aggregation results from SearchHits

When using Spring Data Elasticsearch, aggregations are returned in `SearchHits.getAggregations()`. The return type is `AggregationsContainer<?>`; with the current Elasticsearch Java API Client, the implementation is typically `ElasticsearchAggregations`.

Example reading buckets of a string terms aggregation:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;

import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;

SearchHits<Product> searchHits = operations.search(
    query,
    Product.class
);

if (searchHits.getAggregations() instanceof ElasticsearchAggregations aggregations) {

    ElasticsearchAggregation categories = aggregations.get("categories");

    if (categories != null) {
        Aggregate aggregate = categories.aggregation().getAggregate();

        if (aggregate.isSterms()) {
            for (StringTermsBucket bucket : aggregate.sterms().buckets().array()) {
                String category = bucket.key().stringValue();
                long documentCount = bucket.docCount();

                System.out.println(category + ": " + documentCount);
            }
        }
    }
}
~~~

Data reading flow:

1. Call `SearchHits.getAggregations()` to obtain the container.
2. Cast to `ElasticsearchAggregations` when using the corresponding client implementation.
3. Call `get("categories")` to retrieve the aggregation by the name declared in the query.
4. Call `aggregation().getAggregate()` to get the Elasticsearch Java API Client aggregate.
5. Check the bucket type with `isSterms()`.
6. Retrieve the bucket list with `sterms().buckets().array()`.
7. Read the key and doc_count of each bucket.

A terms aggregation can return string, long, double, or other bucket types depending on the field. Therefore, not every aggregation is `sterms`. For integer fields, the response may be `lterms`; for floating-point numbers, it may be `dterms`. Check the variant before reading buckets and select the corresponding bucket type.

In Spring Data 6.x, the `ElasticsearchAggregations` structure is based on the Java API Client. Older Spring Data versions use different clients and aggregation types, so result-reading code may not be directly compatible as-is.

## 19. Reading metric sub-aggregations inside each bucket

When a terms aggregation has child metrics, each bucket carries a map of sub-aggregations. For example, a request with `average_price`:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
~~~

In the Java API Client, a bucket can hold sub-aggregations accessible via `bucket.aggregations()`. Example reading average price:

~~~java
for (StringTermsBucket bucket : aggregate.sterms().buckets().array()) {

    String category = bucket.key().stringValue();
    long count = bucket.docCount();

    Aggregate averagePrice = bucket.aggregations().get("average_price");

    if (averagePrice != null && averagePrice.isAvg()) {
        double average = averagePrice.avg().value();

        System.out.println(
            category + " | count=" + count + " | average=" + average
        );
    }
}
~~~

The sub-aggregation name must match the name declared in the request. Check the variant before calling accessors like `avg()` or `sum()` because the return type depends on the metric type.

## 20. Filters and terms in the same request

You can build an analytics dashboard consisting of multiple groups and metrics in a single request, allowing Elasticsearch to aggregate over the same document set.

For example, aggregating by category while only considering active products and breaking down price ranges within each category:

~~~json
{
  "size": 0,
  "query": {
    "term": {
      "active": true
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "price_ranges": {
          "range": {
            "field": "price",
            "ranges": [
              {
                "key": "under_500k",
                "to": 500000
              },
              {
                "key": "500k_to_2m",
                "from": 500000,
                "to": 2000000
              },
              {
                "key": "over_2m",
                "from": 2000000
              }
            ]
          }
        },
        "average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
~~~

The result has the structure:

~~~text
categories
  ├── audio
  │    ├── doc_count
  │    ├── price_ranges
  │    │    ├── under_500k
  │    │    ├── 500k_to_2m
  │    │    └── over_2m
  │    └── average_price
  ├── accessories
  │    └── ...
  └── furniture
       └── ...
~~~

This is an example of nested bucket aggregations. From a single request, the application can build a dashboard with counts per category, price distributions, and average prices.

When nesting multiple aggregations, check the total number of buckets generated and the `search.max_buckets` limit. A terms aggregation with 100 buckets, each having 20 child range buckets, can generate far more buckets than expected.

## 21. Common mistakes when using Terms aggregation

**Aggregating on a text field.** Elasticsearch disallows terms aggregations on text fields by default. Use a keyword sub-field or an appropriate mapping.

**Confusing search size with aggregation size.** Search size controls hits, while aggregation size controls buckets. The two values are not interchangeable.

**Thinking terms returns all unique values.** By default, it only returns the top 10 buckets. Increase size within limits or use composite when you need to iterate through all of them.

**Assuming doc_count is always strictly exact.** A distributed terms aggregation across multiple shards can return approximate counts. Check shard_size and error metadata.

**Using ascending count to find rare terms.** Ordering by `_count: asc` can miss terms due to per-shard candidate selection. Use `rare_terms` for finding rare values.

**Setting shard_size too high.** Increasing shard_size can improve accuracy, but it also increases memory and data transferred between shards and the coordinating node.

**Confusing include/exclude with query filters.** Include/exclude filter bucket term values. Query filters restrict which documents enter search and aggregations.

**Ignoring documents missing the field.** By default, documents without a value will not appear in any bucket. Use `missing` if they need a dedicated group.

**Treating doc_count as the number of field values.** For multi-valued fields, a document can appear in multiple buckets. `doc_count` counts documents in the bucket, not occurrences of all values.

**Overusing fielddata.** Enabling fielddata on text can significantly increase heap usage. Prefer keyword fields when grouping by full values.

**Fetching too many buckets.** High cardinality and large sizes can hit `search.max_buckets` or cause memory pressure. Choose top-N or composite as needed.

**Reading the wrong aggregation type in Java.** String terms, long terms, and double terms have different variants. Check the aggregate type before calling accessors.

**Misusing post_filter.** Post filter only filters hits after aggregations. If you want aggregations to reflect the filter condition as well, place the condition in query or an appropriate filter aggregation.

## 22. Workflow for designing Terms aggregations

You can implement following these steps:

1. Identify the statistical question: group by category, brand, status, or another attribute.
2. Check the field mapping and choose an aggregatable keyword/numeric field.
3. Decide whether you need document hits or only statistics; set search size accordingly.
4. Declare the aggregation name and field in `terms`.
5. Choose the bucket `size` based on the UI.
6. Keep the default descending count order if you want the most popular groups.
7. Use `min_doc_count`, `include`, `exclude`, or `missing` when business rules require it.
8. Add metric sub-aggregations to compute numbers inside each bucket.
9. Add `filter` or `filters` aggregations if you need conditional groups.
10. Inspect `sum_other_doc_count`, `doc_count_error_upper_bound`, and shard distribution.
11. Read aggregations from `SearchHits` and check the right variant.
12. Use composite aggregation if you need to paginate over high-cardinality buckets.
13. Evaluate bucket count, execution time, and memory on realistic data.

## Conclusion

A terms aggregation creates a bucket for each distinct value of a field and counts documents in each bucket. It forms the foundation for building facets, category filters, and analytics dashboards. You can combine terms with metric sub-aggregations to compute sum, average, min, and max, or with filter aggregations to analyze conditional subsets.

Choose an aggregatable field, typically `keyword` or numeric. By default, terms only returns the top 10 buckets ordered by `doc_count` descending; `size`, `shard_size`, `min_doc_count`, `include`, `exclude`, and `missing` fine-tune the output. On multi-shard clusters, bucket counts can be approximate, so pay attention to `sum_other_doc_count` and `doc_count_error_upper_bound`.

In Spring Data Elasticsearch, `NativeQuery` lets you declare terms aggregations using the Elasticsearch Java API Client. Results are read from `SearchHits.getAggregations()` via `ElasticsearchAggregations` and the corresponding bucket types. If you need to iterate over all unique values with high cardinality, use a composite aggregation rather than raising terms size indefinitely.

## References

- [Elasticsearch — Terms aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-terms-aggregation)
- [Elasticsearch — Bucket aggregations](https://www.elastic.co/docs/reference/aggregations)
- [Elasticsearch — Filters aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-filters-aggregation)
- [Elasticsearch — Composite aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-composite-aggregation)
- [Elasticsearch — Rare terms aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-rare-terms-aggregation)
- [Spring Data Elasticsearch — Elasticsearch Operations and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch — ElasticsearchAggregations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchAggregations.html)
