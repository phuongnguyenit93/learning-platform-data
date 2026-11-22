# NaN, vô cực và số không có dấu trong DoubleStream

Khi dùng Java Stream API để tổng hợp dữ liệu số, không phải mọi giá trị kiểu `double` đều là một số thực hữu hạn. Ngoài các giá trị thông thường, Java còn có **`NaN` (Not a Number)**, **vô cực dương/âm** (`+Infinity`, `-Infinity`) và **hai cách biểu diễn số không** (`+0.0`, `-0.0`). Những giá trị này có thể thay đổi kết quả của `DoubleStream.sum()`, `average()`, `min()`, `max()`, `sorted()`, `distinct()` và các phép so sánh.

Bài học thuộc chương **Độ chính xác khi tổng hợp số** của module **JAVA_STREAM_API**. Sau khi đã biết xây pipeline lười bằng `filter`, `map`, `reduce` và `collect`, người học cần xem xét thêm **hợp đồng số học** của dữ liệu đầu vào. Điều này đặc biệt quan trọng trong thống kê, xử lý dữ liệu cảm biến, grouping với Collector, chạy Stream song song và tối ưu hiệu năng: kết quả có thể đúng theo quy tắc của `double` nhưng không đúng với kỳ vọng nghiệp vụ.

> **Làm rõ tên bài:** Cụm “số không có dấu” dễ gây nhầm lẫn. Kiểu `double` của Java **không loại bỏ bit dấu khi giá trị là zero**: nó phân biệt biểu diễn `+0.0` và `-0.0`. Giá trị viết là `0.0` chính là zero có dấu dương. Bài này giải thích cả hai biểu diễn và hệ quả của chúng trong `DoubleStream`.

## 1. Những giá trị đặc biệt trong kiểu double

Java `double` sử dụng định dạng dấu phẩy động nhị phân 64 bit theo IEEE 754. Một số phép toán có thể tạo ra các giá trị đặc biệt ngay cả khi không có lỗi biên dịch hay ngoại lệ.

| Giá trị | Cách viết trong Java | Ví dụ sinh ra giá trị | Ý nghĩa |
| --- | --- | --- | --- |
| NaN | `Double.NaN` | `0.0 / 0.0`; `Math.sqrt(-1.0)` | Kết quả số học không xác định trong miền số thực |
| Vô cực dương | `Double.POSITIVE_INFINITY` | `1.0 / 0.0`; phép toán vượt miền hữu hạn | Giá trị vô cực dương |
| Vô cực âm | `Double.NEGATIVE_INFINITY` | `-1.0 / 0.0` | Giá trị vô cực âm |
| Zero dương | `+0.0` hoặc `0.0` | `1.0 - 1.0` | Zero có bit dấu dương |
| Zero âm | `-0.0` | `-1.0 / Double.POSITIVE_INFINITY` | Zero có bit dấu âm |
| Số hữu hạn | `12.5`, `-2.0` | Các phép tính thông thường | Giá trị có độ lớn hữu hạn |

Ví dụ:

```java
System.out.println(0.0 / 0.0);  // NaN
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(-1.0 / 0.0); // -Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

Khác với phép chia số nguyên cho zero, các phép chia `double` trên **không ném `ArithmeticException`**. Chúng tuân theo ngữ nghĩa dấu phẩy động. Do đó, pipeline tính toán có thể tiếp tục chạy với `NaN` hoặc `Infinity` mà người viết chương trình không nhận ra.

Những phương thức kiểm tra chuẩn:

```java
Double.isNaN(value);       // Chỉ nhận diện NaN.
Double.isInfinite(value);  // Nhận diện +Infinity hoặc -Infinity.
Double.isFinite(value);    // Chỉ true với các giá trị hữu hạn, gồm cả +/-0.0.
```

`Double.isFinite` có từ Java 8; nó rất phù hợp khi cần định nghĩa chính sách “chỉ thống kê các giá trị hữu hạn”.

## 2. NaN không tuân theo cách so sánh số thông thường

`NaN` có quy tắc so sánh khác số thực:

```java
double missing = Double.NaN;

System.out.println(missing == missing); // false
System.out.println(missing < 10.0);     // false
System.out.println(missing > 10.0);     // false
System.out.println(missing <= 10.0);    // false
System.out.println(missing >= 10.0);    // false
System.out.println(Double.isNaN(missing)); // true
```

Không nên dùng `value == Double.NaN` để phát hiện NaN: phép so sánh đó luôn trả về `false`. Hãy dùng `Double.isNaN(value)`.

Với các giá trị hữu hạn và vô cực, so sánh nguyên thủy như `-5.0 < Double.POSITIVE_INFINITY` hoạt động theo trật tự số học thông thường. Riêng `NaN` không nhỏ hơn, không lớn hơn và cũng không bằng chính nó theo toán tử `==`.

Tuy nhiên, `Double.compare(a, b)` được định nghĩa để cung cấp **thứ tự toàn phần** cho việc sắp xếp:

- `-Infinity` đứng trước mọi giá trị hữu hạn.
- `-0.0` đứng trước `+0.0`.
- `+Infinity` đứng sau mọi giá trị hữu hạn.
- `NaN` được xem là lớn hơn `+Infinity`; các NaN được xem là bằng nhau theo phép so sánh này.

Đó cũng là trật tự mà `DoubleStream.sorted()` sử dụng, khác với việc tự viết comparator dùng `<` hoặc `>` mà không xử lý NaN.

## 3. Tác động của NaN và vô cực lên các phép tổng hợp

Xét các terminal operation phổ biến của `DoubleStream`:

| Phép toán | Khi có NaN | Khi có vô cực | Lưu ý thêm |
| --- | --- | --- | --- |
| `sum()` | Kết quả là NaN | Một phía vô cực có thể cho vô cực cùng dấu; cộng cả `+Infinity` và `-Infinity` cho NaN | Thứ tự cộng và sai số số học có thể ảnh hưởng kết quả |
| `average()` | Kết quả hiện diện có thể là NaN | Trung bình có thể là vô cực hoặc NaN tùy dữ liệu | Trả về `OptionalDouble`; Stream rỗng cho `OptionalDouble.empty()` |
| `min()` | NaN được lan truyền vào kết quả | `-Infinity` nhỏ hơn các giá trị số khác | `-0.0` nhỏ hơn `+0.0` |
| `max()` | NaN được lan truyền vào kết quả | `+Infinity` lớn hơn các giá trị số khác | `+0.0` lớn hơn `-0.0` |
| `count()` | Vẫn đếm phần tử NaN | Vẫn đếm phần tử vô cực | Chỉ đếm số phần tử, không đo độ hợp lệ |
| `summaryStatistics()` | Tổng, trung bình, min/max có thể trở thành NaN | Tương tự các terminal tương ứng | `getCount()` vẫn phản ánh số phần tử đã thu thập |

Trong bảng, “NaN được lan truyền” nghĩa là **chỉ cần một NaN trong dữ liệu đầu vào** thì `DoubleStream.min()` và `max()` trả về `OptionalDouble` **có giá trị NaN**, chứ không chọn một giá trị hữu hạn để bỏ qua NaN.

### Ví dụ: cùng một nguồn, các kết quả khác nhau

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

public class SpecialValuesDemo {
    public static void main(String[] args) {
        double[] values = {2.0, Double.NaN, 5.0};

        System.out.println(Arrays.stream(values).count()); // 3
        System.out.println(Arrays.stream(values).sum());   // NaN
        System.out.println(Arrays.stream(values).average().getAsDouble()); // NaN
        System.out.println(Arrays.stream(values).min().getAsDouble()); // NaN
        System.out.println(Arrays.stream(values).max().getAsDouble()); // NaN

        DoubleSummaryStatistics stats = Arrays.stream(values).summaryStatistics();
        System.out.println(stats.getCount()); // 3
        System.out.println(stats.getSum());   // NaN

        System.out.println(DoubleStream.of(
            3.0, Double.POSITIVE_INFINITY).sum()); // Infinity
        System.out.println(DoubleStream.of(
            Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY).sum()); // NaN
    }
}
```

Ở đây, `count() == 3` **không có nghĩa** đã có ba quan sát hợp lệ cho tính toán. Một giá trị là NaN nhưng vẫn là một phần tử trong Stream. Khi phân tích dữ liệu thực, phải chọn cách xử lý giá trị không hợp lệ một cách rõ ràng.

### OptionalDouble.empty khác OptionalDouble chứa NaN

```java
OptionalDouble noData = DoubleStream.empty().average();
OptionalDouble invalidAverage = DoubleStream.of(Double.NaN).average();

System.out.println(noData.isPresent());         // false
System.out.println(invalidAverage.isPresent());  // true
System.out.println(Double.isNaN(invalidAverage.getAsDouble())); // true
```

Hai trường hợp có ý nghĩa khác nhau: **không có dữ liệu** và **có dữ liệu nhưng tính toán cho ra NaN**. `orElse(...)` chỉ thay thế giá trị **khi OptionalDouble rỗng**; nó không thay thế NaN. Gọi `getAsDouble()` trên `OptionalDouble.empty()` ném `NoSuchElementException`.

## 4. Hai biểu diễn zero: +0.0 và -0.0

Về so sánh số học thông thường, `+0.0` và `-0.0` bằng nhau:

```java
System.out.println(+0.0 == -0.0); // true
System.out.println(+0.0 < -0.0);  // false
System.out.println(-0.0 < +0.0);  // false
```

Nhưng bit dấu khác nhau và có thể tạo kết quả khác:

```java
System.out.println(1.0 / +0.0); // Infinity
System.out.println(1.0 / -0.0); // -Infinity

System.out.println(
    Double.doubleToRawLongBits(+0.0) ==
    Double.doubleToRawLongBits(-0.0)
); // false

System.out.println(Double.compare(-0.0, +0.0) < 0); // true
System.out.println(
    Double.valueOf(-0.0).equals(Double.valueOf(+0.0))
); // false
```

`Double.compare` và `Double.equals` có quy tắc phân biệt hai zero có dấu, mặc dù toán tử `==` trên kiểu nguyên thủy coi chúng bằng nhau.

### min và max của DoubleStream phân biệt dấu zero

```java
double minZero = DoubleStream.of(+0.0, -0.0)
    .min().orElseThrow(IllegalStateException::new);
double maxZero = DoubleStream.of(+0.0, -0.0)
    .max().orElseThrow(IllegalStateException::new);

System.out.println(minZero); // -0.0
System.out.println(maxZero); // 0.0
```

Ngữ nghĩa của `min`/`max` trên `double` tương thích với `Math.min`/`Math.max`: zero âm được xem là nhỏ hơn zero dương, và NaN làm kết quả trở thành NaN.

Vì thế, việc thay thế tùy tiện `DoubleStream.min()` bằng một phép `reduce` tự viết dựa trên `a < b ? a : b` có thể khiến kết quả xử lý NaN và signed zero **không giống** phép toán chuẩn.

## 5. sorted và distinct: có thứ tự, có tính duy nhất theo quy tắc double

Hai phép toán trung gian này không chỉ nhìn vào toán tử `==`.

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;

double[] sorted = DoubleStream.of(
    Double.NaN,
    +0.0,
    Double.POSITIVE_INFINITY,
    -0.0,
    Double.NEGATIVE_INFINITY
).sorted().toArray();

System.out.println(Arrays.toString(sorted));
// [-Infinity, -0.0, 0.0, Infinity, NaN]

double[] unique = DoubleStream.of(
    -0.0, +0.0, Double.NaN, Double.NaN
).distinct().toArray();

System.out.println(Arrays.toString(unique));
// [-0.0, 0.0, NaN]
```

Điểm cần nhớ:

1. `sorted()` dùng thứ tự tương thích với `Double.compare`. Vì vậy, NaN có vị trí xác định trong thứ tự sắp xếp thay vì khiến phép sắp xếp không thể diễn giải.
2. `distinct()` coi `-0.0` và `+0.0` là **hai giá trị phân biệt**, vì vậy giữ cả hai.
3. `distinct()` coi các giá trị NaN là tương đương để loại trùng, dù biểu thức nguyên thủy `Double.NaN == Double.NaN` là `false`.
4. Khi Stream có encounter order, `distinct()` giữ phần tử xuất hiện đầu tiên trong mỗi nhóm tương đương.

Nếu nghiệp vụ coi mọi zero là một giá trị giống nhau, hãy **chuẩn hóa trước khi gọi `distinct()`**:

```java
double[] normalizedZeros = DoubleStream.of(-0.0, +0.0, 2.0)
    .map(x -> x == 0.0 ? 0.0 : x)
    .distinct()
    .toArray();

System.out.println(Arrays.toString(normalizedZeros)); // [0.0, 2.0]
```

Quyết định chuẩn hóa nên dựa trên yêu cầu nghiệp vụ. Trong một số phép đo và bài toán số học, dấu của zero mang thông tin và cần được giữ lại.

## 6. Sum và average vẫn chịu sai số dấu phẩy động

Ngay cả khi không có NaN hay Infinity, phép cộng `double` có thể làm tròn. Chẳng hạn `0.1` và `0.2` không được biểu diễn chính xác bằng phân số nhị phân hữu hạn:

```java
double ordinary = 0.1 + 0.2;
System.out.println(ordinary == 0.3); // false
```

`DoubleStream.sum()` sử dụng cách tính nhằm cải thiện độ chính xác so với một số cách cộng đơn giản, nhưng **không biến `double` thành kiểu thập phân chính xác tuyệt đối**. Không giả định rằng cộng trên Stream hay chia lấy trung bình sẽ giữ chính xác mọi chữ số thập phân.

Thứ tự cộng cũng quan trọng vì phép cộng dấu phẩy động **không kết hợp tuyệt đối**:

\[
(a+b)+c \quad \text{có thể khác} \quad a+(b+c)
\]

Khi các số có độ lớn rất khác nhau, phần đóng góp nhỏ có thể bị mất vì làm tròn. Các trường hợp rất lớn còn có thể tạo Infinity trong quá trình tính và khiến kết quả sau đó thành NaN khi các vô cực trái dấu gặp nhau.

### Khi cần tiền tệ hoặc tổng thập phân chính xác

Dữ liệu tiền có quy tắc số chữ số thập phân cố định thường phù hợp với `BigDecimal` hoặc số nguyên biểu diễn đơn vị nhỏ nhất hơn là dùng `double`:

```java
import java.math.BigDecimal;
import java.util.stream.Stream;

BigDecimal total = Stream.of("0.10", "0.20", "1.35")
    .map(BigDecimal::new)
    .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 1.65
```

`new BigDecimal(String)` giữ chính xác số thập phân đã cung cấp. Tránh `new BigDecimal(0.1)` nếu ý định là giá trị thập phân chính xác `0.1`: constructor nhận `double` sẽ phản ánh giá trị nhị phân được biểu diễn thực sự.

Nếu dùng `mapToLong` để chuyển thành số đơn vị nhỏ nhất, cần kiểm soát quy tắc làm tròn, phạm vi giá trị và nguy cơ tràn `long`. Primitive Stream tiện cho hiệu năng, nhưng không tự giải quyết mọi yêu cầu về độ chính xác.

## 7. Chọn chính sách xử lý NaN và Infinity trước khi tổng hợp

Không có một lựa chọn đúng cho mọi nguồn dữ liệu. Cần xác định NaN hoặc vô cực có phải lỗi dữ liệu, thông tin cần giữ hay giá trị có ý nghĩa riêng.

| Chính sách | Cách tiếp cận | Khi phù hợp |
| --- | --- | --- |
| Giữ nguyên | Để NaN/Infinity đi vào terminal | Cần biết chính xác kết quả theo IEEE 754 hoặc muốn phát hiện kết quả bất thường |
| Chỉ lấy số hữu hạn | `filter(Double::isFinite)` | Thống kê riêng các phép đo hợp lệ, theo hợp đồng nghiệp vụ |
| Loại riêng NaN | `filter(x -> !Double.isNaN(x))` | Vẫn muốn cho phép `+Infinity`/`-Infinity` |
| Báo lỗi | Kiểm tra từng phần tử, từ chối dữ liệu không hợp lệ | Hợp đồng nghiệp vụ không cho phép giá trị đặc biệt |
| Chuẩn hóa zero | `map(x -> x == 0.0 ? 0.0 : x)` | Không cần phân biệt `-0.0` và `+0.0` |

**Không âm thầm loại bỏ NaN và vô cực** nếu chúng đang biểu thị lỗi cảm biến, thiếu dữ liệu hay một sự kiện đặc biệt cần báo cáo. Một chương trình đáng tin cậy thường ghi nhận số lượng giá trị không hợp lệ trước khi loại chúng khỏi phép tổng hợp.

### Ví dụ thực tế: thống kê phép đo cảm biến

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;

public class SensorSummaryDemo {
    public static void main(String[] args) {
        double[] readings = {
            21.5, Double.NaN, Double.POSITIVE_INFINITY,
            -0.0, 23.0, Double.NEGATIVE_INFINITY
        };

        long total = Arrays.stream(readings).count();
        long invalid = Arrays.stream(readings)
            .filter(x -> !Double.isFinite(x))
            .count();
        long nan = Arrays.stream(readings)
            .filter(Double::isNaN)
            .count();

        DoubleSummaryStatistics valid = Arrays.stream(readings)
            .filter(Double::isFinite)
            .summaryStatistics();

        System.out.println("Tổng bản ghi: " + total);  // 6
        System.out.println("Không hữu hạn: " + invalid); // 3
        System.out.println("NaN: " + nan);              // 1
        System.out.println("Mẫu hợp lệ: " + valid.getCount()); // 3
        System.out.println("Tổng hợp lệ: " + valid.getSum());  // 44.5
        System.out.println("Nhỏ nhất: " + valid.getMin());   // -0.0
        System.out.println("Lớn nhất: " + valid.getMax());   // 23.0
    }
}
```

Ví dụ đã **chủ động định nghĩa “hợp lệ” là hữu hạn**. Dấu âm của `-0.0` vẫn được giữ, vì zero âm không phải NaN hay Infinity. Nếu ý nghĩa nghiệp vụ không phân biệt dấu zero, có thể chuẩn hóa trong pipeline trước khi thống kê.

Mỗi lời gọi `Arrays.stream(readings)` tạo một Stream mới. Không thể dùng lại cùng một đối tượng Stream sau khi terminal operation đã tiêu thụ nó.

### Khi cần từ chối dữ liệu sai ngay

```java
double[] measurements = {1.5, 2.5, Double.NaN};

for (double value : measurements) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Giá trị không hữu hạn");
    }
}

double total = Arrays.stream(measurements).sum();
```

Đây là lựa chọn phù hợp khi dữ liệu sai cần được xử lý như **lỗi đầu vào**. Việc kiểm tra trước tránh trả một giá trị NaN mà phần mã gọi có thể không biết cách xử lý.

## 8. Chạy parallel stream và tính tái lập kết quả

Phép cộng `double` không kết hợp tuyệt đối, trong khi `parallel()` có thể chia phần tử thành nhiều nhóm, tính tổng từng nhóm và gộp kết quả. Do đó, **không bảo đảm bit kết quả của tổng hoặc trung bình giống hệt** giữa mọi cách phân nhóm và thứ tự xử lý, dù dữ liệu đều hữu hạn.

```java
double[] values = {1.0e16, 1.0, -1.0e16, 3.0};

double sequential = Arrays.stream(values).sum();
double parallel = Arrays.stream(values).parallel().sum();

// Cả hai tuân theo phép toán double, nhưng không dùng == để khẳng định
// mọi cách tính tổng dấu phẩy động đều có cùng bit kết quả.
```

Nếu kết quả được dùng để kiểm tra độ gần đúng, nên xác định **sai số tuyệt đối/tương đối** phù hợp miền giá trị; lưu ý NaN và Infinity phải được kiểm tra riêng:

```java
static boolean nearlyEqual(double a, double b, double epsilon) {
    if (!Double.isFinite(a) || !Double.isFinite(b) || epsilon < 0.0) {
        return false;
    }
    return Math.abs(a - b) <= epsilon;
}
```

Đoạn kiểm tra trên là ví dụ đơn giản dùng **sai số tuyệt đối** cho miền giá trị đã biết. Với dữ liệu có độ lớn rất khác nhau, phải cân nhắc sai số tương đối, trường hợp chênh lệch bị tràn và ngữ nghĩa zero có dấu. Không áp dụng máy móc một `epsilon` cho mọi ứng dụng.

Khi dùng `reduce` hay Collector tùy chỉnh với `double`, cần hiểu tính kết hợp của hàm tích lũy, quy tắc gộp từng phần và trạng thái chia sẻ. Với mục tiêu tính tổng primitive, `DoubleStream.sum()` thường diễn đạt ý định và xử lý sai số tốt hơn `reduce(0.0, Double::sum)`. Tuy vậy, không lựa chọn nào tự biến toán học dấu phẩy động thành số học thập phân chính xác tuyệt đối.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Điều cần nhớ |
| --- | --- |
| “NaN là số rất lớn.” | NaN là giá trị đặc biệt, không thuộc thứ tự số học nguyên thủy; `Double.isNaN` để phát hiện |
| “`x == Double.NaN` phát hiện NaN.” | Phép so sánh ấy luôn sai; dùng `Double.isNaN(x)` |
| “`sum()` tự bỏ qua NaN.” | Có NaN trong đầu vào thì tổng trở thành NaN |
| “`count()` cho biết số phép đo hợp lệ.” | `count()` chỉ đếm phần tử, gồm cả NaN và Infinity |
| “`average().orElse(0)` thay thế NaN.” | `orElse` chỉ xử lý `OptionalDouble.empty()`, không xử lý giá trị NaN hiện diện |
| “`+0.0` và `-0.0` giống nhau trong mọi phép toán.” | Chúng bằng nhau theo `==` nhưng khác bit dấu, khác khi chia nghịch đảo và khi dùng `Double.compare` |
| “`distinct()` loại một trong hai zero có dấu.” | `DoubleStream.distinct()` giữ cả `-0.0` lẫn `+0.0` nếu cả hai xuất hiện |
| “`sorted()` không xử lý được NaN.” | `sorted()` dùng thứ tự xác định, NaN được đặt sau `+Infinity` |
| “`DoubleStream.sum()` luôn chính xác tuyệt đối.” | Tổng dấu phẩy động vẫn chịu làm tròn và không nhất thiết tái lập từng bit trong mọi thứ tự cộng |
| “`parallelStream()` luôn cho cùng bit với tuần tự.” | Thứ tự gộp có thể khác; cần chính sách so sánh và yêu cầu độ chính xác phù hợp |
| “Lọc `Double.isFinite` là luôn đúng.” | Đó là lựa chọn nghiệp vụ, có thể khiến dữ liệu lỗi bị bỏ qua nếu không ghi nhận |

## 10. Bài tập có đáp án

**Bài 1 — NaN có ảnh hưởng gì?** Dự đoán:

```java
double[] data = {10.0, Double.NaN, 20.0};
double sum = Arrays.stream(data).sum();
long count = Arrays.stream(data).count();
```

**Đáp án:** `sum` là `NaN`, `count` là `3`. Nếu muốn tổng riêng các giá trị hữu hạn, có thể dùng `Arrays.stream(data).filter(Double::isFinite).sum()` để nhận `30.0`, đồng thời ghi nhận có một phần tử không hợp lệ.

**Bài 2 — Vô cực trái dấu.** Kết quả của biểu thức sau là gì?

```java
double result = DoubleStream
    .of(Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY)
    .sum();
```

**Đáp án:** `NaN`, vì tổng của hai vô cực trái dấu không được xác định theo ngữ nghĩa dấu phẩy động.

**Bài 3 — Zero có dấu.** Có bao nhiêu phần tử sau `distinct()` và thứ tự sắp xếp là gì?

```java
double[] result = DoubleStream.of(+0.0, -0.0, +0.0)
    .distinct()
    .sorted()
    .toArray();
```

**Đáp án:** Hai phần tử, theo thứ tự `[-0.0, 0.0]`. `distinct` phân biệt zero âm/dương, còn `sorted` đặt zero âm trước zero dương.

**Bài 4 — OptionalDouble.** Phân biệt hai đoạn:

```java
OptionalDouble a = DoubleStream.empty().min();
OptionalDouble b = DoubleStream.of(Double.NaN).min();
```

**Đáp án:** `a.isPresent()` là `false` vì không có phần tử; `b.isPresent()` là `true` và `Double.isNaN(b.getAsDouble())` là `true`.

**Bài 5 — Chính sách dữ liệu.** Dữ liệu nhiệt độ gồm `[20.0, NaN, 22.0, +Infinity]`. Chỉ lấy trung bình giá trị hữu hạn:

```java
double[] temperatures = {
    20.0, Double.NaN, 22.0, Double.POSITIVE_INFINITY
};

OptionalDouble average = Arrays.stream(temperatures)
    .filter(Double::isFinite)
    .average();

System.out.println(average.orElseThrow(
    IllegalStateException::new)); // 21.0
```

**Giải thích:** Chính sách này loại NaN và vô cực, giữ `20.0` và `22.0`; trung bình bằng `21.0`. Trong ứng dụng thật, cần đồng thời báo số lượng giá trị bị loại để tránh che giấu vấn đề dữ liệu.

## Ghi nhớ

Trong **JAVA_STREAM_API**, `DoubleStream` cung cấp các phép tổng hợp tiện lợi nhưng vẫn tuân theo ngữ nghĩa `double`: **NaN thường lan truyền**, **vô cực có thể xuất hiện trong tổng/trung bình**, và **`+0.0`/`-0.0` không hoàn toàn tương đương**. `min`, `max`, `sorted` và `distinct` có quy tắc rõ ràng đối với NaN và zero có dấu. Để báo cáo thống kê đúng nghĩa, hãy quyết định cách xử lý giá trị không hữu hạn, phân biệt dữ liệu rỗng với dữ liệu cho ra NaN, đánh giá sai số làm tròn và kiểm soát sự khác biệt khi chạy song song. Khi cần độ chính xác thập phân tuyệt đối, hãy cân nhắc mô hình dữ liệu như `BigDecimal` thay vì giả định `double` luôn biểu diễn chính xác.
