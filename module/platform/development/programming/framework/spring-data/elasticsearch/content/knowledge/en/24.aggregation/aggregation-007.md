# Nested, reverse_nested, and Aggregating Nested Relationships

When an Elasticsearch document contains an array of objects, an application sometimes needs to preserve the relationship between attributes inside each individual element. For example, an order has multiple order lines; each line has an SKU, quantity, unit price, and status. You may want to count lines by SKU, count how many orders contain each SKU, or compute the average revenue of orders containing that SKU.

The **nested** mapping type lets Elasticsearch treat each child object as a unit that can be queried and aggregated independently. In aggregations, **nested** traverses from the parent document into the set of nested documents; **reverse_nested** traverses back from nested documents to the parent document or an ancestor nested level. These two aggregations allow computing statistics at two different scopes within the same result tree.

This lesson explains when to choose nested mapping, how to interpret **doc_count** scopes accurately, how to combine nested and reverse_nested, how to handle multiple levels of nesting, and how to access aggregations in Spring Data Elasticsearch.

## 1. Why is nested mapping needed?

Suppose an order has multiple order lines:

~~~json
{
  "orderId": "ORD-100",
  "customerId": "CUS-20",
  "status": "PAID",
  "total": 250.00,
  "lines": [
    {
      "sku": "KB-100",
      "category": "keyboard",
      "quantity": 1,
      "unitPrice": 100.00
    },
    {
      "sku": "MS-200",
      "category": "mouse",
      "quantity": 2,
      "unitPrice": 75.00
    }
  ]
}
~~~

Each element in **lines** is an object with an internal relationship between **sku**, **category**, **quantity**, and **unitPrice**.

If Elasticsearch maps **lines** as a regular **object** type, objects in the array are flattened into arrays of field values. A combined query for **lines.sku = KB-100** and **lines.category = mouse** could match because both values exist somewhere in the same document, even though they belong to different array elements.

This becomes a problem when business logic requires conditions to match the same order line.

With **nested**, Elasticsearch indexes each object element as a separate nested document while preserving its link to the parent document. Queries and aggregations can then operate accurately on each individual child object.

### Differences between object and nested

| Mapping | How object arrays are stored | Relationship between fields in the same element |
|---|---|---|
| **object** | Values are flattened into the parent document | Object boundaries are not preserved for combined queries |
| **nested** | Each element is indexed as a separate nested document | Can query and aggregate per individual object |

Nested is not a default type to apply to every object array. It creates extra Lucene documents and adds indexing, storage, and query overhead. Use it only when preserving field relationships within each object is necessary.

## 2. Declaring nested in Spring Data Elasticsearch

Order entity:

~~~java
@Document(indexName = "orders")
public class PurchaseOrder {

    @Id
    private String orderId;

    @Field(type = FieldType.Keyword)
    private String customerId;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private Double total;

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;
}
~~~

Child object:

~~~java
public class OrderLine {

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Integer)
    private Integer quantity;

    @Field(type = FieldType.Double)
    private Double unitPrice;
}
~~~

The **@Field(type = FieldType.Nested)** annotation instructs Spring Data to generate a nested mapping for the **lines** property when the application creates the mapping from entity metadata.

Equivalent Elasticsearch mapping:

~~~json
{
  "mappings": {
    "properties": {
      "orderId": {
        "type": "keyword"
      },
      "customerId": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "total": {
        "type": "double"
      },
      "lines": {
        "type": "nested",
        "properties": {
          "sku": {
            "type": "keyword"
          },
          "category": {
            "type": "keyword"
          },
          "quantity": {
            "type": "integer"
          },
          "unitPrice": {
            "type": "double"
          }
        }
      }
    }
  }
}
~~~

Field names in Query DSL must match actual field names in the mapping. If the application uses **FieldNamingStrategy**, **@Field(name = "...")**, or custom field names, use the mapped names.

### Changing object to nested requires reindexing

You cannot directly change a field already created with an **object** mapping to **nested** on the same existing index. Existing field mappings cannot change types this way. You must create a new index with the right mapping, reindex the data, and switch aliases or read/write flows according to a migration plan.

## 3. Nested aggregation enters child documents

Standard aggregations run over the document set returned by the query. However, when aggregating fields inside **lines**, you must shift the aggregation scope from order documents to nested documents.

The **nested** aggregation does that:

~~~json
{
  "size": 0,
  "aggs": {
    "all_lines": {
      "nested": {
        "path": "lines"
      },
      "aggs": {
        "by_sku": {
          "terms": {
            "field": "lines.sku"
          }
        }
      }
    }
  }
}
~~~

How to read this:

1. Search selects the set of orders at the parent document level.
2. **nested** with path **lines** enters the order lines of those orders.
3. **terms** groups the nested documents by **lines.sku**.
4. Each SKU bucket holds the nested documents belonging to that SKU.

If an order has two lines with the same SKU, two nested documents are counted in that bucket. **doc_count** at the nested bucket is the number of nested documents, not the number of unique orders.

### Example result

Suppose there are three orders:

- ORD-100 has one KB-100 line and two MS-200 lines.
- ORD-101 has one KB-100 line.
- ORD-102 has one MS-200 line.

The **terms** result inside the nested aggregation might look like:

~~~json
{
  "aggregations": {
    "all_lines": {
      "doc_count": 4,
      "by_sku": {
        "buckets": [
          {
            "key": "KB-100",
            "doc_count": 2
          },
          {
            "key": "MS-200",
            "doc_count": 2
          }
        ]
      }
    }
  }
}
~~~

In this example, **all_lines.doc_count** is the total nested documents belonging to the selected orders. **by_sku.doc_count** counts order lines, not the number of orders containing the SKU.

This is the single most important distinction when reading nested statistics.

## 4. reverse_nested traverses from nested documents back to parent documents

After grouping nested documents by SKU, you may want to know how many orders contain each SKU. That is where **reverse_nested** comes in.

~~~json
{
  "size": 0,
  "aggs": {
    "all_lines": {
      "nested": {
        "path": "lines"
      },
      "aggs": {
        "by_sku": {
          "terms": {
            "field": "lines.sku"
          },
          "aggs": {
            "orders": {
              "reverse_nested": {}
            }
          }
        }
      }
    }
  }
}
~~~

**reverse_nested** returns to the root parent document. Within each SKU bucket:

- **by_sku.doc_count** counts nested line documents.
- **orders.doc_count** counts unique parent orders having at least one line in that SKU bucket.

Example response:

~~~json
{
  "aggregations": {
    "all_lines": {
      "doc_count": 4,
      "by_sku": {
        "buckets": [
          {
            "key": "KB-100",
            "doc_count": 2,
            "orders": {
              "doc_count": 2
            }
          },
          {
            "key": "MS-200",
            "doc_count": 2,
            "orders": {
              "doc_count": 2
            }
          }
        ]
      }
    }
  }
}
~~~

If ORD-100 has two MS-200 lines, **by_sku** still counts two nested documents, yet **orders.doc_count** counts ORD-100 only once for that bucket. This distinguishes "number of order lines" from "number of orders containing the product".

### reverse_nested is not a simple reverse counter

**reverse_nested** does not return parent objects in JSON as a list. It switches the aggregation scope to the parent document set so subsequent child aggregations can compute statistics on parent fields.

When **path** is omitted, reverse_nested returns to the root document. When path is provided, it returns to a specific nested parent located above the current nested context.

## 5. Aggregating parent document fields after reverse_nested

Once back at the order document level, you can aggregate on root fields such as **status**, **customerId**, or **total**.

Example: for each SKU, count orders by status and compute the average total value of orders containing that SKU:

~~~json
{
  "size": 0,
  "aggs": {
    "all_lines": {
      "nested": {
        "path": "lines"
      },
      "aggs": {
        "by_sku": {
          "terms": {
            "field": "lines.sku"
          },
          "aggs": {
            "parent_orders": {
              "reverse_nested": {},
              "aggs": {
                "by_status": {
                  "terms": {
                    "field": "status"
                  }
                },
                "average_order_total": {
                  "avg": {
                    "field": "total"
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
~~~

Scope changes across layers:

~~~text
Order documents (root)
        |
        | nested(path = lines)
        v
Nested line documents
        |
        | terms(lines.sku)
        v
One SKU bucket
        |
        | reverse_nested()
        v
Parent orders having at least one line belonging to the SKU
        |
        +-- terms(status)
        |
        +-- avg(total)
~~~

**average_order_total** is the average total amount of parent orders in the SKU bucket, not the average **unitPrice** of the order lines. Even if an order has multiple lines with the same SKU, that order is counted only once in the parent document scope after reverse_nested.

### Each nested bucket can compute statistics at both levels

You can place metrics both before and after reverse_nested:

~~~json
{
  "aggs": {
    "lines": {
      "nested": {
        "path": "lines"
      },
      "aggs": {
        "by_sku": {
          "terms": {
            "field": "lines.sku"
          },
          "aggs": {
            "line_quantity": {
              "sum": {
                "field": "lines.quantity"
              }
            },
            "average_unit_price": {
              "avg": {
                "field": "lines.unitPrice"
              }
            },
            "orders": {
              "reverse_nested": {},
              "aggs": {
                "average_order_total": {
                  "avg": {
                    "field": "total"
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
~~~

Within an SKU bucket:

- **line_quantity** sums the quantities of order lines.
- **average_unit_price** computes the average unit price across nested documents.
- **orders.doc_count** counts unique parent orders.
- **average_order_total** averages the `total` field of those parent orders.

Metric names should clearly reflect their scope so readers do not confuse line-level numbers with order-level numbers.

## 6. Filtering nested documents before aggregating

A common point of confusion is that root-level queries and nested-level aggregations operate on different scopes.

Suppose a top-level query uses a nested query to select orders having at least one line with SKU **KB-100**:

~~~json
{
  "query": {
    "nested": {
      "path": "lines",
      "query": {
        "term": {
          "lines.sku": "KB-100"
        }
      }
    }
  }
}
~~~

This query selects orders that contain at least one **KB-100** line. However, if a **nested(path: lines)** aggregation then runs on those selected orders, the aggregation sees all lines of those orders, including lines with other SKUs.

If the goal is to aggregate only **KB-100** lines, you must repeat the condition in a **filter** aggregation inside the nested aggregation:

~~~json
{
  "query": {
    "nested": {
      "path": "lines",
      "query": {
        "term": {
          "lines.sku": "KB-100"
        }
      }
    }
  },
  "aggs": {
    "lines": {
      "nested": {
        "path": "lines"
      },
      "aggs": {
        "matching_sku": {
          "filter": {
            "term": {
              "lines.sku": "KB-100"
            }
          },
          "aggs": {
            "by_category": {
              "terms": {
                "field": "lines.category"
              }
            }
          }
        }
      }
    }
  }
}
~~~

The two conditions play different roles:

- The top-level nested query determines which order documents enter the result.
- The filter aggregation inside the nested scope determines which line documents are aggregated.

If you want aggregations over all lines belonging to the selected orders, no repeated filter is needed. If you want statistics only over nested objects satisfying a specific condition, add the filter inside the nested aggregation.

### Filtering by multiple attributes of the same nested object

To ensure SKU and category belong to the same line, use a single nested query containing both conditions:

~~~json
{
  "query": {
    "nested": {
      "path": "lines",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "lines.sku": "KB-100"
              }
            },
            {
              "term": {
                "lines.category": "keyboard"
              }
            }
          ]
        }
      }
    }
  }
}
~~~

If the two conditions are placed in two independent nested queries, they can match two different lines in the same order. When business rules require the same child object to satisfy both, put them inside the same nested query.

## 7. reverse_nested with a specific path

In a nested hierarchy, a nested document can itself have a nested parent. **reverse_nested** can return to the root or to a nested ancestor.

For example, a mapping has nested **comments**, and inside each comment there are nested **votes**:

~~~json
{
  "mappings": {
    "properties": {
      "postId": {
        "type": "keyword"
      },
      "comments": {
        "type": "nested",
        "properties": {
          "author": {
            "type": "keyword"
          },
          "votes": {
            "type": "nested",
            "properties": {
              "userId": {
                "type": "keyword"
              },
              "value": {
                "type": "integer"
              }
            }
          }
        }
      }
    }
  }
}
~~~

To aggregate votes by user and then return to the comment containing the vote, enter nested path **comments.votes**, then reverse to **comments**:

~~~json
{
  "size": 0,
  "aggs": {
    "all_votes": {
      "nested": {
        "path": "comments.votes"
      },
      "aggs": {
        "by_user": {
          "terms": {
            "field": "comments.votes.userId"
          },
          "aggs": {
            "comments": {
              "reverse_nested": {
                "path": "comments"
              },
              "aggs": {
                "by_author": {
                  "terms": {
                    "field": "comments.author"
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
~~~

**reverse_nested.path** must be the root or a nested path above the current context. In this example:

- The nested context starts at **comments.votes**.
- **reverse_nested(path: "comments")** returns to the parent nested comment.
- The **by_author** aggregation can read fields of the comment.

If **path** is omitted, reverse_nested returns to the root document (post), not the comment.

You cannot use reverse_nested to jump laterally to a sibling nested branch that is not an ancestor. To aggregate another branch, return to the root and enter that branch with a new nested aggregation if the query and mapping structure allow it.

## 8. Combining multi-level nested aggregations

You can place a nested aggregation inside another nested aggregation when the mapping has a nested hierarchy.

For example, **orders** has nested **shipments**, and each shipment has nested **packages**:

~~~json
{
  "mappings": {
    "properties": {
      "orderId": {
        "type": "keyword"
      },
      "shipments": {
        "type": "nested",
        "properties": {
          "carrier": {
            "type": "keyword"
          },
          "packages": {
            "type": "nested",
            "properties": {
              "trackingCode": {
                "type": "keyword"
              },
              "weight": {
                "type": "double"
              }
            }
          }
        }
      }
    }
  }
}
~~~

An aggregation can traverse from order to shipment to package:

~~~json
{
  "size": 0,
  "aggs": {
    "shipments": {
      "nested": {
        "path": "shipments"
      },
      "aggs": {
        "by_carrier": {
          "terms": {
            "field": "shipments.carrier"
          },
          "aggs": {
            "packages": {
              "nested": {
                "path": "shipments.packages"
              },
              "aggs": {
                "average_weight": {
                  "avg": {
                    "field": "shipments.packages.weight"
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
~~~

The nested path must be the full path of the nested object. While in the shipment scope, the child aggregation descends into **shipments.packages**.

If you need to count shipments that have packages in a certain bucket, use reverse_nested from package to **shipments**. If you need to count unique orders, use reverse_nested from package to root by omitting path.

## 9. Distinguishing doc_count across levels

An aggregation tree can contain multiple **doc_count** values with different meanings. Do not compare them without verifying their scope.

With the structure:

~~~text
orders
  └─ nested(lines)
       └─ terms(sku)
            └─ reverse_nested(root)
                 └─ terms(status)
~~~

Meaning:

| Location | Scope of doc_count |
|---|---|
| **nested(lines).doc_count** | Total nested line documents belonging to the selected orders |
| **terms(sku).buckets[].doc_count** | Number of line documents in each SKU bucket |
| **reverse_nested(root).doc_count** | Number of unique parent orders with a line in the bucket |
| **terms(status).buckets[].doc_count** after reverse_nested | Number of parent orders per status within the SKU bucket |

For instance, an order with three lines of the same SKU increments **terms(sku).doc_count** by 3, yet increments **reverse_nested.doc_count** by only 1.

### Metrics also depend on scope

**sum(lines.quantity)** inside nested context sums quantities of line documents. **sum(total)** after reverse_nested sums total amounts of parent orders.

Placing a metric in the wrong scope can produce numbers that are technically valid yet wrong in business meaning. Name aggregations to reflect the measured unit, such as **line_count**, **distinct_order_count**, **sum_line_quantity**, or **average_parent_order_total**.

## 10. Calculating line totals from nested lines

A common use case is computing the value of each order line and aggregating by SKU or category.

If each line has **quantity** and **unitPrice**, a standard **sum** aggregation does not automatically multiply two fields. You can use **scripted_metric** or runtime/script fields depending on requirements and version, though you must weigh the cost.

Another approach is pre-indexing **lineTotal** into each nested object when writing the document:

~~~json
{
  "sku": "KB-100",
  "quantity": 2,
  "unitPrice": 100.0,
  "lineTotal": 200.0
}
~~~

Mapping:

~~~java
@Field(type = FieldType.Double)
private Double lineTotal;
~~~

Then the nested aggregation can sum directly:

~~~json
{
  "aggs": {
    "lines": {
      "nested": {
        "path": "lines"
      },
      "aggs": {
        "by_sku": {
          "terms": {
            "field": "lines.sku"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "lines.lineTotal"
              }
            },
            "orders": {
              "reverse_nested": {}
            }
          }
        }
      }
    }
  }
}
~~~

This is an example of preparing data for aggregation. If **lineTotal** is indexed, the application must ensure it is consistently recomputed whenever quantity or unitPrice changes.

## 11. Running nested aggregations with Spring Data Elasticsearch

For nested aggregations, **ElasticsearchOperations** combined with **NativeQuery** is usually more flexible than derived repository methods. Query DSL remains the clearest way to express and inspect an aggregation tree.

Query snippet example:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withAggregation("all_lines", Aggregation.of(a -> a
        .nested(n -> n.path("lines"))
        .aggregations("by_sku", Aggregation.of(bySku -> bySku
            .terms(t -> t.field("lines.sku"))
            .aggregations("orders", Aggregation.of(parent -> parent
                .reverseNested(r -> r)
            ))
        ))
    ))
    .withMaxResults(0)
    .build();

SearchHits<PurchaseOrder> result =
    operations.search(query, PurchaseOrder.class);
~~~

This builder snippet illustrates the Elasticsearch Java API Client used by modern Spring Data Elasticsearch releases. Overload names or aggregation configuration methods can vary across release trains; verify against your actual dependencies before applying. Some versions may use **withAggregation** with **Aggregation** from a specific client package.

**withMaxResults(0)** in the example expresses the intent to return only aggregations without document hits; if your API version represents **size: 0** differently, configure according to that API.

### Reading aggregation results

The **SearchHits<T>** result holds search metadata and the aggregation container:

~~~java
SearchHits<PurchaseOrder> result =
    operations.search(query, PurchaseOrder.class);

AggregationsContainer<?> aggregations =
    result.getAggregations();
~~~

The concrete container type depends on client integration. With the Elasticsearch Java API Client, Spring Data provides a dedicated implementation to hold aggregation responses. From that container, retrieve aggregations by name (**all_lines**, **by_sku**, **orders**) and map buckets and metrics to application DTOs.

Do not assume the aggregation container is a plain **Map<String, Object>** or serialize raw client objects directly to API responses. Use the aggregation API of your exact version to read **Aggregate**, buckets, **docCount**, and metric values.

### Mapping results to DTOs

Example target DTO structure:

~~~java
public record SkuOrderStats(
    String sku,
    long lineCount,
    long orderCount
) {}

public record NestedOrderSummary(
    List<SkuOrderStats> items
) {}
~~~

The mapper will read:

- The terms bucket **key** as SKU.
- The terms bucket **doc_count** as lineCount.
- The reverse_nested **doc_count** as orderCount.

Exact bucket extraction depends on the aggregate type and Java API Client version. Keep conversion logic in a dedicated adapter/service so controllers receive stable DTOs.

## 12. When to use @Query vs. Operations?

Repository annotations are convenient for fixed queries, whereas nested aggregations typically involve multi-layer structures and specialized result handling.

Use **ElasticsearchOperations/NativeQuery** when:

- Multiple nested aggregations are layered together.
- **reverse_nested** is needed to compute statistics on parent fields.
- Nested aggregations must combine with filter, terms, metric, or pipeline aggregations.
- Queries have runtime conditions.
- You need **size: 0** to return only statistics.
- Index or alias must be chosen at call time.
- Multiple buckets must be read and mapped to custom DTOs.

If a query is simple and your Spring Data version supports an appropriate repository return type, a repository method can work. Avoid forcing a complex aggregation tree into a long derived method name or hard-to-maintain string.

## 13. Limits and performance considerations

Nested mapping incurs overhead because each nested object is indexed as a separate Lucene document. An order with 20 lines creates 20 additional linked nested documents. With multi-level nesting and large element counts, total Lucene documents increase substantially.

Considerations:

- Declare nested only on object arrays that must preserve element relationships.
- Bound the number of nested objects per parent per business rules.
- Do not aggregate over overly broad nested paths unnecessarily.
- Use filters to narrow the parent document set before entering nested aggregations.
- Limit terms bucket count using an appropriate size.
- Consider shard_size when top-terms accuracy across multiple shards matters.
- Do not treat cardinality as an exact count; it is an approximate metric.
- Measure query latency and response size with production-like data.

**reverse_nested** is powerful but not free. When a bucket holds many nested documents, switching back to parent documents and running additional aggregations increases work. Create only the statistical branches actually needed.

### Terms buckets can be capped

**terms** usually returns only a top subset of buckets according to size. If you need statistics across all distinct values with very high cardinality, consider composite aggregation to paginate buckets. **search_after** for hit documents and **after_key** for composite aggregations are two different cursor mechanisms and are not interchangeable.

## 14. Common mistakes with nested and reverse_nested

| Symptom | Possible cause | Resolution |
|---|---|---|
| Nested query does not match | Field is mapped as object instead of nested | Inspect the actual mapping |
| Nested aggregation reports invalid path | Using Java property name instead of mapped nested path | Use the full indexed path |
| doc_count is larger than order count | Counting nested documents rather than parent documents | Add reverse_nested to count parents |
| Orders are over-counted in code | Summing line counts instead of reading parent bucket count | Read reverse_nested.doc_count |
| Aggregation includes non-matching lines | Top-level nested query only filters parent orders | Add a filter aggregation inside nested scope |
| Cannot read root fields in nested scope | Have not reverse_nested back to parent | Add reverse_nested before aggregating root fields |
| Invalid reverse_nested path | Path is neither root nor a nested ancestor | Use root or a valid nested parent path |
| Cannot aggregate sibling nested branch | Trying to reverse_nested sideways into a sibling branch | Return to a common ancestor then nest into target branch |
| Metric has wrong unit | Metric placed in wrong nested/parent scope | Check the field and aggregation scope |
| Query is too heavy | Too many nested docs or buckets | Narrow parent set, limit buckets, review mapping |

## 15. Testing nested aggregations

Integration tests should create data with clear parent-child relationships and include cases where one parent has multiple children with the same value to distinguish the two counts.

Example:

| Order | SKU lines |
|---|---|
| ORD-100 | KB-100, MS-200, MS-200 |
| ORD-101 | KB-100 |
| ORD-102 | MS-200 |

Expected results:

| SKU | Nested line count | Parent order count |
|---|---:|---:|
| KB-100 | 2 | 2 |
| MS-200 | 3 | 2 |

Tests should verify:

1. The **lines** mapping is nested.
2. The nested aggregation enters the right path.
3. Terms buckets count nested line documents.
4. Reverse_nested returns to root orders.
5. Parent order count does not increase for duplicate SKU lines within the same order.
6. Metrics on root fields are computed only after reverse_nested.
7. Filter aggregations aggregate only nested documents matching the condition.
8. Multi-level nested paths and reverse_nested paths target the right ancestors.
9. Queries matching zero parent documents still return valid empty aggregations.
10. Mapping results to DTOs preserves statistical meaning and units.

Skeleton:

~~~java
@Test
void countsNestedLinesAndDistinctParentOrders() {
    // Index ORD-100 with KB-100, MS-200, MS-200.
    // Index ORD-101 with KB-100.
    // Index ORD-102 with MS-200.
    // Run nested -> terms(sku) -> reverse_nested aggregation.
    // Assert KB-100 has 2 lines and 2 orders.
    // Assert MS-200 has 3 lines and 2 orders.
}
~~~

This is a test skeleton. Index creation, waiting for refresh, and bucket reading depend on your Elasticsearch and Spring Data Elasticsearch versions.

## 16. Checklist for designing nested statistics

- [ ] Object arrays that truly need relationship preservation are mapped as nested.
- [ ] Nested paths match the actual mapping.
- [ ] Top-level queries select the right parent documents.
- [ ] Nested aggregations are used to enter the right child scope.
- [ ] Filter aggregations are added when only a specific subset of children should be aggregated.
- [ ] Terms buckets are understood as nested document counts.
- [ ] reverse_nested is used when parent document counts are needed.
- [ ] reverse_nested path points to root or a valid nested ancestor.
- [ ] Metrics are placed in the right scope: child or parent.
- [ ] Multi-level aggregations maintain valid nested/reverse_nested ordering.
- [ ] Bucket counts, nested object counts, and responses are bounded.
- [ ] Aggregation results are mapped to DTOs whose names reflect exact units.
- [ ] Integration tests distinguish child count from parent count.
- [ ] Mapping changes are rolled out via a new index and reindexing when needed.

**nested** shifts aggregation scope from parent documents into child objects to aggregate individual elements accurately. **reverse_nested** brings the scope back to parent or nested ancestor documents, allowing unique parent counts and aggregations over parent-level fields. When reading results, always identify whether **doc_count** counts nested documents or parent documents; that distinction determines whether statistics accurately reflect business reality.
