# Nested query, inner hits và truy vấn đặc thù

Spring Data Elasticsearch cung cấp nhiều cách xây dựng truy vấn. Query method và Criteria API phù hợp với các điều kiện phổ biến, nhưng những yêu cầu như tìm kiếm trên mảng object có quan hệ theo từng phần tử, lấy lại đúng phần tử con đã khớp, truy vấn địa lý, script query hoặc parent/child thường cần biểu đạt trực tiếp hơn theo Elasticsearch Query DSL.

NativeQuery là lựa chọn quan trọng cho các trường hợp đó. Nó cho phép ứng dụng xây dựng query bằng các kiểu của Elasticsearch Java API Client, sau đó thực thi qua ElasticsearchOperations. Nhờ vậy, ứng dụng vẫn sử dụng mapping metadata và cơ chế chuyển đổi của Spring Data, đồng thời có thể khai thác những query DSL chuyên biệt của Elasticsearch.

Bài học tập trung vào ba nội dung:

- Nested query để truy vấn đúng quan hệ giữa các thuộc tính của cùng một object trong mảng.
- Inner hits để lấy các nested document hoặc child document cụ thể đã khớp với truy vấn.
- Các query đặc thù và cách chọn giữa NativeQuery, CriteriaQuery, @Query và Elasticsearch Java API Client.

## 1. Vì sao cần nested query?

Elasticsearch có kiểu object để lưu object lồng nhau. Tuy nhiên, khi một field object chứa mảng các object, Elasticsearch mặc định phân tích các object con thành các giá trị đa trị của field tương ứng. Quan hệ giữa các field trong cùng một phần tử mảng không còn được bảo toàn theo cách mà nhiều truy vấn nghiệp vụ mong muốn.

Giả sử một sản phẩm có nhiều nhà cung cấp:

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

Yêu cầu nghiệp vụ: tìm sản phẩm có một offer vừa thuộc seller-a, vừa có giá nhỏ hơn hoặc bằng 100.

Nếu offers được map là object, Elasticsearch có thể xem các giá trị tương ứng như:

~~~text
offers.seller    = ["seller-a", "seller-b"]
offers.price     = [120, 95]
offers.available = [true, false]
~~~

Quan hệ giữa seller-a với price 120 và seller-b với price 95 bị mất khi truy vấn các field như những tập giá trị độc lập. Một truy vấn kết hợp seller-a và price nhỏ hơn hoặc bằng 100 có thể khớp sản phẩm dù không có offer đơn lẻ nào thỏa mãn cả hai điều kiện.

Đây là vấn đề sai lệch quan hệ giữa các phần tử mảng, thường được gọi là cross-object matching.

## 2. object và nested khác nhau như thế nào?

Kiểu nested lưu mỗi object con như một hidden document riêng, có liên kết nội bộ với document cha. Nhờ vậy, Elasticsearch có thể đánh giá các điều kiện trên cùng một phần tử object.

| Đặc điểm | object | nested |
| --- | --- | --- |
| Mảng object | Các field con trở thành các giá trị đa trị | Mỗi phần tử object được lưu như nested document |
| Quan hệ giữa các field trong một phần tử | Không bảo toàn cho truy vấn tương quan theo từng object | Được bảo toàn trong nested document |
| Query | Truy vấn field thông thường | Cần nested query để đi vào nested path |
| Kết quả | Trả document cha | Nested query vẫn trả document cha; inner_hits có thể trả object con khớp |
| Chi phí | Thấp hơn, cấu trúc đơn giản | Tốn thêm tài nguyên và chi phí indexing/query |

Không nên chuyển mọi object thành nested. Chỉ dùng nested khi cần truy vấn tương quan giữa nhiều field thuộc cùng một phần tử của mảng object.

### 2.1. Khai báo nested mapping

Với Spring Data Elasticsearch, có thể dùng FieldType.Nested:

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

    // Constructors, getters và setters
}

public class ProductOffer {

    @Field(type = FieldType.Keyword)
    private String seller;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private boolean available;

    // Constructors, getters và setters
}
~~~

Mapping JSON tương ứng có dạng:

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

Kiểu mapping phải là nested ngay từ khi field được tạo. Không thể đổi một field đã có mapping object thành nested trực tiếp. Nếu index đang lưu dữ liệu với kiểu object và cần quan hệ nested, hãy tạo index mới với mapping đúng rồi reindex.

### 2.2. Kiểm tra mapping thực tế

Có thể dùng Elasticsearch API:

~~~http
GET /catalog-products/_mapping
~~~

Hoặc đọc mapping qua Spring Data:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

Document mapping = indexOperations.getMapping();
~~~

Đừng chỉ dựa vào annotation trong source code. Nếu index đã tồn tại từ trước, mapping thực tế có thể không giống entity hiện tại.

## 3. Nested query cơ bản

Nested query yêu cầu chỉ rõ:

- path: đường dẫn tới field có mapping nested.
- query: truy vấn được thực hiện bên trong nested document.
- score_mode: cách kết hợp điểm của các nested document khớp để tạo điểm cho document cha.
- inner_hits: tùy chọn lấy lại các nested document đã khớp.

Ví dụ Query DSL tìm sản phẩm có một offer thuộc seller-a và giá không quá 100:

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

Truy vấn này chỉ khớp khi cùng một nested document trong offers thỏa mãn cả hai điều kiện. Với dữ liệu ví dụ, sản phẩm không khớp vì offer của seller-a có giá 120; offer có giá 95 lại thuộc seller-b.

Nếu đổi seller thành seller-b, sản phẩm khớp hai điều kiện seller và price. Nếu truy vấn còn yêu cầu available true thì sản phẩm lại không khớp vì offer seller-b có available false.

### 3.1. Vì sao dùng bool.filter?

Điều kiện seller và price ở ví dụ là điều kiện lọc. Chúng không cần đóng góp điểm relevance. Dùng bool.filter giúp thể hiện rõ mục tiêu lọc và tránh tính điểm không cần thiết cho các điều kiện đó.

Nếu nested query dùng cho tìm kiếm relevance, có thể đặt điều kiện văn bản trong must hoặc should để điểm của nested document tham gia vào điểm document cha.

### 3.2. score_mode

score_mode quy định cách điểm của các nested document khớp được kết hợp thành điểm của document cha:

| Giá trị | Ý nghĩa |
| --- | --- |
| avg | Trung bình điểm của các nested document khớp |
| max | Lấy điểm cao nhất |
| min | Lấy điểm thấp nhất |
| sum | Cộng các điểm |
| none | Không tính điểm từ nested query cho document cha |

Với truy vấn lọc thuần túy, none thường phù hợp. Với truy vấn relevance trên các phần tử nested, chọn cách kết hợp dựa trên ý nghĩa nghiệp vụ. Không nên mặc định rằng nhiều nested object khớp phải làm điểm cha tăng theo cùng một cách trong mọi bài toán.

## 4. Nested query với NativeQuery

NativeQuery cho phép xây dựng query bằng Elasticsearch Java API Client typed DSL. Đây là cách phù hợp khi query cần nested query, inner hits, script, geo hoặc các tính năng mà Criteria API không biểu đạt thuận tiện.

Ví dụ dùng typed query builder:

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

Các import và overload builder có thể thay đổi theo phiên bản Elasticsearch Java API Client và Spring Data Elasticsearch. Đoạn code minh họa kiểu API của Java client hiện đại; hãy dùng dependency được Spring Boot quản lý để tránh trộn các thế hệ client.

Một số điểm cần chú ý:

- Query trong ví dụ là kiểu co.elastic.clients.elasticsearch._types.query_dsl.Query, không phải org.springframework.data.elasticsearch.core.query.Query.
- NativeQuery là query implementation của Spring Data Elasticsearch, có thể chứa query DSL của Java API Client.
- ElasticsearchOperations.search(...) vẫn chịu trách nhiệm mapping kết quả thành ProductDocument.
- Field path phải khớp mapping thực tế. Nếu mapping dùng offers.seller.keyword, hãy dùng đúng tên field đó.

### 4.1. NativeQuery và CriteriaQuery

| Tiêu chí | CriteriaQuery | NativeQuery |
| --- | --- | --- |
| Cách xây dựng | Criteria API của Spring Data | Typed Query DSL của Elasticsearch Java API Client |
| Truy vấn đơn giản | Dễ đọc, ít phụ thuộc DSL | Có thể dài hơn |
| Nested query và inner hits | Khả năng biểu đạt tùy phiên bản/API | Truy cập trực tiếp các thành phần DSL |
| Query đặc thù | Có giới hạn theo abstraction | Bao phủ query được client hỗ trợ |
| Phụ thuộc client | Ít lộ kiểu query của Java client | Gắn với API của Elasticsearch Java client |

Chọn CriteriaQuery cho điều kiện đơn giản và dễ biểu diễn bằng Criteria. Chọn NativeQuery khi cần toàn bộ khả năng của Elasticsearch DSL hoặc cần kiểm soát chi tiết cấu trúc truy vấn.

## 5. inner_hits là gì?

Nested query trả về document cha nếu có ít nhất một nested document khớp. Trong nhiều trường hợp, ứng dụng còn cần biết nested object nào đã khớp để hiển thị đúng offer, địa chỉ, biến thể sản phẩm hoặc dòng đơn hàng.

inner_hits cho phép Elasticsearch trả kèm các nested document khớp trong từng kết quả cha.

Ví dụ bổ sung inner_hits vào nested query:

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

Kết quả gồm:

- Hit cha là ProductDocument.
- Trong mỗi hit cha, phần inner_hits.matching_offers chứa các nested offer khớp.
- Nested hit có metadata riêng, ví dụ score, source và vị trí nested object trong document cha.

inner_hits.name đặt tên cho nhóm inner hits để ứng dụng lấy đúng nhóm khi query có nhiều nested path hoặc nhiều inner hit definition.

### 5.1. inner_hits không thay đổi document cha

Nested query vẫn trả về document cha. inner_hits chỉ bổ sung phần nested document phù hợp trong response. Nó không biến kết quả tìm kiếm thành danh sách ProductOffer độc lập.

Nếu ứng dụng cần danh sách offer khớp để hiển thị, hãy đọc inner hits từ từng parent hit. Không nên lấy toàn bộ danh sách offers trong source rồi tự lọc lại nếu Elasticsearch đã trả đúng nested matches, đặc biệt khi nested object có nhiều field hoặc logic query phức tạp.

### 5.2. size, from, sort và source filtering

Các tùy chọn phổ biến trong inner hits:

| Tùy chọn | Công dụng |
| --- | --- |
| name | Đặt tên nhóm inner hits |
| size | Số nested hit tối đa trả về cho mỗi parent hit |
| from | Bỏ qua một số nested hit đầu tiên |
| sort | Sắp xếp nested hit |
| _source | Chỉ lấy các field cần thiết trong nested source |
| highlight | Trả highlight cho field nested phù hợp |
| explain | Trả chi tiết tính điểm, hữu ích khi debug |

Kích thước inner hits có thể làm response lớn đáng kể vì được áp dụng cho mỗi parent hit. Ví dụ, 50 parent hit với 20 inner hit mỗi hit có thể tạo ra 1.000 nested hit trong response. Hãy đặt size vừa đủ cho giao diện và giới hạn tổng kết quả.

## 6. Đọc inner hits trong Spring Data Elasticsearch

Kết quả từ ElasticsearchOperations.search(...) được biểu diễn bằng SearchHits<T>. Mỗi SearchHit<T> có thể chứa map inner hits theo tên.

Ví dụ:

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
        // Chuyển đổi hoặc xử lý nested hit theo kiểu trả về của phiên bản.
    }
}
~~~

Kiểu content cụ thể của inner hit phụ thuộc cách Spring Data ánh xạ nested hit và phiên bản đang dùng. Có thể nhận được object đã map hoặc cấu trúc dữ liệu trung gian; hãy kiểm tra kiểu thực tế và mapping metadata của nested class. Không nên ép kiểu mù từ Object.

Nếu cần trả kết quả cho API, nên chuyển nested hit sang DTO response rõ ràng. Không để kiểu SearchHit<?> hoặc cấu trúc nội bộ của Elasticsearch client lan ra ngoài tầng persistence.

### 6.1. Inner hits có thể có nhiều nhóm

Một truy vấn có thể chứa nhiều nested query, mỗi query có inner hits riêng:

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

Trong response, ứng dụng có thể lấy hai nhóm bằng key seller_offers và high_rating_reviews. Mỗi nhóm có ý nghĩa riêng và giới hạn riêng.

## 7. Những lỗi logic thường gặp với nested query

### 7.1. Đặt điều kiện cùng object ở hai nested query riêng

Giả sử yêu cầu là cùng một offer phải có seller-a và price dưới 100. Nếu viết hai nested query độc lập trong bool:

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

Hai nested query có thể khớp hai nested object khác nhau. Document cha được chọn nếu tồn tại một offer thuộc seller-a và tồn tại một offer (có thể khác) có giá dưới 100.

Nếu hai điều kiện phải đúng trên cùng offer, hãy đặt chúng trong một nested query duy nhất, bên trong một bool query:

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

Đây là điểm quan trọng nhất khi truy vấn mảng nested: xác định rõ điều kiện cần áp dụng trên cùng một phần tử hay trên các phần tử khác nhau.

### 7.2. Quên khai báo mapping nested

Nested query chỉ hoạt động trên field đã được map kiểu nested. Nếu field là object thông thường, Elasticsearch sẽ báo lỗi khi query nested vào path đó. Kiểm tra mapping trước khi sửa query.

### 7.3. Sai path hoặc field path

Path phải trỏ tới nested field, ví dụ offers. Các field trong query thường dùng tên đầy đủ như offers.price. Sai tên, sai chữ hoa/thường hoặc nhầm field multi-field có thể làm query không khớp.

### 7.4. Nhầm inner hits với source filtering

Source filtering chỉ chọn field nào xuất hiện trong _source của parent hit. Nó không lọc danh sách object con theo điều kiện query. Muốn lấy đúng nested object khớp, dùng inner_hits.

### 7.5. Không giới hạn inner hits

Không đặt size lớn mặc định nếu parent document có nhiều nested object. Điều này làm tăng response size, network traffic và chi phí deserialize. Chỉ lấy field cần dùng, sắp xếp rõ ràng và phân trang nested hit nếu phù hợp.

## 8. Nested trong nested: multi-level nested query

Một nested object có thể chứa nested object khác. Ví dụ đơn hàng có mảng items, mỗi item có mảng adjustments:

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

Truy vấn tìm đơn hàng có item SKU KB-1042 và adjustment loại discount:

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

Elasticsearch hỗ trợ nested query nhiều cấp và có thể tự xác định nested context cho đường dẫn phù hợp trong query lồng nhau. Tuy nhiên, cấu trúc query nên phản ánh đúng quan hệ cha-con. Nếu cần lấy cả item lẫn adjustment đã khớp, có thể khai báo inner_hits ở từng nested level với tên riêng.

Nested nhiều cấp làm tăng độ phức tạp mapping và chi phí truy vấn. Chỉ nên dùng khi quan hệ dữ liệu thực sự cần bảo toàn ở từng cấp.

## 9. Parent/child query và join field

Nested phù hợp khi object con nằm trong cùng document vật lý và thường được đọc cùng document cha. Nếu quan hệ cha-con cần các document độc lập, có thể cân nhắc kiểu join của Elasticsearch.

Ví dụ sản phẩm là parent, review là child document:

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

Một document parent:

~~~json
{
  "sku": "KB-1042",
  "relation": "product"
}
~~~

Một document child:

~~~json
{
  "rating": 5,
  "relation": {
    "name": "review",
    "parent": "product-1001"
  }
}
~~~

Parent và child phải được lưu trong cùng một index và cùng routing shard. Khi ghi child, cần cung cấp routing phù hợp với ID của parent để hai document nằm cùng shard.

### 9.1. has_child query

Tìm parent có ít nhất một review với rating từ 4 trở lên:

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

### 9.2. has_parent query

Tìm child review thuộc sản phẩm có SKU KB-1042:

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

Parent/child linh hoạt khi các document có vòng đời độc lập, nhưng join query có chi phí đáng kể. Không dùng join chỉ vì muốn truy vấn một mảng object; nested thường phù hợp hơn khi các phần tử con thuộc cùng một aggregate và được lưu cùng document.

Trong Spring Data Elasticsearch, có thể xây dựng has_child/has_parent bằng NativeQuery nếu phiên bản Elasticsearch Java API Client hỗ trợ các query builder tương ứng. Cần cấu hình join field, routing và mapping chính xác; chỉ khai báo nested annotation sẽ không tạo quan hệ parent/child.

## 10. Geo query

Elasticsearch có query địa lý dành cho field map kiểu geo_point hoặc geo_shape.

### 10.1. Mapping geo_point

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Field(type = FieldType.GeoPoint)
private GeoPoint location;
~~~

Mapping JSON:

~~~json
{
  "properties": {
    "location": {
      "type": "geo_point"
    }
  }
}
~~~

### 10.2. Geo distance query

Tìm địa điểm trong bán kính 5 km từ tọa độ cho trước:

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

### 10.3. Geo bounding box

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

NativeQuery cho phép kết hợp geo query với filter khác, sort theo khoảng cách và pagination. Khi sort theo khoảng cách, hãy xác định rõ thứ tự và cách xử lý document thiếu tọa độ.

## 11. Script query

Script query cho phép kiểm tra điều kiện bằng script Painless. Đây là công cụ linh hoạt nhưng có chi phí cao hơn các query native thông thường và cần giới hạn chặt chẽ.

Ví dụ tìm sản phẩm có giá hiệu dụng sau giảm giá thấp hơn ngưỡng:

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

Khi dùng script query:

- Dùng parameter thay vì nối dữ liệu người dùng vào source script.
- Ưu tiên query/filter native nếu có thể biểu đạt cùng điều kiện.
- Kiểm tra field có doc values phù hợp hay không.
- Đánh giá chi phí script trên dữ liệu và tải thực tế.
- Không cho phép người dùng gửi tùy ý nội dung script.

Spring Data có thể biểu diễn script query qua NativeQuery/Java client DSL. Với script phức tạp hoặc stored script, cân nhắc ScriptOperations để quản lý script có ID thay vì gửi source lặp lại trong mọi request.

## 12. Percolate query: tìm truy vấn khớp với document

Percolator đảo chiều cách tìm kiếm thông thường:

- Search thông thường: có document và tìm document khớp query.
- Percolate: có document đầu vào và tìm các query đã lưu trước đó mà document này khớp.

Ví dụ, hệ thống lưu các điều kiện cảnh báo của người dùng và cần xác định cảnh báo nào phù hợp với sản phẩm vừa được nhập.

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

Lưu một query document:

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

Percolator hữu ích cho cảnh báo, đăng ký tìm kiếm và quy tắc theo dõi. Cần bảo đảm mapping của document được percolate tương thích với mapping mà query đã lưu sử dụng. Số lượng query lưu và độ phức tạp query ảnh hưởng trực tiếp tới hiệu năng.

## 13. More Like This và truy vấn liên quan

More Like This tìm các document tương tự nội dung của document hoặc văn bản được cung cấp. Query thường chỉ định các field có nội dung cần so sánh, số term tối thiểu và các ngưỡng tần suất.

Ví dụ:

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

Query này phù hợp với chức năng gợi ý document tương tự. Kết quả phụ thuộc analyzer, nội dung field, tần suất term và các tham số. Hãy kiểm thử trên dữ liệu thật để tránh kết quả quá rộng hoặc quá hẹp.

## 14. KNN và truy vấn vector

Với hệ thống tìm kiếm ngữ nghĩa, Elasticsearch hỗ trợ vector search qua các field vector và query KNN theo phiên bản/cấu hình phù hợp.

Mapping ví dụ:

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

KNN query minh họa:

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

Trong ứng dụng thực tế, vector query cần khớp số chiều, similarity và cách tạo embedding của model. KNN query và khả năng kết hợp với filter, hybrid search hoặc rescoring phụ thuộc phiên bản Elasticsearch. Hãy dùng NativeQuery/Java API Client đúng phiên bản và đo chất lượng truy hồi trên tập dữ liệu đánh giá.

## 15. Xây dựng truy vấn bằng NativeQuery cho các query đặc thù

NativeQuery được xây dựng trên typed query model của Elasticsearch Java API Client. Cấu trúc chung:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query elasticQuery = Query.of(q -> q
    // Chọn query builder tương ứng: nested, geo, script, percolate...
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(elasticQuery)
    .build();
~~~

Sau đó thực thi:

~~~java
SearchHits<ProductDocument> results =
    operations.search(
        nativeQuery,
        ProductDocument.class,
        IndexCoordinates.of("catalog-products")
    );
~~~

Có thể kết hợp thêm:

- Pageable để phân trang ở cấp parent hits khi query hỗ trợ.
- Sort để sắp xếp kết quả cha.
- Highlight fields để trả highlight cho field phù hợp.
- Aggregations để tổng hợp dữ liệu.
- Source filtering để giới hạn field trả về.
- Track scores hoặc min score khi nghiệp vụ cần relevance.

Với inner hits, phân trang parent hits và phân trang nested hits là hai phạm vi khác nhau. Pageable của query chính không tự động phân trang inner hits; cần cấu hình from/size trong inner hits definition.

### 15.1. Dùng @Query cho query tĩnh

Nếu query JSON cố định, ít tham số và không cần dựng DSL động, repository method có thể dùng @Query:

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

@Query tiện cho query tĩnh. Với nhiều điều kiện tùy chọn, query đặc thù cần typed builder hoặc inner hits cấu hình động, NativeQuery thường dễ bảo trì hơn.

### 15.2. Khi nào cần dùng Elasticsearch Java API Client trực tiếp?

NativeQuery bao phủ nhiều query DSL, nhưng abstraction Spring Data có thể chưa phơi bày mọi request option hoặc API mới của Elasticsearch. Khi cần một API chưa có trong Spring Data:

1. Tạo adapter hạ tầng chuyên trách.
2. Inject Elasticsearch Java API Client được Spring quản lý.
3. Gọi API cụ thể và chuyển response sang kiểu ứng dụng.
4. Giữ mapping, exception handling, timeout và logging nhất quán với phần còn lại.
5. Không để kiểu request/response của client lan rộng vào domain hoặc controller.

Chỉ dùng client cấp thấp khi abstraction hiện tại thực sự thiếu khả năng cần thiết. Nếu query đã được hỗ trợ bởi NativeQuery, dùng ElasticsearchOperations giúp tái sử dụng mapping converter và các quy ước Spring Data.

## 16. Chọn query type phù hợp

| Nhu cầu | Cơ chế nên xem xét |
| --- | --- |
| Tìm kiếm text thông thường | match, multi_match |
| So khớp chính xác | term, terms |
| Lọc số/ngày | range |
| Nhiều điều kiện logic | bool |
| Điều kiện trên cùng phần tử mảng object | nested |
| Trả nested object khớp | nested + inner_hits |
| Quan hệ document cha-con độc lập | has_child, has_parent, join mapping |
| Tìm theo vị trí | geo_distance, geo_bounding_box, geo_shape |
| Tính điều kiện bằng biểu thức | script query |
| Tìm query đã lưu khớp document mới | percolate |
| Tìm document tương tự | more_like_this |
| Tìm kiếm vector | knn hoặc các API vector phù hợp phiên bản |

Không nên chọn query phức tạp chỉ vì có thể dùng. Query native đơn giản thường dễ tối ưu, dễ quan sát và ít tốn tài nguyên hơn. Hãy chọn cơ chế theo mô hình dữ liệu và semantics nghiệp vụ.

## 17. Kiểm tra và debug query

Khi query nested hoặc inner hits không trả kết quả như mong đợi, hãy kiểm tra theo trình tự:

1. Đọc mapping thực tế để xác nhận field là nested và path chính xác.
2. Lấy một document mẫu từ _source để xác nhận cấu trúc mảng.
3. Chạy từng điều kiện bên trong nested query riêng lẻ.
4. Kết hợp điều kiện trong cùng nested bool nếu chúng phải khớp cùng một object.
5. Thêm inner_hits để xem phần tử nào thực sự khớp.
6. Kiểm tra field path, kiểu dữ liệu, analyzer và multi-field.
7. Kiểm tra score_mode nếu kết quả được xếp hạng theo điểm.
8. Dùng profile API khi cần phân tích chi phí thực thi.
9. Giảm inner_hits size và source fields để đánh giá ảnh hưởng response.
10. Benchmark bằng dữ liệu đại diện thay vì chỉ một document nhỏ.

Có thể kiểm tra query DSL bằng Elasticsearch _validate/query hoặc _search trong môi trường phát triển:

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

_validate/query giúp kiểm tra query có hợp lệ và có thể trả lời phần giải thích cách phân tích. Nó không thay thế việc chạy query trên dữ liệu thật để kiểm tra kết quả.

## 18. Hiệu năng và giới hạn vận hành

Nested query có chi phí cao hơn object thông thường vì mỗi nested object được lập chỉ mục như một hidden document. Một parent có nhiều nested element làm tăng số document nội bộ, chi phí merge và lượng dữ liệu cần tìm kiếm.

Một số nguyên tắc:

- Chỉ dùng nested cho quan hệ cần truy vấn theo từng phần tử.
- Hạn chế số nested field và số nested object trong một parent.
- Đặt inner_hits size nhỏ và chỉ trả field cần thiết.
- Không dùng script query nếu native query biểu đạt được cùng điều kiện.
- Với parent/child, cân nhắc chi phí join và routing.
- Với geo hoặc vector query, benchmark theo dữ liệu, shard topology và concurrency thật.
- Theo dõi query latency, heap, CPU, segment count và response size.
- Đặt giới hạn đầu vào cho số điều kiện, khoảng cách, kích thước inner hits và số trang.

Nested mapping cũng có các giới hạn cấu hình của Elasticsearch, chẳng hạn số nested field và số nested object trong một document. Giá trị cụ thể phụ thuộc phiên bản và index settings. Nếu dữ liệu có hàng nghìn phần tử con lớn trong một parent, nên đánh giá lại mô hình document thay vì mặc định dùng nested.

## 19. Lỗi thường gặp

**Dùng object cho mảng cần giữ quan hệ giữa các field.** Query có thể ghép nhầm giá trị từ hai phần tử khác nhau. Dùng nested mapping khi cần cùng-object matching.

**Viết nested query nhưng field chỉ là object.** Elasticsearch không thể thực thi nested query trên field không có mapping nested. Tạo index mới và reindex nếu cần đổi kiểu.

**Tách các điều kiện cùng phần tử thành nhiều nested query độc lập.** Các điều kiện có thể khớp trên những nested object khác nhau. Gom chúng vào một nested bool query.

**Nghĩ nested query trả trực tiếp nested object.** Kết quả chính vẫn là parent document. Dùng inner_hits để lấy nested object khớp.

**Quên đặt tên inner hits khi có nhiều nhóm.** Đặt name riêng để đọc đúng nhóm trong SearchHit.

**Để inner_hits trả quá nhiều dữ liệu.** Giới hạn size, sort và source fields.

**Dùng CriteriaQuery cho query DSL rất đặc thù dù abstraction không biểu đạt đủ.** Chọn NativeQuery để dùng typed query builder của Elasticsearch Java API Client.

**Nối chuỗi input vào script hoặc query JSON.** Dùng parameter binding và validation để tránh query injection hoặc script không an toàn.

**Dùng parent/child cho dữ liệu vốn là một mảng con đơn giản.** Nested thường hiệu quả và tự nhiên hơn nếu các phần tử cùng vòng đời với parent.

**Ép kiểu inner hit thành domain object mà không kiểm tra.** Kiểu content phụ thuộc mapping và phiên bản; kiểm tra response, rồi chuyển sang DTO có chủ đích.

## 20. Quy trình thiết kế và triển khai

Khi xây dựng một truy vấn đặc thù cho ứng dụng Spring Data Elasticsearch:

1. Xác định quan hệ dữ liệu: object độc lập, mảng nested hay parent/child.
2. Thiết kế mapping trước khi viết query; xác nhận nested path và field type.
3. Viết query DSL nhỏ nhất để kiểm tra semantics trên document mẫu.
4. Nếu cần trả phần tử con khớp, thêm inner_hits với name, size, sort và source filtering.
5. Chọn CriteriaQuery cho điều kiện thông thường hoặc NativeQuery cho query DSL nâng cao.
6. Dùng ElasticsearchOperations.search(...) để thực thi và nhận SearchHits.
7. Đọc inner hits theo tên và chuyển sang DTO phù hợp.
8. Với truy vấn đặc thù khác, chọn geo, script, percolate, parent/child, more_like_this hoặc vector query theo đúng mô hình dữ liệu.
9. Kiểm tra mapping, query validity, kết quả và chi phí bằng dữ liệu đại diện.
10. Đưa query phức tạp vào adapter hạ tầng, giới hạn input và theo dõi hiệu năng trong môi trường chạy thật.

Nested query giải quyết bài toán quan hệ giữa các field trong cùng một phần tử object; inner_hits trả lại chính các phần tử đã khớp; NativeQuery mở ra khả năng dùng các query DSL chuyên biệt của Elasticsearch trong ứng dụng Spring Data. Chọn đúng mapping và semantics trước khi tối ưu query sẽ giúp kết quả tìm kiếm chính xác và dễ bảo trì hơn.

## 21. Tài liệu tham khảo

- [Elasticsearch - Nested field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/nested): cách lưu nested documents và giới hạn của nested mapping.
- [Elasticsearch - Nested query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-nested-query): cú pháp nested query, score mode và inner hits.
- [Elasticsearch - Retrieve inner hits](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrieve-inner-hits): cách lấy nested/child hit trong kết quả.
- [Elasticsearch - Joining queries](https://www.elastic.co/docs/reference/query-languages/query-dsl/joining-queries): nested, has_child và has_parent.
- [Spring Data Elasticsearch - Query and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): xây dựng và thực thi query qua Spring Data.
- [Elasticsearch Java API Client - Query DSL](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/searching): typed query builder và cách thực thi search bằng Java client.

API builder và kiểu kết quả có thể thay đổi theo phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client. Hãy đối chiếu dependency thực tế của dự án khi triển khai các ví dụ NativeQuery.
