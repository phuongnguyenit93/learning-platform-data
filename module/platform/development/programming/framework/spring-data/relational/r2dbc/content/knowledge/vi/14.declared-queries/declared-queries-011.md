# Tổ chức SQL phức tạp và kiểm tra khả năng di chuyển giữa hệ quản trị

Trong Spring Data Relational R2DBC, truy vấn khai báo cho phép đặt SQL trực tiếp cạnh repository method. Cách này phù hợp khi truy vấn cần join, CTE, phép tổng hợp, biểu thức điều kiện hoặc tính năng riêng của database mà tên method không diễn đạt rõ. Khi SQL phát triển, vấn đề không chỉ còn là viết đúng câu lệnh. Cần tổ chức truy vấn để người đọc hiểu được, tham số được bind an toàn, kết quả được ánh xạ đúng và mức phụ thuộc vào từng hệ quản trị được kiểm soát.

Khả năng di chuyển giữa các hệ quản trị (database portability) không có nghĩa mọi câu SQL đều giống nhau. PostgreSQL, MySQL, SQL Server và các hệ khác có khác biệt về kiểu dữ liệu, hàm, cú pháp phân trang, upsert, JSON, generated values và cách xử lý một số biểu thức. Spring Data R2DBC có abstraction cho những thao tác mapping phổ biến, nhưng không tự động dịch mọi SQL tùy chỉnh sang dialect khác.

Bài học này trình bày cách tổ chức SQL phức tạp, chọn đúng nơi đặt truy vấn, phân biệt phần SQL có thể dùng chung với phần đặc thù, và xây dựng kiểm thử để phát hiện sớm vấn đề khi đổi database.

## 1. Khi nào nên dùng SQL khai báo?

Derived query method phù hợp với điều kiện tương đối đơn giản, có tên property rõ ràng và ít phép biến đổi. Khi truy vấn cần cấu trúc SQL cụ thể, `@Query` hoặc custom repository fragment thường dễ hiểu hơn.

Các dấu hiệu nên cân nhắc SQL khai báo:

- Cần join nhiều bảng hoặc truy vấn dữ liệu từ nhiều quan hệ.
- Cần CTE, subquery, window function hoặc phép tổng hợp.
- Cần biểu thức SQL đặc thù mà Criteria không biểu diễn thuận tiện.
- Cần kiểm soát chính xác cột trả về, thứ tự join hoặc cách nhóm dữ liệu.
- Cần gọi hàm database, truy vấn JSON hoặc full-text search.
- Cần tối ưu một truy vấn đã được đo bằng query plan và workload thực tế.

Ví dụ, method sau vẫn phù hợp với derived query:

```java
Flux<Order> findByCustomerIdAndStatusOrderByCreatedAtDesc(
        Long customerId,
        OrderStatus status);
```

Nhưng khi cần kết hợp thông tin khách hàng, tổng số dòng hàng và tổng tiền theo từng đơn, một câu SQL có thể mô tả rõ hơn:

```sql
SELECT
    o.id,
    o.status,
    o.created_at,
    c.display_name,
    COUNT(ol.id) AS line_count,
    SUM(ol.quantity * ol.unit_price) AS order_total
FROM orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines ol ON ol.order_id = o.id
WHERE o.customer_id = :customerId
GROUP BY
    o.id,
    o.status,
    o.created_at,
    c.display_name
ORDER BY o.created_at DESC;
```

SQL tường minh làm lộ cấu trúc join và phép tổng hợp. Đổi lại, người viết phải chịu trách nhiệm về cú pháp, mapping, tên cột và khác biệt của hệ quản trị.

## 2. Chọn đúng nơi đặt truy vấn

Có ba lựa chọn thường gặp trong Spring Data R2DBC:

| Cách triển khai | Phù hợp với | Đặc điểm |
| --- | --- | --- |
| Derived query method | Điều kiện cố định, dễ đọc từ tên property. | Spring Data suy ra truy vấn từ tên method. |
| `@Query` trên repository method | SQL khai báo ổn định, gắn trực tiếp với hợp đồng repository. | SQL nằm gần chữ ký method và có thể bind tham số. |
| Custom repository fragment với `DatabaseClient` hoặc `R2dbcEntityTemplate` | SQL động, nhiều nhánh, tái sử dụng hoặc cần điều khiển chi tiết. | Có thể tổ chức truy vấn thành nhiều hàm nhỏ và xây dựng điều kiện theo input. |

Không nên chuyển mọi truy vấn sang SQL tùy chỉnh. Giữ derived query khi nó diễn đạt đúng ý định và không che giấu logic. Dùng `@Query` khi câu SQL đủ ổn định để nằm cạnh method. Dùng fragment khi truy vấn có nhiều bước dựng, cần tái sử dụng hoặc cần phối hợp nhiều câu lệnh.

### @Query cho truy vấn khai báo

Ví dụ repository dùng SQL có join và tổng hợp:

```java
import java.math.BigDecimal;
import java.time.LocalDateTime;

import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import reactor.core.publisher.Flux;

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT
            o.id,
            o.status,
            o.created_at AS created_at,
            c.display_name AS customer_name,
            SUM(ol.quantity * ol.unit_price) AS total
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        LEFT JOIN order_lines ol ON ol.order_id = o.id
        WHERE o.created_at >= :from
          AND o.created_at < :to
        GROUP BY
            o.id,
            o.status,
            o.created_at,
            c.display_name
        ORDER BY o.created_at DESC
        """)
    Flux<OrderSummary> findSummaries(
            @Param("from") LocalDateTime from,
            @Param("to") LocalDateTime to);
}
```

Ví dụ giả định có projection `OrderSummary` phù hợp với các cột được trả về. Kiểu trả về phải phản ánh cấu trúc kết quả; không nên cố ánh xạ một hàng tổng hợp vào entity `Order` nếu các cột không đại diện cho một entity hoàn chỉnh.

`@Query` giữ câu SQL gần với hợp đồng truy vấn. Nó không khiến SQL tự trở nên portable. Nếu câu lệnh chứa hàm hoặc cú pháp riêng của PostgreSQL, method đó vẫn phụ thuộc PostgreSQL dù được khai báo trong một repository Spring Data.

### Custom fragment cho truy vấn cần tổ chức riêng

Khi truy vấn có nhiều bộ lọc tùy chọn, có thể đặt nó trong một fragment:

```java
public interface OrderSearch {
    Flux<OrderSummary> search(OrderSearchCriteria criteria);
}
```

Repository chính kết hợp fragment:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long>, OrderSearch {
}
```

Implementation dùng `DatabaseClient` hoặc `R2dbcEntityTemplate` để xây dựng và thực thi truy vấn. Cách này giúp tách hợp đồng repository khỏi chi tiết dựng SQL, đồng thời cho phép chia logic thành các hàm nhỏ theo nhóm điều kiện.

## 3. Tổ chức một câu SQL dài để dễ đọc

Một truy vấn phức tạp nên được trình bày theo cấu trúc mà người đọc có thể lần theo:

1. Xác định tập dữ liệu chính trong `FROM`.
2. Thêm các `JOIN` và điều kiện liên kết.
3. Xác định bộ lọc trong `WHERE`.
4. Nhóm và tổng hợp trong `GROUP BY`/`HAVING`.
5. Chọn thứ tự trong `ORDER BY`.
6. Áp dụng giới hạn kết quả hoặc phân trang.

Ví dụ, truy vấn báo cáo có thể chia thành các CTE có tên theo ý nghĩa:

```sql
WITH customer_orders AS (
    SELECT
        o.id,
        o.customer_id,
        o.status,
        o.created_at
    FROM orders o
    WHERE o.created_at >= :from
      AND o.created_at < :to
),
order_totals AS (
    SELECT
        ol.order_id,
        SUM(ol.quantity * ol.unit_price) AS total
    FROM order_lines ol
    JOIN customer_orders co ON co.id = ol.order_id
    GROUP BY ol.order_id
)
SELECT
    co.id,
    co.customer_id,
    co.status,
    co.created_at,
    ot.total
FROM customer_orders co
LEFT JOIN order_totals ot ON ot.order_id = co.id
ORDER BY co.created_at DESC;
```

CTE giúp đặt tên cho từng bước dữ liệu trung gian. Người đọc có thể hiểu `customer_orders` là tập đơn hàng trong khoảng thời gian, còn `order_totals` là tổng tiền theo từng đơn.

CTE không phải lúc nào cũng nhanh hơn subquery hoặc join. Database có thể inline, materialize hoặc tối ưu theo cách riêng. Dùng CTE trước hết để làm rõ cấu trúc; đánh giá hiệu năng bằng execution plan của database mục tiêu.

### Chọn alias rõ ràng

Alias ngắn có ích trong truy vấn nhiều join, nhưng tránh đặt tên mơ hồ. `orders o`, `customers c`, `order_lines ol` là quy ước dễ nhận diện. Các cột có tên trùng nên được qualify bằng alias.

Đặt alias kết quả rõ ràng nếu projection phụ thuộc tên cột:

```sql
SELECT
    c.display_name AS customer_name,
    COUNT(ol.id) AS line_count
```

Tên alias cần khớp với constructor/property mà Spring Data dùng để ánh xạ projection. Đối với tên có chữ hoa hoặc ký tự đặc biệt, cần hiểu quy tắc folding và quoting của hệ quản trị.

## 4. Giữ projection phù hợp với kết quả SQL

SQL tổng hợp thường trả về dữ liệu không giống entity gốc. Hãy tạo projection riêng để mô tả đúng kết quả.

Ví dụ record projection:

```java
import java.math.BigDecimal;
import java.time.LocalDateTime;

public record OrderSummary(
    Long id,
    String status,
    LocalDateTime createdAt,
    String customerName,
    BigDecimal total
) {}
```

Câu SQL cần trả về các cột có thể ánh xạ vào constructor projection:

```sql
SELECT
    o.id AS id,
    o.status AS status,
    o.created_at AS created_at,
    c.display_name AS customer_name,
    COALESCE(SUM(ol.quantity * ol.unit_price), 0) AS total
FROM orders o
JOIN customers c ON c.id = o.customer_id
LEFT JOIN order_lines ol ON ol.order_id = o.id
GROUP BY o.id, o.status, o.created_at, c.display_name;
```

Các chi tiết mapping có thể phụ thuộc naming strategy và cách Spring Data xử lý constructor projection trong phiên bản đang dùng. Nếu tên alias không được ánh xạ như mong đợi, hãy dùng quy ước tên cột rõ ràng hoặc kiểm tra mapping metadata và integration test.

Không dùng `SELECT *` trong SQL khai báo phức tạp. Khi thêm cột vào bảng hoặc join bảng có cột trùng tên, kết quả có thể thay đổi ngoài ý muốn. Liệt kê cột cần thiết giúp projection ổn định và giảm dữ liệu truyền về.

## 5. Bind tham số và giữ SQL an toàn

Giá trị do người dùng cung cấp phải được bind làm tham số. Không nối trực tiếp chuỗi đầu vào vào SQL:

```java
// Không an toàn: dữ liệu đầu vào trở thành một phần cấu trúc SQL
String sql = "SELECT * FROM customers WHERE email = '" + email + "'";
```

Dùng named parameter:

```java
return databaseClient.sql("""
        SELECT id, email, display_name
        FROM customers
        WHERE email = :email
        """)
    .bind("email", email)
    .map((row, metadata) -> new CustomerSummary(
        row.get("id", Long.class),
        row.get("email", String.class),
        row.get("display_name", String.class)
    ))
    .one();
```

Với repository `@Query`, Spring Data cũng hỗ trợ bind tham số theo tên:

```java
@Query("""
    SELECT id, email, display_name
    FROM customers
    WHERE email = :email
    """)
Mono<CustomerSummary> findSummaryByEmail(
        @Param("email") String email);
```

Named parameter giúp SQL dễ đọc. Spring chuyển named parameter sang marker mà driver cụ thể sử dụng. R2DBC driver có thể dùng cú pháp marker khác nhau, chẳng hạn `?` hoặc `$1`; ứng dụng dùng API Spring nên tránh tự mã hóa marker native trong phần SQL cần dùng qua abstraction named parameter.

### Tham số không thể đại diện cho tên cột hoặc từ khóa

Bind parameter chỉ dành cho giá trị. Không thể dùng `:columnName` để thay thế một tên cột hoặc `:direction` để thay `ASC`/`DESC`.

Nếu cần sắp xếp động, hãy ánh xạ lựa chọn từ client qua danh sách cho phép:

```java
String orderBy = switch (sortField) {
    case "createdAt" -> "created_at";
    case "total" -> "total";
    case "status" -> "status";
    default -> throw new IllegalArgumentException("Unsupported sort field");
};

String direction = descending ? "DESC" : "ASC";
```

Chỉ các chuỗi do ứng dụng kiểm soát mới được ghép vào cấu trúc SQL. Giá trị lọc vẫn phải bind. Không dùng tên cột tùy ý do client gửi vào.

### Bind NULL

R2DBC cần biết kiểu dữ liệu khi bind SQL NULL. Với `DatabaseClient`, dùng `bindNull(name, Type.class)` thay vì truyền Java `null` trực tiếp vào `bind`.

```java
databaseClient.sql("""
        SELECT id, display_name
        FROM customers
        WHERE deleted_at IS NOT NULL
           OR :includeActive = TRUE
        """)
    .bind("includeActive", includeActive);
```

Đây chỉ là ví dụ về tham số boolean. Nếu tham số có thể null, cần quyết định rõ ngữ nghĩa và dùng `bindNull` với kiểu tương ứng. Đừng trộn “không truyền bộ lọc” với “lọc các hàng có cột NULL”.

## 6. IN, danh sách và điều kiện tùy chọn trong SQL khai báo

Truy vấn có thể nhận một danh sách giá trị để lọc:

```java
@Query("""
    SELECT id, customer_id, status, created_at
    FROM orders
    WHERE status IN (:statuses)
    """)
Flux<Order> findByStatuses(
        @Param("statuses") Collection<String> statuses);
```

Spring Data và lớp named-parameter expansion có thể mở rộng collection thành các bind marker tương ứng. Tuy nhiên, hành vi với collection rỗng và kiểu phần tử cần được kiểm tra với phiên bản framework/driver thực tế.

Trước khi gọi method, hãy xử lý danh sách rỗng ở tầng ứng dụng:

- Nếu danh sách rỗng nghĩa là không lọc, gọi một truy vấn không có điều kiện trạng thái.
- Nếu danh sách rỗng nghĩa là không được phép có kết quả, trả `Flux.empty()` hoặc dùng điều kiện luôn sai.
- Nếu danh sách chứa null, loại bỏ hoặc xử lý null riêng theo nghiệp vụ.

Không giả định `IN (:values)` với danh sách rỗng luôn được chuyển thành cú pháp hợp lệ trên mọi database.

### Bộ lọc tùy chọn

Một mẫu SQL thường gặp là:

```sql
WHERE (:status IS NULL OR status = :status)
```

Mẫu này có thể thuận tiện nhưng không phải lúc nào cũng là lựa chọn tối ưu. Nó phụ thuộc khả năng bind NULL, kiểu tham số và query planner. Với nhiều bộ lọc tùy chọn, điều kiện dạng `(:p IS NULL OR column = :p)` có thể làm kế hoạch truy vấn kém chọn lọc hoặc khó tận dụng index.

Nếu cần xây dựng nhiều tổ hợp điều kiện, custom fragment với `Criteria` hoặc dựng SQL có kiểm soát thường rõ ràng hơn. Đặc biệt, phải phân biệt giá trị null có nghĩa “bỏ bộ lọc” hay “tìm cột NULL”.

## 7. Spring Data Dialect làm gì và không làm gì?

Spring Data Relational có khái niệm dialect để thích ứng các thao tác SQL mà framework tự tạo. Dialect cung cấp thông tin về đặc điểm của hệ quản trị, chẳng hạn cách biểu diễn bind marker, kiểu dữ liệu hoặc cú pháp cần thiết cho một số thao tác mapping.

Khi dùng R2dbcEntityTemplate hoặc repository CRUD, Spring Data có thể dựa trên dialect tương ứng với ConnectionFactory để tạo câu lệnh phù hợp với driver/database. Điều này giúp các thao tác CRUD và mapping thông thường ít phụ thuộc vào cú pháp SQL viết tay.

Tuy nhiên, cần phân biệt hai trường hợp:

| Trường hợp | Vai trò của dialect |
| --- | --- |
| repository.save, findById, R2dbcEntityTemplate tạo câu lệnh | Spring Data dùng dialect để tạo SQL phù hợp với driver/database. |
| SQL được viết nguyên văn trong @Query | Câu SQL vẫn phải hợp lệ với database đích. |
| SQL được viết nguyên văn trong DatabaseClient.sql(...) | Named parameter được xử lý bởi Spring, nhưng nội dung SQL tùy chỉnh không tự được dịch sang dialect khác. |
| Custom fragment dùng Criteria/template | Framework có thể tạo phần SQL theo dialect; mọi SQL viết tay trong fragment vẫn mang trách nhiệm của tác giả. |

Ví dụ, dialect có thể giúp Spring Data chọn cách tạo câu lệnh insert phù hợp. Nhưng nếu @Query chứa hàm JSONB riêng của PostgreSQL, đổi ConnectionFactory sang MySQL không làm hàm đó tự đổi thành cú pháp JSON của MySQL.

Không nên coi dialect là một bộ dịch SQL tổng quát. Nó là abstraction cho những điểm mở rộng mà Spring Data hỗ trợ, không phải bộ chuyển đổi mọi câu lệnh tùy chỉnh.

## 8. Ưu tiên SQL chuẩn ở phần có thể dùng chung

Nếu một ứng dụng có thể triển khai trên nhiều hệ quản trị, hãy xác định một tập SQL cơ sở mà các database mục tiêu đều hỗ trợ tốt. SQL chuẩn thường có ích cho:

- SELECT, INSERT, UPDATE, DELETE cơ bản.
- INNER JOIN, LEFT JOIN.
- WHERE, AND, OR, NOT.
- GROUP BY, HAVING, ORDER BY.
- CASE, COALESCE, NULLIF.
- EXISTS và các dạng subquery thông dụng.
- UNION và UNION ALL.
- Các phép so sánh và BETWEEN.

Dù là cú pháp chuẩn, chi tiết về kiểu dữ liệu, collation, NULL ordering, hàm và tối ưu hóa vẫn có thể khác. Hãy xem SQL chuẩn là nền tảng giảm khác biệt, không phải cam kết rằng mọi database cho cùng kết quả với mọi dữ liệu.

Ví dụ CASE giúp biểu diễn logic có thể dùng chung:

```sql
SELECT
    id,
    total,
    CASE
        WHEN total >= :highValue THEN 'HIGH'
        WHEN total >= :mediumValue THEN 'MEDIUM'
        ELSE 'LOW'
    END AS order_band
FROM orders;
```

Các giá trị ngưỡng được bind. Những chuỗi nhãn là hằng do ứng dụng kiểm soát. Nếu nhãn là dữ liệu nghiệp vụ quan trọng và được dùng ở nhiều nơi, cân nhắc tính toán trong domain hoặc lưu dưới dạng trạng thái thay vì lặp lại biểu thức SQL.

### COALESCE và NULLIF

COALESCE(a, b) trả về giá trị đầu tiên không NULL. NULLIF(a, b) trả NULL khi hai biểu thức bằng nhau. Đây là các hàm SQL chuẩn thường hữu ích khi xử lý dữ liệu tổng hợp hoặc tránh chia cho 0:

```sql
SELECT
    customer_id,
    COALESCE(SUM(total), 0) AS total_spent
FROM orders
GROUP BY customer_id;
```

```sql
SELECT
    numerator / NULLIF(denominator, 0) AS ratio
FROM metrics;
```

Kiểu dữ liệu của các biểu thức vẫn cần tương thích. Một số database có thể áp dụng quy tắc ép kiểu hoặc kiểu kết quả khác nhau, nên hãy kiểm thử với kiểu cột thật.

## 9. Những điểm SQL thường khác nhau giữa các hệ quản trị

Khả năng di chuyển thường gặp vấn đề ở những tính năng mà mỗi database có cú pháp hoặc semantics riêng.

| Chủ đề | Khác biệt thường gặp | Cách tổ chức |
| --- | --- | --- |
| Identity và generated key | IDENTITY, AUTO_INCREMENT, sequence, RETURNING hoặc API lấy generated key. | Đặt DDL trong migration theo database; kiểm tra cách driver trả ID. |
| Upsert | ON CONFLICT, ON DUPLICATE KEY UPDATE, MERGE. | Đóng gói trong adapter hoặc repository fragment theo vendor. |
| Phân trang | LIMIT/OFFSET, OFFSET/FETCH, cú pháp riêng. | Dùng API framework khi phù hợp hoặc viết adapter theo dialect. |
| Boolean | Kiểu BOOLEAN, BIT, giá trị literal và cách bind. | Dùng kiểu Java rõ ràng, kiểm tra mapping và literal. |
| Chuỗi | Nối chuỗi, collation, so sánh không phân biệt hoa thường. | Ưu tiên API/SQL chuẩn; tách phần tìm kiếm đặc thù. |
| Ngày giờ | Kiểu có/không có timezone, hàm ngày giờ, độ chính xác. | Chuẩn hóa kiểu Java và timezone; giữ phép lọc theo khoảng. |
| JSON | Kiểu JSON/JSONB, toán tử, hàm và index. | Tách query JSON theo vendor hoặc dùng abstraction có giới hạn. |
| Full-text search | Bộ phân tích, cú pháp, ranking và index riêng. | Tạo implementation riêng cho từng hệ quản trị. |
| Regex và pattern | Hàm, toán tử và quy tắc escape khác nhau. | Không giả định biểu thức regex portable. |
| NULL ordering | Hỗ trợ NULLS FIRST/LAST và mặc định khác nhau. | Viết thứ tự tường minh theo cách tương thích hoặc adapter riêng. |
| Identifier quoting | Dấu nháy kép, backtick, ngoặc vuông và quy tắc chữ hoa/thường. | Tránh tên reserved word; không tự nối identifier tùy input. |

### Identity và generated values

PostgreSQL thường hỗ trợ RETURNING; MySQL thường dùng AUTO_INCREMENT và cơ chế lấy generated key riêng. Không nên viết một câu INSERT ... RETURNING rồi kỳ vọng mọi database đều chấp nhận.

Nếu ứng dụng cần portability, có thể dùng thao tác insert do Spring Data hỗ trợ và xác nhận driver trả về generated ID đúng cách. Nếu cần SQL tùy chỉnh, đặt khác biệt vào implementation riêng cho database tương ứng.

### Upsert

Upsert là ví dụ rõ về khác biệt cú pháp:

```sql
-- PostgreSQL
INSERT INTO customer_setting (customer_id, setting_key, setting_value)
VALUES (:customerId, :key, :value)
ON CONFLICT (customer_id, setting_key)
DO UPDATE SET setting_value = EXCLUDED.setting_value;
```

```sql
-- MySQL
INSERT INTO customer_setting (customer_id, setting_key, setting_value)
VALUES (:customerId, :key, :value)
ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value);
```

Hai đoạn có mục tiêu tương tự nhưng cú pháp và chi tiết semantics khác nhau. Không nhét cả hai vào một câu SQL có nhiều nhánh điều kiện. Hãy cung cấp một implementation cho mỗi dialect hoặc dùng cơ chế abstraction phù hợp nếu framework/driver hỗ trợ đầy đủ trường hợp cần thiết.

### Boolean và literal

Không nên giả định mọi database chấp nhận cùng một literal boolean. Một số hệ dùng kiểu boolean riêng, một số ánh xạ sang bit hoặc số. Bind giá trị boolean bằng kiểu Java Boolean để driver thực hiện mapping; tránh tự chuyển thành chuỗi "true" hoặc "1" nếu không có lý do cụ thể.

## 10. Phân trang và sắp xếp trong SQL tùy chỉnh

Phân trang là một trong những nơi dễ phát sinh SQL phụ thuộc database. LIMIT :limit OFFSET :offset phổ biến ở PostgreSQL và MySQL, trong khi SQL Server thường dùng cú pháp OFFSET ... FETCH với yêu cầu ORDER BY.

Nếu dùng API phân trang do Spring Data hỗ trợ trong ngữ cảnh cụ thể, hãy xác minh khả năng và cách tạo count query của phiên bản R2DBC đang dùng. Không giả định mọi repository @Query tự động có cùng hành vi phân trang như JPA.

Khi viết SQL riêng, luôn dùng thứ tự ổn định:

```sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

Thêm cột ID làm tie-breaker để các hàng có cùng created_at không đổi thứ tự tùy ý giữa các trang. Cú pháp giới hạn trên là ví dụ cho database hỗ trợ LIMIT/OFFSET; hệ khác cần adapter tương ứng.

### Offset pagination và keyset pagination

Offset pagination dễ hiểu nhưng chi phí có thể tăng khi offset lớn. Keyset pagination dùng giá trị của hàng cuối cùng ở trang trước để lấy trang tiếp theo:

```sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = :customerId
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
FETCH FIRST :pageSize ROWS ONLY;
```

Câu lệnh giới hạn ở trên không phải cú pháp dùng chung cho mọi database; phần predicate keyset mới là ý tưởng có thể giữ lại, còn cú pháp giới hạn hàng cần theo vendor. Keyset pagination cần một thứ tự ổn định và các cột cursor phù hợp. Nó phù hợp với tập dữ liệu lớn hoặc luồng cuộn liên tục, nhưng không thay thế được mọi trường hợp cần nhảy tới trang bất kỳ.

## 11. CTE, window function và mức hỗ trợ theo phiên bản

CTE và window function giúp viết truy vấn phân tích dễ đọc:

```sql
WITH ranked_orders AS (
    SELECT
        o.id,
        o.customer_id,
        o.created_at,
        o.total,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.id DESC
        ) AS row_number
    FROM orders o
)
SELECT id, customer_id, created_at, total
FROM ranked_orders
WHERE row_number <= :maxPerCustomer;
```

Ví dụ chọn các đơn mới nhất theo từng khách hàng. CTE và ROW_NUMBER() được hỗ trợ rộng rãi ở các database hiện đại, nhưng mức hỗ trợ, cú pháp bổ sung và tối ưu hóa phụ thuộc phiên bản.

Khi dùng tính năng như recursive CTE, LATERAL, FILTER trong aggregate hoặc window frame nâng cao, hãy xác định phiên bản tối thiểu của database mục tiêu. Nếu một hệ quản trị không hỗ trợ, cần có truy vấn thay thế hoặc giới hạn rõ ràng trong yêu cầu triển khai.

## 12. JSON, array và full-text search

Các tính năng JSON, array và tìm kiếm văn bản thường rất hữu ích nhưng ít portable hơn SQL cơ bản.

Ví dụ PostgreSQL có kiểu JSONB, toán tử truy cập và index riêng. MySQL cũng có kiểu JSON và tập hàm JSON riêng. Tên hàm, đường dẫn, kiểu trả về và khả năng index không giống nhau.

Không nên đặt toàn bộ truy vấn JSON vendor-specific trong repository dùng chung rồi hy vọng đổi driver sẽ giải quyết. Có thể tạo interface theo nhu cầu ứng dụng:

```java
public interface ProductDocumentSearch {
    Flux<Product> findByAttribute(String attribute, String value);
}
```

Sau đó cung cấp implementation cho từng hệ quản trị. Service gọi hợp đồng chung; từng adapter chịu trách nhiệm SQL JSON phù hợp. Nếu ứng dụng chỉ hỗ trợ một database, vẫn nên đặt query JSON trong một fragment có tên rõ để phần phụ thuộc được nhìn thấy.

Với array, full-text search, spatial type hoặc regex, áp dụng cùng nguyên tắc. Chỉ dùng abstraction chung khi nó thực sự bao phủ semantics mà ứng dụng cần; nếu không, để khác biệt lộ ra ở ranh giới repository adapter.

## 13. Tách SQL đặc thù vào adapter theo database

Nếu ứng dụng chỉ triển khai trên một hệ quản trị đã xác định, SQL đặc thù có thể được giữ trong repository fragment có tên rõ ràng. Nếu cùng một ứng dụng phải chạy trên nhiều database, hãy đặt khác biệt vào ranh giới có thể thay thế.

Ví dụ, nghiệp vụ cần lưu hoặc cập nhật một cấu hình theo khóa duy nhất. Hợp đồng ứng dụng chỉ mô tả hành vi:

```java
public interface CustomerSettingWriter {
    Mono<Void> upsert(
        Long customerId,
        String key,
        String value
    );
}
```

Implementation PostgreSQL dùng ON CONFLICT; implementation MySQL dùng ON DUPLICATE KEY UPDATE. Mỗi implementation chứa SQL riêng, nhưng cùng thực hiện hợp đồng đã định. Có thể chọn implementation bằng Spring profile, conditional configuration hoặc cấu hình theo database đang chạy. Bảo đảm chỉ có một implementation phù hợp được đăng ký trong mỗi deployment.

Không nên để service nghiệp vụ tự kiểm tra tên database rồi nối SQL theo vendor. Điều đó khiến logic lưu trữ lan ra nhiều lớp và khó kiểm soát khi thêm hệ quản trị mới.

### Giữ khác biệt ở nơi gần database

Một cách tổ chức package có thể là:

```text
persistence/
  order/
    OrderRepository.java
    OrderSearch.java
    OrderSearchImpl.java
    OrderProjection.java
  vendor/
    postgres/
      PostgresCustomerSettingWriter.java
    mysql/
      MysqlCustomerSettingWriter.java
    CustomerSettingWriter.java
```

Đây là ví dụ về cách tổ chức, không phải quy ước package bắt buộc của Spring. Mục tiêu là người đọc nhìn thấy chỗ chứa SQL đặc thù và không phải tìm nó trong service hoặc controller.

Nếu vendor-specific SQL chỉ xuất hiện trong một method, có thể dùng một fragment riêng. Nếu nhiều tính năng khác nhau cùng phụ thuộc vendor, một adapter theo database giúp tập trung khác biệt và dễ thay thế hơn.

## 14. Dùng abstraction có giới hạn

Không phải mọi khác biệt SQL đều cần một framework abstraction mới. Một abstraction hữu ích khi nó mô tả một nhu cầu nghiệp vụ ổn định và có thể được thực hiện trên các database mục tiêu.

Ví dụ, hợp đồng “tìm các đơn hàng gần đây của khách hàng” có thể có implementation riêng cho từng database nếu việc phân trang, index hoặc lọc JSON khác nhau. Service chỉ cần nhận kết quả theo kiểu thống nhất.

Ngược lại, một abstraction kiểu “thực thi mọi biểu thức SQL trên mọi database” thường quá rộng. Nó có thể buộc ứng dụng giới hạn mình ở tập tính năng chung nhỏ nhất hoặc tạo ra nhiều nhánh cấu hình khó hiểu.

Có thể phân chia truy vấn thành ba mức:

| Mức | Ví dụ | Cách quản lý |
| --- | --- | --- |
| SQL dùng chung | Join, filter, aggregate và subquery phổ biến. | Dùng @Query hoặc fragment với SQL chuẩn, kiểm thử trên mọi database mục tiêu. |
| SQL có khác biệt nhỏ | Pagination syntax, generated key, null ordering. | Dùng helper/adapter nhỏ tại tầng persistence. |
| Tính năng vendor-specific | JSONB, full-text search, upsert, spatial query. | Tách implementation riêng hoặc giới hạn database hỗ trợ. |

Không nên cố trừu tượng hóa một tính năng mà database đích không có semantics tương đương. Nếu full-text search của hai hệ thống cho ranking và tokenization khác nhau, cùng một method name không bảo đảm kết quả giống nhau. Hãy xác định rõ hợp đồng mà ứng dụng cần và những khác biệt nào được chấp nhận.

## 15. Quản lý schema và migration theo hệ quản trị

Portability của query không đủ nếu schema không thể được tạo trên database đích. Kiểu dữ liệu, identity, index, constraint, JSON column, generated column và function trong DDL cũng có thể khác.

Dùng công cụ migration để version hóa thay đổi schema. Nếu hỗ trợ nhiều database, có thể duy trì migration chung cho phần tương thích và migration riêng theo vendor cho những phần không thể dùng chung.

Ví dụ, PostgreSQL có kiểu UUID native trong khi MySQL có thể dùng BINARY(16) hoặc CHAR(36). Một index JSON hoặc expression index cũng có cú pháp riêng. Các khác biệt này cần được thể hiện trong migration có kiểm soát, không nên giấu trong thao tác khởi động ứng dụng.

Một chiến lược triển khai có thể gồm:

1. Xác định database và phiên bản được hỗ trợ.
2. Tạo migration nền cho bảng, cột và constraint chung.
3. Thêm migration theo vendor cho kiểu dữ liệu, index hoặc function riêng.
4. Giữ entity mapping và converter phù hợp với schema của từng profile.
5. Chạy toàn bộ migration trên database mục tiêu trong pipeline kiểm thử.
6. Triển khai ứng dụng theo thứ tự tương thích với schema cũ và mới.

Không sửa migration đã được triển khai ở môi trường dùng chung nếu công cụ migration coi chúng là bất biến. Tạo migration mới để thay đổi schema. Nếu cần hỗ trợ nhiều dialect, hãy bảo đảm pipeline thực sự chạy các tập migration tương ứng, thay vì chỉ kiểm tra compile.

## 16. Kiểm thử portability bằng database thật

Mock repository không kiểm tra được cú pháp SQL, dialect, mapping, kiểu dữ liệu hoặc semantics của database. Với truy vấn khai báo phức tạp, cần integration test bằng driver và database thực tế.

Nếu ứng dụng tuyên bố hỗ trợ nhiều hệ quản trị, hãy chạy cùng bộ kiểm thử hợp đồng trên từng hệ quản trị được hỗ trợ. Testcontainers có thể giúp khởi chạy database cô lập trong pipeline, nhưng image và phiên bản phải tương ứng với môi trường triển khai.

Một ma trận kiểm thử có thể gồm:

| Kiểm thử | Điều cần xác nhận |
| --- | --- |
| Khởi động context và tạo repository | Query method và repository fragment được cấu hình đúng. |
| Chạy từng @Query | SQL hợp lệ, tham số được bind và projection được ánh xạ. |
| Chạy truy vấn CTE/window | Database phiên bản mục tiêu hỗ trợ cú pháp cần dùng. |
| Truy vấn collection IN | Danh sách thường, danh sách rỗng và NULL có ngữ nghĩa đúng. |
| Phân trang | Thứ tự ổn định, count/result đúng và không lặp hoặc bỏ sót dữ liệu. |
| Generated key/upsert | Hành vi insert/update và ID trả về đúng theo vendor. |
| Kiểu dữ liệu | Decimal, timestamp, boolean, enum và JSON được mapping như hợp đồng. |
| Transaction | Nhiều thao tác liên quan commit/rollback theo cấu hình. |
| Migration | Schema được tạo và nâng cấp thành công trên từng database. |

Có thể dùng một interface test hoặc bộ test dùng chung cho các implementation adapter. Mỗi database chạy cùng các trường hợp nghiệp vụ, sau đó bổ sung test riêng cho tính năng vendor-specific.

Ví dụ kiểm tra repository trả projection:

```java
@Test
void returnsOrderSummaryForCustomer() {
    StepVerifier.create(
            orderRepository.findSummaries(from, to)
        )
        .assertNext(summary -> {
            assertNotNull(summary.id());
            assertNotNull(summary.customerName());
            assertNotNull(summary.total());
        })
        .verifyComplete();
}
```

Dữ liệu test cần được chuẩn bị rõ ràng để xác nhận cả kết quả đúng lẫn trường hợp không có hàng. Không chỉ kiểm tra publisher hoàn tất; cần xác minh các giá trị và biên truy vấn.

### Kiểm tra hành vi, không chỉ kiểm tra cú pháp

Hai database có thể chấp nhận cú pháp gần giống nhau nhưng trả kết quả khác do collation, timezone, NULL ordering, precision hoặc kiểu ép chuyển. Vì vậy, portability test cần xác minh semantics nghiệp vụ:

- Chuỗi có phân biệt hoa thường hay không?
- Giá trị NULL được sắp xếp ở đâu?
- Timestamp được lưu và so sánh theo timezone nào?
- Phép chia số có precision/scale nào?
- LIKE và wildcard có cùng quy tắc escape không?
- JSON path trả về scalar hay JSON value?
- Upsert xử lý xung đột trên đúng constraint hay không?

Nếu kết quả giữa các database được phép khác nhau, ghi rõ khác biệt đó trong hợp đồng. Nếu không được phép khác, chuẩn hóa dữ liệu hoặc biểu thức để bảo đảm cùng semantics.

## 17. Dùng query plan và logging để chẩn đoán

Một câu SQL chạy được chưa chắc chạy hiệu quả. Hãy dùng công cụ explain/query plan của database mục tiêu để xem cách optimizer xử lý join, filter, index, sort và aggregate.

Khi truy vấn chậm:

1. Xác định câu SQL thực tế và các bind value có ảnh hưởng đến chọn lọc.
2. Kiểm tra index có phù hợp với điều kiện và thứ tự lọc không.
3. Xem database có scan toàn bảng, sort lớn hoặc join không hiệu quả không.
4. Kiểm tra số hàng ước tính và số hàng thực tế nếu công cụ hỗ trợ.
5. Thử với dữ liệu có quy mô và phân bố gần production.
6. Đo lại sau khi thay đổi index hoặc cấu trúc truy vấn.

Kế hoạch thực thi không nhất thiết giống nhau giữa các database. Đừng sao chép hint hoặc index của một hệ quản trị sang hệ khác mà không đo lại.

Logging SQL hữu ích khi phát triển và điều tra lỗi. Tuy nhiên, cần kiểm soát log parameter vì chúng có thể chứa email, token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Không bật log toàn bộ bind value trong production nếu chưa có chính sách bảo vệ phù hợp.

## 18. Quy trình tổ chức và kiểm tra truy vấn phức tạp

Khi thêm một truy vấn SQL mới, có thể đi theo trình tự:

1. **Viết rõ hợp đồng kết quả:** entity hay projection, số lượng phần tử và semantics của NULL.
2. **Chọn cách triển khai:** derived method, @Query hay custom fragment.
3. **Phác thảo logic SQL:** xác định join, filter, group, sort và pagination.
4. **Đặt tên alias và cột trả về:** bảo đảm mapping projection rõ ràng, tránh SELECT *.
5. **Bind mọi giá trị:** không nối dữ liệu người dùng vào SQL; kiểm soát identifier động bằng allowlist.
6. **Xác định phần phụ thuộc vendor:** hàm, kiểu dữ liệu, upsert, JSON, pagination và generated values.
7. **Chọn ranh giới portability:** SQL chung, adapter nhỏ hoặc implementation riêng theo database.
8. **Quản lý schema bằng migration:** bảo đảm DDL và index tương ứng với truy vấn.
9. **Kiểm thử trên từng database mục tiêu:** xác minh cú pháp, mapping và semantics.
10. **Đo query plan:** tối ưu theo workload thật và ghi lại các giả định vận hành.

Một truy vấn khai báo tốt làm rõ mục đích và cấu trúc dữ liệu mà nó trả về. Spring Data R2DBC giúp quản lý repository, mapping và bind parameter; dialect hỗ trợ SQL do framework tạo. SQL viết tay vẫn phải chịu trách nhiệm về cú pháp và semantics của database đích. Khi giữ phần SQL dùng chung ở mức chuẩn, đặt phần đặc thù trong adapter và kiểm thử bằng database thật, ứng dụng có thể tổ chức truy vấn phức tạp mà vẫn kiểm soát được khả năng di chuyển giữa các hệ quản trị.
