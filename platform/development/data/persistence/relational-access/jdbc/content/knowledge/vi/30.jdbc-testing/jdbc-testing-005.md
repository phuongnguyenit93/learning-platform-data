# Kiểm thử NULL, Unicode, số thập phân và thời gian trong JDBC

Trong chương **Kiểm thử JDBC**, một repository không thể được coi là đúng chỉ vì câu `INSERT` chạy thành công và `SELECT` trả về một hàng. Lỗi ánh xạ dữ liệu thường nằm ở những trường hợp không nổi bật trong dữ liệu mẫu: cột SQL `NULL` bị Java hiểu là số `0`, tên tiếng Việt bị thay ký tự, số tiền mất phần thập phân hoặc một thời điểm bị lệch múi giờ.

Ví dụ, ứng dụng ghi `new BigDecimal("123.4500")` vào cột `DECIMAL` rồi đọc bằng `getDouble()`; phép so sánh qua `double` có thể che đi sai số hoặc khác biệt về scale. Một ví dụ khác, ứng dụng đọc `getInt("score")` thấy `0` và kết luận người dùng có điểm bằng không, trong khi cột thực tế là `NULL`. Hai lỗi này có thể không tạo `SQLException` nào.

Bài này xây dựng một chiến lược **kiểm thử round-trip** cho bốn nhóm dữ liệu: **NULL, Unicode, số thập phân chính xác và ngày giờ/múi giờ**. Các ví dụ sử dụng JDBC chuẩn như `Connection`, `PreparedStatement`, `ResultSet`, `Types`, `BigDecimal` và API `java.time`; phần kiểm thử tích hợp minh họa bằng JUnit 5 và PostgreSQL, với những khác biệt driver/DB được nêu rõ để không nhầm một môi trường kiểm thử thành hợp đồng chung của mọi cơ sở dữ liệu.

## 1. Kiểm thử JDBC phải bao phủ cả chiều ghi và chiều đọc

Một trường dữ liệu đi qua nhiều lớp:

```text
Giá trị Java
    |
    v
PreparedStatement.setXxx(...) / setObject(...) / setNull(...)
    |
    v
Driver JDBC  -- chuyển kiểu, mã hóa, giao thức
    |
    v
Cột SQL -- kiểu dữ liệu, precision/scale, NULL, timezone, collation
    |
    v
ResultSet.getXxx(...) / getObject(...) / wasNull()
    |
    v
Giá trị Java sau khi đọc
    |
    v
Assertion: đúng nội dung, kiểu, độ chính xác, ngữ nghĩa?
```

**Round-trip** nghĩa là ghi một giá trị có chủ đích rồi truy vấn lại để so với kết quả mong đợi. Không chỉ so xem “có một hàng”: phải kiểm tra giá trị, trạng thái `NULL`, độ chính xác và các quy tắc chuyển đổi.

| Nhóm | Điều cần chứng minh | Lỗi dễ bỏ sót |
| --- | --- | --- |
| SQL `NULL` | Giá trị thiếu được nhận diện khác `0`, `false` hoặc chuỗi rỗng | Getter nguyên thủy trả giá trị mặc định |
| Unicode | Dữ liệu tiếng Việt, ký tự kết hợp và ký tự ngoài BMP được lưu/đọc theo hợp đồng | Sai encoding, cắt ngắn, chuẩn hóa ngoài ý muốn |
| `DECIMAL`/`NUMERIC` | Giá trị số được giữ chính xác theo precision/scale đã định | Dùng `double`, làm tròn ngầm, so `BigDecimal.equals` sai ý nghĩa |
| Date/time | Ngày giờ địa phương và thời điểm tuyệt đối được ánh xạ đúng | Áp timezone mặc định, lệch DST, mất phần nano giây |

Trước khi viết test, xác định **hợp đồng mong đợi**: hệ thống cần giữ nguyên chuỗi Unicode từng code point hay chỉ tương đương sau chuẩn hóa? Với số tiền, scale bắt buộc là 2 hay 4? Với thời gian, giá trị là *giờ trên đồng hồ ở một địa phương* hay *một thời điểm tuyệt đối trên trục UTC*? Không có các quy tắc này, assertion dễ sai hoặc bỏ qua lỗi thật.

## 2. Tách unit test, integration test và kiểm thử khả chuyển

Không phải mọi lỗi có thể phát hiện bằng mock `ResultSet`:

| Tầng kiểm thử | Phù hợp kiểm tra | Điều không chứng minh được |
| --- | --- | --- |
| Unit test với đối tượng giả/mocks | Mapping Java, cách xử lý `null`, validate đầu vào, chọn getter/setter | Cách driver mã hóa dữ liệu và kiểu cột DB thật |
| Integration test trên DB thật | Ghi/đọc, constraints, precision/scale, charset, timezone, SQLState | Tính khả chuyển sang DB khác nếu chỉ chạy một driver |
| Contract/compatibility test trên từng DB/driver | Hợp đồng API xuyên nhiều phiên bản và cấu hình | Không tự thay thế kiểm thử tải, concurrency hoặc bảo mật |
| Kiểm thử end-to-end | HTTP → service → JDBC → DB → response | Khó cô lập nguyên nhân nếu không có test ở tầng thấp |

Một DB in-memory có thể hữu ích cho test nhanh, nhưng **không mặc nhiên mô phỏng chính xác PostgreSQL, MySQL, SQL Server hoặc Oracle**. Kiểu `TIMESTAMP WITH TIME ZONE`, quy tắc `NUMERIC`, cách so sánh Unicode và SQLState có thể khác nhau. Những test xác nhận chuyển kiểu quan trọng nên chạy trên **cùng loại DB và driver** mà production sử dụng; có thể dùng database thử nghiệm được khởi tạo riêng hoặc container DB trong pipeline nếu môi trường cho phép.

Nguyên tắc thiết kế fixture:

- Dùng dữ liệu thử nghiệm **cô lập**, không đọc hoặc sửa tài khoản production.
- Chỉ ghi giá trị đã biết; không phụ thuộc vào đồng hồ hệ thống, thứ tự không xác định hoặc bảng do test khác thay đổi.
- Ưu tiên giao dịch có `rollback()` hoặc schema/database dùng riêng cho test; cẩn trọng DDL có tự commit hay không tùy DB.
- Nếu test dùng connection pool, xác định ai sở hữu transaction và ai đóng `Connection`; không để kết nối hoặc transaction bị giữ sau assertion thất bại.
- Ghi nhận tên DB, driver, phiên bản và timezone trong kết quả kiểm thử khi những yếu tố đó ảnh hưởng kết quả.

## 3. SQL `NULL` không giống giá trị mặc định của Java

`NULL` trong SQL biểu thị **giá trị không xác định/không có giá trị**, không phải số 0, chuỗi `""` hay boolean `false`. Getter JDBC trả kiểu tham chiếu thường trả Java `null` cho SQL `NULL`; getter kiểu nguyên thủy trả giá trị Java mặc định, nên phải hỏi `wasNull()`.

Ví dụ đọc cột có thể `NULL`:

```java
int score = rs.getInt("score");
boolean scoreWasNull = rs.wasNull(); // Phải gọi ngay sau getter đó.

if (scoreWasNull) {
    System.out.println("Chưa có điểm");
} else {
    System.out.println("Điểm: " + score); // Có thể bằng 0 thật.
}
```

**Đặc biệt:** `wasNull()` phản ánh **giá trị của lần gọi getter gần nhất trên `ResultSet`**. Nếu giữa `getInt("score")` và `wasNull()` có lời gọi `getString("name")`, kết quả `wasNull()` sẽ nói về `name`, không còn nói về `score`.

### Ghi `NULL` một cách có kiểu

```java
String sql = "INSERT INTO probe (id, score, note) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 10L);
    ps.setNull(2, java.sql.Types.INTEGER);
    ps.setNull(3, java.sql.Types.VARCHAR);
    ps.executeUpdate();
}
```

`setNull(index, sqlType)` cho driver biết kiểu SQL của tham số `NULL`. Một số driver có thể suy luận kiểu từ `setObject(index, null)`, nhưng không nên phụ thuộc điều đó cho các kiểu khó suy luận. Với kiểu do DB tự định nghĩa, đôi khi cần overload `setNull(index, sqlType, typeName)`.

Khi đọc kiểu tham chiếu, có thể thử:

```java
Integer score = rs.getObject("score", Integer.class);
String note = rs.getString("note");

// Với driver hỗ trợ ánh xạ kiểu đích:
// score == null nếu cột score là SQL NULL.
// note == null nếu cột note là SQL NULL.
```

`getObject(column, Class<T>)` thuộc JDBC chuẩn, nhưng tính khả dụng của từng phép chuyển đổi vẫn tùy driver. Test cần chạy với **đúng driver** trước khi coi đó là đường mapping chính.

### NULL trong điều kiện SQL

`WHERE score = NULL` và `WHERE score = ?` với tham số SQL `NULL` **không** tương đương `WHERE score IS NULL`. Theo logic ba giá trị của SQL, phép `= NULL` thường cho kết quả `UNKNOWN` và không khớp hàng:

```sql
SELECT id FROM probe WHERE score IS NULL; -- Tìm giá trị SQL NULL.

-- Không dùng để tìm NULL:
SELECT id FROM probe WHERE score = NULL;
```

Test phải kiểm tra cả cột `NULL` **và** cột có giá trị mặc định hợp lệ như `0`, `false`, `""`. Nếu chỉ test một trong hai trường hợp, mapper có thể vô tình gộp chúng.

## 4. Unicode: kiểm tra nội dung thật, không chỉ độ dài

Văn bản tiếng Việt có dấu, ký tự ngoài bảng mã ASCII và ký tự emoji đều là dữ liệu hợp lệ của nhiều ứng dụng. Những trường hợp cần kiểm tra gồm:

| Dữ liệu thử | Mục đích |
| --- | --- |
| `"Hà Nội – Đà Nẵng"` | Chữ tiếng Việt có dấu và dấu gạch ngang Unicode |
| `"Tiếng Việt: ă â ê ô ơ ư đ"` | Kiểm tra nhiều ký tự có dấu |
| `"🌏"` | Ký tự ngoài BMP, dùng hai `char` UTF-16 trong Java |
| `"é"` và `"e\u0301"` | Ký tự dựng sẵn và chuỗi dùng dấu kết hợp |
| `""` và SQL `NULL` | Phân biệt chuỗi rỗng với không có dữ liệu |
| Chuỗi dài sát giới hạn cột | Phát hiện cắt ngắn, lỗi length và hành vi của DB |

Java `String` dùng UTF-16. Do đó **`String.length()` đếm số đơn vị mã UTF-16**, không nhất thiết bằng số Unicode code point, số ký tự người dùng nhìn thấy hoặc số byte UTF-8.

```java
import java.nio.charset.StandardCharsets;

String earth = "🌏";
System.out.println(earth.length()); // 2: hai đơn vị mã UTF-16.
System.out.println(
        earth.codePointCount(0, earth.length())); // 1 code point.
System.out.println(
        earth.getBytes(StandardCharsets.UTF_8).length); // 4 byte UTF-8.
```

Với tổ hợp dấu, hai chuỗi có thể hiển thị gần giống nhau nhưng là các dãy Unicode khác nhau:

```java
import java.text.Normalizer;

String composed = "é";
String decomposed = "e\u0301"; // e + dấu sắc kết hợp.

System.out.println(composed.equals(decomposed)); // false
System.out.println(
        Normalizer.normalize(decomposed, Normalizer.Form.NFC)
                .equals(composed)); // true
```

**Cần xác định mong đợi trước khi assert:**

- Nếu hệ thống lưu **nguyên chuỗi Unicode**, kiểm tra `assertEquals(input, output)` theo từng code point. Đừng tự chuẩn hóa kết quả kiểm thử để che mất việc dữ liệu bị thay đổi ngoài mong đợi.
- Nếu nghiệp vụ chủ đích chuẩn hóa về `NFC`, chuẩn hóa rõ ràng ở ranh giới ứng dụng và kiểm tra kết quả theo hợp đồng ấy.
- Một số collation của DB có thể coi hai chuỗi tương đương khi so sánh hoặc sắp xếp; điều đó **không** đồng nghĩa chuỗi đọc lại chắc chắn có cùng byte hay cùng code point.
- Với chiều dài `VARCHAR(n)`, ý nghĩa của `n` và cách từ chối/truncate khác nhau giữa DB. Không dùng `String.length()` thay cho giới hạn thật của cơ sở dữ liệu.

Với nội dung ký tự, dùng `PreparedStatement.setString(...)` và `ResultSet.getString(...)` cho dữ liệu vừa phải. Các kiểu `CLOB`/`NCLOB` hoặc nội dung lớn có thể cần `Reader` và `getCharacterStream(...)`; phải kiểm tra charset ở ranh giới tệp/HTTP, không mặc định lỗi Unicode luôn xuất phát từ JDBC.

## 5. Số thập phân: `BigDecimal`, precision và scale

Đối với tiền tệ, thuế suất và số lượng cần chính xác, dùng kiểu SQL `DECIMAL(p,s)` hoặc `NUMERIC(p,s)` và Java `BigDecimal` thay vì `float`/`double`.

Ví dụ cột `NUMERIC(18,4)` có **precision** tối đa 18 chữ số và **scale** 4 chữ số sau dấu thập phân. Với giá trị dương thông thường, tối đa 14 chữ số có thể nằm trước dấu thập phân. Quy tắc làm tròn và cách từ chối giá trị vượt giới hạn có thể khác theo DB.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal exact = new BigDecimal("123456789.1200");
BigDecimal fromBinaryFloat = new BigDecimal(0.1);

System.out.println(exact); // 123456789.1200
System.out.println(fromBinaryFloat);
// Không phải đúng 0.1 vì 0.1 không biểu diễn chính xác bằng double.

BigDecimal money = new BigDecimal("15.2300");
BigDecimal fourDigits =
        money.setScale(4, RoundingMode.UNNECESSARY);
```

`new BigDecimal("0.1")` tạo giá trị thập phân chính xác 0.1. `BigDecimal.valueOf(0.1)` dùng biểu diễn chuỗi chuẩn của `double`, thường hợp lý hơn `new BigDecimal(0.1)`, nhưng nếu giá trị đã đi qua các phép tính `double` thì độ chính xác có thể đã mất trước đó.

### So sánh đúng sau round-trip

```java
BigDecimal requested = new BigDecimal("15.2300");
BigDecimal actual = rs.getBigDecimal("amount");

if (actual == null) {
    throw new IllegalStateException("amount không được NULL");
}

// So sánh giá trị số:
boolean sameValue = requested.compareTo(actual) == 0;

// So sánh thêm scale nếu hợp đồng yêu cầu đúng biểu diễn:
boolean sameScale = requested.scale() == actual.scale();
```

Hai đối tượng `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có `compareTo(...) == 0` nhưng `equals(...) == false` vì khác scale. Với test **giá trị số**, thường kiểm tra bằng `compareTo`; khi nghiệp vụ yêu cầu giữ 4 chữ số thập phân, kiểm tra cả `scale()` theo loại cột/driver đã xác nhận.

Đừng chỉ gọi `getDouble("amount")` để kiểm tra dữ liệu `DECIMAL` chính xác. Việc chuyển sang số dấu phẩy động nhị phân có thể làm sai khác giá trị; dùng `getBigDecimal` và xác định phép làm tròn ở tầng Java trước khi ghi.

### Biên cần kiểm thử

Với một cột `NUMERIC(18,4)`, thử:

1. `0.0000`, số âm và số dương.
2. `123456789.1200` để kiểm tra chữ số có nghĩa và scale.
3. Giá trị sát giới hạn precision/scale, chẳng hạn `99999999999999.9999` nếu kiểu và DB cho phép.
4. Giá trị có **nhiều hơn bốn** chữ số sau dấu thập phân; xác định DB từ chối hay làm tròn, không đoán.
5. Giá trị vượt số chữ số phần nguyên mà cột chứa được.
6. SQL `NULL` nếu cột cho phép, và `0.0000` để bảo đảm không gộp hai trạng thái.

Khi test lỗi, không hard-code mọi DB phải trả cùng SQLState hoặc cùng thông điệp. Nếu muốn **từ chối làm tròn ngầm** ở tầng ứng dụng, có thể kiểm tra `setScale(4, RoundingMode.UNNECESSARY)` trước khi bind.

## 6. Ngày giờ: test phải phân biệt “giờ địa phương” và “thời điểm”

Các kiểu Java trong `java.time` mang ý nghĩa khác nhau:

| Kiểu Java | Ý nghĩa | Kiểu SQL thường ánh xạ |
| --- | --- | --- |
| `LocalDate` | Ngày theo lịch, không có giờ/timezone | `DATE` |
| `LocalTime` | Giờ trong ngày, không có ngày/timezone | `TIME WITHOUT TIME ZONE` hoặc `TIME` |
| `LocalDateTime` | Ngày và giờ *trên đồng hồ*, không có timezone/offset | `TIMESTAMP WITHOUT TIME ZONE` |
| `OffsetDateTime` | Ngày giờ có offset, xác định được một thời điểm | `TIMESTAMP WITH TIME ZONE` trên driver hỗ trợ |
| `Instant` | Một thời điểm tuyệt đối tính từ epoch | Không có ánh xạ `getObject(..., Instant.class)` phổ quát được JDBC 4.2 đảm bảo |

Ví dụ `2026-11-17T09:00:00` kiểu `LocalDateTime` **không xác định một thời điểm UTC duy nhất** cho đến khi gắn timezone/offset. Trái lại, `2026-11-17T09:00:00+07:00` kiểu `OffsetDateTime` tương ứng với `2026-11-17T02:00:00Z`.

```java
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

LocalDateTime wallClock = LocalDateTime.of(
        2026, 11, 17, 9, 0, 0);
OffsetDateTime timestamp = OffsetDateTime.of(
        2026, 11, 17, 9, 0, 0, 0, ZoneOffset.ofHours(7));

System.out.println(wallClock);       // 2026-11-17T09:00
System.out.println(timestamp.toInstant()); // 2026-11-17T02:00:00Z
```

### Kiểm thử `TIMESTAMP` và `TIMESTAMP WITH TIME ZONE`

- Với **`TIMESTAMP WITHOUT TIME ZONE`**, test rằng `LocalDateTime` đọc lại có cùng **các trường ngày, giờ, phút, giây** trong giới hạn độ chính xác cột.
- Với **`TIMESTAMP WITH TIME ZONE`**, test **thời điểm tuyệt đối** bằng `toInstant()` thay vì buộc `OffsetDateTime.getOffset()` phải giống lúc ghi. PostgreSQL `timestamptz` chẳng hạn không giữ riêng offset gốc; driver có thể trả thời điểm được chuẩn hóa về UTC.
- Chọn độ chính xác thời gian cụ thể. Một cột `TIMESTAMP(6)` thường biểu diễn tới micro giây; Java `LocalDateTime`/`OffsetDateTime` có nano giây. Đừng assert giữ đủ 9 chữ số nano giây trên cột chỉ hỗ trợ 6 chữ số.
- Không dùng `LocalDateTime` như đại diện thời điểm tuyệt đối chỉ vì JVM hiện đặt timezone UTC.

Ví dụ JDBC 4.2:

```java
ps.setObject(1, wallClock);
ps.setObject(2, timestamp);

LocalDateTime loadedLocal =
        rs.getObject("event_local", LocalDateTime.class);
OffsetDateTime loadedAbsolute =
        rs.getObject("event_absolute", OffsetDateTime.class);

boolean sameLocalFields = wallClock.equals(loadedLocal);
boolean sameInstant =
        timestamp.toInstant().equals(loadedAbsolute.toInstant());
```

Đoạn mã giả định `ps` và `rs` có cột/tham số phù hợp và driver hỗ trợ phép ánh xạ. Với driver cũ, có thể phải dùng `java.sql.Timestamp` và overload nhận `Calendar` theo hợp đồng DB, nhưng phải kiểm soát timezone rõ ràng: `Timestamp` đi qua timezone mặc định hoặc `Calendar` khác nhau có thể làm thay đổi cách diễn giải.

### Giờ mùa hè và timezone mặc định

Với múi giờ có daylight saving time (DST), không phải mọi giờ địa phương đều tồn tại đúng một lần. Ví dụ `America/New_York` có giai đoạn chuyển sang giờ mùa hè làm một số giờ bị bỏ qua, và giai đoạn quay lại khiến một số giờ xuất hiện hai lần.

```java
import java.time.LocalDateTime;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);

int validOffsets = zone.getRules().getValidOffsets(gap).size();
System.out.println(validOffsets); // 0 với quy tắc DST ở ngày ví dụ.
```

Ứng dụng phải định nghĩa cách xử lý thời điểm không tồn tại hoặc không duy nhất trước khi biến giờ địa phương thành `Instant`. Một test dùng timezone của máy developer sẽ không đủ; hãy có test đặt timezone JVM/DB session theo cấu hình xác định và chọn trường hợp cận DST khi nghiệp vụ liên quan.

## 7. Ví dụ tích hợp đầy đủ: JUnit 5 + JDBC trên PostgreSQL

Mẫu này dùng **PostgreSQL thực** trong môi trường test và tạo **temporary table trên cùng `Connection`** để tránh làm bẩn dữ liệu chung. DDL `TIMESTAMP(6)`/`TIMESTAMPTZ(6)`, `CREATE TEMP TABLE ... ON COMMIT DROP` là **cú pháp PostgreSQL**, không phải SQL khả chuyển cho mọi DB.

Phụ thuộc kiểm thử cần có: **JUnit Jupiter (JUnit 5)** và **PostgreSQL JDBC Driver**. Các biến môi trường `JDBC_TEST_URL`, `JDBC_TEST_USER` và `JDBC_TEST_PASSWORD` phải trỏ đến **database thử nghiệm cô lập**, không trỏ tới production. Code dùng `DriverManager` để tự chứa; trong dự án có `DataSource`/pool kiểm thử có thể thay lời gọi tạo connection bằng `testDataSource.getConnection()` mà không thay nội dung assertion.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Types;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Objects;
import org.junit.jupiter.api.Test;

class JdbcValueIntegrationTest {

    private static Connection openTestConnection() throws SQLException {
        String url = Objects.requireNonNull(
                System.getenv("JDBC_TEST_URL"), "Thiếu JDBC_TEST_URL");
        String user = Objects.requireNonNull(
                System.getenv("JDBC_TEST_USER"), "Thiếu JDBC_TEST_USER");
        String password = Objects.requireNonNull(
                System.getenv("JDBC_TEST_PASSWORD"),
                "Thiếu JDBC_TEST_PASSWORD");

        if (!url.startsWith("jdbc:postgresql:")) {
            throw new IllegalArgumentException(
                    "Test này chỉ dành cho PostgreSQL");
        }
        return DriverManager.getConnection(url, user, password);
    }

    @Test
    void roundTripNullUnicodeDecimalAndTime() throws SQLException {
        String unicode = "Tiếng Việt – Hà Nội 🌏 e\u0301";
        BigDecimal exact = new BigDecimal("123456789.1200");
        LocalDateTime local = LocalDateTime.of(
                2026, 11, 17, 9, 15, 30, 123_456_000);
        OffsetDateTime absolute = OffsetDateTime.of(
                2026, 11, 17, 9, 15, 30, 123_456_000,
                ZoneOffset.ofHours(7));

        try (Connection connection = openTestConnection()) {
            // Không chấp nhận kết nối đang tham gia transaction khác.
            assertTrue(connection.getAutoCommit());
            connection.setAutoCommit(false);
            try {
                try (Statement ddl = connection.createStatement()) {
                    ddl.execute("""
                            CREATE TEMP TABLE jdbc_value_probe (
                                id BIGINT PRIMARY KEY,
                                nullable_number INTEGER,
                                nullable_text VARCHAR(100),
                                display_name VARCHAR(200) NOT NULL,
                                amount NUMERIC(18,4) NOT NULL,
                                event_local TIMESTAMP(6) WITHOUT TIME ZONE NOT NULL,
                                event_absolute TIMESTAMP(6) WITH TIME ZONE NOT NULL
                            ) ON COMMIT DROP
                            """);
                }

                String insert = """
                        INSERT INTO jdbc_value_probe (
                            id, nullable_number, nullable_text, display_name,
                            amount, event_local, event_absolute
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """;
                try (PreparedStatement ps =
                        connection.prepareStatement(insert)) {
                    ps.setLong(1, 42L);
                    ps.setNull(2, Types.INTEGER);
                    ps.setNull(3, Types.VARCHAR);
                    ps.setString(4, unicode);
                    ps.setBigDecimal(5, exact);
                    ps.setObject(6, local);
                    ps.setObject(7, absolute);
                    assertEquals(1, ps.executeUpdate());
                }

                try (PreparedStatement ps = connection.prepareStatement(
                        """
                        SELECT id, nullable_number, nullable_text,
                               display_name, amount, event_local,
                               event_absolute
                        FROM jdbc_value_probe
                        WHERE id = ?
                        """)) {
                    ps.setLong(1, 42L);

                    try (ResultSet rs = ps.executeQuery()) {
                        assertTrue(rs.next());
                        assertEquals(42L, rs.getLong("id"));

                        int missingNumber = rs.getInt("nullable_number");
                        assertEquals(0, missingNumber);
                        assertTrue(rs.wasNull()); // Ngay sau getInt.

                        assertNull(rs.getString("nullable_text"));
                        assertEquals(unicode, rs.getString("display_name"));

                        BigDecimal actual = rs.getBigDecimal("amount");
                        assertNotNull(actual);
                        assertEquals(0, exact.compareTo(actual));

                        LocalDateTime loadedLocal = rs.getObject(
                                "event_local", LocalDateTime.class);
                        assertEquals(local, loadedLocal);

                        OffsetDateTime loadedAbsolute = rs.getObject(
                                "event_absolute", OffsetDateTime.class);
                        assertNotNull(loadedAbsolute);
                        assertEquals(absolute.toInstant(),
                                loadedAbsolute.toInstant());

                        assertFalse(rs.next());
                    }
                }
            } finally {
                // Dọn dữ liệu thử kể cả khi assertion thất bại.
                // PostgreSQL hỗ trợ rollback DDL temporary table ở đây.
                connection.rollback();
            }
        }
    }
}
```

Đoạn test cố ý kiểm tra **bốn loại dữ liệu trong một vòng ghi/đọc**, nhưng một bộ kiểm thử thực tế nên tách thêm các ca biên độc lập để khi thất bại dễ biết nhóm nào gây lỗi. `TIMESTAMP(6)` dùng giá trị nano giây bội số của 1.000, tránh giả định DB lưu được nano giây đến chữ số thứ chín.

**Một điểm cần nhớ về PostgreSQL:** `TIMESTAMP WITH TIME ZONE` được dùng để lưu một thời điểm, không phải offset gốc. Assertion so `toInstant()` là kiểm tra có ý nghĩa; assert rằng offset sau đọc luôn bằng `+07:00` là sai hợp đồng đối với PostgreSQL.

Vì table và các thay đổi đều nằm trong cùng transaction, `rollback()` dọn dữ liệu thử. Với DB khác, DDL có thể tự commit hoặc temporary table có vòng đời khác; cần thay thiết kế fixture. Không dùng tài khoản của hệ thống thực để chạy bài kiểm thử này.

## 8. Bổ sung các ca âm và ca biên mà round-trip cơ bản chưa bắt được

### NULL: kiểm tra giá trị có thật và giá trị không có

Một test tốt cần tạo hai hàng:

- Hàng A: `score IS NULL`.
- Hàng B: `score = 0`.

Sau `SELECT`, hãy assert hàng A có `getInt(...) == 0` **và** `wasNull() == true`, còn hàng B có `getInt(...) == 0` **và** `wasNull() == false`. Kiểm tra cả `getObject(..., Integer.class)` nếu driver hỗ trợ, đồng thời thử câu `WHERE score IS NULL` để xác nhận điều kiện SQL.

Nếu cột `NOT NULL`, thử gán `setNull(...)` và mong đợi thao tác bị từ chối. Nhưng đừng coi **mọi `SQLException`** đều chứng minh ràng buộc hoạt động; cần phân loại nguyên nhân (SQLState/vendor code) và kiểm tra dữ liệu không bị ghi một phần.

### Unicode: kiểm tra chữ có dấu, emoji và giới hạn độ dài

Nên có dữ liệu riêng cho `"é"` và `"e\u0301"`. Nếu hợp đồng là giữ nguyên Unicode, so dữ liệu đọc lại với đầu vào bằng `assertEquals` thay vì tự chuẩn hóa cả hai. Nếu hợp đồng yêu cầu NFC, chủ động chuẩn hóa trước `setString` và kiểm tra:

```java
import java.text.Normalizer;

String input = "e\u0301";
String normalized = Normalizer.normalize(
        input, Normalizer.Form.NFC);
ps.setString(1, normalized);
```

Không coi việc `ORDER BY` hoặc `WHERE name = ?` so khớp hai biểu diễn là bằng chứng DB đã lưu cùng một dãy ký tự. Collation, case-folding và chuẩn hóa là những cơ chế khác nhau.

Với dữ liệu vượt chiều dài cột, kiểm tra DB **báo lỗi, từ chối hoặc cắt** thế nào theo kiểu/driver đã chọn. Tránh viết test khẳng định mọi DB sẽ tự cắt chuỗi hoặc mọi DB luôn ném lỗi giống nhau.

### Decimal: kiểm tra lỗi precision và chính sách rounding

Với `NUMERIC(18,4)`, thử một giá trị vượt giới hạn phần nguyên trong test cô lập. Nếu DB từ chối, assertion nên xác minh không có hàng nào được commit. Thử giá trị có nhiều hơn bốn chữ số sau dấu thập phân và ghi nhận chính sách làm tròn của DB; nếu nghiệp vụ không cho làm tròn, xác thực đầu vào trước:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal submitted = new BigDecimal("12.34567");

// Nếu cần tối đa 4 chữ số sau dấu phẩy và cấm làm tròn:
try {
    submitted.setScale(4, RoundingMode.UNNECESSARY);
    throw new AssertionError("Đáng lẽ phải từ chối dư chữ số");
} catch (ArithmeticException expected) {
    // Đúng: cần làm tròn mới giảm được scale xuống 4.
}
```

Trong JUnit 5, có thể viết gọn bằng `assertThrows(ArithmeticException.class, ...)`. Không dựa vào việc DB tự làm tròn đúng chính sách nghiệp vụ nếu chưa thống nhất quy tắc đó.

### Thời gian: precision, timezone và DST

Thử riêng:

1. `DATE` với `LocalDate`, kể cả ngày nhuận hợp lệ.
2. `TIME` với `LocalTime`; chú ý độ chính xác phần giây.
3. `TIMESTAMP WITHOUT TIME ZONE` với `LocalDateTime`, giữ nguyên các trường wall-clock.
4. `TIMESTAMP WITH TIME ZONE` với `OffsetDateTime`, kiểm tra `Instant`.
5. Hai giá trị `OffsetDateTime` khác offset nhưng cùng `Instant`; nếu DB lưu thời điểm tuyệt đối, kiểm tra chúng truy vấn ra cùng thời điểm.
6. Giá trị có nano giây không chia hết cho 1.000 trên cột chỉ hỗ trợ micro giây: xác định quy tắc làm tròn hoặc cắt và assert theo DB đích.
7. DST gap/overlap trong múi giờ nghiệp vụ; không giả định mọi `LocalDateTime` ánh xạ ra duy nhất một `Instant`.

Nếu ứng dụng dùng `java.sql.Timestamp`, `java.sql.Date` hoặc `Calendar` vì API cũ, cần một nhóm test tương thích riêng. `Calendar` truyền vào `setTimestamp(index, timestamp, calendar)` và `getTimestamp(index, calendar)` điều khiển phép chuyển đổi theo múi giờ lịch; cách driver/DB ánh xạ phải được kiểm tra. Không trộn lẫn một getter mặc định timezone JVM với setter dùng `Calendar` khác múi giờ rồi kết luận dữ liệu DB lỗi.

## 9. Khi test lỗi SQL, chú ý transaction và trạng thái connection

Trong JDBC, việc `executeUpdate()` ném `SQLException` không tự chứng minh transaction đã rollback. Đặc biệt với PostgreSQL, một lỗi SQL bên trong transaction có thể khiến transaction ở trạng thái lỗi cho đến khi rollback; test không được tiếp tục query trên cùng transaction như thể chưa có chuyện gì.

Mẫu xác minh lỗi trong transaction do test sở hữu:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        // 1. Tạo dữ liệu hợp lệ.
        // 2. Chạy thao tác cố tình vi phạm constraint.
        // 3. Kiểm tra loại exception theo DB/driver.
    } finally {
        connection.rollback();
    }
}
```

`dataSource` ở đây là nguồn kết nối kiểm thử đã cấu hình trước. Nếu có transaction manager của framework, hãy để **tầng sở hữu transaction** quyết định rollback và đóng connection; không tự thay đổi `autoCommit` của kết nối đang tham gia giao dịch do framework quản lý.

Với test phát sinh nhiều lỗi cần kiểm chứng độc lập, dùng mỗi ca trên một transaction/connection mới hoặc thiết kế savepoint nếu DB hỗ trợ và test thật sự cần. Không ẩn lỗi chính bằng cách bỏ qua `SQLException` từ `rollback()`/`close()`; công cụ kiểm thử nên báo được cả lỗi cleanup.

### Vì sao không nên test bằng cách nuốt mọi exception?

```java
// SAI: test có thể pass vì mất kết nối, lỗi cú pháp hoặc thiếu quyền.
try {
    ps.executeUpdate();
} catch (SQLException ignored) {
    // Không xác nhận được ràng buộc cần kiểm tra.
}
```

Thay vào đó, assert **loại lỗi, SQLState/vendor code theo DB** hoặc kiểm tra thông điệp bằng quy tắc được kiểm soát, rồi xác minh trạng thái dữ liệu. Đừng dùng đúng một chuỗi `getMessage()` làm tiêu chí khả chuyển, vì thông điệp có thể thay đổi theo phiên bản hoặc ngôn ngữ DB.

## 10. Ma trận kiểm thử theo driver, DB và cấu hình

Khi ứng dụng hỗ trợ nhiều hệ quản trị, ma trận nên bao gồm:

| Chiều thử | Giá trị nên thử | Câu hỏi cần trả lời |
| --- | --- | --- |
| JDBC driver | Phiên bản hiện tại và phiên bản định nâng cấp | Cách ánh xạ `getObject`/`setObject` có thay đổi không? |
| Kiểu cột nullable | INTEGER, VARCHAR, DECIMAL, TIMESTAMP | `getXxx`/`wasNull` có phân biệt SQL `NULL` không? |
| Charset và Unicode | Tiếng Việt, emoji, ký tự kết hợp, chuỗi rỗng | Có mất ký tự, chuẩn hóa hoặc cắt dữ liệu không? |
| Precision/scale | `DECIMAL(18,4)` và giá trị biên | Có làm tròn, overflow hoặc trả scale khác không? |
| Kiểu thời gian | `DATE`, `TIME`, `TIMESTAMP`, kiểu có timezone | Local/absolute time có được giữ đúng ngữ nghĩa không? |
| Timezone JVM | UTC, `Asia/Ho_Chi_Minh`, múi giờ có DST | Có phụ thuộc timezone mặc định ngoài ý muốn không? |
| DB session timezone | UTC và timezone khác, nếu DB hỗ trợ | `TIMESTAMP WITH TIME ZONE` đọc lại có cùng instant không? |
| Chế độ kết nối | `autoCommit=true/false` và DataSource/pool | Dọn dữ liệu/rollback có đúng không? |
| SQL NULL và giá trị rỗng | `NULL`, `0`, `""` | Ứng dụng có trộn các trạng thái không? |

Để giải thích một test thất bại, ghi nhận các thông tin tối thiểu:

```java
var meta = connection.getMetaData();

System.out.println(meta.getDatabaseProductName());
System.out.println(meta.getDatabaseProductVersion());
System.out.println(meta.getDriverName());
System.out.println(meta.getDriverVersion());
System.out.println(connection.getTransactionIsolation());
```

Không log password, nội dung khách hàng thật hay chuỗi kết nối chứa bí mật. Nếu cần báo timezone JVM, lấy qua `ZoneId.systemDefault()`; session timezone phải truy vấn theo cú pháp DB đích. **Kết quả test phụ thuộc môi trường** cần được lưu cùng version và cấu hình để có thể tái hiện.

## 11. Những lỗi thiết kế test thường gặp

| Sai lầm | Vì sao gây kết luận sai | Cách sửa |
| --- | --- | --- |
| Chỉ test với chuỗi ASCII | Không phát hiện lỗi Unicode | Thêm tiếng Việt có dấu, emoji, combining marks |
| Dùng `getInt` nhưng không gọi `wasNull` | SQL `NULL` bị hiểu thành 0 | Kiểm tra `wasNull` ngay sau getter |
| Dùng `getDouble` cho cột tiền | Có thể mất độ chính xác | Dùng `BigDecimal` và `compareTo` |
| Assert `BigDecimal.equals` khi chỉ cần bằng nhau về số | Scale khác làm fail dù số bằng nhau | So `compareTo`; kiểm tra scale riêng nếu cần |
| Test timestamp mà không định nghĩa timezone | Kết quả khác giữa máy developer và CI | Dùng kiểu phù hợp, cấu hình timezone tường minh |
| Assert offset đọc lại phải bằng offset ban đầu của `timestamptz` | DB có thể chỉ lưu instant | So `toInstant` |
| Test nanosecond trên cột có độ chính xác microsecond | Fail vì quy tắc lưu trữ hợp lệ | Chọn precision rõ hoặc assert theo precision cột |
| Dùng DB in-memory để kết luận PostgreSQL/MySQL đúng | Khác kiểu, collation và driver | Chạy integration test với DB mục tiêu |
| Bỏ qua exception trong negative test | Sai nguyên nhân vẫn pass | Kiểm tra SQLState/vendor code và dữ liệu |
| Dùng cùng hàng cố định cho test chạy song song | Test can thiệp lẫn nhau | Temp table, schema/ID riêng và transaction |
| Chỉ kiểm tra `executeUpdate()==1` | Không xác minh giá trị sau lưu | `SELECT` lại và assert round-trip |
| Chạy test bằng tài khoản admin thay vì runtime | Che lỗi permission/cột | Test với quyền production-like |
| Tự động chuẩn hóa kết quả Unicode trong assertion | Có thể che dữ liệu bị thay đổi | Chọn hợp đồng NFC hoặc exact code point rõ ràng |

## 12. Thực hành: mở rộng bộ test round-trip

Với bảng `jdbc_value_probe` của ví dụ tích hợp:

1. Thêm hai hàng cho `nullable_number`: một hàng SQL `NULL`, một hàng `0`; assert `getInt` và `wasNull` khác nhau.
2. Ghi riêng `"é"` và `"e\u0301"`. So với bản gốc và thử chính sách chuẩn hóa `NFC` nếu nghiệp vụ quy định.
3. Thử một ký tự ngoài BMP như `"🌏"`, ghi nhận `String.length()`, `codePointCount(...)` và số byte UTF-8. Kiểm tra dữ liệu round-trip không mất.
4. Ghi `NUMERIC(18,4)` với `0.0000`, `123456789.1200`, số âm và giá trị sát giới hạn; kiểm tra `BigDecimal.compareTo` và `scale()`.
5. Thử số có quá bốn chữ số thập phân; quyết định ứng dụng từ chối, làm tròn có khai báo hay chấp nhận hành vi DB rồi test đúng hợp đồng.
6. Kiểm tra `LocalDateTime` với `TIMESTAMP(6)` và `OffsetDateTime` với kiểu timezone; so wall-clock đối với loại thứ nhất và `Instant` đối với loại thứ hai.
7. Chạy test với timezone JVM khác nhau và DB session timezone khác nhau, nếu hạ tầng test cho phép. Ghi nhận những thay đổi bất ngờ.
8. Thử lỗi constraint trong transaction riêng, xác nhận rollback và không còn hàng thử bị lưu.
9. Chạy lại trên phiên bản driver mới và kiểm tra những trường hợp typed `getObject` không hỗ trợ; ghi rõ fallback đã được kiểm chứng.

**Câu hỏi tự kiểm tra:**

- Tại sao `rs.getInt("score") == 0` không đủ chứng minh điểm bằng 0?
- Vì sao `String.length()` không phải số code point hoặc số byte UTF-8?
- Hai chuỗi `"é"` và `"e\u0301"` có luôn được DB coi bằng nhau khi `WHERE name = ?` không?
- Khi nào phải dùng `BigDecimal.compareTo` thay vì `BigDecimal.equals`?
- Vì sao một `OffsetDateTime` đọc lại từ `TIMESTAMP WITH TIME ZONE` có thể đổi offset nhưng vẫn đúng?
- Phải làm gì khi DB chỉ lưu microsecond nhưng giá trị Java có nanosecond?
- Vì sao test trên driver/DB khác production chưa đủ chứng minh mapper chạy đúng ở production?

**Ghi nhớ:** Kiểm thử JDBC đúng phải **ghi – đọc – so sánh theo ngữ nghĩa của kiểu dữ liệu**. Với SQL `NULL`, kiểm tra `wasNull()` hoặc getter tham chiếu để không nhầm với giá trị mặc định; với Unicode, thử tiếng Việt, emoji và tổ hợp dấu theo hợp đồng chuẩn hóa; với `DECIMAL`, dùng `BigDecimal` và kiểm soát precision/scale; với thời gian, phân biệt `LocalDateTime` với `OffsetDateTime` và so `Instant` khi cần. Dùng fixture cô lập, đóng tài nguyên và rollback rõ ràng, rồi kiểm tra các giả định trên **DB/driver thực** thay vì chỉ dựa vào mock hoặc dữ liệu mẫu đơn giản.
