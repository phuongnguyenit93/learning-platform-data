# Liên kết String, số, boolean, ngày giờ và byte[] vào tham số SQL với Spring JDBC

> **Mục tiêu học tập:** Viết đúng câu SQL có placeholder, chọn kiểu Java/JDBC cho **`String`, số nguyên/số thập phân, `boolean`, `LocalDate`/`LocalTime`/`LocalDateTime` và `byte[]`**, truyền chúng qua `PreparedStatement` hoặc `JdbcTemplate`, xử lý `NULL` có kiểu, kiểm tra dữ liệu đọc ngược và hiểu giới hạn portability giữa JDBC driver/database.

Phạm vi: **Spring Framework → Data Access → Tham số SQL**, tập trung vào JDBC và `JdbcTemplate`. Ví dụ dùng Java 17+ và Spring Boot để có `DataSource`, nhưng cơ chế bind nằm trong JDBC/Spring JDBC; không cần JPA hay Hibernate.

## 1. “Bind tham số SQL” thực sự là gì?

Khi chạy một câu SQL có dữ liệu đầu vào, **không ghép giá trị vào chuỗi SQL**. Thay vào đó, viết **SQL template** có các dấu `?`, rồi gắn (*bind*) giá trị Java vào từng vị trí bằng `PreparedStatement`. Driver chịu trách nhiệm truyền giá trị đến DB theo kiểu JDBC phù hợp.

```text
Dữ liệu Java:
  id = 101L
  label = "Spring JDBC"
  enabled = true
          |
          v
SQL template:
  INSERT INTO bind_demo (id, label, enabled)
  VALUES (?, ?, ?)
           1  2  3
          |
          v
PreparedStatement:
  setLong(1, 101L)
  setString(2, "Spring JDBC")
  setBoolean(3, true)
          |
          v
JDBC driver -> database
```

**Các nguyên tắc cốt lõi:**

1. Vị trí tham số JDBC **bắt đầu từ 1**, không bắt đầu từ 0. Dấu `?` đầu tiên ứng với index 1.
2. Mỗi dấu `?` dùng cho **giá trị**, không đại diện cho tên bảng, tên cột, từ khóa SQL, hướng `ASC/DESC` hoặc một đoạn SQL tùy ý.
3. Phải khớp **số lượng, thứ tự và kiểu dữ liệu** của các placeholder với SQL schema.
4. Binding giúp chống **SQL injection qua giá trị** vì giá trị không bị phân tích như cú pháp SQL. Tên bảng/cột động vẫn phải dùng allowlist/logic đáng tin.
5. Bind không tự kiểm tra tính hợp lệ nghiệp vụ: kích thước chuỗi, khoảng số, format ngày, timezone và ràng buộc DB vẫn cần xử lý.

**Ví dụ sai:**

```java
String sql = "SELECT id FROM users WHERE email = '" + email + "'";
// Input có dấu nháy hoặc payload SQL có thể làm sai cú pháp/ngữ nghĩa.
```

**Cách đúng (snippet, giả định đã có Connection và biến email):**

```java
String sql = "SELECT id FROM users WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            // Xử lý id khi ResultSet còn mở.
        }
    }
}
```

`PreparedStatement` vẫn cần được đóng bằng `try-with-resources`; `Connection` cũng phải được hoàn trả theo đúng bên sở hữu. Với `JdbcTemplate`, Spring quản lý việc đóng resource cho mỗi thao tác.

## 2. Bảng ánh xạ kiểu thường gặp

| Dữ liệu Java | Kiểu SQL thường phù hợp | `PreparedStatement` setter | Getter thông dụng | Lưu ý |
| --- | --- | --- | --- | --- |
| `String` | `VARCHAR`, `CHAR`, đôi khi `NVARCHAR`/`CLOB` | `setString(i, value)`; API quốc gia có `setNString` khi DB hỗ trợ | `getString` | Unicode/độ dài/collation phụ thuộc DB |
| `byte`, `short`, `int` | `TINYINT`, `SMALLINT`, `INTEGER` | `setByte`, `setShort`, `setInt` | `getInt`/`getObject` | Kiểm tra miền giá trị và NULL |
| `long` | `BIGINT` | `setLong` | `getLong` | ID/kích thước lớn; giới hạn 64-bit |
| `BigDecimal` | `DECIMAL(p,s)`, `NUMERIC(p,s)` | `setBigDecimal` | `getBigDecimal` | Thường ưu tiên cho tiền, giữ precision/scale |
| `float`, `double` | `REAL`, `FLOAT`/`DOUBLE` | `setFloat`, `setDouble` | `getDouble` | Xấp xỉ nhị phân, không thay thế tiền chính xác |
| `boolean` / `Boolean` | `BOOLEAN`, `BIT` hoặc kiểu được DB quy ước | `setBoolean`, `setObject` hoặc `setNull` | `getBoolean` + `wasNull` / `getObject` | `NULL` khác `false` |
| `LocalDate` | `DATE` | `setObject(i, localDate)` (JDBC 4.2 + driver hỗ trợ), hoặc `setDate(i, java.sql.Date.valueOf(localDate))` | `getObject(..., LocalDate.class)` hoặc `getDate().toLocalDate()` | Chỉ ngày, **không chứa giờ/múi giờ** |
| `LocalTime` | `TIME` | `setObject` hoặc `setTime(i, Time.valueOf(localTime))` | `getObject(..., LocalTime.class)` hoặc `getTime().toLocalTime()` | Không chứa ngày/zone; chú ý độ chính xác |
| `LocalDateTime` | `TIMESTAMP` không kèm time zone | `setObject` hoặc `setTimestamp(i, Timestamp.valueOf(value))` | `getObject(..., LocalDateTime.class)` | Một thời điểm lịch địa phương, không đại diện instant UTC |
| `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` (nếu DB hỗ trợ) | `setObject(i, value)`, hoặc `setObject(i, value, JDBCType.TIMESTAMP_WITH_TIMEZONE)` | `getObject(..., OffsetDateTime.class)` | Cách lưu offset/zone phụ thuộc DB |
| `byte[]` | `VARBINARY`/`BINARY` hoặc `BLOB` | `setBytes(i, bytes)`; stream cho LOB lớn | `getBytes`, binary stream | Byte thô, không phải hex/base64 text |

Bảng là **định hướng** chứ không là cam kết mọi database đều map giống nhau. SQL dialect và JDBC driver quyết định phần hỗ trợ, giới hạn, tự chuyển kiểu, precision, collation, LOB và timestamp. Khi cần khả năng di động, kiểm thử với DB/driver thật.

## 3. String: chuỗi văn bản và Unicode

Đối với SQL `VARCHAR`, cách thường dùng nhất:

```java
// Snippet trong method có PreparedStatement ps.
ps.setString(1, "Spring JDBC");
ps.setString(2, "Nguyễn An");
```

Nếu cột `VARCHAR(100)`, Java `String` dài hơn kích thước cột có thể bị DB từ chối hoặc cắt theo chế độ cấu hình; **không tự tin rằng bind sẽ rút ngắn an toàn**. Kiểm tra độ dài theo quy tắc nghiệp vụ, lưu ý database đếm ký tự/byte/đơn vị Unicode khác nhau.

**Unicode:** String trong Java dùng UTF-16; driver/DB phải có encoding và collation phù hợp. Một chuỗi tiếng Việt chứa dấu hoặc emoji cần được kiểm tra cả chiều ghi/đọc. Một số DB phân biệt `VARCHAR` với `NVARCHAR`, `CHAR` và national-character API; nếu lưu text đa ngôn ngữ lỗi, đọc DDL, encoding và JDBC driver trước khi “fix” bằng cách tự escape Unicode.

**Text rỗng và NULL không đồng nghĩa** trong mọi database. `""` là chuỗi rỗng Java; SQL `NULL` thể hiện không có giá trị. Một số database có hành vi riêng đối với empty string, nên phải xác nhận quy tắc lưu trữ của hệ đang sử dụng.

**Sai:** nối tên/giá trị vào SQL; tự thêm dấu nháy quanh placeholder (`WHERE name = '?'`). Placeholder là `?` **không có dấu nháy**:

```sql
-- ĐÚNG
SELECT id FROM users WHERE display_name = ?;

-- SAI: dấu hỏi bị hiểu là literal văn bản.
SELECT id FROM users WHERE display_name = '?';
```

Nếu tên cột dùng cho ORDER BY được chọn từ request, viết allowlist Java:

```java
// Minh họa whitelisting tên cột, không phải SQL parameter.
String orderColumn = switch (requestedSort) {
    case "name" -> "display_name";
    case "created" -> "created_at";
    default -> throw new IllegalArgumentException("Unsupported sort");
};
String sql = "SELECT id FROM users ORDER BY " + orderColumn;
```

Chỉ ghép **identifier đã hardcode trong allowlist**, không ghép input trực tiếp. Giá trị WHERE vẫn bind bằng `?`/named parameter.

## 4. Số nguyên và số thập phân: chọn đúng miền và precision

### Integer/Long

```java
// Java int -> SQL INTEGER, Java long -> SQL BIGINT.
ps.setInt(1, 42);
ps.setLong(2, 9_000_000_000L);
```

`int` 32-bit signed, `long` 64-bit signed. Kiểm tra cả giới hạn SQL `SMALLINT`/`INTEGER`/`BIGINT`, kể cả trường hợp converter hoặc driver tự cast. Với ID có giá trị lớn, không ép `long` về `int` rồi hy vọng DB xử lý.

**SQL NULL khi đọc primitive:** `ResultSet.getInt("count")` có thể trả `0` khi cột NULL; `getLong` cũng vậy. Nếu cần phân biệt, gọi `rs.wasNull()` **ngay sau getter** hoặc dùng wrapper + `getObject` khi driver hỗ trợ.

```java
int count = rs.getInt("count");
Integer nullableCount = rs.wasNull() ? null : count;
```

Snippet trên giả định `rs.next()` đã thành công và cột `count` tồn tại.

### BigDecimal và số tiền

`BigDecimal` giữ số thập phân thập phân theo độ chính xác đã chọn; `double` là floating-point nhị phân và có thể gây sai số khi cần khớp chính xác tiền.

```java
BigDecimal amount = new BigDecimal("1999.50");
ps.setBigDecimal(1, amount);
```

**Không ưu tiên** `new BigDecimal(0.1)` vì constructor từ `double` phản ánh xấp xỉ nhị phân; chọn `new BigDecimal("0.10")` hoặc `BigDecimal.valueOf(0.1)` khi đã có double, và tốt nhất nhận chuỗi thập phân có kiểm soát.

Với SQL `DECIMAL(12,2)`: precision 12 là tổng số chữ số; scale 2 là số chữ số sau dấu thập phân. Nếu đầu vào có nhiều chữ số thập phân hơn, DB có thể làm tròn hoặc báo lỗi tùy dialect/chế độ. Xác định quy tắc rounding ở domain, ví dụ:

```java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
```

Bài toán tài chính thực cần chọn quy tắc làm tròn theo sản phẩm/quy định, không áp dụng `HALF_UP` cho mọi trường hợp một cách mù quáng.

### Vì sao SQL type cũng quan trọng?

Spring `JdbcTemplate` thông thường suy ra SQL type từ Java value. Khi loại dữ liệu không rõ, ví dụ `null` hoặc kiểu vendor-specific, có thể cung cấp `java.sql.Types.DECIMAL`/`BIGINT` v.v. để tránh driver chuyển kiểu sai hoặc không suy ra được type. Phần 9 trình bày cách khai báo tường minh.

## 5. Boolean: true, false và NULL là ba trạng thái khác nhau

`boolean` Java chỉ có hai trạng thái, `Boolean` wrapper có thể `null`. Nhiều DB hỗ trợ SQL `BOOLEAN`, một số hệ thống đời cũ lưu bằng `BIT`, `NUMBER(1)`, `TINYINT`, `CHAR(1)` hoặc quy ước riêng.

```java
ps.setBoolean(1, true);
ps.setBoolean(2, false);
```

**Không giả định** `setBoolean(1, true)` luôn có nghĩa driver gửi literal SQL `TRUE`. Nó gửi giá trị typed parameter; DB/driver quyết định mapping. Đọc DDL thay vì suy ra từ tên `is_active`.

**Khi đọc cột nullable:**

```java
boolean active = rs.getBoolean("active");
Boolean nullableActive = rs.wasNull() ? null : active;
```

Nếu cột nullable nhưng code dùng `getBoolean` và bỏ qua `wasNull()`, `NULL` thường bị đọc thành `false` và mất thông tin. Nếu business domain chỉ có hai trạng thái, dùng `NOT NULL` ở DB để thể hiện rõ yêu cầu.

Nếu có `Boolean maybeActive = null`, đừng đưa vào `setBoolean` (chỉ nhận primitive); dùng:

```java
if (maybeActive == null) {
    ps.setNull(1, Types.BOOLEAN);
} else {
    ps.setBoolean(1, maybeActive);
}
```

Đoạn này minh họa mã bên trong callback có biến `ps` và `maybeActive`; không phải file Java chạy độc lập.

## 6. Ngày, giờ và timestamp: bốn loại cần phân biệt

**Sai lầm phổ biến:** dùng một loại “date time” cho tất cả lịch hẹn, ngày sinh và thời điểm hệ thống. Trước khi bind phải quyết định dữ liệu mang ý nghĩa gì.

| Nghiệp vụ | Java nên cân nhắc | SQL thường dùng | Có thông tin zone/offset? |
| --- | --- | --- | --- |
| Ngày sinh, hạn thanh toán theo lịch | `LocalDate` | `DATE` | Không |
| Giờ mở cửa mỗi ngày | `LocalTime` | `TIME` | Không |
| Lịch hẹn ở múi giờ của địa điểm cố định (lưu local date-time cùng zone riêng nếu cần) | `LocalDateTime` | `TIMESTAMP` | Không |
| Một thời điểm sự kiện toàn cục | `Instant` hoặc `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` hoặc chính sách UTC được định nghĩa | Có khi biểu diễn cùng zone/offset riêng |

### 6.1. LocalDate -> SQL DATE

```java
LocalDate day = LocalDate.of(2026, 10, 30);
ps.setDate(1, java.sql.Date.valueOf(day));
// JDBC 4.2 và driver tương thích: ps.setObject(1, day);
```

`java.sql.Date` và `java.util.Date` là hai lớp khác nhau. `LocalDate` không có giờ/zone. Khi đọc, `rs.getDate("day").toLocalDate()` phù hợp nếu không NULL. Với JDBC 4.2 và driver hỗ trợ, dùng `rs.getObject("day", LocalDate.class)` để giảm chuyển qua loại `java.sql` cũ.

### 6.2. LocalTime -> SQL TIME

```java
LocalTime time = LocalTime.of(9, 15, 30);
ps.setTime(1, java.sql.Time.valueOf(time));
// JDBC 4.2 + driver tương thích: ps.setObject(1, time);
```

`TIME` chỉ giờ/phút/giây, không mang ngày hay timezone. `java.sql.Time` thường bỏ precision sub-second; nếu yêu cầu nanosecond, kiểm tra dialect, độ chính xác SQL cột và API `setObject(LocalTime)` thực tế.

### 6.3. LocalDateTime -> SQL TIMESTAMP

```java
LocalDateTime localTime = LocalDateTime.of(2026, 10, 30, 9, 15, 30);
ps.setTimestamp(1, java.sql.Timestamp.valueOf(localTime));
// Driver JDBC 4.2 tương thích: ps.setObject(1, localTime);
```

`LocalDateTime` không gắn timezone. Giá trị `2026-10-30T09:15:30` **không đủ để suy ra một thời điểm UTC**: 09:15 tại Hà Nội và 09:15 tại New York là hai instant khác nhau. Khi dùng `TIMESTAMP` không kèm timezone, quy định timezone theo nghiệp vụ hoặc lưu zone riêng nếu cần diễn giải.

### 6.4. Instant/OffsetDateTime và TIMESTAMP WITH TIME ZONE

`Instant` biểu diễn mốc trên UTC timeline. `OffsetDateTime` giữ ngày giờ cùng độ lệch UTC cụ thể. Với DB/JDBC driver hỗ trợ, có thể bind:

```java
OffsetDateTime moment = OffsetDateTime.parse(
        "2026-10-30T09:15:30+07:00");
ps.setObject(1, moment, JDBCType.TIMESTAMP_WITH_TIMEZONE);
```

**Đây là snippet minh họa, không nằm trong ví dụ runnable của mục 10**: loại SQL, cách driver map, độ chính xác và việc giữ hay chuẩn hóa offset phụ thuộc DB. `TIMESTAMP WITH TIME ZONE` không có nghĩa mọi database giữ nguyên tên vùng `Asia/Ho_Chi_Minh`; đôi khi chỉ lưu instant/offset hoặc normalize. Nếu ứng dụng cần quy tắc daylight-saving, hãy lưu zone ID theo yêu cầu.

Đặc biệt tránh serialize `Instant` thành chuỗi giờ địa phương rồi bind vào `TIMESTAMP` mà không kiểm soát timezone. Kiểm thử round-trip giữa JVM timezone, JDBC/session timezone và cấu hình DB.

## 7. byte[]: nhị phân khác với văn bản

`byte[]` biểu diễn dãy byte thô: hash, checksum, file nhỏ, nội dung nén hoặc binary protocol. SQL tương ứng thường là `VARBINARY`/`BINARY`, còn dữ liệu lớn dùng `BLOB` với cơ chế streaming/LOB phù hợp.

```java
byte[] digest = { 0x01, 0x23, (byte) 0xFF };
ps.setBytes(1, digest);
```

Giải thích: Java `byte` là **signed** trong khoảng -128..127, nên 0xFF được biểu diễn trong mảng là `-1`; đó là **cùng một byte bit-pattern**, không phải dữ liệu bị sai. `Arrays.toString(digest)` in ra `[1, 35, -1]`. Để in hex cho debugging, chuyển từng byte sang giá trị unsigned, nhưng không đổi bản chất dữ liệu:

```java
byte[] bytes = { 0x01, 0x23, (byte) 0xFF };
System.out.println(java.util.HexFormat.of().formatHex(bytes));
// 0123ff
```

`HexFormat` có từ Java 17, nên snippet trên phù hợp JDK của bài. Tuy nhiên tránh log ảnh/credential/token hoặc dữ liệu nhạy cảm ở production.

**Phân biệt ba dạng:**

- `byte[]`: chính các byte gốc; bind với `setBytes`/`Types.VARBINARY`.
- **Hex**: chuỗi ký tự như `"0123ff"`; 6 ký tự đại diện 3 byte, không phải 3 byte gốc.
- **Base64**: chuỗi text mã hóa an toàn để truyền dạng văn bản; vẫn phải decode về bytes nếu cột DB là binary.

Không gọi `new String(bytes)` để lưu binary tùy ý: byte không nhất thiết là UTF-8 hợp lệ, nên dễ mất/đổi dữ liệu. `String.getBytes(StandardCharsets.UTF_8)` chỉ dùng khi *dữ liệu gốc thật sự là text và bạn muốn encode text*.

### VARBINARY, BINARY hay BLOB?

`BINARY(n)` có độ dài cố định và driver/DB có thể padding; `VARBINARY(n)` có độ dài biến đổi trong giới hạn; `BLOB` dành cho dữ liệu lớn tùy hệ. Với dữ liệu nhiều MB, cân nhắc `setBinaryStream`/`getBinaryStream`, `Blob`, `LobHandler` trong Spring, đọc/ghi theo stream và cleanup đúng vòng đời. `setBytes` tải toàn bộ mảng vào bộ nhớ JVM nên không phù hợp mọi file lớn.

**Không nhầm `byte[]` với SQL ARRAY** (mảng giá trị SQL như `INTEGER[]` ở một số DB): SQL ARRAY dùng API/dialect khác, không phải `setBytes`.

## 8. JDBC thuần: setXxx, setObject và setNull

### 8.1. Dùng setter rõ ràng khi biết kiểu

```java
// Đoạn minh họa trong method đã có Connection con.
String sql = "INSERT INTO documents (name, page_count, active) VALUES (?, ?, ?)";
try (PreparedStatement ps = con.prepareStatement(sql)) {
    ps.setString(1, name);
    ps.setInt(2, 12);
    ps.setBoolean(3, true);
    ps.executeUpdate();
}
```

Setter rõ ràng thuận tiện cho việc đối chiếu schema/params. Cần `try-with-resources` cả connection ở lớp sở hữu nó.

### 8.2. setObject hữu ích nhưng không thần kỳ

`ps.setObject(1, value)` yêu cầu driver suy ra SQL type từ Java object. Với `LocalDate`/`LocalTime`/`LocalDateTime`, JDBC 4.2 chuẩn hóa mapping cơ bản, nhưng việc driver/DB hỗ trợ vẫn cần kiểm thử. Khi type quan trọng, dùng overload với `Types`/`JDBCType`:

```java
ps.setObject(1, new BigDecimal("12.30"), JDBCType.DECIMAL);
```

Có thể cung cấp thêm scale khi API hỗ trợ; phải đối chiếu JDBC driver và cột. Đừng truyền mọi dữ liệu dưới dạng `String` chỉ để “dễ bind”: kiểu SQL, index và so sánh có thể bị ảnh hưởng bởi implicit casts.

### 8.3. NULL là giá trị không có kiểu Java cụ thể

**Không thể suy SQL type một cách chắc chắn chỉ từ Java `null`**; nên dùng `setNull(index, Types.X)`:

```java
ps.setNull(1, Types.VARCHAR);
ps.setNull(2, Types.DECIMAL);
ps.setNull(3, Types.TIMESTAMP);
ps.setNull(4, Types.VARBINARY);
```

Chỉ dùng `Types.NULL`/`setObject(index, null)` nếu hiểu driver cụ thể; có DB không chấp nhận untyped NULL trong ngữ cảnh cần biết type. **SQL NULL không bằng Java số 0, false, empty String hay empty byte array.**

### 8.4. Đọc nullable SQL cẩn thận

`ResultSet.getInt`/`getBoolean` trả primitive mặc định khi SQL NULL; gọi `wasNull` ngay sau getter. `getString`, `getBytes`, `getBigDecimal` trả `null` cho SQL NULL. Khi `getDate` trả null, không gọi `.toLocalDate()` lên null. Hãy đưa lựa chọn nullability vào DTO/record và schema; không dùng giá trị giả như ngày `1970-01-01` để che NULL trừ khi nghiệp vụ yêu cầu thực.

## 9. Bind qua JdbcTemplate và NamedParameterJdbcTemplate

Spring Framework `JdbcTemplate` sử dụng JDBC prepared statements nhưng rút gọn việc lấy/đóng `Connection`, `PreparedStatement` và `ResultSet`, đồng thời chuyển `SQLException` thành `DataAccessException`. Với đa số use case, để Spring quản lý tài nguyên và truyền tham số tại lời gọi là đủ.

### 9.1. Varargs đơn giản: suy type từ Java

```java
int updated = jdbcTemplate.update(
        "UPDATE users SET display_name = ? WHERE id = ?",
        "Nguyễn An", 101L);
```

`JdbcTemplate.update(String, Object...)` tiện dụng khi giá trị không mơ hồ. `String`, `Integer`, `Long`, `Boolean`, `BigDecimal` và `byte[]` thường được Spring/JDBC hỗ trợ. Type chính xác và conversion phụ thuộc schema/driver.

**Nhận diện một bẫy của `byte[]`:** Java varargs `Object...` có thể gây nhầm nếu truyền array sai kiểu. Khi bạn muốn bind **một** `byte[]`, hãy đảm bảo nó được xử lý như **một giá trị**; ví dụ:

```java
byte[] bytes = { 0x01, 0x23 };
jdbcTemplate.update(
        "UPDATE docs SET body = ? WHERE id = ?",
        bytes, 101L);
```

Do `byte[]` là mảng primitive, nó là một Java object và không bị trải thành các `Object` riêng. Nhưng `Object[]` có thể bị trải thành nhiều argument trong varargs; nếu thực sự muốn bind một SQL ARRAY, cần cơ chế JDBC khác.

### 9.2. PreparedStatementSetter / PreparedStatementCreator: kiểm soát setXxx

Khi cần set kiểu tường minh, dùng callback:

```java
int changed = jdbcTemplate.update(
    "UPDATE tasks SET due_date = ?, enabled = ? WHERE id = ?",
    ps -> {
        ps.setDate(1, java.sql.Date.valueOf(
                LocalDate.of(2026, 10, 30)));
        ps.setBoolean(2, true);
        ps.setLong(3, 101L);
    });
```

Đây là snippet cần imports, một `JdbcTemplate` đã inject và các bảng/cột thích hợp. Spring quản lý connection/statement; code callback **không được đóng** `ps` hay connection. Dùng `PreparedStatementCreator` khi cần tạo statement đặc biệt hoặc dùng overload `jdbc.update(connection -> prepareStatement(...))` như dự án đầy đủ ở mục 10.

### 9.3. SqlParameterValue và int[] SQL types

Spring thường suy SQL type từ object, nhưng với `NULL`, scale đặc biệt hoặc kiểu driver nhạy cảm, khai báo type rõ:

```java
int affected = jdbcTemplate.update(
        "UPDATE profiles SET nickname = ? WHERE id = ?",
        new SqlParameterValue(Types.VARCHAR, null),
        101L);
```

`SqlParameterValue` ở `org.springframework.jdbc.core`; argument mang cả `sqlType` và `value`. Một số overload `JdbcTemplate.update`/`query` cũng nhận **mảng `int[] argTypes`**:

```java
Object[] args = { null, 101L };
int[] types = { Types.VARCHAR, Types.BIGINT };
int count = jdbcTemplate.update(
        "UPDATE profiles SET nickname = ? WHERE id = ?",
        args, types);
```

Trong cả hai snippet, giả định bảng đã có hàng id 101; code chưa là chương trình chạy riêng. Khi có nhiều tham số, **độ dài và thứ tự `argTypes` phải khớp `args` và dấu `?`**.

### 9.4. NamedParameterJdbcTemplate: dễ đọc khi nhiều tham số

`NamedParameterJdbcTemplate` cho phép SQL `:name` và map/`SqlParameterSource`. Việc parse và bind vẫn dựa trên JDBC prepared statements, không phải nối input vào SQL:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("id", 101L, Types.BIGINT)
        .addValue("active", false, Types.BOOLEAN);

int rows = namedJdbc.update(
        "UPDATE users SET enabled = :active WHERE id = :id",
        params);
```

`MapSqlParameterSource.addValue(name, value, sqlType)` cho phép chỉ rõ SQL type của từng value, **đặc biệt hữu ích cho NULL**:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("nickname", null, Types.VARCHAR)
        .addValue("id", 101L, Types.BIGINT);
```

`BeanPropertySqlParameterSource` map các property của JavaBean; khi chọn dùng, hiểu naming, nullability, property conversion. Named parameter không biến identifier SQL thành parameter; `:tableName` trong chỗ tên bảng không phải giải pháp an toàn cho SQL động.

### 9.5. Bảng so sánh cách bind

| Cách viết | Bạn cung cấp | Ai gọi setter và cleanup? | Khi nên dùng |
| --- | --- | --- | --- |
| JDBC `PreparedStatement` thuần | `setString/setInt/...` | Bạn set và đóng statement/connection | JDBC thấp hoặc thao tác đặc thù |
| `JdbcTemplate.update(sql, values...)` | Các Java objects theo thứ tự | Spring JDBC | CRUD giản đơn |
| `JdbcTemplate.update(sql, PreparedStatementSetter)` | Callback `ps.setXxx(...)` | Bạn bind, Spring cleanup | Kiểu/LOB/vendor-specific |
| `JdbcTemplate.update(PreparedStatementCreator)` | Callback tạo prepared statement và bind | Spring cleanup statement/connection | Cần statement flags/special handling |
| `SqlParameterValue` / `int[] argTypes` | Java value + SQL type | Spring JDBC | Null và SQL types phải tường minh |
| `NamedParameterJdbcTemplate` | `:name` + `MapSqlParameterSource`/map | Spring JDBC | Nhiều tham số, SQL dễ đọc |
| `JdbcClient` (Spring 6.1+) | Fluent SQL + `param(...)` | Spring JDBC | API mới, cú pháp gọn |

## 10. Ví dụ hoàn chỉnh: bind đủ 9 giá trị và đọc ngược qua H2

**Bài thực hành Java 17+**, Maven, Spring Boot **3.5.16**, Spring JDBC và H2 in-memory. Version này được dùng để ví dụ tái lập; Spring Boot 3.5.x đã hết hỗ trợ OSS, nên dự án mới cần chọn phiên bản đang được hỗ trợ và kiểm thử compatibility. H2 giúp minh họa API, không bảo đảm cùng hành vi khi đổi sang PostgreSQL, MySQL, SQL Server hoặc Oracle.

Mục tiêu: ghi `String`, `long`, `int`, `BigDecimal`, `boolean`, `LocalDate`, `LocalTime`, `LocalDateTime` và `byte[]`; cập nhật bằng named parameters; bind SQL `NULL` tường minh.

**Cấu trúc dự án:**

```text
jdbc-bind-types/
├── pom.xml
└── src/main/
    ├── java/com/example/bind/BindTypesApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

### 10.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jdbc-bind-types</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.2. src/main/resources/schema.sql

```sql
CREATE TABLE bind_demo (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    quantity INTEGER NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    enabled BOOLEAN NOT NULL,
    work_date DATE NOT NULL,
    work_time TIME NOT NULL,
    created_local TIMESTAMP NOT NULL,
    payload VARBINARY(16) NOT NULL,
    nickname VARCHAR(120)
);
```

**Schema giải thích:** `DECIMAL(12,2)` bảo toàn tiền dạng fixed-point; `DATE`/`TIME`/`TIMESTAMP` đều không kèm timezone; `payload` là bytes thô (không phải base64); `nickname` nullable dùng để kiểm tra typed NULL.

### 10.3. src/main/resources/application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.datasource.url=jdbc:h2:mem:bindtypes;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

Spring Boot tạo datasource H2 từ classpath và chạy `schema.sql` trước runner. Dùng H2 trong bộ nhớ giúp demo không cần server DB; khi JVM kết thúc dữ liệu demo không còn.

### 10.4. src/main/java/com/example/bind/BindTypesApplication.java

```java
package com.example.bind;

import java.math.BigDecimal;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.Time;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.Arrays;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@SpringBootApplication
public class BindTypesApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindTypesApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc) {
        return args -> {
            String insert = """
                    INSERT INTO bind_demo
                      (id, display_name, quantity, amount, enabled,
                       work_date, work_time, created_local, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """;

            // PreparedStatementCreator: Spring owns closing Connection/Statement.
            int inserted = jdbc.update(connection -> {
                PreparedStatement ps = connection.prepareStatement(insert);

                ps.setLong(1, 101L);
                ps.setString(2, "Spring JDBC");
                ps.setInt(3, 3);
                ps.setBigDecimal(4, new BigDecimal("1999.50"));
                ps.setBoolean(5, true);

                ps.setDate(6, Date.valueOf(
                        LocalDate.of(2026, 10, 30)));
                ps.setTime(7, Time.valueOf(
                        LocalTime.of(9, 15, 30)));
                ps.setTimestamp(8, Timestamp.valueOf(
                        LocalDateTime.of(2026, 10, 30, 9, 15, 30)));

                ps.setBytes(9, new byte[] { 1, 35, (byte) 0xFF });
                return ps;
            });
            System.out.println("inserted=" + inserted);

            // Kiểm tra readback của tất cả kiểu chính.
            String row = jdbc.queryForObject(
                    "SELECT * FROM bind_demo WHERE id = ?",
                    (rs, number) ->
                        rs.getLong("id") + "|" +
                        rs.getString("display_name") + "|" +
                        rs.getInt("quantity") + "|" +
                        rs.getBigDecimal("amount") + "|" +
                        rs.getBoolean("enabled") + "|" +
                        rs.getDate("work_date").toLocalDate() + "|" +
                        rs.getTime("work_time").toLocalTime() + "|" +
                        rs.getTimestamp("created_local")
                                .toLocalDateTime() + "|" +
                        Arrays.toString(rs.getBytes("payload")),
                    101L);
            System.out.println("row=" + row);

            // SQL named params: bật/tắt bằng Boolean có SQL type rõ.
            NamedParameterJdbcTemplate named =
                    new NamedParameterJdbcTemplate(jdbc);
            MapSqlParameterSource params = new MapSqlParameterSource()
                    .addValue("enabled", false, Types.BOOLEAN)
                    .addValue("id", 101L, Types.BIGINT);
            int changed = named.update(
                    "UPDATE bind_demo SET enabled = :enabled WHERE id = :id",
                    params);
            System.out.println("named-updated=" + changed);

            Boolean enabled = jdbc.queryForObject(
                    "SELECT enabled FROM bind_demo WHERE id = ?",
                    Boolean.class, 101L);
            System.out.println("enabled=" + enabled);

            // Typed SQL NULL trong JdbcTemplate varargs.
            int nullChanged = jdbc.update(
                    "UPDATE bind_demo SET nickname = ? WHERE id = ?",
                    new SqlParameterValue(Types.VARCHAR, null),
                    101L);
            System.out.println("null-updated=" + nullChanged);

            String nickname = jdbc.queryForObject(
                    "SELECT nickname FROM bind_demo WHERE id = ?",
                    String.class, 101L);
            System.out.println("nickname-null=" + (nickname == null));
        };
    }
}
```

**Chạy từ thư mục `jdbc-bind-types`**, đã cài JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

**Sáu dòng do ứng dụng in ra**, không tính các dòng Maven/Spring:

```text
inserted=1
row=101|Spring JDBC|3|1999.50|true|2026-10-30|09:15:30|2026-10-30T09:15:30|[1, 35, -1]
named-updated=1
enabled=false
null-updated=1
nickname-null=true
```

**Giải thích kỹ thuật:**

1. Mọi giá trị đầu vào đều bind vào `?`, không phải SQL string concatenation. `PreparedStatementCreator` trả statement đã bind; `JdbcTemplate` đóng connection/statement đúng contract khi thực thi.
2. `id` BIGINT nhận `long`, `quantity` INTEGER nhận `int`; `amount` DECIMAL nhận `BigDecimal("1999.50")` nên giữ hai chữ số thập phân khi đọc lại.
3. `enabled` BOOLEAN nhận true, rồi update bằng `MapSqlParameterSource` thành false; tên `:enabled`/`:id` được Spring parse thành bind parameters.
4. Ngày và giờ được tạo bằng **giá trị cố định**, không dùng đồng hồ hiện tại: `LocalDate`/`LocalTime`/`LocalDateTime` không kèm timezone, tương ứng `DATE`/`TIME`/`TIMESTAMP` H2.
5. `payload` chứa đúng 3 byte; `Arrays.toString` hiển thị byte `0xFF` thành `-1` vì signed byte của Java.
6. `nickname` ban đầu NULL vì chưa được đặt; thao tác `SqlParameterValue(Types.VARCHAR, null)` minh họa bind NULL có SQL type rõ ràng. Query theo `String.class` trả Java `null`.
7. Ví dụ dùng statement riêng biệt và autocommit thông thường của H2 datasource; **không** ngụ ý mọi operation nằm trong một transaction chung. Nếu nhiều thay đổi phải atomic, tổ chức chúng ở `@Transactional` service.
8. Đây là một project Maven hoàn chỉnh về mặt cấu trúc/code, khác với các snippet minh họa ở mục khác. Khi triển khai thực, cần test bằng DB thật và dependency versions còn được hỗ trợ.

## 11. Chọn đúng hình thức bind trong ứng dụng Spring

**Tình huống 1 — CRUD đơn giản có vài tham số, không NULL mơ hồ:** dùng `JdbcTemplate.update(sql, values...)`. Code gọn, ít lỗi quản lý tài nguyên.

**Tình huống 2 — Có nhiều placeholder hoặc nhiều điều kiện:** dùng `NamedParameterJdbcTemplate` và `MapSqlParameterSource`, giúp đọc SQL dễ hơn, nhất là khi các tham số cùng kiểu và dễ đổi thứ tự.

**Tình huống 3 — Driver/DB xử lý NULL không ổn định:** chỉ rõ SQL type bằng `SqlParameterValue`, `int[] argTypes`, `MapSqlParameterSource.addValue(name,value,sqlType)` hoặc `PreparedStatement.setNull(index, Types.X)`.

**Tình huống 4 — Cần dùng JDBC setter chuyên biệt:** dùng `PreparedStatementSetter` hoặc `PreparedStatementCreator`, ví dụ set timestamp theo `Calendar`/driver, streaming LOB, generated keys hoặc custom vendor types.

**Tình huống 5 — Cần xử lý hàng loạt:** dùng `JdbcTemplate.batchUpdate`/`BatchPreparedStatementSetter` để bind từng bộ tham số, kiểm tra batch result và transaction. Không giả định batch tự động atomic nếu không có transaction phù hợp.

**Tình huống 6 — Cần stored procedure/advanced behavior:** API `SimpleJdbcCall` hoặc `CallableStatement` với IN/OUT type chính xác; không thay thế mọi trường hợp bằng một `JdbcTemplate.update`.

**Lưu ý:** Lỗi bind thường bộc lộ khi **thực thi** query, không phải lúc Java compile. Exception của driver được Spring dịch thành `DataAccessException`, nhưng vẫn cần hiểu SQLSTATE, vendor error code, parameter index và database schema để sửa nguyên nhân gốc.

## 12. Những lỗi phổ biến và cách tránh

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Ghép `String` người dùng vào SQL | SQL injection, lỗi quoting | Dùng `?`/named params |
| Viết `'?'` thay `?` | Literal dấu hỏi, không có bind marker | Bỏ nháy đơn quanh placeholder |
| Index bắt đầu từ 0 | `SQLException` về index | Tham số JDBC bắt đầu từ 1 |
| Truyền nhầm thứ tự `id`/`status` | Dữ liệu sai hoặc type mismatch | Đối chiếu SQL, SQL types và call site |
| Đẩy số lớn vào `setInt` | Tràn/ngoài miền SQL | Chọn `long`/`BIGINT` đúng yêu cầu |
| Dùng `double` để lưu tiền vào DECIMAL | Sai số/scale | `BigDecimal` từ chuỗi |
| Bỏ qua `wasNull()` sau `getBoolean/getInt` | NULL bị hiểu là false/0 | Dùng wrapper/read null-aware |
| Gọi `setObject(i, null)` ở DB nhạy type | Driver/DB không xác định type | `setNull(i,Types.X)` hoặc Spring typed NULL |
| Lưu `LocalDateTime` như instant UTC | Sai múi giờ khi chuyển đổi | Xác định zone, dùng OffsetDateTime/Instant theo schema |
| Mong TIMESTAMP giữ zone ID | Lệch thời gian/offset bị chuẩn hóa | Kiểm tra kiểu DB và lưu zone ID nếu cần |
| Dùng `Time.valueOf` với nanosecond | Mất sub-second precision | Dùng `setObject(LocalTime)` khi driver/cột hỗ trợ |
| Lưu byte[] vào cột text bằng `new String(bytes)` | Binary bị biến đổi/mất byte | Dùng `VARBINARY`/`BLOB` |
| Log byte array/secret | Lộ dữ liệu nhạy cảm | Chỉ log length/hash an toàn khi cần |
| Dùng `setBytes` cho file rất lớn | Tốn heap, copy buffers | Dùng LOB/streaming có cleanup |
| Bind tên bảng/cột bằng `?` | Không đúng cú pháp SQL | Allowlist identifiers |
| Giả định mọi DB có BOOLEAN | Portability failure | Kiểm tra schema/dialect |
| Bỏ qua độ dài `VARCHAR` và precision `DECIMAL` | Truncate/rounding/reject | Validate domain và integration test |
| Đóng `PreparedStatement` do JdbcTemplate cấp trong callback | Lỗi sử dụng tài nguyên | Để Spring cleanup |
| Tưởng commit tự động sau mỗi setter | Không đúng vòng đời | Bind chỉ đặt value; execute mới chạy SQL; transaction quyết định commit |

## 13. Kiểm thử đủ để tin tưởng round-trip

Một bài test tốt không chỉ assert `update()==1` mà kiểm chứng dữ liệu **sau khi ghi rồi đọc lại**:

1. **String:** tiếng Việt có dấu, ký tự đặc biệt `'`, chuỗi rỗng, giới hạn độ dài, Unicode.
2. **Integer/Long:** 0, âm (nếu nghiệp vụ cho phép), giá trị sát biên của cột; kiểm tra overflow.
3. **BigDecimal:** số nhiều chữ số, scale khác 2, làm tròn và giá trị lớn hơn `DECIMAL(p,s)`.
4. **Boolean:** true/false và SQL NULL nếu cột nullable, đảm bảo NULL không thành false.
5. **DATE:** ngày nhuận, đầu/cuối năm và đúng ngày khi đổi JVM timezone.
6. **TIME:** giây/phần lẻ giây với precision thực tế của DB.
7. **TIMESTAMP:** round-trip LocalDateTime, precision và timezone JVM/session; dùng `Instant` khi dữ liệu là mốc toàn cục.
8. **byte[]:** zero bytes, byte `0x00`/`0xFF`, empty array, độ dài gần giới hạn `VARBINARY`, so khớp bằng `Arrays.equals`.
9. **NULL:** `setNull`/`SqlParameterValue` và named `MapSqlParameterSource` qua cùng DB/driver.
10. **Rollback:** nếu insert nhiều bảng trong một use case, giả lập lỗi giữa chừng và xác nhận transaction bao toàn bộ.

Với H2, happy-path SQL có thể pass nhưng PostgreSQL/Oracle/SQL Server có thể khác ở BOOLEAN, timestamp precision, national characters, NULL type và binary LOB. Hãy ưu tiên integration tests trên database gần production, có thể dùng Testcontainers khi phù hợp.

### Gợi ý assertion thuần Java

```java
byte[] written = { 0x00, 0x01, (byte) 0xFF };
byte[] read = /* rs.getBytes("payload") trong RowMapper */;
boolean exactlySame = java.util.Arrays.equals(written, read);
```

Đoạn trên chỉ là **mã minh họa so sánh**, không phải file độc lập; `read` phải lấy từ JDBC result set còn mở. `Arrays.equals` so sánh **nội dung byte[]**, trong khi `written.equals(read)` mặc định so sánh tham chiếu mảng.

## 14. Các câu hỏi tự kiểm tra có đáp án

**Câu 1:** SQL `WHERE name = ?`, Java `ps.setString(0,"An")`. Sai ở đâu?  
**Đáp án:** JDBC parameter index bắt đầu ở **1**; dùng `setString(1,"An")`.

**Câu 2:** Khi SQL cột `DECIMAL(12,2)` lưu tiền, nên bind `new BigDecimal("0.10")` hay `double 0.1`?  
**Đáp án:** ưu tiên `BigDecimal` từ chuỗi/giá trị thập phân có kiểm soát để không mang sai số binary floating-point.

**Câu 3:** `ResultSet.getBoolean("active")` trả false. Có chắc SQL là FALSE?  
**Đáp án:** không nếu cột nullable; có thể SQL NULL. Gọi `rs.wasNull()` ngay sau getter hoặc đọc theo phương thức nullable phù hợp.

**Câu 4:** `LocalDateTime.of(2026,10,30,9,15)` có tự chỉ ra timezone Việt Nam không?  
**Đáp án:** không. `LocalDateTime` không có zone; muốn mô tả mốc thời gian toàn cục phải gắn zone/offset theo quy tắc nghiệp vụ hoặc dùng `Instant`.

**Câu 5:** Một mảng `{(byte)0xFF}` đọc lại in `[-1]`. Có bị mất byte không?  
**Đáp án:** không. `byte` Java signed nhưng bit-pattern vẫn là FF; dùng hex hoặc `Byte.toUnsignedInt` nếu cần xem 255.

**Câu 6:** Vì sao `UPDATE ... SET nickname = ?` với value `null` đôi lúc báo lỗi driver?  
**Đáp án:** driver/DB có thể cần SQL type. Dùng `setNull(index,Types.VARCHAR)`, `SqlParameterValue(Types.VARCHAR,null)` hoặc named source có `Types.VARCHAR`.

**Câu 7:** `byte[]` có được tự động bind thành SQL array `INTEGER[]` không?  
**Đáp án:** không. `byte[]` thường là binary bytes (`VARBINARY`/`BLOB`); SQL ARRAY là loại khác với driver API riêng.

**Câu 8:** Nếu dùng `JdbcTemplate.update(sql, setter)`, ai đóng prepared statement và connection?  
**Đáp án:** Spring JDBC quản lý cleanup trong lời gọi; callback chỉ bind, không tự đóng các tài nguyên Spring cung cấp.

**Câu 9:** Nếu cần sort theo cột do client chọn, dùng `ORDER BY ?` với `setString` được không?  
**Đáp án:** không. Dấu `?` bind giá trị, không bind identifier/cú pháp. Dùng allowlist tên cột đáng tin.

**Câu 10:** Chạy `ps.setBytes(1, bytes)` có lập tức ghi bytes vào DB không?  
**Đáp án:** không. Setter đặt tham số; khi `executeUpdate`/`execute` mới gửi statement. Commit theo transaction/auto-commit.

## 15. Checklist trước khi merge code bind SQL

- [ ] Dữ liệu động được bind qua `?`/`:name`; identifier động có allowlist.
- [ ] Mọi dấu `?` đủ số lượng, index từ 1 và thứ tự bind khớp SQL.
- [ ] `String` đúng encoding/độ dài, có test Unicode và ký tự nháy.
- [ ] `int/long` không bị thu hẹp, `BigDecimal` khớp precision/scale.
- [ ] `boolean`/`Boolean` xử lý NULL theo schema và domain.
- [ ] `DATE/TIME/TIMESTAMP` được dùng đúng ngữ nghĩa; timezone policy rõ ràng.
- [ ] `byte[]` vào binary column, so khớp nội dung, không tự đổi sang text.
- [ ] Những `null` nhạy type có `Types.X` tường minh.
- [ ] Không rò resource hay đóng nhầm resource do `JdbcTemplate` sở hữu.
- [ ] Có test readback, boundary values và DB driver thực tế.
- [ ] Transaction/use case rõ ràng nếu nhiều câu SQL phải atomic.

## Tài liệu tham khảo chính thức

- Spring Framework — Common Problems with Parameter and Data Value Handling: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring Framework — JDBC Core Classes (`JdbcTemplate`, named params): https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework API — `SqlParameterValue`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/SqlParameterValue.html
- Spring Framework API — `MapSqlParameterSource`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- Java 17 JDBC — `PreparedStatement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- Java 17 JDBC — `ResultSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- H2 Database — Data Types: https://h2database.com/html/datatypes.html
- Spring Boot 3.5.16 release và trạng thái hỗ trợ: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Ghi nhớ:** **SQL template chứa placeholder; `PreparedStatement` hoặc Spring JDBC bind Java value sang JDBC type; database thực thi theo schema.** Với String/numeric/boolean/date-time/binary, chọn kiểu theo **ngữ nghĩa nghiệp vụ**, chú ý **NULL có kiểu, BigDecimal cho tiền, timezone cho thời điểm, VARBINARY cho byte[]** và luôn kiểm thử round-trip bằng DB thật.