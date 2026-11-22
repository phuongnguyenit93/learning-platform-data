# Encounter order và các bảo đảm về thứ tự

Trong Java Stream API, một pipeline có thể xử lý phần tử theo cách tuần tự hoặc song song, nhưng **thứ tự xử lý trên các luồng thực thi** và **thứ tự phần tử mà kết quả phải tuân theo** là hai vấn đề khác nhau. Hiểu rõ *encounter order* (thứ tự gặp phần tử) giúp dùng `filter`, `map`, `sorted`, `distinct`, `limit`, `collect` và các terminal operation đúng hợp đồng, nhất là khi bật `parallel()`.

Bài này thuộc chương **Hợp đồng và vòng đời pipeline** của module **JAVA_STREAM_API**. Trọng tâm là cách xử lý dữ liệu theo lối khai báo mà vẫn xác định được khi nào thứ tự được bảo đảm, khi nào thứ tự có thể thay đổi và cái giá hiệu năng của việc duy trì thứ tự.

## 1. Encounter order là gì?

**Encounter order** là thứ tự logic mà các phần tử được *gặp* trong một stream, nếu stream đó có thứ tự được định nghĩa. Thứ tự này thường đến từ nguồn dữ liệu, nhưng một thao tác trung gian như `sorted()` cũng có thể thiết lập nó.

Ví dụ:

```java
List<String> names = List.of("Lan", "Minh", "An");

List<String> result = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [LAN, MINH]
```

Nguồn `List` có encounter order là `Lan → Minh → An`. Hai phép biến đổi `filter` và `map` giữ thứ tự tương đối của những phần tử còn lại; `toList()` tạo danh sách theo encounter order đó.

Điều quan trọng là phải phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Encounter order** | Thứ tự logic của các phần tử trong stream | `List.of(3, 1, 2).stream()` có thứ tự `3, 1, 2` |
| **Thứ tự thực thi** | Thứ tự các tác vụ chạy hoặc hoàn tất trên các thread | `parallelStream()` có thể xử lý `2` trước `3` |
| **Thứ tự kết quả** | Thứ tự mà terminal operation cam kết thể hiện | `parallelStream().toList()` vẫn trả `[3, 1, 2]` với nguồn trên |

**Có encounter order không đồng nghĩa stream đã được sắp xếp.** Danh sách `[3, 1, 2]` có encounter order hoàn toàn xác định, dù không tăng dần.

## 2. Nguồn nào có thứ tự?

Thứ tự là một phần của hợp đồng nguồn và pipeline, không thể suy ra chỉ từ việc dữ liệu “trông có vẻ ổn định” khi chạy thử.

| Nguồn stream | Encounter order | Ghi chú |
|---|---|---|
| `List`, mảng, `Arrays.stream(...)` | Có | Theo vị trí phần tử |
| `LinkedHashSet` | Có | Theo thứ tự chèn (trừ khi đã xóa/chèn lại) |
| `TreeSet` | Có | Theo thứ tự của `Comparator` hoặc thứ tự tự nhiên |
| `HashSet`, `HashMap.entrySet().stream()` | Không bảo đảm | Không phụ thuộc vào thứ tự thấy được khi duyệt một lần |
| `IntStream.range(0, n)` | Có | Theo thứ tự tăng dần |
| `Stream.iterate(...)` | Có | Theo chuỗi sinh phần tử |
| `Stream.generate(...)` | Không | Các phần tử được sinh không có thứ tự gặp được định nghĩa |

Ở tầng thấp hơn, `Spliterator.ORDERED` biểu thị nguồn có thứ tự gặp được định nghĩa; `Spliterator.SORTED` cung cấp thêm thông tin về thứ tự sắp xếp. Một pipeline còn có thể thay đổi ràng buộc thứ tự qua `sorted()` hoặc `unordered()`.

```java
System.out.println(
        List.of(8, 3, 5).stream().toList()
); // [8, 3, 5] — có thứ tự, chưa sắp xếp

System.out.println(
        List.of(8, 3, 5).stream().sorted().toList()
); // [3, 5, 8] — đã sắp xếp
```

Với `HashSet`, nếu một lần chạy tình cờ cho ra cùng thứ tự nhiều lần, điều đó **không tạo thành bảo đảm**. Khi cần thứ tự chèn, dùng `LinkedHashSet`; khi cần thứ tự so sánh, dùng `TreeSet` hoặc sắp xếp rõ ràng trong pipeline.

## 3. Thao tác trung gian tác động đến thứ tự như thế nào?

Phần lớn thao tác trung gian là *lazy*: chúng mô tả pipeline và chỉ được thực thi khi terminal operation yêu cầu dữ liệu. Tuy nhiên, mỗi thao tác có hợp đồng riêng về encounter order.

| Thao tác | Bảo đảm quan trọng với stream có thứ tự |
|---|---|
| `filter(predicate)` | Giữ thứ tự tương đối của các phần tử được giữ lại |
| `map(mapper)` | Giữ vị trí tương đối khi chuyển đổi từng phần tử |
| `sorted()`, `sorted(comparator)` | Tạo encounter order theo thứ tự sắp xếp; ổn định (*stable*) khi đầu vào có thứ tự |
| `distinct()` | Với đầu vào có thứ tự, giữ lần xuất hiện đầu tiên của mỗi giá trị khác nhau theo `equals` |
| `limit(n)` | Chọn tối đa `n` phần tử đầu tiên |
| `skip(n)` | Bỏ qua `n` phần tử đầu tiên |
| `takeWhile(predicate)` | Lấy đoạn đầu liên tiếp dài nhất còn thỏa điều kiện |
| `dropWhile(predicate)` | Bỏ đoạn đầu liên tiếp dài nhất còn thỏa điều kiện |
| `unordered()` | Gỡ ràng buộc encounter order ở phần pipeline tiếp theo |
| `parallel()`, `sequential()` | Chọn chế độ thực thi; tự chúng không xóa hoặc tạo encounter order |

### 3.1. `sorted()` tạo ra thứ tự, kể cả khi nguồn ban đầu không có thứ tự

```java
List<Integer> lowest = List.of(7, 3, 5, 1, 9, 2)
        .parallelStream()
        .sorted()
        .limit(3)
        .toList();

System.out.println(lowest); // [1, 2, 3]
```

Ở đây `sorted()` xác lập thứ tự tăng dần trước khi `limit(3)` chọn ba phần tử đầu. Thứ tự được bảo đảm dù pipeline chạy song song.

Với comparator cho phép hai phần tử bằng nhau về thứ tự sắp xếp, `sorted` **ổn định nếu đầu vào có thứ tự**: các phần tử được coi là bằng nhau bởi comparator giữ nguyên thứ tự tương đối ban đầu.

```java
record Task(int priority, String id) {}

List<String> ids = List.of(
        new Task(2, "A"),
        new Task(1, "B"),
        new Task(2, "C")
).stream()
 .sorted(Comparator.comparingInt(Task::priority))
 .map(Task::id)
 .toList();

System.out.println(ids); // [B, A, C]
```

Hai task có priority `2` vẫn theo thứ tự `A` rồi `C`. Với **đầu vào không có thứ tự**, tính ổn định này không được bảo đảm. Nếu cần kết quả tái lập cả khi khóa chính bằng nhau, hãy thêm khóa phụ, ví dụ `thenComparing(Task::id)`.

### 3.2. `distinct()` và khái niệm “phần tử đầu tiên”

```java
List<String> unique = List.of("A", "B", "A", "C", "B")
        .parallelStream()
        .distinct()
        .toList();

System.out.println(unique); // [A, B, C]
```

Khi stream có thứ tự, `distinct()` loại trùng và giữ phần tử xuất hiện đầu tiên theo encounter order. Điều này cũng quan trọng với đối tượng khác nhau nhưng được xem là bằng nhau bởi `equals`. Với stream không có thứ tự, `distinct()` không cam kết giữ đại diện nào trong các phần tử trùng nhau.

### 3.3. `limit`, `skip`, `takeWhile`, `dropWhile` không giống `filter`

```java
List<Integer> values = List.of(2, 4, 5, 6, 8);

System.out.println(values.stream().filter(n -> n % 2 == 0).toList());
// [2, 4, 6, 8]

System.out.println(values.stream().takeWhile(n -> n % 2 == 0).toList());
// [2, 4]

System.out.println(values.stream().dropWhile(n -> n % 2 == 0).toList());
// [5, 6, 8]

System.out.println(values.stream().skip(2).limit(2).toList());
// [5, 6]
```

`takeWhile` chỉ lấy **tiền tố liên tiếp** thỏa điều kiện; gặp `5` là dừng lấy, dù `6` và `8` vẫn chẵn. `dropWhile` chỉ bỏ tiền tố đó. Đây là khác biệt mang tính hợp đồng, không chỉ tối ưu hóa.

Với stream **không có thứ tự**:

- `limit(n)` được phép chọn bất kỳ `n` phần tử nào nếu có đủ phần tử;
- `skip(n)` được phép bỏ bất kỳ `n` phần tử nào;
- `takeWhile(predicate)` có thể lấy một tập con tùy ý của các phần tử thỏa điều kiện (trường hợp mọi phần tử đều thỏa có quy tắc riêng);
- `dropWhile(predicate)` có thể bỏ một tập con tùy ý của các phần tử thỏa điều kiện.

Vì vậy, `unordered().takeWhile(...)` không có cùng nghĩa với “lấy đến khi gặp phần tử đầu tiên sai điều kiện”. Các thao tác `takeWhile` và `dropWhile` xuất hiện từ Java 9.

## 4. Terminal operation: không phải thao tác nào cũng giữ thứ tự đầu ra

Một pipeline có encounter order không có nghĩa **mọi** terminal operation đều phải thực thi hoặc biểu lộ thứ tự đó.

| Terminal operation | Hợp đồng về thứ tự |
|---|---|
| `toList()`, `toArray()` | Tạo kết quả theo encounter order nếu stream có thứ tự |
| `collect(Collectors.toList())` | Tích lũy theo encounter order khi nguồn có thứ tự |
| `findFirst()` | Chọn phần tử đầu tiên theo encounter order, nếu có; với stream không có thứ tự có thể chọn bất kỳ |
| `findAny()` | Được phép chọn bất kỳ phần tử nào, đặc biệt hữu ích cho xử lý song song |
| `forEach(action)` | Không bảo đảm thứ tự thực thi hành động, kể cả với nguồn có thứ tự |
| `forEachOrdered(action)` | Thực hiện hành động theo encounter order nếu stream có thứ tự |
| `count()`, `sum()`, `anyMatch()` | Giá trị kết quả không mang thứ tự phần tử |
| `collect(Collectors.toSet())` | Collector là `UNORDERED`; không cam kết thứ tự duyệt kết quả `Set` |

Ví dụ với `findFirst` và `findAny`:

```java
List<Integer> values = List.of(10, 20, 30, 40);

System.out.println(values.parallelStream().findFirst().orElseThrow());
// 10

System.out.println(values.parallelStream().findAny().orElseThrow());
// Một phần tử bất kỳ trong [10, 20, 30, 40]
```

Kể cả khi `findAny()` thường trả một giá trị quen thuộc trên máy của bạn, không được viết logic phụ thuộc vào giá trị đó.

### 4.1. `forEach` khác `forEachOrdered`

```java
List<Integer> values = List.of(1, 2, 3, 4, 5);

values.parallelStream().forEach(n -> System.out.print(n + " "));
// Thứ tự in không được bảo đảm

System.out.println();

values.parallelStream().forEachOrdered(n -> System.out.print(n + " "));
// 1 2 3 4 5
```

`forEachOrdered` bảo đảm các hành động diễn ra theo encounter order; trong stream song song, hành động cho phần tử trước có quan hệ *happens-before* với hành động cho phần tử sau. Tuy vậy, các hành động không nhất thiết chạy trên cùng một thread.

Nếu mục đích là **thu thập kết quả**, ưu tiên `toList()` hoặc `collect(...)` thay vì thêm phần tử vào một `ArrayList` bên ngoài qua `forEach`. Một `ArrayList` dùng chung sẽ có nguy cơ race condition trong pipeline song song; ngay cả cấu trúc thread-safe cũng không tự bảo đảm thứ tự thêm phần tử.

## 5. Parallel stream: song song không đồng nghĩa mất encounter order

Xét pipeline:

```java
List<Integer> input = List.of(5, 2, 4, 1, 3);

List<Integer> result = input.parallelStream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * 10)
        .toList();

System.out.println(result); // [50, 10, 30]
```

Các task có thể xử lý `1` trước `5` trên các thread khác nhau. Dù vậy, `toList()` phải trả `[50, 10, 30]` theo encounter order của những phần tử được giữ lại. Thay `toList()` bằng `forEach(System.out::println)` sẽ mất bảo đảm về thứ tự in.

Giữ thứ tự có thể làm giảm lợi ích song song với một số thao tác:

- `distinct()` trên stream có thứ tự phải xác định phần tử trùng xuất hiện đầu tiên.
- `limit()`, `skip()` trên stream có thứ tự phải chọn hoặc bỏ đúng các phần tử ở đầu.
- `takeWhile()`, `dropWhile()` trên stream có thứ tự phải xác định tiền tố, có thể hạn chế hiệu quả phân chia công việc.
- `forEachOrdered()` phải phối hợp thứ tự các hành động thay vì cho chúng chạy hoàn toàn tự do.

Điều này **không** có nghĩa bỏ thứ tự luôn nhanh hơn: chi phí thực tế còn phụ thuộc kích thước dữ liệu, thao tác và phần cứng. Hãy đo hiệu năng với dữ liệu đại diện trước khi thay đổi hợp đồng.

### 5.1. Dùng `unordered()` khi thứ tự thật sự không quan trọng

```java
List<Integer> anyThree = List.of(10, 20, 30, 40, 50, 60)
        .parallelStream()
        .unordered()
        .limit(3)
        .toList();

System.out.println(anyThree); // Bất kỳ 3 giá trị; không cam kết [10, 20, 30]
```

`unordered()` **không xáo trộn dữ liệu**. Nó chỉ gỡ ràng buộc thứ tự, cho phép các thao tác về sau có thêm lựa chọn thực thi. Đầu ra vẫn *có thể* tình cờ là `[10, 20, 30]`; đó không còn là cam kết của pipeline.

Nếu nghiệp vụ yêu cầu “ba đơn hàng đầu tiên”, không thêm `unordered()`. Nếu yêu cầu chỉ là “ba mẫu bất kỳ để kiểm thử”, việc bỏ ràng buộc thứ tự có thể hợp lý.

### 5.2. Thứ tự của collector và cấu trúc dữ liệu đầu ra

Khi `collect`, phải xem xét **cả** encounter order của stream, `Collector.Characteristics` và cấu trúc đích:

```java
List<String> words = List.of("a", "bb", "c", "ddd");

// Danh sách giữ thứ tự gặp phần tử.
List<String> list = words.parallelStream()
        .collect(Collectors.toList());
// [a, bb, c, ddd]

// Map mặc định của groupingBy không cam kết thứ tự duyệt các khóa.
Map<Integer, List<String>> groups = words.stream()
        .collect(Collectors.groupingBy(String::length));

// Yêu cầu duy trì thứ tự thêm khóa: dùng LinkedHashMap với stream tuần tự.
Map<Integer, List<String>> orderedGroups = words.stream()
        .collect(Collectors.groupingBy(
                String::length,
                LinkedHashMap::new,
                Collectors.toList()
        ));
// Theo thứ tự khóa: 1 -> [a, c], 2 -> [bb], 3 -> [ddd]
```

`groupingBy` thông thường không bảo đảm kiểu `Map` hoặc thứ tự duyệt khóa nếu không chỉ định `mapFactory`. Với nguồn có thứ tự, danh sách trong từng nhóm thu bằng `toList()` giữ thứ tự gặp phần tử trong nhóm. Khi cần thứ tự chèn khóa có thể dự đoán, ví dụ trên sử dụng `LinkedHashMap` **và** stream tuần tự.

`groupingByConcurrent(...)` là collector mang đặc tính `CONCURRENT` và `UNORDERED`; thích hợp khi không cần bảo toàn thứ tự gặp phần tử trong nhóm. `toSet()` cũng mang đặc tính `UNORDERED`. Đừng suy ra thứ tự chỉ từ kết quả in một lần của `HashMap`, `HashSet` hoặc `toMap(...)` mặc định.

Lưu ý phiên bản: `Stream.toList()` có từ Java 16 và cho danh sách không thể chỉnh sửa; `Collectors.toList()` không cam kết kiểu danh sách hoặc tính thay đổi được. Nếu cần kết quả `ArrayList` có thể sửa, dùng `collect(Collectors.toCollection(ArrayList::new))`.

## 6. Hợp đồng thứ tự gắn với vòng đời pipeline

Một Stream được mô tả bằng chuỗi **nguồn → thao tác trung gian → terminal operation**:

```text
List (ORDERED)
    |
    v
filter(...)    -- giữ thứ tự tương đối
    |
    v
parallel()     -- thay đổi cách thực thi, không bỏ ORDERED
    |
    v
sorted(...)    -- thiết lập encounter order theo comparator
    |
    v
limit(3)       -- lấy ba phần tử đầu theo thứ tự hiện tại
    |
    v
toList()       -- trả danh sách theo encounter order
```

Các thao tác trung gian thường lazy; chỉ khi terminal operation chạy, pipeline mới tiêu thụ nguồn. Mỗi Stream chỉ dành cho **một lần tiêu thụ**; muốn chạy pipeline với terminal operation khác, tạo stream mới từ nguồn:

```java
List<Integer> source = List.of(3, 1, 2);

List<Integer> ascending = source.stream().sorted().toList();
Optional<Integer> first = source.stream().findFirst();

System.out.println(ascending);             // [1, 2, 3]
System.out.println(first.orElseThrow());    // 3
```

Không tái sử dụng chính đối tượng `Stream` sau terminal operation. Với nguồn gắn tài nguyên như `Files.lines(path)`, dùng `try-with-resources` để đóng stream; bảo đảm thứ tự không thay thế nghĩa vụ giải phóng tài nguyên.

Ngoài thứ tự, lambda trong pipeline nên **không can thiệp vào nguồn** và **không dựa vào trạng thái dùng chung có thể thay đổi**. Thứ tự kết quả được bảo đảm không chứng minh rằng side effect trong `map`, `peek` hoặc `forEach` chạy theo một thứ tự hay đúng số lần kỳ vọng; tối ưu hóa và terminal operation có thể làm một số phần pipeline không cần thực thi.

## 7. Những lỗi thường gặp và cách xử lý

| Cách viết hoặc suy nghĩ | Vấn đề | Cách làm phù hợp |
|---|---|---|
| “`parallel()` khiến `toList()` mất thứ tự” | Nhầm thời điểm xử lý với encounter order | Đọc hợp đồng của terminal operation; `toList()` giữ encounter order của nguồn có thứ tự |
| “`forEach` sẽ in theo thứ tự của `List`” | `forEach` không cam kết thứ tự hành động | Dùng `forEachOrdered`, hoặc thu vào `List` nếu cần dữ liệu |
| “`unordered()` sẽ shuffle phần tử” | `unordered` chỉ bỏ ràng buộc | Dùng cơ chế shuffle tường minh nếu thật sự cần xáo trộn |
| “`HashSet.stream().findFirst()` luôn chọn phần tử X” | Nguồn không có encounter order | Chọn nguồn có thứ tự hoặc `sorted()` trước khi `findFirst()` |
| “`takeWhile` tương đương `filter`” | `takeWhile` chỉ xét tiền tố liên tiếp với nguồn có thứ tự | Dùng `filter` để xét độc lập từng phần tử |
| “`groupingBy` tự giữ thứ tự khóa” | Kiểu và thứ tự duyệt `Map` mặc định không được cam kết | Chỉ định `LinkedHashMap::new` và thực thi tuần tự khi thứ tự chèn khóa quan trọng |
| “Kết quả có thứ tự nghĩa là lambda thread-safe” | Bảo đảm kết quả không bảo vệ shared mutable state | Dùng phép biến đổi thuần và collector phù hợp |

## 8. Ví dụ tổng hợp có thể chạy

Ví dụ sau dùng Java 17 trở lên, để các kết quả được chú thích có thể kiểm chứng:

```java
import java.util.List;

public class EncounterOrderDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(5, 2, 4, 1, 3);

        // Song song nhưng kết quả vẫn theo encounter order.
        System.out.println(source.parallelStream()
                .filter(n -> n % 2 != 0)
                .map(n -> n * 10)
                .toList());                         // [50, 10, 30]

        // sorted() thiết lập thứ tự tăng dần trước limit().
        System.out.println(source.parallelStream()
                .sorted()
                .limit(3)
                .toList());                         // [1, 2, 3]

        // findFirst() chọn phần tử đầu tiên của nguồn có thứ tự.
        System.out.println(source.parallelStream()
                .findFirst()
                .orElseThrow());                    // 5

        // Hành động được thực hiện theo encounter order.
        source.parallelStream()
                .forEachOrdered(n -> System.out.print(n + " ")); // 5 2 4 1 3
        System.out.println();
    }
}
```

## 9. Tự kiểm tra

1. Với `List.of(9, 2, 7, 2).parallelStream().distinct().toList()`, thứ tự kết quả là gì? **Đáp án:** `[9, 2, 7]` vì nguồn có thứ tự và `distinct` giữ lần xuất hiện đầu tiên.
2. Với `List.of(9, 2, 7, 2).parallelStream().unordered().limit(2).toList()`, có được khẳng định kết quả là `[9, 2]` không? **Không.** Có thể xuất hiện kết quả đó, nhưng không được bảo đảm.
3. Muốn chọn phần tử nhỏ nhất trong `List.of(8, 3, 5)`, có thể dùng `findFirst()` trực tiếp không? **Không**, vì encounter order ban đầu là `8, 3, 5`. Dùng `min(Integer::compareTo)` hoặc `sorted().findFirst()` nếu cần xét thứ tự sắp xếp.
4. Muốn bảo toàn thứ tự trong kết quả của pipeline song song, có bắt buộc chuyển về `sequential()` không? **Không.** Với nguồn có thứ tự, các terminal operation như `toList()`, `toArray()` và `forEachOrdered()` có các bảo đảm thích hợp.

**Quy tắc thực hành:** xác định nguồn có encounter order hay không, xét xem các thao tác trung gian có giữ hoặc thay đổi nó không, rồi kiểm tra hợp đồng terminal operation. Chỉ bỏ ràng buộc bằng `unordered()` khi nghiệp vụ thực sự không cần thứ tự.
