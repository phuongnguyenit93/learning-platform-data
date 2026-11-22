# Ánh xạ số thập phân, ngày giờ, UUID và dữ liệu lớn

Một ứng dụng Java có thể gửi một khoản tiền `1250.75`, một thời điểm giao dịch `2026-11-14T09:30:00+07:00`, một mã định danh UUID và một tệp đính kèm vài chục megabyte vào database. SQL có kiểu `NUMERIC`, `TIMESTAMP WITH TIME ZONE`, `UUID`, `BLOB` hoặc `BYTEA`; Java có `BigDecimal`, các kiểu `java.time`, `java.util.UUID`, `InputStream` và `Reader`.

Việc ánh xạ giữa hai phía nghe có vẻ đơn giản, nhưng các lỗi thường xuất hiện ở ranh giới:

- Dùng `double` cho tiền làm mất độ chính xác thập phân.
- Lưu một thời điểm có múi giờ vào cột không có múi giờ rồi diễn giải lại sai.
- Đổi UUID thành chuỗi tùy tiện, sai định dạng hoặc sai thứ tự byte.
- Đọc một tệp lớn bằng `getBytes()` rồi giữ toàn bộ trong heap Java.
- Đặt `fetchSize` nhưng tưởng rằng driver đang stream một giá trị BLOB duy nhất.
- Đóng `ResultSet` quá sớm trong khi stream dữ liệu của cột vẫn đang được đọc.

Bài học **“Ánh xạ số thập phân, ngày giờ, UUID và dữ liệu lớn”**, thuộc chương **SQL trong ứng dụng** của module **Database SQL**, hướng dẫn cách chọn kiểu SQL và kiểu Java tương ứng, truyền/đọc dữ liệu qua JDBC, quản lý precision, scale, timezone, binary/text và vòng đời tài nguyên.

Ví dụ chính dùng **Java JDBC và PostgreSQL**. Các bảng so sánh cũng nhắc tới MySQL, SQL Server và Oracle, nhưng cú pháp, driver và hành vi timezone/LOB có thể khác. Hãy kiểm tra phiên bản database và JDBC driver đang dùng trước khi dựa vào một hành vi cụ thể.

> **Nguyên tắc:** Chọn kiểu theo ý nghĩa dữ liệu, không theo cách nó tình cờ hiển thị. Tiền cần kiểu thập phân chính xác; thời điểm cần quy tắc múi giờ; UUID cần định dạng nhất quán; dữ liệu lớn cần truyền theo luồng và có người chịu trách nhiệm đóng tài nguyên.

## 1. Bản đồ ánh xạ giữa SQL và Java

Bảng sau là hướng dẫn thực tế cho JDBC 4.2 trở lên. Mức hỗ trợ cụ thể còn phụ thuộc database và driver:

| Ý nghĩa dữ liệu | Kiểu SQL thường dùng | Kiểu Java nên cân nhắc | JDBC |
|---|---|---|---|
| Số tiền/số thập phân chính xác | `DECIMAL(p,s)` / `NUMERIC(p,s)` | `BigDecimal` | `setBigDecimal`, `getBigDecimal` |
| Số nguyên 32-bit | `INTEGER` | `Integer` / `int` | `setInt`, `getInt` |
| Số nguyên 64-bit | `BIGINT` | `Long` / `long` | `setLong`, `getLong` |
| Ngày lịch | `DATE` | `LocalDate` | `setObject`, `getObject(..., LocalDate.class)` |
| Giờ trong ngày, không múi giờ | `TIME` | `LocalTime` | `setObject`, `getObject(..., LocalTime.class)` |
| Ngày và giờ địa phương, không gắn múi giờ | `TIMESTAMP` | `LocalDateTime` | `setObject`, `getObject(..., LocalDateTime.class)` |
| Thời điểm tuyệt đối có offset | `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` (driver hỗ trợ) | `setObject`, `getObject(..., OffsetDateTime.class)` |
| Định danh 128-bit | PostgreSQL `UUID`; DB khác có kiểu tương đương hoặc binary/text | `UUID` | `setObject`, `getObject(..., UUID.class)` khi driver hỗ trợ |
| Nội dung nhị phân | `BLOB`, PostgreSQL `BYTEA` hoặc Large Object | `byte[]`, `InputStream`, `Blob` | `setBytes`, `setBinaryStream`, `getBinaryStream`, `getBlob` |
| Văn bản lớn | `CLOB`, `NCLOB`, `TEXT` | `String`, `Reader`, `Clob` | `setString`, `setCharacterStream`, `getCharacterStream`, `getClob` |

Không phải mọi kiểu Java đều có một kiểu SQL tương đương tuyệt đối. Ví dụ `ZonedDateTime` giữ tên múi giờ như `Asia/Ho_Chi_Minh`, còn `TIMESTAMPTZ` của PostgreSQL lưu một thời điểm và **không giữ lại tên vùng múi giờ ban đầu**.

### 1.1. Ba lớp phải thống nhất

```text
Ý nghĩa nghiệp vụ
      │
      ▼
Kiểu Java trong domain/application
      │
      ▼
Kiểu JDBC và driver
      │
      ▼
Kiểu SQL và cách database lưu
```

Ví dụ “thời điểm thanh toán” cần được hiểu là một **instant**. Java có thể biểu diễn bằng `Instant` hoặc `OffsetDateTime`; PostgreSQL thường lưu bằng `TIMESTAMPTZ`. Nếu chọn `LocalDateTime` chỉ vì nó tiện, ứng dụng có thể mất thông tin offset cần thiết.

## 2. Số thập phân chính xác: SQL `NUMERIC`/`DECIMAL` và Java `BigDecimal`

Số tiền, thuế, tỷ lệ, số đo cần độ chính xác thập phân thường nên dùng:

```sql
NUMERIC(12, 2)
```

hoặc:

```sql
DECIMAL(12, 2)
```

Trong PostgreSQL, `NUMERIC` và `DECIMAL` là hai tên tương đương cho kiểu số thập phân chính xác.

### 2.1. Precision và scale

Với `NUMERIC(p,s)`:

- `p` (*precision*): tổng số chữ số có nghĩa được lưu.
- `s` (*scale*): số chữ số sau dấu thập phân.

Ví dụ:

```sql
amount NUMERIC(12, 2)
```

cho phép tối đa **12 chữ số**, trong đó **2 chữ số thập phân**. Tức có tối đa 10 chữ số trước dấu thập phân:

```text
9999999999.99
```

Một giá trị vượt phạm vi có thể gây lỗi overflow; giá trị có nhiều chữ số thập phân hơn scale có thể được làm tròn theo quy tắc của database. Nếu nghiệp vụ muốn **từ chối** dữ liệu có quá nhiều chữ số thập phân, phải kiểm tra trước khi ghi, không chỉ trông chờ kiểu cột.

### 2.2. Vì sao Java dùng `BigDecimal`?

`BigDecimal` biểu diễn số thập phân bằng giá trị nguyên không mất chính xác nhị phân như `float`/`double`.

Ví dụ:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

BigDecimal sum = a.add(b);

System.out.println(sum); // 0.3
```

Không nên viết:

```java
BigDecimal wrong = new BigDecimal(0.1);
```

Vì literal `0.1` trước tiên đã là một giá trị `double` xấp xỉ; constructor chuyển chính giá trị nhị phân xấp xỉ đó sang `BigDecimal`, không khôi phục được ý định thập phân ban đầu.

Nếu đầu vào là số thập phân từ người dùng/API, hãy parse từ chuỗi đã xác thực:

```java
BigDecimal amount = new BigDecimal("1250.75");
```

### 2.3. `BigDecimal` là immutable

Các phép toán tạo ra một `BigDecimal` mới:

```java
BigDecimal total = BigDecimal.ZERO;
total.add(new BigDecimal("10.50"));

System.out.println(total); // 0
```

Đoạn trên không cập nhật `total`, vì `add` trả về đối tượng mới. Phải gán lại:

```java
total = total.add(new BigDecimal("10.50"));
```

### 2.4. So sánh `compareTo` và `equals`

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));    // false
System.out.println(x.compareTo(y)); // 0
```

`equals` xét cả giá trị và scale; `compareTo` xét thứ tự số học. Khi muốn kiểm tra hai khoản tiền bằng nhau về mặt số học, thường dùng:

```java
if (x.compareTo(y) == 0) {
    // Bằng nhau về giá trị số.
}
```

Scale vẫn có thể quan trọng với quy tắc lưu/hiển thị, nhưng không nên vô tình biến nó thành điều kiện so sánh nghiệp vụ.

## 3. Quy tắc làm tròn phải được chọn rõ ràng

Giả sử một phép tính cho ra `10.235`, trong khi cột tiền chỉ lưu hai chữ số thập phân.

Java cho phép chỉ định scale và rounding mode:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal raw = new BigDecimal("10.235");

BigDecimal halfUp = raw.setScale(2, RoundingMode.HALF_UP);
BigDecimal halfEven = raw.setScale(2, RoundingMode.HALF_EVEN);

System.out.println(halfUp);   // 10.24
System.out.println(halfEven); // 10.24
```

Ở giá trị đúng điểm giữa khác, `HALF_UP` và `HALF_EVEN` có thể cho kết quả khác:

```java
new BigDecimal("10.245").setScale(2, RoundingMode.HALF_UP);   // 10.25
new BigDecimal("10.245").setScale(2, RoundingMode.HALF_EVEN); // 10.24
```

### 3.1. Một số `RoundingMode`

| Mode | Ý nghĩa tổng quát |
|---|---|
| `UP` | Làm tròn ra xa 0 nếu phải bỏ chữ số khác 0 |
| `DOWN` | Cắt về phía 0 |
| `CEILING` | Hướng về dương vô cùng |
| `FLOOR` | Hướng về âm vô cùng |
| `HALF_UP` | Điểm giữa làm tròn ra xa 0 |
| `HALF_DOWN` | Điểm giữa làm tròn về phía 0 |
| `HALF_EVEN` | Điểm giữa về chữ số chẵn gần nhất |
| `UNNECESSARY` | Nếu phải làm tròn thì ném lỗi |

### 3.2. Từ chối thay vì tự làm tròn

Nếu API yêu cầu số tiền tối đa hai chữ số thập phân và không cho làm tròn:

```java
BigDecimal amount = new BigDecimal("10.235");

BigDecimal normalized = amount.setScale(
    2,
    RoundingMode.UNNECESSARY
);
```

Với `"10.235"`, Java sẽ ném `ArithmeticException` vì cần bỏ thông tin thập phân. Đây là một cách thể hiện rõ chính sách **không chấp nhận làm tròn ngầm**.

### 3.3. Đừng làm tròn ở mọi tầng

Nếu mỗi bước tính thuế, chiết khấu, chia tỷ lệ và cộng tổng đều làm tròn riêng, kết quả cuối có thể khác với việc giữ precision cao rồi làm tròn tại ranh giới nghiệp vụ được quy định.

Hãy ghi rõ:

- Tính toán nội bộ giữ bao nhiêu chữ số?
- Làm tròn theo dòng hay sau khi cộng tổng?
- Dùng `HALF_UP`, `HALF_EVEN` hay quy tắc khác?
- Database hay ứng dụng là nơi quyết định làm tròn cuối?

### 3.4. `NUMERIC(p,s)` không thay thế kiểm tra nghiệp vụ

`NUMERIC(12,2)` không biết một khoản tiền có được âm hay không, có đúng loại tiền hay không, hoặc có vượt hạn mức hợp đồng hay không. Có thể bổ sung:

```sql
amount NUMERIC(12,2) NOT NULL
    CHECK (amount >= 0)
```

Nếu cho phép khoản điều chỉnh âm, quy tắc cần phản ánh đúng mô hình chứ không áp `CHECK` máy móc.

## 4. Ghi và đọc `BigDecimal` bằng JDBC

Ví dụ bảng:

```sql
CREATE TABLE app_invoice_amounts (
    invoice_id BIGINT PRIMARY KEY,
    currency_code CHAR(3) NOT NULL,
    amount NUMERIC(19, 4) NOT NULL
);
```

### 4.1. Ghi bằng `PreparedStatement.setBigDecimal`

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public void insertAmount(
        Connection connection,
        long invoiceId,
        String currencyCode,
        BigDecimal amount) throws SQLException {

    String sql = """
        INSERT INTO app_invoice_amounts
            (invoice_id, currency_code, amount)
        VALUES (?, ?, ?)
        """;

    try (PreparedStatement statement =
            connection.prepareStatement(sql)) {

        statement.setLong(1, invoiceId);
        statement.setString(2, currencyCode);
        statement.setBigDecimal(3, amount);
        statement.executeUpdate();
    }
}
```

Không nối số tiền vào chuỗi SQL. `PreparedStatement` truyền giá trị đúng kiểu và giúp tránh SQL injection.

### 4.2. Đọc bằng `ResultSet.getBigDecimal`

```java
String sql = """
    SELECT invoice_id, currency_code, amount
    FROM app_invoice_amounts
    WHERE invoice_id = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 1001L);

    try (var result = statement.executeQuery()) {
        while (result.next()) {
            long invoiceId = result.getLong("invoice_id");
            String currency = result.getString("currency_code");
            BigDecimal amount = result.getBigDecimal("amount");

            System.out.println(invoiceId + " " + currency + " " + amount);
        }
    }
}
```

`getBigDecimal` trả `BigDecimal`, phù hợp để tiếp tục tính toán chính xác.

### 4.3. SQL NULL và `BigDecimal`

Nếu cột nullable, `getBigDecimal` trả Java `null` khi SQL value là `NULL`:

```java
BigDecimal discount = result.getBigDecimal("discount_amount");

if (discount == null) {
    // Không có discount.
} else {
    // Có một giá trị số cụ thể, có thể là 0.
}
```

Đừng tự đổi `null` thành `BigDecimal.ZERO` nếu nghiệp vụ phân biệt “không biết/không áp dụng” với “bằng 0”.

### 4.4. Đừng dùng `getDouble` cho cột tiền

```java
double amount = result.getDouble("amount");
```

có thể tạo sai số khi tính toán tiếp. Với `NUMERIC`/`DECIMAL`, dùng `getBigDecimal`.

### 4.5. Giá trị SQL NULL cho kiểu Java nguyên thủy

`ResultSet.getInt`, `getLong`, `getBoolean` không trả Java `null`; chúng trả giá trị mặc định tương ứng khi SQL NULL và cần gọi `wasNull()` ngay sau đó để biết:

```java
int count = result.getInt("optional_count");
if (result.wasNull()) {
    // SQL NULL.
} else {
    // Có giá trị count, kể cả 0.
}
```

Với kiểu tham chiếu như `BigDecimal`, `String`, `LocalDate`, `UUID`, có thể nhận Java `null` qua các getter phù hợp.

## 5. Ngày giờ: trước hết phải xác định ý nghĩa

Không có một kiểu ngày giờ duy nhất phù hợp mọi trường hợp. Hãy phân biệt:

1. **Ngày lịch:** sinh nhật, ngày hóa đơn, ngày nghỉ.
2. **Giờ trong ngày:** mở cửa lúc 08:30, không gắn ngày.
3. **Ngày–giờ địa phương:** lịch hẹn lúc 09:00 tại một địa điểm, cần quy tắc vùng thời gian bên ngoài.
4. **Thời điểm tuyệt đối:** lúc thanh toán thực sự xảy ra, cần xác định một instant trên dòng thời gian.

### 5.1. Bản đồ kiểu Java `java.time`

| Ý nghĩa | Java | PostgreSQL |
|---|---|---|
| Ngày lịch | `LocalDate` | `DATE` |
| Giờ địa phương trong ngày | `LocalTime` | `TIME WITHOUT TIME ZONE` |
| Ngày–giờ không có múi | `LocalDateTime` | `TIMESTAMP WITHOUT TIME ZONE` |
| Thời điểm có offset | `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` (`timestamptz`) |
| Thời điểm UTC | `Instant` | Thường lưu trong `timestamptz`, qua chuyển đổi được hỗ trợ |
| Ngày–giờ kèm vùng múi giờ có tên | `ZonedDateTime` | Thường lưu instant và **tên zone riêng** nếu cần khôi phục chính sách |

JDBC 4.2 đưa các kiểu `java.time` vào API `setObject`/`getObject` có kiểu, nhưng **driver phải hỗ trợ** kiểu SQL cụ thể.

### 5.2. `LocalDate` không phải `Instant`

`LocalDate.of(2026, 11, 14)` chỉ có ngày lịch, không có giờ và múi giờ. Không thể tự suy ra một thời điểm tuyệt đối nếu không có thêm giờ và zone.

### 5.3. `LocalDateTime` không có offset

```java
LocalDateTime appointment =
    LocalDateTime.of(2026, 11, 14, 9, 30);
```

Nó nói “09:30 ngày 14/11”, nhưng chưa biết là 09:30 ở đâu. Nếu ứng dụng chạy trên nhiều vùng thời gian, phải tránh tự diễn giải `LocalDateTime` theo múi giờ máy chủ một cách ngầm định.

### 5.4. `OffsetDateTime` có offset

```java
OffsetDateTime paymentTime =
    OffsetDateTime.parse("2026-11-14T09:30:00+07:00");
```

Nó xác định được thời điểm nhờ offset `+07:00`. Offset không phải tên vùng múi giờ: `+07:00` không nói các quy tắc lịch sử/tương lai của `Asia/Ho_Chi_Minh`.

## 6. SQL `DATE`, `TIME`, `TIMESTAMP` và `TIMESTAMPTZ`

### 6.1. `DATE`

```sql
CREATE TABLE app_calendar_entries (
    entry_id BIGINT PRIMARY KEY,
    due_date DATE NOT NULL
);
```

Dùng cho ngày lịch. Không lưu giờ hoặc múi giờ.

### 6.2. `TIME WITHOUT TIME ZONE`

```sql
opening_time TIME NOT NULL
```

Dùng cho giờ địa phương trong ngày, ví dụ cửa hàng mở lúc `08:30`. Nó không chỉ ra ngày cụ thể hoặc một instant.

### 6.3. `TIMESTAMP WITHOUT TIME ZONE`

```sql
scheduled_local TIMESTAMP NOT NULL
```

Lưu trường ngày–giờ không có offset/zone. Phù hợp với thời gian địa phương khi hệ thống có quy ước zone bên ngoài hoặc dữ liệu thực sự không đại diện một instant.

### 6.4. `TIMESTAMP WITH TIME ZONE`

Trong PostgreSQL, viết tắt `TIMESTAMPTZ`:

```sql
occurred_at TIMESTAMPTZ NOT NULL
```

Lưu **thời điểm tuyệt đối**. PostgreSQL chuẩn hóa thời điểm theo UTC nội bộ và hiển thị theo timezone của session. Nó **không lưu nguyên tên vùng zone hoặc offset gốc** đã gửi.

Ví dụ:

```sql
SET TIME ZONE 'UTC';
SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07';

SET TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07';
```

Hai session có thể hiển thị cùng một instant theo dạng giờ khác nhau.

### 6.5. `TIMESTAMP` không đồng nghĩa `TIMESTAMPTZ`

Trong PostgreSQL:

```sql
TIMESTAMP
```

đồng nghĩa `TIMESTAMP WITHOUT TIME ZONE`.

```sql
TIMESTAMP WITH TIME ZONE
```

là một kiểu khác. Không nên dựa vào tên “timestamp” chung chung rồi đoán có lưu offset hay không.

## 7. Ánh xạ `java.time` bằng JDBC 4.2

Ví dụ bảng:

```sql
CREATE TABLE app_scheduled_events (
    event_id BIGINT PRIMARY KEY,
    event_date DATE,
    start_time TIME,
    scheduled_local TIMESTAMP,
    occurred_at TIMESTAMPTZ
);
```

### 7.1. Ghi ngày và giờ

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;

public void insertEvent(
        Connection connection,
        long eventId,
        LocalDate eventDate,
        LocalTime startTime,
        LocalDateTime scheduledLocal,
        OffsetDateTime occurredAt) throws SQLException {

    String sql = """
        INSERT INTO app_scheduled_events
            (event_id, event_date, start_time,
             scheduled_local, occurred_at)
        VALUES (?, ?, ?, ?, ?)
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, eventId);
        statement.setObject(2, eventDate);
        statement.setObject(3, startTime);
        statement.setObject(4, scheduledLocal);
        statement.setObject(5, occurredAt);
        statement.executeUpdate();
    }
}
```

### 7.2. Đọc về kiểu Java

```java
try (PreparedStatement statement = connection.prepareStatement("""
        SELECT event_date, start_time, scheduled_local, occurred_at
        FROM app_scheduled_events
        WHERE event_id = ?
        """)) {

    statement.setLong(1, 1001L);

    try (var result = statement.executeQuery()) {
        if (result.next()) {
            LocalDate eventDate =
                result.getObject("event_date", LocalDate.class);

            LocalTime startTime =
                result.getObject("start_time", LocalTime.class);

            LocalDateTime scheduledLocal =
                result.getObject("scheduled_local", LocalDateTime.class);

            OffsetDateTime occurredAt =
                result.getObject("occurred_at", OffsetDateTime.class);
        }
    }
}
```

### 7.3. Kiểm tra hỗ trợ của driver

`getObject(column, LocalDate.class)` và `setObject(LocalDate)` là hướng JDBC 4.2. Tuy vậy, một driver cũ hoặc DBMS không hỗ trợ kiểu tương ứng có thể từ chối. Hãy kiểm tra phiên bản driver, tài liệu và integration test với database thật.

Với PostgreSQL JDBC driver, `TIMESTAMPTZ` thường được đọc bằng `OffsetDateTime`; giá trị trả về được chuẩn hóa về offset UTC. Driver không giữ lại tên zone gốc của người gửi.

### 7.4. `Instant` qua JDBC

`Instant` là lựa chọn domain rất tốt cho thời điểm tuyệt đối. Nhưng mức hỗ trợ trực tiếp `setObject(Instant)`/`getObject(Instant.class)` không giống nhau giữa các driver. Một cầu nối tương thích phổ biến với JDBC legacy là:

```java
import java.sql.Timestamp;
import java.time.Instant;

Instant instant = Instant.now();
Timestamp timestamp = Timestamp.from(instant);

Instant restored = timestamp.toInstant();
```

Khi dùng `Timestamp` với PostgreSQL, phải hiểu kiểu SQL đích và quy tắc driver/session timezone. Không trộn `Timestamp` đại diện `TIMESTAMP WITHOUT TIME ZONE` với `TIMESTAMPTZ` như thể chúng có cùng ngữ nghĩa.

## 8. Múi giờ, DST và dữ liệu lịch hẹn

Đây là nơi một ánh xạ có thể **chạy thành công nhưng vẫn sai nghiệp vụ**.

### 8.1. Instant và wall-clock time

Ví dụ:

- “Thanh toán xảy ra lúc này” → một **instant**.
- “Cửa hàng mở cửa lúc 09:00 mỗi ngày” → một **local time**.
- “Cuộc hẹn lúc 09:00 tại Hà Nội ngày 14/11” → local date-time cộng **zone `Asia/Ho_Chi_Minh`** nếu muốn diễn giải thành instant.

Không dùng cùng một kiểu SQL chỉ vì cả ba đều có thành phần giờ.

### 8.2. Lưu tên zone nếu cần khôi phục quy tắc

Nếu cần tái hiện lịch theo vùng:

```sql
CREATE TABLE app_local_appointments (
    appointment_id UUID PRIMARY KEY,
    local_start TIMESTAMP NOT NULL,
    zone_id TEXT NOT NULL,
    resolved_instant TIMESTAMPTZ
);
```

`local_start` giữ giờ trên đồng hồ địa phương; `zone_id` giữ `Asia/Ho_Chi_Minh`; `resolved_instant` (nếu cần) lưu thời điểm đã xác định theo quy tắc tại thời điểm lập lịch.

Với vùng có DST, một `LocalDateTime` có thể rơi vào:

- **Gap:** giờ địa phương không tồn tại do đồng hồ nhảy tới.
- **Overlap:** giờ địa phương xuất hiện hai lần do đồng hồ quay lùi.

Ứng dụng phải chọn chính sách xử lý rõ ràng; chỉ lưu `LocalDateTime` không đủ để biết instant nào được chọn trong trường hợp overlap.

### 8.3. `ZoneId` và `ZoneOffset` khác nhau

```java
ZoneOffset.ofHours(7);           // +07:00
ZoneId.of("Asia/Ho_Chi_Minh");   // tên vùng và quy tắc zone
```

`ZoneOffset` là một độ lệch cố định. `ZoneId` có thể tra quy tắc thay đổi theo lịch sử/tương lai.

### 8.4. Đừng dùng timezone mặc định của máy làm hợp đồng

Các đoạn như:

```java
LocalDateTime.now()
```

dựa vào clock mặc định của JVM. Nếu server chuyển vùng hoặc container chạy UTC, giá trị tạo ra có thể khác mong đợi. Với thời điểm tuyệt đối, thường dùng:

```java
Instant.now()
```

và chuyển sang zone hiển thị rõ ràng khi cần.

## 9. Truy vấn thời gian theo khoảng đúng

Khi lọc một ngày hoặc tháng, nên dùng khoảng **nửa mở**:

```sql
WHERE occurred_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-12-01 00:00:00+07'
```

Điều này tránh lỗi phải đoán “thời điểm cuối ngày” có phần microsecond/nanosecond nào.

### 9.1. Tạo ranh giới tháng theo zone nghiệp vụ

Nếu báo cáo theo tháng Việt Nam, tạo hai ranh giới trong `Asia/Ho_Chi_Minh` rồi gửi instant tương ứng, hoặc viết rõ:

```sql
WHERE occurred_at >=
      TIMESTAMP '2026-11-01 00:00:00'
      AT TIME ZONE 'Asia/Ho_Chi_Minh'
  AND occurred_at <
      TIMESTAMP '2026-12-01 00:00:00'
      AT TIME ZONE 'Asia/Ho_Chi_Minh'
```

### 9.2. Tránh bọc cột bằng `DATE()` khi muốn dùng index range

```sql
-- Có thể khó tận dụng index trên occurred_at:
WHERE occurred_at::date = DATE '2026-11-14'
```

Với `TIMESTAMPTZ`, phép cast ngày còn phụ thuộc timezone session. Dùng khoảng nửa mở với ranh giới timezone được xác định thường rõ nghĩa và dễ khai thác index hơn.

### 9.3. Độ chính xác thời gian

Java `Instant` có nano-second precision. PostgreSQL `TIMESTAMP`/`TIMESTAMPTZ` hỗ trợ độ chính xác tối đa đến microsecond (6 chữ số phần giây). Khi ghi từ Java, driver/database có thể phải làm tròn hoặc cắt phần precision vượt mức hỗ trợ. Nếu cần so sánh thời điểm sau khi round-trip, hãy xác định precision lưu trữ và chuẩn hóa ở ứng dụng.

## 10. UUID: ánh xạ `java.util.UUID` với database

UUID là định danh 128-bit, thường biểu diễn thành chuỗi:

```text
550e8400-e29b-41d4-a716-446655440000
```

Java có kiểu:

```java
UUID id = UUID.fromString(
    "550e8400-e29b-41d4-a716-446655440000"
);
```

### 10.1. PostgreSQL có kiểu `UUID`

```sql
CREATE TABLE app_documents (
    document_id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Không cần lưu UUID dưới dạng `VARCHAR(36)` nếu database có kiểu native và ứng dụng/driver hỗ trợ.

### 10.2. Ghi bằng `setObject`

```java
UUID documentId = UUID.randomUUID();

try (PreparedStatement statement = connection.prepareStatement("""
        INSERT INTO app_documents (document_id, title)
        VALUES (?, ?)
        """)) {

    statement.setObject(1, documentId);
    statement.setString(2, "Design notes");
    statement.executeUpdate();
}
```

Với PostgreSQL JDBC driver hiện đại, `UUID` được hỗ trợ trực tiếp cho cột PostgreSQL `uuid`.

### 10.3. Đọc bằng `getObject`

```java
try (PreparedStatement statement = connection.prepareStatement("""
        SELECT document_id, title
        FROM app_documents
        WHERE document_id = ?
        """)) {

    statement.setObject(1, documentId);

    try (var result = statement.executeQuery()) {
        if (result.next()) {
            UUID id = result.getObject("document_id", UUID.class);
            String title = result.getString("title");
        }
    }
}
```

### 10.4. Khi driver không hỗ trợ UUID native

Với database/driver không ánh xạ `UUID` trực tiếp:

```java
statement.setString(1, documentId.toString());
```

và khi đọc:

```java
UUID id = UUID.fromString(result.getString("document_id"));
```

Chỉ dùng cách chuỗi nếu kiểu SQL thực tế là chuỗi tương thích, hoặc database có phép chuyển kiểu được hỗ trợ rõ ràng. Đừng gửi UUID dưới dạng chuỗi vào một cột binary mà không định nghĩa quy tắc encoding.

## 11. UUID ở các DBMS khác nhau

| Database | Kiểu thường gặp | Java |
|---|---|---|
| PostgreSQL | `UUID` | `UUID` |
| SQL Server | `uniqueidentifier` | `UUID` hoặc `String`, tùy driver |
| MySQL | Thường `BINARY(16)` hoặc `CHAR(36)`; phiên bản mới có hàm `UUID_TO_BIN`/`BIN_TO_UUID` | `UUID`, `byte[]` hoặc `String` qua mapping rõ |
| Oracle | Thường `RAW(16)` hoặc `VARCHAR2(36)` theo thiết kế | `UUID`, `byte[]` hoặc `String` |

### 11.1. `CHAR(36)` dễ đọc nhưng tốn chỗ

Chuỗi chuẩn UUID có 36 ký tự (gồm dấu gạch nối). Cách này dễ kiểm tra bằng SQL client nhưng lưu nhiều byte hơn dạng 16-byte binary, và cần thống nhất chữ hoa/thường, canonical format.

### 11.2. `BINARY(16)` tiết kiệm nhưng phải thống nhất thứ tự byte

Khi lưu UUID vào binary, mọi thành phần phải thống nhất:

- Byte order.
- Cách chuyển UUID sang/ra 16 byte.
- Có dùng một phép hoán đổi byte theo phiên bản DB hay không.
- Cách tương thích giữa Java, migration, backup và dịch vụ khác.

Không tự viết `ByteBuffer` đổi thứ tự byte rồi giả định nó khớp với `UUID_TO_BIN(uuid, swap_flag)` của MySQL. Nếu dùng binary, hãy định nghĩa **một chuẩn encoding duy nhất** và kiểm thử round-trip bằng các UUID cố định.

### 11.3. UUID ngẫu nhiên và thứ tự index

`UUID.randomUUID()` thường tạo UUID v4 ngẫu nhiên. Nếu dùng làm khóa chính trên bảng ghi rất lớn, các giá trị ngẫu nhiên có thể làm index phân tán hơn so với khóa tăng tuần tự.

Một số hệ thống dùng UUID có tính sắp xếp theo thời gian như UUID v7 khi thư viện, database và hợp đồng ứng dụng hỗ trợ. Không đổi phiên bản UUID tùy tiện vì nó ảnh hưởng khả năng tương thích, cách sinh và chính sách bảo mật/khả năng đoán.

### 11.4. UUID không phải bí mật hoặc token xác thực tự động

UUID là định danh. Biết một UUID không nên mặc nhiên trao quyền truy cập bản ghi; hệ thống vẫn phải kiểm tra authorization. UUID v4 khó đoán hơn số tăng tuần tự nhưng không thay thế kiểm soát truy cập.

## 12. Dữ liệu lớn: phải phân biệt BLOB, CLOB và tập kết quả lớn

“Dữ liệu lớn” trong JDBC có thể nói về hai bài toán khác nhau:

1. **Một giá trị lớn:** một tệp PDF 80 MB, một ảnh hoặc một nội dung văn bản dài.
2. **Nhiều dòng kết quả:** một truy vấn trả hàng triệu bản ghi nhỏ.

Hai vấn đề này có cơ chế fetch và quản lý bộ nhớ khác nhau.

### 12.1. Kiểu SQL thường gặp

| Loại | PostgreSQL | MySQL | SQL Server | Oracle |
|---|---|---|---|---|
| Binary | `BYTEA`, Large Object (OID) | `BLOB`, `LONGBLOB` | `VARBINARY(MAX)` | `BLOB`, `RAW` tùy kích thước |
| Text lớn | `TEXT` | `TEXT`, `MEDIUMTEXT`, `LONGTEXT` | `VARCHAR(MAX)`, `NVARCHAR(MAX)` | `CLOB`, `NCLOB` |

Tên kiểu chỉ mang tính khái quát; giới hạn kích thước, encoding và cách driver truyền dữ liệu khác nhau.

### 12.2. BLOB và CLOB khác nhau

- **BLOB** (*Binary Large Object*): byte nhị phân, không có giả định encoding ký tự.
- **CLOB** (*Character Large Object*): văn bản, có xử lý theo ký tự/encoding của database.
- **NCLOB**: văn bản theo bộ ký tự quốc gia/Unicode trong các DBMS có kiểu riêng.

Một tệp PDF, ZIP hoặc ảnh là binary. Một tài liệu HTML/JSON/text lớn là character data nếu muốn database xử lý nó như văn bản.

Đừng đọc tệp binary thành `String` bằng charset mặc định; byte có thể bị biến đổi và tệp hỏng.

## 13. PostgreSQL: `BYTEA` và Large Object

PostgreSQL có hai hướng lưu binary thường gặp:

### 13.1. `BYTEA`

```sql
CREATE TABLE app_attachments (
    attachment_id UUID PRIMARY KEY,
    file_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

`BYTEA` lưu chuỗi byte trong một giá trị SQL. PostgreSQL có cơ chế TOAST để xử lý giá trị lớn theo cách nội bộ khi thích hợp.

Với nhiều tệp có kích thước vừa phải và cần transaction/backup cùng bản ghi, `BYTEA` thường là cách đơn giản.

### 13.2. Large Object (LO) dùng OID

PostgreSQL Large Object là một cơ chế riêng, đối tượng được tham chiếu bằng **OID** và thao tác qua API Large Object. Nó phù hợp một số trường hợp tệp rất lớn hoặc cần truy cập theo luồng/vị trí.

Các điểm quan trọng:

- OID trong bảng ứng dụng là **tham chiếu** tới Large Object, không phải nội dung binary.
- Large Object API gắn với transaction; thao tác cần connection/transaction còn hoạt động.
- Khi xóa bản ghi tham chiếu, không mặc định Large Object được xóa tự động. Cần quy trình `lo_unlink`/dọn dẹp để tránh orphan.
- Backup, restore, quyền và migration cần tính cả dữ liệu Large Object.
- PostgreSQL Large Object có giới hạn/chi tiết khác với `BYTEA`; lựa chọn dựa trên kích thước và nhu cầu truy cập thực tế.

### 13.3. Không nhầm `OID` với `BYTEA`

`BYTEA` là nội dung byte. `OID` trong mô hình Large Object là định danh đối tượng lưu ở nơi khác. Chỉ lưu một số OID vào cột không có nghĩa tệp đã được upload thành công hoặc có thể đọc nếu đối tượng LO bị xóa.

### 13.4. Chọn giữa database và object storage

Với tệp ảnh/video rất lớn hoặc cần phân phối qua CDN, object storage có thể phù hợp hơn lưu trực tiếp trong database. Khi đó database lưu metadata như:

```text
attachment_id
object_key
content_type
size_bytes
checksum
created_at
owner_id
```

Phải thiết kế tính nhất quán giữa upload object và ghi metadata: upload thành công nhưng DB thất bại, hoặc DB ghi trước nhưng upload lỗi, đều cần quy trình retry/cleanup. Không coi hai hệ thống ngoài nhau là một transaction SQL duy nhất.

## 14. Ghi binary lớn bằng `setBinaryStream`

Nếu tệp đã có `InputStream`, không nhất thiết phải đọc toàn bộ thành `byte[]` trước khi insert.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.util.UUID;

public void insertAttachment(
        Connection connection,
        UUID attachmentId,
        String fileName,
        String contentType,
        Path file) throws Exception {

    String sql = """
        INSERT INTO app_attachments
            (attachment_id, file_name, content_type, content)
        VALUES (?, ?, ?, ?)
        """;

    long size = Files.size(file);

    try (InputStream input = Files.newInputStream(file);
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setObject(1, attachmentId);
        statement.setString(2, fileName);
        statement.setString(3, contentType);
        statement.setBinaryStream(4, input, size);

        statement.executeUpdate();
    }
}
```

Đây là ví dụ dùng `BYTEA` với PostgreSQL JDBC driver. Hỗ trợ streaming, buffering và overload có length cụ thể có thể khác theo driver; hãy thử với kích thước tệp gần với thực tế.

### 14.1. Tại sao `setBytes` có thể tốn bộ nhớ?

```java
byte[] bytes = Files.readAllBytes(file);
statement.setBytes(4, bytes);
```

`Files.readAllBytes` tạo một mảng chứa **toàn bộ tệp** trong heap. Với nhiều upload đồng thời, bộ nhớ tăng gần theo:

```text
số upload đồng thời × kích thước mỗi tệp
```

`setBinaryStream` cho phép truyền luồng đầu vào, giúp tránh bắt buộc materialize toàn bộ tệp thành `byte[]` ở tầng ứng dụng. Nhưng driver có thể buffer ở nội bộ; không được suy ra rằng mọi driver đều zero-copy hoặc không dùng RAM.

### 14.2. Length và InputStream

JDBC có overload `setBinaryStream(index, stream, long length)` trong các phiên bản JDBC hiện đại. Nếu biết chính xác kích thước, truyền length phù hợp. Nếu stream có độ dài không biết trước, có overload khác nhưng mức hỗ trợ của driver cần được kiểm tra.

Không khai báo length nhỏ hơn dữ liệu thật hoặc lớn hơn lượng dữ liệu có thể đọc; điều này có thể khiến ghi thiếu, lỗi hoặc driver chờ dữ liệu.

### 14.3. Tệp rỗng và NULL khác nhau

- `byte[0]` hoặc stream không có byte: **binary rỗng**.
- SQL `NULL`: không có giá trị binary.

Nếu attachment bắt buộc, dùng `NOT NULL` và kiểm tra size > 0 theo chính sách. Đừng dùng `NULL` làm đại diện cho tệp rỗng trừ khi hợp đồng quy định vậy.

## 15. Đọc binary lớn bằng `getBinaryStream`

Không cần gọi `getBytes` nếu tệp lớn:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.UUID;

public void downloadAttachment(
        Connection connection,
        UUID attachmentId,
        Path destination) throws Exception {

    String sql = """
        SELECT content
        FROM app_attachments
        WHERE attachment_id = ?
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setObject(1, attachmentId);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                throw new IllegalArgumentException("Attachment not found");
            }

            try (InputStream input = result.getBinaryStream("content")) {
                if (input == null) {
                    throw new IllegalStateException("Attachment content is NULL");
                }

                Files.copy(input, destination);
            }
        }
    }
}
```

### 15.1. Vòng đời stream gắn với kết quả/driver

Đọc stream **trước khi đóng `ResultSet` và `Statement`**. Nhiều driver không bảo đảm stream tiếp tục đọc được sau khi result set/connection đã đóng.

Thứ tự đóng trong ví dụ:

```text
InputStream
    ↓ đóng
ResultSet
    ↓ đóng
PreparedStatement
    ↓ đóng
Connection (nếu method sở hữu connection)
```

`try-with-resources` giúp đóng theo thứ tự ngược lại với khai báo.

### 15.2. Không tải hết vào heap nếu không cần

```java
byte[] allBytes = result.getBytes("content");
```

tiện cho tệp nhỏ, nhưng tạo mảng chứa toàn bộ nội dung. Nếu tệp lớn, nhiều người download đồng thời hoặc phải xử lý từng chunk, `getBinaryStream` phù hợp hơn.

### 15.3. Cần kiểm tra path và ghi tệp

Ví dụ trên giả định `destination` do ứng dụng tạo an toàn. Trong ứng dụng thật:

- Không lấy đường dẫn tùy ý từ tên file do người dùng gửi.
- Tránh path traversal (`../`).
- Ghi vào thư mục tạm rồi rename khi tải hoàn tất nếu cần tránh file dở dang.
- Kiểm tra checksum/kích thước khi phù hợp.
- Đóng stream khi có lỗi.

## 16. Văn bản lớn: `TEXT`, CLOB và `Reader`

Với một nội dung văn bản lớn, có thể dùng `TEXT` (PostgreSQL), `CLOB` hoặc kiểu text tương đương:

```sql
CREATE TABLE app_document_text (
    document_id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);
```

### 16.1. Ghi text bằng `setString`

Với văn bản kích thước vừa phải:

```java
statement.setString(1, body);
```

là đủ rõ ràng.

### 16.2. Ghi text lớn bằng `setCharacterStream`

```java
try (java.io.Reader reader =
        Files.newBufferedReader(path, java.nio.charset.StandardCharsets.UTF_8);
     PreparedStatement statement = connection.prepareStatement("""
        INSERT INTO app_document_text (document_id, title, body)
        VALUES (?, ?, ?)
        """)) {

    statement.setObject(1, documentId);
    statement.setString(2, title);
    statement.setCharacterStream(3, reader);
    statement.executeUpdate();
}
```

**Lưu ý:** `Files.size(path)` trả số **byte**, trong khi overload `setCharacterStream` nhận length theo **số ký tự**. Không dùng byte length làm character length cho UTF-8 có ký tự nhiều byte.

Nếu cần truyền length, hãy tính đúng số ký tự theo hợp đồng của API/driver hoặc dùng overload không có length nếu driver hỗ trợ. Ví dụ đơn giản hơn, nếu có thể đọc bằng Reader và không cần length:

```java
statement.setCharacterStream(3, reader);
```

### 16.3. Đọc text lớn bằng `getCharacterStream`

```java
try (PreparedStatement statement = connection.prepareStatement("""
        SELECT body
        FROM app_document_text
        WHERE document_id = ?
        """)) {

    statement.setObject(1, documentId);

    try (ResultSet result = statement.executeQuery()) {
        if (result.next()) {
            try (java.io.Reader reader =
                    result.getCharacterStream("body")) {
                if (reader != null) {
                    try (var writer = Files.newBufferedWriter(
                            destination,
                            java.nio.charset.StandardCharsets.UTF_8)) {
                        char[] buffer = new char[8192];
                        int count;
                        while ((count = reader.read(buffer)) != -1) {
                            writer.write(buffer, 0, count);
                        }
                    }
                }
            }
        }
    }
}
```

`Reader` đọc ký tự, còn `InputStream` đọc byte. Dùng đúng abstraction để tránh tự giải mã/encode sai.

### 16.4. `CLOB` và `TEXT` không phải luôn cùng cách dùng

PostgreSQL `TEXT` là kiểu chuỗi văn bản; JDBC driver có thể expose bằng `String`/`Reader`. DBMS khác có kiểu LOB riêng và API `Clob`/`NClob`. Hãy dùng đúng kiểu driver hỗ trợ thay vì giả định mọi cột `TEXT` phải gọi `getClob`.

## 17. `Blob`, `Clob` và giải phóng LOB

JDBC có interface `Blob` và `Clob` cho dữ liệu LOB:

```java
Blob blob = result.getBlob("content");
```

hoặc:

```java
Clob clob = result.getClob("body");
```

Sau khi sử dụng, có thể cần gọi:

```java
blob.free();
clob.free();
```

### 17.1. Ví dụ đọc Blob

```java
try (PreparedStatement statement = connection.prepareStatement("""
        SELECT content
        FROM app_blob_files
        WHERE file_id = ?
        """)) {

    statement.setObject(1, fileId);

    try (ResultSet result = statement.executeQuery()) {
        if (result.next()) {
            Blob blob = result.getBlob("content");
            if (blob != null) {
                try {
                    try (InputStream input = blob.getBinaryStream()) {
                        Files.copy(input, destination);
                    }
                } finally {
                    blob.free();
                }
            }
        }
    }
}
```

### 17.2. `Blob` không tự bảo đảm streaming hoàn toàn

Driver có thể dùng buffer, dữ liệu tạm hoặc cách triển khai riêng. Để kiểm soát bộ nhớ, cần xem tài liệu driver và đo với tệp thực tế. Dùng `getBinaryStream` thường biểu đạt ý định đọc theo luồng tốt hơn `getBytes`.

### 17.3. `free()` khác `close()`

`Blob`/`Clob` là interface JDBC có phương thức `free()` để giải phóng tài nguyên liên quan. Stream lấy từ LOB có `close()` riêng. Hãy đóng stream và giải phóng LOB theo thứ tự phù hợp với driver.

## 18. `fetchSize` cho nhiều dòng và streaming một cột lớn là hai việc khác nhau

Giả sử query trả 5 triệu bản ghi, mỗi bản ghi có 4 cột nhỏ. Vấn đề chính là **nhiều dòng**.

```java
statement.setFetchSize(500);
```

có thể giúp driver lấy kết quả theo batch trong những điều kiện hỗ trợ.

Ngược lại, một dòng có `content BYTEA` 500 MB là **một giá trị lớn**. `fetchSize=500` không chia giá trị đó thành 500 phần. Cần đọc stream của cột (`getBinaryStream`) hoặc dùng API Large Object phù hợp.

| Vấn đề | Cơ chế cần xem |
|---|---|
| Hàng triệu dòng nhỏ | `fetchSize`, cursor/server-side fetching, paging |
| Một dòng có BLOB lớn | `getBinaryStream`, `setBinaryStream`, LOB API |
| Một dòng có CLOB lớn | `getCharacterStream`, `setCharacterStream`, `Clob` |
| Nhiều BLOB lớn trong nhiều dòng | Kết hợp fetch batch và stream từng giá trị, quản lý tài nguyên chặt |

## 19. Streaming ResultSet bằng PostgreSQL JDBC

Với pgJDBC, một cấu hình phổ biến để driver sử dụng server-side cursor/fetch theo batch là:

- Tắt autocommit (`connection.setAutoCommit(false)`).
- Dùng `TYPE_FORWARD_ONLY`.
- Dùng `CONCUR_READ_ONLY` nếu chỉ đọc.
- Gọi `setFetchSize(n)` với `n > 0`.
- Giữ nguyên connection/transaction trong lúc đọc hết result set.

Ví dụ:

```java
String sql = """
    SELECT invoice_id, amount
    FROM app_invoice_amounts
    ORDER BY invoice_id
    """;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement statement = connection.prepareStatement(
                sql,
                ResultSet.TYPE_FORWARD_ONLY,
                ResultSet.CONCUR_READ_ONLY)) {

            statement.setFetchSize(500);

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    long id = result.getLong("invoice_id");
                    BigDecimal amount = result.getBigDecimal("amount");
                    processInvoice(id, amount);
                }
            }
        }

        connection.commit();
    } catch (Exception failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

### 19.1. `fetchSize` không phải `LIMIT`

`setFetchSize(500)` là gợi ý/cấu hình fetch của JDBC driver; nó không sửa câu SQL thành `LIMIT 500`, không giới hạn tổng số dòng query xử lý và không thay đổi điều kiện lọc.

### 19.2. Transaction dài có chi phí

Muốn tiếp tục fetch qua nhiều batch bằng server-side cursor, transaction phải còn sống. Với kết quả lớn, điều này có thể giữ snapshot và connection lâu. Tránh xử lý chậm hoặc gọi dịch vụ ngoài trong lúc transaction đang mở nếu không cần.

### 19.3. Tương thích driver khác

Các driver MySQL/SQL Server/Oracle có cơ chế fetch, streaming và cấu hình khác. Đừng sao chép điều kiện pgJDBC sang driver khác. Xem tài liệu driver và kiểm chứng bằng metrics/quan sát bộ nhớ.

## 20. Transaction, autocommit và connection pool

JDBC mặc định thường mở connection ở chế độ `autoCommit=true`. Mỗi statement được commit tự động theo quy tắc driver/database.

### 20.1. Transaction quản lý ghi nhiều kiểu dữ liệu cùng nhau

Ví dụ ghi hóa đơn gồm tiền, ngày, UUID và metadata:

```java
connection.setAutoCommit(false);

try {
    // Insert invoice (UUID, BigDecimal, LocalDate...)
    // Insert attachment metadata...
    // Insert audit row...

    connection.commit();
} catch (Exception e) {
    connection.rollback();
    throw e;
}
```

Một transaction có thể đảm bảo các câu ghi SQL cùng commit/rollback. Nhưng nếu ứng dụng upload tệp lên object storage bên ngoài database, transaction SQL **không tự rollback object**. Cần saga/outbox hoặc quy trình cleanup/retry riêng.

### 20.2. Trả connection về pool

Trong connection pool, `connection.close()` thường trả logical connection về pool. Trước khi trả:

- Đảm bảo transaction đã commit hoặc rollback.
- Đóng statement/result set/stream/LOB.
- Không giữ cursor hoặc stream phụ thuộc connection.
- Đảm bảo không để connection ở isolation, schema, timezone hoặc autocommit khác trạng thái mà pool mong đợi; pool/framework thường reset một số thuộc tính nhưng không nên dựa vào điều không được bảo đảm.

### 20.3. Đừng đổi timezone session tùy tiện trên connection dùng chung

Nếu một request chạy:

```sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';
```

và connection được trả pool mà trạng thái session không reset đúng cách, request tiếp theo có thể nhận timezone không như mong đợi. Tốt hơn là:

- Cấu hình timezone chuẩn cho pool/database.
- Dùng offset/zone rõ trong tham số.
- Reset session state nếu ứng dụng thực sự phải thay đổi.

## 21. Thiết kế bảng thực hành tổng hợp

Bảng PostgreSQL dưới đây minh họa các kiểu dữ liệu trong một ứng dụng:

```sql
CREATE TABLE app_media_records (
    record_id UUID PRIMARY KEY,
    amount NUMERIC(19, 4) NOT NULL
        CHECK (amount >= 0),
    business_date DATE,
    local_start_time TIME,
    scheduled_local TIMESTAMP,
    occurred_at TIMESTAMPTZ,
    zone_id TEXT,
    file_name TEXT,
    content_type TEXT,
    content BYTEA,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 21.1. Ý nghĩa từng cột

| Cột | Kiểu SQL | Java |
|---|---|---|
| `record_id` | `UUID` | `UUID` |
| `amount` | `NUMERIC(19,4)` | `BigDecimal` |
| `business_date` | `DATE` | `LocalDate` |
| `local_start_time` | `TIME` | `LocalTime` |
| `scheduled_local` | `TIMESTAMP` | `LocalDateTime` |
| `occurred_at` | `TIMESTAMPTZ` | `OffsetDateTime` hoặc `Instant` qua mapping phù hợp |
| `zone_id` | `TEXT` | `ZoneId`/`String` |
| `content` | `BYTEA` | `InputStream`/`byte[]` |
| `description` | `TEXT` | `String`/`Reader` |
| `created_at` | `TIMESTAMPTZ` | `OffsetDateTime`/`Instant` |

### 21.2. Tại sao vừa có `scheduled_local` vừa có `occurred_at`?

Một bản ghi có thể vừa có lịch dự kiến trên đồng hồ địa phương, vừa có thời điểm thực tế xảy ra. Chúng có **ý nghĩa khác nhau** và cần kiểu riêng. Không nên đổi tất cả thành `TIMESTAMP` hoặc tất cả thành `TIMESTAMPTZ` chỉ để đơn giản mapping.

### 21.3. Không phải cột nào cũng cần nullable

`business_date`, `occurred_at` có thể null nếu nghiệp vụ cho phép chưa xác định. `amount`/`record_id` là bắt buộc. Dùng `NOT NULL`/`CHECK` theo contract để database bảo vệ dữ liệu, đồng thời kiểm tra ở application để trả lỗi dễ hiểu.

## 22. Java domain model và repository mapping

Một record Java có thể biểu diễn domain:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.UUID;

public record MediaRecord(
    UUID recordId,
    BigDecimal amount,
    LocalDate businessDate,
    LocalTime localStartTime,
    LocalDateTime scheduledLocal,
    OffsetDateTime occurredAt,
    String zoneId,
    String fileName,
    String contentType
) {}
```

### 22.1. Map một dòng

```java
private MediaRecord mapRow(ResultSet result) throws SQLException {
    return new MediaRecord(
        result.getObject("record_id", UUID.class),
        result.getBigDecimal("amount"),
        result.getObject("business_date", LocalDate.class),
        result.getObject("local_start_time", LocalTime.class),
        result.getObject("scheduled_local", LocalDateTime.class),
        result.getObject("occurred_at", OffsetDateTime.class),
        result.getString("zone_id"),
        result.getString("file_name"),
        result.getString("content_type")
    );
}
```

### 22.2. Nullable field

Các getter trả kiểu tham chiếu có thể trả `null`. Nếu domain không cho phép `businessDate` null, hãy kiểm tra và chuyển thành lỗi dữ liệu có ngữ cảnh thay vì để null lan qua các tầng.

```java
LocalDate businessDate =
    result.getObject("business_date", LocalDate.class);

if (businessDate == null) {
    throw new SQLException("business_date is required");
}
```

### 22.3. Không biến tất cả SQL type thành String

Một repository kiểu:

```java
String amount = result.getString("amount");
String occurredAt = result.getString("occurred_at");
String recordId = result.getString("record_id");
```

có thể tiện hiển thị nhưng làm mất hợp đồng kiểu trong domain, dễ gây parse lại không nhất quán và làm logic tính toán/so sánh phụ thuộc format.

Hãy ánh xạ sang kiểu Java tương ứng **ngay tại ranh giới persistence**.

## 23. Batch insert với dữ liệu có kiểu

Nếu insert nhiều bản ghi nhỏ, dùng batch JDBC thay vì gọi execute từng dòng:

```java
String sql = """
    INSERT INTO app_invoice_amounts
        (invoice_id, currency_code, amount)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (InvoiceAmount item : items) {
        statement.setLong(1, item.invoiceId());
        statement.setString(2, item.currencyCode());
        statement.setBigDecimal(3, item.amount());
        statement.addBatch();
    }

    int[] counts = statement.executeBatch();
}
```

### 23.1. Batch và transaction

Batch là cách gửi nhiều lệnh cùng statement hiệu quả hơn, nhưng không tự định nghĩa toàn bộ transaction nghiệp vụ. Nếu cần all-or-nothing, vẫn quản lý transaction:

```java
connection.setAutoCommit(false);
try {
    // addBatch / executeBatch
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
```

### 23.2. Batch có thể cần chia nhỏ

Một batch cực lớn có thể tạo áp lực bộ nhớ driver, kích thước packet, transaction và WAL/redo. Chọn batch size theo thử nghiệm, chẳng hạn vài trăm hoặc vài nghìn dòng, tùy driver và kích thước mỗi dòng.

### 23.3. Đừng batch BLOB khổng lồ một cách mù quáng

Nếu mỗi dòng có tệp lớn, batch có thể giữ nhiều stream/giá trị đồng thời. Có thể cần ghi từng tệp hoặc nhóm nhỏ, quản lý stream và transaction theo chính sách phù hợp.

## 24. Cách xử lý SQL NULL đúng với các kiểu đang học

SQL `NULL` không phải `0`, chuỗi rỗng, ngày mặc định hoặc UUID toàn số 0.

### 24.1. Ghi NULL bằng JDBC

```java
statement.setNull(1, java.sql.Types.NUMERIC);
statement.setNull(2, java.sql.Types.DATE);
statement.setNull(3, java.sql.Types.TIMESTAMP_WITH_TIMEZONE);
statement.setNull(4, java.sql.Types.OTHER); // Với UUID tùy driver/database.
statement.setNull(5, java.sql.Types.BLOB);
```

`Types.OTHER` cho UUID là một cách có thể cần với PostgreSQL JDBC tùy driver; nếu driver có hỗ trợ `setObject(index, null, sqlType)` phù hợp, dùng mapping rõ ràng. Không có một `Types.UUID` chuẩn trong JDBC cổ điển.

### 24.2. Đọc nullable `BigDecimal`, `UUID`, ngày giờ

```java
BigDecimal amount = result.getBigDecimal("amount");
UUID externalId = result.getObject("external_id", UUID.class);
LocalDate dueDate = result.getObject("due_date", LocalDate.class);
OffsetDateTime occurredAt =
    result.getObject("occurred_at", OffsetDateTime.class);
```

Các giá trị có thể là Java `null` khi SQL NULL.

### 24.3. `wasNull()` với kiểu primitive

```java
long optionalId = result.getLong("optional_id");
boolean isNull = result.wasNull();
```

Gọi `wasNull()` ngay sau getter primitive tương ứng; nếu gọi một getter khác trước, trạng thái sẽ phản ánh cột vừa đọc gần nhất.

## 25. Kiểm tra schema và round-trip

Mapping đúng không chỉ là một chiều ghi được. Cần kiểm tra **round-trip**:

```text
Java value
   │ setObject / setBigDecimal / stream
   ▼
SQL storage
   │ getObject / getBigDecimal / stream
   ▼
Java value được khôi phục
```

### 25.1. Decimal round-trip

Kiểm tra:

- Giá trị có bằng nhau về số học không (`compareTo == 0`)?
- Scale sau khi đọc có đúng kỳ vọng không?
- Có làm tròn/overflow không?
- Giá trị âm/zero/null được xử lý đúng không?

### 25.2. Date/time round-trip

Kiểm tra:

- `LocalDate` không bị đổi ngày.
- `LocalTime` không bị gắn zone ngầm.
- `LocalDateTime` giữ đúng wall-clock.
- `OffsetDateTime` khôi phục cùng instant (`toInstant()` bằng nhau), không nhất thiết giữ offset ban đầu trong PostgreSQL.
- Precision phần giây có đúng giới hạn cột không.

### 25.3. UUID round-trip

So sánh:

```java
originalUuid.equals(restoredUuid)
```

Nếu lưu binary, kiểm tra cả vector UUID cố định và byte sequence ở mọi ngôn ngữ/driver.

### 25.4. Binary round-trip

So sánh:

- Số byte.
- Checksum SHA-256.
- Content type/metadata.
- Khả năng đọc lại stream khi result set còn mở.
- Hành vi với file rỗng và file lớn.

Không chỉ kiểm tra “insert trả 1 dòng” rồi kết luận tệp không hỏng.

## 26. Kiểm thử với PostgreSQL thật

Một số ánh xạ phụ thuộc driver. Unit test chỉ mock `ResultSet` có thể không phát hiện:

- Driver trả `OffsetDateTime` theo UTC.
- PostgreSQL `NUMERIC(p,s)` làm tròn hoặc overflow.
- UUID mapping không tương thích.
- Fetch size không tạo server-side cursor vì autocommit.
- BLOB stream bị đóng khi `ResultSet` đóng.
- Timezone session thay đổi cách hiển thị `timestamptz`.

### 26.1. Kiểm thử integration tối thiểu

Một bộ test nên:

1. Tạo schema tạm hoặc database test riêng.
2. Ghi `BigDecimal("123.4500")`, đọc lại và kiểm tra precision/scale theo contract.
3. Ghi `LocalDate`, `LocalDateTime`, `OffsetDateTime` có offset khác UTC.
4. Thay `TimeZone` session và xác nhận instant không đổi.
5. Ghi/đọc UUID cố định.
6. Upload/download binary lớn theo stream, so checksum.
7. Kiểm tra SQL NULL và giá trị 0 riêng.
8. Kiểm tra connection/transaction/stream được đóng khi exception.

### 26.2. Kiểm tra timezone session

Ví dụ PostgreSQL:

```sql
SHOW TIME ZONE;

SELECT
    TIMESTAMPTZ '2026-11-14 09:30:00+07' AS event_time,
    TIMESTAMPTZ '2026-11-14 09:30:00+07'
        AT TIME ZONE 'UTC' AS utc_local_time;
```

Kết quả hiển thị cột `event_time` theo session zone; biểu thức `AT TIME ZONE 'UTC'` trả local timestamp UTC tương ứng.

### 26.3. Kiểm tra metadata JDBC

JDBC cung cấp `DatabaseMetaData` và `ResultSetMetaData` để quan sát driver/database:

```java
var metadata = connection.getMetaData();
System.out.println(metadata.getDatabaseProductName());
System.out.println(metadata.getDatabaseProductVersion());
System.out.println(metadata.getDriverName());
System.out.println(metadata.getDriverVersion());
```

Thông tin này hữu ích khi hành vi mapping khác giữa môi trường dev và production.

## 27. Các khác biệt driver cần nhớ

| Tình huống | PostgreSQL JDBC | Driver DBMS khác |
|---|---|---|
| `NUMERIC` ↔ `BigDecimal` | Hỗ trợ chuẩn, thường ổn định | Thường có nhưng cần kiểm tra precision/scale |
| `DATE` ↔ `LocalDate` | JDBC 4.2 hỗ trợ | Tùy driver/phiên bản |
| `TIMESTAMP` ↔ `LocalDateTime` | Hỗ trợ | Tùy driver |
| `TIMESTAMPTZ` ↔ `OffsetDateTime` | Hỗ trợ; giá trị trả về chuẩn hóa UTC | Tên kiểu và hành vi khác |
| UUID | Native PostgreSQL `uuid` ↔ `UUID` | Có thể cần String/BINARY/RAW |
| Binary lớn | `BYTEA` hoặc Large Object API | BLOB/VARBINARY/LOB riêng |
| Server-side fetch | Fetch size dương và transaction phù hợp | Cấu hình có thể hoàn toàn khác |

### 27.1. Không kiểm thử trên H2 rồi suy ra PostgreSQL

Database in-memory có thể hữu ích cho test logic, nhưng không thay thế integration test khi cần xác nhận:

- `TIMESTAMPTZ` và timezone.
- Kiểu UUID native.
- BLOB/LOB và stream.
- Precision của numeric.
- Fetch size/server cursor.

### 27.2. Phiên bản driver là một phần hợp đồng triển khai

Ghi nhận phiên bản JDBC driver trong dependency management. Một nâng cấp driver có thể thay đổi cách chuyển kiểu, timezone hoặc buffering. Nên có test round-trip trước khi nâng phiên bản lớn.

## 28. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `double` cho tiền | Sai số thập phân tích lũy | `BigDecimal` + SQL `NUMERIC` |
| `new BigDecimal(0.1)` | Mang sai số nhị phân vào decimal | `new BigDecimal("0.1")` |
| Quên gán lại kết quả `add` | Tổng không thay đổi | `total = total.add(value)` |
| Dùng `equals` để so hai số khác scale | `1.0` khác `1.00` | `compareTo` nếu so số học |
| Làm tròn mặc định không rõ | Sai quy tắc tài chính | Chỉ định `RoundingMode` |
| Chỉ dựa vào `NUMERIC(p,s)` | Làm tròn/overflow ngoài ý muốn | Kiểm tra precision, scale, miền |
| Dùng `getDouble` cho NUMERIC | Mất chính xác | `getBigDecimal` |
| Dùng `LocalDateTime` cho thời điểm toàn cầu | Không biết instant/zone | `OffsetDateTime`/`Instant` + `TIMESTAMPTZ` |
| Nghĩ `TIMESTAMPTZ` lưu tên zone gốc | Mất zone id | Lưu `ZoneId` riêng nếu cần |
| Dùng `TIMESTAMP` thay `TIMESTAMPTZ` tùy tiện | Diễn giải sai giờ | Chọn theo wall-clock hay instant |
| Dựa vào timezone JVM | Kết quả khác giữa môi trường | Zone rõ ràng, cấu hình session |
| Cast `TIMESTAMPTZ` thành date mà không chọn zone | Ngày báo cáo lệch | Xác định timezone trước |
| Dùng `double`/`long` cho timestamp không rõ đơn vị | Sai hàng nghìn lần | Ghi rõ seconds/milliseconds |
| Đọc UUID bằng `String` rồi dùng tùy ý | Lỗi parse/format | `UUID` native hoặc canonical format |
| Lưu UUID binary không thống nhất byte order | Hệ thống đọc ra UUID khác | Chuẩn hóa encoding và test vector |
| Dùng UUID làm authorization | Truy cập trái phép | Kiểm tra quyền độc lập |
| `readAllBytes()` với tệp lớn | Heap tăng mạnh | `InputStream`/streaming |
| `getBytes()` cho BLOB rất lớn | Tạo mảng lớn | `getBinaryStream()` |
| Đóng ResultSet trước khi đọc xong stream | Stream lỗi hoặc bị đóng | Đọc stream trong phạm vi ResultSet |
| Quên `Blob.free()`/đóng stream | Rò rỉ tài nguyên | Quản lý vòng đời tường minh |
| Đọc PDF bằng `Reader` | Hỏng byte do charset | Dùng binary stream |
| Dùng `fetchSize` để stream BLOB | Nhầm hai vấn đề | Fetch batch cho nhiều dòng; stream cho một giá trị |
| Tưởng `setFetchSize` luôn tạo cursor | Driver có thể buffer toàn bộ | Điều kiện driver/autocommit/fetch |
| Giữ transaction khi gọi API lâu | Giữ connection/snapshot/lock | Batch ngắn, tách side effect |
| Đóng connection mà chưa rollback/commit | Connection pool nhận trạng thái không mong muốn | Kết thúc transaction rõ |
| Test chỉ bằng mock | Bỏ sót khác biệt driver | Integration test với DB thật |

## 29. Bài tập tự luyện

Các bài dưới đây dùng PostgreSQL, JDBC và Java. Những câu có schema SQL có thể chạy trên database test riêng; các ví dụ Java là đoạn độc lập cần có `Connection` hợp lệ và JDBC driver tương ứng.

### Bài 1 — Chọn kiểu cho tiền

Một cột lưu giá bán có tối đa 10 chữ số trước dấu thập phân và 2 chữ số sau dấu thập phân. Chọn kiểu SQL và kiểu Java phù hợp.

### Bài 2 — Vì sao không dùng double?

Giải thích vì sao `new BigDecimal(0.1)` có thể khác `new BigDecimal("0.1")`. Viết cách khởi tạo đúng cho giá trị API `"19.95"`.

### Bài 3 — Precision và scale

`NUMERIC(12,2)` có tối đa bao nhiêu chữ số trước dấu thập phân? Giá trị `9999999999.99` có vừa không?

### Bài 4 — Làm tròn

Với `10.245`, so sánh `HALF_UP` và `HALF_EVEN` khi scale 2. Khi nào dùng `UNNECESSARY`?

### Bài 5 — So sánh BigDecimal

`new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả gì? Dùng phương thức nào để so sánh bằng nhau về số học?

### Bài 6 — JDBC money

Viết hai dòng JDBC ghi và đọc cột `NUMERIC` đúng kiểu Java.

### Bài 7 — SQL NULL và zero

Một cột `discount_amount` nullable. Phân biệt SQL NULL với giá trị `0.00` khi đọc bằng `getBigDecimal`.

### Bài 8 — Chọn kiểu ngày giờ

Chọn kiểu Java và SQL cho:

1. Ngày sinh.
2. Giờ cửa hàng mở.
3. Lịch hẹn 09:00 chưa xác định zone.
4. Thời điểm thanh toán xảy ra trên toàn cầu.

### Bài 9 — `TIMESTAMP` và `TIMESTAMPTZ`

PostgreSQL khác nhau thế nào giữa hai kiểu? Vì sao `TIMESTAMPTZ` không giữ lại tên `Asia/Ho_Chi_Minh`?

### Bài 10 — JDBC 4.2

Viết mapping `LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetDateTime` bằng `setObject` và `getObject`.

### Bài 11 — Instant

Một ứng dụng domain dùng `Instant`. Viết cầu nối qua `java.sql.Timestamp` và nêu điều cần chú ý với kiểu SQL đích.

### Bài 12 — Timezone

Một báo cáo cần lấy giao dịch trong tháng 11/2026 theo giờ Việt Nam. Viết điều kiện khoảng nửa mở cho cột `occurred_at TIMESTAMPTZ`.

### Bài 13 — DST

Vì sao chỉ lưu `LocalDateTime` cho lịch hẹn tại vùng có DST có thể không đủ? Nêu ý nghĩa của gap và overlap.

### Bài 14 — UUID

Viết SQL tạo bảng PostgreSQL có khóa chính UUID và Java insert UUID bằng `setObject`.

### Bài 15 — UUID binary

Nếu MySQL lưu UUID bằng `BINARY(16)`, tại sao các service phải thống nhất byte order? Nêu rủi ro nếu một service dùng quy tắc khác.

### Bài 16 — Lưu tệp binary

Phân biệt `BYTEA` và PostgreSQL Large Object (OID). Khi xóa bản ghi tham chiếu OID, điều gì cần được quản lý?

### Bài 17 — `setBytes` hay `setBinaryStream`

Một file 150 MB cần upload. Vì sao `Files.readAllBytes` có thể gây áp lực heap? Viết cách truyền bằng stream.

### Bài 18 — Đọc BLOB

Viết khung JDBC đọc cột binary ra file bằng `getBinaryStream`. Vì sao stream cần được đọc trước khi đóng `ResultSet`?

### Bài 19 — Text lớn

Phân biệt `InputStream` và `Reader`. Khi ghi UTF-8 text bằng `setCharacterStream`, tại sao không thể lấy `Files.size()` (byte) làm character length?

### Bài 20 — `Blob.free`

`Blob.free()` khác `InputStream.close()` như thế nào? Khi dùng `getBlob`, cần quản lý cả hai không?

### Bài 21 — Fetch size

Một truy vấn trả 5 triệu dòng nhỏ. `setFetchSize(500)` giúp gì? Vì sao nó không phải `LIMIT 500`?

### Bài 22 — Một BLOB lớn

Một dòng có BLOB 500 MB. `setFetchSize(500)` có chia giá trị BLOB thành 500 phần không? Cần API nào?

### Bài 23 — pgJDBC server-side fetch

Nêu các điều kiện phổ biến để pgJDBC dùng cursor-based fetching với fetch size dương.

### Bài 24 — Connection pool

Vì sao không được trả connection về pool khi vẫn đang đọc stream từ `ResultSet`? Vì sao phải commit/rollback trước khi trả?

### Bài 25 — Test round-trip

Đề xuất kiểm tra round-trip cho BigDecimal, OffsetDateTime, UUID và binary. Chỉ kiểm tra số dòng insert thành công có đủ không?

### Bài 26 — Thiết kế schema

Thiết kế một bảng PostgreSQL lưu ID UUID, tiền `NUMERIC`, ngày nghiệp vụ, thời điểm sự kiện, tên zone và tệp đính kèm. Giải thích kiểu từng cột.

### Bài 27 — External object storage

Ứng dụng upload file lên object storage rồi insert metadata SQL. Nếu upload thành công nhưng SQL rollback thì cần quy trình nào? Vì sao transaction DB không xóa object tự động?

### Bài 28 — Tìm lỗi mapping

Một repository dùng `getString("amount")`, parse bằng `Double.parseDouble`, sau đó tạo `BigDecimal` từ double. Hãy nêu các điểm rủi ro và cách viết lại.

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:** SQL `NUMERIC(12,2)`/`DECIMAL(12,2)`; Java `BigDecimal`. Có 12 chữ số tổng, 2 chữ số thập phân.

**Bài 2:** `double` là dấu phẩy động nhị phân nên 0.1 không biểu diễn chính xác. Dùng `new BigDecimal("19.95")`.

**Bài 3:** 10 chữ số trước dấu thập phân. `9999999999.99` vừa đúng giới hạn `NUMERIC(12,2)`.

**Bài 4:** `HALF_UP` cho `10.25`, `HALF_EVEN` cho `10.24`. `UNNECESSARY` dùng khi phải từ chối mọi phép làm tròn.

**Bài 5:** `equals` trả `false`; `compareTo(...) == 0` kiểm tra bằng nhau về số học.

**Bài 6:**

```java
statement.setBigDecimal(1, new BigDecimal("125.75"));
BigDecimal amount = result.getBigDecimal("amount");
```

**Bài 7:** `getBigDecimal` trả Java `null` với SQL NULL; trả `BigDecimal.ZERO` hoặc giá trị 0 thực với `0.00`. Không tự thay null thành zero.

**Bài 8:**

| Ý nghĩa | Java | SQL |
|---|---|---|
| Ngày sinh | `LocalDate` | `DATE` |
| Giờ mở cửa | `LocalTime` | `TIME` |
| Lịch hẹn chưa zone | `LocalDateTime` | `TIMESTAMP` |
| Thanh toán thực tế | `Instant`/`OffsetDateTime` | `TIMESTAMPTZ` |

Nếu lịch hẹn cần vùng cụ thể, lưu thêm `ZoneId`.

**Bài 9:** `TIMESTAMP` không có timezone; `TIMESTAMPTZ` biểu diễn instant và hiển thị theo timezone session. PostgreSQL chuẩn hóa thời điểm, không giữ zone id gốc.

**Bài 10:**

```java
statement.setObject(1, localDate);
statement.setObject(2, localTime);
statement.setObject(3, localDateTime);
statement.setObject(4, offsetDateTime);

LocalDate d = result.getObject(1, LocalDate.class);
LocalTime t = result.getObject(2, LocalTime.class);
LocalDateTime dt = result.getObject(3, LocalDateTime.class);
OffsetDateTime odt = result.getObject(4, OffsetDateTime.class);
```

Driver phải hỗ trợ các mapping.

**Bài 11:**

```java
Timestamp sqlTimestamp = Timestamp.from(instant);
Instant restored = sqlTimestamp.toInstant();
```

Phải biết cột đích là `TIMESTAMPTZ` hay `TIMESTAMP` và hiểu timezone/driver.

**Bài 12:**

```sql
WHERE occurred_at >=
      TIMESTAMP '2026-11-01 00:00:00'
      AT TIME ZONE 'Asia/Ho_Chi_Minh'
  AND occurred_at <
      TIMESTAMP '2026-12-01 00:00:00'
      AT TIME ZONE 'Asia/Ho_Chi_Minh'
```

**Bài 13:** DST gap là local time không tồn tại; overlap là local time xuất hiện hai lần. Cần `ZoneId`/quy tắc để quyết định instant.

**Bài 14:**

```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL
);
```

```java
statement.setObject(1, UUID.randomUUID());
```

**Bài 15:** Binary UUID là 16 byte; khác byte order làm cùng chuỗi UUID thành 16 byte khác, khiến service đọc ra ID khác hoặc lookup thất bại. Cần một encoding chuẩn và test vector.

**Bài 16:** `BYTEA` chứa byte trong một giá trị SQL. Large Object được tham chiếu bằng OID và quản lý qua API riêng; xóa row không mặc nhiên xóa LO, cần `lo_unlink`/cleanup.

**Bài 17:**

```java
try (InputStream input = Files.newInputStream(path);
     PreparedStatement statement = connection.prepareStatement(
         "INSERT INTO app_attachments (...) VALUES (...)")) {
    statement.setBinaryStream(1, input, Files.size(path));
    statement.executeUpdate();
}
```

`readAllBytes` tạo mảng 150 MB cho mỗi upload đồng thời, dễ gây áp lực heap/GC.

**Bài 18:**

```java
try (ResultSet rs = statement.executeQuery()) {
    if (rs.next()) {
        try (InputStream in = rs.getBinaryStream("content")) {
            Files.copy(in, destination);
        }
    }
}
```

Stream có thể phụ thuộc ResultSet/statement/connection; đóng result set sớm có thể làm stream không đọc tiếp được.

**Bài 19:** `InputStream` đọc byte; `Reader` đọc ký tự. UTF-8 có ký tự dài 1–4 byte, nên byte length không bằng số ký tự.

**Bài 20:** `InputStream.close()` đóng luồng đọc; `Blob.free()` giải phóng tài nguyên LOB. Khi dùng `getBlob`, thường cần đóng stream và gọi `free` theo hợp đồng driver.

**Bài 21:** `fetchSize` gợi ý số dòng driver lấy mỗi batch, giảm việc buffer toàn bộ nhiều dòng khi driver hỗ trợ. Nó không thêm `LIMIT` và không giảm tổng số dòng query trả.

**Bài 22:** Không. Fetch size là batch của các dòng; một BLOB là một giá trị. Dùng `getBinaryStream`/`setBinaryStream` hoặc Large Object API phù hợp.

**Bài 23:** Với pgJDBC thường cần `autoCommit=false`, result set forward-only/read-only, fetch size dương và connection/transaction còn mở trong lúc đọc.

**Bài 24:** Stream phụ thuộc result set/statement/connection; trả connection về pool có thể đóng hoặc tái sử dụng connection trước khi stream đọc xong. Phải kết thúc transaction rõ ràng để không để connection ở trạng thái dang dở.

**Bài 25:** Decimal so `compareTo` và scale; thời gian so `Instant` và precision; UUID so `equals`; binary so size và checksum. Chỉ số dòng insert không chứng minh nội dung/kiểu được round-trip đúng.

**Bài 26:**

```sql
CREATE TABLE media_records (
    record_id UUID PRIMARY KEY,
    amount NUMERIC(19,4) NOT NULL,
    business_date DATE,
    occurred_at TIMESTAMPTZ,
    zone_id TEXT,
    content BYTEA
);
```

Java dùng `UUID`, `BigDecimal`, `LocalDate`, `OffsetDateTime`/`Instant`, `ZoneId`/`String`, `InputStream`.

**Bài 27:** Cần cleanup/retry hoặc outbox/saga để xóa object orphan nếu SQL thất bại; database transaction chỉ quản lý thay đổi trong database, không rollback dịch vụ object storage bên ngoài.

**Bài 28:** Rủi ro: chuyển qua double làm mất precision, parse text lặp và phụ thuộc locale/format, BigDecimal từ double giữ sai số nhị phân. Viết lại:

```java
BigDecimal amount = result.getBigDecimal("amount");
```

và ghi bằng `setBigDecimal`.

</details>

## 30. Checklist chọn kiểu và mapping

Trước khi triển khai một cột hoặc repository mới, hãy xác định:

1. **Ý nghĩa nghiệp vụ:** tiền, số đo, ngày lịch, local time, instant, ID, binary hay text?
2. **Kiểu SQL:** `NUMERIC(p,s)`, `DATE`, `TIMESTAMP`, `TIMESTAMPTZ`, `UUID`, `BYTEA`, `BLOB`, `TEXT` hay CLOB?
3. **Kiểu Java:** `BigDecimal`, `LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetDateTime`, `Instant`, `UUID`, `InputStream`, `Reader`?
4. **Precision và scale:** giới hạn, làm tròn, từ chối hay chấp nhận phần thập phân thừa?
5. **Timezone:** local wall-clock hay instant? Có cần giữ `ZoneId` không?
6. **Driver:** phiên bản có hỗ trợ mapping JDBC 4.2 và kiểu LOB cần dùng không?
7. **NULL:** SQL NULL khác zero, chuỗi rỗng, byte rỗng và giá trị mặc định thế nào?
8. **Kích thước:** dữ liệu có thể lớn tới đâu? Dùng byte array/String hay stream?
9. **Vòng đời:** ai đóng ResultSet, stream, Blob/Clob, statement, transaction và connection?
10. **Concurrency:** giữ transaction/snapshot/lock bao lâu?
11. **Tính nhất quán ngoài DB:** object storage, message, email có side effect không?
12. **Round-trip:** đã test dữ liệu biên và phiên bản driver thật chưa?

### 30.1. Năm quy tắc nên nhớ

- **Tiền:** `NUMERIC` ↔ `BigDecimal`, tạo từ chuỗi và chọn rounding mode tường minh.
- **Ngày giờ:** `LocalDate` cho ngày, `LocalDateTime` cho wall-clock không zone, `OffsetDateTime`/`Instant` cho thời điểm; `TIMESTAMPTZ` không lưu tên zone gốc.
- **UUID:** dùng `UUID` và kiểu native nếu có; nếu binary/text, chuẩn hóa format/byte order.
- **Dữ liệu lớn:** binary dùng stream byte, text dùng stream ký tự; tránh materialize cả tệp lớn vào heap.
- **Nhiều dòng:** `fetchSize`/server-side cursor là cơ chế khác với streaming một cột LOB.

## 31. Kết luận

Ánh xạ số thập phân, ngày giờ, UUID và dữ liệu lớn là công việc xác định **ranh giới kiểu dữ liệu** giữa Java, JDBC driver và SQL database.

```text
BigDecimal
   ↕ setBigDecimal / getBigDecimal
NUMERIC / DECIMAL

LocalDate / LocalTime / LocalDateTime
   ↕ setObject / getObject
DATE / TIME / TIMESTAMP

OffsetDateTime / Instant
   ↕ JDBC 4.2 mapping phù hợp
TIMESTAMP WITH TIME ZONE

UUID
   ↕ setObject / getObject
UUID native hoặc mapping binary/text đã chuẩn hóa

InputStream / Reader
   ↕ setBinaryStream / getBinaryStream
BYTEA / BLOB / TEXT / CLOB
```

Hãy nhớ bốn nguyên tắc:

1. **Không hy sinh độ chính xác:** tiền dùng `BigDecimal`/`NUMERIC`, quy tắc scale và rounding phải rõ.
2. **Không đánh mất ý nghĩa thời gian:** phân biệt ngày, giờ địa phương và instant; timezone phải được xác định bằng hợp đồng.
3. **Không làm mơ hồ định danh:** UUID cần một mapping thống nhất giữa mọi service và database.
4. **Không giữ dữ liệu lớn trong bộ nhớ khi không cần:** dùng stream đúng loại, quản lý transaction và tài nguyên theo vòng đời.

Một mapping tốt không chỉ làm câu `INSERT` chạy thành công. Nó phải bảo toàn **giá trị, độ chính xác, ý nghĩa thời gian, định danh và nội dung** khi dữ liệu đi từ ứng dụng vào database rồi quay trở lại.
