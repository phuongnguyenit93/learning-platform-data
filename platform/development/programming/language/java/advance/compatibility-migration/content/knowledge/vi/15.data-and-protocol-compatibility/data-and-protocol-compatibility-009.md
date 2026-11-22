# Thay đổi JDBC driver và cách ánh xạ kiểu dữ liệu

Khi nâng cấp Java, không phải mọi lỗi cơ sở dữ liệu đều đến từ câu lệnh SQL hay mã nghiệp vụ. Một thay đổi **JDBC driver** có thể ảnh hưởng tới cách ứng dụng kết nối, xác thực, đọc metadata, ánh xạ kiểu dữ liệu SQL sang Java và ghi giá trị Java xuống cơ sở dữ liệu. Cùng một bảng, cùng một câu `SELECT` và cùng một phiên bản JDK, nhưng hai phiên bản driver có thể khác nhau về đối tượng mà `ResultSet.getObject()` trả về, cách làm tròn số, xử lý múi giờ hoặc quy tắc chuyển đổi giá trị không hợp lệ.

Trong **Java Advance Compatibility Migration**, việc cập nhật JDK thường kéo theo cập nhật JDBC driver do yêu cầu class-file version, TLS, hỗ trợ `java.time` hoặc tương thích với database server mới. Điều nguy hiểm là chỉ thấy ứng dụng khởi động và chạy được vài truy vấn rồi kết luận quá trình migration đã hoàn thành. Những lỗi khó phát hiện nhất thường nằm trong **ngữ nghĩa dữ liệu**: sai một ngày do timezone, mất phần thập phân của tiền, đổi cách biểu diễn `NULL`, cắt chuỗi Unicode hoặc một giá trị JSON/UUID bị trả về với kiểu Java khác trước.

Bài học này giải thích các tầng tương thích liên quan đến JDBC, những kiểu SQL cần kiểm tra, cách triển khai mapper theo hợp đồng rõ ràng và cách thiết kế bằng chứng kiểm thử khi đổi driver hoặc JDK.

## 1. JDBC là lớp trừu tượng, driver là implementation

JDBC cung cấp API Java tiêu chuẩn để ứng dụng kết nối và thực thi thao tác với cơ sở dữ liệu quan hệ. Những interface thường gặp thuộc các package `java.sql` và `javax.sql`:

- `Connection`: kết nối logic tới database và quản lý transaction.
- `Statement` và `PreparedStatement`: thực thi SQL; PreparedStatement hỗ trợ bind tham số.
- `ResultSet`: đọc các hàng kết quả.
- `ResultSetMetaData` và `DatabaseMetaData`: xem kiểu cột, đặc tính driver/database.
- `DataSource`: cung cấp connection, thường được pool hoặc framework quản lý.
- `SQLType`, `JDBCType`, `Types`: biểu diễn mã kiểu SQL tiêu chuẩn.

**JDBC driver** triển khai hoặc cung cấp các thành phần cần thiết để các interface này giao tiếp với giao thức, server và kiểu dữ liệu của một hệ quản trị cơ sở dữ liệu cụ thể.

Sơ đồ khái quát:

~~~text
Java application / repository / ORM
              |
         JDBC API
              |
     DataSource / Connection pool
              |
         JDBC driver
              |
 Database wire protocol + TLS + auth
              |
       Database server
              |
          SQL schema
~~~

Đổi driver có thể ảnh hưởng tới các tầng phía trên ngay cả khi source code không đổi. Driver có quyền quyết định nhiều phép chuyển đổi và cách xử lý extension của vendor; JDBC chuẩn hóa một phần hợp đồng nhưng không làm mọi database hay mọi driver trở nên giống nhau.

## 2. Phân biệt phiên bản JDK, driver và database server

Một lần migration có ít nhất ba trục phiên bản cần kiểm soát riêng:

| Trục | Câu hỏi chính | Ví dụ rủi ro |
|---|---|---|
| JDK / JVM | Driver có được biên dịch cho release mà runtime hỗ trợ không? | `UnsupportedClassVersionError` |
| JDBC driver | Driver có hỗ trợ JDBC API, authentication, TLS, mapping và database protocol đang dùng không? | `SQLFeatureNotSupportedException`, mapping khác |
| Database server | Driver có hỗ trợ phiên bản server, data type và dialect tương ứng không? | Handshake thất bại, metadata khác, SQL khác |

Nếu ứng dụng chuyển từ JDK 11 sang JDK 21 đồng thời nâng driver và server, khi xuất hiện lỗi `Timestamp` sẽ khó biết tầng nào gây ra nếu không có baseline riêng cho từng trục.

Cách làm tốt hơn là ghi:

~~~yaml
environment:
  java:
    feature: 21
    distribution: "record actual JDK vendor and build"
  jdbcDriver:
    artifact: "vendor JDBC driver artifact"
    version: "record resolved version"
  database:
    product: "record database product"
    version: "record server version"
  deployment:
    os: "record OS and architecture"
    timezone: "UTC"
~~~

Đây là mẫu ghi thông tin, không phải cấu hình bắt buộc của JDBC. Không nên suy từ tên JAR rằng runtime thực sự đang tải đúng bản driver mong muốn.

## 3. Vì sao đổi driver có thể thay đổi mapping dù API Java không đổi?

JDBC định nghĩa nhiều getter và setter như `getString`, `getInt`, `getBigDecimal`, `getTimestamp` và `getObject`. Tuy nhiên, đường đi từ kiểu dữ liệu lưu trữ của database tới đối tượng Java có thể phụ thuộc:

1. Loại cột SQL và metadata do server trả về.
2. Phiên bản server và protocol.
3. Driver/version và khả năng hỗ trợ JDBC.
4. Phương thức getter mà ứng dụng chọn.
5. Giá trị `NULL` và converter của framework.
6. Múi giờ, locale, encoding và các session settings.
7. Thư viện ORM, dialect và custom `AttributeConverter`.
8. Cấu hình driver có tác động đến conversion; tên và ý nghĩa tùy vendor.

Ví dụ:

~~~java
Object value = resultSet.getObject("created_at");
~~~

Ứng dụng không nên mặc định `value` luôn là `java.sql.Timestamp` cho mọi kiểu cột thời gian, mọi database và mọi driver. Nếu mã cast thẳng:

~~~java
Timestamp timestamp = (Timestamp) resultSet.getObject("created_at");
~~~

một thay đổi mapping có thể dẫn đến `ClassCastException`, hoặc giá trị vẫn có cùng class nhưng ngữ nghĩa timezone khác.

Khi xây API dữ liệu lâu dài, nên chọn getter theo **hợp đồng kiểu dữ liệu mong muốn** và xử lý rõ những conversion có thể khác nhau, thay vì suy luận từ class cụ thể của một driver hiện tại.

## 4. Những thay đổi JDBC cần kiểm kê trước khi nâng driver

Nên bắt đầu từ những điểm giao tiếp thực tế:

| Thành phần | Cần kiểm tra |
|---|---|
| Driver dependency | Artifact, version, JDBC support, Java minimum version |
| Driver loading | `DriverManager`, service discovery, classpath/module path |
| DataSource/pool | Driver class, connection URL, credential, timeout, validation |
| Authentication/TLS | Cấu hình TLS, truststore, hostname validation, database auth plugin |
| Numeric mapping | DECIMAL/NUMERIC, INTEGER/BIGINT, unsigned type, scale và rounding |
| Temporal mapping | DATE, TIME, TIMESTAMP, timezone, DST, precision |
| Nullable columns | `NULL` so với giá trị 0/false/empty |
| Text/binary | Unicode, charset, collation, BLOB/CLOB/stream |
| Vendor types | UUID, JSON, ARRAY, XML, enum, geometry |
| SQL metadata | Column label/name, alias, generated keys, type name |
| Transactions | Autocommit, isolation, savepoint, batch, commit/rollback |
| ORM mapping | Dialect, converters, custom types, schema validation |
| Runtime | Class file, modules, resource lifecycle, driver behavior in container |

Một bản đổi driver chỉ an toàn trong phạm vi mà ứng dụng sử dụng đã được kiểm tra. “Driver hỗ trợ JDK 21” không chứng minh mọi mapping và transaction của ứng dụng vẫn giữ nguyên.

## 5. Bảng kiểu SQL và kiểu Java thường dùng

Bảng dưới đây là **định hướng mapping**, không phải đảm bảo mọi vendor trả đúng class này qua `getObject()`. Với cột đặc thù database, cần tham khảo tài liệu driver/version cụ thể.

| SQL type | Kiểu Java thường được chọn | Lưu ý |
|---|---|---|
| `SMALLINT`, `INTEGER` | `short`, `int` hoặc wrapper | Kiểm tra giới hạn giá trị và `NULL` |
| `BIGINT` | `long` / `Long` | Không gán bừa sang `int` |
| `DECIMAL`, `NUMERIC` | `BigDecimal` | Quan trọng với tiền và số chính xác |
| `REAL`, `FLOAT`, `DOUBLE` | `float` / `double` | Số gần đúng, có sai số nhị phân |
| `BOOLEAN` / `BIT` | `boolean` / `Boolean` | Hành vi tùy dialect, nhất là BIT nhiều bit |
| `CHAR`, `VARCHAR`, `LONGVARCHAR` | `String` | Charset, trailing space, collation |
| `BINARY`, `VARBINARY` | `byte[]` | Copy dữ liệu, giới hạn kích thước |
| `BLOB` | `Blob` hoặc stream/bytes | Quản lý lifetime, memory |
| `CLOB`, `NCLOB` | `Clob` / `NClob` hoặc stream/string | Unicode và đọc dữ liệu lớn |
| `DATE` | `LocalDate` hoặc `java.sql.Date` | Không có time-of-day |
| `TIME` | `LocalTime` hoặc `java.sql.Time` | Không tự có timezone |
| `TIMESTAMP` không timezone | `LocalDateTime` hoặc `Timestamp` | Không tự biểu diễn một instant toàn cầu |
| `TIMESTAMP_WITH_TIMEZONE` | `OffsetDateTime` khi driver hỗ trợ | Vendor khác nhau về semantics/lưu offset |
| `SQLXML` | `SQLXML` | Vòng đời, encoding, kiểm soát XML input |
| `ARRAY` | `java.sql.Array` | Element type và vendor support |
| Vendor JSON/UUID/enum | `String`, `UUID` hoặc vendor object | Không áp một mapping cho mọi database |

Mã kiểu `Types.TIMESTAMP_WITH_TIMEZONE` và API `java.time` có thể được sử dụng theo hợp đồng JDBC 4.2 khi driver hỗ trợ, nhưng không được coi mọi driver cũ đều triển khai đồng nhất.

## 6. `getObject()` và typed `getObject(..., Class)`

Có hai cách đọc phổ biến:

~~~java
Object raw = resultSet.getObject("issue_date");

LocalDate date =
        resultSet.getObject("issue_date", LocalDate.class);
~~~

Dạng đầu trả về đối tượng do driver lựa chọn theo mapping mặc định. Dạng sau yêu cầu driver chuyển sang kiểu Java chỉ định nếu chuyển đổi được hỗ trợ. Trong trường hợp không hỗ trợ, driver có thể báo `SQLException` hoặc `SQLFeatureNotSupportedException`.

Không nên viết:

~~~java
LocalDate issueDate =
        (LocalDate) resultSet.getObject("issue_date");
~~~

chỉ vì một phiên bản driver từng trả về `LocalDate`. Một phiên bản khác có thể trả `java.sql.Date` cho cùng cột.

Ví dụ truy cập rõ kiểu:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class InvoiceMapper {
    public static InvoiceRow read(ResultSet rs) throws SQLException {
        long id = rs.getLong("invoice_id");
        BigDecimal amount = rs.getBigDecimal("amount");
        LocalDate issuedOn =
                rs.getObject("issue_date", LocalDate.class);

        return new InvoiceRow(id, amount, issuedOn);
    }
}
~~~

`InvoiceRow` là kiểu domain do ứng dụng định nghĩa. Ví dụ giả định cột `invoice_id` không nullable, và driver hỗ trợ đọc `DATE` thành `LocalDate`.

Nếu driver không hỗ trợ typed `getObject`, nên đặt conversion trong một adapter có kiểm thử, chẳng hạn dùng `getDate` và `toLocalDate` cho `DATE`:

~~~java
java.sql.Date sqlDate = rs.getDate("issue_date");

LocalDate issuedOn = sqlDate == null
        ? null
        : sqlDate.toLocalDate();
~~~

Ngay cả cách fallback này cũng cần được kiểm tra ở boundary timezone/driver khi server sử dụng kiểu thời gian có semantics đặc thù. Không biến fallback của một vendor thành quy tắc chung nếu chưa có test.

## 7. `NULL`: phân biệt thiếu dữ liệu với giá trị mặc định

Một lỗi dữ liệu nguy hiểm xảy ra khi đọc cột nullable bằng getter primitive.

Ví dụ:

~~~java
int discountPercent = rs.getInt("discount_percent");
~~~

Nếu cột có giá trị SQL `NULL`, getter primitive thường trả `0`. Muốn biết giá trị có thực sự bằng 0 hay là `NULL`, cần kiểm tra `wasNull()` **ngay sau getter vừa gọi**:

~~~java
int raw = rs.getInt("discount_percent");
Integer discountPercent = rs.wasNull() ? null : raw;
~~~

Không nên gọi getter khác trước `wasNull()`, vì `wasNull()` phản ánh phép đọc gần nhất tương ứng.

Đối với kiểu reference:

~~~java
BigDecimal total = rs.getBigDecimal("total_amount");
String note = rs.getString("note");
~~~

SQL `NULL` thông thường được biểu diễn bằng Java `null`. Khi nâng driver, cần kiểm tra:

- Cột nullable và NOT NULL được mapper xử lý đúng.
- `NULL` không bị biến thành `0`, `false`, chuỗi rỗng hoặc epoch time.
- Logic ORM converter giữ lại ngữ nghĩa null.
- Khi ghi tham số nullable, JDBC type được chỉ định rõ nếu driver cần biết kiểu.

Ví dụ bind null có kiểu:

~~~java
if (note == null) {
    ps.setNull(2, java.sql.Types.VARCHAR);
} else {
    ps.setString(2, note);
}
~~~

`setObject(index, null)` có thể không đủ rõ với những driver/type cụ thể. Khi biết kiểu cột, `setNull(index, Types.XXX)` hoặc `setObject` với target SQL type thường ít phụ thuộc suy luận hơn.

## 8. DECIMAL, NUMERIC và rủi ro mất độ chính xác

Tiền tệ, số dư, thuế, tỷ lệ tài chính và giá trị cần độ chính xác tuyệt đối nên được xử lý bằng các kiểu phù hợp, thường là SQL `DECIMAL(p, s)` hoặc `NUMERIC(p, s)` và Java `BigDecimal`.

Ví dụ bảng:

~~~sql
CREATE TABLE invoice (
    invoice_id BIGINT PRIMARY KEY,
    total_amount DECIMAL(18, 4) NOT NULL
);
~~~

Đọc:

~~~java
BigDecimal totalAmount = rs.getBigDecimal("total_amount");
~~~

Không nên đọc bằng `double` rồi khởi tạo `new BigDecimal(double)` nếu cần giữ nguyên giá trị decimal gốc: số dấu phẩy động nhị phân không biểu diễn chính xác nhiều số thập phân như `0.1`.

Bind giá trị:

~~~java
BigDecimal amount = new BigDecimal("12345.6700");
ps.setBigDecimal(1, amount);
~~~

Những điểm cần kiểm tra khi đổi driver:

1. **Precision:** tối đa bao nhiêu chữ số được lưu và đọc?
2. **Scale:** số chữ số sau dấu thập phân có được giữ không?
3. **Rounding:** phép ghi vượt scale có bị làm tròn, cắt, lỗi hoặc bị database xử lý theo chế độ cụ thể?
4. **Overflow:** vượt precision tạo lỗi hay có conversion?
5. **Equality:** `BigDecimal.equals()` xét cả scale, còn `compareTo()` so sánh giá trị số; chọn quy tắc test phù hợp hợp đồng.
6. **Metadata:** `getPrecision()` và `getScale()` có đúng kỳ vọng khi dùng view, expression hay aggregate không?
7. **Nullability:** giá trị `NULL` không được đánh đồng với 0.

Không mặc định rằng driver mới “làm tròn tốt hơn” là compatible với dữ liệu đã lưu. Sự khác biệt một đơn vị ở chữ số cuối có thể ảnh hưởng tổng tiền và reconciliation.

## 9. INTEGER, BIGINT, unsigned và giới hạn giá trị

Một cột SQL có thể dùng `INTEGER` hoặc `BIGINT`, nhưng khoảng biểu diễn và chính sách unsigned tùy database.

Ví dụ:

~~~java
long customerId = rs.getLong("customer_id");
~~~

Nếu database dùng kiểu unsigned có khả năng vượt quá `Long.MAX_VALUE`, không được mặc định `long` biểu diễn được toàn bộ miền. Một driver có thể cung cấp conversion khác, hoặc báo lỗi khi giá trị quá lớn.

Một số bài test nên có:

- Giá trị 0, 1 và -1 nếu domain cho phép.
- Ranh giới `Integer.MAX_VALUE` / `Integer.MIN_VALUE`.
- Giá trị ở gần giới hạn `Long.MAX_VALUE`.
- Giá trị ngoài miền biểu diễn của kiểu Java mà mapper đang dùng.
- `NULL` với cột nullable.
- Server-side generated key có giá trị lớn.

Hãy dùng kiểu Java dựa trên **hợp đồng dữ liệu/domain**, không chỉ kiểu mà driver cũ trả trong happy path.

## 10. DATE, TIME và TIMESTAMP: không trộn ngày giờ với instant

Thời gian là một trong những vùng rủi ro cao nhất khi nâng JDBC driver. Cần phân biệt:

| Kiểu | Ý nghĩa Java phù hợp trong nhiều trường hợp | Điều cần lưu ý |
|---|---|---|
| SQL `DATE` | `LocalDate` | Ngày lịch, không tự có giờ hay timezone |
| SQL `TIME` | `LocalTime` | Giờ trong ngày, không tự biểu diễn một instant |
| SQL `TIMESTAMP` không timezone | `LocalDateTime` | Ngày và giờ địa phương, thiếu timezone/offset |
| SQL `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` nếu driver/dialect hỗ trợ | Semantics và cách lưu offset tùy database |
| Sự kiện tại thời điểm tuyệt đối | `Instant` ở domain layer | Cần mapping có quy ước rõ giữa Instant và kiểu SQL |

Các hệ quản trị khác nhau về tên kiểu, precision, cách lưu và cách convert giá trị temporal. Một cột tên `timestamp` không tự đảm bảo ngữ nghĩa giống nhau trên mọi database.

### 10.1. Đọc DATE bằng java.time khi hỗ trợ

~~~java
LocalDate billingDate =
        rs.getObject("billing_date", LocalDate.class);
~~~

### 10.2. Đọc TIMESTAMP không timezone

~~~java
LocalDateTime scheduledAt =
        rs.getObject("scheduled_at", LocalDateTime.class);
~~~

Nếu dữ liệu thực chất là lịch hẹn ở địa phương, `LocalDateTime` có thể là model hợp lý, kèm zone của lịch hẹn được quản lý riêng nếu cần xác định instant.

Nếu đó là thời điểm sự kiện toàn cầu, không thể tự suy ra một `Instant` chính xác từ `LocalDateTime` mà không có quy ước timezone.

### 10.3. TIMESTAMP WITH TIME ZONE không đồng nghĩa lưu nguyên timezone region

Một số database chuẩn hóa thời điểm hoặc giữ offset; một số trả về offset theo session/server setting. **Offset** như `+07:00` và timezone region như `Asia/Ho_Chi_Minh` không giống nhau. Region mang theo quy tắc DST/lịch sử, trong khi offset là sai khác cố định với UTC ở một thời điểm.

Ví dụ đọc nếu driver hỗ trợ:

~~~java
OffsetDateTime eventTime =
        rs.getObject("event_time", OffsetDateTime.class);
~~~

Từ `OffsetDateTime` có thể chuyển sang `Instant` bằng `toInstant()`, nhưng phải xác minh giá trị offset và semantics của database. Đừng giả định driver sẽ luôn trả đúng offset đã được đưa vào lúc insert.

### 10.4. Bài test thời gian phải có boundary

Bộ test nên chứa:

- Gần nửa đêm UTC và theo timezone nghiệp vụ.
- Một ngày cuối tháng, năm nhuận và năm đổi lịch nếu liên quan.
- Giá trị có phần giây với microsecond/nanosecond và precision khác nhau.
- Khoảng thời gian chuyển DST của timezone có DST.
- Giá trị có offset âm và dương.
- `NULL` và min/max date được database hỗ trợ.
- Việc chuyển JVM default timezone hoặc database session timezone.

Nếu chỉ test giá trị giữa trưa và cùng một timezone, sự thay đổi conversion có thể bị che khuất.

## 11. Legacy `java.sql.Date`, `Time` và `Timestamp`

Nhiều ứng dụng cũ dùng:

~~~java
java.sql.Date date = rs.getDate("billing_date");
java.sql.Time time = rs.getTime("scheduled_time");
java.sql.Timestamp timestamp = rs.getTimestamp("created_at");
~~~

Các lớp này vẫn tồn tại trong API JDBC, nhưng không phải lúc nào cũng là representation domain tốt nhất. Trong Java hiện đại, nên cân nhắc `java.time` để tách ngày lịch, giờ địa phương, offset và instant.

Dù vậy, không nên thay cơ học:

~~~java
Instant instant = rs.getTimestamp("created_at").toInstant();
~~~

nếu cột không mang ngữ nghĩa instant rõ ràng. Kết quả có thể phụ thuộc timezone mà driver/JVM sử dụng để giải thích một timestamp không timezone.

Một số API JDBC có overload nhận `Calendar`, ví dụ `getTimestamp(column, calendar)`. Chúng có thể hữu ích cho các driver và schema nhất định, nhưng **không phải phép sửa chung cho mọi vấn đề timezone**. Cần định nghĩa rõ cột lưu gì và test theo database/driver cụ thể.

Đối với code cũ phụ thuộc `Timestamp.equals()`, `toString()` hoặc `getTime()`, cần quan sát sự khác biệt precision và conversion trước khi đổi sang `Instant` hay `LocalDateTime`.

## 12. Bind tham số temporal một cách có chủ đích

JDBC 4.2 bổ sung khả năng làm việc với nhiều kiểu `java.time`, nhưng mức hỗ trợ trong driver thực tế cần được kiểm chứng.

Ví dụ:

~~~java
LocalDate invoiceDate = LocalDate.of(2026, 11, 12);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO invoice (invoice_id, issue_date) VALUES (?, ?)")) {
    ps.setLong(1, 42L);
    ps.setObject(2, invoiceDate, java.sql.JDBCType.DATE);
    ps.executeUpdate();
}
~~~

Có driver yêu cầu dạng `setDate` truyền thống hoặc conversion riêng. Nếu typed `setObject` không được hỗ trợ trên driver đang dùng, adapter có thể dùng:

~~~java
ps.setDate(2, java.sql.Date.valueOf(invoiceDate));
~~~

Dù vậy, cần xác minh mapping thực tế trên cột SQL `DATE`. Không nên chuyển một `LocalDateTime` sang `Timestamp` mà không kiểm soát timezone, precision và semantics dữ liệu.

Khi đã biết target SQL type, có thể truyền rõ để giảm suy luận tự động. Nhưng tên type chuẩn không bảo đảm mọi database triển khai giống nhau.

## 13. BOOLEAN, BIT và chuỗi biểu diễn trạng thái

Các hệ quản trị dữ liệu có thể cung cấp `BOOLEAN`, `BIT` hoặc kiểu số nhỏ dùng làm cờ. Mỗi kiểu có đặc tính riêng, và một số dialect có thể biểu diễn giá trị `true/false` khác nhau.

Ví dụ:

~~~java
boolean active = rs.getBoolean("is_active");
boolean wasNull = rs.wasNull();
~~~

Nếu cột nullable, `false` có thể là giá trị thật hoặc chỉ là kết quả primitive cho SQL `NULL`. Khi cần ba trạng thái:

~~~java
Boolean activeValue = wasNull ? null : active;
~~~

Cần tránh nhầm `BIT(1)` với bit-string nhiều bit ở những database phân biệt hai khái niệm. Driver có thể trả byte[], Boolean hoặc kiểu vendor tùy SQL type và getter được chọn.

Bài test phải gồm true, false, null và representation đặc biệt mà schema/dialect đang dùng.

## 14. Chuỗi, Unicode, encoding và collation

Một JDBC driver không chỉ chuyển byte thành ký tự. Database còn có charset/collation, normal form, trailing spaces và kiểu độ dài theo ký tự hoặc byte.

Ví dụ một ứng dụng đọc:

~~~java
String displayName = rs.getString("display_name");
~~~

Khi đổi driver hoặc server, cần kiểm tra:

- Tiếng Việt có dấu và chữ ngoài ASCII.
- Emoji và ký tự Unicode ngoài Basic Multilingual Plane.
- Chuỗi rỗng so với SQL `NULL` theo semantics database.
- `CHAR` có padding/trailing spaces như thế nào.
- Chiều dài cột tính theo byte hay character.
- Encoding ở connection và database.
- Collation ảnh hưởng sắp xếp, so sánh không phân biệt hoa thường và dấu.
- Cách driver trả dữ liệu `NCHAR` / `NVARCHAR` nếu database hỗ trợ.

Một ứng dụng vẫn khởi động và trả đúng dữ liệu ASCII chưa chứng minh mapping Unicode tương thích.

Không nên tự trim hoặc normalize chuỗi sau khi nâng driver để che mất một khác biệt đã xảy ra. Nếu hợp đồng nghiệp vụ cần normalization, hãy định nghĩa và kiểm thử một cách minh bạch.

## 15. BLOB, CLOB và dữ liệu lớn

Với dữ liệu nhị phân hoặc văn bản lớn, driver có thể hỗ trợ:

- `getBytes` / `setBytes` cho dữ liệu nhỏ.
- `getBinaryStream` / `setBinaryStream` cho stream.
- `getBlob` / `getClob` / `getNClob`.
- `getCharacterStream` / `setCharacterStream`.

Một điểm cần chú ý là lifetime của stream/LOB có thể phụ thuộc `ResultSet`, `Statement` và `Connection`. Nếu trả một stream ra ngoài sau khi đóng connection, một số driver có thể thất bại hoặc âm thầm buffer toàn bộ dữ liệu.

Ví dụ đọc bytes khi kích thước có giới hạn chấp nhận được:

~~~java
byte[] payload = rs.getBytes("payload");
~~~

Với file lớn, ưu tiên thiết kế streaming và đóng resource đúng lúc. Cần test:

- File rỗng và file lớn.
- Binary chứa mọi giá trị byte, không qua conversion chuỗi.
- Dữ liệu nhiều MB/GB theo nhu cầu thực tế.
- Nhiều client đồng thời.
- Behavior khi ngắt connection và retry.
- Cách memory usage thay đổi giữa driver cũ và mới.

Không nên quy mọi khác biệt performance cho JDK nếu driver đổi chiến lược fetch/buffering.

## 16. UUID, JSON, ARRAY, SQLXML và kiểu đặc thù vendor

Các kiểu này thường có hỗ trợ khác nhau giữa hệ quản trị và phiên bản driver.

### 16.1. UUID

Một số database có kiểu `UUID` native; database khác lưu UUID dưới `CHAR(36)` hoặc binary. `getObject` có thể trả `UUID`, `String` hoặc kiểu khác tùy driver/type.

Nếu schema lưu chuỗi chuẩn, có thể chuyển có kiểm soát:

~~~java
String rawUuid = rs.getString("external_id");

UUID externalId = rawUuid == null
        ? null
        : UUID.fromString(rawUuid);
~~~

Đây không phải công thức cho mọi schema UUID. Nếu cột là native/binary type, cần dùng mapping tương ứng đã được driver/database hỗ trợ.

### 16.2. JSON

JSON có thể được lưu dưới kiểu native JSON/JSONB, chuỗi hoặc binary riêng của vendor. Đừng mặc định:

~~~java
String json = (String) rs.getObject("metadata");
~~~

luôn hợp lệ. Driver có thể trả object vendor-specific. Nên xây adapter theo driver/version hoặc dùng getter/cơ chế được tài liệu hóa, sau đó deserialize JSON bằng thư viện được quản lý của ứng dụng và validate schema.

Một lỗi rất dễ bị bỏ qua là driver trả cùng nội dung JSON nhưng thay đổi biểu diễn số, thứ tự key, duplicate key hoặc kiểu null. Kiểm tra theo **hợp đồng dữ liệu**, không chỉ so sánh string nếu thứ tự key không được cam kết.

### 16.3. ARRAY

Khi database hỗ trợ SQL array:

~~~java
java.sql.Array array = rs.getArray("tags");

if (array != null) {
    try {
        Object values = array.getArray();
        // Convert according to element type and driver contract.
    } finally {
        array.free();
    }
}
~~~

Element type và kiểu object/array trả về có thể khác nhau. Không giả định mọi array là `String[]`. Cần kiểm tra null element, empty array và multidimensional array nếu hệ thống sử dụng.

### 16.4. SQLXML

`SQLXML` có lifecycle riêng và có thể được trả qua `getSQLXML`. Với dữ liệu XML từ nguồn không tin cậy, xử lý parser/transformer phải theo chính sách bảo mật XML của ứng dụng. Không giảm cấu hình bảo vệ XML để khôi phục compatibility.

## 17. Đừng tin tuyệt đối `ResultSetMetaData` từ một driver duy nhất

Một mapper động có thể suy luận kiểu qua metadata:

~~~java
ResultSetMetaData md = rs.getMetaData();

for (int i = 1; i <= md.getColumnCount(); i++) {
    System.out.println(md.getColumnLabel(i));
    System.out.println(md.getColumnType(i));
    System.out.println(md.getColumnTypeName(i));
    System.out.println(md.getPrecision(i));
    System.out.println(md.getScale(i));
}
~~~

Khi đổi driver, các giá trị này có thể khác do:

- Driver sửa lỗi báo loại SQL.
- Database thay cách mô tả expression/aggregate/view.
- `getColumnLabel` phản ánh alias còn `getColumnName` phản ánh tên nguồn theo cách driver/database cung cấp.
- `getColumnClassName` mô tả class Java dự kiến của getter mặc định trong điều kiện nhất định.
- Precision/scale của một biểu thức tính toán hoặc kiểu vendor có thể được báo khác.

Nếu một generic mapper dùng metadata để chọn Java class, phải test kỹ cả SQL alias, case sensitivity, join và computed columns. Không nên dùng metadata như một lời hứa bất biến ngoài phạm vi JDBC và vendor.

Ví dụ:

~~~sql
SELECT total_amount AS total FROM invoice
~~~

Trong mapper, thường nên truy xuất theo column label `total` đã công bố. Việc truy cập theo tên vật lý `total_amount` ở một số bối cảnh có thể phụ thuộc driver.

## 18. Driver loading, classpath và module path

Từ JDBC 4.0, driver có thể được tìm và đăng ký tự động qua cơ chế service-provider phù hợp. Nhiều ứng dụng hiện đại không cần:

~~~java
Class.forName("com.vendor.jdbc.Driver");
~~~

chỉ để đăng ký driver, miễn artifact driver đúng có mặt trên classpath/module path và được service discovery nhìn thấy. Tuy nhiên, code cũ có thể dùng tên driver class trực tiếp và tên đó có thể thay đổi qua thế hệ driver hoặc khi chọn vendor khác.

Ví dụ dùng API chuẩn:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;

Connection connection = DriverManager.getConnection(
        "jdbc:example://database-host:5432/app",
        "app_user",
        "credential-from-secure-source");
~~~

URL ở đây là placeholder; trong ứng dụng thực tế, format URL và property tùy driver. Không hardcode credential trong source. Ví dụ trên không mô tả cấu hình an toàn cho production.

Các điểm cần kiểm tra:

- Driver JAR thực sự được resolve ở runtime.
- Version driver có phù hợp với JVM class-file baseline.
- Service discovery có hoạt động sau khi tạo fat/shaded JAR hay không.
- Driver có module descriptor hoặc automatic module name nào khi chuyển lên module path.
- Framework/app server có nạp thêm driver trong class loader khác không.
- Có hai phiên bản driver cùng tồn tại gây chọn nhầm không.
- Driver registration/deregistration và thread/context class loader trong môi trường container.

Không nên tự thêm một module `requires java.sql` vào mọi dự án nếu chúng chưa modularized; cần phân biệt classpath app với named module app.

## 19. DataSource, connection pool và quyền sở hữu connection

Trong ứng dụng thực tế, `DataSource` được ưu tiên cho quản lý kết nối, đặc biệt khi có pooling và transaction framework.

Ví dụ mô hình:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;

public final class ConnectionCheck {
    private final DataSource dataSource;

    public ConnectionCheck(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean canConnect() throws Exception {
        try (Connection conn = dataSource.getConnection()) {
            return conn.isValid(3);
        }
    }
}
~~~

`DataSource` có thể được thư viện pool bọc quanh một driver-specific DataSource. Khi đổi driver, cần kiểm tra:

- Driver class và URL/property cấu hình có còn đúng không.
- Validation query hoặc `Connection.isValid` có hoạt động không.
- Connection timeout, socket timeout, login timeout khác nhau thế nào.
- Có reset `autoCommit`, transaction isolation, read-only, catalog/schema khi trả về pool không.
- Session timezone, search path và encoding có bị giữ lại giữa các lần dùng connection không.
- Prepared statement cache, server-side prepare và fetch size có hành vi khác không.
- Connection bị lỗi có được loại khỏi pool và tạo lại phù hợp không.
- Leak detection và giới hạn kích thước pool có phù hợp tải thực tế không.

Một driver mới có thể xử lý network timeout khác driver cũ. Cần kiểm tra trong môi trường database/proxy tương ứng, không chỉ tạo một connection thành công.

## 20. Transaction, autocommit và isolation

Một thay đổi driver hoặc pool có thể ảnh hưởng ngữ nghĩa transaction, ngay cả khi mapping cột đúng.

Ví dụ pattern JDBC:

~~~java
Connection conn = dataSource.getConnection();

try {
    conn.setAutoCommit(false);

    try (PreparedStatement ps = conn.prepareStatement(
            "UPDATE account SET balance = ? WHERE account_id = ?")) {
        ps.setBigDecimal(1, new BigDecimal("120.50"));
        ps.setLong(2, 42L);
        ps.executeUpdate();
    }

    conn.commit();
} catch (SQLException failure) {
    try {
        conn.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
} finally {
    conn.close();
}
~~~

Đây là mẫu minh họa; trong một hệ thống có transaction manager/connection pool, code cần để framework quản lý connection và trạng thái theo hợp đồng của framework, tránh tự phá transaction hiện có.

Các nội dung cần test khi nâng driver:

- `autoCommit` và cách connection pool reset trạng thái.
- Transaction isolation mặc định và mức được server hỗ trợ.
- Savepoint, rollback và commit ở các nhánh lỗi.
- Generated keys và cách driver trả kết quả sau insert.
- Batch execution, update count và partial failure.
- Deadlock/timeout exception và `SQLState`.
- Thời gian lấy/đóng connection, network error và retry.
- Cách framework ánh xạ `SQLException` thành domain exception.

### 20.1. Kiểm tra SQLState và mã lỗi vendor

Một ứng dụng có thể phân loại lỗi dựa trên:

~~~java
String state = exception.getSQLState();
int vendorCode = exception.getErrorCode();
~~~

JDBC driver mới có thể cải thiện hoặc đổi mapping exception/subclass, SQLState hoặc vendor code cho một số tình huống. Nếu logic retry dựa trên mã lỗi, cần test deadlock, unique constraint, connection reset và syntax error thực tế.

Không retry mọi `SQLException`. Một số lỗi là vĩnh viễn hoặc có thể gây tác dụng phụ nếu thao tác không idempotent.

## 21. PreparedStatement: giữ an toàn và rõ kiểu dữ liệu

Migration driver không phải lý do để quay về nối chuỗi SQL:

~~~java
// Không nên làm:
String sql = "SELECT * FROM customer WHERE name = '" + name + "'";
~~~

Thay vào đó, dùng parameter binding:

~~~java
String sql = "SELECT customer_id FROM customer WHERE name = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, name);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("customer_id"));
        }
    }
}
~~~

Nhưng parameter binding không tự chuẩn hóa mọi kiểu dữ liệu. Với `DECIMAL`, `DATE`, `TIMESTAMP`, JSON hoặc vendor type, cần chỉ rõ kiểu và conversion phù hợp với schema.

Driver/server có thể khác ở prepared statement server-side, parameter inference và plan caching. Nếu thấy lỗi type mismatch sau nâng driver, sửa cách bind hoặc khai báo kiểu rõ ràng theo tài liệu, không thay sang SQL concatenation.

## 22. ORM/JPA: driver là một tầng trong chuỗi mapping

Ứng dụng dùng JPA/Hibernate hoặc ORM khác thường không gọi `ResultSet.getObject` trực tiếp. Dù vậy, driver vẫn xử lý conversion ở tầng thấp.

Ví dụ luồng:

~~~text
Database SQL type
       |
JDBC driver conversion
       |
ORM JDBC type/dialect
       |
AttributeConverter / custom UserType
       |
Java entity attribute
       |
Business DTO / API
~~~

Khi thay driver, cùng lúc nâng Hibernate hoặc đổi dialect, có thể thay đổi cả nhiều tầng. Cần cố gắng tách các thay đổi để xác định nguyên nhân:

1. Giữ database schema, nâng driver và test repository/ORM hiện tại.
2. Nâng framework/dialect nếu driver mới yêu cầu, test lại.
3. Thực hiện schema migration có kiểm soát nếu cần.
4. Kiểm tra API dữ liệu trả ra cho consumer.

Các trường cần chú ý với ORM:

- Mapping `BigDecimal` precision/scale.
- `LocalDateTime`, `Instant` và timestamp timezone.
- Enum lưu theo ordinal hoặc string.
- UUID/JSON custom type.
- LOB lazy loading và session lifetime.
- Generated identifier và sequence/identity strategy.
- Dirty checking với đối tượng mutable.
- Query pagination, fetch size và dialect-specific SQL.
- Schema validation khi metadata driver thay đổi.

Không nên giải quyết một warning kiểu cột của ORM bằng cách tự động sửa production schema nếu chưa đánh giá ảnh hưởng dữ liệu và tương thích ngược.

## 23. Kiểm tra schema migration cùng lúc nhưng tách bằng chứng

Đổi driver thường diễn ra trong một dự án lớn hơn có thay schema. Hai thay đổi có thể che lấp nhau:

- Schema đổi `INT` sang `BIGINT`.
- Driver đổi Java type của một vendor-specific column.
- ORM đổi mapping attribute.
- Dịch vụ công bố kiểu API mới.

Nên kiểm tra theo những cặp rõ ràng:

| Driver | Schema | Mục đích |
|---|---|---|
| Cũ | Cũ | Baseline |
| Mới | Cũ | Tác động riêng từ driver |
| Cũ | Mới | Nếu còn được hỗ trợ, ảnh hưởng riêng của schema |
| Mới | Mới | Trạng thái migration mục tiêu |

Không phải mọi tổ hợp đều được hỗ trợ, đặc biệt nếu server/database version thay đổi. Nếu không thể chạy một tổ hợp, ghi rõ **NOT_SUPPORTED** hoặc **NOT_TESTED**, thay vì coi nó là PASS.

Với rolling deployment có nhiều phiên bản ứng dụng, cần bảo đảm schema trong giai đoạn chuyển tiếp đáp ứng cả consumer cũ và mới nếu đó là yêu cầu vận hành. Có thể cần expand–migrate–contract cho cột, constraint hoặc JSON format.

## 24. Thiết kế bộ test mapping theo dữ liệu biên

Không chỉ test một bản ghi mẫu. Nên xây fixture với các giá trị có khả năng phơi bày khác biệt conversion.

| Nhóm | Trường hợp đại diện |
|---|---|
| Numeric | 0, âm, max/min, overflow, `DECIMAL(18,4)`, rounding |
| Nullable | SQL NULL, giá trị 0/false/empty, NOT NULL |
| Temporal | UTC, zone địa phương, DST, midnight, leap day, fractional seconds |
| Strings | Tiếng Việt, emoji, Unicode ngoài BMP, trailing space, dài gần giới hạn |
| Binary | Byte 0x00/0xFF, empty blob, dữ liệu lớn |
| UUID | Chuỗi hợp lệ, UUID native, binary representation, null |
| JSON | Null, number lớn, nested objects, Unicode, field không bắt buộc |
| Arrays | Empty, null elements, multi-dimensional nếu hỗ trợ |
| SQLXML | XML có encoding và schema phù hợp, dữ liệu không hợp lệ |
| Transactions | Commit, rollback, deadlock, retry, batch partial failure |
| Metadata | Alias, computed column, view, join, precision/scale |
| Connection | Timeout, pool recycling, failover, session setting |

Một test mapping tốt phải so sánh **giá trị và ngữ nghĩa**, không chỉ class trả về. Ví dụ với money, so sánh giá trị số và scale theo hợp đồng; với timestamp, so sánh instant hoặc local date-time tùy loại cột đã thiết kế.

### 24.1. Test round-trip

Một bài test thường hữu ích:

1. Ghi giá trị Java bằng driver mới.
2. Đọc lại qua chính driver đó.
3. So sánh với hợp đồng dữ liệu.
4. Nếu cần backward compatibility, đọc bằng driver cũ.
5. Thử dữ liệu được tạo từ driver cũ.
6. Kiểm tra kiểu cột và precision không đổi ngoài dự kiến.

Không phải mọi phép round-trip đều bảo toàn nguyên trạng dữ liệu đầu vào: database có thể chuẩn hóa timezone, cắt precision hoặc sắp xếp JSON. Điều cần kiểm là hành vi **được cam kết** và sự khác biệt đã được phê duyệt.

### 24.2. Test với hai driver version

Cách tổ chức fixture:

~~~text
same SQL schema
same input dataset
same server version
same JDK/runtime where supported
  |
  +-- Driver A -> capture values/errors/metadata
  |
  +-- Driver B -> capture values/errors/metadata
  |
compare according to explicit data contracts
~~~

Nếu driver A không hỗ trợ JDK mới, có thể phải test ở JDK nguồn và đích khác nhau. Khi đó kết quả phản ánh tổ hợp driver/JDK chứ không tách riêng tác động của driver; báo cáo cần nói rõ giới hạn.

## 25. Kiểm tra runtime compatibility và driver artifact

Một driver phiên bản mới có thể yêu cầu JDK tối thiểu cao hơn phiên bản ứng dụng đang chạy. Khi đó, dù source ứng dụng biên dịch thành công, JVM vẫn có thể báo:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
~~~

Cần đối chiếu yêu cầu JDK của driver, class-file major version, dependency và môi trường runtime. Một số giá trị phổ biến:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Có thể xem class-file version của một class trong JAR:

~~~bash
javap -verbose -classpath jdbc-driver.jar \
  com.vendor.DriverClass
~~~

`com.vendor.DriverClass` là placeholder, cần thay bằng class thực có trong driver. Kiểm tra một class không chứng minh mọi class và dependency tương thích, nhất là multi-release JAR; phải chạy integration test trên runtime được hỗ trợ.

### 25.1. Gradle: pin đúng driver version

Ví dụ Kotlin DSL:

~~~kotlin
dependencies {
    runtimeOnly("com.example:example-jdbc-driver:1.2.3")
}
~~~

Tọa độ trên là minh họa, không phải artifact thật. Trong dự án thực, dùng đúng coordinates theo vendor và version đã kiểm chứng, tránh dynamic version không kiểm soát.

Có thể xem runtime dependency resolution:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Đây là **lệnh ví dụ trong bài học**, không phải hướng dẫn worker chạy ở bước biên soạn. Với multi-module build, cần chọn đúng project/configuration. Kiểm tra dependency graph giúp xác định driver thực sự được đóng gói, nhưng không tự chứng minh mapping đúng.

## 26. TLS, authentication và bảo mật khi nâng driver

Driver mới có thể thay đổi default liên quan đến TLS, certificate validation, hostname verification hoặc authentication plugin. Những thay đổi này cần được phân tích riêng với mapping dữ liệu.

Khi connection fail:

- Kiểm tra server/driver compatibility và protocol.
- Xác nhận TLS certificate chain, hostname/SAN và truststore.
- Kiểm tra authentication mechanism và credential source.
- Xem URL properties của đúng vendor/version.
- Xác minh proxy, firewall, network timeout và server log.

Không nên bỏ xác minh TLS hoặc bật trust-all chỉ để kết nối thành công. Một lỗi certificate sau nâng driver có thể cho thấy hệ thống trước đây bỏ qua xác minh danh tính. Giải pháp đúng thường là sửa certificate, CA chain, truststore hoặc endpoint.

Cũng không nên đưa username/password vào log, source code hay báo cáo migration. Sử dụng secret management phù hợp và che thông tin nhạy cảm khi chụp stack trace.

## 27. Hiệu năng: phân biệt mapping và fetch behavior

Một driver mới có thể thay đổi cách:

- Prefetch/fetch rows.
- Sử dụng server-side prepared statement.
- Buffer result set hoặc stream dữ liệu.
- Gửi batch.
- Cấu hình query timeout và network timeout.
- Cache metadata và prepared statements.
- Xử lý connection failover.

Một query trả đúng dữ liệu nhưng tiêu thụ bộ nhớ cao hơn hoặc chậm hơn nhiều vẫn có thể là regression vận hành.

Khi đo, cần giữ cùng dataset, index, server load và query plan ở mức có thể. Đừng chỉ so sánh kết quả một lần chạy. Cần xem latency percentile, throughput, allocation/memory, connection pool utilization và số lần round-trip.

Dù vậy, hiệu năng khác biệt không tự cho phép đổi precision/scale, bỏ transaction hoặc giảm TLS security để đạt thông số cũ.

## 28. Lưu bằng chứng migration có thể tái lập

Một hồ sơ test có thể theo mẫu:

~~~yaml
migration:
  component: "example-service JDBC integration"
  oldDriver: "vendor-driver:old-version"
  newDriver: "vendor-driver:new-version"
  jdk: "record actual vendor/build"
  database:
    product: "record actual DB"
    serverVersion: "record server version"
  schemaRevision: "record migration or schema version"
  testScope:
    - numeric-precision-scale
    - null-and-boolean
    - time-zone-and-timestamp
    - unicode-and-binary
    - vendor-json-uuid-array
    - transaction-rollback
    - tls-and-connection-pooling
  results:
    mapping: "NOT_YET_RUN"
    integration: "NOT_YET_RUN"
  limitations:
    - "list environments or drivers not yet tested"
~~~

Đây là mẫu minh họa, không phải kết quả có thật. Khi thực hiện, nên bổ sung:

- Commit và artifact checksum.
- JDBC driver resolved version, classpath/module path.
- JDK distribution/build, DB vendor/version và session settings.
- Database schema revision và fixture/dataset checksum.
- Lệnh test, log và test report.
- Các ngoại lệ được phê duyệt.
- Owner, quyết định go/no-go và kế hoạch rollback.

Không ghi một dòng “JDBC compatible” khi mới chạy `SELECT 1`. Nó chỉ cho thấy một đường kết nối/truy vấn rất nhỏ đã hoạt động.

## 29. Quy trình nâng JDBC driver có kiểm soát

### Bước 1: Chốt baseline

Ghi JDK, driver, database server, schema, timezone, pool/ORM version và dependency graph đang hoạt động. Lưu kết quả mapping của các kiểu quan trọng.

### Bước 2: Xác định driver mới và phạm vi hỗ trợ

Kiểm tra yêu cầu Java tối thiểu, database server version, JDBC API level, support policy và những release note về data type, timezone, TLS, authentication.

### Bước 3: Kiểm kê chỗ dùng JDBC

Tìm các lời gọi `getObject` có cast cứng, mapping `Timestamp`, custom converters, `setNull`, generated keys, batch, pool configuration và driver-specific object.

### Bước 4: Nâng một trục khi có thể

Giữ database và schema cố định để kiểm tra driver, hoặc kiểm tra driver mới trên JDK mục tiêu khi driver cũ không chạy được trên JDK ấy. Nếu đổi nhiều trục, ghi rõ kết luận bị giới hạn bởi sự kết hợp đó.

### Bước 5: Chạy type mapping contract tests

Bao phủ numeric, null, date/time/timezone, Unicode, binary, JSON/UUID/ARRAY và metadata như hợp đồng hệ thống yêu cầu.

### Bước 6: Chạy transaction và connection tests

Kiểm tra commit, rollback, isolation, batch, retry, TLS, pool lifecycle và sự cố mất kết nối.

### Bước 7: Chạy integration test với ORM và dịch vụ thật

Xác minh repository, DTO, API response, event payload và hệ thống downstream. Các mapper dữ liệu không chỉ ảnh hưởng JDBC layer mà còn ảnh hưởng hợp đồng công khai.

### Bước 8: Thử rollout

Triển khai môi trường đại diện, có kiểm soát version, metrics và rollback plan. Theo dõi lỗi SQL, deadlock, pool exhaustion, data anomalies và chỉ số nghiệp vụ.

### Bước 9: Ghi nhận sự khác biệt có chủ đích

Nếu driver mới sửa một conversion cũ vốn sai, cần quyết định cách migration và thông báo consumer. Đừng tự diễn đạt mọi behavior change là “không breaking” vì nó có thể làm thay đổi dữ liệu tính toán hoặc báo cáo.

## 30. Những sai lầm thường gặp

**“JDBC là chuẩn nên đổi driver luôn an toàn.”** Chuẩn hóa API không bảo đảm mọi vendor type, metadata và conversion giống nhau.

**“`getObject()` luôn trả cùng Java class.”** Mapping phụ thuộc SQL type, driver và database; nên yêu cầu kiểu rõ hoặc có adapter.

**“TIMESTAMP luôn là một Instant.”** Timestamp không timezone có thể chỉ là local date-time; cần quy ước dữ liệu.

**“Đọc tiền bằng double không sao nếu giao diện hiển thị hai số lẻ.”** Sai số và rounding có thể ảnh hưởng tổng tiền; dùng DECIMAL/BigDecimal đúng hợp đồng.

**“0 và SQL NULL tương đương với getter primitive.”** `getInt`/`getBoolean` cần `wasNull` khi cột nullable.

**“Driver mới hỗ trợ java.time nghĩa là mọi type convert được.”** Mức độ hỗ trợ khác nhau; test từng kiểu SQL và target Java type.

**“Thêm một JDBC JAR là đủ khi driver không được tìm thấy.”** Service discovery, classloader, shading và module path có thể ảnh hưởng.

**“ORM che toàn bộ khác biệt driver.”** ORM có thêm dialect/converter nhưng vẫn dùng driver; mapping và metadata vẫn cần kiểm tra.

**“Chạy `SELECT 1` chứng minh database compatibility.”** Chỉ xác minh kết nối và một truy vấn đơn giản.

**“Có thể tắt TLS validation để chữa lỗi kết nối.”** Đó là giảm kiểm soát bảo mật, không phải sửa tương thích an toàn.

**“Test trên máy developer đủ cho production.”** JVM, DB server, timezone, collation, container, pool và network có thể khác.

**“Mọi lỗi SQL sau nâng JDK đều do JDK.”** Phải tách ảnh hưởng của driver, server, ORM, schema, config và dữ liệu.

## 31. Checklist khi hoàn tất migration JDBC

- [ ] Đã ghi phiên bản JDK, driver, database server và môi trường thực tế.
- [ ] Đã xác nhận class-file baseline và driver/JDK/server support matrix.
- [ ] Đã kiểm tra driver loading, dependency graph, classpath/module path.
- [ ] Đã kiểm tra DataSource và connection pool lifecycle.
- [ ] Đã kiểm thử `NULL`, zero, false và empty riêng biệt.
- [ ] Đã kiểm numeric precision, scale, rounding và overflow.
- [ ] Đã xác định contract cho DATE/TIME/TIMESTAMP và timezone/offset.
- [ ] Đã kiểm thời gian ở midnight, DST boundary và fractional seconds.
- [ ] Đã kiểm Unicode, emoji, collation, trailing spaces và dữ liệu nhị phân.
- [ ] Đã kiểm UUID, JSON, ARRAY, SQLXML và vendor-specific type nếu dùng.
- [ ] Đã xác minh metadata, alias và dynamic mapping.
- [ ] Đã kiểm transaction, generated keys, batch, rollback và SQLState.
- [ ] Đã chạy integration tests với ORM/dialect/framework.
- [ ] Đã kiểm TLS, certificate validation, authentication và connection timeout.
- [ ] Đã chạy round-trip tests và thử đọc dữ liệu lịch sử.
- [ ] Đã lưu test report, artifact checksum, schema revision và các giới hạn.
- [ ] Đã có quyết định go/no-go, owner và rollback plan.

## Kết luận

**Đổi JDBC driver là thay đổi về giao tiếp và ngữ nghĩa dữ liệu, không chỉ thay một JAR.** API JDBC chuẩn giúp ứng dụng viết code ít phụ thuộc vendor hơn, nhưng không loại bỏ khác biệt ở SQL type, precision, null, timezone, metadata, vendor-specific type, transaction hay connection behavior.

Trong Java Advance Compatibility Migration, cần kiểm tra riêng JDK, driver, database và ORM, thiết kế mapper theo contract dữ liệu thay vì cast dựa trên implementation hiện tại, đồng thời dùng test round-trip và dữ liệu biên để phát hiện sai lệch. Khi lưu đầy đủ môi trường, dataset, dependency, kết quả kiểm chứng và rủi ro còn lại, nhóm mới có cơ sở khẳng định thay đổi JDBC driver phù hợp với các consumer thực tế và không làm mất tính chính xác của dữ liệu.
