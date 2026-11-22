# Sequence, identity, generated keys và RETURNING từ JDBC

Ứng dụng Java thường cần tạo khóa chính cho bản ghi mới và lấy ngay giá trị khóa đó để ghi dữ liệu liên quan, trả kết quả cho API hoặc cập nhật object trong bộ nhớ. Với Oracle Database, có nhiều cách thực hiện: dùng database sequence, dùng identity column, yêu cầu JDBC trả generated keys hoặc dùng mệnh đề SQL RETURNING ... INTO.

Các cơ chế này có liên quan nhưng không đồng nhất:
- **Sequence** là object độc lập của Oracle tạo ra dãy số; ứng dụng có thể lấy NEXTVAL trước hoặc dùng trực tiếp trong INSERT.
- **Identity column** là cột được Oracle tự sinh giá trị dựa trên sequence nội bộ gắn với table.
- **JDBC generated keys** là API JDBC cho phép ứng dụng đọc giá trị được database tạo ra sau lệnh DML.
- **RETURNING INTO** là cú pháp Oracle SQL trả giá trị của row vừa được INSERT/UPDATE/DELETE; Oracle JDBC cung cấp API mở rộng để đọc các giá trị này.

Bài học dùng Oracle Database 19c và Java JDBC làm mốc, tập trung vào:
- Tạo, dùng, điều chỉnh và quản lý sequence.
- Phân biệt sequence với identity column.
- Khai báo identity: ALWAYS, BY DEFAULT và BY DEFAULT ON NULL.
- Lấy khóa sinh tự động bằng JDBC getGeneratedKeys().
- Dùng Oracle RETURNING ... INTO qua Oracle JDBC API.
- Xử lý batch insert, transaction, connection pool và concurrency.
- Mapping kiểu dữ liệu, resource management và exception handling.
- Migration dữ liệu, import/export, kiểm tra metadata và troubleshooting.

Cú pháp và khả năng cụ thể phụ thuộc Oracle Database release, Oracle JDBC driver (ojdbc), Java version và loại statement. Luôn thử trên đúng driver/runtime của ứng dụng; không suy luận rằng một tính năng JDBC được hỗ trợ giống nhau ở mọi phiên bản driver.

## 1. Bài toán sinh khóa trong ứng dụng

Giả sử ứng dụng quản lý đơn hàng. Khi tạo một order, database cần cấp ORDER_ID duy nhất. Ứng dụng còn phải tạo các dòng ORDER_ITEM tham chiếu đến order đó.

Luồng nghiệp vụ:

~~~text
Java application
      |
      | INSERT order
      v
Oracle Database assigns ORDER_ID
      |
      | Return ORDER_ID to Java
      v
Java inserts ORDER_ITEM rows using ORDER_ID
      |
      v
COMMIT transaction
~~~

Ứng dụng cần lấy ID ngay sau INSERT, nhưng không nên tự tính bằng MAX(ORDER_ID) + 1. Hai session đồng thời có thể đọc cùng một MAX và tạo cùng giá trị; transaction chưa commit cũng khiến kết quả không ổn định.

Các yêu cầu thường gặp:
- Khóa chính duy nhất khi nhiều session insert đồng thời.
- Không phải query lại table chỉ để tìm row vừa insert.
- Lấy được ID trong cùng transaction.
- Hỗ trợ batch insert khi cần throughput.
- Không phụ thuộc vào thứ tự commit.
- Quản lý đúng transaction rollback và connection pool.

Oracle cung cấp sequence và identity để sinh số; JDBC cung cấp nhiều cách nhận giá trị đó.

## 2. Oracle sequence

Sequence là schema object tạo ra dãy số theo cấu hình. Sequence độc lập với table: nhiều table có thể dùng chung một sequence, và sequence có thể được gọi mà không cần INSERT.

### 2.1. Tạo sequence

~~~sql
CREATE SEQUENCE order_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 9999999999999999999999999999
    CACHE 100
    NOORDER
    NOCYCLE;
~~~

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| START WITH | Giá trị bắt đầu |
| INCREMENT BY | Bước tăng/giảm |
| MINVALUE / MAXVALUE | Giới hạn dưới/trên |
| CACHE n | Oracle cấp trước một nhóm giá trị trong memory |
| NOCACHE | Không cache một nhóm giá trị sequence |
| ORDER | Bảo đảm thứ tự cấp sequence theo yêu cầu |
| NOORDER | Không yêu cầu thứ tự toàn cục giữa các request |
| CYCLE | Quay vòng khi chạm giới hạn |
| NOCYCLE | Không quay vòng; lỗi khi hết giới hạn |

Đối với khóa chính tăng dần, cấu hình phổ biến là INCREMENT BY 1, NOCYCLE và CACHE với kích thước phù hợp workload.

### 2.2. Lấy NEXTVAL

~~~sql
SELECT order_seq.NEXTVAL
FROM dual;
~~~

Mỗi lần gọi NEXTVAL, Oracle cấp một giá trị mới. Giá trị đó được tăng độc lập với transaction commit/rollback.

Có thể dùng trực tiếp trong INSERT:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (order_seq.NEXTVAL, :customer_id, 'NEW');
~~~

Không cần gọi SELECT trước nếu ứng dụng không cần biết ID trước khi insert.

### 2.3. Lấy CURRVAL

Sau khi session đã gọi NEXTVAL, có thể lấy giá trị gần nhất được cấp cho sequence trong chính session đó:

~~~sql
SELECT order_seq.CURRVAL
FROM dual;
~~~

CURRVAL là trạng thái theo session. Nếu session chưa gọi NEXTVAL cho sequence trong session hiện tại, Oracle báo ORA-08002.

Trong JDBC, cần thực hiện NEXTVAL và CURRVAL trên cùng một physical database session. Khi dùng connection pool, một lần getConnection() giữ một connection trong suốt transaction; không đóng connection rồi lấy connection mới để query CURRVAL.

### 2.4. NEXTVAL và CURRVAL trong một INSERT

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (order_seq.NEXTVAL, :customer_id, 'NEW');

SELECT order_seq.CURRVAL FROM dual;
~~~

Hai câu lệnh phải chạy trên cùng connection/session. Giá trị CURRVAL là ID được cấp cho session đó, không bị ảnh hưởng bởi session khác gọi NEXTVAL xen kẽ.

### 2.5. Không dùng MAX(id) + 1

Cách không an toàn:

~~~sql
SELECT NVL(MAX(order_id), 0) + 1
FROM orders;
~~~

Sau đó dùng kết quả để INSERT.

Hai transaction có thể cùng đọc một giá trị MAX và cùng tạo ID kế tiếp. Unique constraint sẽ khiến ít nhất một transaction lỗi. Nếu bỏ unique constraint, dữ liệu có thể bị trùng khóa.

Sequence được Oracle thiết kế cho concurrency; không cần lock table để phát số.

### 2.6. Sequence không gapless

Sequence bảo đảm giá trị được cấp không bị trùng trong phạm vi cấu hình, nhưng không bảo đảm dãy số liên tục không có khoảng trống.

Khoảng trống có thể xuất hiện khi:
- Transaction lấy NEXTVAL rồi rollback.
- Ứng dụng lấy NEXTVAL nhưng không insert.
- Instance crash làm mất các giá trị đã cache nhưng chưa dùng.
- Sequence được alter/restart hoặc cache được thay đổi.
- Nhiều session lấy giá trị nhưng commit theo thứ tự khác nhau.

Không dùng sequence làm số hóa đơn pháp lý cần liên tục nếu nghiệp vụ yêu cầu gapless numbering. Cần một thiết kế cấp số riêng có serialization, audit và xử lý rollback phù hợp quy định.

### 2.7. CACHE và NOCACHE

CACHE n giúp Oracle cấp trước một nhóm sequence value để giảm overhead khi có nhiều request. Khi instance dừng bất thường, các giá trị đã cache nhưng chưa dùng có thể bị mất, tạo khoảng trống.

NOCACHE giảm số giá trị được cache, nhưng không biến sequence thành gapless. Transaction rollback và các nguyên nhân khác vẫn tạo gap.

Với hệ thống insert nhiều, cache thường có lợi cho throughput. Chọn kích thước cache theo workload, không đặt NOCACHE chỉ vì lo ngại khoảng trống.

### 2.8. ORDER và NOORDER

ORDER yêu cầu sequence cấp giá trị theo thứ tự request. Trong RAC, việc đảm bảo thứ tự toàn cục có thể tăng coordination và ảnh hưởng throughput.

NOORDER không cam kết thứ tự cấp phát toàn cục theo thời gian request giữa các instance; nó vẫn cấp các giá trị khác nhau. Với khóa chính, thường chỉ cần uniqueness chứ không cần ID phản ánh thứ tự thời gian chính xác.

Không suy luận rằng ID lớn hơn luôn có nghĩa transaction commit sau. Sequence allocation order không phải commit order.

### 2.9. CYCLE và NOCYCLE

CYCLE cho phép sequence quay về MINVALUE/MAXVALUE sau khi đạt giới hạn. Với primary key, việc quay vòng có thể gây trùng giá trị nếu các giá trị cũ vẫn tồn tại.

Vì vậy, sequence làm khóa chính thường dùng NOCYCLE. Theo dõi giới hạn và datatype trước khi sequence cạn.

### 2.10. Kiểm tra sequence

~~~sql
SELECT
    sequence_owner,
    sequence_name,
    min_value,
    max_value,
    increment_by,
    cycle_flag,
    order_flag,
    cache_size,
    last_number
FROM all_sequences
WHERE sequence_name = 'ORDER_SEQ';
~~~

LAST_NUMBER trong view không nhất thiết là giá trị cuối cùng đã được ứng dụng dùng; khi cache bật, nó có thể phản ánh ranh giới cache tiếp theo. Không dùng riêng cột này để xác định chính xác ID vừa insert.

### 2.11. Điều chỉnh sequence

Ví dụ thay cache:

~~~sql
ALTER SEQUENCE order_seq CACHE 500;
~~~

Thay increment:

~~~sql
ALTER SEQUENCE order_seq INCREMENT BY 10;
~~~

Thay đổi sequence phải được lên kế hoạch vì ứng dụng có thể đang dựa trên giả định về increment hoặc giới hạn. Không alter sequence production chỉ để lấp gap.

## 3. Identity column trong Oracle

Identity column là cột số mà Oracle tự sinh giá trị khi INSERT không cung cấp giá trị cho cột theo policy đã khai báo. Oracle hỗ trợ identity từ Oracle Database 12c trở lên; Oracle 19c hỗ trợ đầy đủ các dạng thường dùng.

Identity column giúp đơn giản hóa schema vì không cần tạo sequence và trigger thủ công cho mỗi table.

### 3.1. GENERATED ALWAYS AS IDENTITY

~~~sql
CREATE TABLE customers (
    customer_id NUMBER
        GENERATED ALWAYS AS IDENTITY,
    customer_name VARCHAR2(200) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT customers_pk PRIMARY KEY (customer_id)
);
~~~

Với GENERATED ALWAYS, Oracle luôn tự tạo giá trị identity. Ứng dụng không được tự cung cấp giá trị cho cột identity trong INSERT thông thường; cố gắng đưa giá trị tường minh sẽ bị từ chối.

Dùng khi database phải kiểm soát hoàn toàn việc cấp ID.

### 3.2. GENERATED BY DEFAULT AS IDENTITY

~~~sql
CREATE TABLE products (
    product_id NUMBER
        GENERATED BY DEFAULT AS IDENTITY,
    product_name VARCHAR2(200) NOT NULL,
    CONSTRAINT products_pk PRIMARY KEY (product_id)
);
~~~

Nếu INSERT không chỉ định PRODUCT_ID, Oracle tự sinh. Nếu ứng dụng chỉ định giá trị, Oracle chấp nhận giá trị được cung cấp.

Dạng này hữu ích khi cần import dữ liệu cũ giữ nguyên ID, nhưng phải kiểm soát nguy cơ giá trị tường minh va chạm với các ID sẽ được sinh sau đó.

### 3.3. GENERATED BY DEFAULT ON NULL AS IDENTITY

~~~sql
CREATE TABLE invoices (
    invoice_id NUMBER
        GENERATED BY DEFAULT ON NULL AS IDENTITY,
    invoice_number VARCHAR2(40) NOT NULL,
    CONSTRAINT invoices_pk PRIMARY KEY (invoice_id)
);
~~~

Dạng này cho phép cung cấp ID tường minh; nếu giá trị không được cung cấp hoặc là NULL, Oracle tự sinh identity.

Khác biệt quan trọng:
- BY DEFAULT: giá trị NULL được đưa tường minh không kích hoạt cơ chế sinh identity như ON NULL.
- BY DEFAULT ON NULL: khi giá trị tường minh là NULL, Oracle sinh giá trị identity.

### 3.4. Cấu hình identity sequence

Có thể chỉ định option cho sequence nội bộ:

~~~sql
CREATE TABLE events (
    event_id NUMBER
        GENERATED ALWAYS AS IDENTITY
        (START WITH 1000 INCREMENT BY 1 CACHE 100 NOCYCLE),
    event_type VARCHAR2(100) NOT NULL
);
~~~

Oracle quản lý sequence nội bộ phục vụ identity. Tên nội bộ thường có dạng ISEQ$$_...; không dựa vào tên đó trong ứng dụng và không alter/drop sequence nội bộ như object nghiệp vụ.

### 3.5. Identity và primary key

Identity chỉ quy định cách Oracle sinh giá trị. Nó không tự thay thế mọi ràng buộc dữ liệu. Nên khai báo PRIMARY KEY hoặc UNIQUE constraint để database bảo đảm tính duy nhất.

Ví dụ:

~~~sql
CREATE TABLE departments (
    department_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    department_name VARCHAR2(100) NOT NULL,
    CONSTRAINT departments_pk PRIMARY KEY (department_id)
);
~~~

### 3.6. Kiểm tra identity metadata

~~~sql
SELECT
    table_name,
    column_name,
    generation_type,
    identity_options
FROM user_tab_identity_cols
ORDER BY table_name, column_name;
~~~

View USER_TAB_IDENTITY_COLS cho biết cột identity và generation type. Có thể dùng ALL_TAB_IDENTITY_COLS hoặc DBA_TAB_IDENTITY_COLS theo quyền.

### 3.7. Khi nào dùng sequence, khi nào dùng identity?

| Nhu cầu | Sequence | Identity |
| --- | --- | --- |
| Tạo khóa chính cho một table | Phù hợp | Rất phù hợp |
| Một sequence dùng chung nhiều table | Có | Không phải mục tiêu chính |
| Lấy ID trước khi INSERT | Dễ dàng qua NEXTVAL | Thường lấy sau INSERT |
| Kiểm soát object sequence độc lập | Có | Oracle quản lý sequence nội bộ |
| Schema đơn giản, ít boilerplate | Cần sequence và dùng trong DML | Gọn hơn |
| Import ID tường minh | Dùng được | Phụ thuộc ALWAYS/BY DEFAULT |
| Tích hợp legacy trigger | Phổ biến | Có thể cần thay đổi migration |

Chọn identity cho table mới nếu muốn database quản lý ID ngay trong định nghĩa cột. Chọn sequence khi cần dùng chung, cần lấy ID trước INSERT hoặc phải tương thích schema/ứng dụng legacy.

## 4. INSERT và lấy ID bằng JDBC

JDBC có một số cách lấy giá trị được database sinh sau INSERT. Cách phù hợp phụ thuộc schema, Oracle JDBC driver và nhu cầu batch.

### 4.1. Dùng sequence NEXTVAL trong INSERT

Đây là cách tương thích rõ ràng với schema dùng sequence:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (order_seq.NEXTVAL, ?, ?)
~~~

Java:

~~~java
String sql = """
    INSERT INTO orders (order_id, customer_id, status)
    VALUES (order_seq.NEXTVAL, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setString(2, "NEW");

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new SQLException("Expected one inserted order, got " + rows);
    }
}
~~~

Cách này chưa trả ID về Java. Nếu cần ID, có thể query CURRVAL trên cùng connection sau INSERT hoặc dùng JDBC generated keys/RETURNING.

### 4.2. SELECT NEXTVAL trước rồi INSERT

Khi ứng dụng cần biết ID trước khi insert (ví dụ tạo object domain hoặc ghi row phụ thuộc), lấy sequence value trước:

~~~sql
SELECT order_seq.NEXTVAL FROM dual
~~~

Java:

~~~java
long orderId;

try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT order_seq.NEXTVAL FROM dual");
     ResultSet rs = ps.executeQuery()) {

    if (!rs.next()) {
        throw new SQLException("Sequence did not return a value");
    }
    orderId = rs.getLong(1);
}

String insertSql = """
    INSERT INTO orders (order_id, customer_id, status)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(insertSql)) {
    ps.setLong(1, orderId);
    ps.setLong(2, customerId);
    ps.setString(3, "NEW");
    ps.executeUpdate();
}
~~~

Hai thao tác phải nằm trên cùng Connection nếu muốn quản lý cùng transaction. Sequence allocation không rollback; nếu INSERT thất bại, ID đã lấy vẫn bị tiêu thụ.

### 4.3. INSERT rồi SELECT CURRVAL

Nếu SQL INSERT dùng order_seq.NEXTVAL, có thể query:

~~~sql
SELECT order_seq.CURRVAL FROM dual
~~~

Java:

~~~java
long orderId;

try (PreparedStatement insert = connection.prepareStatement("""
        INSERT INTO orders (order_id, customer_id, status)
        VALUES (order_seq.NEXTVAL, ?, ?)
        """)) {

    insert.setLong(1, customerId);
    insert.setString(2, "NEW");
    insert.executeUpdate();
}

try (PreparedStatement current = connection.prepareStatement(
        "SELECT order_seq.CURRVAL FROM dual");
     ResultSet rs = current.executeQuery()) {

    if (!rs.next()) {
        throw new SQLException("CURRVAL was not returned");
    }
    orderId = rs.getLong(1);
}
~~~

Không lấy CURRVAL qua connection khác. Với connection pool, giữ cùng connection từ INSERT tới query CURRVAL.

## 5. JDBC getGeneratedKeys()

JDBC cung cấp Statement.RETURN_GENERATED_KEYS và PreparedStatement.getGeneratedKeys() để đọc giá trị được sinh bởi INSERT. Oracle JDBC driver hỗ trợ generated keys, nhưng cách xác định cột cần trả về phải được cấu hình rõ ràng và kiểm thử với driver version đang chạy.

### 5.1. Dùng cờ RETURN_GENERATED_KEYS

Ví dụ chuẩn JDBC:

~~~java
String sql = """
    INSERT INTO customers (customer_name)
    VALUES (?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, "An Nguyen");

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new SQLException("Expected one inserted customer");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("No generated key returned");
        }

        long customerId = keys.getLong(1);
        System.out.println("customerId=" + customerId);
    }
}
~~~

Với Oracle JDBC, cách dùng cờ chung có thể trả về ROWID hoặc hành vi phụ thuộc driver nếu không chỉ định cột generated key. Khi cần giá trị primary key, hãy yêu cầu rõ tên cột thay vì giả định cột đầu tiên là ID.

### 5.2. Chỉ định cột cần trả về

~~~java
String sql = """
    INSERT INTO customers (customer_name)
    VALUES (?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, new String[] {"CUSTOMER_ID"})) {

    ps.setString(1, "An Nguyen");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("No CUSTOMER_ID returned");
        }

        long customerId = keys.getLong("CUSTOMER_ID");
    }
}
~~~

Tên cột cần khớp metadata mà Oracle JDBC driver nhận diện; thường dùng tên cột không quote theo uppercase. Nếu driver hoặc schema dùng quoted identifier/case-sensitive name, xác minh theo metadata và test integration.

### 5.3. Generated keys với identity column

Ví dụ table:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER GENERATED ALWAYS AS IDENTITY,
    customer_name VARCHAR2(200) NOT NULL,
    CONSTRAINT customers_pk PRIMARY KEY (customer_id)
);
~~~

JDBC insert chỉ cung cấp tên:

~~~java
String sql = "INSERT INTO customers (customer_name) VALUES (?)";

try (PreparedStatement ps = connection.prepareStatement(
        sql, new String[] {"CUSTOMER_ID"})) {

    ps.setString(1, "An Nguyen");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("Oracle did not return CUSTOMER_ID");
        }
        long customerId = keys.getLong(1);
    }
}
~~~

Đây là mẫu cần xác minh với đúng ojdbc artifact và database release. Nếu driver không trả cột như mong muốn, dùng Oracle DML RETURNING hoặc sequence/CURRVAL theo thiết kế.

### 5.4. Đọc kiểu dữ liệu đúng

Nếu khóa là NUMBER và giá trị nằm trong phạm vi Java long, có thể dùng getLong. Nếu NUMBER có độ lớn/scale khác, dùng BigDecimal:

~~~java
BigDecimal generatedId = keys.getBigDecimal(1);
~~~

Không dùng getInt cho khóa có thể vượt giới hạn 32-bit. Kiểm tra wasNull() nếu cột trả về có thể NULL.

### 5.5. Đóng ResultSet

getGeneratedKeys() trả về ResultSet. Đóng nó bằng try-with-resources để giải phóng cursor/resource. Cũng đóng PreparedStatement khi hoàn tất. Không giữ generated-keys ResultSet lâu hơn transaction cần thiết.

## 6. Oracle DML RETURNING INTO từ JDBC

Oracle SQL hỗ trợ RETURNING ... INTO để lấy giá trị của row vừa được INSERT, UPDATE hoặc DELETE. Cú pháp này có thể trả một hay nhiều cột và tránh query lại table.

Ví dụ SQL:

~~~sql
INSERT INTO customers (customer_id, customer_name)
VALUES (customer_seq.NEXTVAL, :customer_name)
RETURNING customer_id INTO :generated_id;
~~~

Trong SQL*Plus/PLSQL, bind variable có thể được dùng theo cách riêng. Trong JDBC, Oracle cung cấp API mở rộng trên OraclePreparedStatement.

### 6.1. Khái niệm registerReturnParameter

Với Oracle JDBC, quy trình tổng quát:
1. Tạo OraclePreparedStatement cho DML có RETURNING ... INTO ?.
2. Đăng ký kiểu SQL của bind output bằng registerReturnParameter.
3. Gán các bind input.
4. Gọi executeUpdate().
5. Lấy ResultSet bằng getReturnResultSet().
6. Đọc giá trị được trả về và đóng result set.

### 6.2. Ví dụ INSERT RETURNING

~~~java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

import oracle.jdbc.OraclePreparedStatement;

String sql = """
    INSERT INTO customers (customer_id, customer_name)
    VALUES (customer_seq.NEXTVAL, ?)
    RETURNING customer_id INTO ?
    """;

try (OraclePreparedStatement ps =
         (OraclePreparedStatement) connection.prepareStatement(sql)) {

    ps.setString(1, "An Nguyen");
    ps.registerReturnParameter(2, Types.NUMERIC);

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new SQLException("Expected one inserted customer");
    }

    try (ResultSet returned = ps.getReturnResultSet()) {
        if (!returned.next()) {
            throw new SQLException("RETURNING produced no value");
        }

        long customerId = returned.getLong(1);
    }
}
~~~

Đây là Oracle-specific API, không phải API portable cho mọi JDBC driver. Import class oracle.jdbc.OraclePreparedStatement và dùng ojdbc tương thích với Java runtime.

### 6.3. Trả nhiều cột

Ví dụ SQL:

~~~sql
INSERT INTO customers (customer_id, customer_name)
VALUES (customer_seq.NEXTVAL, ?)
RETURNING customer_id, created_at INTO ?, ?
~~~

Đăng ký từng output parameter theo vị trí và kiểu SQL:

~~~java
ps.registerReturnParameter(2, Types.NUMERIC);
ps.registerReturnParameter(3, Types.TIMESTAMP);
~~~

Sau executeUpdate, đọc hai cột từ getReturnResultSet(). Vị trí bind output phải khớp thứ tự trong RETURNING INTO. Kiểu SQL phải phù hợp cột trả về.

### 6.4. UPDATE RETURNING

Ví dụ:

~~~sql
UPDATE orders
SET status = ?
WHERE order_id = ?
RETURNING status, updated_at INTO ?, ?
~~~

Dùng RETURNING để lấy trạng thái và timestamp sau update mà không cần SELECT lại row. Nếu UPDATE tác động nhiều row, cần kiểm tra semantics/API trả về của driver và câu lệnh; ví dụ một-row update dễ kiểm soát hơn.

### 6.5. DELETE RETURNING

Oracle cũng cho phép trả giá trị trước khi row bị xóa:

~~~sql
DELETE FROM orders
WHERE order_id = ?
RETURNING order_id, status INTO ?, ?
~~~

Ứng dụng có thể ghi audit/event từ các giá trị trả về. Kiểm tra số row bị xóa và quyền transaction trước khi commit.

### 6.6. Giới hạn và tính tương thích

- OraclePreparedStatement là extension của Oracle, tạo dependency vào Oracle JDBC.
- API/cách bind output cần kiểm tra theo ojdbc version.
- DML RETURNING có giới hạn với một số kiểu DML, trigger, view và cấu trúc table; xem SQL Language Reference.
- Nếu một statement tác động nhiều row, khả năng trả nhiều dòng phụ thuộc loại DML và API/driver; không mặc định ví dụ single-row hoạt động y hệt.
- Với portable application, cân nhắc JDBC generated keys hoặc query sequence theo cùng connection.

Không cast PreparedStatement tùy tiện nếu connection/driver không phải Oracle. Dùng connection.prepareStatement từ Oracle JDBC implementation và xác minh driver thực tế.

## 7. So sánh các cách lấy generated ID

| Cách | Cần Oracle-specific API? | Lấy ID trước INSERT? | Query bổ sung? | Điểm cần lưu ý |
| --- | --- | --- | --- | --- |
| SELECT sequence.NEXTVAL rồi INSERT | Không | Có | Không cần query sau | Cùng connection/transaction |
| INSERT sequence.NEXTVAL rồi SELECT CURRVAL | Không | Không | Có | CURRVAL theo session |
| JDBC getGeneratedKeys | Không ở API; behavior phụ thuộc driver | Không | Không | Chỉ định cột key rõ ràng |
| Oracle RETURNING INTO | Có | Không | Không | OraclePreparedStatement extension |
| Identity + getGeneratedKeys | API JDBC; phụ thuộc ojdbc | Không | Không | Kiểm thử cột được trả về |
| Identity + RETURNING INTO | Có | Không | Không | Dùng Oracle-specific API |

Lựa chọn thực tế:
- Ứng dụng cần ID trước INSERT: lấy sequence NEXTVAL.
- Schema dùng sequence và muốn portable code: dùng NEXTVAL rồi CURRVAL trên cùng connection.
- Table dùng identity và driver hỗ trợ tốt: dùng getGeneratedKeys với tên cột rõ ràng.
- Cần lấy nhiều cột sau DML hoặc muốn tránh SELECT tiếp theo: dùng Oracle RETURNING INTO.
- Dùng framework ORM: kiểm tra dialect/generator strategy mà framework hỗ trợ thay vì tự trộn nhiều cơ chế.

## 8. Transaction và connection pool

### 8.1. Sequence allocation không thuộc transaction rollback

Ví dụ:
1. Session lấy order_seq.NEXTVAL = 101.
2. INSERT row với ID 101.
3. Transaction rollback.

Row bị rollback nhưng sequence không quay lại 101. Lần tiếp theo có thể nhận 102.

Đây là hành vi bình thường và cần được tính vào thiết kế nghiệp vụ.

### 8.2. Nhiều statement trong cùng transaction

Ví dụ Java:

~~~java
connection.setAutoCommit(false);

try {
    long orderId = nextOrderId(connection);

    insertOrder(connection, orderId, customerId);
    insertOrderItems(connection, orderId, items);

    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
~~~

Các thao tác INSERT order và INSERT order_items dùng chung ID và cùng transaction. Nếu một bước thất bại, rollback dữ liệu nhưng sequence value vẫn đã tiêu thụ.

### 8.3. CURRVAL và pooled connection

CURRVAL thuộc session Oracle, không thuộc Java thread hay transaction object trừu tượng. Connection pool có thể cấp physical connection khác sau khi connection trước được trả về pool.

Vì vậy:
- Lấy NEXTVAL/INSERT/CURRVAL trên cùng Connection đang giữ.
- Không close connection giữa các bước.
- Không lưu CURRVAL trong static field để chia sẻ giữa request.
- Không gọi sequence trên connection A rồi CURRVAL trên connection B.

### 8.4. Generated keys và commit

Generated key có thể được đọc sau executeUpdate trước commit. Giá trị ID đã được cấp nhưng row chưa trở thành dữ liệu committed cho session khác. Chỉ commit mới xác nhận transaction.

Nếu gửi ID ra message queue/API trước commit và transaction rollback, hệ thống khác có thể nhận một ID không có row tương ứng. Dùng transaction boundary/outbox pattern nếu cần phát event đồng bộ với commit.

## 9. Batch insert

Batch insert giúp giảm round trip khi cần insert nhiều row. Cách lấy generated keys cho batch có khác biệt theo driver và DML strategy.

### 9.1. Batch với sequence trong SQL

~~~java
String sql = """
    INSERT INTO order_items (item_id, order_id, product_id, quantity)
    VALUES (order_item_seq.NEXTVAL, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderItem item : items) {
        ps.setLong(1, orderId);
        ps.setLong(2, item.productId());
        ps.setInt(3, item.quantity());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

Đây là cách đơn giản khi không cần trả từng generated ID về Java. Nếu cần ID từng row, cần lựa chọn API/driver hỗ trợ và kiểm tra mapping giữa batch result và key result.

### 9.2. Lấy sequence range trước batch

Một cách khác là lấy NEXTVAL nhiều lần rồi gán ID vào object Java trước khi batch insert. Có thể gọi sequence nhiều lần hoặc dùng SQL lấy nhiều giá trị theo kỹ thuật phù hợp. Không giả định các giá trị liên tiếp sẽ luôn phản ánh thứ tự commit.

### 9.3. Generated keys trong batch

JDBC định nghĩa generated keys, nhưng khả năng batch key retrieval phụ thuộc driver. Test:
- Số key trả về có khớp số row insert không.
- Thứ tự key có khớp thứ tự batch không.
- Batch có phần tử lỗi hay không.
- Driver có trả key cho từng row khi batch update không.

Nếu không có bảo đảm cần thiết, dùng sequence explicit và giữ ID trong application object để mapping chắc chắn.

## 10. Sequence và identity trong migration

### 10.1. Import dữ liệu có ID tường minh

Nếu import table dùng identity:
- GENERATED ALWAYS có thể từ chối insert ID tường minh trong một số thao tác import thông thường.
- GENERATED BY DEFAULT cho phép cung cấp ID.
- GENERATED BY DEFAULT ON NULL tự sinh khi giá trị được import là NULL.

Data Pump có các tùy chọn transform và metadata handling theo release; kiểm tra hành vi identity cụ thể trước migration. Không sửa internal sequence ISEQ$$_... trực tiếp.

### 10.2. Đồng bộ sequence sau import

Nếu import dữ liệu giữ nguyên ID lớn hơn sequence hiện tại, lần insert mới có thể va chạm primary key. Cần xác định giá trị tối đa đã import và đưa sequence tiếp tục từ một giá trị an toàn bằng quy trình được hỗ trợ.

Không chỉ chạy ALTER SEQUENCE ... INCREMENT BY ... trong production mà không tính concurrency. Trong lúc đồng bộ, phải ngăn các session khác cấp sequence hoặc thực hiện change window có kiểm soát.

### 10.3. Identity sau import

Identity column có sequence nội bộ. Sau Data Pump import, xác minh:
- Column generation type.
- Identity options.
- Giá trị mới được sinh có lớn hơn ID đã nạp.
- Primary key/unique constraint hợp lệ.
- Trigger cũ không còn sinh ID trùng.
- Ứng dụng không đồng thời cung cấp ID tường minh ngoài policy.

### 10.4. Không giả định ID liên tục sau migration

Nếu migration import giữ ID gốc, có thể có gap. Nếu sequence được điều chỉnh, giá trị kế tiếp có thể nhảy. ID là surrogate key; không dùng nó để suy ra số lượng bản ghi hoặc thứ tự nghiệp vụ.

## 11. Trigger-based sequence generator trong schema legacy

Trước khi identity column phổ biến, Oracle thường dùng sequence và BEFORE INSERT trigger.

Ví dụ:

~~~sql
CREATE SEQUENCE employee_seq START WITH 1 INCREMENT BY 1 CACHE 100 NOCYCLE;

CREATE OR REPLACE TRIGGER employees_bir
BEFORE INSERT ON employees
FOR EACH ROW
WHEN (NEW.employee_id IS NULL)
BEGIN
    :NEW.employee_id := employee_seq.NEXTVAL;
END;
/
~~~

Ứng dụng INSERT không truyền EMPLOYEE_ID; trigger gán NEXTVAL.

Điểm cần lưu ý:
- Trigger chỉ chạy khi DML đi qua table và trigger enabled.
- Nếu ứng dụng truyền ID khác NULL, điều kiện WHEN có thể bỏ qua generator.
- Trigger có thể che giấu logic cấp ID khỏi SQL của ứng dụng.
- Khi import/migration, trigger và sequence phải được đồng bộ.
- Không tạo thêm identity/trigger generator cùng lúc cho một cột nếu không thiết kế rõ.

Với schema mới, identity thường gọn hơn. Với schema legacy hoặc cần sequence dùng chung, sequence + trigger vẫn là mô hình hợp lệ.

## 12. JDBC type mapping và null handling

### 12.1. NUMBER và Java type

| Oracle SQL | Java/JDBC thường dùng |
| --- | --- |
| NUMBER(10,0) | long hoặc BigDecimal |
| NUMBER(p,s) | BigDecimal khi cần giữ precision/scale |
| TIMESTAMP | Timestamp hoặc LocalDateTime theo driver/API |
| VARCHAR2 | String |
| RAW | byte[] |

Với generated key NUMBER lớn, ưu tiên BigDecimal nếu không chắc giá trị nằm trong long. Tránh ép kiểu hẹp gây overflow.

### 12.2. Đọc NULL

ResultSet.getLong() trả 0 nếu SQL value NULL; gọi wasNull() để phân biệt NULL với giá trị 0:

~~~java
long id = rs.getLong(1);
if (rs.wasNull()) {
    throw new SQLException("Generated key is NULL");
}
~~~

Khóa chính không nên NULL, nhưng kiểm tra giúp phát hiện lỗi mapping/driver sớm.

### 12.3. Bind variable

Dùng PreparedStatement bind variable cho input. Không nối chuỗi user input vào SQL. Với RETURNING output, đăng ký đúng JDBC type cho từng vị trí bind.

## 13. Ví dụ repository JDBC hoàn chỉnh

Ví dụ dưới đây minh họa identity column + generated key. Phần transaction do service quản lý để có thể kết hợp nhiều thao tác.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public final class CustomerRepository {
    private static final String INSERT_SQL = """
        INSERT INTO customers (customer_name)
        VALUES (?)
        """;

    public long insert(Connection connection, String customerName)
            throws SQLException {

        try (PreparedStatement ps = connection.prepareStatement(
                INSERT_SQL, new String[] {"CUSTOMER_ID"})) {

            ps.setString(1, customerName);

            int affected = ps.executeUpdate();
            if (affected != 1) {
                throw new SQLException(
                    "Expected one inserted customer, got " + affected);
            }

            try (ResultSet keys = ps.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException(
                        "Oracle JDBC returned no CUSTOMER_ID");
                }

                long id = keys.getLong(1);
                if (keys.wasNull()) {
                    throw new SQLException("CUSTOMER_ID was NULL");
                }
                return id;
            }
        }
    }
}
~~~

Service điều khiển transaction:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        long customerId =
            customerRepository.insert(connection, "An Nguyen");

        addressRepository.insertDefaultAddress(connection, customerId);

        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

Trong production, thêm policy cho rollback exception, transaction timeout, logging và exception translation theo framework. Không log dữ liệu nhạy cảm hoặc password.

## 14. Lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| ORA-08002 | Gọi CURRVAL trước NEXTVAL trong session | Gọi NEXTVAL trước trên cùng session |
| ORA-08004 | Sequence đạt giới hạn NOCYCLE | Xem MAXVALUE/INCREMENT và lập kế hoạch mở rộng |
| ORA-00001 | ID trùng primary key | Kiểm tra sequence đã sync sau import hoặc ứng dụng truyền ID |
| Generated keys không có row | Driver không trả key theo cách yêu cầu | Chỉ định tên cột hoặc dùng RETURNING/sequence |
| Generated key là ROWID | Driver dùng default generated-key behavior | Truyền columnNames trong prepareStatement |
| ClassCastException với OraclePreparedStatement | Driver/connection không phải Oracle implementation tương thích | Kiểm tra ojdbc và connection provider |
| RETURNING ResultSet rỗng | Bind output sai vị trí/type hoặc DML không tác động row | Kiểm tra SQL, registerReturnParameter và affected rows |
| Sequence có gap | Rollback, cache loss hoặc giá trị đã cấp nhưng không insert | Đây là hành vi bình thường; không dùng sequence làm gapless counter |
| ID không theo thứ tự commit | NEXTVAL allocation và commit order khác nhau | Dùng timestamp/business ordering riêng |
| ORA-00942 khi SELECT sequence | Sequence không tồn tại hoặc thiếu quyền | Kiểm tra owner, synonym và SELECT privilege |
| Identity insert bị từ chối | GENERATED ALWAYS nhưng ứng dụng truyền ID | Bỏ cột khỏi INSERT hoặc đổi policy có kiểm soát |
| Identity import bị trùng ID | Internal generator không tiếp tục sau giá trị đã import | Xác minh identity metadata và điều chỉnh theo quy trình |
| Batch key count không khớp | Driver hỗ trợ batch generated keys khác nhau | Kiểm thử driver; dùng explicit sequence nếu cần mapping chắc chắn |

## 15. Checklist thiết kế

### Database
- Chọn sequence hay identity theo yêu cầu.
- Có PRIMARY KEY/UNIQUE constraint.
- Chọn CACHE/NOCACHE phù hợp throughput.
- Thường dùng NOCYCLE cho primary key.
- Không dựa vào ID để biểu diễn thứ tự commit.
- Kiểm tra giới hạn sequence và identity metadata.
- Có quy trình đồng bộ generator sau import.

### JDBC
- Dùng PreparedStatement và bind variables.
- Chọn getGeneratedKeys, RETURNING hoặc sequence/CURRVAL.
- Với Oracle generated keys, chỉ định tên cột cần lấy.
- Kiểm tra ojdbc version và Java compatibility.
- Đọc generated value đúng kiểu dữ liệu.
- Đóng ResultSet/Statement.
- Giữ cùng connection khi dùng CURRVAL.
- Quản lý transaction và rollback rõ ràng.

### Migration và vận hành
- Xác định identity generation type.
- Kiểm tra trigger/sequence legacy.
- Đối chiếu MAX(ID) với generator state sau import.
- Test insert tiếp theo sau migration.
- Kiểm tra unique constraint và invalid objects.
- Không thao tác trực tiếp internal identity sequence.
- Test batch insert và connection pool.

## 16. Lab: sequence và JDBC CURRVAL

### Bước 1: Tạo table và sequence

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    description VARCHAR2(100) NOT NULL
);

CREATE SEQUENCE lab_order_seq
    START WITH 1 INCREMENT BY 1 CACHE 20 NOCYCLE;
~~~

### Bước 2: Lấy NEXTVAL

~~~sql
SELECT lab_order_seq.NEXTVAL FROM dual;
SELECT lab_order_seq.CURRVAL FROM dual;
~~~

Chạy CURRVAL trước NEXTVAL trong session mới để quan sát ORA-08002.

### Bước 3: Insert và lấy CURRVAL

~~~sql
INSERT INTO lab_orders (order_id, description)
VALUES (lab_order_seq.NEXTVAL, 'First order');

SELECT lab_order_seq.CURRVAL FROM dual;
~~~

Thực hiện cả hai trên cùng session.

### Bước 4: Thử rollback

~~~sql
SAVEPOINT before_insert;
INSERT INTO lab_orders (order_id, description)
VALUES (lab_order_seq.NEXTVAL, 'Rollback sample');
ROLLBACK TO before_insert;
SELECT lab_order_seq.NEXTVAL FROM dual;
~~~

Quan sát sequence không quay lui theo rollback.

### Bước 5: Thử hai session

Mở hai SQL session và gọi NEXTVAL luân phiên. Xác nhận mỗi session nhận giá trị khác nhau; CURRVAL của mỗi session phản ánh NEXTVAL cuối cùng của chính session đó.

## 17. Lab: identity và generated keys

### Bước 1: Tạo table identity

~~~sql
CREATE TABLE lab_customers (
    customer_id NUMBER
        GENERATED BY DEFAULT ON NULL AS IDENTITY,
    customer_name VARCHAR2(100) NOT NULL,
    CONSTRAINT lab_customers_pk PRIMARY KEY (customer_id)
);
~~~

### Bước 2: Insert không cung cấp ID

~~~sql
INSERT INTO lab_customers (customer_name)
VALUES ('Customer A');

SELECT * FROM lab_customers;
~~~

### Bước 3: Thử NULL và giá trị tường minh

~~~sql
INSERT INTO lab_customers (customer_id, customer_name)
VALUES (NULL, 'Customer B');

INSERT INTO lab_customers (customer_id, customer_name)
VALUES (9000, 'Imported Customer');
~~~

Xác nhận BY DEFAULT ON NULL sinh ID khi NULL, còn giá trị tường minh được chấp nhận.

### Bước 4: Kiểm tra metadata

~~~sql
SELECT
    table_name,
    column_name,
    generation_type,
    identity_options
FROM user_tab_identity_cols
WHERE table_name = 'LAB_CUSTOMERS';
~~~

### Bước 5: Chạy JDBC generated keys

Dùng Java repository ở mục 13, đổi table/column thành LAB_CUSTOMERS/CUSTOMER_ID. Xác nhận getGeneratedKeys() trả đúng ID với ojdbc đang dùng.

## 18. Lab: Oracle RETURNING INTO

### Bước 1: Tạo table và sequence

~~~sql
CREATE TABLE lab_returning (
    id NUMBER PRIMARY KEY,
    label VARCHAR2(100),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE SEQUENCE lab_returning_seq START WITH 1 CACHE 20 NOCYCLE;
~~~

### Bước 2: INSERT RETURNING

Dùng OraclePreparedStatement:

~~~java
String sql = """
    INSERT INTO lab_returning (id, label)
    VALUES (lab_returning_seq.NEXTVAL, ?)
    RETURNING id, created_at INTO ?, ?
    """;

try (OraclePreparedStatement ps =
         (OraclePreparedStatement) connection.prepareStatement(sql)) {

    ps.setString(1, "returning-demo");
    ps.registerReturnParameter(2, Types.NUMERIC);
    ps.registerReturnParameter(3, Types.TIMESTAMP);

    ps.executeUpdate();

    try (ResultSet rs = ps.getReturnResultSet()) {
        if (rs.next()) {
            long id = rs.getLong(1);
            Timestamp createdAt = rs.getTimestamp(2);
        }
    }
}
~~~

Kiểm tra đúng phiên bản Oracle JDBC driver và API signature. Nếu driver không hỗ trợ cách bind này, dùng getGeneratedKeys hoặc sequence/CURRVAL.

### Bước 3: UPDATE RETURNING

Thay label hoặc cập nhật status, dùng RETURNING để đọc giá trị sau update. Kiểm tra số row affected và kết quả trả về.

### Bước 4: Transaction

Thử commit và rollback. Xác nhận RETURNING trả giá trị trong transaction hiện tại nhưng rollback vẫn loại bỏ row; sequence allocation không được hoàn lại.

## 19. Dọn dẹp lab

~~~sql
DROP TABLE lab_orders PURGE;
DROP SEQUENCE lab_order_seq;

DROP TABLE lab_customers PURGE;

DROP TABLE lab_returning PURGE;
DROP SEQUENCE lab_returning_seq;
~~~

Chỉ chạy cleanup trên schema lab. Không xóa sequence/table đang được ứng dụng dùng chung.

## Tổng kết

Sequence là object độc lập của Oracle, thích hợp khi cần kiểm soát việc cấp số, dùng chung giữa nhiều table hoặc lấy ID trước INSERT. Identity column đơn giản hóa schema bằng cách để Oracle tự sinh giá trị cho một cột. Cả hai đều không bảo đảm dãy số liên tục không gap; sequence allocation không rollback cùng transaction và thứ tự cấp số không phải thứ tự commit.

JDBC có thể lấy generated key qua getGeneratedKeys(). Với Oracle, chỉ định rõ tên cột cần trả về và kiểm thử trên ojdbc thực tế vì default behavior có thể không trả primary key như ứng dụng mong đợi. Oracle DML RETURNING ... INTO có thể trả nhiều giá trị sau INSERT/UPDATE/DELETE thông qua OraclePreparedStatement extension. Nếu dùng CURRVAL, phải gọi sau NEXTVAL trên cùng Oracle session/connection.

Chọn một cơ chế nhất quán theo schema và framework. Quản lý sequence/identity sau migration, test batch và connection pool, dùng bind variables, đóng resource và điều khiển transaction rõ ràng. Không dùng MAX(id)+1 và không dùng sequence làm bộ đếm gapless cho chứng từ nghiệp vụ.

## Tài liệu Oracle và JDBC tham khảo

- [Oracle Database SQL Language Reference — CREATE SEQUENCE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SEQUENCE.html) — sequence options, NEXTVAL và CURRVAL.
- [Oracle Database SQL Language Reference — CREATE TABLE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html) — identity column syntax và generation type.
- [Oracle Database SQL Language Reference — INSERT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html) — INSERT và RETURNING clause.
- [Oracle Database JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — Oracle JDBC APIs, generated keys và DML returning.
- [Oracle JDBC API Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/jajdb/) — OraclePreparedStatement, registerReturnParameter và getReturnResultSet.
- [JDBC API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html) — prepareStatement, generated keys và executeUpdate.
- [JDBC API — Statement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html) — RETURN_GENERATED_KEYS.

Khi triển khai trên Oracle release hoặc JDBC driver khác, hãy đối chiếu SQL Language Reference, JDBC Developer's Guide và API Reference đúng phiên bản, đặc biệt identity generation, getGeneratedKeys(), RETURNING INTO, batch update và driver compatibility.
