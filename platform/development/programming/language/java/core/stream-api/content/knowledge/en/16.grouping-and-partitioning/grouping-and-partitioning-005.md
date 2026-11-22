# Phân hoạch theo điều kiện bằng `partitioningBy`

Trong **Java Stream API**, ta thường viết pipeline khai báo gồm nguồn dữ liệu, các phép toán trung gian *lazy* như `filter`, `map`, rồi kết thúc bằng `collect` để xây kết quả. Nếu muốn chia **toàn bộ phần tử** thành hai nhóm dựa trên một điều kiện đúng/sai, `Collectors.partitioningBy` là collector được thiết kế cho việc đó.

Ví dụ, một danh sách giao dịch cần chia thành **hợp lệ** và **không hợp lệ**, một danh sách công việc thành **đã hoàn tất** và **chưa hoàn tất**, hoặc điểm số thành **đạt** và **chưa đạt**. Thay vì lọc cùng nguồn hai lần, ta phân hoạch dữ liệu bằng một predicate và nhận `Map<Boolean, ...>`.

Trong chương **Phân nhóm và phân hoạch**, điều quan trọng không chỉ là cú pháp. Cần hiểu hai khóa `true`/`false`, khác biệt với `filter` và `groupingBy`, cách dùng downstream collector, trường hợp đầu vào rỗng, thứ tự, tài nguyên và giới hạn khi chạy song song.

## 1. Phân hoạch nghĩa là chia thành hai phần bổ sung nhau

Giả sử tập dữ liệu là:

```text
Điểm:       45  90  60  32  75
Điều kiện:  điểm >= 60
               |
               +-- true  -> [90, 60, 75]
               +-- false -> [45, 32]
```

Với mỗi phần tử `x`, predicate `p(x)` trả đúng **một giá trị boolean**. Nếu `p(x) == true`, phần tử thuộc nhánh `true`; ngược lại thuộc nhánh `false`. Hai nhánh **không giao nhau** theo từng lần đánh giá và hợp lại thành toàn bộ đầu vào.

Điều kiện này khác với việc gọi `filter(p)`: `filter` **loại bỏ** những phần tử không thỏa điều kiện, còn `partitioningBy(p)` **giữ cả hai phía** để ta có thể kiểm tra, báo cáo hoặc xử lý riêng.

Ví dụ tối thiểu:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(45, 90, 60, 32, 75);

Map<Boolean, List<Integer>> byPassing = scores.stream()
    .collect(Collectors.partitioningBy(score -> score >= 60));

System.out.println(byPassing.get(true));  // [90, 60, 75]
System.out.println(byPassing.get(false)); // [45, 32]
```

Đừng nhầm ý nghĩa của khóa: `true` có nghĩa **predicate trả true**, không mặc định có nghĩa “tốt”, “thành công” hoặc “hợp lệ”. Nếu viết `score -> score < 60`, lúc ấy `true` lại là nhóm **chưa đạt**.

## 2. Hai overload của `Collectors.partitioningBy`

`partitioningBy` thuộc `java.util.stream.Collectors` từ Java 8, có hai overload khái quát:

```java
static <T> Collector<T, ?, Map<Boolean, List<T>>>
partitioningBy(Predicate<? super T> predicate);

static <T, D, A> Collector<T, ?, Map<Boolean, D>>
partitioningBy(
    Predicate<? super T> predicate,
    Collector<? super T, A, D> downstream
);
```

Trong chữ ký trên:

- `T`: kiểu phần tử của stream.
- `predicate`: hàm hành vi `Predicate<? super T>` nhận một phần tử và trả `boolean`.
- Overload **một tham số**: giá trị trong map là `List<T>` gồm các phần tử thuộc từng nhánh.
- Overload **hai tham số**: `downstream` quyết định **kiểu kết quả `D` của mỗi nhánh**. Nó có thể là số đếm, tổng, danh sách đã ánh xạ, thống kê hoặc một map nhóm con.

Lưu ý: `partitioningBy` **tạo collector**, còn `stream.collect(collector)` là **terminal operation** kích hoạt việc duyệt stream. Collector không nhận một collection có sẵn làm identity; cơ chế thu thập quản lý container tích lũy và cách kết hợp chúng.

## 3. Phân biệt `filter`, `partitioningBy` và `groupingBy`

Ba API thường được đặt cạnh nhau nhưng giải quyết các bài toán khác nhau:

| Công cụ | Kết quả điển hình | Đặc điểm | Dùng khi |
| --- | --- | --- | --- |
| `filter(predicate)` | `Stream<T>` chỉ còn phần tử thỏa điều kiện | Là phép trung gian lazy; phần tử không thỏa bị bỏ qua | Chỉ cần **một phía** của điều kiện. |
| `partitioningBy(predicate)` | `Map<Boolean, List<T>>` | Phân mọi phần tử thành **hai nhánh true/false** | Cần cả nhóm đạt và không đạt. |
| `groupingBy(classifier)` | `Map<K, List<T>>` | Phân nhóm theo khóa tổng quát `K` | Cần **nhiều nhóm**, ví dụ mã phòng ban hoặc trạng thái. |

Nếu sử dụng `groupingBy(score -> score >= 60)`, khóa cũng là `Boolean`, nhưng có một khác biệt quan trọng: `groupingBy` **không bắt buộc tạo khóa cho nhóm không xuất hiện**. Trái lại, `partitioningBy` **luôn có cả khóa `true` và `false`**, kể cả khi một nhóm không nhận phần tử.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(80, 90, 100);

Map<Boolean, List<Integer>> partitioned = scores.stream()
    .collect(Collectors.partitioningBy(score -> score >= 60));

Map<Boolean, List<Integer>> grouped = scores.stream()
    .collect(Collectors.groupingBy(score -> score >= 60));

System.out.println(partitioned.containsKey(false)); // true
System.out.println(partitioned.get(false));         // []
System.out.println(grouped.containsKey(false));     // false
```

Vì lý do này, `partitioningBy` rất tiện khi hiển thị bảng báo cáo có **hai hạng mục cố định**, dù một trong hai hạng mục hiện không có dữ liệu.

Không nên gọi `filter(p)` và `filter(p.negate())` trên cùng **một đối tượng Stream**: sau terminal operation thứ nhất, stream đã bị tiêu thụ. Có thể tạo stream mới từ `List` cho mỗi lần lọc, nhưng như vậy phải xử lý nguồn nhiều lần và có thể cho ảnh chụp dữ liệu khác nhau nếu nguồn thay đổi.

## 4. Hai khóa vẫn tồn tại khi một nhánh hoặc cả nguồn rỗng

Đây là một phần của **hợp đồng** `partitioningBy`, không phải hành vi ngẫu nhiên của một triển khai JDK:

```java
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<String>> empty =
    Collections.<String>emptyList().stream()
        .collect(Collectors.partitioningBy(s -> s.length() >= 3));

System.out.println(empty.size());        // 2
System.out.println(empty.get(true));     // []
System.out.println(empty.get(false));    // []
System.out.println(empty.containsKey(true));  // true
System.out.println(empty.containsKey(false)); // true
```

Với overload có downstream collector, kết quả của một nhánh rỗng được tạo **theo hợp đồng downstream**:

| Downstream | Kết quả ở nhánh không có phần tử |
| --- | --- |
| `Collectors.toList()` | Danh sách rỗng. |
| `Collectors.counting()` | `0L`. |
| `Collectors.summingInt(...)` | `0`. |
| `Collectors.averagingInt(...)` | `0.0` theo quy ước của collector, không có nghĩa đã quan sát trung bình bằng 0. |
| `Collectors.maxBy(comparator)` | `Optional.empty()`. |
| `Collectors.summarizingInt(...)` | `IntSummaryStatistics` có `getCount() == 0`; min/max là các giá trị khởi tạo đặc biệt. |

Trước khi diễn giải `0.0` hoặc min/max của nhóm rỗng như dữ liệu thực tế, hãy kiểm tra số lượng phần tử.

## 5. Chỉ cần số lượng: `partitioningBy` kết hợp `counting`

Nếu mục tiêu là đếm số phần tử mỗi nhánh, không nên tạo danh sách chứa toàn bộ dữ liệu chỉ để gọi `.size()`. Dùng `Collectors.counting()` làm downstream:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(45, 90, 60, 32, 75);

Map<Boolean, Long> counts = scores.stream()
    .collect(Collectors.partitioningBy(
        score -> score >= 60,
        Collectors.counting()
    ));

System.out.println(counts.get(true));  // 3
System.out.println(counts.get(false)); // 2
```

Giá trị map bây giờ là **`Long`**, không phải `List<Integer>`. Không còn nhu cầu lưu từng điểm số chỉ để tính số lượng. Cả hai khóa luôn tồn tại, vì vậy `counts.get(false)` trả `0L` nếu không có người chưa đạt.

Nếu chỉ cần số lượng đạt **mà không cần số lượng chưa đạt**, `scores.stream().filter(s -> s >= 60).count()` vẫn là cách diễn đạt trực tiếp. Chọn `partitioningBy` khi cần hai phía hoặc cần phối hợp các thống kê của cả hai phía.

## 6. Tính tổng, trung bình và nhiều thống kê theo nhánh

Downstream collector cho phép biến phân hoạch thành một phép tổng hợp dữ liệu thay vì chỉ thu các phần tử:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(45, 90, 60, 32, 75);

Map<Boolean, Integer> totals = scores.stream()
    .collect(Collectors.partitioningBy(
        score -> score >= 60,
        Collectors.summingInt(Integer::intValue)
    ));

Map<Boolean, Double> averages = scores.stream()
    .collect(Collectors.partitioningBy(
        score -> score >= 60,
        Collectors.averagingInt(Integer::intValue)
    ));

System.out.println(totals.get(true));   // 225
System.out.println(totals.get(false));  // 77
System.out.println(averages.get(true)); // 75.0
System.out.println(averages.get(false)); // 38.5
```

Đây là **hai pipeline khác nhau** trên cùng `List`. Khi cần đồng thời count, sum, min, max và average **trong một lượt thu thập logic**, dùng `Collectors.summarizingInt`:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, IntSummaryStatistics> stats =
    Arrays.asList(45, 90, 60, 32, 75).stream()
        .collect(Collectors.partitioningBy(
            score -> score >= 60,
            Collectors.summarizingInt(Integer::intValue)
        ));

IntSummaryStatistics passed = stats.get(true);
System.out.println(passed.getCount());   // 3
System.out.println(passed.getSum());     // 225
System.out.println(passed.getMin());     // 60
System.out.println(passed.getMax());     // 90
System.out.println(passed.getAverage()); // 75.0
```

`IntSummaryStatistics.getSum()` trả `long`, giúp tránh tràn `int` trong nhiều trường hợp; tổng vẫn có thể vượt phạm vi `long` nếu dữ liệu cực lớn. Các thống kê `double` có thể chịu sai số dấu phẩy động. Với đầu vào rỗng, phải kiểm tra `getCount()` trước khi đọc ý nghĩa min/max/average.

## 7. Chỉ lưu trường dữ liệu cần thiết với `mapping`

Overload hai tham số đặc biệt hữu ích khi muốn **phân hoạch đối tượng nhưng chỉ giữ một trường**. Giả sử một công việc có tên và trạng thái hoàn thành:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class PartitionTaskNames {
    static final class Task {
        final String name;
        final boolean done;

        Task(String name, boolean done) {
            this.name = name;
            this.done = done;
        }
    }

    public static void main(String[] args) {
        List<Task> tasks = Arrays.asList(
            new Task("Design", true),
            new Task("Review", false),
            new Task("Test", true)
        );

        Map<Boolean, List<String>> namesByDone = tasks.stream()
            .collect(Collectors.partitioningBy(
                task -> task.done,
                Collectors.mapping(
                    task -> task.name,
                    Collectors.toList()
                )
            ));

        System.out.println(namesByDone.get(true));  // [Design, Test]
        System.out.println(namesByDone.get(false)); // [Review]
    }
}
```

`partitioningBy` đánh giá `task.done` trên **đối tượng Task gốc**. Downstream `mapping` chỉ chuyển những đối tượng thuộc mỗi nhánh thành tên. Cách này khác với việc gọi `map(task -> task.name)` *trước* `partitioningBy`: sau khi mất trường `done`, predicate có thể không còn đủ dữ liệu để phân loại.

Nếu chỉ muốn giữ các tên duy nhất, downstream có thể là `Collectors.mapping(TaskNameMapper, Collectors.toSet())`. Tuy nhiên `toSet()` không hứa thứ tự duyệt; khi cần giữ thứ tự gặp phần tử, có thể dùng `Collectors.toCollection(LinkedHashSet::new)` làm downstream sau mapping.

## 8. Lấy phần tử đặc trưng của mỗi nhánh bằng `maxBy`

Mỗi nhánh có thể cần **một** phần tử lớn nhất thay vì danh sách:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

Map<Boolean, Optional<Integer>> largest =
    Arrays.asList(45, 90, 60, 32, 75).stream()
        .collect(Collectors.partitioningBy(
            score -> score >= 60,
            Collectors.maxBy(Comparator.naturalOrder())
        ));

System.out.println(largest.get(true).orElse(-1));  // 90
System.out.println(largest.get(false).orElse(-1)); // 45
```

`Collectors.maxBy` trả một `Optional<T>` cho mỗi nhánh. Khi không có phần tử, `Optional.empty()` diễn đạt rõ hơn một giá trị đại diện như `-1`. Trong nghiệp vụ, nên xử lý tình huống vắng mặt bằng `ifPresent`, `orElse` hoặc `orElseThrow` có chủ đích.

Nếu không cần phân hoạch và chỉ muốn phần tử lớn nhất của toàn bộ stream, `stream.max(comparator)` trực tiếp hơn.

## 9. Kết hợp `groupingBy` và `partitioningBy`

Một điều kiện chỉ tạo **hai nhóm**. Khi cần phân loại theo nhiều chiều, có thể **lồng các collector**. Ví dụ, trong mỗi phòng ban cần biết số công việc hoàn thành và chưa hoàn thành:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class TeamProgress {
    static final class Task {
        final String team;
        final boolean done;

        Task(String team, boolean done) {
            this.team = team;
            this.done = done;
        }
    }

    public static void main(String[] args) {
        List<Task> tasks = Arrays.asList(
            new Task("API", true),
            new Task("API", false),
            new Task("UI", true)
        );

        Map<String, Map<Boolean, Long>> counts = tasks.stream()
            .collect(Collectors.groupingBy(
                task -> task.team,
                Collectors.partitioningBy(
                    task -> task.done,
                    Collectors.counting()
                )
            ));

        System.out.println(counts.get("API").get(true));  // 1
        System.out.println(counts.get("API").get(false)); // 1
        System.out.println(counts.get("UI").get(true));   // 1
        System.out.println(counts.get("UI").get(false));  // 0
    }
}
```

Ở tầng ngoài, `groupingBy` chỉ tạo khóa cho **phòng ban thực sự xuất hiện**. Ở tầng trong, mỗi phòng ban đã xuất hiện đều nhận **cả hai khóa boolean**, cho dù một nhánh không có task. Nếu gọi `counts.get("UNKNOWN")`, kết quả có thể là `null` vì phòng ban ấy không có trong map ngoài.

Có thể đảo thứ tự lồng nhau để nhận `Map<Boolean, Map<String, List<Task>>>` nếu ứng dụng cần xem hai trạng thái trước, rồi mới xem các nhóm. Hãy chọn hình dạng map sao cho các truy vấn thường dùng có đường truy cập rõ ràng.

## 10. Nhiều điều kiện: ranh giới của `partitioningBy`

Một predicate luôn trả `boolean`, nên mỗi lần dùng `partitioningBy` chỉ phân được **hai phía**. Nếu có ba mức điểm `FAIL`, `PASS`, `EXCELLENT`, `groupingBy` với classifier trả enum thường phù hợp hơn:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ScoreLevels {
    enum Level { FAIL, PASS, EXCELLENT }

    static Level classify(int score) {
        if (score < 60) return Level.FAIL;
        if (score < 90) return Level.PASS;
        return Level.EXCELLENT;
    }

    public static void main(String[] args) {
        List<Integer> scores = Arrays.asList(45, 90, 60, 32, 75);
        Map<Level, List<Integer>> byLevel = scores.stream()
            .collect(Collectors.groupingBy(ScoreLevels::classify));

        System.out.println(byLevel.get(Level.FAIL));      // [45, 32]
        System.out.println(byLevel.get(Level.PASS));      // [60, 75]
        System.out.println(byLevel.get(Level.EXCELLENT)); // [90]
    }
}
```

Nếu **hai điều kiện độc lập** cần được theo dõi, không nên dùng một predicate dài, khó diễn giải. Thay vào đó, có thể nhóm theo cặp trạng thái hoặc dùng cấu trúc phân loại hai tầng. Lưu ý rằng lồng `partitioningBy` hai lần sẽ tạo **bốn tổ hợp boolean**; điều này khác với phân loại ba mức loại trừ nhau.

## 11. Thứ tự phần tử, tính mutable và bảo đảm của collector

Khi nguồn có encounter order, chẳng hạn `List.stream()`, các phần tử trong từng danh sách kết quả của `partitioningBy(predicate)` giữ **thứ tự tương đối** mà chúng xuất hiện trong nguồn:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Integer>> values =
    Arrays.asList(5, 4, 3, 2, 1).stream()
        .collect(Collectors.partitioningBy(n -> n % 2 == 0));

System.out.println(values.get(true));  // [4, 2]
System.out.println(values.get(false)); // [5, 3, 1]
```

Tuy nhiên, đừng suy ra thứ tự in `entrySet()` hoặc `keySet()` của map là `false` trước `true` (hoặc ngược lại). Nếu cần một báo cáo cố định, truy cập trực tiếp `result.get(true)` và `result.get(false)` theo thứ tự mong muốn.

API không bảo đảm loại triển khai cụ thể, tính mutable, khả năng tuần tự hóa hay thread-safety của các map/danh sách trả về. Không viết logic phụ thuộc vào việc map là `HashMap` hoặc list là `ArrayList`, hay giả định kết quả luôn cho phép `put`/`add`.

Nếu cần kết quả **không sửa đổi được** ở cả map ngoài và danh sách mỗi nhánh, có thể dùng bước hoàn thiện rõ ràng trên Java 10+:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, List<Integer>> snapshot = Arrays.asList(1, 2, 3, 4)
    .stream()
    .collect(Collectors.collectingAndThen(
        Collectors.partitioningBy(
            n -> n % 2 == 0,
            Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf
            )
        ),
        Map::copyOf
    ));

System.out.println(snapshot.get(true)); // [2, 4]
// snapshot.put(true, Arrays.asList(8)); // UnsupportedOperationException
// snapshot.get(true).add(8);           // UnsupportedOperationException
```

`List.copyOf` và `Map.copyOf` từ chối phần tử/giá trị `null` trong ngữ cảnh không cho phép, và tạo kết quả không sửa đổi được nhưng **không sao chép sâu** các đối tượng phần tử mutable. Không cần bọc map theo cách này nếu ứng dụng không có yêu cầu bất biến cụ thể.

## 12. Chạy song song: predicate và downstream phải tuân thủ hợp đồng

`partitioningBy` hoạt động với cả stream tuần tự và song song:

```java
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

Map<Boolean, Long> counts = IntStream.range(0, 1_000_000)
    .parallel()
    .boxed()
    .collect(Collectors.partitioningBy(
        n -> n % 2 == 0,
        Collectors.counting()
    ));

System.out.println(counts.get(true));  // 500000
System.out.println(counts.get(false)); // 500000
```

Các nhánh song song có thể xử lý những phần nguồn khác nhau rồi kết hợp các kết quả thống kê. Nhưng **`parallel()` không bảo đảm tăng tốc**: boxing `int` sang `Integer`, chi phí chia/gộp và độ lớn nguồn đều ảnh hưởng tới hiệu năng.

Những quy tắc quan trọng:

1. **Predicate phải không can thiệp nguồn** (*non-interfering*) và, khi có thể, **không phụ thuộc trạng thái thay đổi bên ngoài** (*stateless*). Ví dụ `n -> n % 2 == 0` phù hợp; `n -> counter++ % 2 == 0` không phù hợp.
2. Không thay đổi collection nguồn trong khi pipeline đang duyệt.
3. Không thêm phần tử vào một `ArrayList` dùng chung bên ngoài lambda khi stream song song. Hãy để collector xử lý tích lũy và kết hợp.
4. Downstream như `counting`, `summingInt`, `toList` phải tuân thủ hợp đồng collector. Một collector tùy chỉnh có trạng thái chia sẻ có thể phá vỡ kết quả.
5. Không suy luận rằng predicate được chạy theo thứ tự danh sách gốc hoặc trên cùng thread. Nếu cần thứ tự xác định trong kết quả, giữ encounter order và lựa chọn collector phù hợp.

Ví dụ cần tránh:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

AtomicInteger calls = new AtomicInteger();

// SAI VỀ Ý NGHĨA: việc phân nhóm phụ thuộc lịch gọi predicate.
Map<Boolean, List<Integer>> unstable = IntStream.range(0, 100)
    .parallel()
    .boxed()
    .collect(Collectors.partitioningBy(n ->
        calls.getAndIncrement() % 2 == 0
    ));
```

Điều quan trọng là **đừng dùng** cách phân loại này. `AtomicInteger` có thể đảm bảo phép tăng là nguyên tử, nhưng không đảm bảo phần tử cụ thể được đánh giá vào thời điểm nào. Các phần tử được đưa vào nhánh nào sẽ phụ thuộc lịch xử lý song song, không phải thuộc tính ổn định của dữ liệu.

## 13. Ví dụ nghiệp vụ: báo cáo đơn hàng đủ điều kiện

Giả sử mỗi đơn hàng có mã, tổng tiền nguyên đơn vị nhỏ nhất và trạng thái thanh toán. Đơn được xem là **đủ điều kiện xử lý** khi đã thanh toán và tổng tiền lớn hơn 0. Ta vừa cần số lượng, vừa cần tổng tiền của hai phía:

```java
import java.util.Arrays;
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class OrderReport {
    static final class Order {
        final String id;
        final boolean paid;
        final long amount;

        Order(String id, boolean paid, long amount) {
            this.id = id;
            this.paid = paid;
            this.amount = amount;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
            new Order("A", true, 1200L),
            new Order("B", false, 500L),
            new Order("C", true, 800L),
            new Order("D", true, 0L)
        );

        Predicate<Order> eligible =
            order -> order.paid && order.amount > 0;

        Map<Boolean, LongSummaryStatistics> report = orders.stream()
            .collect(Collectors.partitioningBy(
                eligible,
                Collectors.summarizingLong(order -> order.amount)
            ));

        System.out.println(report.get(true).getCount()); // 2
        System.out.println(report.get(true).getSum());   // 2000
        System.out.println(report.get(false).getCount()); // 2
        System.out.println(report.get(false).getSum());   // 500
    }
}
```

Ở đây, phân hoạch chỉ quyết định **đơn thuộc phía nào**. Downstream `summarizingLong` tính tổng tất cả đơn trong từng phía, bao gồm cả đơn không đủ điều kiện nếu được đưa vào nhánh `false`. Nếu muốn biết **lý do** không đủ điều kiện (chưa thanh toán, số tiền không hợp lệ, v.v.), chỉ có Boolean là chưa đủ; cần phân nhóm theo một loại trạng thái cụ thể hoặc thu thập thêm thông tin giải thích.

## 14. Sai lầm thường gặp

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Dùng `filter` nhưng lại cần hai phía | Dữ liệu không thỏa điều kiện bị bỏ qua. | Dùng `partitioningBy` và đọc `get(true)`/`get(false)`. |
| Dùng `groupingBy(predicate)` rồi mặc định hai khóa tồn tại | Nhóm không có phần tử có thể không xuất hiện. | Dùng `partitioningBy` khi cần đúng hai khóa. |
| Cho rằng khóa `true` luôn là nhóm đạt | Phụ thuộc chính predicate. | Đặt tên predicate rõ nghĩa và ghi ý nghĩa điều kiện. |
| Thu danh sách rồi `.size()` chỉ để đếm | Tốn bộ nhớ giữ các phần tử không cần dùng. | `partitioningBy(p, counting())`. |
| Lấy trung bình `0.0` của nhánh rỗng làm kết quả đo được | Không có mẫu nhưng vẫn hiển thị như dữ liệu hợp lệ. | Kiểm tra số lượng mẫu bằng `counting` hoặc `SummaryStatistics.getCount()`. |
| Giả định map kết quả luôn có thể sửa hoặc có thứ tự duyệt cụ thể | Không có bảo đảm từ collector. | Truy cập theo hai khóa Boolean; tạo snapshot/kiểu kết quả theo yêu cầu. |
| Predicate có hiệu ứng phụ hoặc dùng bộ đếm chung | Kết quả song song không ổn định, khó kiểm thử. | Dùng predicate thuần dựa trên dữ liệu của phần tử. |
| Thu toàn bộ stream vô hạn | `collect` không kết thúc nếu không giới hạn dữ liệu. | Dùng `limit`, nguồn hữu hạn hoặc điều kiện dừng thực sự. |
| Dùng `partitioningBy` cho ba trạng thái loại trừ nhau | Kết quả chỉ có hai nhánh boolean. | Dùng `groupingBy` với enum/classifier. |

### Lưu ý về vòng đời và tài nguyên

`collect(partitioningBy(...))` là terminal operation; **cùng đối tượng `Stream` không thể tái sử dụng** sau đó. Với nguồn `Files.lines` hoặc nguồn I/O khác, cần `try-with-resources` để đóng stream; `collect` không tự đóng tất cả tài nguyên nguồn. Các phép thu thập thường cần đi qua toàn bộ nguồn hữu hạn, nên stream vô hạn phải được giới hạn trước khi phân hoạch.

## 15. Bài tập thực hành

**Bài 1 — Chia chẵn/lẻ.** Từ `IntStream.rangeClosed(1, 10).boxed()`, dùng `partitioningBy(n -> n % 2 == 0)` để lấy hai danh sách. Dự đoán `get(true) = [2, 4, 6, 8, 10]` và `get(false) = [1, 3, 5, 7, 9]`.

**Bài 2 — Trường hợp rỗng.** Từ `Stream.of(70, 80)`, phân hoạch theo `score >= 60`; kiểm tra cả `containsKey(true)` và `containsKey(false)`. Sau đó so sánh với `groupingBy(score -> score >= 60)` và giải thích vì sao map thứ hai có thể không có khóa `false`.

**Bài 3 — Thống kê.** Từ các điểm `[45, 90, 60, 32, 75]`, dùng `partitioningBy` cùng `counting`, sau đó cùng `summarizingInt`. Xác nhận nhánh đạt có 3 phần tử, tổng 225 và trung bình 75.0. Nêu cách xử lý khi không có điểm nào đạt.

**Bài 4 — Lồng nhóm.** Tạo danh sách công việc gồm `team` và `done`. Dùng `groupingBy(team, partitioningBy(done, counting()))`. Xác minh mỗi team xuất hiện có cả khóa `true` và `false`, kể cả nhánh có 0 công việc.

**Bài 5 — Lý giải song song.** Dùng `IntStream.range(0, 1000).parallel().boxed()` để đếm hai nhóm chẵn/lẻ. Thử giải thích tại sao `n -> n % 2 == 0` đáng tin cậy hơn predicate dựa trên bộ đếm `AtomicInteger`, ngay cả khi việc tăng biến đếm là an toàn luồng.

**Ghi nhớ:** `Collectors.partitioningBy(predicate)` chia dữ liệu thành **hai nhánh bổ sung nhau** với cả hai khóa Boolean luôn hiện diện. Khi cần kết quả khác `List<T>`, truyền downstream collector để đếm, tính tổng, lấy giá trị đại diện hoặc phân nhóm sâu hơn. Chọn `filter` nếu chỉ cần một phía, `groupingBy` khi có nhiều loại, và giữ predicate không phụ thuộc trạng thái chia sẻ để pipeline dễ hiểu, dễ kiểm thử và an toàn khi xử lý song song.
