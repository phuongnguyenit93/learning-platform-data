# Xử lý bài toán số học với miền giá trị lớn

Nhiều thuật toán đúng về ý tưởng nhưng cho kết quả sai khi dữ liệu tiến gần giới hạn kiểu số. Tổng có thể vượt `int`, tích có thể tràn `long`, phép so sánh có thể đảo thứ tự vì phép trừ bị wrap, `Math.abs(Long.MIN_VALUE)` vẫn âm, và `double` không phân biệt được mọi số nguyên lớn. Những lỗi này thường chỉ xuất hiện ở **giá trị biên**, nên các test nhỏ có thể khiến lời giải trông hoàn toàn đúng.

Bài thuộc nhóm **Thực hành tổng hợp** của **Computer Science Algorithms**, với chủ đề **Xử lý bài toán số học với miền giá trị lớn**. Ta học cách chọn kiểu số từ constraints, tính giới hạn của intermediate values, phát hiện overflow, dùng `BigInteger`/`BigDecimal` khi cần, xử lý modulo và thiết kế test với oracle số học độc lập.

Nội dung đi từ kiểu số Java đến tổng/tích, prefix sum, khoảng cách đường đi, binary search, comparator, GCD/LCM, tổ hợp, số học modulo, decimal và floating point. Phần thực hành có chương trình **Java 17 chạy độc lập**, so sánh checked arithmetic với `BigInteger`, kiểm thử vét cạn các cặp số nhỏ và các giá trị sát biên `long`, kèm stdout xác định.

## 1. Bắt đầu từ constraints, không bắt đầu từ kiểu quen dùng

Trước khi chọn `int`, `long` hay `BigInteger`, hãy xác định:

- Giá trị nhỏ nhất/lớn nhất của từng input;
- Số lượng phần tử, số bước và số lần cập nhật tối đa;
- Công thức có cộng, nhân, bình phương, lũy thừa hay tích nhiều thừa số;
- **Giá trị trung gian lớn nhất**, không chỉ đáp án cuối;
- Có số âm, decimal, modulo hay yêu cầu chính xác tuyệt đối không;
- Giới hạn thời gian, bộ nhớ và số chữ số của kết quả.

Ví dụ, có tối đa \(n=200.000\) phần tử, mỗi phần tử nằm trong \([-10^9,10^9]\). Khi đó:

\[
\left|\sum_{i=1}^{n}a_i\right|
\le n\cdot10^9=2\cdot10^{14}.
\]

`int` không đủ, nhưng `long` đủ cho tổng này. Nếu nhân hai giá trị cỡ \(10^{12}\), tích có thể cỡ \(10^{24}\), vượt `long`.

**Phải kiểm cả kiểu của toán hạng.** Đoạn sau sai:

~~~java
int a = 2_000_000_000;
int b = 2_000_000_000;
long product = a * b; // phep nhan da overflow trong int
~~~

Biến nhận là `long` không thể khôi phục các bit đã mất. Muốn nhân trong `long`:

~~~java
long product = (long) a * b;
~~~

Muốn phát hiện overflow:

~~~java
long product = Math.multiplyExact((long) a, b);
~~~

Quy tắc thực hành: tính bound bằng số học đủ rộng hoặc BigInteger; đừng để chính biểu thức tính bound overflow.

## 2. Miền biểu diễn các kiểu số Java

| Kiểu | Kích thước | Miền giá trị |
| --- | ---: | --- |
| `byte` | 8 bit | −128 đến 127 |
| `short` | 16 bit | −32.768 đến 32.767 |
| `int` | 32 bit | −2³¹ đến 2³¹−1 |
| `long` | 64 bit | −2⁶³ đến 2⁶³−1 |
| `float` | 32 bit IEEE 754 | Số thực xấp xỉ |
| `double` | 64 bit IEEE 754 | Số thực xấp xỉ, significand 53 bit |
| `BigInteger` | Độ dài tùy dữ liệu | Số nguyên chính xác |
| `BigDecimal` | Độ dài tùy dữ liệu | Số thập phân chính xác theo decimal/scale |

Hai giới hạn quan trọng:

~~~java
Long.MIN_VALUE // -9223372036854775808
Long.MAX_VALUE //  9223372036854775807
~~~

`long` là số nguyên có dấu 64 bit. Nó không tự tăng kích thước khi phép tính vượt miền.

### 2.1. Literal và ép kiểu

Dùng hậu tố `L` cho literal `long`:

~~~java
long x = 9_000_000_000L;
long y = 1L * 2_000_000_000 * 2_000_000_000;
~~~

Dùng `L` viết hoa để tránh nhầm với số 1. Dấu gạch dưới chỉ giúp đọc literal dễ hơn.

Ép kiểu không phải kiểm tra:

~~~java
long x = (long) someInt; // mo rong int sang long
int y = (int) someLong;  // co the mat bit
~~~

Khi thu hẹp kiểu, hãy kiểm tra miền hoặc dùng `Math.toIntExact(longValue)`. Method này ném `ArithmeticException` nếu giá trị không vừa `int`.

## 3. Overflow: phép số nguyên thông thường không tự báo lỗi

Phép cộng, trừ và nhân `int`/`long` thông thường giữ lại các bit thấp. Nếu kết quả toán học vượt miền biểu diễn, giá trị **wrap theo bù hai**.

~~~java
long x = Long.MAX_VALUE;
System.out.println(x + 1L);
// -9223372036854775808
~~~

Phép tính không ném exception. Giá trị sai vẫn là một số hợp lệ về mặt kiểu dữ liệu và có thể làm hỏng:
- Điều kiện `sum > limit`;
- Comparator và thứ tự trong priority queue;
- Đường đi ngắn nhất;
- Binary search và điều kiện dừng;
- Kích thước buffer;
- Prefix sum, DP và số cách.

Overflow có thể xảy ra **trước phép so sánh**. Đừng dựa vào mẹo `if (a+b<a)` cho mọi trường hợp signed; dùng checked arithmetic hoặc bound rõ ràng.

## 4. Checked arithmetic với `Math.*Exact`

Các hàm thường dùng:

| Hàm | Tác dụng |
| --- | --- |
| `Math.addExact(a,b)` | Cộng, báo overflow |
| `Math.subtractExact(a,b)` | Trừ, báo overflow |
| `Math.multiplyExact(a,b)` | Nhân, báo overflow |
| `Math.incrementExact(a)` | Tăng 1, báo overflow |
| `Math.decrementExact(a)` | Giảm 1, báo overflow |
| `Math.negateExact(a)` | Đổi dấu, báo overflow |
| `Math.toIntExact(a)` | Chuyển long sang int có kiểm tra |

Ví dụ:

~~~java
long total = 0;
for (long value : values) {
    total = Math.addExact(total, value);
}
~~~

Nếu tổng vượt `long`, chương trình ném `ArithmeticException` thay vì âm thầm trả đáp án sai.

Checked arithmetic **không quyết định thay nghiệp vụ**. Khi overflow, ứng dụng phải chọn từ chối input, báo lỗi, chuyển sang BigInteger, hoặc dùng saturating arithmetic nếu đặc tả cho phép. Không bắt exception rồi gán 0 hay `Long.MAX_VALUE` tùy tiện.

Nếu cần tự kiểm tra cộng trước khi tính, với b>0 overflow dương khi `a > Long.MAX_VALUE - b`; với b<0 overflow âm khi `a < Long.MIN_VALUE - b`. Phép nhân có nhiều trường hợp dấu hơn, vì vậy `Math.multiplyExact` thường dễ kiểm chứng hơn.

## 5. `BigInteger`: số nguyên lớn chính xác

`BigInteger` biểu diễn số nguyên có độ dài tùy dữ liệu. Nó không bị giới hạn 64 bit nhưng vẫn bị giới hạn bởi bộ nhớ, thời gian và khả năng cấp phát của JVM.

~~~java
import java.math.BigInteger;

BigInteger a = new BigInteger("9223372036854775807");
BigInteger b = BigInteger.valueOf(17);
BigInteger sum = a.add(b);
BigInteger product = a.multiply(b);
~~~

`BigInteger` immutable: `a.add(b)` trả object mới, không sửa `a`. Muốn cập nhật biến:

~~~java
a = a.add(b);
~~~

Các method chính:
- `add`, `subtract`, `multiply`;
- `divide`, `remainder`, `divideAndRemainder`;
- `mod`, `modPow`, `modInverse`;
- `gcd`, `abs`, `negate`;
- `pow`, `shiftLeft`, `shiftRight`;
- `compareTo`, `min`, `max`;
- `longValueExact`, `intValueExact`.

Khởi tạo từ string khi số vượt `long`:

~~~java
BigInteger huge =
    new BigInteger("1234567890123456789012345678901234567890");
~~~

### 5.1. Chuyển đổi ngược phải có kiểm tra

`longValue()` và `intValue()` có thể cắt bit. Nếu cần giữ toàn bộ giá trị:

~~~java
long exact = huge.longValueExact();
int small = huge.intValueExact();
~~~

Nếu không vừa miền, method ném `ArithmeticException`. Không dùng `==` để so sánh giá trị của hai BigInteger object; dùng `equals` hoặc `compareTo`.

## 6. Intermediate values: tích trước, chia sau

Công thức:

\[
\frac{a\cdot b}{2}
\]

có thể cho kết quả vừa `long`, trong khi `a*b` tràn trước khi chia. Với số nguyên, giảm thừa số chẵn trước khi nhân:

~~~java
static long triangular(long n) {
    if (n < 0) throw new IllegalArgumentException();
    long a = n, b = n - 1;
    if ((a & 1L) == 0) a /= 2;
    else b /= 2;
    return Math.multiplyExact(a, b);
}
~~~

Đây là \(n(n-1)/2\). Chia trước giúp giảm intermediate; `multiplyExact` vẫn cần vì kết quả cuối cũng có thể vượt long.

Nếu công thức phức tạp hoặc phép chia không thể rút gọn an toàn, dùng BigInteger:

~~~java
BigInteger result = BigInteger.valueOf(a)
    .multiply(BigInteger.valueOf(b))
    .divide(BigInteger.TWO);
~~~

Phép chia số nguyên bỏ phần dư. Nếu công thức yêu cầu chia hết, hãy chứng minh hoặc kiểm tra `divideAndRemainder`.

### 6.1. Prefix sum và DP

Nếu có n phần tử với trị tuyệt đối không quá M:

\[
|prefix[i]|\le iM\le nM.
\]

Chọn `long[]` chỉ khi đã chứng minh cả tổng dương và tổng âm đều nằm trong miền long. Nếu không, dùng BigInteger hoặc một cấu trúc phù hợp.

Trong DP, bảng có ít ô vẫn có thể chứa số cách, tích trọng số hoặc tổng chi phí rất lớn. Kiểu của chỉ số không quyết định kiểu của giá trị trạng thái. Nếu đề chỉ cần kết quả modulo M, lưu residue có thể giảm bộ nhớ, nhưng phép cộng/nhân modulo vẫn phải tránh overflow.

## 7. Bẫy của `Long.MIN_VALUE`

Miền long bất đối xứng:

\[
Long.MIN=-2^{63},\quad Long.MAX=2^{63}-1.
\]

Độ lớn của MIN lớn hơn MAX một đơn vị:

~~~java
Math.abs(Long.MIN_VALUE) == Long.MIN_VALUE // true
Math.negateExact(Long.MIN_VALUE)            // ArithmeticException
~~~

Muốn trị tuyệt đối chính xác:

~~~java
BigInteger magnitude =
    BigInteger.valueOf(Long.MIN_VALUE).abs();
~~~

Nếu API buộc trả long, phải từ chối trường hợp này hoặc công bố quy ước khác.

Tương tự, không dùng `Math.abs(a-b)` khi phép trừ có thể tràn. Nếu chỉ cần thứ tự, dùng `Long.compare(a,b)`. Nếu cần hiệu chính xác:

~~~java
BigInteger distance = BigInteger.valueOf(a)
    .subtract(BigInteger.valueOf(b)).abs();
~~~

## 8. Comparator không được dùng phép trừ

Comparator sai phổ biến:

~~~java
(a, b) -> (int) (a - b)
~~~

Khi hai giá trị gần hai đầu miền long, phép trừ có thể overflow; ép kết quả sang int còn làm mất bit. Comparator có thể trả thứ tự ngược hoặc vi phạm tính bắc cầu.

Dùng:

~~~java
Long.compare(a, b)
Integer.compare(a, b)
Comparator.comparingLong(Item::weight)
~~~

Sort giảm dần:

~~~java
Comparator<Long> descending =
    (a, b) -> Long.compare(b, a);
~~~

Khi so nhiều trường, dùng `thenComparingLong`, không trừ các field. Comparator phải thỏa antisymmetry và transitivity; overflow có thể làm hỏng sort hoặc priority queue.

## 9. Binary search và midpoint an toàn

Công thức `(left + right) / 2` có thể overflow. Với chỉ số mảng không âm:

~~~java
int mid = left + (right - left) / 2;
~~~

Với miền long có điều kiện `0 <= lo <= hi <= Long.MAX_VALUE`, dùng:

~~~java
long mid = lo + (hi - lo) / 2;
~~~

Nếu miền bao gồm toàn bộ signed long, `hi-lo` có thể vượt MAX. Khi `lo<=hi`, công thức sau dùng phép dịch phải không dấu:

~~~java
long mid = lo + ((hi - lo) >>> 1);
~~~

Hiệu toán học nằm trong [0,2⁶⁴−1]; biểu diễn long có thể mang bit dấu, nhưng `>>>1` chia giá trị unsigned đó cho 2. Trung điểm nằm giữa hai biên nên phép cộng cuối biểu diễn được.

Cách rõ nghĩa hơn nhưng tốn chi phí BigInteger:

~~~java
long mid = BigInteger.valueOf(lo)
    .add(BigInteger.valueOf(hi))
    .shiftRight(1)
    .longValueExact();
~~~

Trong binary search trên answer, kiểm cả `mid+1`, `mid-1`, `hi-lo+1`; các biểu thức lân cận cũng có thể overflow.

## 10. GCD, LCM, lũy thừa và tổ hợp

### 10.1. GCD và LCM

`BigInteger.gcd` trả GCD không âm:

~~~java
BigInteger gcd = a.abs().gcd(b.abs());
~~~

Với LCM:

\[
lcm(a,b)=\frac{|a|}{gcd(a,b)}\cdot|b|.
\]

Chia GCD trước khi nhân để giảm intermediate:

~~~java
static BigInteger lcm(BigInteger a, BigInteger b) {
    if (a.signum() == 0 || b.signum() == 0)
        return BigInteger.ZERO;
    return a.divide(a.gcd(b)).multiply(b).abs();
}
~~~

Quy ước `lcm(0,b)=0`. Kết quả LCM vẫn có thể vượt long; dùng BigInteger hoặc `multiplyExact` sau khi giảm GCD.

### 10.2. Lũy thừa và tổ hợp

`Math.pow` trả double, không phù hợp cho số nguyên lớn cần chính xác:

~~~java
BigInteger exact = BigInteger.valueOf(2).pow(1000);
~~~

Nếu chỉ cần modulo:

~~~java
BigInteger mod = BigInteger.valueOf(1_000_000_007L);
BigInteger answer = BigInteger.TWO.modPow(
    BigInteger.valueOf(1_000_000_000L), mod);
~~~

Tổ hợp \(C(n,k)=n!/(k!(n-k)!)\) có thể vượt long rất nhanh. Không tính factorial bằng long rồi mới chia; overflow đã xảy ra trước. Dùng BigInteger và nhân/chia từng bước:

~~~java
static BigInteger choose(int n, int k) {
    if (n < 0 || k < 0 || k > n)
        throw new IllegalArgumentException();
    k = Math.min(k, n - k);
    BigInteger answer = BigInteger.ONE;
    for (int i = 1; i <= k; i++) {
        answer = answer.multiply(
            BigInteger.valueOf(n - k + (long) i));
        answer = answer.divide(BigInteger.valueOf(i));
    }
    return answer;
}
~~~

## 11. Số học modulo và phép nhân an toàn

Đoạn sau có thể sai:

~~~java
long next = (a * b) % mod;
~~~

Tích `a*b` có thể overflow trước khi lấy phần dư. Modulo không sửa được giá trị đã wrap.

Cách đơn giản và chính xác khi toán hạng có thể lớn:

~~~java
static long multiplyMod(long a, long b, long mod) {
    if (mod <= 0) throw new IllegalArgumentException();
    return BigInteger.valueOf(a)
        .multiply(BigInteger.valueOf(b))
        .mod(BigInteger.valueOf(mod))
        .longValueExact();
}
~~~

Nếu cần tốc độ cao cho nhiều phép nhân modulo long, có thể nghiên cứu add-and-double, Montgomery reduction hoặc wide multiplication, nhưng phải chứng minh invariant và kiểm thử riêng.

`%` và `Math.floorMod` khác nhau với số âm. `%` giữ dấu của toán hạng trái; `floorMod(x,m)` với m dương trả phần dư không âm. `BigInteger.mod(m)` yêu cầu m dương; `remainder(m)` có quy tắc dấu khác.

## 12. Floating point và decimal chính xác

`double` có 53 bit precision cho significand. Các số nguyên liên tiếp được biểu diễn chính xác đến \(2^{53}\); từ đó trở lên có những số nguyên không phân biệt được:

~~~java
double a = 9_007_199_254_740_992d; // 2^53
double b = 9_007_199_254_740_993d;
System.out.println(a == b); // true
~~~

Không dùng double cho ID, số đếm hoặc integer cần chính xác.

### 12.1. BigDecimal

Số thực nhị phân không biểu diễn chính xác nhiều phân số decimal. Khi cần tiền hoặc decimal chính xác, khởi tạo từ String:

~~~java
BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");
BigDecimal total = a.add(b); // 0.30
~~~

`new BigDecimal(0.1)` đưa sai số binary của double vào decimal. `BigDecimal.valueOf(0.1)` dùng chuỗi canonical của double, thường tốt hơn, nhưng đầu vào vẫn đã đi qua double.

`BigDecimal("0.10")` và `BigDecimal("0.1")` có cùng giá trị số học nhưng scale khác: `equals` trả false, `compareTo` trả 0. Khi chia số thập phân vô hạn, chỉ định scale và rounding mode:

~~~java
new BigDecimal("1")
    .divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);
// 0.3333
~~~

## 13. Chia số nguyên, khoảng cách và sentinel INF

Phép `/` trên số nguyên Java cắt về 0:

~~~java
-7 / 3                // -2
Math.floorDiv(-7, 3)  // -3
~~~

Dùng `floorDiv` khi ngữ nghĩa yêu cầu floor. Chia cho 0 ném `ArithmeticException`.

Một trường hợp đặc biệt: `Long.MIN_VALUE / -1` không ném exception mà wrap về `Long.MIN_VALUE`, vì kết quả toán học \(2^{63}\) không vừa long.

Trong Dijkstra, `dist[u] + weight` có thể overflow thành số âm. Với trọng số không âm, kiểm tra trước:

~~~java
if (dist[u] > Long.MAX_VALUE - weight) {
    // distance khong bieu dien duoc bang long
} else {
    long candidate = dist[u] + weight;
}
~~~

Không mặc định `Long.MAX_VALUE` luôn là INF an toàn: một đường đi hợp lệ có thể có chính giá trị đó. Dùng `boolean[] reached` riêng, hoặc chứng minh mọi giá trị hợp lệ nhỏ hơn sentinel. Nếu đỉnh unreachable, không cộng sentinel với weight.

## 14. Chọn chiến lược số học và chi phí

| Nhu cầu | Lựa chọn | Ghi chú |
| --- | --- | --- |
| Chỉ số, kích thước mảng | `int` | Java array index dùng int |
| Tổng/tích đã chứng minh nằm trong 64 bit | `long` | Kiểm intermediate |
| Muốn phát hiện overflow | `Math.*Exact` | Xử lý exception theo contract |
| Integer vượt 64 bit | `BigInteger` | Chính xác, tốn CPU/RAM hơn |
| Decimal cần chính xác | `BigDecimal(String)` | Quy định scale/rounding |
| Mô phỏng cần xấp xỉ | `double` | Xét sai số |
| Số mũ lớn chỉ cần modulo | `BigInteger.modPow` | Hoặc thuật toán modulo đã chứng minh |
| Giá trị có thể bằng INF | `reached[]` riêng | Tránh trùng sentinel |

Với primitive long, phép toán thường được xem là O(1) trong mô hình word cố định. BigInteger có chi phí phụ thuộc số bit:
- Cộng/trừ tăng theo số word;
- Nhân phụ thuộc thuật toán nội bộ và kích thước toán hạng;
- Chia, GCD và modular exponentiation cũng phụ thuộc bit length;
- Object immutable khiến các phép toán tạo intermediate objects.

Không cần BigInteger ở mọi nơi. Nếu constraints chứng minh long an toàn, primitive thường gọn và nhanh hơn. Nếu cần số nguyên chính xác vượt 64 bit, BigInteger là lựa chọn đúng. Nếu đề chỉ cần modulo, giữ residue có thể tiết kiệm nhưng vẫn phải nhân modulo an toàn.

## 15. Chương trình Java 17 kiểm tra số học miền lớn

File **LargeValueArithmeticDemo.java** minh họa:
- Cộng/nhân checked với `Math.addExact` và `Math.multiplyExact`;
- Oracle BigInteger kiểm tra primitive;
- Vét cạn 40.401 cặp a,b trong [-100,100];
- Kiểm tra 49 cặp tại `Long.MIN_VALUE`, `Long.MAX_VALUE`, −1, 0 và 1;
- BigInteger sum/product, abs MIN, modular multiply/modPow, GCD/LCM;
- Midpoint toàn miền signed long và comparator an toàn;
- BigDecimal, double precision, chia số âm, prefix sum;
- Kiểm tra overflow và conversion.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class LargeValueArithmeticDemo {
    static final BigInteger BI_MIN =
        BigInteger.valueOf(Long.MIN_VALUE);
    static final BigInteger BI_MAX =
        BigInteger.valueOf(Long.MAX_VALUE);

    static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static boolean fitsLong(BigInteger x) {
        return x.compareTo(BI_MIN) >= 0
            && x.compareTo(BI_MAX) <= 0;
    }

    static long[] checkedPrefix(long[] values) {
        long[] prefix = new long[values.length + 1];
        for (int i = 0; i < values.length; i++)
            prefix[i + 1] =
                Math.addExact(prefix[i], values[i]);
        return prefix;
    }

    static BigInteger[] bigPrefix(long[] values) {
        BigInteger[] prefix =
            new BigInteger[values.length + 1];
        prefix[0] = BigInteger.ZERO;
        for (int i = 0; i < values.length; i++)
            prefix[i + 1] =
                prefix[i].add(BigInteger.valueOf(values[i]));
        return prefix;
    }

    static BigInteger rangeBig(
            BigInteger[] prefix, int left, int right) {
        if (left < 0 || left > right
            || right >= prefix.length)
            throw new IllegalArgumentException("Bad range");
        return prefix[right].subtract(prefix[left]);
    }

    static BigInteger lcm(BigInteger a, BigInteger b) {
        if (a.signum() == 0 || b.signum() == 0)
            return BigInteger.ZERO;
        return a.divide(a.gcd(b)).multiply(b).abs();
    }

    static long midpoint(long lo, long hi) {
        if (lo > hi)
            throw new IllegalArgumentException("lo > hi");
        return lo + ((hi - lo) >>> 1);
    }

    static long triangularChecked(long n) {
        if (n < 0) throw new IllegalArgumentException("n < 0");
        long a = n;
        long b = n - 1;
        if ((a & 1L) == 0) a /= 2;
        else b /= 2;
        return Math.multiplyExact(a, b);
    }

    static void verifyAdd(long a, long b) {
        BigInteger exact = BigInteger.valueOf(a)
            .add(BigInteger.valueOf(b));
        if (fitsLong(exact)) {
            long actual;
            try {
                actual = Math.addExact(a, b);
            } catch (ArithmeticException ex) {
                throw new AssertionError("Unexpected add overflow");
            }
            require(actual == exact.longValueExact(),
                "Wrong checked addition");
        } else {
            boolean overflow = false;
            try {
                Math.addExact(a, b);
            } catch (ArithmeticException expected) {
                overflow = true;
            }
            require(overflow, "Missing add overflow");
        }
    }

    static void verifyMultiply(long a, long b) {
        BigInteger exact = BigInteger.valueOf(a)
            .multiply(BigInteger.valueOf(b));
        if (fitsLong(exact)) {
            long actual;
            try {
                actual = Math.multiplyExact(a, b);
            } catch (ArithmeticException ex) {
                throw new AssertionError(
                    "Unexpected multiply overflow");
            }
            require(actual == exact.longValueExact(),
                "Wrong checked multiplication");
        } else {
            boolean overflow = false;
            try {
                Math.multiplyExact(a, b);
            } catch (ArithmeticException expected) {
                overflow = true;
            }
            require(overflow, "Missing multiply overflow");
        }
    }

    static int verifyPairs(long[] values) {
        int checked = 0;
        for (long a : values) {
            for (long b : values) {
                verifyAdd(a, b);
                verifyMultiply(a, b);
                checked++;
            }
        }
        return checked;
    }

    static int exhaustiveSmall() {
        int checked = 0;
        for (long a = -100; a <= 100; a++) {
            for (long b = -100; b <= 100; b++) {
                verifyAdd(a, b);
                verifyMultiply(a, b);
                checked++;
            }
        }
        return checked;
    }

    static BigInteger multiplyMod(
            long a, long b, long modulus) {
        if (modulus <= 0)
            throw new IllegalArgumentException(
                "Modulus must be positive");
        return BigInteger.valueOf(a)
            .multiply(BigInteger.valueOf(b))
            .mod(BigInteger.valueOf(modulus));
    }

    static void verifyModularArithmetic() {
        long modulus = 1_000_000_007L;
        for (long a = -20; a <= 20; a++) {
            for (long b = -20; b <= 20; b++) {
                long actual =
                    multiplyMod(a,b,modulus).longValueExact();
                long expected = Math.floorMod(
                    Math.floorMod(a,modulus)
                        * Math.floorMod(b,modulus),
                    modulus);
                require(actual == expected,
                    "Modular product mismatch");
            }
        }
    }

    static void verifyMidpoints() {
        require(midpoint(Long.MIN_VALUE, Long.MAX_VALUE) == -1,
            "Full-range midpoint");
        require(midpoint(-10, -3) == -7,
            "Negative midpoint");
        require(midpoint(0, Long.MAX_VALUE)
                == Long.MAX_VALUE / 2,
            "Nonnegative midpoint");
        boolean rejected = false;
        try {
            midpoint(2, 1);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        require(rejected, "Invalid midpoint bounds accepted");
    }

    static void verifyPrefixAndTriangular() {
        long[] input = {2, -1, 4, 3};
        long[] p = checkedPrefix(input);
        require(Arrays.equals(p,
            new long[]{0,2,1,5,8}), "Prefix mismatch");
        require(p[3] - p[1] == 3, "Range sum mismatch");

        BigInteger[] big = bigPrefix(new long[]{
            Long.MAX_VALUE, 1L
        });
        require(rangeBig(big,0,2).equals(
            BigInteger.valueOf(Long.MAX_VALUE).add(
                BigInteger.ONE)), "Big prefix mismatch");

        boolean overflow = false;
        try {
            checkedPrefix(new long[]{Long.MAX_VALUE,1L});
        } catch (ArithmeticException expected) {
            overflow = true;
        }
        require(overflow, "Prefix overflow not detected");

        require(triangularChecked(1_000_000_000L)
            == 499_999_999_500_000_000L,
            "Triangular mismatch");
    }

    static void verifyConversions() {
        boolean overflow = false;
        try {
            BI_MAX.add(BigInteger.ONE).longValueExact();
        } catch (ArithmeticException expected) {
            overflow = true;
        }
        require(overflow, "longValueExact did not reject overflow");
    }

    public static void main(String[] args) {
        long wrapped = Long.MAX_VALUE + 1L;
        boolean addOverflow = false;
        try {
            Math.addExact(Long.MAX_VALUE, 1L);
        } catch (ArithmeticException expected) {
            addOverflow = true;
        }

        boolean multiplyOverflow = false;
        try {
            Math.multiplyExact(4_000_000_000L,
                               4_000_000_000L);
        } catch (ArithmeticException expected) {
            multiplyOverflow = true;
        }

        BigInteger bigSum = BigInteger.valueOf(Long.MAX_VALUE)
            .add(BigInteger.valueOf(Long.MAX_VALUE))
            .add(BigInteger.valueOf(17));
        BigInteger bigProduct = BigInteger.valueOf(4_000_000_000L)
            .multiply(BigInteger.valueOf(4_000_000_000L));

        BigInteger minMagnitude =
            BigInteger.valueOf(Long.MIN_VALUE).abs();

        double d1 = 9_007_199_254_740_992d;
        double d2 = 9_007_199_254_740_993d;

        long badComparatorSign =
            Long.MIN_VALUE - Long.MAX_VALUE;
        List<Long> sorted = new ArrayList<>(List.of(
            Long.MAX_VALUE, 0L, Long.MIN_VALUE));
        sorted.sort(Long::compare);

        BigDecimal decimalSum =
            new BigDecimal("0.10").add(new BigDecimal("0.20"));
        BigDecimal decimalA = new BigDecimal("0.10");
        BigDecimal decimalB = new BigDecimal("0.1");
        BigDecimal decimalDivision = new BigDecimal("1")
            .divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);

        BigInteger a =
            new BigInteger("12345678901234567890");
        BigInteger b = new BigInteger("9876543210");
        BigInteger gcd = a.gcd(b);
        BigInteger lcm = lcm(a,b);

        long modulus = 1_000_000_007L;
        BigInteger modularProduct = multiplyMod(
            Long.MAX_VALUE, Long.MAX_VALUE, modulus);
        BigInteger modularPower = BigInteger.TWO.modPow(
            BigInteger.valueOf(100),
            BigInteger.valueOf(modulus));

        long[] prefix = checkedPrefix(new long[]{2,-1,4,3});

        require(addOverflow && multiplyOverflow,
            "Overflow checks did not trigger");
        verifyConversions();
        verifyPrefixAndTriangular();
        verifyMidpoints();
        verifyModularArithmetic();

        long[] boundary = {
            Long.MIN_VALUE, Long.MIN_VALUE + 1,
            -1, 0, 1, Long.MAX_VALUE - 1, Long.MAX_VALUE
        };
        int boundaryPairs = verifyPairs(boundary);
        int smallPairs = exhaustiveSmall();

        require(smallPairs == 40401, "Small-pair count");
        require(boundaryPairs == 49, "Boundary-pair count");
        require(wrapped == Long.MIN_VALUE, "Wrap example");
        require(badComparatorSign > 0,
            "Expected bad comparator overflow example");
        require(sorted.get(0) == Long.MIN_VALUE
            && sorted.get(2) == Long.MAX_VALUE,
            "Safe comparator order");
        require(d1 == d2, "Expected double precision collision");
        require(decimalSum.toPlainString().equals("0.30"),
            "BigDecimal addition");
        require(decimalA.compareTo(decimalB) == 0
            && !decimalA.equals(decimalB),
            "BigDecimal scale behavior");
        require(gcd.equals(BigInteger.valueOf(90)),
            "GCD mismatch");
        require(lcm.equals(
            new BigInteger("1354807012498094801236261410")),
            "LCM mismatch");
        require(modularProduct.equals(
            BigInteger.valueOf(737564071L)),
            "Modular product mismatch");
        require(modularPower.equals(
            BigInteger.valueOf(976371285L)),
            "Modular exponent mismatch");

        System.out.println("overflow.wrap=" + wrapped);
        System.out.println("overflow.addExact="
            + (addOverflow ? "DETECTED" : "MISSED"));
        System.out.println("overflow.multiplyExact="
            + (multiplyOverflow ? "DETECTED" : "MISSED"));
        System.out.println("big.sum=" + bigSum);
        System.out.println("big.product=" + bigProduct);
        System.out.println("long.minValue=" + Long.MIN_VALUE);
        System.out.println("abs.bigIntegerMin=" + minMagnitude);
        System.out.println("double.sameAt2Pow53=" + (d1 == d2));
        System.out.println("comparator.badSign="
            + Long.signum(badComparatorSign));
        System.out.println("comparator.safe=" + sorted);
        System.out.println("midpoint.fullSignedRange="
            + midpoint(Long.MIN_VALUE,Long.MAX_VALUE));
        System.out.println("division.truncating=" + (-7 / 3));
        System.out.println("division.floor="
            + Math.floorDiv(-7,3));
        System.out.println("bigDecimal.sum="
            + decimalSum.toPlainString());
        System.out.println("bigDecimal.equalsByScale="
            + decimalA.equals(decimalB));
        System.out.println("bigDecimal.compareToZero="
            + (decimalA.compareTo(decimalB) == 0));
        System.out.println("bigDecimal.divide="
            + decimalDivision.toPlainString());
        System.out.println("gcd=" + gcd);
        System.out.println("lcm=" + lcm);
        System.out.println("mod.multiply=" + modularProduct);
        System.out.println("mod.pow=" + modularPower);
        System.out.println("prefix="
            + Arrays.toString(prefix));
        System.out.println("prefix.range[1,3)="
            + (prefix[3]-prefix[1]));
        System.out.println("triangular.1e9="
            + triangularChecked(1_000_000_000L));
        System.out.println("verified.smallPairs=" + smallPairs);
        System.out.println("verified.boundaryPairs=" + boundaryPairs);
        System.out.println("verified.modular=PASS");
        System.out.println("verified.prefix=PASS");
        System.out.println("verified.midpoint=PASS");
        System.out.println("verified.conversion=PASS");
        System.out.println("verification=PASS");
    }
}
~~~

### 15.1. Biên dịch, chạy và stdout dự kiến

Lưu đúng tên **LargeValueArithmeticDemo.java** rồi chạy với JDK 17+:

~~~bash
javac LargeValueArithmeticDemo.java
java LargeValueArithmeticDemo
~~~

Stdout xác định:

~~~text
overflow.wrap=-9223372036854775808
overflow.addExact=DETECTED
overflow.multiplyExact=DETECTED
big.sum=18446744073709551631
big.product=16000000000000000000
long.minValue=-9223372036854775808
abs.bigIntegerMin=9223372036854775808
double.sameAt2Pow53=true
comparator.badSign=1
comparator.safe=[-9223372036854775808, 0, 9223372036854775807]
midpoint.fullSignedRange=-1
division.truncating=-2
division.floor=-3
bigDecimal.sum=0.30
bigDecimal.equalsByScale=false
bigDecimal.compareToZero=true
bigDecimal.divide=0.3333
gcd=90
lcm=1354807012498094801236261410
mod.multiply=737564071
mod.pow=976371285
prefix=[0, 2, 1, 5, 8]
prefix.range[1,3)=3
triangular.1e9=499999999500000000
verified.smallPairs=40401
verified.boundaryPairs=49
verified.modular=PASS
verified.prefix=PASS
verified.midpoint=PASS
verified.conversion=PASS
verification=PASS
~~~

Trong chương trình, `Math.abs(Long.MIN_VALUE)` được giải thích ở phần lý thuyết; output in giá trị `long.minValue` và magnitude BigInteger để thấy hai miền biểu diễn khác nhau.

### 15.2. Cách đọc kiểm thử

`smallPairs=40401` là mọi cặp a,b trong [-100,100]. Mỗi cặp kiểm cả phép cộng và phép nhân. `boundaryPairs=49` là tích Descartes của bảy giá trị: MIN, MIN+1, −1, 0, 1, MAX−1, MAX.

Với từng phép toán, BigInteger là oracle:
- Nếu kết quả toán học vừa long, `Math.*Exact` phải trả đúng giá trị.
- Nếu kết quả không vừa long, checked primitive phải ném `ArithmeticException`.

Chương trình còn kiểm prefix sum overflow, modulo, midpoint trên toàn miền signed long, BigInteger conversion, decimal scale, GCD/LCM và các giá trị đầu ra cố định.

## 16. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gán `int*int` vào long | Phép nhân đã xảy ra trong int | Ép một toán hạng trước phép nhân |
| Cộng tổng lớn trong int | Tổng vượt 2³¹−1 | Long hoặc BigInteger theo bound |
| Tin long không tràn | 64 bit vẫn có giới hạn | Tính bound, dùng `Math.*Exact` |
| `Math.abs(Long.MIN_VALUE)` | Độ lớn không vừa long | BigInteger abs hoặc từ chối |
| Comparator dùng `(int)(a-b)` | Trừ tràn và ép mất bit | `Long.compare` |
| Binary search `(lo+hi)/2` | Tổng biên tràn | Midpoint an toàn |
| `a*b%mod` | Tích tràn trước modulo | BigInteger hoặc modular multiply đã chứng minh |
| `Math.pow` cho integer lớn | Trả double xấp xỉ | `BigInteger.pow/modPow` |
| Factorial rồi mới chia | Factorial tràn trước phép chia | BigInteger hoặc giảm thừa số |
| Dùng double cho integer ID | Mất phân biệt trên 2⁵³ | Long/BigInteger |
| `new BigDecimal(0.1)` | Mang sai số binary vào decimal | Constructor String |
| So BigDecimal bằng equals | Scale khác nhau | `compareTo` nếu so giá trị |
| Dùng MAX làm INF vô điều kiện | Có thể trùng giá trị hợp lệ | `reached[]` hoặc bound rõ |
| Dùng `/` khi cần floor | Java cắt về 0 | `Math.floorDiv` |
| Chuyển BigInteger bằng `longValue` | Cắt bit | `longValueExact` |
| Bỏ qua MIN / −1 | Overflow đặc biệt | Kiểm trước hoặc BigInteger |

## 17. Checklist xử lý miền giá trị lớn

1. Xác định min/max của input và số lượng phần tử.
2. Tính bound cho **mọi intermediate expression**, không chỉ output.
3. Nhớ phép nhân hai int xảy ra trong int trước khi gán long.
4. Dùng hậu tố `L` cho literal cần là long.
5. Dùng `Math.addExact`, `subtractExact`, `multiplyExact`, `toIntExact` khi cần bắt overflow.
6. Dùng BigInteger nếu integer result có thể vượt 64 bit.
7. Không dùng `longValue()`/cast khi cần giữ nguyên giá trị lớn.
8. Tránh `Math.abs(Long.MIN_VALUE)` và `-Long.MIN_VALUE`.
9. Không viết comparator bằng phép trừ.
10. Chọn midpoint an toàn cho miền biên đã cho.
11. Giảm GCD trước khi nhân LCM/tích phân số.
12. Không giả định modulo cứu được phép nhân đã overflow.
13. Dùng `modPow` cho lũy thừa modulo lớn.
14. Chọn `floorDiv` khi cần floor với số âm.
15. Dùng `BigDecimal(String)` cho decimal chính xác và nêu rounding mode.
16. Không dùng double cho integer lớn cần chính xác.
17. Kiểm sentinel INF có trùng một giá trị hợp lệ không.
18. Xử lý tràn distance, prefix sum và DP có chủ đích.
19. Tính chi phí bit length và object khi dùng BigInteger.
20. Kiểm bằng oracle BigInteger trên miền nhỏ và các trường hợp sát biên.
21. Kiểm overflow phải được phát hiện, không chỉ test giá trị thường.
22. Test số âm, 0, MIN, MAX, divisor 0 và modulus không hợp lệ.
23. Đo hiệu năng sau khi đã xác nhận correctness.
24. Phân biệt kết quả nguyên chính xác, modulo và số thực xấp xỉ.

## 18. Bài tập có đáp án

**Bài 1.** Vì sao `long x = a*b` có thể sai nếu a,b là int?

*Đáp án:* Phép nhân được thực hiện trong int trước rồi mới mở rộng kết quả đã overflow.

**Bài 2.** Khi nào nên chọn long thay int?

*Đáp án:* Khi bound chứng minh giá trị hoặc intermediate có thể vượt int nhưng vẫn nằm trong long.

**Bài 3.** Java có tự ném exception khi long cộng tràn không?

*Đáp án:* Không. Phép cộng thông thường wrap; dùng `Math.addExact`.

**Bài 4.** `Math.multiplyExact` làm gì?

*Đáp án:* Nhân và ném ArithmeticException nếu kết quả không biểu diễn được.

**Bài 5.** 200.000 phần tử, mỗi trị tuyệt đối ≤10⁹, tổng trị tuyệt đối tối đa cỡ bao nhiêu?

*Đáp án:* 2×10¹⁴, vừa long.

**Bài 6.** Vì sao phải kiểm intermediate trong n(n−1)/2?

*Đáp án:* Tích có thể tràn dù kết quả sau chia vừa long.

**Bài 7.** BigInteger có mutable không?

*Đáp án:* Không, immutable; add/multiply trả object mới.

**Bài 8.** `longValue()` và `longValueExact()` khác nhau?

*Đáp án:* `longValue` có thể cắt bit; `longValueExact` ném lỗi nếu không vừa long.

**Bài 9.** Vì sao `Math.abs(Long.MIN_VALUE)` vẫn âm?

*Đáp án:* Độ lớn 2⁶³ lớn hơn Long.MAX_VALUE một đơn vị.

**Bài 10.** Cách lấy trị tuyệt đối chính xác của Long.MIN_VALUE?

*Đáp án:* `BigInteger.valueOf(x).abs()`.

**Bài 11.** Comparator `(a,b)->(int)(a-b)` sai ở đâu?

*Đáp án:* Trừ có thể overflow long và ép int làm mất thông tin; dùng `Long.compare`.

**Bài 12.** Vì sao `(lo+hi)/2` có thể sai?

*Đáp án:* Tổng hai biên có thể tràn trước phép chia.

**Bài 13.** Midpoint an toàn cho toàn signed long khi lo≤hi?

*Đáp án:* `lo + ((hi-lo) >>> 1)` với phép dịch phải không dấu.

**Bài 14.** Khi nào `lo+(hi-lo)/2` an toàn?

*Đáp án:* Khi đã chứng minh `hi-lo` nằm trong miền long, ví dụ 0≤lo≤hi≤MAX.

**Bài 15.** Vì sao `a*b%mod` có thể sai dù mod nhỏ?

*Đáp án:* a*b tràn trước khi lấy phần dư.

**Bài 16.** `BigInteger.mod` yêu cầu modulus thế nào?

*Đáp án:* Modulus phải dương và kết quả không âm.

**Bài 17.** `remainder` có luôn giống `mod` không?

*Đáp án:* Không. Với số âm, quy tắc dấu khác nhau.

**Bài 18.** Tính lũy thừa lớn chỉ cần modulo nên dùng gì?

*Đáp án:* `BigInteger.modPow` hoặc modular exponentiation đã kiểm chứng.

**Bài 19.** GCD của 12345678901234567890 và 9876543210 trong ví dụ?

*Đáp án:* 90.

**Bài 20.** Vì sao chia GCD trước khi nhân LCM?

*Đáp án:* Giảm kích thước intermediate và nguy cơ overflow.

**Bài 21.** `Math.pow(2,1000)` có trả integer chính xác không?

*Đáp án:* Không, trả double xấp xỉ; dùng BigInteger.

**Bài 22.** Vì sao factorial rồi chia có thể sai?

*Đáp án:* Factorial có thể overflow trước khi chia.

**Bài 23.** Double có biểu diễn chính xác mọi integer đến Long.MAX_VALUE không?

*Đáp án:* Không. Độ chính xác significand là 53 bit; các integer liên tiếp không còn phân biệt sau 2⁵³.

**Bài 24.** Vì sao BigDecimal từ String tốt hơn từ double?

*Đáp án:* String giữ decimal đã chỉ định; double đã mang sai số nhị phân.

**Bài 25.** `BigDecimal("0.10").equals(BigDecimal("0.1"))` trả gì?

*Đáp án:* false do scale khác; `compareTo` trả 0.

**Bài 26.** Chia 1 cho 3 tới bốn chữ số decimal?

*Đáp án:* `divide(...,4,RoundingMode.HALF_UP)` cho 0.3333.

**Bài 27.** `-7/3` và `Math.floorDiv(-7,3)` khác nhau thế nào?

*Đáp án:* `/` trả −2, `floorDiv` trả −3.

**Bài 28.** `Long.MIN_VALUE / -1` có ném ArithmeticException không?

*Đáp án:* Không; kết quả wrap thành Long.MIN_VALUE.

**Bài 29.** Vì sao MAX có thể không phải sentinel INF an toàn?

*Đáp án:* Một đường đi hợp lệ có thể có đúng giá trị đó.

**Bài 30.** Khi nào dùng `boolean[] reached` cạnh `long[] dist`?

*Đáp án:* Khi cần phân biệt unreachable với mọi giá trị long hợp lệ.

**Bài 31.** Prefix sum của `[2,-1,4,3]` là gì?

*Đáp án:* `[0,2,1,5,8]`.

**Bài 32.** Tổng đoạn nửa mở [1,3) trong mảng trên?

*Đáp án:* −1+4=3.

**Bài 33.** `Math.toIntExact(longValue)` làm gì?

*Đáp án:* Chuyển sang int nếu vừa miền, nếu không ném ArithmeticException.

**Bài 34.** BigInteger có chi phí O(1) cho mọi kích thước không?

*Đáp án:* Không. Chi phí phụ thuộc bit length và thuật toán cộng/nhân/chia.

**Bài 35.** Nếu đề chỉ yêu cầu số cách modulo 1e9+7, có luôn cần BigInteger đầy đủ không?

*Đáp án:* Không nhất thiết; có thể giữ residue nhưng phép nhân modulo vẫn phải an toàn.

**Bài 36.** `Math.addExact` có phát hiện overflow đã xảy ra trong phép nhân int trước đó không?

*Đáp án:* Không. Phải mở rộng kiểu trước phép nhân.

**Bài 37.** Vì sao test 0, −1, MIN và MAX hữu ích?

*Đáp án:* Chúng phơi bày lỗi dấu, wrap, abs, comparator, chia và modulo.

**Bài 38.** Nếu output cuối vừa long nhưng intermediate vượt long thì xử lý thế nào?

*Đáp án:* Biến đổi công thức để giảm thừa số nếu chứng minh được, hoặc dùng BigInteger cho intermediate.

**Bài 39.** 40.401 cặp test trong demo được tạo thế nào?

*Đáp án:* Mọi cặp a,b trong −100..100, tức 201×201 cặp; mỗi cặp kiểm cộng và nhân với oracle BigInteger.

**Bài 40.** Vì sao test nhỏ không thay thế test biên?

*Đáp án:* Overflow thường chỉ xuất hiện gần giới hạn kiểu; test nhỏ xác nhận logic thường nhưng không bao phủ miền giá trị lớn.

## Tổng kết

**Miền giá trị là một phần của thuật toán.** Hãy tính bound cho input, output và mọi intermediate; dùng `int`/`long` khi đã chứng minh đủ miền, `Math.*Exact` khi cần phát hiện overflow, `BigInteger` cho integer vượt 64 bit và `BigDecimal(String)` khi cần decimal chính xác.

Những lỗi nguy hiểm thường nằm ở chỗ tưởng như vô hại: nhân trước khi ép kiểu, comparator dùng phép trừ, `abs(Long.MIN_VALUE)`, midpoint, `a*b%mod`, sentinel INF, chia số âm và chuyển BigInteger bằng `longValue`. Kiểm thử với oracle BigInteger, các giá trị MIN/MAX, số âm, 0, modulo và intermediate giúp phát hiện lỗi trước khi chúng làm sai thuật toán. BigInteger chính xác nhưng tốn chi phí theo kích thước số; tối ưu sau khi đã xác nhận contract và tính đúng.
