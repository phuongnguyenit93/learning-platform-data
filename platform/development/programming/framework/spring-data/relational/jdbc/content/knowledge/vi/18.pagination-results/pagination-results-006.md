# Phân trang SQL tự viết bằng LIMIT/OFFSET theo dialect

Trong **Spring Data Relational JDBC**, có những truy vấn cần SQL tùy chỉnh để JOIN nhiều bảng, tính toán dữ liệu hoặc trả về một projection riêng. Khi viết SQL trực tiếp, lập trình viên phải tự quy định cách lấy từng trang dữ liệu. Một cách phổ biến là dùng **LIMIT/OFFSET** trên các hệ quản trị hỗ trợ cú pháp này.

Ý tưởng cơ bản:

- **LIMIT** xác định số hàng tối đa cần trả về.
- **OFFSET** xác định số hàng cần bỏ qua trước khi lấy kết quả.
- **ORDER BY** xác định thứ tự hàng trước khi phân trang.

Tuy nhiên, cú pháp phân trang không giống nhau ở mọi hệ quản trị. PostgreSQL và MySQL thường dùng `LIMIT ... OFFSET ...`, còn SQL Server và Oracle hiện đại dùng `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY`. Khi viết SQL thủ công trong Spring Data JDBC, bạn phải chọn cú pháp phù hợp với database thực tế, bind các giá trị phân trang an toàn và đảm bảo thứ tự ổn định.

Bài học tập trung vào cách tự triển khai phân trang bằng SQL, cách chuyển page/size thành limit/offset, cách viết query theo dialect, count query, và các giới hạn của offset pagination.

## 1. Phân trang SQL hoạt động như thế nào?

Giả sử bảng `purchase_orders` có các đơn hàng:

| ID | Order number | Status | Created at |
|---:|---|---|---|
| 101 | ORD-0101 | PAID | 2026-11-01 09:00 |
| 102 | ORD-0102 | NEW | 2026-11-01 10:00 |
| 103 | ORD-0103 | PAID | 2026-11-02 08:00 |
| 104 | ORD-0104 | CANCELLED | 2026-11-02 11:00 |
| 105 | ORD-0105 | PAID | 2026-11-03 14:00 |
| 106 | ORD-0106 | NEW | 2026-11-04 09:00 |

Nếu muốn hiển thị 2 đơn mỗi trang, ta cần chia tập kết quả thành các nhóm:

```text
Page 0: 101, 102
Page 1: 103, 104
Page 2: 105, 106
```

Với cách đánh số trang bắt đầu từ 0:

- Trang 0 bỏ qua 0 hàng.
- Trang 1 bỏ qua 2 hàng.
- Trang 2 bỏ qua 4 hàng.

Công thức:

`offset = page × pageSize`

Với `pageSize = 2`:

| Page | Page size | Offset | SQL tương ứng |
|---:|---:|---:|---|
| 0 | 2 | 0 | Bỏ qua 0 hàng, lấy 2 |
| 1 | 2 | 2 | Bỏ qua 2 hàng, lấy 2 |
| 2 | 2 | 4 | Bỏ qua 4 hàng, lấy 2 |
| 3 | 2 | 6 | Bỏ qua 6 hàng, có thể không còn dữ liệu |

Ví dụ SQL theo cú pháp PostgreSQL:

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 2 OFFSET 2;
```

Truy vấn bỏ qua hai hàng đầu theo thứ tự đã sắp xếp, sau đó trả về tối đa hai hàng.

**ORDER BY là điều kiện nền tảng của phân trang.** Nếu không chỉ định thứ tự, database không bảo đảm hàng nào sẽ nằm ở trang đầu hay trang sau. Một query có LIMIT/OFFSET nhưng không có ORDER BY có thể trả về thứ tự khác nhau giữa các lần thực thi.

## 2. Vai trò của LIMIT, OFFSET và ORDER BY

### 2.1. LIMIT

`LIMIT` giới hạn số hàng tối đa:

```sql
SELECT id, order_number
FROM purchase_orders
ORDER BY id
LIMIT 10;
```

Truy vấn lấy tối đa 10 hàng. Nếu chỉ có 6 hàng phù hợp, kết quả có 6 hàng.

### 2.2. OFFSET

`OFFSET` bỏ qua một số hàng đầu tiên của tập kết quả đã được sắp xếp:

```sql
SELECT id, order_number
FROM purchase_orders
ORDER BY id
LIMIT 10 OFFSET 20;
```

Truy vấn bỏ qua 20 hàng đầu rồi lấy tối đa 10 hàng tiếp theo.

OFFSET thường bắt đầu từ 0. Nếu `offset = 0`, không bỏ qua hàng nào.

### 2.3. ORDER BY

`ORDER BY` xác định thứ tự trước khi database áp dụng giới hạn:

```sql
SELECT id, order_number, created_at
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;
```

Ở đây:

- `created_at DESC` đưa đơn mới hơn lên trước.
- `id DESC` là tie-breaker khi nhiều đơn có cùng thời điểm tạo.
- `LIMIT 20` lấy tối đa 20 hàng đầu tiên.
- `OFFSET 0` bắt đầu từ hàng đầu.

Không nên chỉ sắp xếp theo cột có thể trùng như status, tên hoặc timestamp. Hãy thêm một cột duy nhất, thường là primary key, để thứ tự giữa các hàng có cùng giá trị sort được xác định.

### 2.4. Trình tự xử lý logic

Có thể hình dung đơn giản:

```text
FROM / JOIN
    ↓
WHERE
    ↓
GROUP BY / HAVING (nếu có)
    ↓
ORDER BY
    ↓
OFFSET
    ↓
LIMIT / FETCH
```

Đây là mô hình logic để hiểu kết quả, không phải thứ tự thực thi vật lý bắt buộc của query planner. Database có thể chọn kế hoạch tối ưu khác nhưng phải giữ đúng ngữ nghĩa SQL.

## 3. Cú pháp phân trang theo database dialect

Một *dialect* phản ánh cú pháp và khả năng SQL của một hệ quản trị cụ thể. Spring Data Relational có thể sử dụng dialect trong các hoạt động SQL do framework tạo, nhưng khi bạn **tự viết câu SQL**, không nên kỳ vọng framework tự chuyển đổi LIMIT/OFFSET sang cú pháp của mọi database.

Bảng sau tóm tắt cú pháp thường gặp:

| Database | Cú pháp phân trang thường dùng |
|---|---|
| PostgreSQL | `LIMIT :limit OFFSET :offset` |
| MySQL | `LIMIT :limit OFFSET :offset` |
| MariaDB | `LIMIT :limit OFFSET :offset` |
| SQLite | `LIMIT :limit OFFSET :offset` |
| SQL Server 2012+ | `ORDER BY ... OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY` |
| Oracle 12c+ | `OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY` |
| DB2 | `OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY` |

Cú pháp chi tiết có thể khác theo phiên bản, driver và cách binding tham số. Hãy kiểm tra hệ quản trị mà ứng dụng đang chạy, đặc biệt nếu hỗ trợ nhiều database.

### 3.1. PostgreSQL

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

PostgreSQL cũng hỗ trợ dạng:

```sql
SELECT id, order_number, status
FROM purchase_orders
ORDER BY id
OFFSET 20 ROWS
FETCH NEXT 10 ROWS ONLY;
```

Dạng `LIMIT/OFFSET` thường được dùng trong ứng dụng PostgreSQL.

### 3.2. MySQL và MariaDB

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

MySQL còn hỗ trợ dạng ngắn:

```sql
SELECT id, order_number
FROM purchase_orders
ORDER BY id
LIMIT 20, 10;
```

Trong cú pháp `LIMIT offset, row_count`, số đầu tiên là offset, số thứ hai là số hàng lấy. Cách viết này dễ gây nhầm nếu đọc nhanh. Với code ứng dụng, `LIMIT row_count OFFSET offset` thường dễ hiểu hơn.

### 3.3. SQL Server

SQL Server sử dụng `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` và yêu cầu `ORDER BY`:

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = @status
ORDER BY created_at DESC, id DESC
OFFSET @offset ROWS
FETCH NEXT @limit ROWS ONLY;
```

Nếu dùng Spring `NamedParameterJdbcTemplate`, tên tham số có thể viết `:status`, `:offset` và `:limit`; Spring chuyển chúng thành bind parameters phù hợp. Cú pháp `@status` ở ví dụ trên là dạng tham số T-SQL minh họa khi viết SQL trực tiếp trong công cụ SQL Server.

### 3.4. Oracle 12c trở lên

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
OFFSET :offset ROWS
FETCH NEXT :limit ROWS ONLY;
```

Oracle hỗ trợ cú pháp phân trang chuẩn này từ Oracle Database 12c. Với phiên bản cũ hơn, có thể phải dùng truy vấn lồng và `ROWNUM`; không nên áp dụng cú pháp cũ nếu hệ thống đã dùng phiên bản hỗ trợ OFFSET/FETCH.

### 3.5. DB2

Cú pháp thường gặp:

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = ?
ORDER BY created_at DESC, id DESC
OFFSET ? ROWS
FETCH NEXT ? ROWS ONLY;
```

Với JDBC positional parameters, thứ tự bind phải đúng với vị trí dấu `?`. Nếu dùng named parameter abstraction, hãy kiểm tra cách Spring chuyển tham số theo driver đang dùng.

### 3.6. Vì sao không có một câu SQL duy nhất cho mọi database?

Các hệ quản trị phát triển cú pháp SQL theo từng phiên bản. Một câu truy vấn có thể:

- Chạy trên PostgreSQL nhưng lỗi cú pháp trên SQL Server.
- Chạy trên Oracle 12c+ nhưng không chạy trên Oracle cũ.
- Có cú pháp tương tự nhưng cách binding LIMIT/OFFSET khác theo driver.
- Có thứ tự mặc định về NULL khác nhau.

Vì vậy, SQL phân trang tự viết là một phần của contract với database. Khi đổi database hoặc nâng version, cần kiểm tra lại truy vấn và integration tests.

## 4. Viết @Query với LIMIT/OFFSET trong Spring Data JDBC

Với một truy vấn SQL khai báo bằng `@Query`, bạn có thể đưa giá trị limit và offset vào câu SQL như named parameters nếu cú pháp database/driver hỗ trợ bind ở vị trí đó.

Ví dụ PostgreSQL:

```java
import java.util.List;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, order_number, customer_id, status, created_at
        FROM purchase_orders
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        LIMIT :limit OFFSET :offset
        """)
    List<PurchaseOrder> findPageByStatus(
        @Param("status") String status,
        @Param("limit") int limit,
        @Param("offset") long offset
    );
}
```

Gọi:

```java
List<PurchaseOrder> page = repository.findPageByStatus(
    "PAID",
    20,
    40L
);
```

Câu truy vấn lấy tối đa 20 đơn `PAID` sau khi bỏ qua 40 đơn đầu theo thứ tự tạo mới nhất.

Các tham số `:status`, `:limit` và `:offset` là **giá trị được bind**, không phải phần SQL được ghép chuỗi. Đối với một dialect khác, chỉ thay đoạn cú pháp phân trang phù hợp; phần bind dữ liệu và filter vẫn theo cùng nguyên tắc.

### 4.1. Tính offset trong service

Không nên yêu cầu client tự tính offset nếu API đã nhận page và size. Service có thể chuyển đổi:

```java
public List<PurchaseOrder> findPage(
        String status,
        int page,
        int size) {

    if (page < 0) {
        throw new IllegalArgumentException(
            "Page must be zero or greater"
        );
    }

    if (size < 1 || size > 100) {
        throw new IllegalArgumentException(
            "Page size must be between 1 and 100"
        );
    }

    long offset = (long) page * size;

    return repository.findPageByStatus(status, size, offset);
}
```

Ví dụ `page = 2` và `size = 20`:

`offset = 2 × 20 = 40`

Ép `page` sang `long` trước phép nhân để tránh overflow kiểu `int` trong các phép tính lớn. Trong hệ thống có giới hạn page/size, vẫn cần validation trước khi tạo query.

### 4.2. Giữ nguyên ý nghĩa của page number

Một API thường đánh số trang từ 0 hoặc 1. Spring Data `PageRequest` dùng page number bắt đầu từ 0. Nếu API của bạn bắt đầu từ 1, cần chuyển đổi rõ ràng:

```java
int zeroBasedPage = requestedPage - 1;

if (requestedPage < 1) {
    throw new IllegalArgumentException("Page must start at 1");
}

long offset = (long) zeroBasedPage * pageSize;
```

Không trộn page number bắt đầu từ 1 với công thức offset dành cho page number bắt đầu từ 0. Đây là lỗi phổ biến khiến trang đầu tiên bị bỏ qua hoặc dữ liệu các trang lệch nhau.

### 4.3. Kiểu dữ liệu của limit và offset

Dùng kiểu số nguyên:

- `int` thường đủ cho page size bị giới hạn nhỏ.
- `long` phù hợp hơn cho offset vì tổng số hàng có thể lớn.
- Không nhận số âm.
- Không để size bằng 0 nếu API yêu cầu một trang có nội dung.
- Đặt giới hạn tối đa để tránh query trả về quá nhiều hàng.

Việc database/driver hỗ trợ bind offset lớn đến mức nào còn tùy dialect. Hãy đảm bảo kiểu Java, kiểu tham số JDBC và giới hạn của hệ quản trị tương thích.

## 5. Tự triển khai phân trang bằng NamedParameterJdbcTemplate

Với SQL tùy biến phức tạp hoặc kết quả DTO, custom repository thường linh hoạt hơn `@Query`. Ví dụ lấy danh sách đơn kèm tên khách hàng:

```sql
SELECT
    o.id,
    o.order_number,
    o.status,
    c.full_name AS customer_name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset;
```

DTO:

```java
public record OrderSummary(
    long id,
    String orderNumber,
    String status,
    String customerName
) {}
```

Repository:

```java
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderSummaryRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderSummaryRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderSummary> findPage(
            String status,
            int limit,
            long offset) {

        String sql = """
            SELECT
                o.id,
                o.order_number,
                o.status,
                c.full_name AS customer_name
            FROM purchase_orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE o.status = :status
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT :limit OFFSET :offset
            """;

        Map<String, Object> params = Map.of(
            "status", status,
            "limit", limit,
            "offset", offset
        );

        return jdbc.query(
            sql,
            params,
            (rs, rowNum) -> new OrderSummary(
                rs.getLong("id"),
                rs.getString("order_number"),
                rs.getString("status"),
                rs.getString("customer_name")
            )
        );
    }
}
```

Ở đây:

- SQL do ứng dụng kiểm soát.
- `NamedParameterJdbcTemplate` bind giá trị filter, limit và offset.
- `RowMapper` chuyển mỗi hàng thành `OrderSummary`.
- DTO chỉ chứa các trường cần cho màn hình.
- Không cần tải aggregate đầy đủ nếu use case chỉ đọc dữ liệu trình bày.

Ví dụ SQL dùng LIMIT/OFFSET kiểu PostgreSQL/MySQL. Với SQL Server hoặc Oracle, hãy thay phần phân trang theo dialect tương ứng.

### 5.1. Kiểm tra tham số ngay trong repository hoặc service

Không nên để mọi caller tự do truyền giá trị bất kỳ:

```java
private void validatePageArguments(int limit, long offset) {
    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("Invalid limit");
    }

    if (offset < 0) {
        throw new IllegalArgumentException("Offset cannot be negative");
    }
}
```

Có thể đặt validation tại service/API boundary và giữ repository ở mức truy cập dữ liệu. Nếu repository được dùng từ nhiều nơi, một lớp bảo vệ bổ sung giúp tránh truy vấn nguy hiểm do caller truyền sai.

## 6. Count query để biết tổng số bản ghi

LIMIT/OFFSET chỉ trả về một phần dữ liệu. Nếu giao diện cần hiển thị:

- Tổng số đơn hàng phù hợp.
- Tổng số trang.
- “Đang xem 21–40 trong 135 đơn”.

thì cần thêm một truy vấn đếm.

Ví dụ:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = :status;
```

Trong custom repository:

```java
public long countByStatus(String status) {
    String sql = """
        SELECT COUNT(*)
        FROM purchase_orders
        WHERE status = :status
        """;

    Long total = jdbc.queryForObject(
        sql,
        Map.of("status", status),
        Long.class
    );

    return total == null ? 0L : total;
}
```

Thông thường `COUNT(*)` trả về một hàng chứa số lượng, kể cả khi không có bản ghi phù hợp (giá trị là 0). Việc xử lý null ở Java là phòng vệ theo chữ ký API và cách mapping cụ thể.

### 6.1. Count và data query phải có cùng điều kiện

Nếu query lấy nội dung trang:

```sql
SELECT id, order_number
FROM purchase_orders
WHERE status = :status
  AND customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

thì count query phải dùng cùng filter:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = :status
  AND customer_id = :customerId;
```

Nếu bỏ sót điều kiện `customer_id` trong count query, tổng số hàng và số trang sẽ lớn hơn thực tế.

### 6.2. Đếm đúng mức dữ liệu khi có JOIN

Giả sử một đơn có nhiều dòng sản phẩm. Query:

```sql
SELECT o.id, oi.product_id
FROM purchase_orders o
JOIN order_items oi ON oi.order_id = o.id;
```

trả về một hàng cho mỗi cặp đơn/sản phẩm. Nếu giao diện phân trang **đơn hàng**, count cần đếm đơn duy nhất:

```sql
SELECT COUNT(DISTINCT o.id)
FROM purchase_orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.status = :status;
```

Nếu giao diện phân trang **dòng sản phẩm**, `COUNT(*)` trên kết quả JOIN mới có thể là con số đúng.

Hãy xác định *grain* (mức một hàng đại diện) của nội dung trang rồi viết count tương ứng. Đếm nhầm grain là nguyên nhân thường gặp khiến tổng số trang không khớp dữ liệu hiển thị.

### 6.3. Tổng số trang

Với tổng số hàng `total` và page size `size`:

`totalPages = ceil(total / size)`

Có thể tính bằng Java:

```java
long totalPages = (total + size - 1) / size;
```

Cách này yêu cầu `size > 0` và cần tránh overflow nếu total có thể gần giới hạn kiểu long. Cách tính an toàn hơn về mặt số học:

```java
long totalPages = total / size
    + (total % size == 0 ? 0 : 1);
```

Nếu `total = 135` và `size = 20`, tổng số trang là 7.

### 6.4. Khi nào không cần count query?

Nếu UI chỉ cần biết có dữ liệu tiếp theo, không cần tổng số trang. Có thể lấy thêm một hàng:

```sql
SELECT id, order_number, status
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :fetchSize OFFSET :offset;
```

Trong đó `fetchSize = pageSize + 1`. Nếu query trả nhiều hơn page size, có trang tiếp theo; bỏ hàng thừa trước khi trả response.

Cách này tránh count query có thể tốn kém. Custom repository cần tự tạo metadata như `hasNext` thay vì mong SQL khai báo tự tạo `Slice`.

## 7. Phân trang khi JOIN dữ liệu một-nhiều

Một lỗi quan trọng là áp dụng LIMIT/OFFSET sau khi JOIN một quan hệ một-nhiều.

Giả sử một đơn có nhiều dòng sản phẩm:

```text
Order 42
  Item A
  Item B
  Item C

Order 43
  Item D
```

Query:

```sql
SELECT o.id, o.order_number, i.product_id
FROM purchase_orders o
LEFT JOIN order_items i ON i.order_id = o.id
ORDER BY o.id
LIMIT 2 OFFSET 0;
```

`LIMIT 2` giới hạn **hai hàng sau JOIN**, không phải hai đơn hàng. Kết quả có thể chỉ gồm Order 42 với Item A và Item B, còn Item C không xuất hiện trong trang. Nếu map các hàng đó thành object theo cách không phù hợp, dữ liệu chi tiết của aggregate có thể bị cắt.

### 7.1. Phân trang ID của bảng gốc trước

Nếu mục tiêu là 20 đơn mỗi trang, hãy phân trang tập ID đơn trước rồi mới lấy dữ liệu con:

```sql
WITH page_orders AS (
    SELECT id
    FROM purchase_orders
    WHERE status = :status
    ORDER BY created_at DESC, id DESC
    LIMIT :limit OFFSET :offset
)
SELECT
    o.id,
    o.order_number,
    o.status,
    i.product_id,
    i.quantity
FROM page_orders p
JOIN purchase_orders o ON o.id = p.id
LEFT JOIN order_items i ON i.order_id = o.id
ORDER BY o.created_at DESC, o.id DESC, i.product_id;
```

Truy vấn con/CTE giới hạn đúng tập root trước. Sau đó JOIN tất cả các dòng sản phẩm thuộc những đơn trong trang. Kết quả cuối có thể có nhiều hàng trên mỗi đơn, nhưng không làm mất một phần các đơn do giới hạn sau JOIN.

### 7.2. Count query cho trang root

Count đơn hàng nên đếm trên bảng gốc với filter tương ứng:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = :status;
```

Không đếm các dòng order_items nếu response được phân trang theo đơn.

### 7.3. Khi cần DTO một hàng mỗi đơn

Nếu màn hình chỉ cần tổng tiền, hãy tổng hợp dòng sản phẩm trước khi phân trang hoặc trong query được thiết kế theo đúng grain:

```sql
SELECT
    o.id,
    o.order_number,
    o.status,
    COALESCE(t.total_amount, 0) AS total_amount
FROM purchase_orders o
LEFT JOIN (
    SELECT order_id,
           SUM(quantity * unit_price) AS total_amount
    FROM order_items
    GROUP BY order_id
) t ON t.order_id = o.id
WHERE o.status = :status
ORDER BY o.created_at DESC, o.id DESC
LIMIT :limit OFFSET :offset;
```

Subquery `t` chỉ có một hàng cho mỗi `order_id`, nên JOIN không nhân số hàng của order. Điều này giúp phân trang và tổng hợp dễ kiểm soát hơn.

## 8. Thứ tự ổn định và thay đổi dữ liệu giữa các trang

Ngay cả khi đã có ORDER BY, dữ liệu có thể thay đổi giữa hai lần gọi API.

### 8.1. Thêm tie-breaker duy nhất

Không ổn định:

```sql
ORDER BY created_at DESC
```

Ổn định hơn:

```sql
ORDER BY created_at DESC, id DESC
```

Nếu nhiều hàng có cùng `created_at`, `id` quyết định thứ tự giữa chúng. Primary key thường là tie-breaker phù hợp.

### 8.2. Dữ liệu mới được thêm giữa hai request

Giả sử:

1. Người dùng tải trang 0, offset 0, limit 20.
2. Một đơn mới được thêm và nằm đầu danh sách.
3. Người dùng tải trang 1, offset 20, limit 20.

Vì hàng mới làm dịch chuyển vị trí của các hàng cũ, trang tiếp theo có thể lặp một đơn đã xuất hiện ở trang trước hoặc bỏ sót một đơn. Thêm tie-breaker làm thứ tự xác định tại mỗi lần query, nhưng không khóa vị trí hàng giữa các request.

### 8.3. Transaction có thể giúp gì?

Nếu cần nội dung và count query nhìn thấy cùng một trạng thái dữ liệu, có thể chạy chúng trong cùng transaction. Mức nhất quán thực tế vẫn phụ thuộc isolation level và hệ quản trị. Với READ COMMITTED, hai câu SELECT có thể nhìn thấy các commit khác nhau tùy database.

Đối với phân trang qua nhiều HTTP request, giữ một transaction mở xuyên suốt các lần tải trang thường không phù hợp. Nếu yêu cầu duyệt một snapshot nhất quán, cần thiết kế cơ chế snapshot/version/cursor rõ ràng.

## 9. Hiệu năng và giới hạn của OFFSET

OFFSET dễ triển khai, nhưng càng sâu thì chi phí có thể càng lớn.

Ví dụ:

```sql
SELECT id, order_number, created_at
FROM purchase_orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 500000;
```

Database phải xác định các hàng đứng trước vị trí cần trả về. Dù có index phù hợp, việc bỏ qua một offset rất lớn vẫn có thể tốn công xử lý.

### 9.1. Index cho ORDER BY và WHERE

Nếu query thường lọc theo status và sắp xếp theo created_at/id:

```sql
CREATE INDEX idx_orders_status_created_id
    ON purchase_orders(status, created_at DESC, id DESC);
```

Index này là một ví dụ thiết kế cho workload cụ thể. Index phù hợp phụ thuộc hệ quản trị, selectivity, cardinality, thứ tự filter/sort và kế hoạch thực thi. Không tạo index theo ví dụ mà chưa đo trên dữ liệu thực tế.

### 9.2. Khi nào OFFSET vẫn phù hợp?

OFFSET phù hợp khi:

- Danh sách có quy mô vừa phải.
- Người dùng cần nhảy đến một trang cụ thể.
- Tổng số trang được hiển thị.
- Truy vấn có index và độ trễ đáp ứng yêu cầu.
- Dữ liệu không thay đổi quá nhanh trong quá trình người dùng duyệt.

### 9.3. Khi nào nên cân nhắc keyset pagination?

Với danh sách lớn, feed hoặc lịch sử đơn hàng, có thể dùng cursor/keyset pagination. Thay vì bỏ qua 500.000 hàng, query lấy các hàng đứng sau giá trị cuối cùng của trang trước.

Với thứ tự `created_at DESC, id DESC`:

```sql
SELECT id, order_number, created_at
FROM purchase_orders
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
```

Cursor chứa `lastCreatedAt` và `lastId` của hàng cuối trang trước. Query không dùng OFFSET lớn.

Keyset phù hợp với việc đi tiếp tuần tự, nhưng không thuận tiện để nhảy thẳng đến trang bất kỳ. Đây là một lựa chọn kiến trúc khác, không phải cú pháp thay thế đơn giản cho mọi use case OFFSET.

## 10. Sort động trong SQL phân trang

Một câu SQL có thể có ORDER BY cố định:

```sql
ORDER BY created_at DESC, id DESC
```

Nếu API cho client chọn sort field, không thể bind tên cột như một giá trị:

```sql
-- Không dùng cách này để thay tên cột:
ORDER BY :sortColumn;
```

Named parameter chỉ bind giá trị. Nó không thay thế identifier, keyword hoặc đoạn cú pháp SQL.

Không nối trực tiếp chuỗi client:

```java
String sql = "SELECT ... ORDER BY " + request.sortBy();
```

Thay vào đó, chuyển sort key thành enum/allowlist:

```java
public enum OrderSortField {
    CREATED_AT,
    ORDER_NUMBER,
    STATUS
}

public enum Direction {
    ASC,
    DESC
}
```

```java
private String toColumn(OrderSortField field) {
    return switch (field) {
        case CREATED_AT -> "o.created_at";
        case ORDER_NUMBER -> "o.order_number";
        case STATUS -> "o.status";
    };
}

private String toDirection(Direction direction) {
    return switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };
}
```

Khi tạo SQL, chỉ ghép các identifier đã được code kiểm soát. Các giá trị như status, limit và offset vẫn phải bind qua parameter.

Thêm tie-breaker:

```sql
ORDER BY o.created_at DESC, o.id DESC
```

Nếu sort field thay đổi, tie-breaker cũng cần được thiết kế sao cho tạo thứ tự xác định.

## 11. Validation và an toàn cho tham số phân trang

SQL parameter binding ngăn dữ liệu đầu vào trở thành cú pháp SQL, nhưng không tự bảo vệ ứng dụng khỏi các giá trị phân trang vô lý.

### 11.1. Kiểm tra page và size

```java
public record PageInput(int page, int size) {}

public long calculateOffset(PageInput input) {
    if (input.page() < 0) {
        throw new IllegalArgumentException("Page must be >= 0");
    }

    if (input.size() < 1 || input.size() > 100) {
        throw new IllegalArgumentException("Size must be between 1 and 100");
    }

    return (long) input.page() * input.size();
}
```

Nếu API dùng page number bắt đầu từ 1, validation và phép đổi sang zero-based cần thực hiện trước khi tính offset.

### 11.2. Tránh overflow

Nếu nhân hai giá trị `int` trước khi chuyển kiểu, phép nhân có thể overflow:

```java
int page = 100_000;
int size = 100_000;

// Có nguy cơ overflow int trước khi gán vào long:
long wrongOffset = page * size;

// Chuyển một toán hạng sang long trước khi nhân:
long offset = (long) page * size;
```

Không chỉ kiểm tra âm; cần giới hạn kích thước và offset theo yêu cầu hệ thống và khả năng database.

### 11.3. Bind parameter cho dữ liệu, allowlist cho identifier

| Thành phần | Cách truyền an toàn |
|---|---|
| Status, customer ID, ngày lọc | Named/positional bind parameter |
| Limit, offset | Bind parameter nếu dialect/driver hỗ trợ |
| Tên cột trong ORDER BY | Allowlist/enum do ứng dụng kiểm soát |
| ASC/DESC | Enum hoặc lựa chọn cố định |
| Tên bảng/schema | Cấu hình đáng tin cậy, không nhận raw request |

## 12. Tổ chức kết quả phân trang trong Java

Nếu custom repository trả về `List<T>`, service có thể tự đóng gói metadata.

Ví dụ response:

```java
public record PageResult<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    long totalPages
) {}
```

Service:

```java
public PageResult<OrderSummary> findOrderPage(
        String status,
        int page,
        int size) {

    if (page < 0 || size < 1 || size > 100) {
        throw new IllegalArgumentException("Invalid page request");
    }

    long offset = (long) page * size;

    List<OrderSummary> content =
        readRepository.findPage(status, size, offset);

    long total = readRepository.countByStatus(status);

    long totalPages = total / size
        + (total % size == 0 ? 0 : 1);

    return new PageResult<>(
        content,
        page,
        size,
        total,
        totalPages
    );
}
```

`PageResult` là DTO API do ứng dụng định nghĩa. Nó không tự động được Spring Data JDBC tạo chỉ vì SQL có LIMIT/OFFSET.

Nếu không cần tổng số hàng, có thể thiết kế response nhẹ hơn:

```java
public record CursorPage<T>(
    List<T> content,
    boolean hasNext
) {}
```

Trong trường hợp này, query lấy `size + 1` hàng để xác định `hasNext` mà không cần count.

## 13. Kiểm thử truy vấn phân trang theo dialect

SQL phân trang phụ thuộc database, vì vậy cần kiểm thử với đúng hệ quản trị và phiên bản mà ứng dụng sử dụng.

Một bộ dữ liệu kiểm thử nên có:

- Nhiều hàng hơn page size.
- Nhiều hàng có cùng sort key để xác nhận tie-breaker.
- Trạng thái/filter khác nhau.
- Một tập rỗng.
- Trang đầu, trang giữa, trang vượt quá dữ liệu.
- Các giá trị page/size không hợp lệ ở service.

Ví dụ kỳ vọng:

| Trường hợp | Page | Size | Kỳ vọng |
|---|---:|---:|---|
| Trang đầu | 0 | 2 | 2 hàng đầu theo ORDER BY |
| Trang giữa | 1 | 2 | 2 hàng tiếp theo |
| Trang cuối một phần | 2 | 2 | 1 hàng nếu tổng là 5 |
| Trang vượt dữ liệu | 3 | 2 | Danh sách rỗng |
| Size bằng 0 | 0 | 0 | Validation thất bại |
| Offset âm | — | — | Validation thất bại |
| Không có hàng phù hợp | 0 | 20 | Danh sách rỗng, count bằng 0 |

Đừng chỉ kiểm thử bằng H2 nếu production chạy PostgreSQL, SQL Server hoặc Oracle. H2 có thể không tái hiện đầy đủ cú pháp và hành vi của database đích. Dùng Testcontainers hoặc môi trường integration test có đúng database/dialect để kiểm tra câu SQL thực tế.

### 13.1. Kiểm tra thứ tự khi giá trị trùng nhau

Tạo nhiều đơn có cùng `created_at` và xác nhận `id DESC` quyết định thứ tự giữa chúng. Nếu bỏ tie-breaker, test có thể lúc đúng lúc sai tùy query plan và dữ liệu.

### 13.2. Kiểm tra count và nội dung

Đối chiếu:

- Tổng số hàng count trả về.
- Tổng số phần tử ghép qua các trang khi dataset không thay đổi.
- Không trùng và không thiếu ID giữa các trang.
- Bộ lọc của count query khớp với data query.

Với dữ liệu thay đổi đồng thời, cần kiểm thử theo isolation/consistency contract của ứng dụng thay vì đòi hỏi offset pagination luôn tạo snapshot xuyên nhiều request.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SQL chạy trên PostgreSQL nhưng lỗi trên SQL Server | Dùng sai cú pháp LIMIT/OFFSET | Dùng OFFSET/FETCH theo dialect |
| Trang đầu bị thiếu hàng | Nhầm page number bắt đầu từ 1 với 0 | Chuẩn hóa page number trước khi tính offset |
| Trang bị lặp hoặc thiếu hàng | Thiếu ORDER BY ổn định hoặc dữ liệu thay đổi giữa request | Thêm tie-breaker; cân nhắc cursor/snapshot |
| Trang JOIN bị cắt mất item | LIMIT áp dụng lên hàng JOIN thay vì root | Phân trang ID root trước rồi mới JOIN |
| Tổng số trang không khớp | Count query thiếu filter hoặc đếm sai grain | Đồng bộ điều kiện và COUNT(DISTINCT) khi cần |
| Trang sâu rất chậm | OFFSET lớn | Dùng index phù hợp hoặc keyset pagination |
| Database từ chối tham số limit | Driver/dialect không hỗ trợ binding theo cách đang dùng | Kiểm tra driver, kiểu tham số và cú pháp cụ thể |
| SQL injection qua sort | Nối raw identifier từ request | Allowlist cột và hướng sort |
| Page size quá lớn | Không validation đầu vào | Đặt size tối đa ở API/service |
| Truy vấn không có thứ tự ổn định | Không có ORDER BY hoặc sort key bị trùng | Thêm khóa duy nhất làm tie-breaker |
| H2 test chạy nhưng production lỗi | Test database khác dialect production | Integration test với database thật/đúng version |

## 15. Bài thực hành

Giả sử bảng `purchase_orders` có các cột `id`, `order_number`, `status`, `customer_id` và `created_at`. Database của ứng dụng là PostgreSQL.

### Bài 1. Lấy trang đầu tiên

Viết SQL lấy tối đa 10 đơn `PAID` mới nhất.

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit OFFSET :offset;
```

Tham số: `status = 'PAID'`, `limit = 10`, `offset = 0`.

### Bài 2. Lấy trang thứ tư

Page number bắt đầu từ 0, size bằng 25. Offset là bao nhiêu?

**Đáp án:** `offset = 3 × 25 = 75`. Query dùng `LIMIT 25 OFFSET 75`.

### Bài 3. Chuyển sang SQL Server

Cùng ý nghĩa limit 25 và offset 75, cú pháp SQL Server 2012+ là:

```sql
SELECT id, order_number, status, created_at
FROM purchase_orders
WHERE status = @status
ORDER BY created_at DESC, id DESC
OFFSET @offset ROWS
FETCH NEXT @limit ROWS ONLY;
```

Trong Spring named parameter query, sử dụng placeholder theo cơ chế của Spring, ví dụ `:status`, `:offset` và `:limit`.

### Bài 4. Viết count query

Data query lọc theo `status` và `customer_id`. Count query phải có những điều kiện nào?

**Đáp án:** Cả hai điều kiện phải được giữ:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE status = :status
  AND customer_id = :customerId;
```

### Bài 5. Phân trang đơn hàng có dòng sản phẩm

Một đơn có 5 item. Vì sao `LIMIT 10` trên kết quả JOIN có thể không trả về 10 đơn?

**Đáp án:** LIMIT giới hạn hàng JOIN, mỗi đơn có thể tạo nhiều hàng. Hãy phân trang ID đơn trước rồi JOIN các item của những đơn đó.

### Bài 6. Sort an toàn

API nhận `sortBy=createdAt` và `direction=desc`. Có nên nối hai chuỗi này vào SQL không?

**Đáp án:** Không. Chuyển sort key sang enum/allowlist và direction sang ASC/DESC cố định; chỉ ghép identifier đã được code kiểm soát.

### Bài 7. Offset lớn

Một trang yêu cầu `LIMIT 50 OFFSET 900000` và truy vấn chậm. Có thể cân nhắc hướng nào?

**Đáp án:** Kiểm tra index và query plan; nếu người dùng duyệt tuần tự, cân nhắc keyset pagination dựa trên khóa sắp xếp và ID thay vì bỏ qua một offset rất lớn.

## 16. Điều cần ghi nhớ

1. **LIMIT** giới hạn số hàng; **OFFSET** bỏ qua hàng đầu; **ORDER BY** quyết định thứ tự trước khi phân trang.
2. Luôn có thứ tự ổn định, thường thêm primary key làm tie-breaker.
3. SQL viết tay phải dùng đúng cú pháp của database: PostgreSQL/MySQL thường dùng LIMIT/OFFSET; SQL Server và Oracle hiện đại dùng OFFSET/FETCH.
4. Trong Spring Data JDBC, bind filter, limit và offset bằng named/positional parameters nếu driver/dialect hỗ trợ.
5. Tính offset bằng `page × size`, chuẩn hóa page number và dùng `long` để tránh overflow.
6. Count query phải dùng cùng filter và đếm đúng mức dữ liệu mà trang trả về.
7. Khi JOIN một-nhiều, phân trang root trước rồi mới lấy dữ liệu con nếu mục tiêu là một trang gồm các aggregate root.
8. OFFSET lớn có thể chậm; keyset pagination phù hợp với việc duyệt tuần tự tập dữ liệu lớn.
9. Không nối raw sort field từ request vào SQL; dùng allowlist cho identifier và direction.
10. Kiểm thử SQL phân trang với đúng database/dialect production.

### Tài liệu tham khảo

- [PostgreSQL — LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html)
- [MySQL — LIMIT Query Optimization](https://dev.mysql.com/doc/refman/8.4/en/limit-optimization.html)
- [SQL Server — ORDER BY Clause (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/queries/select-order-by-clause-transact-sql)
- [Oracle — SELECT and row limiting clause](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/SELECT.html)
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html)

Khi áp dụng, hãy xác nhận cú pháp theo phiên bản database và JDBC driver đang chạy. Với SQL phân trang tự viết, ứng dụng chịu trách nhiệm thể hiện giới hạn, offset, thứ tự và count query một cách tường minh.
