# divideToIntegralValue, remainder và divideAndRemainder trong BigDecimal

> **Java core – numbers · Phép toán BigDecimal**  
> **Mục tiêu:** Hiểu sự khác biệt giữa chia lấy **phần nguyên của thương**, phép chia lấy **phần dư** và API trả **cả hai**; đọc đúng dấu, scale, precision và ngoại lệ; phân biệt remainder với phép modulo Euclid; biết khi nào nên truyền `MathContext` và viết mã Java 17+ kiểm chứng chính xác kết quả.

## 1. Khi phép chia thập phân không cần thương có phần lẻ

Một tình huống thường gặp: chia một số tiền, khối lượng hoặc số lượng chính xác thành các nhóm, rồi cần biết **có bao nhiêu nhóm nguyên** và **phần còn lại là bao nhiêu**.

Ví dụ có `17.5` đơn vị và mỗi nhóm cần `3` đơn vị:

\[
17.5 = 5 \times 3 + 2.5
\]

Ta cần thương nguyên 5 và phần dư 2.5; không nhất thiết phải tính thương thập phân lặp vô hạn `17.5/3 = 5.83333...`.

`BigDecimal` cung cấp ba phương thức cho nhu cầu ấy:

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("17.5");
BigDecimal unit = new BigDecimal("3");

BigDecimal quotient = amount.divideToIntegralValue(unit);
BigDecimal remainder = amount.remainder(unit);
BigDecimal[] both = amount.divideAndRemainder(unit);

System.out.println(quotient);  // 5.0
System.out.println(remainder); // 2.5
System.out.println(both[0]);   // 5.0
System.out.println(both[1]);   // 2.5
```

**Vì sao in `5.0` chứ không phải `5`?** `BigDecimal` có thuộc tính **scale**. Một kết quả có giá trị số nguyên vẫn có thể được biểu diễn bằng BigDecimal scale dương. `5.0` vẫn là giá trị số 5; phần cách biểu diễn sẽ được phân tích ở mục về scale.

### Bảng API cốt lõi

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `a.divideToIntegralValue(b)` | `BigDecimal` | Phần nguyên của thương, cắt phần lẻ về phía 0 |
| `a.remainder(b)` | `BigDecimal` | `a - q×b` với q là thương nguyên ở trên |
| `a.divideAndRemainder(b)` | `BigDecimal[]` | Mảng hai phần tử: `[0]` là q, `[1]` là r |
| `a.divideToIntegralValue(b, mc)` | `BigDecimal` | Thương nguyên, nhưng bị ràng buộc khả năng biểu diễn bởi `MathContext` |
| `a.remainder(b, mc)` | `BigDecimal` | Phần dư dùng thương nguyên tính với `mc` |
| `a.divideAndRemainder(b, mc)` | `BigDecimal[]` | Cặp thương nguyên và dư với `mc` |

Cả sáu phương thức trên có trong Java 17, thuộc `java.math.BigDecimal`. Không phải phương thức static: chúng được gọi trên **số bị chia**.

## 2. Định nghĩa chính xác của thương nguyên

Cho số bị chia `a` và số chia `b != 0`. Phần nguyên của thương được tính bằng cách **cắt phần thập phân của thương thực về phía số 0** (*truncate toward zero*).

Ký hiệu:

\[
q = \operatorname{trunc}(a/b)
\]
\[
r = a - q\times b
\]

Đẳng thức phải luôn thỏa mãn theo giá trị số học:

\[
a = q\times b + r
\]

Đặc biệt, q không nhất thiết là kết quả của hàm **floor** (làm tròn xuống −∞). Sự khác biệt lộ rõ với số âm:

```text
 a       b      a/b (xấp xỉ)   q = trunc(a/b)    r
-------------------------------------------------------
 17.5    3       5.8333...          5         2.5
-17.5    3      -5.8333...         -5        -2.5
 17.5   -3      -5.8333...         -5         2.5
-17.5   -3       5.8333...          5        -2.5
```

Với `a=-17.5` và `b=3`, nếu dùng `floor(-5.8333...)` thì q=−6; nhưng `divideToIntegralValue` trả giá trị q=−5. Hai quy tắc khác nhau.

**Đừng gọi thương này là “làm tròn xuống” khi có thể có số âm.** Dùng “cắt phần lẻ về 0” hoặc “thương nguyên theo truncation”.

### Thương nguyên vẫn mang kiểu BigDecimal

`divideToIntegralValue` trả **`BigDecimal`**, không phải `BigInteger`, `int` hay `long`:

```java
BigDecimal q = new BigDecimal("17.5")
        .divideToIntegralValue(new BigDecimal("3"));

// Có thể là 5.0, nhưng vẫn biểu diễn một số nguyên.
System.out.println(q.toBigIntegerExact()); // 5
```

Nếu API tiếp theo thật sự cần kiểu nguyên, `toBigIntegerExact()` có thể diễn giải giá trị số nguyên thành BigInteger mà không cắt phần lẻ. Để chuyển về int hoặc long mà không mất giá trị, cân nhắc `intValueExact()`/`longValueExact()`; chúng báo lỗi nếu kết quả không vừa miền kiểu đích.

## 3. remainder là gì? Không phải “modulo luôn không âm”

Với `a=17.5`, `b=3`:

```java
BigDecimal a = new BigDecimal("17.5");
BigDecimal b = new BigDecimal("3");

BigDecimal q = a.divideToIntegralValue(b);
BigDecimal r = a.remainder(b);

System.out.println(q); // 5.0
System.out.println(r); // 2.5
```

Đẳng thức `a = q×b + r` được thực hiện theo giá trị BigDecimal chính xác:

```java
BigDecimal reconstructed = q.multiply(b).add(r);
System.out.println(reconstructed.compareTo(a) == 0); // true
```

Với số âm:

```java
BigDecimal negative = new BigDecimal("-17.5");
System.out.println(negative.divideToIntegralValue(b)); // -5.0
System.out.println(negative.remainder(b));             // -2.5
```

**Phần dư của BigDecimal có thể âm.** Nó lấy dấu theo số bị chia `a` khi phần dư khác 0, do q được cắt về phía 0. Đó là cùng tinh thần với toán tử `%` của số nguyên Java, **không** phải phép modulo Euclid luôn thuộc đoạn `[0,m)` với môđun dương.

Các đặc tính khi `b != 0` và các giá trị hữu hạn:

- `a = q×b+r`;
- `|r| < |b|` khi r khác 0, và điều kiện cũng thỏa với r=0;
- r khác 0 mang dấu của a;
- đổi dấu b có thể đổi dấu q, nhưng **không đổi dấu r** nếu a giữ nguyên;
- thương nguyên q được cắt về 0, không phụ thuộc chế độ rounding thông thường của phép chia decimal.

### Phân biệt remainder với modulo Euclid

Giả sử cần phần dư **không âm** từ một môđun dương 3:

```java
BigDecimal a = new BigDecimal("-17.5");
BigDecimal m = new BigDecimal("3");

BigDecimal raw = a.remainder(m); // -2.5
BigDecimal euclidean = raw.signum() < 0
        ? raw.add(m) : raw;       // 0.5
```

`0.5` là phần dư Euclid trong đoạn `[0,3)`, còn `-2.5` là phần dư của BigDecimal. Nếu muốn phép modulo Euclid cho BigDecimal, hãy định nghĩa **môđun dương** và chuẩn hóa phần dư như trên.

BigInteger có `mod(modulus)` với yêu cầu modulus dương; **BigDecimal không có `mod(BigDecimal)` tương ứng**. Không tự đặt tên `remainder` là modulo không âm rồi xây thuật toán dựa trên giả định sai.

## 4. divideAndRemainder: một lời gọi, hai kết quả

Khi chương trình cần **cả thương nguyên lẫn phần dư**, viết:

```java
BigDecimal[] result = amount.divideAndRemainder(unit);
BigDecimal quotient = result[0];
BigDecimal remainder = result[1];
```

Mảng có **đúng hai phần tử** theo thứ tự:

1. `result[0]`: thương nguyên `divideToIntegralValue`.
2. `result[1]`: phần dư `remainder`.

Đừng đảo hai phần tử hoặc hiểu `result[0]` là thương decimal có phần lẻ.

```java
BigDecimal amount = new BigDecimal("17.5");
BigDecimal unit = new BigDecimal("3");

BigDecimal[] qr = amount.divideAndRemainder(unit);

System.out.println("q = " + qr[0]); // q = 5.0
System.out.println("r = " + qr[1]); // r = 2.5
```

Theo Javadoc, khi cần cả thương và dư, phương thức này **có thể nhanh hơn** gọi lần lượt hai phép riêng vì phần tính thương có thể được dùng lại. Không suy luận rằng một lời gọi luôn có tốc độ cố định hoặc luôn nhanh hơn trong mọi workload; muốn tối ưu thực tế phải benchmark.

### Tính bất biến của BigDecimal

Phép chia và lấy dư **không thay đổi** hai toán hạng:

```java
BigDecimal a = new BigDecimal("17.5");
BigDecimal b = new BigDecimal("3");
BigDecimal[] qr = a.divideAndRemainder(b);

System.out.println(a); // 17.5
System.out.println(b); // 3
```

`BigDecimal` là immutable; việc gán lại biến hay lưu một giá trị mới không thay đổi đối tượng cũ. Mảng `BigDecimal[]` do phương thức trả về là một container gồm hai tham chiếu, bạn có thể thay phần tử của mảng nhưng không làm đổi giá trị BigDecimal bên trong.

## 5. Khác gì với divide và phép chia decimal thông thường?

Đây là khác biệt rất quan trọng:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// Không có thương decimal kết thúc:
 // BigDecimal bad = one.divide(three); // ArithmeticException

BigDecimal integerPart = one.divideToIntegralValue(three);
BigDecimal rest = one.remainder(three);
BigDecimal[] both = one.divideAndRemainder(three);

System.out.println(integerPart); // 0
System.out.println(rest);        // 1
System.out.println(both[0]);     // 0
System.out.println(both[1]);     // 1
```

`1/3` có phần thập phân lặp vô hạn, vì vậy `BigDecimal.divide(BigDecimal)` **không có rounding mode/context** không thể tạo thương decimal kết thúc chính xác và ném `ArithmeticException`.

Nhưng **thương nguyên của 1/3 chỉ là 0, phần dư là 1**. Hai giá trị đó được biểu diễn chính xác; `divideToIntegralValue` và `remainder` không cần tính mọi chữ số của thương decimal.

Khi muốn thương có phần thập phân theo quy tắc làm tròn, dùng một API chia **khác**:

```java
import java.math.RoundingMode;

BigDecimal rounded = one.divide(
        three, 2, RoundingMode.HALF_UP);
System.out.println(rounded); // 0.33
```

Nhưng `0.33` **không phải** thương nguyên q=0 và cũng không được dùng thay q trong công thức remainder mặc định. Nếu dùng `0.33` làm thương để tính `1 - 0.33×3`, phần còn lại là 0.01 — khác định nghĩa r=1.

| Phép toán | `1/3` | Ý nghĩa |
| --- | --- | --- |
| `one.divide(three)` | Ném `ArithmeticException` | Yêu cầu thương decimal chính xác kết thúc |
| `one.divide(three, 2, HALF_UP)` | 0.33 | Thương decimal làm tròn |
| `one.divideToIntegralValue(three)` | 0 | Phần nguyên của thương |
| `one.remainder(three)` | 1 | Phần còn lại theo q=0 |
| `one.divideAndRemainder(three)` | [0, 1] | Trả cả hai |

**Bài học:** Không chọn `divideToIntegralValue` chỉ để “tránh exception” nếu yêu cầu của nghiệp vụ thực sự cần một thương decimal. Nó cố ý **bỏ phần lẻ của thương**.

## 6. Dấu của thương và dư: kiểm tra đủ 4 trường hợp

Thử bốn tổ hợp dấu:

```java
BigDecimal positive = new BigDecimal("17.5");
BigDecimal negative = new BigDecimal("-17.5");
BigDecimal three = new BigDecimal("3");
BigDecimal minusThree = new BigDecimal("-3");

System.out.println(java.util.Arrays.toString(
        positive.divideAndRemainder(three)));
// [5.0, 2.5]

System.out.println(java.util.Arrays.toString(
        negative.divideAndRemainder(three)));
// [-5.0, -2.5]

System.out.println(java.util.Arrays.toString(
        positive.divideAndRemainder(minusThree)));
// [-5.0, 2.5]

System.out.println(java.util.Arrays.toString(
        negative.divideAndRemainder(minusThree)));
// [5.0, -2.5]
```

Lưu ý:

- q âm khi a và b trái dấu; q dương khi chúng cùng dấu và |a|≥|b|.
- r là 2.5 nếu a=17.5; r là −2.5 nếu a=−17.5.
- Khi a có độ lớn nhỏ hơn |b|, q=0 theo trị số và r=a.
- Không dùng `Math.floor` hay rounding xuống để tự tính q âm; đó sẽ là phép toán khác.

Trong hệ thống kế toán hoặc đo lường, hãy kiểm thử số âm nếu có khả năng phát sinh số dư điều chỉnh/hoàn tiền. Chỉ thử a>0, b>0 thường bỏ sót nhầm lẫn về dấu.

## 7. Scale: q là số nguyên về giá trị nhưng có thể in 5.0 hay 2.00

Mỗi `BigDecimal` được diễn giải qua **unscaled value** và **scale**:

\[
\text{value}=\text{unscaledValue}\times10^{-\text{scale}}.
\]

`new BigDecimal("17.5")` có scale 1; `new BigDecimal("3")` có scale 0. Preferred scale của kết quả `divideToIntegralValue` là hiệu scale của số bị chia và số chia; trong ví dụ này là 1:

```java
BigDecimal q = new BigDecimal("17.5")
        .divideToIntegralValue(new BigDecimal("3"));

System.out.println(q);         // 5.0
System.out.println(q.scale()); // 1
```

Thương **về mặt toán học là số nguyên 5**. Nhưng `BigDecimal` có thể giữ scale 1 và in `5.0` để phù hợp biểu diễn ưu tiên của phép toán.

Ví dụ có hai chữ số phần thập phân:

```java
BigDecimal a = new BigDecimal("10.00");
BigDecimal b = new BigDecimal("4");

BigDecimal[] qr = a.divideAndRemainder(b);
System.out.println(java.util.Arrays.toString(qr));
// [2.00, 2.00]

System.out.println(qr[0].scale()); // 2
System.out.println(qr[1].scale()); // 2
```

Ở đây hai kết quả có scale 2, nhưng nếu ta viết dữ liệu đầu vào là `"10"` thay vì `"10.00"`, dạng in của thương và dư có thể khác.

**Không hứa mọi thương nguyên luôn có scale 0, hay scale luôn bằng đúng hiệu scale.** Preferred scale là một nguyên tắc định dạng/biểu diễn; trong một số phép chia hoặc khi `MathContext` ràng buộc precision, API có thể phải dùng scale khác để biểu diễn đúng thương nguyên.

### equals khác compareTo

`BigDecimal.equals` xét cả giá trị **và scale**. `compareTo` xét thứ tự giá trị số:

```java
BigDecimal x = new BigDecimal("2.00");
BigDecimal y = new BigDecimal("2");

System.out.println(x.equals(y));      // false
System.out.println(x.compareTo(y)==0); // true
```

Để kiểm tra đẳng thức `a=q×b+r` theo **giá trị số**, dùng `compareTo(...)==0`. Nếu hợp đồng còn yêu cầu khớp biểu diễn (scale), kiểm tra thêm `scale()` hoặc dùng `equals` khi đó là chủ đích.

Không tự động `stripTrailingZeros()` mọi kết quả trong ứng dụng tài chính: nó có thể thay đổi scale và cách in dữ liệu, đôi khi thành dạng ký pháp khoa học. Hãy phân biệt **số học chính xác** và **quy tắc biểu diễn**.

## 8. MathContext là gì và liên quan thế nào tới chia thương nguyên?

`MathContext` cấu hình **precision** (số chữ số có nghĩa) và một `RoundingMode`:

```java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext mc = new MathContext(
        4, RoundingMode.HALF_UP);
```

Các overload:

```java
BigDecimal q = a.divideToIntegralValue(b, mc);
BigDecimal r = a.remainder(b, mc);
BigDecimal[] pair = a.divideAndRemainder(b, mc);
```

Đối với ba phương thức này, hãy hiểu `mc` chủ yếu là **giới hạn khả năng biểu diễn phần thương nguyên**. Không được suy rằng `RoundingMode.HALF_UP` sẽ làm tròn `5.833...` thành q=6. Phần nguyên theo quy tắc **cắt về 0** vẫn là số 5.

Một điểm tinh tế từ Javadoc: phần dư tính qua thương nguyên **không bị làm tròn về precision của `MathContext`**; vì vậy giá trị remainder trả về **có thể có nhiều chữ số hơn `mc.getPrecision()`**.

### Ví dụ nếu thương nguyên cần nhiều chữ số hơn precision

```java
BigDecimal a = new BigDecimal("12345");
BigDecimal b = new BigDecimal("2");
MathContext tooSmall = new MathContext(
        3, RoundingMode.DOWN);

try {
    a.divideToIntegralValue(b, tooSmall);
} catch (ArithmeticException ex) {
    System.out.println("precision insufficient");
}
```

Vì phần nguyên của `12345 / 2` là `6172`, cần 4 chữ số có nghĩa để biểu diễn chính xác. `MathContext(3,...)` không thể giữ đúng q, nên `divideToIntegralValue` ném `ArithmeticException` thay vì “làm tròn q=6170” hay “cắt tiếp q=617”.

```java
MathContext enough = new MathContext(
        4, RoundingMode.DOWN);

BigDecimal[] qr = a.divideAndRemainder(b, enough);
System.out.println(java.util.Arrays.toString(qr));
// [6172, 1]
```

**Bản chất:** với overload có MathContext, không có nghĩa API cho phép trả một thương nguyên sai chỉ để vừa precision. Nếu thương nguyên chính xác không thể biểu diễn trong giới hạn đã chọn, nó có thể ném exception.

### RoundingMode không thay định nghĩa của phần dư

```java
BigDecimal a = new BigDecimal("17.5");
BigDecimal b = new BigDecimal("3");

BigDecimal[] qr = a.divideAndRemainder(
        b, new MathContext(2, RoundingMode.HALF_UP));

// q vẫn là 5 về mặt số học, r vẫn là 2.5.
```

Kết quả không phải một phép chia decimal thông thường đã được làm tròn. Khi cần chia ra 5.83 hoặc 5.833, dùng `divide(..., mc)` và hiểu rõ yêu cầu precision của **thương có phần lẻ**.

## 9. MathContext.UNLIMITED và precision = 0

Một `MathContext` có `precision == 0` biểu thị **không giới hạn precision** theo nghĩa của MathContext. Hằng tiện ích:

```java
MathContext unlimited = MathContext.UNLIMITED;
```

Có thể dùng:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");
BigDecimal[] qr = one.divideAndRemainder(
        three, MathContext.UNLIMITED);

System.out.println(java.util.Arrays.toString(qr));
// [0, 1]
```

Nhưng **đừng suy** rằng `one.divide(three, MathContext.UNLIMITED)` sẽ tự sinh vô hạn chữ số hoặc tự chọn rounding. Phép chia decimal không có biểu diễn thập phân hữu hạn chính xác vẫn có thể ném `ArithmeticException` vì không có cách trả kết quả chính xác hữu hạn.

Precision không giới hạn ở đây **không có nghĩa heap, CPU hay size BigDecimal vô hạn**. BigDecimal vẫn bị ràng buộc bởi tài nguyên và giới hạn triển khai.

## 10. remainder với MathContext không nhất thiết vừa precision

Javadoc nêu remainder không phải phép toán làm tròn theo cách hiểu “kết quả phải có nhiều nhất P chữ số”:

```java
BigDecimal r = a.remainder(b, mc);
```

Phương thức này về nguyên tắc tính:

```text
q = a.divideToIntegralValue(b, mc)
r = a - q*b
```

Sau khi xác định q theo điều kiện của context, phần dư được hình thành theo giá trị chính xác từ phép trừ, chứ không bắt buộc bị ép còn `mc.getPrecision()` chữ số.

Ví dụ một phép trừ có scale nhỏ hoặc giá trị dư rất nhiều chữ số sau dấu chấm có thể cần nhiều chữ số có nghĩa hơn q. Nếu muốn làm tròn r sau khi tính, đó là **quyết định nghiệp vụ riêng**; bạn có thể dùng `r.round(mc)` và chấp nhận rằng đẳng thức `a = q×b + r_rounded` có thể không còn đúng tuyệt đối.

### Không dùng context để “giấu” overflow

`BigDecimal` không có overflow theo miền 32/64 bit primitive như `int`/`long`, nhưng nó vẫn có thể ném `ArithmeticException` khi chính xác không phù hợp với `MathContext`, khi chia cho zero, hoặc gặp giới hạn scale. Không nên catch toàn bộ lỗi rồi trả `BigDecimal.ZERO`: giá trị 0 thật và phép toán không hợp lệ là hai trường hợp khác nhau.

## 11. Zero divisor và các trường hợp biên

Mọi phép trong nhóm đều yêu cầu **divisor khác 0**:

```java
BigDecimal ten = BigDecimal.TEN;

// ten.divideToIntegralValue(BigDecimal.ZERO); // ArithmeticException
// ten.remainder(BigDecimal.ZERO);             // ArithmeticException
// ten.divideAndRemainder(BigDecimal.ZERO);    // ArithmeticException
```

Kiểm tra trước nếu đầu vào có thể không hợp lệ:

```java
static BigDecimal[] split(BigDecimal a, BigDecimal b) {
    if (b.signum() == 0) {
        throw new IllegalArgumentException(
                "divisor must not be zero");
    }
    return a.divideAndRemainder(b);
}
```

Đoạn mã này giả định a và b không null; nếu API nhận dữ liệu tùy ý, cần kiểm tra null trước khi gọi `signum()` và `divideAndRemainder()`.

### Số bị chia bằng 0

```java
BigDecimal a = BigDecimal.ZERO;
BigDecimal b = new BigDecimal("7");
BigDecimal[] qr = a.divideAndRemainder(b);

System.out.println(qr[0].compareTo(BigDecimal.ZERO) == 0); // true
System.out.println(qr[1].compareTo(BigDecimal.ZERO) == 0); // true
```

Scale và cách in số 0 có thể phụ thuộc cách tạo toán hạng; hãy so sánh **giá trị số** bằng `compareTo` khi đó mới là mục tiêu.

### |a| < |b|

```java
BigDecimal a = new BigDecimal("2.5");
BigDecimal b = new BigDecimal("8");

BigDecimal q = a.divideToIntegralValue(b);
BigDecimal r = a.remainder(b);

System.out.println(q.compareTo(BigDecimal.ZERO)==0); // true
System.out.println(r.compareTo(a)==0);                // true
```

Nếu độ lớn của số bị chia nhỏ hơn độ lớn divisor, thương nguyên có giá trị 0 và phần dư có giá trị đúng bằng số bị chia. Không nhầm với thương decimal `0.3125`.

## 12. Số học tài chính: chia nhóm khác chia tiền bình quân

Với `BigDecimal` trong tài chính, không phải lúc nào cũng nên chọn `divideToIntegralValue`:

- Nếu mục tiêu là **số nhóm nguyên** và **dư giữ lại**, phép này đúng.
- Nếu mục tiêu là chia tiền **đều cho nhiều người**, bạn có thể cần quy tắc làm tròn theo đơn vị tiền nhỏ nhất.
- Nếu mục tiêu là tính thuế, lãi suất hoặc tỷ lệ %, thường cần thương decimal và `RoundingMode` theo hợp đồng.

Ví dụ chia 10.00 đơn vị theo nhóm 4.00 đơn vị:

```java
BigDecimal available = new BigDecimal("10.00");
BigDecimal batchSize = new BigDecimal("4.00");

BigDecimal[] qr = available.divideAndRemainder(batchSize);
// Giá trị số của thương nguyên = 2, phần dư = 2.00.
```

Đây là cách đếm số **nhóm đầy đủ** và lượng còn lại. Nó không nói rằng “mỗi nhóm nhận 2.50 đơn vị”: đó là bài toán chia đều 10.00 thành bốn phần, cần `divide` theo đơn vị thích hợp.

Nếu cần bảo toàn đúng scale tiền tệ (ví dụ luôn 2 chữ số), chỉ áp dụng `setScale(2,...)` sau khi xác định ngữ nghĩa số học và quy tắc rounding, không giả định scale do `divideAndRemainder` sinh ra luôn bằng scale hiển thị nghiệp vụ.

## 13. Kiểm tra tính đúng bằng đẳng thức a = q*b + r

Đây là **invariant** hữu ích nhất khi viết unit test:

```java
static boolean invariantHolds(BigDecimal a, BigDecimal b) {
    if (b.signum() == 0) return false;

    BigDecimal[] qr = a.divideAndRemainder(b);
    BigDecimal rebuilt = qr[0].multiply(b).add(qr[1]);

    return rebuilt.compareTo(a) == 0;
}
```

Ngoài ra kiểm tra:

```java
BigDecimal[] qr = a.divideAndRemainder(b);

boolean smallRemainder =
        qr[1].abs().compareTo(b.abs()) < 0;

boolean signCompatible =
        qr[1].signum() == 0
        || qr[1].signum() == a.signum();
```

Ba kiểm tra này đặc biệt hữu ích với số âm, divisor âm và số có scale khác nhau. **Không nhất thiết dùng `equals`** cho đẳng thức reconstructed, bởi scale của giá trị tái dựng có thể khác scale của a dù hai giá trị số học bằng nhau.

### Kiểm thử với property-based approach

Có thể sinh nhiều cặp `a,b` có scale khác nhau (b≠0), bao gồm các số âm và các số như `0.00`/`1E+3`, rồi kiểm tra các invariant trên.

Khi chạy overload với `MathContext`, hãy phân biệt hai trường hợp:

- Phép toán trả kết quả → kiểm tra invariant.
- Phép toán ném `ArithmeticException` vì precision không cho phép thương nguyên → đây có thể là **hành vi đúng của contract**, không phải thất bại của invariant.

## 14. Java 17+ demo hoàn chỉnh

Tạo tệp **`BigDecimalQuotientRemainderDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.Arrays;

public class BigDecimalQuotientRemainderDemo {

    private static void show(String label,
            BigDecimal a, BigDecimal b) {
        BigDecimal[] qr = a.divideAndRemainder(b);
        BigDecimal rebuilt = qr[0].multiply(b).add(qr[1]);

        System.out.println(label + " -> q=" + qr[0]
                + ", r=" + qr[1]
                + ", identity=" + (rebuilt.compareTo(a) == 0));
    }

    private static BigDecimal euclideanMod(
            BigDecimal a, BigDecimal modulus) {
        if (modulus.signum() <= 0) {
            throw new IllegalArgumentException(
                    "modulus must be positive");
        }
        BigDecimal r = a.remainder(modulus);
        return r.signum() < 0 ? r.add(modulus) : r;
    }

    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("17.5");
        BigDecimal b = new BigDecimal("3");

        show("positive", a, b);
        show("negative dividend", a.negate(), b);
        show("negative divisor", a, b.negate());
        show("both negative", a.negate(), b.negate());

        System.out.println("integral = "
                + a.divideToIntegralValue(b));
        System.out.println("remainder = " + a.remainder(b));
        System.out.println("euclidean mod(-17.5,3) = "
                + euclideanMod(a.negate(), b));

        BigDecimal[] scaled =
                new BigDecimal("10.00")
                .divideAndRemainder(new BigDecimal("4"));
        System.out.println("scaled = " + Arrays.toString(scaled));
        System.out.println("quotient scale = "
                + scaled[0].scale());
        System.out.println("2.00 equals 2 = "
                + new BigDecimal("2.00").equals(
                        new BigDecimal("2")));
        System.out.println("2.00 compareTo 2 = "
                + (new BigDecimal("2.00").compareTo(
                        new BigDecimal("2")) == 0));

        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");
        System.out.println("1 / 3 qr = " +
                Arrays.toString(one.divideAndRemainder(three)));

        try {
            one.divide(three);
        } catch (ArithmeticException ex) {
            System.out.println("exact 1 / 3 = rejected");
        }

        System.out.println("rounded 1 / 3 = " +
                one.divide(three, 2, RoundingMode.HALF_UP));

        BigDecimal numerator = new BigDecimal("12345");
        BigDecimal denominator = new BigDecimal("2");

        try {
            numerator.divideToIntegralValue(denominator,
                    new MathContext(3, RoundingMode.DOWN));
        } catch (ArithmeticException ex) {
            System.out.println("precision 3 = rejected");
        }

        BigDecimal[] withContext =
                numerator.divideAndRemainder(denominator,
                    new MathContext(4, RoundingMode.DOWN));
        System.out.println("precision 4 = "
                + Arrays.toString(withContext));

        System.out.println("unlimited 1/3 qr = "
                + Arrays.toString(one.divideAndRemainder(
                        three, MathContext.UNLIMITED)));

        try {
            a.divideAndRemainder(BigDecimal.ZERO);
        } catch (ArithmeticException ex) {
            System.out.println("zero divisor = rejected");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 BigDecimalQuotientRemainderDemo.java
java BigDecimalQuotientRemainderDemo
```

**Kết quả dự kiến:**

```text
positive -> q=5.0, r=2.5, identity=true
negative dividend -> q=-5.0, r=-2.5, identity=true
negative divisor -> q=-5.0, r=2.5, identity=true
both negative -> q=5.0, r=-2.5, identity=true
integral = 5.0
remainder = 2.5
euclidean mod(-17.5,3) = 0.5
scaled = [2.00, 2.00]
quotient scale = 2
2.00 equals 2 = false
2.00 compareTo 2 = true
1 / 3 qr = [0, 1]
exact 1 / 3 = rejected
rounded 1 / 3 = 0.33
precision 3 = rejected
precision 4 = [6172, 1]
unlimited 1/3 qr = [0, 1]
zero divisor = rejected
```

### Những điểm chương trình xác minh

1. Cả bốn tổ hợp dấu đều tuân theo công thức `a=q×b+r`, và phần dư khác 0 theo dấu số bị chia.
2. `remainder` của số âm không nhất thiết không âm; muốn modulo Euclid phải chuẩn hóa riêng với môđun dương.
3. BigDecimal giữ scale trong một số phép tính: `10.00/4` cho q=2.00, r=2.00; `equals` khác `compareTo`.
4. `divideAndRemainder(1,3)` không cần biểu diễn thương decimal vô hạn, nhưng `divide(3)` chính xác thì phải báo lỗi.
5. `MathContext(3)` không đủ để biểu diễn thương nguyên 6172; `MathContext(4)` cho kết quả.
6. `MathContext.UNLIMITED` không biến `divideAndRemainder` thành phép chia decimal vô hạn.
7. Chia cho 0 bị từ chối bằng `ArithmeticException`.

## 15. Lỗi thường gặp và cách sửa

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “divideToIntegralValue trả int” | Trả `BigDecimal` chứa một giá trị số nguyên |
| “Integral quotient luôn là Math.floor(a/b)” | Cắt về phía 0; với số âm khác floor |
| “remainder luôn không âm” | Phần dư BigDecimal có thể âm; dấu theo số bị chia |
| “BigDecimal.remainder giống BigInteger.mod” | Không; BigInteger.mod cần modulus dương và trả modulo không âm |
| “divideAndRemainder trả thương decimal và dư” | Phần tử 0 là **thương nguyên**, phần tử 1 là remainder |
| “divide(BigDecimal) và divideToIntegralValue giống nhau” | Một bên cần thương decimal chính xác, bên kia chỉ lấy phần nguyên |
| “Nếu 1/3 không chia chính xác được thì lấy dư cũng lỗi” | `1.divideAndRemainder(3)` vẫn cho [0,1] |
| “Có MathContext.HALF_UP thì q=5.833... được làm tròn thành 6” | q vẫn theo truncation về 0, không làm tròn thương decimal thành 6 |
| “MathContext precision nhỏ thì kết quả bị cắt còn đủ chữ số” | Nếu không thể biểu diễn thương nguyên đúng, có thể ném `ArithmeticException` |
| “remainder(mc) luôn có ≤ mc.precision chữ số” | Phần dư không tự bị làm tròn theo precision; có thể dài hơn |
| “MathContext.UNLIMITED biến mọi phép chia thành chính xác” | Chia decimal lặp vô hạn vẫn không biểu diễn hữu hạn |
| “Thương nguyên phải có scale 0” | Có thể là 5.0 hoặc 2.00 tùy preferred scale |
| “2.00.equals(2) là true” | false vì scale khác; `compareTo` bằng 0 |
| “Trả kết quả rồi BigDecimal ban đầu bị chỉnh sửa” | BigDecimal là immutable; các phương thức trả giá trị mới |
| “Chia cho 0 chỉ tạo số Infinity” | BigDecimal không có Infinity; ném `ArithmeticException` |
| “Dùng rounding cho remainder mà không ảnh hưởng invariant” | Làm tròn phần dư có thể phá đẳng thức a=q*b+r |
| “Cần chia nhóm nguyên thì phải gọi divide trước” | Có thể dùng divideAndRemainder trực tiếp, tránh thương decimal lặp vô hạn |

## 16. Bài tập và lời giải

**Bài 1.** Với a=17.5 và b=3, viết q và r theo API BigDecimal.  
**Đáp án:** q có giá trị 5 (có thể hiển thị 5.0), r=2.5; dùng `a.divideAndRemainder(b)` lấy cả hai.

**Bài 2.** Với a=−17.5, b=3, vì sao q không phải −6?  
**Đáp án:** `divideToIntegralValue` cắt thương về 0 nên q=−5; r=−2.5. Nếu dùng floor sẽ là một phép toán khác.

**Bài 3.** Với a=17.5 và b=−3, dấu r là gì?  
**Đáp án:** r=+2.5, vì phần dư khác 0 mang dấu số bị chia a, không phải dấu divisor b.

**Bài 4.** `BigDecimal.ONE.divide(new BigDecimal("3"))` và `BigDecimal.ONE.remainder(new BigDecimal("3"))` có giống hành vi không?  
**Đáp án:** Không. divide không rounding yêu cầu thương decimal kết thúc chính xác nên ném lỗi; remainder trả 1.

**Bài 5.** Kết quả `new BigDecimal("10.00").divideAndRemainder(new BigDecimal("4"))`?  
**Đáp án:** [2.00, 2.00], theo biểu diễn scale của ví dụ; giá trị thương nguyên là 2, dư là 2.

**Bài 6.** Dùng `divideAndRemainder` thì phần tử nào chứa q, phần tử nào chứa r?  
**Đáp án:** `qr[0]` là q, `qr[1]` là r.

**Bài 7.** Vì sao `a.remainder(b, new MathContext(3))` có thể ném ngoại lệ?  
**Đáp án:** Vì thuật toán cần tính thương nguyên theo MathContext; nếu thương nguyên có phần bắt buộc không thể biểu diễn dưới precision=3, phép toán có thể ném ArithmeticException.

**Bài 8.** Dùng `MathContext(3, RoundingMode.UP)` với 12345/2 có làm q tròn thành 6180 không?  
**Đáp án:** Không. Thương nguyên chính xác theo truncation là 6172; giới hạn precision=3 không chứa đủ số chữ số nên có thể ném ArithmeticException.

**Bài 9.** Nếu cần phần dư Euclid của −17.5 theo modulus dương 3, làm thế nào?  
**Đáp án:** Lấy `r = a.remainder(m)` (−2.5), rồi nếu r âm thì `r.add(m)` (0.5).

**Bài 10.** Vì sao test identity bằng `rebuilt.equals(a)` có thể trả false dù số học đúng?  
**Đáp án:** Vì BigDecimal.equals xét thêm scale; dùng `rebuilt.compareTo(a)==0` nếu kiểm tra bằng nhau theo trị số.

**Bài 11.** Muốn biểu diễn phần nguyên thương bằng BigInteger, chọn API nào sau khi chia?  
**Đáp án:** `a.divideToIntegralValue(b).toBigIntegerExact()`, vì phần thương không có thành phần phân số về giá trị.

**Bài 12.** Nếu input từ người dùng có divisor=0, nên làm gì?  
**Đáp án:** Validate và báo lỗi theo hợp đồng; API chia/nhiều phép remainder sẽ ném ArithmeticException chứ không trả Infinity.

## 17. Checklist trước khi dùng ba phương thức

1. **Đọc đúng tên:** `divideToIntegralValue` cho thương nguyên, `remainder` cho phần dư, `divideAndRemainder` cho cả hai.
2. **Chọn quy tắc nguyên:** q cắt về 0, không phải floor cho số âm.
3. **Không nhầm remainder với modulo không âm.** Nếu cần modulo Euclid, kiểm tra modulus dương và chuẩn hóa r.
4. **Đảm bảo divisor khác 0**; có chính sách rõ ràng cho null và dữ liệu sai.
5. **Đừng dùng divideToIntegralValue thay divide một cách máy móc** nếu nghiệp vụ cần thương decimal/làm tròn.
6. **Dùng MathContext đúng mục tiêu:** precision là giới hạn kết quả thương nguyên, không tự chọn q đã làm tròn.
7. **Remainder với context có thể nhiều chữ số hơn precision**; không lén làm tròn nếu phải giữ invariant.
8. **Kiểm tra scale và equals:** trị số nguyên không nhất thiết scale 0; dùng compareTo nếu chỉ kiểm tra giá trị.
9. **Kiểm tra invariant a=q*b+r**, độ lớn phần dư và dấu phần dư trên dữ liệu dương/âm.
10. **Khi cần cả hai, ưu tiên divideAndRemainder** cho ý định rõ ràng và có thể dùng lại phép tính.
11. **Với kết quả quy về int/long**, dùng chuyển đổi Exact để phát hiện vượt miền.
12. **Tôn trọng đơn vị đo và số tiền:** chia thành nhóm nguyên khác chia đều thành tiền decimal có rounding.
13. **Kiểm thử trường hợp biên:** 0, divisor âm, a âm, |a|<|b|, 1/3, scale khác nhau và precision nhỏ.

### Tài liệu tham khảo

- [BigDecimal — Javadoc Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [MathContext — Javadoc Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html)
- [RoundingMode — Javadoc Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html)

**Ghi nhớ:** Cả ba phương thức lấy **thương nguyên theo hướng về 0** và phần dư r thỏa `a=q×b+r`. `remainder` có thể âm và không đồng nghĩa modulo Euclid; `divideAndRemainder` trả mảng `[q,r]`. Với `MathContext`, API không tự làm tròn thương nguyên cho vừa precision mà có thể ném ngoại lệ. Luôn kiểm tra divisor, scale và ý nghĩa nghiệp vụ của việc giữ phần dư.
