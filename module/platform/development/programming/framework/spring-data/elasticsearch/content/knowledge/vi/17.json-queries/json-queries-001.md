# StringQuery và biểu diễn Query DSL dạng JSON

## 1. StringQuery trong Spring Data Elasticsearch là gì?

Spring Data Elasticsearch cung cấp `Query` như một abstraction để mô tả điều kiện tìm kiếm. Một trong các cách triển khai abstraction này là **`StringQuery`**: lớp nhận một chuỗi JSON chứa Elasticsearch Query DSL và chuyển nó thành truy vấn mà `ElasticsearchOperations` có thể thực thi.

`StringQuery` phù hợp khi:

- Bạn đã có sẵn Query DSL từ tài liệu Elasticsearch hoặc từ một hệ thống khác.
- Điều kiện tìm kiếm có cấu trúc rõ ràng và muốn biểu diễn gần với JSON request của Elasticsearch.
- Criteria API không diễn đạt thuận tiện một số cấu trúc query.
- Muốn kiểm soát cụ thể các clause như `bool`, `must`, `filter`, `nested`, `range` hoặc `multi_match`.

Ví dụ đơn giản:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

Query query = new StringQuery("""
{
  "match": {
    "firstName": {
      "query": "Jack"
    }
  }
}
""");
~~~

Chuỗi JSON trên là một query clause của Elasticsearch. Spring Data sử dụng query đó khi gửi thao tác tìm kiếm.

Điểm cần nhớ: tham số của `StringQuery` là **phần Query DSL**, chẳng hạn object `match` hoặc `bool`. Không bọc nó thêm một lớp `"query"` như trong toàn bộ request body của endpoint `_search`.

## 2. Query DSL là gì?

Elasticsearch Query DSL là ngôn ngữ truy vấn dạng JSON. Một query mô tả điều kiện mà document phải đáp ứng để được trả về. Các query có thể được lồng vào nhau để tạo điều kiện phức tạp.

Một request tìm kiếm REST đầy đủ thường có dạng:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "name": "wireless headphones"
    }
  },
  "from": 0,
  "size": 20,
  "sort": [
    {
      "price": "asc"
    }
  ]
}
~~~

Trong request trên:

- `query` chứa điều kiện tìm kiếm.
- `from` và `size` xác định vị trí bắt đầu và số lượng kết quả.
- `sort` xác định thứ tự kết quả.

Khi dùng `StringQuery`, chỉ truyền nội dung của phần `query`:

~~~json
{
  "match": {
    "name": "wireless headphones"
  }
}
~~~

`from`, `size`, `sort`, source filtering và những tùy chọn thực thi khác được cấu hình qua các thuộc tính của đối tượng Spring Data `Query`, ví dụ `Pageable` hoặc `Sort`.

Sự phân biệt này giúp tránh lỗi phổ biến: truyền cả request body có `"query"` vào `StringQuery`, khiến Spring Data xử lý object đó như một query clause thay vì nội dung bên trong trường `query` của request.

## 3. Cấu trúc cơ bản của một query JSON

Một query clause thường có dạng:

~~~json
{
  "ten_query": {
    "field_name": "value"
  }
}
~~~

Ví dụ:

~~~json
{
  "term": {
    "category": "audio"
  }
}
~~~

Ở đây:

- `term` là loại query.
- `category` là field cần tìm.
- `audio` là giá trị so khớp.

Một query có thể chứa object cấu hình chi tiết hơn:

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

Trong ví dụ này, `gte` là lớn hơn hoặc bằng và `lte` là nhỏ hơn hoặc bằng. Document phù hợp khi giá nằm trong khoảng từ 500.000 đến 2.000.000.

Query cũng có thể kết hợp nhiều query con thông qua `bool`:

~~~json
{
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
          "category": "audio"
        }
      },
      {
        "range": {
          "price": {
            "lte": 2000000
          }
        }
      }
    ]
  }
}
~~~

Đây là cấu trúc JSON thường được truyền vào constructor của `StringQuery`.

## 4. Chuẩn bị entity và thực thi StringQuery

Giả sử ứng dụng có entity sản phẩm:

~~~java
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

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // Constructors, getters và setters
}
~~~

Dùng `ElasticsearchOperations` để thực thi:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> searchWirelessHeadphones() {
        Query query = new StringQuery("""
            {
              "match": {
                "name": {
                  "query": "wireless headphones"
                }
              }
            }
            """);

        return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products")
        );
    }
}
~~~

Ví dụ trên dùng từ khóa cố định để tập trung minh họa cách thực thi. Trong ứng dụng thực tế, hãy tạo chuỗi JSON từ dữ liệu tìm kiếm động theo cách an toàn như phần xây dựng query động bên dưới.

Lời gọi `operations.search(...)` nhận ba thông tin:

1. Đối tượng `Query`, ở đây là `StringQuery`.
2. Kiểu entity mà kết quả sẽ được ánh xạ thành, ở đây là `Product.class`.
3. `IndexCoordinates` xác định index hoặc alias được tìm kiếm.

Kết quả là `SearchHits<Product>`, có thể cung cấp danh sách document cùng metadata như ID, score, sort values và highlight fields.

## 5. Match query: tìm kiếm toàn văn

`match` là query thường dùng cho field kiểu `text`. Elasticsearch phân tích chuỗi tìm kiếm bằng search analyzer của field rồi so khớp các token đã được lập chỉ mục.

Ví dụ:

~~~json
{
  "match": {
    "name": {
      "query": "wireless headphones"
    }
  }
}
~~~

Có thể điều chỉnh cách match:

~~~json
{
  "match": {
    "name": {
      "query": "wireless headphones",
      "operator": "and",
      "minimum_should_match": "75%"
    }
  }
}
~~~

- `operator: "and"` yêu cầu các token truy vấn cùng xuất hiện theo semantics của match query.
- `operator: "or"` là hành vi mặc định phổ biến, cho phép khớp một trong các token.
- `minimum_should_match` điều chỉnh tỷ lệ hoặc số token cần khớp.

`match` phù hợp cho tìm kiếm văn bản tự nhiên. Không dùng nó thay cho `term` khi cần so khớp chính xác trên field keyword.

## 6. Term và terms query: so khớp chính xác

`term` tìm một giá trị đã được lập chỉ mục. Nó thường phù hợp với field `keyword`, mã, trạng thái và giá trị phân loại.

~~~json
{
  "term": {
    "category": "audio"
  }
}
~~~

`terms` nhận danh sách giá trị và khớp document có ít nhất một giá trị tương ứng:

~~~json
{
  "terms": {
    "category": [
      "audio",
      "video",
      "accessories"
    ]
  }
}
~~~

Ví dụ này tìm sản phẩm thuộc một trong ba danh mục.

Với field `text`, analyzer có thể biến đổi nội dung khi lập chỉ mục. Vì vậy, `term` với chuỗi gốc có thể không khớp như người viết mong đợi. Hãy kiểm tra mapping và kết quả Analyze API trước khi chọn toán tử.

## 7. Range query: tìm theo khoảng giá trị

`range` hỗ trợ các điều kiện lớn hơn, nhỏ hơn và giới hạn hai đầu:

~~~json
{
  "range": {
    "price": {
      "gte": 500000,
      "lt": 2000000
    }
  }
}
~~~

Các toán tử thường gặp:

| Toán tử | Ý nghĩa |
|---|---|
| `gt` | Lớn hơn |
| `gte` | Lớn hơn hoặc bằng |
| `lt` | Nhỏ hơn |
| `lte` | Nhỏ hơn hoặc bằng |

Với field ngày tháng, range query có thể dùng giá trị ngày và các biểu thức ngày tương đối được Elasticsearch hỗ trợ:

~~~json
{
  "range": {
    "createdAt": {
      "gte": "now-30d/d",
      "lt": "now"
    }
  }
}
~~~

Ví dụ tìm document được tạo trong khoảng 30 ngày gần đây, tính theo cách làm tròn ngày mà biểu thức `/d` chỉ định.

Range query cần field có kiểu dữ liệu phù hợp. Giá nên là numeric field, ngày nên là `date`, không nên dùng chuỗi keyword thông thường nếu cần so sánh số học hoặc thời gian.

## 8. Bool query: kết hợp nhiều điều kiện

`bool` là thành phần quan trọng để xây dựng query phức hợp. Nó có bốn nhóm clause chính:

| Clause | Vai trò | Tác động đến score |
|---|---|---|
| `must` | Điều kiện bắt buộc phải khớp | Có thể đóng góp vào score |
| `filter` | Điều kiện bắt buộc phải khớp | Không tính score |
| `should` | Điều kiện ưu tiên hoặc điều kiện khớp tùy cấu hình | Có thể đóng góp vào score |
| `must_not` | Điều kiện phải không khớp | Không tính score |

Ví dụ tìm sản phẩm có tên liên quan đến `wireless`, thuộc danh mục `audio`, giá tối đa 2.000.000 và đang hoạt động:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "wireless"
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "audio"
        }
      },
      {
        "range": {
          "price": {
            "lte": 2000000
          }
        }
      },
      {
        "term": {
          "active": true
        }
      }
    ],
    "must_not": [
      {
        "term": {
          "status": "DISCONTINUED"
        }
      }
    ]
  }
}
~~~

Trong ví dụ:

- `must` xác định nội dung tìm kiếm chính và có thể ảnh hưởng độ liên quan.
- `filter` giới hạn danh mục, giá và trạng thái hoạt động.
- `must_not` loại sản phẩm đã ngừng kinh doanh.

### Should và minimum_should_match

`should` có thể dùng để ưu tiên một số kết quả:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "headphones"
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
          "featured": true
        }
      }
    ],
    "minimum_should_match": 0
  }
}
~~~

Ở đây, sản phẩm có brand `Acme` hoặc được đánh dấu featured có thể nhận score cao hơn. `minimum_should_match: 0` cho phép document không khớp các nhánh should vẫn được trả về nếu đáp ứng must.

Nếu cần ít nhất một nhánh should phải khớp, đặt `minimum_should_match: 1`. Cần hiểu mặc định của `minimum_should_match` thay đổi theo việc bool query có must/filter hay không; khai báo rõ khi logic nghiệp vụ yêu cầu một số lượng nhánh cụ thể.

## 9. Multi-match query: tìm trên nhiều field

Khi người dùng nhập một cụm từ và muốn tìm trên nhiều thuộc tính văn bản, có thể dùng `multi_match`:

~~~json
{
  "multi_match": {
    "query": "wireless noise cancelling",
    "fields": [
      "name^3",
      "description",
      "brandName^2"
    ],
    "type": "best_fields"
  }
}
~~~

Trong đó:

- `query` là chuỗi tìm kiếm.
- `fields` là danh sách field cần tìm.
- `^3` và `^2` là boost, tăng mức ưu tiên cho field tương ứng.
- `best_fields` là một trong các kiểu multi-match, phù hợp khi một field khớp tốt có thể quyết định mức liên quan.

Có thể kết hợp `multi_match` với bool filter:

~~~json
{
  "bool": {
    "must": [
      {
        "multi_match": {
          "query": "wireless noise cancelling",
          "fields": [
            "name^3",
            "description"
          ]
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "audio"
        }
      }
    ]
  }
}
~~~

Boost giúp điều chỉnh thứ tự kết quả, không phải điều kiện bắt buộc. Nếu cần kiểm soát mức liên quan, hãy thử với bộ truy vấn đại diện và đánh giá kết quả thực tế.

## 10. Nested query: tìm trong object lồng nhau

Khi field được mapping là `nested`, query cần khai báo `nested` và `path` để xác định phạm vi object con.

Ví dụ document sản phẩm có các biến thể:

~~~json
{
  "variants": [
    {
      "color": "black",
      "size": "S",
      "stock": 0
    },
    {
      "color": "white",
      "size": "M",
      "stock": 12
    }
  ]
}
~~~

Mapping `variants` phải là `nested`. Query tìm biến thể vừa có màu đen vừa còn hàng:

~~~json
{
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
~~~

Hai điều kiện nằm trong cùng nested query nên phải khớp trên cùng một nested object. Document ví dụ không khớp vì biến thể màu đen có stock bằng 0.

Nếu field chỉ được mapping là `object`, Elasticsearch có thể làm phẳng các thuộc tính của mảng object và điều kiện ở hai object khác nhau có thể bị kết hợp ngoài ý muốn. Dùng nested query khi nghiệp vụ cần giữ tương quan giữa các thuộc tính của cùng một phần tử.

## 11. Tạo StringQuery cho điều kiện tìm kiếm thực tế

Sau khi hiểu các query clause, có thể ghép chúng thành một JSON Query DSL và truyền vào `StringQuery`.

Ví dụ tìm sản phẩm theo tên, danh mục và giá tối đa:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

Query query = new StringQuery("""
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "wireless headphones",
            "operator": "and"
          }
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "audio"
        }
      },
      {
        "range": {
          "price": {
            "lte": 2000000
          }
        }
      }
    ]
  }
}
""");
~~~

Có thể gắn phân trang qua constructor:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.query.StringQuery;

StringQuery query = new StringQuery(
    """
    {
      "bool": {
        "filter": [
          {
            "term": {
              "category": "audio"
            }
          }
        ]
      }
    }
    """,
    PageRequest.of(0, 20),
    Sort.by(Sort.Direction.ASC, "price")
);
~~~

`StringQuery` có các constructor nhận `source`, `source` cùng `Pageable`, hoặc `source` cùng `Pageable` và `Sort`. Các tùy chọn này thuộc Spring Data Query, không cần nhúng `from`, `size` hay `sort` vào chuỗi query clause.

## 12. Xây dựng JSON động an toàn

Trong ứng dụng thực tế, giá trị tìm kiếm thường đến từ request của người dùng. Không nên nối trực tiếp dữ liệu đầu vào vào chuỗi JSON:

~~~java
// Không nên làm theo cách này
String source = """
{
  "match": {
    "name": "%s"
  }
}
""".formatted(keyword);
~~~

Nếu `keyword` chứa dấu nháy, dấu gạch chéo hoặc nội dung có cấu trúc đặc biệt, JSON có thể không hợp lệ hoặc bị thay đổi ngoài ý muốn. Việc nối chuỗi cũng khiến code khó kiểm soát escape.

Một cách an toàn hơn là tạo cấu trúc Java rồi dùng JSON serializer để chuyển thành chuỗi. Ví dụ với Jackson `ObjectMapper`:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

public Query buildProductQuery(
        ObjectMapper objectMapper,
        String keyword,
        String category,
        Double maxPrice) throws JsonProcessingException {

    Map<String, Object> match = Map.of(
        "match",
        Map.of(
            "name",
            Map.of("query", keyword)
        )
    );

    List<Map<String, Object>> filters = List.of(
        Map.of("term", Map.of("category", category)),
        Map.of("range", Map.of("price", Map.of("lte", maxPrice)))
    );

    Map<String, Object> queryDsl = Map.of(
        "bool",
        Map.of(
            "must", List.of(match),
            "filter", filters
        )
    );

    String json = objectMapper.writeValueAsString(queryDsl);
    return new StringQuery(json);
}
~~~

Jackson chịu trách nhiệm escape chuỗi và tạo JSON hợp lệ. Ứng dụng vẫn phải kiểm tra dữ liệu đầu vào, ví dụ `keyword` không trống, `category` thuộc danh sách hợp lệ và `maxPrice` không âm nếu nghiệp vụ yêu cầu.

Nếu một điều kiện là tùy chọn, chỉ thêm clause khi có giá trị. Không đưa `null` vào query DSL một cách tùy tiện. Có thể xây dựng danh sách `must` và `filter` bằng collection có thể thay đổi, sau đó chuyển sang JSON.

Với query động phức tạp, CriteriaQuery hoặc NativeQuery có thể dễ bảo trì hơn việc tự dựng nhiều Map. StringQuery phù hợp nhất khi cấu trúc JSON đã tương đối ổn định và cần giữ biểu diễn Query DSL.

## 13. Phân biệt StringQuery và @Query trên repository

Hai cơ chế có tên gần giống nhau nhưng cách dùng khác nhau:

- `StringQuery` là một class trong package `org.springframework.data.elasticsearch.core.query`, được tạo trong Java code và truyền cho `ElasticsearchOperations`.
- `@Query` là annotation trên phương thức repository, cho phép khai báo JSON query ngay tại interface.

Ví dụ `StringQuery`:

~~~java
Query query = new StringQuery("""
{
  "match": {
    "name": {
      "query": "wireless"
    }
  }
}
""");

SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

Ví dụ repository `@Query` với placeholder:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\":{\"name\":{\"query\":\"?0\"}}}")
    List<Product> searchByName(String keyword);
}
~~~

Trong repository query, `?0` đại diện cho tham số đầu tiên của phương thức, `?1` cho tham số thứ hai và tiếp tục theo thứ tự. Placeholder được xử lý bởi cơ chế query method của repository.

Không nên giả định `StringQuery` tự động thay thế `?0` bằng tham số Java. Với `StringQuery`, hãy tạo JSON đã có giá trị được serialize an toàn hoặc chọn một API xây dựng query có tham số rõ ràng.

## 14. Kết hợp tùy chọn Query bên ngoài JSON

Chuỗi truyền vào `StringQuery` mô tả query clause. Những tùy chọn thực thi khác có thể được đặt trên đối tượng query sau khi tạo.

Ví dụ phân trang, sort và giới hạn total hits:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.query.StringQuery;

StringQuery query = new StringQuery("""
{
  "match": {
    "name": {
      "query": "wireless"
    }
  }
}
""");

query.setPageable(PageRequest.of(
    0,
    25,
    Sort.by(Sort.Direction.DESC, "price")
));

query.setTrackTotalHits(false);
~~~

Một số tùy chọn thường được quản lý bên ngoài JSON query clause:

- `Pageable`: trang và kích thước trang.
- `Sort`: thứ tự sắp xếp.
- `SourceFilter`: field cần bao gồm hoặc loại trừ khỏi `_source`.
- `trackTotalHits` hoặc `trackTotalHitsUpTo`: cách theo dõi tổng số hit.
- `minScore`: ngưỡng score tối thiểu.
- `timeout`: giới hạn thời gian tìm kiếm.
- `preference` và `routing`: lựa chọn shard hoặc định tuyến request.
- `searchAfter`: tiếp tục phân trang dựa trên sort values.

Các phương thức cụ thể có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy kiểm tra API của dependency mà dự án đang sử dụng trước khi sao chép cấu hình.

## 15. Đọc kết quả SearchHits

Khi thực thi:

~~~java
SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

`SearchHits<Product>` chứa thông tin tìm kiếm cùng các hit. Có thể duyệt kết quả:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();

    String id = hit.getId();
    float score = hit.getScore();

    // Xử lý product, id và score
}
~~~

Ngoài entity, mỗi hit có thể cung cấp:

- ID document.
- Score thể hiện mức liên quan.
- Sort values dùng cho `search_after`.
- Highlight fields nếu query yêu cầu highlight.
- Inner hits trong một số truy vấn lồng nhau.

Nếu chỉ chuyển kết quả thành `List<Product>`, ứng dụng sẽ không còn truy cập thuận tiện một số metadata của từng hit. Với màn hình tìm kiếm cần hiển thị score, đoạn highlight hoặc phân trang sâu, nên giữ `SearchHits` hoặc `SearchHit`.

## 16. Kiểm tra Query DSL trước khi triển khai

Một chuỗi JSON có thể hợp lệ về cú pháp nhưng vẫn sai về semantics. Nên kiểm tra theo nhiều lớp:

**Kiểm tra JSON.** Đảm bảo dấu ngoặc, dấu nháy, dấu phẩy và kiểu dữ liệu hợp lệ. Nếu JSON được tạo động, dùng serializer thay vì tự escape.

**Kiểm tra mapping.** Xác nhận field tồn tại và có kiểu phù hợp. `term` trên keyword, `match` trên text và `range` trên numeric/date thường là các lựa chọn phổ biến.

**Kiểm tra analyzer.** Với `match` hoặc `multi_match`, dùng Analyze API để xác nhận văn bản truy vấn được phân tích thành token như mong đợi.

**Thử trực tiếp bằng REST API.** Chạy query clause trong body của `/_search` để quan sát kết quả trước khi đưa vào code Java. Khi chuyển sang `StringQuery`, chỉ lấy phần object nằm trong `query`.

**Kiểm tra integration test.** Dùng Elasticsearch tương thích với phiên bản Spring Data của ứng dụng. Tạo dữ liệu mẫu, thực thi `StringQuery` và xác nhận document trả về, score, sort và phân trang.

**Theo dõi hiệu năng.** Query wildcard, regexp, nested hoặc bool có nhiều nhánh có thể tốn tài nguyên. Đánh giá trên dữ liệu gần với production và giới hạn kích thước trang.

## 17. Những lỗi thường gặp

**Truyền toàn bộ search request body vào StringQuery.** `StringQuery` nhận query clause, ví dụ `{"match": ...}`. Không bọc thêm `{"query": ...}` như body của REST `_search`.

**Nhầm term với match.** `term` không phân tích chuỗi tìm kiếm như `match`. Dùng `term` cho exact value, thường là keyword; dùng `match` cho full-text field.

**Dùng sai kiểu field trong range.** Range trên chuỗi keyword có semantics từ vựng, không phải số học hay thời gian. Giá cần numeric mapping, ngày cần date mapping.

**Đưa sort, from hoặc size vào query clause.** Những phần này thuộc search request options. Cấu hình qua `Pageable`, `Sort` hoặc các thuộc tính của `Query`.

**Nối trực tiếp đầu vào vào JSON.** Dữ liệu chứa dấu nháy hoặc ký tự đặc biệt có thể phá JSON. Dùng Jackson hoặc một query builder an toàn.

**Giả định StringQuery có placeholder `?0`.** Placeholder là cơ chế của repository `@Query`; `StringQuery` không tự bind tham số theo cách đó.

**Quên mapping nested.** Query có `nested` chỉ hoạt động đúng khi field được khai báo `nested` trong mapping và `path` trỏ đúng field.

**Không phân trang.** Query có thể trả về nhiều kết quả hơn giao diện cần. Đặt `Pageable`, giới hạn kích thước trang hoặc dùng `search_after` cho phân trang sâu.

**Chỉ kiểm tra JSON mà không kiểm tra kết quả.** JSON hợp lệ chưa chắc query đúng nghiệp vụ. Hãy thử trên dữ liệu mẫu và xác nhận semantics của mapping, analyzer và bool clauses.

## 18. Quy trình sử dụng StringQuery trong dự án

Có thể thực hiện theo trình tự sau:

1. Xác định yêu cầu tìm kiếm và các field liên quan.
2. Kiểm tra mapping để biết field là `text`, `keyword`, numeric, date hay nested.
3. Viết Query DSL tối thiểu bằng REST API và kiểm tra kết quả.
4. Chỉ lấy phần query clause để đưa vào `StringQuery`.
5. Nếu query có tham số động, dựng cấu trúc Java rồi serialize thành JSON.
6. Tạo `StringQuery` từ chuỗi JSON đã hoàn chỉnh.
7. Cấu hình `Pageable`, `Sort`, source filtering và các tùy chọn thực thi trên Query.
8. Gọi `ElasticsearchOperations.search(...)` với entity type và index coordinates.
9. Giữ `SearchHits` khi cần score, sort values, highlight hoặc metadata.
10. Kiểm tra bằng integration test và theo dõi hiệu năng trên dữ liệu gần với thực tế.

## Kết luận

`StringQuery` là cách biểu diễn truy vấn Spring Data Elasticsearch bằng chuỗi JSON Query DSL. Nó hữu ích khi đã có sẵn query JSON hoặc cần kiểm soát trực tiếp các clause như `match`, `term`, `range`, `bool`, `multi_match` và `nested`.

Chuỗi đầu vào là query clause, còn phân trang, sort, source filtering và các tùy chọn thực thi khác được cấu hình trên đối tượng `Query`. Với dữ liệu động, hãy tạo cấu trúc Java và serialize bằng JSON mapper để tránh lỗi escape và injection. Khi cần kiểm tra kiểu tốt hơn hoặc xây dựng query động phức tạp, có thể cân nhắc CriteriaQuery hoặc NativeQuery.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Elasticsearch Operations and Queries](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — StringQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/StringQuery.html)
- [Elasticsearch — Query DSL](https://www.elastic.co/docs/reference/query-languages/query-dsl)
- [Elasticsearch — Bool query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-bool-query)
- [Elasticsearch — Match query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-query)
