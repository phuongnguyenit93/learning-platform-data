# BigDecimal, độ chính xác và quy tắc làm tròn

`java.math.BigDecimal` biểu diễn số thập phân có dấu với độ chính xác tùy ý (arbitrary precision). Đây là kiểu quan trọng khi tính tiền, thuế, tỷ lệ, đơn giá, số đo và những dữ liệu mà sai số nhị phân hoặc việc làm tròn không rõ ràng có thể làm thay đổi kết quả nghiệp vụ.

Tuy nhiên, dùng `BigDecimal` không tự động đảm bảo mọi phép tính đều đúng. Người lập trình vẫn phải quyết định:

- Tạo giá trị từ chuỗi thập phân hay từ `double`?
- `precision` và `scale` khác nhau thế nào?
- Hai số có cùng giá trị nhưng khác số chữ số thập phân có được coi là bằng nhau không?
- Khi chia ra số thập phân vô hạn, làm tròn ở đâu và theo quy tắc nào?
- Nên dùng `MathContext` hay `setScale(...)`?
- Có nên làm tròn sau từng phép toán hay giữ độ chính xác đến bước cuối?
- Làm sao để dữ liệu giữ nguyên quy tắc khi đi qua JDBC, JSON, Spring binding và cơ sở dữ liệu?

Bài này dùng Java 17+ để giải thích cơ chế số học, ví dụ chạy hoàn chỉnh, kết quả mong đợi và cách thiết kế quy tắc làm tròn trong ứng dụng.

## 1. Vì sao cần BigDecimal?

Các kiểu `float` và `double` lưu số dấu phẩy động theo biểu diễn nhị phân IEEE 754. Nhiều phân số thập phân hữu hạn không có biểu diễn nhị phân hữu hạn. Vì vậy, giá trị nhìn thấy là `0.1` không thể được lưu chính xác dưới dạng `double`.

~~~java
System.out.println(0.1 + 0.2);
~~~

Kết quả thường thấy:

~~~text
0.30000000000000004
~~~

Với nghiệp vụ tài chính, việc tích lũy sai lệch qua nhiều phép tính có thể gây chênh lệch số tiền. `BigDecimal` lưu giá trị bằng một số nguyên chưa scale (unscaled integer) và một scale, từ đó biểu diễn chính xác những số thập phân hữu hạn như `0.1`, `12.3400` hoặc `999999999999.99` mà không chuyển chúng qua dạng nhị phân dấu phẩy động.

Ví dụ:

~~~java
BigDecimal price = new BigDecimal("0.10");
BigDecimal tax = new BigDecimal("0.20");
BigDecimal total = price.add(tax);

System.out.println(total); // 0.30
~~~

Kết quả số học là chính xác và scale phù hợp với toán tử. `BigDecimal` không giới hạn số chữ số có nghĩa theo một định dạng cố định như `double`, nhưng vẫn có giới hạn thực tế về bộ nhớ, thời gian, scale kiểu `int` và kích thước dữ liệu.

**Quy tắc đầu tiên:** nếu nguồn dữ liệu vốn là số thập phân viết bằng chữ số, hãy tạo `BigDecimal` từ chính biểu diễn thập phân đó, thường là `String` hoặc `BigInteger` cùng scale.

## 2. Cấu trúc bên trong: unscaledValue và scale

Một `BigDecimal` được xác định bởi:

- `unscaledValue`: giá trị nguyên có dấu.
- `scale`: số chữ số thập phân, có thể dương, bằng 0 hoặc âm.

Công thức:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Ví dụ:

| Biểu diễn | Unscaled value | Scale | Giá trị |
| --- | ---: | ---: | ---: |
| `12.34` | 1234 | 2 | 1234 × 10⁻² |
| `12.3400` | 123400 | 4 | 123400 × 10⁻⁴ |
| `1234` | 1234 | 0 | 1234 |
| `1.23E+3` | 123 | -1 | 123 × 10¹ = 1230 |
| `0.00123` | 123 | 5 | 123 × 10⁻⁵ |

Có thể xem cấu trúc trực tiếp:

~~~java
BigDecimal amount = new BigDecimal("12.3400");

System.out.println(amount.unscaledValue()); // 123400
System.out.println(amount.scale());         // 4
System.out.println(amount.precision());     // 6
~~~

Một điểm quan trọng: **scale âm là hợp lệ**. Ví dụ `new BigDecimal("1.23E+3")` có thể có scale âm; không phải mọi `BigDecimal` đều có scale bằng số chữ số sau dấu chấm trong cách in thông thường.

`BigDecimal` là immutable (bất biến). Các phép toán như `add`, `multiply`, `setScale` và `round` trả về một `BigDecimal` mới; chúng không sửa object ban đầu. Vì thế phải gán lại kết quả:

~~~java
BigDecimal value = new BigDecimal("1.235");
value.setScale(2, RoundingMode.HALF_UP); // Bỏ kết quả: value vẫn là 1.235.

value = value.setScale(2, RoundingMode.HALF_UP); // value nay là 1.24.
~~~

## 3. Tạo BigDecimal đúng cách

### 3.1. Ưu tiên constructor nhận String

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("123.4500");
BigDecimal c = new BigDecimal("-0.005");
~~~

`String` cho phép `BigDecimal` phân tích trực tiếp biểu diễn thập phân. `new BigDecimal("0.1")` tạo đúng giá trị thập phân một phần mười, với scale 1.

Đây là cách phù hợp khi đọc từ form, file CSV, cấu hình, cơ sở dữ liệu hoặc một API có contract biểu diễn số dạng chuỗi.

### 3.2. Tránh constructor BigDecimal(double) cho giá trị thập phân cần chính xác

~~~java
BigDecimal wrong = new BigDecimal(0.1);
System.out.println(wrong);
~~~

Kết quả thể hiện chính xác giá trị nhị phân `double` đã nhận, không phải giá trị thập phân mà người đọc thường kỳ vọng:

~~~text
0.1000000000000000055511151231257827021181583404541015625
~~~

Nguyên nhân không phải `BigDecimal` làm tròn sai. Constructor này chuyển **chính xác giá trị double nhị phân** sang dạng thập phân chính xác của giá trị đó. Bản thân double đã không biểu diễn đúng một phần mười.

### 3.3. Khi bắt buộc nhận double, cân nhắc valueOf

~~~java
BigDecimal value = BigDecimal.valueOf(0.1);
System.out.println(value); // 0.1
~~~

`BigDecimal.valueOf(double)` chuyển từ biểu diễn chuỗi chuẩn của `Double.toString(double)`. Cách này thường cho kết quả mà người dùng mong đợi hơn constructor trực tiếp `new BigDecimal(double)`.

Dù vậy, nếu nguồn đầu vào vốn là chữ số thập phân, **không nên chuyển qua double trước rồi mới gọi valueOf**. Đường đi tốt hơn là đọc String ngay từ đầu.

### 3.4. Không dùng new BigDecimal(float) để lưu tiền

~~~java
float rate = 0.1f;
BigDecimal value = new BigDecimal(rate);
~~~

`float` có độ chính xác thấp hơn `double`; sai lệch đã xuất hiện trước khi tạo `BigDecimal`. `valueOf` không có overload nhận `float`; ép sang double cũng chỉ mở rộng giá trị float đã được lưu, không khôi phục số thập phân ban đầu.

### 3.5. Giá trị phải được kiểm tra trước khi tạo

Chuỗi rỗng hoặc không phải số có thể ném `NumberFormatException`:

~~~java
BigDecimal amount = new BigDecimal("abc"); // NumberFormatException
~~~

Trong code nhận input, cần kiểm tra/để converter báo lỗi rõ ràng; không mặc định thay mọi dữ liệu sai bằng 0. **Thiếu dữ liệu**, **giá trị bằng 0** và **giá trị không parse được** là ba trạng thái khác nhau.

## 4. Precision và scale: hai khái niệm không giống nhau

`precision()` trả về số chữ số trong unscaled value; với giá trị khác 0, nó là số chữ số có nghĩa của biểu diễn thập phân. Precision của số 0 là 1.

`scale()` mô tả số chữ số ở bên phải dấu thập phân theo biểu diễn nội bộ; scale dương là số chữ số thập phân, scale 0 không có phần lẻ, scale âm biểu diễn bội của lũy thừa 10.

Ví dụ:

~~~java
BigDecimal a = new BigDecimal("123.45");
BigDecimal b = new BigDecimal("123.4500");
BigDecimal c = new BigDecimal("1000");
BigDecimal d = new BigDecimal("1.23E+3");

System.out.println(a.precision() + "/" + a.scale()); // 5/2
System.out.println(b.precision() + "/" + b.scale()); // 7/4
System.out.println(c.precision() + "/" + c.scale()); // 4/0
System.out.println(d.precision() + "/" + d.scale()); // 3/-1
~~~

| Giá trị | Precision | Scale |
| --- | ---: | ---: |
| `123.45` | 5 | 2 |
| `123.4500` | 7 | 4 |
| `1000` | 4 | 0 |
| `1.23E+3` | 3 | -1 |

Hai giá trị đầu tiên bằng nhau về số học nhưng khác precision/scale và khác representation. Điều này rất quan trọng khi so sánh, lưu dữ liệu, serialize hoặc kiểm tra schema `DECIMAL(p,s)` trong database.

### DECIMAL(p,s) trong cơ sở dữ liệu

Thông thường:

- `p` là precision tối đa (số chữ số tổng thể).
- `s` là scale được khai báo (số chữ số sau dấu thập phân).

Ví dụ `DECIMAL(12,2)` dành tối đa 12 chữ số, trong đó 2 chữ số ở phần thập phân, tức còn tối đa 10 chữ số phần nguyên. Giá trị vượt phạm vi có thể bị từ chối hoặc chuyển đổi theo hành vi của database/driver.

`BigDecimal` trong Java không tự buộc mọi giá trị có scale 2. Ứng dụng nên kiểm tra và chuẩn hóa ở ranh giới domain/persistence theo contract, thay vì để database âm thầm xử lý rounding mà code Java không biết.

## 5. Equals và compareTo: bằng nhau theo hai nghĩa

`BigDecimal.equals(Object)` so sánh **giá trị và biểu diễn (scale)**. `compareTo(BigDecimal)` so sánh giá trị số học.

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));         // false
System.out.println(a.compareTo(b) == 0); // true
~~~

Cùng biểu diễn số một, nhưng `1.0` có scale 1 và `1.00` có scale 2. Vì thế:

- Dùng `compareTo(...) == 0` khi muốn so sánh hai số theo giá trị toán học.
- Dùng `equals(...)` khi scale cũng là một phần của ý nghĩa representation.
- Cẩn thận khi dùng `BigDecimal` làm key của `HashMap`/`HashSet`: `equals` và `hashCode` có xét scale, nên `1.0` và `1.00` là hai key khác nhau.

Nếu domain coi `1.0` và `1.00` giống nhau, hãy chuẩn hóa representation theo quy tắc nhất quán trước khi dùng làm key hoặc so sánh. Ví dụ `stripTrailingZeros()` có thể chuẩn hóa số 0 thập phân, nhưng kết quả có thể mang scale âm; đừng giả định nó luôn trả về scale 0 hoặc 2.

## 6. Các phép toán cơ bản và scale kết quả

`BigDecimal` hỗ trợ phép toán số học chính xác:

~~~java
BigDecimal a = new BigDecimal("10.25");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.add(b));      // 12.25
System.out.println(a.subtract(b)); // 8.25
System.out.println(a.multiply(b)); // 20.5000
~~~

Scale ưu tiên của các kết quả chính xác theo quy tắc:

| Phép toán | Scale ưu tiên |
| --- | --- |
| `add` | Giá trị lớn hơn giữa scale hai toán hạng |
| `subtract` | Giá trị lớn hơn giữa scale hai toán hạng |
| `multiply` | Tổng scale của hai toán hạng |
| `divide` | Scale của số bị chia trừ scale của số chia (trong kết quả chính xác nếu phù hợp) |

Vì `multiply` cộng scale, `10.25` (scale 2) nhân `2.00` (scale 2) cho representation `20.5000` (scale 4). Đây không phải lỗi; nó bảo toàn thông tin scale theo phép toán.

**Không tự động làm tròn sau mỗi phép cộng/nhân.** Các phép toán không nhận `MathContext` thường tính chính xác kết quả và giữ scale theo quy tắc ưu tiên. Quyết định giảm scale nên được đặt tại ranh giới nghiệp vụ đã thống nhất, ví dụ khi chốt số tiền cần thanh toán.

## 7. Chia số thập phân: vì sao có ArithmeticException?

Một số phép chia có kết quả thập phân hữu hạn:

~~~java
new BigDecimal("1").divide(new BigDecimal("4")); // 0.25
~~~

Nhưng `1 / 3` có khai triển thập phân vô hạn tuần hoàn. `BigDecimal` không tự chọn số chữ số để cắt kết quả, vì việc lựa chọn đó là quyết định nghiệp vụ:

~~~java
new BigDecimal("1").divide(new BigDecimal("3"));
// ArithmeticException: Non-terminating decimal expansion
~~~

Cần truyền quy tắc scale/rounding hoặc precision context:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal byScale = one.divide(
        three, 2, RoundingMode.HALF_UP);

BigDecimal byContext = one.divide(
        three, new MathContext(4, RoundingMode.HALF_UP));

System.out.println(byScale);   // 0.33
System.out.println(byContext); // 0.3333
~~~

Hai kết quả khác nhau vì quy tắc khác nhau:

- `divide(divisor, 2, roundingMode)` cố định **scale 2**, tức hai chữ số sau dấu thập phân.
- `divide(divisor, MathContext(4, ...))` giới hạn **precision 4 chữ số có nghĩa**, không phải bốn chữ số sau dấu thập phân.

Không chọn overload chỉ vì nó ngắn hơn. Phải xác định yêu cầu là số chữ số thập phân cố định hay số chữ số có nghĩa cố định.

### Chia với scale hiện tại

~~~java
a.divide(b, RoundingMode.HALF_UP)
~~~

Overload này sử dụng scale của `this` làm scale kết quả. Trong nhiều bài toán tiền tệ, dùng overload có scale tường minh dễ đọc và ít gây nhầm hơn.

### Chia cho 0

`BigDecimal` không biểu diễn vô cực như một số float. Chia cho zero ném `ArithmeticException`. Hãy xác thực divisor trước khi tính hoặc để tầng gọi chuyển exception thành lỗi nghiệp vụ phù hợp.

## 8. RoundingMode: tám cách xử lý chữ số bị bỏ

`java.math.RoundingMode` có tám mode. Chọn sai mode có thể gây sai số có hệ thống hoặc vi phạm quy định tài chính.

| RoundingMode | Quy tắc |
| --- | --- |
| `UP` | Làm tròn ra xa 0; có chữ số bị bỏ khác 0 thì tăng độ lớn. |
| `DOWN` | Cắt về phía 0; bỏ phần dư. |
| `CEILING` | Làm tròn hướng lên về dương vô cực; với số âm có thể là gần 0 hơn. |
| `FLOOR` | Làm tròn hướng xuống về âm vô cực; với số âm có thể xa 0 hơn. |
| `HALF_UP` | Gần nhất; trường hợp đúng giữa hai giá trị thì đi xa 0. |
| `HALF_DOWN` | Gần nhất; trường hợp đúng giữa thì đi về gần 0. |
| `HALF_EVEN` | Gần nhất; trường hợp đúng giữa thì chọn chữ số cuối cùng chẵn (banker's rounding). |
| `UNNECESSARY` | Không cho phép làm tròn; nếu phải bỏ thông tin thì ném `ArithmeticException`. |

### Ví dụ số dương và số âm

Với scale 2:

~~~java
new BigDecimal("2.345").setScale(2, RoundingMode.HALF_UP);   // 2.35
new BigDecimal("2.345").setScale(2, RoundingMode.HALF_EVEN); // 2.34
new BigDecimal("-2.345").setScale(2, RoundingMode.HALF_UP);  // -2.35
new BigDecimal("-2.345").setScale(2, RoundingMode.DOWN);     // -2.34
new BigDecimal("-2.345").setScale(2, RoundingMode.FLOOR);    // -2.35
~~~

`HALF_EVEN` không phải lúc nào cũng “làm tròn xuống”. Nó chọn kết quả gần nhất; chỉ khi nằm đúng giữa hai lựa chọn mới chọn giá trị có chữ số cuối cùng chẵn. Cách này có thể giảm bias tích lũy khi xử lý số lượng lớn phép tính, nhưng chỉ dùng khi quy định nghiệp vụ cho phép.

### Ví dụ kiểm tra HALF_EVEN ở hai phía

~~~java
System.out.println(
        new BigDecimal("2.345").setScale(2, RoundingMode.HALF_EVEN));
System.out.println(
        new BigDecimal("2.355").setScale(2, RoundingMode.HALF_EVEN));
~~~

Kết quả:

~~~text
2.34
2.36
~~~

Trong trường hợp thứ nhất, chữ số giữ lại cuối cùng là 4 (chẵn), còn trường hợp thứ hai là 5 (lẻ), nên kết quả thứ hai được tăng thành 6.

### UNNECESSARY để phát hiện sai scale

~~~java
BigDecimal value = new BigDecimal("12.340");
BigDecimal exact = value.setScale(2, RoundingMode.UNNECESSARY);
System.out.println(exact); // 12.34
~~~

Việc giảm scale từ 3 xuống 2 không làm thay đổi giá trị vì chữ số bị bỏ là 0. Nhưng:

~~~java
new BigDecimal("12.345")
        .setScale(2, RoundingMode.UNNECESSARY);
~~~

sẽ ném `ArithmeticException` vì phải bỏ chữ số khác 0. Điều này hữu ích khi contract yêu cầu giá trị phải có tối đa hai chữ số thập phân và ứng dụng muốn **từ chối** dữ liệu vượt scale thay vì tự làm tròn.

## 9. MathContext: precision và rounding cho phép toán

`MathContext` đóng gói hai thiết lập:

- `precision`: số chữ số có nghĩa của kết quả.
- `roundingMode`: quy tắc làm tròn nếu kết quả chính xác có quá nhiều chữ số.

Ví dụ:

~~~java
MathContext mc = new MathContext(5, RoundingMode.HALF_EVEN);

BigDecimal result = new BigDecimal("123.4567").round(mc);
System.out.println(result); // 123.46
~~~

Precision 5 có nghĩa giữ 5 chữ số có nghĩa, không phải scale 5. Kết quả `123.46` có precision 5 và scale 2.

`MathContext.DECIMAL32`, `DECIMAL64` và `DECIMAL128` là các cấu hình hữu ích tương ứng với precision thập phân chuẩn; nhưng chúng không tự đặt giới hạn scale kiểu database. Đối với tiền cần hai chữ số sau dấu thập phân, `setScale(2, ...)` diễn đạt yêu cầu trực tiếp hơn là dùng `MathContext(2, ...)`.

### MathContext.UNLIMITED

`MathContext.UNLIMITED` có precision bằng 0. Đây là phép toán không giới hạn precision và dùng tính toán chính xác khi có biểu diễn hữu hạn. Với phép chia không có khai triển thập phân hữu hạn, nó vẫn không tự tạo ra chuỗi vô hạn; kết quả không thể biểu diễn chính xác sẽ gây `ArithmeticException`.

### Áp dụng MathContext trong từng phép toán

~~~java
MathContext mc = new MathContext(6, RoundingMode.HALF_EVEN);

BigDecimal a = new BigDecimal("123.456");
BigDecimal b = new BigDecimal("7.89");

BigDecimal sum = a.add(b, mc);
BigDecimal product = a.multiply(b, mc);
BigDecimal quotient = a.divide(b, mc);
~~~

Khi truyền context, từng phép toán tạo kết quả theo precision/rounding đã chọn. Điều đó có nghĩa nếu dùng context ở mọi bước, sai lệch do rounding trung gian có thể khác với cách tính chính xác các bước rồi làm tròn ở cuối. Lựa chọn nào đúng phụ thuộc quy tắc kế toán/định giá đang áp dụng.

## 10. setScale, round và stripTrailingZeros

Ba API này thường bị dùng lẫn:

### setScale

Dùng khi cần số chữ số thập phân cụ thể:

~~~java
BigDecimal price = new BigDecimal("19.987");
BigDecimal amount = price.setScale(2, RoundingMode.HALF_UP);

System.out.println(amount); // 19.99
~~~

### round(MathContext)

Dùng khi cần số chữ số có nghĩa cụ thể:

~~~java
BigDecimal value = new BigDecimal("12345.67");
BigDecimal rounded = value.round(
        new MathContext(4, RoundingMode.HALF_UP));

System.out.println(rounded); // 1.235E+4
~~~

Khi hiển thị, nếu muốn không dùng scientific notation, có thể dùng `toPlainString()`; đừng biến việc format output thành phép tính hoặc rounding mới.

### stripTrailingZeros

Dùng khi muốn bỏ các số 0 thập phân ở cuối mà không thay đổi giá trị:

~~~java
BigDecimal value = new BigDecimal("12.3400");
BigDecimal stripped = value.stripTrailingZeros();

System.out.println(stripped); // 12.34
System.out.println(stripped.scale()); // 2
~~~

Với `1000`, `stripTrailingZeros()` có thể tạo representation scale âm, ví dụ số được biểu diễn theo dạng scientific. Nếu muốn chuỗi thông thường, dùng `toPlainString()`; nếu muốn scale cố định (ví dụ hai chữ số), dùng `setScale(2, ...)` thay vì `stripTrailingZeros()`.

## 11. Ví dụ Java 17+ hoàn chỉnh: tính tiền, VAT và làm tròn

Chương trình sau chạy không cần thư viện bên ngoài. Nó minh họa:

- Tạo số tiền từ chuỗi.
- Nhân số lượng với đơn giá.
- Tính VAT theo tỷ lệ.
- Làm tròn số tiền đến hai chữ số bằng `HALF_EVEN`.
- So sánh `equals` và `compareTo`.
- Phân biệt constructor nhận double với `valueOf`.
- Chia số thập phân vô hạn với scale tường minh.

### Cấu trúc

~~~text
bigdecimal-demo/
└── BigDecimalDemo.java
~~~

### BigDecimalDemo.java

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalDemo {

    private static BigDecimal money(BigDecimal value) {
        return value.setScale(2, RoundingMode.HALF_EVEN);
    }

    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.99");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal vatRate = new BigDecimal("0.10");

        BigDecimal subtotal = unitPrice.multiply(quantity);
        BigDecimal vatExact = subtotal.multiply(vatRate);
        BigDecimal vat = money(vatExact);
        BigDecimal total = money(subtotal.add(vat));

        System.out.println("subtotal=" + subtotal.toPlainString());
        System.out.println("vatExact=" + vatExact.toPlainString());
        System.out.println("vatRounded=" + vat.toPlainString());
        System.out.println("total=" + total.toPlainString());

        BigDecimal first = new BigDecimal("1.0");
        BigDecimal second = new BigDecimal("1.00");

        System.out.println("equals=" + first.equals(second));
        System.out.println("compareTo="
                + (first.compareTo(second) == 0));

        System.out.println("fromString="
                + new BigDecimal("0.1").toPlainString());
        System.out.println("fromDouble="
                + new BigDecimal(0.1).toPlainString());
        System.out.println("fromValueOf="
                + BigDecimal.valueOf(0.1).toPlainString());

        BigDecimal third = BigDecimal.ONE.divide(
                new BigDecimal("3"),
                4,
                RoundingMode.HALF_UP);
        System.out.println("oneThird=" + third.toPlainString());

        BigDecimal significant = new BigDecimal("12345.67").round(
                new MathContext(4, RoundingMode.HALF_UP));
        System.out.println("fourSignificantDigits="
                + significant.toPlainString());
    }
}
~~~

### Biên dịch và chạy

JDK 17+:

~~~bash
javac BigDecimalDemo.java
java BigDecimalDemo
~~~

Stdout chính xác:

~~~text
subtotal=59.97
vatExact=5.9970
vatRounded=6.00
total=65.97
equals=false
compareTo=true
fromString=0.1
fromDouble=0.1000000000000000055511151231257827021181583404541015625
fromValueOf=0.1
oneThird=0.3333
fourSignificantDigits=12350
~~~

Giải thích:

1. `19.99 × 3 = 59.97` được tính chính xác. Do scale của hai toán hạng là 2 và 0, kết quả có scale 2.
2. VAT là `59.97 × 0.10 = 5.9970`. Đây là kết quả chính xác, scale 4 do nhân hai scale.
3. `money(...)` áp dụng quy tắc làm tròn hai chữ số bằng `HALF_EVEN`. `5.9970` thành `6.00`.
4. Tổng `59.97 + 6.00 = 65.97`, được chuẩn hóa hai chữ số.
5. `1.0` và `1.00` có cùng giá trị số học nhưng khác representation; `equals` trả false, còn `compareTo == 0` trả true.
6. Constructor double bộc lộ chính xác giá trị double nhị phân; `String` và `valueOf` trong ví dụ đều tạo giá trị thập phân 0.1.
7. `1 / 3` được làm tròn đến scale 4 thành `0.3333`.
8. `MathContext(4, HALF_UP)` giữ bốn chữ số có nghĩa của `12345.67`, tạo giá trị tương đương 12350; `toPlainString()` in ra dạng không scientific.

Đây là chương trình chạy độc lập, không cần Maven, Spring hay database. Nếu thay đổi scale, rounding mode hoặc đầu vào, stdout cũng thay đổi theo quy tắc tương ứng.

## 12. Chọn làm tròn ở đâu trong một quy trình nghiệp vụ?

Một quyết định quan trọng không kém mode làm tròn là **thời điểm làm tròn**. Không nên làm tròn mọi giá trị trung gian một cách tùy tiện.

Ví dụ bán hàng:

~~~text
Đơn giá × số lượng
        |
        v
  Thành tiền từng dòng
        |
        v
  Chiết khấu / thuế
        |
        v
  Tổng đơn hàng
        |
        v
  Làm tròn theo quy tắc thanh toán
~~~

Có ít nhất hai chính sách thường gặp:

- **Làm tròn từng dòng:** tính thành tiền/thuế cho từng dòng rồi cộng các kết quả đã làm tròn.
- **Cộng chính xác rồi làm tròn tổng:** giữ độ chính xác từng dòng, cộng các giá trị, chỉ làm tròn ở mức tổng.

Hai cách có thể cho kết quả khác nhau. Không có một cách đúng cho mọi hệ thống; phải theo hợp đồng tài chính, quy định thuế, quốc gia/đồng tiền và cách đối tác đối soát. Ghi rõ quy tắc để frontend, backend, báo cáo và database không làm tròn khác nhau.

### Tiền tệ không phải lúc nào cũng có hai chữ số thập phân

Một số loại tiền có số chữ số fraction khác nhau, và quy tắc làm tròn khi thanh toán tiền mặt có thể khác quy tắc ghi sổ. Không nên hard-code `setScale(2)` cho mọi currency nếu ứng dụng hỗ trợ nhiều loại tiền. Dùng metadata tiền tệ (ví dụ `Currency.getDefaultFractionDigits()` nếu phù hợp với chính sách) và cấu hình nghiệp vụ cụ thể; vẫn cần phân biệt số chữ số ghi sổ với bước làm tròn tiền mặt.

### Chiết khấu và tỷ lệ

Tỷ lệ phần trăm có thể cần precision cao hơn đơn vị tiền:

~~~java
BigDecimal discountRate = new BigDecimal("0.075");
BigDecimal discount = subtotal.multiply(discountRate);
~~~

Đừng làm tròn `discountRate` xuống hai chữ số thập phân nếu tỷ lệ 7.5% cần được giữ chính xác. Thường giữ độ chính xác cho tỷ lệ, tính số tiền chiết khấu rồi làm tròn theo đơn vị tiền ở điểm đã quy định.

## 13. BigDecimal với dữ liệu đầu vào, database và JSON

### 13.1. Input từ form/API

Khi người dùng nhập số dạng chuỗi, chuyển trực tiếp:

~~~java
BigDecimal amount = new BigDecimal(rawAmount);
~~~

Trong Spring MVC, một converter mặc định có thể hỗ trợ String sang BigDecimal; với quy tắc riêng, có thể đăng ký converter hoặc validator. Phải xử lý `NumberFormatException`/binding error, không thay dữ liệu sai bằng zero.

### 13.2. JDBC và DECIMAL/NUMERIC

JDBC có các API như `PreparedStatement.setBigDecimal(...)` và `ResultSet.getBigDecimal(...)`:

~~~java
preparedStatement.setBigDecimal(1, amount);
BigDecimal loaded = resultSet.getBigDecimal("amount");
~~~

Dùng cột `DECIMAL(p,s)` hoặc `NUMERIC(p,s)` phù hợp với giới hạn domain. Kiểm tra overflow và scale trước khi ghi, vì database có thể từ chối hoặc áp dụng chuyển đổi theo engine/configuration. Không chỉ dựa vào việc Java object tạo thành công để kết luận dữ liệu phù hợp schema.

### 13.3. JSON number và string

JSON có token number, nhưng các framework có thể parse qua kiểu trung gian và cấu hình khác nhau. Nếu cần bảo toàn chính xác decimal, hãy cấu hình serializer/deserializer để ánh xạ trực tiếp sang `BigDecimal` và kiểm thử round-trip. Với những API cần giữ chính xác representation (ví dụ số chữ số thập phân do người dùng gửi), có thể chọn contract chuỗi có kiểm soát:

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

Chuỗi giúp giữ representation `1234.50` nguyên vẹn qua bước truyền; tuy nhiên, cần validation format và độ dài. Nếu contract chọn JSON number, không được để client JavaScript chuyển qua `Number` (IEEE 754 double) với giá trị quá lớn hoặc precision vượt khả năng biểu diễn của nó rồi mong backend khôi phục số ban đầu.

## 14. Các lỗi phổ biến

1. **Dùng `new BigDecimal(0.1)`:** chuyển chính xác giá trị double nhị phân, thường tạo phần dư dài. Dùng chuỗi thập phân hoặc `BigDecimal.valueOf` khi nguồn thực sự là double.
2. **Dùng double trong một đoạn tính toán tiền:** sai lệch đã tích lũy trước khi chuyển sang BigDecimal; đổi kiểu ở cuối không sửa được.
3. **Nhầm precision với scale:** `MathContext(2, ...)` có hai chữ số có nghĩa, không phải hai chữ số sau dấu thập phân. Dùng `setScale(2, ...)` nếu cần hai chữ số lẻ.
4. **Dùng equals để so sánh giá trị:** `1.0` không equals `1.00`. Dùng `compareTo == 0` nếu chỉ quan tâm giá trị số học.
5. **Chia mà không xác định rounding:** `1/3` không có kết quả thập phân hữu hạn; overload exact ném `ArithmeticException`. Chọn scale hoặc MathContext rõ ràng.
6. **Dùng rounding mode không phù hợp:** `DOWN` là hướng về zero, không đồng nghĩa với `FLOOR`; với số âm hai mode có thể khác.
7. **Làm tròn ở mỗi bước mà không có quy định:** rounding trung gian có thể tích lũy và làm tổng khác với cách làm tròn cuối.
8. **Quên gán kết quả của setScale:** `BigDecimal` immutable, nên lời gọi không thay đổi biến cũ.
9. **Giả định mọi currency có scale 2:** dữ liệu tiền tệ và quy tắc thanh toán cần metadata/policy phù hợp.
10. **Dùng stripTrailingZeros rồi giả định scale luôn không âm:** kết quả có thể có scale âm; dùng `toPlainString` để in và `setScale` khi contract yêu cầu scale cố định.
11. **Làm tròn âm mà không test:** HALF_UP, DOWN, FLOOR và CEILING có ý nghĩa khác nhau với số âm.
12. **Lưu BigDecimal không kiểm tra database precision/scale:** giá trị có thể vượt `DECIMAL(p,s)` hoặc mất độ chính xác ở ranh giới persistence.
13. **Nhầm canConvert/parse thành validation nghiệp vụ:** parse thành BigDecimal chỉ xác nhận biểu diễn số; vẫn cần kiểm tra min/max, scale và quy tắc domain.
14. **Dùng chuỗi scientific notation ngoài contract:** `BigDecimal` có thể chấp nhận exponent, nhưng giao diện/API có thể không muốn định dạng này. Validate format theo contract thay vì dựa mặc định của constructor.

## 15. Checklist thiết kế số thập phân

Trước khi đưa `BigDecimal` vào một use case:

- Xác định nguồn dữ liệu và cách tạo object; ưu tiên `String`, tránh double trung gian.
- Định nghĩa miền giá trị, precision tối đa và scale cho từng trường.
- Phân biệt equality theo giá trị (`compareTo`) với equality representation (`equals`).
- Xác định phép toán nào phải chính xác, phép chia nào cần làm tròn.
- Chọn rounding mode theo quy tắc nghiệp vụ/pháp lý và ghi rõ ở code.
- Xác định làm tròn theo từng dòng, từng khoản thuế hay trên tổng.
- Đặt rounding ở ranh giới có ý nghĩa; tránh làm tròn tùy tiện ở mọi bước.
- Kiểm thử cả số âm, số 0, giá trị tie, số có trailing zero, chia cho zero và quotient vô hạn.
- Kiểm tra tương thích với `DECIMAL(p,s)`, JSON và frontend.
- Ghi rõ đơn vị và currency cùng giá trị; `BigDecimal` chỉ biểu diễn số, không mang theo đơn vị tiền.

**Ghi nhớ:** `BigDecimal` cung cấp số học thập phân chính xác và cho phép kiểm soát làm tròn; trách nhiệm chọn precision, scale, rounding mode và thời điểm làm tròn vẫn thuộc về thiết kế ứng dụng.

### Tài liệu tham khảo chính thức

- [Java SE 17 — BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE 17 — RoundingMode API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html)
- [Java SE 17 — MathContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html)
- [Java SE 17 — Currency API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html)
- [JDBC — PreparedStatement.setBigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html#setBigDecimal(int,java.math.BigDecimal))
