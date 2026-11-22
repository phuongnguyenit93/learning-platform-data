# `boxed()`, `mapToObj()` và chuyển đổi giữa các Stream nguyên thủy trong Java

## 1. Vì sao Java có Stream nguyên thủy?

Java Stream API có kiểu tổng quát `Stream<T>` để xử lý các đối tượng, nhưng `int`, `long` và `double` là **kiểu nguyên thủy** (*primitive*), không phải object để dùng trực tiếp làm tham số kiểu generic. Vì vậy JDK cung cấp ba stream chuyên biệt:

- `IntStream`: luồng các giá trị `int`.
- `LongStream`: luồng các giá trị `long`.
- `DoubleStream`: luồng các giá trị `double`.

Các stream này nằm trong `java.util.stream`, có các toán tử dành riêng cho primitive như `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()`, và có thể giảm chi phí boxing/unboxing trong những pipeline xử lý số lớn.

Ví dụ:

```java
import java.util.stream.IntStream;

int total = IntStream.rangeClosed(1, 5).sum();
System.out.println(total); // 15
```

`IntStream.rangeClosed(1,5)` sinh các số 1,2,3,4,5. Terminal `sum()` trả một `int`, không cần tạo `Integer` cho từng phần tử trong biểu diễn logic của pipeline.

Khi dữ liệu phải được dùng bởi API làm việc với object (`List<Integer>`, `Collectors.groupingBy`, `Map`, `Stream<String>`...) hoặc cần biến mỗi số thành một đối tượng mới, ta phải chọn phép chuyển đổi thích hợp. Ba câu hỏi chính:

1. **`boxed()`:** Giữ nguyên giá trị số nhưng chuyển sang **wrapper object**?
2. **`mapToObj()`:** Dùng mỗi giá trị primitive để tạo **object thuộc kiểu bất kỳ**?
3. **`mapToInt`/`mapToLong`/`mapToDouble`, `asLongStream`/`asDoubleStream`:** Chuyển **loại stream** hoặc **kiểu số** như thế nào?

## 2. `boxed()`: từ primitive stream thành `Stream` wrapper

Chữ ký có thể hình dung như sau:

```java
// IntStream:
Stream<Integer> boxed();

// LongStream:
Stream<Long> boxed();

// DoubleStream:
Stream<Double> boxed();
```

Ba `boxed()` là các phương thức **không nhận tham số** của từng primitive stream. Chúng tạo object stream tương ứng với wrapper của phần tử primitive:

| Đầu vào | Gọi | Kiểu kết quả |
| --- | --- | --- |
| `IntStream` | `.boxed()` | `Stream<Integer>` |
| `LongStream` | `.boxed()` | `Stream<Long>` |
| `DoubleStream` | `.boxed()` | `Stream<Double>` |

Ví dụ:

```java
List<Integer> numbers = IntStream.rangeClosed(1, 4)
        .boxed()
        .toList();

System.out.println(numbers); // [1, 2, 3, 4]
```

Cần `import java.util.List;` và `import java.util.stream.IntStream;` khi đặt trong phương thức. Mỗi `int` từ IntStream được chuyển thành một giá trị wrapper `Integer` để cung cấp qua `Stream<Integer>`. Việc có object không có nghĩa bạn có thể dựa vào danh tính `==` của từng wrapper: khi xử lý số, so sánh nội dung bằng phép toán số hoặc `equals` theo kiểu phù hợp.

### Tại sao không dùng ngay `Stream<int>`?

`Stream<int>` **không hợp lệ** vì generic type argument của Java phải là reference type. Nếu cần object stream, hãy dùng `Stream<Integer>` hoặc gọi `boxed()` từ `IntStream`.

### `boxed()` không tạo danh sách ngay

`boxed()` là **intermediate operation** trả một stream mới, không trả `List<Integer>`. Phải có terminal operation khi cần dữ liệu cụ thể:

```java
Stream<Integer> boxed = IntStream.of(10, 20).boxed();
List<Integer> result = boxed.toList(); // [10, 20]
```

Tương tự mọi stream, đối tượng `boxed` không được dùng lại sau khi đã tiêu thụ. `Stream.toList()` (Java 16+) trả một List **không hỗ trợ các phương thức sửa đổi** như `add`/`remove`. Nếu muốn một danh sách mutable:

```java
List<Integer> mutable = new java.util.ArrayList<>(
        IntStream.of(10, 20).boxed().toList()
);
mutable.add(30);
System.out.println(mutable); // [10, 20, 30]
```

Chọn `boxed()` khi **chỉ cần đổi `int → Integer`**, `long → Long` hoặc `double → Double` để tương thích API dùng reference type, chứ không cần đổi nội dung thành một mô hình mới.

## 3. `mapToObj()`: từ primitive sang một object tùy ý

`mapToObj` nhận hàm ánh xạ **một giá trị primitive → object kiểu `U`**. Dạng tương ứng:

```java
// IntStream:
<U> Stream<U> mapToObj(IntFunction<? extends U> mapper);

// LongStream:
<U> Stream<U> mapToObj(LongFunction<? extends U> mapper);

// DoubleStream:
<U> Stream<U> mapToObj(DoubleFunction<? extends U> mapper);
```

Trong khi `boxed()` chỉ cho wrapper cùng giá trị số, `mapToObj` có thể tạo `String`, `record`, DTO hoặc object khác.

Ví dụ:

```java
List<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "Item-" + n)
        .toList();

System.out.println(labels); // [Item-1, Item-2, Item-3]
```

Kiểu pipeline:

```text
IntStream            --mapToObj(n -> "Item-" + n)--> Stream<String>
1, 2, 3                                             "Item-1", "Item-2", "Item-3"
```

Nếu muốn object giữ nhiều thông tin:

```java
record Score(String id, int points) {}

List<Score> scores = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> new Score("S" + n, n * 10))
        .toList();

// [Score[id=S1, points=10], Score[id=S2, points=20],
//  Score[id=S3, points=30]]
```

`record` được hỗ trợ chính thức từ Java 16. Đây là đoạn **minh họa** để đặt trong một lớp thích hợp; chương trình Java 17 hoàn chỉnh xuất hiện ở phần sau.

### Hai cách tương đương về nội dung, không phải về biểu đạt

Đối với mỗi `int`, có thể tạo `Integer` bằng cả hai cách:

```java
Stream<Integer> a = IntStream.of(1, 2).boxed();
Stream<Integer> b = IntStream.of(1, 2).mapToObj(Integer::valueOf);
```

Cả hai đều tạo luồng object wrapper với nội dung 1,2. Nhưng `boxed()` **nêu rõ mục đích đóng hộp** và ngắn gọn hơn. `mapToObj` phù hợp khi ánh xạ sang kiểu khác như `String`, `Score` hoặc `BigDecimal`.

Không cần viết `.boxed().map(n -> "Item-" + n)` nếu có thể biểu diễn trực tiếp bằng `.mapToObj(n -> "Item-" + n)`: phiên bản trực tiếp giúp tránh bước wrapper trung gian về mặt mô hình API. Hiệu năng thực tế vẫn tùy JVM và workload; muốn khẳng định nhanh/chậm hơn cần benchmark.

## 4. Chuyển ngược: `Stream<T>` sang `IntStream`, `LongStream`, `DoubleStream`

Trên object stream, có ba phương thức quan trọng:

```java
IntStream mapToInt(ToIntFunction<? super T> mapper);
LongStream mapToLong(ToLongFunction<? super T> mapper);
DoubleStream mapToDouble(ToDoubleFunction<? super T> mapper);
```

Mapper lấy một object `T` và sinh một giá trị primitive cụ thể. Ví dụ chuyển `Stream<String>` thành `IntStream`:

```java
int total = Stream.of("12", "8", "5")
        .mapToInt(Integer::parseInt)
        .sum();

System.out.println(total); // 25
```

Ở đây:

- `Stream.of(...)` có kiểu `Stream<String>`.
- `Integer.parseInt(String)` trả `int`, phù hợp `ToIntFunction<String>`.
- `mapToInt` trả `IntStream`.
- `sum()` là terminal operation của `IntStream`, trả `int`.

Chuyển wrapper sang primitive:

```java
List<Integer> values = List.of(2, 4, 6);

double mean = values.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElseThrow();

System.out.println(mean); // 4.0
```

`average()` của `IntStream` trả `OptionalDouble` vì một stream rỗng không có trung bình. Với dữ liệu ở ví dụ, trung bình là 4.0; nếu nguồn rỗng và gọi `orElseThrow()`, ngoại lệ `NoSuchElementException` xuất hiện. Đừng gọi `getAsDouble()` không kiểm tra trên `OptionalDouble.empty()`.

### Chuyển dữ liệu có thể null phải xử lý trước khi unboxing

`Stream<Integer>` có thể chứa tham chiếu `null` nếu được tạo từ nguồn cho phép null (khác `List.of`). Khi gọi `Integer::intValue` trên null, nó ném `NullPointerException`:

```java
List<Integer> values = new java.util.ArrayList<>();
values.add(2);
values.add(null);
values.add(5);

// SAI runtime: gọi intValue() trên null.
// int total = values.stream().mapToInt(Integer::intValue).sum();

int safeTotal = values.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(safeTotal); // 7
```

Chỉ bỏ null nếu quy tắc nghiệp vụ cho phép. Nếu null biểu thị dữ liệu bị lỗi hoặc thiếu dữ liệu bắt buộc, hãy validate và báo lỗi thay vì im lặng bỏ qua.

## 5. Chuyển đổi trực tiếp giữa các loại Stream primitive

Ba stream nguyên thủy có những phép chuyển kiểu chuyên biệt. Sơ đồ thường dùng:

```text
IntStream  --asLongStream()----> LongStream
IntStream  --asDoubleStream()--> DoubleStream
LongStream --asDoubleStream()--> DoubleStream

IntStream  --mapToLong(IntToLongFunction)--> LongStream
IntStream  --mapToDouble(IntToDoubleFunction)--> DoubleStream
LongStream --mapToInt(LongToIntFunction)--> IntStream
LongStream --mapToDouble(LongToDoubleFunction)--> DoubleStream
DoubleStream --mapToInt(DoubleToIntFunction)--> IntStream
DoubleStream --mapToLong(DoubleToLongFunction)--> LongStream
```

### `asLongStream()`: mở rộng `int` sang `long`

```java
long sum = IntStream.rangeClosed(1, 4)
        .asLongStream()
        .sum();

System.out.println(sum); // 10
```

`asLongStream()` chuyển mỗi `int` thành `long` theo primitive widening conversion. Mọi giá trị `int` đều biểu diễn chính xác bằng `long`; cách này còn hữu ích khi cần tổng lớn hơn phạm vi `int`, **nhưng phép cộng `long` vẫn có thể overflow** nếu tổng quá lớn.

### `asDoubleStream()`: mở rộng sang `double`

```java
double average = IntStream.of(2, 4, 6)
        .asDoubleStream()
        .average()
        .orElseThrow();

System.out.println(average); // 4.0
```

Tất cả giá trị `int` đều được biểu diễn chính xác thành `double`, vì `double` có độ chính xác số nguyên đủ cho khoảng 32-bit. Tuy nhiên **`LongStream.asDoubleStream()` không bảo đảm mọi giá trị `long` được giữ chính xác**, bởi `double` chỉ có 53 bit độ chính xác của phần trị.

### `mapToLong`/`mapToDouble` để tùy biến phép biến đổi

```java
long squares = IntStream.of(2, 3, 4)
        .mapToLong(n -> (long) n * n)
        .sum();

System.out.println(squares); // 29
```

Khác `asLongStream()` chỉ đổi kiểu, `mapToLong(...)` có thể vừa đổi kiểu vừa biến đổi giá trị. Ép `(long) n` **trước khi nhân** tránh phép nhân trung gian trong phạm vi `int` khi n đủ lớn.

## 6. Thu hẹp kiểu: hãy làm rõ mất dữ liệu

Không có `LongStream.asIntStream()` vì `long → int` là **narrowing conversion**, có thể làm mất giá trị. Thay vào đó `LongStream.mapToInt(LongToIntFunction)` buộc bạn nêu rõ phép biến đổi.

Ví dụ:

```java
List<Integer> small = LongStream.of(10L, 20L)
        .mapToInt(Math::toIntExact)
        .boxed()
        .toList();

System.out.println(small); // [10, 20]
```

`Math.toIntExact(long)` ném `ArithmeticException` nếu giá trị ngoài phạm vi của `int`. Đây là lựa chọn tốt khi yêu cầu nghiệp vụ là **không được mất thông tin**.

Ngược lại:

```java
int narrowed = (int) 3_000_000_000L;
System.out.println(narrowed); // -1294967296
```

Ép kiểu primitive `(int)` có thể cho kết quả đã bị mất các bit cao. Dùng `mapToInt(n -> (int) n)` mà không kiểm tra có thể dẫn đến số sai âm thầm. Với `double → int/long`, Java có quy tắc chuyển dấu phẩy động sang số nguyên (trong đó phần thập phân bị loại bỏ theo hướng về 0; các trường hợp NaN/ngoài phạm vi có quy tắc riêng). Nếu nghiệp vụ cần làm tròn, hãy áp dụng chính sách làm tròn rõ ràng và kiểm tra phạm vi trước khi đổi.

### Độ chính xác khi `long → double`

Ví dụ minh họa có thể kiểm chứng:

```java
long original = 9_007_199_254_740_993L; // 2^53 + 1
double converted = (double) original;
long roundTrip = (long) converted;

System.out.println(original == roundTrip); // false
```

Số `2^53 + 1` không biểu diễn chính xác trong `double` nhị phân chuẩn. Vì vậy `LongStream.asDoubleStream()` có thể làm mất độ chính xác của số nguyên lớn dù trình biên dịch cho phép chuyển kiểu. Không dùng đường chuyển này cho mã định danh/số tiền nguyên lớn nếu cần bảo toàn chính xác. Với tiền tệ, ưu tiên `BigDecimal` hoặc kiểu số nguyên có đơn vị rõ ràng, cùng chính sách làm tròn được xác định.

## 7. Chương trình Java 17 hoàn chỉnh: chuyển đổi và tổng hợp dữ liệu

Ví dụ dưới đây xử lý các điểm số, giá trị `long` và chuỗi số. Mục tiêu là xác nhận chính xác kiểu trả về, việc đóng hộp, chuyển sang object, quay về primitive và phát hiện mất mát khi thu hẹp kiểu.

Tạo tệp **`PrimitiveStreamConversionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class PrimitiveStreamConversionDemo {
    record Score(String id, int points) {}

    public static void main(String[] args) {
        // 1. boxed(): IntStream -> Stream<Integer> -> List<Integer>.
        List<Integer> boxedNumbers = IntStream.rangeClosed(1, 4)
                .boxed()
                .toList();
        System.out.println("Boxed: " + boxedNumbers);

        // 2. mapToObj(): IntStream -> Stream<String>.
        List<String> labels = IntStream.rangeClosed(1, 3)
                .mapToObj(n -> "Item-" + n)
                .toList();
        System.out.println("Labels: " + labels);

        // 3. mapToObj(): tạo record mới thay vì chỉ đóng hộp.
        List<Score> scores = IntStream.rangeClosed(1, 3)
                .mapToObj(n -> new Score("S" + n, n * 10))
                .toList();
        System.out.println("Scores: " + scores);

        // 4. Object Stream -> IntStream để tổng hợp số.
        int parsedSum = Stream.of("7", "11", "2")
                .mapToInt(Integer::parseInt)
                .sum();
        System.out.println("Parsed sum: " + parsedSum);

        // 5. boxed() cho phép dùng collector trên Stream<Integer>.
        Map<String, List<Integer>> groups = IntStream.rangeClosed(1, 6)
                .boxed()
                .collect(Collectors.groupingBy(
                        n -> n % 2 == 0 ? "even" : "odd",
                        TreeMap::new,
                        Collectors.toList()
                ));
        System.out.println("Grouped: " + groups);

        // 6. IntStream -> LongStream qua primitive widening.
        long longSum = IntStream.rangeClosed(1, 4)
                .asLongStream()
                .sum();
        System.out.println("Long sum: " + longSum);

        // 7. IntStream -> DoubleStream rồi tính trung bình.
        double mean = IntStream.of(2, 4, 6)
                .asDoubleStream()
                .average()
                .orElseThrow();
        System.out.println("Mean: " + mean);

        // 8. LongStream -> Stream<String> bằng mapToObj().
        List<String> longLabels = LongStream.of(10L, 20L)
                .mapToObj(n -> "L" + n)
                .toList();
        System.out.println("Long labels: " + longLabels);

        // 9. DoubleStream -> Stream<Double> bằng boxed().
        List<Double> decimals = DoubleStream.of(1.5, 2.5)
                .boxed()
                .toList();
        System.out.println("Decimals: " + decimals);

        // 10. LongStream -> IntStream: chuyển đúng phạm vi.
        List<Integer> checked = LongStream.of(10L, 20L)
                .mapToInt(Math::toIntExact)
                .boxed()
                .toList();
        System.out.println("Checked narrowing: " + checked);

        // 11. Phát hiện giá trị long không vừa int.
        try {
            LongStream.of(3_000_000_000L)
                    .mapToInt(Math::toIntExact)
                    .sum();
        } catch (ArithmeticException ex) {
            System.out.println("Narrowing rejected: ArithmeticException");
        }

        // 12. Dữ liệu wrapper có null phải được kiểm tra.
        List<Integer> possiblyNull = new ArrayList<>();
        possiblyNull.add(2);
        possiblyNull.add(null);
        possiblyNull.add(5);
        int validSum = possiblyNull.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("Null-safe sum: " + validSum);

        // 13. Map một record sang primitive bằng field số.
        int scoreSum = scores.stream()
                .mapToInt(Score::points)
                .sum();
        System.out.println("Score sum: " + scoreSum);

        // 14. Long -> double có thể mất độ chính xác.
        long large = 9_007_199_254_740_993L;
        long roundTrip = (long) ((double) large);
        System.out.println("Precise round trip: " + (large == roundTrip));

        // 15. Stream rỗng: không có giá trị average.
        System.out.println("Empty average: "
                + IntStream.empty().average().isEmpty());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 PrimitiveStreamConversionDemo.java
java PrimitiveStreamConversionDemo
```

**Stdout xác định:**

```text
Boxed: [1, 2, 3, 4]
Labels: [Item-1, Item-2, Item-3]
Scores: [Score[id=S1, points=10], Score[id=S2, points=20], Score[id=S3, points=30]]
Parsed sum: 20
Grouped: {even=[2, 4, 6], odd=[1, 3, 5]}
Long sum: 10
Mean: 4.0
Long labels: [L10, L20]
Decimals: [1.5, 2.5]
Checked narrowing: [10, 20]
Narrowing rejected: ArithmeticException
Null-safe sum: 7
Score sum: 60
Precise round trip: false
Empty average: true
```

### Đọc kết quả theo kiểu

1. `boxedNumbers` có kiểu `List<Integer>`, nội dung [1,2,3,4]. `boxed()` không đổi số, chỉ tạo object stream wrapper.
2. `labels` có kiểu `List<String>`, nội dung Item-1, Item-2, Item-3. `mapToObj` đã áp dụng quy tắc biến đổi sang object khác.
3. `scores` có kiểu `List<Score>`, record tự cung cấp `toString()` theo định dạng tên kiểu và các component. `Score("S1",10)` được in thành `Score[id=S1, points=10]`.
4. `parsedSum` bằng `7+11+2=20`. `mapToInt(Integer::parseInt)` tạo IntStream để dùng `sum()`.
5. `groups` tạo `Stream<Integer>` bằng `boxed()` rồi `Collectors.groupingBy` với `TreeMap::new`, nên thứ tự khóa hiển thị xác định là `even` trước `odd`. Giá trị nhóm giữ thứ tự gặp phần tử: even=[2,4,6], odd=[1,3,5].
6. `asLongStream` giữ chính xác các giá trị 1..4 và tổng là 10. `asDoubleStream` tạo các số 2.0,4.0,6.0 nên trung bình là 4.0.
7. `LongStream.mapToObj` tạo nhãn từ long. `DoubleStream.boxed` trả wrapper Double.
8. `Math.toIntExact` thành công với 10L,20L nhưng ném `ArithmeticException` với 3_000_000_000L, thay vì âm thầm đổi số không chính xác.
9. `Objects::nonNull` loại tham chiếu null trước khi unboxing. Nếu null có ý nghĩa nghiệp vụ riêng, cần biểu diễn và xử lý thay vì bỏ qua.
10. `scores.stream().mapToInt(Score::points).sum()` trả `10+20+30=60`.
11. Giá trị long lớn hơn khả năng biểu diễn số nguyên chính xác của double nên round trip trả false. `IntStream.empty().average()` trả `OptionalDouble.empty()` và `isEmpty()` là true.

Toàn bộ chương trình sử dụng nguồn có thứ tự và terminal phù hợp; output không phụ thuộc vào thứ tự thực thi của parallel stream hay danh tính object wrapper.

## 8. Khi nào dùng `boxed` trước collector?

Nhiều collector như `Collectors.groupingBy` hoặc `Collectors.toMap` làm việc với **`Stream<T>`**, không nhận `IntStream` trực tiếp. Khi cần nhóm số theo khóa:

```java
Map<String, List<Integer>> grouped = IntStream.rangeClosed(1, 6)
        .boxed()
        .collect(Collectors.groupingBy(
                n -> n % 2 == 0 ? "even" : "odd",
                TreeMap::new,
                Collectors.toList()
        ));
```

`boxed()` là lựa chọn hợp lý vì nội dung cần gom vẫn là `Integer`. Nhưng khi chỉ muốn **tổng, min, max, average, count**, primitive stream đã có terminal chuyên biệt:

```java
int sum = IntStream.rangeClosed(1, 100).sum();
long count = IntStream.rangeClosed(1, 100).count();
int max = IntStream.rangeClosed(1, 100).max().orElseThrow();
```

Không cần `boxed()` chỉ để gọi `collect(Collectors.summingInt(...))` nếu `sum()` đã giải quyết đúng bài toán. `boxed` có thể tạo thêm boxing overhead so với dùng primitive pipeline liên tục.

### Primitive collect có tồn tại nhưng khác Collector object

Các primitive stream cũng có overload `collect` riêng, ví dụ `IntStream.collect(Supplier<R>, ObjIntConsumer<R>, BiConsumer<R,R>)`. Nó không nhận trực tiếp `Collector<T,A,R>` như `Stream<T>.collect(Collector)`. Vì vậy để sử dụng `Collectors.groupingBy` trên phần tử số nguyên, `boxed()` là đường đi rõ ràng.

## 9. Bảng tra kiểu chuyển đổi quan trọng

| Nguồn | Phương thức | Đích | Dùng khi |
| --- | --- | --- | --- |
| `IntStream` | `boxed()` | `Stream<Integer>` | Dùng generic collector/API đòi object |
| `LongStream` | `boxed()` | `Stream<Long>` | Lấy wrapper long |
| `DoubleStream` | `boxed()` | `Stream<Double>` | Lấy wrapper double |
| `IntStream` | `mapToObj(IntFunction<U>)` | `Stream<U>` | Tạo String/record/DTO |
| `LongStream` | `mapToObj(LongFunction<U>)` | `Stream<U>` | Tạo object từ long |
| `DoubleStream` | `mapToObj(DoubleFunction<U>)` | `Stream<U>` | Tạo object từ double |
| `Stream<T>` | `mapToInt(ToIntFunction<T>)` | `IntStream` | Parse hoặc trích xuất int |
| `Stream<T>` | `mapToLong(ToLongFunction<T>)` | `LongStream` | Trích xuất long |
| `Stream<T>` | `mapToDouble(ToDoubleFunction<T>)` | `DoubleStream` | Trích xuất double |
| `IntStream` | `asLongStream()` | `LongStream` | Widening int → long |
| `IntStream` | `asDoubleStream()` | `DoubleStream` | Widening int → double |
| `LongStream` | `asDoubleStream()` | `DoubleStream` | Widening long → double, có thể mất chính xác |
| `LongStream` | `mapToInt(LongToIntFunction)` | `IntStream` | Thu hẹp có chính sách kiểm tra |
| `DoubleStream` | `mapToInt(DoubleToIntFunction)` | `IntStream` | Áp dụng quy tắc double → int rõ ràng |
| `DoubleStream` | `mapToLong(DoubleToLongFunction)` | `LongStream` | Áp dụng quy tắc double → long rõ ràng |
| `IntStream` | `mapToLong(IntToLongFunction)` | `LongStream` | Vừa chuyển kiểu vừa biến đổi |
| `IntStream` | `mapToDouble(IntToDoubleFunction)` | `DoubleStream` | Vừa chuyển kiểu vừa biến đổi |

Trong Java, các generic `ToIntFunction<? super T>`/`ToLongFunction<? super T>`/`ToDoubleFunction<? super T>` cho phép nhận object đầu vào và trả primitive. Các tên interface chuyên biệt khác có thể cần import từ `java.util.function`; `java.util.stream` là gói chứa Stream.

## 10. Kiểu primitive và phép tính số: tránh hiểu nhầm

### `sum()` không tự chống overflow

`IntStream.sum()` trả `int`, phép cộng có thể overflow nếu kết quả vượt miền `int`. Ví dụ tổng một triệu giá trị lớn có thể không chính xác dù không có boxing.

Nếu tổng có thể vượt `int`, mở rộng sang `long` trước phép tổng hợp:

```java
long total = IntStream.of(1_500_000_000, 1_500_000_000)
        .asLongStream()
        .sum();

System.out.println(total); // 3000000000
```

`IntStream.of(...).sum()` trả `int`, sẽ không giữ được kết quả 3.000.000.000 trong miền `int`. `asLongStream()` mở rộng từng phần tử trước khi cộng nên đủ trong ví dụ này.

Dù `long` lớn hơn, nó vẫn có giới hạn. Khi số liệu có thể vượt giới hạn long, cân nhắc `BigInteger` hoặc `BigDecimal` với định nghĩa độ chính xác phù hợp.

### `average()` của stream rỗng không trả 0

`IntStream.empty().average()` trả `OptionalDouble.empty()`, không trả “giá trị trung bình bằng 0”. Trung bình của một tập không có phần tử **không xác định** theo cách tính thông thường; hãy dùng `orElse(default)` nếu nghiệp vụ thực sự muốn gán một mặc định.

### `DoubleStream` có các đặc tính dấu phẩy động

Phép tính trên `double` có thể gặp NaN, dương/âm vô cùng, và sai số làm tròn. `DoubleStream.boxed()` không làm dữ liệu chính xác hơn; nó chỉ đổi `double` sang `Double` wrapper. Với tiền tệ hoặc kiểm toán, quyết định loại số trước khi chọn stream.

### Wrapper `Integer`, `Long`, `Double` không phải primitive

`Stream<Integer>` chứa reference object và có thể có null nếu nguồn cho phép. `IntStream` không thể có phần tử null: mỗi phần tử đã là một `int`. Nếu cần biểu diễn “có thể không có số”, dùng các mô hình phù hợp như `OptionalInt` cho **một kết quả tùy chọn**, chứ không lén mã hóa null bằng một giá trị 0 hợp lệ.

## 11. Stream dùng một lần và tính lười

Các phương thức `boxed`, `mapToObj`, `mapToInt`, `asLongStream` là **intermediate operations**. Chúng không tự duyệt hết nguồn ngay lập tức mà cấu tạo một pipeline lazy, sẽ được đánh giá khi chạy terminal operation như `sum()`, `toList()`, `collect(...)`.

```java
IntStream numbers = IntStream.of(1, 2, 3);
Stream<Integer> objects = numbers.boxed();

System.out.println(objects.toList()); // [1, 2, 3]

// Sai: nguồn stream đã tham gia pipeline/được tiêu thụ.
// System.out.println(numbers.sum());
```

Cần tính hai kết quả khác nhau thì tạo hai nguồn:

```java
List<Integer> list = IntStream.of(1, 2, 3).boxed().toList();
int sum = IntStream.of(1, 2, 3).sum();
```

Tránh đưa side effect quan trọng vào mapper với giả định nó luôn chạy một lần cho mọi phần tử. Các terminal short-circuit, nguồn bất kỳ, tối ưu hóa và parallel pipeline có thể ảnh hưởng cách thực thi. Việc nối phép chuyển đổi qua nhiều stream không khiến chúng được tự chạy độc lập nếu chưa có terminal.

## 12. Primitive mapping khác object mapping

Trên `IntStream`, phương thức `map` **không** trả `Stream<R>`; nó nhận `IntUnaryOperator` và trả lại `IntStream`:

```java
IntStream doubled = IntStream.rangeClosed(1, 3)
        .map(n -> n * 2);

System.out.println(doubled.boxed().toList()); // [2, 4, 6]
```

Trên `Stream<Integer>`, `map` nhận `Function<Integer,R>` và có thể trả `Stream<R>`:

```java
Stream<String> labels = IntStream.rangeClosed(1, 3)
        .boxed()
        .map(n -> "n=" + n);
```

Cách `mapToObj` trực tiếp:

```java
Stream<String> labels = IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "n=" + n);
```

Nếu cùng phạm vi cục bộ, không thể khai báo hai biến cùng tên `labels` liên tiếp; các đoạn trên là **hai phương án thay thế nhau**, không ghép chung một phương thức. Mục tiêu là nhận diện **kiểu stream ở từng bước**:

- `IntStream.map(IntUnaryOperator)`: int → int.
- `IntStream.mapToObj(IntFunction<R>)`: int → object `R`.
- `Stream<T>.map(Function<T,R>)`: object `T` → object `R`.
- `Stream<T>.mapToInt(ToIntFunction<T>)`: object `T` → int.

Các biến thể trên `LongStream`, `DoubleStream` có nguyên tắc tương tự, nhưng tên interface chuyển đổi primitive thay đổi theo loại đầu vào/đầu ra.

## 13. Kiểu generic, thứ tự và song song

Khi nguồn có encounter order, các phép chuyển đổi `boxed`/`mapToObj`/`mapToInt` không mặc nhiên xóa encounter order. Ví dụ:

```java
List<String> labels = IntStream.rangeClosed(1, 3)
        .parallel()
        .mapToObj(n -> "N" + n)
        .toList();

System.out.println(labels); // [N1, N2, N3]
```

`IntStream.rangeClosed` có thứ tự, và `toList()` giữ encounter order, kể cả khi pipeline có thể xử lý phần tử song song. Tuy nhiên không suy ra lambda `n -> "N" + n` thực thi lần lượt trên đúng một thread. Tránh cập nhật một `ArrayList` bên ngoài từ `parallel().forEach(...)`: collection mutable không được bảo vệ có thể bị data race.

Với primitive stream, terminal `sum`/`average`/`count` thường thuận tiện hơn tự dùng `forEach` để tích lũy. Đối với những phép số cần tính kết hợp nghiêm ngặt (đặc biệt dấu phẩy động), đánh giá tính ổn định và hợp đồng kết quả trước khi song song hóa.

## 14. Những lỗi phổ biến

| Sai lầm | Nguyên nhân | Cách đúng |
| --- | --- | --- |
| `Stream<int>` | Generics không chấp nhận primitive | `IntStream` hoặc `Stream<Integer>` |
| Nghĩ `boxed()` trả `List<Integer>` | Nó trả `Stream<Integer>` | Thêm terminal `toList()`/`collect` |
| `IntStream.map(n -> "N"+n)` | `IntStream.map` yêu cầu int → int | `mapToObj(n -> "N"+n)` |
| `IntStream.boxed().sum()` | `Stream<Integer>` không có `sum()` | `IntStream.sum()` hoặc `mapToInt(...).sum()` |
| `Stream<String>.mapToInt(...)` với mapper trả `String` | Mapper phải trả int | `Integer::parseInt` hoặc trích xuất số |
| Nghĩ `mapToObj` luôn đóng hộp | Nó cho phép đổi sang object bất kỳ | Dùng `boxed()` nếu chỉ cần wrapper |
| Bỏ qua `null` trước `Integer::intValue` | Unboxing gây NPE | Validate hoặc `filter(Objects::nonNull)` có chủ đích |
| Dùng `(int) longValue` mà không kiểm tra | Có thể mất dữ liệu khi narrowing | `Math.toIntExact` hoặc validation |
| Nghĩ `long → double` luôn chính xác | Số nguyên lớn có thể vượt độ chính xác 53-bit | Giữ long/BigInteger nếu cần exact |
| Dùng `IntStream.sum()` cho tổng ngoài miền int | Overflow có thể sai âm thầm | `asLongStream().sum()` nếu long đủ |
| Gọi `average().getAsDouble()` khi stream rỗng | Không có kết quả trung bình | `orElse`/`orElseThrow` và chính sách rõ |
| Dùng lại stream sau `boxed().toList()` | Stream dùng một lần | Tạo lại nguồn |
| Chuyển sang `parallel` rồi tự thêm vào List ngoài | Shared mutable state không an toàn | Thu thập bằng terminal collector/toList |

## 15. Bài tập áp dụng

1. Viết `IntStream.rangeClosed(1,5).boxed().toList()` rồi ghi rõ kiểu của từng đoạn: `IntStream` → `Stream<Integer>` → `List<Integer>`.
2. Từ số 1..5, dùng `mapToObj(n -> "ID-" + n)` để nhận danh sách chuỗi. Vì sao không cần `boxed()`?
3. Dùng `Stream.of("10","20","30").mapToInt(Integer::parseInt).sum()`. **Kết quả:** 60. Xác định kiểu nhận của mapper và kiểu kết quả.
4. Dùng `IntStream.of(1_500_000_000,1_500_000_000).asLongStream().sum()`. Vì sao phép cộng giữ 3.000.000.000 mà `IntStream.sum()` không bảo đảm?
5. Nhóm các số 1..8 thành `even` và `odd` bằng `boxed().collect(groupingBy(...))`. Nêu lý do phải chuyển sang object stream với collector tổng quát.
6. Từ `Stream<Score>`, dùng `mapToInt(Score::points)` tính tổng điểm. So sánh với `map(Score::points)` có kiểu `Stream<Integer>`.
7. Viết `DoubleStream.of(1.5, 2.5).mapToObj(value -> "v=" + value).toList()`. Kết quả là `[v=1.5, v=2.5]`.
8. Dùng `LongStream.of(10L, 3_000_000_000L).mapToInt(Math::toIntExact)` và terminal duyệt. Giải thích exception với giá trị thứ hai.
9. Từ `List<Integer>` có phần tử null, kiểm tra đường chạy `mapToInt(Integer::intValue)` và chọn chính sách xử lý null phù hợp.
10. Tính average trên `IntStream.empty()`. Vì sao phải xử lý `OptionalDouble.empty()` thay vì mặc định có số 0?
11. So sánh `IntStream.map(n -> n * 2)` với `IntStream.mapToObj(n -> n * 2)`. Dù nội dung số có thể giống, kiểu kết quả và việc boxing khác nhau như thế nào?
12. Kiểm thử long `2^53+1` qua `LongStream.asDoubleStream()` rồi chuyển ngược về long. Vì sao không thể dùng double để lưu chính xác mọi long?
13. Dùng `IntStream.rangeClosed(1,3).parallel().mapToObj(...).toList()` và giải thích vì sao thứ tự phần tử kết quả vẫn xác định nhưng không thể khẳng định thứ tự thực thi mapper.
14. Thử thiết kế một bài toán dùng số tiền chính xác: quyết định nên giữ số nguyên theo đơn vị nhỏ hay dùng `BigDecimal`, và chỉ boxing khi đi vào API collection/generic.

## 16. Checklist trước khi chuyển kiểu Stream

- Kiểu đầu vào hiện tại là `Stream<T>` hay `IntStream`/`LongStream`/`DoubleStream`?
- Đầu ra cần **wrapper cùng giá trị** (`boxed`) hay **object mới** (`mapToObj`)?
- Có thể giữ primitive đến terminal `sum`/`average` để tránh boxing không cần thiết không?
- Cần dùng generic `Collector` hoặc một API nhận `Stream<T>` không?
- Khi object → primitive, dữ liệu có thể `null` không? Mapper trả đúng kiểu int/long/double không?
- Khi `long → int` hoặc `long → double`, có nguy cơ mất phạm vi hoặc độ chính xác không?
- Với tổng lớn, kiểu kết quả `int`/`long` có đủ không, có cần `BigInteger`/`BigDecimal` không?
- Terminal operation có thể trả `OptionalInt`/`OptionalLong`/`OptionalDouble` rỗng không?
- Có đang dùng lại một stream đã tiêu thụ hoặc đưa side effect vào parallel mapper không?
- Đã kiểm thử ít nhất trường hợp **rỗng, null ở nguồn object, giá trị biên, chuyển đổi narrowing, overflow và kết quả theo thứ tự** chưa?

**Ghi nhớ:** `boxed()` chuyển primitive stream thành `Stream` wrapper; `mapToObj()` chuyển primitive thành object bất kỳ; `mapToInt`/`mapToLong`/`mapToDouble` chuyển object stream thành primitive stream; `asLongStream`/`asDoubleStream` là các phép mở rộng kiểu thuận tiện. Hãy chọn dựa trên **kiểu dữ liệu mong muốn**, độ chính xác và hợp đồng nghiệp vụ, không chỉ vì một chuỗi method call nhìn ngắn hơn.
