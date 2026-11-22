# SQL injection, tham số hóa và tên đối tượng động trong PostgreSQL

## 1. Một chuỗi đầu vào có thể trở thành câu lệnh SQL như thế nào?

Giả sử API cho phép tìm đơn hàng theo mã khách hàng:

```text
GET /orders?customer_code=O'Reilly
```

Nếu ứng dụng tạo SQL bằng cách nối chuỗi:

```java
String sql =
    "SELECT order_id, amount FROM app.orders " +
    "WHERE customer_code = '" + userInput + "'";
```

ký tự `'` trong tên `O'Reilly` làm hỏng cấu trúc string literal. Tệ hơn, một giá trị được tạo để chứa thêm cú pháp SQL có thể làm thay đổi điều kiện `WHERE`, biểu thức, bảng được truy vấn hoặc thao tác được thực hiện, tùy đường đi của input và quyền của kết nối.

**SQL injection** xảy ra khi dữ liệu do một bên không đáng tin cậy kiểm soát bị đưa vào **vị trí cú pháp SQL** mà không được ràng buộc đúng. Lỗi cốt lõi không chỉ là thiếu escape dấu nháy; đó là việc nhầm lẫn giữa **mã lệnh** và **giá trị**.

```text
Đầu vào từ người dùng / file / request / database
                       |
                       v
             Xây dựng câu SQL
                       |
            +----------+-----------+
            |                      |
       Nối thẳng text        Bind parameter
            |                      |
  Dữ liệu có thể trở       Dữ liệu giữ vai trò
    thành cú pháp SQL          data value
            |                      |
  Injection / query sai      SQL cố định, dễ audit
            |
            v
       Có thể vượt WHERE, lộ hoặc sửa dữ liệu
```

Nhưng parameter binding **không thể đại diện cho tên bảng/cột/schema hoặc một keyword SQL**. Nếu ứng dụng cần chọn đối tượng động, ta phải sử dụng **allowlist**, quote định danh đúng cách và kiểm tra quyền riêng.

> **Nguyên tắc trung tâm:** dùng câu SQL cố định và parameter binding cho **giá trị**; chỉ tạo SQL động khi cấu trúc thật sự cần đổi; với **định danh động**, chọn từ allowlist đáng tin và quote bằng `format('%I', ...)` hoặc `quote_ident(...)`. Quoting không thay thế kiểm tra quyền.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện SQL injection từ việc nối input vào SQL, kể cả khi input đến từ database hoặc cấu hình.
2. Phân biệt SQL **value**, **identifier** và **syntax fragment**.
3. Dùng PostgreSQL `PREPARE`/`EXECUTE` để truyền tham số thay vì dựng literal.
4. Dùng JDBC `PreparedStatement` và `setString`, `setInt`, `setBigDecimal`, `setArray`.
5. Viết PostgreSQL PL/pgSQL `EXECUTE ... USING` đúng kiểu.
6. Biết vì sao placeholder không thay được tên bảng/cột, thứ tự `ASC`/`DESC` hoặc biểu thức SQL.
7. Dùng `quote_ident`, `quote_literal`, `quote_nullable` và `format('%I')`/`format('%L')`.
8. Phân biệt nguy cơ của `format('%s')` khi nhận raw input.
9. Quote **schema** và **table** riêng bằng `%I.%I`.
10. Tạo allowlist tên bảng, cột, chiều sort và loại phép lọc.
11. Tránh logic injection qua `OR`, nối WHERE và filter tùy chọn.
12. Hiểu cách xử lý `NULL` trong SQL động và `IS NOT DISTINCT FROM`.
13. Phân biệt SQL injection với `LIKE`/`ILIKE` wildcard injection và regex abuse.
14. Sử dụng full-text search với `websearch_to_tsquery` mà không ghép cú pháp tự do.
15. Thiết kế multi-tenant query có authorization không phụ thuộc tham số do caller tự khai báo.
16. Hiểu tác động của `SECURITY DEFINER`, RLS và `search_path` đến phạm vi hậu quả.
17. Biết vì sao tạo nhiều SQL statements hoặc utility DDL từ request nguy hiểm hơn truy vấn read-only.
18. Phân biệt safe SQL syntax với safe business authorization.
19. Kiểm thử dấu nháy, Unicode, `NULL`, identifier lạ, schema shadowing và quyền hạn chế.
20. Đánh giá chi phí plan/index, logging và vận hành sau khi đã giải quyết injection.

## 3. Mô hình đe dọa: input không tin cậy đến từ đâu?

Không phải chỉ HTTP query string mới gây injection. Những nguồn có thể bị kiểm soát hoặc nhiễm dữ liệu bất thường gồm:

- Request body, URL parameters, headers hoặc cookies.
- Form nhập tên, từ khóa tìm kiếm, mô tả đơn hàng.
- Nội dung CSV/Excel/import jobs hoặc đối tác tích hợp.
- Thông điệp queue, webhook và log-derived data.
- Text đã nằm trong database từ một bước trước.
- User-configured report columns, sort rules hoặc filter definitions.
- Tên schema/table do một dịch vụ khác cung cấp.
- Custom session variables nếu caller có thể `SET` chúng tùy ý.

### 3.1. First-order và second-order injection

**First-order:** input được ghép vào SQL ngay trong request hiện tại.

**Second-order:** dữ liệu được lưu an toàn lúc đầu, nhưng về sau được đọc lại và ghép thành SQL text tại một migration, báo cáo hoặc routine khác.

Ví dụ: tên hiển thị của khách hàng được lưu bằng prepared statement; một báo cáo sau đó lại ghép tên đó vào SQL mà không bind. Việc “đã được lưu trong database” **không khiến chuỗi trở nên đáng tin cậy**.

### 3.2. Hậu quả phụ thuộc quyền của DB role

Một injection có thể dẫn đến:

- Trả quá nhiều rows vì điều kiện WHERE bị thay đổi.
- Đọc dữ liệu ở tenant khác.
- Suy luận tồn tại/không tồn tại dữ liệu qua lỗi hoặc khác biệt thời gian.
- Gọi một hàm SQL không dự kiến.
- Sửa/xóa dữ liệu nếu quyền và đường thực thi cho phép.
- Truy cập objects nhạy cảm qua một `SECURITY DEFINER` routine.
- Tạo truy vấn tốn tài nguyên, gây tăng latency/DoS.

Không phải mọi input xấu đều có thể thực thi nhiều statements hoặc thay đổi dữ liệu. Điều đó còn phụ thuộc cách câu SQL được gửi, driver/protocol, loại query và quyền của role. **Đừng xem khả năng “chỉ một statement” là biện pháp chống injection.**

### 3.3. Injection khác lỗi phân quyền

Một câu SQL được bind **hoàn toàn đúng** vẫn có thể trả dữ liệu sai phạm vi nếu ứng dụng cho người dùng truyền `tenant_id` của tổ chức khác. Đó là **authorization flaw**, không phải SQL syntax injection.

## 4. Ba nhóm thành phần phải được xử lý khác nhau

| Thành phần | Ví dụ | Phương án an toàn |
| --- | --- | --- |
| Data value | Mã khách hàng, giá, ngày, trạng thái | Bind parameter: `$1`, JDBC `?`, PL/pgSQL `USING` |
| Identifier | Tên schema, bảng, cột | Allowlist/mapping + `%I` hoặc `quote_ident` |
| SQL fragment | `ASC`, `DESC`, `NULLS LAST`, toán tử, JOIN shape | Lựa chọn cố định từ code, không nhận raw fragment |
| DDL literal khi không bind được | Comment, giá trị utility command | `%L`/`quote_nullable` khi buộc phải dựng SQL text |
| Search pattern | `LIKE`, regex, FTS input | Bind dữ liệu **và** áp semantics/giới hạn riêng |
| Authorization scope | Tenant, principal, role, quyền object | Context xác thực + kiểm tra quyền/RLS phù hợp |

### 4.1. Một cột không phải một giá trị

```sql
SELECT status FROM some_table;
```

đọc dữ liệu của cột `status`.

```sql
SELECT 'status' FROM some_table;
```

trả một literal text `status` trên từng row. Hai câu không tương đương.

### 4.2. Hai loại dấu nháy

- `'O''Reilly'` là **string literal** chứa dấu nháy đơn.
- `"Order Details"` là **quoted identifier** chứa khoảng trắng.
- `"status"` là identifier, còn `'status'` là literal.
- `quote_ident` và `%I` dành cho identifiers; `quote_literal` và `%L` dành cho literals.

## 5. Lab PostgreSQL có dữ liệu nhiều tenant

Chỉ thực hành trong database dùng để học, không tạo bảng và chạy ví dụ DDL trên production.

### 5.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS sqli388;

CREATE TABLE sqli388.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_code text NOT NULL,
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    description text NOT NULL,
    note text,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL
);

CREATE INDEX orders_tenant_customer_idx
ON sqli388.orders (tenant_id, customer_code);

CREATE INDEX orders_tenant_status_created_idx
ON sqli388.orders (tenant_id, status, created_at DESC);
```

### 5.2. Dữ liệu minh họa

```sql
INSERT INTO sqli388.orders (
    tenant_id, customer_code, status,
    description, note, amount, created_at
)
VALUES
    (10, 'ALICE', 'NEW',
        'PostgreSQL beginner handbook', 'First order',
        150.00, timestamptz '2026-01-02 09:00:00+00'),
    (10, 'O''Reilly', 'PAID',
        'SQL performance workshop', 'Customer''s request',
        330.00, timestamptz '2026-01-03 10:00:00+00'),
    (10, 'A%_B', 'NEW',
        'Search syntax class', NULL,
        35.00, timestamptz '2026-01-04 11:00:00+00'),
    (10, 'VN-ĐỎ', 'PAID',
        'Unicode and collation', 'Đã thanh toán',
        90.00, timestamptz '2026-01-05 12:00:00+00'),
    (10, 'x'' OR TRUE --', 'NEW',
        'Untrusted input as plain data',
        'Safe when bound', 20.00,
        timestamptz '2026-01-06 13:00:00+00'),
    (20, 'ALICE', 'PAID',
        'Another tenant''s order', 'Private scope',
        999.00, timestamptz '2026-01-07 14:00:00+00'),
    (20, 'O''Reilly', 'CANCELLED',
        'Cancelled order', NULL,
        10.00, timestamptz '2026-01-08 15:00:00+00'),
    (20, 'BOB', 'NEW',
        'Database indexing', 'Private scope',
        80.00, timestamptz '2026-01-09 16:00:00+00');
```

Hai tenants có cùng `customer_code`. Mã `x' OR TRUE --` là **dữ liệu text nằm trong bảng**, không phải cú pháp SQL.

### 5.3. Bảng archive để thực hành chọn bảng động

```sql
CREATE TABLE sqli388.orders_archive (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_code text NOT NULL,
    status text NOT NULL,
    description text NOT NULL,
    note text,
    amount numeric(12,2) NOT NULL,
    created_at timestamptz NOT NULL
);

INSERT INTO sqli388.orders_archive (
    order_id, tenant_id, customer_code,
    status, description, note, amount, created_at
)
VALUES
    (1001, 10, 'ALICE', 'PAID',
        'Old order', NULL, 10.00,
        timestamptz '2025-01-01 00:00:00+00'),
    (1002, 20, 'BOB', 'PAID',
        'Old order', NULL, 20.00,
        timestamptz '2025-01-02 00:00:00+00');

ANALYZE sqli388.orders;
ANALYZE sqli388.orders_archive;
```

### 5.4. Kiểm tra tập dữ liệu

```sql
SELECT tenant_id, COUNT(*) AS orders_count
FROM sqli388.orders
GROUP BY tenant_id
ORDER BY tenant_id;

SELECT
    order_id, tenant_id, customer_code, amount
FROM sqli388.orders
ORDER BY order_id;
```

Trong lab, tenant 10 có **5** đơn ở `orders` và tenant 20 có **3** đơn. Các mã chứa dấu nháy, Unicode và ký tự `%`/`_` giúp kiểm thử các ranh giới dữ liệu.

## 6. Mẫu nguy hiểm: nối input vào SQL literal

Một ứng dụng có thể xây:

```java
String sql =
    "SELECT order_id FROM sqli388.orders " +
    "WHERE customer_code = '" + customerCode + "'";
```

Nếu `customerCode = "O'Reilly"`, kết quả là SQL text có dấu nháy sai.

Nếu input chứa các token giống điều kiện SQL, phần sau có thể được SQL parser diễn giải như **cú pháp**, thay vì một mã khách hàng.

### 6.1. Không chạy query dựng sai để chứng minh hậu quả

Việc phân tích string đã đủ chứng minh ranh giới code/data bị phá. Không cần tạo payload có tác dụng xóa dữ liệu hoặc nâng quyền.

### 6.2. Tự thay dấu nháy đơn không phải giải pháp kiến trúc

Một cách sửa vội là:

```java
String escaped = customerCode.replace("'", "''");
```

Trong một tình huống string literal đơn giản nó có thể giúp tạo literal theo SQL quoting, nhưng hệ thống vẫn dễ sai khi:

- Code sau này cho phép tên bảng/cột.
- Input vào `ORDER BY` hay một biểu thức SQL.
- Có nhiều lớp escape: Java → SQL → LIKE/regex.
- Một statement được xây bằng nhiều chuỗi/encoding khác nhau.
- Một nhánh query quên escape.
- Input `NULL`, binary/typed values hoặc date/time phức tạp.

Đừng tự phát minh một “SQL sanitizer” đa năng. **Bind parameters** mới là mặc định cho values.

## 7. Câu SQL an toàn với PostgreSQL `PREPARE`

PostgreSQL hỗ trợ parameter placeholders trong prepared statements.

```sql
PREPARE find_orders(integer, text) AS
SELECT
    order_id,
    tenant_id,
    customer_code,
    status,
    amount
FROM sqli388.orders
WHERE tenant_id = $1
  AND customer_code = $2
ORDER BY order_id;

EXECUTE find_orders(10, 'O''Reilly');

DEALLOCATE find_orders;
```

Ở đây:

- `$1` là một `integer`.
- `$2` là một `text`.
- SQL structure đã được khai báo sẵn, values không được phép thay đổi cấu trúc.
- `EXECUTE find_orders(...)` là cú pháp SQL để thực thi **named prepared statement** trong session.

### 7.1. Vì sao vẫn thấy hai dấu nháy khi thử trong SQL script?

Dòng `EXECUTE find_orders(10, 'O''Reilly')` là **một SQL statement bạn tự gõ**, nên literal trong script phải tuân theo SQL syntax. Đây không phải cách ứng dụng production cần tự tạo chuỗi parameter.

Trong JDBC, ứng dụng sẽ gọi `ps.setString(2, customerCode)`, không cần tự escape `O'Reilly`.

### 7.2. Cần kiểm tra tenant scope riêng

Query bind cả `$1` và `$2`, nhưng nếu một API cho caller tự đổi `$1` từ 10 sang 20, nó vẫn có thể truy cập tenant 20 nếu database role được phép.

**Bind chống injection, không chứng thực quyền dùng tenant ID.**

### 7.3. Prepared statement chỉ là một cách biểu diễn

Bên trong ứng dụng, giao thức extended query và JDBC driver có thể quản lý việc chuẩn bị/bind khác câu SQL `PREPARE` thủ công. Không bắt buộc gọi SQL `PREPARE` trước mọi JDBC query.

## 8. JDBC PreparedStatement: lựa chọn phổ biến trong Java

Ví dụ Java 17+:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderSearch {
    private final DataSource dataSource;

    public OrderSearch(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void findByCustomer(
        int authenticatedTenantId,
        String customerCode
    ) throws SQLException {

        String sql = """
            SELECT order_id, customer_code, status, amount
            FROM sqli388.orders
            WHERE tenant_id = ?
              AND customer_code = ?
            ORDER BY order_id
            LIMIT 100
            """;

        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {

            ps.setInt(1, authenticatedTenantId);
            ps.setString(2, customerCode);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    System.out.println(
                        rs.getLong("order_id")
                        + " | " + rs.getString("customer_code")
                    );
                }
            }
        }
    }
}
```

### 8.1. Điều kiện tiên quyết về authorization

`authenticatedTenantId` phải được server lấy từ identity đã xác thực/ủy quyền. Không đơn thuần gọi:

```java
int authenticatedTenantId =
    Integer.parseInt(request.getParameter("tenant_id"));
```

rồi tin giá trị đó là phạm vi được phép.

### 8.2. `PreparedStatement` không phải String concatenation

Sai:

```java
String sql = "SELECT * FROM sqli388.orders " +
             "WHERE customer_code = '" + userInput + "'";
Statement s = conn.createStatement();
ResultSet rs = s.executeQuery(sql);
```

Đúng hơn:

```java
String sql = "SELECT * FROM sqli388.orders " +
             "WHERE customer_code = ?";
PreparedStatement ps = conn.prepareStatement(sql);
ps.setString(1, userInput);
```

### 8.3. Java parameter index bắt đầu từ 1

`setString(1, ...)` bind placeholder `?` thứ nhất, không bắt đầu từ 0.

### 8.4. Close resources

`try-with-resources` giúp giải phóng statement/result set/connection theo vòng đời cần thiết. Hãy tuân theo semantics của connection pool ứng dụng.

### 8.5. Không gửi nguyên SQL từ client

Không thiết kế API:

```text
POST /query
{"sql": "SELECT ..."}
```

rồi chạy chuỗi đó bằng role có nhiều quyền. SQL templates phải do server quản lý, không do caller cung cấp.

## 9. Parameterization giữ nguyên kiểu dữ liệu

Một lợi ích ngoài bảo mật là value được truyền với kiểu rõ ràng.

| Kiểu | PostgreSQL | JDBC |
| --- | --- | --- |
| ID | `bigint` | `setLong(...)` |
| Tenant ID | `integer` | `setInt(...)` |
| Customer code | `text` | `setString(...)` |
| Amount | `numeric` | `setBigDecimal(...)` |
| Boolean flag | `boolean` | `setBoolean(...)` |
| Date/time | `timestamptz` | Bind kiểu timestamp/time được driver hỗ trợ |
| NULL | Theo kiểu cột/parameter | `setNull(..., Types.XXX)` hoặc binding type phù hợp |

### 9.1. Không convert money bằng string

```java
String sql = "... WHERE amount >= " + userAmount;
```

có thể sai số/locale và đưa text vào SQL structure. Dùng `BigDecimal` và bind.

### 9.2. NULL cần kiểu thích hợp

Trong JDBC:

```java
ps.setNull(2, java.sql.Types.VARCHAR);
```

nếu vị trí parameter là string nullable. Với PostgreSQL cần type resolution đúng; đôi khi SQL cần cast tường minh như `?::text` để loại bỏ mơ hồ.

### 9.3. Parameterized không đồng nghĩa được dùng hết tài nguyên

`LIMIT ?` có thể bind một số rất lớn. Validate các tham số như page size, regex complexity, time range và số tags để tránh query quá đắt.

## 10. Nhiều giá trị trong `IN`: đừng nối danh sách raw

Một sai lầm:

```java
String sql =
    "SELECT * FROM sqli388.orders " +
    "WHERE status IN (" + csvStatuses + ")";
```

Nếu `csvStatuses` đến từ input, nó có thể biến thành raw SQL syntax.

### 10.1. Dùng ANY với PostgreSQL array

```sql
PREPARE find_by_status(integer, text[]) AS
SELECT order_id, status
FROM sqli388.orders
WHERE tenant_id = $1
  AND status = ANY($2)
ORDER BY order_id;

EXECUTE find_by_status(
    10,
    ARRAY['NEW', 'PAID']::text[]
);

DEALLOCATE find_by_status;
```

### 10.2. Java JDBC array

```java
String sql = """
    SELECT order_id, status
    FROM sqli388.orders
    WHERE tenant_id = ?
      AND status = ANY(?)
    ORDER BY order_id
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, authenticatedTenantId);

    java.sql.Array sqlArray = conn.createArrayOf(
        "text",
        new String[] {"NEW", "PAID"}
    );

    try {
        ps.setArray(2, sqlArray);
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getLong(1));
            }
        }
    } finally {
        sqlArray.free();
    }
}
```

Đoạn JDBC trên giả định `conn` đã được quản lý từ bên ngoài. Với các drivers khác, API/type details cần được kiểm tra; nguyên tắc là **truyền mảng như dữ liệu, không ghép SQL từ phần tử**.

### 10.3. Mảng rỗng và NULL khác nhau

- `status = ANY(ARRAY[]::text[])` không match hàng nào.
- `NULL::text[]` không mang cùng semantics.
- “Không chọn filter” là một policy ứng dụng khác, không nên tự đồng nhất với “không có giá trị nào được phép”.

### 10.4. Dynamic placeholders là phương án khác

Ứng dụng cũng có thể tạo số lượng `?` cố định theo độ dài danh sách và bind từng giá trị. Khi làm vậy, chỉ tạo placeholder tokens theo **số lượng đã validate**, không ghép raw elements.

## 11. Dùng parameter cho ngày, khoảng tiền và phân trang

Ví dụ:

```sql
PREPARE list_orders(
    integer, numeric, numeric, timestamptz, integer
) AS
SELECT
    order_id,
    amount,
    created_at
FROM sqli388.orders
WHERE tenant_id = $1
  AND amount >= $2
  AND amount <= $3
  AND created_at >= $4
ORDER BY created_at DESC, order_id DESC
LIMIT $5;

EXECUTE list_orders(
    10,
    20.00,
    400.00,
    timestamptz '2026-01-01 00:00:00+00',
    20
);

DEALLOCATE list_orders;
```

### 11.1. Bind không thay input validation

- `min_amount <= max_amount`.
- Amount phải cùng đơn vị tiền/currency policy.
- `page_size` trong giới hạn cho phép.
- Timestamps phải được xử lý đúng timezone và semantics.
- Tenant phải đến từ ngữ cảnh đáng tin.

### 11.2. Không lấy integer trực tiếp từ raw string để ghép ORDER BY

Một số người cho rằng numeric không thể injection nên có thể chèn raw input. Nhưng một **chuỗi** trông giống số vẫn là raw SQL text nếu không parse và validate. Dùng bind cho values.

### 11.3. `ORDER BY` cần total order

Hai hàng cùng `created_at` có thể đổi thứ tự nếu không thêm tie-breaker. `order_id DESC` tạo thứ tự xác định trong cùng snapshot.

## 12. Lỗi logic trong `AND`/`OR` cũng làm lộ dữ liệu

Không phải mọi lỗi truy vấn làm lộ dữ liệu đều là SQL injection.

Sai:

```sql
SELECT order_id, tenant_id, customer_code
FROM sqli388.orders
WHERE tenant_id = 10
  AND status = 'PAID'
   OR customer_code = 'ALICE';
```

Do `AND` có độ ưu tiên cao hơn `OR`, câu này tương đương:

```text
(tenant_id = 10 AND status = 'PAID')
OR customer_code = 'ALICE'
```

Nó có thể trả đơn hàng `ALICE` của tenant 20.

Đúng:

```sql
SELECT order_id, tenant_id, customer_code
FROM sqli388.orders
WHERE tenant_id = 10
  AND (
      status = 'PAID'
      OR customer_code = 'ALICE'
  );
```

### 12.1. Parameterization không sửa parentheses sai

Ngay cả khi dùng `tenant_id = $1` và `customer_code = $2`, một `OR` không được nhóm vẫn có thể phá scope.

### 12.2. Mandatory predicates phải áp lên mọi nhánh

Một dynamic query builder nên có cấu trúc:

```sql
WHERE tenant_id = $1
  AND (
      status = $2
      OR customer_code = $3
  )
```

Không để một bộ lọc tùy chọn nối thêm `OR...` ở cuối rồi vô hiệu hóa authorization.

### 12.3. Không lấy top N trước khi áp quyền

`LIMIT 20` trong CTE lấy raw candidates trước, rồi mới lọc tenant ở query ngoài, có thể trả thiếu top 20 hợp lệ. Đó là lỗi search/business semantics khác injection nhưng cũng ảnh hưởng bảo mật.

## 13. Khi nào phải dùng SQL động?

Cấu trúc cố định:

```sql
SELECT order_id
FROM sqli388.orders
WHERE tenant_id = $1
  AND customer_code = $2;
```

không cần dynamic SQL.

Những tình huống có thể cần SQL động:

- Người dùng chọn giữa bảng live và archive qua một enum được quản lý.
- Một công cụ nội bộ cần tạo DDL trong schema được phép.
- Dashboard cho phép chọn một số **cột** được whitelist.
- Một báo cáo có tập trường group/sort thay đổi theo options.
- Migration chọn partition được xác minh từ hệ thống metadata.

### 13.1. Đừng dùng SQL động chỉ vì nhìn “linh hoạt”

Nó có thể tăng:

- Khó khăn khi review và test.
- Rủi ro thiếu một mandatory filter.
- Planning overhead hoặc plan differences.
- Bề mặt SQL injection và object authorization.
- Độ phức tạp logging/observability.

### 13.2. Dynamic SQL có thể an toàn

Sử dụng:

1. SQL template cố định.
2. Identifiers từ allowlist rồi `%I`.
3. Data values qua bind/`USING`.
4. Quyền DB role tối thiểu.
5. Input validation và business authorization.

## 14. PL/pgSQL `EXECUTE ... USING`

Trong PostgreSQL PL/pgSQL:

```sql
EXECUTE command_string
    [INTO [STRICT] target]
    [USING expression [, ...]];
```

Ví dụ an toàn trong body một function:

```sql
EXECUTE
    'SELECT COUNT(*)
     FROM sqli388.orders
     WHERE tenant_id = $1
       AND customer_code = $2'
INTO v_count
USING p_tenant_id, p_customer_code;
```

### 14.1. Hai cách dùng từ `EXECUTE`

- SQL `EXECUTE prepared_name(arguments)`: chạy named prepared statement đã `PREPARE`.
- PL/pgSQL `EXECUTE command_string USING ...`: chạy câu SQL **được tạo dưới dạng text**.

Không copy trực tiếp `INTO local_variable USING ...` ra ngoài PL/pgSQL và kỳ vọng nó là SQL prepared execution.

### 14.2. Parameter giữ nguyên vai trò dữ liệu

`$1` và `$2` trong dynamic command đại diện cho data values ở các vị trí cho phép. Dấu nháy đơn trong `p_customer_code` không trở thành SQL syntax.

### 14.3. NULL không làm command string thành NULL

`USING NULL::text` là một parameter value hợp lệ. Khác với việc nối `quote_literal(NULL)` làm cả SQL string trở thành NULL.

### 14.4. Khả năng áp dụng

Data parameters trong PL/pgSQL dynamic SQL được hỗ trợ cho các **optimizable SQL commands** như `SELECT`, `INSERT`, `UPDATE`, `DELETE` và `MERGE` theo các phiên bản tương ứng.

Một số **utility statements** không thể dùng parameter placeholders ở vị trí muốn truyền giá trị; lúc đó cần tạo SQL text bằng `format` với quoting đúng.

## 15. Chạy một function hoàn chỉnh có USING

```sql
CREATE OR REPLACE FUNCTION sqli388.count_by_customer(
    p_tenant_id integer,
    p_customer_code text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, sqli388, pg_temp
AS $fn$
DECLARE
    v_count bigint;
BEGIN
    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant id'
            USING ERRCODE = '22023';
    END IF;

    EXECUTE
        'SELECT COUNT(*)
         FROM sqli388.orders
         WHERE tenant_id = $1
           AND customer_code = $2'
    INTO v_count
    USING p_tenant_id, p_customer_code;

    RETURN v_count;
END;
$fn$;
```

Thử:

```sql
SELECT sqli388.count_by_customer(10, 'O''Reilly');
SELECT sqli388.count_by_customer(10, 'A%_B');
SELECT sqli388.count_by_customer(10, 'x'' OR TRUE --');
SELECT sqli388.count_by_customer(20, 'O''Reilly');
```

Tất cả được hiểu là **so khớp chính xác một text value**. Không có đoạn `OR TRUE` nào được chuyển thành logic SQL.

### 15.1. Vì sao dùng SECURITY INVOKER?

Hàm không cần đặc quyền vượt quyền trực tiếp của người gọi. Caller cần các quyền truy cập bảng phù hợp theo PostgreSQL.

### 15.2. Vì sao vẫn có tenant parameter?

Đây là **lab về cách bind**. Trong public endpoint thật, `p_tenant_id` phải được cấp/kiểm tra từ nguồn quyền đáng tin hoặc được kiểm soát bằng RLS, không do caller tự chọn mọi tenant.

### 15.3. Khi có thể viết SQL tĩnh

Chúng ta dùng `EXECUTE` để học kỹ thuật. Trong production, vì tên bảng/cột không đổi, thường viết:

```sql
SELECT COUNT(*)
INTO v_count
FROM sqli388.orders
WHERE tenant_id = p_tenant_id
  AND customer_code = p_customer_code;
```

đơn giản hơn, và PL/pgSQL có thể dùng plan caching theo semantics thích hợp.

## 16. Tên bảng không thể thay bằng `$1`

Một ví dụ sai ý định:

```sql
EXECUTE
    'SELECT COUNT(*) FROM $1'
INTO v_count
USING p_table_name;
```

`$1` đại diện data value trong expression positions, **không phải table identifier** trong `FROM`.

Tương tự, JDBC:

```java
PreparedStatement ps =
    conn.prepareStatement("SELECT * FROM ?");
ps.setString(1, tableName);
```

không biến `?` thành tên bảng; cấu trúc này không phải cách bind identifier hợp lệ.

### 16.1. Vì sao không thể bind tên object như data?

SQL parser phải xác định structure/relations/columns/operations để lập kế hoạch câu SQL. Identifier thuộc phần cú pháp đó; parameter binding dành cho **giá trị** trong cấu trúc đã xác định.

### 16.2. Tên cột cũng không bind được

```sql
SELECT $1 FROM sqli388.orders;
```

với `$1='status'`, nếu expression có type hợp lệ, cho ra giá trị constant text `status` trên mỗi row chứ không lấy cột status.

### 16.3. Với object động phải quote identifier

Sử dụng `format('%I', ...)`, `quote_ident(...)` hoặc một mapping tương đương, **kèm allowlist**.

## 17. `quote_ident`: biểu diễn identifier đúng cú pháp

```sql
SELECT
    quote_ident('orders') AS simple_name,
    quote_ident('Order Details') AS spaced_name,
    quote_ident('select') AS keyword_name,
    quote_ident('MixedCase') AS mixed_case_name,
    quote_ident('has"quote') AS quoted_quote;
```

`quote_ident(text)` tạo text phù hợp khi chèn **một identifier** vào SQL.

### 17.1. Kết quả không phải lúc nào cũng có dấu `"`

`quote_ident('orders')` có thể trả `orders` vì tên này hợp lệ khi không quote.

`quote_ident('MixedCase')` cần double quotes để giữ case; PostgreSQL gấp unquoted identifiers về chữ thường.

### 17.2. Identifier chứa dấu double quote

`quote_ident` escape double quote bên trong bằng cách nhân đôi khi cần, tránh việc ký tự dữ liệu kết thúc identifier.

### 17.3. `quote_ident` không kiểm tra tồn tại

Nếu quote tên `'missing_table'`, PostgreSQL không tự tạo bảng đó. Dynamic statement vẫn có thể lỗi `relation does not exist`.

### 17.4. `quote_ident` không kiểm tra quyền

Một identifier hợp lệ có thể trỏ tới bảng/cột mà user **không được phép** xem. Quoting là an toàn cú pháp, không phải authorization.

## 18. `quote_literal` và `quote_nullable`

Khi **buộc** phải tạo SQL literal text, PostgreSQL có:

```sql
SELECT
    quote_literal('O''Reilly') AS safe_literal,
    quote_literal(42) AS number_literal,
    quote_nullable(NULL::text) AS null_token,
    quote_nullable('O''Reilly') AS safe_nullable_literal;
```

### 18.1. `quote_literal`

Tạo text biểu diễn SQL literal. Ví dụ `O'Reilly` được biểu diễn với dấu nháy đơn escape theo PostgreSQL.

Nhưng `quote_literal` là hàm **STRICT**: khi nhận SQL NULL, nó trả SQL NULL.

### 18.2. `quote_nullable`

Tạo literal text với giá trị không NULL; với SQL NULL, nó trả **text `NULL`** (SQL token, không phải chuỗi `'NULL'`).

### 18.3. Bẫy nối chuỗi khi dữ liệu NULL

```sql
SELECT
    'SELECT ' || quote_literal(NULL::text)
        AS whole_command;
```

`whole_command` là SQL NULL. Trong PL/pgSQL, `EXECUTE` với command string NULL sẽ báo lỗi.

### 18.4. `quote_nullable` giữ command string

```sql
SELECT
    'SELECT ' || quote_nullable(NULL::text)
        AS whole_command;
```

Lúc này output là SQL text `SELECT NULL`.

### 18.5. NULL trong WHERE vẫn là câu chuyện riêng

`WHERE note = NULL` cho UNKNOWN, không match các NULL rows. `quote_nullable` chỉ tạo text, **không sửa logic so sánh NULL**.

## 19. `format('%I')`, `format('%L')` và `format('%s')`

Đây là ba lựa chọn thường gặp khi xây SQL text:

| Specifier | Ý nghĩa | Có tự quote cho SQL không? |
| --- | --- | --- |
| `%I` | SQL identifier | Có, theo identifier rules |
| `%L` | SQL literal, gồm NULL | Có, theo literal rules |
| `%s` | Chèn text thông thường | **Không** |
| `%%` | Ký tự `%` của format string | Không liên quan SQL escaping |

### 19.1. Quote identifier

```sql
SELECT format(
    'SELECT %I FROM sqli388.orders',
    'customer_code'
);
```

Tạo source text tham chiếu một **cột**.

### 19.2. Quote literal

```sql
SELECT format(
    'SELECT * FROM sqli388.orders
     WHERE customer_code = %L',
    'O''Reilly'
);
```

Tạo source text với giá trị SQL literal.

### 19.3. %L xử lý NULL

```sql
SELECT format(
    'SELECT %L',
    NULL::text
);
```

Tạo text chứa SQL token `NULL`. `%I` thì không có “NULL identifier”: truyền NULL có thể gây lỗi.

### 19.4. %s không phải công cụ chống injection

Sai nếu raw user input được dùng ở vị trí câu lệnh:

```sql
format(
    'SELECT * FROM sqli388.orders ORDER BY %s',
    p_sort_expression
)
```

`%s` không quote như `%I`/`%L`, nên raw text có thể trở thành SQL expression hoặc fragment không mong muốn.

Chỉ dùng `%s` cho **fragment cố định do code chọn từ allowlist**, ví dụ `'ASC'` hoặc `'DESC'`.

### 19.5. Format positional arguments

```sql
SELECT format(
    'SELECT %1$I FROM %2$I.%3$I ORDER BY %1$I',
    'order_id',
    'sqli388',
    'orders'
);
```

`%1$I` tham chiếu argument thứ nhất ở hai nơi.

## 20. Định danh `schema.table` gồm hai identifiers

Sai:

```sql
SELECT format(
    'SELECT COUNT(*) FROM %I',
    'sqli388.orders'
);
```

Đây là **một** identifier chứa dấu chấm, tương ứng kiểu `"sqli388.orders"`, không phải relation `orders` trong schema `sqli388`.

Đúng:

```sql
SELECT format(
    'SELECT COUNT(*) FROM %I.%I',
    'sqli388',
    'orders'
);
```

### 20.1. Vì sao phải tách?

Dấu chấm giữa schema và relation là **syntax separator**. Mỗi thành phần là một identifier riêng, có quy tắc quote riêng.

### 20.2. Cột cũng có thể schema/table qualification

Trong SQL:

```sql
SELECT o.customer_code
FROM sqli388.orders AS o;
```

`o.customer_code` là cột từ alias `o`, không phải một identifier có dấu chấm trong tên. Nếu tạo dynamic alias/column, cần quote mỗi component đúng cách.

### 20.3. Dấu chấm trong identifier hợp lệ nhưng khác ý nghĩa

Một table có thể thực sự tên `"a.b"` trong một schema. Vì vậy, đừng cố loại bỏ dấu chấm bằng replace rồi xem chuỗi thành qualified name.

## 21. Allowlist: phòng thủ bắt buộc cho tên đối tượng động

Giả sử API báo cáo có hai lựa chọn:

- `current` tương ứng `sqli388.orders`.
- `archive` tương ứng `sqli388.orders_archive`.

Nếu cho client tự truyền `schema_name`/`table_name` tùy ý, `%I.%I` vẫn cho phép chọn một bảng **hợp lệ nhưng không được phép** khi routine chạy với quyền cao.

### 21.1. Mapping từ business option sang table name

Trong PL/pgSQL:

```sql
IF p_source IS NULL
   OR p_source NOT IN ('current', 'archive')
THEN
    RAISE EXCEPTION 'Unsupported source'
        USING ERRCODE = '22023';
END IF;

v_table_name := CASE p_source
    WHEN 'current' THEN 'orders'
    WHEN 'archive' THEN 'orders_archive'
END;
```

### 21.2. Sau đó quote từng identifier

```sql
EXECUTE format(
    'SELECT COUNT(*)
     FROM %I.%I
     WHERE tenant_id = $1',
    'sqli388',
    v_table_name
)
INTO v_count
USING p_tenant_id;
```

### 21.3. Hai tầng bảo vệ

- Allowlist quy định **được phép chọn object nào**.
- `%I` đảm bảo **object name được biểu diễn đúng cú pháp SQL**.

Thiếu một tầng vẫn có thể sai: chỉ allowlist nhưng nối identifiers không quote dễ lỗi với tên lạ; chỉ quote mà không allowlist dễ vượt quyền khi owner rộng.

## 22. Hàm chọn bảng động an toàn về syntax

```sql
CREATE OR REPLACE FUNCTION sqli388.count_from_source(
    p_source text,
    p_tenant_id integer
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, sqli388, pg_temp
AS $fn$
DECLARE
    v_table text;
    v_count bigint;
BEGIN
    IF p_source IS NULL
       OR p_source NOT IN ('current', 'archive')
    THEN
        RAISE EXCEPTION 'Unsupported source'
            USING ERRCODE = '22023';
    END IF;

    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant id'
            USING ERRCODE = '22023';
    END IF;

    v_table := CASE p_source
        WHEN 'current' THEN 'orders'
        WHEN 'archive' THEN 'orders_archive'
    END;

    EXECUTE format(
        'SELECT COUNT(*)
         FROM %I.%I
         WHERE tenant_id = $1',
        'sqli388',
        v_table
    )
    INTO v_count
    USING p_tenant_id;

    RETURN v_count;
END;
$fn$;
```

Thử:

```sql
SELECT sqli388.count_from_source('current', 10);
SELECT sqli388.count_from_source('archive', 10);
SELECT sqli388.count_from_source('current', 20);
```

Kỳ vọng là `5`, `1` và `3`.

### 22.1. Test tên bảng không được phép

```sql
-- Kỳ vọng lỗi Unsupported source:
SELECT sqli388.count_from_source('pg_catalog.pg_authid', 10);
```

Hàm không lấy input đó làm tên object; nó từ chối ngay tại allowlist.

### 22.2. Vì sao hàm vẫn không phải public multi-tenant API?

Vì `p_tenant_id` vẫn do caller truyền. Với INVOKER, DB privileges và RLS có thể hạn chế phạm vi; nhưng nếu role có SELECT rộng và API không xác minh tenant, caller có thể đếm dữ liệu tenant khác.

## 23. Chọn cột động bằng allowlist và `%I`

Một báo cáo chỉ cho phép tìm theo:

- `status`.
- `customer_code`.

Ví dụ:

```sql
CREATE OR REPLACE FUNCTION sqli388.count_by_field(
    p_tenant_id integer,
    p_field text,
    p_value text
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, sqli388, pg_temp
AS $fn$
DECLARE
    v_count bigint;
BEGIN
    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant id'
            USING ERRCODE = '22023';
    END IF;

    IF p_field IS NULL
       OR p_field NOT IN ('status', 'customer_code')
    THEN
        RAISE EXCEPTION 'Unsupported field'
            USING ERRCODE = '22023';
    END IF;

    EXECUTE format(
        'SELECT COUNT(*)
         FROM sqli388.orders
         WHERE tenant_id = $1
           AND %I = $2',
        p_field
    )
    INTO v_count
    USING p_tenant_id, p_value;

    RETURN v_count;
END;
$fn$;
```

```sql
SELECT sqli388.count_by_field(10, 'status', 'NEW');

SELECT sqli388.count_by_field(
    10, 'customer_code', 'O''Reilly'
);
```

### 23.1. Vì sao p_field không dùng USING?

`p_field` là **column identifier**, còn `p_value` là data value. Hai loại input cần cơ chế xử lý khác.

### 23.2. Vì sao vẫn phải allowlist?

Nếu không có allowlist, caller có thể yêu cầu filter bằng cột nhạy cảm/không dự kiến hoặc gây lỗi kiểu/cấu trúc. `%I` chỉ xử lý tên đúng cú pháp.

### 23.3. Nếu field có kiểu khác text?

Trong lab cả `status` và `customer_code` đều text. Nếu thêm `amount` kiểu numeric, không dùng một tham số text chung rồi hy vọng mọi operator/cast luôn đúng. Nên tách query variants theo kiểu hoặc bind đúng data type.

### 23.4. Nếu giá trị NULL?

`column = $2` không match khi `$2` là SQL NULL. Dùng predicate riêng hoặc `IS NOT DISTINCT FROM` nếu muốn so sánh null-safe.

## 24. Dynamic ORDER BY: nơi binding dễ bị hiểu sai

Ứng dụng muốn người dùng chọn:

- Sắp xếp mới nhất.
- Sắp xếp giá tăng.
- Sắp xếp giá giảm.

Sai:

```java
String sql = "SELECT * FROM sqli388.orders " +
             "ORDER BY " + requestSort;
```

Nếu `requestSort` là raw text, ứng dụng đưa cú pháp SQL của người dùng vào câu lệnh.

### 24.1. Allowlist ở Java

```java
String orderBy = switch (requestedSort) {
    case "newest" -> "created_at DESC, order_id DESC";
    case "price_asc" -> "amount ASC, order_id DESC";
    case "price_desc" -> "amount DESC, order_id DESC";
    default -> throw new IllegalArgumentException(
        "Unsupported sort"
    );
};

String sql = """
    SELECT order_id, customer_code, amount, created_at
    FROM sqli388.orders
    WHERE tenant_id = ?
    ORDER BY
    """ + orderBy + "\nLIMIT ?";
```

Ở đây `orderBy` **không được sao chép nguyên văn từ client**; nó chỉ có thể nhận một trong ba literal SQL fragments cố định do code định nghĩa.

### 24.2. Bind phần còn lại

```java
try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, authenticatedTenantId);
    ps.setInt(2, validatedPageSize);
    // ps.executeQuery(), xử lý ResultSet, close...
}
```

### 24.3. Vì sao không bind cả ORDER BY bằng `?`?

Parameter đại diện **giá trị**, không tạo SQL column identifier, keyword `ASC` hay `DESC`. Dùng `ORDER BY ?` với chuỗi `"amount DESC"` không tạo sort theo amount như mong muốn.

### 24.4. Chiều sắp xếp động trong PL/pgSQL

```sql
v_direction := CASE
    WHEN p_descending IS TRUE THEN 'DESC'
    ELSE 'ASC'
END;

EXECUTE format(
    'SELECT COUNT(*)
     FROM (
         SELECT order_id FROM sqli388.orders
         WHERE tenant_id = $1
         ORDER BY %I %s, order_id DESC
         LIMIT $2
     ) AS page',
    v_sort_column,
    v_direction
)
INTO v_count
USING p_tenant_id, p_page_size;
```

Chỉ an toàn khi `v_sort_column` đã đi qua allowlist và `v_direction` được code sinh đúng từ `ASC`/`DESC`. Đoạn này chỉ minh họa dynamic sort; muốn đếm **total matched rows**, không dùng count sau LIMIT.

### 24.5. NULLS FIRST/LAST cũng là syntax

Nếu cần cho phép user chọn vị trí NULL, map enum sang `'NULLS FIRST'` hoặc `'NULLS LAST'` fixed fragments, không nhận raw SQL text.

## 25. Dynamic WHERE và optional filters

Một bộ lọc tùy chọn:

- Có thể lọc status.
- Có thể lọc min/max amount.
- Có thể lọc customer.
- Tenant scope luôn bắt buộc.

### 25.1. Cách tĩnh khi ít filters

```sql
WHERE tenant_id = $1
  AND ($2::text IS NULL OR status = $2)
  AND ($3::numeric IS NULL OR amount >= $3)
  AND ($4::numeric IS NULL OR amount <= $4)
```

Cách viết này có semantics rõ nếu NULL nghĩa là “không lọc”. Nhưng có thể ảnh hưởng kế hoạch thực thi, đặc biệt generic prepared plan.

### 25.2. Query builder với danh sách clauses cố định

Một cách khác là tạo các conditions từ **những literal được code kiểm soát**:

```text
mandatory := "tenant_id = ?"
if status present:
    add "AND status = ?"
if minAmount present:
    add "AND amount >= ?"
if maxAmount present:
    add "AND amount <= ?"
bind values in exactly that order
```

Không bao giờ nối raw field/operator/value đến từ request vào WHERE.

### 25.3. Nếu cho user chọn toán tử?

Thay vì nhận raw `operator` rồi ghép SQL, map lựa chọn:

- `eq` → `=`.
- `gte` → `>=`.
- `lte` → `<=`.

Tuy nhiên, phải xác minh operator nào phù hợp kiểu cột và nghiệp vụ. Một allowlist trên toán tử không đủ nếu caller có thể tự chọn cột nhạy cảm và scope.

### 25.4. Bao các nhánh OR

Đảm bảo:

```sql
AND (
    customer_code = $2
    OR status = $3
)
```

không bị nối sai thành `... AND customer_code = $2 OR status = $3` làm rơi điều kiện tenant.

## 26. SQL NULL, `quote_nullable` và equality

Trong SQL, `NULL` có nghĩa “không có giá trị biết được”. Do đó:

```sql
SELECT NULL::text = NULL::text;
```

trả SQL NULL (UNKNOWN), không TRUE.

### 26.1. Tìm rows note IS NULL

```sql
SELECT order_id
FROM sqli388.orders
WHERE tenant_id = 10
  AND note IS NULL;
```

### 26.2. So sánh null-safe với một parameter

```sql
PREPARE by_note(integer, text) AS
SELECT order_id
FROM sqli388.orders
WHERE tenant_id = $1
  AND note IS NOT DISTINCT FROM $2;

EXECUTE by_note(10, NULL);
DEALLOCATE by_note;
```

`IS NOT DISTINCT FROM` coi hai phía cùng NULL là bằng nhau, trả Boolean xác định.

### 26.3. PL/pgSQL động với NULL

```sql
EXECUTE
    'SELECT COUNT(*)
     FROM sqli388.orders
     WHERE tenant_id = $1
       AND note IS NOT DISTINCT FROM $2'
INTO v_count
USING p_tenant_id, p_note;
```

Không cần `quote_nullable` nếu value được bind.

### 26.4. Khi bắt buộc tạo literal SQL text

```sql
v_sql := format(
    'SELECT COUNT(*)
     FROM sqli388.orders
     WHERE note IS NOT DISTINCT FROM %L',
    p_note
);
```

`%L` tạo token `NULL` khi p_note SQL NULL; text SQL vẫn tồn tại. Tuy nhiên, `USING` vẫn là lựa chọn ưu tiên cho các query được hỗ trợ.

## 27. SQL injection khác LIKE wildcard injection

Giả sử người dùng nhập:

```text
A%_B
```

Nếu query dùng:

```sql
WHERE customer_code LIKE $1
```

và giá trị bind là `'%A%_B%'`, `%` và `_` **bên trong** input vẫn được LIKE hiểu là wildcard.

**Điều này không phải SQL syntax injection**: câu SQL vẫn không đổi. Nhưng nó có thể làm phạm vi matching rộng hơn kỳ vọng, gọi là **pattern injection/semantic abuse** tùy ứng dụng.

### 27.1. Khi muốn tìm đúng chuỗi literal

Chọn escape character `!`:

- `!` → `!!`.
- `%` → `!%`.
- `_` → `!_`.

Trong PL/pgSQL:

```sql
v_escaped := replace(
    replace(
        replace(p_text, '!', '!!'),
        '%', '!%'
    ),
    '_', '!_'
);

v_pattern := '%' || v_escaped || '%';

EXECUTE $query$
    SELECT COUNT(*)
    FROM sqli388.orders
    WHERE tenant_id = $1
      AND customer_code LIKE $2 ESCAPE '!'
$query$
INTO v_count
USING p_tenant_id, v_pattern;
```

### 27.2. Thứ tự escape quan trọng

Đầu tiên escape chính ký tự `!`, sau đó escape `%` và `_`. Nếu làm ngược, phần `!` mới thêm có thể bị double-escape ngoài ý muốn.

### 27.3. ILIKE cũng cần escape khi tìm literal

`ILIKE` chỉ khác case-matching behavior theo collation/locale liên quan, không tự biến `%` và `_` thành plain text.

### 27.4. SQL parameter không thay đổi LIKE semantics

`PreparedStatement`/`USING` bảo vệ cú pháp SQL, nhưng **không tự sửa** wildcard logic. Chọn pattern search policy riêng.

## 28. Regex và Full Text Search vẫn là những ngôn ngữ con

### 28.1. Regex

```sql
WHERE description ~ $1
```

SQL được parameterized, nhưng `$1` được regex engine phân tích như **regular expression**. Metacharacters, anchors, repetition và alternation vẫn có tác dụng.

Nếu user chỉ muốn tìm literal text, không chuyển thẳng input thành regex mà không có quoting/policy.

### 28.2. Query rất tốn tài nguyên

Một biểu thức chính quy phức tạp có thể tốn CPU trên dữ liệu lớn. Bảo vệ bằng giới hạn input, quyền dùng regex, statement timeout và test workload phù hợp.

### 28.3. PostgreSQL Full Text Search

```sql
PREPARE fts_find(integer, text) AS
SELECT order_id, description
FROM sqli388.orders
WHERE tenant_id = $1
  AND to_tsvector(
      'simple', coalesce(description, '')
  ) @@ websearch_to_tsquery('simple', $2)
ORDER BY order_id;

EXECUTE fts_find(10, 'PostgreSQL');
DEALLOCATE fts_find;
```

`$2` là data value; không ghép raw text thành SQL syntax.

### 28.4. FTS query syntax không phải SQL syntax

`websearch_to_tsquery` diễn giải input như biểu thức tìm kiếm kiểu web theo tính năng PostgreSQL hỗ trợ. Cũng cần giới hạn độ dài, chọn text search configuration và kiểm thử chất lượng/chi phí. Nhưng input đó không tự được parser SQL chạy như một câu lệnh mới.

### 28.5. Không coi tìm kiếm là kiểm soát truy cập

Bất kể regex/FTS/LIKE có bind an toàn đến đâu, bắt buộc giữ tenant/status/ACL predicates và RLS phù hợp.

## 29. SQL text từ format và string escaping

Trong một số utility commands không hỗ trợ bind values ở vị trí cần thiết, ta có thể phải dựng SQL text.

### 29.1. `format('%L')` cho DDL literal

Ví dụ admin có thể thay comment của bảng **đã được allowlist**:

```sql
EXECUTE format(
    'COMMENT ON TABLE %I.%I IS %L',
    'sqli388',
    'orders',
    p_comment
);
```

`%L` quote comment literal hoặc token `NULL` đúng ngữ nghĩa.

### 29.2. Chỉ chạy bởi admin được phép

`COMMENT ON` là utility command/DDL liên quan quyền object. Nếu caller có thể chọn arbitrary table name hoặc dùng definer owner quyền cao, vẫn có authorization risk dù SQL text được quote đúng.

### 29.3. Backslash không phải giải pháp chung

Dùng một hàm tự viết `replace(input, "'", "\\'")` rồi ghép SQL là dễ sai vì PostgreSQL string-literal rules, `standard_conforming_strings` và các lớp escape khác.

### 29.4. Dollar quoting thích hợp cho code cố định

```sql
DO $body$
BEGIN
    RAISE NOTICE 'Hello from a fixed PL/pgSQL body';
END;
$body$;
```

Nhưng **không ghép arbitrary user input vào giữa `$tag$ ... $tag$`** như cách escape runtime. Input có thể chứa đúng delimiter đó.

### 29.5. Identifier cũng có giới hạn độ dài

PostgreSQL giới hạn identifier length theo cấu hình build (mặc định thường 63 bytes). `quote_ident` không làm biến mất các rủi ro collision/truncation khi tự tạo object names từ dữ liệu.

## 30. Không tin tên relation chỉ vì `regclass` nhận diện được

`regclass` có thể phân giải text thành relation OID:

```sql
SELECT
    'sqli388.orders'::regclass AS active_relation,
    'sqli388.orders_archive'::regclass AS archive_relation;
```

Điều này có thể hữu ích trong database tooling, nhưng:

- `regclass` không tự bảo đảm caller **được phép** chọn relation.
- Tên không fully qualified vẫn có thể phụ thuộc `search_path`.
- Object có thể bị rename/drop/recreate sau một bước lookup.
- Một definer function nhận relation OID tùy ý rồi chạy quyền owner vẫn có thể vượt authorization.

### 30.1. Catalog lookup không phải allowlist

Kiểm tra “tên bảng tồn tại” yếu hơn “bảng nằm trong đúng tập cho phép và caller có quyền theo policy”.

### 30.2. Static mapping thường đơn giản hơn

Với hai bảng `orders` và `orders_archive`, dùng enum `current`/`archive` rồi map sang hardcoded identifiers dễ review hơn một API nhận arbitrary regclass.

## 31. SECURITY DEFINER: cùng injection, hậu quả có thể lớn hơn

Một routine:

```sql
CREATE FUNCTION trusted.some_api(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
AS $fn$
...
$fn$;
```

được thực thi theo quyền **owner của routine** trong phần thực thi thích hợp.

Nếu owner có quyền đọc nhiều bảng mà caller không có, dynamic SQL không an toàn có thể khiến caller điều khiển những gì owner truy cập.

### 31.1. Quoting đúng chưa đủ

Đoạn code:

```sql
EXECUTE format(
    'SELECT COUNT(*) FROM %I.%I',
    p_schema, p_table
)
INTO v_count;
```

có thể **hoàn toàn đúng cú pháp**, không có syntax injection, nhưng vẫn là API đọc bất kỳ bảng mà owner có quyền. Cần allowlist và authorization theo object.

### 31.2. Chủ sở hữu ít quyền

Ưu tiên NOLOGIN owner role chuyên biệt, chỉ có SELECT/UPDATE/INSERT cần thiết, không dùng superuser hoặc role `BYPASSRLS` cho routine nếu không có lý do rất rõ.

### 31.3. `CURRENT_USER` trong definer

Trong definer context, `CURRENT_USER` thể hiện owner, không tự cho biết end user đã gọi routine. `SESSION_USER` thường thể hiện login DB; khi nhiều HTTP users chia sẻ một DB connection pool, nó không phân biệt những người dùng web.

### 31.4. Tenant identity cần nguồn đáng tin

Một function definer nhận `p_tenant_id` tùy ý rồi dùng quyền owner truy vấn bảng khác tenant là lỗi phân quyền, dù mọi values đã bind.

## 32. `search_path`: bảo vệ phân giải đối tượng

PostgreSQL dùng `search_path` để tìm các unqualified object names theo quy tắc áp dụng.

```sql
SHOW search_path;

SELECT
    current_schema(),
    current_schemas(true);
```

Một câu:

```sql
SELECT * FROM orders;
```

có thể tìm bảng `orders` khác nhau tùy path.

### 32.1. Nguy cơ schema writable

Nếu schema mà attacker có quyền `CREATE` đứng trước trusted schema, một unqualified function/table/operator/type name có thể bị shadow trong những điều kiện resolution phù hợp.

### 32.2. `pg_catalog` và `pg_temp`

- `pg_catalog` chứa built-in objects. Khi được nêu rõ, vị trí của nó trong path ảnh hưởng ưu tiên lookup; nên đặt trước untrusted application schemas.
- Temporary schema có quy tắc đặc biệt: nếu không được liệt kê rõ, nó có thể được tìm trước với **relation/type names**; không dùng cùng cách lookup đó cho function/operator names.

### 32.3. Mẫu path cho privileged routine

```sql
SECURITY DEFINER
SET search_path = pg_catalog, trusted_schema, pg_temp
```

Trong đó `trusted_schema` phải thực sự **không cho untrusted caller CREATE/ALTER objects**.

Dùng fully qualified references cho bảng/hàm nhạy cảm:

```sql
SELECT *
FROM trusted_schema.some_table;
```

### 32.4. Mẫu definer chưa hoàn chỉnh không được đem chạy

```sql
-- Pseudocode về cấu hình, không phải DDL hoàn chỉnh:
-- CREATE FUNCTION trusted_schema.api(...) RETURNS ...
-- LANGUAGE plpgsql SECURITY DEFINER
-- SET search_path = pg_catalog, trusted_schema, pg_temp
-- AS $fn$ ... $fn$;
```

Hàm definer thật phải được review privileges, inputs, tenant scope, helper calls và body. Không thể tạo một API an toàn chỉ bằng việc thêm `SET search_path`.

### 32.5. Tránh `public` nếu không đáng tin

Quyền `CREATE` trên schema `public` phụ thuộc database, phiên bản, upgrade history và grants. Đừng giả định mọi public schema hiện có là trusted.

## 33. RLS và multi-tenant: SQL an toàn vẫn có thể lộ hàng

Row-Level Security (RLS) là một lớp hạn chế rows được phép truy cập theo policies của PostgreSQL.

### 33.1. RLS không tự áp nếu role bypass

Superusers và roles có `BYPASSRLS` có trường hợp bỏ qua RLS. Table owner thường bypass policies, trừ khi `FORCE ROW LEVEL SECURITY` được cấu hình phù hợp.

### 33.2. Khi gọi SECURITY DEFINER

Bảng được truy cập theo effective privileges của definer owner, không mặc định theo caller RLS context như invoker. Nếu owner bypass RLS, cần explicit trusted authorization trong routine để tránh lộ tenant.

### 33.3. Custom GUC không tự chứng thực user

Một policy dạng:

```sql
USING (
    tenant_id =
    current_setting('app.tenant_id')::integer
)
```

chỉ an toàn nếu hệ thống **bảo vệ được giá trị session context**. Nếu caller untrusted có thể tự `SET app.tenant_id`, giá trị đó không đáng tin.

### 33.4. Tenant predicate còn cần cho count, facets và exports

Không chỉ trang list phải áp authorization; cả total counts, search suggestions, downloads và reports có thể rò thông tin nếu bỏ phạm vi tenant.

### 33.5. SQL injection và authorization testing tách biệt

Phải thử cả:

- Parameter chứa ký tự giống SQL syntax không được biến thành code.
- Caller không thể truy cập tenant không được phép **dù không có ký tự đặc biệt nào** trong input.

## 34. GRANT, roles và quyền hạn chế hậu quả

Ngay cả khi app dùng prepared statements, vẫn cần cấu hình quyền:

- Runtime DB role không sở hữu bảng nếu không cần.
- Không có quyền `CREATE` trong schemas nhạy cảm.
- Chỉ được `SELECT`/`INSERT`/`UPDATE` theo nhiệm vụ.
- Không có superuser, `CREATEROLE` hay `BYPASSRLS` theo mặc định.
- Tránh cho phép arbitrary SQL execution từ client.
- Dùng migration role riêng cho DDL.
- Definer owner có quyền thấp nhất đủ đáp ứng chức năng.

### 34.1. Prepared statements không phải firewall SQL

Role có quyền chạy arbitrary SQL thì vẫn có thể gửi **SQL tùy ý** với cú pháp chính xác. Parameterization chỉ ngăn một data parameter phá SQL template.

### 34.2. Tối thiểu hóa blast radius

Nếu code có lỗi, quyền hạn chế giảm phạm vi hậu quả. Một runtime role chỉ SELECT một schema ít nhạy cảm có mức rủi ro khác hẳn superuser.

### 34.3. `PUBLIC EXECUTE` và hàm đặc quyền

Functions PostgreSQL mới thường có `EXECUTE` cho `PUBLIC` theo default privileges nếu không thay đổi. Với `SECURITY DEFINER`:

```sql
BEGIN;

-- CREATE FUNCTION ... SECURITY DEFINER ...;

-- Khi đã tạo routine:
-- REVOKE ALL ON FUNCTION schema.api(types...) FROM PUBLIC;
-- GRANT EXECUTE ON FUNCTION schema.api(types...) TO trusted_role;

COMMIT;
```

Mẫu này là **khung migration**, không phải câu SQL độc lập chạy được vì phần CREATE/REVOKE/GRANT chỉ ở comment. Ý chính là CREATE, REVOKE và GRANT được thực hiện **trong cùng transaction** để tránh cửa sổ quyền rộng.

### 34.4. Phân biệt privilege và object authorization

Có quyền gọi `api()` không có nghĩa được truy cập **mọi customer ID** mà API có thể nhận. Kiểm tra row/object-level business rules vẫn cần có trong API.

## 35. Dynamic DDL: rủi ro cao hơn SELECT động

Một công cụ migration có thể tạo bảng theo cấu hình:

```sql
EXECUTE format(
    'CREATE TABLE %I.%I (
         id bigint PRIMARY KEY,
         payload text
     )',
    v_schema,
    v_table
);
```

### 35.1. Quoting là cần thiết nhưng không đủ

- `v_schema` phải là schema được phép quản lý.
- `v_table` phải được xác định theo policy naming/quota.
- Caller phải có quyền tạo object phù hợp.
- Tránh trùng tên hoặc va chạm hệ thống.
- Không cho role ngoài ý muốn tạo bảng trên schema được `SECURITY DEFINER` dùng.

### 35.2. DDL utility không bind mọi vị trí

Một số utility statements không hỗ trợ placeholders theo cách optimizable SQL commands hỗ trợ. Sử dụng `%I` cho identifiers và `%L` cho literals khi buộc phải build text.

### 35.3. Không nhận raw DDL fragments

Một `p_columns_sql text` từ HTTP request rồi ghép vào `CREATE TABLE` không được bảo vệ bằng việc quote table name. Nếu cần dynamic DDL, hãy build column definitions từ **schema định nghĩa sẵn hoặc cấu trúc validated**, không từ SQL text người dùng.

### 35.4. Tránh cấp quyền CREATE không giới hạn

Tạo hàng nghìn bảng/schema tự động có thể làm tăng catalog overhead, backup/maintenance cost và rủi ro vận hành, ngay cả khi không có injection.

## 36. Không đồng nhất query syntax với business policy

Ví dụ query đã bind:

```sql
SELECT order_id, amount
FROM sqli388.orders
WHERE tenant_id = $1
  AND amount >= $2
ORDER BY amount ASC
LIMIT $3;
```

nó có thể có những vấn đề **ngoài injection**:

- Tenant ID không được xác thực.
- Giá trị amount quá lớn/âm hoặc sai currency.
- `LIMIT` vượt quota.
- Không có thời gian/permission filter bắt buộc.
- Không có tie-breaker khi hai orders cùng amount.
- Không có timeout cho truy vấn.
- DB role có quyền đọc nhiều schemas ngoài nhu cầu.

**Parameterized SQL là một lớp trong hệ thống an toàn**, không phải toàn bộ thiết kế.

## 37. Kế hoạch thực thi và parameterization

`PREPARE`/JDBC prepared statements có thể được PostgreSQL thực thi theo **custom plan** hoặc **generic plan** tùy điều kiện cache/planner, phiên bản và query.

### 37.1. Có thể khác theo tham số

Tenant có 10 hàng và tenant có 10 triệu hàng có thể cần access paths khác nhau. Query parameterized vẫn đúng semantics; nhưng performance có thể khác.

### 37.2. PL/pgSQL EXECUTE động thường re-plan

`EXECUTE command_string USING ...` trong PL/pgSQL không cache plan kiểu statement tĩnh của PL/pgSQL; nó lập plan khi thực thi dynamic command. Điều này có thể giúp với parameter selectivity lệch nhưng làm tăng planning overhead.

### 37.3. Không chuyển về nối literal để “ép index”

Nếu generic prepared plan kém với một workload, xem thống kê, indexes, plan cache mode và query variants được parameterized, không bỏ an toàn để ghép raw SQL values.

### 37.4. `EXPLAIN (ANALYZE, BUFFERS)`

```sql
PREPARE perf_orders(integer, text) AS
SELECT order_id, amount
FROM sqli388.orders
WHERE tenant_id = $1
  AND customer_code = $2;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE perf_orders(10, 'O''Reilly');

DEALLOCATE perf_orders;
```

Dùng để so actual rows, buffers và index access. `EXPLAIN ANALYZE` thật sự chạy câu SQL; với DML phải cẩn thận vì nó có thể thay dữ liệu.

### 37.5. Bảo mật và hiệu năng không đối lập

Parameterization đúng thường giúp code rõ, type-safe và dễ audit. Performance tuning nên diễn ra **sau khi đã giữ đúng ranh giới code/data và authorization**.

## 38. Logging, lỗi và phát hiện tấn công

Trong production, có thể theo dõi:

- Error rates: syntax errors, permission denied, statement timeout.
- Các lựa chọn sort/table/column bị từ chối bởi allowlist.
- Query duration và p95/p99.
- Frequency của requests với input rất dài hoặc mẫu bất thường.
- Số lượng truy vấn chạy đồng thời.
- Số lần gọi definer APIs, quyền/role context khi có nguồn đáng tin.
- Thay đổi grants, schema objects và migration definitions.

### 38.1. Không log nguyên payload nhạy cảm tùy tiện

Search terms, tên khách hàng và notes có thể chứa dữ liệu cá nhân. Logging tất cả bound parameters có thể tạo một kênh rò dữ liệu khác.

Ưu tiên structured logs với template ID, error category, độ dài input, outcome, correlation ID và masking phù hợp.

### 38.2. Lỗi cú pháp không phải bằng chứng duy nhất

Một injection có thể không tạo SQL syntax error. Và một syntax error có thể đến từ bug code thay vì tấn công. Xây hệ thống detection dựa trên hành vi/quyền/metrics kết hợp.

### 38.3. Không trả SQL nội bộ qua API error

Một driver exception có thể chứa tên bảng, câu query hoặc thông tin cấu trúc. Log nội bộ đúng mức và trả thông báo công khai không tiết lộ chi tiết không cần thiết.

### 38.4. Query timeout và rate limits

Bind an toàn không ngăn câu regex/FTS hoặc báo cáo hợp pháp nhưng quá rộng tốn tài nguyên. Áp timeout, page-size caps, rate limits và quotas theo workload.

## 39. Chiến lược kiểm thử SQL injection

Bộ test nên có ít nhất các nhóm:

| Nhóm | Dữ liệu thử | Kỳ vọng |
| --- | --- | --- |
| Text thông thường | `ALICE` | Đúng record |
| Dấu nháy đơn | `O'Reilly` | Không lỗi parse, đúng value |
| Chuỗi giống cú pháp | `x' OR TRUE --` | Không đổi WHERE semantics |
| Unicode | `VN-ĐỎ` | Không lỗi encoding/normalization giả định |
| Wildcards literal | `A%_B` | `=` exact; `LIKE` có ESCAPE khi cần |
| Empty string | `''` | Theo API policy |
| SQL NULL | `NULL` | So sánh `IS NULL`/null-safe đúng |
| Dấu double quote | `a"b` | Không phá identifier quoting |
| Có dấu chấm | `schema.table` | Không bị coi tự động là qualified name |
| Keyword identifier | `select` | Quote identifier đúng nếu cho phép |
| Identifier không allowlist | `pg_catalog.pg_authid` | Từ chối trước SQL |
| Sort sai | `unknown_sort` | Từ chối |
| Page size rất lớn | `999999999` | Từ chối hoặc clamp theo policy |
| Tenant không được phép | Tenant khác | Không trả dữ liệu |
| Regexp quá phức tạp | Regex không hợp lệ/tốn CPU | Validate/limit/timeout |
| FTS rỗng/không có match | Empty or rare query | Theo UX, không full scan vô ý |
| Schema shadowing | Bảng trùng tên trong pg_temp | Definer không đổi object đích |
| Role hạn chế | Role chỉ EXECUTE/không SELECT | Theo đúng privilege contract |

### 39.1. Test SQL template và kết quả

Không chỉ khẳng định “không thấy syntax error”. Kiểm tra chính xác rows/counts trả về để phát hiện logic bug.

### 39.2. Test không thay đổi state

Với endpoint read-only, chạy test đảm bảo số rows/schema không bị thay đổi vì input.

### 39.3. Test bằng role thực tế

Một superuser test connection có thể che lỗi quyền/RLS. Dùng app runtime role hoặc role mô phỏng đúng ACL.

### 39.4. Test trong transaction riêng khi phù hợp

`BEGIN`/`ROLLBACK` giúp kiểm soát DML trong lab, nhưng không nên coi rollback một lần là bằng chứng mọi API đều read-only.

## 40. Những ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Escape dấu nháy là đủ” | Values nên bind; identifiers/syntax cần cơ chế khác |
| “PreparedStatement biến mọi input thành an toàn” | Chỉ những vị trí được bind, không sửa authorization/logic |
| “`?` thay được tên bảng” | Không; parameter là value, không phải identifier |
| “`ORDER BY ?` có thể nhận `amount DESC`” | Không dùng như SQL sort syntax |
| “`quote_ident` tự kiểm tra quyền table” | Không |
| “`quote_literal` an toàn cho table name” | Sai loại: string literal khác identifier |
| “`format('%I','a.b')` là schema.table” | Nó quote một identifier có dấu chấm |
| “`%s` tương đương `%I`” | Không quote SQL |
| “`%L` cần cho mọi value dù đã có USING” | Không; USING thường tốt hơn |
| “`quote_literal(NULL)` là text NULL” | Nó trả SQL NULL |
| “`quote_nullable` làm `= NULL` đúng” | Không; phải dùng NULL-safe predicate |
| “LIKE bind rồi %/_ đều literal” | Pattern wildcards vẫn có semantics |
| “Regex bind nghĩa là literal search” | Regex engine vẫn diễn giải pattern |
| “Dữ liệu đã lưu trong DB luôn đáng tin” | Second-order injection vẫn có thể xảy ra |
| “Whitelist chỉ cần cho SQL injection” | Nó còn quyết định object authorization |
| “Tên bảng quote đúng thì chọn tùy ý được” | Không; owner có thể truy cập object nhạy cảm |
| “Role superuser giúp API hoạt động ổn định” | Blast radius cực lớn |
| “RLS luôn áp theo caller trong definer” | Owner context có thể bypass |
| “Tenant ID đã bind thì tenant isolation được bảo đảm” | Cần nguồn tenant đáng tin |
| “SET search_path caller đủ cho definer” | Đặt path an toàn ngay trong routine |
| “pg_temp không thể shadow bảng” | Có quy tắc lookup đặc biệt |
| “Có GIN/B-tree index thì không cần giới hạn query” | Wildcards/regex/sort vẫn có thể tốn kém |
| “Một statement không thể bị injection” | Injection có thể đổi nghĩa trong một statement |
| “SQL builder tự động an toàn mọi raw fragment” | Phải xem API có biểu diễn value hay nối SQL text |
| “Không có lỗi SQL nghĩa không bị injection” | Nhiều lỗi logic không báo lỗi |
| “SQL injection và access control là một vấn đề” | Hai vấn đề khác nhau, phải kiểm thử riêng |

## 41. Bài tập có đáp án

Các bài sử dụng schema `sqli388`. Nếu muốn thử các đoạn `EXECUTE ... INTO ... USING`, đặt chúng bên trong PL/pgSQL function/DO block có khai báo variables tương ứng. Những mẫu ghi “sai/nguy hiểm” chỉ để phân tích, không chạy trên production.

### Bài 1. SQL injection là gì?

**Đáp án:** dữ liệu không đáng tin bị đưa vào cú pháp SQL, khiến parser hiểu một phần input như cấu trúc câu lệnh thay vì value.

### Bài 2. Vì sao mã `O'Reilly` gây lỗi khi nối literal thủ công?

**Đáp án:** dấu nháy đơn có thể kết thúc string literal sớm. Parameter binding tránh xây literal từ input.

### Bài 3. PreparedStatement bảo vệ phần nào?

**Đáp án:** các placeholders biểu diễn **data values** trong SQL template cố định. Nó không tự ràng buộc table names hay sửa logic authorization.

### Bài 4. JDBC dùng placeholder ký hiệu nào?

**Đáp án:** `?` và bind bằng `ps.setX(index, value)`, với index bắt đầu từ 1.

### Bài 5. PostgreSQL PREPARE sử dụng placeholder nào?

**Đáp án:** `$1`, `$2`... tương ứng declared parameter types/positions.

### Bài 6. Viết SQL tìm customer có tenant rõ ràng

```sql
PREPARE q(integer, text) AS
SELECT order_id FROM sqli388.orders
WHERE tenant_id = $1
  AND customer_code = $2;
```

**Đáp án:** bind hai values, không nối input.

### Bài 7. Vì sao tenant bind đúng nhưng vẫn có thể lộ dữ liệu?

**Đáp án:** caller có thể tự chọn tenant khác nếu API/DB không kiểm tra quyền. Bind không phải authorization.

### Bài 8. Một chuỗi đã lưu trong database có tự đáng tin khi đọc lại không?

**Đáp án:** không. Nếu đưa nó vào dynamic SQL bằng nối chuỗi về sau, vẫn có second-order injection.

### Bài 9. Data value và identifier khác nhau thế nào?

**Đáp án:** value là dữ liệu trong expression, identifier là tên object/cột trong cú pháp SQL.

### Bài 10. `quote_ident` dùng để làm gì?

**Đáp án:** tạo biểu diễn SQL identifier đúng cú pháp, chẳng hạn tên bảng/cột.

### Bài 11. `quote_literal` dùng để làm gì?

**Đáp án:** biểu diễn một data value thành SQL literal text khi buộc phải xây source SQL; với optimizable dynamic SQL ưu tiên `USING`.

### Bài 12. `quote_nullable` khác `quote_literal` khi input NULL?

**Đáp án:** `quote_nullable(NULL)` trả text `NULL`, `quote_literal(NULL)` trả SQL NULL.

### Bài 13. Vì sao command string có thể thành NULL?

**Đáp án:** nối `'prefix' || quote_literal(NULL)` trả SQL NULL, nên `EXECUTE` không có command text hợp lệ.

### Bài 14. `%I` và `%L` khác gì?

**Đáp án:** `%I` dành cho identifier, `%L` dành cho literal value (gồm SQL NULL).

### Bài 15. Có thể dùng `%s` với raw sort expression không?

**Đáp án:** không. `%s` chèn text không SQL-quote; chỉ dùng với fragment fixed/allowlisted.

### Bài 16. Quote schema.table thế nào?

```sql
SELECT format('%I.%I', 'sqli388', 'orders');
```

**Đáp án:** quote schema và table riêng.

### Bài 17. Vì sao quote `'sqli388.orders'` bằng một %I là sai?

**Đáp án:** nó tạo một identifier chứa dấu chấm, không phải qualified path.

### Bài 18. Bind tên bảng qua `USING p_table` được không?

**Đáp án:** không; `USING` bind values, không thay phần `FROM table_identifier` của SQL grammar.

### Bài 19. Bind tên cột qua `SELECT $1 FROM orders` là đọc cột?

**Đáp án:** không; `$1` là parameter value, không phải column reference.

### Bài 20. Chọn giữa current/archive an toàn thế nào?

**Đáp án:** kiểm tra enum `current`/`archive`, map sang tên bảng cố định, dùng `%I.%I` và bind tenant.

### Bài 21. Một tên bảng được quote đúng có chắc caller được phép chọn?

**Đáp án:** không. Cần allowlist/privileges và business authorization.

### Bài 22. Chọn cột status/customer_code trong dynamic query?

**Đáp án:** allowlist hai tên, dùng `%I` cho column identifier, `$1`/`USING` cho data values.

### Bài 23. Nêu lỗi của `tenant=10 AND status='PAID' OR customer='ALICE'`

**Đáp án:** nhánh OR cho customer có thể trả tenant khác. Phải nhóm OR trong ngoặc.

### Bài 24. Parameterization có sửa lỗi AND/OR thiếu ngoặc không?

**Đáp án:** không. Cần đúng Boolean logic.

### Bài 25. ORDER BY column và direction lấy từ user nên xử lý sao?

**Đáp án:** map enum sang fixed SQL fragments; quote column identifier hoặc chọn cả fragment cố định; không chèn raw input.

### Bài 26. LIMIT đã bind có cần validate?

**Đáp án:** có. Vẫn cần page-size caps/quota để tránh dùng quá nhiều tài nguyên.

### Bài 27. `IN ($1)` có nhận một chuỗi CSV thành nhiều values không?

**Đáp án:** không. Có thể dùng `= ANY($1::text[])` với một SQL array value hoặc tạo placeholders theo số lượng đã validate.

### Bài 28. Vì sao `status = ANY(ARRAY[]::text[])` khác không có filter?

**Đáp án:** mảng rỗng thường match không hàng nào, còn không filter có thể cho mọi status hợp lệ.

### Bài 29. `NULL = NULL` là TRUE?

**Đáp án:** không, nó là SQL NULL (UNKNOWN).

### Bài 30. Viết so sánh null-safe

```sql
WHERE note IS NOT DISTINCT FROM $1
```

**Đáp án:** đúng cho cả hai phía cùng NULL.

### Bài 31. `quote_nullable` có tự làm `note = NULL` match?

**Đáp án:** không. Nó chỉ tạo literal text; phải sửa predicate theo NULL semantics.

### Bài 32. LIKE đã bind input có biến %/_ thành literal không?

**Đáp án:** không. Nếu muốn literal matching, escape `%`/`_` bằng escape character thích hợp và khai báo `ESCAPE`.

### Bài 33. Escape tìm `A%_B` dưới dạng literal

**Đáp án:** với `ESCAPE '!'`, phần nội dung được escape thành `A!%!_B` rồi thêm wildcard ngoài để tìm contains: `%A!%!_B%`.

### Bài 34. Regex được bind thì có thành literal không?

**Đáp án:** không. Regex metacharacters vẫn được regex engine xử lý; cần policy cho phép/escape literal riêng.

### Bài 35. FTS có nhận raw SQL khi bind keyword không?

**Đáp án:** không. `websearch_to_tsquery('simple', $1)` nhận value để phân tích theo FTS syntax, không là SQL parser.

### Bài 36. Dùng SQL động chỉ vì thích có lợi không?

**Đáp án:** thường không. SQL tĩnh đơn giản, dễ audit và có cơ chế plan caching phù hợp.

### Bài 37. PL/pgSQL EXECUTE có lập plan lại không?

**Đáp án:** dynamic command thường được parse/plan tại mỗi lần EXECUTE, khác với SQL tĩnh PL/pgSQL có thể cache plan.

### Bài 38. Utility DDL có bind được mọi input không?

**Đáp án:** không. Identifiers phải là syntax; một số DDL literal cần `%L` khi không thể bind ở vị trí tương ứng.

### Bài 39. `COMMENT ON TABLE` có thể dùng gì?

**Đáp án:** `format('COMMENT ON TABLE %I.%I IS %L', schema, table, comment)` với object đã allowlist và role được quyền.

### Bài 40. Vì sao không ghép arbitrary column definitions từ request?

**Đáp án:** đó là SQL syntax fragment có thể chứa nhiều điều kiện/thao tác bất ngờ; cần một schema model và validator rõ ràng, không raw SQL.

### Bài 41. regclass có thay thế authorization không?

**Đáp án:** không. Nó hỗ trợ relation resolution/OID, không quyết định caller được phép chọn object.

### Bài 42. Vì sao `SECURITY DEFINER` làm tăng rủi ro?

**Đáp án:** dynamic SQL có thể thực thi dưới quyền owner cao hơn caller, tăng phạm vi dữ liệu/hành động nếu object name/input không kiểm soát.

### Bài 43. Definer function nên dùng owner nào?

**Đáp án:** role ít quyền nhất, thường NOLOGIN chuyên biệt; tránh superuser/BYPASSRLS trừ khi có nhu cầu được thiết kế và review kỹ.

### Bài 44. Vì sao `search_path` quan trọng?

**Đáp án:** unqualified names có thể resolve tới objects ở schema khác; attacker-writable schema/pg_temp có thể gây shadowing theo loại object.

### Bài 45. Search path mẫu cho definer?

**Đáp án:** `pg_catalog, trusted_schema, pg_temp` với trusted_schema không cho attacker CREATE/ALTER, cùng fully qualified references.

### Bài 46. `CURRENT_USER` trong definer có luôn là web user?

**Đáp án:** không, nó thường là function owner; `SESSION_USER` cũng có thể chỉ là shared DB login.

### Bài 47. RLS có luôn áp như caller khi gọi definer?

**Đáp án:** không. Owner privileges và RLS bypass semantics phải được kiểm tra riêng.

### Bài 48. Một PreparedStatement an toàn về syntax vẫn trả sai tenant thì vì sao?

**Đáp án:** application authorization/row filter hoặc RLS không đúng; đây là lỗi bảo mật khác injection.

### Bài 49. Vì sao không log mọi parameter?

**Đáp án:** có thể lộ PII/secrets; dùng structured sanitized logs, correlation IDs và policy retention.

### Bài 50. Lập checklist bảo mật một endpoint tìm kiếm

**Đáp án gợi ý:**

1. SQL template do server kiểm soát, không nhận raw SQL từ client.
2. Bind tất cả data values bằng JDBC/`USING`.
3. Allowlist mọi dynamic table/column/operator/sort fragment.
4. Quote identifiers bằng `%I` và schema/table riêng `%I.%I`.
5. Không dùng `%s` với raw user input.
6. Giữ tenant/ACL/status predicates bắt buộc trong mọi query variant.
7. Kiểm tra RLS, DB role privileges và definer owner/search_path.
8. Xử lý NULL và LIKE/regex/FTS semantics riêng.
9. Validate page size, input length, array cardinality và time range.
10. Test quote/Unicode/wildcard/SQL-like inputs và negative authorization.
11. Đo query plans, timeouts, logs và concurrent workload.
12. Tạo alert/runbook khi xuất hiện lỗi truy vấn/quyền bất thường.

## 42. Checklist triển khai thực tế

| Câu hỏi | Tiêu chuẩn |
| --- | --- |
| Có nối raw input vào SQL không? | Không với data values |
| Đã dùng prepared/bind? | `?` / `$n` / `USING` |
| Có tên bảng/schema/cột động? | Allowlist + `%I` |
| Có phân biệt string literal với identifier? | `%L` vs `%I` |
| Có quote schema.table đúng? | `%I.%I` |
| Có fragment `%s`? | Chỉ code-controlled fixed fragment |
| Có dynamic ORDER BY? | Enum sort, stable tie-breaker |
| Có dynamic IN-list? | Array/validated placeholders |
| Có NULL values? | Typed parameter và correct predicate |
| Có LIKE wildcard? | Chính sách literal/pattern rõ |
| Có regex? | Limit/validation, không nhầm injection |
| Có FTS? | Bind query text, giới hạn search cost |
| Có dynamic utility DDL? | Privilege/object policy và `%L` khi cần |
| Có role quyền rộng? | Least privilege |
| Có SECURITY DEFINER? | Owner/search_path/allowlist/ACL review |
| Có trusted schemas? | Không cho untrusted CREATE |
| Có RLS? | Test under actual effective role |
| Có shared DB login? | User identity không suy từ SESSION_USER |
| Có tenant authorization? | Trusted context, không chỉ input |
| Có OR logic phức tạp? | Parentheses đúng |
| Có count/exports? | Cùng authorization scope |
| Có auto-generated SQL từ ORM? | Kiểm tra raw fragments/native query paths |
| Có data lấy lại từ DB rồi ghép SQL? | Chống second-order injection |
| Có limits/quota? | Query/page/search bounded |
| Có test strange inputs? | Quote, Unicode, NULL, long text |
| Có test quyền thấp? | Không dùng superuser làm mọi test |
| Có kiểm thử rò dữ liệu tenant khác? | Negative assertions |
| Có log raw PII? | Redaction/retention |
| Có theo dõi syntax/permission errors? | Alert và runbook |
| Có so plan performance? | `EXPLAIN ANALYZE BUFFERS` |
| Có review migration và grants? | Có |

## 43. Quy trình review một báo cáo SQL động

Giả sử nhóm sản phẩm muốn API:

```text
GET /reports/orders
?source=archive
&sort=amount_desc
&customer=O'Reilly
&limit=50
```

Quy trình đúng:

### Bước 1. Xác thực caller và tenant

Server xác định tenant 10 có quyền từ identity/context đáng tin. Không nhận tenant_id client tự chọn rồi mặc định tin tưởng.

### Bước 2. Mapping source

`source=archive` → fixed identifier `sqli388.orders_archive`. Từ chối các giá trị khác.

### Bước 3. Mapping sort

`sort=amount_desc` → fixed fragment `ORDER BY amount DESC, order_id DESC`.

### Bước 4. Validate limit

Đảm bảo `limit` nằm trong khoảng 1–100 hoặc chính sách tương ứng.

### Bước 5. Bind customer

Dùng `$2`/JDBC `?` cho giá trị `O'Reilly`. Không tự dựng SQL literal.

### Bước 6. Thực thi query có scope

```sql
-- Minh họa dạng template sau mapping từ code:
SELECT order_id, customer_code, amount
FROM sqli388.orders_archive
WHERE tenant_id = $1
  AND customer_code = $2
ORDER BY amount DESC, order_id DESC
LIMIT $3;
```

Nếu table name thực sự được thay đổi runtime trong PL/pgSQL, hãy dùng `format('%I.%I')` và `EXECUTE ... USING`.

### Bước 7. Kiểm tra kết quả/quan sát

- Không có hàng từ tenant khác.
- Không có duplicate/out-of-scope rows.
- Không có raw parameter leakage qua logs.
- Query hoàn thành trong giới hạn.
- Chỉ data được phép xuất hiện trong response.

**Một API tốt là API giữ nguyên ranh giới giữa cú pháp và dữ liệu, đồng thời giữ đúng ranh giới quyền.**

## 44. Tổng kết

SQL injection trong PostgreSQL không chỉ là vấn đề đặt dấu nháy đúng; đó là **thiết kế ranh giới giữa SQL code, input data và quyền truy cập**.

Những quy tắc cần nhớ:

1. **Không nối input không tin cậy vào SQL source**. Dữ liệu phải được bind bằng `?`, `$n` hoặc `EXECUTE ... USING`.
2. **JDBC PreparedStatement** là lựa chọn mặc định ở tầng Java cho các queries có cấu trúc cố định.
3. **PL/pgSQL EXECUTE ... USING** giữ giá trị bên ngoài SQL text ngay cả khi câu lệnh được tạo động.
4. **Identifiers không bind được như values**. Nếu cần chọn bảng/cột, dùng allowlist/mapping rồi quote bằng `%I` hoặc `quote_ident`.
5. **`%L`/`quote_literal` dùng cho SQL literals**, đặc biệt khi utility DDL buộc phải tạo text.
6. **`%s` không SQL-escape**. Chỉ dùng cho fragment cố định do code quản lý.
7. **Schema và table phải quote riêng bằng `%I.%I`**.
8. **`quote_literal(NULL)` trả SQL NULL**, còn `quote_nullable`/`%L` tạo token text `NULL`; đúng escaping vẫn cần đúng NULL logic.
9. **Quoting không thay authorization**. Một tên bảng hợp lệ vẫn có thể là object nhạy cảm; một tenant ID bind đúng vẫn có thể không được phép.
10. **LIKE/regex/FTS có pattern semantics riêng**. Parameterization bảo vệ SQL syntax nhưng không tự escape metacharacters của các ngôn ngữ con.
11. **`SECURITY DEFINER` cần least privilege, trusted search_path và kiểm tra RLS/tenant scope**.
12. **Đừng dựa vào parser/string escaping tự viết**, hay cho user gửi raw SQL/ORDER BY/DDL.
13. **Kiểm thử negative cases**: dấu nháy, Unicode, NULL, identifiers bất hợp lệ, tenant khác, quyền thấp và query quá lớn.
14. **Tối ưu performance sau khi giữ đúng security**: index, planning, limits, timeouts và logging an toàn.

Mẫu an toàn khi buộc phải dùng table/column động:

```sql
-- Giả định v_schema, v_table, v_column đã đi qua
-- allowlist/authorization và thuộc schema đáng tin.
EXECUTE format(
    'SELECT COUNT(*)
     FROM %I.%I
     WHERE tenant_id = $1
       AND %I = $2',
    v_schema,
    v_table,
    v_column
)
INTO v_count
USING authenticated_tenant_id, p_value;
```

**Câu hỏi review cuối cùng:** “Giá trị nào có thể đến từ caller, phần nào đang được parse như SQL syntax, caller được phép chọn object nào, và câu lệnh thực thi với quyền của role nào?”. Khi trả lời rõ cả bốn điểm, bạn có nền tảng đúng để chống SQL injection và tránh lộ dữ liệu qua những truy vấn động trong PostgreSQL.
