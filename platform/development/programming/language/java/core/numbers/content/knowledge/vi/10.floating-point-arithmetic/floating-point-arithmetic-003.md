# Overflow, underflow và giá trị subnormal trong phép toán dấu phẩy động Java

## 1. Mục tiêu và bức tranh tổng quát

Các kiểu `float` và `double` của Java dùng số dấu phẩy động nhị phân theo IEEE 754. Chúng biểu diễn được nhiều số rất lớn và rất nhỏ nhưng **miền giá trị hữu hạn** và **độ chính xác** có giới hạn. Một phép toán có kết quả toán học hợp lệ vẫn có thể cho `Infinity`, `0.0` hoặc một số *subnormal* khi lưu vào `float`/`double`.

Bài học tập trung vào ba hiện tượng:

- **Overflow (tràn trên):** độ lớn kết quả vượt miền số hữu hạn biểu diễn được; với phép toán Java thông thường, kết quả có thể trở thành `+Infinity` hoặc `-Infinity`.
- **Underflow (tràn dưới):** kết quả khác 0 về mặt toán học quá gần 0 để được giữ với độ chính xác thông thường; Java có thể làm tròn thành số subnormal, hoặc thành `+0.0`/`-0.0`.
- **Subnormal (số dưới chuẩn):** số hữu hạn khác 0 có độ lớn nhỏ hơn số dương *normal* nhỏ nhất, giúp biểu diễn giá trị gần 0 theo cơ chế *gradual underflow*.

Không nên nhầm các hiện tượng này với **integer overflow** (số nguyên quay vòng theo modulo) hoặc lỗi biên dịch khi một literal có số mũ không thể biểu diễn.

## 2. Phạm vi IEEE 754 trong float và double

| Thuộc tính | `float` (binary32) | `double` (binary64) |
| --- | --- | --- |
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit số mũ | 8 | 11 |
| Bit phân số lưu trữ | 23 | 52 |
| Độ chính xác hiệu dụng của số normal | 24 bit | 53 bit |
| Số dương normal nhỏ nhất | 2⁻¹²⁶ ≈ 1,17549435 × 10⁻³⁸ | 2⁻¹⁰²² ≈ 2,2250738585072014 × 10⁻³⁰⁸ |
| Số dương subnormal nhỏ nhất | 2⁻¹⁴⁹ ≈ 1,4 × 10⁻⁴⁵ | 2⁻¹⁰⁷⁴ ≈ 4,9 × 10⁻³²⁴ |
| Số hữu hạn dương lớn nhất | ≈ 3,4028235 × 10³⁸ | ≈ 1,7976931348623157 × 10³⁰⁸ |

Java có sẵn các hằng số hữu ích:

~~~java
Float.MAX_VALUE
Float.MIN_NORMAL
Float.MIN_VALUE
Double.MAX_VALUE
Double.MIN_NORMAL
Double.MIN_VALUE
~~~

**Rất dễ nhầm:** `Double.MIN_VALUE` **không phải giá trị âm nhỏ nhất**. Nó là **số dương khác 0 nhỏ nhất**, tức số subnormal dương thấp nhất. Giá trị hữu hạn âm có độ lớn lớn nhất là `-Double.MAX_VALUE`. Điều tương tự áp dụng cho `Float.MIN_VALUE`.

Miền số hữu hạn của `double` có khoảng âm, số 0 và khoảng dương; thêm vào đó còn có `-Infinity`, `+Infinity` và `NaN` (*Not a Number*). IEEE 754 phân biệt **`+0.0` và `-0.0`** bằng bit dấu dù toán tử `==` coi chúng bằng nhau.

## 3. Vì sao có số normal và subnormal?

Một số nhị phân *normal* khác 0 về ý tưởng có dạng:

\[
(-1)^s \times (1.f)_2 \times 2^e
\]

Trong đó `s` là bit dấu, `f` là các bit phân số và `e` là số mũ đã giải mã. Số `1` ở đầu phần định trị của giá trị normal là bit **ngầm định**. Vì thế `double` lưu 52 bit phân số nhưng có 53 bit có nghĩa đối với normal (và `float` là 23 + 1 = 24 bit).

Ở số mũ thấp nhất, không thể tiếp tục giảm số mũ normal. Chuẩn IEEE 754 cho phép **subnormal** sử dụng định trị không còn bit `1` ngầm định:

\[
(-1)^s \times (0.f)_2 \times 2^{e_{\min}}
\]

Cụ thể, với binary64: số normal dương nhỏ nhất là 2⁻¹⁰²²; một số subnormal có dạng `k × 2⁻¹⁰⁷⁴`, với `k` nguyên từ 1 đến 2⁵²−1. Khoảng cách giữa hai subnormal dương liền nhau luôn bằng `Double.MIN_VALUE`.

Bởi vậy, Java có thể biểu diễn những số nhỏ hơn `Double.MIN_NORMAL` mà chưa phải làm tròn ngay về 0. Đổi lại, **số bit có nghĩa hiệu dụng giảm dần** khi độ lớn của subnormal tiến về 0.

<text>Hình dung tiến dần về 0:</text>

~~~text
... normal ...  2^-1022  |  subnormal ...  2^-1074  |  +0.0
                 ↑                         ↑
           MIN_NORMAL                 MIN_VALUE
~~~

Biểu đồ là minh họa khái niệm; khoảng cách trên trục số không được vẽ theo tỷ lệ.

### Biên normal/subnormal

~~~java
double smallestNormal = Double.MIN_NORMAL;
double largestSubnormal = Math.nextDown(smallestNormal);
double smallestSubnormal = Double.MIN_VALUE;

System.out.println(largestSubnormal < smallestNormal); // true
System.out.println(largestSubnormal > 0.0);            // true
System.out.println(Math.nextUp(0.0) == smallestSubnormal); // true
~~~

Các đoạn mã ngắn trong bài, trừ chương trình hoàn chỉnh ở phần 8, được viết để đặt bên trong một phương thức hoặc `main`.

## 4. Overflow: kết quả vượt số hữu hạn lớn nhất

Xét phép nhân:

~~~java
double x = Double.MAX_VALUE;
double overflow = x * 2.0;
System.out.println(overflow);                 // Infinity
System.out.println(Double.isInfinite(overflow)); // true
~~~

`Double.MAX_VALUE` là số `double` hữu hạn dương lớn nhất. Kết quả toán học của phép nhân gấp đôi lớn hơn rất nhiều miền số hữu hạn, nên phép nhân được làm tròn theo quy tắc floating point và trả `+Infinity`.

Với kết quả âm vượt giới hạn, có thể nhận `-Infinity`:

~~~java
double negativeOverflow = -Double.MAX_VALUE * 2.0;
System.out.println(negativeOverflow); // -Infinity
~~~

Một số điểm quan trọng:

1. Phép toán số thực Java thông thường **không ném `ArithmeticException`** vì overflow/underflow.
2. `Infinity` là một giá trị floating point đặc biệt. Các phép tính tiếp theo có thể tiếp tục cho `Infinity` hoặc tạo `NaN`, chẳng hạn `Infinity - Infinity`.
3. Overflow có thể xảy ra ngay cả khi **kết quả cuối của phép biến đổi đại số** đáng lẽ hữu hạn: kết quả trung gian có thể tràn trước.

~~~java
double a = 1e200;
double b = 1e200;

double unstable = (a * b) / b;
double rearranged = a * (b / b);

System.out.println(unstable);   // Infinity
System.out.println(rearranged); // 1.0E200
~~~

Trong số học thực, hai biểu thức bằng nhau khi `b != 0`. Trong số học floating point, phép nhân trung gian `a * b` đã overflow. Biến đổi thứ tự tính toán chỉ phù hợp khi hiểu miền giá trị, quy tắc làm tròn, xử lý số 0/Infinity/NaN và các yêu cầu chính xác của bài toán.

### Infinity khác NaN

~~~java
double inf = Double.MAX_VALUE * 2.0;
double undefined = inf - inf;

System.out.println(Double.isInfinite(inf)); // true
System.out.println(Double.isNaN(undefined)); // true
~~~

`NaN` biểu diễn kết quả không xác định trong ngữ nghĩa dấu phẩy động; không phải số vô hạn. Ví dụ khác: `0.0 / 0.0` cho `NaN`, còn `1.0 / 0.0` cho `Infinity`. Cả ba kết quả đều không làm ném ngoại lệ số học.

## 5. Underflow: kết quả quá nhỏ để giữ đủ độ chính xác

Với số thực, underflow xảy ra ở đầu **gần số 0** của dải số. Phải phân biệt *kết quả subnormal vẫn khác 0* với *kết quả đã làm tròn thành 0*.

~~~java
double smallButRepresentable = Double.MIN_NORMAL / 2.0;
double tooSmall = Double.MIN_VALUE / 2.0;

System.out.println(smallButRepresentable > 0.0); // true
System.out.println(smallButRepresentable < Double.MIN_NORMAL); // true
System.out.println(tooSmall); // 0.0
~~~

`Double.MIN_NORMAL / 2` bằng 2⁻¹⁰²³ và biểu diễn được như một số subnormal. `Double.MIN_VALUE / 2` bằng 2⁻¹⁰⁷⁵, nằm đúng giữa 0 và số subnormal dương nhỏ nhất. Làm tròn **nearest, ties to even** cho ra `+0.0`.

**Lưu ý về thuật ngữ IEEE 754:** underflow theo nghĩa điều kiện ngoại lệ kỹ thuật liên quan đến tính *tininess* và mất độ chính xác. Trong bài học lập trình Java, “underflow thành subnormal/zero” mô tả hành vi vùng độ lớn rất nhỏ. Không nên khẳng định rằng **mọi** kết quả subnormal đều là một lỗi hay một phép toán underflow không chính xác: nhiều kết quả subnormal (như chia `MIN_NORMAL` cho 2) vẫn chính xác.

### Gradual underflow

Nếu không có subnormal, một kết quả dương nhỏ hơn `MIN_NORMAL` phải đột ngột trở thành 0. Subnormal giúp chuyển tiếp **dần dần**: rất nhiều giá trị nhỏ vẫn khác 0, nhưng độ chính xác tương đối kém dần.

Ví dụ:

~~~java
double halfNormal = Double.MIN_NORMAL / 2.0;
double smaller = halfNormal / 2.0;

System.out.println(halfNormal != 0.0); // true
System.out.println(smaller != 0.0);    // true
~~~

Đây là hành vi hữu ích khi một phép trừ của hai số dương gần nhau tạo giá trị rất nhỏ; vẫn có thể giữ được thông tin về sự khác nhau nếu kết quả nằm trong miền subnormal biểu diễn được.

## 6. Dấu của zero khi underflow

`double` phân biệt `+0.0` và `-0.0`. Một phép toán dương quá nhỏ thường làm tròn về `+0.0`; phép toán âm tương ứng có thể làm tròn về `-0.0`.

~~~java
double positiveZero = Double.MIN_VALUE / 2.0;
double negativeZero = -Double.MIN_VALUE / 2.0;

System.out.println(positiveZero); // 0.0
System.out.println(negativeZero); // -0.0
System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
~~~

Do đó không được kết luận hai giá trị floating point có biểu diễn bit giống nhau chỉ vì `a == b`. Khi cần quan sát dấu của số 0 hoặc bit của NaN, có thể dùng `Double.doubleToRawLongBits`; với `float`, dùng `Float.floatToRawIntBits`. Cơ chế so sánh số thực, sắp xếp và serialization phải xác định rõ có quan tâm `-0.0` hay không.

## 7. API Java để phát hiện tình trạng số thực

| API | Mục đích |
| --- | --- |
| `Double.isFinite(x)`, `Float.isFinite(x)` | Kiểm tra x là số hữu hạn (bao gồm ±0, normal và subnormal) |
| `Double.isInfinite(x)`, `Float.isInfinite(x)` | Kiểm tra ±Infinity |
| `Double.isNaN(x)`, `Float.isNaN(x)` | Kiểm tra NaN |
| `Double.MIN_NORMAL`, `Float.MIN_NORMAL` | Ngưỡng dương nhỏ nhất của số normal |
| `Double.MIN_VALUE`, `Float.MIN_VALUE` | Số dương khác 0 nhỏ nhất: subnormal thấp nhất |
| `Math.ulp(x)` | Khoảng cách theo đơn vị cuối cùng (*unit in last place*) tại x |
| `Math.nextUp(x)`, `Math.nextDown(x)` | Giá trị floating point kề trên/kề dưới |

Hàm nhận diện subnormal hữu hạn, khác 0:

~~~java
static boolean isSubnormal(double x) {
    return Double.isFinite(x)
            && x != 0.0
            && Math.abs(x) < Double.MIN_NORMAL;
}
~~~

Đây là một phương thức Java 17 độc lập trong thân lớp (chưa có `main`). Điều kiện `x != 0.0` loại cả `+0.0` và `-0.0`. Điều kiện `isFinite` loại Infinity/NaN; `Math.abs(x) < MIN_NORMAL` phân biệt miền subnormal với miền normal. Biểu thức tương tự áp dụng cho `float` với `Float.MIN_NORMAL` và `Float.isFinite`.

Đặc biệt:

~~~java
System.out.println(Math.ulp(0.0) == Double.MIN_VALUE); // true
System.out.println(Math.ulp(Double.MIN_NORMAL) == Double.MIN_VALUE); // true
System.out.println(Math.nextUp(0.0) == Double.MIN_VALUE); // true
~~~

Một số floating point hữu hạn *normal* có bước nhảy phụ thuộc độ lớn. Ở vùng subnormal dương, các giá trị liên tiếp cách nhau đúng `Double.MIN_VALUE`.

Không nên dùng `Math.getExponent(x)` một mình để phát hiện subnormal, vì nó trả `Double.MIN_EXPONENT - 1` cho **cả zero lẫn subnormal** (với `double` là −1023).

## 8. Chương trình Java 17+ đầy đủ, biên dịch và quan sát

Tạo tệp `FloatingRangeDemo.java`:

~~~java
public class FloatingRangeDemo {
    private static boolean isSubnormal(double x) {
        return Double.isFinite(x)
                && x != 0.0
                && Math.abs(x) < Double.MIN_NORMAL;
    }

    public static void main(String[] args) {
        double overflow = Double.MAX_VALUE * 2.0;
        double subnormal = Double.MIN_NORMAL / 2.0;
        double lost = Double.MIN_VALUE / 2.0;
        double negativeZero = -Double.MIN_VALUE / 2.0;

        System.out.println("overflow=" + overflow);
        System.out.println("overflow finite=" + Double.isFinite(overflow));
        System.out.println("subnormal=" + subnormal);
        System.out.println("is subnormal=" + isSubnormal(subnormal));
        System.out.println("min normal=" + Double.MIN_NORMAL);
        System.out.println("min positive=" + Double.MIN_VALUE);
        System.out.println("underflow to zero=" + lost);
        System.out.println("negative zero=" + negativeZero);
        System.out.println("negative reciprocal=" + (1.0 / negativeZero));
        System.out.println("ulp zero=" + Math.ulp(0.0));

        double parsedBig = Double.parseDouble("1e309");
        double parsedSmall = Double.parseDouble("1e-400");
        System.out.println("parsed big=" + parsedBig);
        System.out.println("parsed small=" + parsedSmall);

        float fSubnormal = Float.MIN_NORMAL / 2.0f;
        float fOverflow = Float.MAX_VALUE * 2.0f;
        System.out.println("float subnormal=" +
                (fSubnormal > 0.0f && fSubnormal < Float.MIN_NORMAL));
        System.out.println("float infinity=" + Float.isInfinite(fOverflow));

        double nan = overflow - overflow;
        System.out.println("NaN detected=" + Double.isNaN(nan));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 FloatingRangeDemo.java
java FloatingRangeDemo
~~~

Kết quả stdout:

~~~text
overflow=Infinity
overflow finite=false
subnormal=1.1125369292536007E-308
is subnormal=true
min normal=2.2250738585072014E-308
min positive=4.9E-324
underflow to zero=0.0
negative zero=-0.0
negative reciprocal=-Infinity
ulp zero=4.9E-324
parsed big=Infinity
parsed small=0.0
float subnormal=true
float infinity=true
NaN detected=true
~~~

Phân tích từng nhóm kết quả:

- `MAX_VALUE * 2` tràn thành Infinity; `isFinite` báo false.
- `MIN_NORMAL / 2` thuộc vùng subnormal nhưng còn khác 0; chương trình kiểm tra bằng miền giá trị chứ không chỉ dựa trên định dạng in.
- `MIN_VALUE / 2` nhỏ hơn giá trị dương khác 0 nhỏ nhất, nên được làm tròn thành 0.
- Underflow của số âm có thể tạo `-0.0`; phép lấy nghịch đảo minh họa dấu có ý nghĩa.
- `Double.parseDouble` xử lý chuỗi ngoài miền thành Infinity/0 theo quy tắc chuyển đổi floating point; phép parse không thay thế được việc **kiểm tra miền** nếu ứng dụng yêu cầu kết quả hữu hạn khác 0.
- `float` cũng có dải subnormal và overflow, nhưng với biên gần 0/Infinity lớn nhỏ khác `double`.
- `Infinity - Infinity` tạo NaN.

## 9. Literal số quá lớn/nhỏ: khác với kết quả phép toán runtime

Literals dấu phẩy động trong mã nguồn Java có quy tắc ở thời điểm biên dịch. Các ví dụ này **không biên dịch**:

~~~java
// double tooLarge = 1e309; // literal double ngoài miền
// double tooSmall = 1e-400; // literal double khác 0 quá nhỏ để thành nonzero
// float alsoTooLarge = 1e39f; // literal float ngoài miền
~~~

Khi cần minh họa overflow/underflow runtime, thực hiện phép toán từ các giá trị hợp lệ hoặc parse từ chuỗi ở runtime:

~~~java
double overflowRuntime = 1e308 * 10.0;
double underflowRuntime = 1e-300 * 1e-300;

System.out.println(overflowRuntime);  // Infinity
System.out.println(underflowRuntime); // 0.0
~~~

`Double.parseDouble("1e309")` trả Infinity và `Double.parseDouble("1e-400")` trả 0.0; khi giá trị chuỗi đến từ cấu hình/người dùng, lập trình viên cần kiểm tra để tránh silently chấp nhận dữ liệu mất miền.

Lưu ý riêng: literal `0.0` hoàn toàn hợp lệ; `0x0.0p0` cũng vậy. Giới hạn đối với literal *khác 0* quá nhỏ phản ánh quy tắc biên dịch, không có nghĩa ngôn ngữ cấm số 0.

## 10. Underflow không giống mất độ chính xác thông thường

Phần lớn số thập phân không có biểu diễn nhị phân hữu hạn, chẳng hạn `0.1`. Điều đó tạo ra **rounding error**, nhưng không nhất thiết là underflow:

~~~java
double x = 0.1 + 0.2;
System.out.println(x); // 0.30000000000000004
~~~

`0.30000000000000004` là kết quả làm tròn của các số normal và phép cộng; nó **không** thuộc vùng subnormal. Underflow liên quan đến độ lớn quá nhỏ gần 0, không phải mọi sai số dấu phẩy động.

Một kết quả subnormal vẫn có thể là biểu diễn **chính xác** của phép toán. Ví dụ, `Double.MIN_NORMAL / 2.0` là 2⁻¹⁰²³ và có thể biểu diễn chính xác dưới dạng subnormal. Khác biệt giữa **miền (range)** và **độ chính xác (precision)** là nền tảng của việc phân tích floating point.

Ngoài ra, đừng nhầm underflow của **giá trị** với underflow của **số mũ trong hàm Math.exp**: ví dụ `Math.exp(-1000)` có thể trả 0.0 vì kết quả toán học quá nhỏ để biểu diễn bằng `double`, không phải do số mũ nguyên trong máy “quay vòng”.

## 11. Các vấn đề phổ biến và cách xử lý

### 11.1. Intermediate overflow dù kết quả mong muốn hữu hạn

Công thức độ dài vector:

\[
\sqrt{x^2 + y^2}
\]

có thể overflow ở `x*x`/`y*y` dù kết quả cuối vẫn nhỏ hơn `Double.MAX_VALUE`.

~~~java
double x = 1e308;
double y = 1e308;

double naive = Math.sqrt(x * x + y * y);
double stable = Math.hypot(x, y);

System.out.println(naive);  // Infinity
System.out.println(stable); // 1.4142135623730951E308
~~~

`Math.hypot` được thiết kế giảm nguy cơ overflow/underflow trung gian. Nó vẫn trả Infinity khi độ lớn cuối cùng thật sự vượt dải biểu diễn.

### 11.2. Tích của nhiều số rất nhỏ bị làm tròn thành 0

~~~java
double a = 1e-200;
double b = 1e-200;
double c = 1e200;

double lostFirst = (a * b) * c;
double keptFirst = a * (b * c);

System.out.println(lostFirst); // 0.0
System.out.println(keptFirst); // 1.0E-200
~~~

Khi tính tích/xác suất của rất nhiều số nhỏ, đôi lúc chuyển sang **log-domain** (cộng logarithm thay vì nhân trực tiếp, rồi áp dụng biến đổi ổn định khi cần) giúp tránh underflow trung gian. Phải đặc biệt xử lý số 0, giá trị âm, NaN và yêu cầu trả lại giá trị cuối có thể hoặc không thể biểu diễn.

### 11.3. Định dạng in khác với tính chính xác

Java in `Double.MIN_VALUE` là `4.9E-324`; biểu thức đó là chuỗi thập phân ngắn đủ để round-trip về cùng giá trị `double`, không phải khẳng định giá trị nhị phân đúng bằng số hữu tỉ thập phân có bốn chữ số 4.9.

Tương tự, `System.out.println(0.1)` in `0.1`, nhưng lưu trữ nội bộ là số binary64 xấp xỉ 0,1. Đừng suy ra tính chính xác chỉ từ số chữ số hiển thị.

### 11.4. Kiểm tra kết quả trước khi sử dụng

Ví dụ nhận số thực từ một phép tính:

~~~java
static double requireFinite(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Kết quả phải hữu hạn");
    }
    return value;
}
~~~

Hàm này từ chối Infinity/NaN nhưng **cho phép 0 và subnormal**. Nếu nghiệp vụ cấm kết quả khác 0 bị mất thành 0, không có cách nhìn **chỉ vào kết quả 0.0 cuối cùng** để biết trước phép tính từng có một giá trị nhỏ hơn miền lưu trữ. Cần kiểm soát dữ liệu đầu vào, dùng phương pháp số ổn định hơn hoặc mô hình độ chính xác rộng hơn.

### 11.5. Khi nào dùng BigDecimal?

`BigDecimal` biểu diễn hệ thập phân với độ chính xác tùy ý (giới hạn tài nguyên và phạm vi scale) và quy tắc làm tròn có kiểm soát. Nó phù hợp với số tiền, dữ liệu thập phân chính xác hoặc phép tính cần giữ nhiều chữ số hơn `double`:

~~~java
import java.math.BigDecimal;

// Đoạn minh họa bên trong phương thức:
BigDecimal x = new BigDecimal("1e400");
BigDecimal y = x.multiply(BigDecimal.TEN);
System.out.println(y.toEngineeringString()); // 10E+400
~~~

`BigDecimal` không có giá trị NaN/Infinity giống `double`; không phải công cụ thay thế `double` cho mọi bài toán khoa học. Khi lập `BigDecimal` từ số thập phân cần giữ nguyên, ưu tiên constructor chuỗi (`new BigDecimal("0.1")`) hoặc `BigDecimal.valueOf(double)` phù hợp; `new BigDecimal(0.1)` giữ chính xác **giá trị nhị phân đã bị xấp xỉ** trước đó.

Lựa chọn kiểu dữ liệu phụ thuộc bài toán: phép đo kỹ thuật chấp nhận sai số thường vẫn dùng `double`; tài chính và dữ liệu decimal exact thường dùng `BigDecimal`; bài toán rất lớn/nhỏ có thể cần scale, log-domain hoặc thư viện số chuyên dụng.

## 12. Giá trị biên và những điều không nên nhầm

| Biểu thức (đặt trong một phương thức) | Kết quả/ý nghĩa |
| --- | --- |
| `Double.MAX_VALUE * 2.0` | `Infinity`: overflow dương |
| `-Double.MAX_VALUE * 2.0` | `-Infinity`: overflow âm |
| `Double.MIN_NORMAL / 2.0` | Subnormal dương khác 0, **chính xác** |
| `Double.MIN_VALUE / 2.0` | `+0.0` theo round-to-nearest ties-to-even |
| `-Double.MIN_VALUE / 2.0` | `-0.0` |
| `Math.nextUp(0.0)` | `Double.MIN_VALUE` |
| `Math.nextDown(0.0)` | `-Double.MIN_VALUE` |
| `Double.isFinite(Double.MIN_VALUE)` | `true`: subnormal vẫn hữu hạn |
| `Double.isNaN(Double.POSITIVE_INFINITY)` | `false` |
| `Double.NaN == Double.NaN` | `false` theo phép `==` của IEEE 754 |
| `Double.compare(-0.0, +0.0) < 0` | `true`: thứ tự theo `Double.compare` phân biệt signed zero |
| `1.0 / 0.0` | `Infinity`, không ném `ArithmeticException` |
| `1 / 0` | Lỗi phép chia số nguyên: khác quy tắc chia floating point |

### Java 17 và strict floating point

Từ **Java 17**, ngữ nghĩa floating point luôn strict theo Java Language Specification (JEP 306). Từ khóa `strictfp` vẫn tồn tại để tương thích mã cũ nhưng không còn cần thiết để bắt buộc strict trên Java 17+. Điều này giúp mã `float`/`double` có các quy tắc xác định của ngôn ngữ, nhưng **không loại bỏ** overflow, underflow, subnormal hay rounding error.

Java không cung cấp qua phép toán floating point thông thường cơ chế tự động ném exception cho mọi overflow/underflow hoặc một cờ trạng thái IEEE 754 mà lập trình viên có thể luôn truy cập trực tiếp. Nếu hệ thống cần phát hiện rủi ro, hãy kết hợp kiểm tra giá trị (`isFinite`, miền subnormal) với thiết kế thuật toán và dữ liệu đầu vào.

## 13. Tự kiểm tra

**Câu 1.** Vì sao `Double.MIN_VALUE` lớn hơn 0 nhưng nhỏ hơn `Double.MIN_NORMAL`?

Vì `MIN_VALUE` là số subnormal dương nhỏ nhất (2⁻¹⁰⁷⁴), còn `MIN_NORMAL` là số normal dương nhỏ nhất (2⁻¹⁰²²). Tên `MIN_VALUE` ở đây nói đến độ lớn **dương khác 0**, không phải điểm âm cực tiểu của trục số.

**Câu 2.** `Double.MIN_NORMAL / 2.0` có bắt buộc bằng 0 hay mất chính xác không?

Không. 2⁻¹⁰²³ là một giá trị subnormal có thể biểu diễn **chính xác** dưới dạng binary64.

**Câu 3.** Vì sao `Double.MIN_VALUE / 2.0` cho `0.0`?

Vì giá trị toán học 2⁻¹⁰⁷⁵ nằm giữa 0 và giá trị dương khác 0 nhỏ nhất; mặc định round-to-nearest ties-to-even chọn +0.0.

**Câu 4.** Có thể dựa vào `Double.isFinite(result)` để phát hiện mọi underflow không?

Không. `0.0` và các số subnormal đều **hữu hạn**. `isFinite` nhận biết NaN/Infinity; dưới chuẩn cần kiểm tra thêm điều kiện khác 0 và `abs(result) < MIN_NORMAL`, còn việc làm tròn thành 0 cần được phát hiện bằng thông tin về bài toán hoặc phép tính trước đó.

**Câu 5.** Vì sao `Math.hypot(x, y)` thường an toàn hơn `Math.sqrt(x*x + y*y)`?

Nó được thiết kế hạn chế overflow và underflow trong các kết quả trung gian khi tính khoảng cách; việc bình phương trực tiếp có thể tạo Infinity/0 trước khi căn bậc hai được áp dụng.

**Câu 6.** Có nên thay mọi phép tính `double` bằng `BigDecimal`?

Không. `BigDecimal` hữu ích khi cần chính xác thập phân và kiểm soát làm tròn; nó thay đổi mô hình dữ liệu, tốc độ, bộ nhớ và thuật toán. Với bài toán khoa học/kỹ thuật, chọn `double` và thuật toán số ổn định có thể là lựa chọn phù hợp hơn.

## 14. Tóm tắt và tham khảo

- **Overflow:** độ lớn vượt miền hữu hạn → thường `±Infinity`, cần kiểm tra `isFinite`/`isInfinite`.
- **Underflow:** độ lớn quá gần 0 → kết quả subnormal hoặc bị làm tròn về `±0.0`; không nhất thiết là một ngoại lệ Java.
- **Subnormal:** giá trị khác 0 có `abs(x) < MIN_NORMAL`; giúp *gradual underflow* nhưng có ít bit có nghĩa hiệu dụng.
- `MIN_VALUE` là số dương khác 0 nhỏ nhất, còn `MIN_NORMAL` là số normal dương nhỏ nhất.
- Viết thuật toán tránh kết quả trung gian quá lớn/quá nhỏ và kiểm tra NaN, Infinity, zero có dấu, tính chính xác theo nhu cầu.

Tài liệu tra cứu:

- [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html) và [Float](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): `MAX_VALUE`, `MIN_NORMAL`, `MIN_VALUE` và các API kiểm tra.
- [Java SE 17 — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `ulp`, `nextUp`, `nextDown`, `hypot`.
- [JLS SE 17 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): số hữu hạn, subnormal, NaN, Infinity và zero.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): thay đổi ngữ nghĩa strict của Java 17.
