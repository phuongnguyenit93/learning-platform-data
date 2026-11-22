# IntStream, LongStream và DoubleStream trong Java

**Chủ đề cha:** Primitive Stream. Bài viết giải thích ba primitive stream còn được hỗ trợ đầy đủ trong Java hiện đại: `IntStream`, `LongStream` và `DoubleStream`. Chúng xuất hiện từ Java 8; các ví dụ Java chạy được với JDK 17 trở lên. Các phương thức bổ sung ở phiên bản sau được ghi rõ để không nhầm với API Java 8.

## 1. Primitive Stream là gì và vì sao cần thiết?

`Stream<T>` là luồng tham chiếu tới các đối tượng thuộc kiểu `T`. Generic không thể nhận kiểu nguyên thủy như `int`, `long` hay `double`; vì vậy `Stream<Integer>` không phải `IntStream`. Java có ba specialization giúp làm việc trực tiếp với số nguyên thủy:

| Luồng | Kiểu phần tử | Kiểu wrapper tương ứng | Sử dụng điển hình |
| --- | --- | --- | --- |
| `IntStream` | `int` | `Integer` | Điểm số, số lượng, chỉ số phần tử |
| `LongStream` | `long` | `Long` | Số lượng lớn, timestamp số nguyên, tổng vượt miền `int` |
| `DoubleStream` | `double` | `Double` | Giá trị đo, thống kê số thực, trung bình |

Cả ba đều nằm trong `java.util.stream`, kế thừa `BaseStream` và giữ mô hình pipeline của Stream API: **source → intermediate operations → terminal operation**. Các phương thức như `filter`, `map`, `sorted`, `limit` thường lazy; chúng thực hiện công việc khi có terminal operation như `sum`, `average`, `count` hoặc `toArray`.

**Lợi ích:** giảm nhu cầu boxing (`int` → `Integer`) và unboxing (`Integer` → `int`) trong pipeline số học; có sẵn các terminal operation chuyên biệt như `sum()`, `average()`, `summaryStatistics()`. Tuy nhiên hiệu năng thực tế còn tùy dữ liệu và JVM/JIT; đừng kết luận primitive stream luôn nhanh hơn vòng `for` khi chưa benchmark.

Không có `FloatStream`, `ByteStream` hoặc `BooleanStream` trong Java Stream API. Với `byte`, `short`, `char`, nhiều thao tác số học có thể dùng `IntStream`; với `float` có thể mở rộng thành `double` nếu nghiệp vụ chấp nhận, hoặc dùng các cấu trúc khác khi cần bảo toàn kiểu/độ chính xác.

**Quy tắc vòng đời:** giống object stream, một primitive stream được tiêu thụ **chỉ một lần**. Gọi `sum()` rồi `average()` trên cùng một đối tượng stream là không hợp lệ; muốn tính hai phép độc lập, tạo lại stream từ nguồn hoặc dùng `summaryStatistics()` trong một lượt.

## 2. Tạo các primitive stream

### 2.1. Nguồn thường gặp

| Cách tạo | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- |
| Các giá trị có sẵn | `IntStream.of(1, 2, 3)` | `LongStream.of(1L, 2L)` | `DoubleStream.of(1.5, 2.5)` |
| Rỗng | `IntStream.empty()` | `LongStream.empty()` | `DoubleStream.empty()` |
| Mảng nguyên thủy | `Arrays.stream(int[])` | `Arrays.stream(long[])` | `Arrays.stream(double[])` |
| Builder | `IntStream.builder()` | `LongStream.builder()` | `DoubleStream.builder()` |
| Lặp từ seed | `IntStream.iterate(seed, op)` | `LongStream.iterate(seed, op)` | `DoubleStream.iterate(seed, op)` |
| Từ supplier | `IntStream.generate(supplier)` | `LongStream.generate(supplier)` | `DoubleStream.generate(supplier)` |

Ví dụ `IntStream.generate(() -> 1).limit(3)` sinh ba số 1. `iterate(seed, next)` và `generate(...)` có thể tạo luồng vô hạn; trước `sum`, `toArray` hoặc `forEach` yêu cầu duyệt hết, phải có giới hạn/điều kiện dừng thích hợp.

Từ Java 9 có thêm `iterate(seed, hasNext, next)` để tạo dãy hữu hạn theo điều kiện; `takeWhile` và `dropWhile` cũng có từ Java 9. Đây là các API vẫn áp dụng hôm nay, nhưng không có trong bản Java 8 ban đầu.

### 2.2. Khoảng số nguyên: `range` và `rangeClosed`

`IntStream` và `LongStream` hỗ trợ:

- `range(startInclusive, endExclusive)`: lấy từ start **đến trước** end.
- `rangeClosed(startInclusive, endInclusive)`: lấy **cả** start và end khi start không lớn hơn end.
- `DoubleStream` **không có** hai factory `range` này. Khi cần dãy số thực theo bước, có thể tạo dãy chỉ số từ `IntStream.range(...)` và ánh xạ sang `double`, đồng thời xét sai số tính toán.

Ví dụ:

```java
IntStream.range(2, 6).toArray();       // [2, 3, 4, 5]
IntStream.rangeClosed(2, 6).toArray(); // [2, 3, 4, 5, 6]
LongStream.range(0L, 3L).toArray();    // [0, 1, 2]
```

Ba dòng trên là **đoạn mã minh họa bên trong phương thức**, cần import `IntStream` và `LongStream`. Kết quả chú thích mô tả các mảng trả về. Nếu chỉ cần tổng/đếm một khoảng rất lớn, đừng gọi `toArray()` để đưa mọi phần tử vào bộ nhớ.

### 2.3. Primitive stream từ đối tượng

Khi nguồn là `List<Order>`, dùng `mapToInt(Order::quantity)`, `mapToLong(Order::amount)` hoặc `mapToDouble(Order::weight)` sau `list.stream()`. Phương thức `String.chars()` và `String.codePoints()` cũng trả `IntStream`, nhưng chúng khác nhau ở Unicode: `chars()` là đơn vị mã UTF-16, trong khi `codePoints()` là điểm mã Unicode. Một ký tự bổ sung ngoài BMP chiếm hai đơn vị UTF-16 nên số phần tử có thể khác nhau.

## 3. Intermediate operation: gần giống nhau nhưng có kiểu hàm chuyên biệt

| Tác vụ | `IntStream` | Ghi chú |
| --- | --- | --- |
| Lọc phần tử | `filter(n -> n % 2 == 0)` | Nhận `IntPredicate` |
| Biến đổi cùng kiểu | `map(n -> n * 2)` | Nhận `IntUnaryOperator`, trả `IntStream` |
| Một thành nhiều | `flatMap(n -> IntStream.of(n, -n))` | Hàm sinh `IntStream` |
| Loại trùng | `distinct()` | Giữ các giá trị phân biệt |
| Sắp xếp | `sorted()` | Theo thứ tự tự nhiên của kiểu số |
| Lấy/bỏ giới hạn | `limit(10)`, `skip(10)` | Phục vụ phân đoạn |
| Xử lý tiền tố | `takeWhile(...)`, `dropWhile(...)` | Có từ Java 9 |
| Biến thành đối tượng | `mapToObj(n -> "id-" + n)` | Trả `Stream<String>` |
| Boxing | `boxed()` | Trả `Stream<Integer>` |

`LongStream` và `DoubleStream` có các thao tác tương tự với `LongPredicate`, `DoublePredicate`, `LongUnaryOperator`, `DoubleUnaryOperator`, `LongConsumer`, `DoubleConsumer`. Không nhầm `IntStream.map` với `Stream<T>.map`: phương thức `IntStream.map` **chỉ** trả `IntStream`; khi muốn tạo object hãy gọi `mapToObj`, khi muốn đổi sang kiểu số nguyên thủy khác hãy gọi `mapToLong` hoặc `mapToDouble`.

Các lambda thông thường nên **stateless** và **non-interfering**: đừng sửa source collection đang duyệt và tránh side effect trên trạng thái dùng chung. `peek` chủ yếu hữu ích để quan sát khi debug, không phải cơ chế chạy logic nghiệp vụ chắc chắn trên mọi phần tử.

## 4. Terminal operation và kiểu trả về

| Phương thức | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- |
| `sum()` | `int` | `long` | `double` |
| `average()` | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` |
| `count()` | `long` | `long` | `long` |
| `min()`/`max()` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `findFirst()`/`findAny()` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `summaryStatistics()` | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |
| `toArray()` | `int[]` | `long[]` | `double[]` |

`sum()` trên stream rỗng trả số 0 của kiểu tương ứng, nhưng `average()`, `min()`, `max()` và `findFirst()` trả Optional rỗng khi không có kết quả. Sử dụng `isPresent`, `ifPresent`, `orElse` hoặc `orElseThrow` tùy chính sách nghiệp vụ. Không coi “không có giá trị” và “giá trị hợp lệ bằng 0” là một.

`summaryStatistics()` giúp tính count, min, max, sum và average trong một lượt duyệt. Khi cần nhiều số liệu của cùng nguồn, đây thường là lựa chọn rõ ràng hơn gọi `sum()` rồi `average()` trên một stream đã bị tiêu thụ.

Ngoài các hàm số học, cả ba hỗ trợ `reduce`, `anyMatch`, `allMatch`, `noneMatch`, `forEach` và `forEachOrdered`. Phương thức `collect(supplier, accumulator, combiner)` của primitive stream sử dụng dạng tham số chuyên biệt; **không** gọi `IntStream.collect(Collectors.toList())` trực tiếp. Nếu cần generic `Collector`, hãy dùng `boxed()` hoặc `mapToObj(...)` để nhận `Stream<T>`.

## 5. Ví dụ Java đầy đủ: số nguyên, số nguyên lớn và số thực

Tạo file **`PrimitiveStreamsDemo.java`**:

```java
import java.util.Arrays;
import java.util.stream.Collectors;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveStreamsDemo {
    public static void main(String[] args) {
        int[] scores = {12, 8, 17, 3, 8};

        int oddSum = Arrays.stream(scores)
                .filter(n -> n % 2 != 0)
                .sum();

        int[] sortedUnique = Arrays.stream(scores)
                .distinct()
                .sorted()
                .toArray();

        double average = Arrays.stream(scores)
                .average()
                .orElseThrow();

        System.out.println("Odd sum: " + oddSum);
        System.out.println("Sorted unique: "
                + Arrays.toString(sortedUnique));
        System.out.println("Average: " + average);

        System.out.println("Range: "
                + Arrays.toString(IntStream.range(2, 6).toArray()));
        System.out.println("Closed: "
                + Arrays.toString(IntStream.rangeClosed(2, 6).toArray()));

        long longSum = LongStream.of(
                3_000_000_000L, 4_000_000_000L).sum();
        System.out.println("Long sum: " + longSum);

        double doubleAverage = DoubleStream.of(1.5, 2.0, 2.5)
                .average()
                .orElseThrow();
        System.out.println("Double average: " + doubleAverage);

        String labels = IntStream.range(1, 4)
                .mapToObj(n -> "id-" + n)
                .collect(Collectors.joining(", "));
        System.out.println("Labels: " + labels);
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 PrimitiveStreamsDemo.java
java PrimitiveStreamsDemo
```

**Stdout chính xác:**

```text
Odd sum: 20
Sorted unique: [3, 8, 12, 17]
Average: 9.6
Range: [2, 3, 4, 5]
Closed: [2, 3, 4, 5, 6]
Long sum: 7000000000
Double average: 2.0
Labels: id-1, id-2, id-3
```

Giải thích:

1. Mỗi phép tính từ `scores` tạo một stream mới bằng `Arrays.stream(scores)`. Không gọi hai terminal operations lên cùng đối tượng stream.
2. Lọc số lẻ trong `12, 8, 17, 3, 8` chỉ còn 17 và 3, tổng bằng 20; `distinct().sorted()` cho `3, 8, 12, 17`.
3. Trung bình các điểm bằng 48/5 = 9.6; `average()` trả `OptionalDouble` nên ở ví dụ nguồn không rỗng có thể dùng `orElseThrow()`.
4. `IntStream.range(2,6)` bỏ mốc 6; `rangeClosed(2,6)` bao gồm 6.
5. Hai số 3 tỷ và 4 tỷ nằm trong `long` và tổng vượt miền `int`; đặt hậu tố `L` cho literal số lớn.
6. `mapToObj` chuyển primitive `int` thành `String` để sử dụng collector `joining`.

## 6. Chuyển đổi giữa primitive streams và object streams

| Từ | Sang | Phương thức |
| --- | --- | --- |
| `Stream<T>` | `IntStream` | `mapToInt(ToIntFunction<T>)` |
| `Stream<T>` | `LongStream` | `mapToLong(ToLongFunction<T>)` |
| `Stream<T>` | `DoubleStream` | `mapToDouble(ToDoubleFunction<T>)` |
| `IntStream` | `Stream<Integer>` | `boxed()` |
| `LongStream` | `Stream<Long>` | `boxed()` |
| `DoubleStream` | `Stream<Double>` | `boxed()` |
| `IntStream` | `Stream<R>` | `mapToObj(IntFunction<R>)` |
| `LongStream`/`DoubleStream` | `Stream<R>` | `mapToObj(...)` |
| `IntStream` | `LongStream` | `asLongStream()` hoặc `mapToLong(...)` |
| `IntStream` | `DoubleStream` | `asDoubleStream()` hoặc `mapToDouble(...)` |
| `LongStream` | `DoubleStream` | `asDoubleStream()` hoặc `mapToDouble(...)` |
| `LongStream`/`DoubleStream` | `IntStream` | `mapToInt(...)` và quy tắc chuyển kiểu phù hợp |

`Stream<Integer>.map(i -> i)` vẫn trả `Stream<Integer>`. Để tính tổng bằng `IntStream`, dùng `mapToInt(Integer::intValue)`. Khi dữ liệu thực tế chứa `null`, phép unboxing qua `Integer::intValue` phát sinh `NullPointerException`; phải xử lý dữ liệu thiếu trước khi chuyển.

Tạo file **`PrimitiveConversionsDemo.java`**:

```java
import java.util.List;
import java.util.stream.IntStream;

public class PrimitiveConversionsDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(2, 4, 6);

        int total = values.stream()
                .mapToInt(Integer::intValue)
                .sum();

        List<Integer> boxed = IntStream.rangeClosed(1, 3)
                .boxed()
                .toList();

        System.out.println("Unboxed sum: " + total);
        System.out.println("Boxed list: " + boxed);
    }
}
```

Chạy `javac --release 17 PrimitiveConversionsDemo.java` và `java PrimitiveConversionsDemo`:

```text
Unboxed sum: 12
Boxed list: [1, 2, 3]
```

`boxed()` tạo wrapper `Integer` ở ranh giới cần dùng object collection. `Stream.toList()` có từ Java 16, trả danh sách không sửa được; muốn một `ArrayList` mutable, có thể dùng `boxed().collect(Collectors.toCollection(ArrayList::new))` với import thích hợp.

### 6.1. Đổi kiểu số không phải lúc nào cũng bảo toàn dữ liệu

- `IntStream.asLongStream()` mở rộng `int` sang `long`, giữ nguyên mọi giá trị.
- `IntStream.asDoubleStream()` giữ chính xác mọi giá trị `int` trong `double`.
- `LongStream.asDoubleStream()` có thể mất độ chính xác khi `long` lớn (vượt miền các số nguyên liên tiếp được biểu diễn chính xác trong `double`, khoảng `2^53`). Không dùng phép đổi này cho ID/giá trị cần khớp bit tuyệt đối.
- `DoubleStream.mapToInt(x -> (int) x)` không phải phép làm tròn: ép kiểu Java cắt phần thập phân về 0, giá trị `NaN` chuyển 0, giá trị hữu hạn vượt miền `int` bị chặn về biên. Chọn chính sách làm tròn/từ chối dữ liệu rõ ràng khi cần.
- Chuyển số liệu tài chính yêu cầu thập phân chính xác sang `double` có thể gây sai số; cân nhắc `BigDecimal` hoặc đơn vị nhỏ nhất bằng integer kết hợp kiểm tra overflow.

## 7. Ví dụ nghiệp vụ: tổng số lượng, doanh thu và khối lượng trung bình

Primitive streams thường hữu ích với danh sách record/entity và các phép cộng/đo lường.

Tạo file **`PrimitiveBusinessDemo.java`**:

```java
import java.util.List;

public class PrimitiveBusinessDemo {
    record OrderLine(int quantity, long unitPriceCents, double weightKg) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
                new OrderLine(2, 1_250L, 1.25),
                new OrderLine(3, 2_000L, 1.75)
        );

        int units = lines.stream()
                .mapToInt(OrderLine::quantity)
                .sum();

        long revenueCents = lines.stream()
                .mapToLong(line -> line.quantity() * line.unitPriceCents())
                .sum();

        double averageWeight = lines.stream()
                .mapToDouble(OrderLine::weightKg)
                .average()
                .orElse(0.0);

        System.out.println("Units: " + units);
        System.out.println("Revenue cents: " + revenueCents);
        System.out.println("Average weight: " + averageWeight);
    }
}
```

Chạy `javac --release 17 PrimitiveBusinessDemo.java` và `java PrimitiveBusinessDemo`:

```text
Units: 5
Revenue cents: 8500
Average weight: 1.5
```

`mapToInt` lấy số lượng `int`, `mapToLong` tính doanh thu `long`, `mapToDouble` lấy các giá trị đo thực. `quantity() * unitPriceCents()` được nâng lên `long` do có toán hạng `long`; dù vậy cả nhân lẫn cộng `long` vẫn có khả năng overflow nếu dữ liệu rất lớn. Khi cần an toàn overflow tuyệt đối, dùng `Math.multiplyExact`/`Math.addExact` hoặc thiết kế phép tính có kiểm soát.

Mỗi kết quả lấy từ `lines.stream()` mới vì stream không thể được sử dụng lại.

## 8. Các trường hợp biên quan trọng

### 8.1. Tổng `int` bị overflow; nâng kiểu trước khi cộng

`IntStream.sum()` trả `int` và không tự nâng lên `long`. Nếu tổng `int` vượt phạm vi, kết quả bị overflow theo phép toán số nguyên Java. `LongStream.sum()` cũng có giới hạn `long`; chỉ tăng miền giá trị chứ không triệt tiêu overflow.

Tạo file **`PrimitiveEdgeCasesDemo.java`**:

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveEdgeCasesDemo {
    public static void main(String[] args) {
        int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
        long widened = IntStream.of(Integer.MAX_VALUE, 1)
                .asLongStream()
                .sum();

        boolean hasAverage = IntStream.empty()
                .average()
                .isPresent();

        long exact = 9_007_199_254_740_993L;
        double rounded = LongStream.of(exact)
                .asDoubleStream()
                .findFirst()
                .orElseThrow();

        System.out.println("Int sum: " + overflowed);
        System.out.println("Long sum: " + widened);
        System.out.println("Empty average present: " + hasAverage);
        System.out.println("Long precision kept: "
                + ((long) rounded == exact));
    }
}
```

Chạy:

```bash
javac --release 17 PrimitiveEdgeCasesDemo.java
java PrimitiveEdgeCasesDemo
```

Stdout:

```text
Int sum: -2147483648
Long sum: 2147483648
Empty average present: false
Long precision kept: false
```

Hai tổng dùng hai stream độc lập; `asLongStream()` mở rộng **trước** khi cộng. `OptionalDouble.empty()` phân biệt tập rỗng với trung bình thực sự bằng 0. So sánh cuối cho thấy khi số nguyên `long` lớn hơn `2^53`, ép sang `double` có thể làm mất bit chính xác và không lấy lại được khi ép ngược.

### 8.2. `double`, NaN và số 0 có dấu

`DoubleStream` dựa trên kiểu `double` IEEE 754:

- Phần lớn phân số thập phân không được lưu chính xác trong biểu diễn nhị phân; phép cộng có thể cho giá trị gần đúng. `DoubleStream.sum()` có thể dùng kỹ thuật cải thiện độ chính xác nhưng vẫn chịu quy tắc floating point; không mặc định so sánh mọi kết quả số thực bằng `==`.
- Thứ tự cộng có thể ảnh hưởng kết quả. Với xử lý song song, phép gộp floating-point có thể cho các sai khác ở những bit thấp; cần chọn mức dung sai hoặc thuật toán chính xác phù hợp với nghiệp vụ.
- `DoubleStream.min()` và `max()` trả `NaN` nếu có bất kỳ `NaN` theo hợp đồng API; chúng xem `-0.0` nhỏ hơn `+0.0`.
- `DoubleStream.distinct()` coi các giá trị `NaN` là tương đương khi lọc trùng, còn `-0.0` và `+0.0` là hai giá trị phân biệt theo `Double.compare`.
- Dữ liệu có `Infinity`, `-Infinity` hoặc `NaN` cần kiểm tra rõ trước khi thu thập số liệu; `average()` hay `summaryStatistics()` không thay thế việc xác định chính sách dữ liệu thiếu.
- Tiền tệ/giá trị cần quy tắc làm tròn thập phân chính xác nên dùng `BigDecimal` hoặc minor units dạng integer thay vì `double` thông thường.

### 8.3. Empty stream và các Optional chuyên biệt

`IntStream.empty().sum()` trả 0, nhưng `IntStream.empty().average()` trả `OptionalDouble.empty()`. `IntStream.empty().findFirst()` trả `OptionalInt.empty()`; `LongStream.empty().max()` là `OptionalLong.empty()`. Không gọi `getAsInt/getAsLong/getAsDouble` khi Optional rỗng. `orElse(0)` đơn giản nhưng có thể che mất tình huống nguồn không có dữ liệu; hãy chọn default tùy nghiệp vụ.

## 9. Chọn đúng công cụ theo yêu cầu

| Nhu cầu | Nên cân nhắc | Lưu ý |
| --- | --- | --- |
| Điểm số, đếm/tính với miền `int` | `IntStream` | `sum()` vẫn có thể overflow |
| Tính tổng `int` lớn hơn giới hạn int | `IntStream.asLongStream().sum()` | Mở rộng từng phần tử trước terminal |
| Đếm dữ liệu lớn, tính trên số nguyên `long` | `LongStream` | Cần kiểm tra overflow `long` |
| Giá trị đo và trung bình số thực | `DoubleStream` | Xem xét sai số, NaN, Infinity |
| Tạo dãy số nguyên có index | `IntStream.range` hoặc `LongStream.range` | Phân biệt end-exclusive/end-inclusive |
| Tạo `List<Integer>` từ số nguyên | `IntStream.boxed()` rồi `toList/collect` | Boxing ở điểm cần object |
| Tạo entity/chuỗi từ số nguyên | `mapToObj(...)` | Trả `Stream<R>` |
| Cần nhiều số liệu cùng nguồn | `summaryStatistics()` | Một lần tiêu thụ |
| Tính tiền yêu cầu độ chính xác thập phân | `BigDecimal` hoặc integer minor units | Không dựa vào `double` để bảo đảm chính xác |

`IntStream.average()` và `LongStream.average()` đều trả `OptionalDouble` nên **không cần** chuyển toàn bộ sang `DoubleStream` chỉ để tính trung bình.

## 10. Thứ tự, song song và hiệu năng

- `parallel()` có thể phân chia công việc, nhưng không bảo đảm nhanh hơn; nguồn nhỏ, phép toán rẻ hoặc chi phí phối hợp cao có thể khiến parallel chậm hơn sequential. Benchmark với dữ liệu thực tế.
- Với stream có encounter order, `forEachOrdered` duy trì thứ tự theo quy tắc API; `forEach` trong parallel không bảo đảm thứ tự xuất ra. Điều này áp dụng cho cả primitive và object streams.
- Lambda trong `map`, `filter` và các phép giảm nên stateless/non-interfering. Không cập nhật `ArrayList` hoặc biến đếm thường dùng chung trong `parallel().forEach(...)` vì có thể tạo race.
- `boxed()` chuyển sang object stream, tạo wrapper; thường nên trì hoãn chuyển đổi tới khi API tiếp theo thật sự cần object.
- Primitive stream không phải “array tự động vector hóa” và không có bảo đảm hiệu năng cụ thể; JDK có thể tối ưu tùy pipeline. Với logic đơn giản hoặc truy cập nhiều vị trí theo index, vòng lặp truyền thống đôi khi dễ hiểu và phù hợp hơn.

## 11. Lỗi phổ biến và cách tránh

1. **Dùng `Stream<Integer>.sum()`:** không có phương thức đó; dùng `mapToInt(Integer::intValue).sum()` hoặc collector số học thích hợp.
2. **Giả định `Stream<Integer>` = `IntStream`:** wrapper khác primitive, và chữ ký hàm/terminal operation khác nhau.
3. **Gọi `IntStream.map(...)` để tạo `String`:** `map` giữ kiểu `int`; dùng `mapToObj`.
4. **Quên hậu tố `L` của literal lớn:** số nguyên vượt miền `int` cần biểu thức/literal `long` hợp lệ.
5. **Nhầm `range` với `rangeClosed`:** một phương thức loại bỏ end, một phương thức bao gồm end.
6. **Tái sử dụng stream:** sau `sum` hoặc `average`, tạo stream mới nếu cần kết quả khác.
7. **Tạo stream vô hạn rồi gọi terminal duyệt hết:** dùng `limit` hoặc dãy lặp hữu hạn.
8. **Nhầm `sum` tự chống overflow:** mở rộng `int` sang `long` trước khi cộng, đồng thời kiểm tra trường hợp có thể vượt `long`.
9. **Không xử lý Optional rỗng:** `average`, `min`, `max`, `findFirst` có thể không có kết quả.
10. **Nhầm ép `double` sang `int` với làm tròn:** phép ép kiểu cắt phần thập phân về 0 và có quy tắc riêng cho NaN/giá trị ngoài miền.
11. **Dùng `asDoubleStream` để truyền giá trị `long` cần chính xác:** có thể mất precision; không phù hợp cho khóa định danh lớn.
12. **Dùng `DoubleStream` cho phép tính thập phân kế toán:** áp dụng mô hình `BigDecimal` hoặc integer minor units khi yêu cầu chính xác.
13. **Dùng `Collectors.toList()` trực tiếp trên `IntStream`:** phải `boxed()`/`mapToObj` trước, hoặc dùng `toArray()` nếu cần mảng primitive.
14. **Giả định `forEach` giữ thứ tự trong parallel:** chọn `forEachOrdered` khi thực sự cần, hoặc để terminal reduction quyết định thứ tự an toàn.
15. **Giả định primitive stream luôn nhanh hơn:** đo bằng benchmark phù hợp; tránh boxing thừa nhưng không tối ưu theo cảm giác.

## 12. Tự kiểm tra

1. `IntStream.range(3, 7)` có các phần tử nào? `rangeClosed(3, 7)` khác thế nào?
2. Tại sao `IntStream.of(Integer.MAX_VALUE, 1).sum()` không trả kết quả nguyên dương 2147483648?
3. Một `List<Employee>` cần trung bình mức lương kiểu `long`: nên dùng `mapToLong(Employee::salary).average()` hay `map(Employee::salary).average()`? Vì sao?
4. `IntStream.empty().sum()` và `IntStream.empty().average()` có kết quả thuộc loại nào và tại sao cần phân biệt?
5. Khi cần `List<Integer>` để trả API, `boxed()` nên xuất hiện ở phần nào của pipeline?
6. Vì sao không nên chuyển ID `long` rất lớn sang `double` rồi chuyển ngược?

**Đáp án gợi ý:** (1) 3–6 so với 3–7; (2) overflow `int`, dùng `asLongStream().sum()`; (3) `mapToLong` trả `LongStream` có `average`; (4) 0 so với `OptionalDouble.empty`; (5) khi cần object ở cuối; (6) `double` không biểu diễn chính xác tất cả `long`.

**Ghi nhớ:** `IntStream`, `LongStream` và `DoubleStream` là ba chuyên biệt cho số nguyên thủy, giúp biểu đạt pipeline số học rõ ràng và tránh boxing không cần thiết. Chúng vẫn tuân theo vòng đời Stream: lazy ở intermediate, terminal tiêu thụ một lần; việc chọn kiểu số và cách xử lý overflow, empty result, độ chính xác `double` phải dựa trên yêu cầu nghiệp vụ.

## Tài liệu API chính thức còn áp dụng

- `IntStream`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html
- `LongStream`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/LongStream.html
- `DoubleStream`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html
- `Stream<T>` và `mapToInt`/`mapToLong`/`mapToDouble`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html
- `BaseStream`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/BaseStream.html
- `IntSummaryStatistics`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/IntSummaryStatistics.html
