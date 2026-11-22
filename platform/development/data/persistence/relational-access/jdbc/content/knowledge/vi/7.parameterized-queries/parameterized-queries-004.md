# Lựa chọn phương thức setXxx và setObject trong JDBC

Trong JDBC (*Java Database Connectivity*, API Java để truy cập cơ sở dữ liệu quan hệ), `PreparedStatement` cho phép viết câu SQL có dấu `?` và truyền giá trị từ Java vào từng vị trí tham số. Khi bind giá trị, hai nhóm API thường được sử dụng là **các phương thức có kiểu cụ thể** như `setString()`, `setLong()`, `setBigDecimal()` và **phương thức tổng quát `setObject()`**.

Bài học thuộc chương **Truy vấn tham số** này giúp bạn chọn đúng setter cho từng kiểu dữ liệu, tránh lỗi chuyển kiểu, mất độ chính xác, hiểu sai `NULL` và lệch thời gian khi làm việc với driver JDBC. Trọng tâm là **ý nghĩa kiểu SQL**, không phải chỉ làm cho một giá trị Java được đưa vào câu truy vấn.

Sau bài học, bạn có thể:

- Biết khi nào ưu tiên `setXxx` để truyền ý định kiểu dữ liệu rõ ràng.
- Hiểu các overload của `setObject`, nhất là khi khai báo kiểu SQL đích.
- Xử lý `NULL`, số thập phân, ngày giờ và dữ liệu nhị phân.
- Nhận diện những phép chuyển kiểu phụ thuộc driver và hệ quản trị.
- Viết và kiểm chứng một câu lệnh `INSERT`/`SELECT` dùng nhiều loại tham số.

## 1. PreparedStatement bind **giá trị**, không chèn mã SQL

Ví dụ cần tìm đơn hàng theo người mua và ngưỡng giá trị:

```sql
SELECT id, total_amount
FROM orders
WHERE customer_id = ? AND total_amount >= ?
```

Hai dấu `?` là vị trí chứa **giá trị SQL**. Ta bind theo thứ tự, **đánh số từ 1**:

```java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setBigDecimal(2, new BigDecimal("150.00"));

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getLong("id"));
        }
    }
}
```

Đoạn trên giả định `connection`, `sql` và `customerId` đã được khai báo; chúng cần nằm trong vòng đời connection phù hợp. Khi bind bằng `PreparedStatement`, driver nhận giá trị riêng với cấu trúc SQL. Điều này giúp xử lý ký tự đặc biệt an toàn và chống SQL injection ở vị trí **giá trị**.

Điểm quan trọng là setter còn truyền **thông tin kiểu** đến driver. Cùng một giá trị biểu diễn `"150.00"` có thể được xem là chuỗi văn bản, số nguyên, số thập phân hoặc kiểu khác; điều đó ảnh hưởng tới quy tắc so sánh, chuyển đổi, mức chính xác và khả năng chọn kiểu tham số của câu SQL.

**Không thể dùng dấu `?` thay tên bảng, cột hoặc hướng sắp xếp.** Ví dụ `ORDER BY ?` không cho phép tham số trở thành identifier `price`; nó chỉ biểu diễn một giá trị. Khi có cột sắp xếp động, phải chọn từ danh sách tên cột hợp lệ trong code rồi mới xây dựng phần identifier.

## 2. setXxx: chọn setter theo kiểu dữ liệu và mục đích

Nhóm `setXxx` cung cấp các setter tường minh. Tên phương thức nhấn mạnh **kiểu Java truyền vào** và thường thể hiện loại giá trị ứng dụng muốn gửi.

| Giá trị Java | Setter thường dùng | Kiểu cột SQL hay gặp | Lưu ý |
|---|---|---|---|
| `String` | `setString(index, value)` | `VARCHAR`, `CHAR`, một số kiểu text | Không dùng để “giả lập” mọi kiểu dữ liệu |
| `int` | `setInt(index, value)` | `INTEGER` | Chú ý giới hạn và tràn khi chuyển kiểu |
| `long` | `setLong(index, value)` | `BIGINT` | Phù hợp với ID kiểu bigint |
| `short`, `byte` | `setShort()`, `setByte()` | `SMALLINT`, `TINYINT` | `TINYINT` và xử lý signed/unsigned khác theo DB |
| `boolean` | `setBoolean(index, value)` | `BOOLEAN` hoặc kiểu tương đương | Một số DB lưu boolean bằng kiểu đặc thù |
| `BigDecimal` | `setBigDecimal(index, value)` | `DECIMAL`, `NUMERIC` | Phù hợp tiền tệ, độ chính xác thập phân |
| `double`, `float` | `setDouble()`, `setFloat()` | `DOUBLE`, `REAL`/`FLOAT` | Số dấu phẩy động nhị phân có sai số biểu diễn |
| `byte[]` | `setBytes(index, value)` | `VARBINARY` hoặc kiểu nhị phân được hỗ trợ | Dùng cho payload nhỏ, lưu toàn bộ mảng trong heap |
| `InputStream` | `setBinaryStream(...)` | Kiểu nhị phân lớn được hỗ trợ | Giữ luồng mở cho đến khi statement đọc xong |
| `java.sql.Date` | `setDate(index, value)` | `DATE` | API cũ, cần chuyển từ `LocalDate` khi thích hợp |
| `java.sql.Time` | `setTime(index, value)` | `TIME` | API cũ, không nên nhầm với timestamp |
| `java.sql.Timestamp` | `setTimestamp(index, value)` | `TIMESTAMP` | Cẩn thận múi giờ và ý nghĩa timestamp |
| SQL `NULL` | `setNull(index, sqlType)` | Kiểu SQL cụ thể | Không dùng `setInt`/`setBoolean` để biểu diễn null |

**Không có bảng ánh xạ nào thay thế hoàn toàn tài liệu của driver.** Một số SQL type mang tính nhà cung cấp, chẳng hạn `UUID`, `JSONB`, `ENUM` hoặc `GEOGRAPHY`. Driver có thể hỗ trợ truyền những giá trị này bằng `setObject` hoặc API mở rộng, nhưng không nên mặc định cùng một kiểu Java hoạt động trên mọi database.

### Ví dụ chọn setter theo schema

Cho cột `customer_id BIGINT`, `email VARCHAR(255)`, `amount DECIMAL(12,2)`:

```java
statement.setLong(1, customerId);
statement.setString(2, email);
statement.setBigDecimal(3, new BigDecimal("875.30"));
```

Cách này cho thấy rõ tham số 1 là ID nguyên 64 bit, tham số 2 là văn bản và tham số 3 là số thập phân. Không nên chuyển tiền thành `double` rồi truyền bằng `setDouble()` chỉ vì Java dễ tính toán với `double`.

Đối với cột số thập phân, độ chính xác còn phụ thuộc **`precision` và `scale` trong schema**. `setBigDecimal()` không tự bỏ qua ràng buộc như `DECIMAL(12,2)`; nếu truyền số có quá nhiều chữ số hoặc quá nhiều chữ số thập phân, database/driver có thể làm tròn hoặc từ chối theo quy tắc của hệ thống. Nên kiểm tra và chuẩn hóa giá trị ngay ở tầng nghiệp vụ.

## 3. setObject: API tổng quát và các overload

`setObject` cho phép truyền một đối tượng Java và để driver ánh xạ sang kiểu SQL. Các overload quan trọng của `PreparedStatement` gồm:

```java
// Driver suy luận kiểu SQL từ lớp Java và ngữ cảnh câu SQL:
statement.setObject(1, value);

// Yêu cầu một kiểu SQL đích cụ thể:
statement.setObject(1, value, java.sql.Types.DECIMAL);

// Cung cấp thêm scale/length khi overload phù hợp với kiểu SQL:
statement.setObject(1, value, java.sql.Types.DECIMAL, 2);

// JDBC 4.2+: biểu diễn kiểu đích qua SQLType:
statement.setObject(1, value, java.sql.JDBCType.DECIMAL);
```

Ở đây, `statement` là `PreparedStatement`, `value` là giá trị đầu vào giả định. Các overload nhận `int targetSqlType` được định nghĩa trong JDBC; các overload dùng `SQLType` thuộc JDBC 4.2 và **có thể không được tất cả driver triển khai đầy đủ**. Với các kiểu đặc thù, hãy kiểm tra khả năng thực tế của driver. Không hiểu `scaleOrLength` là tham số áp dụng chung cho mọi SQL type: ý nghĩa của nó phụ thuộc kiểu đích và overload.

### 3.1. setObject(index, value): khi nào phù hợp?

Thường hợp lý khi:

- Giá trị thuộc một kiểu Java được JDBC 4.2/driver hỗ trợ trực tiếp, chẳng hạn `LocalDate`, `LocalDateTime` hoặc `OffsetDateTime` với kiểu SQL thích hợp.
- Lớp truy cập dữ liệu có schema/metadata rõ và kiểu runtime tương ứng kiểu cột.
- Cần làm việc với kiểu vendor-specific, chẳng hạn PostgreSQL `UUID`, và đã xác minh driver hỗ trợ.

Nhưng nếu kiểu SQL **không rõ** hoặc dữ liệu có thể chứa `null`, phép suy luận có thể mơ hồ. Ví dụ:

```java
statement.setObject(1, "42"); // Driver có thể coi đây là VARCHAR
statement.setObject(1, 42L);  // Thường suy luận từ Long/BIGINT
```

Cả hai có thể được database cho phép so sánh với cột số nguyên ở một số cấu hình, nhưng quy tắc chuyển đổi ngầm **không nhất quán giữa hệ quản trị**. Với cột `BIGINT`, `setLong()` thể hiện đúng ý định và ít phụ thuộc chuyển kiểu hơn.

### 3.2. setObject(index, value, targetSqlType): dùng khi cần rõ kiểu đích

Có thể yêu cầu driver chuyển đối tượng Java sang kiểu SQL cụ thể:

```java
statement.setObject(1, invoiceId, java.sql.Types.BIGINT);
statement.setObject(2, total, java.sql.Types.DECIMAL);
statement.setObject(3, issuedOn, java.sql.Types.DATE);
```

`invoiceId`, `total` và `issuedOn` ở đây lần lượt giả định là `Long`, `BigDecimal` và `LocalDate`. Lời gọi **không bảo đảm mọi phép chuyển kiểu đều hợp lệ**: nếu driver không hỗ trợ chuyển đối tượng sang kiểu SQL yêu cầu, JDBC có thể ném `SQLException` hoặc `SQLFeatureNotSupportedException`. Kiểm tra trên database mục tiêu và không kỳ vọng `setObject(?, "abc", Types.INTEGER)` tự biến được một chuỗi không phải số thành số.

**Khuyến nghị thực hành:** ưu tiên setter chuyên biệt khi kiểu Java và SQL đã rõ; dùng `setObject` khi cần ánh xạ hiện đại, kiểu trừu tượng hoặc target SQL type cụ thể, và ghi rõ kiểu đích khi có khả năng mơ hồ.

### 3.3. Khi cần scale cho DECIMAL

```java
BigDecimal amount = new BigDecimal("19.95");
statement.setBigDecimal(1, amount);

// Một lựa chọn tổng quát khác:
statement.setObject(1, amount, java.sql.Types.DECIMAL, 2);
```

Với dữ liệu tiền tệ, `setBigDecimal` thường dễ đọc hơn. Overload có scale có thể thực hiện chuyển đổi/làm tròn theo hợp đồng và driver; **đừng dựa vào nó làm quy tắc làm tròn nghiệp vụ**. Nếu ứng dụng quy định chỉ chấp nhận đúng hai chữ số thập phân:

```java
BigDecimal validated = amount.setScale(2, RoundingMode.UNNECESSARY);
statement.setBigDecimal(1, validated);
```

Đoạn này giả định đã import `java.math.BigDecimal` và `java.math.RoundingMode`. `UNNECESSARY` sẽ gây `ArithmeticException` nếu giá trị cần làm tròn. Nếu nghiệp vụ cho phép làm tròn, hãy chọn rõ quy tắc như `HALF_UP` hoặc `HALF_EVEN` thay vì phó mặc cho database.

## 4. Ví dụ đầy đủ: INSERT với nhiều kiểu tham số

Giả sử ứng dụng có bảng hóa đơn. DDL dưới đây minh họa các kiểu quan hệ phổ biến (cú pháp boolean/timestamp có thể khác giữa DB):

```sql
CREATE TABLE invoices (
    id            BIGINT PRIMARY KEY,
    invoice_code  VARCHAR(64) NOT NULL,
    total_amount  DECIMAL(12, 2) NOT NULL,
    issued_on     DATE NOT NULL,
    reviewed_at   TIMESTAMP NOT NULL,
    paid          BOOLEAN NOT NULL,
    note          VARCHAR(500)
);
```

Chúng ta dùng record Java để truyền dữ liệu có kiểu rõ ràng. `issuedOn` là **ngày lịch**, `reviewedAt` là **ngày giờ địa phương không có offset**, và `note` có thể bằng `null`.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Objects;
import javax.sql.DataSource;

public final class InvoiceDao {
    public record NewInvoice(
            long id,
            String invoiceCode,
            BigDecimal totalAmount,
            LocalDate issuedOn,
            LocalDateTime reviewedAt,
            boolean paid,
            String note) {}

    private final DataSource dataSource;

    public InvoiceDao(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public long insert(NewInvoice value) throws SQLException {
        Objects.requireNonNull(value);
        Objects.requireNonNull(value.invoiceCode());
        Objects.requireNonNull(value.totalAmount());
        Objects.requireNonNull(value.issuedOn());
        Objects.requireNonNull(value.reviewedAt());

        String sql = """
                INSERT INTO invoices (
                    id, invoice_code, total_amount, issued_on,
                    reviewed_at, paid, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            // Các setter có kiểu cụ thể:
            statement.setLong(1, value.id());
            statement.setString(2, value.invoiceCode());
            statement.setBigDecimal(3,
                    value.totalAmount().setScale(2, RoundingMode.UNNECESSARY));

            // Java time qua JDBC 4.2:
            statement.setObject(4, value.issuedOn());
            statement.setObject(5, value.reviewedAt(), Types.TIMESTAMP);

            statement.setBoolean(6, value.paid());

            // NULL có kiểu SQL rõ ràng:
            if (value.note() == null) {
                statement.setNull(7, Types.VARCHAR);
            } else {
                statement.setString(7, value.note());
            }

            int affectedRows = statement.executeUpdate();
            if (affectedRows != 1) {
                throw new SQLException(
                        "INSERT dự kiến ảnh hưởng 1 dòng, thực tế: " + affectedRows);
            }
            return value.id();
        }
    }
}
```

**Phân tích lựa chọn API:**

1. `id` là `BIGINT`: `setLong()` chuyển đúng loại giá trị nguyên 64 bit.
2. `invoice_code` là `VARCHAR`: `setString()` biểu đạt chính xác dữ liệu văn bản.
3. `total_amount` là `DECIMAL(12,2)`: `setBigDecimal()` tránh biểu diễn nhị phân không chính xác của `double`.
4. `issued_on` là `DATE`: truyền `LocalDate` bằng `setObject()` trên driver hỗ trợ ánh xạ JDBC 4.2.
5. `reviewed_at` là `TIMESTAMP`: truyền `LocalDateTime` và khai báo target `Types.TIMESTAMP` để diễn đạt kiểu SQL đích.
6. `paid` là boolean: dùng `setBoolean()` cho cột boolean hoặc tương đương mà driver hỗ trợ.
7. `note` có thể không có giá trị: dùng `setNull(7, Types.VARCHAR)`, không dựa vào suy luận kiểu từ `null`.

Ví dụ dùng một SQL `INSERT` và tự đóng statement/connection với `try-with-resources`. Nếu một nghiệp vụ cần nhiều câu lệnh ghi chung một transaction, mọi lệnh phải sử dụng **cùng kết nối trong transaction đó**; không gọi `getConnection()` riêng cho từng bước rồi giả định có thể rollback cả chuỗi.

Một số driver cũ hoặc hệ quản trị không hỗ trợ đầy đủ ánh xạ Java Time của JDBC 4.2. Khi đó cần giải pháp tương thích rõ ràng, ví dụ `setDate(index, java.sql.Date.valueOf(localDate))` hoặc `setTimestamp(index, java.sql.Timestamp.valueOf(localDateTime))` khi **ý nghĩa thời gian** của cột cho phép. Không đổi kiểu chỉ để “hết lỗi” nếu nó làm thay đổi ngữ nghĩa timezone.

## 5. NULL: chọn kiểu đích trước khi truyền giá trị vắng mặt

`NULL` trong SQL có nghĩa “không có giá trị được biết”, khác với số `0`, chuỗi rỗng và boolean `false`. Kiểu tham số vẫn quan trọng dù giá trị là NULL.

**Nên dùng:**

```java
statement.setNull(1, java.sql.Types.VARCHAR);
statement.setNull(2, java.sql.Types.INTEGER);
statement.setNull(3, java.sql.Types.DECIMAL);

// Cũng có thể khai báo kiểu SQL đích khi dùng setObject:
statement.setObject(4, null, java.sql.Types.DATE);
```

**Cần thận trọng với:**

```java
statement.setObject(1, null); // Không nêu target SQL type
```

Lời gọi này có thể hoạt động ở một driver và thất bại hoặc bị diễn giải khác ở driver khác, đặc biệt khi server cần suy luận kiểu từ tham số hoặc truy vấn có phép toán/overload. Thêm kiểu `Types.VARCHAR`, `Types.DATE`, `Types.DECIMAL`... dựa trên schema sẽ rõ ràng hơn. Một số kiểu DB đặc thù có thể yêu cầu `Types.OTHER` cùng tên type của database hoặc API riêng; không tự ý dùng `Types.OTHER` cho tất cả kiểu khi chưa kiểm tra driver.

Cẩn thận với các kiểu Java được đóng hộp:

```java
Integer quantity = null;

// Sai: tự unbox null trước khi JDBC nhận giá trị.
// statement.setInt(1, quantity); // NullPointerException

if (quantity == null) {
    statement.setNull(1, java.sql.Types.INTEGER);
} else {
    statement.setInt(1, quantity);
}
```

`setString(index, null)` hoặc `setBytes(index, null)` có thể được driver xử lý thành SQL NULL, nhưng **đọc code sẽ không thể hiện chính xác kiểu SQL mong muốn như `setNull()`** và có thể phụ thuộc driver/cột. Với nullable primitive wrapper, tránh để Java tự unbox `null`.

Nếu cần phân biệt “cột không tồn tại trong request” với “người dùng muốn cập nhật cột thành SQL NULL”, chỉ một giá trị Java `null` chưa đủ; nên thiết kế model đầu vào biểu thị rõ ba trạng thái: không thay đổi, đặt NULL hoặc đặt một giá trị.

## 6. Kiểu ngày giờ: đừng nhầm ngày, local time và instant

Ngày giờ là nơi `setObject()` đặc biệt hữu ích nhờ các kiểu `java.time` của Java hiện đại, nhưng **ngữ nghĩa cột phải được xác định trước**.

| Nhu cầu | Kiểu Java nên cân nhắc | Kiểu SQL thường gặp | API/điểm cần chú ý |
|---|---|---|---|
| Chỉ ngày, không có giờ | `LocalDate` | `DATE` | `setObject(index, localDate)` trên driver JDBC 4.2 |
| Chỉ giờ trong ngày | `LocalTime` | `TIME` | `setObject(index, localTime)` nếu được hỗ trợ |
| Ngày giờ không có timezone | `LocalDateTime` | `TIMESTAMP` | Không chứa offset/timezone |
| Thời điểm có offset | `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` hoặc tương đương | `setObject()` khi driver hỗ trợ; cách lưu offset có thể khác |
| Thời điểm tuyệt đối trong ứng dụng | `Instant` | Phụ thuộc schema/driver | Không mặc định JDBC có mapping trực tiếp cho mọi DB |

`LocalDateTime` diễn đạt “2026-11-16 09:30” nhưng **không xác định** 09:30 theo múi giờ nào. `Instant` biểu diễn một thời điểm trên dòng thời gian UTC, còn `OffsetDateTime` mang cả ngày giờ và UTC offset. Với sự kiện cần chính xác thời điểm xảy ra, hãy chọn quy ước lưu dữ liệu và cách chuyển đổi nhất quán giữa client, server và ứng dụng.

Ví dụ, khi database/driver hỗ trợ đúng kiểu `TIMESTAMP WITH TIME ZONE`:

```java
OffsetDateTime createdAt =
        OffsetDateTime.parse("2026-11-16T09:30:00+07:00");
statement.setObject(1, createdAt, java.sql.Types.TIMESTAMP_WITH_TIMEZONE);
```

Không giả định cột giữ nguyên tên vùng như `Asia/Ho_Chi_Minh`; nhiều hệ quản trị chuẩn hóa thành thời điểm hoặc offset, không lưu zone ID ban đầu. Nếu ứng dụng cần phục dựng lịch hẹn theo múi giờ dân sự, có thể cần lưu riêng zone ID như `Asia/Ho_Chi_Minh`.

Các setter cũ `setDate()`, `setTime()`, `setTimestamp()` nhận kiểu `java.sql.*`; với driver sử dụng timezone mặc định để diễn giải giá trị, kết quả có thể thay đổi theo cấu hình máy chủ/JVM. Một số overload nhận `Calendar` khi cần kiểm soát phép chuyển đổi trong API legacy. Hãy kiểm thử với timezone khác nhau và thời điểm đổi giờ mùa hè nếu dữ liệu liên quan.

## 7. Các trường hợp chuyên biệt: binary, UUID, JSON, array và enum

`setXxx()` và `setObject()` không thay thế nhau tuyệt đối; với kiểu đặc biệt, phương thức phù hợp có thể khác.

| Dữ liệu | Cách tiếp cận | Điều phải kiểm tra |
|---|---|---|
| Nhị phân nhỏ trong `VARBINARY` | `setBytes(index, bytes)` | Giới hạn kích thước cột, RAM giữ mảng |
| Tệp lớn/BLOB | `setBinaryStream(index, stream, length)` hoặc API `setBlob` | Driver có hỗ trợ stream cho cột, vòng đời stream |
| `UUID` | `setObject(index, uuid)` nếu driver hỗ trợ native UUID; hoặc `setString()` khi cột lưu văn bản | Kiểu SQL thực tế và binding vendor-specific |
| JSON/JSONB | Chuỗi JSON hoặc đối tượng riêng của driver/`setObject` với kiểu đích | Driver và DB có thể yêu cầu cast, type wrapper hoặc `Types.OTHER` |
| SQL ARRAY | `Connection.createArrayOf()` và `setArray()` khi được hỗ trợ | Kiểu phần tử, driver, gọi `Array.free()` khi phù hợp |
| Enum nghiệp vụ | Dùng mã chuỗi hoặc số rõ ràng; ánh xạ theo schema | Khi đổi tên enum phải tính đến tương thích dữ liệu |
| Cột XML / CLOB | `setSQLXML()`, `setCharacterStream()` hoặc API chuyên biệt | Đúng kiểu văn bản và bộ mã, dọn tài nguyên |

Với tệp lớn, đừng gọi `Files.readAllBytes()` rồi `setBytes()` chỉ vì API ngắn; ứng dụng có thể phải giữ toàn bộ tệp trong heap. Ví dụ:

```java
try (InputStream file = Files.newInputStream(path);
     PreparedStatement statement = connection.prepareStatement(
             "INSERT INTO attachments (id, payload) VALUES (?, ?)")) {

    statement.setLong(1, attachmentId);
    statement.setBinaryStream(2, file, Files.size(path));
    statement.executeUpdate();
}
```

Đoạn này giả định `connection`, `path` và `attachmentId` đã có, cùng các import `java.io.InputStream`, `java.nio.file.Files` và `java.sql.PreparedStatement`. Đặc biệt, phải giữ stream mở trong lúc statement thực thi. Khi kích thước file có thể thay đổi giữa lúc gọi `Files.size()` và đọc, cần có cơ chế ổn định nguồn và giới hạn upload phù hợp.

Đừng dùng `setObject(index, enumValue)` rồi kỳ vọng driver biết ý nghĩa enum Java, hay truyền đối tượng JSON bất kỳ và mặc định database tự lưu đúng. **Chủ động chỉ rõ serialization, kiểu SQL và phép chuyển đổi được hỗ trợ**.

## 8. Những lỗi thường gặp khi bind tham số

| Lỗi | Biểu hiện | Cách sửa |
|---|---|---|
| Dùng chỉ số 0 thay vì 1 | `SQLException` / parameter index out of range | Đánh số dấu `?` từ 1 |
| Bỏ sót một placeholder | Driver báo thiếu giá trị cho tham số | Đối chiếu số `?` và mọi setter |
| Bind sai thứ tự | Truy vấn trả sai/không có dữ liệu hoặc lỗi chuyển kiểu | Đặt constant/chú thích cho tham số phức tạp, kiểm tra SQL cùng mapping |
| Dùng `setString()` cho giá trị số để tiện xử lý | Driver/DB phải ép kiểu, có thể lỗi hoặc ảnh hưởng cách chọn kế hoạch | Dùng `setInt()`, `setLong()`, `setBigDecimal()` đúng kiểu |
| Dùng `setDouble()` cho tiền | Sai số biểu diễn, đối chiếu giá trị khó hiểu | Dùng `BigDecimal` và `DECIMAL` |
| Gọi `setObject(index, null)` khi cần kiểu rõ | Server không xác định SQL type hoặc chọn sai overload | Dùng `setNull()` hoặc `setObject(..., targetSqlType)` |
| Đưa `LocalDateTime` vào cột ghi nhận instant | Sai offset/ý nghĩa sự kiện | Thống nhất kiểu, timezone và phép chuyển đổi |
| Truyền class vendor-specific không được hỗ trợ | `SQLFeatureNotSupportedException`, lỗi cast/SQL type | Kiểm tra driver và quy tắc chuyển kiểu |
| Dùng dấu `?` cho tên bảng/cột | SQL sai hoặc `ORDER BY` không có tác dụng mong đợi | Dùng allowlist identifier |
| Ghép giá trị vào SQL bằng chuỗi | SQL injection và lỗi escaping | Dùng placeholder và setter |
| Giữ lại tham số cũ khi tái sử dụng statement | Truy vấn tiếp theo sử dụng dữ liệu không mong muốn | Bind đầy đủ mỗi lần, `clearParameters()` khi có lý do |

### Ví dụ: danh sách IN động

Một dấu `?` đại diện **một giá trị**, không đại diện cho cả danh sách `IN`. Cách đúng là tạo số placeholder theo số phần tử, sau khi đã giới hạn số phần tử và lựa chọn SQL có kiểm soát:

```java
List<Long> ids = List.of(10L, 20L, 30L);
String placeholders =
        String.join(", ", java.util.Collections.nCopies(ids.size(), "?"));
String sql = "SELECT id FROM orders WHERE id IN (" + placeholders + ")";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        statement.setLong(i + 1, ids.get(i));
    }
    try (ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            System.out.println(rows.getLong("id"));
        }
    }
}
```

Mã ví dụ giả định `connection` đã mở và đã import `java.util.List`, `java.sql.PreparedStatement`, `java.sql.ResultSet`. Cần xử lý danh sách **rỗng** trước khi tạo `IN ()` vì cú pháp có thể không hợp lệ, và không tạo vô hạn placeholder vì database có thể giới hạn số tham số. Một số hệ quản trị có hỗ trợ array parameter hoặc bảng tạm cho danh sách lớn.

## 9. Hiệu năng và tính di động giữa các driver

Không có quy luật rằng `setObject` luôn chậm hơn `setXxx`. Chi phí đáng kể thường đến từ kết nối mạng, câu SQL, bộ lập kế hoạch truy vấn, số hàng trả về, index và transaction. Điểm cần ưu tiên khi chọn setter là **đúng kiểu và dễ kiểm tra**.

Tuy vậy, kiểu tham số thực tế có thể ảnh hưởng cách DB suy luận và lên kế hoạch truy vấn. Ví dụ tham số văn bản cho cột số hoặc kiểu ngày không được nhận diện chính xác có thể kích hoạt ép kiểu, lỗi toán tử hoặc thay đổi khả năng sử dụng index tùy DB. Vì vậy, một ứng dụng chạy đúng trên H2 chưa chắc đúng hệt trên PostgreSQL, MySQL hay SQL Server khi dùng kiểu vendor-specific.

Các thực hành hữu ích:

1. **Reuse SQL có placeholder** và bind đầy đủ tham số mỗi lần; DB/driver có thể tận dụng chuẩn bị và cache statement theo chính sách cụ thể.
2. **Dùng connection pool đúng cách**, đóng `Connection`/`PreparedStatement`/`ResultSet` bằng `try-with-resources`. Với pool, `Connection.close()` thường trả connection về pool.
3. **Dùng batch khi thích hợp**: bind một bộ tham số, gọi `addBatch()`, rồi lặp và `executeBatch()`. Hiệu quả phụ thuộc driver, ràng buộc, kích thước batch và transaction.
4. **Không phụ thuộc hoàn toàn vào `ParameterMetaData`** để suy kiểu của các tham số trống: mức hỗ trợ và chi phí lấy metadata khác nhau theo driver, SQL và server.
5. **Kiểm tra số hàng ảnh hưởng và lỗi SQL**, đặc biệt khi nullable, precision hoặc conversion là phần của hợp đồng nghiệp vụ.

Ví dụ batch nhỏ:

```java
String sql = "INSERT INTO audit_events (event_id, event_text) VALUES (?, ?)";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (AuditEvent event : events) {
        statement.setLong(1, event.id());
        statement.setString(2, event.text());
        statement.addBatch();
    }
    int[] counts = statement.executeBatch();
    // Diễn giải counts theo hợp đồng JDBC và driver.
}
```

Đoạn này giả định `connection`, `events` và kiểu `AuditEvent` đã có. Một số phần tử `counts` có thể là các hằng như `Statement.SUCCESS_NO_INFO`, không nhất thiết bằng 1; khi batch thất bại, kiểm tra `BatchUpdateException` và trạng thái transaction. Việc chọn setter vẫn nên nhất quán với kiểu cột cho mọi phần tử của batch.

## 10. Sơ đồ quyết định chọn setter

```text
Biết kiểu SQL đích?
  |
  +-- Có: kiểu Java/SQL rõ ràng?
  |       |
  |       +-- Có setter trực tiếp phù hợp?
  |       |       |
  |       |       +-- Có  -> dùng setString/setLong/setBigDecimal/...
  |       |       +-- Không -> cân nhắc setObject với target SQL type
  |       |
  |       +-- Dữ liệu có thể NULL?
  |               |
  |               +-- Có  -> setNull(index, Types.XXX)
  |               +-- Không -> bind giá trị theo kiểu thích hợp
  |
  +-- Chưa rõ: kiểm tra schema/metadata và hợp đồng API
           |
           +-- Không dùng setObject(Object) để che sự mơ hồ kiểu dữ liệu
```

Có thể ghi nhớ theo thứ tự:

- **Giá trị nguyên/văn bản/tiền tệ đã rõ kiểu:** ưu tiên setter tường minh.
- **Ngày giờ theo Java Time hoặc kiểu đối tượng được driver hỗ trợ:** cân nhắc `setObject()`; chỉ định target SQL type khi cần.
- **Giá trị NULL:** chọn `setNull()` cùng kiểu SQL, hoặc overload `setObject` có target type.
- **Giá trị database-specific:** đọc tài liệu driver, viết phép chuyển đổi rõ ràng và kiểm thử tích hợp.
- **Dữ liệu lớn:** xét streaming API thay vì giữ mọi thứ trong `byte[]`.

Đây là nguyên tắc thiết kế, không phải yêu cầu mọi dòng code phải dùng một setter duy nhất. Mục tiêu là làm cho **ý nghĩa kiểu dữ liệu, lỗi chuyển đổi và tính tương thích** trở nên dễ thấy.

## 11. Kịch bản kiểm thử và câu hỏi vận dụng

### Kiểm thử tích hợp cần có

| Kịch bản | Điều cần xác minh |
|---|---|
| Lưu `BigDecimal("15.20")` vào `DECIMAL(12,2)` | Đọc lại đúng `15.20`, không phát sinh sai số do `double` |
| Lưu giá trị có hơn 2 chữ số thập phân | Ứng dụng xử lý làm tròn/từ chối theo quy tắc nghiệp vụ |
| Bind `NULL` vào `VARCHAR`, `DATE` | Driver chấp nhận kiểu đích; đọc lại là SQL NULL |
| Bind `LocalDate` vào `DATE` | Ngày không thay đổi sau round trip |
| Bind `LocalDateTime` vào `TIMESTAMP` | Giữ ý nghĩa ngày giờ đã định nghĩa, không vô tình suy ra instant |
| Bind `OffsetDateTime` vào timestamp có timezone | Kiểm tra instant/offset theo quy ước driver và DB |
| Bind `UUID` vào cột UUID native | Xác định driver có hỗ trợ kiểu Java đó hay cần phương án khác |
| Bind sai kiểu: chuỗi không hợp lệ vào số | Kiểm tra loại lỗi và cách ứng dụng báo lỗi |
| Batch nhiều bộ tham số | Xử lý thành công, thất bại và rollback đúng hợp đồng |

Chạy các kiểm thử quan trọng trên **driver và database mục tiêu**, không chỉ database in-memory dùng cho unit test.

### Câu hỏi tự luyện

**1.** Cột `unit_price DECIMAL(12,2)` cần lưu `19.99`. Vì sao `setBigDecimal()` thường phù hợp hơn `setDouble()`? Điều gì cần làm nếu ứng dụng nhận giá trị `19.999`?

**2.** Tham số `nickname` có kiểu Java `String` nhưng đôi khi bằng `null`. Có nên gọi `setObject(index, null)` không? Hãy viết nhánh bind có target `Types.VARCHAR` rõ ràng.

**3.** Cột `created_at` có ý nghĩa thời điểm tuyệt đối. Vì sao `LocalDateTime` có thể không đủ? Bạn sẽ đánh giá cách dùng `OffsetDateTime` và kiểu timestamp trên database thế nào?

**4.** MySQL chấp nhận `setString(1, "123")` để tìm cột số nguyên, nhưng hệ quản trị khác báo lỗi chuyển kiểu. Lỗi ở tầng thiết kế binding là gì và nên sửa ở đâu?

**5.** API cho người dùng chọn `sortBy=created_at` hoặc `sortBy=amount`. Có nên viết `ORDER BY ?` rồi dùng `setString()`? Cách thiết kế an toàn là gì?

**6.** Một lớp DAO dùng `setObject(index, customObject)` để ghi JSON native nhưng driver không nhận kiểu Java ấy. Những lựa chọn nào có thể kiểm tra để xử lý rõ nghĩa?

**Ghi nhớ:** `setXxx` làm rõ kiểu giá trị khi truyền vào SQL; `setObject` thuận tiện cho ánh xạ tổng quát, Java Time và một số kiểu dữ liệu do driver hỗ trợ. Chọn setter dựa trên **kiểu SQL đích, ý nghĩa dữ liệu và khả năng của driver**; với `NULL`, tiền tệ, thời gian và kiểu đặc thù, phải kiểm tra rõ phép chuyển đổi thay vì phó mặc cho suy luận ngầm.

