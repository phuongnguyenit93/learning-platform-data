# BigDecimal, precision và scale cho dữ liệu thập phân trong Spring JDBC

Dữ liệu thập phân xuất hiện trong đơn giá, thuế, lãi suất, tỷ lệ, khối lượng và các phép đo. Khi làm việc với Spring Framework ở tầng data access, một lỗi phổ biến là ứng dụng giữ một số bằng Java `double` rồi ghi vào cột SQL `DECIMAL`/`NUMERIC`, hoặc đưa `BigDecimal` có quá nhiều chữ số thập phân xuống cơ sở dữ liệu mà không xác định trước quy tắc làm tròn. Những lỗi này có thể dẫn đến sai lệch nhỏ nhưng tích lũy, số bị làm tròn không nhất quán, hoặc lỗi vượt giới hạn của cột.

Bài học đi từ **biểu diễn số của `BigDecimal`** đến **ràng buộc `DECIMAL(precision, scale)` của SQL**, rồi áp dụng trong Spring `JdbcTemplate` và `NamedParameterJdbcTemplate`. Mục tiêu là biết giá trị nào sẽ được lưu, làm tròn ở đâu, cách bind và đọc về đúng kiểu, cùng cách kiểm chứng hành vi trên JDBC driver thực tế.

## 1. Vì sao BigDecimal phù hợp với dữ liệu thập phân cần độ chính xác?

`double` và `float` lưu số dưới dạng dấu phẩy động nhị phân. Nhiều số thập phân thông thường như `0.1` không biểu diễn chính xác bằng một số hữu hạn bit nhị phân. Vì vậy:

~~~java
System.out.println(0.1 + 0.2);
~~~

Kết quả điển hình của Java là:

~~~text
0.30000000000000004
~~~

`BigDecimal` lưu giá trị dưới dạng **số nguyên không có dấu phẩy (`unscaled value`)** và **`scale`**, về mặt toán học:

~~~text
value = unscaledValue × 10^(-scale)
~~~

Ví dụ `new BigDecimal("12.30")` có `unscaledValue = 1230` và `scale = 2`, nên giá trị chính xác là `1230 × 10^-2 = 12.30`. `BigDecimal` là **immutable**: các lời gọi như `add`, `multiply` hoặc `setScale` trả về một đối tượng kết quả; chúng không sửa giá trị ban đầu.

`BigDecimal` cho phép tính thập phân chính xác **khi đầu vào đã chính xác và phép toán được thực hiện với quy tắc làm tròn phù hợp**. Nó không tự sửa dữ liệu đã bị mất độ chính xác trước đó khi tính bằng `double`, và không có nghĩa mọi phép chia đều cho kết quả thập phân hữu hạn.

Trong ứng dụng, `BigDecimal` thường đi với các cột SQL `DECIMAL` hoặc `NUMERIC`. Tuy nhiên, phải phân biệt đặc tính của **một giá trị Java** với **giới hạn được khai báo của một cột**.

## 2. Precision và scale của một BigDecimal

- **`precision()`:** số chữ số có nghĩa trong `unscaledValue`, bỏ dấu âm và các số 0 đứng đầu. Với giá trị 0, precision bằng 1.
- **`scale()`:** số chữ số sau dấu thập phân ở biểu diễn thông thường khi scale không âm. Scale cũng có thể âm; khi đó giá trị được nhân với một lũy thừa dương của 10.
- **`unscaledValue()`:** số nguyên dùng cùng scale để biểu diễn giá trị.
- **`toPlainString()`:** chuyển sang chuỗi thập phân không dùng ký hiệu số mũ; hữu ích khi muốn minh họa các chữ số thực tế.

| Tạo từ chuỗi | `unscaledValue` | `precision()` | `scale()` | Giá trị |
| --- | ---: | ---: | ---: | --- |
| `"12.30"` | 1230 | 4 | 2 | 12.30 |
| `"123.456"` | 123456 | 6 | 3 | 123.456 |
| `"0.0010"` | 10 | 2 | 4 | 0.0010 |
| `"1000.00"` | 100000 | 6 | 2 | 1000.00 |
| `"0.00"` | 0 | 1 | 2 | 0.00 |
| `"1E+3"` | 1 | 1 | -3 | 1000 |

Do đó, `precision` **không phải chỉ số chữ số trước dấu thập phân**, và `scale` **không phải tổng số chữ số**. Một giá trị `0.0010` có bốn chữ số sau dấu thập phân nhưng chỉ hai chữ số có nghĩa theo biểu diễn `BigDecimal`.

~~~java
BigDecimal amount = new BigDecimal("12.30");

System.out.println(amount.precision());      // 4
System.out.println(amount.scale());          // 2
System.out.println(amount.unscaledValue());  // 1230
System.out.println(amount.toPlainString());  // 12.30
~~~

Đây là **mảnh code Java** (cần `import java.math.BigDecimal;`) minh họa các accessor, không phải một class `main` hoàn chỉnh. Phần 7 có chương trình Java 17+ chạy độc lập.

### Scale có thể thay đổi dù giá trị số không đổi

~~~java
BigDecimal left  = new BigDecimal("2.0");   // precision 2, scale 1
BigDecimal right = new BigDecimal("2.00");  // precision 3, scale 2

System.out.println(left.compareTo(right));  // 0: cùng giá trị số
System.out.println(left.equals(right));     // false: khác scale
~~~

`compareTo` so sánh **giá trị số**; `equals` so cả giá trị và scale. Vì `hashCode` cũng chịu ảnh hưởng biểu diễn, hai giá trị bằng nhau về số học nhưng khác scale có thể hoạt động khác khi dùng làm key của `HashMap` hoặc phần tử của `HashSet`. Với so sánh nghiệp vụ như số tiền lớn hơn 0 hoặc hai số bằng nhau về giá trị, thường dùng `compareTo`. Khi scale là một phần của hợp đồng dữ liệu, hãy chuẩn hóa về scale quy định trước khi so sánh hoặc lưu.

`stripTrailingZeros()` cũng có thể thay đổi scale đáng kể: `new BigDecimal("1000.00").stripTrailingZeros()` có thể có scale `-3` và `toString()` cho dạng `1E+3`. Vì vậy, **không dùng `stripTrailingZeros()` như cách bảo đảm giữ hai chữ số thập phân khi hiển thị tiền**; dùng `setScale(2, ...)` theo quy tắc nghiệp vụ khi cần biểu diễn hai chữ số.

## 3. Precision và scale của SQL DECIMAL(p, s)

Với khai báo thông thường `DECIMAL(p, s)`:

- `p` là **precision khai báo**: tổng số chữ số thập phân có thể lưu theo định nghĩa cột.
- `s` là **scale khai báo**: số chữ số ở phần thập phân.
- Theo dạng phổ biến, `0 ≤ s ≤ p` và phần nguyên có tối đa `p - s` chữ số.

Ví dụ:

~~~sql
CREATE TABLE invoice_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description VARCHAR(100) NOT NULL,
    amount DECIMAL(8, 2) NOT NULL,
    tax_rate DECIMAL(7, 5)
);
~~~

Cột `amount DECIMAL(8,2)` phù hợp với các giá trị đã chuẩn hóa như `1234.57` hoặc `999999.99`. Nó dành tối đa **6 chữ số phần nguyên và 2 chữ số phần thập phân**, nên `1000000.00` vượt giới hạn của định nghĩa này. Cột `tax_rate DECIMAL(7,5)` có thể phục vụ tỷ lệ với tối đa 5 chữ số phần lẻ; không nên ép nó về hai chữ số như một số tiền.

| Đầu vào | Cột đích | Nhận xét |
| --- | --- | --- |
| `1234.57` | `DECIMAL(8,2)` | Vừa giới hạn và đủ 2 chữ số phần lẻ |
| `999999.99` | `DECIMAL(8,2)` | Giá trị dương lớn nhất với dạng `p=8, s=2` thông thường |
| `1000000.00` | `DECIMAL(8,2)` | Vượt sức chứa phần nguyên |
| `12.345` | `DECIMAL(8,2)` | Có thêm một chữ số phần lẻ; DB có thể làm tròn hoặc báo lỗi tùy hệ và cấu hình |
| `0.07500` | `DECIMAL(7,5)` | Tỷ lệ năm chữ số phần lẻ; không nên đổi sang scale 2 một cách tùy ý |

**Precision của cột khác precision của giá trị Java.** Ví dụ `new BigDecimal("12.3")` có `precision() = 3`, `scale() = 1`; cột `DECIMAL(8,2)` có định nghĩa tối đa tám chữ số và scale hai. Database/driver có thể đọc lại giá trị theo dạng `12.30`, nghĩa là biểu diễn `BigDecimal` sau khi đọc có scale 2, dù đầu vào Java scale 1.

Không chỉ kiểm tra `value.precision() <= p`. Ví dụ `new BigDecimal("12345")` có precision 5 nhưng **không thể lưu nguyên vẹn** vào `DECIMAL(5,2)` vì phần nguyên cần 5 chữ số, trong khi cột chỉ dành 3. Một phép kiểm tra hữu ích với dạng thông thường `0 ≤ s ≤ p` là chuẩn hóa scale trước, rồi xác nhận trị tuyệt đối nhỏ hơn `10^(p-s)`; phần 9 có hàm Java cụ thể.

Hành vi khi truyền quá nhiều chữ số lẻ **không đồng nhất trên mọi DB**. Chẳng hạn PostgreSQL `NUMERIC(p,s)` làm tròn về scale cột trước, rồi từ chối nếu phần nguyên vượt giới hạn. Các DB khác có thể xử lý chi tiết khác nhau. Do đó, **quy tắc làm tròn của nghiệp vụ nên được thực hiện và kiểm thử trong ứng dụng**, không dựa ngầm vào một cách làm tròn của cơ sở dữ liệu.

## 4. Khởi tạo BigDecimal mà không mang sai số của double

Lựa chọn an toàn cho giá trị thập phân chính xác là dựng từ chuỗi decimal hoặc từ dữ liệu kiểu số nguyên theo đơn vị nhỏ nhất:

~~~java
BigDecimal price = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.075");
BigDecimal quantity = BigDecimal.valueOf(3L);
BigDecimal result = price.multiply(quantity);
~~~

Các giá trị trên giữ đúng ý nghĩa của chuỗi hoặc số nguyên gốc.

Tránh:

~~~java
BigDecimal unreliable = new BigDecimal(0.1);
~~~

Giá trị `0.1` đã đi qua kiểu `double`. Constructor nhận `double` ghi lại chính xác giá trị nhị phân của `double` đó, nên `unreliable` thực tế mang nhiều chữ số lẻ khác với số thập phân `0.1` mong muốn.

~~~java
BigDecimal decimal = new BigDecimal("0.1");
BigDecimal viaValueOf = BigDecimal.valueOf(0.1);

System.out.println(decimal.equals(viaValueOf));     // true
System.out.println(decimal.equals(new BigDecimal(0.1))); // false
~~~

`BigDecimal.valueOf(double)` dùng biểu diễn chuỗi `Double.toString(...)`, nên với literal `0.1` cho kết quả như chuỗi `"0.1"`. Nhưng nếu dữ liệu **đã trải qua phép tính bằng double**, các sai lệch trước đó vẫn có thể tồn tại. Khi dữ liệu nguồn đòi chính xác thập phân, hãy tránh vòng chuyển đổi `BigDecimal -> double -> BigDecimal`.

Ở biên API hoặc file import, phân tích chuỗi số theo quy tắc locale rõ ràng. Ví dụ `new BigDecimal("1,25")` **không** hiểu dấu phẩy là dấu thập phân; Java sẽ ném `NumberFormatException`. Nếu UI dùng dấu phẩy thập phân, parse đầu vào theo định dạng đã xác định trước rồi tạo số chính xác. Đừng thay dấu phẩy bằng dấu chấm một cách mù quáng khi dấu phân tách hàng nghìn cũng có thể xuất hiện.

## 5. setScale, RoundingMode và MathContext là ba khái niệm khác nhau

`setScale(n, mode)` quyết định **số chữ số sau dấu thập phân của kết quả**. Nó trả một `BigDecimal` mới; đối tượng gốc không đổi.

~~~java
BigDecimal amount = new BigDecimal("1.005");

System.out.println(amount.setScale(2, RoundingMode.HALF_UP));   // 1.01
System.out.println(amount.setScale(2, RoundingMode.HALF_EVEN)); // 1.00
~~~

- `HALF_UP`: khi nằm đúng giữa hai kết quả, làm tròn ra xa 0; thường được dùng ở một số quy tắc tiền tệ, nhưng không phải mặc định cho mọi nghiệp vụ.
- `HALF_EVEN`: khi nằm đúng giữa hai kết quả, chọn chữ số cuối chẵn; thường được gọi là *banker's rounding*.
- `DOWN`: bỏ các chữ số bị loại theo hướng về 0. Với số âm, hướng về 0 khác với `FLOOR`.
- `UNNECESSARY`: **không chấp nhận việc phải làm tròn**; ném `ArithmeticException` nếu đầu vào không thể biểu diễn chính xác ở scale yêu cầu.

~~~java
new BigDecimal("12.340").setScale(2, RoundingMode.UNNECESSARY);
// Kết quả 12.34: chỉ bỏ chữ số 0 thừa, không đổi giá trị.

new BigDecimal("12.345").setScale(2, RoundingMode.UNNECESSARY);
// Ném ArithmeticException vì bỏ chữ số 5 sẽ đổi giá trị.
~~~

`setScale(2)` không truyền `RoundingMode` cũng yêu cầu không đổi giá trị; nó ném `ArithmeticException` nếu cần làm tròn. Nếu chính sách nghiệp vụ là “nhận tối đa hai chữ số lẻ và từ chối giá trị sai”, `UNNECESSARY` phù hợp hơn việc tự động làm tròn.

### MathContext giới hạn chữ số có nghĩa, không phải số chữ số thập phân

`MathContext(precision, roundingMode)` áp dụng **độ chính xác có nghĩa cho kết quả phép toán**. Ví dụ:

~~~java
BigDecimal input = new BigDecimal("123.456");

System.out.println(input.setScale(2, RoundingMode.HALF_UP));
// 123.46: scale = 2

System.out.println(input.round(new MathContext(4, RoundingMode.HALF_UP)));
// 123.5: precision = 4, scale = 1
~~~

Đây là **mảnh code minh họa**, cần import `java.math.BigDecimal`, `java.math.MathContext` và `java.math.RoundingMode`. `new MathContext(4, ...)` không có nghĩa tương đương cột SQL `DECIMAL(4,2)`. Cột `DECIMAL(4,2)` còn có giới hạn riêng là tối đa hai chữ số phần nguyên.

`MathContext.DECIMAL64` có precision 16 chữ số có nghĩa; không nên hiểu đó là “16 chữ số sau dấu thập phân”. Khi nhân/chia nhiều bước, cần quyết định có làm tròn ở từng bước hay chỉ tại điểm nghiệp vụ quy định để tránh cộng dồn sai số làm tròn.

### Phép chia có thể không kết thúc

~~~java
BigDecimal one = new BigDecimal("1");
BigDecimal three = new BigDecimal("3");

// one.divide(three) ném ArithmeticException:
// kết quả 0.333... không có biểu diễn thập phân hữu hạn.

BigDecimal third = one.divide(three, 4, RoundingMode.HALF_UP);
// third = 0.3333
~~~

Nên chỉ rõ scale và rounding mode với phép chia tỷ lệ không bảo đảm kết quả hữu hạn. Không chờ đến lúc lưu database để quyết định cắt bớt chữ số.

## 6. Quy tắc scale khi tính toán và so sánh

Với các phép toán **chính xác, không truyền MathContext**, BigDecimal có quy tắc scale kết quả:

| Phép toán | Scale kết quả chính xác thường theo | Ví dụ |
| --- | --- | --- |
| `add`, `subtract` | Scale lớn nhất của hai toán hạng | `1.20 + 2.3 = 3.50` (scale 2) |
| `multiply` | Tổng scale của hai toán hạng | `1.20 × 3.00 = 3.6000` (scale 4) |
| `divide` | Có preferred scale nhưng kết quả không nhất thiết hữu hạn | `1 / 3` cần rounding rule |
| `setScale` | Scale được chỉ định; có thể cần làm tròn | `2.345 -> 2.35` với `HALF_UP` |

Ví dụ tính số tiền hàng và thuế:

~~~java
BigDecimal unitPrice = new BigDecimal("19.99");
BigDecimal count = BigDecimal.valueOf(3);
BigDecimal subtotal = unitPrice.multiply(count); // 59.97

BigDecimal taxRate = new BigDecimal("0.075");
BigDecimal exactTax = subtotal.multiply(taxRate); // 4.49775
BigDecimal tax = exactTax.setScale(2, RoundingMode.HALF_UP); // 4.50
BigDecimal total = subtotal.add(tax); // 64.47
~~~

Chính sách “làm tròn thuế theo từng dòng”, “làm tròn thuế trên toàn hóa đơn”, hoặc “làm tròn mỗi phép toán” có thể cho kết quả khác nhau. Đây là **quyết định nghiệp vụ**, cần ghi rõ và kiểm thử. `BigDecimal` đảm bảo ta thực hiện đúng quy tắc đã chọn, nhưng không tự chọn quy tắc thay cho nghiệp vụ.

Khi kiểm tra không âm:

~~~java
if (total.compareTo(BigDecimal.ZERO) < 0) {
    throw new IllegalArgumentException("Total must not be negative");
}
~~~

Dùng `compareTo` ở đây vì so sánh **giá trị số**, bất kể `total` có scale 1, 2 hay 4. Nếu cần dùng số làm key của map/set hoặc dùng `equals`, hãy chuẩn hóa scale nhất quán trước.

## 7. Ví dụ Java 17+ độc lập: kiểm tra precision, scale và rounding

Tạo file `DecimalMathDemo.java` chứa nguyên chương trình sau:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class DecimalMathDemo {
    private static void show(String label, BigDecimal number) {
        System.out.printf(
                "%s=%s p=%d s=%d%n",
                label,
                number.toPlainString(),
                number.precision(),
                number.scale());
    }

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("123.450");
        show("amount", amount);
        show("scale2", amount.setScale(2, RoundingMode.UNNECESSARY));

        BigDecimal tax = new BigDecimal("19.99")
                .multiply(new BigDecimal("0.075"))
                .setScale(2, RoundingMode.HALF_UP);
        show("tax", tax);

        BigDecimal third = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        show("third", third);

        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        System.out.println("equals=" + a.equals(b));
        System.out.println("compare=" + a.compareTo(b));

        System.out.println("doubleConstructorExact="
                + new BigDecimal(0.1).equals(new BigDecimal("0.1")));
        System.out.println("valueOfDouble="
                + BigDecimal.valueOf(0.1).equals(new BigDecimal("0.1")));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ (không cần dependency):

~~~bash
javac DecimalMathDemo.java
java DecimalMathDemo
~~~

Stdout chính xác:

~~~text
amount=123.450 p=6 s=3
scale2=123.45 p=5 s=2
tax=1.50 p=3 s=2
third=0.33 p=2 s=2
equals=false
compare=0
doubleConstructorExact=false
valueOfDouble=true
~~~

`tax` được tính chính xác ở giá trị `19.99 × 0.075 = 1.49925` rồi mới làm tròn thành `1.50`. Không có phép tính `double` trung gian. Hai dòng cuối cho thấy rủi ro khi khởi tạo trực tiếp từ literal `double`.

## 8. Đường đi dữ liệu BigDecimal qua Spring JDBC

Luồng điển hình:

~~~text
Chuỗi/đầu vào chính xác
    ↓ parse
java.math.BigDecimal (precision(), scale())
    ↓ validate và áp dụng RoundingMode do nghiệp vụ quy định
BigDecimal đã chuẩn hóa theo cột
    ↓ JdbcTemplate / NamedParameterJdbcTemplate bind JDBC parameter
PreparedStatement → DECIMAL/NUMERIC trong DB
    ↓ truy vấn
ResultSet.getBigDecimal(...) hoặc RowMapper
    ↓ so sánh giá trị, kiểm tra scale theo DB/driver
Dữ liệu ứng dụng / response
~~~

`JdbcTemplate` không tự biết quy tắc làm tròn tiền tệ của nghiệp vụ. Nó thực hiện việc truyền tham số xuống JDBC driver và đọc kết quả. Database quyết định ràng buộc `DECIMAL(p,s)`; vì vậy bước validate/normalize nên diễn ra **trước khi đưa vào câu lệnh INSERT/UPDATE**.

### 8.1. Ghi bằng JdbcTemplate và PreparedStatement.setBigDecimal

Giả sử cột `amount` có kiểu `DECIMAL(8,2)`:

~~~java
BigDecimal amount = new BigDecimal("1234.567")
        .setScale(2, RoundingMode.HALF_UP);

int rows = jdbcTemplate.update(
        "INSERT INTO invoice_line (description, amount) VALUES (?, ?)",
        ps -> {
            ps.setString(1, "Phí dịch vụ");
            ps.setBigDecimal(2, amount);
        });
~~~

Đây là **mảnh code trong DAO** có sẵn biến `jdbcTemplate`, không phải class Java độc lập. `setBigDecimal` giữ đối tượng Java ở kiểu decimal thay vì chuyển thành `double`. `rows` là **số hàng bị ảnh hưởng**, không phải precision, scale hoặc giá trị khóa sinh. Spring quản lý vòng đời PreparedStatement và connection theo cấu hình transaction.

Có thể truyền `BigDecimal` trực tiếp trong dạng ngắn:

~~~java
jdbcTemplate.update(
        "INSERT INTO invoice_line (description, amount) VALUES (?, ?)",
        "Phí dịch vụ",
        amount);
~~~

Spring thường bind tham số đúng theo kiểu Java và JDBC metadata. Khi driver nhạy với SQL type hoặc giá trị `null`, dùng cách rõ ràng hơn như `PreparedStatement.setBigDecimal`/`setNull`, `SqlParameterValue` hoặc nguồn tham số có `Types.DECIMAL`.

### 8.2. Ghi bằng NamedParameterJdbcTemplate và MapSqlParameterSource

~~~java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("description", "Phí dịch vụ", Types.VARCHAR)
        .addValue("amount", amount, Types.DECIMAL);

int rows = namedJdbc.update(
        """
        INSERT INTO invoice_line (description, amount)
        VALUES (:description, :amount)
        """,
        params);
~~~

Đây là **mảnh code DAO** có `namedJdbc` và `amount` đã được khởi tạo, không phải chương trình chạy độc lập. `Types.DECIMAL` là **mã kiểu SQL của tham số**; nó **không tự áp scale 2, không làm tròn, cũng không nới rộng giới hạn `DECIMAL(8,2)`**. Hãy chủ động chuẩn hóa số trước khi bind.

Nếu cột cho phép `NULL`, có thể truyền:

~~~java
MapSqlParameterSource nullableParams = new MapSqlParameterSource()
        .addValue("amount", null, Types.DECIMAL);
~~~

Đoạn này chỉ tạo nguồn tham số. Nếu đưa `NULL` vào cột `NOT NULL` như bảng `invoice_line`, database vẫn từ chối; `Types.DECIMAL` chỉ giúp driver biết cách bind `NULL`, không thay đổi ràng buộc.

### 8.3. Đọc bằng ResultSet.getBigDecimal hoặc RowMapper

~~~java
BigDecimal stored = jdbcTemplate.queryForObject(
        "SELECT amount FROM invoice_line WHERE id = ?",
        BigDecimal.class,
        id);
~~~

Đây là **mảnh code DAO** đã có biến `jdbcTemplate` và `id`. Nếu SQL không trả hàng, `queryForObject` ném ngoại lệ phù hợp; nếu cột SQL nhận `NULL`, kết quả có thể là `null`. Đọc theo cột cũng có thể dùng `RowMapper`:

~~~java
List<BigDecimal> amounts = jdbcTemplate.query(
        "SELECT amount FROM invoice_line ORDER BY id",
        (rs, rowNum) -> rs.getBigDecimal("amount"));
~~~

`ResultSet.getBigDecimal` nhận giá trị decimal từ driver. **Scale của giá trị đọc về có thể được driver/database biểu diễn khác đầu vào** (ví dụ trả `12.30` thay cho `12.3`). So sánh giá trị bằng `compareTo` và kiểm tra scale riêng nếu nghiệp vụ yêu cầu. Không dùng `getDouble` để đọc `DECIMAL` rồi tạo lại `BigDecimal` vì có thể đưa sai số nhị phân vào dữ liệu chính xác.

## 9. Chuẩn hóa scale và kiểm tra sức chứa của DECIMAL(p,s)

Đối với các cột decimal kiểu thông thường `0 ≤ scale ≤ precision`, một cách kiểm soát đầu vào gồm:

1. Kiểm tra giá trị không null và các ràng buộc nghiệp vụ như không âm.
2. Quyết định **cho phép làm tròn** hay **từ chối nếu có quá nhiều chữ số lẻ**.
3. Gọi `setScale(s, mode)` để có đúng scale mong muốn.
4. **Sau khi làm tròn**, kiểm tra giá trị tuyệt đối có nhỏ hơn `10^(p-s)` hay không. Bước này bắt cả trường hợp làm tròn gây nhớ sang phần nguyên.
5. Bind dưới dạng `BigDecimal`; vẫn để ràng buộc thực tế của DB là lớp kiểm tra cuối.

Ví dụ utility Java 17+:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class DecimalNormalizer {
    private DecimalNormalizer() {}

    public static BigDecimal forColumn(
            BigDecimal value, int precision, int scale,
            RoundingMode roundingMode) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(roundingMode, "roundingMode");

        if (precision < 1 || scale < 0 || scale > precision) {
            throw new IllegalArgumentException(
                    "Expected 0 <= scale <= precision, precision >= 1");
        }

        BigDecimal normalized = value.setScale(scale, roundingMode);
        BigDecimal exclusiveBound =
                BigDecimal.TEN.pow(precision - scale);

        if (normalized.abs().compareTo(exclusiveBound) >= 0) {
            throw new IllegalArgumentException(
                    "Value does not fit DECIMAL("
                    + precision + "," + scale + ")");
        }
        return normalized;
    }
}
~~~

Lưu thành `DecimalNormalizer.java` nếu muốn sử dụng như class riêng; đoạn này **biên dịch được với JDK 17+**. Quy tắc giới hạn ở đây áp dụng cho **cột decimal chuẩn có p ≥ s ≥ 0**; một số DB hỗ trợ scale âm hoặc vượt p theo mở rộng riêng, khi đó cần quy tắc khác. Hàm không thay thế giới hạn precision tối đa do từng DB hỗ trợ hoặc validation nghiệp vụ.

Ví dụ:

~~~java
BigDecimal a = DecimalNormalizer.forColumn(
        new BigDecimal("12.345"), 5, 2, RoundingMode.HALF_UP);
// a = 12.35, hợp lệ trong DECIMAL(5,2)

BigDecimal b = DecimalNormalizer.forColumn(
        new BigDecimal("999.995"), 5, 2, RoundingMode.HALF_UP);
// Ném IllegalArgumentException:
// 999.995 làm tròn thành 1000.00, vượt giới hạn 999.99.
~~~

Hai dòng trên là **minh họa gọi tiện ích ở trên**; dòng thứ hai cố ý phát sinh lỗi, nên không chạy tiếp như một chương trình mong đợi thành công. Nếu không cho phép tự làm tròn, truyền `RoundingMode.UNNECESSARY` và xử lý `ArithmeticException` khi đầu vào có chữ số lẻ thừa.

Đừng dựa duy nhất vào `value.precision() <= p` vì có thể bỏ sót giới hạn phần nguyên. Ngược lại, việc tăng scale bằng cách thêm các số 0 thập phân có thể làm `value.precision()` tăng mà **giá trị số không đổi**; điều quan trọng là khả năng biểu diễn ở `(p,s)` sau chuẩn hóa.

## 10. Demo Spring JDBC hoàn chỉnh với DECIMAL(8,2) và H2

Ví dụ dưới dùng **Java 17**, **Spring JDBC 6.1.14**, **H2 2.2.224** và Gradle. Nó thực hiện hai cách bind decimal: JDBC positional parameter với `setBigDecimal` và named parameter với `Types.DECIMAL`; sau đó đọc dữ liệu về bằng `getBigDecimal` để kiểm tra kết quả.

Tạo cấu trúc:

~~~text
decimal-jdbc-demo/
├── build.gradle
└── src/main/java/example/
    └── DecimalJdbcDemo.java
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.1.14'
    runtimeOnly 'com.h2database:h2:2.2.224'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.DecimalJdbcDemo'
}
~~~

File `src/main/java/example/DecimalJdbcDemo.java`:

~~~java
package example;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Types;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class DecimalJdbcDemo {
    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(
                "jdbc:h2:mem:decimal_lecture;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
                CREATE TABLE invoice_line (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    description VARCHAR(100) NOT NULL,
                    amount DECIMAL(8,2) NOT NULL
                )
                """);

        BigDecimal input = new BigDecimal("1234.567");
        BigDecimal normalized = input.setScale(
                2, RoundingMode.HALF_UP);

        int first = jdbc.update(
                "INSERT INTO invoice_line (description, amount) "
                + "VALUES (?, ?)",
                ps -> {
                    ps.setString(1, "positional");
                    ps.setBigDecimal(2, normalized);
                });

        NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(dataSource);
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("description", "named", Types.VARCHAR)
                .addValue("amount",
                        new BigDecimal("5.20"), Types.DECIMAL);

        int second = named.update(
                "INSERT INTO invoice_line (description, amount) "
                + "VALUES (:description, :amount)",
                params);

        List<BigDecimal> stored = jdbc.query(
                "SELECT amount FROM invoice_line ORDER BY id",
                (rs, rowNum) -> rs.getBigDecimal("amount"));

        System.out.printf(
                "input=%s precision=%d scale=%d%n",
                input.toPlainString(), input.precision(), input.scale());
        System.out.printf(
                "normalized=%s precision=%d scale=%d%n",
                normalized.toPlainString(),
                normalized.precision(), normalized.scale());
        System.out.println("updated=" + first + "," + second);
        System.out.println("db=" + stored.get(0).toPlainString()
                + "," + stored.get(1).toPlainString());
        System.out.println("db-scale=" + stored.get(0).scale()
                + "," + stored.get(1).scale());
    }
}
~~~

Chạy ở thư mục chứa `build.gradle` bằng Gradle đã cài:

~~~bash
gradle run
~~~

Nếu dự án đã có Gradle Wrapper: dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows. Với database H2 mới và đúng các phiên bản như trên, **stdout do chương trình tạo**:

~~~text
input=1234.567 precision=7 scale=3
normalized=1234.57 precision=6 scale=2
updated=1,1
db=1234.57,5.20
db-scale=2,2
~~~

Gradle còn in các log build riêng. H2 lưu cột `DECIMAL(8,2)` với scale hai và driver trả `BigDecimal` theo scale cột trong ví dụ này. Một driver/DB khác có thể thể hiện scale đọc về khác; do đó test tích hợp cần kiểm tra cả **giá trị số** lẫn **biểu diễn** theo yêu cầu thật.

**Vì sao code chạy được:** `DriverManagerDataSource` mở kết nối JDBC đến H2 in-memory; `DB_CLOSE_DELAY=-1` giữ database tồn tại giữa các kết nối mà `JdbcTemplate` sử dụng trong quá trình demo; Spring tự quản lý statement và chuyển ngoại lệ JDBC. `DriverManagerDataSource` ở đây phục vụ bài học, không phải lựa chọn connection pooling khuyến nghị cho production.

Chú ý rằng code tự chuẩn hóa giá trị `1234.567` thành `1234.57` **trước khi bind**. Nếu bỏ `setScale`, kết quả phụ thuộc quy tắc làm tròn/thông báo lỗi của DB. Khi chuyển từ H2 sang PostgreSQL, MySQL, Oracle hay SQL Server, hãy kiểm thử với driver và kiểu cột đang triển khai.

## 11. Đọc metadata của cột để kiểm chứng precision và scale

JDBC cho phép kiểm tra precision/scale mà driver báo về:

~~~java
List<String> metadata = jdbcTemplate.query(
        "SELECT amount FROM invoice_line WHERE 1 = 0",
        rs -> {
            var md = rs.getMetaData();
            return List.of(
                    "type=" + md.getColumnTypeName(1),
                    "precision=" + md.getPrecision(1),
                    "scale=" + md.getScale(1));
        });
~~~

Đây là **mảnh code trong DAO** đã có `jdbcTemplate` và bảng `invoice_line`; truy vấn không trả dòng dữ liệu nhưng vẫn có metadata của cột. `ResultSetMetaData.getPrecision(1)` và `getScale(1)` phản ánh metadata do driver cung cấp, có thể không đầy đủ hoặc khác với kỳ vọng đối với expression/`CAST`. Metadata của cột thực cũng có thể tra từ `DatabaseMetaData.getColumns(...)` (ví dụ `COLUMN_SIZE` và `DECIMAL_DIGITS`). Đừng dùng metadata đơn lẻ để thay thế schema migration hoặc test insert/round-trip.

Trong một dự án có schema cố định, quy tắc `(p,s)` của từng trường thường được xác định ở tầng domain/application và migrations. Nếu có nhiều DB đích, hãy lưu lại **DBMS, phiên bản driver, DDL và cách trả dữ liệu** trong báo cáo test để phát hiện khác biệt.

## 12. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `new BigDecimal(0.1)` ra nhiều chữ số lẻ | Đầu vào đã là `double` nhị phân | Tạo từ chuỗi thập phân chính xác hoặc đơn vị nguyên; tránh chuyển qua double |
| `ArithmeticException` khi `divide` | Thương không kết thúc hoặc cần làm tròn | Chỉ định scale và `RoundingMode` phù hợp |
| `ArithmeticException` khi `setScale(2)` | Không thể giảm scale mà vẫn chính xác | Chỉ định policy làm tròn hoặc dùng `UNNECESSARY` để chủ động từ chối |
| Database báo numeric overflow/out of range | Phần nguyên hoặc tổng độ dài sau làm tròn vượt `DECIMAL(p,s)` | Chuẩn hóa và kiểm tra sức chứa trước khi bind |
| Lưu `12.345` nhưng đọc `12.35` | DB/driver đã ép về scale cột | Làm tròn ở Java theo policy, kiểm thử trên DB thật |
| `equals` trả `false` với `2.0` và `2.00` | BigDecimal so thêm scale | Dùng `compareTo` cho so sánh số, hoặc thống nhất scale |
| Dữ liệu đọc về khác scale đầu vào | DB/driver chuẩn hóa cột decimal | Test giá trị và scale riêng; không dùng scale của input làm giả định |
| Kết quả có sai số sau khi xử lý API | Chuyển `BigDecimal` qua `double` hoặc JSON số bị client parse thành floating point | Giữ decimal chính xác qua các bước; xét chuỗi decimal ở biên có yêu cầu lossless |
| SQL `NULL` gây lỗi binding hoặc constraint | Driver thiếu SQL type hoặc cột `NOT NULL` | Dùng `Types.DECIMAL` khi cần, kiểm tra nullable và validation |
| Spring báo `DataAccessException` | JDBC driver/DB từ chối giá trị hoặc SQL | Xem nguyên nhân gốc và SQLState, schema, kiểu tham số, precision/scale |

**Không tự thử lại lệnh ghi chỉ vì phát sinh exception sau khi gửi tới database** nếu chưa biết kết quả transaction. Retry thiếu kiểm soát có thể tạo dữ liệu lặp. Với giao dịch nhiều dòng, đặt các thao tác trong transaction phù hợp; `BigDecimal` đúng kiểu không thay thế nguyên tắc nhất quán giao dịch.

## 13. Bộ kiểm thử cần có cho dữ liệu DECIMAL/NUMERIC

Khi thiết kế repository Spring JDBC, nên kiểm thử tối thiểu:

1. **Giá trị thường:** `123.45` vào `DECIMAL(8,2)`, đọc ra và `compareTo` bằng 0.
2. **Scale thấp hơn cột:** `12.3` vào `DECIMAL(8,2)`; ghi nhận scale được đọc về, không giả định nó luôn là 1 hoặc 2 trên mọi driver.
3. **Scale quá lớn:** `12.345`: kiểm tra policy ứng dụng (làm tròn thành `12.35` hoặc từ chối).
4. **Biên dương/âm:** `±999999.99` vừa với `DECIMAL(8,2)`; `±1000000.00` phải bị phát hiện vượt giới hạn.
5. **Carry do rounding:** `999999.995` làm tròn `HALF_UP` thành `1000000.00`, phải từ chối cho `DECIMAL(8,2)`.
6. **Zero và dấu âm:** `0`, `0.00`, `-0.00` sau chuẩn hóa có giá trị số 0; scale được xử lý nhất quán.
7. **Phép toán tỷ lệ:** kết quả nhân/chia, tie như `1.005` với `HALF_UP` và `HALF_EVEN`.
8. **NULL và sai kiểu:** bind nullable `DECIMAL` với `Types.DECIMAL`; xác nhận `NOT NULL` bị từ chối như schema quy định.
9. **Round-trip đúng DB đích:** thực thi cùng test trên database và driver thực tế, vì việc H2 pass không chứng minh hệ production sẽ có cùng biểu diễn/rounding.
10. **Tính nhất quán nghiệp vụ:** xác minh tổng hóa đơn khi làm tròn theo từng dòng so với làm tròn ở cấp tổng; assert chính sách đã chọn.

Khi so sánh nội dung số trong test, dùng `actual.compareTo(expected) == 0` để xác nhận cùng giá trị, và dùng assert riêng cho `actual.scale()` **chỉ khi scale là yêu cầu của hợp đồng dữ liệu**. Nếu muốn kiểm tra biểu diễn chính xác, có thể assert `toPlainString()` sau khi chuẩn hóa; đừng vô tình biến khác biệt scale hợp lệ giữa driver thành lỗi nghiệp vụ.

## 14. Checklist trước khi lưu dữ liệu thập phân

- **Kiểu nguồn:** tạo `BigDecimal` từ decimal string/nguồn số nguyên chính xác; tránh đi qua `double`.
- **Quy tắc nghiệp vụ:** xác định scale cho từng trường (tiền, thuế, tỷ lệ, đo lường có thể khác nhau) và `RoundingMode` hoặc chính sách từ chối.
- **Schema:** chọn `DECIMAL(p,s)`/`NUMERIC(p,s)` đủ phần nguyên và phần lẻ cho miền dữ liệu; không giả định mọi DB xử lý out-of-range giống nhau.
- **Thứ tự xử lý:** normalize scale, kiểm tra giới hạn sau rounding, rồi mới bind JDBC.
- **Spring JDBC:** truyền `BigDecimal`, `setBigDecimal` hoặc tham số có `Types.DECIMAL` khi cần; không ép sang float/double.
- **Readback:** dùng `getBigDecimal`/`BigDecimal.class`, so sánh numeric bằng `compareTo`, kiểm tra scale khi hợp đồng thật sự cần.
- **QA:** có unit test rounding và integration test với đúng DB/driver/schema production.

**Điểm cần nhớ:** `BigDecimal.precision()/scale()` mô tả *một giá trị Java*; `DECIMAL(p,s)` mô tả *khả năng lưu trữ của một cột SQL*. `setScale` áp dụng quy tắc làm tròn phần lẻ, `MathContext` giới hạn tổng chữ số có nghĩa, còn Spring JDBC truyền dữ liệu qua driver. Tầng ứng dụng cần quyết định độ chính xác, cách làm tròn và giới hạn trước khi dữ liệu được lưu.

## Tài liệu tham khảo

- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): định nghĩa unscaled value, scale, precision, phép toán, rounding và `equals`/`compareTo`.
- [Java SE 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): các chế độ làm tròn.
- [Java SE 21 — MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html): precision của phép toán và rounding policy.
- [Spring Framework — JDBC core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, binding tham số, cập nhật và mapping `ResultSet`.
- [Spring Framework — JDBC named parameters](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): `NamedParameterJdbcTemplate` và `MapSqlParameterSource`.
- [PostgreSQL — Numeric Types](https://www.postgresql.org/docs/current/datatype-numeric.html): ví dụ hành vi khai báo `NUMERIC(p,s)`, rounding và giới hạn cột (đặc thù PostgreSQL).
