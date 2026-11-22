# Nested, reverse_nested và thống kê quan hệ lồng nhau

Khi document Elasticsearch chứa một mảng object, đôi khi ứng dụng cần giữ nguyên quan hệ giữa các thuộc tính bên trong từng phần tử. Ví dụ một đơn hàng có nhiều dòng hàng; mỗi dòng có SKU, số lượng, đơn giá và trạng thái. Ta có thể muốn thống kê số dòng theo SKU, đếm có bao nhiêu đơn hàng chứa từng SKU, hoặc tính doanh thu trung bình của các đơn hàng có chứa SKU đó.

Mapping kiểu **nested** giúp Elasticsearch giữ từng object con như một đơn vị có thể truy vấn và tổng hợp độc lập. Trong aggregation, **nested** đi từ document cha vào tập document nested; **reverse_nested** đi ngược từ document nested về document cha hoặc một cấp nested cha. Hai aggregation này cho phép thống kê trên hai phạm vi khác nhau trong cùng một cây kết quả.

Bài học này giải thích cách chọn mapping nested, cách đọc đúng phạm vi của **doc_count**, cách kết hợp nested và reverse_nested, cách xử lý nhiều cấp lồng nhau và cách truy xuất aggregation trong Spring Data Elasticsearch.

## 1. Vì sao cần nested mapping?

Giả sử một đơn hàng có nhiều dòng hàng:

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

Mỗi phần tử trong **lines** là một object có quan hệ nội bộ giữa **sku**, **category**, **quantity** và **unitPrice**.

Nếu Elasticsearch mapping **lines** là kiểu **object** thông thường, các object trong mảng được flatten thành các giá trị field. Một truy vấn kết hợp **lines.sku = KB-100** và **lines.category = mouse** có thể khớp vì hai giá trị tồn tại đâu đó trong cùng document, dù chúng nằm ở hai phần tử khác nhau.

Đây là vấn đề khi nghiệp vụ yêu cầu các điều kiện phải thuộc cùng một dòng hàng.

Với **nested**, Elasticsearch index từng phần tử object như một nested document riêng, đồng thời giữ quan hệ với document cha. Khi đó, query và aggregation có thể làm việc trên đúng từng object con.

### Object và nested khác nhau

| Mapping | Cách lưu mảng object | Quan hệ giữa field trong cùng phần tử |
|---|---|---|
| **object** | Các giá trị được flatten vào document cha | Không bảo toàn ranh giới object cho truy vấn kết hợp |
| **nested** | Mỗi phần tử được index như nested document riêng | Có thể truy vấn và aggregate theo từng object |

Nested không phải kiểu dữ liệu mặc định cần dùng cho mọi mảng object. Nó tạo thêm Lucene documents và có chi phí index, lưu trữ, query. Chỉ dùng khi cần giữ quan hệ giữa các field bên trong từng object.

## 2. Khai báo nested trong Spring Data Elasticsearch

Entity đơn hàng:

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

Object con:

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

Annotation **@Field(type = FieldType.Nested)** yêu cầu Spring Data tạo mapping nested cho property **lines** khi ứng dụng tạo mapping từ entity metadata.

Mapping tương đương trong Elasticsearch:

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

Tên field trong Query DSL phải khớp tên field thực tế trong mapping. Nếu ứng dụng dùng **FieldNamingStrategy**, **@Field(name = "...")** hoặc tên field tùy chỉnh, hãy dùng tên đã được mapping.

### Thay đổi object thành nested cần reindex

Không thể đổi trực tiếp một field đã được tạo với mapping **object** thành **nested** trên cùng index hiện có. Mapping field đã tồn tại không thể đổi kiểu theo cách này. Cần tạo index mới với mapping đúng, reindex dữ liệu, rồi chuyển alias hoặc luồng đọc/ghi theo kế hoạch migration.

## 3. Nested aggregation đi vào document con

Một aggregation thông thường chạy trên tập document mà query trả về. Nhưng khi muốn thống kê field nằm trong **lines**, cần chuyển phạm vi aggregation từ order document sang nested documents.

Aggregation **nested** thực hiện việc đó:

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

Cách đọc:

1. Search chọn tập order ở cấp document cha.
2. **nested** với path **lines** đi vào các dòng hàng của những order đó.
3. **terms** nhóm các nested documents theo **lines.sku**.
4. Mỗi bucket SKU chứa các nested documents thuộc SKU đó.

Nếu một order có hai dòng cùng SKU, hai nested documents có thể được tính trong bucket đó. **doc_count** tại bucket nested là số nested documents, không phải số order duy nhất.

### Ví dụ kết quả

Giả sử có ba order:

- ORD-100 có một dòng KB-100 và hai dòng MS-200.
- ORD-101 có một dòng KB-100.
- ORD-102 có một dòng MS-200.

Kết quả **terms** trong nested aggregation có thể có dạng:

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

Ở ví dụ này, **all_lines.doc_count** là tổng nested documents thuộc các order đã chọn. **by_sku.doc_count** đếm số dòng hàng, không phải số order chứa SKU.

Đây là khác biệt quan trọng nhất khi đọc thống kê nested.

## 4. reverse_nested đi từ nested document về document cha

Sau khi nhóm nested documents theo SKU, có thể muốn biết mỗi SKU xuất hiện trong bao nhiêu đơn hàng. Đó là lúc dùng **reverse_nested**.

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

**reverse_nested** quay lại document cha ở root. Trong mỗi bucket SKU:

- **by_sku.doc_count** đếm nested line documents.
- **orders.doc_count** đếm các order cha duy nhất có ít nhất một line thuộc bucket SKU đó.

Ví dụ response:

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

Nếu ORD-100 có hai dòng MS-200, **by_sku** vẫn đếm hai nested documents, nhưng **orders.doc_count** chỉ đếm ORD-100 một lần cho bucket đó. Đây là cách phân biệt “số dòng hàng” với “số đơn hàng có chứa sản phẩm”.

### reverse_nested không phải phép đếm ngược đơn giản

**reverse_nested** không trả về parent object trong JSON như một danh sách. Nó chuyển phạm vi aggregation sang tập parent documents để các aggregation con tiếp theo có thể thống kê field của cha.

Khi không truyền **path**, reverse_nested quay về root document. Nếu truyền path, nó quay về một nested parent cụ thể nằm phía trên nested context hiện tại.

## 5. Thống kê field của document cha sau reverse_nested

Khi đã quay về order document, có thể aggregate trên các field root như **status**, **customerId** hoặc **total**.

Ví dụ: với mỗi SKU, thống kê số order theo trạng thái và tổng giá trị trung bình của các order có chứa SKU đó:

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

Phạm vi thay đổi theo từng tầng:

~~~text
Order documents (root)
        |
        | nested(path = lines)
        v
Nested line documents
        |
        | terms(lines.sku)
        v
Một bucket SKU
        |
        | reverse_nested()
        v
Các order cha có ít nhất một line thuộc SKU
        |
        +-- terms(status)
        |
        +-- avg(total)
~~~

**average_order_total** là trung bình tổng tiền của các order cha thuộc bucket SKU, không phải trung bình **unitPrice** của các dòng hàng. Nếu một order có nhiều line cùng SKU, order đó vẫn chỉ được tính một lần trong phạm vi parent documents sau reverse_nested.

### Mỗi bucket nested có thể thống kê cả hai cấp

Có thể đặt metric trước và sau reverse_nested:

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

Trong một bucket SKU:

- **line_quantity** cộng số lượng của các dòng hàng.
- **average_unit_price** tính giá đơn vị trung bình trên các nested documents.
- **orders.doc_count** đếm số order cha duy nhất.
- **average_order_total** tính trung bình trường total của những order cha đó.

Tên metric nên thể hiện rõ phạm vi để người đọc không nhầm số liệu ở cấp line với số liệu ở cấp order.

## 6. Filter nested documents trước khi thống kê

Một điểm dễ nhầm là query ở cấp root và aggregation ở cấp nested có phạm vi khác nhau.

Giả sử top-level query dùng nested query để chọn các order có ít nhất một line với SKU **KB-100**:

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

Query này chọn các order có ít nhất một dòng **KB-100**. Tuy nhiên, nếu sau đó aggregation **nested(path: lines)** được thực hiện trên những order đã chọn, aggregation có thể nhìn thấy tất cả các line của các order đó, bao gồm cả SKU khác.

Nếu mục tiêu là chỉ thống kê các line **KB-100**, cần lặp điều kiện trong một **filter** aggregation bên trong nested aggregation:

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

Hai điều kiện có vai trò khác nhau:

- Top-level nested query xác định order document nào được đưa vào kết quả.
- Filter aggregation trong nested scope xác định line document nào được thống kê.

Nếu chỉ cần aggregation trên tất cả line thuộc những order đã chọn, không cần filter lặp. Nếu cần chỉ thống kê những nested object thỏa điều kiện cụ thể, hãy thêm filter trong nested aggregation.

### Filter theo nhiều thuộc tính cùng một nested object

Để đảm bảo SKU và category cùng thuộc một line, dùng một nested query chứa cả hai điều kiện:

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

Nếu hai điều kiện được đặt trong hai nested query độc lập, chúng có thể khớp hai line khác nhau trong cùng order. Khi nghiệp vụ yêu cầu cùng một object con phải thỏa cả hai, hãy đặt chúng trong cùng một nested query.

## 7. reverse_nested với path cụ thể

Trong nested hierarchy, một nested document có thể có nested parent. **reverse_nested** có thể quay về root hoặc một nested ancestor.

Ví dụ mapping có **comments** nested, bên trong mỗi comment có **votes** nested:

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

Để thống kê vote theo user rồi quay về comment chứa vote, dùng nested path **comments.votes**, sau đó reverse về **comments**:

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

**reverse_nested.path** phải là root hoặc một nested path nằm phía trên context hiện tại. Trong ví dụ này:

- Nested context bắt đầu ở **comments.votes**.
- **reverse_nested(path: "comments")** quay về comment nested cha.
- Aggregation **by_author** có thể đọc field của comment.

Nếu bỏ **path**, reverse_nested quay về root document (post), không phải comment.

Không thể dùng reverse_nested để nhảy sang một nhánh nested sibling không phải ancestor. Muốn thống kê nhánh khác, cần quay về root rồi đi vào nhánh đó bằng một nested aggregation mới nếu cấu trúc query và mapping cho phép.

## 8. Kết hợp nested nhiều cấp

Có thể đặt một nested aggregation bên trong một nested aggregation khác khi mapping có nested hierarchy.

Ví dụ **orders** có **shipments** nested, và mỗi shipment có **packages** nested:

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

Aggregation có thể đi từ order đến shipment rồi đến package:

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

Nested path phải là path đầy đủ của nested object. Khi đang ở shipment scope, aggregation con đi sâu vào **shipments.packages**.

Nếu cần đếm số shipment có package thuộc bucket nào đó, có thể dùng reverse_nested từ package về **shipments**. Nếu cần đếm số order duy nhất, reverse_nested từ package về root bằng cách bỏ path.

## 9. Phân biệt doc_count ở từng cấp

Một aggregation tree có thể chứa nhiều **doc_count** mang ý nghĩa khác nhau. Không nên so sánh chúng nếu chưa xác định phạm vi.

Với cấu trúc:

~~~text
orders
  └─ nested(lines)
       └─ terms(sku)
            └─ reverse_nested(root)
                 └─ terms(status)
~~~

Ý nghĩa:

| Vị trí | Phạm vi của doc_count |
|---|---|
| **nested(lines).doc_count** | Tổng số nested line documents thuộc tập order đã chọn |
| **terms(sku).buckets[].doc_count** | Số line documents trong từng SKU bucket |
| **reverse_nested(root).doc_count** | Số order cha duy nhất có line thuộc bucket |
| **terms(status).buckets[].doc_count** sau reverse_nested | Số order cha theo từng status trong bucket SKU |

Ví dụ, một order có ba dòng cùng SKU có thể làm **terms(sku).doc_count** tăng 3 nhưng chỉ làm **reverse_nested.doc_count** tăng 1.

### Metric cũng phụ thuộc scope

**sum(lines.quantity)** bên trong nested context cộng số lượng của line documents. **sum(total)** sau reverse_nested cộng tổng tiền của các order cha.

Đặt metric sai scope có thể tạo số liệu hợp lệ về mặt kỹ thuật nhưng sai ý nghĩa nghiệp vụ. Hãy đặt tên aggregation phản ánh đơn vị được đo, ví dụ **line_count**, **distinct_order_count**, **sum_line_quantity** hoặc **average_parent_order_total**.

## 10. Tính tổng tiền từ nested line

Một use case thường gặp là tính giá trị từng dòng hàng rồi tổng hợp theo SKU hoặc category.

Nếu mỗi line có **quantity** và **unitPrice**, aggregation **sum** thông thường không tự nhân hai field. Có thể dùng **scripted_metric** hoặc runtime/script field tùy yêu cầu và phiên bản, nhưng cần cân nhắc chi phí.

Một cách khác là index sẵn **lineTotal** vào từng nested object khi ghi document:

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

Khi đó nested aggregation có thể tính tổng trực tiếp:

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

Đây là ví dụ về việc chuẩn bị dữ liệu phục vụ aggregation. Nếu **lineTotal** được index, ứng dụng cần bảo đảm nó luôn được tính nhất quán khi quantity hoặc unitPrice thay đổi.

## 11. Chạy nested aggregation bằng Spring Data Elasticsearch

Với aggregation lồng nhau, **ElasticsearchOperations** kết hợp **NativeQuery** thường linh hoạt hơn derived repository method. Query DSL vẫn là cách dễ nhất để biểu diễn và kiểm tra cây aggregation.

Ví dụ phần truy vấn:

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

Đoạn builder minh họa API của Elasticsearch Java API Client được dùng bởi các release Spring Data Elasticsearch hiện đại. Tên overload hoặc cách cấu hình aggregation có thể khác giữa các release train; đối chiếu dependency thực tế trước khi áp dụng. Một số phiên bản có thể dùng **withAggregation** với **Aggregation** từ package client cụ thể.

**withMaxResults(0)** trong ví dụ thể hiện mục đích chỉ lấy aggregation, không cần document hits; nếu API phiên bản đang dùng biểu diễn **size: 0** theo cách khác, cấu hình theo API đó.

### Đọc aggregation result

Kết quả **SearchHits<T>** giữ metadata tìm kiếm và aggregation container:

~~~java
SearchHits<PurchaseOrder> result =
    operations.search(query, PurchaseOrder.class);

AggregationsContainer<?> aggregations =
    result.getAggregations();
~~~

Kiểu cụ thể của container phụ thuộc client tích hợp. Với Elasticsearch Java API Client, Spring Data cung cấp implementation riêng để giữ aggregation response. Từ container đó, truy xuất aggregation theo tên (**all_lines**, **by_sku**, **orders**) rồi chuyển các bucket và metric sang DTO của ứng dụng.

Không nên giả định aggregation container là một **Map<String, Object>** thuần hoặc serialize nguyên object client ra API. Hãy dùng API aggregation của đúng phiên bản để đọc **Aggregate**, bucket, **docCount** và metric value.

### Chuyển kết quả sang DTO

Ví dụ cấu trúc DTO mong muốn:

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

Mapper sẽ đọc:

- **key** của bucket terms làm SKU.
- **doc_count** của bucket terms làm lineCount.
- **doc_count** của reverse_nested làm orderCount.

Cách lấy bucket cụ thể phụ thuộc kiểu aggregate và phiên bản Java API Client. Giữ phần chuyển đổi trong một adapter/service riêng để controller chỉ nhận DTO ổn định.

## 12. Khi nào dùng @Query và khi nào dùng Operations?

Repository annotation thuận tiện cho query cố định, nhưng aggregation lồng nhau thường cần cấu trúc nhiều tầng và xử lý kết quả chuyên biệt.

Dùng **ElasticsearchOperations/NativeQuery** khi:

- Có nhiều nested aggregation lồng nhau.
- Cần **reverse_nested** để thống kê field của parent.
- Cần kết hợp nested aggregation với filter, terms, metric hoặc pipeline aggregation.
- Query có điều kiện runtime.
- Cần trả **size: 0** và chỉ lấy thống kê.
- Cần chọn index hoặc alias tại thời điểm gọi.
- Cần đọc nhiều bucket và chuyển thành DTO riêng.

Nếu query đơn giản và phiên bản Spring Data hỗ trợ kiểu repository return phù hợp, có thể dùng repository method. Nhưng không nên ép một aggregation tree phức tạp vào method có tên dài hoặc một chuỗi khó bảo trì.

## 13. Những giới hạn và lưu ý hiệu năng

Nested mapping có chi phí vì mỗi nested object được index như một Lucene document riêng. Một order có 20 lines tạo thêm 20 nested documents liên quan. Với document có nhiều cấp nested và số phần tử lớn, tổng số Lucene documents tăng đáng kể.

Các lưu ý:

- Chỉ khai báo nested cho object array cần giữ quan hệ.
- Giới hạn số nested objects trong một parent theo nghiệp vụ.
- Không aggregate trên nested path quá rộng nếu không cần.
- Dùng filter để giảm tập parent documents trước khi đi vào nested aggregation.
- Giới hạn số bucket của terms bằng size phù hợp.
- Cân nhắc shard_size khi cần độ chính xác của top terms trên nhiều shard.
- Không dùng cardinality như phép đếm chính xác tuyệt đối; đây là metric ước lượng.
- Đo thời gian query và kích thước response với dữ liệu gần production.

**reverse_nested** có thể hữu ích nhưng không miễn phí. Khi bucket có nhiều nested documents, việc chuyển về tập parent documents và chạy thêm aggregation có thể làm tăng công việc. Hãy chỉ tạo các nhánh thống kê thực sự cần thiết.

### Terms bucket có thể bị giới hạn

**terms** thường chỉ trả một số bucket đầu theo size. Nếu cần thống kê toàn bộ giá trị distinct với tập cardinality rất lớn, cân nhắc composite aggregation để phân trang bucket. **search_after** của hit documents và **after_key** của composite aggregation là hai cơ chế cursor khác nhau, không dùng thay thế cho nhau.

## 14. Các lỗi thường gặp khi dùng nested và reverse_nested

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Nested query không khớp | Field được mapping là object thay vì nested | Kiểm tra mapping thực tế |
| Nested aggregation báo sai path | Dùng tên property Java thay vì nested path trong mapping | Dùng path đầy đủ đã index |
| doc_count lớn hơn số order | Đang đếm nested documents, không phải parent documents | Thêm reverse_nested để đếm parent |
| Số order bị đếm nhiều lần trong code | Cộng line counts thay vì dùng parent bucket count | Đọc reverse_nested.doc_count |
| Aggregation chứa cả line không khớp | Top-level nested query chỉ lọc parent order | Thêm filter aggregation trong nested scope |
| Không đọc được field root trong nested scope | Chưa reverse_nested về parent | Thêm reverse_nested trước aggregation root field |
| reverse_nested path không hợp lệ | Path không phải root hoặc nested ancestor | Dùng root hoặc nested parent path hợp lệ |
| Không thống kê được nested sibling | Cố reverse_nested sang nhánh sibling | Quay về ancestor chung rồi nested vào nhánh cần dùng |
| Giá trị metric sai đơn vị | Metric đặt sai nested/parent scope | Kiểm tra field và phạm vi aggregation |
| Query quá nặng | Quá nhiều nested docs hoặc bucket | Giảm tập parent, giới hạn bucket, xem lại mapping |

## 15. Kiểm thử nested aggregation

Integration test nên tạo dữ liệu có quan hệ cha-con rõ ràng và có trường hợp một parent chứa nhiều child cùng giá trị để phân biệt hai loại đếm.

Ví dụ:

| Order | SKU lines |
|---|---|
| ORD-100 | KB-100, MS-200, MS-200 |
| ORD-101 | KB-100 |
| ORD-102 | MS-200 |

Kết quả mong đợi:

| SKU | Nested line count | Parent order count |
|---|---:|---:|
| KB-100 | 2 | 2 |
| MS-200 | 3 | 2 |

Test cần xác nhận:

1. Mapping **lines** là nested.
2. Nested aggregation đi đúng path.
3. Terms bucket đếm nested line documents.
4. Reverse_nested quay về root order.
5. Parent order count không tăng theo số line trùng SKU trong cùng order.
6. Metric trên field root chỉ được tính sau reverse_nested.
7. Filter aggregation chỉ thống kê nested documents thỏa điều kiện.
8. Multi-level nested path và reverse_nested path đúng ancestor.
9. Query với không có parent document vẫn trả aggregation rỗng hợp lệ.
10. Kết quả chuyển sang DTO giữ đúng ý nghĩa và đơn vị thống kê.

Skeleton:

~~~java
@Test
void countsNestedLinesAndDistinctParentOrders() {
    // Index ORD-100 với KB-100, MS-200, MS-200.
    // Index ORD-101 với KB-100.
    // Index ORD-102 với MS-200.
    // Chạy nested -> terms(sku) -> reverse_nested aggregation.
    // Xác nhận KB-100 có 2 line và 2 order.
    // Xác nhận MS-200 có 3 line và 2 order.
}
~~~

Đây là skeleton kiểm thử. Cách tạo index, chờ refresh và đọc bucket phụ thuộc phiên bản Elasticsearch và Spring Data Elasticsearch đang dùng.

## 16. Checklist thiết kế thống kê nested

- [ ] Mảng object thực sự cần giữ quan hệ đã được mapping là nested.
- [ ] Nested path trùng với mapping thực tế.
- [ ] Top-level query chọn đúng parent documents.
- [ ] Nested aggregation được dùng để đi vào đúng child scope.
- [ ] Filter aggregation được thêm nếu chỉ muốn thống kê một tập child cụ thể.
- [ ] Terms bucket được hiểu là số nested documents.
- [ ] reverse_nested được dùng khi cần đếm parent documents.
- [ ] reverse_nested path chỉ về root hoặc nested ancestor hợp lệ.
- [ ] Metric được đặt đúng scope: child hay parent.
- [ ] Các aggregation nhiều cấp giữ đúng thứ tự nested/reverse_nested.
- [ ] Số bucket, nested object và response được giới hạn.
- [ ] Kết quả aggregation được chuyển sang DTO có tên thể hiện đúng đơn vị.
- [ ] Integration test phân biệt child count và parent count.
- [ ] Mapping thay đổi được triển khai qua index mới và reindex khi cần.

**nested** chuyển aggregation từ document cha vào các object con để thống kê từng phần tử một cách chính xác. **reverse_nested** đưa phạm vi trở lại parent hoặc nested ancestor, nhờ đó có thể đếm số parent duy nhất và aggregate các field ở cấp cha. Khi đọc kết quả, hãy luôn xác định **doc_count** đang đếm nested documents hay parent documents; sự phân biệt đó quyết định thống kê có phản ánh đúng nghiệp vụ hay không.

