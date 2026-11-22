# Kết hợp `CriteriaQuery` với `Sort` và `Pageable`

Trong Spring Data Elasticsearch, `CriteriaQuery` cho phép xây dựng điều kiện tìm kiếm bằng Java API thay vì viết toàn bộ Query DSL dưới dạng JSON. Khi kết hợp với `Sort` và `Pageable`, ứng dụng có thể lọc dữ liệu theo nhiều điều kiện, sắp xếp kết quả theo một hoặc nhiều field, rồi lấy từng trang có kích thước xác định.

Ba thành phần đảm nhiệm ba nhiệm vụ khác nhau:

- **Criteria** mô tả điều kiện lọc, ví dụ trạng thái là `ACTIVE`, giá lớn hơn một ngưỡng hoặc ngày tạo nằm trong một khoảng.
- **Sort** xác định thứ tự kết quả, ví dụ giá giảm dần rồi tên tăng dần.
- **Pageable** xác định trang cần lấy và số document tối đa trong trang; nó cũng có thể mang thông tin sort.

`CriteriaQuery` kết hợp các điều kiện Criteria thành một query, sau đó được gửi qua `ElasticsearchOperations` để Elasticsearch thực thi.

```text
Criteria
  status = ACTIVE
  price >= 100
  category = KEYBOARD
      |
      v
CriteriaQuery
      |
      +---- Sort: createdAt DESC, sku ASC
      |
      +---- Pageable: page 0, size 20
      |
      v
ElasticsearchOperations.search(...)
      |
      v
Elasticsearch cluster
      |
      v
SearchHits / SearchPage
```

## 1. `CriteriaQuery` là gì?

`CriteriaQuery` là implementation của Spring Data Elasticsearch `Query`, được tạo từ một đối tượng `Criteria`. `Criteria` mô tả các điều kiện như so sánh, khớp chính xác, tồn tại field hoặc kết hợp điều kiện AND/OR.

Ví dụ entity:

```java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(name = "created_at", type = FieldType.Date)
    private Instant createdAt;

    // constructors, getters, setters
}
```

Tạo điều kiện cơ bản:

```java
Criteria criteria = new Criteria("status").is("ACTIVE")
        .and("category").is("KEYBOARD")
        .and("price").greaterThanEqual(new BigDecimal("100"));

CriteriaQuery query = new CriteriaQuery(criteria);
```

Criteria trên yêu cầu document có `status` là `ACTIVE`, `category` là `KEYBOARD` và `price` lớn hơn hoặc bằng 100. Đây là điều kiện lọc; nó chưa quy định thứ tự hoặc số lượng kết quả trả về.

Các tên property truyền vào Criteria thường là tên property trong domain class để Spring Data có thể áp dụng mapping metadata. Nếu entity dùng `@Field(name = "created_at")` cho property `createdAt`, khi dùng Spring Data abstraction hãy ưu tiên tham chiếu property Java `createdAt`; với raw Query DSL gửi trực tiếp đến Elasticsearch, dùng field name thực tế `created_at`.

## 2. Kết hợp nhiều điều kiện Criteria

Có thể nối điều kiện theo AND bằng `and(...)`:

```java
Criteria criteria = new Criteria("status").is("ACTIVE")
        .and("price").greaterThanEqual(100)
        .and("price").lessThan(500)
        .and("category").is("KEYBOARD");
```

Ví dụ này tìm sản phẩm đang hoạt động, thuộc nhóm bàn phím và có giá từ 100 đến dưới 500. Có thể dùng các phép so sánh khác như `greaterThan`, `lessThanEqual`, `between`, `in`, `notIn`, `contains`, `startsWith`, `endsWith` hoặc `exists` tùy kiểu field và phiên bản API.

Kết hợp OR bằng nhóm Criteria:

```java
Criteria active = new Criteria("status").is("ACTIVE");
Criteria featured = new Criteria("featured").is(true);

Criteria criteria = new Criteria().or(active, featured);
CriteriaQuery query = new CriteriaQuery(criteria);
```

Điều kiện trên tìm document thỏa `status = ACTIVE` hoặc `featured = true`. Khi query có nhiều nhóm AND/OR, nên tạo biến Criteria riêng và đặt tên theo ý nghĩa nghiệp vụ để dễ đọc.

Ví dụ nhóm điều kiện phức hợp:

```java
Criteria statusCriteria = new Criteria("status").is("ACTIVE");

Criteria priceCriteria = new Criteria("price").lessThan(100)
        .or(new Criteria("price").greaterThan(1000));

Criteria criteria = statusCriteria.and(priceCriteria);
```

Kết quả là các document đang hoạt động và có giá dưới 100 hoặc trên 1000. Với biểu thức phức tạp, hãy kiểm tra Query DSL được sinh ra để bảo đảm grouping AND/OR đúng ý định.

## 3. Thêm `Sort` vào `CriteriaQuery`

`Sort` của Spring Data mô tả thứ tự sắp xếp. Một `Sort` có thể gồm nhiều `Sort.Order`; thứ tự các order quyết định mức ưu tiên.

Ví dụ sắp xếp giá giảm dần:

```java
Sort sort = Sort.by(Sort.Order.desc("price"));
```

Sắp xếp theo nhiều field:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku")
);
```

Thứ tự được áp dụng như sau:

1. `createdAt` giảm dần, document mới hơn đứng trước.
2. Nếu nhiều document có cùng `createdAt`, `sku` tăng dần được dùng để phân định thứ tự.

Có thể gắn sort trực tiếp vào query:

```java
CriteriaQuery query = new CriteriaQuery(criteria);
query.addSort(sort);
```

Trong các phiên bản Spring Data Elasticsearch có API `Query.addSort`, cũng có thể thêm từng order bằng overload tương ứng. Cú pháp chính xác cần đối chiếu với phiên bản dependency của dự án.

### Sort tăng dần và giảm dần

```java
Sort ascending = Sort.by(Sort.Order.asc("price"));
Sort descending = Sort.by(Sort.Order.desc("price"));
```

`asc` sắp xếp tăng dần; `desc` sắp xếp giảm dần. Với nhiều order, order khai báo trước có ưu tiên cao hơn.

### Sort theo field có tên khác property Java

Nếu entity khai báo:

```java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
```

Khi dùng Spring Data `Sort` trên domain type, thông thường tham chiếu property Java:

```java
Sort sort = Sort.by(Sort.Order.desc("createdAt"));
```

Mapping metadata giúp Spring Data ánh xạ property sang field thực tế. Nếu tự viết native Elasticsearch sort hoặc raw request, dùng `created_at`. Không nên trộn tên property Java và tên field Elasticsearch trong cùng một lớp abstraction mà không xác định rõ API đang nhận loại tên nào.

## 4. Sort trên field nào?

Elasticsearch chỉ sắp xếp hiệu quả trên các field có kiểu và cấu hình phù hợp. Các field thường dùng để sort gồm:

- `keyword`: mã, trạng thái, tên chuẩn hóa hoặc giá trị phân loại.
- Kiểu số: `integer`, `long`, `float`, `double`, `scaled_float`.
- `date`: thời điểm tạo, ngày cập nhật hoặc thời hạn.
- Boolean và một số kiểu scalar khác theo khả năng sort của Elasticsearch.

Field `text` thường không có doc values và không phù hợp để sort trực tiếp. Nếu cần vừa full-text search vừa sort theo toàn bộ chuỗi, khai báo multi-field `keyword`:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
```

Sau đó sort theo `name.keyword` trong native Elasticsearch query. Với Spring Data mapping, hãy xác định cách property/subfield được biểu diễn trong `Sort` của phiên bản đang dùng; có thể dùng tên field con khi API yêu cầu field path Elasticsearch.

Không nên bật `fielddata` cho field `text` chỉ để sort nếu có thể dùng subfield `keyword`. Fielddata có thể tiêu tốn nhiều heap và làm tăng áp lực bộ nhớ.

### Sort ổn định khi nhiều document có cùng giá trị

Nếu chỉ sort theo `createdAt`, nhiều document có cùng timestamp có thể xuất hiện theo thứ tự không ổn định giữa các lần truy vấn. Khi phân trang, điều này có thể khiến document bị lặp hoặc bị bỏ qua giữa hai trang nếu thứ tự thay đổi.

Nên thêm một field phụ có giá trị duy nhất và có thể sort, ví dụ `sku` kiểu `keyword`:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku")
);
```

`sku` làm tie-breaker để xác định thứ tự giữa các document cùng thời điểm. Không nên mặc định dùng `_id` làm field sort: `_id` là metadata đặc biệt và không được cấu hình doc values để sort thông thường. Hãy lưu một field định danh sort được nếu cần thứ tự ổn định.

## 5. Thêm `Pageable` để phân trang

`Pageable` xác định trang và kích thước trang. Với `PageRequest`, số trang bắt đầu từ 0:

```java
Pageable pageable = PageRequest.of(0, 20);
```

Ý nghĩa:

- `0`: trang đầu tiên.
- `20`: tối đa 20 document trong trang.

Trang thứ hai:

```java
Pageable pageable = PageRequest.of(1, 20);
```

Spring Data chuyển thông tin này thành phân trang offset/limit tương ứng khi tạo search request. Có thể hình dung:

```text
Page 0, size 20  -> from = 0,  size = 20
Page 1, size 20  -> from = 20, size = 20
Page 2, size 20  -> from = 40, size = 20
```

`PageRequest.of(page, size)` yêu cầu `page` không âm và `size` lớn hơn 0. Nên giới hạn page size ở API service để tránh client yêu cầu một trang quá lớn làm tăng tải cluster và bộ nhớ ứng dụng.

## 6. Đặt Sort bên trong Pageable

Một cách phổ biến là truyền `Sort` vào `PageRequest`. Khi đó cùng một object `Pageable` chứa cả số trang, kích thước và thứ tự sắp xếp:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku")
);

Pageable pageable = PageRequest.of(0, 20, sort);

CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(pageable);
```

Đây là cách thuận tiện khi sort gắn với cách phân trang của endpoint. Khi đổi trang, có thể tạo `PageRequest` mới với page index khác nhưng giữ nguyên sort.

Ví dụ hàm service:

```java
public SearchHits<ProductDocument> searchProducts(
        String status,
        int page,
        int size) {

    Criteria criteria = new Criteria("status").is(status);

    Sort sort = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("sku")
    );

    Pageable pageable = PageRequest.of(page, size, sort);

    CriteriaQuery query = new CriteriaQuery(criteria);
    query.setPageable(pageable);

    return operations.search(query, ProductDocument.class);
}
```

Service nhận page và size từ caller, xây dựng điều kiện, tạo sort, gắn pageable rồi gọi `ElasticsearchOperations.search`. Đoạn code giả định `operations` là bean `ElasticsearchOperations` được inject.

## 7. Thêm Pageable và Sort riêng trên Query

`Query` của Spring Data Elasticsearch có thể quản lý pageable và sort riêng. Có thể đặt pageable không có sort rồi thêm sort cho query:

```java
CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(0, 20));
query.addSort(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku")
));
```

Cách này hữu ích khi sort được xây dựng độc lập với thông tin trang. Tuy nhiên, tránh khai báo sort ở cả `Pageable` và `Query` nếu không có chủ đích rõ ràng. Khi có hai nguồn sort, việc kết hợp hoặc xử lý trùng order phụ thuộc cách implementation query trong phiên bản Spring Data đang dùng.

Nên chọn một nguồn làm nơi định nghĩa sort:

- Sort là một phần của API phân trang: dùng `PageRequest.of(page, size, sort)`.
- Pageable chỉ xác định offset/size, sort được xây dựng riêng: dùng `query.addSort(...)`.

## 8. Ví dụ hoàn chỉnh: CriteriaQuery + Sort + Pageable

Giả sử cần tìm các sản phẩm đang hoạt động, thuộc nhóm `KEYBOARD`, có giá từ 100 đến dưới 500; kết quả được sắp xếp theo ngày tạo mới nhất rồi SKU tăng dần, mỗi trang 20 sản phẩm.

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.Criteria;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public List<ProductDocument> search(int page, int size) {
        Criteria criteria = new Criteria("status").is("ACTIVE")
                .and("category").is("KEYBOARD")
                .and("price").greaterThanEqual(new BigDecimal("100"))
                .and("price").lessThan(new BigDecimal("500"));

        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("sku")
        );

        Pageable pageable = PageRequest.of(page, size, sort);

        CriteriaQuery query = new CriteriaQuery(criteria);
        query.setPageable(pageable);

        SearchHits<ProductDocument> hits =
                operations.search(query, ProductDocument.class);

        return hits.getSearchHits().stream()
                .map(SearchHit::getContent)
                .toList();
    }
}
```

Trong ví dụ:

1. Criteria xác định tập document cần tìm.
2. Sort quy định thứ tự kết quả.
3. Pageable chọn trang và kích thước trang.
4. `CriteriaQuery` mang cả ba phần đến `ElasticsearchOperations`.
5. `SearchHits` chứa các hit trả về; `SearchHit::getContent` lấy entity từ mỗi hit.

Phương thức `.toList()` yêu cầu Java 16 trở lên. Nếu dự án dùng Java thấp hơn, thay bằng `collect(Collectors.toList())`.

## 9. Đọc kết quả phân trang từ `SearchHits`

`ElasticsearchOperations.search(...)` trả về `SearchHits<T>`, không phải trực tiếp `Page<T>`. `SearchHits` chứa thông tin của từng hit, tổng số hit theo cấu hình tracking, thời gian thực thi, aggregations và các metadata tìm kiếm khác.

Ví dụ:

```java
SearchHits<ProductDocument> searchHits =
        operations.search(query, ProductDocument.class);

long totalHits = searchHits.getTotalHits();
List<ProductDocument> content = searchHits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();
```

`totalHits` là số hit được Elasticsearch báo cáo. Tùy cấu hình `track_total_hits` và ngưỡng mặc định của server, tổng số hit có thể là con số chính xác hoặc một lower bound. Nếu nghiệp vụ cần tổng số chính xác, phải cấu hình tracking phù hợp và cân nhắc chi phí hiệu năng.

### Chuyển thành `SearchPage`

Spring Data Elasticsearch cung cấp `SearchHitSupport.searchPageFor(...)` để tạo `SearchPage` từ `SearchHits` và `Pageable`:

```java
SearchPage<ProductDocument> searchPage =
        SearchHitSupport.searchPageFor(searchHits, pageable);

long total = searchPage.getTotalElements();
int number = searchPage.getNumber();
int size = searchPage.getSize();
List<SearchHit<ProductDocument>> pageHits = searchPage.getContent();

List<ProductDocument> products = pageHits.stream()
        .map(SearchHit::getContent)
        .toList();
```

`SearchPage` giữ metadata phân trang cùng các `SearchHit`; mỗi `SearchHit` vẫn chứa entity trong `getContent()`, score và thông tin hit khác. Cần import các lớp từ package `org.springframework.data.elasticsearch.core` theo phiên bản thư viện.

Nếu ứng dụng chỉ cần danh sách entity và tổng số hit, có thể trả DTO riêng thay vì đưa `SearchHit` ra khỏi tầng repository/service.

## 10. Xây dựng API nhận page, size và sort an toàn

Không nên cho client truyền tùy ý mọi tên field sort xuống Elasticsearch. Hãy whitelist các trường được phép sort:

```java
public enum ProductSortField {
    CREATED_AT,
    PRICE,
    SKU
}
```

Service chuyển lựa chọn thành `Sort`:

```java
private Sort resolveSort(ProductSortField field, boolean descending) {
    Sort.Direction direction = descending
            ? Sort.Direction.DESC
            : Sort.Direction.ASC;

    return switch (field) {
        case CREATED_AT -> Sort.by(direction, "createdAt");
        case PRICE -> Sort.by(direction, "price");
        case SKU -> Sort.by(direction, "sku");
    };
}
```

Whitelist giúp tránh sort nhầm field không có mapping phù hợp, field quá tốn tài nguyên hoặc tên field nội bộ mà API không nên công khai. Đồng thời, validate `page >= 0` và giới hạn `size` theo chính sách API.

Khi sort theo chuỗi, hãy xác định rõ sort theo keyword chính xác hay theo một giá trị đã chuẩn hóa. Sort theo `text` thường không phù hợp; nên dùng subfield `keyword` hoặc một field sort riêng.

## 11. Nhiều tiêu chí sort và thứ tự ưu tiên

Ví dụ:

```java
Sort sort = Sort.by(
        Sort.Order.desc("statusPriority"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("sku")
);
```

Elasticsearch ưu tiên `statusPriority` trước. Nếu hai document có cùng priority, so sánh `createdAt`; nếu vẫn bằng nhau, so sánh `sku`.

Thứ tự này có ý nghĩa nghiệp vụ. Ví dụ trang danh sách có thể muốn:

1. Sản phẩm được ưu tiên hiển thị trước.
2. Trong cùng nhóm ưu tiên, sản phẩm mới cập nhật đứng trước.
3. Nếu cùng thời điểm cập nhật, SKU tăng dần để kết quả ổn định.

Các field sort nên có mapping rõ ràng và giá trị phù hợp. Nếu một field có thể null/missing, cần quyết định cách xử lý document thiếu giá trị và kiểm tra null sort behavior của Elasticsearch.

## 12. Phân trang offset có giới hạn

`Pageable` thường được chuyển thành phân trang offset/limit (`from`/`size`). Cách này đơn giản cho các trang đầu, nhưng càng đi sâu thì Elasticsearch càng phải xử lý và bỏ qua nhiều hit trước offset.

Ví dụ page 500 với size 20 cần bỏ qua 10.000 hit trước khi lấy 20 hit tiếp theo. Elasticsearch mặc định giới hạn cửa sổ kết quả thường là 10.000 (`index.max_result_window`), nên truy vấn sâu có thể bị từ chối nếu vượt ngưỡng.

Không nên tăng `index.max_result_window` tùy tiện để hỗ trợ trang rất sâu. Việc tăng giới hạn có thể làm tăng bộ nhớ và chi phí xử lý trên cluster.

### Khi cần lấy dữ liệu sâu: `search_after`

Với luồng duyệt nhiều kết quả, Elasticsearch khuyến nghị dùng `search_after` kết hợp sort ổn định. Thay vì yêu cầu trang số 500, request tiếp theo gửi giá trị sort của hit cuối trang trước để lấy các document tiếp theo.

Ví dụ ý tưởng:

```json
GET /products/_search
{
  "size": 100,
  "sort": [
    { "created_at": "desc" },
    { "sku": "asc" }
  ],
  "search_after": [
    "2026-11-13T10:15:00Z",
    "SKU-500"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
```

Các giá trị trong `search_after` phải đúng thứ tự và kiểu của các sort field trên hit cuối trang trước. Với quá trình duyệt cần một góc nhìn dữ liệu nhất quán, kết hợp Point in Time (PIT) để các trang dùng cùng một snapshot tìm kiếm trong thời gian hiệu lực.

`Pageable` với page number không tự chuyển thành cursor `search_after`. Nếu cần deep pagination, hãy dùng API hỗ trợ search-after/PIT của Elasticsearch Java API Client hoặc abstraction tương ứng của phiên bản Spring Data, thay vì cố biểu diễn mọi trường hợp bằng `PageRequest`.

## 13. Sort và Pageable có thể tác động đến hiệu năng

Một số nguyên tắc thực tế:

- Chỉ sort trên field cần thiết; sort có thể yêu cầu tài nguyên và bộ nhớ trên shard.
- Ưu tiên `keyword`, numeric và date field có doc values phù hợp.
- Không sort trực tiếp trên `text` nếu không có mapping hỗ trợ.
- Dùng page size vừa phải; tránh trả hàng nghìn document cho một request giao diện.
- Dùng sort ổn định với tie-breaker duy nhất khi chuyển trang.
- Không dùng offset pagination cho luồng duyệt rất sâu.
- Nếu chỉ cần kiểm tra có kết quả hay không, dùng kích thước trang nhỏ thay vì tải toàn bộ dữ liệu.
- Nếu không cần tổng số hit chính xác, cân nhắc giảm chi phí total-hit tracking theo API và phiên bản hỗ trợ.

Một query có Criteria rất chọn lọc nhưng sort trên field không phù hợp vẫn có thể tốn kém. Cần kiểm tra mapping và đo hiệu năng bằng dữ liệu gần với production.

## 14. Kiểm thử CriteriaQuery, Sort và Pageable

Nên kiểm tra riêng từng phần và sau đó kiểm tra kết hợp:

1. Criteria lọc đúng document theo từng điều kiện.
2. AND/OR được nhóm đúng như yêu cầu nghiệp vụ.
3. Sort đúng chiều tăng/giảm và đúng thứ tự ưu tiên giữa nhiều field.
4. Page 0 và page 1 không lặp document khi dữ liệu ổn định.
5. Kích thước trang không vượt giới hạn service cho phép.
6. Field sort có mapping tương thích, đặc biệt với text/keyword.
7. Tên property Java và tên field Elasticsearch được ánh xạ đúng.
8. Tổng số hit được hiểu đúng theo chế độ tracking.
9. Truy vấn sâu có chiến lược `search_after`/PIT nếu cần.

Ví dụ integration test kiểm tra thứ tự:

```java
@Test
void shouldReturnProductsSortedByCreatedAtDescending() {
    // Arrange: index các sản phẩm có createdAt khác nhau.
    // Act: gọi service với page 0, size 10 và sort createdAt DESC.
    // Assert: phần tử đầu tiên có createdAt mới nhất.
}
```

Với test tìm kiếm ngay sau khi index document, cần refresh index hoặc dùng cơ chế chờ refresh phù hợp. Không dựa vào `Thread.sleep` để làm test ổn định.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Kết quả không theo thứ tự mong muốn | Sort dùng sai property/field hoặc mapping không đúng. | Kiểm tra entity mapping và sort field thực tế. |
| Sort trên text báo lỗi hoặc tốn bộ nhớ | Field `text` không có doc values cho sort thông thường. | Dùng multi-field `keyword` hoặc field sort chuyên biệt. |
| Page 1 không có dữ liệu như mong đợi | Page index bị truyền theo kiểu 1-based thay vì 0-based. | Dùng `PageRequest.of(0, size)` cho trang đầu. |
| Hai trang có document trùng hoặc thiếu | Sort không ổn định khi nhiều document có cùng giá trị sort hoặc dữ liệu thay đổi giữa các request. | Thêm tie-breaker duy nhất; cân nhắc PIT và `search_after`. |
| Truy vấn trang sâu bị từ chối | Vượt `index.max_result_window`. | Dùng cursor pagination/search_after thay vì tăng giới hạn tùy tiện. |
| Sort không áp dụng như dự kiến | Sort được khai báo đồng thời trong `Pageable` và query hoặc API dùng nguồn sort khác nhau. | Chọn một nơi định nghĩa sort và kiểm tra request. |
| Tổng hit không bằng số document thật | Total-hit tracking có ngưỡng hoặc relation là lower bound. | Cấu hình tracking chính xác khi thực sự cần và đánh giá chi phí. |
| Query method khác với CriteriaQuery | Derived query và Criteria API có cách biểu diễn riêng. | Kiểm tra Query DSL thực tế và test trên đúng phiên bản. |

## 16. Quy tắc thiết kế

- Dùng `Criteria` cho điều kiện lọc và `CriteriaQuery` để gom query.
- Dùng `Sort` cho thứ tự; order đầu tiên có độ ưu tiên cao nhất.
- Dùng `PageRequest.of(page, size)` với page index bắt đầu từ 0.
- Đưa sort vào `Pageable` khi sort là một phần của API phân trang; hoặc thêm sort riêng vào query, nhưng tránh hai nguồn sort không rõ ràng.
- Dùng field có mapping phù hợp để sort; ưu tiên keyword, numeric và date.
- Với Spring Data mapping, tham chiếu property Java khi API nhận domain property; với raw Query DSL/native request, dùng field name Elasticsearch.
- Thêm tie-breaker duy nhất để phân trang ổn định; không mặc định sort theo `_id`.
- Hiểu rằng `SearchHits` không phải `Page<T>`; chuyển thành `SearchPage` khi cần metadata phân trang hoặc tự tạo response DTO.
- Cân nhắc total-hit tracking nếu cần tổng số chính xác.
- Dùng `search_after` và PIT cho phân trang sâu hoặc luồng duyệt lớn.

## 17. Những điểm cần nhớ

- `CriteriaQuery` kết hợp điều kiện Criteria với các tùy chọn query như sort và pageable.
- `Sort` quy định thứ tự một hoặc nhiều field; order khai báo trước được ưu tiên trước.
- `Pageable` xác định page và size, đồng thời có thể mang Sort.
- `PageRequest` dùng page index bắt đầu từ 0.
- `ElasticsearchOperations.search` trả về `SearchHits`; có thể dùng `SearchHitSupport.searchPageFor` để tạo `SearchPage` khi cần.
- Sort trên field `text` thường không phù hợp; dùng subfield `keyword` hoặc field sort riêng.
- Dùng tie-breaker duy nhất để giảm việc lặp/bỏ sót document giữa các trang.
- Offset pagination có giới hạn và chi phí tăng ở trang sâu; dùng `search_after`/PIT cho trường hợp cần duyệt nhiều kết quả.
- Kiểm tra mapping, tên property/field và request thực tế khi sort hoặc phân trang không đúng.

Kết hợp đúng `CriteriaQuery`, `Sort` và `Pageable` giúp truy vấn Spring Data Elasticsearch rõ ràng, có thứ tự và dễ tích hợp vào API danh sách. Hãy thiết kế điều kiện lọc, sort ổn định và giới hạn phân trang cùng nhau; đồng thời chọn chiến lược cursor khi số lượng kết quả lớn vượt khả năng phù hợp của offset pagination.
