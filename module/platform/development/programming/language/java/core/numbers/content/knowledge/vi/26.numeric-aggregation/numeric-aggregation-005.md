# `min`, `max` và các `Optional` chuyên biệt khi tổng hợp số trong Java

## 1. Mục tiêu và bài toán

Khi tổng hợp dữ liệu số trong Java, hai yêu cầu phổ biến là tìm **giá trị nhỏ nhất (`min`)** và **giá trị lớn nhất (`max`)**. Ví dụ: mức nhiệt thấp nhất trong ngày, độ trễ lớn nhất của request, điểm số cao nhất hoặc số lượng đơn hàng nhỏ nhất.

Khó khăn xuất hiện khi **nguồn dữ liệu rỗng**. Một dãy không có phần tử không có giá trị nhỏ nhất hoặc lớn nhất xác định. Java Stream API biểu diễn điều này bằng `OptionalInt`, `OptionalLong`, `OptionalDouble` hoặc `Optional<T>`; người gọi phải quyết định cách xử lý trường hợp thiếu dữ liệu.

```java
OptionalInt minimum = IntStream.of(8, 3, 12).min();
OptionalInt maximum = IntStream.of(8, 3, 12).max();
// minimum chứa 3; maximum chứa 12
```

Sau bài học, bạn có thể chọn đúng overload `min`/`max`, hiểu vì sao API trả `Optional`, xử lý dãy rỗng an toàn, phân biệt stream nguyên thủy và stream đối tượng, đánh giá trường hợp `NaN`/`-0.0`, và áp dụng `summaryStatistics()` khi cần nhiều phép tổng hợp trên cùng nguồn.

## 2. `min` và `max` trên ba kiểu stream nguyên thủy

Java có ba giao diện stream chuyên biệt cho số nguyên thủy:

| Kiểu stream | Phương thức | Kết quả | Loại giá trị |
| --- | --- | --- | --- |
| `IntStream` | `min()`, `max()` | `OptionalInt` | `int` |
| `LongStream` | `min()`, `max()` | `OptionalLong` | `long` |
| `DoubleStream` | `min()`, `max()` | `OptionalDouble` | `double` |
| `Stream<T>` | `min(Comparator)`, `max(Comparator)` | `Optional<T>` | Đối tượng |

Các phương thức `min()`/`max()` của primitive stream là **terminal operation**: chúng tiêu thụ stream để tính kết quả. Không có overload nhận `Comparator` trên `IntStream`, `LongStream`, `DoubleStream`; các kiểu số nguyên thủy dùng thứ tự số tự nhiên của mình. Với `Stream<T>`, bạn phải truyền một `Comparator` xác định thứ tự.

Ví dụ:

```java
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.OptionalDouble;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

OptionalInt smallestInt = IntStream.of(6, -2, 9).min();
OptionalLong largestLong = LongStream.of(2L, 5_000_000_000L).max();
OptionalDouble smallestDouble = DoubleStream.of(3.5, 1.25).min();

System.out.println(smallestInt.orElseThrow());  // -2
System.out.println(largestLong.orElseThrow());   // 5000000000
System.out.println(smallestDouble.orElseThrow()); // 1.25
```

Đây là **đoạn mã nhúng**: đặt các lệnh trong một phương thức, cùng các `import` đã nêu. Chương trình độc lập có thể chạy ở mục 8.

Các hàm này tìm cực trị theo **giá trị phần tử**. Nếu muốn tìm *phần tử có giá trị điểm số lớn nhất* nhưng vẫn giữ ID, nhãn hoặc thông tin khác, hãy dùng `Stream<T>.max(comparator)` thay vì chỉ chuyển mọi đối tượng thành `int`.

### 2.1. Vì sao kết quả là `Optional`?

Vì không thể gán cực trị hợp lệ cho một stream rỗng:

```java
OptionalInt none = IntStream.empty().max();

System.out.println(none.isPresent()); // false
System.out.println(none.isEmpty());   // true
```

`OptionalInt.empty()` không phải số `0`. Trả `0`, `Integer.MIN_VALUE` hay `null` làm kết quả mặc định sẽ thay đổi ý nghĩa của bài toán nếu giá trị đó vốn có thể xuất hiện trong dữ liệu.

Các overload `min`/`max` với primitive stream tương đương một phép **reduction không có identity** theo phép lấy cực tiểu/cực đại, như `reduce(Integer::min)` với `IntStream`. Vì không có identity phổ quát phân biệt được dãy rỗng, kết quả tự nhiên là `OptionalInt`.

### 2.2. Khoảng kiểu dữ liệu và chuyển đổi

- `IntStream` chứa `int`, từ `Integer.MIN_VALUE` đến `Integer.MAX_VALUE`. Nó không tự nâng mọi đầu vào thành `long`.
- `LongStream` chứa `long`, phù hợp số vượt giới hạn `int`.
- `DoubleStream` chứa `double`, nên chịu các đặc tính số dấu phẩy động IEEE 754 như `NaN`, vô cực và `-0.0`.
- `Stream<Integer>`, `Stream<Long>`, `Stream<Double>` là **stream đối tượng**, có thể cần boxing/unboxing nếu chuyển kiểu và dùng `Optional<T>` thay vì `OptionalInt`/`OptionalLong`/`OptionalDouble`.

Ví dụ danh sách `List<Integer>`:

```java
List<Integer> numbers = List.of(7, 2, 11);
OptionalInt min = numbers.stream()
        .mapToInt(Integer::intValue)
        .min();
```

Lệnh trên cần `import java.util.List; import java.util.OptionalInt;`. `List.of(...)` không chứa `null`, nên chuyển thành primitive an toàn. Với một `List<Integer>` khác có phần tử `null`, unboxing sẽ gây `NullPointerException`; phải đưa ra chính sách lọc/từ chối `null` rõ ràng.

## 3. Các phương thức của `OptionalInt`, `OptionalLong` và `OptionalDouble`

Ba lớp chuyên biệt lưu trạng thái **có hoặc không có một giá trị nguyên thủy**, tránh phải đóng hộp vào `Integer`, `Long`, `Double` chỉ để biểu diễn “có thể vắng mặt”.

| Nhu cầu | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| --- | --- | --- | --- |
| Kiểm tra hiện diện | `isPresent()` / `isEmpty()` | `isPresent()` / `isEmpty()` | `isPresent()` / `isEmpty()` |
| Lấy giá trị khi chắc chắn có | `getAsInt()` | `getAsLong()` | `getAsDouble()` |
| Có giá trị thì lấy, thiếu thì thay | `orElse(int)` | `orElse(long)` | `orElse(double)` |
| Tính fallback khi thiếu | `orElseGet(IntSupplier)` | `orElseGet(LongSupplier)` | `orElseGet(DoubleSupplier)` |
| Thiếu thì ném ngoại lệ | `orElseThrow()` | `orElseThrow()` | `orElseThrow()` |
| Chạy hành động nếu có | `ifPresent(IntConsumer)` | `ifPresent(LongConsumer)` | `ifPresent(DoubleConsumer)` |
| Hai nhánh có/không | `ifPresentOrElse(...)` | `ifPresentOrElse(...)` | `ifPresentOrElse(...)` |
| Chuyển thành stream 0 hoặc 1 phần tử | `stream()` | `stream()` | `stream()` |

Trong Java 17, `isEmpty()`, `stream()`, `ifPresentOrElse()` và `orElseThrow()` đều có thể được sử dụng. Các kiểu primitive Optional **không cung cấp đầy đủ mọi phép biến đổi** giống `Optional<T>`; chẳng hạn không thể mặc định viết `optionalInt.map(x -> ...)` như với `Optional<Integer>`.

### 3.1. Khi nào dùng `orElse`, `orElseGet` và `orElseThrow`?

```java
OptionalInt optional = IntStream.of(4, 9, 2).max();

int mustExist = optional.orElseThrow(); // 9
int fallback = optional.orElse(-1);     // 9 vì Optional có giá trị

OptionalInt missing = IntStream.empty().min();
int defaultValue = missing.orElse(0);   // 0 theo CHÍNH SÁCH người gọi
```

`orElse(0)` chỉ phù hợp nếu nghiệp vụ định nghĩa **không có phần tử = 0**. Đây không phải định nghĩa toán học của min/max trên tập rỗng. Ví dụ đo nhiệt độ, `0°C` là một phép đo hợp lệ, nên dùng `0` để biểu diễn “không có phép đo” là nguy hiểm.

Nếu dữ liệu bắt buộc không rỗng, thể hiện điều đó bằng ngoại lệ:

```java
int peak = IntStream.of(4, 9, 2)
        .max()
        .orElseThrow(() ->
                new IllegalStateException("Không có dữ liệu tính cực đại"));
```

Đây là đoạn nhúng. `orElseGet(() -> expensiveFallback())` chỉ tính fallback khi Optional rỗng; còn đối số truyền vào `orElse(expensiveFallback())` được đánh giá trước khi gọi `orElse`, ngay cả khi đã có giá trị. Fallback kiểu primitive phải trả đúng kiểu `int`, `long` hoặc `double`.

Khi thiếu dữ liệu là trạng thái bình thường, hãy **giữ nguyên Optional** ở ranh giới API để tầng gọi quyết định. Khi thiếu dữ liệu là lỗi của hợp đồng, dùng `orElseThrow` có thông báo phù hợp.

### 3.2. Không gọi `getAs...()` khi chưa xác thực

```java
OptionalLong empty = LongStream.empty().min();
// empty.getAsLong() -> NoSuchElementException
```

`getAsInt`, `getAsLong` và `getAsDouble` chỉ dùng sau `isPresent()` hoặc khi có bảo đảm miền dữ liệu khác rằng Optional không thể rỗng. Nếu bạn định ném lỗi khi thiếu dữ liệu, `orElseThrow()` truyền đạt ý định rõ hơn.

### 3.3. Xử lý với `ifPresent`, `ifPresentOrElse` và `stream`

```java
OptionalInt maybe = IntStream.of(2, 8, 5).max();

maybe.ifPresent(value -> System.out.println("max=" + value));

maybe.ifPresentOrElse(
        value -> System.out.println("Có giá trị: " + value),
        () -> System.out.println("Dữ liệu rỗng"));

int[] result = maybe.stream().map(x -> x * 2).toArray();
// result là mảng chỉ chứa 16
```

Các đoạn này là ví dụ nhúng dùng `OptionalInt` và `IntStream`. `stream()` hữu ích nếu muốn xử lý tiếp 0 hoặc 1 giá trị bằng pipeline primitive mà không tự kiểm tra nhánh rỗng.

## 4. `Stream<T>.min/max` và bộ so sánh (`Comparator`)

Với stream đối tượng, thư viện không biết quy tắc sắp xếp của từng kiểu; API cần comparator:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

record Reading(String id, int score) {}

List<Reading> readings = List.of(
        new Reading("sensor-A", 4),
        new Reading("sensor-B", 9),
        new Reading("sensor-C", 3));

Comparator<Reading> byScore =
        Comparator.comparingInt(Reading::score);

Optional<Reading> smallest = readings.stream().min(byScore);
Optional<Reading> largest = readings.stream().max(byScore);

System.out.println(smallest.orElseThrow().id()); // sensor-C
System.out.println(largest.orElseThrow().id());  // sensor-B
```

Đây là **đoạn nhúng** minh họa một `record` Java 17. Nếu đặt record trong cùng một file `.java` với lớp demo khác, bảo đảm tuân thủ quy tắc tên và số lớp `public`.

`Comparator.comparingInt` đọc `int` qua `ToIntFunction`, tránh boxing cần thiết chỉ để so sánh. Với trường `long`/`double`, có các hàm `comparingLong`/`comparingDouble`. `Stream<Integer>` có thể dùng `Comparator.naturalOrder()` để lấy `Optional<Integer>`; `mapToInt(Integer::intValue).min()` phù hợp hơn nếu cần `OptionalInt`.

### 4.1. Khi nhiều phần tử cùng cực trị

Giả sử hai đơn hàng có điểm `9`. `max(byScore)` có thể chọn một trong hai; **không dựa vào phần tử cụ thể được chọn khi comparator coi chúng ngang nhau**, đặc biệt trong xử lý song song hoặc sau khi thứ tự nguồn thay đổi.

Nếu nghiệp vụ yêu cầu một phần tử xác định, quy định tiêu chí phụ:

```java
Comparator<Reading> ranking = Comparator
        .comparingInt(Reading::score)
        .thenComparing(Reading::id);

Reading selected = readings.stream().max(ranking).orElseThrow();
```

Với comparator này, khi score bằng nhau, `max` chọn ID lớn hơn theo thứ tự từ điển. Nếu muốn ưu tiên ID nhỏ hơn khi score bằng nhau, phải định nghĩa lại tiêu chí phụ, ví dụ `thenComparing(Reading::id, Comparator.reverseOrder())` cho trường hợp lấy `max`. Đây là quyết định miền dữ liệu, không phải mặc định của Stream API.

Comparator nên có tính nhất quán, tính bắc cầu và không dựa vào trạng thái thay đổi trong lúc stream đang chạy. Nếu không, kết quả tổng hợp trở nên khó dự đoán.

### 4.2. `Collectors.minBy/maxBy`

Khi đang dùng `collect` hoặc nhóm dữ liệu:

```java
import java.util.Comparator;
import java.util.Optional;
import java.util.stream.Collectors;

Optional<Integer> min = List.of(6, 3, 9)
        .stream()
        .collect(Collectors.minBy(Comparator.naturalOrder()));
```

`Collectors.minBy` trả `Optional<T>` giống `Stream.min(comparator)`; nó hữu ích khi kết hợp với collector khác như `groupingBy`. Nếu chỉ lấy cực trị của toàn stream, gọi trực tiếp `.min(comparator)` hoặc `.max(comparator)` thường đơn giản hơn.

## 5. Dữ liệu rỗng và ý nghĩa nghiệp vụ

Một nguồn có thể rỗng vì hoàn toàn không có bản ghi, vì filter loại hết mọi phần tử, hoặc vì dữ liệu đầu vào lỗi/không có quyền truy cập. Các trường hợp này có thể có cùng kết quả `Optional.empty()` nhưng **nguyên nhân nghiệp vụ khác nhau**.

```java
OptionalInt expensivePeak = IntStream.of(10, 20, 30)
        .filter(x -> x > 100)
        .max(); // OptionalInt.empty()
```

Trước khi chọn fallback, cần trả lời:

- **Không có dữ liệu là trạng thái bình thường?** Trả về `OptionalInt`/`OptionalLong`/`OptionalDouble` cho caller.
- **Dữ liệu bắt buộc phải tồn tại?** Ném lỗi rõ nguyên nhân, chẳng hạn `orElseThrow`.
- **Có đơn vị mặc định được quy định?** Có thể dùng `orElse(fallback)`; ghi rõ fallback là chính sách của miền nghiệp vụ.
- **Cần JSON/REST?** Thiết kế biểu diễn “không có giá trị” trong DTO/API rõ ràng. Không giả định mọi thư viện JSON đều serialize primitive Optional theo cùng một cách; chuyển sang kiểu DTO/giao thức đã định nghĩa khi xuất dữ liệu.

Không thay Optional rỗng bằng một giá trị cực biên như `Integer.MAX_VALUE` hoặc `Integer.MIN_VALUE` rồi không ghi rõ điều kiện tồn tại, vì giá trị cực biên là một giá trị số thực sự hợp lệ trong miền `int`.

## 6. Trường hợp đặc biệt với `DoubleStream.min/max`

`double` không giống số nguyên vì có các giá trị và thứ tự đặc biệt:

### 6.1. `NaN`

Nếu **bất kỳ phần tử** nào trong `DoubleStream` là `Double.NaN`, thì theo hợp đồng Java 17, `min()`/`max()` trả `OptionalDouble` **có giá trị `NaN`**, kể cả khi các phần tử khác hữu hạn.

```java
double result = DoubleStream.of(3.0, Double.NaN, -5.0)
        .max()
        .orElseThrow();

System.out.println(result); // NaN
```

`OptionalDouble` lúc này **không rỗng**. `isPresent()` chỉ cho biết có phần tử được tổng hợp, không khẳng định giá trị là số hữu hạn.

Nếu miền dữ liệu quy định phải bỏ `NaN`, lọc có chủ đích:

```java
OptionalDouble cleanMin = DoubleStream.of(3.0, Double.NaN, -5.0)
        .filter(d -> !Double.isNaN(d))
        .min();
// cleanMin chứa -5.0
```

Nếu không chấp nhận cả vô cực, dùng `Double.isFinite(d)` để chỉ giữ các giá trị hữu hạn. Tuy nhiên, lọc dữ liệu là **quy tắc nghiệp vụ**; với dữ liệu đáng lẽ phải hợp lệ, từ chối một bản ghi có `NaN` có thể thích hợp hơn là âm thầm bỏ qua.

### 6.2. Hai loại số không: `-0.0` và `+0.0`

Java phân biệt dấu của số không ở kiểu `double`:

```java
System.out.println(DoubleStream.of(+0.0, -0.0).min().orElseThrow()); // -0.0
System.out.println(DoubleStream.of(+0.0, -0.0).max().orElseThrow()); // 0.0
```

`DoubleStream.min()` coi `-0.0` nhỏ hơn `+0.0`; `max()` coi `+0.0` lớn hơn `-0.0`, phù hợp với thứ tự của `Double.compare`. Nếu dấu của số 0 có ý nghĩa với phép đo hay phép tính tiếp theo, không xóa dấu một cách tùy tiện.

### 6.3. Vô cực và độ chính xác số dấu phẩy động

`Double.POSITIVE_INFINITY`/`Double.NEGATIVE_INFINITY` có thể tham gia min/max. Kết quả vẫn thuộc kiểu `double` và chịu sai số của biểu diễn số dấu phẩy động. Ví dụ phép tổng hợp **min/max** tự nó không làm tròn thêm như phép cộng liên tục, nhưng từng giá trị nguồn có thể đã bị xấp xỉ trước đó.

Nếu miền dữ liệu là tiền tệ/thập phân cần biểu diễn chính xác, cân nhắc `BigDecimal` trong `Stream<BigDecimal>` cùng comparator tự nhiên thay vì tự động chuyển sang `double`:

```java
Optional<BigDecimal> min = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"))
        .stream()
        .min(BigDecimal::compareTo);
```

Đây là đoạn nhúng cần `import java.math.BigDecimal; import java.util.List; import java.util.Optional;`. Chú ý `BigDecimal.compareTo` so theo **giá trị số**, trong khi `BigDecimal.equals` còn xét scale; bài toán cực trị thường muốn so giá trị.

## 7. Tính đồng thời min và max bằng `summaryStatistics()`

Nếu cần cả min, max, count, sum và average của cùng một nguồn, có thể lấy tất cả trong **một lần duyệt**:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.of(7, -2, 13, 13, 0)
        .summaryStatistics();

System.out.println(stats.getCount()); // 5
System.out.println(stats.getMin());   // -2
System.out.println(stats.getMax());   // 13
System.out.println(stats.getSum());   // 31
System.out.println(stats.getAverage()); // 6.2
```

Java có `IntSummaryStatistics`, `LongSummaryStatistics` và `DoubleSummaryStatistics`. `summaryStatistics()` hữu ích khi cần nhiều metric và tránh việc cố tái sử dụng một stream đã bị tiêu thụ.

**Lưu ý với nguồn rỗng:** `IntSummaryStatistics` có `count == 0`; khi chưa có phần tử, `getMin()` trả `Integer.MAX_VALUE`, `getMax()` trả `Integer.MIN_VALUE`. Đây là **giá trị khởi tạo nội bộ**, không phải min/max có nghĩa cho tập rỗng. Với `LongSummaryStatistics`, các giá trị mặc định tương tự theo miền `long`. Với `DoubleSummaryStatistics`, min và max của nguồn rỗng lần lượt là `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`.

Vì vậy, trước khi sử dụng cực trị:

```java
IntSummaryStatistics stats = IntStream.empty().summaryStatistics();
if (stats.getCount() == 0) {
    System.out.println("Không có dữ liệu");
} else {
    System.out.println(stats.getMin());
}
```

`summaryStatistics()` có thêm chính sách về tổng/average: `int` sum có thể tràn số nguyên, `long` sum cũng có thể tràn, còn phép tính trên `double` có thể mang sai số dấu phẩy động. Vì vậy, chọn công cụ theo yêu cầu phép tổng hợp, không dùng statistics như một giải pháp “chính xác tuyệt đối” cho mọi chỉ số.

### Stream chỉ dùng một lần

Đoạn sau **không hợp lệ** vì một stream không được dùng lại sau terminal operation:

```java
IntStream source = IntStream.of(3, 7, 2);
int min = source.min().orElseThrow();
// source.max(); // IllegalStateException: stream đã bị tiêu thụ
```

Muốn lấy cả min và max, tạo hai stream mới từ nguồn có thể duyệt lại (ví dụ `Arrays.stream(array)` mỗi lần) hoặc dùng `summaryStatistics()` một lượt. Với nguồn I/O chỉ đọc một lần, `summaryStatistics()` thường là hướng hợp lý cho các thống kê được hỗ trợ.

## 8. Chương trình Java 17+ chạy được

Lưu vào **`MinMaxOptionalDemo.java`**:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class MinMaxOptionalDemo {
    record Reading(String id, int score) {}

    public static void main(String[] args) {
        int[] scores = {7, -2, 13, 13, 0};

        OptionalInt smallest = Arrays.stream(scores).min();
        OptionalInt biggest = Arrays.stream(scores).max();
        OptionalInt empty = IntStream.empty().min();
        OptionalLong biggestLong =
                LongStream.of(5_000_000_000L, -4L, 9L).max();
        OptionalDouble smallestDouble =
                DoubleStream.of(2.5, -0.0, 7.75).min();

        List<Reading> readings = List.of(
                new Reading("A", 4),
                new Reading("B", 9),
                new Reading("C", 3));
        Comparator<Reading> ranking = Comparator
                .comparingInt(Reading::score)
                .thenComparing(Reading::id);

        Reading minReading = readings.stream()
                .min(ranking).orElseThrow();
        Reading maxReading = readings.stream()
                .max(ranking).orElseThrow();

        IntSummaryStatistics stats =
                Arrays.stream(scores).summaryStatistics();

        System.out.println("int min = " + smallest.orElseThrow());
        System.out.println("int max = " + biggest.orElseThrow());
        System.out.println("empty = " + empty.isEmpty());
        System.out.println("long max = " + biggestLong.orElseThrow());
        System.out.println("double min = " + smallestDouble.orElseThrow());
        System.out.println("reading min = " + minReading);
        System.out.println("reading max = " + maxReading);
        System.out.println("count = " + stats.getCount());
        System.out.println("stats min/max = "
                + stats.getMin() + "/" + stats.getMax());
        System.out.println("NaN max = "
                + DoubleStream.of(3.0, Double.NaN, -5.0)
                              .max().orElseThrow());
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac MinMaxOptionalDemo.java
java MinMaxOptionalDemo
```

Stdout chính xác:

```text
int min = -2
int max = 13
empty = true
long max = 5000000000
double min = -0.0
reading min = Reading[id=C, score=3]
reading max = Reading[id=B, score=9]
count = 5
stats min/max = -2/13
NaN max = NaN
```

**Giải thích:** Các số trong `scores` cho min `-2` và max `13`; `IntStream.empty()` dẫn tới Optional rỗng. `LongStream` giữ được giá trị `5_000_000_000` vượt phạm vi `int`. `DoubleStream` giữ dấu của `-0.0`. Comparator giữ nguyên bản ghi `Reading` gắn với điểm cực trị. `summaryStatistics` đếm năm phần tử và cùng cực trị. Giá trị `NaN` trong nguồn làm `DoubleStream.max()` trả `NaN` thay vì trả `3.0`.

Trong chương trình này, `orElseThrow()` trên các stream không rỗng là hợp lệ vì dữ liệu mẫu đã định rõ. Với nguồn có thể rỗng từ API hoặc database, phải xử lý từng Optional theo chính sách của miền thay vì mặc định `orElseThrow` ở mọi nơi.

## 9. Hiệu năng, song song và thứ tự so sánh

Để tìm riêng min hoặc max, một phép duyệt đầy đủ thông thường có độ phức tạp thời gian **O(n)** và không cần sắp xếp toàn bộ dữ liệu. `stream().sorted().findFirst()` có thể tìm giá trị thấp nhất nhưng phải sắp xếp và thường tốn nhiều tài nguyên hơn `min(comparator)`.

Với `IntStream`/`LongStream`/`DoubleStream`, tránh boxing không cần thiết trong quá trình reduction. Khi dữ liệu đã là `List<Reading>`, việc chuyển sang một primitive stream để lấy giá trị rồi truy ngược về đối tượng có thể tạo thêm vấn đề; dùng comparator trực tiếp để giữ metadata.

`min` và `max` có thể dùng với stream song song nếu nguồn, mapping và comparator được thiết kế an toàn:

```java
OptionalInt min = IntStream.rangeClosed(1, 1_000_000)
        .parallel()
        .min();
// Kết quả có giá trị 1, nhưng việc parallel có nhanh hơn hay không phải đo.
```

Nếu nhiều đối tượng được comparator coi ngang nhau, không dựa vào việc chọn một phần tử cụ thể; hãy tạo tiêu chí phụ nếu cần kết quả duy nhất theo hợp đồng. Không để comparator đọc/ghi shared mutable state hay thay đổi các giá trị đang được so sánh giữa chừng.

Không sử dụng `min`/`max` trên một nguồn đang bị sửa đồng thời thiếu đồng bộ; tính đúng đắn của kết quả còn phụ thuộc vào ràng buộc của collection/source. Với các Stream API, nguồn và các lambda phải tuân thủ nguyên tắc không can thiệp và không có trạng thái dùng chung nguy hiểm.

## 10. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách làm |
| --- | --- | --- |
| Gọi `getAsInt()` trên kết quả của stream rỗng | `NoSuchElementException` | Dùng `orElse`, `orElseThrow`, `ifPresent` hoặc trả Optional |
| Nghĩ `OptionalInt.empty()` tương đương `0` | Báo min/max giả, che mất dữ liệu | Giữ trạng thái vắng mặt rõ ràng |
| Dùng `Integer.MIN_VALUE` làm mặc định max mà không kiểm tra hiện diện | Không phân biệt được rỗng với dữ liệu thật có giá trị cực biên | Trả Optional hoặc thêm flag hiện diện |
| Gọi `.min()` rồi `.max()` trên cùng một Stream | `IllegalStateException` | Tạo stream mới hoặc dùng `summaryStatistics()` |
| Dùng `Stream<T>.min()` không có comparator | Không biên dịch | Truyền `Comparator` hoặc chuyển sang primitive stream phù hợp |
| Gọi `getAsInt` trên `Optional<Integer>` | Không biên dịch | Với object Optional dùng `get`/`orElseThrow`; muốn primitive dùng `mapToInt` |
| Không xử lý `NaN` trong `DoubleStream` | Min/max chứa `NaN` dù các số khác hợp lệ | Định nghĩa chính sách reject/filter theo miền |
| Nhầm `-0.0` bằng `+0.0` về mọi ngữ nghĩa | Kết quả hiển thị và thứ tự cực trị bất ngờ | Xem quy tắc `Double.compare` và hợp đồng ứng dụng |
| Comparator chỉ xét score khi cần kết quả thắng cuộc duy nhất | Các bản ghi cùng score không phân biệt | Thêm tiêu chí phụ bằng `thenComparing` |
| Dùng `summaryStatistics.getMin()` trên tập rỗng mà không xét count | Nhận giá trị khởi tạo nội bộ thay vì min thực | Kiểm tra `getCount() > 0` |
| Dùng `sorted()` để lấy một cực trị | Tốn thời gian/bộ nhớ không cần thiết | Dùng terminal `min` hoặc `max` |
| Đưa `null` vào `mapToInt(Integer::intValue)` | `NullPointerException` khi unboxing | Xác thực, lọc hoặc xử lý null có chủ đích |

## 11. Bài tập tự kiểm tra

1. Cho `IntStream.of(-3, 0, 9, 9)`: `min`, `max` trả gì? Vì sao dùng `OptionalInt` thay vì trả trực tiếp `int`?
2. Sau `.filter(x -> x > 100)` trên dãy trên, Optional của `max()` là gì? Khi nào bạn sẽ dùng `orElseThrow` thay vì `orElse(0)`?
3. Với các `Reading(id, score)` có hai phần tử cùng `score`, hãy định nghĩa tie-breaker để lấy score lớn nhất, rồi ưu tiên ID *nhỏ nhất*.
4. Với `DoubleStream.of(2.0, Double.NaN, -10.0)`, kết quả `.min()` là gì? Sửa pipeline để chỉ xét giá trị hữu hạn.
5. Vì sao `IntStream.empty().summaryStatistics().getMin()` không thể coi là cực tiểu của tập dữ liệu? Bạn cần kiểm tra thuộc tính nào?
6. Một request cần `min`, `max`, `count` trên nguồn chỉ đọc được một lần. Nên gọi ba terminal operation trên cùng stream, hay chọn phương pháp nào?
7. Viết hàm nhận `List<Integer>` và trả `OptionalInt` chứa giá trị lớn nhất, với quy tắc từ chối `null`, không dùng `sorted()`.

**Gợi ý:** (1) min `-3`, max `9`, vì nguồn bất kỳ có thể rỗng. (2) `OptionalInt.empty()`; `orElseThrow` khi thiếu dữ liệu vi phạm hợp đồng. (3) `comparingInt(Reading::score).thenComparing(Reading::id, Comparator.reverseOrder())` rồi `.max(...)`. (4) `NaN`; dùng `.filter(Double::isFinite)` nếu quy tắc miền yêu cầu. (5) `getCount() == 0` có nghĩa chưa có phần tử. (6) `summaryStatistics()` một lần. (7) dùng `stream().mapToInt(Integer::intValue).max()` sau khi bảo đảm không có null.

## 12. Ghi nhớ áp dụng

Để lấy cực trị trên dữ liệu số, ưu tiên `IntStream.min/max`, `LongStream.min/max`, `DoubleStream.min/max` theo kiểu dữ liệu và nhận `OptionalInt`, `OptionalLong`, `OptionalDouble`. Với dữ liệu đối tượng, dùng `Stream<T>.min/max(Comparator)` để giữ toàn bộ đối tượng. Hãy xác định chính sách **thiếu dữ liệu** rõ ràng, đặc biệt khi stream rỗng do filter; không tùy tiện thay bằng 0.

Nếu cần nhiều chỉ số trên cùng stream, dùng `summaryStatistics()` và kiểm tra `count` trước khi đọc ý nghĩa min/max của nguồn rỗng. Với `double`, xác định chính sách cho `NaN`, vô cực và dấu số không. Khi cần thứ tự ổn định cho các bản ghi bằng điểm, định nghĩa comparator có tiêu chí phụ.

Tài liệu API Java SE 17:
- [`IntStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html), [`LongStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/LongStream.html), [`DoubleStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html).
- [`OptionalInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html), [`OptionalLong`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalLong.html), [`OptionalDouble`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalDouble.html).
- [`Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [`IntSummaryStatistics`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IntSummaryStatistics.html).
