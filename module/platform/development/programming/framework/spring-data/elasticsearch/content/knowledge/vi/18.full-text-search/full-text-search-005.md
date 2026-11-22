# Bool query với must, should, must_not và filter

Bool query là cách Elasticsearch kết hợp nhiều điều kiện tìm kiếm trong cùng một truy vấn. Nó cho phép yêu cầu một số điều kiện phải khớp, một số điều kiện chỉ đóng vai trò tăng điểm phù hợp, loại bỏ những document không được chấp nhận và áp dụng các bộ lọc không cần tính điểm relevance.

Spring Data Elasticsearch hỗ trợ Bool Query thông qua nhiều cách xây dựng query, phổ biến nhất là NativeQuery với Elasticsearch Java Client, hoặc JSON DSL khai báo bằng @Query trên repository. CriteriaQuery cũng biểu diễn được nhiều điều kiện thông thường, nhưng khi cần kiểm soát rõ must, should, must_not, filter và minimum_should_match, NativeQuery thường thể hiện ý định chính xác hơn.

Bốn clause cần phân biệt:

- **must:** document bắt buộc phải khớp; điều kiện tham gia tính điểm relevance.
- **filter:** document bắt buộc phải khớp; điều kiện không tham gia tính điểm relevance.
- **should:** điều kiện lựa chọn hoặc tăng điểm; mức độ bắt buộc phụ thuộc minimum_should_match và cấu trúc bool.
- **must_not:** document không được khớp; dùng để loại kết quả và không tính điểm relevance.

Hiểu đúng ý nghĩa của từng clause là điều quan trọng nhất. Một truy vấn có thể chạy thành công nhưng trả về kết quả sai nếu dùng should với mặc định không như mong đợi hoặc đặt một điều kiện lọc vào sai nhóm.

## 1. Bool query là gì?

Bool query kết hợp các truy vấn con theo logic Boolean. Mỗi truy vấn con có thể là term, match, range, exists, nested hoặc một bool query khác.

Ví dụ một trang tìm kiếm sản phẩm cần:

- Tên sản phẩm phải liên quan đến cụm từ người dùng nhập.
- Sản phẩm phải thuộc danh mục electronics.
- Giá nằm trong khoảng từ 100 đến dưới 500.
- Sản phẩm không được có trạng thái discontinued.
- Sản phẩm có thương hiệu ưu tiên sẽ được xếp hạng cao hơn.

Biểu thức nghiệp vụ:

~~~text
MATCH name
AND category = electronics
AND 100 <= price < 500
AND NOT status = discontinued
OPTIONAL boost when brand = preferred
~~~

Bool query giúp chia các điều kiện trên thành những nhóm có ý nghĩa:

~~~text
bool
  ├── must
  │     └── match name
  ├── filter
  │     ├── term category
  │     └── range price
  ├── must_not
  │     └── term status = discontinued
  └── should
        └── term brand = preferred
~~~

Các clause có thể chứa nhiều query con. Elasticsearch kết hợp chúng theo ngữ nghĩa của từng clause, không đơn thuần ghép chuỗi điều kiện theo thứ tự xuất hiện.

## 2. Vai trò của must

must chứa các điều kiện bắt buộc phải khớp. Nếu bool query có nhiều điều kiện must, document phải khớp tất cả các điều kiện đó.

Ví dụ:

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
          "match": {
            "description": "office equipment"
          }
        }
      ]
    }
  }
}
~~~

Document phải khớp cả truy vấn tên và mô tả. Các query trong must cũng tham gia tính score, vì vậy mức độ khớp có thể ảnh hưởng thứ tự kết quả.

### 2.1. Khi nào dùng must?

Dùng must khi điều kiện vừa bắt buộc vừa có ý nghĩa về relevance. Ví dụ:

- Từ khóa người dùng nhập phải xuất hiện trong tiêu đề hoặc nội dung.
- Tên sản phẩm phải liên quan đến cụm từ tìm kiếm.
- Nội dung bài viết phải khớp truy vấn toàn văn.

Với truy vấn match, score giúp xếp document phù hợp hơn lên trước. Đây là lý do thường đặt điều kiện full-text trong must.

### 2.2. Nhiều điều kiện must là AND

Ví dụ:

~~~json
{
  "bool": {
    "must": [
      { "term": { "status": "published" } },
      { "term": { "language": "vi" } }
    ]
  }
}
~~~

Kết quả phải có status là published và language là vi. Tuy nhiên, nếu các điều kiện chỉ là ràng buộc chính xác, không cần tính điểm relevance, filter thường phù hợp hơn.

## 3. Vai trò của filter

filter cũng là điều kiện bắt buộc phải khớp, nhưng chạy trong filter context và không đóng góp vào score. Đây là lựa chọn phù hợp cho những điều kiện lọc có tính cấu trúc.

Ví dụ:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "electronics"
          }
        },
        {
          "term": {
            "available": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 100,
              "lt": 500
            }
          }
        }
      ]
    }
  }
}
~~~

Document phải khớp match name và tất cả filter. Các filter không làm tăng hoặc giảm score của document.

### 3.1. Những điều kiện phù hợp với filter

Các điều kiện thường được đặt trong filter:

- Trạng thái như published, active hoặc archived.
- Danh mục, mã sản phẩm, tenant hoặc loại tài liệu.
- Cờ boolean như available hoặc enabled.
- Khoảng giá, số lượng hoặc thời gian.
- Điều kiện tồn tại field.
- Các ràng buộc quyền truy cập hoặc phạm vi dữ liệu do server xác định.

Filter giúp tách relevance khỏi các ràng buộc nghiệp vụ. Với một trang tìm kiếm, người dùng có thể nhập từ khóa để xếp hạng bằng score, còn bộ lọc danh mục, trạng thái và khoảng giá chỉ quyết định document nào được phép xuất hiện.

### 3.2. Filter không tính score

Một query đặt trong filter context chỉ xác định document có thỏa điều kiện hay không. Nó không được dùng để tăng điểm relevance. Vì vậy, nếu một điều kiện phải ảnh hưởng đến thứ tự kết quả, hãy cân nhắc đặt nó trong must hoặc should.

Filter context thường phù hợp với điều kiện chính xác và có thể tận dụng cơ chế cache của Elasticsearch trong các trường hợp thích hợp. Không nên giả định mọi filter đều chắc chắn được cache; việc cache phụ thuộc query, dữ liệu và trạng thái cluster.

### 3.3. must và filter đều bắt buộc, khác nhau ở scoring

| Tiêu chí | must | filter |
|---|---|---|
| Document phải khớp | Có | Có |
| Tính score | Có | Không |
| Phù hợp | Full-text, điều kiện cần ảnh hưởng relevance | Trạng thái, mã, danh mục, khoảng giá, ngày |
| Thứ tự kết quả | Có thể ảnh hưởng score | Không làm thay đổi score |

Đừng dùng must cho tất cả điều kiện chỉ vì chúng đều bắt buộc. Hãy phân biệt điều kiện tìm kiếm toàn văn với điều kiện lọc cấu trúc.

## 4. Vai trò của should

should chứa các điều kiện lựa chọn. Nó có hai cách sử dụng phổ biến:

1. Khi không có must hoặc filter, mặc định ít nhất một điều kiện should phải khớp.
2. Khi bool đã có must hoặc filter, các điều kiện should mặc định có thể chỉ đóng vai trò tăng score và không bắt buộc khớp.

Quy tắc mặc định này là nguồn gây lỗi thường gặp nhất khi viết Bool Query.

### 4.1. should như một nhóm OR bắt buộc

Ví dụ tìm sản phẩm thuộc danh mục books hoặc games:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "term": {
            "category": "books"
          }
        },
        {
          "term": {
            "category": "games"
          }
        }
      ]
    }
  }
}
~~~

Vì bool chỉ có should, ít nhất một nhánh phải khớp. Có thể khai báo tường minh:

~~~json
{
  "query": {
    "bool": {
      "should": [
        { "term": { "category": "books" } },
        { "term": { "category": "games" } }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

minimum_should_match làm rõ rằng ít nhất một điều kiện should phải khớp.

### 4.2. should như điều kiện tăng điểm

Giả sử mọi sản phẩm đều phải khớp từ khóa và thuộc danh mục electronics. Nếu thương hiệu là Acme, sản phẩm được ưu tiên hơn:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "electronics"
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": "Acme"
          }
        }
      ]
    }
  }
}
~~~

Trong cấu trúc này, must và filter đã có điều kiện bắt buộc. Mặc định should không bắt buộc khớp; nó có thể tăng score cho sản phẩm thuộc thương hiệu Acme. Sản phẩm của thương hiệu khác vẫn có thể xuất hiện nếu thỏa must và filter.

Đây là cách dùng should để boost relevance mà không loại các kết quả khác.

### 4.3. Khi muốn should bắt buộc dù có must/filter

Nếu nghiệp vụ yêu cầu vừa khớp must/filter, vừa phải khớp ít nhất một nhánh should, hãy đặt minimum_should_match:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "electronics"
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": "Acme"
          }
        },
        {
          "term": {
            "brand": "Contoso"
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

Document phải khớp ít nhất một trong hai thương hiệu, đồng thời phải thỏa must và filter.

### 4.4. Quy tắc mặc định của should

| Các clause trong bool | Mặc định minimum_should_match |
|---|---:|
| Chỉ có should | 1 |
| Có must hoặc filter cùng should | 0 |
| Không có should | Không áp dụng |

Nếu logic nghiệp vụ phụ thuộc vào việc should có bắt buộc hay không, nên khai báo minimum_should_match tường minh thay vì dựa vào mặc định.

## 5. Vai trò của must_not

must_not chứa các điều kiện mà document không được khớp. Nếu document khớp bất kỳ query con nào trong must_not, document bị loại khỏi kết quả.

Ví dụ loại sản phẩm đã ngừng kinh doanh:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "term": {
            "status": "discontinued"
          }
        }
      ]
    }
  }
}
~~~

Có thể kết hợp must_not với must và filter:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "laptop"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "available": true
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "status": "discontinued"
          }
        },
        {
          "term": {
            "visibility": "private"
          }
        }
      ]
    }
  }
}
~~~

Kết quả phải khớp tên, phải available và không được discontinued hoặc private.

### 5.1. must_not không tính score

must_not là điều kiện loại trừ. Nó không làm tăng hoặc giảm score của document được giữ lại. Nếu cần một điều kiện có ảnh hưởng tích cực đến relevance, hãy dùng must hoặc should tùy yêu cầu.

### 5.2. Document thiếu field khi dùng must_not

Một điểm quan trọng: document không có field thường không khớp một term query trên field đó. Vì vậy, khi term query được đặt trong must_not, document thiếu field có thể vẫn được giữ lại.

Ví dụ:

~~~json
{
  "bool": {
    "must_not": [
      {
        "term": {
          "status": "deleted"
        }
      }
    ]
  }
}
~~~

Truy vấn loại document có status bằng deleted. Document không có status cũng không khớp term status=deleted, do đó vẫn có thể xuất hiện.

Nếu nghiệp vụ yêu cầu status phải tồn tại và không phải deleted, hãy thêm exists vào filter:

~~~json
{
  "bool": {
    "filter": [
      {
        "exists": {
          "field": "status"
        }
      }
    ],
    "must_not": [
      {
        "term": {
          "status": "deleted"
        }
      }
    ]
  }
}
~~~

Đừng nhầm “không có giá trị bị cấm” với “có giá trị hợp lệ”. Đây là hai quy tắc dữ liệu khác nhau.

## 6. Kết hợp bốn clause trong một truy vấn

Ví dụ hoàn chỉnh cho trang tìm kiếm sản phẩm:

- Tên hoặc mô tả phải liên quan đến cụm từ tìm kiếm.
- Danh mục phải là electronics.
- Giá nằm trong khoảng từ 100 đến dưới 500.
- Sản phẩm phải available.
- Sản phẩm không được discontinued hoặc private.
- Thương hiệu Acme hoặc Contoso được ưu tiên về score.

Query DSL:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless keyboard",
            "fields": ["name^3", "description"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "electronics"
          }
        },
        {
          "term": {
            "available": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 100,
              "lt": 500
            }
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": "Acme"
          }
        },
        {
          "term": {
            "brand": "Contoso"
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "status": "discontinued"
          }
        },
        {
          "term": {
            "visibility": "private"
          }
        }
      ]
    }
  }
}
~~~

Ở đây should chỉ dùng để ưu tiên thương hiệu. Vì bool đã có must và filter, sản phẩm không thuộc Acme hoặc Contoso vẫn có thể xuất hiện nếu thỏa các điều kiện bắt buộc. Nếu nghiệp vụ chỉ cho phép hai thương hiệu này, thêm minimum_should_match: 1.

## 7. Quy tắc kết hợp logic và nhóm bool lồng nhau

Bool query có thể lồng nhau để thể hiện các biểu thức có ngoặc. Mỗi bool con có quy tắc must, should, filter và must_not độc lập.

Giả sử yêu cầu:

~~~text
status = published
AND
(
    category = books
    OR
    (category = games AND featured = true)
)
AND NOT discontinued
~~~

Có thể biểu diễn:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "published"
          }
        },
        {
          "bool": {
            "should": [
              {
                "term": {
                  "category": "books"
                }
              },
              {
                "bool": {
                  "filter": [
                    {
                      "term": {
                        "category": "games"
                      }
                    },
                    {
                      "term": {
                        "featured": true
                      }
                    }
                  ]
                }
              }
            ],
            "minimum_should_match": 1
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "discontinued": true
          }
        }
      ]
    }
  }
}
~~~

Nhóm bool con thứ hai chỉ khớp khi category là games và featured là true. Bool cha yêu cầu một trong hai nhánh should khớp. minimum_should_match được đặt tường minh để giữ đúng ý nghĩa OR.

### 7.1. Đừng dựa vào thứ tự xuất hiện của clause

Bool query không hoạt động như một danh sách lệnh tuần tự. Vị trí clause trong JSON không tạo ra thứ tự thực thi logic giống một chuỗi if trong Java. Hãy thiết kế nhóm theo ý nghĩa Boolean và dùng bool con để thể hiện ngoặc.

### 7.2. Dùng should cho nhiều cách khớp văn bản

Một ví dụ khác là tìm bài viết theo tiêu đề hoặc nội dung:

~~~json
{
  "bool": {
    "should": [
      {
        "match": {
          "title": {
            "query": "spring data elasticsearch",
            "boost": 3
          }
        }
      },
      {
        "match": {
          "content": "spring data elasticsearch"
        }
      }
    ],
    "minimum_should_match": 1
  }
}
~~~

Document chỉ cần khớp tiêu đề hoặc nội dung. Tiêu đề có boost cao hơn nên một kết quả khớp tiêu đề có thể được xếp hạng cao hơn kết quả chỉ khớp nội dung.

## 8. minimum_should_match chi tiết hơn

minimum_should_match quy định số hoặc tỷ lệ điều kiện should tối thiểu phải khớp. Nó có thể nhận một số nguyên, phần trăm hoặc biểu thức điều kiện.

Ví dụ:

| Giá trị | Ý nghĩa |
|---|---|
| 1 | Ít nhất một should phải khớp |
| 2 | Ít nhất hai should phải khớp |
| 75% | Ít nhất 75% số should phải khớp |
| -1 | Cho phép thiếu một should |
| -25% | Cho phép thiếu 25% số should |

Với 4 điều kiện should:

- 75% yêu cầu ít nhất 3 điều kiện khớp.
- -25% cho phép thiếu 1 điều kiện, cũng yêu cầu 3 điều kiện khớp.

Với số lượng điều kiện khác, phần trăm dương và phần trăm âm có thể cho kết quả làm tròn khác nhau. Hãy kiểm tra tài liệu Elasticsearch và kiểm thử với số nhánh thực tế.

Có thể dùng biểu thức có điều kiện, ví dụ:

~~~json
{
  "bool": {
    "should": [
      { "term": { "tag": "java" } },
      { "term": { "tag": "spring" } },
      { "term": { "tag": "elasticsearch" } },
      { "term": { "tag": "search" } }
    ],
    "minimum_should_match": "2<-25% 9<-3"
  }
}
~~~

Biểu thức điều kiện cho phép thay đổi số lượng match tối thiểu theo tổng số clause should. Chỉ nên dùng dạng nâng cao khi yêu cầu tìm kiếm thực sự cần nó; với phần lớn use case, giá trị nguyên như 1 dễ hiểu và dễ kiểm thử hơn.

## 9. Dùng Bool Query trong Spring Data Elasticsearch với NativeQuery

Khi cần kiểm soát rõ bốn clause, NativeQuery là lựa chọn phù hợp trong các phiên bản Spring Data Elasticsearch sử dụng Elasticsearch Java Client.

Ví dụ entity:

~~~java
import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String brand;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    // constructors, getters and setters
}
~~~

Xây dựng NativeQuery:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

public SearchHits<Product> searchProducts(String text) {
    NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                    .must(m -> m.match(mm -> mm
                            .field("name")
                            .query(text)
                    ))
                    .filter(f -> f.term(t -> t
                            .field("category")
                            .value(FieldValue.of("electronics"))
                    ))
                    .filter(f -> f.term(t -> t
                            .field("available")
                            .value(FieldValue.of(true))
                    ))
                    .mustNot(mn -> mn.term(t -> t
                            .field("status")
                            .value(FieldValue.of("discontinued"))
                    ))
                    .should(s -> s.term(t -> t
                            .field("brand")
                            .value(FieldValue.of("Acme"))
                    ))
            ))
            .build();

    return operations.search(query, Product.class);
}
~~~

Đoạn code minh họa builder API của Elasticsearch Java Client được Spring Data Elasticsearch sử dụng. Package NativeQuery, kiểu FieldValue và một số overload có thể khác theo release train; hãy kiểm tra dependency và Javadoc của phiên bản dự án trước khi áp dụng nguyên văn.

Trong ví dụ, should chỉ tăng điểm cho thương hiệu Acme vì bool đã có must và filter. Nếu chỉ muốn kết quả của Acme, cần thêm minimum_should_match("1") vào BoolQuery builder.

### 9.1. Thêm minimum_should_match trong NativeQuery

Ví dụ:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("name")
                        .query(text)
                ))
                .should(s -> s.term(t -> t
                        .field("brand")
                        .value(FieldValue.of("Acme"))
                ))
                .should(s -> s.term(t -> t
                        .field("brand")
                        .value(FieldValue.of("Contoso"))
                ))
                .minimumShouldMatch("1")
        ))
        .build();
~~~

Khi đó, ngoài việc phải khớp tên, document phải khớp ít nhất một trong hai thương hiệu.

## 10. Dùng Bool Query trong repository với @Query

Nếu cấu trúc query cố định và chỉ thay một vài giá trị, có thể khai báo JSON DSL bằng @Query:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "bool": {
            "must": [
              {
                "match": {
                  "name": "?0"
                }
              }
            ],
            "filter": [
              {
                "term": {
                  "category": "?1"
                }
              }
            ],
            "must_not": [
              {
                "term": {
                  "status": "discontinued"
                }
              }
            ]
          }
        }
        """)
    List<Product> searchAvailableProducts(String text, String category);
}
~~~

Đây là cách biểu diễn phù hợp khi DSL ít thay đổi. Với query có nhiều nhánh điều kiện tùy chọn, nhiều nhóm bool hoặc logic nghiệp vụ thay đổi theo request, xây dựng NativeQuery trong service thường dễ đọc và dễ kiểm thử hơn.

Nếu repository method cần phân trang, có thể kết hợp Pageable theo hỗ trợ của phiên bản. Pageable điều khiển phân trang; không đặt nó vào JSON Bool Query như một placeholder thông thường.

## 11. Dùng CriteriaQuery hay NativeQuery?

CriteriaQuery hữu ích cho các điều kiện field phổ biến và các nhóm AND/OR cơ bản. NativeQuery phù hợp hơn khi cần kiểm soát chính xác cấu trúc bool, minimum_should_match, nested query, boost hoặc các tính năng DSL khác.

| Nhu cầu | Cách tiếp cận thường phù hợp |
|---|---|
| Một vài điều kiện bắt buộc trên field | CriteriaQuery hoặc NativeQuery |
| Bộ lọc động đơn giản | CriteriaQuery |
| must, filter, must_not và should rõ ràng | NativeQuery |
| should có minimum_should_match cụ thể | NativeQuery hoặc @Query JSON |
| Bool lồng nhiều cấp | NativeQuery |
| Query cố định, chỉ thay vài giá trị | @Query |
| Nested query, function score hoặc DSL đặc thù | NativeQuery |

Không có yêu cầu phải dùng một API cho mọi truy vấn. Chọn cách biểu diễn khiến logic dễ hiểu, dễ quan sát và dễ kiểm thử.

## 12. Mapping ảnh hưởng đến Bool Query

Bool query kết hợp các query con, nhưng từng query con vẫn chịu ảnh hưởng của mapping field.

| Field mapping | Query thường dùng | Ghi chú |
|---|---|---|
| text | match, multi_match | Phân tích văn bản theo analyzer |
| keyword | term, terms | So khớp giá trị chính xác |
| integer, long, double | range, term | Kiểu tham số phải phù hợp |
| date, date_nanos | range | Format và múi giờ phải rõ ràng |
| boolean | term | Dùng giá trị true/false |
| nested | nested query chứa bool | Phải dùng đúng path và mapping nested |

Ví dụ dùng term trên field text có thể không khớp toàn bộ chuỗi như người viết mong đợi vì field đã được analyzer tách token. Với mã, trạng thái hoặc danh mục, keyword thường phù hợp hơn. Với nội dung tìm kiếm toàn văn, match thường là lựa chọn đúng.

### 12.1. Nested query chứa Bool Query

Nếu một field được mapping là nested, điều kiện trên các thuộc tính của cùng một phần tử phải được đặt trong nested query:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "variants.color": "black"
              }
            },
            {
              "range": {
                "variants.stock": {
                  "gt": 0
                }
              }
            }
          ]
        }
      }
    }
  }
}
~~~

Truy vấn yêu cầu cùng một nested object có color là black và stock lớn hơn 0. Nếu variants là object thông thường thay vì nested, ngữ nghĩa truy vấn sẽ khác. Hãy xác nhận mapping trước khi xây nested bool query.

## 13. Những lỗi thường gặp

### 13.1. Dùng must cho mọi điều kiện

Điều này có thể làm các điều kiện lọc tham gia tính score không cần thiết. Hãy đặt từ khóa tìm kiếm trong must và các ràng buộc cấu trúc trong filter khi không cần score.

### 13.2. Nghĩ should luôn là OR bắt buộc

Khi bool có must hoặc filter, should mặc định có thể không bắt buộc khớp. Nếu cần ít nhất một nhánh, hãy khai báo minimum_should_match.

### 13.3. Dùng must_not nhưng quên field có thể thiếu

Document không có field bị phủ định có thể vẫn được giữ lại. Nếu field bắt buộc tồn tại, kết hợp exists trong filter.

### 13.4. Đặt minimum_should_match ở sai cấp

Nếu query có nhiều bool lồng nhau, minimum_should_match áp dụng cho nhóm should của bool chứa nó. Đặt ở bool cha không tự điều khiển should của bool con. Hãy đặt giá trị ở đúng nhóm cần ràng buộc.

### 13.5. Dùng term trên text

term không phân tích chuỗi đầu vào như match. Kiểm tra mapping và chọn query tương ứng.

### 13.6. Nhầm filter với must_not

filter yêu cầu document phải khớp. must_not yêu cầu document không được khớp. Hai clause có hướng logic ngược nhau.

### 13.7. Dùng should để boost nhưng vô tình biến thành điều kiện bắt buộc

Nếu bool chỉ có should, mặc định ít nhất một nhánh phải khớp. Nếu muốn mọi document được tìm bằng một query khác và chỉ boost theo should, hãy đặt must hoặc filter phù hợp trong bool.

### 13.8. Viết query lồng nhau quá sâu mà không kiểm tra DSL

Một bool query có thể hợp lệ về JSON nhưng nhóm logic sai. Hãy viết biểu thức Boolean trước, kiểm tra DSL được gửi và thử với dữ liệu có kết quả dự kiến rõ ràng.

## 14. Kiểm thử Bool Query

Nên kiểm thử từng clause riêng rồi mới kiểm thử query tổng hợp.

Ví dụ cho biểu thức:

~~~text
name matches "keyboard"
AND category = electronics
AND available = true
AND NOT status = discontinued
AND (brand = Acme OR brand = Contoso)
~~~

Bộ dữ liệu thử:

| Document | Name | Category | Available | Status | Brand | Kết quả |
|---|---|---|---|---|---|---|
| A | Wireless keyboard | electronics | true | active | Acme | Chọn |
| B | Office keyboard | electronics | true | active | Contoso | Chọn |
| C | Wireless keyboard | electronics | true | active | Other | Loại do nhóm OR |
| D | Wireless keyboard | books | true | active | Acme | Loại do category |
| E | Wireless keyboard | electronics | false | active | Acme | Loại do available |
| F | Wireless keyboard | electronics | true | discontinued | Acme | Loại do must_not |
| G | Wireless keyboard | electronics | true | active | thiếu | Loại nếu brand là should bắt buộc |

Với query chỉ dùng should để boost và không đặt minimum_should_match, document C có thể được giữ lại nhưng có score thấp hơn A hoặc B. Test cần phản ánh đúng chế độ should đang sử dụng.

Các điểm nên xác nhận:

1. Từng must thực sự bắt buộc khớp.
2. Từng filter thực sự loại document không phù hợp.
3. should có đúng mức bắt buộc và boost như mong muốn.
4. must_not loại đúng document.
5. Field thiếu được xử lý theo quy tắc nghiệp vụ.
6. Score và thứ tự kết quả hợp lý.
7. Query qua alias hoặc nhiều index có mapping tương thích.

### 14.1. Kiểm tra score

Khi cần hiểu vì sao một document đứng trước document khác, có thể dùng Explain API cho một document cụ thể hoặc profile query trong môi trường phù hợp. Không nên bật profile cho mọi truy vấn production vì nó tạo thêm chi phí.

Score chịu ảnh hưởng bởi các query trong query context như must và should. Filter và must_not không cộng điểm. Nếu score không phải yêu cầu nghiệp vụ, tránh làm query phức tạp chỉ để tối ưu thứ hạng không cần thiết.

## 15. Quy trình xây dựng truy vấn từ yêu cầu nghiệp vụ

Một cách làm rõ ràng:

1. Viết điều kiện bắt buộc thành danh sách riêng.
2. Phân loại điều kiện nào cần ảnh hưởng relevance và điều kiện nào chỉ lọc.
3. Liệt kê điều kiện loại trừ.
4. Xác định các lựa chọn OR và số nhánh tối thiểu phải khớp.
5. Đặt ngoặc bằng bool query lồng nhau khi cần.
6. Kiểm tra mapping từng field để chọn match, term, range, exists hoặc nested.
7. Xây dựng NativeQuery hoặc @Query phù hợp.
8. Kiểm tra DSL được gửi đến Elasticsearch.
9. Kiểm thử với document khớp, không khớp, thiếu field và các trường hợp biên.

Ví dụ phân loại:

| Yêu cầu | Clause |
|---|---|
| Tên liên quan từ khóa | must |
| Danh mục là electronics | filter |
| Giá trong khoảng hợp lệ | filter |
| Sản phẩm không discontinued | must_not |
| Ưu tiên thương hiệu Acme | should |
| Chỉ cho phép Acme hoặc Contoso | should + minimum_should_match = 1 |

## 16. Kết luận

Bool query kết hợp bốn nhóm điều kiện với ngữ nghĩa khác nhau. must và filter đều bắt buộc khớp, nhưng must tham gia tính relevance còn filter thì không. should tạo lựa chọn hoặc tăng score; khi bool có must hoặc filter, should mặc định có thể không bắt buộc khớp. must_not loại document khớp điều kiện bị cấm và không tính score.

minimum_should_match là tham số cần đặc biệt chú ý. Hãy đặt nó tường minh khi nghiệp vụ yêu cầu một hoặc nhiều nhánh should phải khớp. Khi biểu thức có ngoặc hoặc nhiều cấp logic, dùng bool query lồng nhau để giữ đúng phạm vi từng điều kiện.

Trong Spring Data Elasticsearch, NativeQuery phù hợp để xây dựng Bool Query bằng Elasticsearch Java Client; @Query phù hợp với DSL cố định. Dù chọn cách nào, hãy đối chiếu query với mapping, kiểm tra DSL thực tế và kiểm thử các trường hợp thiếu field, nhánh OR và điều kiện loại trừ.
