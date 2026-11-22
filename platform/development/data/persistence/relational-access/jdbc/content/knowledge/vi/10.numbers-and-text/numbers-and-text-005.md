# Phân biệt số thập phân chính xác và số dấu phẩy động trong JDBC

Trong chương **Số và văn bản**, một quyết định quan trọng khi ứng dụng Java làm việc với cơ sở dữ liệu quan hệ là chọn cách biểu diễn số. Số tiền `0,10`, tỷ lệ thuế `0,0750` và kết quả đo `23,7` đều có phần thập phân, nhưng chúng không nhất thiết nên dùng cùng một kiểu dữ liệu. Với JDBC, lựa chọn này ảnh hưởng đồng thời đến **kiểu cột SQL**, **kiểu Java**, **cách truyền tham số bằng `PreparedStatement`**, **cách đọc `ResultSet`** và **quy tắc tính toán**.

Mục tiêu của bài học là phân biệt số thập phân **chính xác** (exact decimal) với số dấu phẩy động **xấp xỉ** (floating-point), biết khi nào dùng `BigDecimal` hoặc `double`/`float` và tránh các lỗi làm sai giá trị trong quy trình CRUD.

## 1. Hai cách biểu diễn, hai mục đích

### Số dấu phẩy động: `float` và `double`

Java dùng định dạng nhị phân IEEE 754 cho `float` (32 bit) và `double` (64 bit). Một giá trị được biểu diễn qua dấu, phần trị và số mũ cơ số 2. Vì vậy, nhiều phân số thập phân quen thuộc như `0.1`, `0.2` và `0.3` không có biểu diễn hữu hạn chính xác trong hệ nhị phân.

```java
double a = 0.1;
double b = 0.2;

System.out.println(a + b);         // 0.30000000000000004
System.out.println(a + b == 0.3);  // false
```

Đây là hệ quả của **biểu diễn xấp xỉ**, không phải lỗi của JDBC hay máy tính. `double` thường có khoảng 15–17 chữ số thập phân có nghĩa; `float` có độ chính xác thấp hơn, khoảng 6–9 chữ số. Hai kiểu này phù hợp với phép đo, mô phỏng, tính toán khoa học hoặc đồ họa khi sai số được chấp nhận và kiểm soát.

Không nên dùng phép so sánh `==` để quyết định hai kết quả tính dấu phẩy động có tương đương về mặt nghiệp vụ hay không. Nếu cần kiểm tra gần bằng, hãy chọn **ngưỡng sai số phù hợp với đơn vị đo và độ lớn giá trị**, thay vì mặc định một ngưỡng dùng cho mọi trường hợp.

### Số thập phân chính xác: `BigDecimal`

`java.math.BigDecimal` biểu diễn một số bằng số nguyên không chia tỷ lệ (*unscaled value*) và một `scale`. Về mặt khái niệm:

```text
giá trị = unscaledValue × 10^(-scale)

12.34  = 1234 × 10^(-2)
0.0750 = 750  × 10^(-4)
```

Những giá trị thập phân hữu hạn được khởi tạo từ chữ số thập phân có thể giữ **chính xác**; giới hạn thực tế là tài nguyên tính toán và ràng buộc của hệ thống lưu trữ. `BigDecimal` thích hợp cho tiền tệ, phí, thuế, tỷ giá, số lượng hàng hóa có bước thập phân xác định và các phép đối soát.

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
```

`BigDecimal` là đối tượng **bất biến**: `add`, `subtract`, `multiply`, `divide` và `setScale` trả về đối tượng mới, không sửa đối tượng ban đầu.

| Tiêu chí | Thập phân chính xác | Dấu phẩy động nhị phân |
| --- | --- | --- |
| Java | `BigDecimal` | `float`, `double` |
| SQL thường gặp | `DECIMAL(p,s)`, `NUMERIC(p,s)` | `REAL`, `FLOAT`, `DOUBLE PRECISION` |
| Giá trị như `0.1` | Lưu đúng giá trị thập phân nếu còn trong phạm vi kiểu | Thường là giá trị nhị phân gần `0.1` |
| Phép toán | Chính xác nếu phép toán có kết quả biểu diễn được; một số phép chia cần quy tắc làm tròn | Có sai số làm tròn theo IEEE 754 |
| Đổi lại | Tốn tài nguyên hơn; phải quản lý `scale` và làm tròn | Nhanh, thuận lợi cho nhiều phép toán số học |
| Trường hợp điển hình | Số tiền, giá, tỷ lệ tính phí | Nhiệt độ, tín hiệu cảm biến, mô phỏng |

> **Nguyên tắc chọn kiểu:** Khi một chênh lệch dù rất nhỏ cũng có thể làm sai tiền, báo cáo hoặc đối soát, ưu tiên số thập phân chính xác từ đầu đến cuối đường dữ liệu.

## 2. Chọn kiểu cột SQL theo ý nghĩa dữ liệu

Trong cơ sở dữ liệu quan hệ, `DECIMAL(p,s)` hoặc `NUMERIC(p,s)` là kiểu số thập phân chính xác. `p` là tổng số chữ số có nghĩa được phép lưu (*precision*); `s` là số chữ số bên phải dấu thập phân (*scale*).

Ví dụ, `DECIMAL(12,2)` dành 12 chữ số cho toàn bộ giá trị, trong đó có 2 chữ số sau dấu thập phân. Giá trị dương lớn nhất về mặt khuôn dạng là `9999999999.99`.

```sql
CREATE TABLE invoice_line (
    id           BIGINT PRIMARY KEY,
    amount       DECIMAL(12, 2) NOT NULL,
    tax_rate     DECIMAL(7, 4),
    sensor_value DOUBLE PRECISION
);
```

Ý nghĩa của các cột:

- `amount`: số tiền cần lưu với hai chữ số thập phân, nên dùng `BigDecimal` ở Java.
- `tax_rate`: tỷ lệ có thể cần bốn chữ số sau dấu thập phân, cũng nên dùng `BigDecimal`.
- `sensor_value`: số đo chấp nhận sai số biểu diễn, có thể dùng `double`.

`REAL`, `FLOAT` và `DOUBLE PRECISION` là những tên kiểu thường dùng cho dữ liệu dấu phẩy động, nhưng **độ chính xác, cú pháp và cách ánh xạ cụ thể phụ thuộc hệ quản trị cơ sở dữ liệu và driver JDBC**. Một số hệ còn có quy tắc đặc biệt cho `NUMERIC`, `FLOAT` hoặc kiểu `DECIMAL` không khai báo `p,s`. Vì vậy, hãy kiểm tra tài liệu của hệ quản trị đang dùng và thử đọc/ghi trên driver thực tế; đừng suy ra kiểu Java chỉ từ tên cột.

Việc đưa `BigDecimal` vào cột `DECIMAL(p,s)` vẫn có thể gây lỗi vượt phạm vi, lỗi `scale` hoặc làm tròn theo quy tắc của cơ sở dữ liệu. **Chính xác** không có nghĩa là **không giới hạn**.

## 3. Ánh xạ qua `PreparedStatement` và `ResultSet`

Với JDBC, hãy giữ đúng ý nghĩa dữ liệu khi truyền tham số và nhận kết quả:

| Kiểu cột | Ghi với `PreparedStatement` | Đọc với `ResultSet` |
| --- | --- | --- |
| `DECIMAL` / `NUMERIC` | `setBigDecimal(index, value)` | `getBigDecimal(column)` |
| `DOUBLE PRECISION` hoặc kiểu tương ứng | `setDouble(index, value)` | `getDouble(column)` |
| `REAL` hoặc kiểu tương ứng | `setFloat(index, value)` | `getFloat(column)` |

Ví dụ ghi một khoản tiền và một phép đo. `DataSource` cung cấp kết nối; `PreparedStatement` truyền giá trị dưới dạng tham số SQL, tránh ghép số vào câu lệnh bằng chuỗi:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public class InvoiceLineRepository {
    private final DataSource dataSource;

    public InvoiceLineRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(long id, BigDecimal amount, double sensorValue)
            throws SQLException {
        // Dữ liệu tiền phải có đúng 2 chữ số thập phân.
        // UNNECESSARY báo lỗi nếu cần làm tròn để đạt scale này.
        BigDecimal checkedAmount =
                amount.setScale(2, RoundingMode.UNNECESSARY);

        if (!Double.isFinite(sensorValue)) {
            throw new IllegalArgumentException("Số đo phải hữu hạn");
        }

        String sql = """
                INSERT INTO invoice_line (id, amount, sensor_value)
                VALUES (?, ?, ?)
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setBigDecimal(2, checkedAmount);
            statement.setDouble(3, sensorValue);
            statement.executeUpdate();
        }
    }
}
```

Ví dụ trên sử dụng *text block* của Java (Java 15+). Với phiên bản cũ hơn, có thể dùng chuỗi SQL thông thường. Nếu ứng dụng có transaction nhiều bước, cần quản lý `commit`/`rollback` ở phạm vi transaction phù hợp; chỉ riêng việc chọn `BigDecimal` không bảo đảm tính nhất quán giao dịch.

Đọc lại số tiền bằng đúng kiểu `BigDecimal`:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public BigDecimal findAmount(DataSource dataSource, long id)
        throws SQLException {
    String sql = "SELECT amount FROM invoice_line WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, id);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                return null; // Không có bản ghi với id này.
            }
            return result.getBigDecimal("amount");
        }
    }
}
```

Ở đây `amount` là `NOT NULL`; do đó `null` biểu thị *không tìm thấy dòng*. Nếu cột cho phép `NULL`, `ResultSet.getBigDecimal(...)` trả về `null` khi giá trị SQL là `NULL`. Với các getter kiểu nguyên thủy như `getDouble(...)`, JDBC trả về `0.0` cho SQL `NULL`; cần gọi `wasNull()` **ngay sau getter** để phân biệt dữ liệu `NULL` với số không thật:

```java
double measurement = result.getDouble("sensor_value");
if (result.wasNull()) {
    // sensor_value là SQL NULL.
} else {
    // measurement là giá trị được đọc từ cột.
}
```

**Không đọc `DECIMAL` bằng `getDouble` rồi chuyển lại thành `BigDecimal`** nếu cần giữ chính xác. Sai số hoặc phần chữ số bị mất trong bước trung gian thường không thể phục hồi.

## 4. Khởi tạo `BigDecimal`: tránh đưa sai số vào từ đầu

Ba cách tạo đối tượng dưới đây không tương đương:

```java
import java.math.BigDecimal;

BigDecimal exact = new BigDecimal("0.1");
BigDecimal fromDouble = new BigDecimal(0.1);
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);

System.out.println(exact);        // 0.1
System.out.println(fromDouble);   // 0.10000000000000000555...
System.out.println(fromValueOf);  // 0.1
```

- `new BigDecimal("0.1")` giữ đúng giá trị thập phân mà chuỗi thể hiện: phù hợp khi đầu vào là số tiền từ biểu mẫu, file hoặc nguồn văn bản đã kiểm tra.
- `new BigDecimal(0.1)` chuyển **giá trị nhị phân thực sự của `double`** sang thập phân; nó làm lộ sai số biểu diễn.
- `BigDecimal.valueOf(0.1)` dùng biểu diễn chuỗi thập phân chuẩn của `double` nên trong trường hợp này trả về `0.1`. Tuy nhiên, hàm này **không thể lấy lại chữ số đã mất** nếu giá trị `double` trước đó đã trải qua các phép toán hoặc bị làm tròn.

Khi dữ liệu gốc là decimal, hãy parse trực tiếp từ chuỗi đã xác thực hoặc nhận `BigDecimal` từ JDBC. Tránh đường đi `String → double → BigDecimal`.

## 5. Scale, làm tròn và so sánh

### Phép chia có thể cần làm tròn

`BigDecimal` tính chính xác những phép toán có kết quả thập phân hữu hạn trong khả năng biểu diễn, nhưng `1 / 3` có vô hạn chữ số thập phân. Vì vậy, phép chia không quy định độ chính xác hoặc cách làm tròn có thể ném `ArithmeticException`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal total = new BigDecimal("10.00");
BigDecimal pieces = new BigDecimal("3");

// total.divide(pieces); // ArithmeticException: non-terminating decimal
BigDecimal each = total.divide(pieces, 2, RoundingMode.HALF_EVEN);
System.out.println(each); // 3.33
```

`RoundingMode.HALF_EVEN` làm tròn về chữ số chẵn ở tình huống đúng giữa hai mức; `HALF_UP` làm tròn các trường hợp đúng giữa theo hướng tăng độ lớn. Không có một quy tắc làm tròn đúng cho mọi hệ thống: phải dùng **quy tắc mà nghiệp vụ, hợp đồng hoặc pháp luật yêu cầu**. Nên tính với độ chính xác cần thiết và làm tròn tại bước đã định, thay vì làm tròn tùy ý ở nhiều lớp.

```java
BigDecimal price = new BigDecimal("19.995");
BigDecimal rounded = price.setScale(2, RoundingMode.HALF_UP);
System.out.println(rounded); // 20.00

// Báo lỗi nếu đầu vào không đúng scale, thay vì tự làm tròn.
// price.setScale(2, RoundingMode.UNNECESSARY);
```

### `equals` khác `compareTo`

`BigDecimal.equals` xét **cả giá trị và scale**, trong khi `compareTo` so sánh giá trị số học:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.equals(y));        // false
System.out.println(x.compareTo(y) == 0); // true
```

Khi kiểm tra số tiền hai bên có bằng nhau không, thường cần `compareTo(...) == 0`. Khi dùng `BigDecimal` làm khóa trong `HashMap` hoặc phần tử của `HashSet`, lưu ý `equals` và `hashCode` chịu ảnh hưởng bởi `scale`; nên chuẩn hóa `scale` theo quy ước của miền dữ liệu nếu muốn các giá trị như `2.0` và `2.00` được xem là cùng một khóa.

## 6. Những lỗi dễ gặp trong ứng dụng JDBC

| Tình huống | Hậu quả có thể gặp | Cách xử lý |
| --- | --- | --- |
| Dùng `double` cho số tiền, rồi `setDouble` vào `DECIMAL` | Đưa sai số nhị phân vào luồng tiền; driver hoặc DB có thể chuyển đổi/làm tròn | Giữ `BigDecimal` từ lúc nhận dữ liệu đến khi ghi DB |
| Đọc `DECIMAL` bằng `getDouble` | Mất độ chính xác khi số có nhiều chữ số hoặc phần lẻ | Dùng `getBigDecimal` |
| Đặt `DECIMAL(p,s)` quá nhỏ | Không lưu được số lớn hoặc số có quá nhiều chữ số sau dấu thập phân | Chọn `p,s` từ giới hạn nghiệp vụ; thử các giá trị biên |
| Gọi `divide` mà không xử lý kết quả vô hạn | Có thể gặp `ArithmeticException` | Chọn `scale`/`MathContext` và `RoundingMode` được nghiệp vụ phê duyệt |
| Dùng `BigDecimal.equals` để so giá trị bất kể scale | `2.0` bị xem là khác `2.00` | Dùng `compareTo` khi so sánh giá trị số học |
| Đọc cột nullable bằng `getDouble` nhưng không gọi `wasNull` | Nhầm SQL `NULL` thành `0.0` | Kiểm tra `wasNull` ngay sau getter |
| Đưa `NaN` hoặc vô cực vào cột dấu phẩy động | Hành vi hỗ trợ khác nhau giữa các DB/driver | Xác thực với `Double.isFinite` khi miền dữ liệu yêu cầu số hữu hạn |

Ngoài ra, khi tính tổng trong SQL, chẳng hạn `SELECT SUM(amount)`, hãy kiểm tra kiểu và phạm vi của kết quả theo DB/driver, sau đó đọc bằng `getBigDecimal` nếu kết quả thuộc miền thập phân chính xác. Tránh chuyển tổng tiền qua `double` để tiện tính toán hoặc trình bày. Việc định dạng hai chữ số trên giao diện **không thể sửa lại giá trị đã bị mất độ chính xác**.

## 7. Tình huống thực hành

Giả sử một dịch vụ JDBC cần lưu hai thông tin:

1. **Đơn hàng** có `unit_price = 19.90`, `quantity = 3` và mức thuế `7.50%`.
2. **Cảm biến** gửi nhiệt độ `23.7°C`, dùng để vẽ biểu đồ theo thời gian.

Đối với đơn hàng, có thể dùng cột `DECIMAL(12,2)` cho giá và `DECIMAL(7,4)` cho tỷ lệ thuế dưới dạng `0.0750`. Ở Java:

```java
BigDecimal unitPrice = new BigDecimal("19.90");
BigDecimal quantity = new BigDecimal("3");
BigDecimal taxRate = new BigDecimal("0.0750");

BigDecimal subtotal = unitPrice.multiply(quantity);    // 59.70
BigDecimal tax = subtotal.multiply(taxRate)
        .setScale(2, RoundingMode.HALF_UP);            // 4.48
BigDecimal payable = subtotal.add(tax);               // 64.18
```

`HALF_UP` ở đây **chỉ là quy tắc minh họa**; hệ thống thực tế phải áp dụng quy tắc làm tròn thuế của nghiệp vụ và địa phương. Đối với nhiệt độ, `double` cùng kiểu SQL dấu phẩy động có thể phù hợp nếu yêu cầu chỉ là lưu/hiển thị số đo trong sai số thiết bị cho phép.

Tự kiểm tra trước khi viết repository:

- Cột dữ liệu đang thể hiện **đại lượng phải chính xác theo chữ số thập phân** hay **đại lượng đo xấp xỉ**?
- `precision` và `scale` của cột đã đủ cho giá trị lớn nhất, số lẻ và trung gian tính toán chưa?
- Từ nguồn dữ liệu đến `PreparedStatement`, từ `ResultSet` đến tính toán, có bước nào chuyển nhầm `BigDecimal` sang `double` không?
- Quy tắc làm tròn được áp dụng tại đâu, có rõ ràng và nhất quán không?
- Cột có thể chứa SQL `NULL` không, và code đã phân biệt `NULL` với số không chưa?

**Ghi nhớ:** Với JDBC, chọn kiểu số là một quyết định xuyên suốt từ nghiệp vụ → SQL → Java → phép tính → dữ liệu trả về. Dùng `BigDecimal` với `DECIMAL`/`NUMERIC` cho các giá trị thập phân cần chính xác; dùng `float`/`double` với kiểu SQL dấu phẩy động khi sai số nhị phân được chấp nhận và có kiểm soát.
