# Mô hình IntStream, LongStream và DoubleStream

> **Chương:** Stream kiểu nguyên thủy  
> **Module:** JAVA_STREAM_API  
> **Mục tiêu:** Hiểu mô hình của ba Stream chuyên biệt cho dữ liệu số nguyên thủy, biết tạo nguồn, xây dựng pipeline, chuyển đổi kiểu, tổng hợp kết quả và lựa chọn API phù hợp với độ chính xác, tài nguyên, hiệu năng.

Trong Java, `Stream<T>` thường được dùng để xử lý dữ liệu theo phong cách khai báo: tạo nguồn, ghép các phép toán trung gian như `filter` và `map`, rồi thực hiện phép kết thúc như `reduce` hoặc `collect`. Tuy nhiên, khi mỗi phần tử chỉ là một số `int`, `long` hoặc `double`, đưa số vào `Stream<Integer>`, `Stream<Long>` hoặc `Stream<Double>` có thể phát sinh **boxing/unboxing**: chuyển giữa kiểu nguyên thủy và đối tượng wrapper.

Java Stream API cung cấp ba giao diện chuyên biệt:

- **`IntStream`:** xử lý các giá trị `int`.
- **`LongStream`:** xử lý các giá trị `long`.
- **`DoubleStream`:** xử lý các giá trị `double`.

Các giao diện này giúp diễn đạt những phép tính số học, lọc, ánh xạ, thống kê mà không cần bọc mỗi phần tử thành một wrapper chỉ để di chuyển qua pipeline. Trong module **JAVA_STREAM_API**, mô hình này kết nối trực tiếp với pipeline lazy, `filter`, `map`, `reduce`, `collect`, grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và giới hạn về trạng thái, tài nguyên, hiệu năng. Những phần học nâng cao như Stream Gatherers vẫn cần dựa trên nhận thức đúng về kiểu phần tử và cách chuyển sang `Stream<T>` khi API yêu cầu.

Các ví dụ dùng Java 17+ để có `List.of(...)`, record và `Stream.toList()`. Bản thân các primitive stream và phần lớn phương thức trình bày đã có từ Java 8; một số overload `iterate(seed, predicate, next)` có từ Java 9.

## 1. Ba loại primitive stream nằm ở đâu trong hệ thống Stream?

Một sơ đồ đơn giản:

```text
                     BaseStream<T, S>
                     /      |      \
                    /       |       \
              Stream<T>  IntStream  LongStream  DoubleStream
                  |         |          |           |
           phần tử object  int        long        double
                  |         |          |           |
               map(...)    sum()      sum()       sum()
               collect()   average()  average()   average()
                           toArray()  toArray()   toArray()
```

Sơ đồ minh họa mối quan hệ API, không diễn đạt đầy đủ cây kế thừa. Về mặt kiểu, `IntStream`, `LongStream` và `DoubleStream` là các giao diện chuyên biệt mở rộng `BaseStream`, **không phải** các subtype của `Stream<Integer>`, `Stream<Long>` hay `Stream<Double>`.

| Đặc điểm | `Stream<T>` | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- | --- |
| Dạng phần tử | Đối tượng `T` | `int` | `long` | `double` |
| Ví dụ giá trị | `Integer.valueOf(5)` | `5` | `5L` | `5.0` |
| `map` | `Function<T,R>` | `IntUnaryOperator` | `LongUnaryOperator` | `DoubleUnaryOperator` |
| `filter` | `Predicate<T>` | `IntPredicate` | `LongPredicate` | `DoublePredicate` |
| Tính tổng trực tiếp | Không có `sum()` tổng quát | `sum(): int` | `sum(): long` | `sum(): double` |
| Tính trung bình | Tự xây logic/collector | `average(): OptionalDouble` | `average(): OptionalDouble` | `average(): OptionalDouble` |
| Thu mảng | `Object[]` hoặc `T[]` theo generator | `int[]` | `long[]` | `double[]` |
| Chuyển về object stream | Đã là object stream | `boxed()` → `Stream<Integer>` | `boxed()` → `Stream<Long>` | `boxed()` → `Stream<Double>` |

### 1.1. Vì sao không dùng Stream<Integer> trong mọi trường hợp?

`Integer` là một đối tượng wrapper, còn `int` là giá trị nguyên thủy. Chẳng hạn:

```java
Stream<Integer> objectNumbers = Stream.of(1, 2, 3);
IntStream primitiveNumbers = IntStream.of(1, 2, 3);
```

Hai nguồn biểu diễn cùng các giá trị số, nhưng đường xử lý khác nhau:

```text
Stream<Integer>
  Integer ──unbox──► int ──tính toán──► int ──box──► Integer
       (có thể xuất hiện ở các phép biến đổi liên quan)

IntStream
    int ────────────► int ────────────► int
```

Không nên kết luận rằng mọi thao tác trên `Stream<Integer>` đều tạo một đối tượng mới: JVM và JIT có các tối ưu riêng, còn tốc độ phụ thuộc dữ liệu thực tế. Nhưng primitive stream **diễn đạt rõ ý định xử lý số** và tránh yêu cầu wrapper ở giao diện của các phép toán chuyên biệt.

### 1.2. Không có FloatStream, ByteStream hay ShortStream chuẩn

Trong `java.util.stream`, ba giao diện primitive stream chuẩn là `IntStream`, `LongStream` và `DoubleStream`. Java không có `FloatStream`, `ByteStream` hay `ShortStream` tương ứng trong API này.

Khi cần tính toán với `byte`, `short` hoặc `char`, có thể dùng `IntStream` sau khi chuyển/widen giá trị thích hợp; với `float` có thể sử dụng `DoubleStream` nếu việc chuyển sang `double` phù hợp bài toán. Đừng coi cách chuyển này là sự bảo đảm về kết quả biểu diễn dưới dạng số thập phân tuyệt đối.

## 2. Cấu trúc pipeline không thay đổi

Dù là `Stream<T>` hay primitive stream, pipeline vẫn có ba phần:

```text
NGUỒN                       TRUNG GIAN                    KẾT THÚC
IntStream.range(1, 8)  →  filter(n -> n % 2 == 0)  →  sum()
                          map(n -> n * n)
```

Ví dụ:

```java
import java.util.stream.IntStream;

class FirstIntStream {
    public static void main(String[] args) {
        int sumOfSquares = IntStream.range(1, 8)
            .filter(n -> n % 2 == 0) // 2, 4, 6
            .map(n -> n * n)         // 4, 16, 36
            .sum();                  // 56

        System.out.println(sumOfSquares);
    }
}
```

`filter` và `map` chỉ mô tả phép biến đổi; khi `sum()` được gọi, pipeline được đánh giá. Nguyên tắc **lazy evaluation** và **một Stream chỉ tiêu thụ một lần** vẫn được áp dụng.

```java
IntStream numbers = IntStream.of(1, 2, 3);

int sum = numbers.sum(); // 6
// long count = numbers.count(); // Sai: Stream đã được tiêu thụ.
```

Muốn tính nhiều kết quả, tạo Stream mới từ nguồn có thể duyệt lại hoặc tạo kết quả tổng hợp trong một lượt nếu API hỗ trợ.

## 3. Tạo IntStream, LongStream và DoubleStream từ đâu?

### 3.1. Từ giá trị trực tiếp: of và empty

```java
IntStream a = IntStream.of(10, 20, 30);
LongStream b = LongStream.of(1L, 2L, 3L);
DoubleStream c = DoubleStream.of(1.5, 2.0, 3.25);

int[] values = a.toArray();       // [10, 20, 30]
long totalLong = b.sum();         // 6
double totalDouble = c.sum();     // 6.75

long emptyCount = IntStream.empty().count(); // 0
```

Các `of` có overload nhận một giá trị hoặc mảng cùng kiểu nguyên thủy. Không cần truyền wrapper vào chúng.

### 3.2. Từ mảng nguyên thủy

`Arrays.stream` cung cấp overload dành cho `int[]`, `long[]` và `double[]`:

```java
import java.util.Arrays;

int max = Arrays.stream(new int[] {3, 10, 7})
    .max()
    .orElseThrow(); // 10

long count = Arrays.stream(new long[] {100L, 200L})
    .count(); // 2

double average = Arrays.stream(new double[] {1.0, 3.0})
    .average()
    .orElseThrow(); // 2.0
```

Nếu đối tượng đang là `int[]`, `Arrays.stream(data)` thường biểu đạt rõ ràng hơn cách tự bọc thành `Stream<Integer>`.

**Phân biệt `int[]` với `Integer[]`:** `Arrays.stream(new Integer[] {1, 2})` trả về `Stream<Integer>` vì đây là mảng đối tượng; `Arrays.stream(new int[] {1, 2})` trả về `IntStream`.

### 3.3. Tạo dãy nguyên: range và rangeClosed

`IntStream` và `LongStream` có hai factory method dành cho dãy liên tiếp:

| Phương thức | Giá trị tạo ra | Ghi nhớ |
| --- | --- | --- |
| `IntStream.range(2, 6)` | `2, 3, 4, 5` | Cận cuối **loại trừ**. |
| `IntStream.rangeClosed(2, 6)` | `2, 3, 4, 5, 6` | Cận cuối **bao gồm**. |
| `LongStream.range(2L, 6L)` | `2, 3, 4, 5` dạng `long` | Cận cuối loại trừ. |
| `LongStream.rangeClosed(2L, 6L)` | `2, 3, 4, 5, 6` dạng `long` | Cận cuối bao gồm. |

Ví dụ tạo chỉ số mảng:

```java
String[] names = {"An", "Bình", "Chi"};

List<String> labels = IntStream.range(0, names.length)
    .mapToObj(index -> index + ": " + names[index])
    .toList();

// [0: An, 1: Bình, 2: Chi]
```

Nếu `startInclusive >= endExclusive`, `range` không tạo phần tử; nếu `startInclusive > endInclusive`, `rangeClosed` cũng không tạo phần tử.

`DoubleStream` không có `range` hoặc `rangeClosed` chuẩn. Tự sinh dãy `double` bằng cách cộng một bước số thực nhiều lần có thể tích lũy sai số; nếu cần dãy mốc cố định, cân nhắc sinh chỉ số bằng `IntStream` rồi ánh xạ:

```java
double[] values = IntStream.rangeClosed(0, 4)
    .mapToDouble(index -> index * 0.25)
    .toArray(); // [0.0, 0.25, 0.5, 0.75, 1.0]
```

### 3.4. Từ một quy tắc sinh dữ liệu: iterate và generate

`iterate` thường diễn đạt một dãy mà phần tử sau phụ thuộc phần tử trước:

```java
int[] powersOfTwo = IntStream.iterate(1, n -> n * 2)
    .limit(5)
    .toArray(); // [1, 2, 4, 8, 16]
```

Từ Java 9, có overload gồm điều kiện dừng:

```java
long[] multiples = LongStream.iterate(
        2L,
        n -> n <= 10L,
        n -> n + 2L
    )
    .toArray(); // [2, 4, 6, 8, 10]
```

`generate` nhận một supplier và gọi khi cần giá trị tiếp theo:

```java
double[] fixedValues = DoubleStream.generate(() -> 1.25)
    .limit(3)
    .toArray(); // [1.25, 1.25, 1.25]
```

Các nguồn `iterate` hoặc `generate` không có điểm kết thúc tự nhiên khi dùng overload vô hạn. Với các phép kết thúc cần đọc hết nguồn như `sum`, `toArray` hay `sorted` toàn cục, phải bảo đảm pipeline có cơ chế kết thúc phù hợp.

### 3.5. Từ Collection, văn bản hoặc API khác

Khi bắt đầu với collection đối tượng, chuyển sang primitive stream bằng `mapToInt`, `mapToLong` hoặc `mapToDouble`:

```java
List<String> numbers = List.of("5", "12", "8");

int total = numbers.stream()
    .mapToInt(Integer::parseInt)
    .sum(); // 25
```

Từ `String`, hai phương thức đặc biệt:

```java
IntStream utf16Units = "Java".chars();
IntStream codePoints = "Java".codePoints();
```

`chars()` trả các đơn vị mã UTF-16 dưới dạng `int`, còn `codePoints()` trả các Unicode code point. Với ký tự ngoài BMP, một code point có thể được biểu diễn bởi hai UTF-16 code unit; hai Stream có thể khác số phần tử.

Nếu đọc dữ liệu từ tệp bằng `Files.lines(path)`, có thể chuyển các dòng sang số:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

class ReadScores {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("scores.txt"); // Mỗi dòng là một số nguyên hợp lệ.

        try (Stream<String> lines = Files.lines(path)) {
            int total = lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .mapToInt(Integer::parseInt)
                .sum();

            System.out.println(total);
        }
    }
}
```

`Files.lines` cần được đóng qua `try-with-resources`. Chuyển sang `IntStream` **không tự giải phóng tài nguyên** của Stream đọc tệp; phải quản lý vòng đời của nguồn.

## 4. Các phép toán trung gian chuyên biệt

Ba primitive stream cung cấp nhiều phép toán tương tự `Stream<T>`, nhưng nhận functional interface chuyên biệt:

| Thao tác | `IntStream` | `LongStream` | `DoubleStream` |
| --- | --- | --- | --- |
| Lọc phần tử | `filter(IntPredicate)` | `filter(LongPredicate)` | `filter(DoublePredicate)` |
| Ánh xạ cùng kiểu | `map(IntUnaryOperator)` | `map(LongUnaryOperator)` | `map(DoubleUnaryOperator)` |
| Ghép Stream con | `flatMap(IntFunction<? extends IntStream>)` | `flatMap(LongFunction<? extends LongStream>)` | `flatMap(DoubleFunction<? extends DoubleStream>)` |
| Loại trùng | `distinct()` | `distinct()` | `distinct()` |
| Sắp tăng dần | `sorted()` | `sorted()` | `sorted()` |
| Giới hạn/bỏ qua | `limit`, `skip` | `limit`, `skip` | `limit`, `skip` |
| Quan sát phần tử | `peek(IntConsumer)` | `peek(LongConsumer)` | `peek(DoubleConsumer)` |

### 4.1. filter và map giữ kiểu nguyên thủy

```java
int[] results = IntStream.of(-3, 2, 5, 6, 2)
    .filter(n -> n > 0)
    .map(n -> n * n)
    .distinct()
    .sorted()
    .toArray();

// [4, 25, 36]
```

Sau mỗi phép `filter`, `map`, `distinct` và `sorted` trên `IntStream`, kiểu trả về vẫn là `IntStream`. Tương tự với `LongStream`, `DoubleStream` khi dùng overload cùng kiểu.

`sorted()` của primitive stream dùng thứ tự tự nhiên của loại số. Khác với `Stream<T>.sorted(comparator)`, primitive stream **không có overload `sorted(Comparator)`**. Nếu cần quy tắc so sánh tùy chỉnh, có thể `boxed()` rồi `sorted(comparator)`:

```java
List<Integer> descending = IntStream.of(3, 1, 2)
    .boxed()
    .sorted(Comparator.reverseOrder())
    .toList(); // [3, 2, 1]
```

Ví dụ cần `import java.util.Comparator;`. Đổi sang object stream kéo theo wrapper; cân nhắc điều đó nếu đường xử lý có khối lượng dữ liệu rất lớn.

### 4.2. flatMap trên primitive stream

`flatMap` có thể làm mỗi giá trị đầu vào sinh 0, 1 hoặc nhiều giá trị cùng kiểu primitive:

```java
int[] repeated = IntStream.of(1, 3)
    .flatMap(n -> IntStream.rangeClosed(1, n))
    .toArray();

// [1, 1, 2, 3]
```

Đầu vào `1` sinh `1`, còn `3` sinh `1,2,3`. Các Stream con do mapper tạo ra được `flatMap` đóng sau khi nội dung của chúng được đưa vào kết quả theo hợp đồng API.

### 4.3. lazy evaluation và dừng sớm

`filter`, `map`, `peek` và các phép trung gian vẫn có tính **lazy**:

```java
IntStream pipeline = IntStream.rangeClosed(1, 10)
    .filter(n -> {
        System.out.println("Đang xét: " + n);
        return n % 2 == 0;
    });

System.out.println("Đã khai báo pipeline");
int first = pipeline.findFirst().orElseThrow(); // 2
```

Với Stream tuần tự, `findFirst()` chỉ cần xét tới `2`; pipeline không cần quét tất cả mười phần tử. Vì vậy không đặt logic cập nhật trạng thái bắt buộc trong `peek` hoặc các lambda trung gian.

Các phép như `sorted` và `distinct` có trạng thái; chúng có thể làm phát sinh chi phí bộ nhớ hoặc ảnh hưởng khả năng dừng sớm, đặc biệt khi xử lý song song.

## 5. Chuyển giữa primitive stream và Stream<T>

Đây là kỹ năng quan trọng vì nhiều API yêu cầu đối tượng, còn phép toán số lại phù hợp kiểu nguyên thủy.

### 5.1. mapToInt, mapToLong và mapToDouble

Từ `Stream<T>`, các phương thức này dùng hàm trích xuất số:

```java
record Product(String name, int quantity, long unitPrice, double rating) {}

List<Product> products = List.of(
    new Product("Sách", 2, 75_000L, 4.5),
    new Product("Bút", 5, 12_000L, 4.0)
);

int totalQuantity = products.stream()
    .mapToInt(Product::quantity)
    .sum(); // 7

long totalRevenue = products.stream()
    .mapToLong(p -> p.unitPrice() * p.quantity())
    .sum(); // 210000

double averageRating = products.stream()
    .mapToDouble(Product::rating)
    .average()
    .orElse(0.0); // 4.25
```

`mapToInt` nhận `ToIntFunction<Product>`; `mapToLong` nhận `ToLongFunction<Product>`; `mapToDouble` nhận `ToDoubleFunction<Product>`.

Cách tính doanh thu bằng `long` ở trên giả định phép nhân và tổng không vượt `Long.MAX_VALUE`. Với nghiệp vụ yêu cầu kiểm soát tràn số, cần thêm kiểm tra số học hoặc chọn kiểu dữ liệu phù hợp.

### 5.2. boxed: quay về wrapper stream

`boxed()` chuyển các giá trị nguyên thủy thành wrapper tương ứng:

```java
List<Integer> ids = IntStream.rangeClosed(1, 4)
    .boxed()
    .toList(); // [1, 2, 3, 4]

List<Long> times = LongStream.of(10L, 20L)
    .boxed()
    .toList(); // [10, 20]

List<Double> temperatures = DoubleStream.of(20.5, 22.0)
    .boxed()
    .toList(); // [20.5, 22.0]
```

`boxed()` hữu ích khi:

- Cần `List<Integer>`, `List<Long>`, `List<Double>`.
- Cần `Collectors.groupingBy`, `Collectors.toMap` hoặc collector chỉ có trên `Stream<T>`.
- Cần truyền `Comparator` tùy chỉnh cho `sorted(comparator)`.
- Cần API chỉ chấp nhận `Stream<T>` hoặc collection đối tượng.

Không phải pipeline nào cũng nên `boxed()` ngay từ đầu: giữ phần xử lý số nguyên thủy trong `IntStream`/`LongStream`/`DoubleStream` lâu nhất có ích, rồi chuyển khi thực sự cần đối tượng.

### 5.3. mapToObj: tạo đối tượng từ giá trị số

Nếu kết quả là đối tượng không phải wrapper của chính số đó, dùng `mapToObj`:

```java
List<String> labels = IntStream.rangeClosed(1, 3)
    .mapToObj(n -> "Mục " + n)
    .toList();

// [Mục 1, Mục 2, Mục 3]
```

Một ví dụ dùng mảng:

```java
String[] names = {"An", "Bình", "Chi"};

List<String> indexed = IntStream.range(0, names.length)
    .mapToObj(i -> (i + 1) + ". " + names[i])
    .toList();

// [1. An, 2. Bình, 3. Chi]
```

`mapToObj` trả về `Stream<R>`; các phép sau đó sử dụng API của object stream.

### 5.4. Chuyển giữa các loại primitive stream

Bảng thao tác:

| Nguồn | Phép toán | Đầu ra |
| --- | --- | --- |
| `IntStream` | `asLongStream()` | `LongStream` (widening `int → long`). |
| `IntStream` | `asDoubleStream()` | `DoubleStream` (widening `int → double`). |
| `LongStream` | `asDoubleStream()` | `DoubleStream` (`long → double`, có thể mất độ chính xác). |
| `IntStream` | `mapToLong(IntToLongFunction)` | `LongStream`. |
| `IntStream` | `mapToDouble(IntToDoubleFunction)` | `DoubleStream`. |
| `LongStream` | `mapToInt(LongToIntFunction)` | `IntStream`. |
| `DoubleStream` | `mapToInt(DoubleToIntFunction)` | `IntStream`. |
| `DoubleStream` | `mapToLong(DoubleToLongFunction)` | `LongStream`. |

Ví dụ:

```java
long total = IntStream.of(100, 200, 300)
    .asLongStream()
    .sum(); // 600

double adjusted = LongStream.of(1L, 2L, 3L)
    .mapToDouble(n -> n * 1.5)
    .sum(); // 9.0
```

Không có phương thức `asIntStream()` trên `LongStream` hay `DoubleStream`. Phải lựa chọn phép chuyển hẹp bằng `mapToInt` và chấp nhận/kiểm soát quy tắc ép kiểu.

Ví dụ, `(int) someLong` có thể cắt mất bit cao và không báo lỗi; `Math.toIntExact(someLong)` sẽ ném `ArithmeticException` nếu vượt phạm vi `int`:

```java
int[] exact = LongStream.of(10L, 20L)
    .mapToInt(Math::toIntExact)
    .toArray(); // [10, 20]
```

## 6. Phép kết thúc chuyên biệt cho số học

Các primitive stream có sẵn những phép kết thúc mà `Stream<T>` tổng quát không có:

| Phép toán | IntStream | LongStream | DoubleStream |
| --- | --- | --- | --- |
| `sum()` | `int` | `long` | `double` |
| `average()` | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` |
| `min()` / `max()` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `count()` | `long` | `long` | `long` |
| `summaryStatistics()` | `IntSummaryStatistics` | `LongSummaryStatistics` | `DoubleSummaryStatistics` |
| `reduce(identity, op)` | `int` | `long` | `double` |
| `reduce(op)` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |
| `toArray()` | `int[]` | `long[]` | `double[]` |
| `anyMatch/allMatch/noneMatch` | `boolean` | `boolean` | `boolean` |
| `findFirst/findAny` | `OptionalInt` | `OptionalLong` | `OptionalDouble` |

### 6.1. sum, count, min và max

```java
int sum = IntStream.of(3, 6, 9).sum();      // 18
long count = LongStream.of(3L, 6L).count(); // 2

int min = IntStream.of(7, 2, 5)
    .min()
    .orElseThrow(); // 2

double max = DoubleStream.of(1.5, 3.5, 2.0)
    .max()
    .orElseThrow(); // 3.5
```

`count()` trả về `long` ngay cả khi phần tử thuộc `IntStream`. Điều này thể hiện sự khác nhau giữa **kiểu của mỗi phần tử** và **kiểu của kết quả tổng hợp**.

### 6.2. average trả OptionalDouble

`average()` có thể không có kết quả với Stream rỗng, nên Java trả `OptionalDouble`:

```java
OptionalDouble avg = IntStream.of(10, 20, 30).average();

if (avg.isPresent()) {
    System.out.println(avg.getAsDouble()); // 20.0
}
```

Có thể dùng `orElse(...)` nếu ứng dụng có chính sách mặc định:

```java
double averageOrZero = IntStream.empty()
    .average()
    .orElse(0.0);
```

`0.0` trong ví dụ là **lựa chọn của ứng dụng**, không phải giá trị trung bình toán học của tập rỗng. Khi kết quả rỗng mang ý nghĩa nghiệp vụ, giữ `OptionalDouble` để nơi gọi quyết định cách xử lý.

### 6.3. summaryStatistics: nhiều thống kê trong một lần duyệt

`summaryStatistics()` tính các đại lượng đếm, tổng, nhỏ nhất, lớn nhất và trung bình trên cùng một Stream:

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

class ScoresStatistics {
    public static void main(String[] args) {
        IntSummaryStatistics stats = IntStream.of(6, 8, 10, 8)
            .summaryStatistics();

        System.out.println(stats.getCount());   // 4
        System.out.println(stats.getSum());     // 32 (long)
        System.out.println(stats.getMin());     // 6
        System.out.println(stats.getMax());     // 10
        System.out.println(stats.getAverage()); // 8.0
    }
}
```

Tương tự:

```java
LongSummaryStatistics longStats =
    LongStream.of(10L, 20L, 30L).summaryStatistics();

DoubleSummaryStatistics doubleStats =
    DoubleStream.of(1.5, 2.5, 3.0).summaryStatistics();
```

Hai lớp `LongSummaryStatistics` và `DoubleSummaryStatistics` nằm trong `java.util`. Nếu chương trình cần đồng thời nhiều thông số, một lời gọi `summaryStatistics()` thường rõ ràng hơn việc tạo Stream mới để gọi `sum`, `min`, `max`, `average` từng lần.

### 6.4. reduce và tính kết hợp

`reduce` dùng hàm kết hợp để thu các phần tử về một giá trị:

```java
int product = IntStream.of(2, 3, 4)
    .reduce(1, (left, right) -> left * right); // 24

long sum = LongStream.of(10L, 20L, 30L)
    .reduce(0L, Long::sum); // 60
```

Với nguồn có thể xử lý song song, toán tử của `reduce` cần thỏa tính kết hợp (*associativity*), identity phải phù hợp. Phép trừ `(a, b) -> a - b` không kết hợp, nên kết quả có thể thay đổi khi các phần tử được nhóm theo cách khác.

Với số thực, **tính toán `double` không tuân thủ tính kết hợp toán học một cách chính xác trong mọi trường hợp** do làm tròn. Dùng `sum()` và `summaryStatistics()` khi phù hợp thay vì tự viết phép giảm cộng số thực mà kỳ vọng kết quả tuyệt đối giống nhau giữa mọi thứ tự đánh giá.

## 7. collect trên primitive stream khác collect(Collector) thế nào?

`Stream<T>` có overload phổ biến:

```java
<R, A> R collect(Collector<? super T, A, R> collector);
```

Primitive stream có phép `collect` riêng nhận **ba tham số**:

```java
// Hình dạng chữ ký rút gọn của IntStream:
<R> R collect(
    Supplier<R> supplier,
    ObjIntConsumer<R> accumulator,
    BiConsumer<R, R> combiner
);
```

Với `LongStream` và `DoubleStream`, accumulator lần lượt là `ObjLongConsumer<R>` và `ObjDoubleConsumer<R>`.

Ví dụ tạo StringBuilder từ IntStream:

```java
import java.util.stream.IntStream;

StringBuilder builder = IntStream.rangeClosed(1, 4)
    .collect(
        StringBuilder::new,
        (text, number) -> {
            if (text.length() > 0) text.append(", ");
            text.append(number);
        },
        (left, right) -> {
            if (left.length() > 0 && right.length() > 0) {
                left.append(", ");
            }
            left.append(right);
        }
    );

System.out.println(builder.toString()); // 1, 2, 3, 4
```

`supplier` tạo vùng tích lũy, `accumulator` cập nhật bằng từng giá trị nguyên thủy và `combiner` hợp nhất kết quả từng phần khi framework cần, chẳng hạn trong xử lý song song. Hàm gộp phải tương thích về ngữ nghĩa với hàm tích lũy và giá trị ban đầu.

Khi muốn dùng `Collectors.groupingBy`, chuyển sang object stream:

```java
Map<String, Long> counts = IntStream.of(1, 2, 3, 4, 5, 6)
    .boxed()
    .collect(Collectors.groupingBy(
        n -> n % 2 == 0 ? "chẵn" : "lẻ",
        Collectors.counting()
    ));

// {chẵn=3, lẻ=3} (thứ tự khóa trong Map không được bảo đảm)
```

Ví dụ cần import `java.util.Map` và `java.util.stream.Collectors`. Đây là điểm kết nối với nội dung grouping và collector tùy chỉnh của module JAVA_STREAM_API: nhiều collector chuẩn xử lý đối tượng, trong khi primitive stream tối ưu cho phép tính số.

## 8. Ví dụ hoàn chỉnh: thống kê dòng hàng

Xét các dòng trong đơn hàng có số lượng `int`, đơn giá nguyên `long` và điểm đánh giá `double`. Mục tiêu là đếm tổng số lượng, tính doanh thu, lấy giá trị trung bình và gom doanh thu theo nhóm hàng.

Ví dụ chạy độc lập trên Java 17+; lưu dưới tên `PrimitiveStreamDemo.java`:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class PrimitiveStreamDemo {
    record OrderLine(
        String category,
        int quantity,
        long unitPrice,
        double rating
    ) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("Sách", 2, 120_000L, 4.5),
            new OrderLine("Sách", 1, 80_000L, 4.0),
            new OrderLine("Thiết bị", 3, 150_000L, 5.0),
            new OrderLine("Thiết bị", 0, 200_000L, 4.0)
        );

        // Stream<OrderLine> -> IntStream -> IntSummaryStatistics.
        IntSummaryStatistics quantityStats = lines.stream()
            .mapToInt(OrderLine::quantity)
            .summaryStatistics();

        // Stream<OrderLine> -> LongStream -> long.
        long totalRevenue = lines.stream()
            .mapToLong(line ->
                Math.multiplyExact(
                    (long) line.quantity(),
                    line.unitPrice()
                )
            )
            .sum();

        // Stream<OrderLine> -> DoubleStream -> OptionalDouble.
        OptionalDouble averageRating = lines.stream()
            .filter(line -> line.quantity() > 0)
            .mapToDouble(OrderLine::rating)
            .average();

        // Khi cần grouping, dùng Collector trên Stream<OrderLine>.
        Map<String, Long> revenueByCategory = lines.stream()
            .collect(Collectors.groupingBy(
                OrderLine::category,
                TreeMap::new,
                Collectors.summingLong(line ->
                    Math.multiplyExact(
                        (long) line.quantity(),
                        line.unitPrice()
                    )
                )
            ));

        System.out.println(quantityStats.getSum());         // 6
        System.out.println(totalRevenue);                   // 770000
        System.out.println(averageRating.orElse(0.0));      // 4.5
        System.out.println(revenueByCategory);
        // {Sách=320000, Thiết bị=450000}
    }
}
```

Phân tích cấu trúc:

| Mục tiêu | Đường xử lý | Lý do chọn |
| --- | --- | --- |
| Tổng số lượng và các thống kê liên quan | `mapToInt(OrderLine::quantity).summaryStatistics()` | Giữ dữ liệu `int` và nhận tổng `long` cùng min/max/count/average. |
| Doanh thu toàn bộ | `mapToLong(...).sum()` | Số tiền dạng số nguyên `long` để tránh sai số số thực cho giá trị tiền nguyên. |
| Trung bình điểm đánh giá | `mapToDouble(OrderLine::rating).average()` | Kết quả có kiểu `OptionalDouble` vì tập được lọc có thể rỗng. |
| Doanh thu theo nhóm | `collect(groupingBy(..., summingLong(...)))` | Dùng collector để xây `Map<String,Long>` từ các đối tượng nghiệp vụ. |

Tổng doanh thu `770000` không vượt phạm vi `long` trong ví dụ. `Math.multiplyExact` phát hiện tràn số ở **từng phép nhân**, nhưng `LongStream.sum()` và phép cộng của `Collectors.summingLong` vẫn có thể tràn số nếu tổng vượt phạm vi `long`. Với nghiệp vụ cần bảo đảm không tràn, phải chọn chiến lược cộng có kiểm tra (như `Math.addExact` trong phép giảm thích hợp) hoặc một kiểu số lớn hơn.

Điểm đánh giá `4.5` ở đây là trung bình của ba **dòng hàng có số lượng dương**, không phải trung bình được gia quyền theo số đơn vị sản phẩm. Nếu yêu cầu là trung bình gia quyền, phải nhân điểm với trọng số và chia cho tổng trọng số.

## 9. IntStream và LongStream: tràn số nguyên

Primitive stream không tự thay đổi miền giá trị của kiểu số. `IntStream.sum()` trả về `int` và có thể tràn khi tổng vượt giới hạn:

```java
int overflow = IntStream.of(Integer.MAX_VALUE, 1)
    .sum();

System.out.println(overflow); // -2147483648 (tràn số int)
```

Nếu muốn chuyển từng `int` thành `long` trước khi cộng:

```java
long safeForThisInput = IntStream.of(Integer.MAX_VALUE, 1)
    .asLongStream()
    .sum();

System.out.println(safeForThisInput); // 2147483648
```

`LongStream.sum()` cũng có thể tràn `long`. Việc mở rộng từ `int` sang `long` làm tăng miền giá trị nhưng không loại bỏ tất cả rủi ro.

### 9.1. sum và summaryStatistics có kiểu tổng khác nhau

`IntStream.sum()` trả về `int`, trong khi `IntSummaryStatistics.getSum()` trả về `long`:

```java
long sum = IntStream.of(Integer.MAX_VALUE, 1)
    .summaryStatistics()
    .getSum(); // 2147483648
```

Đây là một khác biệt quan trọng khi tổng có thể vượt `Integer.MAX_VALUE`. Với bài toán chỉ cần tổng `long`, `asLongStream().sum()` thường đơn giản hơn và thể hiện chủ đích rõ ràng.

### 9.2. Kiểm tra tràn số trước khi tạo kết quả

Nếu nghiệp vụ bắt buộc báo lỗi khi tổng vượt `long`:

```java
long exact = LongStream.of(10L, 20L, 30L)
    .reduce(0L, Math::addExact); // 60
```

`Math.addExact` ném `ArithmeticException` nếu phép cộng trung gian tràn. Phép cộng kiểm tra này có tính kết hợp về kết quả trong miền có thể biểu diễn, nhưng với tổng có thể vượt giới hạn, thứ tự nhóm phép cộng trong parallel stream vẫn ảnh hưởng **thời điểm hoặc việc có phát hiện tràn trung gian**; hãy lựa chọn chính sách xử lý dữ liệu và thứ tự thực thi phù hợp.

Nếu cần tổng vượt phạm vi `long`, cân nhắc `BigInteger`. Nếu dữ liệu tiền tệ có phần thập phân và đòi hỏi làm tròn theo quy tắc tài chính, cân nhắc lưu đơn vị nhỏ nhất dạng số nguyên hoặc dùng `BigDecimal`; `DoubleStream` không phải công cụ bảo đảm tính chính xác tiền tệ thập phân.

## 10. DoubleStream: sai số, NaN và vô cực

`double` là số dấu phẩy động nhị phân IEEE 754. Nhiều phân số thập phân không biểu diễn chính xác dưới dạng nhị phân:

```java
double result = DoubleStream.of(0.1, 0.2).sum();

System.out.println(result == 0.3); // Không nên dựa vào phép so sánh này.
```

Trong ví dụ, kết quả in của biểu thức so sánh phụ thuộc biểu diễn và thuật toán cộng; điều cần ghi nhớ là **không lấy phép bằng tuyệt đối giữa hai kết quả số thực tính toán làm quy tắc nghiệp vụ chung**.

### 10.1. sum() và average() có độ chính xác hữu hạn

`DoubleStream.sum()` cho phép triển khai dùng phương pháp cộng có bù để cải thiện độ chính xác, nhưng API **không bảo đảm một thứ tự cộng cố định**; các cách nhóm phép cộng hoặc chạy song song có thể tạo kết quả hơi khác do làm tròn.

```java
double sum = DoubleStream.of(0.1, 0.2, 0.3).sum();
OptionalDouble average = DoubleStream.of(0.1, 0.2, 0.3)
    .average();
```

Khi so sánh kết quả tính toán gần đúng, nên chọn sai số cho phép (*tolerance*) phù hợp miền bài toán:

```java
double expected = 0.6;
double actual = DoubleStream.of(0.1, 0.2, 0.3).sum();

boolean closeEnough = Math.abs(actual - expected) < 1e-9;
```

Ngưỡng `1e-9` chỉ là ví dụ. Với số có độ lớn rất khác nhau, cần cân nhắc sai số tương đối, sai số tuyệt đối hoặc thuật toán số học chuyên biệt.

### 10.2. NaN, Infinity và số 0 âm

`DoubleStream` có thể chứa:

- `Double.NaN`: giá trị *Not a Number*.
- `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY`.
- `0.0` và `-0.0`: đều là số 0 trong nhiều phép toán, nhưng có biểu diễn bit khác nhau.

Ví dụ:

```java
double[] values = DoubleStream.of(
        1.0,
        Double.NaN,
        -0.0,
        0.0,
        Double.POSITIVE_INFINITY
    )
    .sorted()
    .toArray();
```

`DoubleStream.sorted()` dùng thứ tự theo `Double.compare`: `-0.0` đứng trước `0.0`; `NaN` được xem lớn hơn mọi giá trị số theo thứ tự so sánh đó, kể cả `POSITIVE_INFINITY`.

`DoubleStream.distinct()` xác định phần tử trùng theo `Double.doubleToLongBits`; vì vậy `NaN` được coi là trùng với `NaN`, còn `-0.0` và `0.0` được coi là **khác nhau**:

```java
long count = DoubleStream.of(-0.0, 0.0, Double.NaN, Double.NaN)
    .distinct()
    .count(); // 3
```

`DoubleStream.sum()` và `average()` có thể trả về `NaN` khi nguồn chứa `NaN`. Khi xử lý dữ liệu đo lường hoặc thống kê, quyết định rõ cách lọc/ghi nhận giá trị thiếu hoặc không hữu hạn:

```java
double[] finite = DoubleStream.of(1.5, Double.NaN, 3.0,
                                 Double.POSITIVE_INFINITY)
    .filter(Double::isFinite)
    .toArray(); // [1.5, 3.0]
```

**Lưu ý:** việc loại `NaN` hay giá trị vô cực có thể khiến thống kê che giấu lỗi đầu vào. Hãy xác định chính sách dữ liệu trước khi lọc.

### 10.3. long → double có thể mất độ chính xác

`double` có 53 bit chính xác cho phần trị, nên không thể biểu diễn chính xác **mọi** số nguyên `long` lớn.

```java
long value = 9_007_199_254_740_993L; // 2^53 + 1
double asDouble = LongStream.of(value)
    .asDoubleStream()
    .findFirst()
    .orElseThrow();

System.out.println((long) asDouble == value); // false
```

Phép chuyển `long → double` là widening conversion về mặt hệ thống kiểu Java, nhưng không đảm bảo giữ nguyên từng giá trị nguyên lớn. Nếu dữ liệu là ID, timestamp rất lớn hoặc số tiền nguyên tuyệt đối, tránh dùng `DoubleStream` chỉ để thuận tiện tính toán.

## 11. OptionalInt, OptionalLong và OptionalDouble

Các phép `min`, `max`, `findFirst`, `findAny` và `reduce` không có identity cần biểu diễn trường hợp **không có phần tử**.

```java
OptionalInt smallest = IntStream.empty().min();
OptionalLong firstLong = LongStream.empty().findFirst();
OptionalDouble largest = DoubleStream.empty().max();

System.out.println(smallest.isPresent()); // false
System.out.println(firstLong.isEmpty());  // true (Java 11+)
System.out.println(largest.orElse(-1.0)); // -1.0
```

So sánh với `Optional<T>` dùng cho object stream:

| Primitive stream | Kiểu tùy chọn | Lấy giá trị khi có |
| --- | --- | --- |
| `IntStream` | `OptionalInt` | `getAsInt()` |
| `LongStream` | `OptionalLong` | `getAsLong()` |
| `DoubleStream` | `OptionalDouble` | `getAsDouble()` |

Nên ưu tiên `orElse`, `orElseGet` (nơi API hỗ trợ) hoặc `orElseThrow` khi chính sách dữ liệu được xác định rõ. Không gọi `getAsInt()` trên `OptionalInt.empty()` mà chưa kiểm tra, vì có thể ném `NoSuchElementException`.

Với nguồn rỗng, các phép tổng hợp không phải lúc nào cũng trả Optional: `sum()` của `IntStream.empty()` là `0`, `count()` là `0L`, nhưng `average()` là `OptionalDouble.empty()`. Hãy phân biệt giá trị identity của phép cộng với việc không tồn tại giá trị trung bình.

## 12. Nguồn, thứ tự, hiệu năng và parallel stream

Primitive stream có các phép `sequential()`, `parallel()` và `unordered()` như những loại Stream khác. Khi nguồn có thứ tự gặp phần tử, các phép như `findFirst` và `limit` tuân theo thứ tự đó.

```java
long total = LongStream.rangeClosed(1, 1_000_000)
    .parallel()
    .sum();
```

Việc gọi `parallel()` yêu cầu chế độ song song nhưng **không tự bảo đảm nhanh hơn**. Lợi ích phụ thuộc kích thước nguồn, chi phí mỗi phần tử, khả năng chia việc của `Spliterator`, các phép có trạng thái và chi phí phối hợp kết quả.

### 12.1. Giữ lambda không có trạng thái phụ thuộc

Không dùng chung biến đếm mutable giữa các luồng:

```java
// Không nên làm như sau:
// int[] shared = {0};
// IntStream.range(0, 1000).parallel()
//     .forEach(n -> shared[0] += n);
```

Đây là race condition, có thể cho kết quả sai. Hãy dùng phép kết thúc chuyên biệt:

```java
long total = IntStream.range(0, 1000)
    .parallel()
    .asLongStream()
    .sum(); // 499500
```

Các lambda của `filter`, `map` và `reduce` nên không gây tác động phụ làm thay đổi nguồn hoặc trạng thái dùng chung. Mọi collector và hàm tích lũy phải tuân thủ hợp đồng kết hợp khi chạy song song.

### 12.2. Spliterator chuyên biệt

Primitive stream dùng các kiểu `Spliterator.OfInt`, `Spliterator.OfLong` và `Spliterator.OfDouble` khi duyệt hoặc phân chia nguồn, qua đó tránh phải đưa phần tử vào wrapper ở giao diện tiêu thụ chuyên biệt.

Ví dụ truy cập một `Spliterator.OfInt`:

```java
import java.util.Spliterator;
import java.util.stream.IntStream;

class PrimitiveSpliterator {
    public static void main(String[] args) {
        Spliterator.OfInt source = IntStream.range(1, 4)
            .spliterator();

        source.forEachRemaining((int n) -> System.out.println(n));
        // 1, 2, 3
    }
}
```

Không nên tự lấy `Spliterator` từ một Stream, tiêu thụ nó rồi mong tiếp tục gọi terminal operation trên cùng Stream. Việc lấy iterator/spliterator là cách tiêu thụ nguồn của Stream theo vòng đời một lần.

Các đặc tính như `SIZED`, `SUBSIZED`, `ORDERED` có thể hỗ trợ việc phân chia công việc và tối ưu. Những đặc tính này thuộc nguồn thực tế, không tự xuất hiện chỉ vì phần tử có kiểu nguyên thủy.

### 12.3. Boxing và benchmark

Primitive stream thường phù hợp khi pipeline chỉ tính toán trên số. Tuy nhiên, hiệu năng còn chịu ảnh hưởng bởi:

- Kích thước dữ liệu và chi phí tạo nguồn.
- Số phép trung gian và khả năng tối ưu của JVM/JIT.
- Những bước `boxed()` hoặc `mapToObj` cần tạo/điều phối đối tượng.
- Việc phải sắp xếp, loại trùng, gom nhóm hoặc giữ thứ tự khi chạy song song.
- Bộ nhớ, garbage collection và độ lớn của dữ liệu đầu vào.

Không nên viết benchmark chỉ dựa vào một lần đo thời gian chạy. Khi cần quyết định kỹ thuật theo hiệu năng, sử dụng công cụ như JMH và dữ liệu đại diện cho ứng dụng.

## 13. Khi nào chọn loại Stream nào?

| Đầu vào / mục tiêu | Lựa chọn hợp lý | Ghi chú |
| --- | --- | --- |
| Dữ liệu `int[]`, tính tổng hoặc lọc số nguyên | `IntStream` | `Arrays.stream(int[])` hoặc `IntStream.of(...)`. |
| Dãy chỉ số hoặc số nguyên liên tiếp | `IntStream.range/rangeClosed` | Cẩn thận cận cuối loại trừ/bao gồm. |
| Số lượng lớn, timestamp hoặc giá tiền nguyên phạm vi `long` | `LongStream` | Kiểm tra tràn số khi cộng/nhân. |
| Dữ liệu đo lường hay giá trị số thực gần đúng | `DoubleStream` | Chấp nhận sai số nhị phân và chọn chính sách NaN. |
| Danh sách đối tượng, cần tính tổng một thuộc tính `int` | `stream().mapToInt(...).sum()` | Chuyển sang primitive sau khi trích thuộc tính. |
| Danh sách đối tượng, cần tính tổng một thuộc tính `long` | `stream().mapToLong(...).sum()` | Phù hợp thống kê trên số nguyên. |
| Cần `List<Integer>` | `intStream.boxed().toList()` | Có boxing để tạo wrapper. |
| Cần hiển thị nhãn từ chỉ số | `intStream.mapToObj(...)` | Trả về `Stream<R>`. |
| Cần `Collectors.groupingBy` trên giá trị nguyên thủy | `intStream.boxed().collect(...)` | Collector chuẩn chạy trên object stream. |
| Cần sắp xếp số giảm dần tùy chỉnh | `intStream.boxed().sorted(Comparator.reverseOrder())` | Primitive `sorted()` không nhận Comparator. |
| Tính toán tài chính thập phân chính xác | `BigDecimal` hoặc biểu diễn số nguyên đơn vị nhỏ nhất | Tránh giả định `double` chính xác tuyệt đối. |

## 14. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `sum()` trên `Stream<Integer>` | `Stream<T>` không có phép `sum()` chuyên biệt. | `mapToInt(Integer::intValue).sum()` hoặc nguồn `IntStream`. |
| Nghĩ `IntStream` là `Stream<Integer>` | Không tương thích ở các overload yêu cầu `Stream<T>`. | Dùng `boxed()` khi cần wrapper stream. |
| Gọi `collect(Collectors.toList())` trực tiếp trên `IntStream` | Primitive `collect` có chữ ký ba đối số, không nhận `Collector`. | `boxed().collect(Collectors.toList())` hoặc `boxed().toList()`. |
| Dùng `IntStream.sum()` cho tổng có thể vượt `int` | Tràn số và kết quả sai. | `asLongStream().sum()` hoặc phương án kiểm tra tràn. |
| Tính tiền bằng `DoubleStream` rồi so sánh chính xác tuyệt đối | Sai số biểu diễn số thực. | Sử dụng số nguyên đơn vị nhỏ nhất hoặc `BigDecimal` theo yêu cầu. |
| Ép `long` lớn sang `double` và tin rằng luôn bảo toàn giá trị | Có thể mất bit chính xác. | Giữ `long` hoặc chọn kiểu số phù hợp. |
| Gọi `average().getAsDouble()` trên Stream rỗng | `NoSuchElementException`. | Xử lý `OptionalDouble` tường minh. |
| Gọi `sorted(Comparator)` trực tiếp trên `IntStream` | Không có overload nhận Comparator. | `boxed().sorted(comparator)` hoặc thuật toán phù hợp. |
| Bỏ `limit` khi thu Stream được sinh vô hạn | Terminal operation có thể không kết thúc. | Dùng giới hạn/điều kiện dừng phù hợp. |
| Dùng biến mutable chung trong `parallel().forEach` | Race condition. | Dùng `sum`, `reduce`, `summaryStatistics`, `collect` phù hợp. |
| Dùng lại primitive Stream đã có terminal operation | `IllegalStateException`. | Tạo Stream mới từ nguồn có thể duyệt lại. |
| Không đóng Stream đọc dữ liệu từ tệp | Rò rỉ tài nguyên I/O. | `try-with-resources` trên Stream nguồn. |

## 15. Bài tập tự thực hành

**Bài 1 — Dãy số.** Dùng `IntStream.rangeClosed(1, 100)` để tính tổng bình phương các số chia hết cho 3. Diễn giải rõ vai trò nguồn, phép trung gian, phép kết thúc.

**Bài 2 — Thống kê một lượt.** Cho mảng `int[]` chứa 100 điểm thi. Dùng `summaryStatistics()` để lấy số lượng, tổng, min, max, trung bình. So sánh kiểu trả về của `sum()` và `getSum()`.

**Bài 3 — Chuyển đổi kiểu.** Cho `List<String>` gồm các giá trị `"12", "5", "8"`. Chuyển sang `IntStream` và tính tổng. Thử một chuỗi không phải số và quyết định cách xử lý lỗi `NumberFormatException`.

**Bài 4 — Tổng lớn.** Dùng `IntStream.of(Integer.MAX_VALUE, 1)`. So sánh `sum()`, `asLongStream().sum()` và `summaryStatistics().getSum()`. Giải thích vì sao có kết quả khác nhau.

**Bài 5 — Số thực không hữu hạn.** Dùng `DoubleStream.of(1.0, Double.NaN, 2.0, Double.POSITIVE_INFINITY)`. Tính tổng trước và sau khi `filter(Double::isFinite)`. Nêu chính sách dữ liệu khi loại giá trị không hợp lệ.

**Bài 6 — Gom nhóm.** Với `IntStream.rangeClosed(1, 20)`, tạo `Map<String, Long>` đếm các số chẵn/lẻ bằng `boxed().collect(Collectors.groupingBy(..., counting()))`.

**Bài 7 — Tính tiền.** Với `OrderLine(quantity, unitPrice)`, tính tổng `long` bằng `mapToLong`. Thêm đầu vào đủ lớn để nhận biết vị trí tràn và lựa chọn phương án kiểm tra.

Gợi ý Bài 1:

```java
int result = IntStream.rangeClosed(1, 100)
    .filter(n -> n % 3 == 0)
    .map(n -> n * n)
    .sum();
```

Tổng các bình phương trong phạm vi này phù hợp miền `int`; với cận lớn hơn, cần đánh giá nguy cơ tràn khi `n * n` trước cả bước `sum()`.

## 16. Ghi nhớ cốt lõi

- **`IntStream`, `LongStream` và `DoubleStream`** là các primitive stream chuyên biệt, không phải `Stream<Integer>`, `Stream<Long>`, `Stream<Double>`.
- **Mô hình pipeline vẫn là nguồn → trung gian lazy → kết thúc.** Điểm khác biệt chính là kiểu phần tử và các phép toán số học/functional interface chuyên biệt.
- **`range` và `rangeClosed`** tạo dãy `int`/`long`; `of`, `Arrays.stream`, `iterate` và `generate` tạo các nguồn khác. Nguồn có thể vô hạn cần điều kiện dừng.
- **`mapToInt` / `mapToLong` / `mapToDouble`** đi từ object stream sang primitive stream; **`boxed`** quay về wrapper stream; **`mapToObj`** tạo một object stream từ giá trị nguyên thủy.
- **`sum`, `average`, `min`, `max`, `summaryStatistics` và `reduce`** cung cấp các kết quả số học đúng kiểu; `OptionalInt`, `OptionalLong` và `OptionalDouble` biểu diễn kết quả có thể vắng mặt.
- **`IntStream.sum()` có thể tràn `int`; `LongStream.sum()` có thể tràn `long`; `DoubleStream` chịu sai số số thực, NaN và Infinity.** Chọn kiểu dữ liệu theo yêu cầu miền nghiệp vụ.
- **Primitive `collect` nhận supplier, accumulator, combiner**, còn collector chuẩn như `groupingBy` thường được dùng với `Stream<T>` hoặc sau khi `boxed()`.
- **Không dùng lại Stream đã tiêu thụ**, không phụ thuộc tác động phụ trong lambda trung gian, và phải đóng nguồn I/O. Song song chỉ có ích khi nguồn, phép toán và khối lượng dữ liệu phù hợp.
- Kiến thức về primitive stream là nền để lựa chọn cách trích dữ liệu cho grouping, collector tùy chỉnh, `Spliterator`, Stream song song và các phép biến đổi nâng cao trong **JAVA_STREAM_API**.
