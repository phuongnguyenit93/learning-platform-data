# `exp`, `log`, `log10`, `expm1` và `log1p` trong Java

Java cung cấp năm hàm số mũ/logarit thường gặp trong `java.lang.Math` và `java.lang.StrictMath`. Chúng có quan hệ toán học gần nhau, nhưng **không thể dùng thay thế máy móc** trong tính toán dấu phẩy động:

- `Math.exp(x)` tính \(e^x\).
- `Math.log(x)` tính \(\ln(x)\), logarit tự nhiên cơ số \(e\).
- `Math.log10(x)` tính \(\log_{10}(x)\), logarit cơ số 10.
- `Math.expm1(x)` tính \(e^x-1\) **trực tiếp với độ chính xác tốt hơn** khi \(x\) rất gần 0.
- `Math.log1p(x)` tính \(\ln(1+x)\) **trực tiếp với độ chính xác tốt hơn** khi \(x\) rất gần 0.

Cả năm đều nhận một tham số `double` và trả `double`. Nếu truyền `int` hoặc `float`, Java có thể widening sang `double` trước lời gọi. Các hàm không trả giá trị số nguyên chính xác tùy ý; chúng làm việc trong giới hạn IEEE 754 của `double`.

**Mục tiêu học tập:** chọn đúng hàm, hiểu miền xác định và các trường hợp `NaN`/`Infinity`/`-0.0`, tránh mất độ chính xác khi tự viết `exp(x)-1` hoặc `log(1+x)`, và biết lúc nào cần `StrictMath` thay cho `Math`.

## 1. Bảng tổng quan và quan hệ toán học

| Java API | Biểu thức toán học | Điều kiện để kết quả thực hữu hạn thông thường | Trường hợp dễ nhớ |
| --- | --- | --- | --- |
| `Math.exp(x)` | \(e^x\) | \(x\) hữu hạn và không vượt/underflow miền biểu diễn đầu ra | `exp(0.0) = 1.0` |
| `Math.log(x)` | \(\ln(x)\) | \(x > 0\), hữu hạn | `log(1.0) = 0.0` |
| `Math.log10(x)` | \(\log_{10}(x)\) | \(x > 0\), hữu hạn | `log10(1000.0) = 3.0` |
| `Math.expm1(x)` | \(e^x - 1\) | \(x\) hữu hạn, kết quả trong phạm vi | `expm1(0.0) = 0.0` |
| `Math.log1p(x)` | \(\ln(1+x)\) | \(x > -1\), hữu hạn | `log1p(0.0) = 0.0` |

Các điều kiện hữu hạn nêu ở bảng là tình huống **thường có kết quả hữu hạn**; `exp` và `expm1` vẫn có thể tràn hoặc underflow ngay cả khi tham số `double` hữu hạn. `log`, `log10` và `log1p` cũng định nghĩa cách xử lý đầu vào ở **ranh giới miền**, không đơn giản ném exception như phép tính số nguyên.

Cơ số \(e\) xấp xỉ `2.718281828459045`, có hằng `Math.E`:

```java
System.out.println(Math.E);                  // 2.718281828459045
System.out.println(Math.exp(0.0));           // 1.0
System.out.println(Math.log(1.0));           // 0.0
System.out.println(Math.log10(1000.0));      // 3.0
```

Dùng các ví dụ số học quen thuộc để nắm ý nghĩa, nhưng **đừng suy ra mọi phép ghép hàm sẽ cho chính xác tuyệt đối** vì phần lớn phép tính đều làm tròn theo `double`.

## 2. `Math.exp(x)`: hàm mũ cơ số `e`

`Math.exp(x)` tính \(e^x\); kết quả toán học luôn **dương** đối với mọi \(x\) thực hữu hạn. Các tính chất:

- `Math.exp(0.0)` và `Math.exp(-0.0)` đều bằng `1.0`.
- `Math.exp(1.0)` xấp xỉ \(e\).
- `Math.exp(Math.log(a))` xấp xỉ `a` khi `a > 0` và không gặp giới hạn làm tròn/miền.
- `Math.exp(x + y)` tương ứng \(e^x e^y\) về mặt toán học, nhưng hai cách tính trên `double` **có thể khác do sai số hoặc overflow**.

```java
double rate = 0.05;
double years = 10.0;
double growthFactor = Math.exp(rate * years); // e^0.5, hệ số tăng trưởng
```

Đây là đoạn minh họa trong một method, không phải chương trình Java độc lập. Mô hình \(e^{rt}\) thường dùng cho tăng trưởng liên tục; ứng dụng phải xác định rõ đơn vị thời gian và ý nghĩa của `rate`.

### Overflow và underflow của `exp`

`double` không chứa được mọi giá trị của \(e^x\). Ví dụ:

```java
System.out.println(Math.exp(800.0));  // Infinity
System.out.println(Math.exp(-800.0)); // 0.0
```

`Math.exp(800.0)` vượt độ lớn hữu hạn của `double` nên cho dương vô cực. `Math.exp(-800.0)` là giá trị toán học dương nhưng quá nhỏ để thể hiện, nên làm tròn thành dương zero.

Vì thế **`Math.exp(x) == 0.0` không nhất thiết nói \(e^x=0\) về toán học**. Với phép tính xác suất cực nhỏ, log-likelihood hoặc số liệu có nhiều bậc độ lớn, đôi khi nên giữ dữ liệu ở **miền logarit** thay vì chuyển sang số mũ quá sớm.

## 3. `Math.log(x)`: logarit tự nhiên

`Math.log(x)` tính \(\ln(x)\), hàm ngược của \(e^x\) trên miền số thực dương:

```java
double x = 3.0;
double logX = Math.log(x);
double approximatelyOriginal = Math.exp(logX);
```

Do làm tròn, `approximatelyOriginal` không được bảo đảm có bit giống hoàn toàn `x`. Không nên viết test khẳng định `Math.exp(Math.log(x)) == x` cho mọi `double`.

Một số quy tắc:

- `Math.log(1.0)` trả `0.0`.
- Nếu `0 < x < 1`, \(\ln(x)\) âm.
- Nếu `x > 1`, \(\ln(x)\) dương.
- `Math.log(+0.0)` và `Math.log(-0.0)` đều trả `-Infinity`.
- `Math.log(x)` với `x < 0` trả `NaN`, vì không có logarit thực.
- `Math.log(Double.POSITIVE_INFINITY)` trả `Infinity`.

```java
System.out.println(Math.log(1.0));           // 0.0
System.out.println(Math.log(0.0));           // -Infinity
System.out.println(Math.log(-1.0));          // NaN
System.out.println(Math.log(Double.POSITIVE_INFINITY)); // Infinity
```

**Không ném `ArithmeticException` cho các đầu vào miền sai thông thường.** Đây là hàm dấu phẩy động; ứng dụng cần kiểm tra kết quả hoặc đầu vào nếu không cho phép NaN/vô cực.

Logarit còn giúp biến tích thành tổng về mặt toán học: \(\ln(ab)=\ln(a)+\ln(b)\) với \(a,b>0\). Điều này hữu ích khi tích của nhiều giá trị dương quá lớn hoặc quá nhỏ, nhưng cần cân nhắc sai số khi lấy log và khi quy đổi lại.

## 4. `Math.log10(x)`: logarit cơ số 10

`Math.log10(x)` trả \(\log_{10}(x)\). Nó có cùng miền số thực dương với `log`, nhưng **cơ số khác nhau**:

```java
System.out.println(Math.log10(1.0));    // 0.0
System.out.println(Math.log10(10.0));   // 1.0
System.out.println(Math.log10(1000.0)); // 3.0
```

Dùng `log10` khi vấn đề liên quan số bậc độ lớn thập phân, thang đo cơ số 10 hoặc tỷ lệ theo lũy thừa của 10. Dùng `log` khi công thức cần logarit tự nhiên, ví dụ liên tục, giải tích và nhiều mô hình xác suất.

Quan hệ toán học:

\[
\log_{10}(x)=\frac{\ln(x)}{\ln(10)}.
\]

Đừng nhất thiết triển khai `Math.log(x) / Math.log(10.0)` thay cho `Math.log10(x)`: Java đã có API trực tiếp, và các cách tính dấu phẩy động khác nhau có thể khác ở chữ số cuối.

**Đổi cơ số tổng quát:** \(\log_b(x)=\ln(x)/\ln(b)\), với `x > 0`, `b > 0` và `b != 1`:

```java
double base = 2.0;
double value = 8.0;
double logBase2 = Math.log(value) / Math.log(base);
```

Đây là công thức tính logarit cơ số 2 từ hai lời gọi `log`; kết quả là xấp xỉ. Khi `base` cực gần 1, mẫu số \(\ln(base)\) nhỏ nên bài toán có thể nhạy với sai số; cần đánh giá độ ổn định thay vì chỉ thay bằng một phép chia.

## 5. Vì sao `Math.exp(x) - 1.0` có thể mất precision?

Với \(x\) gần 0, \(e^x\) gần 1. Nếu gọi `Math.exp(x)`, kết quả bị làm tròn sang lưới `double` quanh 1. Sau đó trừ 1 có thể làm **mất toàn bộ tín hiệu rất nhỏ**.

Chọn:

```java
double x = 1e-16;
double naive = Math.exp(x) - 1.0;
double stable = Math.expm1(x);

System.out.println(naive);  // 0.0
System.out.println(stable); // 1.0E-16
```

Về toán học, \(e^{10^{-16}}-1\) xấp xỉ \(10^{-16}\), nhưng `Math.exp(1e-16)` được làm tròn thành `1.0` ở độ chính xác `double`, khiến `1.0-1.0` bằng 0. Đây là **cancellation** (mất thông tin khi trừ hai số gần nhau).

`Math.expm1(x)` tính \(e^x-1\) bằng thuật toán đặc thù, **không đơn thuần thực hiện phép Java `Math.exp(x) - 1` theo cùng các bước**. Nhờ đó hàm giữ được độ chính xác cao khi x rất nhỏ.

### Chọn `expm1` theo ý nghĩa công thức

Nếu công thức cần **hệ số tăng trưởng** \(e^r\), dùng `exp(r)`. Nếu cần **mức tăng so với 1** \(e^r-1\), dùng `expm1(r)`:

```java
double continuousRate = 1e-12;
double relativeIncrease = Math.expm1(continuousRate);
```

Với lãi suất rất nhỏ hoặc biến đổi phần trăm, `relativeIncrease` là đại lượng cần thiết. Dùng `exp` rồi trừ 1 có thể mất chữ số có nghĩa.

Ở đầu vào rất âm, `Math.expm1(-1000.0)` trả `-1.0` vì \(e^{-1000}-1\) làm tròn thành -1. Trái lại `Math.exp(-1000.0)` làm tròn thành zero. Đây không phải mâu thuẫn, vì **hai hàm trả hai đại lượng khác nhau**.

## 6. Vì sao `Math.log(1.0 + x)` có thể mất precision?

Cơ chế tương tự xảy ra khi \(x\) rất gần 0. Phép `1.0 + x` có thể được làm tròn thành đúng `1.0` **trước khi** `Math.log` được gọi:

```java
double x = 1e-16;
double naive = Math.log(1.0 + x);
double stable = Math.log1p(x);

System.out.println(naive);  // 0.0
System.out.println(stable); // 1.0E-16
```

Về toán học, \(\ln(1+x) \approx x\) khi \(x\) nhỏ. `Math.log(1.0 + x)` không biết rằng giá trị đầu vào `1.0` là kết quả làm tròn của tổng `1.0 + 1e-16`; thông tin đã mất **trước khi gọi log**.

`Math.log1p(x)` tính \(\ln(1+x)\) bằng thuật toán giữ precision cho x nhỏ. Nó thích hợp trong:

- Công thức lợi suất logarit \(\ln(1+r)\) với tỷ lệ biến động `r` rất nhỏ.
- Xử lý xác suất và các biến đổi được biểu diễn theo phần thay đổi quanh 1.
- Thuật toán cần logarit của tổng `1+x` mà `x` là một đầu vào độc lập nhỏ.

Ví dụ tính *log-return*:

```java
double smallReturn = 1e-12;
double logReturn = Math.log1p(smallReturn);
```

Không nên dùng `log1p` chỉ vì muốn lấy logarit thông thường: `Math.log1p(100.0)` là \(\ln(101)\), **khác** `Math.log(100.0)` là \(\ln(100)\).

## 7. Miền xác định: `log(x)` khác `log1p(x)`

Hai hàm logarit có miền số thực khác nhau:

| Hàm | Đầu vào cho giá trị thực thông thường | Điểm ranh giới | Phía không hợp lệ |
| --- | --- | --- | --- |
| `Math.log(x)` | `x > 0.0` | `x == ±0.0` → `-Infinity` | `x < 0.0` → `NaN` |
| `Math.log10(x)` | `x > 0.0` | `x == ±0.0` → `-Infinity` | `x < 0.0` → `NaN` |
| `Math.log1p(x)` | `x > -1.0` | `x == -1.0` → `-Infinity` | `x < -1.0` → `NaN` |

`Math.log1p(-0.5)` là giá trị hữu hạn âm vì `1-0.5 = 0.5 > 0`, còn `Math.log(-0.5)` trả NaN.

```java
System.out.println(Math.log1p(-1.0)); // -Infinity
System.out.println(Math.log1p(-2.0)); // NaN
System.out.println(Math.log(-1.0));   // NaN
```

Dấu zero là một trường hợp đặc biệt:

```java
System.out.println(Math.log1p(-0.0)); // -0.0
System.out.println(Math.expm1(-0.0)); // -0.0
System.out.println(Math.log(-0.0));   // -Infinity
```

`log1p(-0.0)` và `expm1(-0.0)` **giữ âm zero**. Trong khi đó `log(-0.0)` trả âm vô cực, vì logarit tại giá trị zero ở ranh giới miền. Không được suy luận rằng hai hàm có thể dùng thay nhau chỉ vì x gần 0.

Nếu kết quả phải hữu hạn, hãy kiểm tra miền đầu vào **và** kiểm tra đầu ra; các quy tắc đặc biệt có thể cho `Infinity`/`NaN` mà không phát sinh exception.

## 8. Các trường hợp `Infinity`, `NaN` và overflow/underflow

Với `double`, năm hàm có hành vi số thực đặc biệt. Bảng sau nêu các kết quả đáng nhớ:

| Đầu vào | `exp(x)` | `log(x)` | `log10(x)` | `expm1(x)` | `log1p(x)` |
| --- | --- | --- | --- | --- | --- |
| `+0.0` | `1.0` | `-Infinity` | `-Infinity` | `+0.0` | `+0.0` |
| `-0.0` | `1.0` | `-Infinity` | `-Infinity` | `-0.0` | `-0.0` |
| `+Infinity` | `+Infinity` | `+Infinity` | `+Infinity` | `+Infinity` | `+Infinity` |
| `-Infinity` | `+0.0` | `NaN` | `NaN` | `-1.0` | `NaN` |
| `NaN` | `NaN` | `NaN` | `NaN` | `NaN` | `NaN` |
| `-1.0` | Dương hữu hạn | `NaN` | `NaN` | Âm hữu hạn | `-Infinity` |

Lưu ý: `Math.exp(-Infinity)` là **dương zero**, không phải âm zero. `Math.expm1(-Infinity)` là -1.0. `Math.log1p(-Infinity)` là NaN vì \(1+(-\infty)\) không thuộc miền logarit thực dương.

### Không có exception tự động cho log âm và exp overflow

`Math.log(-2.0)` không ném `IllegalArgumentException`; nó trả `NaN`. `Math.exp(800.0)` không ném `ArithmeticException`; nó trả `Infinity`. Đó là giá trị dấu phẩy động đặc biệt theo quy tắc API.

Để phân loại:

```java
double result = Math.exp(800.0);
System.out.println(Double.isInfinite(result)); // true
System.out.println(Double.isFinite(result));   // false
```

`Double.isFinite` chỉ nói kết quả có hữu hạn hay không. Nó không bảo đảm **không mất precision**, và `0.0` do underflow vẫn được coi là hữu hạn. Nếu cần ngăn underflow hoặc kiểm soát độ chính xác tương đối, phải phân tích miền đầu vào và thuật toán cụ thể.

## 9. Độ chính xác: `Math` và `StrictMath`

Cả `Math` và `StrictMath` cung cấp `exp`, `log`, `log10`, `expm1`, `log1p` với ý nghĩa và các trường hợp đặc biệt tương ứng.

- **`Math`:** API chuẩn cho tính toán thông thường; những hàm này có các yêu cầu về độ chính xác như sai số tối đa khoảng **1 ulp** và tính chất *semi-monotonic* theo đặc tả từng phương thức. JVM có thể sử dụng triển khai tối ưu.
- **`StrictMath`:** thiết kế nhằm đem lại kết quả có tính tái lập giữa các nền tảng cho các hàm được chỉ định, dựa trên quy tắc/thuật toán được chuẩn hóa. Nó không có nghĩa luôn gần kết quả toán học hơn `Math` ở mọi đầu vào.
- Từ Java 17, biểu thức dấu phẩy động Java đã có ngữ nghĩa luôn nghiêm ngặt theo thay đổi ngôn ngữ; điều này **không làm `Math` và `StrictMath` trở thành cùng một API hoặc bắt buộc trả cùng mọi bit**.

Ví dụ:

```java
double fastOrDefault = Math.exp(1.0);
double reproducible = StrictMath.exp(1.0);

String first = String.format(java.util.Locale.ROOT,
        "%.6f", fastOrDefault);
String second = String.format(java.util.Locale.ROOT,
        "%.6f", reproducible);
// Cả hai có thể hiển thị "2.718282" khi format 6 số sau dấu chấm.
```

**Không nên khẳng định `Math.exp(x) == StrictMath.exp(x)` luôn true**, cũng không tuyên bố `StrictMath` luôn nhanh/chậm hơn trên mọi JVM; đánh giá độ chính xác, tính tái lập và hiệu năng theo hợp đồng và môi trường.

`StrictMath.expm1`/`StrictMath.log1p` vẫn hữu ích cho mục đích **ổn định phép tính gần 0**. Yếu tố chọn `expm1` thay `exp-1`, hoặc `log1p` thay `log(1+x)`, là công thức số học cần tính, không chỉ tên class.

## 10. Những công thức thường áp dụng và giới hạn

### Tính tăng trưởng nhỏ

Nếu cần phần tăng \(e^{rt}-1\):

```java
double rateTimesTime = 1e-12;
double relativeGrowth = Math.expm1(rateTimesTime);
```

`relativeGrowth` giữ được tín hiệu nhỏ tốt hơn `Math.exp(rateTimesTime)-1.0`. Nếu chỉ cần hệ số nhân \(e^{rt}\), dùng `Math.exp(rateTimesTime)`.

### Lợi suất logarit

Nếu có phần thay đổi tương đối `r`, với `r > -1`:

```java
double r = 1e-12;
double logReturn = Math.log1p(r);
```

Nếu `r == -1`, kết quả là `-Infinity`. Nếu `r < -1`, kết quả là `NaN`. Hợp đồng nghiệp vụ có thể yêu cầu từ chối dữ liệu không phù hợp trước khi gọi hàm.

### Ghép hai hàm là phép đảo gần đúng, không bảo đảm chính xác từng bit

Về toán học, với điều kiện phù hợp:

\[
\ln(e^x)=x,\qquad e^{\ln(x)}=x \quad(x>0).
\]

Tuy nhiên với số học dấu phẩy động:

- `Math.log(Math.exp(800.0))` trả `Infinity` vì `exp(800)` đã overflow.
- `Math.log(Math.exp(-800.0))` trả `-Infinity` vì `exp(-800)` đã underflow về 0.
- Với `x` nhỏ, `Math.log(Math.exp(x))` có thể trả 0 thay vì x; `Math.log1p(Math.expm1(x))` có thể giữ x tốt hơn gần 0.
- Với x dương bình thường, `Math.exp(Math.log(x))` vẫn là xấp xỉ; không dùng so sánh `==` làm bảo đảm toán học tuyệt đối.

### Tính trên miền log tránh tràn tích số

Nếu nhiều hệ số dương rất nhỏ, có thể cộng `Math.log(p)` thay vì nhân tất cả trực tiếp:

```java
double p = 1e-200;
double q = 1e-200;
double directProduct = p * q;      // underflow: 0.0
double logProduct = Math.log(p) + Math.log(q); // hữu hạn
```

Đây là chiến lược lưu **log của tích**, không tự động khôi phục được tích ban đầu dưới dạng `double` nếu nó vẫn nhỏ hơn miền biểu diễn. Với mô hình xác suất và các thuật toán thống kê, đây thường là lợi ích thực tế.

## 11. Chương trình Java 17+ chạy độc lập

Tạo file **`ExpLogDemo.java`**:

```java
import java.util.Locale;

public class ExpLogDemo {
    public static void main(String[] args) {
        System.out.println("expZero=" + Math.exp(0.0));
        System.out.println("expNegativeZero=" + Math.exp(-0.0));
        System.out.println("logOne=" + Math.log(1.0));
        System.out.println("logTenBase10=" + Math.log10(10.0));
        System.out.println("logThousandBase10=" + Math.log10(1000.0));

        double x = 1e-16;
        System.out.println("naiveExpMinusOne=" + (Math.exp(x) - 1.0));
        System.out.println("stableExpMinusOne=" + Math.expm1(x));
        System.out.println("naiveLogOnePlus=" + Math.log(1.0 + x));
        System.out.println("stableLogOnePlus=" + Math.log1p(x));
        System.out.println("composedNaive=" + Math.log(Math.exp(x)));
        System.out.println("composedStable=" +
                Math.log1p(Math.expm1(x)));

        System.out.println("expOverflow=" + Math.exp(800.0));
        System.out.println("expUnderflow=" + Math.exp(-800.0));
        System.out.println("expm1NegativeInfinity=" +
                Math.expm1(Double.NEGATIVE_INFINITY));
        System.out.println("expPositiveInfinity=" +
                Math.exp(Double.POSITIVE_INFINITY));
        System.out.println("expNegativeInfinity=" +
                Math.exp(Double.NEGATIVE_INFINITY));

        System.out.println("logZero=" + Math.log(0.0));
        System.out.println("logNegativeZero=" + Math.log(-0.0));
        System.out.println("logNegative=" + Math.log(-1.0));
        System.out.println("log10Zero=" + Math.log10(0.0));
        System.out.println("log10Negative=" + Math.log10(-10.0));
        System.out.println("logPositiveInfinity=" +
                Math.log(Double.POSITIVE_INFINITY));

        System.out.println("log1pMinusOne=" + Math.log1p(-1.0));
        System.out.println("log1pBelowMinusOne=" + Math.log1p(-2.0));
        System.out.println("expm1NegativeZero=" + Math.expm1(-0.0));
        System.out.println("log1pNegativeZero=" + Math.log1p(-0.0));
        System.out.println("nanInput=" + Math.log1p(Double.NaN));

        double overflow = Math.exp(800.0);
        System.out.println("overflowIsInfinite=" +
                Double.isInfinite(overflow));
        System.out.println("overflowIsFinite=" +
                Double.isFinite(overflow));

        System.out.println("mathExpSixDecimals=" +
                String.format(Locale.ROOT, "%.6f", Math.exp(1.0)));
        System.out.println("strictExpSixDecimals=" +
                String.format(Locale.ROOT, "%.6f", StrictMath.exp(1.0)));
        System.out.println("logOneHalfSixDecimals=" +
                String.format(Locale.ROOT, "%.6f", Math.log1p(-0.5)));
        System.out.println("logBaseTwoEightSixDecimals=" +
                String.format(Locale.ROOT, "%.6f",
                        Math.log(8.0) / Math.log(2.0)));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac ExpLogDemo.java
java ExpLogDemo
```

**Kết quả mong đợi** trên JDK 17 khi sử dụng đúng ví dụ này:

```text
expZero=1.0
expNegativeZero=1.0
logOne=0.0
logTenBase10=1.0
logThousandBase10=3.0
naiveExpMinusOne=0.0
stableExpMinusOne=1.0E-16
naiveLogOnePlus=0.0
stableLogOnePlus=1.0E-16
composedNaive=0.0
composedStable=1.0E-16
expOverflow=Infinity
expUnderflow=0.0
expm1NegativeInfinity=-1.0
expPositiveInfinity=Infinity
expNegativeInfinity=0.0
logZero=-Infinity
logNegativeZero=-Infinity
logNegative=NaN
log10Zero=-Infinity
log10Negative=NaN
logPositiveInfinity=Infinity
log1pMinusOne=-Infinity
log1pBelowMinusOne=NaN
expm1NegativeZero=-0.0
log1pNegativeZero=-0.0
nanInput=NaN
overflowIsInfinite=true
overflowIsFinite=false
mathExpSixDecimals=2.718282
strictExpSixDecimals=2.718282
logOneHalfSixDecimals=-0.693147
logBaseTwoEightSixDecimals=3.000000
```

Bốn dòng `naive...` và `stable...` chứng minh sự khác biệt thiết yếu: những bước `exp(x)-1` và `log(1+x)` có thể đánh mất tín hiệu gần 0; `expm1` và `log1p` giữ precision tốt hơn. Các dòng `Infinity`/`NaN` chứng minh lý do phải xét miền đầu vào và đầu ra. Hai dòng `Math`/`StrictMath` dùng **định dạng sáu chữ số**, không khẳng định mọi chữ số nhị phân của hai kết quả đều giống nhau.

## 12. Sai lầm thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “`Math.log` trong Java mặc định cơ số 10.” | Sai: `Math.log` là logarit tự nhiên; `Math.log10` mới là cơ số 10. |
| “`Math.exp(x) - 1` và `Math.expm1(x)` luôn có cùng độ chính xác.” | Sai: `expm1` tốt hơn gần x = 0 do tránh cancellation. |
| “`Math.log(1+x)` giống `Math.log1p(x)` trong máy tính ở mọi x.” | Sai: bước `1+x` có thể làm tròn thành 1. |
| “`Math.log1p(x)` có nghĩa log của x cộng thêm 1 sau phép log.” | Sai: nó tính \(\ln(1+x)\), không phải \(\ln(x)+1\). |
| “`Math.expm1(x)` tính \(e^{x-1}\).” | Sai: nó tính \(e^x-1\). |
| “`Math.log(-1)` phải ném exception.” | Với số thực `double`, kết quả là `NaN`, không phải exception tự động. |
| “`Math.log1p(-1)` cho NaN.” | Sai: đúng ranh giới -1 trả `-Infinity`; nhỏ hơn -1 mới NaN. |
| “`Math.exp(800)` sẽ luôn cho một số `double` hữu hạn.” | Sai: overflow thành `Infinity`. |
| “`Math.exp(-800)` bằng 0 trong toán học.” | Sai: đó là underflow về zero trong biểu diễn `double`. |
| “`Math.log1p(-0.0)` sẽ đổi dấu thành dương zero.” | Sai: API giữ `-0.0`. |
| “`StrictMath` luôn cho nhiều chữ số chính xác hơn `Math`.” | Không có bảo đảm chung như vậy; mục tiêu quan trọng của `StrictMath` là tái lập kết quả. |
| “`exp(log(x)) == x` luôn true.” | Là hệ thức toán học trong miền phù hợp, nhưng triển khai dấu phẩy động có làm tròn và trường hợp đặc biệt. |

## 13. Checklist chọn hàm

1. **Bạn cần hàm mũ hay logarit?** `exp(x)` tính \(e^x\); `log(x)` tính \(\ln x\); `log10(x)` tính \(\log_{10}x\).
2. **Bài toán cần trừ 1 sau hàm mũ?** Nếu công thức là \(e^x-1\), ưu tiên `expm1(x)`, đặc biệt khi `x` gần 0.
3. **Bài toán cần log của 1 cộng x?** Nếu công thức là \(\ln(1+x)\), ưu tiên `log1p(x)`, đặc biệt khi `x` gần 0.
4. **Miền xác định có hợp lệ không?** `log`/`log10` cần x dương; `log1p` cần x lớn hơn -1 để có kết quả hữu hạn thông thường.
5. **Có nguy cơ overflow hoặc underflow không?** `exp` có thể thành vô cực/zero. Xem xét miền log và xử lý `Double.isFinite` phù hợp.
6. **Có quan tâm `NaN`, Infinity và signed zero không?** Đừng dựa vào exception số nguyên; dùng kiểm tra miền, `Double.isNaN`/`isInfinite`/`isFinite`.
7. **Bạn cần tính tái lập xuyên JVM không?** Cân nhắc `StrictMath` theo yêu cầu; không mặc định nó luôn nhanh hơn hoặc chính xác hơn.
8. **Bạn cần kết quả bit giống hệt sau ghép hàm không?** Nếu không có bảo đảm, dùng sai số tuyệt đối/tương đối phù hợp thay vì `==` cho các kết quả số thực xấp xỉ.

**Ghi nhớ:** `exp` và `log` là hai hàm cơ bản theo cơ số \(e\), `log10` theo cơ số 10; hai hàm `expm1` và `log1p` dành cho những biểu thức **rất gần 0 dễ mất chữ số có nghĩa**. Chọn đúng hàm thường quan trọng hơn việc tìm cách làm tròn kết quả sau mỗi bước.