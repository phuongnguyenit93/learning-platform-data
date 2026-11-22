# Bind tham số đúng kiểu và xử lý giá trị NULL

## 1. Vì sao bind tham số là một phần của SQL an toàn?

Ứng dụng Java thường nhận dữ liệu từ HTTP request, màn hình, message queue hoặc dịch vụ khác rồi gửi SQL tới database. Khi dữ liệu được ghép thẳng vào chuỗi SQL, một dấu nháy hoặc đoạn SQL do người dùng gửi có thể làm thay đổi cấu trúc câu lệnh.

Ví dụ không an toàn:

```java
String sql =
    "SELECT customer_id, full_name " +
    "FROM app.customers " +
    "WHERE email = '" + email + "'";

Statement statement = connection.createStatement();
ResultSet rs = statement.executeQuery(sql);
```

Cách đúng là để SQL và dữ liệu đi theo hai phần riêng:

```java
String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE email = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("customer_id");
            String name = rs.getString("full_name");
        }
    }
}
```

Dấu hỏi là placeholder. Giá trị email được bind riêng bằng setString. Driver gửi giá trị theo giao thức và kiểu dữ liệu phù hợp, để database xử lý nó như **một giá trị**, không phải một mảnh cú pháp SQL.

Bind tham số còn giúp:

- Tránh lỗi dấu nháy và ký tự đặc biệt trong dữ liệu.
- Giảm nguy cơ SQL injection.
- Truyền đúng kiểu dữ liệu và giảm chuyển kiểu ngầm.
- Dùng lại câu lệnh đã chuẩn bị khi phù hợp.
- Xử lý SQL NULL có chủ đích.
- Giữ code dễ đọc, dễ kiểm thử và dễ bảo trì.

**Bind đúng kiểu và xử lý NULL đúng nghĩa là hai kỹ năng khác nhau nhưng luôn đi cùng nhau.** Một câu SQL đã dùng placeholder vẫn có thể sai nếu ứng dụng bind sai kiểu, dùng phép so sánh bằng với NULL, hoặc nhầm lẫn giữa “không gửi bộ lọc” và “tìm những hàng có giá trị NULL”.

## 2. Bộ dữ liệu minh họa

Các ví dụ chính dùng Java JDBC và PostgreSQL làm hệ quản trị minh họa. Phần cuối so sánh MySQL, SQL Server, Oracle và SQLite.

```sql
CREATE SCHEMA app;

CREATE TABLE app.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    birth_date DATE,
    credit_limit NUMERIC(14,2),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO app.customers (
    email, full_name, birth_date, credit_limit, is_active
)
VALUES
    ('an@example.invalid', 'An',
     DATE '1995-04-12', 5000000.00, TRUE),
    ('binh@example.invalid', 'Bình',
     NULL, 2500000.00, TRUE),
    (NULL, 'Chi',
     DATE '2000-09-01', NULL, FALSE);
```

| customer_id | email | full_name | birth_date | credit_limit | is_active |
| ---: | --- | --- | --- | ---: | --- |
| 1 | an@example.invalid | An | 1995-04-12 | 5.000.000 | true |
| 2 | binh@example.invalid | Bình | NULL | 2.500.000 | true |
| 3 | NULL | Chi | 2000-09-01 | NULL | false |

Bảng có nhiều kiểu SQL khác nhau:

- BIGINT: định danh.
- VARCHAR: chuỗi.
- DATE: ngày lịch.
- NUMERIC: số thập phân chính xác.
- BOOLEAN: đúng/sai.
- TIMESTAMPTZ: thời điểm theo ngữ nghĩa múi giờ.

Email, ngày sinh và hạn mức có thể NULL theo schema. Ứng dụng phải bind đúng kiểu và giữ nguyên ý nghĩa của trạng thái chưa có dữ liệu.

## 3. PreparedStatement và placeholder

PreparedStatement là API JDBC dùng để thực thi câu lệnh có tham số.

```java
String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE customer_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 2L);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(
                rs.getLong("customer_id") + " " +
                rs.getString("full_name")
            );
        }
    }
}
```

### 3.1. Vị trí tham số bắt đầu từ 1

Trong JDBC, placeholder đầu tiên là index 1, placeholder thứ hai là index 2. Đây là chỉ số JDBC, không phải chỉ số mảng Java bắt đầu từ 0.

```java
String sql = """
    SELECT customer_id
    FROM app.customers
    WHERE full_name = ?
      AND is_active = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "An");
    ps.setBoolean(2, true);

    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả
    }
}
```

Nếu gán nhầm thứ tự, SQL vẫn có thể chạy nhưng tìm sai dữ liệu hoặc báo lỗi chuyển kiểu.

### 3.2. Mỗi dấu hỏi là một tham số riêng

```sql
SELECT *
FROM app.customers
WHERE full_name = ?
  AND email = ?;
```

Ứng dụng phải bind cả hai vị trí. JDBC không tự hiểu tên biến Java như name hay email.

### 3.3. Không đặt dấu nháy quanh placeholder

Đúng:

```sql
WHERE email = ?
```

Sai:

```sql
WHERE email = '?'
```

Ở dạng sai, dấu hỏi nằm trong literal chuỗi và database coi nó là ký tự hỏi, không phải tham số.

### 3.4. Placeholder không phải phép nối chuỗi

Nếu bind chuỗi O'Connor, driver truyền đúng giá trị có dấu nháy. Không cần tự thay dấu nháy thành hai dấu nháy để chống SQL injection khi dùng PreparedStatement.

Escape vẫn có thể cần cho ngữ nghĩa tìm kiếm LIKE hoặc định dạng dữ liệu riêng; đó là vấn đề khác với tách dữ liệu khỏi cú pháp SQL.

## 4. Chọn setter JDBC đúng kiểu SQL

Nên chọn setter tương ứng với kiểu dữ liệu của cột và ý nghĩa của giá trị.

| Kiểu SQL phổ biến | Kiểu Java phù hợp | Setter thường dùng |
| --- | --- | --- |
| SMALLINT | short / Short | setShort |
| INTEGER | int / Integer | setInt |
| BIGINT | long / Long | setLong |
| NUMERIC / DECIMAL | BigDecimal | setBigDecimal |
| REAL | float / Float | setFloat |
| DOUBLE PRECISION | double / Double | setDouble |
| VARCHAR / TEXT | String | setString |
| BOOLEAN | boolean / Boolean | setBoolean |
| DATE | LocalDate hoặc java.sql.Date | setObject hoặc setDate |
| TIME | LocalTime hoặc java.sql.Time | setObject hoặc setTime |
| TIMESTAMP | LocalDateTime hoặc Timestamp | setObject hoặc setTimestamp |
| TIMESTAMP WITH TIME ZONE | OffsetDateTime tùy driver | setObject |
| BINARY / VARBINARY | byte[] | setBytes |
| BLOB | InputStream | setBinaryStream |
| CLOB | Reader | setCharacterStream |

### 4.1. Kiểu dữ liệu phải khớp cả ý nghĩa

Cột price NUMERIC(14,2) nên nhận BigDecimal, không phải chuỗi hiển thị như “5.000.000 đ”.

Cột birth_date DATE nên nhận LocalDate, không phải chuỗi “12/04/1995” phụ thuộc locale.

Cột customer_id BIGINT nên nhận long/Long, không phải giá trị được ghép vào SQL dưới dạng văn bản.

### 4.2. Tránh dựa vào chuyển kiểu ngầm

Ví dụ:

```java
ps.setString(1, "5000000");
```

cho cột NUMERIC có thể được một DBMS/driver chuyển đổi, nhưng không nên xem đây là hợp đồng tốt. Chuyển kiểu ngầm có thể gây lỗi với chuỗi không hợp lệ, khác biệt giữa DBMS, ảnh hưởng index hoặc khiến kế hoạch thực thi khó dự đoán.

**Bind giá trị bằng kiểu thật của dữ liệu.**

## 5. NUMERIC/DECIMAL: dùng BigDecimal cho tiền

Java double biểu diễn số thực nhị phân. Nhiều số thập phân không thể biểu diễn chính xác dưới dạng nhị phân.

```java
double price = 0.1 + 0.2;
System.out.println(price);
```

Có thể in ra giá trị gần 0.30000000000000004, không phải đúng decimal 0.30.

Với số tiền, dùng BigDecimal:

```java
BigDecimal price = new BigDecimal("1250000.50");

String sql = """
    INSERT INTO app.invoice_lines(amount)
    VALUES (?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, price);
    ps.executeUpdate();
}
```

### 5.1. Khởi tạo BigDecimal từ String

Nên:

```java
BigDecimal amount = new BigDecimal("0.10");
```

Tránh:

```java
BigDecimal amount = new BigDecimal(0.10);
```

Constructor nhận double sẽ đưa sai số biểu diễn nhị phân của double vào BigDecimal.

### 5.2. Kiểm soát scale và rounding

Nếu database dùng NUMERIC(14,2), ứng dụng có thể kiểm tra scale:

```java
BigDecimal amount =
    new BigDecimal("1250.5")
        .setScale(2, RoundingMode.HALF_UP);

ps.setBigDecimal(1, amount);
```

Chính sách làm tròn phải đến từ nghiệp vụ. Không tự chọn HALF_UP nếu quy định kế toán yêu cầu cách khác.

### 5.3. So sánh BigDecimal

BigDecimal.equals xét cả giá trị và scale:

```java
new BigDecimal("1.0").equals(new BigDecimal("1.00"))
```

trả false, trong khi compareTo cho kết quả bằng 0.

Khi kiểm tra bằng nhau theo giá trị số, cân nhắc compareTo:

```java
if (amount.compareTo(new BigDecimal("1.00")) == 0) {
    // Cùng giá trị số
}
```

### 5.4. Đọc lại bằng getBigDecimal

```java
BigDecimal creditLimit =
    rs.getBigDecimal("credit_limit");
```

Nếu cột SQL là NULL, getBigDecimal trả Java null. Không tự thay NULL bằng 0 trừ khi nghiệp vụ định nghĩa rõ hai trạng thái tương đương.

## 6. Chuỗi, UUID và kiểu enum

### 6.1. VARCHAR/TEXT

```java
ps.setString(1, "an@example.invalid");
```

Nếu tham số là null, dùng setNull hoặc setObject có SQL type rõ ràng, không thay bằng chuỗi giả “NULL”.

### 6.2. UUID

Java có java.util.UUID:

```java
UUID customerId = UUID.fromString(
    "7c8f3a6a-4f6d-4a23-a4cb-4d7e8a9b1001"
);

ps.setObject(1, customerId);
```

PostgreSQL JDBC hỗ trợ UUID theo driver. Với DBMS khác, UUID có thể được lưu dạng binary, character hoặc kiểu native riêng. Kiểm tra mapping của driver.

### 6.3. Enum Java

Có thể bind tên enum:

```java
enum OrderStatus {
    NEW, PAID, CANCELLED
}

OrderStatus status = OrderStatus.PAID;
ps.setString(1, status.name());
```

Cách này phù hợp khi cột SQL là VARCHAR có vocabulary tương ứng. Nếu DBMS dùng native enum hoặc kiểu riêng, có thể cần mapping/driver-specific binding.

Không dùng toString làm hợp đồng lưu trữ nếu phương thức đó có thể được override và thay đổi nội dung.

### 6.4. Phân biệt mã và số

Mã bưu chính, số tài khoản hiển thị, mã sản phẩm có thể chứa số 0 ở đầu hoặc ký tự. Dù chỉ có chữ số, chúng vẫn có thể là chuỗi định danh, không phải số để cộng trừ.

## 7. Boolean: false khác NULL

Một cột boolean có thể có ba trạng thái logic nếu cho phép NULL:

| Giá trị | Ý nghĩa ví dụ |
| --- | --- |
| TRUE | Đang hoạt động |
| FALSE | Đã tắt |
| NULL | Chưa xác định/chưa được nhập |

Bind boolean:

```java
ps.setBoolean(1, true);
```

Bind NULL:

```java
ps.setNull(1, Types.BOOLEAN);
```

Không dùng setString(1, "false") nếu cột SQL là BOOLEAN, trừ khi có lý do chuyển kiểu đặc thù được tài liệu hóa.

### 7.1. Boolean nullable và checkbox

Một checkbox UI thường chỉ có true/false. Nếu database còn trạng thái NULL, UI cần quyết định NULL hiển thị như chưa thiết lập, có nút “không xác định” riêng hay khi người dùng không sửa trường thì ứng dụng bỏ qua tham số.

Đừng tự chuyển NULL thành false khi chưa xác nhận quy tắc nghiệp vụ.

## 8. DATE, TIME và TIMESTAMP: chọn đúng kiểu Java

Ngày và thời điểm không giống nhau.

| SQL | Ý nghĩa | Java thường phù hợp |
| --- | --- | --- |
| DATE | Ngày lịch, không có giờ | LocalDate |
| TIME | Giờ trong ngày, không ngày | LocalTime |
| TIMESTAMP WITHOUT TIME ZONE | Ngày giờ địa phương không gắn múi giờ | LocalDateTime |
| TIMESTAMP WITH TIME ZONE | Thời điểm theo quy tắc DBMS | OffsetDateTime/Instant tùy driver |

### 8.1. Bind DATE bằng LocalDate

```java
LocalDate birthDate = LocalDate.of(1995, 4, 12);

String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE birth_date = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, birthDate);

    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả
    }
}
```

JDBC 4.2 hỗ trợ mapping các kiểu java.time phổ biến qua setObject/getObject khi driver triển khai tương thích.

### 8.2. Đừng bind ngày theo format hiển thị

Không nên:

```java
ps.setString(1, "12/04/1995");
```

Chuỗi này có thể được hiểu là ngày 12 tháng 4 hoặc 4 tháng 12 tùy định dạng/locale. Dùng LocalDate tránh mơ hồ đó.

### 8.3. TIMESTAMP WITHOUT TIME ZONE

Nếu cột là timestamp không múi giờ:

```java
LocalDateTime localDateTime =
    LocalDateTime.of(2026, 11, 14, 9, 30);

ps.setObject(1, localDateTime);
```

Đừng tự gắn UTC cho một giá trị địa phương nếu nghiệp vụ không nói như vậy.

### 8.4. TIMESTAMPTZ và OffsetDateTime

Với PostgreSQL TIMESTAMPTZ:

```java
OffsetDateTime eventTime =
    OffsetDateTime.parse("2026-11-14T09:30:00+07:00");

ps.setObject(1, eventTime);
```

PostgreSQL lưu thời điểm theo ngữ nghĩa instant; cách hiển thị phụ thuộc TimeZone của session. Offset ban đầu không nhất thiết được giữ nguyên như một thuộc tính riêng của giá trị đã lưu.

### 8.5. Instant có thể cần mapping driver rõ ràng

Instant biểu diễn thời điểm UTC. Một số driver có thể hỗ trợ trực tiếp; một số trường hợp nên chuyển thành OffsetDateTime UTC:

```java
OffsetDateTime utc =
    instant.atOffset(ZoneOffset.UTC);

ps.setObject(1, utc);
```

Kiểm tra phiên bản JDBC driver thực tế. Không giả định mọi driver đều hỗ trợ mọi kiểu java.time giống nhau.

### 8.6. Tránh phụ thuộc timezone mặc định của JVM

Nếu dùng java.sql.Timestamp/Calendar hoặc mapping legacy, timezone mặc định của JVM và session DB có thể ảnh hưởng chuyển đổi.

Đặt chính sách rõ cho múi giờ lưu trữ, múi giờ hiển thị, ranh giới ngày, DST nếu khu vực áp dụng và cách so sánh/phân trang theo thời gian.

## 9. Binary, BLOB và dữ liệu lớn

Với cột BYTEA PostgreSQL hoặc kiểu binary tương ứng:

```java
byte[] content = Files.readAllBytes(path);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO app.attachments(file_data) VALUES (?)")) {
    ps.setBytes(1, content);
    ps.executeUpdate();
}
```

Với file lớn, không nhất thiết đọc toàn bộ file vào RAM:

```java
try (InputStream input = Files.newInputStream(path);
     PreparedStatement ps = connection.prepareStatement(
         "INSERT INTO app.attachments(file_data) VALUES (?)")) {

    ps.setBinaryStream(1, input);
    ps.executeUpdate();
}
```

JDBC có overload nhận độ dài stream; khả năng streaming và cách driver truyền dữ liệu có thể khác nhau. Với file lớn, kiểm tra tài liệu driver, giới hạn packet, timeout và transaction.

Nếu dữ liệu là binary, dùng kiểu binary phù hợp. Chuyển thành Base64 rồi lưu VARCHAR có thể làm tăng dung lượng và chi phí encode/decode. Log kích thước, content type hoặc hash phù hợp, không in toàn bộ nội dung file/token ra log.

## 10. SQL NULL và Java null là hai tầng khác nhau

Trong Java:

```java
String email = null;
```

Trong SQL, NULL biểu thị giá trị không xác định/không có theo ngữ nghĩa SQL.

Khi bind:

```java
ps.setNull(1, Types.VARCHAR);
```

ứng dụng yêu cầu database nhận SQL NULL có kiểu VARCHAR.

Không giống:

```java
ps.setString(1, "NULL");
```

câu này truyền bốn ký tự N U L L dưới dạng chuỗi.

### 10.1. NULL không phải chuỗi rỗng

| Java input | Giá trị SQL dự kiến |
| --- | --- |
| null qua setNull | SQL NULL |
| "" qua setString | Chuỗi rỗng |
| " " qua setString | Một dấu cách |
| "NULL" qua setString | Chuỗi literal NULL |

Oracle có quy tắc đặc biệt: chuỗi ký tự độ dài 0 trong SQL thường được xử lý như NULL đối với kiểu character. Đây là khác biệt quan trọng khi viết ứng dụng đa DBMS.

### 10.2. NULL không phải số 0

```text
NULL  -- chưa biết/không có giá trị
0     -- giá trị số bằng không
```

Nếu credit_limit là NULL, điều đó không tự có nghĩa khách hàng được cấp hạn mức 0.

### 10.3. NULL không phải false

```text
FALSE -- đã xác định là sai
NULL  -- chưa biết
```

Ứng dụng cần giữ đúng khác biệt khi map sang Boolean nullable.

## 11. Bind NULL đúng kiểu bằng setNull

Đây là phần quan trọng khi tham số Java có thể là null.

Ví dụ tìm khách hàng theo email:

```java
String email = null;

String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE email = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    if (email == null) {
        ps.setNull(1, Types.VARCHAR);
    } else {
        ps.setString(1, email);
    }

    try (ResultSet rs = ps.executeQuery()) {
        // Với email null, điều kiện email = NULL không khớp hàng nào.
    }
}
```

### 11.1. Vì sao setNull cần SQL type?

JDBC cần biết kiểu SQL mà tham số NULL đại diện. Một giá trị Java null không mang đủ thông tin kiểu ở runtime.

Cú pháp:

```java
ps.setNull(parameterIndex, sqlType);
```

Ví dụ:

```java
ps.setNull(1, Types.VARCHAR);
ps.setNull(2, Types.BIGINT);
ps.setNull(3, Types.NUMERIC);
ps.setNull(4, Types.DATE);
ps.setNull(5, Types.BOOLEAN);
```

### 11.2. Dùng setObject với kiểu đích

Có thể dùng:

```java
ps.setObject(1, null, Types.VARCHAR);
```

hoặc kiểu cụ thể khác khi driver hỗ trợ. Với code cần tương thích nhiều driver, setNull(index, Types.X) thường thể hiện ý định rõ.

### 11.3. Không nên dùng Types.NULL cho mọi trường hợp

Types.NULL là kiểu generic. Driver/DBMS có thể cần kiểu cụ thể để xác định overload, cast hoặc kiểu tham số.

Ưu tiên setNull(1, Types.BIGINT) nếu cột thực sự là BIGINT.

### 11.4. Đừng bind chuỗi "null"

```java
ps.setString(1, "null");
```

không tương đương SQL NULL. Nó là chuỗi có bốn ký tự.

## 12. setObject: linh hoạt nhưng cần biết kiểu đích

setObject cho phép truyền nhiều loại giá trị:

```java
ps.setObject(1, localDate);
ps.setObject(2, offsetDateTime);
ps.setObject(3, uuid);
```

Có overload chỉ định kiểu SQL:

```java
ps.setObject(1, value, Types.NUMERIC);
```

Ưu điểm là hỗ trợ nhiều kiểu Java mới, có thể chỉ định kiểu đích và thuận tiện cho tầng binding tổng quát.

Rủi ro là nếu gọi setObject(1, null), driver có thể không xác định được kiểu đích hoặc có hành vi khác nhau. Với NULL, nên cung cấp kiểu rõ.

Tránh binder tổng quát chỉ dựa vào toString:

```java
ps.setString(index, value == null ? null : value.toString());
```

Cách này làm BigDecimal, LocalDate, UUID và Boolean thành chuỗi, còn binary không thể biểu diễn đúng theo cách này. Binder tổng quát phải phân loại kiểu có chủ đích hoặc dùng framework mapping có hợp đồng rõ.

## 13. SQL NULL và logic ba giá trị

SQL không chỉ có TRUE và FALSE. Với NULL, nhiều biểu thức có thể trả UNKNOWN.

| Biểu thức | Kết quả |
| --- | --- |
| 5 = 5 | TRUE |
| 5 = 8 | FALSE |
| 5 = NULL | UNKNOWN |
| NULL = NULL | UNKNOWN |
| NULL <> 5 | UNKNOWN |
| NULL IS NULL | TRUE |

### 13.1. WHERE chỉ giữ hàng mà điều kiện TRUE

```sql
SELECT customer_id, email
FROM app.customers
WHERE email = NULL;
```

Kết quả không có hàng nào. Điều kiện không phải TRUE mà là UNKNOWN đối với cả email NULL và email không NULL.

### 13.2. Dùng IS NULL

```sql
SELECT customer_id, full_name
FROM app.customers
WHERE email IS NULL;
```

Kết quả: khách hàng Chi.

### 13.3. Dùng IS NOT NULL

```sql
SELECT customer_id, full_name
FROM app.customers
WHERE email IS NOT NULL;
```

Kết quả: An và Bình.

Nếu tham số email là null và query dùng WHERE email = ?, setNull khiến điều kiện thành UNKNOWN. Muốn tìm hàng NULL, SQL phải biểu diễn IS NULL.

## 14. IS NULL, IS NOT DISTINCT FROM và null-safe equality

### 14.1. So sánh thông thường

WHERE email = ? có nghĩa so sánh bằng thông thường. Nếu tham số NULL, không có hàng nào khớp bằng cách này.

### 14.2. PostgreSQL: IS NOT DISTINCT FROM

Nếu yêu cầu là hai giá trị được xem là bằng nhau kể cả khi cả hai cùng NULL, PostgreSQL hỗ trợ:

```sql
SELECT customer_id
FROM app.customers
WHERE email IS NOT DISTINCT FROM ?;
```

Bind email của An thì trả An; bind NULL thì trả Chi. IS NOT DISTINCT FROM là phép so sánh null-safe.

### 14.3. PostgreSQL: IS DISTINCT FROM

```sql
WHERE email IS DISTINCT FROM ?
```

trả TRUE khi hai giá trị khác nhau, trong đó NULL được xử lý theo quy tắc null-safe.

### 14.4. MySQL: toán tử <=> 

MySQL có toán tử null-safe equality:

```sql
WHERE email <=> ?
```

### 14.5. SQL Server và các DBMS khác

SQL Server thường biểu diễn điều kiện rõ:

```sql
WHERE
    email = @email
    OR (email IS NULL AND @email IS NULL)
```

SQLite hỗ trợ phép so sánh null-safe theo cú pháp/phiên bản, trong đó IS có ngữ nghĩa đặc biệt so với dấu bằng. Oracle thường dùng IS NULL và điều kiện logic tường minh.

Không sao chép toán tử null-safe của DBMS này sang DBMS khác mà chưa kiểm tra dialect.

### 14.6. Dạng portable với hai placeholder

```sql
WHERE email = ?
   OR (email IS NULL AND ? IS NULL)
```

JDBC phải bind cùng một giá trị ở cả hai vị trí:

```java
if (email == null) {
    ps.setNull(1, Types.VARCHAR);
    ps.setNull(2, Types.VARCHAR);
} else {
    ps.setString(1, email);
    ps.setString(2, email);
}
```

Với tham số có kiểu mơ hồ, một số DBMS cần cast rõ ràng. Mẫu này còn có thể ảnh hưởng khả năng dùng index; nếu hiệu năng quan trọng, đo kế hoạch hoặc dùng cú pháp native phù hợp.

## 15. NULL trong AND, OR và NOT

| A | B | A AND B | A OR B |
| --- | --- | --- | --- |
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

NOT UNKNOWN vẫn là UNKNOWN.

Một bẫy thường gặp:

```sql
SELECT *
FROM app.customers
WHERE customer_id NOT IN (1, NULL);
```

Đối với customer_id không bằng 1, so sánh với NULL vẫn UNKNOWN; toàn bộ điều kiện có thể không TRUE. Nếu muốn loại những ID cụ thể, không đưa NULL vào danh sách trừ khi đã định nghĩa ngữ nghĩa chính xác.

NOT EXISTS thường dễ diễn đạt “không có bản ghi khớp” và tránh một số bẫy NOT IN có NULL trong subquery:

```sql
SELECT c.customer_id
FROM app.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers AS b
    WHERE b.customer_id = c.customer_id
);
```

## 16. NULL trong INSERT: không giống bỏ qua cột để dùng DEFAULT

```sql
CREATE TABLE app.jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_name TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    note TEXT
);
```

Bỏ cột priority:

```sql
INSERT INTO app.jobs(job_name)
VALUES ('daily-report');
```

Database sử dụng DEFAULT 5.

Dùng từ khóa DEFAULT tường minh:

```sql
INSERT INTO app.jobs(job_name, priority)
VALUES ('weekly-report', DEFAULT);
```

Bind NULL vào priority:

```java
String sql = """
    INSERT INTO app.jobs(job_name, priority)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "monthly-report");
    ps.setNull(2, Types.INTEGER);
    ps.executeUpdate();
}
```

Trong schema trên, thao tác vi phạm NOT NULL. Database **không tự dùng DEFAULT 5** chỉ vì tham số được bind NULL.

| SQL/Java | Ý nghĩa |
| --- | --- |
| Không đưa cột vào INSERT | Database áp dụng default nếu có |
| Dùng từ khóa SQL DEFAULT | Yêu cầu database dùng default |
| Bind SQL NULL | Ghi NULL; nếu NOT NULL thì bị từ chối |

## 17. Optional filter: NULL có nghĩa “không lọc” hay “tìm NULL”?

Một API tìm khách hàng có thể nhận email tùy chọn. Có hai hợp đồng khác nhau:

- Hợp đồng A: email không được gửi hoặc là null thì bỏ qua điều kiện email.
- Hợp đồng B: email null nghĩa là tìm những hàng có email SQL NULL.

Hai ý nghĩa này không thể nhập làm một nếu ứng dụng cần phân biệt.

### 17.1. Hợp đồng A: null nghĩa là bỏ qua filter

Một dạng SQL:

```sql
SELECT customer_id, full_name
FROM app.customers
WHERE (? IS NULL OR email = ?);
```

Nếu bind NULL vào cả hai vị trí, vế đầu TRUE nên không lọc theo email. Nếu bind chuỗi email, vế đầu FALSE và vế thứ hai thực hiện so sánh.

Với PostgreSQL, có thể cần cast rõ kiểu placeholder đầu tiên:

```sql
WHERE (CAST(? AS VARCHAR) IS NULL OR email = CAST(? AS VARCHAR))
```

Java:

```java
if (email == null) {
    ps.setNull(1, Types.VARCHAR);
    ps.setNull(2, Types.VARCHAR);
} else {
    ps.setString(1, email);
    ps.setString(2, email);
}
```

### 17.2. Hợp đồng B: null nghĩa là tìm SQL NULL

Dùng predicate rõ ràng:

```sql
SELECT customer_id, full_name
FROM app.customers
WHERE email IS NULL;
```

Nếu email khác null, dùng WHERE email = ? và bind giá trị.

### 17.3. Cách thường tốt hơn: xây predicate có điều kiện

Khi nhiều filter là tùy chọn, có thể thêm điều kiện SQL dựa trên trạng thái presence của input:

```java
StringBuilder sql = new StringBuilder("""
    SELECT customer_id, full_name
    FROM app.customers
    WHERE 1 = 1
    """);

List<Object> values = new ArrayList<>();

if (email != null) {
    sql.append(" AND email = ?");
    values.add(email);
}

if (active != null) {
    sql.append(" AND is_active = ?");
    values.add(active);
}

try (PreparedStatement ps =
         connection.prepareStatement(sql.toString())) {

    for (int i = 0; i < values.size(); i++) {
        Object value = values.get(i);

        if (value instanceof String s) {
            ps.setString(i + 1, s);
        } else if (value instanceof Boolean b) {
            ps.setBoolean(i + 1, b);
        }
    }

    try (ResultSet rs = ps.executeQuery()) {
        // Map kết quả
    }
}
```

Đoạn minh họa dùng danh sách Object đơn giản; production nên có binder có kiểu rõ thay vì một nhánh mapping ngắn cho mọi loại dữ liệu.

Query động ở đây không phải SQL injection vì ứng dụng chỉ thêm những đoạn SQL cố định do developer viết. Cấu trúc query được chọn bởi logic code; giá trị vẫn được bind.

Một query optional filter duy nhất không phải lúc nào cũng tối ưu nhất. Điều kiện tham số NULL hoặc OR có thể làm optimizer khó chọn kế hoạch tốt cho mọi trường hợp. Query không có predicate khi không cần lọc thường dễ tối ưu hơn.

## 18. COALESCE và NULL

COALESCE trả biểu thức đầu tiên không NULL:

```sql
SELECT COALESCE(NULL, 'unknown');
```

Dùng cho hiển thị:

```sql
SELECT
    customer_id,
    COALESCE(email, '(chưa có email)') AS email_display
FROM app.customers;
```

Không nên dùng COALESCE để tự động làm optional filter:

```sql
WHERE email = COALESCE(?, email)
```

Khi tham số NULL, điều kiện trở thành email = email. Với hàng có email NULL, biểu thức vẫn UNKNOWN, nên hàng đó bị loại. Nếu mục tiêu là “NULL nghĩa là không lọc”, query này không đáp ứng đúng ý định.

COALESCE cũng có thể đổi ý nghĩa dữ liệu:

```sql
SELECT COALESCE(credit_limit, 0)
FROM app.customers;
```

Nó đổi “chưa xác định hạn mức” thành “hạn mức bằng 0” ở kết quả. Chỉ làm khi nghiệp vụ chấp nhận hai trạng thái giống nhau trong ngữ cảnh đó.

Áp dụng COALESCE lên cột trong predicate cũng có thể ảnh hưởng cách dùng index. Đo query plan hoặc cân nhắc expression index nếu thực sự cần.

## 19. PostgreSQL: tham số NULL có thể cần cast rõ kiểu

Một câu lệnh PostgreSQL:

```sql
SELECT ?;
```

có thể không đủ thông tin để suy ra kiểu dữ liệu của placeholder, nhất là khi tham số chưa có ngữ cảnh cột hoặc được bind NULL. Một lỗi có thể liên quan kiểu dữ liệu tham số không xác định, ví dụ SQLSTATE 42P18 trong tình huống phù hợp.

Cast placeholder:

```sql
SELECT CAST(? AS INTEGER);
```

hoặc cú pháp PostgreSQL:

```sql
SELECT ?::integer;
```

So sánh với cột typed thường giúp suy luận:

```sql
SELECT customer_id
FROM app.customers
WHERE customer_id = ?;
```

Cột BIGINT cung cấp ngữ cảnh kiểu cho phép so sánh, nhưng ứng dụng vẫn nên bind đúng kiểu BIGINT qua setLong hoặc setNull(..., Types.BIGINT).

Với optional predicate:

```sql
WHERE (? IS NULL OR customer_id = ?)
```

placeholder đầu tiên chỉ xuất hiện trong IS NULL, có thể thiếu ngữ cảnh kiểu. Dùng:

```sql
WHERE (CAST(? AS BIGINT) IS NULL
       OR customer_id = CAST(? AS BIGINT))
```

và bind BIGINT cho cả hai vị trí.

Một câu SQL chạy được trong psql với literal không chứng minh câu có placeholder trong JDBC sẽ suy luận kiểu y hệt. Khi lỗi chỉ xuất hiện với NULL, kiểm tra kiểu placeholder, setter và phiên bản driver.

## 20. IN clause với danh sách tham số

PreparedStatement không tự mở rộng một placeholder thành nhiều phần tử.

Sai:

```java
String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE customer_id IN (?)
    """;

ps.setString(1, "1,2,3");
```

Câu này bind một giá trị chuỗi "1,2,3", không phải ba số ID.

### 20.1. Tạo đúng số placeholder

```java
List<Long> ids = List.of(1L, 2L, 3L);

String placeholders = String.join(
    ",",
    Collections.nCopies(ids.size(), "?")
);

String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE customer_id IN (%s)
    """.formatted(placeholders);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        ps.setLong(i + 1, ids.get(i));
    }

    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả
    }
}
```

Danh sách ID chỉ tạo số lượng dấu hỏi; từng giá trị vẫn bind bằng setLong.

### 20.2. Xử lý danh sách rỗng

Nếu ids rỗng, code trên tạo WHERE customer_id IN (), không phải cú pháp portable và có thể lỗi.

Hãy quyết định hợp đồng:

- Danh sách rỗng nghĩa là không có kết quả: trả empty list trước khi query hoặc dùng điều kiện luôn false.
- Danh sách rỗng nghĩa là không áp dụng filter: bỏ predicate.
- Không tự chọn một trong hai nếu API chưa định nghĩa.

### 20.3. Danh sách NULL và danh sách lớn

Nếu danh sách chứa NULL, IN/NOT IN chịu logic ba giá trị. Nên validate và tách NULL khỏi danh sách nếu nó không phải một phần ngữ nghĩa truy vấn.

Nhiều placeholder có thể chạm giới hạn driver/DBMS hoặc tạo SQL dài. Các lựa chọn khác tùy DBMS gồm temporary table, table-valued parameter (SQL Server), array parameter/unnest (PostgreSQL), staging table hoặc bulk load.

## 21. PostgreSQL array parameter

PostgreSQL JDBC hỗ trợ bind array qua API driver/JDBC tương ứng.

```java
Long[] ids = {1L, 2L, 3L};

String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE customer_id = ANY (?::bigint[])
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    Array sqlArray = connection.createArrayOf("int8", ids);

    try {
        ps.setArray(1, sqlArray);

        try (ResultSet rs = ps.executeQuery()) {
            // Đọc kết quả
        }
    } finally {
        sqlArray.free();
    }
}
```

Nếu array chứa NULL, kết quả logic của phép so sánh bằng ANY(array) có thể là UNKNOWN khi không có phần tử nào khớp nhưng có NULL trong array. Validate danh sách theo hợp đồng.

Array parameter là cách truyền tập giá trị vào query, không tự tạo khóa ngoại hoặc bảng quan hệ bền vững. createArrayOf và cú pháp ANY phụ thuộc hỗ trợ driver/DBMS.

## 22. LIKE: bind an toàn nhưng wildcard vẫn có ý nghĩa

Bind tham số giúp chống injection:

```java
String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE full_name LIKE ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "%An%");
    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả
    }
}
```

Nhưng % và _ vẫn là wildcard của LIKE:

- %: khớp chuỗi bất kỳ, kể cả rỗng.
- _: khớp một ký tự.

Nếu input là literal tìm kiếm, người dùng nhập 50% có thể vô tình tạo wildcard.

### 22.1. Escape wildcard cho tìm kiếm literal

Một mẫu SQL:

```sql
SELECT customer_id, full_name
FROM app.customers
WHERE full_name LIKE ? ESCAPE '!';
```

Ứng dụng escape ký tự !, % và _ trong input trước khi thêm wildcard đầu/cuối:

```java
static String escapeLike(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}

String pattern = "%" + escapeLike(userInput) + "%";
ps.setString(1, pattern);
```

Ký tự escape phải nhất quán với mệnh đề ESCAPE và cú pháp DBMS.

Bind chống injection nhưng không vô hiệu hóa wildcard. Nếu API yêu cầu tìm literal, cần xử lý wildcard riêng. LIKE '%term%' thường khó tận dụng B-tree prefix index thông thường; DBMS có extension hoặc cơ chế tìm kiếm chuyên biệt.

## 23. Không bind tên bảng, tên cột hoặc từ khóa SQL

Placeholder đại diện giá trị, không đại diện cú pháp.

Sai:

```java
String sql = "SELECT * FROM ? WHERE customer_id = ?";
ps.setString(1, "app.customers");
ps.setLong(2, 1L);
```

Dấu hỏi không thể biến thành tên bảng.

Tương tự, không thể bind trực tiếp tên cột trong ORDER BY, ASC/DESC, tên schema, tên bảng, toán tử, tên hàm hoặc một đoạn WHERE tùy ý.

### 23.1. Dùng whitelist cho identifier động

```java
enum CustomerSort {
    NAME,
    CREATED_AT
}

String sortColumn = switch (sort) {
    case NAME -> "full_name";
    case CREATED_AT -> "created_at";
};

String direction = ascending ? "ASC" : "DESC";

String sql = """
    SELECT customer_id, full_name, created_at
    FROM app.customers
    ORDER BY %s %s
    """.formatted(sortColumn, direction);
```

sortColumn và direction chỉ đến từ tập giá trị cố định do code định nghĩa, không lấy nguyên văn từ request. Giá trị filter vẫn dùng placeholder.

Không dùng regex đơn giản để “lọc SQL” từ user. Với identifier động, dùng whitelist/metadata rõ ràng và quoting identifier theo quy tắc DBMS khi thật sự cần.

## 24. PreparedStatement: vòng đời và tái sử dụng

PreparedStatement gắn với một Connection và câu SQL đã chuẩn bị.

```java
String sql = """
    UPDATE app.customers
    SET is_active = ?
    WHERE customer_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBoolean(1, false);
    ps.setLong(2, 3L);

    int changed = ps.executeUpdate();
}
```

Thông thường:

- executeQuery() dùng cho câu trả result set, như SELECT.
- executeUpdate() dùng cho INSERT/UPDATE/DELETE và một số câu DDL; trả số hàng bị tác động theo API.
- execute() dùng khi kết quả có thể đa dạng.

### 24.1. Reuse statement cần bind lại mọi vị trí

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT customer_id FROM app.customers WHERE email = ?")) {

    ps.setString(1, "an@example.invalid");
    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }

    ps.setString(1, "binh@example.invalid");
    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
```

Đừng giả định tham số chưa bind ở lần thứ hai tự trở về NULL hoặc giá trị mặc định. Hãy gán mọi vị trí cần thiết trước mỗi lần execute.

clearParameters có thể xóa các giá trị đã bind, nhưng không thay thế việc bind đầy đủ từng lần. Không giữ một statement dùng chung tùy tiện giữa nhiều thread; JDBC Connection/Statement thường không được thiết kế để chia sẻ đồng thời.

## 25. Batch binding: nhiều hàng, cùng một câu SQL

```java
String sql = """
    INSERT INTO app.customers(
        email, full_name, birth_date, credit_limit, is_active
    )
    VALUES (?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "mai@example.invalid");
    ps.setString(2, "Mai");
    ps.setObject(3, LocalDate.of(1998, 2, 10));
    ps.setBigDecimal(4, new BigDecimal("3000000.00"));
    ps.setBoolean(5, true);
    ps.addBatch();

    ps.setNull(1, Types.VARCHAR);
    ps.setString(2, "Nam");
    ps.setNull(3, Types.DATE);
    ps.setNull(4, Types.NUMERIC);
    ps.setBoolean(5, false);
    ps.addBatch();

    int[] counts = ps.executeBatch();
}
```

Mỗi hàng có thể mang kiểu dữ liệu khác nhau nhưng kiểu SQL của cột phải tương thích. Hàng thứ hai vẫn cần setNull với Types.DATE và Types.NUMERIC cho hai cột nullable.

### 25.1. Batch không tự quyết định transaction

Nếu muốn toàn bộ batch thành công hoặc rollback cùng nhau, quản lý transaction rõ:

```java
connection.setAutoCommit(false);

try {
    // Bind và addBatch nhiều hàng
    ps.executeBatch();
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(true);
}
```

Mẫu production cần khôi phục trạng thái connection theo pool và xử lý lỗi rollback/commit cẩn thận. Không tự động bật/tắt auto-commit trên connection đang được framework quản lý transaction.

Driver có thể trả SUCCESS_NO_INFO hoặc EXECUTE_FAILED trong mảng kết quả. Đừng giả định mọi phần tử luôn là số hàng dương chính xác.

## 26. Transaction và NULL: giá trị không xác định không phải lỗi kết nối

Khi cập nhật một trường tùy chọn, cần phân biệt:

- Trường không xuất hiện trong request: không thay đổi.
- Trường xuất hiện với giá trị null: xóa giá trị hiện có nếu API định nghĩa như vậy.
- Trường xuất hiện với số: cập nhật số mới.

Nếu DTO chỉ có một BigDecimal creditLimit, Java null có thể đang đại diện cả “không gửi” lẫn “xóa”. Hai ý nghĩa này bị nhập làm một.

### 26.1. Mô hình PATCH cần biểu diễn presence riêng

```java
record PatchField<T>(boolean present, T value) {}
```

- present=false: không thay đổi.
- present=true, value=null: đặt SQL NULL.
- present=true, value=5000000: cập nhật số.

DTO/JSON deserialization cần phân biệt key không xuất hiện và key có giá trị JSON null.

### 26.2. SQL tương ứng

Nếu field không được gửi, bỏ cột đó khỏi UPDATE. Nếu field được gửi, dùng:

```sql
UPDATE app.customers
SET credit_limit = ?
WHERE customer_id = ?;
```

và bind setNull(1, Types.NUMERIC) khi hợp đồng yêu cầu xóa hạn mức.

Tránh dùng:

```sql
SET credit_limit = COALESCE(?, credit_limit)
```

nếu NULL là lệnh xóa, vì tham số NULL sẽ giữ nguyên giá trị cũ. Nếu API cần cả “bỏ qua” và “đặt NULL”, cần thêm presence flag hoặc cấu trúc query khác.

## 27. Đọc NULL từ ResultSet đúng cách

JDBC có một bẫy với primitive getter:

```java
int value = rs.getInt("some_nullable_integer");
```

Nếu cột SQL là NULL, getInt trả 0. Phải gọi wasNull ngay sau getter để biết giá trị có phải SQL NULL không.

```java
int value = rs.getInt("priority");
Integer priority = rs.wasNull() ? null : value;
```

wasNull áp dụng cho giá trị cột được đọc gần nhất; gọi nó sau một getter khác sẽ kiểm tra cột khác.

### 27.1. Dùng getObject với wrapper type

```java
Integer priority =
    rs.getObject("priority", Integer.class);
```

Với driver hỗ trợ JDBC mapping tương ứng, có thể nhận null trực tiếp vào wrapper.

Các getter khác:

- getLong trả 0 nếu SQL NULL; dùng wasNull hoặc Long.
- getBoolean trả false nếu SQL NULL; dùng wasNull hoặc Boolean.
- getBigDecimal trả null nếu SQL NULL.
- getString trả null nếu SQL NULL.
- getDate/getTimestamp có thể trả null.

Java int, long, boolean không có giá trị null. Nếu dữ liệu SQL nullable, cân nhắc wrapper, Optional ở API/domain khi phù hợp, hoặc một kiểu trạng thái có presence riêng nếu cần phân biệt missing/null.

## 28. getObject và kiểu Java thời gian

JDBC 4.2 hỗ trợ typed retrieval trong nhiều driver:

```java
LocalDate birthDate =
    rs.getObject("birth_date", LocalDate.class);

OffsetDateTime createdAt =
    rs.getObject("created_at", OffsetDateTime.class);
```

Nếu cột SQL là NULL, kết quả typed object có thể là null.

Không phải driver/phiên bản nào cũng hỗ trợ cùng mapping cho mọi kiểu java.time, enum, UUID, JSON hoặc kiểu đặc thù. Nếu driver cũ không hỗ trợ, có thể cần nâng cấp driver, dùng mapping legacy phù hợp hoặc chuyển đổi rõ ràng ở tầng repository.

Đừng dùng getString cho mọi kiểu. Lấy ngày giờ bằng chuỗi rồi parse có thể bị ảnh hưởng bởi format, timezone và locale.

## 29. CallableStatement: bind IN, OUT và NULL

Stored procedure/function có thể cần tham số IN/OUT.

Ví dụ procedure theo cú pháp PostgreSQL:

```sql
CREATE PROCEDURE app.find_customer_name(
    IN p_customer_id BIGINT,
    INOUT p_name TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    SELECT full_name
    INTO p_name
    FROM app.customers
    WHERE customer_id = p_customer_id;
END;
$$;
```

Cách gọi qua JDBC phụ thuộc driver và cách DBMS biểu diễn procedure. Ví dụ JDBC tổng quát cho procedure có OUT:

```java
try (CallableStatement cs =
         connection.prepareCall("{ call app.some_procedure(?, ?) }")) {

    cs.setLong(1, 1L);
    cs.registerOutParameter(2, Types.VARCHAR);
    cs.execute();

    String result = cs.getString(2);
}
```

IN parameter NULL dùng setNull(index, Types.X). OUT parameter cần registerOutParameter với kiểu SQL driver mong đợi. Nếu output nullable, getter có thể trả Java null; với getter primitive, vẫn cần kiểm tra wasNull.

PostgreSQL function và procedure có cú pháp gọi khác; MySQL có CALL và tham số OUT/INOUT; SQL Server dùng EXEC/EXECUTE và OUTPUT; Oracle có PL/SQL block/callable syntax; SQLite không có stored procedure lõi theo cùng mô hình.

## 30. Bind JSON và kiểu đặc thù của DBMS

Một cột PostgreSQL JSONB có thể cần cách bind riêng.

Với PostgreSQL JDBC, một cách driver-specific:

```java
PGobject json = new PGobject();
json.setType("jsonb");
json.setValue("""
    {"theme":"dark","page_size":20}
    """);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO app.user_preferences(user_id, settings) VALUES (?, ?)")) {
    ps.setLong(1, 10L);
    ps.setObject(2, json);
    ps.executeUpdate();
}
```

Cột JSONB không phải VARCHAR. Một driver/DBMS có thể không tự cast một tham số VARCHAR sang JSONB theo cách mong muốn. Dùng kiểu object phù hợp hoặc cast tường minh theo dialect.

PGobject là API của PostgreSQL JDBC driver. MySQL, SQL Server và Oracle có mapping riêng. JSON phải hợp lệ và tuân theo schema nghiệp vụ; bind parameter chống injection nhưng không xác nhận JSON có đúng ý nghĩa hay không.

## 31. NULL với kiểu PostgreSQL đặc thù

Một số kiểu như UUID, JSONB, ARRAY, ENUM hoặc kiểu do extension tạo cần type mapping cụ thể.

Ví dụ khi bind SQL NULL cho JSONB bằng PostgreSQL JDBC, tùy driver có thể dùng:

```java
ps.setNull(1, Types.OTHER);
```

hoặc dùng API kiểu riêng/cast trong SQL:

```sql
INSERT INTO app.events(payload)
VALUES (CAST(? AS jsonb));
```

Nếu bind NULL bằng Types.VARCHAR, driver có thể gửi kiểu VARCHAR, khiến PostgreSQL không thể dùng nó như JSONB trong ngữ cảnh mong đợi.

Dùng kiểu đích thực tế của cột và tài liệu driver, không đoán dựa trên tên Java.

## 32. Tham số hóa không thay validation nghiệp vụ

Một câu lệnh:

```sql
UPDATE app.customers
SET credit_limit = ?
WHERE customer_id = ?;
```

được bind an toàn nhưng vẫn có thể nhận hạn mức âm, vượt giới hạn nghiệp vụ, customer_id không tồn tại, NULL trái hợp đồng hoặc scale không mong muốn.

Validation nên được phân lớp:

- API: kiểm tra format, quyền và quy tắc đầu vào.
- Domain/service: kiểm tra nghiệp vụ.
- Database: NOT NULL, CHECK, UNIQUE, FOREIGN KEY.
- Repository: bind đúng kiểu và xử lý SQL exception.

Client có thể bị chỉnh sửa request. Database constraint là lớp bảo vệ cuối cho những bất biến cần áp dụng cho mọi đường ghi.

Nếu Java DTO cho phép null nhưng database có NOT NULL, cần quyết định null bị từ chối ở API/service hay được chuyển thành default/giữ nguyên. Đừng để SQLException bất ngờ trở thành cơ chế validation duy nhất.

## 33. SQL injection vẫn có thể xuất hiện dù đã dùng PreparedStatement

Đúng:

```java
String sql = """
    SELECT customer_id
    FROM app.customers
    WHERE email = ?
    """;
ps.setString(1, email);
```

Sai:

```java
String sql =
    "SELECT customer_id FROM app.customers " +
    "WHERE email = '" + email + "'";
```

Một kiểu lỗi khác:

```java
String sql =
    "SELECT customer_id FROM app.customers " +
    "ORDER BY " + request.getParameter("sort");
```

PreparedStatement không thể bind tên cột ở vị trí ORDER BY. Nếu input không được whitelist, vẫn có thể injection.

### 33.1. Whitelist cho sort

```java
String orderBy = switch (sortField) {
    case "name" -> "full_name";
    case "created" -> "created_at";
    default -> throw new IllegalArgumentException(
        "Unsupported sort field"
    );
};

String direction = descending ? "DESC" : "ASC";

String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    ORDER BY %s %s
    """.formatted(orderBy, direction);
```

Identifier/keyword được chọn từ danh sách code kiểm soát; giá trị filter vẫn bind riêng.

Dùng prepared statement cho mọi giá trị dữ liệu. Dùng whitelist cho phần cấu trúc query động. Kết hợp least privilege ở tài khoản database.

## 34. Parameter type và hiệu năng truy vấn

Bind đúng kiểu không chỉ giúp tránh lỗi dữ liệu. Nó còn có thể ảnh hưởng kế hoạch thực thi.

Giả sử cột customer_id là BIGINT nhưng ứng dụng bind chuỗi:

```java
ps.setString(1, "123");
```

DBMS có thể phải chuyển kiểu để so sánh. Tùy hệ quản trị, chiều chuyển đổi có thể ảnh hưởng index, thống kê hoặc kế hoạch.

Typed bind:

```java
ps.setLong(1, 123L);
```

làm rõ tham số là BIGINT.

Không có quy tắc rằng mọi CAST đều làm mất index. Cast trên tham số có thể được tối ưu khác cast trên cột. Cần xem đúng query plan và DBMS.

Khi điều tra query chậm, xem SQL template thực tế, kiểu cột và kiểu tham số driver gửi, giá trị đại diện, kế hoạch thực thi, estimated/actual rows, thời gian và I/O.

Một câu SQL chạy nhanh với literal trong console chưa chắc có cùng plan với prepared statement của ứng dụng.

Một số DBMS cache/reuse plan và tối ưu theo giá trị tham số. Nếu phân bố dữ liệu lệch, plan phù hợp cho giá trị này có thể kém cho giá trị khác. Không khắc phục bằng cách chuyển mọi tham số thành chuỗi; cần hiểu plan cache và công cụ DBMS.

## 35. Logging tham số: hữu ích nhưng có ranh giới bảo mật

Tham số có thể chứa email, số điện thoại, địa chỉ, token, mật khẩu, session ID, thông tin thanh toán, dữ liệu sức khỏe hoặc payload binary.

Có thể log:

- Query name hoặc operation ID.
- SQL template đã loại giá trị.
- Thời gian chạy và số hàng tác động.
- SQLState/vendor code.
- Kiểu tham số và trạng thái null khi hữu ích.
- Correlation ID.
- Giá trị đã mask/hash nếu chính sách cho phép.

Không log mọi giá trị thô một cách mặc định. Khi tái hiện lỗi, dùng dữ liệu giả hoặc dữ liệu đã mask và kiểm soát quyền truy cập log.

NULL cũng có thể mang thông tin. Log trạng thái email null chỉ khi phù hợp chính sách dữ liệu.

## 36. Xử lý SQLException và phân loại lỗi bind

```java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setBigDecimal(2, creditLimit);
    ps.executeUpdate();
} catch (SQLException ex) {
    String sqlState = ex.getSQLState();
    int vendorCode = ex.getErrorCode();

    // Ghi log theo chính sách, không log secret.
    throw ex;
}
```

SQLState là mã phân loại lỗi theo chuẩn/DBMS. Một số nhóm hữu ích:

| Nhóm ví dụ | Ý nghĩa khái quát |
| --- | --- |
| 22 | Lỗi dữ liệu/chuyển đổi dữ liệu |
| 23 | Vi phạm constraint |
| 28 | Lỗi authorization/authentication theo tình huống |
| 42 | Lỗi cú pháp hoặc access rule/schema theo DBMS |
| 08 | Lỗi kết nối |
| 40 | Rollback/transaction serialization theo tình huống |

Mã cụ thể và thông điệp khác nhau giữa driver/DBMS; không hardcode xử lý chỉ dựa vào chuỗi message.

Những lỗi có thể liên quan đến bind gồm không chuyển được chuỗi thành số, vượt precision/scale, bind NULL vào NOT NULL, kiểu placeholder không xác định, tham số không tương thích kiểu cột hoặc thiếu quyền.

BatchUpdateException có thể cung cấp update counts và SQLException tiếp theo. Tùy driver, batch có thể dừng ở lỗi hoặc tiếp tục một phần. Hiểu hành vi transaction/driver trước khi retry.

Không retry mọi lỗi SQL: lỗi validation/constraint thường không tự hết khi retry; lỗi serialization/deadlock có thể cần retry toàn transaction; lỗi connection có thể khiến trạng thái commit không chắc chắn; lỗi quyền không nên xử lý bằng cách cấp ALL.

## 37. Resource management: đóng Connection, Statement và ResultSet

Dùng try-with-resources:

```java
String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE is_active = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setBoolean(1, true);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("customer_id");
            String name = rs.getString("full_name");
        }
    }
}
```

Try-with-resources đóng theo thứ tự ngược: ResultSet đóng trước, rồi PreparedStatement, rồi Connection.

Với connection pool, Connection.close thường trả connection về pool thay vì đóng socket vật lý. Không giữ connection lâu hơn transaction/work cần thiết.

Không dùng chung PreparedStatement giữa thread. Statement có trạng thái parameter và cursor; chia sẻ đồng thời có thể làm lẫn giá trị, kết quả và vòng đời.

## 38. Spring JDBC: named parameters và SQL type

JDBC lõi dùng placeholder vị trí ?. Spring NamedParameterJdbcTemplate cho phép viết tên tham số:

```java
String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE customer_id = :customerId
    """;

MapSqlParameterSource params =
    new MapSqlParameterSource()
        .addValue("customerId", 2L, Types.BIGINT);

List<CustomerRow> rows =
    namedParameterJdbcTemplate.query(
        sql,
        params,
        (rs, rowNum) -> new CustomerRow(
            rs.getLong("customer_id"),
            rs.getString("full_name")
        )
    );
```

Named parameter dễ đọc khi query có nhiều tham số và có thể cung cấp SQL type rõ khi giá trị NULL.

Bind NULL với type tường minh:

```java
MapSqlParameterSource params =
    new MapSqlParameterSource()
        .addValue("email", null, Types.VARCHAR);
```

:customerId là placeholder của framework. Framework chuyển nó thành dạng JDBC tương ứng trước khi gửi tới database; không gửi nguyên văn cú pháp này cho JDBC driver thuần.

Spring có thể mở rộng collection trong IN (:ids) ở một số API. Vẫn phải xử lý danh sách rỗng theo hợp đồng.

## 39. Kiểm thử bind kiểu và NULL

Một test tốt cần kiểm tra cả trường hợp có dữ liệu, rỗng và NULL.

### 39.1. Ma trận test cho cột nullable

| Input Java | Hành vi dự kiến |
| --- | --- |
| "an@example.invalid" | Tìm đúng email |
| null | Theo hợp đồng: tìm NULL hoặc bỏ filter |
| "" | Chuỗi rỗng nếu DBMS hỗ trợ khác NULL |
| " " | Một dấu cách |
| Chuỗi có dấu nháy | Vẫn là dữ liệu, không đổi cú pháp |
| Chuỗi Unicode | Được lưu/so sánh theo encoding/collation |
| Chuỗi quá dài | Bị validation hoặc constraint từ chối có chủ đích |

### 39.2. Test kiểu số

- Số nguyên trong phạm vi.
- Số âm khi cột cấm.
- Số lớn vượt precision.
- Scale nhiều chữ số hơn schema.
- Java null.
- Chuỗi không phải số nếu API nhận text.

### 39.3. Test ngày giờ

- Ngày hợp lệ và ngày nhuận.
- NULL.
- Mốc gần nửa đêm UTC/local.
- Offset khác nhau nhưng cùng instant.
- Thay đổi timezone của JVM/session.
- Thời điểm qua DST nếu nghiệp vụ liên quan.

### 39.4. Test optional filter

Kiểm tra riêng field không gửi, field có mặt và là JSON null, field có giá trị, field là chuỗi rỗng và field có wildcard khi dùng LIKE.

### 39.5. Test trên DBMS thật hoặc Testcontainers phù hợp

Mock JDBC có thể xác minh code gọi setter nhưng không tái tạo đầy đủ type inference, SQL NULL semantics, driver mapping, SQL dialect, constraint/transaction và query plan.

Integration test với đúng DBMS/driver giúp phát hiện khác biệt quan trọng.

## 40. Những lỗi phổ biến và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Dùng = NULL | Nhầm NULL là giá trị so sánh thông thường | Dùng IS NULL hoặc null-safe equality |
| Bind Java null bằng setString | Không cung cấp SQL type rõ | Dùng setNull(index, Types.X) |
| Gửi chuỗi "NULL" | Nhầm literal text với SQL NULL | Bind SQL NULL thật |
| Bind tiền bằng double | Sai số floating-point | Dùng BigDecimal |
| Bind DATE bằng chuỗi locale | Định dạng mơ hồ | Dùng LocalDate/setObject |
| Dùng setString cho BIGINT | Chuyển kiểu ngầm | setLong/setNull BIGINT |
| Dùng một ? cho cả danh sách IN | Placeholder chỉ là một giá trị | Tạo nhiều placeholder hoặc cơ chế array/table |
| IN () khi list rỗng | Không xử lý empty list | Trả empty result/bỏ filter theo hợp đồng |
| Dùng COALESCE để bỏ filter | Không xử lý đúng cột NULL | Predicate optional rõ ràng |
| Gắn wildcard LIKE nhưng không escape | %/_ vẫn là wildcard | ESCAPE nếu cần tìm literal |
| Bind tên bảng bằng ? | Placeholder không đại diện identifier | Whitelist identifier |
| getInt trên cột nullable | NULL biến thành 0 nếu không wasNull | Wrapper/getObject/wasNull |
| Bind NULL JSONB bằng VARCHAR | Kiểu driver không phù hợp | Types.OTHER/PGobject/cast theo dialect |
| Bỏ qua timezone | Local time và instant khác nhau | Chọn LocalDateTime/OffsetDateTime/Instant có chủ đích |
| Log mọi tham số | Lộ PII/secret | Mask, redact, log metadata |
| Retry mọi SQLException | Lỗi vĩnh viễn bị lặp lại | Phân loại SQLState và retry có điều kiện |
| Dùng một statement nhiều thread | Trạng thái parameter/cursor dùng chung | Statement theo thao tác/thread phù hợp |

## 41. So sánh cách bind giữa các DBMS

JDBC là API chung, nhưng kiểu native và cách driver triển khai có thể khác.

| Nội dung | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Placeholder JDBC | ? | ? | ? | ? | Driver JDBC dùng ? |
| BIGINT | BIGINT | BIGINT | BIGINT | Mapping số tương ứng theo schema | Mapping theo affinity/driver |
| Decimal | NUMERIC | DECIMAL | DECIMAL | NUMBER | Numeric affinity/driver |
| Boolean | BOOLEAN | BOOLEAN/biểu diễn tương ứng theo version | BIT | Không có SQL BOOLEAN cột trong nhiều phiên bản truyền thống; khác biệt theo version | Giá trị integer 0/1 thường gặp |
| JSON | JSON/JSONB | JSON | JSON functions; native capabilities tùy version | JSON/text/binary theo version | JSON functions; JSONB nội bộ tùy version |
| Null-safe equality | IS NOT DISTINCT FROM | <=> | Predicate tường minh | Predicate tường minh/NULL semantics riêng | IS/cú pháp theo version |
| Array binding | Native arrays qua driver | Không cùng kiểu native PostgreSQL | Table-valued parameters qua API phù hợp | Collection types theo driver | Nhiều placeholders/temp table |
| Timestamp with zone | TIMESTAMPTZ | Kiểu và session behavior riêng | datetimeoffset | TIMESTAMP WITH TIME ZONE | Không có kiểu native tương đương đầy đủ |
| Đặc điểm driver | OID, PGobject, array, JSONB | JSON và type mapping riêng | TVP, UUID/uniqueidentifier, datetimeoffset | NUMBER, DATE/TIMESTAMP, REF CURSOR | Affinity và cách mapping theo driver |

Cú pháp Java JDBC cơ bản giống nhau; kiểu SQL và cách driver ánh xạ không giống nhau.

### 41.1. PostgreSQL

Dùng setLong cho BIGINT, setBigDecimal cho NUMERIC, setNull với SQL type cụ thể. JSONB/array/enum có thể cần API driver-specific. Cẩn thận tham số NULL chưa xác định kiểu.

### 41.2. MySQL

Kiểu JSON native có mapping riêng. SQL NULL và chuỗi rỗng có quy tắc đặc biệt theo kiểu/DBMS. Toán tử <=> hỗ trợ so sánh null-safe. Timestamp/date-time có hành vi liên quan session timezone; kiểm tra driver và server settings.

### 41.3. SQL Server

BIT thường dùng cho boolean. DATETIME2 và DATETIMEOFFSET có ngữ nghĩa khác. Table-valued parameter hữu ích cho tập ID lớn.

### 41.4. Oracle

NUMBER thường dùng cho số chính xác. DATE của Oracle chứa cả ngày và thời gian đến giây, khác kiểu DATE của PostgreSQL/MySQL. Chuỗi rỗng trong kiểu character có ngữ nghĩa như NULL trong SQL Oracle truyền thống. Một số kiểu/collection/REF CURSOR cần mapping JDBC riêng.

### 41.5. SQLite

Type affinity và driver ảnh hưởng mapping. Không có kiểu timestamp native giống PostgreSQL; ứng dụng thường chọn TEXT/INTEGER/REAL theo quy ước. Cần thống nhất định dạng ngày giờ và đơn vị thời gian. Đừng giả định NULL/boolean/decimal được lưu như một server RDBMS có type enforcement chặt.

## 42. Quy trình debug khi ứng dụng bind sai kiểu hoặc NULL

Khi query chạy trong SQL console nhưng lỗi trong Java, hãy đi theo thứ tự.

### Bước 1 — Xác nhận SQL template

Lưu lại câu SQL có placeholder, không ghép tham số vào chuỗi.

### Bước 2 — Liệt kê từng vị trí

```sql
UPDATE app.customers
SET credit_limit = ?,
    is_active = ?
WHERE customer_id = ?;
```

| Vị trí | Cột | Kiểu SQL | Kiểu Java |
| ---: | --- | --- | --- |
| 1 | credit_limit | NUMERIC(14,2) | BigDecimal |
| 2 | is_active | BOOLEAN | Boolean |
| 3 | customer_id | BIGINT | Long |

### Bước 3 — Kiểm tra nullability

- Cột có nullable không?
- DTO có phân biệt absent và null không?
- Khi null, code dùng setter nào?
- SQL type truyền cho setNull có đúng không?

### Bước 4 — Kiểm tra ResultSet mapping

- Primitive getter có dùng wasNull?
- Wrapper có giữ được null?
- Driver có hỗ trợ typed getObject?
- Cột timestamp được map theo timezone nào?

### Bước 5 — Đọc SQLState và vendor code

Không chỉ đọc thông báo tiếng Anh. Ghi nhận SQLState, vendor code, câu lệnh operation và kiểu parameter đã bind.

### Bước 6 — Reproduce với driver và DBMS thực

Dùng cùng version database, driver, session settings và query shape. Không thay giá trị null bằng literal trong console rồi kết luận đã tái hiện chính xác.

### Bước 7 — Kiểm tra plan khi lỗi là hiệu năng

Nếu query không lỗi nhưng chậm, kiểm tra implicit casts, parameter types, selectivity, plan cache và index.

## 43. Bài tập thực hành có lời giải

Các bài tập dùng bảng app.customers ở mục 2 và Java JDBC.

### Bài 1. Bind customer_id BIGINT

```java
String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE customer_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 2L);
    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả
    }
}
```

**Đáp án:** Dùng setLong(1, 2L); kết quả là Bình.

### Bài 2. Bind NUMERIC

```java
String sql = """
    SELECT customer_id, full_name
    FROM app.customers
    WHERE credit_limit >= ?
    """;

ps.setBigDecimal(1, new BigDecimal("3000000.00"));
```

**Đáp án:** An. Bình có 2.500.000; Chi có NULL nên predicate UNKNOWN.

### Bài 3. Tại sao không dùng double cho tiền?

**Đáp án:** Floating-point nhị phân không biểu diễn chính xác mọi số thập phân. Dùng BigDecimal và chính sách rounding rõ.

### Bài 4. Bind email NULL

**Đáp án:**

```java
ps.setNull(1, Types.VARCHAR);
```

Không dùng setString(1, "NULL").

### Bài 5. email = NULL trả bao nhiêu hàng?

```sql
SELECT *
FROM app.customers
WHERE email = NULL;
```

**Đáp án:** 0 hàng vì biểu thức là UNKNOWN, không phải TRUE.

### Bài 6. Tìm khách chưa có email

```sql
SELECT customer_id, full_name
FROM app.customers
WHERE email IS NULL;
```

**Đáp án:** Chi.

### Bài 7. Tìm email khác NULL

```sql
SELECT customer_id, full_name
FROM app.customers
WHERE email IS NOT NULL;
```

**Đáp án:** An và Bình.

### Bài 8. Null-safe equality trong PostgreSQL

```sql
SELECT customer_id
FROM app.customers
WHERE email IS NOT DISTINCT FROM ?;
```

**Đáp án:** Nếu bind NULL, trả Chi; nếu bind email của An, trả An.

### Bài 9. MySQL null-safe equality

```sql
WHERE email <=> ?
```

**Đáp án:** Toán tử <=> của MySQL xử lý hai NULL là bằng nhau trong phép so sánh null-safe.

### Bài 10. Java null khác chuỗi rỗng?

**Đáp án:** Có. Java null bind thành SQL NULL; chuỗi rỗng là giá trị khác NULL ở DBMS phân biệt chúng, nhưng Oracle có quy tắc đặc biệt coi chuỗi rỗng character là NULL.

### Bài 11. Đọc cột nullable bằng getInt

```java
int value = rs.getInt("some_nullable_integer");
Integer result = rs.wasNull() ? null : value;
```

**Đáp án:** Hoặc dùng getObject(column, Integer.class) nếu driver hỗ trợ.

### Bài 12. Tại sao setObject(index, null) không phải lựa chọn an toàn nhất?

**Đáp án:** Giá trị null không mang kiểu Java cụ thể. Driver có thể không suy ra kiểu SQL; cung cấp Types.X hoặc kiểu đích rõ ràng.

### Bài 13. Bind DATE bằng LocalDate

```java
ps.setObject(1, LocalDate.of(2000, 9, 1));
```

**Đáp án:** Phù hợp cột DATE với JDBC 4.2 và driver hỗ trợ.

### Bài 14. Timestamp có timezone

**Đáp án:** Với PostgreSQL TIMESTAMPTZ, có thể bind OffsetDateTime theo hỗ trợ driver. Thống nhất instant và timezone session; không lưu chuỗi hiển thị phụ thuộc locale.

### Bài 15. IN (?) với ba ID

**Câu hỏi:** Bind chuỗi "1,2,3" vào một placeholder có tương đương IN ba ID không?

**Đáp án:** Không. Đó là một giá trị. Cần ba placeholder hoặc array/table parameter phù hợp DBMS.

### Bài 16. Danh sách IN rỗng

**Đáp án:** Xác định empty list nghĩa là không có kết quả hay bỏ filter; không sinh IN () một cách mù quáng.

### Bài 17. LIKE và phần trăm

**Câu hỏi:** Input 50% được bind bằng PreparedStatement có còn wildcard không?

**Đáp án:** Có. Bind chống injection nhưng không vô hiệu hóa wildcard. Dùng ESCAPE nếu cần tìm literal.

### Bài 18. Bind tên cột ORDER BY

**Đáp án:** Không thể dùng placeholder giá trị. Dùng enum/whitelist identifier và chọn SQL fragment cố định.

### Bài 19. INSERT với cột DEFAULT

**Câu hỏi:** Bind SQL NULL cho cột có DEFAULT 5 có tự lưu 5 không?

**Đáp án:** Không. Bỏ cột khỏi INSERT hoặc dùng từ khóa SQL DEFAULT; bind NULL là yêu cầu ghi NULL.

### Bài 20. PATCH: không gửi field khác gửi null thế nào?

**Đáp án:** DTO cần biểu diễn presence riêng. present=false nghĩa giữ nguyên; present=true,value=null nghĩa đặt SQL NULL nếu hợp đồng cho phép.

### Bài 21. COALESCE(?, email) khi email NULL

**Đáp án:** Nếu tham số NULL, predicate email = email vẫn UNKNOWN đối với hàng có email NULL, nên không thực sự bỏ filter cho mọi hàng.

### Bài 22. PostgreSQL lỗi kiểu tham số chưa xác định

**Đáp án:** Kiểm tra vị trí placeholder, ngữ cảnh suy luận kiểu, setter và driver. Có thể cần CAST(? AS BIGINT) hoặc kiểu đích cụ thể khi placeholder không có ngữ cảnh.

### Bài 23. BigDecimal scale

**Câu hỏi:** new BigDecimal("1.0").equals(new BigDecimal("1.00")) có true không?

**Đáp án:** Không; equals xét scale. compareTo trả 0 theo giá trị số.

### Bài 24. ResultSet boolean nullable

**Đáp án:** getBoolean trả false nếu SQL NULL; dùng wasNull ngay sau getter hoặc getObject(..., Boolean.class).

### Bài 25. Batch có một tham số null

**Đáp án:** Gán đúng setNull và SQL type cho vị trí đó trước addBatch. Không để lại giá trị cũ của lần bind trước.

### Bài 26. PreparedStatement có an toàn khi nối ORDER BY input không?

**Đáp án:** Không. Placeholder chỉ bind giá trị, còn identifier động vẫn cần whitelist.

### Bài 27. JSONB PostgreSQL

**Đáp án:** Có thể dùng PGobject kiểu jsonb hoặc cast/kiểu binding driver hỗ trợ. Không mặc định setString luôn được hiểu là JSONB.

### Bài 28. SQL NULL với JSON null

**Đáp án:** SQL NULL là trạng thái của cột/parameter SQL; JSON null là giá trị null nằm bên trong tài liệu JSON. Cần kiểm tra theo kiểu và toán tử JSON của DBMS.

### Bài 29. Tại sao query chạy ở console nhưng JDBC lỗi?

**Đáp án:** Literal trong console và parameter protocol có thể có cách suy luận kiểu khác; kiểm tra setter, SQL type của NULL, driver/version và session settings.

### Bài 30. Log tham số thế nào?

**Đáp án:** Log query template, SQLState, operation ID và kiểu/trạng thái cần thiết; mask PII/token/secret. Không log toàn bộ tham số nhạy cảm.

## 44. Checklist trước khi bind một query trong ứng dụng

Trước khi gọi executeQuery hoặc executeUpdate, hãy xác định:

1. SQL có dùng PreparedStatement cho mọi giá trị dữ liệu không?
2. Placeholder JDBC có được đánh số từ 1 đúng thứ tự không?
3. Kiểu Java có khớp kiểu SQL không?
4. Tiền có dùng BigDecimal không?
5. DATE/TIMESTAMP có đúng ngữ nghĩa ngày, local time hay instant không?
6. Driver có hỗ trợ mapping kiểu đặc thù không?
7. Tham số có thể NULL không?
8. Nếu NULL, dùng setNull(index, Types.X) phù hợp chưa?
9. NULL có nghĩa bỏ filter, tìm NULL hay xóa giá trị?
10. API có phân biệt field không gửi và null không?
11. SQL có dùng IS NULL thay vì = NULL không?
12. Có toán tử null-safe phù hợp DBMS khi cần không?
13. IN list có empty list hoặc phần tử NULL không?
14. LIKE có cần escape wildcard không?
15. Identifier động có được whitelist không?
16. DEFAULT có bị nhầm với bind NULL không?
17. ResultSet nullable có dùng wrapper/wasNull không?
18. Batch có bind lại mọi parameter ở mỗi hàng không?
19. Transaction và retry có được xác định không?
20. Log có tránh PII và secret không?
21. Integration test có dùng đúng DBMS và driver không?
22. Có kiểm tra plan khi kiểu bind ảnh hưởng hiệu năng không?

## 45. Tổng kết

Bind tham số đúng kiểu giúp ứng dụng truyền **giá trị dữ liệu** tách khỏi cấu trúc SQL. Với JDBC, PreparedStatement và các setter như setLong, setBigDecimal, setString, setObject, setNull là công cụ cơ bản.

Xử lý NULL đòi hỏi thêm tư duy về ngữ nghĩa:

- Java null phải được bind thành SQL NULL bằng setter/SQL type phù hợp.
- SQL NULL không phải số 0, chuỗi rỗng hay Boolean false.
- Phép so sánh bằng với NULL không tìm được hàng có NULL; dùng IS NULL.
- Khi cần so sánh null-safe, dùng toán tử phù hợp DBMS hoặc predicate tường minh.
- NULL trong optional filter phải có hợp đồng rõ: bỏ filter, tìm NULL hay đặt lại giá trị.
- Bỏ cột khỏi INSERT/UPDATE khác với bind NULL; DEFAULT không tự chạy chỉ vì parameter là NULL.
- Kết quả nullable phải được map vào kiểu Java có thể biểu diễn null hoặc kiểm tra wasNull.
- PreparedStatement không bind identifier; tên bảng/cột và sort direction phải đến từ whitelist.
- Kiểu và cách xử lý NULL khác nhau giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite; kiểm thử với đúng driver.

**Kết luận:** Một repository an toàn không chỉ tạo câu SQL có dấu hỏi. Nó phải xác định rõ **mỗi tham số đại diện cho kiểu dữ liệu nào, NULL có ý nghĩa gì, driver gửi kiểu gì và database sẽ diễn giải điều kiện ra sao**. Khi các hợp đồng này rõ ràng, ứng dụng giảm SQL injection, lỗi chuyển kiểu, lỗi tìm kiếm NULL, sai lệch thời gian và những truy vấn khó tối ưu; đồng thời dữ liệu từ Java tới database được giữ đúng ý nghĩa nghiệp vụ.
