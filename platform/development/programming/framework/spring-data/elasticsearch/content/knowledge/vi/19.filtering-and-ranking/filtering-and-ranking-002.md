# Query context và filter context trong thực tế

Khi tìm kiếm bằng Elasticsearch, một điều kiện có thể được dùng để **xếp hạng mức độ phù hợp** của document hoặc chỉ để **xác định document có được phép xuất hiện trong kết quả hay không**. Hai cách đánh giá này được gọi là query context và filter context.

- **Query context** trả lời câu hỏi: document phù hợp với nội dung tìm kiếm đến mức nào? Elasticsearch tính `_score` để biểu diễn mức độ phù hợp và thường dùng score để xếp hạng kết quả.
- **Filter context** trả lời câu hỏi: document có thỏa điều kiện hay không? Kết quả chỉ đúng hoặc sai; điều kiện không đóng góp vào `_score`.

Trong ứng dụng Spring Data Elasticsearch, việc đặt đúng điều kiện vào `must`, `should`, `filter` hoặc `must_not` giúp kết quả có thứ tự hợp lý, giảm công việc tính điểm không cần thiết và làm rõ ý nghĩa nghiệp vụ của truy vấn.

Ví dụ một trang tìm kiếm sản phẩm:

- Người dùng nhập `mechanical keyboard`: nội dung tên/mô tả cần được chấm điểm để sản phẩm phù hợp hơn xuất hiện trước.
- Người dùng chọn danh mục `KEYBOARD`, trạng thái `ACTIVE`, giá từ 1.000.000 đến 5.000.000: đây là các điều kiện lọc có/không.
- Người dùng loại trừ sản phẩm đã ngừng bán: điều kiện loại trừ không cần tăng hay giảm relevance score.

Một query kết hợp thường có dạng:

```json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "mechanical keyboard" } }
      ],
      "filter": [
        { "term": { "category": "KEYBOARD" } },
        { "term": { "status": "ACTIVE" } },
        {
          "range": {
            "price": {
              "gte": 1000000,
              "lte": 5000000
            }
          }
        }
      ],
      "must_not": [
        { "term": { "discontinued": true } }
      ]
    }
  }
}
```

Trong ví dụ này, `match` nằm trong query context để tính độ phù hợp; các điều kiện `filter` và `must_not` chỉ giới hạn tập kết quả.

## 1. Query context là gì?

Một query clause được chạy trong query context khi Elasticsearch cần đánh giá mức độ phù hợp của document với truy vấn. Ngoài việc xác định document có khớp hay không, Elasticsearch tính điểm relevance trong trường `_score`.

Query context thường phù hợp với các yêu cầu như:

- Tìm văn bản theo ý nghĩa hoặc từ khóa người dùng nhập.
- Xếp hạng tài liệu theo mức độ liên quan.
- Kết hợp nhiều tín hiệu nội dung để document phù hợp hơn đứng trước.
- Tìm kiếm gần đúng, fuzzy hoặc phrase khi người dùng không biết chính xác cách dữ liệu được lưu.

Ví dụ `match` query:

```json
GET /articles/_search
{
  "query": {
    "match": {
      "body": "distributed search engine"
    }
  }
}
```

Elasticsearch phân tích nội dung truy vấn bằng analyzer của field, tìm document có token phù hợp và tính `_score`. Document khớp nhiều thuật ngữ hoặc có tín hiệu phù hợp hơn có thể nhận score cao hơn, tùy thuật toán similarity và cấu trúc query.

Query context không chỉ dành cho `match`. Các query khác như `term`, `range` hoặc `exists` cũng có thể được đặt trong query context. Điểm khác biệt nằm ở **ngữ cảnh thực thi**, không chỉ ở loại query clause.

## 2. Filter context là gì?

Một query clause được chạy trong filter context khi mục tiêu chỉ là kiểm tra điều kiện đúng/sai. Elasticsearch không tính relevance score cho clause đó và có thể tận dụng cơ chế cache phù hợp.

Filter context thường phù hợp với các điều kiện có ý nghĩa cố định:

- Trạng thái phải là `ACTIVE`.
- Tenant phải là `tenant-42`.
- Giá nằm trong khoảng xác định.
- Ngày tạo nằm trong một khoảng thời gian.
- Field phải tồn tại.
- Địa chỉ IP phải nằm trong một subnet.
- Document không được đánh dấu đã xóa hoặc ngừng bán.

Ví dụ:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "ACTIVE" } },
        { "term": { "category": "KEYBOARD" } },
        {
          "range": {
            "price": {
              "gte": 1000000,
              "lte": 5000000
            }
          }
        }
      ]
    }
  }
}
```

Các document thỏa cả ba điều kiện được giữ lại. Không có điều kiện nào được dùng để xếp hạng relevance; nếu không có phần scoring khác và không sort theo field, thứ tự kết quả không mang ý nghĩa relevance.

## 3. Phân biệt qua các thành phần của `bool` query

`bool` query là cách phổ biến để kết hợp query context và filter context.

| Thành phần | Ngữ cảnh | Ý nghĩa |
|---|---|---|
| `must` | Query context | Điều kiện phải khớp; score của clause có thể đóng góp vào score tổng. |
| `should` | Query context | Điều kiện nên khớp; có thể tăng score và đôi khi trở thành điều kiện bắt buộc theo `minimum_should_match`. |
| `filter` | Filter context | Điều kiện phải khớp nhưng không đóng góp vào score. |
| `must_not` | Filter context | Loại document khớp điều kiện; không đóng góp vào score. |

Ví dụ:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "gaming keyboard" } }
      ],
      "should": [
        { "term": { "brand": "ACME" } },
        { "term": { "featured": true } }
      ],
      "filter": [
        { "term": { "status": "ACTIVE" } }
      ],
      "must_not": [
        { "term": { "deleted": true } }
      ],
      "minimum_should_match": 0
    }
  }
}
```

Ở đây:

- Sản phẩm phải khớp nội dung `gaming keyboard`.
- Sản phẩm phải đang hoạt động.
- Sản phẩm đã xóa bị loại.
- Thương hiệu `ACME` hoặc sản phẩm nổi bật có thể được tăng điểm nếu khớp `should`.

Với `minimum_should_match: 0`, `should` chỉ là tín hiệu tăng điểm; document không nhất thiết phải khớp một trong các clause `should` nếu đã thỏa `must` và `filter`.

### Quy tắc mặc định của `minimum_should_match`

Nếu một `bool` query chỉ có `should` và không có `must` hoặc `filter`, mặc định cần khớp ít nhất một `should`. Nếu đã có `must` hoặc `filter`, mặc định `should` không bắt buộc và có thể chỉ đóng vai trò tăng điểm.

Nếu nghiệp vụ yêu cầu ít nhất một trong nhiều điều kiện tùy chọn phải đúng, hãy khai báo `minimum_should_match` tường minh:

```json
{
  "bool": {
    "must": [
      { "match": { "name": "keyboard" } }
    ],
    "should": [
      { "term": { "brand": "ACME" } },
      { "term": { "featured": true } }
    ],
    "minimum_should_match": 1
  }
}
```

Khi đó document cần khớp nội dung `keyboard` và đồng thời khớp ít nhất một điều kiện trong hai `should`.

## 4. Chọn đúng context trong nghiệp vụ thực tế

Một quy tắc dễ áp dụng:

- Nếu điều kiện quyết định document **được phép xuất hiện** hay không, thường đặt vào `filter` hoặc `must_not`.
- Nếu điều kiện thể hiện document **phù hợp hơn** với ý định tìm kiếm và cần ảnh hưởng thứ tự, đặt vào `must` hoặc `should`.

Ví dụ một trang tìm kiếm khóa học:

| Điều kiện | Context gợi ý | Lý do |
|---|---|---|
| Tên/mô tả chứa nội dung người dùng nhập | `must` với `match` | Cần tính relevance theo nội dung. |
| Khóa học thuộc danh mục Java | `filter` với `term` | Danh mục là điều kiện bắt buộc, không cần chấm điểm. |
| Chỉ lấy khóa học đã xuất bản | `filter` với `term` | Trạng thái là điều kiện nghiệp vụ. |
| Học phí trong khoảng người dùng chọn | `filter` với `range` | Chỉ cần kiểm tra khoảng giá. |
| Khóa học được đề xuất | `should` | Có thể tăng mức ưu tiên nhưng không nhất thiết loại khóa học khác. |
| Loại khóa học đã bị gỡ | `must_not` | Loại khỏi tập kết quả. |

Không nên đưa tất cả điều kiện vào `must` chỉ vì chúng đều là điều kiện cần thỏa. `must` có thể tính điểm cho từng clause dù ứng dụng không có nhu cầu xếp hạng theo các điều kiện đó. Ngược lại, không nên đặt nội dung tìm kiếm chính vào `filter` nếu cần relevance scoring.

## 5. Query context không đồng nghĩa với full-text; filter context không đồng nghĩa với exact query

Đây là nhầm lẫn phổ biến. `match` thường dùng trong query context vì nó phục vụ full-text search, nhưng vẫn có thể đặt `match` bên trong `filter`. Khi đó nó chỉ kiểm tra document có khớp hay không và không đóng góp score.

Tương tự, `term` thường dùng để so khớp chính xác, nhưng có thể được đặt trong `must` hoặc `should` để đóng góp score nếu query được chạy trong query context.

Ví dụ một `term` trong query context:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        { "term": { "brand": "ACME" } }
      ]
    }
  }
}
```

Ví dụ cùng điều kiện nhưng ở filter context:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "brand": "ACME" } }
      ]
    }
  }
}
```

Hai query đều kiểm tra giá trị `brand` bằng `ACME`, nhưng query đầu tính score còn query thứ hai không tính score từ điều kiện brand.

## 6. Vì sao nên đưa điều kiện lọc vào filter context?

### Không tính score cho điều kiện không cần xếp hạng

Nếu `status = ACTIVE` chỉ là điều kiện bắt buộc, việc tính điểm cho nó không đem lại giá trị nghiệp vụ. Đưa vào `filter` giúp query thể hiện rõ rằng điều kiện này chỉ giới hạn tập document.

### Có thể tận dụng query cache

Elasticsearch có node query cache cho một số query trong filter context. Cache lưu kết quả matching theo segment để có thể tái sử dụng trong những lần truy vấn phù hợp. Tuy nhiên, không phải mọi filter đều được cache; việc cache phụ thuộc loại query, tần suất sử dụng, kích thước segment và heuristic của Elasticsearch.

Vì vậy, không nên thiết kế query với giả định rằng mọi `filter` chắc chắn sẽ được cache. Filter context vẫn hữu ích vì không cần scoring; cache chỉ là khả năng tối ưu bổ sung khi điều kiện và workload phù hợp.

### Kết hợp với dữ liệu có tính lặp lại

Các điều kiện như tenant, trạng thái, loại sản phẩm hoặc khoảng thời gian thường xuất hiện trong nhiều request. Chúng phù hợp với filter context vì có ngữ nghĩa boolean rõ ràng và có thể được tái sử dụng trong quá trình thực thi.

### Không phải tự sắp xếp filter theo độ chọn lọc

Không cần cố sắp xếp các clause `filter` theo thứ tự điều kiện có khả năng loại nhiều document nhất. Elasticsearch có cơ chế tối ưu thực thi query; thứ tự trong JSON không phải một cam kết rằng clause đầu tiên luôn được thực hiện trước. Hãy tổ chức filter theo ý nghĩa và khả năng bảo trì.

## 7. Query context và `_score`

Trong query context, `_score` biểu diễn mức độ phù hợp của document với query. Elasticsearch thường dùng BM25 cho full-text similarity mặc định, nhưng score cụ thể phụ thuộc analyzer, term statistics, field length, similarity và cấu trúc truy vấn.

Ví dụ:

```json
GET /articles/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "title": "spring elasticsearch" } },
        { "match": { "body": "distributed search" } }
      ],
      "filter": [
        { "term": { "status": "PUBLISHED" } }
      ]
    }
  }
}
```

Hai `match` trong `must` đóng góp vào score tổng. Filter `status` chỉ giữ các bài đã xuất bản; nó không tăng score của bài viết.

Trong bool query, score của các clause scoring được kết hợp theo quy tắc của query. Không nên tự giả định score tổng là phép cộng đơn giản trong mọi cấu trúc, vì các query lồng nhau, boost, dis_max, function score hoặc script score có thể thay đổi cách tính.

### Kiểm tra score bằng `explain`

Khi muốn biết vì sao một document có score cụ thể, có thể dùng Explain API:

```json
GET /articles/_explain/article-100
{
  "query": {
    "bool": {
      "must": [
        { "match": { "title": "spring elasticsearch" } }
      ],
      "filter": [
        { "term": { "status": "PUBLISHED" } }
      ]
    }
  }
}
```

Response giải thích document có khớp query không và các thành phần đóng góp vào score. Explain hữu ích để chẩn đoán một document; không nên gọi cho mọi document trong luồng production vì response có thể lớn và tốn tài nguyên.

## 8. Dùng `constant_score` khi chỉ cần điều kiện khớp với điểm cố định

`constant_score` chạy query bên trong filter context và gán một score cố định cho mọi document khớp. Nó hữu ích khi cần đưa một điều kiện boolean vào query scoring nhưng không muốn score phụ thuộc độ phù hợp của điều kiện đó.

Ví dụ:

```json
GET /products/_search
{
  "query": {
    "constant_score": {
      "filter": {
        "term": {
          "featured": true
        }
      },
      "boost": 2.0
    }
  }
}
```

Mọi document có `featured = true` đều nhận score cố định theo boost được cấu hình. Cách này khác với việc đặt `term` trực tiếp trong `must`, nơi score của query term được tính theo scoring model.

Trong một truy vấn phức tạp, có thể dùng `constant_score` để tạo một tín hiệu điểm cố định cho một nhóm document, nhưng cần cân nhắc cách kết hợp với các scoring clause khác để tránh làm lệch thứ tự kết quả ngoài ý muốn.

## 9. Kết hợp relevance với bộ lọc trong một truy vấn sản phẩm

Giả sử một trang thương mại điện tử có các tham số:

- `q`: từ khóa tìm kiếm.
- `category`: danh mục người dùng chọn.
- `minPrice`, `maxPrice`: khoảng giá.
- `brand`: thương hiệu tùy chọn.
- `featured`: ưu tiên sản phẩm nổi bật.
- `status`: chỉ lấy sản phẩm đang hoạt động.

Query DSL có thể được tổ chức như sau:

```json
GET /products/_search
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
        { "term": { "status": "ACTIVE" } },
        { "term": { "category": "KEYBOARD" } },
        {
          "range": {
            "price": {
              "gte": 1000000,
              "lte": 5000000
            }
          }
        }
      ],
      "should": [
        { "term": { "brand": { "value": "ACME", "boost": 1.5 } } },
        { "term": { "featured": { "value": true, "boost": 2.0 } } }
      ],
      "minimum_should_match": 0,
      "must_not": [
        { "term": { "discontinued": true } }
      ]
    }
  }
}
```

Ở đây:

- `name^3` tăng trọng số cho kết quả khớp tên so với mô tả.
- Danh mục, trạng thái và khoảng giá là filter.
- Thương hiệu ACME và sản phẩm nổi bật là tín hiệu tăng điểm tùy chọn.
- Sản phẩm ngừng bán bị loại.
- `minimum_should_match: 0` cho phép sản phẩm không khớp các tín hiệu `should` vẫn xuất hiện nếu thỏa điều kiện chính và filter.

Nếu người dùng chọn thương hiệu và yêu cầu chỉ xem thương hiệu đó, hãy chuyển brand từ `should` sang `filter`. Vị trí clause phải phản ánh ý nghĩa của bộ lọc trên giao diện.

## 10. Ví dụ trong Spring Data Elasticsearch với `NativeQuery`

Với Spring Data Elasticsearch hiện đại, `NativeQuery` sử dụng query DSL của Elasticsearch Java API Client. Có thể tạo `bool` query và đặt từng điều kiện vào đúng context.

```java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(String text, String category) {
        Query esQuery = Query.of(q -> q
                .bool(b -> b
                        .must(m -> m
                                .match(mm -> mm
                                        .field("name")
                                        .query(text)
                                )
                        )
                        .filter(f -> f
                                .term(t -> t
                                        .field("category")
                                        .value(FieldValue.of(category))
                                )
                        )
                        .filter(f -> f
                                .term(t -> t
                                        .field("status")
                                        .value(FieldValue.of("ACTIVE"))
                                )
                        )
                        .mustNot(mn -> mn
                                .term(t -> t
                                        .field("discontinued")
                                        .value(FieldValue.of(true))
                                )
                        )
                )
        );

        NativeQuery query = NativeQuery.builder()
                .withQuery(esQuery)
                .build();

        return operations.search(query, ProductDocument.class);
    }
}
```

Đoạn code thể hiện rõ:

- `must(match(...))` dùng query context để tính relevance theo tên sản phẩm.
- `filter(term(...))` giới hạn danh mục và trạng thái mà không tính score.
- `mustNot(term(...))` loại sản phẩm ngừng bán trong filter context.

Trong ví dụ, field name được truyền vào Java API Client là tên field Elasticsearch thực tế. Nếu entity có `@Field(name = "product_name")` cho property `name`, raw Java API Client query cần dùng `product_name`; mapping của Spring Data không tự đổi tên field bên trong Query DSL do ứng dụng tự tạo.

### Dùng CriteriaQuery cho điều kiện lọc đơn giản

`CriteriaQuery` phù hợp khi phần lớn truy vấn là các điều kiện lọc động và không cần kiểm soát scoring phức tạp. Ví dụ:

```java
Criteria criteria = new Criteria("status").is("ACTIVE")
        .and("category").is(category)
        .and("price").between(minPrice, maxPrice);

CriteriaQuery query = new CriteriaQuery(criteria);
SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

Khi cần kết hợp relevance scoring, `should`, boost hoặc query DSL chuyên sâu, `NativeQuery` giúp biểu đạt trực tiếp `bool` query và context mong muốn. Với Criteria API, cần xem query DSL được sinh ra bởi phiên bản Spring Data đang dùng nếu việc phân biệt scoring/filter là yêu cầu quan trọng.

## 11. Dùng filter cho tenant, quyền truy cập và trạng thái

Các điều kiện như tenant, trạng thái hoặc phạm vi dữ liệu thường là filter vì chúng quyết định document nào được phép tham gia kết quả. Ví dụ:

```json
GET /orders/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "description": "late delivery" } }
      ],
      "filter": [
        { "term": { "tenant_id": "tenant-42" } },
        { "term": { "status": "OPEN" } }
      ]
    }
  }
}
```

Filter theo tenant giúp giới hạn kết quả của truy vấn ứng dụng. Tuy nhiên, việc đặt tenant vào filter không thay thế Elasticsearch security. Nếu nhiều tenant hoặc người dùng có quyền khác nhau truy cập trực tiếp cluster, cần cấu hình security role, document-level security nếu môi trường hỗ trợ, hoặc bảo đảm mọi truy vấn đều đi qua service có kiểm soát.

Không nên cho client gửi tùy ý tenant ID để truy vấn. Tenant identity nên được lấy từ authentication context và được thêm ở tầng service/repository để tránh người dùng sửa tham số request nhằm đọc dữ liệu tenant khác.

## 12. Filter context và cache

Elasticsearch có node query cache, thường phục vụ kết quả của một số query chạy trong filter context. Cache hoạt động theo segment và được quản lý bởi Elasticsearch; nó không phải cache kết quả toàn bộ HTTP response.

Một số lưu ý:

- Không phải mọi filter đều được cache.
- Các query được sử dụng thường xuyên và phù hợp với heuristic có cơ hội được cache hơn.
- Segment nhỏ hoặc query ít lặp có thể không đem lại lợi ích cache.
- Cache được quản lý tự động; không nên giả định mọi điều kiện filter sẽ tồn tại trong cache mãi mãi.
- `must_not` cũng hoạt động trong filter context và có thể tham gia cơ chế tối ưu phù hợp.

Vì vậy, đưa điều kiện vào filter chủ yếu để thể hiện đúng semantics và tránh scoring không cần thiết. Nếu hiệu năng là mục tiêu, hãy đo workload thực tế và quan sát thống kê cache thay vì dựa vào giả định rằng filter luôn nhanh hơn một tỷ lệ cố định.

## 13. Sort theo field khác với relevance scoring

Nếu query có scoring clause, Elasticsearch thường sắp xếp theo `_score` giảm dần mặc định. Nhưng khi nghiệp vụ yêu cầu sort theo giá, ngày tạo hoặc tên, có thể khai báo sort field.

Ví dụ:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "keyboard" } }
      ],
      "filter": [
        { "term": { "status": "ACTIVE" } }
      ]
    }
  },
  "sort": [
    { "price": "asc" },
    { "_score": "desc" }
  ]
}
```

Ở đây, giá thấp được ưu tiên trước; nếu giá bằng nhau, score cao hơn đứng trước. Nếu sort chỉ theo field và không cần score, có thể cân nhắc tắt việc tính/giữ score theo API phù hợp. Nếu cần kết hợp score và field, phải xác định rõ thứ tự ưu tiên của từng sort key.

Sort theo `keyword`, numeric hoặc date field phù hợp hơn sort trực tiếp trên `text`. Nếu tên cần vừa full-text search vừa sort, hãy dùng multi-field `keyword` hoặc field sort riêng.

## 14. Khi nào dùng `function_score` hoặc boost?

Query context cho phép xếp hạng theo độ phù hợp văn bản. Khi nghiệp vụ cần thêm tín hiệu như độ phổ biến, chất lượng sản phẩm hoặc mức độ mới, có thể kết hợp scoring bằng boost, `function_score` hoặc query chuyên biệt.

Ví dụ một tín hiệu tùy chọn:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "wireless mouse" } }
      ],
      "filter": [
        { "term": { "status": "ACTIVE" } }
      ],
      "should": [
        { "term": { "featured": { "value": true, "boost": 2.0 } } }
      ]
    }
  }
}
```

Sản phẩm nổi bật được tăng score nếu khớp, nhưng vẫn phải đáp ứng truy vấn tên và trạng thái. Nếu `featured` là điều kiện bắt buộc, chuyển nó sang filter; nếu nó chỉ là tín hiệu xếp hạng, giữ trong should hoặc dùng scoring function phù hợp.

Không nên đưa mọi thuộc tính kinh doanh vào boost mà không có đánh giá. Boost quá lớn có thể làm sản phẩm nổi bật nhưng không liên quan vượt lên trên sản phẩm khớp nội dung tốt. Hãy kiểm thử bằng tập query và kết quả mong đợi.

## 15. Kiểm thử query context và filter context

Khi xây dựng truy vấn, nên kiểm thử cả tập document và score:

1. Document không thỏa filter phải bị loại dù score nội dung rất cao.
2. Document thỏa filter nhưng không khớp query chính không được xuất hiện nếu query chính nằm trong `must`.
3. Document khớp nhiều scoring clause có thể được xếp hạng cao hơn theo thiết kế.
4. `should` có đúng semantics với `minimum_should_match`.
5. `must_not` loại đúng document.
6. Sort field không vô tình ghi đè thứ tự relevance nếu sản phẩm cần sort theo score.
7. Filter theo tenant lấy tenant từ security context, không tin giá trị tùy ý của client.

Ví dụ bộ dữ liệu kiểm thử:

| ID | Name | Status | Category | Featured | Kết quả mong đợi với query `keyboard` + filter ACTIVE/KEYBOARD |
|---|---|---|---|---:|---|
| P1 | Mechanical keyboard | ACTIVE | KEYBOARD | true | Có; có thể được tăng score. |
| P2 | Keyboard cover | ACTIVE | KEYBOARD | false | Có nếu match query. |
| P3 | Mechanical keyboard | INACTIVE | KEYBOARD | true | Bị loại bởi filter. |
| P4 | Mechanical keyboard | ACTIVE | MOUSE | true | Bị loại bởi filter. |
| P5 | Wireless mouse | ACTIVE | MOUSE | false | Không khớp query chính và không thỏa filter. |

Trong integration test, có thể kiểm tra `SearchHit.getScore()` để xác nhận scoring clause có tác động như mong muốn. Không nên khẳng định một score tuyệt đối cố định nếu analyzer, corpus hoặc similarity có thể thay đổi; thường nên kiểm tra thứ tự tương đối và tập kết quả.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Kết quả không được xếp hạng theo độ phù hợp | Đưa truy vấn văn bản vào `filter` thay vì query context. | Đặt nội dung tìm kiếm vào `must` hoặc `should` khi cần score. |
| Điều kiện trạng thái làm thay đổi thứ tự score không cần thiết | Đưa điều kiện boolean vào `must`. | Chuyển điều kiện bắt buộc sang `filter`. |
| Document không khớp điều kiện tùy chọn vẫn xuất hiện | `should` không bắt buộc vì có `must`/`filter` và `minimum_should_match` mặc định là 0. | Đặt `minimum_should_match` phù hợp hoặc chuyển điều kiện thành filter. |
| Filter không cải thiện hiệu năng như kỳ vọng | Query không được cache, cache không phù hợp workload hoặc bottleneck nằm ở phần khác. | Đo query, kiểm tra cache stats và profile khi cần. |
| Dùng `match` để lọc chính xác mã/trạng thái | Analyzer có thể tách hoặc chuẩn hóa token. | Dùng `keyword` và `term` trong filter context. |
| `term` query không tìm được giá trị trên field text | Field text được phân tích, token trong index khác chuỗi đầu vào. | Dùng keyword subfield hoặc query phù hợp analyzer. |
| `must_not` không loại document như mong đợi | Điều kiện con hoặc mapping không khớp field/value. | Kiểm tra mapping, query DSL và dữ liệu `_source`. |
| Sản phẩm nổi bật luôn đứng đầu dù không liên quan | Boost quá lớn hoặc `should` được thiết kế không phù hợp. | Điều chỉnh boost, kiểm thử relevance và giữ query chính trong `must`. |
| Filter tenant không bảo vệ dữ liệu | Tenant ID được client tự truyền hoặc service không áp dụng filter nhất quán. | Lấy tenant từ authentication context và cấu hình security phù hợp. |

## 17. Nguyên tắc thiết kế

- Đặt nội dung tìm kiếm cần relevance vào query context (`must`, `should`).
- Đặt điều kiện bắt buộc có/không vào filter context (`filter`, `must_not`).
- Dùng `term` cho giá trị exact trên field `keyword`; dùng `range` cho điều kiện khoảng.
- Đừng nhầm loại query với context: cùng một clause có thể chạy trong query hoặc filter context tùy vị trí.
- Khai báo `minimum_should_match` rõ ràng khi `should` có ý nghĩa bắt buộc.
- Dùng `should` cho tín hiệu xếp hạng tùy chọn, không dùng nó thay filter nếu người dùng đã chọn điều kiện bắt buộc.
- Không giả định mọi filter đều được cache; để Elasticsearch quản lý cache và đo workload thực tế.
- Không cần sắp xếp filter thủ công theo độ chọn lọc.
- Dùng `explain` để chẩn đoán score của một document và kiểm thử thứ tự tương đối trên tập dữ liệu đại diện.
- Bảo vệ điều kiện tenant/authorization ở tầng service và security; filter query không tự là ranh giới bảo mật.

## 18. Những điểm cần nhớ

- Query context vừa xác định document khớp vừa tính `_score` để đánh giá relevance.
- Filter context chỉ kiểm tra đúng/sai, không đóng góp score.
- Trong `bool`: `must` và `should` chạy trong query context; `filter` và `must_not` chạy trong filter context.
- `should` có thể chỉ tăng điểm hoặc trở thành bắt buộc tùy `minimum_should_match` và các clause khác trong bool query.
- `match` không mặc định luôn là query context; vị trí đặt clause quyết định context.
- Filter context tránh scoring không cần thiết và có thể tận dụng node query cache khi phù hợp; không phải filter nào cũng được cache.
- Dùng `NativeQuery` để biểu đạt rõ bool query trong Spring Data Elasticsearch khi cần kiểm soát context và scoring.
- `CriteriaQuery` phù hợp với điều kiện lọc có cấu trúc; với yêu cầu scoring phức tạp cần xác minh Query DSL được sinh ra.
- Query relevance và sort theo field là hai cơ chế khác nhau; xác định thứ tự ưu tiên rõ ràng.
- Filter theo tenant hoặc quyền truy cập phải được bảo vệ ở tầng ứng dụng/security, không chỉ dựa vào query do client gửi.

Hiểu rõ query context và filter context giúp thiết kế truy vấn vừa đúng nghiệp vụ vừa dễ kiểm soát thứ tự kết quả. Hãy dùng query context cho tín hiệu cần chấm điểm, filter context cho điều kiện giới hạn tập document, rồi kiểm thử cả tập kết quả lẫn thứ tự relevance trên dữ liệu đại diện.
