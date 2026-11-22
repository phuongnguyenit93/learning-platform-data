# Quản lý precision, scale và quy tắc làm tròn trong JDBC

Khi ứng dụng Java làm việc với giá bán, số dư, thuế, tỷ lệ hoặc các đại lượng đo lường, câu hỏi không chỉ là “lưu được bao nhiêu chữ số?”. Cần xác định **bao nhiêu chữ số có nghĩa** (*precision*), **bao nhiêu chữ số sau dấu thập phân** (*scale*) và **khi nào, theo quy tắc nào được phép làm tròn**. Nếu ứng dụng và cơ sở dữ liệu hiểu khác nhau về ba điều này, một câu lệnh `INSERT` có thể bị từ chối, một số tiền có thể bị thay đổi ngoài ý muốn, hoặc tổng các dòng có thể lệch với tổng hóa đơn.

Trong JDBC, `PreparedStatement` và `ResultSet` giúp truyền và nhận các giá trị số chính xác qua driver; `BigDecimal` giúp Java thực hiện các phép tính thập phân có kiểm soát. Tuy nhiên, **JDBC không tự quyết định quy tắc làm tròn nghiệp vụ**. Ứng dụng cần thống nhất chính sách trước khi ghi dữ liệu và kiểm tra lại hành vi của hệ quản trị cơ sở dữ liệu đang dùng.

## 1. Phân biệt precision, scale và rounding

### Precision và scale trong cột SQL

Với một cột khai báo `DECIMAL(p, s)` hoặc `NUMERIC(p, s)` theo cách dùng phổ biến trong các hệ quản trị cơ sở dữ liệu quan hệ:

- **Precision (`p`)**: số chữ số thập phân tối đa của giá trị được biểu diễn.
- **Scale (`s`)**: số chữ số dành cho phần thập phân (bên phải dấu thập phân).
- Khi `0 <= s <= p`, phần nguyên có tối đa `p - s` chữ số.

Ví dụ:

```sql
CREATE TABLE product_price (
    product_id BIGINT PRIMARY KEY,
    amount     DECIMAL(12, 2) NOT NULL
);
```

`amount` có tối đa **12 chữ số**, trong đó **2 chữ số sau dấu thập phân** và **10 chữ số phần nguyên**. Giá trị dương lớn nhất theo giới hạn đó là `9999999999.99`; `10000000000.00` vượt phạm vi.

| Khai báo cột | Phần nguyên tối đa | Phần thập phân | Ví dụ phù hợp |
| --- | ---: | ---: | --- |
| `DECIMAL(12, 2)` | 10 chữ số | 2 chữ số | `1234567890.12` |
| `DECIMAL(8, 4)` | 4 chữ số | 4 chữ số | `1234.5678` |
| `DECIMAL(5, 0)` | 5 chữ số | 0 chữ số | `12345` |
| `DECIMAL(9, 6)` | 3 chữ số | 6 chữ số | `12.345678` |

Đây là giới hạn **khai báo của cột**, không phải phép đo số chữ số hiện có trong một đối tượng Java. Cú pháp, phạm vi `p`/`s`, khả năng hỗ trợ scale âm và cách xử lý giá trị vượt giới hạn phụ thuộc hệ quản trị cơ sở dữ liệu. Không mặc định mọi sản phẩm sẽ tự làm tròn hay báo lỗi giống nhau.

### Precision và scale của `BigDecimal`

Java biểu diễn một `BigDecimal` bằng một số nguyên *unscaled value* cùng một `scale`; về mặt toán học:

\[
\text{giá trị} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

`precision()` trả về số chữ số của *unscaled value* (bỏ dấu âm và các số không ở đầu); `scale()` là số mũ tỉ lệ của biểu diễn đó. Khi scale dương, nó tương ứng với số vị trí sau dấu thập phân; scale cũng có thể bằng **0 hoặc âm**.

```java
BigDecimal a = new BigDecimal("123.4500");
System.out.println(a.precision()); // 7
System.out.println(a.scale());     // 4

BigDecimal b = new BigDecimal("0.00120");
System.out.println(b.precision()); // 3
System.out.println(b.scale());     // 5

BigDecimal c = new BigDecimal("1000").stripTrailingZeros();
System.out.println(c);            // 1E+3
System.out.println(c.scale());    // -3
```

Điều đáng chú ý: `new BigDecimal("12.30")` và `new BigDecimal("12.3")` có **cùng giá trị toán học nhưng scale khác nhau**. `precision()` của `BigDecimal` cũng không cho biết một giá trị được phép lưu trong **cột nào** nếu chưa xét scale và precision khai báo của cột ấy.

### Rounding là một quyết định riêng

Giả sử cần ghi `12.345` vào `DECIMAL(12, 2)`. Có ít nhất ba hướng xử lý hợp lệ về mặt thiết kế:

1. **Từ chối** vì dữ liệu có phần thập phân không thể lưu chính xác tới hai vị trí.
2. **Làm tròn trước khi ghi** theo quy tắc nghiệp vụ được công bố, chẳng hạn `HALF_UP`.
3. **Thay đổi mô hình lưu trữ**, chẳng hạn dùng `DECIMAL(12, 3)` nếu chữ số thứ ba là dữ liệu có ý nghĩa cần giữ lại.

Không giao quyết định này ngầm cho driver hoặc cơ sở dữ liệu. Tùy hệ quản trị và cấu hình, giá trị có thể được làm tròn, bị từ chối hoặc dẫn tới lỗi vượt phạm vi; ứng dụng cần có quy tắc rõ ràng và kiểm thử bằng chính cơ sở dữ liệu sẽ triển khai.

## 2. Các chế độ làm tròn của Java

`BigDecimal.setScale(targetScale, roundingMode)` đặt số vị trí thập phân mong muốn. Nếu giảm scale làm mất chữ số có nghĩa, `RoundingMode` quy định xử lý phần bị loại bỏ.

| `RoundingMode` | Quy tắc | Ví dụ làm tròn đến 2 chữ số |
| --- | --- | --- |
| `HALF_UP` | Gần nhất; đúng giữa hai mức thì làm tròn ra xa 0 | `1.235 -> 1.24`, `-1.235 -> -1.24` |
| `HALF_EVEN` | Gần nhất; đúng giữa hai mức thì chọn chữ số cuối chẵn | `1.245 -> 1.24`, `1.255 -> 1.26` |
| `DOWN` | Bỏ phần dư, tiến về 0 | `-1.239 -> -1.23` |
| `UP` | Nếu có phần dư thì đi xa 0 | `-1.231 -> -1.24` |
| `FLOOR` | Làm tròn về âm vô cực | `-1.231 -> -1.24` |
| `CEILING` | Làm tròn về dương vô cực | `-1.231 -> -1.23` |
| `UNNECESSARY` | Cấm làm tròn: phát sinh `ArithmeticException` nếu phải bỏ chữ số khác 0 | `1.230 -> 1.23`; `1.235 -> lỗi` |

Hai chế độ `HALF_UP` và `HALF_EVEN` thường xuất hiện trong yêu cầu tài chính hoặc thống kê, nhưng **không có một chế độ đúng cho mọi nghiệp vụ**. `HALF_EVEN` có thể giảm thiên lệch khi có nhiều trường hợp đúng điểm giữa; điều này không thay thế quy định cụ thể về tính tiền, thuế hoặc phí. Với giá trị âm, `DOWN`, `FLOOR` và `CEILING` cho kết quả khác nhau; cần thử cả số âm trong bộ kiểm thử.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal value = new BigDecimal("1.245");

System.out.println(value.setScale(2, RoundingMode.HALF_UP));   // 1.25
System.out.println(value.setScale(2, RoundingMode.HALF_EVEN)); // 1.24
System.out.println(value.setScale(2, RoundingMode.DOWN));      // 1.24

System.out.println(new BigDecimal("12").setScale(2));         // 12.00
System.out.println(new BigDecimal("12.340").setScale(
        2, RoundingMode.UNNECESSARY));                         // 12.34
// new BigDecimal("12.345").setScale(2, RoundingMode.UNNECESSARY)
// -> ArithmeticException: Rounding necessary
```

**Phân biệt hai API dễ nhầm:** `setScale(2, ...)` quản lý **2 chữ số sau dấu thập phân**; `round(new MathContext(4, ...))` quản lý **4 chữ số có nghĩa** của phép tính hoặc kết quả. Chúng không tương đương:

```java
import java.math.MathContext;

BigDecimal x = new BigDecimal("123.456");

System.out.println(x.setScale(2, RoundingMode.HALF_EVEN));
// 123.46 (hai chữ số sau dấu thập phân)

System.out.println(x.round(new MathContext(4, RoundingMode.HALF_EVEN)));
// 123.5 (bốn chữ số có nghĩa)
```

`MathContext.DECIMAL64` cũng quy định **precision của phép tính**, không có nghĩa là dữ liệu sẽ phù hợp với cột `DECIMAL(16, 2)` hay sẽ tự giữ đúng hai chữ số thập phân.

## 3. Chọn kiểu và tính toán số thập phân an toàn

Với các giá trị cần biểu diễn thập phân chính xác, dùng `BigDecimal` xuyên suốt luồng **nhận dữ liệu → tính toán → chuẩn hóa → ghi JDBC → đọc JDBC**.

### Khởi tạo từ chuỗi hoặc số nguyên

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.085");
BigDecimal count = BigDecimal.valueOf(3);

BigDecimal tax = price.multiply(rate);
System.out.println(tax); // 1.69915, chưa làm tròn

BigDecimal taxToCharge = tax.setScale(2, RoundingMode.HALF_UP);
System.out.println(taxToCharge); // 1.70
```

Tránh `new BigDecimal(0.1)` vì đối số `double` đã mang sai số biểu diễn nhị phân. Nếu nguồn dữ liệu bắt buộc là `double`, `BigDecimal.valueOf(double)` thường phù hợp hơn hàm tạo từ `double` trực tiếp nhờ cách chuyển qua chuỗi thập phân; tốt hơn vẫn là nhận đầu vào chuẩn dưới dạng chuỗi hoặc `BigDecimal` để tránh mất chính xác từ sớm.

### Phép chia luôn cần chính sách precision/scale

Một phép chia thập phân có thể không có biểu diễn hữu hạn, như `1 / 3`. `BigDecimal.divide(divisor)` khi đó phát sinh `ArithmeticException`. Hãy chỉ rõ scale/rounding mode hoặc dùng `MathContext` thích hợp:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal share = one.divide(three, 2, RoundingMode.HALF_EVEN);
System.out.println(share); // 0.33

BigDecimal ratio = one.divide(
        three, new MathContext(10, RoundingMode.HALF_EVEN));
System.out.println(ratio); // 0.3333333333
```

Khi chia tiền cho nhiều người, mỗi phần làm tròn riêng có thể khiến tổng các phần lệch số ban đầu. Nghiệp vụ phải xác định cách phân bổ phần dư, ví dụ phân phối từng đơn vị tiền nhỏ nhất cho một số người, thay vì chỉ làm tròn độc lập rồi giả định tổng luôn bằng nhau.

### Không nhầm `equals` với so sánh giá trị

```java
BigDecimal first = new BigDecimal("1.0");
BigDecimal second = new BigDecimal("1.00");

System.out.println(first.equals(second));    // false: scale khác nhau
System.out.println(first.compareTo(second)); // 0: bằng nhau về giá trị
```

Khi cần so sánh giá trị số, dùng `compareTo`. Khi cần chuẩn hóa dữ liệu theo hợp đồng lưu trữ, dùng `setScale`. `stripTrailingZeros()` hữu ích cho hiển thị hoặc một số mục đích chuẩn hóa, nhưng có thể tạo **scale âm**; không dùng nó thay cho chính sách scale đã định nghĩa của cột.

## 4. Kiểm soát dữ liệu trước khi ghi qua JDBC

Giả sử bảng `product_price.amount` phải giữ **đúng giá trị** với `DECIMAL(12, 2)`: ứng dụng cho phép thêm số 0 ở phần thập phân (`12.340` → `12.34`), nhưng từ chối chữ số có nghĩa thứ ba (`12.345`). Ta có thể chuẩn hóa bằng `UNNECESSARY` và kiểm tra precision **sau khi đã đặt scale bằng 2**.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class PriceRepository {
    private static final int DB_PRECISION = 12;
    private static final int DB_SCALE = 2;

    private PriceRepository() {}

    public static BigDecimal normalizeAmount(BigDecimal input) {
        Objects.requireNonNull(input, "input");

        final BigDecimal amount;
        try {
            // Chỉ bỏ số 0 dư; không tự làm tròn số tiền.
            amount = input.setScale(DB_SCALE, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Số tiền phải biểu diễn chính xác với 2 chữ số thập phân", ex);
        }

        // Sau setScale(2), precision kiểm tra giới hạn DECIMAL(12, 2).
        if (amount.precision() > DB_PRECISION) {
            throw new IllegalArgumentException("Số tiền vượt DECIMAL(12, 2)");
        }
        return amount;
    }

    public static void updateAmount(
            DataSource dataSource, long productId, BigDecimal input)
            throws SQLException {
        BigDecimal amount = normalizeAmount(input);

        String sql = "UPDATE product_price SET amount = ? WHERE product_id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBigDecimal(1, amount);
            statement.setLong(2, productId);
            statement.executeUpdate();
        }
    }

    public static Optional<BigDecimal> findAmount(
            DataSource dataSource, long productId) throws SQLException {
        String sql = "SELECT amount FROM product_price WHERE product_id = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, productId);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return Optional.empty();
                }
                return Optional.of(result.getBigDecimal("amount"));
            }
        }
    }
}
```

Ví dụ giả định cột `amount` có ràng buộc `NOT NULL`; vì vậy `Optional.empty()` biểu thị **không tìm thấy hàng**, không phải giá trị SQL `NULL`. Với cột cho phép `NULL`, `ResultSet.getBigDecimal(...)` có thể trả về `null` và cần xử lý theo hợp đồng của ứng dụng.

Các điểm chính trong ví dụ:

- `setBigDecimal` và `getBigDecimal` là API JDBC phù hợp cho `DECIMAL`/`NUMERIC`, tránh chuyển qua `float` hoặc `double`.
- Dấu `?` trong `PreparedStatement` là tham số hóa SQL; giá trị và định dạng số được truyền qua driver, không ghép chuỗi bằng tay.
- `normalizeAmount` **từ chối việc làm tròn ngầm**. Nếu nghiệp vụ cho phép làm tròn, có thể thay `UNNECESSARY` bằng `HALF_UP`/`HALF_EVEN` theo quy tắc đã phê duyệt, nhưng vẫn phải kiểm tra giới hạn sau khi làm tròn.
- `amount.precision() <= 12` là cách kiểm tra hữu ích **sau khi scale đã được chuẩn hóa về 2** cho cột `DECIMAL(12, 2)`. Không áp dụng máy móc phép kiểm tra này cho mọi kiểu dữ liệu, kiểu dấu phẩy động hoặc các quy tắc scale đặc biệt của từng hệ cơ sở dữ liệu.
- `SQLException` vẫn cần được xử lý ở tầng gọi: lỗi mất kết nối, ràng buộc cơ sở dữ liệu hay khác biệt về định nghĩa cột không thể được loại bỏ chỉ nhờ kiểm tra `BigDecimal`.

Nếu bài toán yêu cầu làm tròn thuế hoặc phí, hãy tổ chức quy trình thành hai bước minh bạch:

```java
BigDecimal rawTax = new BigDecimal("19.99")
        .multiply(new BigDecimal("0.085")); // 1.69915

// Đây là ranh giới nghiệp vụ: ghi nhận thuế đến đơn vị 0.01.
BigDecimal roundedTax = rawTax.setScale(2, RoundingMode.HALF_UP);

// Đây là ranh giới lưu trữ: xác nhận số cuối cùng vừa khít cột.
BigDecimal persistableTax = PriceRepository.normalizeAmount(roundedTax);
```

**Chọn ranh giới làm tròn có chủ đích.** Chẳng hạn “làm tròn thuế mỗi dòng rồi cộng” và “cộng thuế chưa làm tròn của các dòng rồi mới làm tròn” không nhất thiết bằng nhau. Quy định nghiệp vụ phải xác định phương án nào là nguồn sự thật và lưu đủ dữ liệu đầu vào để có thể kiểm tra lại kết quả khi cần.

## 5. Đọc metadata precision/scale qua JDBC

JDBC cho phép kiểm tra metadata của các cột trong `ResultSet`:

```java
import java.sql.ResultSetMetaData;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT amount FROM product_price WHERE product_id = ?")) {
    statement.setLong(1, productId);

    try (ResultSet result = statement.executeQuery()) {
        ResultSetMetaData meta = result.getMetaData();
        int column = 1;
        System.out.println("SQL type: " + meta.getColumnTypeName(column));
        System.out.println("Precision: " + meta.getPrecision(column));
        System.out.println("Scale: " + meta.getScale(column));
    }
}
```

`getPrecision` và `getScale` cung cấp thông tin mà driver báo cho **cột trong kết quả truy vấn**. Với một cột `DECIMAL(12, 2)` trực tiếp, thường mong đợi precision `12` và scale `2`; các biểu thức tính toán, phép `CAST`, alias, view và những khác biệt driver có thể làm metadata thay đổi hoặc khó diễn giải. Để khảo sát khai báo cột bảng, `DatabaseMetaData.getColumns(...)` cung cấp các trường như `COLUMN_SIZE` và `DECIMAL_DIGITS`; tên schema/catalog, cách diễn giải thông tin và độ tin cậy vẫn phụ thuộc hệ quản trị.

**Không lấy metadata truy vấn làm chính sách nghiệp vụ tại thời điểm chạy.** Mô hình dữ liệu và quy tắc làm tròn cần được xác định trong thiết kế, đồng bộ với migration/DDL và kiểm tra qua integration test với driver thực tế. Metadata phù hợp để kiểm tra sự tương thích, chẩn đoán hoặc phát hiện cấu hình sai.

## 6. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `12.345` không lưu đúng vào `DECIMAL(12,2)` | Scale đầu vào vượt scale lưu trữ | Từ chối hoặc làm tròn theo nghiệp vụ trước `setBigDecimal` |
| `9999999999.995` bị lỗi sau khi làm tròn | Làm tròn có thể tạo ra `10000000000.00`, vượt 10 chữ số phần nguyên | Kiểm tra precision **sau** khi làm tròn |
| Giá trị `0.1` thành chuỗi thập phân rất dài | Tạo `BigDecimal` trực tiếp từ `double` | Dùng chuỗi thập phân hoặc `BigDecimal.valueOf` khi bắt buộc nhận `double` |
| Phép chia `1/3` ném `ArithmeticException` | Không chỉ định cách làm tròn cho kết quả vô hạn | Dùng `divide(divisor, scale, roundingMode)` hoặc `MathContext` |
| `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả `false` | `equals` còn so sánh scale | Dùng `compareTo(...) == 0` khi so sánh giá trị số |
| Tổng hóa đơn lệch một vài đơn vị nhỏ nhất | Làm tròn các bước ở vị trí không thống nhất | Quy định rõ làm tròn từng dòng, từng thuế, hay tại tổng cuối |
| Chạy đúng với một DB nhưng lệch ở DB khác | Quy tắc ép kiểu, giới hạn và làm tròn SQL khác nhau | Kiểm thử trên DB/driver đích, tránh dựa vào ép kiểu ngầm |

Một vài lựa chọn thiết kế cần thống nhất sớm:

1. **Định nghĩa đơn vị và độ phân giải của từng đại lượng.** Ví dụ giá bán hai chữ số thập phân, tỷ giá hoặc số đo có thể cần nhiều chữ số hơn. Không áp cùng một scale cho mọi loại dữ liệu.
2. **Tách độ chính xác tính toán khỏi độ chính xác lưu trữ.** Có thể giữ trung gian với precision cao hơn và chỉ lượng tử hóa ở bước nghiệp vụ xác định.
3. **Xác định rõ hành vi với dữ liệu quá scale hoặc quá precision.** Trả lỗi xác thực, yêu cầu điều chỉnh, hay làm tròn đều phải là quyết định có chủ đích.
4. **Giữ logic nhất quán giữa Java và SQL.** Phép `ROUND`, `CAST` hoặc biểu thức `amount * rate` ở DB có thể áp dụng quy tắc và suy diễn precision/scale riêng; nếu tính toán cả hai phía, kiểm thử cùng bộ giá trị biên.
5. **Bảo vệ tính nhất quán khi ghi nhiều bản ghi.** Với cập nhật tổng hợp, sử dụng transaction phù hợp; xác định quy tắc phân bổ phần dư để tổng các dòng vẫn khớp số tổng cuối cùng.

## 7. Bộ tình huống kiểm thử nên có

Với hợp đồng “`DECIMAL(12,2)`, không cho làm tròn khi ghi”, các tình huống dưới đây cần được kiểm thử ở cả lớp Java và integration test JDBC:

| Đầu vào | Kết quả mong đợi khi chuẩn hóa | Lý do |
| --- | --- | --- |
| `12` | `12.00` | Có thể thêm số 0 để đạt scale 2 |
| `12.340` | `12.34` | Loại bỏ số 0 dư không đổi giá trị |
| `12.345` | Từ chối | Phải bỏ chữ số `5` có nghĩa |
| `9999999999.99` | `9999999999.99` | Giá trị dương lớn nhất với `DECIMAL(12,2)` |
| `10000000000.00` | Từ chối | Có 11 chữ số phần nguyên |
| `-0.01` | `-0.01` | Giá trị âm không làm thay đổi quy tắc scale |
| `0.005` | Từ chối | Chữ số thứ ba có nghĩa; không tự chọn cách làm tròn |

Nếu nghiệp vụ sử dụng `HALF_UP` để lưu `DECIMAL(12,2)`, cần bổ sung kiểm thử: `1.235 -> 1.24`, `-1.235 -> -1.24`, `0.005 -> 0.01` và `9999999999.995` **bị từ chối sau khi làm tròn** vì vượt precision. Nếu sử dụng `HALF_EVEN`, bổ sung các điểm giữa có chữ số cuối chẵn/lẻ (`1.245 -> 1.24`, `1.255 -> 1.26`).

## 8. Tự kiểm tra hiểu biết

**Câu 1.** `DECIMAL(8,3)` cho phép tối đa bao nhiêu chữ số phần nguyên? `BigDecimal("12345.678")` có phù hợp không?

**Đáp án:** 5 chữ số phần nguyên; `12345.678` phù hợp với giới hạn này.

**Câu 2.** Tại sao `new BigDecimal("7.500").setScale(2, RoundingMode.UNNECESSARY)` thành công, còn `new BigDecimal("7.505").setScale(2, RoundingMode.UNNECESSARY)` thất bại?

**Đáp án:** Trường hợp đầu chỉ bỏ số 0 dư, không mất giá trị; trường hợp sau phải bỏ chữ số `5` có nghĩa.

**Câu 3.** Cột `DECIMAL(12,2)` nhận một số đã được làm tròn từ `9999999999.995` theo `HALF_UP` thì sao?

**Đáp án:** Kết quả là `10000000000.00`, lớn hơn giới hạn phần nguyên 10 chữ số. Phải phát hiện và từ chối **trước khi ghi**, không chỉ kiểm tra kích thước đầu vào.

**Câu 4.** Có nên dùng `ResultSet.getDouble("amount")` rồi tạo `BigDecimal` từ kết quả khi đọc tiền không?

**Đáp án:** Không nên. Dùng `ResultSet.getBigDecimal("amount")` để giữ biểu diễn thập phân chính xác và tránh đi vòng qua `double`.

**Ghi nhớ:** SQL `DECIMAL(p,s)` đặt giới hạn lưu trữ; `BigDecimal` cung cấp biểu diễn và phép tính thập phân; `RoundingMode` thể hiện quyết định làm tròn. Xác định quy tắc nghiệp vụ, chuẩn hóa và kiểm tra biên **trước** `PreparedStatement.setBigDecimal`, rồi xác nhận với cơ sở dữ liệu/driver thực tế.
