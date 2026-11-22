# Bỏ tiền tố thỏa điều kiện bằng `dropWhile`

## 1. Bài toán: bỏ phần đầu của một dãy cho đến mốc chuyển trạng thái

Trong Java Stream API, không phải lúc nào ta cũng muốn **lọc tất cả** phần tử thỏa một điều kiện. Đôi khi ta chỉ muốn bỏ một đoạn **liên tiếp ở đầu** của dãy, rồi giữ nguyên tất cả những phần tử còn lại:

- Bỏ các dòng chú thích ở đầu tệp, bắt đầu xử lý từ dòng dữ liệu đầu tiên.
- Bỏ các sự kiện có thời gian trước một mốc, nếu sự kiện đã được sắp theo thời gian.
- Bỏ các công việc đã hoàn thành ở đầu danh sách, tiếp tục từ công việc chưa hoàn thành đầu tiên.
- Bỏ các ID đã duyệt qua trong một danh sách tăng dần để lấy trang kế tiếp.

`dropWhile` diễn đạt đúng thao tác này: **bỏ tiền tố dài nhất gồm các phần tử liên tiếp thỏa predicate** của một stream **có thứ tự gặp phần tử** (*encounter order*).

Hình dung dãy số:

```text
Nguồn:       [1, 2, 4, 8, 3, 10]
Điều kiện:   n < 5
                     ▲
               8 là phần tử đầu tiên KHÔNG thỏa

Bỏ:          [1, 2, 4]
Giữ lại:              [8, 3, 10]
```

Điểm mấu chốt: **số `3` vẫn được giữ lại** dù `3 < 5`, vì nó đứng sau phần tử `8` đã làm kết thúc tiền tố cần bỏ.

Ví dụ Java:

```java
import java.util.List;

List<Integer> values = List.of(1, 2, 4, 8, 3, 10);

List<Integer> result = values.stream()
    .dropWhile(n -> n < 5)
    .toList();

System.out.println(result); // [8, 3, 10]
```

Bài học thuộc phần **Thứ tự, loại trùng và cắt lát** của module `JAVA_STREAM_API`. Sau bài, bạn cần:

1. Đọc và vận dụng đúng chữ ký `dropWhile` cùng quy tắc **tiền tố liên tiếp**.
2. Phân biệt `dropWhile` với `takeWhile`, `filter`, `skip`, `limit` và `sorted`.
3. Nhận ra tác động của encounter order và stream không có thứ tự.
4. Dùng `dropWhile` trong pipeline khai báo kết hợp `map`, `reduce`, `collect` hoặc grouping.
5. Kiểm thử những biên quan trọng: nguồn rỗng, tất cả phần tử thỏa, không phần tử nào thỏa, điều kiện đúng trở lại ở phía sau.
6. Đánh giá tính lười, tác dụng phụ, nguồn vô hạn và chi phí xử lý song song.

## 2. Đọc chữ ký API và hợp đồng chính thức

Trên `java.util.stream.Stream<T>`, phương thức có chữ ký:

```java
Stream<T> dropWhile(Predicate<? super T> predicate)
```

`dropWhile` được giới thiệu trong **Java 9**. Những thành phần trong chữ ký cho biết:

| Thành phần | Ý nghĩa |
| --- | --- |
| `Stream<T>` ở đầu | Kết quả là stream cùng kiểu phần tử `T` |
| `Predicate<? super T>` | Hàm kiểm tra phần tử, nhận `T` hoặc kiểu cha tương thích và trả `boolean` |
| `true` từ predicate | Phần tử **có thể bị bỏ** nếu còn thuộc tiền tố đang xét |
| `false` đầu tiên | Kết thúc tiền tố bị bỏ trên **ordered stream**; phần tử này được giữ |
| Giá trị trả về | Stream gồm phần đuôi sau khi đã bỏ tiền tố, hoặc stream rỗng |

Theo Javadoc, đây là một **stateful intermediate operation** (phép toán trung gian có trạng thái), đồng thời là **short-circuiting intermediate operation**. Nó cần ghi nhận thời điểm đã gặp phần tử đầu tiên không thỏa; từ thời điểm ấy, các phần tử sau được giữ lại, kể cả khi predicate của chúng sẽ trả `true`.

Là **intermediate operation**, `dropWhile` không tự tiêu thụ stream. Terminal operation như `toList`, `findFirst` hoặc `count` mới yêu cầu dữ liệu đi qua pipeline:

```java
var pipeline = values.stream()
    .dropWhile(n -> n < 5); // Mới xây dựng pipeline.

List<Integer> suffix = pipeline.toList(); // Kích hoạt việc xử lý.
```

Một stream chỉ nên được tiêu thụ một lần. Nếu cần một kết quả từ `dropWhile` và một kết quả từ `filter`, tạo hai stream mới từ collection nguồn.

Tài liệu chính thức:

- [`Stream.dropWhile` trong Javadoc Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html#dropWhile(java.util.function.Predicate))
- [Package `java.util.stream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html)
- [`IntStream.dropWhile`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/IntStream.html#dropWhile(java.util.function.IntPredicate))

Chọn tài liệu phù hợp với phiên bản JDK đang chạy. Các ví dụ trong bài dùng `toList()` (Java 16+) và `record` (Java 16+), nên các chương trình minh họa đầy đủ nhắm đến **JDK 17 trở lên**; riêng phương thức `dropWhile` đã có từ JDK 9.

## 3. Quy tắc chính xác trên stream có thứ tự

Gọi dãy nguồn có thứ tự là `x₀, x₁, ..., xₙ₋₁` và điều kiện là `p(x)`. Tìm chỉ số đầu tiên `k` sao cho `p(xₖ) == false`. Khi đó:

- Bỏ tất cả phần tử `x₀ ... xₖ₋₁`.
- Giữ lại `xₖ ... xₙ₋₁`.
- Nếu mọi phần tử đều thỏa, kết quả rỗng.
- Nếu phần tử đầu tiên đã không thỏa, kết quả gồm toàn bộ nguồn.

Không cần tìm một mốc ở cuối dãy, cũng không cần điều kiện trở thành false **vĩnh viễn**. Chỉ lần đầu tiên chuyển từ true sang false trong quá trình đi từ đầu dãy mới quyết định chỗ cắt.

| Nguồn có thứ tự | Predicate | Kết quả `dropWhile` |
| --- | --- | --- |
| `[1, 2, 3, 7, 2, 8]` | `n < 5` | `[7, 2, 8]` |
| `[1, 2, 3]` | `n < 5` | `[]` |
| `[7, 1, 2]` | `n < 5` | `[7, 1, 2]` |
| `[]` | `n < 5` | `[]` |
| `[5, 6, 7]` | `n < 5` | `[5, 6, 7]` |
| `[1, 2, 5, 3]` | `n <= 5` | `[3]` |

Ví dụ cuối cho thấy **ranh giới `<` và `<=` khác nhau**: nếu predicate là `n <= 5`, số `5` vẫn nằm trong tiền tố bị bỏ. Khi triển khai mốc thời gian hoặc ID, cần nói rõ **giữ hay bỏ giá trị bằng mốc**.

## 4. So sánh `dropWhile`, `takeWhile`, `filter` và `skip`

Các phương thức này nhìn giống nhau vì đều làm dãy kết quả ngắn lại, nhưng hợp đồng khác nhau.

### 4.1. `dropWhile` so với `filter`

`filter` áp dụng điều kiện cho **mọi phần tử được đánh giá**. `dropWhile` chỉ quyết định **điểm cắt tiền tố**.

```java
List<Integer> source = List.of(1, 2, 8, 3, 10);

List<Integer> droppedPrefix = source.stream()
    .dropWhile(n -> n < 5)
    .toList();
// [8, 3, 10]

List<Integer> filtered = source.stream()
    .filter(n -> n >= 5)
    .toList();
// [8, 10]
```

Nếu điều kiện có thể đúng trở lại phía sau một phần tử không thỏa, **hai kết quả khác nhau**. Chỉ thay `dropWhile` bằng `filter` khi nghiệp vụ thật sự muốn lựa chọn từng phần tử riêng lẻ.

### 4.2. `dropWhile` so với `takeWhile`

Trên stream **có thứ tự**, cả hai cùng dựa vào tiền tố dài nhất thỏa predicate nhưng tác động ngược nhau:

```java
List<Integer> source = List.of(1, 2, 8, 3, 10);

List<Integer> prefix = source.stream()
    .takeWhile(n -> n < 5)
    .toList(); // [1, 2]

List<Integer> suffix = source.stream()
    .dropWhile(n -> n < 5)
    .toList(); // [8, 3, 10]
```

Với nguồn có thứ tự, `takeWhile` giữ tiền tố, `dropWhile` bỏ cùng tiền tố. Nếu cần tách hai phần để dùng độc lập, tạo **hai pipeline** từ cùng nguồn có thể duyệt lại; đừng cố tái sử dụng stream đã được terminal operation tiêu thụ.

### 4.3. `dropWhile` so với `skip`

`skip(long n)` bỏ **số lượng cố định** `n` phần tử đầu, không dựa vào giá trị:

```java
List<Integer> source = List.of(1, 2, 8, 3, 10);

System.out.println(source.stream()
    .skip(2)
    .toList()); // [8, 3, 10]

System.out.println(source.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [8, 3, 10]
```

Hai kết quả tình cờ giống nhau vì có đúng hai số đầu nhỏ hơn `5`. Nếu nguồn đổi thành `[1, 2, 4, 8, 3, 10]` thì `skip(2)` giữ `4`, còn `dropWhile(n -> n < 5)` bỏ cả `4`. `skip` phù hợp với phân trang theo vị trí, còn `dropWhile` phù hợp khi mốc được mô tả bằng điều kiện.

### 4.4. Bảng chọn phép toán

| Yêu cầu nghiệp vụ | Chọn | Lý do |
| --- | --- | --- |
| Bỏ các phần tử đầu liên tiếp thỏa điều kiện | `dropWhile(predicate)` | Cắt theo điều kiện của tiền tố |
| Lấy các phần tử đầu liên tiếp thỏa điều kiện | `takeWhile(predicate)` | Giữ tiền tố |
| Chỉ giữ mọi phần tử thỏa điều kiện, bất kể vị trí | `filter(predicate)` | Kiểm tra từng phần tử |
| Bỏ đúng `n` phần tử đầu | `skip(n)` | Cắt theo số lượng |
| Giới hạn tối đa `n` phần tử kết quả | `limit(n)` | Cắt theo số lượng đầu ra |
| Sắp xếp dữ liệu theo comparator | `sorted(comparator)` | Thay đổi thứ tự để xác định lại tiền tố |

## 5. Encounter order là điều kiện quyết định

Quy tắc “tiền tố” chỉ xác định rõ khi stream có **encounter order**. Nguồn thường có thứ tự gồm `List`, mảng, `IntStream.range` và `Stream.of`. Các cấu trúc như `HashSet` thường **không bảo đảm encounter order**.

### 5.1. Nguồn có thứ tự

```java
List<String> lines = List.of(
    "# file được tạo tự động",
    "# phiên bản 2",
    "id,name",
    "# dấu # này là một phần dữ liệu phía sau",
    "1,An"
);

List<String> content = lines.stream()
    .dropWhile(line -> line.startsWith("#"))
    .toList();

System.out.println(content);
// [id,name, # dấu # này là một phần dữ liệu phía sau, 1,An]
```

`dropWhile` chỉ bỏ hai dòng chú thích ở **đầu**. Dòng bắt đầu `#` xuất hiện sau header `id,name` vẫn được giữ lại. Nếu chỉ muốn loại bỏ **mọi** dòng chú thích, phải dùng `filter(line -> !line.startsWith("#"))` theo chính sách định dạng dữ liệu.

### 5.2. Nguồn không có thứ tự: hợp đồng khác hẳn

Với **unordered stream**, Javadoc không định nghĩa “tiền tố đầu tiên”. Nếu có những phần tử thỏa predicate, `dropWhile` có thể bỏ **một tập con bất kỳ** trong số các phần tử thỏa, kể cả tập rỗng. Các phần tử không thỏa predicate vẫn phải được giữ. Do đó không thể hứa trước chính xác phần tử nào thỏa predicate sẽ còn lại.

Ví dụ:

```java
import java.util.Set;

Set<Integer> numbers = Set.of(1, 2, 3, 8, 9);

List<Integer> result = numbers.stream()
    .unordered()
    .dropWhile(n -> n < 5)
    .toList();

// Không được khẳng định result == [8, 9]
// hay một thứ tự đầu ra cố định.
// Hai phần tử 8 và 9 không thỏa n < 5 nên không bị dropWhile loại bỏ.
```

Không dùng `unordered()` chỉ vì nghĩ thao tác này đơn thuần làm pipeline nhanh hơn: nó cho phép một **tập kết quả khác** trong trường hợp `dropWhile`. Nếu yêu cầu là bỏ một tiền tố xác định theo thứ tự thời gian hoặc thứ tự công việc, phải **có và giữ encounter order**.

Nếu mọi phần tử đều thỏa, `dropWhile` có thể loại hết chúng; trên unordered stream nó không bắt buộc loại toàn bộ. Nếu không phần tử nào thỏa, không phần tử nào có thể bị loại bởi `dropWhile`.

### 5.3. `sorted` biến đổi ý nghĩa của tiền tố

`sorted` tạo thứ tự gặp phần tử theo phép so sánh. Điều này thường hữu ích khi điều kiện cắt là một **ngưỡng tăng dần**, nhưng cũng làm thay đổi thứ tự dữ liệu so với nguồn ban đầu.

```java
List<Integer> values = List.of(6, 1, 8, 2, 4);

System.out.println(values.stream()
    .dropWhile(n -> n < 5)
    .toList()); // [6, 1, 8, 2, 4] vì 6 không thỏa ngay từ đầu.

System.out.println(values.stream()
    .sorted()
    .dropWhile(n -> n < 5)
    .toList()); // [6, 8]
```

Khi thêm `sorted()`, nghiệp vụ chuyển từ “bỏ tiền tố theo thứ tự nhập liệu” sang “bỏ những giá trị nhỏ hơn ngưỡng sau khi sắp tăng dần”. `sorted` là phép toán trung gian có trạng thái, có thể cần duyệt, sắp xếp và lưu nhiều phần tử trước khi trả kết quả; cân nhắc chi phí khi dữ liệu lớn.

## 6. Ví dụ thực tế: lấy sự kiện từ mốc thời gian

Giả sử hệ thống có các sự kiện đến **không theo thứ tự thời gian**, nhưng báo cáo cần giữ những sự kiện xảy ra từ một mốc trở đi. Ta sắp xếp rồi dùng `dropWhile` theo thời điểm:

```java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;

public class EventsAfterCutoff {

    record Event(String id, Instant occurredAt, String message) {}

    public static void main(String[] args) {
        List<Event> events = List.of(
            new Event("E3", Instant.parse("2026-11-17T08:15:00Z"), "Done"),
            new Event("E1", Instant.parse("2026-11-17T08:05:00Z"), "Created"),
            new Event("E4", Instant.parse("2026-11-17T08:07:00Z"), "Received"),
            new Event("E2", Instant.parse("2026-11-17T08:10:00Z"), "Started")
        );

        Instant cutoff = Instant.parse("2026-11-17T08:10:00Z");

        List<String> eventIds = events.stream()
            .sorted(Comparator.comparing(Event::occurredAt))
            .dropWhile(event -> event.occurredAt().isBefore(cutoff))
            .map(Event::id)
            .toList();

        System.out.println(eventIds); // [E2, E3]
    }
}
```

Ở đây:

1. `sorted(Comparator.comparing(Event::occurredAt))` định nghĩa encounter order theo thời điểm tăng dần.
2. `dropWhile(event -> event.occurredAt().isBefore(cutoff))` bỏ các sự kiện **trước** mốc.
3. Sự kiện xảy ra **đúng mốc** được giữ vì `isBefore(cutoff)` trả `false` khi bằng nhau.
4. `map(Event::id)` chuyển mỗi sự kiện thành ID; `toList()` thu kết quả theo thứ tự đã sắp.

Nếu yêu cầu chỉ giữ sự kiện **sau** mốc, đổi predicate thành:

```java
.dropWhile(event -> !event.occurredAt().isAfter(cutoff))
```

Biểu thức mới bỏ cả sự kiện bằng mốc, vì “không sau cutoff” bao gồm **trước hoặc bằng**.

**Quan trọng:** `dropWhile` không làm bộ lọc thời gian đúng trên dữ liệu có timestamp lộn xộn nếu bỏ bước sắp xếp. Nếu nguồn đã **được cam kết** tăng dần theo thời gian, có thể bỏ `sorted` để tránh chi phí sắp xếp. Nếu không cần giữ thứ tự, mà chỉ muốn tất cả sự kiện không trước cutoff, dùng `filter(event -> !event.occurredAt().isBefore(cutoff))` có thể trực tiếp và phù hợp hơn.

## 7. Ví dụ thực tế: tiếp tục từ công việc chưa hoàn thành đầu tiên

Xét danh sách công việc theo thứ tự ưu tiên. Ta muốn bỏ các công việc đã hoàn thành **ở đầu dãy**, rồi giữ tất cả công việc từ điểm bắt đầu xử lý tiếp:

```java
import java.util.List;

record Task(String id, boolean done) {}

List<Task> tasks = List.of(
    new Task("A", true),
    new Task("B", true),
    new Task("C", false),
    new Task("D", true),
    new Task("E", false)
);

List<String> remainingFromFirstIncomplete = tasks.stream()
    .dropWhile(Task::done)
    .map(Task::id)
    .toList();

System.out.println(remainingFromFirstIncomplete); // [C, D, E]
```

**Vì sao `D` vẫn được giữ dù đã hoàn thành?** Đây là phép “tiếp tục từ vị trí chưa hoàn thành đầu tiên”, cần giữ phần đuôi để có thể xem xét trạng thái các công việc theo thứ tự. Nếu nghiệp vụ chỉ muốn **danh sách công việc chưa hoàn thành** ở bất kỳ vị trí nào, dùng:

```java
List<String> incompleteIds = tasks.stream()
    .filter(task -> !task.done())
    .map(Task::id)
    .toList();

System.out.println(incompleteIds); // [C, E]
```

Mấu chốt của thiết kế là định nghĩa rõ **bỏ tiền tố theo thứ tự** hay **lọc phần tử theo trạng thái**, vì hai bài toán không giống nhau.

## 8. Kết hợp `dropWhile` với `limit`, `map`, `reduce` và `collect`

### 8.1. Lấy trang dữ liệu theo mốc

Giả sử ID đã tăng dần và cần lấy tối đa hai ID **lớn hơn** cursor `20`:

```java
List<Integer> ids = List.of(10, 20, 30, 40, 50);
int cursor = 20;

List<Integer> page = ids.stream()
    .dropWhile(id -> id <= cursor)
    .limit(2)
    .toList();

System.out.println(page); // [30, 40]
```

Điều kiện để cách này đúng là nguồn được sắp tăng dần theo cùng tiêu chí so với cursor. Với nguồn `[30, 10, 40]`, phần tử đầu `30` làm tiền tố cần bỏ kết thúc ngay; `10` vẫn xuất hiện trong kết quả. Nếu dữ liệu nằm trong database lớn, hãy cân nhắc đưa điều kiện cursor và giới hạn vào truy vấn thay vì tải toàn bộ về JVM rồi mới `dropWhile`.

Thứ tự các phép toán rất quan trọng:

```java
List<Integer> byCursorThenLimit = ids.stream()
    .dropWhile(id -> id <= 20)
    .limit(2)
    .toList(); // [30, 40]

List<Integer> limitedBeforeCursor = ids.stream()
    .limit(2)
    .dropWhile(id -> id <= 20)
    .toList(); // []
```

Đặt `limit` trước `dropWhile` chỉ xem xét hai ID đầu và loại cả hai, nên không còn dữ liệu.

### 8.2. Tính tổng phần đuôi

```java
List<Integer> points = List.of(1, 3, 5, 10, 2);

int totalAfterThreshold = points.stream()
    .dropWhile(n -> n < 5)
    .mapToInt(Integer::intValue)
    .sum();

System.out.println(totalAfterThreshold); // 17 = 5 + 10 + 2
```

Khi cần tính tổng số nguyên thủy, `mapToInt` và `sum` tránh phải tạo nhiều `Integer` trung gian để gộp bằng `reduce`.

### 8.3. Grouping phần đuôi của dãy sự kiện

Sử dụng lại danh sách `events` đã được sắp thứ tự theo `occurredAt` trong mục 6. Có thể gom các sự kiện từ mốc theo loại:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> countByMessage = events.stream()
    .sorted(Comparator.comparing(Event::occurredAt))
    .dropWhile(event -> event.occurredAt().isBefore(cutoff))
    .collect(Collectors.groupingBy(
        Event::message,
        Collectors.counting()
    ));
```

`dropWhile` quyết định **những sự kiện nào thuộc phần đuôi cần thống kê**; `collect(groupingBy(...))` là phép toán kết thúc tổng hợp. Kết quả `Map` không bảo đảm thứ tự duyệt khóa; nếu cần thứ tự hiển thị, hãy chỉ định chính sách sắp xếp hoặc sử dụng overload phù hợp của collector.

## 9. Đầu vào rỗng, điều kiện biên và `null`

### 9.1. Những trường hợp cần nắm vững

```java
import java.util.List;
import java.util.stream.Stream;

System.out.println(
    Stream.<Integer>empty()
        .dropWhile(n -> n < 5)
        .toList()
); // []

System.out.println(
    List.of(1, 2, 3).stream()
        .dropWhile(n -> n < 5)
        .toList()
); // []

System.out.println(
    List.of(8, 1, 2).stream()
        .dropWhile(n -> n < 5)
        .toList()
); // [8, 1, 2]
```

Nguồn rỗng không có phần tử nào để giữ. Nếu mọi phần tử đều thỏa điều kiện, `dropWhile` bỏ toàn bộ dãy. Nếu phần tử đầu tiên đã không thỏa, nó giữ nguyên cả dãy có thứ tự.

### 9.2. Predicate bằng `null` và phần tử `null`

Truyền một `Predicate` bằng `null` cho `dropWhile` là không hợp lệ và có thể gây `NullPointerException`. Phần tử **bên trong stream** có thể bằng `null` nếu nguồn cho phép, nên predicate cần có chính sách phù hợp:

```java
import java.util.ArrayList;
import java.util.List;

List<String> data = new ArrayList<>();
data.add("");
data.add(null);
data.add("start");
data.add("");

// Quy ước: cả chuỗi rỗng và null ở đầu đều là phần cần bỏ.
List<String> result = data.stream()
    .dropWhile(value -> value == null || value.isEmpty())
    .toList();

System.out.println(result); // [start, ""]
```

Nếu `null` là lỗi dữ liệu, nên từ chối sớm thay vì âm thầm coi đó là phần tử cần bỏ. `List.of(...)` không nhận `null`, nên ví dụ dùng `ArrayList` để minh họa. Khi kết quả chứa `null`, cũng cần lưu ý một số terminal operation hoặc collector có quy tắc riêng với giá trị `null`.

### 9.3. Không dùng predicate có trạng thái ngoài

Tránh viết:

```java
// Phản ví dụ: predicate thay đổi trạng thái ngoài và dựa vào số lần gọi.
java.util.concurrent.atomic.AtomicInteger calls =
    new java.util.concurrent.atomic.AtomicInteger();

var result = values.stream()
    .dropWhile(n -> calls.incrementAndGet() <= 2)
    .toList();
```

`AtomicInteger` an toàn về cập nhật đồng thời nhưng predicate vẫn có side effect, phụ thuộc vào trạng thái thay đổi và không thể kiểm thử như một điều kiện thuần. Javadoc yêu cầu behavioral parameter của stream phải **non-interfering** và thường phải **stateless**. Kết quả có thể phụ thuộc vào cách triển khai hoặc chế độ thực thi; dùng `skip(2)` nếu bài toán là bỏ hai phần tử, dùng predicate chỉ dựa trên giá trị nếu bài toán là cắt theo điều kiện.

Không chỉnh sửa collection nguồn trong predicate:

```java
// Không làm:
// list.stream().dropWhile(item -> {
//     list.remove(item); // Can thiệp vào nguồn đang được duyệt.
//     return item.isOld();
// }).toList();
```

## 10. Stream vô hạn và điều kiện dừng

`dropWhile` có thể hoạt động với stream vô hạn nếu **cuối cùng sẽ gặp** phần tử không thỏa predicate và một terminal operation phía sau đủ điều kiện kết thúc:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> afterOneHundred = Stream.iterate(0, n -> n + 1)
    .dropWhile(n -> n < 100)
    .limit(4)
    .toList();

System.out.println(afterOneHundred); // [100, 101, 102, 103]
```

Nhưng nếu một stream vô hạn **luôn** thỏa predicate, `dropWhile` không thể tìm phần tử đầu tiên cần giữ:

```java
// Ví dụ có nguy cơ không kết thúc; KHÔNG chạy như một bài test thường.
// Stream.generate(() -> 0)
//     .dropWhile(n -> n == 0)
//     .findFirst();
```

`findFirst()` chỉ có thể trả khi có một phần tử đầu ra, còn `dropWhile` ở đây luôn bỏ phần tử nhận được. Đặt `limit(n)` **trước** `dropWhile` sẽ giới hạn phần nguồn phải duyệt, nhưng cũng đổi ý nghĩa vì chỉ quan sát tối đa `n` phần tử ban đầu.

Không đặt `sorted()` lên một nguồn vô hạn để mong nó cung cấp thứ tự cho `dropWhile`: việc sắp xếp toàn bộ nguồn vô hạn nói chung không thể hoàn thành.

## 11. Chi phí, xử lý song song và rủi ro hiệu năng

### 11.1. Đặc điểm khi chạy tuần tự

Khi stream có thứ tự và chạy tuần tự, `dropWhile` cần xác định tiền tố: nó kiểm tra các phần tử đầu cho đến phần tử không thỏa đầu tiên; sau đó các phần tử còn lại được chuyển tiếp theo yêu cầu của downstream operation. Chẳng hạn `dropWhile(...).limit(5)` có thể dừng sớm sau khi nhận đủ năm phần tử ở phần đuôi, nếu phía nguồn và các bước trước cho phép.

Với nguồn đã có thứ tự và predicate đơn giản, cách này thường dễ hiểu và không đòi hỏi tạo danh sách phụ chỉ để tìm vị trí cắt. Nhưng chi phí thực tế phụ thuộc các thao tác trước/sau nó, nguồn dữ liệu, khả năng short-circuit và số phần tử phải bỏ.

### 11.2. `parallel()` có thể tốn kém khi cần giữ thứ tự

Javadoc lưu ý `dropWhile` trên **ordered parallel stream** có thể rất tốn chi phí nếu phải bảo toàn “tiền tố dài nhất”: các luồng xử lý những phần khác nhau của nguồn nhưng vẫn phải xác định ranh giới theo thứ tự toàn cục.

```java
List<Integer> numbers = java.util.stream.IntStream.range(0, 100_000)
    .boxed()
    .toList();

List<Integer> remaining = numbers.parallelStream()
    .dropWhile(n -> n < 90_000)
    .toList();

System.out.println(remaining.size()); // 10000
```

Không suy ra `parallelStream` nhanh hơn chỉ vì có nhiều lõi CPU. Hãy đo trên bộ dữ liệu thật. Nếu nguồn có thứ tự cần bảo toàn và phép cắt rẻ, tuần tự có thể là lựa chọn tốt hơn.

Một số trường hợp **không phụ thuộc thứ tự đầu ra và chấp nhận ngữ nghĩa unordered** có thể cân nhắc `unordered()` để giảm chi phí; nhưng thay đổi này cho phép `dropWhile` bỏ một tập con tùy ý các phần tử thỏa predicate, nên **không tương đương** với cắt theo mốc. Chỉ thực hiện nếu đặc tả đầu ra cho phép.

### 11.3. Primitive streams

Các kiểu `IntStream`, `LongStream` và `DoubleStream` cũng có `dropWhile` với predicate nguyên thủy tương ứng:

```java
import java.util.stream.IntStream;

int sum = IntStream.range(0, 8)
    .dropWhile(n -> n < 5)
    .sum(); // 5 + 6 + 7 = 18

System.out.println(sum); // 18
```

`IntStream.dropWhile(IntPredicate)` tránh boxing sang `Integer`. Đối với `DoubleStream`, cần xác định chính sách khi gặp `NaN`, vô cực hoặc dấu của số không, vì phép so sánh số thực có những trường hợp biên đặc biệt. Ví dụ `Double.NaN < 5` là `false`, vì vậy một phần tử `NaN` có thể làm tiền tố bị bỏ kết thúc sớm.

### 11.4. Stream Gatherers và tác vụ cắt lát nâng cao

Stream Gatherers là API chính thức từ **JDK 24** để mô tả các phép biến đổi trung gian có thể duy trì trạng thái như cửa sổ hoặc phép quét tích lũy. Tuy nhiên, khi yêu cầu chỉ là “bỏ tiền tố thỏa predicate”, `dropWhile` đơn giản và biểu đạt đúng ý hơn. Không dùng Gatherers để thay thế một thao tác đã có sẵn, trừ khi nghiệp vụ cần trạng thái hay quy tắc cắt phức tạp hơn.

## 12. Kiểm thử ngữ nghĩa và những lỗi dễ mắc

### 12.1. Unit test JUnit 5

Các test này dùng JDK 17+ và JUnit Jupiter; chúng không kiểm tra số lần predicate được gọi mà kiểm tra **đầu ra được bảo đảm**:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class DropWhileTest {

    @Test
    void dropsOnlyLeadingMatchingElements() {
        List<Integer> input = List.of(1, 2, 8, 3, 10);

        assertEquals(
            List.of(8, 3, 10),
            input.stream().dropWhile(n -> n < 5).toList()
        );
    }

    @Test
    void returnsEmptyWhenAllElementsMatch() {
        assertEquals(
            List.of(),
            List.of(1, 2, 3).stream()
                .dropWhile(n -> n < 5)
                .toList()
        );
    }

    @Test
    void retainsWholeStreamWhenFirstDoesNotMatch() {
        assertEquals(
            List.of(8, 1, 2),
            List.of(8, 1, 2).stream()
                .dropWhile(n -> n < 5)
                .toList()
        );
    }

    @Test
    void handlesEmptySource() {
        assertEquals(
            List.of(),
            Stream.<Integer>empty()
                .dropWhile(n -> n < 5)
                .toList()
        );
    }

    @Test
    void differsFromFiltering() {
        List<Integer> input = List.of(1, 2, 8, 3, 10);

        assertEquals(
            List.of(8, 3, 10),
            input.stream().dropWhile(n -> n < 5).toList()
        );
        assertEquals(
            List.of(8, 10),
            input.stream().filter(n -> n >= 5).toList()
        );
    }

    @Test
    void boundaryValueIsRetainedWhenPredicateIsStrict() {
        List<Integer> input = List.of(1, 2, 5, 7);

        assertEquals(
            List.of(5, 7),
            input.stream().dropWhile(n -> n < 5).toList()
        );
    }
}
```

Không nên có test dạng “predicate phải được gọi chính xác N lần” hoặc khẳng định một tập phần tử cụ thể trên unordered stream, vì đó không phải hợp đồng đầu ra được API bảo đảm.

### 12.2. Sáu lỗi thiết kế phổ biến

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `dropWhile` để bỏ mọi phần tử không hợp lệ | Phần tử không hợp lệ sau ranh giới vẫn còn | Dùng `filter` nếu cần lọc toàn bộ |
| Quên xác định encounter order | Điểm cắt không được bảo đảm | Dùng nguồn có thứ tự, hoặc `sorted` khi nghiệp vụ cần sắp xếp |
| Dùng `unordered()` khi cần ranh giới chính xác | Tập phần tử bị bỏ có thể thay đổi | Giữ ordered semantics |
| Nhầm `<` với `<=` | Mất hoặc giữ sai phần tử bằng ngưỡng | Định nghĩa rõ ranh giới trong yêu cầu và test |
| Đặt `limit` trước `dropWhile` không có chủ đích | Chỉ tìm điểm cắt trong một lát dữ liệu ban đầu | Đặt `dropWhile` trước `limit` nếu cần giới hạn phần đuôi |
| Predicate có tác dụng phụ hoặc sửa nguồn | Kết quả khó dự đoán, rủi ro khi song song | Dùng predicate thuần, không can thiệp nguồn |

## 13. Bài tập thực hành

**Bài 1 — Bỏ header đầu tệp.** Với dữ liệu:

```java
List<String> lines = List.of(
    "# generated",
    "# schema 1",
    "name,age",
    "# ghi chú trong dữ liệu",
    "An,20"
);
```

Hãy tạo danh sách giữ từ dòng `name,age` đến cuối. Giải thích vì sao dòng bắt đầu `#` ở sau vẫn nằm trong kết quả. Sau đó sửa bài toán thành “bỏ tất cả dòng bắt đầu `#`” và chọn lại phép toán phù hợp.

**Bài 2 — Mốc có bao gồm giá trị bằng không?** Cho `[2, 4, 6, 8, 3]` và ngưỡng `6`. Viết hai pipeline:

- Bỏ các phần tử đầu **nhỏ hơn** `6`. Kết quả dự kiến `[6, 8, 3]`.
- Bỏ các phần tử đầu **nhỏ hơn hoặc bằng** `6`. Kết quả dự kiến `[8, 3]`.

**Bài 3 — Phân trang.** Cho danh sách ID tăng dần `[10, 20, 30, 40, 50, 60]`, cursor `30` và kích thước trang `2`. Lấy `[40, 50]` bằng `dropWhile` và `limit`. Thử đổi thứ tự hai phép toán và giải thích kết quả khác nhau.

**Bài 4 — Dữ liệu chưa sắp xếp.** Cho `[9, 1, 5, 2, 12]`, yêu cầu “giữ các số từ `5` trở lên”. Hãy giải thích vì sao `dropWhile(n -> n < 5)` trên dãy ban đầu không đúng yêu cầu. Viết lời giải dùng `filter`. Nếu yêu cầu thêm “kết quả tăng dần”, thêm `sorted` ở vị trí thích hợp.

**Bài 5 — Đánh giá song song.** Một lập trình viên thay `stream()` bằng `parallelStream()` vì thấy có 100.000 phần tử, rồi gọi `unordered()` để cải thiện hiệu năng. Hãy phân tích sự khác nhau giữa **tính đúng** (có còn bỏ đúng tiền tố theo mốc?) và **hiệu năng** (có nhanh hơn không?). Viết lại giải pháp đúng nếu cần giữ thứ tự ID tăng dần.

## 14. Ghi nhớ khi áp dụng

| Câu hỏi trước khi dùng | Điều cần quyết định |
| --- | --- |
| Cần bỏ một tiền tố hay lọc mọi phần tử? | `dropWhile` khác `filter` |
| Stream có encounter order không? | Quy tắc tiền tố cần thứ tự xác định |
| Phần tử đầu không thỏa có được giữ lại không? | **Có** trên ordered stream |
| Sau phần tử đầu không thỏa, predicate lại đúng thì sao? | Các phần tử phía sau vẫn được giữ |
| Giá trị bằng ngưỡng có bị bỏ không? | Phụ thuộc `<` hay `<=` trong predicate |
| Có thể tất cả phần tử đều thỏa không? | Kết quả có thể rỗng; cần xử lý |
| Nguồn có thể vô hạn không? | Bảo đảm sẽ đến mốc, và terminal operation có thể kết thúc |
| Có cần `limit` sau khi bỏ tiền tố không? | Đặt theo đúng ngữ nghĩa phân trang/cắt lát |
| Có muốn chạy song song hoặc bỏ thứ tự không? | Kiểm tra lại hợp đồng và đo hiệu năng |
| Có dùng `IntStream`/`LongStream`/`DoubleStream` không? | Dùng `dropWhile` theo kiểu nguyên thủy |

`dropWhile` giúp diễn đạt trực tiếp việc **bỏ phần đầu liên tiếp thỏa điều kiện** trong pipeline Java Stream API. Để dùng đúng, hãy xác định thứ tự của nguồn, ranh giới predicate và ý nghĩa của phần đuôi sau khi cắt; sau đó mới kết hợp với `map`, `reduce`, `collect`, grouping hoặc các thao tác cắt lát khác. Tính lười và xử lý song song có thể ảnh hưởng thời điểm thực thi, tài nguyên và chi phí, nhưng không thay đổi hợp đồng tiền tố của một **ordered stream**.
