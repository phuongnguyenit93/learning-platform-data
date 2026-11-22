# Identity, sequence và lấy định danh vừa sinh

Trong ứng dụng, nhiều bảng cần một khóa chính để nhận diện từng hàng: `user_id`, `order_id`, `invoice_id`, `payment_id` hoặc `event_id`. Thay vì yêu cầu ứng dụng tự tìm một số chưa dùng rồi gửi vào câu `INSERT`, database thường có cơ chế **tự sinh định danh** như identity column, auto-increment hoặc sequence.

Sau khi chèn một hàng, ứng dụng thường cần lấy ngay ID vừa được tạo để:
- Ghi các hàng con có foreign key trỏ tới hàng cha.
- Trả ID trong response API.
- Ghi audit/event hoặc tạo đường dẫn chi tiết.
- Liên kết các thao tác tiếp theo trong cùng transaction.
- Ánh xạ kết quả của một batch insert.

Bài toán có vẻ đơn giản nhưng có một yêu cầu quan trọng: **ID phải thuộc chính hàng mà thao tác INSERT của ứng dụng vừa tạo**, kể cả khi nhiều request đồng thời chèn dữ liệu, trigger chạy thêm INSERT hoặc connection pool thay đổi connection. Các cách như `SELECT MAX(id)` hoặc lấy “ID lớn nhất toàn bảng” không đáp ứng được yêu cầu đó.

> **Nguyên tắc:** để database sinh ID, lấy ID từ chính thao tác INSERT bằng cơ chế `RETURNING`, `OUTPUT`, `getGeneratedKeys()` hoặc hàm/session API được DBMS định nghĩa. Không suy đoán ID bằng cách đọc giá trị lớn nhất trong bảng và không giả định ID liên tục, không có khoảng trống.

Bài học thuộc **Database SQL → SQL đa hệ quản trị**. Nội dung so sánh PostgreSQL, MySQL, SQL Server, Oracle và SQLite; phân biệt identity column với sequence độc lập; giải thích phạm vi session/connection, trigger, transaction, rollback, cache, insert nhiều hàng, JDBC, batch, migration và các bài tập thực hành.

## 1. Vì sao bảng cần định danh được sinh tự động?

Một bảng đơn giản:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);
```

Ứng dụng phải tự cấp `customer_id` khi INSERT. Nếu hai request đồng thời cùng đọc một số tiếp theo rồi cùng dùng nó, chúng có thể đụng nhau. Nếu dùng `MAX(customer_id) + 1`, còn có race condition và chi phí scan/index lookup.

Cơ chế tự sinh của database giúp nhiều session cùng yêu cầu giá trị mà không phải tự phối hợp bằng một câu SELECT rồi INSERT.

### 1.1. Surrogate key và natural key

- **Natural key** là thuộc tính vốn có ý nghĩa nghiệp vụ, ví dụ mã ISBN, mã quốc gia, mã hóa đơn bên ngoài hoặc email nếu nghiệp vụ bảo đảm tính duy nhất.
- **Surrogate key** là định danh kỹ thuật được tạo để nhận diện hàng, ví dụ `customer_id BIGINT`.

Surrogate key thường có các đặc điểm:
- Không mang ý nghĩa nghiệp vụ.
- Ổn định dù email/tên/địa chỉ thay đổi.
- Nhỏ và thuận tiện làm foreign key.
- Được database bảo vệ bằng PRIMARY KEY hoặc UNIQUE.

Không nên biến ID tự sinh thành mã nghiệp vụ có ý nghĩa như số hóa đơn hiển thị cho khách nếu quy định yêu cầu dãy số không được thiếu, không lặp, có tiền tố, reset theo năm hoặc kiểm toán riêng. Các yêu cầu đó cần thiết kế riêng, không thể mặc định dựa vào identity/sequence.

### 1.2. ID không phải số thứ tự hàng

ID tự sinh không phải:
- Số dòng hiện tại trong bảng.
- Số bản ghi đã commit.
- Thứ tự tạo hàng theo thời gian commit.
- Bộ đếm không có khoảng trống.
- Bí mật hoặc bằng chứng người dùng có quyền truy cập.

Một hàng có ID 500 có thể commit sau hàng ID 501 nếu hai transaction được cấp số theo thứ tự khác nhau. Một ID có thể bị bỏ phí khi transaction rollback. Vì vậy, **không dùng ID làm bằng chứng thứ tự commit hoặc số lượng bản ghi**.

## 2. Identity column và sequence khác nhau thế nào?

Hai khái niệm liên quan nhưng không hoàn toàn giống nhau.

### 2.1. Identity column

Identity column là cột được database tự cấp giá trị khi INSERT mà ứng dụng không cung cấp giá trị rõ ràng. Cú pháp và quy tắc phụ thuộc DBMS.

Ví dụ về ý tưởng:

```sql
customer_id GENERATED ... AS IDENTITY
```

Ứng dụng thường không cần gọi sequence trực tiếp; chỉ INSERT các cột nghiệp vụ rồi lấy ID trả về.

### 2.2. Sequence

Sequence là một đối tượng tạo số độc lập với một cột cụ thể. Nhiều bảng hoặc nhiều thao tác có thể sử dụng sequence theo thiết kế, dù thường nên dùng một sequence cho một miền định danh phù hợp.

Sequence có thể được gọi trực tiếp để lấy giá trị trước INSERT, dùng làm default hoặc cấp ID cho nhiều loại thao tác. Sequence có lifecycle, quyền, cache và quy tắc riêng.

### 2.3. So sánh khái quát

| Tiêu chí | Identity column | Sequence |
| --- | --- | --- |
| Mục đích | Sinh giá trị cho một cột | Cấp số độc lập |
| Liên kết với bảng | Gắn trực tiếp vào cột | Có thể được dùng bởi nhiều đối tượng |
| Lấy trước khi INSERT | Tùy DBMS/cơ chế | Thường có thể gọi NEXT VALUE |
| Tính linh hoạt | Thường đơn giản, ít cấu hình hơn | Cao hơn: start, increment, min/max, cycle, cache |
| Dùng nhiều cột/bảng | Thường mỗi cột có cơ chế riêng | Có thể chia sẻ sequence |
| Lấy ID sau INSERT | RETURNING/OUTPUT/driver API | Có thể lấy qua returning hoặc sequence session API |
| Gaps | Có thể có | Có thể có |
| Tính liên tục tuyệt đối | Không bảo đảm | Không bảo đảm |

Identity column trong một số DBMS được triển khai bên dưới bằng sequence. Điều đó không làm cho mọi cú pháp hoặc hành vi identity và sequence giống nhau.

## 3. PostgreSQL: GENERATED AS IDENTITY

PostgreSQL hỗ trợ identity columns bằng `GENERATED ALWAYS AS IDENTITY` và `GENERATED BY DEFAULT AS IDENTITY`.

```sql
CREATE TEMP TABLE demo_pg_customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);
```

INSERT không chỉ định ID:

```sql
INSERT INTO demo_pg_customers (email, display_name)
VALUES ('an@example.com', 'An');
```

Database tự cấp `customer_id`.

### 3.1. GENERATED ALWAYS và GENERATED BY DEFAULT

**ALWAYS:**

```sql
CREATE TABLE demo_pg_always (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL
);
```

Thông thường, ứng dụng không được tự cung cấp giá trị `id` trong INSERT. Nếu cần nạp ID tường minh trong migration/import, PostgreSQL có cú pháp `OVERRIDING SYSTEM VALUE`:

```sql
INSERT INTO demo_pg_always (id, name)
OVERRIDING SYSTEM VALUE
VALUES (1000, 'Imported row');
```

**BY DEFAULT:**

```sql
CREATE TABLE demo_pg_default (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL
);
```

Nếu INSERT không có ID, database sinh. Nếu ứng dụng cung cấp ID, giá trị explicit được dùng theo quy tắc identity `BY DEFAULT`.

Khác biệt này hữu ích khi chọn chính sách:
- `ALWAYS`: ưu tiên để database kiểm soát việc cấp ID.
- `BY DEFAULT`: cho phép import/seed dữ liệu với ID cụ thể dễ hơn.

### 3.2. Lấy ID bằng RETURNING

Đây thường là cách rõ ràng nhất trong PostgreSQL:

```sql
INSERT INTO demo_pg_customers (email, display_name)
VALUES ('binh@example.com', 'Bình')
RETURNING customer_id;
```

Database trả ID của **hàng vừa được INSERT bởi chính statement này**. Không cần chạy thêm `SELECT MAX(customer_id)`.

Có thể trả thêm các cột:

```sql
INSERT INTO demo_pg_customers (email, display_name)
VALUES ('chi@example.com', 'Chi')
RETURNING customer_id, email, display_name;
```

Đây là cách thuận tiện khi API cần trả DTO vừa tạo.

### 3.3. RETURNING nhiều hàng

PostgreSQL hỗ trợ trả kết quả cho INSERT nhiều hàng:

```sql
INSERT INTO demo_pg_customers (email, display_name)
VALUES
    ('dung@example.com', 'Dũng'),
    ('ha@example.com', 'Hà'),
    ('linh@example.com', 'Linh')
RETURNING customer_id, email;
```

Mỗi hàng INSERT thành công được trả về cùng các cột được chỉ định. Nếu cần map ID với input, trả cả một khóa nghiệp vụ duy nhất (ví dụ `email` trong ví dụ có UNIQUE) để ánh xạ rõ ràng. Không chỉ dựa vào giả định thứ tự sequence liên tiếp.

### 3.4. RETURNING trong JDBC

Có thể dùng SQL `RETURNING` và đọc ResultSet:

```java
String sql = """
    INSERT INTO demo_pg_customers (email, display_name)
    VALUES (?, ?)
    RETURNING customer_id
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, email);
    ps.setString(2, displayName);

    try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            throw new SQLException("INSERT did not return customer_id");
        }
        long customerId = rs.getLong("customer_id");
    }
}
```

Đây là ví dụ PostgreSQL-specific vì SQL có `RETURNING`. Một số driver/framework có cách gọi khác hoặc hỗ trợ `getGeneratedKeys()`. Chọn một API phù hợp và nhất quán, không cần vừa gọi `RETURNING` vừa gọi thêm một truy vấn lấy ID.

### 3.5. BY DEFAULT và ALWAYS trong import

Khi import hàng đã có ID:
- Với `BY DEFAULT`, có thể cung cấp ID tường minh.
- Với `ALWAYS`, dùng `OVERRIDING SYSTEM VALUE` nếu nghiệp vụ và quyền cho phép.

Sau khi import explicit IDs, phải kiểm tra trạng thái sequence/identity generator. Database không nhất thiết tự nhảy sequence lên cao hơn ID lớn nhất được import trong mọi trường hợp. Nếu sequence tiếp tục cấp ID đã tồn tại, INSERT có thể đụng PRIMARY KEY.

Cách đồng bộ generator phải dựa vào sequence thực tế được gắn với cột và quy tắc PostgreSQL đang dùng; không mặc định mọi cột identity đều có cùng tên sequence.

## 4. PostgreSQL sequence: NEXTVAL, CURRVAL và LASTVAL

Tạo sequence độc lập:

```sql
CREATE SEQUENCE demo_customer_seq
    START WITH 1000
    INCREMENT BY 1
    MINVALUE 1
    NO MAXVALUE
    CACHE 20;
```

Lấy giá trị mới:

```sql
SELECT nextval('demo_customer_seq');
```

`nextval` cấp một giá trị mới cho session đang gọi. Mỗi lần gọi thành công, sequence tiến theo increment.

Dùng sequence làm default:

```sql
CREATE TEMP TABLE demo_pg_sequence_customers (
    customer_id BIGINT PRIMARY KEY
        DEFAULT nextval('demo_customer_seq'),
    email TEXT NOT NULL
);
```

INSERT:

```sql
INSERT INTO demo_pg_sequence_customers (email)
VALUES ('sequence@example.com')
RETURNING customer_id;
```

### 4.1. NEXTVAL

`nextval(sequence_name)` yêu cầu sequence cấp số mới. Các session đồng thời có thể gọi mà không phải tự khóa một hàng counter trong bảng nghiệp vụ. Giá trị được cấp là duy nhất theo sequence trong điều kiện cấu hình bình thường, không đồng nghĩa INSERT sẽ thành công nếu ứng dụng cố tình dùng ID trùng hoặc sequence bị cấu hình lại sai.

### 4.2. CURRVAL

`currval(sequence_name)` trả giá trị gần nhất mà **session hiện tại** đã lấy từ `nextval` của sequence đó:

```sql
SELECT nextval('demo_customer_seq');
SELECT currval('demo_customer_seq');
```

`currval` chỉ có ý nghĩa sau khi session đã gọi `nextval` cho sequence ấy. Nếu session chưa gọi, PostgreSQL báo lỗi.

Điểm quan trọng: session khác có thể gọi `nextval` xen giữa; `currval` vẫn là giá trị cuối cùng mà **session hiện tại** đã nhận, không bị đổi bởi session khác.

### 4.3. LASTVAL

`lastval()` trả giá trị gần nhất mà session hiện tại nhận từ bất kỳ sequence nào qua `nextval`.

```sql
SELECT nextval('demo_customer_seq');
SELECT lastval();
```

`lastval` có thể hữu ích trong script ngắn, nhưng dễ bị ảnh hưởng nếu một trigger hoặc câu lệnh khác trong cùng session gọi một sequence khác sau đó. Khi cần ID của một cột cụ thể, `RETURNING customer_id` hoặc `currval` của đúng sequence thường rõ hơn.

### 4.4. Không dùng MAX(id)

Không an toàn:

```sql
INSERT INTO customers (email, display_name)
VALUES ('new@example.com', 'New');

SELECT MAX(customer_id) FROM customers;
```

Giả sử:
1. Session A INSERT và nhận ID 100.
2. Session B INSERT và nhận ID 101, commit.
3. Session A chạy `SELECT MAX(customer_id)` và nhận 101.

A đã lấy ID của hàng B. Đây là race condition dù cả hai câu INSERT đều hợp lệ.

Cách đúng:

```sql
INSERT INTO customers (email, display_name)
VALUES ('new@example.com', 'New')
RETURNING customer_id;
```

hoặc API generated keys của driver.

### 4.5. Sequence không rollback theo transaction như hàng bảng

Trong PostgreSQL, giá trị đã cấp bằng `nextval` **không được trả lại** khi transaction rollback. Ví dụ:

```sql
BEGIN;

SELECT nextval('demo_customer_seq');

ROLLBACK;
```

Giá trị đó đã được tiêu thụ; lần gọi sau tiếp tục từ giá trị kế tiếp. Đây là chủ đích để cấp số đồng thời hiệu quả, không phải lỗi dữ liệu.

### 4.6. CACHE và gaps

`CACHE 20` cho phép backend giữ một nhóm giá trị sequence để giảm chi phí truy cập. Nếu session/server kết thúc bất ngờ hoặc cache chưa dùng hết, một số giá trị có thể không xuất hiện trong bảng. Sequence có thể tạo gaps vì:
- Transaction rollback.
- INSERT thất bại sau khi đã lấy số.
- `ON CONFLICT` có thể đã gọi default/sequence trước khi phát hiện conflict.
- Cache bị mất khi session/server kết thúc.
- Ứng dụng gọi `nextval` nhưng không INSERT.
- Sequence được tăng thủ công hoặc cấu hình increment khác 1.

**Không dùng sequence để tạo dãy hóa đơn bắt buộc liên tục không thiếu.**

### 4.7. Identity column và sequence ownership

Identity column PostgreSQL có sequence nội bộ được gắn với cột. PostgreSQL quản lý dependency/ownership của sequence theo identity column. Không nên dựa vào tên sequence được sinh tự động bằng quy tắc ghép tên bảng/cột; hãy truy vấn catalog/hàm hỗ trợ khi cần xác định sequence cụ thể.

Với cột dùng `DEFAULT nextval(...)` truyền thống, có thể gắn sequence bằng `OWNED BY` để lifecycle phụ thuộc bảng/cột:

```sql
CREATE SEQUENCE customer_id_seq;

CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY
        DEFAULT nextval('customer_id_seq'),
    email TEXT NOT NULL
);

ALTER SEQUENCE customer_id_seq
OWNED BY customers.customer_id;
```

Đây là mẫu cho bảng thường, không phải identity column.

## 5. MySQL: AUTO_INCREMENT và LAST_INSERT_ID()

MySQL thường dùng `AUTO_INCREMENT`:

```sql
CREATE TABLE demo_mysql_customers (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customer_email (email)
);
```

INSERT:

```sql
INSERT INTO demo_mysql_customers (email, display_name)
VALUES ('an@example.com', 'An');
```

Database tự sinh `customer_id`.

### 5.1. LAST_INSERT_ID()

Trong cùng connection:

```sql
SELECT LAST_INSERT_ID();
```

MySQL trả ID auto-increment được tạo bởi câu INSERT gần nhất phù hợp trên **connection hiện tại**. Đây là phạm vi quan trọng: hãy thực hiện INSERT và lấy ID trên cùng physical connection.

Nếu session A INSERT, session B INSERT sau đó, `LAST_INSERT_ID()` trong A vẫn giữ giá trị của A theo semantics connection-local; không phải đọc ID lớn nhất toàn bảng.

### 5.2. JDBC getGeneratedKeys

Với MySQL JDBC driver, thường có thể dùng:

```java
String sql = """
    INSERT INTO demo_mysql_customers (email, display_name)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS
)) {
    ps.setString(1, email);
    ps.setString(2, displayName);
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("No generated key returned");
        }
        long customerId = keys.getLong(1);
    }
}
```

Driver có thể hỗ trợ thêm metadata hoặc nhiều generated keys theo statement. Hành vi multi-row/batch cần kiểm theo phiên bản Connector/J và cấu hình; không giả định mọi driver trả cùng hình thức.

### 5.3. LAST_INSERT_ID và connection pool

Nếu ứng dụng:
1. Gọi INSERT qua connection A.
2. Trả A về pool.
3. Mượn connection B.
4. Gọi `SELECT LAST_INSERT_ID()`.

Kết quả ở B không nhất thiết là ID của INSERT ở A. Nó là trạng thái của connection B.

Vì vậy, dùng driver generated keys ngay sau INSERT hoặc giữ đúng connection trong cùng thao tác. Không chạy INSERT ở một connection rồi hỏi ID trên connection khác.

### 5.4. Multi-row INSERT

```sql
INSERT INTO demo_mysql_customers (email, display_name)
VALUES
    ('b@example.com', 'B'),
    ('c@example.com', 'C'),
    ('d@example.com', 'D');
```

`LAST_INSERT_ID()` thường cho ID đầu tiên được tạo cho câu INSERT đó theo semantics MySQL, nhưng việc suy ra mọi ID còn lại bằng `first_id + offset` phụ thuộc cách cấp auto-increment, chế độ lock, concurrency, `auto_increment_increment`, `auto_increment_offset`, trigger và driver. **Không giả định các ID của multi-row insert luôn liên tiếp**.

Nếu cần ánh xạ chính xác từng input với ID, hãy thiết kế cách trả khóa phù hợp với DBMS/driver hoặc dùng khóa nghiệp vụ duy nhất để query/map. Kiểm tra driver cụ thể.

### 5.5. LAST_INSERT_ID(expr)

MySQL có dạng `LAST_INSERT_ID(expr)` để đặt giá trị connection-local và trả lại giá trị đó, thường được dùng trong một số mẫu counter/UPSERT. Đây là tính năng đặc thù; không nhầm với `LAST_INSERT_ID()` không đối số để lấy auto-increment gần nhất.

### 5.6. AUTO_INCREMENT gaps và reset

AUTO_INCREMENT có thể có khoảng trống do rollback, delete, lỗi insert hoặc cơ chế cấp số/concurrency. Không dùng nó cho yêu cầu số liên tục tuyệt đối.

MySQL cho phép thay đổi giá trị AUTO_INCREMENT bằng DDL như `ALTER TABLE ... AUTO_INCREMENT = ...` trong điều kiện phù hợp. Không reset tùy tiện khi hệ thống đang ghi đồng thời hoặc khi có hàng mang ID cao hơn.

## 6. SQL Server: IDENTITY, SCOPE_IDENTITY và OUTPUT

SQL Server hỗ trợ `IDENTITY(seed, increment)`:

```sql
CREATE TABLE dbo.DemoCustomers (
    CustomerId BIGINT IDENTITY(1,1) NOT NULL
        CONSTRAINT PK_DemoCustomers PRIMARY KEY,
    Email NVARCHAR(320) NOT NULL,
    DisplayName NVARCHAR(200) NOT NULL
);
```

INSERT:

```sql
INSERT INTO dbo.DemoCustomers (Email, DisplayName)
VALUES (N'an@example.com', N'An');
```

Database cấp `CustomerId`.

### 6.1. SCOPE_IDENTITY()

Trong cùng batch/procedure scope:

```sql
INSERT INTO dbo.DemoCustomers (Email, DisplayName)
VALUES (N'binh@example.com', N'Bình');

SELECT CAST(SCOPE_IDENTITY() AS BIGINT) AS CustomerId;
```

`SCOPE_IDENTITY()` trả identity cuối cùng được tạo trong **cùng scope**. Nó tránh một số nhầm lẫn do trigger chạy trong scope khác.

### 6.2. Vì sao không nên dùng @@IDENTITY?

`@@IDENTITY` trả identity cuối cùng được tạo trong **session**, kể cả ở scope khác, ví dụ trigger.

Giả sử:
- INSERT vào `DemoCustomers` sinh CustomerId 10.
- Trigger ghi `AuditRows`, sinh AuditId 900.
- Sau INSERT, `@@IDENTITY` có thể trả 900, không phải 10.

`SCOPE_IDENTITY()` thường tránh vấn đề trigger scope này. Tuy nhiên, với INSERT nhiều hàng hoặc cần trả nhiều ID, `OUTPUT INSERTED` là lựa chọn rõ ràng hơn.

### 6.3. IDENT_CURRENT()

`IDENT_CURRENT('dbo.DemoCustomers')` trả identity hiện tại của một bảng trên phạm vi các session, không gắn với INSERT của caller. Một session khác có thể tạo ID mới giữa thao tác của bạn. Không dùng `IDENT_CURRENT()` để lấy ID vừa sinh cho request hiện tại.

### 6.4. OUTPUT INSERTED

SQL Server có thể trả ID ngay trong INSERT:

```sql
INSERT INTO dbo.DemoCustomers (Email, DisplayName)
OUTPUT INSERTED.CustomerId, INSERTED.Email
VALUES (N'chi@example.com', N'Chi');
```

Đây là cách rõ ràng để nhận ID của các hàng được INSERT.

Nhiều hàng:

```sql
INSERT INTO dbo.DemoCustomers (Email, DisplayName)
OUTPUT INSERTED.CustomerId, INSERTED.Email
VALUES
    (N'dung@example.com', N'Dũng'),
    (N'ha@example.com', N'Hà');
```

`OUTPUT` có thể trả nhiều hàng. Nếu cần map chính xác input và output, có thể thêm một khóa correlation duy nhất trong input và dùng `OUTPUT` kết hợp `MERGE`/table variable hoặc pattern phù hợp; đừng chỉ giả định output luôn có thứ tự tương ứng với input nếu contract không bảo đảm.

### 6.5. JDBC với SQL Server

Một cách là JDBC generated keys:

```java
String sql = """
    INSERT INTO dbo.DemoCustomers (Email, DisplayName)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS
)) {
    ps.setString(1, email);
    ps.setString(2, displayName);
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("No generated key");
        }
        long customerId = keys.getLong(1);
    }
}
```

Hoặc dùng SQL Server-specific `OUTPUT INSERTED.CustomerId` trong SQL và đọc ResultSet theo cách driver hỗ trợ. Cần kiểm phiên bản Microsoft JDBC Driver và cú pháp cụ thể, nhất là khi có trigger hoặc nhiều hàng.

### 6.6. IDENTITY_INSERT

SQL Server có `SET IDENTITY_INSERT table ON` để cho phép explicit ID trong một số thao tác import/migration. Chỉ một table trong session có thể có IDENTITY_INSERT ON tại một thời điểm. Sau import, cần kiểm current identity seed/counter bằng `DBCC CHECKIDENT` và đồng bộ phù hợp. Không bật IDENTITY_INSERT cho endpoint ứng dụng thông thường.

### 6.7. IDENTITY gaps và rollback

Identity value được cấp có thể không được hoàn lại khi transaction rollback. SQL Server có thể cache identity values; restart bất thường cũng có thể làm xuất hiện gaps theo version/configuration. Identity không phải bộ đếm không mất số.

## 7. SQL Server SEQUENCE độc lập

Tạo sequence:

```sql
CREATE SEQUENCE dbo.CustomerSequence
    AS BIGINT
    START WITH 1000
    INCREMENT BY 1
    CACHE 50;
```

Lấy giá trị:

```sql
SELECT NEXT VALUE FOR dbo.CustomerSequence AS CustomerId;
```

Dùng làm default:

```sql
CREATE TABLE dbo.SequenceCustomers (
    CustomerId BIGINT NOT NULL
        CONSTRAINT DF_SequenceCustomers_Id
        DEFAULT (NEXT VALUE FOR dbo.CustomerSequence),
    Email NVARCHAR(320) NOT NULL,
    CONSTRAINT PK_SequenceCustomers PRIMARY KEY (CustomerId)
);
```

INSERT và lấy ID bằng OUTPUT:

```sql
INSERT INTO dbo.SequenceCustomers (Email)
OUTPUT INSERTED.CustomerId
VALUES (N'seq@example.com');
```

### 7.1. Sequence có thể dùng trước INSERT

Khác identity column chỉ tự sinh khi INSERT, sequence có thể được lấy trước rồi dùng trong nhiều thao tác:

```sql
DECLARE @newId BIGINT =
    NEXT VALUE FOR dbo.CustomerSequence;

INSERT INTO dbo.SequenceCustomers (CustomerId, Email)
VALUES (@newId, N'new@example.com');
```

Có thể hữu ích khi cần tạo ID cha rồi truyền vào nhiều câu INSERT trong cùng transaction. Nhưng nếu transaction rollback, sequence value đã cấp vẫn có thể bị bỏ phí.

### 7.2. Sequence cache và gaps

`CACHE` giảm chi phí cấp giá trị nhưng có thể tạo gaps khi server restart hoặc cache bị mất. `NO CACHE` cũng không biến sequence thành dãy liên tục khi transaction rollback hoặc INSERT thất bại.

### 7.3. NEXT VALUE FOR trong nhiều hàng

SQL Server có các quy tắc về dùng `NEXT VALUE FOR` trong SELECT/INSERT và thứ tự cấp số. Khi cần cấp sequence cho nhiều hàng, xem tài liệu phiên bản và dùng `OVER (ORDER BY ...)` trong ngữ cảnh hỗ trợ nếu cần thứ tự cấp theo một order xác định. Dù vậy, thứ tự ID không nên được coi là thứ tự commit.

## 8. Oracle: sequence và identity column

Oracle truyền thống sử dụng sequence để cấp ID:

```sql
CREATE SEQUENCE customer_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 50
    NOCYCLE;
```

Bảng:

```sql
CREATE TABLE demo_oracle_customers (
    customer_id NUMBER(19) PRIMARY KEY,
    email VARCHAR2(320) NOT NULL UNIQUE,
    display_name VARCHAR2(200) NOT NULL
);
```

INSERT:

```sql
INSERT INTO demo_oracle_customers (
    customer_id, email, display_name
)
VALUES (
    customer_seq.NEXTVAL,
    'an@example.com',
    'An'
);
```

### 8.1. CURRVAL

Sau khi session đã gọi `NEXTVAL`, có thể đọc `CURRVAL`:

```sql
SELECT customer_seq.NEXTVAL FROM dual;
SELECT customer_seq.CURRVAL FROM dual;
```

`CURRVAL` có phạm vi session và chỉ có giá trị sau `NEXTVAL` trong session đó. Nó không lấy ID cuối cùng do session khác tạo.

### 8.2. RETURNING INTO

PL/SQL có thể lấy ID ngay trong INSERT:

```sql
DECLARE
    v_customer_id NUMBER;
BEGIN
    INSERT INTO demo_oracle_customers (
        customer_id, email, display_name
    )
    VALUES (
        customer_seq.NEXTVAL,
        'binh@example.com',
        'Bình'
    )
    RETURNING customer_id INTO v_customer_id;

    DBMS_OUTPUT.PUT_LINE(v_customer_id);
END;
/
```

`RETURNING INTO` gắn ID với hàng vừa được INSERT bởi statement đó, không phải truy vấn MAX.

### 8.3. Identity columns trong Oracle

Các phiên bản Oracle hiện đại hỗ trợ identity columns, ví dụ:

```sql
CREATE TABLE demo_oracle_identity (
    customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY
        PRIMARY KEY,
    email VARCHAR2(320) NOT NULL
);
```

Có thể dùng `GENERATED ALWAYS AS IDENTITY` hoặc `BY DEFAULT AS IDENTITY` tùy chính sách explicit values. Khả năng và cú pháp chi tiết phụ thuộc phiên bản Oracle. Identity column dùng sequence nội bộ do Oracle quản lý; không nên phụ thuộc vào tên sequence nội bộ.

### 8.4. JDBC Oracle và generated keys

Oracle JDBC hỗ trợ nhiều cơ chế generated keys/RETURNING tùy driver và statement. Với sequence, một lựa chọn rõ là:
- Lấy `NEXTVAL` trên cùng connection, sau đó INSERT với ID ấy; hoặc
- Dùng `INSERT ... RETURNING ... INTO` qua API Oracle-specific phù hợp.

Không gọi `NEXTVAL` ở connection A rồi INSERT ở connection B nếu logic cần cùng một ID. Nếu sequence value đã lấy mà INSERT lỗi, giá trị có thể bị bỏ phí.

### 8.5. Sequence cache và transaction

Oracle sequence được thiết kế cho cấp số đồng thời, không rollback giá trị khi transaction rollback. Cache giúp giảm I/O/overhead nhưng có thể gây gaps khi instance restart/failover. Không dùng sequence làm số hóa đơn liên tục nếu business yêu cầu không thiếu.

## 9. SQLite: INTEGER PRIMARY KEY, AUTOINCREMENT và last_insert_rowid

SQLite có cách tự sinh ID gắn với `ROWID`:

```sql
CREATE TABLE demo_sqlite_customers (
    customer_id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);
```

Trong bảng rowid table thông thường, một cột có kiểu khai báo chính xác `INTEGER PRIMARY KEY` là alias của `ROWID`. Nếu INSERT bỏ cột này hoặc truyền NULL, SQLite tự cấp một rowid.

```sql
INSERT INTO demo_sqlite_customers (email, display_name)
VALUES ('an@example.com', 'An');

SELECT last_insert_rowid();
```

### 9.1. last_insert_rowid()

`last_insert_rowid()` trả rowid của INSERT gần nhất thành công trên **connection hiện tại** (với các quy tắc của SQLite). Không lấy ID từ một connection khác.

Trong ứng dụng, ưu tiên API driver generated keys hoặc `RETURNING` khi SQLite version hỗ trợ. Nếu dùng `last_insert_rowid()`, thực hiện ngay trên cùng connection và hiểu tác động của trigger/virtual tables theo tài liệu SQLite.

### 9.2. AUTOINCREMENT không phải từ đồng nghĩa với tự sinh ID

```sql
CREATE TABLE demo_sqlite_strict_ids (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL
);
```

`AUTOINCREMENT` thay đổi thuật toán cấp ROWID để **không tái sử dụng các ROWID đã từng được dùng** theo phạm vi SQLite cam kết. Nó có thêm overhead và thường không cần thiết.

Nếu chỉ dùng `INTEGER PRIMARY KEY`, SQLite thường chọn một ROWID lớn hơn giá trị lớn nhất hiện tại, nhưng có thể tái sử dụng một số ID đã bị xóa trong các trường hợp nhất định. Chọn AUTOINCREMENT khi yêu cầu không tái sử dụng có ý nghĩa, không thêm theo thói quen.

### 9.3. Không nhầm kiểu INTEGER với BIGINT

Trong SQLite, tên kiểu chính xác `INTEGER PRIMARY KEY` có ý nghĩa alias rowid. `BIGINT PRIMARY KEY` không có cùng hành vi alias trong một rowid table thông thường. Nếu cần cơ chế rowid tự sinh, chú ý kiểu khai báo chính xác.

### 9.4. RETURNING

SQLite hỗ trợ `RETURNING` từ phiên bản 3.35.0:

```sql
INSERT INTO demo_sqlite_customers (email, display_name)
VALUES ('binh@example.com', 'Bình')
RETURNING customer_id, email;
```

Ứng dụng có thể đọc ID từ kết quả statement, tránh thêm một query lấy last rowid. Kiểm version SQLite được bundle trong runtime/driver, vì nhiều ứng dụng nhúng dùng phiên bản cũ hơn hệ điều hành hiện tại.

## 10. Bảng so sánh cú pháp và cách lấy ID

| DBMS | Cơ chế phổ biến | Cách lấy ID ngay sau INSERT |
| --- | --- | --- |
| PostgreSQL | `GENERATED ... AS IDENTITY`, sequence | `INSERT ... RETURNING id`; sequence `currval` khi cần |
| MySQL | `AUTO_INCREMENT` | `LAST_INSERT_ID()` cùng connection; JDBC `getGeneratedKeys()` |
| SQL Server | `IDENTITY`, `SEQUENCE` | `OUTPUT INSERTED.id`; `SCOPE_IDENTITY()` cho một hàng trong scope |
| Oracle | Identity, sequence | `RETURNING ... INTO`; `CURRVAL` sau `NEXTVAL` cùng session |
| SQLite | `INTEGER PRIMARY KEY`/ROWID | `RETURNING id`; `last_insert_rowid()` cùng connection |

Bảng là hướng dẫn tổng quát. Driver có thể cung cấp API generated keys khác nhau; multi-row/batch behavior và phiên bản phải được xác minh.

## 11. JDBC getGeneratedKeys: mẫu đa hệ quản trị

JDBC cung cấp API chung:

```java
PreparedStatement ps = conn.prepareStatement(
    sql,
    Statement.RETURN_GENERATED_KEYS
);
```

Sau khi `executeUpdate()`, lấy `ResultSet` từ `getGeneratedKeys()`:

```java
String sql = """
    INSERT INTO customers (email, display_name)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS
)) {
    ps.setString(1, email);
    ps.setString(2, displayName);

    int affected = ps.executeUpdate();
    if (affected != 1) {
        throw new SQLException("Expected one inserted row");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("Driver returned no generated key");
        }

        long id = keys.getLong(1);
        if (keys.wasNull()) {
            throw new SQLException("Generated key is NULL");
        }

        return id;
    }
}
```

Đây là pattern JDBC phổ biến, nhưng tên/cột trả về và hỗ trợ phụ thuộc database driver. Đọc tài liệu driver cho MySQL Connector/J, PostgreSQL JDBC, Microsoft JDBC Driver, Oracle JDBC hoặc SQLite JDBC.

### 11.1. Không phải DBMS nào cũng hỗ trợ cùng một dạng SQL

JDBC API cố gắng trừu tượng hóa việc lấy generated keys. SQL `RETURNING` của PostgreSQL/SQLite và `OUTPUT INSERTED` của SQL Server là các cú pháp riêng. Một ứng dụng đa DBMS có thể:
- Dùng JDBC generated keys nếu driver hỗ trợ đủ.
- Có implementation theo dialect cho SQL đặc thù.
- Kiểm thử bằng integration test trên từng DBMS thực tế.

Không viết một query PostgreSQL `RETURNING` rồi mong chạy nguyên văn trên SQL Server/MySQL/Oracle.

### 11.2. Không đóng connection trước khi lấy key

Generated keys là kết quả của statement/connection. Đừng:
1. INSERT qua connection A.
2. Đóng A/trả về pool.
3. Mượn connection B.
4. Gọi một hàm lấy last ID.

Hãy lấy keys từ chính `PreparedStatement` vừa chạy, trước khi đóng statement/connection theo lifecycle.

### 11.3. Tên cột generated keys

Một số driver có thể trả một hoặc nhiều cột, và metadata/column labels khác nhau. Dùng chỉ số cột hoặc tên theo hợp đồng driver đã kiểm thử. Nếu query có trigger/default phức tạp, hãy xác nhận generated key đúng là khóa chính mong muốn.

## 12. Multi-row INSERT và batch generated keys

Chèn nhiều hàng trong một câu:

```sql
INSERT INTO demo_pg_customers (email, display_name)
VALUES
    ('a@example.com', 'A'),
    ('b@example.com', 'B'),
    ('c@example.com', 'C')
RETURNING customer_id, email;
```

PostgreSQL trả ID và email của từng hàng được INSERT. Đây là cách tiện để map output theo khóa email duy nhất.

### 12.1. Đừng suy ra dãy ID liên tiếp

Ngay cả khi một lần insert nhiều hàng thường cấp các giá trị kế tiếp trong một tình huống đơn giản, ứng dụng không nên mặc định:
- Các ID liên tục.
- ID output theo đúng thứ tự input trên mọi DBMS/driver.
- Không có sequence calls khác.
- Không có trigger/default gây cấp thêm số.
- Một batch insert luôn trả đúng một generated key.

Nếu cần mapping chắc chắn, trả một correlation key hoặc natural/business key duy nhất trong output. Với PostgreSQL, `RETURNING customer_id, external_key` có thể giúp ánh xạ rõ.

### 12.2. JDBC executeBatch và getGeneratedKeys

Driver khác nhau có thể trả generated keys cho batch theo các cách khác nhau:
- Không hỗ trợ.
- Trả tất cả keys.
- Chỉ trả key đầu hoặc subset.
- Hành vi thay đổi theo rewrite batch/driver flags.

Không dựa vào giả định chung của JDBC cho mọi driver. Nếu mapping mỗi input tới mỗi ID quan trọng, kiểm tra integration test với đúng driver/version và cấu hình production. Có thể dùng statement `INSERT ... RETURNING` hoặc cú pháp DB-specific hỗ trợ multi-row output.

### 12.3. Thêm correlation key

Ví dụ PostgreSQL:

```sql
CREATE TEMP TABLE demo_imported_rows (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

INSERT INTO demo_imported_rows (external_key, name)
VALUES
    ('batch-A-001', 'An'),
    ('batch-A-002', 'Bình'),
    ('batch-A-003', 'Chi')
RETURNING id, external_key;
```

`external_key` giữ liên kết giữa input và ID được sinh. Không phụ thuộc thứ tự hàng trả về.

### 12.4. Batch thất bại một phần

Nếu một hàng trong batch vi phạm UNIQUE hoặc CHECK, hành vi thực thi và generated keys có thể phụ thuộc driver, DBMS và transaction mode. Nếu cần all-or-nothing, dùng transaction và rollback phù hợp. Nếu chấp nhận partial success, phải có cơ chế ánh xạ rõ hàng nào thành công/hàng nào lỗi.

## 13. Vì sao SELECT MAX(id) sai?

Đây là một lỗi kinh điển:

```sql
INSERT INTO customers (email, display_name)
VALUES ('new@example.com', 'New');

SELECT MAX(customer_id)
FROM customers;
```

Nó có thể trả ID của một session khác đã INSERT sau bạn.

### 13.1. Kịch bản cạnh tranh

```text
Session A                       Session B
---------                       ---------
INSERT customer -> id 100
                                INSERT customer -> id 101
                                COMMIT
SELECT MAX(id) -> 101
```

A cần ID 100 nhưng lấy 101. Điều kiện UNIQUE/PK vẫn hoạt động, song quan hệ cha/con của A có thể bị ghi nhầm hoặc query tiếp theo thao tác nhầm khách hàng B.

### 13.2. MAX(id) còn không phản ánh ID vừa sinh sau delete/import

Nếu hàng ID lớn nhất bị xóa, MAX giảm. Nếu import explicit IDs, MAX có thể không khớp trạng thái sequence. Nếu sequence cache đã cấp giá trị chưa insert, MAX cũng không phản ánh số tiếp theo.

### 13.3. Các cách không an toàn khác

Không dùng:
- `SELECT TOP 1 id ORDER BY id DESC` sau INSERT để suy ra ID của mình.
- `SELECT MAX(id)` trong transaction khác.
- Đọc bảng counter không có khóa/atomic update.
- Lấy ID từ một connection khác.
- Tự cộng `last_id + 1`.
- Dùng thời gian hiện tại hoặc random number thay cho cơ chế khóa được kiểm soát.

### 13.4. Cách đúng theo DBMS

- PostgreSQL: `INSERT ... RETURNING id`.
- MySQL: `LAST_INSERT_ID()` cùng connection hoặc driver generated keys.
- SQL Server: `OUTPUT INSERTED.id`, hoặc `SCOPE_IDENTITY()` cho trường hợp phù hợp.
- Oracle: `RETURNING INTO` hoặc sequence `CURRVAL` cùng session.
- SQLite: `RETURNING id` hoặc `last_insert_rowid()` cùng connection.

## 14. Trigger và ID vừa sinh

Trigger có thể INSERT thêm hàng vào bảng audit, bảng phụ hoặc bảng liên quan. Điều này quan trọng với hàm “last identity” theo phạm vi session.

### 14.1. SQL Server @@IDENTITY

Giả sử:
- `DemoCustomers` có `IDENTITY`.
- Trigger AFTER INSERT ghi vào `AuditRows` cũng có `IDENTITY`.

Sau INSERT customer:
- `SCOPE_IDENTITY()` thường trả CustomerId trong scope caller.
- `@@IDENTITY` có thể trả AuditId do trigger sinh.
- `IDENT_CURRENT('...')` trả giá trị hiện tại của bảng trên phạm vi session, không riêng caller.

`OUTPUT INSERTED.CustomerId` gắn với hàng được INSERT vào bảng mục tiêu, thường là cách trực tiếp hơn để trả ID.

### 14.2. PostgreSQL lastval và trigger

`lastval()` trả giá trị sequence gần nhất mà session gọi. Nếu trigger của INSERT chính gọi một sequence khác sau khi sequence identity cấp ID, `lastval()` có thể phản ánh sequence trong trigger. `RETURNING id` trả cột ID của hàng mục tiêu, rõ hơn.

`currval('specific_sequence')` cũng rõ hơn `lastval()` nếu biết đúng sequence, nhưng `RETURNING` vẫn gắn kết quả với chính statement INSERT.

### 14.3. MySQL trigger và LAST_INSERT_ID

MySQL có semantics connection-local cho `LAST_INSERT_ID()`; trigger/stored function có quy tắc lưu/khôi phục giá trị theo phạm vi thực thi riêng. Tuy nhiên, khi cần ID của hàng mục tiêu, hãy dùng driver generated keys hoặc kiểm hành vi đúng với trigger và Connector/J thay vì dựa vào giả định từ DBMS khác.

### 14.4. Oracle trigger và sequence

Trigger Oracle có thể gọi sequence để cấp ID. `RETURNING INTO` lấy giá trị cột của hàng được INSERT. Nếu trigger thay đổi ID hoặc có logic phức tạp, test chính xác giá trị trả về và contract của trigger. Không suy đoán sequence CURRVAL nào được gọi cuối cùng nếu có nhiều trigger/sequence.

## 15. Transaction, rollback và tính bền vững của ID

Một ID được trả ngay sau INSERT có thể được dùng để INSERT hàng con trong cùng transaction:

```sql
BEGIN;

INSERT INTO demo_pg_customers (email, display_name)
VALUES ('parent@example.com', 'Parent')
RETURNING customer_id;
-- Giả sử ứng dụng nhận id = 200.

INSERT INTO customer_addresses (customer_id, address_line)
VALUES (200, 'Địa chỉ mẫu');

COMMIT;
```

Trong ứng dụng, không hardcode 200; lấy giá trị ResultSet từ `RETURNING` rồi bind vào INSERT con.

### 15.1. Có thể dùng ID trước COMMIT

Trong cùng transaction, ứng dụng có thể đọc ID vừa sinh và dùng làm foreign key cho các hàng khác. Không cần commit trước mới biết ID.

### 15.2. Rollback không đảm bảo ID được dùng lại

Nếu transaction rollback:
- Hàng cha/con không được commit.
- ID đã cấp có thể vẫn bị tiêu thụ.
- Lần INSERT sau có thể nhận số lớn hơn.

Điều này bình thường với sequence/identity. Đừng cố “bù lại” số đã mất bằng cách reset sequence trong luồng ứng dụng.

### 15.3. ID được trả cho client trước COMMIT

Nếu API gửi ID cho client rồi transaction commit thất bại, client có thể nhận một ID không tồn tại. Thông thường:
1. INSERT.
2. Lấy ID.
3. Hoàn tất các thao tác trong transaction.
4. COMMIT thành công.
5. Sau đó mới gửi response thành công.

Nếu transaction có kết quả commit không rõ do mất kết nối, cần idempotency key/đối soát để client retry không tạo bản ghi trùng.

### 15.4. Không dùng sequence để thay thế transaction

Sequence cấp ID an toàn đồng thời, nhưng không đảm bảo nhiều INSERT liên quan thành công cùng nhau. Dùng transaction cho các thao tác nghiệp vụ cần atomicity.

## 16. ID tự sinh không đảm bảo thứ tự thời gian

Giả sử:
- Transaction A gọi sequence nhận 100, sau đó xử lý lâu.
- Transaction B nhận 101 và commit trước.
- A commit sau.

ID 101 có thể xuất hiện trong bảng trước ID 100. ID chỉ phản ánh thứ tự cấp số trong phạm vi cơ chế sequence, không phản ánh thứ tự commit.

Nếu cần thời gian tạo, lưu cột `created_at` có semantics rõ. Nếu cần thứ tự sự kiện, dùng event offset/commit sequence được thiết kế cho hệ thống đó, không suy từ identity.

### 16.1. Sequence tăng không đồng nghĩa không có ID cũ đến muộn

Import dữ liệu, explicit values, replication, retry và nhiều transaction có thể khiến ID xuất hiện theo thứ tự khác nhau. Không dùng `WHERE id > last_seen` làm incremental sync nếu có thể có hàng ID thấp hơn commit sau watermark mà không có quy tắc bảo đảm.

### 16.2. Không dùng ID tuần tự làm authorization

Nếu API có `/customers/100`, việc đoán được ID 101 không nên cho phép đọc khách hàng 101. Luôn kiểm quyền theo principal/tenant và object-level authorization. ID ngẫu nhiên khó đoán cũng không thay thế authorization.

## 17. Identity/sequence: explicit values và đồng bộ generator sau import

Một migration có thể nạp dữ liệu giữ ID cũ:
- Bảng đích đã có identity/auto-increment.
- Import chèn explicit ID.
- Sequence/identity generator có thể vẫn ở vị trí cũ.
- INSERT tiếp theo có thể tạo ID đã tồn tại.

### 17.1. PostgreSQL sequence với cột serial/default

Với sequence truyền thống, có thể đồng bộ bằng `setval` theo trạng thái đã import. Ví dụ cần xác định sequence đúng:

```sql
SELECT pg_get_serial_sequence(
    'public.customers',
    'customer_id'
);
```

Sau đó, trong migration có kiểm soát, dùng sequence được xác định để đồng bộ theo dữ liệu thực tế. Mẫu phổ biến với sequence serial:

```sql
SELECT setval(
    pg_get_serial_sequence('public.customers', 'customer_id'),
    COALESCE((SELECT MAX(customer_id) FROM public.customers), 1),
    EXISTS (SELECT 1 FROM public.customers)
);
```

Tham số thứ ba của `setval` quyết định giá trị đã được gọi hay chưa. Câu trên là mẫu cần được hiểu và điều chỉnh theo start value, increment và trường hợp bảng rỗng; không sao chép máy móc cho mọi sequence/identity. Chạy migration trong thời gian ghi được kiểm soát để tránh concurrent INSERT.

### 17.2. SQL Server DBCC CHECKIDENT

Sau import explicit IDs, có thể cần kiểm tra/reset identity:
```sql
DBCC CHECKIDENT ('dbo.DemoCustomers', NORESEED);
```

`NORESEED` báo trạng thái hiện tại và giá trị hiện tại. `RESEED` có thể đặt lại current identity value theo quy tắc DBMS. Cần hiểu trường hợp bảng rỗng, hàng lớn nhất và lần INSERT tiếp theo; chạy trong migration/maintenance có kiểm soát.

### 17.3. MySQL AUTO_INCREMENT

Sau import, kiểm `AUTO_INCREMENT` hiện tại qua metadata hoặc `SHOW TABLE STATUS`/information schema theo phiên bản. Có thể đặt lại bằng `ALTER TABLE ... AUTO_INCREMENT = n` trong điều kiện hợp lệ. Không reset thấp hơn ID đang tồn tại rồi giả định database sẽ dùng ID trùng; engine có quy tắc bảo vệ riêng, nhưng migration phải kiểm dữ liệu.

### 17.4. Oracle sequence

Nếu import explicit IDs, sequence độc lập không tự biết ID lớn nhất trong bảng. Cần điều chỉnh sequence bằng migration có kiểm soát theo phiên bản và cách tạo sequence; không gọi NEXTVAL một số lần tùy tiện trong code ứng dụng để “đưa sequence lên đúng chỗ” khi có concurrency.

### 17.5. Không reset generator khi hệ thống vẫn ghi

Đổi sequence/identity counter trong lúc ứng dụng đang INSERT có thể tạo va chạm. Lập kế hoạch maintenance:
- Dừng hoặc điều phối writers.
- Xác nhận dữ liệu import hoàn chỉnh.
- Xác định generator đúng.
- Đặt lại bằng cú pháp DBMS phù hợp.
- Kiểm thử một INSERT trong transaction/môi trường staging.
- Mở lại writers.

## 18. Sequence options và giới hạn

Sequence thường có:
- `START WITH`: giá trị bắt đầu.
- `INCREMENT BY`: bước tăng/giảm.
- `MINVALUE`, `MAXVALUE`: giới hạn.
- `CYCLE`/`NOCYCLE`: có quay vòng khi chạm giới hạn hay báo lỗi.
- `CACHE`/`NO CACHE`: cấp trước nhóm giá trị hay không.
- `OWNED BY` hoặc quan hệ dependency tùy DBMS.

### 18.1. CYCLE có phù hợp cho primary key không?

Nếu sequence dùng làm PRIMARY KEY, `CYCLE` có thể quay lại giá trị cũ và đụng unique constraint khi bảng vẫn giữ các hàng cũ. Thông thường khóa chính tự sinh dùng `NO CYCLE`/cấu hình không quay vòng. Nếu cần một counter vòng tròn, nó không nên được coi là surrogate key duy nhất toàn đời.

### 18.2. Kiểu số phải đủ lớn

Nếu bảng có thể tăng hàng tỷ hoặc hàng chục tỷ hàng, chọn `BIGINT`/`NUMBER` phù hợp ngay từ đầu. Khi sequence chạm MAXVALUE, cấp số mới sẽ lỗi. Đừng đợi gần hết dải mới tính migration.

### 18.3. Increment không nhất thiết bằng 1

Sequence có thể dùng increment khác 1 cho một số chiến lược shard/range, nhưng điều đó càng chứng minh ID không phải số thứ tự hàng. Không viết logic `next_id = last_id + 1`.

### 18.4. Sequence dùng chung nhiều bảng

Một sequence dùng cho nhiều bảng có thể tạo ID duy nhất toàn hệ thống theo sequence, nhưng không tự tạo FK/type domain rõ hoặc bảo đảm uniqueness nếu bảng khác vẫn có nguồn ID khác. Chỉ dùng khi có yêu cầu kiến trúc rõ, chẳng hạn ID toàn cục giữa nhiều loại entity; nếu không, sequence riêng thường dễ quản lý hơn.

## 19. Generated ID và UPSERT

UPSERT có thể INSERT hoặc UPDATE tùy conflict. Câu hỏi “ID vừa sinh” cần được diễn giải:
- Nếu INSERT thành công, trả ID hàng mới.
- Nếu conflict và UPDATE hàng cũ, cần trả ID của hàng hiện hữu.
- Nếu DO NOTHING, có thể không có hàng RETURNING.
- Sequence có thể đã tiêu thụ một số dù cuối cùng conflict.

PostgreSQL ví dụ:

```sql
INSERT INTO demo_pg_customers (email, display_name)
VALUES ('an@example.com', 'An mới')
ON CONFLICT (email)
DO UPDATE SET display_name = EXCLUDED.display_name
RETURNING customer_id, email;
```

Nếu conflict, `RETURNING` trả hàng được INSERT hoặc UPDATE theo statement. Cần hiểu chính sách update để tránh ghi đè trường ngoài ý muốn.

Nếu dùng `ON CONFLICT DO NOTHING RETURNING customer_id`, khi conflict không có hàng được INSERT nên ResultSet có thể rỗng. Ứng dụng cần query hàng hiện hữu theo unique business key nếu contract yêu cầu ID, và thực hiện với semantics concurrency phù hợp.

MySQL `INSERT ... ON DUPLICATE KEY UPDATE`, SQL Server `MERGE`/UPDATE-INSERT patterns, Oracle `MERGE` và SQLite UPSERT có semantics riêng. Không giả định `getGeneratedKeys()` trả ID của hàng cũ giống nhau ở mọi driver.

## 20. Trigger, default và generated columns

ID có thể được tạo bởi:
- Identity/auto-increment.
- Sequence trong DEFAULT.
- BEFORE INSERT trigger.
- Stored procedure.
- Ứng dụng cấp qua một dịch vụ ID riêng.

Khi dùng trigger, cần xác định **giá trị cuối cùng của cột mục tiêu** và cơ chế trả về có phản ánh giá trị sau trigger hay không. `RETURNING`/`OUTPUT` semantics theo DBMS và timing trigger; kiểm tài liệu engine khi trigger sửa chính ID.

Không tự viết logic ở application giả định:
- ID luôn được cấp trước trigger.
- Trigger không bao giờ đổi ID.
- Mỗi INSERT chỉ gọi một sequence.
- Audit trigger không tạo identity khác.
- Một default expression luôn được đánh giá đúng một lần như mong đợi.

## 21. Migration đa hệ quản trị

Một ứng dụng hỗ trợ nhiều DBMS nên trừu tượng hóa **hành vi cần thiết**, không ép tất cả DBMS dùng cùng cú pháp.

### 21.1. Một repository contract

Ví dụ:
```java
public interface CustomerRepository {
    long insertCustomer(CustomerInput input) throws SQLException;
}
```

Implementation PostgreSQL có thể dùng `RETURNING`, MySQL/SQL Server/SQLite có thể dùng JDBC generated keys, Oracle có thể dùng sequence/RETURNING API theo driver.

Business service chỉ nhận ID được trả về và dùng nó để tạo quan hệ con.

### 21.2. Không giấu khác biệt quan trọng của driver

Một abstraction generated keys cần kiểm:
- Có hỗ trợ multi-row không?
- Trả một hay nhiều keys?
- Có trả đúng cột identity không?
- Có tương thích trigger không?
- Có yêu cầu tên cột key không?
- Có khác nhau giữa `executeUpdate`, `execute`, batch không?

Nếu abstraction chỉ hỗ trợ một hàng, ghi rõ giới hạn thay vì giả định batch mapping.

### 21.3. Kiểu dữ liệu ID giữa DBMS

| DBMS | Kiểu thường dùng |
| --- | --- |
| PostgreSQL | `BIGINT` |
| MySQL | `BIGINT` |
| SQL Server | `BIGINT` |
| Oracle | `NUMBER(19)` hoặc kiểu phù hợp |
| SQLite | signed 64-bit ROWID trong rowid table |

Java thường map sang `long`/`Long` khi dải số phù hợp. Nếu dùng UUID hoặc ID lớn hơn 64-bit trong hệ khác, chọn kiểu application tương ứng. Không chuyển BIGINT qua JavaScript `Number` nếu có thể vượt giới hạn số nguyên an toàn của IEEE-754; dùng string/BigInt theo contract API khi cần.

### 21.4. Không giả định identity luôn bắt đầu từ 1

Migration, reseed, seed data, increment tùy chỉnh, replication và sequence options có thể làm giá trị đầu tiên khác 1. Code không nên kiểm tra ID > 0 như một bằng chứng duy nhất về việc INSERT thành công nếu DBMS/contract không bảo đảm điều đó.

## 22. UUID và ID phân tán

Không phải mọi hệ thống đều cần identity số nguyên. Một số hệ thống dùng UUID hoặc ID do application/distributed service sinh.

### 22.1. UUID

Ưu điểm:
- Có thể sinh ở client trước khi INSERT.
- Dễ tạo ID duy nhất qua nhiều node mà không cần hỏi database trước.
- Khó đoán hơn ID tuần tự, nhưng không thay authorization.

Đánh đổi:
- Thường rộng hơn BIGINT.
- Index có thể lớn hơn.
- UUID ngẫu nhiên có thể gây phân tán insertion/page locality.
- Có nhiều phiên bản UUID và cách sinh; chọn theo DBMS/driver/workload.

PostgreSQL có kiểu `uuid`; các DBMS khác có kiểu/biểu diễn riêng. API JSON thường biểu diễn UUID dưới dạng string chuẩn.

### 22.2. UUID v7 và tính sắp xếp

Một số phiên bản UUID có cấu trúc gần theo thời gian, như UUIDv7, giúp cải thiện tính locality so với UUID ngẫu nhiên trong một số workload. Nhưng vẫn phải xem chuẩn, generator và hỗ trợ DBMS. Không giả định UUID sort hoàn toàn tương đương timestamp commit.

### 22.3. Snowflake-style IDs

Một số hệ thống tạo ID từ timestamp, worker/node ID và sequence trong một khoảng thời gian. Cần quản lý:
- Đồng hồ hệ thống lệch/lùi.
- Worker ID không trùng.
- Giới hạn số ID mỗi time unit.
- Restart và state.
- Thứ tự giữa các node.
- Kiểu số và khả năng serialize.

Đây là một kiến trúc cấp ID riêng, không phải thay thế đơn giản cho identity column. Chỉ dùng khi yêu cầu phân tán/ID trước khi ghi thực sự cần.

## 23. Security và quyền truy cập

ID tuần tự dễ đoán không phải bí mật. Endpoint:

```text
GET /customers/1001
```

phải kiểm tra người gọi có quyền đọc customer 1001. Đổi sang UUID không tự ngăn BOLA/IDOR nếu server không kiểm authorization.

### 23.1. Generated ID không chứng minh INSERT được phép

Ứng dụng cần:
- Kiểm quyền tạo hàng.
- Ràng buộc tenant từ principal.
- Validate input.
- Dùng bind parameters.
- Giữ transaction cho các hàng liên quan.
- Kiểm lỗi unique/foreign key.
- Trả ID sau commit thành công theo contract.

### 23.2. Sequence permissions

Một sequence độc lập có quyền `USAGE`, `SELECT`, `UPDATE` tùy DBMS. Không cấp quyền gọi/đổi sequence cho role không cần. Nếu application chỉ INSERT qua một procedure, có thể hạn chế quyền trực tiếp lên bảng/sequence theo thiết kế security.

### 23.3. Không expose sequence state như thông tin bí mật

ID tăng dần có thể để lộ xấp xỉ lượng record hoặc tốc độ tạo mới nếu API công khai. Nếu đây là vấn đề nghiệp vụ, cân nhắc public identifier riêng (UUID/token), nhưng vẫn kiểm quyền. Không dùng số lượng ID làm số liệu thống kê chính xác vì gaps và concurrency.

## 24. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| `SELECT MAX(id)` sau INSERT | Có thể lấy ID session khác | RETURNING/OUTPUT/generated keys |
| `@@IDENTITY` trong SQL Server có trigger | Có thể lấy identity của trigger table | SCOPE_IDENTITY/OUTPUT |
| `IDENT_CURRENT` cho request hiện tại | Giá trị của session khác có thể mới hơn | OUTPUT/SCOPE_IDENTITY |
| PostgreSQL `lastval()` khi trigger gọi sequence khác | Có thể lấy sequence không phải cột mục tiêu | RETURNING hoặc currval đúng sequence |
| MySQL lấy LAST_INSERT_ID trên connection khác | Sai session-local state | Cùng connection/generated keys |
| Oracle CURRVAL trước NEXTVAL | Lỗi vì session chưa gọi NEXTVAL | Gọi NEXTVAL trước |
| SQLite last_insert_rowid trên connection khác | Không phải ID của INSERT cần lấy | Cùng connection/RETURNING |
| Giả định ID liên tiếp | Gaps bình thường | Không dùng ID làm counter liên tục |
| Giả định rollback trả ID | Sequence/identity thường không hoàn lại | Chấp nhận gaps |
| Cộng ID đầu cho multi-row insert | Không đảm bảo trên mọi engine/driver | Trả từng key/correlation key |
| Không lấy generated keys ngay | Mất connection context | Lấy từ statement/connection vừa INSERT |
| Tái sử dụng ID sau delete | Có thể phá FK/audit/cache | Để generator quản lý |
| Reset sequence khi app đang ghi | Có thể trùng ID | Maintenance có điều phối |
| Import explicit IDs nhưng quên reseed | INSERT sau có thể conflict | Đồng bộ generator trong migration |
| Dùng AUTOINCREMENT SQLite mặc định | Overhead không cần thiết | Chỉ dùng khi cần không tái sử dụng rowid |
| Dùng ID làm authorization | BOLA/IDOR | Kiểm quyền theo principal/tenant |
| Dùng identity làm số hóa đơn liên tục | Gaps và thứ tự commit không phù hợp | Thiết kế numbering nghiệp vụ riêng |
| JDBC batch giả định trả đủ keys | Driver có thể khác | Test đúng driver/version |
| Dùng JavaScript Number cho BIGINT lớn | Mất chính xác | BigInt/string |
| Cho nhiều bảng dùng một sequence tùy tiện | Domain/ownership khó hiểu | Thiết kế ID domain rõ |
| Bỏ qua trigger/default | Lấy sai cột/sequence | Dùng output của statement và test trigger |

## 25. Checklist thiết kế

### Schema
- [ ] Khóa chính có PRIMARY KEY/UNIQUE thực sự?
- [ ] Kiểu số đủ dải phát triển?
- [ ] Identity hay sequence phù hợp với use case?
- [ ] `ALWAYS` hay `BY DEFAULT` đúng chính sách import?
- [ ] Sequence có owner/dependency phù hợp?
- [ ] Không dùng CYCLE cho khóa cần duy nhất toàn đời?

### Insert và lấy ID
- [ ] Dùng RETURNING/OUTPUT/generated keys hoặc API DBMS tương ứng?
- [ ] Lấy key trên cùng statement/connection/session?
- [ ] Kiểm driver trả đúng cột ID?
- [ ] Multi-row/batch mapping đã được test?
- [ ] Trigger/default có ảnh hưởng giá trị trả về?
- [ ] Không dùng MAX(id), TOP 1 hoặc IDENT_CURRENT để lấy ID vừa sinh?

### Transaction và concurrency
- [ ] ID được dùng trong cùng transaction cho hàng con?
- [ ] Chỉ trả response thành công sau commit thành công?
- [ ] Chấp nhận gaps do rollback/failed insert?
- [ ] Không giả định ID phản ánh commit order?
- [ ] Retry có idempotency phù hợp?
- [ ] Connection pool không làm mất session context?

### Migration/vận hành
- [ ] Import explicit IDs có kế hoạch reseed?
- [ ] Reseed được chạy khi writers đã được điều phối?
- [ ] Backup/replication/failover hiểu cache/gap semantics?
- [ ] Quyền sequence/identity tối thiểu?
- [ ] ID công khai không được dùng làm cơ chế authorization?

## 26. Sơ đồ lựa chọn

```text
               CẦN TẠO HÀNG MỚI
                       |
                       v
             ID do DB hay app sinh?
                 /           \
               DB             App/distributed
               |                    |
               v                    v
        Identity hay sequence?   UUID/ID service
           /          \
       Một cột       Cần cấp trước/
       tự động       dùng độc lập
          |              |
          v              v
      Identity         Sequence
          |              |
          +------+-------+
                 |
                 v
             INSERT
                 |
                 v
       Cần lấy ID ngay sau INSERT?
                 |
                 v
       RETURNING / OUTPUT /
       getGeneratedKeys / API
                 |
                 v
       Dùng ID trong transaction
       cho hàng con/response
                 |
                 v
       COMMIT thành công rồi trả
       kết quả thành công cho client
```

## 27. Bài tập thực hành

Các bài PostgreSQL dùng bảng `demo_pg_customers` hoặc bảng sequence được tạo trong cùng session. Những bài MySQL, SQL Server, Oracle và SQLite là cú pháp riêng của DBMS tương ứng; không chạy nguyên một dialect trên DBMS khác.

### Bài 1 — Identity column
Tạo bảng PostgreSQL có `BIGINT GENERATED ALWAYS AS IDENTITY`, INSERT hai hàng và dùng `RETURNING` để lấy ID. Vì sao không cần tự chọn ID trước?

### Bài 2 — ALWAYS và BY DEFAULT
Tạo hai bảng identity với hai chế độ. Thử INSERT không có ID và INSERT có explicit ID. So sánh hành vi và giải thích khi nào dùng OVERRIDING SYSTEM VALUE.

### Bài 3 — Sequence
Tạo sequence start 1000, increment 5, cache 10. Gọi NEXTVAL nhiều lần. Dự đoán các giá trị trả về và kiểm tra thực tế.

### Bài 4 — CURRVAL
Trong một session, gọi NEXTVAL rồi CURRVAL. Mở session khác và gọi CURRVAL trước NEXTVAL. Vì sao hai kết quả khác nhau?

### Bài 5 — LASTVAL
Gọi NEXTVAL sequence A rồi sequence B. `lastval()` trả giá trị nào? Vì sao nó có thể nguy hiểm nếu trigger gọi sequence khác?

### Bài 6 — MAX(id) race
Mô phỏng hai session A/B: A INSERT, B INSERT/COMMIT, A SELECT MAX. Giải thích vì sao A có thể lấy ID của B. Viết lại bằng RETURNING.

### Bài 7 — Rollback
Gọi NEXTVAL hoặc INSERT identity trong transaction rồi ROLLBACK. Chèn hàng tiếp theo. Vì sao ID bị bỏ trống?

### Bài 8 — RETURNING nhiều hàng
INSERT ba customers bằng một VALUES list và RETURNING ID/email. Dùng email duy nhất để ánh xạ từng input với ID.

### Bài 9 — JDBC generated keys
Viết PreparedStatement với RETURN_GENERATED_KEYS, executeUpdate, getGeneratedKeys. Xử lý trường hợp driver không trả key.

### Bài 10 — JDBC PostgreSQL RETURNING
Viết query INSERT ... RETURNING customer_id và đọc ResultSet. So sánh với getGeneratedKeys trên đúng PostgreSQL JDBC version.

### Bài 11 — MySQL AUTO_INCREMENT
Tạo bảng MySQL AUTO_INCREMENT, INSERT và SELECT LAST_INSERT_ID trên cùng connection. Mở connection thứ hai và giải thích vì sao không dùng nó để lấy ID của connection đầu.

### Bài 12 — MySQL multi-row
INSERT ba hàng cùng statement. Kiểm tra LAST_INSERT_ID và driver generated keys. Vì sao không mặc định first_id + 1, +2 luôn đúng?

### Bài 13 — SQL Server SCOPE_IDENTITY
Tạo bảng identity và INSERT một hàng. Lấy SCOPE_IDENTITY. Kiểu trả về của hàm là gì và vì sao thường cần CAST?

### Bài 14 — Trigger SQL Server
Tạo trigger ghi audit vào bảng identity khác. So sánh @@IDENTITY và SCOPE_IDENTITY. Thử OUTPUT INSERTED.CustomerId.

### Bài 15 — IDENT_CURRENT
Hai session INSERT cùng bảng. Vì sao IDENT_CURRENT không phải hàm lấy ID riêng của caller?

### Bài 16 — SQL Server sequence
Tạo sequence CACHE 50, gọi NEXT VALUE FOR, dùng làm DEFAULT và OUTPUT ID. So sánh với IDENTITY.

### Bài 17 — Oracle sequence
Tạo sequence Oracle, INSERT bằng NEXTVAL và lấy CURRVAL. Thử CURRVAL trước NEXTVAL trong một session mới.

### Bài 18 — Oracle RETURNING INTO
Viết PL/SQL INSERT ... RETURNING customer_id INTO biến. Vì sao cách này gắn ID với hàng vừa chèn?

### Bài 19 — Oracle identity
Tạo identity column ALWAYS và BY DEFAULT trong Oracle version hỗ trợ. Thử explicit value và giải thích khác biệt.

### Bài 20 — SQLite ROWID
Tạo `INTEGER PRIMARY KEY`, INSERT bỏ ID, đọc RETURNING hoặc last_insert_rowid. Chạy hai connection và so sánh phạm vi.

### Bài 21 — SQLite AUTOINCREMENT
So sánh `INTEGER PRIMARY KEY` và `INTEGER PRIMARY KEY AUTOINCREMENT`. Xóa hàng có rowid lớn nhất, INSERT tiếp và quan sát khác biệt.

### Bài 22 — SQLite BIGINT
Thử `BIGINT PRIMARY KEY` thay cho `INTEGER PRIMARY KEY`. Giải thích vì sao không có cùng alias ROWID semantics.

### Bài 23 — Multi-row mapping
Chèn nhiều hàng và yêu cầu mapping chính xác input-to-ID. Thiết kế correlation key duy nhất và giải thích vì sao không chỉ dựa vào thứ tự output.

### Bài 24 — Trigger và last identity
Thiết kế một trigger ghi audit có sequence/identity riêng. Với PostgreSQL, SQL Server và MySQL, xác định cách lấy ID bảng mục tiêu không bị nhầm bởi trigger.

### Bài 25 — Import explicit IDs
Import các ID 100, 101, 500 vào bảng có generator. Kiểm tra lần INSERT tiếp theo và lập kế hoạch đồng bộ sequence/identity theo DBMS.

### Bài 26 — Sequence gaps
Liệt kê ít nhất năm nguyên nhân tạo gaps. Giải thích vì sao không nên dùng sequence làm số hóa đơn liên tục.

### Bài 27 — ID và commit order
Hai transaction nhận ID theo thứ tự 100, 101 nhưng commit ngược. Vì sao ORDER BY id không chứng minh thứ tự commit?

### Bài 28 — UPSERT
PostgreSQL INSERT ON CONFLICT DO UPDATE RETURNING. So sánh với DO NOTHING RETURNING khi email đã tồn tại. Ứng dụng cần làm gì nếu không có hàng trả về?

### Bài 29 — JavaScript BIGINT
Một ID lớn hơn Number.MAX_SAFE_INTEGER. Điều gì xảy ra nếu serialize qua JSON bằng JavaScript Number? Đề xuất BigInt/string contract.

### Bài 30 — Thiết kế repository đa DBMS
Thiết kế interface `insertCustomer()` trả ID. Tạo chiến lược PostgreSQL RETURNING, MySQL/JDBC generated keys, SQL Server OUTPUT, Oracle RETURNING/sequence và SQLite RETURNING. Định nghĩa integration tests cho trigger, batch, rollback, pool và concurrency.

## 28. Tổng kết

Identity column và sequence giúp database cấp định danh an toàn khi nhiều session ghi đồng thời. Identity thường thuận tiện cho một cột tự sinh; sequence độc lập linh hoạt hơn khi cần cấp giá trị trước INSERT hoặc dùng theo một thiết kế riêng. PostgreSQL có `GENERATED ... AS IDENTITY`, `nextval/currval/lastval` và `RETURNING`; MySQL có `AUTO_INCREMENT` và `LAST_INSERT_ID()` theo connection; SQL Server có `IDENTITY`, `SCOPE_IDENTITY()`, `OUTPUT INSERTED` và `SEQUENCE`; Oracle có identity, `NEXTVAL/CURRVAL` và `RETURNING INTO`; SQLite dùng `INTEGER PRIMARY KEY`/ROWID, `last_insert_rowid()` và `RETURNING` theo version.

Điều quan trọng nhất là **lấy ID từ chính thao tác INSERT**. `SELECT MAX(id)`, `IDENT_CURRENT`, `@@IDENTITY` trong bối cảnh trigger, hoặc hỏi last ID trên connection khác đều có thể trả sai định danh. JDBC `getGeneratedKeys()` là API chung hữu ích nhưng cần xác minh driver, đặc biệt với multi-row insert và batch. Các cú pháp `RETURNING`/`OUTPUT` thường cho thấy rõ hàng nào vừa được ghi.

ID tự sinh không đảm bảo liên tục, không đại diện cho thứ tự commit, và không thay thế quyền truy cập. Rollback, lỗi insert, conflict, cache, trigger và restart có thể tạo khoảng trống. Sau import explicit IDs, generator cần được đồng bộ trong migration có kiểm soát. Nếu nghiệp vụ yêu cầu số chứng từ liên tục hoặc ID toàn cục phân tán, đó là bài toán riêng cần thiết kế riêng.

Hãy thiết kế schema với kiểu khóa đủ lớn, PRIMARY KEY rõ ràng, chọn identity/sequence theo use case, dùng RETURNING/OUTPUT/generated keys, giữ đúng connection và transaction, kiểm driver thực tế và không dựa vào khoảng trống hoặc thứ tự ID. Khi làm được những điều đó, việc tạo và lấy định danh vừa sinh sẽ đúng ngay cả khi nhiều request, trigger, batch và transaction cùng hoạt động.
