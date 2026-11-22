# Lựa chọn giữa truy vấn động của Template và SQL tự viết

Trong Spring Data R2DBC, một yêu cầu tìm kiếm thường có nhiều bộ lọc tùy chọn: trạng thái, khách hàng, khoảng thời gian, từ khóa, thứ tự sắp xếp và giới hạn kết quả. Có thể xây dựng truy vấn bằng API `Query`/`Criteria` của `R2dbcEntityTemplate`, hoặc viết SQL trực tiếp qua `DatabaseClient` hay `@Query` trong Repository.

Hai cách đều có chỗ đứng. Template phù hợp với truy vấn xoay quanh entity, dùng các điều kiện lọc, sắp xếp và phân trang thông thường. SQL tự viết phù hợp khi cần kiểm soát cấu trúc truy vấn, join, tổng hợp, CTE, window function hoặc tính năng riêng của database. Quyết định nên dựa trên độ phức tạp của truy vấn, khả năng đọc hiểu, yêu cầu hiệu năng, tính di động và cách ánh xạ kết quả.

## 1. Hai cách tiếp cận

### 1.1. Truy vấn động bằng R2dbcEntityTemplate

`R2dbcEntityTemplate` là API mức cao của Spring Data R2DBC để thao tác với entity. Nó sử dụng mapping metadata của Spring Data và dialect của database để tạo câu lệnh SQL từ các đối tượng truy vấn.

Các thành phần thường dùng:

- `Criteria`: biểu diễn điều kiện lọc trên thuộc tính/cột.
- `Query`: kết hợp điều kiện với sort, limit và offset.
- `Update`: mô tả các thuộc tính cần cập nhật.
- `R2dbcEntityTemplate`: thực thi select, insert, update và delete theo mapping entity.

Ví dụ một truy vấn có điều kiện trạng thái và thời gian:

```java
Criteria criteria = Criteria.where("tenantId").is(tenantId)
        .and("status").is("PAID")
        .and("createdAt").greaterThanOrEquals(from);

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt"),
                      Sort.Order.desc("id")))
        .limit(20)
        .offset(0);

return template.select(query, OrderEntity.class);
```

Template tạo truy vấn dựa trên mapping của `OrderEntity`, thực thi qua R2DBC và ánh xạ các hàng kết quả thành entity. Trong ví dụ, các tên như `tenantId` và `createdAt` là thuộc tính Java của entity; mapping metadata xử lý quan hệ với tên cột theo cấu hình.

### 1.2. SQL tự viết qua DatabaseClient

`DatabaseClient` cung cấp API thực thi SQL trực tiếp. Người phát triển quyết định các bảng, join, biểu thức, alias, thứ tự và cấu trúc câu lệnh. Giá trị đầu vào vẫn cần được bind bằng tham số để tránh SQL injection và bảo đảm kiểu dữ liệu được truyền đúng cho driver.

Ví dụ:

```java
return databaseClient.sql("""
        SELECT id, order_code, status
        FROM orders
        WHERE tenant_id = :tenantId
          AND status = :status
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
        """)
    .bind("tenantId", tenantId)
    .bind("status", status)
    .bind("limit", 20)
    .bind("offset", 0)
    .map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("order_code", String.class),
            row.get("status", String.class)))
    .all();
```

Ở đây code tự viết SQL và ánh xạ kết quả sang `OrderSummary`. `DatabaseClient` không tự suy ra entity mapping cho mọi kiểu projection tùy ý trong callback `map`; người viết phải chỉ rõ cách đọc cột và tạo kết quả.

### 1.3. SQL khai báo trong Repository bằng @Query

Nếu câu SQL tùy chỉnh có cấu trúc cố định, có thể khai báo trực tiếp bằng `@Query` trong một Repository method:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    @Query("""
        SELECT * FROM orders
        WHERE tenant_id = :tenantId
          AND status = :status
        ORDER BY created_at DESC
        """)
    Flux<OrderEntity> findByTenantAndStatus(
            Long tenantId, String status);
}
```

`@Query` hữu ích khi câu SQL được biết trước và không cần ghép nhiều đoạn cấu trúc theo runtime. Khi số lượng tổ hợp điều kiện lớn hoặc cần thay đổi nhiều phần câu lệnh theo bộ lọc, có thể dùng `DatabaseClient` để xây dựng SQL có tham số hoặc quay lại Criteria nếu truy vấn thuộc nhóm Template hỗ trợ tốt.

## 2. Xây dựng bộ lọc tùy chọn bằng Criteria

Truy vấn động thường bắt đầu từ một số điều kiện bắt buộc, sau đó bổ sung điều kiện nếu người dùng cung cấp giá trị tương ứng. Ví dụ, mọi truy vấn đều phải giới hạn trong một tenant; trạng thái và thời gian là tùy chọn.

### 2.1. Mô hình bộ lọc

```java
public record OrderFilter(
        Long tenantId,
        String status,
        Instant createdFrom,
        Instant createdTo,
        int limit,
        long offset
) {
}
```

Tenant là điều kiện bắt buộc để giới hạn phạm vi dữ liệu. Trạng thái và khoảng thời gian chỉ được thêm vào khi có giá trị.

### 2.2. Bổ sung Criteria theo điều kiện

```java
public Flux<OrderEntity> search(OrderFilter filter) {
    Criteria criteria = Criteria.where("tenantId").is(filter.tenantId());

    if (filter.status() != null && !filter.status().isBlank()) {
        criteria = criteria.and("status").is(filter.status());
    }

    if (filter.createdFrom() != null) {
        criteria = criteria.and("createdAt")
                .greaterThanOrEquals(filter.createdFrom());
    }

    if (filter.createdTo() != null) {
        criteria = criteria.and("createdAt")
                .lessThan(filter.createdTo());
    }

    Query query = Query.query(criteria)
            .sort(Sort.by(Sort.Order.desc("createdAt"),
                          Sort.Order.desc("id")))
            .limit(filter.limit())
            .offset(filter.offset());

    return template.select(query, OrderEntity.class);
}
```

Đoạn code minh họa cách nối điều kiện vào `Criteria`. `Criteria` là đối tượng mô tả điều kiện; mỗi lần thêm điều kiện, hãy giữ lại kết quả trả về để truy vấn cuối cùng chứa đầy đủ các predicate. Không bỏ qua kết quả của `and(...).is(...)`.

Trong ứng dụng thật, kiểm tra `limit` nằm trong một giới hạn hợp lý, `offset` không âm và khoảng thời gian hợp lệ trước khi xây dựng query. Không để client gửi `limit` quá lớn khiến ứng dụng đọc hàng trăm nghìn bản ghi chỉ trong một request.

### 2.3. Các toán tử Criteria thường dùng

| Nhu cầu | Cách biểu diễn |
|---|---|
| Bằng một giá trị | `Criteria.where("status").is("PAID")` |
| Khác giá trị | `Criteria.where("status").not("CANCELLED")` |
| Lớn hơn | `Criteria.where("totalAmount").greaterThan(amount)` |
| Lớn hơn hoặc bằng | `greaterThanOrEquals(value)` |
| Nhỏ hơn | `lessThan(value)` |
| Trong khoảng | `between(min, max)` |
| Thuộc tập giá trị | `in(values)` |
| Không thuộc tập giá trị | `notIn(values)` |
| Giá trị null | `isNull()` |
| Giá trị không null | `notNull()` |
| Khớp mẫu | `like(pattern)` hoặc toán tử tương ứng được hỗ trợ |

Tên phương thức và tập toán tử khả dụng cần được đối chiếu với phiên bản Spring Data Relational của dự án. Cú pháp so sánh cũng có thể chịu ảnh hưởng của kiểu cột và database.

### 2.4. Phân biệt bỏ qua bộ lọc và tìm giá trị NULL

Một bộ lọc không được cung cấp thường có nghĩa là không thêm điều kiện đó vào truy vấn. Nó không đồng nghĩa với việc tìm những hàng có cột `NULL`.

Ví dụ:

- `status == null` trong request: bỏ qua bộ lọc trạng thái.
- Yêu cầu rõ ràng `status IS NULL`: thêm `Criteria.where("status").isNull()`.

Nếu API cần phân biệt hai trường hợp, DTO nên biểu diễn ý định rõ ràng, chẳng hạn một cờ `onlyWithoutStatus` hoặc một kiểu filter có trạng thái `ANY`, `IS_NULL`, `EQUALS`. Không dùng một giá trị null cho hai ý nghĩa khác nhau.

### 2.5. Kết hợp AND và OR

Các điều kiện đơn giản thường kết hợp bằng AND. Khi có logic OR, hãy nhóm điều kiện để thể hiện đúng thứ tự logic. Ví dụ tìm đơn hàng có trạng thái `PAID` hoặc `SHIPPED` trong cùng tenant. Có thể dùng các nhóm Criteria với API `or`/`and` mà phiên bản Spring Data hỗ trợ.

Với biểu thức logic nhiều tầng, hãy viết điều kiện ra giấy trước khi chuyển thành API. Một truy vấn có dạng:

```sql
WHERE tenant_id = :tenantId
  AND (status = 'PAID' OR status = 'SHIPPED')
  AND created_at >= :from
```

không tương đương với:

```sql
WHERE (tenant_id = :tenantId AND status = 'PAID')
   OR (status = 'SHIPPED' AND created_at >= :from)
```

Nếu API Criteria khó thể hiện hoặc khó đọc đối với biểu thức lồng nhau, SQL tự viết có thể làm ý định rõ hơn.

## 3. Sử dụng Template cho select, update và delete

`R2dbcEntityTemplate` không chỉ dùng để tìm kiếm. Nó còn cung cấp API thao tác dữ liệu dựa trên entity metadata.

### 3.1. Select một hoặc nhiều entity

```java
Mono<OrderEntity> findOne(Long id) {
    Query query = Query.query(Criteria.where("id").is(id));
    return template.selectOne(query, OrderEntity.class);
}

Flux<OrderEntity> findRecent(Long tenantId) {
    Query query = Query.query(Criteria.where("tenantId").is(tenantId))
            .sort(Sort.by(Sort.Order.desc("createdAt")))
            .limit(50);

    return template.select(query, OrderEntity.class);
}
```

`selectOne` trả về `Mono` vì kết quả tối đa một entity; `select` trả về `Flux` cho không hoặc nhiều kết quả. Nếu điều kiện không duy nhất nhưng dùng `selectOne`, cần hiểu cách API xử lý trường hợp có nhiều hàng và thiết kế điều kiện phù hợp.

### 3.2. Update có điều kiện

```java
Mono<Long> markAsExpired(Instant cutoff) {
    Query query = Query.query(
            Criteria.where("status").is("PENDING")
                    .and("expiresAt").lessThan(cutoff));

    Update update = Update.update("status", "EXPIRED");

    return template.update(query, update, OrderEntity.class);
}
```

API Template có thể tạo câu `UPDATE` từ điều kiện và tập thuộc tính thay đổi. Kết quả thường biểu diễn số hàng bị ảnh hưởng. Đây là cách thuận tiện cho update đơn giản trên một entity type.

Lưu ý rằng update theo Query là thao tác trực tiếp trên các hàng thỏa điều kiện. Nó không nhất thiết tải từng entity, gọi phương thức domain trên từng instance hoặc chạy cùng quy trình như đọc entity rồi `save`. Nếu nghiệp vụ cần kiểm tra chuyển trạng thái cho từng đơn hàng, phát domain event hoặc xử lý optimistic locking theo từng entity, hãy thiết kế luồng đọc/cập nhật phù hợp và kiểm tra hành vi versioning của API được dùng.

### 3.3. Delete theo Criteria

```java
Mono<Long> deleteExpiredDrafts(Instant cutoff) {
    Query query = Query.query(
            Criteria.where("status").is("DRAFT")
                    .and("createdAt").lessThan(cutoff));

    return template.delete(query, OrderEntity.class);
}
```

Delete theo Query phù hợp khi có thể xác định chính xác tập hàng cần xóa bằng điều kiện. Với thao tác xóa hàng loạt, cần cân nhắc khóa ngoại, audit, chính sách lưu trữ và yêu cầu phát sự kiện. Nếu cần xử lý từng entity trước khi xóa, không nên thay thế bằng một câu delete hàng loạt chỉ vì ngắn hơn.

## 4. Khi nào SQL tự viết phù hợp hơn?

Criteria có giới hạn về biểu đạt. Một số truy vấn yêu cầu cấu trúc SQL rõ ràng và có thể không phù hợp với mô hình query-by-entity.

### 4.1. JOIN nhiều bảng và projection tổng hợp

Ví dụ một trang quản trị cần danh sách đơn hàng cùng tên khách hàng và số dòng hàng:

```sql
SELECT o.id,
       o.order_code,
       c.display_name AS customer_name,
       COUNT(ol.id) AS line_count
FROM orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines ol ON ol.order_id = o.id
WHERE o.tenant_id = :tenantId
GROUP BY o.id, o.order_code, c.display_name
ORDER BY o.created_at DESC, o.id DESC
```

Đây là truy vấn kết hợp nhiều bảng và tổng hợp. SQL tự viết giúp thể hiện join, group và alias một cách trực tiếp. Kết quả nên được ánh xạ sang projection/DTO, không nhất thiết phải dựng toàn bộ graph entity.

### 4.2. CTE, window function và truy vấn phân tích

Các yêu cầu như lấy bản ghi mới nhất theo từng khách hàng, xếp hạng theo doanh thu, tính tổng lũy kế hoặc truy vấn cây phân cấp thường sử dụng CTE và window function. Khi truy vấn phụ thuộc các cấu trúc này, SQL trực tiếp thường dễ kiểm soát hơn.

Ví dụ:

```sql
WITH ranked_orders AS (
    SELECT o.*,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.created_at DESC, o.id DESC
           ) AS row_number
    FROM orders o
    WHERE o.tenant_id = :tenantId
)
SELECT id, customer_id, order_code, created_at
FROM ranked_orders
WHERE row_number = 1
```

Không phải mọi database hoặc phiên bản đều hỗ trợ cùng cú pháp. SQL tự viết cho phép tận dụng tính năng của database mục tiêu, đồng thời làm tăng sự phụ thuộc vào hệ quản trị đó.

### 4.3. Hàm và kiểu dữ liệu riêng của database

Nếu cần JSON operator, full-text search, array operation, spatial function, locking clause hoặc hint đặc thù, SQL tự viết có thể cần thiết. Template có thể tận dụng dialect cho những khác biệt được hỗ trợ, nhưng không phải một bộ dựng SQL tổng quát có thể biểu diễn mọi tính năng của mọi database.

### 4.4. Tối ưu truy vấn đã đo được

Khi execution plan cho thấy truy vấn được sinh từ Template không đáp ứng yêu cầu, SQL tự viết giúp kiểm soát join, projection, predicate, hint hoặc cấu trúc subquery. Tuy nhiên, không nên chuyển sang SQL thủ công chỉ vì giả định nó luôn nhanh hơn. Trước tiên hãy đo thời gian, đọc execution plan, kiểm tra index, số hàng đọc và dữ liệu được trả về.

## 5. Xây dựng SQL động an toàn

SQL động hữu ích khi số lượng bộ lọc thay đổi theo request. Nguyên tắc quan trọng là chỉ ghép những đoạn cấu trúc SQL do ứng dụng kiểm soát; mọi giá trị dữ liệu phải được bind qua tham số.

### 5.1. Ghép điều kiện tùy chọn và bind tham số

```java
public Flux<OrderSummary> search(OrderFilter filter) {
    StringBuilder sql = new StringBuilder("""
            SELECT id, order_code, status
            FROM orders
            WHERE tenant_id = :tenantId
            """);

    if (filter.status() != null && !filter.status().isBlank()) {
        sql.append(" AND status = :status");
    }

    if (filter.createdFrom() != null) {
        sql.append(" AND created_at >= :createdFrom");
    }

    if (filter.createdTo() != null) {
        sql.append(" AND created_at < :createdTo");
    }

    sql.append(" ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset");

    DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql.toString())
            .bind("tenantId", filter.tenantId())
            .bind("limit", filter.limit())
            .bind("offset", filter.offset());

    if (filter.status() != null && !filter.status().isBlank()) {
        spec = spec.bind("status", filter.status());
    }
    if (filter.createdFrom() != null) {
        spec = spec.bind("createdFrom", filter.createdFrom());
    }
    if (filter.createdTo() != null) {
        spec = spec.bind("createdTo", filter.createdTo());
    }

    return spec.map((row, metadata) -> new OrderSummary(
            row.get("id", Long.class),
            row.get("order_code", String.class),
            row.get("status", String.class)))
        .all();
}
```

Mỗi điều kiện chỉ được thêm vào SQL khi tham số tương ứng có giá trị; cùng lúc đó code bind đúng tham số. Cách này tránh việc bind một tham số không xuất hiện trong câu lệnh. Nếu cần bind `NULL` một cách có chủ đích, R2DBC thường yêu cầu dùng `bindNull(name, Type.class)` thay vì `bind(name, null)`.

### 5.2. Không nối trực tiếp dữ liệu người dùng vào SQL

Không làm như sau:

```java
String sql = "SELECT * FROM orders WHERE status = '" + status + "'";
```

Nếu `status` đến từ request, dữ liệu có thể phá vỡ cấu trúc SQL và tạo lỗ hổng injection. Dùng tham số:

```java
databaseClient.sql("SELECT * FROM orders WHERE status = :status")
        .bind("status", status);
```

Bind tham số chỉ áp dụng cho giá trị dữ liệu. Tên bảng, tên cột, toán tử và hướng sort là thành phần cấu trúc SQL; không thể thay thế chúng bằng bind parameter thông thường.

### 5.3. Whitelist cho tên cột và hướng sắp xếp

Nếu API cho phép chọn trường sắp xếp, chuyển giá trị đầu vào sang một tập lựa chọn cố định:

```java
String orderBy = switch (filter.sortBy()) {
    case CREATED_AT -> "created_at";
    case ORDER_CODE -> "order_code";
    case STATUS -> "status";
};

String direction = filter.descending() ? "DESC" : "ASC";
sql.append(" ORDER BY ").append(orderBy).append(' ').append(direction);
```

`sortBy` ở đây là enum do ứng dụng định nghĩa. Không nối một chuỗi cột tùy ý từ client vào SQL. Với Template, dùng `Sort` và các thuộc tính được phép sắp xếp để giảm việc tự quản lý tên cột.

### 5.4. Tham số NULL và điều kiện tùy chọn

Có thể viết một câu SQL cố định theo dạng:

```sql
WHERE (:status IS NULL OR status = :status)
```

Nhưng cách này cần bind null đúng kiểu bằng `bindNull` và có thể khiến optimizer khó tận dụng index như một predicate cụ thể tùy database. Một truy vấn động chỉ thêm predicate khi có bộ lọc thường dễ đọc và có thể tạo execution plan tốt hơn. Hãy đo trên database mục tiêu.

## 6. So sánh Template và SQL tự viết

| Tiêu chí | R2dbcEntityTemplate với Criteria | SQL tự viết qua DatabaseClient / @Query |
|---|---|---|
| Truy vấn CRUD theo entity | Rất phù hợp | Có thể làm nhưng nhiều mã mapping hơn |
| Bộ lọc tùy chọn đơn giản | Dễ ghép bằng Criteria | Phải quản lý SQL và tham số |
| Sort, limit, offset | API Query hỗ trợ trực tiếp | Viết rõ trong SQL |
| Join nhiều bảng | Không phải điểm mạnh của Criteria | Linh hoạt và rõ ràng |
| Group by, aggregate, window function | Hạn chế theo API truy vấn | Phù hợp |
| Tính năng riêng của database | Phụ thuộc dialect và API hỗ trợ | Có thể khai thác trực tiếp |
| Mapping entity | Dựa trên metadata entity | `@Query` có thể map entity; DatabaseClient callback thường map thủ công |
| Projection tùy chỉnh | Có thể cần mapping bổ sung | Chủ động alias và map DTO |
| Khả năng di động | Thường cao hơn với thao tác chuẩn | Phụ thuộc cú pháp SQL đã viết |
| Kiểm soát SQL | Framework sinh SQL | Người phát triển kiểm soát câu lệnh |
| Bảo trì | Gọn với query entity-centric | Tốt khi SQL phức tạp được đặt tên và tổ chức rõ |

Không có lựa chọn nào luôn tốt hơn. Template giảm boilerplate và tận dụng mapping metadata. SQL tự viết đem lại khả năng biểu đạt và kiểm soát chi tiết. Cả hai vẫn cần kiểm thử với driver và database thực tế.

## 7. Tiêu chí lựa chọn trong thực tế

### Chọn Template khi

- Truy vấn chủ yếu lấy một loại entity.
- Điều kiện lọc là bằng, so sánh, khoảng giá trị hoặc tập giá trị.
- Các bộ lọc có thể bật/tắt theo request.
- Chỉ cần sắp xếp, giới hạn và phân trang thông thường.
- Update/delete có thể biểu diễn bằng một tập điều kiện rõ ràng.
- Muốn tận dụng mapping metadata và giảm việc tự ánh xạ cột.

### Chọn SQL tự viết khi

- Cần join nhiều bảng hoặc trả về dữ liệu tổng hợp.
- Cần CTE, window function, subquery phức tạp hoặc biểu thức database-specific.
- Cần projection chỉ đọc với alias và phép tính cụ thể.
- Cần kiểm soát chính xác SQL để tối ưu sau khi đã đo và phân tích execution plan.
- Cần thao tác mà Criteria API không biểu đạt được hoặc biểu đạt làm code khó hiểu.

### Kết hợp hai cách trong cùng ứng dụng

Một module có thể dùng Repository cho CRUD cơ bản, Template cho tìm kiếm theo bộ lọc, và `DatabaseClient` cho báo cáo hoặc truy vấn đặc biệt. Điều này bình thường nếu ranh giới được đặt rõ ràng:

- Repository chứa các thao tác dữ liệu gắn với aggregate.
- Một lớp query service hoặc custom repository chứa truy vấn phức tạp.
- Service nghiệp vụ phối hợp các kết quả và thực hiện quy tắc nghiệp vụ.

Không nên tạo một abstraction truy vấn chung quá phức tạp chỉ để buộc mọi truy vấn đi qua cùng một API. Hãy để hình thức truy vấn phản ánh nhu cầu thực tế.

## 8. Phân trang và sắp xếp

### 8.1. Sắp xếp ổn định

Khi dùng `limit` và `offset`, cần có thứ tự sắp xếp xác định. Nếu chỉ sort theo `createdAt` và nhiều hàng có cùng thời điểm, thứ tự giữa chúng có thể thay đổi giữa các lần truy vấn. Thêm khóa duy nhất làm tiêu chí phụ, ví dụ `id`, để thứ tự ổn định:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));
```

SQL tương ứng:

```sql
ORDER BY created_at DESC, id DESC
```

### 8.2. Offset pagination

Offset pagination phù hợp với trang dữ liệu nhỏ và giao diện cần nhảy đến một trang cụ thể. Tuy nhiên, offset lớn có thể khiến database phải đọc và bỏ qua nhiều hàng trước khi trả kết quả. Khi dữ liệu tăng lớn, hãy đo hiệu năng và cân nhắc keyset pagination.

### 8.3. Keyset pagination

Keyset pagination dùng giá trị cuối của trang trước làm mốc. Ví dụ sắp xếp giảm dần theo `created_at`, rồi `id`:

```sql
SELECT id, order_code, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize
```

Cú pháp so sánh tuple không được hỗ trợ giống nhau trên mọi database; có thể viết điều kiện tương đương bằng biểu thức `OR`:

```sql
AND (created_at < :lastCreatedAt
     OR (created_at = :lastCreatedAt AND id < :lastId))
```

Template có thể biểu diễn điều kiện keyset đơn giản bằng Criteria lồng/ghép nếu API phiên bản đang dùng hỗ trợ rõ ràng. Nếu điều kiện trở nên khó đọc hoặc cần tuple comparison riêng, SQL tự viết thường dễ kiểm soát hơn.

### 8.4. Đếm tổng số kết quả

Để hiển thị tổng số trang, có thể cần một truy vấn `COUNT(*)` với cùng bộ lọc. Với truy vấn phức tạp có join/group, câu count có thể cần cấu trúc khác với câu lấy dữ liệu. Không nên giả định mọi truy vấn Template tự động cung cấp tổng số hàng khi đã dùng `limit`/`offset`. Hãy xác định API có thực sự cần total count hay chỉ cần biết còn trang tiếp theo hay không.

## 9. Mapping kết quả SQL tự viết

Khi dùng `DatabaseClient`, hãy chọn kiểu kết quả theo nhu cầu:

- Entity nếu kết quả có đầy đủ cột cần thiết và muốn dùng mapping entity phù hợp.
- DTO/projection nếu kết quả là join, aggregate hoặc chỉ gồm một phần cột.
- Scalar nếu truy vấn chỉ trả về một giá trị như `COUNT(*)`.

Ví dụ DTO cho truy vấn join:

```java
public record OrderSummary(
        Long id,
        String orderCode,
        String customerName,
        Long lineCount
) {
}
```

Với callback mapping, tên alias SQL nên rõ ràng và nhất quán với tên trường DTO:

```sql
SELECT o.id,
       o.order_code AS order_code,
       c.display_name AS customer_name,
       COUNT(ol.id) AS line_count
FROM ...
```

Đọc cột theo alias trong callback và chuyển sang kiểu Java phù hợp. Một số database/driver có thể trả kiểu số khác nhau cho biểu thức tổng hợp; cần kiểm tra kiểu thực tế thay vì ép kiểu tùy tiện.

## 10. Hiệu năng và khả năng bảo trì

### 10.1. Đo trước khi tối ưu

Một câu SQL viết tay không mặc nhiên nhanh hơn SQL do Template sinh. Hiệu năng phụ thuộc index, số hàng, selectivity của predicate, join order, thống kê database, connection pool và lượng dữ liệu chuyển về ứng dụng. Dùng execution plan và metrics để tìm nút thắt trước khi thay đổi cách truy vấn.

### 10.2. Chỉ lấy các cột cần thiết

Với màn hình tổng hợp, projection chỉ đọc các cột cần dùng giúp giảm I/O và dữ liệu truyền qua mạng. Nếu dùng entity đầy đủ, kiểm tra xem entity có trường lớn hoặc dữ liệu không cần thiết cho use case không.

### 10.3. Tránh N+1 query

Nếu đọc danh sách đơn hàng rồi gọi thêm một truy vấn khách hàng cho từng đơn, số truy vấn có thể tăng theo số hàng. Cân nhắc join/projection bằng SQL hoặc một truy vấn lấy tập khách hàng theo ID. R2DBC là non-blocking API nhưng không làm cho hàng trăm truy vấn thừa trở nên miễn phí.

### 10.4. Đặt tên và tổ chức truy vấn

Truy vấn SQL dài nên nằm trong custom repository hoặc query service có tên theo nghiệp vụ. Tránh ghép SQL trong controller hoặc rải các đoạn query builder khắp service. Với Criteria, tách phương thức tạo predicate nếu bộ lọc được tái sử dụng và vẫn giữ được ý nghĩa rõ ràng.

### 10.5. Tính di động giữa database

Template tận dụng dialect cho các thao tác được abstraction hỗ trợ, nên có thể giảm khác biệt giữa các database. SQL tự viết cần được kiểm tra khi đổi database: hàm, kiểu dữ liệu, paging syntax, JSON operator, locking clause và cách so sánh có thể khác nhau. Nếu dự án chỉ hỗ trợ một database, dùng SQL đặc thù có thể là lựa chọn hợp lý khi lợi ích rõ ràng.

## 11. Các lỗi thường gặp

### Dùng Criteria cho truy vấn quá phức tạp

Khi phải mô phỏng nhiều join, aggregate và điều kiện lồng nhau bằng nhiều lớp code, ý định SQL trở nên khó nhận biết. Hãy dùng SQL trực tiếp nếu nó diễn đạt truy vấn rõ hơn.

### Dùng SQL tự viết cho mọi thao tác đơn giản

CRUD và bộ lọc cơ bản có thể được thực hiện gọn bằng Repository hoặc Template. Viết SQL riêng cho mọi thao tác làm tăng mã mapping và chi phí bảo trì không cần thiết.

### Ghép giá trị đầu vào vào chuỗi SQL

Đây là nguồn lỗi injection. Bind mọi giá trị bằng named parameter hoặc positional parameter. Chỉ ghép cấu trúc cố định do ứng dụng kiểm soát; whitelist tên cột và hướng sort.

### Bỏ sót điều kiện tenant hoặc quyền truy cập

Truy vấn động có nhiều nhánh dễ vô tình bỏ điều kiện giới hạn dữ liệu. Các điều kiện bảo mật như tenant, owner hoặc phạm vi quyền phải được đưa vào mọi nhánh truy vấn và kiểm thử riêng.

### Dùng tên cột thay cho tên thuộc tính trong Criteria

Criteria làm việc cùng mapping metadata của entity. Kiểm tra quy tắc tên thuộc tính/cột của phiên bản đang dùng, nhất là khi dùng snake_case hoặc `@Column`. Integration test giúp phát hiện truy vấn sai tên cột.

### Phân trang không có sort ổn định

Kết quả có thể trùng hoặc thiếu giữa các trang nếu nhiều hàng có cùng giá trị sort. Thêm khóa duy nhất làm tiêu chí phụ và cân nhắc keyset pagination khi offset lớn.

### Giả định Template update luôn tương đương đọc rồi save

Bulk update theo Query không chạy các hành vi domain trên từng entity. Nếu cần validation theo từng object, audit hoặc optimistic locking, hãy chọn luồng phù hợp và kiểm tra hành vi API cụ thể.

## 12. Quy trình chọn và triển khai truy vấn

1. Xác định dữ liệu đầu ra: entity đầy đủ, projection hay scalar.
2. Liệt kê điều kiện bắt buộc, điều kiện tùy chọn và quy tắc phân quyền.
3. Kiểm tra truy vấn có thể biểu diễn rõ bằng `Criteria` hay cần join/aggregate/SQL đặc thù.
4. Chọn Template cho truy vấn entity-centric đơn giản; chọn SQL tự viết khi cấu trúc truy vấn cần được kiểm soát.
5. Bind mọi giá trị đầu vào; whitelist các identifier và sort option.
6. Thiết kế sort ổn định, giới hạn kích thước trang và chọn offset/keyset phù hợp.
7. Kiểm tra index và execution plan với dữ liệu gần thực tế.
8. Kiểm thử dữ liệu rỗng, null, bộ lọc kết hợp, tenant boundary và trường hợp nhiều hàng.
9. Kiểm thử trên database/driver mục tiêu và theo dõi thời gian truy vấn khi vận hành.

## 13. Checklist ghi nhớ

- [ ] Criteria phù hợp với các predicate đơn giản và bộ lọc tùy chọn.
- [ ] Query hỗ trợ sort, limit và offset cho phân trang thông thường.
- [ ] SQL tự viết phù hợp với join, aggregate, CTE, window function và tính năng riêng của database.
- [ ] Đã chọn kiểu kết quả phù hợp: entity, DTO/projection hoặc scalar.
- [ ] Mọi giá trị dữ liệu được bind qua tham số, không nối trực tiếp input vào SQL.
- [ ] Tên cột và hướng sort động được chọn từ whitelist.
- [ ] Điều kiện tenant và quyền truy cập luôn có mặt trong mọi nhánh truy vấn.
- [ ] Phân biệt bộ lọc bị bỏ qua với điều kiện tìm `NULL`.
- [ ] Có sort ổn định và giới hạn trang hợp lý.
- [ ] Truy vấn phức tạp đã được kiểm tra bằng execution plan và index phù hợp.
- [ ] Integration test chạy trên database/driver mục tiêu.

Template và SQL tự viết là hai công cụ bổ trợ trong Spring Data R2DBC. Dùng Criteria khi truy vấn xoay quanh entity và các điều kiện tiêu chuẩn; dùng SQL trực tiếp khi cần diễn đạt join, tổng hợp hoặc tính năng database một cách chính xác. Giữ tham số an toàn, mapping rõ ràng và kiểm thử theo database thực tế sẽ giúp truy vấn động vừa dễ bảo trì vừa đáp ứng yêu cầu vận hành.
