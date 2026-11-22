# Bảo toàn độ chính xác với BigDecimal

Khi ứng dụng Java làm việc với giá tiền, tỷ lệ, số lượng có phần thập phân hoặc dữ liệu cần đối soát, **đúng kiểu dữ liệu từ Java đến cơ sở dữ liệu** là điều kiện để kết quả không bị sai lệch. Trong JDBC, cặp thường dùng để lưu số thập phân chính xác là `java.math.BigDecimal` ở phía Java và `DECIMAL(p, s)` hoặc `NUMERIC(p, s)` ở phía SQL. Bài này giải thích cách tạo, tính toán, kiểm tra, ghi và đọc `BigDecimal` mà không vô tình làm mất độ chính xác.

Sau bài học, bạn có thể:

- Phân biệt số dấu phẩy động nhị phân (`float`, `double`, `FLOAT`, `REAL`) với số thập phân chính xác (`BigDecimal`, `DECIMAL`, `NUMERIC`).
- Chọn độ chính xác (`precision`) và số chữ số thập phân (`scale`) phù hợp với dữ liệu.
- Dùng `PreparedStatement.setBigDecimal` và `ResultSet.getBigDecimal` đúng cách.
- Kiểm soát quy tắc làm tròn, so sánh, phép chia, giá trị `NULL` và giới hạn cột SQL.
- Kiểm tra đường đi của một giá trị số từ đầu vào đến cơ sở dữ liệu và ngược lại.

## 1. Vì sao `double` có thể gây sai số?

`double` biểu diễn số theo dấu phẩy động **nhị phân** (IEEE 754). Nhiều phân số thập phân hữu hạn, chẳng hạn `0.1` và `0.2`, không có biểu diễn nhị phân hữu hạn. Vì vậy:

~~~java
System.out.println(0.1 + 0.2);
// 0.30000000000000004
~~~

Sai khác này có thể nhỏ trong một phép tính, nhưng sẽ thành vấn đề khi ứng dụng cần kiểm tra số dư, đối soát hóa đơn, so sánh giá trị bằng nhau hoặc áp dụng quy tắc làm tròn cố định. `BigDecimal` lưu giá trị thập phân dưới dạng **số nguyên không chia tỷ lệ** (`unscaled value`) cùng **scale**, nên có thể biểu diễn chính xác các giá trị như `0.10`, `0.20` và `0.30`.

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");

System.out.println(a.add(b)); // 0.30
~~~

Điểm cần nhớ: **`BigDecimal` chỉ giữ được giá trị đầu vào mà nó nhận được.** Nếu dữ liệu đã bị làm tròn qua `double` trước đó, chuyển nó sang `BigDecimal` không thể khôi phục những chữ số ban đầu đã mất.

| Nhu cầu | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Tiền, phí, thuế, số dư, số lượng cần đối soát theo chữ số thập phân | Java `BigDecimal` + SQL `DECIMAL/NUMERIC` | Biểu diễn thập phân chính xác trong giới hạn định nghĩa của cột |
| Đo lường khoa học, hình học, tính toán chấp nhận sai số gần đúng | `double` + kiểu dấu phẩy động SQL khi phù hợp | Tính toán xấp xỉ thường nhanh hơn, có dải giá trị rộng |
| Số đếm nguyên | `int`/`long` + `INTEGER`/`BIGINT` | Không cần phần thập phân |
| Số tiền quy đổi sang đơn vị nhỏ nhất dạng số nguyên | `long` + `BIGINT`, nếu miền giá trị và nghiệp vụ cho phép | Có thể chính xác nhưng phải quản lý đơn vị và nguy cơ tràn số |

## 2. Khởi tạo `BigDecimal` mà không mang theo sai số

Ưu tiên nhận dữ liệu thập phân ở dạng chuỗi gốc hoặc đã được parser xử lý thành kiểu số thập phân chính xác:

~~~java
BigDecimal price = new BigDecimal("1299.90");
BigDecimal rate = new BigDecimal("0.075");
BigDecimal zero = BigDecimal.ZERO;
BigDecimal count = BigDecimal.valueOf(42L);
~~~

Tránh tạo trực tiếp từ literal kiểu `double`:

~~~java
BigDecimal wrong = new BigDecimal(0.1);
// 0.1000000000000000055511151231257827021181583404541015625

BigDecimal decimalOfDouble = BigDecimal.valueOf(0.1);
// 0.1

BigDecimal exactFromText = new BigDecimal("0.1");
// 0.1
~~~

`BigDecimal.valueOf(double)` dựa trên biểu diễn thập phân của `Double.toString(double)`, thường phù hợp hơn `new BigDecimal(double)` khi bắt buộc phải nhận một `double`. Tuy nhiên, **nếu dữ liệu nguồn từng bị làm tròn hoặc mất chữ số trong `double`, cả hai cách đều không lấy lại được dữ liệu gốc**. Ví dụ, khi nhận JSON cho dữ liệu tài chính, hãy cấu hình parser để giữ số thập phân dưới dạng `BigDecimal` hoặc chuỗi thay vì mặc định đi qua `double`.

Không dùng phép nối chuỗi để biến `double` đã tính toán thành dữ liệu được cho là chính xác: `new BigDecimal(String.valueOf(a + b))` vẫn nhận kết quả `double` đã bị sai số.

## 3. Hiểu `precision`, `scale` và giới hạn cột SQL

Một `BigDecimal` có hai thông tin quan trọng:

- **Precision**: số chữ số có nghĩa trong giá trị không chia tỷ lệ.
- **Scale**: số chữ số ở bên phải dấu thập phân; scale có thể âm trong Java.

~~~java
BigDecimal n = new BigDecimal("123.4500");

System.out.println(n.precision()); // 7
System.out.println(n.scale());     // 4
System.out.println(n.unscaledValue()); // 1234500
~~~

Trong SQL, `DECIMAL(p, s)` thường cho phép tối đa `p` chữ số thập phân tổng cộng, trong đó `s` chữ số ở phần thập phân; số chữ số dành cho phần nguyên là `p - s`. Ví dụ:

~~~sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL CHECK (amount >= 0)
);
~~~

`DECIMAL(19, 2)` dành tối đa **17 chữ số phần nguyên và 2 chữ số phần thập phân**. Giá trị `99999999999999999.99` vừa giới hạn, còn `100000000000000000.00` vượt giới hạn. Kiểu `NUMERIC(19, 2)` thường phục vụ mục đích tương tự; chi tiết giới hạn, quy tắc làm tròn và xử lý lỗi vẫn phụ thuộc hệ quản trị cơ sở dữ liệu.

Không nên hiểu rằng dùng `BigDecimal` đồng nghĩa với lưu được số lớn tùy ý trong SQL: bản thân `BigDecimal` có độ chính xác tùy ý trong giới hạn tài nguyên, nhưng **giá trị lưu được bị giới hạn bởi kiểu cột và driver**. Một cột `DECIMAL(19, 2)` có thể từ chối hoặc làm tròn giá trị nhiều hơn hai chữ số phần thập phân tùy hệ quản trị và cấu hình. Hãy kiểm tra trước khi truyền cho JDBC.

### Quy ước scale tại ranh giới lưu trữ

Nếu nghiệp vụ yêu cầu đúng hai chữ số sau dấu thập phân, có thể áp dụng:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

static BigDecimal requireAmount(BigDecimal input) {
    if (input == null) {
        throw new IllegalArgumentException("amount khong duoc null");
    }

    // Chỉ cho phép bỏ các số 0 thừa; cấm làm tròn ngầm.
    BigDecimal amount = input.setScale(2, RoundingMode.UNNECESSARY);

    if (amount.precision() > 19) {
        throw new IllegalArgumentException("amount vuot DECIMAL(19, 2)");
    }
    if (amount.signum() < 0) {
        throw new IllegalArgumentException("amount phai khong am");
    }

    return amount;
}
~~~

Các ví dụ khi gọi `requireAmount`:

| Đầu vào | Kết quả | Giải thích |
| --- | --- | --- |
| `"12.3"` | `12.30` | Bổ sung số 0, không thay đổi giá trị |
| `"12.3400"` | `12.34` | Bỏ số 0 thừa, không làm tròn |
| `"12.345"` | Lỗi `ArithmeticException` | Cần bỏ chữ số có nghĩa; `UNNECESSARY` cấm |
| `"99999999999999999.99"` | Chấp nhận | Vừa `DECIMAL(19, 2)` |
| `"100000000000000000.00"` | Lỗi `IllegalArgumentException` | Vượt 19 chữ số sau khi chuẩn hóa scale |
| `"-0.01"` | Lỗi `IllegalArgumentException` | Vi phạm quy tắc nghiệp vụ không âm |

Đây là **ví dụ chính sách cho một cột tiền tệ có hai chữ số thập phân**, không phải quy tắc cho mọi loại tiền hoặc mọi số đo. Với đơn vị không có phần thập phân, số lượng cần ba chữ số thập phân hoặc quy định khác, hãy chọn scale tương ứng và điều chỉnh schema. Không tùy tiện cắt bớt chữ số để dữ liệu vừa cột.

## 4. Đọc và ghi chính xác qua JDBC

Đường truyền dữ liệu mong muốn:

~~~mermaid
flowchart LR
    A["Đầu vào thập phân gốc"] --> B["BigDecimal"]
    B --> C["Kiểm tra scale và precision"]
    C --> D["PreparedStatement.setBigDecimal"]
    D --> E["SQL DECIMAL / NUMERIC"]
    E --> F["ResultSet.getBigDecimal"]
    F --> G["BigDecimal trong ứng dụng"]
~~~

Dùng `DataSource` để lấy kết nối, `PreparedStatement` để truyền giá trị theo tham số và `ResultSet` để đọc lại. Đoạn mã sau dùng bảng `payments` đã tạo ở phần trên:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class PaymentRepository {
    private final DataSource dataSource;

    public PaymentRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public void insert(long id, BigDecimal rawAmount) throws SQLException {
        BigDecimal amount = requireAmount(rawAmount);
        String sql = "INSERT INTO payments (id, amount) VALUES (?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);
            statement.setBigDecimal(2, amount);
            statement.executeUpdate();
        }
    }

    public Optional<BigDecimal> findAmount(long id) throws SQLException {
        String sql = "SELECT amount FROM payments WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, id);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                BigDecimal amount = rs.getBigDecimal("amount");
                if (amount == null) {
                    throw new SQLException("payments.amount bat ngo NULL");
                }
                return Optional.of(amount);
            }
        }
    }

    private static BigDecimal requireAmount(BigDecimal input) {
        if (input == null) {
            throw new IllegalArgumentException("amount khong duoc null");
        }
        BigDecimal value = input.setScale(2, RoundingMode.UNNECESSARY);
        if (value.precision() > 19 || value.signum() < 0) {
            throw new IllegalArgumentException("amount khong hop le");
        }
        return value;
    }
}
~~~

Ví dụ sử dụng khi đã có `DataSource` hợp lệ và bảng `payments`:

~~~java
PaymentRepository repository = new PaymentRepository(dataSource);

BigDecimal expected = new BigDecimal("12345678901234567.89");
repository.insert(1001L, expected);

BigDecimal actual = repository.findAmount(1001L)
    .orElseThrow(() -> new IllegalStateException("Khong tim thay payment"));

System.out.println(actual.compareTo(expected) == 0); // Kỳ vọng: true
~~~

Lưu ý khi đọc/ghi:

1. Chỉ số tham số của `PreparedStatement` **bắt đầu từ 1**. `setBigDecimal(2, amount)` gán đúng tham số thứ hai.
2. `setBigDecimal` truyền số thập phân cho driver; **nó không tự bảo đảm schema SQL đủ precision/scale**. Việc kiểm tra giá trị và định nghĩa cột vẫn cần thiết.
3. `ResultSet.getBigDecimal` là lựa chọn thích hợp cho cột `DECIMAL/NUMERIC`. Tránh `getDouble` rồi chuyển ngược sang `BigDecimal` vì có thể mất chữ số quan trọng.
4. `getBigDecimal` trả `null` nếu ô SQL là `NULL`. Nếu cột cho phép null, hãy xử lý rõ ràng. Khi ghi null, dùng `statement.setNull(index, java.sql.Types.DECIMAL)` theo kiểu SQL tương ứng.
5. `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` ngay cả khi thao tác phát sinh ngoại lệ. Trong ví dụ chỉ có một câu `INSERT`; nhiều câu ghi phụ thuộc nhau cần transaction riêng.
6. `Optional.empty()` ở `findAmount` biểu thị **không có bản ghi**. Với schema `NOT NULL`, giá trị null trả về từ cột là bất thường, vì vậy ví dụ phát sinh `SQLException` thay vì nhầm nó với việc thiếu bản ghi.

### Vì sao không dùng `setDouble` / `getDouble`?

Giả sử cột lưu `12345678901234567.89`. Một `double` có khoảng 15–17 chữ số thập phân có nghĩa, vì vậy không thể bảo đảm giữ đủ **19 chữ số có nghĩa** của số này. Chuyển qua `double` làm mất tính đúng đắn ngay cả khi cột SQL vốn lưu chính xác.

~~~java
// Không nên: đi vòng qua double.
double approximate = rs.getDouble("amount");
BigDecimal recovered = BigDecimal.valueOf(approximate);

// Nên: lấy số thập phân trực tiếp từ cột DECIMAL.
BigDecimal exact = rs.getBigDecimal("amount");
~~~

Nếu dữ liệu được lưu trước đó trong cột `FLOAT`/`DOUBLE` hoặc đã đi qua `double`, chỉ thay `getDouble` thành `getBigDecimal` **không thể sửa lại sai số đã có trong dữ liệu**.

## 5. Tính toán và làm tròn phải tuân theo nghiệp vụ

`BigDecimal` là kiểu **bất biến** (`immutable`); các phép tính trả về đối tượng kết quả mới:

~~~java
BigDecimal subtotal = new BigDecimal("199.95");
BigDecimal rate = new BigDecimal("0.075");

// Nhân trước, chỉ làm tròn ở thời điểm nghiệp vụ yêu cầu.
BigDecimal rawTax = subtotal.multiply(rate); // 14.99625
BigDecimal tax = rawTax.setScale(2, RoundingMode.HALF_EVEN); // 15.00
BigDecimal total = subtotal.add(tax); // 214.95
~~~

Một số quy tắc quan trọng:

- `add`, `subtract`, `multiply` có thể giữ kết quả số học chính xác khi không áp dụng `MathContext` giới hạn chữ số; kết quả vẫn có thể có scale lớn hơn cột SQL.
- `divide` không phải lúc nào cũng có kết quả thập phân hữu hạn. Ví dụ `BigDecimal.ONE.divide(new BigDecimal("3"))` phát sinh `ArithmeticException`. Khi phép chia có thể vô hạn, phải chỉ rõ scale và `RoundingMode`.
- `setScale(2, RoundingMode.HALF_UP)` và `setScale(2, RoundingMode.HALF_EVEN)` có thể cho kết quả khác nhau. Quy tắc nào đúng phụ thuộc hợp đồng, luật hoặc quy định nghiệp vụ.
- `RoundingMode.UNNECESSARY` hữu ích khi chỉ muốn **kiểm tra** dữ liệu có phù hợp scale, thay vì âm thầm làm tròn.
- `MathContext(19, ...)` giới hạn **số chữ số có nghĩa của phép toán**, không đồng nghĩa với `scale = 2`. Không nhầm `precision` với số chữ số sau dấu thập phân.

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal part = one.divide(three, 2, RoundingMode.HALF_UP);
// 0.33

BigDecimal midpoint = new BigDecimal("10.005");
System.out.println(midpoint.setScale(2, RoundingMode.HALF_UP));   // 10.01
System.out.println(midpoint.setScale(2, RoundingMode.HALF_EVEN)); // 10.00
~~~

**Vị trí làm tròn cũng quan trọng.** Làm tròn mỗi dòng hóa đơn rồi cộng có thể khác với cộng các giá trị chưa làm tròn và chỉ làm tròn tổng một lần. Hệ thống phải chọn quy tắc nhất quán cho tính toán, ghi cơ sở dữ liệu, in hóa đơn và đối soát; không nên lấy scale của cột SQL làm chính sách nghiệp vụ mặc định.

## 6. So sánh và biểu diễn dạng văn bản

`BigDecimal.equals` xét **cả giá trị lẫn scale**, còn `compareTo` xét giá trị số:

~~~java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));          // false
System.out.println(x.compareTo(y) == 0);  // true
~~~

Dùng `compareTo` để so sánh giá trị số. Khi muốn so sánh bằng `equals` hoặc dùng làm khóa trong `HashMap`/phần tử `HashSet`, hãy thống nhất scale từ trước. Cẩn thận khi trộn `HashSet` và `TreeSet` vì `equals` và thứ tự tự nhiên của `BigDecimal` có thể khác nhau đối với các giá trị cùng số nhưng khác scale.

~~~java
BigDecimal a = new BigDecimal("1.2").setScale(2);  // 1.20
BigDecimal b = new BigDecimal("1.20").setScale(2); // 1.20

System.out.println(a.equals(b)); // true
~~~

`stripTrailingZeros()` có thể làm thay đổi scale, thậm chí khiến scale âm (`new BigDecimal("1000").stripTrailingZeros()` có thể được biểu diễn thành `1E+3`). Nếu cần cố định hai chữ số thập phân, dùng `setScale(2, ...)` theo quy tắc đã chọn.

Khi đưa số sang giao diện hoặc gửi sang hệ thống khác, xác định rõ **định dạng truyền dữ liệu**:

~~~java
BigDecimal amount = new BigDecimal("123456.70");

System.out.println(amount.toPlainString()); // 123456.70
System.out.println(amount.toString());      // Có thể dùng ký hiệu khoa học ở giá trị khác
~~~

`toPlainString` giúp tránh ký hiệu khoa học trong chuỗi số thuần, nhưng không tự áp dụng quy tắc phân tách hàng nghìn, dấu phẩy theo ngôn ngữ hoặc đơn vị tiền. Việc trình bày cho người dùng thuộc tầng định dạng; không trộn định dạng vùng miền vào dữ liệu số trước khi gửi cho JDBC.

## 7. Transaction, batching và lỗi dữ liệu

Độ chính xác thập phân chỉ là một phần của tính đúng đắn:

- Nếu cập nhật nhiều bảng hoặc nhiều dòng như một nghiệp vụ, quản lý transaction bằng `Connection.setAutoCommit(false)`, `commit()` và `rollback()`; `BigDecimal` không thay thế tính nguyên tử của transaction.
- Khi chạy `PreparedStatement.addBatch()` / `executeBatch()`, chuẩn hóa từng giá trị **trước khi thêm vào batch**. Một bản ghi không hợp lệ phải được phát hiện và xử lý theo chính sách của toàn giao dịch.
- Bắt `SQLException` để phân biệt lỗi kiểu dữ liệu, overflow, scale hoặc ràng buộc SQL; thông báo và mã lỗi cụ thể tùy driver/hệ quản trị. Không nuốt ngoại lệ rồi mặc định giá trị sai bằng `0`.
- Nên khai báo `DECIMAL(p, s)` rõ ràng trong migration/schema. Cách xử lý khi vượt giới hạn, quy tắc làm tròn, phạm vi precision tối đa và ánh xạ metadata có thể khác nhau giữa PostgreSQL, MySQL, SQL Server, Oracle và các hệ quản trị khác.
- Có thể kiểm tra `ResultSetMetaData.getPrecision(columnIndex)` và `getScale(columnIndex)` khi cần chẩn đoán schema, nhưng hãy đối chiếu với đặc tả của driver. Metadata không thay thế kiểm thử thực tế.

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `0.1 + 0.2` ra `0.30000000000000004` | Số đã qua `double` | Giữ dạng chuỗi/`BigDecimal` từ đầu vào |
| Lưu `12.345` vào `DECIMAL(19, 2)` bị lỗi hoặc mất chữ số | Scale ứng dụng lớn hơn scale cột | Kiểm tra với `UNNECESSARY` hoặc làm tròn theo quy tắc được chấp thuận |
| Giá trị rất lớn đọc ra không còn chữ số cuối | Đọc qua `getDouble` hoặc trung gian dấu phẩy động | Đọc trực tiếp bằng `getBigDecimal` |
| Hai số cùng giá trị nhưng `equals` trả `false` | Scale khác nhau | Dùng `compareTo` hoặc chuẩn hóa scale |
| `divide` ném `ArithmeticException` | Phép chia vô hạn hoặc không cho phép làm tròn | Chỉ rõ scale và `RoundingMode` |
| Ghi thất bại vì vượt giới hạn | Precision của giá trị lớn hơn `DECIMAL(p, s)` | Xem lại validation, schema và giới hạn nghiệp vụ |

## 8. Quy trình tự kiểm tra trước khi đưa vào hệ thống

Dùng checklist này để rà soát một luồng dữ liệu thập phân từ đầu vào đến cơ sở dữ liệu:

1. **Đầu vào:** dữ liệu ban đầu còn nguyên chữ số thập phân hay đã bị chuyển qua `double`?
2. **Miền giá trị:** nghiệp vụ cho phép âm không, tối đa bao nhiêu chữ số phần nguyên, cần bao nhiêu chữ số phần thập phân?
3. **Tính toán:** phép nhân/chia có tăng scale không; khi nào và theo quy tắc nào được phép làm tròn?
4. **Ranh giới JDBC:** đã dùng `setBigDecimal`, `getBigDecimal` và câu SQL tham số hóa chưa?
5. **Schema:** kiểu cột có phải `DECIMAL/NUMERIC(p, s)` với precision/scale đủ chứa dữ liệu hợp lệ không?
6. **Kiểm chứng:** đã thử số sát giới hạn, số có nhiều số 0 cuối, giá trị `NULL`, giá trị cần làm tròn và đọc lại sau khi ghi chưa?

Một phép thử tích hợp hữu ích là ghi rồi đọc lại các giá trị `0.10`, `12.3400`, `99999999999999999.99` và một giá trị vượt giới hạn. Với các giá trị được phép lưu, so sánh bằng `compareTo` để xác nhận **giá trị số** không thay đổi, đồng thời kiểm tra scale theo hợp đồng dữ liệu. Với giá trị không hợp lệ, xác minh ứng dụng báo lỗi có chủ đích trước khi cơ sở dữ liệu âm thầm làm tròn hoặc từ chối.

### Câu hỏi tự luyện

1. Vì sao `new BigDecimal("0.1")` chính xác hơn `new BigDecimal(0.1)` với giá trị thập phân này?
2. Cột `DECIMAL(12, 3)` có tối đa bao nhiêu chữ số phần nguyên? `BigDecimal("123.4567")` có phù hợp để lưu nguyên vẹn không?
3. Tại sao `BigDecimal("1.0").equals(BigDecimal("1.00"))` trả `false` nhưng `compareTo` trả `0`?
4. Nếu ứng dụng phải lưu `5 / 6` với hai chữ số thập phân, bạn sẽ chọn overload nào của `divide` và chọn `RoundingMode` dựa trên điều gì?
5. Với cột `DECIMAL(19, 2)`, cách nào giúp phát hiện `12.345` trước khi gửi đến driver?

**Gợi ý đáp án:** (1) Constructor từ chuỗi nhận đúng các chữ số được viết, còn constructor từ `double` nhận giá trị xấp xỉ nhị phân; (2) 9 chữ số phần nguyên và `123.4567` có 4 chữ số thập phân nên không phù hợp để lưu nguyên vẹn; (3) `equals` xét scale, `compareTo` xét giá trị số; (4) `divide(divisor, 2, roundingMode)` với quy tắc làm tròn do nghiệp vụ quy định; (5) `setScale(2, RoundingMode.UNNECESSARY)` và kiểm tra precision.

Giữ toàn bộ đường đi **đầu vào chính xác → `BigDecimal` → phép tính có quy tắc → JDBC tham số hóa → SQL `DECIMAL/NUMERIC` → `BigDecimal`** là nguyên tắc cốt lõi để tránh sai lệch thập phân trong ứng dụng JDBC.
