# Ánh xạ DECIMAL, UNSIGNED BIGINT, BIT và BOOLEAN sang Java

Khi ứng dụng Java đọc hoặc ghi dữ liệu MySQL qua Connector/J, kiểu SQL và kiểu Java phải được chọn sao cho giữ nguyên giá trị. Một số kiểu có vẻ tương tự nhưng có miền biểu diễn rất khác nhau: `DECIMAL` cần độ chính xác thập phân, `BIGINT UNSIGNED` có thể vượt giới hạn `long`, `BIT(M)` có thể là một vector bit nhiều byte, còn `BOOLEAN` trong MySQL thực chất là bí danh của `TINYINT(1)`.

Nếu chọn sai getter hoặc setter, driver có thể làm tròn, tràn số, đổi metadata hoặc biến một giá trị SQL `NULL` thành giá trị mặc định của kiểu primitive. Bài này tập trung vào cách ánh xạ bốn nhóm kiểu dữ liệu trên, cách kiểm tra metadata mà Connector/J công bố và cách viết JDBC code để giữ dữ liệu chính xác.

## 1. Bảng ánh xạ cần nhớ

Với Connector/J hiện đại, các kiểu thường gặp được ánh xạ như sau khi dùng `ResultSet.getObject()`:

| MySQL | Kiểu Java thường nhận được | JDBC type metadata | Cách đọc nên dùng |
|---|---|---|---|
| `DECIMAL(p,s)` | `java.math.BigDecimal` | `DECIMAL` | `getBigDecimal()` |
| `DECIMAL(p,s) UNSIGNED` | `java.math.BigDecimal` | `DECIMAL` | `getBigDecimal()` |
| `BIGINT` | `java.lang.Long` | `BIGINT` | `getLong()` hoặc `getObject()` |
| `BIGINT UNSIGNED` | `java.math.BigInteger` | `BIGINT UNSIGNED` | `getObject()` hoặc `getBigDecimal()` rồi chuyển chính xác sang `BigInteger` |
| `BIT(1)` | `java.lang.Boolean` | `BIT` | `getBoolean()` hoặc `getObject()` |
| `BIT(M)` với M lớn hơn 1 | `byte[]` | `BIT` | `getBytes()` |
| `BOOLEAN`, `BOOL`, `TINYINT(1)` có `tinyInt1isBit=true` | `java.lang.Boolean` | `BIT` hoặc `BOOLEAN` tùy cấu hình metadata | `getBoolean()` hoặc `getObject()` |
| `TINYINT(1)` có `tinyInt1isBit=false` | `java.lang.Integer` | `TINYINT` | `getInt()` hoặc `getObject()` |

Đây là kiểu lớp Java mà Connector/J báo qua metadata trong trường hợp được liệt kê. JDBC vẫn cho phép nhiều phép chuyển đổi khác, nhưng chuyển đổi sang kiểu có miền nhỏ hơn có thể gây làm tròn, tràn số hoặc mất độ chính xác. Không nên chọn getter chỉ vì nó biên dịch được.

## 2. DECIMAL: dùng BigDecimal để giữ độ chính xác

MySQL `DECIMAL(p,s)` là kiểu số thập phân chính xác. `p` là tổng số chữ số và `s` là số chữ số sau dấu thập phân. MySQL hỗ trợ precision tối đa 65 chữ số và scale tối đa 30 chữ số. Ví dụ `DECIMAL(19,4)` có tối đa 19 chữ số, trong đó 4 chữ số ở phần thập phân.

Trong Java, kiểu phù hợp là `java.math.BigDecimal`:

```java
BigDecimal amount = new BigDecimal("12345.6700");

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO invoices (amount) VALUES (?)")) {
    ps.setBigDecimal(1, amount);
    ps.executeUpdate();
}

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT amount FROM invoices WHERE invoice_id = ?")) {
    ps.setLong(1, invoiceId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal storedAmount = rs.getBigDecimal("amount");
        }
    }
}
```

`BigDecimal` giữ giá trị thập phân mà không chuyển qua biểu diễn nhị phân gần đúng của `double`. Tránh các cách sau khi làm việc với tiền hoặc số thập phân cần chính xác:

```java
// Không nên: 0.1 không biểu diễn chính xác bằng double nhị phân.
BigDecimal wrong = new BigDecimal(0.1);

// Nên: tạo từ chuỗi thập phân hoặc từ dữ liệu nguyên chính xác.
BigDecimal right = new BigDecimal("0.1");
```

### Precision và scale phải theo hợp đồng dữ liệu

Nếu cột là `DECIMAL(12,2)`, ứng dụng nên kiểm tra cả số chữ số và số chữ số thập phân trước khi ghi. `setScale()` cho phép áp dụng chính sách làm tròn một cách tường minh:

```java
BigDecimal normalized = input.setScale(2, RoundingMode.UNNECESSARY);
```

`RoundingMode.UNNECESSARY` sẽ ném `ArithmeticException` nếu cần làm tròn. Nếu nghiệp vụ cho phép làm tròn, hãy chọn mode đã được quy định, chẳng hạn `HALF_UP` hoặc `HALF_EVEN`, thay vì dựa vào chuyển đổi ngầm của driver/server.

Không nhầm `BigDecimal.equals()` với so sánh giá trị số:

```java
new BigDecimal("1.0").equals(new BigDecimal("1.00"));
// false: scale khác nhau

new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0;
// true: giá trị số bằng nhau
```

Nếu cần kiểm tra hai số có cùng giá trị, dùng `compareTo()`. Nếu scale mang ý nghĩa nghiệp vụ hoặc định dạng hiển thị, giữ scale theo quy ước của domain.

Khi đọc `DECIMAL`, `getBigDecimal()` trả về `null` nếu SQL value là `NULL`. Khi ghi null, dùng `setNull(index, Types.DECIMAL)` hoặc `setObject(index, null, Types.DECIMAL)` để giữ kiểu tham số rõ ràng.

## 3. BIGINT UNSIGNED: miền số vượt quá long

`BIGINT` có dấu có miền từ `-9223372036854775808` đến `9223372036854775807`, vừa với Java `long`. Nhưng `BIGINT UNSIGNED` có miền từ `0` đến `18446744073709551615`, lớn hơn giá trị tối đa của `long`.

Vì vậy, không dùng `long` làm kiểu miền dữ liệu cho toàn bộ `BIGINT UNSIGNED`. Connector/J ánh xạ `BIGINT UNSIGNED` sang `java.math.BigInteger` khi lấy qua `getObject()`:

```java
Object raw = rs.getObject("external_id");
BigInteger externalId = (BigInteger) raw;
```

Nếu cần cách đọc rõ ràng và ít phụ thuộc vào lớp cụ thể driver, JDBC cũng cho phép đọc số này dưới dạng `BigDecimal`, sau đó chuyển chính xác sang `BigInteger`:

```java
BigDecimal rawId = rs.getBigDecimal("external_id");
BigInteger externalId = rawId.toBigIntegerExact();
```

`toBigIntegerExact()` từ chối phần thập phân khác 0, nhờ đó không âm thầm cắt phần lẻ. Kiểm tra `null` trước khi gọi phương thức chuyển đổi.

### Ghi BIGINT UNSIGNED

Kiểm tra miền trước khi gửi tham số. Ví dụ dùng `BigDecimal` để truyền một giá trị nguyên chính xác:

```java
private static final BigInteger MAX_UNSIGNED_BIGINT =
        new BigInteger("18446744073709551615");

static void bindUnsignedBigInt(
        PreparedStatement ps,
        int parameterIndex,
        BigInteger value) throws SQLException {

    if (value == null) {
        ps.setNull(parameterIndex, Types.BIGINT);
        return;
    }

    if (value.signum() < 0 || value.compareTo(MAX_UNSIGNED_BIGINT) > 0) {
        throw new IllegalArgumentException("Value is outside BIGINT UNSIGNED range");
    }

    ps.setBigDecimal(parameterIndex, new BigDecimal(value));
}
```

Đây là cách truyền tham số số nguyên chính xác, không ép qua `long` hoặc `double`. Hãy kiểm thử giá trị sát hai biên với phiên bản Connector/J đang dùng. Nếu hệ thống chỉ sử dụng các giá trị không vượt `Long.MAX_VALUE`, `long` vẫn có thể là kiểu domain thuận tiện; điều đó phải được bảo đảm bằng constraint và quy tắc nghiệp vụ.

Tránh các cách chuyển đổi có thể làm mất dữ liệu:

```java
long id = bigInteger.longValue();       // có thể tràn hoặc giữ sai giá trị
double idAsDouble = bigInteger.doubleValue(); // mất chính xác ở số lớn
```

Nếu cần dùng `long`, gọi `longValueExact()` để thất bại rõ ràng khi giá trị nằm ngoài miền `long`:

```java
long id = externalId.longValueExact();
```

## 4. BIT(M): boolean đơn lẻ hay vector bit?

MySQL `BIT(M)` lưu một giá trị gồm M bit; M nằm trong khoảng 1 đến 64 và mặc định là 1 nếu không chỉ định. Cách ánh xạ sang Java phụ thuộc độ rộng:

- `BIT(1)` được Connector/J ánh xạ thành `Boolean`.
- `BIT(M)` với M lớn hơn 1 được ánh xạ thành `byte[]`.

Ví dụ, `BIT(8)` có thể dùng làm tập cờ nhỏ, mỗi bit đại diện cho một quyền hoặc tính năng:

```sql
CREATE TABLE account_settings (
    account_id BIGINT NOT NULL PRIMARY KEY,
    feature_flags BIT(8) NOT NULL
);

INSERT INTO account_settings (account_id, feature_flags)
VALUES (1, b'00000101');
```

Đọc bằng JDBC:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT feature_flags FROM account_settings WHERE account_id = ?")) {
    ps.setLong(1, 1L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            byte[] flags = rs.getBytes("feature_flags");
            int firstByte = flags[0] & 0xFF;

            boolean canExport = (firstByte & 0b00000100) != 0;
            boolean canImport = (firstByte & 0b00000001) != 0;
        }
    }
}
```

Phép `& 0xFF` chuyển byte có dấu của Java thành giá trị nguyên không dấu từ 0 đến 255 để thao tác bit dễ hiểu. Với `BIT(M)` lớn hơn 8, giá trị có thể chiếm nhiều byte; cần thống nhất độ rộng, thứ tự bit và quy ước ánh xạ từng bit giữa database và ứng dụng. Không giả định `flags[0]` luôn đại diện cho cùng một quyền nếu các service khác dùng quy ước byte khác.

Khi ghi một giá trị `BIT(8)` qua prepared statement, có thể bind byte array:

```java
byte[] flags = new byte[] { (byte) 0b00000101 };

try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE account_settings SET feature_flags = ? WHERE account_id = ?")) {
    ps.setBytes(1, flags);
    ps.setLong(2, 1L);
    ps.executeUpdate();
}
```

Đảm bảo byte array có đúng độ rộng và biểu diễn mà schema/domain quy định. Với mask nhiều byte, viết unit test round-trip cho các mẫu như bit thấp nhất, bit cao nhất và tất cả bit được bật. `getBoolean()` trên một `BIT(M)` nhiều bit chỉ cho biết giá trị có khác 0 hay không; nó làm mất thông tin các bit riêng lẻ, vì vậy hãy dùng `getBytes()` cho bitmask.

## 5. BOOLEAN trong MySQL là TINYINT(1)

Trong MySQL, `BOOL` và `BOOLEAN` là bí danh của `TINYINT(1)`. `TRUE` và `FALSE` lần lượt là bí danh của `1` và `0`. Giá trị `0` được coi là false; mọi giá trị khác 0 được coi là true trong biểu thức logic.

Điều này có nghĩa cột `BOOLEAN` không tự giới hạn dữ liệu chỉ còn hai giá trị 0 và 1. Nếu nghiệp vụ yêu cầu đúng hai trạng thái, có thể thêm check constraint; MySQL thực thi `CHECK` constraint từ phiên bản 8.0.16 trở lên. Với phiên bản cũ hơn, cần xác thực ở tầng ứng dụng hoặc dùng giải pháp tương thích:

```sql
CREATE TABLE feature_switches (
    feature_name VARCHAR(100) NOT NULL PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT chk_feature_switches_enabled CHECK (enabled IN (0, 1))
);
```

### Ảnh hưởng của tinyInt1isBit

Connector/J có thuộc tính `tinyInt1isBit`, mặc định là `true`. Khi bật, driver xem `TINYINT(1)` signed/`BOOLEAN` như kiểu `BIT` trong metadata và `getObject()` trả `Boolean`. Khi tắt, metadata là `TINYINT` và lớp Java được báo là `Integer`.

Ví dụ cấu hình trong JDBC URL:

```text
jdbc:mysql://localhost:3306/appdb?tinyInt1isBit=false
```

Thuộc tính `transformedBitIsBoolean` mặc định là `false`. Khi `tinyInt1isBit=true`, thuộc tính này điều khiển tên JDBC type metadata được báo là `BIT` hay `BOOLEAN`; lớp Java vẫn là `Boolean`. Hai thuộc tính này có thể được cấu hình qua JDBC URL, `Properties` hoặc `DataSource`.

| `tinyInt1isBit` | `transformedBitIsBoolean` | Metadata type | Java class từ `getObject()` |
|---|---|---|---|
| `true` | `false` | `BIT` | `Boolean` |
| `true` | `true` | `BOOLEAN` | `Boolean` |
| `false` | không áp dụng cho phép biến đổi này | `TINYINT` | `Integer` |

Thuộc tính này ảnh hưởng cả những cột `TINYINT(1)` được dùng như số đếm hoặc mã trạng thái. Nếu một cột lưu giá trị 0 đến 9 nhưng có định nghĩa `TINYINT(1)`, bật `tinyInt1isBit` có thể khiến metadata và `getObject()` thay đổi theo hướng Boolean. Không dùng độ rộng hiển thị `1` như cách biểu đạt một cột số nguyên tổng quát; hãy chọn kiểu SQL có miền dữ liệu phù hợp. `TINYINT(1) UNSIGNED` được xử lý như `TINYINT UNSIGNED` và có Java class `Integer`, không theo nhánh biến đổi `TINYINT(1)` signed/`BOOLEAN` ở bảng trên.

### Đọc boolean và SQL NULL

`ResultSet.getBoolean()` trả `false` khi SQL value là `0`, và trả `true` khi khác 0. Nếu SQL value là `NULL`, getter primitive trả giá trị mặc định `false`; phải gọi `wasNull()` ngay sau getter để phân biệt:

```java
boolean enabled = rs.getBoolean("enabled");
boolean wasSqlNull = rs.wasNull();

Boolean nullableEnabled = wasSqlNull ? null : enabled;
```

Nếu cột là `NOT NULL`, không cần nhánh null trong dữ liệu hợp lệ, nhưng vẫn nên giữ constraint ở database. Với cột nullable, không bỏ qua `wasNull()` vì `NULL` và `FALSE` có ý nghĩa khác nhau.

Khi ghi:

```java
ps.setBoolean(1, enabled);
ps.setNull(2, Types.BOOLEAN); // khi cột nullable và giá trị domain là null
```

`setBoolean()` gửi giá trị logic theo dạng mà Connector/J ánh xạ cho MySQL. Nếu muốn lưu một mã số nhiều trạng thái, hãy dùng `TINYINT`/`SMALLINT` và `getInt()`/`setInt()` thay vì cột `BOOLEAN`.

## 6. Ví dụ JDBC đầy đủ cho bốn kiểu

Tạo bảng thử nghiệm:

```sql
CREATE TABLE jdbc_type_mapping_demo (
    id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(19, 4) NOT NULL,
    flags BIT(8) NOT NULL,
    enabled BOOLEAN NULL,
    PRIMARY KEY (id),
    CONSTRAINT chk_demo_enabled CHECK (enabled IS NULL OR enabled IN (0, 1))
) ENGINE = InnoDB;
```

Ghi dữ liệu bằng `PreparedStatement`:

```java
BigInteger id = new BigInteger("18446744073709551615");
BigDecimal amount = new BigDecimal("123456789012345.6700");
byte[] flags = new byte[] { (byte) 0b00000101 };
Boolean enabled = Boolean.TRUE;

String insertSql = """
    INSERT INTO jdbc_type_mapping_demo (id, amount, flags, enabled)
    VALUES (?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(insertSql)) {
    ps.setBigDecimal(1, new BigDecimal(id));
    ps.setBigDecimal(2, amount);
    ps.setBytes(3, flags);

    if (enabled == null) {
        ps.setNull(4, Types.BOOLEAN);
    } else {
        ps.setBoolean(4, enabled);
    }

    ps.executeUpdate();
}
```

Đọc lại mà không làm mất miền giá trị:

```java
String selectSql = """
    SELECT id, amount, flags, enabled
    FROM jdbc_type_mapping_demo
    WHERE id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(selectSql)) {
    ps.setBigDecimal(1, new BigDecimal(id));

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigInteger readId = rs.getBigDecimal("id").toBigIntegerExact();
            BigDecimal readAmount = rs.getBigDecimal("amount");
            byte[] readFlags = rs.getBytes("flags");

            boolean enabledValue = rs.getBoolean("enabled");
            Boolean readEnabled = rs.wasNull() ? null : enabledValue;
        }
    }
}
```

Ví dụ dùng Java text block, cần Java 15 trở lên. Với Java thấp hơn, thay text block bằng chuỗi nối hoặc string literal thông thường. Dữ liệu mẫu sử dụng giá trị lớn nhất của `BIGINT UNSIGNED` để kiểm tra đường đi không qua `long`.

## 7. Kiểm tra metadata mà Connector/J công bố

Khi một cột có kiểu ánh xạ phụ thuộc cấu hình, đừng đoán từ tên cột hoặc annotation của ORM. Dùng `ResultSetMetaData` để xem driver đang báo JDBC type và lớp Java nào:

```java
try (Statement st = connection.createStatement();
     ResultSet rs = st.executeQuery(
         "SELECT id, amount, flags, enabled FROM jdbc_type_mapping_demo LIMIT 1")) {

    ResultSetMetaData md = rs.getMetaData();

    for (int i = 1; i <= md.getColumnCount(); i++) {
        System.out.printf(
            "%s | mysql=%s | jdbcType=%d | class=%s%n",
            md.getColumnLabel(i),
            md.getColumnTypeName(i),
            md.getColumnType(i),
            md.getColumnClassName(i)
        );
    }
}
```

Với Connector/J, kết quả kỳ vọng cho ví dụ là:

| Cột | `getColumnTypeName()` | `getColumnClassName()` thường gặp |
|---|---|---|
| `id` | `BIGINT UNSIGNED` | `java.math.BigInteger` |
| `amount` | `DECIMAL` | `java.math.BigDecimal` |
| `flags` | `BIT` | `byte[]` |
| `enabled` | `BIT` hoặc `BOOLEAN` theo thuộc tính | `java.lang.Boolean` khi `tinyInt1isBit=true` |

Metadata có thể thay đổi khi đổi Connector/J version hoặc thuộc tính connection. Hãy chạy kiểm tra trên đúng URL và driver được dùng trong production. Khi dùng ORM, kiểm tra cả kiểu Java mà ORM suy ra từ JDBC metadata và kiểu domain thực tế.

## 8. Những lỗi thường gặp và cách phòng tránh

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Số tiền đọc ra có phần lẻ sai | Dùng `getDouble()` hoặc tạo `BigDecimal` từ `double` | Dùng `getBigDecimal()` và tạo giá trị từ chuỗi hoặc số nguyên chính xác. |
| `BIGINT UNSIGNED` bị âm hoặc sai số | Ép giá trị lớn qua `long`/`double` | Dùng `BigInteger`, `BigDecimal` và kiểm tra miền trước khi ghi. |
| `getObject()` trả `Integer` thay vì `Boolean` | `tinyInt1isBit=false` hoặc cột không được nhận diện là `TINYINT(1)` signed | Kiểm tra JDBC URL và `ResultSetMetaData`; thống nhất cấu hình trên mọi pool. |
| `getObject()` trả `Boolean` cho cột cần số | `tinyInt1isBit=true` làm `TINYINT(1)` được biến đổi thành BIT | Dùng kiểu SQL có miền đúng, hoặc cấu hình `tinyInt1isBit=false` nếu ứng dụng cần số nguyên. |
| Bitmask chỉ còn true/false | Dùng `getBoolean()` cho `BIT(M)` với M lớn hơn 1 | Dùng `getBytes()` và giải mã từng bit theo quy ước domain. |
| `NULL` bị hiểu là false hoặc 0 | Dùng getter primitive mà không gọi `wasNull()` | Gọi `wasNull()` ngay sau getter hoặc dùng wrapper/`getObject()` phù hợp. |
| Giá trị thập phân bị làm tròn khi ghi | Không quy định scale/rounding trước khi bind | Kiểm tra precision/scale và chọn `RoundingMode` theo nghiệp vụ. |
| Chỉ một service ánh xạ boolean khác service khác | Các connection pool dùng URL/property không đồng nhất | Chuẩn hóa cấu hình Connector/J và kiểm tra metadata khi khởi động. |
| Tràn số không bị phát hiện sớm | Tắt kiểm tra truncation hoặc ép kiểu quá rộng | Giữ hành vi truncation phù hợp JDBC và kiểm thử biên kiểu dữ liệu. |

Connector/J có thể phát warning hoặc ném `DataTruncation` theo yêu cầu JDBC khi chuyển đổi không biểu diễn được; hành vi có thể bị thay đổi nếu cấu hình `jdbcCompliantTruncation=false`. Không tắt thuộc tính này chỉ để bỏ qua lỗi dữ liệu. Hãy xử lý kiểu Java, miền dữ liệu và schema cho khớp nhau.

## 9. Checklist thiết kế mapping

- [ ] `DECIMAL` được ánh xạ sang `BigDecimal`, không đi qua `float`/`double`.
- [ ] Precision và scale được kiểm tra trước khi ghi; rounding policy được xác định rõ.
- [ ] `BIGINT UNSIGNED` có thể vượt `Long.MAX_VALUE`, nên domain dùng `BigInteger` nếu cần toàn miền.
- [ ] Không gọi `longValue()` cho giá trị unsigned chưa được xác minh; dùng `longValueExact()` nếu cần thu hẹp miền.
- [ ] `BIT(1)` và `BIT(M>1)` được xử lý khác nhau: Boolean so với byte array.
- [ ] Bitmask có quy ước độ rộng, thứ tự bit và ý nghĩa từng bit thống nhất giữa các service.
- [ ] `BOOLEAN` được hiểu là `TINYINT(1)`; thêm check constraint nếu chỉ cho phép 0/1.
- [ ] `tinyInt1isBit` và `transformedBitIsBoolean` được thống nhất trong cấu hình Connector/J.
- [ ] Getter primitive được theo sau bởi `wasNull()` khi cột có thể null.
- [ ] `ResultSetMetaData` đã được kiểm tra với đúng phiên bản driver và cấu hình production.
- [ ] Có kiểm thử round-trip cho giá trị nhỏ nhất, lớn nhất, null và các trường hợp biên.

Ánh xạ đúng bắt đầu từ miền dữ liệu thực tế. `DECIMAL` cần `BigDecimal` để giữ số thập phân chính xác; `BIGINT UNSIGNED` cần `BigInteger` khi dùng toàn bộ miền unsigned; `BIT(1)` có thể biểu diễn bằng `Boolean` trong khi `BIT(M)` rộng hơn cần `byte[]`; `BOOLEAN` phải được hiểu cùng quy tắc `TINYINT(1)` và thuộc tính `tinyInt1isBit`. Kiểm tra metadata và thử round-trip với dữ liệu biên giúp phát hiện sai lệch trước khi chúng đi vào nghiệp vụ.
