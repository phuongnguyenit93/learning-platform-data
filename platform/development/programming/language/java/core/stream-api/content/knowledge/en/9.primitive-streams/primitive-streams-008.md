# Tính `sum`, `average`, `min`, `max` và `summaryStatistics`

> **Chương:** Stream kiểu nguyên thủy  
> **Module:** `JAVA_STREAM_API` — học xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; mở rộng tới grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời hiểu giới hạn về trạng thái, tài nguyên và hiệu năng.

Trong báo cáo doanh thu, điểm thi, nhiệt độ hay số lượng hàng tồn, các yêu cầu thường là **tính tổng**, **trung bình**, **giá trị nhỏ nhất**, **giá trị lớn nhất** và **nhiều thống kê cùng lúc**. Java cung cấp các phép toán kết thúc (*terminal operations*) chuyên dụng trên `IntStream`, `LongStream` và `DoubleStream`. Chúng giúp diễn đạt rõ ý định và xử lý trực tiếp kiểu nguyên thủy, giảm nhu cầu boxing/unboxing so với `Stream<Integer>`, `Stream<Long>` hay `Stream<Double>`.

Mục tiêu của bài:

1. Chọn đúng phép toán và hiểu kiểu trả về của `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()`.
2. Lấy kết quả an toàn khi luồng không có phần tử.
3. Tính nhiều thống kê trong một lần duyệt.
4. Nhận diện sai số số thực, nguy cơ tràn số nguyên và các giới hạn khi xử lý dữ liệu lớn hoặc song song.

## 1. Ba loại primitive stream và cách tạo nguồn

Khác với `Stream<T>` chứa tham chiếu tới đối tượng, primitive stream thao tác trực tiếp trên một trong ba kiểu `int`, `long` hoặc `double`:

| Loại luồng | Dữ liệu phần tử | Ví dụ nguồn | Trường hợp điển hình |
| --- | --- | --- | --- |
| `IntStream` | `int` | `IntStream.of(2, 4, 6)` | Điểm số, số lượng, chỉ số. |
| `LongStream` | `long` | `LongStream.of(100L, 200L)` | Số lượng hoặc tổng lớn hơn miền `int`, mili giây. |
| `DoubleStream` | `double` | `DoubleStream.of(1.5, 2.5)` | Phép đo, giá trị số thực chấp nhận sai số. |

Có nhiều cách đi từ dữ liệu đã có tới primitive stream:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

IntStream fromArray = Arrays.stream(new int[] {5, 10, 15});
IntStream fromList = List.of(5, 10, 15).stream()
        .mapToInt(Integer::intValue);
LongStream orderIds = LongStream.of(1001L, 1002L, 1003L);
DoubleStream temperatures = DoubleStream.of(28.5, 29.0, 30.25);
```

Khi dữ liệu ở dạng đối tượng, `mapToInt`, `mapToLong` và `mapToDouble` trích xuất khóa số:

```java
record Product(String name, int quantity, long revenueCents) {}

List<Product> products = List.of(
        new Product("A", 3, 125_000L),
        new Product("B", 7, 250_000L)
);

int totalQuantity = products.stream()
        .mapToInt(Product::quantity)
        .sum(); // 10

long totalRevenueCents = products.stream()
        .mapToLong(Product::revenueCents)
        .sum(); // 375000
```

Các khai báo ở đoạn trên độc lập và minh họa cú pháp. Ở những đoạn có sử dụng lại `Product`, `products` hoặc biến khác, hãy đặt chúng trong cùng phạm vi khi chạy. Phần 3 có chương trình Java hoàn chỉnh.

**Nguyên tắc vòng đời:** gọi một terminal operation sẽ tiêu thụ Stream. Không gọi `sum()` rồi `average()` trên **cùng một đối tượng** `IntStream`; hãy tạo Stream mới từ nguồn có thể duyệt lại hoặc dùng `summaryStatistics()` nếu cần nhiều giá trị trong một lượt.

## 2. API tổng hợp và kiểu kết quả

| Terminal operation | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- |
| `sum()` | `int` | `long` | `double` |
| `average()` | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` |
| `min()` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `max()` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `summaryStatistics()` | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |

Tất cả là **phép toán kết thúc**. Khi chưa có terminal operation, các bước trung gian như `filter` hoặc `mapToInt` thường chưa thực hiện duyệt nguồn. Khi gọi `sum` hay `summaryStatistics`, pipeline được duyệt để tạo kết quả.

### Tính tổng với `sum()`

```java
int sum = java.util.stream.IntStream.of(5, 10, 15).sum();
// 30

long longSum = java.util.stream.LongStream.of(3_000_000_000L, 4_000_000_000L)
        .sum();
// 7000000000

double doubleSum = java.util.stream.DoubleStream.of(1.5, 2.0, 3.5)
        .sum();
// 7.0
```

`sum()` trả trực tiếp kiểu số. Với nguồn rỗng, `sum()` trả **0** (hoặc `0.0`) vì 0 là phần tử trung hòa của phép cộng.

### Tính trung bình với `average()`

```java
import java.util.OptionalDouble;
import java.util.stream.IntStream;

OptionalDouble avg = IntStream.of(7, 8, 10).average();
System.out.println(avg.orElseThrow()); // 8.333333333333334
```

`average()` trả `OptionalDouble` **cho cả ba loại primitive stream**. Kết quả có thể chứa phần lẻ, kể cả khi nguồn là `IntStream` hoặc `LongStream`. Trên nguồn rỗng, không có trung bình cộng nên kết quả là `OptionalDouble.empty()`, không phải số 0.

### Tìm nhỏ nhất và lớn nhất

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt minimum = IntStream.of(9, 2, 7, 4).min();
OptionalInt maximum = IntStream.of(9, 2, 7, 4).max();

System.out.println(minimum.orElseThrow()); // 2
System.out.println(maximum.orElseThrow()); // 9
```

Trên primitive stream, `min()` và `max()` **không cần `Comparator`** vì chúng dùng thứ tự số học của kiểu nguyên thủy. Nếu cần tìm chính **đối tượng** có giá trị thuộc tính lớn nhất, hãy dùng `Stream<T>.max(Comparator.comparingInt(...))` để giữ lại đối tượng, thay vì `mapToInt(...).max()` chỉ còn trả về số.

## 3. Chương trình Java 17+ hoàn chỉnh: thống kê điểm

Ví dụ dưới đây minh họa cả năm phép toán trên một nguồn `int[]`. Lưu nội dung vào `PrimitiveStatisticsDemo.java`:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.OptionalInt;

public class PrimitiveStatisticsDemo {
    public static void main(String[] args) {
        int[] scores = {12, 18, 24, 30, 36};

        // Mỗi lần Arrays.stream(scores) tạo một Stream mới.
        int sum = Arrays.stream(scores).sum();
        OptionalDouble average = Arrays.stream(scores).average();
        OptionalInt min = Arrays.stream(scores).min();
        OptionalInt max = Arrays.stream(scores).max();

        System.out.println("sum = " + sum);
        System.out.println("average = " + average.orElseThrow());
        System.out.println("min = " + min.orElseThrow());
        System.out.println("max = " + max.orElseThrow());

        // Một lần duyệt cho count, sum, min, max, average.
        IntSummaryStatistics stats = Arrays.stream(scores)
                .summaryStatistics();

        System.out.println("count = " + stats.getCount());
        System.out.println("stats.sum = " + stats.getSum());
        System.out.println("stats.average = " + stats.getAverage());
        System.out.println("stats.min = " + stats.getMin());
        System.out.println("stats.max = " + stats.getMax());
    }
}
```

Đầu ra:

```text
sum = 120
average = 24.0
min = 12
max = 36
count = 5
stats.sum = 120
stats.average = 24.0
stats.min = 12
stats.max = 36
```

Lưu ý điểm khác biệt về **kiểu dữ liệu**: `IntStream.sum()` trả `int`, còn `IntSummaryStatistics.getSum()` trả `long`. Điều này trở nên quan trọng khi tổng các phần tử có thể vượt phạm vi 32-bit.

## 4. `summaryStatistics()`: nhiều chỉ số trong một lần duyệt

Nếu cần cả tổng, trung bình, nhỏ nhất và lớn nhất, gọi bốn terminal operations độc lập trên một nguồn tái sử dụng được sẽ dẫn đến bốn lần duyệt (trong trường hợp tổng quát). `summaryStatistics()` trả về một đối tượng tích lũy **count, sum, min, max và average** khi nguồn được duyệt một lần:

```text
Nguồn dữ liệu
    │
    ▼
 filter / mapToInt     ← các bước trung gian nếu có
    │
    ▼
 summaryStatistics()   ← terminal operation
    │
    ├── count
    ├── sum
    ├── min
    ├── max
    └── average
```

Ba lớp thống kê có các phương thức tương đương nhau:

| Lớp | `getCount()` | `getSum()` | `getMin()` / `getMax()` | `getAverage()` |
| --- | --- | --- | --- | --- |
| `IntSummaryStatistics` | `long` | `long` | `int` | `double` |
| `LongSummaryStatistics` | `long` | `long` | `long` | `double` |
| `DoubleSummaryStatistics` | `long` | `double` | `double` | `double` |

Ví dụ với số lớn:

```java
import java.util.LongSummaryStatistics;
import java.util.stream.LongStream;

LongSummaryStatistics stats = LongStream
        .of(1_000_000_000L, 2_000_000_000L, 3_000_000_000L)
        .summaryStatistics();

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 6000000000
System.out.println(stats.getMin());     // 1000000000
System.out.println(stats.getMax());     // 3000000000
System.out.println(stats.getAverage()); // 2.0E9
```

Với `DoubleStream`, có lớp `DoubleSummaryStatistics` và các getter tương tự:

```java
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

DoubleSummaryStatistics temperatures = DoubleStream
        .of(28.5, 30.0, 29.5)
        .summaryStatistics();

System.out.println(temperatures.getCount());   // 3
System.out.println(temperatures.getSum());     // 88.0
System.out.println(temperatures.getMin());     // 28.5
System.out.println(temperatures.getMax());     // 30.0
System.out.println(temperatures.getAverage()); // 29.333333333333332
```

Giá trị `average` trên `double` là xấp xỉ biểu diễn nhị phân của `88 / 3`; không nên so sánh bình quân số thực bằng `==` trong các yêu cầu cần chính xác tuyệt đối.

### `summaryStatistics` không phải bộ sưu tập phần tử

Đối tượng statistics chỉ lưu các chỉ số tổng hợp, **không giữ danh sách gốc**. Nếu muốn thống kê theo từng nhóm (ví dụ mỗi phòng ban hoặc từng loại sản phẩm), cần phân nhóm bằng `collect(groupingBy(...))` và các downstream collector phù hợp. Đây là bài toán khác với thống kê một dãy primitive duy nhất.

## 5. Stream rỗng: phân biệt “không có dữ liệu” với số 0

Các hành vi trên **nguồn rỗng** rất quan trọng khi một bước `filter` loại hết các phần tử.

| Phép toán | Với `IntStream.empty()` |
| --- | --- |
| `sum()` | `0` |
| `average()` | `OptionalDouble.empty()` |
| `min()` | `OptionalInt.empty()` |
| `max()` | `OptionalInt.empty()` |
| `summaryStatistics().getCount()` | `0` |
| `summaryStatistics().getSum()` | `0L` |
| `summaryStatistics().getMin()` | `Integer.MAX_VALUE` |
| `summaryStatistics().getMax()` | `Integer.MIN_VALUE` |
| `summaryStatistics().getAverage()` | `0.0` |

Các giá trị `getMin()` và `getMax()` của statistics rỗng là **giá trị khởi tạo**, không phải cực trị thực tế. Tương tự, `getAverage() == 0.0` không chứng minh đã có số 0 trong dữ liệu.

```java
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.stream.IntStream;

IntSummaryStatistics emptyStats = IntStream.empty()
        .summaryStatistics();

if (emptyStats.getCount() == 0) {
    System.out.println("Không có dữ liệu để tính cực trị hoặc trung bình");
} else {
    System.out.println("Min: " + emptyStats.getMin());
    System.out.println("Average: " + emptyStats.getAverage());
}

OptionalDouble average = IntStream.empty().average();
System.out.println(average.isPresent()); // false
```

Với `LongSummaryStatistics` rỗng, `getMin()` là `Long.MAX_VALUE`, `getMax()` là `Long.MIN_VALUE`. Với `DoubleSummaryStatistics` rỗng, `getMin()` là `Double.POSITIVE_INFINITY` và `getMax()` là `Double.NEGATIVE_INFINITY`. Trong cả ba trường hợp, **kiểm tra `getCount() > 0`** trước khi diễn giải min/max/average.

### Sử dụng `Optional` khi có thể thiếu kết quả

```java
import java.util.OptionalDouble;
import java.util.stream.IntStream;

OptionalDouble maybeAverage = IntStream.of().average();

// Cho phép lớp gọi biết là không có trung bình:
if (maybeAverage.isPresent()) {
    System.out.println(maybeAverage.getAsDouble());
} else {
    System.out.println("Chưa có điểm");
}

// Chỉ dùng giá trị mặc định 0 khi nghiệp vụ quy định rõ như vậy:
double averageForDashboard = maybeAverage.orElse(0.0);
```

Không dùng `getAsInt()` hoặc `getAsDouble()` khi Optional tương ứng có thể rỗng mà chưa kiểm tra: các phương thức này có thể ném `NoSuchElementException`. Khi dữ liệu bắt buộc phải tồn tại, có thể dùng `orElseThrow()`.

## 6. Tràn số nguyên: `sum()` có thể sai dù từng phần tử hợp lệ

Phép cộng `int` trong Java có miền `[-2^{31}, 2^{31}-1]`. Nếu tổng vượt phạm vi đó, số nguyên bị **tràn (overflow)** mà `IntStream.sum()` không tự ném ngoại lệ.

```java
import java.util.stream.IntStream;

int wrong = IntStream.of(2_000_000_000, 2_000_000_000).sum();
System.out.println(wrong); // -294967296 (tràn int)

long correct = IntStream.of(2_000_000_000, 2_000_000_000)
        .asLongStream()
        .sum();
System.out.println(correct); // 4000000000

long fromStats = IntStream.of(2_000_000_000, 2_000_000_000)
        .summaryStatistics()
        .getSum();
System.out.println(fromStats); // 4000000000
```

`asLongStream()` đổi cách cộng sang `long`. `IntSummaryStatistics` cũng tích lũy tổng bằng `long`, dù `IntStream.sum()` trả `int`. Tuy nhiên, `long` vẫn có giới hạn: `LongStream.sum()` và `LongSummaryStatistics.getSum()` cũng có thể tràn khi tổng vượt phạm vi `long`.

Khi cần **phát hiện** overflow thay vì chỉ tăng miền số, có thể dùng `Math.addExact` cho reduction tuần tự hoặc song song với phép cộng có kiểm tra:

```java
long exact = java.util.stream.LongStream
        .of(9_000_000_000L, 8_000_000_000L)
        .reduce(0L, Math::addExact);
// 17000000000
```

Ví dụ này nằm trong phạm vi `long` nên không ném lỗi. Nếu tổng vượt `long`, `Math.addExact` sẽ ném `ArithmeticException`. Với số nguyên cực lớn, có thể chuyển giá trị sang `BigInteger` và tính bằng `reduce` trên `Stream<BigInteger>`, đổi lại không còn là primitive stream.

## 7. Sai số `double`, NaN, vô cực và số 0 có dấu

Không giống số nguyên, `double` dùng biểu diễn dấu chấm động nhị phân. Nhiều số thập phân không biểu diễn chính xác được, nên `sum()` và `average()` có thể chỉ là **giá trị gần đúng**:

```java
double total = java.util.stream.DoubleStream.of(0.1, 0.2).sum();
System.out.println(total); // thường hiển thị 0.30000000000000004
```

Triển khai `DoubleStream.sum()` có thể dùng kỹ thuật cộng bù (*compensated summation*) để giảm lỗi trong một số trường hợp. Tuy nhiên, thứ tự cộng có thể khác nhau theo cách thực thi và kết quả **không bảo đảm chính xác tuyệt đối**. Tương tự, `DoubleSummaryStatistics` không phải công cụ tính tiền chính xác đến từng đơn vị.

Khi phải tính tiền có quy tắc làm tròn chính xác, nên lưu số tiền theo đơn vị nhỏ nhất dưới dạng số nguyên nếu không thể tràn, hoặc dùng `BigDecimal`:

```java
import java.math.BigDecimal;
import java.util.List;

BigDecimal totalMoney = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20")
).stream().reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(totalMoney); // 0.30
```

Đây là `Stream<BigDecimal>`, không phải `DoubleStream`, vì loại dữ liệu và yêu cầu chính xác quyết định giải pháp phù hợp.

### Các giá trị đặc biệt

`DoubleStream` có một số quy tắc cần biết:

- Nếu luồng chứa `Double.NaN`, `min()` và `max()` sẽ cho kết quả chứa `NaN` theo hợp đồng của các phép toán này.
- Với `+0.0` và `-0.0`, `min()` xem `-0.0` nhỏ hơn `+0.0`; `max()` xem `+0.0` lớn hơn `-0.0`.
- Khi cộng các giá trị vô cực trái dấu hoặc có `NaN`, kết quả `sum` có thể là `NaN`. Cách sắp xếp và cộng `double` ảnh hưởng độ chính xác của giá trị hữu hạn.

```java
import java.util.stream.DoubleStream;

System.out.println(DoubleStream.of(-0.0, +0.0)
        .min().orElseThrow()); // -0.0
System.out.println(DoubleStream.of(-0.0, +0.0)
        .max().orElseThrow()); // 0.0

System.out.println(Double.isNaN(
        DoubleStream.of(2.0, Double.NaN).max().orElseThrow()));
// true
```

Nếu ứng dụng chỉ chấp nhận các giá trị hữu hạn, hãy **quy định chính sách lọc** trước khi thống kê:

```java
double[] measurements = {1.2, Double.NaN, 2.4, Double.POSITIVE_INFINITY};

java.util.DoubleSummaryStatistics finiteStats = java.util.Arrays
        .stream(measurements)
        .filter(Double::isFinite)
        .summaryStatistics();

System.out.println(finiteStats.getCount()); // 2
System.out.println(finiteStats.getSum());   // xấp xỉ 3.6
```

Việc loại `NaN` hoặc `Infinity` thay đổi tập dữ liệu được báo cáo, vì vậy chỉ áp dụng khi quy tắc nghiệp vụ coi chúng là dữ liệu không hợp lệ.

## 8. Ví dụ thực tế: thống kê tồn kho sau khi lọc

Giả sử hệ thống cần thống kê **số lượng của các sản phẩm đang bán**. Kết hợp `filter` (trung gian, lazy) với `mapToInt` (chuyển sang `IntStream`) và `summaryStatistics()`:

```java
import java.util.IntSummaryStatistics;
import java.util.List;

public class InventoryStatisticsDemo {
    record Item(String sku, boolean active, int stock) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A-01", true, 12),
                new Item("A-02", false, 99),
                new Item("B-03", true, 8),
                new Item("B-04", true, 20)
        );

        IntSummaryStatistics stats = items.stream()
                .filter(Item::active)
                .mapToInt(Item::stock)
                .summaryStatistics();

        System.out.println("Số mặt hàng: " + stats.getCount());
        System.out.println("Tổng tồn: " + stats.getSum());
        System.out.println("Ít nhất: " + stats.getMin());
        System.out.println("Nhiều nhất: " + stats.getMax());
        System.out.println("Bình quân: " + stats.getAverage());
    }
}
```

Kết quả:

```text
Số mặt hàng: 3
Tổng tồn: 40
Ít nhất: 8
Nhiều nhất: 20
Bình quân: 13.333333333333334
```

Điểm cần chú ý:

- `filter(Item::active)` bỏ mặt hàng không hoạt động **trước khi** thống kê.
- `mapToInt(Item::stock)` chỉ lấy số tồn kho; từ bước này không còn đối tượng `Item` trong luồng.
- `stats.getCount()` đếm **mặt hàng được giữ lại**, không phải tổng số đơn vị hàng.
- Nếu cần tìm **mặt hàng nào có tồn kho lớn nhất**, dùng `items.stream().filter(Item::active).max(Comparator.comparingInt(Item::stock))`; kết quả là `Optional<Item>`.
- Nếu toàn bộ mặt hàng không hoạt động, kết quả thống kê có `getCount() == 0` và không nên trình bày `getMin()`/`getMax()` như cực trị thật.

## 9. Hiệu năng, nguồn dữ liệu và xử lý song song

### Một lần duyệt cho nhiều chỉ số

Với các phép tổng hợp trên nguồn hữu hạn chưa có kết quả tính sẵn, chi phí điển hình là **O(n)** để duyệt n phần tử. `summaryStatistics()` gộp nhiều phép tích lũy trong một lượt, nên có thể giảm các lần đọc nguồn nếu cùng lúc cần `count`, `sum`, `min`, `max`, `average`.

Đừng suy ra `summaryStatistics()` luôn nhanh hơn mọi phương án khác: nếu chỉ cần tổng, `sum()` trực tiếp thường đơn giản và tránh tính thêm chỉ số không cần. Hãy đo bằng dữ liệu đại diện khi hiệu năng thực sự quan trọng.

### Stream không dùng lại được

```java
import java.util.stream.IntStream;

IntStream stream = IntStream.of(1, 2, 3);
int total = stream.sum(); // 6

// Không hợp lệ: cùng stream đã bị tiêu thụ.
// double avg = stream.average().orElseThrow();
```

Tạo Stream mới từ một `List` hoặc mảng có thể duyệt lại, hoặc dùng `summaryStatistics()` nếu dữ liệu chỉ nên đọc một lần. Với các nguồn gắn tài nguyên như tệp hoặc kết nối I/O, cần tôn trọng vòng đời tài nguyên, đóng luồng đúng chỗ và tránh tự ý duyệt nhiều lần.

### Nguồn vô hạn và short-circuit

`sum`, `average`, `min`, `max`, `summaryStatistics` đều cần **xét hết dữ liệu** của nguồn hữu hạn để trả kết quả tổng quát. Chúng thường không kết thúc nếu nguồn vô hạn không bị giới hạn:

```java
import java.util.stream.IntStream;

// Có điểm dừng rõ ràng:
int total = IntStream.iterate(1, n -> n + 1)
        .limit(5)
        .sum();
System.out.println(total); // 15

// Không được chạy không giới hạn trên nguồn vô hạn:
// IntStream.iterate(1, n -> n + 1).sum();
```

`limit` đứng trước terminal operation tạo phạm vi hữu hạn. Trên một nguồn vô hạn có thể tạo số rất lớn, còn phải cân nhắc overflow như mục 6.

### Song song và độ ổn định kết quả

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.rangeClosed(1, 1_000_000)
        .parallel()
        .summaryStatistics();

System.out.println(stats.getCount()); // 1000000
System.out.println(stats.getSum());   // 500000500000
```

Các phép tổng hợp của Stream có cơ chế kết hợp kết quả nhánh khi chạy song song. Với `int`/`long`, vẫn phải xét khả năng overflow. Với `double`, thay đổi thứ tự cộng làm kết quả thập phân có thể khác nhau giữa cách chạy hoặc giữa các lần thực thi. `parallel()` cũng không mặc nhiên nhanh hơn, vì có chi phí chia nguồn, quản lý tác vụ và gộp kết quả.

**Quy tắc thực hành:** chọn `mapToInt`/`mapToLong`/`mapToDouble` đúng loại dữ liệu; chỉ dùng song song sau khi có số đo hiệu năng và bảo đảm pipeline không có lambda phụ thuộc trạng thái dùng chung.

## 10. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `average().getAsDouble()` trên Stream rỗng | `NoSuchElementException` | Kiểm tra `isPresent()`, dùng `orElse` nếu có chính sách mặc định. |
| Hiểu `getMin() == Integer.MAX_VALUE` là giá trị thật khi rỗng | Báo cáo sai cực trị | Kiểm tra `stats.getCount() > 0`. |
| Dùng `IntStream.sum()` cho tổng vượt `int` | Tràn số nguyên, kết quả sai | Chuyển sang `asLongStream().sum()` hoặc `IntSummaryStatistics.getSum()` nếu vừa miền `long`. |
| Dùng `LongStream.sum()` cho tổng vượt `long` | Có thể tràn số nguyên | Dùng chiến lược `BigInteger`/kiểm tra overflow. |
| Dùng `double` để tính tiền chính xác | Sai số biểu diễn và làm tròn | Dùng đơn vị nguyên với miền số phù hợp hoặc `BigDecimal`. |
| Dùng lại một Stream cho `sum` và `average` | `IllegalStateException` | Tạo Stream mới hoặc dùng `summaryStatistics`. |
| Dùng `mapToInt` khi getter trả `Integer` có thể null | Auto-unboxing có thể ném `NullPointerException` | Lọc `null` hoặc quyết định giá trị mặc định theo nghiệp vụ. |
| Dùng `max()` trên primitive stream khi cần đối tượng gốc | Chỉ có giá trị số, mất thông tin đối tượng | Dùng `Stream<T>.max(Comparator.comparingInt(...))`. |
| Chạy thống kê trên nguồn vô hạn chưa giới hạn | Không kết thúc | Giới hạn nguồn hoặc thiết kế phân đoạn/cửa sổ hữu hạn. |
| Nghĩ `summaryStatistics()` tự phân nhóm | Chỉ có tổng hợp toàn luồng | Dùng collector thích hợp khi cần nhiều nhóm. |

## 11. Tự luyện tập

**Bài 1 — Tính tổng và bình quân.** Cho `int[] numbers = {3, 6, 9, 12}`. Tổng và trung bình là bao nhiêu?

```java
int total = java.util.Arrays.stream(numbers).sum(); // 30
double avg = java.util.Arrays.stream(numbers).average().orElseThrow(); // 7.5
```

**Bài 2 — Lọc trước khi thống kê.** Với `IntStream.of(-3, 2, 5, 8)`, chỉ xét số dương. `min`, `max` và `sum` bằng bao nhiêu?

**Đáp án:** Các phần tử còn lại là `2, 5, 8`; `min = 2`, `max = 8`, `sum = 15`. Có thể lấy chúng cùng lúc bằng:

```java
var stats = java.util.stream.IntStream.of(-3, 2, 5, 8)
        .filter(n -> n > 0)
        .summaryStatistics();
```

**Bài 3 — Dữ liệu rỗng.** `IntStream.empty().sum()` và `IntStream.empty().average()` có giống nhau về ý nghĩa không?

**Đáp án:** Không. Tổng của tập rỗng là `0` theo giá trị trung hòa của phép cộng; trung bình không xác định và được biểu diễn bằng `OptionalDouble.empty()`.

**Bài 4 — Tràn số.** `IntStream.of(2_000_000_000, 2_000_000_000).sum()` trả `4_000_000_000` không?

**Đáp án:** Không, `int` không chứa được giá trị đó; hãy dùng `.asLongStream().sum()` để có `4_000_000_000L`.

**Bài 5 — Chọn API.** Chỉ cần tổng doanh thu chính xác tính bằng số nguyên xu, có nên chuyển sang `DoubleStream` không?

**Đáp án:** Không nhất thiết. Nếu giá trị và tổng nằm trong miền `long`, lưu theo `long` và `mapToLong(...).sum()` là phù hợp hơn. Nếu có nguy cơ vượt `long` hoặc cần quy tắc thập phân phức tạp, cân nhắc `BigInteger`/`BigDecimal` và chính sách làm tròn rõ ràng.

## Ghi nhớ

- `sum()` trả số trực tiếp; `average()` trả `OptionalDouble`; `min()`/`max()` trả Optional chuyên biệt theo kiểu primitive.
- `summaryStatistics()` lấy `count`, `sum`, `min`, `max`, `average` **trong một lần duyệt** và trả về lớp thống kê tương ứng với `int`, `long` hoặc `double`.
- Với thống kê từ luồng rỗng, **kiểm tra `getCount() > 0`** trước khi tin giá trị min/max/average; các getter dùng giá trị khởi tạo.
- `IntStream.sum()` có thể tràn `int`; `IntSummaryStatistics.getSum()` dùng `long`. `DoubleStream` có sai số dấu chấm động, nên không thay thế phép tính tiền chính xác.
- Chọn đúng nguồn primitive, giới hạn nguồn vô hạn và cân nhắc chi phí duyệt cùng độ chính xác trước khi chọn cách tổng hợp hay xử lý song song.
