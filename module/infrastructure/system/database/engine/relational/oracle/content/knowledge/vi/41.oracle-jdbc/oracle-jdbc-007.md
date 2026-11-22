# Ánh xạ NUMBER sang BigDecimal và kiểm soát độ chính xác trong Oracle JDBC

## 1. Vì sao cần kiểm soát kiểu số giữa Oracle và Java?

Oracle Database thường dùng kiểu `NUMBER` để lưu số nguyên, số thập phân, số tiền, tỷ lệ, số lượng và nhiều giá trị nghiệp vụ khác. Trong Java, kiểu tương ứng phù hợp nhất cho `NUMBER` là `java.math.BigDecimal`, vì cả hai đều biểu diễn số thập phân theo cơ chế decimal thay vì số dấu phẩy động nhị phân như `double`.

Nếu ứng dụng đọc `NUMBER` bằng `double`, tính toán bằng `double` rồi ghi ngược lại database, có thể phát sinh sai số làm tròn. Với số tiền hoặc số liệu tài chính, sai khác rất nhỏ cũng có thể gây lệch đối soát, tổng tiền hoặc báo cáo.

Bài học này thuộc module **Database Engine Relational Oracle**, chương **Oracle JDBC**, tập trung vào **ánh xạ NUMBER sang BigDecimal và kiểm soát độ chính xác**. Các mục tiêu chính:

- Hiểu precision và scale của Oracle `NUMBER(p,s)`.
- Dùng `ResultSet.getBigDecimal()` và `PreparedStatement.setBigDecimal()` đúng cách.
- Tránh chuyển đổi qua `double`/`float` làm mất độ chính xác.
- Quy định rõ cách làm tròn, scale, overflow và null.
- Kiểm tra metadata, validate đầu vào và thiết kế API.
- Viết kiểm thử tích hợp để phát hiện lỗi số học giữa Java và Oracle.

Nguyên tắc cốt lõi: giữ dữ liệu ở dạng decimal xuyên suốt đường đi từ input, Java, JDBC đến Oracle; chỉ chuyển sang kiểu gần đúng khi nghiệp vụ thực sự chấp nhận sai số.

## 2. Oracle NUMBER biểu diễn số như thế nào?

`NUMBER` là kiểu số decimal của Oracle. Nó có thể biểu diễn số nguyên và số thập phân với độ chính xác thập phân cao. Dạng khai báo thường gặp:

```sql
NUMBER
NUMBER(p)
NUMBER(p, s)
```

Trong đó:
- `p` là precision: tổng số chữ số có nghĩa được cho phép.
- `s` là scale: số chữ số ở bên phải dấu thập phân; scale âm có nghĩa làm tròn về bên trái dấu thập phân.

Oracle `NUMBER` hỗ trợ tối đa 38 chữ số có nghĩa. Với khai báo `NUMBER(p,s)`, precision `p` thường nằm trong khoảng 1 đến 38; scale `s` có miền từ -84 đến 127. Các giá trị này là giới hạn của kiểu Oracle, không phải giới hạn của `BigDecimal`.

### 2.1. Precision và scale

Ví dụ:

```sql
CREATE TABLE invoice_line (
    line_id NUMBER(12,0),
    quantity NUMBER(10,3),
    unit_price NUMBER(12,2),
    tax_rate NUMBER(7,6),
    adjustment NUMBER(8,-2)
);
```

| Khai báo | Ý nghĩa | Ví dụ giá trị phù hợp |
|---|---|---|
| `NUMBER(12,0)` | Tối đa 12 chữ số, không có phần thập phân | `123456789012` |
| `NUMBER(10,3)` | Tổng 10 chữ số, 3 chữ số thập phân | `1234567.125` |
| `NUMBER(12,2)` | Tổng 12 chữ số, 2 chữ số thập phân | `1234567890.12` |
| `NUMBER(7,6)` | Tổng 7 chữ số, 6 chữ số thập phân | `0.123456` |
| `NUMBER(8,-2)` | Làm tròn đến hàng trăm, tối đa 8 chữ số có nghĩa | `12345600` |

Với `NUMBER(12,2)`, phần nguyên có tối đa 10 chữ số và phần thập phân có 2 chữ số. Giá trị vượt quá precision khai báo có thể gặp lỗi `ORA-01438`.

### 2.2. Scale âm

Scale âm không phải là “số chữ số sau dấu thập phân”. Ví dụ:

```sql
amount_rounded NUMBER(6,-2)
```

Giá trị được lưu theo bội số của 100 sau khi áp dụng quy tắc scale của Oracle. Một giá trị như `12345` sẽ được làm tròn đến hàng trăm khi gán vào cột này. Vì vậy, scale âm cần được mô hình hóa rõ trong Java nếu ứng dụng cũng cần thể hiện cùng quy tắc.

### 2.3. NUMBER không khai báo precision/scale

Khai báo `NUMBER` không có `(p,s)` cho phép lưu phạm vi rộng hơn về precision/scale so với một cột có scale cố định, trong giới hạn của kiểu NUMBER. Điều này hữu ích khi dữ liệu có precision thay đổi, nhưng làm hợp đồng dữ liệu của ứng dụng kém rõ ràng hơn.

Với dữ liệu nghiệp vụ, nên khai báo precision/scale cụ thể khi quy tắc miền dữ liệu đã biết. Ví dụ tiền tệ, tỷ lệ, số lượng và chỉ số đo lường thường có quy tắc riêng.

### 2.4. NUMBER khác BINARY_FLOAT và BINARY_DOUBLE

Oracle còn có `BINARY_FLOAT` và `BINARY_DOUBLE`, là kiểu số dấu phẩy động nhị phân. Chúng phù hợp cho một số phép tính khoa học hoặc kỹ thuật cần floating point, nhưng không có cùng semantics decimal với `NUMBER`.

| Oracle type | Kiểu Java thường dùng | Đặc tính |
|---|---|---|
| `NUMBER` | `BigDecimal` | Decimal, phù hợp dữ liệu chính xác |
| `BINARY_FLOAT` | `float` | Floating point nhị phân 32-bit |
| `BINARY_DOUBLE` | `double` | Floating point nhị phân 64-bit |

Không nên đổi một cột `NUMBER` sang `double` chỉ vì thuận tiện cho code. Chọn kiểu Java theo semantics của dữ liệu.

## 3. BigDecimal trong Java

`BigDecimal` biểu diễn một số decimal bằng một số nguyên không dấu phẩy (unscaled value) cùng với scale. Về khái niệm:

\[
value = unscaledValue \times 10^{-scale}
\]

Ví dụ:

```java
BigDecimal a = new BigDecimal("123.45");
```

Giá trị có:
- Unscaled value: `12345`
- Scale: `2`
- Precision: `5`

Một số khác:

```java
BigDecimal b = new BigDecimal("1.2300");
```

`b` có scale 4 và precision 5. Hai giá trị `1.23` và `1.2300` bằng nhau về số học, nhưng có scale khác nhau.

### 3.1. BigDecimal là immutable

Các phép toán trả về một `BigDecimal` mới:

```java
BigDecimal amount = new BigDecimal("10.00");
amount.add(new BigDecimal("2.50"));

System.out.println(amount); // 10.00
```

Kết quả `12.50` bị bỏ qua vì `add()` không sửa object ban đầu. Cách đúng:

```java
amount = amount.add(new BigDecimal("2.50"));
```

Tính immutable giúp `BigDecimal` an toàn hơn khi truyền qua các lớp, nhưng lập trình viên phải luôn nhận giá trị trả về.

### 3.2. Precision không đồng nghĩa scale

```java
BigDecimal x = new BigDecimal("123.4500");

System.out.println(x.precision()); // 7
System.out.println(x.scale());     // 4
```

- `precision()` trả số chữ số trong unscaled value.
- `scale()` trả số chữ số bên phải dấu thập phân; scale có thể âm.

Đừng dùng `precision()` để suy ra số chữ số thập phân hoặc dùng `scale()` để suy ra tổng số chữ số.

### 3.3. equals() và compareTo()

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));        // false
System.out.println(x.compareTo(y) == 0); // true
```

`equals()` so sánh cả giá trị và scale. `compareTo()` so sánh giá trị số học.

Khi kiểm tra hai số tiền bằng nhau về mặt nghiệp vụ, thường dùng:

```java
if (x.compareTo(y) == 0) {
    // Cùng giá trị số học
}
```

Nếu hợp đồng yêu cầu scale cố định, hãy chuẩn hóa scale trước khi so sánh hoặc serialize.

## 4. Ánh xạ JDBC: NUMBER sang BigDecimal

Oracle JDBC driver ánh xạ Oracle `NUMBER` sang Java `java.math.BigDecimal` theo mapping số decimal chuẩn. JDBC cũng cung cấp các phương thức trực tiếp để lấy và bind `BigDecimal`.

### 4.1. Đọc bằng ResultSet.getBigDecimal()

```java
String sql = """
    SELECT invoice_id, total_amount
    FROM app.invoice
    WHERE invoice_id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, invoiceId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long id = resultSet.getLong("invoice_id");
            BigDecimal total = resultSet.getBigDecimal("total_amount");

            // total == null nếu cột SQL là NULL
        }
    }
}
```

`getBigDecimal()` là lựa chọn ưu tiên khi cột Oracle là `NUMBER` và ứng dụng cần giữ độ chính xác decimal.

### 4.2. Bind bằng PreparedStatement.setBigDecimal()

```java
String sql = """
    INSERT INTO app.invoice (invoice_id, total_amount)
    VALUES (?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, invoiceId);
    statement.setBigDecimal(2, new BigDecimal("1250.75"));

    statement.executeUpdate();
}
```

`setBigDecimal()` gửi giá trị decimal qua JDBC dưới dạng bind parameter. Không cần chuyển thành chuỗi SQL literal và tránh phụ thuộc vào dấu thập phân theo NLS của database session.

### 4.3. Không nối BigDecimal vào SQL string

Không nên:

```java
String sql = "INSERT INTO app.invoice(total_amount) VALUES ("
        + amount.toString() + ")";
statement.executeUpdate(sql);
```

Cách này:
- Bỏ qua lợi ích bind variable.
- Có thể làm SQL text thay đổi theo từng giá trị.
- Tăng parse overhead.
- Dễ phát sinh lỗi định dạng và SQL injection khi kết hợp với input khác.
- Khó kiểm soát NLS nếu chuyển số qua chuỗi.

Nên dùng placeholder `?` và `setBigDecimal()`.

### 4.4. getObject() và mapping

Với Oracle `NUMBER`, `ResultSet.getObject()` thường trả về `BigDecimal` theo mapping JDBC của driver. Tuy nhiên, code cần kiểu rõ ràng thì nên gọi `getBigDecimal()` trực tiếp:

```java
BigDecimal amount = resultSet.getBigDecimal("amount");
```

Không dựa vào việc ép kiểu `getObject()` nếu driver, kiểu cột hoặc lớp mapping có thể thay đổi. Với JDBC 4.2, typed `getObject(column, BigDecimal.class)` có thể dùng khi driver hỗ trợ, nhưng `getBigDecimal()` là API trực tiếp và dễ đọc.

### 4.5. Đọc và bind NULL

`getBigDecimal()` trả `null` khi SQL value là `NULL`. Không cần gọi `wasNull()` sau `getBigDecimal()` để phân biệt null.

Khi bind null, nên khai báo JDBC type rõ ràng:

```java
if (amount == null) {
    statement.setNull(2, java.sql.Types.NUMERIC);
} else {
    statement.setBigDecimal(2, amount);
}
```

Không thay null bằng `BigDecimal.ZERO` trừ khi nghiệp vụ định nghĩa rõ hai giá trị này tương đương. SQL NULL biểu thị không có/không biết giá trị; số 0 là một giá trị số thực.

## 5. Vì sao không dùng double cho Oracle NUMBER?

Java `double` dùng biểu diễn IEEE 754 binary floating point. Nhiều số thập phân hữu hạn không thể biểu diễn chính xác trong hệ nhị phân.

Ví dụ:

```java
double d = 0.1 + 0.2;
System.out.println(d); // thường hiển thị 0.30000000000000004
```

Trong khi decimal arithmetic:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
```

### 5.1. Lỗi từ new BigDecimal(double)

Tránh:

```java
BigDecimal amount = new BigDecimal(0.1);
```

Constructor nhận `double` sẽ chuyển biểu diễn nhị phân gần đúng hiện có thành decimal chính xác của giá trị nhị phân đó. Kết quả có thể là một chuỗi dài như `0.10000000000000000555...`.

Ưu tiên:

```java
BigDecimal amount = new BigDecimal("0.1");
```

Hoặc nếu dữ liệu đầu vào là số nguyên:

```java
BigDecimal count = BigDecimal.valueOf(123L);
```

`BigDecimal.valueOf(double)` dùng cách chuyển đổi qua chuỗi chuẩn của `Double`, thường tránh chuỗi dài như constructor `double`, nhưng nó không thể khôi phục độ chính xác đã mất nếu dữ liệu nguồn vốn đã bị làm tròn trong `double`. Với dữ liệu tiền tệ, tốt nhất nhận decimal dưới dạng chuỗi hoặc kiểu decimal từ đầu.

### 5.2. Sai số tích lũy

Nếu mỗi dòng hóa đơn được chuyển qua `double`, tổng hàng nghìn dòng có thể lệch so với tổng tính trong Oracle `NUMBER`. Sai số còn có thể xuất hiện khi:
- Chia tỷ lệ thuế.
- Phân bổ chiết khấu.
- Chuyển đổi ngoại tệ.
- Tính lãi suất.
- Tính trung bình và phân bổ chi phí.

Dùng `BigDecimal` xuyên suốt giúp quy tắc decimal được kiểm soát rõ ràng.

### 5.3. Khi nào double là phù hợp?

`double` có thể phù hợp cho:
- Mô phỏng khoa học.
- Đồ họa hoặc thuật toán xấp xỉ.
- Dữ liệu cảm biến chấp nhận sai số.
- Tính toán số học mà binary floating point là yêu cầu tự nhiên.

Không dùng `double` cho số tiền, số dư, thuế, tỷ giá hoặc giá trị cần đối soát chính xác nếu hệ thống lưu bằng Oracle `NUMBER`.

## 6. Kiểm soát scale trước khi ghi database

Một cột `NUMBER(12,2)` chỉ có hai chữ số thập phân. Java nên định nghĩa rõ ứng dụng sẽ:
- Từ chối giá trị có quá hai chữ số thập phân.
- Làm tròn theo quy tắc nghiệp vụ.
- Hay giữ nguyên và để Oracle áp dụng scale.

Không để hành vi này xảy ra ngẫu nhiên tại database mà không có hợp đồng.

### 6.1. Từ chối nếu cần làm tròn

Dùng `RoundingMode.UNNECESSARY` để yêu cầu không có phần thông tin nào bị làm tròn:

```java
BigDecimal normalized = amount.setScale(
    2,
    RoundingMode.UNNECESSARY
);
```

Nếu `amount` có phần lẻ vượt quá 2 chữ số và không thể biểu diễn chính xác ở scale 2, Java ném `ArithmeticException`.

Ví dụ:
- `12.3` thành `12.30` mà không mất thông tin.
- `12.345` bị từ chối.
- `12.340` có thể chuẩn hóa thành `12.34` vì các chữ số bỏ đi đều bằng 0.

### 6.2. Làm tròn theo quy tắc đã chọn

```java
BigDecimal normalized = amount.setScale(
    2,
    RoundingMode.HALF_UP
);
```

`HALF_UP` làm tròn gần nhất; trường hợp đúng giữa hai giá trị thì làm tròn xa zero. Đây là một quy tắc phổ biến, nhưng không phải quy tắc đúng cho mọi nghiệp vụ.

Các chế độ thường gặp:

| RoundingMode | Hành vi |
|---|---|
| `UP` | Làm tròn xa zero nếu cần bỏ chữ số |
| `DOWN` | Cắt về zero |
| `CEILING` | Làm tròn hướng dương vô cực |
| `FLOOR` | Làm tròn hướng âm vô cực |
| `HALF_UP` | Gần nhất; tie làm tròn xa zero |
| `HALF_DOWN` | Gần nhất; tie làm tròn về zero |
| `HALF_EVEN` | Gần nhất; tie về chữ số chẵn |
| `UNNECESSARY` | Không cho phép làm tròn |

### 6.3. Không mặc định mọi currency có 2 chữ số

Một số đồng tiền có 0, 2 hoặc 3 chữ số thập phân theo quy ước. Quy tắc làm tròn còn có thể phụ thuộc:
- Loại giao dịch.
- Quốc gia và quy định kế toán.
- Đơn vị tiền tệ.
- Cấp tính toán (line, invoice, settlement).
- Quy tắc thuế và thanh toán.

Không hard-code `setScale(2)` cho mọi giá trị tiền. Lấy currency scale từ domain/configuration được quản lý và áp dụng quy tắc phù hợp.

### 6.4. Làm tròn một lần ở ranh giới được định nghĩa

Ví dụ tính chiết khấu:
- Tính từng dòng rồi làm tròn từng dòng.
- Tính tổng trước rồi mới làm tròn.
- Làm tròn thuế theo từng dòng hoặc toàn hóa đơn.

Các cách này có thể cho kết quả khác nhau. Nghiệp vụ phải định nghĩa điểm làm tròn và áp dụng thống nhất giữa Java và SQL.

## 7. Kiểm soát precision và overflow

Với cột `NUMBER(p,s)`, cần kiểm tra cả scale lẫn precision trước khi bind.

Ví dụ:

```sql
CREATE TABLE app.payment (
    payment_id NUMBER(18,0) PRIMARY KEY,
    amount     NUMBER(12,2) NOT NULL
);
```

`amount` cho phép tối đa 10 chữ số phần nguyên và 2 chữ số thập phân.

### 7.1. Hàm chuẩn hóa và kiểm tra NUMBER(p,s)

Một helper đơn giản cho trường hợp muốn từ chối dữ liệu cần làm tròn:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class OracleNumberValidator {
    private OracleNumberValidator() {
    }

    public static BigDecimal requireNumber(
            BigDecimal value,
            int precision,
            int scale) {

        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }
        if (precision < 1 || precision > 38) {
            throw new IllegalArgumentException("precision must be 1..38");
        }
        if (scale < -84 || scale > 127) {
            throw new IllegalArgumentException("scale must be -84..127");
        }

        BigDecimal normalized =
                value.setScale(scale, RoundingMode.UNNECESSARY);

        if (normalized.precision() > precision) {
            throw new IllegalArgumentException(
                    "value exceeds NUMBER(" + precision + "," + scale + ")"
            );
        }

        return normalized;
    }
}
```

Đây là helper cho policy “không tự làm tròn”. Nếu nghiệp vụ cho phép làm tròn, hãy chuẩn hóa bằng rounding mode đã thống nhất trước khi kiểm tra precision.

### 7.2. Ví dụ

Với `NUMBER(12,2)`:

```java
BigDecimal a = OracleNumberValidator.requireNumber(
    new BigDecimal("1234567890.12"), 12, 2
); // Hợp lệ

BigDecimal b = OracleNumberValidator.requireNumber(
    new BigDecimal("12345678901.12"), 12, 2
); // Bị từ chối: precision vượt giới hạn

BigDecimal c = OracleNumberValidator.requireNumber(
    new BigDecimal("12.345"), 12, 2
); // Bị từ chối: cần làm tròn
```

### 7.3. Tại sao kiểm tra precision sau setScale?

`NUMBER(p,s)` định nghĩa scale lưu trữ. Khi scale đã được chuẩn hóa, `precision()` của BigDecimal phản ánh số chữ số có nghĩa trong biểu diễn đã chuẩn hóa. So sánh với `p` giúp phát hiện overflow.

Với scale âm, `setScale(-2, ...)` làm tròn/chuẩn hóa về bội số 100 trước khi kiểm tra precision. Chỉ dùng nếu nghiệp vụ thật sự yêu cầu scale âm.

### 7.4. Database vẫn là lớp bảo vệ cuối

Validation ở Java cải thiện thông báo lỗi và tránh round trip không cần thiết. Database vẫn cần:
- Kiểu cột `NUMBER(p,s)` đúng.
- `NOT NULL` nếu bắt buộc.
- `CHECK` constraint cho miền giá trị.
- Unique/foreign key nếu có quy tắc liên quan.

Không bỏ constraint database chỉ vì ứng dụng đã validate. Có thể có batch, job hoặc ứng dụng khác ghi vào cùng bảng.

## 8. Rounding trong Java và Oracle

Oracle có thể làm tròn giá trị khi gán vào cột `NUMBER(p,s)` có scale cố định. Ví dụ giá trị có nhiều chữ số thập phân khi lưu vào `NUMBER(8,2)` có thể được làm tròn về hai chữ số thập phân; nếu sau đó precision vượt giới hạn thì có thể nhận `ORA-01438`.

Để tránh Java và Oracle làm tròn khác nhau:
1. Chọn rounding mode nghiệp vụ.
2. Chuẩn hóa `BigDecimal` trước khi bind.
3. Bind bằng `setBigDecimal()`.
4. Giữ DDL cột đúng precision/scale.
5. Kiểm thử các trường hợp tie, số âm và overflow.

### 8.1. Ví dụ ROUND

```java
BigDecimal price = new BigDecimal("10.125");

BigDecimal halfUp = price.setScale(2, RoundingMode.HALF_UP);
BigDecimal halfEven = price.setScale(2, RoundingMode.HALF_EVEN);

System.out.println(halfUp);   // 10.13
System.out.println(halfEven); // 10.12
```

Kết quả khác nhau vì tie-breaking rule khác nhau. Không chọn rounding mode chỉ dựa trên một ví dụ dương; phải kiểm tra cả giá trị âm.

### 8.2. ROUND ở SQL

Oracle có hàm `ROUND(number, integer)`:

```sql
SELECT ROUND(10.125, 2)
FROM dual;
```

Nếu Java tính một phần và SQL tính phần khác, phải xác định hệ thống nào là nguồn quy tắc làm tròn. Tránh làm tròn ở cả hai tầng với hai policy khác nhau.

### 8.3. RoundingMode.HALF_EVEN

`HALF_EVEN` làm tròn trường hợp tie về chữ số cuối cùng chẵn. Nó có thể giảm thiên lệch tích lũy trong một số loại phép tính, nhưng chỉ dùng khi quy định nghiệp vụ/kế toán cho phép.

### 8.4. RoundingMode.DOWN không phải FLOOR

`DOWN` làm tròn về zero:
- `1.239` scale 2 thành `1.23`.
- `-1.239` scale 2 thành `-1.23`.

`FLOOR` làm tròn về âm vô cực:
- `1.239` scale 2 thành `1.23`.
- `-1.239` scale 2 thành `-1.24`.

Nhầm hai chế độ có thể gây sai lệch khi xử lý số âm.

## 9. Phép toán BigDecimal và MathContext

`BigDecimal` hỗ trợ cộng, trừ, nhân, chia và phần dư. Mỗi phép toán cần xét scale và rounding.

### 9.1. Cộng và trừ

```java
BigDecimal subtotal = new BigDecimal("125.50");
BigDecimal discount = new BigDecimal("10.25");

BigDecimal total = subtotal.subtract(discount); // 115.25
```

Kết quả scale thường dựa trên scale của hai toán hạng. Chuẩn hóa ở ranh giới nghiệp vụ nếu cần scale cố định.

### 9.2. Nhân

```java
BigDecimal unitPrice = new BigDecimal("12.50");
BigDecimal quantity = new BigDecimal("3.000");

BigDecimal lineTotal = unitPrice.multiply(quantity); // 37.50000
```

Phép nhân có thể tạo scale bằng tổng scale của hai toán hạng. Nếu cột đích là `NUMBER(12,2)`, hãy áp dụng quy tắc làm tròn/validate trước khi lưu.

### 9.3. Chia

Chia decimal có thể tạo kết quả vô hạn tuần hoàn:

```java
BigDecimal result = new BigDecimal("10")
        .divide(new BigDecimal("3"));
```

Lệnh này ném `ArithmeticException` vì kết quả không có biểu diễn decimal hữu hạn chính xác.

Chỉ rõ scale và rounding:

```java
BigDecimal result = new BigDecimal("10")
        .divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);
// 3.3333
```

Hoặc dùng `MathContext` khi nghiệp vụ định nghĩa precision theo số chữ số có nghĩa:

```java
MathContext mc = new MathContext(12, RoundingMode.HALF_EVEN);

BigDecimal result = new BigDecimal("10")
        .divide(new BigDecimal("3"), mc);
```

### 9.4. MathContext khác scale

`MathContext(12, ...)` giới hạn precision còn 12 chữ số có nghĩa. `setScale(2, ...)` yêu cầu 2 chữ số bên phải dấu thập phân. Hai khái niệm không thay thế nhau.

### 9.5. Chia tiền và phân bổ phần dư

Khi chia tổng tiền cho nhiều người hoặc nhiều dòng, tổng các phần sau làm tròn có thể không bằng tổng ban đầu. Cần quy tắc phân bổ phần dư, ví dụ:
- Chia theo tỷ trọng.
- Làm tròn từng phần.
- Tính phần dư còn lại.
- Phân bổ phần dư theo quy tắc xác định để tổng cuối bằng tổng nguồn.

Không bỏ qua phần dư vì sai lệch có thể tích lũy giữa các báo cáo.

## 10. Đọc và ghi NUMBER với JDBC trong ứng dụng thực tế

### 10.1. Repository method đọc một giá trị

```java
public BigDecimal findInvoiceTotal(
        DataSource dataSource,
        long invoiceId) throws SQLException {

    String sql = """
        SELECT total_amount
        FROM app.invoice
        WHERE invoice_id = ?
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, invoiceId);

        try (ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                return null; // Hoặc Optional theo API repository
            }

            return resultSet.getBigDecimal("total_amount");
        }
    }
}
```

Trong code production, nên phân biệt “không có row” với “row có amount NULL”. Nếu cả hai tình huống có ý nghĩa khác nhau, dùng một kiểu kết quả rõ ràng thay vì cùng trả null.

### 10.2. Repository method ghi giá trị

```java
public int updateInvoiceTotal(
        DataSource dataSource,
        long invoiceId,
        BigDecimal total) throws SQLException {

    String sql = """
        UPDATE app.invoice
        SET total_amount = ?
        WHERE invoice_id = ?
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        if (total == null) {
            statement.setNull(1, Types.NUMERIC);
        } else {
            BigDecimal normalized =
                    OracleNumberValidator.requireNumber(total, 12, 2);
            statement.setBigDecimal(1, normalized);
        }

        statement.setLong(2, invoiceId);
        return statement.executeUpdate();
    }
}
```

Ví dụ giả định cột `TOTAL_AMOUNT` là `NUMBER(12,2)`. Với cột nullable, null được bind như SQL NULL; nếu cột `NOT NULL`, database sẽ từ chối và ứng dụng nên validate sớm.

### 10.3. Batch insert

```java
String sql = """
    INSERT INTO app.invoice_line (invoice_id, line_no, amount)
    VALUES (?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    connection.setAutoCommit(false);

    for (InvoiceLine line : lines) {
        statement.setLong(1, line.invoiceId());
        statement.setInt(2, line.lineNo());

        BigDecimal amount = OracleNumberValidator.requireNumber(
                line.amount(), 12, 2);

        statement.setBigDecimal(3, amount);
        statement.addBatch();
    }

    int[] counts = statement.executeBatch();
    connection.commit();
}
```

Production code cần xử lý exception bằng rollback và đóng tài nguyên đúng cách. Không bỏ qua `BatchUpdateException`; một batch có thể có kết quả từng phần tùy driver/database, nên phải hiểu transaction boundary và commit policy.

### 10.4. CallableStatement và OUT NUMBER

Stored procedure có thể trả về `NUMBER`:

```sql
CREATE OR REPLACE PROCEDURE app.get_invoice_total (
    p_invoice_id IN NUMBER,
    p_total OUT NUMBER
) AS
BEGIN
    SELECT total_amount
    INTO p_total
    FROM app.invoice
    WHERE invoice_id = p_invoice_id;
END;
/
```

Java:

```java
try (Connection connection = dataSource.getConnection();
     CallableStatement call = connection.prepareCall(
             "{ call app.get_invoice_total(?, ?) }")) {

    call.setLong(1, invoiceId);
    call.registerOutParameter(2, Types.NUMERIC);
    call.execute();

    BigDecimal total = call.getBigDecimal(2);
}
```

Dùng `getBigDecimal()` cho OUT parameter `NUMBER` để giữ decimal. Nếu procedure có thể trả NULL, kết quả Java cũng có thể là null.

## 11. Dùng metadata để hiểu precision và scale của cột

Khi xây dựng generic mapper hoặc schema validation, JDBC metadata có thể cung cấp precision và scale.

### 11.1. ResultSetMetaData

```java
try (PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT amount FROM app.invoice_line WHERE 1 = 0");
     ResultSet resultSet = statement.executeQuery()) {

    ResultSetMetaData metadata = resultSet.getMetaData();

    int precision = metadata.getPrecision(1);
    int scale = metadata.getScale(1);
    int jdbcType = metadata.getColumnType(1);
    String typeName = metadata.getColumnTypeName(1);
}
```

Metadata giúp mapper biết cột có kiểu gì, precision/scale được driver báo ra sao. Giá trị metadata cụ thể có thể khác theo kiểu khai báo, driver version và trường hợp `NUMBER` không khai báo `(p,s)`.

### 11.2. DatabaseMetaData.getColumns()

Có thể lấy metadata của table:

```java
DatabaseMetaData dbmd = connection.getMetaData();

try (ResultSet columns = dbmd.getColumns(
        connection.getCatalog(),
        "APP",
        "INVOICE_LINE",
        "AMOUNT")) {

    while (columns.next()) {
        String columnName = columns.getString("COLUMN_NAME");
        int dataType = columns.getInt("DATA_TYPE");
        int precision = columns.getInt("COLUMN_SIZE");
        int scale = columns.getInt("DECIMAL_DIGITS");
    }
}
```

Tên schema/table thường cần viết hoa khi tra metadata Oracle nếu object được tạo bằng identifier không đặt trong dấu ngoặc kép. Nếu dùng quoted identifier, cần truyền đúng tên phân biệt hoa thường.

### 11.3. Metadata không thay thế schema contract

Không nên chỉ dựa vào metadata lúc runtime để quyết định quy tắc tiền tệ hoặc làm tròn. Schema contract và domain model phải quy định rõ ý nghĩa số. Metadata hỗ trợ kiểm tra và mapping, không thay thế quyết định nghiệp vụ.

## 12. Ánh xạ NUMBER sang kiểu Java khác khi nào?

Không phải mọi `NUMBER` đều cần giữ thành `BigDecimal` trong mọi lớp. Nhưng cần chuyển đổi có kiểm soát và chỉ khi miền giá trị phù hợp.

| Oracle column | Java type cân nhắc | Điều kiện |
|---|---|---|
| `NUMBER(5,0)` | `Integer` hoặc `BigDecimal` | Giá trị nằm trong miền int và không có phần lẻ |
| `NUMBER(18,0)` | `Long` hoặc `BigDecimal` | Giá trị nằm trong miền long |
| `NUMBER(19,0)` | `BigDecimal`/`BigInteger` | Không phải mọi giá trị 19 chữ số đều vừa `long` |
| `NUMBER(p,s)` với `s > 0` | `BigDecimal` | Cần giữ phần thập phân chính xác |
| `NUMBER` không ràng buộc | `BigDecimal` | Precision/scale có thể thay đổi |
| `BINARY_FLOAT` | `Float` | Chấp nhận binary floating point |
| `BINARY_DOUBLE` | `Double` | Chấp nhận binary floating point |

### 12.1. Chuyển sang long một cách an toàn

```java
long id = decimalValue.longValueExact();
```

`longValueExact()` ném `ArithmeticException` nếu giá trị có phần lẻ hoặc vượt miền `long`.

Tránh:

```java
long id = decimalValue.longValue();
```

`longValue()` có thể bỏ phần lẻ và mất thông tin khi giá trị vượt miền kiểu đích.

### 12.2. Chuyển sang int một cách an toàn

```java
int count = decimalValue.intValueExact();
```

Dùng khi nghiệp vụ thật sự yêu cầu integer trong miền `int`. Đừng cast một `BigDecimal` tùy ý sang `int`.

### 12.3. BigInteger cho số nguyên rất lớn

Nếu cột là số nguyên và có thể vượt `long`, có thể dùng:

```java
BigInteger number = decimalValue.toBigIntegerExact();
```

Phương thức ném lỗi nếu số có phần thập phân khác 0. Với dữ liệu Oracle `NUMBER` có scale, vẫn cần kiểm tra quy tắc miền trước khi chuyển.

## 13. BigDecimal trong DTO và API

Giữ `BigDecimal` ở tầng domain/repository để tránh mất precision. Ở ranh giới API, cần định nghĩa cách serialize.

### 13.1. JSON number có thể mất precision ở consumer

Một số client JavaScript parse JSON number thành IEEE 754 `Number`. Số nguyên lớn hơn `2^53 - 1` không còn được biểu diễn chính xác. Số thập phân như tiền tệ cũng có thể trở thành binary floating point.

Vì vậy, API cần cân nhắc:
- Trả tiền/số decimal chính xác dưới dạng chuỗi decimal.
- Hoặc quy định rõ consumer phải dùng decimal library.
- Ghi rõ scale, currency và rounding rule.
- Không để frontend tự làm tròn theo locale.

Ví dụ JSON dạng chuỗi:

```json
{
  "amount": "12345678901234567890.12",
  "currency": "VND"
}
```

Định dạng chuỗi bảo toàn chữ số, nhưng API phải mô tả đây là decimal string và quy định dấu chấm thập phân, không dùng dấu phân tách hàng nghìn.

### 13.2. Không format locale trong payload máy đọc

Không gửi `"1.234,56"` hoặc `"1,234.56"` làm giá trị API trừ khi hợp đồng định nghĩa rõ locale. Dữ liệu máy đọc nên dùng một format invariant như `"1234.56"`.

Format hiển thị cho người dùng có thể được tạo ở UI theo locale; format lưu trữ/truyền tải nên độc lập locale.

### 13.3. DTO không nên dùng double nếu domain là decimal

```java
public record InvoiceResponse(
        String invoiceId,
        BigDecimal totalAmount,
        String currency
) {}
```

Nếu serializer hoặc client không bảo đảm decimal exact, có thể dùng `String totalAmount` trong contract. Quyết định này phải nhất quán với API consumer và versioning.

## 14. NLS và chuyển đổi số thành chuỗi

Oracle session có các tham số NLS ảnh hưởng cách parse/format số khi chuyển qua chuỗi trong SQL. Ví dụ dấu thập phân có thể khác theo `NLS_NUMERIC_CHARACTERS`.

JDBC bind `BigDecimal` tránh việc ứng dụng tự dựng chuỗi số trong SQL:

```java
statement.setBigDecimal(1, amount);
```

Không làm:

```java
String sql = "SELECT * FROM app.invoice WHERE total_amount = "
        + amount.toString();
```

Nếu thật sự cần chuyển số sang chuỗi ở SQL, hãy chỉ định format model và NLS parameter phù hợp:

```sql
SELECT TO_CHAR(
    total_amount,
    'FM9999999990D00',
    'NLS_NUMERIC_CHARACTERS = ''.,'''
)
FROM app.invoice;
```

Format model phải phù hợp precision/scale thực tế. Không dùng chuỗi format cố định quá ngắn cho mọi giá trị.

### 14.1. Locale trong Java

`DecimalFormat` phục vụ hiển thị theo locale, không nên dùng output của nó làm giá trị bind SQL hoặc payload decimal chuẩn. Ví dụ dấu phẩy thập phân trong locale có thể bị hiểu sai khi chuyển sang hệ thống khác.

Giữ `BigDecimal` trong domain, chỉ format khi hiển thị.

## 15. Ràng buộc dữ liệu ở Oracle

Validation Java giúp thông báo lỗi sớm, nhưng Oracle cần là lớp bảo vệ cuối để mọi client tuân thủ cùng quy tắc.

### 15.1. NUMBER(p,s) và NOT NULL

```sql
CREATE TABLE app.payment (
    payment_id NUMBER(18,0) PRIMARY KEY,
    amount NUMBER(12,2) NOT NULL,
    currency_code VARCHAR2(3) NOT NULL
);
```

`NUMBER(12,2)` giới hạn precision/scale. `NOT NULL` ngăn giá trị SQL NULL.

### 15.2. CHECK constraint

```sql
ALTER TABLE app.payment
ADD CONSTRAINT payment_amount_nonnegative_ck
CHECK (amount >= 0);
```

Constraint bảo vệ dữ liệu dù thao tác ghi đến từ JDBC, SQL*Plus, batch hoặc một ứng dụng khác.

### 15.3. Phân biệt NULL và zero

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(amount) AS non_null_amounts,
       SUM(amount) AS total_amount
FROM app.payment;
```

`COUNT(amount)` bỏ qua NULL; `SUM` cũng bỏ qua NULL và trả NULL nếu không có giá trị phù hợp. Không tự thay NULL bằng 0 nếu nghiệp vụ cần phân biệt “chưa biết” với “không có tiền”.

### 15.4. Ràng buộc miền số

Ngoài precision/scale, cần quy định:
- Giá trị âm có hợp lệ không.
- Tỷ lệ nằm trong khoảng nào.
- Số lượng có cho phép phân số không.
- Giá trị tối thiểu/tối đa.
- Có cho phép zero không.
- Có cần currency/unit đi kèm không.

Dùng CHECK constraint và domain validation phù hợp.

## 16. Lỗi thường gặp khi mapping số

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| `getDouble()` cho cột NUMBER tiền tệ | Sai số nhị phân | Dùng `getBigDecimal()` |
| `setDouble()` để ghi NUMBER | Có thể lưu giá trị gần đúng | Dùng `setBigDecimal()` |
| `new BigDecimal(0.1)` | Mang sai số của double vào decimal | Dùng chuỗi hoặc nguồn decimal |
| `BigDecimal.equals()` để so sánh số | Khác scale bị coi là khác | Dùng `compareTo()` khi so sánh số học |
| Quên nhận kết quả `add()`/`multiply()` | BigDecimal không thay đổi | Gán giá trị trả về |
| `divide()` không có rounding | ArithmeticException với số tuần hoàn | Chỉ định scale/rounding hoặc MathContext |
| `setScale()` không nêu rounding mode | Có thể lỗi hoặc policy không rõ | Chỉ định rõ RoundingMode |
| Dùng `DOWN` thay `FLOOR` | Số âm có kết quả khác | Chọn đúng hướng làm tròn |
| `longValue()` cho số bất kỳ | Mất phần lẻ hoặc overflow | Dùng `longValueExact()` |
| Nối số vào SQL | NLS/parse/security issue | Bind bằng PreparedStatement |
| Coi NULL là zero | Sai semantics nghiệp vụ | Giữ null hoặc xử lý rõ |
| Dùng scale 2 cho mọi currency | Sai quy tắc tiền tệ | Xác định scale theo currency/domain |
| Chỉ validate ở Java | Client khác có thể ghi dữ liệu sai | Dùng constraint ở database |
| Serialize BigDecimal thành JSON number không kiểm soát | Consumer có thể parse mất precision | Định nghĩa decimal string hoặc decimal-aware consumer |

## 17. Xử lý lỗi Oracle liên quan precision

### 17.1. ORA-01438

`ORA-01438: value larger than specified precision allowed for this column` xảy ra khi giá trị vượt precision của cột `NUMBER(p,s)` sau quy tắc scale.

Điều tra:
- Giá trị trước khi bind.
- `precision()` và `scale()` của BigDecimal.
- DDL cột.
- Có rounding trước khi ghi hay không.
- Giá trị được tính trong Java hay SQL.
- Có khác biệt giữa môi trường schema không.

Không khắc phục bằng cách âm thầm tăng precision nếu chưa đánh giá miền nghiệp vụ và tác động storage/API.

### 17.2. ORA-01426

`ORA-01426: numeric overflow` có thể xảy ra khi một phép toán số vượt phạm vi Oracle. Xem biểu thức, kiểu dữ liệu, intermediate result và phép cast.

### 17.3. ORA-06502

`ORA-06502: PL/SQL numeric or value error` có thể xuất hiện khi gán giá trị vào biến PL/SQL có precision/scale không đủ hoặc chuyển đổi không hợp lệ.

Kiểm tra khai báo biến PL/SQL, tham số procedure và cột đích.

### 17.4. Bắt SQLException

```java
try {
    statement.executeUpdate();
} catch (SQLException e) {
    int oracleCode = e.getErrorCode();
    String sqlState = e.getSQLState();

    // Ghi nhận mã lỗi và ngữ cảnh không nhạy cảm.
    // Không log toàn bộ payload hoặc credential.
    throw e;
}
```

Với Oracle JDBC, `getErrorCode()` cung cấp vendor error code. Không chỉ parse message text vì message có thể thay đổi theo ngôn ngữ/driver. Cũng cần xét exception chain và batch update exceptions.

## 18. Kiểm thử precision và scale

Kiểm thử bằng H2 hoặc mock có thể giúp kiểm tra logic Java, nhưng không thay thế integration test với đúng Oracle Database và Oracle JDBC driver. Semantics NUMBER, rounding, metadata và driver mapping cần được kiểm tra ở môi trường tương ứng.

### 18.1. Bộ giá trị kiểm thử

Với cột `NUMBER(12,2)`, nên thử:

| Input | Mục đích |
|---|---|
| `0` | Zero |
| `0.01` | Giá trị nhỏ nhất ở scale 2 |
| `-0.01` | Số âm |
| `9999999999.99` | Biên trên hợp lệ |
| `10000000000.00` | Vượt precision |
| `12.3` | Chuẩn hóa thêm zero |
| `12.340` | Có zero thừa |
| `12.345` | Cần rounding hoặc reject |
| `-12.345` | Rounding với số âm |
| SQL NULL | Null mapping |

### 18.2. Round-trip test

Round-trip test:
1. Tạo `BigDecimal` từ chuỗi decimal.
2. Bind vào cột NUMBER bằng `setBigDecimal`.
3. Commit.
4. Đọc lại bằng `getBigDecimal`.
5. So sánh giá trị theo quy tắc scale đã định.

Ví dụ:

```java
BigDecimal input = new BigDecimal("12345.67");

try (PreparedStatement insert = connection.prepareStatement(
        "INSERT INTO app.number_test(id, amount) VALUES (?, ?)")) {
    insert.setLong(1, 1L);
    insert.setBigDecimal(2, input);
    insert.executeUpdate();
}

try (PreparedStatement query = connection.prepareStatement(
        "SELECT amount FROM app.number_test WHERE id = ?")) {
    query.setLong(1, 1L);

    try (ResultSet rs = query.executeQuery()) {
        if (rs.next()) {
            BigDecimal actual = rs.getBigDecimal(1);
            if (actual.compareTo(input) != 0) {
                throw new AssertionError("Decimal round trip mismatch");
            }
        }
    }
}
```

Trong test thật, quản lý transaction/rollback và dữ liệu test độc lập để tránh va chạm khóa.

### 18.3. Test rounding boundary

Kiểm thử:
- Giá trị ngay dưới midpoint.
- Giá trị đúng midpoint.
- Giá trị ngay trên midpoint.
- Cùng ba trường hợp với số âm.
- Các rounding mode được nghiệp vụ cho phép.

Ví dụ với scale 2: `1.234`, `1.235`, `1.236`, và `-1.235`.

### 18.4. Test concurrency và batch

Với batch insert/update:
- Xác nhận mọi bind parameter giữ decimal.
- Kiểm tra `BatchUpdateException`.
- Xác nhận rollback khi một phần batch lỗi theo transaction policy.
- Đảm bảo retry không tạo bản ghi trùng.
- Kiểm tra dữ liệu đọc lại sau commit.

### 18.5. Test NLS

Chạy test với session có các `NLS_NUMERIC_CHARACTERS` khác nhau. Khi dùng `setBigDecimal`, kết quả số không nên phụ thuộc cách format dấu phẩy/dấu chấm ở client. Nếu ứng dụng tự dựng SQL literal từ chuỗi, test có thể phát hiện lỗi phụ thuộc NLS.

## 19. Checklist triển khai Oracle JDBC

### Schema
- DDL khai báo precision/scale phù hợp.
- Có `NOT NULL`/`CHECK` khi nghiệp vụ yêu cầu.
- Đã phân biệt `NUMBER`, `BINARY_FLOAT`, `BINARY_DOUBLE`.
- Metadata schema được kiểm tra giữa các môi trường.

### Java
- Dùng `BigDecimal` cho Oracle `NUMBER` cần chính xác.
- Không tạo `BigDecimal` từ `double` khi cần decimal exact.
- Phép toán giữ lại giá trị trả về vì BigDecimal immutable.
- Có rounding mode rõ ràng.
- Chia có scale/MathContext phù hợp.
- Chuyển sang primitive bằng exact conversion.
- Phân biệt NULL và zero.

### JDBC
- Dùng `getBigDecimal()` để đọc.
- Dùng `setBigDecimal()` để bind.
- Dùng `setNull(..., Types.NUMERIC)` cho null.
- Dùng PreparedStatement, không nối số vào SQL.
- Kiểm tra OUT parameter và batch mapping.
- Dùng driver version tương thích.

### API và kiểm thử
- Decimal serialization được định nghĩa rõ.
- Consumer không vô tình parse số chính xác thành double.
- Có round-trip integration test với Oracle.
- Có boundary, rounding, negative, null và NLS tests.
- Có kiểm thử lỗi precision/overflow.
- Có đối soát kết quả Java và SQL theo cùng quy tắc.

## 20. Bài thực hành tổng hợp

Bài lab dùng schema riêng và database Oracle có JDBC driver tương thích. Không chạy DDL trên schema nghiệp vụ.

### Bước 1. Tạo bảng thử nghiệm

```sql
CREATE TABLE app.number_precision_lab (
    id NUMBER(10,0) PRIMARY KEY,
    amount NUMBER(12,2),
    rate NUMBER(8,6),
    rounded_hundred NUMBER(8,-2)
);
```

### Bước 2. Chèn giá trị từ SQL để hiểu schema

```sql
INSERT INTO app.number_precision_lab
    (id, amount, rate, rounded_hundred)
VALUES
    (1, 12345.67, 0.123456, 12345);

COMMIT;
```

Đọc lại và quan sát scale lưu trữ:

```sql
SELECT id,
       amount,
       rate,
       rounded_hundred,
       DUMP(amount)
FROM app.number_precision_lab
WHERE id = 1;
```

### Bước 3. Viết JDBC insert

Dùng `PreparedStatement.setBigDecimal()` cho `amount`, `rate` và `rounded_hundred`. Tạo input bằng constructor chuỗi.

### Bước 4. Đọc bằng getBigDecimal

Đọc lại các cột và in:
- `toPlainString()`
- `precision()`
- `scale()`

Không dùng `double` để in hoặc so sánh giá trị.

### Bước 5. Thử giá trị cần rounding

Ghi `12.345` vào cột `NUMBER(12,2)`:
- Một lần validate bằng `UNNECESSARY` để xác nhận bị từ chối.
- Một lần chuẩn hóa bằng rounding mode đã chọn rồi bind.
- Đọc lại để so sánh với giá trị dự kiến.

### Bước 6. Thử overflow

Thử một giá trị có phần nguyên vượt giới hạn `NUMBER(12,2)`. Xác nhận Java validator phát hiện trước khi gửi SQL. Sau đó trong một test riêng, bỏ validator để quan sát lỗi database.

### Bước 7. Thử null

Bind SQL NULL bằng `setNull(..., Types.NUMERIC)`, đọc lại bằng `getBigDecimal()` và xác nhận kết quả Java là null.

### Bước 8. Kiểm tra metadata

Dùng `ResultSetMetaData` hoặc `DatabaseMetaData.getColumns()` để xem precision, scale và type name của từng cột. So sánh giữa driver version nếu ứng dụng hỗ trợ nhiều môi trường.

### Bước 9. Đối chiếu Java và Oracle

Tính một biểu thức trong Java bằng `BigDecimal`, tính cùng biểu thức trong SQL bằng `NUMBER`, sau đó so sánh. Xác định rõ điểm làm tròn ở mỗi phía.

### Bước 10. Dọn lab

Xóa bảng thử nghiệm chỉ khi chắc chắn không còn cần dữ liệu:

```sql
DROP TABLE app.number_precision_lab PURGE;
```

Không chạy lệnh dọn dẹp trên bảng nghiệp vụ.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Oracle `NUMBER` nên ánh xạ sang kiểu Java nào khi cần độ chính xác decimal?

**Trả lời:** `java.math.BigDecimal`.

**Câu 2.** Precision và scale khác nhau thế nào?

**Trả lời:** Precision là tổng số chữ số có nghĩa; scale là số chữ số bên phải dấu thập phân và có thể âm.

**Câu 3.** Vì sao không nên dùng `getDouble()` cho số tiền trong NUMBER?

**Trả lời:** `double` là binary floating point, không biểu diễn chính xác nhiều số thập phân và có thể tạo sai số khi tính toán.

**Câu 4.** Vì sao `new BigDecimal(0.1)` không được khuyến nghị?

**Trả lời:** Nó chuyển giá trị binary floating point gần đúng của `0.1` sang decimal, mang theo sai số nhị phân.

**Câu 5.** Dùng API nào để đọc NUMBER?

**Trả lời:** `ResultSet.getBigDecimal()`.

**Câu 6.** Dùng API nào để bind BigDecimal?

**Trả lời:** `PreparedStatement.setBigDecimal()`.

**Câu 7.** `BigDecimal.equals()` và `compareTo()` khác nhau thế nào?

**Trả lời:** `equals()` xét cả scale; `compareTo()` so sánh giá trị số học.

**Câu 8.** `setScale(2, UNNECESSARY)` có tác dụng gì?

**Trả lời:** Chuẩn hóa về scale 2 nhưng ném lỗi nếu phải làm tròn mất thông tin.

**Câu 9.** HALF_UP và HALF_EVEN khác nhau thế nào?

**Trả lời:** Khi đúng midpoint, HALF_UP làm tròn xa zero; HALF_EVEN chọn kết quả có chữ số cuối chẵn.

**Câu 10.** `MathContext` kiểm soát điều gì?

**Trả lời:** Precision theo số chữ số có nghĩa và rounding mode, không phải số chữ số thập phân cố định.

**Câu 11.** Vì sao phép chia BigDecimal có thể ném ArithmeticException?

**Trả lời:** Kết quả có thể là số thập phân vô hạn tuần hoàn, không thể biểu diễn chính xác nếu không chỉ định scale/rounding hoặc MathContext.

**Câu 12.** Làm thế nào chuyển BigDecimal sang long an toàn?

**Trả lời:** Dùng `longValueExact()` để phát hiện phần lẻ hoặc overflow.

**Câu 13.** Khi bind SQL NULL cho NUMBER nên làm gì?

**Trả lời:** Dùng `setNull(index, Types.NUMERIC)` và giữ semantics NULL riêng với zero.

**Câu 14.** Vì sao cần kiểm tra precision sau khi setScale?

**Trả lời:** Vì cột NUMBER(p,s) áp dụng scale trước khi giới hạn tổng số chữ số có nghĩa.

**Câu 15.** ORA-01438 thường chỉ ra điều gì?

**Trả lời:** Giá trị vượt precision được khai báo cho cột sau khi áp dụng scale.

**Câu 16.** Tại sao unique database constraint vẫn cần dù Java đã validate?

**Trả lời:** Nhiều client hoặc transaction có thể ghi đồng thời; database là nơi bảo vệ tính toàn vẹn cho mọi đường ghi.

**Câu 17.** JSON number có luôn bảo toàn BigDecimal không?

**Trả lời:** Không. Một số consumer, đặc biệt JavaScript Number, có thể chuyển sang binary floating point và mất precision; API có thể cần decimal string.

**Câu 18.** Test nào cần có cho mapping NUMBER?

**Trả lời:** Round-trip, boundary precision, scale, rounding midpoint, số âm, null, overflow, batch và NLS.

## 22. Kết luận

Oracle `NUMBER` là kiểu decimal có thể biểu diễn số chính xác trong giới hạn của database; Java `BigDecimal` là kiểu tương ứng phù hợp để đọc, tính toán và ghi những giá trị đó. Dùng `ResultSet.getBigDecimal()` và `PreparedStatement.setBigDecimal()` để giữ decimal xuyên suốt JDBC. Tránh chuyển qua `double` hoặc `float` khi dữ liệu cần đối soát chính xác, và không tạo `BigDecimal` từ một `double` đã chứa sai số.

Precision và scale phải được xem như một phần của hợp đồng dữ liệu. Với `NUMBER(p,s)`, hãy chuẩn hóa scale theo quy tắc nghiệp vụ, kiểm tra precision, chọn rounding mode rõ ràng và để constraint database bảo vệ mọi đường ghi. Phân biệt `equals()` với `compareTo()`, `MathContext` với scale, SQL NULL với zero, và chuyển sang primitive bằng exact conversion khi cần.

Một triển khai đáng tin cậy phải có round-trip integration test trên Oracle JDBC driver thật, gồm biên precision, scale, rounding, số âm, null, overflow và NLS. API cũng cần quy định cách serialize decimal để consumer không tự chuyển thành floating point. Khi Java và Oracle cùng áp dụng một quy tắc decimal rõ ràng, dữ liệu số mới giữ được tính nhất quán từ lúc nhập đến lúc lưu, đọc, tính toán và trao đổi giữa các hệ thống.

