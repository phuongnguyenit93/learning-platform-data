# Ánh xạ kiểu dữ liệu PostgreSQL sang Java qua JDBC

Khi ứng dụng Java truy cập PostgreSQL, dữ liệu phải đi qua hai hệ kiểu khác nhau: **kiểu SQL do PostgreSQL quản lý** và **kiểu Java mà JDBC driver cung cấp**. Một cột `numeric(18,4)` không nên được đọc tùy tiện thành `double` khi đại diện cho tiền; `timestamp with time zone` không giống `timestamp without time zone`; một cột `jsonb` không tự trở thành đối tượng domain Java; và `NULL` trong SQL không giống giá trị mặc định 0 của kiểu nguyên thủy Java.

Tài liệu này hướng dẫn cách chọn kiểu Java, cách gọi `ResultSet.getXxx()`, `getObject()`, `PreparedStatement.setXxx()`, `setObject()` và `setNull()`, đồng thời giải thích các trường hợp cần kiểu riêng của PostgreSQL JDBC driver như `PGobject`, `PGInterval` hoặc `java.sql.Array`. Các ví dụ nhấn mạnh tính đúng đắn của tiền tệ, ngày giờ, JSON, UUID, mảng, bytea và các kiểu đặc thù PostgreSQL.

Bài thuộc chương **Kết nối ứng dụng** của module **Database Engine Relational PostgreSQL**. Tất cả đoạn mã đều tập trung vào PostgreSQL và Java/JDBC; tên bảng, role, URL trong ví dụ có tính minh họa. Tính năng của PostgreSQL JDBC Driver (*pgJDBC*) có thể thay đổi theo phiên bản, vì thế nên dùng driver còn được hỗ trợ và thử hành vi đặc thù trên phiên bản thực tế trước khi triển khai.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt kiểu dữ liệu ở PostgreSQL, JDBC type code và kiểu đối tượng Java.
2. Đọc và ghi các kiểu `boolean`, số nguyên, số thực, `numeric` và chuỗi mà không đánh mất ý nghĩa dữ liệu.
3. Sử dụng các kiểu `java.time` đúng với `date`, `time`, `timestamp` và `timestamptz`.
4. Biết vì sao PostgreSQL không lưu tên múi giờ gốc trong `timestamptz`.
5. Ánh xạ UUID, JSON/JSONB, ARRAY, BYTEA, ENUM, INTERVAL và một số kiểu mở rộng.
6. Phân biệt SQL NULL với Java null, JSON null, mảng rỗng và chuỗi rỗng.
7. Dùng `PreparedStatement` và placeholder an toàn để truyền giá trị.
8. Chọn đúng `getObject(column, Type.class)` trong phạm vi driver hỗ trợ; biết khi nào phải dùng API khác.
9. Xem metadata cột qua JDBC và system catalogs để tránh suy đoán kiểu.
10. Tạo một lab PostgreSQL và Java có thể thực hành.
11. Nhận diện lỗi mất độ chính xác, trôi múi giờ, ép kiểu sai, nhầm encoding và lộ dữ liệu.
12. Thiết kế ranh giới domain model, DTO và database schema dễ nâng cấp.

## 2. Ba lớp ánh xạ phải được phân biệt

~~~text
PostgreSQL
   |
   | Kiểu SQL và giá trị
   | numeric, uuid, timestamptz, jsonb, text[], ...
   v
PostgreSQL Wire Protocol / pgJDBC
   |
   | JDBC type code + driver conversion
   | Types.NUMERIC, Types.OTHER, ...
   v
ResultSet / PreparedStatement
   |
   | getBigDecimal / getObject(UUID.class)
   | setObject / setNull / ...
   v
Java model
   |
   | BigDecimal, UUID, OffsetDateTime, List<String>, ...
   v
Service / API / Business logic
~~~

### 2.1. Kiểu PostgreSQL

PostgreSQL biết `numeric(12,2)`, `timestamptz`, `jsonb`, `text[]` hoặc tên enum do bạn tạo. PostgreSQL thực thi các phép toán, constraints và chuyển kiểu ở phía server.

### 2.2. JDBC type code

`java.sql.Types` cung cấp các mã kiểu tiêu chuẩn như `INTEGER`, `BIGINT`, `NUMERIC`, `DATE`, `TIMESTAMP`, `TIMESTAMP_WITH_TIMEZONE`, `ARRAY`, `BINARY` và `OTHER`.

Một kiểu PostgreSQL-specific có thể được driver báo bằng `Types.OTHER`; điều này không nói rằng dữ liệu “không có kiểu”.

### 2.3. Kiểu Java

Một cột PostgreSQL `bigint` có thể được đọc thành `long` hoặc `Long`, nhưng nếu cột nullable thì primitive `long` không biểu diễn được SQL NULL. Phải cân nhắc kiểu Java theo hợp đồng nghiệp vụ.

### 2.4. Metadata không thay domain semantics

PostgreSQL `numeric(18,2)` có thể đại diện tiền, khối lượng hoặc tỷ lệ. JDBC thấy đều là `BigDecimal`, nhưng ứng dụng cần phân biệt đơn vị, tiền tệ, quy tắc làm tròn và validation.

## 3. Chuẩn JDBC và phần mở rộng của pgJDBC

Trong Java, JDBC là API chuẩn gồm:

- `java.sql.Connection`
- `java.sql.PreparedStatement`
- `java.sql.ResultSet`
- `java.sql.ResultSetMetaData`
- `java.sql.Types`
- `java.sql.Array`
- `java.sql.SQLXML`
- `java.sql.Date`, `Time`, `Timestamp` trong các ứng dụng cũ.

PostgreSQL JDBC driver bổ sung những khả năng cần thiết cho kiểu riêng:

- `org.postgresql.util.PGobject`
- `org.postgresql.util.PGInterval`
- Các cơ chế thông báo, COPY, large objects và các API đặc thù khác nếu ứng dụng sử dụng.

### 3.1. Ưu tiên JDBC chuẩn khi đủ

Với `integer`, `numeric`, `date` hoặc `timestamp`, thường không cần phụ thuộc PGobject. Các getter tiêu chuẩn hoặc `getObject(..., Class)` tương ứng có thể dễ đọc và dễ kiểm thử hơn.

### 3.2. Kiểu riêng không nhất thiết ánh xạ tự động thành POJO

Một cột `jsonb` không tự trở thành `OrderPayload`. Bạn phải serialize/deserialize dữ liệu JSON theo library và schema hợp đồng của ứng dụng.

### 3.3. Driver version quan trọng

JDBC 4.2 đưa ra hỗ trợ `java.time`; pgJDBC có tập chuyển đổi được hỗ trợ riêng. Không nên suy luận chỉ vì Java có `Instant` hay `OffsetTime` thì `getObject(..., Instant.class)` hoặc `setObject(OffsetTime)` chắc chắn chạy trên mọi pgJDBC version.

### 3.4. Tài liệu phải dựa vào kiểm tra thực tế

Với kiểu hiếm như range, multirange, enum, network hay interval, driver có thể đưa về `PGobject` hoặc cách biểu diễn khác tùy loại và phiên bản. Trong ứng dụng quan trọng, viết integration test thay vì mặc định mọi cột sẽ thành một Java class cụ thể.

## 4. Bảng ánh xạ nền tảng

| PostgreSQL | Java nên ưu tiên | JDBC đọc | JDBC ghi |
|---|---|---|---|
| `boolean` | `Boolean` / `boolean` | `getBoolean`, `getObject(..., Boolean.class)` | `setBoolean`, `setObject` |
| `smallint` | `Short` / `short` | `getShort` | `setShort` |
| `integer` | `Integer` / `int` | `getInt` | `setInt` |
| `bigint` | `Long` / `long` | `getLong` | `setLong` |
| `numeric`, `decimal` | `BigDecimal` | `getBigDecimal` | `setBigDecimal` |
| `real` | `Float` / `float` | `getFloat` | `setFloat` |
| `double precision` | `Double` / `double` | `getDouble` | `setDouble` |
| `text`, `varchar` | `String` | `getString` | `setString` |
| `date` | `LocalDate` | `getObject(..., LocalDate.class)` | `setObject(LocalDate)` |
| `time` không timezone | `LocalTime` | `getObject(..., LocalTime.class)` | `setObject(LocalTime)` |
| `timestamp` không timezone | `LocalDateTime` | `getObject(..., LocalDateTime.class)` | `setObject(LocalDateTime)` |
| `timestamptz` | `OffsetDateTime` | `getObject(..., OffsetDateTime.class)` | `setObject(OffsetDateTime)` |
| `uuid` | `UUID` | `getObject(..., UUID.class)` | `setObject(UUID)` |
| `bytea` | `byte[]` | `getBytes` | `setBytes` |
| `text[]`, `integer[]` | `java.sql.Array`, array Java tương ứng | `getArray` | `createArrayOf` + `setArray` |
| `json`, `jsonb` | JSON string / `PGobject` / domain model qua JSON parser | `getString`, `getObject` | `PGobject` hoặc cast rõ |
| `interval` | `PGInterval` hoặc kiểu domain | `getObject` rồi kiểm tra kiểu | `PGInterval` / SQL expression phù hợp |
| PostgreSQL ENUM | `String` / Java enum theo converter | `getString` | `setObject` + cast/type |
| `inet`, `cidr`, range... | `String` / `PGobject` / converter | `getString`, `getObject` | Cast rõ / PGobject |

Bảng này là **lựa chọn sử dụng phổ biến**, không phải lời hứa rằng mọi overload hoặc kiểu Java đều được driver hỗ trợ giống nhau. Đặc biệt với SQL NULL, ngày giờ cực trị và các kiểu PostgreSQL-specific, cần những phần hướng dẫn phía sau.

## 5. Những kiểu số nguyên và giới hạn phạm vi

PostgreSQL cung cấp:

| PostgreSQL | Dung lượng | Khoảng thường dùng | Java |
|---|---:|---|---|
| `smallint` | 2 bytes | -32.768 đến 32.767 | `short` / `Short` |
| `integer` | 4 bytes | -2.147.483.648 đến 2.147.483.647 | `int` / `Integer` |
| `bigint` | 8 bytes | -2^63 đến 2^63−1 | `long` / `Long` |

Ví dụ đọc:

~~~java
short priority = rs.getShort("priority");
int attemptCount = rs.getInt("attempt_count");
long orderId = rs.getLong("order_id");
~~~

Ví dụ ghi:

~~~java
ps.setShort(1, (short) 2);
ps.setInt(2, 3);
ps.setLong(3, 9_223_372_036L);
~~~

### 5.1. Không dùng int cho BIGINT chỉ vì dữ liệu hôm nay còn nhỏ

Một cột `bigint` thường được dùng vì dải giá trị rộng. Nếu đọc bằng `getInt()`, giá trị tăng vượt phạm vi có thể gây lỗi conversion hoặc làm ứng dụng không còn đúng. Chọn `Long` cho hợp đồng BIGINT.

### 5.2. SERIAL không phải một kiểu số riêng

`smallserial`, `serial`, `bigserial` là cách khai báo tạo cột số và sequence/default liên quan. Trong JDBC, giá trị vẫn được xử lý theo kiểu số thực tế: `smallint`, `integer` hoặc `bigint`.

### 5.3. IDENTITY cũng là cơ chế sinh giá trị

~~~sql
event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
~~~

Phía Java đọc `event_id` thành Long, không có Java type tên “Identity”. Với INSERT muốn lấy ID, nên dùng `RETURNING` hoặc JDBC generated keys phù hợp.

### 5.4. Cột Nullable nên dùng wrapper

Nếu `attempt_count integer NULL`, có thể dùng `Integer` thay `int` để biểu diễn thiếu giá trị. Primitive không thể chứa null.

## 6. SQL NULL khác số 0 và false

Đây là một trong những lỗi ánh xạ nghiêm trọng và khó phát hiện.

~~~java
int count = rs.getInt("attempt_count");
~~~

Nếu cột SQL là NULL, JDBC primitive getter trả giá trị mặc định (ví dụ `0`), nên không thể suy ra đó là “số lần thử bằng 0”.

### 6.1. Kiểm tra wasNull ngay sau getter

~~~java
int value = rs.getInt("attempt_count");
Integer attemptCount = rs.wasNull() ? null : value;
~~~

Tương tự:

~~~java
boolean value = rs.getBoolean("enabled");
Boolean enabled = rs.wasNull() ? null : value;
~~~

### 6.2. wasNull dựa trên giá trị vừa đọc

Không gọi một getter khác trước khi kiểm tra `wasNull()`, vì nó phản ánh trạng thái NULL của giá trị cột được đọc gần nhất.

### 6.3. getObject với wrapper

Khi driver hỗ trợ:

~~~java
Integer attemptCount =
    rs.getObject("attempt_count", Integer.class);
~~~

Nếu cột SQL NULL, phương án trả object có thể cho Java null trực tiếp. Hãy kiểm tra behavior trên driver version đang dùng.

### 6.4. SQL NULL không phải chuỗi rỗng

`NULL` trong `text` không giống `''`. `getString()` trả null cho SQL NULL và chuỗi rỗng cho giá trị `''`.

### 6.5. Kiểu domain phải thể hiện chủ đích

Nếu boolean nullable có nghĩa “chưa biết”, dùng `Boolean` hoặc enum ba trạng thái thay vì âm thầm gán false.

## 7. NUMERIC/DECIMAL và BigDecimal

Với dữ liệu tiền hoặc các giá trị thập phân cần chính xác, dùng `numeric(p,s)` trong PostgreSQL và `java.math.BigDecimal` trong Java.

~~~sql
CREATE TABLE billing_examples (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(18,4) NOT NULL,
    tax_rate NUMERIC(9,6) NOT NULL
);
~~~

~~~java
BigDecimal amount = rs.getBigDecimal("amount");
BigDecimal taxRate = rs.getBigDecimal("tax_rate");
~~~

### 7.1. Vì sao không dùng double cho tiền?

`double` là floating-point nhị phân. Nhiều giá trị thập phân như 0,1 không có biểu diễn chính xác trong hệ nhị phân hữu hạn, nên arithmetic có thể tạo sai số làm tròn.

### 7.2. Tạo BigDecimal từ chuỗi

~~~java
BigDecimal price = new BigDecimal("1250.75");
~~~

Tránh:

~~~java
BigDecimal price = new BigDecimal(0.1);
~~~

Constructor nhận double có thể giữ lại sai số biểu diễn nhị phân. Khi đầu vào là double, có thể dùng `BigDecimal.valueOf(double)` nếu đã hiểu giới hạn của nguồn dữ liệu, nhưng tốt hơn là nhận từ string/decimal source ngay từ đầu.

### 7.3. Ghi BigDecimal

~~~java
ps.setBigDecimal(1, new BigDecimal("199.9900"));
~~~

PostgreSQL áp dụng typmod precision/scale của cột theo ngữ nghĩa SQL. App vẫn nên validate nghiệp vụ trước khi ghi.

### 7.4. Chú ý precision và scale

- **Precision**: tổng số chữ số có nghĩa theo định nghĩa numeric.
- **Scale**: số chữ số sau dấu thập phân được khai báo ở cột.
- Một giá trị vượt phạm vi có thể bị PostgreSQL từ chối.
- Giá trị có nhiều chữ số thập phân hơn scale có thể bị làm tròn khi lưu.

### 7.5. BigDecimal.equals khác compareTo

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));      // false
System.out.println(a.compareTo(b) == 0); // true
~~~

`equals` cân nhắc scale, trong khi `compareTo` so giá trị số. Điều này quan trọng khi dùng BigDecimal làm key trong Set/Map hoặc so sánh domain.

## 8. Quy tắc rounding cho tiền và tỷ lệ

Một số hệ thống muốn làm tròn chính xác theo chính sách nghiệp vụ:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("99.995");
BigDecimal rounded = price.setScale(2, RoundingMode.HALF_UP);
~~~

### 8.1. Không mặc định PostgreSQL và Java dùng cùng quy tắc

PostgreSQL `numeric` và Java `BigDecimal` có những behavior rounding khác trong một số tình huống/tie cases, đặc biệt khi chuyển đổi giữa numeric và floating-point. Chọn rõ quy tắc nghiệp vụ và test cùng input.

### 8.2. Không round quá nhiều lần

Nếu tiền được round ở từng dòng rồi tổng, kết quả có thể khác tổng trước rồi round. Quy tắc cần được thống nhất giữa SQL, Java và báo cáo.

### 8.3. Tránh chuyển BigDecimal thành double ở giữa

~~~java
// Không phù hợp khi cần giữ chính xác thập phân tuyệt đối:
double asDouble = amount.doubleValue();
~~~

Một khi mất precision, chuyển lại BigDecimal không giúp khôi phục toàn bộ chữ số ban đầu.

### 8.4. Giá trị đặc biệt của NUMERIC

PostgreSQL có hỗ trợ một số giá trị đặc biệt như NaN và tùy phiên bản Infinity trong numeric. Java BigDecimal **không biểu diễn NaN/Infinity**. Nếu cột có khả năng chứa giá trị đó, quy ước domain rõ và kiểm tra conversion; đối với tiền nên có constraints để loại dữ liệu không phù hợp.

## 9. REAL và DOUBLE PRECISION

PostgreSQL:

- `real`: số thực dấu phẩy động độ chính xác đơn.
- `double precision`: số thực độ chính xác kép.

Java:

~~~java
float f = rs.getFloat("sensor_value");
double d = rs.getDouble("confidence");
~~~

Ghi:

~~~java
ps.setFloat(1, 0.75f);
ps.setDouble(2, 0.987654321);
~~~

### 9.1. Khi nào nên dùng?

Phù hợp các tính toán khoa học, đo lường hoặc kết quả xấp xỉ mà sai số floating-point được chấp nhận.

### 9.2. NaN và Infinity

Java `Float`/`Double` có thể biểu diễn NaN và ±Infinity; PostgreSQL floating types có behavior tương ứng. Nhưng JSON serializer, báo cáo và database constraints có thể không chấp nhận các giá trị này. Cần quy định ở tầng domain.

### 9.3. Không so sánh bằng tuyệt đối khi giá trị xấp xỉ

Các phép tính floating point thường cần tolerance, nhưng tolerance phải tương ứng đơn vị/precision. Không dùng chiến lược tolerance cho tiền mà lẽ ra phải dùng BigDecimal.

## 10. BOOLEAN

PostgreSQL `boolean` hỗ trợ TRUE/FALSE/NULL. Trong Java:

~~~java
Boolean verified = rs.getObject("verified", Boolean.class);
~~~

hoặc:

~~~java
boolean verifiedPrimitive = rs.getBoolean("verified");
boolean isUnknown = rs.wasNull();
~~~

### 10.1. getBoolean trả false khi SQL NULL

Nếu bỏ `wasNull()`, ba trạng thái TRUE, FALSE, NULL có thể bị thu hẹp thành hai trạng thái, làm thay đổi nghiệp vụ.

### 10.2. Ghi NULL có kiểu

~~~java
ps.setNull(1, java.sql.Types.BOOLEAN);
~~~

hoặc dùng `setObject(..., null, Types.BOOLEAN)` khi API/driver hỗ trợ đúng cách.

### 10.3. Không đọc boolean bằng getString để tự parse nếu không cần

PostgreSQL driver hiểu boolean; tự parse `"t"`, `"true"`, `"1"` qua String có thể tạo lỗi không cần thiết.

## 11. TEXT, VARCHAR và CHAR

Các kiểu văn bản thường gặp:

| PostgreSQL | Java | Lưu ý |
|---|---|---|
| `text` | `String` | Không có giới hạn ký tự kiểu VARCHAR(n) |
| `varchar(n)` | `String` | PostgreSQL kiểm soát giới hạn độ dài |
| `varchar` | `String` | Không có typmod độ dài cụ thể |
| `char(n)` / `character(n)` | `String` | Padding và semantics khoảng trắng cần chú ý |
| `citext` (extension) | `String` | So sánh không phân biệt hoa/thường theo extension/collation |

~~~java
String title = rs.getString("title");
ps.setString(1, "PostgreSQL và Java");
~~~

### 11.1. PostgreSQL text và Java String khác cách tính độ dài

Java `String.length()` đếm UTF-16 code units, không nhất thiết bằng số code points hoặc ký tự nhìn thấy. PostgreSQL `char_length` đếm ký tự theo encoding; `octet_length` đếm bytes.

### 11.2. Unicode tiếng Việt

Chuỗi có dấu có thể có các dạng Unicode tổ hợp khác nhau. Hai chuỗi nhìn giống nhau chưa chắc bằng nhau theo mọi phép so sánh/collation. Khi cần chuẩn hóa Unicode, xác định rõ nơi thực hiện và giữ contract nhất quán.

### 11.3. Không tự trim dữ liệu trừ khi hợp đồng yêu cầu

`text` giữ khoảng trắng có ý nghĩa. Tự động `.trim()` hoặc `.strip()` ở DTO mapper có thể làm mất dữ liệu văn bản, token hoặc định danh.

### 11.4. PostgreSQL không lưu ký tự NUL trong text

Java String có thể chứa ký tự `\u0000` theo nghĩa một code unit zero; PostgreSQL text không chấp nhận NUL. Cần validate input nếu dữ liệu có thể chứa byte/character đặc biệt. Với dữ liệu nhị phân, chọn BYTEA thay vì ép vào TEXT.

### 11.5. CHAR(n) không phải kiểu tối ưu mặc định

`character(n)` có padding/trailing-space semantics có thể gây bất ngờ. Phần lớn dữ liệu tên, mô tả, mã tự do phù hợp `text` hoặc `varchar(n)` hơn.

## 12. Ngày giờ là nhóm ánh xạ cần thận trọng nhất

PostgreSQL có:

- `date`: ngày lịch, không thời gian.
- `time without time zone`: giờ trong ngày, không offset.
- `timestamp without time zone`: ngày + giờ cục bộ, không có múi giờ gắn vào giá trị.
- `timestamp with time zone` / `timestamptz`: thời điểm tuyệt đối, hiển thị theo session timezone.
- `time with time zone` / `timetz`: giờ có offset; có nhiều giới hạn sử dụng, thường không phải lựa chọn thiết kế mới được khuyến nghị cho đa số nghiệp vụ.
- `interval`: khoảng thời gian/calendar components.

| PostgreSQL | Java 8+ thường phù hợp | Ví dụ ý nghĩa |
|---|---|---|
| `date` | `LocalDate` | Ngày sinh, hạn theo ngày |
| `time` | `LocalTime` | Giờ mở cửa theo lịch |
| `timestamp` | `LocalDateTime` | Giờ hẹn theo lịch, chưa gán zone |
| `timestamptz` | `OffsetDateTime`, convert sang `Instant` | Thời điểm giao dịch |
| `timetz` | Driver-specific handling | Giờ + offset; không lưu timezone ID |
| `interval` | `PGInterval` / kiểu domain tách thành phần | Hai tháng, ba ngày, 4 giờ |

### 12.1. Không gắn múi giờ một cách ngầm

Một `LocalDateTime` chỉ là lịch + đồng hồ địa phương, không xác định một instant toàn cầu cho tới khi áp quy tắc `ZoneId`.

### 12.2. TIMESTAMPTZ không lưu ZoneId gốc

PostgreSQL chuẩn hóa giá trị thành một thời điểm và có thể hiển thị theo `TimeZone` của session. Nếu khách hàng nhập `Asia/Ho_Chi_Minh` hay `Europe/Paris`, PostgreSQL không tự giữ tên vùng đó trong cột timestamptz.

### 12.3. Dấu cộng trong timestamp

PostgreSQL có cú pháp rõ:

~~~sql
TIMESTAMPTZ '2026-11-14 10:30:00+07'
~~~

Nó biểu diễn một instant với offset +07:00 tại thời điểm nhập; offset này không phải timezone ID đầy đủ có quy tắc DST lịch sử.

## 13. DATE ↔ LocalDate

PostgreSQL:

~~~sql
SELECT DATE '2026-11-14' AS event_date;
~~~

JDBC 4.2/pgJDBC:

~~~java
LocalDate date = rs.getObject("event_date", LocalDate.class);
ps.setObject(1, LocalDate.of(2026, 11, 14));
~~~

### 13.1. Không dùng java.util.Date khi không cần

`java.util.Date` biểu diễn một thời điểm kiểu epoch milliseconds, khác về semantics với ngày lịch không gắn giờ và zone. `LocalDate` thường phù hợp hơn cho SQL DATE.

### 13.2. Legacy API

~~~java
java.sql.Date sqlDate = rs.getDate("event_date");
LocalDate localDate = sqlDate == null ? null : sqlDate.toLocalDate();
~~~

Khi sử dụng legacy DATE/Timestamp APIs, cần chú ý conversion/default timezone ở các ngữ cảnh có liên quan.

### 13.3. DATE vô cùng và giá trị cực trị

PostgreSQL hỗ trợ những giá trị đặc biệt như `infinity` và `-infinity` cho date/timestamps theo kiểu. Không giả định mọi giá trị có thể ánh xạ tự nhiên vào `LocalDate` trong toàn bộ versions. Nếu domain có giá trị cực trị, định nghĩa chính sách rõ và integration test.

### 13.4. Date-of-birth không phải instant

Một ngày sinh `2000-01-01` không cần đổi qua UTC offset. Ép DATE thành Instant có thể làm hiển thị sai ngày ở nơi có múi giờ khác.

## 14. TIME WITHOUT TIME ZONE ↔ LocalTime

PostgreSQL:

~~~sql
SELECT TIME '09:15:30.123456' AS opening_time;
~~~

Java:

~~~java
LocalTime t = rs.getObject("opening_time", LocalTime.class);
ps.setObject(1, LocalTime.of(9, 15, 30, 123_456_000));
~~~

### 14.1. Cách hiểu

LocalTime đại diện giờ-phút-giây trong ngày **không gắn ngày và zone**. Hữu ích cho lịch làm việc hoặc giờ mở cửa theo địa phương.

### 14.2. 09:00 không phải 09:00 UTC

Nếu cửa hàng mở lúc 9 giờ tại Hà Nội, cần lưu vùng `Asia/Ho_Chi_Minh` trong thông tin business, hoặc có quy tắc cấu hình riêng. LocalTime tự nó không cho biết múi giờ.

### 14.3. TIME WITH TIME ZONE

`timetz` có offset gắn với giờ nhưng không chứa ngày để áp dụng DST đúng mọi tình huống. Đừng suy luận pgJDBC luôn hỗ trợ `OffsetTime` trên mọi version chỉ vì Java có lớp đó. Chỉ sử dụng khi cần semantics và đã thử driver cụ thể.

### 14.4. Độ phân giải thời gian

PostgreSQL timestamp/time thường có độ chính xác microseconds, trong khi Java time types hỗ trợ nanoseconds. Dữ liệu nano có thể bị giới hạn/làm tròn khi ghi. Test các trường hợp cuối giây thay vì mong mọi chữ số nano được giữ.

## 15. TIMESTAMP WITHOUT TIME ZONE ↔ LocalDateTime

PostgreSQL:

~~~sql
SELECT TIMESTAMP '2026-11-14 08:45:00' AS local_meeting;
~~~

Java:

~~~java
LocalDateTime local = rs.getObject(
    "local_meeting",
    LocalDateTime.class
);
ps.setObject(1, LocalDateTime.of(2026, 11, 14, 8, 45));
~~~

### 15.1. Không tự gán UTC

SQL `timestamp without time zone` không đại diện một instant duy nhất. Gọi `local.toInstant(ZoneOffset.UTC)` chỉ đúng nếu ứng dụng **đã có quy ước rõ** rằng giá trị đó là thời gian UTC.

### 15.2. Cấu hình JVM timezone không nên định nghĩa hợp đồng ngầm

Một chương trình chạy ở UTC, một chương trình chạy tại Asia/Ho_Chi_Minh có thể xử lý legacy `Timestamp` khác nhau nếu ứng dụng chuyển qua epoch/Calendar mà không có quy tắc thống nhất.

### 15.3. Khi cần lưu lịch hẹn tương lai

Một cuộc hẹn 09:00 theo zone có DST cần cả **LocalDateTime và ZoneId** hoặc một mô hình lịch hẹn rõ ràng. Nếu chỉ lưu instant hôm nay mà sau này luật DST thay đổi, ý nghĩa “9 giờ địa phương” có thể khác.

### 15.4. Không dùng LocalDateTime cho thời điểm giao dịch tuyệt đối

Trường hợp created_at/paid_at/audit timestamp thường có ý nghĩa instant, nên ưu tiên `timestamptz` và kiểu Java mang instant/offset.

## 16. TIMESTAMPTZ ↔ OffsetDateTime

PostgreSQL:

~~~sql
SELECT TIMESTAMPTZ '2026-11-14 10:00:00+07' AS occurred_at;
~~~

Java:

~~~java
OffsetDateTime value = rs.getObject(
    "occurred_at",
    OffsetDateTime.class
);
Instant instant = value.toInstant();
~~~

Ghi:

~~~java
OffsetDateTime moment = OffsetDateTime.now(ZoneOffset.UTC);
ps.setObject(1, moment);
~~~

### 16.1. PostgreSQL lưu instant, không giữ offset nhập ban đầu

`2026-11-14 10:00+07` và `2026-11-14 03:00+00` biểu diễn cùng instant. Khi đọc bằng OffsetDateTime, pgJDBC thường trả về offset UTC cho `timestamptz`; không kỳ vọng lấy lại +07:00 mà client đã truyền vào.

### 16.2. OffsetDateTime không giống ZonedDateTime

`ZoneOffset.ofHours(7)` là độ lệch cố định. `ZoneId.of("Europe/Paris")` mang quy tắc vùng qua các ngày. Một cột timestamptz không thể khôi phục tên ZoneId ban đầu.

### 16.3. Java Instant có thể phù hợp domain

Nếu business chỉ cần một instant, có thể chuyển:

~~~java
Instant occurredAt = rs.getObject(
    "occurred_at", OffsetDateTime.class
).toInstant();
~~~

Với cột nullable, phải kiểm tra null trước khi gọi `.toInstant()`.

### 16.4. Không mặc định getObject(..., Instant.class)

Tùy pgJDBC version, `Instant` có thể không phải lớp được hỗ trợ trực tiếp trong JDBC getter/setter. Con đường chắc chắn hơn cho timestamptz là OffsetDateTime rồi chuyển Instant.

### 16.5. TimeZone session ảnh hưởng biểu diễn SQL text

~~~sql
SHOW TimeZone;
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 10:00:00+07';
~~~

Kết quả hiển thị có thể thay theo session TimeZone, nhưng instant vẫn không đổi.

## 17. DST và chuyển đổi giờ địa phương

Một thời điểm theo zone có DST có thể gặp:

- **Gap**: giờ địa phương không tồn tại khi đồng hồ nhảy lên.
- **Overlap**: cùng một giờ địa phương xảy ra hai lần khi đồng hồ lùi lại.

Java:

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local =
    LocalDateTime.of(2026, 10, 25, 2, 30);

ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();
~~~

### 17.1. atZone có quy tắc xử lý gap/overlap

Không coi `atZone` là phép kiểm tra “ngày giờ có duy nhất một instant”; Java áp dụng quy tắc mặc định để giải quyết gap/overlap. Với hệ thống đặt lịch quan trọng, cần xác nhận người dùng muốn offset nào hoặc có cho phép giờ không tồn tại không.

### 17.2. Lưu zone ID ở đâu?

Nếu cần giữ ý định lịch hẹn theo vùng, có thể lưu một cột `text` riêng như `time_zone_id` cùng local date/time và quy tắc chuyển đổi.

### 17.3. Không lấy múi giờ máy chủ làm chính sách

Production chạy container UTC trong khi ứng dụng ở Việt Nam hoặc châu Âu. Zone phải đến từ domain/user/business requirement, không từ cấu hình ngẫu nhiên của máy chạy.

### 17.4. Offset không giải quyết đầy đủ lịch tương lai

`+01:00` tại tháng 1 không nhất thiết áp dụng vào tháng 7 cùng vùng. Với lịch lặp định kỳ, ZoneId quan trọng hơn một offset cố định.

## 18. Legacy Timestamp, Calendar và tính tương thích

Các codebase cũ thường dùng:

~~~java
Timestamp ts = rs.getTimestamp("occurred_at");
Date date = rs.getDate("birth_date");
Time time = rs.getTime("opens_at");
~~~

### 18.1. Không trộn java.sql.Date và java.util.Date tùy tiện

Hai lớp có cùng tên `Date` nhưng semantics khác. Ưu tiên `java.time` trong code mới.

### 18.2. Timestamp có nanoseconds API

`java.sql.Timestamp` hỗ trợ phần nano trong Java, nhưng PostgreSQL timestamp precision có giới hạn; không mặc định 9 chữ số nano sẽ round-trip nguyên vẹn.

### 18.3. Calendar overloads

JDBC có những overload như `getTimestamp(column, Calendar)` để ảnh hưởng cách đọc/diễn giải ở các tình huống legacy. Khi migrate sang `LocalDateTime`/`OffsetDateTime`, cần test kết quả thực, không thay getter hàng loạt chỉ vì method tên ngắn hơn.

### 18.4. Quy tắc migration

Chọn một quy ước rõ cho từng cột: DATE = ngày lịch, TIMESTAMP = wall-clock local, TIMESTAMPTZ = instant. Sau đó sửa domain model, serializer, tests và queries đồng bộ.

## 19. UUID ↔ java.util.UUID

PostgreSQL có kiểu `uuid`:

~~~sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    label TEXT NOT NULL
);
~~~

Java:

~~~java
UUID id = rs.getObject("id", UUID.class);
ps.setObject(1, UUID.randomUUID());
~~~

### 19.1. UUID là giá trị nhị phân logic, không phải text tùy ý

Bạn có thể dùng `getString()` để hiển thị UUID, nhưng `UUID` Java type giúp code biểu diễn đúng domain và hạn chế lỗi parse.

### 19.2. Khi cần String JSON

~~~java
String serialized = id.toString();
UUID restored = UUID.fromString(serialized);
~~~

Kiểm tra null trước khi gọi phương thức.

### 19.3. UUID không tự có ý nghĩa bảo mật

Một UUID ngẫu nhiên không nên được coi là authentication token có quyền chỉ vì khó đoán; còn tùy phiên bản sinh, entropy, lifetime và authorization.

### 19.4. Phân biệt khóa chính và business identifier

UUID có thể là surrogate key, nhưng không thay UNIQUE constraint cho các field nghiệp vụ như order_number nếu chúng phải duy nhất.

## 20. JSON và JSONB: PostgreSQL type khác Java object

PostgreSQL:

~~~sql
CREATE TABLE events_json (
    event_id BIGINT PRIMARY KEY,
    payload JSONB NOT NULL
);
~~~

JSONB lưu dữ liệu JSON theo biểu diễn nhị phân nội bộ đã parse/chuẩn hóa; không nhất thiết giữ nguyên whitespace, thứ tự keys hoặc bản gốc text. JSON giữ văn bản đầu vào gần hơn, với behavior parse/validation khác.

### 20.1. getString

~~~java
String jsonText = rs.getString("payload");
~~~

Dùng JSON parser như Jackson hoặc Gson để biến chuỗi thành domain class hoặc tree. `getString()` không tự biến JSON thành `Map` hay DTO.

### 20.2. PGobject

Một cách đọc phổ biến với pgJDBC:

~~~java
Object raw = rs.getObject("payload");
if (raw instanceof org.postgresql.util.PGobject) {
    org.postgresql.util.PGobject obj =
        (org.postgresql.util.PGobject) raw;
    String postgresTypeName = obj.getType();
    String json = obj.getValue();
}
~~~

Với các kiểu do driver chưa có mapping Java chuẩn, PGobject mang tên kiểu PostgreSQL và giá trị dạng text tương ứng.

### 20.3. Không gán nhầm Types.VARCHAR khi ghi JSONB

Một parameter String được JDBC gửi như varchar/text có thể không được PostgreSQL tự chuyển sang jsonb ở mọi statement context. Dùng cast rõ hoặc một PGobject có type jsonb.

### 20.4. JSONB chỉ xác nhận cú pháp JSON, không xác nhận toàn bộ business schema

Giá trị `{"price":"abc"}` là JSON hợp lệ nhưng có thể không hợp lệ cho domain giá tiền. Cần JSON schema/domain validation ở tầng thích hợp, kết hợp constraints khi cần.

## 21. Ghi JSONB qua PGobject và cast rõ

### 21.1. Dùng PGobject

~~~java
import org.postgresql.util.PGobject;

PGobject jsonb = new PGobject();
jsonb.setType("jsonb");
jsonb.setValue("{\"source\":\"jdbc\",\"attempt\":2}");

ps.setObject(1, jsonb);
~~~

### 21.2. Dùng cast SQL

~~~sql
INSERT INTO events_json(event_id, payload)
VALUES (?, ?::jsonb);
~~~

~~~java
ps.setLong(1, 101L);
ps.setString(2, "{\"source\":\"jdbc\"}");
~~~

### 21.3. Hai cách, một mục tiêu

Cả hai giúp PostgreSQL xác định parameter là JSONB ở vị trí cần thiết. Cần test với driver, prepared statements, casts và SQL thật.

### 21.4. Tránh nối chuỗi JSON trực tiếp vào SQL

Không xây:

~~~java
// SAI: ghép JSON/user input thành SQL text
String sql = "INSERT INTO events_json(payload) VALUES ('"
           + jsonFromUser + "')";
~~~

Lỗi dấu nháy, escaping và SQL injection có thể xảy ra. Parameterize dữ liệu bằng `PreparedStatement`.

## 22. SQL NULL khác JSON null

Ba trường hợp:

~~~sql
SELECT
    NULL::jsonb                  AS sql_null,
    'null'::jsonb                AS json_null,
    '{}'::jsonb                  AS empty_object;
~~~

- `NULL::jsonb`: giá trị SQL NULL, cột không có giá trị.
- `'null'::jsonb`: giá trị JSON literal null, cột SQL vẫn không NULL.
- `'{}'::jsonb`: JSON object rỗng.

### 22.1. JDBC getString

Nếu SQL NULL: `getString()` thường trả Java null.

Nếu JSON literal null: `getString()` thường trả chuỗi `"null"` (bốn ký tự n-u-l-l), không phải Java null.

### 22.2. Jackson tree model

Một JSON parser có thể biểu diễn JSON null bằng node riêng, khác việc không có giá trị SQL. Nếu ứng dụng cần phân biệt, không gộp cả hai thành một Java null.

### 22.3. Array JSON rỗng khác SQL ARRAY rỗng

JSON `[]` lưu trong jsonb khác cột PostgreSQL kiểu `text[]` có giá trị `ARRAY[]::text[]`. Chúng có operators, indexes và schema semantics khác nhau.

### 22.4. JSON type và Java schema evolution

Nếu payload JSONB chứa field mới, Java DTO cũ có thể cần ignore unknown fields hoặc versioning; ngược lại, PostgreSQL không mặc định kiểm tra domain schema của từng property.

## 23. Ký tự ? trong toán tử JSONB và JDBC

PostgreSQL JSONB có các toán tử tồn tại key, trong đó `?` là toán tử SQL. Nhưng JDBC cũng dùng dấu hỏi cho **parameter placeholder**.

~~~sql
SELECT payload ? 'customerId'
FROM events_json;
~~~

### 23.1. Xung đột khi viết PreparedStatement

Trong PostgreSQL JDBC, khi cần gửi dấu hỏi literal thuộc toán tử PostgreSQL, driver hỗ trợ escaping `??` trong SQL của `PreparedStatement` cho trường hợp phù hợp.

~~~java
String sql =
    "SELECT event_id FROM events_json WHERE payload ?? ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "customerId");
    // query...
}
~~~

Driver gửi toán tử JSONB tồn tại key và một parameter; số placeholder mà JDBC nhận là một.

### 23.2. Giải pháp cú pháp hàm

Khi muốn tránh xung đột token và API có hàm tương ứng, có thể dùng cách diễn đạt SQL được hỗ trợ như `jsonb_exists(payload, ?)` cho phép toán tồn tại key.

### 23.3. Đừng escape mọi dấu hỏi tùy tiện

`??` là cơ chế đặc thù để phân biệt operator với placeholder trong pgJDBC. Không thay `?` parameter bind bình thường thành `??` vì làm mất vị trí bind.

### 23.4. Kiểm tra câu SQL thực

Khi query phức tạp có nhiều JSON operators và parameters, dùng integration test xác nhận số placeholders và kết quả thay vì debug bằng cách in mọi parameters nhạy cảm.

## 24. Mảng PostgreSQL và java.sql.Array

PostgreSQL có kiểu mảng như `text[]`, `integer[]`, `uuid[]`, `numeric[]`.

~~~sql
SELECT ARRAY['java', 'jdbc', 'postgresql']::text[] AS tags;
~~~

### 24.1. java.sql.Array không phải java.util.List

`ResultSet.getArray()` trả một đối tượng implement JDBC `java.sql.Array`, từ đó có thể lấy Java array phù hợp hoặc ResultSet biểu diễn các phần tử.

~~~java
java.sql.Array sqlArray = rs.getArray("tags");
if (sqlArray != null) {
    Object nativeArray = sqlArray.getArray();
    // Với text[]/driver tương ứng thường là String[].
}
~~~

### 24.2. Tạo mảng parameter

~~~java
String[] tags = {"jdbc", "postgresql"};
java.sql.Array array =
    connection.createArrayOf("text", tags);

try {
    ps.setArray(1, array);
    ps.executeUpdate();
} finally {
    array.free();
}
~~~

### 24.3. Tên element type phải đúng

Với `uuid[]` có thể dùng element type `"uuid"`; với `int4[]` dùng PostgreSQL element type tương ứng được driver hỗ trợ như `"int4"` hoặc `"integer"`. Không dùng tên Java `"Integer"` mà giả định server hiểu.

### 24.4. NULL array khác empty array

- SQL NULL: không có giá trị mảng.
- `ARRAY[]::text[]`: mảng rỗng.
- `ARRAY[NULL]::text[]`: mảng một phần tử NULL.

Đừng chuyển cả ba thành `Collections.emptyList()` nếu hợp đồng cần phân biệt.

## 25. Đọc và ghi ARRAY an toàn

### 25.1. Đọc text[]

~~~java
java.sql.Array sqlArray = rs.getArray("tags");

List<String> tags;
if (sqlArray == null) {
    tags = null;
} else {
    try {
        String[] values = (String[]) sqlArray.getArray();
        tags = Arrays.asList(values);
    } finally {
        sqlArray.free();
    }
}
~~~

Đoạn này cần `import java.util.Arrays` và `import java.util.List`. Kiểu phần tử cụ thể cần xác nhận driver; không ép mọi loại SQL ARRAY thành `String[]`.

### 25.2. Với integer[]

~~~java
java.sql.Array sqlArray = rs.getArray("scores");
Integer[] scores = sqlArray == null
    ? null
    : (Integer[]) sqlArray.getArray();
~~~

Khi dùng thật, giải phóng resource nếu cần và kiểm tra driver conversion. Tránh ép thành `int[]` khi các phần tử có thể NULL.

### 25.3. Với UUID[]

Có thể tạo array bằng:

~~~java
UUID[] ids = {UUID.randomUUID(), UUID.randomUUID()};
java.sql.Array dbIds = connection.createArrayOf("uuid", ids);
ps.setArray(1, dbIds);
~~~

Giải phóng `dbIds` sau khi statement thực thi xong theo lifecycle được hỗ trợ.

### 25.4. Multidimensional arrays

PostgreSQL cho phép mảng nhiều chiều; Java có thể nhận nested arrays qua driver. Cần test shape, dimensions và phần tử NULL. Không giả định `java.sql.Array.getArray()` luôn trả mảng một chiều.

### 25.5. PostgreSQL array lower bounds

PostgreSQL có thể có array lower bounds không bắt đầu ở 1. Khi chuyển sang Java arrays (0-based), không tự giữ toàn bộ metadata lower bounds. Nếu business logic phụ thuộc chỉ số SQL nguyên gốc, xem `array_lower`/`array_dims` hoặc truy vấn mảng bằng SQL.

## 26. BYTEA ↔ byte[]

Kiểu `bytea` lưu chuỗi bytes, khác `text` lưu chuỗi ký tự.

~~~sql
CREATE TABLE attachments_small (
    id BIGINT PRIMARY KEY,
    content BYTEA
);
~~~

Java:

~~~java
byte[] bytes = rs.getBytes("content");
ps.setBytes(1, bytes);
~~~

### 26.1. Dùng BYTEA cho dữ liệu nhị phân

Các bytes từ ảnh, file nhỏ, hash bytes hoặc dữ liệu mã hóa không phải Unicode text. Không tạo String từ bytes ngẫu nhiên rồi lưu `text` nếu không có encoding rõ ràng.

### 26.2. Ghi stream

~~~java
try (InputStream input = Files.newInputStream(path)) {
    ps.setBinaryStream(1, input);
    ps.executeUpdate();
}
~~~

Mẫu này cần `java.io.InputStream`, `java.nio.file.Files` và `Path`. Lifecycle stream phải kéo dài tới lúc statement sử dụng xong.

### 26.3. Đọc stream

~~~java
try (InputStream input = rs.getBinaryStream("content")) {
    if (input != null) {
        // Đọc theo chunks, tránh giữ toàn bộ dữ liệu lớn trong RAM.
    }
}
~~~

### 26.4. BYTEA không tương đương PostgreSQL Large Object API

PostgreSQL có cơ chế Large Objects riêng, thường tham chiếu bằng OID và API riêng của driver. Không dùng `getBytes()` trên một OID rồi tưởng driver tự tải toàn bộ large object. Khi dùng Large Objects, cần transaction, quyền, lifecycle cleanup và backup strategy phù hợp.

### 26.5. Rủi ro dung lượng

Lưu file lớn trong database có trade-off về WAL, backup, replication, bloat và latency. Có trường hợp phù hợp lưu object storage và metadata trong PostgreSQL, nhưng phải xét tính nhất quán dữ liệu và quy trình xóa/retention.

## 27. Kiểu BIT và VARBIT

PostgreSQL:

~~~sql
SELECT B'1010'::bit(4) AS feature_flags;
SELECT B'101001'::varbit AS variable_flags;
~~~

### 27.1. Không đồng nhất bit(1) với boolean

`bit(1)` là một dãy một bit, còn `boolean` là logic TRUE/FALSE/NULL. Một số driver conversion có thể mang giá trị gần nhau, nhưng schema semantics khác nhau.

### 27.2. Đọc kiểu bit string

Với dãy bit, có thể đọc biểu diễn dạng chuỗi qua `getString()` tùy loại hoặc sử dụng mapping khác được driver hỗ trợ. Kiểm tra chính xác output của `getObject()` và `getColumnType()` trên driver hiện tại.

### 27.3. Không lạm dụng bitfield

Nếu flags có ý nghĩa nghiệp vụ độc lập và cần query/index/constraints thường xuyên, các cột boolean riêng hoặc cấu trúc khác có thể dễ bảo trì hơn một dãy bit khó đọc.

### 27.4. Khi truyền parameter

Dùng PostgreSQL casts và conversion rõ khi cần, thay vì mặc định `setBoolean()` là cách ghi mọi bit string có độ dài tùy ý.

## 28. INTERVAL, Duration và Period không tương đương

PostgreSQL có kiểu `interval` để biểu diễn khoảng thời gian có thể gồm **tháng, ngày và giờ/phút/giây**:

~~~sql
SELECT INTERVAL '2 months 3 days 04:05:06' AS elapsed;
~~~

Một cách đọc phổ biến với PostgreSQL JDBC driver:

~~~java
Object raw = rs.getObject("elapsed");
if (raw instanceof org.postgresql.util.PGInterval) {
    org.postgresql.util.PGInterval interval =
        (org.postgresql.util.PGInterval) raw;

    int years = interval.getYears();
    int months = interval.getMonths();
    int days = interval.getDays();
    int hours = interval.getHours();
    double seconds = interval.getSeconds();
}
~~~

### 28.1. PGInterval là lớp riêng của pgJDBC

`PGInterval` không thuộc `java.sql`. Nếu không muốn các tầng service phụ thuộc driver, hãy chuyển sang một domain model biểu diễn đủ các thành phần lịch và thời lượng.

### 28.2. Duration không biểu diễn tháng lịch

`java.time.Duration` chủ yếu là khoảng thời gian dựa trên giây/nanoseconds. Một tháng có thể dài 28, 29, 30 hoặc 31 ngày. Không chuyển `interval '1 month'` thành `Duration.ofDays(30)` nếu nghiệp vụ thật sự nói “cộng một tháng”.

### 28.3. Period cũng không chứa giờ

`java.time.Period` chứa years/months/days nhưng không chứa phần giờ. PostgreSQL interval có thể chứa cả lịch và time-of-day components, nên không luôn ánh xạ đầy đủ thành một Period hoặc Duration.

### 28.4. Ghi interval qua cast hoặc driver extension

~~~sql
INSERT INTO timing_events(elapsed)
VALUES (?::interval);
~~~

~~~java
ps.setString(1, "2 months 3 days 04:05:06");
~~~

Đây là ví dụ dùng text input đã validate để server parse interval. Có thể dùng `PGInterval` khi API/driver hỗ trợ. Với thời gian giữ khóa hoặc TTL, hãy chọn đơn vị rõ ràng trước khi lưu.

### 28.5. Day khác 24 giờ trong lịch có DST

Nếu thực hiện “cộng một ngày lịch” theo time zone có daylight saving, instant nhận được có thể cách instant ban đầu không đúng 24 giờ. Đừng chuyển đổi calendar periods sang fixed Duration một cách im lặng.

## 29. PostgreSQL ENUM và Java enum

PostgreSQL có thể khai báo một tập nhãn enum:

~~~sql
CREATE TYPE workflow_state AS ENUM (
    'new', 'processing', 'completed', 'failed'
);
~~~

Java:

~~~java
enum WorkflowState {
    NEW, PROCESSING, COMPLETED, FAILED
}
~~~

### 29.1. Nhãn không nhất thiết bằng tên constant

PostgreSQL enum labels có thể viết thường, có khoảng trắng hoặc tên tùy chọn; Java enum identifiers có quy tắc khác. Cần converter rõ:

~~~java
static WorkflowState parseDbState(String dbLabel) {
    if (dbLabel == null) {
        return null;
    }
    return switch (dbLabel) {
        case "new" -> WorkflowState.NEW;
        case "processing" -> WorkflowState.PROCESSING;
        case "completed" -> WorkflowState.COMPLETED;
        case "failed" -> WorkflowState.FAILED;
        default -> throw new IllegalArgumentException(
            "Unknown DB workflow state"
        );
    };
}
~~~

Đoạn switch expression dùng Java 14+; với Java cũ có thể dùng switch statement thông thường.

### 29.2. Đọc enum thường qua getString

~~~java
String label = rs.getString("state");
WorkflowState state = parseDbState(label);
~~~

### 29.3. Ghi enum bằng cast rõ

~~~sql
UPDATE workflows
SET state = ?::workflow_state
WHERE workflow_id = ?;
~~~

~~~java
ps.setString(1, "completed");
ps.setLong(2, 101L);
~~~

Có thể dùng `PGobject` với PostgreSQL type name, nhưng cast explicit giúp SQL dễ hiểu.

### 29.4. Thêm enum label có thể phá Java code

Khi database bổ sung nhãn `'paused'`, ứng dụng dùng `Enum.valueOf` hoặc converter exhaustive cũ có thể lỗi. Đó là vấn đề versioning contract, dù cột vẫn mang cùng kiểu enum trong PostgreSQL.

### 29.5. Đừng thay text bằng enum vô điều kiện

ENUM phù hợp khi tập trạng thái ổn định. Nếu các giá trị thay đổi liên tục, bảng lookup với FK hoặc kiểu text có CHECK có thể giúp quản trị linh hoạt hơn, tùy use case.

## 30. Kiểu mạng INET, CIDR và MACADDR

PostgreSQL có các kiểu mạng:

~~~sql
SELECT INET '192.0.2.45' AS client_ip;
SELECT CIDR '192.0.2.0/24' AS network_block;
~~~

Một cách đơn giản là đọc text:

~~~java
String ip = rs.getString("client_ip");
~~~

### 30.1. Vì sao không dùng InetAddress cho mọi kiểu?

`java.net.InetAddress` biểu diễn địa chỉ IP, nhưng không tự chứa toàn bộ thông tin prefix length của CIDR. Nếu cần semantics subnet, hãy định nghĩa domain type có cả address và prefix.

### 30.2. Ghi INET có kiểu

~~~sql
INSERT INTO access_logs(client_ip) VALUES (?::inet);
~~~

~~~java
ps.setString(1, "192.0.2.46");
~~~

### 30.3. Đừng thay kiểm tra nguồn gốc IP bằng parsing

Một IP trong bảng có thể đến từ HTTP header do client khai báo; giá trị đó không tự xác minh remote peer hoặc chống giả mạo proxy header.

### 30.4. Các lớp mapping đặc thù

Tùy pgJDBC version, `getObject` có thể trả `PGobject` hoặc kiểu extension với một số PostgreSQL-specific types. Nếu sử dụng, cần test output class và converter.

## 31. PostgreSQL Range và Multirange

PostgreSQL hỗ trợ các kiểu range như:

~~~sql
SELECT int4range(1, 10, '[)') AS valid_numbers;

SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 10:00+07',
    TIMESTAMPTZ '2026-11-14 11:00+07',
    '[)'
) AS booking_window;
~~~

### 31.1. Range không chỉ là hai giá trị biên

Nó còn biểu diễn:

- Biên đóng hoặc mở.
- Biên không bị chặn (*unbounded*).
- Range rỗng.
- Các quy tắc chuẩn hóa theo subtype.
- Các phép chứa, giao, chồng lấp trên miền dữ liệu.

### 31.2. Một pair Java start/end có thể mất nghĩa

Nếu một range là `[1,10)`, việc lưu lại hai số 1 và 10 không đủ để biết 10 có thuộc range không. Một range rỗng và range vô hạn còn cần trạng thái riêng.

### 31.3. Driver không có một Java Range chuẩn cho mọi trường hợp

Có thể cần `PGobject` hoặc đọc chuỗi và parse bằng converter hiểu PostgreSQL range grammar; không split chuỗi tại dấu phẩy một cách ngây thơ.

### 31.4. Để PostgreSQL thực hiện phép toán range khi hợp lý

Nếu mục tiêu là lọc booking windows giao nhau, dùng SQL operators/indexes phù hợp thay vì tải tất cả ranges về Java để so thủ công.

## 32. XML và SQLXML

PostgreSQL có kiểu `xml`. JDBC cung cấp giao diện `java.sql.SQLXML` trong những driver hỗ trợ.

~~~java
SQLXML xml = rs.getSQLXML("document_xml");
if (xml != null) {
    try {
        String xmlText = xml.getString();
        // Parse XML an toàn sau khi đọc.
    } finally {
        xml.free();
    }
}
~~~

### 32.1. Giải phóng tài nguyên

`SQLXML.free()` nên được gọi khi hoàn tất, theo lifecycle của driver.

### 32.2. Chống XXE

Khi chuyển XML text thành Java DOM/SAX/StAX, cần cấu hình chống XML External Entity và network resource retrieval trái phép. XML lưu trong PostgreSQL không đồng nghĩa parser Java an toàn.

### 32.3. XML type chưa bảo đảm toàn bộ nghiệp vụ

Tính hợp lệ theo application schema, namespaces và nội dung phải được kiểm tra riêng nếu domain yêu cầu.

## 33. MONEY và đơn vị tiền tệ

PostgreSQL có kiểu `money`, nhưng nó mang đặc thù format/locale. Đối với nhiều hệ thống nghiệp vụ cần tính toán chính xác, thường dễ kiểm soát hơn với:

~~~sql
amount NUMERIC(18,2) NOT NULL,
currency_code CHAR(3) NOT NULL
~~~

Java:

~~~java
BigDecimal amount = rs.getBigDecimal("amount");
String currency = rs.getString("currency_code");
~~~

### 33.1. BigDecimal không chứa currency

`100.00` không cho biết đơn vị là VND hay USD. Phải dùng thêm currency code hoặc một Money domain object.

### 33.2. Một hệ thống khác có thể dùng minor units

BIGINT số cent/số đơn vị nhỏ nhất cũng hợp lý nếu có hợp đồng currency/scale, overflow handling và khả năng đa tiền tệ rõ ràng.

### 33.3. Không đổi NUMERIC sang DOUBLE chỉ để đơn giản hóa mapper

Đây có thể là một breaking semantic change do lỗi precision, bất kể mapper Java có biên dịch được.

## 34. JDBC metadata để xác minh kiểu thực tế

Không nên đoán mapping cho một query phức tạp. JDBC cung cấp `ResultSetMetaData`:

~~~java
ResultSetMetaData md = rs.getMetaData();

for (int i = 1; i <= md.getColumnCount(); i++) {
    System.out.printf(
        "%s | JDBC type=%d | SQL type=%s | Java=%s%n",
        md.getColumnLabel(i),
        md.getColumnType(i),
        md.getColumnTypeName(i),
        md.getColumnClassName(i)
    );
}
~~~

### 34.1. getColumnType không phải PostgreSQL OID

Giá trị này thuộc `java.sql.Types`. PostgreSQL-specific type có thể được báo bằng `Types.OTHER`.

### 34.2. getColumnTypeName giúp thấy typename

Có thể trả `jsonb`, `uuid`, tên enum hoặc tên PostgreSQL array type tùy driver. Dùng để chẩn đoán, không coi đây là domain class mặc định.

### 34.3. Precision, scale, nullable

~~~java
int precision = md.getPrecision(i);
int scale = md.getScale(i);
int nullableFlag = md.isNullable(i);
~~~

Với expressions/views phức tạp, metadata không luôn khẳng định toàn bộ business invariant về nullability.

### 34.4. Log metadata vẫn cần giới hạn

Metadata có thể lộ tên schema nội bộ; không nên dump nguyên ResultSet chứa dữ liệu cá nhân hoặc token chỉ để xem types.

## 35. Đối chiếu PostgreSQL information_schema

~~~sql
SELECT
    column_name,
    data_type,
    udt_schema,
    udt_name,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    datetime_precision,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'jdbc_types_lab'
  AND table_name = 'events'
ORDER BY ordinal_position;
~~~

### 35.1. udt_name có ích cho array và enum

Một PostgreSQL array có thể hiện `data_type='ARRAY'` và `udt_name` theo representation nội bộ. PostgreSQL enum có thể là `USER-DEFINED` và tên enum thể hiện ở `udt_name`.

### 35.2. Không hiểu getString thành schema text

Rất nhiều kiểu có thể có biểu diễn chuỗi. Nhưng một kiểu có thể đọc qua String không có nghĩa được phép chuyển cột đó thành TEXT mà không đổi semantics.

### 35.3. Schema-qualified casting

Nếu hai schemas cùng có enum tên `status`, một cast không ghi schema có thể resolve theo `search_path` không mong muốn. Trong migration và prepared SQL quan trọng, sử dụng tên kiểu đầy đủ.

## 36. Lab: tạo bảng thử nghiệm đủ nhiều kiểu dữ liệu

Lab chỉ chạy trong database **thử nghiệm**, không dùng production. Nếu schema `jdbc_types_lab` đã tồn tại, dùng tên khác thay vì xóa dữ liệu của người khác.

~~~sql
CREATE SCHEMA jdbc_types_lab;

CREATE TYPE jdbc_types_lab.event_state AS ENUM (
    'new', 'processed', 'failed'
);

CREATE TABLE jdbc_types_lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id UUID NOT NULL UNIQUE,
    owner_name TEXT NOT NULL,
    note VARCHAR(200),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    attempts INTEGER,
    total_amount NUMERIC(18,4) NOT NULL
        CHECK (total_amount >= 0),
    confidence DOUBLE PRECISION,
    event_day DATE NOT NULL,
    local_time TIME WITHOUT TIME ZONE,
    local_deadline TIMESTAMP WITHOUT TIME ZONE,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    duration INTERVAL,
    payload JSONB,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
    data BYTEA,
    source_ip INET,
    state jdbc_types_lab.event_state NOT NULL
        DEFAULT 'new'
);
~~~

### 36.1. Tại sao chọn kiểu dữ liệu rõ?

PostgreSQL có thể kiểm tra UUID, parse JSONB, giới hạn NUMERIC, hiểu INET operators và ngày giờ theo type. Nếu lưu tất cả thành TEXT, ứng dụng phải tự tái tạo nhiều ràng buộc và chịu rủi ro dữ liệu không hợp lệ.

### 36.2. Các cột có NULL

`note`, `attempts`, `duration`, `payload` và một số trường khác cho phép NULL để kiểm tra mapper. `active`, `total_amount`, `event_day`, `occurred_at` và `tags` có NOT NULL theo schema.

### 36.3. event_day không nhất thiết bằng ngày UTC của occurred_at

Nếu event_day là ngày nghiệp vụ theo Việt Nam, nó có thể khác ngày lịch UTC của cùng instant. Đây là contract domain, không nên suy từ tên cột.

## 37. Lab: INSERT từ SQL để tạo fixture

~~~sql
INSERT INTO jdbc_types_lab.events (
    external_id, owner_name, note, active, attempts,
    total_amount, confidence, event_day, local_time,
    local_deadline, occurred_at, duration, payload,
    tags, data, source_ip, state
)
VALUES (
    UUID '550e8400-e29b-41d4-a716-446655440000',
    'Nguyễn An',
    NULL,
    TRUE,
    NULL,
    1234.5600,
    0.98,
    DATE '2026-11-14',
    TIME '09:30:00.123456',
    TIMESTAMP '2026-11-14 09:30:00',
    TIMESTAMPTZ '2026-11-14 09:30:00+07',
    INTERVAL '1 month 2 days 03:04:05',
    '{"source":"jdbc-lab","attempt":null}'::jsonb,
    ARRAY['jdbc','postgresql']::text[],
    decode('DEADBEEF', 'hex'),
    INET '192.0.2.45',
    'new'
)
RETURNING event_id;
~~~

### 37.1. Kiểm tra dữ liệu

~~~sql
SELECT
    event_id, external_id, owner_name, attempts,
    total_amount, occurred_at, tags, state
FROM jdbc_types_lab.events
ORDER BY event_id;
~~~

### 37.2. Kiểm tra kiểu tại server

~~~sql
SELECT
    pg_typeof(external_id),
    pg_typeof(total_amount),
    pg_typeof(occurred_at),
    pg_typeof(payload),
    pg_typeof(tags),
    pg_typeof(state)
FROM jdbc_types_lab.events
LIMIT 1;
~~~

### 37.3. Kiểm tra precision và bytes

~~~sql
SELECT
    total_amount,
    octet_length(data) AS binary_size,
    cardinality(tags) AS num_tags
FROM jdbc_types_lab.events;
~~~

### 37.4. Không khẳng định offset nhập ban đầu được giữ

TIMESTAMPTZ chứa instant. Cách PostgreSQL hiển thị tùy session TimeZone, không cho biết input đã dùng +07 hay một ZoneId cụ thể.

## 38. Lab: Java DTO dùng kiểu đúng

Một DTO có thể sử dụng Java record (Java 16+):

~~~java
import java.math.BigDecimal;
import java.time.*;
import java.util.*;

record EventRow(
    long eventId,
    UUID externalId,
    String ownerName,
    String note,
    boolean active,
    Integer attempts,
    BigDecimal totalAmount,
    Double confidence,
    LocalDate eventDay,
    LocalTime localTime,
    LocalDateTime localDeadline,
    OffsetDateTime occurredAt,
    String payloadJson,
    List<String> tags,
    byte[] data,
    String sourceIp,
    String state
) {}
~~~

### 38.1. Nullable dùng wrapper

`attempts` và `confidence` có thể NULL nên dùng Integer/Double. `active` NOT NULL, vì vậy boolean primitive có thể phù hợp.

### 38.2. JSONB tách parsing

Ví dụ giữ payload dưới dạng String. Một converter riêng có thể dùng Jackson để parse thành DTO. Không giả định pgJDBC tự deserialize.

### 38.3. Enum có converter

Ở bước mapping ban đầu, `state` là String. Business layer có thể chuyển sang Java enum bằng converter explicit, kiểm soát unknown labels khi schema thay đổi.

### 38.4. Record toString có thể làm lộ dữ liệu

Với record chứa JSON/PII/byte[], đừng log nguyên record vào hệ thống quan sát nếu dữ liệu nhạy cảm.

## 39. Lab: ResultSet mapper

~~~java
import java.sql.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;

static EventRow mapEvent(ResultSet rs) throws SQLException {
    long id = rs.getLong("event_id");
    UUID externalId = rs.getObject("external_id", UUID.class);
    String ownerName = rs.getString("owner_name");
    String note = rs.getString("note");
    boolean active = rs.getBoolean("active");

    int n = rs.getInt("attempts");
    Integer attempts = rs.wasNull() ? null : n;

    BigDecimal amount = rs.getBigDecimal("total_amount");

    double c = rs.getDouble("confidence");
    Double confidence = rs.wasNull() ? null : c;

    LocalDate eventDay =
        rs.getObject("event_day", LocalDate.class);
    LocalTime localTime =
        rs.getObject("local_time", LocalTime.class);
    LocalDateTime localDeadline =
        rs.getObject("local_deadline", LocalDateTime.class);
    OffsetDateTime occurredAt =
        rs.getObject("occurred_at", OffsetDateTime.class);

    String payload = rs.getString("payload");

    Array sqlTags = rs.getArray("tags");
    List<String> tags = null;
    if (sqlTags != null) {
        try {
            tags = Arrays.asList((String[]) sqlTags.getArray());
        } finally {
            sqlTags.free();
        }
    }

    byte[] data = rs.getBytes("data");
    String sourceIp = rs.getString("source_ip");
    String state = rs.getString("state");

    return new EventRow(
        id, externalId, ownerName, note, active, attempts,
        amount, confidence, eventDay, localTime,
        localDeadline, occurredAt, payload, tags,
        data, sourceIp, state
    );
}
~~~

### 39.1. wasNull đọc ngay sau primitive getter

Nếu gọi một getter khác trước `rs.wasNull()`, trạng thái NULL đã chuyển sang cột mới. Đây là bug mapping rất phổ biến.

### 39.2. Trả resources đúng lúc

SQL Array được giải phóng sau khi đã lấy Java String[]. Nếu driver/type/shape khác, điều chỉnh converter và dùng integration test.

### 39.3. Mã mapper không chịu trách nhiệm commit

Mapper đọc một row; transaction, pagination và resource lifetime thuộc tầng gọi.

### 39.4. getObject typed cần driver hỗ trợ

Đoạn này giả định pgJDBC hỗ trợ UUID/LocalDate/LocalTime/LocalDateTime/OffsetDateTime typed getters. Nếu driver cũ không hỗ trợ, nâng cấp hoặc có converter được kiểm thử.

## 40. Lab: SELECT sử dụng PreparedStatement

~~~java
import java.sql.*;
import java.time.OffsetDateTime;

static void printEvents(Connection connection)
        throws SQLException {
    String sql = """
        SELECT event_id, external_id, owner_name, note,
               active, attempts, total_amount, confidence,
               event_day, local_time, local_deadline,
               occurred_at, payload, tags, data, source_ip, state
        FROM jdbc_types_lab.events
        WHERE occurred_at >= ?
        ORDER BY occurred_at, event_id
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setObject(
            1,
            OffsetDateTime.parse("2026-11-01T00:00:00Z")
        );

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                EventRow row = mapEvent(rs);
                System.out.println(row.eventId());
            }
        }
    }
}
~~~

### 40.1. Java text blocks

Ký hiệu `"""` dùng Java 15+. Với Java 8/11, viết String theo cú pháp cũ.

### 40.2. Projection rõ

Chỉ lấy những cột thực sự cần; tránh `SELECT *` trong API lâu dài vì schema evolution.

### 40.3. Parameter hóa timestamp

`ps.setObject(OffsetDateTime)` giữ semantic instant tốt hơn nối chuỗi timestamp người dùng vào SQL.

### 40.4. Không log dữ liệu nhạy cảm

Chỉ log metadata/ID phù hợp chính sách, không tự in payload JSON hoặc toàn row có thể chứa thông tin cá nhân.

## 41. Lab: INSERT với nhiều kiểu JDBC

Sử dụng `INSERT ... RETURNING event_id`:

~~~java
import java.sql.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.UUID;

static long insertEvent(
    Connection connection,
    String payloadJson
) throws SQLException {
    String sql = """
        INSERT INTO jdbc_types_lab.events (
            external_id, owner_name, active, attempts,
            total_amount, confidence, event_day, local_time,
            local_deadline, occurred_at, duration, payload,
            tags, data, source_ip, state
        )
        VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?::interval, ?::jsonb,
            ?, ?, ?::inet, ?::jdbc_types_lab.event_state
        )
        RETURNING event_id
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setObject(1, UUID.randomUUID());
        ps.setString(2, "Trần Bình");
        ps.setBoolean(3, true);
        ps.setNull(4, Types.INTEGER);
        ps.setBigDecimal(5, new BigDecimal("75.1250"));
        ps.setDouble(6, 0.875);
        ps.setObject(7, LocalDate.of(2026, 11, 14));
        ps.setObject(8, LocalTime.of(9, 30));
        ps.setObject(
            9, LocalDateTime.of(2026, 11, 14, 9, 30)
        );
        ps.setObject(
            10,
            OffsetDateTime.parse("2026-11-14T09:30:00+07:00")
        );
        ps.setString(11, "2 days 3 hours");
        ps.setString(12, payloadJson);

        Array tags = connection.createArrayOf(
            "text", new String[] {"java", "jdbc", "jsonb"}
        );

        try {
            ps.setArray(13, tags);
            ps.setBytes(
                14,
                new byte[] {(byte) 0xDE, (byte) 0xAD}
            );
            ps.setString(15, "192.0.2.46");
            ps.setString(16, "new");

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "INSERT RETURNING returned no ID"
                    );
                }
                return rs.getLong(1);
            }
        } finally {
            tags.free();
        }
    }
}
~~~

### 41.1. Đếm parameters

Câu SQL có 16 placeholders và PreparedStatement bind từ vị trí 1 tới 16. Nhầm thứ tự parameters dễ gây cast errors hoặc ghi nhầm cột.

### 41.2. Types.INTEGER khi NULL

`ps.setNull(4, Types.INTEGER)` ghi SQL NULL có type, khác `ps.setInt(4,0)`.

### 41.3. Ghi JSONB/interval/network/enum bằng casts

Các tham số text được ép đúng kiểu PostgreSQL tại vị trí cần thiết, không phải nối chuỗi SQL literal từ user input.

### 41.4. SQL Array lifecycle

`createArrayOf` tạo array parameter; `free()` được gọi sau khi statement thực thi.

### 41.5. Caller sở hữu transaction

Helper không tự commit hoặc rollback Connection được truyền vào. Service có thể kết hợp nhiều DML trong một transaction.

## 42. RETURNING và getGeneratedKeys

Một cách quen thuộc với PostgreSQL là:

~~~sql
INSERT INTO orders(customer_id, total)
VALUES (?, ?)
RETURNING order_id;
~~~

Với JDBC, dùng `executeQuery()` và đọc ResultSet. Một lựa chọn khác là `getGeneratedKeys()`:

~~~java
String sql = """
    INSERT INTO orders(customer_id, total)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, new String[] {"order_id"})) {
    ps.setLong(1, customerId);
    ps.setBigDecimal(2, total);
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long id = keys.getLong(1);
        }
    }
}
~~~

### 42.1. Không dùng MAX(id)

Một SELECT MAX(id) sau INSERT không bảo đảm trả ID của chính hàng vừa chèn nếu có các transactions đồng thời.

### 42.2. Generated identity không có Java type riêng

Cột BIGINT IDENTITY vẫn đọc thành long/Long.

### 42.3. Batch inserts cần kiểm tra driver behavior

Cơ chế RETURNING/generated keys với batch, upsert và nhiều rows có thể khác cách API tổng quát xử lý. Dùng integration test cho câu SQL đang triển khai.

## 43. Ghi NULL với đúng kiểu

~~~java
ps.setNull(1, Types.INTEGER);
ps.setNull(2, Types.NUMERIC);
ps.setNull(3, Types.TIMESTAMP_WITH_TIMEZONE);
ps.setNull(4, Types.VARCHAR);
~~~

### 43.1. setObject(index, null) không phải luôn đủ

Nếu PostgreSQL không suy được kiểu của một placeholder NULL trong expression, câu SQL có thể lỗi. Dùng `setNull` với JDBC type hoặc SQL cast rõ.

### 43.2. SQL NULL cho JSONB

~~~sql
UPDATE jdbc_types_lab.events
SET payload = ?::jsonb
WHERE event_id = ?;
~~~

~~~java
ps.setNull(1, Types.OTHER);
ps.setLong(2, eventId);
~~~

### 43.3. JSON literal null

~~~java
ps.setString(1, "null");
~~~

Khi dùng `?::jsonb`, đây là JSON null được lưu trong một giá trị SQL không NULL. Không đánh đồng với setNull.

### 43.4. NULL array khác array rỗng

Một cột có NOT NULL không cho phép SQL NULL, nhưng vẫn có thể cho phép array rỗng. Thông báo lỗi thuộc schema constraint, không phải lỗi JDBC Array.

## 44. SQL casts và typed parameters

~~~sql
SELECT ?::uuid;
SELECT ?::jsonb;
SELECT ?::inet;
SELECT ?::date;
SELECT ?::jdbc_types_lab.event_state;
~~~

### 44.1. Dùng cast cho parameter, không ghép SQL từ user

SQL string concatenation với dữ liệu đầu vào có nguy cơ injection/escaping. Dùng PreparedStatement và SQL cast khi cần.

### 44.2. Không truyền identifier qua placeholder

Tên table, schema hoặc enum type không được bind như value parameter. Nếu có SQL động, hãy dùng whitelist tên hợp lệ và cách quote identifier thích hợp.

### 44.3. Cast trên cột có thể tác động index

Nếu bạn bọc một cột đã được index bằng function/cast không cần thiết trong WHERE, planner có thể không dùng được index cũ. Thường nên bind giá trị đúng kiểu ở phía parameter.

### 44.4. Date/time cast không phải chuyện trình bày

`timestamp` và `timestamptz` có ngữ nghĩa khác khi input có offset hoặc khi session timezone được áp dụng. Chọn kiểu/cast theo domain contract, không theo cách dễ làm SQL chạy.

## 45. Deserialize JSON thành domain object

Một thư viện như Jackson có thể biến chuỗi JSONB được JDBC đọc ra thành domain object hoặc JSON tree. Đây là **bước ứng dụng**, không phải một chức năng tự động của `getObject()`.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

String jsonText = rs.getString("payload");
JsonNode json = jsonText == null
    ? null
    : mapper.readTree(jsonText);
~~~

Cần khai báo Jackson dependency và xử lý checked exception tương ứng.

### 45.1. Ba loại “không có dữ liệu”

- SQL NULL của cột JSONB → Java `null` từ `getString`.
- JSON literal `null` → chuỗi `"null"` khi đọc JSON text.
- JSON object thiếu key → object tồn tại, nhưng không có member đó.

Nếu gộp cả ba thành Java null, business logic có thể mất thông tin.

### 45.2. Validation

PostgreSQL xác minh JSONB có cú pháp JSON hợp lệ; ứng dụng vẫn phải xác minh nghiệp vụ như kiểu field, version, quyền và constraints.

### 45.3. Versioning payload

Có thể có field `schema_version` hoặc event type. Khi producer thêm field, consumer Java cần chính sách unknown-field phù hợp.

### 45.4. Không log raw JSON

Payload có thể chứa PII hoặc tokens; tránh log `JsonNode.toString()` hoặc DTO tự serialize ở môi trường thật.

## 46. Driver version, Java version và protocol

### 46.1. pgJDBC là driver PostgreSQL cụ thể

`PGobject`, `PGInterval` và escaping JSONB operator không phải khả năng chung của mọi JDBC driver.

### 46.2. Java syntax trong ví dụ

`java.time` có từ Java 8; text blocks `"""` có từ Java 15; Java records ổn định từ Java 16; switch expressions thuộc các Java versions mới hơn. Nếu dự án ở Java 8/11, hãy điều chỉnh syntax chứ không đổi semantics của kiểu dữ liệu.

### 46.3. Binary vs text transfer

PostgreSQL protocol/driver có thể truyền kiểu bằng binary/text format tùy cấu hình và loại dữ liệu. Mapper phải giữ cùng ý nghĩa dù transfer mode khác.

### 46.4. Không parse timestamp bằng String khi có typed getter

Format hiển thị có thể chịu TimeZone/session setting, còn typed getter giúp giảm chuyển đổi ngầm.

### 46.5. Nâng cấp driver cần tests

Các conversion đặc thù như enum, array, JSONB, range và thời gian dễ phụ thuộc driver. Pin version và chạy integration tests khi nâng cấp.

## 47. Connection, transaction và fetch size

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT event_id, total_amount, occurred_at "
       + "FROM jdbc_types_lab.events"
     );
     ResultSet rs = ps.executeQuery()) {

    while (rs.next()) {
        long id = rs.getLong("event_id");
        BigDecimal amount = rs.getBigDecimal("total_amount");
        OffsetDateTime occurredAt =
            rs.getObject("occurred_at", OffsetDateTime.class);
    }
}
~~~

### 47.1. try-with-resources

Đóng ResultSet, PreparedStatement và Connection theo vòng đời. Với connection pool, `close()` của Connection thường trả connection về pool thay vì đóng socket vật lý.

### 47.2. Fetch size trên pgJDBC

~~~java
conn.setAutoCommit(false);

try (PreparedStatement ps = conn.prepareStatement(
        "SELECT event_id, payload FROM jdbc_types_lab.events")) {
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý tuần tự, không tải hết vào một List.
        }
    }
}

conn.commit();
~~~

Cursor-based fetching của pgJDBC có các điều kiện như transaction không autocommit và ResultSet phù hợp. Cần đối chiếu driver đang triển khai.

### 47.3. Không giữ transaction mở vô thời hạn

Một query lớn chạy streaming có thể giữ snapshot/tài nguyên của server lâu; cần cân nhắc batching/COPY/pagination.

### 47.4. Fetch size không sửa thiếu index

Nó giúp cách fetch dữ liệu, nhưng không làm phép JOIN/sort trên server tự biến mất.

### 47.5. Resource của SQL Array và stream

Đọc dữ liệu cần thiết và giải phóng Array/stream khi đã xong; không để DTO tham chiếu ResultSet đã đóng.

## 48. Hiệu năng của mapping

### 48.1. BYTEA lớn

`getBytes()` materialize byte array trong heap; nếu dữ liệu lớn, dùng stream và giới hạn size hoặc cân nhắc object storage.

### 48.2. JSONB lớn

Không fetch hàng triệu payload chỉ để Java lọc một field. PostgreSQL JSON operators và indexes có thể lọc trước khi chuyển qua network.

### 48.3. BigDecimal vs double

BigDecimal có overhead nhưng phù hợp tiền. Đừng đổi sang double để “tối ưu” khi có yêu cầu exact decimal.

### 48.4. ARRAY lớn

Mảng đa chiều hoặc nhiều phần tử có thể tạo nhiều Java objects. Khi cần aggregate/filter theo tập, xem SQL server-side.

### 48.5. Chỉ SELECT cột cần thiết

`SELECT *` có thể truyền JSONB/BYTEA không cần thiết, tăng network, GC và serialization costs.

## 49. Bảo mật ở ranh giới JDBC

### 49.1. Không nối user input thành SQL

~~~java
// KHÔNG AN TOÀN:
String sql = "SELECT * FROM events WHERE owner_name = '"
           + userInput + "'";
~~~

Dùng `PreparedStatement` để bind values và kiểm soát kiểu.

### 49.2. Placeholder không dùng cho identifier

Tên schema/table/column/enum type không phải value parameter. Với SQL động, whitelist và quote identifier đúng.

### 49.3. Quyền database vẫn cần bảo vệ

Mapper đúng không thay GRANT/RLS; role JDBC phải có quyền tối thiểu.

### 49.4. Log redaction

Tránh log raw JSON, tokens, binary secrets, connection passwords và nguyên DTO chứa dữ liệu nhạy cảm. Java record `toString()` có thể làm lộ fields.

### 49.5. Giới hạn input và an toàn khi render

PostgreSQL JSONB/BYTEA không tự bảo vệ Java/browser khỏi HTML injection, dữ liệu giả hoặc file độc hại. Validate và encode theo context.

## 50. Schema migrations và kiểu Java

| Thay đổi PostgreSQL | Rủi ro Java |
|---|---|
| `integer → bigint` | Integer không đủ phạm vi; đổi Long |
| `numeric → double precision` | Mất exact-decimal semantics |
| `timestamp → timestamptz` | Thay ý nghĩa thời gian |
| `text → enum` | String parameter cần converter/cast |
| `text → jsonb` | Cần JSON parser và validation |
| `text[] → jsonb` | Thay kiểu dữ liệu, operators và Java model |
| NOT NULL → nullable | Primitive mapper có thể nhầm NULL |
| Thêm enum label | Converter Java cũ có thể lỗi |
| Đổi NUMERIC scale | Rounding/precision đổi |
| Đổi tên cột | Getter theo tên cũ lỗi |
| Thêm cột vào SELECT * | Mapping theo vị trí có thể sai |

### 50.1. Expand–contract

Với breaking change, cân nhắc thêm cột mới, backfill, chuyển ứng dụng và chỉ xóa cột cũ sau khi tất cả consumers đã sẵn sàng.

### 50.2. Đừng dùng String cho mọi field để né migration

Điều đó chỉ đẩy sai số, null/timezone và validation bugs sang runtime.

### 50.3. Rolling deploy

Hai phiên bản app có thể chạy song song. Database migration cần bảo vệ mapping của app cũ trong quá trình cutover.

### 50.4. Contract tests

Nên có fixtures cho BIGINT lớn, NUMERIC scale, SQL NULL, Unicode, DST/time zones, array rỗng và enum mới.

## 51. Bảng chẩn đoán lỗi mapping

| Triệu chứng | Điều cần kiểm tra |
|---|---|
| SQL NULL thành 0/false | Primitive getter và `wasNull()` |
| Tiền sai chữ số | double/rounding/scale |
| BIGINT đọc không được | getInt thay getLong |
| Timestamp sai giờ | Nhầm TIMESTAMP và TIMESTAMPTZ |
| Offset +07 thành +00 | Instant được giữ, offset gốc không |
| getObject Instant.class lỗi | Driver chưa hỗ trợ typed getter |
| JSONB bị type mismatch | Cast/PGobject chưa phù hợp |
| JSON null thành SQL NULL | Converter gộp hai trạng thái |
| Enum không nhận String | Cast sang đúng PostgreSQL enum |
| Array cast ClassCastException | Java element type không khớp |
| ARRAY NULL thành empty | Mapper mất null semantics |
| Interval “1 tháng” bị hiểu là 30 ngày | Nhầm calendar vs Duration |
| BYTEA lỗi Unicode | Ép bytes sang String |
| Enum label mới làm Java lỗi | Converter chưa xử lý unknown values |
| JSONB operator ? lỗi JDBC | Placeholder conflict, escape ?? |
| Memory tăng khi đọc rows | Fetch quá nhiều JSONB/BYTEA |
| SELECT permission denied | Quyền DB, không phải type conversion |
| Driver upgrade gây regression | Driver-specific conversion/metadata |

### 51.1. Phân biệt tầng lỗi

SQLSTATE và server error có thể chỉ rõ cast/constraint; ClassCastException hoặc JSON parser errors thuộc Java conversion.

### 51.2. Không lộ dữ liệu khi debug

Dùng schema metadata và fixtures giả lập; tránh in password, PII hoặc payload chứa token vào logs.

## 52. Bài tập thực hành

### Bài 1 — BIGINT nullable

Kiểu Java nên dùng?

**Đáp án:** Long.

### Bài 2 — wasNull

Sau `getInt()`, vì sao cần gọi `wasNull()` ngay?

**Gợi ý:** 0 có thể biểu diễn SQL NULL; wasNull phản ánh getter gần nhất.

### Bài 3 — BOOLEAN nullable

Vì sao `Boolean` có thể tốt hơn boolean?

**Gợi ý:** Giữ ba trạng thái TRUE/FALSE/NULL.

### Bài 4 — Money

Vì sao dùng BigDecimal thay double?

**Gợi ý:** Exact decimal.

### Bài 5 — BigDecimal constructor

Cách nào an toàn hơn: `new BigDecimal("0.1")` hay `new BigDecimal(0.1)`?

**Đáp án:** Constructor String.

### Bài 6 — equals vs compareTo

Vì sao 1.0 và 1.00 có thể equals=false nhưng compareTo=0?

**Gợi ý:** Scale khác nhau.

### Bài 7 — REAL

Java type cho PostgreSQL real?

**Đáp án:** Float.

### Bài 8 — DOUBLE PRECISION

Java type cho PostgreSQL double precision?

**Đáp án:** Double.

### Bài 9 — DATE

Java type cho ngày sinh PostgreSQL date?

**Đáp án:** LocalDate.

### Bài 10 — TIME

Java type cho time without time zone?

**Đáp án:** LocalTime.

### Bài 11 — TIMESTAMP

Timestamp without time zone có tự xác định một Instant không?

**Đáp án:** Không.

### Bài 12 — TIMESTAMPTZ

Kiểu Java time nào pgJDBC thường hỗ trợ?

**Đáp án:** OffsetDateTime.

### Bài 13 — Instant

Nếu getObject Instant.class không hỗ trợ, làm gì?

**Gợi ý:** Đọc OffsetDateTime rồi toInstant.

### Bài 14 — ZoneId

PostgreSQL timestamptz có lưu tên vùng Asia/Ho_Chi_Minh không?

**Đáp án:** Không.

### Bài 15 — DST

Vì sao LocalDateTime có thể không có hoặc có hai Instants?

**Gợi ý:** DST gap/overlap.

### Bài 16 — Microseconds

Java hỗ trợ nano, PostgreSQL timestamp thường có độ phân giải gì?

**Đáp án:** Microsecond.

### Bài 17 — UUID

Getter nào dùng cho UUID?

**Gợi ý:** getObject("col", UUID.class).

### Bài 18 — JSONB

JDBC có tự chuyển JSONB thành domain DTO không?

**Đáp án:** Không; cần parser.

### Bài 19 — PGobject

PGobject mang những thông tin gì?

**Gợi ý:** PostgreSQL type name và giá trị.

### Bài 20 — JSON null

SQL NULL khác `'null'::jsonb` thế nào?

**Gợi ý:** Null của cột vs JSON literal.

### Bài 21 — JSONB parameter

Vì sao cần `?::jsonb` hoặc PGobject khi ghi?

**Gợi ý:** String parameter có thể được gửi như VARCHAR/text.

### Bài 22 — JSONB question mark

Trong PreparedStatement pgJDBC, dấu hỏi của operator JSONB có thể viết gì?

**Đáp án:** ??.

### Bài 23 — ARRAY getter

Kiểu API JDBC nào dùng để đọc text[]?

**Đáp án:** java.sql.Array qua getArray.

### Bài 24 — ARRAY parameter

Cách tạo text[]?

**Gợi ý:** connection.createArrayOf("text", String[]), setArray.

### Bài 25 — ARRAY rỗng

SQL NULL, ARRAY[] và ARRAY[NULL] có giống nhau không?

**Đáp án:** Không.

### Bài 26 — BYTEA

Java type phổ biến?

**Đáp án:** byte[].

### Bài 27 — Large Object

OID trỏ Large Object có giống cột BYTEA không?

**Đáp án:** Không; cần API phù hợp.

### Bài 28 — INTERVAL

Một tháng lịch có luôn đúng 30 ngày không?

**Đáp án:** Không.

### Bài 29 — ENUM

Java enum NEW và PostgreSQL 'new' cần gì?

**Gợi ý:** Converter.

### Bài 30 — CIDR

InetAddress có tự chứa prefix length không?

**Đáp án:** Không.

### Bài 31 — Range

Cần gì ngoài hai biên để diễn đạt range?

**Gợi ý:** Inclusive/exclusive, empty/unbounded.

### Bài 32 — XML

Java parser XML cần phòng tránh rủi ro nào?

**Gợi ý:** XXE.

### Bài 33 — Metadata SQL type

JDBC method nào trả tên kiểu PostgreSQL?

**Đáp án:** getColumnTypeName.

### Bài 34 — Type code

getColumnType trả PostgreSQL OID hay JDBC Types?

**Đáp án:** JDBC Types.

### Bài 35 — Enum metadata

information_schema có thể báo data_type gì cho enum?

**Gợi ý:** USER-DEFINED với udt_name.

### Bài 36 — Null parameter

Khi setObject(index,null) thiếu type context, làm gì?

**Gợi ý:** setNull(index, Types.X) hoặc explicit cast.

### Bài 37 — RETURNING

Lấy ID sau INSERT an toàn bằng gì?

**Đáp án:** INSERT ... RETURNING hoặc getGeneratedKeys.

### Bài 38 — MAX ID

Vì sao không dùng SELECT MAX(id) để biết row vừa insert?

**Gợi ý:** Concurrency.

### Bài 39 — Unicode

Java String.length và PostgreSQL char_length khác nhau vì sao?

**Gợi ý:** UTF-16 code units và đếm ký tự DB.

### Bài 40 — Empty string

getString trả gì cho SQL NULL và ''?

**Đáp án:** Java null và chuỗi rỗng.

### Bài 41 — Fetch size

Fetch size có luôn làm SQL server chạy nhanh hơn không?

**Đáp án:** Không.

### Bài 42 — Schema migration

Thay INTEGER thành BIGINT ảnh hưởng Java mapper thế nào?

**Gợi ý:** Integer → Long.

### Bài 43 — Nullable boolean

Đổi cột sang nullable nhưng mapper giữ primitive boolean gây gì?

**Gợi ý:** Không phân biệt NULL với FALSE.

### Bài 44 — SQL injection

Vì sao không dùng String concatenation cho SQL user input?

**Gợi ý:** Injection/escaping.

### Bài 45 — Thiết kế hoàn chỉnh

Ứng dụng có amount NUMERIC(18,2), created_at TIMESTAMPTZ, delivery_date DATE, tags TEXT[], payload JSONB, external_id UUID, status ENUM và note TEXT nullable. Hãy chọn kiểu Java, getter/setter, null policy và migration tests.

**Gợi ý:** BigDecimal, OffsetDateTime/Instant, LocalDate, java.sql.Array/List, JSON converter, UUID, enum converter, nullable String; PreparedStatement/cast thích hợp.

## 53. Checklist triển khai

### 53.1. Kiểu và domain

- [ ] BIGINT/INTEGER/NUMERIC đúng Java width và precision?
- [ ] Tiền không đi qua double?
- [ ] NULL khác 0, false, empty string và empty array?
- [ ] DATE/TIME/TIMESTAMP/TIMESTAMPTZ dùng đúng java.time?
- [ ] ZoneId/DST và precision được xử lý có chủ đích?
- [ ] JSONB/ENUM/ARRAY/INTERVAL/INET có converter?
- [ ] Có special values vượt khả năng Java type không?

### 53.2. JDBC API

- [ ] Typed getters có được driver version hỗ trợ?
- [ ] wasNull ngay sau primitive getter?
- [ ] setNull/cast cung cấp đúng kiểu?
- [ ] Parameter thứ tự đúng?
- [ ] Không nối user input thành SQL?
- [ ] ResultSet/Statement/Connection được đóng?
- [ ] Array/SQLXML/streams được giải phóng phù hợp?

### 53.3. Kiểm thử và vận hành

- [ ] Integration tests trên PostgreSQL và pgJDBC thật?
- [ ] Test NULL, empty array, JSON null, Unicode và BigDecimal?
- [ ] Test timezone khác nhau và DST gap/overlap?
- [ ] Test enum labels mới và schema migration?
- [ ] Query chỉ SELECT cột cần thiết?
- [ ] Không log PII/token/secret?
- [ ] Có rollback plan khi đổi type/nullability?

## 54. Bảng tra cứu nhanh

| PostgreSQL | Java/JDBC | Ghi nhớ |
|---|---|---|
| `smallint` | Short | 16-bit signed |
| `integer` | Integer | NULL cần wrapper/wasNull |
| `bigint` | Long | 64-bit signed |
| `numeric` | BigDecimal | Exact decimal |
| `real` | Float | Approximate |
| `double precision` | Double | Approximate |
| `boolean` | Boolean | NULL khác FALSE |
| `text/varchar` | String | Unicode/NULL |
| `date` | LocalDate | Ngày lịch |
| `time` | LocalTime | Giờ trong ngày |
| `timestamp` | LocalDateTime | Local wall-clock |
| `timestamptz` | OffsetDateTime | Instant, không giữ ZoneId |
| `uuid` | UUID | getObject/setObject |
| `jsonb` | String/PGobject/JSON converter | SQL NULL khác JSON null |
| `ARRAY` | java.sql.Array | getArray/createArrayOf/free |
| `bytea` | byte[]/stream | Khác Large Object OID |
| `interval` | PGInterval/domain | Month khác Duration |
| `enum` | String + converter | Cast khi ghi |
| `inet/cidr` | String/PGobject | Prefix semantics |
| Range/multirange | PGobject/domain | Inclusive/exclusive/empty |
| `xml` | SQLXML | free/parser security |
| `Types.OTHER` | JDBC metadata | PostgreSQL-specific |
| `wasNull()` | ResultSet | Sau primitive getter |
| `setNull` | PreparedStatement | SQL NULL có kiểu |
| `RETURNING` | PostgreSQL SQL | Lấy generated ID |
| `setFetchSize` | JDBC | Fetch/memory khi hỗ trợ |

---

## 55. Kết luận

**Ánh xạ dữ liệu PostgreSQL sang Java qua JDBC là bảo toàn ý nghĩa dữ liệu, không chỉ ép kiểu cho code chạy.** NUMERIC và BigDecimal giúp tránh sai số tiền; BIGINT cần Java Long; SQL NULL cần wrapper hoặc `wasNull()`; UUID nên dùng UUID; JSONB cần parser; ARRAY cần JDBC Array; còn INTERVAL, ENUM, INET và range có thể cần converter hoặc PostgreSQL-specific classes.

**Ngày giờ là nhóm dễ gây sai lệch nghiêm trọng:** DATE hợp với LocalDate, TIME với LocalTime, TIMESTAMP WITHOUT TIME ZONE với LocalDateTime và TIMESTAMPTZ với OffsetDateTime (chuyển Instant khi domain chỉ cần thời điểm). Timestamptz không lưu lại ZoneId gốc; DST và độ phân giải microseconds cần được tính tới trong thiết kế.

Hãy dùng PreparedStatement, typed getters/setters, NULL/cast đúng kiểu, kiểm tra metadata khi cần và quản lý JDBC resources bằng try-with-resources. Khi database schema thay đổi, phải thử cả Java mapper, DTO, enum converters, numeric precision, nullable fields và những phiên bản ứng dụng đang rolling deploy. Nguyên tắc quan trọng nhất: **chọn kiểu SQL đúng ngay từ đầu, giữ nguyên semantics qua JDBC và chỉ chuyển sang domain model sau khi kiểm soát rõ NULL, độ chính xác, thời gian và kiểu PostgreSQL-specific**.




