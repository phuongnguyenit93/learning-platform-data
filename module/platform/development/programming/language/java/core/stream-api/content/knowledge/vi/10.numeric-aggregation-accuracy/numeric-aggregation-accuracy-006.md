# Chọn `summaryStatistics` thay cho nhiều lần duyệt nguồn

Trong **Java Stream API**, ta thường cần nhiều đại lượng trên cùng một tập dữ liệu: **số phần tử, tổng, nhỏ nhất, lớn nhất và trung bình**. Nếu viết năm pipeline riêng biệt để gọi `count()`, `sum()`, `min()`, `max()` và `average()`, chương trình có thể phải đọc hoặc xử lý nguồn nhiều lần. Các kiểu `IntSummaryStatistics`, `LongSummaryStatistics` và `DoubleSummaryStatistics` giúp tổng hợp năm đại lượng đó trong **một phép toán kết thúc**.

Chủ đề này thuộc phần **Độ chính xác khi tổng hợp số**: chọn `summaryStatistics()` giúp giảm việc duyệt lại nguồn, nhưng vẫn phải hiểu phạm vi kiểu số, dữ liệu rỗng, sai số dấu phẩy động, tính chất của xử lý song song và vòng đời của stream.

## 1. Khi nào nhiều lần duyệt nguồn trở thành vấn đề?

Giả sử có danh sách điểm `[12, 18, 24, 30]` và cần trình bày các thống kê. Một cách viết dễ nghĩ tới là tạo lại stream cho mỗi đại lượng:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> scores = Arrays.asList(12, 18, 24, 30);

long count = scores.stream().mapToInt(Integer::intValue).count();
int minimum = scores.stream().mapToInt(Integer::intValue)
    .min().orElseThrow(IllegalStateException::new);
int maximum = scores.stream().mapToInt(Integer::intValue)
    .max().orElseThrow(IllegalStateException::new);
long sum = scores.stream().mapToLong(Integer::longValue).sum();
double average = scores.stream().mapToInt(Integer::intValue)
    .average().orElseThrow(IllegalStateException::new);

System.out.println(count);   // 4
System.out.println(minimum); // 12
System.out.println(maximum); // 30
System.out.println(sum);     // 84
System.out.println(average); // 21.0
```

Mỗi lần gọi `scores.stream()` tạo một **pipeline mới**. Các phép toán như `min`, `max`, `sum`, `average` thường cần xét hết phần dữ liệu liên quan. Trên nguồn lớn hoặc có `filter`/`map` đắt tiền, việc lặp lại có thể tiêu tốn thời gian và tài nguyên. Một số trường hợp đặc biệt, chẳng hạn `count` trên nguồn biết trước kích thước, có thể được tối ưu mà không gọi hết mapper; không nên suy ra rằng mọi lambda luôn chạy chính xác một lần ở mỗi pipeline.

Không thể lưu một `Stream` rồi gọi nhiều terminal operation trên cùng đối tượng:

```java
import java.util.stream.IntStream;

IntStream numbers = IntStream.of(12, 18, 24, 30);
long count = numbers.count();

// Không hợp lệ: stream đã bị tiêu thụ.
// int sum = numbers.sum(); // IllegalStateException
```

Với nguồn là `List`, ta có thể tạo stream mới mỗi lần; với nguồn chỉ đọc được một lần như luồng I/O, mạng hoặc iterator tiêu thụ dần, cách làm đó có thể không khả thi hoặc khiến dữ liệu giữa các lần đọc không nhất quán.

## 2. `summaryStatistics()`: năm thống kê trong một pipeline

Cách gọn hơn là chuyển dữ liệu về primitive stream rồi gọi một terminal operation:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;

List<Integer> scores = Arrays.asList(12, 18, 24, 30);

IntSummaryStatistics stats = scores.stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 84
System.out.println(stats.getMin());     // 12
System.out.println(stats.getMax());     // 30
System.out.println(stats.getAverage()); // 21.0
```

`summaryStatistics()` là **terminal operation**: quá trình duyệt nguồn và cập nhật trạng thái thống kê diễn ra trong một pipeline. Nó không phải phép toán ngắn mạch, vì để biết min/max/tổng chính xác theo hợp đồng, phải xét mọi phần tử đầu vào hữu hạn còn lại.

Hình dung quá trình tích lũy:

```text
Nguồn -> filter/map lazy -> IntStream -> summaryStatistics()
                                        |
                                        +-- count
                                        +-- sum
                                        +-- min
                                        +-- max
                                        +-- average = sum / count (khi count > 0)
```

Từng phần tử được đưa vào bộ tích lũy cần thiết cho các thống kê; sau khi terminal operation trả về, ta đọc các thuộc tính trên **một đối tượng kết quả** mà không cần duyệt lại nguồn.

### Chọn đúng kiểu theo loại dữ liệu

| Primitive stream | Phép toán kết thúc | Đối tượng kết quả | Các giá trị đọc được |
| --- | --- | --- | --- |
| `IntStream` | `summaryStatistics()` | `IntSummaryStatistics` | `getCount()`, `getSum()`, `getMin()`, `getMax()`, `getAverage()` |
| `LongStream` | `summaryStatistics()` | `LongSummaryStatistics` | Cùng bộ getter, theo kiểu `long` cho sum/min/max |
| `DoubleStream` | `summaryStatistics()` | `DoubleSummaryStatistics` | Cùng bộ getter, theo kiểu `double` cho sum/min/max/average |

Các kiểu này thuộc `java.util` và có từ Java 8. `getCount()` luôn trả `long`; `getAverage()` trả `double`. Với `IntSummaryStatistics`, `getSum()` trả `long`, trong khi `getMin()` và `getMax()` trả `int`. Với `LongSummaryStatistics`, tổng, min và max là `long`; với `DoubleSummaryStatistics`, chúng là `double`.

## 3. Từ dữ liệu đối tượng sang thống kê số

Dữ liệu nghiệp vụ thường nằm trong đối tượng: đơn hàng, giao dịch, bài kiểm tra, cảm biến. Hãy dùng `mapToInt`, `mapToLong` hoặc `mapToDouble` để trích đúng trường số, rồi thống kê.

```java
import java.util.Arrays;
import java.util.List;
import java.util.LongSummaryStatistics;

public class OrderSummary {
    static final class Order {
        final String id;
        final boolean paid;
        final long amountInMinorUnits;

        Order(String id, boolean paid, long amountInMinorUnits) {
            this.id = id;
            this.paid = paid;
            this.amountInMinorUnits = amountInMinorUnits;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
            new Order("A", true, 15000L),
            new Order("B", false, 7000L),
            new Order("C", true, 25000L),
            new Order("D", true, 10000L)
        );

        LongSummaryStatistics paidStats = orders.stream()
            .filter(order -> order.paid)
            .mapToLong(order -> order.amountInMinorUnits)
            .summaryStatistics();

        System.out.println(paidStats.getCount());   // 3
        System.out.println(paidStats.getSum());     // 50000
        System.out.println(paidStats.getMin());     // 10000
        System.out.println(paidStats.getMax());     // 25000
        System.out.println(paidStats.getAverage()); // 16666.666...
    }
}
```

Trong ví dụ, chỉ những đơn đã thanh toán được đưa vào thống kê. `filter` và `mapToLong` là các bước trung gian lazy; `summaryStatistics` kích hoạt chúng. Một phần tử đi qua pipeline một lần về mặt logic, thay vì viết nhiều pipeline lặp lại điều kiện `order.paid` và phép trích số tiền.

Lưu số tiền bằng đơn vị nguyên nhỏ nhất là một lựa chọn thiết kế hữu ích khi cần tránh biểu diễn thập phân bằng `double`. Tuy nhiên, **trung bình** từ `getAverage()` vẫn là `double` và có thể cần quy tắc làm tròn riêng khi chuyển thành số tiền thanh toán.

## 4. Độ chính xác của `IntSummaryStatistics`: tổng là `long`

Một lợi ích dễ bỏ qua là `IntSummaryStatistics.getSum()` trả về **`long`**, dù các giá trị đầu vào là `int`. Trái lại, `IntStream.sum()` trả về `int` và có thể tràn nếu tổng vượt phạm vi 32 bit.

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;

int[] largeValues = {1_500_000_000, 1_500_000_000};

int intSum = Arrays.stream(largeValues).sum();
IntSummaryStatistics stats = Arrays.stream(largeValues)
    .summaryStatistics();
long summarySum = stats.getSum();

System.out.println(intSum);      // -1294967296 (tràn int)
System.out.println(summarySum);  // 3000000000
System.out.println(stats.getAverage()); // 1500000000.0
```

`IntSummaryStatistics` tích lũy các `int` vào tổng kiểu `long`, giúp tránh tràn `int` trong nhiều bài toán thực tế. **Không có nghĩa là tổng không bao giờ tràn**: với một số lượng cực lớn phần tử hoặc tổng vượt `Long.MAX_VALUE`/`Long.MIN_VALUE`, `long` cũng có giới hạn.

Nếu chỉ muốn tổng `long` và không cần min/max/count/average, `intStream.asLongStream().sum()` hoặc `mapToLong(...).sum()` thường diễn đạt mục tiêu trực tiếp hơn. Không cần tạo bộ thống kê đầy đủ cho một đại lượng duy nhất.

### `LongSummaryStatistics` vẫn có giới hạn

```java
import java.util.LongSummaryStatistics;
import java.util.stream.LongStream;

LongSummaryStatistics stats = LongStream.of(Long.MAX_VALUE, 1L)
    .summaryStatistics();

System.out.println(stats.getCount()); // 2
System.out.println(stats.getSum());   // Long.MIN_VALUE do tràn long
```

`LongSummaryStatistics` dùng tổng kiểu `long`; nó **không tự phát hiện hoặc ném lỗi tràn** như `Math.addExact`. Khi phải phát hiện tràn và chỉ cần tính tổng, có thể dùng `LongStream.reduce(0L, Math::addExact)` để ném `ArithmeticException` nếu phép cộng tràn:

```java
import java.util.stream.LongStream;

long safeTotal = LongStream.of(10L, 20L, 30L)
    .reduce(0L, Math::addExact);

System.out.println(safeTotal); // 60
```

Nếu tổng vượt phạm vi `long` một cách hợp lệ theo nghiệp vụ, cân nhắc `BigInteger` hoặc `BigDecimal` qua `Stream<T>`. Những kiểu này dùng đối tượng, có chi phí và hợp đồng tính toán khác, nhưng đáp ứng nhu cầu độ chính xác vượt phạm vi primitive.

## 5. Dữ liệu rỗng: luôn kiểm tra `getCount()`

Không giống `min()`, `max()` hoặc `average()` của primitive stream vốn trả `OptionalInt`, `OptionalLong`, `OptionalDouble`, `summaryStatistics()` **luôn trả về đối tượng thống kê**, kể cả khi không có phần tử.

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics empty = IntStream.empty().summaryStatistics();

System.out.println(empty.getCount());   // 0
System.out.println(empty.getSum());     // 0
System.out.println(empty.getAverage()); // 0.0
System.out.println(empty.getMin());     // Integer.MAX_VALUE
System.out.println(empty.getMax());     // Integer.MIN_VALUE
```

Khi chưa nhận phần tử nào, min/max mang **giá trị khởi tạo đặc biệt** chứ không phải một quan sát thực tế. Hợp đồng các đối tượng thống kê khi rỗng:

| Kiểu | `getMin()` khi rỗng | `getMax()` khi rỗng | `getSum()` | `getAverage()` |
| --- | --- | --- | --- | --- |
| `IntSummaryStatistics` | `Integer.MAX_VALUE` | `Integer.MIN_VALUE` | `0L` | `0.0` |
| `LongSummaryStatistics` | `Long.MAX_VALUE` | `Long.MIN_VALUE` | `0L` | `0.0` |
| `DoubleSummaryStatistics` | `Double.POSITIVE_INFINITY` | `Double.NEGATIVE_INFINITY` | `0.0` | `0.0` |

Vì vậy, đừng trả `getMin()` của nhóm rỗng cho người dùng như “giá trị nhỏ nhất”. Hãy kiểm tra `getCount() == 0` trước khi đọc min, max hay diễn giải average:

```java
if (empty.getCount() == 0) {
    System.out.println("Không có dữ liệu hợp lệ để thống kê");
} else {
    System.out.println("Thấp nhất: " + empty.getMin());
}
```

Trong bài toán giám sát, phân biệt **“trung bình bằng 0”** với **“không có mẫu để tính trung bình”** là điều quan trọng. Giá trị `0.0` trả về trên dữ liệu rỗng là quy ước của API, không chứng minh đã quan sát được đại lượng bằng 0.

## 6. `DoubleSummaryStatistics`: hiểu sai số trước khi dùng

Với dữ liệu đo đạc hoặc xác suất, `DoubleSummaryStatistics` cung cấp cùng năm thống kê:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics measurements = DoubleStream.of(2.5, 3.0, 4.5)
    .summaryStatistics();

System.out.println(measurements.getCount());   // 3
System.out.println(measurements.getSum());     // 10.0
System.out.println(measurements.getMin());     // 2.5
System.out.println(measurements.getMax());     // 4.5
System.out.println(measurements.getAverage()); // xấp xỉ 3.3333333333333335
```

`double` là số dấu phẩy động nhị phân. Nhiều số thập phân như `0.1` hoặc `0.2` không biểu diễn chính xác trong kiểu này. Khi cộng nhiều số, sai số làm tròn phụ thuộc dữ liệu và thứ tự cộng. Triển khai JDK có thể dùng kỹ thuật tổng có bù sai số (*compensated summation*), nhưng **không được coi `getSum()` hoặc `getAverage()` là phép tính thập phân chính xác tuyệt đối**.

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics stats = DoubleStream.of(0.1, 0.2, 0.3)
    .summaryStatistics();

double expected = 0.6;
double tolerance = 1e-12;
System.out.println(Math.abs(stats.getSum() - expected) < tolerance);
// true với dữ liệu và ngưỡng trong ví dụ
```

Ngưỡng `1e-12` chỉ minh họa. Trong kiểm thử thực tế, phải xác định sai số tuyệt đối hoặc tương đối phù hợp với quy mô và đơn vị của dữ liệu. Nếu thống kê tiền tệ yêu cầu kết quả thập phân chính xác, nên dùng biểu diễn số nguyên theo đơn vị nhỏ nhất hoặc `BigDecimal` cùng quy tắc làm tròn rõ ràng.

### `NaN`, vô cực và giá trị bất thường

`DoubleSummaryStatistics` không tự loại giá trị không hữu hạn. Nếu đầu vào có `NaN`, tổng và các giá trị min/max/average có thể trở thành `NaN`; hai giá trị `+Infinity` và `-Infinity` cũng khiến tổng không xác định:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics stats = DoubleStream
    .of(1.0, Double.NaN, 2.0)
    .summaryStatistics();

System.out.println(Double.isNaN(stats.getSum())); // true
System.out.println(Double.isNaN(stats.getMin())); // true
```

Khi nghiệp vụ chỉ chấp nhận số hữu hạn, đặt điều kiện lọc rõ ràng trước khi thống kê:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics finiteStats = DoubleStream
    .of(1.0, Double.NaN, Double.POSITIVE_INFINITY, 2.0)
    .filter(x -> !Double.isNaN(x) && !Double.isInfinite(x))
    .summaryStatistics();

System.out.println(finiteStats.getCount());   // 2
System.out.println(finiteStats.getAverage()); // 1.5
```

Việc lọc không hữu hạn chỉ thích hợp nếu quy tắc xử lý dữ liệu cho phép; trong hệ thống cảnh báo lỗi cảm biến, có thể phải **ghi nhận** mẫu bất thường thay vì âm thầm bỏ qua.

## 7. `Collectors.summarizingInt/Long/Double` khi cần nhóm dữ liệu

`summaryStatistics()` nằm trên các primitive stream. Nếu đang làm việc với `Stream<T>` và muốn thống kê trường số của từng phần tử, có thể dùng các collector:

| Collector | Nhận mapper | Kết quả |
| --- | --- | --- |
| `Collectors.summarizingInt(mapper)` | `ToIntFunction<? super T>` | `IntSummaryStatistics` |
| `Collectors.summarizingLong(mapper)` | `ToLongFunction<? super T>` | `LongSummaryStatistics` |
| `Collectors.summarizingDouble(mapper)` | `ToDoubleFunction<? super T>` | `DoubleSummaryStatistics` |

Ví dụ không nhóm:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

List<String> words = Arrays.asList("Java", "Stream", "API");

IntSummaryStatistics lengths = words.stream()
    .collect(Collectors.summarizingInt(String::length));

System.out.println(lengths.getCount()); // 3
System.out.println(lengths.getSum());   // 13
```

Về kết quả, ví dụ này tương ứng với `words.stream().mapToInt(String::length).summaryStatistics()`. Phiên bản `Collectors.summarizingInt` đặc biệt tiện khi đặt **bên trong một collector khác**, chẳng hạn `groupingBy`.

### Một lượt duyệt logic để thống kê từng nhóm

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class SummaryByTeam {
    static final class Task {
        final String team;
        final int minutes;

        Task(String team, int minutes) {
            this.team = team;
            this.minutes = minutes;
        }
    }

    public static void main(String[] args) {
        List<Task> tasks = Arrays.asList(
            new Task("API", 30),
            new Task("UI", 45),
            new Task("API", 15),
            new Task("UI", 20),
            new Task("API", 25)
        );

        Map<String, IntSummaryStatistics> byTeam = tasks.stream()
            .collect(Collectors.groupingBy(
                task -> task.team,
                Collectors.summarizingInt(task -> task.minutes)
            ));

        IntSummaryStatistics api = byTeam.get("API");
        System.out.println(api.getCount());   // 3
        System.out.println(api.getSum());     // 70
        System.out.println(api.getMin());     // 15
        System.out.println(api.getMax());     // 30
        System.out.println(api.getAverage()); // 23.333...
    }
}
```

`groupingBy` phân loại phần tử theo khóa, còn `summarizingInt` tích lũy thống kê của từng nhóm. Đây là cách phù hợp hơn việc lọc toàn bộ danh sách **năm lần cho mỗi nhóm**. Bản đồ kết quả chỉ có những khóa thực sự xuất hiện; gọi `byTeam.get("OTHER")` có thể trả `null`, vì vậy cần kiểm tra nhóm có tồn tại trước khi đọc thống kê.

Để thống kê một giá trị duy nhất theo nhóm (chẳng hạn chỉ tổng thời gian), `Collectors.summingInt`/`summingLong` cũng phù hợp. Không nhất thiết chọn `summarizingInt` nếu không dùng count, min, max và average.

## 8. Nguồn tệp, nguồn đọc một lần và vòng đời tài nguyên

Với stream lấy từ `Files.lines`, đọc dữ liệu lại nhiều lần đồng nghĩa mở và quét lại tệp. Nếu tệp lớn, điều đó tốn I/O; nếu tệp đang được cập nhật, các lần đọc còn có thể phản ánh những bộ dữ liệu khác nhau.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LongSummaryStatistics;
import java.util.stream.Stream;

public class FileStatistics {
    public static LongSummaryStatistics read(Path path)
            throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return lines.map(String::trim)
                .filter(line -> !line.isEmpty())
                .mapToLong(Long::parseLong)
                .summaryStatistics();
        }
    }
}
```

Pipeline này đọc mỗi dòng dữ liệu hợp lệ để cập nhật năm thống kê, thay vì tạo năm luồng đọc tệp độc lập. `try-with-resources` đóng stream và tài nguyên I/O sau khi kết thúc, kể cả khi xảy ra lỗi trong quá trình phân tích dòng.

`summaryStatistics` là **terminal operation**, nhưng tự nó **không thay thế `close()`**. Stream dựa trên collection thường không cần đóng; stream gắn với I/O phải được quản lý tài nguyên đúng cách. `Long::parseLong` có thể ném `NumberFormatException` nếu dòng không hợp lệ, vì vậy cần quy định xử lý dữ liệu lỗi trước khi dùng trong hệ thống thực tế.

### Nguồn vô hạn phải có ranh giới

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics firstHundred = IntStream.iterate(1, n -> n + 1)
    .limit(100)
    .summaryStatistics();

System.out.println(firstHundred.getCount()); // 100
System.out.println(firstHundred.getSum());   // 5050
```

`summaryStatistics` không thể trả kết quả đầy đủ nếu nguồn cứ sinh phần tử mãi mà không có giới hạn hoặc điều kiện dừng. Dùng `limit`, nguồn hữu hạn, hoặc `takeWhile` khi đúng ý nghĩa bài toán để bảo đảm pipeline có thể hoàn thành.

## 9. Song song: gộp thống kê đúng hợp đồng

Các đối tượng `IntSummaryStatistics`, `LongSummaryStatistics` và `DoubleSummaryStatistics` có thể tích lũy bằng `accept(value)` và kết hợp qua `combine(other)`. Khi gọi `parallel().summaryStatistics()`, cơ chế stream có thể phân chia nguồn, tính các thống kê bộ phận rồi gộp chúng. Ta không cần tự tạo một đối tượng thống kê dùng chung giữa các luồng.

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.rangeClosed(1, 100_000)
    .parallel()
    .summaryStatistics();

System.out.println(stats.getCount());   // 100000
System.out.println(stats.getSum());     // 5000050000
System.out.println(stats.getMin());     // 1
System.out.println(stats.getMax());     // 100000
System.out.println(stats.getAverage()); // 50000.5
```

Với các giá trị `int` trong ví dụ, tổng kiểu `long` không tràn, nên kết quả giống nhau khi duyệt tuần tự hay song song. Song song có chi phí chia và gộp dữ liệu, vì thế không có bảo đảm luôn nhanh hơn.

**Không** làm như sau:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

// Ví dụ SAI: cùng một đối tượng mutable bị cập nhật từ nhiều luồng.
IntSummaryStatistics shared = new IntSummaryStatistics();
IntStream.rangeClosed(1, 100_000)
    .parallel()
    .forEach(shared::accept);

// shared có thể cho kết quả sai do cập nhật tranh chấp.
```

Các đối tượng thống kê **có trạng thái thay đổi được và không được thiết kế để cập nhật đồng thời vào một instance chung**. Hãy để `summaryStatistics()` hoặc `Collectors.summarizing*` phối hợp việc tích lũy và kết hợp. Các lambda trước đó như `mapToLong` hoặc `filter` cũng nên không can thiệp nguồn và không dựa vào trạng thái ngoài có thể thay đổi.

Với `double`, phép cộng không có tính kết hợp tuyệt đối do sai số làm tròn. Thứ tự gộp trong pipeline song song có thể ảnh hưởng các bit cuối của `getSum()` và `getAverage()`. Vì vậy, không dùng phép so sánh chính xác bằng `==` cho kết quả số thực nếu yêu cầu cho phép sai số; đồng thời đừng dùng stream song song khi cần một thứ tự tính toán dấu phẩy động cố định.

## 10. Khi nào nên chọn `summaryStatistics`, khi nào không?

| Yêu cầu | Lựa chọn | Lý do |
| --- | --- | --- |
| Cần count, min, max, sum, average trên cùng dữ liệu | `mapToInt/Long/Double(...).summaryStatistics()` | Một pipeline tạo đủ năm đại lượng. |
| Cần các thống kê trên mỗi nhóm | `groupingBy(..., Collectors.summarizingInt/Long/Double(...))` | Phân loại và thống kê trong cùng phép collect. |
| Chỉ cần tổng | `sum()` hoặc `Collectors.summing*` | Không cần duy trì min/max nếu không dùng. |
| Chỉ cần giá trị nhỏ nhất hoặc lớn nhất | `min()` / `max()` | Diễn đạt trực tiếp, trả `Optional*` khi rỗng. |
| Cần median, percentile, độ lệch chuẩn | Thuật toán hoặc collector khác | Bộ `SummaryStatistics` không có sẵn các đại lượng ấy. |
| Cần tổng không bao giờ tràn `long` | `BigInteger` hoặc cộng có kiểm tra | `LongSummaryStatistics` không phát hiện tràn. |
| Cần số tiền thập phân chính xác | Số nguyên đơn vị nhỏ nhất hoặc `BigDecimal` | `double` không biểu diễn mọi số thập phân chính xác. |
| Nguồn không giới hạn | Giới hạn nguồn trước khi tổng hợp | Không thể tổng hợp toàn bộ một dãy vô hạn. |

### Các lỗi thường gặp

1. **Tái sử dụng stream:** gọi `sum()` rồi `average()` trên cùng đối tượng `IntStream` sẽ gây `IllegalStateException`; một terminal `summaryStatistics()` giải quyết nhu cầu nhiều đại lượng cùng lúc.
2. **Không kiểm tra dữ liệu rỗng:** `getMin()`/`getMax()` có thể chứa giá trị khởi tạo đặc biệt; chỉ diễn giải chúng khi `getCount() > 0`.
3. **Giả định `getSum()` luôn chính xác không tràn:** `IntSummaryStatistics` cộng vào `long`, nhưng `LongSummaryStatistics` vẫn có thể tràn `long`.
4. **Dùng `DoubleSummaryStatistics` cho tiền chính xác:** kết quả có thể chịu sai số biểu diễn và cộng số thực.
5. **Tự chia sẻ bộ thống kê giữa các thread:** `IntSummaryStatistics.accept` trên một instance chung không là phương thức cập nhật đồng thời an toàn.
6. **Chọn `summaryStatistics` khi chỉ cần một số duy nhất:** phép toán chuyên dụng `sum`/`min`/`count` có thể rõ ý hơn và giảm trạng thái không cần thiết.
7. **Bỏ qua giá trị bất thường:** `NaN`, `Infinity`, dữ liệu văn bản sai định dạng hoặc `null` có thể làm thống kê sai hoặc ném ngoại lệ.

## 11. Bài tập áp dụng

**Bài 1 — Một lần duyệt.** Cho `List<Integer> scores = Arrays.asList(5, 15, 20, 40)`. Dùng một pipeline với `mapToInt` và `summaryStatistics` để lấy count, sum, min, max, average. Dự đoán lần lượt là **4, 80, 5, 40, 20.0**.

**Bài 2 — Kiểm tra tràn số.** Tạo `IntStream` chứa hai số `1_500_000_000`. So sánh `sum()` với `summaryStatistics().getSum()`, giải thích vì sao chúng khác nhau và vì sao tổng `long` vẫn cần giới hạn.

**Bài 3 — Nhóm dữ liệu.** Cho danh sách nhiệm vụ gồm tên nhóm và thời lượng; dùng `groupingBy` kết hợp `summarizingInt` để thống kê từng nhóm. Xử lý trường hợp một tên nhóm không có trong map mà không truy cập `null.getCount()`.

**Bài 4 — Dữ liệu rỗng.** Tạo `IntStream.empty().summaryStatistics()`, quan sát năm getter và viết logic chỉ hiển thị min/max/average nếu có mẫu. Giải thích vì sao `0.0` của `getAverage()` khi rỗng không đại diện cho trung bình đã đo được.

**Bài 5 — Số thực bất thường.** Dùng `DoubleStream.of(1.0, Double.NaN, 3.0)` để thống kê. Kiểm tra `getSum()`, sau đó thêm điều kiện lọc giá trị hữu hạn và giải thích sự thay đổi số mẫu.

**Ghi nhớ:** Khi cần **nhiều thống kê trên cùng một nguồn**, `summaryStatistics()` và các collector `summarizing*` giúp tính count, sum, min, max, average trong một pipeline, tiết kiệm việc duyệt và biến đổi lặp lại. Hãy luôn kiểm tra dữ liệu rỗng, phạm vi `int`/`long`, sai số `double` và tính an toàn của pipeline song song trước khi sử dụng các giá trị trong quyết định nghiệp vụ.
