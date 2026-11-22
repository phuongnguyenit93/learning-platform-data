# Tham số Query và lựa chọn CriteriaQuery, StringQuery, NativeQuery

## 1. Query trong Spring Data Elasticsearch

Khi cần tìm nhiều document, Spring Data Elasticsearch cung cấp `ElasticsearchOperations` và `SearchOperations`. Các phương thức tìm kiếm nhận một đối tượng `Query` để mô tả nội dung cần tìm cùng các tùy chọn thực thi như phân trang, sắp xếp và giới hạn kết quả.

`Query` trong Spring Data Elasticsearch là abstraction của tầng Spring Data. Nó khác với kiểu `Query` trong Elasticsearch Java API Client. Ba cách xây dựng query thường dùng là:

- **CriteriaQuery:** tạo điều kiện bằng API Criteria dạng fluent, không cần tự viết JSON Query DSL.
- **StringQuery:** truyền trực tiếp Elasticsearch Query DSL dưới dạng chuỗi JSON.
- **NativeQuery:** xây dựng query bằng các kiểu query của Elasticsearch Java API Client.

Luồng thực thi cơ bản:

~~~text
Service
  |
  v
ElasticsearchOperations.search(query, ...)
  |
  v
Spring Data SearchOperations
  |
  v
Chuyển Query thành Elasticsearch request
  |
  v
Elasticsearch cluster
  |
  v
SearchHits<T>
~~~

Cùng một yêu cầu tìm sản phẩm theo tên, danh mục và giá có thể được biểu diễn bằng cả ba implementation. Cách chọn phụ thuộc độ phức tạp, mức độ cần kiểm soát Query DSL và khả năng động của điều kiện tìm kiếm.

## 2. Truyền Query vào ElasticsearchOperations

`ElasticsearchOperations` kết hợp các thao tác document và search. Với tìm kiếm, có thể gọi `search` bằng query, kiểu entity và index coordinates:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(Query query) {
        return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products")
        );
    }
}
~~~

Các tham số của lời gọi:

- `query` mô tả điều kiện tìm kiếm và những tùy chọn đi kèm.
- `Product.class` là kiểu Java mà document trả về sẽ được ánh xạ thành.
- `IndexCoordinates.of("products")` là index hoặc alias mà request sẽ truy vấn.

Nếu entity có metadata `@Document(indexName = "...")`, một số overload có thể lấy index từ metadata entity. Truyền `IndexCoordinates` tường minh hữu ích khi service cần làm việc với alias hoặc index được chọn tại thời điểm chạy.

`Query` là phần mô tả yêu cầu tìm kiếm. `ElasticsearchOperations` chuyển query thành request phù hợp với client, gửi request và ánh xạ kết quả thành `SearchHits`.

## 3. Các tham số Query thường gặp

Query không chỉ chứa điều kiện lọc. Nó còn có thể mang các tùy chọn kiểm soát kết quả và cách Elasticsearch thực thi tìm kiếm.

| Tham số hoặc tùy chọn | Mục đích | Khi nào dùng |
|---|---|---|
| `Pageable` | Xác định trang, kích thước trang và có thể cả sort | Giao diện danh sách kết quả |
| `Sort` | Sắp xếp theo một hoặc nhiều field | Giá tăng dần, ngày mới nhất, tên |
| `SourceFilter` | Chỉ lấy một số field trong `_source` hoặc loại trừ field | Giảm dữ liệu trả về khi entity lớn |
| Fields / stored fields | Yêu cầu trả về các field cần thiết | Khi cần lấy dữ liệu trường cụ thể |
| `trackTotalHits` | Yêu cầu Elasticsearch theo dõi tổng số hit chính xác | Khi giao diện cần tổng số kết quả chính xác |
| `trackTotalHitsUpTo` | Giới hạn ngưỡng theo dõi tổng số hit | Khi chỉ cần biết số lượng đến một ngưỡng |
| `minScore` | Chỉ giữ hit có điểm liên quan tối thiểu | Loại kết quả có mức liên quan quá thấp |
| `timeout` | Giới hạn thời gian thực thi tìm kiếm ở phía Elasticsearch | Truy vấn cần có giới hạn thời gian |
| `preference` | Gợi ý shard copy/node ưu tiên xử lý request | Khi cần tính ổn định của lựa chọn shard hoặc locality |
| `routing` | Định tuyến tìm kiếm đến shard tương ứng | Khi hệ thống dùng custom routing |
| `searchAfter` | Tiếp tục lấy trang sau từ sort values của trang trước | Phân trang sâu |
| `highlight` | Yêu cầu các đoạn văn bản khớp truy vấn | Tô sáng từ khóa trong kết quả |

Không phải mọi tùy chọn đều có cùng cách cấu hình ở mọi phiên bản hoặc mọi implementation của `Query`. API hiện hành cung cấp các phương thức như `setPageable`, `addSort`, `addSourceFilter`, `setTrackTotalHits`, `setTrackTotalHitsUpTo`, `setPreference`, `setSearchAfter` và `setHighlightQuery`. Một số tùy chọn khác được khai báo ở `BaseQuery` hoặc thông qua builder của `NativeQuery`.

### Phân trang và sắp xếp

Có thể đặt `Pageable` trực tiếp trên query:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.desc("name")
    )
);

query.setPageable(pageable);
~~~

Trang bắt đầu từ chỉ số `0`. Ví dụ trên lấy tối đa 20 kết quả đầu tiên, sắp xếp theo giá tăng dần rồi tên giảm dần.

Nếu query đã có `Pageable` chứa sort, không cần thêm cùng một sort lần nữa. Có thể dùng `addSort` khi muốn bổ sung sort theo API của phiên bản đang dùng.

### Theo dõi tổng số kết quả

Elasticsearch có thể giới hạn việc theo dõi total hits để tiết kiệm chi phí. Nếu giao diện thực sự cần tổng số kết quả chính xác, có thể yêu cầu:

~~~java
query.setTrackTotalHits(true);
~~~

Nếu chỉ cần biết kết quả đến một ngưỡng, có thể dùng `trackTotalHitsUpTo` theo API của phiên bản đang sử dụng. Việc yêu cầu tổng số chính xác có thể tốn thêm tài nguyên trên tập dữ liệu lớn; chỉ bật khi nghiệp vụ cần.

### Giới hạn dữ liệu trả về

Source filtering cho phép lấy một số field trong `_source` hoặc loại trừ các field không cần thiết. Điều này hữu ích khi document có nhiều metadata hoặc trường lớn nhưng màn hình chỉ cần tên, giá và danh mục.

Cần phân biệt source filtering với stored fields. Source filtering chọn phần dữ liệu trong `_source`; stored fields yêu cầu các field đã được cấu hình lưu riêng trong index. Không phải field nào cũng có thể trả về qua stored fields chỉ vì đã khai báo tên.

### Phân trang sâu bằng search_after

`from` và `size` phù hợp với các trang đầu. Khi cần đi sâu qua nhiều kết quả, chi phí và giới hạn result window có thể trở thành vấn đề. `search_after` sử dụng sort values của hit cuối cùng ở trang trước để lấy trang kế tiếp.

Spring Data Query có `setSearchAfter(...)`. Các giá trị truyền vào phải lấy từ `SearchHit.getSortValues()` của kết quả trước, đồng thời query sau phải giữ thứ tự sort tương ứng. Với tập kết quả cần nhất quán trong lúc dữ liệu thay đổi, cân nhắc kết hợp Point in Time theo khả năng của phiên bản Elasticsearch và Spring Data.

## 4. CriteriaQuery: xây dựng truy vấn bằng Criteria

`CriteriaQuery` phù hợp khi điều kiện tìm kiếm có thể diễn đạt bằng các phép toán quen thuộc như bằng, lớn hơn, nhỏ hơn, trong danh sách, chứa chuỗi hoặc kết hợp AND/OR. Người viết không cần tự tạo JSON Query DSL.

Giả sử entity sản phẩm có các field:

~~~java
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

Tìm sản phẩm có giá đúng bằng một giá trị:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Criteria criteria = new Criteria("price").is(42.0);
Query query = new CriteriaQuery(criteria);
~~~

Tìm sản phẩm thuộc danh mục `audio` và có giá không vượt quá 2.000.000:

~~~java
Criteria criteria = new Criteria("category").is("audio")
    .and("price").lessThanEqual(2_000_000);

Query query = new CriteriaQuery(criteria);
~~~

`and("price")` nối điều kiện giá vào chuỗi Criteria. Các điều kiện được kết hợp theo logic AND.

### Kết hợp AND và OR

Mặc định, khi nối các Criteria bằng `and`, các điều kiện phải cùng thỏa mãn. Với `or`, một trong các nhánh có thể thỏa mãn.

Ví dụ tìm sản phẩm có danh mục `audio` và thương hiệu là `Acme` hoặc `Contoso`:

~~~java
Criteria brandCriteria = new Criteria()
    .or("brand").is("Acme")
    .or("brand").is("Contoso");

Criteria criteria = new Criteria("category").is("audio")
    .subCriteria(brandCriteria);

Query query = new CriteriaQuery(criteria);
~~~

Có thể hiểu điều kiện trên như:

~~~text
category = "audio"
AND
(brand = "Acme" OR brand = "Contoso")
~~~

Trong Elasticsearch Query DSL, AND thường được chuyển thành `bool.must`, còn OR được chuyển thành `bool.should`. Khi biểu thức có nhiều tầng logic, hãy dùng `subCriteria` để thể hiện rõ nhóm điều kiện và kiểm tra query được tạo ra nếu thứ tự nhóm có ảnh hưởng đến nghiệp vụ.

### Các phép toán Criteria thường dùng

| Phép toán | Ví dụ | Ý nghĩa |
|---|---|---|
| Bằng | `is("audio")` | Giá trị bằng giá trị truyền vào |
| Khác | `not().is("audio")` | Phủ định điều kiện |
| Lớn hơn | `greaterThan(100)` | Giá trị lớn hơn |
| Lớn hơn hoặc bằng | `greaterThanEqual(100)` | Giá trị ít nhất bằng |
| Nhỏ hơn | `lessThan(100)` | Giá trị nhỏ hơn |
| Nhỏ hơn hoặc bằng | `lessThanEqual(100)` | Giá trị không vượt quá |
| Trong khoảng | `between(10, 20)` | Nằm trong khoảng |
| Thuộc danh sách | `in("audio", "video")` | Khớp một giá trị trong danh sách |
| Có giá trị | `exists()` | Field có giá trị được lập chỉ mục |
| Chứa chuỗi | `contains("wireless")` | Điều kiện dạng contains theo Criteria API |
| Bắt đầu bằng | `startsWith("pro")` | Điều kiện tiền tố |
| Kết thúc bằng | `endsWith("phone")` | Điều kiện hậu tố |
| Gần đúng | `fuzzy("wirless")` | Tìm kiếm gần đúng theo hỗ trợ của Criteria |

Không phải phép toán nào cũng phù hợp với mọi kiểu field. Ví dụ, `in` tạo terms query nên thường phù hợp với `keyword`, không nên dùng trên text field đã được analyzer biến đổi. Những phép contains hoặc wildcard có thể gây truy vấn tốn kém, đặc biệt khi có leading wildcard. Hãy chọn mapping và toán tử theo dữ liệu thực tế.

### Khi nào CriteriaQuery phù hợp?

CriteriaQuery là lựa chọn tốt khi:

- Điều kiện là các filter nghiệp vụ đơn giản.
- Muốn tạo query theo từng tham số có hoặc không có giá trị.
- Muốn code dễ đọc mà không phải viết JSON.
- Các toán tử Criteria đủ để mô tả yêu cầu.
- Query không cần nhiều tính năng chuyên biệt của Elasticsearch.

CriteriaQuery không nhằm thay thế toàn bộ Query DSL. Nếu cần truy vấn phức tạp như nested query, script, vector search hoặc một tổ hợp DSL chuyên sâu, NativeQuery thường phù hợp hơn.

## 5. StringQuery: truyền Query DSL dưới dạng JSON

`StringQuery` nhận một chuỗi JSON chứa phần query Elasticsearch. Cách này phù hợp khi đã có Query DSL rõ ràng hoặc muốn giữ query JSON gần với tài liệu Elasticsearch.

Ví dụ tìm sản phẩm theo tên:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

Query query = new StringQuery("""
{
  "match": {
    "name": {
      "query": "wireless headphones"
    }
  }
}
""");
~~~

Tìm theo tên và lọc theo danh mục, khoảng giá:

~~~java
Query query = new StringQuery("""
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "wireless headphones"
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

Trong ví dụ:

- `match` tìm kiếm toàn văn trên field `name`.
- `must` chứa điều kiện truy vấn có thể ảnh hưởng đến điểm liên quan.
- `filter` lọc theo danh mục và giá mà không dùng các điều kiện này để tính điểm liên quan.
- `term` phù hợp với field keyword.
- `range` lọc theo khoảng giá.

Sau khi tạo `StringQuery`, vẫn có thể gắn các tùy chọn phân trang hoặc sort thông qua API `Query`:

~~~java
query.setPageable(PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "price")
));
~~~

### StringQuery không tự bind tham số như repository @Query

Cần phân biệt hai cơ chế:

- `StringQuery` nhận một chuỗi JSON Query DSL đã được tạo sẵn.
- Annotation `@Query` trên repository có cơ chế placeholder như `?0`, `?1` để thay tham số phương thức.

Không nên mặc định rằng `StringQuery` tự thay `?0` bằng giá trị Java. Nếu cần tạo JSON từ dữ liệu đầu vào, hãy dùng JSON serializer hoặc một cơ chế tạo query an toàn. Không nối trực tiếp chuỗi người dùng vào JSON vì dấu nháy, ký tự escape hoặc nội dung không tin cậy có thể làm hỏng query hoặc tạo truy vấn ngoài ý muốn.

### Khi nào StringQuery phù hợp?

- Đã có sẵn JSON Query DSL từ một nguồn đáng tin cậy.
- Muốn biểu diễn query đúng như request Elasticsearch.
- Cần dùng một phần Query DSL mà Criteria API không diễn đạt thuận tiện.
- Query tương đối cố định và nhóm phát triển muốn kiểm soát JSON.

Nhược điểm là JSON được giữ dưới dạng chuỗi, nên lỗi cú pháp hoặc sai tên field thường chỉ được phát hiện khi query được thực thi. Chuỗi dài cũng khó refactor và kiểm tra kiểu hơn so với NativeQuery.

## 6. NativeQuery: dùng trực tiếp Elasticsearch Java API Client

`NativeQuery` phù hợp với truy vấn phức tạp hoặc những khả năng không thể diễn đạt thuận tiện bằng Criteria API. Nó sử dụng các kiểu query từ Elasticsearch Java API Client, thuộc package `co.elastic.clients.elasticsearch._types.query_dsl`.

Ví dụ tìm sản phẩm có tên phù hợp với `wireless headphones` và thuộc danh mục `audio`:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .must(m -> m
                .match(mm -> mm
                    .field("name")
                    .query("wireless headphones")
                )
            )
            .filter(f -> f
                .term(t -> t
                    .field("category")
                    .value(v -> v.stringValue("audio"))
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Trong ví dụ:

- `NativeQuery.builder()` tạo builder của Spring Data.
- `withQuery(...)` nhận lambda để xây dựng query bằng Elasticsearch Java API Client.
- `bool(...)` tạo bool query.
- `must(...)` chứa full-text match query.
- `filter(...)` chứa term query lọc danh mục.
- `withPageable(...)` cấu hình trang kết quả.
- `build()` tạo query hoàn chỉnh.

Điểm khác biệt quan trọng là code dùng builder có kiểu của Java API Client. IDE có thể hỗ trợ autocomplete và compiler kiểm tra kiểu dữ liệu tốt hơn so với việc viết JSON dài trong StringQuery.

### Kết hợp aggregation

NativeQuery cũng phù hợp khi cần aggregation cùng truy vấn:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query query = NativeQuery.builder()
    .withQuery(q -> q
        .match(m -> m
            .field("name")
            .query("wireless")
        )
    )
    .withAggregation(
        "categories",
        Aggregation.of(a -> a
            .terms(t -> t
                .field("category")
                .size(10)
            )
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Aggregation `categories` tạo bucket theo field `category`. Kết quả aggregation có thể được đọc từ `SearchHits` thông qua metadata aggregation mà Spring Data cung cấp.

### Những khả năng thường cần NativeQuery

Tùy phiên bản Elasticsearch Java API Client và Spring Data Elasticsearch, NativeQuery có thể dùng để xây dựng:

- Bool query với nhiều nhánh `must`, `filter`, `should` và `must_not`.
- Nested query.
- Geo query.
- Script query.
- Highlight.
- Aggregation.
- Suggestion.
- Các truy vấn chuyên biệt khác được Java API Client hỗ trợ.

Không phải mọi tính năng của Elasticsearch đều có API giống nhau qua các phiên bản. Hãy dùng tài liệu của đúng phiên bản dependency trong dự án khi xây dựng query.

## 7. So sánh CriteriaQuery, StringQuery và NativeQuery

Ba implementation đều có thể được truyền cho `ElasticsearchOperations.search(...)`, nhưng cách tạo query và mức độ kiểm soát khác nhau.

| Tiêu chí | CriteriaQuery | StringQuery | NativeQuery |
|---|---|---|---|
| Cách khai báo | Fluent Criteria API | JSON Query DSL dạng chuỗi | Builder có kiểu của Elasticsearch Java API Client |
| Mức độ cần biết Query DSL | Thấp đến trung bình | Cao | Cao |
| Kiểm tra kiểu lúc biên dịch | Tốt với kiểu Java và API Criteria | Thấp đối với nội dung JSON | Tốt hơn nhờ builder có kiểu |
| Đọc điều kiện đơn giản | Rất dễ đọc | Có thể dài hơn cần thiết | Có thể nhiều lambda |
| Query phức tạp | Có giới hạn | Diễn đạt được bằng JSON | Diễn đạt qua Java API Client |
| Aggregation | Không phải lựa chọn chính | Có thể dùng phần query JSON nhưng cần kiểm soát cấu trúc request | Hỗ trợ trực tiếp qua builder |
| Refactor | Thuận tiện với property và code Java | Khó hơn vì JSON là chuỗi | Thuận tiện hơn với API có kiểu |
| Phù hợp | Filter nghiệp vụ và điều kiện cơ bản | Query JSON đã có hoặc query cố định | Query nâng cao, aggregation và DSL phức tạp |

Có thể chọn theo nguyên tắc:

- Bắt đầu với CriteriaQuery nếu điều kiện đơn giản và Criteria API hỗ trợ đầy đủ.
- Dùng StringQuery khi đã có JSON Query DSL và muốn giữ nguyên cấu trúc đó.
- Dùng NativeQuery khi cần các khả năng nâng cao, aggregation hoặc builder có kiểu của Elasticsearch Java API Client.

Không cần dùng cùng lúc cả ba implementation trong một truy vấn. Hãy chọn cách biểu diễn phù hợp nhất với cấu trúc query.

## 8. Thực thi query và đọc SearchHits

Sau khi xây dựng query bằng bất kỳ implementation nào, có thể thực thi theo cùng một API:

~~~java
SearchHits<Product> searchHits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

`SearchHits<Product>` chứa nhiều thông tin hơn danh sách entity thuần túy. Mỗi `SearchHit<Product>` có thể cung cấp:

- ID của document.
- Điểm liên quan (`score`).
- Sort values.
- Highlight fields.
- Nội dung entity đã ánh xạ.
- Inner hits nếu truy vấn có trả về.

Ví dụ lấy danh sách entity từ kết quả:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

List<Product> products = searchHits.getSearchHits()
    .stream()
    .map(SearchHit::getContent)
    .toList();
~~~

Nếu chỉ lấy `List<Product>`, ứng dụng có thể bỏ qua score, sort values, highlight và một số metadata khác. Khi xây dựng trang tìm kiếm cần hiển thị đoạn văn bản được tô sáng hoặc điểm liên quan, nên giữ `SearchHits`/`SearchHit` để sử dụng metadata.

## 9. Tạo query động theo tham số đầu vào

Trong ứng dụng thực tế, người dùng có thể chọn một hoặc nhiều bộ lọc. Ví dụ:

- Từ khóa có thể có hoặc không.
- Danh mục có thể không được chọn.
- Giá tối đa có thể trống.
- Trạng thái active có thể là true, false hoặc không lọc.

CriteriaQuery phù hợp để tạo điều kiện theo từng tham số có mặt:

~~~java
Criteria criteria = new Criteria();

if (keyword != null && !keyword.isBlank()) {
    criteria = criteria.and("name").matches(keyword);
}

if (category != null && !category.isBlank()) {
    criteria = criteria.and("category").is(category);
}

if (maxPrice != null) {
    criteria = criteria.and("price").lessThanEqual(maxPrice);
}

Query query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(
    page,
    size,
    Sort.by(Sort.Direction.ASC, "price")
));
~~~

Đây là ví dụ minh họa cách lắp ghép điều kiện. Cần chọn phép toán Criteria phù hợp với mapping: full-text search trên `name` cần analyzer và semantics phù hợp; điều kiện `is` trên `category` nên dùng field keyword.

Nếu điều kiện động cần nested query, script, aggregation hoặc nhiều nhánh bool phức tạp, có thể tạo NativeQuery bằng cách thêm từng điều kiện vào builder. Cách này giúp tránh ghép JSON thủ công và giữ query có cấu trúc.

Với StringQuery, nếu phải tạo query JSON động, nên dùng JSON serializer để escape dữ liệu đúng cách. Không ghép chuỗi từ đầu vào không tin cậy vào JSON Query DSL.

## 10. Phân trang, tổng số hit và giới hạn kết quả

Một truy vấn có thể đúng về điều kiện nhưng vẫn không phù hợp nếu trả quá nhiều document. Hãy cấu hình `Pageable`, sort và total hits theo nhu cầu giao diện.

Ví dụ:

~~~java
Pageable pageable = PageRequest.of(
    0,
    25,
    Sort.by(Sort.Direction.DESC, "createdAt")
);

query.setPageable(pageable);
query.setTrackTotalHits(false);
~~~

Nếu màn hình chỉ cần hiển thị danh sách trang hiện tại và nút “Xem thêm”, không nhất thiết phải lấy tổng số kết quả chính xác. Nếu cần hiển thị “Có 12.483 kết quả”, phải cân nhắc yêu cầu theo dõi total hits.

Với dữ liệu rất lớn, tránh dùng `from` quá sâu. Có thể dùng `search_after` và sort ổn định. Khi dùng `search_after`, lấy sort values của hit cuối cùng ở trang hiện tại rồi truyền chúng vào query tiếp theo. Không tự tạo sort values vì chúng phải khớp chính xác với sort đã dùng.

## 11. Những lỗi thường gặp khi xây dựng Query

**Dùng sai field type.** `term` trên text field có analyzer có thể không khớp như mong đợi; `match` trên keyword không mang semantics full-text như trên text. Kiểm tra mapping trước khi chọn toán tử.

**Nhầm Query của Spring Data với Query của Elasticsearch Java Client.** `org.springframework.data.elasticsearch.core.query.Query` là abstraction mà `ElasticsearchOperations` nhận. `co.elastic.clients.elasticsearch._types.query_dsl.Query` là kiểu query trong Java API Client, thường được tạo bên trong NativeQuery.

**Nghĩ rằng StringQuery có placeholder tự động.** StringQuery nhận JSON query string. Cơ chế placeholder `?0` thuộc một số khai báo repository như annotation `@Query`, không tự động áp dụng cho chuỗi StringQuery.

**Ghép JSON từ đầu vào trực tiếp.** Dấu nháy, ký tự escape hoặc nội dung không tin cậy có thể phá cấu trúc JSON. Dùng Criteria, NativeQuery hoặc JSON serializer.

**Dùng Criteria cho query vượt quá khả năng của nó.** Khi cần nested DSL, aggregation, script hoặc query nâng cao, chuyển sang NativeQuery thay vì cố tạo một chuỗi Criteria khó hiểu.

**Không nhóm AND/OR rõ ràng.** Các chuỗi Criteria mặc định kết hợp AND; OR được chuyển thành should. Dùng subCriteria để nhóm điều kiện và xác nhận logic truy vấn.

**Bỏ qua phân trang.** Truy vấn không giới hạn có thể tải quá nhiều document. Dùng Pageable hoặc cơ chế phân trang sâu phù hợp.

**Yêu cầu total hits chính xác không cần thiết.** Theo dõi tổng số hit chính xác có thể làm tăng chi phí tìm kiếm. Chỉ bật khi giao diện hoặc nghiệp vụ thực sự cần.

**Không kiểm tra query trên Elasticsearch thật.** Code có thể biên dịch nhưng query vẫn sai do mapping, analyzer hoặc dữ liệu. Integration test cần xác nhận kết quả thực tế.

## 12. Quy trình chọn và xây dựng Query

Có thể thực hiện theo trình tự sau:

1. Xác định dữ liệu cần tìm và mapping của các field.
2. Phân loại điều kiện thành full-text, exact match, range, nested hoặc aggregation.
3. Chọn CriteriaQuery nếu điều kiện cơ bản và có thể biểu diễn rõ bằng Criteria.
4. Chọn StringQuery nếu đã có JSON Query DSL ổn định và muốn truyền nguyên cấu trúc đó.
5. Chọn NativeQuery nếu cần Query DSL nâng cao, aggregation hoặc builder có kiểu.
6. Thêm các tùy chọn Query như Pageable, Sort, source filtering và total-hit tracking.
7. Gọi `ElasticsearchOperations.search(...)` với entity type và index coordinates.
8. Đọc `SearchHits` nếu cần score, sort values, highlight hoặc aggregation.
9. Kiểm tra bằng integration test với Elasticsearch tương thích phiên bản ứng dụng.
10. Theo dõi thời gian thực thi, số lượng kết quả và chi phí truy vấn trên dữ liệu gần với production.

## Kết luận

`Query` là abstraction giúp Spring Data Elasticsearch tách cách mô tả tìm kiếm khỏi cách gửi request. `CriteriaQuery` cung cấp API Criteria dễ đọc cho điều kiện thông dụng; `StringQuery` nhận trực tiếp Elasticsearch Query DSL dưới dạng JSON; `NativeQuery` dùng builder có kiểu từ Elasticsearch Java API Client cho truy vấn phức tạp và aggregation.

Ngoài query body, đối tượng Query còn mang các tham số thực thi như phân trang, sort, source filtering, total-hit tracking, preference, timeout và search_after. Chọn đúng implementation, cấu hình đúng tham số và đọc `SearchHits` khi cần metadata sẽ giúp phần tìm kiếm rõ ràng, kiểm soát được hiệu năng và phù hợp với khả năng của Elasticsearch.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Elasticsearch Operations and Queries](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Query API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/Query.html)
- [Spring Data Elasticsearch — Criteria API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/Criteria.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
