# `var` với các bước trung gian của Stream trong Java 10+

*Chủ đề cha: `var` và generics. Bài học trình bày cách suy luận kiểu tĩnh khi dùng `var` để giữ từng bước của Stream pipeline, cùng những quy tắc Stream còn áp dụng trong Java hiện đại. Tất cả chương trình hoàn chỉnh sử dụng JDK 17 trở lên.*

## 1. Sau bài học, bạn làm được gì?

Bạn sẽ biết cách:

1. Phân biệt **nguồn Stream**, **thao tác trung gian** (intermediate operation) và **thao tác kết thúc** (terminal operation).
2. Đọc kiểu tĩnh mà `var` suy luận ở mỗi bước, kể cả `Stream<T>`, `IntStream`, `Optional<T>` và `List<T>`.
3. Theo dõi cách tham số kiểu generic `T` biến đổi qua `filter`, `map`, `flatMap`, `sorted`, `distinct`.
4. Hiểu vì sao việc gán một bước trung gian vào `var` **không thực thi pipeline ngay**, và vì sao Stream chỉ dành cho một chuỗi xử lý.
5. Tránh suy luận sai `Object` khi initializer là generic factory thiếu ngữ cảnh; tránh nhầm stream trung gian với collection và các kết quả terminal.
6. Chọn lúc nên chia pipeline thành nhiều biến `var` để debug, lúc nên giữ chuỗi fluent và lúc nên ghi kiểu tường minh.

`var` được giới thiệu trong Java 10 cho **biến cục bộ có initializer**. Java vẫn là ngôn ngữ **kiểu tĩnh**: trình biên dịch xác định một kiểu cho biến; `var` không phải `dynamic`, không làm kiểu thay đổi theo phần tử đang chạy qua Stream và không thay đổi chữ ký API.

## 2. Stream pipeline và nơi `var` tham gia

Một pipeline thường có cấu trúc:

```text
Collection hoặc nguồn khác
    .stream()              -> Stream<T>
    .filter(predicate)     -> Stream<T>
    .map(function)         -> Stream<R>
    .flatMap(function)     -> Stream<R>
    .distinct() / .sorted() -> Stream<R>
    .toList() / .count() / .collect(...) -> Kết quả terminal
```

Ví dụ:

```java
var words = java.util.List.of("java", "stream", "api"); // List<String>
var source = words.stream();                           // Stream<String>
var filtered = source.filter(s -> s.length() > 3);     // Stream<String>
var lengths = filtered.map(String::length);            // Stream<Integer>
var output = lengths.toList();                         // List<Integer>
```

Mỗi biến có **kiểu tĩnh riêng** được suy ra từ giá trị trả về của phương thức ở bên phải. Dù đều dùng từ `var`, `source` và `output` **khác loại**: một bên là đối tượng Stream mô tả việc xử lý; một bên là List chứa kết quả đã được tạo ra bởi terminal operation.

Nhìn vào chữ ký quan trọng:

| API | Kiểu đầu vào, kiểu trả về | `var` nhận kiểu gì? |
| --- | --- | --- |
| `Collection<T>.stream()` | `Stream<T>` | `Stream<T>` |
| `Stream<T>.filter(Predicate<? super T>)` | `Stream<T>` | Vẫn `Stream<T>` |
| `Stream<T>.map(Function<? super T, ? extends R>)` | `Stream<R>` | Kiểu phần tử mới `R` |
| `Stream<T>.flatMap(Function<? super T, ? extends Stream<? extends R>>)` | `Stream<R>` | Stream đã làm phẳng |
| `Stream<T>.distinct()` | `Stream<T>` | Không đổi kiểu phần tử |
| `Stream<T>.sorted()` | `Stream<T>` | Không đổi kiểu phần tử |
| `Stream<T>.mapToInt(ToIntFunction<? super T>)` | `IntStream` | `IntStream`, không phải `Stream<Integer>` |
| `IntStream.boxed()` | `Stream<Integer>` | Quay lại Stream đối tượng |
| `Stream<T>.toList()` | `List<T>` | Danh sách kết quả |
| `Stream<T>.count()` | `long` | Kiểu primitive `long` |
| `Stream<T>.findFirst()` | `Optional<T>` | Một giá trị có thể vắng mặt |

Ở bảng trên, `T` là kiểu phần tử trước biến đổi; `R` là kiểu phần tử sau biến đổi. Dấu `? super` và `? extends` trong tham số generic thể hiện khả năng truyền các function/predicate tương thích; điều này được `javac` kiểm tra, không phải `var` tự quyết định.

**Quy tắc đọc kiểu:** nhìn **kiểu trả về của phương thức tại bước cuối biểu thức khởi tạo**, rồi đi ngược lại để xác định `T` hoặc `R`. Đừng chỉ nhìn tên biến hay giá trị in ra.

## 3. Chương trình hoàn chỉnh: giữ từng bước trung gian bằng `var`

Tạo tệp **`StreamStageDemo.java`**:

```java
import java.util.List;

public class StreamStageDemo {
    public static void main(String[] args) {
        var names = List.of("  An  ", "Binh", "An", "Chi", "Binh", " ");

        var source = names.stream();
        var trimmed = source.map(String::trim);
        var nonBlank = trimmed.filter(s -> !s.isBlank());
        var unique = nonBlank.distinct();
        var sorted = unique.sorted();
        var result = sorted.toList();

        System.out.println(result);
        System.out.println(names.size());

        var lengths = result.stream().mapToInt(String::length);
        System.out.println(lengths.sum());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac --release 17 StreamStageDemo.java
java StreamStageDemo
```

Stdout chính xác:

```text
[An, Binh, Chi]
6
9
```

### 3.1. Đọc từng kiểu đã được suy luận

| Biến | Kiểu tại thời điểm biên dịch | Lý do |
| --- | --- | --- |
| `names` | `List<String>` | `List.of(...)` có các phần tử `String` |
| `source` | `Stream<String>` | `stream()` lấy phần tử `String` của List |
| `trimmed` | `Stream<String>` | `String::trim` trả `String` |
| `nonBlank` | `Stream<String>` | `filter` chỉ chọn phần tử, không đổi kiểu |
| `unique` | `Stream<String>` | `distinct` chỉ bỏ trùng theo `equals` |
| `sorted` | `Stream<String>` | `sorted` chỉ sắp xếp, không đổi kiểu |
| `result` | `List<String>` | `Stream.toList()` là terminal operation |
| `lengths` | `IntStream` | `mapToInt` chuyển sang primitive stream |

Khi `result` được tạo, tên sau khi trim được lọc, bỏ trùng rồi sắp xếp thành `[An, Binh, Chi]`. Danh sách `names` ban đầu vẫn có **6 phần tử**; các thao tác Stream không tự sửa collection nguồn.

Ở phần sau, `mapToInt(String::length)` tạo `IntStream` chứa các độ dài `2`, `4`, `3`. `sum()` trả primitive `int` có giá trị `9`.

### 3.2. Tại sao tách các bước bằng `var` vẫn đúng?

Hai cách viết sau mô tả cùng pipeline, nếu nguồn và các function giống nhau.

**Gộp thành fluent chain:**

```java
// Đoạn minh họa bên trong một phương thức có biến names:
var result = names.stream()
        .map(String::trim)
        .filter(s -> !s.isBlank())
        .distinct()
        .sorted()
        .toList();
```

**Đặt tên cho các bước** như trong chương trình hoàn chỉnh:

```java
var source = names.stream();
var trimmed = source.map(String::trim);
var nonBlank = trimmed.filter(s -> !s.isBlank());
var unique = nonBlank.distinct();
var sorted = unique.sorted();
var result = sorted.toList();
```

Tách bước hữu ích khi:

- Muốn **kiểm tra kiểu** tại ranh giới `map`/`flatMap`/`mapToInt`.
- Đặt tên để làm rõ ý nghĩa dữ liệu, chẳng hạn `nonBlank`, `unique`.
- Một lỗi generic xuất hiện ở bước nào đó và cần thu hẹp vị trí.
- Muốn giải thích pipeline trong tài liệu hoặc khi học.

Pipeline ngắn, rõ nghĩa có thể giữ dạng chain để tránh quá nhiều biến cục bộ. Dù viết kiểu nào, **mỗi Stream đã tham gia một pipeline không được đem đi sử dụng lại để tạo pipeline thứ hai**. Chi tiết này đặc biệt dễ bị bỏ qua khi bạn giữ nhiều biến `var` trỏ đến các stage.

## 4. Phân biệt các thao tác trung gian theo ảnh hưởng tới kiểu

### 4.1. `filter`, `distinct`, `sorted` và `limit` giữ nguyên `T`

```java
// Các đoạn trong method:
var source = List.of(5, 2, 5, 8, 1).stream(); // Stream<Integer>
var filtered = source.filter(n -> n > 2);     // Stream<Integer>
var unique = filtered.distinct();            // Stream<Integer>
var sorted = unique.sorted();                // Stream<Integer>
var limited = sorted.limit(2);               // Stream<Integer>
var result = limited.toList();               // List<Integer>
```

`filter` chỉ quyết định giữ hay bỏ phần tử. `distinct` so sánh trùng theo `equals`. `sorted` giữ kiểu `Integer` (kiểu phải có quy tắc so sánh hợp lệ); `limit` chỉ giới hạn số phần tử. Không có bước nào tạo một kiểu phần tử `R` mới.

Với `skip`, `takeWhile`, `dropWhile` cũng không đổi kiểu phần tử; thứ tự và điều kiện dừng ảnh hưởng tới kết quả, không ảnh hưởng đến kiểu trả về chung `Stream<T>`.

### 4.2. `map` thay `T` thành `R`

```java
var texts = List.of("one", "two").stream();  // Stream<String>
var lengths = texts.map(String::length);    // Stream<Integer>
var values = lengths.toList();              // List<Integer>
```

`String::length` có kết quả `int`, nhưng `Stream.map` là generic object Stream, nên kết quả `int` được boxing thành `Integer`. Vì vậy `lengths` là `Stream<Integer>`, còn `values` là `List<Integer>`.

`map` không bắt buộc kiểu thay đổi. Ví dụ `.map(String::toUpperCase)` vẫn cho `Stream<String>`. Kiểu `R` phụ thuộc kiểu trả về của lambda/method reference.

Một ví dụ khác:

```java
var labels = List.of("a", "bbb").stream()
        .map(s -> s.length() > 1); // Stream<Boolean>
```

Boolean primitive từ biểu thức so sánh được boxing thành `Boolean` trong object Stream.

### 4.3. `mapToInt`, `mapToLong`, `mapToDouble` tạo primitive stream

Thay vì `Stream<Integer>`, bạn có thể dùng primitive Stream:

```java
var lengths = List.of("a", "bbb").stream()
        .mapToInt(String::length);       // IntStream
var total = lengths.sum();             // int
```

`IntStream` hỗ trợ `sum`, `average`, `summaryStatistics`, `min`, `max` theo dữ liệu primitive mà không yêu cầu boxing mỗi phần tử như `Stream<Integer>`. `average()` trả `OptionalDouble` để biểu diễn trường hợp stream rỗng.

Chuyển đổi giữa primitive và object stream:

```java
var numbers = java.util.stream.IntStream.rangeClosed(1, 3); // IntStream
var boxed = numbers.boxed();                                // Stream<Integer>
var list = boxed.toList();                                  // List<Integer>
```

**Không có `IntStream.toList()`** theo API Java 17: nếu cần `List<Integer>`, dùng `boxed().toList()` hoặc collector thích hợp; nếu cần mảng primitive, `IntStream.toArray()` trả `int[]`. Đừng suy ra kiểu theo tên `numbers` hay `list`, hãy đọc chính xác kiểu trả về của terminal operation.

### 4.4. `flatMap` thay đổi kiểu và làm phẳng cấu trúc

Xét `List<List<String>>`:

```java
var groups = List.of(
        List.of("java", "stream"),
        List.of("var", "java")
); // List<List<String>>

var outer = groups.stream();               // Stream<List<String>>
var flat = outer.flatMap(List::stream);     // Stream<String>
var unique = flat.distinct();              // Stream<String>
var result = unique.sorted().toList();     // List<String>
```

`flatMap` nhận mỗi `List<String>` rồi tạo một `Stream<String>`; nó nối các stream con thành một pipeline phẳng. Nếu dùng `map(List::stream)` thay thế, kết quả sẽ là `Stream<Stream<String>>`, **chưa được làm phẳng**.

Khi kết hợp `var` với `flatMap`, cần đọc đúng lambda trả về **Stream của loại phần tử nào**; đây là nguồn lỗi generic thường gặp. IDE hover trên biến `flat` giúp xác định có vô tình giữ kiểu lồng nhau không.

### 4.5. Một số thao tác đổi kiểu gián tiếp

- `mapMulti` (có trong Java hiện đại từ Java 16) có thể tạo 0, 1 hoặc nhiều phần tử đầu ra từ mỗi phần tử đầu vào. Chữ ký mang tham số kết quả `R` nên cần chú ý type inference, đặc biệt khi method chain thiếu ngữ cảnh; viết kiểu đích tường minh hoặc gợi ý tham số generic nếu cần.
- `Stream.ofNullable(value)` tạo Stream gồm 0 hoặc 1 phần tử. Nếu chỉ truyền literal `null` mà không có ngữ cảnh kiểu, `var s = Stream.ofNullable(null);` thường suy ra `Stream<Object>`; muốn `Stream<String>`, viết `Stream.<String>ofNullable(null)` hoặc khai báo đích tường minh.
- `Stream.empty()` với `var` và không có kiểu đích thường là `Stream<Object>`. Khi cần phần tử `String`, dùng `Stream.<String>empty()` hoặc `Stream<String> s = Stream.empty();`.

## 5. Tính lazy: gán stage vào `var` chưa duyệt phần tử

Các thao tác trung gian như `filter`, `map`, `flatMap`, `sorted` chủ yếu **xây dựng pipeline**. Việc xử lý phần tử được kích hoạt khi terminal operation yêu cầu kết quả, chẳng hạn `toList`, `sum`, `count`, `findFirst`.

Tạo tệp **`LazyPipelineDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class LazyPipelineDemo {
    public static void main(String[] args) {
        var observed = new AtomicInteger();

        var pipeline = List.of(1, 2, 3, 4, 5).stream()
                .filter(n -> {
                    observed.incrementAndGet();
                    return n % 2 == 0;
                })
                .map(n -> n * 10);

        System.out.println("before=" + observed.get());

        var result = pipeline.toList();

        System.out.println("result=" + result);
        System.out.println("after=" + observed.get());
    }
}
```

Chạy:

```bash
javac --release 17 LazyPipelineDemo.java
java LazyPipelineDemo
```

Stdout chính xác của chương trình tuần tự này:

```text
before=0
result=[20, 40]
after=5
```

Ở thời điểm gán `pipeline`, filter chưa được duyệt nên bộ đếm là `0`. Sau `toList()`, các phần tử đã được thử qua `filter` và kết quả là `[20, 40]`. Ví dụ dùng `AtomicInteger` **chỉ để minh họa thời điểm xử lý**; code nghiệp vụ nên ưu tiên lambda không có tác dụng phụ và lấy dữ liệu qua terminal operation.

**Không lấy ví dụ này làm lý do thiết kế pipeline dựa trên side effect.** Stream có thể tối ưu một số thao tác, rút ngắn quá trình đánh giá hoặc thực thi song song. Đặc biệt, một số terminal operation như `count()` có thể suy ra số phần tử từ kích thước nguồn và bỏ qua bước `peek` hoặc `map` không cần thiết. Side effect trong `peek`/`map`/`filter` không phải cơ chế theo dõi công việc đáng tin cậy cho mọi pipeline.

### 5.1. Short-circuit

`findFirst`, `anyMatch`, `allMatch`, `noneMatch` và `limit` có thể giúp pipeline ngừng sớm tùy nguồn, thứ tự và điều kiện. Ví dụ:

```java
var firstEven = List.of(1, 3, 4, 6).stream()
        .filter(n -> n % 2 == 0)
        .findFirst(); // Optional<Integer> chứa 4
```

Hệ thống không bắt buộc xử lý toàn bộ phần tử để tìm thấy `4`. Vì vậy không thiết kế logic kiểu “mỗi phần tử nhất định sẽ đi qua `map`” nếu terminal operation có thể dừng sớm.

### 5.2. Stream chỉ dùng cho một pipeline

Ví dụ **cố ý sai**:

```java
var source = List.of("a", "b").stream();
var upper = source.map(String::toUpperCase);
var output = upper.toList();      // [A, B]
// source.count();                // Không hợp lệ: source đã tham gia pipeline
// upper.findFirst();             // Không hợp lệ: pipeline đã kết thúc
```

Theo hợp đồng Stream, một stream không được vận hành lại sau khi đã có thao tác trung gian/terminal trước đó; nhiều JVM sẽ báo `IllegalStateException` nếu cố dùng lại. Không nên phụ thuộc việc implementation nào phát hiện được mọi kiểu tái sử dụng.

Muốn tạo kết quả khác, gọi `.stream()` **lần nữa trên nguồn dữ liệu**:

```java
var values = List.of("a", "b");
var uppercase = values.stream().map(String::toUpperCase).toList();
var count = values.stream().count(); // 2L
```

`uppercase` là `List<String>`; `count` là primitive `long`. Hai Stream là hai pipeline độc lập dù cùng dùng một collection.

## 6. Ví dụ generics và `flatMap` với dữ liệu có cấu trúc

Tạo tệp **`FlatMapStageDemo.java`**:

```java
import java.util.List;

public class FlatMapStageDemo {
    record Project(String name, List<String> labels) {}

    public static void main(String[] args) {
        var projects = List.of(
                new Project("Core", List.of("java", "api")),
                new Project("Portal", List.of("ui", "java"))
        );

        var tags = projects.stream()
                .flatMap(p -> p.labels().stream());

        var selected = tags.distinct().sorted().toList();

        var projectNames = projects.stream()
                .map(Project::name)
                .sorted()
                .toList();

        var labelCount = projects.stream()
                .flatMap(p -> p.labels().stream())
                .count();

        System.out.println(selected);
        System.out.println(projectNames);
        System.out.println(labelCount);
    }
}
```

Chạy:

```bash
javac --release 17 FlatMapStageDemo.java
java FlatMapStageDemo
```

Stdout:

```text
[api, java, ui]
[Core, Portal]
4
```

Ở đây:

1. `projects` có kiểu `List<Project>` (record `Project` được hỗ trợ chính thức từ Java 16).
2. `projects.stream()` có kiểu `Stream<Project>`.
3. `p.labels()` trả `List<String>`; `p.labels().stream()` là `Stream<String>`.
4. `flatMap(...)` vì vậy trả `Stream<String>`, nên `tags` không còn là `Stream<Project>`.
5. `selected` là `List<String>`, gồm 3 nhãn duy nhất sau `distinct()`/`sorted()`.
6. `projectNames` là `List<String>` vì `Project::name` trả `String`.
7. `labelCount` là `long` và có giá trị `4` vì đếm **tổng số nhãn trước khi loại trùng**.

Có thể nhận ra `var` giúp tránh phải viết tay các kiểu trung gian phức tạp, nhưng cũng dễ khiến người đọc bỏ qua một bước đổi kiểu. Khi khó theo dõi, hãy dùng hover trong IDE để xem chữ ký generic và ghi chú kiểu ở nơi thực sự cần.

## 7. Bẫy suy luận kiểu: `var` không cung cấp ngữ cảnh đích

### 7.1. Generic factory với kiểu phần tử không rõ

`var` yêu cầu kiểu được suy ra từ **initializer**, còn kiểu tường minh ở bên trái có thể cung cấp ngữ cảnh cho generic method/constructor.

```java
// Các đoạn minh họa trong phương thức:
var loose = java.util.stream.Stream.empty();       // Stream<Object>
var typed = java.util.stream.Stream.<String>empty(); // Stream<String>
java.util.stream.Stream<String> declared =
        java.util.stream.Stream.empty();            // Stream<String>
```

Không có phần tử nào, nên `Stream.empty()` khi dùng với `var` không có ràng buộc hẹp hơn và suy ra `Object`. Đây là **vấn đề generic inference**, không có nghĩa `var` tự động chọn kiểu `Object` cho mọi biểu thức. `var text = "x";` vẫn là `String` và `var one = List.of("x");` vẫn là `List<String>`.

Một bẫy tương tự:

```java
var rawLooking = new java.util.ArrayList<>();        // ArrayList<Object>
var typedList = new java.util.ArrayList<String>(); // ArrayList<String>
java.util.List<String> asList = new java.util.ArrayList<>();
```

`rawLooking` không phải raw type `ArrayList`; nó vẫn là **`ArrayList<Object>`**. Nhưng kiểu phần tử rộng có thể khiến việc gán vào `String` lỗi biên dịch về sau.

### 7.2. Kiểu suy luận của kết quả terminal không phải của Stream

| Biểu thức initializer | Kiểu của `var` | Ghi chú |
| --- | --- | --- |
| `List.of("a").stream()` | `Stream<String>` | Nguồn stream |
| `List.of("a").stream().map(String::length)` | `Stream<Integer>` | Bước trung gian object map |
| `List.of("a").stream().mapToInt(String::length)` | `IntStream` | Bước trung gian primitive |
| `List.of("a").stream().map(String::length).toList()` | `List<Integer>` | Kết quả terminal không sửa được |
| `List.of("a").stream().count()` | `long` | Đếm phần tử |
| `List.of("a").stream().findFirst()` | `Optional<String>` | Có thể có/không có giá trị |
| `List.of("a").stream().mapToInt(String::length).sum()` | `int` | Kết quả tổng primitive |
| `List.of("a").stream().mapToInt(String::length).average()` | `OptionalDouble` | Vắng mặt khi IntStream rỗng |

Nếu IDE hiện `var` nhưng code gọi phương thức như `.sum()` không được, hãy xem biến thực ra là `Stream<Integer>` hay `IntStream`. Hai kiểu có API khác nhau, dù cùng liên quan đến số nguyên.

### 7.3. `map` và `flatMap`: nhìn generic trước khi đoán kết quả

```java
var teams = List.of(List.of("A", "B"), List.of("C"));

var nested = teams.stream().map(List::stream);
// nested: Stream<Stream<String>>

var flat = teams.stream().flatMap(List::stream);
// flat: Stream<String>
```

Không thể lấy trực tiếp `List<String>` từ `nested.toList()`, vì kết quả đó là `List<Stream<String>>`. Nếu muốn một danh sách tên phẳng, dùng `flatMap` trước `toList`. Đây là ví dụ điển hình để đặt một biến `var` ở ranh giới nghi ngờ và hover kiểm tra type.

## 8. `toList`, `collect` và khả năng sửa kết quả

Từ Java 16, `Stream.toList()` trả một **List không thể sửa** qua `add`, `remove` hoặc `set`; gọi các thao tác sửa sẽ ném `UnsupportedOperationException`. Điều này **không** đồng nghĩa mọi đối tượng phần tử trong danh sách đều bất biến.

```java
var immutableResult = List.of("a", "b").stream()
        .map(String::toUpperCase)
        .toList();  // List<String> không cho sửa

var mutableResult = List.of("a", "b").stream()
        .map(String::toUpperCase)
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new)); // ArrayList<String> có thể sửa

mutableResult.add("C"); // Hợp lệ
```

Nếu dùng `collect(Collectors.toList())`, hợp đồng API không đảm bảo cụ thể danh sách trả về luôn mutable hay thuộc lớp nào. Muốn mutable thì chọn `toCollection(ArrayList::new)`. Với `Stream.toList()`, biết chắc không sửa được thông qua API List.

Một chi tiết dễ nhầm: `Stream.toList()` có thể chứa phần tử `null` nếu pipeline tạo ra chúng, trong khi `List.of(...)` không chấp nhận phần tử `null`. Đây là quy tắc của API tạo collection, không phải của `var`.

## 9. Cách gỡ lỗi khi pipeline có nhiều kiểu trung gian

Giả sử code có lỗi biên dịch:

```java
// Ví dụ cố ý sai nếu bỏ chú thích:
var lengths = List.of("a", "bb").stream()
        .map(String::length); // Stream<Integer>
// int total = lengths.sum(); // Sai: Stream<Integer> không có sum()
```

Có hai cách sửa theo ý định:

```java
// Cách 1: dùng primitive IntStream ngay từ đầu
var ints = List.of("a", "bb").stream()
        .mapToInt(String::length);
int total1 = ints.sum(); // 3

// Cách 2: nếu đã là Stream<Integer>, chuyển sang IntStream mới
var boxedLengths = List.of("a", "bb").stream()
        .map(String::length);
int total2 = boxedLengths.mapToInt(Integer::intValue).sum(); // 3
```

Khi lỗi liên quan Stream và `var`, làm theo thứ tự:

1. **Hover từng biến** và xem kiểu IDE suy ra, đặc biệt trước/sau `map`, `flatMap`, `mapToInt` và terminal operation.
2. **Đọc chữ ký phương thức:** với `map`, lambda trả `R` nào; với `flatMap`, lambda tạo `Stream<R>` nào; với primitive stream, API trả kiểu gì?
3. **Đánh giá initializer có ngữ cảnh generic hay không.** `Stream.empty()`, `new ArrayList<>()` không có phần tử/kiểu đích có thể suy ra `Object`.
4. **Biên dịch lại đúng language level** của dự án; dùng `javac --release 17 File.java` cho các ví dụ và `-Xdiags:verbose` khi cần đọc lỗi generic rõ hơn.
5. **Không cố tái sử dụng Stream** sau khi một bước khác đã vận hành trên nó; tạo Stream mới từ nguồn nếu cần xử lý lần hai.
6. **Kiểm tra terminal operation.** `toList` trả `List<T>`, `count` trả `long`, `findFirst` trả `Optional<T>`; chúng không giữ kiểu `Stream<T>`.
7. **Chọn cách diễn đạt tốt nhất:** chain để giữ mạch dễ đọc; tách `var` khi có bước nghiệp vụ cần tên hoặc cần xác định kiểu; khai báo kiểu tường minh khi cần nhấn mạnh API contract.

Không cần đổi toàn bộ `var` thành các khai báo dài mới xử lý được lỗi. Vấn đề thực tế thường nằm ở kiểu phần tử đầu vào, chữ ký generic, sai loại Stream hoặc tái sử dụng pipeline.

## 10. Một số lưu ý về hiệu năng, xử lý song song và tài nguyên

### 10.1. `var` không tối ưu Stream thay bạn

`var` là cú pháp giúp trình biên dịch suy luận kiểu cục bộ. Nó **không** thay đổi bản chất lazy của Stream, số lần boxing hay cơ chế xử lý song song.

- `Stream<Integer>` và `IntStream` khác nhau: nếu xử lý số nhiều lần, primitive stream có thể giảm boxing và cung cấp phép tổng hợp phù hợp. Hãy đo thực tế trước khi khẳng định nhanh hơn.
- `parallel()` tạo đường thực thi song song; không mặc nhiên tăng hiệu năng và có chi phí chia/ghép công việc. Với dữ liệu nhỏ, công việc nhẹ hoặc phép biến đổi có side effect, kết quả có thể chậm hơn hoặc sai do race condition.
- Dùng `forEachOrdered` nếu thực sự cần thứ tự quan sát trên pipeline có encounter order; `forEach` của parallel stream không đảm bảo thứ tự đó.
- Đừng thay phép tổng hợp bằng biến ngoài kiểu `int[] sum = {0};` rồi sửa trong lambda. Với parallel stream, đây là nguy cơ race và phá ý định khai báo của Stream; dùng `sum`, `reduce` hoặc collector thích hợp.
- Một số thao tác trung gian `stateful`, như `sorted` và `distinct`, có thể cần lưu/điều phối thêm dữ liệu; `limit`, `skip` ảnh hưởng đến lượng công việc. Không tối ưu chỉ dựa vào số biến `var`.

### 10.2. Stream gắn với tài nguyên phải được đóng

Stream từ `List.stream()` không sở hữu I/O cần đóng trong ví dụ trên. Ngược lại, Stream từ `Files.lines(path)` có tài nguyên file liên quan; nên dùng try-with-resources:

```java
// Đoạn minh họa trong method khai báo IOException;
 // path là biến java.nio.file.Path có sẵn:
try (var lines = java.nio.file.Files.lines(path)) {
    var cleaned = lines.map(String::strip)
            .filter(s -> !s.isBlank())
            .toList();
    System.out.println(cleaned.size());
}
```

Ở đây `lines` được suy luận là `Stream<String>` và được đóng khi ra khỏi khối try. `cleaned` là `List<String>` đã được materialize trước lúc Stream đóng. Đây là đoạn minh họa có phụ thuộc `path`; không phải chương trình tự chạy độc lập.

## 11. Những nhầm lẫn cần tránh

| Nhầm lẫn | Thực tế |
| --- | --- |
| “`var stream = list.stream().filter(...)` đã lọc toàn bộ list.” | `filter` là trung gian, thường lazy; terminal mới yêu cầu duyệt dữ liệu. |
| “Sau `filter`, biến tự đổi sang kiểu phần tử cụ thể hơn.” | `filter` trả `Stream<T>`, không đổi kiểu generic chỉ vì predicate kiểm tra giá trị. |
| “`map(String::length)` cho `IntStream`.” | `map` cho `Stream<Integer>`; muốn primitive dùng `mapToInt`. |
| “`map(List::stream)` làm phẳng danh sách lồng nhau.” | `map` tạo `Stream<Stream<T>>`; dùng `flatMap` để làm phẳng. |
| “Có thể dùng lại `source` sau khi tạo `mapped = source.map(...)`.” | Một Stream chỉ thuộc một pipeline; tạo Stream mới từ nguồn nếu cần nhánh khác. |
| “`var` là dynamic nên mỗi bước có thể đổi kiểu tùy phần tử.” | Mỗi biến `var` có đúng một kiểu tĩnh được biên dịch xác định. |
| “`Stream.empty()` với `var` sẽ suy luận kiểu mình mong muốn.” | Thiếu ngữ cảnh generic, có thể suy ra `Object`; ghi kiểu đích/generic rõ ràng. |
| “`toList()` trả Stream hoặc List mutable.” | `toList()` trả List không cho sửa theo hợp đồng hiện đại. |
| “`parallelStream()` luôn nhanh và an toàn.” | Cần kiểm tra phép toán, shared state, thứ tự và đo hiệu năng. |
| “`peek` luôn chạy đúng một lần trên mọi phần tử.” | Không nên dựa vào side effect ở `peek`; pipeline có thể tối ưu hoặc dừng sớm. |

## 12. Bài tập có đáp án

**Bài 1 — Đọc kiểu từng bước.** Xem code:

```java
var a = List.of("a", "abcd").stream();
var b = a.filter(s -> s.length() > 1);
var c = b.map(String::length);
var d = c.toList();
```

Hãy xác định kiểu của từng biến.

**Đáp án:** `a` là `Stream<String>`, `b` là `Stream<String>`, `c` là `Stream<Integer>`, `d` là `List<Integer>` và có giá trị `[4]`. `filter` không đổi kiểu; `map` đổi kiểu phần tử; `toList` kết thúc pipeline.

**Bài 2 — Tổng độ dài.** Vì sao mã này không biên dịch ở dòng `sum`?

```java
var lengths = List.of("abc", "de").stream()
        .map(String::length);
// var total = lengths.sum();
```

**Đáp án:** `lengths` là `Stream<Integer>` nên không có `sum()`. Viết `mapToInt(String::length).sum()` trên Stream mới để nhận primitive `int` có giá trị `5`, hoặc chuyển `lengths.mapToInt(Integer::intValue).sum()` trong cùng pipeline.

**Bài 3 — Đếm có loại trùng.** Với:

```java
var result = List.of("b", "a", "b").stream()
        .distinct()
        .sorted()
        .toList();
```

Kết quả và kiểu là gì?

**Đáp án:** `result` là `List<String>` với giá trị `[a, b]`. `distinct` không thay generic `String`; `sorted` sắp xếp; `toList` tạo danh sách kết quả không cho sửa.

**Bài 4 — Stream có dùng hai lần được không?**

```java
var stream = List.of(1, 2, 3).stream();
var mapped = stream.map(n -> n * 2);
var first = mapped.findFirst();
// var count = mapped.count();
```

**Đáp án:** Dòng `mapped.count()` là sai cách sử dụng: `mapped` đã được terminal `findFirst()` tiêu thụ. Nếu muốn đếm, tạo Stream mới từ `List`. `first` là `Optional<Integer>` chứa `2`.

**Bài 5 — Xác định đầu ra `flatMap`.**

```java
var nested = List.of(List.of(1, 2), List.of(3));
var flatten = nested.stream().flatMap(List::stream);
var sum = flatten.mapToInt(Integer::intValue).sum();
```

**Đáp án:** `flatten` có kiểu `Stream<Integer>`; `sum` là `int` bằng `6`. `flatMap` làm phẳng từ `Stream<List<Integer>>` về `Stream<Integer>`.

**Bài 6 — Nhận diện suy luận `Object`.** Vì sao `var items = Stream.empty();` không nhất thiết là `Stream<String>`?

**Đáp án:** không có phần tử và không có kiểu đích `String` trong ngữ cảnh `var`, nên `T` được suy luận là `Object`. Nếu cần `String`, dùng `var items = Stream.<String>empty();` hoặc `Stream<String> items = Stream.empty();`.

## 13. Tổng kết cách tư duy

Khi đọc `var` trong pipeline Stream, hãy theo dõi **kiểu dữ liệu chảy qua từng bước**, không chỉ kết quả cuối:

- Bắt đầu từ nguồn: `Collection<T>.stream()` tạo `Stream<T>`.
- Một số bước chỉ chọn/sắp xếp mà giữ `T`: `filter`, `distinct`, `sorted`, `limit`.
- Một số bước thay kiểu: `map` và `flatMap` chuyển thành `Stream<R>`; `mapToInt` chuyển sang `IntStream`.
- Bước terminal chuyển từ mô tả xử lý thành kết quả: `toList`, `count`, `sum`, `findFirst` hoặc `collect`.
- Tất cả kiểu nói trên đều được xác định **lúc biên dịch**, dù thao tác trên phần tử thường chỉ được đánh giá khi terminal chạy.
- Mỗi Stream thuộc một pipeline; muốn dùng lại dữ liệu, lấy Stream mới từ nguồn và cân nhắc cách xử lý tài nguyên.

Với các nguyên tắc đó, `var` giúp code Stream ngắn gọn và vẫn rõ kiểu. Khi pipeline phức tạp, đặt tên trung gian có ý nghĩa, đọc chữ ký API và xác nhận bằng IDE/`javac` sẽ giúp giữ trọn tính an toàn kiểu của Java.