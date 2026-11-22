# Tránh boxing không cần thiết trong phép tính số với Java Stream

Khi tính tổng, trung bình, giá trị lớn nhất hoặc thống kê trên một dãy số, cách chọn kiểu Stream ảnh hưởng đến chi phí xử lý. `Stream<Integer>`, `Stream<Long>` và `Stream<Double>` chứa **tham chiếu đến các wrapper object**; còn `IntStream`, `LongStream` và `DoubleStream` chuyên xử lý **giá trị nguyên thủy** tương ứng. Việc đi qua các wrapper không cần thiết có thể gây boxing/unboxing, tăng bộ nhớ, lượng cấp phát và áp lực garbage collector.

Mục tiêu của bài là nhận diện **khi nào thật sự cần kiểu wrapper**, khi nào nên dùng primitive stream để giữ phép toán số ở dạng nguyên thủy, và tránh tối ưu sai làm thay đổi ý nghĩa dữ liệu.

Ví dụ trọng tâm:

~~~java
List<Integer> values = List.of(2, 3, 5);

// Dễ tạo trung gian boxed khi nguồn/kiểu đích đòi Integer:
int boxed = values.stream()
        .map(n -> n * 2)
        .reduce(0, Integer::sum);

// Phép toán số nằm trên IntStream sau khi unbox phần tử nguồn:
int primitive = values.stream()
        .mapToInt(Integer::intValue)
        .map(n -> n * 2)
        .sum();
~~~

Cả hai cho tổng `20`. Nguồn `List<Integer>` vẫn đang giữ `Integer`, nên không thể xóa hoàn toàn unboxing khi đọc từ list. Tuy nhiên, pipeline thứ hai tránh tiếp tục dùng `Integer` cho **các bước số học ở giữa**, và dùng trực tiếp terminal `sum()`.

Đoạn trên cần `import java.util.List;` và đặt trong một phương thức. Trình biên dịch/JVM có thể tối ưu một số đối tượng tạm nhờ JIT, nên không nên tuyên bố mỗi phép `map` bắt buộc cấp phát một `Integer` mới. Cần hiểu khác biệt ở **kiểu API và khả năng phát sinh chi phí**, sau đó đo hiệu năng nếu tối ưu hóa là mục tiêu.

## 1. Boxing và unboxing là gì?

Java có kiểu nguyên thủy `int`, `long`, `double` và các lớp wrapper tương ứng `Integer`, `Long`, `Double`. **Boxing** chuyển giá trị nguyên thủy thành tham chiếu wrapper; **unboxing** lấy giá trị nguyên thủy từ wrapper:

~~~java
int primitiveValue = 42;
Integer boxedValue = primitiveValue; // Autoboxing: Integer.valueOf(42)
int restored = boxedValue;           // Unboxing: boxedValue.intValue()
~~~

Autoboxing hữu ích khi API yêu cầu đối tượng, chẳng hạn các generic collection. Nhưng khi lặp qua lượng lớn dữ liệu số, tạo/giữ wrapper ở các bước không cần thiết có thể tốn thêm tài nguyên.

Ví dụ:

~~~java
Stream<Integer> boxedStream = Stream.of(1, 2, 3);
IntStream intStream = IntStream.of(1, 2, 3);
~~~

`Stream<Integer>` truyền `Integer` qua pipeline; `IntStream` biểu diễn dữ liệu dạng `int`. Trong lời gọi `Stream.of(1, 2, 3)`, các literal kiểu `int` được boxing để khớp `Integer` của Stream. `IntStream.of(...)` có overload nhận các giá trị `int` và cho phép các toán tử chuyên biệt.

**Chi phí không phải ở mỗi dấu ngoặc của mã nguồn.** Thực tế còn phụ thuộc JDK, escape analysis, JIT, kích thước dữ liệu và khả năng JVM loại bỏ cấp phát. Nhưng chọn kiểu primitive giúp API diễn đạt đúng đặc tính phép toán số và tránh nhu cầu boxing ở nhiều khâu.

## 2. Ba họ primitive stream

| Họ Stream | Kiểu phần tử | Phép toán thường dùng |
| --- | --- | --- |
| `IntStream` | `int` | `map(IntUnaryOperator)`, `sum()`, `average()`, `summaryStatistics()` |
| `LongStream` | `long` | `map(LongUnaryOperator)`, `sum()`, `max()`, `average()` |
| `DoubleStream` | `double` | `map(DoubleUnaryOperator)`, `sum()`, `average()`, `summaryStatistics()` |

Các lớp đều nằm trong `java.util.stream`. Chúng là **primitive specializations** của Stream API, không phải `Stream<int>` hay `Stream<double>`: Java generics không cho phép dùng kiểu nguyên thủy làm type argument.

Các nguồn cơ bản:

~~~java
IntStream oneToFive = IntStream.rangeClosed(1, 5);
LongStream identifiers = LongStream.of(10L, 20L, 30L);
DoubleStream prices = DoubleStream.of(1.5, 2.25, 3.75);
~~~

Đoạn mã minh họa cần import ba lớp `IntStream`, `LongStream`, `DoubleStream`; các stream chỉ dùng một lần. Sau khi terminal như `sum()`, chúng đã được tiêu thụ.

Từ mảng nguyên thủy:

~~~java
int[] items = {2, 4, 6};
int total = Arrays.stream(items).sum(); // 12
~~~

Cần `java.util.Arrays`. `Arrays.stream(int[])` tạo `IntStream`, còn `Arrays.stream(Integer[])` tạo `Stream<Integer>`. Nếu hệ thống đang xử lý số học trên mảng, giữ `int[]` hoặc `long[]` có thể tránh chi phí biểu diễn mỗi phần tử bằng wrapper như trong `Integer[]`.

## 3. `mapToInt()`, `mapToLong()` và `mapToDouble()`

Khi nguồn là `Stream<T>` (ví dụ danh sách đối tượng nghiệp vụ), dùng một hàm trích xuất số trực tiếp để chuyển sang primitive stream.

Giả sử có:

~~~java
record Sale(String sku, int quantity, long cents, double rating) {}
~~~

Các hàm chuyển đổi:

~~~java
IntStream quantities = sales.stream().mapToInt(Sale::quantity);
LongStream amounts = sales.stream().mapToLong(Sale::cents);
DoubleStream ratings = sales.stream().mapToDouble(Sale::rating);
~~~

Đây là những **đoạn mã minh họa**, đặt trong phương thức có `List<Sale> sales` và import thích hợp. Method reference `Sale::quantity` có kiểu tương thích với `ToIntFunction<Sale>`; `Sale::cents` với `ToLongFunction<Sale>`; `Sale::rating` với `ToDoubleFunction<Sale>`. Những functional interface này trả về primitive thay vì wrapper.

Từ danh sách wrapper `List<Integer>`:

~~~java
int sum = values.stream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

Bước `Integer::intValue` unbox phần tử nguồn. Sau bước đó, các phép `filter`, `map`, `sum` trên `IntStream` làm việc với `int`.

### Phân biệt `map` và `mapToInt`

~~~java
// map nhận Function<Sale, Integer> và trả Stream<Integer>:
Stream<Integer> valuesBoxed = sales.stream().map(Sale::quantity);

// mapToInt nhận ToIntFunction<Sale> và trả IntStream:
IntStream valuesPrimitive = sales.stream().mapToInt(Sale::quantity);
~~~

Đường thứ nhất cần biểu diễn giá trị số của pipeline dưới dạng wrapper; đường thứ hai đưa giá trị nguyên thủy qua chuyên biệt `IntStream`. Nếu mục đích cuối cùng là tổng, trung bình, min/max hoặc thống kê, đường thứ hai thường đơn giản và phù hợp hơn.

### Các hàm trích xuất cho kiểu lớn

Nếu `quantity` là `int` nhưng tổng có nguy cơ vượt phạm vi `int`, dùng `mapToLong` để mở rộng **trước** khi tính tổng:

~~~java
long total = sales.stream()
        .mapToLong(s -> (long) s.quantity())
        .sum();
~~~

Điều này bảo vệ khỏi tràn `int` xảy ra trong quá trình cộng (nếu kết quả còn trong khoảng `long`). **Không** dùng `mapToInt(...).sum()` rồi mới ép sang `long`: phép cộng đã tràn trong `int` trước khi ép kiểu.

## 4. Terminal chuyên biệt cho phép tính số

Primitive streams có terminal số học, không cần tự ghép `reduce` để tính những tổng đơn giản:

| Phép tính | Ví dụ | Kiểu kết quả |
| --- | --- | --- |
| Tổng `int` | `IntStream.of(1, 2, 3).sum()` | `int` bằng `6` |
| Tổng `long` | `LongStream.of(1L, 2L).sum()` | `long` bằng `3` |
| Tổng `double` | `DoubleStream.of(1.5, 2.0).sum()` | `double` bằng `3.5` |
| Số lượng phần tử | `IntStream.of(1, 2).count()` | `long` bằng `2` |
| Trung bình | `IntStream.of(2, 4).average()` | `OptionalDouble` chứa `3.0` |
| Nhỏ nhất/lớn nhất | `IntStream.of(2, 4).max()` | `OptionalInt` chứa `4` |
| Thống kê | `IntStream.of(2, 4).summaryStatistics()` | `IntSummaryStatistics` |

`OptionalInt`, `OptionalLong` và `OptionalDouble` là các container tùy chọn chuyên biệt cho primitive. Chúng cho phép biểu diễn việc **không có giá trị** mà không cần bọc số bằng `Optional<Integer>`, `Optional<Long>` hoặc `Optional<Double>`. Ví dụ `IntStream.empty().max()` trả `OptionalInt.empty()`; `IntStream.empty().average()` trả `OptionalDouble.empty()`.

~~~java
OptionalInt maybeMax = IntStream.of(5, 8, 3).max();
int maxOrDefault = maybeMax.orElse(0); // 8

double meanOrZero = IntStream.of(5, 8, 3)
        .average()
        .orElse(0.0); // 5.333333...
~~~

Đoạn cần import `OptionalInt`, `IntStream`. Mỗi lời gọi `IntStream.of(...)` tạo stream mới, vì stream đã bị tiêu thụ sau terminal.

### `summaryStatistics()` gom nhiều kết quả trong một lần duyệt

`IntStream.summaryStatistics()` cung cấp `count`, `sum`, `min`, `max` và `average`. Khi cùng cần nhiều thống kê trên cùng dữ liệu, nó tránh phải tạo nhiều pipeline riêng để tính từng con số.

~~~java
IntSummaryStatistics stats = sales.stream()
        .mapToInt(Sale::quantity)
        .summaryStatistics();

long count = stats.getCount();
long sum = stats.getSum();
int min = stats.getMin();
int max = stats.getMax();
double average = stats.getAverage();
~~~

Đây là đoạn mã trong phương thức có `sales`; cần `java.util.IntSummaryStatistics`. Một chi tiết quan trọng: **`IntSummaryStatistics.getSum()` có kiểu `long`**, còn `IntStream.sum()` có kiểu `int`. Không nên nhầm hai phương thức khi đánh giá giới hạn tràn số.

Với stream rỗng, `IntSummaryStatistics` có count/sum bằng 0 và average bằng 0.0; min là `Integer.MAX_VALUE`, max là `Integer.MIN_VALUE` khi chưa có phần tử. Vì vậy trước khi dùng min/max như một kết quả có nghĩa, cần kiểm tra `count > 0`.

## 5. Tránh `reduce` kiểu boxed khi đã có primitive terminal

Một cách viết có thể làm việc với `Stream<Integer>`:

~~~java
int sumBoxed = sales.stream()
        .map(Sale::quantity)
        .reduce(0, Integer::sum);
~~~

`map` tạo `Stream<Integer>`; phép giảm `reduce` dùng toán tử trên kiểu wrapper, phát sinh khả năng boxing/unboxing trong chuỗi xử lý. Khi mục tiêu chỉ là tổng `int`, ưu tiên:

~~~java
int sumPrimitive = sales.stream()
        .mapToInt(Sale::quantity)
        .sum();
~~~

Cách thứ hai ngắn, nêu rõ ý định và tránh pipeline `Stream<Integer>` trung gian. Nếu cần bộ kết quả chính xác khác (ví dụ tính đồng thời tổng, danh sách kiểm chứng và số lượng), có thể dùng collector hoặc cấu trúc accumulator thích hợp, nhưng hãy cân nhắc tính kết hợp, tính bất biến và yêu cầu song song.

`IntStream.reduce(identity, op)` vẫn hữu ích khi phép gộp không phải cộng và không có terminal chuyên biệt:

~~~java
int product = IntStream.of(2, 3, 4)
        .reduce(1, (a, b) -> a * b);
// 24
~~~

`IntBinaryOperator` dùng hai `int` và trả `int`. Khi parallel, hàm giảm cần **associative** và identity phải trung lập với phép gộp. Phép nhân có thể tràn số nguyên; dùng dạng dữ liệu khác nếu nghiệp vụ yêu cầu không tràn.

### Giảm nhiều kiểu số trong cùng pipeline

Có thể làm một số phép toán bằng `mapToLong` hoặc `asLongStream` nếu phép cộng vượt `int`:

~~~java
long safeWideSum = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum();
// 2147483648
~~~

Ngược lại:

~~~java
int overflow = IntStream.of(Integer.MAX_VALUE, 1).sum();
// -2147483648 do tràn int hai bù trong Java
~~~

Kết quả ví dụ cho thấy lý do mở rộng **trước khi** tổng hợp. Tuy nhiên, `long` cũng có giới hạn; khi vượt `Long.MAX_VALUE` hoặc cần số nguyên chính xác không giới hạn, dùng `BigInteger` và phép tính thích hợp, chấp nhận bản chất object của nó.

## 6. Chuyển qua lại giữa Stream đối tượng và primitive stream

Java cung cấp một số điểm chuyển đổi rõ ràng:

| Từ | Đến | Phương thức |
| --- | --- | --- |
| `Stream<T>` | `IntStream` | `mapToInt(ToIntFunction<? super T>)` |
| `Stream<T>` | `LongStream` | `mapToLong(ToLongFunction<? super T>)` |
| `Stream<T>` | `DoubleStream` | `mapToDouble(ToDoubleFunction<? super T>)` |
| `IntStream` | `Stream<Integer>` | `boxed()` |
| `LongStream` | `Stream<Long>` | `boxed()` |
| `DoubleStream` | `Stream<Double>` | `boxed()` |
| `IntStream` | `Stream<R>` | `mapToObj(IntFunction<? extends R>)` |
| `IntStream` | `LongStream` | `asLongStream()` |
| `IntStream` | `DoubleStream` | `asDoubleStream()` |
| `LongStream` | `DoubleStream` | `asDoubleStream()` |

Đừng đổi qua lại chỉ vì thói quen: chuyển primitive → object → primitive có thể làm mất lợi thế tránh wrapper trong các phép toán trung gian.

### Khi `boxed()` là cần thiết

~~~java
List<Integer> values = IntStream.rangeClosed(1, 4)
        .boxed()
        .toList();
// [1, 2, 3, 4]
~~~

`List<Integer>` đòi đối tượng `Integer` vì generic không chấp nhận `int`. Boxing tại **ranh giới cần lưu trong List** là hợp lý, không phải lỗi. Vấn đề chỉ là boxing **sớm hơn mức cần thiết** khi phần lớn công việc vẫn là số học.

Nếu kết quả là mảng nguyên thủy, không cần boxed:

~~~java
int[] squares = IntStream.rangeClosed(1, 4)
        .map(n -> n * n)
        .toArray();
// [1, 4, 9, 16]
~~~

### Khi `mapToObj` là lựa chọn đúng

Nếu mục tiêu là dữ liệu đối tượng như chuỗi, bản ghi hay DTO, hãy đổi sang `Stream<R>`:

~~~java
List<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "S" + n)
        .toList();
// [S1, S2, S3]
~~~

Đây là thay đổi **loại dữ liệu có chủ đích**, không phải boxing thừa. `mapToObj` nhận `IntFunction<R>`, còn `boxed()` chỉ bọc giá trị nguyên thủy vào wrapper tương ứng.

### `flatMapToInt` thay vì tạo `Stream<Integer>` ở giữa

Với một `Stream<List<Integer>>`, có thể flatten thành primitive stream:

~~~java
List<List<Integer>> groups = List.of(
        List.of(1, 2),
        List.of(3, 4)
);
int sum = groups.stream()
        .flatMapToInt(group -> group.stream().mapToInt(Integer::intValue))
        .sum();
// 10
~~~

Nguồn danh sách chứa wrapper, nên vẫn cần unboxing tại ranh giới. Nhưng sau `flatMapToInt` các phép tổng hợp dùng `IntStream`. Nếu dữ liệu đầu vào được lưu ở mảng `int[]`, có thể sử dụng `flatMapToInt(Arrays::stream)` trên `Stream<int[]>` để tránh wrapper ngay từ đầu.

## 7. Chương trình Java 17+ đầy đủ

Đặt mã sau vào tệp **`PrimitiveStreamDemo.java`**:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.OptionalInt;
import java.util.stream.IntStream;

public class PrimitiveStreamDemo {
    record Sale(String sku, int quantity, long cents, double rating) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 2, 1_500L, 4.0),
                new Sale("B", 3, 2_600L, 4.5),
                new Sale("C", 1, 900L, 3.5),
                new Sale("D", 4, 1_000L, 5.0)
        );

        int quantity = sales.stream().mapToInt(Sale::quantity).sum();
        long cents = sales.stream().mapToLong(Sale::cents).sum();
        double averageRating = sales.stream().mapToDouble(Sale::rating).average().orElse(0.0);
        IntSummaryStatistics stats = sales.stream()
                .mapToInt(Sale::quantity).summaryStatistics();

        int boxedSum = sales.stream().map(Sale::quantity)
                .reduce(0, Integer::sum);
        int flatQuantity = List.of(List.of(1, 2), List.of(3, 4)).stream()
                .flatMapToInt(group -> group.stream().mapToInt(Integer::intValue))
                .sum();

        OptionalInt maximum = sales.stream().mapToInt(Sale::quantity).max();
        List<String> labels = IntStream.rangeClosed(1, 3)
                .mapToObj(n -> "S" + n).toList();
        List<Integer> boxed = IntStream.rangeClosed(1, 4).boxed().toList();
        long squares = IntStream.rangeClosed(1, 4).mapToLong(n -> (long) n * n).sum();
        long safeWideSum = IntStream.of(Integer.MAX_VALUE, 1).asLongStream().sum();

        System.out.println("quantity=" + quantity);
        System.out.println("cents=" + cents);
        System.out.println("averageRating=" + averageRating);
        System.out.println("statistics=" + stats.getCount() + "/" + stats.getMin()
                + "/" + stats.getMax() + "/" + stats.getSum());
        System.out.println("boxedSum=" + boxedSum);
        System.out.println("flatQuantity=" + flatQuantity);
        System.out.println("maximum=" + maximum.orElse(-1));
        System.out.println("labels=" + labels);
        System.out.println("boxed=" + boxed);
        System.out.println("squares=" + squares);
        System.out.println("safeWideSum=" + safeWideSum);
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac PrimitiveStreamDemo.java
java PrimitiveStreamDemo
~~~

**Stdout chính xác:**

~~~text
quantity=10
cents=6000
averageRating=4.25
statistics=4/1/4/10
boxedSum=10
flatQuantity=10
maximum=4
labels=[S1, S2, S3]
boxed=[1, 2, 3, 4]
squares=30
safeWideSum=2147483648
~~~

Giải thích:

1. `mapToInt(Sale::quantity).sum()` cộng số lượng 2 + 3 + 1 + 4 = 10 mà không tạo `Stream<Integer>` trung gian.
2. `mapToLong(Sale::cents).sum()` cộng các giá trị tiền theo đơn vị cent, kết quả `6000`; không dùng floating point để tính tiền.
3. `mapToDouble(Sale::rating).average()` cho trung bình `4.25`; `orElse(0.0)` chỉ dùng nếu không có phần tử.
4. `summaryStatistics()` gom bốn số lượng: count 4, min 1, max 4, sum 10.
5. `boxedSum` bằng kết quả nhưng dùng `Stream<Integer>` và `reduce` boxed; `flatQuantity` flatten các nhóm số rồi tính bằng `IntStream`.
6. `maximum` là `OptionalInt`; `labels` chuyển sang chuỗi bằng `mapToObj`; `boxed` tạo `List<Integer>` khi đầu ra thực sự cần wrapper.
7. `squares` tính 1² + 2² + 3² + 4² = 30. `safeWideSum` mở rộng `int` lên `long` trước khi cộng để nhận 2.147.483.648 mà không tràn `int`.

Mỗi lời gọi `sales.stream()` tạo một Stream mới trên cùng nguồn list; Stream đã bị tiêu thụ sau terminal thì không thể tái sử dụng. Với JDK 17, ví dụ đã được biên dịch bằng `javac --release 17` và chạy kiểm chứng đúng phần stdout.

## 8. Những nguồn boxing thường bị bỏ qua

### Collection chứa wrapper ngay từ đầu

`List<Integer>` luôn chứa tham chiếu wrapper; chuyển sang `IntStream` không thay đổi cấu trúc lưu trữ gốc. Nếu hệ thống chạy tính toán số nặng và kiểm soát được format dữ liệu, `int[]`, `long[]` hoặc cấu trúc primitive chuyên biệt có thể phù hợp hơn.

Tuy vậy, không nhất thiết chuyển mọi `List<Integer>` sang mảng: nếu cần API object/generic, dữ liệu nhỏ, hoặc phần số học không phải điểm nghẽn, độ dễ đọc và khả năng tương thích có thể quan trọng hơn mức cấp phát tối ưu.

### `map` trong Stream đối tượng

~~~java
Stream<Integer> doubled = values.stream().map(n -> n * 2);
~~~

`doubled` mang kiểu `Stream<Integer>`; pipeline phải biểu diễn kết quả dưới dạng wrapper ở cấp kiểu. Chọn:

~~~java
IntStream doubledPrimitive = values.stream()
        .mapToInt(Integer::intValue)
        .map(n -> n * 2);
~~~

Bằng cách này, sau chuyển đổi, toán tử `map(IntUnaryOperator)` dùng kiểu primitive.

### Boxing trong collector

~~~java
List<Integer> result = IntStream.range(0, 1000)
        .boxed()
        .collect(Collectors.toList());
~~~

Khi đích cần `List<Integer>`, boxing là cần thiết. Nhưng nếu cuối cùng chỉ cần tổng, không tạo list để rồi `stream()` lại:

~~~java
int total = IntStream.range(0, 1000).sum();
~~~

Cả hai đoạn minh họa nằm trong phương thức; đoạn collector cần `java.util.stream.Collectors` và `List`.

### Generic API không chuyên biệt

Các giao diện generic như `Function<T, R>`, `Predicate<T>` và `Consumer<T>` làm việc với type argument là reference type. Khi viết pipeline số với primitive specialization, hãy dùng functional interface tương ứng: `IntUnaryOperator`, `IntPredicate`, `IntConsumer`, `ToIntFunction<T>`, `IntToLongFunction`... Chúng biểu diễn tham số/giá trị trả về ở dạng nguyên thủy.

Ví dụ:

~~~java
IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .forEach(System.out::println);
~~~

`filter` nhận `IntPredicate`; `map` nhận `IntUnaryOperator`; `forEach` nhận `IntConsumer`. Đoạn này là minh họa chạy trong phương thức, không phải ví dụ stdout chính của bài.

## 9. Cẩn trọng về độ đúng: tràn số, floating point, null

### Tràn số không liên quan trực tiếp tới boxing

`IntStream.sum()` trả `int`; nếu tổng vượt miền `int`, kết quả bị tràn theo số học Java. Dùng `asLongStream().sum()`, `mapToLong(...)` hoặc `LongStream` khi kết quả yêu cầu `long`. Nhưng `long` cũng có giới hạn. Đối với giá trị tiền lớn cần tính chính xác vượt phạm vi `long`, có thể dùng `BigInteger` hoặc `BigDecimal` theo bài toán; object ở đây là **yêu cầu về miền giá trị/độ chính xác**, không phải boxing thừa.

### Số thực không chính xác tuyệt đối

`DoubleStream` xử lý `double` theo IEEE 754. Những số thập phân như `0.1` có thể không biểu diễn chính xác nhị phân; tổng hoặc trung bình dễ có sai số làm tròn. Nếu tính tiền, dùng số nguyên đơn vị nhỏ nhất (cents) trong phạm vi hợp lý hoặc `BigDecimal`, không thay bằng `double` chỉ vì muốn tránh boxing.

Với `DoubleStream`, phép tổng hợp cũng phải xử lý `NaN` và giá trị vô hạn theo hợp đồng Java. Thứ tự cộng floating point có thể làm kết quả thay đổi do phép cộng không kết hợp chính xác về mặt toán học máy tính, đặc biệt trong parallel stream.

### Wrapper null sẽ gây lỗi khi unbox

~~~java
List<Integer> nullableValues = Arrays.asList(1, null, 3);
// Có thể ném NullPointerException khi gặp null:
// int sum = nullableValues.stream().mapToInt(Integer::intValue).sum();
~~~

`mapToInt(Integer::intValue)` yêu cầu phần tử `Integer` không null. Nếu chính sách dữ liệu là bỏ qua null, lọc trước:

~~~java
int sum = nullableValues.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
// 4
~~~

Cần `Arrays` và `Objects` từ `java.util`. Nếu null mang ý nghĩa nghiệp vụ khác (thiếu dữ liệu, lỗi nhập), không tự loại bỏ mà không nêu chính sách.

## 10. Parallel stream và hiệu năng thực tế

Primitive streams giúp giảm nhu cầu wrapper khi tính toán số, nhưng **không đồng nghĩa mọi pipeline primitive đều nhanh**. Hiệu năng thực tế phụ thuộc:

- Quy mô đầu vào, bộ nhớ cache CPU, cách dữ liệu được lưu trữ.
- Chi phí trích xuất thuộc tính từ đối tượng nguồn.
- Lambda/JIT và khả năng loại bỏ đối tượng tạm.
- Toán tử stateful như `sorted` hoặc `distinct` và yêu cầu giữ encounter order.
- Chi phí chia/gộp công việc khi `parallel()`.
- Chi phí terminal, collector và bộ nhớ đích.

Một phép tính `IntStream.range(...).sum()` rất đơn giản có thể nhanh và ít cấp phát; nhưng không nên tự suy ra nó luôn nhanh hơn vòng lặp `for`. Stream là abstraction hữu ích; vòng lặp nguyên thủy trực tiếp đôi khi phù hợp nhất cho vùng xử lý cực nóng (*hot path*).

Với parallel reduction, toán tử phải phù hợp để gộp các nhánh; tránh mutate shared accumulator trong `forEach`. Thay vì:

~~~java
// Không làm kiểu này với parallel stream:
// int[] sum = {0};
// numbers.parallelStream().forEach(n -> sum[0] += n);
~~~

hãy dùng phép giảm:

~~~java
long total = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

Đây là đoạn minh họa với `List<Integer> numbers`, có thể dùng khi miền tổng cần long. Dùng chung mảng một phần tử không đồng bộ gây data race và có thể mất cập nhật. Ngược lại, primitive `sum()` có hợp đồng giảm thích hợp cho cách triển khai song song.

Để khẳng định lợi ích hiệu năng, nên đo bằng **JMH** hoặc benchmark có warm-up và dữ liệu đại diện, quan sát GC allocation rate, throughput và latency. Đừng chỉ chạy một lần `System.nanoTime()`, vì tối ưu JIT, dead-code elimination và nhiễu hệ thống dễ khiến kết luận sai. Không tối ưu boxing bằng cách làm code khó hiểu nếu dữ liệu đo không cho thấy lợi ích đáng kể.

## 11. Lỗi thường gặp

**Dùng `Stream<Integer>` xuyên suốt chỉ để cộng tổng.** Nếu có thể, trích xuất bằng `mapToInt` và dùng `sum`, `average` hay `summaryStatistics`.

**Gọi `boxed()` quá sớm.** Nếu cần lưu `List<Integer>` thì boxing tại ranh giới là hợp lý. Nếu ngay sau đó lại `mapToInt(Integer::intValue)` để tổng, hãy xem có thể giữ `IntStream` đến terminal số học hay không.

**Nghĩ primitive stream làm nguồn `List<Integer>` hết wrapper.** Không đúng: wrapper đã tồn tại trong list; chỉ các bước sau chuyển đổi được chuyên biệt hóa.

**Nhầm `sum()` với phương thức trả long.** `IntStream.sum()` trả `int`, `LongStream.sum()` trả `long`. `IntSummaryStatistics.getSum()` là `long`; mở rộng số trước khi cộng nếu cần.

**Dùng `double` cho tiền chỉ để nhanh.** Sai số floating point có thể không phù hợp nghiệp vụ. Chọn kiểu theo yêu cầu độ chính xác, không chỉ theo boxing.

**Bỏ qua null trong `List<Integer>`.** Unboxing null ném `NullPointerException`. Quyết định rõ bỏ qua, báo lỗi hay dùng giá trị thay thế.

**Tự tạo accumulator mutable trong parallel stream.** Dễ xảy ra race hoặc sai lệch. Hãy dùng terminal reduction có hợp đồng đúng.

**Kỳ vọng mọi wrapper cấp phát tại runtime.** JIT có thể loại bỏ cấp phát trong một số tình huống; đo thực tế thay vì suy diễn byte cấp phát cố định từ code nguồn.

**Tái dùng primitive stream sau terminal.** `IntStream` cũng single-use như `Stream<T>`. Nếu cần tính nhiều chỉ số, có thể dùng `summaryStatistics()` hoặc tạo stream mới từ nguồn phù hợp.

## 12. Checklist chọn kiểu và thao tác

| Nhu cầu | Chọn cách viết |
| --- | --- |
| Tổng số lượng `int` | `source.stream().mapToInt(Entity::quantity).sum()` |
| Tổng giá trị `long` | `source.stream().mapToLong(Entity::amount).sum()` |
| Trung bình điểm số | `source.stream().mapToDouble(Entity::score).average()` |
| Min/max số nguyên | `source.stream().mapToInt(Entity::quantity).max()` |
| Lấy nhiều thống kê `int` | `...mapToInt(...).summaryStatistics()` |
| Tổng có thể vượt `int` | `...mapToLong(...).sum()` hoặc `IntStream.asLongStream().sum()` |
| Từ `int[]` | `Arrays.stream(intArray)` |
| Cần `int[]` kết quả | `IntStream...toArray()` |
| Cần `List<Integer>` | `IntStream...boxed().toList()` |
| Cần `List<String>` từ các số | `IntStream...mapToObj(...).toList()` |
| Nối nhóm số từ `Stream<List<Integer>>` | `flatMapToInt(group -> group.stream().mapToInt(Integer::intValue))` |
| Số thập phân tiền tệ chính xác | `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất, theo hợp đồng nghiệp vụ |

**Quy tắc áp dụng:** Chọn **primitive stream từ sớm khi pipeline chủ yếu thực hiện phép toán trên số**, giữ kiểu nguyên thủy xuyên suốt `filter`/`map`/`reduce`/`sum`, rồi chỉ chuyển sang wrapper hoặc đối tượng **khi đích sử dụng thực sự đòi hỏi**. Mục tiêu là giảm boxing không cần thiết mà vẫn giữ đúng miền giá trị, chính sách null, độ chính xác và ý nghĩa nghiệp vụ.