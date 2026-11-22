# Tính di động, bảo mật tham số và kiểm thử theo hệ quản trị đích

## 1. Vì sao native SQL trong Hibernate cần ba lớp bảo đảm?

Hibernate cung cấp HQL/JPQL, Criteria API và SQL gốc (*native SQL*). HQL mô tả truy vấn trên entity model và để Hibernate sinh SQL theo dialect. Native SQL cho phép lập trình viên viết trực tiếp câu SQL sẽ chạy trên hệ quản trị cơ sở dữ liệu (DBMS), từ truy vấn thông thường đến JSON, window function, upsert, CTE và các câu lệnh đặc thù.

Lợi ích của native SQL là quyền kiểm soát cú pháp, kế hoạch tối ưu và những tính năng riêng của database. Đổi lại, ứng dụng phải xử lý rõ ba vấn đề:

1. **Tính di động:** Cú pháp và semantics có chạy đúng khi thay DBMS, phiên bản, schema, driver hoặc cấu hình?
2. **Bảo mật tham số:** Input có luôn được truyền dưới dạng dữ liệu, không bị hiểu thành một phần câu SQL?
3. **Kiểm thử theo DBMS đích:** Kết quả, kiểu dữ liệu, transaction, lock và execution plan đã được xác nhận trên engine thực sự dùng ở production chưa?

Ví dụ:

```sql
SELECT id, order_number, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC;
```

Câu SQL khá đơn giản nhưng vẫn có câu hỏi về tên cột vật lý, kiểu của `status`, cách bind tham số, quyền truy cập tenant, timezone của `created_at` và thứ tự khi hai hàng cùng timestamp.

**Native SQL chạy thành công trên máy lập trình viên chưa đủ để kết luận đúng và an toàn ở production.**

## 2. Ranh giới giữa HQL và native SQL

HQL:

```hql
select o
from Order o
where o.status = :status
```

Native SQL:

```sql
SELECT o.id, o.order_number, o.status
FROM orders o
WHERE o.status = :status;
```

Ở HQL, `Order` và `o.status` là tên entity/property Java. Ở native SQL, `orders` và `o.status` phải là tên bảng/cột vật lý. Hibernate vẫn tham gia transaction, JDBC, parameter binding và result mapping nhưng không tự dịch tất cả cú pháp native SQL của PostgreSQL sang MySQL hay Oracle.

```text
Java service / repository
          |
          +-- HQL / Criteria
          |       |
          |       v
          |  Hibernate translation + Dialect
          |       |
          +-- Native SQL -----------------+
                                         |
                                         v
                               JDBC driver / connection
                                         |
                                         v
                             PostgreSQL, MySQL, Oracle ...
```

Các query thiên về entity lifecycle, association, filter và portability thường phù hợp với HQL. Native SQL phù hợp khi cần đặc tính SQL riêng, truy vấn phân tích hay tối ưu quan trọng mà HQL không biểu đạt thuận tiện.

## 3. Tính di động không chỉ là cú pháp

Một query có thể parse thành công trên hai DBMS nhưng cho kết quả khác:

| Tầng | Câu hỏi về portability | Tình huống |
|---|---|---|
| Cú pháp | DBMS có hiểu toán tử/hàm? | `LIMIT`, `RETURNING`, JSON operators |
| Kiểu SQL | Java/JDBC type có tương thích? | UUID, JSON, Boolean, Decimal |
| Semantics | So sánh và kết quả có giống? | NULL, collation, timezone |
| DDL/schema | Tên bảng, khóa và index có tồn tại? | sequence, identity, generated column |
| Transaction | Isolation/locks giống nhau? | gap lock, serialization failure |
| JDBC driver | Binding/reading result giống nhau? | timestamp, arrays |
| ORM mapping | Result columns có đủ để hydrate entity? | discriminator, composite ID |
| Vận hành | Query có hiệu quả trên dữ liệu thật? | index statistics, query plan |

Vì vậy, định nghĩa “hỗ trợ PostgreSQL 16” cụ thể hơn “hỗ trợ SQL”. Nếu sản phẩm hỗ trợ nhiều hệ quản trị, cần khai báo ma trận DBMS/major version, không khẳng định portable chỉ vì query dùng những từ khóa quen thuộc.

## 4. Hibernate Dialect làm gì, và không làm gì?

Hibernate `Dialect` cung cấp hiểu biết về khả năng DBMS khi Hibernate **sinh SQL** từ HQL, Criteria, entity persisting và các thao tác ORM khác. Nhưng với native SQL, người viết tự quyết định phần lớn câu SQL.

Ví dụ native PostgreSQL:

```sql
SELECT id, payload ->> 'customerId' AS customer_id
FROM event_log
WHERE payload @> CAST(:filter AS jsonb);
```

Chỉ đổi cấu hình Dialect sang MySQL sẽ không khiến Hibernate tự biến toán tử JSONB `->>` hoặc `@>` thành biểu thức MySQL tương đương.

Khi chuyển DBMS:

- Query HQL có thể được dịch sang SQL thích hợp nhờ Dialect.
- Native SQL vendor-specific cần được thay hoặc viết phiên bản riêng.
- Vẫn phải kiểm chứng semantics, vì SQL cùng cú pháp chưa chắc có cùng kết quả và performance.

Không phải lúc nào dùng vendor-specific SQL cũng sai. Điều quan trọng là cô lập phụ thuộc đó trong repository/adapter và có test cho từng DBMS được hỗ trợ.

## 5. So sánh các cấu trúc SQL thường gặp

| Nhu cầu | PostgreSQL thường gặp | MySQL thường gặp | Điểm cần kiểm tra |
|---|---|---|---|
| Phân trang | `LIMIT ... OFFSET ...` | `LIMIT ... OFFSET ...` | DBMS khác có cú pháp khác |
| Upsert | `ON CONFLICT ... DO UPDATE` | `ON DUPLICATE KEY UPDATE` | Chọn conflict key và affected count |
| Trả bản ghi sau DML | `RETURNING` | Không cùng mức hỗ trợ/syntax | Chọn API nhận result set |
| JSON | `jsonb` và toán tử riêng | Hàm JSON và kiểu trả về riêng | Index, cast và null handling |
| Khóa | `FOR UPDATE` | `FOR UPDATE` | Gap/row locks và isolation |
| ID tự sinh | identity/sequence | auto-increment | Generator và returned keys |
| Date arithmetic | Interval/operator riêng | Date functions riêng | Timezone và precision |

Đây là những ví dụ định hướng; hỗ trợ cụ thể còn phụ thuộc phiên bản. Oracle và SQL Server có cách phân trang, casting, upsert và locking riêng. Đừng ghép một query “SQL chung” mà bỏ qua DBMS đích.

## 6. Ưu tiên SQL chuẩn, nhưng chấp nhận vendor-specific có chủ đích

Một query đơn giản:

```sql
SELECT id, order_number
FROM orders
WHERE status = :status
ORDER BY created_at DESC, id DESC;
```

có thể dễ bảo trì hơn một query dùng tính năng độc quyền mà không cần thiết.

Ngược lại, nếu hệ thống dùng PostgreSQL JSONB index cho dữ liệu lớn, dùng native JSONB có thể là quyết định đúng. Khi đó:

1. Ghi rõ chỉ hỗ trợ PostgreSQL/version được kiểm thử.
2. Đặt SQL vendor-specific trong một repository/adapter.
3. Có migration tạo index/extension cần thiết.
4. Có integration test dùng PostgreSQL thật.
5. Có benchmark/execution plan nếu performance là lý do chọn native SQL.

Không nên hy sinh tính đúng đắn và hiệu năng chỉ để đạt portability giả định tới database chưa bao giờ có trong phạm vi sản phẩm.

## 7. Physical naming, reserved words và schema

Native SQL dùng tên bảng và cột thực tế. Entity Java:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "order_number")
    private String orderNumber;
}
```

tương ứng native SQL:

```sql
SELECT id, order_number
FROM purchase_orders
WHERE id = :id;
```

Không viết `FROM PurchaseOrder` hoặc `SELECT orderNumber` như HQL nếu bảng/cột vật lý không có những tên ấy.

Các nguồn lỗi portability gồm:

- Identifier trùng reserved keyword như `order`.
- Naming strategy đổi camelCase thành snake_case.
- Schema mặc định khác giữa các môi trường.
- Case sensitivity/quoted identifier khác theo DBMS.
- Tenant dùng schema riêng hoặc prefix tên bảng.

Quoting identifier cũng có cú pháp khác giữa các DBMS. Nếu muốn dễ chuyển database, ưu tiên tên vật lý thường, rõ ràng, ít va keyword. Khi schema có quote, tạo và tham chiếu đúng tên/case theo DBMS đích.

**Parameter không thay thế được tên bảng, tên cột hoặc schema.** Chỉ chọn identifier động qua whitelist do ứng dụng định nghĩa.

## 8. Java type, SQL type và JDBC type

SQL cùng cấu trúc:

```sql
SELECT id, total_amount, active, created_at
FROM invoices
WHERE id = :id;
```

có thể khác ở cách driver trả về các cột:

- `DECIMAL/NUMERIC` thường nên ánh xạ `BigDecimal`, không dùng `double` cho tiền.
- `BOOLEAN` có thể là kiểu Boolean thật hoặc số ở DBMS/schema khác.
- `UUID` có thể là kiểu native, chuỗi hoặc binary.
- `TIMESTAMP` có thể có hoặc không có timezone.
- `BIGINT` có thể xuất hiện dưới các numeric class khác trong scalar result tùy driver.

HQL biết mapping property. Với native scalar query, Hibernate có thể dựa vào JDBC metadata để suy luận kiểu. Đừng ép kiểu kết quả khi chưa biết contract.

### 8.1. Decimal

```sql
CREATE TABLE invoices (
    id BIGINT PRIMARY KEY,
    total_amount DECIMAL(19, 2) NOT NULL
);
```

Đọc tiền bằng `BigDecimal`, kiểm chứng scale/rounding khi write và aggregate. Với:

```sql
SELECT SUM(total_amount)
FROM invoices
WHERE customer_id = :customerId;
```

aggregate có thể trả NULL khi không có giá trị. Driver và database có thể thay đổi precision/type của aggregate.

### 8.2. UUID

```java
query.setParameter("id", documentId);
```

Nếu `documentId` là UUID, binding JDBC phụ thuộc kiểu cột và provider. Với PostgreSQL native UUID, có thể cần kiểu/cast phù hợp; với MySQL lưu binary hoặc varchar, cách bind khác. Phải kiểm thử cả DDL lẫn Java type conversion.

## 9. Timestamp, timezone và ranh giới thời gian

Phân biệt:

| Java type | Ý nghĩa chính |
|---|---|
| `LocalDate` | Ngày không có thời gian |
| `LocalDateTime` | Ngày giờ địa phương, không có offset |
| `Instant` | Mốc trên timeline UTC |
| `OffsetDateTime` | Ngày giờ đi kèm offset |

Ví dụ tìm dữ liệu trong tháng:

```sql
SELECT id
FROM orders
WHERE created_at >= :fromTime
  AND created_at < :toTime;
```

Java:

```java
Instant from = Instant.parse("2026-11-01T00:00:00Z");
Instant to = Instant.parse("2026-12-01T00:00:00Z");

var query = entityManager.createNativeQuery("""
    SELECT id FROM orders
    WHERE created_at >= :fromTime
      AND created_at < :toTime
    """);
query.setParameter("fromTime", from);
query.setParameter("toTime", to);
```

Đây là named native parameters của Hibernate; nếu dự án yêu cầu JPA portable, cần tuân thủ kiểu positional parameters/provider. Dùng khoảng nửa mở `[from,to)` để tránh tính toán “23:59:59.999” sai khi DB có precision khác.

Kiểm thử timezone của JDBC connection, JVM, server DB, kiểu cột và daylight-saving transitions nếu ứng dụng hỗ trợ nhiều múi giờ. Không giả định `TIMESTAMP WITHOUT TIME ZONE` tự chứa thông tin UTC.

## 10. Unicode, collation và sắp xếp NULL

Native query:

```sql
SELECT id, full_name
FROM customers
WHERE full_name = :name
ORDER BY full_name;
```

được DBMS so sánh theo collation. Hai hệ quản trị hoặc hai database cấu hình khác nhau có thể:

- Phân biệt hoặc không phân biệt chữ hoa.
- Phân biệt dấu tiếng Việt khác nhau.
- Xếp thứ tự ký tự Unicode khác nhau.
- Xử lý normalization và ký tự đặc biệt khác nhau.

Nếu API cần phân trang ổn định, thêm ID làm tie-breaker:

```sql
ORDER BY full_name ASC, id ASC
```

NULL sorting cũng có default khác nhau. Một số DBMS hỗ trợ `NULLS LAST`; nếu cần biểu thức dễ port hơn:

```sql
ORDER BY
    CASE WHEN completed_at IS NULL THEN 1 ELSE 0 END,
    completed_at DESC,
    id DESC;
```

CASE làm semantics rõ ràng, nhưng có thể ảnh hưởng index usage. Cần kiểm thử SQL và execution plan trên DB đích.

## 11. Pagination: syntax và consistency

Một số DBMS dùng:

```sql
SELECT id, created_at
FROM orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
```

Nhưng không phải mọi DBMS đều chấp nhận cùng cú pháp LIMIT/OFFSET. Có thể để Hibernate/JPA áp dụng `setFirstResult()`/`setMaxResults()` cho native select khi provider hỗ trợ, hoặc dùng SQL biến thể theo DBMS.

Ngoài syntax, offset pagination khi dữ liệu thay đổi có thể tạo duplicate/missing rows giữa các trang. Với dữ liệu lớn, keyset pagination phù hợp nếu có sort key ổn định:

```sql
SELECT id, created_at
FROM orders
WHERE status = :status
  AND (
      created_at < :cursorTime
      OR (created_at = :cursorTime AND id < :cursorId)
  )
ORDER BY created_at DESC, id DESC;
```

Ứng dụng cần giới hạn page size, validate cursor và kiểm thử với các hàng có timestamp trùng nhau.

## 12. Tính năng vendor: JSON, upsert, RETURNING

### 12.1. PostgreSQL upsert

```sql
INSERT INTO daily_metrics (metric_date, metric_key, metric_value)
VALUES (:metricDate, :metricKey, :metricValue)
ON CONFLICT (metric_date, metric_key)
DO UPDATE SET metric_value = EXCLUDED.metric_value;
```

MySQL có cú pháp upsert khác; semantics của constraint và affected count cũng có thể khác. Hibernate không tự dịch native `ON CONFLICT`.

### 12.2. RETURNING

```sql
INSERT INTO orders (order_number, total_amount)
VALUES (:number, :total)
RETURNING id;
```

Đây là pattern PostgreSQL. Khả năng RETURNING và cách truy xuất result set từ DML phụ thuộc DBMS và API Hibernate/JDBC. Không dùng `executeUpdate()` để lấy trực tiếp một result set trả về mà chưa xác định contract API.

### 12.3. JSONB

```sql
SELECT id
FROM event_log
WHERE payload @> CAST(:filterJson AS jsonb);
```

Giá trị filterJson vẫn phải bind như parameter và kiểu JSONB cần phù hợp. Một số driver/Hibernate mapping cần kiểu JDBC riêng; string binding có thể không tự chuyển thành JSONB. Kiểm thử câu SQL và type trên PostgreSQL thực.

### 12.4. CTE, window function và recursion

Nhiều DBMS hỗ trợ window functions và CTE, nhưng khác về SQL grammar, materialization, recursive depth và semantics với null/collation. Cần test kết quả lẫn execution plan; portable ở mức keyword không đồng nghĩa portable về performance.

## 13. SQL injection: nguyên nhân là ghép dữ liệu thành cú pháp

Đoạn code không an toàn:

```java
String sql = "SELECT id FROM orders WHERE order_number = '"
        + orderNumber + "'";

List<?> rows = entityManager
        .createNativeQuery(sql)
        .getResultList();
```

Khi input chứa dấu nháy và từ khóa SQL, nó có thể phá cấu trúc điều kiện. Một chuỗi như:

```text
' OR '1'='1
```

có thể làm truy vấn bị hiểu thành điều kiện khác nếu được nối trực tiếp. Không sửa bằng việc tự thay vài dấu nháy. Giải pháp nền tảng là prepared/bound parameters.

## 14. Bind parameter đúng trong Hibernate/JPA

Hibernate native query hỗ trợ named parameters:

```java
String sql = """
    SELECT id
    FROM orders
    WHERE order_number = :orderNumber
    """;

List<?> rows = entityManager
    .createNativeQuery(sql)
    .setParameter("orderNumber", orderNumber)
    .getResultList();
```

Parameter được truyền như dữ liệu cho JDBC/DBMS, không ghép trực tiếp vào câu SQL. Các ký tự giống SQL trong input vẫn là giá trị của phép so sánh.

**Portability JPA:** Jakarta Persistence không bảo đảm named parameters cho mọi native query/provider; Hibernate hỗ trợ nhưng nếu cần portable nên dùng positional parameters đúng API.

```java
List<?> rows = entityManager.createNativeQuery("""
    SELECT id FROM orders
    WHERE order_number = ?1
    """)
    .setParameter(1, orderNumber)
    .getResultList();
```

Phải dùng đúng cách đánh số placeholder mà phiên bản JPA/Hibernate hỗ trợ. Với JDBC trực tiếp, PreparedStatement thường dùng placeholder `?` không đánh số trong SQL và setter đánh số từ 1.

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id FROM orders WHERE order_number = ?")) {
    ps.setString(1, orderNumber);
    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả.
    }
}
```

Hệ quả quan trọng: input có quote, dấu gạch chéo, từ khóa hay Unicode vẫn được truyền dưới dạng giá trị. Binding không có nghĩa không cần validate nghiệp vụ, nhưng nó tách rạch ròi **SQL structure** và **data value**.

## 15. Parameter bảo vệ giá trị, không bảo vệ identifier động

Không thể bind tên bảng/cột, hướng sort hoặc một đoạn WHERE tự do như một giá trị.

Ví dụ sai:

```java
String sql = "SELECT id FROM orders ORDER BY " + sortBy;
```

Đưa `sortBy` vào `ORDER BY :sortBy` cũng không giải quyết việc chọn cột: parameter là một giá trị, không phải identifier SQL.

Giải pháp là whitelist các fragment cố định:

```java
private static final Map<String, String> SORT_COLUMNS = Map.of(
        "createdAt", "o.created_at",
        "total", "o.total_amount",
        "id", "o.id");

static String orderBy(String userKey, boolean descending) {
    String column = SORT_COLUMNS.get(userKey);
    if (column == null) {
        throw new IllegalArgumentException("Unsupported sort key");
    }
    return column + (descending ? " DESC" : " ASC");
}
```

Ở đây giá trị người dùng chỉ chọn một trong các fragment đã được lập trình viên định nghĩa. Không nhận raw SQL từ request. Khi cần ổn định thứ tự, thêm khóa ID phù hợp (và tránh duplicate ORDER BY nếu ID đã là khóa chính).

Tương tự, nếu một API cho phép chọn tên bảng report hoặc schema, mapping phải nằm ở phía server, qua whitelist/config đã xác thực. Không nối tenant schema trực tiếp từ request body.

## 16. LIKE: injection và wildcard là hai vấn đề khác nhau

Bind parameter không tự escape ý nghĩa của `%` và `_` trong `LIKE`.

```sql
SELECT id, customer_name
FROM customers
WHERE customer_name LIKE :pattern;
```

Nếu `pattern = "%"`, query có thể match rất nhiều rows. Đây là semantics wildcard, không phải SQL injection.

Nếu muốn tìm nguyên văn chuỗi chứa keyword:

```java
static String escapeLike(String input) {
    return input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}

String pattern = "%" + escapeLike(keyword) + "%";

List<?> rows = entityManager.createNativeQuery("""
    SELECT id, customer_name
    FROM customers
    WHERE customer_name LIKE :pattern ESCAPE '!'
    """)
    .setParameter("pattern", pattern)
    .getResultList();
```

Escape character `!` được chọn rõ ràng; phải escape chính nó trước khi escape wildcard. Kiểm thử `ESCAPE` và collation trên DBMS đích. Nếu sản phẩm chủ ý cho người dùng nhập wildcard, đó là contract khác; cần giới hạn độ dài pattern và xem execution plan vì leading wildcard có thể làm index kém hiệu quả.

## 17. IN, danh sách parameters và tập rỗng

Query có tập ID:

```sql
SELECT id, order_number
FROM orders
WHERE id IN (:ids);
```

Không nối raw list:

```java
String sql = "SELECT id FROM orders WHERE id IN (" + rawIds + ")";
```

Với Hibernate NativeQuery, có thể dùng API bind collection:

```java
import org.hibernate.query.NativeQuery;

NativeQuery<?> query = entityManager.createNativeQuery("""
    SELECT id, order_number
    FROM orders
    WHERE id IN (:ids)
    """).unwrap(NativeQuery.class);

query.setParameterList("ids", List.of(10L, 20L, 30L));
List<?> rows = query.getResultList();
```

Đây là khả năng của Hibernate, không phải cú pháp list binding portable của mọi JPA provider/JDBC driver. Cách khác là tạo số placeholder phù hợp từ **số phần tử đã được kiểm soát** và bind từng giá trị, chứ không ghép chúng thành SQL raw.

### 17.1. Danh sách rỗng

```sql
WHERE id IN ()
```

không portable và có thể lỗi syntax. Nếu nghiệp vụ hiểu “IN tập rỗng” là không có kết quả, trả `List.of()` trước khi query:

```java
if (ids.isEmpty()) {
    return List.of();
}
```

Với NOT IN, tập rỗng có nghĩa khác và cần xử lý riêng.

### 17.2. NULL trong NOT IN

Nếu danh sách hoặc subquery bên phải chứa NULL, `NOT IN` có thể trả UNKNOWN thay vì TRUE. Trong các anti-join query, `NOT EXISTS` thường dễ suy luận hơn. Lọc NULL nếu đó là semantics đúng.

### 17.3. Danh sách quá dài

DBMS/driver có giới hạn bind count và SQL length. Danh sách nhiều nghìn ID có thể nên chuyển thành staging table, chunk, database array hoặc table-valued parameter (tùy DBMS); không kỳ vọng một danh sách lớn luôn được hỗ trợ với hiệu năng tốt.

## 18. Multi-tenancy: bind đúng vẫn có thể lộ dữ liệu

Query:

```sql
SELECT id, total_amount
FROM invoices
WHERE id = :invoiceId;
```

có thể chống SQL injection nhưng vẫn để lộ invoice của tenant khác nếu quyền truy cập chỉ dựa vào ID do client cung cấp.

Thay vào đó:

```sql
SELECT id, total_amount
FROM invoices
WHERE tenant_id = :tenantId
  AND id = :invoiceId;
```

Tenant ID phải được lấy từ authentication/security context đáng tin cậy, không tin ngay request body. Nếu dùng database Row-Level Security (RLS), test cả cách set/reset session context khi connection được trả về pool.

Nếu mỗi tenant có schema riêng, không bind schema name như giá trị; dùng mapping tenant-to-schema do server kiểm soát và cơ chế multi-tenancy của Hibernate/connection provider được cấu hình đúng.

Ngoài bind parameter:

- Áp dụng least privilege cho DB user.
- Không cấp quyền DDL rộng cho connection chỉ dùng read/report.
- Chọn các cột cần thiết, tránh trả thông tin nhạy cảm không cần dùng.
- Kiểm tra authorization cả lúc SELECT, UPDATE và DELETE.
- Audit những mutation quan trọng.

## 19. Result mapping của native query cũng cần portability

JPA có:

```java
List<?> ids = entityManager.createNativeQuery("""
    SELECT id FROM orders WHERE status = :status
    """)
    .setParameter("status", status)
    .getResultList();
```

Với scalar query, kiểu Java có thể phụ thuộc metadata của driver. Không tự giả định `id` luôn là `Long`; đôi khi cần đọc qua `Number` hoặc mapping explicit.

### 19.1. Mapping entity

```java
List<Order> orders = entityManager.createNativeQuery("""
    SELECT o.*
    FROM orders o
    WHERE o.status = :status
    """, Order.class)
    .setParameter("status", status)
    .getResultList();
```

Result set phải chứa các cột mà Hibernate cần để hydrate entity: ID, các mapped attributes bắt buộc, discriminator và các cột liên quan nếu mapping phức tạp. Một native query chỉ SELECT hai scalar fields không mặc nhiên map được thành entity đầy đủ.

### 19.2. DTO bằng SqlResultSetMapping

JPA hỗ trợ `@SqlResultSetMapping` và `@ConstructorResult`:

```java
public record OrderBrief(Long id, String orderNumber) {}

@SqlResultSetMapping(
    name = "OrderBriefMapping",
    classes = @ConstructorResult(
        targetClass = OrderBrief.class,
        columns = {
            @ColumnResult(name = "id", type = Long.class),
            @ColumnResult(name = "order_number", type = String.class)
        }
    )
)
@Entity
public class Order {
    @Id
    private Long id;
    // Các thuộc tính khác...
}
```

```java
List<?> rows = entityManager.createNativeQuery("""
    SELECT o.id AS id,
           o.order_number AS order_number
    FROM orders o
    WHERE o.status = :status
    """, "OrderBriefMapping")
    .setParameter("status", status)
    .getResultList();
```

Mapping phải được đăng ký đúng, aliases khớp với result set, constructor types tương thích với JDBC conversion. Nếu driver trả timestamp hay numeric type khác kỳ vọng, mapping cần được điều chỉnh có chủ đích.

### 19.3. Object[] không phải type-safe

```java
for (Object value : rows) {
    Object[] columns = (Object[]) value;
    Long id = ((Number) columns[0]).longValue();
    String orderNumber = (String) columns[1];
}
```

Đoạn code chỉ phù hợp với result shape đã kiểm chứng. Query một cột có thể trả scalar thay vì Object[], và kiểu dữ liệu có thể khác khi đổi DBMS/driver. Ưu tiên DTO/mapping explicit cho query quan trọng.

## 20. Native mutation và persistence context stale

Native UPDATE/DELETE chạy trực tiếp trên database:

```java
Order order = entityManager.find(Order.class, orderId);

entityManager.createNativeQuery("""
    UPDATE orders
    SET status = :newStatus
    WHERE id = :id
    """)
    .setParameter("newStatus", "CANCELLED")
    .setParameter("id", orderId)
    .executeUpdate();

// order.getStatus() có thể vẫn là giá trị trước update.
```

Hibernate không tự đồng bộ field của mọi managed instance sau native SQL. Một mẫu xử lý:

```java
entityManager.flush();

int changed = entityManager.createNativeQuery("""
    UPDATE orders SET status = :status
    WHERE id = :id
    """)
    .setParameter("status", "CANCELLED")
    .setParameter("id", orderId)
    .executeUpdate();

entityManager.refresh(order);
```

- Flush trước nếu có pending changes cần ghi.
- Refresh các managed entity cụ thể còn dùng tiếp.
- Clear persistence context nếu mutation ảnh hưởng rất nhiều entity và tiếp tục làm việc với state mới.
- Clear/refresh có thể loại bỏ thay đổi chưa flush, nên cần thiết kế transaction boundary rõ.

Native SQL cũng có thể ảnh hưởng second-level/query cache. Hibernate NativeQuery có API synchronized query spaces:

```java
import org.hibernate.query.NativeQuery;

NativeQuery<?> query = entityManager.createNativeQuery("""
    UPDATE orders SET status = :status
    WHERE id = :id
    """).unwrap(NativeQuery.class);

query.addSynchronizedEntityClass(Order.class);
query.setParameter("status", "CANCELLED");
query.setParameter("id", orderId);
int affected = query.executeUpdate();
```

Thông tin query spaces giúp Hibernate quản lý synchronization/cache theo mapping. Nó **không** tự cập nhật managed entity đang stale trong first-level cache. Kiểm thử behavior theo Hibernate version/cache provider.

## 21. Native SQL và lifecycle/cascade

Một câu native UPDATE hoặc DELETE không tương đương tải entity rồi gọi domain method, `EntityManager.remove()` hoặc dirty checking.

| Cơ chế | Thao tác entity managed | Native bulk SQL |
|---|---|---|
| Java entity callback | Có theo lifecycle | Không chạy per entity |
| JPA cascade / orphan removal | Theo mapping | Không tự chạy như object graph |
| Bean Validation lifecycle | Theo cấu hình | Không per entity |
| Database FK/CHECK/trigger | Có | Có |
| Persistence context state | ORM theo dõi | Có thể stale |
| Transaction/isolation | Có | Có |
| DB permission/RLS | Có | Có |

Nếu cần phát domain event cho từng Order hoặc xóa graph theo cascade mapping, native mutation có thể chưa đủ. Cân nhắc managed entity workflow hoặc database audit/outbox được thiết kế riêng.

Với bulk DELETE, constraint FK có thể chặn xóa parent. Database ON DELETE CASCADE có thể xóa child rows nhưng không gọi JPA callbacks từng child. Đây là khác biệt quan trọng giữa database cascade và ORM cascade.

## 22. Transaction và locking phụ thuộc DBMS

Ví dụ:

```sql
SELECT id, available
FROM inventory_items
WHERE id = :id
FOR UPDATE;
```

Một số DBMS đều hiểu FOR UPDATE, nhưng lock scope, thời gian chờ, gap locks, deadlocks và isolation behavior khác nhau. Không suy luận từ việc query chạy trên H2 rằng concurrency đúng trên PostgreSQL hoặc MySQL/InnoDB.

Một conditional UPDATE thường hữu ích:

```sql
UPDATE inventory_items
SET available = available - :quantity
WHERE id = :id
  AND available >= :quantity;
```

Điều kiện và phép cập nhật nằm trong cùng statement. Ứng dụng vẫn phải validate quantity dương, kiểm tra affected count, dùng version nếu cần và bảo đảm transaction/constraint phù hợp.

Nếu invariant liên quan nhiều row hoặc predicate, một row lock đơn lẻ không tự bảo vệ mọi phantom insert. Có thể cần unique constraint, parent-lock protocol, isolation SERIALIZABLE hoặc cơ chế predicate/range locking đặc thù DBMS.

## 23. Không log bind parameters nhạy cảm

Khi debug native query, SQL logging và bind parameter logging rất hữu ích. Nhưng tham số có thể chứa:

- Email, số điện thoại, thông tin thanh toán.
- Token, session identifiers, thông tin riêng tư.
- Tenant/user identifiers hoặc dữ liệu kinh doanh nhạy cảm.

Nên bật logging chi tiết trong môi trường test dùng dữ liệu giả. Trong production, dùng masking và correlation ID; không ghi raw secrets hoặc JDBC URL chứa credentials. SQL injection protection không tự giải quyết rủi ro lộ dữ liệu qua logs.

## 24. Vì sao H2 không thay thế integration test DBMS đích?

H2 hoặc SQLite hữu ích để kiểm thử logic Java và một số trường hợp đơn giản, nhưng chúng không chứng minh SQL native vendor-specific chạy đúng trên PostgreSQL/MySQL/Oracle. Khác biệt bao gồm:

- DDL, schema, indexes và constraints.
- UUID/JSON/Boolean/timestamp types.
- Collation, NULL sorting, Unicode.
- Row/gap/predicate locking.
- Sequence/identity.
- Upsert, RETURNING, CTE, JSON functions.
- JDBC driver và query planner.

Một bài test pass trên H2 compatibility mode có thể vẫn lỗi trên production. **DBMS đích** nên là engine và major version thực tế được hỗ trợ. Nếu hệ thống chạy PostgreSQL 16, integration tests trọng yếu phải dùng PostgreSQL 16, không chỉ “SQL-compatible in-memory database”.

## 25. Phân tầng kiểm thử native SQL

| Lớp test | Mục tiêu | Cần DB đích? |
|---|---|---|
| Unit test | Whitelist, validation, logic chọn query variant | Không nhất thiết |
| Repository integration | SQL parse, parameter binding, result mapping | Có |
| Migration integration | DDL/index/constraints đúng | Có |
| Transaction/concurrency | Lock wait, rollback, deadlock, isolation | Có, nhiều connection |
| Performance smoke | Plan, index, dữ liệu đại diện | Có |
| API/end-to-end | Tenant, auth, pagination, retry | Nên gần production |

Đừng chỉ assert “không ném exception”. Cần assert dữ liệu trả về, kiểu được map, state database sau mutation và behavior khi đầu vào bất thường.

## 26. Chạy PostgreSQL thật trong Testcontainers

Ví dụ JUnit 5 + Spring Boot + Testcontainers:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class NativeOrderRepositoryIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("app_test")
            .withPassword("app_test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    NativeOrderRepository repository;

    @Test
    void findByNumberUsesBoundParameter() {
        // Migration + fixture chuẩn bị trước khi test.
        // Thực thi repository query và assert kết quả.
    }
}
```

Đây là khung minh họa, giả định dự án có JUnit 5, Spring Boot Test, các dependency Testcontainers PostgreSQL/JUnit Jupiter và Docker/container runtime. Các test thật phải tạo fixture và assert kết quả; method trống không chứng minh chức năng.

Không dùng image tag `latest` thiếu kiểm soát; pin DBMS major version production. Nếu dự án dùng Hibernate thuần, lấy JDBC URL từ container để tạo SessionFactory thay vì Spring Boot. Mục tiêu là cùng **database engine**, không phải một framework test cụ thể.

### 26.1. Dùng migration production trong test

```text
Start DB container
        |
        v
Run Flyway/Liquibase migrations
        |
        v
Validate Hibernate mappings
        |
        v
Load fixture rows
        |
        v
Execute native query through repository
        |
        v
Assert result + DB state + constraints
```

Nếu production schema được quản lý bằng migration, test không nên chỉ để Hibernate tự `ddl-auto=create` rồi tin rằng đang kiểm thử schema production. Dùng migration thật để bắt lỗi đổi tên cột, index thiếu hoặc constraint sai.

## 27. Một repository native SQL an toàn

Giả sử ứng dụng cần lấy các Order gần đây theo tenant và status:

```java
@Repository
public class NativeOrderRepository {

    @PersistenceContext
    private EntityManager em;

    public List<OrderBrief> findRecent(
            long tenantId,
            String status,
            int limit) {

        if (limit < 1 || limit > 200) {
            throw new IllegalArgumentException("Invalid limit");
        }

        List<?> raw = em.createNativeQuery("""
            SELECT o.id, o.order_number
            FROM orders o
            WHERE o.tenant_id = :tenantId
              AND o.status = :status
            ORDER BY o.created_at DESC, o.id DESC
            """)
            .setParameter("tenantId", tenantId)
            .setParameter("status", status)
            .setMaxResults(limit)
            .getResultList();

        return raw.stream()
            .map(value -> {
                Object[] row = (Object[]) value;
                return new OrderBrief(
                    ((Number) row[0]).longValue(),
                    (String) row[1]);
            })
            .toList();
    }
}

public record OrderBrief(long id, String orderNumber) {}
```

Ví dụ giả định Java 17+, Hibernate là JPA provider và schema có những cột nêu trên. Những điều được kiểm soát:

- tenantId phải lấy từ context đáng tin, không tùy tiện từ client.
- status được bind.
- limit được validate và áp dụng qua API.
- ORDER BY có tie-breaker.
- Không trả entity graph/proxy ra API.
- Kiểu cột và result shape vẫn phải được xác nhận bằng integration test.

Nếu yêu cầu ánh xạ phức tạp, dùng `@SqlResultSetMapping` hoặc mapper DTO có type conversion rõ thay vì ép kiểu thủ công nhiều nơi.

## 28. Kiểm thử các edge case bắt buộc

Một suite tốt nên kiểm tra:

| Trường hợp | Điều cần chứng minh |
|---|---|
| Chuỗi có dấu nháy đơn | Query không bị phá syntax |
| Input chứa SQL-looking text | Vẫn là data, không thay đổi predicate |
| Wildcards % và _ trong LIKE | Được escape đúng khi tìm literal |
| Unicode tiếng Việt | Encoding/collation đúng |
| IN list rỗng | Không sinh SQL lỗi |
| NOT IN có NULL | Semantics theo yêu cầu |
| NULL sort | Thứ tự mong muốn |
| Timestamp ở ranh giới ngày | Không lệch timezone/precision |
| Nhiều rows cùng sort key | Pagination ổn định |
| Cross-tenant ID | Không trả dữ liệu tenant khác |
| Sort key ngoài whitelist | Từ chối |
| Unique/FK violation | Transaction rollback và lỗi được map |
| Kết quả JDBC kiểu khác | Mapping không ClassCastException bất ngờ |

Ví dụ test injection-safe equality:

```java
@Test
void sqlLookingOrderNumberIsOnlyData() {
    String unusualNumber = "' OR '1'='1";

    // Tạo fixture Order có đúng order_number unusualNumber,
    // đồng thời tạo các Order khác không phù hợp.
    List<OrderBrief> result =
        repository.findByNumber(tenantId, unusualNumber);

    assertThat(result)
        .extracting(OrderBrief::orderNumber)
        .containsExactly(unusualNumber);
}
```

Đây là test minh họa; giả định repository có method `findByNumber` và fixture được chuẩn bị. Assert cần chứng minh input bất thường không làm query trả thêm hàng ngoài điều kiện.

## 29. Kiểm thử transaction và concurrency

Để test locking, phải tạo ít nhất hai transaction/connection độc lập:

```text
Initial: inventory.available = 1

Transaction A                 Transaction B
-------------                 -------------
BEGIN                         BEGIN
UPDATE available = available-1
WHERE available >= 1
                              UPDATE available = available-1
                              WHERE available >= 1
COMMIT                        chờ/đánh giá lại điều kiện
                              affected rows = 0
                              COMMIT/ROLLBACK

Expected: inventory.available = 0
          không bao giờ âm
```

Test cần phối hợp hai thread/transaction có kiểm soát và assert kết quả database. Các kịch bản nên có:

- Hai transaction cùng cập nhật một row.
- SELECT FOR UPDATE, lock wait và timeout.
- Deadlock khi khóa nhiều row theo thứ tự ngược.
- Serialization failure ở isolation SERIALIZABLE.
- Insert race với unique constraint.
- Phantom row khi query kiểm tra không tồn tại.

Không suy từ behavior của H2 sang PostgreSQL hay MySQL. Test DBMS đích với isolation/index/connection settings tương ứng.

## 30. Kết hợp query tests với migrations

Native SQL phụ thuộc tên bảng/cột vật lý. Nếu migration đổi:

```sql
ALTER TABLE orders
RENAME COLUMN order_number TO external_number;
```

HQL có thể được sửa bằng mapping entity, còn native query cũ chứa `order_number` sẽ lỗi khi chạy. Vì vậy:

1. Chạy migration trên empty database.
2. Chạy các native repository integration tests ngay sau migration.
3. Nếu hỗ trợ nâng cấp từ schema cũ, test upgrade path với dữ liệu hiện hữu.
4. Review index/constraints đi kèm query thay đổi.
5. Kiểm tra quyền DB user thực tế; test bằng superuser có thể che lỗi permission.

Nếu có quy trình rollback migration, cũng cần xác định khả năng rollback dữ liệu và schema.

## 31. Test đúng version và cấu hình của database đích

Một môi trường được mô tả “PostgreSQL” còn thiếu:

- Major version.
- Extension được bật.
- Collation/locale.
- Timezone của server/session.
- JDBC driver và Hibernate version.
- Migration version.
- Isolation/connection pool configuration.

Nếu production đang rolling upgrade từ một major version sang version kế tiếp, test cả hai nếu chúng cùng được hỗ trợ trong giai đoạn chuyển đổi.

Một ma trận:

| Môi trường | DBMS | Mục tiêu |
|---|---|---|
| Local | Container đúng DBMS | Debug nhanh |
| CI integration | Major version production | Kiểm tra SQL/mapping |
| CI compatibility | Các versions được cam kết hỗ trợ | Phát hiện khác biệt |
| Staging | Config, extension, migration gần production | Xác nhận triển khai |
| Production | DBMS thật | Quan sát plan, lock và errors |

Nếu sản phẩm chỉ hỗ trợ một DBMS, hãy nói rõ thay vì cố portable giả tạo. Kiểm thử sâu DBMS thực sự dùng có giá trị hơn một tuyên bố hỗ trợ rộng không được xác nhận.

## 32. Kiểm tra performance với query plan

Testcontainers có 20 hàng có thể chứng minh cú pháp và result mapping, nhưng không chứng minh hiệu năng trên 20 triệu hàng.

Ví dụ:

```sql
SELECT id, order_number
FROM orders
WHERE tenant_id = :tenantId
  AND created_at >= :fromTime
ORDER BY created_at DESC, id DESC;
```

Index đáng cân nhắc:

```sql
CREATE INDEX idx_orders_tenant_created_id
ON orders (tenant_id, created_at DESC, id DESC);
```

Hiệu quả phụ thuộc phân bố dữ liệu, selectivity, statistics và DBMS optimizer. Dùng `EXPLAIN`/execution plan để xem scan, sort, join, estimated/actual rows và index usage. `EXPLAIN ANALYZE` thường **thực thi query**; với mutation có thể sửa dữ liệu, nên chỉ chạy trong môi trường và transaction kiểm soát.

Quan sát thêm lock waits, replication lag, memory và network round trips. Cần tối ưu query **trong bối cảnh use case**, không chỉ nhìn thời gian một lần chạy.

## 33. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Query chạy PostgreSQL nhưng lỗi MySQL | JSONB, cast, upsert hoặc cú pháp khác vendor | Tách DBMS-specific query hoặc dùng HQL |
| Thời gian bị lệch | Timezone/precision/JDBC type khác | Xác định timestamp contract và test ranh giới |
| Tìm kiếm Unicode khác | Collation và normalization khác | Cấu hình/test collation |
| Pagination lặp/mất rows | Không có sort tie-breaker | Thêm ID hoặc key ổn định |
| ClassCastException khi đọc scalar | JDBC result type khác | Result mapping/conversion explicit |
| Native named parameter không portable | Provider khác Hibernate | Dùng positional parameters/adapter |
| SQL injection | Nối raw input thành SQL | Bind mọi giá trị |
| ORDER BY bị injection | Dynamic identifier raw | Whitelist |
| LIKE trả quá nhiều rows | %/_ được hiểu wildcard | Escape theo business contract |
| IN () lỗi SQL | Parameter list rỗng | Xử lý empty list |
| NOT IN trả sai | Có NULL trong tập | NOT EXISTS hoặc lọc NULL |
| Cross-tenant leak | Thiếu tenant/authorization predicate | Server-bound tenant context, RLS |
| Entity vẫn có state cũ | Native DML không đồng bộ persistence context | Flush, refresh/clear |
| FK violation khi DELETE | Còn rows phụ thuộc | Điều chỉnh delete flow/constraint |
| Query cache stale | Thiếu synchronization query spaces | Khai báo query spaces/evict đúng |
| H2 test xanh, production lỗi | DBMS khác nhau | Test trên database đích |
| Query rất chậm trên dữ liệu thật | Index/plan khác | EXPLAIN với dữ liệu đại diện |
| Lộ tham số trong log | Bật bind logging chứa secrets | Mask/tắt ở production |

## 34. Kiến trúc giữ native SQL có thể bảo trì

Nên giới hạn native SQL trong repository hoặc infrastructure adapter:

```text
API / Controller
       |
       v
Application Service
  - business validation
  - tenant + authorization context
  - transaction
       |
       v
Native SQL Repository
  - fixed SQL templates
  - bound parameters
  - whitelist SQL fragments
  - typed result mapping
       |
       v
Hibernate / JDBC / DBMS
```

Nếu phải hỗ trợ nhiều DBMS, tách variant theo database ở một chỗ:

```java
interface OrderSearchSql {
    String selectRecentOrders();
}

final class PostgreSqlOrderSearchSql implements OrderSearchSql {
    @Override
    public String selectRecentOrders() {
        return """
            SELECT id, order_number
            FROM orders
            WHERE tenant_id = :tenantId
            ORDER BY created_at DESC, id DESC
            """;
    }
}
```

Không cần thêm abstraction lớn cho một query đơn giản nếu sản phẩm chỉ hỗ trợ một DBMS. Mục tiêu là làm rõ nơi chứa phụ thuộc DBMS và có test theo contract của nó.

## 35. Quy trình triển khai một native query an toàn

**Bước 1 — Xác định DBMS đích.** Ghi engine, major version, driver, Dialect, timezone, collation và extension.

**Bước 2 — Xác định phần SQL portable và vendor-specific.** Chọn HQL nếu đủ biểu đạt; nếu native-specific, cô lập variant.

**Bước 3 — Kiểm tra schema/mapping.** Tên bảng, cột, constraints, indexes và JDBC types phải khớp migration.

**Bước 4 — Bind giá trị.** Không nối input vào SQL. Chọn placeholder convention đúng Hibernate/JPA/JDBC.

**Bước 5 — Kiểm soát cú pháp động.** Identifier, sort key, direction, schema phải dùng whitelist/config server-side.

**Bước 6 — Xử lý edge cases.** LIKE wildcard, IN rỗng, NOT IN NULL, timezone boundaries, Unicode, pagination order.

**Bước 7 — Bảo vệ authorization.** Tenant ID từ context đáng tin; privilege và RLS nếu có.

**Bước 8 — Định nghĩa mapping và transaction.** Dùng DTO/entity mapping đúng; flush/clear/refresh sau native DML nếu cần.

**Bước 9 — Kiểm thử trên DBMS đích.** Chạy migrations thật, fixture dữ liệu, injection-safe tests, concurrency tests, result types.

**Bước 10 — Đánh giá performance và vận hành.** EXPLAIN, index, metrics, logging an toàn và kiểm soát thay đổi khi nâng phiên bản DBMS.

## 36. Sơ đồ quyết định

```text
               Cần thực hiện truy vấn persistence
                             |
                             v
                    HQL/JPQL đủ phù hợp?
                       /           \
                     CÓ            KHÔNG
                     |               |
                     v               v
                 Ưu tiên HQL      Native SQL
                                     |
                                     v
                         Có vendor-specific syntax?
                              /           \
                            KHÔNG         CÓ
                             |             |
                             v             v
                      SQL standard    DBMS adapter/variant
                             \             /
                              \           /
                               v         v
                         Bound parameters
                         Whitelist identifiers
                         Tenant/authorization
                                   |
                                   v
                         Result mapping, transaction
                         Persistence context/cache
                                   |
                                   v
                         Integration test trên
                         DBMS/version đích
                                   |
                                   v
                         EXPLAIN, rollout, monitoring
```

## 37. Tổng kết

Native SQL trong Hibernate cho phép dùng khả năng riêng của hệ quản trị và kiểm soát chi tiết câu query, nhưng không tự có tính di động của HQL. Cú pháp, kiểu SQL/JDBC, timezone, collation, schema, locks, isolation và optimizer có thể khác giữa các database. Hãy công bố rõ DBMS/version được hỗ trợ, dùng SQL chuẩn khi phù hợp và cô lập tính năng vendor-specific.

An toàn parameter bắt đầu bằng **không ghép input thành cú pháp SQL**. Dùng bind parameter cho giá trị; danh sách IN, LIKE wildcard và dynamic identifier phải được xử lý đúng ngữ nghĩa. Tên cột, bảng, sort direction và schema không thể bind như dữ liệu; dùng whitelist từ server. Đồng thời phải kiểm tra tenant/authorization vì prepared statement không tự ngăn lộ dữ liệu ngoài phạm vi quyền.

Để tin tưởng native query, cần kiểm thử bằng engine/version database đích, chạy schema migration thật và assert những edge case về NULL, Unicode, thời gian, mapping, concurrency và constraint. H2 có thể giúp unit tests nhưng không thay thế integration tests của PostgreSQL/MySQL/Oracle. Với query quan trọng, kiểm tra execution plan và dữ liệu đại diện.

**Một native SQL tốt phải đúng trên database thật, an toàn với mọi input và có giới hạn phụ thuộc DBMS được hiểu rõ.** Khi ba điều kiện ấy được đảm bảo, SQL gốc trở thành công cụ persistence mạnh mẽ mà vẫn bảo trì được lâu dài.
