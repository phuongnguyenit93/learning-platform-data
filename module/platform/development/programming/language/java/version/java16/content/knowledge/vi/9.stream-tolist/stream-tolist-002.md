# Encounter order của danh sách kết quả với nguồn có thứ tự

`Stream.toList()` thu các phần tử của pipeline thành một `List`. Nếu stream có **encounter order** (thứ tự gặp phần tử), danh sách kết quả giữ đúng thứ tự đó. Phương thức không tự sắp xếp phần tử theo giá trị, thời gian hay một tiêu chí nghiệp vụ nào; nó phản ánh thứ tự mà pipeline quy định.

Điều này đặc biệt hữu ích khi kết quả cần giữ thứ tự ban đầu của dữ liệu, chẳng hạn danh sách công việc theo thứ tự ưu tiên đã có, các dòng trong tệp, hoặc các bản ghi theo thứ tự xuất hiện. Muốn có thứ tự khác, hãy định nghĩa thứ tự đó rõ ràng trong pipeline.

## 1. Encounter order là gì?

Encounter order là thứ tự mà một stream có quy định khi duyệt các phần tử. Thứ tự này phụ thuộc vào nguồn dữ liệu và các intermediate operation đã áp dụng.

Ví dụ, một `List` có thứ tự phần tử `["B", "A", "C", "D"]`. Khi dùng `filter` để bỏ `C` rồi `map` để chuyển chữ thành chữ thường, các phần tử còn lại vẫn xuất hiện theo thứ tự tương đối ban đầu:

```java
import java.util.List;

List<String> result = List.of("B", "A", "C", "D").stream()
    .filter(value -> !value.equals("C"))
    .map(String::toLowerCase)
    .toList();

System.out.println(result);
// [b, a, d]
```

`toList()` giữ thứ tự `b`, `a`, `d`. Nó không tự đổi thành `[a, b, d]`; muốn sắp xếp theo chữ cái, cần gọi `sorted()`.

## 2. Nguồn nào có encounter order?

Không phải mọi stream đều có thứ tự được bảo đảm. Hãy xem loại collection hoặc nguồn dữ liệu trước khi dựa vào vị trí của phần tử trong kết quả.

| Nguồn stream | Encounter order | Ý nghĩa khi gọi `toList()` |
| --- | --- | --- |
| `List` hoặc mảng | Có | Giữ thứ tự phần tử trong list hoặc mảng. |
| `LinkedHashSet` | Có | Giữ thứ tự duyệt, thường tương ứng thứ tự thêm phần tử. |
| `TreeSet` | Có | Giữ thứ tự duyệt theo natural order hoặc comparator của set. |
| `HashSet` | Không được bảo đảm | Không dựa vào thứ tự cụ thể của danh sách kết quả. |
| `HashMap.entrySet()` hoặc `Map.of(...).entrySet()` | Không được bảo đảm | Thứ tự duyệt entry không phải hợp đồng để dựa vào. |
| `Stream.iterate(...)` | Có | Giữ thứ tự sinh ra từ seed và hàm kế tiếp. |
| `Stream.generate(...)` | Không | Không có encounter order được xác định. |

Ví dụ với `LinkedHashSet`, thứ tự duyệt được giữ khi chuyển sang list:

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

Set<String> steps = new LinkedHashSet<>();
steps.add("Nhận yêu cầu");
steps.add("Xử lý dữ liệu");
steps.add("Trả kết quả");

List<String> workflow = steps.stream().toList();
System.out.println(workflow);
// [Nhận yêu cầu, Xử lý dữ liệu, Trả kết quả]
```

Ngược lại, `HashSet` không cam kết thứ tự duyệt. Một lần chạy có thể tình cờ cho ra một thứ tự dễ đoán, nhưng chương trình không được coi thứ tự đó là hợp đồng ổn định.

## 3. Các operation ảnh hưởng đến encounter order

Các intermediate operation có thể giữ nguyên, áp đặt hoặc loại bỏ encounter order. Những hành vi thường gặp:

| Operation | Ảnh hưởng đến thứ tự |
| --- | --- |
| `filter(...)` | Giữ thứ tự tương đối của các phần tử vượt qua điều kiện. |
| `map(...)` | Giữ vị trí tương đối; thay đổi giá trị hoặc kiểu phần tử, không tự sắp xếp. |
| `flatMap(...)` | Giữ thứ tự các phần tử nguồn bên ngoài; trong mỗi nhóm, thứ tự phụ thuộc encounter order của stream con nếu có. |
| `distinct()` | Với stream có thứ tự, giữ phần tử xuất hiện đầu tiên trong mỗi nhóm phần tử trùng nhau. |
| `sorted()` | Áp đặt thứ tự theo natural order hoặc comparator được cung cấp. Với stream có thứ tự, phép sắp xếp là stable. |
| `unordered()` | Loại bỏ ràng buộc encounter order của stream. |

### Sắp xếp theo quy tắc nghiệp vụ

Nếu cần danh sách theo một tiêu chí cụ thể, hãy biểu diễn tiêu chí bằng `Comparator`. Ví dụ sau xếp công việc theo độ ưu tiên giảm dần, sau đó theo mã công việc tăng dần để phân định các trường hợp cùng độ ưu tiên:

```java
import java.util.Comparator;
import java.util.List;

record Task(String code, int priority) {}

List<Task> tasks = List.of(
    new Task("CV-03", 2),
    new Task("CV-02", 3),
    new Task("CV-01", 3),
    new Task("CV-04", 1)
);

List<Task> orderedTasks = tasks.stream()
    .sorted(Comparator.comparingInt(Task::priority)
        .reversed()
        .thenComparing(Task::code))
    .toList();

System.out.println(orderedTasks);
// [Task[code=CV-01, priority=3], Task[code=CV-02, priority=3],
//  Task[code=CV-03, priority=2], Task[code=CV-04, priority=1]]
```

`sorted()` là stateful intermediate operation: nó cần xem các phần tử để xác định thứ tự trước khi phát kết quả. Với stream có thứ tự, sort stable nghĩa là nếu comparator xem hai phần tử là bằng nhau, thứ tự tương đối ban đầu của chúng được giữ. Trong ví dụ trên, `thenComparing(Task::code)` tạo thêm tiêu chí phân định rõ ràng, giúp kết quả không phụ thuộc thứ tự nguồn khi hai công việc có cùng priority.

## 4. Encounter order trong parallel stream

Chuyển một stream có thứ tự sang parallel stream không tự loại bỏ encounter order. Khi pipeline vẫn có ràng buộc thứ tự, `toList()` tiếp tục tạo danh sách theo thứ tự đó, dù các phần tử có thể được xử lý ở những thread khác nhau.

```java
import java.util.List;

List<Integer> doubled = List.of(1, 2, 3, 4, 5).parallelStream()
    .map(number -> number * 2)
    .toList();

System.out.println(doubled);
// [2, 4, 6, 8, 10]
```

Thứ tự xử lý và thứ tự kết quả là hai khái niệm khác nhau. Một phần tử có thể được xử lý trước phần tử đứng trước nó trong nguồn, nhưng `toList()` vẫn sắp kết quả theo encounter order đã được bảo đảm.

Điều này không có nghĩa mọi terminal operation đều giữ thứ tự. Với parallel stream, `forEach()` không bảo đảm thực hiện action theo encounter order. Nếu cần thực hiện action lần lượt theo thứ tự nguồn, dùng `forEachOrdered()`:

```java
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

numbers.parallelStream().forEach(System.out::println);
// Không bảo đảm thứ tự dòng được in.

numbers.parallelStream().forEachOrdered(System.out::println);
// Bảo đảm in theo thứ tự 1, 2, 3, 4, 5.
```

`forEachOrdered()` có thể hạn chế mức độ song song vì action phải được thực hiện theo thứ tự. Với thao tác chỉ thu kết quả thành danh sách, hãy dùng `toList()` và để pipeline giữ encounter order khi nghiệp vụ yêu cầu.

## 5. Khi nào nên dùng `unordered()`?

`unordered()` trả về một stream không còn ràng buộc encounter order. Phương thức này **không xáo trộn dữ liệu** và cũng không hứa rằng thứ tự kết quả sẽ thay đổi. Nó cho phép implementation lựa chọn cách xử lý không cần duy trì thứ tự, có thể hữu ích với một số pipeline song song hoặc operation có trạng thái như `distinct()`.

```java
import java.util.List;

List<Integer> selected = List.of(8, 3, 6, 1, 4, 9).parallelStream()
    .unordered()
    .filter(number -> number % 2 == 0)
    .toList();

// Không được giả định kết quả luôn là [8, 6, 4].
```

Chỉ gọi `unordered()` khi logic chương trình không phụ thuộc thứ tự. Nếu kết quả cần được trình bày theo thứ tự xác định, hãy giữ encounter order hoặc áp đặt thứ tự bằng `sorted(...)` trước `toList()`.

## 6. Tạo thứ tự rõ ràng từ nguồn không có thứ tự

Khi dữ liệu đến từ nguồn không có encounter order nhưng giao diện hoặc nghiệp vụ cần kết quả ổn định, hãy sắp xếp theo một khóa xác định. Ví dụ, `Map.of(...)` không cung cấp thứ tự duyệt để chương trình dựa vào; có thể sắp xếp entry theo key trước khi thu thập:

```java
import java.util.List;
import java.util.Map;

Map<String, Integer> scores = Map.of(
    "Chi", 9,
    "An", 8,
    "Bình", 10
);

List<String> names = scores.entrySet().stream()
    .sorted(Map.Entry.comparingByKey())
    .map(Map.Entry::getKey)
    .toList();

System.out.println(names);
// [An, Bình, Chi]
```

Nếu nhiều phần tử có cùng khóa sắp xếp, hãy thêm tiêu chí phụ bằng `thenComparing(...)` để quy định rõ thứ tự giữa chúng. Điều này đặc biệt quan trọng khi kết quả được dùng để hiển thị, xuất báo cáo, so sánh snapshot hoặc tạo dữ liệu cần lặp lại ổn định.

## 7. Checklist khi dùng `Stream.toList()`

- Xác định nguồn có encounter order hay không trước khi dựa vào vị trí phần tử.
- Nhớ rằng `toList()` giữ encounter order nếu stream có thứ tự; nó không tự sắp xếp.
- Kiểm tra pipeline có gọi `unordered()` hay operation nào thay đổi thứ tự hay không.
- Với nguồn không có thứ tự, dùng `sorted(...)` nếu cần kết quả xác định.
- Không nhầm thứ tự xử lý trong parallel stream với thứ tự phần tử trong danh sách kết quả.
- Không dùng `forEach()` nếu action bắt buộc phải chạy theo encounter order; cân nhắc `forEachOrdered()` khi thực sự cần thứ tự cho side effect.

`Stream.toList()` có từ Java 16 và vẫn là API chuẩn trong Java hiện đại. Khi hiểu encounter order, bạn có thể dự đoán chính xác thứ tự kết quả, tránh phụ thuộc vào hành vi tình cờ của collection và chủ động cân bằng giữa yêu cầu thứ tự với hiệu năng xử lý song song.

## Tài liệu tham khảo

- [Stream.toList() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Package java.util.stream – Ordering, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html#Ordering)
- [BaseStream.unordered() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/BaseStream.html#unordered())
