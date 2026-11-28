# BigDecimal, scale và chính sách làm tròn

Trong Java 27, `BigDecimal` thuộc gói `java.math` là kiểu số thập phân có độ chính xác tùy ý, phù hợp khi cần kiểm soát chính xác giá trị và **quy tắc làm tròn**: tính giá, thuế, chiết khấu, số lượng đo lường hoặc đối soát. Khác với `double`, `BigDecimal` biểu diễn số dưới dạng **số nguyên chưa chia tỷ lệ** (*unscaled value*) và **scale**, nhờ đó các phép toán thập phân có thể cho kết quả chính xác khi kết quả toán học có biểu diễn thập phân hữu hạn.

Tuy nhiên, chỉ đổi `double` thành `BigDecimal` **không tự bảo đảm tính đúng đắn nghiệp vụ**. Một hệ thống vẫn có thể sai nếu làm tròn quá sớm, chọn sai `RoundingMode`, dùng không nhất quán `scale`, cộng các số tiền khác đơn vị hoặc lẫn lộn so sánh theo giá trị với so sánh bằng `equals()`.

Bài này hướng dẫn cách dùng `BigDecimal`, `MathContext` và `RoundingMode` đang được hỗ trợ trong Java 27, đồng thời xây dựng một chính sách tính toán minh bạch có thể kiểm tra bằng bài tập và ví dụ hoàn chỉnh.

## 1. Khi nào chọn BigDecimal thay vì double?

Các kiểu `float` và `double` dùng biểu diễn nhị phân dấu phẩy động theo IEEE 754. Một số phân số thập phân quen thuộc, chẳng hạn `0.1`, **không có biểu diễn nhị phân hữu hạn**, nên các phép toán có thể xuất hiện sai số:

```java
double result = 0.1 + 0.2;
System.out.println(result);        // 0.30000000000000004
System.out.println(result == 0.3); // false
```

Với các giá trị tạo từ chuỗi thập phân, `BigDecimal` không mang sai số chuyển đổi nhị phân này:

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

BigDecimal sum = a.add(b);

System.out.println(sum.toPlainString()); // 0.3
System.out.println(sum.compareTo(new BigDecimal("0.3")) == 0); // true
```

| Tiêu chí | `double` | `BigDecimal` |
|---|---|---|
| Cơ chế biểu diễn | Nhị phân dấu phẩy động, độ chính xác hữu hạn | Số nguyên không chia tỷ lệ + scale thập phân |
| Khả năng lưu chính xác `0.1` | Không, ở dạng số nhị phân | Có, khi tạo từ `"0.1"` |
| Tốc độ và chi phí | Nhìn chung nhanh, ít bộ nhớ | Tốn thêm cấp phát và xử lý |
| Phép toán | Toán tử `+`, `-`, `*`, `/` | Phương thức `add`, `subtract`, `multiply`, `divide` |
| Chính sách làm tròn | Theo phép toán dấu phẩy động và API cụ thể | Chỉ định `RoundingMode` và `MathContext` |
| Trường hợp thường phù hợp | Khoa học, đồ họa, mô phỏng chấp nhận sai số | Tài chính, đo lường thập phân, đối soát theo chính sách |

`BigDecimal` không phải giải pháp mặc định cho mọi phép tính. Với dữ liệu cảm biến hoặc mô phỏng mà hiệu năng và mô hình sai số nhị phân là phù hợp, `double` vẫn là lựa chọn có lý. Với tiền tệ cần số chữ số thập phân theo hợp đồng nghiệp vụ, `BigDecimal` thường thích hợp hơn.

## 2. BigDecimal lưu giá trị bằng unscaledValue và scale

Một `BigDecimal` được mô tả bằng:

```text
giá trị = unscaledValue × 10^(-scale)
```

- `unscaledValue()` trả về một `BigInteger`.
- `scale()` là số nguyên `int`, mô tả số chữ số sau dấu thập phân khi scale không âm.
- `precision()` là số chữ số thập phân trong phần unscaled value, **không** đồng nghĩa với scale.

Ví dụ:

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount.unscaledValue()); // 1234500
System.out.println(amount.scale());         // 4
System.out.println(amount.precision());     // 7
System.out.println(amount.toPlainString()); // 123.4500
```

Cùng giá trị số học có thể có nhiều biểu diễn:

| Biểu thức tạo | Unscaled value | Scale | Precision | Giá trị |
|---|---:|---:|---:|---|
| `new BigDecimal("12.3")` | 123 | 1 | 3 | 12.3 |
| `new BigDecimal("12.30")` | 1230 | 2 | 4 | 12.30 |
| `new BigDecimal("0.005")` | 5 | 3 | 1 | 0.005 |
| `BigDecimal.valueOf(12345, 2)` | 12345 | 2 | 5 | 123.45 |
| `new BigDecimal("1E+3")` | 1 | -3 | 1 | 1000 |

**Scale có thể âm.** Chẳng hạn `1E+3` nghĩa là `1 × 10³`, tương ứng với scale `-3`. Đừng coi scale luôn là “số chữ số sau dấu phẩy” theo nghĩa trực quan nếu có ký pháp khoa học hoặc sau bước loại số 0 ở cuối.

### Precision và scale là hai khái niệm khác nhau

- `scale = 2` nói về **vị trí dấu thập phân**: `123.45` có scale 2.
- `precision = 5` nói về **số chữ số có nghĩa được giữ**: `123.45` có precision 5.
- Một số có thể có precision cao và scale nhỏ, hoặc scale cao nhưng precision rất thấp: `0.00001` có scale 5 và precision 1.

Hai khái niệm này dẫn đến hai kiểu làm tròn khác nhau: **`setScale`** cố định số chữ số thập phân; **`MathContext`** giới hạn tổng số chữ số có nghĩa.

## 3. Khởi tạo BigDecimal an toàn

Cách tạo `BigDecimal` ảnh hưởng trực tiếp đến giá trị được lưu.

### Ưu tiên chuỗi thập phân khi nguồn là số thập phân

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.10");
BigDecimal quantity = BigDecimal.valueOf(3);

System.out.println(price.multiply(quantity)); // 59.97
```

Dùng `new BigDecimal("19.99")` khi dữ liệu đầu vào là chuỗi thập phân, hoặc `BigDecimal.valueOf(long)` cho số nguyên.

### Không tạo giá trị thập phân bằng new BigDecimal(double)

```java
BigDecimal fromBinary = new BigDecimal(0.1);
BigDecimal fromDoubleString = BigDecimal.valueOf(0.1);
BigDecimal fromText = new BigDecimal("0.1");

System.out.println(fromBinary);
// 0.1000000000000000055511151231257827021181583404541015625
System.out.println(fromDoubleString); // 0.1
System.out.println(fromText);         // 0.1
```

`new BigDecimal(0.1)` lấy **giá trị nhị phân thực tế của double** và chuyển nó thành biểu diễn thập phân chính xác; vì vậy thấy phần dư dài. `BigDecimal.valueOf(double)` dùng dạng chuỗi chuẩn của `Double.toString(double)`, nên thường tạo biểu diễn ngắn dễ hiểu hơn.

Tuy nhiên, `valueOf(double)` **không phục hồi** được dữ liệu đã sai lệch do tính toán bằng `double` trước đó:

```java
double calculated = 0.1 + 0.2;

BigDecimal afterBinaryMath = BigDecimal.valueOf(calculated);
System.out.println(afterBinaryMath); // 0.30000000000000004
```

Nếu nguồn là giá tiền, số thập phân từ API hoặc file, hãy giữ chuỗi gốc hoặc chuyển trực tiếp sang giá trị decimal ở ranh giới nhập dữ liệu, thay vì qua `double`.

### Các hằng số và cách đặt tên

`BigDecimal.ZERO`, `BigDecimal.ONE`, `BigDecimal.TWO` và `BigDecimal.TEN` là các hằng số tiện dụng. Nên đưa các tỷ lệ nghiệp vụ vào các hằng số rõ nghĩa:

```java
private static final BigDecimal VAT_RATE = new BigDecimal("0.10");
private static final BigDecimal DISCOUNT_RATE = new BigDecimal("0.05");
```

Các tỷ lệ trên chỉ là **giả định cho ví dụ**. Không coi `0.10` là thuế suất mặc định của mọi quốc gia, sản phẩm, thời điểm hoặc loại giao dịch.

## 4. BigDecimal bất biến và các phép toán cơ bản

`BigDecimal` là kiểu **immutable**. Mọi phép toán trả về một đối tượng biểu diễn kết quả; nó không chỉnh sửa giá trị ban đầu.

```java
BigDecimal balance = new BigDecimal("100.00");

balance.add(new BigDecimal("25.00"));
System.out.println(balance); // 100.00

balance = balance.add(new BigDecimal("25.00"));
System.out.println(balance); // 125.00
```

Các phương thức thường gặp:

| Phương thức | Vai trò |
|---|---|
| `add(other)` | Cộng |
| `subtract(other)` | Trừ |
| `multiply(other)` | Nhân |
| `divide(other, scale, roundingMode)` | Chia với scale và chính sách làm tròn |
| `remainder(other)` | Phần dư theo quy tắc của `BigDecimal` |
| `abs()`, `negate()` | Giá trị tuyệt đối và đổi dấu |
| `pow(int)` | Lũy thừa số nguyên không âm trong overload cơ bản |
| `compareTo(other)` | So sánh thứ tự theo giá trị số học |
| `signum()` | Trả `-1`, `0` hoặc `1` theo dấu |

Ví dụ:

```java
BigDecimal a = new BigDecimal("10.50");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.add(b));      // 12.50
System.out.println(a.subtract(b)); // 8.50
System.out.println(a.multiply(b)); // 21.0000
System.out.println(a.negate());    // -10.50
```

Giá trị `21.0000` là chính xác và có scale 4. Điều này không phải lỗi: phép nhân chính xác mặc định có preferred scale bằng **tổng** scale của hai toán hạng.

### Preferred scale của phép toán

Khi không cung cấp `MathContext`, các phép toán số học trả kết quả chính xác nếu có thể:

| Phép toán | Preferred scale |
|---|---|
| `add` | `max(scale(a), scale(b))` |
| `subtract` | `max(scale(a), scale(b))` |
| `multiply` | `scale(a) + scale(b)` |
| `divide` | `scale(a) - scale(b)`, nhưng có thể cần scale lớn hơn để biểu diễn thương chính xác |

Ví dụ:

```java
BigDecimal one = new BigDecimal("1.20");
BigDecimal two = new BigDecimal("2.0");

System.out.println(one.add(two));      // 3.20
System.out.println(one.multiply(two)); // 2.400
```

Nếu hiển thị đơn vị tiền với hai chữ số lẻ, đừng ngầm giả định mọi phép nhân đã trả đúng scale mong muốn. **Chính sách scale phải được áp dụng tại vị trí nghiệp vụ quy định**, không phải chỉ nhìn dạng chuỗi đang in.

## 5. setScale: cố định số chữ số sau dấu thập phân

`setScale(newScale, roundingMode)` trả về giá trị có **scale được yêu cầu**. Khi việc giảm scale cần bỏ các chữ số khác 0, `roundingMode` quyết định cách làm tròn.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal value = new BigDecimal("12.345");

System.out.println(value.setScale(2, RoundingMode.HALF_UP)); // 12.35
System.out.println(value.setScale(2, RoundingMode.DOWN));    // 12.34
System.out.println(value.setScale(4, RoundingMode.UNNECESSARY)); // 12.3450
```

Tăng scale không làm thay đổi giá trị số học, chỉ bổ sung các số 0 cần thiết trong biểu diễn. Giảm scale có thể cần làm tròn.

### Dùng UNNECESSARY để xác thực dữ liệu đầu vào

Nếu hệ thống yêu cầu số tiền có thể biểu diễn chính xác với tối đa hai chữ số thập phân, có thể dùng:

```java
static BigDecimal requireTwoDecimalPlaces(BigDecimal amount) {
    return amount.setScale(2, RoundingMode.UNNECESSARY);
}
```

```java
System.out.println(requireTwoDecimalPlaces(
    new BigDecimal("5.5")
)); // 5.50

System.out.println(requireTwoDecimalPlaces(
    new BigDecimal("5.500")
)); // 5.50

// ArithmeticException: cần bỏ chữ số khác 0.
// requireTwoDecimalPlaces(new BigDecimal("5.555"));
```

Điểm cần hiểu: cách kiểm tra này xác thực **có thể biểu diễn chính xác với scale 2**, chứ không từ chối mọi đầu vào có *dạng văn bản* chứa nhiều hơn hai chữ số sau dấu thập phân. `5.500` vẫn được chấp nhận vì loại số 0 ở cuối không làm mất giá trị. Nếu hợp đồng cần giới hạn **đúng số chữ số người dùng nhập**, phải kiểm tra chuỗi đầu vào riêng.

Không nên dùng `setScale(2, HALF_UP)` để tự động sửa mọi dữ liệu không hợp lệ khi nghiệp vụ muốn từ chối thay vì làm tròn. **Xác thực dữ liệu** và **làm tròn kết quả tính toán** là hai trách nhiệm khác nhau.

## 6. RoundingMode: tám chính sách hiện hành

Trong Java 27, dùng enum `java.math.RoundingMode` thay cho các hằng số `int` `BigDecimal.ROUND_*` đã deprecated.

| RoundingMode | Quy tắc |
|---|---|
| `UP` | Rời xa 0 nếu cần bỏ phần khác 0 |
| `DOWN` | Tiến về 0 (cắt bớt, không làm tròn lên độ lớn) |
| `CEILING` | Hướng về dương vô cực |
| `FLOOR` | Hướng về âm vô cực |
| `HALF_UP` | Chọn giá trị gần nhất; ở đúng giữa thì rời xa 0 |
| `HALF_DOWN` | Chọn giá trị gần nhất; ở đúng giữa thì tiến về 0 |
| `HALF_EVEN` | Chọn giá trị gần nhất; ở đúng giữa thì chữ số cuối được giữ là số chẵn |
| `UNNECESSARY` | Chỉ chấp nhận kết quả chính xác, nếu cần làm tròn thì ném `ArithmeticException` |

### HALF_UP và HALF_EVEN khác nhau ở trường hợp đúng giữa

```java
BigDecimal a = new BigDecimal("2.345");
BigDecimal b = new BigDecimal("2.355");

System.out.println(a.setScale(2, RoundingMode.HALF_UP));   // 2.35
System.out.println(a.setScale(2, RoundingMode.HALF_EVEN)); // 2.34

System.out.println(b.setScale(2, RoundingMode.HALF_UP));   // 2.36
System.out.println(b.setScale(2, RoundingMode.HALF_EVEN)); // 2.36
```

`HALF_EVEN` còn được gọi là *round half to even* hoặc *banker's rounding*: trong tình huống đúng giữa hai giá trị có thể biểu diễn, nó ưu tiên giá trị có chữ số cuối chẵn ở vị trí đang giữ. Tính chất này có thể giúp giảm thiên lệch qua nhiều phép làm tròn trong một số phân bố dữ liệu, nhưng **không có chính sách nào mặc định đúng cho tất cả hợp đồng tài chính**.

### Dấu âm làm thay đổi ý nghĩa CEILING/FLOOR

```java
BigDecimal negative = new BigDecimal("-1.231");

System.out.println(negative.setScale(2, RoundingMode.CEILING)); // -1.23
System.out.println(negative.setScale(2, RoundingMode.FLOOR));   // -1.24
System.out.println(negative.setScale(2, RoundingMode.DOWN));    // -1.23
System.out.println(negative.setScale(2, RoundingMode.UP));      // -1.24
```

`CEILING` không phải “luôn tăng độ lớn” và `FLOOR` không phải “luôn cắt chữ số”. Chúng hướng về hai phía của trục số. Đối với hoàn tiền hoặc điều chỉnh âm, phân biệt này có thể làm thay đổi kết quả nghiệp vụ.

### Chọn rounding mode theo hợp đồng, không theo thói quen

Ví dụ về quyết định cần được ghi thành chính sách:

- Giá niêm yết có được nhập nhiều hơn hai chữ số thập phân không?
- Thuế được làm tròn theo **từng dòng**, **từng loại thuế** hay **tổng hóa đơn**?
- Một khoản giảm giá có được làm tròn trước khi tính thuế không?
- Khoản âm (hoàn tiền, chiết khấu) có cùng quy tắc làm tròn với khoản dương không?
- Số tiền dùng đơn vị tiền tệ nào và cần bao nhiêu chữ số lẻ?
- Hệ thống có phải tuân thủ quy định pháp luật, chính sách nhà cung cấp thanh toán hoặc hợp đồng đối tác không?

Nên lưu lại quy tắc trong code và tài liệu nghiệp vụ, đi kèm ví dụ ở ranh giới `x.xx5` và các trường hợp âm.

## 7. MathContext: giới hạn số chữ số có nghĩa

`MathContext` gồm hai thông tin:

- `precision`: tổng **số chữ số có nghĩa** của kết quả.
- `roundingMode`: cách chọn giá trị khi vượt quá precision.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal input = new BigDecimal("123.456");

BigDecimal bySignificantDigits = input.round(
    new MathContext(4, RoundingMode.HALF_EVEN)
);

BigDecimal byDecimalPlaces = input.setScale(
    2, RoundingMode.HALF_EVEN
);

System.out.println(bySignificantDigits); // 123.5
System.out.println(byDecimalPlaces);     // 123.46
```

`new MathContext(4, HALF_EVEN)` giữ **4 chữ số có nghĩa**; `setScale(2, HALF_EVEN)` giữ **2 chữ số sau dấu thập phân**. Chúng không thể thay thế lẫn nhau.

Một số hằng số `MathContext`:

| Hằng số | Precision | RoundingMode |
|---|---:|---|
| `MathContext.UNLIMITED` | 0 (không giới hạn precision) | Không có tác dụng làm tròn khi precision = 0 |
| `MathContext.DECIMAL32` | 7 | HALF_EVEN |
| `MathContext.DECIMAL64` | 16 | HALF_EVEN |
| `MathContext.DECIMAL128` | 34 | HALF_EVEN |

Các hằng số `DECIMAL32/64/128` thể hiện mức precision theo mô hình số thập phân IEEE 754 tương ứng, không tự giới hạn miền số mũ theo định dạng IEEE đó và **không** tự giải quyết quy tắc số chữ số lẻ của một loại tiền.

Khi không truyền `MathContext`, cộng, trừ, nhân `BigDecimal` thường được thực hiện chính xác (trong giới hạn bộ nhớ và scale). Khi truyền một context precision hữu hạn, **phép toán có thể làm tròn ngay tại bước đó**:

```java
var context = new MathContext(4, RoundingMode.HALF_EVEN);

BigDecimal result = new BigDecimal("123.456")
    .add(new BigDecimal("0.001"), context);

System.out.println(result); // 123.5
```

Nếu mô hình nghiệp vụ yêu cầu giữ độ chính xác đầy đủ trong suốt quá trình tính rồi mới làm tròn cuối kỳ, đừng truyền `MathContext` precision thấp vào tất cả các phép toán chỉ vì muốn mọi số “trông đẹp”.

## 8. Phép chia: trường hợp bắt buộc suy nghĩ về làm tròn

Một thương số có thể có hoặc không có biểu diễn thập phân hữu hạn:

```java
BigDecimal one = BigDecimal.ONE;

System.out.println(one.divide(new BigDecimal("8"))); // 0.125

// ArithmeticException: phần thập phân vô hạn tuần hoàn.
// System.out.println(one.divide(new BigDecimal("3")));
```

`divide(divisor)` yêu cầu kết quả chính xác; khi phép chia tạo số thập phân vô hạn (như `1/3`), nó ném `ArithmeticException`. Nếu mẫu số bằng `0`, phép chia cũng ném ngoại lệ.

### Chia với scale và rounding mode tường minh

```java
BigDecimal ratio = BigDecimal.ONE.divide(
    new BigDecimal("3"),
    2,
    RoundingMode.HALF_UP
);

System.out.println(ratio); // 0.33
```

Overload `divide(divisor, int scale, RoundingMode roundingMode)` xác định **số chữ số thập phân của kết quả**. Đây là một lựa chọn rõ ràng cho yêu cầu hiển thị hoặc phân bổ theo decimal places.

### Chia với MathContext

```java
var context = new MathContext(4, RoundingMode.HALF_EVEN);

BigDecimal result = BigDecimal.ONE.divide(
    new BigDecimal("3"),
    context
);

System.out.println(result); // 0.3333
```

Ở đây số `4` nói về **precision**, không phải “luôn có 4 chữ số sau dấu phẩy”. Với số lớn, cùng precision có thể dẫn đến `scale` thấp hoặc âm.

Chú ý overload `divide(divisor, RoundingMode)` sử dụng **scale của số bị chia** làm scale kết quả. Ví dụ, `BigDecimal.ONE.divide(new BigDecimal("8"), HALF_UP)` có thể làm tròn thành `0` vì `BigDecimal.ONE` có scale 0. Do dễ gây nhầm, hãy ưu tiên overload có `scale` tường minh hoặc `MathContext` phù hợp với chính sách.

### Đừng làm tròn phép chia quá sớm

Ví dụ phân bổ `1` đơn vị tiền thành ba phần với `scale=2`:

```java
BigDecimal oneUnit = new BigDecimal("1.00");

BigDecimal share = oneUnit.divide(
    BigDecimal.valueOf(3),
    2,
    RoundingMode.HALF_UP
);

System.out.println(share);                             // 0.33
System.out.println(share.multiply(BigDecimal.valueOf(3))); // 0.99
```

Tổng ba phần chỉ là `0.99`, thiếu `0.01`. Nếu nghiệp vụ yêu cầu **bảo toàn tổng**, cần một **thuật toán phân bổ phần dư**: ví dụ hai phần `0.33`, phần cuối nhận `0.34`; không chỉ gọi `divide` rồi nhân lại và mặc định tổng luôn bằng số gốc.

## 9. equals, compareTo và hệ quả với collection

Đây là khác biệt quan trọng giữa `BigDecimal` và nhiều kiểu giá trị khác:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));       // false
System.out.println(a.compareTo(b));    // 0
System.out.println(a.hashCode() == b.hashCode()); // false trong ví dụ này
```

- `equals()` so sánh cả **giá trị số học và biểu diễn/scale**.
- `compareTo()` chỉ so sánh **giá trị số học**; những số cùng giá trị nhưng khác scale được xem là tương đương theo thứ tự tự nhiên.
- `hashCode()` nhất quán với `equals()`, nhưng hai `BigDecimal` cùng giá trị số học mà khác scale **có thể có hash code khác**.

Điều này ảnh hưởng đến việc dùng làm key:

```java
import java.util.HashSet;
import java.util.TreeSet;

var hashValues = new HashSet<BigDecimal>();
hashValues.add(new BigDecimal("2.0"));
hashValues.add(new BigDecimal("2.00"));

var sortedValues = new TreeSet<BigDecimal>();
sortedValues.add(new BigDecimal("2.0"));
sortedValues.add(new BigDecimal("2.00"));

System.out.println(hashValues.size());   // 2
System.out.println(sortedValues.size()); // 1
```

`HashSet` dựa trên `equals/hashCode`; `TreeSet` dùng thứ tự `compareTo` để quyết định tính duy nhất. Vì thứ tự tự nhiên của `BigDecimal` **không nhất quán với `equals`**, hai collection có thể có cách hiểu “trùng” khác nhau.

### So sánh giá trị số học đúng cách

```java
BigDecimal amount = new BigDecimal("0.00");

boolean isZero = amount.signum() == 0;
boolean isPositive = amount.compareTo(BigDecimal.ZERO) > 0;
boolean isNegative = amount.signum() < 0;

System.out.println(isZero);     // true
System.out.println(isPositive); // false
```

Tránh dùng `amount.equals(BigDecimal.ZERO)` để kiểm tra số bằng 0, vì `0.00` có scale 2 còn `BigDecimal.ZERO` có scale 0.

Nếu một miền dữ liệu cần equality theo số học, hãy chuẩn hóa representation ngay tại ranh giới tạo value object. Với tiền tệ cần hai chữ số lẻ, `setScale(2, UNNECESSARY)` là một cách rõ nghĩa hơn việc bỏ mọi số 0 tùy tiện.

## 10. stripTrailingZeros và ký pháp khoa học

`stripTrailingZeros()` tạo `BigDecimal` có cùng giá trị số học nhưng bỏ các số 0 không cần thiết ở cuối biểu diễn.

```java
BigDecimal raw = new BigDecimal("600.0");
BigDecimal stripped = raw.stripTrailingZeros();

System.out.println(stripped.toString());      // 6E+2
System.out.println(stripped.toPlainString()); // 600
System.out.println(stripped.scale());         // -2
```

`toString()` có thể dùng ký pháp khoa học; `toPlainString()` không dùng ký pháp mũ trong kết quả chuỗi. Cả hai đều chỉ là phép chuyển sang văn bản, **không tự áp dụng quy tắc làm tròn**.

`stripTrailingZeros()` hữu ích khi muốn chuẩn hóa các giá trị số học, nhưng nó có thể sinh scale âm và làm mất cách biểu diễn “2 chữ số sau dấu thập phân” của tiền tệ. Đối với DTO tiền, biên nhận hoặc khóa chứa amount, hãy chọn chính sách biểu diễn rõ ràng và nhất quán trước khi serialize hoặc so sánh.

Cũng cần phân biệt:

```java
BigDecimal amount = new BigDecimal("12.30");

System.out.println(amount.toString());      // 12.30
System.out.println(amount.toPlainString()); // 12.30
System.out.println(amount.setScale(2));     // 12.30
```

`toPlainString` không thay đổi đối tượng hay scale, chỉ thay cách biểu diễn văn bản. `setScale` tạo giá trị mới với scale được chọn (nếu tăng scale hoặc không cần bỏ chữ số khác 0, overload không truyền rounding mode cũng áp dụng được).

## 11. Chính sách tiền tệ: scale không đồng nghĩa đơn vị tiền

Một kiểu `BigDecimal` chỉ chứa **số**. Nó không biết giá trị `100.00` là 100 USD, 100 VND, số điểm thưởng hay trọng lượng hàng hóa.

Đối với tiền tệ, nên mô hình hóa thêm:

- **Mã tiền tệ** (ví dụ `USD`, `VND`, `JPY`, `KWD`).
- **Scale cho từng nghiệp vụ** (giá niêm yết, phí, thuế, khoản thanh toán).
- **RoundingMode** và vị trí áp dụng.
- Quy tắc chấp nhận đầu vào, quy tắc chuyển đổi tiền tệ và cách xử lý phần dư nếu phải phân bổ.

Không giả định mọi loại tiền đều có hai chữ số lẻ. `java.util.Currency.getDefaultFractionDigits()` cung cấp số chữ số thập phân **mặc định theo ISO** cho tiền tệ mà JDK biết; với một số mã, giá trị có thể là `-1`. Ngay cả khi biết mặc định theo ISO, yêu cầu thực tế của hệ thống thanh toán hoặc chính sách pháp lý có thể khác.

```java
import java.util.Currency;

System.out.println(Currency.getInstance("USD").getDefaultFractionDigits()); // 2
System.out.println(Currency.getInstance("JPY").getDefaultFractionDigits()); // 0
System.out.println(Currency.getInstance("KWD").getDefaultFractionDigits()); // 3
```

### Value object mang rõ currency và scale

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

record Money(Currency currency, BigDecimal amount) {
    Money {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(amount, "amount");

        int scale = currency.getDefaultFractionDigits();

        if (scale < 0) {
            throw new IllegalArgumentException(
                "Cần cấu hình scale cho tiền tệ này");
        }

        amount = amount.setScale(scale, RoundingMode.UNNECESSARY);
    }

    Money add(Money other) {
        Objects.requireNonNull(other, "other");

        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Không thể cộng khác tiền tệ");
        }
        return new Money(currency, amount.add(other.amount()));
    }
}
```

Ví dụ:

```java
var usd = Currency.getInstance("USD");
var first = new Money(usd, new BigDecimal("12.5"));
var second = new Money(usd, new BigDecimal("2.25"));

System.out.println(first.add(second).amount()); // 14.75
```

Đây là mô hình minh họa. Trong sản phẩm thực tế, nên **tiêm chính sách scale từ miền hoặc cấu hình nghiệp vụ**, không bắt buộc lấy mặc định `Currency` cho mọi thao tác. Phải thực hiện chuyển đổi tỷ giá được kiểm soát trước khi cộng tiền khác đơn vị; phép cộng đơn thuần trên hai `BigDecimal` không phải chuyển đổi tiền tệ.

### Số nguyên theo đơn vị nhỏ nhất

Khi hệ thống thanh toán bên ngoài cung cấp giá trị theo *minor units* dưới dạng số nguyên, có thể dùng:

```java
long cents = 12345L;
BigDecimal dollars = BigDecimal.valueOf(cents, 2);

System.out.println(dollars); // 123.45
```

`BigDecimal.valueOf(long unscaledValue, int scale)` biểu diễn chính xác dữ liệu dạng nguyên theo scale, nhưng scale cần đi kèm hợp đồng đơn vị tiền. Không tự lấy scale 2 với mọi loại tiền.

## 12. Làm tròn ở đâu quan trọng hơn làm tròn bằng gì

Ngay cả khi mọi bước đều dùng `BigDecimal` và cùng `RoundingMode`, thứ tự làm tròn có thể tạo kết quả khác nhau.

Giả sử có ba dòng, mỗi dòng có cơ sở tính thuế `0.05` và thuế suất minh họa `10%`:

```java
var base = new BigDecimal("0.05");
var rate = new BigDecimal("0.10");

BigDecimal taxPerLine = base.multiply(rate)
    .setScale(2, RoundingMode.HALF_UP); // 0.01

BigDecimal lineLevelTax = taxPerLine
    .multiply(BigDecimal.valueOf(3));   // 0.03

BigDecimal invoiceLevelTax = base
    .multiply(BigDecimal.valueOf(3))    // 0.15
    .multiply(rate)                     // 0.0150
    .setScale(2, RoundingMode.HALF_UP);  // 0.02

System.out.println(lineLevelTax);    // 0.03
System.out.println(invoiceLevelTax); // 0.02
```

Hai kết quả **đều phù hợp với phép làm tròn đã chọn**, nhưng chúng trả lời **hai chính sách khác nhau**:

- **Làm tròn từng dòng:** làm tròn thuế từng dòng rồi cộng.
- **Làm tròn tổng:** cộng cơ sở tính thuế rồi làm tròn thuế một lần.

Không có lựa chọn nào luôn đúng ở mọi quốc gia hoặc loại hóa đơn. Chính sách phải được xác định bởi quy định và hợp đồng nghiệp vụ. Nếu đang di chuyển hệ thống hoặc đối soát hai bên, hãy kiểm tra **cả vị trí làm tròn**, không chỉ `RoundingMode`.

### Tránh làm tròn trung gian khi chưa được yêu cầu

Một pipeline có thể có giá niêm yết, số lượng, chiết khấu, thuế và tổng thanh toán. Hãy phân biệt:

1. **Dữ liệu gốc được xác thực** (đơn vị, scale đầu vào).
2. **Giá trị toán học chính xác** của từng phép tính, nếu có thể.
3. **Điểm chốt nghiệp vụ** buộc kết quả phải làm tròn.
4. **Định dạng hiển thị** cho người dùng hoặc bên thứ ba.

Nếu mọi phép nhân đều lập tức `setScale(2, HALF_UP)` mà không có lý do, kết quả cuối có thể sai với chính sách của hợp đồng.

## 13. Ví dụ đầy đủ: tính hóa đơn với một chính sách tường minh

Ví dụ sau dùng một chính sách **minh họa**, không phải quy định thuế của bất kỳ địa phương nào:

- Dữ liệu giá đầu vào là giá trị tiền có thể biểu diễn đúng ở 2 chữ số sau dấu thập phân, không tự làm tròn.
- Thành tiền từng dòng = đơn giá × số lượng (tính chính xác).
- Tổng trước giảm giá = tổng thành tiền các dòng.
- Chiết khấu 5% được tính trên tổng, làm tròn 2 chữ số bằng `HALF_UP`.
- Thuế minh họa 10% được tính trên phần còn lại sau chiết khấu, làm tròn 2 chữ số bằng `HALF_UP`.
- Tổng phải thanh toán = sau chiết khấu + thuế.

Lưu toàn bộ mã sau vào file `BigDecimalPolicyDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

public class BigDecimalPolicyDemo {
    private static final int MONEY_SCALE = 2;
    private static final RoundingMode MONEY_ROUNDING = RoundingMode.HALF_UP;

    private static final BigDecimal DISCOUNT_RATE = new BigDecimal("0.05");
    private static final BigDecimal TAX_RATE = new BigDecimal("0.10");

    record Line(String sku, int quantity, BigDecimal unitPrice) {
        Line {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (sku.isBlank()) {
                throw new IllegalArgumentException("Mã hàng không được rỗng");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải dương");
            }
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Đơn giá không được âm");
            }

            // Kiểm tra chính xác, không âm thầm làm tròn đầu vào.
            unitPrice = unitPrice.setScale(
                MONEY_SCALE, RoundingMode.UNNECESSARY);
        }

        BigDecimal lineTotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record Invoice(List<Line> lines) {
        Invoice {
            lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("Hóa đơn phải có dòng hàng");
            }
        }
    }

    record Totals(
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal taxableAmount,
        BigDecimal tax,
        BigDecimal grandTotal
    ) {}

    static Totals calculate(Invoice invoice) {
        Objects.requireNonNull(invoice, "invoice");

        BigDecimal subtotal = invoice.lines().stream()
            .map(Line::lineTotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add)
            .setScale(MONEY_SCALE, RoundingMode.UNNECESSARY);

        BigDecimal discount = subtotal
            .multiply(DISCOUNT_RATE)
            .setScale(MONEY_SCALE, MONEY_ROUNDING);

        BigDecimal taxable = subtotal.subtract(discount);

        BigDecimal tax = taxable
            .multiply(TAX_RATE)
            .setScale(MONEY_SCALE, MONEY_ROUNDING);

        BigDecimal grandTotal = taxable.add(tax);

        return new Totals(
            subtotal, discount, taxable, tax, grandTotal);
    }

    public static void main(String[] args) {
        var invoice = new Invoice(List.of(
            new Line("BOOK", 2, new BigDecimal("19.99")),
            new Line("PEN", 3, new BigDecimal("5.50"))
        ));

        Totals totals = calculate(invoice);

        System.out.println("Tạm tính: " + totals.subtotal().toPlainString());
        System.out.println("Chiết khấu: " + totals.discount().toPlainString());
        System.out.println(
            "Sau chiết khấu: " + totals.taxableAmount().toPlainString());
        System.out.println("Thuế: " + totals.tax().toPlainString());
        System.out.println("Thanh toán: " + totals.grandTotal().toPlainString());
    }
}
```

Biên dịch và chạy bằng JDK 27:

```shell
javac BigDecimalPolicyDemo.java
java BigDecimalPolicyDemo
```

Kết quả dự kiến:

```text
Tạm tính: 56.48
Chiết khấu: 2.82
Sau chiết khấu: 53.66
Thuế: 5.37
Thanh toán: 59.03
```

Có thể kiểm tra bằng tính toán từng bước:

| Bước | Phép tính | Kết quả |
|---|---|---|
| BOOK | 2 × 19.99 | 39.98 |
| PEN | 3 × 5.50 | 16.50 |
| Tổng trước giảm giá | 39.98 + 16.50 | 56.48 |
| Chiết khấu | 56.48 × 0.05 = 2.8240 → làm tròn 2 chữ số | 2.82 |
| Sau chiết khấu | 56.48 − 2.82 | 53.66 |
| Thuế | 53.66 × 0.10 = 5.3660 → làm tròn 2 chữ số | 5.37 |
| Thanh toán | 53.66 + 5.37 | 59.03 |

Trong mã, `setScale(2, UNNECESSARY)` ở đầu vào là **validation**; `setScale(2, HALF_UP)` khi tính chiết khấu/thuế là **policy rounding**. Hai quyết định khác nhau được biểu diễn bằng hai mode khác nhau để tránh “làm tròn cho tiện”.

Kết quả mẫu chưa xét nhiều loại tiền, trả hàng, giảm giá nhiều tầng, thuế nhiều nhóm, tỷ giá, chuyển đổi đơn vị hoặc làm tròn tiền mặt. Những yêu cầu đó cần mở rộng mô hình domain và các bài kiểm thử tương ứng.

## 14. Tính tổng BigDecimal bằng Stream và xử lý danh sách rỗng

Khi tổng hợp nhiều `BigDecimal`, `reduce` giúp biểu diễn phép cộng không cần mutable accumulator:

```java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> amounts = List.of(
    new BigDecimal("12.50"),
    new BigDecimal("7.25"),
    new BigDecimal("0.25")
);

BigDecimal total = amounts.stream()
    .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 20.00
```

`BigDecimal.ZERO` là identity cho phép cộng; stream rỗng trả về `ZERO` (scale 0), không tự trở thành `0.00`:

```java
BigDecimal emptyTotal = List.<BigDecimal>of().stream()
    .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(emptyTotal);       // 0
System.out.println(emptyTotal.scale()); // 0

BigDecimal moneyTotal = emptyTotal.setScale(2, RoundingMode.UNNECESSARY);
System.out.println(moneyTotal); // 0.00
```

Nếu định dạng đầu ra luôn yêu cầu scale 2, chuẩn hóa tại ranh giới xuất dữ liệu hoặc dùng identity có scale mong muốn và chính sách nhất quán; đừng dựa vào việc một danh sách có phần tử hay không để quyết định dạng hiển thị.

`BigDecimal` là immutable, phép cộng có tính kết hợp trong toán học chính xác và không có shared mutable state, vì vậy nó thuận tiện cho `reduce`. Tuy nhiên, **thêm `MathContext` precision hữu hạn vào mỗi bước cộng** có thể đưa làm tròn vào các kết quả trung gian; lúc đó tổng có thể phụ thuộc thứ tự/nhóm tính. Với yêu cầu đối soát, cần kiểm soát kỹ điểm làm tròn và thứ tự tổng hợp.

## 15. Lưu trữ, định dạng và trao đổi dữ liệu

**Tính toán**, **lưu trữ** và **hiển thị** là ba bước riêng biệt:

- Trong Java, biểu diễn số thập phân bằng `BigDecimal` với scale và chính sách rõ ràng.
- Trong cơ sở dữ liệu quan hệ, thường chọn kiểu `DECIMAL(p,s)` hoặc `NUMERIC(p,s)` phù hợp với giá trị và giới hạn nghiệp vụ; không dùng `FLOAT`/`DOUBLE` cho dữ liệu yêu cầu tính toán thập phân chính xác.
- Với JDBC, `PreparedStatement.setBigDecimal` và `ResultSet.getBigDecimal` cho phép làm việc với kiểu số thập phân. Kiểm tra hành vi của driver, cột dữ liệu và chính sách scale.
- Với JSON và dịch vụ bên ngoài, xác định rõ hợp đồng schema: số JSON, chuỗi thập phân hay số nguyên theo *minor units*. Một số hệ sinh thái có thể chuyển JSON number qua `double`; cần tránh đánh mất độ chính xác ở ranh giới giao tiếp.
- Với hiển thị theo quốc gia, dùng `NumberFormat`/`DecimalFormat` hoặc thư viện định dạng chuyên dụng sau khi đã tính ra giá trị đúng. Format để hiển thị **không thay thế** chính sách làm tròn nghiệp vụ.

Ví dụ định dạng tách khỏi tính toán:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

BigDecimal value = new BigDecimal("1234.50");

var formatter = NumberFormat.getCurrencyInstance(Locale.US);
String displayed = formatter.format(value);

System.out.println(displayed); // $1,234.50 (với locale và dữ liệu mặc định tương ứng)
```

Nếu giá trị thực tế không phải USD, phải chỉ định đúng loại tiền và quy tắc hiển thị; không gán ký hiệu theo locale bất kể đơn vị của dữ liệu.

Đối với việc lưu key/caching, cần quyết định liệu `2.0` và `2.00` có phải một giá trị nghiệp vụ hay không. Nếu có, chuẩn hóa scale trước khi dùng làm key hoặc xây một value object áp dụng hợp đồng equality rõ ràng.

## 16. Các lỗi thường gặp và cách tránh

| Sai lầm | Hậu quả | Giải pháp |
|---|---|---|
| `new BigDecimal(0.1)` cho giá trị tiền thập phân | Mang chính xác sai số nhị phân của `double` | Tạo từ chuỗi thập phân hoặc nguồn decimal |
| Dùng `BigDecimal.valueOf(0.1 + 0.2)` rồi nghĩ đã sửa sai số | Sai số đã hình thành trước khi chuyển đổi | Tính bằng `BigDecimal` từ đầu |
| Dùng toán tử `+` để cộng `BigDecimal` | Không phải phép cộng số học của `BigDecimal` | `add()`, `subtract()`, `multiply()` |
| Gọi `add()` mà không gán kết quả | Giá trị ban đầu không thay đổi | Nhận giá trị trả về |
| Gọi `divide(3)` và kỳ vọng tự làm tròn | `ArithmeticException` với thương vô hạn | Dùng overload có scale + `RoundingMode` |
| Dùng `MathContext(2)` để “giữ 2 số lẻ” | Precision khác scale | Dùng `setScale(2, mode)` khi cần 2 số lẻ |
| Luôn dùng `equals()` để so sánh số | `2.0` khác `2.00` | Dùng `compareTo` hoặc chuẩn hóa scale |
| Dùng `stripTrailingZeros()` để chuẩn hóa tiền mà không kiểm tra | Scale có thể âm, ký pháp mũ | Chọn scale theo chính sách tiền tệ |
| Làm tròn sau mọi phép toán | Tích lũy sai lệch giữa các bước | Làm tròn tại điểm nghiệp vụ xác định |
| Mặc định mọi loại tiền có 2 số lẻ | Sai đơn vị tiền và quy tắc thanh toán | Mô hình hóa currency, scale và domain rules |
| Bỏ qua số âm ở `CEILING`/`FLOOR` | Kết quả hoàn tiền hoặc điều chỉnh sai | Kiểm thử dấu âm và ranh giới |
| Chia nhỏ tổng mà không phân bổ phần dư | Tổng từng phần khác số gốc | Có thuật toán phân bổ bảo toàn tổng |
| Dùng `toString()` làm định dạng hiển thị bắt buộc | Có thể xuất hiện scientific notation | Dùng `toPlainString` hoặc formatter |
| So sánh kết quả bằng `doubleValue()` | Có thể mất độ chính xác | Dùng `compareTo`, `equals` theo policy |

Khi áp dụng các chính sách làm tròn trong phần mềm tài chính, còn cần kiểm tra yêu cầu pháp lý và hợp đồng hiện hành tại nơi triển khai. Không suy ra quy định cụ thể chỉ từ tên `HALF_UP` hay `HALF_EVEN`.

## 17. Bài tập thực hành

### Bài 1 — Scale và precision

Cho:

```java
BigDecimal value = new BigDecimal("123.4500");
```

Hãy xác định `unscaledValue()`, `scale()`, `precision()`, `toPlainString()`. Sau đó so sánh `value.stripTrailingZeros()` với `value` bằng `equals()` và `compareTo()`.

### Bài 2 — HALF_EVEN so với HALF_UP

Đưa `2.345` và `2.355` về scale 2 bằng hai mode `HALF_EVEN` và `HALF_UP`. Giải thích tại sao kết quả khác nhau ở `2.345`.

### Bài 3 — Phép chia

Tính `1 / 3` với scale 4 và `HALF_UP`. So sánh với `new MathContext(4, HALF_UP)` khi tính `100 / 3`: vì sao kết quả không nhất thiết có 4 chữ số sau dấu thập phân?

### Bài 4 — Kiểm tra dữ liệu

Viết một hàm nhận số tiền dưới dạng chuỗi và tạo `BigDecimal` với tối đa hai chữ số lẻ, **từ chối** số thực sự cần làm tròn. Đầu vào `"10.230"` có hợp lệ không? Còn `"10.231"`?

### Bài 5 — Hóa đơn

Với hai đơn giá `19.99` × 2 và `5.50` × 3, hãy tính tạm tính, chiết khấu 5%, thuế 10% sau chiết khấu và tổng bằng `HALF_UP` tại hai bước chiết khấu/thuế, giữ scale 2.

### Bài 6 — Tiền khác đơn vị

Một báo cáo nhận hai khoản `100.00 USD` và `100 JPY`. Vì sao không được cộng trực tiếp hai `BigDecimal` thành `200.00` và gọi đó là tổng tiền? Cần thông tin nào nếu muốn quy đổi?

### Bài 7 — Kiểm thử ranh giới

Viết các trường hợp kiểm thử cho:

- Tỷ lệ chia tạo decimal vô hạn (`1/3`).
- `setScale(2, UNNECESSARY)` với `"1.230"` và `"1.231"`.
- `HALF_UP` với `-1.235`.
- `compareTo` và `equals` khi so `"0"` và `"0.00"`.
- Kết quả làm tròn thuế theo từng dòng khác làm tròn tổng.

### Đáp án gợi ý

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal a = new BigDecimal("123.4500");
System.out.println(a.unscaledValue()); // 1234500
System.out.println(a.scale());         // 4
System.out.println(a.precision());     // 7

BigDecimal normalized = a.stripTrailingZeros();
System.out.println(a.equals(normalized));          // false
System.out.println(a.compareTo(normalized) == 0); // true

System.out.println(
    new BigDecimal("2.345").setScale(2, RoundingMode.HALF_EVEN)
); // 2.34
System.out.println(
    new BigDecimal("2.345").setScale(2, RoundingMode.HALF_UP)
); // 2.35

System.out.println(
    BigDecimal.ONE.divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP)
); // 0.3333

System.out.println(
    new BigDecimal("100").divide(
        new BigDecimal("3"),
        new MathContext(4, RoundingMode.HALF_UP))
); // 33.33

static BigDecimal parseTwoPlaces(String text) {
    return new BigDecimal(text).setScale(2, RoundingMode.UNNECESSARY);
}
```

`"10.230"` được chuẩn hóa thành `10.23` vì chữ số bị bỏ là 0; `"10.231"` bị từ chối bằng `ArithmeticException`. `-1.235` về scale 2 với `HALF_UP` cho `-1.24`. `0` và `0.00` bằng nhau theo `compareTo` nhưng không bằng nhau theo `equals`.

## 18. Tổng kết

`BigDecimal` là một kiểu số thập phân immutable hỗ trợ số học chính xác tùy ý trong giới hạn tài nguyên. **Scale** mô tả vị trí dấu thập phân, **precision** mô tả số chữ số có nghĩa, còn **RoundingMode** mô tả quyết định khi không thể giữ mọi chữ số.

Những nguyên tắc thiết yếu trong Java 27 là:

1. Tạo giá trị thập phân từ chuỗi hoặc số nguyên theo scale; tránh nhập dữ liệu tiền qua `double`.
2. Dùng `setScale` khi cần cố định số chữ số thập phân; dùng `MathContext` khi cần precision theo chữ số có nghĩa.
3. Chia cho số tạo decimal vô hạn phải có chính sách rounding hoặc context phù hợp.
4. Nhớ `equals` xét cả scale còn `compareTo` xét giá trị số học.
5. Làm tròn tại **điểm nghiệp vụ quy định**, phân biệt kiểm tra input với làm tròn kết quả.
6. Luôn mô hình hóa đơn vị tiền, kiểm tra quy tắc phân bổ phần dư, và có bài kiểm thử các giá trị biên, giá trị âm, dữ liệu rỗng và phép chia.

## Tài liệu tham khảo

- [Java SE 27 API — BigDecimal](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html): mô hình unscaled value/scale, arithmetic, precision, `divide`, `equals` và `compareTo`.
- [Java SE 27 API — MathContext](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/MathContext.html): precision, roundingMode và các hằng số `DECIMAL32/64/128`.
- [Java SE 27 API — RoundingMode](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/RoundingMode.html): tám chế độ làm tròn hiện hành.
- [Java SE 27 API — Currency](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Currency.html): mã đơn vị tiền và `getDefaultFractionDigits()`.
- [Java SE 27 API — NumberFormat](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/NumberFormat.html): hiển thị số và tiền theo locale.
- [Java SE 27 API — Stream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html): `reduce` cho tổng hợp giá trị immutable.
- [Java SE 27 API — PreparedStatement](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/PreparedStatement.html): `setBigDecimal` khi ghi số thập phân bằng JDBC.
