# Mô hình thuộc tính sản phẩm bằng nested query

Một sản phẩm thường có nhiều thuộc tính, biến thể hoặc lựa chọn bán hàng. Ví dụ một chiếc áo có nhiều tổ hợp màu và kích cỡ; một laptop có nhiều cấu hình RAM/SSD; một sản phẩm có nhiều người bán với giá và tồn kho riêng. Khi các giá trị có quan hệ với nhau, mapping Elasticsearch phải giữ được mối quan hệ đó để query không ghép nhầm field từ những phần tử khác nhau.

Elasticsearch có hai kiểu object quan trọng:

- Object thông thường: các field con được flatten khi index. Phù hợp khi cần tìm theo từng field nhưng không cần giữ quan hệ giữa các phần tử trong một array of objects.
- Nested: mỗi phần tử object được index như một nested Lucene document liên kết với parent. Nested query đảm bảo nhiều điều kiện có thể được áp dụng trên cùng một phần tử object.

Nếu sản phẩm có các variant, nested thường phù hợp khi người dùng hỏi một tổ hợp cụ thể như “màu đen, size L, còn hàng”. Nếu dùng object thông thường, Elasticsearch có thể match màu đen ở variant thứ nhất và size L ở variant thứ hai, dù không có variant nào thỏa cả hai điều kiện.

Bài học này đi từ thiết kế document, mapping Spring Data Elasticsearch, nested query, inner_hits, sort và aggregation đến chi phí, kiểm thử và các lỗi thường gặp.

## 1. Bài toán thuộc tính sản phẩm

Giả sử một sản phẩm có nhiều biến thể:

    {
      "productId": "shirt-100",
      "name": "Classic Shirt",
      "brand": "Northwind",
      "variants": [
        {
          "sku": "shirt-100-black-m",
          "color": "black",
          "size": "M",
          "price": 29.9,
          "stock": 0
        },
        {
          "sku": "shirt-100-blue-l",
          "color": "blue",
          "size": "L",
          "price": 31.9,
          "stock": 12
        }
      ]
    }

Người dùng tìm sản phẩm có variant màu đen, size L và còn hàng. Với dữ liệu trên, sản phẩm không có variant như vậy:

- Variant thứ nhất có color=black nhưng size=M và stock=0.
- Variant thứ hai có size=L và stock=12 nhưng color=blue.

Nếu query chỉ kiểm tra riêng từng field mà không giữ quan hệ giữa chúng, sản phẩm có thể bị trả về sai.

## 2. Object thông thường flatten array of objects

Nếu mapping variants là object thông thường, Elasticsearch index các giá trị field như những tập giá trị độc lập. Về mặt khái niệm, document có thể được nhìn như:

    variants.color = ["black", "blue"]
    variants.size  = ["M", "L"]
    variants.stock = [0, 12]

Quan hệ giữa black với M và blue với L không còn được bảo toàn cho mục đích query correlation.

Query:

    GET products/_search
    {
      "query": {
        "bool": {
          "filter": [
            { "term": { "variants.color": "black" } },
            { "term": { "variants.size": "L" } },
            { "range": { "variants.stock": { "gt": 0 } } }
          ]
        }
      }
    }

Có thể match document dù không có variant nào đồng thời thỏa cả ba điều kiện. Mỗi filter có thể được thỏa bởi một phần tử array khác nhau.

Đây là lỗi correlation phổ biến với object array. Nếu nghiệp vụ cần điều kiện phải cùng thuộc một variant, hãy dùng nested.

## 3. Nested giữ quan hệ giữa các object

Khi field được mapping là nested, mỗi phần tử trong array được index thành một nested document riêng, có quan hệ với parent document.

Ví dụ mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "productId": {
            "type": "keyword"
          },
          "name": {
            "type": "text"
          },
          "brand": {
            "type": "keyword"
          },
          "variants": {
            "type": "nested",
            "properties": {
              "sku": {
                "type": "keyword"
              },
              "color": {
                "type": "keyword"
              },
              "size": {
                "type": "keyword"
              },
              "price": {
                "type": "double"
              },
              "stock": {
                "type": "integer"
              }
            }
          }
        }
      }
    }

Nested query chạy trên các nested documents tại path được chỉ định rồi trả về parent documents có ít nhất một nested object match.

## 4. Nested query cho cùng một variant

Query màu đen, size L và còn hàng:

    GET products/_search
    {
      "query": {
        "nested": {
          "path": "variants",
          "query": {
            "bool": {
              "filter": [
                { "term": { "variants.color": "black" } },
                { "term": { "variants.size": "L" } },
                { "range": { "variants.stock": { "gt": 0 } } }
              ]
            }
          }
        }
      }
    }

Các điều kiện nằm trong cùng một nested query nên phải được thỏa bởi cùng một phần tử variants. Với document ví dụ, sản phẩm sẽ không match.

Nếu thêm variant:

    {
      "sku": "shirt-100-black-l",
      "color": "black",
      "size": "L",
      "price": 32.9,
      "stock": 5
    }

thì product mới match.

## 5. Nhiều nested query có nghĩa là nhiều phần tử có thể khác nhau

Nếu query có hai nested clauses riêng:

    {
      "bool": {
        "filter": [
          {
            "nested": {
              "path": "variants",
              "query": {
                "term": {
                  "variants.color": "black"
                }
              }
            }
          },
          {
            "nested": {
              "path": "variants",
              "query": {
                "term": {
                  "variants.size": "L"
                }
              }
            }
          }
        ]
      }
    }

Hai nested clauses có thể được thỏa bởi hai variant khác nhau. Điều này đúng nếu nghiệp vụ chỉ cần sản phẩm có ít nhất một variant màu đen và có ít nhất một variant size L, dù không phải cùng variant.

Nếu nghiệp vụ yêu cầu một variant đồng thời có màu đen và size L, hãy đặt cả hai điều kiện trong cùng một nested query.

## 6. Khi nào dùng object, nested hoặc flattened?

| Kiểu | Bảo toàn quan hệ giữa object array? | Trường hợp phù hợp |
|---|---|---|
| object | Không | Field con được query độc lập |
| nested | Có | Các field của cùng một phần tử phải match cùng nhau |
| flattened | Không giữ quan hệ object | Map có nhiều key động, chủ yếu exact lookup |

Không nên chuyển mọi object thành nested. Nested có chi phí indexing, storage và query cao hơn object thông thường vì mỗi phần tử nested tạo một Lucene document nội bộ.

Dùng nested khi quan hệ giữa các thuộc tính là một phần của semantics nghiệp vụ. Nếu chỉ cần filter theo từng giá trị độc lập, object có thể đơn giản và nhẹ hơn.

Flattened hữu ích với map có key động và nhiều thuộc tính không cố định, nhưng không thay thế nested khi cần correlation giữa các trường trong cùng object.

## 7. Mô hình thuộc tính động dạng key/value

Một số catalog có thuộc tính khác nhau theo category:

    {
      "productId": "laptop-100",
      "attributes": [
        {
          "name": "ramGb",
          "valueKeyword": "16",
          "valueNumber": 16
        },
        {
          "name": "storageType",
          "valueKeyword": "SSD"
        },
        {
          "name": "color",
          "valueKeyword": "silver"
        }
      ]
    }

Nếu cần đảm bảo name và value thuộc cùng một attribute entry, mapping attributes nên là nested:

    "attributes": {
      "type": "nested",
      "properties": {
        "name": {
          "type": "keyword"
        },
        "valueKeyword": {
          "type": "keyword"
        },
        "valueNumber": {
          "type": "double"
        }
      }
    }

Query laptop có RAM 16 GB:

    {
      "nested": {
        "path": "attributes",
        "query": {
          "bool": {
            "filter": [
              { "term": { "attributes.name": "ramGb" } },
              { "term": { "attributes.valueNumber": 16 } }
            ]
          }
        }
      }
    }

Nếu value có nhiều kiểu dữ liệu, đừng lưu tất cả thành text rồi cố range query trên chuỗi. Dùng field typed như valueNumber, valueDate, valueBoolean hoặc mô hình attribute riêng theo domain.

## 8. Mô hình variants và attributes có thể kết hợp

Một product có variants, mỗi variant lại có attributes:

    {
      "productId": "laptop-200",
      "variants": [
        {
          "sku": "lap-200-silver-16",
          "attributes": [
            { "name": "color", "valueKeyword": "silver" },
            { "name": "ramGb", "valueNumber": 16 }
          ],
          "price": 1200,
          "stock": 8
        }
      ]
    }

Mapping có thể dùng nested ở cả hai cấp:

    "variants": {
      "type": "nested",
      "properties": {
        "sku": { "type": "keyword" },
        "price": { "type": "double" },
        "stock": { "type": "integer" },
        "attributes": {
          "type": "nested",
          "properties": {
            "name": { "type": "keyword" },
            "valueKeyword": { "type": "keyword" },
            "valueNumber": { "type": "double" }
          }
        }
      }
    }

Nested query lồng nhau cần chỉ rõ path ở từng cấp. Cách này mạnh nhưng có thêm chi phí và độ phức tạp. Chỉ dùng khi cần giữ quan hệ ở cả hai cấp.

## 9. Mapping bằng Spring Data Elasticsearch

Một entity có thể khai báo nested field bằng FieldType.Nested:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String productId;

        @Field(type = FieldType.Text)
        private String name;

        @Field(type = FieldType.Keyword)
        private String brand;

        @Field(type = FieldType.Nested)
        private List<ProductVariant> variants;
    }

    public class ProductVariant {

        @Field(type = FieldType.Keyword)
        private String sku;

        @Field(type = FieldType.Keyword)
        private String color;

        @Field(type = FieldType.Keyword)
        private String size;

        @Field(type = FieldType.Double)
        private Double price;

        @Field(type = FieldType.Integer)
        private Integer stock;
    }

Tên enum và thuộc tính annotation phụ thuộc Spring Data Elasticsearch version. Có thể quản lý mapping bằng JSON hoặc index template nếu cần settings nâng cao. Điều quan trọng là mapping thực tế trong Elasticsearch phải khai báo variants là nested; chỉ khai báo Java List không tự đảm bảo semantics nested nếu mapping không đúng.

## 10. Tạo index và kiểm tra mapping

Trong ứng dụng Spring Data, có thể dùng IndexOperations để kiểm tra hoặc tạo index theo metadata của entity:

    IndexOperations indexOps =
        operations.indexOps(Product.class);

    if (!indexOps.exists()) {
        indexOps.create();
        indexOps.putMapping();
    }

Tên method và cách tạo mapping phụ thuộc version. Trong deployment thực tế, mapping thường được quản lý qua migration hoặc index template thay vì tạo tùy tiện khi ứng dụng khởi động.

Kiểm tra mapping từ Elasticsearch:

    GET products/_mapping

Xác nhận:

- variants có type nested.
- color và size là keyword nếu dùng term filter.
- price là numeric nếu dùng range/sort.
- stock là integer/long phù hợp.
- Field name trong query đúng mapping.

Nếu mapping đã được tạo trước đó với variants là object, không thể chỉ đổi annotation rồi mong index cũ trở thành nested. Tạo index mới và reindex dữ liệu.

## 11. NativeQuery với nested query

Spring Data Elasticsearch hỗ trợ NativeQuery để biểu diễn query DSL của Elasticsearch. Một ví dụ khái quát:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .nested(n -> n
                .path("variants")
                .query(nq -> nq
                    .bool(b -> b
                        .filter(f -> f
                            .term(t -> t
                                .field("variants.color")
                                .value("black")
                            )
                        )
                        .filter(f -> f
                            .term(t -> t
                                .field("variants.size")
                                .value("L")
                            )
                        )
                        .filter(f -> f
                            .range(r -> r
                                .number(nr -> nr
                                    .field("variants.stock")
                                    .gt(0.0)
                                )
                            )
                        )
                    )
                )
            )
        )
        .build();

    SearchHits<Product> hits =
        operations.search(query, Product.class);

Đây là minh họa theo Java API Client builder được dùng trong các phiên bản Spring Data hiện đại. Chữ ký builder, kiểu numeric range và import có thể khác theo version. Nếu IDE không nhận đúng builder, kiểm tra API client được Spring Data quản lý và tạo query bằng đúng version đó.

Điều quan trọng là query DSL cuối cùng phải có nested path variants và cả ba filter nằm trong query con đó.

## 12. Criteria API và nested semantics

Criteria API có thể hữu ích cho query đơn giản, nhưng không nên giả định việc viết:

    Criteria.where("variants.color").is("black")
        .and("variants.size").is("L")

sẽ tự động tạo nested query với correlation đúng như mong muốn.

Mapping nested và nested query là hai việc liên quan nhưng khác nhau. Query cần phát sinh đúng nested DSL. Với query phức tạp, NativeQuery hoặc Java API Client thường giúp kiểm soát semantics rõ ràng hơn.

Hãy kiểm tra request thực tế trong integration test hoặc request logging đã redact. Không kết luận chỉ dựa trên việc Java code compile.

## 13. Kết hợp nested query với filter ở parent

Product thường có field ở parent như brand, category, tenant và status, cùng field ở nested variant như color, size, price và stock.

Query có thể kết hợp:

    GET products/_search
    {
      "query": {
        "bool": {
          "filter": [
            { "term": { "brand": "Northwind" } },
            { "term": { "category": "shirts" } },
            { "term": { "status": "ACTIVE" } },
            {
              "nested": {
                "path": "variants",
                "query": {
                  "bool": {
                    "filter": [
                      { "term": { "variants.color": "black" } },
                      { "term": { "variants.size": "L" } },
                      { "range": { "variants.stock": { "gt": 0 } } }
                    ]
                  }
                }
              }
            }
          ]
        }
      }
    }

Parent filters xác định sản phẩm đủ điều kiện. Nested filter xác định có ít nhất một variant thỏa tổ hợp thuộc tính.

## 14. Nested query với nhiều lựa chọn OR

Giả sử người dùng chấp nhận màu đen hoặc xanh, nhưng cần size L và còn hàng:

    {
      "nested": {
        "path": "variants",
        "query": {
          "bool": {
            "filter": [
              {
                "terms": {
                  "variants.color": ["black", "blue"]
                }
              },
              { "term": { "variants.size": "L" } },
              { "range": { "variants.stock": { "gt": 0 } } }
            ]
          }
        }
      }
    }

Terms query là OR giữa các giá trị trong cùng field. Các filter trong bool.filter là AND. Tất cả vẫn được đánh giá trên cùng nested object.

Nếu cần logic OR giữa nhiều nhóm điều kiện phức tạp, dùng bool.should và đặt minimum_should_match rõ ràng.

## 15. Nested query và score_mode

Nested query có thể trả score của parent dựa trên score của nested documents match. score_mode xác định cách kết hợp:

- avg: trung bình score của nested matches.
- max: score cao nhất.
- min: score thấp nhất.
- sum: tổng score.
- none: không tính nested score cho parent.

Với điều kiện lọc thuộc tính sản phẩm, thường dùng filter context hoặc score_mode none vì match variant chỉ quyết định eligibility, không cần tăng relevance score.

Nếu nested query dùng trong should để góp phần xếp hạng, chọn score_mode theo ý nghĩa nghiệp vụ và đo tác động.

## 16. Lấy variant đã match bằng inner_hits

Nested query mặc định trả parent product. Nếu giao diện cần biết variant nào đã match, dùng inner_hits:

    GET products/_search
    {
      "query": {
        "nested": {
          "path": "variants",
          "query": {
            "bool": {
              "filter": [
                { "term": { "variants.color": "black" } },
                { "term": { "variants.size": "L" } },
                { "range": { "variants.stock": { "gt": 0 } } }
              ]
            }
          },
          "inner_hits": {
            "name": "matching_variants",
            "size": 5
          }
        }
      }
    }

Response có phần inner_hits chứa nested documents đã match, giúp ứng dụng biết SKU, price và stock của variant phù hợp.

inner_hits hữu ích khi:

- Hiển thị variant phù hợp.
- Giải thích vì sao product được trả về.
- Lấy SKU cụ thể để thêm vào giỏ hàng.
- Tránh phải tải mọi variant rồi lọc lại trong Java.

Giới hạn inner_hits size. Nếu một parent có hàng nghìn nested children, trả tất cả có thể làm response lớn và tốn memory.

## 17. Đọc inner_hits trong Spring Data

Spring Data SearchHit có thể expose inner hits tùy version và cách mapping. Cấu trúc response của Java API Client có thể chứa map innerHits theo tên đã đặt.

Khi tích hợp:

- Kiểm tra kiểu trả về của SearchHit.
- Đọc inner hit theo tên matching_variants.
- Map nested source sang ProductVariant DTO.
- Không giả định content của parent đã bị rút gọn chỉ còn nested object match.

Parent Product vẫn có thể chứa toàn bộ variants trong source. inner_hits là phần kết quả riêng cho nested matches.

Nếu chỉ cần variant match, map inner_hits sang response DTO và không trả mọi variant.

## 18. Nested sort

Một sản phẩm có nhiều giá variant. Nếu muốn sort sản phẩm theo giá thấp nhất trong các variant còn hàng, cần nested sort với filter.

Ví dụ:

    GET products/_search
    {
      "sort": [
        {
          "variants.price": {
            "order": "asc",
            "mode": "min",
            "nested": {
              "path": "variants",
              "filter": {
                "range": {
                  "variants.stock": {
                    "gt": 0
                  }
                }
              }
            }
          }
        }
      ],
      "query": {
        "match_all": {}
      }
    }

Nested sort cần path và có thể có filter để chỉ xét variant hợp lệ. Nếu không có filter, sản phẩm có thể được sort theo variant hết hàng có giá thấp nhất.

Các mode như min, max, avg, sum hoặc median có thể được hỗ trợ tùy kiểu field/API. Chọn mode theo business semantics.

## 19. Nested sort kết hợp nested query

Nếu query đã yêu cầu variant còn hàng nhưng sort không có nested filter tương ứng, sort có thể xét tập nested values khác với tập đã match query tùy cách query và sort được cấu hình.

Để bảo đảm sort theo đúng nhóm variant, cấu hình nested sort filter giống điều kiện eligibility liên quan:

- stock > 0.
- status = ACTIVE.
- color/size nếu sort theo kết quả đã chọn.

Không mặc định rằng nested sort tự kế thừa mọi điều kiện trong nested query. Kiểm tra DSL và kết quả thực tế.

## 20. Nested aggregation

Nếu muốn thống kê số variant theo màu, dùng nested aggregation để đi vào nested documents:

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "variants_scope": {
          "nested": {
            "path": "variants"
          },
          "aggs": {
            "by_color": {
              "terms": {
                "field": "variants.color"
              }
            }
          }
        }
      }
    }

Nested aggregation đếm các nested documents, không phải parent products. Một product có nhiều variant cùng màu có thể đóng góp nhiều bucket documents.

Nếu cần quay lại parent scope để đếm sản phẩm duy nhất, dùng reverse_nested aggregation.

## 21. Reverse nested aggregation

Ví dụ đếm số product có variant theo màu:

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "variants_scope": {
          "nested": {
            "path": "variants"
          },
          "aggs": {
            "by_color": {
              "terms": {
                "field": "variants.color"
              },
              "aggs": {
                "parent_products": {
                  "reverse_nested": {}
                }
              }
            }
          }
        }
      }
    }

Trong mỗi bucket màu:

- doc_count của bucket là số nested variant documents.
- parent_products.doc_count là số parent products liên quan.

Hai con số khác nhau nếu một product có nhiều variant cùng màu.

## 22. Nested query với must_not

Phủ định nested query cần đặc biệt cẩn thận.

Muốn tìm product không có variant màu đỏ, đặt nested query bên trong bool.must_not ở parent level:

    GET products/_search
    {
      "query": {
        "bool": {
          "must_not": [
            {
              "nested": {
                "path": "variants",
                "query": {
                  "term": {
                    "variants.color": "red"
                  }
                }
              }
            }
          ]
        }
      }
    }

Cách này loại parent nếu tồn tại ít nhất một nested variant màu đỏ.

Nếu đặt must_not bên trong nested query, ý nghĩa là tìm nested variant không có thuộc tính màu đỏ; parent vẫn có thể match nhờ một nested variant khác. Đó không tương đương với “parent không có bất kỳ variant màu đỏ nào”.

Luôn viết test cho phủ định và empty nested array.

## 23. Nested query và missing/null

Field nested có thể:

- Không tồn tại.
- Có array rỗng.
- Có object nhưng field con thiếu.
- Có field con null.
- Có giá trị rỗng.

Các trường hợp này không nhất thiết tương đương trong Elasticsearch. exists query kiểm tra field có giá trị được index hay không, không đơn giản là kiểm tra key có xuất hiện trong JSON.

Ví dụ tìm variant có stock field:

    {
      "nested": {
        "path": "variants",
        "query": {
          "exists": {
            "field": "variants.stock"
          }
        }
      }
    }

Nếu business yêu cầu stock thiếu được xem là 0, nên chuẩn hóa dữ liệu trước khi index hoặc biểu diễn trạng thái rõ ràng. Không dựa vào null semantics để thay thế business default.

## 24. Nested query và filter quyền truy cập

Một số hệ thống có ACL ở cấp variant, offer hoặc inventory source. Khi đó cần nested filter để giữ quan hệ giữa principal, permission và variant.

Ví dụ:

    "offers": [
      {
        "sellerId": "seller-a",
        "region": "VN",
        "status": "ACTIVE",
        "price": 100
      },
      {
        "sellerId": "seller-b",
        "region": "SG",
        "status": "ACTIVE",
        "price": 90
      }
    ]

Nếu cần offer ở region VN do seller A cung cấp, các điều kiện phải nằm trong cùng nested query path offers. Nếu query region và seller ở hai nested clauses riêng, có thể match hai offer khác nhau.

Security filter bắt buộc phải được tạo từ trusted principal và policy phía backend. Không cho client tự chọn seller/tenant để vượt qua quyền truy cập.

## 25. Nested query kết hợp vector search

Một product có thể có vector ở parent và nested variants chứa thuộc tính lọc. Khi query semantic, có thể kết hợp kNN retrieval với nested filter theo variant, tùy API và phiên bản Elasticsearch.

Ví dụ ý tưởng:

    {
      "knn": {
        "field": "embedding",
        "query_vector": [ ... ],
        "k": 20,
        "num_candidates": 200,
        "filter": {
          "nested": {
            "path": "variants",
            "query": {
              "bool": {
                "filter": [
                  { "term": { "variants.color": "black" } },
                  { "term": { "variants.size": "L" } },
                  { "range": { "variants.stock": { "gt": 0 } } }
                ]
              }
            }
          }
        }
      }
    }

Đây là minh họa cấu trúc. Hỗ trợ filter nested trong kNN, nested vector fields và vị trí filter phụ thuộc Elasticsearch version và API. Kiểm tra server reference và test request thực tế.

Nếu vector nằm trong nested object thay vì parent, query phải dùng nested kNN semantics phù hợp. Không giả định query vector trên parent field tự động tìm vector trong nested children.

## 26. Multi-level nested

Khi nested object chứa một nested object khác, query cần lồng nested path:

    {
      "nested": {
        "path": "variants",
        "query": {
          "nested": {
            "path": "variants.attributes",
            "query": {
              "bool": {
                "filter": [
                  { "term": { "variants.attributes.name": "color" } },
                  { "term": { "variants.attributes.valueKeyword": "black" } }
                ]
              }
            }
          }
        }
      }
    }

Nested path con được diễn giải trong context của parent nested path. Cấu trúc phức tạp làm query khó đọc và có thể tăng chi phí đáng kể.

Nếu chỉ cần vài thuộc tính cố định, field trực tiếp trên variant thường đơn giản hơn dynamic nested attributes.

## 27. Giới hạn và chi phí nested

Nested tạo thêm Lucene documents nội bộ. Một parent có 50 nested children có thể tạo ra số Lucene documents lớn hơn đáng kể so với số product records.

Chi phí:

- Index size tăng.
- Indexing và update tốn CPU hơn.
- Query cần join nested-child với parent.
- Nested aggregation tốn thêm work.
- Inner hits làm response lớn.
- Merge và recovery phải xử lý nested docs.

Elasticsearch có giới hạn cấu hình cho số nested fields và số nested objects trong một document. Tên setting và default có thể thay đổi theo version. Kiểm tra giới hạn hiện tại của cluster trước khi index dữ liệu có nested arrays rất lớn.

Đừng dùng nested cho một array có hàng chục nghìn phần tử mà không benchmark. Nếu cần lưu lịch sử hoặc quan hệ con lớn, cân nhắc tách child thành index riêng và liên kết bằng ID.

## 28. Update nested object

Nested documents gắn với parent. Khi update một nested child, Elasticsearch thường phải index lại parent document cùng nested structure theo thao tác update của document.

Nếu product có hàng nghìn variants và chỉ stock một variant thay đổi thường xuyên, update parent có thể tốn đáng kể.

Lựa chọn mô hình:

- Nested: phù hợp khi cần query correlation và số child vừa phải.
- Child documents/index riêng: phù hợp khi child cập nhật độc lập và số lượng lớn, nhưng query/join phức tạp hơn.
- Denormalized product projection: phù hợp khi chấp nhận cập nhật projection theo event.

Chọn theo tần suất cập nhật, số lượng child, query pattern và consistency requirements.

## 29. Partial update và nested array

Partial update một field ở nested child không đơn giản như update một relational row theo child ID vì nested child không có ID độc lập theo API document thông thường.

Có thể:

- Đọc parent, sửa nested list rồi index lại parent.
- Dùng script update trên parent source để sửa phần tử phù hợp, nếu logic và hiệu năng chấp nhận được.
- Tách child thành document riêng nếu cần update độc lập.

Script update phải xử lý trường hợp child không tồn tại, duplicate key và concurrent updates. Với update thường xuyên, cần benchmark và có optimistic concurrency.

## 30. Idempotency khi đồng bộ nested data

Khi đồng bộ product từ database, event có thể được giao nhiều lần. Dùng ID ổn định cho parent và key ổn định cho variant:

    productId = "shirt-100"
    variant.sku = "shirt-100-black-l"

Consumer nên tạo projection deterministically từ source of truth, thay vì append nested item mỗi lần event đến. Nếu append không kiểm tra, duplicate event có thể tạo variant lặp.

Khi thay đổi variant:

- Tạo lại list từ trạng thái nguồn hiện tại nếu phù hợp.
- Hoặc update theo SKU với script/logic idempotent.
- Giữ source version để bỏ qua event cũ.
- Kiểm tra delete/tombstone cho variant đã ngừng bán.

## 31. Nested mapping và dynamic attributes

Nếu category có hàng nghìn loại attribute name khác nhau, mapping một field riêng cho mỗi tên có thể làm mapping bùng nổ.

Một nested key/value model có thể tránh tạo dynamic field cho từng attribute:

    attributes:
      - name: ramGb
        valueNumber: 16
      - name: color
        valueKeyword: silver

Nhưng nested vẫn tạo một nested document cho mỗi attribute entry. Nếu số attribute cực lớn hoặc không cần correlation, flattened có thể tiết kiệm hơn.

Chọn typed value fields để range query đúng kiểu. Nếu dùng một field value text chung, numeric sorting và range semantics sẽ khó kiểm soát.

## 32. Nested query trên nhiều index

Alias có thể trỏ đến nhiều index version. Nếu một index có variants là nested nhưng index khác có variants là object hoặc không có field, query có thể lỗi hoặc cho kết quả không nhất quán.

Trước khi dùng nested query trên alias:

- Kiểm tra mapping của mọi index.
- Giữ nested path tương thích.
- Dùng ignore_unmapped khi phù hợp với API.
- Không dùng ignore_unmapped để che giấu mapping migration chưa hoàn tất.
- Chuyển alias sau khi index mới được kiểm tra.

Mapping nested không thể được đổi tại chỗ một cách tùy ý; thường cần index mới và reindex.

## 33. Nested query với sort và pagination

Khi sort theo nested price, pagination cần sort ổn định. Nếu nhiều product có cùng giá, thêm tie-breaker như productId để tránh thứ tự không ổn định giữa các trang.

Ví dụ:

    "sort": [
      {
        "variants.price": {
          "order": "asc",
          "mode": "min",
          "nested": {
            "path": "variants",
            "filter": {
              "range": {
                "variants.stock": {
                  "gt": 0
                }
              }
            }
          }
        }
      },
      {
        "productId": {
          "order": "asc"
        }
      }
    ]

Với deep pagination, cân nhắc PIT và search_after thay vì from/size lớn. Sort values phải được giữ nguyên giữa các trang.

## 34. Kiểm thử false positive do object flattening

Một integration test quan trọng nên tạo hai variants không có variant nào thỏa đủ điều kiện:

    Product product = product(
        variant("black", "M", 0),
        variant("blue", "L", 12)
    );

Sau khi index và refresh, query black + L + stock > 0 phải không trả product.

Sau đó thêm variant black + L + stock 5, index lại và query phải trả product.

Test này chứng minh nested semantics đang hoạt động. Chỉ kiểm tra mapping JSON có type nested chưa đủ; cần kiểm tra behavior query trên data có thể tạo false positive.

## 35. Kiểm thử inner_hits

Tạo product có nhiều variants, chỉ một variant thỏa điều kiện. Query nested với inner_hits và xác nhận:

- Parent product xuất hiện.
- inner_hits chỉ chứa variant thỏa điều kiện.
- SKU, color, size, stock đúng.
- Variant không thỏa không xuất hiện trong inner_hits.
- Response DTO không vô tình trả toàn bộ nested source nếu không cần.

Nếu dùng Spring Data SearchHit, kiểm tra cách version hiện tại expose inner hit map và conversion.

## 36. Kiểm thử nested sort

Tạo hai product:

- Product A có variant còn hàng giá 120 và variant hết hàng giá 50.
- Product B có variant còn hàng giá 90.

Nếu sort theo giá thấp nhất trong variant còn hàng, Product B phải đứng trước Product A. Nếu sort bỏ qua nested filter, Product A có thể đứng trước vì variant hết hàng giá 50.

Test này xác nhận nested sort filter đúng với business eligibility.

## 37. Kiểm thử nested aggregation

Tạo product có nhiều variants cùng màu và product khác có variant màu đó. Kiểm tra:

- Nested bucket count phản ánh số variant.
- Reverse nested count phản ánh số parent product.
- Một product có nhiều variant cùng màu không bị đếm thành nhiều product khi dùng parent count.

Đây là lỗi phổ biến khi dashboard hiển thị “số sản phẩm theo màu” nhưng aggregation lại đếm nested variants.

## 38. Test bằng Spring Data Elasticsearch

Một integration test có thể dùng ElasticsearchOperations:

    @Test
    void nestedQueryMatchesOneVariantAsAWhole() {
        Product product = new Product();
        product.setProductId("shirt-test-1");
        product.setName("Classic Shirt");
        product.setVariants(List.of(
            variant("black", "M", 0),
            variant("blue", "L", 12)
        ));

        operations.save(product);
        operations.indexOps(Product.class).refresh();

        NativeQuery query = buildBlackLargeInStockQuery();

        SearchHits<Product> hits =
            operations.search(query, Product.class);

        assertThat(hits.getSearchHits())
            .extracting(hit -> hit.getId())
            .doesNotContain("shirt-test-1");
    }

Đây là ví dụ minh họa. Query builder và API refresh phụ thuộc Spring Data version. Test cần chạy với index mapping thực tế có variants là nested.

## 39. Test mapping và index lifecycle

Test setup nên tạo index từ mapping đúng. Nếu dùng index đã tồn tại từ lần chạy trước với mapping object, annotation mới không tự sửa mapping.

Một lifecycle rõ:

1. Tạo index test mới.
2. Apply mapping.
3. Index fixture.
4. Refresh khi cần search.
5. Chạy nested query/sort/aggregation.
6. Xác nhận kết quả.
7. Xóa index test.

Không xóa index dùng chung giữa các test hoặc môi trường developer. Dùng tên index riêng cho test run.

## 40. Những lỗi thường gặp

### Dùng object array khi cần correlation

Field từ nhiều phần tử có thể ghép thành một match sai. Dùng nested query nếu các điều kiện phải thuộc cùng object.

### Mỗi điều kiện là một nested query riêng dù cần cùng variant

Các nested clauses riêng có thể match những phần tử khác nhau. Đặt điều kiện cùng variant trong một nested query.

### Nghĩ Java List tự động tạo nested mapping

List trong entity không đủ để bảo đảm mapping nested. Kiểm tra mapping thực tế.

### Đổi annotation nhưng dùng index cũ

Mapping cũ không tự đổi từ object sang nested. Tạo index mới và reindex.

### Dùng nested cho mọi object

Nested tăng số Lucene documents và query overhead. Chỉ dùng khi cần giữ quan hệ.

### Query field con mà quên nested path

Term query thông thường không thay thế nested query. Dùng nested query với đúng path.

### Sort theo nested field nhưng không có nested filter

Có thể sort theo variant không đủ điều kiện, như variant hết hàng. Đặt nested sort filter.

### Aggregation nested nhưng đọc doc_count như product count

doc_count trong nested scope là số nested documents. Dùng reverse_nested để quay lại parent scope.

### Dùng must_not sai cấp

must_not bên trong nested có thể tìm nested child không match, không có nghĩa parent không chứa child match. Đặt nested query trong parent bool.must_not khi cần loại parent.

### inner_hits không giới hạn

Response có thể rất lớn. Đặt size và chỉ lấy field cần thiết.

### Nested array quá lớn

Indexing, query và update tốn kém. Cân nhắc child index hoặc mô hình khác.

### Update nested child như một relational row

Nested child không có lifecycle document độc lập thông thường. Update parent hoặc tách child index nếu cần cập nhật độc lập.

### Dynamic attribute tạo mapping bùng nổ

Không tạo field riêng cho mọi attribute name nếu key thay đổi tự do. Dùng typed key/value model hoặc flattened khi phù hợp.

### Không test false positive

Dataset đơn giản có thể không bộc lộ lỗi correlation. Tạo fixture với hai nested objects chia nhau các điều kiện.

## 41. Quy trình thiết kế product nested query

Khi thiết kế catalog:

1. Liệt kê các field ở cấp product và variant.
2. Xác định điều kiện nào phải thuộc cùng một variant.
3. Chọn object hay nested theo correlation semantics.
4. Định nghĩa field type cho keyword, numeric, date và boolean.
5. Tạo mapping và kiểm tra trên index thật.
6. Viết query nested cho các tổ hợp điều kiện.
7. Dùng inner_hits nếu cần trả variant match.
8. Dùng nested sort với filter tương ứng.
9. Dùng nested/reverse_nested aggregation theo đúng scope.
10. Đánh giá chi phí nested document count và update rate.
11. Viết integration test false positive, sort, aggregation và must_not.
12. Reindex qua index version mới nếu thay đổi mapping.

## Kết luận

Nested là lựa chọn phù hợp khi các field trong cùng một object array phải được đánh giá như một nhóm. Với sản phẩm có nhiều variants, nested query giúp bảo đảm color, size, price và stock cùng thuộc một variant; object thông thường flatten các giá trị và có thể tạo false positive. Trong Spring Data Elasticsearch, khai báo FieldType.Nested phải khớp mapping thực tế và query phải phát sinh đúng nested DSL. Đặt các điều kiện cần cùng match trong một nested query; dùng nhiều nested clauses riêng chỉ khi các điều kiện có thể được thỏa bởi các phần tử khác nhau.

Nested query có thể kết hợp parent filters, inner_hits, nested sort và nested aggregation. Hãy dùng reverse_nested khi cần thống kê parent products, nested sort filter để bỏ qua variant không hợp lệ và parent-level must_not để loại product có bất kỳ nested child nào vi phạm điều kiện. Nested làm tăng Lucene document count và chi phí indexing/update, vì vậy chỉ dùng khi cần correlation. Kiểm thử bằng fixture cố tình chia các điều kiện qua nhiều variant để bắt lỗi false positive, đồng thời đo query, sort, aggregation và update trên dữ liệu gần thực tế.
