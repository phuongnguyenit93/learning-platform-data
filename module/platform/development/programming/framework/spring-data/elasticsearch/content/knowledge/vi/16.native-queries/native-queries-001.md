# NativeQuery và kiểu Query của Elasticsearch Java Client

Spring Data Elasticsearch cung cấp nhiều cách xây dựng truy vấn. Với các truy vấn đơn giản, có thể dùng `CriteriaQuery`. Khi cần biểu diễn đầy đủ query DSL của Elasticsearch, Spring Data cung cấp `NativeQuery`, cho phép sử dụng trực tiếp kiểu `Query` của Elasticsearch Java API Client.

Điểm dễ nhầm là có hai kiểu mang tên `Query`:

- **Spring Data Query**: abstraction của Spring Data Elasticsearch, được các phương thức như `ElasticsearchOperations.search(...)` nhận vào.
- **Elasticsearch Java Client Query**: kiểu query DSL có cấu trúc, thuộc package `co.elastic.clients.elasticsearch._types.query_dsl`.

`NativeQuery` kết nối hai lớp này: nó là một query của Spring Data và chứa query DSL được tạo bằng Elasticsearch Java Client.

## 1. Hai kiểu Query có vai trò khác nhau

Spring Data Elasticsearch định nghĩa interface:

~~~java
org.springframework.data.elasticsearch.core.query.Query
~~~

Đây là abstraction chung cho các truy vấn mà Spring Data có thể thực thi. Một số implementation quen thuộc:

- `CriteriaQuery`: query được xây dựng từ Criteria API.
- `StringQuery`: query được mô tả bằng chuỗi JSON DSL.
- `NativeQuery`: query sử dụng các kiểu dữ liệu của Elasticsearch Java API Client.

Trong khi đó, Elasticsearch Java API Client có kiểu:

~~~java
co.elastic.clients.elasticsearch._types.query_dsl.Query
~~~

Kiểu này biểu diễn các query DSL như `match`, `term`, `bool`, `range`, `multi_match` và nhiều loại query khác.

| Kiểu | Package | Vai trò |
|---|---|---|
| Spring Data `Query` | `org.springframework.data.elasticsearch.core.query.Query` | Abstraction đầu vào của Spring Data operations |
| `CriteriaQuery` | `org.springframework.data.elasticsearch.core.query.CriteriaQuery` | Tạo query bằng Criteria |
| `StringQuery` | `org.springframework.data.elasticsearch.core.query.StringQuery` | Tạo query từ JSON DSL dạng chuỗi |
| `NativeQuery` | `org.springframework.data.elasticsearch.client.elc.NativeQuery` | Bọc query DSL và các tùy chọn search của Java Client |
| Elasticsearch Java Client `Query` | `co.elastic.clients.elasticsearch._types.query_dsl.Query` | Mô tả query DSL có kiểu dữ liệu |

Do hai package cùng có tên `Query`, cần chú ý import. Trong code sử dụng `NativeQuery`, có thể đặt tên biến là `elasticsearchQuery` và chỉ import kiểu Query của Java Client để tránh nhầm lẫn.

## 2. NativeQuery là gì?

`NativeQuery` là implementation của Spring Data Query abstraction. Nó cho phép truyền query DSL được xây dựng bằng Elasticsearch Java API Client vào Spring Data Elasticsearch.

Luồng xử lý:

~~~mermaid
flowchart TD
    A["Elasticsearch Java Client Query"] --> B["NativeQuery.Builder"]
    B --> C["NativeQuery"]
    C --> D["Spring Data Query abstraction"]
    D --> E["ElasticsearchOperations.search"]
    E --> F["Elasticsearch Java Client"]
    F --> G["Elasticsearch cluster"]
    G --> H["Search response"]
    H --> I["SearchHits<Entity>"]
~~~

`NativeQuery` có thể mang nhiều thông tin của một search request, chẳng hạn:

- Query DSL chính.
- Filter query.
- Pageable và sort.
- Aggregations.
- Highlight.
- Track total hits.
- Các tùy chọn search khác được Spring Data hỗ trợ.

Query DSL bên trong `NativeQuery` là kiểu của Elasticsearch Java Client. `NativeQuery` giúp Spring Data sử dụng query đó cùng mapping metadata và conversion của entity.

## 3. Tạo Query bằng Elasticsearch Java API Client

Elasticsearch Java API Client cung cấp builder có kiểu dữ liệu để tạo query. Thay vì tự ghép JSON string, ta tạo đối tượng `Query` bằng `Query.of(...)`.

Ví dụ một truy vấn `match`:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query elasticsearchQuery = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("wireless keyboard")
        )
);
~~~

Trong ví dụ:

- `Query.of(...)` tạo một query object.
- `match(...)` chọn loại query toàn văn.
- `field("name")` chỉ định field được tìm kiếm.
- `query("wireless keyboard")` là nội dung người dùng nhập.

Kết quả là một đối tượng Query bất biến, mô tả cấu trúc DSL. Builder hỗ trợ kiểm tra kiểu dữ liệu trong lúc biên dịch, giúp giảm lỗi do sai cấu trúc JSON hoặc sai tên thuộc tính.

### Truy vấn term

Đối với field keyword như trạng thái, dùng `term`:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query statusQuery = Query.of(q -> q
        .term(t -> t
                .field("status")
                .value(FieldValue.of("PUBLISHED"))
        )
);
~~~

`FieldValue` là kiểu giá trị dùng trong Elasticsearch Java API Client cho các term query. Ở đây, giá trị chuỗi được biểu diễn bằng `FieldValue.of(...)`.

`term` so khớp term đã được lập chỉ mục. Với field `text` đã qua analyzer, cần chú ý token thực tế; field `keyword` thường phù hợp hơn cho trạng thái và mã cần so khớp nguyên vẹn.

## 4. Kết hợp nhiều điều kiện bằng bool query

Một biểu mẫu tìm kiếm thực tế thường cần kết hợp tìm kiếm toàn văn với các filter chính xác.

Ví dụ: tìm sản phẩm theo từ khóa trong tên, đồng thời chỉ lấy sản phẩm có trạng thái `PUBLISHED`:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query elasticsearchQuery = Query.of(q -> q
        .bool(b -> b
                .must(m -> m
                        .match(mm -> mm
                                .field("name")
                                .query("wireless keyboard")
                        )
                )
                .filter(f -> f
                        .term(t -> t
                                .field("status")
                                .value(FieldValue.of("PUBLISHED"))
                        )
                )
        )
);
~~~

Ý nghĩa:

- `bool` kết hợp các điều kiện.
- `must` chứa điều kiện tìm kiếm có thể ảnh hưởng relevance score.
- `filter` chứa điều kiện lọc không cần tính relevance score.
- `match` phân tích văn bản truy vấn theo search analyzer.
- `term` so khớp giá trị trạng thái.

Một số nhánh thường dùng trong bool query:

| Nhánh | Ý nghĩa |
|---|---|
| `must` | Điều kiện phải khớp và có thể tham gia tính điểm |
| `filter` | Điều kiện phải khớp nhưng không tính điểm liên quan |
| `should` | Điều kiện tùy chọn hoặc OR, tùy minimum_should_match và cấu trúc bool |
| `must_not` | Điều kiện loại trừ |

### Kết hợp OR bằng should

Ví dụ muốn lấy sản phẩm có trạng thái `FEATURED` hoặc có nhãn `PROMOTED`:

~~~java
Query elasticsearchQuery = Query.of(q -> q
        .bool(b -> b
                .should(s -> s
                        .term(t -> t
                                .field("status")
                                .value(FieldValue.of("FEATURED"))
                        )
                )
                .should(s -> s
                        .term(t -> t
                                .field("label")
                                .value(FieldValue.of("PROMOTED"))
                        )
                )
                .minimumShouldMatch("1")
        )
);
~~~

`minimumShouldMatch("1")` yêu cầu ít nhất một nhánh `should` phải khớp. Khi kết hợp `must` hoặc `filter` với `should`, hãy đặt rõ `minimum_should_match` nếu nghiệp vụ yêu cầu OR bắt buộc. Nếu không, các nhánh should có thể chỉ đóng vai trò tăng điểm theo quy tắc mặc định của bool query.

## 5. Đóng gói Elasticsearch Query vào NativeQuery

Sau khi tạo query DSL, truyền nó vào `NativeQuery.builder().withQuery(...)`.

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query elasticsearchQuery = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("wireless keyboard")
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .build();
~~~

`nativeQuery` lúc này là một Spring Data Query. Có thể truyền nó vào `ElasticsearchOperations.search(...)`.

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> hits =
        operations.search(nativeQuery, ProductDocument.class);
~~~

Spring Data sử dụng `ProductDocument.class` để biết cách chuyển đổi từng search hit thành entity. Query DSL quyết định điều kiện tìm kiếm; entity class quyết định kiểu dữ liệu Java nhận về và mapping metadata liên quan.

## 6. Thêm phân trang và sắp xếp

`NativeQuery` hỗ trợ các tùy chọn search của Spring Data, trong đó có pageable.

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withPageable(
                PageRequest.of(
                        0,
                        20,
                        Sort.by(Sort.Direction.DESC, "createdAt")
                )
        )
        .build();
~~~

Trong ví dụ:

- Trang đầu tiên có index `0`.
- Mỗi trang có tối đa `20` kết quả.
- Kết quả được sắp xếp theo `createdAt` giảm dần.

Field dùng để sort phải có mapping hỗ trợ sort, thường là keyword, numeric hoặc date. Không nên sort trực tiếp trên field text thông thường nếu field đó không có doc values.

Với phân trang sâu, cần cân nhắc `search_after` và sort ổn định thay vì tăng `from/size` quá lớn.

## 7. Phân biệt query và filter trong NativeQuery

Có thể mô tả điều kiện tìm kiếm và điều kiện filter bên trong một bool query như ví dụ trước. `NativeQuery` cũng cung cấp builder method riêng cho filter trong các phiên bản hỗ trợ.

Ví dụ:

~~~java
NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(nameQuery)
        .withFilter(statusFilter)
        .build();
~~~

Ở đây `nameQuery` và `statusFilter` đều là đối tượng Elasticsearch Java Client `Query`.

Việc tách query và filter có ý nghĩa:

- Query chính phục vụ matching và scoring.
- Filter bổ sung điều kiện bắt buộc mà không cần relevance score.
- Cấu trúc query thể hiện rõ ý đồ nghiệp vụ.

Có thể dùng bool query thay vì tách `withFilter`; cả hai cách đều có thể biểu diễn điều kiện. Hãy chọn một cấu trúc nhất quán để query dễ đọc và dễ bảo trì. Kiểm tra API của phiên bản Spring Data Elasticsearch đang dùng nếu sử dụng các builder method nâng cao.

## 8. Tích hợp NativeQuery với ElasticsearchOperations

Một service có thể nhận query từ input, tạo Java Client Query, đóng gói thành NativeQuery và thực thi:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(
            String keyword,
            String status
    ) {
        Query elasticsearchQuery = Query.of(q -> q
                .bool(b -> b
                        .must(m -> m
                                .match(mm -> mm
                                        .field("name")
                                        .query(keyword)
                                )
                        )
                        .filter(f -> f
                                .term(t -> t
                                        .field("status")
                                        .value(FieldValue.of(status))
                                )
                        )
                )
        );

        NativeQuery nativeQuery = NativeQuery.builder()
                .withQuery(elasticsearchQuery)
                .build();

        return operations.search(
                nativeQuery,
                ProductDocument.class
        );
    }
}
~~~

`ElasticsearchOperations` là abstraction của Spring Data. Service không cần tự tạo HTTP request hay tự parse JSON response. Spring Data thực thi query thông qua client đã được cấu hình và chuyển đổi kết quả thành `SearchHits<ProductDocument>`.

Trong ứng dụng thật, cần validate `keyword` và `status`, xử lý trường hợp không có điều kiện, giới hạn kết quả và thêm filter quyền truy cập/tenant từ security context.

## 9. Đọc kết quả SearchHits

`operations.search(...)` thường trả về `SearchHits<T>`, không chỉ là danh sách entity đơn thuần.

~~~java
SearchHits<ProductDocument> hits =
        operations.search(nativeQuery, ProductDocument.class);

for (var hit : hits) {
    ProductDocument product = hit.getContent();
    float score = hit.getScore();

    System.out.println(product.getName());
    System.out.println(score);
}
~~~

Mỗi `SearchHit<T>` có thể chứa:

- Nội dung entity.
- Relevance score.
- Document ID.
- Index chứa document.
- Sort values và metadata khác tùy response.

Nếu chỉ cần danh sách entity, có thể chuyển `hits.getSearchHits()` thành list nội dung. Nếu giao diện cần relevance hoặc ID/index metadata, giữ lại cấu trúc SearchHit.

## 10. NativeQuery và CriteriaQuery khác nhau thế nào?

Cả hai đều có thể được truyền vào phương thức Spring Data operations vì cùng triển khai abstraction `org.springframework.data.elasticsearch.core.query.Query`.

| Tiêu chí | CriteriaQuery | NativeQuery |
|---|---|---|
| Cách xây dựng | Criteria API của Spring Data | Elasticsearch Java Client Query DSL |
| Độ trừu tượng | Cao hơn, API đơn giản | Gần với Elasticsearch DSL |
| Query phức tạp | Phù hợp với điều kiện phổ biến | Phù hợp với query DSL nâng cao |
| Bool query lồng nhau | Có thể biểu diễn nhưng đôi khi khó đọc | Biểu diễn trực tiếp bằng typed DSL |
| Tính năng Elasticsearch mới | Phụ thuộc mức hỗ trợ của Criteria | Có thể tiếp cận các query type được Java Client hỗ trợ |
| Đọc và bảo trì | Dễ với filter đơn giản | Rõ ràng khi cần kiểm soát cấu trúc DSL |

Ví dụ CriteriaQuery:

~~~java
Criteria criteria = new Criteria("status").is("PUBLISHED")
        .and("price").greaterThanEqual(100000);

CriteriaQuery criteriaQuery = new CriteriaQuery(criteria);
~~~

Ví dụ NativeQuery:

~~~java
import co.elastic.clients.json.JsonData;
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query elasticsearchQuery = Query.of(q -> q
        .bool(b -> b
                .filter(f -> f
                        .term(t -> t
                                .field("status")
                                .value(FieldValue.of("PUBLISHED"))
                        )
                )
                .filter(f -> f
                        .range(r -> r
                                .field("price")
                                .gte(JsonData.of(100000.0))
                        )
                )
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .build();
~~~

NativeQuery cho phép thể hiện cấu trúc query DSL gần với request JSON của Elasticsearch, nhưng cần hiểu các kiểu dữ liệu và builder API của Java Client.

Không cần dùng NativeQuery cho mọi truy vấn. Với filter đơn giản, CriteriaQuery thường dễ đọc hơn. Chọn NativeQuery khi cần kiểm soát chi tiết DSL hoặc dùng tính năng không được Criteria API biểu diễn thuận tiện.

## 11. NativeQuery và StringQuery khác nhau thế nào?

`StringQuery` nhận query DSL dưới dạng chuỗi JSON:

~~~java
import org.springframework.data.elasticsearch.core.query.StringQuery;

StringQuery query = new StringQuery("""
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
        """);
~~~

Trong khi đó, NativeQuery nhận query object có kiểu dữ liệu:

~~~java
Query elasticsearchQuery = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("wireless keyboard")
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .build();
~~~

| Tiêu chí | StringQuery | NativeQuery |
|---|---|---|
| Đầu vào | JSON DSL dạng chuỗi | Query object của Java Client |
| Kiểm tra kiểu khi biên dịch | Hạn chế | Tốt hơn nhờ typed builder |
| Dễ sao chép từ Dev Tools | Cao | Cần chuyển DSL sang builder |
| Refactor theo API Java | Khó hơn | Thuận tiện hơn |
| Phù hợp | Query JSON có sẵn hoặc cấu trúc nhỏ | Query được tạo trong code Java và cần type safety |

Nếu query JSON được quản lý bên ngoài hoặc được sao chép từ Kibana Dev Tools, StringQuery có thể thuận tiện. Nếu query được tạo động trong code, NativeQuery giúp giảm lỗi cấu trúc và kiểu dữ liệu.

## 12. Phân biệt với API cũ RestHighLevelClient

Các ví dụ Spring Data Elasticsearch đời cũ thường dùng `NativeSearchQuery` và `QueryBuilders` thuộc Elasticsearch Rest High Level Client.

Ví dụ kiểu cũ:

~~~java
// API cũ, minh họa để nhận diện
QueryBuilder queryBuilder =
        QueryBuilders.matchQuery("name", "wireless keyboard");
~~~

Trong Spring Data Elasticsearch 5.x, tích hợp client mặc định dựa trên Elasticsearch Java API Client. Khi đó, kiểu query là:

~~~java
co.elastic.clients.elasticsearch._types.query_dsl.Query
~~~

và wrapper Spring Data là:

~~~java
org.springframework.data.elasticsearch.client.elc.NativeQuery
~~~

Không trộn `QueryBuilder` của RestHighLevelClient với `NativeQuery` của Java API Client. Đây là hai thế hệ API khác nhau, có package, kiểu dữ liệu và cách khởi tạo khác nhau.

Khi nâng cấp dự án, cần kiểm tra phiên bản Spring Data Elasticsearch và Elasticsearch client được quản lý trong dependency. Trong ứng dụng Spring Boot, nên ưu tiên dependency management tương thích của Boot thay vì tự nâng riêng một client.

## 13. Các lỗi thường gặp

### Import nhầm Query

Hai kiểu Query có cùng tên đơn giản. Nếu import nhầm `org.springframework.data.elasticsearch.core.query.Query` rồi gọi `Query.of(...)`, code sẽ không biên dịch vì Spring Data Query không có builder đó.

Hãy import:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
~~~

và dùng `NativeQuery` để đóng gói.

### Truyền nhầm kiểu vào NativeQuery

`NativeQuery.builder().withQuery(...)` cần query DSL của Java Client. Không truyền một `Criteria` object hoặc một Spring Data Query implementation khác vào vị trí này.

### Dùng term cho field text

`term` không phân tích input như `match`. Nếu field text đã được lowercase hoặc stemming, giá trị truy vấn nguyên bản có thể không khớp token trong index.

### Dùng sai FieldValue

Một số term query của Java Client yêu cầu `FieldValue`. Dùng `FieldValue.of(...)` với đúng kiểu dữ liệu thay vì truyền một object không tương thích.

### Nhầm filter với must

`must` có thể tham gia scoring; `filter` không tính điểm. Dùng filter cho điều kiện như status, tenant, category khi không cần relevance score.

### Dùng field chưa có trong mapping

Java Client builder kiểm tra kiểu cấu trúc query, nhưng không thể tự biết mọi field trong index có mapping đúng hay không. Nếu query field không tồn tại hoặc sai kiểu, kết quả có thể rỗng hoặc request có thể lỗi tùy loại query. Kiểm tra mapping thực tế.

### Dùng query DSL của phiên bản client khác

API builder có thể thay đổi theo phiên bản Elasticsearch Java API Client. Đảm bảo import và dependency tương thích với Spring Data Elasticsearch đang dùng.

## 14. Quy trình xây dựng NativeQuery

Khi cần tạo truy vấn bằng Elasticsearch Java Client và thực thi qua Spring Data:

1. Xác định field, kiểu mapping và mục tiêu tìm kiếm.
2. Chọn query DSL phù hợp như `match`, `term`, `bool`, `range` hoặc `multi_match`.
3. Tạo đối tượng `co.elastic.clients.elasticsearch._types.query_dsl.Query` bằng `Query.of(...)`.
4. Kết hợp các điều kiện bằng bool query; dùng `filter` cho điều kiện không cần scoring.
5. Đóng gói query vào `NativeQuery.builder().withQuery(...)`.
6. Thêm pageable, sort, aggregation hoặc tùy chọn search nếu cần.
7. Gọi `ElasticsearchOperations.search(...)` với entity class và index coordinates phù hợp.
8. Đọc kết quả qua `SearchHits<T>` hoặc chuyển thành DTO.
9. Kiểm tra query với mapping và dữ liệu thực tế.
10. Đảm bảo các query field, sort field và filter quyền truy cập đều được kiểm soát.

## Kết luận

`NativeQuery` là cầu nối giữa Spring Data Elasticsearch Query abstraction và Elasticsearch Java API Client query DSL. Kiểu `co.elastic.clients.elasticsearch._types.query_dsl.Query` mô tả điều kiện tìm kiếm bằng builder có kiểu dữ liệu; `NativeQuery` đóng gói nó cùng các tùy chọn search để truyền vào `ElasticsearchOperations`. Dùng CriteriaQuery cho truy vấn phổ biến, NativeQuery khi cần kiểm soát DSL chi tiết, và luôn phân biệt rõ hai kiểu cùng tên `Query` để tránh import nhầm.
