# Truy vấn tổng hợp, GROUP BY và dữ liệu thống kê

Nhiều use case không cần đọc từng entity mà cần một kết quả đã được tổng hợp: tổng doanh thu theo tháng, số đơn hàng theo trạng thái, giá trị trung bình của đơn, số khách hàng hoạt động hoặc lượng tồn kho theo sản phẩm. Với Spring Data R2DBC, nên để database thực hiện phép tổng hợp bằng SQL rồi ánh xạ kết quả thành projection/DTO. Cách này giảm lượng dữ liệu truyền qua mạng, tránh tải hàng loạt entity vào JVM và thường hiệu quả hơn việc lấy tất cả hàng rồi cộng/trung bình trong Java.

Các câu lệnh `GROUP BY`, `HAVING` và hàm aggregate có thể được dùng qua `@Query`, `DatabaseClient` hoặc API phù hợp của `R2dbcEntityTemplate`. Với báo cáo có nhiều phép tính, JOIN hoặc filter linh hoạt, `DatabaseClient` thường giúp kiểm soát SQL và mapping rõ ràng. Cần đặc biệt chú ý semantics của `NULL`, kiểu dữ liệu trả về, cardinality của JOIN và việc phân trang trên các nhóm kết quả thay vì trên hàng nguồn.

## 1. Aggregate query dùng để làm gì?

Aggregate query biến nhiều hàng dữ liệu thành một hoặc nhiều giá trị tổng hợp. Ví dụ bảng `purchase_order` có hàng triệu đơn hàng, nhưng dashboard chỉ cần số đơn và doanh thu theo trạng thái. Thay vì tải từng order vào ứng dụng, database có thể trả vài hàng thống kê.

| Nhu cầu | SQL thường dùng |
|---|---|
| Tổng số hàng | `COUNT(*)` |
| Số giá trị khác NULL | `COUNT(column)` |
| Tổng tiền/số lượng | `SUM(column)` |
| Giá trị trung bình | `AVG(column)` |
| Giá trị nhỏ nhất/lớn nhất | `MIN(column)`, `MAX(column)` |
| Số giá trị phân biệt | `COUNT(DISTINCT column)` |
| Thống kê theo nhóm | `GROUP BY` |
| Lọc nhóm sau tổng hợp | `HAVING` |

Ví dụ: đếm số đơn theo trạng thái:

```sql
SELECT status, COUNT(*) AS order_count
FROM purchase_order
GROUP BY status;
```

Nếu bảng có trạng thái `NEW`, `PAID`, `CANCELLED`, kết quả có tối đa một hàng cho mỗi trạng thái xuất hiện trong tập dữ liệu.

## 2. Bảng dữ liệu dùng trong ví dụ

Giả sử hệ thống có bảng đơn hàng và dòng hàng:

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_no VARCHAR(40) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 4) NOT NULL
);
```

Một số báo cáo thường gặp:

- Số đơn theo trạng thái.
- Tổng doanh thu theo tháng.
- Số đơn và doanh thu theo tenant.
- Số lượng sản phẩm đã bán.
- Giá trị đơn trung bình theo khách hàng.
- Nhóm khách hàng có tổng chi tiêu vượt ngưỡng.

Các ví dụ dùng SQL phổ biến; kiểu timestamp, hàm xử lý ngày và cú pháp phân trang có thể cần điều chỉnh theo database mục tiêu.

## 3. Các hàm aggregate cơ bản

### `COUNT`

`COUNT(*)` đếm tất cả hàng trong tập đầu vào:

```sql
SELECT COUNT(*) AS total_orders
FROM purchase_order;
```

`COUNT(column)` chỉ đếm hàng có giá trị cột khác `NULL`:

```sql
SELECT COUNT(customer_id) AS orders_with_customer
FROM purchase_order;
```

`COUNT(DISTINCT column)` đếm số giá trị khác nhau, bỏ qua `NULL`:

```sql
SELECT COUNT(DISTINCT customer_id) AS customer_count
FROM purchase_order;
```

### `SUM`

`SUM` cộng các giá trị khác `NULL`:

```sql
SELECT SUM(quantity) AS total_quantity
FROM order_line;
```

Với tiền, nên dùng `DECIMAL`/`NUMERIC` và Java `BigDecimal`, không dùng `double` cho phép tính cần độ chính xác thập phân.

### `AVG`

`AVG` tính trung bình trên các giá trị khác `NULL`:

```sql
SELECT AVG(unit_price) AS average_unit_price
FROM order_line;
```

Kiểu kết quả của `AVG` phụ thuộc database và kiểu đầu vào. Hãy kiểm tra mapping qua R2DBC driver; nếu cần quy tắc precision/scale cụ thể, có thể CAST trong SQL theo dialect.

### `MIN` và `MAX`

```sql
SELECT MIN(created_at) AS first_order_at,
       MAX(created_at) AS latest_order_at
FROM purchase_order;
```

`MIN`/`MAX` hoạt động trên kiểu có thứ tự như số, ngày giờ hoặc chuỗi. Với chuỗi, kết quả phụ thuộc collation.

## 4. `NULL` ảnh hưởng phép tổng hợp ra sao?

Các hàm aggregate thường bỏ qua giá trị `NULL`, nhưng kết quả có thể là `NULL` khi không có giá trị đầu vào:

| Biểu thức | Ý nghĩa |
|---|---|
| `COUNT(*)` | Đếm mọi hàng, kể cả hàng có cột NULL |
| `COUNT(amount)` | Đếm hàng có `amount` khác NULL |
| `SUM(amount)` | Tổng các amount khác NULL; có thể NULL nếu không có giá trị |
| `AVG(amount)` | Trung bình trên amount khác NULL; có thể NULL nếu không có giá trị |
| `MIN(amount)`/`MAX(amount)` | Bỏ qua NULL; kết quả NULL nếu không có giá trị |

Ví dụ:

```sql
SELECT COALESCE(SUM(amount), 0) AS total_amount
FROM payment
WHERE status = 'SETTLED';
```

`COALESCE` trả 0 khi `SUM` là NULL. Chỉ dùng giá trị mặc định khi nghiệp vụ coi “không có giao dịch” tương đương tổng bằng 0. Với `AVG`, thay NULL bằng 0 có thể làm sai thống kê; không nên áp dụng mặc định một cách máy móc.

## 5. `GROUP BY` chia dữ liệu thành nhóm

`GROUP BY` gom các hàng có cùng giá trị ở các cột nhóm. Mỗi nhóm tạo ra một hàng kết quả sau khi áp dụng aggregate.

```sql
SELECT status,
       COUNT(*) AS order_count
FROM purchase_order
GROUP BY status
ORDER BY status;
```

Nếu nhóm theo nhiều cột:

```sql
SELECT tenant_id,
       status,
       COUNT(*) AS order_count
FROM purchase_order
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Mỗi cặp `(tenant_id, status)` tạo thành một nhóm riêng. Số hàng kết quả là số tổ hợp khác nhau xuất hiện trong tập dữ liệu sau `WHERE`.

Trong SQL chuẩn, mọi biểu thức ở `SELECT` phải là biểu thức nhóm, hàm aggregate hoặc biểu thức được database cho phép dựa trên functional dependency. Đừng chọn một cột không nằm trong `GROUP BY` và không được tổng hợp rồi kỳ vọng database tự chọn một giá trị đại diện.

## 6. Quy tắc chọn cột khi dùng GROUP BY

Ví dụ hợp lệ:

```sql
SELECT status,
       COUNT(*) AS order_count,
       MAX(created_at) AS latest_order_at
FROM purchase_order
GROUP BY status;
```

Ví dụ không portable và thường không hợp lệ:

```sql
SELECT status,
       customer_id,
       COUNT(*) AS order_count
FROM purchase_order
GROUP BY status;
```

Một nhóm `status` có thể chứa nhiều `customer_id`; database không biết cần chọn customer nào. Nếu cần thống kê theo cả customer, thêm `customer_id` vào `GROUP BY`. Nếu chỉ cần số customer duy nhất trong mỗi status, dùng `COUNT(DISTINCT customer_id)`.

Một số database có quy tắc mở rộng về functional dependency hoặc cho phép cú pháp không chuẩn, nhưng không nên dựa vào behavior đó nếu ứng dụng cần portable giữa nhiều hệ quản trị.

## 7. `WHERE` và `HAVING` khác nhau

`WHERE` lọc hàng trước khi nhóm. `HAVING` lọc nhóm sau khi aggregate.

```sql
SELECT status,
       COUNT(*) AS order_count
FROM purchase_order
WHERE created_at >= :fromTime
GROUP BY status
HAVING COUNT(*) >= :minimumOrders;
```

Trong ví dụ:

1. `WHERE` chỉ giữ đơn hàng từ thời điểm `fromTime` trở đi.
2. `GROUP BY` gom các đơn theo trạng thái.
3. `COUNT(*)` tính số đơn mỗi nhóm.
4. `HAVING` chỉ giữ nhóm có ít nhất `minimumOrders` đơn.

Không dùng `WHERE COUNT(*) >= ...` vì aggregate chưa được tính tại giai đoạn WHERE. Nếu điều kiện không phụ thuộc aggregate, ưu tiên đặt ở WHERE để giảm số hàng phải xử lý.

## 8. Thứ tự xử lý logic của câu SELECT

Có thể hình dung thứ tự logic phổ biến như sau:

```text
FROM / JOIN
    ↓
WHERE
    ↓
GROUP BY
    ↓
HAVING
    ↓
SELECT
    ↓
DISTINCT
    ↓
ORDER BY
    ↓
OFFSET / FETCH / LIMIT
```

Thứ tự thực thi vật lý do optimizer quyết định, nhưng thứ tự logic giúp hiểu vì sao alias aggregate thường không dùng được trong WHERE, vì sao HAVING lọc nhóm và vì sao LIMIT áp dụng lên các hàng kết quả sau grouping.

## 9. Thống kê số đơn và doanh thu theo trạng thái

Giả sử doanh thu được tính từ order lines:

```sql
SELECT o.status,
       COUNT(DISTINCT o.id) AS order_count,
       COALESCE(SUM(l.quantity * l.unit_price), 0) AS revenue
FROM purchase_order o
LEFT JOIN order_line l ON l.order_id = o.id
GROUP BY o.status
ORDER BY o.status;
```

`COUNT(DISTINCT o.id)` bảo đảm mỗi order được đếm một lần sau JOIN một-nhiều. Tổng tiền từ line được cộng theo các hàng line. Nếu query JOIN thêm một collection khác như payment attempts, tổng line có thể bị nhân lên; cần aggregate từng collection trước khi JOIN hoặc query riêng.

Nếu `status` là filter đầu vào, dùng bind parameter thay vì nối chuỗi:

```sql
WHERE o.status = :status
```

## 10. Tổng hợp theo tenant và bảo vệ ranh giới dữ liệu

Trong ứng dụng multi-tenant, tenant filter phải được áp dụng trước khi nhóm:

```sql
SELECT status,
       COUNT(*) AS order_count
FROM purchase_order
WHERE tenant_id = :tenantId
GROUP BY status;
```

Không chỉ group theo `tenant_id` rồi trả tất cả nhóm cho client. Query phải giới hạn đúng tenant đã được xác thực. `tenantId` nên lấy từ security context/server-side identity, không tin trực tiếp giá trị tùy ý trong request.

Nếu báo cáo cần xem nhiều tenant, use case phải có authorization rõ ràng và giới hạn dữ liệu được phép. Aggregate không tự làm dữ liệu an toàn: số liệu tổng hợp vẫn có thể tiết lộ thông tin nhạy cảm nếu nhóm quá nhỏ hoặc filter không đúng.

## 11. Tổng doanh thu theo tháng

Có thể nhóm theo năm và tháng. Cú pháp trích xuất phần ngày giờ khác nhau theo database; ví dụ PostgreSQL:

```sql
SELECT DATE_TRUNC('month', o.created_at) AS month_start,
       COUNT(DISTINCT o.id) AS order_count,
       COALESCE(SUM(l.quantity * l.unit_price), 0) AS revenue
FROM purchase_order o
LEFT JOIN order_line l ON l.order_id = o.id
WHERE o.created_at >= :fromTime
  AND o.created_at < :toTime
GROUP BY DATE_TRUNC('month', o.created_at)
ORDER BY month_start;
```

`DATE_TRUNC` là hàm PostgreSQL, không phải cú pháp portable cho mọi database. MySQL, SQL Server và Oracle có hàm/biểu thức thời gian riêng. Hãy tách query theo dialect nếu hỗ trợ nhiều engine.

Nên dùng khoảng thời gian nửa mở `[fromTime, toTime)` để tránh lỗi biên khi cột có fractional seconds. Ví dụ lấy dữ liệu hết tháng 1 dùng từ đầu tháng 1 inclusive đến đầu tháng 2 exclusive.

## 12. Nhóm theo ngày và timezone

Thống kê theo ngày phụ thuộc timezone nghiệp vụ. Một instant `2026-01-01T17:00:00Z` có thể thuộc ngày khác nhau ở UTC và một timezone địa phương.

Trước khi nhóm theo ngày, hãy xác định:

- Cột lưu instant UTC hay local date-time.
- Ngày báo cáo theo UTC hay timezone của tenant.
- Ranh giới ngày có tuân theo daylight saving time hay không.
- Database session timezone đang được cấu hình thế nào.
- Hàm trunc/extract có chuyển timezone trước khi nhóm không.

Nếu báo cáo theo timezone tenant, có thể chuyển instant sang timezone đó trong SQL hoặc tính ranh giới thời gian ở ứng dụng rồi lọc bằng khoảng nửa mở. Cách thứ hai thường giúp index trên cột timestamp được sử dụng tốt hơn vì cột không bị bọc trong hàm ở WHERE.

## 13. Conditional aggregation

Conditional aggregation tạo nhiều chỉ số trong một lần quét nhóm bằng `CASE`:

```sql
SELECT tenant_id,
       COUNT(*) AS total_orders,
       SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
       SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders
FROM purchase_order
GROUP BY tenant_id;
```

Có thể tính tổng doanh thu chỉ từ các đơn đã thanh toán:

```sql
SELECT tenant_id,
       SUM(CASE WHEN status = 'PAID'
                THEN amount
                ELSE 0 END) AS paid_revenue
FROM order_summary
GROUP BY tenant_id;
```

`CASE` thường portable hơn các aggregate filter extension riêng của database. Với PostgreSQL, `FILTER (WHERE ...)` cũng có thể diễn đạt conditional aggregate, nhưng không nên dùng nếu cần một câu SQL chung cho nhiều engine.

## 14. `COUNT(DISTINCT ...)` và số lượng đối tượng duy nhất

Nếu cần số khách hàng có đơn theo từng trạng thái:

```sql
SELECT status,
       COUNT(DISTINCT customer_id) AS unique_customers
FROM purchase_order
GROUP BY status;
```

`COUNT(DISTINCT)` có thể tốn thêm CPU/memory hoặc sort/hash để loại trùng. Khi dữ liệu lớn, hãy xem execution plan và index. Đừng thay bằng `COUNT(*)` nếu yêu cầu nghiệp vụ là số đối tượng duy nhất.

Với nhiều cột phân biệt, cú pháp đếm distinct tuple khác nhau giữa database. Nếu cần portability, có thể dùng subquery `SELECT DISTINCT col_a, col_b ...` rồi `COUNT(*)` ở lớp ngoài.

## 15. GROUP BY sau JOIN: tránh nhân số liệu

Một lỗi thống kê phổ biến xảy ra khi JOIN nhiều quan hệ một-nhiều. Giả sử một order có 3 lines và 2 payment records. JOIN cả hai collection tạo 6 hàng. `SUM(line_amount)` bị nhân đôi và `COUNT(line.id)` bị nhân theo số payment.

Không sửa bằng cách thêm `DISTINCT` vào mọi aggregate mà chưa hiểu cardinality. Hãy aggregate từng bảng con trước:

```sql
WITH line_totals AS (
    SELECT order_id,
           COUNT(*) AS line_count,
           SUM(quantity * unit_price) AS order_total
    FROM order_line
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id,
           COUNT(*) AS payment_count,
           SUM(amount) AS paid_amount
    FROM payment
    GROUP BY order_id
)
SELECT o.id,
       o.order_no,
       COALESCE(l.line_count, 0) AS line_count,
       COALESCE(l.order_total, 0) AS order_total,
       COALESCE(p.payment_count, 0) AS payment_count,
       COALESCE(p.paid_amount, 0) AS paid_amount
FROM purchase_order o
LEFT JOIN line_totals l ON l.order_id = o.id
LEFT JOIN payment_totals p ON p.order_id = o.id;
```

Mỗi CTE chỉ có tối đa một hàng cho mỗi `order_id`, nên JOIN không nhân bản tổng hợp của collection còn lại. CTE có thể được tối ưu/inlined tùy database; điều quan trọng là logic cardinality.

## 16. Aggregate với LEFT JOIN

Khi muốn giữ nhóm parent không có hàng con, dùng `LEFT JOIN`:

```sql
SELECT c.id AS customer_id,
       c.display_name,
       COUNT(o.id) AS order_count
FROM customer c
LEFT JOIN purchase_order o ON o.customer_id = c.id
GROUP BY c.id, c.display_name;
```

Khách hàng không có order vẫn xuất hiện với `order_count = 0`. Nếu dùng `COUNT(*)`, hàng customer vẫn tạo một hàng kết quả sau LEFT JOIN và count có thể là 1. Hãy đếm cột không null của bảng bên phải như primary key.

Điều kiện trên bảng bên phải cần đặt đúng vị trí. Nếu viết:

```sql
WHERE o.status = 'PAID'
```

thì các hàng không có order có `o.status = NULL` và bị loại, khiến LEFT JOIN có hiệu ứng gần như INNER JOIN. Nếu muốn giữ khách hàng không có đơn đã thanh toán, đưa điều kiện vào `ON`:

```sql
LEFT JOIN purchase_order o
  ON o.customer_id = c.id
 AND o.status = 'PAID'
```

## 17. `HAVING` lọc nhóm theo aggregate

Ví dụ chỉ hiển thị khách hàng có ít nhất 5 đơn:

```sql
SELECT customer_id,
       COUNT(*) AS order_count,
       MAX(created_at) AS latest_order_at
FROM purchase_order
GROUP BY customer_id
HAVING COUNT(*) >= :minimumOrders
ORDER BY order_count DESC;
```

`HAVING` phù hợp cho điều kiện trên tổng số, tổng tiền hoặc trung bình. Nếu có thể lọc hàng nguồn bằng `WHERE`, hãy làm trước khi GROUP BY để giảm khối lượng aggregate.

Không nên dựa vào việc dùng alias `order_count` trong HAVING vì khả năng hỗ trợ khác nhau theo database. Viết lại biểu thức aggregate hoặc bọc query trong subquery để portable hơn.

## 18. Subquery và CTE cho báo cáo nhiều bước

Khi báo cáo cần lọc theo aggregate, có thể bọc GROUP BY trong subquery:

```sql
SELECT customer_id, order_count, total_spend
FROM (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_spend
    FROM order_summary
    WHERE created_at >= :fromTime
      AND created_at < :toTime
    GROUP BY customer_id
) customer_stats
WHERE order_count >= :minimumOrders
ORDER BY total_spend DESC;
```

CTE (`WITH`) giúp tách query thành các bước có tên:

```sql
WITH customer_stats AS (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_spend
    FROM order_summary
    GROUP BY customer_id
)
SELECT *
FROM customer_stats
WHERE total_spend >= :minimumSpend;
```

CTE cải thiện khả năng đọc và tái sử dụng logic trong một câu SQL, nhưng không mặc định luôn nhanh hơn subquery. Optimizer của database quyết định execution plan.

## 19. Truy vấn thống kê bằng `DatabaseClient`

`DatabaseClient` là lựa chọn phù hợp cho aggregate query vì có thể kiểm soát SQL, alias và mapping DTO:

```java
public record StatusStatistics(
    String status,
    Long orderCount
) {}
```

```java
@Repository
public class OrderStatisticsRepository {

    private final DatabaseClient databaseClient;

    public OrderStatisticsRepository(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<StatusStatistics> countByStatus(Long tenantId) {
        return databaseClient.sql("""
                SELECT status,
                       COUNT(*) AS order_count
                FROM purchase_order
                WHERE tenant_id = :tenantId
                GROUP BY status
                ORDER BY status
                """)
            .bind("tenantId", tenantId)
            .map((row, metadata) -> new StatusStatistics(
                row.get("status", String.class),
                row.get("order_count", Long.class)
            ))
            .all();
    }
}
```

Mỗi nhóm được phát thành một phần tử của `Flux<StatusStatistics>`. Không cần lấy tất cả entity `purchase_order` về JVM để đếm.

## 20. Mapping kết quả aggregate và kiểu số

Kiểu SQL của aggregate có thể khác kiểu cột gốc. Ví dụ:

| SQL expression | Kiểu Java thường dùng |
|---|---|
| `COUNT(*)` | `Long` |
| `SUM(INTEGER)` | Có thể là `Long`/numeric theo database |
| `SUM(DECIMAL)` | `BigDecimal` |
| `AVG(DECIMAL)` | Thường dùng `BigDecimal`, cần xác nhận driver |
| `MIN(timestamp)` | Kiểu thời gian theo driver/schema |
| `COUNT(DISTINCT ...)` | `Long` |

Không nên ép mọi aggregate về `Integer` vì bảng có thể vượt giới hạn. Với tiền, dùng `BigDecimal`. Với phần trăm/tỷ lệ, xác định precision/scale rõ ràng và cân nhắc CAST theo dialect.

Ví dụ DTO:

```java
public record RevenueStatistics(
    String status,
    Long orderCount,
    BigDecimal totalRevenue,
    BigDecimal averageOrderValue
) {}
```

Mapper:

```java
.map((row, metadata) -> new RevenueStatistics(
    row.get("status", String.class),
    row.get("order_count", Long.class),
    row.get("total_revenue", BigDecimal.class),
    row.get("average_order_value", BigDecimal.class)
))
```

Nếu driver không map trực tiếp kiểu trả về sang class được yêu cầu, hãy dùng converter hoặc đọc kiểu driver thực tế rồi chuyển đổi an toàn. Không cast số nguyên lớn về `int` nếu chưa kiểm tra overflow.

## 21. Dùng `@Query` trong reactive repository

Với aggregate đơn giản, có thể đặt SQL trong repository method:

```java
public record StatusStatistics(String status, Long orderCount) {}

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT status,
               COUNT(*) AS order_count
        FROM purchase_order
        WHERE tenant_id = :tenantId
        GROUP BY status
        ORDER BY status
        """)
    Flux<StatusStatistics> countByStatus(Long tenantId);
}
```

Spring Data R2DBC hỗ trợ khai báo query bằng `@Query`; cách ánh xạ projection/DTO phụ thuộc kiểu projection, constructor và phiên bản Spring Data. Tên cột/alias cần khớp với mapping convention của DTO. Nếu query có nhiều phép tính, alias phức tạp hoặc cần xử lý kiểu nullable đặc biệt, dùng `DatabaseClient` với mapper tường minh sẽ dễ kiểm soát hơn.

Không dùng `@Query` chỉ để nhét một câu SQL rất dài vào interface nếu nó làm repository khó đọc. Có thể tách custom read repository thành lớp riêng.

## 22. `R2dbcEntityTemplate` và aggregate query

`R2dbcEntityTemplate` hữu ích cho truy vấn theo entity metadata, `Query`, `Criteria` và thao tác CRUD. Tuy nhiên, các truy vấn thống kê có `GROUP BY`, nhiều aggregate expression, CTE hoặc projection đặc biệt thường rõ ràng hơn khi viết SQL trực tiếp qua `DatabaseClient`.

Ví dụ dùng Template cho filter entity thông thường:

```java
Query query = Query.query(
    Criteria.where("tenantId").is(tenantId)
        .and("status").is("PAID")
);

Flux<Order> orders = template.select(query, Order.class).all();
```

Đoạn này đọc entity, không phải aggregate. Nếu sau đó gọi `.collectList()` rồi tính tổng trong Java, ứng dụng đã chuyển công việc aggregate từ database sang JVM. Chỉ làm vậy khi tập dữ liệu nhỏ hoặc có lý do nghiệp vụ cụ thể; với dữ liệu lớn, ưu tiên SQL aggregate.

## 23. Conditional filter cho báo cáo

Một báo cáo có thể lọc theo tenant, status, khoảng ngày và customer. Cần bind giá trị an toàn và tránh viết nhiều câu SQL gần giống nhau không cần thiết.

Ví dụ điều kiện tùy chọn:

```sql
SELECT status,
       COUNT(*) AS order_count
FROM purchase_order
WHERE tenant_id = :tenantId
  AND (:status IS NULL OR status = :status)
  AND created_at >= :fromTime
  AND created_at < :toTime
GROUP BY status;
```

Mẫu `(:status IS NULL OR status = :status)` dễ hiểu nhưng có thể làm optimizer khó tận dụng index trong một số database/plan. Với filter nhiều tổ hợp, có thể xây dựng SQL động bằng cách chỉ thêm điều kiện đã được allow-list, còn mọi giá trị vẫn bind parameter.

Không nối trực tiếp giá trị người dùng vào SQL. Bind parameter bảo vệ giá trị, không bảo vệ tên cột/tên bảng. Nếu cho phép chọn group field hoặc sort field động, dùng mapping allow-list do server định nghĩa.

## 24. Lọc theo khoảng thời gian bằng nửa mở

Với báo cáo theo thời gian, ưu tiên:

```sql
WHERE created_at >= :fromTime
  AND created_at < :toTime
```

Ví dụ tháng 3:

- `fromTime`: đầu tháng 3 inclusive.
- `toTime`: đầu tháng 4 exclusive.

Không nên tạo `23:59:59.999999` cho ngày cuối vì precision timestamp khác nhau giữa database/driver. Khoảng nửa mở tránh bỏ sót dữ liệu ở biên.

Nếu cột lưu UTC instant nhưng báo cáo theo timezone địa phương, hãy chuyển ranh giới ngày địa phương sang instant trước khi bind hoặc dùng phép chuyển timezone trong SQL theo dialect. Không trộn `LocalDateTime` và `Instant` mà không có timezone policy rõ ràng.

## 25. Phân trang kết quả GROUP BY

Khi query đã GROUP BY, `LIMIT`/`OFFSET` áp dụng lên các nhóm kết quả sau khi lọc `HAVING`, không phải số hàng nguồn.

Ví dụ:

```sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(amount) AS total_spend
FROM order_summary
WHERE tenant_id = :tenantId
GROUP BY customer_id
HAVING SUM(amount) >= :minimumSpend
ORDER BY total_spend DESC, customer_id
LIMIT :limit OFFSET :offset;
```

Thứ tự phải ổn định. Nếu nhiều customer có cùng `total_spend`, thêm `customer_id` làm tie-breaker. Nếu không có `ORDER BY`, thứ tự nhóm không được bảo đảm.

## 26. Đếm tổng số nhóm để làm pagination metadata

Nếu API cần total pages của kết quả thống kê, count phải đếm số nhóm sau điều kiện `HAVING`, không phải số hàng nguồn.

Ví dụ bọc query:

```sql
SELECT COUNT(*) AS total_groups
FROM (
    SELECT customer_id
    FROM order_summary
    WHERE tenant_id = :tenantId
    GROUP BY customer_id
    HAVING SUM(amount) >= :minimumSpend
) grouped_customers;
```

Đây là điểm dễ sai: `COUNT(*) FROM order_summary` đếm đơn hàng, trong khi API trả một hàng cho mỗi customer. Tổng số nhóm phải được tính từ cùng logic filter/group/having với content query.

Nếu chỉ cần biết còn nhóm tiếp theo hay không, có thể lấy `limit + 1` nhóm và không chạy count chính xác. Điều này đặc biệt hữu ích với báo cáo có aggregate đắt.

## 27. Reactive composition cho content và count

Có thể kết hợp query lấy content và query đếm nhóm bằng `Mono.zip`:

```java
public Mono<StatisticsPage<CustomerStatistics>> findCustomerStats(
        Long tenantId, int limit, long offset) {

    Mono<List<CustomerStatistics>> content =
        findCustomerStatsContent(tenantId, limit, offset).collectList();

    Mono<Long> totalGroups = countCustomerStatsGroups(tenantId);

    return Mono.zip(content, totalGroups)
        .map(tuple -> new StatisticsPage<>(
            tuple.getT1(), tuple.getT2(), limit, offset));
}
```

`Mono.zip` subscribe hai publisher và có thể chạy hai query đồng thời. Đây là hai statement riêng; dữ liệu có thể thay đổi giữa thời điểm content và count được thực thi. Nếu cần cùng snapshot, dùng transaction/isolation phù hợp. Với dashboard chấp nhận total hơi trễ, có thể cache count hoặc không yêu cầu total chính xác.

## 28. Grouping sets, ROLLUP và CUBE

Một số database hỗ trợ các phép tổng hợp nhiều cấp trong một câu query:

- `ROLLUP`: tạo tổng phụ theo các prefix của danh sách group key và grand total.
- `CUBE`: tạo các tổ hợp tổng hợp của các group key.
- `GROUPING SETS`: chỉ định chính xác những cấp nhóm cần tạo.

Ví dụ ý tưởng:

```sql
SELECT tenant_id,
       status,
       COUNT(*) AS order_count
FROM purchase_order
GROUP BY ROLLUP (tenant_id, status);
```

Kết quả có thể gồm nhóm `(tenant_id, status)`, subtotal theo `tenant_id` và grand total. Những hàng subtotal thường biểu diễn cột group bị lược bằng `NULL`; cần dùng hàm `GROUPING(...)` nếu database hỗ trợ để phân biệt subtotal với dữ liệu nguồn thực sự NULL.

`ROLLUP`, `CUBE`, `GROUPING SETS` và hàm `GROUPING` có mức hỗ trợ/cú pháp khác nhau giữa engine. Chỉ dùng khi database mục tiêu hỗ trợ và có test; nếu cần portability, có thể viết nhiều query aggregate hoặc dùng `UNION ALL` với semantics rõ.

## 29. Window functions khác GROUP BY

`GROUP BY` thu gọn nhiều hàng thành một hàng cho mỗi nhóm. Window function tính aggregate trên một cửa sổ nhưng vẫn giữ từng hàng nguồn.

Ví dụ tính tổng doanh thu theo tenant nhưng vẫn trả từng order:

```sql
SELECT id,
       tenant_id,
       amount,
       SUM(amount) OVER (PARTITION BY tenant_id) AS tenant_total
FROM order_summary;
```

Kết quả vẫn có một hàng cho mỗi order, thêm cột `tenant_total`. Nếu cần xếp hạng order trong tenant:

```sql
SELECT id,
       tenant_id,
       amount,
       ROW_NUMBER() OVER (
           PARTITION BY tenant_id
           ORDER BY amount DESC, id
       ) AS rank_in_tenant
FROM order_summary;
```

Window functions hữu ích cho ranking, running total, moving average và top-N-per-group. Cú pháp và hỗ trợ phụ thuộc database/version; hãy tách dialect khi cần.

## 30. Top N trong mỗi nhóm

Ví dụ lấy 3 khách hàng có doanh thu cao nhất trong từng tenant:

```sql
WITH customer_revenue AS (
    SELECT tenant_id,
           customer_id,
           SUM(amount) AS total_spend
    FROM order_summary
    GROUP BY tenant_id, customer_id
), ranked AS (
    SELECT tenant_id,
           customer_id,
           total_spend,
           ROW_NUMBER() OVER (
               PARTITION BY tenant_id
               ORDER BY total_spend DESC, customer_id
           ) AS row_num
    FROM customer_revenue
)
SELECT tenant_id, customer_id, total_spend
FROM ranked
WHERE row_num <= :topN;
```

`ROW_NUMBER` tạo thứ tự duy nhất; nếu muốn giữ các đồng hạng, cân nhắc `RANK` hoặc `DENSE_RANK`. Tie-breaker trong `ROW_NUMBER` giúp kết quả ổn định.

## 31. Index và hiệu năng aggregate query

Aggregate query có thể phải đọc rất nhiều hàng. Index phù hợp giúp database lọc đầu vào trước khi nhóm và có thể giảm lượng dữ liệu cần scan.

Ví dụ query:

```sql
SELECT status, COUNT(*)
FROM purchase_order
WHERE tenant_id = :tenantId
  AND created_at >= :fromTime
  AND created_at < :toTime
GROUP BY status;
```

Một index ứng viên có thể là:

```sql
CREATE INDEX idx_order_tenant_created_status
ON purchase_order (tenant_id, created_at, status);
```

Thứ tự cột phụ thuộc selectivity và query workload. Nếu database cần nhóm theo status, một index khác có thể có lợi; nhưng không nên suy luận chỉ từ câu SQL. Kiểm tra execution plan trên dữ liệu đủ lớn.

Các điểm cần xem:

- Có full table scan hay index scan?
- Filter có giảm mạnh số hàng trước aggregate không?
- Database dùng hash aggregate hay sort aggregate?
- Có sort spill ra disk không?
- JOIN có tạo quá nhiều hàng trung gian không?
- Ước lượng cardinality có lệch xa số hàng thực tế không?
- Index-only scan có khả thi không?

Không tạo index cho mọi cột GROUP BY. Index tăng chi phí ghi và dung lượng; hãy dựa vào query phổ biến và đo lường.

## 32. Không bọc cột filter trong hàm nếu muốn tận dụng index

Ví dụ:

```sql
WHERE DATE(created_at) = :reportDate
```

Có thể khiến index thông thường trên `created_at` khó được sử dụng hiệu quả vì database phải áp dụng hàm lên cột. Thay vào đó, tính ranh giới thời gian ở ứng dụng rồi dùng khoảng nửa mở:

```sql
WHERE created_at >= :dayStart
  AND created_at < :nextDayStart
```

Nếu cần grouping theo ngày, có thể dùng biểu thức ở `SELECT/GROUP BY`, nhưng vẫn giữ filter range trên cột gốc để hỗ trợ index. Nếu truy vấn theo biểu thức đó rất thường xuyên, xem xét functional index/computed column theo database.

## 33. Approximate statistics và materialized summary

Với dashboard rất lớn, aggregate chính xác trên bảng giao dịch có thể quá tốn kém. Một số lựa chọn:

- Cache kết quả thống kê trong thời gian ngắn.
- Tạo bảng summary được cập nhật theo batch hoặc event.
- Dùng materialized view nếu database hỗ trợ.
- Dùng data warehouse/OLAP store cho báo cáo nặng.
- Dùng approximate distinct/count khi nghiệp vụ chấp nhận sai số.

Ví dụ bảng tổng hợp theo ngày/tenant/status:

```sql
CREATE TABLE daily_order_stats (
    stat_date DATE NOT NULL,
    tenant_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    order_count BIGINT NOT NULL,
    revenue DECIMAL(19, 4) NOT NULL,
    PRIMARY KEY (stat_date, tenant_id, status)
);
```

API dashboard đọc bảng summary thay vì quét toàn bộ order và lines. Tuy nhiên, cần thiết kế cách cập nhật, chống đếm trùng, xử lý late-arriving events, rebuild và đối soát với dữ liệu nguồn.

Approximate count không phù hợp cho logic hạn mức, billing hoặc quyền truy cập nếu sai số có thể gây hậu quả nghiệp vụ. Hãy phân biệt rõ số liệu ước lượng và số liệu chính xác.

## 34. Dữ liệu thống kê có thể cần consistency khác CRUD

Dashboard thường chấp nhận số liệu trễ vài giây/phút; báo cáo tài chính hoặc đối soát có thể cần snapshot chính xác. Hãy xác định freshness và consistency requirement:

| Use case | Mức nhất quán có thể phù hợp |
|---|---|
| Dashboard vận hành | Eventual consistency hoặc cache ngắn |
| Báo cáo theo ngày đã đóng sổ | Snapshot/summary đã chốt |
| Tính phí hoặc billing | Chính xác theo transaction/ledger và quy tắc chốt kỳ |
| Đếm online để hiển thị | Có thể chấp nhận total thay đổi giữa request |
| Kiểm tra hạn mức trước ghi | Cần transaction/locking hoặc cơ chế atomic phù hợp; không dựa vào count hiển thị |

Không dùng kết quả thống kê có thể stale để quyết định một thao tác ghi quan trọng nếu không có cơ chế đồng bộ/atomic riêng.

## 35. Kiểm thử aggregate query bằng Testcontainers

Aggregate query phụ thuộc semantics SQL và kiểu dữ liệu, nên integration test nên chạy trên database mục tiêu. Test cần tạo fixture bao gồm:

- Nhiều nhóm khác nhau.
- Nhóm có một hàng và nhóm có nhiều hàng.
- Giá trị NULL.
- Parent không có child trong LEFT JOIN.
- Nhiều child để phát hiện JOIN multiplication.
- Decimal có scale cần giữ.
- Timestamp sát ranh giới ngày/tháng.
- Tenant/status filter khác nhau.

Ví dụ kiểm tra thống kê theo trạng thái:

```java
@Test
void countsOrdersByStatus() {
    StepVerifier.create(orderStatisticsRepository.countByStatus(tenantId)
            .collectMap(StatusStatistics::status, StatusStatistics::orderCount))
        .assertNext(stats -> {
            assertThat(stats.get("PAID")).isEqualTo(2L);
            assertThat(stats.get("NEW")).isEqualTo(1L);
        })
        .verifyComplete();
}
```

Fixture cần được tạo trước test và tenant ID phải được cô lập. Nếu thứ tự kết quả có ý nghĩa, thêm `ORDER BY` trong SQL và kiểm tra thứ tự thay vì chỉ collect thành map.

## 36. Kiểm thử `NULL`, LEFT JOIN và cardinality

Một bộ test quan trọng nên có:

1. Customer không có order: `COUNT(order.id)` phải là 0.
2. Order không có line: tổng line phải là 0 theo hợp đồng.
3. Line có giá trị nullable: `COUNT(column)` khác `COUNT(*)` đúng kỳ vọng.
4. Một order có nhiều lines và nhiều payments: tổng line không bị nhân.
5. Có nhiều customer với cùng số tiền: sort có tie-breaker.
6. `HAVING` loại đúng nhóm theo aggregate.
7. Count total groups khớp số hàng của query không phân trang.

Đừng chỉ kiểm tra một fixture có mỗi nhóm một hàng. Các lỗi đếm trùng thường chỉ xuất hiện khi quan hệ một-nhiều có nhiều bản ghi.

## 37. Kiểm thử kiểu số và thời gian

Với `SUM(DECIMAL)` và `AVG`, test nên xác nhận giá trị chính xác bằng `BigDecimal`:

```java
assertThat(actual.totalRevenue())
    .isEqualByComparingTo(new BigDecimal("12345.6700"));
```

Nếu scale là một phần của hợp đồng, kiểm tra cả `scale()`. Đối với tỷ lệ, xác định rõ cách làm tròn và số chữ số thập phân.

Với báo cáo theo tháng/ngày, test dữ liệu ở:

- Đúng đầu khoảng inclusive.
- Đúng đầu khoảng exclusive.
- Ngay trước và sau ranh giới tháng.
- Instant UTC tương ứng ngày địa phương khác nhau.
- Ngày có thay đổi DST nếu timezone đó áp dụng.

Đảm bảo test chạy trên timezone/session giống production hoặc cố định timezone rõ ràng.

## 38. Những lỗi thường gặp khi viết truy vấn thống kê

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Count lớn hơn số đối tượng | JOIN một-nhiều nhân hàng | `COUNT(DISTINCT id)` hoặc aggregate trước khi JOIN |
| Customer không có order bị mất | Dùng INNER JOIN | Dùng LEFT JOIN và đếm cột child không null |
| Customer không có order có count bằng 1 | Dùng `COUNT(*)` sau LEFT JOIN | Dùng `COUNT(child.id)` |
| Tổng tiền bị nhân đôi | JOIN nhiều collection | Tách aggregate từng collection hoặc batch query |
| Aggregate trả NULL thay vì 0 | Không có input khác NULL | Dùng `COALESCE` khi nghiệp vụ yêu cầu |
| AVG bị sai | Thay NULL bằng 0 hoặc chia tổng sai mẫu số | Xác định rõ tập giá trị được tính |
| HAVING không lọc đúng | Dùng điều kiện aggregate trong WHERE hoặc nhầm alias | Đặt điều kiện sau GROUP BY bằng HAVING/subquery |
| Total pages không khớp | Đếm hàng nguồn thay vì số nhóm | Count từ subquery chứa GROUP BY/HAVING |
| Báo cáo thiếu dữ liệu ngày cuối | Dùng BETWEEN với thời điểm cuối không đủ precision | Dùng khoảng `[from, to)` |
| Query aggregate chậm | Filter/index chưa phù hợp hoặc scan quá nhiều | Xem execution plan và thiết kế index theo workload |
| DTO mapping lỗi | Kiểu aggregate khác kiểu cột gốc | Kiểm tra kiểu driver, dùng Long/BigDecimal/converter |
| Số liệu tenant bị lộ | Thiếu tenant filter/authorization | Lấy tenant từ security context và bind đúng điều kiện |

## 39. Quy trình xây dựng một endpoint thống kê

**Bước 1 — Xác định chỉ số.** Viết rõ công thức nghiệp vụ: đếm đơn hay đếm khách hàng, doanh thu theo gross/net, xử lý refund/cancel thế nào.

**Bước 2 — Xác định grain.** Một hàng kết quả đại diện cho một tenant, status, customer, ngày hay tổ hợp nào.

**Bước 3 — Xác định tập dữ liệu nguồn.** Chọn filter thời gian, tenant, trạng thái và quyền truy cập trước khi aggregate.

**Bước 4 — Xác định cardinality JOIN.** Liệt kê quan hệ một-một/một-nhiều và kiểm tra có nhân hàng hay không.

**Bước 5 — Viết SQL aggregate.** Dùng `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `GROUP BY` và `HAVING` đúng semantics.

**Bước 6 — Thiết kế DTO.** Chọn kiểu Java phù hợp, đặc biệt `Long`, `BigDecimal` và nullable wrapper.

**Bước 7 — Chọn API R2DBC.** Dùng `@Query` cho query đơn giản hoặc `DatabaseClient` cho projection/aggregate phức tạp.

**Bước 8 — Thiết kế pagination.** Phân trang nhóm sau GROUP BY; count phải đếm nhóm hoặc dùng slice `limit + 1`.

**Bước 9 — Tối ưu.** Kiểm tra execution plan, index, filter range và chi phí JOIN/aggregate.

**Bước 10 — Kiểm thử.** Dùng Testcontainers, fixture có null/cardinality/biên thời gian và xác nhận kết quả với dữ liệu độc lập đã biết.

## 40. Kết luận

Truy vấn tổng hợp và `GROUP BY` cho phép database biến tập dữ liệu lớn thành kết quả thống kê nhỏ trước khi gửi về ứng dụng. `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `COUNT(DISTINCT)` cùng `HAVING` là các công cụ cơ bản để xây dựng báo cáo theo tenant, trạng thái, khách hàng hoặc thời gian. Trong Spring Data R2DBC, hãy ánh xạ các hàng aggregate thành DTO/projection bằng `DatabaseClient` hoặc query method phù hợp, thay vì tải toàn bộ entity rồi tính toán trong JVM.

Điều quan trọng là xác định đúng grain của mỗi nhóm, hiểu `NULL`, chọn kiểu số chính xác và kiểm soát cardinality khi JOIN. Đặc biệt, JOIN nhiều quan hệ một-nhiều có thể nhân số liệu; hãy aggregate từng collection trước hoặc tách query. Khi phân trang, count phải đếm số nhóm sau `GROUP BY`/`HAVING`, còn filter và index cần được thiết kế theo workload thực. Kết hợp integration test trên database mục tiêu và execution plan giúp số liệu thống kê chính xác, an toàn theo tenant và đủ hiệu năng khi dữ liệu tăng.
