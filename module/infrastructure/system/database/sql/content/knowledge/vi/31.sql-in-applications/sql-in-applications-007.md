# Lấy khóa sinh tự động và số hàng ảnh hưởng trong SQL

> **Module:** Database SQL  
> **Chương:** SQL trong ứng dụng  
> **Bài học:** Lấy khóa sinh tự động và số hàng ảnh hưởng

Khi một ứng dụng INSERT đơn hàng mới, cơ sở dữ liệu có thể tự cấp khóa chính. Ứng dụng thường cần lấy khóa đó để INSERT các dòng chi tiết, ghi audit hoặc trả ID cho API. Sau đó, khi chạy UPDATE hoặc DELETE, ứng dụng cần biết **bao nhiêu hàng đã được xử lý** để quyết định nghiệp vụ có thành công hay không.

Hai việc tưởng đơn giản này có nhiều khác biệt giữa các hệ quản trị và driver:

- Khóa sinh tự động có thể đến từ **IDENTITY, AUTO_INCREMENT, sequence, ROWID hoặc UUID**.
- Câu SQL có thể dùng **RETURNING, OUTPUT, getGeneratedKeys(), currval(), LAST_INSERT_ID() hoặc SCOPE_IDENTITY()** tùy DBMS.
- Một lệnh UPDATE có thể báo số hàng **khớp điều kiện**, số hàng **thực sự thay đổi**, số hàng được trigger xử lý hoặc số hàng do driver nhận từ giao thức.
- Batch INSERT có thể sinh nhiều khóa nhưng không phải driver nào cũng trả chúng theo cùng cách.
- Trigger, upsert, cascade, view, transaction rollback và connection pooling đều ảnh hưởng cách lấy kết quả.

Bài học này xây dựng cách làm cho **PostgreSQL, MySQL, SQL Server, Oracle Database và SQLite**, cùng Java/JDBC. Mục tiêu là lấy đúng khóa của đúng hàng, diễn giải đúng số hàng ảnh hưởng và bảo đảm transaction không để lại dữ liệu mồ côi.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khóa sinh tự động và phân biệt khóa thay thế (surrogate key) với khóa nghiệp vụ.
2. Phân biệt IDENTITY, AUTO_INCREMENT, sequence, ROWID và UUID.
3. Tạo bảng có khóa tự sinh trên năm hệ quản trị SQL phổ biến.
4. Lấy khóa vừa INSERT bằng RETURNING, OUTPUT, JDBC generated keys và hàm session/connection-specific.
5. Giải thích vì sao không dùng MAX(id) để lấy ID của bản ghi vừa chèn.
6. Hiểu phạm vi của LAST_INSERT_ID, SCOPE_IDENTITY, currval và last_insert_rowid.
7. Xử lý INSERT nhiều hàng, JDBC batch và generated keys mà không giả định thứ tự trả về.
8. Phân biệt số hàng khớp (matched), số hàng thay đổi (changed) và số hàng bị tác động theo báo cáo DBMS/driver.
9. Hiểu tác động của UPDATE đặt giá trị bằng giá trị cũ, DELETE 0 hàng và UPSERT.
10. Đọc kết quả executeUpdate(), executeLargeUpdate(), executeBatch() và getGeneratedKeys().
11. Dùng row count cho optimistic locking và kiểm tra cập nhật/xóa đúng bản ghi.
12. Hiểu ảnh hưởng của trigger, view, cascade, stored procedure và SET NOCOUNT.
13. Biết khóa sequence/identity có thể bị khuyết và không bảo đảm liên tục.
14. Xử lý generated key khi transaction rollback, retry, timeout và connection pooling.
15. Phân biệt khóa do DB sinh với UUID do ứng dụng sinh.
16. Thiết kế transaction INSERT cha–con an toàn.
17. Viết code JDBC có bind đúng kiểu, đọc khóa, kiểm tra row count và rollback đúng.
18. Xây dựng kiểm thử cho từng DBMS/driver/version thay vì dựa vào hành vi tình cờ.

## 2. Khóa sinh tự động và khóa nghiệp vụ

Một bảng đơn hàng có thể dùng:

~~~sql
CREATE TABLE don_hang (
    id BIGINT PRIMARY KEY,
    ma_don VARCHAR(40) NOT NULL UNIQUE,
    customer_id VARCHAR(40) NOT NULL,
    tong_tien DECIMAL(14,2) NOT NULL
);
~~~

Hai khóa mang hai ý nghĩa:

- **id:** định danh nội bộ, có thể được database sinh tự động. Đây thường là surrogate key.
- **ma_don:** mã nghiệp vụ, có thể mang quy tắc như tiền tố, ngày, tenant hoặc mã đối tác.

Không nên mặc định ID tự sinh là mã đơn hàng hiển thị cho người dùng. Khóa số tăng dần dễ đoán, có thể làm lộ số lượng bản ghi và không thích hợp làm bí mật hoặc authorization token.

### 2.1. Vì sao cần surrogate key?

- Khóa nghiệp vụ có thể thay đổi.
- Mã nghiệp vụ có thể dài, chứa Unicode hoặc nhiều cột.
- Khóa số thường gọn cho foreign key và index.
- Có thể tạo bản ghi trước khi mọi thông tin nghiệp vụ hoàn tất.

Tuy nhiên, surrogate key không thay thế UNIQUE constraint cho khóa nghiệp vụ. Nếu ma_don phải duy nhất, hãy đặt UNIQUE; đừng chỉ kiểm tra trong ứng dụng.

### 2.2. Tự sinh khóa không đồng nghĩa liên tục

Giả sử ID lần lượt là 100, 101, 102. Sau đó transaction tạo ID 103 nhưng rollback. ID tiếp theo có thể là 104, để lại khoảng trống.

Khoảng trống có thể xuất hiện do:
- Transaction rollback.
- INSERT lỗi hoặc conflict.
- Sequence cache/preallocation.
- Server restart.
- Batch thất bại giữa chừng.
- Identity/auto increment cấp số trước khi biết transaction commit.

**Không dùng IDENTITY/AUTO_INCREMENT/sequence làm số hóa đơn liên tục theo pháp lý** nếu yêu cầu nghiệp vụ bắt buộc không có khoảng trống. Đánh số chứng từ liên tục cần cơ chế riêng với khóa/transaction và quy định audit phù hợp.

## 3. Các chiến lược sinh khóa

| Cơ chế | Ý tưởng | Hệ thường gặp |
|---|---|---|
| Identity column | DB tự cấp số khi INSERT | SQL Server, PostgreSQL, Oracle, MySQL với cú pháp tương ứng |
| AUTO_INCREMENT | Cột số tăng tự động | MySQL |
| Sequence | Đối tượng sinh số độc lập | PostgreSQL, Oracle, SQL Server và DBMS khác |
| INTEGER PRIMARY KEY | Rowid alias trong SQLite | SQLite |
| UUID/GUID | Sinh định danh 128-bit | Nhiều hệ và ứng dụng |
| Application-generated ID | Ứng dụng tạo ID trước INSERT | UUID/ULID/Snowflake và thuật toán khác |

Mỗi cơ chế có trade-off về:
- Khả năng sinh ID trước INSERT.
- Hiệu năng concurrency.
- Kích thước index.
- Tính phân tán.
- Khả năng đoán.
- Khoảng trống.
- Cách lấy giá trị qua JDBC.
- Hành vi khi rollback.

### 3.1. Identity và sequence khác nhau thế nào?

Identity thường là thuộc tính/cơ chế gắn với cột, giúp DB tự sinh giá trị khi INSERT. Sequence là đối tượng có thể được gọi độc lập và có thể dùng cho nhiều cột/bảng, tùy DBMS.

Trong PostgreSQL, identity column được triển khai dựa trên sequence nhưng có quy tắc quản lý quyền/ownership riêng. Oracle có identity columns và sequence độc lập. SQL Server có IDENTITY property và SEQUENCE object. Không nên coi cú pháp của chúng giống nhau.

## 4. PostgreSQL: GENERATED AS IDENTITY và RETURNING

Một bảng PostgreSQL hiện đại:

~~~sql
CREATE TABLE don_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_don VARCHAR(40) NOT NULL UNIQUE,
    customer_id VARCHAR(40) NOT NULL,
    tong_tien NUMERIC(14,2) NOT NULL
);
~~~

**GENERATED ALWAYS AS IDENTITY** yêu cầu giá trị được sinh theo cơ chế identity; việc chủ động chèn giá trị có quy tắc riêng và cần cú pháp OVERRIDING SYSTEM VALUE khi được phép.

Biến thể:

~~~sql
id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
~~~

cho phép ứng dụng cung cấp giá trị tường minh trong trường hợp được phép, nếu không thì DB sinh mặc định.

### 4.1. INSERT ... RETURNING

Cách trực tiếp:

~~~sql
INSERT INTO don_hang (ma_don, customer_id, tong_tien)
VALUES ('ORD-2026-0001', 'C001', 250000)
RETURNING id;
~~~

DB trả khóa của chính hàng được INSERT trong result set của câu lệnh. Đây thường là cách rõ ràng nhất trong PostgreSQL.

Có thể lấy nhiều cột:

~~~sql
INSERT INTO don_hang (ma_don, customer_id, tong_tien)
VALUES ('ORD-2026-0002', 'C002', 180000)
RETURNING id, ma_don, tong_tien;
~~~

Và INSERT nhiều hàng:

~~~sql
INSERT INTO don_hang (ma_don, customer_id, tong_tien)
VALUES
    ('ORD-2026-0003', 'C003', 100000),
    ('ORD-2026-0004', 'C004', 200000)
RETURNING id, ma_don;
~~~

Kết quả chứa một hàng cho mỗi hàng được INSERT thành công trong câu lệnh. Nếu dùng ON CONFLICT DO NOTHING, số hàng RETURNING có thể ít hơn số hàng đề xuất insert.

### 4.2. Sequence functions

Nếu cần gọi sequence riêng:

~~~sql
SELECT nextval('don_hang_id_seq');
~~~

Lấy giá trị hiện tại đã cấp trong session:

~~~sql
SELECT currval('don_hang_id_seq');
~~~

currval chỉ hợp lệ trong session đã gọi nextval cho sequence đó trước đó. Session mới chưa gọi nextval sẽ nhận lỗi.

Có thể dùng:

~~~sql
SELECT lastval();
~~~

để lấy giá trị sequence gần nhất được gọi trong session, nhưng nếu trigger hoặc sequence khác vừa gọi nextval, lastval có thể là sequence khác với sequence ID của INSERT mà bạn quan tâm.

Vì vậy, **RETURNING id** thường an toàn và gắn trực tiếp kết quả với hàng INSERT hơn.

### 4.3. SERIAL cũ và identity

Cú pháp:

~~~sql
id BIGSERIAL PRIMARY KEY
~~~

là cách phổ biến trong PostgreSQL trước khi identity được chuẩn hóa. BIGSERIAL tạo cơ chế sequence/default theo cách PostgreSQL-specific. Không coi SERIAL/BIGSERIAL là kiểu dữ liệu SQL chuẩn có trên mọi DBMS.

Khi tạo schema mới, cân nhắc GENERATED ... AS IDENTITY; khi làm việc với schema cũ, hiểu sequence và default thật sự trước migration.

## 5. MySQL: AUTO_INCREMENT và LAST_INSERT_ID()

Bảng MySQL:

~~~sql
CREATE TABLE don_hang (
    id BIGINT NOT NULL AUTO_INCREMENT,
    ma_don VARCHAR(40) NOT NULL,
    customer_id VARCHAR(40) NOT NULL,
    tong_tien DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_don_hang_ma (ma_don)
) ENGINE=InnoDB;
~~~

INSERT:

~~~sql
INSERT INTO don_hang (ma_don, customer_id, tong_tien)
VALUES ('ORD-2026-0001', 'C001', 250000);
~~~

Lấy ID vừa cấp trong cùng connection:

~~~sql
SELECT LAST_INSERT_ID();
~~~

### 5.1. LAST_INSERT_ID có phạm vi connection

LAST_INSERT_ID() trả giá trị auto-generated ID gần nhất của connection hiện tại theo ngữ nghĩa MySQL. Một connection khác có thể có giá trị khác.

Điều này tránh race condition kiểu session A INSERT, session B INSERT, rồi A SELECT MAX(id). LAST_INSERT_ID không bị session B ghi đè vì nó gắn với connection A.

**Phải chạy SELECT LAST_INSERT_ID() trên đúng connection đã INSERT.** Không trả connection về pool rồi mượn connection khác để lấy ID.

### 5.2. LAST_INSERT_ID với INSERT nhiều hàng

Với một INSERT thêm nhiều hàng có AUTO_INCREMENT, LAST_INSERT_ID thường cho **giá trị auto-increment đầu tiên được tạo** cho statement theo ngữ nghĩa MySQL. Không dùng nó như danh sách tất cả ID được cấp.

Nếu cần từng ID:
- Dùng JDBC generated keys và kiểm thử driver/version.
- Dùng INSERT ... RETURNING nếu phiên bản sản phẩm hỗ trợ.
- Hoặc INSERT từng hàng/đợt theo cơ chế liên kết rõ từng key.
- Tránh suy ra dải ID bằng first_id + row_count nếu không có bảo đảm cấu hình/engine/statement.

### 5.3. INSERT ... ON DUPLICATE KEY UPDATE

Với upsert, hành vi LAST_INSERT_ID có thể cần thiết kế riêng. Một mẫu MySQL thường gặp để trả ID khi update conflict:

~~~sql
INSERT INTO don_hang (ma_don, customer_id, tong_tien)
VALUES ('ORD-2026-0001', 'C001', 250000)
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id),
    tong_tien = VALUES(tong_tien);
~~~

Cú pháp VALUES(col) trong phần ON DUPLICATE KEY UPDATE đã bị deprecated ở một số phiên bản MySQL mới; dùng alias row syntax phù hợp phiên bản khi triển khai. Mẫu trên minh họa kỹ thuật LAST_INSERT_ID(id), không phải template bất biến.

### 5.4. Không dùng LAST_INSERT_ID như biến toàn cục

Giá trị thuộc connection, không phải ID toàn hệ thống. Khi dùng connection pool, luôn thực hiện INSERT và lấy ID trong cùng callback/transaction giữ cùng Connection.

## 6. SQL Server: IDENTITY và OUTPUT INSERTED

Tạo bảng:

~~~sql
CREATE TABLE dbo.don_hang (
    id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ma_don VARCHAR(40) NOT NULL UNIQUE,
    customer_id VARCHAR(40) NOT NULL,
    tong_tien DECIMAL(14,2) NOT NULL
);
~~~

INSERT và lấy ID bằng OUTPUT:

~~~sql
INSERT INTO dbo.don_hang (ma_don, customer_id, tong_tien)
OUTPUT INSERTED.id
VALUES ('ORD-2026-0001', 'C001', 250000);
~~~

Có thể trả nhiều cột:

~~~sql
INSERT INTO dbo.don_hang (ma_don, customer_id, tong_tien)
OUTPUT INSERTED.id, INSERTED.ma_don
VALUES ('ORD-2026-0002', 'C002', 180000);
~~~

OUTPUT có thể trả các hàng được INSERT/UPDATE/DELETE, tùy loại DML và pseudo-table INSERTED/DELETED.

### 6.1. SCOPE_IDENTITY()

Cách khác:

~~~sql
INSERT INTO dbo.don_hang (ma_don, customer_id, tong_tien)
VALUES ('ORD-2026-0003', 'C003', 100000);

SELECT CAST(SCOPE_IDENTITY() AS BIGINT) AS id;
~~~

SCOPE_IDENTITY trả identity value cuối cùng được sinh trong **cùng scope** của session hiện tại. Scope là module/batch/procedure/trigger context theo quy tắc SQL Server.

### 6.2. @@IDENTITY có thể lấy nhầm ID từ trigger

Giả sử INSERT don_hang sinh id=10, trigger sau đó INSERT audit_log và audit_log có identity id=500.

- @@IDENTITY có thể trả 500 vì nó theo session và bị ảnh hưởng bởi identity trong trigger.
- SCOPE_IDENTITY() trả identity được sinh trong scope INSERT hiện tại, không lấy identity từ scope trigger lồng.
- OUTPUT INSERTED.id trả trực tiếp ID hàng được thao tác, thường là cách rõ ràng nhất.

Không dùng @@IDENTITY cho logic ứng dụng thông thường khi có trigger tạo thêm identity.

### 6.3. IDENT_CURRENT

~~~sql
SELECT IDENT_CURRENT('dbo.don_hang');
~~~

IDENT_CURRENT trả identity gần nhất cho một table trên mọi session/scope, không bị giới hạn connection. Nó không an toàn để tìm ID của hàng vừa INSERT trong ứng dụng concurrent, vì session khác có thể đã chèn sau đó.

### 6.4. OUTPUT và trigger trên bảng

SQL Server có hạn chế khi dùng OUTPUT trực tiếp với bảng có trigger tương ứng được bật, tùy dạng OUTPUT và INTO. Ví dụ OUTPUT không có INTO có thể không được phép nếu bảng đích có trigger cho action tương ứng. Khi cần, dùng OUTPUT ... INTO table variable/temp table rồi SELECT từ đó, theo cú pháp và giới hạn cụ thể.

### 6.5. IDENTITY không bảo đảm không có khoảng trống

IDENTITY có thể nhảy số do rollback, lỗi, cache hoặc restart. Không dùng IDENTITY làm bộ đếm chứng từ liên tục.

## 7. Oracle: identity columns và sequences

Oracle hỗ trợ identity columns ở các phiên bản hiện đại:

~~~sql
CREATE TABLE don_hang (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_don VARCHAR2(40) NOT NULL UNIQUE,
    customer_id VARCHAR2(40) NOT NULL,
    tong_tien NUMBER(14,2) NOT NULL
);
~~~

Biến thể GENERATED BY DEFAULT AS IDENTITY cho phép giá trị tường minh trong điều kiện phù hợp. Oracle có thêm lựa chọn như ON NULL tùy cú pháp/version.

### 7.1. INSERT ... RETURNING INTO

Trong PL/SQL:

~~~sql
DECLARE
    v_id NUMBER;
BEGIN
    INSERT INTO don_hang (ma_don, customer_id, tong_tien)
    VALUES ('ORD-2026-0001', 'C001', 250000)
    RETURNING id INTO v_id;

    DBMS_OUTPUT.PUT_LINE('ID=' || v_id);
END;
/
~~~

RETURNING INTO gắn giá trị được tạo với chính hàng DML. Với JDBC, có thể dùng PreparedStatement/Oracle driver với generated keys hoặc RETURNING bind/CallableStatement theo API và phiên bản driver phù hợp.

### 7.2. Sequence độc lập

~~~sql
CREATE SEQUENCE don_hang_seq
START WITH 1
INCREMENT BY 1
CACHE 100;
~~~

Lấy giá trị mới:

~~~sql
SELECT don_hang_seq.NEXTVAL FROM dual;
~~~

Lấy giá trị đã cấp trong session:

~~~sql
SELECT don_hang_seq.CURRVAL FROM dual;
~~~

CURRVAL chỉ hợp lệ sau khi NEXTVAL đã được gọi trong session hiện tại.

INSERT dùng sequence:

~~~sql
INSERT INTO don_hang (id, ma_don, customer_id, tong_tien)
VALUES (
    don_hang_seq.NEXTVAL,
    'ORD-2026-0002',
    'C002',
    180000
);
~~~

Hoặc định nghĩa DEFAULT sequence/identity để ứng dụng không cần biết sequence name.

### 7.3. Trigger sequence cũ

Schema Oracle cũ thường dùng BEFORE INSERT trigger:

~~~sql
:NEW.id := don_hang_seq.NEXTVAL;
~~~

với điều kiện trigger và schema được thiết kế đúng. Khi migrate sang identity column, cần kiểm tra sequence hiện tại, giá trị lớn nhất, insert explicit IDs và trigger cũ để tránh cấp trùng.

## 8. SQLite: INTEGER PRIMARY KEY và last_insert_rowid()

SQLite có cơ chế đặc biệt:

~~~sql
CREATE TABLE don_hang (
    id INTEGER PRIMARY KEY,
    ma_don TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL,
    tong_tien NUMERIC NOT NULL
);
~~~

Trong bảng rowid thông thường, cột có kiểu khai báo đúng **INTEGER PRIMARY KEY** là alias cho ROWID. Nếu không cung cấp ID, SQLite cấp rowid tự động.

### 8.1. AUTOINCREMENT không giống AUTO_INCREMENT MySQL

Có thể khai báo:

~~~sql
id INTEGER PRIMARY KEY AUTOINCREMENT
~~~

Từ khóa AUTOINCREMENT của SQLite ngăn tái sử dụng một số ROWID đã từng được cấp theo quy tắc SQLite, nhưng có thêm chi phí và dùng sqlite_sequence. Nó **không bảo đảm số liên tục không có khoảng trống**.

Thông thường INTEGER PRIMARY KEY không cần AUTOINCREMENT nếu không có yêu cầu đặc biệt về không tái sử dụng ID đã xóa trong vòng đời DB.

### 8.2. last_insert_rowid()

Trên cùng connection:

~~~sql
SELECT last_insert_rowid();
~~~

API C sqlite3_last_insert_rowid() hoặc JDBC driver có thể cung cấp kết quả tương ứng. Phạm vi connection rất quan trọng.

Nếu trigger thực hiện INSERT vào bảng khác, last_insert_rowid có quy tắc riêng trong lúc trigger chạy và sau khi trigger kết thúc. Đừng dựa vào một truy vấn tùy tiện sau nhiều thao tác để lấy nhầm bảng audit; dùng RETURNING khi phiên bản hỗ trợ hoặc JDBC generated keys/kiểm thử driver.

### 8.3. SQLite RETURNING

SQLite hỗ trợ RETURNING từ phiên bản 3.35.0:

~~~sql
INSERT INTO don_hang (ma_don, customer_id, tong_tien)
VALUES ('ORD-2026-0001', 'C001', 250000)
RETURNING id, ma_don;
~~~

RETURNING trả hàng được INSERT/UPDATE/DELETE theo cú pháp hỗ trợ. Phải kiểm tra SQLite library runtime thực tế, không chỉ version của công cụ phát triển hoặc JDBC wrapper.

### 8.4. WITHOUT ROWID

Bảng khai báo WITHOUT ROWID không có rowid ẩn theo mô hình bảng thường; INTEGER PRIMARY KEY không còn là alias rowid. Không dùng last_insert_rowid để lấy khóa của bảng WITHOUT ROWID như bảng rowid thông thường.

## 9. Lấy khóa bằng JDBC: Generated Keys

JDBC cung cấp cách tương đối độc lập DBMS:

~~~java
String sql = """
    INSERT INTO don_hang (ma_don, customer_id, tong_tien)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, "ORD-2026-0001");
    ps.setString(2, "C001");
    ps.setBigDecimal(3, new BigDecimal("250000.00"));

    int affected = ps.executeUpdate();

    if (affected != 1) {
        throw new SQLException("Khong insert duoc mot don hang");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("Driver khong tra generated key");
        }

        long id = keys.getLong(1);
        if (keys.wasNull()) {
            throw new SQLException("Generated key la NULL");
        }

        System.out.println("New order id = " + id);
    }
}
~~~

### 9.1. Yêu cầu generated keys rõ ràng

Không phải mọi JDBC driver đều mặc định trả generated keys. Hãy yêu cầu bằng:
- Statement.RETURN_GENERATED_KEYS.
- Hoặc overload nhận tên/chỉ số cột được sinh nếu driver hỗ trợ.

Ví dụ:

~~~java
connection.prepareStatement(sql, new String[] {"id"});
~~~

Tên cột và hỗ trợ cụ thể phụ thuộc driver/DBMS.

### 9.2. Generated key có thể không phải cột đầu tiên

Một số driver trả ResultSet generated keys với metadata và thứ tự cột riêng. Nếu cần nhiều cột, kiểm tra metadata/tên cột và tài liệu driver. Không mặc định cột 1 luôn là ID BIGINT nếu câu INSERT có nhiều generated columns.

### 9.3. Không được bỏ qua ResultSet

getGeneratedKeys() trả ResultSet cần đóng. Dùng try-with-resources để đóng đúng cách, đặc biệt khi connection pool tái sử dụng connection.

### 9.4. Driver có thể triển khai khác nhau

Generated keys phụ thuộc:
- DBMS và version.
- JDBC driver và version.
- Câu INSERT đơn hay batch.
- Có trigger hay không.
- Cột identity hay sequence/default.
- Có upsert hay không.
- Cách driver rewrite batch.

Một API JDBC chung không xóa hết khác biệt vendor. Phải có integration tests với driver thực tế.

## 10. JDBC dùng RETURNING/OUTPUT theo dialect

JDBC generated keys tiện cho INSERT đơn, nhưng đôi khi ứng dụng cần trả nhiều cột hoặc nhiều hàng. Khi đó SQL dialect có thể dùng trực tiếp:

**PostgreSQL:**

~~~java
String sql = """
    INSERT INTO don_hang (ma_don, customer_id, tong_tien)
    VALUES (?, ?, ?)
    RETURNING id, ma_don
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "ORD-2026-0002");
    ps.setString(2, "C002");
    ps.setBigDecimal(3, new BigDecimal("180000.00"));

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long id = rs.getLong("id");
            String maDon = rs.getString("ma_don");
        }
    }
}
~~~

**SQL Server:**

~~~sql
INSERT INTO dbo.don_hang (ma_don, customer_id, tong_tien)
OUTPUT INSERTED.id, INSERTED.ma_don
VALUES (?, ?, ?);
~~~

**Oracle:** dùng RETURNING INTO qua cơ chế bind phù hợp của Oracle JDBC, hoặc generated keys nếu driver hỗ trợ.

**MySQL:** dùng generated keys hoặc LAST_INSERT_ID trên cùng connection; hỗ trợ RETURNING phụ thuộc phiên bản sản phẩm, không áp dụng cú pháp PostgreSQL mặc định.

**SQLite:** dùng RETURNING nếu SQLite runtime hỗ trợ; nếu không, generated keys/last_insert_rowid cùng connection theo driver.

Một repository đa DBMS nên tách phần SQL này trong adapter/dialect, nhưng trả cùng kiểu domain result.

## 11. Vì sao không dùng SELECT MAX(id)?

Cách sai phổ biến:

~~~sql
INSERT INTO don_hang (...);
SELECT MAX(id) FROM don_hang;
~~~

Giả sử:
- Session A INSERT và được ID 100.
- Trước khi A chạy MAX(id), session B INSERT và được ID 101.
- A SELECT MAX(id) và nhận 101.

A có thể gắn chi tiết đơn hàng vào **đơn của B**. Đây là race condition nghiêm trọng.

### 11.1. MAX(id) còn sai khi dữ liệu xóa

Nếu ID lớn nhất bị xóa, MAX(id) không phải khóa vừa INSERT và có thể trả hàng cũ.

### 11.2. MAX(id) có thể sai với tenant/filter

Nếu query có WHERE theo tenant hoặc partition, MAX trong tập đó không chứng minh được ID thuộc INSERT hiện tại.

### 11.3. Quy tắc

Dùng:
- RETURNING/OUTPUT gắn với DML.
- JDBC getGeneratedKeys trên statement.
- LAST_INSERT_ID/currval/last_insert_rowid đúng connection/session.
- Sequence NEXTVAL nếu chủ động lấy trước và dùng chính giá trị đó cho INSERT.

**Không dùng MAX(id), ORDER BY id DESC LIMIT 1 hoặc SELECT TOP 1 id DESC để lấy ID của chính INSERT vừa chạy.**

## 12. Sequence, identity và transaction rollback

Nhiều hệ thống sequence/identity sinh số theo cơ chế không rollback giá trị đã cấp.

Ví dụ:

~~~text
BEGIN
INSERT don_hang -> id=100
INSERT chi_tiet -> lỗi
ROLLBACK
~~~

Bản ghi đơn hàng không còn, nhưng ID 100 có thể đã bị tiêu thụ. Lần INSERT sau nhận 101.

Đây là hành vi bình thường. Không:
- Cập nhật lại sequence để lấp mọi lỗ hổng.
- Giả định số ID phản ánh số đơn đã commit.
- Tính số đơn bằng MAX(id)-MIN(id)+1.
- Tái sử dụng ID bị rollback như hợp đồng nghiệp vụ.

### 12.1. Sequence có thể cache

Để tăng hiệu năng concurrency, DBMS có thể cấp số theo cache/range. Server crash có thể làm bỏ qua số chưa dùng trong cache. Khoảng trống không đồng nghĩa có dữ liệu bị xóa.

### 12.2. Commit và khóa trả về

Ứng dụng có thể biết ID ngay sau INSERT trước COMMIT. ID này chỉ là khóa của hàng trong transaction hiện tại; nếu rollback thì hàng biến mất. Không gửi ID cho hệ ngoài như bản ghi đã tồn tại bền vững trước khi transaction commit.

## 13. INSERT cha–con: lấy khóa đúng để ghi bảng con

Mẫu:

~~~sql
CREATE TABLE don_hang (
    id BIGINT PRIMARY KEY,
    ma_don VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE chi_tiet_don (
    id BIGINT PRIMARY KEY,
    don_hang_id BIGINT NOT NULL,
    sku VARCHAR(40) NOT NULL,
    qty INTEGER NOT NULL,
    FOREIGN KEY (don_hang_id) REFERENCES don_hang(id)
);
~~~

Quy trình:
1. INSERT đơn hàng.
2. Lấy đúng id được sinh.
3. INSERT chi tiết dùng id đó.
4. COMMIT cả hai.

Nếu bước 3 lỗi, ROLLBACK cả transaction để không có đơn hàng thiếu chi tiết, nếu nghiệp vụ yêu cầu atomicity.

### 13.1. JDBC transaction

~~~java
connection.setAutoCommit(false);

try {
    long orderId;

    String insertOrder = """
        INSERT INTO don_hang (ma_don)
        VALUES (?)
        """;

    try (PreparedStatement ps = connection.prepareStatement(
            insertOrder, Statement.RETURN_GENERATED_KEYS)) {

        ps.setString(1, "ORD-2026-0001");

        int count = ps.executeUpdate();
        if (count != 1) {
            throw new SQLException("Insert order khong thanh cong");
        }

        try (ResultSet keys = ps.getGeneratedKeys()) {
            if (!keys.next()) {
                throw new SQLException("Khong nhan duoc order id");
            }
            orderId = keys.getLong(1);
            if (keys.wasNull()) {
                throw new SQLException("Order id NULL");
            }
        }
    }

    String insertItem = """
        INSERT INTO chi_tiet_don (don_hang_id, sku, qty)
        VALUES (?, ?, ?)
        """;

    try (PreparedStatement ps = connection.prepareStatement(insertItem)) {
        ps.setLong(1, orderId);
        ps.setString(2, "P01");
        ps.setInt(3, 2);

        int count = ps.executeUpdate();
        if (count != 1) {
            throw new SQLException("Insert item khong thanh cong");
        }
    }

    connection.commit();
} catch (SQLException | RuntimeException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
} finally {
    connection.setAutoCommit(true);
}
~~~

Đây là khung minh họa. Trong ứng dụng dùng pool, cần xử lý lỗi khi khôi phục autoCommit, trạng thái connection không còn hợp lệ và đóng/return connection theo framework. Không nuốt lỗi rollback hoặc tiếp tục dùng connection ở trạng thái transaction không xác định.

### 13.2. Một connection xuyên suốt

INSERT cha, lấy generated key, INSERT con và COMMIT phải cùng **Connection** nếu muốn cùng transaction. Không trả connection về pool giữa chừng rồi lấy connection mới để SELECT LAST_INSERT_ID/currval.

## 14. INSERT nhiều hàng và generated keys

Giả sử một batch thêm 100 sản phẩm. Ứng dụng muốn nhận đủ 100 ID để liên kết dữ liệu khác.

Không giả định:
- Một executeBatch luôn trả 100 generated keys.
- Keys luôn theo thứ tự input.
- Mỗi batch item chỉ tạo đúng một row.
- Một row input luôn tương ứng một row inserted nếu có upsert/conflict/trigger.
- Driver không rewrite batch thành một multi-row INSERT.

### 14.1. JDBC batch

~~~java
String sql = """
    INSERT INTO san_pham (ma_san_pham, ten_san_pham)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {

    for (Product p : products) {
        ps.setString(1, p.code());
        ps.setString(2, p.name());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        while (keys.next()) {
            long id = keys.getLong(1);
            // Luu ID theo cach da xac minh voi driver.
        }
    }
}
~~~

Ví dụ chỉ minh họa API. Cần kiểm tra tài liệu driver về generated keys sau batch, thứ tự, số lượng và kiểu kết quả.

### 14.2. Batch update counts

executeBatch trả mảng int:
- Số hàng update cho từng phần tử khi biết.
- Statement.SUCCESS_NO_INFO khi thành công nhưng không biết số hàng.
- Statement.EXECUTE_FAILED khi phần tử thất bại trong trường hợp driver tiếp tục batch.

Nếu batch thất bại, BatchUpdateException có thể chứa update counts đã hoàn thành/đã biết. Driver có thể dừng hoặc tiếp tục phần còn lại theo khả năng và cấu hình. Ứng dụng phải xử lý partial results và transaction/rollback.

### 14.3. executeLargeBatch

Với lượng row count lớn hơn miền int, JDBC có executeLargeBatch trả long[] và executeLargeUpdate trả long. Driver có thể không hỗ trợ đầy đủ hoặc vẫn có giới hạn riêng. Chọn API phù hợp và kiểm thử.

### 14.4. Gắn key với input row

Cách an toàn thường là có **client-generated correlation key** hoặc business key unique trong batch, rồi lấy kết quả có đủ correlation key + generated id.

Ví dụ INSERT nhiều hàng có RETURNING:

~~~sql
INSERT INTO san_pham (client_ref, ten_san_pham)
VALUES
    ('req-a1', 'But'),
    ('req-a2', 'So'),
    ('req-a3', 'Thuoc')
RETURNING id, client_ref;
~~~

Đây là cú pháp minh họa cho DBMS hỗ trợ RETURNING và bảng có cột client_ref phù hợp. Ứng dụng ánh xạ bằng client_ref, không phụ thuộc thứ tự dòng trả về.

## 15. Số hàng ảnh hưởng: một con số có nhiều nghĩa

Khi gọi UPDATE, cần phân biệt:

- **Matched rows:** số hàng thỏa WHERE.
- **Changed rows:** số hàng có giá trị thực thay đổi.
- **Affected/update count:** số hàng mà DBMS/driver báo cho câu lệnh theo semantics của nó.
- **Rows returned:** số hàng được RETURNING/OUTPUT trả ra.
- **Rows inserted/deleted in trigger:** số hàng trigger thao tác thêm/bớt.
- **Batch update count:** số hàng hoặc trạng thái theo từng phần tử batch.

Không phải DBMS nào cũng báo cùng một khái niệm qua API mặc định.

### 15.1. Ví dụ UPDATE đặt cùng giá trị

~~~sql
UPDATE san_pham
SET trang_thai = 'ACTIVE'
WHERE trang_thai = 'ACTIVE';
~~~

Giả sử 80 hàng đã có ACTIVE.

- Matched rows = 80.
- Changed rows = 0 theo nghĩa giá trị cuối không đổi.
- Số row count client nhận có thể khác tùy DBMS/driver/cấu hình.

Không viết code dùng điều kiện count==0 để báo không tồn tại nếu DBMS/driver có thể trả 0 cho UPDATE khớp nhưng không đổi giá trị.

### 15.2. Câu UPDATE 0 hàng

~~~sql
UPDATE san_pham
SET trang_thai = 'STOP'
WHERE ma_san_pham = 'P99';
~~~

Nếu P99 không tồn tại, affected count thường là 0. Nhưng 0 cũng có thể do:
- Optimistic version không khớp.
- Trạng thái hiện tại không cho phép cập nhật.
- Giá trị không thay đổi và DBMS báo changed rows.
- Row-level security/trigger/view làm thay đổi tập hàng có thể cập nhật.
- Điều kiện tenant/authorization không khớp.

Cần thiết kế query và error semantics để phân biệt nguyên nhân nếu nghiệp vụ yêu cầu.

## 16. So sánh affected rows giữa DBMS

| DBMS | Hành vi cần chú ý |
|---|---|
| PostgreSQL | Command tag thường báo số hàng được UPDATE/DELETE/INSERT; UPDATE thường tính cả hàng khớp dù giá trị không đổi. RETURNING trả tập hàng DML thực hiện. |
| MySQL | Có khác biệt giữa rows matched và rows changed; affected rows mặc định thường phản ánh rows changed cho UPDATE, còn CLIENT_FOUND_ROWS có thể thay đổi cách báo matched rows. JDBC driver có thể cấu hình. |
| SQL Server | @@ROWCOUNT/execute count theo DML và trigger/SET NOCOUNT/driver có thể ảnh hưởng thông báo. Cần đọc kết quả đúng statement. |
| Oracle | SQL%ROWCOUNT trong PL/SQL và update count JDBC báo số hàng DML tác động theo ngữ nghĩa Oracle; trigger DML là một phần cần kiểm tra riêng. |
| SQLite | sqlite3_changes()/JDBC count có quy tắc riêng, thường không bao gồm mọi thay đổi do trigger/foreign key; UPDATE không đổi giá trị vẫn có thể được tính là hàng bị xử lý. |

Bảng là định hướng; phải kiểm tra driver, API, version và tùy chọn kết nối thật.

### 16.1. MySQL: CLIENT_FOUND_ROWS

Với UPDATE:

~~~sql
UPDATE san_pham
SET trang_thai = 'ACTIVE'
WHERE trang_thai = 'ACTIVE';
~~~

MySQL có thể báo số hàng thay đổi là 0 vì giá trị không đổi, trong khi số hàng khớp là 80. Nếu connection bật CLIENT_FOUND_ROWS, semantics affected rows có thể phản ánh số hàng tìm thấy hơn là số hàng đổi.

Một ứng dụng đổi driver option mà không cập nhật logic xử lý count==0 có thể thay đổi hành vi nghiệp vụ.

### 16.2. SQL Server: @@ROWCOUNT

~~~sql
UPDATE dbo.san_pham
SET trang_thai = 'STOP'
WHERE ma_san_pham = 'P01';

SELECT @@ROWCOUNT AS affected_rows;
~~~

@@ROWCOUNT phản ánh số hàng của statement vừa thực thi theo quy tắc SQL Server. Nhưng câu lệnh tiếp theo có thể thay đổi @@ROWCOUNT. Một SELECT/SET/statement khác trước khi đọc có thể làm mất giá trị bạn muốn.

Trong stored procedure/trigger, hãy lưu ngay sau DML nếu cần dùng tiếp:

~~~sql
DECLARE @n BIGINT = @@ROWCOUNT;
~~~

đồng thời lưu ý các lệnh SET/EXEC và cấu trúc điều khiển có semantics riêng.

### 16.3. SQL Server: SET NOCOUNT ON

SET NOCOUNT ON trong stored procedure/trigger giúp tránh gửi thông báo row count phụ cho client. Nó không có nghĩa DML không tác động hàng và không nên được dùng để suy ra số hàng bằng 0.

Khi JDBC gọi procedure có nhiều result sets/update counts, cần xử lý chuỗi kết quả bằng getMoreResults()/getUpdateCount() theo hợp đồng procedure.

### 16.4. Oracle: SQL%ROWCOUNT

Trong PL/SQL:

~~~sql
UPDATE san_pham
SET trang_thai = 'STOP'
WHERE ma_san_pham = 'P01';

DBMS_OUTPUT.PUT_LINE(SQL%ROWCOUNT);
~~~

SQL%ROWCOUNT là thuộc tính implicit cursor phản ánh số hàng của SQL statement vừa chạy trong phạm vi PL/SQL. Đọc ngay sau DML; một SQL statement tiếp theo sẽ thay context implicit cursor.

### 16.5. SQLite: changes và total_changes

SQLite có:
- changes(): số hàng thay đổi bởi DML gần nhất trên connection theo quy tắc SQLite.
- total_changes(): tổng thay đổi của connection trong vòng đời tương ứng, với quy tắc riêng về trigger.
- API sqlite3_changes()/sqlite3_total_changes().

Không dùng total_changes làm row count của một statement đơn lẻ. Cần xem tài liệu SQLite về trigger, foreign key và view vì các thay đổi phụ không nhất thiết được tính giống DML trực tiếp.

## 17. RETURNING/OUTPUT và số hàng

Một cách gắn khóa và số hàng vào chính result set là RETURNING/OUTPUT.

PostgreSQL:

~~~sql
UPDATE san_pham
SET trang_thai = 'STOP'
WHERE trang_thai = 'ACTIVE'
RETURNING id, ma_san_pham;
~~~

SQL Server:

~~~sql
UPDATE dbo.san_pham
SET trang_thai = 'STOP'
OUTPUT INSERTED.id, INSERTED.ma_san_pham
WHERE trang_thai = 'ACTIVE';
~~~

SQLite (runtime hỗ trợ RETURNING):

~~~sql
UPDATE san_pham
SET trang_thai = 'STOP'
WHERE trang_thai = 'ACTIVE'
RETURNING id, ma_san_pham;
~~~

Oracle có RETURNING INTO, với cách bind/collection khác nhau khi nhiều hàng. MySQL hỗ trợ RETURNING tùy sản phẩm/phiên bản; không mặc định có cú pháp PostgreSQL.

### 17.1. Result row count khác update count

Nếu UPDATE RETURNING 80 hàng, ResultSet có thể có 80 dòng. Nhưng JDBC executeQuery/execute trả ResultSet chứ không nhất thiết cung cấp update count theo cùng API. Đừng gọi getUpdateCount trước/sau mà không hiểu JDBC result sequence.

### 17.2. RETURNING không phải chứng cứ transaction đã commit

Ứng dụng có thể đọc returned rows trong transaction chưa commit. Nếu sau đó rollback, các thay đổi không tồn tại bền vững. Chỉ phát sự kiện ra hệ ngoài sau khi commit thành công, hoặc dùng outbox.

## 18. Optimistic locking dùng affected rows

Một bảng có version:

~~~sql
CREATE TABLE tai_khoan (
    id BIGINT PRIMARY KEY,
    ten_hien_thi VARCHAR(100) NOT NULL,
    version_no INTEGER NOT NULL
);
~~~

Ứng dụng đọc version=7. Khi cập nhật:

~~~sql
UPDATE tai_khoan
SET ten_hien_thi = :new_name,
    version_no = version_no + 1
WHERE id = :id
  AND version_no = :expected_version;
~~~

Nếu row count = 1:
- Đúng một hàng khớp ID và version.
- Cập nhật đã được chấp nhận theo điều kiện.
- Có thể tiếp tục transaction.

Nếu row count = 0:
- ID không tồn tại, hoặc
- Version đã thay đổi, hoặc
- Policy/RLS/điều kiện bổ sung không khớp.

Ứng dụng có thể báo conflict hoặc “bản ghi đã được thay đổi bởi người khác”.

### 18.1. Không chỉ kiểm tra row count sau UPDATE không có version

Nếu hai session cùng đọc tên cũ, cả hai UPDATE WHERE id=:id có thể đều thành công; kết quả cuối có thể ghi đè nhau. Thêm version predicate hoặc cơ chế khóa/transaction phù hợp để phát hiện lost update.

### 18.2. Version column không phải timestamp

Dùng số version tăng dần thường tránh độ chính xác thời gian và clock skew. Không dùng updated_at=CURRENT_TIMESTAMP làm optimistic token nếu precision, timezone hoặc nhiều cập nhật cùng tick khiến token không phân biệt.

### 18.3. JPA/Hibernate

ORM có thể hỗ trợ @Version và phát hiện optimistic lock exception. Khi dùng ORM, không tự viết thêm UPDATE native bỏ qua version nếu không quản lý đồng bộ persistence context và cache.

## 19. Phân biệt “không tồn tại” và “không được phép”

Ví dụ:

~~~sql
UPDATE don_hang
SET trang_thai = 'CANCELLED'
WHERE id = :id
  AND customer_id = :current_customer
  AND trang_thai = 'NEW';
~~~

Nếu affected rows=0, có thể:
- Đơn không tồn tại.
- Đơn thuộc customer khác.
- Đơn đã PAID/SHIPPED.
- Đơn đã CANCELLED.

Đôi khi trả cùng một lỗi “không tìm thấy hoặc không thể cập nhật” là chủ đích bảo mật để tránh lộ tồn tại tài nguyên. Nếu cần phân biệt, thực hiện truy vấn/logic trong transaction có phân quyền và không tạo race mới.

Không chạy SELECT trước rồi UPDATE sau mà không xét concurrency: trạng thái có thể đổi giữa hai câu lệnh.

## 20. DELETE và affected rows

~~~sql
DELETE FROM chi_tiet_don
WHERE don_hang_id = :order_id;
~~~

Nếu count=0, có thể:
- Đơn không có chi tiết.
- ID không tồn tại.
- Dữ liệu đã bị xóa trước.
- Điều kiện tenant/authorization không khớp.

### 20.1. Idempotent DELETE

Một API DELETE có thể coi xóa tài nguyên đã không tồn tại là thành công theo semantics HTTP/API, hoặc trả 404. Row count=0 không tự quyết định hợp đồng.

### 20.2. ON DELETE CASCADE

Xóa một đơn có thể làm xóa 10 dòng chi tiết bằng FK cascade. Số hàng mà JDBC báo cho DELETE cha không nhất thiết bằng tổng số hàng cha + con. Nếu cần tổng audit, hãy đếm/ghi ở cơ chế riêng, không suy ra từ một update count duy nhất.

### 20.3. Trigger DELETE

Trigger có thể ghi log hoặc thao tác bảng khác. Số dòng log không đồng nghĩa số hàng DELETE gốc. Xác định rõ count đang đo DML gốc hay side effects.

## 21. INSERT ... ON CONFLICT / UPSERT và affected rows

Upsert kết hợp insert mới và update khi conflict. Row count semantics khác giữa DBMS.

PostgreSQL:

~~~sql
INSERT INTO tai_khoan (id, ten_hien_thi)
VALUES (10, 'An')
ON CONFLICT (id)
DO UPDATE SET ten_hien_thi = EXCLUDED.ten_hien_thi
RETURNING id;
~~~

RETURNING trả hàng được INSERT hoặc UPDATE theo nhánh thực hiện; với điều kiện WHERE của DO UPDATE, một số hàng conflict có thể bị bỏ qua.

MySQL:

~~~sql
INSERT INTO tai_khoan (id, ten_hien_thi)
VALUES (10, 'An')
ON DUPLICATE KEY UPDATE
    ten_hien_thi = 'An';
~~~

Affected rows có semantics riêng cho insert/update/no-op, và CLIENT_FOUND_ROWS có thể ảnh hưởng. Không dùng một công thức count chung với PostgreSQL.

SQL Server thường dùng INSERT/UPDATE logic trong transaction hoặc MERGE với đánh giá kỹ hành vi/phiên bản; OUTPUT có thể ghi nhận action/rows. Không mặc định MERGE là giải pháp an toàn nhất cho mọi workload.

Oracle MERGE xử lý nhánh matched/not matched; SQL%ROWCOUNT và RETURNING capabilities cần kiểm tra theo cú pháp/phiên bản.

SQLite INSERT ... ON CONFLICT DO UPDATE có upsert; RETURNING được hỗ trợ ở runtime mới. changes() và returned rows cần hiểu theo quy tắc SQLite.

### 21.1. No-op upsert

Nếu conflict row đã có cùng giá trị, DBMS có thể:
- Vẫn xem nhánh UPDATE là action.
- Báo changed rows=0.
- Báo matched/affected theo option.
- Kích hoạt trigger theo semantics riêng.

Nếu ứng dụng chỉ muốn tạo event khi **giá trị thực sự đổi**, cần so sánh trước/sau hoặc có điều kiện update khi khác, đồng thời test row count và trigger.

## 22. Generated keys với batch: chiến lược an toàn

Khi cần insert nhiều hàng và nhận khóa, có ba mẫu:

### 22.1. INSERT ... RETURNING/OUTPUT

Ưu tiên khi DBMS hỗ trợ trả toàn bộ keys và correlation columns:

~~~sql
INSERT INTO san_pham (client_ref, ten_san_pham)
VALUES
    ('req-a1', 'But'),
    ('req-a2', 'So')
RETURNING id, client_ref;
~~~

Ứng dụng map theo client_ref, không dựa vào thứ tự trả về.

### 22.2. Sinh khóa ở ứng dụng trước

Với UUID:

~~~java
UUID id = UUID.randomUUID();
~~~

Sau đó INSERT id cùng dữ liệu. Ứng dụng đã biết ID trước khi gọi DB, dễ liên kết batch/cha–con và phân tán. Nhưng cần bảo đảm DB column/driver mapping đúng và có UNIQUE/PK.

### 22.3. Sequence lấy trước

Với sequence độc lập, ứng dụng có thể lấy NEXTVAL rồi INSERT chính ID đó. Hữu ích khi cần chuẩn bị khóa cho nhiều bảng, nhưng làm SQL phụ thuộc DBMS và tiêu thụ sequence kể cả khi INSERT sau đó rollback.

### 22.4. Không suy ra keys theo dải số

Không giả định batch 100 hàng sinh ID từ first_id đến first_id+99:
- Có thể có increment khác 1.
- Có thể có interleaving/concurrency.
- Trigger có thể sinh identity khác.
- Conflict/no-op làm số hàng tạo ít hơn.
- Driver có thể rewrite batch.
- Cơ chế cache/sequence khác.

Chỉ dùng dải số nếu hệ thống có hợp đồng rất cụ thể, được DBMS/driver/config bảo đảm và test; thông thường không nên.

## 23. JDBC: đọc update count đúng cách

### 23.1. executeUpdate()

Dùng cho câu DML thông thường khi không cần ResultSet:

~~~java
int count = ps.executeUpdate();
~~~

count có thể là số hàng hoặc Statement.SUCCESS_NO_INFO trong một số batch contexts; executeUpdate cho statement thông thường trả int theo API. Nếu số hàng có thể vượt int, dùng executeLargeUpdate khi driver hỗ trợ.

### 23.2. executeLargeUpdate()

~~~java
long count = ps.executeLargeUpdate();
~~~

Dùng khi số hàng có thể vượt giới hạn int hoặc API large update count cần thiết. Kiểm tra driver support.

### 23.3. executeBatch()

~~~java
int[] counts = ps.executeBatch();
~~~

Mỗi phần tử phản ánh một lệnh batch theo thứ tự batch được thêm vào, với các giá trị:
- Số hàng update.
- SUCCESS_NO_INFO.
- EXECUTE_FAILED.

Nếu nhận BatchUpdateException, inspect getUpdateCounts() và transaction state. Không coi batch thất bại có nghĩa không có thao tác nào đã xảy ra; dùng transaction và rollback theo yêu cầu atomicity.

### 23.4. execute() khi có nhiều loại kết quả

Stored procedure, SQL Server OUTPUT hoặc câu lệnh trả ResultSet có thể yêu cầu execute() và lặp qua:
- getResultSet().
- getUpdateCount().
- getMoreResults().

Không giả định kết quả đầu tiên luôn là update count hoặc ResultSet cuối luôn chứa generated key.

## 24. Trigger và update counts

Trigger có thể thực hiện INSERT/UPDATE/DELETE khác. Driver có thể nhận update count phụ hoặc chỉ count DML gốc tùy DBMS, protocol, stored procedure và SET NOCOUNT.

### 24.1. SQL Server

SET NOCOUNT ON trong trigger/procedure giúp tránh thông báo row count phụ. Nếu procedure trả nhiều result counts, client phải xử lý theo JDBC API. Không dựa vào “lệnh update count đầu tiên” nếu procedure có nhiều DML.

### 24.2. MySQL

Affected rows của statement có thể bị ảnh hưởng bởi client flags và hành vi trigger/upsert; trigger phụ không nên được dùng làm nguồn đo số hàng của câu lệnh gốc nếu không có contract cụ thể.

### 24.3. SQLite

changes() có quy tắc về direct changes so với trigger/foreign key; last_insert_rowid có behavior riêng trong trigger. Đọc tài liệu API cụ thể thay vì suy ra từ SQL chuẩn.

### 24.4. PostgreSQL

Command tag/RETURNING phản ánh DML theo quy tắc PostgreSQL; trigger có thể sửa/loại hàng trong BEFORE ROW và tác động phụ có thể làm số hàng/returned rows khác kỳ vọng. Nếu dùng trigger RETURN NULL để bỏ qua hàng, hãy test command count và RETURNING.

## 25. Generated keys và trigger

Một bảng INSERT có trigger AFTER INSERT ghi audit table cũng có identity riêng.

- PostgreSQL RETURNING id gắn với hàng DML chính.
- SQL Server OUTPUT INSERTED.id gắn với hàng target; @@IDENTITY có thể bị trigger làm thay đổi.
- MySQL LAST_INSERT_ID() có quy tắc connection-specific; trigger insert vào bảng khác có behavior riêng, cần kiểm tra theo MySQL docs.
- Oracle RETURNING INTO trả giá trị cột mục tiêu; sequence trong trigger có thể cấp giá trị cho NEW theo cách khác.
- SQLite last_insert_rowid có quy tắc khi ở trong trigger; sau khi trigger kết thúc giá trị trước trigger được khôi phục theo mô tả SQLite.

**Ưu tiên cơ chế trả khóa gắn trực tiếp với hàng target** (RETURNING/OUTPUT/JDBC generated keys được driver hỗ trợ), thay vì một hàm “ID gần nhất” có thể bị side effects ảnh hưởng.

## 26. Connection pooling và session-specific functions

Các hàm như:
- MySQL LAST_INSERT_ID().
- PostgreSQL currval()/lastval().
- SQLite last_insert_rowid().
- SQL Server SCOPE_IDENTITY()/@@IDENTITY.

đều có phạm vi session/connection/scope riêng.

Với connection pool:
1. Mượn một Connection.
2. Thực hiện INSERT.
3. Lấy key trên cùng Connection/statement.
4. Hoàn tất transaction.
5. Trả Connection về pool.

Không INSERT trên connection A rồi trả A về pool, lấy connection B và SELECT LAST_INSERT_ID()/currval() với kỳ vọng ID của A.

Cũng không chia INSERT và retrieval sang hai thread sử dụng cùng connection đồng thời; thao tác có thể xen kẽ và phá semantics.

## 27. Isolation, retry và duplicate insert

Ứng dụng có thể gặp timeout sau khi DB đã INSERT và COMMIT nhưng trước khi client nhận response. Client không biết thao tác đã commit hay chưa.

Nếu retry INSERT:
- Có thể tạo bản ghi thứ hai nếu không có idempotency key.
- Có thể gặp UNIQUE conflict.
- Có thể nhận generated ID khác.
- Không thể dùng “lấy ID mới nhất” để suy ra lần đầu đã thành công.

### 27.1. Idempotency key

Một mẫu:

~~~sql
CREATE TABLE request_dedup (
    request_id VARCHAR(80) PRIMARY KEY,
    order_id BIGINT NOT NULL
);
~~~

Trong cùng transaction:
1. Kiểm tra/ghi request_id có UNIQUE.
2. Nếu request mới, INSERT đơn và lấy ID.
3. Lưu request_id → order_id.
4. Commit.
5. Retry cùng request_id thì trả order_id đã lưu.

Chi tiết locking/upsert khác DBMS; phải xử lý race hai retry đồng thời. UNIQUE constraint là lớp chống duplicate chính.

### 27.2. Generated key không phải idempotency token

ID sinh mới chỉ xác định một hàng đã được tạo; nó không chứng minh client retry đang nói về cùng một business request. Dùng request_id/client_ref riêng.

## 28. Sinh UUID ở DB hay ứng dụng?

### 28.1. DB-generated UUID

Ưu điểm:
- DB quản lý default.
- Client không phải sinh ID.
- Dễ áp một chính sách chung nếu mọi writer đi qua DB.

Nhược điểm:
- Hàm khác nhau.
- Có thể cần extension.
- Driver/generated keys phụ thuộc DBMS.
- ID chỉ biết sau INSERT.

### 28.2. Application-generated UUID

Java:

~~~java
UUID id = UUID.randomUUID();
~~~

Insert bằng setObject(id), setString(id.toString()) hoặc bind binary theo driver/schema.

Ưu điểm:
- Biết ID trước INSERT.
- Hỗ trợ offline/distributed creation.
- Dễ gắn cha–con trong batch.
- Không cần round-trip lấy generated key.

Nhược điểm:
- Phải thống nhất version/format/byte order.
- UUID ngẫu nhiên có thể làm B-tree locality kém hơn ID tăng dần.
- Mọi client phải tạo ID đúng.
- Cần UNIQUE/PK để phát hiện collision.

### 28.3. UUID không phải secret

UUID v4 khó đoán hơn ID tăng dần, nhưng không thay authorization. API vẫn phải kiểm tra quyền truy cập theo người dùng/tenant.

### 28.4. UUID v7/ULID

Các ID có thành phần thời gian giúp locality tốt hơn trong một số workload và dễ sắp xếp gần theo thời gian. Nhưng:
- DBMS có hỗ trợ native generator hay không khác nhau.
- Clock skew và tính phân tán cần hiểu.
- ID có thể tiết lộ thời gian tạo.
- Thứ tự không đồng nghĩa transaction commit order.
- ULID string và UUID binary không phải cùng format nếu không mapping.

## 29. Generated key và security

IDENTITY tăng dần dễ đoán:

~~~text
/orders/1001
/orders/1002
/orders/1003
~~~

Nếu API trả ID, không có nghĩa người gọi được phép xem/sửa mọi ID. Phải kiểm tra ownership/tenant, authorization ở server, RLS khi phù hợp, không tin ID do client gửi và không lộ ID nội bộ nếu không cần.

Không dùng “UUID khó đoán” làm lớp bảo mật duy nhất.

## 30. Dùng affected rows trong optimistic locking và API

Một API PATCH có thể chạy:

~~~sql
UPDATE tai_khoan
SET ten_hien_thi = :name,
    version_no = version_no + 1
WHERE id = :id
  AND version_no = :expected_version;
~~~

Logic:
- Count = 1: cập nhật đúng một phiên bản.
- Count = 0: xung đột/không tồn tại/không được phép.
- Count > 1: lỗi mô hình khóa hoặc điều kiện WHERE thiếu tính duy nhất; không nên âm thầm chấp nhận.

### 30.1. WHERE phải có unique key

Nếu UPDATE theo email không UNIQUE, count=5 có thể hợp lệ về SQL nhưng sai nghiệp vụ nếu chỉ mong một tài khoản. Dùng PK/UNIQUE key và kiểm tra row count đúng 1.

### 30.2. Phân biệt 404 và 409

- 404: tài nguyên không tồn tại hoặc cố tình che giấu.
- 409: conflict do version/trạng thái.
- 412: Precondition Failed khi dùng HTTP If-Match/ETag.

Chọn theo API contract. Row count=0 chỉ là tín hiệu từ DB, không tự quyết định HTTP status.

### 30.3. No-op update

Nếu người dùng gửi cùng giá trị hiện tại, ứng dụng có thể:
- Coi thành công idempotent.
- Không tăng version nếu không đổi.
- Tăng version vì request được chấp nhận.
- Trả 204 nhưng không ghi audit change.

Phải xác định rõ. Với MySQL, affected rows có thể khác giữa changed/matched; với hệ khác, semantics khác. Có thể dùng RETURNING/OUTPUT hoặc điều kiện null-safe để biết giá trị đổi theo contract.

## 31. Dùng row count khi UPDATE/DELETE theo tenant

~~~sql
UPDATE don_hang
SET trang_thai = 'CANCELLED'
WHERE id = :id
  AND tenant_id = :tenant_id
  AND trang_thai = 'NEW';
~~~

Đây là cách đưa **authorization scope và state transition** vào predicate atomic, miễn tenant_id lấy từ server-side authenticated context.

Count=1: đúng một hàng được cập nhật. Count=0: không có hàng phù hợp hoặc trạng thái không cho phép.

Không SELECT để kiểm tra tenant/state rồi UPDATE chỉ theo id mà bỏ điều kiện; giữa hai câu lệnh transaction khác có thể đổi trạng thái. Đưa điều kiện vào UPDATE và xử lý row count.

## 32. RETURNING/OUTPUT cho UPDATE và DELETE

PostgreSQL lấy dữ liệu sau UPDATE:

~~~sql
UPDATE tai_khoan
SET ten_hien_thi = 'An'
WHERE id = 10
RETURNING id, ten_hien_thi, version_no;
~~~

SQL Server:

~~~sql
UPDATE dbo.tai_khoan
SET ten_hien_thi = 'An'
OUTPUT INSERTED.id, INSERTED.ten_hien_thi, INSERTED.version_no
WHERE id = 10;
~~~

Lấy dữ liệu cũ khi DELETE:

PostgreSQL:

~~~sql
DELETE FROM don_hang
WHERE id = 10
RETURNING id, ma_don;
~~~

SQL Server:

~~~sql
DELETE FROM dbo.don_hang
OUTPUT DELETED.id, DELETED.ma_don
WHERE id = 10;
~~~

Các result rows hữu ích để trả resource đã đổi, ghi outbox/audit set-based, xác định hàng đã xóa và tránh SELECT lại sau DML. Tuy nhiên, OUTPUT/RETURNING có hạn chế khi trigger/view/cascade và transaction; hãy kiểm tra docs/version.

## 33. SQL Server OUTPUT INTO và audit

SQL Server có thể dùng OUTPUT INTO để lưu các hàng đã thay đổi:

~~~sql
DECLARE @changed TABLE (
    id BIGINT,
    old_status VARCHAR(20),
    new_status VARCHAR(20)
);

UPDATE dbo.don_hang
SET trang_thai = 'CANCELLED'
OUTPUT
    DELETED.id,
    DELETED.trang_thai,
    INSERTED.trang_thai
INTO @changed (id, old_status, new_status)
WHERE trang_thai = 'NEW';

SELECT * FROM @changed;
~~~

Đây là ví dụ minh họa; nếu bảng có trigger tương ứng, OUTPUT có thể cần INTO theo hạn chế SQL Server. Với table variable/temp table, kiểm tra transaction và quyền truy cập.

### 33.1. OUTPUT không nhất thiết là trạng thái sau AFTER trigger

OUTPUT có quy tắc về thời điểm giá trị được lấy so với trigger. Đừng giả định mọi cột OUTPUT phản ánh những thay đổi tiếp theo do AFTER trigger thực hiện. Nếu cần trạng thái cuối sau toàn bộ trigger logic, có thể cần SELECT lại trong transaction theo thiết kế an toàn hoặc ghi kết quả trong trigger/outbox phù hợp.

## 34. Batch failures và transaction semantics

Giả sử batch INSERT 100 dòng, dòng 51 vi phạm UNIQUE.

Tùy DBMS/driver:
- Batch có thể dừng ở lỗi.
- Một phần câu lệnh trước đó có thể đã chạy.
- Nếu autoCommit=true, một số thao tác trước đó có thể đã commit.
- Nếu transaction thủ công, có thể rollback toàn batch nếu engine/driver và logic hỗ trợ.
- BatchUpdateException có thể mang update counts đã biết.
- Generated keys có thể chỉ có một phần hoặc không được trả đầy đủ.

### 34.1. Atomic batch

Nếu cần tất cả hoặc không có:
1. setAutoCommit(false).
2. Chạy batch.
3. Kiểm tra kết quả và constraints.
4. Commit nếu toàn bộ thành công.
5. Rollback khi có lỗi.

Kiểm tra DBMS có statement atomicity và driver batch behavior như mong đợi. Không mặc định mọi batch trên mọi engine có cùng rollback semantics.

### 34.2. Partial acceptance

Một số nghiệp vụ cho phép một phần thành công. Khi đó phải lưu kết quả từng item với correlation ID, generated key (nếu có), error code và trạng thái; không chỉ nhìn một boolean success.

### 34.3. Retry

Retry batch có thể tạo duplicates nếu các item trước đã commit. Dùng idempotency keys/business unique constraints và thiết kế retry có thể lặp an toàn.

## 35. Những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| SELECT MAX(id) sau INSERT | Session khác có thể chèn trước | RETURNING/OUTPUT/getGeneratedKeys |
| Dùng @@IDENTITY khi có trigger | Có thể lấy identity từ trigger scope | SCOPE_IDENTITY/OUTPUT |
| Dùng IDENT_CURRENT để lấy ID của mình | Giá trị toàn table, mọi session | OUTPUT/SCOPE_IDENTITY |
| Lấy LAST_INSERT_ID trên connection khác | Giá trị theo connection | Cùng Connection |
| Gọi currval trước nextval | Chưa có giá trị session | RETURNING hoặc nextval trước |
| Dùng lastval sau trigger | Có thể là sequence khác vừa gọi | RETURNING cột target |
| Giả định ID không có khoảng trống | Rollback/cache/failure tiêu thụ số | Không dùng ID làm số chứng từ liên tục |
| Giả định batch trả đủ keys | Driver/DBMS khác nhau | Integration test, RETURNING/correlation |
| Giả định keys theo input order | Result order không phải contract | Correlation key |
| Tính dải ID bằng first+count | Increment/concurrency/conflict | Lấy từng key |
| Coi count=0 luôn không tồn tại | Có no-op/optimistic mismatch/RLS | Định nghĩa affected semantics |
| Coi count=1 luôn giá trị đổi | Có thể matched/no-op semantics | Compare old/new khi cần |
| Không đọc count ngay | @@ROWCOUNT/SQL%ROWCOUNT bị statement sau đổi | Lưu ngay |
| Dùng total_changes cho một SQLite statement | Đó là tổng connection | changes()/driver count đúng phạm vi |
| Không kiểm tra SUCCESS_NO_INFO | Batch không biết count chính xác | Xử lý sentinel |
| Nuốt BatchUpdateException | Có thể đã partial execute | Inspect counts + rollback |
| Tách insert/retrieve khỏi connection | Session-specific function đổi scope | Giữ một connection |
| Commit trước khi lấy key | Không cần thiết, tăng roundtrip | Lấy key trong transaction |
| Gửi ID ra ngoài trước commit | Có thể rollback sau đó | Outbox/response sau commit |
| Dùng UUID thay authorization | ID không phải quyền | Authorization server-side |
| Trigger tạo audit làm lệch @@IDENTITY | Identity phụ | OUTPUT/SCOPE_IDENTITY |
| Trigger tạo count phụ | Client đọc nhầm update count | SET NOCOUNT/driver handling |
| Cascade tính vào count cha | Row count không phải tổng toàn graph | Audit riêng |
| Upsert count giả định portable | Changed/matched semantics khác | Adapter và test |
| No-op UPDATE bị coi lỗi | DBMS changed rows=0 | Hợp đồng no-op rõ |
| Update theo non-unique key mong count=1 | Có thể nhiều hàng | PK/UNIQUE predicate |
| SELECT trước UPDATE để kiểm tra state | Race condition | Predicate atomic + count |
| Dùng IDENTITY cho invoice continuous | Gap là bình thường | Counter/document number design riêng |

## 36. Quy trình kiểm thử lấy key và row count

Mỗi DBMS/driver cần test riêng:

| Test | Kỳ vọng cần xác định |
|---|---|
| INSERT một hàng | Lấy đúng generated key |
| INSERT có ID tường minh | Cho phép/từ chối theo identity mode |
| INSERT lỗi UNIQUE | Không trả nhầm key cũ |
| INSERT rollback | Hàng mất; sequence gap có thể còn |
| INSERT cha–con | FK dùng đúng ID |
| INSERT nhiều hàng | Đủ keys/correlation |
| JDBC batch | Keys/counts/success sentinels |
| Batch lỗi giữa chừng | Partial execution và rollback |
| Trigger sinh identity khác | Không lấy nhầm audit ID |
| MySQL LAST_INSERT_ID | Cùng connection |
| PostgreSQL currval | Cùng session và sequence đã nextval |
| SQL Server @@IDENTITY vs SCOPE_IDENTITY | Trigger identity không gây nhầm |
| SQL Server OUTPUT + trigger | Tuân thủ OUTPUT restrictions |
| Oracle RETURNING INTO | Bind đúng kiểu/số hàng |
| SQLite INTEGER PRIMARY KEY | Lấy đúng rowid alias |
| SQLite WITHOUT ROWID | Không dùng last_insert_rowid sai |
| UPDATE matched và changed | Phân biệt theo DBMS |
| UPDATE set cùng giá trị | Row count semantics |
| UPDATE 0 hàng | Xử lý đúng |
| DELETE 0/1/n | API behavior |
| ON DELETE CASCADE | Count cha vs con |
| Upsert insert branch | Generated key đúng |
| Upsert update/no-op branch | Count/trigger semantics |
| Optimistic version đúng | Count=1 |
| Optimistic version cũ | Count=0/conflict |
| Tenant sai | Không sửa hàng khác |
| Connection pool | Không trộn session IDs |
| Timeout sau commit | Retry không duplicate |
| Large update count | executeLargeUpdate support |
| SET NOCOUNT/procedure | JDBC result sequence đúng |
| Driver upgrade | Không đổi mapping âm thầm |

### 36.1. Test concurrency cho key retrieval

Chạy hai connection song song:
- A INSERT hàng A.
- B INSERT hàng B.
- A lấy key.
- B lấy key.
- Xác nhận mỗi key map đúng business key.

Nếu giải pháp dựa trên MAX(id), test này có thể bộc lộ race. Với RETURNING/getGeneratedKeys/connection-scoped functions, test chứng minh đúng scope.

### 36.2. Test no-op update

Tạo hàng có status ACTIVE, chạy UPDATE status=ACTIVE:
- Ghi nhận matched rows nếu có API.
- Ghi nhận changed rows.
- Ghi nhận JDBC update count.
- So sánh khi bật/tắt driver option CLIENT_FOUND_ROWS trên MySQL.
- Xác nhận trigger/audit có chạy hay không theo DBMS.

## 37. Ma trận lựa chọn theo DBMS

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| Tự sinh số | IDENTITY/sequence | AUTO_INCREMENT | IDENTITY/SEQUENCE | IDENTITY/sequence | INTEGER PRIMARY KEY |
| Lấy khóa gắn DML | RETURNING | JDBC keys/LAST_INSERT_ID; tùy version | OUTPUT INSERTED | RETURNING INTO/JDBC keys | RETURNING (version mới)/JDBC |
| Session current value | currval/lastval | LAST_INSERT_ID() | SCOPE_IDENTITY() | sequence.CURRVAL | last_insert_rowid() |
| Tránh trigger identity nhiễu | RETURNING target | Kiểm tra same connection | OUTPUT/SCOPE_IDENTITY | RETURNING target | RETURNING/rowid API |
| Lấy nhiều generated rows | RETURNING | Driver/version-specific | OUTPUT | RETURNING/bulk API | RETURNING |
| Row count trong PL/SQL/T-SQL | Command tag/GET DIAGNOSTICS | ROW_COUNT diagnostics | @@ROWCOUNT | SQL%ROWCOUNT | changes()/API |
| JDBC count | executeUpdate | Driver options | Driver/procedure results | Driver | Driver |
| Large update count | Driver/JDBC large API | Driver/JDBC large API | Driver/JDBC large API | Driver/JDBC large API | Driver/JDBC large API |

Bảng là hướng dẫn chọn công cụ, không thay thế tài liệu phiên bản cụ thể. Một số cú pháp trả key nhiều hàng phụ thuộc driver và runtime.

## 38. Lựa chọn khóa tăng dần hay UUID

| Tiêu chí | BIGINT tăng dần | UUID/ID phân tán |
|---|---|---|
| Kích thước khóa | Nhỏ | Lớn hơn |
| Index locality | Thường tốt | UUID ngẫu nhiên có thể phân tán |
| Sinh trước INSERT | Thường cần sequence/identity | Có thể sinh ở ứng dụng |
| Multi-node offline | Cần cơ chế cấp ID | Thuận tiện hơn |
| Dễ đoán | Có | UUID ngẫu nhiên khó đoán hơn nhưng không phải bảo mật |
| Khả năng tương thích | Nhiều DB hỗ trợ | Cần mapping format |
| Foreign key | Gọn | Tốn dung lượng hơn |
| Tính liên tục | Có khoảng trống | Không có ý nghĩa liên tục |

Không có lựa chọn đúng cho mọi hệ thống. Hãy xét số lượng ghi, phân tán, kích thước index, yêu cầu ID trước insert, khả năng di chuyển và mức lộ thông tin.

## 39. Tài liệu và API chính thức nên tra cứu

Khi triển khai, kiểm tra đúng version và driver:

- **PostgreSQL:** Identity Columns, Sequence Functions, INSERT/UPDATE/DELETE RETURNING, Command Tags, JDBC driver generated keys.
- **MySQL:** AUTO_INCREMENT, LAST_INSERT_ID(), INSERT ... ON DUPLICATE KEY UPDATE, affected rows, CLIENT_FOUND_ROWS, Connector/J generated keys.
- **SQL Server:** IDENTITY, SEQUENCE, SCOPE_IDENTITY, @@IDENTITY, IDENT_CURRENT, OUTPUT Clause, @@ROWCOUNT, SET NOCOUNT, Microsoft JDBC generated keys.
- **Oracle:** Identity Columns, CREATE SEQUENCE, NEXTVAL/CURRVAL, DML RETURNING INTO, SQL%ROWCOUNT, Oracle JDBC generated keys/RETURNING binds.
- **SQLite:** INTEGER PRIMARY KEY/ROWID, AUTOINCREMENT, last_insert_rowid(), changes(), RETURNING, sqlite3 APIs, JDBC driver behavior.
- **JDBC:** Statement.RETURN_GENERATED_KEYS, PreparedStatement.getGeneratedKeys, executeUpdate/executeLargeUpdate, executeBatch/executeLargeBatch, BatchUpdateException, getMoreResults.
- **Java:** BigDecimal, UUID, transaction management, try-with-resources.

## 40. Tổng kết cần ghi nhớ

1. Khóa tự sinh là định danh kỹ thuật; khóa nghiệp vụ vẫn cần UNIQUE/validation riêng.
2. **IDENTITY, AUTO_INCREMENT, sequence và ROWID** là các cơ chế khác nhau, không có cú pháp chung cho mọi DBMS.
3. PostgreSQL thường ưu tiên **INSERT ... RETURNING**; SQL Server có **OUTPUT INSERTED**; Oracle có **RETURNING INTO**; MySQL/SQLite có cơ chế connection-specific và JDBC phù hợp.
4. **Không dùng MAX(id)** để lấy ID vừa INSERT vì session khác có thể chèn trước.
5. SQL Server **@@IDENTITY** có thể bị trigger làm nhiễu; dùng SCOPE_IDENTITY hoặc OUTPUT phù hợp.
6. MySQL LAST_INSERT_ID, PostgreSQL currval và SQLite last_insert_rowid cần đúng connection/session.
7. JDBC **getGeneratedKeys()** tiện nhưng phụ thuộc driver, batch, trigger và version; phải kiểm thử.
8. Batch keys cần correlation key; không giả định thứ tự hay dải ID liên tục.
9. IDENTITY/sequence có thể có khoảng trống do rollback, cache, lỗi và concurrency.
10. **Matched rows và changed rows không giống nhau**; MySQL có tùy chọn CLIENT_FOUND_ROWS ảnh hưởng semantics báo count.
11. PostgreSQL, SQL Server, Oracle, MySQL, SQLite và JDBC có cách báo update count khác nhau; đọc đúng API/context.
12. SQL Server @@ROWCOUNT và Oracle SQL%ROWCOUNT cần đọc ngay sau DML trước khi statement khác thay đổi context.
13. JDBC batch có SUCCESS_NO_INFO/EXECUTE_FAILED và BatchUpdateException; phải xử lý partial results/rollback.
14. Dùng affected rows cho optimistic locking bằng version predicate và khóa duy nhất.
15. Count=0 không tự giải thích “không tồn tại”, “xung đột”, “không đủ quyền” hay “no-op”; hợp đồng API quyết định.
16. Trigger, cascade, upsert, view và stored procedure có thể làm update counts phức tạp; không coi count log phụ là count DML gốc.
17. Lấy khóa và INSERT cha–con trên **cùng connection/transaction**.
18. Không gửi generated ID như dữ liệu đã commit trước khi transaction commit thành công.
19. Dùng idempotency key để xử lý timeout/retry, không dựa vào generated key như business request identity.
20. UUID không thay authorization; ID tăng dần không phải số chứng từ liên tục.
21. Kiểm thử concurrency, batch, no-op, rollback, trigger và connection pooling trên driver thực tế.
22. Hãy hỏi: **“Khóa này do ai sinh, thuộc connection/scope nào, hàng nào tạo ra nó, và con số affected rows đang đếm matched hay changed?”**

**Thông điệp cuối cùng:** Lấy khóa sinh tự động phải gắn với đúng hàng và đúng connection; đọc số hàng ảnh hưởng phải gắn với đúng semantics của DBMS/driver. Dùng RETURNING/OUTPUT/generated keys khi có thể, kiểm tra row count theo hợp đồng nghiệp vụ, giữ cha–con trong cùng transaction và kiểm thử retry/concurrency. Đó là nền tảng để ứng dụng SQL không gắn nhầm dữ liệu và không báo thành công giả.
