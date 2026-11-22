# Phân biệt `NativeQuery` với các API truy vấn cũ

Spring Data Elasticsearch cung cấp nhiều cách xây dựng truy vấn. Khi đọc code của dự án cũ hoặc nâng cấp phiên bản, rất dễ nhầm `NativeQuery` hiện đại với `NativeSearchQuery` và `NativeSearchQueryBuilder` của các phiên bản trước. Tên gần giống nhau, nhưng chúng dựa trên hai Elasticsearch Java client khác nhau và không dùng chung kiểu query builder.

Từ Spring Data Elasticsearch 5.x, native query được xây dựng trên **Elasticsearch Java API Client** mới, với kiểu `co.elastic.clients.elasticsearch._types.query_dsl.Query`. Các dự án Spring Data Elasticsearch 4.x thường dùng **Rest High Level Client (HLRC)** cũ, với `org.elasticsearch.index.query.QueryBuilder`, `QueryBuilders`, `NativeSearchQuery` và `NativeSearchQueryBuilder`.

Điểm cần nhớ khi nâng cấp: `NativeQuery` không phải chỉ là đổi tên class `NativeSearchQuery`. Cần chuyển phần tạo Query DSL từ API builder cũ sang kiểu query của Java API Client mới, đồng thời kiểm tra các tùy chọn sort, aggregation, highlight, paging và mapping.

```text
Spring Data Elasticsearch 4.x (legacy)
--------------------------------------
QueryBuilders / BoolQueryBuilder
              |
              v
       NativeSearchQuery
              |
              v
      Rest High Level Client

Spring Data Elasticsearch 5.x+
------------------------------
Elasticsearch Java API Client Query
              |
              v
          NativeQuery
              |
              v
      ElasticsearchOperations
              |
              v
       Elasticsearch cluster
```

## 1. Các API truy vấn chính trong Spring Data Elasticsearch

Spring Data Elasticsearch có nhiều abstraction vì truy vấn có mức độ phức tạp khác nhau:

| API | Cách xây dựng | Khi nào phù hợp |
|---|---|---|
| `CriteriaQuery` | Dùng `Criteria` và các phép so sánh/logic của Spring Data. | Điều kiện lọc thông dụng, dễ xây dựng động trong Java. |
| `StringQuery` | Truyền Query DSL dưới dạng chuỗi JSON. | Đã có JSON Query DSL hoặc cần một truy vấn tĩnh ngắn, dễ đọc. |
| `NativeQuery` | Dùng query type của Elasticsearch Java API Client mới. | Truy vấn Elasticsearch phức tạp, cần đầy đủ khả năng của Query DSL. |
| `NativeSearchQuery` (legacy) | Dùng `QueryBuilder` của Rest High Level Client. | Code cũ dựa trên Spring Data Elasticsearch 4.x/HLRC. |

Ba API đầu là các lựa chọn trong thế hệ Spring Data Elasticsearch mới. `NativeSearchQuery` là kiểu native query thuộc thế hệ cũ và không nên được xem là API thay thế trực tiếp cho `NativeQuery` trong dự án 5.x.

## 2. `NativeSearchQuery` và `NativeSearchQueryBuilder` ở thế hệ cũ

Trong Spring Data Elasticsearch 4.x, native query thường được tạo bằng `NativeSearchQueryBuilder`. Query condition sử dụng các lớp của HLRC, chẳng hạn `BoolQueryBuilder`, `QueryBuilders` và `SortBuilders`.

Ví dụ code legacy:

```java
import org.elasticsearch.index.query.BoolQueryBuilder;
import org.elasticsearch.index.query.QueryBuilders;
import org.elasticsearch.search.sort.SortBuilders;
import org.elasticsearch.search.sort.SortOrder;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.query.NativeSearchQuery;
import org.springframework.data.elasticsearch.core.query.NativeSearchQueryBuilder;

BoolQueryBuilder boolQuery = QueryBuilders.boolQuery()
        .must(QueryBuilders.matchQuery("title", "spring data"))
        .filter(QueryBuilders.termQuery("status", "PUBLISHED"));

NativeSearchQuery query = new NativeSearchQueryBuilder()
        .withQuery(boolQuery)
        .withPageable(PageRequest.of(0, 20))
        .withSort(SortBuilders.fieldSort("published_at").order(SortOrder.DESC))
        .build();
```

Ở đây:

- `QueryBuilders` tạo các query builder như `matchQuery`, `termQuery`, `boolQuery`.
- `BoolQueryBuilder` gom các điều kiện `must`, `filter`, `should` và `mustNot`.
- `NativeSearchQueryBuilder` gom query, pageable, sort và các tùy chọn tìm kiếm.
- `build()` tạo `NativeSearchQuery`, sau đó Spring Data chuyển nó thành request gửi qua HLRC.

Code này phụ thuộc vào các class thuộc namespace `org.elasticsearch.*` của Rest High Level Client. Khi dự án chuyển sang Spring Data Elasticsearch 5.x, các kiểu `QueryBuilder` cũ không phải kiểu query mà Java API Client mới sử dụng.

### Cách thực thi trong code cũ

Ở tầng service, query thường được gửi qua `ElasticsearchOperations`:

```java
SearchHits<ArticleDocument> hits =
        operations.search(query, ArticleDocument.class);
```

Ý tưởng sử dụng operations vẫn được giữ ở thế hệ mới. Phần cần thay đổi chủ yếu là loại query object và cách xây dựng Query DSL.

## 3. `NativeQuery` ở Spring Data Elasticsearch 5.x+

Spring Data Elasticsearch 5.x sử dụng Elasticsearch Java API Client. Query DSL được biểu diễn bằng các kiểu Java có type safety trong package `co.elastic.clients.elasticsearch._types.query_dsl`.

`NativeQuery` nằm trong package:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
```

Query object của Elasticsearch Java API Client:

```java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
```

Ví dụ tương đương với truy vấn legacy ở trên:

```java
Query esQuery = Query.of(q -> q
        .bool(b -> b
                .must(m -> m
                        .match(mm -> mm
                                .field("title")
                                .query("spring data")
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

NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(PageRequest.of(0, 20))
        .build();
```

Sau đó vẫn có thể gọi Spring Data operations:

```java
SearchHits<ArticleDocument> hits =
        operations.search(query, ArticleDocument.class);
```

Khác biệt cốt lõi nằm ở kiểu query:

- Legacy: `org.elasticsearch.index.query.QueryBuilder`.
- Hiện đại: `co.elastic.clients.elasticsearch._types.query_dsl.Query`.

Không thể truyền `BoolQueryBuilder` cũ vào `NativeQuery.withQuery(...)`, vì hai client có model request và kiểu dữ liệu khác nhau.

### Dùng lambda DSL trực tiếp

Elasticsearch Java API Client cho phép truyền lambda builder trực tiếp vào `NativeQuery` trong những overload được phiên bản hỗ trợ. Ví dụ:

```java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .bool(b -> b
                        .must(m -> m.match(mm -> mm
                                .field("title")
                                .query("spring data")
                        ))
                        .filter(f -> f.term(t -> t
                                .field("status")
                                .value(FieldValue.of("PUBLISHED"))
                        ))
                )
        )
        .withPageable(PageRequest.of(0, 20))
        .build();
```

Cách này giảm số biến trung gian, nhưng dùng `Query esQuery` riêng thường dễ đọc và tái sử dụng khi query được tạo từ nhiều nhánh logic.

## 4. Khác biệt giữa hai thế hệ API

| Nội dung | Legacy: Spring Data ES 4.x | Hiện đại: Spring Data ES 5.x+ |
|---|---|---|
| Elasticsearch client | Rest High Level Client (HLRC). | Elasticsearch Java API Client. |
| Native query class | `NativeSearchQuery`. | `NativeQuery`. |
| Builder | `NativeSearchQueryBuilder`. | `NativeQuery.builder()`. |
| Query condition | `QueryBuilder`, `BoolQueryBuilder`, `QueryBuilders`. | `co.elastic.clients.elasticsearch._types.query_dsl.Query`. |
| Sort DSL | Các builder cũ như `SortBuilders`. | Sort type của Java API Client hoặc Spring Data `Sort` qua query abstraction. |
| Package query | `org.elasticsearch.index.query.*`. | `co.elastic.clients.elasticsearch._types.query_dsl.*`. |
| Serialization/request model | HLRC request model. | Java API Client request model. |
| Khả năng dùng chung object query | Theo HLRC và phiên bản tương ứng. | Theo Java API Client và phiên bản tương ứng. |

Spring Data Elasticsearch 5.x không đơn giản bọc lại HLRC. Đây là thay đổi client và request model, vì vậy cần cập nhật imports, dependency, cấu hình client và code xây dựng query.

## 5. `NativeQuery` khác `CriteriaQuery` như thế nào?

`CriteriaQuery` và `NativeQuery` đều triển khai abstraction `Query` của Spring Data, nhưng cách mô tả điều kiện khác nhau.

### CriteriaQuery: query theo mô hình Spring Data

Ví dụ:

```java
Criteria criteria = new Criteria("status").is("PUBLISHED")
        .and("publishedAt").greaterThanEqual(startDate);

CriteriaQuery query = new CriteriaQuery(criteria);
```

Criteria API phù hợp với điều kiện lọc có cấu trúc, dễ sinh từ form tìm kiếm hoặc tham số service. Nó giúp code không phải thao tác trực tiếp với mọi kiểu Query DSL của Elasticsearch.

### NativeQuery: query theo Elasticsearch Java API Client

Ví dụ:

```java
Query esQuery = Query.of(q -> q
        .bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("body")
                        .query("distributed search")
                ))
                .should(s -> s.term(t -> t
                        .field("category")
                        .value(FieldValue.of("ENGINEERING"))
                ))
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .build();
```

NativeQuery thích hợp khi cần truy cập các khả năng Query DSL cụ thể như nested query, function score, script score, rank feature, kNN hoặc cấu trúc bool phức tạp. Tính năng thực tế còn phụ thuộc phiên bản Elasticsearch server và Java API Client.

### Nên chọn API nào?

| Nhu cầu | Lựa chọn gợi ý |
|---|---|
| Lọc theo một số field và phép so sánh thông thường | `CriteriaQuery`. |
| Query JSON tĩnh đã có sẵn | `StringQuery`. |
| Bool/nested/function score/kNN hoặc Query DSL chuyên sâu | `NativeQuery`. |
| Code cũ đang dùng `NativeSearchQuery` trên Spring Data ES 4.x | Giữ nguyên trong phạm vi phiên bản cũ hoặc chuyển đổi có kế hoạch sang `NativeQuery` khi nâng cấp. |

Không cần dùng `NativeQuery` cho mọi truy vấn. CriteriaQuery có thể dễ bảo trì hơn với điều kiện nghiệp vụ thông thường; NativeQuery nên được dùng khi cần quyền kiểm soát Query DSL.

## 6. `StringQuery` không phải `NativeQuery`

Một nhầm lẫn khác là coi `StringQuery` như native query mới. `StringQuery` nhận Query DSL dạng JSON string:

```java
StringQuery query = new StringQuery(
        """
        {
          "match": {
            "title": "spring data"
          }
        }
        """
);
```

`StringQuery` phù hợp khi JSON query đã được tạo sẵn hoặc cần lưu trong resource/config. Tuy nhiên:

- JSON là chuỗi nên lỗi cú pháp thường chỉ được phát hiện khi parse/thực thi.
- Không có type safety ở thời điểm biên dịch cho tên field hoặc cấu trúc query.
- Query động cần ghép chuỗi cẩn thận; không nối trực tiếp dữ liệu đầu vào chưa được xử lý.
- Việc tái cấu trúc query lớn khó hơn so với builder có kiểu.

NativeQuery dùng Java API Client DSL có type-safe builder, giúp IDE hỗ trợ autocomplete và compiler phát hiện một số lỗi kiểu dữ liệu/cấu trúc trước khi chạy.

## 7. Chuyển đổi một query legacy sang NativeQuery

Giả sử code cũ tìm bài viết có tiêu đề chứa `spring data`, trạng thái `PUBLISHED`, sắp xếp ngày xuất bản mới nhất và lấy 20 kết quả đầu.

### Code cũ

```java
BoolQueryBuilder boolQuery = QueryBuilders.boolQuery()
        .must(QueryBuilders.matchQuery("title", "spring data"))
        .filter(QueryBuilders.termQuery("status", "PUBLISHED"));

NativeSearchQuery oldQuery = new NativeSearchQueryBuilder()
        .withQuery(boolQuery)
        .withSort(SortBuilders.fieldSort("published_at").order(SortOrder.DESC))
        .withPageable(PageRequest.of(0, 20))
        .build();
```

### Code mới

```java
Query boolQuery = Query.of(q -> q
        .bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("title")
                        .query("spring data")
                ))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value(FieldValue.of("PUBLISHED"))
                ))
        )
);

NativeQuery newQuery = NativeQuery.builder()
        .withQuery(boolQuery)
        .withPageable(PageRequest.of(
                0,
                20,
                Sort.by(Sort.Order.desc("publishedAt"))
        ))
        .build();
```

Ở ví dụ mới, query DSL trực tiếp dùng tên field Elasticsearch trong `field(...)`, ví dụ `title` và `status`. Phần `Pageable` là Spring Data abstraction; sort có thể tham chiếu property Java `publishedAt` để mapping metadata ánh xạ sang `published_at` nếu entity khai báo `@Field(name = "published_at")`.

Khi chuyển đổi, không nên chỉ thay tên class. Cần so sánh request cũ và mới để bảo đảm:

1. Các điều kiện `must`, `filter`, `should`, `must_not` được giữ đúng.
2. Kiểu giá trị term/range đúng với mapping.
3. Sort, pageable, source filter và routing không bị mất.
4. Aggregation, highlight, suggest hoặc các option nâng cao được chuyển đầy đủ nếu có.
5. Query trả về cùng tập document và thứ tự phù hợp với yêu cầu nghiệp vụ.

## 8. Sort, Pageable và các tùy chọn truy vấn với NativeQuery

NativeQuery vẫn có thể dùng các abstraction Spring Data quen thuộc như `Pageable` và `Sort`:

```java
Pageable pageable = PageRequest.of(
        0,
        25,
        Sort.by(
                Sort.Order.desc("publishedAt"),
                Sort.Order.asc("slug")
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(pageable)
        .build();
```

Điều này giúp ứng dụng không phải tự xây dựng `from` và `size` cho các trang thông thường. Với truy vấn sâu, cần xem xét `search_after` và Point in Time thay vì tăng offset vô hạn.

NativeQuery cũng hỗ trợ các tùy chọn khác thông qua builder của Spring Data và các kiểu request của Java API Client, tùy phiên bản. Có thể cần cấu hình aggregation, highlight, source filtering, track total hits, runtime fields hoặc các thành phần truy vấn chuyên biệt. Hãy kiểm tra API builder trong dependency cụ thể của dự án trước khi dùng một method mới.

## 9. NativeQuery và ElasticsearchOperations

NativeQuery là query object; nó không tự gửi request đến cluster. Có thể thực thi qua `ElasticsearchOperations`:

```java
@Service
public class ArticleSearchService {

    private final ElasticsearchOperations operations;

    public ArticleSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ArticleDocument> search(String text) {
        Query esQuery = Query.of(q -> q
                .match(m -> m
                        .field("title")
                        .query(text)
                )
        );

        NativeQuery query = NativeQuery.builder()
                .withQuery(esQuery)
                .withPageable(PageRequest.of(0, 20))
                .build();

        return operations.search(query, ArticleDocument.class);
    }
}
```

`ElasticsearchOperations` giữ vai trò abstraction của Spring Data để thực thi query và chuyển đổi kết quả thành domain object. `SearchHits<T>` cung cấp các hit cùng metadata như score và tổng số hit theo cấu hình tracking.

Nếu cần gọi API Elasticsearch mà Spring Data chưa cung cấp abstraction phù hợp, có thể inject `ElasticsearchClient` và gọi Java API Client trực tiếp. Tuy nhiên, khi đó ứng dụng cần tự xử lý phần mapping/serialization và response theo API đang dùng. Không nên tạo client mới cho mỗi request; hãy tái sử dụng client do Spring quản lý.

## 10. Những thay đổi cần chú ý khi nâng cấp từ 4.x lên 5.x

Nâng cấp từ Spring Data Elasticsearch 4.x sang 5.x có thể ảnh hưởng nhiều hơn phần query builder:

### Dependency và client

- Spring Data Elasticsearch 4.x thường sử dụng Rest High Level Client.
- Spring Data Elasticsearch 5.x chuyển sang Elasticsearch Java API Client.
- Kiểm tra dependency tree để tránh kéo đồng thời client cũ và mới ngoài ý muốn.
- Ưu tiên Spring Boot dependency management/BOM để giữ các phiên bản Spring Data và Elasticsearch client tương thích.

### Imports và kiểu dữ liệu

Các import từ `org.elasticsearch.index.query.*` và `org.elasticsearch.search.sort.*` của HLRC không còn là kiểu query/sort tương ứng trong Java API Client mới. Thay bằng các type trong `co.elastic.clients.elasticsearch.*` hoặc Spring Data `Sort` phù hợp.

### Cấu hình client

Cấu hình kết nối, authentication, TLS và transport cũng thay đổi theo client mới. Không nên chỉ sửa query class nhưng giữ nguyên toàn bộ cấu hình HLRC cũ mà không kiểm tra auto-configuration của Spring Boot.

### Tính năng và response

Các request/response model có thể khác nhau. Nếu code đọc aggregation, highlight, suggest, profile hoặc metadata từ response cũ, cần chuyển đổi cách truy cập tương ứng. Hãy viết integration test cho các luồng quan trọng thay vì giả định response mới có cấu trúc giống hệt response HLRC.

### Kiểm tra tương thích phiên bản

Spring Boot, Spring Data Elasticsearch, Elasticsearch Java API Client và Elasticsearch server cần nằm trong ma trận tương thích. Không nâng riêng một dependency client mà bỏ qua BOM nếu chưa xác minh khả năng tương thích.

## 11. Những lỗi thường gặp khi chuyển từ NativeSearchQuery sang NativeQuery

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không import được `NativeSearchQueryBuilder` | Dự án đã chuyển sang Spring Data Elasticsearch 5.x. | Chuyển sang `NativeQuery.builder()`. |
| `withQuery` không nhận `BoolQueryBuilder` | `BoolQueryBuilder` thuộc HLRC, còn NativeQuery nhận query type của Java API Client. | Xây dựng `co.elastic.clients.elasticsearch._types.query_dsl.Query`. |
| Không tìm thấy `QueryBuilders` | Đang dùng import legacy của `org.elasticsearch.index.query`. | Dùng typed builder của Elasticsearch Java API Client. |
| Sort field không hoạt động sau migration | Dùng nhầm property Java và field name Elasticsearch hoặc mapping thay đổi. | Kiểm tra `@Field`, mapping thực tế và Query DSL được gửi. |
| Kết quả khác code cũ | Điều kiện bool, analyzer, sort hoặc kiểu giá trị đã thay đổi. | So sánh request cũ/mới và chạy regression tests. |
| Aggregation/highlight bị mất | Chỉ chuyển phần query chính mà quên các option khác của NativeSearchQuery. | Kiểm kê toàn bộ cấu hình cũ và chuyển từng phần. |
| Lỗi class/version khi chạy | Dependency HLRC, Java API Client hoặc Spring Data không tương thích. | Kiểm tra dependency tree và dùng BOM phù hợp. |
| Code cũ và mới dùng chung kiểu QueryBuilder | Hai client có model request riêng. | Tách adapter theo phiên bản hoặc chuyển hoàn toàn query builder. |

## 12. Chiến lược migration thực tế

Khi nâng cấp một ứng dụng lớn, nên chuyển theo từng nhóm truy vấn thay vì sửa đồng loạt mà không có kiểm soát.

1. **Kiểm kê query cũ:** tìm các chỗ dùng `NativeSearchQuery`, `NativeSearchQueryBuilder`, `QueryBuilders`, `BoolQueryBuilder`, `SortBuilders` và các lớp HLRC.
2. **Phân loại query:** query đơn giản có thể chuyển sang CriteriaQuery; query JSON tĩnh có thể dùng StringQuery; query DSL phức tạp nên chuyển sang NativeQuery.
3. **Chuyển từng query:** xây dựng lại điều kiện bằng Java API Client DSL và giữ nguyên semantics.
4. **Kiểm tra mapping:** xác nhận field name, type, analyzer và nested path.
5. **So sánh kết quả:** chạy cùng bộ dữ liệu và truy vấn ở môi trường kiểm thử, so sánh IDs, thứ tự, score và aggregation khi cần.
6. **Kiểm tra hiệu năng:** đo latency và tải cluster với query mới.
7. **Loại bỏ dependency cũ:** chỉ gỡ HLRC sau khi không còn code nào phụ thuộc vào nó và các thành phần khác đã được chuyển đổi.

Với query có nhiều nhánh logic, nên tách hàm tạo `Query` riêng để dễ unit test:

```java
private Query buildArticleQuery(String text, String status) {
    return Query.of(q -> q
            .bool(b -> b
                    .must(m -> m.match(mm -> mm
                            .field("title")
                            .query(text)
                    ))
                    .filter(f -> f.term(t -> t
                            .field("status")
                            .value(FieldValue.of(status))
                    ))
            )
    );
}
```

Service chỉ chịu trách nhiệm tạo tham số, thêm pageable/sort và thực thi query. Cách tổ chức này giúp việc thay đổi điều kiện không làm method service trở nên quá dài.

## 13. Khi nào không nên dùng NativeQuery?

NativeQuery mạnh và linh hoạt, nhưng cũng khiến code gắn chặt hơn với Query DSL của Elasticsearch. Không cần dùng nó nếu yêu cầu có thể biểu diễn rõ ràng bằng CriteriaQuery hoặc repository query method.

Nên cân nhắc:

- Dùng derived query method cho truy vấn đơn giản, ổn định và có tên method dễ hiểu.
- Dùng CriteriaQuery khi cần ghép điều kiện động từ nhiều tham số.
- Dùng StringQuery khi JSON DSL đã được quản lý như resource và ít thay đổi.
- Dùng NativeQuery khi cần khả năng của Query DSL mà các abstraction cao hơn không biểu diễn thuận tiện.
- Dùng Java API Client trực tiếp khi cần API cluster hoặc request/response cấp thấp mà Spring Data abstraction không bao phủ.

Chọn abstraction vừa đủ giúp code ít phụ thuộc vào chi tiết Elasticsearch và dễ thay đổi hơn. Tuy nhiên, với các tính năng tìm kiếm đặc thù, NativeQuery là lựa chọn tự nhiên trong Spring Data Elasticsearch hiện đại.

## 14. Những điểm cần nhớ

- `NativeSearchQuery` và `NativeSearchQueryBuilder` thuộc thế hệ Spring Data Elasticsearch cũ dựa trên Rest High Level Client.
- `NativeQuery` của Spring Data Elasticsearch 5.x+ dựa trên Elasticsearch Java API Client mới.
- Legacy query dùng `org.elasticsearch.index.query.QueryBuilder`; query mới dùng `co.elastic.clients.elasticsearch._types.query_dsl.Query`.
- Hai kiểu query không tương thích trực tiếp; không thể truyền `BoolQueryBuilder` cũ vào `NativeQuery`.
- `NativeQuery.builder()` kết hợp query DSL mới với pageable, sort và các tùy chọn Spring Data được phiên bản hỗ trợ.
- `CriteriaQuery` phù hợp với điều kiện có cấu trúc; `StringQuery` nhận JSON DSL dạng chuỗi; `NativeQuery` dùng typed Java API Client DSL.
- `ElasticsearchOperations.search(...)` vẫn là cách thực thi query phổ biến trong tầng Spring Data.
- Khi migration, kiểm kê cả query, sort, aggregation, highlight, client config và response handling.
- Dùng dependency management phù hợp và integration tests để xác nhận query mới giữ đúng kết quả, thứ tự và hiệu năng.

Hiểu rõ khác biệt giữa `NativeQuery` và các API truy vấn cũ giúp tránh lỗi kiểu dữ liệu khi nâng cấp Spring Data Elasticsearch. Hãy xem đây là thay đổi từ HLRC sang Elasticsearch Java API Client, chọn đúng abstraction cho từng truy vấn và kiểm tra kết quả thực tế trước khi loại bỏ code legacy.
