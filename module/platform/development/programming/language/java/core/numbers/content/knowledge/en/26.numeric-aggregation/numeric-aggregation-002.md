# IntStream, LongStream, DoubleStream và cách giảm boxing khi tổng hợp số trong Java

## 1. Vấn đề: tổng hợp số có cần tạo đối tượng Integer, Long, Double?

Java Stream API cho phép xử lý tập dữ liệu bằng các phép biến đổi như `filter`, `map` và các phép tổng hợp như `sum`, `average`, `min`, `max`. Khi phần tử là giá trị nguyên thủy (*primitive*) `int`, `long` hoặc `double`, Java cung cấp ba loại stream chuyên biệt:

- `IntStream` xử lý phần tử kiểu `int`.
- `LongStream` xử lý phần tử kiểu `long`.
- `DoubleStream` xử lý phần tử kiểu `double`.

Ba kiểu đều nằm trong package `java.util.stream`. Khác với `Stream<Integer>`, `Stream<Long>` hoặc `Stream<Double>`, phần tử của chúng được truyền trong các thao tác chuyên biệt dưới dạng giá trị primitive. Vì thế chúng **có thể giảm việc boxing/unboxing và số đối tượng trung gian** khi tính tổng, trung bình hay tìm cực trị.

**Boxing** là chuyển primitive thành wrapper, như `int → Integer`. **Unboxing** là lấy primitive từ wrapper, như `Integer → int`. Java có thể tự động thực hiện hai chuyển đổi này, nhưng chúng vẫn là các thao tác có chi phí và có thể phát sinh đối tượng hoặc lỗi `NullPointerException` khi unbox giá trị `null`.

Ví dụ cùng một mục tiêu tính tổng:

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> numbers = List.of(10, 20, 30);

// Đã có List<Integer>: chuyển một lần sang IntStream để tính toán primitive.
int sumFromList = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum(); // 60

// Tạo dữ liệu bằng primitive ngay từ nguồn.
int sumFromPrimitive = IntStream.of(10, 20, 30).sum(); // 60
~~~

Cả hai cho kết quả 60. Lựa chọn tối ưu phụ thuộc nguồn dữ liệu: nếu dữ liệu đã được chứa trong `List<Integer>` thì việc unbox tại ranh giới là cần thiết; nếu có thể tạo và giữ dữ liệu primitive từ đầu, `IntStream` tránh được bước tạo wrapper chỉ để tính tổng.

## 2. Phân biệt Stream<T> và ba primitive stream

| Khía cạnh | `Stream<Integer>` (tương tự Long/Double) | `IntStream` | `LongStream` | `DoubleStream` |
|---|---|---|---|---|
| Kiểu phần tử | Đối tượng `Integer` | `int` | `long` | `double` |
| Có `sum()`? | Không | Có, trả `int` | Có, trả `long` | Có, trả `double` |
| Có `average()`? | Không | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` |
| `min()`, `max()` | `Optional<T>` khi có comparator/natural order | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `summaryStatistics()` | Không có phương thức tương ứng trực tiếp | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |
| `toArray()` | `T[]` nếu dùng constructor thích hợp; không đối số trả `Object[]` | `int[]` | `long[]` | `double[]` |
| `boxed()` | Không cần vì đã là stream đối tượng | `Stream<Integer>` | `Stream<Long>` | `Stream<Double>` |
| `map(...)` | Biến đổi đối tượng → đối tượng | `int → int` | `long → long` | `double → double` |

`Stream<T>` là abstraction cho đối tượng tham chiếu; nó không cung cấp `sum()` vì một `T` bất kỳ không nhất thiết là số, cũng không có một kiểu kết quả tổng mặc định. Trong khi đó, stream primitive biết sẵn kiểu của phần tử nên cung cấp phép toán số học chuyên biệt.

Một điểm cần chú ý: `IntStream` không thể chứa `null`. Điều này loại bỏ lỗi null do chính phần tử primitive, nhưng nếu nguồn là `Stream<Integer>` có `null`, thao tác `mapToInt(Integer::intValue)` vẫn có thể ném `NullPointerException` khi unbox.

Các primitive stream chỉ chuyên biệt cho ba kiểu `int`, `long`, `double`. Không có `ByteStream`, `ShortStream`, `CharStream` hoặc `FloatStream` trong Stream API chuẩn. Các giá trị `byte`, `short`, `char` có thể được đẩy sang `IntStream` khi phù hợp; `float` thường được xử lý bằng `DoubleStream` nếu cần phép toán số thực.

## 3. Cách tạo stream primitive

### 3.1. Từ các giá trị, mảng primitive

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

IntStream ints = IntStream.of(2, 4, 6);
LongStream longs = LongStream.of(1_000_000_000L, 2_000_000_000L);
DoubleStream doubles = DoubleStream.of(1.5, 2.5, 3.5);

int[] readings = {4, 6, 8};
int total = Arrays.stream(readings).sum(); // 18
~~~

`Arrays.stream(int[])` trả `IntStream`. Tương tự, `Arrays.stream(long[])` trả `LongStream` và `Arrays.stream(double[])` trả `DoubleStream`. Đây là con đường tự nhiên khi dữ liệu đã nằm trong mảng primitive.

Dễ mắc lỗi với `Stream.of(array)`:

~~~java
int[] readings = {4, 6, 8};

long a = Arrays.stream(readings).count(); // 3
long b = java.util.stream.Stream.of(readings).count(); // 1
~~~

`Stream.of(readings)` trong ví dụ này là stream chứa **một đối tượng mảng `int[]`**, không phải ba số nguyên. Muốn duyệt các phần tử số, dùng `Arrays.stream(readings)` hoặc `IntStream.of(readings)`.

### 3.2. Tạo dãy liên tiếp với range, rangeClosed

~~~java
IntStream.range(1, 5);         // 1, 2, 3, 4
IntStream.rangeClosed(1, 5);   // 1, 2, 3, 4, 5
LongStream.range(10L, 13L);   // 10, 11, 12
LongStream.rangeClosed(10L, 13L); // 10, 11, 12, 13
~~~

`range(startInclusive, endExclusive)` gồm đầu, không gồm cuối; `rangeClosed(startInclusive, endInclusive)` gồm cả hai đầu. Hai họ phương thức này có trên `IntStream` và `LongStream`; `DoubleStream` **không có** `range`/`rangeClosed`.

`range` rất hữu ích cho chỉ số mảng, vòng lặp đếm và dữ liệu có khoảng liên tục, nhưng lưu ý tính đúng của biên trước khi thay thế vòng lặp thông thường.

### 3.3. Từ Stream đối tượng qua mapToInt, mapToLong, mapToDouble

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> texts = List.of("7", "10", "13");

int sum = texts.stream()
        .mapToInt(Integer::parseInt)
        .sum(); // 30

long totalLengths = Stream.of("Java", "Stream")
        .mapToLong(s -> s.length())
        .sum(); // 10

double average = Stream.of("1.5", "2.5", "3.5")
        .mapToDouble(Double::parseDouble)
        .average()
        .orElseThrow(); // 2.5
~~~

Các toán tử `mapToInt`/`mapToLong`/`mapToDouble` là ranh giới chuyển từ stream đối tượng sang stream primitive. Sau chuyển đổi, phép lọc, ánh xạ và tổng hợp số có thể diễn ra mà không phải liên tục chuyển đổi từng phần tử sang wrapper.

## 4. Các phép tổng hợp số: sum, average, min, max, count

Ví dụ:

~~~java
int sum = IntStream.of(2, 4, 6).sum(); // 12
double average = IntStream.of(2, 4, 6).average().orElseThrow(); // 4.0
int minimum = IntStream.of(2, 4, 6).min().orElseThrow(); // 2
int maximum = IntStream.of(2, 4, 6).max().orElseThrow(); // 6
long count = IntStream.of(2, 4, 6).count(); // 3
~~~

`count()` trả `long`, không phải `int`. `average()` trên cả ba primitive stream đều trả `OptionalDouble`, vì trung bình của các số nguyên có thể là phân số: ví dụ trung bình của `1` và `2` là `1.5`.

`min()`/`max()` trả `OptionalInt`, `OptionalLong` hoặc `OptionalDouble` tương ứng; chúng không trả trực tiếp primitive vì stream có thể rỗng.

### 4.1. Xử lý stream rỗng đúng cách

~~~java
import java.util.OptionalDouble;
import java.util.stream.IntStream;

int sum = IntStream.empty().sum();       // 0
long count = IntStream.empty().count();  // 0
OptionalDouble avg = IntStream.empty().average(); // OptionalDouble.empty()
~~~

Với `min()`, `max()` và `average()`, hãy chọn cách xử lý stream rỗng theo nghiệp vụ:

~~~java
double fallback = IntStream.empty().average().orElse(0.0); // 0.0

// Chỉ dùng khi tập dữ liệu bắt buộc không rỗng.
// double required = IntStream.empty().average().orElseThrow();
~~~

`orElse(0.0)` là quyết định riêng của ứng dụng: về mặt toán học, trung bình của tập rỗng không phải 0. Nếu 0 có thể bị hiểu thành kết quả hợp lệ, tốt hơn nên giữ `OptionalDouble` hoặc báo lỗi rõ ràng.

### 4.2. summaryStatistics: tổng hợp nhiều chỉ số trong một lượt

Thay vì tạo nhiều stream riêng cho `count`, `sum`, `min`, `max` và `average`, có thể lấy một đối tượng thống kê:

~~~java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.of(2, 4, 6).summaryStatistics();

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 12
System.out.println(stats.getMin());     // 2
System.out.println(stats.getMax());     // 6
System.out.println(stats.getAverage()); // 4.0
~~~

Tương tự:

- `LongStream.summaryStatistics()` trả `LongSummaryStatistics`.
- `DoubleStream.summaryStatistics()` trả `DoubleSummaryStatistics`.

Các lớp thống kê cung cấp tổng, số lượng, cực trị và trung bình. Đối với stream rỗng, các giá trị cực trị và trung bình của summary-statistics dùng giá trị mặc định theo API; cần **kiểm tra `getCount()`** trước khi coi kết quả là một cực trị/trung bình có ý nghĩa.

`summaryStatistics()` cũng là một **terminal operation**: nó tiêu thụ stream. Không thể gọi lại `sum()` trên cùng một instance stream đã dùng.

## 5. Biến đổi primitive rồi tổng hợp: filter, map, reduce

Primitive stream có các thao tác trung gian `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`, `skip` và nhiều thao tác khác với hàm nhận primitive:

~~~java
int totalEvenSquares = IntStream.rangeClosed(1, 5)
        .filter(n -> n % 2 == 0) // 2, 4
        .map(n -> n * n)         // 4, 16
        .sum();                  // 20
~~~

Trong chuỗi này, `filter` và `map` làm việc với `int` qua các functional interface chuyên biệt `IntPredicate`, `IntUnaryOperator`. Dữ liệu không phải biến thành `Integer` giữa các thao tác.

Một số kiểu callback quan trọng:

| Primitive stream | `filter` nhận | `map` nhận | `forEach` nhận |
|---|---|---|---|
| `IntStream` | `IntPredicate` | `IntUnaryOperator` | `IntConsumer` |
| `LongStream` | `LongPredicate` | `LongUnaryOperator` | `LongConsumer` |
| `DoubleStream` | `DoublePredicate` | `DoubleUnaryOperator` | `DoubleConsumer` |

### 5.1. reduce với phép gộp tùy chọn

~~~java
int product = IntStream.rangeClosed(1, 4)
        .reduce(1, (a, b) -> a * b); // 24

int biggest = IntStream.of(4, 9, 2)
        .reduce(Integer::max)
        .orElseThrow(); // 9
~~~

`reduce(identity, operator)` trả một primitive (có giá trị identity nếu stream rỗng). `reduce(operator)` không có identity trả một `OptionalInt`/`OptionalLong`/`OptionalDouble`. Dùng phép kết hợp **có tính kết hợp (associative)** và identity phù hợp để đúng cả khi stream chạy parallel. Ví dụ phép cộng với identity 0, phép nhân với identity 1; không dùng phép trừ như một phép reduce tổng quát nếu cần kết quả ổn định dưới phân hoạch song song.

Khi chỉ cần tổng, ưu tiên `sum()` hơn `reduce(0, Integer::sum)` vì mã rõ mục đích hơn.

### 5.2. Không phải lúc nào cũng cần reduce tùy biến

`sum`, `average`, `summaryStatistics` đã thể hiện các kiểu tổng hợp phổ biến. Nếu cần gom vào cấu trúc đặc biệt mà không muốn boxing từng phần tử, `IntStream` có overload `collect(supplier, accumulator, combiner)` với accumulator là `ObjIntConsumer<R>`:

~~~java
String joined = IntStream.of(2, 3, 5)
        .collect(
            StringBuilder::new,
            (builder, value) -> builder.append(value),
            (left, right) -> left.append(right)
        )
        .toString(); // "235"
~~~

Accumulator nhận `int` primitive. Với tác vụ song song, supplier tạo container riêng cho các nhánh và combiner phải ghép đúng, không dùng một container chia sẻ bên ngoài. Trường hợp chỉ nối chuỗi đơn giản chưa chắc cần collector tùy biến; ví dụ này minh họa cơ chế chuyên biệt.

## 6. Chuyển đổi qua lại: boxed(), mapToObj(), mapToInt()

Khi API phía sau cần đối tượng, hãy **boxing ở ranh giới thực sự cần thiết**.

### 6.1. Primitive stream → Stream wrapper bằng boxed()

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> ids = IntStream.of(3, 1, 3, 2)
        .distinct()
        .sorted()
        .boxed()
        .toList(); // [1, 2, 3]
~~~

`boxed()` chuyển:

| Đầu vào | Kết quả |
|---|---|
| `IntStream.boxed()` | `Stream<Integer>` |
| `LongStream.boxed()` | `Stream<Long>` |
| `DoubleStream.boxed()` | `Stream<Double>` |

`toList()` trong ví dụ là terminal operation của `Stream<Integer>` (có từ Java 16); `IntStream` không có phương thức `toList()` để tạo `List<Integer>` trực tiếp. Bước `boxed()` là cần thiết khi kiểu đầu ra được yêu cầu là list các wrapper.

Chỉ nên chuyển sang wrapper khi thực sự cần đối tượng, ví dụ gọi API nhận `List<Integer>`. Nếu chỉ tính tổng thì `IntStream.of(...).sum()` gọn và tránh ranh giới boxing đó.

### 6.2. Primitive → kiểu đối tượng khác bằng mapToObj()

~~~java
List<String> labels = IntStream.of(2, 3, 5)
        .mapToObj(n -> "id-" + n)
        .toList(); // [id-2, id-3, id-5]
~~~

`mapToObj` khác `boxed`: nó ánh xạ primitive sang **đối tượng bất kỳ**. Tương tự, `LongStream` và `DoubleStream` cũng có `mapToObj`. Việc tạo `String` là chủ ý của nghiệp vụ, không phải boxing số nguyên không cần thiết.

### 6.3. Stream wrapper → primitive bằng mapToInt(), mapToLong(), mapToDouble()

~~~java
List<Integer> values = List.of(5, 10, 15);

int total = values.stream()
        .mapToInt(Integer::intValue)
        .sum(); // 30
~~~

Ở ranh giới này, Java cần unbox từng `Integer` thành `int`. Điều hữu ích là phần còn lại của pipeline có thể tiếp tục làm việc với primitive. Nếu danh sách có `null` thì `Integer::intValue` gây `NullPointerException`; nên xử lý nguồn có null rõ ràng, ví dụ lọc trước bằng `filter(java.util.Objects::nonNull)` nếu nghiệp vụ cho phép bỏ qua dữ liệu thiếu.

`IntStream` còn có `mapToLong`, `mapToDouble` để đổi loại primitive; `LongStream` có `mapToInt`, `mapToDouble`; `DoubleStream` có `mapToInt`, `mapToLong`. Các chuyển đổi *narrowing* từ `long`/`double` xuống `int` có thể mất thông tin, vì thế không coi chúng là thao tác luôn an toàn.

### 6.4. asLongStream(), asDoubleStream()

~~~java
long safeForThisSum = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum(); // 2147483648

double mean = IntStream.of(1, 2)
        .asDoubleStream()
        .average()
        .orElseThrow(); // 1.5
~~~

`asLongStream()` trên `IntStream` là phép *widening* giữ chính xác giá trị `int`. `IntStream.asDoubleStream()` cũng giữ chính xác mọi giá trị `int` (vì `double` biểu diễn chính xác các số nguyên 32 bit). Nhưng `LongStream.asDoubleStream()` **có thể mất độ chính xác** đối với `long` lớn hơn ngưỡng chính xác nguyên của `double` (khoảng `2^53`). Không dùng chuyển đổi đó cho phép tính đòi hỏi giữ chính xác từng đơn vị với số nguyên lớn.

## 7. Chương trình Java 17+ hoàn chỉnh và kết quả kiểm chứng

Tạo tệp `PrimitiveStreamsDemo.java`:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class PrimitiveStreamsDemo {
    public static void main(String[] args) {
        int[] readings = {2, 4, 6, 8};
        System.out.println("array sum=" + Arrays.stream(readings).sum());
        System.out.println("range=" + IntStream.range(1, 5).sum());
        System.out.println("rangeClosed=" + LongStream.rangeClosed(1, 5).sum());

        IntSummaryStatistics stats =
                IntStream.of(2, 4, 6).summaryStatistics();
        System.out.println("stats count=" + stats.getCount()
                + ", sum=" + stats.getSum()
                + ", avg=" + stats.getAverage());

        System.out.println("max=" +
                IntStream.of(8, 2, 5).max().orElseThrow());
        System.out.println("empty average present=" +
                IntStream.empty().average().isPresent());

        List<Integer> ids = IntStream.of(3, 1, 3, 2)
                .distinct().sorted().boxed().toList();
        System.out.println("boxed ids=" + ids);

        List<String> labels = IntStream.of(2, 3, 5)
                .mapToObj(i -> "id-" + i).toList();
        System.out.println("labels=" + labels);

        System.out.println("parsed sum=" +
                Stream.of("7", "10", "13")
                        .mapToInt(Integer::parseInt).sum());

        System.out.println("long sum=" +
                IntStream.of(Integer.MAX_VALUE, 1)
                        .asLongStream().sum());
        System.out.println("int sum=" +
                IntStream.of(Integer.MAX_VALUE, 1).sum());

        System.out.println("double total=" +
                DoubleStream.of(1.5, 2.5, 3.5).sum());
        System.out.println("double avg=" +
                DoubleStream.of(1.5, 2.5, 3.5)
                        .average().orElseThrow());

        String joined = IntStream.of(2, 3, 5)
                .collect(
                        StringBuilder::new,
                        (builder, value) -> builder.append(value),
                        (left, right) -> left.append(right))
                .toString();
        System.out.println("collected=" + joined);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PrimitiveStreamsDemo.java
java PrimitiveStreamsDemo
~~~

Kết quả stdout:

~~~text
array sum=20
range=10
rangeClosed=15
stats count=3, sum=12, avg=4.0
max=8
empty average present=false
boxed ids=[1, 2, 3]
labels=[id-2, id-3, id-5]
parsed sum=30
long sum=2147483648
int sum=-2147483648
double total=7.5
double avg=2.5
collected=235
~~~

Chương trình minh họa các ranh giới quan trọng. `Arrays.stream(int[])` và `IntStream.range` tạo luồng primitive; `summaryStatistics` tổng hợp các chỉ số trong một lần tiêu thụ; `boxed()` chỉ xuất hiện tại nơi cần `List<Integer>`; `mapToObj` tạo đối tượng `String` khi cần. Hai dòng `long sum` và `int sum` cố ý cho thấy tràn số `int` trong một phép tổng hợp mặc định.

## 8. Kiểm soát overflow khi tổng hợp số nguyên

Dùng stream primitive **không tự động bảo đảm tổng luôn nằm trong kiểu kết quả**.

~~~java
int overflowed = IntStream.of(Integer.MAX_VALUE, 1).sum();
// -2147483648 do tràn int

long widenedFirst = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
// 2147483648
~~~

`IntStream.sum()` trả `int` nên có thể overflow theo quy tắc số nguyên Java; `LongStream.sum()` cũng có thể overflow với dữ liệu `long` đủ lớn. Không phải lúc nào `asLongStream()` cũng giải quyết được mọi bài toán: nó chỉ mở rộng giới hạn từ 32 bit sang 64 bit.

Quan trọng là **mở rộng trước khi thực hiện phép toán có thể tràn**, không phải cast sau:

~~~java
long wrong = IntStream.of(50_000, 60_000)
        .map(n -> n * n)        // phép nhân trong int: đã tràn
        .asLongStream()
        .sum();

long correct = IntStream.of(50_000, 60_000)
        .mapToLong(n -> (long) n * n)
        .sum(); // 6100000000
~~~

Cast `(long) n` được đặt **trước phép nhân** nên toán tử nhân tính ở `long`. Với dữ liệu có thể vượt cả phạm vi `long`, cần thiết kế phép tổng hợp dùng `BigInteger` hoặc xử lý giới hạn theo yêu cầu.

Khi cần **phát hiện** overflow thay vì để giá trị wrap, có thể dùng `Math.addExact`:

~~~java
int exact = IntStream.of(1, 2, 3)
        .reduce(0, Math::addExact); // 6

// IntStream.of(Integer.MAX_VALUE, 1)
//          .reduce(0, Math::addExact);
// Ném ArithmeticException khi phép cộng vượt miền int.
~~~

Đối với một pipeline song song, các phép reduce phải thỏa điều kiện về phép kết hợp; phép cộng chính xác bằng `Math.addExact` có thể ném ngoại lệ trong quá trình gộp nếu một bước vượt giới hạn. Hãy xác định rõ bạn muốn kết quả kiểu `int`, `long`, số nguyên không giới hạn, hay hành vi lỗi khi tràn.

## 9. DoubleStream có tốc độ và đặc tính số thực riêng

`DoubleStream` phù hợp với dữ liệu đo lường hoặc số thực mà độ chính xác xấp xỉ IEEE 754 được chấp nhận:

~~~java
double sum = DoubleStream.of(1.5, 2.5, 3.5).sum(); // 7.5
double average = DoubleStream.of(1.5, 2.5, 3.5)
        .average().orElseThrow(); // 2.5
~~~

Tuy nhiên `double` **không thể biểu diễn chính xác mọi phân số thập phân**, chẳng hạn `0.1`. `DoubleStream.sum()` có cơ chế cộng bù (*compensated summation*) nhằm giảm sai số so với cộng ngây thơ trong nhiều tình huống, nhưng **không bảo đảm** kết quả thập phân chính xác như một phép tính `BigDecimal`.

Ví dụ diễn giải:

~~~java
double a = 0.1;
double b = 0.2;
System.out.println(a + b == 0.3); // false trên phép cộng double thông thường
~~~

Không nên dùng ví dụ này để khẳng định một chuỗi `DoubleStream.sum()` cụ thể luôn tạo cùng chuỗi thập phân với phép cộng trực tiếp: thuật toán gộp có thể khác. Bài học là phải chọn kiểu số phù hợp với yêu cầu chính xác.

Nếu xử lý số tiền hoặc các đại lượng có quy định thập phân chính xác, `BigDecimal` thường là lựa chọn thích hợp hơn; khi đó pipeline đối tượng có thể là chủ ý đúng đắn, và lợi ích giảm boxing không quan trọng bằng bảo đảm tính đúng của phép toán.

Một số khác biệt khác cần biết:

- `DoubleStream` có thể chứa `NaN`, `Infinity` và `-Infinity`; cách các giá trị này lan truyền trong tổng hợp cần được quy định ở ứng dụng.
- `DoubleStream.min()`/`max()` trả `OptionalDouble`. Không dùng kết quả nếu rỗng mà thiếu kiểm tra.
- `double` mất khả năng biểu diễn chính xác mọi số nguyên lớn hơn `2^53`. Tránh chuyển số lượng `long` lớn thành `double` chỉ để dùng `average()` nếu nghiệp vụ cần giữ nguyên từng đơn vị.
- Trong phép cộng số thực, thứ tự gộp có thể ảnh hưởng chữ số thấp của kết quả. Chạy parallel có thể thay đổi thứ tự tính, vì vậy so sánh số thực thường cần ngưỡng sai số thay vì `==` khi nghiệp vụ cho phép.

## 10. flatMapToInt và xử lý nhiều mảng primitive

Một dữ liệu đầu vào có thể là nhiều mảng `int[]` nằm trong một `Stream<int[]>`. Không cần boxing từng phần tử để nối chúng:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

int total = Stream.of(
        new int[] {1, 2},
        new int[] {3, 4, 5}
    )
    .flatMapToInt(Arrays::stream)
    .sum(); // 15
~~~

`flatMapToInt` lấy từng `int[]`, tạo `IntStream` tương ứng rồi nối các phần tử primitive. Tương tự, `flatMapToLong` và `flatMapToDouble` áp dụng khi kết quả ánh xạ là `LongStream` hoặc `DoubleStream`.

Nếu nguồn đã là `IntStream` và mỗi giá trị phải sinh ra nhiều `int`, chính `IntStream.flatMap` nhận hàm trả `IntStream`:

~~~java
int sum = IntStream.of(1, 2, 3)
        .flatMap(n -> IntStream.of(n, n * 10))
        .sum(); // 66
~~~

Đây là mô hình hữu ích khi trải phẳng dữ liệu số trước khi tổng hợp mà không cần dựng `List<Integer>` trung gian.

## 11. Parallel stream: có thể nhanh hơn, nhưng không phải mặc định

Các primitive stream hỗ trợ `parallel()`:

~~~java
long sum = IntStream.rangeClosed(1, 1_000_000)
        .asLongStream()
        .parallel()
        .sum(); // 500000500000
~~~

Phép tính này hợp lệ vì tổng `long` trong ví dụ không overflow, và việc cộng số nguyên có tính kết hợp phù hợp cho phân hoạch dữ liệu. Tuy nhiên `parallel()` **không mặc nhiên nhanh hơn**; với đầu vào nhỏ hoặc mỗi phần tử xử lý quá nhẹ, chi phí chia việc, lập lịch và gộp có thể cao hơn lợi ích.

Đừng thay một pipeline tuần tự nhỏ bằng parallel chỉ vì nó dùng primitive. Cũng không nên ghi vào biến cộng dồn dùng chung trong `forEach`:

~~~java
// Không an toàn khi chạy parallel vì cập nhật biến chung không đồng bộ:
int[] total = {0};
IntStream.rangeClosed(1, 100).parallel()
        .forEach(n -> total[0] += n);
~~~

Kết quả ví dụ trên có thể sai do data race. Hãy dùng `sum()`, `reduce()` hoặc collector có supplier/accumulator/combiner hợp lệ. Với `forEach` trên parallel stream, thứ tự thực thi không được bảo đảm; `forEachOrdered` giữ thứ tự gặp phần tử khi cần nhưng có thể làm giảm lợi ích song song.

Các primitive stream, giống `Stream<T>`, thường **chỉ được tiêu thụ một lần**. Sau một terminal operation (`sum`, `toArray`, `count`, `collect`...), muốn tính chỉ số khác cần tạo stream mới hoặc lấy nhiều thống kê trong một lượt bằng `summaryStatistics`.

## 12. Giảm boxing thế nào cho đúng, và khi nào nên đo hiệu năng?

So sánh hai pipeline cùng mục tiêu:

~~~java
// Có thể tạo các giá trị wrapper ở nhiều bước.
int totalA = IntStream.rangeClosed(1, 1000)
        .boxed()
        .map(n -> n * 2)
        .reduce(0, Integer::sum);

// Giữ primitive xuyên suốt.
int totalB = IntStream.rangeClosed(1, 1000)
        .map(n -> n * 2)
        .sum();
~~~

Cả hai trả kết quả `1001000`. Pipeline thứ hai mô tả ý định tính toán rõ hơn và tránh chuyển phần tử thành `Integer` trước khi `map`/`reduce`. Tuy nhiên không suy luận một tỉ lệ tăng tốc cố định: JVM có tối ưu JIT, cache wrapper trong một số trường hợp, escape analysis và chi phí tối ưu khác tùy workload.

Các quy tắc thực hành:

1. **Bắt đầu từ nguồn primitive nếu có thể:** `int[]`, `long[]`, `double[]`, `IntStream.range`.
2. **Giữ primitive trong phần xử lý số học:** `filter`, `map`, `sum`, `average`, `summaryStatistics`.
3. **Chuyển khi cần:** dùng `mapToInt` cho dữ liệu đối tượng đầu vào; dùng `boxed` khi đầu ra bắt buộc là wrapper/list; dùng `mapToObj` khi cần một đối tượng nghiệp vụ.
4. **Không hy sinh tính đúng:** chọn `long` hoặc `BigInteger` khi `int` có thể tràn; chọn `BigDecimal` khi cần tính thập phân chính xác.
5. **Đo ở môi trường phù hợp:** với hệ thống quan trọng hiệu năng, dùng profiler và microbenchmark đáng tin cậy (thường dùng JMH) trên dữ liệu và kích thước thực tế; tránh kết luận từ một lần chạy nhỏ hoặc đo qua `System.currentTimeMillis()`.

Mục tiêu của primitive stream không phải "xóa sạch mọi đối tượng" trong JVM. Mục tiêu là tránh boxing/unboxing của **từng phần tử số** tại những điểm không cần thiết, đồng thời có API tổng hợp số rõ ràng, dễ kiểm tra.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Hướng xử lý |
|---|---|---|
| `Stream.of(intArray)` để tính tổng các phần tử | Stream chứa một mảng, không phải nhiều số | `Arrays.stream(intArray).sum()` |
| Gọi `sum()` trực tiếp trên `Stream<Integer>` | Không có phương thức `sum()` | `mapToInt(Integer::intValue).sum()` |
| Gọi `toList()` trên `IntStream` | Không có API trả `List<Integer>` như vậy | `boxed().toList()` nếu cần list |
| Boxing sớm trước chuỗi tính toán dài | Thêm chuyển đổi và có thể tăng cấp phát wrapper | Giữ primitive tới ranh giới object |
| Unbox `Integer` có `null` | `NullPointerException` | Xử lý null theo nghiệp vụ trước `mapToInt` |
| Cho rằng `IntStream.sum()` không thể overflow | Tổng có thể wrap ra số âm | Mở rộng sớm sang long, hoặc kiểm tra bằng `Math.addExact` |
| Cast sang long **sau** khi nhân int | Tích đã overflow trước cast | Ép kiểu `(long) n * n` ngay trong `mapToLong` |
| Gọi `max().getAsInt()` trên stream rỗng | `NoSuchElementException` | Kiểm tra `isPresent` hoặc `orElseThrow` theo contract |
| Dùng `DoubleStream` cho tiền cần thập phân chính xác | Sai số số thực | Dùng `BigDecimal` và quy tắc làm tròn rõ |
| Kỳ vọng parallel luôn nhanh | Chi phí đồng bộ/phân hoạch lớn | Benchmark và chỉ parallel khi đáng giá |
| Tích lũy vào biến chung trong parallel `forEach` | Data race, kết quả không xác định | Dùng `sum`, `reduce`, collector đúng |
| Gọi `sum()` rồi `average()` trên cùng stream | `IllegalStateException` vì stream đã tiêu thụ | Tạo stream mới hoặc `summaryStatistics` |
| Chuyển `long` rất lớn sang `double` để làm tổng/trung bình | Có thể mất độ chính xác nguyên | Giữ `long`/`BigInteger` hoặc chọn kỹ thuật chính xác thích hợp |

## 14. Bài tập tự kiểm tra

**Bài 1.** Viết tổng các số chẵn từ 1 đến 10 mà không boxing.

**Đáp án:**

~~~java
int sum = IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .sum(); // 30
~~~

**Bài 2.** Với mảng `int[] data = {3, 6, 9}`, vì sao `Stream.of(data).count()` trả 1 còn `Arrays.stream(data).count()` trả 3?

**Đáp án:** `Stream.of(data)` coi cả `int[]` là một phần tử đối tượng; `Arrays.stream(data)` tạo `IntStream` gồm ba phần tử primitive.

**Bài 3.** Tổng `Integer.MAX_VALUE + 1` nên dùng thao tác nào để tránh overflow `int` trong phép tổng hợp này?

**Đáp án:** `IntStream.of(Integer.MAX_VALUE, 1).asLongStream().sum()` trả `2147483648`; không dùng `IntStream.sum()` cho trường hợp đó.

**Bài 4.** `IntStream.of(1, 2, 3).average()` trả loại gì? Nếu stream rỗng thì sao?

**Đáp án:** `OptionalDouble`, có giá trị trung bình `2.0` khi có phần tử. Với stream rỗng là `OptionalDouble.empty()`; người gọi quyết định fallback hoặc báo lỗi.

**Bài 5.** Sau `IntStream.range(0, 4).sum()` có thể tiếp tục dùng cùng stream để tính `max()` không?

**Đáp án:** Không, stream đã kết thúc sau terminal operation. Hãy tạo stream mới, hoặc nếu cần nhiều chỉ số trong một lượt thì dùng `summaryStatistics()`.

**Bài 6.** Khi đầu ra phải là `List<Integer>` có tăng dần từ 1 đến 5, có phải boxing không?

**Đáp án:** Có vì `List<Integer>` chứa đối tượng wrapper. Ví dụ `IntStream.rangeClosed(1, 5).boxed().toList()`. Điều cần tránh là boxing sớm hơn nhu cầu đầu ra.

**Bài 7.** Kết quả của `IntStream.of(50_000, 60_000).mapToLong(n -> (long)n * n).sum()` bằng bao nhiêu?

**Đáp án:** `6_100_000_000L`. Cast lên long trước phép nhân giữ chính xác hai bình phương và tổng trong giới hạn long.

---

**Ghi nhớ:** `IntStream`, `LongStream` và `DoubleStream` là những stream chuyên biệt cho tính toán số, cung cấp `sum`, `average`, `summaryStatistics` và nhiều phép toán trên phần tử primitive. **Giữ primitive trong phần tính toán, boxing khi API thực sự cần đối tượng**, đồng thời luôn kiểm tra overflow, độ chính xác số thực, trường hợp stream rỗng và yêu cầu nghiệp vụ.