# So sánh embedded, nested, cha-con và liên kết ở tầng ứng dụng

Khi một document Elasticsearch có dữ liệu liên quan, ứng dụng cần chọn cách biểu diễn mối quan hệ đó. Ví dụ, một sản phẩm có nhiều biến thể và nhiều người bán; một câu hỏi có nhiều câu trả lời; một bài viết có tác giả và nhiều bình luận; một đơn hàng có nhiều dòng hàng. Những dữ liệu này có thể được lưu chung trong một document, lưu thành nested object, tổ chức theo quan hệ parent-child hoặc giữ riêng rồi liên kết ở tầng ứng dụng.

Không có một mô hình phù hợp cho mọi trường hợp. Cách lưu trữ ảnh hưởng đến:

- Độ chính xác của truy vấn khi nhiều thuộc tính liên quan phải khớp trên cùng một phần tử.
- Chi phí index, update, delete và search.
- Khả năng truy vấn, aggregation và sort trên dữ liệu liên quan.
- Kích thước document và số lượng Lucene document nội bộ.
- Cách đồng bộ dữ liệu và xử lý tính nhất quán.
- Độ phức tạp của code Spring Data Elasticsearch.

Bốn lựa chọn chính:

1. **Embedded object:** nhúng dữ liệu liên quan vào document dưới dạng object hoặc mảng object thông thường.
2. **Nested:** lưu từng phần tử object trong một cấu trúc nested để Elasticsearch giữ quan hệ giữa các field trong cùng phần tử.
3. **Parent-child:** lưu parent và child thành các document riêng trong cùng một index, kết nối bằng join field.
4. **Liên kết ở tầng ứng dụng:** lưu ID tham chiếu, truy vấn các document riêng rồi ghép kết quả trong service hoặc repository.

Để chọn đúng, cần bắt đầu từ cách dữ liệu được đọc và cập nhật, sau đó xem xét các giới hạn của Elasticsearch và khả năng ánh xạ của Spring Data.

## 1. Bài toán quan hệ trong document database

Giả sử một sản phẩm có nhiều offer:

    {
      "productId": "p-100",
      "name": "Mechanical Keyboard",
      "offers": [
        {
          "seller": "Store A",
          "price": 120,
          "available": true
        },
        {
          "seller": "Store B",
          "price": 95,
          "available": false
        }
      ]
    }

Người dùng muốn tìm sản phẩm có một offer vừa có seller là Store A vừa có price dưới 100. Nếu lưu offers dưới dạng object array thông thường, Elasticsearch có thể tách các giá trị thành những danh sách độc lập khi index. Một truy vấn kết hợp seller và price có thể vô tình khớp seller của offer thứ nhất với price của offer thứ hai.

Đây là ví dụ cho thấy quan hệ giữa các field có ý nghĩa. Nếu nghiệp vụ yêu cầu các điều kiện phải cùng đúng trên một phần tử, cần chọn mô hình giữ được ranh giới phần tử, thường là nested.

Ngược lại, nếu ứng dụng chỉ cần tìm sản phẩm theo bất kỳ seller nào và không cần đảm bảo seller cùng price thuộc cùng một offer, object array có thể đủ đơn giản và tiết kiệm chi phí hơn.

## 2. Embedded object là gì?

Embedded object là object được lưu trực tiếp bên trong document cha. Trong Elasticsearch mapping, kiểu object là mặc định cho một thuộc tính object nếu không khai báo kiểu khác.

Ví dụ:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text"
          },
          "manufacturer": {
            "properties": {
              "name": {
                "type": "keyword"
              },
              "country": {
                "type": "keyword"
              }
            }
          }
        }
      }
    }

Document:

    {
      "name": "Keyboard K8",
      "manufacturer": {
        "name": "Keychron",
        "country": "China"
      }
    }

Embedded object phù hợp khi dữ liệu con:

- Có vòng đời gắn chặt với document cha.
- Thường được đọc cùng document cha.
- Không cần truy vấn độc lập như một thực thể riêng.
- Không cần giữ quan hệ phức tạp giữa nhiều object trong một mảng.
- Có kích thước tương đối ổn định và không tăng vô hạn.

Một lợi ích lớn là ứng dụng có thể lấy toàn bộ dữ liệu cần thiết trong một lần search mà không cần join hoặc gọi thêm repository.

## 3. Mảng object thông thường và vấn đề mất quan hệ giữa field

Giả sử mapping có một mảng offers:

    PUT products
    {
      "mappings": {
        "properties": {
          "offers": {
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

Document:

    {
      "offers": [
        {
          "seller": "Store A",
          "price": 120,
          "available": true
        },
        {
          "seller": "Store B",
          "price": 95,
          "available": false
        }
      ]
    }

Elasticsearch index các giá trị của object array theo cách làm mất ranh giới giữa từng object. Về mặt khái niệm, các field có thể được nhìn như:

    offers.seller = [ "Store A", "Store B" ]
    offers.price = [ 120, 95 ]
    offers.available = [ true, false ]

Nếu truy vấn:

    GET products/_search
    {
      "query": {
        "bool": {
          "must": [
            {
              "term": {
                "offers.seller": "Store A"
              }
            },
            {
              "range": {
                "offers.price": {
                  "lt": 100
                }
              }
            }
          ]
        }
      }
    }

Document có thể khớp vì Store A tồn tại trong một offer và price 95 tồn tại trong một offer khác. Nhưng không có offer nào vừa thuộc Store A vừa có giá dưới 100.

Đây là false positive do ứng dụng cần quan hệ cùng phần tử, trong khi object array thông thường không giữ quan hệ đó khi index.

### Khi object array vẫn phù hợp

Object array không phải lúc nào cũng sai. Nó phù hợp khi:

- Chỉ cần biết một giá trị có xuất hiện ở bất kỳ phần tử nào.
- Không cần ghép nhiều điều kiện trên cùng một object con.
- Mỗi field được truy vấn độc lập.
- Cần giảm chi phí của nested document.

Ví dụ, tìm sản phẩm có bất kỳ offer nào từ Store A có thể dùng term query trên offers.seller nếu không cần ràng buộc thêm thuộc tính khác của cùng offer.

## 4. Spring Data mapping cho embedded object

Spring Data Elasticsearch ánh xạ object Java vào object field. Có thể khai báo rõ kiểu bằng FieldType.Object:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;

        @Field(type = FieldType.Object)
        private Manufacturer manufacturer;
    }

    public class Manufacturer {

        private String name;
        private String country;
    }

Với danh sách object:

    @Field(type = FieldType.Object)
    private List<Offer> offers;

    public class Offer {

        private String seller;
        private Double price;
        private Boolean available;
    }

Mapping metadata của Spring Data giúp tạo mapping phù hợp khi ứng dụng tạo index bằng IndexOperations. Nếu mapping cần analyzer, normalizer, dynamic template hoặc thuộc tính Elasticsearch chuyên sâu, có thể quản lý mapping bằng mapping JSON hoặc index template.

Khai báo Java class không tự giải quyết vấn đề mất quan hệ giữa các object trong array. Nếu field được map thành object, Elasticsearch vẫn áp dụng semantics object array nói trên.

## 5. Nested là gì?

Nested là một kiểu object đặc biệt của Elasticsearch. Mỗi phần tử nested được index như một Lucene document riêng, nhưng vẫn gắn với document cha. Nhờ vậy, Elasticsearch có thể giữ quan hệ giữa các field trong cùng một nested object.

Mapping:

    PUT products
    {
      "mappings": {
        "properties": {
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

Document vẫn có cấu trúc JSON tương tự:

    {
      "name": "Keyboard K8",
      "offers": [
        {
          "seller": "Store A",
          "price": 120,
          "available": true
        },
        {
          "seller": "Store B",
          "price": 95,
          "available": false
        }
      ]
    }

Khác biệt nằm ở mapping và cách index. Nested giữ ranh giới từng phần tử, vì vậy query có thể yêu cầu seller và price cùng khớp trong một offer.

Nested không phải quan hệ join tổng quát giữa hai entity. Nó là cách biểu diễn object con nằm trong cùng document cha, có thể truy vấn độc lập theo nested path nhưng thường được đọc và cập nhật cùng document cha.

## 6. Nested query giữ điều kiện trong cùng một phần tử

Để tìm sản phẩm có một offer vừa thuộc Store A vừa có giá dưới 100:

    GET products/_search
    {
      "query": {
        "nested": {
          "path": "offers",
          "query": {
            "bool": {
              "must": [
                {
                  "term": {
                    "offers.seller": "Store A"
                  }
                },
                {
                  "range": {
                    "offers.price": {
                      "lt": 100
                    }
                  }
                }
              ]
            }
          }
        }
      }
    }

Nested query chạy các điều kiện bên trong path offers trên cùng một nested document. Với dữ liệu ví dụ, document không khớp vì offer của Store A có giá 120.

Nếu đổi điều kiện seller thành Store B, document sẽ khớp vì offer Store B có giá 95.

### Nested path phải chính xác

path là tên nested field trong mapping. Nếu nested object lồng nhau, query phải dùng đúng path và có thể cần nested query lồng nhau theo cấu trúc mapping.

Không thể dùng nested query trên một field được mapping là object thông thường. Elasticsearch cần mapping type nested để tạo và truy vấn các nested Lucene document.

## 7. Nested trong Spring Data Elasticsearch

Có thể ánh xạ nested field bằng FieldType.Nested:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;

        @Field(type = FieldType.Nested)
        private List<Offer> offers;
    }

    public class Offer {

        private String seller;
        private Double price;
        private Boolean available;
    }

Annotation này cho Spring Data biết field offers cần được tạo mapping nested thay vì object thông thường.

Một số dự án quản lý index mapping bằng template hoặc JSON riêng thay vì tạo mapping từ entity. Trong trường hợp đó, cần bảo đảm mapping thực tế trên cluster có type nested. Chỉ đổi annotation mà không tạo lại mapping của index đã tồn tại không tự chuyển object thành nested.

Nếu đổi field hiện tại từ object sang nested, thông thường cần tạo index mới và reindex dữ liệu vì mapping type của field không thể thay đổi trực tiếp theo cách này.

## 8. Nested query bằng NativeQuery

Spring Data Elasticsearch hiện đại có thể xây dựng nested query qua NativeQuery và Elasticsearch Java API Client:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .nested(n -> n
                .path("offers")
                .query(nq -> nq
                    .bool(b -> b
                        .must(m -> m
                            .term(t -> t
                                .field("offers.seller")
                                .value(FieldValue.of("Store B"))
                            )
                        )
                        .must(m -> m
                            .range(r -> r
                                .number(num -> num
                                    .field("offers.price")
                                    .lt(100.0)
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

Ví dụ dùng:

    import co.elastic.clients.elasticsearch._types.FieldValue;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Tên overload và kiểu range builder phụ thuộc phiên bản Elasticsearch Java API Client. Điểm quan trọng là toàn bộ điều kiện seller và price được đặt bên trong cùng nested query với path offers.

Nếu đưa term seller và range price ra hai nested query độc lập, mỗi query có thể khớp một phần tử offers khác nhau. Khi yêu cầu là cùng một offer phải thỏa tất cả điều kiện, hãy đặt chúng trong cùng một nested query và bool.

## 9. inner_hits: lấy phần tử nested đã khớp

Nested query mặc định trả về document cha. Nếu giao diện cần biết chính xác offer nào khớp, có thể dùng inner_hits:

    GET products/_search
    {
      "query": {
        "nested": {
          "path": "offers",
          "query": {
            "bool": {
              "must": [
                {
                  "term": {
                    "offers.seller": "Store B"
                  }
                },
                {
                  "range": {
                    "offers.price": {
                      "lt": 100
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

inner_hits trả các nested document khớp theo từng parent hit. Nó hữu ích khi cần hiển thị đúng offer, comment hoặc variant khiến sản phẩm được tìm thấy.

Cần giới hạn size của inner_hits. Nếu mỗi parent có rất nhiều nested object và request trả nhiều inner hit, response có thể tăng đáng kể.

Spring Data có thể trả inner hits trong metadata của SearchHit theo API tương ứng phiên bản. Nếu cần xử lý chi tiết, kiểm tra kiểu SearchHit và cấu trúc inner hits của Elasticsearch Java API Client.

## 10. Nested aggregation

Khi cần thống kê trên nested object, dùng nested aggregation để đi vào nested path:

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "offers": {
          "nested": {
            "path": "offers"
          },
          "aggs": {
            "average_offer_price": {
              "avg": {
                "field": "offers.price"
              }
            },
            "by_seller": {
              "terms": {
                "field": "offers.seller"
              }
            }
          }
        }
      }
    }

Nested aggregation chuyển phạm vi aggregation từ document cha sang nested document. Vì vậy, doc_count trong nested bucket đếm nested object, không phải số product cha.

Nếu cần quay lại phạm vi document cha, có thể dùng reverse_nested aggregation:

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "offers": {
          "nested": {
            "path": "offers"
          },
          "aggs": {
            "by_seller": {
              "terms": {
                "field": "offers.seller"
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

parent_products đếm các document cha có nested object tương ứng. Phân biệt rõ số nested object và số parent document khi trình bày thống kê.

## 11. Nested sort

Có thể sort document cha theo giá thấp nhất trong nested offers:

    GET products/_search
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

Nested sort cần chỉ định nested path. Có thể thêm filter trong nested sort nếu chỉ muốn xét offer đáp ứng điều kiện, ví dụ chỉ tính giá của offer còn hàng.

Spring Data Sort thông thường không biểu diễn đầy đủ mọi tùy chọn nested sort. Với nested path, filter hoặc mode phức tạp, có thể dùng native SortOptions của Elasticsearch Java API Client và gắn vào NativeQuery.

## 12. Chi phí và giới hạn của nested

Nested giữ quan hệ chính xác, nhưng có chi phí:

- Mỗi nested object được index thành Lucene document riêng ngoài document cha.
- Một document có nhiều nested object làm tăng số Lucene document.
- Update một phần nested thường dẫn đến việc index lại document cha cùng nested data.
- Nested query, nested aggregation và nested sort phức tạp hơn query trên field phẳng.
- Số lượng nested field và nested object có giới hạn cấu hình của Elasticsearch.

Nếu một product có vài chục variant và thường xuyên cần điều kiện nhiều field trên cùng variant, nested có thể phù hợp. Nếu một document có hàng chục nghìn nested object và các object thay đổi liên tục, cần cân nhắc mô hình khác.

Không nên dùng nested chỉ vì JSON có object array. Hãy dùng nested khi việc giữ quan hệ giữa field trong cùng phần tử là yêu cầu truy vấn thực sự.

## 13. Parent-child là gì?

Parent-child là quan hệ giữa các document riêng biệt trong cùng một Elasticsearch index. Mapping sử dụng field type join để định nghĩa tên quan hệ giữa loại parent và child.

Ví dụ một question có nhiều answer:

    PUT qa
    {
      "mappings": {
        "properties": {
          "relation": {
            "type": "join",
            "relations": {
              "question": "answer"
            }
          },
          "title": {
            "type": "text"
          },
          "body": {
            "type": "text"
          }
        }
      }
    }

Parent document:

    PUT qa/_doc/q-1
    {
      "title": "How does nested query work?",
      "relation": "question"
    }

Child document:

    PUT qa/_doc/a-1?routing=q-1
    {
      "body": "A nested query scopes matching to one nested object.",
      "relation": {
        "name": "answer",
        "parent": "q-1"
      }
    }

Parent và child là document riêng, có ID riêng, nhưng phải nằm cùng shard. Vì vậy, khi index child, routing thường phải dùng ID của parent. Query và delete child cũng cần routing đúng để Elasticsearch tìm đúng shard.

Join field không phải foreign key tổng quát như trong relational database. Nó chỉ hỗ trợ quan hệ parent-child trong cùng một index và có chi phí join khi query.

## 14. Khi nào parent-child phù hợp?

Parent-child hữu ích khi:

- Parent và child có vòng đời cập nhật tương đối độc lập.
- Một parent có thể có rất nhiều child.
- Cần truy vấn child riêng hoặc tìm parent dựa trên điều kiện của child.
- Không muốn reindex toàn bộ parent mỗi khi thêm hoặc sửa child.
- Cần giữ document parent và child riêng nhưng vẫn join được trong Elasticsearch.

Ví dụ:

- Một câu hỏi có rất nhiều câu trả lời.
- Một bài viết có nhiều comment được thêm thường xuyên.
- Một sản phẩm có nhiều review độc lập.
- Một tài khoản có nhiều sự kiện hoặc bản ghi con được cập nhật riêng.

Parent-child không phải lựa chọn mặc định cho mọi quan hệ một-nhiều. Join query có chi phí đáng kể hơn query thông thường; nếu child luôn được đọc cùng parent và cập nhật ít, embedded hoặc nested thường đơn giản hơn.

## 15. Routing và cùng shard

Parent và child phải nằm cùng shard để Elasticsearch thực hiện join. Khi index child, routing phải xác định shard giống parent. Thông thường dùng parent ID làm routing:

    PUT qa/_doc/a-2?routing=q-1
    {
      "body": "Another answer",
      "relation": {
        "name": "answer",
        "parent": "q-1"
      }
    }

Nếu quên routing, child có thể được ghi vào shard khác và quan hệ không hoạt động đúng. Tương tự, các thao tác lấy hoặc xóa child cần routing phù hợp.

Khi dùng custom routing, cần duy trì cùng quy tắc trong mọi đường ghi và đọc. Có thể bật yêu cầu routing trên mapping hoặc tầng ứng dụng để giảm rủi ro quên routing.

Một parent có nhiều child không có nghĩa các child được phân bố tự do trên toàn cluster. Chúng tập trung cùng shard với parent, điều này có thể tạo mất cân bằng nếu một parent có số child rất lớn.

## 16. has_child và has_parent query

has_child tìm parent document dựa trên điều kiện của child:

    GET qa/_search
    {
      "query": {
        "has_child": {
          "type": "answer",
          "query": {
            "match": {
              "body": "nested query"
            }
          }
        }
      }
    }

Query trả về question có ít nhất một answer khớp nội dung nested query.

has_parent làm chiều ngược lại: tìm child document dựa trên điều kiện của parent:

    GET qa/_search
    {
      "query": {
        "has_parent": {
          "parent_type": "question",
          "query": {
            "match": {
              "title": "nested query"
            }
          }
        }
      }
    }

Query trả về answer thuộc question có title phù hợp.

Có thể cấu hình score_mode cho has_child để quyết định cách score của child ảnh hưởng đến parent. Với has_parent, có thể cấu hình parent score có được truyền xuống child hay không theo API hỗ trợ. Nếu chỉ cần điều kiện tồn tại, không nhất thiết phải bật scoring join.

## 17. Parent-child trong Spring Data Elasticsearch

Spring Data Elasticsearch hỗ trợ join field mapping qua các kiểu và annotation dành cho quan hệ join, nhưng chữ ký chính xác phụ thuộc phiên bản Spring Data. Cần bảo đảm mapping cuối cùng trên index có field type join và quan hệ đúng như cấu trúc Elasticsearch.

Ví dụ mapping JSON là nguồn rõ ràng để hiểu cấu trúc:

    {
      "properties": {
        "relation": {
          "type": "join",
          "relations": {
            "question": "answer"
          }
        }
      }
    }

Trong model Java, cần biểu diễn giá trị join gồm tên relation và parent ID đối với child. Spring Data có abstraction JoinField và annotation JoinType/JoinField ở những phiên bản hỗ trợ. Hãy xem API thực tế của dependency dự án để khai báo property, tên field, relation và parent value chính xác.

Không nên dùng một String parentId đơn giản rồi kỳ vọng Spring Data tự chuyển thành join relation nếu mapping không được cấu hình. Join field có cấu trúc riêng và child document cần parent ID cùng routing.

Khi ghi parent và child bằng ElasticsearchOperations hoặc repository, hãy kiểm tra request cuối cùng có routing đúng. Nếu abstraction repository không cho phép truyền routing trong use case cụ thể, dùng IndexQuery hoặc Java API Client request có routing tường minh.

## 18. NativeQuery cho has_child và has_parent

Ví dụ has_child bằng Elasticsearch Java API Client builder:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .hasChild(h -> h
                .type("answer")
                .query(childQuery -> childQuery
                    .match(m -> m
                        .field("body")
                        .query("nested query")
                    )
                )
                .scoreMode(ChildScoreMode.Max)
            )
        )
        .build();

Ví dụ has_parent:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .hasParent(h -> h
                .parentType("question")
                .query(parentQuery -> parentQuery
                    .match(m -> m
                        .field("title")
                        .query("nested query")
                    )
                )
                .score(true)
            )
        )
        .build();

Tên enum ChildScoreMode và builder method có thể thay đổi theo phiên bản Java API Client. Cần kiểm tra generated API của dependency dự án. Các ví dụ tập trung vào cấu trúc: has_child chỉ định child relation type; has_parent chỉ định parent type và query tương ứng.

Join query cần mapping join field hợp lệ. Chỉ viết NativeQuery mà không có join mapping và routing đúng sẽ không tạo ra quan hệ parent-child.

## 19. Chi phí và giới hạn của parent-child

Parent-child cho phép cập nhật document riêng nhưng phải trả giá bằng join query:

- has_child và has_parent có chi phí cao hơn query thông thường.
- Join được thực hiện trong phạm vi shard; routing ảnh hưởng đến phân bố dữ liệu.
- Nhiều child của một parent tập trung cùng shard và có thể tạo hotspot.
- Join field làm tăng metadata và chi phí quản lý quan hệ.
- Quan hệ parent-child chỉ hỗ trợ trong cùng index.
- Một document chỉ có một parent trong quan hệ join tương ứng.
- Mapping join có thể mô tả nhiều cấp quan hệ, nhưng cây quan hệ sâu làm truy vấn và vận hành phức tạp hơn.

Nếu ứng dụng thường xuyên truy vấn child rồi hiển thị parent, cần benchmark join query với dữ liệu và số shard thực tế. Không nên chọn parent-child chỉ để tránh việc cập nhật một document lớn nếu query join sẽ xuất hiện trong hầu hết request.

## 20. Liên kết ở tầng ứng dụng là gì?

Một lựa chọn khác là lưu các thực thể trong index riêng và giữ ID tham chiếu trong document. Elasticsearch không thực hiện join tự động giữa hai index; service của ứng dụng điều phối các truy vấn rồi ghép dữ liệu.

Ví dụ:

Index products:

    {
      "productId": "p-100",
      "name": "Keyboard K8",
      "manufacturerId": "m-10"
    }

Index manufacturers:

    {
      "manufacturerId": "m-10",
      "name": "Keychron",
      "country": "China"
    }

Khi cần hiển thị product cùng manufacturer, service:

1. Tìm product.
2. Lấy manufacturerId từ kết quả.
3. Tìm manufacturer theo ID.
4. Ghép dữ liệu thành response DTO.

Có thể dùng repository findById hoặc findAllById để lấy dữ liệu tham chiếu. Nếu có nhiều ID, nên gom thành một lần multi-get hoặc terms query thay vì gọi một request cho mỗi product.

### Không có join tự động giữa index

Elasticsearch không cung cấp join query tổng quát giữa hai index giống SQL join. Một field manufacturerId trong product chỉ là dữ liệu tham chiếu. Ứng dụng phải tự tìm document manufacturer tương ứng.

Nếu cần filter product theo country của manufacturer, có thể:

- Denormalize country vào product để query một lần.
- Query manufacturers trước để lấy ID rồi query products bằng terms.
- Dùng hệ thống dữ liệu quan hệ bên ngoài làm nguồn truy vấn chính.
- Thiết kế lại document để chứa dữ liệu cần tìm cùng nhau.

Mỗi cách có tradeoff về độ trễ, tính nhất quán và kích thước index.

## 21. Liên kết ứng dụng với hai bước query

Giả sử cần tìm sản phẩm thuộc manufacturer ở China:

Bước 1, tìm ID manufacturer:

    GET manufacturers/_search
    {
      "_source": false,
      "query": {
        "term": {
          "country": "China"
        }
      },
      "fields": [
        "manufacturerId"
      ],
      "size": 1000
    }

Bước 2, tìm product theo danh sách ID:

    GET products/_search
    {
      "query": {
        "terms": {
          "manufacturerId": [
            "m-10",
            "m-12",
            "m-18"
          ]
        }
      }
    }

Trong ứng dụng, ID ở bước 1 được đưa vào terms query bước 2. Cần giới hạn số ID và xử lý trường hợp danh sách rỗng. Nếu số lượng manufacturer lớn, cách hai bước có thể tạo query terms rất lớn và tăng latency.

Nếu cần phân trang hoặc sort product theo thuộc tính manufacturer, phải thiết kế rõ việc phân trang ở bước nào. Lấy một tập manufacturer ID lớn rồi query product không tự tạo một phép join có sort toàn cục.

## 22. Denormalization: sao chép dữ liệu để tìm kiếm nhanh

Thay vì join ở mỗi request, ứng dụng có thể sao chép một số field cần thiết vào document product:

    {
      "productId": "p-100",
      "name": "Keyboard K8",
      "manufacturerId": "m-10",
      "manufacturerName": "Keychron",
      "manufacturerCountry": "China"
    }

Giờ đây, có thể tìm product theo manufacturerCountry trong một query:

    GET products/_search
    {
      "query": {
        "term": {
          "manufacturerCountry": "China"
        }
      }
    }

Denormalization thường phù hợp với search engine vì nó tối ưu read path: document chứa sẵn dữ liệu mà query cần.

Nhược điểm là khi manufacturer đổi tên hoặc quốc gia, nhiều product document có thể cần cập nhật. Ứng dụng cần cơ chế đồng bộ:

- Cập nhật đồng bộ trong service nếu số document ít và thao tác phù hợp.
- Phát event khi manufacturer thay đổi và cập nhật các product liên quan.
- Dùng outbox hoặc message queue để không mất sự kiện.
- Chấp nhận eventual consistency với khoảng trễ được xác định.
- Chạy job backfill khi cần sửa dữ liệu cũ.

Không cần sao chép toàn bộ manufacturer vào mọi product. Chỉ denormalize những field thực sự dùng để search, filter, sort hoặc hiển thị thường xuyên.

## 23. So sánh bốn cách mô hình hóa

| Tiêu chí | Embedded object | Nested | Parent-child | Liên kết ứng dụng |
|---|---|---|---|---|
| Lưu dữ liệu | Cùng document cha | Cùng document cha, nested Lucene docs | Document riêng cùng index | Document riêng, thường có thể ở index khác |
| Giữ quan hệ field trong một phần tử array | Không | Có | Có theo document child | Có trong từng document tham chiếu |
| Query liên quan | Query field object | Nested query | has_child/has_parent | Nhiều query và ghép ở service |
| Cập nhật dữ liệu con | Thường index lại cha | Thường index lại cha và nested data | Có thể cập nhật child riêng | Cập nhật document liên quan riêng |
| Join giữa parent và child | Không cần join | Nested query theo path | Join query trong shard | Ứng dụng tự ghép |
| Dữ liệu con rất lớn | Không lý tưởng nếu tăng vô hạn | Cần thận trọng | Có thể phù hợp hơn | Có thể phù hợp |
| Độ phức tạp query | Thấp | Trung bình | Cao hơn | Phụ thuộc service |
| Tính nhất quán | Một lần ghi document | Một lần ghi document | Nhiều document, cần quản lý quan hệ | Nhiều document/index, cần đồng bộ |
| Phù hợp | Thuộc tính con đơn giản | Mảng object cần giữ quan hệ | Child độc lập và cần join trong cùng index | Thực thể độc lập, dữ liệu nhiều nguồn hoặc cần kiểm soát ở ứng dụng |

## 24. Cách chọn mô hình theo access pattern

Thay vì bắt đầu từ câu hỏi dữ liệu có quan hệ một-nhiều hay không, hãy bắt đầu từ những query quan trọng nhất.

### Đọc parent cùng toàn bộ child

Nếu gần như mọi lần đọc đều lấy parent cùng child và child không quá lớn, embedded object thường là lựa chọn đơn giản. Nếu cần nhiều điều kiện cùng khớp trên một phần tử trong object array, chọn nested.

### Tìm parent theo thuộc tính của child

Nếu child là object con trong cùng document và cần điều kiện nhiều field cùng phần tử, nested query phù hợp. Nếu child là document riêng, có vòng đời riêng và cần join trong cùng index, cân nhắc parent-child.

### Cập nhật child thường xuyên và độc lập

Parent-child hoặc application-level references có thể tránh reindex toàn bộ parent khi một child thay đổi. Tuy nhiên, cần cân nhắc chi phí join hoặc số request ứng dụng phải thực hiện.

### Query qua nhiều loại dữ liệu hoặc nhiều index

Liên kết ở tầng ứng dụng thường linh hoạt hơn vì parent và child có thể nằm trong index khác nhau hoặc được lấy từ hệ thống khác. Nếu query cần filter/sort theo field tham chiếu thường xuyên, denormalize field đó vào document tìm kiếm.

### Dữ liệu con tăng không giới hạn

Không nên nhúng một danh sách có thể tăng mãi vào một document cha. Document lớn làm tăng chi phí update và có thể chạm giới hạn kích thước hoặc nested object. Tách child thành document riêng thường phù hợp hơn.

## 25. Vòng đời cập nhật và xóa

Mô hình quan hệ ảnh hưởng trực tiếp đến cách ứng dụng cập nhật dữ liệu.

| Thao tác | Embedded/object | Nested | Parent-child | Liên kết ứng dụng |
|---|---|---|---|---|
| Thêm child | Update/reindex parent | Update/reindex parent | Index child riêng | Index document tham chiếu riêng |
| Sửa child | Update parent | Update parent | Update child | Update child |
| Xóa child | Update parent | Update parent | Delete child có routing | Delete child document |
| Xóa parent | Xóa một document | Xóa parent và nested data cùng document | Cần chính sách xóa child liên quan | Cần xử lý reference/orphan |
| Đồng bộ nhiều bản sao | Không nếu dữ liệu chỉ nằm trong parent | Không nếu dữ liệu chỉ nằm trong parent | Quản lý quan hệ và routing | Quản lý event, backfill hoặc eventual consistency |

Với parent-child, xóa parent không nên được xem là tự động xóa mọi child trong mọi tình huống ứng dụng. Cần thiết kế thao tác xóa rõ ràng, dùng query theo parent/routing hoặc quy trình cleanup phù hợp.

Với application-level references, khi xóa một manufacturer, product có thể giữ manufacturerId không còn tồn tại. Cần chọn chính sách: xóa product, giữ reference để audit, đánh dấu manufacturer inactive hoặc cập nhật dữ liệu denormalized.

## 26. Tính nhất quán và giao dịch

Elasticsearch không phải relational database có transaction nhiều document tương đương SQL. Khi cập nhật parent và child riêng, hoặc cập nhật dữ liệu gốc cùng bản sao denormalized, có thể có khoảng thời gian dữ liệu chưa đồng bộ.

Các chiến lược thường dùng:

- **Một document duy nhất:** nhúng dữ liệu cần đọc cùng nhau để cập nhật trong một lần ghi.
- **Eventual consistency:** phát sự kiện và cập nhật các document liên quan sau đó.
- **Outbox pattern:** ghi thay đổi và event vào nguồn dữ liệu giao dịch, sau đó publish event để cập nhật Elasticsearch.
- **Version hoặc timestamp:** giữ thông tin phiên bản nguồn để phát hiện bản sao cũ.
- **Idempotent update:** xử lý event lặp mà không tạo trạng thái sai.
- **Reconciliation job:** định kỳ so sánh nguồn và index để sửa lệch dữ liệu.

Nếu ứng dụng yêu cầu tính nhất quán giao dịch mạnh giữa nhiều thực thể, nên cân nhắc giữ nguồn dữ liệu chính trong relational database hoặc hệ thống hỗ trợ transaction; Elasticsearch phục vụ search projection được cập nhật từ nguồn đó.

## 27. Routing và phân bố dữ liệu

Routing đặc biệt quan trọng với parent-child vì parent và child phải ở cùng shard. Với application-level references trên các index riêng, không có yêu cầu join cùng shard, nhưng vẫn có thể dùng routing theo tenant hoặc khóa nghiệp vụ để tối ưu query.

Routing tùy chỉnh có thể tạo lợi ích và rủi ro:

- Query theo routing có thể giảm số shard cần tìm.
- Một tenant hoặc parent quá lớn có thể tạo shard hotspot.
- Cần dùng routing nhất quán khi index, get, update và delete.
- Nếu alias trỏ nhiều index, phải bảo đảm routing semantics phù hợp ở mọi index.

Không nên chọn routing chỉ dựa trên một ví dụ query. Hãy xem phân phối dữ liệu, kích thước tenant, số child mỗi parent và concurrency.

## 28. Security và tenant isolation

Mô hình quan hệ không tự cung cấp authorization. Nếu document cha thuộc tenant A, child hoặc embedded data cũng phải được truy vấn theo đúng phạm vi tenant.

Một số nguyên tắc:

- Đặt tenant filter ở query cha và các truy vấn child độc lập.
- Không dựa vào parent ID do client gửi mà bỏ qua kiểm tra quyền.
- Với parent-child, kiểm tra routing và parent relation từ dữ liệu đáng tin cậy.
- Với application-level references, xác thực cả document tham chiếu và document đích.
- Nếu denormalize tenantId, cập nhật đồng bộ khi quan hệ thay đổi.
- Kiểm tra inner_hits và aggregation không trả dữ liệu thuộc tenant khác.

Một query nested trả document cha có thể bao gồm nested inner hits. Cần bảo đảm filter áp dụng đúng phạm vi và không để inner_hits lộ dữ liệu ngoài quyền truy cập.

## 29. Mẫu code Spring Data cho application-level references

Ví dụ entity product lưu manufacturerId:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;
        private String manufacturerId;
    }

Entity manufacturer:

    @Document(indexName = "manufacturers")
    public class Manufacturer {

        @Id
        private String id;

        private String name;
        private String country;
    }

Service ghép dữ liệu:

    @Service
    public class ProductCatalogService {

        private final ProductRepository productRepository;
        private final ManufacturerRepository manufacturerRepository;

        public ProductCatalogService(
                ProductRepository productRepository,
                ManufacturerRepository manufacturerRepository) {
            this.productRepository = productRepository;
            this.manufacturerRepository = manufacturerRepository;
        }

        public ProductView getProduct(String productId) {
            Product product = productRepository.findById(productId)
                .orElseThrow();

            Manufacturer manufacturer =
                manufacturerRepository.findById(product.getManufacturerId())
                    .orElse(null);

            return new ProductView(product, manufacturer);
        }
    }

Đây là cách đơn giản cho một product. Nếu lấy nhiều product, không nên gọi findById cho từng manufacturer vì tạo N+1 requests. Hãy gom ID duy nhất rồi dùng findAllById hoặc multi-get phù hợp:

    List<Product> products = productRepository.findAllById(productIds);

    Set<String> manufacturerIds = products.stream()
        .map(Product::getManufacturerId)
        .filter(Objects::nonNull)
        .collect(Collectors.toSet());

    Map<String, Manufacturer> manufacturers =
        StreamSupport.stream(
            manufacturerRepository.findAllById(manufacturerIds).spliterator(),
            false
        ).collect(Collectors.toMap(
            Manufacturer::getId,
            Function.identity()
        ));

Sau đó service ghép mỗi product với manufacturer tương ứng. Kiểu trả về repository và cách tối ưu multi-get phụ thuộc interface đang dùng, nhưng nguyên tắc là batch reference lookup thay vì request từng document.

## 30. Lựa chọn khi cần filter theo dữ liệu liên quan

Một quyết định quan trọng là ứng dụng có cần tìm parent theo thuộc tính child hoặc thuộc tính entity tham chiếu hay không.

| Nhu cầu | Mô hình thường phù hợp |
|---|---|
| Filter theo một field đơn giản trong embedded object | Object |
| Filter nhiều field phải thuộc cùng một phần tử array | Nested |
| Tìm parent có child thỏa điều kiện | Parent-child hoặc nested tùy vòng đời dữ liệu |
| Tìm child thuộc parent thỏa điều kiện | Parent-child |
| Filter product theo country của manufacturer | Denormalize country hoặc query hai bước |
| Hiển thị manufacturer khi đọc product | Application-level reference hoặc denormalize |
| Child thay đổi độc lập và thường xuyên | Parent-child hoặc application-level reference |
| Quan hệ nằm ở nhiều index/hệ thống | Application-level reference |

Nếu một thuộc tính liên quan thường xuyên xuất hiện trong filter, sort hoặc relevance, denormalize field đó vào document tìm kiếm có thể đơn giản hóa query đáng kể.

## 31. Những lỗi thường gặp

### Dùng object array nhưng cần điều kiện cùng phần tử

Object array thông thường không giữ quan hệ giữa các field của từng phần tử khi index. Nếu seller và price phải cùng thuộc một offer, dùng nested query trên nested mapping.

### Nghĩ nested là document độc lập

Nested object được index riêng ở mức Lucene nhưng vẫn thuộc document cha. Nó không có vòng đời và ID độc lập như child document của parent-child.

### Đặt nested query trên object mapping

Nested query chỉ hoạt động với field được mapping type nested. Đổi mapping cần tạo index mới và reindex dữ liệu khi field trước đó là object.

### Quên nested path

Nested query, aggregation và sort cần đúng path. Field name có dấu chấm không tự làm query trở thành nested query.

### Tách điều kiện ra nhiều nested query khi cần cùng phần tử

Hai nested query riêng có thể khớp hai nested object khác nhau. Đặt các điều kiện cần đồng thời đúng trong cùng nested query.

### Dùng nested cho danh sách rất lớn và cập nhật liên tục

Nested object nằm trong document cha; cập nhật một phần tử thường yêu cầu index lại document cha. Với child độc lập và nhiều, cân nhắc parent-child hoặc application-level references.

### Dùng parent-child cho mọi quan hệ một-nhiều

Join query có chi phí và routing phức tạp. Nếu child luôn được đọc cùng parent, embedded hoặc nested thường đơn giản hơn.

### Quên routing của child

Parent và child phải cùng shard. Index child với routing theo parent ID và giữ cùng quy tắc khi get, update hoặc delete.

### Mong join field nối hai index

Join field chỉ hỗ trợ quan hệ parent-child trong cùng index. Liên kết giữa các index cần denormalization hoặc application-level lookup.

### Tạo N+1 requests khi ghép reference

Khi lấy nhiều parent, gom ID và batch lookup các document tham chiếu. Tránh gọi repository một lần cho mỗi document.

### Denormalize nhưng không có cơ chế đồng bộ

Khi dữ liệu nguồn thay đổi, bản sao trong index có thể cũ. Cần event, outbox, backfill hoặc reconciliation job.

### Cho rằng Elasticsearch có transaction nhiều document

Ghi parent, child và các bản sao denormalized là nhiều thao tác. Thiết kế retry, idempotency và eventual consistency nếu cần.

## 32. Quy trình chọn mô hình quan hệ

Có thể dùng quy trình sau khi thiết kế document:

1. Xác định dữ liệu con có luôn được đọc cùng parent hay không.
2. Xác định các điều kiện query có cần khớp trên cùng một phần tử array không.
3. Nếu không cần giữ quan hệ giữa field trong object array, dùng object.
4. Nếu cần giữ quan hệ từng phần tử và dữ liệu con gắn chặt với parent, dùng nested.
5. Nếu child là document riêng, cập nhật độc lập và cần join trong cùng index, đánh giá parent-child.
6. Nếu dữ liệu ở nhiều index/hệ thống hoặc ứng dụng muốn tự kiểm soát việc ghép, dùng application-level references.
7. Nếu query/filter/sort thường xuyên cần field tham chiếu, cân nhắc denormalize field cần thiết.
8. Đánh giá số lượng child, tần suất update, kích thước document và phân bố shard.
9. Thiết kế routing, cleanup, đồng bộ và xử lý dữ liệu mồ côi.
10. Viết query đại diện và benchmark trên dữ liệu gần production.

## Kết luận

Embedded object phù hợp với dữ liệu con đơn giản, được đọc cùng document cha và không cần giữ quan hệ giữa nhiều field trong từng phần tử array. Nested giữ ranh giới từng object con, cho phép nested query, aggregation, sort và inner_hits chính xác, nhưng nested data vẫn gắn với document cha và làm tăng chi phí index/update. Parent-child lưu parent và child thành document riêng trong cùng index, hỗ trợ cập nhật độc lập và join query, nhưng yêu cầu routing cùng shard và có chi phí truy vấn cao hơn. Liên kết ở tầng ứng dụng dùng ID tham chiếu rồi batch lookup và ghép dữ liệu, linh hoạt giữa nhiều index nhưng đòi hỏi service quản lý số request và tính nhất quán.

Trong Spring Data Elasticsearch, object và nested thường được biểu diễn bằng FieldType.Object và FieldType.Nested; parent-child cần join field mapping cùng giá trị relation/parent và routing chính xác; application-level references thường là ID field và repository hoặc ElasticsearchOperations lookup. Hãy chọn theo access pattern, tần suất cập nhật, số lượng child và yêu cầu query. Nếu dữ liệu liên quan thường xuyên dùng để filter hoặc sort, denormalize những field cần thiết có thể giúp search đơn giản hơn, miễn là ứng dụng có quy trình đồng bộ rõ ràng.
