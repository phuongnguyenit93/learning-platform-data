# Đối chiếu khóa sinh, sequence và cú pháp trả dữ liệu trong JDBC

Trong chương **Đa hệ quản trị**, ứng dụng Java sử dụng **JDBC** có thể gửi những câu `INSERT` tương tự nhau tới PostgreSQL, MySQL, SQL Server, Oracle, SQLite hoặc H2. Tuy nhiên, việc **cơ sở dữ liệu sinh khóa chính (generated key)** và cách lấy lại giá trị vừa sinh **không hoàn toàn giống nhau**.

Một chương trình có thể chạy tốt trên một driver khi gọi `PreparedStatement.getGeneratedKeys()`, nhưng driver khác lại yêu cầu chỉ rõ tên cột, trả kết quả khác khi batch, hoặc có thể không hỗ trợ tình huống cụ thể. Ngoài JDBC, mỗi hệ quản trị còn có cú pháp riêng như `RETURNING`, `OUTPUT INSERTED`, `RETURNING ... INTO` hay các hàm lấy identity cuối của **cùng connection**. Nếu chọn sai, ứng dụng có thể liên kết đơn hàng với một ID không đúng, chèn bản ghi con sai khóa ngoại hoặc retry làm tạo đơn trùng.

Bài học kết nối kiến thức nền tảng JDBC — driver, `DataSource`, `PreparedStatement`, `ResultSet`, CRUD, transaction và batching — với cách triển khai khóa sinh trong **nhiều hệ quản trị cơ sở dữ liệu**. Mục tiêu không chỉ là nhớ cú pháp, mà là **biết giới hạn nào có thể lập trình bằng API chuẩn và giới hạn nào phải kiểm chứng theo DBMS/driver**.

Sau bài học, bạn có thể:

- Phân biệt **IDENTITY/AUTO_INCREMENT**, **SEQUENCE** và khóa do ứng dụng tự sinh.
- Sử dụng `Statement.RETURN_GENERATED_KEYS`, `prepareStatement(sql, columnNames)` và `getGeneratedKeys()` đúng vòng đời.
- So sánh cú pháp trả dữ liệu của PostgreSQL, MySQL, SQL Server, Oracle và SQLite.
- Hiểu vì sao sequence/identity có thể **nhảy số**, ngay cả khi transaction rollback.
- Tránh những giả định nguy hiểm khi lấy khóa của **nhiều hàng hoặc JDBC batch**.
- Thiết kế transaction, idempotency, test đa driver và cơ chế fallback rõ ràng.

## 1. Khóa chính sinh tự động giải quyết vấn đề gì?

Giả sử ứng dụng lưu đơn hàng:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    external_ref VARCHAR(80) NOT NULL UNIQUE,
    total_cents BIGINT NOT NULL
);
~~~

Nếu dùng SQL trên, ứng dụng phải cung cấp giá trị `id` khi `INSERT`. Có nhiều cách để sinh nó:

1. **DBMS tự sinh khi INSERT**: cột IDENTITY, AUTO_INCREMENT hoặc cơ chế đặc thù của hệ quản trị.
2. **DBMS cấp giá trị qua một SEQUENCE**: ứng dụng hoặc default expression lấy `NEXTVAL` rồi chèn.
3. **Ứng dụng tự sinh khóa**: ví dụ UUID/ULID hoặc một ID generator riêng; DBMS chỉ kiểm tra uniqueness.
4. **Khóa nghiệp vụ có sẵn**: ví dụ một mã định danh đã được bảo đảm duy nhất bởi hợp đồng dữ liệu.

Ở bài này, ta tập trung vào **(1) và (2)**, nhưng cần biết hai loại còn lại để chọn giải pháp khi hỗ trợ đa DBMS.

| Thuật ngữ | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| **Generated key** | Giá trị khóa được sinh hoặc xác định khi INSERT, được ứng dụng cần đọc lại | Có thể được trả qua API JDBC hoặc cú pháp SQL riêng |
| **IDENTITY** | Cột có cơ chế DBMS tự cấp giá trị khi chèn | Cú pháp, seed, increment và quy tắc explicit insert khác nhau |
| **AUTO_INCREMENT** | Tên cơ chế thường thấy ở MySQL/MariaDB | Không phải từ khóa SQL portable cho mọi DBMS |
| **SEQUENCE** | Đối tượng DBMS cung cấp chuỗi số qua `NEXTVAL`/tương đương | Thường độc lập với transaction của hàng |
| **RETURNING/OUTPUT** | Cú pháp trả cột từ hàng được INSERT/UPDATE/DELETE | Rất hữu ích khi cần nhiều giá trị chứ không chỉ ID |
| **JDBC `getGeneratedKeys()`** | API đọc các khóa sinh được driver báo cáo | Mức hỗ trợ và cấu trúc kết quả tùy driver |

**Khóa sinh không nhất thiết tăng liên tục theo thời điểm commit**, và cũng không phải là bằng chứng một đơn hàng đã thanh toán, một transaction thành công hay một người dùng có quyền truy cập bản ghi.

## 2. Tổng quan khác biệt giữa các hệ quản trị

Bảng sau tập trung vào các cách triển khai phổ biến; cú pháp và giới hạn phải được kiểm tra với **phiên bản server và JDBC driver thực tế**.

| DBMS | Tạo cột khóa phổ biến | Cách trả khóa/dữ liệu thường dùng |
| --- | --- | --- |
| **PostgreSQL** | `GENERATED ... AS IDENTITY`, cũ hơn có `SERIAL`; hoặc sequence với `nextval` | `INSERT ... RETURNING id, ...`; JDBC `getGeneratedKeys()` qua pgJDBC |
| **MySQL / InnoDB** | `AUTO_INCREMENT` | JDBC `getGeneratedKeys()`; `LAST_INSERT_ID()` trên cùng connection |
| **MariaDB** | `AUTO_INCREMENT`, cũng có hỗ trợ sequence tùy phiên bản | JDBC generated keys; một số phiên bản hỗ trợ `INSERT ... RETURNING` |
| **SQL Server** | `IDENTITY(seed, increment)`; cũng có `SEQUENCE` | `OUTPUT INSERTED.id, ...`; `SCOPE_IDENTITY()`; JDBC generated keys |
| **Oracle Database** | `GENERATED ... AS IDENTITY` hoặc `SEQUENCE` | `INSERT ... RETURNING id INTO ...` với cơ chế bind output; JDBC generated keys theo driver |
| **SQLite** | `INTEGER PRIMARY KEY` gắn với `rowid`; có tùy chọn `AUTOINCREMENT` | `INSERT ... RETURNING id` ở các phiên bản hỗ trợ; `last_insert_rowid()` trên cùng connection |
| **H2** | `GENERATED ... AS IDENTITY` hoặc sequence | JDBC generated keys và cú pháp do H2 hỗ trợ; không đại diện hoàn toàn cho DBMS khác |

Đừng coi bảng là bản cam kết **mọi overload JDBC luôn được hỗ trợ**. Ví dụ, việc trả cả cột khóa từ một lệnh upsert hoặc nhiều hàng có thể khác hành vi của một INSERT đơn lẻ.

## 3. Cách portable nhất để bắt đầu: JDBC `getGeneratedKeys()`

JDBC cung cấp API để yêu cầu driver trả khóa vừa sinh.

### 3.1. Dùng `Statement.RETURN_GENERATED_KEYS`

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

static long insertOrder(
        Connection conn, String externalRef, long totalCents
) throws SQLException {

    String sql = """
        INSERT INTO orders (external_ref, total_cents)
        VALUES (?, ?)
        """;

    try (PreparedStatement ps = conn.prepareStatement(
            sql, Statement.RETURN_GENERATED_KEYS)) {

        ps.setString(1, externalRef);
        ps.setLong(2, totalCents);

        int affected = ps.executeUpdate();
        if (affected != 1) {
            throw new SQLException(
                "INSERT không ảnh hưởng đúng một hàng"
            );
        }

        try (ResultSet keys = ps.getGeneratedKeys()) {
            if (!keys.next()) {
                throw new SQLException(
                    "Driver không trả generated key"
                );
            }

            long id = keys.getLong(1);
            if (keys.wasNull()) {
                throw new SQLException(
                    "Generated key là SQL NULL"
                );
            }

            return id;
        }
    }
}
~~~

Phần quan trọng:

1. `RETURN_GENERATED_KEYS` được truyền lúc **tạo PreparedStatement**, không phải sau khi execute.
2. `getGeneratedKeys()` được gọi **sau `executeUpdate()`**.
3. Các khóa trả về nằm trong một `ResultSet`, vì vậy phải gọi `next()` và đóng tài nguyên.
4. Số cột, thứ tự cột và kiểu dữ liệu **không nên được giả định chung cho mọi driver**.
5. Đối với đơn hàng mới với một INSERT, ứng dụng mong đợi một ID; nếu driver không trả giá trị, phải xử lý lỗi thay vì suy đoán.

Code này dựa trên giả định cột `orders.id` do DBMS sinh và có kiểu nguyên 64-bit tương thích với `getLong()`. Nếu khóa là UUID hoặc DBMS trả kiểu khác, phải đọc bằng kiểu JDBC phù hợp.

### 3.2. Yêu cầu đích danh cột khóa

Một cách rõ ràng hơn trong nhiều driver:

~~~java
String sql = """
    INSERT INTO orders (external_ref, total_cents)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(
        sql, new String[] {"id"})) {

    ps.setString(1, "ORDER-2026-0001");
    ps.setLong(2, 125_000L);

    if (ps.executeUpdate() != 1) {
        throw new SQLException("INSERT không thành công");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("Không nhận được ID");
        }
        long id = keys.getLong(1);
        System.out.println("ID vừa sinh: " + id);
    }
}
~~~

Overload `prepareStatement(sql, String[] columnNames)` cho biết **các cột muốn driver trả về**. Khi được hỗ trợ, nó tránh phụ thuộc vào việc driver tự chọn những cột nào.

Tuy nhiên:

- Không phải driver/kiểu statement nào cũng hỗ trợ chọn danh sách cột.
- Tên cột có thể chịu quy tắc chữ hoa/chữ thường và quoted identifiers của DBMS.
- Một số driver hỗ trợ `RETURN_GENERATED_KEYS` nhưng không hỗ trợ overload chỉ định cột theo cùng cách.
- Danh sách cột phải do **code tin cậy xác định**; không ghép tên cột từ request tùy ý.
- Kể cả khi khai báo `{"id"}`, cần test cấu trúc `ResultSet` thực tế để bảo đảm `getLong(1)` là ID mong đợi.

### 3.3. Kiểm tra driver công bố hỗ trợ

~~~java
import java.sql.DatabaseMetaData;

DatabaseMetaData meta = conn.getMetaData();
System.out.println(
    "DBMS: " + meta.getDatabaseProductName());
System.out.println(
    "Driver: " + meta.getDriverName());
System.out.println(
    "Hỗ trợ generated keys: "
        + meta.supportsGetGeneratedKeys());
~~~

`supportsGetGeneratedKeys()` là **điểm bắt đầu**, không phải bằng chứng mọi biến thể INSERT, batch, upsert và kiểu cột đều thành công.

Một driver có thể hỗ trợ khóa sinh cho INSERT đơn hàng nhưng trả kết quả khác cho một lệnh `INSERT ... SELECT` hoặc batch. Cần kiểm thử **đúng câu SQL và workload** của ứng dụng.

## 4. PostgreSQL: IDENTITY, SEQUENCE và `RETURNING`

PostgreSQL hỗ trợ cách khai báo cột identity theo SQL chuẩn hiện đại:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    external_ref VARCHAR(80) NOT NULL UNIQUE,
    total_cents BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

### 4.1. `GENERATED ALWAYS` và `BY DEFAULT`

- `GENERATED ALWAYS AS IDENTITY`: DBMS thường yêu cầu sinh ID, việc truyền ID tường minh cần cơ chế override được phép.
- `GENERATED BY DEFAULT AS IDENTITY`: DBMS sinh giá trị nếu câu INSERT không cung cấp, nhưng có thể cho phép ứng dụng truyền giá trị tường minh.
- `SERIAL`/`BIGSERIAL` là cú pháp kiểu cũ của PostgreSQL, thường tạo một sequence kết hợp với default expression. Chúng không phải kiểu SQL chuẩn và không hoàn toàn đồng nghĩa với identity column về mặt metadata/quy tắc quản lý.

Khi ứng dụng thực sự cần tự sinh ID, nên cân nhắc cơ chế **IDENTITY** phù hợp thay vì tự lấy `MAX(id) + 1`.

### 4.2. Trả ngay dữ liệu vừa ghi bằng `RETURNING`

~~~sql
INSERT INTO orders (external_ref, total_cents)
VALUES (?, ?)
RETURNING id, created_at;
~~~

`RETURNING` là cú pháp của PostgreSQL để trả những giá trị từ hàng chịu tác động bởi DML. Nó có thể trả:

- ID do identity/sequence sinh.
- Thời gian default được DBMS gán.
- Giá trị đã được biểu thức mặc định hoặc trigger điều chỉnh theo semantics của DBMS.
- Nhiều hàng và nhiều cột, nếu lệnh DML ảnh hưởng nhiều hàng.

Ví dụ JDBC với `PreparedStatement.executeQuery()` cho PostgreSQL:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

static long insertPgReturning(
        Connection conn, String externalRef, long totalCents
) throws SQLException {
    String sql = """
        INSERT INTO orders (external_ref, total_cents)
        VALUES (?, ?)
        RETURNING id
        """;

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setString(1, externalRef);
        ps.setLong(2, totalCents);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException(
                    "INSERT RETURNING không trả hàng"
                );
            }

            long id = rs.getLong("id");
            if (rs.wasNull()) {
                throw new SQLException("ID bị NULL");
            }
            return id;
        }
    }
}
~~~

**Đừng gọi `executeUpdate()` rồi mặc định sẽ đọc được `RETURNING` qua `getGeneratedKeys()`**. Khi SQL đã có mệnh đề trả hàng, cách xử lý kết quả phụ thuộc driver. Với PostgreSQL, xử lý `INSERT ... RETURNING` như một statement trả `ResultSet` qua `executeQuery()` là mẫu rõ ràng.

### 4.3. Sequence tường minh

PostgreSQL hỗ trợ:

~~~sql
CREATE SEQUENCE order_number_seq
    START WITH 1
    INCREMENT BY 1;

SELECT nextval('order_number_seq');
~~~

Hoặc cấp ID bên trong INSERT:

~~~sql
INSERT INTO orders (id, external_ref, total_cents)
VALUES (nextval('order_number_seq'), ?, ?)
RETURNING id;
~~~

**Chú ý:** Nếu bảng đã dùng cột IDENTITY với sequence ngầm định, ví dụ trên dùng **sequence riêng** nên cần thiết kế đồng bộ cẩn thận. Không tùy tiện tạo thêm một sequence để cùng sinh ID cho một cột mà không xác định rõ default/ownership.

`currval('order_number_seq')` trả giá trị sequence gần nhất **đã được `nextval` cấp trong session hiện tại**, và lỗi nếu session chưa gọi `nextval` phù hợp. `lastval()` liên quan sequence được gọi gần nhất trong session, có thể không phải sequence bạn muốn.

**Cách đáng tin để lấy khóa của hàng vừa INSERT là `RETURNING id` hoặc JDBC generated keys**, thay vì gọi một câu query “lấy sequence hiện tại” không gắn rõ với câu INSERT.

## 5. MySQL/InnoDB: `AUTO_INCREMENT` và `LAST_INSERT_ID()`

MySQL thường khai báo:

~~~sql
CREATE TABLE orders (
    id BIGINT NOT NULL AUTO_INCREMENT,
    external_ref VARCHAR(80) NOT NULL,
    total_cents BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_orders_external_ref (external_ref)
) ENGINE = InnoDB;
~~~

Khi INSERT bỏ qua cột ID, InnoDB có thể tự cấp ID:

~~~sql
INSERT INTO orders (external_ref, total_cents)
VALUES (?, ?);
~~~

Với MySQL Connector/J, ứng dụng thường dùng `Statement.RETURN_GENERATED_KEYS` hoặc overload yêu cầu cột, tùy phiên bản driver và loại câu lệnh.

### 5.1. `LAST_INSERT_ID()` thuộc session/connection

MySQL hỗ trợ:

~~~sql
SELECT LAST_INSERT_ID();
~~~

Giá trị này gắn với **connection/session** thực hiện câu INSERT. Vì vậy:

- Phải gọi trên **chính connection đã INSERT**, không lấy một connection mới từ pool.
- Không để mã dùng chung connection chạy một thao tác khác có thể thay đổi giá trị trước khi đọc.
- Không dùng `SELECT MAX(id)` để thay thế: transaction khác có thể chèn hàng và tạo ID lớn hơn.
- Khi INSERT nhiều hàng, đừng suy diễn tất cả khóa từ một giá trị và “+1” theo mặc định.

Ví dụ ý tưởng:

~~~java
// Phải giữ cùng Connection trong cả INSERT và SELECT.
try (PreparedStatement ps = conn.prepareStatement(
        "INSERT INTO orders(external_ref, total_cents) "
        + "VALUES (?, ?)")) {

    ps.setString(1, externalRef);
    ps.setLong(2, totalCents);
    ps.executeUpdate();
}

try (PreparedStatement ps = conn.prepareStatement(
        "SELECT LAST_INSERT_ID()");
     ResultSet rs = ps.executeQuery()) {

    if (!rs.next()) {
        throw new SQLException("Không có LAST_INSERT_ID");
    }

    long id = rs.getLong(1);
}
~~~

Mã trên thể hiện cách liên hệ cùng session, không phải lý do để ưu tiên hai round-trip hơn `getGeneratedKeys()`. Với nhiều statement/driver, `getGeneratedKeys()` thường tiện và bộc lộ ý định rõ hơn.

### 5.2. Lưu ý với upsert và multi-row INSERT

MySQL có `INSERT ... ON DUPLICATE KEY UPDATE`. Khi đường **INSERT** và **UPDATE** có thể xảy ra, ý nghĩa khóa trả về, update count và `LAST_INSERT_ID()` cần được **kiểm thử riêng** với driver/phiên bản mục tiêu.

Với nhiều hàng:

~~~sql
INSERT INTO orders (external_ref, total_cents)
VALUES (?, ?), (?, ?), (?, ?);
~~~

Không coi ID đầu tiên cộng lần lượt một đơn vị là cách xác định mọi ID. Server có thể có cấu hình increment, trigger, bỏ trống ID, concurrent inserts hoặc khác biệt về cách cấp phát.

**MariaDB là sản phẩm khác MySQL** dù có nhiều cú pháp chung. Một số phiên bản MariaDB hỗ trợ `INSERT ... RETURNING`; không tự mang cú pháp đó sang MySQL hay giả định cùng phiên bản/tính năng. Trước khi sử dụng, kiểm tra đúng server và JDBC driver.

## 6. SQL Server: `IDENTITY`, `OUTPUT INSERTED` và `SCOPE_IDENTITY()`

Ví dụ SQL Server:

~~~sql
CREATE TABLE orders (
    id BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
    external_ref VARCHAR(80) NOT NULL UNIQUE,
    total_cents BIGINT NOT NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
~~~

`IDENTITY(1, 1)` biểu thị seed và increment. Giá trị có thể xuất hiện **khoảng trống** khi rollback, restart, cache hoặc thao tác đồng thời.

### 6.1. `OUTPUT INSERTED`

SQL Server hỗ trợ trả giá trị của hàng chịu tác động bởi DML:

~~~sql
INSERT INTO orders (external_ref, total_cents)
OUTPUT INSERTED.id, INSERTED.created_at
VALUES (?, ?);
~~~

Mệnh đề `OUTPUT` có thể trả dữ liệu cho nhiều hàng trong một lệnh, không chỉ một ID. Tuy nhiên:

- Cú pháp SQL Server khác PostgreSQL `RETURNING`.
- `OUTPUT` không đi kèm `INTO` có những giới hạn khi bảng đích có trigger được bật cho thao tác DML; trong tình huống này có thể cần `OUTPUT ... INTO` hoặc giải pháp khác.
- **Không dựa vào thứ tự các hàng `OUTPUT`** để map với thứ tự input nếu hợp đồng không bảo đảm.
- Các giá trị `INSERTED` có thời điểm quan sát và ngữ nghĩa theo SQL Server; với trigger thay đổi dữ liệu sau đó cần kiểm tra kết quả thực.

Nếu dùng SQL Server JDBC driver, khả năng `getGeneratedKeys()` và cách JDBC nhận `OUTPUT` phải được kiểm thử trên phiên bản driver dùng thật.

### 6.2. `SCOPE_IDENTITY()` so với `@@IDENTITY`

SQL Server hỗ trợ:

~~~sql
SELECT SCOPE_IDENTITY();
~~~

Hàm này trả identity cuối được sinh **trong scope hiện tại**, và có kiểu số theo quy tắc của SQL Server. `@@IDENTITY` lại liên quan identity cuối trên session, **có thể đến từ trigger** thực hiện INSERT ở bảng khác.

Vì thế, **tránh dùng `@@IDENTITY` để lấy khóa bảng chính khi trigger có thể can thiệp**. Cũng đừng dùng `IDENT_CURRENT('orders')` để lấy ID của riêng giao dịch mình: giá trị đó không bị giới hạn bởi session/scope của bạn.

Với nhiều hàng hoặc khi cần nhiều cột, `OUTPUT INSERTED...` thường diễn đạt rõ hơn. Với một hàng, JDBC generated keys là lựa chọn đáng kiểm thử.

**Quan trọng:** `SCOPE_IDENTITY()` phải được gọi trong đúng scope SQL Server; việc đưa nó vào **một câu lệnh/batch khác** không phải mặc nhiên giữ scope của INSERT trước. Không suy luận rằng chỉ vì dùng cùng connection thì mọi truy vấn `SCOPE_IDENTITY()` đều lấy đúng giá trị. Ưu tiên `OUTPUT` hoặc generated keys khi cần tính rõ ràng.

## 7. Oracle Database: IDENTITY, SEQUENCE và `RETURNING ... INTO`

Oracle hỗ trợ cột identity trong các phiên bản hiện đại:

~~~sql
CREATE TABLE orders (
    id NUMBER(19)
        GENERATED BY DEFAULT AS IDENTITY
        PRIMARY KEY,
    external_ref VARCHAR2(80) NOT NULL UNIQUE,
    total_cents NUMBER(19) NOT NULL
);
~~~

Ngoài ra có thể dùng sequence độc lập:

~~~sql
CREATE SEQUENCE orders_seq
    START WITH 1
    INCREMENT BY 1;
~~~

Cấp ID ngay trong INSERT:

~~~sql
INSERT INTO orders (id, external_ref, total_cents)
VALUES (orders_seq.NEXTVAL, ?, ?);
~~~

Đọc giá trị tiếp theo:

~~~sql
SELECT orders_seq.NEXTVAL FROM dual;
~~~

Đọc `NEXTVAL` trước khi INSERT giúp ứng dụng biết ID để chuẩn bị bản ghi liên quan. Tuy nhiên, **đã nhận ID không đồng nghĩa INSERT đã thành công**, và sequence vẫn có thể bỏ qua giá trị nếu transaction rollback.

### 7.1. Cú pháp trả dữ liệu của Oracle

Oracle sử dụng dạng DML returning:

~~~sql
INSERT INTO orders (external_ref, total_cents)
VALUES (:external_ref, :total_cents)
RETURNING id INTO :out_id;
~~~

Các dấu `:external_ref`, `:total_cents`, `:out_id` ở đây minh họa **bind variables trong cú pháp Oracle**, không phải một đoạn `PreparedStatement` JDBC portable có thể dán nguyên xi.

Để nhận biến `:out_id`, ứng dụng phải đăng ký **output parameter** hoặc dùng cơ chế returning mà driver Oracle hỗ trợ. Tùy phiên bản driver/API, có thể sử dụng `OraclePreparedStatement.registerReturnParameter(...)` hoặc phương án CallableStatement/PLSQL phù hợp.

**Không giả định `PreparedStatement.executeQuery()` với `INSERT ... RETURNING ... INTO` hoạt động như PostgreSQL**. Oracle có cách bind output riêng; cần bám vào tài liệu và kiểm thử driver mục tiêu.

### 7.2. Dùng `getGeneratedKeys()` với Oracle

Oracle JDBC driver có hỗ trợ generated keys trong các điều kiện nhất định. Tuy nhiên, kiểu statement, overload chỉ định tên cột, tên cột/case và những cột được trả có thể khác driver khác.

Một hướng thử là:

~~~java
String sql = """
    INSERT INTO orders (external_ref, total_cents)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = conn.prepareStatement(
        sql, new String[] {"ID"})) {
    // Bind input, executeUpdate(), getGeneratedKeys().
}
~~~

Dùng tên cột chính xác theo quy tắc định danh của Oracle/schema. Đây chỉ là khung minh họa: **phải xác minh** `getGeneratedKeys()` trả đúng ID trong môi trường Oracle thực tế.

Với key kiểu `NUMBER(19)`, đôi khi driver trả `BigDecimal`. Chọn cách chuyển đổi tránh mất độ chính xác/tràn số; không dùng `int` cho khóa có miền giá trị vượt 32 bit.

## 8. SQLite: `INTEGER PRIMARY KEY`, `AUTOINCREMENT` và `RETURNING`

SQLite có cơ chế đặc thù về `rowid`. Trong bảng rowid thông thường:

~~~sql
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    external_ref TEXT NOT NULL UNIQUE,
    total_cents INTEGER NOT NULL
);
~~~

Cột `INTEGER PRIMARY KEY` (với đúng quy tắc khai báo của SQLite) là alias của `rowid`. Nếu INSERT không cung cấp ID, SQLite thường chọn một rowid còn khả dụng.

### `AUTOINCREMENT` có cần thiết không?

SQLite cho phép:

~~~sql
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_ref TEXT NOT NULL UNIQUE,
    total_cents INTEGER NOT NULL
);
~~~

`AUTOINCREMENT` trong SQLite **không chỉ là cách “bật tự sinh ID”**. Nó thay đổi thuật toán chọn rowid để hạn chế tái sử dụng các rowid đã từng tồn tại theo quy tắc của SQLite, với chi phí quản lý bổ sung.

- `INTEGER PRIMARY KEY` đã đủ cho nhiều nhu cầu sinh ID.
- `AUTOINCREMENT` có overhead về lưu trữ/hiệu năng, không nên thêm chỉ vì quen từ MySQL.
- Nó **không bảo đảm chuỗi ID không có khoảng trống**.
- Những bảng `WITHOUT ROWID` có cơ chế khóa khác; không thể mặc nhiên áp dụng `last_insert_rowid()` để đọc khóa của bảng đó.

### SQLite `RETURNING`

SQLite hỗ trợ mệnh đề `RETURNING` trên nhiều thao tác DML từ **SQLite 3.35.0**:

~~~sql
INSERT INTO orders (external_ref, total_cents)
VALUES (?, ?)
RETURNING id;
~~~

Khi dùng SQLite JDBC driver hỗ trợ phiên bản SQLite phù hợp, có thể đọc `ResultSet` từ câu lệnh này theo khả năng driver. Test cách gọi `executeQuery()` hoặc `execute()` với driver thực tế; không giả định mọi SQLite driver đều xử lý DML returning giống nhau.

### `last_insert_rowid()`

~~~sql
SELECT last_insert_rowid();
~~~

Giá trị là rowid của thao tác INSERT phù hợp trên **connection hiện tại**. Không gọi qua một connection mới lấy từ pool. Nó có nhiều chi tiết liên quan trigger, virtual table và thao tác đồng thời trên cùng connection; phải đọc đúng tài liệu SQLite khi phụ thuộc vào hành vi đó.

**Không dùng `SELECT MAX(id)`** thay `last_insert_rowid()`: câu MAX không liên kết với session đã INSERT và có thể trả khóa của transaction khác.

## 9. Vì sao `SEQUENCE` và `IDENTITY` thường có khoảng trống?

Rất nhiều lỗi nghiệp vụ đến từ giả định:

> “Nếu đơn 10 đã tồn tại thì đơn tiếp theo bắt buộc là 11.”

Giả định này sai trong các hệ dùng sequence/identity thông thường.

### Ví dụ sequence không rollback

PostgreSQL:

~~~sql
BEGIN;

SELECT nextval('order_number_seq'); -- Ví dụ trả 101.

ROLLBACK;

SELECT nextval('order_number_seq'); -- Có thể trả 102.
~~~

Giá trị sequence đã cấp **không nhất thiết được hoàn lại** khi transaction rollback. Tương tự, identity/auto_increment có thể để lại khoảng trống do:

- Transaction rollback hoặc câu INSERT thất bại sau khi đã cấp ID.
- Giá trị bị bỏ qua bởi constraint/trigger.
- Cache sequence/identity mất một phần khi server restart/failover.
- Các session đồng thời cấp ID.
- Dùng increment khác 1 hoặc cấu hình phân bổ giá trị.
- Xóa bản ghi đã được cấp ID.

**Hệ quả:** Generated ID là **khóa định danh**, không phải bộ đếm nghiệp vụ gapless hoặc số thứ tự xác nhận hoàn thành.

### Không thể suy ra thứ tự commit từ ID

Hai transaction:

~~~text
Tx A: được cấp id=100, chưa commit.
Tx B: được cấp id=101, commit trước.
Tx A: commit sau, hoặc rollback.
~~~

Dù 100 nhỏ hơn 101, không thể nói A đã commit trước B. Nếu nghiệp vụ cần thứ tự hoàn tất, phải có mô hình sự kiện/thứ tự được thiết kế riêng.

### Khi nghiệp vụ đòi số hóa đơn liên tục

Số hóa đơn pháp lý hoặc số chứng từ có thể có yêu cầu quy định riêng, **khác khóa chính kỹ thuật**. Không cố dùng sequence mặc định để hứa “không nhảy số”; hãy thiết kế cơ chế cấp số chuyên biệt với transaction, khóa và chính sách xử lý hủy chứng từ phù hợp quy định.

## 10. `getGeneratedKeys()` và cú pháp trả dữ liệu không giống nhau

| Góc nhìn | JDBC generated keys | Cú pháp SQL returning/output |
| --- | --- | --- |
| Đường lập trình | `prepareStatement(..., RETURN_GENERATED_KEYS)` hoặc tên cột; `getGeneratedKeys()` | SQL có `RETURNING`/`OUTPUT`/`RETURNING INTO` |
| Phạm vi | Driver quyết định những khóa có thể trả | Có thể trả nhiều cột bất kỳ theo khả năng DBMS |
| Tính portable | API JDBC chuẩn, mức hỗ trợ tùy driver | SQL dialect cụ thể |
| Khi cần server default timestamp | Có thể cần yêu cầu thêm cột, không luôn portable | Dễ biểu diễn với DBMS có `RETURNING id, created_at` |
| Multi-row | Cần kiểm thử số lượng/thứ tự keys | Thường biểu diễn rõ nhiều hàng, nhưng có giới hạn/thứ tự riêng |
| Ảnh hưởng trigger | Kết quả do driver/DBMS quyết định | Có thời điểm quan sát/giới hạn riêng theo DBMS |
| Cách đọc | `getGeneratedKeys()` trả `ResultSet` | `executeQuery()`/`execute()` hoặc output parameter tùy DBMS |

**Chiến lược chọn API:**

1. Nếu chỉ cần **một ID** và driver hỗ trợ, thử `getGeneratedKeys()` trước.
2. Nếu cần **nhiều giá trị từ hàng đã ghi**, cân nhắc SQL returning/output đúng dialect.
3. Nếu cần ID **trước khi INSERT**, có thể dùng sequence tường minh tại hệ hỗ trợ hoặc khóa do ứng dụng sinh.
4. Nếu phải hỗ trợ nhiều DBMS, đặt sự khác biệt trong một tầng adapter/repository cụ thể, **không rải SQL riêng cho từng vendor khắp service**.

## 11. Ghi bản ghi cha rồi dùng generated key cho bản ghi con

Ví dụ nghiệp vụ: tạo `orders`, sau đó tạo một `order_items` tham chiếu đến ID đơn vừa sinh.

~~~sql
-- Ví dụ cấu trúc logic, DDL chi tiết tùy DBMS.
CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    quantity INT NOT NULL
);
~~~

Nếu DBMS đã có ID tự sinh cho `orders`, flow hợp lý:

~~~mermaid
flowchart TD
    A["Lấy một Connection từ DataSource"] --> B["autoCommit=false"]
    B --> C["INSERT orders"]
    C --> D["Đọc generated id trên cùng Connection"]
    D --> E["INSERT order_items với order_id vừa nhận"]
    E --> F{"Mọi lệnh thành công?"}
    F -- "Có" --> G["COMMIT"]
    F -- "Không" --> H["ROLLBACK"]
    G --> I["Trả ID sau khi commit thành công"]
    H --> J["Báo lỗi, không công bố đơn"]
~~~

Mã JDBC ví dụ:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class OrderService {
    private final DataSource dataSource;

    public OrderService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long createOrderWithItem(
            String externalRef, long totalCents,
            String productCode, int quantity
    ) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity phải dương"
            );
        }

        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);

            try {
                long orderId =
                    insertOrder(conn, externalRef, totalCents);

                String itemSql = """
                    INSERT INTO order_items (
                        order_id, product_code, quantity
                    ) VALUES (?, ?, ?)
                    """;

                try (PreparedStatement ps =
                         conn.prepareStatement(itemSql)) {
                    ps.setLong(1, orderId);
                    ps.setString(2, productCode);
                    ps.setInt(3, quantity);

                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                            "Không thêm được order item"
                        );
                    }
                }

                conn.commit();
                return orderId;

            } catch (SQLException | RuntimeException failure) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }

    private static long insertOrder(
            Connection conn, String ref, long cents
    ) throws SQLException {
        String sql = """
            INSERT INTO orders (external_ref, total_cents)
            VALUES (?, ?)
            """;

        try (PreparedStatement ps = conn.prepareStatement(
                sql, new String[] {"id"})) {
            ps.setString(1, ref);
            ps.setLong(2, cents);

            if (ps.executeUpdate() != 1) {
                throw new SQLException(
                    "INSERT orders không thành công"
                );
            }

            try (var rs = ps.getGeneratedKeys()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "Không lấy được order ID"
                    );
                }

                long id = rs.getLong(1);
                if (rs.wasNull()) {
                    throw new SQLException("Order ID là NULL");
                }
                return id;
            }
        }
    }
}
~~~

**Phạm vi mã:** ví dụ giả định lược đồ của cả `orders` và `order_items` đã có khóa/constraint phù hợp, và `order_items.id` cũng có cơ chế tự sinh trong DBMS mục tiêu (hoặc được xử lý bởi schema), vì SQL chèn item không đưa `id` vào.

Với code production, thêm khóa ngoại `order_items.order_id → orders.id`, giới hạn input, unique/idempotency key và cách quản lý trạng thái `autoCommit`/rollback/connection pool phù hợp.

**Điều cần nhớ:**

- Lấy ID và INSERT item trên **cùng transaction/connection**.
- `getGeneratedKeys()` được đọc ngay sau INSERT tạo order, trước khi statement đóng.
- Có ID trong Java **chưa có nghĩa transaction đã commit**.
- Sau khi đã commit, mới công bố kết quả thành công.
- Nếu `commit()` ném `SQLException` do mất kết nối, **không luôn biết server đã commit hay chưa**. Không retry mù.

### Đừng trộn cách lấy khóa với cách quản lý transaction

Nếu ứng dụng dùng Spring `@Transactional`, repository phải dùng connection do transaction manager quản lý (ví dụ `JdbcTemplate` hoặc `DataSourceUtils`). Tự mượn connection mới từ DataSource bên trong service transactional có thể khiến INSERT con/cha chạy ở transaction khác.

## 12. Chèn nhiều hàng và JDBC batch: không “zip” keys theo vị trí

Tình huống:

~~~java
try (PreparedStatement ps = conn.prepareStatement(
        """
        INSERT INTO orders (external_ref, total_cents)
        VALUES (?, ?)
        """,
        Statement.RETURN_GENERATED_KEYS)) {

    for (OrderInput order : ordersToCreate) {
        ps.setString(1, order.externalRef());
        ps.setLong(2, order.totalCents());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
    // Không tự giả định getGeneratedKeys trả đúng N hàng
    // tương ứng 1-1 với thứ tự addBatch trên mọi driver.
}
~~~

`OrderInput` và `ordersToCreate` là kiểu/dữ liệu nghiệp vụ minh họa. Code này chỉ thể hiện **điểm rủi ro**, chưa phải một hàm xử lý batch đầy đủ.

Những điều thay đổi theo driver/DBMS:

- `getGeneratedKeys()` có thể trả một, nhiều hoặc không đủ keys cho một batch cụ thể.
- Với batch được driver rewrite thành multi-row INSERT, cấu trúc và thứ tự kết quả có thể khác.
- `executeBatch()` trả update counts; `Statement.SUCCESS_NO_INFO` báo thành công nhưng không biết số hàng ảnh hưởng, và `EXECUTE_FAILED` có thể xuất hiện trong một số chế độ.
- Nếu một lệnh lỗi, driver có thể dừng hoặc tiếp tục một số phần của batch; `BatchUpdateException.getUpdateCounts()` không có nghĩa những lệnh trước đó đã commit.
- Trigger, upsert hoặc default expression có thể ảnh hưởng đến những giá trị mà bạn thực sự cần.

**Không tự viết `generatedIds[i]` tương ứng `inputs[i]` nếu chưa có cam kết đúng từ driver và test thực tế.**

### 12.1. Một cách xác định mapping chắc hơn: khóa tương quan

Nếu mỗi input có `client_ref` duy nhất, PostgreSQL có thể trả cả nó và ID:

~~~sql
INSERT INTO orders (external_ref, total_cents)
VALUES (?, ?), (?, ?), (?, ?)
RETURNING external_ref, id;
~~~

Java tạo map theo `external_ref`, **không phụ thuộc vào thứ tự các hàng trả về**:

~~~java
import java.util.HashMap;
import java.util.Map;

Map<String, Long> idsByRef = new HashMap<>();

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    // Bind đủ tham số cho từng input.
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            String ref = rs.getString("external_ref");
            long id = rs.getLong("id");

            if (idsByRef.putIfAbsent(ref, id) != null) {
                throw new SQLException(
                    "Trùng external_ref trong kết quả"
                );
            }
        }
    }
}

// Sau đó so khớp keys của mọi input với idsByRef.
~~~

Đây là **mẫu cấu trúc**: cần định nghĩa biến `sql` và thực hiện parameter binding thực tế. Dữ liệu đầu vào phải có `external_ref` duy nhất; lệnh PostgreSQL returning chỉ trả những hàng thực sự được INSERT/UPDATE theo SQL. Nếu dùng `ON CONFLICT DO NOTHING`, những input bị bỏ qua có thể **không có hàng trả về**.

### 12.2. Khi không thể dựa vào batch generated keys

Có các lựa chọn:

1. INSERT từng hàng trong cùng transaction và đọc khóa ngay sau mỗi lệnh. Đổi lấy thêm round-trip nhưng dễ map chính xác.
2. Dùng SQL returning/output **trả cả khóa tương quan** theo khả năng DBMS.
3. Sinh ID ở ứng dụng hoặc lấy từ sequence trước khi batch, rồi tự bind ID cho từng hàng (nếu kiến trúc/DBMS cho phép).
4. Load vào staging table có khóa tương quan, sau đó chuyển vào bảng chính bằng cơ chế DBMS phù hợp.

Chọn giải pháp dựa trên **độ tin cậy cần thiết và benchmark**, không chỉ dựa trên số câu SQL ít nhất.

## 13. `INSERT ... RETURNING` không tự giải quyết mọi trường hợp upsert

Một số DBMS cho phép INSERT có nhánh update khi gặp xung đột:

~~~sql
-- PostgreSQL:
INSERT INTO orders (external_ref, total_cents)
VALUES (?, ?)
ON CONFLICT (external_ref)
DO UPDATE SET total_cents = EXCLUDED.total_cents
RETURNING id, external_ref;
~~~

Kết quả có thể là **ID của bản ghi đã tồn tại** được cập nhật, không phải ID mới được cấp. Vì vậy:

- Đừng suy ra một ID được trả nghĩa là “đã tạo bản ghi mới”.
- `ON CONFLICT DO NOTHING RETURNING ...` có thể trả **không hàng** khi xung đột.
- Nếu nghiệp vụ cần phân biệt CREATED và UPDATED, phải có quy tắc/cột trạng thái/cú pháp có thể kiểm chứng trên DBMS mục tiêu.
- Với MySQL `ON DUPLICATE KEY UPDATE`, update count và identity semantics phải được test riêng; không copy cách diễn giải PostgreSQL.
- Không dùng lỗi unique constraint để retry INSERT vô hạn mà không kiểm tra xem bản ghi đã được tạo bởi yêu cầu trước hay chưa.

Khi dùng upsert trong môi trường nhiều tenant, khóa unique và predicate cần bảo đảm **không ghi đè dữ liệu tenant khác**. Generated ID là kết quả kỹ thuật, không phải cơ chế phân quyền.

## 14. Lỗi transaction, rollback và kết quả commit chưa rõ

Giả sử code:

1. INSERT order, nhận generated ID 501.
2. INSERT item thành công.
3. Gọi `commit()`.
4. Mất kết nối và nhận `SQLException`.

Có hai khả năng đáng chú ý:

- DBMS chưa commit, transaction bị rollback.
- DBMS **đã commit**, nhưng phản hồi commit không tới Java.

Chỉ từ việc `commit()` ném lỗi mạng, ứng dụng **không thể luôn xác định** trường hợp nào đã xảy ra.

Nếu retry mà không có idempotency, có thể tạo **hai đơn hàng** với hai generated IDs khác nhau.

### Dùng idempotency key / external reference

Trong ví dụ, cột:

~~~sql
external_ref VARCHAR(80) NOT NULL UNIQUE
~~~

có thể giữ định danh yêu cầu đã được server kiểm chứng. Khi một lần ghi gặp kết quả commit không xác định:

1. Không coi lỗi là chứng minh rollback thành công.
2. Dùng connection **mới, lành mạnh** truy vấn theo `external_ref` và tenant nếu có.
3. Nếu bản ghi tồn tại và dữ liệu/hậu điều kiện đúng, phản hồi theo chính sách đã thiết kế.
4. Nếu không tồn tại, đánh giá có thể retry trong transaction mới hay không.
5. Nếu trạng thái vẫn không chắc hoặc có thao tác ngoài DB, đưa vào quy trình đối soát.

**Không dựa vào `getGeneratedKeys()` để xác nhận commit.** ID có thể đã được cấp cho transaction cuối cùng rollback. Tương tự, khoảng trống sequence không chứng minh một đơn hàng đã bị xóa hoặc thất lạc.

## 15. DatabaseMetaData giúp được gì khi hỗ trợ nhiều DBMS?

`DatabaseMetaData` cung cấp thông tin chung về DBMS, driver và khả năng JDBC:

~~~java
import java.sql.DatabaseMetaData;

DatabaseMetaData meta = conn.getMetaData();

System.out.println("Product: "
    + meta.getDatabaseProductName());
System.out.println("Version: "
    + meta.getDatabaseProductVersion());
System.out.println("Driver: "
    + meta.getDriverName());
System.out.println("Driver version: "
    + meta.getDriverVersion());
System.out.println("getGeneratedKeys: "
    + meta.supportsGetGeneratedKeys());
~~~

Nhưng metadata không đưa ra một API chung kiểu:

~~~text
giveMePortableReturningClauseForAllDatabases()
~~~

Những khác biệt `RETURNING`, `OUTPUT INSERTED`, `RETURNING INTO`, sequence và kiểu cột vẫn phải được giải quyết bởi **dialect/adapter** và test tích hợp.

### Tránh nhận diện DBMS bằng chuỗi ở mọi chỗ

Cách dễ bảo trì hơn là định nghĩa một abstraction nhỏ:

~~~java
interface OrderInsertStrategy {
    long insertOrder(
        java.sql.Connection conn,
        String externalRef,
        long totalCents
    ) throws java.sql.SQLException;
}
~~~

Các triển khai có thể là:

- `JdbcGeneratedKeysOrderInsertStrategy` dùng `getGeneratedKeys()` khi đã được chứng minh.
- `PostgresReturningOrderInsertStrategy` dùng `INSERT ... RETURNING id`.
- `SqlServerOutputOrderInsertStrategy` dùng `OUTPUT INSERTED.id`.
- `OracleReturningOrderInsertStrategy` dùng cơ chế Oracle driver hỗ trợ.

Chọn implementation theo **cấu hình deployment đã xác thực** và một bộ integration test, không dựa vào lời đoán từ tên driver ở từng request. Không cần xây một framework SQL dialect phức tạp nếu sản phẩm chỉ hỗ trợ một DBMS.

## 16. Kịch bản kiểm thử đa driver cho generated keys

Muốn khẳng định một đoạn code hoạt động trên PostgreSQL, MySQL, SQL Server hoặc Oracle, cần chạy **trên từng hệ quản trị thực tế đã cam kết hỗ trợ**. Một DB nhúng như H2 có thể giúp thử API, nhưng không thay thế cơ chế sequence và driver của DBMS mục tiêu.

### Ma trận tối thiểu

| Phép thử | Hậu điều kiện cần kiểm tra |
| --- | --- |
| INSERT một hàng | Nhận đúng ID, hàng tồn tại với external_ref mong đợi |
| INSERT hai hàng | Hai ID phân biệt; không suy luận ID liên tiếp |
| INSERT trong transaction rồi rollback | Hàng không tồn tại sau rollback; không kiểm yêu cầu ID không có gap |
| INSERT rồi chèn bản ghi con | Foreign key tham chiếu đúng hàng cha khi commit |
| Unique constraint failure | Không coi lỗi là ID hợp lệ; transaction được cleanup |
| Generated key với explicit column names | Driver trả đúng cột/kiểu; xử lý khi không hỗ trợ |
| Multi-row INSERT | Số hàng/keys và mapping được kiểm tra độc lập thứ tự |
| JDBC batch | Update counts, keys, rollback sau lỗi và driver rewrite |
| Trigger | Có lấy nhầm ID của bảng trigger ghi không? |
| Upsert | Phân biệt đã tạo/đã cập nhật, ID là của hàng nào |
| Connection pool | Hàm session-scoped không chạy trên connection khác |
| Crash/lỗi commit | Idempotency key, đối soát và retry an toàn |
| Unicode và kiểu khóa | Không cắt/tràn giá trị khi chuyển `NUMBER`/`BIGINT`/UUID |

### Ví dụ test hợp đồng một hàng

Mã JUnit 5 sau giả định bảng test `orders` đã được tạo bằng **DDL đúng DBMS mục tiêu** và có `external_ref` unique:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.UUID;

class GeneratedKeyContractTest {
    private final DataSource dataSource;

    GeneratedKeyContractTest(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Test
    void generatedKeyReferencesExactlyInsertedRow()
            throws Exception {

        String ref = "test-" + UUID.randomUUID();

        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);

            try {
                long id = insertOrder(conn, ref, 500L);

                try (PreparedStatement ps =
                         conn.prepareStatement(
                    """
                    SELECT external_ref, total_cents
                    FROM orders
                    WHERE id = ?
                    """)) {

                    ps.setLong(1, id);

                    try (ResultSet rs = ps.executeQuery()) {
                        assertTrue(rs.next());
                        assertEquals(ref,
                            rs.getString("external_ref"));
                        assertEquals(500L,
                            rs.getLong("total_cents"));
                        assertFalse(rs.next());
                    }
                }
            } finally {
                conn.rollback(); // Dọn fixture test.
            }
        }
    }
}
~~~

Trong snippet test, `insertOrder(conn, ...)` là helper JDBC đã giới thiệu ở phần 3, có thể đặt vào một class utility và import vào test. Test này dùng constructor nhận DataSource nên cần được test framework cấu hình/inject theo cách phù hợp; **không phải một file JUnit độc lập đã đầy đủ wiring**.

**Vì sao `rollback()` trong test?** Để test không lưu bản ghi fixture khi kết thúc. Nó **không làm ID được tái sử dụng**. Không assert rằng lần INSERT sau nhận ID liền kề, vì sequence/identity có thể đã tăng.

### Những điều cần quan sát thêm

1. Dùng `DatabaseMetaData.supportsGetGeneratedKeys()` để ghi nhận khả năng driver, nhưng vẫn chạy test thực tế.
2. Nếu driver ném `SQLFeatureNotSupportedException` cho overload yêu cầu cột, ghi nhận và chuyển sang một strategy đã kiểm chứng.
3. Kiểm tra `ResultSetMetaData` của `getGeneratedKeys()` khi kết quả khác dự đoán; không đoán mọi driver đều trả cùng tên cột.
4. Nếu dùng DML `RETURNING`/`OUTPUT`, test bằng **chính câu SQL production**, không thay bằng cú pháp khác trên H2.
5. Với batch và trigger, kiểm tra kết quả gắn với **external_ref** hoặc khóa tương quan, không chỉ đếm số keys.
6. Test cả đường rollback và tình huống commit không rõ kết quả bằng cơ chế lỗi được kiểm soát trong môi trường thử nghiệm.
7. Dùng DBMS/runtime role/version gần production, không chỉ chạy với superuser hoặc schema khác.

## 17. Hiệu năng và giới hạn khi chọn giải pháp

Một số lựa chọn có thể cùng cho ID đúng nhưng khác chi phí:

| Giải pháp | Lợi điểm | Đánh đổi |
| --- | --- | --- |
| `getGeneratedKeys()` cho INSERT một hàng | API JDBC chung, thường dễ dùng | Driver support và metadata khác nhau |
| PostgreSQL `RETURNING` | Trả nhiều cột trong cùng DML | Phụ thuộc PostgreSQL dialect |
| MySQL `LAST_INSERT_ID()` | Hàm session-scoped hữu ích khi cần | Thường thêm round-trip; dễ sai nếu đổi connection |
| SQL Server `OUTPUT INSERTED` | Có thể trả nhiều cột/hàng | Cần xét trigger và result set semantics |
| Oracle `RETURNING INTO` | Có thể lấy output từ DML | Cần output binding theo driver |
| Sequence preallocation | Biết ID trước khi INSERT; hỗ trợ liên kết batch | Thêm bước cấp ID, có thể tạo gap |
| Application-generated UUID | Không phải chờ DB cấp khóa | Index/storage/order/format và phân phối ID cần thiết kế |

### Không tối ưu bằng giả định sai

Ví dụ, giả định “một lệnh batch 500 hàng luôn trả generated keys cùng thứ tự” có thể tiết kiệm round-trip, nhưng nếu sai sẽ tạo liên kết dữ liệu hỏng âm thầm. Hãy benchmark sau khi có **kiểm thử mapping chính xác**.

Nếu rất nhiều bản ghi cần chèn nhanh, cân nhắc:

- Multi-row INSERT có returning kèm khóa tương quan.
- Staging table và dữ liệu nhập theo chunk.
- Sequence allocation có kiểm soát ở DBMS hỗ trợ.
- Batching với transaction và chiến lược đọc khóa đã được kiểm chứng.
- Application-assigned IDs nếu yêu cầu cross-DBMS thực sự phù hợp.

Đừng thiết kế thiếu transaction chỉ để giữ ID tăng đẹp; sequence gap và commit-order là đặc điểm cần chấp nhận hoặc tách ra khỏi khóa kỹ thuật.

## 18. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| JDBC có `RETURN_GENERATED_KEYS` nên mọi driver trả cùng format | API chung, driver implementation khác | Kiểm thử driver và overload |
| `getGeneratedKeys()` trả ID là transaction đã commit | ID có thể cấp trước commit | Chỉ công bố thành công sau transaction |
| `SELECT MAX(id)` tìm đúng ID vừa chèn | Transaction khác có thể chèn ID lớn hơn | `getGeneratedKeys()`/`RETURNING`/session mechanism |
| `LAST_INSERT_ID()` dùng được sau khi lấy connection mới | Session-specific | Cùng connection với INSERT |
| `@@IDENTITY` luôn là ID hàng chính SQL Server | Trigger có thể tạo identity khác | `OUTPUT INSERTED` hoặc phương thức scope đúng |
| `SCOPE_IDENTITY()` dùng ở bất cứ SQL statement nào cùng connection | Scope có giới hạn rõ | Ưu tiên `OUTPUT` hoặc generated keys |
| Oracle `RETURNING INTO` hoạt động như PostgreSQL `RETURNING` | Oracle yêu cầu output binding riêng | Theo Oracle driver |
| SQLite bắt buộc có `AUTOINCREMENT` mới sinh ID | `INTEGER PRIMARY KEY` thường đã đủ | Chọn AUTOINCREMENT khi cần semantics riêng |
| Sequence rollback trả lại số vừa cấp | Sequence thường không transactional | Chấp nhận gap |
| ID tăng theo thứ tự commit | Transaction có thể commit ngược thứ tự cấp ID | Không dùng ID làm commit timestamp |
| Batch keys luôn map theo `addBatch()` | Driver có thể rewrite/return khác thứ tự | Dùng khóa tương quan hoặc INSERT từng hàng |
| `SUCCESS_NO_INFO` là thất bại | Là thành công nhưng không có count | Xử lý theo hợp đồng batch |
| Upsert trả khóa nghĩa vừa tạo bản ghi | Có thể là bản ghi được update | Phân biệt created/updated riêng |
| Một test H2 đủ cho PostgreSQL/Oracle | Engine/driver/dialect khác | Test trên DBMS mục tiêu |
| ID khó đoán đã là phân quyền | Có thể vẫn truy cập hàng ngoài tenant | Scope/authorization trong SQL |
| Retry INSERT sau lỗi commit luôn an toàn | Commit có thể đã thành công | Idempotency key và đối soát |

## 19. Tình huống tự kiểm tra

**Tình huống A.** Một `INSERT` PostgreSQL đã gọi `getGeneratedKeys()` và nhận `id=2001`; ngay sau đó transaction rollback. Có thể xem đơn `2001` tồn tại và sequence phải cấp lại `2001` không?

**Đáp án:** Không. ID có thể đã được cấp nhưng bản ghi không tồn tại sau rollback. Sequence thường không rollback giá trị đã cấp; lần sau có thể cấp một ID khác.

**Tình huống B.** Hai request đồng thời INSERT order. Request A gọi `SELECT MAX(id)` để tìm ID mới. Cách này đúng không?

**Đáp án:** Không. `MAX(id)` có thể trả khóa của request khác. Dùng generated keys, returning hoặc API đúng session.

**Tình huống C.** MySQL `LAST_INSERT_ID()` chạy trên một connection mới lấy từ pool. Có thể lấy đúng ID của INSERT trước không?

**Đáp án:** Không có bảo đảm. Hàm gắn với session hiện tại, nên phải dùng cùng connection thực hiện INSERT.

**Tình huống D.** SQL Server có trigger INSERT một hàng vào bảng audit cũng dùng IDENTITY. Có nên lấy `@@IDENTITY` để xác định ID của order không?

**Đáp án:** Không. Nó có thể phản ánh ID do trigger sinh. Ưu tiên `OUTPUT INSERTED.id` hoặc cơ chế generated keys đã kiểm thử.

**Tình huống E.** Oracle dùng `RETURNING id INTO :id`. Có thể paste SQL này vào `PreparedStatement.executeQuery()` rồi đọc `ResultSet` như PostgreSQL không?

**Đáp án:** Không được giả định. Oracle dùng cơ chế bind output phù hợp JDBC driver; phải đăng ký/đọc out parameter theo tài liệu Oracle.

**Tình huống F.** SQLite `id INTEGER PRIMARY KEY` không có `AUTOINCREMENT`. SQLite có thể tự tạo rowid khi INSERT thiếu ID không?

**Đáp án:** Có, với bảng rowid và kiểu khai báo phù hợp. `AUTOINCREMENT` có semantics khác về tái sử dụng ID và thêm chi phí, không bắt buộc cho việc sinh ID đơn giản.

**Tình huống G.** `getGeneratedKeys()` của một JDBC batch trả 10 ID cho 10 input. Có thể ghép theo thứ tự index ngay không?

**Đáp án:** Chỉ khi driver/loại SQL/phiên bản mục tiêu **bảo đảm và đã được test**. Nếu không, dùng khóa tương quan hoặc chèn từng hàng để mapping chính xác.

**Tình huống H.** PostgreSQL `INSERT ... ON CONFLICT DO NOTHING RETURNING id` không trả hàng. Điều đó có nghĩa driver hỏng không?

**Đáp án:** Không. Có thể INSERT đã bị bỏ qua vì xung đột; returning chỉ có hàng thực sự được thao tác theo semantics câu SQL.

**Tình huống I.** Cần biết ID của order để tạo item rồi commit cả hai. Có cần tạo connection riêng cho INSERT item không?

**Đáp án:** Không. Nên dùng **cùng connection và transaction** để order/item cùng commit hoặc rollback.

**Tình huống J.** `commit()` ném lỗi mạng, nhưng trước đó ứng dụng nhận generated ID. Có nên tạo lại order với external_ref mới ngay lập tức?

**Đáp án:** Không. Không rõ DBMS đã commit hay chưa. Dùng external_ref/idempotency key ổn định và đối soát trên connection mới trước khi retry.

**Tình huống K.** Một bảng có sequence với increment lớn hơn 1. Có thể dự đoán tất cả ID sau multi-row INSERT bằng cách tăng 1 không?

**Đáp án:** Không. Increment và allocation phụ thuộc cấu hình; concurrent sessions, cache và driver còn tạo khác biệt.

**Tình huống L.** Một ứng dụng phải hỗ trợ PostgreSQL, SQL Server và Oracle; mỗi nơi có cú pháp khác nhau. Cách tổ chức code nào dễ bảo trì hơn?

**Đáp án:** Đặt hành vi đặc thù trong adapter/strategy theo DBMS, thống nhất contract nghiệp vụ và chạy integration test trên từng engine/driver được hỗ trợ; không rải chuỗi SQL dialect khắp controller.

## Ghi nhớ

- **JDBC `getGeneratedKeys()` là API chung**, nhưng không bảo đảm mọi DBMS/driver trả cùng cấu trúc, tên cột hoặc số khóa cho batch.
- **IDENTITY/AUTO_INCREMENT và SEQUENCE có khác biệt** về cách cấu hình, lấy giá trị, explicit insert và tính chất transaction.
- **PostgreSQL dùng `RETURNING`; SQL Server dùng `OUTPUT INSERTED`; Oracle dùng `RETURNING ... INTO`; SQLite hiện đại cũng có `RETURNING`; MySQL phổ biến với `getGeneratedKeys()`/`LAST_INSERT_ID()`.** Không sao chép mù cú pháp giữa các DBMS.
- **Không dùng `MAX(id)` để đoán ID vừa chèn**, không dùng hàm session trên connection khác, và không lấy khóa sinh làm bằng chứng commit.
- **Sequence/identity thường có khoảng trống** do rollback, lỗi, concurrency và cache; ID không thể hiện thứ tự commit hoặc số thứ tự nghiệp vụ gapless.
- **Với nhiều hàng/batch, cần mapping khóa theo hợp đồng driver** hoặc dùng một khóa tương quan; không mặc định thứ tự `getGeneratedKeys()` bằng thứ tự input.
- **Gắn tạo cha/con vào cùng transaction**, có idempotency key và đối soát sau lỗi commit chưa rõ; kiểm thử trên từng DBMS/driver thực tế.
