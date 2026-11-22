# Kiểm thử thứ tự, phần tử cực trị và kết quả `Optional`

> **Chương:** Gỡ lỗi và kiểm thử pipeline  
> **Module:** `JAVA_STREAM_API` — học xử lý dữ liệu khai báo bằng Java Stream API qua pipeline lazy, `filter`, `map`, `reduce`, `collect`; thực hành grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers, đồng thời nhận diện các giới hạn về trạng thái, tài nguyên và hiệu năng.

Một pipeline Stream có thể trả **đúng số lượng phần tử nhưng sai thứ tự**, tìm được **điểm cao nhất nhưng chọn sai bản ghi khi đồng hạng**, hoặc chạy tốt với nguồn có dữ liệu nhưng ném ngoại lệ khi kết quả là `Optional.empty()`. Vì thế, kiểm thử Java Stream không chỉ là so sánh một danh sách được in ra; nó phải xác nhận **ngữ nghĩa đã cam kết** của từng thao tác.

Bài này tập trung vào ba nhóm kiểm thử: **thứ tự gặp phần tử (encounter order)**, **phần tử cực trị `min`/`max`**, và **kết quả có thể vắng mặt của `Optional`**. Ta xây dựng một bộ dữ liệu có điểm đồng hạng và bản ghi bị lọc, viết phép kiểm tra độc lập với thứ tự lập lịch của luồng, rồi đối chiếu giữa Stream tuần tự và song song.

Mọi đoạn mã chạy độc lập trong bài dùng **Java 17 trở lên**. Không cần bật preview feature hoặc thêm thư viện ngoài JDK.

## 1. Xác định hợp đồng kiểm thử trước khi viết mã

Giả sử hệ thống quản lý các phiếu đánh giá có:

| Mã phiếu | Điểm | Còn hiệu lực? | Ý nghĩa |
| --- | ---: | --- | --- |
| `T-01` | 80 | Có | Phiếu đầu tiên trong danh sách nguồn. |
| `T-02` | 95 | Có | Đồng điểm cao nhất với `T-03`. |
| `T-03` | 95 | Có | Dùng để kiểm thử phá hòa. |
| `T-04` | 65 | Có | Đồng điểm thấp nhất còn hiệu lực với `T-06`. |
| `T-05` | 40 | Không | Phải bị loại trước khi tìm cực trị. |
| `T-06` | 65 | Có | Dùng để kiểm thử phá hòa ở mức điểm thấp. |

Các quy tắc của báo cáo:

1. Chỉ xử lý bản ghi có `active == true`.
2. Danh sách phiếu giữ nguyên **thứ tự xuất hiện trong nguồn** nếu pipeline chỉ `filter` và `map`.
3. Danh sách xếp hạng có thứ tự **điểm giảm dần, mã phiếu tăng dần**; cùng điểm phải có kết quả xác định.
4. Phiếu **thấp điểm nhất**: điểm tăng dần, nếu đồng điểm chọn mã tăng dần.
5. Phiếu **cao điểm nhất**: điểm giảm dần, nếu đồng điểm chọn mã tăng dần.
6. Nếu sau lọc không còn phiếu nào, `findFirst`, `findAny`, `min` và `max` đều trả `Optional.empty()`, không tự tạo một đối tượng giả.

Với dữ liệu ở bảng, kết quả kỳ vọng là:

```text
Thứ tự phiếu còn hiệu lực: [T-01, T-02, T-03, T-04, T-06]
Xếp hạng (điểm DESC, mã ASC): [T-02, T-03, T-01, T-04, T-06]
findFirst: T-01
Phiếu có điểm thấp nhất: T-04 (65)
Phiếu có điểm cao nhất:   T-02 (95)
Điểm min / max: 65 / 95
```

**Đừng dùng một tiêu chí kiểm thử cho mọi thao tác.** Một kết quả `findAny` có thể là **bất kỳ** phiếu còn hiệu lực, còn `findFirst` phải là `T-01` đối với nguồn `List` có thứ tự. Sự khác biệt này là hợp đồng API, không phải lỗi.

## 2. Kiểm thử thứ tự: `filter`, `map`, `toList`

Với `List`, Stream có **encounter order** theo thứ tự phần tử của danh sách. Các thao tác `filter` và `map` thông thường không thay đổi thứ tự của các phần tử còn lại.

```java
import java.util.List;

record Ticket(String id, int score, boolean active) {}

List<Ticket> tickets = List.of(
        new Ticket("T-01", 80, true),
        new Ticket("T-02", 95, true),
        new Ticket("T-03", 95, true),
        new Ticket("T-04", 65, true),
        new Ticket("T-05", 40, false),
        new Ticket("T-06", 65, true)
);

List<String> activeIds = tickets.stream()
        .filter(Ticket::active)
        .map(Ticket::id)
        .toList();

System.out.println(activeIds);
// [T-01, T-02, T-03, T-04, T-06]
```

Kiểm thử **thứ tự** nên so sánh danh sách đầy đủ:

```java
List<String> expected = List.of(
        "T-01", "T-02", "T-03", "T-04", "T-06");

if (!activeIds.equals(expected)) {
    throw new AssertionError("Sai thứ tự phần tử");
}
```

Chỉ kiểm `activeIds.size() == 5` là chưa đủ: một pipeline vô tình `sorted()` cũng có thể trả năm phần tử nhưng vi phạm yêu cầu giữ thứ tự đầu vào.

### Thứ tự phần tử khác thứ tự gọi callback

Ví dụ:

```java
List<String> parallelIds = tickets.parallelStream()
        .filter(Ticket::active)
        .map(Ticket::id)
        .toList();

System.out.println(parallelIds);
// [T-01, T-02, T-03, T-04, T-06]
```

Với nguồn `List` có thứ tự và pipeline không bỏ encounter order, `Stream.toList()` giữ thứ tự kết quả, kể cả ở chế độ song song. Điều này **không** có nghĩa các lời gọi `map` của từng phần tử sẽ chạy theo đúng thứ tự ấy hoặc trên cùng một thread.

Tránh đưa side effect bắt buộc vào `map`, `filter` hoặc `peek` rồi kiểm thử bằng thứ tự in log: có những pipeline có thể tối ưu bỏ qua bước trung gian hoặc ngắn mạch. Hãy kiểm tra **giá trị đầu ra**, không phụ thuộc dấu vết lập lịch.

## 3. `findFirst` và `findAny`: kiểm thử hai hợp đồng khác nhau

`findFirst()` lấy phần tử đầu tiên **theo encounter order** nếu nguồn có thứ tự. `findAny()` được phép trả **một phần tử bất kỳ**, nhằm tạo thêm lựa chọn tối ưu, nhất là khi chạy song song.

```java
import java.util.Optional;

Optional<Ticket> first = tickets.stream()
        .filter(Ticket::active)
        .findFirst();

Optional<Ticket> any = tickets.parallelStream()
        .filter(Ticket::active)
        .findAny();

System.out.println(first.map(Ticket::id).orElse("NONE")); // T-01
// Không cam kết any là T-01 hay một mã cụ thể.
```

Kiểm thử đúng:

```java
// findFirst có expected value cụ thể vì nguồn List có thứ tự.
check(first.isPresent(), "Phải có phiếu còn hiệu lực");
check(first.orElseThrow().id().equals("T-01"), "findFirst sai");

// findAny chỉ cần là một phần tử đáp ứng predicate.
check(any.isPresent(), "findAny không được rỗng ở nguồn này");
check(any.orElseThrow().active(), "findAny trả phiếu không hợp lệ");
check(activeIds.contains(any.orElseThrow().id()),
        "findAny trả phiếu ngoài tập phù hợp");
```

`check(...)` là một hàm kiểm tra sẽ được định nghĩa trong chương trình hoàn chỉnh ở mục 7; đoạn trên minh họa cách viết điều kiện kiểm thử.

**Không nên viết** `check(any.orElseThrow().id().equals("T-01"))`: điều này biến một lựa chọn thường gặp của implementation thành điều kiện bắt buộc, gây test chập chờn hoặc sai đặc tả.

Nếu nguồn bị gắn `unordered()` hoặc vốn không có encounter order, `findFirst` không thể khẳng định là phần tử “đầu” theo quy tắc thứ tự của ứng dụng. Khi thật sự cần “đầu tiên theo thời gian”, hãy **sắp xếp theo timestamp và khóa phá hòa** hoặc dùng một nguồn có thứ tự đã được xác định.

## 4. Kiểm thử `min`, `max` với điểm đồng hạng

`Stream.min(comparator)` và `Stream.max(comparator)` trả `Optional<T>`. Khi **nhiều phần tử được comparator xem là bằng nhau**, chỉ kiểm tra điểm số vẫn chưa chứng minh rằng bản ghi được chọn đúng theo quy tắc nghiệp vụ.

Giả sử chỉ so điểm:

```java
import java.util.Comparator;

Comparator<Ticket> byScore = Comparator.comparingInt(Ticket::score);

Optional<Ticket> highestScore = tickets.stream()
        .filter(Ticket::active)
        .max(byScore);

check(highestScore.isPresent(), "Không có điểm cao nhất");
check(highestScore.orElseThrow().score() == 95, "Sai điểm max");
```

Ở đây `T-02` và `T-03` đều có điểm 95. Nếu comparator chỉ xét điểm, hai phiếu **so sánh bằng nhau**, nên không được coi việc nhận đúng một trong hai ID là hợp đồng có thể giữ ổn định khi đổi cách chia hoặc thứ tự nguồn.

### Đặt tiêu chí phá hòa rõ ràng

Với **điểm thấp nhất** và yêu cầu mã tăng dần khi đồng điểm:

```java
Comparator<Ticket> minOrder = Comparator
        .comparingInt(Ticket::score)
        .thenComparing(Ticket::id);

Ticket lowest = tickets.stream()
        .filter(Ticket::active)
        .min(minOrder)
        .orElseThrow();

System.out.println(lowest.id()); // T-04
```

Với **điểm cao nhất** và cũng muốn mã tăng dần khi đồng điểm, `max` phải ưu tiên **mã nhỏ hơn** trong các phiếu cùng điểm. Một cách diễn đạt là đảo comparator ở tiêu chí phụ:

```java
Comparator<Ticket> maxOrder = Comparator
        .comparingInt(Ticket::score)
        .thenComparing(Ticket::id, Comparator.reverseOrder());

Ticket highest = tickets.stream()
        .filter(Ticket::active)
        .max(maxOrder)
        .orElseThrow();

System.out.println(highest.id()); // T-02
```

Lý do: `max` chọn phần tử được comparator xem là “lớn nhất”. Khi điểm cùng là 95, `Comparator.reverseOrder()` khiến mã `"T-02"` được ưu tiên hơn `"T-03"` theo thứ tự chọn cực đại.

Đừng viết `Comparator.comparingInt(Ticket::score).thenComparing(Ticket::id)` rồi gọi `max` và **mong chọn mã nhỏ nhất**: comparator đó sẽ ưu tiên mã **lớn nhất** khi điểm bằng nhau.

### Dùng `sorted(...).findFirst()` để đọc đúng thứ tự xếp hạng

Khi đã có một quy tắc xếp hạng **điểm giảm dần, mã tăng dần**, có thể viết:

```java
Comparator<Ticket> ranking = Comparator
        .comparingInt(Ticket::score)
        .reversed()
        .thenComparing(Ticket::id);

List<String> rankingIds = tickets.stream()
        .filter(Ticket::active)
        .sorted(ranking)
        .map(Ticket::id)
        .toList();

System.out.println(rankingIds);
// [T-02, T-03, T-01, T-04, T-06]
```

`sorted(ranking).findFirst()` sẽ chọn `T-02`, giống kết quả `max(maxOrder)` với dữ liệu trên. Tuy nhiên, nếu chỉ cần **một cực trị**, `min`/`max` thường phù hợp hơn vì không cần sắp xếp toàn bộ dữ liệu như `sorted`.

## 5. Kiểm thử cực trị phải loại dữ liệu không hợp lệ trước

Dòng `T-05` có điểm 40 nhưng không còn hiệu lực. Vì vậy:

```java
int allMin = tickets.stream()
        .mapToInt(Ticket::score)
        .min()
        .orElseThrow();
// 40 — không đúng nếu bài toán chỉ xét phiếu active.

int activeMin = tickets.stream()
        .filter(Ticket::active)
        .mapToInt(Ticket::score)
        .min()
        .orElseThrow();
// 65 — đúng theo yêu cầu.
```

Khi kiểm thử, cần có ít nhất **một bản ghi bị lọc mà nếu quên lọc sẽ thay đổi kết quả**. Nếu dữ liệu test toàn là `active == true`, cả phiên bản đúng và phiên bản quên `filter` đều có thể vượt qua kiểm thử.

Tương tự, có thể thử nguồn chứa **hai giá trị cực trị cùng điểm** để bắt lỗi thiếu tie-break. Các test phải được thiết kế để phân biệt mã đúng với mã sai, không chỉ để có vài con số đẹp.

## 6. `Optional<T>` và `OptionalInt`: kiểm thử cả trường hợp vắng mặt

Các thao tác sau có thể không tìm thấy kết quả:

| Thao tác | Kiểu kết quả | Khi nào rỗng? |
| --- | --- | --- |
| `stream.findFirst()` | `Optional<T>` | Stream sau lọc không có phần tử. |
| `stream.findAny()` | `Optional<T>` | Stream không có phần tử. |
| `stream.min(comparator)` | `Optional<T>` | Không có phần tử để so sánh. |
| `stream.max(comparator)` | `Optional<T>` | Không có phần tử để so sánh. |
| `intStream.min()` | `OptionalInt` | Không có giá trị `int`. |
| `intStream.max()` | `OptionalInt` | Không có giá trị `int`. |
| `longStream.average()` | `OptionalDouble` | Không có phần tử để lấy trung bình. |

Ví dụ nguồn có dữ liệu, nhưng **sau lọc rỗng**:

```java
Optional<Ticket> none = tickets.stream()
        .filter(Ticket::active)
        .filter(t -> t.score() > 100)
        .findFirst();

check(none.isEmpty(), "Không thể có điểm > 100");
```

### `orElse`, `orElseGet` và `orElseThrow`

```java
String label = none.map(Ticket::id).orElse("(không có)");
System.out.println(label); // (không có)

Ticket fallback = none.orElseGet(
        () -> new Ticket("NONE", 0, false));
System.out.println(fallback.id()); // NONE
```

`orElse(defaultValue)` nhận giá trị đã được tính khi gọi phương thức, trong khi `orElseGet(supplier)` chỉ gọi supplier khi `Optional` rỗng. Điều này đáng kiểm thử nếu việc tạo giá trị mặc định đắt tiền hoặc có side effect.

Khi **không có kết quả là lỗi nghiệp vụ**, dùng:

```java
Ticket required = tickets.stream()
        .filter(t -> t.active() && t.id().equals("T-02"))
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException("Không tìm thấy phiếu T-02"));
```

Không gọi `get()` hoặc `getAsInt()` trên một `Optional` chưa kiểm tra chỉ vì dữ liệu mẫu hiện có phần tử. Cần có test cho **nguồn rỗng** và **nguồn sau lọc rỗng**.

### `OptionalInt` không phải `Optional<Integer>`

```java
import java.util.OptionalInt;

OptionalInt highest = tickets.stream()
        .filter(Ticket::active)
        .mapToInt(Ticket::score)
        .max();

System.out.println(highest.orElse(-1)); // 95

OptionalInt absent = tickets.stream()
        .filter(t -> t.active() && t.score() > 100)
        .mapToInt(Ticket::score)
        .max();

System.out.println(absent.isEmpty());   // true
System.out.println(absent.orElse(-1));  // -1
```

Giá trị `-1` ở đây chỉ là **chính sách mặc định của ví dụ**, không phải giá trị `max` mà Java tự trả khi rỗng. Trong một hệ thống chỉ cho điểm 0–100, `-1` có thể được dùng để hiển thị “không có dữ liệu”; với nghiệp vụ khác, nên giữ `OptionalInt` hoặc dùng thông báo riêng.

## 7. Chương trình Java 17+ hoàn chỉnh với bộ kiểm thử

Lưu mã sau thành `StreamOrderingOptionalTests.java`. Chương trình sử dụng `record`, `List.of`, `Stream.toList` và `Optional.isEmpty`, đều có trong Java 17. Mỗi ca kiểm thử có điều kiện cụ thể và ném `AssertionError` khi sai, nên **không cần bật `-ea`**.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class StreamOrderingOptionalTests {

    record Ticket(String id, int score, boolean active) {
        Ticket {
            Objects.requireNonNull(id, "id");
            if (id.isBlank()) {
                throw new IllegalArgumentException("ID phải có nội dung");
            }
            if (score < 0 || score > 100) {
                throw new IllegalArgumentException("Điểm ngoài miền 0..100");
            }
        }
    }

    // Xếp hạng: điểm giảm dần, mã tăng dần.
    private static final Comparator<Ticket> RANK_ORDER =
            Comparator.comparingInt(Ticket::score)
                    .reversed()
                    .thenComparing(Ticket::id);

    // min: điểm thấp nhất; cùng điểm chọn mã nhỏ nhất.
    private static final Comparator<Ticket> MIN_ORDER =
            Comparator.comparingInt(Ticket::score)
                    .thenComparing(Ticket::id);

    // max: điểm cao nhất; cùng điểm chọn mã nhỏ nhất.
    private static final Comparator<Ticket> MAX_ORDER =
            Comparator.comparingInt(Ticket::score)
                    .thenComparing(Ticket::id, Comparator.reverseOrder());

    static List<Ticket> fixture() {
        return List.of(
                new Ticket("T-01", 80, true),
                new Ticket("T-02", 95, true),
                new Ticket("T-03", 95, true),
                new Ticket("T-04", 65, true),
                new Ticket("T-05", 40, false),
                new Ticket("T-06", 65, true)
        );
    }

    static Stream<Ticket> active(
            List<Ticket> source, boolean parallel) {
        Objects.requireNonNull(source, "source");
        Stream<Ticket> stream =
                parallel ? source.parallelStream() : source.stream();
        return stream.filter(Ticket::active);
    }

    static List<String> rankedIds(
            List<Ticket> source, boolean parallel) {
        return active(source, parallel)
                .sorted(RANK_ORDER)
                .map(Ticket::id)
                .toList();
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void testEncounterOrder() {
        List<Ticket> data = fixture();
        List<String> expected = List.of(
                "T-01", "T-02", "T-03", "T-04", "T-06");
        List<String> expectedRanking = List.of(
                "T-02", "T-03", "T-01", "T-04", "T-06");

        for (boolean parallel : new boolean[] {false, true}) {
            List<String> ids = active(data, parallel)
                    .map(Ticket::id)
                    .toList();
            check(ids.equals(expected), "Sai encounter order");
            check(rankedIds(data, parallel).equals(expectedRanking),
                    "Sai thứ tự xếp hạng");

            Optional<Ticket> first =
                    active(data, parallel).findFirst();
            check(first.isPresent(), "Thiếu phiếu đầu tiên");
            check(first.orElseThrow().id().equals("T-01"),
                    "findFirst không giữ encounter order");

            Optional<Ticket> any = active(data, parallel).findAny();
            check(any.isPresent(), "findAny không được rỗng");
            check(any.orElseThrow().active(), "findAny trả phiếu inactive");
            check(expected.contains(any.orElseThrow().id()),
                    "findAny nằm ngoài tập đầu vào hợp lệ");
            // Tuyệt đối không ép findAny phải bằng T-01.
        }
    }

    static void testExtremes() {
        List<Ticket> data = fixture();
        for (boolean parallel : new boolean[] {false, true}) {
            Ticket minimum = active(data, parallel)
                    .min(MIN_ORDER).orElseThrow();
            Ticket maximum = active(data, parallel)
                    .max(MAX_ORDER).orElseThrow();

            check(minimum.id().equals("T-04"), "Sai min/tie-break");
            check(minimum.score() == 65, "Sai điểm min");
            check(maximum.id().equals("T-02"), "Sai max/tie-break");
            check(maximum.score() == 95, "Sai điểm max");

            OptionalInt minScore = active(data, parallel)
                    .mapToInt(Ticket::score).min();
            OptionalInt maxScore = active(data, parallel)
                    .mapToInt(Ticket::score).max();

            check(minScore.orElse(-1) == 65, "Sai OptionalInt min");
            check(maxScore.orElse(-1) == 95, "Sai OptionalInt max");
        }

        // Nếu comparator chỉ xét điểm, ID của phiếu đồng hạng
        // không phải phần ta được phép khẳng định.
        Ticket tied = data.stream()
                .filter(Ticket::active)
                .max(Comparator.comparingInt(Ticket::score))
                .orElseThrow();
        check(tied.score() == 95, "Sai cực trị theo điểm");
    }

    static void testOptionalAbsent() {
        List<Ticket> source = fixture();
        Optional<Ticket> none = source.stream()
                .filter(t -> t.active() && t.score() > 100)
                .findFirst();
        check(none.isEmpty(), "Điều kiện bất khả thi vẫn có kết quả");
        check(none.map(Ticket::id).orElse("NONE").equals("NONE"),
                "Sai fallback");

        List<Ticket> empty = List.of();
        check(active(empty, false).findFirst().isEmpty(),
                "Nguồn rỗng có findFirst");
        check(active(empty, true).findAny().isEmpty(),
                "Nguồn rỗng có findAny");
        check(active(empty, false).min(MIN_ORDER).isEmpty(),
                "Nguồn rỗng có min");
        check(active(empty, true).max(MAX_ORDER).isEmpty(),
                "Nguồn rỗng có max");

        OptionalInt noScore = active(empty, false)
                .mapToInt(Ticket::score).max();
        check(noScore.isEmpty(), "Nguồn rỗng có OptionalInt max");
        check(noScore.orElse(-1) == -1, "Sai giá trị mặc định");

        // Nguồn không rỗng nhưng đã bị filter loại hết.
        List<Ticket> onlyInactive =
                List.of(new Ticket("T-X", 0, false));
        check(active(onlyInactive, true).findFirst().isEmpty(),
                "Nguồn bị lọc hết mà vẫn có phiếu");

        // Optional.stream() tạo 0 hoặc 1 phần tử để xử lý tiếp.
        check(none.stream().map(Ticket::id).toList().isEmpty(),
                "Optional rỗng phải cho Stream rỗng");
        check(active(source, false).min(MIN_ORDER)
                .stream().map(Ticket::id).toList()
                .equals(List.of("T-04")), "Optional có giá trị");

        // orElseGet chỉ chạy supplier khi Optional rỗng.
        AtomicInteger fallbackCalls = new AtomicInteger();
        Ticket present = active(source, false).findFirst()
                .orElseGet(() -> {
                    fallbackCalls.incrementAndGet();
                    return new Ticket("NONE", 0, false);
                });
        check(present.id().equals("T-01"), "Sai phần tử có sẵn");
        check(fallbackCalls.get() == 0, "Supplier chạy khi đã có giá trị");

        Ticket replacement = none.orElseGet(() -> {
            fallbackCalls.incrementAndGet();
            return new Ticket("NONE", 0, false);
        });
        check(replacement.id().equals("NONE"), "Sai fallback rỗng");
        check(fallbackCalls.get() == 1, "Supplier không chạy đúng một lần");

        boolean thrown = false;
        try {
            none.orElseThrow(NoSuchElementException::new);
        } catch (NoSuchElementException expected) {
            thrown = true;
        }
        check(thrown, "orElseThrow không ném lỗi cho Optional rỗng");
    }

    static void testPermutationInvariants() {
        List<Ticket> reversed = new ArrayList<>(fixture());
        Collections.reverse(reversed);

        // Gặp phần tử đầu tiên phụ thuộc encounter order.
        check(active(reversed, false).findFirst()
                .orElseThrow().id().equals("T-06"),
                "Đảo nguồn phải đổi findFirst");

        // Các quy tắc xếp hạng và cực trị có phá hòa
        // không được phụ thuộc vị trí đầu vào.
        List<String> expectedRanking = List.of(
                "T-02", "T-03", "T-01", "T-04", "T-06");
        for (boolean parallel : new boolean[] {false, true}) {
            check(rankedIds(reversed, parallel).equals(expectedRanking),
                    "Ranking đổi khi đảo nguồn");
            check(active(reversed, parallel).min(MIN_ORDER)
                    .orElseThrow().id().equals("T-04"),
                    "Min đổi khi đảo nguồn");
            check(active(reversed, parallel).max(MAX_ORDER)
                    .orElseThrow().id().equals("T-02"),
                    "Max đổi khi đảo nguồn");
        }
    }

    public static void main(String[] args) {
        testEncounterOrder();
        testExtremes();
        testOptionalAbsent();
        testPermutationInvariants();

        System.out.println("Thứ tự active: "
                + active(fixture(), false).map(Ticket::id).toList());
        System.out.println("Xếp hạng: " + rankedIds(fixture(), false));
        System.out.println("Phiếu cao nhất: "
                + active(fixture(), false).max(MAX_ORDER)
                .orElseThrow().id());
        System.out.println("ALL STREAM TESTS PASS");
    }
}
```

Để thực hành trên máy có JDK 17 trở lên:

```text
javac StreamOrderingOptionalTests.java
java StreamOrderingOptionalTests
```

Đầu ra kỳ vọng:

```text
Thứ tự active: [T-01, T-02, T-03, T-04, T-06]
Xếp hạng: [T-02, T-03, T-01, T-04, T-06]
Phiếu cao nhất: T-02
ALL STREAM TESTS PASS
```

Đây là mã minh họa và bộ kiểm thử tự chứa cho người học; **không đồng nghĩa chương trình đã được biên dịch hoặc chạy** trong bước biên soạn Markdown. Kiểm thử trong `main` dùng `AssertionError` để thất bại rõ ràng, thay vì phụ thuộc cấu hình `assert` của JVM.

## 8. Ma trận trường hợp biên cần kiểm thử

| Nhóm | Tình huống | Kết luận đúng |
| --- | --- | --- |
| Encounter order | Nguồn `List`, `filter` rồi `map` | `toList()` giữ thứ tự của các phần tử còn lại. |
| Song song | Cùng nguồn `List`, `parallelStream().toList()` | Thứ tự **kết quả** giữ encounter order, không cam kết thứ tự chạy lambda. |
| `findFirst` | `List` có phần tử hợp lệ | Đúng phần tử đầu theo thứ tự nguồn. |
| `findAny` | Cùng dữ liệu, nhất là parallel | Kết quả thuộc tập thỏa predicate; không ép một ID cố định. |
| `min`/`max` | Có hai phần tử đồng điểm | Phải kiểm quy tắc phá hòa nếu nghiệp vụ yêu cầu một ID cụ thể. |
| Lọc trước cực trị | Bản ghi inactive có điểm nhỏ hơn active | `min` chỉ xét những bản ghi hợp lệ. |
| Nguồn rỗng | Không có phần tử | `findFirst`, `findAny`, `min`, `max` trả `Optional.empty()`. |
| Sau lọc rỗng | Nguồn ban đầu không rỗng | Kết quả tìm kiếm và cực trị vẫn là Optional rỗng. |
| Primitive | `IntStream.max()` với nguồn rỗng | `OptionalInt.empty()`, không có `0` hay `-1` mặc định. |
| `orElseGet` | Optional có sẵn giá trị | Supplier không được gọi. |
| Đảo thứ tự nguồn | Đảo `List` | `findFirst` có thể đổi; ranking và cực trị có tie-break phải giữ quy tắc. |
| Map/Set unordered | Nguồn không có encounter order | Không kiểm một thứ tự duyệt cố định khi API không cam kết. |

**Một nguyên tắc quan trọng:** các khẳng định trong bộ kiểm thử phải xuất phát từ yêu cầu thật, không xuất phát từ một lần chạy quan sát được. Ví dụ, không chụp đầu ra `parallelStream().forEach(System.out::println)` làm snapshot rồi đòi tất cả lần chạy tiếp theo phải in theo đúng lịch đó.

## 9. Kiểm thử bất biến theo hoán vị và tính xác định

Khi mục tiêu là “chọn phiếu có điểm cao nhất, phá hòa bằng mã nhỏ nhất”, kết quả **không được đổi** nếu chỉ đảo vị trí các bản ghi trong danh sách. Đây là một phép **kiểm thử bất biến theo hoán vị** (*metamorphic testing*).

```text
Nguồn A: T-01, T-02, T-03, T-04, T-05, T-06
Nguồn B: T-06, T-05, T-04, T-03, T-02, T-01

max với tie-break:       T-02 ở cả hai nguồn
min với tie-break:       T-04 ở cả hai nguồn
ranking có tie-break:    cùng danh sách sắp xếp
findFirst:               T-01 ở A, T-06 ở B
```

Đây là bốn phát biểu **khác nhau**. Nếu viết test `findFirst(A) == findFirst(B)`, test đã nhầm ngữ nghĩa nguồn; nếu viết test “max trả bất kỳ phiếu 95 điểm” trong khi hợp đồng bắt buộc ưu tiên ID nhỏ nhất, test lại **quá yếu**.

### Kiểm thử một quy tắc tổng thứ tự

Để kết quả ranking xác định, comparator nên phân biệt được những trường hợp cần phân biệt. Trong dữ liệu mẫu, `score` và `id` tạo thứ tự có phá hòa. Nếu hai bản ghi có cùng cả `score` và `id` nhưng lại là hai đối tượng khác nhau về thuộc tính quan trọng khác, comparator vẫn xem chúng tương đương.

Khi đó cần xác định rõ:

- Hai bản ghi cùng ID có được phép tồn tại không?
- Nếu có, thuộc tính nào quyết định thứ tự giữa chúng?
- Trường hợp comparator trả `0` có nghĩa hai bản ghi **tương đương theo nghiệp vụ**, hay chỉ do thiếu tiêu chí phụ?

Không thêm `thenComparing` ngẫu nhiên chỉ để làm kết quả có vẻ ổn định. Tie-break phải phản ánh quy tắc nghiệp vụ hoặc một khóa định danh ổn định.

## 10. Khi nào không nên kiểm một thứ tự cụ thể?

### `forEach` trên parallel stream

```java
List.of("A", "B", "C").parallelStream()
        .forEach(System.out::print);
```

Không được khẳng định kết quả console luôn là `ABC`. `forEach` không cam kết encounter order trong pipeline song song.

Nếu phải bảo đảm thứ tự tiêu thụ:

```java
List.of("A", "B", "C").parallelStream()
        .forEachOrdered(System.out::print); // ABC
```

`forEachOrdered` giữ thứ tự khi nguồn có encounter order, nhưng không có nghĩa mọi phần tử được tính toán trước đó đều tuần tự. Khi cần kiểm thử dữ liệu, ưu tiên một **giá trị trả về** như `toList()` thay vì kiểm thứ tự in log.

### `unordered()` và nguồn không có thứ tự

```java
List<String> result = List.of("C", "A", "B").stream()
        .unordered()
        .toList();
```

`unordered()` cho phép bỏ ràng buộc encounter order; đừng khẳng định kết quả luôn ở cùng một thứ tự, kể cả khi một số lần chạy thực tế vẫn trả `[C, A, B]`. Với nguồn `HashSet`, thứ tự duyệt cũng không phải hợp đồng có thể dùng làm tiêu chí nghiệp vụ.

Nếu cần một thứ tự **xác định**, thêm `sorted(comparator)` phù hợp với miền dữ liệu trước khi thu thập. Đừng dựa vào thứ tự HashMap, hash code, danh sách thread hoặc kết quả một lần chạy làm nguồn chân lý.

## 11. Gỡ lỗi pipeline: kiểm theo giai đoạn nhưng không thay đổi ngữ nghĩa

Một pipeline phức tạp nên được gỡ lỗi bằng những **đầu ra trung gian có chủ đích**. Ví dụ, trước khi gọi `min`, có thể tạo một danh sách các phần tử hợp lệ:

```java
List<Ticket> eligible = tickets.stream()
        .filter(Ticket::active)
        .toList();

check(eligible.size() == 5, "Sai bước lọc");
check(eligible.stream().map(Ticket::id).toList().equals(
        List.of("T-01", "T-02", "T-03", "T-04", "T-06")),
        "Sai thứ tự sau lọc");

Ticket minimum = eligible.stream()
        .min(minOrder)
        .orElseThrow();
check(minimum.id().equals("T-04"), "Sai min");
```

Trong đoạn minh họa này, `tickets`, `Ticket`, `check` và `minOrder` là các tên từ các ví dụ trước. `eligible` là một **danh sách đã vật hóa** nên có thể tạo Stream mới nhiều lần để kiểm từng giai đoạn. Đừng giữ một biến `Stream<Ticket> s` rồi gọi liên tiếp `s.toList()` và `s.min(...)`: một Stream đã qua terminal operation không được tái sử dụng.

### `peek` chỉ hỗ trợ quan sát có điều kiện

```java
List<String> ids = tickets.stream()
        .filter(Ticket::active)
        .peek(t -> System.out.println("active: " + t.id()))
        .map(Ticket::id)
        .toList();
```

Trong ví dụ tuần tự, `peek` có thể giúp quan sát dữ liệu đang chảy qua pipeline. Tuy nhiên, không được coi số dòng log là một điều kiện đúng đắn của chương trình: Stream được phép tối ưu các thao tác trung gian khi không ảnh hưởng kết quả terminal. Trên parallel stream, log có thể xuất hiện theo thứ tự khác. **Kiểm thử sản phẩm bằng giá trị đầu ra**, còn `peek` là công cụ hỗ trợ chẩn đoán.

### Có nên dùng JUnit?

Chương trình hoàn chỉnh ở mục 7 dùng `check` để chạy độc lập không cần thư viện. Khi đưa vào dự án thực tế, nên tách từng trường hợp thành test riêng với framework như JUnit:

- Một test cho encounter order.
- Một test cho `findFirst` và một test khác cho `findAny`.
- Một test cho `min`/tie-break và một test cho `max`/tie-break.
- Các test cho Optional rỗng, nguồn rỗng và các fallback.
- Test so sánh tuần tự–song song và hoán vị nguồn.

Không cần kiểm cả số thread được tạo hoặc số lần gọi callback của một phép `findAny`: đó là chi tiết thực thi, không phải hợp đồng kết quả của Stream API.

## 12. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách kiểm thử/khắc phục |
| --- | --- | --- |
| Kiểm riêng số phần tử mà không so thứ tự | Pipeline sắp xếp sai vẫn có thể qua test | So sánh danh sách đầu ra đầy đủ nếu thứ tự là yêu cầu. |
| Ép `findAny` trả phần tử đầu tiên | Test sai hợp đồng, có thể chập chờn khi parallel | Kiểm kết quả thuộc tập hợp thỏa predicate. |
| Giả định `max` chọn mã nhỏ nhất khi comparator chỉ so điểm | Kết quả đồng hạng không xác định theo yêu cầu | Thêm tiêu chí phá hòa vào comparator. |
| Gọi `max` với comparator điểm tăng + ID tăng mà mong ID nhỏ | Thực tế ưu tiên ID lớn khi đồng điểm | Đảo comparator ở riêng tiêu chí ID hoặc dùng ranking + `findFirst`. |
| Quên `filter` trước `min` | Bản ghi không hợp lệ có thể trở thành cực trị | Đặt fixture có điểm thấp/cao bất thường nhưng inactive. |
| Gọi `Optional.get()` không kiểm tra rỗng | `NoSuchElementException` | Dùng `isPresent`, `orElseGet`, `orElseThrow` với chính sách rõ. |
| Xem `orElse(-1)` là hành vi mặc định của `OptionalInt` | Hiểu sai API và có thể che giấu thiếu dữ liệu | Kiểm `isEmpty` trước khi chọn sentinel nghiệp vụ. |
| Quên test sau lọc rỗng | Chỉ pass khi nguồn có phần tử phù hợp | Thêm test nguồn rỗng và nguồn có tất cả phần tử bị lọc. |
| Lấy thứ tự `forEach` song song làm expected | Test phụ thuộc lập lịch | Dùng `forEachOrdered` khi cần thứ tự, hoặc kiểm `toList()`. |
| Dùng `HashSet` rồi đòi `findFirst` cố định | Nguồn không có encounter order xác định | Sắp xếp nguồn hoặc dùng `List` có thứ tự. |
| Dùng lại cùng Stream sau terminal operation | `IllegalStateException` | Tạo Stream mới từ nguồn có thể duyệt lại. |
| Biến kiểm thử thành một phép đo hiệu năng | Tốc độ chạy một lần không nói lên tính đúng | Phân biệt kiểm thử ngữ nghĩa với benchmark, dùng công cụ đo phù hợp khi cần. |

## 13. Bài tập tự luyện

**Bài 1 — Thứ tự sau lọc.** Với `List.of(4, 1, 6, 2, 5)`, lọc số chẵn và nhân đôi. Kết quả của `toList()` trên Stream tuần tự là gì?

```java
List<Integer> values = List.of(4, 1, 6, 2, 5);
List<Integer> result = values.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 2)
        .toList();
// [8, 12, 4]
```

**Bài 2 — `findFirst` và `findAny`.** Với `List.of("A", "B", "C")`, kết quả `findFirst` nào phải đúng? Có được khẳng định `parallelStream().findAny()` luôn là `"A"` không?

**Đáp án:** `findFirst()` trên nguồn có thứ tự phải là `"A"`; `findAny()` có thể trả phần tử bất kỳ trong danh sách và không có cam kết luôn là `"A"`.

**Bài 3 — Đồng hạng.** Cho ba phiếu `X` 90 điểm, `A` 90 điểm, `Z` 85 điểm. Hãy lấy phiếu có điểm cao nhất và mã tăng dần khi đồng điểm.

```java
Ticket best = tickets.stream()
        .max(Comparator.comparingInt(Ticket::score)
                .thenComparing(Ticket::id, Comparator.reverseOrder()))
        .orElseThrow();
// Với dữ liệu X=90, A=90, Z=85: best.id() là "A".
```

Trong đoạn này, `tickets` được hiểu là danh sách của đề bài nhỏ, không phải fixture ở mục 7.

**Bài 4 — Không có dữ liệu.** Nếu `List.of(5, 10, 20).stream().filter(n -> n > 30).findFirst()` trả Optional rỗng, biểu thức `.orElse(-1)` sẽ cho gì?

**Đáp án:** `-1`. Giá trị này do người gọi chỉ định; Stream không tự trả `-1` khi không tìm thấy phần tử.

**Bài 5 — Primitive cực trị.** `IntStream.empty().min()` trả kiểu nào, và gọi `getAsInt()` ngay sẽ ra sao?

**Đáp án:** Trả `OptionalInt.empty()`; gọi `getAsInt()` khi rỗng ném `NoSuchElementException`. Có thể kiểm `isPresent`, dùng `orElse`, hoặc `orElseThrow` theo nghiệp vụ.

**Bài 6 — Đảo nguồn.** Đảo thứ tự tất cả phiếu ở mục 1. Giá trị `min`, `max` có comparator phá hòa và danh sách ranking có thay đổi không? `findFirst` có thay đổi không?

**Đáp án:** Cực trị và ranking không đổi vì comparator đã xác định quy tắc độc lập với vị trí. `findFirst` đổi theo encounter order: phiếu đầu tiên còn hiệu lực của danh sách đảo là `T-06`.

**Bài 7 — Chuyển một Optional thành Stream.** Với `Optional<Ticket> best`, tạo danh sách chứa 0 hoặc 1 ID mà không cần `if (best.isPresent())`.

```java
List<String> ids = best.stream()
        .map(Ticket::id)
        .toList();
```

Với `Optional.empty()`, danh sách rỗng; với Optional có giá trị, danh sách chứa một ID. `Optional.stream()` có từ Java 9.

## 14. Ghi nhớ

- **Encounter order** là thuộc tính của nguồn và pipeline: với `List`, `filter`/`map`/`toList` giữ thứ tự các phần tử còn lại; thứ tự chạy callback song song có thể khác.
- `findFirst` phải theo encounter order của nguồn có thứ tự; `findAny` chỉ cam kết chọn một phần tử hợp lệ, **không** cam kết chọn phần tử đầu.
- `min`/`max` cần comparator tương thích **tiêu chí nghiệp vụ và tie-break**. Nếu chỉ so điểm, không ép ID cố định trong ca đồng hạng.
- `Optional` và `OptionalInt` có thể rỗng sau lọc hoặc trên nguồn rỗng; kiểm tra cả các nhánh có dữ liệu và không có dữ liệu, xác định rõ chính sách fallback hoặc ngoại lệ.
- Các kiểm thử vững chắc bao gồm **so thứ tự**, **kiểm tra cực trị đồng hạng**, **Optional rỗng**, **đảo nguồn**, và **đối chiếu tuần tự/song song**; không khẳng định những hành vi mà API không bảo đảm.
