# `CriteriaQuery`: so sánh giá trị, khoảng, thời gian và tập hợp

Spring Data Elasticsearch cung cấp Criteria API để xây dựng truy vấn bằng Java object thay vì viết trực tiếp JSON Query DSL. `Criteria` mô tả điều kiện trên một field; `CriteriaQuery` đóng gói các điều kiện đó thành một query có thể gửi qua `ElasticsearchOperations` hoặc `ElasticsearchRestTemplate`.

Criteria API hữu ích khi bộ lọc được ghép từ nhiều tham số của request, chẳng hạn trạng thái, danh mục, khoảng giá, khoảng thời gian hoặc danh sách mã. Các toán tử như `is`, `greaterThan`, `between`, `in` và `notIn` giúp thể hiện điều kiện rõ ràng trong code. Muốn kết quả đúng, vẫn cần mapping phù hợp: so sánh mã và trạng thái thường dùng `keyword`, giá dùng kiểu số, còn thời điểm dùng `date`.

## 1. Vai trò của `Criteria` và `CriteriaQuery`

`Criteria` biểu diễn điều kiện tìm kiếm. Có thể tạo điều kiện cho một field, sau đó kết hợp với điều kiện khác bằng `and` hoặc `or`.

`CriteriaQuery` nhận một `Criteria` và cung cấp query cho Spring Data Elasticsearch. `ElasticsearchOperations` thực thi query trên index được chỉ định và chuyển kết quả thành document class.

Luồng tổng quát:

```text
Request / Search criteria
        |
        v
Build Criteria
        |
        v
Create CriteriaQuery
        |
        v
ElasticsearchOperations.search(...)
        |
        v
Elasticsearch index
        |
        v
SearchHits / ProductDocument
```

Khác với query derivation, Criteria API cho phép thêm điều kiện có điều kiện trong code. Khác với việc nối chuỗi JSON, mỗi điều kiện được biểu diễn bằng API Java và tham số được truyền trực tiếp.

## 2. Document mẫu và mapping

Giả sử ứng dụng cần tìm sản phẩm theo trạng thái, danh mục, giá, thời điểm tạo và nhãn. Document có thể được khai báo như sau:

```java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    // Constructors, getters and setters
}
```

Mapping quyết định cách Elasticsearch hiểu từng giá trị:

| Field | Kiểu mapping | Lý do |
|---|---|---|
| `status` | `keyword` | So sánh chính xác trạng thái |
| `categoryId` | `keyword` | So sánh mã danh mục |
| `priceMinorUnits` | `long` | So sánh số và khoảng giá |
| `createdAt` | `date` | Range query theo thời gian |
| `tags` | `keyword` | Tìm document có một hoặc nhiều tag |
| `available` | `boolean` | Lọc đúng/sai |

Nếu dùng `text` cho mã hoặc trạng thái, analyzer có thể chia và biến đổi nội dung. Những điều kiện cần khớp chính xác thường nên dùng `keyword`. Với số tiền, ví dụ lưu theo đơn vị nhỏ nhất bằng `long` để tránh sai số floating-point trong nghiệp vụ.

## 3. Tạo query đơn giản với `is`

`is(value)` biểu diễn điều kiện bằng với giá trị. Ví dụ tìm sản phẩm có trạng thái `PUBLISHED`:

```java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Criteria criteria = new Criteria("status").is("PUBLISHED");
Query query = new CriteriaQuery(criteria);
```

Thực thi query:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

public SearchHits<ProductDocument> findPublished(
        ElasticsearchOperations operations) {

    Criteria criteria = new Criteria("status").is("PUBLISHED");
    Query query = new CriteriaQuery(criteria);

    return operations.search(query, ProductDocument.class);
}
```

Với field `keyword`, điều kiện này thường có ngữ nghĩa so khớp chính xác. Không nên nhầm `is()` trên một field `text` với phép so sánh nguyên chuỗi giống SQL; nếu cần tìm toàn văn trên field được phân tích, dùng toán tử phù hợp như `matches()` hoặc query full-text tường minh.

## 4. So sánh lớn hơn, nhỏ hơn và khoảng số

Criteria API hỗ trợ các toán tử range. Những toán tử thường dùng gồm:

| Toán tử | Ý nghĩa | Biên |
|---|---|---|
| `greaterThan(value)` | Lớn hơn | Không bao gồm giá trị biên |
| `greaterThanEqual(value)` | Lớn hơn hoặc bằng | Bao gồm biên dưới |
| `lessThan(value)` | Nhỏ hơn | Không bao gồm giá trị biên |
| `lessThanEqual(value)` | Nhỏ hơn hoặc bằng | Bao gồm biên trên |
| `between(from, to)` | Nằm trong khoảng | Kiểm tra quy ước biên của API/version đang dùng; thường biểu đạt khoảng gồm hai đầu |

Ví dụ tìm sản phẩm có giá lớn hơn hoặc bằng 1.000.000 và nhỏ hơn 5.000.000 đơn vị nhỏ nhất:

```java
Criteria priceCriteria = new Criteria("priceMinorUnits")
    .greaterThanEqual(1_000_000L)
    .lessThan(5_000_000L);

Query query = new CriteriaQuery(priceCriteria);
```

Biểu thức này tương ứng với khoảng nửa mở:

\[
1{,}000{,}000 \leq priceMinorUnits < 5{,}000{,}000
\]

Dùng cặp toán tử lớn hơn/nhỏ hơn giúp chủ động chọn biên đóng hoặc mở. Ví dụ, khoảng giá `[min, max]` dùng `greaterThanEqual(min)` và `lessThanEqual(max)`; khoảng `[min, max)` dùng `greaterThanEqual(min)` và `lessThan(max)`.

### Dùng `between`

Khi cần khoảng hai đầu, có thể viết:

```java
Criteria priceCriteria = new Criteria("priceMinorUnits")
    .between(1_000_000L, 5_000_000L);
```

`between` ngắn gọn khi ý nghĩa khoảng của ứng dụng phù hợp với cách API chuyển thành range query. Nếu quy tắc nghiệp vụ phụ thuộc chính xác vào việc có bao gồm biên hay không, hãy chọn `greaterThanEqual`/`greaterThan` và `lessThanEqual`/`lessThan` tường minh, đồng thời kiểm tra query thực tế của phiên bản Spring Data đang dùng.

### Range với số thực

Với field `double`, `float` hoặc `scaled_float`, các toán tử range vẫn có thể dùng được. Tuy nhiên, cần xét độ chính xác và cách lượng tử hóa của kiểu field. Với `scaled_float`, giá trị đã được làm tròn theo `scaling_factor`; một ngưỡng nằm giữa hai mức biểu diễn có thể cho kết quả khác với phép so sánh thập phân chính xác ở tầng Java.

## 5. So sánh ngày giờ và khoảng thời gian

Elasticsearch dùng kiểu `date` để lưu thời điểm và hỗ trợ range query. Trong Java, `Instant` thường phù hợp khi cần biểu diễn một thời điểm tuyệt đối theo UTC.

Ví dụ tìm sản phẩm được tạo trong một khoảng thời gian từ `from` đến trước `to`:

```java
import java.time.Instant;

public SearchHits<ProductDocument> findCreatedBetween(
        ElasticsearchOperations operations,
        Instant from,
        Instant to) {

    Criteria criteria = new Criteria("createdAt")
        .greaterThanEqual(from)
        .lessThan(to);

    Query query = new CriteriaQuery(criteria);
    return operations.search(query, ProductDocument.class);
}
```

Khoảng thời gian trên có dạng `[from, to)`: bao gồm thời điểm bắt đầu nhưng không bao gồm thời điểm kết thúc. Cách này hữu ích khi chia dữ liệu theo ngày hoặc tháng vì hai khoảng liền nhau không bị chồng lấn:

```text
Ngày 1: [2026-11-01T00:00:00Z, 2026-11-02T00:00:00Z)
Ngày 2: [2026-11-02T00:00:00Z, 2026-11-03T00:00:00Z)
```

Document đúng tại nửa đêm ngày 2 chỉ thuộc khoảng ngày 2, không bị tính hai lần.

### Chọn kiểu thời gian trong Java

- `Instant`: một thời điểm tuyệt đối, phù hợp với timestamp sự kiện.
- `OffsetDateTime`: thời điểm có offset UTC rõ ràng.
- `LocalDate`: ngày lịch không có giờ, phù hợp với ngày sinh hoặc ngày hiệu lực theo lịch.
- `LocalDateTime`: ngày giờ không chứa timezone; cần quy ước timezone rõ ràng trước khi chuyển thành giá trị lưu trữ.

Với log và sự kiện hệ thống, nên lưu timestamp theo UTC và chuyển sang timezone người dùng ở tầng hiển thị. Nếu nhận khoảng thời gian theo ngày địa phương, hãy chuyển đầu ngày và đầu ngày kế tiếp của timezone đó thành `Instant` trước khi tạo Criteria.

Ví dụ chuyển một ngày địa phương sang khoảng UTC:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;

LocalDate day = LocalDate.of(2026, 11, 13);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = day.atStartOfDay(zone).toInstant();
Instant to = day.plusDays(1).atStartOfDay(zone).toInstant();

Criteria dateCriteria = new Criteria("createdAt")
    .greaterThanEqual(from)
    .lessThan(to);
```

Không nên cộng cố định 24 giờ vào một `Instant` để xác định ngày kế tiếp trong mọi timezone, vì một số timezone có thay đổi giờ mùa hè. Tính đầu ngày kế tiếp từ `LocalDate` và `ZoneId` giúp giữ đúng ý nghĩa ngày lịch.

## 6. Lọc theo tập hợp với `in`

`in(...)` tìm document có giá trị field nằm trong một tập giá trị. Đây là lựa chọn phù hợp khi client chọn nhiều danh mục, trạng thái hoặc mã.

Ví dụ tìm sản phẩm thuộc một trong ba danh mục:

```java
import java.util.List;

List<String> categoryIds = List.of("coffee", "kitchen", "home");

Criteria criteria = new Criteria("categoryId").in(categoryIds);
Query query = new CriteriaQuery(criteria);
```

Với field `keyword`, điều kiện này có ngữ nghĩa tương tự terms query: field khớp một trong các giá trị trong danh sách. Ví dụ JSON Query DSL tương ứng về mặt ý nghĩa:

```json
{
  "query": {
    "terms": {
      "categoryId": ["coffee", "kitchen", "home"]
    }
  }
}
```

`in` phù hợp với tập giá trị hữu hạn. Nếu danh sách rất lớn, cần cân nhắc giới hạn số phần tử, chi phí request và phương án thiết kế dữ liệu khác. Không nên gửi hàng chục nghìn giá trị trong một terms query mà không đo lường tác động.

## 7. Loại trừ tập hợp với `notIn`

`notIn(...)` biểu diễn điều kiện field không thuộc tập giá trị được chỉ định.

Ví dụ loại bỏ các trạng thái `DELETED` và `ARCHIVED`:

```java
List<String> excludedStatuses = List.of("DELETED", "ARCHIVED");

Criteria criteria = new Criteria("status").notIn(excludedStatuses);
Query query = new CriteriaQuery(criteria);
```

Về mặt Query DSL, phép loại trừ thường được biểu diễn bằng `bool.must_not` chứa điều kiện terms tương ứng.

Lưu ý: document không có field hoặc field không được lập chỉ mục có thể được xử lý như không khớp điều kiện bị loại trừ và do đó xuất hiện trong kết quả. Nếu nghiệp vụ yêu cầu field phải tồn tại, cần kết hợp điều kiện tồn tại phù hợp hoặc dùng query tường minh. Đừng mặc định `notIn` đồng nghĩa với “field tồn tại và có giá trị ngoài danh sách”.

## 8. Kết hợp so sánh, khoảng, thời gian và tập hợp

Các điều kiện có thể được kết hợp bằng `and`. Ví dụ tìm sản phẩm:

- Có trạng thái `PUBLISHED`.
- Thuộc một trong các danh mục được chọn.
- Có giá từ mức tối thiểu đến dưới mức tối đa.
- Được tạo trong khoảng thời gian yêu cầu.
- Đang có sẵn.

```java
import java.time.Instant;
import java.util.Collection;

Criteria criteria = new Criteria("status").is("PUBLISHED")
    .and("categoryId").in(categoryIds)
    .and("priceMinorUnits").greaterThanEqual(minPrice)
    .lessThan(maxPrice)
    .and("createdAt").greaterThanEqual(from)
    .lessThan(to)
    .and("available").is(true);

Query query = new CriteriaQuery(criteria);
```

Logic tương ứng:

```text
status = PUBLISHED
AND categoryId IN categoryIds
AND priceMinorUnits >= minPrice
AND priceMinorUnits < maxPrice
AND createdAt >= from
AND createdAt < to
AND available = true
```

Các biểu thức Criteria có thể được xây dựng theo chuỗi. Khi có nhiều điều kiện tùy chọn, nên thêm từng điều kiện chỉ khi tham số thực sự được cung cấp.

### Kết hợp `or`

Ví dụ tìm sản phẩm có trạng thái `PUBLISHED` hoặc `FEATURED`:

```java
Criteria statusCriteria = new Criteria("status").is("PUBLISHED")
    .or("status").is("FEATURED");

Query query = new CriteriaQuery(statusCriteria);
```

OR có thể dùng cho nhiều giá trị của cùng một field. Với trường hợp một field cần khớp một trong nhiều giá trị, `in(...)` thường ngắn gọn hơn:

```java
Criteria statusCriteria = new Criteria("status")
    .in(List.of("PUBLISHED", "FEATURED"));
```

### Khi cần nhóm ngoặc phức tạp

Nếu cần logic như:

```text
(status = PUBLISHED OR status = FEATURED)
AND (categoryId = coffee OR categoryId = tea)
AND available = true
```

hãy kiểm tra khả năng nhóm `Criteria` của phiên bản đang dùng. Với bool query lồng nhiều tầng, `NativeQuery` thường diễn đạt rõ hơn vì cấu trúc `must`, `filter`, `should`, `must_not` và `minimum_should_match` được thể hiện trực tiếp. Không nên nối nhiều `.and()`/`.or()` mà không xác nhận nhóm điều kiện cuối cùng.

## 9. Xây dựng Criteria động từ tham số tìm kiếm

Trong API tìm kiếm, nhiều tham số là tùy chọn. Ví dụ người dùng có thể chỉ truyền category, hoặc truyền thêm khoảng giá và khoảng thời gian. Không nên tạo query có điều kiện với giá trị mặc định tùy tiện nếu điều đó làm thay đổi ý nghĩa tìm kiếm.

Tạo DTO tiêu chí:

```java
import java.time.Instant;
import java.util.List;

public class ProductSearchCriteria {
    private String status;
    private List<String> categoryIds;
    private Long minPrice;
    private Long maxPrice;
    private Instant createdFrom;
    private Instant createdTo;
    private Boolean available;

    // Getters and setters
}
```

Xây dựng Criteria chỉ từ tham số có giá trị:

```java
public Query buildQuery(ProductSearchCriteria request) {
    String status = request.getStatus() == null || request.getStatus().isBlank()
        ? "PUBLISHED"
        : request.getStatus();
    Criteria criteria = new Criteria("status").is(status);

    if (request.getCategoryIds() != null
            && !request.getCategoryIds().isEmpty()) {
        criteria = criteria.and("categoryId").in(request.getCategoryIds());
    }

    if (request.getMinPrice() != null) {
        criteria = criteria.and("priceMinorUnits")
            .greaterThanEqual(request.getMinPrice());
    }

    if (request.getMaxPrice() != null) {
        criteria = criteria.and("priceMinorUnits")
            .lessThan(request.getMaxPrice());
    }

    if (request.getCreatedFrom() != null) {
        criteria = criteria.and("createdAt")
            .greaterThanEqual(request.getCreatedFrom());
    }

    if (request.getCreatedTo() != null) {
        criteria = criteria.and("createdAt")
            .lessThan(request.getCreatedTo());
    }

    if (request.getAvailable() != null) {
        criteria = criteria.and("available").is(request.getAvailable());
    }

    return new CriteriaQuery(criteria);
}
```

Trong ví dụ này, `PUBLISHED` là filter mặc định của use case. Nếu request truyền status, giá trị đó thay thế mặc định; code chỉ thêm một điều kiện status. Cách chọn giá trị trước khi tạo Criteria tránh vô tình yêu cầu một field phải bằng hai trạng thái khác nhau.

### Xử lý danh sách rỗng

Danh sách rỗng cần có quy tắc rõ ràng:

- Nếu danh sách không được truyền hoặc rỗng có nghĩa “không lọc theo danh sách”, bỏ qua điều kiện `in`.
- Nếu danh sách rỗng có nghĩa “không có giá trị nào được phép”, trả về kết quả rỗng ngay hoặc tạo query luôn không khớp.
- Nếu danh sách rỗng là input không hợp lệ, trả lỗi validation.

Không nên phụ thuộc vào hành vi của terms query với danh sách rỗng để quyết định nghiệp vụ. Hãy xử lý trường hợp này trước khi xây dựng Criteria.

### Kiểm tra khoảng đầu vào

Trước khi tạo range, kiểm tra `minPrice <= maxPrice` và `createdFrom < createdTo`. Nếu biên không hợp lệ, trả lỗi validation thay vì gửi query vô nghĩa.

## 10. Thực thi query bằng `ElasticsearchOperations`

Sau khi tạo `CriteriaQuery`, gọi `ElasticsearchOperations.search(...)`:

```java
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public List<ProductDocument> search(Query query) {
        SearchHits<ProductDocument> hits =
            operations.search(query, ProductDocument.class);

        return hits.getSearchHits().stream()
            .map(SearchHit::getContent)
            .toList();
    }
}
```

`SearchHits` chứa metadata của kết quả tìm kiếm như tổng số hit, thông tin score và danh sách `SearchHit`. Mỗi `SearchHit` có document content cùng metadata liên quan. Nếu ứng dụng cần score, highlight hoặc tổng số kết quả, hãy giữ `SearchHits` thay vì chỉ chuyển thành `List<ProductDocument>`.

### Chỉ định index hoặc alias

Có thể chỉ định rõ index/alias bằng `IndexCoordinates`:

```java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

SearchHits<ProductDocument> hits = operations.search(
    query,
    ProductDocument.class,
    IndexCoordinates.of("products-read")
);
```

Điều này hữu ích khi ứng dụng đọc qua alias hoặc index khác với tên được khai báo trong document class. Cần bảo đảm alias trỏ tới index có mapping tương thích với `ProductDocument`.

## 11. Phân trang và sắp xếp

CriteriaQuery có thể kết hợp với `Pageable` để giới hạn số kết quả và sắp xếp.

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Query query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "priceMinorUnits")
));

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
```

Ví dụ lấy trang đầu tiên, mỗi trang 20 document và sắp xếp giá tăng dần. Tên field sort phải tương ứng với mapping có thể sort được; `text` thường không phù hợp để sort trực tiếp, nên dùng `keyword` subfield hoặc field chuyên dụng.

Với dữ liệu lớn, tránh phân trang sâu bằng `from`/`size` vượt giới hạn result window. Hãy xem xét `search_after` và sort ổn định nếu cần duyệt nhiều trang. CriteriaQuery vẫn có thể là phần điều kiện lọc; chiến lược phân trang có thể cần query/operations API phù hợp hơn tùy phiên bản.

## 12. Phân biệt `is`, `matches` và điều kiện tập hợp

Criteria API có các toán tử cho nhiều kiểu tìm kiếm. Cần chọn theo mapping và mục tiêu:

| Toán tử | Ý nghĩa thường dùng | Mapping phù hợp |
|---|---|---|
| `is(value)` | So khớp giá trị/term | `keyword`, boolean, số, date |
| `matches(text)` | Full-text match sau khi phân tích | `text` |
| `greaterThan` / `lessThan` | Range mở | Số, date |
| `greaterThanEqual` / `lessThanEqual` | Range đóng ở một biên | Số, date |
| `between` | Range giữa hai giá trị | Số, date |
| `in(values)` | Khớp một giá trị trong tập hợp | Thường là `keyword`, số |
| `notIn(values)` | Loại trừ các giá trị trong tập hợp | Thường là `keyword`, số |

Ví dụ full-text:

```java
Criteria textCriteria = new Criteria("description")
    .matches("máy pha cà phê");
```

`matches` sử dụng ngữ nghĩa tìm kiếm văn bản được phân tích, khác với điều kiện term chính xác. Nếu tìm kiếm nội dung, hãy cấu hình analyzer phù hợp với ngôn ngữ và kiểm tra token bằng `_analyze`.

## 13. Null, field bị thiếu và giá trị rỗng

Elasticsearch không xử lý null giống hệt SQL. Một field không có trong document hoặc được gửi với JSON `null` thường không tạo giá trị có thể so khớp như một term. Do đó:

- `is(null)` không nên được hiểu như `column IS NULL` trong SQL nếu chưa kiểm tra cách Criteria chuyển thành query.
- `notIn(...)` có thể bao gồm document thiếu field.
- Chuỗi rỗng `""` là một giá trị khác với field không tồn tại.
- Mapping `null_value` có thể thay đổi cách null được lập chỉ mục.

Nếu cần kiểm tra field tồn tại/không tồn tại, dùng điều kiện `exists` hoặc query tường minh mà phiên bản Spring Data hỗ trợ. Với các quy tắc quan trọng, kiểm tra Query DSL và dữ liệu thực tế thay vì suy luận theo ngữ nghĩa SQL.

## 14. Khi nào CriteriaQuery không còn phù hợp?

CriteriaQuery phù hợp với các điều kiện lọc tương đối trực tiếp: equality, range, tập hợp và các phép kết hợp thông thường. Khi cần cấu trúc Query DSL phức tạp, hãy cân nhắc `NativeQuery` hoặc custom repository.

| Nhu cầu | Lựa chọn nên cân nhắc |
|---|---|
| Lọc status, category, giá và ngày | `CriteriaQuery` |
| Thêm filter tùy chọn từ request | `Criteria` dựng động |
| Full-text đơn giản trên một field | Criteria `matches` hoặc query match |
| Nhiều nhóm bool lồng nhau, `minimum_should_match` | `NativeQuery` |
| Nested query trên mảng object | `NativeQuery` với nested query |
| Aggregation, highlight hoặc scoring chuyên biệt | `NativeQuery`/`ElasticsearchOperations` |
| Query DSL cố định, ngắn | `@Query` |

Không nên ép Criteria API diễn đạt một logic khó đọc chỉ để tránh JSON Query DSL. Chọn API giúp người bảo trì nhìn thấy chính xác điều kiện và cách nhóm logic.

## 15. Kiểm tra truy vấn và kết quả

Khi CriteriaQuery trả kết quả không như mong muốn, hãy kiểm tra theo từng lớp.

### Kiểm tra mapping

```http
GET /products/_mapping
```

Xác nhận `status` và `categoryId` là `keyword`, `priceMinorUnits` là kiểu số, `createdAt` là `date` và field được dùng cho sort có thể sort.

### Kiểm tra dữ liệu mẫu

Tạo document có giá ở đúng biên và ngoài biên, timestamp đúng đầu/cuối khoảng, category nằm trong/ngoài danh sách và field bị thiếu. Sau đó chạy cùng điều kiện bằng Query DSL trực tiếp để so sánh với kết quả CriteriaQuery.

### Kiểm tra timezone

Với thời gian, xác nhận giá trị đầu vào đã được chuyển về đúng timezone và khoảng `[from, to)` hay `[from, to]` khớp yêu cầu. Lỗi timezone thường làm kết quả thiếu hoặc thừa document ở đầu/cuối ngày.

### Kiểm tra danh sách

Xác nhận danh sách truyền vào `in`/`notIn` đã được validate, không có giá trị null ngoài ý muốn và có quy tắc rõ ràng khi danh sách rỗng.

### Kiểm tra query thực tế

Có thể bật logging ở môi trường phát triển để quan sát request Elasticsearch hoặc dựng JSON tương đương rồi gửi qua Dev Tools. Tên logger và mức log phụ thuộc phiên bản. Tránh log payload có dữ liệu nhạy cảm trong production.

## 16. Lỗi thường gặp

### Dùng `is()` cho field `text`

Field `text` được analyzer phân tích thành token; điều kiện term không phải so sánh nguyên chuỗi như SQL. Dùng `keyword` cho equality hoặc `matches` cho full-text.

### Dùng range trên field dạng chuỗi

Nếu giá hoặc timestamp được map thành `keyword`, range query có thể so sánh theo thứ tự từ vựng thay vì số học/thời gian. Khai báo kiểu số hoặc `date` đúng ngay từ đầu.

### Bao gồm nhầm biên thời gian

Dùng `lessThanEqual(to)` thay vì `lessThan(to)` có thể khiến hai khoảng liền kề cùng bao gồm thời điểm biên. Với phân đoạn thời gian, khoảng nửa mở `[from, to)` thường tránh đếm trùng.

### Gửi danh sách rỗng vào `in`

Danh sách rỗng có thể không mang ý nghĩa mong muốn và có thể tạo query không hợp lệ hoặc không khớp. Xử lý rõ ràng trước khi tạo Criteria.

### Kết hợp AND/OR mà không xác nhận nhóm

Chuỗi Criteria dài có thể khó nhìn ra cấu trúc logic. Viết biểu thức có ngoặc trước; với nhóm lồng nhau, dùng NativeQuery nếu rõ ràng hơn.

### Không phân biệt null với field thiếu

Elasticsearch không có ngữ nghĩa null giống SQL. Kiểm tra exists, null_value và cách serializer ghi document.

### Sort trên field không hỗ trợ sort

Sort trên `text` có thể không hoạt động hoặc không phù hợp. Dùng `keyword` subfield hoặc field có mapping số/ngày thích hợp.

## 17. Quy trình xây dựng CriteriaQuery

Khi triển khai một màn hình tìm kiếm, có thể đi theo trình tự:

1. Liệt kê field mà người dùng được phép lọc và xác định kiểu mapping.
2. Xác định toán tử cho từng field: bằng, lớn hơn/nhỏ hơn, khoảng, thuộc tập hợp hoặc full-text.
3. Quy định rõ biên khoảng giá và thời gian có bao gồm hay không.
4. Chuẩn hóa timezone và kiểu Java trước khi dựng date range.
5. Xử lý danh sách rỗng, tham số null và khoảng đầu vào không hợp lệ.
6. Dựng Criteria theo từng điều kiện có giá trị.
7. Đóng gói bằng `CriteriaQuery` và thêm phân trang/sắp xếp nếu cần.
8. Thực thi qua `ElasticsearchOperations` và xử lý `SearchHits`.
9. Kiểm tra mapping, query và kết quả với dữ liệu biên.
10. Chuyển sang `NativeQuery` khi logic bool/nested hoặc scoring vượt quá mức Criteria dễ biểu đạt.

## 18. Kết luận

CriteriaQuery giúp xây dựng truy vấn Elasticsearch bằng Java API. `is` dùng cho so sánh giá trị, các toán tử `greaterThan`/`lessThan` và biến thể `Equal` dùng cho khoảng số hoặc thời gian, còn `in`/`notIn` dùng để lọc theo tập hợp. Có thể kết hợp điều kiện bằng `and` và `or`, rồi thực thi qua `ElasticsearchOperations`.

Mapping phải phù hợp với phép so sánh: `keyword` cho mã/trạng thái, kiểu số cho giá, `date` cho thời điểm và `text` cho nội dung toàn văn. Với thời gian, hãy thống nhất timezone và chọn biên khoảng rõ ràng; với tập hợp, xử lý danh sách rỗng theo quy tắc nghiệp vụ. Khi cần nhóm bool lồng nhau hoặc Query DSL chuyên biệt, dùng `NativeQuery` để thể hiện logic trực tiếp thay vì làm Criteria chain khó hiểu.
