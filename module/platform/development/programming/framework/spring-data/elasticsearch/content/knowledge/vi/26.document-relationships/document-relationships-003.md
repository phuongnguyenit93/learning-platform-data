# Nested query, score mode và inner hits

Khi một document chứa mảng object, ứng dụng đôi khi cần kiểm tra nhiều điều kiện trên cùng một phần tử. Ví dụ sản phẩm có nhiều offer từ các nhà bán khác nhau; truy vấn cần tìm sản phẩm có offer của SELLER-A với giá dưới 100 và đang còn hàng. Nếu mapping và query không giữ đúng quan hệ giữa các field trong từng phần tử, Elasticsearch có thể ghép điều kiện từ hai offer khác nhau rồi trả về sản phẩm không đúng.

`nested` là cơ chế để lập chỉ mục và truy vấn object con như những document lồng nhau, giữ quan hệ giữa các field trong cùng phần tử. `nested query` tìm document cha có ít nhất một nested document khớp. `score_mode` quyết định cách score của những nested document khớp được gộp thành score document cha. `inner_hits` cho phép lấy lại chính nested document đã khớp để ứng dụng hiển thị hoặc xử lý.

Ba khái niệm này giải quyết ba vấn đề liên quan nhưng khác nhau: giữ quan hệ dữ liệu, tổng hợp điểm xếp hạng và trả về phần tử con phù hợp.

## 1. Vì sao cần Nested mapping?

### 1.1. Mảng object thông thường có thể làm mất quan hệ giữa field

Giả sử một sản phẩm có hai offer:

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

Nghiệp vụ cần tìm sản phẩm có offer của SELLER-A, giá không quá 100 và còn hàng. Không có offer nào trong ví dụ đáp ứng cả ba điều kiện:

- Offer của SELLER-A có giá 150.
- Offer giá 80 thuộc SELLER-B và không còn hàng.

Nếu `offers` được mapping thành `object` thông thường, Elasticsearch flatten các giá trị của object array thành các field đa trị. Quan hệ giữa các giá trị của từng object không còn được giữ theo cách cần thiết cho truy vấn cùng phần tử.

Khi đó, bool query có thể thấy seller = SELLER-A, price <= 100 và available = true đều xuất hiện đâu đó trong document rồi trả về sản phẩm. Đây là false positive vì các điều kiện thực tế thuộc những phần tử khác nhau.

### 1.2. Nested tạo document Lucene riêng cho từng object con

Khi field được mapping là `nested`, mỗi object trong mảng được lập chỉ mục như một nested document riêng, liên kết với document cha.

| Nested offer | Seller | Price | Available |
|---|---|---:|---|
| Offer 1 | SELLER-A | 150 | true |
| Offer 2 | SELLER-B | 80 | false |

Một nested query có thể yêu cầu tất cả điều kiện cùng khớp trên một nested document. Do không có offer nào khớp đủ điều kiện, sản phẩm P1001 sẽ không được trả về.

Nested document không phải document độc lập mà ứng dụng có thể cập nhật riêng như root document. Chúng được lưu và truy vấn trong quan hệ với document cha.

### 1.3. Khi nào dùng object và khi nào dùng nested?

| Nhu cầu | Mapping phù hợp |
|---|---|
| Lưu field con nhưng không cần giữ quan hệ giữa từng phần tử array | `object` |
| Cần nhiều điều kiện cùng khớp trên một object trong array | `nested` |
| Cần query và lấy riêng object con đã khớp | `nested` kết hợp `inner_hits` |
| Dữ liệu con có vòng đời, cập nhật và truy vấn độc lập | Cân nhắc index riêng hoặc parent-child |

Nested có chi phí cao hơn object thông thường vì mỗi nested object tạo thêm một Lucene document ẩn. Không nên chuyển mọi object array thành nested nếu ứng dụng không cần semantics này.

## 2. Khai báo Nested mapping trong Spring Data Elasticsearch

### 2.1. Model Java

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

Điểm quan trọng là field offers được khai báo với `FieldType.Nested`. Nếu dùng `FieldType.Object`, Spring Data sẽ tạo mapping object thông thường và query không có semantics nested.

Tên annotation, package và cách khai báo field có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy xác nhận API của dependency đang sử dụng.

### 2.2. Mapping JSON tương ứng

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

Nested path là `offers`. Các field bên trong nested object được tham chiếu bằng đường dẫn như `offers.seller`, `offers.price` và `offers.available`.

Mapping cần được tạo đúng trước khi index dữ liệu. Nếu field đã được tạo thành object, không thể chỉ đổi annotation Java rồi kỳ vọng mapping hiện tại tự chuyển thành nested. Thông thường cần tạo index mới với mapping đúng và reindex dữ liệu.

### 2.3. Kiểm tra mapping thực tế

Có thể dùng mapping API:

~~~http
GET /products/_mapping
~~~

Tìm field offers và kiểm tra type là nested. Đừng chỉ dựa vào Java entity vì index có thể đã tồn tại với mapping cũ hoặc được tạo bởi pipeline khác.

Khi ứng dụng chạy qua alias nhiều index, hãy bảo đảm các index có mapping tương thích. Nếu một index khai báo offers là object còn index khác là nested, cùng một query có thể lỗi hoặc cho kết quả không nhất quán.

## 3. Nested query cơ bản

### 3.1. Cấu trúc query

Nested query có các thành phần chính:

- `path`: đường dẫn tới nested field.
- `query`: query chạy trên nested document.
- `score_mode`: cách gộp score của nested documents khớp.
- `inner_hits`: tùy chọn lấy nested documents khớp trong response.

Ví dụ tìm sản phẩm có offer từ Seller A:

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

`path` phải trỏ tới field được mapping là nested. Field trong query vẫn dùng đường dẫn đầy đủ, chẳng hạn offers.seller.

Nested query trả về document cha nếu có ít nhất một nested document khớp. Nó không tự biến nested document thành root hit.

### 3.2. Kết hợp nhiều điều kiện trên cùng nested object

Query đầy đủ cho ví dụ offer:

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

Các điều kiện seller, price và available nằm bên trong cùng một nested query. Elasticsearch đánh giá bool query trên từng nested document, nên tất cả điều kiện phải khớp trên cùng một offer.

### 3.3. Sai lầm: chia điều kiện thành các nested query riêng

Ví dụ sau có thể trả sản phẩm nếu có một nested object thỏa seller và một nested object khác thỏa price:

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

Mỗi nested query độc lập chỉ cần tìm được một nested document khớp. Hai nested query có thể khớp hai offer khác nhau.

Nếu nghiệp vụ yêu cầu cùng một offer phải thuộc Seller A và có giá không quá 100, hãy đặt cả hai điều kiện trong một nested query và cùng một bool bên trong.

### 3.4. Kết hợp điều kiện root và nested

Có thể kết hợp điều kiện ở document cha với nested query:

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

Tên sản phẩm được tìm trên root document, điều kiện seller/price được kiểm tra trên một nested offer, còn active là điều kiện filter của document cha.

### 3.5. Nested path nhiều cấp

Nếu một nested object lại chứa nested array, query phải dùng đúng nested path đầy đủ. Ví dụ orders.items hoặc comments.replies, tùy mapping.

Elasticsearch hỗ trợ nested query nhiều cấp và có thể xác định nested context theo cấu trúc query. Tuy nhiên, khai báo path rõ ràng giúp code dễ đọc và giảm nhầm lẫn khi có nhiều cấp nested.

## 4. Bool logic bên trong Nested query

### 4.1. must, filter, should và must_not

Nested query nhận các query clause thông thường:

- `must`: nested document bắt buộc khớp và tham gia scoring.
- `filter`: nested document phải thỏa điều kiện nhưng không đóng góp relevance score.
- `should`: nested document được tăng điểm hoặc phải khớp tùy `minimum_should_match`.
- `must_not`: loại nested document thỏa điều kiện.

Ví dụ Seller A phải còn hàng, nhưng ưu tiên offer giá thấp:

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

Điều kiện seller và available lọc candidate nested document. should có thể đóng góp score nếu query chạy trong scoring context. Nếu muốn giá bắt buộc không vượt 100, hãy chuyển range vào filter hoặc must.

### 4.2. minimum_should_match

Khi bool query có must hoặc filter, các clause should thường không bắt buộc theo mặc định. Nếu không có must/filter, should thường phải khớp ít nhất một clause.

Hãy đặt minimum_should_match tường minh khi nghiệp vụ phụ thuộc số lượng điều kiện should cần thỏa. Điều này tránh query thay đổi ý nghĩa khi thêm hoặc bớt clause.

### 4.3. must_not và ý nghĩa phủ định

Nếu cần tìm sản phẩm không có offer từ Seller A, có thể đặt nested query trong must_not ở cấp root:

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

Query này loại document cha nếu tồn tại ít nhất một nested offer của Seller A.

Phủ định bên trong nested query có ý nghĩa khác. Nested query với must_not seller=A có thể khớp một offer khác seller A ngay cả khi sản phẩm vẫn có một offer Seller A. Nếu muốn “không tồn tại bất kỳ offer Seller A nào”, đặt nested query dương bên trong root-level must_not.

## 5. Score mode trong Nested query

### 5.1. Vì sao cần score_mode?

Một document cha có thể có nhiều nested document cùng khớp. Mỗi nested document có thể tạo ra một score riêng. Elasticsearch cần một quy tắc để kết hợp những score đó thành score của document cha.

`score_mode` xác định cách gộp score của các nested document khớp:

| score_mode | Cách gộp |
|---|---|
| `avg` | Trung bình score của các nested document khớp |
| `max` | Lấy score lớn nhất |
| `min` | Lấy score nhỏ nhất |
| `sum` | Cộng score của các nested document khớp |
| `none` | Không đưa score của nested document vào score cha |

Nếu không khai báo, nested query thường dùng avg. Hãy kiểm tra tài liệu của phiên bản Elasticsearch đang chạy nếu dựa vào default trong hợp đồng ranking.

### 5.2. avg: điểm trung bình

avg lấy trung bình score của các nested document khớp.

Ví dụ một sản phẩm có ba offer khớp với score 2, 4 và 6:

\[
parentScore = \frac{2 + 4 + 6}{3} = 4
\]

Chế độ này giảm ảnh hưởng của số lượng nested document khớp. Một sản phẩm có nhiều offer không tự động nhận tổng score cao chỉ vì có nhiều offer.

### 5.3. max: lấy nested match tốt nhất

max chọn score cao nhất trong các nested document khớp. Với score 2, 4 và 6, parent score là 6.

Chế độ này phù hợp khi chỉ cần một nested item tốt nhất quyết định mức liên quan của document cha. Ví dụ sản phẩm có một offer rất phù hợp có thể được xếp hạng cao dù các offer còn lại không tốt.

### 5.4. min: lấy nested score thấp nhất

min chọn score nhỏ nhất trong các nested document khớp. Với score 2, 4 và 6, parent score là 2.

Đây là lựa chọn ít phổ biến hơn trong ranking thông thường, nhưng có thể phù hợp khi nghiệp vụ muốn đánh giá document cha dựa trên nested match có điểm thấp nhất trong nhóm match.

### 5.5. sum: cộng điểm các nested match

sum cộng score của tất cả nested document khớp. Với score 2, 4 và 6, parent score là 12.

Chế độ này làm số lượng nested match có thể ảnh hưởng mạnh đến thứ tự. Sản phẩm có nhiều offer khớp có thể nhận điểm cao hơn sản phẩm chỉ có một offer, ngay cả khi score từng offer tương đương.

Chỉ dùng sum khi số lượng nested match thực sự là tín hiệu nghiệp vụ mong muốn. Nếu không, một document có nhiều phần tử lặp có thể được boost ngoài ý muốn.

### 5.6. none: không dùng nested score

none không đưa score của nested document vào score của document cha. Chế độ này phù hợp khi nested query chỉ cần xác định document cha có thỏa điều kiện hay không, không cần nested relevance ảnh hưởng đến ranking.

Nếu nested query nằm trong bool filter, score vốn không được dùng để xếp hạng, nên score_mode thường không tạo khác biệt hữu ích cho kết quả cuối. Có thể đặt none để thể hiện ý định rõ ràng.

### 5.7. Minh họa các score mode

Giả sử ba nested document khớp có score 2, 4, 6:

| Mode | Score cha |
|---|---:|
| avg | 4 |
| max | 6 |
| min | 2 |
| sum | 12 |
| none | Không sử dụng nested score |

Đây là phép minh họa đơn giản. Score thực tế của Elasticsearch phụ thuộc query, similarity và các yếu tố scoring khác.

### 5.8. Khai báo score_mode trong DSL

Ví dụ ưu tiên nested offer có score cao nhất:

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

Query này tìm sản phẩm có offer của Seller A với mô tả phù hợp. Nếu có nhiều offer khớp, score của offer tốt nhất được dùng làm score của sản phẩm.

### 5.9. score_mode và boost của query cha

Score mode chỉ xác định cách gộp điểm từ nested matches. Score cuối của document cha còn có thể chịu ảnh hưởng bởi các clause khác trong bool query, boost của query và scoring function ở tầng ngoài.

Đừng coi score_mode max là score cuối cùng của toàn bộ search response. Nó chỉ điều khiển phần đóng góp của nested query.

## 6. Scoring context và filter context

### 6.1. Nested query trong must

Nếu nested query nằm trong must hoặc scoring clause phù hợp, nested score có thể đóng góp vào score của document cha.

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

Score của nested match tốt nhất ảnh hưởng đến thứ tự sản phẩm.

### 6.2. Nested query trong filter

Nếu chỉ cần kiểm tra tồn tại offer phù hợp:

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

Filter context không tính relevance score cho điều kiện đó. Đây thường là lựa chọn tốt khi nested query chỉ là điều kiện nghiệp vụ.

### 6.3. Tách điều kiện lọc và điều kiện xếp hạng

Có thể dùng nested filter để đảm bảo có offer còn hàng, và nested scoring query riêng để xếp hạng theo mô tả offer:

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

Cần chú ý rằng hai nested query này có thể khớp hai offer khác nhau. Nếu yêu cầu cùng một offer vừa available vừa có mô tả phù hợp, hãy đặt cả hai điều kiện trong cùng một nested query. Chỉ tách thành hai query khi nghiệp vụ cho phép hai nested item khác nhau.

## 7. Inner hits: lấy nested document đã khớp

### 7.1. Nested query chỉ trả document cha

Một nested query thông thường trả root document phù hợp. Phần offers trong _source vẫn có thể chứa toàn bộ offer của sản phẩm, kể cả những offer không khớp điều kiện nested query.

Nếu giao diện cần hiển thị chính xác offer nào làm sản phẩm được chọn, cần dùng inner_hits.

### 7.2. Cấu trúc inner_hits

Có thể thêm inner_hits vào nested query:

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

Elasticsearch trả document cha trong hits.hits và nhóm nested matches trong inner_hits của từng parent hit. Tên matching_offers giúp phân biệt khi query có nhiều inner-hit definition.

Inner hits chỉ chứa nested document khớp nested query tương ứng, không phải toàn bộ nested array.

### 7.3. Response có inner hits

Response khái niệm:

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

Đây là cấu trúc minh họa. Giá trị offset và source phải tương ứng với dữ liệu thực tế. Điểm cần nhớ là root _source có thể chứa toàn bộ mảng, còn inner hits cung cấp riêng nested item đã khớp.

### 7.4. Inner hit không tạo document ID độc lập

Nested object không có _id độc lập như root document. Elasticsearch dùng metadata nested, chẳng hạn field path và offset trong mảng, để chỉ vị trí nested object trong parent.

Offset có thể thay đổi nếu mảng được cập nhật hoặc sắp xếp lại. Nếu ứng dụng cần định danh ổn định cho offer, hãy lưu một business key như offerId bên trong nested object và trả field đó qua inner hits.

Không dùng offset làm ID lâu dài hoặc khóa nghiệp vụ.

### 7.5. Inner hits có giới hạn mặc định

Inner hits có giới hạn số nested document được trả cho mỗi parent. Nếu không cấu hình, mặc định thường chỉ trả một số lượng nhỏ (thường là 3) nested hit. Hãy khai báo size rõ ràng theo nhu cầu UI và kiểm tra mặc định của phiên bản Elasticsearch.

Một query trả 20 parent hit và mỗi parent lấy 100 inner hits có thể tạo ra hàng nghìn nested items trong response. Giới hạn số parent hits, inner hit size và field trả về.

## 8. Tùy chỉnh inner_hits

### 8.1. Sắp xếp nested matches

Có thể sort inner hits độc lập:

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

Trong ví dụ, offer khớp được sắp xếp theo giá tăng dần. Sort trong inner hits chỉ sắp xếp nested results bên trong mỗi parent. Nó không tự sắp xếp parent products.

### 8.2. Phân trang inner hits

Inner hits hỗ trợ from và size để lấy một phần nested matches của từng parent:

~~~json
{
  "inner_hits": {
    "name": "matching_offers",
    "from": 0,
    "size": 10
  }
}
~~~

Các tùy chọn này áp dụng cho inner hits của mỗi parent hit, nên tổng số phần tử response có thể tăng nhanh khi nhiều parent được trả về.

Elasticsearch có giới hạn `index.max_inner_result_window` cho cửa sổ inner result. Hãy kiểm tra cấu hình cluster và tránh tăng giới hạn chỉ để trả về một lượng nested data quá lớn.

### 8.3. Chỉ lấy field cần thiết

Có thể giới hạn source của inner hits:

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

Tùy phiên bản và ngữ cảnh nested, phần _source của inner hit có thể được biểu diễn dưới dạng fragment của nested object. Hãy xác nhận response thực tế và mapping converter trước khi ánh xạ DTO.

Nếu chỉ cần một số scalar field, có thể cân nhắc docvalue_fields cho field hỗ trợ doc values. Source filtering và doc values có semantics khác nhau; chọn theo kiểu dữ liệu và cách ứng dụng sử dụng kết quả.

### 8.4. Highlight inner hits

Inner hits có thể yêu cầu highlight cho field nested:

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

Điều này hữu ích khi tìm sản phẩm dựa trên mô tả offer và muốn hiển thị đoạn mô tả khớp. Highlight fragment vẫn là dữ liệu không tin cậy; phải xử lý an toàn trước khi render ở trình duyệt.

### 8.5. Explanation và metadata bổ sung

Inner hits có thể cấu hình thêm thông tin như explain, version, seq_no_primary_term và các tùy chọn field phù hợp. Chỉ bật khi use case cần.

Explanation có thể làm response lớn và tăng chi phí. Không nên bật trên endpoint tìm kiếm công khai chỉ để debug tạm thời.

## 9. Nhiều nested query và nhiều inner hits

### 9.1. Mỗi nested query có thể có tên inner hits riêng

Một sản phẩm có thể có nested offers và reviews. Có thể truy vấn hai nhóm nested khác nhau:

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

Mỗi parent hit có thể chứa hai nhóm inner hits với tên khác nhau. Tên giúp ứng dụng biết nhóm nào đến từ nested query nào.

Tên inner hits cần duy nhất trong phạm vi search request nếu các definition có thể xung đột. Không dùng tên động tùy ý từ client.

### 9.2. Nested trong nested

Với mapping có nested object lồng nhau, có thể đặt nested query theo path cấp sâu và yêu cầu inner hits ở cấp tương ứng. Kết quả có thể có inner hits lồng nhau theo cấu trúc query.

Cần kiểm tra kỹ path và cách response được ánh xạ. Nếu ứng dụng chỉ cần một cấp con, tránh lấy cả cây nested sâu vì response và chi phí xử lý sẽ tăng.

### 9.3. Inner hits không thay thế nested aggregation

inner_hits phục vụ việc lấy nested documents khớp cho từng parent hit. Nested aggregation phục vụ thống kê/tổng hợp trên nested documents trong tập dữ liệu.

Ví dụ:

- inner_hits: hiển thị 3 offer phù hợp trong từng sản phẩm.
- nested aggregation: tính phân phối giá của tất cả offer thuộc các sản phẩm đã lọc.
- reverse_nested aggregation: từ nested bucket quay lại ngữ cảnh parent để đếm sản phẩm cha.

Chọn API theo mục đích hiển thị từng item hay tính thống kê tổng hợp.

## 10. Nested query và Spring Data Elasticsearch

### 10.1. Dùng StringQuery cho DSL có inner_hits

Khi query có cấu trúc nested phức tạp, có thể biểu diễn query clause bằng StringQuery:

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

StringQuery nhận query DSL clause trong Spring Data abstraction, không phải toàn bộ search request body có trường query bên ngoài. Các tùy chọn như pageable có thể được gắn riêng vào Query.

### 10.2. Dùng NativeQuery

NativeQuery cho phép xây dựng DSL bằng Elasticsearch Java API Client và phù hợp khi cần type-safe builder. Cấu trúc logic vẫn giống nhau:

- Tạo nested query với path.
- Đặt bool query bên trong.
- Khai báo score_mode.
- Đính kèm inner_hits với tên và giới hạn cần thiết.

Chữ ký builder cho nested query và inner hits phụ thuộc phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client. Hãy dùng API đúng phiên bản trong dependency của dự án; không sao chép nguyên overload từ một bản client khác.

### 10.3. Đọc inner hits từ SearchHit

Spring Data Elasticsearch giữ inner hits trong metadata của parent SearchHit. Với các phiên bản hỗ trợ API này, có thể truy cập theo tên:

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
            // Chuyển nested content sang DTO theo kiểu mapping thực tế.
        }
    }
}
~~~

Kiểu dữ liệu và cách converter tạo content cho inner hit có thể phụ thuộc phiên bản và cách khai báo entity. Có thể cần kiểm tra getContent() là kiểu nested object nào hoặc ánh xạ qua cấu trúc trung gian. Không ép kiểu mù sang một class khi chưa xác minh response.

### 10.4. Tạo DTO cho nested match

Ví dụ DTO:

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

Mapper lấy parent content từ SearchHit<ProductDocument> và inner hits từ key matching_offers. Chỉ đưa các offer đã khớp vào matchingOffers.

Nếu nested object không có business ID, cân nhắc bổ sung offerId. Không dùng offset của nested array làm định danh lâu dài.

### 10.5. Phân biệt source nested array với inner hits

Parent entity có thể chứa toàn bộ offers trong _source, còn inner hits chỉ chứa các offer khớp query. Nếu mapper lấy product.getOffers() thay cho inner hits, API có thể trả cả offer không thỏa điều kiện.

Khi UI cần “những offer đã khớp”, hãy dùng inner hits. Khi UI cần toàn bộ offer của sản phẩm, đó là use case khác và nên được thể hiện rõ trong response contract.

## 11. Sort parent theo nested field

### 11.1. Sort inner hits không sort parent

Cấu hình inner_hits.sort chỉ quyết định thứ tự các nested document được trả trong mỗi parent hit. Nó không quyết định thứ tự danh sách parent products.

Nếu cần sắp xếp sản phẩm theo giá offer thấp nhất, phải dùng nested sort ở cấp root sort:

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

Nested sort có path và có thể có filter để chỉ xét những nested object phù hợp. mode ở đây là cách chọn giá trị sort từ nhiều nested values, ví dụ min hoặc max. Nó khác với score_mode của nested query.

### 11.2. Phân biệt score_mode và nested sort mode

| Thuộc tính | Mục đích |
|---|---|
| score_mode | Gộp score của nested query thành score parent |
| Nested sort mode | Chọn giá trị nested field dùng để sort parent |
| inner_hits.sort | Sắp xếp nested hits trả về bên trong mỗi parent |

Ba cơ chế này độc lập. Parent products có thể được xếp theo giá offer thấp nhất, inner hits của mỗi sản phẩm được sắp xếp theo giá tăng dần và score_mode được dùng cho relevance query.

### 11.3. Đồng bộ filter giữa query và sort

Nếu nested query chỉ xét offer còn hàng nhưng nested sort lại xét mọi offer, parent có thể được sắp theo giá của offer không còn hàng. Hãy dùng nested sort filter tương ứng với điều kiện nghiệp vụ.

Không giả định nested sort tự kế thừa filter từ nested query ở nơi khác trong request.

## 12. Nested mapping và giới hạn tài nguyên

### 12.1. Nested object làm tăng số Lucene documents

Một root document có 1.000 nested objects tạo thêm nhiều Lucene documents ẩn. Điều này ảnh hưởng:

- Số lượng document nội bộ trong index.
- Kích thước index.
- Chi phí indexing và cập nhật.
- Chi phí nested query và aggregation.
- Bộ nhớ và công việc của search.

Nếu mỗi root document có hàng nghìn hoặc hàng chục nghìn nested items, hãy đánh giá lại mô hình dữ liệu. Có thể phù hợp hơn khi tách nested entities thành index riêng hoặc dùng parent-child trong trường hợp phù hợp.

### 12.2. Giới hạn nested fields và nested objects

Elasticsearch có các index setting để giới hạn số nested field mapping và số nested objects trong một document. Các tên setting thường gặp gồm:

- `index.mapping.nested_fields.limit`
- `index.mapping.nested_objects.limit`

Giá trị mặc định và cách áp dụng có thể khác theo phiên bản. Hãy kiểm tra cluster hiện tại trước khi thiết kế schema hoặc thay đổi giới hạn.

Tăng giới hạn không miễn phí. Nếu dữ liệu tạo quá nhiều nested objects, việc tăng setting có thể làm tăng tải index và search.

### 12.3. Cập nhật nested object

Nested objects thuộc cùng root document. Khi cập nhật một phần nested array, Elasticsearch thường phải lập chỉ mục lại root document và các nested documents liên quan.

Nếu nested child có tần suất cập nhật cao hoặc cần lifecycle độc lập, mô hình nested có thể không phù hợp. Hãy cân nhắc index riêng và join/application-level query tùy yêu cầu.

### 12.4. Giới hạn inner result window

`index.max_inner_result_window` giới hạn cửa sổ from + size cho inner hits và một số cấu trúc liên quan. Giá trị mặc định thường khá thấp để ngăn response quá lớn.

Hãy đặt inner_hits.size vừa đủ cho UI. Nếu cần xem toàn bộ nested children, dùng endpoint chi tiết hoặc query riêng có phân trang phù hợp thay vì tăng inner result window không giới hạn.

## 13. Những tình huống cần lưu ý

### 13.1. Field không tồn tại hoặc mapping không đồng nhất

Nếu query nhiều index và một số index không có nested path tương ứng, nested query có thể báo lỗi. Có thể dùng ignore_unmapped: true trong trường hợp nghiệp vụ cho phép coi index không có path đó là không có match.

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

Không dùng ignore_unmapped để che một mapping sai trên index đáng lẽ phải có field. Hãy đồng bộ mapping nếu đó là yêu cầu schema.

### 13.2. Nested query không khớp vì sai path

path phải là nested field path, không phải tên property Java tùy ý. Kiểm tra mapping và tên field thực tế, đặc biệt khi entity dùng @Field(name = "...").

### 13.3. Nested query trả parent nhưng inner hits rỗng

Có thể do:

- Inner hits được đặt ở nested query khác với query đã khớp.
- Tên inner hits trong mapper không đúng.
- Response không chứa inner hits vì request DSL chưa gắn đúng vị trí.
- API client/converter không giữ metadata như dự kiến.
- Query trả parent qua một nhánh bool khác.

Hãy kiểm tra raw response của Elasticsearch và cấu trúc query cuối cùng.

### 13.4. score_mode không thay đổi thứ tự

Một số nguyên nhân:

- Nested query nằm trong filter context.
- Inner query không tạo score khác nhau.
- Mọi nested match có cùng score.
- Root query có các clause khác chi phối score.
- Request sort theo field thay vì _score.

score_mode chỉ ảnh hưởng phần score đến từ nested query. Kiểm tra scoring context và sort của request trước khi kết luận cấu hình không hoạt động.

### 13.5. Parent xuất hiện dù nested item không được UI mong đợi

Có thể nested query được đặt thành nhiều nhánh riêng, mỗi nhánh khớp một nested object khác nhau. Đặt các điều kiện cần cùng một phần tử trong cùng một nested bool query.

### 13.6. Inner hits response quá lớn

Có thể nhiều parent hits, mỗi parent lại có nhiều inner hits và nhiều field source. Giảm root page size, inner hit size, số field và số fragment. Nếu UI cần tất cả children, tách sang endpoint riêng.

## 14. Bảo mật và phân quyền

### 14.1. Áp dụng quyền ở nested query

Nếu nested object có thông tin nhạy cảm theo tenant hoặc user, phải đặt điều kiện phân quyền trong query ở server. Không chỉ trả toàn bộ nested items rồi lọc bằng Java hoặc frontend.

Ví dụ, nested offers thuộc một tenant:

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

Tenant ID phải được lấy từ security context đáng tin cậy ở server, không nhận giá trị tùy ý từ client nếu nó xác định phạm vi truy cập.

### 14.2. Inner hits cũng là dữ liệu cần bảo vệ

Inner hits có thể chứa field không xuất hiện trong DTO root. Hãy áp dụng source filtering và DTO mapping để chỉ trả field được phép.

Không expose toàn bộ inner hit source hoặc explanation trong endpoint công khai nếu chúng chứa thông tin nội bộ.

### 14.3. Giới hạn query do client điều khiển

Không cho client tự gửi nested path, tên inner hit, field sort hoặc DSL tùy ý. Server nên chọn path và field từ cấu hình đã kiểm soát, còn client chỉ cung cấp các tham số nghiệp vụ được validate.

## 15. Kiểm thử Nested query, score mode và inner hits

### 15.1. Test mapping

Tạo index trong test và xác nhận:

- offers có type nested.
- seller là keyword.
- price là numeric.
- available là boolean.
- Nested path và tên field khớp entity.

Không chỉ kiểm tra annotation Java; cần kiểm tra mapping thực tế trên Elasticsearch test instance.

### 15.2. Test false positive của object array

Tạo dữ liệu hai offer:

- Offer A: seller A, price 150, available true.
- Offer B: seller B, price 80, available false.

Query yêu cầu seller A, price <= 100 và available true phải không trả sản phẩm.

Sau đó thêm Offer C có seller A, price 90, available true. Query mới phải trả sản phẩm và inner hits phải chứa Offer C.

Test này xác nhận các điều kiện thật sự khớp trên cùng một nested object.

### 15.3. Test từng score mode

Tạo parent có nhiều nested documents khớp với score có thể phân biệt được. Kiểm tra:

- avg dùng trung bình score.
- max chọn score lớn nhất.
- min chọn score nhỏ nhất.
- sum cộng score.
- none không đưa nested score vào parent score.

Score cụ thể phụ thuộc analyzer và similarity, nên integration test nên so sánh quan hệ thứ tự hoặc dùng query scoring có kết quả ổn định. Không hardcode score tuyệt đối nếu môi trường có thể thay đổi similarity hoặc dữ liệu thống kê.

### 15.4. Test inner hits

Kiểm tra:

- Inner hit chỉ chứa nested items khớp.
- Tên inner hits đúng.
- Size được áp dụng.
- Sort inner hits đúng.
- Source filtering không trả field ngoài yêu cầu.
- Highlight inner hit có mặt khi được yêu cầu.
- Nhiều nested query có nhiều inner hit group riêng.
- Parent source vẫn có thể chứa toàn bộ nested array.

### 15.5. Test nested sort riêng biệt

Nếu parent được sort theo giá nested nhỏ nhất, hãy tạo sản phẩm có nhiều offer và xác nhận:

- Parent order dựa trên nested sort mode.
- Inner hit order dựa trên inner_hits.sort.
- Filter trong nested sort loại offer không phù hợp.
- Kết quả không phụ thuộc thứ tự phần tử trong source array.

### 15.6. Test hiệu năng và giới hạn

Dùng dữ liệu gần quy mô production để đo:

- Số nested objects trên mỗi parent.
- Số parent hits.
- Inner hits size.
- Response size.
- Search latency và heap.
- Số nested field mapping.
- Hành vi khi vượt inner result window.

Không tăng limit để làm test qua nếu query đang trả quá nhiều nested items. Hãy xác định đúng số lượng UI cần.

## 16. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Kết quả có seller đúng nhưng giá từ offer khác | Field array được mapping object, hoặc query chia điều kiện nested riêng | Mapping nested và đặt điều kiện trong cùng một nested query |
| Query nested không chạy | Path không tồn tại hoặc field không phải nested | Kiểm tra mapping thực tế |
| Đổi annotation nhưng query vẫn sai | Index cũ vẫn có object mapping | Tạo index mới và reindex |
| Parent score không như mong đợi | Chọn score_mode không phù hợp hoặc query ở filter context | Kiểm tra scoring context và nested matches |
| Sản phẩm có nhiều offer được boost quá mạnh | Dùng sum trong khi không muốn số lượng match ảnh hưởng | Dùng avg/max hoặc điều chỉnh ranking |
| Inner hits không xuất hiện | Thiếu inner_hits hoặc đặt sai nested query | Kiểm tra request DSL và raw response |
| Inner hits chỉ có vài phần tử | Inner hit size mặc định/đang bị giới hạn | Khai báo size theo nhu cầu |
| Inner hit order khác parent order | Nhầm inner_hits.sort với root nested sort | Cấu hình riêng hai loại sort |
| Parent có đủ source nhưng UI hiển thị offer sai | Mapper dùng toàn bộ source array thay vì inner hits | Ánh xạ từ đúng inner hit group |
| Inner hit ID không ổn định | Dùng nested offset như ID | Thêm business key cho nested object |
| Query qua nhiều index bị lỗi | Nested mapping không đồng nhất | Đồng bộ mapping hoặc dùng ignore_unmapped có chủ đích |
| Response quá lớn | Quá nhiều parent và inner hits, source không giới hạn | Giảm page size, inner size và field trả về |
| Nested update tốn kém | Nested object được cập nhật thường xuyên | Xem xét tách index hoặc mô hình dữ liệu khác |

## 17. Quy trình chọn và triển khai

Khi thiết kế một truy vấn nested, đi theo thứ tự:

1. Xác định các điều kiện có cần khớp trên cùng một phần tử array không.
2. Chọn mapping nested cho field cần giữ quan hệ.
3. Tạo index/mapping đúng trước khi index dữ liệu.
4. Đặt các điều kiện cần cùng nested object trong một nested query.
5. Chọn scoring context: must/should khi score có ý nghĩa, filter khi chỉ cần điều kiện.
6. Chọn score_mode theo cách muốn gộp score của nested matches.
7. Thêm inner_hits nếu UI cần biết nested item nào đã khớp.
8. Đặt tên inner hit rõ ràng, giới hạn size và chọn field cần trả.
9. Cấu hình inner hit sort và root nested sort riêng nếu cần.
10. Ánh xạ parent và inner hits sang DTO do ứng dụng sở hữu.
11. Áp dụng authorization cho cả nested query và inner-hit content.
12. Integration test false positive, score mode, inner hits, sort và giới hạn tài nguyên.
13. Đo hiệu năng trên dữ liệu có số nested object gần production.

## 18. Những điểm cần ghi nhớ

- Object array thông thường có thể làm mất quan hệ giữa field của từng phần tử; nested giữ quan hệ đó.
- nested query trả về document cha khi có nested document khớp.
- Các điều kiện cần khớp trên cùng nested item phải nằm trong cùng một nested query.
- score_mode gồm avg, max, min, sum và none; nó gộp score của nested matches thành score parent.
- score_mode không có ý nghĩa ranking đáng kể khi nested query chỉ nằm trong filter context.
- inner_hits trả về các nested document đã khớp, không phải toàn bộ nested array.
- Inner hit không có _id độc lập như root document; nên có business ID nếu cần định danh ổn định.
- Inner hit size, from, sort, source filtering và highlight đều có thể được cấu hình.
- inner_hits.sort sắp xếp nested result; nested root sort sắp xếp parent; score_mode điều khiển score.
- Nested query, nested aggregation và inner hits phục vụ những mục đích khác nhau.
- Nested object làm tăng số Lucene documents và chi phí index/search; không dùng nested cho mọi object array.
- Mapping đã tạo thành object thường cần index mới và reindex để chuyển sang nested.
- Spring Data có thể giữ inner hits trong metadata của SearchHit; cách unwrap content cần khớp phiên bản.
- Áp dụng authorization cho nested matches và giới hạn dữ liệu inner hits trước khi trả API.

Nested query giúp Elasticsearch xử lý chính xác quan hệ giữa các object con trong một document. Khi kết hợp đúng score_mode và inner_hits, ứng dụng vừa xếp hạng được document cha theo các nested match, vừa biết chính xác phần tử con nào đã làm kết quả phù hợp.
