# Vì sao `Float.MIN_VALUE` và `Double.MIN_VALUE` không phải số âm nhỏ nhất?

## 1. Sai lầm phổ biến: nhầm “MIN” với số âm lớn nhất về độ lớn

Khi lập trình Java, người học thường quen với `Integer.MIN_VALUE` là số nguyên âm nhỏ nhất có thể biểu diễn. Từ đó dễ suy luận nhầm rằng `Float.MIN_VALUE` hay `Double.MIN_VALUE` cũng mang ý nghĩa tương tự.

**Thực tế trong Java 17+:**

- `Float.MIN_VALUE` là **số `float` dương nhỏ nhất khác 0**, bằng khoảng `1.4E-45`.
- `Double.MIN_VALUE` là **số `double` dương nhỏ nhất khác 0**, bằng khoảng `4.9E-324`.
- Số `float` hữu hạn âm nhỏ nhất là **`-Float.MAX_VALUE`**, khoảng `-3.4028235E38`.
- Số `double` hữu hạn âm nhỏ nhất là **`-Double.MAX_VALUE`**, khoảng `-1.7976931348623157E308`.
- Nếu tính cả giá trị vô cực đặc biệt, `Float.NEGATIVE_INFINITY` và `Double.NEGATIVE_INFINITY` nhỏ hơn tất cả các số hữu hạn cùng kiểu.

Một bug điển hình:

```java
double max = Double.MIN_VALUE;  // SAI nếu dữ liệu có thể toàn số âm.

for (double value : new double[]{-8.0, -3.0, -11.0}) {
    if (value > max) {
        max = value;
    }
}
System.out.println(max); // 4.9E-324 — không có trong dữ liệu!
```

Vì `Double.MIN_VALUE > 0`, cả ba số âm đều nhỏ hơn giá trị khởi tạo nên vòng lặp không bao giờ cập nhật `max`.

**Mục tiêu của bài:** nắm được chính xác ý nghĩa các hằng số `MIN_VALUE`, `MIN_NORMAL`, `MAX_VALUE`, vô cực và `NaN`; chọn cách khởi tạo min/max đúng; xây dựng cách tổng hợp an toàn trên tập rỗng và các giá trị đặc biệt; tránh dùng `MIN_VALUE` làm ngưỡng sai số.

## 2. Bảng đối chiếu với kiểu số nguyên

| Hằng số | Giá trị xấp xỉ | Ý nghĩa |
| --- | --- | --- |
| `Integer.MIN_VALUE` | `-2147483648` | Số `int` nhỏ nhất |
| `Integer.MAX_VALUE` | `2147483647` | Số `int` lớn nhất |
| `Long.MIN_VALUE` | `-9223372036854775808` | Số `long` nhỏ nhất |
| `Float.MIN_VALUE` | `1.4E-45` | Số `float` **dương** nhỏ nhất khác 0 |
| `Float.MIN_NORMAL` | `1.1754944E-38` | Số `float` dương **normal** nhỏ nhất |
| `Float.MAX_VALUE` | `3.4028235E38` | Số `float` dương hữu hạn lớn nhất |
| `-Float.MAX_VALUE` | `-3.4028235E38` | Số `float` âm hữu hạn nhỏ nhất |
| `Double.MIN_VALUE` | `4.9E-324` | Số `double` **dương** nhỏ nhất khác 0 |
| `Double.MIN_NORMAL` | `2.2250738585072014E-308` | Số `double` dương **normal** nhỏ nhất |
| `Double.MAX_VALUE` | `1.7976931348623157E308` | Số `double` dương hữu hạn lớn nhất |
| `-Double.MAX_VALUE` | `-1.7976931348623157E308` | Số `double` âm hữu hạn nhỏ nhất |
| `Float.NEGATIVE_INFINITY`, `Double.NEGATIVE_INFINITY` | `-Infinity` | Giá trị đặc biệt nhỏ hơn số hữu hạn |
| `Float.POSITIVE_INFINITY`, `Double.POSITIVE_INFINITY` | `Infinity` | Giá trị đặc biệt lớn hơn số hữu hạn |

Giá trị trên dùng định dạng mà Java thường in ra bằng `Float.toString`/`Double.toString`; các hằng số lưu trữ theo nhị phân IEEE 754 nên không nhất thiết có đúng biểu diễn thập phân ngắn như chuỗi in ra.

**Điểm cần nhớ:** đối với kiểu nguyên, `MIN_VALUE` là cận dưới âm của miền giá trị. Đối với `float` và `double`, `MIN_VALUE` lại là **độ lớn dương nhỏ nhất khác 0** của kiểu dấu phẩy động, bao gồm cả vùng subnormal. Cách đặt tên là đặc điểm API đã được chuẩn hóa; không suy diễn ý nghĩa từ cùng tên hằng số của kiểu số nguyên.

## 3. Tại sao số dương nhỏ nhất khác 0 lại nhỏ đến như vậy?

`float` và `double` là kiểu dấu phẩy động nhị phân theo IEEE 754, không lưu số như một đoạn liên tiếp với khoảng cách đều. Biểu diễn có dấu, phần mũ và phần trị, nên độ phân giải phụ thuộc độ lớn số.

Các giá trị hữu hạn thông thường (**normal**) có phần mũ và các bit hữu hiệu theo quy tắc normal. Khi giá trị tiến rất gần 0, Java còn có các giá trị **subnormal** (*denormalized*) để biểu diễn một số độ lớn nhỏ hơn cận normal; chúng có ít chữ số/bit hữu hiệu hơn.

- `Float.MIN_NORMAL` là cận dương nhỏ nhất còn **normal**.
- `Float.MIN_VALUE` nhỏ hơn `Float.MIN_NORMAL` rất nhiều và là số dương **subnormal** nhỏ nhất khác 0.
- `Double.MIN_NORMAL` và `Double.MIN_VALUE` có quan hệ tương tự.

Ví dụ trên Java:

```java
System.out.println(Float.MIN_VALUE);       // 1.4E-45
System.out.println(Float.MIN_NORMAL);      // 1.1754944E-38
System.out.println(Double.MIN_VALUE);      // 4.9E-324
System.out.println(Double.MIN_NORMAL);     // 2.2250738585072014E-308
```

Đoạn này là mã **nhúng** trong một phương thức. `Float.MIN_NORMAL` không phải số âm nhỏ nhất; chữ `NORMAL` chỉ phân biệt số normal với subnormal. `MIN_VALUE` **không phải** số dương nhỏ nhất *theo ý nghĩa số thực toán học* (trên trục số thực không tồn tại số dương nhỏ nhất); nó chỉ là giá trị nhỏ nhất khác 0 biểu diễn được bằng kiểu `float`/`double` trong Java.

### 3.1. Trục giá trị quan trọng

Sắp xếp theo **thứ tự số học**:

```text
-Infinity
   <
-Double.MAX_VALUE
   <
... các số hữu hạn âm ...
   <
-Double.MIN_VALUE
   <
-0.0 / +0.0 (cùng giá trị dưới phép so sánh ==)
   <
Double.MIN_VALUE
   <
... các số hữu hạn dương ...
   <
Double.MAX_VALUE
   <
+Infinity
```

Sơ đồ là một cách mô tả trật tự số học; với `Double.compare`, `-0.0` được xếp trước `+0.0`. `NaN` không nằm trên trục số thực này. Đối với phép `<`, `>`, `==` với `NaN`, hành vi không phải trật tự tuyến tính thông thường (xem mục 6).

`Double.MIN_VALUE` nằm **ngay phía dương của 0** trong các giá trị biểu diễn được, chứ không nằm phía âm sâu nhất.

### 3.2. `Math.nextUp` và `Math.nextDown` làm rõ giới hạn

```java
System.out.println(Math.nextUp(0.0));   // 4.9E-324
System.out.println(Math.nextDown(0.0)); // -4.9E-324
```

`Math.nextUp(0.0)` trả giá trị `double` biểu diễn được kế tiếp lớn hơn 0, chính là `Double.MIN_VALUE`. `Math.nextDown(0.0)` trả giá trị kế tiếp nhỏ hơn 0, tức `-Double.MIN_VALUE`. Giá trị **`-Double.MIN_VALUE` là số âm gần 0 nhất nhưng vẫn khác 0**, không phải số âm nhỏ nhất.

Tương tự, `Math.nextDown(-Double.MAX_VALUE)` chuyển sang `Double.NEGATIVE_INFINITY`: không còn số `double` **hữu hạn** nào nhỏ hơn `-Double.MAX_VALUE`.

## 4. Lỗi khi khởi tạo cực đại bằng `MIN_VALUE`

### 4.1. Bug rõ nhất: toàn bộ dữ liệu âm

```java
double[] temperatures = {-8.0, -3.0, -11.0};
double maximum = Double.MIN_VALUE; // Sai chính sách khởi tạo.

for (double temperature : temperatures) {
    if (temperature > maximum) {
        maximum = temperature;
    }
}
System.out.println(maximum); // 4.9E-324 — sai!
```

Giá trị đúng phải là **`-3.0`**. Nếu code dùng `Float.MIN_VALUE`, hiện tượng tương tự xảy ra cho `float[]` toàn số âm.

### 4.2. Đối xứng: dùng `MIN_VALUE` làm giá trị khởi tạo của cực tiểu cũng sai

```java
double[] positives = {8.0, 3.0, 11.0};
double minimum = Double.MIN_VALUE; // Sai: nhỏ hơn mọi phần tử.

for (double value : positives) {
    if (value < minimum) {
        minimum = value;
    }
}
System.out.println(minimum); // 4.9E-324 — sai, đúng là 3.0.
```

Tên `MIN_VALUE` nghe như “phần tử nhỏ nhất” nhưng **không có nghĩa** là hằng khởi tạo phù hợp cho thuật toán tìm min. Nếu thuật toán cần tìm min/max của dữ liệu, phải bảo đảm kết quả thuộc dữ liệu và giải quyết đúng trường hợp rỗng.

### 4.3. Chỉ thay bằng `-Double.MAX_VALUE` có đủ chưa?

Đối với **dữ liệu được bảo đảm hữu hạn và không rỗng**, khởi tạo:

```java
double maximum = -Double.MAX_VALUE;
```

có thể hợp lệ để tìm cực đại. Tuy nhiên, nếu dữ liệu chứa `Double.NEGATIVE_INFINITY` và không có số hữu hạn nào, `-Double.MAX_VALUE` lớn hơn mọi phần tử: bạn vẫn nhận kết quả sai, vì sentinel không thuộc dữ liệu. Nếu mảng rỗng, sentinel còn bị trả như một cực trị dù không có phần tử nào.

Tương tự:

```java
double minimum = Double.MAX_VALUE;
```

sai nếu mọi phần tử là `Double.POSITIVE_INFINITY`, hoặc mảng rỗng mà kết quả được coi là min thực.

`Double.NEGATIVE_INFINITY` có thể là sentinel khởi tạo max, và `Double.POSITIVE_INFINITY` là sentinel khởi tạo min trong một số thuật toán, nhưng **cần cờ có dữ liệu** để phân biệt tập rỗng với đầu vào thực sự có toàn vô cực. Nếu miền dữ liệu có `NaN`, phải có thêm chính sách xử lý riêng.

Giải pháp thường dễ bảo trì hơn: **lấy giá trị đầu tiên khi dữ liệu tồn tại**, hoặc dùng stream trả `OptionalDouble` (mục 5).

## 5. Chọn cách tìm `min`/`max` không dựa vào sentinel sai

### 5.1. Dùng `DoubleStream.min()` và `max()`

```java
import java.util.OptionalDouble;
import java.util.stream.DoubleStream;

OptionalDouble min = DoubleStream.of(-8.0, -3.0, -11.0).min();
OptionalDouble max = DoubleStream.of(-8.0, -3.0, -11.0).max();

System.out.println(min.orElseThrow()); // -11.0
System.out.println(max.orElseThrow()); // -3.0
```

Đây là mã **nhúng**. Các phương thức `min()`/`max()` là terminal operation và trả `OptionalDouble` vì nguồn **có thể rỗng**. Không dùng lại cùng một stream sau một terminal operation: tạo stream mới từ mảng/list hoặc chọn `summaryStatistics()` nếu cần nhiều chỉ số trong một lượt.

```java
OptionalDouble none = DoubleStream.empty().max();
System.out.println(none.isEmpty()); // true
```

Trường hợp nguồn rỗng được mô tả rõ bằng Optional thay vì giả một con số làm kết quả. Nếu nghiệp vụ yêu cầu ít nhất một giá trị, có thể dùng `orElseThrow(() -> new IllegalArgumentException("Dữ liệu rỗng"))`. Nếu rỗng là hợp lệ, trả Optional cho caller. `orElse(0.0)` chỉ phù hợp **khi nghiệp vụ thực sự định nghĩa giá trị mặc định bằng 0**, vì 0 cũng là một giá trị dữ liệu hợp lệ.

### 5.2. Dùng giá trị đầu tiên và cờ hiện diện

Khi bạn cần một vòng lặp chuyên biệt (ví dụ vừa kiểm tra dữ liệu vừa tìm max), nên dùng cờ `found`:

```java
boolean found = false;
double maximum = 0.0; // Giá trị ban đầu không được sử dụng nếu chưa found.

for (double value : values) {
    if (!found || Double.compare(value, maximum) > 0) {
        maximum = value;
        found = true;
    }
}

OptionalDouble result =
        found ? OptionalDouble.of(maximum) : OptionalDouble.empty();
```

Đây là mã **nhúng** với `double[] values` và `import java.util.OptionalDouble;`. Vì `!found` luôn thắng cho phần tử đầu tiên, `0.0` chỉ là chỗ đặt bộ nhớ, không bị hiểu lầm là một kết quả dữ liệu.

**Nhưng cần lưu ý:** `Double.compare` định nghĩa trật tự cho cả `NaN` (xếp `NaN` lớn hơn mọi giá trị số) và hai số 0 có dấu. Vì vậy đoạn lặp trên không tự động có cùng chính sách `NaN` như `DoubleStream.min/max`. Khi muốn từ chối `NaN`, hãy kiểm tra trước khi so sánh; khi muốn `NaN` lan truyền, triển khai rõ chính sách đó. Đừng thay thế hai cách mà không đối chiếu hợp đồng.

### 5.3. Khi chỉ nhận dữ liệu hữu hạn

Nếu miền đầu vào không được có `NaN` hoặc `±Infinity`, hãy xác thực:

```java
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("Chỉ nhận số hữu hạn");
}
```

Sau kiểm tra, hàm có thể tìm cực trị bằng `Double.compare` hoặc trực tiếp các toán tử `<`/`>`, tùy có cần phân biệt `-0.0` và `+0.0` hay không. Không mặc định loại bỏ giá trị không hữu hạn một cách im lặng nếu chúng báo lỗi upstream (ví dụ chia cho 0 hoặc dữ liệu cảm biến bị hỏng).

## 6. Ba trường hợp đặc biệt của `double`: vô cực, `NaN` và số 0 có dấu

### 6.1. Vô cực và cận hữu hạn

`Double.MAX_VALUE` là số **hữu hạn** dương lớn nhất; nó không phải `Double.POSITIVE_INFINITY`. `-Double.MAX_VALUE` là số hữu hạn âm nhỏ nhất; nó không phải `Double.NEGATIVE_INFINITY`.

```java
System.out.println(Double.NEGATIVE_INFINITY < -Double.MAX_VALUE); // true
System.out.println(Double.POSITIVE_INFINITY > Double.MAX_VALUE);  // true
```

Nếu dữ liệu có thể chứa vô cực, không được trả về `-Double.MAX_VALUE` như max của một nguồn chỉ chứa `-Infinity`. Tương tự, min của nguồn chỉ chứa `+Infinity` phải là `+Infinity` nếu hợp đồng chấp nhận vô cực. `Math.min` và `DoubleStream.min` không tự từ chối vô cực.

### 6.2. `NaN` không phải số thực và không so sánh theo `<`/`>`

`Double.NaN` (Not a Number) là giá trị đặc biệt:

```java
double invalid = Double.NaN;

System.out.println(invalid < 0.0);          // false
System.out.println(invalid > 0.0);          // false
System.out.println(invalid == Double.NaN);  // false
System.out.println(Double.isNaN(invalid));  // true
```

Với các toán tử so sánh primitive, ngay cả `NaN == NaN` cũng là `false`. Một vòng lặp dùng `if (x > current)` có thể **bỏ qua** `NaN`; điều này nguy hiểm nếu `NaN` biểu thị phép đo không hợp lệ và phải gây lỗi.

Theo Java 17, `DoubleStream.min/max` **trả `NaN` nếu trong nguồn có bất kỳ giá trị `NaN` nào**, kể cả khi còn giá trị hữu hạn. `Math.min`/`Math.max` trên `double` cũng trả `NaN` nếu một toán hạng là `NaN`.

```java
double min = java.util.stream.DoubleStream
        .of(5.0, Double.NaN, -2.0)
        .min()
        .orElseThrow();

System.out.println(min); // NaN
```

`OptionalDouble` ở đây **có giá trị**, chỉ là giá trị đặc biệt `NaN`; `isPresent()` không có nghĩa là “dữ liệu hợp lệ”.

Nếu nghiệp vụ yêu cầu bỏ qua `NaN`, thực hiện `.filter(v -> !Double.isNaN(v))` và quyết định trường hợp sau filter rỗng; nếu nghiệp vụ yêu cầu báo lỗi, ném ngoại lệ ngay khi phát hiện. Không tự chọn một chính sách chỉ vì nó giúp vòng lặp chạy nhanh hơn.

### 6.3. `-0.0` và `+0.0` có biểu diễn khác nhau

```java
System.out.println(-0.0 == +0.0);         // true
System.out.println(Double.compare(-0.0, +0.0) < 0); // true

System.out.println(Math.min(-0.0, +0.0)); // -0.0
System.out.println(Math.max(-0.0, +0.0)); // 0.0
```

Hai số 0 cùng bằng nhau theo `==`, nhưng `Double.compare` sắp xếp `-0.0` nhỏ hơn `+0.0`. `Math.min`/`Math.max` và `DoubleStream.min/max` có quy tắc cho số 0 có dấu. Nếu muốn thay các API này bằng vòng lặp, cần kiểm thử trường hợp `-0.0`/`+0.0` để không vô tình đổi nghĩa khi thứ tự phần tử thay đổi.

Các vấn đề trên không xảy ra với `int` theo cách tương tự: `int` không có `NaN`, vô cực hay số 0 mang dấu âm tách biệt.

## 7. `Float.MIN_VALUE` và `Double.MIN_VALUE` cũng không phải epsilon để so sánh gần bằng

Một nhầm lẫn liên quan là dùng:

```java
boolean approximatelyEqual =
        Math.abs(a - b) < Double.MIN_VALUE; // Gần như luôn quá nghiêm ngặt.
```

Đây là mã minh họa giả định hai biến `double a`, `double b` đã tồn tại. `Double.MIN_VALUE` mô tả **khoảng cách từ 0 đến số dương nhỏ nhất khác 0**, không phải sai số làm tròn tuyệt đối phù hợp cho mọi phép toán và mọi độ lớn.

Tại quanh `1.0`, khoảng cách tới số `double` biểu diễn được kế tiếp phía trên là:

```java
System.out.println(Math.ulp(1.0)); // 2.220446049250313E-16
System.out.println(Math.ulp(1.0f)); // 1.1920929E-7
```

Nó lớn hơn `Double.MIN_VALUE` và `Float.MIN_VALUE` rất nhiều. `Math.ulp(x)` mô tả độ lớn của một đơn vị ở chữ số cuối gần `x`, khác với một “epsilon nghiệp vụ” phổ quát.

### 7.1. Chính sách so sánh gần bằng phải dựa trên bài toán

Một cách **minh họa** cho số hữu hạn trong trường hợp ứng dụng đã xác định ngưỡng:

```java
static boolean approximatelyEqualFinite(
        double a, double b, double absTolerance, double relTolerance) {

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        throw new IllegalArgumentException("Chỉ so sánh số hữu hạn");
    }
    if (!Double.isFinite(absTolerance) || absTolerance < 0.0
            || !Double.isFinite(relTolerance) || relTolerance < 0.0) {
        throw new IllegalArgumentException("Tolerance không hợp lệ");
    }
    if (a == b) { // Gồm +0.0 == -0.0 theo chính sách ví dụ.
        return true;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= Math.max(absTolerance, relTolerance * scale);
}
```

Đây là phương thức **nhúng** áp dụng cho một miền hữu hạn đã định. Với giá trị cực lớn, phép trừ hoặc nhân ngưỡng có thể tràn thành vô cực, nên một bộ so sánh đòi ràng buộc số học chặt phải xử lý miền và phép tính trung gian kỹ hơn. Công thức chỉ là điểm khởi đầu khi nghiệp vụ cho phép sai số tuyệt đối và tương đối đã được xác định, **không phải phép chữa tổng quát** cho mọi kiểm thử số học.

Nếu cần so sánh chính xác tiền tệ hoặc số nguyên, dùng kiểu biểu diễn thích hợp (`BigDecimal`/integer minor units) và quy tắc so sánh tương ứng; không dùng epsilon để che việc đổi kiểu số gây mất dữ liệu.

## 8. Chương trình Java 17+ hoàn chỉnh và kết quả chạy

Lưu dưới tên **`FloatingMinimumDemo.java`**:

```java
import java.util.OptionalDouble;

public class FloatingMinimumDemo {

    // Hợp đồng: chấp nhận cả vô cực, nhưng từ chối NaN;
    // trả Optional.empty() khi không có phần tử.
    static OptionalDouble maximumRejectNaN(double[] values) {
        boolean found = false;
        double maximum = 0.0;

        for (double value : values) {
            if (Double.isNaN(value)) {
                throw new IllegalArgumentException("NaN is not allowed");
            }

            if (!found || Double.compare(value, maximum) > 0) {
                maximum = value;
                found = true;
            }
        }

        return found
                ? OptionalDouble.of(maximum)
                : OptionalDouble.empty();
    }

    public static void main(String[] args) {
        System.out.println("Float.MIN_VALUE = " + Float.MIN_VALUE);
        System.out.println("-Float.MAX_VALUE = " + (-Float.MAX_VALUE));
        System.out.println("Double.MIN_VALUE = " + Double.MIN_VALUE);
        System.out.println("-Double.MAX_VALUE = " + (-Double.MAX_VALUE));

        double[] values = {-8.0, -3.0, -11.0};
        double wrongMax = Double.MIN_VALUE;

        for (double value : values) {
            if (value > wrongMax) {
                wrongMax = value;
            }
        }

        System.out.println("wrong max = " + wrongMax);
        System.out.println("correct max = "
                + maximumRejectNaN(values).orElseThrow());
        System.out.println("empty = "
                + maximumRejectNaN(new double[0]).isEmpty());
        System.out.println("only -Infinity = "
                + maximumRejectNaN(
                        new double[]{Double.NEGATIVE_INFINITY})
                        .orElseThrow());
        System.out.println("signed zero max = "
                + maximumRejectNaN(new double[]{-0.0, 0.0})
                        .orElseThrow());
        System.out.println("nextUp zero = " + Math.nextUp(0.0));

        try {
            maximumRejectNaN(new double[]{1.0, Double.NaN});
        } catch (IllegalArgumentException e) {
            System.out.println("NaN policy = rejected");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FloatingMinimumDemo.java
java FloatingMinimumDemo
```

Stdout chuẩn trên Java 17+:

```text
Float.MIN_VALUE = 1.4E-45
-Float.MAX_VALUE = -3.4028235E38
Double.MIN_VALUE = 4.9E-324
-Double.MAX_VALUE = -1.7976931348623157E308
wrong max = 4.9E-324
correct max = -3.0
empty = true
only -Infinity = -Infinity
signed zero max = 0.0
nextUp zero = 4.9E-324
NaN policy = rejected
```

### Diễn giải kết quả

1. Bốn dòng đầu phân biệt rõ **dương nhỏ nhất khác 0** với **âm hữu hạn nhỏ nhất** cho `float` và `double`.
2. `wrong max` bộc lộ bug phổ biến: sentinel `Double.MIN_VALUE` lớn hơn mọi phần tử âm, nên kết quả sai.
3. `maximumRejectNaN` chọn phần tử đầu tiên trước khi so sánh những phần tử còn lại, trả `-3.0` cho dữ liệu mẫu.
4. Mảng rỗng trả `OptionalDouble.empty()` thay vì một sentinel giả.
5. Dữ liệu chỉ có `-Infinity` vẫn được trả đúng vì hợp đồng cho phép vô cực.
6. `Double.compare` giữ thứ tự chuẩn giữa `-0.0` và `+0.0`, nên `max` chọn `+0.0`.
7. `Math.nextUp(0.0)` chứng minh `Double.MIN_VALUE` nằm ngay phía dương của 0.
8. `NaN` bị từ chối theo chính sách của **hàm minh họa**. Chính sách này khác `DoubleStream.max()` vốn trả `NaN` khi nguồn chứa NaN; cần chọn rõ một trong các chính sách khi thiết kế API.

Không phải lúc nào tự viết vòng lặp cũng tốt hơn `DoubleStream.max()`: ví dụ ở đây nhằm minh họa điều kiện đầu vào và quy tắc chọn kết quả. Đối với nghiệp vụ thông thường, ưu tiên API chuẩn nếu hợp đồng `NaN`/infinity và kết quả rỗng phù hợp.

## 9. Chọn cách khởi tạo phù hợp theo từng hợp đồng

| Yêu cầu dữ liệu và kết quả | Cách triển khai gợi ý | Lưu ý |
| --- | --- | --- |
| Tìm `max` của mảng không rỗng, **chỉ số hữu hạn** | Bắt đầu bằng phần tử đầu, hoặc `-Double.MAX_VALUE` khi miền đã chứng minh | Chặn mảng rỗng; xác thực finite |
| Tìm `min` của mảng không rỗng, **chỉ số hữu hạn** | Bắt đầu bằng phần tử đầu, hoặc `Double.MAX_VALUE` khi miền đã chứng minh | Không dùng `Double.MIN_VALUE` |
| Có thể rỗng và có thể chứa ±infinity | `DoubleStream.min/max()` trả `OptionalDouble` | Dữ liệu NaN được lan truyền theo API |
| Có thể rỗng; `NaN` là lỗi; ±infinity hợp lệ | Cờ `found` + `Double.compare` + reject NaN | Như chương trình ví dụ |
| Nguồn chỉ chấp nhận số hữu hạn | Xác thực `Double.isFinite` rồi tính | Không âm thầm loại bỏ phần tử lỗi |
| Cần giá trị hữu hạn nhỏ nhất theo miền kiểu | `-Double.MAX_VALUE` / `-Float.MAX_VALUE` | Không phải kết quả `min` của một mảng tùy ý |
| Cần giá trị đặc biệt thấp hơn mọi số hữu hạn | `Double.NEGATIVE_INFINITY` / `Float.NEGATIVE_INFINITY` | Phân biệt với giá trị thực trong nguồn |
| Cần số dương biểu diễn được kế tiếp 0 | `Double.MIN_VALUE` / `Float.MIN_VALUE` | Đây mới là trường hợp dùng đúng `MIN_VALUE` |

### Khi nào sentinel vẫn hợp lý?

Sentinel có thể là một **giá trị kỹ thuật** trong thuật toán khi bạn biết chính xác miền đầu vào và có cách đánh dấu tập rỗng. Ví dụ phép reduction cần giá trị identity `-Infinity` cho cực đại có thể hợp lý trên số `double` nếu hợp đồng xử lý `NaN` được công bố. Nhưng identity không phải “phần tử lớn nhất của một dãy rỗng”, và không được nhầm trạng thái rỗng với dữ liệu thực.

Nếu API trả dữ liệu cho tầng gọi, `OptionalDouble` thường truyền đạt trạng thái “không có cực trị” rõ ràng hơn việc phát ra `-Infinity` không có ngữ cảnh.

## 10. Những lỗi đi kèm cần nhận diện

**Lỗi 1: `Float.MIN_VALUE` là giới hạn âm.** Sai vì hằng số dương. Số âm hữu hạn thấp nhất là `-Float.MAX_VALUE`.

**Lỗi 2: `-Float.MIN_VALUE` là số âm thấp nhất.** Sai vì đây là số âm khác 0 gần 0 nhất; nó có độ lớn rất nhỏ. Không nhầm **âm nhỏ nhất theo thứ tự số học** với **số âm có độ lớn tuyệt đối nhỏ nhất**.

**Lỗi 3: `Double.MIN_NORMAL` là số dương biểu diễn được nhỏ nhất.** Sai: còn các số subnormal dương nhỏ hơn, xuống đến `Double.MIN_VALUE`.

**Lỗi 4: `Double.MAX_VALUE` có nghĩa là vô cực.** Sai: `Double.MAX_VALUE` hữu hạn. Phép toán vượt miền `double` có thể cho `Infinity`, nhưng hằng này không phải vô cực.

**Lỗi 5: Trả sentinel ngay khi dữ liệu rỗng.** Sai khi hợp đồng yêu cầu “không có dữ liệu”; phải biểu diễn vắng mặt hoặc ném lỗi.

**Lỗi 6: Dùng `Double.MIN_VALUE` cho ngưỡng kiểm thử xấp xỉ.** Quá nhỏ so với khoảng cách biểu diễn ở hầu hết các miền; ngưỡng phải dựa trên sai số cho phép của bài toán.

**Lỗi 7: Dùng `Math.abs(Double.MIN_VALUE)` để nhận số âm.** `Math.abs` giữ giá trị không âm, vì thế không tạo cận âm. Muốn đảo dấu cần toán tử `-`, nhưng `-Double.MIN_VALUE` vẫn gần 0 chứ không phải thấp nhất.

**Lỗi 8: So sánh qua `Double.compare` rồi bỏ quên `NaN`.** `Double.compare` cung cấp một thứ tự xác định, nhưng nó coi NaN lớn hơn mọi giá trị số; đó có thể không phải quy tắc dữ liệu cảm biến/nghiệp vụ.

**Lỗi 9: Bỏ qua `-0.0` khi thay `Math.min/max` bằng `if (a < b)` hoặc `if (a > b)`.** Các toán tử không phân biệt `-0.0` với `+0.0`; đầu ra có thể đổi dấu số 0 theo thứ tự dữ liệu.

**Lỗi 10: Cắt số `double` sang `float` khi tạo cận.** `-Double.MAX_VALUE` không nằm trong phạm vi hữu hạn của `float`; ép kiểu sang `float` sẽ tạo `-Infinity`, khác với `-Float.MAX_VALUE`.

## 11. Kiểm thử đầu vào biên để tránh tái xuất hiện bug

Khi viết hoặc review hàm tìm min/max, nên kiểm tra tối thiểu:

1. **Toàn số âm:** `{-8.0, -3.0, -11.0}` phải cho max `-3.0`, min `-11.0`.
2. **Toàn số dương:** `{8.0, 3.0, 11.0}` phải cho min `3.0`, max `11.0`.
3. **Chỉ số 0:** `{0.0}` phải trả 0, không trả `Double.MIN_VALUE`.
4. **Mảng rỗng:** trả Optional rỗng hoặc lỗi đã định, không trả sentinel tùy ý.
5. **Subnormal:** `{Double.MIN_VALUE, 0.0}` phải được xử lý theo chính sách dấu/zero phù hợp.
6. **Dữ liệu vô cực:** `{-Infinity}` và `{+Infinity}` để bảo đảm không trả nhầm cận hữu hạn.
7. **NaN:** `{1.0, NaN}` phải lan truyền NaN, bị từ chối hoặc bị lọc đúng theo hợp đồng, không do tình cờ của toán tử so sánh.
8. **Số 0 có dấu:** `{-0.0, +0.0}` kiểm tra lựa chọn và chuỗi/bit biểu diễn nếu dấu quan trọng.
9. **Cận cực đại hữu hạn:** `{-Double.MAX_VALUE, Double.MAX_VALUE}` và các trường hợp overflow khi tính giá trị khác từ cận.
10. **Kiểu float riêng:** lặp lại các case với `Float.MIN_VALUE`, `Float.MAX_VALUE`, ±infinity; không giả định mọi phép đổi kiểu giữ nguyên miền.

Kiểm thử nên đối chiếu giá trị kỳ vọng theo **hợp đồng**. Nếu cần phân biệt hai số 0 có dấu, `==` không đủ; kiểm tra `Double.compare` hoặc raw bits. Nếu kiểm tra giá trị NaN, dùng `Double.isNaN`, không viết `actual == Double.NaN`.

## 12. Bài tập tự đánh giá

1. `Float.MIN_VALUE > 0.0f` đúng hay sai? Vậy `Float.MIN_VALUE` có thể là số âm nhỏ nhất không?
2. Phân biệt `Double.MIN_VALUE`, `Double.MIN_NORMAL`, `-Double.MAX_VALUE` và `Double.NEGATIVE_INFINITY`. Giá trị nào là cận thấp nhất **hữu hạn**?
3. Với dữ liệu `{-10.0, -20.0, -5.0}`, đoạn vòng lặp dùng `double max = Double.MIN_VALUE` trả giá trị gì? Vì sao?
4. Nếu phép toán chấp nhận `-Infinity` nhưng không chấp nhận NaN, tại sao `double max = -Double.MAX_VALUE` là sentinel không an toàn cho mọi nguồn?
5. Với một nguồn rỗng, tại sao `DoubleStream.empty().max()` trả `OptionalDouble.empty()` và không trả `-Infinity`?
6. `Math.nextUp(0.0)` nhận giá trị gì? `Math.nextDown(0.0)` tương ứng với số âm nào?
7. Vì sao một hàm so sánh gần bằng dùng `Double.MIN_VALUE` có thể bác bỏ cả hai giá trị trông gần như bằng nhau quanh `1.0`?
8. Viết phương thức `minimumRejectNaN(double[])` tương tự hàm `maximumRejectNaN` trong bài, dùng `Double.compare` và `OptionalDouble`. Thử `+Infinity`, `-0.0`, nguồn rỗng và NaN.
9. Giải thích vì sao `DoubleStream.of(2.0, Double.NaN).max().isPresent()` vẫn trả `true` mặc dù max thực tế là `NaN`.

**Đáp án tóm tắt:** (1) Đúng; hằng này dương. (2) `Double.MIN_VALUE` là số dương subnormal nhỏ nhất; `MIN_NORMAL` là số dương normal nhỏ nhất; `-MAX_VALUE` là cận hữu hạn âm thấp nhất; `NEGATIVE_INFINITY` nhỏ hơn các số hữu hạn nhưng không hữu hạn. (3) Trả `4.9E-324` sai vì mọi phần tử đều âm. (4) Với nguồn chỉ có `-Infinity`, sentinel hữu hạn lớn hơn giá trị thật. (5) Cực trị của nguồn rỗng không tồn tại. (6) `+Double.MIN_VALUE`, `-Double.MIN_VALUE`. (7) Khoảng cách representable quanh 1 lớn hơn `Double.MIN_VALUE` rất nhiều. (8) Dùng cờ `found`, kiểm tra NaN rồi đổi phép `> 0` thành `< 0` trong `Double.compare`. (9) Optional có phần tử; NaN là giá trị `double` đặc biệt, khác trạng thái thiếu dữ liệu.

## 13. Ghi nhớ nhanh

`Float.MIN_VALUE` và `Double.MIN_VALUE` đều **dương**, rất nhỏ và khác 0; chúng không phải cận âm của kiểu. Khi cần **số hữu hạn thấp nhất** của `float`/`double`, dùng `-Float.MAX_VALUE` hoặc `-Double.MAX_VALUE`. Khi cần giá trị đặc biệt **nhỏ hơn mọi số hữu hạn**, dùng `NEGATIVE_INFINITY` với hiểu biết về miền giá trị.

Khi tìm cực trị của dữ liệu thực, cách chắc chắn nhất thường là `DoubleStream.min/max()` trả `OptionalDouble` hoặc vòng lặp khởi tạo bằng **phần tử đầu tiên**, kết hợp chính sách xử lý rỗng, vô cực, NaN và số 0 có dấu. Không dùng một hằng số tên `MIN_VALUE` như sentinel chỉ vì chữ “MIN”.

Tài liệu chuẩn Java SE 17:
- [`Float`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html), [`Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): ý nghĩa chính xác của `MIN_VALUE`, `MIN_NORMAL`, `MAX_VALUE`, ±infinity và `NaN`.
- [`Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `min`, `max`, `nextUp`, `nextDown`, `ulp`.
- [`DoubleStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html), [`OptionalDouble`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalDouble.html): cực trị an toàn trên nguồn có thể rỗng.
