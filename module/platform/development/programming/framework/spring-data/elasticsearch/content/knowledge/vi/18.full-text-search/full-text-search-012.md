# Thiết kế truy vấn kết hợp từ khóa và bộ lọc nghiệp vụ

Một màn hình tìm kiếm trong ứng dụng thường phải giải quyết hai yêu cầu cùng lúc: tìm nội dung phù hợp với từ khóa và giới hạn kết quả theo điều kiện nghiệp vụ. Ví dụ, người dùng nhập “mechanical keyboard”, sau đó lọc theo category, khoảng giá, thương hiệu, trạng thái còn hàng và thời gian cập nhật.

Trong Elasticsearch, phần tìm kiếm văn bản thường được xây bằng **match** hoặc **multi_match**. Các điều kiện nghiệp vụ như category, trạng thái, khoảng giá và ngày thường được đặt trong **bool.filter**. Các điều kiện ảnh hưởng đến mức độ liên quan có thể nằm trong **must** hoặc **should**, còn document cần loại trừ được đặt trong **must_not**.

Thiết kế tốt cần phân biệt rõ điều kiện nào quyết định document có được xuất hiện hay không, điều kiện nào chỉ ảnh hưởng điểm relevance, field nào cần analyzer và field nào cần exact match. Bài học này trình bày cách phối hợp các thành phần đó bằng Query DSL và cách triển khai trong Spring Data Elasticsearch.

## 1. Phân biệt tìm kiếm từ khóa và bộ lọc nghiệp vụ

Tìm kiếm từ khóa trả lời câu hỏi: “Document nào có nội dung liên quan đến cụm từ người dùng nhập?”

Bộ lọc nghiệp vụ trả lời câu hỏi: “Trong các document đó, document nào thỏa điều kiện của màn hình hoặc quy tắc sản phẩm?”

Ví dụ catalog sản phẩm có entity:

~~~java
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

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Date)
    private Instant updatedAt;
}
~~~

Người dùng nhập từ khóa “mechanical keyboard”, chọn category accessories, đặt giá từ 50 đến 150 và chỉ xem sản phẩm còn hàng.

Có thể phân loại điều kiện như sau:

| Điều kiện | Vai trò | Query thường dùng |
|---|---|---|
| Từ khóa trong name/description | Tìm nội dung liên quan | match, multi_match |
| Category | Lọc chính xác | term hoặc terms |
| Brand | Lọc chính xác | term hoặc terms |
| Giá tối thiểu/tối đa | Lọc theo khoảng số | range |
| Còn hàng | Lọc boolean | term |
| Trạng thái được phép | Lọc theo tập giá trị | terms |
| Thời gian cập nhật | Lọc theo khoảng ngày | range |

Một quy tắc thiết kế hữu ích là dùng query full-text để đánh giá độ liên quan của nội dung, còn các điều kiện bắt buộc về nghiệp vụ được đặt trong filter context.

## 2. Cấu trúc bool query

Bool query kết hợp nhiều clause:

- **must**: clause phải khớp và thường tham gia tính score.
- **filter**: clause phải khớp nhưng không đóng góp vào score.
- **should**: clause khớp sẽ làm tăng score; tùy cấu hình, nó cũng có thể là điều kiện bắt buộc.
- **must_not**: document khớp clause sẽ bị loại khỏi kết quả.

Cấu trúc tổng quát:

~~~json
{
  "query": {
    "bool": {
      "must": [],
      "filter": [],
      "should": [],
      "must_not": []
    }
  }
}
~~~

Không cần khai báo đủ cả bốn danh sách. Chỉ thêm các clause mà use case thực sự cần.

### Vì sao filter phù hợp với điều kiện nghiệp vụ?

Filter context kiểm tra document có thỏa điều kiện hay không mà không tính relevance score cho điều kiện đó. Category, brand, boolean, status và khoảng giá thường không cần score. Một sản phẩm có category đúng không nhất thiết phải được đánh giá liên quan hơn sản phẩm khác chỉ vì giá trị category khớp.

Filter cũng phù hợp với các điều kiện có thể được Elasticsearch tối ưu và cache theo cơ chế nội bộ. Không nên hiểu điều này là mọi filter đều được cache chắc chắn; cache phụ thuộc query, dữ liệu và trạng thái cluster.

### Khi nào dùng must?

Dùng must khi một điều kiện văn bản cần vừa bắt buộc khớp vừa tham gia tính relevance. Ví dụ, cụm từ người dùng nhập phải xuất hiện trong tên hoặc mô tả theo semantics của full-text query.

Nếu query chỉ có filter mà không có phần scoring, kết quả vẫn có thể được sắp xếp theo field sort. Khi cần thứ tự theo mức độ liên quan, hãy đưa full-text clause vào must hoặc cấu hình scoring phù hợp.

## 3. Query kết hợp từ khóa và filter cơ bản

Ví dụ hoàn chỉnh bằng Query DSL:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "mechanical keyboard",
            "fields": [
              "name^3",
              "description"
            ],
            "type": "best_fields"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "accessories"
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
              "gte": 50,
              "lte": 150
            }
          }
        }
      ]
    }
  }
}
~~~

Query này thực hiện ba việc:

1. Tìm sản phẩm có nội dung liên quan đến “mechanical keyboard”.
2. Ưu tiên kết quả khớp trong name hơn description nhờ boost 3.
3. Chỉ giữ sản phẩm thuộc category accessories, còn hàng và có giá trong khoảng 50–150.

Boost chỉ điều chỉnh score tương đối trong query. name^3 không có nghĩa kết quả khớp tên chắc chắn được xếp cao gấp ba lần theo cách tuyến tính trong mọi tình huống.

Nếu name và description là field text, analyzer sẽ xử lý từ khóa. Nếu category là keyword, term so khớp chính xác giá trị đã index.

## 4. Chọn match, multi_match và match_phrase

### match cho một field

Dùng match khi từ khóa chỉ cần tìm trên một field:

~~~json
{
  "match": {
    "name": {
      "query": "mechanical keyboard",
      "operator": "and"
    }
  }
}
~~~

operator and yêu cầu các token được phân tích phải cùng thỏa điều kiện trong field theo semantics của match query. Nếu bỏ operator, mặc định thường là OR. Chọn AND hay OR dựa trên trải nghiệm tìm kiếm mong muốn.

### multi_match cho nhiều field

Dùng multi_match khi cùng một cụm từ cần tìm trên nhiều field:

~~~json
{
  "multi_match": {
    "query": "mechanical keyboard",
    "fields": [
      "name^3",
      "description",
      "brand^2"
    ],
    "type": "best_fields"
  }
}
~~~

Có thể boost từng field để thể hiện mức độ quan trọng khác nhau. Ví dụ tên sản phẩm quan trọng hơn mô tả; brand có thể quan trọng hơn một phần nội dung mô tả.

Các multi_match type có semantics khác nhau:

- **best_fields**: lấy cách khớp tốt nhất giữa các field, phù hợp khi một field đơn lẻ có thể chứa phần lớn truy vấn.
- **most_fields**: kết hợp điểm từ nhiều field, hữu ích khi dữ liệu được phân tích theo nhiều cách hoặc lưu trong các multi-field.
- **cross_fields**: xử lý các field như những phần của cùng một nội dung, phù hợp với một số mô hình như tên và họ.
- **phrase** và **phrase_prefix**: tìm cụm từ hoặc prefix theo semantics tương ứng.

Không chọn type chỉ theo tên. Hãy kiểm tra analyzer, dữ liệu và cách score được tính trong use case.

### match_phrase cho cụm từ

Nếu người dùng cần cụm từ xuất hiện theo thứ tự gần nhau, dùng match_phrase:

~~~json
{
  "match_phrase": {
    "name": {
      "query": "mechanical keyboard"
    }
  }
}
~~~

match_phrase thường chặt hơn match. Nó hữu ích cho tên sản phẩm, tiêu đề hoặc cụm từ có ý nghĩa khi giữ thứ tự từ. Nếu muốn tìm các từ ở vị trí không liền nhau, cân nhắc match với slop phù hợp hoặc một query type khác.

## 5. Thiết kế filter theo field mapping

Query chính xác phụ thuộc mapping. Không nên dùng cùng một kiểu query cho mọi field.

### Keyword field

Các field như category, brand, status, mã SKU thường được mapping keyword:

~~~java
@Field(type = FieldType.Keyword)
private String category;
~~~

Dùng term cho một giá trị:

~~~json
{
  "term": {
    "category": "accessories"
  }
}
~~~

Dùng terms cho nhiều giá trị:

~~~json
{
  "terms": {
    "category": [
      "accessories",
      "office"
    ]
  }
}
~~~

terms có semantics OR giữa các giá trị: document chỉ cần khớp một giá trị trong danh sách.

### Text field và keyword subfield

Một tên có thể cần cả full-text search lẫn exact filter/sort:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Khi đó:

- Tìm nội dung tên bằng match trên name.
- Lọc hoặc sort exact theo name.keyword nếu mapping có subfield đó.

Không dùng term trên field text đã được analyzer xử lý nếu mục tiêu là exact match toàn chuỗi. Query term làm việc với term đã index, không tự chạy analyzer như match query.

### Numeric và date field

Giá, số lượng, điểm đánh giá và thời gian thường được lọc bằng range:

~~~json
{
  "range": {
    "price": {
      "gte": 50,
      "lt": 150
    }
  }
}
~~~

Có thể dùng gt, gte, lt và lte. Chọn inclusive/exclusive boundary theo nghiệp vụ. Khoảng nửa mở gte + lt thường thuận tiện khi chia các khoảng liền nhau.

### Boolean field

Filter boolean dùng term:

~~~json
{
  "term": {
    "available": true
  }
}
~~~

Boolean phải là literal true hoặc false, không phải chuỗi "true".

## 6. Xử lý filter tùy chọn

Màn hình tìm kiếm thường có nhiều filter không bắt buộc. Người dùng có thể chỉ nhập từ khóa, hoặc nhập từ khóa rồi chọn category, brand và khoảng giá.

Không nên tạo một query cố định mà mọi filter đều bắt buộc nếu input có thể vắng mặt. Hãy định nghĩa rõ semantics của từng trạng thái:

| Input | Hành vi gợi ý |
|---|---|
| Keyword null hoặc rỗng | Bỏ phần full-text query hoặc yêu cầu keyword, tùy sản phẩm |
| Category null | Không thêm category filter |
| Brand list rỗng | Không thêm brand filter nếu rỗng có nghĩa chưa chọn |
| Min price null | Không có lower bound |
| Max price null | Không có upper bound |
| Available null | Không lọc theo trạng thái còn hàng |
| Available false | Chỉ lấy document không còn hàng |
| Status list rỗng | Theo chính sách: bỏ filter hoặc trả không kết quả |

Điểm quan trọng là false khác null, và collection rỗng không tự động mang nghĩa bỏ filter.

### Ví dụ Query DSL với filter tùy chọn

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "mechanical keyboard",
            "fields": ["name^3", "description"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  }
}
~~~

Khi người dùng không chọn brand, không cần thêm clause brand vào filter. Khi không nhập minPrice, bỏ lower bound. Query cuối cùng chỉ chứa những điều kiện đang có hiệu lực.

### Không dùng match_all để thay cho filter tùy chọn một cách máy móc

Nếu keyword rỗng, ứng dụng có thể muốn bỏ must và chỉ dùng filter. Có thể xây query chỉ có bool.filter. Nếu không có cả keyword lẫn filter, cần quyết định có cho phép trả toàn bộ catalog hay yêu cầu ít nhất một điều kiện.

Trả mọi document khi người dùng gửi form rỗng có thể tạo request rất rộng. Hãy đặt giới hạn page size và quy tắc tìm kiếm phù hợp với sản phẩm.

## 7. Kết hợp must, filter, should và must_not

Một query thực tế có thể cần tất cả các loại clause:

~~~http
POST /products/_search
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
            "available": true
          }
        },
        {
          "terms": {
            "category": ["accessories", "computer"]
          }
        },
        {
          "range": {
            "price": {
              "gte": 30,
              "lte": 200
            }
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": {
              "value": "KeyPro",
              "boost": 2
            }
          }
        },
        {
          "match": {
            "description": "wireless"
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
}
~~~

Ở đây:

- must yêu cầu nội dung khớp và tính score.
- filter áp dụng các điều kiện nghiệp vụ bắt buộc.
- should tăng score cho brand ưu tiên hoặc nội dung mô tả phù hợp hơn.
- must_not loại sản phẩm đã ngừng kinh doanh.

### should là bắt buộc hay chỉ tăng score?

Đây là điểm cần chú ý. Trong bool query có must hoặc filter, các clause should thường không bắt buộc theo mặc định; chúng chỉ tăng score. Nếu bool query không có must hoặc filter, mặc định có thể yêu cầu ít nhất một should khớp.

Muốn điều khiển rõ ràng, đặt minimum_should_match:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "keyboard"
        }
      }
    ],
    "should": [
      {
        "term": {
          "brand": "KeyPro"
        }
      },
      {
        "term": {
          "category": "accessories"
        }
      }
    ],
    "minimum_should_match": 1
  }
}
~~~

Trong ví dụ này, ngoài việc tên sản phẩm phải khớp, ít nhất một trong hai điều kiện should phải khớp. Nếu mục đích chỉ là boost kết quả ưu tiên, không đặt minimum_should_match hoặc chọn giá trị phù hợp với yêu cầu.

### Khi nào dùng must_not?

Dùng must_not cho điều kiện loại trừ như:

- Trạng thái đã xóa hoặc ngừng kinh doanh.
- Sản phẩm bị ẩn khỏi catalog.
- Một category không được phép xuất hiện.
- Document có field hoặc giá trị bị cấm.

Không nên đưa mọi điều kiện loại trừ vào must_not nếu thực chất đó là filter allowlist. Ví dụ chỉ cho phép status là ACTIVE hoặc BACKORDER thì terms trong filter diễn đạt rõ hơn.

## 8. Tìm kiếm nhiều field và ưu tiên field

Một query thường tìm trên nhiều field nhưng mỗi field có độ quan trọng khác nhau. Dùng boost để điều chỉnh mức độ ảnh hưởng:

~~~json
{
  "multi_match": {
    "query": "wireless keyboard",
    "fields": [
      "name^4",
      "brand^2",
      "description"
    ],
    "type": "best_fields"
  }
}
~~~

Tên sản phẩm được ưu tiên cao nhất, brand có mức ưu tiên trung gian, description là field hỗ trợ.

Boost không phải thứ tự sort cố định. Một document có score cao hơn vẫn có thể đứng sau nếu query và nội dung khác tạo ra điểm tổng hợp cao hơn cho document khác. Nếu nghiệp vụ yêu cầu ưu tiên cứng, ví dụ sản phẩm featured luôn đứng trước, hãy cân nhắc sort theo field hoặc function_score thay vì chỉ dựa vào boost.

### Multi-field và analyzer

Một field có thể có nhiều cách index:

- name kiểu text với analyzer chuẩn để tìm full-text.
- name.keyword kiểu keyword để sort hoặc exact filter.
- Một subfield lowercase hoặc analyzer tùy chỉnh cho nhu cầu tìm kiếm riêng.

Query phải tham chiếu đúng field cho từng mục đích. Đừng dùng field keyword cho truy vấn ngôn ngữ tự nhiên dài nếu muốn analyzer tách token.

## 9. Filter theo khoảng giá và thời gian

Range filter thường có hai ranh giới. Ví dụ:

~~~json
{
  "range": {
    "price": {
      "gte": 50,
      "lte": 150
    }
  }
}
~~~

Nếu chỉ có minPrice:

~~~json
{
  "range": {
    "price": {
      "gte": 50
    }
  }
}
~~~

Nếu chỉ có maxPrice:

~~~json
{
  "range": {
    "price": {
      "lte": 150
    }
  }
}
~~~

Nếu không có cả hai, không thêm range filter.

Với ngày giờ, nên chuẩn hóa timezone và dùng ISO 8601:

~~~json
{
  "range": {
    "updatedAt": {
      "gte": "2026-01-01T00:00:00Z",
      "lt": "2026-02-01T00:00:00Z"
    }
  }
}
~~~

Khoảng từ đầu tháng 1 đến đầu tháng 2 bao gồm các thời điểm trong tháng 1 và không bao gồm chính xác thời điểm đầu tháng 2. Khi input là ngày địa phương, service cần chuyển ranh giới sang timezone thống nhất trước khi tạo query.

## 10. Sort kết quả sau khi kết hợp từ khóa và filter

Khi có full-text query, Elasticsearch thường sắp xếp theo _score giảm dần nếu không khai báo sort khác. Nếu thêm sort theo field, thứ tự relevance có thể không còn là tiêu chí chính.

Ví dụ sort theo relevance rồi giá:

~~~json
{
  "sort": [
    { "_score": "desc" },
    { "price": "asc" }
  ]
}
~~~

Ví dụ sort theo giá trước rồi relevance:

~~~json
{
  "sort": [
    { "price": "asc" },
    { "_score": "desc" }
  ]
}
~~~

Hai yêu cầu tạo ra trải nghiệm khác nhau. Nếu người dùng chọn “giá thấp đến cao”, có thể ưu tiên price. Nếu người dùng chọn “liên quan nhất”, ưu tiên _score.

Với field text, thường sort trên keyword subfield thay vì text field. Với sort động, hãy dùng allowlist field và direction hợp lệ; không chèn trực tiếp tên field từ input tùy ý vào Query DSL.

## 11. Pagination và giới hạn kết quả

Kết quả tìm kiếm cần giới hạn số document trả về. Với phân trang thông thường, dùng from và size hoặc Pageable trong Spring Data:

~~~json
{
  "from": 0,
  "size": 20,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "available": true
          }
        }
      ]
    }
  }
}
~~~

Không để client gửi page size tùy ý quá lớn. Giới hạn page size tối đa ở tầng API.

Với tập kết quả lớn và phân trang sâu, cân nhắc search_after cùng sort ổn định và Point in Time (PIT) nếu cần góc nhìn nhất quán. Khi đó, cần giữ sort values của hit cuối trang trước làm cursor. Không tự dựng cursor từ entity nếu có thể lấy trực tiếp sort values Elasticsearch trả về.

## 12. Triển khai trong Spring Data Elasticsearch bằng @Query

Nếu cấu trúc query cố định, repository method có thể dùng @Query:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "bool": {
            "must": [
              {
                "multi_match": {
                  "query": "?0",
                  "fields": ["name^3", "description"]
                }
              }
            ],
            "filter": [
              {
                "term": {
                  "available": true
                }
              },
              {
                "term": {
                  "category": "?1"
                }
              },
              {
                "range": {
                  "price": {
                    "gte": ?2,
                    "lte": ?3
                  }
                }
              }
            ]
          }
        }
        """)
    List<Product> searchCatalog(
        String keyword,
        String category,
        Double minPrice,
        Double maxPrice
    );
}
~~~

Method này minh họa query có cấu trúc cố định: keyword, category và cả hai ranh giới giá đều bắt buộc. Nếu category hoặc giá có thể vắng mặt, không nên truyền null vào placeholder rồi kỳ vọng clause tự biến mất.

@Query phù hợp khi query ít biến thể, ngắn và dễ kiểm tra. Khi số filter tùy chọn tăng lên, method annotation có thể khó duy trì.

## 13. Xây dựng query động bằng ElasticsearchOperations

Với filter tùy chọn, dùng ElasticsearchOperations để tạo query theo input runtime. CriteriaQuery phù hợp với điều kiện đơn giản; NativeQuery phù hợp khi cần kiểm soát Query DSL chi tiết.

Ví dụ tổ chức service:

~~~java
public SearchHits<Product> search(ProductSearchCriteria criteria) {
    // Tạo full-text clause nếu keyword có nội dung.
    // Thêm category filter nếu category được chọn.
    // Thêm brand terms filter nếu danh sách brand có phần tử.
    // Thêm range filter cho minPrice/maxPrice khi có giá trị.
    // Thêm boolean filter nếu available khác null.
    // Ghép các clause thành bool query rồi gọi operations.search(...).
}
~~~

Một Criteria query đơn giản có thể được xây theo từng điều kiện:

~~~java
Criteria criteria = new Criteria();

if (criteriaInput.category() != null) {
    criteria.and("category").is(criteriaInput.category());
}

if (criteriaInput.minPrice() != null) {
    criteria.and("price")
        .greaterThanEqual(criteriaInput.minPrice());
}

if (criteriaInput.maxPrice() != null) {
    criteria.and("price")
        .lessThanEqual(criteriaInput.maxPrice());
}

Query query = new CriteriaQuery(criteria);
SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Đoạn code minh họa cách tạo filter động bằng Criteria. Với full-text query nhiều field, boost, nested query hoặc các nhánh bool phức tạp, NativeQuery thường phù hợp hơn. Cú pháp builder thay đổi theo phiên bản Spring Data Elasticsearch và Elasticsearch Java API Client, nên cần dùng API tương ứng với dependency của dự án.

### Tách SearchCriteria khỏi Query DSL

Không nên để controller nhận trực tiếp JSON Query DSL. Tạo một object input thể hiện điều kiện nghiệp vụ:

~~~java
public record ProductSearchCriteria(
    String keyword,
    String category,
    List<String> brands,
    Double minPrice,
    Double maxPrice,
    Boolean available,
    int page,
    int size
) {}
~~~

Service chịu trách nhiệm:

1. Validate input.
2. Chuẩn hóa keyword và giá trị.
3. Quyết định filter nào được áp dụng.
4. Chọn sort và pagination hợp lệ.
5. Xây dựng query.
6. Thực thi bằng Operations.
7. Chuyển kết quả sang DTO phù hợp.

Cách tổ chức này giữ controller và domain không phụ thuộc cấu trúc Query DSL.

## 14. Thiết kế thứ tự điều kiện và scoring

Một query kết hợp keyword và filter nên có một quy tắc scoring rõ ràng.

Ví dụ:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "gaming keyboard",
            "fields": ["name^4", "description", "brand^2"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "available": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 40,
              "lte": 250
            }
          }
        }
      ],
      "should": [
        {
          "term": {
            "featured": {
              "value": true,
              "boost": 1.5
            }
          }
        }
      ]
    }
  }
}
~~~

Sản phẩm còn hàng và nằm trong khoảng giá là điều kiện bắt buộc. Sản phẩm featured chỉ được tăng score, không phải điều kiện bắt buộc. Vì vậy, sản phẩm không featured vẫn có thể xuất hiện nếu khớp keyword và filter.

Nếu yêu cầu là chỉ lấy sản phẩm featured, chuyển điều kiện đó vào filter. Nếu yêu cầu là ít nhất một trong nhiều điều kiện ưu tiên phải khớp, cấu hình minimum_should_match.

Không dùng should khi ý nghĩa nghiệp vụ là bắt buộc mà không cấu hình rõ. Đây là nguyên nhân phổ biến khiến query trả về document tưởng như không thỏa điều kiện.

## 15. Tối ưu và các lỗi thiết kế thường gặp

### Đưa mọi điều kiện vào must

Nếu category, price và available đều được đặt trong must, chúng có thể tham gia score dù không cần thiết. Dùng filter cho điều kiện nghiệp vụ giúp query thể hiện đúng mục đích.

### Dùng term cho field text

Field text được analyzer tách thành token. term không phân tích chuỗi truy vấn như match. Với exact filter, dùng keyword field; với full-text, dùng match.

### Dùng should mà quên minimum_should_match

Khi bool query có must/filter, should có thể chỉ là clause tăng score. Nếu cần bắt buộc một trong các should, đặt minimum_should_match.

### Dùng wildcard cho từ khóa tự nhiên

Wildcard không thay thế full-text search. Dùng match hoặc multi_match cho văn bản tự nhiên. Wildcard chỉ dành cho pattern phù hợp và cần giới hạn độ rộng.

### Thêm filter rỗng hoặc null

Không tạo terms từ collection rỗng hoặc range với ranh giới null mà không xác định semantics. Xây dựng query theo điều kiện thực tế.

### Sort làm mất ưu tiên relevance

Nếu sort chỉ theo price, kết quả có thể không còn được xếp theo score. Xác định thứ tự ưu tiên giữa relevance và sort nghiệp vụ trước khi triển khai.

### Query quá rộng khi keyword trống

Nếu không có keyword và không có filter, query có thể trả gần như toàn bộ index. Đặt chính sách rõ ràng cho tìm kiếm rỗng, page size và giới hạn kết quả.

## 16. Kiểm thử truy vấn kết hợp

Nên kiểm tra query với dữ liệu đại diện cho từng nhánh điều kiện:

- Keyword khớp tên nhưng không khớp mô tả.
- Keyword chỉ khớp mô tả.
- Category đúng và sai.
- Brand thuộc và không thuộc danh sách.
- Giá nằm đúng trong khoảng, bằng ranh giới và ngoài khoảng.
- Available true, false và null/missing theo mapping.
- Status bị loại bởi must_not.
- Document chỉ khớp should nhưng không thỏa must/filter.
- Keyword rỗng và collection filter rỗng.
- Nhiều document có score gần nhau và sort field trùng giá trị.

Một integration test nên xác nhận cả tập kết quả lẫn thứ tự:

~~~java
@Test
void combinesKeywordAndBusinessFilters() {
    // Index các sản phẩm có tên, category, price và available khác nhau.
    // Tạo query cho keyword "mechanical keyboard".
    // Áp dụng category accessories, price range và available=true.
    // Thực thi search.
    // Xác nhận chỉ document thỏa filter được trả về.
    // Xác nhận thứ tự score/sort theo yêu cầu.
}
~~~

Đây là skeleton kiểm thử. Cấu hình test và cách tạo index phụ thuộc phiên bản Spring Data Elasticsearch và môi trường Elasticsearch của dự án. Test nên dùng mapping tương thích với production, vì analyzer và field type ảnh hưởng trực tiếp đến kết quả.

Khi cần chẩn đoán score, có thể bật explain trong môi trường phát triển để xem clause nào đóng góp vào điểm. Không nên bật explain cho mọi request production vì response lớn và chi phí xử lý tăng.

## 17. Checklist thiết kế search query

- [ ] Keyword được tìm trên field text phù hợp bằng match hoặc multi_match.
- [ ] Field cần exact match được mapping keyword.
- [ ] Điều kiện nghiệp vụ bắt buộc được đặt trong filter.
- [ ] Điều kiện ảnh hưởng relevance được đặt trong must/should có chủ đích.
- [ ] must_not chỉ chứa điều kiện loại trừ thực sự.
- [ ] should có minimum_should_match nếu cần bắt buộc khớp.
- [ ] Các filter tùy chọn chỉ được thêm khi input có giá trị.
- [ ] false được phân biệt với null đối với Boolean nullable.
- [ ] Collection rỗng có semantics rõ ràng.
- [ ] Khoảng số và ngày dùng đúng inclusive/exclusive boundary.
- [ ] Sort không vô tình làm mất ưu tiên relevance.
- [ ] Pagination và page size có giới hạn.
- [ ] Tên field động được chọn từ allowlist.
- [ ] Query được integration test với mapping và dữ liệu thực tế.

Một truy vấn tìm kiếm tốt kết hợp hai lớp rõ ràng: phần full-text xác định nội dung liên quan và scoring, còn phần filter giới hạn kết quả theo quy tắc nghiệp vụ. Khi dùng đúng must, filter, should và must_not, đồng thời chọn query type theo mapping, ứng dụng có thể tạo trải nghiệm tìm kiếm linh hoạt mà vẫn giữ được tính chính xác và khả năng bảo trì.

