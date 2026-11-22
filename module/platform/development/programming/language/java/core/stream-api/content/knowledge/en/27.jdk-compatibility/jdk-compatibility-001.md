# Bản đồ API nền tảng của Stream trong Java 8

> **Chương:** Khả năng tương thích JDK  
> **Module:** JAVA_STREAM_API  
> **Phạm vi:** Những thành phần của Java Stream API **đã có trong Java 8**: kiểu Stream, tạo nguồn, thao tác trung gian, thao tác kết thúc, primitive streams, Optional, Collector, Spliterator và các quy tắc an toàn khi chạy song song. Bài cũng đặt ranh giới rõ với các API được bổ sung **sau Java 8** để bạn có thể viết mã tương thích với dự án cũ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Tìm đúng package, lớp và interface cốt lõi của Stream API khi mục tiêu triển khai là **Java 8**.
2. Phân biệt `Stream<T>` với `IntStream`, `LongStream` và `DoubleStream`.
3. Chọn nguồn tạo Stream từ `Collection`, mảng, khoảng số, tệp, bộ sinh và `Spliterator`.
4. Phân loại các phương thức **intermediate** và **terminal**, nhận diện thao tác lazy và short-circuit.
5. Dùng `filter`, `map`, `flatMap`, `distinct`, `sorted`, `skip` và `limit` đúng ngữ nghĩa.
6. Dùng `reduce` và `collect` theo hợp đồng, kể cả `Collectors.groupingBy` và collector nhiều tầng.
7. Làm việc với `Optional`/`OptionalInt`/`OptionalLong`/`OptionalDouble` khi kết quả có thể rỗng.
8. Đánh giá encounter order, trạng thái chia sẻ, tài nguyên và tính đúng khi gọi `parallelStream()`.
9. Nhận ra phương thức **không tồn tại trong Java 8** như `Stream.toList()`, `takeWhile()`, `mapMulti()` và biết cách thay thế phù hợp.
10. Viết, đọc và kiểm tra một chương trình Java 8 hoàn chỉnh có pipeline xử lý dữ liệu thực tế.

**Nguyên tắc phiên bản:** Ví dụ có nhãn *Java 8* chỉ sử dụng API và cú pháp đã có trong Java 8. Những API mới hơn được trình bày riêng trong bảng đối chiếu, không được đưa trực tiếp vào mã cần biên dịch trên JDK 8. Các ví dụ là kiến thức nền cho pipeline lazy, grouping, collector tùy chỉnh, Spliterator, xử lý song song và những tính năng Stream xuất hiện ở các JDK tiếp theo.

---

## 1. Bản đồ tổng quan: Java 8 đưa Stream API vào đâu?

Stream API được đưa vào Java cùng **Java 8**. Các kiểu trung tâm nằm trong `java.util.stream`; một số kiểu hỗ trợ nằm ở `java.util`, `java.util.function` và những package cung cấp nguồn dữ liệu.

~~~text
Java 8 Stream API
│
├── java.util.stream
│   ├── BaseStream<T, S>
│   ├── Stream<T>
│   ├── IntStream / LongStream / DoubleStream
│   ├── Collectors
│   ├── Collector<T, A, R>
│   └── StreamSupport
│
├── java.util
│   ├── Optional<T>
│   ├── OptionalInt / OptionalLong / OptionalDouble
│   ├── Spliterator<T> / Spliterators
│   ├── Collection.stream() / parallelStream()
│   ├── Arrays.stream(...)
│   ├── Comparator
│   └── IntSummaryStatistics / LongSummaryStatistics /
│       DoubleSummaryStatistics
│
├── java.util.function
│   ├── Predicate<T> / Function<T,R>
│   ├── Consumer<T> / Supplier<T>
│   ├── UnaryOperator<T> / BinaryOperator<T>
│   ├── BiFunction<T,U,R> / BiConsumer<T,U>
│   └── IntPredicate / IntFunction / IntUnaryOperator / ...
│
└── Nguồn dữ liệu
    ├── java.nio.file.Files.lines(Path, Charset)
    ├── java.io.BufferedReader.lines()
    ├── java.util.regex.Pattern.splitAsStream(...)
    └── java.util.Random.ints() / longs() / doubles()
~~~

**Bản đồ này mô tả vai trò**, không nói mọi kiểu là một phần của riêng module Stream. Ví dụ `java.util.function` chứa các *functional interfaces* được dùng ở nhiều API Java 8, không chỉ Stream.

### 1.1. Stream không phải Collection

| Tiêu chí | `Collection<E>` | `Stream<T>` |
|---|---|---|
| Bản chất | Chứa/quản lý phần tử | Mô tả chuỗi phép xử lý trên nguồn |
| Duyệt lại | Có thể duyệt lại khi collection cho phép | Một Stream không được dùng lại sau terminal operation |
| Lazy operations | Không phải đặc điểm chính của Collection | Phần lớn intermediate operations là lazy |
| Thêm/xóa phần tử | Phụ thuộc loại collection | Stream không có `add`/`remove` để sửa nguồn |
| Song song | Cần thuật toán riêng hoặc API tương ứng | Có `parallel()` và nguồn `parallelStream()` |
| Kết quả | Thường chính collection hoặc iterator | Terminal operation tạo số, Optional, List, Map... |

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

List<Integer> values = Arrays.asList(2, 4, 6);

Stream<Integer> stream = values.stream();
long count = stream.count(); // 3

// Không được tiếp tục dùng chính stream sau terminal operation:
// stream.findFirst(); // thường gây IllegalStateException

// Có thể tạo Stream MỚI từ cùng collection:
int sum = values.stream().mapToInt(Integer::intValue).sum();
System.out.println(sum); // 12
~~~

Stream có thể tham chiếu một nguồn **không lưu sẵn toàn bộ dữ liệu**, ví dụ một bộ sinh vô hạn, nên đừng mặc định mọi Stream đều có `size()` hoặc có thể duyệt lại.

---

## 2. Các kiểu trung tâm và ý nghĩa của tham số kiểu

### 2.1. Stream<T> và BaseStream

`Stream<T>` đại diện các phần tử kiểu tham chiếu `T`. Nó kế thừa `BaseStream<T, Stream<T>>`, là nơi định nghĩa các thao tác chung như `iterator`, `spliterator`, `sequential`, `parallel`, `unordered`, `onClose` và `close`.

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Stream<String> names = Arrays.asList("An", "Binh").stream();

Stream<String> normalized = names
        .map(String::trim)
        .filter(s -> !s.isEmpty());

System.out.println(normalized.count()); // 2
~~~

Trong ví dụ này, `map`/`filter` trả về Stream khác trong cùng pipeline. Một pipeline được xây rồi tiêu thụ bởi terminal operation `count`.

### 2.2. Ba primitive streams

| Kiểu | Phần tử | Ví dụ terminal operation |
|---|---|---|
| `IntStream` | `int` | `sum()`, `average()`, `summaryStatistics()` |
| `LongStream` | `long` | `sum()`, `min()`, `max()` |
| `DoubleStream` | `double` | `sum()`, `average()`, `summaryStatistics()` |

~~~java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

int sum = IntStream.range(1, 5).sum();         // 10
long max = LongStream.of(3L, 8L, 5L)
        .max().getAsLong();                    // 8
double average = DoubleStream.of(2.0, 4.0, 9.0)
        .average().getAsDouble();              // 5.0

System.out.println(sum);
System.out.println(max);
System.out.println(average);
~~~

`IntStream` không phải `Stream<Integer>`. Primitive Stream tránh việc phải tạo đối tượng boxing cho mỗi phần tử trong nhiều phép toán số.

### 2.3. Kiểu Optional đi cùng terminal operations

| Kết quả có thể thiếu | Kiểu bao |
|---|---|
| Object `T` | `Optional<T>` |
| `int` | `OptionalInt` |
| `long` | `OptionalLong` |
| `double` | `OptionalDouble` |

Ví dụ `findFirst()` trên nguồn rỗng trả `Optional.empty()`; `IntStream.average()` trên nguồn rỗng trả `OptionalDouble.empty()`. Không gọi `get()`/`getAsInt()` khi chưa có dữ liệu mà không có chính sách lỗi rõ ràng.

---

## 3. Tạo nguồn Stream từ Collection và mảng

### 3.1. Collection.stream() và parallelStream()

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

List<String> names = Arrays.asList("An", "Binh", "Chi");

Stream<String> sequential = names.stream();
Stream<String> parallel = names.parallelStream();

System.out.println(sequential.count()); // 3
System.out.println(parallel.count());   // 3
~~~

Cả hai phương thức có từ Java 8. `parallelStream` chỉ yêu cầu pipeline có khả năng xử lý song song; không có bảo đảm nhanh hơn và không làm những lambda có side effect trở thành thread-safe.

**Map không có phương thức `map.stream()` trong Java 8.** Muốn xử lý từng entry, hãy bắt đầu từ view của Map:

~~~java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> stock = new HashMap<String, Integer>();
stock.put("PEN", 5);
stock.put("BOOK", 3);

int total = stock.entrySet().stream()
        .mapToInt(entry -> entry.getValue())
        .sum();

System.out.println(total); // 8
~~~

### 3.2. Arrays.stream(...)

~~~java
import java.util.Arrays;

String[] words = {"java", "stream", "api"};
int[] numbers = {3, 5, 7};

long wordsCount = Arrays.stream(words).count();
int numericTotal = Arrays.stream(numbers).sum();

System.out.println(wordsCount);  // 3
System.out.println(numericTotal); // 15
~~~

`Arrays.stream(int[])` trả `IntStream`, trong khi `Arrays.stream(String[])` trả `Stream<String>`. Các overload của mảng còn hỗ trợ chọn đoạn bằng chỉ số đầu/cuối.

~~~java
int[] data = {10, 20, 30, 40};
int middle = Arrays.stream(data, 1, 3).sum(); // 20 + 30
System.out.println(middle); // 50
~~~

Chỉ số cuối `toIndex` là **exclusive**, giống quy tắc thường dùng cho các khoảng trong Java.

### 3.3. Stream.of() và Stream.empty()

~~~java
import java.util.stream.Stream;

long count = Stream.of("A", "B", "C").count(); // 3
long emptyCount = Stream.<String>empty().count(); // 0

System.out.println(count);
System.out.println(emptyCount);
~~~

**Cảnh báo mảng nguyên thủy:**

~~~java
int[] values = {1, 2, 3};

// Stream.of(values) nhận 1 đối tượng kiểu int[]:
long oneArray = Stream.of(values).count(); // 1

// Arrays.stream(values) phát ra 3 số int:
long threeNumbers = java.util.Arrays.stream(values).count(); // 3

System.out.println(oneArray + " / " + threeNumbers); // 1 / 3
~~~

Khi muốn thao tác trên từng số nguyên, dùng `Arrays.stream(int[])` hoặc `IntStream.of(int...)`.

### 3.4. Stream.Builder và Stream.concat

~~~java
import java.util.stream.Stream;

Stream.Builder<String> builder = Stream.builder();
builder.add("A");
builder.add("B");

Stream<String> built = builder.build();

Stream<String> joined = Stream.concat(
        built,
        Stream.of("C")
);

System.out.println(joined.count()); // 3
~~~

`Stream.builder()` và `Stream.concat(...)` đều đã có từ Java 8. Builder chỉ nên dùng theo hợp đồng: thêm phần tử **trước** `build()`, không tự tái sử dụng builder sau đó. Hai Stream đầu vào của `concat` cũng không nên bị tiêu thụ bởi terminal operation trước khi tạo/tiêu thụ kết quả nối.

---

## 4. Tạo dãy số và nguồn sinh dữ liệu

### 4.1. IntStream.range và rangeClosed

~~~java
import java.util.stream.IntStream;

int leftClosedRightOpen = IntStream.range(1, 5).sum();
// 1 + 2 + 3 + 4 = 10

int bothClosed = IntStream.rangeClosed(1, 5).sum();
// 1 + 2 + 3 + 4 + 5 = 15

System.out.println(leftClosedRightOpen); // 10
System.out.println(bothClosed);           // 15
~~~

- `range(start, endExclusive)` không gồm `endExclusive`.
- `rangeClosed(start, endInclusive)` gồm giá trị cuối.

`LongStream` cũng có `range` và `rangeClosed` trong Java 8. `DoubleStream` không có factory `range` tương tự.

### 4.2. Stream.iterate(seed, next) — Java 8

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Integer> powers = Stream.iterate(
        1,
        n -> n * 2
).limit(5).collect(Collectors.toList());

System.out.println(powers); // [1, 2, 4, 8, 16]
~~~

Overload **hai tham số** `Stream.iterate(seed, UnaryOperator)` có trong Java 8 và có thể tạo **nguồn vô hạn**. Cần một thao tác dừng thích hợp như `limit` hoặc terminal operation short-circuit nếu muốn kết thúc.

**Không nhầm** với overload ba tham số `Stream.iterate(seed, hasNext, next)`: nó xuất hiện **từ Java 9**, không dùng để biên dịch mã Java 8.

### 4.3. Stream.generate(Supplier)

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> repeated = Stream.generate(() -> "OK")
        .limit(3)
        .collect(Collectors.toList());

System.out.println(repeated); // [OK, OK, OK]
~~~

`generate` lấy phần tử từ một `Supplier` và thường cho nguồn không giới hạn. Đừng dựa vào thứ tự gọi supplier hoặc bộ đếm chia sẻ làm logic nghiệp vụ khi xử lý song song.

### 4.4. Nguồn số ngẫu nhiên

~~~java
import java.util.Random;

Random random = new Random(123L);

long count = random.ints(20, 0, 100)
        .count();

System.out.println(count); // 20
~~~

`Random.ints/longs/doubles` đã được bổ sung trong Java 8. Ví dụ tạo 20 số nguyên từ 0 (inclusive) đến 100 (exclusive). Seed cố định giúp tái hiện dãy trong các ngữ cảnh phù hợp, nhưng việc điều khiển thứ tự sử dụng nguồn ngẫu nhiên trong xử lý song song cần được xem xét riêng nếu yêu cầu khả năng tái lập nghiêm ngặt.

---

## 5. Nguồn I/O: Files.lines và BufferedReader.lines

Stream có thể đọc dữ liệu dần từ tệp văn bản. Đây là điểm khác với việc tải toàn bộ tệp vào một `List` trước khi xử lý.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

Path path = Paths.get("orders.txt");

try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long nonEmpty = lines
            .filter(line -> !line.trim().isEmpty())
            .count();

    System.out.println(nonEmpty);
} catch (IOException ex) {
    System.err.println("Không mở được tệp: " + ex.getMessage());
}
~~~

Ví dụ dùng `Paths.get(...)` vì đây là cách tạo `Path` tương thích **Java 8**. `Path.of(...)` chỉ có từ Java 11.

**Quan trọng:**

- `Files.lines(...)` có thể giữ tài nguyên mở; dùng `try-with-resources` để đóng Stream.
- Ngoại lệ I/O xảy ra trong quá trình đọc/lặp có thể được chuyển thành `UncheckedIOException`, không chỉ `IOException` lúc mở tệp.
- Đóng Stream không có nghĩa mọi Stream bắt buộc giữ tài nguyên; phần lớn Stream lấy từ collection không cần đóng.
- Không chạy nhiều terminal operations trên cùng Stream vừa đọc tệp.

`BufferedReader.lines()` cũng đã có trong Java 8:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

try (BufferedReader reader = Files.newBufferedReader(
        Paths.get("orders.txt"), StandardCharsets.UTF_8)) {
    long lineCount = reader.lines().count();
    System.out.println(lineCount);
} catch (IOException ex) {
    System.err.println(ex.getMessage());
}
~~~

Ở đây đóng `BufferedReader` bằng `try-with-resources` sẽ giải phóng nguồn đọc. Đừng tự cho rằng `Stream.count()` hoặc `collect` tự đóng nguồn tệp khi hoàn tất.

### 5.1. Pattern.splitAsStream()

~~~java
import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

List<String> tokens = Pattern.compile(",")
        .splitAsStream("A,B,C")
        .collect(Collectors.toList());

System.out.println(tokens); // [A, B, C]
~~~

`Pattern.splitAsStream` là một API Java 8 khác để tạo Stream từ dữ liệu chuỗi theo biểu thức chính quy.

---

## 6. Bản đồ intermediate operations — stateless

Intermediate operations thường trả một Stream mới cùng pipeline. Chúng **lazy**: chưa tiêu thụ nguồn ngay lúc được khai báo.

| Phương thức Java 8 | Vai trò | Kiểu kết quả điển hình |
|---|---|---|
| `filter(Predicate<T>)` | Giữ phần tử thỏa điều kiện | `Stream<T>` |
| `map(Function<T,R>)` | Biến đổi từng phần tử | `Stream<R>` |
| `mapToInt(ToIntFunction<T>)` | Chuyển object thành `int` | `IntStream` |
| `mapToLong(ToLongFunction<T>)` | Chuyển object thành `long` | `LongStream` |
| `mapToDouble(ToDoubleFunction<T>)` | Chuyển object thành `double` | `DoubleStream` |
| `flatMap(Function<T,Stream<R>>)` | Mỗi phần tử phát 0..n phần tử, làm phẳng | `Stream<R>` |
| `flatMapToInt` / `flatMapToLong` / `flatMapToDouble` | Làm phẳng về primitive stream | Primitive Stream |
| `peek(Consumer<T>)` | Chạy hành động quan sát khi phần tử được tiêu thụ | `Stream<T>` |

### 6.1. filter và map

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> names = Arrays.asList(
        " An ", "", " Binh ", "  ", " Chi "
);

List<String> cleaned = names.stream()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());

System.out.println(cleaned); // [An, Binh, Chi]
~~~

`String.trim()` tồn tại trong Java 8. `String.strip()` và `String.isBlank()` là API **Java 11**, nên không thay vào ví dụ cần chạy trên Java 8 mà không nâng runtime/API.

### 6.2. map khác flatMap

Với danh sách chứa nhiều danh sách:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<List<String>> groups = Arrays.asList(
        Arrays.asList("A", "B"),
        Arrays.asList("C")
);

// map tạo một Stream<Stream<String>> (các Stream con):
Stream<Stream<String>> nested = groups.stream()
        .map(List::stream);

// flatMap làm phẳng thành Stream<String>:
List<String> flat = groups.stream()
        .flatMap(List::stream)
        .collect(Collectors.toList());

System.out.println(flat); // [A, B, C]

// nested không được tiêu thụ trong đoạn minh họa này.
nested.close();
~~~

`flatMap` nhận một mapper từ mỗi phần tử sang Stream con, rồi nối các phần tử của những Stream con vào pipeline. Theo hợp đồng, các Stream con được đóng khi không còn cần thiết.

`mapMulti` chưa có trong Java 8; nếu gặp code dùng `mapMulti` trên tài liệu mới, phiên bản thay thế quen thuộc cho Java 8 là `flatMap`, tùy bài toán phát phần tử.

### 6.3. peek không dùng làm lõi nghiệp vụ

~~~java
import java.util.Arrays;

long count = Arrays.asList("A", "B", "C").stream()
        .peek(System.out::println)
        .filter(s -> !s.isEmpty())
        .count();
~~~

`peek` thích hợp cho một số tình huống quan sát/chẩn đoán, nhưng **không** nên đặt việc ghi dữ liệu bắt buộc hoặc thay đổi trạng thái nghiệp vụ vào nó. Stream có thể tối ưu hóa pipeline, các thao tác short-circuit có thể khiến chỉ một số phần tử được xử lý, và thứ tự tác dụng phụ trong parallel stream không phải hợp đồng kết quả.

---

## 7. Bản đồ intermediate operations — stateful và slicing

| Phương thức Java 8 | Ngữ nghĩa | Ghi chú |
|---|---|---|
| `distinct()` | Khử phần tử trùng theo `equals` | Có trạng thái, có thể tốn bộ nhớ |
| `sorted()` | Sắp theo natural order | Có trạng thái |
| `sorted(Comparator)` | Sắp theo comparator | Dùng với `Stream<T>` |
| `limit(long n)` | Lấy tối đa n phần tử đầu | Short-circuiting, stateful |
| `skip(long n)` | Bỏ n phần tử đầu | Stateful, không short-circuiting tổng quát |
| `unordered()` | Bỏ ràng buộc encounter order | Không chủ động xáo trộn |
| `sequential()` / `parallel()` | Chuyển chế độ thực thi | Không phải biến đổi từng phần tử |

### 7.1. distinct, sorted, skip, limit

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> source = Arrays.asList(4, 2, 4, 1, 3);

List<Integer> result = source.stream()
        .distinct()                 // [4, 2, 1, 3]
        .sorted()                   // [1, 2, 3, 4]
        .skip(1)                   // [2, 3, 4]
        .limit(2)                  // [2, 3]
        .collect(Collectors.toList());

System.out.println(result); // [2, 3]
~~~

`limit` và `skip` nhận số lượng **không âm**, nếu âm sẽ ném `IllegalArgumentException`. Trên nguồn có thứ tự, chúng làm việc với **tiền tố** theo encounter order.

### 7.2. Hoán đổi các thao tác có thể đổi bài toán

~~~java
import java.util.Arrays;
import java.util.Comparator;

List<Integer> nums = Arrays.asList(2, 9, 4, 7);

System.out.println(nums.stream()
        .sorted(Comparator.reverseOrder())
        .limit(2)
        .collect(java.util.stream.Collectors.toList()));
// [9, 7]

System.out.println(nums.stream()
        .limit(2)
        .sorted(Comparator.reverseOrder())
        .collect(java.util.stream.Collectors.toList()));
// [9, 2]
~~~

Hai pipeline **không tương đương**. Pipeline thứ nhất lấy top 2 toàn cục; pipeline thứ hai chỉ sắp hai phần tử đầu của nguồn.

### 7.3. Những thao tác chưa có trong Java 8

- `takeWhile(Predicate)`: từ **Java 9**.
- `dropWhile(Predicate)`: từ **Java 9**.
- `mapMulti(...)`: từ **Java 16**.
- `Stream.gather(...)` và các Gatherers chuẩn: xuất hiện ở JDK mới hơn, không có trong Java 8.

Nếu bài toán thật sự cần **lấy/bỏ tiền tố đến một ranh giới**, không thay đơn giản `takeWhile`/`dropWhile` bằng `filter`: `filter` xem tất cả phần tử và **không** giữ ngữ nghĩa ranh giới đầu tiên. Với code Java 8, có thể dùng một vòng lặp tuần tự rõ ràng hoặc custom `Spliterator` đúng hợp đồng khi cần phát Stream.

---

## 8. Bản đồ terminal operations

Terminal operation kích hoạt việc xử lý nguồn và hoàn tất pipeline.

| Nhóm | Phương thức Java 8 | Kết quả |
|---|---|---|
| Duyệt | `forEach`, `forEachOrdered` | `void` |
| Đếm | `count` | `long` |
| Tìm | `findFirst`, `findAny` | `Optional<T>` |
| Match | `anyMatch`, `allMatch`, `noneMatch` | `boolean` |
| Min/max | `min(Comparator)`, `max(Comparator)` | `Optional<T>` |
| Mảng | `toArray()`, `toArray(generator)` | Mảng |
| Giảm gộp | Các overload `reduce` | `Optional<T>` hoặc giá trị |
| Thu thập | `collect(Collector)` hoặc `collect(supplier,accumulator,combiner)` | `R` |
| Primitive | `sum`, `average`, `summaryStatistics` | Số hoặc kiểu thống kê |

**`Stream<T>` không có `sum()` chung.** Để cộng các trường số trong `Stream<Order>`, chuyển sang primitive stream qua `mapToInt`/`mapToLong` hoặc dùng `reduce`/`Collectors.summing...`.

### 8.1. findFirst, findAny và match

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

List<Integer> values = Arrays.asList(4, 7, 8, 10);

Optional<Integer> firstEven = values.stream()
        .filter(n -> n % 2 == 0)
        .findFirst();

boolean hasNegative = values.stream().anyMatch(n -> n < 0);
boolean allPositive = values.stream().allMatch(n -> n > 0);
boolean noneZero = values.stream().noneMatch(n -> n == 0);

System.out.println(firstEven.orElse(-1)); // 4
System.out.println(hasNegative);          // false
System.out.println(allPositive);          // true
System.out.println(noneZero);             // true
~~~

Với Stream có encounter order, `findFirst` chọn phần tử đầu theo thứ tự ấy. `findAny` có thể chọn **bất kỳ phần tử** hợp lệ và thích hợp khi không quan tâm vị trí, nhất là trong xử lý song song.

### 8.2. Short-circuiting terminals

`findFirst`, `findAny`, `anyMatch`, `allMatch` và `noneMatch` có thể dừng khi đã xác định kết quả. Điều đó không có nghĩa lambda upstream được gọi đúng một số lần cố định, đặc biệt khi pipeline chạy song song.

Với nguồn rỗng:

~~~java
import java.util.stream.Stream;

boolean any = Stream.<Integer>empty().anyMatch(n -> n > 0);
boolean all = Stream.<Integer>empty().allMatch(n -> n > 0);
boolean none = Stream.<Integer>empty().noneMatch(n -> n > 0);

System.out.println(any);  // false
System.out.println(all);  // true
System.out.println(none); // true
~~~

Đây là ngữ nghĩa logic của các phép match trên tập rỗng; không phải lỗi.

### 8.3. toArray

~~~java
import java.util.Arrays;

String[] result = Arrays.asList("A", "B", "C")
        .stream()
        .filter(s -> !"B".equals(s))
        .toArray(String[]::new);

System.out.println(Arrays.toString(result)); // [A, C]
~~~

`toArray(String[]::new)` có từ Java 8. Nếu gọi `toArray()` không tham số trên `Stream<T>`, kiểu kết quả là `Object[]`.

---

## 9. Primitive streams: chuyển kiểu và phép tổng hợp

### 9.1. mapToInt, mapToLong, mapToDouble

~~~java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("java", "api", "stream");

int totalCharacters = words.stream()
        .mapToInt(String::length)
        .sum();

System.out.println(totalCharacters); // 13
~~~

`mapToInt` không tạo ra `Stream<Integer>`; nó trả `IntStream`, hỗ trợ `sum()` trực tiếp.

~~~java
import java.util.Arrays;
import java.util.List;

List<Integer> amounts = Arrays.asList(
        1500000000, 1500000000
);

long total = amounts.stream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(total); // 3000000000
~~~

Dùng `mapToLong` **trước khi cộng** để tránh overflow `int`. Tuy nhiên tổng kiểu `long` vẫn có thể overflow nếu miền dữ liệu đủ lớn; khi đó cân nhắc `BigInteger`.

### 9.2. boxed và mapToObj

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> ids = IntStream.rangeClosed(1, 3)
        .boxed()
        .collect(Collectors.toList());

List<String> labels = IntStream.range(1, 4)
        .mapToObj(n -> "ID-" + n)
        .collect(Collectors.toList());

System.out.println(ids);    // [1, 2, 3]
System.out.println(labels); // [ID-1, ID-2, ID-3]
~~~

`boxed()` đổi primitive stream sang wrapper object Stream. `mapToObj` chuyển primitive thành đối tượng theo hàm mapper.

### 9.3. average và summaryStatistics

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;

int[] scores = {10, 20, 30};

OptionalDouble average = Arrays.stream(scores).average();
IntSummaryStatistics stats = Arrays.stream(scores)
        .summaryStatistics();

System.out.println(average.orElse(0.0)); // 20.0
System.out.println(stats.getCount());    // 3
System.out.println(stats.getSum());      // 60
System.out.println(stats.getMin());      // 10
System.out.println(stats.getMax());      // 30
~~~

Với nguồn rỗng, `average()` trả `OptionalDouble.empty()`. Các trường min/max của `IntSummaryStatistics` khi không có phần tử là **giá trị sentinel**, không nên diễn giải là điểm nhỏ nhất/lớn nhất thực tế; luôn xét `getCount()` trước.

### 9.4. Khi cần precision

`DoubleStream.sum()`/`average()` thực hiện số học dấu phẩy động; việc gộp song song có thể thay đổi thứ tự tính toán và sai số. Với tiền tệ cần chính xác, thường dùng số cent nguyên hoặc `BigDecimal` thay vì mặc định dùng `double`.

---

## 10. Optional trong Java 8: nhận và xử lý kết quả vắng mặt

`Optional<T>` có từ Java 8 và xuất hiện ở nhiều terminal operations.

~~~java
import java.util.Arrays;
import java.util.Optional;

Optional<String> firstLong = Arrays.asList(
        "An", "Binh", "Chi"
).stream()
 .filter(name -> name.length() > 10)
 .findFirst();

String display = firstLong.orElse("Không tìm thấy");

System.out.println(display); // Không tìm thấy
~~~

Những thao tác `Optional` có sẵn trong Java 8:

| API | Vai trò |
|---|---|
| `Optional.of(value)` | Bọc giá trị khác null |
| `Optional.ofNullable(value)` | Có giá trị nếu không null |
| `Optional.empty()` | Không có giá trị |
| `isPresent()` | Có phần tử không? |
| `get()` | Lấy giá trị; ném nếu rỗng |
| `ifPresent(Consumer)` | Thực thi khi có giá trị |
| `orElse(default)` | Giá trị mặc định |
| `orElseGet(Supplier)` | Tạo giá trị mặc định khi cần |
| `orElseThrow(Supplier)` | Ném lỗi được cung cấp khi rỗng |
| `filter(Predicate)` | Giữ Optional nếu predicate thỏa |
| `map(Function)` / `flatMap(Function)` | Biến đổi Optional |

Ví dụ API Java 8:

~~~java
import java.util.Optional;

Optional<Integer> maybeScore = Optional.of(90);

int score = maybeScore
        .filter(n -> n >= 0)
        .orElseThrow(() ->
                new IllegalStateException("Điểm không hợp lệ")
        );

System.out.println(score); // 90
~~~

**Chú ý phiên bản:**

- `optional.isEmpty()` không có trong Java 8 (từ Java 11).
- `optional.stream()` không có trong Java 8 (từ Java 9).
- `optional.ifPresentOrElse(...)` không có trong Java 8 (từ Java 9).
- `optional.orElseThrow()` **không tham số** không có trong Java 8 (từ Java 10); dùng overload truyền Supplier như trên.
- `OptionalInt` có `getAsInt`, `orElse` và các API chuyên biệt; không nhầm với `Optional<Integer>`.

### 10.1. Làm phẳng Optional bằng Java 8

Một pipeline mới thường dùng `Optional.stream()` để bỏ Optional rỗng. Trong Java 8, có thể làm tương đương bằng `flatMap`:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Optional<String>> options = Arrays.asList(
        Optional.of("A"),
        Optional.<String>empty(),
        Optional.of("C")
);

List<String> present = options.stream()
        .flatMap(o -> o.isPresent()
                ? Stream.of(o.get())
                : Stream.<String>empty())
        .collect(Collectors.toList());

System.out.println(present); // [A, C]
~~~

Đây là **cách tương thích Java 8**. Không cần cố dùng method reference `Optional::stream` vì phương thức đó chưa tồn tại ở phiên bản này.

---

## 11. reduce trong Java 8: ba overload và hợp đồng đại số

### 11.1. Không có identity

~~~java
import java.util.Arrays;
import java.util.Optional;

Optional<Integer> max = Arrays.asList(2, 9, 5)
        .stream()
        .reduce(Integer::max);

System.out.println(max.orElse(-1)); // 9
~~~

`reduce(BinaryOperator<T>)` trả `Optional<T>` để biểu diễn nguồn rỗng mà không tự bịa ra một giá trị đơn vị cho bài toán.

### 11.2. Có identity

~~~java
import java.util.Arrays;

int total = Arrays.asList(2, 9, 5)
        .stream()
        .reduce(0, Integer::sum);

System.out.println(total); // 16
~~~

Điều kiện quan trọng:

- Identity `0` trung hòa phép cộng.
- Operator có tính **kết hợp**: `(a+b)+c = a+(b+c)` theo quy tắc số học đang xét.
- Lambda phải **stateless** và **non-interfering**.

Identity sai như `reduce(10, Integer::sum)` có thể khiến kết quả song song cộng số `10` nhiều lần, vì từng phần có thể bắt đầu từ identity.

### 11.3. Dạng ba tham số: U khác T

~~~java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("java", "api");

long lengthSum = words.parallelStream()
        .reduce(
                0L,
                (sum, word) -> sum + word.length(),
                Long::sum
        );

System.out.println(lengthSum); // 7
~~~

Ba thành phần:

1. `identity` kiểu `U` (ở đây `Long`).
2. `accumulator(U,T) -> U`.
3. `combiner(U,U) -> U`.

Đối với overload này, combiner còn phải tương thích với accumulator. Một biểu thức kiểm tra quan trọng:

~~~text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
~~~

Nếu accumulator cộng độ dài nhưng combiner lấy `max`, phép reduce có thể đúng tuần tự rồi sai khi chia thành hai nhánh. Không nên dùng một `ArrayList` mutable chung làm identity và sửa nó trong reducer: dùng `collect` để tạo container mutable.

### 11.4. Phép cộng số thực và thay đổi thứ tự gộp

Phép cộng `double` không kết hợp tuyệt đối do làm tròn IEEE 754:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Do đó `reduce(0.0, Double::sum)` song song có thể khác một cách nhóm tuần tự ở các dữ liệu nhạy sai số. Khi cần kết quả tài chính chính xác, chọn kiểu và quy tắc tổng hợp phù hợp trước khi bật parallel.

---

## 12. collect: kết quả thành List, Set, Map hoặc cấu trúc riêng

Java 8 có hai nhóm API collect:

~~~java
<R, A> R collect(Collector<? super T, A, R> collector)

<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner
)
~~~

Trong thực tế, overload dùng `Collector` rất phổ biến vì `Collectors` cung cấp nhiều collector có sẵn.

### 12.1. Collectors.toList, toSet, toCollection

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> list = Arrays.asList("A", "B", "A")
        .stream()
        .collect(Collectors.toList());

Set<String> set = Arrays.asList("A", "B", "A")
        .stream()
        .collect(Collectors.toSet());

ArrayList<String> explicitArrayList = Arrays.asList("A", "B")
        .stream()
        .collect(Collectors.toCollection(ArrayList::new));

System.out.println(list); // [A, B, A]
System.out.println(set.size()); // 2
System.out.println(explicitArrayList); // [A, B]
~~~

**`Collectors.toList()` của Java 8 không cam kết kiểu cài đặt, tính có thể sửa, thread-safety hoặc serializability của List trả về.** Nếu cần một `ArrayList` cụ thể, dùng `toCollection(ArrayList::new)`.

`Collectors.toSet()` không bảo đảm encounter order hoặc kiểu Set. Nếu muốn một `LinkedHashSet` cụ thể:

~~~java
import java.util.LinkedHashSet;

LinkedHashSet<String> orderedUnique = Arrays
        .asList("B", "A", "B")
        .stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(orderedUnique); // [B, A]
~~~

### 12.2. Collectors.joining

~~~java
import java.util.Arrays;
import java.util.stream.Collectors;

String csv = Arrays.asList("A", "B", "C")
        .stream()
        .collect(Collectors.joining(","));

System.out.println(csv); // A,B,C
~~~

`joining()`, `joining(delimiter)` và `joining(delimiter, prefix, suffix)` đều là API Java 8. Đây thường là lựa chọn tốt hơn việc nối String liên tiếp bằng reducer khi số phần tử lớn.

### 12.3. collect ba tham số cho container mutable

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

List<String> result = Arrays.asList("A", "B", "C")
        .parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );

System.out.println(result); // [A, B, C]
~~~

`supplier` tạo container mới cho mỗi phần xử lý khi cần; `accumulator` nhận một phần tử; `combiner` hợp hai container. Không dùng một List chung được tạo ngoài pipeline thay cho supplier đúng hợp đồng.

---

## 13. Bản đồ Collectors có sẵn trong Java 8

| Nhóm | API Java 8 | Kết quả |
|---|---|---|
| Tập hợp | `toList`, `toSet`, `toCollection` | List/Set/Collection |
| Chuỗi | `joining` | String |
| Map | `toMap`, `toConcurrentMap` | Map/ConcurrentMap |
| Phân nhóm | `groupingBy`, `groupingByConcurrent` | Map<K, ...> |
| Chia hai nhóm | `partitioningBy` | Map<Boolean, ...> |
| Downstream | `mapping`, `collectingAndThen` | Kết quả được biến đổi/hoàn thiện |
| Đếm | `counting` | Long |
| Số | `summingInt/Long/Double` | Tổng |
| Trung bình | `averagingInt/Long/Double` | Double |
| Thống kê | `summarizingInt/Long/Double` | SummaryStatistics |
| Cực trị | `minBy`, `maxBy` | Optional<T> |
| Giảm gộp | Các overload `reducing` | Giá trị hoặc Optional |

### 13.1. groupingBy và counting

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> words = Arrays.asList(
        "java", "stream", "java", "api"
);

Map<String, Long> frequency = words.stream()
        .collect(Collectors.groupingBy(
                word -> word,
                Collectors.counting()
        ));

System.out.println(frequency.get("java")); // 2
System.out.println(frequency.get("api"));  // 1
~~~

`groupingBy(classifier)` mặc định thu thập danh sách giá trị của từng khóa. Downstream `counting()` thay List bằng số lượng.

### 13.2. groupingBy + mapping

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

class Sale {
    final String category;
    final long cents;

    Sale(String category, long cents) {
        this.category = category;
        this.cents = cents;
    }
}

List<Sale> sales = Arrays.asList(
        new Sale("BOOK", 100),
        new Sale("PEN", 40),
        new Sale("BOOK", 200)
);

Map<String, List<Long>> centsByCategory =
        sales.stream().collect(Collectors.groupingBy(
                sale -> sale.category,
                Collectors.mapping(
                        sale -> sale.cents,
                        Collectors.toList()
                )
        ));

System.out.println(centsByCategory.get("BOOK")); // [100, 200]
~~~

`mapping` đã có trong **Java 8**. Đừng nhầm nó với `Collectors.flatMapping` (Java 9) hoặc `Collectors.filtering` (Java 9), dù cả ba đều là downstream adapters.

### 13.3. toMap và merge function

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> values = Arrays.asList("a", "bb", "ccc");

Map<Integer, String> byLength = values.stream()
        .collect(Collectors.toMap(
                String::length,
                Function.identity()
        ));

System.out.println(byLength.get(2)); // bb
~~~

Nếu hai phần tử cho cùng khóa, overload `toMap(keyMapper, valueMapper)` sẽ ném `IllegalStateException`. Cần chọn chính sách rõ ràng khi khóa có thể trùng:

~~~java
List<String> duplicates = Arrays.asList(
        "an", "bo", "chi"
);

Map<Integer, String> firstPerLength = duplicates.stream()
        .collect(Collectors.toMap(
                String::length,
                Function.identity(),
                (first, later) -> first
        ));

System.out.println(firstPerLength.get(2)); // an
~~~

Trong Stream có thứ tự, chính sách chọn bản ghi đầu phù hợp với yêu cầu “đầu theo encounter order” khi dùng collector thông thường. Nếu nghiệp vụ muốn bản ghi **mới nhất**, đừng coi “đầu/cuối nguồn” là timestamp nếu chưa có ràng buộc dữ liệu; dùng merge theo version/time và tie-break phù hợp.

### 13.4. collectingAndThen đã có từ Java 8

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

List<String> readOnly = Arrays.asList("A", "B")
        .stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                list -> Collections.unmodifiableList(
                        new ArrayList<String>(list)
                )
        ));

// readOnly.add("C"); // UnsupportedOperationException.
~~~

`collectingAndThen` không phải tính năng Java 9+: nó có ngay từ Java 8. Ta dùng `Collections.unmodifiableList(new ArrayList<>(list))` để tạo một bản sao cấu trúc chỉ đọc trong Java 8. `List.copyOf` là API **Java 10**, không dùng được khi biên dịch Java 8.

### 13.5. partitioningBy

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Integer>> partitioned =
        Arrays.asList(1, 2, 3, 4)
                .stream()
                .collect(Collectors.partitioningBy(
                        n -> n % 2 == 0
                ));

System.out.println(partitioned.get(true));  // [2, 4]
System.out.println(partitioned.get(false)); // [1, 3]
~~~

`partitioningBy` tạo hai nhánh khóa Boolean. Đây là collector theo predicate, khác với grouping theo một khóa tùy ý.

---

## 14. Collector tùy chỉnh: cũng là Java 8

`Collector<T, A, R>` định nghĩa năm thành phần:

1. `supplier`: tạo trạng thái tích lũy `A`.
2. `accumulator`: đưa phần tử `T` vào `A`.
3. `combiner`: ghép hai trạng thái `A`.
4. `finisher`: chuyển trạng thái `A` sang kết quả `R`.
5. `characteristics`: mô tả những bảo đảm của collector.

Một collector đếm số phần tử bằng container mutable:

~~~java
import java.util.Arrays;
import java.util.stream.Collector;

Collector<String, long[], Long> countCollector =
        Collector.of(
                () -> new long[] {0L},
                (acc, value) -> acc[0]++,
                (left, right) -> {
                    left[0] += right[0];
                    return left;
                },
                acc -> acc[0]
        );

long count = Arrays.asList("A", "B", "C")
        .parallelStream()
        .collect(countCollector);

System.out.println(count); // 3
~~~

Trong ví dụ:

- Mỗi `supplier` tạo **mảng mới**.
- `accumulator` chỉ sửa trạng thái của container được giao.
- `combiner` gộp hai bộ đếm theo phép cộng.
- `finisher` trả số đếm `Long`.
- Không tự khai báo `CONCURRENT` vì `long[]` không thread-safe khi bị nhiều thread sửa cùng lúc.

Với nghiệp vụ chỉ đếm phần tử, dùng `count()` hoặc `Collectors.counting()` sẽ đơn giản hơn; mục tiêu ví dụ này là nhìn cấu trúc collector.

### 14.1. Ba đặc tính Collector

| Đặc tính | Ý nghĩa |
|---|---|
| `CONCURRENT` | Cho phép các thread tích lũy đồng thời trên cùng container trong điều kiện hợp đồng phù hợp |
| `UNORDERED` | Collector không yêu cầu giữ encounter order |
| `IDENTITY_FINISH` | Bước finisher có thể được coi là đồng nhất, có thể bị bỏ qua |

Các tên này là `Collector.Characteristics`, **khác** với cờ `Spliterator.ORDERED/SORTED/SIZED`. Không nhầm characteristics của collector với characteristics của nguồn.

Collector phải giữ identity/associativity của `combiner` và tính tương thích với `accumulator`. Một collector đúng khi chạy tuần tự **không nhất thiết đúng khi chạy parallel** nếu combiner bị viết sai.

---

## 15. Spliterator và StreamSupport: nền tảng nguồn tùy chỉnh từ Java 8

`Spliterator<T>` có các phương thức chính:

| Phương thức | Vai trò |
|---|---|
| `tryAdvance(Consumer)` | Phát nhiều nhất một phần tử |
| `forEachRemaining(Consumer)` | Phát các phần tử còn lại |
| `trySplit()` | Tách một phần dữ liệu còn lại |
| `estimateSize()` | Ước lượng số phần tử còn lại |
| `characteristics()` | Trả bitmask đặc tính |
| `getComparator()` | Comparator nếu nguồn có `SORTED` |

Một số cờ đã có trong Java 8:

- `ORDERED`: nguồn có encounter order.
- `DISTINCT`: không có phần tử trùng theo `equals`.
- `SORTED`: nguồn sắp xếp theo natural order hoặc comparator; kéo theo `ORDERED`.
- `NONNULL`: nguồn không phát `null`.
- `SIZED` và `SUBSIZED`: bảo đảm về kích thước.
- `IMMUTABLE` và `CONCURRENT`: đặc điểm cấu trúc/biến đổi nguồn.

### 15.1. Lấy Spliterator từ Collection

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;

List<Integer> values = Arrays.asList(3, 1, 2);
Spliterator<Integer> source = values.spliterator();

System.out.println(
        source.hasCharacteristics(Spliterator.ORDERED)
); // true, List có encounter order.

System.out.println(source.estimateSize()); // 3
~~~

Nếu tự viết `Spliterator` cho Stream song song và công bố `ORDERED`, `trySplit()` phải trả một phần **tiền tố** của các phần tử còn lại. Công bố sai `DISTINCT` hoặc `SORTED` có thể khiến những tối ưu của Stream tin vào dữ liệu không đúng.

### 15.2. Tạo Stream từ Spliterator

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

List<Integer> values = Arrays.asList(3, 1, 2);
Spliterator<Integer> source = values.spliterator();

int sum = StreamSupport.stream(source, false)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 6
~~~

Tham số `false` yêu cầu pipeline tuần tự; `true` yêu cầu song song. `StreamSupport.stream(...)` tồn tại trong Java 8, nên không cần tự xây một loại `Stream` mới để làm việc với nguồn tùy chỉnh.

### 15.3. Không tự dùng chung một Spliterator đã bị tiêu thụ

Spliterator thường chứa trạng thái vị trí duyệt. Nếu vừa tiêu thụ nguồn để lấy tổng, không dùng lại chính Spliterator ấy để đọc dữ liệu từ đầu. Hãy tạo một Spliterator mới hoặc tạo Stream mới từ collection có thể duyệt lại.

---

## 16. Functional interfaces có sẵn ở Java 8

Lambda và method reference là nền tảng giúp dùng Stream API gọn hơn.

| Interface | Phương thức trừu tượng | Ví dụ |
|---|---|---|
| `Predicate<T>` | `boolean test(T)` | `n -> n > 0` |
| `Function<T,R>` | `R apply(T)` | `String::length` |
| `Consumer<T>` | `void accept(T)` | `System.out::println` |
| `Supplier<T>` | `T get()` | `ArrayList::new` |
| `UnaryOperator<T>` | `T apply(T)` | `n -> n + 1` |
| `BinaryOperator<T>` | `T apply(T,T)` | `Integer::sum` |
| `BiFunction<T,U,R>` | `R apply(T,U)` | `(sum, item) -> ...` |
| `BiConsumer<T,U>` | `void accept(T,U)` | `List::add` trong collector |
| `ToIntFunction<T>` | `int applyAsInt(T)` | `String::length` |
| `IntPredicate` | `boolean test(int)` | `n -> n % 2 == 0` |
| `IntUnaryOperator` | `int applyAsInt(int)` | `n -> n * n` |

### 16.1. Lambda và method reference

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> names = Arrays.asList("a", "bb", "ccc");

List<Integer> lengths1 = names.stream()
        .map(name -> name.length())
        .collect(Collectors.toList());

List<Integer> lengths2 = names.stream()
        .map(String::length)
        .collect(Collectors.toList());

System.out.println(lengths1.equals(lengths2)); // true
~~~

`String::length` là method reference có thể thay lambda tương ứng.

### 16.2. Effectively final và side effects

~~~java
int minLength = 2; // Không bị gán lại sau khi khởi tạo.

long count = Arrays.asList("a", "bb", "ccc")
        .stream()
        .filter(s -> s.length() >= minLength)
        .count();

System.out.println(count); // 2
~~~

Biến local được lambda capture phải là `final` hoặc **effectively final**. Nhưng điều này **không có nghĩa đối tượng được capture là bất biến**:

~~~java
import java.util.ArrayList;
import java.util.List;

// Không nên dùng side effect chung trong parallel stream:
List<String> shared = new ArrayList<String>();

// Arrays.asList("A", "B", "C")
//         .parallelStream()
//         .forEach(shared::add);
~~~

`ArrayList` không thread-safe khi nhiều thread gọi `add` đồng thời. Dùng `collect(Collectors.toList())` hoặc một collector phù hợp thay vì sửa một List chung trong `forEach`.

---

## 17. Lazy evaluation và vòng đời một Stream

### 17.1. Intermediate operations chưa duyệt nguồn ngay

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Stream<Integer> pipeline = Arrays.asList(1, 2, 3)
        .stream()
        .filter(n -> {
            System.out.println("test " + n);
            return n > 1;
        });

System.out.println("Pipeline đã tạo");
// Chưa duyệt phần tử chỉ vì gọi filter().

long count = pipeline.count(); // terminal kích hoạt pipeline
System.out.println(count); // 2
~~~

Kết quả log của ví dụ thể hiện tính lazy khi terminal operation được gọi. Tuy nhiên đừng biến log/side effect thành kết quả bắt buộc: một số tối ưu được phép bỏ qua việc gọi lambda nếu không làm thay đổi **kết quả được đặc tả**.

### 17.2. Short-circuit

~~~java
import java.util.Arrays;
import java.util.Optional;

Optional<Integer> found = Arrays.asList(2, 4, 7, 8)
        .stream()
        .filter(n -> n % 2 != 0)
        .findFirst();

System.out.println(found.orElse(-1)); // 7
~~~

`findFirst` có thể dừng khi xác định phần tử phù hợp đầu tiên. Trên parallel stream có thứ tự, việc bảo đảm “đầu tiên” có thể gây thêm phối hợp so với `findAny`.

### 17.3. Stream không tái sử dụng sau terminal operation

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Stream<Integer> once = Arrays.asList(1, 2, 3).stream();

System.out.println(once.count()); // 3

// Không tiếp tục gọi once.reduce(...) hoặc once.findAny().
// Tạo Stream mới nếu muốn đánh giá lần nữa.
~~~

Một Stream có thể được tiêu thụ hoặc đóng chỉ một lần. Với nguồn có thể duyệt lại như List, gọi `list.stream()` thêm lần nữa; với nguồn tệp/I/O, cần quản lý việc mở lại nguồn.

---

## 18. Encounter order, parallel, unordered và tính đúng

### 18.1. Chế độ tuần tự và song song đều đã có từ Java 8

~~~java
import java.util.Arrays;
import java.util.List;

List<Integer> nums = Arrays.asList(1, 2, 3, 4);

long sequential = nums.stream()
        .mapToLong(Integer::longValue)
        .sum();

long parallel = nums.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(sequential); // 10
System.out.println(parallel);   // 10
~~~

Bật song song thay đổi **kế hoạch thực thi**, không tự tạo một thuật toán khác cho nghiệp vụ. Các lambda phải tuân thủ yêu cầu stateless/non-interfering, và phép gộp phải đúng identity/associativity.

### 18.2. forEach khác forEachOrdered

~~~java
import java.util.Arrays;

Arrays.asList("A", "B", "C", "D")
        .parallelStream()
        .forEach(System.out::println);
// Thứ tự in không được bảo đảm.

Arrays.asList("A", "B", "C", "D")
        .parallelStream()
        .forEachOrdered(System.out::println);
// Theo encounter order: A, B, C, D.
~~~

`forEachOrdered` bảo đảm thứ tự áp dụng hành động theo encounter order đối với Stream có thứ tự, nhưng có thể làm giảm lợi ích song song.

### 18.3. unordered() không phải shuffle()

~~~java
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

Set<Integer> unique = Arrays.asList(2, 1, 2, 3)
        .parallelStream()
        .unordered()
        .distinct()
        .collect(Collectors.toSet());

System.out.println(unique.size()); // 3
~~~

`unordered` bỏ ràng buộc encounter order, **không hứa đổi thứ tự dữ liệu**. Chỉ dùng khi thứ tự **không quan trọng** theo hợp đồng bài toán.

### 18.4. reduce và collector phải ghép đúng

Với reduce:

~~~java
// Identity đúng và phép gộp đúng:
int sum = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, Integer::sum);
~~~

Với collector mutable:

~~~java
// Mỗi supplier tạo container mới, combiner ghép kết quả:
List<Integer> result = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .collect(
                java.util.ArrayList::new,
                List::add,
                List::addAll
        );
~~~

Hai dạng giải quyết **hai kiểu bài toán khác nhau**. Đừng cố sử dụng `reduce` với một `ArrayList` mutable dùng chung để thay `collect`.

**Độ chính xác:** Song song không khôi phục kết quả đã overflow hay đã sai vì làm tròn. Cần kiểm tra miền số, thứ tự xếp hạng, sự ổn định khi trùng khóa và tính đúng của combiner trước khi đánh giá hiệu năng.

---

## 19. Bảng mốc tương thích: Java 8 có gì, chưa có gì?

Đây là bảng giúp đọc tài liệu hiện đại mà vẫn viết mã chạy trên Java 8.

| API / cú pháp | Có từ | Với Java 8, thay bằng gì? |
|---|---:|---|
| `Stream.of`, `Stream.empty` | 8 | Dùng trực tiếp |
| `Collection.stream/parallelStream` | 8 | Dùng trực tiếp |
| `filter/map/flatMap/distinct/sorted/skip/limit` | 8 | Dùng trực tiếp |
| `reduce`, `collect`, `Collectors.groupingBy` | 8 | Dùng trực tiếp |
| `Collectors.mapping/collectingAndThen` | 8 | Dùng trực tiếp |
| `StreamSupport.stream`, `Spliterator` | 8 | Dùng trực tiếp |
| `Stream.ofNullable` | 9 | Kiểm tra null rồi `Stream.empty()` hoặc `Stream.of(value)` |
| `takeWhile`, `dropWhile` | 9 | Vòng lặp hoặc custom `Spliterator` theo ranh giới |
| `Stream.iterate(seed, hasNext, next)` | 9 | `iterate(seed, next).limit(n)` nếu biết n, hoặc vòng lặp điều kiện |
| `Optional.stream` | 9 | `flatMap(o -> o.isPresent() ? Stream.of(o.get()) : Stream.empty())` |
| `Collectors.flatMapping` | 9 | `flatMap` trước grouping nếu giữ đúng nghĩa, hoặc collector tùy chỉnh |
| `Collectors.filtering` | 9 | `filter` trước grouping **nếu chấp nhận mất khóa nhóm rỗng**; nếu không, collector tùy chỉnh |
| `Collectors.toUnmodifiableList/Set/Map` | 10 | `collectingAndThen` + defensive copy + `Collections.unmodifiable...` |
| `List.copyOf`, `Map.copyOf`, `Set.copyOf` | 10 | `new ArrayList<>(...)`/`new HashMap<>(...)` + unmodifiable view |
| `Optional.orElseThrow()` không tham số | 10 | `orElseThrow(() -> new NoSuchElementException())` |
| `String.isBlank`, `String.strip`, `Path.of` | 11 | `trim`, kiểm tra chuỗi, `Paths.get` tùy ngữ nghĩa |
| `Optional.isEmpty` | 11 | `!optional.isPresent()` |
| `Collectors.teeing` | 12 | Collector tùy chỉnh hoặc hai phép tổng hợp riêng |
| `Stream.toList` | 16 | `collect(Collectors.toList())`; muốn read-only thì copy + unmodifiable view |
| `Stream.mapMulti` | 16 | `flatMap` hoặc collector/source tùy chỉnh |
| `record` (ngôn ngữ) | 16 | Class thông thường với fields/constructor/getters |
| `Stream.gather` / Stream Gatherers | 24 | Xây pipeline Java 8 bằng `map`/`flatMap`/collector hoặc custom `Spliterator` phù hợp |

**Đọc bảng theo ba chiều độc lập:**

1. **Phiên bản Java của cú pháp:** `record`, `var`, switch expression, text blocks không phải cú pháp Java 8.
2. **Phiên bản của API thư viện:** `Stream.toList()` không tồn tại trên Java 8 dù cú pháp gọi phương thức trông bình thường.
3. **Phiên bản runtime:** chạy bytecode mới trên Java 8 có thể thất bại vì class-file version, ngay cả khi code không dùng Stream mới.

### 19.1. Chú ý không phải mọi thay thế đều cùng ngữ nghĩa

- `String.trim` không xử lý hoàn toàn giống `String.strip` đối với Unicode whitespace.
- `filter(P)` **không** tương đương `takeWhile(P)`/`dropWhile(P)` trên nguồn có thứ tự bất kỳ.
- Lọc trước `groupingBy` có thể làm **mất nhóm không còn phần tử**, khác downstream `Collectors.filtering`.
- `Collectors.toList` không cam kết kết quả unmodifiable như `Stream.toList`.
- Một vòng lặp thay thế có thể đúng về kết quả nhưng không có tính lazy hoặc khả năng parallel như pipeline ban đầu.

Đừng thay API chỉ vì tên gần giống. Hãy xác định **hợp đồng kết quả** và hành vi với nguồn rỗng, null, thứ tự, dữ liệu trùng trước khi chuyển đổi phiên bản.

---

## 20. Bốn công thức chuyển mã hiện đại về Java 8

### 20.1. Stream.toList → Collectors.toList

Mã mới hơn:

~~~java
// Java 16+:
// List<String> names = source.stream()
//         .map(String::trim)
//         .toList();
~~~

Mã Java 8:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> names = source.stream()
        .map(String::trim)
        .collect(Collectors.toList());
~~~

Hai kết quả có thể cùng **nội dung**, nhưng khác hợp đồng khả năng sửa. Nếu API yêu cầu List chỉ đọc trong Java 8:

~~~java
import java.util.ArrayList;
import java.util.Collections;

List<String> readOnly = Collections.unmodifiableList(
        new ArrayList<String>(names)
);
~~~

Cách này tạo snapshot cấu trúc **nông**; nếu các phần tử mutable, bản thân object phần tử vẫn có thể bị thay đổi qua tham chiếu khác.

### 20.2. Stream.ofNullable → kiểm tra null

Mã mới hơn:

~~~java
// Java 9+:
// Stream<String> s = Stream.ofNullable(maybeName);
~~~

Java 8:

~~~java
import java.util.stream.Stream;

String maybeName = null;

Stream<String> s = maybeName == null
        ? Stream.<String>empty()
        : Stream.of(maybeName);

System.out.println(s.count()); // 0
~~~

Nếu cần giữ `null` như **một phần tử thật**, đây không còn là phép thay thế đúng; `Stream.ofNullable` vốn bỏ giá trị null.

### 20.3. takeWhile → vòng lặp dừng ở phần tử đầu không thỏa

Mã Java 9+:

~~~java
// List<Integer> prefix = values.stream()
//         .takeWhile(n -> n < 5)
//         .collect(Collectors.toList());
~~~

Java 8:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

List<Integer> values = Arrays.asList(1, 3, 8, 2, 4);
List<Integer> prefix = new ArrayList<Integer>();

for (Integer n : values) {
    if (n >= 5) {
        break;
    }
    prefix.add(n);
}

System.out.println(prefix); // [1, 3]
~~~

Vòng lặp này giữ **tiền tố dài nhất** theo thứ tự List. Thay bằng `filter(n -> n < 5)` sẽ trả `[1,3,2,4]`, **khác** kết quả mong đợi.

### 20.4. mapMulti → flatMap

Mã Java 16+:

~~~java
// Stream<Integer> expanded = values.stream()
//         .<Integer>mapMulti((n, output) -> {
//             if (n > 0) {
//                 output.accept(n);
//                 output.accept(n * 2);
//             }
//         });
~~~

Java 8:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Integer> values = Arrays.asList(-1, 2, 3);

List<Integer> expanded = values.stream()
        .flatMap(n -> n > 0
                ? Stream.of(n, n * 2)
                : Stream.<Integer>empty())
        .collect(Collectors.toList());

System.out.println(expanded); // [2, 4, 3, 6]
~~~

`flatMap` có thể tạo Stream con cho mỗi phần tử, còn `mapMulti` phát phần tử trực tiếp qua consumer. Kết quả được minh họa là tương đương, nhưng đặc điểm cấp phát và mô hình lập trình có thể khác; không kết luận hiệu năng chỉ từ tên API.

---

## 21. Biên dịch và chạy đúng mục tiêu Java 8

### 21.1. Chọn công cụ phù hợp

Khi đang dùng đúng **JDK 8**, lệnh biên dịch và chạy một chương trình độc lập:

~~~text
javac StreamApi8Demo.java
java StreamApi8Demo
~~~

Khi dùng **JDK 9 trở lên** nhưng cần tạo code tương thích Java 8, nên dùng lựa chọn:

~~~text
javac --release 8 StreamApi8Demo.java
~~~

`--release 8` kiểm soát cả phiên bản bytecode và tập API Java được phép truy cập theo bản Java đích; nó **không có trong javac của JDK 8**.

Chỉ dùng `-source 8 -target 8` với một JDK mới hơn có thể giới hạn cú pháp và bytecode nhưng **chưa đủ để ngăn tham chiếu tới API thư viện được bổ sung sau Java 8**. Đây là một nguyên nhân phổ biến của lỗi tương thích: mã biên dịch được trên JDK mới nhưng khi chạy bằng Java 8 lại không tìm thấy phương thức/lớp.

### 21.2. Nhận diện lỗi thường gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra |
|---|---|
| `cannot find symbol: method toList()` trên Stream | `Stream.toList` chỉ có từ Java 16 |
| `cannot find symbol: takeWhile(...)` | Java 8 chưa có; xuất hiện Java 9 |
| `cannot find symbol: mapMulti(...)` | Java 8 chưa có; xuất hiện Java 16 |
| `cannot find symbol: method of(...)` với `List.of` | Factory collection `List.of` từ Java 9 |
| `UnsupportedClassVersionError` | Bytecode được biên dịch cho runtime mới hơn |
| `NoSuchMethodError` ở runtime | Mã tham chiếu phương thức không có trong thư viện/runtime đang chạy hoặc có bất tương thích phiên bản |
| `Cannot infer type` ở collector/lambda | Cần xem generic inference, overload và kiểu lambda, không phải mọi lỗi đều do thiếu API |

Đọc kỹ stack trace và dòng lỗi. Đừng thấy lỗi `toList` rồi chỉ thay sang `Collectors.toList` mà không xem **hợp đồng bất biến** của nơi sử dụng kết quả.

---

## 22. Ví dụ Java 8 hoàn chỉnh: phân tích giao dịch

Chương trình sau **không dùng API sau Java 8**. Nó lọc giao dịch hợp lệ, tính tổng, nhóm doanh thu theo category, chọn giao dịch lớn nhất và gom danh sách mã giao dịch.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

public class StreamApi8Demo {

    static final class Transaction {
        private final String id;
        private final String category;
        private final long cents;
        private final boolean paid;

        Transaction(String id, String category,
                    long cents, boolean paid) {
            this.id = id;
            this.category = category;
            this.cents = cents;
            this.paid = paid;
        }

        String getId() { return id; }
        String getCategory() { return category; }
        long getCents() { return cents; }
        boolean isPaid() { return paid; }
    }

    public static void main(String[] args) {
        List<Transaction> txs = Arrays.asList(
                new Transaction("T1", "BOOK", 100L, true),
                new Transaction("T2", "PEN", 50L, true),
                new Transaction("T3", "BOOK", 300L, false),
                new Transaction("T4", "BOOK", 400L, true),
                new Transaction("T5", "PEN", 70L, true)
        );

        List<Transaction> paid = txs.stream()
                .filter(Transaction::isPaid)
                .collect(Collectors.toList());

        long paidCount = paid.stream().count();

        BigInteger total = paid.stream()
                .map(tx -> BigInteger.valueOf(tx.getCents()))
                .reduce(BigInteger.ZERO, BigInteger::add);

        Map<String, BigInteger> totalsByCategory = paid.stream()
                .collect(Collectors.groupingBy(
                        Transaction::getCategory,
                        Collectors.mapping(
                                tx -> BigInteger.valueOf(tx.getCents()),
                                Collectors.reducing(
                                        BigInteger.ZERO,
                                        BigInteger::add
                                )
                        )
                ));

        Optional<Transaction> biggest = paid.stream()
                .max(Comparator.comparingLong(
                        Transaction::getCents
                ));

        List<String> ids = paid.stream()
                .map(Transaction::getId)
                .sorted()
                .collect(Collectors.toList());

        System.out.println("paidCount=" + paidCount);
        System.out.println("total=" + total);
        System.out.println(
                "BOOK=" + totalsByCategory.get("BOOK")
        );
        System.out.println(
                "PEN=" + totalsByCategory.get("PEN")
        );
        System.out.println(
                "biggest=" + biggest.get().getId()
        );
        System.out.println("ids=" + ids);
    }
}
~~~

Kết quả mong đợi:

~~~text
paidCount=4
total=620
BOOK=500
PEN=120
biggest=T4
ids=[T1, T2, T4, T5]
~~~

**Giải thích các khía cạnh tương thích:**

- Class `Transaction` thông thường thay cho `record` (chưa có ở Java 8).
- `Arrays.asList` thay cho `List.of`.
- `Collectors.toList` thay `Stream.toList`.
- `Collectors.groupingBy`, `mapping` và `reducing` đều đã có trong Java 8.
- `BigInteger::add` giúp cộng số nguyên chính xác mà không làm tràn tổng `long` theo cách dùng `summingLong`.
- `Optional<Transaction>` từ `max` biểu diễn khả năng không có giao dịch; `biggest.get()` chỉ an toàn ở ví dụ vì danh sách `paid` được biết không rỗng. Trong hệ thống thực tế, dùng `orElseThrow(Supplier)` hoặc một chính sách rỗng rõ ràng.

### 22.1. Dòng chảy dữ liệu của chương trình

~~~text
List<Transaction>
        |
        +-- filter(paid)
               |
               +-- count()                   -> 4
               |
               +-- map(BigInteger cents)
               |      reduce(BigInteger::add) -> 620
               |
               +-- groupingBy(category,
               |       mapping(cents,
               |           reducing(add)))   -> {BOOK=500, PEN=120}
               |
               +-- max(byCents)              -> Optional(T4)
               |
               +-- map(id).sorted().collect  -> [T1, T2, T4, T5]
~~~

Mỗi nhánh trong sơ đồ bắt đầu từ một **Stream mới** trên danh sách `paid`, vì một Stream đã tiêu thụ không thể tái sử dụng. Trong trường hợp cần tối ưu lượt đọc nguồn, có thể thiết kế một collector tổng hợp nhiều trường, nhưng phải giữ đúng hợp đồng combiner.

---

## 23. Những sai lầm tương thích JDK thường gặp

| Sai lầm | Vì sao sai trên Java 8? | Cách xử lý |
|---|---|---|
| Dùng `stream.toList()` | Phương thức được bổ sung từ Java 16 | `collect(Collectors.toList())`, kiểm tra yêu cầu mutable/read-only |
| Dùng `List.of(...)` | Factory có từ Java 9 | `Arrays.asList(...)` hoặc list cụ thể |
| Dùng `Stream.ofNullable` | API từ Java 9 | `value == null ? Stream.empty() : Stream.of(value)` |
| Dùng `Optional.stream` | API từ Java 9 | `flatMap` bằng `isPresent/get` |
| Dùng `takeWhile/dropWhile` | API từ Java 9 | Vòng lặp dừng ở ranh giới hoặc nguồn tùy chỉnh |
| Dùng `mapMulti` | API từ Java 16 | `flatMap` nếu phù hợp |
| Dùng `Collectors.filtering/flatMapping` | Downstream adapters từ Java 9 | Collector tùy chỉnh hoặc đổi pipeline sau khi kiểm tra ngữ nghĩa |
| Dùng `Collectors.teeing` | API từ Java 12 | Collector giữ nhiều trường hoặc các tổng hợp riêng |
| Dùng `String.isBlank/strip` | API từ Java 11 | `trim/isEmpty` tùy yêu cầu Unicode |
| Dùng `Path.of` | API từ Java 11 | `Paths.get` |
| Dùng `record` hoặc `var` | Cú pháp chưa có ở Java 8 | Class/kiểu khai báo rõ ràng |
| Dùng `optional.isEmpty()` | API từ Java 11 | `!optional.isPresent()` |
| Coi `Collectors.toList` là luôn immutable | Không được bảo đảm bởi Collector | Copy và bọc unmodifiable nếu cần |
| Dùng `Stream.of(intArray)` để duyệt từng số | Cho một phần tử kiểu `int[]` | `Arrays.stream(intArray)` hoặc `IntStream.of(...)` |
| Coi `Stream<T>` có `sum()` | `sum()` nằm ở primitive streams | `mapToInt/mapToLong` hoặc `reduce` |
| Dùng lại Stream sau `count` | Stream đã tiêu thụ | Tạo Stream mới từ nguồn |
| Cho rằng parallel luôn nhanh hơn | Overhead chia/gộp và stateful operations | Kiểm tra đúng trước, benchmark sau |

---

## 24. Checklist chọn API cho dự án Java 8

Trước khi nộp một pipeline, hãy trả lời các câu hỏi:

1. **Runtime đích có thật là Java 8?** Không chỉ nhìn phiên bản JDK máy phát triển.
2. **Cú pháp dùng có hợp lệ ở Java 8?** Không dùng `record`, `var`, text blocks hoặc `switch` expression mới.
3. **Tất cả phương thức thư viện có từ Java 8?** Kiểm tra bảng mốc, nhất là `Stream.toList` và `takeWhile`.
4. **Nguồn đến từ đâu?** Collection, mảng, tệp, iterator, bộ sinh hay Spliterator tùy chỉnh?
5. **Stream kiểu object hay primitive?** Nếu đang tổng hợp số, có thể dùng `mapToInt/mapToLong`?
6. **Pipeline có terminal operation?** Các thao tác `filter/map` tự chúng chưa tiêu thụ nguồn.
7. **Có dùng lại Stream không?** Mỗi terminal operation cần Stream phù hợp, không tái dùng cái đã đóng/tiêu thụ.
8. **Có thể rỗng không?** Xử lý `Optional`/`OptionalDouble` theo chính sách rõ.
9. **Nguồn có null không?** Đừng dựa vào `Optional.get` hoặc mapper khi chưa kiểm tra.
10. **Có yêu cầu thứ tự không?** `findFirst`, `limit`, `forEachOrdered` cần xem encounter order.
11. **Có dùng song song không?** Xác minh stateless/non-interfering, combiner, container riêng.
12. **Kết quả cần kiểu cụ thể hay immutable?** `Collectors.toList` không cam kết kiểu/độ bất biến.
13. **Có tài nguyên I/O không?** Dùng `try-with-resources` với nguồn tệp.
14. **Kiểu số đủ rộng chưa?** Kiểm tra overflow và sai số dấu phẩy động.
15. **Có test biên và biên dịch đúng release đích chưa?** Java 8 trên JDK 8 hoặc `--release 8` từ JDK 9+.

### 24.1. Sơ đồ ra quyết định

~~~text
Cần xử lý tập dữ liệu bằng Java 8?
                |
                v
         Tạo nguồn Stream
                |
                +---- Collection.stream / Arrays.stream
                +---- Stream.of / IntStream.range
                +---- Files.lines / StreamSupport.stream
                |
                v
       Chọn kiểu phù hợp
           |              |
       Stream<T>       Primitive Stream
           |              |
           +------+-------+
                  |
                  v
         Intermediate operations
        filter / map / flatMap
     distinct / sorted / skip / limit
                  |
                  v
       Chọn terminal operation
       |         |          |
   Tìm/đếm    reduce      collect
       |         |          |
   Optional     Value     List/Map/...
       \         |          /
        \        |         /
         v       v        v
    Kiểm tra null/rỗng/order/overflow
                  |
                  v
     Biên dịch theo Java 8 API
                  |
                  v
       Kiểm thử và benchmark
~~~

---

## 25. Bài tập tự kiểm tra (có lời giải)

### Bài 1. Phân loại API Java 8

**Đề:** Những phương thức nào trong danh sách có sẵn ở Java 8: `filter`, `takeWhile`, `flatMap`, `mapMulti`, `Collectors.groupingBy`, `Stream.toList`, `Collectors.collectingAndThen`?

**Đáp án:** Có trong Java 8: `filter`, `flatMap`, `Collectors.groupingBy`, `Collectors.collectingAndThen`. Không có: `takeWhile` (9), `mapMulti` (16), `Stream.toList` (16).

### Bài 2. Sửa Stream.toList

**Đề:** Chuyển `names.stream().map(String::trim).toList()` thành code Java 8.

**Đáp án:**

~~~java
List<String> result = names.stream()
        .map(String::trim)
        .collect(Collectors.toList());
~~~

Nếu kết quả phải là List không thể chỉnh sửa cấu trúc, cần thêm defensive copy và `Collections.unmodifiableList` trong Java 8.

### Bài 3. Tính tổng bằng primitive Stream

**Đề:** `List<String> words = Arrays.asList("a", "bb", "ccc")`. Tính tổng độ dài bằng Java 8.

**Đáp án:**

~~~java
int total = words.stream()
        .mapToInt(String::length)
        .sum();

System.out.println(total); // 6
~~~

### Bài 4. Stream.of trên mảng nguyên thủy

**Đề:** Vì sao `Stream.of(new int[]{1,2,3}).count()` trả `1`?

**Đáp án:** Stream này có một phần tử kiểu `int[]`. Muốn ba số nguyên, dùng `Arrays.stream(new int[]{1,2,3})` hoặc `IntStream.of(1,2,3)`.

### Bài 5. range và rangeClosed

**Đề:** `IntStream.range(1,4).sum()` khác `IntStream.rangeClosed(1,4).sum()` thế nào?

**Đáp án:** `range(1,4)` duyệt 1,2,3 nên tổng 6; `rangeClosed(1,4)` duyệt 1,2,3,4 nên tổng 10.

### Bài 6. Optional trong Java 8

**Đề:** `Optional<String> result` có thể rỗng. Viết cách trả `"N/A"` nếu thiếu và cách báo lỗi nếu thiếu.

**Đáp án:**

~~~java
String shown = result.orElse("N/A");

String required = result.orElseThrow(
        () -> new IllegalStateException("Thiếu dữ liệu")
);
~~~

Cả hai cách có trong Java 8. `result.orElseThrow()` không tham số chưa có trong Java 8.

### Bài 7. toMap với khóa trùng

**Đề:** Dữ liệu có hai chuỗi `"an"` và `"bo"`. Điều gì xảy ra khi `Collectors.toMap(String::length, Function.identity())`?

**Đáp án:** Cùng khóa `2`, overload hai tham số ném `IllegalStateException`. Nếu nghiệp vụ cho phép trùng, thêm merge function rõ ràng hoặc dùng `groupingBy`.

### Bài 8. Có cần FlatMapping từ Java 9?

**Đề:** Dùng Java 8 để làm phẳng `List<List<Integer>>`.

**Đáp án:**

~~~java
List<Integer> flat = nested.stream()
        .flatMap(List::stream)
        .collect(Collectors.toList());
~~~

`Stream.flatMap` đã có trong Java 8. `Collectors.flatMapping` là downstream adapter mới hơn.

### Bài 9. takeWhile có thể thay bằng filter không?

**Đề:** Nguồn có thứ tự `[1,3,8,2,4]`, cần các phần tử **trước số đầu tiên ≥ 5**. Dùng `filter(n -> n < 5)` có đúng không?

**Đáp án:** Không. `filter` trả `[1,3,2,4]`; tiền tố đúng là `[1,3]`. Trên Java 8, dùng vòng lặp với `break` hoặc nguồn tùy chỉnh có điều kiện dừng.

### Bài 10. Vì sao Stream không tái sử dụng?

**Đề:** Có thể gọi `Stream<Integer> s = list.stream(); s.count(); s.findFirst();` không?

**Đáp án:** Không. `count()` là terminal operation đã tiêu thụ Stream. Tạo `list.stream()` lần nữa cho phép tìm.

### Bài 11. reduce sai identity

**Đề:** Vì sao `reduce(10, Integer::sum)` không đúng để tính tổng bình thường, nhất là trên parallel stream?

**Đáp án:** Identity của phép cộng là `0`, không phải 10. Nhiều phân vùng có thể mỗi phần cộng thêm 10. Dùng `reduce(0, Integer::sum)`; nếu nghiệp vụ có phí cộng thêm 10, áp dụng một lần sau khi giảm gộp.

### Bài 12. Có thể dùng ArrayList chung với parallel forEach?

**Đề:** Việc gọi `parallelStream().forEach(sharedList::add)` khi `sharedList` là `ArrayList` có an toàn không?

**Đáp án:** Không. `ArrayList` không thread-safe cho nhiều lần ghi đồng thời. Dùng `collect(Collectors.toList())` hoặc collector có supplier/combiner đúng hợp đồng.

### Bài 13. Collectors.toList có đảm bảo read-only?

**Đề:** Có thể dựa vào `Collectors.toList()` trả danh sách không chỉnh sửa được không?

**Đáp án:** Không. Collector không bảo đảm loại List hoặc tính bất biến. Nếu cần snapshot cấu trúc không thể sửa trên Java 8, dùng `Collections.unmodifiableList(new ArrayList<>(list))`.

### Bài 14. Xử lý I/O bằng Stream

**Đề:** Vì sao phải dùng `try-with-resources` với `Files.lines(...)`?

**Đáp án:** Stream tệp có thể giữ file handle/tài nguyên mở. Terminal operation không tự động đóng nguồn; cần bảo đảm gọi `close()` khi hoàn tất hoặc có lỗi.

### Bài 15. Biên dịch trên JDK mới cho Java 8

**Đề:** Đang dùng javac của JDK 17, cần phát hành chương trình cho Java 8. Nên chọn cách nào?

**Đáp án:** Dùng `javac --release 8 ...` để chặn tham chiếu API sau Java 8 và phát hành bytecode phù hợp. `--release` có từ JDK 9, không có trong javac JDK 8.

### Bài 16. Không nhầm Collector và Spliterator

**Đề:** `Collector.Characteristics.CONCURRENT` có cùng nghĩa `Spliterator.CONCURRENT` không?

**Đáp án:** Không. Một cờ mô tả khả năng tích lũy của collector, cờ kia mô tả nguồn có hỗ trợ sửa đổi đồng thời. Hai hợp đồng liên quan các tầng khác nhau của Stream pipeline.

---

## Tổng kết

Java 8 đã cung cấp **phần lớn nền tảng Java Stream API**: nguồn từ collection/mảng/bộ sinh/I/O, `Stream<T>` và primitive streams, pipeline `filter`/`map`/`flatMap`/`distinct`/`sorted`/`skip`/`limit`, terminal operations, `Optional`, `reduce`, `collect`, `Collectors`, `Spliterator` và `StreamSupport`. Các chủ đề nâng cao như grouping, collector tùy chỉnh và xử lý song song đều đã có điểm xuất phát ngay từ Java 8.

Những tính năng như `Stream.ofNullable`, `takeWhile/dropWhile`, `Optional.stream`, `Collectors.filtering`, `Collectors.teeing`, `Stream.toList`, `mapMulti` và Stream Gatherers là **mở rộng của các JDK sau**. Khi bảo trì dự án Java 8, hãy phân biệt tên API, phiên bản bổ sung và hợp đồng của phương án thay thế, đặc biệt ở các trường hợp rỗng, thứ tự, tính bất biến và tính đúng khi song song.

**Ghi nhớ:** Học **bản đồ API Java 8** trước khi học tính năng Stream mới giúp bạn chọn đúng công cụ, đọc được code cũ và chuyển phiên bản an toàn. Một pipeline ngắn chỉ thực sự tốt khi **biên dịch được trên runtime mục tiêu**, **giữ đúng ý nghĩa nghiệp vụ** và **không dựa vào những bảo đảm mà API chưa hứa**.

