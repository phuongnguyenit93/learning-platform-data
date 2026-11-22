# IntStream, LongStream và DoubleStream trong Java

Trong Java Stream API, `Stream<T>` là một pipeline xử lý đối tượng. Tuy nhiên, dữ liệu số nguyên thủy xuất hiện rất thường xuyên: `int`, `long` và `double`. Để làm việc với những giá trị này mà không phải đóng gói từng phần tử thành `Integer`, `Long`, `Double`, Java cung cấp ba **primitive streams** trong gói `java.util.stream`:

- **`IntStream`**: luồng các giá trị `int`.
- **`LongStream`**: luồng các giá trị `long`.
- **`DoubleStream`**: luồng các giá trị `double`.

Ba kiểu này có nhiều thao tác tương tự object stream: `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`, `skip`, `forEach`, `reduce`. Chúng còn có terminal operations rất tiện cho số học như `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()`.

Lợi ích quan trọng là **tránh boxing/unboxing không cần thiết** và trình bày trực tiếp ý định tính toán số. Tuy nhiên, primitive streams không tự đảm bảo phép cộng không tràn, số thực không sai số, hay chế độ song song luôn nhanh hơn.

Sau bài này, bạn có thể:
1. Chọn đúng `IntStream`, `LongStream`, `DoubleStream` và tạo nguồn từ mảng, khoảng số hoặc các giá trị riêng lẻ.
2. Biến đổi, lọc, cộng, tìm min/max, tính trung bình và thống kê trên dữ liệu số.
3. Chuyển giữa `Stream<T>` và primitive stream, hiểu `boxed()`, `mapToInt`, `mapToLong`, `mapToDouble`.
4. Xử lý kết quả có thể vắng mặt bằng `OptionalInt`, `OptionalLong`, `OptionalDouble`.
5. Nhận biết các bẫy về `range`, `rangeClosed`, boxing, tràn số, độ chính xác dấu phẩy động và terminal operation.

Các chương trình chạy đầy đủ bên dưới được viết cho **JDK 17 trở lên**; mỗi tệp có lệnh `javac`/`java` và stdout xác định.

## 1. Primitive stream khác Stream<T> thế nào?

| Tiêu chí | `Stream<Integer>` | `IntStream` |
| --- | --- | --- |
| Kiểu phần tử | Đối tượng `Integer` | Giá trị nguyên thủy `int` |
| Hàm lọc | `Predicate<Integer>` | `IntPredicate` |
| Hàm biến đổi cùng kiểu | `Function<Integer,Integer>` | `IntUnaryOperator` |
| Tính tổng | Thường dùng `mapToInt(...).sum()` hoặc `reduce` | Có sẵn `sum()` |
| Trung bình | Cần chuyển sang primitive stream hoặc tính riêng | Có `average()` trả `OptionalDouble` |
| Chuyển thành object stream | Đã là object stream | Dùng `boxed()` |
| Khi dữ liệu số lớn | Có thể phát sinh boxing/unboxing | Thường giúp tránh chi phí wrapper |

`LongStream` và `DoubleStream` áp dụng ý tưởng tương tự cho `long` và `double`. Chúng triển khai `BaseStream`, nhưng không phải `Stream<Long>` hay `Stream<Double>` và không thay thế được nhau trực tiếp.

Ví dụ:

```java
IntStream primitive = IntStream.of(1, 2, 3);
Stream<Integer> objects = IntStream.of(1, 2, 3).boxed();
```

Đây là mảnh mã minh họa, cần `import java.util.stream.IntStream;` và `import java.util.stream.Stream;`. `boxed()` biến từng `int` thành `Integer` để đưa vào object stream. Nếu chỉ cần `sum`, không cần boxing.

**Lưu ý kiểu:** `int` và `Integer` khác nhau. Dù autoboxing giúp code thuận tiện, kiểu generic của `Stream<T>` không chấp nhận primitive `int` làm type argument: không thể viết `Stream<int>`.

## 2. Tạo IntStream

Những factory và nguồn thường gặp:

```java
IntStream a = IntStream.of(2, 4, 6);
IntStream b = IntStream.empty();
IntStream c = IntStream.range(1, 5);       // 1, 2, 3, 4
IntStream d = IntStream.rangeClosed(1, 5); // 1, 2, 3, 4, 5
int[] source = {7, 8, 9};
IntStream e = java.util.Arrays.stream(source);
```

Đây là **mảnh mã minh họa**, đặt trong một phương thức và import `java.util.stream.IntStream`. Mỗi biến là **một Stream riêng** có thể tiêu thụ một lần. Hai phương thức `range` và `rangeClosed` có sự khác biệt rất dễ nhầm:

- `IntStream.range(startInclusive, endExclusive)`: gồm đầu trái, **không** gồm đầu phải.
- `IntStream.rangeClosed(startInclusive, endInclusive)`: gồm **cả hai đầu** nếu khoảng có phần tử.

Ví dụ `range(5,5)` rỗng, `rangeClosed(5,5)` có đúng một phần tử 5. Khi đầu trái lớn hơn đầu phải, cả hai trả Stream rỗng, không tự tạo dãy giảm.

Ngoài ra có thể tạo Stream từ phép sinh dữ liệu:

```java
IntStream odds = IntStream.iterate(1, n -> n + 2).limit(4);
IntStream fixed = IntStream.generate(() -> 7).limit(3);
```

`iterate(seed, next)` tạo một dãy theo quy tắc; `generate(supplier)` lấy giá trị từ supplier. Hai nguồn này có thể **không hữu hạn** nếu không đặt điều kiện kết thúc; `limit` bảo đảm đoạn ví dụ chỉ lấy một số phần tử. Từ Java 9, có thêm dạng `iterate(seed, hasNext, next)` để dừng theo predicate:

```java
int[] values = IntStream.iterate(1, n -> n <= 5, n -> n + 2)
        .toArray(); // [1, 3, 5]
```

Trong pipeline này, `hasNext` được kiểm tra để quyết định có phát phần tử tiếp theo hay không. Không thêm `sorted()` hoặc các phép cần toàn bộ dữ liệu vào nguồn vô hạn mà không có cách giới hạn phù hợp.

## 3. Tạo LongStream và DoubleStream

`LongStream` phù hợp cho các phép tính trên `long` và các khoảng số lớn:

```java
LongStream ids = LongStream.of(10L, 20L, 30L);
LongStream sequence = LongStream.rangeClosed(1L, 4L);
long[] source = {100L, 200L};
LongStream fromArray = java.util.Arrays.stream(source);
```

Đây là mảnh mã với `import java.util.stream.LongStream;`. `LongStream.range` và `rangeClosed` hoạt động tương tự phiên bản `IntStream`, nhưng trên miền `long`.

`DoubleStream` dùng cho số thực:

```java
DoubleStream prices = DoubleStream.of(1.5, 2.5, 4.0);
double[] weights = {0.5, 1.0, 1.5};
DoubleStream fromArray = java.util.Arrays.stream(weights);
DoubleStream repeated = DoubleStream.generate(() -> 0.5).limit(3);
```

Đây là mảnh mã minh họa với `import java.util.stream.DoubleStream;`; các tên biến `fromArray` được dùng ở **hai ví dụ độc lập**. `DoubleStream` **không có** các phương thức `range` hoặc `rangeClosed` như `IntStream`/`LongStream`. Nếu cần một dãy số thực tăng đều, có thể tạo chỉ số nguyên rồi chuyển đổi:

```java
double[] steps = IntStream.rangeClosed(0, 3)
        .mapToDouble(i -> i * 0.5)
        .toArray(); // [0.0, 0.5, 1.0, 1.5]
```

Với bước tăng thập phân không biểu diễn chính xác bằng nhị phân, kết quả `double` có thể có sai số làm tròn; ví dụ dùng 0.5 để có kết quả chính xác.

## 4. Những phép xử lý cốt lõi

Các primitive streams cung cấp một nhóm operations gần như tương ứng:

| Mục đích | IntStream | LongStream | DoubleStream |
| --- | --- | --- | --- |
| Lọc | `filter(IntPredicate)` | `filter(LongPredicate)` | `filter(DoublePredicate)` |
| Biến đổi cùng kiểu | `map(IntUnaryOperator)` | `map(LongUnaryOperator)` | `map(DoubleUnaryOperator)` |
| Chuyển sang object stream | `mapToObj(IntFunction<R>)` | `mapToObj(LongFunction<R>)` | `mapToObj(DoubleFunction<R>)` |
| Lấy tổng | `sum(): int` | `sum(): long` | `sum(): double` |
| Giá trị nhỏ nhất | `min(): OptionalInt` | `min(): OptionalLong` | `min(): OptionalDouble` |
| Giá trị lớn nhất | `max(): OptionalInt` | `max(): OptionalLong` | `max(): OptionalDouble` |
| Trung bình | `average(): OptionalDouble` | `average(): OptionalDouble` | `average(): OptionalDouble` |
| Số phần tử | `count(): long` | `count(): long` | `count(): long` |
| Tạo mảng | `toArray(): int[]` | `toArray(): long[]` | `toArray(): double[]` |

Ví dụ `IntStream.rangeClosed(1, 6).filter(n -> n % 2 == 0).sum()` trả **12**, vì các phần tử được giữ là 2, 4, 6. `LongStream.of(5L, 9L).max()` trả `OptionalLong` có giá trị 9. `DoubleStream.of(1.0, 3.0).average()` trả `OptionalDouble` có giá trị 2.0.

Các phép `filter`, `map`, `sorted`, `distinct` là **intermediate operations**: tạo pipeline mới và thường lazy. Các phép `sum`, `average`, `count`, `toArray`, `reduce` là **terminal operations**: kích hoạt xử lý và tiêu thụ Stream.

Vì primitive stream không phải `Stream<T>`, bạn cũng không thể gọi `toList()` trực tiếp trên `IntStream`, `LongStream` hoặc `DoubleStream` trong Java 17. Khi cần `List<Integer>`, `List<Long>` hoặc `List<Double>`, hãy dùng `boxed().toList()`.

## 5. Chương trình Java 17: IntStream từ nguồn đến thống kê

Lưu thành **`IntStreamBasicsDemo.java`**:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.IntStream;

public class IntStreamBasicsDemo {
    public static void main(String[] args) {
        int[] numbers = {2, 3, 4, 5, 6};

        int[] evenSquares = Arrays.stream(numbers)
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .toArray();

        int total = Arrays.stream(numbers).sum();
        double average = Arrays.stream(numbers)
                .average()
                .orElse(-1.0);

        List<Integer> exclusive = IntStream.range(1, 5)
                .boxed()
                .toList();

        List<Integer> inclusive = IntStream.rangeClosed(1, 5)
                .boxed()
                .toList();

        int[] odds = IntStream.iterate(1, n -> n + 2)
                .limit(4)
                .toArray();

        IntSummaryStatistics stats = Arrays.stream(numbers)
                .summaryStatistics();

        System.out.println("evenSquares=" + Arrays.toString(evenSquares));
        System.out.println("sum=" + total);
        System.out.println("average=" + average);
        System.out.println("range=" + exclusive);
        System.out.println("rangeClosed=" + inclusive);
        System.out.println("odds=" + Arrays.toString(odds));
        System.out.println("stats=" + stats.getCount() + "/"
                + stats.getMin() + "/" + stats.getMax());
    }
}
```

Lệnh chạy với JDK 17+:

```bash
javac -encoding UTF-8 IntStreamBasicsDemo.java
java IntStreamBasicsDemo
```

**Stdout chính xác:**

```text
evenSquares=[4, 16, 36]
sum=20
average=4.0
range=[1, 2, 3, 4]
rangeClosed=[1, 2, 3, 4, 5]
odds=[1, 3, 5, 7]
stats=5/2/6
```

Giải thích:
1. Mảng `numbers` gồm 2, 3, 4, 5, 6. Lọc số chẵn được 2, 4, 6 rồi bình phương thành 4, 16, 36.
2. `sum()` trả tổng 20; `average()` trả `OptionalDouble` chứa 4.0. Ở đây `orElse(-1.0)` chỉ là chính sách fallback cho trường hợp không có phần tử.
3. `range(1,5)` không gồm 5; `rangeClosed(1,5)` có 5. `boxed()` biến luồng `int` thành `Stream<Integer>`.
4. `iterate(...).limit(4)` chỉ lấy bốn số lẻ đầu, tránh pipeline vô hạn.
5. `summaryStatistics()` gom các thống kê `count`, `sum`, `min`, `max`, `average` trong một terminal operation. Ví dụ chỉ in ba chỉ số để stdout ngắn gọn, nhưng các getter khác vẫn có sẵn.

## 6. LongStream: xử lý long và giảm rủi ro tràn int

`LongStream` có các factory và terminal operations tương tự IntStream, nhưng làm việc với kiểu `long`. Nó thường phù hợp khi giá trị, phép nhân hoặc tổng có thể vượt miền `int`.

```java
long sum = LongStream.of(2_000_000_000L, 2_000_000_000L)
        .sum(); // 4_000_000_000L
```

Đây là mảnh mã cần `import java.util.stream.LongStream;`. Nếu thay bằng `IntStream.of(2_000_000_000, 2_000_000_000).sum()`, phép cộng `int` sẽ tràn theo quy tắc số nguyên Java và **không** cho kết quả 4 tỉ.

### Chương trình Java 17: LongStream và reduction

Lưu thành **`LongStreamDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class LongStreamDemo {
    public static void main(String[] args) {
        long[] squares = LongStream.rangeClosed(1L, 4L)
                .map(value -> value * value)
                .toArray();

        long bigSum = LongStream.of(2_000_000_000L, 2_000_000_000L)
                .sum();

        long exactIntPromoted = IntStream.of(
                        2_000_000_000,
                        2_000_000_000)
                .asLongStream()
                .sum();

        long product = LongStream.rangeClosed(1L, 4L)
                .reduce(1L, (left, right) -> left * right);

        List<Long> boxed = LongStream.of(10L, 20L, 30L)
                .boxed()
                .toList();

        System.out.println("squares=" + Arrays.toString(squares));
        System.out.println("bigSum=" + bigSum);
        System.out.println("promotedSum=" + exactIntPromoted);
        System.out.println("product=" + product);
        System.out.println("boxed=" + boxed);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 LongStreamDemo.java
java LongStreamDemo
```

**Stdout chính xác:**

```text
squares=[1, 4, 9, 16]
bigSum=4000000000
promotedSum=4000000000
product=24
boxed=[10, 20, 30]
```

`asLongStream()` chuyển từng `int` thành `long` **trước khi cộng**, nên ví dụ cho tổng 4 tỉ. Đây là khác biệt quan trọng với việc tính tổng bằng `int` rồi mới cast kết quả: khi tràn đã xảy ra, cast sau đó không khôi phục giá trị đúng.

`reduce(1L, (a,b) -> a*b)` dùng phần tử đơn vị 1 và phép nhân. Ở ví dụ nhỏ này kết quả là `1×2×3×4 = 24`. Trên dữ liệu lớn, phép nhân `long` vẫn có thể tràn; dùng `long` **không đồng nghĩa** tránh được mọi trường hợp tràn số.

## 7. DoubleStream: tính toán double và trung bình

`DoubleStream` phục vụ phép toán với `double`. Các terminal operations `sum`, `average`, `summaryStatistics` rất hữu ích cho số liệu đo lường.

### Chương trình Java 17: thống kê DoubleStream

Tạo tệp **`DoubleStreamStatsDemo.java`**:

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

public class DoubleStreamStatsDemo {
    public static void main(String[] args) {
        double[] measurements = {2.0, 4.0, 6.0};

        DoubleSummaryStatistics stats = Arrays.stream(measurements)
                .summaryStatistics();

        double[] halves = Arrays.stream(measurements)
                .map(value -> value / 2.0)
                .toArray();

        double greaterThanThree = Arrays.stream(measurements)
                .filter(value -> value > 3.0)
                .sum();

        double mean = DoubleStream.of(1.0, 2.0, 3.0)
                .average()
                .orElse(-1.0);

        System.out.println("halves=" + Arrays.toString(halves));
        System.out.println("filteredSum=" + greaterThanThree);
        System.out.println("count=" + stats.getCount());
        System.out.println("sum=" + stats.getSum());
        System.out.println("min=" + stats.getMin());
        System.out.println("max=" + stats.getMax());
        System.out.println("average=" + stats.getAverage());
        System.out.println("mean=" + mean);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 DoubleStreamStatsDemo.java
java DoubleStreamStatsDemo
```

**Stdout chính xác:**

```text
halves=[1.0, 2.0, 3.0]
filteredSum=10.0
count=3
sum=12.0
min=2.0
max=6.0
average=4.0
mean=2.0
```

Ba phép `sum`, `average`, `summaryStatistics` đều là terminal operations; không thể gọi liên tiếp trên **cùng** Stream đã tiêu thụ. Trong ví dụ trên, mỗi phép tạo nguồn mới từ mảng/giá trị ban đầu.

### Lưu ý về số thực

`double` là kiểu dấu phẩy động nhị phân, không biểu diễn chính xác mọi số thập phân. Do đó phép cộng dồn có thể xuất hiện sai số. Với dữ liệu song song, phép cộng có thể được nhóm theo thứ tự khác; đừng yêu cầu mọi cách tính phải cho cùng kết quả ở mức bit.

Nếu bài toán cần chính xác theo thang số tiền (ví dụ hai chữ số thập phân), cân nhắc `BigDecimal` hoặc đơn vị nguyên thích hợp. `DoubleStream` phù hợp cho nhiều phép tính đo lường, thống kê, khoa học, nhưng không tự giải quyết chính sách làm tròn nghiệp vụ.

## 8. Chuyển đổi giữa object stream và primitive streams

Đây là điểm rất quan trọng vì phần lớn API nghiệp vụ bắt đầu từ `List<T>`, không phải mảng primitive.

| Nguồn | Chuyển đổi | Kiểu kết quả |
| --- | --- | --- |
| `Stream<String>` | `.mapToInt(String::length)` | `IntStream` |
| `Stream<String>` | `.mapToLong(Long::parseLong)` | `LongStream` |
| `Stream<String>` | `.mapToDouble(Double::parseDouble)` | `DoubleStream` |
| `IntStream` | `.boxed()` | `Stream<Integer>` |
| `LongStream` | `.boxed()` | `Stream<Long>` |
| `DoubleStream` | `.boxed()` | `Stream<Double>` |
| `IntStream` | `.asLongStream()` | `LongStream` |
| `IntStream` | `.asDoubleStream()` | `DoubleStream` |
| `LongStream` | `.asDoubleStream()` | `DoubleStream` |
| `IntStream` | `.mapToObj(n -> "ID-" + n)` | `Stream<String>` |

Ở đây, `Long::parseLong` nhận `String` và trả primitive `long`; nếu chuỗi đầu vào sai định dạng, lời gọi có thể ném `NumberFormatException`. Primitive stream chỉ giúp mô tả và xử lý dữ liệu, không tự biến lỗi parse thành giá trị hợp lệ.

Các chuyển đổi **không hoàn toàn đảo ngược về mặt thông tin**:
- `IntStream.asLongStream()` chuyển `int` sang `long` không mất giá trị.
- `IntStream.asDoubleStream()` giữ chính xác mọi giá trị `int` vì `double` có đủ độ chính xác cho miền `int`.
- `LongStream.asDoubleStream()` **có thể mất chính xác** với `long` lớn (đặc biệt vượt 2^53), vì `double` không biểu diễn chính xác mọi số nguyên 64-bit.
- Chuyển từ `double` sang `int` hoặc `long` bằng phép cast hoặc `mapToInt`/`mapToLong` cần cân nhắc phần thập phân, NaN, vô cực và quy tắc chuyển đổi số của Java.

## 9. Chương trình Java 17: mapToInt, boxed, asLongStream, mapToObj

Lưu thành **`PrimitiveStreamConversionsDemo.java`**:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class PrimitiveStreamConversionsDemo {
    public static void main(String[] args) {
        List<String> words = List.of("Java", "Stream", "API");

        int letters = words.stream()
                .mapToInt(String::length)
                .sum();

        List<Integer> lengths = words.stream()
                .mapToInt(String::length)
                .boxed()
                .toList();

        List<String> labels = IntStream.rangeClosed(1, 3)
                .mapToObj(number -> "ID-" + number)
                .toList();

        long fromString = Stream.of("10", "20", "30")
                .mapToLong(Long::parseLong)
                .sum();

        long promotedSum = IntStream.rangeClosed(1, 3)
                .asLongStream()
                .sum();

        double mean = LongStream.of(2L, 4L, 6L)
                .asDoubleStream()
                .average()
                .orElse(-1.0);

        System.out.println("letters=" + letters);
        System.out.println("lengths=" + lengths);
        System.out.println("labels=" + labels);
        System.out.println("parsedSum=" + fromString);
        System.out.println("promotedSum=" + promotedSum);
        System.out.println("mean=" + mean);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 PrimitiveStreamConversionsDemo.java
java PrimitiveStreamConversionsDemo
```

**Stdout chính xác:**

```text
letters=13
lengths=[4, 6, 3]
labels=[ID-1, ID-2, ID-3]
parsedSum=60
promotedSum=6
mean=4.0
```

Ví dụ cho thấy `mapToInt` trả luồng `int` có `sum()`; `boxed()` biến luồng số thành Stream object để dùng `toList()`; `mapToObj` tạo object tùy ý từ primitive, không bắt buộc là wrapper. Với `LongStream.asDoubleStream()`, các số nhỏ 2, 4, 6 được biểu diễn chính xác và có trung bình 4.0.

## 10. OptionalInt, OptionalLong và OptionalDouble

Vì `min`, `max`, `findFirst`, `findAny` hoặc `average` có thể không có kết quả khi Stream rỗng, API không thể luôn trả một primitive trực tiếp. Nó dùng các container chuyên biệt:

- `OptionalInt`: có `getAsInt()`, `orElse(int)`, `isPresent()`, `isEmpty()`.
- `OptionalLong`: có `getAsLong()`, `orElse(long)`, `isPresent()`, `isEmpty()`.
- `OptionalDouble`: có `getAsDouble()`, `orElse(double)`, `isPresent()`, `isEmpty()`.

Ví dụ:

```java
OptionalInt firstEven = IntStream.of(3, 4, 5)
        .filter(n -> n % 2 == 0)
        .findFirst(); // chứa 4

OptionalLong missingLong = LongStream.empty().max(); // rỗng
OptionalDouble emptyAverage = DoubleStream.empty().average(); // rỗng
```

Đây là mảnh mã minh họa cần import các lớp từ `java.util` và `java.util.stream`. Không gọi `getAsInt()`, `getAsLong()` hay `getAsDouble()` **tùy tiện** khi chưa chắc có giá trị: các phương thức đó ném `NoSuchElementException` khi Optional chuyên biệt rỗng. Dùng `orElse`, `ifPresent`, `orElseThrow` hoặc kiểm tra trạng thái phù hợp.

### Trường hợp Stream rỗng

| Terminal operation | Kết quả cho Stream nguyên thủy rỗng |
| --- | --- |
| `sum()` | `0`, `0L` hoặc `0.0` tùy kiểu |
| `count()` | `0L` |
| `average()` | `OptionalDouble.empty()` |
| `min()`, `max()` | Optional chuyên biệt rỗng |
| `findFirst()`, `findAny()` | Optional chuyên biệt rỗng |
| `reduce(identity, op)` | `identity` |
| `reduce(op)` | Optional chuyên biệt rỗng |
| `summaryStatistics()` | Đối tượng statistics có `count == 0`, getter min/max có giá trị sentinel riêng của class |

**Đừng coi `sum() == 0` là bằng chứng luồng không có phần tử.** Một luồng có các số đối nhau cũng có thể cho tổng 0. Khi cần biết có phần tử hay không, dùng `count`, `findAny` hoặc một thiết kế kết quả phù hợp.

### Chương trình Java 17: fallback trên các Optional chuyên biệt

Lưu thành **`PrimitiveOptionalDemo.java`**:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveOptionalDemo {
    public static void main(String[] args) {
        OptionalInt firstOdd = IntStream.of(2, 4, 5)
                .filter(n -> n % 2 != 0)
                .findFirst();

        OptionalLong maxMissing = LongStream.empty().max();
        OptionalDouble avgMissing = DoubleStream.empty().average();

        System.out.println("firstOdd=" + firstOdd.orElse(-1));
        System.out.println("maxMissing=" + maxMissing.orElse(-1L));
        System.out.println("avgMissing=" + avgMissing.orElse(-1.0));
        System.out.println("sumEmpty=" + IntStream.empty().sum());
        System.out.println("countEmpty=" + LongStream.empty().count());
        System.out.println("minPresent=" + IntStream.of(9, 3, 7)
                .min().isPresent());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 PrimitiveOptionalDemo.java
java PrimitiveOptionalDemo
```

**Stdout chính xác:**

```text
firstOdd=5
maxMissing=-1
avgMissing=-1.0
sumEmpty=0
countEmpty=0
minPresent=true
```

Trong ví dụ, `firstOdd` chứa số 5, `maxMissing` và `avgMissing` rỗng. Các fallback `-1`, `-1L`, `-1.0` chỉ là **quy ước minh họa**; ứng dụng thật cần chọn fallback không gây nhầm với dữ liệu hợp lệ, hoặc dùng exception/kết quả có trạng thái nếu cần phân biệt chính xác.

## 11. reduce và parallel trên primitive streams

Các primitive streams hỗ trợ `reduce`, ví dụ:

```java
int sum = IntStream.rangeClosed(1, 5)
        .reduce(0, Integer::sum); // 15

long product = LongStream.rangeClosed(1L, 4L)
        .reduce(1L, (a, b) -> a * b); // 24
```

Mỗi đoạn là mảnh mã đặt trong phương thức. Với identity và toán tử phù hợp, `reduce` gộp phần tử thành một kết quả. `sum()` thường diễn đạt ý định cộng rõ ràng hơn `reduce(0, Integer::sum)`.

Bạn có thể chọn `parallel()`:

```java
long sum = LongStream.rangeClosed(1L, 1_000L)
        .parallel()
        .sum(); // 500500L
```

**Không phải phép reduce nào cũng thích hợp để chạy song song.** Toán tử gộp nên có tính **kết hợp (associative)** và identity đúng, không phụ thuộc vào shared mutable state. Ví dụ phép trừ không kết hợp, nên `reduce(0, (a,b) -> a-b)` có thể trả kết quả khác giữa sequential và parallel.

Với `double`, kết quả làm tròn có thể khác khi chia/gộp trên nhiều thread. Parallel stream cũng có overhead: dữ liệu ít hoặc phép toán đơn giản như cộng vài trăm số có thể chậm hơn sequential. Hãy đo trên workload thực tế thay vì mặc định thêm `parallel()` luôn có lợi.

## 12. Tràn số nguyên và độ chính xác dấu phẩy động

### 12.1. IntStream.sum() trả int

Ví dụ:

```java
int wrong = IntStream.of(2_000_000_000, 2_000_000_000).sum();
// Java int tràn, kết quả là -294967296

long correct = IntStream.of(2_000_000_000, 2_000_000_000)
        .asLongStream()
        .sum(); // 4000000000L
```

Cả hai dòng là mảnh mã hợp lệ trong phương thức. `asLongStream()` làm phép mở rộng kiểu **trước phép cộng**, nên ví dụ cho đúng tổng trên miền `long`. Đừng tính xong tổng `int` rồi mới cast sang `long` để hy vọng sửa được phần tràn.

### 12.2. LongStream vẫn có giới hạn

`long` có miền giá trị lớn hơn `int` nhưng không vô hạn; phép cộng hoặc nhân long vẫn có thể tràn. Nếu bài toán cần số nguyên không giới hạn miền `long`, có thể dùng `BigInteger` trong object stream hoặc thuật toán phù hợp.

### 12.3. DoubleStream không phải phép tính thập phân chính xác tuyệt đối

Ví dụ `0.1 + 0.2` có thể không so sánh bằng `0.3` khi dùng `double`. `DoubleStream.sum()` và `average()` hỗ trợ tính tổng/trung bình nhưng vẫn theo đặc tính số thực IEEE 754. Nếu cần so sánh gần đúng, xác định ngưỡng sai số phù hợp; nếu cần số tiền chính xác theo quy tắc thập phân, cân nhắc `BigDecimal` thay vì `DoubleStream`.

Đừng xem `DoubleStream.of(0.1, 0.2).sum() == 0.3` là một phép kiểm thử tốt cho mọi JDK và mọi cách tính; nội dung cần kiểm thử là **độ chính xác trong ngưỡng nghiệp vụ**, không phải một mệnh đề về bit representation.

### 12.4. Độ chính xác khi chuyển long thành double

`LongStream.asDoubleStream()` thuận tiện cho average nhưng có thể mất phần thông tin nguyên khi `long` rất lớn. `double` không thể biểu diễn chính xác mọi số nguyên ngoài phạm vi độ chính xác 53 bit của phần định trị. Nếu tuyệt đối không được mất một đơn vị ở số ID lớn, **đừng chuyển ID sang double chỉ để xử lý nhanh hơn**.

## 13. Những lỗi phổ biến

1. **Viết `Stream<int>`:** generic type parameter phải là reference type; chọn `IntStream`.
2. **Gọi `IntStream.toList()`:** primitive stream không có method này trong Java 17; dùng `boxed().toList()`.
3. **Nhầm `range` và `rangeClosed`:** một bên không gồm end, một bên gồm end.
4. **Tưởng `DoubleStream.range` tồn tại:** không có; tạo chỉ số từ IntStream rồi `mapToDouble`.
5. **Gọi terminal hai lần trên cùng một Stream:** Stream thường chỉ được tiêu thụ một lần.
6. **Dùng `sum()` của IntStream cho tổng có thể vượt int:** tổng có thể tràn; mở rộng sang LongStream trước.
7. **Cho rằng LongStream không bao giờ tràn:** `long` cũng có miền hữu hạn.
8. **Gọi `getAsInt()` hoặc `getAsDouble()` trên Optional rỗng:** gây `NoSuchElementException`.
9. **Cho rằng average trên Stream rỗng trả 0.0:** nó trả `OptionalDouble.empty()`.
10. **Nhầm `boxed()` với `mapToObj`:** `boxed()` tạo wrapper của primitive; `mapToObj` cho phép tạo object kiểu tùy ý.
11. **Dùng `map` thay `mapToInt` từ `Stream<String>`:** `map(String::length)` trả object stream của Integer, không phải IntStream.
12. **Cho rằng DoubleStream dùng cho tiền tệ chính xác:** số thực nhị phân có sai số làm tròn.
13. **Tạo `generate` vô hạn rồi gọi `sum` không giới hạn:** pipeline có thể không kết thúc.
14. **Đổi sang `parallel()` mà phép gộp không kết hợp:** kết quả có thể sai/không xác định theo mong đợi.
15. **Cho rằng không boxing nghĩa là luôn nhanh:** hiệu năng còn phụ thuộc workload, JIT, cấp phát, boxing thực tế và thuật toán; hãy benchmark.
16. **Dùng primitive stream để biểu diễn null:** các phần tử primitive không thể null; nếu nguồn có wrapper nullable, xác định chính sách lọc/đổi trước khi unbox.
17. **Dùng asDoubleStream cho số nguyên long lớn cần chính xác:** chuyển đổi có thể mất thông tin.

## 14. Lựa chọn nhanh theo nhu cầu

| Bài toán | API phù hợp | Ý chính |
| --- | --- | --- |
| Tạo các số nguyên từ 0 đến n-1 | `IntStream.range(0,n)` | End exclusive |
| Tạo các số nguyên từ 1 đến n | `IntStream.rangeClosed(1,n)` | End inclusive |
| Tính tổng các giá trị int, chắc chắn không tràn | `IntStream.sum()` | Kết quả int |
| Cộng nhiều int có thể vượt miền int | `IntStream.asLongStream().sum()` | Mở rộng trước cộng |
| Xử lý các ID kiểu long | `LongStream` | Tránh ép hẹp về int |
| Thống kê giá trị đo kiểu double | `DoubleStream.summaryStatistics()` | Đếm, tổng, min, max, avg |
| Tính tổng độ dài chuỗi | `words.stream().mapToInt(String::length).sum()` | Đổi object stream sang primitive |
| Trả danh sách số nguyên | `IntStream.boxed().toList()` | Trở về object stream |
| Phát biểu kết quả min/max có thể thiếu | `OptionalInt`/`OptionalLong`/`OptionalDouble` | Không bóc khi rỗng |
| Chuyển int thành chuỗi mô tả | `IntStream.mapToObj(...)` | Tạo object theo từng số |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `IntStream.range(1,5).sum()` và `IntStream.rangeClosed(1,5).sum()` trả gì?

**Đáp án:** `range` trả tổng 1+2+3+4 = **10**; `rangeClosed` trả tổng thêm 5 = **15**.

**Câu 2.** Vì sao `IntStream.of(1,2,3).toList()` không biên dịch trên Java 17?

**Đáp án:** `IntStream` không có `toList()`. Dùng `boxed().toList()` để nhận `List<Integer>`, hoặc `toArray()` để nhận `int[]`.

**Câu 3.** `List.of("A","BB","CCC").stream().mapToInt(String::length).sum()` trả gì?

**Đáp án:** 1 + 2 + 3 = **6**.

**Câu 4.** `DoubleStream.empty().average()` trả gì?

**Đáp án:** `OptionalDouble.empty()`, không phải một `double` 0.0.

**Câu 5.** Có thể dùng `LongStream.asDoubleStream()` để giữ chính xác mọi số long lớn hơn 2^53 không?

**Không.** Có thể mất chính xác vì `double` không biểu diễn mọi số nguyên lớn.

**Câu 6.** `IntStream.of(2_000_000_000, 2_000_000_000).sum()` có kết quả 4.000.000.000 không?

**Không.** `int` tràn. Chuyển sang `asLongStream()` **trước** khi cộng để nhận 4.000.000.000 dưới dạng long.

**Câu 7.** Khi nào nên dùng `boxed()), và khi nào dùng `mapToObj()`?

**Đáp án:** `boxed()` khi cần Stream wrapper (`Integer`, `Long`, `Double`); `mapToObj()` khi muốn biến primitive thành một kiểu object bất kỳ, ví dụ chuỗi `"ID-"` cộng số.

**Câu 8.** Vì sao `IntStream.generate(() -> 1).sum()` là một pipeline nguy hiểm?

Vì nguồn sinh vô hạn và `sum()` cần tiêu thụ toàn bộ dữ liệu; nếu không có giới hạn, phép tính không kết thúc theo cách thông thường.

**Ghi nhớ:** Dùng **`IntStream` cho int**, **`LongStream` cho long**, **`DoubleStream` cho double** để tính toán theo kiểu nguyên thủy. Biết cách tạo nguồn, chuyển đổi bằng `mapToX`/`boxed`, xử lý các `OptionalX` và kiểm soát tràn số/sai số quan trọng hơn việc chỉ thay `Stream<T>` bằng một cái tên mới.
