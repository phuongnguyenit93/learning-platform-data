# Ánh xạ kiểu dữ liệu giữa MySQL, JDBC và mô hình miền Java

Một ứng dụng Java làm việc với MySQL qua JDBC phải chuyển đổi dữ liệu qua ba lớp: kiểu cột trong MySQL, kiểu SQL mà JDBC nhận diện và kiểu Java mà ứng dụng sử dụng. Chọn đúng kiểu ở cả ba lớp giúp giữ nguyên giá trị, tránh mất độ chính xác, xử lý múi giờ nhất quán và biểu diễn đúng ý nghĩa nghiệp vụ.

Ví dụ, cột tiền `DECIMAL(14,2)` nên đi qua JDBC bằng `BigDecimal` và được biểu diễn trong mô hình miền bằng một kiểu tiền tệ dựa trên `BigDecimal`. Cột ngày lịch `DATE` phù hợp với `LocalDate`. Cột `TIMESTAMP` biểu diễn một thời điểm trên dòng thời gian và cần quy ước múi giờ rõ ràng trước khi chuyển thành `Instant`. Nếu chỉ chọn kiểu Java theo thói quen, dữ liệu có thể bị làm tròn, tràn số hoặc lệch thời gian.

Bài học này thuộc module `DATABASE_MYSQL`, bao gồm thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, tối ưu truy vấn, phân quyền và vận hành cơ sở dữ liệu quan hệ. Nội dung tập trung vào JDBC trực tiếp và cách giữ ranh giới rõ ràng giữa schema lưu trữ, lớp truy cập dữ liệu và mô hình miền Java.

Các ví dụ dùng JDBC 4.2 và cú pháp Java hiện đại (record, switch expression). Thuộc tính kết nối của Connector/J cần được đối chiếu với đúng phiên bản driver mà dự án đang sử dụng.

Sau bài học, bạn có thể:

- Đọc bảng ánh xạ phổ biến giữa MySQL, JDBC và Java.
- Chọn kiểu Java có miền giá trị và độ chính xác phù hợp với cột MySQL.
- Xử lý `UNSIGNED`, `DECIMAL`, `NULL` và dữ liệu thời gian an toàn.
- Dùng `PreparedStatement`, `ResultSet` và JDBC 4.2 để truyền/nhận kiểu dữ liệu.
- Ánh xạ `ENUM`, `JSON`, `BIT` và các kiểu đặc thù của MySQL có kiểm soát.
- Thiết kế repository và mô hình miền mà không để chi tiết JDBC lan khắp ứng dụng.
- Kiểm thử việc ánh xạ trên đúng MySQL và phiên bản Connector/J triển khai.

## 1. Ba lớp kiểu dữ liệu

Khi đọc một hàng dữ liệu, JDBC driver nhận kiểu của cột MySQL, chuyển nó thành kiểu JDBC phù hợp và cung cấp cho Java thông qua các phương thức như `ResultSet.getLong()`, `getBigDecimal()` hoặc `getObject()`.

```text
MySQL column type
       |
       v
MySQL Connector/J
  - đọc metadata
  - chuyển đổi giá trị
       |
       v
JDBC type / API
  - Types.BIGINT
  - Types.DECIMAL
  - Types.TIMESTAMP
       |
       v
Java type
  - Long
  - BigDecimal
  - LocalDateTime / Timestamp
       |
       v
Domain model
  - OrderId
  - Money
  - Instant / LocalDateTime
```

JDBC định nghĩa hợp đồng chung, còn Connector/J là driver cụ thể thực hiện việc chuyển đổi MySQL. Vì vậy, ánh xạ có thể phụ thuộc phiên bản driver và một số thuộc tính cấu hình. Các bảng trong bài là hướng dẫn thực hành phổ biến; hãy kiểm tra `DatabaseMetaData`, tài liệu đúng phiên bản Connector/J và integration test của ứng dụng trước khi dựa vào một hành vi đặc thù.

Không nên để kiểu lưu trữ quyết định trực tiếp toàn bộ mô hình miền. Repository có nhiệm vụ chuyển dữ liệu giữa JDBC và domain. Ví dụ, database có thể lưu `order_status` dưới dạng `VARCHAR` hoặc `ENUM`, nhưng domain dùng `OrderStatus`; database lưu số tiền dưới dạng `DECIMAL`, còn domain dùng `Money` chứa số tiền và mã tiền tệ.

## 2. Bảng ánh xạ các kiểu phổ biến

Bảng sau mô tả kiểu Java thường dùng với MySQL qua Connector/J. JDBC type là loại JDBC thường được báo qua metadata; một số kiểu MySQL đặc thù có thể được driver báo dưới dạng tương thích như `VARCHAR`, `LONGVARCHAR` hoặc kiểu khác tùy phiên bản.

| MySQL | JDBC thường gặp | Java thường dùng | Ghi chú |
| --- | --- | --- | --- |
| `TINYINT` signed | `TINYINT` | `Byte` / `byte` | Miền -128 đến 127 |
| `TINYINT UNSIGNED` | `TINYINT` hoặc kiểu tương thích | `Short` / `short` | Miền 0 đến 255, không vừa `Byte` |
| `SMALLINT` | `SMALLINT` | `Short` / `short` | Signed |
| `SMALLINT UNSIGNED` | `SMALLINT` hoặc kiểu tương thích | `Integer` / `int` | Cần miền đến 65,535 |
| `MEDIUMINT` | `INTEGER` | `Integer` / `int` | 3 byte trong MySQL |
| `INT` | `INTEGER` | `Integer` / `int` | Signed |
| `INT UNSIGNED` | `INTEGER` hoặc kiểu tương thích | `Long` / `long` | Miền dương vượt giới hạn Integer |
| `BIGINT` | `BIGINT` | `Long` / `long` | Signed 64-bit |
| `BIGINT UNSIGNED` | `BIGINT` hoặc kiểu tương thích | `BigInteger` hoặc `BigDecimal` | Miền MySQL rộng hơn `Long` |
| `DECIMAL`, `NUMERIC` | `DECIMAL`, `NUMERIC` | `BigDecimal` | Dùng cho giá trị thập phân chính xác |
| `FLOAT` | `REAL` hoặc `FLOAT` | `Float` / `float` | Số gần đúng |
| `DOUBLE` | `DOUBLE` | `Double` / `double` | Số gần đúng, độ chính xác lớn hơn FLOAT |
| `CHAR`, `VARCHAR` | `CHAR`, `VARCHAR` | `String` | Chịu ảnh hưởng charset/collation ở phía SQL |
| `TINYTEXT`, `TEXT`, `MEDIUMTEXT`, `LONGTEXT` | `VARCHAR` hoặc `LONGVARCHAR` | `String` | Chú ý kích thước dữ liệu và giới hạn truyền |
| `BINARY`, `VARBINARY` | `BINARY`, `VARBINARY` | `byte[]` | Dữ liệu byte, không phải văn bản |
| `BLOB` và biến thể | `BLOB` hoặc `LONGVARBINARY` | `byte[]`, `Blob` hoặc stream | Chọn theo kích thước và cách đọc |
| `DATE` | `DATE` | `LocalDate` | JDBC 4.2; `java.sql.Date` là API cũ |
| `TIME` | `TIME` | `LocalTime` trong trường hợp giờ trong ngày | MySQL TIME còn biểu diễn thời lượng âm hoặc trên 24 giờ |
| `DATETIME` | `TIMESTAMP` | `LocalDateTime` | Không chứa múi giờ |
| `TIMESTAMP` | `TIMESTAMP` | `Timestamp`, chuyển sang `Instant` theo cấu hình múi giờ | Có chuyển đổi theo múi giờ session MySQL |
| `YEAR` | Phụ thuộc driver/metadata | `Integer` hoặc kiểu tương thích | Xác minh mapping, có thể ép kiểu số trong SQL |
| `BIT(1)` | `BIT` hoặc `BOOLEAN` | `Boolean` | Cần kiểm tra cấu hình driver |
| `BIT(M)` với M lớn hơn 1 | `BIT` hoặc kiểu nhị phân | `byte[]` hoặc kiểu số phù hợp | Kiểm tra thứ tự byte và chiều dài |
| `ENUM`, `SET` | Thường là `VARCHAR` | `String` | Chuyển sang enum/domain type tại repository |
| `JSON` | Thường là `LONGVARCHAR` hoặc kiểu vendor | `String` rồi parse JSON | JDBC không có kiểu JSON chuẩn dùng chung |

Các kiểu primitive Java như `int`, `long`, `boolean` không thể biểu diễn `NULL`. Với cột nullable, dùng wrapper (`Integer`, `Long`, `Boolean`), `BigDecimal`, kiểu tham chiếu hoặc chuyển thành `Optional` ở ranh giới domain.

## 3. Số nguyên và thuộc tính UNSIGNED

MySQL có các kiểu số nguyên với kích thước khác nhau. Khi ánh xạ sang Java, phải xét cả signedness, không chỉ tên kiểu.

### 3.1. Ánh xạ số nguyên signed

Với cột signed thông thường:

- `TINYINT` → `Byte`.
- `SMALLINT` → `Short`.
- `MEDIUMINT` và `INT` → `Integer`.
- `BIGINT` → `Long`.

Ví dụ schema:

```sql
CREATE TABLE inventory (
    item_id BIGINT NOT NULL,
    available_quantity INT NOT NULL,
    PRIMARY KEY (item_id)
) ENGINE = InnoDB;
```

Domain model tương ứng:

```java
public record InventoryItem(
    long itemId,
    int availableQuantity
) {}
```

Nếu giá trị có thể vắng mặt, dùng `Long` và `Integer` thay cho primitive.

### 3.2. Vì sao UNSIGNED cần xử lý riêng?

Java không có kiểu primitive unsigned tương ứng đầy đủ với các kiểu số nguyên MySQL. Ví dụ:

| MySQL | Miền dương tối đa | Kiểu Java nên cân nhắc |
| --- | ---: | --- |
| `TINYINT UNSIGNED` | 255 | `Short` |
| `SMALLINT UNSIGNED` | 65,535 | `Integer` |
| `MEDIUMINT UNSIGNED` | 16,777,215 | `Integer` |
| `INT UNSIGNED` | 4,294,967,295 | `Long` |
| `BIGINT UNSIGNED` | 18,446,744,073,709,551,615 | `BigInteger` |

`BIGINT UNSIGNED` có miền lớn hơn giá trị tối đa của Java `long`. Nếu hệ thống chỉ dùng giá trị đến `Long.MAX_VALUE`, bạn có thể quy định giới hạn đó trong hợp đồng dữ liệu và dùng `Long`. Nếu cần toàn bộ miền unsigned, hãy dùng `BigInteger` ở domain và kiểm thử chuyển đổi với đúng Connector/J.

Một cách lấy giá trị `BIGINT UNSIGNED` chính xác là đọc qua `BigDecimal`, sau đó chuyển sang `BigInteger`:

```java
BigDecimal raw = resultSet.getBigDecimal("external_id");
BigInteger externalId = raw == null ? null : raw.toBigIntegerExact();
```

`toBigIntegerExact()` ném lỗi nếu giá trị có phần thập phân khác 0, giúp tránh cắt bỏ thông tin âm thầm. Khi ghi, có thể chuyển `BigInteger` sang `BigDecimal`:

```java
preparedStatement.setBigDecimal(1, new BigDecimal(externalId));
```

Không ép `BIGINT UNSIGNED` lớn thành `long` bằng cách cast. Giá trị vượt `Long.MAX_VALUE` sẽ không còn được biểu diễn đúng theo số nguyên có dấu Java.

### 3.3. Kiểm tra giá trị nullable

Khi dùng getter primitive như `getInt()` hoặc `getLong()`, JDBC trả `0` nếu SQL value là `NULL`; cần gọi `wasNull()` ngay sau getter để phân biệt:

```java
int quantity = resultSet.getInt("quantity");
Integer nullableQuantity = resultSet.wasNull() ? null : quantity;
```

Với JDBC 4.1+ và driver hỗ trợ đầy đủ, có thể dùng `getObject` với wrapper:

```java
Integer quantity = resultSet.getObject("quantity", Integer.class);
Long parentId = resultSet.getObject("parent_id", Long.class);
```

Cách này thể hiện rõ `NULL` hơn. Hãy kiểm tra khả năng chuyển đổi của Connector/J cho từng kiểu và phiên bản đang dùng.

## 4. DECIMAL và BigDecimal

`DECIMAL(p,s)` trong MySQL dùng số thập phân chính xác. Java `BigDecimal` là kiểu phù hợp để giữ precision và scale của giá trị này.

Không dùng `double` hoặc `float` làm trung gian cho tiền. Không khởi tạo `BigDecimal` từ một literal `double` nếu cần giá trị thập phân chính xác:

```java
// Không nên: giá trị double đã có thể chứa sai số nhị phân
BigDecimal wrong = new BigDecimal(0.1);

// Nên: tạo từ chuỗi thập phân
BigDecimal price = new BigDecimal("0.10");
```

### 4.1. Ghi và đọc DECIMAL bằng JDBC

```java
String sql = "INSERT INTO product_prices (product_id, unit_price) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 1001L);
    statement.setBigDecimal(2, new BigDecimal("1299.90"));
    statement.executeUpdate();
}

String query = "SELECT unit_price FROM product_prices WHERE product_id = ?";
try (PreparedStatement statement = connection.prepareStatement(query)) {
    statement.setLong(1, 1001L);
    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            BigDecimal unitPrice = rs.getBigDecimal("unit_price");
        }
    }
}
```

`setBigDecimal()` và `getBigDecimal()` tránh chuyển qua số dấu phẩy động. Cần quy định scale trong domain hoặc service. Nếu nghiệp vụ yêu cầu làm tròn, chỉ rõ `RoundingMode`:

```java
BigDecimal amount = new BigDecimal("19.995");
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
```

Không tự động làm tròn mọi giá trị ngay khi đọc từ database. Hãy xác định chính sách làm tròn ở đúng bước nghiệp vụ, ví dụ khi tính thuế, phân bổ chiết khấu hoặc tạo dòng thanh toán.

### 4.2. Scale và precision của domain

MySQL có thể lưu `DECIMAL(14,2)`, nhưng `BigDecimal` tự nó không giới hạn scale. Domain cần kiểm tra precision/scale trước khi ghi để tránh dữ liệu không hợp lệ:

```java
static BigDecimal requireMoneyAmount(BigDecimal value) {
    if (value == null) {
        throw new IllegalArgumentException("amount is required");
    }
    BigDecimal normalized;
    try {
        normalized = value.setScale(2, RoundingMode.UNNECESSARY);
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException("amount has more than 2 meaningful decimal places", ex);
    }
    if (normalized.abs().compareTo(new BigDecimal("999999999999.99")) > 0) {
        throw new IllegalArgumentException("amount exceeds DECIMAL(14,2)");
    }
    return normalized;
}
```

Ví dụ này chấp nhận scale có thể chuẩn hóa mà không làm tròn (chẳng hạn `1.230`) và từ chối phần lẻ có ý nghĩa vượt 2 chữ số (chẳng hạn `1.234`). Nó cũng kiểm tra giới hạn 12 chữ số phần nguyên của `DECIMAL(14,2)`. Quy tắc cho phép số âm hay không vẫn phải do nghiệp vụ quyết định.

## 5. Chuỗi, enum và dữ liệu nhị phân

### 5.1. CHAR, VARCHAR và TEXT

Các kiểu văn bản MySQL thường được ánh xạ sang `String`. JDBC driver xử lý charset và chuyển byte thành ký tự. Với tiếng Việt, cấu hình schema và connection phải thống nhất charset như `utf8mb4`.

```java
String fullName = resultSet.getString("full_name");
statement.setString(1, fullName);
```

Không dùng `getBytes()` để đọc cột văn bản trừ khi bạn thực sự cần byte theo encoding đã xác định. `String` là kiểu phù hợp cho tên, email, địa chỉ và mã văn bản.

`CHAR` có ngữ nghĩa độ dài cố định và đệm khoảng trắng; `VARCHAR` có độ dài thay đổi. Quy tắc so sánh và trailing spaces còn phụ thuộc collation và kiểu cột. Nếu mã định danh cần so sánh byte-for-byte, hãy chọn charset/collation phù hợp hoặc dùng kiểu nhị phân.

### 5.2. ENUM và SET

Connector/J thường trả giá trị `ENUM` và `SET` như chuỗi. Trong Java, chuyển chuỗi thành enum bằng tên hoặc mã ổn định:

```java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED,
    REFUNDED;

    public String databaseValue() {
        return name().toLowerCase(Locale.ROOT);
    }
}

OrderStatus status = OrderStatus.valueOf(resultSet.getString("status").toUpperCase(Locale.ROOT));
```

Ví dụ này giả định giá trị trong MySQL tương ứng chính xác với tên enum sau chuẩn hóa. Nếu database lưu `in_progress` còn Java enum là `IN_PROGRESS`, hãy viết mapper tường minh thay vì dựa vào `valueOf()`.

```java
static OrderStatus toOrderStatus(String value) {
    return switch (value) {
        case "pending" -> OrderStatus.PENDING;
        case "paid" -> OrderStatus.PAID;
        case "cancelled" -> OrderStatus.CANCELLED;
        case "refunded" -> OrderStatus.REFUNDED;
        default -> throw new IllegalArgumentException("Unknown order status: " + value);
    };
}
```

Không lưu `enum.ordinal()` vào database. Thứ tự phần tử trong mã Java có thể thay đổi, trong khi thứ tự giá trị ENUM của MySQL có quy tắc riêng. Hãy lưu tên hoặc một mã nghiệp vụ ổn định.

Với `SET`, giá trị có thể chứa nhiều lựa chọn được phân tách bằng dấu phẩy. Nếu ứng dụng cần một tập phần tử có kiểu, hãy parse chuỗi thành `Set<Permission>` bằng mapper riêng. Khi các lựa chọn cần quan hệ nhiều-nhiều hoặc thay đổi thường xuyên, bảng liên kết quan hệ thường dễ quản lý hơn `SET`.

### 5.3. BINARY, VARBINARY và BLOB

Dùng `byte[]` cho dữ liệu nhị phân nhỏ hoặc vừa:

```java
byte[] tokenHash = resultSet.getBytes("token_hash");
statement.setBytes(1, tokenHash);
```

Với BLOB lớn, khi đọc hãy dùng `Blob` hoặc `InputStream`; khi ghi, dùng `PreparedStatement.setBinaryStream()` hoặc `Blob.setBinaryStream()` nếu driver và cách triển khai hỗ trợ. Cách này tránh phải giữ toàn bộ nội dung trong heap:

```java
try (InputStream input = resultSet.getBinaryStream("file_content")) {
    // Đọc theo từng khối và chuyển tới nơi lưu trữ phù hợp.
}
```

Đóng stream và tài nguyên JDBC đúng cách. Không log nội dung token, khóa, tài liệu riêng tư hoặc payload nhạy cảm khi debug.

## 6. Ngày giờ: LocalDate, LocalDateTime, Timestamp và Instant

Ánh xạ thời gian là nguồn lỗi phổ biến vì MySQL có cả kiểu không chứa múi giờ và kiểu có chuyển đổi theo múi giờ session.

### 6.1. DATE và LocalDate

`DATE` chỉ biểu diễn ngày lịch, không chứa giờ hoặc múi giờ. Với JDBC 4.2, dùng `LocalDate`:

```java
LocalDate birthDate = resultSet.getObject("birth_date", LocalDate.class);
statement.setObject(1, birthDate);
```

`LocalDate` phù hợp với ngày sinh, ngày hiệu lực và ngày nghiệp vụ. Không chuyển thành `Instant` nếu chưa có quy tắc về múi giờ và thời điểm trong ngày.

### 6.2. DATETIME và LocalDateTime

`DATETIME` lưu giá trị ngày giờ lịch mà MySQL không tự chuyển đổi theo múi giờ session. Dùng `LocalDateTime`:

```java
LocalDateTime appointment = resultSet.getObject("starts_at", LocalDateTime.class);
statement.setObject(1, appointment);
```

`LocalDateTime` không có offset hoặc zone. Nếu `2026-11-19 09:00:00` có nghĩa là 9 giờ sáng tại một địa điểm cụ thể, ứng dụng phải biết múi giờ địa điểm đó khi chuyển sang thời điểm tuyệt đối. Không thể suy ra `Instant` chỉ từ `LocalDateTime`.

### 6.3. TIMESTAMP và Instant

MySQL `TIMESTAMP` chuyển giá trị từ múi giờ session sang UTC khi lưu và chuyển từ UTC sang múi giờ session khi đọc. Java thường dùng `java.sql.Timestamp` ở ranh giới JDBC rồi chuyển sang `Instant` cho domain:

```java
Timestamp timestamp = resultSet.getTimestamp("created_at");
Instant createdAt = timestamp == null ? null : timestamp.toInstant();

if (createdAt == null) {
    statement.setNull(1, Types.TIMESTAMP);
} else {
    statement.setTimestamp(1, Timestamp.from(createdAt));
}
```

Việc giữ đúng instant phụ thuộc cấu hình múi giờ của Connector/J và session MySQL. Hãy cấu hình connection time zone rõ ràng, thường là UTC, và kiểm thử khi JVM, MySQL server và người dùng chạy ở các múi giờ khác nhau. Không dựa vào timezone mặc định của máy phát triển.

Ví dụ URL kết nối minh họa với MySQL Connector/J:

```text
jdbc:mysql://db-host:3306/shop?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true
```

Các thuộc tính `connectionTimeZone` và `forceConnectionTimeZoneToSession` có trong các phiên bản Connector/J hiện đại (bao gồm nhánh 8.0.23 trở lên); quy tắc giữ instant và mặc định có thể khác theo phiên bản. Hãy đối chiếu tài liệu đúng phiên bản, đồng thời xác minh session bằng:

```sql
SELECT @@global.time_zone, @@session.time_zone, NOW(), UTC_TIMESTAMP();
```

`TIMESTAMP` trong MySQL có phạm vi thời gian hẹp hơn `DATETIME`, thường từ năm 1970 đến đầu năm 2038. Nếu nghiệp vụ cần thời gian ngoài phạm vi đó, cân nhắc `DATETIME` cùng quy ước lưu UTC do ứng dụng kiểm soát.

### 6.4. TIME và Duration

MySQL `TIME` có thể biểu diễn giá trị âm và thời lượng lớn hơn 24 giờ, trong khi Java `LocalTime` chỉ biểu diễn giờ trong ngày từ 00:00 đến trước 24:00. Vì vậy:

- Nếu cột là giờ trong ngày, ví dụ giờ mở cửa `09:30:00`, dùng `LocalTime`.
- Nếu cột là thời lượng, ví dụ thời gian xử lý `27:15:00` hoặc `-02:00:00`, không ánh xạ trực tiếp sang `LocalTime`.
- Với thời lượng dài hoặc cần tính toán chính xác, cân nhắc lưu số giây/millisecond/microsecond bằng kiểu số nguyên và ánh xạ sang `Duration`.
- Nếu phải giữ MySQL `TIME` có thể âm hoặc vượt 24 giờ, đọc chuỗi và viết parser/formatter kiểm thử kỹ cho miền giá trị thực tế.

### 6.5. API java.sql cũ và JDBC 4.2

Các lớp `java.sql.Date`, `java.sql.Time` và `java.sql.Timestamp` vẫn được dùng ở API JDBC cũ. Với driver hỗ trợ JDBC 4.2, ưu tiên `LocalDate`, `LocalTime` và `LocalDateTime` qua `getObject()`/`setObject()` cho các kiểu tương ứng. `Timestamp` vẫn hữu ích ở ranh giới với `TIMESTAMP` khi cần chuyển đổi sang `Instant`.

Không dùng `java.util.Date` làm kiểu domain mặc định cho mọi cột thời gian vì nó không thể hiện rõ ngày lịch, giờ địa phương hay instant.

## 7. BIT, BOOLEAN và YEAR

### 7.1. BOOLEAN và TINYINT(1)

Trong MySQL, `BOOL` và `BOOLEAN` là alias của `TINYINT(1)`, không phải kiểu boolean độc lập. Connector/J có thể diễn giải `TINYINT(1)` theo cấu hình driver; một số thuộc tính tương thích có thể khiến nó được nhận diện như `BIT`/boolean.

Nếu cột thực sự chỉ nhận 0 hoặc 1, mô hình Java có thể dùng `boolean` hoặc `Boolean` nếu nullable. Hãy ràng buộc miền giá trị ở database:

```sql
CREATE TABLE feature_flags (
    flag_name VARCHAR(80) NOT NULL,
    enabled TINYINT(1) NOT NULL,
    PRIMARY KEY (flag_name),
    CONSTRAINT chk_feature_enabled CHECK (enabled IN (0, 1))
) ENGINE = InnoDB;
```

Nếu `TINYINT` được dùng để lưu số từ 0 đến 9, đừng ánh xạ sang `Boolean` chỉ vì display width là 1. Kiểm tra cấu hình Connector/J như `tinyInt1isBit` và metadata thực tế của cột.

### 7.2. BIT(M)

`BIT(1)` có thể ánh xạ thuận tiện thành boolean, còn `BIT(M)` nhiều bit có thể được driver trả về dưới dạng byte hoặc mảng byte. Nếu chỉ cần cờ true/false, `TINYINT(1)` kèm `CHECK` thường dễ hiểu và dễ tương tác hơn. Với bit mask hoặc dữ liệu nhị phân, xác định rõ thứ tự bit và quy tắc chuyển đổi ở cả hai phía.

### 7.3. YEAR

MySQL `YEAR` là kiểu đặc thù. Driver có thể báo metadata hoặc chuyển đổi khác nhau theo phiên bản. Nếu domain cần một năm lịch, chẳng hạn `Year` của Java hoặc `int`, hãy kiểm tra metadata và viết mapper tường minh. Có thể yêu cầu MySQL trả dạng số để giảm sự mơ hồ:

```sql
SELECT CAST(birth_year AS UNSIGNED) AS birth_year_number
FROM customer_profiles;
```

Sau đó chuyển giá trị số sang `Year.of(value)` nếu miền hợp lệ. Không tự giả định `YEAR` là một `DATE` đầy đủ hoặc là một số nguyên trong mọi driver.

## 8. JSON và kiểu miền Java

MySQL `JSON` không có kiểu JSON chuẩn trong JDBC. Connector/J thường cung cấp nội dung JSON dưới dạng chuỗi hoặc kiểu vendor tương thích. Cách đơn giản là lấy chuỗi rồi parse bằng thư viện JSON trong ứng dụng:

```java
String json = resultSet.getString("attributes");
ProductAttributes attributes = objectMapper.readValue(json, ProductAttributes.class);
```

Khi ghi:

```java
String json = objectMapper.writeValueAsString(attributes);
preparedStatement.setString(1, json);
```

Database xác thực JSON hợp lệ, nhưng không tự bảo đảm cấu trúc JSON đúng với domain Java. Hãy xác thực schema/field bắt buộc ở ứng dụng hoặc bằng constraint phù hợp. Các thuộc tính thường xuyên lọc hoặc join nên cân nhắc tách thành cột quan hệ hoặc generated column có index.

## 9. NULL và kiểu Java nullable

SQL `NULL` có nghĩa là giá trị vắng mặt/không xác định theo ngữ nghĩa cột. Java primitive không có trạng thái null:

| SQL nullable | Java nên dùng |
| --- | --- |
| `INT NULL` | `Integer` |
| `BIGINT NULL` | `Long` |
| `BOOLEAN`/`TINYINT(1) NULL` | `Boolean` |
| `DECIMAL NULL` | `BigDecimal` có thể null |
| `DATE NULL` | `LocalDate` có thể null |
| `DATETIME NULL` | `LocalDateTime` có thể null |
| `VARCHAR NULL` | `String` có thể null |

Không chuyển SQL NULL thành 0, false hoặc chuỗi rỗng nếu các giá trị đó có nghĩa nghiệp vụ riêng. Nếu cần biểu diễn sự vắng mặt rõ hơn ở domain, repository có thể trả `Optional<T>` cho một giá trị đơn; không nên dùng `Optional` làm field của mọi entity hoặc làm kiểu thay thế trực tiếp cho JDBC.

Ví dụ ghi NULL:

```java
if (middleName == null) {
    statement.setNull(1, Types.VARCHAR);
} else {
    statement.setString(1, middleName);
}
```

Với JDBC 4.2, `setObject(index, null, JDBCType.VARCHAR)` cũng có thể dùng khi driver hỗ trợ đúng kiểu. Truyền loại SQL tường minh giúp tránh trường hợp driver không xác định được kiểu của giá trị null.

## 10. Dùng PreparedStatement để truyền kiểu đúng

`PreparedStatement` tách SQL khỏi giá trị tham số. Ngoài việc ngăn SQL injection, các setter có kiểu giúp driver biết dữ liệu cần gửi theo loại nào.

```java
String sql = """
    INSERT INTO orders
        (customer_id, order_code, total_amount, placed_at, status)
    VALUES (?, ?, ?, ?, ?)
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setString(2, orderCode);
    statement.setBigDecimal(3, totalAmount);
    statement.setObject(4, placedAt); // LocalDateTime cho DATETIME
    statement.setString(5, status.databaseValue());
    statement.executeUpdate();
}
```

Các setter thường dùng:

| Java value | JDBC setter | SQL thường tương ứng |
| --- | --- | --- |
| `byte` / `Byte` | `setByte()` | `TINYINT` |
| `short` / `Short` | `setShort()` | `SMALLINT` |
| `int` / `Integer` | `setInt()` | `INT`, `MEDIUMINT` |
| `long` / `Long` | `setLong()` | `BIGINT` |
| `BigDecimal` | `setBigDecimal()` | `DECIMAL` |
| `float` / `Float` | `setFloat()` | `FLOAT` |
| `double` / `Double` | `setDouble()` | `DOUBLE` |
| `String` | `setString()` | `CHAR`, `VARCHAR`, `TEXT`, `ENUM`, JSON text |
| `byte[]` | `setBytes()` | `BINARY`, `VARBINARY`, BLOB |
| `LocalDate` | `setObject()` | `DATE` |
| `LocalTime` | `setObject()` | `TIME` trong miền giờ trong ngày |
| `LocalDateTime` | `setObject()` | `DATETIME` |
| `Timestamp` | `setTimestamp()` | `TIMESTAMP` |

Không nối chuỗi dữ liệu vào SQL:

```java
// Không an toàn và dễ sai khi có dấu nháy hoặc ký tự đặc biệt
String sql = "SELECT * FROM customers WHERE email = '" + email + "'";

// Dùng tham số
String sql = "SELECT * FROM customers WHERE email = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, email);
}
```

Parameter marker `?` chỉ đại diện cho giá trị, không đại diện cho tên bảng, tên cột hoặc từ khóa SQL. Nếu cần chọn cột sắp xếp động, hãy dùng whitelist tên cột được phép và ghép từ whitelist đã kiểm soát.

## 11. Đọc ResultSet và ánh xạ vào domain

Ví dụ một repository đọc đơn hàng:

```java
public record Order(
    long id,
    long customerId,
    String orderCode,
    BigDecimal totalAmount,
    LocalDateTime placedAt,
    OrderStatus status
) {}

public Optional<Order> findById(Connection connection, long orderId) throws SQLException {
    String sql = """
        SELECT order_id, customer_id, order_code,
               total_amount, placed_at, status
        FROM orders
        WHERE order_id = ?
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, orderId);

        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return Optional.empty();
            }

            Order order = new Order(
                rs.getLong("order_id"),
                rs.getLong("customer_id"),
                rs.getString("order_code"),
                rs.getBigDecimal("total_amount"),
                rs.getObject("placed_at", LocalDateTime.class),
                toOrderStatus(rs.getString("status"))
            );
            return Optional.of(order);
        }
    }
}
```

Ví dụ giả định các cột không nullable và `OrderStatus` có mapper hợp lệ. Nếu cột nullable, dùng wrapper hoặc kiểm tra null trước khi tạo domain object. Với truy vấn trả nhiều hàng, lặp `while (rs.next())` và map từng hàng.

### 11.1. Dùng metadata để kiểm tra ánh xạ

Khi cần chẩn đoán driver, hãy kiểm tra metadata của result set:

```java
ResultSetMetaData metadata = resultSet.getMetaData();
for (int i = 1; i <= metadata.getColumnCount(); i++) {
    System.out.printf(
        "%s | SQL type=%s | JDBC type=%d | Java class=%s%n",
        metadata.getColumnLabel(i),
        metadata.getColumnTypeName(i),
        metadata.getColumnType(i),
        metadata.getColumnClassName(i)
    );
}
```

`getColumnTypeName()` hữu ích để biết tên kiểu MySQL, còn `getColumnType()` và `getColumnClassName()` phản ánh cách driver công bố kiểu JDBC/Java. Đây là cách kiểm tra thực tế khi nâng cấp Connector/J hoặc thay đổi cấu hình như `tinyInt1isBit`.

## 12. Thiết kế mô hình miền tách khỏi JDBC

Không nên để `ResultSet`, `Timestamp`, `Blob` hoặc mã JDBC xuất hiện trong mọi lớp nghiệp vụ. Repository nên chuyển đổi kiểu SQL sang domain type tại một ranh giới rõ ràng.

Ví dụ:

```java
public record CustomerId(long value) {
    public CustomerId {
        if (value <= 0) {
            throw new IllegalArgumentException("CustomerId must be positive");
        }
    }
}

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
    }
}

public record OrderId(long value) {}
```

Database có thể lưu `customer_id` là `BIGINT`, `amount` là `DECIMAL(14,2)` và `currency_code` là `CHAR(3)`. Repository chuyển thành `CustomerId`, `Money` và `Currency`. Domain không cần biết JDBC type code hoặc cách Connector/J xử lý metadata.

Một số nguyên tắc thiết kế:

- ID có kiểu riêng giúp tránh truyền nhầm `customerId` vào tham số `orderId`.
- `Money` nên chứa cả amount và currency; `DECIMAL` đơn lẻ không nói rõ đơn vị tiền.
- Dùng `LocalDate` cho ngày lịch, `Instant` cho thời điểm tuyệt đối và `LocalDateTime` cho ngày giờ lịch không kèm zone.
- Dùng enum/domain mapper theo giá trị ổn định, không theo vị trí ordinal.
- Không để quy tắc chuyển đổi kiểu rải rác trong controller hoặc service; gom vào repository, row mapper hoặc converter.

## 13. Những lỗi ánh xạ thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đọc `DECIMAL` bằng `getDouble()` | Mất độ chính xác thập phân | Dùng `getBigDecimal()` |
| Ghi tiền bằng `setDouble()` | Có thể ghi sai chữ số do floating point | Dùng `setBigDecimal()` |
| Ánh xạ `BIGINT UNSIGNED` vào `long` mà không giới hạn | Tràn hoặc sai giá trị khi vượt `Long.MAX_VALUE` | Dùng `BigInteger`/`BigDecimal` và kiểm tra miền |
| Đọc cột nullable bằng primitive mà không gọi `wasNull()` | Nhầm SQL NULL thành 0/false | Dùng wrapper hoặc kiểm tra `wasNull()` |
| Dùng `LocalDateTime` như `Instant` | Mất thông tin múi giờ, có thể lệch thời điểm | Xác định zone trước khi chuyển hoặc dùng `TIMESTAMP` với UTC rõ ràng |
| Dùng `LocalTime` cho TIME dài hơn 24 giờ | Không biểu diễn được giá trị MySQL hợp lệ | Dùng `Duration`, số nguyên thời lượng hoặc parser riêng |
| Dùng `java.util.Date` cho mọi kiểu thời gian | Không rõ ngày lịch, giờ địa phương hay instant | Dùng `LocalDate`, `LocalDateTime`, `Instant` theo ngữ nghĩa |
| Dùng `enum.ordinal()` để lưu trạng thái | Thay đổi thứ tự enum làm sai dữ liệu | Lưu tên hoặc mã ổn định và map tường minh |
| Giả định JSON có JDBC type chuẩn | Driver có thể trả kiểu vendor/chuỗi | Đọc bằng `getString()` và parse có kiểm tra |
| Giả định TINYINT(1) luôn là Boolean | Cấu hình Connector/J có thể thay đổi metadata/mapping | Kiểm tra driver property và `ResultSetMetaData` |
| Dùng `setString()` cho mọi tham số | Có thể kích hoạt ép kiểu ngầm định và làm giảm tính rõ ràng của kiểu dữ liệu | Dùng setter hoặc `setObject` đúng kiểu |

## 14. Kiểm thử ánh xạ trên MySQL thật

Không chỉ kiểm thử repository bằng mock. Các khác biệt về `UNSIGNED`, `TIMESTAMP`, collation, JSON và kiểu vendor cần được kiểm tra với đúng MySQL và Connector/J mà ứng dụng triển khai.

Một bộ integration test nên có:

1. **Giá trị biên số nguyên:** min/max cho từng kiểu signed và unsigned; đặc biệt `INT UNSIGNED` và `BIGINT UNSIGNED`.
2. **Độ chính xác:** ghi/đọc `DECIMAL` có nhiều chữ số, scale tối đa được dùng và các trường hợp làm tròn.
3. **NULL:** phân biệt NULL, 0, false và chuỗi rỗng.
4. **Unicode:** lưu và đọc tiếng Việt có dấu, ký tự emoji và chuỗi ở giới hạn độ dài.
5. **Thời gian:** thử `DATE`, `DATETIME`, `TIMESTAMP`, phần microsecond và session timezone khác nhau.
6. **TIME:** thử giờ trong ngày, giá trị âm và thời lượng vượt 24 giờ nếu schema cho phép.
7. **Kiểu đặc thù:** `BIT`, `YEAR`, `ENUM`, `SET` và JSON với đúng phiên bản Connector/J.
8. **Metadata:** xác minh `getColumnTypeName()`, `getColumnType()` và `getColumnClassName()` khi nâng cấp driver.
9. **Migration:** xác minh dữ liệu cũ không bị làm tròn, cắt chuỗi hoặc đổi timezone khi thay đổi schema.

Ví dụ kiểm tra round-trip cho `DECIMAL`:

```java
BigDecimal original = new BigDecimal("1234567890.12");
// Ghi original bằng PreparedStatement.setBigDecimal(...)
// Đọc lại bằng ResultSet.getBigDecimal(...)
assertEquals(0, original.compareTo(readBack));
```

So sánh `BigDecimal` bằng `compareTo()` khi mục tiêu là so sánh giá trị số. `equals()` còn xét scale, nên `1.0` và `1.00` không bằng nhau theo `equals()` dù cùng giá trị số.

Ví dụ kiểm thử instant nên chạy với session UTC và một session có múi giờ khác, sau đó xác nhận cùng một instant được lưu/đọc đúng theo cấu hình đã chọn. Đừng chỉ chạy test trên máy developer có timezone mặc định giống database server.

## 15. Checklist trước khi đưa mapping vào production

- [ ] Phiên bản MySQL và MySQL Connector/J đã được xác định và quản lý đồng bộ.
- [ ] Mỗi cột có kiểu Java phù hợp với miền giá trị và signedness.
- [ ] `DECIMAL` được ánh xạ bằng `BigDecimal`, có quy tắc scale và rounding rõ ràng.
- [ ] `BIGINT UNSIGNED` có chiến lược nếu giá trị vượt `Long.MAX_VALUE`.
- [ ] Cột nullable dùng kiểu Java có thể biểu diễn null.
- [ ] `DATE`, `DATETIME`, `TIMESTAMP` được ánh xạ theo đúng ý nghĩa thời gian.
- [ ] Múi giờ session MySQL và thuộc tính timezone của Connector/J được cấu hình rõ ràng.
- [ ] `TIME` có miền lớn hơn 24 giờ được xử lý như duration, không ép vào `LocalTime`.
- [ ] ENUM/SET được chuyển bằng mã ổn định, không dùng ordinal.
- [ ] JSON được parse và validate theo domain schema.
- [ ] `PreparedStatement` dùng setter đúng kiểu và không nối dữ liệu vào SQL.
- [ ] Integration test chạy trên đúng MySQL/Connector/J, bao gồm giá trị biên và round-trip.

## 16. Bài tập thực hành

1. Tạo bảng `orders` với `BIGINT UNSIGNED`, `DECIMAL(14,2)`, `DATETIME`, `TIMESTAMP` và `ENUM`. Viết một Java record biểu diễn đơn hàng.
2. Viết repository dùng `PreparedStatement` để insert và select đơn hàng. Dùng `setBigDecimal`, `setObject(LocalDateTime)` và mapper enum tường minh.
3. Thử ghi `BIGINT UNSIGNED` lớn hơn `Long.MAX_VALUE`. Đọc bằng `BigDecimal`, chuyển sang `BigInteger` và giải thích vì sao `long` không đủ.
4. Tạo cột nullable và đọc bằng `getInt()` kết hợp `wasNull()`. Viết lại bằng `getObject(Integer.class)` rồi so sánh.
5. Ghi và đọc giá tiền `1234567890.12` bằng `BigDecimal`. Thử `new BigDecimal(0.1)` và `new BigDecimal("0.1")` để quan sát khác biệt.
6. Lưu ngày sinh bằng `DATE`, lịch hẹn bằng `DATETIME` và thời điểm thanh toán bằng `TIMESTAMP`. Chạy test với timezone UTC và timezone khác.
7. Tạo cột `TIME` có giá trị `27:15:00`. Chứng minh `LocalTime` không thể biểu diễn trực tiếp giá trị này và đề xuất mapping `Duration`.
8. Tạo cột JSON và parse thành một Java record. Kiểm tra hành vi khi JSON thiếu field hoặc có field không hợp lệ.
9. In metadata của các cột `TINYINT(1)`, `BIT(1)`, `YEAR`, `JSON`, `ENUM` và `SET` bằng `ResultSetMetaData`.

## 17. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể giải thích đường đi từ kiểu MySQL qua JDBC tới kiểu Java, chọn được kiểu Java phù hợp cho số nguyên, số thập phân, chuỗi và thời gian, xử lý được `UNSIGNED` và `NULL`, cấu hình timezone nhất quán cho `TIMESTAMP`, ánh xạ kiểu đặc thù bằng mapper rõ ràng và viết được repository dùng `PreparedStatement`/`ResultSet`. Bạn cũng cần chứng minh mapping bằng integration test với đúng phiên bản MySQL và Connector/J, bao gồm giá trị biên và các trường hợp có nguy cơ mất dữ liệu.
