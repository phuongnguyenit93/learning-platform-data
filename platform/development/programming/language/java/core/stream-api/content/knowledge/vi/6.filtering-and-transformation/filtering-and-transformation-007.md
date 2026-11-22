# Chuyển giữa Stream đối tượng và Stream nguyên thủy

Trong Java Stream API, phần tử của một pipeline có thể là **đối tượng** (`Stream<T>`) hoặc **giá trị nguyên thủy** thuộc ba kiểu chuyên biệt: `IntStream`, `LongStream` và `DoubleStream`. Chuyển đúng loại Stream giúp biểu diễn phép tính rõ ràng, tận dụng các thao tác số học có sẵn và tránh boxing không cần thiết. Khi đầu ra cần đối tượng, ta chuyển lại bằng `mapToObj` hoặc `boxed`.

Bài học thuộc chương **Lọc và biến đổi phần tử** của mô-đun **JAVA_STREAM_API**. Chủ đề này kết nối trực tiếp `filter`, `map`, `reduce` và `collect` với các pipeline lazy, đồng thời tạo nền tảng để áp dụng `groupingBy`, collector tùy chỉnh, `Spliterator` và xử lý song song đúng ngữ nghĩa. Trọng tâm là lựa chọn **kiểu phần tử ở từng giai đoạn**, hiểu giới hạn của boxing, `null`, ép kiểu số và hiệu năng.

## 1. Phân biệt `Stream<T>` và ba Primitive Stream

Java có các loại Stream thường gặp sau:

| Loại | Phần tử | Ví dụ nguồn | Thao tác đặc trưng |
| --- | --- | --- | --- |
| `Stream<T>` | Tham chiếu đối tượng kiểu `T`, ví dụ `String`, `Order`, `Integer` | `orders.stream()`, `Stream.of("A", "B")` | `map`, `filter`, `collect(Collectors.groupingBy(...))` |
| `IntStream` | `int` | `IntStream.range(0, 10)`, `Arrays.stream(int[])` | `sum`, `average`, `summaryStatistics`, `mapToObj` |
| `LongStream` | `long` | `LongStream.of(1L, 2L)` | `sum`, `average`, `mapToObj` |
| `DoubleStream` | `double` | `DoubleStream.of(0.5, 1.5)` | `sum`, `average`, `mapToObj` |

Ba Primitive Stream không phải là `Stream<Integer>`, `Stream<Long>` hoặc `Stream<Double>` với tên khác. Chúng là các giao diện chuyên biệt, xử lý trực tiếp `int`, `long` và `double`, có các phép số học như `sum()` mà `Stream<T>` không cung cấp trực tiếp.

Ví dụ, với `Stream<Integer>`, không thể gọi `sum()` ngay:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.Stream;

Stream<Integer> objectNumbers = Stream.of(10, 20, 30);
IntStream primitiveNumbers = IntStream.of(10, 20, 30);

// objectNumbers.sum(); // Không biên dịch: Stream<Integer> không có sum().
int total = primitiveNumbers.sum(); // 60
```

`Stream.of(10, 20, 30)` tạo `Stream<Integer>` do các giá trị nguyên thủy được boxing thành `Integer`. `IntStream.of(10, 20, 30)` tạo nguồn `IntStream` trực tiếp. Lưu ý mỗi Stream chỉ dùng được cho **một lần tiêu thụ** bởi terminal operation; ví dụ trên gọi `sum()` một lần với `primitiveNumbers`.

### Sơ đồ chuyển đổi

```text
Stream<T>   -- mapToInt(ToIntFunction<T>) ------> IntStream
            -- mapToLong(ToLongFunction<T>) ----> LongStream
            -- mapToDouble(ToDoubleFunction<T>) -> DoubleStream

IntStream   -- mapToObj(IntFunction<R>) -------> Stream<R>
            -- boxed() ------------------------> Stream<Integer>

LongStream  -- mapToObj(LongFunction<R>) ------> Stream<R>
            -- boxed() ------------------------> Stream<Long>

DoubleStream -- mapToObj(DoubleFunction<R>) ---> Stream<R>
             -- boxed() -----------------------> Stream<Double>
```

Điều quan trọng: `mapToInt` trên `Stream<T>` không phải là ép kiểu toàn bộ đối tượng thành `int`; nó nhận **hàm trích xuất hoặc tính ra `int`** từ từng đối tượng.

## 2. Từ `Stream<T>` sang `IntStream`, `LongStream`, `DoubleStream`

Khi một luồng đối tượng chứa thông tin số, ta chọn phương thức dựa trên **kiểu nguyên thủy của kết quả**.

| Phương thức của `Stream<T>` | Functional interface được nhận | Hàm trừu tượng | Kết quả |
| --- | --- | --- | --- |
| `mapToInt` | `ToIntFunction<? super T>` | `int applyAsInt(T value)` | `IntStream` |
| `mapToLong` | `ToLongFunction<? super T>` | `long applyAsLong(T value)` | `LongStream` |
| `mapToDouble` | `ToDoubleFunction<? super T>` | `double applyAsDouble(T value)` | `DoubleStream` |

### 2.1. `mapToInt`: trích xuất giá trị `int`

Giả sử có danh sách tên sản phẩm, cần tính **tổng số ký tự UTF-16** trong các tên không trống:

```java
import java.util.List;

List<String> productNames = List.of("Bút", "Sách", "Máy tính");

int totalUtf16Units = productNames.stream()
    .filter(name -> !name.isBlank())
    .mapToInt(String::length)
    .sum();

System.out.println(totalUtf16Units); // 3 + 4 + 8 = 15
```

Các giai đoạn:

1. `stream()` tạo `Stream<String>`.
2. `filter` giữ những tên không trống, vẫn là `Stream<String>`.
3. `mapToInt(String::length)` biến từng tên thành số `int`, tạo `IntStream`.
4. `sum()` là terminal operation cộng các số nguyên.

`String.length()` đếm **UTF-16 code units**. Nếu nghiệp vụ cần đếm Unicode code points thay vì đơn vị mã UTF-16, có thể dùng `name.codePointCount(0, name.length())`; không nên gọi chung hai đại lượng đó là “số ký tự hiển thị”.

### 2.2. `mapToLong`: tổng hợp các trường `long`

Nhiều ứng dụng biểu diễn tiền bằng số nguyên đơn vị nhỏ nhất để tránh lỗi nhị phân của số thực. Ví dụ giá trị đơn hàng lưu bằng `long` (VND):

```java
record Order(String id, long amountVnd, boolean paid) {}

List<Order> orders = List.of(
    new Order("O-01", 1_500_000L, true),
    new Order("O-02",   800_000L, false),
    new Order("O-03", 2_300_000L, true)
);

long paidRevenue = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amountVnd)
    .sum();

System.out.println(paidRevenue); // 3800000
```

Ở ví dụ này, `Order::amountVnd` tương thích với `ToLongFunction<Order>`. Dùng `mapToLong` vì trường dữ liệu là `long`; dùng `mapToInt(order -> (int) order.amountVnd())` có nguy cơ mất dữ liệu khi giá trị vượt phạm vi `int`.

`long` cũng có giới hạn: `sum()` có thể **tràn số** khi tổng vượt `Long.MAX_VALUE` hoặc thấp hơn `Long.MIN_VALUE`. Nếu nghiệp vụ cần độ lớn vượt `long`, cân nhắc `BigInteger` hoặc `BigDecimal` theo mô hình tiền tệ, và phép tổng hợp trên `Stream<T>` thích hợp.

### 2.3. `mapToDouble`: tính trung bình hoặc thống kê số thực

```java
record Reading(String sensor, double temperatureC) {}

List<Reading> readings = List.of(
    new Reading("S-01", 22.0),
    new Reading("S-02", 24.5),
    new Reading("S-03", 26.0)
);

double averageC = readings.stream()
    .mapToDouble(Reading::temperatureC)
    .average()
    .orElseThrow();

System.out.println(averageC); // 24.166666666666668
```

`average()` trả về `OptionalDouble` vì luồng có thể rỗng. Chỉ dùng `orElseThrow()` khi dữ liệu bảo đảm không rỗng; với đầu vào tùy ý, xử lý trường hợp thiếu dữ liệu:

```java
double averageOrZero = readings.stream()
    .mapToDouble(Reading::temperatureC)
    .average()
    .orElse(0.0);
```

Giá trị mặc định `0.0` có thể mang ý nghĩa nghiệp vụ gây nhầm lẫn (“không có mẫu đo” không đồng nghĩa “nhiệt độ bằng 0”). Nhiều trường hợp nên giữ `OptionalDouble` để biểu diễn dữ liệu chưa có.

### 2.4. Dùng Primitive Stream cho các thống kê số học

Sau khi chuyển kiểu, ta có thể sử dụng:

```java
import java.util.IntSummaryStatistics;

List<Integer> scores = List.of(7, 9, 8, 10);

IntSummaryStatistics stats = scores.stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 34
System.out.println(stats.getMin());     // 7
System.out.println(stats.getMax());     // 10
System.out.println(stats.getAverage()); // 8.5
```

`summaryStatistics()` cho biết số lượng, tổng, nhỏ nhất, lớn nhất và trung bình trong **một lượt tiêu thụ pipeline**. Với `IntStream` và `LongStream`, `sum()` và thống kê tổng vẫn có thể tràn số nguyên. Với `DoubleStream`, kết quả còn chịu quy tắc số thực dấu phẩy động, bao gồm `NaN` và vô cực.

## 3. Từ Primitive Stream về Stream đối tượng

Khi cần chuyển số nguyên thủy thành **đối tượng tùy ý**, sử dụng `mapToObj`. Khi chỉ cần **wrapper type tương ứng**, sử dụng `boxed`.

### 3.1. `mapToObj`: tạo đối tượng theo quy tắc nghiệp vụ

Phương thức này nhận một hàm chuyển giá trị nguyên thủy thành đối tượng:

| Nguồn | Phương thức | Hàm nhận vào | Kiểu kết quả |
| --- | --- | --- | --- |
| `IntStream` | `mapToObj(IntFunction<R>)` | `int` | `Stream<R>` |
| `LongStream` | `mapToObj(LongFunction<R>)` | `long` | `Stream<R>` |
| `DoubleStream` | `mapToObj(DoubleFunction<R>)` | `double` | `Stream<R>` |

Ví dụ tạo mã ghế từ chỉ số:

```java
import java.util.List;
import java.util.stream.IntStream;

List<String> seatIds = IntStream.rangeClosed(1, 4)
    .mapToObj(i -> "A-" + i)
    .toList();

System.out.println(seatIds); // [A-1, A-2, A-3, A-4]
```

`IntStream.rangeClosed(1, 4)` phát ra bốn giá trị 1, 2, 3 và 4. `mapToObj` tạo `Stream<String>`, để `toList()` trả về `List<String>`.

Ví dụ với đối tượng domain:

```java
record Tier(int level, String label) {}

List<Tier> tiers = IntStream.rangeClosed(1, 3)
    .mapToObj(level -> new Tier(level, "Bậc " + level))
    .toList();

System.out.println(tiers);
// [Tier[level=1, label=Bậc 1], Tier[level=2, label=Bậc 2],
//  Tier[level=3, label=Bậc 3]]
```

Không cần `boxed()` trước `mapToObj` trong trường hợp trên: `mapToObj` nhận trực tiếp `int` và tạo ra đúng đối tượng kết quả.

### 3.2. `boxed()`: tạo Stream wrapper

`boxed()` chuyển từng giá trị nguyên thủy thành đối tượng wrapper tương ứng:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> ids = IntStream.rangeClosed(1, 5)
    .boxed()
    .toList();

System.out.println(ids); // [1, 2, 3, 4, 5]
```

Tương ứng:

- `IntStream.boxed()` trả về `Stream<Integer>`.
- `LongStream.boxed()` trả về `Stream<Long>`.
- `DoubleStream.boxed()` trả về `Stream<Double>`.

Nếu muốn tạo `Stream<Integer>`, `boxed()` ngắn và biểu đạt ý định rõ hơn `mapToObj(Integer::valueOf)`. Ngược lại, để tạo `Stream<String>` hoặc `Stream<OrderView>`, hãy dùng `mapToObj`.

**Lưu ý về bộ nhớ:** `boxed()` có thể dẫn đến boxing các giá trị; việc gọi `toList()` còn giữ toàn bộ kết quả trong một danh sách. Dùng hai bước này khi API hoặc đầu ra thực sự cần `List<Integer>`, thay vì boxing chỉ để tính tổng.

### 3.3. Khi cần collector của Stream đối tượng

Các collector tổng quát như `groupingBy` là API trên `Stream<T>`. Khi muốn nhóm các số nguyên theo tính chẵn lẻ, ta có thể chuyển `IntStream` về `Stream<Integer>`:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<String, Long> countsByParity = IntStream.rangeClosed(1, 10)
    .boxed()
    .collect(Collectors.groupingBy(
        number -> number % 2 == 0 ? "Chẵn" : "Lẻ",
        Collectors.counting()
    ));

System.out.println(countsByParity.get("Chẵn")); // 5
System.out.println(countsByParity.get("Lẻ"));   // 5
```

`boxed()` là hợp lý vì `groupingBy` nhận các đối tượng `Integer`. Mặc dù vậy, nếu bài toán chỉ cần đếm số chẵn, dùng `IntStream.rangeClosed(1, 10).filter(n -> n % 2 == 0).count()` sẽ trực tiếp hơn và không cần boxing.

### 3.4. Một chuỗi chuyển đổi đi và về

```java
List<String> labels = List.of("Mật ong", "Sữa", "Bánh")
    .stream()                       // Stream<String>
    .mapToInt(String::length)       // IntStream
    .filter(length -> length >= 4) // IntStream
    .mapToObj(length -> length + " UTF-16 units") // Stream<String>
    .toList();                      // List<String>

System.out.println(labels);
// [7 UTF-16 units, 4 UTF-16 units]
```

Ở ví dụ này, sau `mapToInt` ta **không còn giữ tên sản phẩm gốc**, chỉ giữ độ dài. Nếu cần cả tên lẫn độ dài, nên `map` trực tiếp thành đối tượng chứa hai trường từ `Stream<String>` ban đầu:

```java
record NameLength(String name, int utf16Units) {}

List<NameLength> details = List.of("Mật ong", "Sữa", "Bánh")
    .stream()
    .map(name -> new NameLength(name, name.length()))
    .toList();
```

Đừng chuyển sang Stream nguyên thủy nếu thao tác đó làm mất thông tin cần thiết ở bước sau.

## 4. Chuyển giữa ba Primitive Stream

Ngoài chuyển với đối tượng, Java còn hỗ trợ chuyển các dòng số nguyên thủy qua một số phương thức chuyên biệt.

### 4.1. Mở rộng kiểu số: `asLongStream` và `asDoubleStream`

`IntStream` có `asLongStream()` và `asDoubleStream()`; `LongStream` có `asDoubleStream()`.

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

long totalAsLong = IntStream.of(1, 2, 3)
    .asLongStream()
    .sum();

double totalAsDouble = LongStream.of(1L, 2L, 3L)
    .asDoubleStream()
    .sum();

System.out.println(totalAsLong);   // 6
System.out.println(totalAsDouble); // 6.0
```

Hai phương thức này phù hợp khi muốn chuyển sang kiểu có miền giá trị khác. Tuy nhiên, **mở rộng sang `double` không bảo đảm giữ chính xác mọi giá trị `long`**: `double` có 53 bit độ chính xác cho phần định trị, nên nhiều số nguyên lớn không còn biểu diễn chính xác. Với số tiền lớn hoặc định danh số nguyên, cần giữ ở kiểu `long` hoặc kiểu số có độ chính xác thích hợp.

### 4.2. `mapToLong`, `mapToDouble` và chuyển kiểu có chủ đích

Trong các Primitive Stream cũng có các hàm ánh xạ giữa kiểu số. Ví dụ:

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

LongStream longValues = IntStream.of(1, 2, 3)
    .mapToLong(n -> n * 1_000_000L);

DoubleStream ratios = LongStream.of(1L, 2L, 3L)
    .mapToDouble(n -> n / 10.0);

IntStream rounded = DoubleStream.of(1.2, 2.6, 3.1)
    .mapToInt(value -> (int) Math.round(value));

System.out.println(longValues.sum());                   // 6000000
System.out.println(java.util.Arrays.toString(ratios.toArray())); // [0.1, 0.2, 0.3]
System.out.println(java.util.Arrays.toString(rounded.toArray())); // [1, 3, 3]
```

Khi ép kiểu từ `long` xuống `int`, dữ liệu có thể vượt giới hạn. Nếu yêu cầu là **phát hiện tràn thay vì cắt dữ liệu**, dùng `Math.toIntExact`:

```java
import java.util.stream.LongStream;

int[] safeValues = LongStream.of(10L, 20L, 30L)
    .mapToInt(Math::toIntExact)
    .toArray();

System.out.println(java.util.Arrays.toString(safeValues)); // [10, 20, 30]

// Nếu có giá trị ngoài phạm vi int, Math.toIntExact ném ArithmeticException.
```

Chuyển từ `double` sang kiểu nguyên còn phụ thuộc quy tắc làm tròn và xử lý `NaN`, vô cực. Ví dụ `(int) 2.9` cho `2` (cắt phần thập phân về phía 0), còn `Math.round(2.9)` cho `3L` trước khi ép về `int`. Khi giá trị có thể ngoài phạm vi `int`, nên xác thực phạm vi trước khi chuyển.

### Bảng định hướng nhanh

| Đang có | Muốn nhận | Phương thức điển hình |
| --- | --- | --- |
| `IntStream` | `LongStream` | `asLongStream()`, hoặc `mapToLong(...)` để biến đổi giá trị |
| `IntStream` | `DoubleStream` | `asDoubleStream()`, hoặc `mapToDouble(...)` |
| `LongStream` | `DoubleStream` | `asDoubleStream()`, hoặc `mapToDouble(...)` |
| `LongStream` | `IntStream` | `mapToInt(...)`, cân nhắc `Math.toIntExact` |
| `DoubleStream` | `IntStream` / `LongStream` | `mapToInt(...)` / `mapToLong(...)` với quy tắc chuyển số rõ ràng |
| Một Primitive Stream | `Stream<R>` bất kỳ | `mapToObj(...)` |
| Một Primitive Stream | `Stream<Wrapper>` tương ứng | `boxed()` |

## 5. Lưu ý `null` khi unboxing

Với một `Stream<Integer>` có thể chứa `null`, gọi `Integer::intValue` sẽ gây `NullPointerException` khi gặp phần tử rỗng. Không được mặc định mọi `List<Integer>` đều không chứa `null`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<Integer> values = Arrays.asList(10, null, 20);

int sumNonNull = values.stream()
    .filter(Objects::nonNull)
    .mapToInt(Integer::intValue)
    .sum();

System.out.println(sumNonNull); // 30
```

Ở đây, cách xử lý `null` là **bỏ qua**. Đó là một quyết định về nghiệp vụ, không phải quy tắc bắt buộc. Nếu `null` biểu thị dữ liệu lỗi, có thể chủ động ném ngoại lệ hoặc xử lý tại lớp xác thực đầu vào. Nếu `null` thật sự có nghĩa bằng `0`, có thể ánh xạ nó thành `0`:

```java
int sumNullAsZero = values.stream()
    .mapToInt(value -> value == null ? 0 : value)
    .sum();
```

Ba cách này dẫn đến ý nghĩa khác nhau khi tính `count()`, `average()` hoặc thống kê số mẫu. Ví dụ “bỏ qua mẫu bị thiếu” khác “coi mẫu thiếu là 0” khi tính trung bình.

Với `Stream<Long>` và `Stream<Double>`, có thể dùng `Long::longValue` và `Double::doubleValue` tương ứng, cùng yêu cầu xem xét `null` trước khi unboxing.

## 6. `map`, `mapToX` và `flatMapToX` khác nhau như thế nào?

Không phải mọi phép biến đổi đều giữ một phần tử đầu vào thành đúng một phần tử đầu ra. Cần phân biệt:

| Phương thức | Nhận đầu vào | Kết quả mỗi đầu vào | Kiểu luồng sau thao tác |
| --- | --- | --- | --- |
| `map(Function<T, R>)` | `T` | Một `R` | `Stream<R>` |
| `mapToInt(ToIntFunction<T>)` | `T` | Một `int` | `IntStream` |
| `mapToLong(ToLongFunction<T>)` | `T` | Một `long` | `LongStream` |
| `mapToDouble(ToDoubleFunction<T>)` | `T` | Một `double` | `DoubleStream` |
| `flatMapToInt(Function<T, IntStream>)` | `T` | 0 đến nhiều `int` | `IntStream` |
| `flatMapToLong(Function<T, LongStream>)` | `T` | 0 đến nhiều `long` | `LongStream` |
| `flatMapToDouble(Function<T, DoubleStream>)` | `T` | 0 đến nhiều `double` | `DoubleStream` |

Ví dụ mỗi chuỗi chứa **nhiều code point Unicode**, vì vậy ta dùng `flatMapToInt` thay cho `mapToInt`:

```java
import java.util.List;

List<String> tokens = List.of("AB", "😀");

int[] codePoints = tokens.stream()
    .flatMapToInt(String::codePoints)
    .toArray();

System.out.println(java.util.Arrays.toString(codePoints));
// [65, 66, 128512]
```

`String::codePoints` trả về `IntStream` từ từng chuỗi; `flatMapToInt` ghép các luồng con thành một `IntStream` phẳng. Nếu viết `tokens.stream().map(String::codePoints)`, kết quả là `Stream<IntStream>`, tức **Stream chứa các đối tượng Stream con**, chưa được làm phẳng. Nếu viết `mapToInt(String::length)`, ta chỉ có độ dài từng chuỗi, không nhận các code point bên trong.

Theo hợp đồng của `flatMapToInt`, các Stream con được đóng sau khi nội dung của chúng được đưa vào luồng kết quả. Dù vậy, với nguồn I/O hoặc tài nguyên đặc biệt, cần xem xét cách quản lý vòng đời và lỗi một cách rõ ràng.

## 7. Ví dụ hoàn chỉnh: báo cáo doanh thu từ danh sách đơn hàng

Ví dụ sau dùng **Java 17+**, vì sử dụng `record` và `Stream.toList()`. Nó minh họa ba tình huống: tính tổng trên `LongStream`, tạo nhãn đầu ra từ `mapToObj` và tổng hợp theo khóa với collector của `Stream<Order>`.

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ObjectPrimitiveStreamDemo {
    record Order(String id, String region, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "Bắc", 1_500_000L, true),
            new Order("O-02", "Nam",   700_000L, true),
            new Order("O-03", "Bắc", 2_000_000L, false),
            new Order("O-04", "Bắc",   300_000L, true)
        );

        // 1. Stream<Order> -> LongStream -> long.
        long paidRevenue = orders.stream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .sum();

        // 2. Stream<Order> -> LongStream -> Stream<String> -> List<String>.
        List<String> paidAmountLabels = orders.stream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .mapToObj(amount -> "Đã thanh toán: " + amount + " VND")
            .toList();

        // 3. Giữ Order để nhóm theo region và cộng amountVnd.
        Map<String, Long> revenueByRegion = orders.stream()
            .filter(Order::paid)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.summingLong(Order::amountVnd)
            ));

        System.out.println(paidRevenue);
        System.out.println(paidAmountLabels);
        System.out.println(revenueByRegion.get("Bắc"));
        System.out.println(revenueByRegion.get("Nam"));
    }
}
```

Kết quả:

```text
2500000
[Đã thanh toán: 1500000 VND, Đã thanh toán: 700000 VND, Đã thanh toán: 300000 VND]
1800000
700000
```

Phân tích:

- Ở bước tính tổng, chỉ cần trường `amountVnd` nên `mapToLong` là cách diễn đạt trực tiếp.
- Ở bước tạo nhãn, `mapToObj` chuyển mỗi giá trị `long` thành một `String`. Các trường `id` và `region` không còn khả dụng sau `mapToLong`.
- Ở bước nhóm doanh thu, cần giữ `region` cùng `amountVnd`; nếu chuyển sang `LongStream` từ đầu, pipeline sẽ mất khóa để nhóm. `Collectors.summingLong` là lựa chọn phù hợp trên `Stream<Order>`.
- Mỗi phép tính bắt đầu bằng `orders.stream()` mới, vì Stream chỉ được tiêu thụ một lần.

Lưu ý `Collectors.summingLong` cũng dùng phép cộng `long` và có nguy cơ tràn số tương tự `LongStream.sum()` khi dữ liệu vượt phạm vi.

## 8. Tính lazy, dữ liệu có trạng thái và xử lý song song

`mapToInt`, `mapToLong`, `mapToDouble`, `mapToObj`, `boxed` và `flatMapToInt` là các **thao tác trung gian**. Chúng tạo pipeline mới và thông thường chưa xử lý phần tử ngay; terminal operation mới kích hoạt việc duyệt:

```java
List<String> names = List.of("A", "BBB", "CC");

var lengths = names.stream()
    .mapToInt(String::length); // Chưa yêu cầu tính toán kết quả.

int sum = lengths.sum();       // 1 + 3 + 2 = 6

// lengths.count();            // Sai: Stream đã được tiêu thụ.
```

Trong các hàm ánh xạ, nên tránh thay đổi nguồn đang được duyệt hoặc cập nhật trạng thái chia sẻ. Ví dụ không an toàn khi chạy song song:

```java
// Không nên dùng, đặc biệt nguy hiểm nếu thêm parallelStream().
long[] total = {0L};

orders.stream().mapToLong(order -> {
    total[0] += order.amountVnd(); // Tác dụng phụ bên ngoài pipeline.
    return order.amountVnd();
}).sum();

// Viết trực tiếp theo kết quả cần:
long paidTotal = orders.stream()
    .filter(Order::paid)
    .mapToLong(Order::amountVnd)
    .sum();
```

Trong ví dụ đầu, `total[0]` biến đổi ngoài pipeline và phép cộng còn có thể bị đếm hai lần nếu sử dụng cả biến này lẫn `sum()`. Với Stream song song, cập nhật chung không đồng bộ có thể gây race condition và kết quả sai.

`parallelStream()` không tự động nhanh hơn Stream tuần tự. Chia dữ liệu, boxing trong các giai đoạn `boxed()`, ghép kết quả, thứ tự và chi phí collector đều ảnh hưởng tốc độ. Với tác vụ số học độc lập trên dữ liệu đủ lớn, Primitive Stream có thể là lựa chọn tốt để **cân nhắc** song song; cần kiểm chứng bằng phép đo thực tế.

Đối với các thao tác có trạng thái như `distinct`, `sorted`, các phép gom nhóm hoặc nguồn dữ liệu có ràng buộc thứ tự, chi phí bộ nhớ và phối hợp có thể tăng. `Spliterator` ảnh hưởng đến khả năng chia nguồn cho song song, nhưng thường không cần tự viết `Spliterator` chỉ để chuyển giữa `Stream<T>` và Primitive Stream.

## 9. Hiệu năng: khi nào boxing đáng chú ý?

Các wrapper như `Integer`, `Long`, `Double` là **đối tượng**, còn `int`, `long`, `double` là giá trị nguyên thủy. Boxing/unboxing có thể dẫn tới chi phí chuyển đổi và cấp phát; khả năng tối ưu thực tế còn phụ thuộc JVM và ngữ cảnh.

So sánh hai cách tính tổng:

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

// Phương án A: reduce trên Stream<Integer>.
int sumBoxed = numbers.stream()
    .reduce(0, Integer::sum);

// Phương án B: dùng IntStream chuyên biệt.
int sumPrimitive = numbers.stream()
    .mapToInt(Integer::intValue)
    .sum();

System.out.println(sumBoxed == sumPrimitive); // true
```

Ở phương án A, phép `reduce` thực hiện trên `Integer`; phương án B chỉ dùng `Integer` ở nguồn, sau đó chuyển sang `int` và tính toán với `IntStream`. Phương án B thường diễn đạt yêu cầu số học rõ hơn. Tuy nhiên, không thể kết luận về tỷ lệ nhanh/chậm chỉ từ hai đoạn mã này: tối ưu JIT, kích thước nguồn và chi phí chung của pipeline phải được đo.

Khi so sánh, nên:

1. Đo trên dữ liệu đại diện và đường chạy thực tế.
2. Dùng công cụ benchmark phù hợp như **JMH**, có warm-up.
3. Xác minh hai cách tính trả về cùng kết quả và cùng quy tắc overflow/`null`.
4. Kiểm tra bộ nhớ, boxing và độ ổn định trước khi đổi code vì hiệu năng.

Primitive Stream không giải quyết mọi vấn đề hiệu năng: tạo `List<Integer>` đầu ra vẫn cần lưu các đối tượng; chuyển số qua `double` có thể mất độ chính xác; phép giảm với số nguyên vẫn có thể tràn.

## 10. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Gọi `sum()` trực tiếp trên `Stream<Integer>` | Không biên dịch | Chuyển bằng `mapToInt(Integer::intValue)` rồi `sum()`. |
| Gọi `mapToInt` nhưng vẫn dùng các phép dành riêng cho `Stream<T>` như `groupingBy` | Không có `collect(Collector)` trên `IntStream` | Giữ đối tượng hoặc dùng `boxed()`/`mapToObj` nếu thực sự cần collector tổng quát. |
| Dùng `boxed().map(...)` khi `mapToObj(...)` đã đủ | Boxing không cần thiết | Dùng `mapToObj` để tạo trực tiếp đối tượng kết quả. |
| Chuyển `long` sang `int` bằng ép kiểu âm thầm | Giá trị lớn có thể bị cắt | Dùng `Math.toIntExact` khi cần phát hiện overflow. |
| Coi `asDoubleStream` là chuyển đổi nguyên vẹn mọi số `long` | Mất chính xác số nguyên lớn | Giữ `long`/`BigInteger` hoặc dùng số học độ chính xác phù hợp. |
| Unboxing phần tử `null` | `NullPointerException` | Xác định quy tắc xử lý `null` trước `mapToInt`/`mapToLong`. |
| Chuyển sang Primitive Stream quá sớm | Mất dữ liệu ngữ cảnh cần dùng ở bước sau | Giữ `Stream<T>` khi vẫn cần nhiều trường của đối tượng. |
| Dùng một Stream cho nhiều terminal operation | `IllegalStateException` | Tạo nguồn Stream mới cho từng phép tính. |
| Dùng `parallel()` và sửa biến/collection bên ngoài trong `mapToX` | Race condition, sai kết quả | Dùng giảm/tổng hợp phù hợp, tránh trạng thái chia sẻ. |
| Mặc định Primitive Stream luôn nhanh hơn mọi vòng lặp | Tối ưu dựa trên suy đoán | Đo bằng dữ liệu và workload đại diện. |

## 11. Bài tập thực hành

### Bài 1: Điểm số sinh viên

Cho `List<Student>`, mỗi `Student` có `name` và `score` kiểu `int`. Lọc sinh viên đạt ít nhất 5 điểm, tính tổng điểm, điểm trung bình và điểm cao nhất bằng `mapToInt`. Trả lời: khi danh sách rỗng, `average()` và `max()` xử lý khác `sum()` như thế nào?

### Bài 2: Tạo danh sách nhãn

Dùng `IntStream.rangeClosed(1, 12)` tạo `List<String>` chứa các giá trị `"Tháng 1"` đến `"Tháng 12"`. Giải thích tại sao nên dùng `mapToObj` và không cần `boxed()`.

### Bài 3: Nhóm số theo tính chẵn lẻ

Dùng `IntStream.rangeClosed(1, 20)` kết hợp `boxed()` và `Collectors.groupingBy` để tạo `Map<Boolean, List<Integer>>`, trong đó khóa `true` chứa số chẵn. Sau đó, chỉ đếm số chẵn bằng `IntStream.filter(...).count()` và so sánh bộ nhớ đầu ra của hai mục tiêu.

### Bài 4: Tổng tiền theo khu vực

Cho danh sách đơn hàng có `region` và `amountVnd`. Tạo báo cáo tổng tiền toàn bộ đơn bằng `mapToLong`, rồi tạo `Map<String, Long>` theo khu vực với `Collectors.groupingBy` và `Collectors.summingLong`. Giải thích tại sao lần thứ hai cần giữ đối tượng đơn hàng.

### Bài 5: Chuyển kiểu an toàn

Cho `LongStream` chứa `1L`, `2_147_483_647L` và `2_147_483_648L`. Thử `mapToInt(Math::toIntExact)` rồi giải thích ngoại lệ xuất hiện ở phần tử nào. Sau đó thử chuyển cùng luồng sang `DoubleStream` và nghiên cứu điều kiện giữ chính xác số nguyên.

### Bài 6: Xử lý `null`

Cho `List<Integer>` chứa `[10, null, 20]`. So sánh trung bình tính theo hai chính sách: **bỏ qua `null`** và **coi `null` là 0**. Giải thích vì sao kết quả khác nhau và chọn cách phù hợp theo ý nghĩa dữ liệu.

## 12. Tự kiểm tra kiến thức

- `Stream<Integer>` và `IntStream` khác nhau về kiểu phần tử và API tổng hợp ra sao?
- Khi nào dùng `mapToLong` thay cho `mapToInt`?
- `mapToObj` khác `boxed` ở kiểu kết quả và mục đích sử dụng thế nào?
- Vì sao `Collectors.groupingBy` thường được gọi trên `Stream<T>`, không gọi trực tiếp trên `IntStream`?
- `flatMapToInt` giải quyết vấn đề nào mà `mapToInt` không giải quyết?
- Điều gì xảy ra nếu unboxing một `Integer` bằng `null`?
- Vì sao việc chuyển `long` sang `double` có thể làm mất chính xác dù là chuyển kiểu mở rộng?
- Tại sao việc chuyển sang Primitive Stream quá sớm có thể khiến ta không còn đủ dữ liệu để nhóm theo khóa?

**Ghi nhớ:** Khi cần **tính toán trên số**, hãy dùng `mapToInt`, `mapToLong` hoặc `mapToDouble` để chuyển `Stream<T>` sang Primitive Stream. Khi cần **tạo đối tượng kết quả**, dùng `mapToObj`; khi cần **wrapper tương ứng**, dùng `boxed`. Lựa chọn đúng thời điểm chuyển kiểu giúp pipeline rõ ràng, giữ đúng dữ liệu nghiệp vụ và tránh những lỗi về `null`, overflow, mất chính xác và trạng thái chia sẻ.
