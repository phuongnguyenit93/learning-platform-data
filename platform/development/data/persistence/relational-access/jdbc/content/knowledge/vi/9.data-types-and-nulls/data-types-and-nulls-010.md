# Kiểm tra mất thông tin khi chuyển kiểu dữ liệu trong JDBC

## 1. Vì sao chuyển kiểu có thể làm dữ liệu sai mà không báo lỗi?

**JDBC (Java Database Connectivity)** là API giúp ứng dụng Java truy cập cơ sở dữ liệu quan hệ. Khi ứng dụng gọi `PreparedStatement.setXxx(...)` hoặc `ResultSet.getXxx(...)`, dữ liệu phải đi qua ranh giới giữa **kiểu dữ liệu Java**, **kiểu SQL**, **JDBC driver** và đôi khi cả **biểu thức chuyển kiểu trên database**.

Một phép chuyển kiểu có thể hoàn tất mà không ném `SQLException`, nhưng giá trị sau chuyển đổi **không còn mang đủ thông tin như ban đầu**. Ví dụ:

- `DECIMAL(12,2)` chỉ giữ hai chữ số thập phân; giá trị `12.345` có thể bị từ chối hoặc làm tròn theo quy tắc của DBMS.
- Số nguyên `3_000_000_000L` không nằm trong khoảng của `int` Java; thu hẹp bằng ép kiểu có thể cho số hoàn toàn khác.
- Số tiền `0.1` biểu diễn bằng `double` không lưu chính xác phân số thập phân `1/10`.
- Giá trị SQL `NULL` được đọc bằng `getInt()` có thể cho số `0`, nếu không kiểm tra `wasNull()` sẽ lẫn với số không thực.
- Một chuỗi Unicode có thể vượt giới hạn cột dù số ký tự nhìn thấy ít hơn giới hạn byte của DBMS.
- Một thời điểm có múi giờ có thể đổi ý nghĩa khi được đọc vào `LocalDateTime` hoặc được chuyển qua các múi giờ khác nhau.

Bài học trong chương **Kiểu dữ liệu và NULL** tập trung vào việc **phát hiện sớm, kiểm tra có chủ đích và ngăn mất thông tin** khi dữ liệu đi từ Java vào database hoặc từ database về Java.

### 1.1. Sơ đồ đường đi của dữ liệu

~~~mermaid
flowchart LR
    A[Giá trị Java] --> B[PreparedStatement.setXxx / setObject]
    B --> C[JDBC Driver]
    C --> D[Kiểu cột / CAST / ràng buộc SQL]
    D --> E[(Dữ liệu đã lưu)]
    E --> F[SQL SELECT / biểu thức]
    F --> G[ResultSet.getXxx / getObject]
    G --> H[Kiểu Java nhận]
    H --> I[Đối chiếu với hợp đồng dữ liệu]
~~~

Có **hai chiều cần kiểm tra độc lập**:

1. **Java → SQL:** dữ liệu đưa vào có vừa kiểu SQL mục tiêu và có giữ đúng ý nghĩa không?
2. **SQL → Java:** kiểu đọc ở Java có đủ miền giá trị, độ chính xác và thông tin ngữ nghĩa của dữ liệu SQL không?

Một phép thử chỉ “insert thành công” chưa đủ; cần xem dữ liệu **được lưu và đọc lại** có đúng hợp đồng nghiệp vụ hay không.

## 2. Những dạng mất thông tin thường gặp

| Nhóm | Dạng mất thông tin | Ví dụ | Cách nhận biết |
| --- | --- | --- | --- |
| Số nguyên | Tràn miền giá trị khi thu hẹp kiểu | `long → int` | Kiểm tra giới hạn hoặc dùng `Math.toIntExact(...)`. |
| Số thập phân | Làm tròn hoặc cắt phần lẻ | `12.345 → DECIMAL(...,2)` | Dùng `BigDecimal.setScale(..., UNNECESSARY)` trước khi bind. |
| Số thực dấu phẩy động | Sai số biểu diễn nhị phân | `0.1 double` | So sánh bằng decimal đúng nghĩa, không dùng `double` cho tiền. |
| Kiểu chuỗi | Cắt chuỗi, thay ký tự, đệm dấu cách | `VARCHAR(n)` / `CHAR(n)` | Kiểm tra giới hạn DBMS, encoding và round-trip. |
| Ngày giờ | Mất offset, vùng giờ hoặc phần lẻ giây | `TIMESTAMP → LocalDateTime` | Chọn kiểu thời gian đúng ngữ nghĩa và kiểm tra precision/time zone. |
| `NULL` | Biến NULL thành giá trị mặc định của primitive | `getInt(NULL) → 0` | Gọi `wasNull()` ngay sau getter hoặc dùng kiểu reference. |
| BOOLEAN/ENUM | Ép nhiều trạng thái thành ít trạng thái | Chuỗi trạng thái → boolean | Định nghĩa mapping và xử lý giá trị ngoài miền. |
| Dữ liệu nhị phân/LOB | Cắt bytes hoặc đọc chưa hết stream | BLOB → `byte[]` không đầy đủ | Kiểm tra độ dài, checksum, vòng đời stream. |

**Cần phân biệt “đúng kiểu” với “đúng giá trị”:** Truy vấn có thể trả một `String` hợp lệ hoặc một `long` hợp lệ về mặt Java nhưng vẫn sai về mặt nghiệp vụ vì đã bị biến đổi trước đó.

## 3. Bắt đầu từ hợp đồng kiểu SQL và metadata

Trước khi chọn getter hoặc setter, hãy biết **kiểu cột thực tế**. `ResultSetMetaData` giúp xem kiểu SQL mà driver công bố cho một kết quả truy vấn:

~~~java
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;

public static void printColumnMetadata(ResultSet rs)
        throws SQLException {
    ResultSetMetaData md = rs.getMetaData();

    for (int i = 1; i <= md.getColumnCount(); i++) {
        System.out.printf(
                "column=%s, sqlType=%s, precision=%d, scale=%d, nullable=%d%n",
                md.getColumnLabel(i),
                md.getColumnTypeName(i),
                md.getPrecision(i),
                md.getScale(i),
                md.isNullable(i));
    }
}
~~~

Trong JDBC, **chỉ số cột bắt đầu từ 1**. Các giá trị `precision` và `scale` có ý nghĩa quan trọng với kiểu số; với chuỗi, cách diễn giải chiều dài có thể khác. Không xem mọi giá trị `0` trả về bởi metadata là chứng cứ rằng cột thật sự không chứa chữ số hay không có độ dài: driver có thể không công bố được giới hạn cho một biểu thức.

Một số API metadata liên quan:

| API | Cho biết điều gì? | Giới hạn cần nhớ |
| --- | --- | --- |
| `ResultSetMetaData.getColumnType(i)` | Mã kiểu theo `java.sql.Types` cho kết quả SELECT. | Kiểu có thể là kiểu **sau biểu thức CAST**, không phải kiểu cột gốc. |
| `getColumnTypeName(i)` | Tên kiểu SQL do driver/DBMS báo. | Tên có thể đặc thù theo DBMS. |
| `getPrecision(i)` / `getScale(i)` | Độ chính xác và số chữ số thập phân, tùy loại SQL. | Không phải lúc nào cũng đầy đủ hoặc áp dụng giống nhau. |
| `isNullable(i)` | Khả năng chứa NULL của cột kết quả theo metadata. | Có thể trả `columnNullableUnknown`. |
| `DatabaseMetaData.getColumns(...)` | Kiểu cột theo schema/table, gồm `DATA_TYPE`, `TYPE_NAME`, `COLUMN_SIZE`, `DECIMAL_DIGITS`. | Phụ thuộc quyền, schema và cách driver báo metadata. |
| `ParameterMetaData` | Thông tin tham số của `PreparedStatement`. | Một số driver không suy được type/precision khi SQL chưa prepare ở server. |

**Không dùng metadata làm biện pháp xác minh duy nhất.** Một cột báo `DECIMAL(10,2)` có thể nhận dữ liệu đầu vào theo một quy tắc làm tròn của DBMS; cần xác minh giá trị đã lưu nếu độ chính xác là yêu cầu quan trọng.

## 4. Số nguyên: phát hiện tràn thay vì ép kiểu

Java có các miền giá trị cố định:

| Kiểu Java | Miền giá trị |
| --- | --- |
| `byte` | −128 đến 127 |
| `short` | −32.768 đến 32.767 |
| `int` | −2.147.483.648 đến 2.147.483.647 |
| `long` | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |

Các kiểu SQL tương tự `TINYINT`, `SMALLINT`, `INTEGER` và `BIGINT` thường được dùng để lưu số nguyên nhưng **miền giá trị chính xác còn phụ thuộc DBMS**. Ví dụ, một số DBMS có biến thể `UNSIGNED` mà Java `long` có thể không chứa hết.

### 4.1. Ví dụ ép kiểu gây sai âm thầm

~~~java
long databaseValue = 3_000_000_000L;

int unsafe = (int) databaseValue;
System.out.println(unsafe); // Giá trị khác 3_000_000_000.
~~~

Lệnh ép kiểu này không tự ném exception khi giá trị vượt `int`. Nếu ID hoặc số lượng bị biến đổi, việc truy cập đối tượng sai có thể gây lỗi nghiệp vụ nghiêm trọng.

### 4.2. Chuyển đổi có kiểm tra

~~~java
long databaseValue = 3_000_000_000L;

try {
    int safe = Math.toIntExact(databaseValue);
    System.out.println(safe);
} catch (ArithmeticException ex) {
    throw new IllegalArgumentException(
            "Giá trị vượt miền int Java: " + databaseValue, ex);
}
~~~

`Math.toIntExact(long)` ném `ArithmeticException` nếu kết quả không thể biểu diễn chính xác bằng `int`. Khi nguồn là `BigDecimal`:

~~~java
BigDecimal value = new BigDecimal("123.00");

int exact = value.intValueExact(); // 123, không mất phần lẻ.

BigDecimal fractional = new BigDecimal("123.45");
fractional.intValueExact(); // ArithmeticException: có phần thập phân.
~~~

`BigDecimal.intValue()` / `longValue()` **có thể loại bỏ phần lẻ hoặc làm sai giá trị khi không vừa miền**, nên dùng `intValueExact()` / `longValueExact()` nếu hợp đồng cần chuyển đổi chính xác.

### 4.3. Chọn getter đúng ngay từ đầu

Nếu cột SQL là `BIGINT` có thể lớn hơn giới hạn `int`, hãy đọc về `long`:

~~~java
long orderId = rs.getLong("order_id");
~~~

Tránh đọc ngay bằng `getInt("order_id")` rồi hy vọng driver tự phát hiện tràn. Mức kiểm tra tràn/sự biến đổi của driver có thể không đồng nhất giữa các hệ quản trị.

Nếu business layer thật sự cần `int`:

~~~java
long orderIdLong = rs.getLong("order_id");
if (rs.wasNull()) {
    throw new IllegalStateException("order_id không được NULL");
}
int orderId = Math.toIntExact(orderIdLong);
~~~

**Đặt `wasNull()` ngay sau getter cần kiểm tra.** Một lời gọi getter khác trước đó có thể khiến `wasNull()` áp dụng cho cột khác.

## 5. DECIMAL/NUMERIC: kiểm soát precision và scale

Các kiểu `DECIMAL(p,s)` hoặc `NUMERIC(p,s)` thường dành cho giá trị thập phân có độ chính xác xác định.

- **Precision `p`:** tổng số chữ số thập phân có thể chứa theo định nghĩa kiểu.
- **Scale `s`:** số chữ số ở bên phải dấu thập phân.
- Với `DECIMAL(10,2)`, phần nguyên tối đa thường có **8 chữ số**, phần lẻ tối đa có **2 chữ số**.

Ví dụ:

| Giá trị | `DECIMAL(10,2)` có thể lưu chính xác? | Lý do |
| --- | --- | --- |
| `12.34` | Có. | Vừa precision và scale. |
| `99999999.99` | Có theo miền giá trị thông thường. | 8 chữ số phần nguyên, 2 chữ số phần lẻ. |
| `100000000.00` | Không. | Phần nguyên 9 chữ số vượt giới hạn. |
| `12.345` | Không thể giữ nguyên ở scale 2. | Cần làm tròn hoặc từ chối. |
| `12.340` | Có cùng **giá trị số** sau khi đưa về scale 2. | Chữ số 0 cuối không đổi giá trị, nhưng biểu diễn scale có thay đổi. |

Việc DBMS từ chối, làm tròn hay sinh cảnh báo khi nhận giá trị không vừa kiểu phụ thuộc hệ quản trị và chế độ cấu hình. **Không dựa vào sự khác biệt đó để bảo vệ dữ liệu tài chính.**

### 5.1. Ưu tiên `BigDecimal` thay vì `double` cho tiền và decimal exact

~~~java
// Giá trị thập phân được định nghĩa chính xác từ chuỗi.
BigDecimal amount = new BigDecimal("1200.35");

// Không nên lấy BigDecimal từ literal double nếu muốn số thập phân đúng nghĩa.
BigDecimal fromBinary = new BigDecimal(0.1);
System.out.println(fromBinary); // Thể hiện sai số biểu diễn nhị phân.
~~~

`new BigDecimal("0.1")` thể hiện chính xác số thập phân `0.1`. `BigDecimal.valueOf(0.1)` dùng biểu diễn decimal của giá trị `double`, thường tiện cho chuyển đổi hơn constructor nhận `double`, nhưng **không khôi phục được độ chính xác gốc nếu phép tính đã mất thông tin trước đó**.

**Mẫu an toàn với tiền:** Nhận giá trị ở định dạng decimal hợp lệ, parse trực tiếp bằng `BigDecimal(String)` và truyền với `PreparedStatement.setBigDecimal(...)`.

### 5.2. Kiểm tra decimal trước khi ghi

Hàm sau yêu cầu số **vừa `DECIMAL(p,s)` mà không phải làm tròn**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class DecimalConstraints {
    private DecimalConstraints() {}

    public static BigDecimal requireExact(
            BigDecimal value, int precision, int scale) {
        Objects.requireNonNull(value, "value");

        if (precision <= 0 || scale < 0 || scale > precision) {
            throw new IllegalArgumentException(
                    "Yêu cầu 0 <= scale <= precision và precision > 0");
        }

        final BigDecimal normalized;
        try {
            // Cho phép 12.340 -> 12.34, nhưng không cho 12.345 -> 12.35.
            normalized = value.setScale(
                    scale, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Số chữ số thập phân vượt scale=" + scale, ex);
        }

        int integerDigits = Math.max(
                0, normalized.precision() - normalized.scale());

        if (integerDigits > precision - scale) {
            throw new IllegalArgumentException(
                    "Phần nguyên vượt DECIMAL(" + precision
                    + "," + scale + ")");
        }

        return normalized;
    }
}
~~~

Ví dụ:

~~~java
DecimalConstraints.requireExact(
        new BigDecimal("12.340"), 10, 2);       // 12.34

DecimalConstraints.requireExact(
        new BigDecimal("12.345"), 10, 2);       // Ném exception.

DecimalConstraints.requireExact(
        new BigDecimal("100000000.00"), 10, 2); // Ném exception.
~~~

Đoạn mã giới hạn theo mô hình `DECIMAL(p,s)` phổ biến với `0 <= s <= p`. Một số DBMS cho phép khai báo scale ngoài miền đó hoặc diễn giải kiểu numeric khác; muốn hỗ trợ các biến thể đặc thù cần viết chính sách riêng theo tài liệu DBMS.

Đây là **kiểm tra tại ứng dụng** để phát hiện lỗi sớm, không thay thế ràng buộc cột, quyền, transaction hay xác minh dữ liệu đã ghi ở database.

### 5.3. Làm tròn có chủ đích là nghiệp vụ riêng

Nếu nghiệp vụ **cho phép** làm tròn, phải chọn chính sách rõ ràng:

~~~java
BigDecimal original = new BigDecimal("12.345");

BigDecimal rounded = original.setScale(
        2, RoundingMode.HALF_UP); // 12.35
~~~

`HALF_UP`, `HALF_EVEN`, `DOWN`... không tương đương. Không âm thầm chọn một kiểu làm tròn chỉ để insert không báo lỗi; với giá cả, thuế, tỷ giá và đơn vị tiền tệ, quy tắc cần được xác định bởi hợp đồng nghiệp vụ.

**Lưu ý:** Hai giá trị `new BigDecimal("12.340")` và `new BigDecimal("12.34")` bằng nhau về **giá trị số** khi dùng `compareTo(...) == 0`, nhưng `equals(...)` còn xét scale. Vì vậy, khi kiểm tra round-trip, phải quyết định cần giữ nguyên **giá trị**, hay còn yêu cầu giữ cả **biểu diễn/scale**.

## 6. Ghi dữ liệu có kiểm tra với `PreparedStatement`

Giả sử bảng có cột `amount DECIMAL(10,2)` và `quantity INTEGER`:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class InvoiceWriter {
    public static int insert(
            DataSource dataSource,
            long id,
            BigDecimal amount,
            long quantity) throws SQLException {

        BigDecimal safeAmount =
                DecimalConstraints.requireExact(amount, 10, 2);

        int safeQuantity = Math.toIntExact(quantity);

        String sql = """
                INSERT INTO invoice (id, amount, quantity)
                VALUES (?, ?, ?)
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setBigDecimal(2, safeAmount);
            ps.setInt(3, safeQuantity);

            return ps.executeUpdate();
        }
    }
}
~~~

Ở đây `DecimalConstraints` là lớp đã định nghĩa ở mục trước. `setBigDecimal(...)` và `setInt(...)` truyền **kiểu Java phù hợp** với dữ liệu cần lưu; chúng **không bảo đảm** DBMS sẽ giữ nguyên dữ liệu nếu định nghĩa cột thực tế khác giả định.

Nếu một môi trường đổi schema từ `DECIMAL(10,2)` thành `DECIMAL(8,1)` nhưng ứng dụng không biết, việc kiểm tra local theo thông số cũ vẫn chưa đủ. Cần đồng bộ hợp đồng schema/metadata và thử nghiệm tích hợp với database mục tiêu.

### 6.1. `setObject(...)` có thể hữu ích nhưng không miễn kiểm tra kiểu

`PreparedStatement.setObject(index, value)` và các overload nhận `java.sql.Types`/`SQLType` giúp biểu diễn kiểu đích, chẳng hạn:

~~~java
ps.setObject(2, new BigDecimal("18.50"), java.sql.Types.DECIMAL);
~~~

Việc chỉ định kiểu SQL giúp driver biết ý định chuyển đổi, nhưng **không có nghĩa sẽ tự phát hiện mọi mất thông tin hoặc kiểm soát scale theo nghiệp vụ**. Khi yêu cầu exact, hãy validate `BigDecimal` trước rồi kiểm chứng kết quả trên DBMS.

### 6.2. Không tự chuyển qua `String` để tránh lỗi type

Ví dụ:

~~~java
// Không khuyến nghị: đưa mọi dữ liệu về String để DBMS tự CAST.
ps.setString(1, "123.456");
~~~

Nếu cột đích là DECIMAL hoặc INTEGER, driver/DBMS có thể từ chối hoặc chuyển đổi theo quy tắc riêng; lỗi và ý nghĩa còn phụ thuộc thiết lập SQL mode, locale hoặc driver. Hãy dùng setter có kiểu phù hợp, chẳng hạn `setBigDecimal`, `setInt`, `setLong` hoặc `setObject` có kiểu SQL minh bạch.

## 7. Đọc dữ liệu không mất thông tin: chọn getter đúng

Một câu SELECT có thể trả giá trị SQL hợp lệ nhưng getter Java quá hẹp:

~~~java
// Cột amount là DECIMAL(18,2).
double wrongForMoney = rs.getDouble("amount");
~~~

Giá trị `double` phù hợp tính toán gần đúng, nhưng không phải nơi lưu giá trị tiền tệ có yêu cầu chính xác tới cent hoặc các chữ số decimal cố định.

Thay vào đó:

~~~java
BigDecimal amount = rs.getBigDecimal("amount");
if (amount == null) {
    // Bên gọi quyết định xử lý SQL NULL.
}
~~~

Nếu cần biến decimal thành integer, không nên gọi `getInt(...)` ngay trên cột có phần thập phân. Đọc `BigDecimal`, xác minh null rồi chuyển exact:

~~~java
BigDecimal quantityDecimal = rs.getBigDecimal("quantity");

Integer quantity = (quantityDecimal == null)
        ? null
        : quantityDecimal.intValueExact();
~~~

Tùy driver, việc gọi getter sai kiểu có thể ném `SQLException`, hoặc nó có thể chuyển đổi bằng quy tắc riêng. **Đừng dựa vào một hành vi ngầm định khi hợp đồng dữ liệu yêu cầu bảo toàn chính xác.**

### 7.1. Mẫu repository đọc strict mapping

Ví dụ SQL bảng `invoice(id BIGINT, amount DECIMAL(10,2), quantity INTEGER)`:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class InvoiceReader {
    public record Invoice(
            long id, BigDecimal amount, Integer quantity) {}

    public static Optional<Invoice> findById(
            DataSource dataSource, long id) throws SQLException {

        String sql = """
                SELECT id, amount, quantity
                FROM invoice
                WHERE id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                long dbId = rs.getLong("id");
                if (rs.wasNull()) {
                    throw new SQLException("invoice.id bất ngờ là NULL");
                }

                BigDecimal amount = rs.getBigDecimal("amount");
                // Ví dụ quy ước amount NOT NULL.
                if (amount == null) {
                    throw new SQLException("invoice.amount là NULL");
                }

                int rawQuantity = rs.getInt("quantity");
                Integer quantity = rs.wasNull()
                        ? null
                        : rawQuantity;

                return Optional.of(
                        new Invoice(dbId, amount, quantity));
            }
        }
    }
}
~~~

Lưu ý: ví dụ chọn `getInt("quantity")` vì cột **được khai báo INTEGER** trong hợp đồng schema. Nếu cột thực tế là `BIGINT` và có thể lớn hơn miền `int`, hãy đọc `getLong` và kiểm tra bằng `Math.toIntExact` trước khi tạo DTO.

DTO trả ra đã được materialize, nên vẫn dùng được sau khi `ResultSet`, `PreparedStatement` và `Connection` đóng.

## 8. NULL: dữ liệu không có giá trị khác với số 0 và chuỗi rỗng

Một số getter dùng kiểu nguyên thủy trả **giá trị mặc định** khi cột SQL là `NULL`:

| Getter | Kiểu Java | Giá trị Java khi SQL NULL | Cách phân biệt |
| --- | --- | --- | --- |
| `getInt(...)` | `int` | `0` | `rs.wasNull()` |
| `getLong(...)` | `long` | `0L` | `rs.wasNull()` |
| `getDouble(...)` | `double` | `0.0` | `rs.wasNull()` |
| `getBoolean(...)` | `boolean` | `false` | `rs.wasNull()` |
| `getString(...)` | `String` | `null` | Có thể kiểm tra trực tiếp. |
| `getBigDecimal(...)` | `BigDecimal` | `null` | Có thể kiểm tra trực tiếp. |

Ví dụ dễ sai:

~~~java
int retryCount = rs.getInt("retry_count");

// retryCount == 0 không cho biết DB lưu 0 hay NULL.
~~~

Cách đúng khi field nullable:

~~~java
int raw = rs.getInt("retry_count");
Integer retryCount = rs.wasNull() ? null : raw;
~~~

**Không gọi getter khác giữa `getInt(...)` và `wasNull()`.** Phương thức `wasNull()` cho biết giá trị **vừa được đọc cuối cùng** có là SQL NULL hay không.

Khi ghi `NULL`:

~~~java
if (retryCount == null) {
    ps.setNull(1, java.sql.Types.INTEGER);
} else {
    ps.setInt(1, retryCount);
}
~~~

Không tự đổi Java `null` thành `0`, chuỗi rỗng hoặc ngày mặc định trừ khi đó là **quy tắc nghiệp vụ được chấp nhận**. Lưu ý một số DBMS có xử lý đặc thù với chuỗi rỗng (ví dụ không phải mọi hệ quản trị đều phân biệt chuỗi rỗng với SQL NULL theo cùng cách).

### 8.1. Có nên dùng `getObject(...)`?

Với các kiểu tham chiếu được hỗ trợ, `ResultSet.getObject(column, Type.class)` có thể đọc về Java type cần thiết:

~~~java
Integer retries = rs.getObject("retry_count", Integer.class);
~~~

Cách này tiện khi driver hỗ trợ mapping tương ứng, nhưng **không phải cam kết mọi phiên bản driver đều hỗ trợ mọi chuyển đổi yêu cầu**. Với kiểu dữ liệu đặc thù hoặc driver cũ, kiểm thử thực tế hoặc dùng getter tường minh + `wasNull()`.

## 9. FLOAT/DOUBLE: sai số biểu diễn và độ chính xác

Không phải mọi vấn đề đều đến từ kiểu cột có precision/scale. Các kiểu số thực dấu phẩy động `float` và `double` là biểu diễn **xấp xỉ** theo cơ số hai.

~~~java
double x = 0.1;
double y = 0.2;

System.out.println(x + y); // Thường in 0.30000000000000004.
System.out.println((x + y) == 0.3); // false
~~~

Khi dữ liệu được lưu bằng kiểu SQL gần đúng như `REAL` / `FLOAT` / `DOUBLE PRECISION`, độ chính xác và quy tắc làm tròn còn tùy DBMS. Đọc lại bằng `double` không biến giá trị thành số decimal exact.

Nên:

- Dùng **`DECIMAL/NUMERIC + BigDecimal`** khi hợp đồng cần số thập phân chính xác (tiền, số lượng với precision xác định).
- Dùng `float`/`double` cho đại lượng **cho phép sai số**; xác định tolerance theo miền bài toán.
- Không so sánh hai kết quả xấp xỉ bằng `==` trong bài toán tính toán có sai số.
- Khi dùng `double` ở dữ liệu đầu vào, kiểm tra `Double.isFinite(value)` nếu nghiệp vụ không cho phép NaN/Infinity; hỗ trợ các giá trị đặc biệt khác nhau giữa DBMS.
- Khi chuyển kết quả số thực sang số nguyên hoặc decimal, kiểm tra chính xác và giới hạn theo **chính sách riêng**, không mặc định ép kiểu là không mất dữ liệu.

**Ví dụ về kiểm tra sai số:** Với dữ liệu khoa học, có thể định nghĩa sai số tuyệt đối hoặc tương đối được phép. Giá trị tolerance phải gắn với đơn vị đo và miền giá trị; không sử dụng một epsilon cố định cho mọi bài toán.

## 10. Chuỗi ký tự: độ dài, encoding và làm mất ký tự

Một cột `VARCHAR(n)` có thể giới hạn độ dài theo **ký tự**, **đơn vị mã** hoặc **byte** tùy DBMS, charset và cấu hình kiểu. Không nên cho rằng `String.length() <= n` luôn đủ.

Trong Java, `String.length()` đếm **đơn vị mã UTF-16**, còn `codePointCount(...)` đếm **Unicode code point**:

~~~java
import java.nio.charset.StandardCharsets;

String text = "A😀";

System.out.println(text.length()); // 3 đơn vị mã UTF-16.
System.out.println(text.codePointCount(0, text.length())); // 2 code point.
System.out.println(text.getBytes(StandardCharsets.UTF_8).length);
                                                    // 5 byte UTF-8.
~~~

Những số này không nhất thiết bằng số **ký tự hiển thị** (grapheme cluster). Ví dụ một chữ có dấu có thể gồm nhiều code point, còn emoji có thể gồm chuỗi code point kết hợp.

### 10.1. Kiểm tra trước khi ghi

Với cột bị giới hạn byte theo UTF-8, có thể dùng:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

if (bytes.length > maxUtf8Bytes) {
    throw new IllegalArgumentException(
            "Chuỗi vượt giới hạn byte được phép");
}
~~~

Nhưng đây chỉ là kiểm tra đúng khi **hợp đồng DBMS xác định giới hạn theo bytes của UTF-8**. Nếu database sử dụng charset khác hoặc cột định nghĩa giới hạn theo ký tự, phải kiểm tra theo semantics thực của cột.

Không cắt tùy tiện bằng `substring(0, n)` rồi cho rằng đã giải quyết vì:

- Có thể chia cắt một cặp surrogate hoặc cụm ký tự Unicode.
- Có thể làm thay đổi ý nghĩa tên, địa chỉ hoặc dữ liệu định danh.
- Độ dài Java không phản ánh hoàn toàn giới hạn byte/char của cột.
- Một số DBMS **đệm dấu cách** cho kiểu cố định như `CHAR(n)` hoặc loại bỏ một số dấu cách theo quy tắc riêng.

Nếu ứng dụng cho phép cắt chuỗi, quy tắc cắt phải là **quy tắc sản phẩm** đã được mô tả và kiểm thử; không biến cắt dữ liệu thành hành vi mặc định của tầng JDBC.

### 10.2. Phát hiện sai khác khi đọc lại

Với giá trị có dấu, emoji và ký tự bổ sung, kiểm thử round-trip:

~~~java
String original = "Tiếng Việt 😀";
String persisted = /* đọc lại bằng ResultSet.getString(...) */ "";

if (!original.equals(persisted)) {
    throw new IllegalStateException(
            "Nội dung Unicode đã thay đổi sau khi lưu/đọc");
}
~~~

Đoạn trích minh họa phép đối chiếu; cần gán `persisted` bằng dữ liệu đọc thật từ database thử nghiệm. Nếu hợp đồng cho phép chuẩn hóa Unicode hoặc chuyển đổi hoa/thường, phải **chuẩn hóa có chủ đích trên hai phía** trước khi so. Không xem sự khác biệt là chấp nhận được chỉ vì tìm kiếm `LIKE` vẫn khớp.

**Đối với dữ liệu nhị phân**, so sánh bằng `Arrays.equals(expected, actual)` hoặc checksum phù hợp; checksum chỉ là phép kiểm tra nhất quán chứ không tự giải thích nguyên nhân sai.

## 11. Ngày giờ: mất offset, múi giờ hoặc phần lẻ giây

Các kiểu thời gian có hai nhóm ngữ nghĩa cần tách:

- **Thời điểm thực trên trục thời gian:** ví dụ sự kiện xảy ra tại một instant xác định, có thể biểu diễn bằng `Instant` hoặc `OffsetDateTime` khi mapping hỗ trợ.
- **Ngày giờ địa phương không gắn múi giờ:** ví dụ cuộc hẹn lúc `09:00` theo lịch địa phương, có thể biểu diễn bằng `LocalDateTime` nhưng cần thêm thông tin vùng giờ nếu muốn xác định instant.

JDBC 4.2 đưa ra mapping với nhiều kiểu `java.time`, nhưng mức hỗ trợ thực tế phụ thuộc driver và kiểu SQL. Một cách dùng phổ biến:

~~~java
LocalDate date = rs.getObject("business_date", LocalDate.class);
LocalDateTime local = rs.getObject(
        "local_event_time", LocalDateTime.class);
OffsetDateTime occurredAt = rs.getObject(
        "occurred_at", OffsetDateTime.class);
~~~

Các câu lệnh trên giả sử cột SQL và driver hỗ trợ mapping tương ứng, ví dụ `DATE`, `TIMESTAMP WITHOUT TIME ZONE` và một kiểu timestamp with time zone phù hợp. **Không áp dụng mù quáng `OffsetDateTime` cho mọi cột `TIMESTAMP`**.

### 11.1. Vì sao `LocalDateTime` có thể làm mất ý nghĩa?

Giả sử hai chuỗi đầu vào:

~~~text
2026-11-16T09:00:00+07:00
2026-11-16T09:00:00+00:00
~~~

Chúng có **cùng giờ hiển thị nhưng là hai thời điểm cách nhau bảy tiếng**. Nếu chỉ giữ phần `2026-11-16T09:00:00` trong `LocalDateTime`, thông tin offset đã mất và không thể khôi phục chính xác hai instant ban đầu.

Ngược lại, hai offset khác nhau có thể chỉ cùng **một instant**. Nếu hệ thống chỉ cần thời điểm tuyệt đối, lưu/so sánh theo instant thích hợp; nếu cần giữ **offset gốc do người dùng cung cấp**, phải quyết định lưu thêm offset (hoặc thông tin vùng giờ) tùy mục tiêu nghiệp vụ.

Không đồng nhất `OffsetDateTime` với `ZonedDateTime`: offset `+07:00` không chứa đầy đủ quy tắc múi giờ theo vùng, ví dụ thay đổi giờ mùa hè trong lịch sử/tương lai.

### 11.2. Precision của phần lẻ giây

Một nguồn mất thông tin khác là phần lẻ giây:

~~~text
Giá trị Java:  2026-11-16T09:00:00.123456789
Cột SQL:       TIMESTAMP(3)
Giá trị lưu:   có thể bị làm tròn/cắt về mức millisecond theo DBMS.
~~~

Nếu hợp đồng yêu cầu nanosecond, cần biết DBMS/driver hỗ trợ tối đa bao nhiêu chữ số phần lẻ giây và áp dụng chính sách làm tròn hoặc từ chối trước khi lưu.

**Đừng dựa vào format chuỗi hiển thị để đánh giá mất thông tin.** Hãy lấy lại giá trị dưới dạng temporal type có ngữ nghĩa đúng rồi so sánh theo `Instant`, `LocalDateTime` hoặc thành phần mà hợp đồng thực sự yêu cầu.

### 11.3. Chú ý múi giờ mặc định và DST

Các API JDBC cũ như `getTimestamp(...)` và `setTimestamp(...)`, hoặc các overload có `Calendar`, có thể phụ thuộc múi giờ mặc định/Calendar và cách driver diễn giải kiểu SQL. Một thay đổi timezone của JVM hoặc ngày chuyển giờ mùa hè có thể làm kết quả khác nhau.

Nên thực hiện integration test với: giá trị UTC, offset khác nhau, các ngày sát thời điểm chuyển DST và thời điểm có phần lẻ giây. Không thử chuyển kiểu bằng một ngày bình thường duy nhất rồi kết luận cả năm sẽ đúng.

## 12. Dữ liệu ngoài kiểu số: Boolean, JSON, UUID và LOB

Bên cạnh numeric/text/date, một số kiểu cần hợp đồng chuyển đổi riêng:

| Dữ liệu | Rủi ro | Cách kiểm tra |
| --- | --- | --- |
| `BOOLEAN`/`BIT` | DBMS/driver có thể dùng bit, số hoặc chuỗi để biểu diễn; NULL khác false. | Đọc kiểu tương ứng, kiểm tra `wasNull()` với `getBoolean()`. |
| ENUM/trạng thái | Giá trị mới trên DB không có trong enum Java; fallback “UNKNOWN” có thể làm mất nghĩa. | Mapping đầy đủ, xử lý giá trị ngoài miền và kế hoạch tương thích schema. |
| UUID | DBMS có thể lưu kiểu UUID native, `CHAR(36)` hoặc binary. | Kiểm tra định dạng, thứ tự byte và round-trip theo DBMS/driver. |
| JSON | Số lớn có thể bị parser chuyển thành `double`, bỏ mất chữ số; object field có thể thay đổi. | Parser giữ precision cần thiết; kiểm thử giá trị lớn, NULL, thứ tự/kiểu dữ liệu theo yêu cầu. |
| `BINARY/VARBINARY/BLOB` | Cắt bytes, bỏ phần stream, sai mã hóa giữa byte và String. | Giữ kiểu `byte[]`/stream đúng, kiểm tra length/checksum và resource lifetime. |
| SQL `ARRAY` | Kiểu phần tử hoặc NULL phần tử không tương thích Java array mong muốn. | Kiểm tra metadata, dữ liệu phần tử và driver trước khi chuyển. |

Đặc biệt, nếu một `BIGINT` lớn hơn `2^53 - 1` được đưa qua JavaScript number trong API JSON, có thể mất chữ số **sau khi đã đọc JDBC chính xác**. Do đó, kiểm tra mất thông tin phải bao quát toàn bộ đường đi **database → Java → JSON/UI** khi nghiệp vụ cần giữ ID/số chính xác.

Với BLOB/CLOB, đừng trả stream hoặc locator vẫn phụ thuộc `ResultSet` đã đóng. Đọc đủ dữ liệu trong phạm vi JDBC còn mở hoặc copy có kiểm soát vào đích do caller sở hữu.

## 13. SQLWarning và lỗi: tín hiệu hữu ích nhưng chưa đủ

Một số chuyển đổi được database/driver thông báo qua `SQLException` hoặc `SQLWarning`, nhưng **không phải mọi mất thông tin đều tạo cảnh báo**. Ví dụ, `double` biểu diễn `0.1` xấp xỉ là tính chất số học, không nhất thiết là lỗi hoặc warning của driver.

`SQLWarning` có thể gắn với `Connection`, `Statement` hoặc `ResultSet`. Có thể thu thập khi cần chẩn đoán:

~~~java
import java.sql.SQLWarning;

public static void reportWarnings(SQLWarning warning) {
    for (SQLWarning w = warning;
         w != null;
         w = w.getNextWarning()) {

        System.out.printf("SQLState=%s, code=%d, message=%s%n",
                w.getSQLState(),
                w.getErrorCode(),
                w.getMessage());
    }
}

// Gọi ở vị trí phù hợp, ngay sau thao tác quan tâm:
reportWarnings(ps.getWarnings());
reportWarnings(connection.getWarnings());
~~~

Trong production, không in trực tiếp thông điệp lỗi nếu nó chứa dữ liệu nhạy cảm; hãy lọc/sanitise log. Warnings có thể được xóa theo các thao tác statement/connection hoặc cách triển khai driver, nên **đọc ở thời điểm gần thao tác** đang đánh giá.

| Tín hiệu | Cách diễn giải |
| --- | --- |
| `SQLException` | Có lỗi khi thao tác. Xem SQLState, vendor code và trạng thái transaction. |
| `SQLDataException` (một nhánh của `SQLException`) | Lỗi liên quan dữ liệu/chuyển đổi theo loại exception của JDBC khi driver sử dụng. |
| `SQLWarning` | Thao tác có thể hoàn tất nhưng có cảnh báo; cần xem lý do. |
| Không lỗi/cảnh báo | **Chưa đủ bằng chứng** giá trị được bảo toàn chính xác. Cần round-trip và đối chiếu nghiệp vụ. |

Không bắt mọi `SQLException` rồi mặc định sửa bằng cách cắt chuỗi hoặc làm tròn số. Khi phát hiện mất dữ liệu, cần quyết định **từ chối, chuyển đổi có chủ đích hoặc nâng schema**.

## 14. Kiểm tra round-trip trên database thật

Để phát hiện mất thông tin do driver hoặc server, hãy ghi **dữ liệu thử nghiệm**, đọc lại rồi so sánh với kỳ vọng.

~~~mermaid
flowchart LR
    A[Giá trị đầu vào] --> B[Validate theo hợp đồng]
    B --> C[Bind đúng kiểu và INSERT/UPDATE trong test transaction]
    C --> D[SELECT đọc lại bằng getter phù hợp]
    D --> E{Giá trị còn đúng?}
    E -- Có --> F[PASS]
    E -- Không --> G[FAIL: đo phạm vi mất thông tin]
    F --> H[Rollback dữ liệu test]
    G --> H
~~~

Ví dụ kiểm tra với bảng test `conversion_probe(id VARCHAR(36) PRIMARY KEY, amount DECIMAL(10,2))` đã được tạo trong **database thử nghiệm**:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public static void assertDecimalRoundTrip(
        DataSource dataSource, BigDecimal input) throws SQLException {

    BigDecimal expected =
            DecimalConstraints.requireExact(input, 10, 2);
    String id = UUID.randomUUID().toString();

    try (Connection connection = dataSource.getConnection()) {
        if (!connection.getAutoCommit()) {
            throw new SQLException(
                    "Ví dụ yêu cầu kết nối test ở autoCommit=true");
        }

        connection.setAutoCommit(false);
        try {
            try (PreparedStatement insert = connection.prepareStatement(
                    "INSERT INTO conversion_probe(id, amount) VALUES (?, ?)")) {

                insert.setString(1, id);
                insert.setBigDecimal(2, expected);
                insert.executeUpdate();
            }

            try (PreparedStatement select = connection.prepareStatement(
                    "SELECT amount FROM conversion_probe WHERE id = ?")) {

                select.setString(1, id);

                try (ResultSet rs = select.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Không tìm thấy dữ liệu test");
                    }

                    BigDecimal actual = rs.getBigDecimal("amount");
                    if (actual == null
                            || expected.compareTo(actual) != 0) {
                        throw new SQLException(
                                "Round-trip sai giá trị DECIMAL");
                    }
                }
            }
        } finally {
            // Rollback dữ liệu test cả khi kiểm tra thất bại.
            try {
                connection.rollback();
            } finally {
                connection.setAutoCommit(true);
            }
        }
    }
}
~~~

**Ý nghĩa của ví dụ:**

- `requireExact(...)` chặn giá trị không vừa `DECIMAL(10,2)` trước khi ghi.
- `setBigDecimal/getBigDecimal` giữ đường dữ liệu theo decimal.
- `compareTo(...) == 0` kiểm tra giá trị số, tránh nhầm scale hiển thị.
- Transaction được rollback để không giữ lại hàng test.

Đoạn mã giả định kết nối test **không do transaction manager khác sở hữu** và bảng đã có sẵn. Khi chạy trong framework/connection pool, hãy để tầng sở hữu transaction quản lý rollback và khôi phục trạng thái. Nếu rollback hoặc reset thất bại, connection có thể không còn đáng tin; cần để pool/framework xử lý lỗi và tránh tiếp tục dùng connection đó.

**Không chạy phép thử ghi trên dữ liệu production.** Dùng database test có cùng DBMS, schema, driver, cấu hình charset, timezone và chế độ SQL với môi trường triển khai. Nếu chỉ dùng H2 thay cho PostgreSQL/MySQL/SQL Server, bạn mới kiểm tra **H2**, chưa xác nhận quy tắc chuyển đổi của production.

### 14.1. Thử trên dữ liệu ranh giới

Một bộ test nên bao gồm:

| Nhóm | Dữ liệu cần thử | Mục đích |
| --- | --- | --- |
| `DECIMAL(10,2)` | `0.00`, `99999999.99`, `-99999999.99`, `12.345`, `100000000.00` | Giới hạn precision, scale và dấu âm. |
| Số nguyên | `Integer.MAX_VALUE`, thêm 1, `Long.MAX_VALUE` nếu hợp lệ | Phát hiện narrowing/overflow. |
| Nullable | `NULL`, `0`, `false`, chuỗi rỗng | Không nhập nhằng giá trị mặc định với thiếu dữ liệu. |
| Unicode | Tiếng Việt có dấu, emoji, ký tự ghép, chuỗi sát giới hạn | Charset và độ dài. |
| Thời gian | Giữa ngày, sát midnight, DST, nanosecond | Offset, timezone, precision. |
| Số thực gần đúng | `0.1`, số rất lớn/nhỏ, không hữu hạn nếu có | Sai số và giới hạn floating-point. |
| Binary/LOB | Dữ liệu trống, bytes `0x00`, kích thước lớn | Không cắt, không biến đổi bytes. |

Ngoài dữ liệu thành công, phải kiểm tra **phản hồi khi dữ liệu không hợp lệ**: exception có xảy ra, warning có xuất hiện, DBMS có tự làm tròn và transaction có bị ảnh hưởng không.

## 15. Checklist khi thiết kế mapping không mất thông tin

- [ ] Biết **kiểu SQL thực tế**, precision, scale, nullability và charset/timezone liên quan.
- [ ] Chọn **Java type có đủ miền giá trị**, không đọc `BIGINT` lớn thành `int`.
- [ ] Dùng `Math.toIntExact`, `BigDecimal.intValueExact` hoặc kiểm tra miền khi thu hẹp kiểu số.
- [ ] Dùng `BigDecimal` cho decimal exact; không chuyển tiền qua `float/double`.
- [ ] Với `DECIMAL(p,s)`, kiểm tra khả năng biểu diễn không làm tròn bằng `setScale(..., UNNECESSARY)` và precision phù hợp.
- [ ] Nếu nghiệp vụ chấp nhận rounding/truncation, định nghĩa **quy tắc rõ ràng**, có test và theo dõi.
- [ ] Phân biệt SQL `NULL` với `0`/`false` bằng `wasNull()` hoặc kiểu Java nullable.
- [ ] Kiểm tra giới hạn chuỗi theo semantics thật của DBMS; không đồng nhất UTF-16 units, Unicode code points và UTF-8 bytes.
- [ ] Chọn temporal type theo **instant, local date-time, offset hoặc zone**; kiểm tra precision phần lẻ giây và DST.
- [ ] Xem xét typed getter/setter thay vì trông cậy vào implicit conversion qua `setString`/`getString`.
- [ ] Xem `SQLException`/`SQLWarning` như tín hiệu chẩn đoán; **không xem thiếu warning là bằng chứng giá trị còn nguyên**.
- [ ] Chạy **round-trip integration test** với dữ liệu ranh giới trên đúng DBMS và driver triển khai.
- [ ] Kiểm tra cả đường đi sau JDBC như JSON serialization, ORM và API client nếu giá trị cần giữ chính xác.
- [ ] Chỉ dùng phép chuyển kiểu mất thông tin khi chính sách nghiệp vụ cho phép và đã công bố rõ.

**Ghi nhớ:** Trong JDBC, chuyển đổi “thành công” về mặt API không đồng nghĩa **không mất thông tin**. Hãy kiểm tra cả **miền giá trị, precision/scale, NULL, encoding, timezone** và ngữ nghĩa kiểu dữ liệu trước khi bind hoặc sau khi đọc. Với các giá trị cần chính xác tuyệt đối, chọn kiểu Java phù hợp, áp dụng chuyển đổi exact, kiểm chứng round-trip trên database đích và xem việc làm tròn/cắt dữ liệu là quyết định nghiệp vụ tường minh.
