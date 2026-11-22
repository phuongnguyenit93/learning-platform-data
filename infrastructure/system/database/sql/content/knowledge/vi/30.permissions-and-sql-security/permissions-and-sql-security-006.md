# Truy vấn tham số hóa và prepared statement

Khi ứng dụng gọi SQL để tìm người dùng, tra cứu đơn hàng, cập nhật hồ sơ hoặc ghi giao dịch, rất nhiều giá trị đến từ HTTP request, biểu mẫu, file nhập, message hoặc dịch vụ khác. Vấn đề cốt lõi là: **đâu là cú pháp SQL do lập trình viên quyết định, và đâu chỉ là dữ liệu không đáng tin từ bên ngoài?**

**Truy vấn tham số hóa (parameterized query)** giữ ranh giới ấy bằng cách để cấu trúc SQL chứa **tham số (bind parameters)**, còn giá trị cụ thể được gửi riêng qua driver/API. Hệ quản trị diễn giải chuỗi SQL như câu lệnh, rồi sử dụng các giá trị bind như dữ liệu theo kiểu khai báo; nó **không phân tích lại dữ liệu thành từ khóa, dấu nháy, toán tử hoặc điều kiện SQL**.

Ví dụ JDBC:

```java
String sql = """
    SELECT user_id, email
    FROM demo_safe_users
    WHERE tenant_id = ? AND email = ?
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, tenantId);
    ps.setString(2, emailFromRequest);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getInt("user_id"));
        }
    }
}
```

Ngay cả khi `emailFromRequest` chứa dấu nháy đơn hoặc ký tự giống một biểu thức SQL, nó vẫn chỉ là **một giá trị email** trong phép so sánh `email = ?`.

Nhưng **prepared statement không tự giải quyết mọi vấn đề bảo mật**. Nó không quyết định người gọi có được xem dữ liệu tenant khác, không biến chuỗi tên cột thành một identifier hợp lệ, không chặn truy vấn quá nặng, không sửa điều kiện `WHERE` thiếu khóa, và không thay thế transaction, validation, constraint hoặc phân quyền tối thiểu.

> **Nguyên tắc:** dựng **cấu trúc câu SQL** từ mã tin cậy và danh sách lựa chọn được cho phép; truyền **mọi giá trị biến thiên** qua API bind tham số với kiểu phù hợp. Sau đó vẫn kiểm quyền, tính đúng kết quả và hiệu năng.

Bài học thuộc **Database SQL → Quyền và SQL an toàn**. Nội dung dùng PostgreSQL làm hệ thực hành, cùng ví dụ Java/JDBC, Python/psycopg, Node.js/pg và các dialect MySQL, SQL Server, SQLite, Oracle; bao gồm `LIKE`, `IN`, `NULL`, JSON, định danh động, batch, transaction, kế hoạch thực thi, checklist và bài tập.

## 1. SQL injection bắt đầu khi dữ liệu bị coi là mã lệnh

Xem một ví dụ không an toàn:

```java
String sql =
    "SELECT user_id FROM users WHERE email = '" +
    emailFromRequest +
    "' AND tenant_id = " + tenantId;
```

Ứng dụng tự mở dấu nháy, chèn toàn bộ nội dung email, rồi đóng nháy. Nếu email có ký tự đặc biệt làm thay đổi cú pháp SQL, dữ liệu có thể bị **diễn giải thành điều kiện hay một phần câu lệnh**.

Ví dụ input dùng riêng trong database thử nghiệm:

```text
x' OR '1'='1
```

Khi bị nối vào SQL như mã nguồn, chuỗi đó có thể làm thay đổi logic `WHERE`. Đây là dạng cơ bản của **SQL injection**: dữ liệu không tin cậy được trộn vào vùng cú pháp SQL.

### 1.1. Prepared statement giữ giá trị ở đúng vị trí

Thay bằng:

```java
String sql =
    "SELECT user_id FROM users " +
    "WHERE email = ? AND tenant_id = ?";

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, emailFromRequest);
    ps.setInt(2, tenantId);
    // ps.executeQuery() ...
}
```

Driver biết `?` là **vị trí một giá trị**, không phải một chỗ cần thay bằng đoạn SQL mới. Nếu input là `x' OR '1'='1`, database so sánh email với **toàn bộ chuỗi ấy**, không mở ra một điều kiện `OR` mới.

### 1.2. “Escape mọi dấu nháy” không thay thế binding

Một tên như `O'Connor` hoặc email như `o'connor@example.com` có thể là dữ liệu hoàn toàn hợp lệ. Cấm dấu nháy khiến người dùng nhập dữ liệu sai, nhưng vẫn không chứng minh mọi chỗ ghép SQL đã an toàn. Tự viết hàm escape SQL dễ sai khi gặp nhiều dialect, kiểu dữ liệu và bối cảnh cú pháp.

**Parameterization** giải quyết ranh giới cú pháp và dữ liệu; **validation** kiểm tra một giá trị có hợp lệ về nghiệp vụ hay không. Cả hai cần thiết, nhưng làm việc khác nhau.

### 1.3. Phạm vi thực hành

Chỉ thử các chuỗi minh họa trên database hoặc ứng dụng lab mà bạn được phép vận hành. Không gửi các chuỗi thăm dò injection đến hệ thống hoặc dữ liệu không được ủy quyền. Mục tiêu là thiết kế code để **mọi giá trị input vẫn là dữ liệu**, kể cả input kỳ lạ.

## 2. Thuật ngữ phải phân biệt

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Parameterized query** | SQL có các marker và dữ liệu được cung cấp riêng qua binding API |
| **Bind parameter / bind variable** | Một giá trị thay vào marker như `?`, `$1`, `:email` |
| **Client-side PreparedStatement** | Đối tượng/API driver quản lý tham số và thực thi |
| **SQL-level PREPARE** | Câu lệnh chuẩn bị được DBMS lưu theo phạm vi session và thực thi lại theo tên |
| **Server-side prepared statement** | Trạng thái chuẩn bị tại server qua SQL hoặc protocol, có thể tái sử dụng |
| **Plan cache** | Cơ chế tái sử dụng phân tích/kế hoạch thực thi theo quy tắc DBMS |

**Không phải mọi lần gọi `Connection.prepareStatement()` trong JDBC đều tạo một đối tượng PostgreSQL SQL `PREPARE name AS ...` có tên.** Driver có thể dùng extended query protocol, statement không tên, hoặc chủ động tạo prepared statement trên server theo ngưỡng/cấu hình. Tính an toàn của bind **không phụ thuộc** việc server có cache plan theo tên hay chưa.

### 2.1. Prepared statement không hứa luôn nhanh hơn

Bind parameters giúp giảm rủi ro SQL injection do trộn giá trị với code. Việc giảm parse/plan overhead có thể là lợi ích bổ sung, nhưng đôi khi một **generic plan** không phù hợp với giá trị tham số hiếm hoặc phân bố dữ liệu lệch. Cần đo trên workload thật.

### 2.2. Bind thay giá trị, không thay cú pháp SQL

Có thể bind `user_id`, `email`, `status`, amount, timestamp và giới hạn trang trong những DBMS hỗ trợ:

```sql
WHERE user_id = ?
WHERE created_at >= ?
WHERE status = ?
LIMIT ?
```

Không thể tự hiểu:

```sql
FROM ?
ORDER BY ?
SELECT ? FROM users
```

`FROM ?` không chọn tên bảng. `ORDER BY ?` thường sắp xếp theo **một biểu thức giá trị/hằng**, không biến string `"created_at DESC"` thành tên cột kèm hướng sắp xếp. `SELECT ?` trả về một giá trị parameter, không tự đọc một cột được gọi tên bởi giá trị ấy.

## 3. Tạo dữ liệu PostgreSQL để học

Chạy trên một **session PostgreSQL riêng dành cho thực hành**. Các bảng `TEMP` chỉ tồn tại trong session tạo chúng; nếu muốn chạy JDBC/psycopg từ một connection khác, hãy tạo dữ liệu mẫu trên **chính connection đó** hoặc tạo schema trong database lab được phép.

```sql
CREATE TEMP TABLE demo_safe_users (
    user_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    user_role TEXT NOT NULL CHECK (
        user_role IN ('ADMIN', 'EDITOR', 'VIEWER')
    ),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    nickname TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, user_id),
    UNIQUE (tenant_id, email)
);

CREATE TEMP TABLE demo_safe_orders (
    order_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PAID', 'PENDING', 'CANCELED')
    ),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES demo_safe_users (tenant_id, user_id)
);

INSERT INTO demo_safe_users
    (user_id, tenant_id, email, display_name, user_role,
     is_active, nickname, metadata, created_at)
VALUES
    (1,10,'an@example.com','An','ADMIN',TRUE,NULL,
     '{"language":"vi","tags":["staff","vip"]}'::jsonb,
     '2026-10-01 08:00:00+07'),
    (2,10,'binh@example.com','Bình','EDITOR',TRUE,'Bình',
     '{"language":"vi"}'::jsonb,
     '2026-10-02 09:00:00+07'),
    (3,10,'chi@example.com','Chi','VIEWER',TRUE,'',
     '{"language":null}'::jsonb,
     '2026-10-03 09:00:00+07'),
    (4,10,'o''connor@example.com','O''Connor','VIEWER',TRUE,NULL,
     '{}'::jsonb,
     '2026-10-04 09:00:00+07'),
    (5,10,'dung@example.com','Dũng','VIEWER',FALSE,'Dũng',
     '{"language":"en"}'::jsonb,
     '2026-10-05 09:00:00+07'),
    (6,10,'ha@example.com','Hà','EDITOR',TRUE,'Hà',
     '{"language":"vi","tags":["ops"]}'::jsonb,
     '2026-10-05 09:00:00+07'),
    (7,20,'an@example.com','An tenant 20','ADMIN',TRUE,NULL,
     '{"language":"en"}'::jsonb,
     '2026-10-06 09:00:00+07'),
    (8,20,'linh@example.com','Linh tenant 20','VIEWER',TRUE,NULL,
     '{}'::jsonb,
     '2026-10-07 09:00:00+07');

INSERT INTO demo_safe_orders
    (order_id, tenant_id, user_id, status, amount, created_at)
VALUES
    (101,10,1,'PAID',    100.00,'2026-10-10 08:00:00+07'),
    (102,10,1,'PENDING',  50.00,'2026-10-11 08:00:00+07'),
    (103,10,2,'PAID',    200.00,'2026-10-11 08:00:00+07'),
    (104,10,3,'PAID',     75.00,'2026-10-12 08:00:00+07'),
    (105,10,4,'CANCELED',  0.00,'2026-10-12 08:00:00+07'),
    (106,10,5,'PAID',    120.00,'2026-10-13 08:00:00+07'),
    (107,10,6,'PAID',    300.00,'2026-10-14 08:00:00+07'),
    (108,20,7,'PAID',    900.00,'2026-10-14 08:00:00+07'),
    (109,20,8,'PENDING',  20.00,'2026-10-15 08:00:00+07');
```

Kiểm dữ liệu:

```sql
SELECT tenant_id, user_id, email, display_name, nickname, is_active
FROM demo_safe_users
ORDER BY tenant_id, user_id;

SELECT tenant_id, order_id, user_id, status, amount
FROM demo_safe_orders
ORDER BY order_id;
```

### 3.1. Những góc cạnh đã được cài vào dữ liệu

- Tenant **10** có user 1–6, trong đó user 5 **inactive**.
- Tenant **20** có user 7–8; hai tenant cùng có email `an@example.com`.
- Email user 4 chứa dấu nháy đơn `o'connor@example.com`.
- Nickname user 1 và 4 là **SQL NULL**, user 3 là **chuỗi rỗng**.
- Metadata JSONB có JSON `null` ở một field.
- Có đơn PAID, PENDING, CANCELED và amount khác nhau.

Nếu hợp đồng là “lấy user active của tenant 10”, kết quả chuẩn có **5 user**: 1, 2, 3, 4, 6. `PreparedStatement` không tự thêm bộ lọc `is_active`, cũng không tự kiểm việc client có quyền truy cập tenant 10.

## 4. PostgreSQL SQL PREPARE và EXECUTE

SQL-level `PREPARE` đặt tên một statement trong **session hiện tại**:

```sql
PREPARE demo_find_user_by_email(INTEGER, TEXT) AS
SELECT user_id, email, display_name
FROM demo_safe_users
WHERE tenant_id = $1
  AND email = $2;
```

Trong đó `$1` có kiểu `INTEGER` và `$2` có kiểu `TEXT`. Chúng được dùng **như giá trị**, không phải chuỗi ký tự thêm vào văn bản SQL.

Thực thi:

```sql
EXECUTE demo_find_user_by_email(10, 'an@example.com');
-- User 1.

EXECUTE demo_find_user_by_email(10, 'o''connor@example.com');
-- User 4.
```

**Chú ý:** đây là SQL gõ tay trong console, nên literal `o'connor@example.com` phải được viết theo cú pháp SQL literal (`'o''connor@example.com'`). Trong ứng dụng thực, hãy dùng binding API của driver, **không tự viết lại chuỗi literal** như vậy.

### 4.1. Một giá trị trông giống biểu thức SQL vẫn là giá trị

PostgreSQL cho phép viết một literal dưới dạng dollar-quoted string để dễ thấy ranh giới:

```sql
EXECUTE demo_find_user_by_email(
    10,
    $literal$x' OR '1'='1$literal$
);
-- Không trả user nào: toàn bộ input là một chuỗi email.
```

Cấu trúc của câu SQL đã PREPARE không bị thay thành điều kiện `OR`.

### 4.2. Xem prepared statements

```sql
SELECT name, statement, parameter_types
FROM pg_prepared_statements
WHERE name = 'demo_find_user_by_email';
```

View này cho biết các prepared statements trong **session hiện tại** theo phạm vi PostgreSQL. Nó không tự hiển thị mọi query parameterized từ các connection khác.

Giải phóng:

```sql
DEALLOCATE demo_find_user_by_email;
```

Nếu bạn mở Session B độc lập, nó **không tự có** statement tên `demo_find_user_by_email` đã chuẩn bị ở Session A.

### 4.3. Dùng giá trị kiểu số

```sql
PREPARE demo_get_order(INTEGER, INTEGER) AS
SELECT order_id, user_id, amount
FROM demo_safe_orders
WHERE tenant_id = $1
  AND order_id = $2;

EXECUTE demo_get_order(10, 101);
DEALLOCATE demo_get_order;
```

Với bảng demo, truy vấn trả một order có amount **100.00**. Nếu dùng tenant 20 và order 101, không có hàng. **Đúng cú pháp và đúng type** là cần, nhưng quyền được phép yêu cầu tenant 20 vẫn phải được kiểm tại ứng dụng/DB.

## 5. Placeholder khác nhau giữa các driver và dialect

| Môi trường | Marker thường gặp | Ví dụ |
| --- | --- | --- |
| PostgreSQL SQL-level PREPARE | `$1`, `$2` | `email = $2` |
| Java JDBC PreparedStatement | `?` | `email = ?` |
| Python psycopg | `%s`, `%(email)s` | `email = %s` |
| Node.js package `pg` | `$1`, `$2` | `email = $2` |
| MySQL driver | `?` | `email = ?` |
| SQLite | `?`, `?1`, `:email` | `email = :email` |
| SQL Server `sp_executesql` | `@email` | `email = @email` |
| Oracle driver | `:email`, `:1` tùy API | `email = :email` |

Không thay dấu đánh dấu tham số tùy tiện giữa driver. Đặc biệt, `%s` của psycopg là marker của **API driver**, **không** phải lời mời gọi Python string formatting để chèn email trước khi gửi query.

### 5.1. Không đặt parameter marker trong dấu nháy

Sai:

```java
String sql = "SELECT user_id FROM users WHERE email = '?'";
```

`'?'` chỉ là một SQL string literal chứa dấu `?`, không phải marker JDBC.

Đúng:

```java
String sql = "SELECT user_id FROM users WHERE email = ?";
ps.setString(1, email);
```

Tương tự trong PostgreSQL: `'$1'` là chuỗi văn bản, còn `$1` ở vị trí expression mới là parameter.

### 5.2. Marker không tự động là tên cột

`SELECT ? AS input` trả một giá trị được bind với alias `input`; nó không lấy cột có tên bằng giá trị truyền vào. SQL identifier phải thuộc cấu trúc query đã được xây từ lựa chọn tin cậy.

## 6. Java/JDBC: viết SELECT đầy đủ với PreparedStatement

Ví dụ một repository method có thể tái sử dụng:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class UserRepository {
    public record UserRow(int id, String email, String name) {}

    public static List<UserRow> findByEmail(
            Connection conn,
            int tenantId,
            String email
    ) throws SQLException {
        final String sql = """
            SELECT user_id, email, display_name
            FROM demo_safe_users
            WHERE tenant_id = ?
              AND is_active = TRUE
              AND email = ?
            ORDER BY user_id
            """;

        List<UserRow> rows = new ArrayList<>();
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setInt(1, tenantId);
            ps.setString(2, email);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    rows.add(new UserRow(
                        rs.getInt("user_id"),
                        rs.getString("email"),
                        rs.getString("display_name")
                    ));
                }
            }
        }
        return rows;
    }
}
```

Ở đây:

1. SQL có hai marker và cấu trúc cố định.
2. `setInt(1, tenantId)` bind integer.
3. `setString(2, email)` bind text.
4. `ResultSet` và `PreparedStatement` được đóng bằng try-with-resources.
5. Connection do caller sở hữu, nên repository **không tự đóng** connection nếu transaction manager bên ngoài cần tiếp tục dùng.

Java `record` yêu cầu phiên bản Java có hỗ trợ tính năng ấy. Nếu dùng Java cũ, thay bằng một data class thông thường. Để chạy với bảng TEMP, connection phải là chính session đã tạo bảng mẫu.

### 6.1. JDBC đánh số tham số từ 1

```java
ps.setInt(1, tenantId);
ps.setString(2, email);
```

Không phải index 0. Đảo thứ tự tham số có thể làm query lỗi type hoặc âm thầm trả sai hàng nếu các tham số cùng kiểu.

### 6.2. Không thêm dấu nháy vào giá trị

Sai:

```java
ps.setString(2, "'" + email + "'");
```

Driver đã truyền đây là text; đoạn trên sẽ tìm email có **dấu nháy ở hai đầu** thật, không phải email gốc.

### 6.3. Tìm email có dấu nháy

Gọi method với:

```java
findByEmail(conn, 10, "o'connor@example.com");
```

Trong lab, nếu cùng session, kết quả là user 4. Không cần một quy tắc riêng để sửa dấu nháy của input trước khi bind.

## 7. PreparedStatement cho INSERT, UPDATE và DELETE

Parameterization áp dụng cả các thao tác ghi.

### 7.1. INSERT có type rõ

```java
String sql = """
    INSERT INTO demo_safe_orders
        (order_id, tenant_id, user_id, status, amount, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, 200);
    ps.setInt(2, 10);
    ps.setInt(3, 1);
    ps.setString(4, "PENDING");
    ps.setBigDecimal(5, new java.math.BigDecimal("25.50"));
    ps.setObject(6, java.time.OffsetDateTime.now());
    int inserted = ps.executeUpdate();
    if (inserted != 1) {
        throw new SQLException("Expected exactly one inserted order");
    }
}
```

Đây là đoạn code minh họa cho DB lab. `BigDecimal` biểu thị số thập phân chính xác; `OffsetDateTime` cần JDBC driver hỗ trợ mapping `TIMESTAMPTZ` phù hợp.

### 7.2. UPDATE với điều kiện tenant

```java
String sql = """
    UPDATE demo_safe_users
    SET nickname = ?
    WHERE tenant_id = ?
      AND user_id = ?
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, nickname);
    ps.setInt(2, tenantId);
    ps.setInt(3, userId);
    int changed = ps.executeUpdate();
    if (changed != 1) {
        throw new SQLException("Expected one updated user");
    }
}
```

Một UPDATE trả **0 hàng** là tình huống hợp lệ về SQL, có thể do không có user hoặc không đúng tenant. Một UPDATE trả hơn một hàng là dấu hiệu logic/khóa sai nếu nghiệp vụ yêu cầu đúng một. **Prepared statement không tự kiểm số hàng hoặc quyền.**

### 7.3. DELETE có status

```java
String sql = """
    DELETE FROM demo_safe_orders
    WHERE tenant_id = ?
      AND order_id = ?
      AND status = ?
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, tenantId);
    ps.setInt(2, orderId);
    ps.setString(3, "CANCELED");
    int deleted = ps.executeUpdate();
}
```

Nếu đã chặn xóa đơn thanh toán, một câu DELETE chỉ bind order_id nhưng **bỏ điều kiện status** vẫn có thể là lỗi nghiêm trọng. Binding giữ cấu trúc không bị thay bởi user input; nó không tự chọn **đúng cấu trúc nghiệp vụ**.

## 8. Python/psycopg: truyền giá trị là đối số riêng của execute

Trong psycopg (ví dụ API psycopg 3):

```python
import psycopg

with psycopg.connect(
    "dbname=training user=training_user"
) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id, email, display_name
            FROM demo_safe_users
            WHERE tenant_id = %s
              AND email = %s
            """,
            (10, "an@example.com"),
        )
        for row in cur.fetchall():
            print(row)
```

Đây là cấu hình kết nối minh họa, không phải lý do để hardcode mật khẩu hoặc credentials production. Khi dùng bảng TEMP, code tạo dữ liệu phải chạy trên **cùng connection**.

### 8.1. Không dùng f-string hoặc Python format để chèn giá trị

Không an toàn:

```python
sql = f"SELECT * FROM users WHERE email = '{email_from_request}'"
cur.execute(sql)
```

Nên dùng:

```python
cur.execute(
    "SELECT * FROM users WHERE email = %s",
    (email_from_request,),
)
```

Dấu phẩy trong `(email_from_request,)` tạo tuple một phần tử. Nếu viết `(email_from_request)` thì đó chỉ là biểu thức ngoặc, không phải tuple.

### 8.2. Không thêm nháy quanh %s

Sai:

```python
cur.execute(
    "SELECT * FROM users WHERE email = '%s'",
    (email,),
)
```

Đúng:

```python
cur.execute(
    "SELECT * FROM users WHERE email = %s",
    (email,),
)
```

### 8.3. Psycopg và identifier động

Psycopg có `psycopg.sql.Identifier` giúp quote identifier:

```python
from psycopg import sql

allowed_columns = {"email", "display_name", "created_at"}
if requested_column not in allowed_columns:
    raise ValueError("Unsupported column")

stmt = sql.SQL(
    "SELECT user_id, email FROM demo_safe_users "
    "WHERE tenant_id = %s ORDER BY {}"
).format(sql.Identifier(requested_column))

cur.execute(stmt, (10,))
```

**Identifier quoting** giúp cấu trúc SQL hợp lệ; **allowlist** mới quyết định người gọi được phép sử dụng cột nào. Đừng chỉ dùng `Identifier(user_input)` mà bỏ kiểm quyền và giới hạn cột.

## 9. Node.js với pg: tham số $1, $2

Với package `pg`:

```javascript
const sql = [
  "SELECT user_id, email, display_name",
  "FROM demo_safe_users",
  "WHERE tenant_id = $1",
  "AND is_active = TRUE",
  "AND email = $2"
].join(" ");

const result = await pool.query(sql, [tenantId, emailFromRequest]);
console.log(result.rows);
```

`[tenantId, emailFromRequest]` là mảng giá trị được bind cho `$1`, `$2`.

Không nối input:

```javascript
const sql = "SELECT * FROM users WHERE email = '" +
            emailFromRequest + "'";
await pool.query(sql);
```

### 9.1. Named query

```javascript
const result = await client.query({
  name: "safe-find-user-v1",
  text: [
    "SELECT user_id, email",
    "FROM demo_safe_users",
    "WHERE tenant_id = $1 AND email = $2"
  ].join(" "),
  values: [tenantId, emailFromRequest],
});
```

Trong `pg`, một query được đặt tên có thể được driver/server tái sử dụng trên **connection tương ứng**. Không đặt tên mới cho mỗi email vì sẽ làm số prepared statements lớn mà không tạo thêm lợi ích bảo mật.

### 9.2. Transaction phải dùng cùng client

Không gọi `pool.query("BEGIN")` rồi hy vọng những lần `pool.query(...)` khác dùng cùng connection. Mỗi lần pool có thể cấp client khác. Đúng hơn:

```javascript
const client = await pool.connect();
try {
  await client.query("BEGIN");
  await client.query(
    "UPDATE demo_safe_users SET nickname = $1 WHERE tenant_id = $2 AND user_id = $3",
    [nickname, tenantId, userId]
  );
  await client.query("COMMIT");
} catch (err) {
  try {
    await client.query("ROLLBACK");
  } catch (rollbackError) {
    // Log an toàn và không che mất lỗi ban đầu.
  }
  throw err;
} finally {
  client.release();
}
```

Đây là mẫu đơn giản. Với connection lỗi ngay lúc COMMIT, kết quả commit có thể không rõ; hệ thống quan trọng cần idempotency và đối soát. Prepared statement và transaction giải quyết **hai bài toán độc lập**.

## 10. Bind đúng kiểu dữ liệu

| Dữ liệu | JDBC gợi ý | Lưu ý |
| --- | --- | --- |
| ID integer | `setInt`, `setLong` | Kiểm giới hạn và quyền |
| Văn bản | `setString` | Unicode, length, collation |
| Giá tiền | `setBigDecimal` | Precision/scale/rounding |
| Boolean | `setBoolean` | Khác string `"true"` |
| DATE | `setObject(LocalDate)` theo driver | Ngày không giống instant |
| TIMESTAMPTZ | `setObject(OffsetDateTime)` theo driver | Timezone và range |
| SQL NULL | `setNull(index, Types.XXX)` | Type phải rõ trong ngữ cảnh |
| Array | `createArrayOf`, `setArray` | Không phải CSV string |
| JSON/JSONB | Serialize JSON, cast hoặc binder typed | Validate cấu trúc JSON riêng |
| Binary | `setBytes`/stream | Giới hạn kích thước |

### 10.1. Decimal không nên đi qua double tùy tiện

```java
ps.setBigDecimal(1, new java.math.BigDecimal("25.50"));
```

thể hiện số tiền theo decimal chính xác, tránh một số lỗi làm tròn khi tạo `BigDecimal` từ `double`. Bind vẫn phải phối hợp CHECK constraints và giới hạn giá trị tiền.

### 10.2. Timestamp phải có ý nghĩa timezone

```sql
PREPARE demo_created_after(TIMESTAMPTZ) AS
SELECT order_id, created_at
FROM demo_safe_orders
WHERE created_at >= $1;

EXECUTE demo_created_after('2026-10-11 00:00:00+07');
DEALLOCATE demo_created_after;
```

Đừng coi `"2026-10-11"` là một instant có timezone tự hiển nhiên. Với khoảng ngày nghiệp vụ, xác định timezone rồi tính mốc bắt đầu/kết thúc chính xác.

### 10.3. Value parameters không phải phép ép kiểu vô hạn

Một `TEXT` dài quá giới hạn của ứng dụng hoặc một số vượt phạm vi của cột vẫn có thể báo lỗi, dù bind an toàn khỏi injection. Validation type/range là bắt buộc.

## 11. SQL NULL và giá trị bind

Trong SQL, `nickname = NULL` không trả TRUE cho nickname NULL. Nó trả `UNKNOWN`, và `WHERE` loại những hàng không TRUE. Bind SQL NULL **không làm thay đổi quy tắc ba giá trị**.

```sql
PREPARE demo_nickname_equals(TEXT) AS
SELECT user_id, nickname
FROM demo_safe_users
WHERE tenant_id = 10
  AND nickname = $1
ORDER BY user_id;

EXECUTE demo_nickname_equals(NULL);
-- Không trả các user có nickname SQL NULL.

DEALLOCATE demo_nickname_equals;
```

Muốn lọc NULL:

```sql
SELECT user_id, nickname
FROM demo_safe_users
WHERE tenant_id = 10
  AND nickname IS NULL;
-- User 1 và 4.
```

### 11.1. PostgreSQL IS NOT DISTINCT FROM

So sánh null-safe:

```sql
PREPARE demo_nickname_nullable(TEXT) AS
SELECT user_id, nickname
FROM demo_safe_users
WHERE tenant_id = 10
  AND nickname IS NOT DISTINCT FROM $1
ORDER BY user_id;

EXECUTE demo_nickname_nullable(NULL);
-- User 1 và 4.

EXECUTE demo_nickname_nullable('');
-- User 3: nickname là chuỗi rỗng.

DEALLOCATE demo_nickname_nullable;
```

Hai biểu thức `= $1` và `IS NOT DISTINCT FROM $1` **không tương đương khi tham số NULL**.

### 11.2. JDBC setNull

```java
if (nickname == null) {
    ps.setNull(1, java.sql.Types.VARCHAR);
} else {
    ps.setString(1, nickname);
}
```

`setNull` bind một **giá trị SQL NULL có kiểu rõ**; nó không tự viết lại `= ?` thành `IS NULL`. Hãy chọn SQL predicate đúng contract.

### 11.3. Ba trạng thái filter của API

Một API PATCH/search có thể phân biệt:

- **Không gửi nickname**: không lọc hoặc không cập nhật field.
- **Gửi nickname: null**: tìm/gán giá trị SQL NULL theo contract.
- **Gửi nickname: ""**: tìm/gán chuỗi rỗng.

Nếu deserialization làm cả hai tình huống đầu thành một biến Java `null`, prepared statement không thể tự khôi phục thông tin. Cần giữ **cờ field presence** hoặc kiểu request thể hiện rõ trạng thái.

## 12. LIKE, ILIKE và wildcard

Parameterization tránh SQL injection, nhưng **không xóa ý nghĩa của `%` và `_` trong LIKE**.

```sql
PREPARE demo_search_name(TEXT) AS
SELECT user_id, display_name
FROM demo_safe_users
WHERE tenant_id = 10
  AND display_name ILIKE $1
ORDER BY user_id;

EXECUTE demo_search_name('%an%');
DEALLOCATE demo_search_name;
```

`ILIKE` là cú pháp PostgreSQL tìm không phân biệt chữ hoa/thường theo quy tắc collation liên quan. Trong pattern, `%` khớp chuỗi bất kỳ, `_` khớp một ký tự.

### 12.1. Tìm văn bản literal phải escape LIKE riêng

Nếu người dùng nhập `50%` và muốn tìm đúng ký tự phần trăm, chỉ bind `%` vào LIKE không đủ: `%` vẫn là wildcard.

Một cách chọn `!` làm ký tự escape:

```java
static String escapeLike(String text) {
    return text
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}

String sql = """
    SELECT user_id, display_name
    FROM demo_safe_users
    WHERE tenant_id = ?
      AND display_name ILIKE ? ESCAPE '!'
    ORDER BY user_id
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, tenantId);
    ps.setString(2, "%" + escapeLike(searchText) + "%");
    // ps.executeQuery()...
}
```

Ứng dụng chủ ý thêm `%` ở hai đầu cho phép tìm chuỗi chứa văn bản người dùng, còn `%`, `_`, `!` bên trong input được escape thành literal. **Escape wildcard LIKE** khác hoàn toàn **escape SQL string literal**; binding đã bảo vệ ranh giới code/data.

### 12.2. Prefix search và contains search

`LIKE 'abc%'` có thể được một số index hỗ trợ tốt hơn `LIKE '%abc%'`, tùy DBMS, collation, operator class và kế hoạch. Nhưng đừng đổi contains thành prefix chỉ để làm query nhanh nếu kết quả nghiệp vụ phải tìm chuỗi chứa từ khóa.

### 12.3. Regex cũng có meta-character

Nếu API hỗ trợ regex search, dữ liệu bind vẫn có **nghĩa regex**, dù không còn khả năng thay cấu trúc SQL. Muốn tìm literal regex text, cần escaping theo regex; muốn chấp nhận pattern người dùng, cần giới hạn độ dài/độ phức tạp/timeout để giảm truy vấn quá nặng.

## 13. IN với danh sách nhiều ID

Một placeholder không tự biến một CSV text thành ba giá trị.

Sai về logic:

```java
String sql = "SELECT user_id FROM users WHERE user_id IN (?)";
ps.setString(1, "1,2,4");
```

Driver coi `"1,2,4"` là **một string**; database không tự tách nó thành ba integers trong `IN`.

### 13.1. PostgreSQL = ANY với array

```sql
PREPARE demo_find_ids(INTEGER, INTEGER[]) AS
SELECT user_id, email
FROM demo_safe_users
WHERE tenant_id = $1
  AND user_id = ANY($2)
ORDER BY user_id;

EXECUTE demo_find_ids(10, ARRAY[1,2,4]::INTEGER[]);
-- User 1, 2, 4.

EXECUTE demo_find_ids(10, ARRAY[]::INTEGER[]);
-- Không có hàng.

DEALLOCATE demo_find_ids;
```

`= ANY(empty_array)` không khớp hàng nào theo ngữ nghĩa bình thường. Nếu array chứa NULL hoặc bản thân array là SQL NULL, kết quả so sánh có thể là `UNKNOWN`; phải hiểu logic ba giá trị.

### 13.2. JDBC PostgreSQL Array

```java
String sql = """
    SELECT user_id, email
    FROM demo_safe_users
    WHERE tenant_id = ?
      AND user_id = ANY(?::integer[])
    ORDER BY user_id
    """;

java.sql.Array idsArray =
    conn.createArrayOf("integer", new Object[] {1, 2, 4});
try {
    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setInt(1, 10);
        ps.setArray(2, idsArray);
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getInt("user_id"));
            }
        }
    }
} finally {
    idsArray.free();
}
```

Hỗ trợ `java.sql.Array` và cú pháp cast phụ thuộc driver. Không tự nối các ID vào SQL.

### 13.3. Sinh số lượng marker bằng code, rồi bind từng giá trị

```java
List<Integer> ids = List.of(1, 2, 4);
if (ids.isEmpty()) {
    // Một API trả List có thể trả danh sách rỗng ngay tại đây.
}

String placeholders = String.join(
    ", ", java.util.Collections.nCopies(ids.size(), "?")
);
String sql =
    "SELECT user_id FROM demo_safe_users " +
    "WHERE tenant_id = ? AND user_id IN (" + placeholders + ")";

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, tenantId);
    for (int i = 0; i < ids.size(); i++) {
        ps.setInt(i + 2, ids.get(i));
    }
    // executeQuery()...
}
```

**Đoạn này là fragment**: khi danh sách rỗng phải thực sự return kết quả rỗng hoặc dùng nhánh query khác, bởi `IN ()` không hợp lệ trong nhiều DBMS. Đây là trường hợp **chuỗi SQL nối từ dấu hỏi do code tạo**, không chèn giá trị người dùng. Giới hạn kích thước list và số tham số để tránh query khổng lồ; với danh sách lớn, cân nhắc staging/table-valued parameters tùy DBMS.

### 13.4. NOT IN và NULL

`NOT IN` khi danh sách hoặc subquery chứa NULL có thể cho `UNKNOWN` với những giá trị không khớp. `NOT EXISTS` với điều kiện tương quan rõ là một lựa chọn cho bài toán “không tồn tại hàng khớp”, nhưng **không luôn tương đương** nếu không xác định ngữ nghĩa NULL ở hai phía.

## 14. ORDER BY động: không bind tên cột

Một API cho client chọn:

```text
sortBy = created
sortDirection = desc
```

Không an toàn:

```java
String sql = "SELECT ... FROM users ORDER BY " +
             sortBy + " " + sortDirection;
```

Nhưng cũng không thể dùng `ORDER BY ?` rồi bind `"created_at DESC"` và mong database diễn giải giá trị ấy thành cú pháp sort.

### 14.1. Dùng allowlist ánh xạ lựa chọn

```java
static String sortColumn(String requested) {
    return switch (requested) {
        case "email" -> "email";
        case "name" -> "display_name";
        case "created" -> "created_at";
        default -> throw new IllegalArgumentException("Unsupported sort");
    };
}

static String sortDirection(String requested) {
    return switch (requested) {
        case "asc" -> "ASC";
        case "desc" -> "DESC";
        default -> throw new IllegalArgumentException("Unsupported direction");
    };
}

String order = sortColumn(requestedSort) + " " +
               sortDirection(requestedDirection);
String sql =
    "SELECT user_id, email, display_name FROM demo_safe_users " +
    "WHERE tenant_id = ? AND is_active = ? " +
    "ORDER BY " + order + ", user_id ASC LIMIT ?";

if (requestedLimit < 1 || requestedLimit > 100) {
    throw new IllegalArgumentException("Limit out of range");
}

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setInt(1, tenantId);
    ps.setBoolean(2, true);
    ps.setInt(3, requestedLimit);
    // executeQuery()...
}
```

Ở đây chỉ nối những **fragment SQL cố định do code định nghĩa**. Values tenant, active và limit vẫn bind.

### 14.2. Identifier hợp lệ chưa chắc được phép

Ngay cả khi tên cột được quote đúng, API không nên cho caller sắp xếp/lọc theo `password_hash`, `secret_note` hay các cột nội bộ không nằm trong contract. **Allowlist là quyết định nghiệp vụ và quyền**, không chỉ escaping cú pháp.

### 14.3. Pagination cần tie-breaker

Nếu nhiều user cùng `created_at`, `ORDER BY created_at DESC LIMIT 10` có thể chọn các hàng khác nhau khi plan thay đổi. Thêm `user_id ASC` là khóa unique giúp thứ tự xác định trên cùng snapshot. Bind tham số không tự làm pagination ổn định.

## 15. Tên bảng/schema động không phải giá trị

`FROM ?` trong JDBC hoặc `FROM $1` trong PostgreSQL SQL PREPARE không tự thay bằng table name. Một tên bảng là **SQL identifier cần parser xác định trong cấu trúc lệnh**.

Khi thực sự cần nhiều bảng báo cáo, nên:

1. Ưu tiên một schema ổn định, partitioning hoặc view khi phù hợp.
2. Map business option như `"monthly"` sang tên bảng/view cố định do code kiểm soát.
3. Dùng API quote identifier của dialect.
4. Kiểm quyền được chọn bảng, không chỉ kiểm chuỗi là tên hợp lệ.
5. Tiếp tục bind mọi giá trị WHERE/LIMIT.

### 15.1. Identifier quoting không thay allowlist

Trong PostgreSQL, `format('%I', identifier)` và `quote_ident` giúp quote định danh theo cú pháp. Nhưng **quote một tên cột nhạy cảm** vẫn tạo một identifier hợp lệ về SQL. Để an toàn về nghiệp vụ, bạn phải có **allowlist** quyết định caller được yêu cầu cột nào.

### 15.2. Đừng xây multi-tenant SQL bằng tên bảng từ request

Một thiết kế tạo `users_tenant_10`, `users_tenant_20` rồi lấy hậu tố từ HTTP request có thể làm tăng nguy cơ sai phạm vi/SQL injection nếu dựng tên không được kiểm soát. Nhiều trường hợp nên dùng cột tenant_id, RLS/permission, partitioning hoặc một ánh xạ server-side rõ hơn.

## 16. PL/pgSQL: EXECUTE dynamic SQL với USING

SQL động đôi khi cần thiết, nhưng phần identifier và phần value phải xử lý riêng:

```sql
DO $$
DECLARE
    v_column TEXT := 'email';
    v_value TEXT := 'an@example.com';
    v_tenant INTEGER := 10;
    v_count BIGINT;
BEGIN
    IF v_column NOT IN ('email', 'display_name') THEN
        RAISE EXCEPTION 'Unsupported column: %', v_column;
    END IF;

    EXECUTE format(
        'SELECT COUNT(*) FROM demo_safe_users
         WHERE tenant_id = $1 AND %I = $2',
        v_column
    )
    INTO v_count
    USING v_tenant, v_value;

    RAISE NOTICE 'Count: %', v_count;
END;
$$;
```

Trong ví dụ:

- `format('%I', v_column)` tạo identifier hợp lệ.
- `IF v_column NOT IN (...)` giới hạn các identifier được phép.
- `$1`, `$2` nằm **trong chuỗi SQL động** được PL/pgSQL xử lý bằng `EXECUTE ... USING`.
- `USING` cung cấp **values** mà không cần ghép chúng vào command text.

### 16.1. Hai loại EXECUTE trong PostgreSQL

**SQL-level:**

```sql
PREPARE demo_q(INTEGER) AS
SELECT user_id FROM demo_safe_users WHERE tenant_id = $1;
EXECUTE demo_q(10);
DEALLOCATE demo_q;
```

**PL/pgSQL:**

```text
EXECUTE command_string INTO result USING value1, value2;
```

Đừng trộn hai cú pháp. `EXECUTE prepared_name USING ...` không phải dạng SQL-level PREPARE/EXECUTE của PostgreSQL.

### 16.2. Tránh dùng format('%s', input) cho giá trị

`format('%I', ...)` phục vụ identifier, `format('%L', ...)` có khả năng quote literal, nhưng khi giá trị được bind qua `USING`, **ưu tiên USING**. `format('%s', user_input)` chèn nguyên text có thể mở lại rủi ro injection.

### 16.3. SECURITY DEFINER và search_path

Hàm PostgreSQL `SECURITY DEFINER` có thể chạy với quyền của owner. Nếu hàm dựng SQL động từ input, cho caller chọn bảng tùy ý hoặc dựa vào `search_path` không kiểm soát, hậu quả có thể vượt quyền caller.

Khi thật sự cần hàm có quyền cao, phải hạn chế quyền owner, kiểm/scope `search_path`, schema-qualify các object phù hợp, allowlist identifiers, bind values, kiểm quyền nghiệp vụ và test cả dữ liệu từ nơi không tin cậy.

## 17. Tham số hóa JSON/JSONB

Một HTTP request có thể gửi:

```json
{
  "language": "vi",
  "tags": ["staff", "vip"],
  "note": "Có dấu nháy ' trong văn bản"
}
```

Không an toàn:

```java
String sql = "UPDATE users SET metadata = '" +
             jsonRaw + "' WHERE user_id = " + userId;
```

Với PostgreSQL JDBC, có thể bind string JSON rồi cast rõ:

```java
String sql = """
    UPDATE demo_safe_users
    SET metadata = CAST(? AS jsonb)
    WHERE tenant_id = ?
      AND user_id = ?
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, jsonRaw);
    ps.setInt(2, tenantId);
    ps.setInt(3, userId);
    int changed = ps.executeUpdate();
}
```

Driver giữ `jsonRaw` là dữ liệu; PostgreSQL kiểm tính hợp lệ khi cast thành JSONB.

### 17.1. Valid JSON không phải valid business schema

JSON:

```json
{"language": 42, "tags": "not-an-array"}
```

có thể hợp cú pháp JSON nhưng sai type theo business. Parameterization không tự ràng buộc `language` phải string hoặc `tags` là array. Cần schema validation, constraints và kiểm quyền field.

### 17.2. SQL NULL khác JSON null

`NULL::jsonb` là **SQL NULL**, còn `'null'::jsonb` là **giá trị JSON null**. Nếu bind một SQL NULL vào cột JSONB `NOT NULL`, DB có thể báo vi phạm constraint; nếu bind chuỗi JSON `null` rồi cast, bạn đang lưu JSON null, không phải SQL NULL. Cần phân biệt theo contract.

### 17.3. JSON path do client cung cấp

Nếu API cho phép sửa `metadata.some_path`, người dùng vẫn không được tự chọn nhánh `roles`, `is_admin`, `permissions` hoặc thông tin nhạy cảm chỉ vì giá trị mới đã bind. Kiểm path được phép, type cấu trúc, quyền và giới hạn độ sâu/độ lớn.

## 18. LIMIT/OFFSET và timestamp cũng là values

Trong PostgreSQL:

```sql
PREPARE demo_order_page(
    INTEGER, TEXT, TIMESTAMPTZ, TIMESTAMPTZ,
    INTEGER, INTEGER
) AS
SELECT order_id, amount, created_at
FROM demo_safe_orders
WHERE tenant_id = $1
  AND status = $2
  AND created_at >= $3
  AND created_at < $4
ORDER BY created_at DESC, order_id DESC
LIMIT $5 OFFSET $6;

EXECUTE demo_order_page(
    10,
    'PAID',
    '2026-10-10 00:00:00+07',
    '2026-10-15 00:00:00+07',
    3,
    0
);

DEALLOCATE demo_order_page;
```

Các vị trí của status, tenant, mốc thời gian và limit/offset đều là **giá trị** và có thể bind trong PostgreSQL.

### 18.1. Parameterization không thay giới hạn tài nguyên

Input `LIMIT 100000000` được bind an toàn nhưng có thể bắt server xử lý cực nhiều dữ liệu. Hãy giới hạn **page size**, độ dài pattern search, số ID trong IN-list, offset tối đa/rate limit và query timeout.

### 18.2. Khoảng ngày nửa mở

`created_at >= start AND created_at < end` thường phù hợp với khoảng ngày `[start,end)` để tránh nhầm sự kiện đúng 00:00 ngày sau. Mốc `start/end` phải được tính đúng timezone nghiệp vụ, nhất là ngày có DST hoặc hệ thống lưu `TIMESTAMPTZ`.

### 18.3. Keyset pagination

```sql
PREPARE demo_keyset(INTEGER, TIMESTAMPTZ, INTEGER, INTEGER) AS
SELECT order_id, created_at, amount
FROM demo_safe_orders
WHERE tenant_id = $1
  AND (created_at, order_id) < ($2, $3)
ORDER BY created_at DESC, order_id DESC
LIMIT $4;

EXECUTE demo_keyset(
    10, '2026-10-14 08:00:00+07', 107, 5
);

DEALLOCATE demo_keyset;
```

Cursor là **typed values**, còn danh sách sort keys là cấu trúc SQL cố định. Keyset có thể giúp phân trang tốt hơn OFFSET lớn trong nhiều tình huống, nhưng cần quy định xử lý dữ liệu thay đổi giữa các trang.

## 19. Batch execution với PreparedStatement

Một PreparedStatement có thể nhận nhiều **bộ tham số**:

```java
String sql = """
    INSERT INTO demo_safe_orders
        (order_id, tenant_id, user_id, status, amount, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    for (OrderInput o : inputs) {
        ps.setInt(1, o.orderId());
        ps.setInt(2, o.tenantId());
        ps.setInt(3, o.userId());
        ps.setString(4, o.status());
        ps.setBigDecimal(5, o.amount());
        ps.setObject(6, o.createdAt());
        ps.addBatch();
    }
    int[] affected = ps.executeBatch();
}
```

Đây là fragment giả định có `OrderInput` và `inputs`, không phải chương trình Java độc lập. Batching có thể giảm round trips, nhưng **không tự biến toàn bộ batch thành một transaction all-or-nothing**.

### 19.1. Transaction cho batch

```java
boolean oldAutoCommit = conn.getAutoCommit();
try {
    conn.setAutoCommit(false);
    // Thực hiện prepared batch và các statement liên quan.
    conn.commit();
} catch (SQLException ex) {
    try {
        conn.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
} finally {
    conn.setAutoCommit(oldAutoCommit);
}
```

**Lưu ý:** đổi autocommit khi transaction còn mở có thể dẫn tới commit theo JDBC contract; phải đảm bảo transaction kết thúc đúng. Nếu connection bị lỗi tại thời điểm COMMIT, kết quả có thể không rõ; không tái sử dụng connection bị hỏng một cách mù quáng. Trong framework quản lý transaction, repository thường **không tự set autocommit**.

### 19.2. Batch có lỗi giữa chừng

Cách driver báo update counts, dừng hoặc tiếp tục batch khi gặp lỗi, và mức rollback phụ thuộc driver/DBMS/transaction. Không kết luận “tất cả đã commit” chỉ từ việc đã gọi `executeBatch()`. Dùng ràng buộc, kiểm row counts, transaction và retry/idempotency theo yêu cầu.

### 19.3. Khối lượng cực lớn

`INSERT ... SELECT`, bulk loader, staging table hoặc PostgreSQL `COPY` có thể tốt hơn nhiều lần execute cho dữ liệu rất lớn. Nhưng cách nhập dữ liệu ấy vẫn cần validate schema, quyền, giới hạn tài nguyên và chống injection ở **các phần SQL động** liên quan.

## 20. Prepared statements và kế hoạch thực thi

Bind parameters có thể giúp giảm một phần chi phí parse/plan khi tái thực thi, tùy engine/driver. Nhưng thời gian truy vấn còn phụ thuộc index, statistics, joins, sort, I/O, row counts, locks, network và giá trị tham số.

### 20.1. PostgreSQL EXPLAIN EXECUTE

```sql
PREPARE demo_orders_for_tenant(INTEGER, TEXT) AS
SELECT order_id, amount
FROM demo_safe_orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY order_id;

EXPLAIN EXECUTE demo_orders_for_tenant(10, 'PAID');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE demo_orders_for_tenant(10, 'PAID');

DEALLOCATE demo_orders_for_tenant;
```

`EXPLAIN EXECUTE` cho biết plan dự kiến; `EXPLAIN (ANALYZE, BUFFERS) EXECUTE` **thực thi query SELECT** để ghi actual time/rows/buffers.

### 20.2. Generic vs custom plan

PostgreSQL có thể dùng:

- **Custom plan:** được lập xét các giá trị tham số cụ thể.
- **Generic plan:** một kế hoạch được tái sử dụng cho nhiều giá trị.

Khi tenant 10 có 10 triệu hàng còn tenant 20 chỉ vài chục, phân bố lệch có thể khiến plan tối ưu cho một giá trị nhưng kém cho giá trị khác. `plan_cache_mode` với các chế độ như `auto`, `force_custom_plan`, `force_generic_plan` là công cụ nghiên cứu nâng cao trong PostgreSQL; đừng đổi cấu hình production khi chưa có benchmark đại diện.

### 20.3. Server-side lifecycle

Prepared statements thường có phạm vi **connection/session**. Connection pool/reconnect, driver prepare threshold, schema thay đổi và invalidation có thể tác động đến cache. Nếu tạo tên statement mới cho mỗi email hoặc mỗi request, hệ thống có thể dùng nhiều tài nguyên hơn thay vì tối ưu.

### 20.4. SQL Server parameter sniffing

SQL Server có những hành vi plan caching và parameter sensitivity thường được gọi bằng thuật ngữ **parameter sniffing**. Khi query nhanh với một input nhưng chậm với input khác, cần xem actual plans, data skew, statistics, Query Store và tính năng của phiên bản đang dùng. Đừng quay lại nối literal trực tiếp với user input để “chữa” plan vì như thế tái tạo rủi ro injection.

### 20.5. EXPLAIN ANALYZE trên DML

`EXPLAIN ANALYZE UPDATE ...` trong PostgreSQL **thực thi UPDATE thật**. Nếu đo DML trong database lab, dùng transaction có `ROLLBACK` khi phù hợp, nhưng nhớ rollback không đảo mọi side effect ngoài database. Không chạy đo thử destructive DML trên hệ thống thật chỉ để xem plan.

## 21. Index, predicate và parameterization

Trong lab PostgreSQL:

```sql
CREATE INDEX idx_demo_safe_user_tenant_email
ON demo_safe_users (tenant_id, email);

CREATE INDEX idx_demo_safe_orders_tenant_status_time
ON demo_safe_orders (tenant_id, status, created_at DESC);
```

Xem kế hoạch:

```sql
PREPARE demo_search_users(INTEGER, TEXT) AS
SELECT user_id, display_name
FROM demo_safe_users
WHERE tenant_id = $1
  AND email = $2;

EXPLAIN EXECUTE demo_search_users(10, 'an@example.com');
DEALLOCATE demo_search_users;
```

Với bảng chỉ tám user, PostgreSQL có thể chọn Seq Scan vì rẻ hơn index. Đó không chứng minh index hay binding vô dụng trong dữ liệu lớn.

### 21.1. Function trên cột có thể đổi cách dùng index

```sql
WHERE lower(email) = lower($1)
```

không giống hoàn toàn:

```sql
WHERE email = $1
```

về case sensitivity, và có thể cần expression index hoặc collation phù hợp. Không bỏ `lower` chỉ vì muốn dùng một index đơn giản nếu yêu cầu tìm kiếm không phân biệt chữ hoa/thường.

### 21.2. Không bỏ tenant filter để plan nhanh hơn

`WHERE email = $1` có thể chạy nhanh nhưng vẫn trả dữ liệu tenant 20 khi input trùng tenant 10 nếu caller không được phép. Một query an toàn về injection vẫn có thể là **lỗi phân quyền**.

## 22. SQL injection khác Broken Object Level Authorization

Query:

```sql
SELECT user_id, email
FROM demo_safe_users
WHERE user_id = $1;
```

có thể được parameterized hoàn toàn, nhưng người dùng vẫn có thể thử `user_id` của tài khoản khác. Nếu business không kiểm quyền, đó là **Broken Object Level Authorization (BOLA/IDOR)**, không phải SQL injection.

### 22.1. Tenant lấy từ principal được xác thực

```sql
SELECT user_id, email
FROM demo_safe_users
WHERE tenant_id = $1
  AND user_id = $2;
```

`tenant_id` nên được gắn với **principal đã xác thực và được ủy quyền**, không tin mù quáng giá trị client gửi trong body/query string. Bind `tenant_id=20` chỉ bảo đảm số 20 là dữ liệu, không chứng minh caller có quyền xem tenant 20.

### 22.2. Quyền database tối thiểu

- Role chỉ đọc không cần quyền `DROP TABLE`, `ALTER ROLE` hoặc đọc tất cả bảng nhạy cảm.
- Role ứng dụng không nên là superuser.
- Phân quyền SELECT/INSERT/UPDATE/DELETE phù hợp theo tính năng.
- Đọc credential từ cơ chế secrets an toàn, không hardcode mật khẩu vào source.
- Kiểm những đường raw SQL/stored procedure bên cạnh các query parameterized.

### 22.3. PostgreSQL Row-Level Security

RLS có thể đặt policy giới hạn hàng người dùng/role được đọc hoặc ghi. Nó là lớp bổ trợ cho authorization, không tự được bật chỉ vì query dùng prepared statement. Phải hiểu role owner/bypass, session settings, connection pool, policy và điều kiện tenant context trước khi đưa vào production.

### 22.4. Constraints và transaction

CHECK, NOT NULL, UNIQUE, FOREIGN KEY và transaction giữ bất biến dữ liệu, còn parameterization bảo vệ ranh giới cú pháp. Một thao tác chuyển tiền có thể dùng bind an toàn nhưng vẫn sai nếu quên kiểm đủ tiền, kiểm số hàng debit/credit hoặc gộp commit đúng connection.

## 23. Second-order SQL injection

Input không đáng tin có thể được **lưu an toàn vào database** nhưng về sau lại được một job đọc ra và ghép thành SQL:

```text
Request gửi report_column
       |
       v
INSERT config(report_column) bằng bind, an toàn khi lưu
       |
       v
Nightly job đọc lại report_column
       |
       v
Nối vào "ORDER BY " + report_column
       |
       v
Rủi ro: dữ liệu từ DB bị coi như cú pháp SQL
```

Đây là một dạng **second-order injection**. Việc dữ liệu đã được lưu trong bảng không tự biến nó thành mã SQL được phép thực thi.

Biện pháp:

1. Lưu **business key** như `"sort_created"` thay cho raw SQL fragment.
2. Ánh xạ key sang fragment cố định bằng allowlist khi sử dụng.
3. Kiểm quyền tại thời điểm chạy job.
4. Bind mọi giá trị còn lại.
5. Không dựa vào kiểm input ở bước trước như cơ chế bảo vệ duy nhất.

## 24. ORM và query builder: kiểm API raw query

Một ORM có thể tự bind giá trị cho các phương thức repository thông thường, nhưng câu:

```text
rawQuery("SELECT ... WHERE email = '" + email + "'")
```

vẫn tạo rủi ro injection. Phải dùng API truyền parameters của ORM/query builder thực tế. Đặc biệt cẩn thận với các API có tên `raw`, `literal`, `unsafe`, template strings hoặc tự ghép SQL trong utility functions.

### 24.1. Named parameters

Nhiều framework có dạng:

```sql
SELECT user_id, email
FROM demo_safe_users
WHERE tenant_id = :tenantId
  AND email = :email;
```

Đây là cú pháp **framework/driver**, không phải cú pháp SQL-level PREPARE của PostgreSQL khi gõ trực tiếp trong psql. Framework chuyển named parameters thành binding tương ứng; vẫn phải truyền giá trị qua API riêng.

### 24.2. Chèn literal ở tầng trước có thể phá ranh giới

Một query có thể đi qua template engine, ORM và JDBC. Nếu một lớp đã nối user input vào SQL text trước khi lớp sau gọi `prepareStatement`, việc dùng PreparedStatement ở lớp cuối **không biến chuỗi đã chèn thành bind value**. Hãy kiểm đường đi của dữ liệu từ request tới lệnh cuối.

### 24.3. Stored procedure không miễn nhiễm

Một stored procedure quyền cao có thể chứa dynamic SQL sai cách. Dù frontend query dùng prepared statement khi gọi procedure, bên trong procedure vẫn có thể nối input vào cú pháp SQL. Cần kiểm **mọi ranh giới dynamic SQL**, không chỉ endpoint.

## 25. MySQL prepared statements

MySQL driver thường cho bind dấu `?`:

```javascript
const [rows] = await mysqlConnection.execute(
  "SELECT user_id, email FROM users WHERE tenant_id = ? AND email = ?",
  [tenantId, emailFromRequest]
);
```

Ví dụ trên là kiểu API `mysql2`, không phải package `pg`.

### 25.1. SQL-level PREPARE của MySQL

```sql
SET @tenant_id = 10;
SET @email_value = 'an@example.com';

PREPARE stmt_find_user FROM
    'SELECT user_id, email
     FROM users
     WHERE tenant_id = ? AND email = ?';

EXECUTE stmt_find_user USING @tenant_id, @email_value;
DEALLOCATE PREPARE stmt_find_user;
```

Đây là cú pháp MySQL trên bảng `users` giả định, không chạy trực tiếp trên TEMP tables PostgreSQL. Cách khai báo biến session và `EXECUTE ... USING` khác SQL-level PostgreSQL.

### 25.2. Tên bảng/column không phải bind value

MySQL cũng không biến `FROM ?` thành identifier. Với SQL động, dùng allowlist và quoting identifier theo quy tắc MySQL; values vẫn bind. `LIMIT`, JSON, plan caching và khả năng chuẩn bị statement cần kiểm theo phiên bản/driver.

## 26. SQL Server sp_executesql

Trong SQL Server, `sp_executesql` cho phép SQL động có parameters:

```sql
DECLARE @sql NVARCHAR(MAX) =
    N'SELECT UserId, Email
      FROM dbo.Users
      WHERE TenantId = @TenantId
        AND Email = @Email';

EXEC sys.sp_executesql
    @sql,
    N'@TenantId INT, @Email NVARCHAR(320)',
    @TenantId = 10,
    @Email = N'an@example.com';
```

`@TenantId` và `@Email` được bind như data. **Chỉ gọi `sp_executesql` không đủ** nếu ứng dụng đã nối nội dung email vào chuỗi `@sql` từ trước.

### 26.1. Identifier và QUOTENAME

SQL Server có `QUOTENAME` để quote identifier. Nó không thay allowlist/authorization; một tên cột hợp lệ vẫn có thể là cột không được phép expose.

### 26.2. Type và parameter sniffing

Khai báo `NVARCHAR(320)` khác `VARCHAR`, `DECIMAL(p,s)` khác floating point. Kiểu/tham số có thể ảnh hưởng implicit conversion và plan. Với data skew, cần nghiên cứu parameter-sensitive plans, statistics và Query Store theo phiên bản, không tự bỏ bind.

## 27. SQLite binding

Ví dụ Python `sqlite3` có thể chạy độc lập:

```python
import sqlite3

with sqlite3.connect(":memory:") as conn:
    conn.execute(
        "CREATE TABLE users (user_id INTEGER PRIMARY KEY, email TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO users (user_id, email) VALUES (?, ?)",
        (1, "o'connor@example.com"),
    )
    rows = conn.execute(
        "SELECT user_id, email FROM users WHERE email = ?",
        ("o'connor@example.com",),
    ).fetchall()
    print(rows)
```

SQLite cũng có named placeholders:

```python
rows = conn.execute(
    "SELECT user_id, email FROM users WHERE email = :email",
    {"email": "an@example.com"},
).fetchall()
```

Đoạn named-placeholder trên là **fragment giả định conn vẫn đang mở** và bảng `users` tồn tại. Không chạy nó sau khi connection in-memory đã đóng nếu không mở/tạo bảng lại.

SQLite có type affinity linh hoạt tùy schema/phiên bản; bind một chuỗi `"100"` không đảm bảo business type đúng. Dùng schema, CHECK/STRICT tables khi phù hợp và validation để tránh conversion sai.

## 28. Oracle bind variables

Trong Oracle client có thể dùng:

```sql
SELECT user_id, email
FROM app_users
WHERE tenant_id = :tenant_id
  AND email = :email;
```

`:tenant_id` và `:email` là bind variables theo Oracle driver/client phù hợp.

### 28.1. PL/SQL EXECUTE IMMEDIATE ... USING

```sql
DECLARE
    v_email VARCHAR2(320) := 'an@example.com';
    v_tenant NUMBER := 10;
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM app_users
         WHERE tenant_id = :t AND email = :e'
    INTO v_count
    USING v_tenant, v_email;
END;
/
```

Đây là mã Oracle giả định bảng `app_users`. SQL động có placeholder cho values; identifier động vẫn cần allowlist/quoting riêng.

### 28.2. Oracle và chuỗi rỗng

Oracle trong nhiều ngữ cảnh coi chuỗi rỗng tương tự NULL, khác PostgreSQL. Một endpoint dùng `nickname=''` có thể thay nghĩa khi chuyển dialect dù bind an toàn về cú pháp.

### 28.3. Cursor sharing và bind peeking

Oracle có cơ chế parse/cursor caching và tối ưu plan tùy parameter, version và statistics. Khi gặp truy vấn chậm theo giá trị cụ thể, phải đo plan và data skew; không vội nối literals trở lại để “tối ưu”.

## 29. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao không đúng | Cách làm |
| --- | --- | --- |
| Escape nháy là đủ | Khác dialect, type, encoding/context | Bind values |
| Cấm dấu nháy sẽ chặn injection | Làm hỏng dữ liệu hợp lệ, không đủ | Tham số hóa |
| Prepare luôn nhanh hơn literal query | Plan/caching/data skew khác nhau | Benchmark |
| JDBC prepareStatement luôn tạo named SQL PREPARE | Driver/protocol/lifecycle khác | Hiểu driver |
| `'?'` là marker | Là string literal chứa `?` | Dùng `?` không nháy |
| Driver cần giá trị string có thêm nháy | Nháy là cú pháp SQL, không phải dữ liệu | `setString` với giá trị gốc |
| `IN (?)` với `"1,2,3"` là ba ID | Là một giá trị | Array ANY hoặc nhiều markers |
| `ORDER BY ?` chọn cột theo tên | Parameter là expression value | Allowlist fragment |
| `FROM ?` chọn bảng | Identifier thuộc cú pháp SQL | Allowlist + quote |
| `LIKE ?` khiến `%` mất nghĩa | Wildcard vẫn có semantics LIKE | Escape LIKE riêng |
| `= ?` với SQL NULL tìm hàng NULL | So sánh cho UNKNOWN | IS NULL/null-safe equality |
| Chuỗi rỗng và NULL luôn giống nhau | Phụ thuộc DBMS và type | Test dialect |
| Bind mọi thứ dạng string là đủ | Có thể ép kiểu sai/ mất precision | Typed binds |
| Parameterization tự validate JSON | Valid JSON có thể sai business schema | Validation riêng |
| Prepared statement tự giới hạn query lớn | LIMIT/pattern/batch vẫn có thể quá nặng | Validate giới hạn |
| Prepared statement tự kiểm quyền | Bind tenant khác vẫn là số hợp lệ | Authorization/RLS |
| Cùng DataSource là cùng transaction | Pool có thể cấp nhiều connections | Transaction manager |
| Batch nghĩa tất cả đã COMMIT | Còn phụ thuộc transaction và lỗi | Rollback/row count |
| Identifier quoting là cho phép mọi cột | Đúng cú pháp khác được phép | Allowlist |
| Data từ DB luôn tin cậy | Second-order injection | Kiểm lúc dùng |
| ORM mọi trường hợp tự an toàn | Raw SQL có thể nối input | Bind API ORM |
| Stored procedure tự an toàn | Bên trong có thể dựng SQL động sai | EXECUTE USING/allowlist |
| `sp_executesql` tự chống injection dù đã concat | Values phải thật sự bind | Params khai báo riêng |
| Prepared plan luôn ổn cho mọi tenant | Data skew/generic plan | Đo phân bố |
| EXPLAIN ANALYZE chỉ mô phỏng | DML vẫn thực thi | Database test và rollback |
| SQL injection là rủi ro duy nhất | BOLA, quyền, DoS, tính đúng còn lại | Defense in depth |

## 30. Quy trình thiết kế endpoint SQL an toàn

### Bước 1 — Viết hợp đồng

Ví dụ endpoint `GET /users/search`:

```text
Principal: đã xác thực; có tenant được phép.
Output: user_id, email, display_name (không password_hash).
Filter: email chính xác hoặc tên có chứa văn bản literal.
Sort: email, name, created; ASC/DESC.
Pagination: limit 1..100; cursor typed.
Scope: chỉ user active, chỉ tenant được phép.
```

### Bước 2 — Phân loại input

| Input | Loại | Xử lý |
| --- | --- | --- |
| tenant_id | Value nhưng gắn với quyền | Verify principal rồi bind |
| email | Text value | Bind |
| searchText | LIKE pattern value | Escape literal wildcards theo contract rồi bind |
| sortBy | Identifier choice | Allowlist |
| sortDirection | SQL keyword choice | Enum ASC/DESC |
| limit/offset | Integer values | Range check rồi bind |
| cursor | Typed values | Parse/validate rồi bind |
| metadata | JSON value | Serialize/validate rồi bind |

### Bước 3 — Tạo SQL shape tin cậy

```sql
SELECT user_id, email, display_name
FROM demo_safe_users
WHERE tenant_id = $1
  AND is_active = TRUE
  AND email = $2
ORDER BY user_id
LIMIT $3;
```

Đây là dạng marker PostgreSQL dùng trong một API driver hoặc SQL-level PREPARE theo ngữ cảnh, không phải statement được chuẩn bị độc lập để chạy y nguyên trong psql. Nếu không có filter email, xây **một query shape khác từ code**, không nối raw email.

### Bước 4 — Kiểm quyền và giới hạn

Xác thực caller, lấy tenant từ principal, validate các lựa chọn sort/limit, kiểm role database, policy/RLS nếu có, timeout và rate limit. Dùng CHECK/FK/UNIQUE cho bất biến dữ liệu.

### Bước 5 — Thực thi với bind

Gắn typed parameters, dùng một connection theo transaction khi có nhiều thao tác, kiểm affected rows với DML, phân loại lỗi nghiệp vụ và DBMS.

### Bước 6 — Test biên

Email có nháy đơn, Unicode, chuỗi trông giống SQL, string rỗng, SQL NULL, JSON null, ký tự `%/_`, danh sách ID rỗng, limit ngoài range, tenant không được phép và payload quá lớn.

### Bước 7 — Đo và giám sát

Đo actual plan/rows/buffers, latency, cache/connection pool, timeouts, lock waits, lỗi mapping type và số lượng prepared statements. Log query fingerprint/request ID, nhưng **không log mọi giá trị nhạy cảm** như token, số tài khoản hay nội dung bí mật.

## 31. Bộ bài tập thực hành

Các bài PostgreSQL dùng hai bảng TEMP ở mục 3, **trong cùng session tạo bảng**. Các bài Java/Python/Node là mã ứng dụng ví dụ; cần tạo lab data bằng chính connection ấy nếu muốn thực thi. Với UPDATE/DELETE, bao bằng `BEGIN ... ROLLBACK` để không thay đổi dữ liệu cho bài sau.

### Bài 1 — Ranh giới code/data

Trong `SELECT ... WHERE email = ? AND tenant_id = ?`, phần nào là SQL code và phần nào là values? Vì sao một email có dấu nháy đơn không phá cú pháp khi dùng bind?

### Bài 2 — Phân tích ghép chuỗi

So sánh rủi ro của `"... WHERE email='" + email + "'"` và `"... WHERE email=?"` với input `x' OR '1'='1` trong database lab. Không thực hiện thử nghiệm trên hệ không được phép.

### Bài 3 — PostgreSQL PREPARE

Chuẩn bị query tìm user theo tenant/email, EXECUTE với `(10, 'an@example.com')`, email `o'connor@example.com` và email không tồn tại. Giải thích từng kết quả rồi DEALLOCATE.

### Bài 4 — Prepared statement theo session

PREPARE ở Session A, mở Session B và thử gọi tên statement ở A. Vì sao B không tự thấy prepared statement đó?

### Bài 5 — Placeholder trong nháy

Giải thích vì sao `WHERE email='?'` không phải JDBC parameter. Index tham số đầu tiên của JDBC là 0 hay 1?

### Bài 6 — JDBC SELECT

Viết method JDBC tìm user bằng `tenantId` và `email`, dùng `setInt`, `setString`, `executeQuery` và try-with-resources. Test user 4 có dấu nháy đơn.

### Bài 7 — JDBC UPDATE

Thực hiện UPDATE nickname theo tenant_id/user_id, kiểm `executeUpdate()==1`. Nếu update 0 hàng thì có phải chắc chắn SQL injection không?

### Bài 8 — DELETE an toàn

Viết DELETE chỉ cho order `CANCELED` theo tenant_id và order_id. Vì sao việc bind order_id đúng không thay thế điều kiện status hoặc quyền?

### Bài 9 — NULL trong bind

PREPARE `nickname = $1`, EXECUTE(NULL) có trả user 1/4 không? Thay bằng `IS NOT DISTINCT FROM` và so sánh với nickname `''` của user 3.

### Bài 10 — Optional filter

API nhận ba trạng thái: không gửi nickname, gửi null, gửi chuỗi rỗng. Thiết kế cấu trúc request và query shapes để không gộp ba ý nghĩa.

### Bài 11 — LIKE wildcard

Client muốn tìm literal `50%` hoặc `a_b`. Vì sao bind pattern chưa đủ? Viết hàm escape `!`, `%`, `_` cho `LIKE ... ESCAPE '!'`.

### Bài 12 — Unicode/dấu nháy

Với chuỗi `O'Connor`, `Bình`, emoji, giải thích tại sao việc cấm ký tự đặc biệt không phải giải pháp parameterization.

### Bài 13 — IN list

Viết PostgreSQL query `user_id = ANY($2::integer[])` với array `[1,2,4]` và array rỗng. Tại sao bind `"1,2,4"` vào `IN (?)` không giống?

### Bài 14 — Dynamic placeholders

Trong JDBC, sinh số dấu `?` từ kích thước list ID và bind từng phần tử, xử lý list rỗng và giới hạn tối đa 500 ID.

### Bài 15 — ORDER BY động

Cho sortBy thuộc ba lựa chọn email, name, created; direction ASC/DESC. Thiết kế mapping allowlist. Vì sao `ORDER BY ?` với value `"created_at DESC"` không dùng được?

### Bài 16 — Tên bảng

Tại sao `SELECT * FROM ?` không chọn table name? Nếu chỉ có hai report tables hợp lệ, hãy ánh xạ report key qua allowlist và quote identifier đúng dialect.

### Bài 17 — PL/pgSQL EXECUTE USING

Viết `DO` block với `format('%I', column)` cho column được allowlist, còn values truyền qua `USING`. Giải thích vì sao `format('%s', value)` không nên thay bind.

### Bài 18 — SECURITY DEFINER

Một hàm có quyền cao cho caller chọn tên bảng/column. Những rủi ro về `search_path`, quyền, identifier và dynamic SQL là gì? Nêu giải pháp.

### Bài 19 — JSONB

Viết JDBC UPDATE metadata bằng `CAST(? AS jsonb)`. Vì sao JSON có dấu nháy không phá SQL khi bind, nhưng JSON có field sai type vẫn cần validation?

### Bài 20 — TIMEZONE

Viết query `created_at >= ? AND created_at < ?` cho hai mốc typed. Vì sao mốc bắt đầu/kết thúc phải tính theo timezone nghiệp vụ?

### Bài 21 — LIMIT và tài nguyên

Bind limit với giá trị từ API, áp dụng range 1..100. Vì sao một `LIMIT 100000000` được bind vẫn có thể gây nghẽn?

### Bài 22 — Keyset pagination

Viết query cursor `(created_at, order_id)` với ORDER BY tương ứng. Phân biệt cursor values và sort structure.

### Bài 23 — Python psycopg

Viết một `cur.execute(sql, (tenant_id, email))` có hai marker `%s`. Giải thích vì sao f-string và `'%s'` trong SQL sai.

### Bài 24 — Node pg

Viết `pool.query(text, values)` dùng `$1/$2`; sau đó viết transaction BEGIN/UPDATE/COMMIT dùng một `client` duy nhất. Vì sao `pool.query` lặp không tự giữ cùng transaction?

### Bài 25 — Query plans

Dùng `PREPARE` rồi `EXPLAIN EXECUTE` và `EXPLAIN (ANALYZE, BUFFERS) EXECUTE`. Tham số theo tenant nhỏ/lớn có thể chọn plan khác thế nào? Generic và custom plans có đánh đổi gì?

### Bài 26 — JDBC batch

Dùng `addBatch()` và `executeBatch()` với nhiều bộ tham số. Giải thích vì sao batching khác all-or-nothing transaction và cách xử lý lỗi giữa batch.

### Bài 27 — SQL Server

Viết `sp_executesql` khai báo `@TenantId INT, @Email NVARCHAR(320)`. Tại sao gọi sp_executesql nhưng đã nối email vào `@sql` vẫn là rủi ro?

### Bài 28 — MySQL, SQLite, Oracle

So sánh `?`, `:email` và `EXECUTE ... USING` ở ba dialect. Viết ví dụ tìm email bằng binding và giải thích vì sao không bind tên bảng như một value.

### Bài 29 — Second-order injection

Một job đọc `sort_column` đã lưu từ user trong DB rồi nối vào ORDER BY. Vì sao đó vẫn là dữ liệu không tin cậy? Thiết kế business key và allowlist lúc dùng.

### Bài 30 — Endpoint tổng hợp

Thiết kế `GET /orders` có tenant từ principal, status enum, khoảng ngày typed, danh sách user IDs, sort allowlist, cursor và limit 1..100; query luôn bind values. Bổ sung role DB tối thiểu, RLS nếu phù hợp, kiểm row count cho ghi, query timeout, EXPLAIN theo phân bố tham số, test input có nháy/NULL/wildcard/tenant khác, và log không rò rỉ PII. Phân biệt lớp chống **SQL injection** với lớp bảo đảm **authorization**.

## 32. Checklist trước khi triển khai

### Ranh giới code/data

- [ ] Không chèn raw user values vào SQL text?
- [ ] Values đều dùng bind API đúng của driver?
- [ ] Không đặt marker trong dấu nháy?
- [ ] Dynamic identifiers/keywords đều lấy từ allowlist?
- [ ] SQL trong stored procedure/ORM/raw query cũng được kiểm?
- [ ] Không nhầm identifier quoting với authorization?

### Kiểu dữ liệu và semantics

- [ ] Đúng type integer, decimal, boolean, date, timestamp, JSON?
- [ ] SQL NULL, chuỗi rỗng, optional filter phân biệt đúng?
- [ ] IN-list/array rỗng và NOT IN với NULL được xử lý?
- [ ] LIKE/regex wildcard được quy định theo contract?
- [ ] Limit, list size, pattern length và timeout có giới hạn?
- [ ] ORDER BY có tie-breaker khi phân trang?

### Quyền và tính đúng

- [ ] Tenant được xác thực và ràng buộc trong query hoặc RLS?
- [ ] DB role chỉ có quyền cần thiết?
- [ ] Có CHECK/FK/UNIQUE và validation business?
- [ ] DML kiểm số hàng thay đổi?
- [ ] Transaction dùng đúng một connection/manager khi cần?
- [ ] Test cả user inactive, tenant khác và input không hợp lệ?

### Hiệu năng và vận hành

- [ ] Đo với phân bố giá trị tham số đại diện?
- [ ] Có xem actual plan/rows/buffers/locks?
- [ ] Hiểu generic/custom/parameter-sensitive plan theo engine?
- [ ] Giám sát lifecycle prepared statements và connection pool?
- [ ] Không log token/PII/raw sensitive params không cần thiết?
- [ ] Có tracing, rate limit, timeout và xử lý lỗi/retry phù hợp?

## 33. Sơ đồ tư duy

```text
            HTTP REQUEST / FILE / MESSAGE
                         |
                         v
               Phân loại từng input
                         |
              +----------+-----------+
              |                      |
              v                      v
       GIÁ TRỊ DỮ LIỆU           CẤU TRÚC SQL
       ID, email, date,          table, column,
       amount, JSON,            ORDER BY direction,
       limit, search             SQL fragment
              |                      |
              v                      v
       Validate type/range       Allowlist/enum
       + quyền tenant           + quote identifier
              |                      |
              v                      |
       BIND PARAMETERS               |
              |                      |
              +----------+-----------+
                         |
                         v
                SQL shape tin cậy
                         |
                         v
               Driver / DBMS execute
                         |
              +----------+-----------+
              |                      |
              v                      v
        SQL/code boundary       Authorization
        và typed values         + correctness
              |                      |
              +----------+-----------+
                         |
                         v
                 EXPLAIN / monitoring
```

## 34. Tổng kết

**Truy vấn tham số hóa** tách giá trị dữ liệu khỏi cú pháp SQL. Trong Java/JDBC dùng `PreparedStatement` với `?`; PostgreSQL SQL PREPARE dùng `$1`, `$2`; psycopg dùng `%s` qua binding API; Node.js `pg` dùng `$1/$2`; MySQL, SQL Server, SQLite và Oracle có các marker/API tương ứng. Dù cú pháp khác nhau, nguyên tắc vẫn là **đừng nối trực tiếp dữ liệu người dùng vào câu SQL**.

Prepared statements có thể giúp tái sử dụng công việc parse/plan, nhưng chúng **không hứa luôn nhanh hơn**, không thay thế index, không tự bảo vệ khỏi truy vấn quá nặng, và không biến `FROM ?`/`ORDER BY ?` thành tên bảng/cột động. Những thành phần cấu trúc phải được tạo từ **allowlist tin cậy**, còn mọi giá trị được **bind đúng kiểu**.

Cuối cùng, SQL an toàn còn đòi hỏi **validation, quyền tenant và role tối thiểu, RLS khi phù hợp, constraints, transaction, kiểm số hàng, giới hạn tài nguyên và giám sát**. Một câu SQL có thể chống injection hoàn toàn nhưng vẫn truy cập sai tenant hoặc sửa sai dữ liệu nếu nghiệp vụ không được bảo vệ.

Hãy giữ câu hỏi thường trực: **“Thành phần này là cú pháp SQL được phép hay chỉ là giá trị input?”** Khi ranh giới ấy rõ ràng, các value được bind, các fragment động được allowlist và kết quả còn đáp ứng đúng quyền cùng hợp đồng nghiệp vụ, bạn đã có nền tảng vững để viết SQL an toàn, dễ kiểm thử và có thể tối ưu mà không đánh đổi tính đúng.
