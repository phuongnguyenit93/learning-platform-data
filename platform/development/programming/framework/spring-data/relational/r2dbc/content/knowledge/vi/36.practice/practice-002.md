# Triển khai bộ lọc động, sắp xếp và phân trang ổn định

Trong Spring Data Relational R2DBC, một màn hình tìm kiếm thường cho phép người dùng kết hợp nhiều bộ lọc, chọn thứ tự sắp xếp và chuyển qua các trang kết quả. Các điều kiện này thay đổi theo request nên không thể luôn viết một câu SQL cố định cho mọi tổ hợp.

Spring Data R2DBC cung cấp `Criteria`, `Query`, `Sort` và `R2dbcEntityTemplate` để xây dựng truy vấn entity theo điều kiện. Với SQL phức tạp hoặc cần kiểm soát rõ hơn, có thể dùng `DatabaseClient` và bind parameter. Cả hai cách đều phải giữ nguyên các nguyên tắc:

- Chỉ thêm predicate khi filter tương ứng thực sự được cung cấp.
- Phân biệt filter bị bỏ qua với filter yêu cầu tìm giá trị NULL.
- Bind giá trị thay vì nối chuỗi đầu vào vào SQL.
- Không cho client tự truyền tên cột, biểu thức SQL hoặc keyword sort tùy ý.
- Áp dụng tenant/ownership scope từ nguồn đã xác thực cho mọi query.
- Giới hạn page size và kiểm soát offset.
- Dùng thứ tự sort xác định, có khóa duy nhất làm tie-breaker.
- Cân nhắc keyset pagination khi dữ liệu lớn hoặc có nhiều thay đổi đồng thời.

## 1. Bộ lọc động, sort và pagination là ba phần khác nhau

Một truy vấn tìm kiếm có thể được chia thành ba phần:

| Phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Filter | Xác định row nào được chọn | status = OPEN, createdAt trong khoảng thời gian |
| Sort | Xác định thứ tự row | createdAt giảm dần, id giảm dần |
| Pagination | Giới hạn phần kết quả được trả về | page size 20, offset 40 hoặc cursor |

Ví dụ request:

~~~http
GET /orders?status=OPEN&from=2026-01-01&sort=createdAt,desc&page=0&size=20
~~~

Query tương ứng về mặt ý nghĩa:

~~~sql
SELECT id, tenant_id, status, created_at, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :from
ORDER BY created_at DESC, id DESC
LIMIT :limit
OFFSET :offset;
~~~

Đây chỉ là hình dạng SQL minh họa. Tên placeholder và cú pháp LIMIT/OFFSET thay đổi theo driver/database. Với R2dbcEntityTemplate, Spring Data có thể tạo SQL theo dialect của database.

## 2. Thiết kế DTO cho search request

Không nên nhận trực tiếp một object entity làm search request. Tạo DTO chỉ chứa các filter và tùy chọn được phép:

~~~java
public record OrderSearchRequest(
    String status,
    Instant createdFrom,
    Instant createdTo,
    BigDecimal minAmount,
    BigDecimal maxAmount,
    String keyword,
    String sortBy,
    String sortDirection,
    Integer page,
    Integer size
) {
}
~~~

DTO này mô tả điều kiện tìm kiếm, không chứa tenant ID đáng tin cậy. Tenant phải được lấy từ security principal hoặc context đã xác thực.

Một số quy tắc validation:

- status chỉ nhận các giá trị nghiệp vụ hợp lệ.
- createdFrom không được sau createdTo.
- minAmount không được lớn hơn maxAmount.
- keyword có giới hạn độ dài.
- sortBy phải nằm trong danh sách trường được phép.
- sortDirection chỉ nhận ASC hoặc DESC.
- page không âm.
- size phải lớn hơn 0 và không vượt giới hạn hệ thống.

Nên validate ở biên HTTP trước khi gọi repository/service. Repository vẫn phải bảo đảm query được tạo an toàn, vì nó có thể được gọi từ nhiều nơi khác ngoài controller.

## 3. Phân biệt filter vắng mặt, NULL và giá trị cụ thể

Một lỗi phổ biến là coi filter không được gửi và filter yêu cầu tìm NULL là cùng một trạng thái.

Ba trường hợp khác nhau:

| Request | Ý nghĩa |
|---|---|
| Không gửi assignedTo | Không lọc theo assignedTo |
| assignedTo=null theo hợp đồng API | Tìm row có assigned_to IS NULL |
| assignedTo=alice | Tìm row có assigned_to = 'alice' |

Với DTO Java thông thường, một thuộc tính null có thể có nghĩa “không gửi” hoặc “yêu cầu NULL”. Nếu cần hỗ trợ cả hai, hãy biểu diễn trạng thái rõ ràng, ví dụ bằng filter wrapper có cờ specified hoặc một kiểu request riêng.

Ví dụ:

~~~java
public record OptionalFilter<T>(
    boolean specified,
    T value
) {
}
~~~

Khi specified là false, bỏ predicate. Khi specified là true và value là null, tạo predicate IS NULL. Khi value có giá trị, tạo predicate equality.

Không tự động biến mọi filter null thành IS NULL. Điều đó có thể khiến một request không gửi filter bất ngờ chỉ trả về các row có cột NULL.

## 4. Xây dựng Criteria động với R2dbcEntityTemplate

Criteria biểu diễn điều kiện lọc trên thuộc tính entity. Có thể bắt đầu bằng predicate bắt buộc, sau đó thêm các điều kiện tùy chọn:

~~~java
private Criteria buildCriteria(
        Long tenantId,
        OrderSearchRequest request) {

    Criteria criteria = Criteria.where("tenantId").is(tenantId);

    if (request.status() != null) {
        criteria = criteria.and("status").is(request.status());
    }

    if (request.createdFrom() != null) {
        criteria = criteria.and("createdAt")
            .greaterThanOrEquals(request.createdFrom());
    }

    if (request.createdTo() != null) {
        criteria = criteria.and("createdAt")
            .lessThan(request.createdTo());
    }

    if (request.minAmount() != null) {
        criteria = criteria.and("totalAmount")
            .greaterThanOrEquals(request.minAmount());
    }

    if (request.maxAmount() != null) {
        criteria = criteria.and("totalAmount")
            .lessThanOrEquals(request.maxAmount());
    }

    return criteria;
}
~~~

Các tên trong Criteria.where(...) là thuộc tính persistent của entity theo mapping Spring Data. Không lấy trực tiếp tên cột tùy ý từ request.

Predicate tenant được thêm ngay từ đầu và luôn bắt buộc. Đây là điều kiện bảo vệ phạm vi dữ liệu, không phải filter tùy chọn do client điều khiển.

### Truy vấn entity

Sau khi tạo criteria, xây dựng Query:

~~~java
public Flux<Order> search(
        Long tenantId,
        OrderSearchRequest request) {

    Criteria criteria = buildCriteria(tenantId, request);
    Sort sort = buildSort(request.sortBy(), request.sortDirection());

    int page = normalizePage(request.page());
    int size = normalizePageSize(request.size());
    long offset = Math.multiplyExact((long) page, size);

    Query query = Query.query(criteria)
        .sort(sort)
        .limit(size)
        .offset(offset);

    return template.select(query, Order.class).all();
}
~~~

template ở đây là R2dbcEntityTemplate hoặc một bean có kiểu R2dbcEntityOperations. API cụ thể nên được đối chiếu với phiên bản Spring Data Relational đang dùng.

limit giới hạn số row lấy về; offset bỏ qua số row trước đó. Không dùng offset do client gửi trực tiếp mà chưa validate và giới hạn.

## 5. Kết hợp điều kiện AND

Các filter độc lập thường kết hợp bằng AND:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at >= :from
  AND total_amount <= :maxAmount
~~~

Khi thêm điều kiện có điều kiện, chỉ thêm predicate tương ứng:

~~~java
Criteria criteria = Criteria.where("tenantId").is(tenantId);

if (status != null) {
    criteria = criteria.and("status").is(status);
}

if (from != null) {
    criteria = criteria.and("createdAt").greaterThanOrEquals(from);
}
~~~

Không tạo một predicate kiểu:

~~~sql
(:status IS NULL OR status = :status)
~~~

cho mọi filter chỉ vì nó tiện. Cách này có thể làm query plan khó tối ưu hơn, đặc biệt khi có nhiều filter tùy chọn và dữ liệu lệch. Xây query với những predicate thực sự được dùng thường cho optimizer thông tin rõ hơn.

## 6. Kết hợp điều kiện OR và nhóm ngoặc

Một số search cần OR trong một nhóm:

~~~sql
WHERE tenant_id = :tenantId
  AND (status = 'OPEN' OR status = 'PENDING')
~~~

Với Criteria:

~~~java
Criteria statusCriteria =
    Criteria.where("status").is("OPEN")
        .or("status").is("PENDING");

Criteria criteria =
    Criteria.where("tenantId").is(tenantId)
        .and(statusCriteria);
~~~

Điểm quan trọng là nhóm OR phải nằm trong ngoặc logic bên dưới điều kiện tenant. Không được vô tình tạo logic tương đương:

~~~sql
WHERE (tenant_id = :tenantId AND status = 'OPEN')
   OR status = 'PENDING'
~~~

Query sai này cho phép các row PENDING của tenant khác lọt vào kết quả.

Với điều kiện OR phức tạp, hãy đặt tên cho từng nhóm predicate và đọc lại biểu thức logic trước khi thực thi. Có thể viết helper tạo nhóm Criteria riêng để tránh lỗi precedence.

## 7. Các phép so sánh thường dùng

Spring Data Relational Criteria hỗ trợ các phép so sánh phổ biến:

| Nhu cầu | Predicate SQL tương đương |
|---|---|
| Bằng | `column = value` |
| Khác | `column <> value` |
| Lớn hơn | `column > value` |
| Lớn hơn hoặc bằng | `column >= value` |
| Nhỏ hơn | `column < value` |
| Nhỏ hơn hoặc bằng | `column <= value` |
| Trong tập giá trị | `column IN (...)` |
| Trong khoảng | `column BETWEEN a AND b` |
| NULL | `column IS NULL` |
| Không NULL | `column IS NOT NULL` |
| Chuỗi khớp pattern | `column LIKE pattern` |

Ví dụ:

~~~java
Criteria.where("totalAmount").between(
    request.minAmount(),
    request.maxAmount()
);
~~~

Chỉ dùng between khi cả hai biên đều được cung cấp và semantics bao gồm cả hai đầu là đúng với nghiệp vụ. Nếu một biên có thể vắng mặt, dùng greaterThan/lessThan tương ứng.

## 8. Filter danh sách với IN

Filter theo nhiều trạng thái:

~~~java
Criteria.where("status").in(
    List.of("OPEN", "PENDING", "PAID")
);
~~~

Không để client gửi danh sách không giới hạn. Hãy giới hạn số phần tử và validate từng giá trị.

### Danh sách IN rỗng

Danh sách rỗng cần có semantics rõ ràng:

- Nếu filter không được gửi, bỏ predicate.
- Nếu filter được gửi nhưng danh sách rỗng, thường trả về không có row hoặc trả validation error.
- Không tạo SQL IN () vì cú pháp và cách xử lý có thể lỗi hoặc khác nhau theo database.

Không tự coi danh sách rỗng là “bỏ filter”, vì điều đó có thể làm query trả về nhiều dữ liệu hơn request dự định.

## 9. Filter chuỗi và LIKE

Tìm kiếm theo tiền tố:

~~~java
Criteria.where("customerName").like(prefix + "%");
~~~

Tìm kiếm chứa chuỗi:

~~~java
Criteria.where("customerName").like("%" + keyword + "%");
~~~

Giá trị phải được bind như một parameter bởi Spring Data. Tuy nhiên, % và _ là wildcard của LIKE. Nếu người dùng muốn tìm đúng ký tự % hoặc _, cần escape theo cú pháp database và chỉ định escape character phù hợp.

Ví dụ SQL minh họa:

~~~sql
WHERE customer_name LIKE :pattern ESCAPE '\'
~~~

Pattern phải được escape ký tự escape trước, sau đó escape % và _, rồi mới thêm wildcard do ứng dụng chủ động tạo. Cú pháp ESCAPE và collation cần được kiểm tra trên database mục tiêu.

### Tìm kiếm không phân biệt hoa thường

Không có một cách portable tuyệt đối:

- PostgreSQL có ILIKE và expression index phù hợp.
- MySQL thường phụ thuộc collation của cột.
- SQL Server phụ thuộc collation.
- Oracle và SQLite có quy tắc riêng.

Có thể chuẩn hóa dữ liệu khi ghi, dùng collation phù hợp hoặc tạo normalized column. Nếu dùng LOWER(column), cần xem xét expression/functional index để tránh làm predicate không tận dụng index.

## 10. Filter theo thời gian

Với khoảng thời gian, nên dùng khoảng nửa mở:

~~~sql
created_at >= :from
AND created_at < :to
~~~

Ví dụ:

~~~java
if (request.createdFrom() != null) {
    criteria = criteria.and("createdAt")
        .greaterThanOrEquals(request.createdFrom());
}

if (request.createdTo() != null) {
    criteria = criteria.and("createdAt")
        .lessThan(request.createdTo());
}
~~~

Khoảng nửa mở tránh phải tự tạo thời điểm cuối ngày như 23:59:59.999999. Nó cũng hoạt động rõ ràng với timestamp có precision khác nhau.

Nếu API nhận ngày địa phương, hãy chuyển ngày đó thành start instant và next-day instant theo timezone nghiệp vụ trước khi gọi repository. Không giả định một ngày luôn dài đúng 24 giờ vì có vùng timezone thay đổi offset theo mùa.

## 11. Filter số và validation range

Với min/max:

- Chỉ min: amount >= min.
- Chỉ max: amount <= max.
- Cả hai: amount >= min AND amount <= max.
- min lớn hơn max: trả lỗi validation.

Không chuyển số tiền qua double nếu cần độ chính xác thập phân. Dùng BigDecimal và kiểu cột tương ứng.

Với integer pagination hoặc numeric range, kiểm tra overflow trước khi nhân hoặc chuyển kiểu. Ví dụ tính offset nên dùng Math.multiplyExact((long) page, pageSize) sau khi page/size đã được giới hạn.

## 12. Sort phải dùng allowlist

Tên cột hoặc identifier không thể được bảo vệ bằng bind parameter giống giá trị. Không làm:

~~~java
String sql = "SELECT * FROM orders ORDER BY " + request.sortBy();
~~~

Nếu client truyền created_at DESC; DROP TABLE orders, chuỗi đó có thể biến thành SQL nguy hiểm nếu bị nối trực tiếp.

Thay vào đó, ánh xạ tên sort public sang property được cho phép:

~~~java
private static final Map<String, String> SORT_FIELDS = Map.of(
    "createdAt", "createdAt",
    "status", "status",
    "amount", "totalAmount",
    "orderId", "id"
);
~~~

Tạo Sort:

~~~java
private Sort buildSort(String requestedField, String direction) {
    String property = SORT_FIELDS.get(requestedField);

    if (property == null) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    boolean descending = "desc".equalsIgnoreCase(direction);

    Sort.Order primary = descending
        ? Sort.Order.desc(property)
        : Sort.Order.asc(property);

    Sort.Order tieBreaker = descending
        ? Sort.Order.desc("id")
        : Sort.Order.asc("id");

    return Sort.by(primary, tieBreaker);
}
~~~

Trong thực tế, nếu requestedField đã là id thì không cần thêm id lần thứ hai. Nếu cho phép nhiều trường sort, hãy giới hạn số trường, validate từng trường và loại bỏ duplicate.

### Không dùng tên cột từ request trực tiếp

Sort.by(request.getSortBy()) chỉ an toàn khi giá trị đã được kiểm tra theo allowlist. Dù Spring Data ánh xạ property, không nên để client quyết định tùy ý trường nội bộ được sort, vì có thể lộ dữ liệu hoặc tạo query rất tốn kém.

Sort property thường là tên thuộc tính entity theo mapping Spring Data, không nhất thiết là tên cột SQL. Hãy ánh xạ API field sang property rõ ràng.

## 13. Sort mặc định và thứ tự xác định

Nếu client không gửi sort, ứng dụng nên có thứ tự mặc định:

~~~java
Sort defaultSort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
~~~

Một thứ tự chỉ dựa vào createdAt không xác định đầy đủ nếu nhiều row có cùng timestamp. Database có thể trả các row đồng timestamp theo thứ tự khác nhau ở các lần chạy.

Thêm khóa duy nhất:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Đây là thứ tự total order nếu id duy nhất. Tie-breaker giúp phân trang tránh lặp hoặc bỏ sót row do các giá trị sort chính trùng nhau.

Nếu sort theo nhiều cột, hãy thêm khóa duy nhất cuối cùng. Hướng sort của tie-breaker phải được quy định nhất quán.

## 14. Null ordering và collation

Giá trị NULL có thể được xếp đầu hoặc cuối tùy database và direction. Spring Data Sort có thể biểu diễn null handling ở mức abstraction, nhưng driver/dialect có thể hỗ trợ khác nhau hoặc phải mô phỏng bằng SQL.

Nếu thứ tự NULL là yêu cầu nghiệp vụ:

- Xác định NULLS FIRST hay NULLS LAST.
- Kiểm tra khả năng hỗ trợ của database.
- Kiểm thử cả ASC và DESC.
- Đảm bảo keyset cursor mã hóa được trạng thái NULL.

Sort chuỗi còn phụ thuộc collation: thứ tự chữ hoa/thường, dấu tiếng Việt, ký tự Unicode và locale có thể khác nhau. Nếu API cần thứ tự ngôn ngữ cụ thể, phải xác định collation/normalization ở database và kiểm thử dữ liệu thật.

## 15. Giới hạn page size và offset

Không tin page và size do client gửi:

~~~java
private int normalizePage(Integer requestedPage) {
    if (requestedPage == null) {
        return 0;
    }
    if (requestedPage < 0) {
        throw new IllegalArgumentException("page must be >= 0");
    }
    return requestedPage;
}

private int normalizePageSize(Integer requestedSize) {
    int size = requestedSize == null ? 20 : requestedSize;

    if (size < 1 || size > 100) {
        throw new IllegalArgumentException(
            "size must be between 1 and 100"
        );
    }

    return size;
}
~~~

Giới hạn size giúp tránh một request tải hàng trăm nghìn row vào bộ nhớ hoặc giữ connection quá lâu.

Offset:

~~~java
long offset = Math.multiplyExact((long) page, size);
~~~

Tính bằng long để tránh overflow int. Vẫn cần giới hạn page hoặc offset tối đa theo chính sách API, vì offset rất lớn thường tốn tài nguyên.

## 16. Offset pagination với Query

Offset pagination phù hợp khi:

- Cần chuyển đến một trang bất kỳ.
- Tập dữ liệu vừa phải.
- Kết quả ít thay đổi trong lúc người dùng duyệt.
- Query có index phù hợp với filter và sort.

Ví dụ:

~~~java
public Flux<Order> findPage(
        Criteria criteria,
        Sort sort,
        int page,
        int size) {

    long offset = Math.multiplyExact((long) page, size);

    Query query = Query.query(criteria)
        .sort(sort)
        .limit(size)
        .offset(offset);

    return template.select(query, Order.class).all();
}
~~~

Với page 0 và size 20, database trả tối đa 20 row đầu. Với page 1000, size 20, database phải xử lý vị trí offset 20.000 trước khi trả phần tiếp theo. Index hỗ trợ sort có thể giảm chi phí, nhưng không loại bỏ hoàn toàn việc bỏ qua nhiều row.

## 17. Vì sao offset pagination không ổn định khi dữ liệu thay đổi?

Giả sử page size là 3 và sort theo createdAt giảm dần:

~~~text
Ban đầu:
A, B, C | D, E, F
Page 1    Page 2
~~~

Người dùng đọc page 1. Sau đó một row mới X được insert lên đầu:

~~~text
Sau khi có X:
X, A, B | C, D, E | F
~~~

Request page 2 với OFFSET 3 sẽ trả C, D, E. Row C bị lặp vì nó đã xuất hiện ở page 1 trước khi dữ liệu thay đổi.

Nếu row bị xóa ở phía trước, page 2 có thể bỏ qua một row. Thứ tự sort xác định giúp tránh kết quả không ổn định do tie, nhưng không thể làm offset pagination miễn nhiễm với insert/delete đồng thời.

## 18. Keyset pagination là gì?

Keyset pagination (seek pagination) dùng giá trị của row cuối trang trước làm mốc để tìm trang kế tiếp. Thay vì bỏ qua N row, query yêu cầu các row đứng sau cursor theo thứ tự sort.

Ví dụ sort:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Cursor của trang trước:

~~~text
lastCreatedAt = 2026-01-10T10:30:00Z
lastId = 900
~~~

Query tiếp theo:

~~~sql
WHERE tenant_id = :tenantId
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :size;
~~~

Điều kiện này biểu diễn thứ tự từ điển (lexicographic) của hai khóa sort giảm dần.

Keyset pagination thường có hiệu năng ổn định hơn khi đi sâu vào tập dữ liệu vì database có thể seek từ cursor trong index phù hợp. Nó cũng tránh lặp do một row mới được thêm trước cursor.

## 19. Tạo Criteria cho keyset cursor

Với sort createdAt DESC, id DESC:

~~~java
Criteria afterCursor =
    Criteria.where("createdAt")
        .lessThan(cursor.createdAt())
        .or(
            Criteria.where("createdAt")
                .is(cursor.createdAt())
                .and("id")
                .lessThan(cursor.id())
        );

Criteria criteria =
    Criteria.where("tenantId").is(tenantId)
        .and(afterCursor);
~~~

Sau đó kết hợp các filter nghiệp vụ khác và tạo query:

~~~java
Query query = Query.query(criteria)
    .sort(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    ))
    .limit(pageSize + 1);
~~~

Lấy pageSize + 1 row để biết còn trang tiếp theo hay không:

~~~java
return template.select(query, Order.class)
    .all()
    .collectList()
    .map(rows -> {
        boolean hasNext = rows.size() > pageSize;

        List<Order> content = hasNext
            ? rows.subList(0, pageSize)
            : rows;

        return new CursorPage<>(
            content,
            hasNext,
            content.isEmpty()
                ? null
                : toCursor(content.get(content.size() - 1))
        );
    });
~~~

Đây là ví dụ khung. Cần bảo đảm cursor được tạo từ row cuối thực sự trả cho client, không phải row phụ thứ pageSize + 1.

## 20. Keyset với nhiều cột sort

Với thứ tự:

~~~sql
ORDER BY status ASC, created_at DESC, id DESC
~~~

Cursor phải chứa cả ba giá trị. Điều kiện “sau cursor” có dạng:

~~~sql
status > :lastStatus
OR (
    status = :lastStatus
    AND created_at < :lastCreatedAt
)
OR (
    status = :lastStatus
    AND created_at = :lastCreatedAt
    AND id < :lastId
)
~~~

Dấu so sánh phải thay đổi theo direction của từng cột:

- ASC: giá trị tiếp theo thường lớn hơn cursor.
- DESC: giá trị tiếp theo thường nhỏ hơn cursor.

Với NULL, collation, expression sort hoặc kiểu dữ liệu phức tạp, phải mô hình hóa đúng quy tắc so sánh mà database đang dùng. Không áp dụng máy móc công thức đơn giản cho mọi sort.

Nếu cho phép sort động nhiều cột, cursor builder phải dựa trên cùng danh sách sort đã được allowlist và chuẩn hóa. Một cách đơn giản hơn là giới hạn API cursor vào một vài sort profile đã định nghĩa trước.

## 21. Index cho pagination

Với query:

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT 50
~~~

Index có thể phù hợp:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Index có thể giúp:

1. Tìm phạm vi tenant.
2. Giới hạn theo status.
3. Đọc theo thứ tự createdAt và id.
4. Bắt đầu từ cursor trong keyset pagination.

Nếu status là filter tùy chọn, index bắt đầu bằng tenant_id, status không luôn phục vụ tốt query chỉ có tenant_id và sort created_at. Có thể cần một index khác (tenant_id, created_at, id) nếu workload chứng minh cần thiết.

Đừng tạo mọi tổ hợp index có thể. Đo các search profile phổ biến và cân bằng chi phí ghi.

## 22. Tổng số bản ghi và count query

Một API dạng Page thường muốn trả:

- Danh sách row.
- Page number và page size.
- Tổng số row phù hợp.
- Tổng số trang.

Count query phải dùng cùng predicate với query dữ liệu:

~~~java
Mono<Long> count = template.count(
    Query.query(criteria),
    Order.class
);
~~~

Không dùng count không có tenant filter hoặc bỏ một điều kiện nghiệp vụ vì điều đó có thể làm lộ số lượng dữ liệu ngoài phạm vi.

### Count có thể đắt

COUNT(*) trên một tập dữ liệu lớn vẫn cần đọc đủ dữ liệu phù hợp hoặc dùng cơ chế thống kê/metadata tùy database. Một query lấy 20 row đầu có thể nhanh, trong khi count toàn bộ kết quả chậm hơn đáng kể.

Các lựa chọn API:

- Page: trả total count khi nghiệp vụ thật sự cần.
- Slice: trả content và hasNext, thường dùng limit + 1, không cần count tổng.
- Cursor page: trả cursor tiếp theo và hasNext.

Nếu người dùng chỉ cần “Xem thêm”, không cần đếm tổng số row. Dùng cursor/slice sẽ giảm công việc database.

### Đảm bảo filter giống nhau

Hãy tạo criteria một lần rồi dùng cho cả select và count. Không copy/paste logic filter ở hai nơi vì dễ dẫn đến total count không khớp nội dung.

Nếu cần hai query nhìn cùng một snapshot, chạy tuần tự trong transaction với isolation level phù hợp database. READ COMMITTED có thể cho mỗi statement thấy snapshot khác nhau ở một số hệ quản trị. Không giả định mọi database có cùng semantics isolation.

## 23. Reactive pagination và giới hạn bộ nhớ

R2DBC trả kết quả theo reactive Publisher. Với page size đã giới hạn, có thể collect một page nhỏ thành List để tạo DTO:

~~~java
template.select(query, Order.class)
    .all()
    .collectList();
~~~

Không collect toàn bộ bảng rồi phân trang trong Java:

~~~java
// Không phù hợp với tập dữ liệu lớn
repository.findAll()
    .collectList()
    .map(all -> all.subList(start, end));
~~~

Cách đó tải tất cả row qua network, chiếm bộ nhớ và giữ tài nguyên lâu hơn. Filter, sort và pagination nên được thực hiện ở database.

Nếu cần export dữ liệu lớn, dùng streaming có kiểm soát, fetch/chunk phù hợp và xử lý backpressure. Không biến export thành một page size khổng lồ.

## 24. Kết hợp nhiều filter trong một search service

Có thể tổ chức service theo các bước:

~~~java
public Flux<Order> search(
        OrderSearchRequest request,
        CurrentUser currentUser) {

    Long tenantId = currentUser.tenantId();

    Criteria criteria = buildCriteria(tenantId, request);
    Sort sort = buildValidatedSort(request);
    int page = normalizePage(request.page());
    int size = normalizePageSize(request.size());

    Query query = Query.query(criteria)
        .sort(sort)
        .limit(size)
        .offset(Math.multiplyExact((long) page, size));

    return template.select(query, Order.class).all();
}
~~~

Service lấy tenant từ principal đã xác thực. Không cho request thay tenant bằng query parameter trừ khi nghiệp vụ có một quyền cross-tenant được kiểm tra riêng.

Với một hệ thống lớn, có thể tách:

- OrderFilterBuilder: tạo Criteria.
- OrderSortPolicy: validate và tạo Sort.
- PageRequestValidator: chuẩn hóa page/size.
- OrderSearchRepository: thực hiện query.

Chỉ tách class khi nó giúp tái sử dụng hoặc kiểm soát trách nhiệm. Không cần tạo framework generic quá phức tạp cho một search endpoint đơn giản.

## 25. Dùng DatabaseClient cho dynamic SQL

Khi cần SQL phức tạp, có thể xây dựng phần WHERE từ các predicate được allowlist, còn giá trị vẫn bind:

~~~java
DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(
    "SELECT id, status, created_at " +
    "FROM orders WHERE tenant_id = :tenantId"
).bind("tenantId", tenantId);

if (status != null) {
    spec = spec.bind("status", status);
}
~~~

Đoạn trên mới minh họa việc bind, chưa hoàn chỉnh vì SQL phải được nối thêm predicate tương ứng trước khi gọi sql(). Một builder an toàn nên đồng thời tạo SQL fragment từ các nhánh cố định trong code và bind map chứa giá trị.

Ví dụ khái niệm:

~~~java
StringBuilder sql = new StringBuilder(
    "SELECT id, status, created_at FROM orders WHERE tenant_id = :tenantId"
);

Map<String, Object> bindings = new HashMap<>();
bindings.put("tenantId", tenantId);

if (status != null) {
    sql.append(" AND status = :status");
    bindings.put("status", status);
}

if (createdFrom != null) {
    sql.append(" AND created_at >= :createdFrom");
    bindings.put("createdFrom", createdFrom);
}
~~~

Khi hoàn thiện:

1. Tạo SQL từ các fragment cố định do ứng dụng sở hữu.
2. Chỉ thêm fragment theo boolean/enum đã validate.
3. Bind toàn bộ giá trị qua DatabaseClient.
4. Sort field phải lấy từ allowlist và map sang identifier cố định.
5. Limit/offset phải là số nguyên đã giới hạn.

Không nối giá trị status, keyword, tenant ID hoặc ngày tháng trực tiếp vào SQL.

### Bind danh sách

Việc bind collection vào IN phụ thuộc API named parameter expander và driver. Kiểm tra hỗ trợ của phiên bản Spring Framework/Spring Data R2DBC. Với danh sách lớn, cân nhắc chunk, temporary table hoặc chiến lược database-specific thay vì tạo hàng nghìn placeholder.

## 26. SQL động và tên cột

Bind parameter không thể thay thế identifier:

~~~sql
ORDER BY :columnName
~~~

Thông thường câu lệnh trên sắp xếp theo một giá trị parameter hằng, không phải tên cột được bind.

Nếu dùng DatabaseClient:

- Chỉ dùng tên cột từ allowlist.
- Không chấp nhận biểu thức SQL tự do từ client.
- Không cho client truyền ASC/DESC như một đoạn SQL; parse thành enum.
- Quote identifier đúng dialect nếu cần.
- Không dùng sort string từ URL để nối trực tiếp vào câu lệnh.

Nếu dùng Criteria/Sort của Spring Data, vẫn cần allowlist vì client có thể yêu cầu sort theo cột nhạy cảm, cột lớn hoặc biểu thức gây query tốn kém.

## 27. Phân trang với sort động cần cursor tương thích

Nếu API hỗ trợ nhiều sort profile, cursor phải phản ánh chính xác sort được dùng:

~~~json
{
  "sort": [
    {"field": "createdAt", "direction": "DESC"},
    {"field": "id", "direction": "DESC"}
  ],
  "lastValues": [
    "2026-01-10T10:30:00Z",
    900
  ]
}
~~~

Đây chỉ là cấu trúc khái niệm. API có thể phát một cursor opaque thay vì JSON để client không phải hiểu nội dung.

Cursor cần được:

- Kiểm tra cấu trúc và kiểu dữ liệu.
- Ràng buộc với tenant hoặc principal phù hợp.
- Ràng buộc với filter và sort profile.
- Phiên bản hóa để có thể thay đổi định dạng.
- Ký hoặc bảo vệ toàn vẹn nếu client có thể sửa nội dung.

Base64 chỉ mã hóa biểu diễn, không bảo đảm bí mật hoặc chống sửa đổi. Nếu cursor chứa dữ liệu nhạy cảm, dùng chữ ký hoặc mã hóa theo nhu cầu.

Không tin cursor client gửi chỉ vì nó được phát từ server ở lần trước. Kiểm tra nó vẫn phù hợp với request hiện tại.

## 28. Tính ổn định khi dữ liệu được cập nhật

Keyset pagination ổn định hơn offset khi có insert mới đứng trước cursor, nhưng không tạo snapshot bất biến cho toàn bộ lần duyệt:

- Row đã đọc có thể bị xóa.
- Giá trị sort của row chưa đọc có thể thay đổi và chuyển qua vị trí cursor.
- Filter membership có thể thay đổi khi status hoặc tenant metadata được cập nhật.
- Dữ liệu mới được insert sau cursor có thể xuất hiện trong các trang sau tùy giá trị sort.

Nếu nghiệp vụ cần một tập dữ liệu nhất quán tuyệt đối trong suốt phiên duyệt, cân nhắc:

- Snapshot transaction với isolation phù hợp và thời gian sống được giới hạn.
- Một mốc dữ liệu như createdAt <= snapshotTime.
- Export job tạo tập dữ liệu cố định.
- Version/watermark của dataset.

Transaction snapshot kéo dài có thể giữ connection, snapshot hoặc tài nguyên database lâu. Không giữ một transaction reactive mở trong suốt thời gian người dùng đọc nhiều trang qua HTTP nếu thời gian đó không được kiểm soát.

## 29. Phân trang và isolation level

Offset hoặc keyset pagination giữa nhiều HTTP request thường chạy trên các transaction riêng. Vì vậy mỗi request có thể nhìn thấy một trạng thái database khác.

Nếu cần count và content của cùng một request nhìn cùng snapshot:

1. Chạy hai query trong cùng transaction.
2. Chọn isolation level có semantics snapshot phù hợp database.
3. Thực hiện tuần tự nếu driver/connection không hỗ trợ nhiều statement đồng thời.
4. Kết thúc transaction ngay sau khi tạo response.

Không giả định READ COMMITTED, REPEATABLE READ và SNAPSHOT có cùng semantics giữa PostgreSQL, MySQL, SQL Server và Oracle.

## 30. Sort trên quan hệ và thuộc tính nested

Một số màn hình muốn sort theo thuộc tính quan hệ, ví dụ tên customer của order. Spring Data Relational không có lazy-loading quan hệ giống ORM JPA; query sort theo thuộc tính nested không tự động bảo đảm join được sinh như mong muốn.

Nếu cần sort theo cột của bảng liên quan:

- Viết query JOIN tường minh bằng DatabaseClient hoặc custom repository.
- Dùng view/materialized view nếu phù hợp.
- Denormalize giá trị sort nếu nghiệp vụ và consistency cho phép.
- Xác định index trên join key và sort key.

Không đưa customer.name vào Sort một cách máy móc rồi giả định Spring Data R2DBC sẽ tạo JOIN.

## 31. Kiểm soát chi phí filter và sort

Không phải filter nào cũng rẻ. Những filter sau có thể tốn kém:

- %keyword% trên bảng lớn.
- OR trên nhiều cột không có index phù hợp.
- IN list rất dài.
- Function/cast trên cột.
- Sort theo cột có cardinality thấp trên tập row rất lớn.
- Filter theo JSON expression không có index.

API nên giới hạn:

- Số filter tối đa.
- Độ dài keyword.
- Số phần tử trong IN.
- Số trường sort.
- Page size và offset.
- Khoảng thời gian tìm kiếm tối đa nếu nghiệp vụ cho phép.
- Các tổ hợp sort/filter được hỗ trợ.

Đo query plan trên dữ liệu đại diện. Có thể tạo một số search profile được tối ưu trước thay vì cho phép tổ hợp tùy ý không giới hạn.

## 32. Index cho các search profile phổ biến

Giả sử có ba query thường dùng:

**Tìm đơn hàng theo tenant và status, mới nhất trước**

~~~sql
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
~~~

Index có thể thử:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

**Tìm mọi đơn hàng của tenant, mới nhất trước**

~~~sql
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
~~~

Có thể cần index riêng:

~~~sql
CREATE INDEX idx_orders_tenant_created
ON orders (tenant_id, created_at DESC, id DESC);
~~~

**Tìm theo khoảng thời gian của tenant**

~~~sql
WHERE tenant_id = :tenantId
  AND created_at >= :from
  AND created_at < :to
~~~

Index (tenant_id, created_at) có thể hỗ trợ.

Đây là các ứng viên cần kiểm tra bằng EXPLAIN. Không tạo cả ba index nếu một index đã đáp ứng workload hoặc chi phí ghi không chấp nhận được.

## 33. Kiểm thử dynamic filter

Nên có test cho từng trạng thái filter:

- Không gửi filter.
- Giá trị hợp lệ.
- Giá trị không hợp lệ.
- Giá trị NULL được yêu cầu rõ ràng.
- Khoảng min/max chỉ có một biên.
- Min lớn hơn max.
- Danh sách IN rỗng.
- Danh sách IN có một hoặc nhiều phần tử.
- Keyword chứa %, _ và ký tự escape.
- Tenant A không đọc được row của tenant B.
- OR group không vượt qua tenant predicate.

Kiểm thử cả query không có filter tùy chọn để xác nhận predicate tenant vẫn luôn được áp dụng.

## 34. Kiểm thử sort và pagination

Test sort:

- Field nằm trong allowlist.
- Field không được hỗ trợ bị từ chối.
- ASC và DESC trả thứ tự đúng.
- Nhiều row có cùng createdAt được tie-break bằng id.
- Null ordering đúng yêu cầu.
- Sort chuỗi theo collation đã chọn.

Test offset pagination:

- Page đầu.
- Page giữa.
- Page rỗng.
- Page âm.
- Size 0, size quá lớn.
- Offset overflow hoặc vượt giới hạn.
- Insert/delete giữa hai lần gọi và ghi nhận semantics được chấp nhận.

Test keyset pagination:

- Cursor đầu tiên không có cursor input.
- Cursor tiếp theo không lặp row.
- Nhiều row có cùng giá trị sort chính.
- Cursor sai định dạng hoặc bị sửa.
- Cursor thuộc tenant khác.
- Cursor dùng filter/sort khác request hiện tại.
- Row bị xóa hoặc thay đổi sort trong lúc duyệt.

Nên dùng integration test với R2DBC driver và database thực tế cho các trường hợp mapping, NULL, collation, order và cursor predicate.

## 35. Ví dụ response cho offset page

Một response có thể gồm:

~~~json
{
  "content": [
    {
      "id": 900,
      "status": "OPEN"
    },
    {
      "id": 899,
      "status": "OPEN"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 135,
  "totalPages": 7
}
~~~

Response trên phù hợp khi client cần số trang. Total count có thể làm tăng chi phí truy vấn.

## 36. Ví dụ response cho cursor page

Một response dạng cursor:

~~~json
{
  "content": [
    {
      "id": 900,
      "status": "OPEN"
    },
    {
      "id": 899,
      "status": "OPEN"
    }
  ],
  "hasNext": true,
  "nextCursor": "opaque-signed-cursor"
}
~~~

Client chỉ gửi lại cursor ở lần tiếp theo. Nó không cần biết createdAt/id nằm trong cursor nếu API dùng token opaque.

## 37. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nối filter value vào SQL | SQL injection | Dùng Criteria hoặc bind parameter |
| Dùng sort field trực tiếp từ request | Identifier injection hoặc query ngoài dự kiến | Allowlist và map sang entity property |
| Filter tenant là tùy chọn | Có thể lộ row tenant khác | Lấy tenant từ principal và luôn thêm predicate |
| Đặt OR sai nhóm ngoặc | Predicate OR có thể vượt qua tenant scope | Gom OR thành một Criteria group |
| Coi filter null là IS NULL | Request không gửi filter cho kết quả sai | Phân biệt absent, explicit null và value |
| Bỏ qua validation IN list rỗng | SQL lỗi hoặc vô tình bỏ filter | Định nghĩa semantics rõ ràng |
| Không escape LIKE wildcard | Tìm kiếm rộng hơn dự kiến | Escape %, _ và escape character |
| Sort không có tie-breaker | Row có thể đổi vị trí giữa các page | Thêm khóa duy nhất vào cuối sort |
| Cho phép page size không giới hạn | Tốn memory, connection và database CPU | Đặt maximum size |
| Dùng offset rất lớn | Query chậm khi đi sâu | Cân nhắc keyset pagination |
| Dùng keyset nhưng cursor thiếu sort values | Bỏ sót hoặc lặp row | Cursor chứa mọi khóa sort và unique tie-breaker |
| Không ràng buộc cursor với filter/tenant | Cursor có thể được tái sử dụng sai phạm vi | Validate/sign cursor theo request context |
| Count query khác filter query | totalElements không khớp content | Dùng chung Criteria builder |
| Giả định hai query count/content luôn cùng snapshot | Metadata và row có thể lệch khi concurrent write | Transaction và isolation phù hợp |
| Collect toàn bộ repository.findAll() | Tốn bộ nhớ và network | Filter/page tại database |
| Sort theo thuộc tính quan hệ như JPA | Không tự sinh JOIN như mong đợi | JOIN tường minh hoặc custom query |
| Không đo index theo query profile | Tạo index dư thừa hoặc sai thứ tự | Đọc EXPLAIN và đo workload |

## 38. Quy trình triển khai một search endpoint

Có thể triển khai theo trình tự:

1. Định nghĩa search DTO với các filter được hỗ trợ.
2. Validate kiểu dữ liệu, range, độ dài và số lượng filter.
3. Lấy tenant/ownership scope từ security context.
4. Xây Criteria với predicate bắt buộc trước.
5. Thêm các filter tùy chọn theo semantics rõ ràng.
6. Xây nhóm AND/OR có ngoặc đúng.
7. Validate sort field và direction qua allowlist.
8. Thêm unique tie-breaker vào thứ tự sort.
9. Chuẩn hóa page/size và giới hạn offset.
10. Chọn offset hay keyset pagination theo use case.
11. Xây Query và thực hiện qua R2dbcEntityTemplate.
12. Tạo count query nếu API thực sự cần total.
13. Đảm bảo count và content dùng cùng filter logic.
14. Đo execution plan và thiết kế index theo workload.
15. Viết integration test cho filter, sort, tenant scope và dữ liệu thay đổi đồng thời.

## 39. Ghi nhớ

- Dùng Criteria/Query của Spring Data R2DBC để xây filter động theo thuộc tính entity.
- Dùng DatabaseClient khi cần SQL tùy chỉnh, nhưng luôn bind giá trị.
- Phân biệt filter không gửi, filter yêu cầu NULL và filter có giá trị.
- Kết hợp AND/OR đúng nhóm ngoặc; tenant scope phải luôn được áp dụng từ nguồn đã xác thực.
- Xử lý danh sách IN rỗng và LIKE wildcard theo semantics rõ ràng.
- Không nhận identifier sort tùy ý; map API field qua allowlist.
- Sort mặc định phải xác định và nên có unique tie-breaker như id.
- Validate page, size, offset và giới hạn page size tối đa.
- Offset pagination phù hợp với trang ngẫu nhiên nhưng tốn kém khi offset lớn và nhạy với insert/delete đồng thời.
- Keyset pagination dùng giá trị row cuối làm cursor, phù hợp duyệt dữ liệu lớn và giảm chi phí offset.
- Cursor phải chứa đầy đủ sort values, ràng buộc với filter/tenant và được bảo vệ toàn vẹn nếu client có thể sửa.
- Count query phải dùng cùng filter; Page có total count thường tốn hơn Slice/cursor page.
- Reactive pagination phải thực hiện tại database; không collect toàn bộ bảng trong ứng dụng.
- Isolation level và snapshot semantics khác nhau giữa database; không giữ transaction lâu qua nhiều HTTP request.
- Sort theo quan hệ cần JOIN/query tường minh trong Spring Data Relational.
- Thiết kế index theo search profile, predicate, order và execution plan thực tế.
- Kiểm thử bằng đúng database/R2DBC driver, gồm NULL, collation, tie-breaker, cursor và concurrent changes.
