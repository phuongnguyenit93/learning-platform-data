# Bind kiểu dữ liệu, setNull và phân biệt JDBC type với Oracle type

Trong Oracle JDBC, bind variable không chỉ là một giá trị được gửi lên database. Driver còn phải truyền kiểu dữ liệu, độ dài, precision, scale và metadata liên quan để Oracle parse và thực thi SQL đúng cách. Nếu ứng dụng bind một cột NUMBER bằng chuỗi, bind DATE bằng kiểu thời gian không phù hợp hoặc gửi NULL mà không chỉ rõ kiểu, Oracle có thể phải suy luận/chuyển kiểu, phát sinh lỗi hoặc tạo execution plan kém ổn định.

Có nhiều lớp kiểu dữ liệu khác nhau: kiểu Java trong chương trình, kiểu JDBC chuẩn trong java.sql.Types/JDBCType, kiểu SQL của Oracle như NUMBER, VARCHAR2, DATE, TIMESTAMP, RAW, CLOB và kiểu vendor-specific trong Oracle JDBC như OracleTypes. Chúng có quan hệ ánh xạ, nhưng không phải một hệ kiểu duy nhất. Types.NUMERIC là mã kiểu JDBC, còn NUMBER(p,s) là kiểu SQL Oracle; Types.TIMESTAMP không mô tả hết khác biệt giữa TIMESTAMP, TIMESTAMP WITH TIME ZONE và TIMESTAMP WITH LOCAL TIME ZONE.

Bài học tập trung vào cách chọn setter đúng, truyền NULL có kiểu bằng setNull, dùng setObject có target type, xử lý date/time, số, text, national character, LOB và Oracle-specific types. Đồng thời giải thích tác động của bind datatype tới implicit conversion, index access, cursor sharing và khả năng tương thích giữa Java version với Oracle JDBC driver.

Sau bài học, bạn có thể:

- Phân biệt Java type, JDBC type và Oracle SQL type.
- Chọn setter tương ứng với datatype của cột.
- Dùng PreparedStatement.setNull đúng JDBC type.
- Hiểu vì sao setObject(index, null) hoặc setString cho mọi tham số dễ gây vấn đề.
- Xử lý NUMBER precision/scale bằng BigDecimal.
- Phân biệt DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE và TIMESTAMP WITH LOCAL TIME ZONE.
- Chọn setString hay setNString, setBytes hay stream/LOB setter.
- Bind Oracle collection, object type và REF CURSOR khi driver hỗ trợ.
- Đăng ký OUT parameter đúng kiểu với CallableStatement.
- Chẩn đoán implicit conversion, ORA-01722, ORA-01861 và cursor child mismatch.
- Kiểm thử bind metadata, SQL plan và hành vi trên đúng Oracle JDBC driver.

> API và mapping có thể khác theo JDK, JDBC specification và Oracle JDBC driver (ojdbc8/ojdbc11/ojdbc17...). Ví dụ dùng JDBC phổ biến; kiểm tra Oracle JDBC Developer's Guide và tài liệu driver tương ứng với phiên bản ứng dụng/database.

## 1. Ba lớp kiểu dữ liệu cần phân biệt

### 1.1. Java type

Đây là kiểu dữ liệu trong chương trình Java, ví dụ:

- String
- Integer, Long, Short
- BigDecimal
- Float, Double
- Boolean
- LocalDate, LocalDateTime, OffsetDateTime
- java.sql.Date, java.sql.Timestamp
- byte[], InputStream
- Reader, Clob, Blob

Java type biểu diễn dữ liệu trong JVM. Nó chưa tự xác định Oracle sẽ nhận một bind variable có SQL datatype nào trong mọi trường hợp.

### 1.2. JDBC type

JDBC định nghĩa kiểu dữ liệu chuẩn để driver giao tiếp với database. Các mã truyền thống nằm trong java.sql.Types, ví dụ:

- Types.VARCHAR
- Types.CHAR
- Types.INTEGER
- Types.BIGINT
- Types.NUMERIC
- Types.DECIMAL
- Types.DATE
- Types.TIMESTAMP
- Types.BINARY
- Types.VARBINARY
- Types.BLOB
- Types.CLOB
- Types.NCLOB
- Types.ARRAY
- Types.STRUCT
- Types.REF_CURSOR (JDBC 4.2)

Từ JDBC 4.2 có enum java.sql.JDBCType, ví dụ JDBCType.VARCHAR, JDBCType.NUMERIC, JDBCType.TIMESTAMP. Enum này triển khai SQLType và giúp code dễ đọc hơn.

### 1.3. Oracle SQL type

Đây là datatype thật của column/expression trong Oracle Database, ví dụ:

- NUMBER(p,s), BINARY_FLOAT, BINARY_DOUBLE.
- CHAR, VARCHAR2, NCHAR, NVARCHAR2.
- DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE, TIMESTAMP WITH LOCAL TIME ZONE.
- RAW, LONG RAW.
- CLOB, NCLOB, BLOB, BFILE.
- ROWID, UROWID.
- INTERVAL YEAR TO MONTH, INTERVAL DAY TO SECOND.
- XMLTYPE, JSON và các datatype/feature theo phiên bản.
- Object type, collection type (nested table/VARRAY), REF CURSOR ở API/PLSQL context.

Oracle SQL type có semantics riêng. Ví dụ Oracle DATE lưu cả ngày và giờ tới giây; JDBC Types.DATE thường mang semantics ngày không có time-of-day. Oracle NUMBER có precision/scale khác với Java double.

### 1.4. Oracle JDBC type extension

Oracle JDBC cung cấp các API và hằng số mở rộng, thường qua package oracle.jdbc, ví dụ OracleTypes và OracleConnection. Chúng cần thiết khi JDBC chuẩn không biểu diễn đầy đủ một Oracle-specific type hoặc feature.

Ví dụ vendor-specific có thể bao gồm CURSOR, BINARY_FLOAT, BINARY_DOUBLE, TIMESTAMP WITH TIME ZONE, TIMESTAMP WITH LOCAL TIME ZONE, INTERVAL, STRUCT, ARRAY và các kiểu Oracle khác. Tên hằng số/API chính xác phụ thuộc driver version.

### 1.5. Quan hệ giữa các lớp

```text
JAVA VALUE
   String / BigDecimal / LocalDateTime / byte[]
             |
             v
JDBC BIND API
   setString / setBigDecimal / setTimestamp / setBytes
   setNull(index, jdbcType)
   setObject(index, value, targetSqlType)
             |
             v
ORACLE JDBC DRIVER
   Mapping + conversion + bind metadata
             |
             v
ORACLE SQL TYPE
   VARCHAR2 / NUMBER / DATE / TIMESTAMP / RAW / CLOB ...
             |
             v
SQL EXECUTION
   Comparison / INSERT / UPDATE / procedure call
```

### 1.6. Quy tắc quan trọng

Setter xác định cách driver biểu diễn giá trị bind. Datatype của column được định nghĩa trong schema. Hai bên nên tương thích để tránh implicit conversion và giữ SQL semantics ổn định.

Không phải lúc nào một JDBC type cũng ánh xạ một-một tới đúng một Oracle type. Driver có thể dùng internal representation hoặc Oracle extension; hãy quan tâm tới SQL semantics cuối cùng và tài liệu driver.

## 2. java.sql.Types và JDBCType

### 2.1. java.sql.Types

Types là lớp chứa các hằng số int được JDBC dùng trong setNull, registerOutParameter, metadata và API tương tự.

Ví dụ:

```java
import java.sql.Types;

int textType = Types.VARCHAR;
int numberType = Types.NUMERIC;
int timestampType = Types.TIMESTAMP;
```

Đây là mã kiểu JDBC, không phải tên Oracle datatype.

### 2.2. java.sql.JDBCType

JDBC 4.2 bổ sung enum JDBCType, triển khai SQLType:

```java
import java.sql.JDBCType;

JDBCType textType = JDBCType.VARCHAR;
JDBCType numberType = JDBCType.NUMERIC;
JDBCType timestampType = JDBCType.TIMESTAMP;
```

JDBCType có thể dùng với overload setObject/registerOutParameter nhận SQLType nếu driver hỗ trợ JDBC version tương ứng.

### 2.3. Khi nào dùng Types và khi nào dùng JDBCType?

- Dùng Types.* khi API nhận int, như PreparedStatement.setNull(index, sqlType).
- Dùng JDBCType.* khi API nhận SQLType và driver/JDK hỗ trợ.
- Dùng OracleTypes.* khi cần Oracle-specific type mà JDBC chuẩn không mô tả đầy đủ.

Không truyền một mã OracleTypes vào API chỉ mong đợi tên Oracle SQL datatype dạng string, hoặc ngược lại.

### 2.4. Types.NUMERIC và Types.DECIMAL

Hai kiểu này gần nhau trong JDBC và thường được dùng cho Oracle NUMBER. NUMERIC/DECIMAL là generic JDBC category; Oracle NUMBER(p,s) vẫn có precision/scale riêng. Với giá trị decimal chính xác, Java BigDecimal thường là lựa chọn phù hợp.

### 2.5. Types.DATE và Types.TIMESTAMP

JDBC DATE có semantics ngày, còn TIMESTAMP có fractional seconds. Oracle DATE cũng chứa time tới giây, do đó không suy ra mapping chỉ từ tên giống nhau. Chọn API dựa trên semantics nghiệp vụ và kiểm tra mapping của driver.

## 3. Setter của PreparedStatement

### 3.1. Dùng PreparedStatement

PreparedStatement tách SQL text khỏi giá trị bind:

```java
String sql = """
    INSERT INTO customers (customer_id, full_name, credit_limit)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setString(2, fullName);
    ps.setBigDecimal(3, creditLimit);
    ps.executeUpdate();
}
```

Driver gửi bind values với metadata, tránh nối giá trị trực tiếp vào SQL text và giúp statement có thể được reuse.

### 3.2. Chọn setter theo Java value và column

| Java value | Setter thường dùng | JDBC category thường gặp | Oracle column thường gặp |
| --- | --- | --- | --- |
| String | setString | VARCHAR | VARCHAR2 |
| String cho fixed-width | setString | CHAR/VARCHAR | CHAR |
| Integer | setInt | INTEGER | NUMBER(p,0) |
| Long | setLong | BIGINT | NUMBER(p,0) |
| BigDecimal | setBigDecimal | DECIMAL/NUMERIC | NUMBER(p,s) |
| Float | setFloat | REAL/FLOAT | BINARY_FLOAT hoặc NUMBER tùy schema/driver |
| Double | setDouble | DOUBLE | BINARY_DOUBLE hoặc NUMBER tùy schema/driver |
| Boolean | setBoolean | BOOLEAN | SQL BOOLEAN nếu release hỗ trợ; mapping khác ở release cũ |
| java.sql.Date | setDate | DATE | DATE |
| java.sql.Timestamp | setTimestamp | TIMESTAMP | TIMESTAMP hoặc Oracle DATE theo contract |
| byte[] | setBytes | VARBINARY/BINARY | RAW |
| InputStream | setBinaryStream | BLOB/binary stream | BLOB |
| Reader | setCharacterStream | CLOB/text stream | CLOB |
| String quốc gia | setNString | NVARCHAR | NVARCHAR2/NCHAR |

Bảng là hướng dẫn khởi đầu, không phải mapping tuyệt đối cho mọi driver/release.

### 3.3. Không bind tất cả bằng setString

Nếu cột là NUMBER mà ứng dụng gọi setString, Oracle/driver có thể phải chuyển character value sang number. Điều này phụ thuộc SQL expression và bind metadata; conversion có thể làm phát sinh ORA-01722, phụ thuộc NLS hoặc làm predicate kém thân thiện với index.

Tương tự, bind ngày giờ bằng string khiến việc parse phụ thuộc format/NLS nếu SQL không dùng TO_DATE/TO_TIMESTAMP với mask rõ ràng. Nên truyền typed value.

### 3.4. Không bind mọi số bằng setDouble

Double dùng floating-point binary và không biểu diễn chính xác mọi decimal. Tiền tệ, tỷ lệ và số cần decimal exact nên dùng BigDecimal và setBigDecimal.

### 3.5. Setter phải khớp thứ tự placeholder

Parameter index bắt đầu từ 1, không phải 0:

```java
String sql = "UPDATE orders SET status = ?, amount = ? WHERE order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, status);
    ps.setBigDecimal(2, amount);
    ps.setLong(3, orderId);
    ps.executeUpdate();
}
```

Đặt nhầm index có thể tạo lỗi datatype hoặc ghi sai dữ liệu. Dùng hằng số index có tên hoặc helper bind theo thứ tự để giảm lỗi ở SQL dài.

### 3.6. Bind cùng một parameter nhiều lần?

Mỗi dấu ? là một parameter riêng. Nếu cùng một giá trị xuất hiện hai lần trong SQL, cần bind hai vị trí:

```java
String sql = """
    SELECT *
    FROM orders
    WHERE created_at >= ?
      AND updated_at < ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, fromTime);
    ps.setTimestamp(2, toTime);
}
```

## 4. setNull và typed NULL

### 4.1. NULL không tự mang datatype

Trong SQL, NULL biểu thị giá trị không xác định/không có giá trị. Khi bind một NULL, driver cần biết kiểu SQL của parameter để gửi metadata phù hợp và Oracle cần giải quyết datatype của expression.

Một NULL có kiểu VARCHAR2 khác NULL có kiểu NUMBER hoặc DATE trong context SQL. Vì vậy, setNull cần cả parameter index và JDBC type.

### 4.2. Cú pháp setNull

```java
ps.setNull(parameterIndex, sqlType);
```

Ví dụ:

```java
ps.setNull(1, Types.VARCHAR);
ps.setNull(2, Types.NUMERIC);
ps.setNull(3, Types.DATE);
ps.setNull(4, Types.TIMESTAMP);
```

Parameter index bắt đầu từ 1. sqlType là mã JDBC type trong java.sql.Types, hoặc mã type tương thích mà driver hỗ trợ.

### 4.3. Ví dụ INSERT có nullable columns

Giả sử schema:

```sql
CREATE TABLE jdbc_bind_lab (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100),
    amount NUMBER(12,2),
    event_time TIMESTAMP
);
```

Java:

```java
String sql = """
    INSERT INTO jdbc_bind_lab (id, note, amount, event_time)
    VALUES (?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 10L);
    ps.setNull(2, Types.VARCHAR);
    ps.setNull(3, Types.NUMERIC);
    ps.setNull(4, Types.TIMESTAMP);
    ps.executeUpdate();
}
```

### 4.4. Vì sao không chỉ gọi setObject(index, null)?

setObject(index, null) không nói rõ kiểu mong muốn trong code. Cách driver xử lý có thể phụ thuộc driver/JDBC version và SQL context; một số biểu thức hoặc procedure overload không thể suy luận duy nhất datatype. Dùng setNull(index, jdbcType) làm intent rõ và tránh phụ thuộc vào inference.

Nếu dùng overload setObject(index, null, targetSqlType) hoặc setObject(index, null, JDBCType.VARCHAR), vẫn cần xác nhận driver hỗ trợ overload đó và target type đúng.

### 4.5. NULL trong expression có thể mơ hồ

Ví dụ SQL:

```sql
SELECT COALESCE(?, ?) FROM dual;
```

Nếu cả hai bind đều NULL và không có context type rõ, Oracle có thể không xác định được kiểu kết quả mong muốn. Có thể CAST bind/NULL:

```sql
SELECT COALESCE(
         CAST(? AS VARCHAR2(30)),
         CAST(? AS VARCHAR2(30))
       )
FROM dual;
```

Typed NULL giúp driver và SQL engine giải quyết expression chính xác hơn.

### 4.6. NULL cho NUMBER

```java
ps.setNull(1, Types.NUMERIC);
```

Nếu SQL/procedure yêu cầu precision/scale cụ thể, column hoặc expression xác định NUMBER(p,s). JDBC Types.NUMERIC không truyền precision/scale của column; nó chỉ phân loại kiểu parameter. Dùng BigDecimal cho giá trị không NULL và schema/procedure contract để xác định precision/scale.

### 4.7. NULL cho character và national character

```java
ps.setNull(1, Types.VARCHAR);  // VARCHAR2/character
ps.setNull(2, Types.NVARCHAR); // national character
ps.setNull(3, Types.CLOB);     // CLOB
ps.setNull(4, Types.NCLOB);    // NCLOB
```

Đảm bảo JDBC type tương ứng column/parameter thực tế. Nếu driver yêu cầu Oracle-specific type cho NCLOB hoặc một vendor type, dùng API được tài liệu driver hỗ trợ.

### 4.8. NULL cho LOB và binary

```java
ps.setNull(1, Types.BLOB);
ps.setNull(2, Types.CLOB);
ps.setNull(3, Types.VARBINARY);
```

Không dùng Types.VARCHAR cho một parameter BLOB chỉ vì giá trị Java hiện tại là null. Type cần phản ánh SQL contract, không phải giá trị có mặt hay không.

### 4.9. NULL trong IN list

```sql
WHERE customer_id IN (?, ?, ?)
```

Bind NULL trong IN list không tương đương bỏ parameter khỏi danh sách. SQL three-valued logic khiến so sánh với NULL là UNKNOWN. Nếu ứng dụng cần bỏ qua điều kiện khi filter null, phải thiết kế predicate rõ ràng hoặc tạo SQL structure phù hợp; không kỳ vọng setNull tự bỏ qua điều kiện.

## 5. setObject và target SQL type

### 5.1. setObject không target type

```java
ps.setObject(1, value);
```

Driver suy luận JDBC type từ runtime Java class. Cách này tiện với Java types chuẩn, nhưng có thể tạo mapping không mong muốn khi dùng class tùy biến, null, temporal type hoặc Oracle-specific type.

### 5.2. setObject có JDBC type

```java
ps.setObject(1, value, Types.NUMERIC);
ps.setObject(2, value, Types.VARCHAR);
```

Overload này nói rõ target JDBC type. Có thể dùng JDBCType/SQLType trong overload tương ứng nếu driver hỗ trợ JDBC 4.2.

### 5.3. Scale cho DECIMAL/NUMERIC

Một số overload setObject nhận target SQL type và scale/length. Scale có ý nghĩa với numeric conversion; hãy xác định rounding/truncation policy trước khi bind.

```java
ps.setObject(1, new BigDecimal("123.456"),
            Types.DECIMAL, 2);
```

Không mặc định rằng mọi driver đều xử lý rounding giống nhau khi chuyển scale. Nếu nghiệp vụ cần rounding cụ thể, xử lý BigDecimal bằng setScale với RoundingMode rõ ràng trước khi bind.

### 5.4. setObject với java.time

JDBC 4.2 hỗ trợ một số java.time classes qua setObject, nhưng hỗ trợ cụ thể phụ thuộc driver:

```java
ps.setObject(1, LocalDate.of(2026, 11, 14));
ps.setObject(2, LocalDateTime.of(2026, 11, 14, 10, 30));
ps.setObject(3, OffsetDateTime.parse("2026-11-14T10:30:00+07:00"));
```

Kiểm thử round-trip và timezone semantics trên driver đang triển khai. Với code cần tương thích driver cũ, dùng java.sql.Date/Timestamp hoặc Oracle JDBC extension có tài liệu rõ.

### 5.5. Không ép target type để che schema mismatch

setObject(index, value, Types.VARCHAR) không làm cho một cột NUMBER trở thành VARCHAR2. Nếu schema là NUMBER, bind NUMBER theo contract; chỉ bind character khi SQL/procedure thực sự định nghĩa parameter character.

## 6. Mapping số: NUMBER và Java numeric

### 6.1. Oracle NUMBER

NUMBER hỗ trợ precision/scale rộng, bao gồm số decimal chính xác. Dùng BigDecimal để giữ giá trị decimal trong Java:

```java
BigDecimal amount = new BigDecimal("12345.67");
ps.setBigDecimal(1, amount);
```

Không tạo BigDecimal từ double nếu cần chính xác decimal:

```java
new BigDecimal(0.1);       // mang sai số binary của double
new BigDecimal("0.1");     // decimal chính xác theo chuỗi
```

### 6.2. NUMBER(p,0)

Với NUMBER(p,0), Java integral type phù hợp nếu miền giá trị không vượt giới hạn:

| Oracle | Java gợi ý |
| --- | --- |
| NUMBER(3,0) | short/int |
| NUMBER(9,0) | int |
| NUMBER(18,0) | long nếu range phù hợp |
| NUMBER(38,0) | BigDecimal |

Các con số trên là định hướng, không thay thế kiểm tra min/max thực tế và signed range của Java type.

### 6.3. NUMBER(p,s)

Với số thập phân, dùng BigDecimal và kiểm tra:

- precision: tổng số chữ số có ý nghĩa.
- scale: số chữ số sau dấu thập phân.
- rounding mode.
- overflow và scale mismatch.

Ví dụ:

```java
BigDecimal value = new BigDecimal("123.4567");
BigDecimal normalized =
    value.setScale(2, RoundingMode.HALF_UP);
ps.setBigDecimal(1, normalized);
```

Chọn RoundingMode theo business rule; không tự động làm tròn mọi dữ liệu.

### 6.4. BINARY_FLOAT và BINARY_DOUBLE

Oracle BINARY_FLOAT/BINARY_DOUBLE là floating-point binary types. Có thể dùng setFloat/setDouble nếu column/parameter được thiết kế cho floating point. Chúng khác NUMBER về precision, rounding và representation.

### 6.5. Không nhầm BIGINT với NUMBER(38)

JDBC BIGINT tương ứng Java long range; Oracle NUMBER có thể chứa miền rộng hơn. Nếu cột NUMBER có giá trị vượt Long.MAX_VALUE hoặc Long.MIN_VALUE, dùng BigDecimal thay vì getLong/setLong.

### 6.6. NULL numeric

Dùng setNull(index, Types.NUMERIC) hoặc type tương ứng của API. Không dùng setInt(index, 0) để biểu diễn NULL; zero là một giá trị hợp lệ khác NULL.

## 7. Mapping DATE và TIMESTAMP

### 7.1. Oracle DATE không giống JDBC DATE hoàn toàn

Oracle DATE lưu năm, tháng, ngày, giờ, phút và giây. JDBC DATE được thiết kế cho SQL DATE mang ý nghĩa ngày, không biểu diễn fractional seconds và không phải lúc nào cũng giữ time-of-day theo cách ứng dụng mong muốn.

Nếu column Oracle DATE chứa cả ngày và giờ, hãy kiểm tra driver mapping và cân nhắc java.sql.Timestamp/setTimestamp hoặc java.time LocalDateTime với driver hỗ trợ. Không dùng getDate nếu cần giữ phần giờ.

### 7.2. java.sql.Date

java.sql.Date biểu diễn date-only. Dùng khi nghiệp vụ thật sự chỉ cần ngày:

```java
LocalDate localDate = LocalDate.of(2026, 11, 14);
java.sql.Date sqlDate = java.sql.Date.valueOf(localDate);
ps.setDate(1, sqlDate);
```

Không dùng cho thời điểm có giờ/phút/giây cần bảo toàn.

### 7.3. java.sql.Timestamp

Timestamp biểu diễn date-time với fractional seconds:

```java
LocalDateTime localDateTime =
    LocalDateTime.of(2026, 11, 14, 21, 18, 30, 123_000_000);
Timestamp timestamp = Timestamp.valueOf(localDateTime);
ps.setTimestamp(1, timestamp);
```

Oracle TIMESTAMP hỗ trợ fractional seconds theo precision của column. Kiểm tra scale/precision và rounding khi Java có nanoseconds nhưng column lưu ít chữ số hơn.

### 7.4. Calendar overload

JDBC có overload setDate(index, date, Calendar) và setTimestamp(index, timestamp, Calendar). Calendar cho phép xác định timezone dùng khi chuyển đổi giá trị trong một số driver/API path.

```java
Calendar utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
ps.setTimestamp(1, timestamp, utc);
```

Đừng truyền Calendar tùy tiện; phải thống nhất timezone contract giữa ứng dụng, JDBC connection/session và Oracle datatype.

### 7.5. TIMESTAMP WITH TIME ZONE

Oracle TIMESTAMP WITH TIME ZONE giữ thông tin timezone/offset cùng timestamp theo semantics Oracle. Khi dùng java.time, OffsetDateTime là kiểu tự nhiên để biểu diễn thời điểm có offset:

```java
OffsetDateTime value =
    OffsetDateTime.parse("2026-11-14T21:18:30+07:00");
ps.setObject(1, value);
```

Khả năng mapping trực tiếp phụ thuộc JDBC driver. Nếu cần dùng Oracle-specific API, tham khảo Oracle JDBC guide cho Oracle TIMESTAMPTZ/OracleTypes.TIMESTAMPTZ.

### 7.6. OffsetDateTime và ZonedDateTime

OffsetDateTime giữ local date-time và UTC offset. ZonedDateTime còn giữ ZoneId như Asia/Ho_Chi_Minh. Không phải mọi Oracle JDBC driver đều bind ZonedDateTime trực tiếp theo cách bảo toàn ZoneId. Nếu nghiệp vụ cần lưu tên vùng timezone, lưu riêng ZoneId hoặc dùng mapping Oracle được tài liệu hỗ trợ.

### 7.7. TIMESTAMP WITH LOCAL TIME ZONE

TIMESTAMP WITH LOCAL TIME ZONE chuẩn hóa thời điểm theo database timezone khi lưu và hiển thị theo session time zone khi truy vấn. Giá trị trả về không giữ nguyên zone identifier/offset ban đầu như TSTZ.

Điều này làm session time zone trở thành một phần quan trọng của semantics. Cùng một giá trị lưu có thể được hiển thị khác nhau khi hai session dùng TIME_ZONE khác nhau.

### 7.8. Session time zone

Kiểm tra:

```sql
SELECT
    SESSIONTIMEZONE,
    DBTIMEZONE,
    CURRENT_TIMESTAMP,
    SYSTIMESTAMP,
    CURRENT_DATE,
    SYSDATE
FROM dual;
```

DBTIMEZONE và SESSIONTIMEZONE có mục đích khác nhau. Không mặc định server timezone, JVM default timezone và Oracle session timezone giống nhau.

### 7.9. java.time API

Mapping khởi điểm:

| Java time type | JDBC/Oracle semantics thường dùng |
| --- | --- |
| LocalDate | SQL DATE/date-only |
| LocalTime | TIME semantics; Oracle SQL TIME riêng không phổ biến |
| LocalDateTime | TIMESTAMP không timezone |
| OffsetDateTime | TIMESTAMP WITH TIME ZONE nếu driver hỗ trợ |
| Instant | Một thời điểm UTC; thường chuyển sang Timestamp/OffsetDateTime theo contract |
| ZonedDateTime | Cần kiểm tra driver; ZoneId có thể cần lưu riêng |

Đừng tự động đổi Instant sang LocalDateTime mà bỏ UTC/offset nếu cần xác định một thời điểm duy nhất.

### 7.10. Tránh bind ngày giờ bằng String

Không nên:

```java
ps.setString(1, "14/11/2026 21:18:30");
```

Nếu SQL so sánh với DATE/TIMESTAMP, Oracle có thể implicit convert theo NLS format và gây lỗi/khác kết quả giữa môi trường. Dùng typed setter hoặc explicit conversion với format mask rõ khi input contract bắt buộc là text.

## 8. Mapping character: CHAR, VARCHAR2, NCHAR, NVARCHAR2

### 8.1. setString

setString là lựa chọn phổ biến cho VARCHAR2/CHAR:

```java
ps.setString(1, "Nguyen Van A");
```

Driver bind theo character type tương ứng. Oracle column vẫn quyết định length semantics, collation và constraint.

### 8.2. CHAR và blank padding

CHAR là fixed-length character type và có blank-padding semantics. Khi so sánh hoặc lấy dữ liệu, khoảng trắng cuối có thể được xử lý khác VARCHAR2. Java String không tự thể hiện sự khác biệt này; ứng dụng cần hiểu column definition.

### 8.3. VARCHAR2

VARCHAR2 lưu chuỗi biến độ dài. Dùng setString cho giá trị text thông thường. Kiểm tra max length theo BYTE/CHAR semantics và database character set.

### 8.4. NCHAR và NVARCHAR2

National character types dùng national character set. Khi bind, JDBC cung cấp setNString/setNCharacterStream cho NCHAR/NVARCHAR2/NCLOB:

```java
ps.setNString(1, "Tiếng Việt – dữ liệu Unicode");
```

setString có thể dùng được trong nhiều trường hợp nhờ driver/database conversion, nhưng setNString thể hiện rõ intent national character. Kiểm tra driver và character set nếu dữ liệu đa ngôn ngữ.

### 8.5. setNCharacterStream

Với text Unicode dạng stream:

```java
try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    ps.setNCharacterStream(1, reader);
    ps.executeUpdate();
}
```

Đảm bảo stream còn mở trong lúc execute; đóng stream sau khi driver đã tiêu thụ xong theo contract.

### 8.6. BYTE và CHAR length semantics

VARCHAR2(100 BYTE) giới hạn theo byte; VARCHAR2(100 CHAR) giới hạn theo ký tự. Với UTF-8/multibyte characters, 100 ký tự có thể vượt 100 byte. Ứng dụng không nên chỉ dùng String.length() để dự đoán byte length Oracle.

### 8.7. Empty string và NULL

Trong Oracle SQL, chuỗi zero-length cho character datatype được xử lý như NULL trong nhiều ngữ cảnh. Java String rỗng và Java null là hai giá trị khác nhau trong chương trình, nhưng khi bind vào Oracle VARCHAR2, empty string có thể trở thành NULL. Nếu nghiệp vụ cần phân biệt “không nhập” với “chuỗi rỗng”, lưu thêm trạng thái/flag hoặc quy ước rõ.

### 8.8. Collation và case sensitivity

Bind type character không quyết định collation. Kết quả so sánh phụ thuộc datatype/collation, NLS_COMP/NLS_SORT và collation được cấu hình. Không giả định setString tự động làm comparison case-insensitive.

## 9. RAW, BLOB và binary values

### 9.1. RAW

RAW lưu byte sequence có giới hạn độ dài theo release. Dùng setBytes cho payload nhỏ:

```java
byte[] digest = MessageDigest.getInstance("SHA-256")
    .digest(payload);
ps.setBytes(1, digest);
```

Không mã hóa byte[] thành hex string rồi bind VARCHAR2 nếu column là RAW, trừ khi SQL contract yêu cầu text encoding.

### 9.2. BLOB

BLOB phù hợp binary lớn. Dùng setBinaryStream hoặc setBlob:

```java
try (InputStream in = Files.newInputStream(filePath)) {
    ps.setBinaryStream(1, in, Files.size(filePath));
    ps.executeUpdate();
}
```

Overload có length dùng long/int tùy JDBC API/driver. Đảm bảo length đúng và stream còn mở tới khi execute hoàn tất.

### 9.3. Blob object

Nếu dùng java.sql.Blob, có thể bind qua setBlob. Blob thường gắn với connection/transaction; không giữ locator lâu hơn lifecycle của connection.

### 9.4. RAW khác BLOB

RAW là scalar binary value có giới hạn chiều dài; BLOB là large object locator/content. Chọn datatype theo kích thước, cách truy cập và nhu cầu streaming. Không dùng RAW cho file lớn.

### 9.5. NULL binary

```java
ps.setNull(1, Types.VARBINARY); // RAW-like binary mapping
ps.setNull(2, Types.BLOB);
```

Với Oracle RAW cụ thể, kiểm tra driver mapping JDBC VARBINARY/BINARY và dùng Oracle extension nếu cần.

## 10. CLOB, NCLOB và character streams

### 10.1. CLOB

CLOB lưu character large object. Có thể bind String cho dữ liệu nhỏ nếu giới hạn/driver phù hợp, hoặc dùng setCharacterStream/Clob cho dữ liệu lớn.

```java
try (Reader reader = Files.newBufferedReader(textPath, StandardCharsets.UTF_8)) {
    ps.setCharacterStream(1, reader);
    ps.executeUpdate();
}
```

### 10.2. NCLOB

NCLOB lưu national character large object. Dùng setNCharacterStream/setNClob theo driver support:

```java
try (Reader reader = Files.newBufferedReader(textPath, StandardCharsets.UTF_8)) {
    ps.setNCharacterStream(1, reader);
    ps.executeUpdate();
}
```

### 10.3. Length và stream lifecycle

Một số overload yêu cầu khai báo length; có overload nhận long length trong JDBC mới. Đừng khai báo sai length hoặc đóng stream trước execute. Với stream không biết trước độ dài, dùng overload không length nếu driver hỗ trợ và kiểm tra performance.

### 10.4. LOB locator và transaction

LOB locator thường gắn với connection/transaction. Đọc/ghi LOB sau khi connection đóng hoặc transaction kết thúc có thể thất bại. Giữ lifecycle rõ ràng, không trả locator ra khỏi tầng repository mà không quản lý resource.

### 10.5. NULL LOB

Dùng setNull với Types.CLOB/NCLOB/BLOB tương ứng. Không truyền empty Reader/empty InputStream để thay NULL trừ khi nghiệp vụ muốn LOB rỗng (và hiểu semantics Oracle).

## 11. Oracle-specific types và OracleTypes

### 11.1. Khi nào cần Oracle extension?

JDBC chuẩn bao phủ phần lớn scalar type phổ biến. Một số Oracle type/feature không có mapping chuẩn đủ chi tiết, hoặc driver version cũ yêu cầu API vendor-specific. Khi đó có thể cần OracleTypes, OracleConnection hoặc các class trong oracle.jdbc.

Ưu tiên JDBC standard type nếu nó mô tả đúng semantics và driver hỗ trợ. Chỉ dùng Oracle extension khi cần tính năng Oracle-specific hoặc mapping chuẩn không đáp ứng.

### 11.2. OracleTypes

Oracle JDBC có class hằng số OracleTypes để đại diện các datatype/feature của Oracle. Tùy driver version, các hằng số có thể gồm CURSOR, TIMESTAMP, TIMESTAMPTZ, TIMESTAMPLTZ, INTERVALYM, INTERVALDS, BINARY_FLOAT, BINARY_DOUBLE, STRUCT, ARRAY và các type khác.

Ví dụ dạng API legacy:

```java
import oracle.jdbc.OracleTypes;

callable.registerOutParameter(1, OracleTypes.CURSOR);
```

Với driver hỗ trợ JDBC 4.2, có thể dùng Types.REF_CURSOR cho REF CURSOR. Kiểm tra Oracle JDBC version trước khi chọn API; không copy hằng số từ một ojdbc version sang driver khác mà không build/test.

### 11.3. REF CURSOR

REF CURSOR là cursor handle được PL/SQL trả về cho client. JDBC chuẩn có Types.REF_CURSOR từ JDBC 4.2; Oracle driver cũ hơn có thể dùng OracleTypes.CURSOR.

Ví dụ:

```java
String call = "{ call customer_api.list_customers(?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.registerOutParameter(1, Types.REF_CURSOR);
    cs.execute();

    try (ResultSet rs = (ResultSet) cs.getObject(1)) {
        while (rs.next()) {
            long id = rs.getLong("customer_id");
            String name = rs.getString("full_name");
        }
    }
}
```

Kiểm tra driver có hỗ trợ Types.REF_CURSOR và procedure signature thực tế. Cursor ResultSet phải được đóng; nó có thể giữ server cursor và tài nguyên database.

### 11.4. STRUCT và Oracle object type

Oracle object type có thể được biểu diễn qua java.sql.Struct hoặc mapping Java class tùy driver/API. Ví dụ:

```sql
CREATE TYPE address_t AS OBJECT (
    street VARCHAR2(100),
    city   VARCHAR2(60)
);

CREATE TABLE customer_address (
    customer_id NUMBER,
    address     address_t
);
```

JDBC:

```java
Object[] attributes = {"12 Nguyen Hue", "Ho Chi Minh City"};
Struct address = connection.createStruct(
    "APP.ADDRESS_T", attributes);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customer_address(customer_id, address) VALUES (?, ?)")) {
    ps.setLong(1, 100L);
    ps.setObject(2, address);
    ps.executeUpdate();
}
```

Tên type thường phải ghi schema chính xác. Cách tạo Struct và hỗ trợ UDT phụ thuộc Oracle JDBC driver; Oracle-specific type mapping có thể cần OracleConnection/OracleData API.

### 11.5. NULL cho STRUCT/ARRAY có type name

JDBC có overload setNull nhận typeName:

```java
ps.setNull(1, Types.STRUCT, "APP.ADDRESS_T");
```

Type name giúp driver xác định named SQL type. Với collection, dùng Types.ARRAY và tên collection type phù hợp nếu driver hỗ trợ. Kiểm tra schema qualification và quyền EXECUTE type.

### 11.6. Collection và ARRAY

Oracle nested table/VARRAY là named collection type. Không giả định Connection.createArrayOf hoạt động giống mọi database; Oracle JDBC thường cung cấp OracleConnection.createOracleArray với tên SQL collection type:

```java
OracleConnection oracleConnection =
    connection.unwrap(OracleConnection.class);

Array values = oracleConnection.createOracleArray(
    "APP.NUMBER_LIST_T",
    new BigDecimal[] {
        new BigDecimal("10"),
        new BigDecimal("20")
    });

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO batch_ids(ids) VALUES (?)")) {
    ps.setArray(1, values);
    ps.executeUpdate();
} finally {
    values.free();
}
```

Đây là ví dụ minh họa. Collection type phải được tạo trước trong Oracle và tên phải khớp chính xác. Oracle JDBC API cụ thể phụ thuộc driver; tránh dùng class oracle.sql.ARRAY legacy nếu driver mới có API thay thế.

### 11.7. INTERVAL

Oracle INTERVAL YEAR TO MONTH và INTERVAL DAY TO SECOND không ánh xạ trực tiếp hoàn hảo với mọi Java Duration/Period. Period biểu diễn năm/tháng; Duration biểu diễn thời lượng theo giây/nanosecond. Chọn mapping theo semantics và dùng Oracle-specific API nếu cần giữ chính xác interval type.

### 11.8. ROWID và UROWID

JDBC có java.sql.RowId. Oracle ROWID/UROWID có semantics định vị row; không dùng làm business key ổn định hoặc định danh xuyên database. Nếu bind, dùng RowId/setRowId khi driver hỗ trợ và không serialize ROWID như khóa nghiệp vụ.

### 11.9. BFILE

BFILE là locator tới file bên ngoài database và thường chỉ đọc qua Oracle-specific APIs. Nó không giống BLOB; nội dung file không được lưu trong datafile như LOB nội bộ. Xử lý BFILE cần quyền directory object và lifecycle locator đúng cách.

### 11.10. XMLTYPE và JSON

XMLTYPE/JSON support phụ thuộc Oracle Database release và JDBC driver. Một số phiên bản cung cấp Oracle-specific XML/JSON API; phiên bản mới có thêm JDBC mapping cho JSON. Không mặc định setString vào mọi parameter JSON là giữ nguyên binary/native JSON semantics. Xác nhận column type, driver API và round-trip behavior.

## 12. BOOLEAN: SQL BOOLEAN và PL/SQL BOOLEAN

### 12.1. PL/SQL BOOLEAN

PL/SQL BOOLEAN tồn tại từ lâu trong PL/SQL, nhưng các Oracle Database release trước 23ai không có SQL BOOLEAN column type để dùng trực tiếp trong table/query như datatype SQL thông thường.

Một số Oracle JDBC driver cung cấp extension để bind PL/SQL BOOLEAN trong procedure/function call. Hằng số/API cụ thể phụ thuộc driver, ví dụ OracleTypes.PLSQL_BOOLEAN ở các phiên bản có hỗ trợ.

### 12.2. SQL BOOLEAN trong release mới

Oracle Database 23ai bổ sung SQL BOOLEAN. Với database/driver hỗ trợ, JDBC boolean mapping có thể dùng setBoolean/getBoolean hoặc JDBCType.BOOLEAN tùy driver version.

Không dùng JDBC BOOLEAN với database cũ rồi giả định nó sẽ tự map an toàn sang NUMBER(1) hoặc CHAR(1).

### 12.3. Legacy mapping

Với database không có SQL BOOLEAN, schema thường dùng:

- NUMBER(1) với 0/1.
- CHAR(1)/VARCHAR2 với Y/N hoặc T/F.

Chọn một contract nhất quán. Kiểm tra CHECK constraint để loại giá trị ngoài tập cho phép và mapping null riêng.

### 12.4. Boolean NULL

Boolean nullable có ba trạng thái nghiệp vụ: TRUE, FALSE và UNKNOWN/NULL. Không tự map NULL thành false nếu business logic cần phân biệt. Dùng setNull với JDBC type được driver/database hỗ trợ hoặc biểu diễn qua legacy schema contract.

## 13. CallableStatement và procedure parameters

### 13.1. IN parameter

IN parameter dùng setter giống PreparedStatement:

```java
String call = "{ call order_api.update_status(?, ?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, orderId);
    cs.setString(2, "SHIPPED");
    cs.execute();
}
```

### 13.2. OUT parameter

OUT parameter cần đăng ký JDBC type trước execute:

```java
String call = "{ call order_api.get_total(?, ?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, customerId);
    cs.registerOutParameter(2, Types.NUMERIC);
    cs.execute();

    BigDecimal total = cs.getBigDecimal(2);
}
```

JDBC index bắt đầu từ 1. Kiểu registerOutParameter phải tương thích procedure parameter.

### 13.3. IN OUT parameter

IN OUT parameter vừa bind input vừa register output:

```java
cs.setBigDecimal(1, startingBalance);
cs.registerOutParameter(1, Types.NUMERIC);
cs.execute();
BigDecimal resultingBalance = cs.getBigDecimal(1);
```

Một số driver yêu cầu register trước set hoặc ngược lại theo API; tuân theo JDBC/Oracle driver documentation và kiểm thử.

### 13.4. NULL IN parameter

Nếu IN parameter nullable:

```java
if (note == null) {
    cs.setNull(1, Types.VARCHAR);
} else {
    cs.setString(1, note);
}
```

Không bỏ qua bind vì parameter index vẫn phải được gán. Nếu procedure có overload cùng tên, NULL untyped có thể làm overload resolution mơ hồ; typed NULL và signature rõ giúp giảm vấn đề.

### 13.5. Named parameter

CallableStatement có API đặt parameter theo tên ở một số JDBC driver, ví dụ setString("P_STATUS", value). Oracle driver hỗ trợ named notation theo API riêng/driver. Kiểm tra tài liệu; với positional call syntax, giữ index và thứ tự signature chính xác.

### 13.6. OUT REF CURSOR

Đăng ký OUT cursor bằng Types.REF_CURSOR hoặc OracleTypes.CURSOR tùy driver:

```java
cs.registerOutParameter(1, Types.REF_CURSOR);
cs.execute();
try (ResultSet rs = (ResultSet) cs.getObject(1)) {
    while (rs.next()) {
        // consume rows
    }
}
```

Đóng ResultSet và CallableStatement để giải phóng server cursor.

### 13.7. Procedure overload và NULL

PL/SQL cho phép overload procedure/function theo kiểu parameter. Nếu client bind NULL không có type rõ, Oracle có thể không chọn được overload mong muốn hoặc driver báo lỗi type mismatch. Gọi package procedure với signature rõ, dùng typed NULL, hoặc viết wrapper procedure có contract không mơ hồ.

## 14. Implicit conversion do bind datatype

### 14.1. Column NUMBER nhưng bind VARCHAR

Ví dụ:

```sql
SELECT *
FROM orders
WHERE order_id = :p_id;
```

Nếu order_id là NUMBER nhưng driver bind p_id như VARCHAR, Oracle phải giải quyết type mismatch. Tùy expression/type precedence, Oracle có thể chuyển bind hoặc expression. Kiểm tra Predicate Information để xác định conversion thực tế.

### 14.2. Bind NUMBER cho VARCHAR2 column

Nếu column là VARCHAR2 nhưng ứng dụng bind NUMBER, Oracle có thể chuyển đổi character value hoặc bind theo semantics khác với mong đợi. Mã có leading zero như 000123 có thể mất ý nghĩa khi chuyển thành số.

### 14.3. Bind DATE/TIMESTAMP bằng text

String date/time có thể phụ thuộc NLS_DATE_FORMAT, NLS_TIMESTAMP_FORMAT, NLS_DATE_LANGUAGE và timezone. Dùng typed setter hoặc explicit TO_DATE/TO_TIMESTAMP với mask và NLS parameter rõ ràng.

### 14.4. Tác động tới index

Nếu implicit conversion/function được áp dụng lên indexed column, predicate có thể không còn phù hợp với index access thông thường. Không suy đoán từ Java setter một mình; xem actual cursor plan và Predicate Information.

### 14.5. Tác động tới partition pruning

Nếu partition key bị bọc function hoặc conversion, partition pruning có thể giảm. Bind đúng kiểu của partition key và dùng range predicate phù hợp datatype.

### 14.6. ORA-01722 và ORA-01861

- ORA-01722: invalid number, có thể xảy ra khi character bind/data bị chuyển sang NUMBER nhưng có giá trị không hợp lệ.
- ORA-01861: literal does not match format string, có thể xảy ra khi text date/time không khớp format mask.

Sửa bind type và input contract; không bắt lỗi rồi retry cùng một giá trị sai.

### 14.7. Đọc execution plan

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
    )
);
```

PEEKED_BINDS chỉ hiển thị bind values/types được optimizer peek/capture theo điều kiện và quyền; không bảo đảm mọi execution/bind đều hiện. Cẩn trọng khi output có giá trị nhạy cảm.

## 15. Bind metadata, cursor sharing và child cursors

### 15.1. Bind datatype là một phần của cursor semantics

SQL text giống nhau nhưng bind metadata khác nhau có thể khiến Oracle tạo child cursor khác hoặc không share cursor trong một số trường hợp. Khác biệt datatype, length, precision/scale và optimizer environment có thể ảnh hưởng cursor compatibility.

### 15.2. Bind peeking

Oracle có thể peek bind value ở parse để ước lượng cardinality/plan. Bind datatype cũng ảnh hưởng cách predicate được hiểu. Adaptive Cursor Sharing có thể tạo nhiều child cursor cho selectivity khác nhau; nó không sửa được ứng dụng bind sai type.

### 15.3. Kiểm tra child cursor

```sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    parse_calls,
    is_bind_sensitive,
    is_bind_aware
FROM v$sql
WHERE sql_text LIKE '%FROM orders%'
ORDER BY sql_id, child_number;
```

SQL_TEXT search chỉ là ví dụ; có thể tìm theo SQL_ID đã biết. Xem V$SQL_SHARED_CURSOR để tìm lý do child cursor không share theo release.

### 15.4. V$SQL_SHARED_CURSOR

View này cung cấp các cờ lý do child cursor không share. Các cột và nguyên nhân có thể khác theo release; xem các cột liên quan bind mismatch/optimizer mismatch khi điều tra.

### 15.5. Parameter metadata

PreparedStatement.getParameterMetaData có thể cung cấp thông tin parameter tùy driver. Không nên phụ thuộc hoàn toàn vào việc driver suy luận mọi parameter type trước khi bind, đặc biệt với NULL, expression hoặc PL/SQL call. Ứng dụng nên biết schema/procedure contract và bind tường minh.

## 26. Bài lab: tạo schema và bind đúng kiểu

Chỉ chạy trên schema lab hoặc database được phép. Không dùng tên bảng/cột trùng object production.

### 26.1. Tạo bảng thử nghiệm

```sql
CREATE TABLE jdbc_bind_lab (
    id             NUMBER(12,0) PRIMARY KEY,
    code           VARCHAR2(30 CHAR),
    note           NVARCHAR2(100),
    amount         NUMBER(12,2),
    event_date     DATE,
    event_time     TIMESTAMP(6),
    raw_value      RAW(32),
    payload        CLOB
);
```

### 26.2. Insert giá trị không NULL

```java
String sql = """
    INSERT INTO jdbc_bind_lab
      (id, code, note, amount, event_date, event_time, raw_value)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);
    ps.setString(2, "ORD-0001");
    ps.setNString(3, "Đơn hàng thử nghiệm");
    ps.setBigDecimal(4, new BigDecimal("1250.75"));
    ps.setDate(5, java.sql.Date.valueOf(LocalDate.of(2026, 11, 14)));
    ps.setTimestamp(6, Timestamp.valueOf(
        LocalDateTime.of(2026, 11, 14, 21, 18, 30)));
    ps.setBytes(7, new byte[] {1, 2, 3, 4});
    ps.executeUpdate();
}
```

### 26.3. Insert NULL có type

```java
String sql = """
    INSERT INTO jdbc_bind_lab
      (id, code, note, amount, event_date, event_time, raw_value, payload)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 2L);
    ps.setNull(2, Types.VARCHAR);
    ps.setNull(3, Types.NVARCHAR);
    ps.setNull(4, Types.NUMERIC);
    ps.setNull(5, Types.DATE);
    ps.setNull(6, Types.TIMESTAMP);
    ps.setNull(7, Types.VARBINARY);
    ps.setNull(8, Types.CLOB);
    ps.executeUpdate();
}
```

### 26.4. Xác nhận dữ liệu

```sql
SELECT
    id,
    code,
    note,
    amount,
    event_date,
    event_time,
    RAWTOHEX(raw_value) AS raw_hex,
    CASE WHEN payload IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS payload_state
FROM jdbc_bind_lab
ORDER BY id;
```

So sánh null/non-null và dữ liệu Unicode. Xác nhận event_time giữ fractional seconds theo column precision.

### 26.5. Kiểm tra getter null

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT amount FROM jdbc_bind_lab WHERE id = ?")) {
    ps.setLong(1, 2L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal amount = rs.getBigDecimal(1);
            if (amount == null) {
                // SQL NULL
            }
        }
    }
}
```

### 26.6. Kiểm tra wasNull

```java
int id = rs.getInt("id");
boolean wasNull = rs.wasNull();
```

Ví dụ này minh họa thứ tự getter/wasNull; không dùng getInt cho NUMBER(12,2) nếu cần phần thập phân. Để kiểm tra NULL của amount, gọi getter trên đúng cột rồi gọi wasNull ngay sau đó.

## 27. Bài lab: so sánh bind type và conversion

### 27.1. Tạo bảng số và index

```sql
CREATE TABLE jdbc_number_lab (
    id NUMBER(12,0) PRIMARY KEY,
    description VARCHAR2(50)
);

INSERT INTO jdbc_number_lab
SELECT LEVEL, 'row-' || LEVEL
FROM dual
CONNECT BY LEVEL <= 10000;

CREATE INDEX ix_jdbc_number_lab_id
ON jdbc_number_lab(id);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'JDBC_NUMBER_LAB',
        cascade => TRUE
    );
END;
/
```

### 27.2. Bind NUMBER

```java
String sql =
    "SELECT description FROM jdbc_number_lab WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 500L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString(1));
        }
    }
}
```

### 27.3. Bind character

Trong lab, chạy cùng SQL nhưng dùng setString(1, "500"). Quan sát plan/predicate và bind metadata. Kết quả có thể vẫn đúng nhờ implicit conversion, nhưng đây không phải contract nên dùng trong ứng dụng khi column là NUMBER.

### 27.4. Xem plan

Chạy SQL với GATHER_PLAN_STATISTICS và đọc DBMS_XPLAN.DISPLAY_CURSOR. Xác định Oracle chuyển bind hay column, index có được sử dụng và predicate thực tế là gì.

### 27.5. Thử giá trị không hợp lệ

Bind "ABC" bằng setString cho predicate NUMBER có thể gây ORA-01722. Quan sát lỗi và so sánh với setLong. Không dùng test này trên hệ thống chia sẻ có workload thật.

### 27.6. Bài học

Một giá trị dạng text có thể được Oracle convert thành number và trả kết quả đúng trong test đơn giản, nhưng vẫn tạo phụ thuộc conversion/NLS và contract yếu. Bind đúng kiểu column giúp SQL rõ ràng và ổn định hơn.

## 28. Bài lab: typed NULL và PL/SQL overload

### 28.1. Tạo package thử nghiệm

```sql
CREATE OR REPLACE PACKAGE jdbc_null_lab AS
    PROCEDURE accept_text(p_value VARCHAR2);
    PROCEDURE accept_number(p_value NUMBER);
END;
/

CREATE OR REPLACE PACKAGE BODY jdbc_null_lab AS
    PROCEDURE accept_text(p_value VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE('TEXT');
    END;

    PROCEDURE accept_number(p_value NUMBER) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE('NUMBER');
    END;
END;
/
```

### 28.2. Gọi typed NULL

Khi package overload có parameter khác type, bind NULL bằng type rõ:

```java
try (CallableStatement cs = connection.prepareCall(
        "{ call jdbc_null_lab.accept_text(?) }")) {
    cs.setNull(1, Types.VARCHAR);
    cs.execute();
}
```

Và cho NUMBER:

```java
try (CallableStatement cs = connection.prepareCall(
        "{ call jdbc_null_lab.accept_number(?) }")) {
    cs.setNull(1, Types.NUMERIC);
    cs.execute();
}
```

### 28.3. Vì sao signature tường minh?

Procedure name trong call đã chỉ rõ package member/signature trong ví dụ. Trong các call phức tạp hoặc dynamic PL/SQL block, typed NULL và signature rõ giúp tránh ambiguity. Không dùng Types.NULL cho mọi overload.

## 29. Bài lab: timezone round-trip

### 29.1. Tạo bảng

```sql
CREATE TABLE jdbc_time_lab (
    id NUMBER PRIMARY KEY,
    local_ts TIMESTAMP(6),
    tz_ts TIMESTAMP(6) WITH TIME ZONE,
    local_tz_ts TIMESTAMP(6) WITH LOCAL TIME ZONE
);
```

### 29.2. Insert bằng java.time

Trên driver có JDBC 4.2 java.time support:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO jdbc_time_lab VALUES (?, ?, ?, ?)")) {
    ps.setLong(1, 1L);
    ps.setObject(2, LocalDateTime.of(2026, 11, 14, 21, 18));
    ps.setObject(3,
        OffsetDateTime.parse("2026-11-14T21:18:00+07:00"));
    ps.setObject(4,
        OffsetDateTime.parse("2026-11-14T21:18:00+07:00"));
    ps.executeUpdate();
}
```

### 29.3. Đọc ở hai session timezone

Đọc dữ liệu trong hai session có SESSIONTIMEZONE khác nhau. So sánh TIMESTAMP WITH TIME ZONE và TIMESTAMP WITH LOCAL TIME ZONE. Kết quả hiển thị của LTZ có thể đổi theo session timezone; TSTZ giữ semantics timezone của giá trị.

### 29.4. Xác minh

```sql
SELECT
    id,
    local_ts,
    tz_ts,
    local_tz_ts,
    SESSIONTIMEZONE,
    DBTIMEZONE
FROM jdbc_time_lab
WHERE id = 1;
```

Không kết luận dữ liệu sai chỉ vì local display khác nhau. Chuyển về cùng Instant/UTC hoặc cùng timezone contract trước khi so sánh.

## 30. Bài lab: driver metadata và bind capture

### 30.1. Ghi nhận driver

Chạy DatabaseMetaData.getDriverName/getDriverVersion/getDatabaseProductVersion trong ứng dụng và lưu cùng log test.

### 30.2. Lấy SQL_ID

Sau khi chạy một SQL lab, DBA tìm SQL_ID trong V$SQL bằng module/action hoặc SQL text. Tránh tìm bằng literal nhạy cảm.

### 30.3. Xem bind metadata

```sql
SELECT
    sql_id,
    child_number,
    name,
    position,
    datatype_string,
    max_length,
    precision,
    scale,
    last_captured
FROM v$sql_bind_capture
WHERE sql_id = :p_sql_id
ORDER BY child_number, position;
```

Không phải execution nào cũng có captured bind. Nếu không có row, không kết luận driver không bind parameter.

### 30.4. So sánh child cursor

```sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    parse_calls
FROM v$sql
WHERE sql_id = :p_sql_id
ORDER BY child_number;
```

Nếu có nhiều child, kiểm tra V$SQL_SHARED_CURSOR và bind mismatch. So sánh cùng SQL text nhưng khác setter/type ở lab để quan sát driver/Oracle behavior.

## 31. Troubleshooting matrix

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-01722 | Character bind/value bị chuyển sang NUMBER nhưng không hợp lệ | Bind NUMBER đúng kiểu, validate input và xem Predicate Information |
| ORA-01861/ORA-01843 | Text date không khớp mask/NLS | Dùng typed date/time setter hoặc parse explicit |
| ORA-00932 | Expression/parameter trộn datatype không tương thích | CAST rõ và thống nhất bind contract |
| ORA-01008 | Có placeholder chưa được bind | Đếm placeholder, kiểm tra mọi nhánh null/non-null và index |
| ORA-17004 | JDBC type không hợp lệ với driver/API | Phân biệt Types/OracleTypes, kiểm tra driver và SQL type |
| NULL không đi vào overload mong muốn | NULL không có type rõ hoặc overload mơ hồ | setNull đúng JDBC type, wrapper procedure có signature rõ |
| Giá trị tiền bị sai số | Dùng double/float cho decimal exact | Dùng BigDecimal và quy tắc rounding rõ |
| Ngày giờ lệch giờ | JVM/session/database timezone khác nhau | Xác định timezone contract, dùng java.time/Calendar có kiểm soát |
| Giờ bị mất khi đọc Oracle DATE | Dùng getDate cho column có time | Dùng mapping Timestamp/LocalDateTime theo driver semantics |
| Ký tự Unicode lỗi | Character set/NCHAR mapping không đúng | Kiểm tra setNString, NLS_NCHAR_CHARACTERSET và driver |
| String dài lỗi | Dùng setString vượt giới hạn/LOB mapping | Dùng CLOB/NCLOB stream setter |
| Batch insert sai dữ liệu | Parameter cũ còn giữ hoặc bind type thay đổi | Bind tất cả index mỗi row, setNull đúng type |
| Child cursor tăng | Bind metadata/length/optimizer environment khác | Chuẩn hóa setter và xem V$SQL_SHARED_CURSOR |
| REF CURSOR cast lỗi | Driver/JDBC type không hỗ trợ hoặc sai OUT type | Dùng Types.REF_CURSOR/OracleTypes.CURSOR phù hợp |
| ARRAY/STRUCT lỗi | Type name/schema hoặc API vendor-specific sai | Xác nhận named type và Oracle JDBC API/version |

### 31.1. Quy trình điều tra

1. Xác nhận Oracle column/procedure parameter datatype.
2. Ghi nhận Java runtime class của value, kể cả null.
3. Ghi nhận setter/Types/OracleTypes thực tế được gọi.
4. Xác nhận driver name/version và JDBC API support.
5. Tìm SQL_ID/child cursor và bind metadata nếu có.
6. Đọc Predicate Information để phát hiện implicit conversion.
7. Tạo test tối thiểu trên đúng driver/database version.
8. Sửa contract ở tầng DAO/repository và kiểm thử round-trip.

### 31.2. Phân biệt lỗi bind với lỗi dữ liệu

Nếu setBigDecimal vẫn nhận ORA-01438, có thể giá trị vượt precision column; đây là dữ liệu không vừa schema, không phải JDBC bind type sai. Nếu setString cho VARCHAR2 gặp ORA-12899, kiểm tra length BYTE/CHAR và character expansion. Không đổi JDBC type để che constraint/data-size issue.

### 31.3. Phân biệt lỗi driver với lỗi SQL

ORA- error thường đến từ database semantics; SQLRecoverableException/SQLTransientConnectionException hoặc vendor code có thể đến từ transport/session. Lưu SQLState, vendor error code, cause chain và driver version. Không phân loại mọi SQLException là lỗi bind.

## 32. Nguyên tắc thực hành tốt

1. **Đọc schema trước khi bind.** Biết column datatype, precision, scale, length semantics và timezone semantics.
2. **Dùng setter chuyên biệt.** NUMBER dùng setLong/setBigDecimal; VARCHAR2 dùng setString; DATE/TIMESTAMP dùng temporal setter phù hợp.
3. **Typed NULL luôn rõ ràng.** setNull(index, Types.X) phản ánh SQL parameter contract.
4. **Không dùng Types.NULL đại trà.** Dùng JDBC type cụ thể, đặc biệt với procedure overload, expression và UDT.
5. **Không bind tất cả bằng String.** Tránh implicit conversion và phụ thuộc NLS.
6. **Dùng BigDecimal cho decimal exact.** Không dùng double để lưu tiền/tỷ lệ cần chính xác.
7. **Hiểu Oracle DATE có time.** Chọn get/set API để không vô tình bỏ phần giờ.
8. **Kiểm soát timezone.** Phân biệt TIMESTAMP, TSTZ, LTZ, JVM timezone và session timezone.
9. **Dùng setNString khi contract là national character.** Kiểm tra Unicode round-trip.
10. **Dùng stream/LOB API cho dữ liệu lớn.** Quản lý length và lifecycle.
11. **Giữ bind type ổn định xuyên execution.** Cùng placeholder không đổi datatype theo nhánh code.
12. **Bind lại mọi parameter khi reuse statement.** Null mới phải setNull, không để giá trị cũ.
13. **Tách JDBC mapping vào DAO/repository.** Một schema contract nên có một mapping thống nhất.
14. **Dùng JDBC standard trước Oracle extension.** Vendor API chỉ dùng khi cần Oracle-specific feature.
15. **Pin driver version.** Không trộn nhiều ojdbc jar trong runtime.
16. **Kiểm thử sau driver/database upgrade.** Bao gồm null, temporal, LOB, UDT và batch.
17. **Không suy luận từ setObject một cách mù quáng.** Chọn target SQL type khi runtime inference không đủ rõ.
18. **Dùng PreparedStatement.** Bind values thay vì nối user input vào SQL.
19. **Không bind identifier.** Tên bảng/cột động phải qua allowlist.
20. **Kiểm tra actual plan.** Xem conversion, index access và child cursor khi có vấn đề.
21. **Không phụ thuộc bind capture hoàn toàn.** View capture có sampling và giới hạn.
22. **Bảo vệ bind values.** Không log secret/PII trong application log, trace hay plan output.
23. **Dùng wasNull với primitive getter.** Phân biệt SQL NULL với 0/false.
24. **Đóng resource.** ResultSet, statement, stream, LOB và Array phải có lifecycle rõ.
25. **Kiểm thử đúng driver.** Test với cùng JDK, ojdbc artifact và Oracle release như production.

## 33. Câu hỏi tự kiểm tra

1. Java type, JDBC type và Oracle SQL type khác nhau như thế nào?
2. Types.NUMERIC khác Oracle NUMBER(p,s) ở điểm nào?
3. JDBCType là gì và được bổ sung trong JDBC version nào?
4. OracleTypes dùng khi nào?
5. Vì sao setString không phù hợp cho mọi column?
6. Vì sao setBigDecimal phù hợp hơn setDouble cho tiền tệ?
7. Oracle DATE khác JDBC DATE như thế nào?
8. LocalDate, LocalDateTime và OffsetDateTime phù hợp với semantics nào?
9. TIMESTAMP WITH LOCAL TIME ZONE hiển thị theo timezone nào?
10. setNull cần những tham số nào?
11. Vì sao setObject(index, null) kém rõ ràng hơn typed NULL?
12. Khi nào cần setNull với typeName?
13. Types.NULL khác Types.VARCHAR/NUMERIC ra sao?
14. Vì sao NULL có thể làm procedure overload mơ hồ?
15. Types.REF_CURSOR khác OracleTypes.CURSOR thế nào?
16. Vì sao Oracle named collection cần type name?
17. setNString khác setString về intent ra sao?
18. RAW khác BLOB thế nào?
19. Khi nào dùng setCharacterStream/setBinaryStream?
20. Vì sao batch phải bind lại mọi parameter mỗi row?
21. wasNull được gọi vào thời điểm nào?
22. Vì sao status = NULL không tương đương status IS NULL?
23. Vì sao IN (?) không tự mở rộng danh sách Java?
24. Bind datatype ảnh hưởng implicit conversion/index access ra sao?
25. V$SQL_BIND_CAPTURE có ghi mọi bind value không?
26. Vì sao cùng SQL text có thể có nhiều child cursor?
27. JDBC driver artifact cần tương thích với những thành phần nào?
28. Khi nào cần OracleConnection.unwrap?
29. Làm thế nào kiểm tra timezone round-trip?
30. Cần lưu thông tin gì khi điều tra lỗi bind type?

## 34. Mô hình ghi nhớ

```text
JAVA VALUE
  String / BigDecimal / LocalDateTime / OffsetDateTime / byte[]
       |
       v
JDBC TYPE CONTRACT
  Types.* / JDBCType.* / OracleTypes.*
       |
       +-- setString / setBigDecimal / setTimestamp
       +-- setNull(index, type)
       +-- setObject(index, value, targetType)
       +-- registerOutParameter(index, type)
       |
       v
ORACLE JDBC DRIVER
  Mapping + conversion + metadata
       |
       v
ORACLE SQL TYPE
  NUMBER / VARCHAR2 / DATE / TIMESTAMP / RAW / LOB / UDT
       |
       v
SQL EXECUTION
  Implicit conversion? Index access? Cursor sharing?
       |
       v
READ BACK
  getBigDecimal / getTimestamp / getObject
  wasNull / ResultSet / LOB lifecycle
       |
       v
DIAGNOSTICS
  Schema metadata / V$SQL_BIND_CAPTURE
  DBMS_XPLAN / driver version / SQL error
```

**Điểm cần nhớ:** Java class, JDBC type và Oracle SQL datatype là ba lớp riêng. Bind đúng kiểu theo schema và nghiệp vụ; với NULL, chỉ rõ JDBC type bằng setNull. Dùng BigDecimal cho NUMBER decimal, chọn temporal mapping theo timezone semantics, và dùng Oracle extension khi JDBC chuẩn không đủ. Khi có lỗi, đối chiếu schema, setter, driver version, bind metadata và actual execution plan thay vì dựa vào giá trị hiển thị trong Java.

## 16. Parameter metadata và bind capture trong Oracle

### 16.1. V$SQL_BIND_CAPTURE

DBA có thể xem bind metadata được Oracle capture:

```sql
SELECT
    sql_id,
    child_number,
    name,
    position,
    datatype_string,
    max_length,
    precision,
    scale,
    last_captured
FROM v$sql_bind_capture
WHERE sql_id = :p_sql_id
ORDER BY child_number, position;
```

Bind capture có sampling và giới hạn; không ghi nhận mọi bind ở mọi execution. Một số datatype/value không được capture hoặc value có thể bị mask. Đây là công cụ điều tra, không phải audit log đầy đủ.

### 16.2. Bind value nhạy cảm

Bind capture/plan display có thể làm lộ dữ liệu như account number, email, token hoặc thông tin cá nhân. Hạn chế quyền truy cập, mask output khi chia sẻ ticket và tuân theo retention/audit policy.

### 16.3. Kiểm tra datatype column

Xác nhận schema:

```sql
SELECT
    column_name,
    data_type,
    data_length,
    char_length,
    char_used,
    data_precision,
    data_scale
FROM user_tab_columns
WHERE table_name = 'ORDERS'
ORDER BY column_id;
```

Nếu table thuộc schema khác, dùng ALL_TAB_COLUMNS/DBA_TAB_COLUMNS với quyền phù hợp. Column metadata là cơ sở chọn setter và NULL type.

### 16.4. SQL Monitor và actual plan

Khi SQL chậm, kết hợp SQL_ID, child_number, actual execution plan, bind metadata, wait events và application tracing. Không kết luận bind type là nguyên nhân chỉ vì thấy nhiều child cursor.

## 17. JDBC driver version và compatibility

### 17.1. Driver phải tương thích JDK/database

Oracle JDBC có nhiều dòng driver như ojdbc8, ojdbc11, ojdbc17 và các artifact theo release. Tên artifact thường phản ánh JDK baseline, không có nghĩa chỉ kết nối được một database version cụ thể. Kiểm tra compatibility matrix của Oracle cho JDK, database release và driver.

### 17.2. Không trộn nhiều ojdbc jar

Classpath chứa nhiều version ojdbc có thể gây NoSuchMethodError, ClassCastException, driver loading không mong muốn hoặc API extension mismatch. Chỉ triển khai một driver version được kiểm soát trong application runtime, trừ trường hợp kiến trúc đặc biệt đã được kiểm thử.

### 17.3. Kiểm tra driver runtime

```java
DatabaseMetaData md = connection.getMetaData();

System.out.println(md.getDriverName());
System.out.println(md.getDriverVersion());
System.out.println(md.getDatabaseProductName());
System.out.println(md.getDatabaseProductVersion());
```

Ghi nhận driver version trong diagnostic khi điều tra type mapping, timezone hoặc LOB issue.

### 17.4. JDBC version

```java
System.out.println(md.getJDBCMajorVersion());
System.out.println(md.getJDBCMinorVersion());
```

JDK API có thể có overload setObject(SQLType), nhưng driver phải hỗ trợ. Biên dịch thành công không bảo đảm mọi runtime driver đều triển khai overload với semantics mong muốn.

### 17.5. Java 8 và Java 17+

Text block trong ví dụ Java cần JDK 15+. Với JDK 8, dùng string literal nối dòng. java.time có từ Java 8, nhưng mapping JDBC 4.2 phụ thuộc driver. Chọn artifact ojdbc phù hợp JDK và xác nhận feature matrix.

### 17.6. Driver upgrade

Sau khi nâng driver, kiểm thử:

- setNull cho mọi nullable parameter.
- NUMBER precision/scale và rounding.
- DATE/TIMESTAMP/timezone round-trip.
- NCHAR/NVARCHAR2 và Unicode.
- LOB streaming/length.
- ARRAY/STRUCT/REF CURSOR nếu dùng.
- Batch, statement cache và cursor sharing.
- Failover/reconnect nếu dùng RAC/ONS.

Không nâng driver vào production mà chưa kiểm thử data correctness và performance.

## 18. Batch binding

### 18.1. addBatch với PreparedStatement

PreparedStatement cho phép bind nhiều bộ giá trị rồi addBatch:

```java
String sql =
    "INSERT INTO jdbc_bind_lab(id, note, amount) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (LabRow row : rows) {
        ps.setLong(1, row.id());

        if (row.note() == null) {
            ps.setNull(2, Types.VARCHAR);
        } else {
            ps.setString(2, row.note());
        }

        if (row.amount() == null) {
            ps.setNull(3, Types.NUMERIC);
        } else {
            ps.setBigDecimal(3, row.amount());
        }

        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
```

Ví dụ dùng record accessors, cần JDK hỗ trợ record; với JDK cũ dùng getter.

### 18.2. Mỗi batch row phải giữ cùng parameter type

Tránh batch đầu tiên bind index 2 bằng VARCHAR, batch sau bind cùng index bằng NUMBER hoặc một row NULL không typed. Giữ một datatype contract cho từng vị trí placeholder xuyên toàn batch.

### 18.3. Batch và NULL

Null row phải dùng setNull đúng type giống non-null row:

```java
if (row.amount() == null) {
    ps.setNull(3, Types.NUMERIC);
} else {
    ps.setBigDecimal(3, row.amount());
}
```

Không bỏ qua setter khi value null vì PreparedStatement có thể giữ lại giá trị từ lần bind trước ở cùng parameter index.

### 18.4. Clear parameters

Có thể dùng clearParameters để xóa toàn bộ parameter values khi tái sử dụng statement, nhưng thông thường bind lại tất cả parameter mỗi iteration là rõ ràng hơn. Không dựa vào giá trị bind cũ.

### 18.5. Batch update counts

executeBatch trả update counts hoặc BatchUpdateException. Oracle JDBC có thể dùng batch execution/array DML optimization tùy driver. Khi lỗi, xử lý partial success, transaction rollback và idempotency theo đúng batch semantics.

### 18.6. Batch và transaction

Tự quản lý autoCommit/commit theo batch boundary:

```java
connection.setAutoCommit(false);
try {
    // bind and execute batches
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
```

Không commit mỗi row nếu nghiệp vụ yêu cầu atomic batch. Nếu batch rất lớn, thiết kế chunk size và recovery strategy.

## 19. NULL trong dynamic SQL và filter

### 19.1. Optional filter

Ứng dụng thường có filter tùy chọn. SQL:

```sql
WHERE (:p_status IS NULL OR status = :p_status)
```

có thể bind cùng giá trị ở hai vị trí, cần bind cả hai và dùng type phù hợp. Tùy cardinality và optimizer, predicate optional có thể ảnh hưởng plan.

### 19.2. Bind cùng giá trị nhiều lần

```java
if (status == null) {
    ps.setNull(1, Types.VARCHAR);
    ps.setNull(2, Types.VARCHAR);
} else {
    ps.setString(1, status);
    ps.setString(2, status);
}
```

### 19.3. IS NULL không cần bind NULL

Nếu muốn lọc cột NULL, SQL rõ ràng là:

```sql
WHERE status IS NULL
```

Không viết status = NULL rồi bind NULL với kỳ vọng nó tương đương IS NULL. Trong SQL, status = NULL không trả TRUE.

### 19.4. IN list có kích thước động

JDBC không hỗ trợ một placeholder đại diện cho toàn bộ danh sách scalar values theo cách IN (?) tự mở rộng. Ứng dụng phải tạo số placeholder tương ứng, dùng collection/array type của Oracle hoặc cơ chế khác được thiết kế.

Ví dụ tạo placeholders:

```java
String placeholders = ids.stream()
    .map(id -> "?")
    .collect(Collectors.joining(","));
String sql = "SELECT * FROM orders WHERE order_id IN (" +
             placeholders + ")";
```

Chỉ ghép cấu trúc SQL do ứng dụng kiểm soát; values vẫn bind riêng. Với list lớn, cân nhắc Oracle collection type, global temporary table hoặc staging table.

### 19.5. Không bind tên cột/tên bảng như value

Bind variable đại diện expression value, không thay thế identifier hoặc keyword. Không thể dùng FROM ? để bind tên bảng. Identifier động phải lấy từ allowlist và quote/validate đúng; không ghép input tùy ý để tránh SQL injection.

### 19.6. SQL injection

PreparedStatement giúp tách value khỏi SQL text. Không nối chuỗi user input vào predicate/order by/table name. Nếu cần sort column động, map logical sort key tới danh sách identifier đã cho phép.

## 20. Oracle JDBC connection/session settings

### 20.1. NLS settings

Typed bind giúp giảm phụ thuộc NLS khi xử lý number/date. Tuy nhiên NLS vẫn ảnh hưởng string conversion, sorting, collation và một số format operations. Không thay thế typed bind bằng setString rồi dựa vào NLS_DATE_FORMAT/NLS_NUMERIC_CHARACTERS.

### 20.2. Session timezone

Nếu dùng TIMESTAMP WITH LOCAL TIME ZONE hoặc conversion dựa trên session timezone, kiểm tra SESSIONTIMEZONE. Connection pool có thể tái sử dụng session; thay đổi session time zone phải được reset khi trả connection về pool.

### 20.3. NLS_NUMERIC_CHARACTERS

Nếu ứng dụng bind BigDecimal, driver truyền numeric value thay vì text format. Điều này giảm phụ thuộc dấu thập phân/thousands separator. Nếu bind String số, parse có thể phụ thuộc NLS_NUMERIC_CHARACTERS và gây sai dữ liệu.

### 20.4. Character set

Database character set và national character set quyết định lưu trữ text. Driver có thể chuyển đổi từ Java Unicode; kiểm tra round-trip với ký tự tiếng Việt, supplementary characters và dữ liệu dài.

### 20.5. Connection pool reset

Pool phải quản lý transaction, autocommit, schema, role, NLS, timezone và các session settings khác. Không để một request đổi session state rồi rò sang request tiếp theo. Bind type ổn định là một phần của connection/SQL contract.

## 21. Diagnostics khi bind sai kiểu

### 21.1. ORA-01722

Thường xảy ra khi character data/bind được chuyển sang NUMBER nhưng giá trị không hợp lệ. Kiểm tra:

- Column datatype và bind datatype.
- Input có dấu phẩy/chấm theo locale không.
- Có leading/trailing whitespace hoặc ký tự ngoài numeric không.
- Predicate nào tạo implicit TO_NUMBER.
- SQL plan và bind capture.

### 21.2. ORA-01861 và ORA-01843

Lỗi date/time conversion thường do text không khớp format hoặc language. Dùng setDate/setTimestamp hoặc java.time mapping; nếu API nhận text thì parse ở application boundary và validate format.

### 21.3. ORA-00932

Datatype không nhất quán giữa expression/parameter, thường xuất hiện khi COALESCE/CASE/UNION/PLSQL overload trộn type. CAST rõ expression và bind type.

### 21.4. ORA-01461 / lỗi LOB

Lỗi liên quan bind chuỗi dài hoặc dữ liệu vượt giới hạn có thể phụ thuộc driver version, SQL datatype và API setter. Dùng stream/LOB API đúng column type; không mặc định setString xử lý mọi kích thước.

### 21.5. ORA-01008: not all variables bound

Có placeholder chưa được set. Kiểm tra index bắt đầu từ 1, số dấu hỏi, nhánh code null/non-null và bind lại tất cả parameter khi reuse statement.

### 21.6. ORA-17004: invalid column type

Driver không nhận JDBC type/Oracle type được truyền cho API đó. Kiểm tra Types vs OracleTypes, driver version, overload được gọi và datatype column/procedure.

### 21.7. Cursor mismatch

Nếu cùng SQL text có nhiều child cursor, xem V$SQL_SHARED_CURSOR, bind metadata và optimizer environment. Chuẩn hóa Java setter cho từng vị trí parameter trên tất cả code path.

### 21.8. Kiểm tra actual predicate

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
    )
);
```

Tùy overload DBMS_XPLAN, có thể truyền SQL_ID/child number hoặc dùng NULL cho cursor hiện tại. Không chia sẻ output bind values nhạy cảm.

## 22. Đọc dữ liệu và xử lý SQL NULL

### 22.1. Getter cho scalar

JDBC cung cấp getter tương ứng:

| Oracle type | Getter thường dùng |
| --- | --- |
| NUMBER integer range | getInt/getLong |
| NUMBER decimal | getBigDecimal |
| VARCHAR2/CHAR | getString |
| DATE | getDate hoặc getTimestamp theo semantics |
| TIMESTAMP | getTimestamp |
| BLOB | getBlob/getBinaryStream |
| CLOB | getClob/getCharacterStream |
| RAW | getBytes |
| REF CURSOR | getObject/getResultSet theo driver/API |

Chọn getter theo column semantics và miền giá trị. getLong không phù hợp NUMBER(38) có thể vượt Long range.

### 22.2. wasNull với primitive getter

Nếu SQL value là NULL, getter primitive như getInt/getLong/getBoolean trả về giá trị mặc định (0/false). Gọi wasNull ngay sau getter để biết giá trị gốc có phải NULL:

```java
int quantity = rs.getInt("quantity");
if (rs.wasNull()) {
    // SQL NULL
} else {
    // quantity có giá trị, kể cả 0
}
```

wasNull áp dụng cho giá trị vừa đọc gần nhất. Gọi getter khác trước wasNull sẽ thay đổi giá trị mà wasNull kiểm tra.

### 22.3. Dùng wrapper/BigDecimal để giữ NULL

```java
Integer quantity = (Integer) rs.getObject("quantity");
BigDecimal amount = rs.getBigDecimal("amount");
```

getBigDecimal trả null nếu SQL NULL. Với primitive wrapper, hành vi getObject class mapping phụ thuộc driver/JDBC version; có thể dùng getObject(column, Integer.class) nếu driver hỗ trợ.

### 22.4. getObject với target Java class

JDBC 4.1+ có getObject(index, Class<T>) cho type mapping được hỗ trợ:

```java
LocalDate orderDate = rs.getObject("order_date", LocalDate.class);
LocalDateTime createdAt =
    rs.getObject("created_at", LocalDateTime.class);
```

Oracle driver support phụ thuộc version và Oracle datatype. Kiểm thử với DATE/TIMESTAMP cụ thể; không giả định tất cả Oracle timezone types đều map được sang mọi java.time class.

### 22.5. Đọc TIMESTAMP WITH TIME ZONE

Nếu driver hỗ trợ:

```java
OffsetDateTime occurredAt =
    rs.getObject("occurred_at", OffsetDateTime.class);
```

Nếu cần preserve region timezone, kiểm tra mapping và lưu ZoneId riêng nếu Oracle/driver không trả lại đúng region identifier.

### 22.6. NULL và primitive boolean

getBoolean trả false cho SQL NULL; gọi wasNull để phân biệt false với NULL. Không map null thành false nếu business logic cần trạng thái unknown.

### 22.7. ResultSet getter và timezone

getTimestamp(column) có overload nhận Calendar. Nếu dùng overload này, timezone conversion phải theo contract của ứng dụng. Không trộn JVM default timezone khác nhau giữa các node mà không kiểm soát.

## 23. Pattern code an toàn cho bind parameter

### 23.1. Một helper bind nullable String

```java
static void bindNullableVarchar(
        PreparedStatement ps, int index, String value)
        throws SQLException {
    if (value == null) {
        ps.setNull(index, Types.VARCHAR);
    } else {
        ps.setString(index, value);
    }
}
```

Helper chỉ nên được dùng cho parameter contract là VARCHAR2/character. Không tạo một helper generic luôn dùng VARCHAR cho mọi NULL.

### 23.2. Helper nullable BigDecimal

```java
static void bindNullableNumber(
        PreparedStatement ps, int index, BigDecimal value)
        throws SQLException {
    if (value == null) {
        ps.setNull(index, Types.NUMERIC);
    } else {
        ps.setBigDecimal(index, value);
    }
}
```

Nếu schema có precision/scale và business rounding rule, normalize BigDecimal trước khi gọi helper.

### 23.3. Helper nullable Timestamp

```java
static void bindNullableTimestamp(
        PreparedStatement ps, int index, Timestamp value)
        throws SQLException {
    if (value == null) {
        ps.setNull(index, Types.TIMESTAMP);
    } else {
        ps.setTimestamp(index, value);
    }
}
```

Chỉ dùng cho TIMESTAMP semantics phù hợp. Nếu column là TIMESTAMP WITH TIME ZONE, chọn mapping OffsetDateTime/Oracle type thay vì mặc định Types.TIMESTAMP.

### 23.4. Tách SQL contract khỏi domain object

Domain object có thể dùng Optional, BigDecimal hoặc java.time. Repository/DAO chịu trách nhiệm chuyển đổi sang JDBC type theo schema. Không để mọi tầng ứng dụng tự chọn Types.* khác nhau cho cùng một cột.

### 23.5. Bind tất cả placeholder mỗi lần execute

Khi reuse PreparedStatement, mọi parameter index phải được gán lại cho mỗi execution. Nếu giá trị mới null, phải gọi setNull đúng type; nếu không, driver có thể giữ bind value cũ hoặc báo thiếu parameter tùy tình huống.

### 23.6. Resource lifecycle

Dùng try-with-resources cho PreparedStatement, CallableStatement, ResultSet và stream. Đảm bảo connection/transaction vẫn mở trong thời gian bind/execute/consume LOB hoặc REF CURSOR.

### 23.7. Không log bind value mặc định

Log SQL_ID, parameter position, JDBC type, null/non-null và length khi cần chẩn đoán. Tránh log đầy đủ value nhạy cảm. Nếu cần sample, mask hoặc hash theo policy.

## 24. setNull nâng cao và named SQL types

### 24.1. Overload có typeName

JDBC có:

```java
ps.setNull(parameterIndex, sqlType, typeName);
```

Overload này hữu ích với user-defined type như STRUCT/ARRAY có tên. Với scalar NUMBER/VARCHAR/DATE thông thường, không cần typeName.

### 24.2. Types.NULL

Types.NULL là generic JDBC null type. Nó không mô tả chính xác Oracle parameter type như VARCHAR, NUMBER hay TIMESTAMP. Với SQL expression đơn giản, driver/Oracle đôi khi có thể suy luận từ context, nhưng với overload/procedure/expression phức tạp, nên dùng type cụ thể.

### 24.3. Null cho REF CURSOR

Nếu procedure parameter là REF CURSOR IN/OUT, dùng JDBC Types.REF_CURSOR hoặc OracleTypes.CURSOR theo driver support. Không dùng Types.VARCHAR chỉ vì cursor được lấy bằng getObject.

### 24.4. Null cho named object type

```java
ps.setNull(1, Types.STRUCT, "APP.ADDRESS_T");
```

Nếu schema type thay đổi hoặc tên không được qualify đúng, driver có thể báo invalid type. Xác nhận type name trong ALL_TYPES/ALL_TYPE_ATTRS và schema owner.

### 24.5. Null cho collection

```java
ps.setNull(1, Types.ARRAY, "APP.NUMBER_LIST_T");
```

Một số Oracle driver yêu cầu Oracle-specific SQL type constant hoặc type name format riêng. Thử trong integration test với đúng driver; đừng giả định tất cả database/driver xử lý Types.ARRAY giống nhau.

### 24.6. Null và overload resolution

Nếu package có:

```sql
PROCEDURE update_value(p_value NUMBER);
PROCEDURE update_value(p_value VARCHAR2);
```

thì NULL không typed có thể khiến overload không rõ ràng. Gọi đúng signature qua wrapper/typed bind. Một cách khác là đặt tên procedure khác nhau để API client không phải dựa vào overload resolution phức tạp.

## 25. Driver-specific legacy APIs

### 25.1. oracle.sql package

Các class legacy trong oracle.sql như ARRAY, STRUCT, TIMESTAMP, TIMESTAMPTZ và BLOB/CLOB có thể xuất hiện trong code cũ. Oracle đã cung cấp các API mới hơn trong oracle.jdbc và JDBC standard; nhiều legacy class bị deprecated hoặc có lộ trình thay thế tùy version.

Không refactor hàng loạt khi chưa kiểm thử. Khi viết code mới, ưu tiên java.sql/java.time và Oracle JDBC API hiện hành được tài liệu hóa cho driver đang dùng.

### 25.2. OraclePreparedStatement

OraclePreparedStatement cung cấp một số extension như bind form-of-use, batch và Oracle-specific features. Dùng khi JDBC standard không đủ; unwrap connection/statement qua API được hỗ trợ và giữ code vendor-specific ở một adapter nhỏ.

### 25.3. NCHAR form-of-use legacy

Một số code cũ dùng OraclePreparedStatement.setFormOfUse với FORM_NCHAR để chỉ định national character semantics. Code mới thường có setNString/setNCharacterStream. Không gọi cả hai cơ chế cùng lúc nếu chưa hiểu driver behavior.

### 25.4. OracleConnection unwrap

Khi cần extension:

```java
OracleConnection oracleConnection =
    connection.unwrap(OracleConnection.class);
```

unwrap là cách JDBC chuẩn để lấy vendor interface từ pooled/proxy connection. Không cast trực tiếp pooled connection sang OracleConnection nếu pool trả wrapper khác.

### 25.5. Đóng Oracle-specific resource

Array, Blob, Clob, ResultSet và Oracle extension object có lifecycle riêng. Dùng free()/close() khi API yêu cầu; giải phóng trong finally/try-with-resources phù hợp.

## 11. Oracle-specific types và OracleTypes

### 11.1. Khi nào cần Oracle extension?

JDBC chuẩn bao phủ phần lớn scalar type phổ biến. Một số Oracle type/feature không có mapping chuẩn đủ chi tiết, hoặc driver version cũ yêu cầu API vendor-specific. Khi đó có thể cần OracleTypes, OracleConnection hoặc các class trong oracle.jdbc.

Ưu tiên JDBC standard type nếu nó mô tả đúng semantics và driver hỗ trợ. Chỉ dùng Oracle extension khi cần tính năng Oracle-specific hoặc mapping chuẩn không đáp ứng.

### 11.2. OracleTypes

Oracle JDBC có class hằng số OracleTypes để đại diện các datatype/feature của Oracle. Tùy driver version, các hằng số có thể gồm CURSOR, TIMESTAMP, TIMESTAMPTZ, TIMESTAMPLTZ, INTERVALYM, INTERVALDS, BINARY_FLOAT, BINARY_DOUBLE, STRUCT, ARRAY và các type khác.

Ví dụ dạng API legacy:

```java
import oracle.jdbc.OracleTypes;

callable.registerOutParameter(1, OracleTypes.CURSOR);
```

Với driver hỗ trợ JDBC 4.2, có thể dùng Types.REF_CURSOR cho REF CURSOR. Kiểm tra Oracle JDBC version trước khi chọn API; không copy hằng số từ một ojdbc version sang driver khác mà không build/test.

### 11.3. REF CURSOR

REF CURSOR là cursor handle được PL/SQL trả về cho client. JDBC chuẩn có Types.REF_CURSOR từ JDBC 4.2; Oracle driver cũ hơn có thể dùng OracleTypes.CURSOR.

Ví dụ:

```java
String call = "{ call customer_api.list_customers(?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.registerOutParameter(1, Types.REF_CURSOR);
    cs.execute();

    try (ResultSet rs = (ResultSet) cs.getObject(1)) {
        while (rs.next()) {
            long id = rs.getLong("customer_id");
            String name = rs.getString("full_name");
        }
    }
}
```

Kiểm tra driver có hỗ trợ Types.REF_CURSOR và procedure signature thực tế. Cursor ResultSet phải được đóng; nó có thể giữ server cursor và tài nguyên database.

### 11.4. STRUCT và Oracle object type

Oracle object type có thể được biểu diễn qua java.sql.Struct hoặc mapping Java class tùy driver/API. Ví dụ:

```sql
CREATE TYPE address_t AS OBJECT (
    street VARCHAR2(100),
    city   VARCHAR2(60)
);

CREATE TABLE customer_address (
    customer_id NUMBER,
    address     address_t
);
```

JDBC:

```java
Object[] attributes = {"12 Nguyen Hue", "Ho Chi Minh City"};
Struct address = connection.createStruct(
    "APP.ADDRESS_T", attributes);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customer_address(customer_id, address) VALUES (?, ?)")) {
    ps.setLong(1, 100L);
    ps.setObject(2, address);
    ps.executeUpdate();
}
```

Tên type thường phải ghi schema chính xác. Cách tạo Struct và hỗ trợ UDT phụ thuộc Oracle JDBC driver; Oracle-specific type mapping có thể cần OracleConnection/OracleData API.

### 11.5. NULL cho STRUCT/ARRAY có type name

JDBC có overload setNull nhận typeName:

```java
ps.setNull(1, Types.STRUCT, "APP.ADDRESS_T");
```

Type name giúp driver xác định named SQL type. Với collection, dùng Types.ARRAY và tên collection type phù hợp nếu driver hỗ trợ. Kiểm tra schema qualification và quyền EXECUTE type.

### 11.6. Collection và ARRAY

Oracle nested table/VARRAY là named collection type. Không giả định Connection.createArrayOf hoạt động giống mọi database; Oracle JDBC thường cung cấp OracleConnection.createOracleArray với tên SQL collection type:

```java
OracleConnection oracleConnection =
    connection.unwrap(OracleConnection.class);

Array values = oracleConnection.createOracleArray(
    "APP.NUMBER_LIST_T",
    new BigDecimal[] {
        new BigDecimal("10"),
        new BigDecimal("20")
    });

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO batch_ids(ids) VALUES (?)")) {
    ps.setArray(1, values);
    ps.executeUpdate();
} finally {
    values.free();
}
```

Đây là ví dụ minh họa. Collection type phải được tạo trước trong Oracle và tên phải khớp chính xác. Oracle JDBC API cụ thể phụ thuộc driver; tránh dùng class oracle.sql.ARRAY legacy nếu driver mới có API thay thế.

### 11.7. INTERVAL

Oracle INTERVAL YEAR TO MONTH và INTERVAL DAY TO SECOND không ánh xạ trực tiếp hoàn hảo với mọi Java Duration/Period. Period biểu diễn năm/tháng; Duration biểu diễn thời lượng theo giây/nanosecond. Chọn mapping theo semantics và dùng Oracle-specific API nếu cần giữ chính xác interval type.

### 11.8. ROWID và UROWID

JDBC có java.sql.RowId. Oracle ROWID/UROWID có semantics định vị row; không dùng làm business key ổn định hoặc định danh xuyên database. Nếu bind, dùng RowId/setRowId khi driver hỗ trợ và không serialize ROWID như khóa nghiệp vụ.

### 11.9. BFILE

BFILE là locator tới file bên ngoài database và thường chỉ đọc qua Oracle-specific APIs. Nó không giống BLOB; nội dung file không được lưu trong datafile như LOB nội bộ. Xử lý BFILE cần quyền directory object và lifecycle locator đúng cách.

### 11.10. XMLTYPE và JSON

XMLTYPE/JSON support phụ thuộc Oracle Database release và JDBC driver. Một số phiên bản cung cấp Oracle-specific XML/JSON API; phiên bản mới có thêm JDBC mapping cho JSON. Không mặc định setString vào mọi parameter JSON là giữ nguyên binary/native JSON semantics. Xác nhận column type, driver API và round-trip behavior.

## 12. BOOLEAN: SQL BOOLEAN và PL/SQL BOOLEAN

### 12.1. PL/SQL BOOLEAN

PL/SQL BOOLEAN tồn tại từ lâu trong PL/SQL, nhưng các Oracle Database release trước 23ai không có SQL BOOLEAN column type để dùng trực tiếp trong table/query như datatype SQL thông thường.

Một số Oracle JDBC driver cung cấp extension để bind PL/SQL BOOLEAN trong procedure/function call. Hằng số/API cụ thể phụ thuộc driver, ví dụ OracleTypes.PLSQL_BOOLEAN ở các phiên bản có hỗ trợ.

### 12.2. SQL BOOLEAN trong release mới

Oracle Database 23ai bổ sung SQL BOOLEAN. Với database/driver hỗ trợ, JDBC boolean mapping có thể dùng setBoolean/getBoolean hoặc JDBCType.BOOLEAN tùy driver version.

Không dùng JDBC BOOLEAN với database cũ rồi giả định nó sẽ tự map an toàn sang NUMBER(1) hoặc CHAR(1).

### 12.3. Legacy mapping

Với database không có SQL BOOLEAN, schema thường dùng:

- NUMBER(1) với 0/1.
- CHAR(1)/VARCHAR2 với Y/N hoặc T/F.

Chọn một contract nhất quán. Kiểm tra CHECK constraint để loại giá trị ngoài tập cho phép và mapping null riêng.

### 12.4. Boolean NULL

Boolean nullable có ba trạng thái nghiệp vụ: TRUE, FALSE và UNKNOWN/NULL. Không tự map NULL thành false nếu business logic cần phân biệt. Dùng setNull với JDBC type được driver/database hỗ trợ hoặc biểu diễn qua legacy schema contract.

## 13. CallableStatement và procedure parameters

### 13.1. IN parameter

IN parameter dùng setter giống PreparedStatement:

```java
String call = "{ call order_api.update_status(?, ?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, orderId);
    cs.setString(2, "SHIPPED");
    cs.execute();
}
```

### 13.2. OUT parameter

OUT parameter cần đăng ký JDBC type trước execute:

```java
String call = "{ call order_api.get_total(?, ?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, customerId);
    cs.registerOutParameter(2, Types.NUMERIC);
    cs.execute();

    BigDecimal total = cs.getBigDecimal(2);
}
```

JDBC index bắt đầu từ 1. Kiểu registerOutParameter phải tương thích procedure parameter.

### 13.3. IN OUT parameter

IN OUT parameter vừa bind input vừa register output:

```java
cs.setBigDecimal(1, startingBalance);
cs.registerOutParameter(1, Types.NUMERIC);
cs.execute();
BigDecimal resultingBalance = cs.getBigDecimal(1);
```

Một số driver yêu cầu register trước set hoặc ngược lại theo API; tuân theo JDBC/Oracle driver documentation và kiểm thử.

### 13.4. NULL IN parameter

Nếu IN parameter nullable:

```java
if (note == null) {
    cs.setNull(1, Types.VARCHAR);
} else {
    cs.setString(1, note);
}
```

Không bỏ qua bind vì parameter index vẫn phải được gán. Nếu procedure có overload cùng tên, NULL untyped có thể làm overload resolution mơ hồ; typed NULL và signature rõ giúp giảm vấn đề.

### 13.5. Named parameter

CallableStatement có API đặt parameter theo tên ở một số JDBC driver, ví dụ setString("P_STATUS", value). Oracle driver hỗ trợ named notation theo API riêng/driver. Kiểm tra tài liệu; với positional call syntax, giữ index và thứ tự signature chính xác.

### 13.6. OUT REF CURSOR

Đăng ký OUT cursor bằng Types.REF_CURSOR hoặc OracleTypes.CURSOR tùy driver:

```java
cs.registerOutParameter(1, Types.REF_CURSOR);
cs.execute();
try (ResultSet rs = (ResultSet) cs.getObject(1)) {
    while (rs.next()) {
        // consume rows
    }
}
```

Đóng ResultSet và CallableStatement để giải phóng server cursor.

### 13.7. Procedure overload và NULL

PL/SQL cho phép overload procedure/function theo kiểu parameter. Nếu client bind NULL không có type rõ, Oracle có thể không chọn được overload mong muốn hoặc driver báo lỗi type mismatch. Gọi package procedure với signature rõ, dùng typed NULL, hoặc viết wrapper procedure có contract không mơ hồ.

## 14. Implicit conversion do bind datatype

### 14.1. Column NUMBER nhưng bind VARCHAR

Ví dụ:

```sql
SELECT *
FROM orders
WHERE order_id = :p_id;
```

Nếu order_id là NUMBER nhưng driver bind p_id như VARCHAR, Oracle phải giải quyết type mismatch. Tùy expression/type precedence, Oracle có thể chuyển bind hoặc expression. Kiểm tra Predicate Information để xác định conversion thực tế.

### 14.2. Bind NUMBER cho VARCHAR2 column

Nếu column là VARCHAR2 nhưng ứng dụng bind NUMBER, Oracle có thể chuyển đổi character value hoặc bind theo semantics khác với mong đợi. Mã có leading zero như 000123 có thể mất ý nghĩa khi chuyển thành số.

### 14.3. Bind DATE/TIMESTAMP bằng text

String date/time có thể phụ thuộc NLS_DATE_FORMAT, NLS_TIMESTAMP_FORMAT, NLS_DATE_LANGUAGE và timezone. Dùng typed setter hoặc explicit TO_DATE/TO_TIMESTAMP với mask và NLS parameter rõ ràng.

### 14.4. Tác động tới index

Nếu implicit conversion/function được áp dụng lên indexed column, predicate có thể không còn phù hợp với index access thông thường. Không suy đoán từ Java setter một mình; xem actual cursor plan và Predicate Information.

### 14.5. Tác động tới partition pruning

Nếu partition key bị bọc function hoặc conversion, partition pruning có thể giảm. Bind đúng kiểu của partition key và dùng range predicate phù hợp datatype.

### 14.6. ORA-01722 và ORA-01861

- ORA-01722: invalid number, có thể xảy ra khi character bind/data bị chuyển sang NUMBER nhưng có giá trị không hợp lệ.
- ORA-01861: literal does not match format string, có thể xảy ra khi text date/time không khớp format mask.

Sửa bind type và input contract; không bắt lỗi rồi retry cùng một giá trị sai.

### 14.7. Đọc execution plan

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
    )
);
```

PEEKED_BINDS chỉ hiển thị bind values/types được optimizer peek/capture theo điều kiện và quyền; không bảo đảm mọi execution/bind đều hiện. Cẩn trọng khi output có giá trị nhạy cảm.

## 15. Bind metadata, cursor sharing và child cursors

### 15.1. Bind datatype là một phần của cursor semantics

SQL text giống nhau nhưng bind metadata khác nhau có thể khiến Oracle tạo child cursor khác hoặc không share cursor trong một số trường hợp. Khác biệt datatype, length, precision/scale và optimizer environment có thể ảnh hưởng cursor compatibility.

### 15.2. Bind peeking

Oracle có thể peek bind value ở parse để ước lượng cardinality/plan. Bind datatype cũng ảnh hưởng cách predicate được hiểu. Adaptive Cursor Sharing có thể tạo nhiều child cursor cho selectivity khác nhau; nó không sửa được ứng dụng bind sai type.

### 15.3. Kiểm tra child cursor

```sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    parse_calls,
    is_bind_sensitive,
    is_bind_aware
FROM v$sql
WHERE sql_text LIKE '%FROM orders%'
ORDER BY sql_id, child_number;
```

SQL_TEXT search chỉ là ví dụ; có thể tìm theo SQL_ID đã biết. Xem V$SQL_SHARED_CURSOR để tìm lý do child cursor không share theo release.

### 15.4. V$SQL_SHARED_CURSOR

View này cung cấp các cờ lý do child cursor không share. Các cột và nguyên nhân có thể khác theo release; xem các cột liên quan bind mismatch/optimizer mismatch khi điều tra.

### 15.5. Parameter metadata

PreparedStatement.getParameterMetaData có thể cung cấp thông tin parameter tùy driver. Không nên phụ thuộc hoàn toàn vào việc driver suy luận mọi parameter type trước khi bind, đặc biệt với NULL, expression hoặc PL/SQL call. Ứng dụng nên biết schema/procedure contract và bind tường minh.
