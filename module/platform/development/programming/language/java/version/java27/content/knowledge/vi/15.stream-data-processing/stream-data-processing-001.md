# Nguồn stream, pipeline và cơ chế thực thi lười

> **Phạm vi:** Java 27 — chương **Xử lý dữ liệu bằng Stream**. Bài học làm rõ Stream đến từ đâu, cách xây dựng một pipeline, vì sao các bước trung gian được thực thi lười (*lazy evaluation*), các tình huống short-circuit, giới hạn của việc dùng lại Stream và quản lý tài nguyên. Các ví dụ dùng API Java hiện hành, không cần preview feature.

## 1. Stream là gì và khác Collection như thế nào?

`java.util.stream.Stream<T>` biểu diễn một luồng phần tử có thể được xử lý bằng các phép toán kết hợp theo kiểu khai báo: lọc, ánh xạ, nhóm, tổng hợp và tìm kiếm. Các specialization cho primitive gồm `IntStream`, `LongStream` và `DoubleStream`.

Một Stream **không phải một cấu trúc dữ liệu chứa sẵn các phần tử** như `List` hay `Set`. Stream là một mô tả về **nguồn dữ liệu** và các phép xử lý dữ liệu đó. Nguồn có thể là collection, mảng, hàm sinh dữ liệu, file, kết quả phân tách văn bản hoặc một nguồn tùy chỉnh.

| Tiêu chí | Collection | Stream |
| --- | --- | --- |
| Vai trò chính | Lưu trữ và quản lý phần tử | Mô tả và thực thi chuỗi phép xử lý |
| Có thể duyệt lại? | Thường có, nếu collection còn dùng được | Một pipeline chỉ được tiêu thụ một lần |
| Phần tử có nhất thiết lưu sẵn? | Có dữ liệu do collection quản lý | Không; nguồn có thể sinh dữ liệu theo nhu cầu |
| Thao tác `filter`/`map` | Không phải API cơ bản của Collection | Intermediate operations tạo pipeline |
| Khi nào bắt đầu tính toán? | Tùy lời gọi trên collection | Phần lớn công việc chỉ bắt đầu tại terminal operation |
| Số phần tử | Thường hữu hạn | Có thể hữu hạn hoặc vô hạn |
| Dữ liệu gốc có bị sửa khi filter/map? | Không áp dụng | Stream operations không tự sửa source |

Ví dụ:

~~~java
import java.util.List;

List<String> names = List.of("Lan", "Binh", "Linh");

List<String> result = names.stream()
        .filter(name -> name.startsWith("L"))
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [LAN, LINH]
System.out.println(names);  // [Lan, Binh, Linh]
~~~

`names.stream()` **không xóa** phần tử khỏi `names`. `toList()` tạo một kết quả mới sau khi pipeline chạy; kết quả này là một `List` không cho phép sửa qua các phương thức mutation theo hợp đồng `Stream.toList()`.

## 2. Mô hình ba phần của một Stream pipeline

Một pipeline có ba thành phần:

1. **Source**: nơi lấy hoặc sinh các phần tử.
2. **Zero hoặc nhiều intermediate operations**: định nghĩa các bước biến đổi, ví dụ `filter`, `map`, `sorted`.
3. **Terminal operation**: yêu cầu tính toán kết quả hoặc gây tác động xác định, ví dụ `toList`, `count`, `findFirst`.

~~~text
  Source                      Intermediate (lazy)            Terminal
┌─────────────┐           ┌──────────┐    ┌──────────┐    ┌──────────────┐
│ List<Order> │─stream()─▶│ filter   │───▶│ map      │───▶│ toList()     │
└─────────────┘           └──────────┘    └──────────┘    └──────────────┘
                                                            │
                                                            ▼
                                                      List<Result>
~~~

Ví dụ dùng record làm mô hình dữ liệu:

~~~java
import java.util.List;

record Order(String id, long amount) {}

List<Order> orders = List.of(
        new Order("A", 150),
        new Order("B", 50),
        new Order("C", 300));

List<String> importantIds = orders.stream() // Source
        .filter(order -> order.amount() >= 100) // Intermediate
        .map(Order::id)                         // Intermediate
        .toList();                              // Terminal

System.out.println(importantIds); // [A, C]
~~~

Đến trước `toList()`, các bước `filter` và `map` chưa được chạy trên các phần tử. Terminal operation kích hoạt quá trình xử lý các phần tử theo pipeline.

### 2.1. Một pipeline có thể không có intermediate operation

~~~java
long count = List.of("A", "B", "C")
        .stream()        // Source
        .count();        // Terminal, không có intermediate
~~~

Lưu ý: đừng nhầm việc **tạo Stream** bằng `stream()` với việc **tiêu thụ Stream** bằng `count()`.

## 3. Các nguồn Stream phổ biến trong Java 27

Các nguồn đang được hỗ trợ gồm collection, mảng, factory methods, các generator, file và API của JDK. Chọn nguồn cần dựa trên đặc tính dữ liệu, số phần tử, khả năng đóng tài nguyên và yêu cầu encounter order.

### 3.1. Collection.stream() và parallelStream()

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> languages = List.of("Java", "Kotlin", "Scala");

Stream<String> sequential = languages.stream();
long count = sequential.count(); // 3
~~~

`Collection.stream()` tạo stream tuần tự. `Collection.parallelStream()` tạo stream với chế độ parallel; **không có nghĩa** mọi phép toán sẽ chạy nhanh hơn hay mọi thao tác sẽ chia thành tác vụ song song có lợi.

~~~java
long total = List.of(10, 20, 30)
        .parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(total); // 60
~~~

Nguồn `List` thường có **encounter order** theo vị trí phần tử. `HashSet` không cam kết encounter order; `LinkedHashSet` và `TreeSet` có thứ tự theo hợp đồng của implementation. Thứ tự nguồn có ảnh hưởng đến `findFirst`, `forEachOrdered` và một số phép toán stateful.

### 3.2. Arrays.stream và Stream.of

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.Stream;

String[] words = {"java", "streams", "pipeline"};

Stream<String> wordStream = Arrays.stream(words);
IntStream values = Arrays.stream(new int[] {3, 5, 8});

System.out.println(wordStream.count()); // 3
System.out.println(values.sum());       // 16
~~~

`Stream.of(...)` phù hợp khi đã có vài phần tử:

~~~java
var result = Stream.of("red", "green", "blue")
        .filter(color -> color.length() > 3)
        .toList();

System.out.println(result); // [green, blue]
~~~

**Bẫy với mảng primitive:**

~~~java
int[] numbers = {1, 2, 3};

// Một phần tử kiểu int[]:
Stream<int[]> oneArray = Stream.of(numbers);

// Ba số primitive:
IntStream threeInts = Arrays.stream(numbers);

System.out.println(oneArray.count()); // 1
System.out.println(threeInts.count()); // 3
~~~

Nên dùng `Arrays.stream(int[])` hoặc `IntStream.of(int...)` khi cần stream chứa từng số primitive, không phải stream chứa **một mảng**.

### 3.3. Stream.empty và Stream.ofNullable

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<String> empty = Stream.empty();
System.out.println(empty.count()); // 0

String optionalLabel = null;

List<String> labels = Stream.ofNullable(optionalLabel)
        .map(String::strip)
        .toList();

System.out.println(labels); // []
~~~

`Stream.ofNullable(value)` tạo stream có **0 phần tử nếu value là null**, hoặc **1 phần tử nếu không null**. Đây là cách thuận tiện để đưa một giá trị tùy chọn vào pipeline mà không tạo collection tạm.

`Stream.ofNullable` không phải thao tác lọc tất cả phần tử null từ một stream đã có. Để xử lý một stream hiện hữu có thể chứa null, có thể dùng `filter(java.util.Objects::nonNull)` nếu đúng hợp đồng dữ liệu.

### 3.4. Stream.builder

Khi muốn thêm dần một số phần tử trước khi tạo stream:

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream.Builder<String> builder = Stream.builder();
builder.add("receive");
builder.add("validate");
builder.add("publish");

List<String> stages = builder.build().toList();
System.out.println(stages); // [receive, validate, publish]
~~~

Sau `build()`, builder không còn ở trạng thái cho phép thêm phần tử để build lần nữa. Đây không phải công cụ để cập nhật một stream đã bắt đầu xử lý.

### 3.5. IntStream.range, rangeClosed và các primitive streams

~~~java
import java.util.stream.IntStream;

int sum = IntStream.range(1, 5).sum();       // 1 + 2 + 3 + 4 = 10
int sumClosed = IntStream.rangeClosed(1, 5).sum(); // 15

System.out.println(sum);
System.out.println(sumClosed);
~~~

| Nguồn | Đặc điểm |
| --- | --- |
| `IntStream.range(a, b)` | Bao gồm `a`, không bao gồm `b` |
| `IntStream.rangeClosed(a, b)` | Bao gồm cả hai đầu |
| `LongStream.range(a, b)` | Nguồn `long` theo đoạn |
| `IntStream.of(int...)` | Các giá trị primitive cụ thể |
| `Arrays.stream(int[])` | Từng phần tử của mảng primitive |
| `Stream<T>.mapToInt(...)` | Chuyển object stream sang primitive stream |

Các specialization primitive giúp tránh boxing/unboxing không cần thiết trong nhiều phép toán số. Tuy nhiên, vẫn cần quan tâm đến **tràn số** khi tổng hợp lượng dữ liệu lớn; ví dụ `IntStream.sum()` trả `int`, không phải số nguyên độ lớn tùy ý.

### 3.6. Stream.iterate và Stream.generate

`Stream.iterate(seed, next)` sinh chuỗi phần tử tuần tự theo quy tắc lặp. Nếu không có điều kiện dừng, stream có thể **vô hạn**:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Integer> powersOfTwo = Stream
        .iterate(1, n -> n * 2)
        .limit(5)
        .toList();

System.out.println(powersOfTwo); // [1, 2, 4, 8, 16]
~~~

Bản overload có điều kiện dừng:

~~~java
List<Integer> values = Stream
        .iterate(1, n -> n <= 5, n -> n + 1)
        .toList();

System.out.println(values); // [1, 2, 3, 4, 5]
~~~

`Stream.generate(supplier)` tạo stream tuần tự **không có encounter order**, thường không giới hạn số phần tử:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> defaults = Stream
        .generate(() -> "unknown")
        .limit(3)
        .toList();

System.out.println(defaults); // [unknown, unknown, unknown]
~~~

Đối với nguồn vô hạn, pipeline chỉ hoàn tất nếu có cơ chế dừng phù hợp với chuỗi phép toán. `limit` và `findFirst` là những thành phần có thể làm việc đó, nhưng **không bảo đảm** mọi pipeline chứa chúng sẽ kết thúc (ví dụ khi có `sorted` trước `limit` trên một nguồn vô hạn).

### 3.7. Stream từ file và các nguồn I/O

`Files.lines(path, charset)` mở một stream các dòng trong tệp; các dòng được cung cấp trong khi pipeline được duyệt:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

public class LogCounter {
    public static long countErrors(Path path) throws IOException {
        try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                    .filter(line -> line.contains("ERROR"))
                    .count();
        }
    }
}
~~~

**Quan trọng:** Stream nguồn I/O có thể giữ file descriptor, channel hoặc tài nguyên của hệ điều hành. Dùng `try-with-resources` để bảo đảm `close()` được gọi, kể cả khi pipeline ném ngoại lệ.

Các nguồn tương tự cần lưu ý vòng đời tài nguyên:

- `Files.lines(path)` và `BufferedReader.lines()` (đóng reader sở hữu bên ngoài khi thích hợp).
- `Files.list(dir)`, `Files.walk(dir)`, `Files.find(...)`.
- Stream được tạo bởi một API truy cập database hoặc bên thứ ba nếu API ghi rõ cần đóng.

Ngược lại, stream bắt nguồn từ `List`, mảng, `Stream.of` hay `IntStream.range` thường **không** quản lý tài nguyên bên ngoài và không cần đóng sau khi dùng.

### 3.8. Nguồn tùy chỉnh với Spliterator

Đối với nguồn dữ liệu đặc biệt, `StreamSupport.stream(spliterator, parallel)` hoặc overload nhận `Supplier<Spliterator>` cho phép kết nối một `Spliterator` vào Stream API.

~~~java
import java.util.List;
import java.util.stream.StreamSupport;

var source = List.of("A", "B", "C");
var spliterator = source.spliterator();

var result = StreamSupport.stream(spliterator, false)
        .map(String::toLowerCase)
        .toList();

System.out.println(result); // [a, b, c]
~~~

`Spliterator` mô tả cách duyệt/phân chia nguồn và báo các đặc tính như `ORDERED`, `SIZED`, `SORTED`, `DISTINCT`, `CONCURRENT`, `IMMUTABLE`. **Không khai báo sai** các characteristic vì pipeline có thể tối ưu hóa dựa trên chúng và cho ra kết quả không như mong đợi.

Với ứng dụng bình thường, ưu tiên nguồn Stream đã được thư viện chuẩn cung cấp thay vì tự viết Spliterator nếu không có nhu cầu thực tế.

## 4. Intermediate operations: xây pipeline nhưng chưa chạy

Các phương thức intermediate trả một stream, có thể là stream cùng loại hoặc stream mang kiểu mới. Chúng **lười** (*lazy*): gọi method để xây một tầng pipeline không đồng nghĩa đã duyệt source.

| Operation | Nhóm | Mô tả |
| --- | --- | --- |
| `filter(predicate)` | Stateless | Giữ phần tử phù hợp điều kiện |
| `map(mapper)` | Stateless | Biến đổi từng phần tử |
| `mapToInt/mapToLong/mapToDouble` | Stateless | Chuyển sang primitive stream |
| `flatMap(mapper)` | Stateless (về bản chất operation) | Ghép các stream con thành một luồng |
| `mapMulti(mapper)` | Stateless theo cách mapper được thiết kế | Một phần tử đầu vào có thể tạo 0/nhiều đầu ra |
| `peek(consumer)` | Stateless nếu callback không giữ trạng thái | Quan sát phần tử khi pipeline thực sự xử lý |
| `distinct()` | Stateful | Loại phần tử trùng, cần ghi nhớ dữ liệu trước đó |
| `sorted()/sorted(comparator)` | Stateful | Sắp xếp, có thể cần giữ toàn bộ dữ liệu |
| `limit(n)` | Short-circuiting, stateful | Giới hạn số phần tử sau các bước phía trước |
| `skip(n)` | Stateful | Bỏ qua số phần tử đầu theo encounter order |
| `takeWhile(predicate)` | Short-circuiting, stateful trên ordered stream | Lấy prefix còn thỏa điều kiện |
| `dropWhile(predicate)` | Stateful trên ordered stream | Bỏ prefix còn thỏa điều kiện |
| `gather(gatherer)` | Mở rộng tùy chỉnh, thường stateful | Các phép biến đổi nâng cao với Gatherers |

Tất cả phép toán trong bảng là intermediate, nhưng **không đồng nghĩa không tốn bộ nhớ**. `sorted` phải có đủ thông tin để xuất thứ tự đúng, `distinct` có thể phải nhớ các phần tử đã gặp, và `gather` có thể giữ trạng thái theo quy tắc Gatherer.

### 4.1. filter và map không tự tạo List trung gian

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> pipeline = List.of(1, 2, 3, 4).stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10);

// Chưa có phần tử nào được xử lý bởi filter/map ở trên.
List<Integer> result = pipeline.toList();

System.out.println(result); // [20, 40]
~~~

Trong ví dụ, `pipeline` là một mô tả xử lý đang chờ terminal operation. Pipeline không bắt buộc tạo `List` cho kết quả riêng của từng bước `filter` và `map`. Khi có thể, các bước stateless được *fuse* trong một lần duyệt source.

### 4.2. Ví dụ flatMap: mỗi phần tử tạo một nguồn con

~~~java
import java.util.List;

List<List<String>> batches = List.of(
        List.of("A", "B"),
        List.of("C"),
        List.of("D", "E"));

List<String> all = batches.stream()
        .flatMap(List::stream)
        .toList();

System.out.println(all); // [A, B, C, D, E]
~~~

`flatMap` phù hợp để “làm phẳng” một collection lồng nhiều cấp. Stream con được đóng khi nội dung của nó đã được ghép vào pipeline, theo hợp đồng của `flatMap`. Callback không được sửa source đang được duyệt.

### 4.3. Stream Gatherers đã là API chính thức

`Stream.gather(Gatherer)` và `java.util.stream.Gatherers` là API chính thức từ Java 24 (JEP 485), vẫn có trong Java 27. Chúng cho phép xây intermediate operation tùy chỉnh, kể cả phép biến đổi stateful như chia luồng thành các nhóm cửa sổ:

~~~java
import java.util.List;
import java.util.stream.Gatherers;

List<List<Integer>> windows = List.of(1, 2, 3, 4, 5)
        .stream()
        .gather(Gatherers.windowFixed(2))
        .toList();

System.out.println(windows); // [[1, 2], [3, 4], [5]]
~~~

`gather` vẫn là intermediate và thực thi theo nhu cầu của terminal operation. Một Gatherer có thể giữ trạng thái hoặc cần bộ đệm, nên không nên suy luận rằng mọi gatherer đều tiêu thụ O(1) bộ nhớ.

## 5. Chứng minh laziness bằng ví dụ có dấu vết

Để thấy thứ tự thực thi, dùng ví dụ **tuần tự** đơn giản với lời gọi terminal `findFirst`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class LazyDemo {
    public static void main(String[] args) {
        Stream<String> pipeline = List.of(
                "  ", " Java ", " Kotlin ")
                .stream()
                .filter(s -> {
                    System.out.println("filter: [" + s + "]");
                    return !s.isBlank();
                })
                .map(s -> {
                    System.out.println("map: [" + s + "]");
                    return s.strip();
                });

        System.out.println("Pipeline ready");

        Optional<String> first = pipeline.findFirst();
        System.out.println(first.orElse("none"));
    }
}
~~~

Kết quả cho ví dụ tuần tự này:

~~~text
Pipeline ready
filter: [  ]
filter: [ Java ]
map: [ Java ]
Java
~~~

Giải thích:

1. Khi gọi `filter`/`map`, Java chỉ **kết nối pipeline**; chưa gọi lambda trên phần tử.
2. In `Pipeline ready` trước vì chưa có terminal operation.
3. `findFirst` bắt đầu tiêu thụ source.
4. Phần tử `"  "` bị `filter` loại, nên `map` không chạy với nó.
5. Phần tử `" Java "` vượt qua filter, được map thành `"Java"`.
6. `findFirst` đã có kết quả nên không cần duyệt `" Kotlin "`.

Đây là hành vi quan sát được với pipeline có thứ tự, xử lý tuần tự, không có thao tác stateful ngăn việc rút ngắn. **Đừng coi số lần gọi callback là hợp đồng chung** của mọi pipeline: Stream implementation có quyền tối ưu và có thể bỏ qua một số giai đoạn nếu kết quả terminal vẫn đúng.

## 6. Thực thi theo từng phần tử, nhưng không phải luôn như vậy

Với các bước stateless, Java thường xử lý một phần tử qua nhiều công đoạn rồi mới chuyển sang phần tử tiếp theo:

~~~text
Source [A, B, C, D]
   │
   ├─ A → filter → map → terminal
   ├─ B → filter (discard)
   ├─ C → filter → map → terminal
   └─ D → filter → map → terminal
~~~

Cách vận hành này giúp tránh tạo các collection tạm lớn. Tuy nhiên pipeline có **stateful intermediate operation** có thể phải giữ lại các phần tử:

~~~java
import java.util.List;

List<Integer> sorted = List.of(4, 1, 3, 2).stream()
        .filter(n -> n > 0)
        .sorted()
        .limit(2)
        .toList();

System.out.println(sorted); // [1, 2]
~~~

Với dữ liệu bất kỳ, `sorted()` cần xét toàn bộ đầu vào để bảo đảm phần tử đầu ra là nhỏ nhất. Vì vậy, `limit(2)` đứng **sau** `sorted()` không làm cho việc đọc source nhất thiết dừng sau hai phần tử.

Trái lại:

~~~java
List<Integer> firstTwoSorted = List.of(4, 1, 3, 2).stream()
        .limit(2)
        .sorted()
        .toList();

System.out.println(firstTwoSorted); // [1, 4]
~~~

Hai pipeline khác nhau về **ngữ nghĩa**, không chỉ hiệu năng:

- `sorted().limit(2)` = lấy hai giá trị nhỏ nhất trong toàn bộ tập.
- `limit(2).sorted()` = lấy hai giá trị đầu theo encounter order, rồi sắp xếp chúng.

**Không đổi thứ tự intermediate operations chỉ để tối ưu hóa nếu điều đó làm thay đổi bài toán.**

## 7. Terminal operations kích hoạt pipeline

Một số terminal operations phổ biến:

| Terminal | Kết quả | Ghi chú |
| --- | --- | --- |
| `toList()` | `List<T>` không cho sửa | Có từ Java 16; giữ encounter order nếu tồn tại |
| `collect(collector)` | Giá trị theo collector | Ví dụ `Collectors.groupingBy`, `toSet` |
| `count()` | `long` | Có thể tối ưu không duyệt phần tử |
| `reduce(...)` | Giá trị tổng hợp | Cần phép kết hợp phù hợp, nhất là khi parallel |
| `min/max` | `Optional<T>` | Cần comparator |
| `findFirst()` | `Optional<T>` | Short-circuit, xét encounter order nếu có |
| `findAny()` | `Optional<T>` | Short-circuit, không cam kết phần tử cụ thể |
| `anyMatch/allMatch/noneMatch` | `boolean` | Short-circuit theo điều kiện |
| `forEach` | `void` | Side-effect terminal, không cam kết encounter order khi parallel |
| `forEachOrdered` | `void` | Tôn trọng encounter order khi nguồn có thứ tự |
| `IntStream.sum()/average()` | Số hoặc `OptionalDouble` | Primitive terminal |

Một vài ví dụ:

~~~java
import java.util.List;

List<Integer> nums = List.of(2, 5, 8, 11);

long evens = nums.stream()
        .filter(n -> n % 2 == 0)
        .count(); // 2

boolean hasLarge = nums.stream()
        .anyMatch(n -> n > 10); // true

int sum = nums.stream()
        .mapToInt(Integer::intValue)
        .sum(); // 26
~~~

Mỗi phép trên tạo **stream mới từ source**. Không dùng lại cùng một `Stream` sau khi nó được tiêu thụ.

### 7.1. count() có thể bỏ qua thao tác trung gian

Tính lười còn cho phép tối ưu hóa mạnh hơn: nếu source đã biết số phần tử và các bước intermediate không thay đổi kích thước, `count()` có thể trả lời mà không thực hiện traversal:

~~~java
import java.util.List;

long size = List.of("A", "B", "C")
        .stream()
        .peek(s -> System.out.println("seen: " + s))
        .count();

System.out.println(size); // 3
~~~

Lời gọi `peek` **có thể không in gì** trong ví dụ này. Đó là hành vi hợp lệ: `count` có thể lấy kích thước từ source mà không duyệt phần tử; callback `peek` không cần chạy để bảo toàn giá trị `count`.

Điểm quan trọng:

- **Lazy** không có nghĩa “mọi callback chắc chắn chạy sau đó”.
- Terminal operation có thể **không cần** gọi toàn bộ callback phía trước.
- Không dựa vào `peek`/`map` như nơi ghi audit bắt buộc, đếm transaction hay thực thi nghiệp vụ.

Dùng `peek` chủ yếu để quan sát/debug có kiểm soát, không làm tiền đề cho tính đúng của kết quả.

### 7.2. Một số terminal operations là ngoại lệ về độ eager

`iterator()` và `spliterator()` là terminal operations đặc biệt: chúng trả phương tiện cho caller **tự điều khiển quá trình duyệt** sau đó, thay vì duyệt toàn bộ trước khi trả về.

~~~java
import java.util.List;
import java.util.Iterator;

Iterator<String> it = List.of("A", "B")
        .stream()
        .map(String::toLowerCase)
        .iterator();

System.out.println(it.next()); // a
~~~

Đừng lấy đây làm lý do gọi `iterator()` rồi tiếp tục gắn intermediate operation vào stream cũ: pipeline đã chuyển quyền duyệt sang iterator và không được tái sử dụng.

## 8. Short-circuiting: kết thúc sớm khi đủ kết quả

Short-circuiting cho phép pipeline dừng sau khi đã có đủ thông tin. Có hai nhóm:

- **Short-circuiting intermediate**: `limit(n)` và `takeWhile(predicate)` có thể tạo một stream hữu hạn từ nguồn vô hạn.
- **Short-circuiting terminal**: `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch` có thể dừng mà không duyệt hết nguồn.

Ví dụ:

~~~java
import java.util.stream.IntStream;

boolean hasEven = IntStream.range(1, 1_000_000)
        .anyMatch(n -> n % 2 == 0);

System.out.println(hasEven); // true, có thể dừng tại 2
~~~

`anyMatch` chỉ cần thấy **một phần tử thỏa**. `allMatch` có thể dừng khi gặp **một phần tử không thỏa**; `noneMatch` có thể dừng khi gặp **một phần tử thỏa**.

### 8.1. Trường hợp rỗng của match operations

~~~java
import java.util.stream.Stream;

System.out.println(Stream.<Integer>empty()
        .anyMatch(n -> n > 0)); // false

System.out.println(Stream.<Integer>empty()
        .allMatch(n -> n > 0)); // true

System.out.println(Stream.<Integer>empty()
        .noneMatch(n -> n > 0)); // true
~~~

`allMatch` và `noneMatch` trả `true` với stream rỗng theo quy tắc lượng từ logic; không phải lỗi hay một special case bất thường.

### 8.2. Short-circuit không bảo đảm luôn hữu hạn

~~~java
import java.util.stream.Stream;

// Nguy hiểm: nguồn vô hạn, sorted không thể biết thứ tự cuối cùng.
// var neverFinishes = Stream.iterate(0, n -> n + 1)
//         .sorted()
//         .limit(5)
//         .toList();
~~~

Dù có `limit(5)`, `sorted` phải xét nguồn trước khi biết “năm phần tử nhỏ nhất”, nên pipeline này không có điều kiện kết thúc bình thường. Tương tự, `filter` trên một nguồn vô hạn không có phần tử thỏa điều kiện có thể không tạo được kết quả đầu tiên cho `findFirst`.

Khi xử lý nguồn chưa biết kích thước, hãy phân tích **khả năng hoàn tất từng stage** chứ không chỉ nhìn vào terminal operation.

### 8.3. takeWhile và dropWhile

~~~java
import java.util.List;

List<Integer> values = List.of(2, 4, 6, 3, 8);

System.out.println(values.stream()
        .takeWhile(n -> n % 2 == 0)
        .toList()); // [2, 4, 6]

System.out.println(values.stream()
        .dropWhile(n -> n % 2 == 0)
        .toList()); // [3, 8]
~~~

`takeWhile` không tương đương `filter`: nó lấy **prefix liên tục** đến khi điều kiện sai lần đầu tiên. `dropWhile` bỏ prefix đó, không loại mọi phần tử chẵn ở phần còn lại.

Với **unordered stream**, các phép toán này có quyền chọn tập con/thứ tự khác theo hợp đồng, vì không có một prefix theo encounter order để cố định. Khi thứ tự là điều kiện nghiệp vụ, giữ ordered source.

## 9. Encounter order, sự khác biệt giữa findFirst và findAny

Encounter order được quyết định bởi source (nếu có) và có thể bị ảnh hưởng bởi các operation như `unordered()`, `sorted()`. Ví dụ:

~~~java
import java.util.List;

String first = List.of("A", "B", "C")
        .stream()
        .findFirst()
        .orElseThrow();

System.out.println(first); // A
~~~

Với ordered source, `findFirst` trả phần tử đầu theo encounter order. `findAny` chỉ trả **một** phần tử nếu có, không cam kết là phần tử đầu, nhất là trong pipeline song song.

~~~java
import java.util.Set;

var result = Set.of("A", "B", "C")
        .parallelStream()
        .findAny();
~~~

Không viết test đòi `result` luôn bằng `"A"`: nguồn `Set.of` không có encounter order được cam kết và `findAny` vốn nondeterministic theo hợp đồng.

### 9.1. forEach và forEachOrdered

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3);

values.parallelStream()
        .forEach(System.out::println);
// Thứ tự in không được bảo đảm.

values.parallelStream()
        .forEachOrdered(System.out::println);
// 1, 2, 3 theo encounter order.
~~~

`forEachOrdered` giữ thứ tự khi có encounter order, nhưng việc ràng buộc thứ tự có thể giảm khả năng tối ưu song song. `parallelStream()` không được chọn chỉ vì pipeline “trông dài”; hãy đo hiệu năng thực tế.

## 10. Stream chỉ tiêu thụ một lần

Một Stream không giống collection có thể duyệt lại vô hạn lần. Mỗi Stream pipeline chỉ được vận hành một lần.

Ví dụ lỗi:

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<String> source = List.of("A", "B", "C").stream();

long count = source.count();   // Đã tiêu thụ stream
// List<String> copy = source.toList(); // IllegalStateException (thường gặp)
~~~

Javadoc nói việc vận hành lại pipeline đã được tiêu thụ là **không hợp lệ**; implementation có thể ném `IllegalStateException` khi phát hiện, nhưng không phải lúc nào cũng phát hiện được mọi trường hợp reuse. Không thiết kế logic dựa vào việc “thử lại stream và xem có ném exception không”.

### 10.1. Cách đúng: tạo Stream mới từ source còn dùng được

~~~java
import java.util.List;

List<String> values = List.of("A", "B", "C");

long count = values.stream().count();
List<String> upper = values.stream()
        .map(String::toUpperCase)
        .toList();
~~~

Collection nguồn vẫn có thể được dùng để tạo hai pipeline độc lập.

Nếu muốn trì hoãn việc tạo pipeline, có thể dùng `Supplier<Stream<T>>`:

~~~java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

Supplier<Stream<String>> freshStream =
        () -> List.of("A", "B", "C").stream();

System.out.println(freshStream.get().count()); // 3
System.out.println(freshStream.get().toList()); // [A, B, C]
~~~

Mỗi lần gọi supplier tạo **Stream mới**; không được viết supplier chỉ trả lại cùng một instance Stream đã tiêu thụ.

### 10.2. Không tách một Stream thành hai nhánh để dùng riêng

~~~java
import java.util.stream.Stream;

Stream<Integer> base = Stream.of(1, 2, 3);
Stream<Integer> even = base.filter(n -> n % 2 == 0);

// Không tiếp tục dùng base để tạo một pipeline khác:
// Stream<Integer> odd = base.filter(n -> n % 2 != 0);
~~~

Khi gắn intermediate stage, source stream không còn được dùng như điểm phân nhánh để vận hành độc lập. Nếu cần nhiều phép tính, tạo stream mới từ source hoặc tính chung trong một traversal bằng collector/reduction phù hợp.

## 11. Chỉnh sửa nguồn khi pipeline đang thực thi: non-interference

Các callback truyền vào `filter`, `map`, `sorted(comparator)` và nhiều operation khác phải **non-interfering**: không sửa nguồn stream trong lúc pipeline đang vận hành, trừ các trường hợp đặc biệt có hợp đồng cho phép (ví dụ một số concurrent source).

Sai lầm:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> values = new ArrayList<>(
        List.of("A", "B", "C"));

// Không nên làm điều này:
// values.stream().forEach(v -> {
//     if (v.equals("A")) {
//         values.remove(v);
//     }
// });
~~~

Hành vi có thể không ổn định, ném `ConcurrentModificationException` hoặc cho kết quả không mong đợi. Fail-fast exception không phải cơ chế bảo đảm an toàn dữ liệu.

Nếu cần loại phần tử khỏi collection:

~~~java
List<String> values = new ArrayList<>(
        List.of("A", "B", "C"));

values.removeIf("A"::equals);
System.out.println(values); // [B, C]
~~~

Nếu muốn tạo collection mới mà không sửa nguồn:

~~~java
List<String> retained = values.stream()
        .filter(v -> !v.equals("A"))
        .toList();
~~~

Hai giải pháp này có hợp đồng khác nhau: `removeIf` **sửa collection nguồn**, còn pipeline `filter(...).toList()` **tạo kết quả mới**.

### 11.1. Stateful lambda và nguồn có thể thay đổi

~~~java
int[] counter = {0};

// Tránh: kết quả phụ thuộc trạng thái mutable bên ngoài;
// đặc biệt khó đúng khi parallel hoặc Stream tối ưu pipeline.
var labels = List.of("A", "B", "C").stream()
        .map(s -> (++counter[0]) + "-" + s)
        .toList();
~~~

Ví dụ trên không phải mẫu thiết kế tốt: lambda vừa tăng biến đếm vừa biến đổi giá trị. Nếu cần chỉ số, hãy dùng nguồn `IntStream.range` có miền rõ:

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<String> values = List.of("A", "B", "C");

List<String> indexed = IntStream.range(0, values.size())
        .mapToObj(i -> (i + 1) + "-" + values.get(i))
        .toList();

System.out.println(indexed); // [1-A, 2-B, 3-C]
~~~

Giải pháp phù hợp khi nguồn là list có truy cập theo chỉ số. Với luồng không có index tự nhiên, hãy xác định rõ yêu cầu order trước khi đánh số.

## 12. Side effects: vì sao peek không phải công cụ nghiệp vụ

Do pipeline có thể lazy, short-circuit và được tối ưu, không nên dùng các callback làm nơi thực hiện tác vụ bắt buộc như:

- Ghi sổ giao dịch/audit không được phép mất.
- Gửi email, thanh toán, ghi database.
- Tăng bộ đếm phải có số lần chính xác bằng số phần tử nguồn.
- Thay đổi global state quyết định kết quả các phần tử tiếp theo.
- Thực hiện lock/unlock tài nguyên bên ngoài.

Ví dụ sai về mặt thiết kế:

~~~java
// Không dùng peek cho tác động bắt buộc:
// orders.stream()
//       .peek(order -> auditService.record(order))
//       .map(Order::id)
//       .count();
~~~

`count()` có thể bỏ qua traversal khi đủ thông tin; `peek` vì thế có thể không chạy. Với `findFirst`, pipeline chỉ xử lý phần tử cần thiết; với parallel pipelines, thứ tự và luồng thực thi callback có thể khác dự đoán.

Nếu thực sự cần ghi audit **cho từng đơn hàng**, hãy dùng một bước xử lý có hợp đồng side-effect rõ ràng, quản lý lỗi/giao dịch và không dựa vào Stream optimization:

~~~java
for (Order order : orders) {
    auditService.record(order);
}
~~~

Ví dụ này chỉ minh họa hình thức điều khiển; `orders` và `auditService` là các đối tượng nghiệp vụ giả định. Cần triển khai retry, idempotency, transaction và xử lý lỗi theo yêu cầu ứng dụng, không phải chỉ thay một method gọi.

Đối với việc biến đổi dữ liệu thuần túy, ưu tiên các lambda **pure**: đầu ra phụ thuộc đầu vào, không thay đổi state bên ngoài.

## 13. Đóng Stream và vòng đời tài nguyên

Stream implement `AutoCloseable` (qua `BaseStream`), nhưng **terminal operation không tự gọi close()**. Đây là điểm quan trọng khi nguồn dựa trên file, socket hoặc resource bên ngoài.

### 13.1. Cách đúng với Files.lines

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class TextLoader {
    public static List<String> nonBlankLines(Path path)
            throws IOException {

        try (var stream = Files.lines(path, StandardCharsets.UTF_8)) {
            return stream
                    .map(String::strip)
                    .filter(s -> !s.isEmpty())
                    .toList();
        }
    }
}
~~~

`try-with-resources` đóng stream dù xử lý thành công hay xảy ra ngoại lệ. Dữ liệu đầu ra `List<String>` đã được materialize trong block nên có thể trả về an toàn sau khi file đóng.

Không trả trực tiếp `Files.lines(path)` từ một phương thức đã đóng stream ở bên trong:

~~~java
// Sai: trả một Stream đã đóng.
// static Stream<String> lines(Path path) throws IOException {
//     try (Stream<String> s = Files.lines(path)) {
//         return s;
//     }
// }
~~~

Nếu thiết kế API trả Stream để caller tiêu thụ, hợp đồng phải ghi rõ **caller sở hữu trách nhiệm đóng** và stream chỉ dùng một lần. Với API quy mô nhỏ, trả `List` đã materialize có thể dễ dùng hơn; với file lớn, cần cân đối bộ nhớ và vòng đời tài nguyên.

### 13.2. onClose

`BaseStream.onClose(Runnable)` đăng ký callback chạy khi `close()` được gọi, không phải khi terminal operation kết thúc:

~~~java
import java.util.stream.Stream;

try (Stream<String> stream = Stream.of("A", "B")
        .onClose(() -> System.out.println("closed"))) {
    System.out.println(stream.count()); // 2
}
// closed
~~~

Không dùng `onClose` như cách đảm bảo callback chạy “sau toList/count” trừ khi chắc chắn có đoạn code gọi `close()`.

### 13.3. Checked exception từ nguồn file

`Files.lines` có thể ném `IOException` tại lúc mở file. Ngoài ra, lỗi I/O khi tiếp tục đọc bên trong pipeline có thể xuất hiện dưới dạng `UncheckedIOException`. Khi xử lý file đầu vào có độ tin cậy thấp, cần tính đến lỗi cả **lúc tạo stream** và **trong lúc tiêu thụ stream**. Try-with-resources giải quyết đóng tài nguyên, không thay thế xử lý lỗi nghiệp vụ.

## 14. Sequential và parallel không thay đổi nguyên lý lazy

`Stream.parallel()` hoặc `Collection.parallelStream()` yêu cầu pipeline vận hành ở chế độ parallel. Nguồn và intermediate operations vẫn tạo pipeline lazy, và terminal operation vẫn khởi phát thực thi.

~~~java
import java.util.List;

long sum = List.of(1L, 2L, 3L, 4L).stream()
        .parallel()
        .mapToLong(Long::longValue)
        .sum();

System.out.println(sum); // 10
~~~

Điểm cần tránh:

- Không dựa vào thứ tự callback `map/filter/peek` giữa các luồng.
- Không cập nhật `ArrayList` hoặc biến đếm mutable bên ngoài từ một parallel stream.
- Một ordered source không biến `forEach` song song thành thao tác giữ thứ tự; dùng `forEachOrdered` khi thực sự cần.
- Stateful operations như `sorted` và `distinct` có thể đòi bộ đệm hoặc hợp nhất dữ liệu lớn.
- `parallel()` không bảo đảm nhanh hơn; tập dữ liệu nhỏ, blocking I/O và thứ tự chặt thường làm overhead lớn hơn lợi ích.

### 14.1. Reduction phù hợp hơn shared mutable state

Không nên viết:

~~~java
// Sai khi parallel: race condition
// long[] total = {0L};
// values.parallelStream().forEach(v -> total[0] += v);
~~~

Thay bằng reduction chuẩn:

~~~java
import java.util.List;

List<Long> values = List.of(10L, 20L, 30L);

long total = values.parallelStream()
        .mapToLong(Long::longValue)
        .sum();

System.out.println(total); // 60
~~~

Với phép reduce tùy chỉnh, phép kết hợp cần **associative** và có identity phù hợp để song song hóa đúng. Không tự động giả định các phép tính dấu phẩy động sẽ cho bit kết quả giống nhau trong mọi thứ tự cộng; sai số làm tròn phụ thuộc cách kết hợp.

## 15. Khi nào cần dùng collection thay vì Stream?

Stream phù hợp cho một chuỗi biến đổi/tổng hợp **một lần**, đặc biệt khi không cần điều khiển phần tử từng bước.

Collection hoặc vòng lặp truyền thống có thể phù hợp hơn khi:

- Cần duyệt lại dữ liệu nhiều lần hoặc truy cập phần tử theo chỉ số.
- Phải cập nhật collection nguồn có kiểm soát.
- Có logic state machine phức tạp, lỗi cần báo theo từng bước, hoặc nhiều tác động I/O phải phối hợp.
- Cần quản lý vòng đời tài nguyên ngoài luồng hoặc backpressure từ một hệ thống phản ứng.
- Cần mô hình hóa trạng thái giữa nhiều sự kiện theo thời gian, không chỉ xử lý một source stream.

**Java Stream không phải mạng truyền dữ liệu bất đồng bộ liên tục** giống các reactive streams; `Stream<T>` chủ yếu là abstraction cho aggregate operations và traversal, thường thực thi đồng bộ trên luồng gọi (hoặc fork/join song song tùy triển khai). Không dùng nó như thay thế mặc định cho `Flow.Publisher` hoặc một messaging system có backpressure.

## 16. Ví dụ tổng hợp: lọc và tính tổng đơn hàng

Yêu cầu: nhận danh sách đơn hàng có vùng và số tiền; chỉ lấy đơn hàng đã hoàn tất ở một vùng, sắp theo giá trị giảm dần rồi lấy tối đa ba ID để hiển thị.

~~~java
import java.util.Comparator;
import java.util.List;

record Purchase(
        String id,
        String region,
        long amount,
        boolean completed) {}

public class PurchaseReport {
    public static List<String> topCompletedIds(
            List<Purchase> purchases,
            String region,
            int limit) {

        if (limit < 0) {
            throw new IllegalArgumentException("limit must be >= 0");
        }

        return purchases.stream()                  // Source
                .filter(Purchase::completed)       // Stateless
                .filter(p -> p.region().equals(region)) // Stateless
                .sorted(Comparator.comparingLong(
                        Purchase::amount).reversed()) // Stateful
                .limit(limit)                      // Short-circuiting
                .map(Purchase::id)                 // Stateless
                .toList();                         // Terminal
    }

    public static void main(String[] args) {
        List<Purchase> purchases = List.of(
                new Purchase("A", "HN", 100, true),
                new Purchase("B", "HCM", 400, true),
                new Purchase("C", "HCM", 250, false),
                new Purchase("D", "HCM", 300, true),
                new Purchase("E", "HCM", 200, true)
        );

        System.out.println(topCompletedIds(purchases, "HCM", 2));
        // [B, D]
    }
}
~~~

Phân tích pipeline:

1. `purchases.stream()` tạo source từ list.
2. Hai `filter` loại các đơn hàng không đủ điều kiện.
3. `sorted` cần xem các ứng viên được giữ lại để biết thứ tự giảm dần.
4. `limit(limit)` giữ N ứng viên đầu **sau khi sắp xếp**.
5. `map` chuyển các record thành ID.
6. `toList()` thực thi pipeline và trả danh sách kết quả không cho sửa.

Đây là ví dụ dùng dữ liệu nhỏ và hữu hạn. Với dữ liệu rất lớn hoặc lưu trong database, có thể đẩy bộ lọc, sắp xếp và giới hạn về nơi lưu trữ bằng query/index thích hợp để tránh tải toàn bộ dữ liệu vào heap. Stream không tự động biến truy vấn trên một `List` thành truy vấn database.

### 16.1. Tối ưu hóa phải giữ nguyên nghĩa

Đưa `limit(2)` lên trước `sorted` có thể thay đổi top-2 vì nó chỉ sắp xếp hai phần tử đầu đã lọc, không còn xét tất cả đơn hàng thỏa điều kiện. Tối ưu hóa đúng cần xuất phát từ miền dữ liệu và kết quả phải giữ, không phải chỉ từ giảm số phần tử sớm.

## 17. Bảng những lỗi thường gặp

| Sai lầm | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| Gọi `filter/map` rồi mong lambda chạy ngay | Intermediate operations lazy | Thêm terminal operation khi cần kết quả |
| Xem Stream như List lưu phần tử | Stream mô tả pipeline, không lưu trữ như collection | Materialize bằng `toList`/`collect` khi cần |
| Gọi terminal hai lần trên cùng Stream | Pipeline chỉ được dùng một lần | Tạo Stream mới từ source hoặc supplier |
| Coi `peek` là audit bắt buộc | Optimizer/short-circuit có thể bỏ callback | Dùng tác vụ side-effect được quản lý riêng |
| Nghĩ `limit` luôn chỉ đọc đúng N phần tử nguồn | Filter/stateful stages trước nó có thể cần đọc nhiều hơn | Phân tích từng stage và vị trí `limit` |
| Đặt `sorted` trên nguồn vô hạn rồi mới `limit` | Không thể hoàn tất sắp xếp vô hạn | Đưa giới hạn lên trước nếu đúng nghiệp vụ, hoặc thay thuật toán |
| Sửa collection nguồn trong callback | Vi phạm non-interference | Dùng `removeIf` hoặc tạo collection kết quả mới |
| Dùng mảng counter mutable trong parallel stream | Data race và kết quả không xác định | Dùng reduction hoặc nguồn chỉ số |
| Dùng `findAny` rồi đòi phần tử đầu | `findAny` không cam kết encounter order | Dùng `findFirst` nếu cần đầu |
| Dùng `forEach` song song để in theo thứ tự | Callback có thể chạy khác thứ tự | Dùng `forEachOrdered` nếu cần |
| Quên đóng `Files.lines` | Rò rỉ file descriptor/channel | Dùng try-with-resources |
| Nghĩ terminal tự đóng Stream | Terminal tiêu thụ, không tự gọi `close()` | Đóng nguồn quản lý resource |
| Dùng `Stream.of(intArray)` như các giá trị int | Thường tạo Stream chứa một mảng | Dùng `Arrays.stream(intArray)` |
| Nghĩ `parallel()` luôn nhanh hơn | Chi phí chia tác vụ, state và order | Đo benchmark, chọn theo workload |
| Dựa vào kích thước source dù source bị sửa trong lúc duyệt | Stream không bảo đảm phản ứng giống collection snapshot | Giữ source ổn định hoặc dùng cơ chế concurrent rõ |

## 18. Checklist khi thiết kế Stream pipeline

- [ ] Đã xác định source là collection, array, generator, I/O hay nguồn tùy chỉnh.
- [ ] Đã biết source có finite/unbounded, ordered/unordered và mutable/immutable không.
- [ ] Đã phân biệt intermediate operations với terminal operations.
- [ ] Không dựa vào side-effect của callback để bảo đảm kết quả nghiệp vụ.
- [ ] Đã kiểm tra xem các bước stateful có cần giữ toàn bộ dữ liệu hay không.
- [ ] Đã xét khả năng short-circuit và điều kiện kết thúc nếu source vô hạn.
- [ ] Không thay thứ tự `sorted/limit/filter` nếu điều đó đổi ý nghĩa kết quả.
- [ ] Không vận hành lại Stream đã consumed hoặc closed.
- [ ] Nếu cần nhiều phép tính, tạo fresh stream từ source chứ không fork cùng một pipeline.
- [ ] Callback không sửa source và không phụ thuộc state mutable chia sẻ.
- [ ] Nếu dùng parallel, đã đánh giá thread safety, encounter order, reduction và overhead.
- [ ] Nếu stream đến từ I/O, đã dùng try-with-resources hoặc hợp đồng ownership rõ ràng.
- [ ] Đã phân biệt live source, lazy traversal và snapshot kết quả.
- [ ] Đã cân nhắc `IntStream/LongStream/DoubleStream` để tránh boxing và lưu ý tràn số.
- [ ] Đã xác định kết quả cần unmodifiable `toList()` hay mutable collection có chủ đích.
- [ ] Test có stream rỗng, một phần tử, dữ liệu lớn, source có thứ tự và các trường hợp có khả năng dừng sớm.

## 19. Tài liệu chính thức

- [Java SE 27 API — java.util.stream package](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/package-summary.html) — tổng quan nguồn, pipelines, lazy, stateful/stateless, short-circuit, non-interference.
- [Java SE 27 API — Stream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html) — tất cả intermediate/terminal operations, optimization, reuse, `toList`, `gather`.
- [Java SE 27 API — BaseStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/BaseStream.html) — `parallel`, `sequential`, `iterator`, `spliterator`, `onClose`, `close`.
- [Java SE 27 API — IntStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/IntStream.html) — primitive streams, `range`, `iterate`, `sum`.
- [Java SE 27 API — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html) — `lines`, `list`, `walk`, `find` và tài nguyên I/O.
- [Java SE 27 API — StreamSupport](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/StreamSupport.html) — tự tạo source từ Spliterator.
- [Java SE 27 API — Spliterator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Spliterator.html) — traversal/splitting và các source characteristics.
- [Java SE 27 API — Collectors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collectors.html) — các reduction/collector thông dụng.
- [Java SE 27 API — Gatherers](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherers.html) — các intermediate gatherer hiện hành.
- [JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485) — chuẩn hóa extension point cho intermediate operations từ JDK 24.

**Kết luận:** Trong Java 27, Stream là một **pipeline xử lý được kích hoạt khi tiêu thụ**, không phải một collection chứa dữ liệu. Cơ chế lazy giúp kết hợp các bước, tránh materialization không cần thiết và dừng sớm khi có thể; nhưng không bảo đảm mọi lambda được chạy, không loại bỏ chi phí stateful operations, không cho phép reuse và không tự đóng các nguồn I/O. Hiểu rõ **source → intermediate → terminal** là điều kiện để thiết kế pipeline vừa đúng nghĩa, vừa hiệu quả và an toàn.
