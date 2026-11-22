# Đọc chữ ký API và tài liệu `java.util.stream`

## 1. Mục tiêu và cách tiếp cận

Java Stream API cho phép mô tả việc xử lý dữ liệu theo kiểu khai báo: tạo một luồng phần tử từ nguồn, nối các phép biến đổi thành **pipeline**, rồi kích hoạt xử lý bằng một phép toán kết thúc. Để dùng đúng API, cần biết cách đọc **chữ ký phương thức** (method signature) và các cam kết trong **Javadoc**, thay vì chỉ ghi nhớ tên `filter`, `map` hay `collect`.

Sau bài này, bạn có thể:

- Tìm đúng lớp, interface và phiên bản Javadoc cho `java.util.stream`.
- Đọc kiểu trả về, tham số, tham số kiểu (`<T>`, `<R>`) và wildcard (`? super`, `? extends`) trong chữ ký API.
- Nhận diện phép toán trung gian, kết thúc, lười thực thi, rút ngắn xử lý và các yêu cầu về thứ tự, trạng thái, tài nguyên.
- Tra cứu và lựa chọn `Stream`, `IntStream`/`LongStream`/`DoubleStream`, `Collectors`, `Collector`, `Spliterator`, `Gatherer` khi giải quyết bài toán thực tế.
- Đánh giá các điều kiện để pipeline đúng và có hiệu năng phù hợp trước khi dùng `parallel()`.

Ví dụ khởi đầu:

```java
List<String> names = List.of("An", "Bình", "Anh", "Chi");

List<String> result = names.stream()  // Nguồn: Stream<String>
    .filter(name -> name.startsWith("A")) // Trung gian: Stream<String>
    .map(String::toUpperCase)               // Trung gian: Stream<String>
    .toList();                              // Kết thúc: List<String>

System.out.println(result); // [AN, ANH]
```

`filter` và `map` tạo mô tả cho pipeline; `toList()` mới kích hoạt việc duyệt dữ liệu. `Stream` **không phải** một collection lưu sẵn các phần tử đã biến đổi. Nó là giao diện mô tả các phép tính trên một nguồn dữ liệu, thường chỉ được tiêu thụ một lần.

## 2. Tìm và đọc tài liệu chính thức

### 2.1. Bản đồ API cần tra cứu

Mở Javadoc của đúng phiên bản JDK đang sử dụng và đi từ trang **Package `java.util.stream`** đến các kiểu liên quan:

| Tài liệu | Dùng khi nào? | Điều cần chú ý |
| --- | --- | --- |
| [`java.util.stream` — package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html) | Hiểu tổng quan pipeline và danh sách kiểu | Các nguyên tắc non-interference, stateless behavior, side effects, reduction, parallelism |
| [`Stream<T>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html) | Duyệt phương thức xử lý đối tượng | `filter`, `map`, `flatMap`, `reduce`, `collect`, `toList`, `findFirst` |
| [`BaseStream<T, S>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/BaseStream.html) | Điều khiển chế độ và vòng đời luồng | `sequential`, `parallel`, `unordered`, `onClose`, `close` |
| [`IntStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/IntStream.html), `LongStream`, `DoubleStream` | Tính toán số học tránh boxing | `sum`, `average`, `summaryStatistics`, `boxed` |
| [`Collectors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html) | Kết hợp phần tử thành collection, map, nhóm, thống kê | Các factory tạo `Collector`, nhất là downstream collector |
| [`Collector<T,A,R>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html) | Hiểu cách tích lũy và collector tùy chỉnh | `supplier`, `accumulator`, `combiner`, `finisher`, `characteristics` |
| [`Spliterator<T>`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Spliterator.html) | Hiểu nguồn, thứ tự và phân chia công việc | `tryAdvance`, `trySplit`, `estimateSize`, `characteristics` |
| [`Gatherer<T,A,R>`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html), [`Gatherers`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html) | Phép biến đổi trung gian có trạng thái, tạo cửa sổ, quét dãy | API chính thức từ **JDK 24**; không có trong JDK 21 |

**Ghi nhớ ranh giới package:** `Collection.stream()` là phương thức của `java.util.Collection`; `Files.lines()` thuộc `java.nio.file.Files`; `Predicate`, `Function`, `BiFunction`, `Consumer` thuộc `java.util.function`; `Optional` thuộc `java.util`. Chúng thường xuất hiện trong pipeline dù không được khai báo ở package `java.util.stream`.

### 2.2. Đọc gì trên một trang Javadoc?

Một trang API thường có phần mô tả chung, danh sách phương thức (**Method Summary**) và phần mô tả từng phương thức (**Method Details**). Khi chọn một phương thức, đọc theo trình tự:

1. **Tên, kiểu trả về và tham số:** phương thức nhận gì và tạo kết quả loại nào?
2. **Type Parameters / Parameters / Returns:** các ký hiệu generic và ý nghĩa từng tham số.
3. **Mô tả ngữ nghĩa:** phương thức là intermediate hay terminal, có short-circuit không, thứ tự phần tử có được đảm bảo không?
4. **API Note / Implementation Requirements / Implementation Note:** hướng dẫn sử dụng và các cam kết triển khai nếu có; đừng nhầm một ví dụ triển khai với bảo đảm cho mọi JDK.
5. **Throws / Since / See Also:** ngoại lệ, phiên bản được giới thiệu, các API liên quan.
6. **Mô tả chung của interface và package:** nhiều quy tắc quan trọng như không can thiệp nguồn, tính không trạng thái hoặc giới hạn của side effect được mô tả ở đây, chứ không lặp lại dưới mỗi phương thức.

Ví dụ, khi gặp `Stream.toList()`, phải đọc cả việc nó là **terminal operation**, danh sách kết quả **không thể sửa đổi**, và mục **Since: 16**. Đừng suy từ tên `toList()` rằng kết quả là `ArrayList` có thể thêm phần tử.

**Chọn đúng phiên bản:** Javadoc của JDK 21 không mô tả `Stream.gather` vì phương thức này chỉ trở thành API chính thức ở JDK 24. Khi sao chép ví dụ, kiểm tra JDK của dự án và dòng `Since` của từng API; tài liệu JDK mới có thể chứa phương thức mà dự án chưa biên dịch được.

## 3. Giải mã chữ ký generic

Hãy xét chữ ký rút từ `Stream<T>`:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

Đọc từ ngoài vào trong:

- `T`: kiểu phần tử **đầu vào** của `Stream<T>` hiện tại; ví dụ `Stream<String>` thì `T` là `String`.
- `<R>` trước kiểu trả về: phương thức khai báo một **tham số kiểu mới** tên `R`. Trình biên dịch thường suy luận nó từ `mapper`.
- `Stream<R>`: kết quả vẫn là một stream, nhưng phần tử có kiểu `R`.
- `Function<X,Y>`: hàm nhận một giá trị kiểu `X`, trả về giá trị kiểu `Y`.
- `? super T`: mapper có thể nhận `T` **hoặc một kiểu cha của `T`** (tính linh hoạt phía đầu vào).
- `? extends R`: mapper có thể trả về `R` **hoặc một kiểu con của `R`** (tính linh hoạt phía đầu ra).

Suy ra, `map` biến đổi **mỗi phần tử** bằng một hàm; nó không tự loại bỏ phần tử hoặc thực thi pipeline ngay lập tức.

```java
Stream<String> source = Stream.of("java", "stream");
Stream<Integer> lengths = source.map(String::length);
// T = String; R = Integer; mapper: String -> Integer
List<Integer> values = lengths.toList(); // [4, 6]
```

Các ký hiệu xuất hiện thường xuyên:

| Ký hiệu | Cách đọc | Ví dụ ý nghĩa |
| --- | --- | --- |
| `T` | Kiểu phần tử của stream | `Stream<Order>` có `T = Order` |
| `<R>` | Kiểu mới do phương thức khai báo | `map` chuyển `Order` thành `String` |
| `<K, V>` | Kiểu khóa và giá trị, thường khi gom vào map | `Map<String, Long>` |
| `? super T` | Cho phép `T` hoặc kiểu cha ở phía nhận dữ liệu | `Predicate<Object>` có thể kiểm tra `String` |
| `? extends R` | Cho phép `R` hoặc kiểu con ở phía tạo dữ liệu | Mapper trả `Integer` trong ngữ cảnh nhận `Number` |
| `A` trong `Collector<T,A,R>` | Kiểu vùng chứa tích lũy trung gian | Có thể là một đối tượng nội bộ không lộ ra ngoài |
| `Optional<T>` | Có thể có hoặc không có kết quả | `findFirst()` trên stream rỗng trả `Optional.empty()` |

**Phân biệt hai vị trí generic:** ở `Stream<T>`, `T` thuộc interface; ở `<R> Stream<R> map(...)`, `R` được khai báo riêng cho lần gọi phương thức. Đọc cả hai mới biết dữ liệu đổi kiểu như thế nào.

## 4. Đọc hợp đồng của các phép toán chính

### 4.1. Phép toán trung gian (intermediate operations)

Các phương thức này trả về một stream mới và thường chỉ thực hiện khi có terminal operation:

| Chữ ký rút gọn từ `Stream<T>` | Cách hiểu |
| --- | --- |
| `Stream<T> filter(Predicate<? super T> predicate)` | Giữ phần tử mà predicate cho kết quả `true` |
| `<R> Stream<R> map(Function<? super T, ? extends R> mapper)` | Biến đổi một phần tử thành một giá trị |
| `<R> Stream<R> flatMap(Function<? super T, ? extends Stream<? extends R>> mapper)` | Mỗi phần tử sinh một stream con, rồi trải phẳng thành stream kết quả |
| `<R> Stream<R> mapMulti(BiConsumer<? super T, ? super Consumer<R>> mapper)` | Mỗi phần tử có thể phát ra 0, 1 hoặc nhiều giá trị qua `Consumer<R>`; có từ JDK 16 |
| `Stream<T> distinct()` | Loại phần tử trùng theo `equals` |
| `Stream<T> sorted(Comparator<? super T> comparator)` | Sắp xếp bằng comparator; là phép toán cần lưu trạng thái |
| `Stream<T> limit(long maxSize)` | Lấy tối đa `maxSize` phần tử; có thể rút ngắn pipeline |
| `Stream<T> takeWhile(Predicate<? super T> predicate)` | Với stream có thứ tự, lấy tiền tố liên tiếp thỏa điều kiện; có từ JDK 9 |
| `Stream<T> peek(Consumer<? super T> action)` | Quan sát phần tử trong lúc duyệt, thường để chẩn đoán; không đảm bảo action chạy cho mọi phần tử |

Hai ví dụ dễ nhầm lẫn:

```java
List<List<String>> groups = List.of(
    List.of("Java", "Kotlin"),
    List.of("Python")
);

List<String> wrongShape = groups.stream()
    .map(group -> group.toString())
    .toList(); // ["[Java, Kotlin]", "[Python]"]

List<String> flattened = groups.stream()
    .flatMap(List::stream)
    .toList(); // ["Java", "Kotlin", "Python"]
```

`map` tạo **một kết quả cho một đầu vào**, còn `flatMap` cho phép mỗi đầu vào tạo **một số lượng tùy ý** kết quả qua stream con. Khi dùng `flatMap`, các stream con do mapper tạo ra được đóng sau khi nội dung của chúng đã được sử dụng.

Lưu ý **stateful** và **short-circuit** là hai đặc tính khác nhau: `sorted` cần xem xét nhiều phần tử trước khi xuất kết quả; `limit` có thể dừng sớm. Với nguồn có thứ tự, `distinct`, `sorted` hay `limit` có thể làm tăng chi phí khi chạy song song.

### 4.2. Phép toán kết thúc (terminal operations)

| Chữ ký rút gọn từ `Stream<T>` | Kiểu kết quả và ngữ nghĩa |
| --- | --- |
| `long count()` | Đếm phần tử; việc triển khai có thể tối ưu mà không duyệt từng phần tử |
| `boolean anyMatch(Predicate<? super T> predicate)` | Có ít nhất một phần tử thỏa; short-circuit |
| `boolean allMatch(Predicate<? super T> predicate)` | Tất cả phần tử thỏa; short-circuit |
| `Optional<T> findFirst()` | Phần tử đầu tiên nếu có, theo encounter order |
| `Optional<T> findAny()` | Một phần tử bất kỳ nếu có; phù hợp khi không cần giữ thứ tự |
| `Optional<T> reduce(BinaryOperator<T> accumulator)` | Gộp phần tử thành một giá trị; có thể rỗng |
| `T reduce(T identity, BinaryOperator<T> accumulator)` | Gộp với giá trị khởi đầu (`identity`) |
| `<R, A> R collect(Collector<? super T, A, R> collector)` | Thu thập bằng chiến lược tích lũy được đóng gói trong `Collector` |
| `List<T> toList()` | Tạo danh sách không thể sửa đổi; từ JDK 16 |
| `void forEach(Consumer<? super T> action)` | Thực hiện hành động; không đảm bảo encounter order trong chế độ song song |

`findFirst`, `findAny` và `reduce` không có identity trả `Optional`, vì kết quả có thể không tồn tại. Chẳng hạn:

```java
String first = Stream.of("A", "B")
    .filter(s -> s.startsWith("Z"))
    .findFirst()
    .orElse("Không tìm thấy");

System.out.println(first); // Không tìm thấy
```

Không gọi `get()` trên `Optional` khi chưa kiểm tra sự hiện diện. Với `IntStream`, `LongStream`, `DoubleStream`, các phương thức như `findFirst()` trả về `OptionalInt`, `OptionalLong`, `OptionalDouble` tương ứng.

### 4.3. Đọc `reduce` trước khi quyết định dùng

Ba overload của `reduce` phục vụ các bài toán khác nhau:

```java
Optional<Integer> optionalSum = Stream.of(1, 2, 3)
    .reduce(Integer::sum); // Optional[6]

int sum = Stream.of(1, 2, 3)
    .reduce(0, Integer::sum); // 6

int totalLength = Stream.of("A", "BB", "CCC")
    .reduce(0, (sumSoFar, s) -> sumSoFar + s.length(), Integer::sum); // 6
```

Trong overload thứ ba, `U` (ở ví dụ là `Integer`) có thể khác `T` (ở ví dụ là `String`). `identity` phải là giá trị trung hòa; `combiner` phải tương thích với `accumulator`; phép gộp phải **kết hợp được** (*associative*) để hoạt động chính xác khi luồng được chia nhóm hoặc xử lý song song. Không dùng `reduce` để sửa đổi một đối tượng tích lũy mutable như `ArrayList`: công việc đó dành cho `collect`.

Đối với tổng, trung bình hoặc thống kê số, hãy ưu tiên các phép toán chuyên dụng của primitive stream khi chúng diễn đạt bài toán rõ ràng hơn:

```java
long sum = Stream.of("10", "20", "30")
    .mapToLong(Long::parseLong)
    .sum(); // 60
```

## 5. Đọc chữ ký `collect`, `Collectors` và `Collector`

Một phương thức quan trọng là:

```java
<R, A> R collect(Collector<? super T, A, R> collector)
```

`T` là kiểu phần tử đầu vào; `A` là kiểu bộ tích lũy nội bộ; `R` là kiểu kết quả cuối. `Collectors` cung cấp các *factory methods* để tạo `Collector` phù hợp, ví dụ `toList()`, `toSet()`, `joining()`, `counting()`, `mapping()`, `groupingBy()`, `partitioningBy()`, `summingLong()` và `toMap()`.

Ví dụ đọc chữ ký quá tải của `groupingBy`:

```java
<T, K, A, D> Collector<T, ?, Map<K, D>> groupingBy(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
)
```

Ta đọc được: `classifier` tạo khóa `K` cho mỗi phần tử `T`, `downstream` xử lý các phần tử trong từng nhóm để tạo giá trị `D`, và kết quả chung là `Map<K,D>`. Wildcard `?` ở vị trí bộ tích lũy trong `Collector<T, ?, Map<K,D>>` cho biết người dùng không cần biết kiểu tích lũy nội bộ.

Ví dụ hoàn chỉnh, chạy trên **JDK 17 trở lên**:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class StreamApiReading {
    record Order(String region, String product, long amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("HN", "Sach", 120),
            new Order("HCM", "But", 50),
            new Order("HN", "Man hinh", 300),
            new Order("HCM", "Ban", 180)
        );

        Map<String, Long> revenueByRegion = orders.stream()
            .filter(order -> order.amount() >= 100)
            .collect(Collectors.groupingBy(
                Order::region,
                Collectors.summingLong(Order::amount)
            ));

        System.out.println(revenueByRegion.get("HN"));  // 420
        System.out.println(revenueByRegion.get("HCM")); // 180

        long allRevenue = orders.stream()
            .mapToLong(Order::amount)
            .sum();
        System.out.println(allRevenue); // 650

        List<String> productNames = orders.stream()
            .map(Order::product)
            .distinct()
            .toList();
        System.out.println(productNames); // [Sach, But, Man hinh, Ban]
    }
}
```

Phân tích các kiểu theo từng đoạn:

| Biểu thức | Kiểu suy ra | Lý do |
| --- | --- | --- |
| `orders.stream()` | `Stream<Order>` | Nguồn chứa `Order` |
| `.filter(...)` | `Stream<Order>` | Không đổi kiểu phần tử |
| `Order::region` | `Function<Order,String>` tương thích | Chọn khóa nhóm là `String` |
| `Collectors.summingLong(Order::amount)` | Collector tạo `Long` | Gom tổng `long` của mỗi nhóm |
| `.collect(groupingBy(...))` | `Map<String,Long>` | Kết quả có khóa vùng, giá trị tổng |
| `.mapToLong(Order::amount)` | `LongStream` | Dùng stream kiểu nguyên thủy |

**Hai lưu ý khi đọc tài liệu collector:**

- `Stream.toList()` bảo đảm kết quả không thể sửa đổi; `Collectors.toList()` **không cam kết** loại cụ thể, khả năng sửa đổi, khả năng tuần tự hóa hay an toàn luồng. Nếu muốn danh sách có thể chỉnh sửa một cách tường minh, dùng `collect(Collectors.toCollection(ArrayList::new))` cùng import `java.util.ArrayList`.
- `groupingBy` mặc định không bảo đảm loại `Map` hay thứ tự khóa. Nếu thứ tự cần thiết, đọc overload nhận `mapFactory`, hoặc sắp xếp dữ liệu đầu ra một cách chủ đích. Với khóa trùng, `Collectors.toMap(keyMapper, valueMapper)` có thể ném ngoại lệ: hãy tra overload nhận `mergeFunction`.

### 5.1. Khi nào cần `Collector` tùy chỉnh?

`Collector<T,A,R>` mô tả năm thành phần: `supplier` tạo bộ tích lũy, `accumulator` đưa phần tử vào đó, `combiner` gộp hai bộ tích lũy, `finisher` tạo kết quả và `characteristics` mô tả đặc tính. API có `Collector.of(...)` để tạo collector thủ công.

Khi đọc `Collector.Characteristics`, phân biệt:

- `CONCURRENT`: bộ tích lũy có thể được nhiều luồng cùng cập nhật theo hợp đồng collector.
- `UNORDERED`: kết quả không phụ thuộc encounter order.
- `IDENTITY_FINISH`: có thể dùng trực tiếp bộ tích lũy làm kết quả, không cần bước chuyển kiểu thực sự.

Không tự gắn các characteristics nếu bộ tích lũy hoặc thuật toán không đáp ứng điều kiện. Trong nhiều bài toán, kết hợp các collector sẵn có (`mapping`, `filtering`, `collectingAndThen`, `groupingBy`) dễ bảo trì hơn viết collector mới.

## 6. Đọc mô tả về thứ tự, tính lười và tác dụng phụ

Javadoc của `Stream` và package là nguồn chính để hiểu những điều sau:

**Encounter order.** Một nguồn như `List` thường có thứ tự gặp phần tử; một nguồn như `HashSet` không cam kết thứ tự ổn định. `forEach` có thể xử lý khác thứ tự khi chạy song song; `forEachOrdered` tôn trọng encounter order nếu luồng có thứ tự, nhưng có thể tốn chi phí hơn. `findFirst` ưu tiên phần tử đầu tiên; `findAny` có quyền chọn phần tử bất kỳ.

**Laziness và tối ưu hóa.** Một terminal operation có thể rút ngắn công việc hoặc bỏ qua bước trung gian nếu việc tối ưu không làm thay đổi kết quả được bảo đảm. Vì thế, không dùng `peek` hay `map` chỉ để ghi log hoặc cập nhật bộ đếm mà chương trình phải dựa vào:

```java
long count = List.of("a", "b", "c").stream()
    .peek(System.out::println)
    .count();
// count == 3; không được dựa vào việc peek chắc chắn in ba dòng.
```

**Non-interference và statelessness.** Hàm truyền cho stream nên không sửa đổi nguồn đang được duyệt và không phụ thuộc vào trạng thái có thể thay đổi giữa các lần gọi. Khi dùng `parallel()`, việc cập nhật một `ArrayList`, `HashMap` hoặc biến đếm bên ngoài từ lambda có thể gây race condition hoặc lỗi. Hãy biểu diễn việc tích lũy bằng `collect`/`reduce` hoặc các phép toán thống kê thay vì side effect dùng chung.

**Tái sử dụng.** Một stream đã có terminal operation không dùng lại được; nếu cần hai kết quả, tạo hai stream mới từ nguồn có thể duyệt lại:

```java
List<Integer> data = List.of(1, 2, 3);
long count = data.stream().count();
int total = data.stream().mapToInt(Integer::intValue).sum();
```

**Tài nguyên.** Stream tạo từ `List.stream()` thường không cần đóng. Stream gắn với I/O như `Files.lines(path)` cần đóng để giải phóng handle:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
```

`Stream` kế thừa `BaseStream` và có phương thức `close()` qua `AutoCloseable`; try-with-resources là cách thích hợp với nguồn cần giải phóng tài nguyên. Đừng giữ stream mở lâu hơn phạm vi sử dụng.

## 7. Đọc các API nâng cao và giới hạn phiên bản

### 7.1. Primitive streams và chuyển kiểu

`Stream<Integer>` chứa đối tượng `Integer`; `IntStream` làm việc trực tiếp trên giá trị nguyên thủy `int`. Các chữ ký cần nhận diện:

```java
IntStream mapToInt(ToIntFunction<? super T> mapper) // trên Stream<T>
LongStream mapToLong(ToLongFunction<? super T> mapper) // trên Stream<T>
Stream<Integer> boxed()                            // trên IntStream
OptionalDouble average()                           // trên IntStream
```

`mapToInt` và `mapToLong` giúp tránh boxing không cần thiết trong tính toán số. `boxed()` chỉ nên dùng khi cần chuyển lại thành stream đối tượng, chẳng hạn trước khi gom vào `List<Integer>`.

### 7.2. `Spliterator` và xử lý song song

Stream có thể dùng `Spliterator<T>` để duyệt và chia nguồn. Khi xem chữ ký `boolean tryAdvance(Consumer<? super T> action)` và `Spliterator<T> trySplit()`, hiểu rằng phương thức đầu thử tiêu thụ một phần tử, còn phương thức sau có thể trả một spliterator tách ra hoặc `null` nếu không tách được. Các thuộc tính `ORDERED`, `SIZED`, `SUBSIZED`, `SORTED`, `DISTINCT`, `NONNULL`, `IMMUTABLE`, `CONCURRENT` giúp mô tả nguồn và hỗ trợ tối ưu hóa.

`parallel()` chỉ là yêu cầu thực thi pipeline theo chế độ song song; không đảm bảo nhanh hơn. Phân chia dữ liệu, phối hợp kết quả, tính thứ tự, các phép toán có trạng thái và chi phí của từng phần tử đều ảnh hưởng hiệu năng. Hãy dùng phép gộp associative, tránh shared mutable state và đo trên dữ liệu thực trước khi kết luận.

### 7.3. `Stream.gather` và Stream Gatherers (JDK 24+)

JDK 24 đưa Stream Gatherers thành API chính thức. Chữ ký cần đọc:

```java
<R> Stream<R> gather(Gatherer<? super T, ?, R> gatherer)
```

`Gatherer<T,A,R>` đại diện cho một phép toán trung gian có thể duy trì trạng thái `A`, nhận đầu vào `T` và phát đầu ra `R`. Nó bổ sung những biến đổi như phân cửa sổ, quét tích lũy hoặc biến đổi có ràng buộc mà chuỗi `map`/`filter` đơn giản khó thể hiện.

Ví dụ riêng cho **JDK 24 trở lên**:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(2))
    .toList();

System.out.println(windows); // [[1, 2], [3, 4], [5]]
```

Khi đọc Gatherer tùy chỉnh, cần xem kỹ `initializer`, `integrator`, `combiner`, `finisher` và những ràng buộc về thứ tự/khả năng chạy song song. Không thêm `gather` vào mã đích JDK 17 hoặc 21; dùng giải pháp thay thế tương thích hoặc nâng phiên bản sau khi đánh giá.

## 8. Quy trình tra cứu khi gặp một phương thức lạ

Ví dụ đề bài: “Từ `Stream<Order>`, lấy `Map<String,Long>` tổng doanh thu theo vùng”. Thay vì thử ngẫu nhiên các hàm:

1. **Xác định đầu vào/đầu ra:** `T = Order`; cần khóa `K = String` và giá trị `D = Long`.
2. **Tìm terminal operation:** `Stream.collect` cho kết quả kiểu tùy ý `R`, phù hợp hơn `toList()`.
3. **Tìm factory collector:** `Collectors.groupingBy(classifier, downstream)` trả `Map<K,D>`; `summingLong` tạo `Long` cho từng nhóm.
4. **Kiểm tra hợp đồng:** thứ tự map không được bảo đảm; xử lý `null`, dữ liệu rỗng, và các điều kiện phụ thuộc business trước khi viết pipeline.
5. **Kiểm tra `Since` và phiên bản JDK:** API dùng trong ví dụ đã có từ trước JDK 17.
6. **Chạy thử bằng dữ liệu nhỏ:** kiểm tra vùng có nhiều đơn hàng, vùng chỉ có một đơn, đơn không được lọc, nguồn rỗng; đo hiệu năng trước khi cân nhắc `parallel()`.

### Tự kiểm tra khả năng đọc chữ ký

**Câu 1.** `boolean noneMatch(Predicate<? super T> predicate)` nhận gì và có thể kết thúc sớm không?

Trả lời: nhận điều kiện kiểm tra từng `T`, trả `true` khi không có phần tử nào thỏa; có thể kết thúc ngay khi tìm thấy một phần tử thỏa. Với stream rỗng, kết quả là `true`.

**Câu 2.** `Optional<T> min(Comparator<? super T> comparator)` khác `Stream<T> sorted(Comparator<? super T>)` thế nào?

Trả lời: `min` là terminal operation trả một giá trị tùy chọn, còn `sorted` là intermediate operation trả stream đã được mô tả để sắp xếp. Khi chỉ cần phần tử nhỏ nhất, `min` diễn đạt mục tiêu trực tiếp hơn.

**Câu 3.** Tại sao `Stream<T>.mapToLong(...)` trả `LongStream`, trong khi `map(...)` trả `Stream<R>`?

Trả lời: `mapToLong` chuyên dùng cho dữ liệu `long` nguyên thủy và hỗ trợ `sum`, `average`, `summaryStatistics` trực tiếp; `map` giữ cách biểu diễn đối tượng và có thể phát sinh boxing.

**Câu 4.** Có nên dùng `stream.parallel().forEach(x -> sharedList.add(x))` không?

Trả lời: không; `ArrayList` chia sẻ không an toàn khi nhiều luồng cập nhật. Dùng terminal collection phù hợp như `toList()`/`collect` để thư viện phối hợp kết quả; chỉ dùng `forEach` với hành động đáp ứng yêu cầu đồng thời và không phụ thuộc thứ tự.

## 9. Bảng nhắc nhanh khi đọc Javadoc Stream API

| Câu hỏi cần trả lời | Nơi tìm trong Javadoc |
| --- | --- |
| Phần tử đầu vào và kết quả có kiểu gì? | Chữ ký phương thức; Type Parameters; Parameters; Returns |
| Có chạy ngay không, có thể dừng sớm không? | Mô tả intermediate/terminal/short-circuiting |
| Kết quả có ổn định theo thứ tự nguồn không? | Encounter order và mô tả cụ thể của phương thức |
| Có dùng được với stream rỗng/null không? | Returns, Throws, hợp đồng của Optional và collector |
| Lambda có được đọc/sửa trạng thái bên ngoài không? | Package summary; non-interference; statelessness; side effects |
| Chạy song song có đúng và có lợi không? | Reduction, parallelism, Collector characteristics, Spliterator characteristics |
| Khi nào đóng stream? | `BaseStream.close`, `onClose`, tài liệu của nguồn I/O |
| Dự án hỗ trợ phiên bản nào? | `Since`, Javadoc của đúng JDK đích |

Khi đọc API, hãy xem **chữ ký để xác định hợp đồng kiểu**, đọc **mô tả Javadoc để xác định hành vi**, và kiểm tra **nguồn dữ liệu cùng phiên bản JDK** để lựa chọn pipeline đúng. Đây là nền tảng để mở rộng từ `filter`/`map` sang `reduce`, collector tùy chỉnh, Spliterator, xử lý song song và Stream Gatherers mà vẫn kiểm soát được trạng thái, tài nguyên và hiệu năng.
