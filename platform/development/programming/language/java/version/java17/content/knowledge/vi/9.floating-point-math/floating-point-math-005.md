# Tràn, hụt và giá trị dưới chuẩn của số thực trong Java 17

Các kiểu số thực `float` và `double` trong Java có phạm vi biểu diễn hữu hạn. Khi kết quả tính toán vượt quá phạm vi đó, phép toán có thể tạo ra vô cực (`Infinity`); khi kết quả quá nhỏ, nó có thể được làm tròn thành **số dưới chuẩn (subnormal)** hoặc thành số 0. Những hiện tượng này thuộc mô hình số thực dấu phẩy động của Java và cần được tính đến khi viết thuật toán khoa học, xử lý đo lường, tính toán tài chính, đồ họa và kiểm tra dữ liệu.

Java 17 sử dụng ngữ nghĩa dấu phẩy động nghiêm ngặt theo IEEE 754 cho mọi biểu thức (`JEP 306`). Bài này giải thích **tràn (overflow)**, **hụt (underflow)**, **giá trị dưới chuẩn**, số 0 có dấu, `Infinity` và `NaN`; đồng thời hướng dẫn cách quan sát, kiểm soát và lựa chọn kiểu dữ liệu phù hợp. Các ví dụ dùng tính năng chính thức của Java 17, không cần preview.

## 1. Cách Java biểu diễn số thực

Hai kiểu dấu phẩy động nguyên thủy của Java là:

- `float`: độ chính xác đơn, thường chiếm 32 bit.
- `double`: độ chính xác kép, thường chiếm 64 bit và là kiểu mặc định cho literal số thực không có hậu tố.

Cả hai theo định dạng nhị phân IEEE 754. Các bit được chia thành dấu, số mũ và phần trị (fraction/significand).

| Thành phần | `float` (binary32) | `double` (binary64) |
| --- | ---: | ---: |
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit số mũ | 8 | 11 |
| Bit fraction | 23 | 52 |
| Bias của số mũ | 127 | 1023 |
| Độ chính xác xấp xỉ | 7 chữ số thập phân | 15–17 chữ số thập phân |

Với một số chuẩn hóa (normal), giá trị có dạng:

\[
(-1)^{sign} \times 1.fraction \times 2^{exponent-bias}
\]

Bit 1 đứng trước dấu chấm nhị phân là bit ẩn (implicit leading bit), vì vậy độ chính xác có 24 bit significand đối với `float` và 53 bit đối với `double`.

Không phải mọi giá trị toán học đều biểu diễn chính xác được bằng số nhị phân hữu hạn. Ví dụ, 0.1 ở hệ thập phân có biểu diễn nhị phân tuần hoàn; khi lưu trong `double`, Java phải chọn giá trị dấu phẩy động gần nhất có thể biểu diễn.

## 2. Phạm vi normal và subnormal

IEEE 754 dành một vùng mã hóa riêng cho số mũ bằng toàn bit 0. Nếu fraction khác 0, giá trị đó là **subnormal**. Nếu fraction bằng 0, đó là số 0 có dấu.

Số normal có bit đầu significand ngầm định bằng 1. Số subnormal không có bit 1 ngầm định này; significand bắt đầu bằng 0, nhờ vậy định dạng có thể biểu diễn những giá trị dương rất nhỏ, nằm liên tục ngay dưới ngưỡng normal.

Các hằng số quan trọng trong Java:

| Hằng số | `float` | `double` | Ý nghĩa |
| --- | ---: | ---: | --- |
| `MAX_VALUE` | xấp xỉ `3.4028235E38` | xấp xỉ `1.7976931348623157E308` | Giá trị hữu hạn dương lớn nhất |
| `MIN_NORMAL` | xấp xỉ `1.17549435E-38` | xấp xỉ `2.2250738585072014E-308` | Giá trị dương normal nhỏ nhất |
| `MIN_VALUE` | xấp xỉ `1.4E-45` | xấp xỉ `4.9E-324` | Giá trị dương khác 0 nhỏ nhất, thuộc vùng subnormal |

**Lưu ý quan trọng:**

`Float.MIN_VALUE` và `Double.MIN_VALUE` **không phải** số âm nhỏ nhất, cũng không phải giá trị normal nhỏ nhất. Chúng là **giá trị dương khác 0 nhỏ nhất** mà kiểu tương ứng biểu diễn được. Muốn lấy ngưỡng normal nhỏ nhất, dùng `MIN_NORMAL`.

### 2.1. Công thức của số subnormal

Đối với `float`, số subnormal có dạng:

\[
(-1)^{sign} \times fraction \times 2^{-149}
\]

Đối với `double`:

\[
(-1)^{sign} \times fraction \times 2^{-1074}
\]

Ở đây `fraction` được hiểu là phân số nhị phân có 23 bit đối với `float` hoặc 52 bit đối với `double`. Vì không còn bit 1 ẩn, các giá trị subnormal có ít bit chính xác có nghĩa hơn so với normal.

### 2.2. Khoảng cách giữa các giá trị biểu diễn được

Hai số dấu phẩy động liên tiếp không cách nhau một khoảng cố định trên toàn miền.

- Ở vùng normal, khoảng cách phụ thuộc số mũ: số càng lớn thì khoảng cách tuyệt đối giữa hai giá trị liền kề càng lớn.
- Ở vùng subnormal, bước biểu diễn là cố định và bằng `MIN_VALUE`.
- Ở vùng quanh 0, các subnormal cho phép tiến dần về 0 thay vì nhảy trực tiếp từ `MIN_NORMAL` về 0.

Có thể dùng `Math.ulp(value)` để xem khoảng cách biểu diễn (unit in the last place) quanh một giá trị:

~~~java
System.out.println(Math.ulp(1.0));
System.out.println(Math.ulp(1.0f));
System.out.println(Double.MIN_VALUE);
~~~

Kết quả đầu tiên xấp xỉ `2.220446049250313E-16`; kết quả thứ hai xấp xỉ `1.1920929E-7`. `Math.ulp` hữu ích khi phân tích sai số làm tròn và độ phân giải của một kiểu số thực.

## 3. Tràn số thực (floating-point overflow)

**Overflow** xảy ra khi kết quả toán học có độ lớn vượt quá khả năng biểu diễn hữu hạn của kiểu dấu phẩy động. Với phép toán dấu phẩy động Java, kết quả không tự động ném `ArithmeticException` như phép chia số nguyên cho 0; kết quả có thể trở thành `POSITIVE_INFINITY` hoặc `NEGATIVE_INFINITY`.

Ví dụ:

~~~java
double tooLarge = Double.MAX_VALUE * 2.0;
System.out.println(tooLarge);                 // Infinity
System.out.println(Double.isInfinite(tooLarge)); // true
System.out.println(Double.isFinite(tooLarge));   // false
~~~

Với `float`:

~~~java
float tooLarge = Float.MAX_VALUE * 2.0f;
System.out.println(tooLarge); // Infinity
~~~

Dùng hậu tố `f` để literal là `float`. Literal số thực không có hậu tố mặc định là `double`.

### 3.1. Phép toán nào có thể gây overflow?

Overflow có thể xảy ra trong nhiều phép toán:

~~~java
double a = Double.MAX_VALUE;

double multiply = a * 2.0;     // Infinity
double add = a + a;            // Infinity
double divideByTiny = a / 1e-300; // Infinity
~~~

Một phép tính có thể tràn ở **giá trị trung gian**, dù kết quả toán học cuối cùng đáng lẽ nằm trong miền biểu diễn nếu tính theo thứ tự khác. Ví dụ tính độ dài vector bằng cách bình phương trực tiếp các thành phần lớn có thể tràn trước khi lấy căn.

~~~java
double x = 3e200;
double y = 4e200;

double naive = Math.sqrt(x * x + y * y);
double stable = Math.hypot(x, y);

System.out.println(naive);  // Infinity
System.out.println(stable); // xấp xỉ 5.0E200
~~~

`Math.hypot` được thiết kế để tính độ dài mà hạn chế overflow/underflow ở các bước trung gian. Với các thuật toán số học, nên ưu tiên hàm thư viện đã được thiết kế cho miền giá trị rộng thay vì tự nhân/chia một cách ngây thơ.

### 3.2. Overflow không giống phép chia cho 0 của số nguyên

Java xử lý hai nhóm kiểu khác nhau:

~~~java
double floating = 1.0 / 0.0;
System.out.println(floating); // Infinity

// int integer = 1 / 0;
// Ném ArithmeticException nếu bỏ comment.
~~~

Phép chia số thực cho 0 tạo giá trị đặc biệt theo IEEE 754; phép chia số nguyên cho 0 ném `ArithmeticException`. Không nên dựa vào hành vi của số nguyên để suy luận cách `float`/`double` hoạt động.

### 3.3. Chuyển `double` sang `float` cũng có thể tràn

~~~java
double source = 1e100;
float narrowed = (float) source;

System.out.println(narrowed); // Infinity
~~~

Ép kiểu thu hẹp từ `double` sang `float` có thể làm mất độ chính xác, đưa giá trị vào subnormal, thành 0 hoặc thành vô cực nếu giá trị vượt miền của `float`. Cần kiểm tra sau khi chuyển nếu miền giá trị hữu hạn là điều kiện bắt buộc.

## 4. Hụt số thực (floating-point underflow)

**Underflow** xảy ra khi kết quả có độ lớn quá nhỏ so với độ phân giải của kiểu dấu phẩy động. Với định dạng IEEE 754 hỗ trợ subnormal, kết quả không nhất thiết trở thành 0 ngay khi nhỏ hơn `MIN_NORMAL`.

Quá trình có thể diễn ra như sau:

1. Kết quả vẫn nằm trong vùng normal: biểu diễn bình thường.
2. Kết quả nhỏ hơn `MIN_NORMAL` nhưng còn đủ lớn để biểu diễn: được biểu diễn bằng subnormal.
3. Kết quả nhỏ hơn mức có thể phân biệt ở vùng subnormal: sau làm tròn có thể thành một subnormal nhỏ hơn hoặc thành signed zero.

Đây gọi là **gradual underflow** (hụt dần): các giá trị giảm dần qua vùng subnormal đến 0.

### 4.1. Nhỏ hơn MIN_NORMAL chưa có nghĩa là bằng 0

~~~java
double smallestNormal = Double.MIN_NORMAL;
double subnormal = smallestNormal / 2.0;

System.out.println(smallestNormal);
System.out.println(subnormal);
System.out.println(subnormal > 0.0); // true
System.out.println(subnormal < Double.MIN_NORMAL); // true
~~~

`subnormal` vẫn dương và khác 0, nhưng nằm dưới ngưỡng normal. Java vẫn giữ được giá trị này.

### 4.2. Kết quả quá nhỏ có thể làm tròn về 0

~~~java
double smallestPositive = Double.MIN_VALUE;
double half = smallestPositive / 2.0;

System.out.println(smallestPositive); // xấp xỉ 4.9E-324
System.out.println(half);             // 0.0
System.out.println(half == 0.0);      // true
~~~

`Double.MIN_VALUE` chính là một bước subnormal nhỏ nhất. Chia đôi nó tạo giá trị nằm giữa 0 và `Double.MIN_VALUE`; với quy tắc làm tròn gần nhất, hòa về số chẵn, kết quả là 0.

### 4.3. Phép nhân rất nhỏ

~~~java
double product = 1e-200 * 1e-200;
System.out.println(product); // 0.0
~~~

Giá trị toán học là khoảng `1e-400`, nhỏ hơn mức `double` có thể biểu diễn khác 0, nên kết quả bị làm tròn về 0.

Đối với `float`, phạm vi còn hẹp hơn:

~~~java
float tiny = 1e-30f * 1e-20f;
System.out.println(tiny); // 0.0f
~~~

Nếu bài toán cần bảo toàn những đại lượng rất nhỏ, hãy đánh giá miền giá trị của dữ liệu và lựa chọn kiểu phù hợp; đổi từ `float` sang `double` có thể giúp mở rộng miền biểu diễn, nhưng không giải quyết mọi giới hạn số học.

## 5. Ví dụ quan sát overflow, subnormal và underflow

Tạo file **`FloatingRangeDemo.java`**:

~~~java
public final class FloatingRangeDemo {

    private FloatingRangeDemo() {
    }

    public static void main(String[] args) {
        double overflow = Double.MAX_VALUE * 2.0;
        double subnormal = Double.MIN_NORMAL / 2.0;
        double roundedToZero = Double.MIN_VALUE / 2.0;
        double negativeZero = -Double.MIN_VALUE / 2.0;

        System.out.println("MAX_VALUE = " + Double.MAX_VALUE);
        System.out.println("MIN_NORMAL = " + Double.MIN_NORMAL);
        System.out.println("MIN_VALUE = " + Double.MIN_VALUE);

        System.out.println("overflow = " + overflow);
        System.out.println("isInfinite = " + Double.isInfinite(overflow));
        System.out.println("isFinite = " + Double.isFinite(overflow));

        System.out.println("subnormal = " + subnormal);
        System.out.println("subnormal > 0 = " + (subnormal > 0.0));
        System.out.println("roundedToZero = " + roundedToZero);
        System.out.println("negativeZero = " + negativeZero);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 FloatingRangeDemo.java
java FloatingRangeDemo
~~~

Kết quả có dạng:

~~~text
MAX_VALUE = 1.7976931348623157E308
MIN_NORMAL = 2.2250738585072014E-308
MIN_VALUE = 4.9E-324
overflow = Infinity
isInfinite = true
isFinite = false
subnormal = 1.1125369292536007E-308
subnormal > 0 = true
roundedToZero = 0.0
negativeZero = -0.0
~~~

Các giá trị được in theo cách chuyển đổi số thực sang chuỗi của Java. Điểm cần nhận biết là:

- `overflow` trở thành vô cực dương.
- `subnormal` nhỏ hơn `MIN_NORMAL` nhưng vẫn lớn hơn 0.
- `roundedToZero` đã bị làm tròn thành 0.
- `negativeZero` giữ dấu âm sau khi hụt về 0.

## 6. Số 0 có dấu (positive zero và negative zero)

IEEE 754 có cả `+0.0` và `-0.0`. Chúng so sánh bằng nhau bằng toán tử `==`, nhưng có biểu diễn bit và một số hành vi số học khác nhau.

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);            // Infinity
System.out.println(1.0 / negativeZero);            // -Infinity
~~~

Underflow có thể giữ dấu của kết quả:

~~~java
double positive = Double.MIN_VALUE / 2.0;
double negative = -Double.MIN_VALUE / 2.0;

System.out.println(positive); // 0.0
System.out.println(negative); // -0.0
~~~

Nếu logic nghiệp vụ chỉ quan tâm giá trị bằng 0, `== 0.0` thường đủ. Nếu dấu có ý nghĩa (ví dụ hướng chuyển động, giới hạn một phía hoặc thuật toán số học), cần giữ và kiểm tra dấu riêng.

Có thể dùng `Double.doubleToRawLongBits` để quan sát biểu diễn:

~~~java
long positiveBits = Double.doubleToRawLongBits(+0.0);
long negativeBits = Double.doubleToRawLongBits(-0.0);

System.out.printf("%016X%n", positiveBits);
System.out.printf("%016X%n", negativeBits);
~~~

Giá trị bit lần lượt là `0000000000000000` và `8000000000000000`. Không nên dùng phép so sánh `==` để phân biệt hai số 0 có dấu.

## 7. Infinity và NaN là giá trị đặc biệt

Khi xảy ra overflow, kết quả có thể là vô cực. Ngoài ra, IEEE 754 còn định nghĩa `NaN` (*Not a Number*) cho các phép toán không tạo ra một số thực có nghĩa theo quy tắc dấu phẩy động.

Ví dụ:

~~~java
double positiveInfinity = 1.0 / 0.0;
double negativeInfinity = -1.0 / 0.0;
double notANumber = 0.0 / 0.0;
double alsoNaN = Math.sqrt(-1.0);

System.out.println(positiveInfinity); // Infinity
System.out.println(negativeInfinity); // -Infinity
System.out.println(notANumber);       // NaN
System.out.println(alsoNaN);          // NaN
~~~

Một số quy tắc đáng chú ý:

| Biểu thức | Kết quả |
| --- | --- |
| Giá trị hữu hạn dương chia 0.0 | `POSITIVE_INFINITY` |
| Giá trị hữu hạn âm chia 0.0 | `NEGATIVE_INFINITY` |
| 0.0 chia 0.0 | `NaN` |
| `Infinity - Infinity` | `NaN` |
| `0.0 * Infinity` | `NaN` |
| `sqrt(-1.0)` | `NaN` |
| Giá trị hữu hạn chia `Infinity` | Signed zero |

`NaN` có một tính chất rất quan trọng:

~~~java
double value = Double.NaN;

System.out.println(value == Double.NaN); // false
System.out.println(Double.isNaN(value));  // true
~~~

Không kiểm tra NaN bằng `== Double.NaN`. Hãy dùng `Double.isNaN(value)` hoặc `Float.isNaN(value)`.

Tương tự, để kiểm tra vô cực và hữu hạn, dùng các API chuyên dụng:

~~~java
Double.isInfinite(value);
Double.isFinite(value);
Float.isInfinite(value);
Float.isFinite(value);
~~~

`isFinite` trả về `false` đối với cả NaN và hai vô cực.

## 8. Phân biệt overflow, underflow và mất độ chính xác

Ba hiện tượng này có liên quan nhưng không đồng nghĩa:

| Hiện tượng | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Overflow | Kết quả vượt miền hữu hạn | `Double.MAX_VALUE * 2` thành `Infinity` |
| Underflow | Kết quả rất nhỏ, bị biểu diễn dưới dạng subnormal hoặc làm tròn về zero | `Double.MIN_VALUE / 2` thành `0.0` |
| Mất độ chính xác (rounding/precision loss) | Giá trị toán học không thể biểu diễn chính xác bằng số bit hữu hạn | `0.1 + 0.2 != 0.3` |
| Cancellation | Trừ hai giá trị gần nhau làm mất các chữ số có nghĩa | `(1.000000000000001 - 1.0)` chỉ giữ ít chữ số đáng tin |

### 8.1. Mất độ chính xác không nhất thiết là underflow

~~~java
double result = 0.1 + 0.2;
System.out.println(result);          // 0.30000000000000004
System.out.println(result == 0.3);   // false
~~~

Kết quả vẫn nằm rất xa cả 0 và `Double.MAX_VALUE`. Đây là sai số biểu diễn/làm tròn, không phải overflow hay underflow.

### 8.2. Cancellation không phải overflow

~~~java
double a = 1.000000000000001;
double b = 1.0;
double difference = a - b;
~~~

Hai số gần nhau khi trừ có thể làm mất các chữ số có nghĩa của kết quả. Đây là vấn đề ổn định số học (*numerical stability*), không đồng nghĩa kết quả đã rơi vào vùng subnormal.

Khi thiết kế thuật toán, cần xác định đang gặp loại vấn đề nào trước khi chọn cách xử lý. Tăng kiểu từ `float` lên `double` có thể giảm một số lỗi làm tròn, nhưng không sửa được một thuật toán vốn không ổn định.

## 9. Cách phát hiện và kiểm soát giá trị ngoài miền mong muốn

### 9.1. Kiểm tra dữ liệu đầu vào

Nếu nghiệp vụ chỉ chấp nhận số hữu hạn:

~~~java
static double requireFinite(double value, String name) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException(
                name + " phải là số hữu hạn");
    }
    return value;
}
~~~

Dùng kiểm tra trước khi đưa giá trị vào tính toán để tránh NaN/Infinity lan truyền qua nhiều tầng.

### 9.2. Kiểm tra kết quả sau phép toán

~~~java
double result = input * factor;

if (!Double.isFinite(result)) {
    throw new ArithmeticException("Kết quả nằm ngoài miền hữu hạn");
}
~~~

Java không tự ném ngoại lệ cho overflow của `double`; nếu hợp đồng nghiệp vụ yêu cầu lỗi, ứng dụng phải chủ động kiểm tra.

### 9.3. Kiểm tra miền nghiệp vụ thay vì chỉ kiểm tra hữu hạn

Một giá trị hữu hạn vẫn có thể không hợp lệ:

~~~java
double temperature = -500.0;

if (!Double.isFinite(temperature)
        || temperature < -273.15
        || temperature > 1000.0) {
    throw new IllegalArgumentException("Nhiệt độ ngoài miền cho phép");
}
~~~

Hợp đồng dữ liệu cần xác định cả miền hữu hạn, đơn vị đo và giới hạn nghiệp vụ.

### 9.4. Tránh overflow ở bước trung gian

Khi tính toán biểu thức có thể tạo số trung gian rất lớn hoặc rất nhỏ:

- Dùng hàm thư viện đã được thiết kế để ổn định số học, như `Math.hypot`.
- Chuẩn hóa/scaling các giá trị trước khi nhân hoặc bình phương nếu thuật toán cho phép.
- Chọn thứ tự phép toán phù hợp để tránh tràn trung gian không cần thiết.
- Với thuật toán khoa học, phân tích sai số và miền dữ liệu bằng test ở cả giá trị lớn, nhỏ và gần ranh giới.

Không có một mẹo chung cho mọi biểu thức. Cần dựa vào ý nghĩa toán học và giới hạn đầu vào của bài toán.

## 10. Chọn `float`, `double`, `BigDecimal` hay kiểu số nguyên?

`double` có phạm vi rộng và độ chính xác cao hơn `float`, nên thường là lựa chọn mặc định cho tính toán dấu phẩy động trong Java. Nhưng có bài toán cần số thập phân chính xác theo quy tắc nghiệp vụ hoặc số nguyên với miền rất lớn.

| Kiểu | Phù hợp khi | Giới hạn cần hiểu |
| --- | --- | --- |
| `float` | Đồ họa, dữ liệu lớn cần tiết kiệm bộ nhớ, API yêu cầu binary32 | Phạm vi và độ chính xác thấp hơn `double` |
| `double` | Tính toán khoa học/kỹ thuật thông dụng, đo lường và số thực tổng quát | Có rounding, overflow và underflow |
| `BigDecimal` | Số thập phân cần quy tắc độ chính xác/làm tròn rõ, chẳng hạn số tiền | Tốn tài nguyên hơn; cần quy định scale và rounding |
| `BigInteger` | Số nguyên lớn hơn miền `long` | Không biểu diễn phần thập phân |

### 10.1. Dùng BigDecimal khi cần số thập phân có kiểm soát

Không nên khởi tạo `BigDecimal` từ literal `double` nếu muốn giữ giá trị thập phân người dùng nhập:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.08");

BigDecimal tax = price.multiply(taxRate)
        .setScale(2, RoundingMode.HALF_UP);

BigDecimal total = price.add(tax);

System.out.println(total); // 21.59
~~~

`new BigDecimal("19.99")` giữ giá trị thập phân chính xác được chỉ định bởi chuỗi. Ngược lại, `new BigDecimal(0.1)` nhận giá trị `double` đã được xấp xỉ ở hệ nhị phân, rồi biểu diễn chính xác chính giá trị xấp xỉ đó ở dạng thập phân.

`BigDecimal.valueOf(0.1)` thường là lựa chọn thuận tiện hơn constructor nhận `double` trực tiếp vì nó dựa trên biểu diễn chuỗi chuẩn của giá trị double. Với dữ liệu tiền tệ từ người dùng, nên parse chuỗi đầu vào và quy định rõ scale/rounding theo nghiệp vụ.

`BigDecimal` không có các giá trị `NaN` hoặc `Infinity`. Tuy nhiên, phép chia không có kết quả thập phân hữu hạn nếu không chỉ định độ chính xác có thể ném `ArithmeticException`:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3);

// one.divide(three) // ArithmeticException: kết quả thập phân vô hạn tuần hoàn

BigDecimal result = one.divide(
        three,
        10,
        RoundingMode.HALF_UP
);
~~~

`BigDecimal` cũng không phải giải pháp thay thế mọi phép tính khoa học: cần cân nhắc hiệu năng, quy tắc làm tròn và mô hình dữ liệu phù hợp.

### 10.2. Dùng BigInteger cho số nguyên không được phép tràn

Với phép tính số nguyên cần phát hiện overflow, có thể dùng `Math.addExact`, `Math.multiplyExact` hoặc `BigInteger` tùy yêu cầu:

~~~java
long result = Math.multiplyExact(1_000_000_000L, 1_000_000_000L);
~~~

Đoạn trên ném `ArithmeticException` nếu phép nhân vượt miền `long`. Đây là cơ chế dành cho số nguyên; `Math.multiplyExact` không áp dụng cho `float`/`double`.

## 11. Java 17 luôn dùng strict floating-point semantics

Trước Java 17, Java có khái niệm biểu thức dấu phẩy động *value set* và từ khóa `strictfp` để yêu cầu đánh giá nghiêm ngặt trên những nền tảng có thể dùng giá trị trung gian mở rộng. Từ **Java 17 (JEP 306)**, mọi biểu thức dấu phẩy động luôn được đánh giá nghiêm ngặt theo ngữ nghĩa chuẩn; `strictfp` không còn cần thiết để đạt hành vi đó.

Ví dụ:

~~~java
public strictfp class Calculation {
    static double calculate(double x, double y) {
        return x * y + 1.0;
    }
}
~~~

Trong Java 17, modifier `strictfp` ở ví dụ trên là dư thừa. Không cần thêm `strictfp` vào class hoặc method mới chỉ để “bật IEEE 754”. Có thể gặp code cũ vẫn giữ từ khóa này; điều đó không làm thay đổi ý nghĩa của chủ đề overflow/underflow ở Java 17.

Strict semantics không có nghĩa mọi phép tính thập phân trở nên chính xác tuyệt đối. Nó đảm bảo cách đánh giá dấu phẩy động tuân theo quy tắc xác định của Java, còn giới hạn bit, làm tròn, overflow và underflow vẫn tồn tại.

## 12. Bài thực hành: kiểm tra các ranh giới biểu diễn

Tạo chương trình kiểm tra một số giá trị quan trọng:

~~~java
public final class FloatingBoundaryExercise {

    private FloatingBoundaryExercise() {
    }

    public static void main(String[] args) {
        double normal = Double.MIN_NORMAL;
        double subnormal = normal / 2.0;
        double smallest = Double.MIN_VALUE;
        double zero = smallest / 2.0;
        double overflow = Double.MAX_VALUE * 2.0;

        print("normal", normal);
        print("subnormal", subnormal);
        print("smallest", smallest);
        print("underflow-to-zero", zero);
        print("overflow", overflow);
    }

    private static void print(String label, double value) {
        System.out.printf(
                "%-20s value=%-24s finite=%-5s zero=%s%n",
                label,
                value,
                Double.isFinite(value),
                value == 0.0
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 FloatingBoundaryExercise.java
java FloatingBoundaryExercise
~~~

Sau khi chạy, trả lời:

1. Vì sao `subnormal` vẫn có `finite=true`?
2. Vì sao `underflow-to-zero` không ném ngoại lệ?
3. Vì sao `overflow` có `finite=false`?
4. Nếu đổi `double` thành `float`, ranh giới biểu diễn thay đổi ra sao?
5. Giá trị `-0.0` có so sánh bằng `0.0` không? Có thể phân biệt chúng bằng cách nào?

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Kết quả phép nhân thành `Infinity` | Giá trị vượt miền hữu hạn | Kiểm tra đầu vào/kết quả, scaling hoặc dùng kiểu số khác |
| Giá trị nhỏ thành `0.0` | Underflow sau làm tròn | Đánh giá miền dữ liệu, dùng `double` thay `float` hoặc mô hình số khác |
| `Double.MIN_VALUE` bị hiểu là số normal nhỏ nhất | Nhầm tên hằng số | Dùng `Double.MIN_NORMAL` cho ngưỡng normal |
| Dữ liệu NaN lọt vào hệ thống | Chỉ kiểm tra null hoặc so sánh số | Dùng `Double.isFinite`/`isNaN` |
| `value == Double.NaN` luôn false | NaN không bằng bất kỳ giá trị nào, kể cả chính nó | Dùng `Double.isNaN(value)` |
| Chia 0.0 không ném lỗi | Quy tắc IEEE 754 của kiểu dấu phẩy động | Chủ động kiểm tra nếu nghiệp vụ cấm mẫu số 0 |
| Tính độ dài vector thành Infinity dù đáp số có thể hữu hạn | Bình phương thành phần gây overflow trung gian | Dùng `Math.hypot` hoặc thuật toán scaling |
| Chuyển `double` sang `float` thành Infinity | Giá trị không nằm trong miền `float` | Kiểm tra sau narrowing conversion |
| Dùng `BigDecimal` nhưng kết quả chia bị lỗi | Chia thập phân vô hạn mà không chỉ định precision/rounding | Dùng overload có scale hoặc `MathContext` |
| Thêm `strictfp` nhưng vẫn thấy sai số thập phân | Strict không đồng nghĩa chính xác tuyệt đối | Phân biệt rounding với overflow/underflow |

## 14. Bài tập mở rộng

1. **Overflow:** tính `Float.MAX_VALUE * 2.0f` và `Double.MAX_VALUE * 2.0`. Kiểm tra bằng `isInfinite` và `isFinite`.
2. **Subnormal:** bắt đầu từ `Double.MIN_NORMAL`, chia liên tiếp cho 2.0 và quan sát thời điểm giá trị nhỏ hơn normal nhưng vẫn khác 0.
3. **Underflow:** tính `Double.MIN_VALUE / 2.0` và `-Double.MIN_VALUE / 2.0`; so sánh kết quả và biểu diễn bit của hai số 0.
4. **NaN:** thử `0.0 / 0.0`, `Math.sqrt(-1)` và `Double.isNaN`; quan sát vì sao so sánh bằng không dùng để phát hiện NaN.
5. **Tràn trung gian:** so sánh `Math.sqrt(x*x + y*y)` với `Math.hypot(x, y)` cho các giá trị `x=3e200`, `y=4e200`.
6. **Số thập phân:** so sánh `new BigDecimal("0.1")`, `BigDecimal.valueOf(0.1)` và `new BigDecimal(0.1)`; giải thích khác biệt về nguồn giá trị.

Khi xử lý số thực, cần biết dữ liệu có thể lớn đến đâu, nhỏ đến đâu, sai số nào chấp nhận được và cách ứng dụng phản ứng khi kết quả ra ngoài miền. Trong Java 17, `float` và `double` tuân theo ngữ nghĩa IEEE 754 nghiêm ngặt, nhưng vẫn có giới hạn hữu hạn: overflow tạo vô cực, underflow đi qua vùng subnormal rồi có thể về signed zero.
