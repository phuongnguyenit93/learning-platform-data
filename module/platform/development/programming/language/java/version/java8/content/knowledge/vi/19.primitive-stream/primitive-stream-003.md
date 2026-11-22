# sum, average và summaryStatistics trong Java Primitive Stream

## 1. Mục tiêu của bài học

Khi xử lý dữ liệu số bằng Java Stream, ba phép tổng hợp cơ bản là:

- **`sum()`:** tính tổng.
- **`average()`:** tính trung bình cộng; trả một `OptionalDouble` vì Stream có thể không có phần tử.
- **`summaryStatistics()`:** tính **đồng thời** số lượng, tổng, giá trị nhỏ nhất, lớn nhất và trung bình của một Stream số.

Ba phép toán này có mặt trong `IntStream`, `LongStream` và `DoubleStream`, là các API của Java 8 **vẫn được hỗ trợ và sử dụng trong các phiên bản Java hiện đại**. Nội dung bên dưới dùng ví dụ Java 17+ để tận dụng cú pháp hiện hành, đồng thời chỉ rõ API nào đã có từ Java 8.

Sau bài, bạn sẽ biết: chọn kiểu Stream phù hợp, hiểu kiểu dữ liệu trả về, xử lý Stream rỗng, tránh tràn số nguyên và nhầm lẫn độ chính xác của số thực, chuyển từ `Stream<T>` sang primitive stream, và chọn cách tính hiệu quả khi cần nhiều chỉ số.

## 2. Primitive Stream là gì?

Thay vì biểu diễn mọi phần tử bằng đối tượng wrapper (`Integer`, `Long`, `Double`), Java cung cấp ba loại Stream chuyên dụng cho giá trị nguyên thủy:

| Kiểu | Phần tử | Nguồn thường dùng | Điểm mạnh |
| --- | --- | --- | --- |
| `IntStream` | `int` | `IntStream.of(...)`, `Arrays.stream(int[])`, `mapToInt(...)`, `range(...)` | Tránh boxing và có phép tính số nguyên trực tiếp |
| `LongStream` | `long` | `LongStream.of(...)`, `Arrays.stream(long[])`, `mapToLong(...)` | Biểu diễn số nguyên lớn hơn `int` |
| `DoubleStream` | `double` | `DoubleStream.of(...)`, `Arrays.stream(double[])`, `mapToDouble(...)` | Tính toán số thực dấu phẩy động |

Ví dụ:

```java
IntStream.of(2, 4, 6);
LongStream.of(10L, 20L);
DoubleStream.of(1.5, 2.5);
```

*Các dòng trên là biểu thức minh họa; khi dùng trong chương trình cần import các lớp của `java.util.stream` và tiêu thụ Stream bằng một terminal operation.*

Một `List<Integer>` không có sẵn phương thức `sum()`. Bạn cần chuyển `Stream<Integer>` sang `IntStream`:

```java
List<Integer> numbers = List.of(2, 4, 6);
int total = numbers.stream().mapToInt(Integer::intValue).sum();
```

*Đây là đoạn mã đặt trong phương thức/chương trình có import phù hợp; `List.of` có từ Java 9.* `mapToInt` là bước chuyển từ object stream sang primitive stream, cho phép dùng các terminal operation dành cho `int`. Nếu phần tử wrapper là `null`, thao tác unboxing sẽ gây `NullPointerException`; cần xử lý dữ liệu thiếu một cách có chủ đích.

## 3. Chữ ký và kiểu kết quả phải nhớ

| API | `sum()` trả về | `average()` trả về | `summaryStatistics()` trả về |
| --- | --- | --- | --- |
| `IntStream` | `int` | `OptionalDouble` | `IntSummaryStatistics` |
| `LongStream` | `long` | `OptionalDouble` | `LongSummaryStatistics` |
| `DoubleStream` | `double` | `OptionalDouble` | `DoubleSummaryStatistics` |

Các phương thức đều là **terminal operation**: chúng kích hoạt pipeline trung gian và kết thúc việc tiêu thụ Stream. Chỉ sử dụng **một** terminal operation trên một đối tượng Stream. Để tính nhiều đại lượng bằng các phép toán riêng, hãy tạo Stream mới từ cùng nguồn, hoặc dùng `summaryStatistics()` để lấy nhiều chỉ số **trong một lượt duyệt**.

Điểm dễ nhầm:

- `IntStream.sum()` trả về **`int`** và có thể tràn.
- `IntSummaryStatistics.getSum()` trả về **`long`**, có thể chứa tổng lớn hơn giới hạn `int`. Điều này **không** đảm bảo mọi tổng đều không tràn `long`.
- `LongStream.sum()` và `LongSummaryStatistics.getSum()` đều trả về **`long`**; cùng có giới hạn `long`.
- Ba biến thể `average()` luôn trả **`OptionalDouble`**, kể cả Stream đầu vào là số nguyên.
- Các getter `getAverage()` của ba lớp statistics trả **`double`** trực tiếp, dùng `0.0` khi chưa có phần tử; muốn phân biệt rỗng phải kiểm tra `getCount()`.

## 4. Ví dụ tổng quan với `IntStream`

Lưu tệp `PrimitiveIntDemo.java`:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;

public class PrimitiveIntDemo {
    public static void main(String[] args) {
        int[] scores = {3, 6, 9, 12};

        int sum = Arrays.stream(scores).sum();
        OptionalDouble average = Arrays.stream(scores).average();
        IntSummaryStatistics stats =
                Arrays.stream(scores).summaryStatistics();

        System.out.println("sum = " + sum);
        System.out.println("average = " + average.orElseThrow());
        System.out.println("count = " + stats.getCount());
        System.out.println("min = " + stats.getMin());
        System.out.println("max = " + stats.getMax());
        System.out.println("statsSum = " + stats.getSum());
        System.out.println("statsAverage = " + stats.getAverage());
    }
}
```

Biên dịch và chạy:

```bash
javac PrimitiveIntDemo.java
java PrimitiveIntDemo
```

Đầu ra:

```text
sum = 30
average = 7.5
count = 4
min = 3
max = 12
statsSum = 30
statsAverage = 7.5
```

Dữ liệu đầu vào gồm bốn số, tổng 30 và trung bình 30 / 4 = 7,5. `getCount()` có kiểu `long`, `getMin()`/`getMax()` có kiểu `int`, `getSum()` có kiểu `long` và `getAverage()` có kiểu `double`.

Ba lời gọi `Arrays.stream(scores)` tạo **ba đối tượng Stream mới**. Nếu thay bằng một biến `IntStream source = Arrays.stream(scores)` rồi gọi `source.sum()` và `source.average()` liên tiếp, lời gọi thứ hai sẽ thất bại vì Stream đã được tiêu thụ. Với dữ liệu lớn và cần mọi chỉ số, một `summaryStatistics()` vừa rõ nghĩa, vừa tránh yêu cầu duyệt nguồn nhiều lần.

## 5. Ví dụ với `LongStream` và `DoubleStream`

Lưu `PrimitiveLongDoubleDemo.java`:

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;
import java.util.LongSummaryStatistics;

public class PrimitiveLongDoubleDemo {
    public static void main(String[] args) {
        long[] views = {3_000_000_000L, 4_000_000_000L};
        LongSummaryStatistics longStats =
                Arrays.stream(views).summaryStatistics();

        System.out.println("longSum = " + longStats.getSum());
        System.out.println("longAverage = " + longStats.getAverage());
        System.out.println("longCount = " + longStats.getCount());

        double[] timings = {1.5, 2.5, 4.0, 8.0};
        DoubleSummaryStatistics doubleStats =
                Arrays.stream(timings).summaryStatistics();

        System.out.println("doubleSum = " + doubleStats.getSum());
        System.out.println("doubleAverage = " + doubleStats.getAverage());
        System.out.println("doubleMin = " + doubleStats.getMin());
        System.out.println("doubleMax = " + doubleStats.getMax());
    }
}
```

```bash
javac PrimitiveLongDoubleDemo.java
java PrimitiveLongDoubleDemo
```

```text
longSum = 7000000000
longAverage = 3.5E9
longCount = 2
doubleSum = 16.0
doubleAverage = 4.0
doubleMin = 1.5
doubleMax = 8.0
```

`longSum` chứa được 7 tỉ, vượt miền biểu diễn của `int`. `longAverage` hiển thị `3.5E9`, ký pháp khoa học của `3_500_000_000.0`. Các số `1.5`, `2.5`, `4.0` và `8.0` biểu diễn chính xác trong nhị phân, nên đầu ra ví dụ `DoubleStream` ổn định.

**Chọn đúng kiểu:** dữ liệu tiền tệ có thể biểu diễn bằng `long` tính theo đơn vị nhỏ nhất nếu phạm vi đủ rộng, hoặc `BigDecimal` cho phép tính thập phân cần độ chính xác chính xác. `DoubleStream` thích hợp cho phép đo số thực và thống kê khoa học nhưng **không phải** giải pháp mặc định cho tính tiền có yêu cầu không sai số.

## 6. Phân biệt `sum()`, `average()` và `summaryStatistics()`

### 6.1. `sum()`: chỉ cần tổng

Ví dụ `IntStream.of(4, 5, 6).sum()` cho `15`.

Đối với Stream số nguyên, `sum()` là phép reduction chuyên dụng cho phép cộng. Nó thể hiện ý định tốt hơn `reduce(0, Integer::sum)` khi yêu cầu đơn giản là tính tổng. Với `DoubleStream.sum()`, phép tính **không nhất thiết tương đương chính xác về mặt số học máy tính** với `reduce(0.0, Double::sum)` vì JDK được phép sử dụng kỹ thuật cộng bù và thứ tự cộng khác để cải thiện sai số.

Khi nguồn là `IntStream` nhưng tổng dự kiến vượt giới hạn `int`, đổi sang `LongStream` **trước khi tính tổng**:

```java
long safeSum = java.util.stream.IntStream
        .of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
```

Kết quả của biểu thức trên là `2_147_483_648L`. Chỉ ép kiểu **sau khi** đã gọi `IntStream.sum()` không sửa được giá trị đã tràn.

### 6.2. `average()`: xử lý trường hợp không có dữ liệu

`average()` trả `OptionalDouble`:

```java
OptionalDouble avg = java.util.stream.IntStream.of(10, 20, 30)
        .average();
double shown = avg.orElse(0.0);
```

*Đoạn này dùng `OptionalDouble` sau khi import `java.util.OptionalDouble`.* Kết quả `shown` bằng `20.0`.

Chọn giá trị mặc định dựa trên nghiệp vụ: `0.0` là một số hợp lệ, nên nếu “không có dữ liệu” khác “trung bình bằng 0”, hãy dùng `isPresent()`/`ifPresent(...)` hoặc lưu `OptionalDouble` lâu hơn, không vội thay bằng số 0.

**Không nên gọi `OptionalDouble.getAsDouble()`** khi không biết giá trị có tồn tại hay không; với optional rỗng, nó ném `NoSuchElementException`. Trong Java 10+, `orElseThrow()` không cần đối số cũng có thể lấy giá trị hoặc ném ngoại lệ; Java 17+ trong các ví dụ đã dùng phương thức này.

### 6.3. `summaryStatistics()`: nhiều số liệu trong một lần duyệt

Mỗi lớp statistics chứa:

| Getter | Ý nghĩa |
| --- | --- |
| `getCount()` | Số phần tử thực sự được xử lý, kiểu `long` |
| `getSum()` | Tổng: kiểu `long` cho `IntSummaryStatistics`/`LongSummaryStatistics`, kiểu `double` cho `DoubleSummaryStatistics` |
| `getMin()` | Nhỏ nhất; kiểu số tương ứng |
| `getMax()` | Lớn nhất; kiểu số tương ứng |
| `getAverage()` | Trung bình cộng, kiểu `double` |

Các đối tượng `IntSummaryStatistics`, `LongSummaryStatistics`, `DoubleSummaryStatistics` cũng có `accept(value)` để thêm dữ liệu và `combine(other)` để ghép statistics. Tuy nhiên, đối với Stream, nên để `summaryStatistics()` quản lý quá trình thu gom; không tự dùng chung một statistics object giữa các thread.

`summaryStatistics()` tiện khi cần **đồng thời** count/min/max/sum/average. Nếu chỉ cần sum hoặc average, dùng chính `sum()` hoặc `average()` để biểu đạt ý định ngắn gọn.

## 7. Trường hợp Stream rỗng: khác nhau rất quan trọng

Với một primitive stream rỗng:

| Phép toán | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- |
| `sum()` | `0` | `0L` | `0.0` |
| `average()` | `OptionalDouble.empty()` | `OptionalDouble.empty()` | `OptionalDouble.empty()` |
| `summaryStatistics().getCount()` | `0` | `0` | `0` |
| `summaryStatistics().getSum()` | `0L` | `0L` | `0.0` |
| `summaryStatistics().getAverage()` | `0.0` | `0.0` | `0.0` |
| `summaryStatistics().getMin()` | `Integer.MAX_VALUE` | `Long.MAX_VALUE` | `Double.POSITIVE_INFINITY` |
| `summaryStatistics().getMax()` | `Integer.MIN_VALUE` | `Long.MIN_VALUE` | `Double.NEGATIVE_INFINITY` |

`getMin()`/`getMax()` trên statistics rỗng là **giá trị sentinel**, không chứng minh rằng dữ liệu thật có min/max như vậy. Trước khi dùng min/max cho quyết định nghiệp vụ, hãy kiểm tra `getCount() > 0`.

Lưu `PrimitiveEmptyDemo.java`:

```java
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveEmptyDemo {
    public static void main(String[] args) {
        OptionalDouble average = IntStream.empty().average();
        IntSummaryStatistics stats =
                IntStream.empty().summaryStatistics();

        System.out.println("intSum = " + IntStream.empty().sum());
        System.out.println("averagePresent = " + average.isPresent());
        System.out.println("count = " + stats.getCount());
        System.out.println("statsAverage = " + stats.getAverage());
        System.out.println("min = " + stats.getMin());
        System.out.println("max = " + stats.getMax());
        System.out.println("longSum = " + LongStream.empty().sum());
        System.out.println("doubleSum = " + DoubleStream.empty().sum());
    }
}
```

```bash
javac PrimitiveEmptyDemo.java
java PrimitiveEmptyDemo
```

```text
intSum = 0
averagePresent = false
count = 0
statsAverage = 0.0
min = 2147483647
max = -2147483648
longSum = 0
doubleSum = 0.0
```

**Vì sao `summaryStatistics().getAverage()` không trả Optional?** Vì bản thân `summaryStatistics()` luôn trả một đối tượng thống kê, kể cả khi không có phần tử. Muốn thể hiện sự vắng mặt của dữ liệu, dùng `count` để nhận biết trước khi đọc số trung bình.

Lưu ý `IntStream.min()`/`max()` và các phương thức tương ứng của `LongStream`/`DoubleStream` là terminal operation **trả Optional tương ứng** trên Stream trực tiếp. Chúng khác với `stats.getMin()` và `stats.getMax()` là getter trên object thống kê.

## 8. Chuyển `Stream<T>` sang Primitive Stream cho dữ liệu thực

Đầu vào thường là một collection các đối tượng nghiệp vụ. Ví dụ xét điểm kiểm tra của các học viên đã đạt ngưỡng. Lưu `StudentScoreDemo.java` (Java 17+):

```java
import java.util.IntSummaryStatistics;
import java.util.List;

public class StudentScoreDemo {
    record Student(String name, int score) {}

    public static void main(String[] args) {
        List<Student> students = List.of(
                new Student("An", 78),
                new Student("Binh", 92),
                new Student("Chi", 88),
                new Student("Dung", 59)
        );

        IntSummaryStatistics passed = students.stream()
                .filter(student -> student.score() >= 60)
                .mapToInt(Student::score)
                .summaryStatistics();

        System.out.println("passed = " + passed.getCount());
        System.out.println("total = " + passed.getSum());
        System.out.println("min = " + passed.getMin());
        System.out.println("max = " + passed.getMax());
        System.out.println("average = " + passed.getAverage());
    }
}
```

```bash
javac StudentScoreDemo.java
java StudentScoreDemo
```

```text
passed = 3
total = 258
min = 78
max = 92
average = 86.0
```

Giải thích từng bước:

1. `filter(...)` giữ các điểm 78, 92 và 88; điểm 59 bị loại.
2. `mapToInt(Student::score)` tạo `IntStream` từ trường `int score` mà không phải tạo `Stream<Integer>` trung gian.
3. `summaryStatistics()` vừa tính count, sum, min, max, average trong **cùng một pipeline**.
4. Chúng ta nhận được một đối tượng thống kê; không cần tự duy trì biến `total`, `min`, `max` bên ngoài Stream.

`record` là cú pháp ổn định từ Java 16, vì vậy ví dụ nhắm tới Java 17+. Các API `filter`, `mapToInt`, `summaryStatistics` vẫn có từ Java 8 và chưa lỗi thời.

Nếu dữ liệu đã là `long[]`/`double[]`, dùng `Arrays.stream(...)`. Nếu là `List<Long>`/`List<Double>`, dùng lần lượt `mapToLong(Long::longValue)`, `mapToDouble(Double::doubleValue)`. Đừng vô tình gọi `map(...)` để chuyển wrapper rồi mong thấy `sum()` trên `Stream<T>`: phương thức `sum()` chỉ tồn tại ở primitive streams.

## 9. Overflow số nguyên: `IntStream.sum()` và `IntSummaryStatistics.getSum()`

`int` trong Java có giới hạn từ -2.147.483.648 đến 2.147.483.647. Khi tổng vượt phạm vi, phép cộng `int` tràn theo quy tắc số nguyên Java; `sum()` không tự ném ngoại lệ để cảnh báo. Đổi sang `long` **trước** reduction là kỹ thuật thông dụng khi tổng nhiều giá trị `int`.

Lưu `PrimitiveOverflowDemo.java`:

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveOverflowDemo {
    public static void main(String[] args) {
        int wrapped = IntStream.of(Integer.MAX_VALUE, 1).sum();

        long statsSum = IntStream.of(Integer.MAX_VALUE, 1)
                .summaryStatistics().getSum();

        long widened = IntStream.of(Integer.MAX_VALUE, 1)
                .asLongStream().sum();

        long longWrapped = LongStream.of(Long.MAX_VALUE, 1L).sum();

        System.out.println("intSum = " + wrapped);
        System.out.println("statsSum = " + statsSum);
        System.out.println("longSum = " + widened);
        System.out.println("longOverflow = " + longWrapped);
    }
}
```

```bash
javac PrimitiveOverflowDemo.java
java PrimitiveOverflowDemo
```

```text
intSum = -2147483648
statsSum = 2147483648
longSum = 2147483648
longOverflow = -9223372036854775808
```

Ba kết luận từ ví dụ:

- `IntStream.sum()` trả `int` nên đã bị tràn.
- `IntSummaryStatistics.getSum()` cộng `int` vào trạng thái `long`, và `asLongStream().sum()` chuyển phần tử sang `long` trước khi cộng; cả hai cho đúng `2_147_483_648L` trong trường hợp này.
- `long` cũng có giới hạn và vẫn có thể tràn. Nếu tổng có nguy cơ vượt `Long.MAX_VALUE`, cân nhắc `BigInteger`, phép cộng kiểm tra overflow (`Math.addExact`) hoặc thiết kế kiểm soát biên rõ ràng.

Đừng hiểu rằng mọi phép thống kê trên `IntSummaryStatistics` “chống overflow hoàn toàn”: API không kiểm tra overflow của `count`/`sum`. Ngoài ra, số học `double` có dạng sai số khác, phân tích ở phần tiếp theo.

Một ví dụ thực dụng: `IntStream.rangeClosed(1, 1_000_000).sum()` vượt giới hạn `int`. Có thể dùng `IntStream.rangeClosed(1, 1_000_000).asLongStream().sum()` nếu muốn kết quả `500_000_500_000L`.

## 10. Độ chính xác của `double`, `NaN` và vô cực

`DoubleStream` xử lý kiểu IEEE 754 `double`. Nhiều số thập phân, chẳng hạn `0.1`, không thể biểu diễn chính xác tuyệt đối bằng nhị phân. Vì vậy:

- Tổng/trung bình số thực có thể có **sai số làm tròn**. Không so sánh kết quả theo cách yêu cầu bằng nhau tuyệt đối khi nghiệp vụ có dung sai.
- `DoubleStream.sum()` và `DoubleSummaryStatistics.getSum()` có thể dùng kỹ thuật cộng bù để cải thiện độ chính xác, nhưng **không đảm bảo kết quả thập phân chính xác tuyệt đối**.
- Thứ tự nhóm/cộng, đặc biệt trong parallel stream, có thể ảnh hưởng các bit cuối của kết quả. Không phụ thuộc vào việc hai cách reduction khác nhau phải cho cùng biểu diễn bit.
- Nếu có giá trị `Double.NaN`, tổng có thể thành `NaN`; `DoubleSummaryStatistics` xử lý min/max chứa `NaN` theo hợp đồng API. Với vô cực dương/âm, kết quả tổng/trung bình có thể là vô cực hoặc `NaN`.
- `+0.0` và `-0.0` là những giá trị số thực có tính chất đặc biệt. `DoubleSummaryStatistics.getMin()/getMax()` phân biệt dấu của zero theo quy tắc `Double.compare`; không nên tự suy diễn từ phép so sánh `<`/`>` đơn thuần.

Ví dụ với dữ liệu hữu hạn có kết quả dễ kiểm chứng, lưu `PrimitiveDoubleDemo.java`:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

public class PrimitiveDoubleDemo {
    public static void main(String[] args) {
        DoubleSummaryStatistics stats = DoubleStream
                .of(2.0, 4.0, 6.0, 8.0)
                .summaryStatistics();

        System.out.println("count = " + stats.getCount());
        System.out.println("sum = " + stats.getSum());
        System.out.println("average = " + stats.getAverage());
        System.out.println("min = " + stats.getMin());
        System.out.println("max = " + stats.getMax());
        System.out.println("emptyAverage = " +
                DoubleStream.empty().average().isPresent());
    }
}
```

```bash
javac PrimitiveDoubleDemo.java
java PrimitiveDoubleDemo
```

```text
count = 4
sum = 20.0
average = 5.0
min = 2.0
max = 8.0
emptyAverage = false
```

Với bài toán tài chính yêu cầu phép tính thập phân chính xác, thường nên dùng `BigDecimal` trên object stream hoặc tổng số tiền dưới dạng `long` ở đơn vị nhỏ nhất. `BigDecimal` không phải primitive stream; cần thiết kế phép tổng hợp riêng, chẳng hạn `stream.map(Order::amount).reduce(BigDecimal.ZERO, BigDecimal::add)` nếu `amount` là `BigDecimal` hợp lệ. Không tự động làm tròn dữ liệu trước mỗi lần cộng khi chưa có quy tắc nghiệp vụ.

## 11. `average()` với `LongStream`: kiểu số thực và độ chính xác

`LongStream.average()` trả `OptionalDouble`, không trả `OptionalLong`. Nguyên nhân: trung bình của các số nguyên có thể không nguyên. Tuy nhiên, `double` chỉ lưu được khoảng **53 bit độ chính xác số nguyên**; với các `long` rất lớn, việc biểu diễn số trung bình có thể làm mất các chữ số thấp.

Ví dụ tính trung bình lượng truy cập nhỏ vừa phải:

```java
double average = java.util.stream.LongStream
        .of(5L, 10L, 15L)
        .average()
        .orElseThrow();
```

*Đây là đoạn lệnh đặt trong phương thức; `average` nhận được `10.0`.* Nếu cần kết quả **chính xác đến đơn vị nhỏ nhất** hoặc quy tắc làm tròn cụ thể, hãy chuyển sang tổng/đếm kiểu đủ rộng rồi dùng phép chia phù hợp (ví dụ `BigDecimal` với `RoundingMode` được chọn), thay vì giả định `OptionalDouble` giữ mọi chữ số của `long`.

Ngoài ra, `average()` tính trung bình **của những phần tử còn lại sau các bước `filter`/`map`**, không phải trung bình của kích thước nguồn ban đầu. Nếu không có phần tử nào đạt điều kiện lọc thì `OptionalDouble` rỗng.

## 12. So sánh với `Collectors.summarizingInt/Long/Double`

Đôi khi bạn đang có `Stream<Student>` và muốn tính thống kê mà **không nhất thiết chuyển** sang `IntStream`. Java có các collector:

- `Collectors.summarizingInt(ToIntFunction<T>)` → `IntSummaryStatistics`
- `Collectors.summarizingLong(ToLongFunction<T>)` → `LongSummaryStatistics`
- `Collectors.summarizingDouble(ToDoubleFunction<T>)` → `DoubleSummaryStatistics`

Chúng cũng có từ Java 8 và vẫn được hỗ trợ. Sự khác biệt là **nơi thực hiện phép trích xuất dữ liệu số**:

```java
IntSummaryStatistics a = students.stream()
        .mapToInt(Student::score)
        .summaryStatistics();

IntSummaryStatistics b = students.stream()
        .collect(java.util.stream.Collectors.summarizingInt(Student::score));
```

*Đây là snippet dựa trên `Student` và `students` đã được định nghĩa ở chương trình mục 8.* Cả hai cùng thống kê trường `score`. Phương án đầu tạo primitive stream; phương án sau thu thập trực tiếp object stream. Các collector tỏ ra đặc biệt hữu ích khi làm downstream của `groupingBy`, ví dụ thống kê điểm theo từng lớp.

Ví dụ chương trình hoàn chỉnh với collector, lưu `CollectorSummaryDemo.java`:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class CollectorSummaryDemo {
    record Student(String classroom, int score) {}

    public static void main(String[] args) {
        List<Student> students = List.of(
                new Student("A", 80),
                new Student("A", 100),
                new Student("B", 70)
        );

        Map<String, IntSummaryStatistics> byClass =
                students.stream().collect(
                        Collectors.groupingBy(
                                Student::classroom,
                                TreeMap::new,
                                Collectors.summarizingInt(Student::score)
                        )
                );

        byClass.forEach((name, stats) ->
                System.out.println(name + ": count=" + stats.getCount()
                        + ", sum=" + stats.getSum()
                        + ", average=" + stats.getAverage()));
    }
}
```

```bash
javac CollectorSummaryDemo.java
java CollectorSummaryDemo
```

```text
A: count=2, sum=180, average=90.0
B: count=1, sum=70, average=70.0
```

`TreeMap::new` giúp đầu ra theo thứ tự khóa `A` rồi `B`. Khi chỉ cần dữ liệu thống kê toàn bộ, `mapToInt(...).summaryStatistics()` thường trực tiếp hơn. Khi cần **thống kê mỗi nhóm**, `groupingBy(..., summarizingInt(...))` tránh việc duyệt thủ công từng `List` sau khi nhóm.

## 13. Stream song song và phép tổng hợp số

`sum`, `average` và `summaryStatistics` là các terminal reduction được thư viện Stream thiết kế để hoạt động trên cả sequential và parallel stream:

```java
long result = java.util.stream.IntStream
        .rangeClosed(1, 1_000_000)
        .parallel()
        .asLongStream()
        .sum();
```

*Đây là biểu thức độc lập trong một phương thức; kết quả `result` là `500_000_500_000L`.* Với số nguyên không tràn, việc chia thành các phần rồi cộng kết quả con có cùng ý nghĩa. Trong ví dụ này chuyển sang `LongStream` để tránh tràn `int`.

Điều không nên làm:

```java
// Thiết kế sai trong parallel: nhiều thread cập nhật biến mutable dùng chung.
// int[] total = {0};
// values.parallelStream().forEach(x -> total[0] += x);
```

Đoạn trên chỉ minh họa **lỗi thiết kế**: `total[0] += x` không phải phép cộng nguyên tử, nên có thể làm mất cập nhật. Hãy dùng `sum()` hoặc `summaryStatistics()` để thư viện tổ chức reduction đúng hợp đồng.

Đối tượng `IntSummaryStatistics`/`LongSummaryStatistics`/`DoubleSummaryStatistics` **không tự thread-safe** khi được người dùng tự chia sẻ để gọi `accept(...)` song song. Nhưng gọi `parallelStream().collect(Collectors.summarizingInt(...))` là thao tác hợp lệ, vì collector và cơ chế chia/ghép partial result đảm nhận tính đúng đắn; không suy ra rằng có thể tùy tiện dùng cùng một instance statistics ở nhiều thread.

`parallel()` không mặc nhiên nhanh hơn. Với dãy nhỏ hoặc pipeline quá rẻ, chi phí phân chia, scheduling và ghép có thể lớn hơn lợi ích. Hãy đo bằng benchmark với dữ liệu thực, và cân nhắc độ nhạy của số thực với thứ tự cộng.

## 14. Các nhầm lẫn phổ biến

| Tình huống | Cách hiểu/sửa đúng |
| --- | --- |
| Gọi `sum()` sau đó `average()` trên **cùng Stream** | Stream đã tiêu thụ; tạo Stream mới hoặc gọi `summaryStatistics()` một lần |
| Nghĩ `IntStream.sum()` trả về `long` | Nó trả `int`; chuyển `asLongStream()` trước khi cộng khi cần |
| Nghĩ `summaryStatistics().getSum()` luôn tránh overflow | `IntSummaryStatistics` dùng `long` cho tổng, nhưng `long` vẫn có giới hạn |
| Gọi `average().getAsDouble()` khi dữ liệu có thể rỗng | Dùng `isPresent`/`orElse` hoặc chính sách rõ ràng |
| Dùng `stats.getMin()` khi count = 0 | Đó là sentinel, không phải min thực |
| Dùng `Collectors.summarizingInt` như method của `IntStream` | Collector dùng với `Stream<T>.collect(...)`; primitive stream có `summaryStatistics()` |
| Lấy độ chính xác tiền tệ từ `DoubleStream.sum()` | Dùng `long` đơn vị nhỏ nhất hoặc `BigDecimal` theo nghiệp vụ |
| Dùng `peek` với side effect để đếm/tính tổng | Dùng terminal reduction; `peek` là thao tác trung gian và không bảo đảm side effect luôn chạy |
| Gọi `map(Integer::valueOf)` rồi mong `sum()` | `map` trả object stream; cần `mapToInt` hoặc primitive stream nguồn |
| Cố chia đôi kiểu `int`/`long` để lấy `average` chính xác | `average` là `OptionalDouble`; cân nhắc quy tắc làm tròn hoặc big-number arithmetic khi cần |

Nên tách **kiểu kết quả của phép toán** khỏi **kiểu phần tử của Stream**. Đối với số nguyên, đếm và trung bình thường cần kiểu rộng hơn dữ liệu gốc; đối với số thực, cần xem xét độ chính xác và giá trị đặc biệt.

## 15. Bài tập và lời giải có thể chạy

### Bài 1. Thống kê doanh số đạt ngưỡng

Có các khoản doanh số `[10, 20, 40, 50, 5]`. Chỉ giữ các khoản từ `10` trở lên, tính `count`, `sum`, `min`, `max` và `average` bằng đúng **một phép `summaryStatistics()`**. Giải thích tại sao lấy count từ statistics phù hợp hơn dùng kích thước mảng gốc.

### Bài 2. Trung bình của Stream rỗng

Giải thích tại sao `IntStream.empty().average()` khác với `IntStream.empty().summaryStatistics().getAverage()` về khả năng nhận biết dữ liệu rỗng.

### Bài 3. Tổng an toàn khi vượt `int`

Tính tổng từ 1 đến 100.000 bằng `IntStream.rangeClosed(...)`, sau đó chuyển sang kiểu phù hợp để giữ kết quả chính xác. Vì sao chỉ ép kiểu kết quả `(long) intStream.sum()` vẫn không đủ?

Lưu lời giải trong `PrimitivePractice.java`:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.stream.IntStream;

public class PrimitivePractice {
    public static void main(String[] args) {
        int[] sales = {10, 20, 40, 50, 5};

        IntSummaryStatistics stats = Arrays.stream(sales)
                .filter(value -> value >= 10)
                .summaryStatistics();

        OptionalDouble emptyAverage = IntStream.empty().average();

        long oneToHundredThousand = IntStream
                .rangeClosed(1, 100_000)
                .asLongStream()
                .sum();

        System.out.println("count = " + stats.getCount());
        System.out.println("sum = " + stats.getSum());
        System.out.println("min = " + stats.getMin());
        System.out.println("max = " + stats.getMax());
        System.out.println("average = " + stats.getAverage());
        System.out.println("emptyPresent = " + emptyAverage.isPresent());
        System.out.println("rangeSum = " + oneToHundredThousand);
    }
}
```

```bash
javac PrimitivePractice.java
java PrimitivePractice
```

```text
count = 4
sum = 120
min = 10
max = 50
average = 30.0
emptyPresent = false
rangeSum = 5000050000
```

Đáp án bài 1: sau `filter` chỉ còn 4 khoản, nên lấy count từ thống kê (không lấy độ dài 5 của mảng gốc). Bài 2: `OptionalDouble.empty()` biểu thị rõ “không có trung bình”, trong khi `getAverage()` trên stats rỗng là `0.0` và cần kết hợp `getCount() == 0` để biết rỗng. Bài 3: đổi `int` thành `long` **trước khi cộng** nhờ `asLongStream()`; phép `sum` kiểu `int` đã tràn thì ép kiểu sau đó không thể khôi phục tổng.

## 16. Checklist khi áp dụng

- Chỉ cần tổng, trung bình hay đồng thời cả count/min/max/sum/average?
- Đã chọn đúng `IntStream`, `LongStream` hay `DoubleStream` chưa?
- Nếu xuất phát từ `Stream<T>`, tôi có dùng `mapToInt`/`mapToLong`/`mapToDouble` đúng kiểu?
- Stream có thể rỗng sau `filter` không? Tôi đã xử lý `OptionalDouble` và sentinel của statistics?
- Tổng có vượt giới hạn `int`/`long` không? Có cần chuyển kiểu **trước** khi reduction hoặc dùng số lớn?
- Dữ liệu `double` có `NaN`/vô cực/sai số và quy tắc làm tròn nghiệp vụ không?
- Tôi đã tránh dùng lại Stream sau một terminal operation?
- Có cần thống kê theo nhóm bằng `Collectors.summarizingInt/Long/Double`?
- Có thật sự lợi ích khi dùng parallel, và tôi đã tránh side effect/mutable shared state?

## 17. API chính thức vẫn đang áp dụng

- Oracle Java SE 26, `IntStream`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html
- Oracle Java SE 26, `LongStream`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/LongStream.html
- Oracle Java SE 26, `DoubleStream`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html
- Oracle Java SE 26, `IntSummaryStatistics`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/IntSummaryStatistics.html
- Oracle Java SE 26, `LongSummaryStatistics`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/LongSummaryStatistics.html
- Oracle Java SE 26, `DoubleSummaryStatistics`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/DoubleSummaryStatistics.html
- Oracle Java SE 26, `Collectors`, nhóm `summarizingInt/Long/Double`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html

**Điểm cần nhớ:** `sum()` dành cho tổng, `average()` trả `OptionalDouble` để biểu diễn khả năng Stream rỗng, còn `summaryStatistics()` tổng hợp nhiều chỉ số trong một lượt xử lý. Chọn đúng kiểu số và hiểu rõ overflow/độ chính xác quan trọng hơn việc rút gọn cú pháp.