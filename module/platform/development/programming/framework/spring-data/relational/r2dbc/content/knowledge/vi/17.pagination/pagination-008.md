# Phân trang với bộ lọc động, join và truy vấn tổng hợp

Một màn hình danh sách trong ứng dụng thường cần nhiều hơn một truy vấn `SELECT` đơn giản. Người dùng có thể chọn trạng thái, khoảng thời gian, khách hàng hoặc từ khóa; kết quả có thể cần thêm tên khách hàng từ bảng liên quan, số dòng hàng hoặc tổng tiền đã nhóm. Khi số bản ghi tăng, ứng dụng còn phải giới hạn số kết quả trả về theo từng trang.

Trong Spring Data R2DBC, có thể xây dựng kiểu truy vấn này bằng `R2dbcEntityTemplate` với `Query`/`Criteria`, hoặc dùng SQL tùy chỉnh qua `DatabaseClient`/`@Query`. Dù chọn API nào, một trang dữ liệu đầy đủ thường cần giải quyết riêng ba vấn đề: xác định đúng tập kết quả theo bộ lọc, sắp xếp/phân trang ổn định và tính tổng số phần tử theo đúng ý nghĩa nghiệp vụ.

## 1. Thành phần của một truy vấn phân trang

Một kết quả phân trang thường có:

- **Bộ lọc:** điều kiện bắt buộc và điều kiện tùy chọn do use case cung cấp.
- **Thứ tự:** các trường sort được cho phép và có khóa phụ để bảo đảm thứ tự ổn định.
- **Trang hiện tại:** số trang và kích thước trang, hoặc cursor của keyset pagination.
- **Dữ liệu trang:** các hàng hoặc nhóm kết quả thuộc trang đó.
- **Tổng số:** tổng số hàng logic thỏa bộ lọc, nếu giao diện cần biết tổng trang.

Ví dụ, trang quản trị đơn hàng cần lọc theo tenant, trạng thái và khoảng thời gian; hiển thị mã đơn, tên khách hàng, số dòng hàng và tổng tiền. Kết quả phải được sắp xếp theo thời điểm tạo mới nhất và trả 20 đơn hàng mỗi trang.

```text
Request filters + page/sort
           |
           v
   Validate and normalize
           |
           v
      Build predicates
           |
      +----+----------------+
      |                     |
      v                     v
 Content query          Count query
 filters + joins        same logical filters
 sort + limit/offset    count logical results
      |                     |
      v                     v
  Page rows             Total count
      |                     |
      +----------+----------+
                 |
                 v
       Page response / DTO
```

Với truy vấn đơn giản trên một entity, Repository hoặc Template có thể đủ. Khi cần join nhiều bảng và tổng hợp, SQL tự viết thường giúp thể hiện chính xác cấu trúc dữ liệu hơn.

## 2. Thiết kế request và kết quả phân trang

### 2.1. Filter object

Nên gom điều kiện tìm kiếm vào một kiểu riêng thay vì truyền nhiều tham số rời rạc qua các tầng:

```java
public record OrderSearchFilter(
        Long tenantId,
        String status,
        Long customerId,
        Instant createdFrom,
        Instant createdTo,
        int page,
        int size,
        OrderSort sort
) {
}

public enum OrderSort {
    CREATED_DESC,
    CREATED_ASC,
    AMOUNT_DESC
}
```

`tenantId` là điều kiện phạm vi dữ liệu bắt buộc. `status`, `customerId` và thời gian có thể tùy chọn. `sort` là enum do ứng dụng kiểm soát; không nhận trực tiếp tên cột SQL tùy ý từ client.

Trước khi truy vấn, cần xác thực:

- `page` không âm.
- `size` lớn hơn 0 và không vượt giới hạn ứng dụng cho phép.
- `createdFrom` không nằm sau `createdTo`.
- `tenantId` lấy từ ngữ cảnh xác thực hoặc được kiểm tra quyền, không tin một ID tenant do client tự gửi.
- Giá trị trạng thái nằm trong tập trạng thái hợp lệ.

### 2.2. Page response

Spring Data R2DBC sử dụng các kiểu reactive như `Mono` và `Flux`. Với truy vấn phân trang có tổng số, có thể định nghĩa response riêng:

```java
public record PageResult<T>(
        List<T> content,
        int page,
        int size,
        long totalElements,
        long totalPages
) {
}
```

`PageResult` là DTO ứng dụng/API, không phải entity. Tổng số trang được tính từ `totalElements` và `size`; nếu API chỉ cần nút “xem thêm”, có thể không cần chạy count query mà dùng `size + 1` để xác định còn dữ liệu hay không.

### 2.3. Tính offset an toàn

Với offset pagination, công thức là:

\[
\text{offset} = \text{page} \times \text{size}
\]

Nên dùng phép nhân có kiểm tra tràn số và giới hạn trang ở tầng request:

```java
long offset = Math.multiplyExact((long) filter.page(), filter.size());
```

Nếu giá trị quá lớn, trả lỗi validation thay vì để offset âm hoặc tràn số đi vào câu truy vấn. Offset rất lớn cũng có thể chậm dù không bị tràn số; khi đó nên cân nhắc keyset pagination.

## 3. Phân trang một entity với R2dbcEntityTemplate

Với truy vấn chỉ lọc trên một loại entity, `R2dbcEntityTemplate` và `Criteria` có thể tạo content query và count query từ cùng bộ điều kiện.

### 3.1. Tạo Criteria dùng chung

```java
private Criteria buildCriteria(OrderSearchFilter filter) {
    Criteria criteria = Criteria.where("tenantId").is(filter.tenantId());

    if (filter.status() != null && !filter.status().isBlank()) {
        criteria = criteria.and("status").is(filter.status());
    }

    if (filter.customerId() != null) {
        criteria = criteria.and("customerId").is(filter.customerId());
    }

    if (filter.createdFrom() != null) {
        criteria = criteria.and("createdAt")
                .greaterThanOrEquals(filter.createdFrom());
    }

    if (filter.createdTo() != null) {
        criteria = criteria.and("createdAt")
                .lessThan(filter.createdTo());
    }

    return criteria;
}
```

Điều kiện tenant luôn được thêm vào. Những điều kiện khác chỉ được thêm khi có giá trị. Phân biệt rõ “không cung cấp bộ lọc” với “tìm các hàng có cột `NULL`”; hai trường hợp này cần biểu diễn bằng request khác nhau nếu nghiệp vụ cần cả hai.

Các tên trong Criteria là property của entity, ví dụ `createdAt` hoặc `customerId`. Mapping metadata của Spring Data xử lý ánh xạ sang cột database. Kiểm tra API Criteria và tên property theo phiên bản Spring Data Relational mà dự án đang sử dụng.

### 3.2. Tạo content query và count query

```java
public Mono<PageResult<OrderEntity>> search(OrderSearchFilter filter) {
    Criteria criteria = buildCriteria(filter);
    long offset = Math.multiplyExact((long) filter.page(), filter.size());

    Query contentQuery = Query.query(criteria)
            .sort(Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.desc("id")))
            .limit(filter.size())
            .offset(offset);

    Query countQuery = Query.query(criteria);

    return template.select(contentQuery, OrderEntity.class)
            .collectList()
            .flatMap(content -> template.count(countQuery, OrderEntity.class)
                    .map(total -> new PageResult<>(
                            content,
                            filter.page(),
                            filter.size(),
                            total,
                            total / filter.size()
                                    + (total % filter.size() == 0 ? 0 : 1))));
}
```

Content query có sort, limit và offset. Count query dùng cùng `Criteria` nhưng không có sort, limit hoặc offset. Nhờ vậy, `totalElements` là tổng số entity thỏa bộ lọc, không phải số hàng của trang hiện tại.

Ví dụ dùng `flatMap` để chạy count sau khi content query hoàn tất. Cách tuần tự này dễ kiểm soát khi các truy vấn cần tham gia cùng một reactive transaction/connection. Nếu không cần transaction và hai truy vấn độc lập, có thể cân nhắc `Mono.zip(contentMono, countMono)` để thực thi đồng thời; hãy kiểm tra giới hạn driver, connection pool và hành vi transaction trước khi làm vậy.

### 3.3. Count query phải bỏ pagination

Một lỗi thường gặp là tái sử dụng `Query` đã có limit/offset cho count. Khi đó số đếm có thể phản ánh số hàng trong trang thay vì toàn bộ tập kết quả. Count query cần giữ đúng predicate nhưng loại bỏ sort, limit và offset.

Nếu filter có thể thay đổi giữa lúc xây dựng hai query, hãy tạo chúng từ cùng một đối tượng filter đã được validate/normalize. Không viết hai bộ điều kiện độc lập có nguy cơ lệch nhau.

## 4. Bộ lọc động cùng join bằng SQL tự viết

Khi kết quả cần dữ liệu từ nhiều bảng hoặc phép tính tổng hợp, có thể dùng `DatabaseClient`. Ví dụ trang đơn hàng hiển thị tên khách hàng, số dòng hàng và tổng tiền của mỗi đơn.

### 4.1. DTO kết quả

```java
public record OrderPageRow(
        Long id,
        String orderCode,
        String status,
        String customerName,
        Instant createdAt,
        Long lineCount,
        BigDecimal totalAmount
) {
}
```

Đây là projection phục vụ truy vấn đọc. Nó có thể chứa dữ liệu từ nhiều bảng và giá trị aggregate không tồn tại trong `OrderEntity`.

### 4.2. Content SQL

```sql
SELECT o.id,
       o.order_code,
       o.status,
       c.display_name AS customer_name,
       o.created_at,
       COUNT(ol.id) AS line_count,
       COALESCE(SUM(ol.quantity * ol.unit_price), 0) AS total_amount
FROM orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines ol ON ol.order_id = o.id
WHERE o.tenant_id = :tenantId
  AND o.status = :status
GROUP BY o.id, o.order_code, o.status,
         c.display_name, o.created_at
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset
```

`LEFT JOIN` giữ lại đơn hàng chưa có dòng hàng. `COUNT(ol.id)` trả 0 cho đơn hàng không có dòng; `COALESCE` chuyển tổng tiền null thành 0. Các cột không nằm trong aggregate phải có trong `GROUP BY` theo cú pháp database đang sử dụng.

### 4.3. Count SQL cho cùng tập đơn hàng

Trong ví dụ, mỗi đơn hàng có đúng một khách hàng và filter chỉ áp dụng lên cột của bảng `orders`. Có thể đếm đơn hàng trực tiếp:

```sql
SELECT COUNT(*)
FROM orders o
WHERE o.tenant_id = :tenantId
  AND o.status = :status
```

Không đưa `order_lines` vào count chỉ vì content query có join. Nếu count query join một-nhiều, mỗi đơn có nhiều dòng hàng có thể bị đếm nhiều lần. Khi cần join để lọc, dùng `COUNT(DISTINCT o.id)` hoặc một `EXISTS` phù hợp để đếm đúng số đơn hàng logic.

### 4.4. Ghép filter và bind parameter

Khi bộ lọc tùy chọn, xây dựng phần `WHERE` động từ các đoạn SQL cố định và bind mọi giá trị:

```java
StringBuilder where = new StringBuilder(" WHERE o.tenant_id = :tenantId ");

if (filter.status() != null && !filter.status().isBlank()) {
    where.append(" AND o.status = :status ");
}
if (filter.customerId() != null) {
    where.append(" AND o.customer_id = :customerId ");
}
if (filter.createdFrom() != null) {
    where.append(" AND o.created_at >= :createdFrom ");
}
if (filter.createdTo() != null) {
    where.append(" AND o.created_at < :createdTo ");
}
```

Hãy dùng cùng một hàm tạo `where` cho content và count query để tránh hai truy vấn áp dụng bộ lọc khác nhau. Chỉ các đoạn cú pháp cố định do ứng dụng kiểm soát được nối vào SQL; giá trị từ request luôn bind bằng named parameter.

Ví dụ bind tham số:

```java
DatabaseClient.GenericExecuteSpec bindFilters(
        DatabaseClient.GenericExecuteSpec spec,
        OrderSearchFilter filter) {

    spec = spec.bind("tenantId", filter.tenantId());

    if (filter.status() != null && !filter.status().isBlank()) {
        spec = spec.bind("status", filter.status());
    }
    if (filter.customerId() != null) {
        spec = spec.bind("customerId", filter.customerId());
    }
    if (filter.createdFrom() != null) {
        spec = spec.bind("createdFrom", filter.createdFrom());
    }
    if (filter.createdTo() != null) {
        spec = spec.bind("createdTo", filter.createdTo());
    }

    return spec;
}
```

Không gọi `.bind(name, null)` để biểu diễn null. Với tham số null có chủ đích, dùng `bindNull(name, type)` hoặc thiết kế predicate phù hợp. Nếu null mang nghĩa “không áp dụng filter”, cách rõ ràng thường là bỏ predicate và bỏ luôn tham số đó.

### 4.5. Whitelist sort động

Tên cột và hướng sắp xếp là cấu trúc SQL, không phải giá trị có thể bind bằng `:sortColumn`. Chuyển lựa chọn từ client sang danh sách cho phép:

```java
String orderBy = switch (filter.sort()) {
    case CREATED_ASC -> "o.created_at ASC, o.id ASC";
    case CREATED_DESC -> "o.created_at DESC, o.id DESC";
    case AMOUNT_DESC -> "total_amount DESC, o.id DESC";
};
```

Chỉ dùng các chuỗi SQL hằng trong switch. Không nối trực tiếp tên cột hoặc `ASC`/`DESC` tùy ý từ request vào câu truy vấn.

## 5. Đếm đúng kết quả khi có JOIN

Count query là phần dễ sai nhất của phân trang với join. Trước khi viết count, cần xác định đơn vị mà giao diện đang phân trang: đơn hàng, khách hàng, dòng hàng hay nhóm tổng hợp.

### 5.1. JOIN một-nhiều làm nhân số hàng

Giả sử một đơn hàng có 4 dòng hàng. Truy vấn:

```sql
SELECT o.id, ol.id
FROM orders o
JOIN order_lines ol ON ol.order_id = o.id
```

trả về 4 hàng cho cùng một `o.id`. `COUNT(*)` trên kết quả join sẽ đếm 4, trong khi trang danh sách có thể chỉ hiển thị một đơn hàng.

Nếu phân trang theo đơn hàng, count phải đếm đơn hàng duy nhất:

```sql
SELECT COUNT(DISTINCT o.id)
FROM orders o
JOIN order_lines ol ON ol.order_id = o.id
WHERE o.tenant_id = :tenantId
```

Nếu chỉ cần kiểm tra đơn hàng có ít nhất một dòng phù hợp, `EXISTS` thường tránh nhân hàng:

```sql
SELECT COUNT(*)
FROM orders o
WHERE o.tenant_id = :tenantId
  AND EXISTS (
      SELECT 1
      FROM order_lines ol
      WHERE ol.order_id = o.id
        AND ol.product_code = :productCode
  )
```

Chọn `COUNT(DISTINCT ...)` hoặc `EXISTS` dựa trên cấu trúc và execution plan. Mục tiêu là đếm đúng đơn vị logic.

### 5.2. LEFT JOIN và COUNT

Với `LEFT JOIN`, `COUNT(*)` vẫn đếm một hàng cho đơn hàng không có dòng con vì hàng phía cha vẫn tồn tại. `COUNT(ol.id)` chỉ đếm các dòng con thực sự có ID và trả 0 khi không có dòng. Khi tính số dòng hàng, dùng `COUNT(ol.id)` thay vì `COUNT(*)`.

### 5.3. DISTINCT có thể làm thay đổi ý nghĩa

`COUNT(DISTINCT o.id)` đúng khi phân trang theo đơn hàng. Nếu giao diện thực sự phân trang từng dòng hàng, dùng count theo dòng hàng. Đừng thêm `DISTINCT` chỉ để số đếm trông hợp lý; hãy xác định loại bản ghi mà mỗi hàng trong trang đại diện.

## 6. Phân trang truy vấn tổng hợp

Một báo cáo có thể phân trang theo nhóm, chẳng hạn tổng doanh thu theo khách hàng. Khi đó, mỗi hàng kết quả là một nhóm `customer_id`, không phải một đơn hàng.

### 6.1. Truy vấn nhóm

```sql
SELECT o.customer_id,
       COUNT(*) AS order_count,
       SUM(o.total_amount) AS revenue
FROM orders o
WHERE o.tenant_id = :tenantId
  AND o.created_at >= :from
  AND o.created_at < :to
GROUP BY o.customer_id
ORDER BY revenue DESC, o.customer_id ASC
LIMIT :limit OFFSET :offset
```

Phân trang được áp dụng sau `GROUP BY` và `ORDER BY`. Nếu giới hạn các đơn hàng trước khi nhóm, kết quả sẽ là tổng hợp trên một phần dữ liệu chứ không phải toàn bộ khoảng thời gian được yêu cầu.

### 6.2. Đếm số nhóm, không đếm số đơn hàng

Để tính tổng số phần tử trang, cần đếm số khách hàng tạo ra nhóm:

```sql
SELECT COUNT(*)
FROM (
    SELECT o.customer_id
    FROM orders o
    WHERE o.tenant_id = :tenantId
      AND o.created_at >= :from
      AND o.created_at < :to
    GROUP BY o.customer_id
) grouped_customers
```

Count query phải áp dụng cùng filter và cùng định nghĩa nhóm. `COUNT(*) FROM orders` sẽ đếm số đơn hàng, không phải số khách hàng trong báo cáo.

### 6.3. HAVING và filter trên aggregate

Nếu báo cáo chỉ hiển thị khách hàng có doanh thu vượt ngưỡng, điều kiện đó thuộc `HAVING`:

```sql
SELECT o.customer_id,
       SUM(o.total_amount) AS revenue
FROM orders o
WHERE o.tenant_id = :tenantId
GROUP BY o.customer_id
HAVING SUM(o.total_amount) >= :minimumRevenue
```

Count query phải áp dụng cùng `HAVING`, thường bằng cách đếm các hàng từ subquery chứa `GROUP BY` và `HAVING`:

```sql
SELECT COUNT(*)
FROM (
    SELECT o.customer_id
    FROM orders o
    WHERE o.tenant_id = :tenantId
    GROUP BY o.customer_id
    HAVING SUM(o.total_amount) >= :minimumRevenue
) result_groups
```

Không thể thay điều kiện trên aggregate bằng `WHERE` trước khi nhóm. `WHERE` lọc hàng đầu vào; `HAVING` lọc nhóm sau khi tổng hợp.

## 7. Content query và count query trong reactive pipeline

### 7.1. Kết hợp kết quả

Với SQL tự viết, có thể tạo hai publisher: một publisher lấy các hàng trang hiện tại và một publisher lấy tổng số. Sau đó kết hợp chúng thành `PageResult`.

```java
Mono<List<OrderPageRow>> contentMono = contentSpec
        .map((row, metadata) -> new OrderPageRow(
                row.get("id", Long.class),
                row.get("order_code", String.class),
                row.get("status", String.class),
                row.get("customer_name", String.class),
                row.get("created_at", LocalDateTime.class)
                        .toInstant(ZoneOffset.UTC),
                row.get("line_count", Long.class),
                row.get("total_amount", BigDecimal.class)))
        .all()
        .collectList();

Mono<Long> countMono = countSpec
        .map((row, metadata) -> row.get("total", Long.class))
        .one()
        .defaultIfEmpty(0L);

return contentMono.flatMap(content -> countMono.map(total ->
        new PageResult<>(content, filter.page(), filter.size(), total,
                total / filter.size()
                        + (total % filter.size() == 0 ? 0 : 1))));
```

Đoạn mapping thời gian minh họa cho cột được đọc dưới dạng `LocalDateTime`; kiểu thực tế phụ thuộc database, driver và quy ước múi giờ. Trong ứng dụng, nên thống nhất kiểu temporal và converter phù hợp thay vì giả định mọi database trả cùng kiểu.

Ví dụ chạy content trước rồi count để thể hiện thứ tự tuần tự. Nếu hai publisher độc lập và không chia sẻ một transaction/connection, `Mono.zip(contentMono, countMono)` có thể chạy chúng đồng thời. Khi có reactive transaction, đặc biệt khi cả hai query dùng cùng connection gắn với Reactor Context, cần tránh giả định driver cho phép hai statement chạy đồng thời trên một connection. Tuần tự hóa truy vấn trong transaction là lựa chọn dễ dự đoán hơn.

### 7.2. Vì sao count và content có thể không khớp?

Nếu có bản ghi được thêm hoặc xóa giữa hai query, content và total có thể phản ánh hai trạng thái khác nhau. Điều này thường chấp nhận được với danh sách có thay đổi liên tục. Nếu nghiệp vụ cần snapshot nhất quán, thực hiện cả hai query trong một reactive transaction và chọn isolation level phù hợp với database.

`@Transactional(readOnly = true)` thể hiện ý định chỉ đọc nhưng không tự bảo đảm snapshot isolation. Mức nhất quán phụ thuộc isolation level thực tế và hệ quản trị. Với yêu cầu nhất quán chặt, cần cấu hình isolation rõ ràng, kiểm tra driver và cân nhắc chi phí giữ transaction.

### 7.3. Không phải API nào cũng cần total count

Count query có thể đắt ngang hoặc đắt hơn content query, đặc biệt khi filter chứa join, distinct hoặc group by. Với giao diện cuộn vô hạn, thường chỉ cần biết còn dữ liệu hay không:

1. Truy vấn `size + 1` hàng.
2. Nếu nhận nhiều hơn `size`, đặt `hasNext = true`.
3. Chỉ trả `size` hàng đầu cho client.

Cách này bỏ được count query và thường phù hợp hơn cho luồng dữ liệu lớn. Chọn response có `hasNext` thay vì `totalPages` nếu giao diện không cần tổng số trang.

## 8. Offset pagination và keyset pagination

### 8.1. Offset pagination

Offset phù hợp với giao diện có số trang và cần nhảy trực tiếp đến trang bất kỳ:

```sql
ORDER BY created_at DESC, id DESC
LIMIT :size OFFSET :offset
```

Ưu điểm là dễ hiểu, dễ tích hợp với giao diện bảng. Nhược điểm là offset lớn có thể khiến database phải duyệt và bỏ qua nhiều hàng; dữ liệu thêm/xóa trong lúc người dùng chuyển trang cũng có thể làm hàng bị lặp hoặc bị bỏ qua.

### 8.2. Keyset pagination

Keyset dùng giá trị cuối của trang trước làm cursor. Với thứ tự `created_at DESC, id DESC`, điều kiện trang tiếp theo là:

```sql
WHERE o.tenant_id = :tenantId
  AND (
      o.created_at < :lastCreatedAt
      OR (o.created_at = :lastCreatedAt AND o.id < :lastId)
  )
ORDER BY o.created_at DESC, o.id DESC
LIMIT :size
```

Cursor cần chứa đủ mọi trường sort để xác định vị trí duy nhất, bao gồm khóa phụ `id`. Nếu chỉ chứa `created_at` và nhiều đơn hàng có cùng timestamp, trang tiếp theo có thể bỏ sót hoặc lặp bản ghi.

Keyset pagination thường hiệu quả hơn cho việc duyệt sâu và ít bị dịch chuyển bởi các bản ghi mới được thêm trước cursor. Nó không thuận tiện cho việc nhảy thẳng đến trang số 80 vì cần cursor của trang trước.

### 8.3. Keyset với bộ lọc động

Điều kiện cursor được bổ sung cùng các predicate filter:

```sql
WHERE o.tenant_id = :tenantId
  AND (:status IS NULL OR o.status = :status)
  AND (
      o.created_at < :lastCreatedAt
      OR (o.created_at = :lastCreatedAt AND o.id < :lastId)
  )
```

Trong SQL động, có thể chỉ thêm predicate status khi người dùng cung cấp bộ lọc. Cursor phải được tạo từ cùng sort mode và filter context của trang trước; không tái sử dụng cursor khi người dùng đổi bộ lọc hoặc thứ tự sắp xếp.

### 8.4. Keyset với sort theo aggregate

Nếu sắp xếp theo `SUM(total_amount)`, cursor phải chứa giá trị aggregate và khóa phụ duy nhất, ví dụ `(revenue, customer_id)`. Predicate cursor cần được áp dụng sau khi nhóm hoặc trong một CTE chứa kết quả tổng hợp. Đây là trường hợp SQL tự viết thường dễ kiểm soát hơn Criteria.

## 9. Sắp xếp ổn định và whitelist

Mọi phân trang đều cần thứ tự xác định. Nếu sort theo một cột không duy nhất, thêm khóa duy nhất làm tie-breaker:

```sql
ORDER BY created_at DESC, id DESC
```

Với sort động, whitelist các tổ hợp được hỗ trợ:

```java
String orderBy = switch (filter.sort()) {
    case CREATED_DESC -> "o.created_at DESC, o.id DESC";
    case CREATED_ASC -> "o.created_at ASC, o.id ASC";
    case AMOUNT_DESC -> "total_amount DESC, o.id DESC";
};
```

Không bind tên cột bằng placeholder và không nối chuỗi sort từ request. Bind parameter chỉ dành cho giá trị, không dành cho identifier hay cú pháp SQL.

Với sort theo alias aggregate, cần bảo đảm alias có mặt trong query scope và cú pháp database cho phép dùng alias trong `ORDER BY`. Nếu không, lặp biểu thức hoặc bọc truy vấn trong CTE/subquery.

## 10. Index và tối ưu truy vấn

Các truy vấn lọc động, join và aggregate cần được tối ưu theo dữ liệu thật:

- Tạo index phù hợp với điều kiện thường dùng, ví dụ `(tenant_id, status, created_at)` nếu query thường lọc tenant và status rồi sort theo thời gian.
- Index trên khóa ngoại dùng để join, ví dụ `orders(customer_id)` hoặc `order_lines(order_id)`.
- Chỉ select các cột cần thiết cho DTO trang, tránh tải các cột lớn không dùng.
- Đánh giá index theo selectivity và execution plan; thêm quá nhiều index làm tăng chi phí ghi và dung lượng.
- Kiểm tra truy vấn count riêng vì count có thể có execution plan khác content query.
- Với aggregate, kiểm tra chi phí group/sort và cân nhắc bảng tổng hợp/materialized view nếu workload yêu cầu.
- Dùng dữ liệu có kích thước gần production để đo latency, số hàng đọc và số hàng trả về.

Không giả định SQL tự viết luôn nhanh hơn Template. Template có thể sinh SQL tốt cho truy vấn chuẩn; SQL tùy chỉnh chỉ giúp khi nó giải quyết được yêu cầu biểu đạt hoặc tối ưu đã được đo.

## 11. Những lỗi thường gặp

### Count query không dùng cùng bộ lọc

Content có filter trạng thái nhưng count quên filter đó sẽ trả tổng số sai. Tạo predicate hoặc SQL where dùng chung cho cả hai query.

### Đếm hàng join thay vì đếm phần tử logic

Join một-nhiều làm một entity cha xuất hiện nhiều lần. Dùng `COUNT(DISTINCT parent.id)` hoặc `EXISTS` khi phân trang theo entity cha.

### Phân trang trước khi GROUP BY

Giới hạn các hàng nguồn trước khi tổng hợp làm thay đổi kết quả nhóm. Nếu mỗi hàng trang là một nhóm, áp dụng group/having trước rồi mới sort và limit/offset.

### Count số hàng thay vì số nhóm

Báo cáo doanh thu theo khách hàng cần count số khách hàng thỏa `GROUP BY`/`HAVING`, không phải số đơn hàng nguồn. Đếm từ subquery tạo nhóm.

### Dùng WHERE thay cho HAVING

`WHERE` lọc hàng trước aggregate; `HAVING` lọc kết quả nhóm. Điều kiện trên `SUM`, `COUNT` hoặc `AVG` thuộc `HAVING`.

### Bỏ sort tie-breaker

Nếu nhiều hàng có cùng giá trị sort, thứ tự trang không ổn định. Thêm khóa duy nhất làm tiêu chí phụ.

### Nhận tên cột sort từ client

Identifier không thể bind như value. Dùng enum/whitelist cho các lựa chọn sort được hỗ trợ.

### Chạy count và content không nhất quán

Hai query có thể quan sát dữ liệu khác nhau nếu có cập nhật đồng thời. Chấp nhận eventual page metadata hoặc dùng transaction/isolation phù hợp.

### Thu thập quá nhiều dữ liệu trước khi phân trang

Không tải toàn bộ entity rồi dùng Java `subList` để tạo trang. Đẩy filter, sort và limit xuống database để giới hạn I/O và bộ nhớ.

## 12. Quy trình xây dựng một endpoint phân trang

1. Xác định đơn vị được phân trang: entity cha, hàng join hay nhóm aggregate.
2. Thiết kế filter DTO và xác thực điều kiện bắt buộc, quyền truy cập, kích thước trang.
3. Chọn offset pagination cho giao diện cần số trang; chọn keyset cho duyệt sâu hoặc cuộn liên tục.
4. Chọn Template cho truy vấn entity-centric đơn giản; chọn SQL cho join, projection hoặc aggregate phức tạp.
5. Tạo content query với predicate, sort ổn định và limit/cursor.
6. Tạo count query riêng nếu API cần tổng số; bảo đảm nó đếm đúng đơn vị logic và không chứa pagination.
7. Với join một-nhiều, dùng `DISTINCT`, `EXISTS` hoặc subquery để tránh đếm trùng.
8. Với aggregate, đếm số nhóm từ subquery có cùng `GROUP BY` và `HAVING`.
9. Bind mọi giá trị và whitelist sort identifier.
10. Kết hợp publisher bằng Reactor; chọn tuần tự hay song song dựa trên transaction và connection pool.
11. Kiểm tra transaction/isolation nếu content và count cần cùng snapshot.
12. Đọc execution plan, kiểm tra index và đo hiệu năng trên dữ liệu gần thực tế.

## 13. Checklist ghi nhớ

- [ ] Filter được validate và chuẩn hóa trước khi xây dựng query.
- [ ] Điều kiện tenant/quyền truy cập luôn được áp dụng.
- [ ] Content query và count query dùng cùng bộ lọc logic.
- [ ] Count query bỏ sort, limit và offset.
- [ ] JOIN một-nhiều không làm đếm trùng entity cha.
- [ ] Phân trang theo aggregate đếm số nhóm, giữ nguyên `GROUP BY` và `HAVING` trong count.
- [ ] Limit/offset được áp dụng sau khi xác định đúng tập kết quả hoặc nhóm.
- [ ] Sort có khóa phụ duy nhất và lựa chọn động dùng whitelist.
- [ ] Mọi giá trị đầu vào được bind bằng tham số.
- [ ] Offset được tính an toàn và kích thước trang có giới hạn.
- [ ] Keyset cursor chứa đủ trường sort và không được tái sử dụng khi filter/sort thay đổi.
- [ ] Content/count được kết hợp trong reactive pipeline, không gọi `block()` hoặc `subscribe()` nội bộ.
- [ ] Transaction/isolation đáp ứng mức nhất quán mà nghiệp vụ yêu cầu.
- [ ] Có integration test cho join, count distinct, group/having và các tổ hợp filter.
- [ ] Index và execution plan đã được xem xét với dữ liệu đại diện.

Phân trang với bộ lọc động, join và truy vấn tổng hợp đòi hỏi xác định chính xác đơn vị kết quả trước khi viết content và count query. Khi bộ lọc được dùng chung, join không làm nhân bản phần tử logic, aggregate được phân trang sau khi nhóm và thứ tự luôn ổn định, API có thể trả dữ liệu nhất quán và giới hạn được chi phí truy vấn. Với Spring Data R2DBC, Template phù hợp cho truy vấn entity đơn giản; SQL tùy chỉnh phù hợp khi cần kiểm soát join, aggregate và cách đếm kết quả.
