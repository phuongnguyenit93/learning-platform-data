# Collectors.collectingAndThen và hoàn thiện đầu ra của Stream

## 1. Khi nào cần `collectingAndThen`?

Trong Java Stream API, `Collectors.collectingAndThen` là một **collector adapter**: nó nhận một collector có sẵn, để collector đó tích lũy dữ liệu, rồi áp dụng thêm **một phép biến đổi sau khi thu thập xong** nhằm tạo kết quả cuối cùng.

Cú pháp tổng quát:

```java
Collector<T, ?, RR> adapted =
        Collectors.collectingAndThen(downstream, finisher);

RR result = stream.collect(adapted);
```

Đây là đoạn cú pháp minh họa: các kiểu `T`, `RR` và hai biến `downstream`/`finisher` cần được khai báo trong ngữ cảnh thực tế.

Ý nghĩa hai tham số:

- **`downstream`:** `Collector` thực hiện việc thu thập, như `toList()`, `counting()`, `averagingInt()`, `maxBy()`, `groupingBy()`.
- **`finisher`:** `Function` chuyển kết quả **đã hoàn thành** của downstream thành kiểu hoặc hình thức đầu ra mong muốn: danh sách không sửa được, chuỗi trình bày, DTO, giá trị lấy ra từ `Optional`, kết quả kiểm tra hoặc cấu trúc lồng nhau.

Chữ ký API hiện hành (từ Java 8):

```java
public static <T, A, R, RR> Collector<T, A, RR> collectingAndThen(
        Collector<T, A, R> downstream,
        Function<R, RR> finisher)
```

| Ký hiệu | Vai trò |
| --- | --- |
| `T` | Kiểu phần tử đầu vào của Stream |
| `A` | Kiểu vùng chứa trung gian khi downstream thu thập |
| `R` | Kiểu kết quả downstream trước bước hoàn thiện |
| `RR` | Kiểu kết quả cuối sau khi chạy finisher |

**Điểm cốt lõi:** `finisher` được gọi sau khi downstream hoàn tất công việc thu thập. Nó **không chạy một lần cho mỗi phần tử**. Với một phép `stream.collect(collectingAndThen(...))` ở cấp ngoài cùng, nó hoàn thiện kết quả của phép thu thập đó. Nếu đặt `collectingAndThen` làm downstream của `groupingBy` thì finisher lồng trong được áp dụng cho **kết quả của từng nhóm**, không phải cho toàn bộ bản đồ một lần.

Ví dụ trực quan:

```text
Stream<T>
  └── collect(
        collectingAndThen(
            toList(),          // gom tất cả phần tử thành List<T>
            List::copyOf       // chuyển List<T> thành List<T> không sửa được
        )
      )
                  ↓
             List<T> đầu ra
```

Không dùng `collectingAndThen` chỉ vì muốn biến đổi **từng phần tử**. Trường hợp đó, `map(...)` là lựa chọn chính xác:

```java
List<String> result = names.stream()
        .map(String::trim)    // chạy cho từng tên
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf   // chạy sau khi toàn bộ danh sách đã được thu thập
        ));
```

Đây là đoạn minh họa trong ngữ cảnh đã có `List<String> names`.

## 2. Vì sao cần hoàn thiện đầu ra sau khi thu thập?

Những tình huống phổ biến:

1. **Khóa cấu trúc kết quả**: tạo danh sách/map không cho người nhận thêm, sửa hoặc xóa phần tử.
2. **Đổi kiểu kết quả**: thu thập thành `Double` rồi định dạng thành `String`, hoặc biến `Optional<T>` thành một đối tượng phù hợp quy tắc nghiệp vụ.
3. **Kiểm tra và chuẩn hóa kết quả tổng thể**: sau khi đã có toàn bộ dữ liệu, xác minh ràng buộc liên quan đến cả tập, sắp xếp và tạo bản sao đầu ra.
4. **Hoàn thiện từng nhóm**: `groupingBy` tạo các nhóm, còn `collectingAndThen` ở downstream làm mỗi nhóm thành một danh sách không sửa được.
5. **Đóng gói cấu trúc trả về**: xây một DTO/record từ tổng, số lượng hoặc thống kê đã được tính.

So sánh:

| Cách viết | Kết quả và ngữ nghĩa |
| --- | --- |
| `stream.collect(toList())` | Thu thập một `List`, nhưng API `Collectors.toList()` **không cam kết** có thể sửa hay không thể sửa, kiểu triển khai hoặc thread-safety |
| `stream.collect(collectingAndThen(toList(), List::copyOf))` | Thu thập rồi trả `List` không sửa được, không chứa `null` |
| `stream.collect(toUnmodifiableList())` | Thu trực tiếp thành `List` không sửa được, từ Java 10, từ chối `null` |
| `stream.toList()` | Terminal operation từ Java 16, trả `List` không sửa được; không phải collector adapter |
| `stream.collect(collectingAndThen(counting(), n -> "Count=" + n))` | Thu số lượng thành `Long`, sau đó định dạng `String` |

Nếu chỉ cần một danh sách không sửa được, với Java 17+ thường có thể chọn **`stream.toList()`** hoặc **`Collectors.toUnmodifiableList()`** để biểu đạt gọn hơn. `collectingAndThen` phát huy tác dụng khi cần **kết hợp một downstream cụ thể với logic hoàn thiện riêng**.

## 3. Mẫu 1: tạo danh sách không thể sửa từ kết quả thu thập

```java
List<String> immutableNames = names.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf));
```

Đây là đoạn minh họa trong ngữ cảnh có `List<String> names`. `List.copyOf` có từ Java 10:

- Danh sách trả về **không cho thêm, xóa hay thay phần tử**; các thao tác sửa thông thường ném `UnsupportedOperationException`.
- `List.copyOf` không nhận các phần tử `null`; nếu đầu ra downstream chứa `null`, bước hoàn thiện ném `NullPointerException`.
- Không cam kết đối tượng danh sách luôn là bản sao vật lý mới. `List.copyOf` có thể tái sử dụng một danh sách đầu vào đã không sửa được.
- Nếu các phần tử bên trong là đối tượng mutable, `List.copyOf` **không biến chúng thành immutable**. Nó chỉ bảo vệ cấu trúc danh sách.

Một lựa chọn tương thích Java 8:

```java
List<String> readonlyNames = names.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                Collections::unmodifiableList));
```

`Collections.unmodifiableList` tạo **view không sửa được** trên danh sách được đưa vào; nếu một mã khác có tham chiếu tới danh sách bên dưới và thay đổi nó thì view cũng phản ánh thay đổi. Trong ví dụ `toList()` thông thường, danh sách tích lũy được tạo riêng và không lộ cho bên ngoài, nhưng vẫn cần hiểu khác biệt giữa **wrapper view** và **bản sao không sửa được**.

Nếu chỉ cần đầu ra không sửa được trên Java 17+, tránh thêm adapter khi đã có `Collectors.toUnmodifiableList()` hoặc `Stream.toList()` đáp ứng chính xác yêu cầu.

## 4. Mẫu 2: chuyển kết quả tổng hợp sang định dạng cuối

Ví dụ: muốn hiển thị điểm trung bình với một chữ số thập phân:

```java
String averageDisplay = tasks.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.averagingInt(Task::points),
                value -> String.format(Locale.ROOT, "%.1f", value)));
```

Đoạn trên giả sử đã có `List<Task> tasks`, `record Task(..., int points)` và import liên quan.

Luồng tính toán là:

```text
Task(3), Task(4), Task(5)
     ↓ averagingInt(Task::points)
            Double 4.0
     ↓ value -> String.format(Locale.ROOT, "%.1f", value)
            String "4.0"
```

`Locale.ROOT` giúp ví dụ tạo dấu thập phân ổn định khi chạy ở máy có locale khác nhau.

**Cẩn thận nguồn rỗng:** `Collectors.averagingInt(...)` cho kết quả `0.0` nếu không có phần tử. Đây là hợp đồng collector, **không tự động có nghĩa điểm trung bình nghiệp vụ của tập rỗng bằng 0**. Nếu nghiệp vụ yêu cầu “không có dữ liệu” thay vì số 0, hãy chọn downstream khác (chẳng hạn gom thành danh sách rồi kiểm tra rỗng), hoặc dùng `summarizingInt` để biết `count` trước khi quyết định.

Ví dụ minh họa kiểm tra số lượng:

```java
String display = tasks.stream().collect(Collectors.collectingAndThen(
        Collectors.summarizingInt(Task::points),
        stats -> stats.getCount() == 0
                ? "N/A"
                : String.format(Locale.ROOT, "%.1f", stats.getAverage())
));
```

Ở đây finisher là nơi hợp lý để áp dụng **quy tắc hiển thị dựa trên toàn bộ kết quả**.

## 5. Mẫu 3: hoàn thiện `Optional` từ `minBy` / `maxBy`

`maxBy` và `minBy` trả về `Optional<T>` vì tập dữ liệu có thể rỗng. `collectingAndThen` giúp định nghĩa đầu ra nghiệp vụ rõ ràng ngay trong pipeline.

Ví dụ lựa chọn công việc có điểm lớn nhất; nếu không có công việc thì trả `"none"`:

```java
Collector<Task, ?, String> topTitle = Collectors.collectingAndThen(
        Collectors.maxBy(Comparator.comparingInt(Task::points)),
        option -> option.map(Task::title).orElse("none"));

String title = tasks.stream().collect(topTitle);
```

Đây là đoạn minh họa trong ngữ cảnh đã khai báo `Task`, `tasks` và import `java.util.*`, `java.util.stream.*`.

| Nguồn | Kết quả downstream | Kết quả cuối từ finisher |
| --- | --- | --- |
| Danh sách Task có điểm lớn nhất 5 | `Optional.of(Task(..., "Auth", 5))` | `"Auth"` |
| Stream rỗng | `Optional.empty()` | `"none"` |

Nếu **không có kết quả phải là lỗi**, chọn:

```java
option -> option.orElseThrow(
        () -> new IllegalStateException("Danh sách công việc rỗng"))
```

Không dùng `Optional.get()` khi có thể gặp nguồn rỗng. `Optional.orElseThrow(Supplier)` có từ Java 8, là cách rõ nghĩa để biểu thị tình huống thiếu kết quả. Ngoài ra cần quyết định chính sách **trường hợp bằng điểm**: nếu có nhiều phần tử cùng giá trị lớn nhất, cần tiêu chí phụ để chọn một kết quả xác định thay vì dựa vào thứ tự thực thi song song.

## 6. Mẫu 4: hoàn thiện đầu ra của `groupingBy`

Phân nhóm theo đội rồi lấy danh sách tên công việc. Nếu chỉ viết:

```java
Map<String, List<String>> grouped = tasks.stream().collect(
        Collectors.groupingBy(
                Task::team,
                Collectors.mapping(Task::title, Collectors.toList())));
```

Kết quả là một `Map` chứa nhiều `List`, nhưng không có bảo đảm chuẩn của API rằng các container kết quả đã được khóa chống sửa.

### 6.1. Chỉ khóa từng danh sách trong nhóm

```java
Map<String, List<String>> grouped = tasks.stream().collect(
        Collectors.groupingBy(
                Task::team,
                Collectors.mapping(
                        Task::title,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                List::copyOf))));
```

Mỗi **danh sách của từng nhóm** sẽ không sửa được. Tuy nhiên **Map bao ngoài vẫn có thể sửa** nếu loại map được dùng cho phép; không được suy ra “các giá trị khóa rồi thì toàn Map cũng khóa”.

### 6.2. Khóa cả Map và danh sách bên trong

```java
Collector<Task, ?, Map<String, List<String>>> byTeam =
        Collectors.collectingAndThen(
                Collectors.groupingBy(
                        Task::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Task::title,
                                Collectors.collectingAndThen(
                                        Collectors.toList(),
                                        List::copyOf))),
                Collections::unmodifiableMap);

Map<String, List<String>> output = tasks.stream().collect(byTeam);
```

Đoạn này giả sử `Task`, `tasks` và các import đã tồn tại. Có **hai tầng hoàn thiện**:

1. `collectingAndThen(toList(), List::copyOf)` bên trong `mapping` chạy cho **mỗi nhóm**, tạo các `List` không sửa được.
2. `collectingAndThen(groupingBy(...), Collections::unmodifiableMap)` bên ngoài chạy sau khi Map được thu thập xong, trả Map không sửa được.

`TreeMap::new` được chọn khi muốn **thứ tự khóa có quy tắc** (ở đây là thứ tự tự nhiên của `String`). `Collections.unmodifiableMap` là wrapper của Map đã thu thập, nhờ đó giữ được cách duyệt của `TreeMap`; `Map.copyOf` không hứa giữ thứ tự duyệt của Map đầu vào.

Với `Task` là record chứa các `String` và `int`, Map cùng danh sách tên có thể được xem là cấu trúc read-only hợp lý. Với các phần tử là đối tượng mutable, hai tầng bảo vệ container **không phải deep immutable của mọi object**. Muốn deep immutable đúng nghĩa cần thiết kế hoặc sao chép chính các phần tử.

## 7. Ví dụ hoàn chỉnh Java 17+ có thể biên dịch và chạy

Tạo tệp **`CollectingAndThenDemo.java`**:

```java
import java.util.*;
import java.util.stream.*;
import static java.util.stream.Collectors.*;

public class CollectingAndThenDemo {
    record Task(String team, String title, int points) {}

    private static boolean rejectsListChange(List<String> values) {
        try {
            values.add("extra");
            return false;
        } catch (UnsupportedOperationException expected) {
            return true;
        }
    }

    private static boolean rejectsMapChange(Map<String, List<String>> values) {
        try {
            values.put("C", List.of("Other"));
            return false;
        } catch (UnsupportedOperationException expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        List<String> names = Stream.of("An", "Binh", "Chi")
                .collect(collectingAndThen(toList(), List::copyOf));
        System.out.println("names=" + names);
        System.out.println("namesUnmodifiable=" + rejectsListChange(names));

        List<Task> tasks = List.of(
                new Task("A", "API", 3),
                new Task("B", "UI", 4),
                new Task("A", "Auth", 5));

        String average = tasks.stream().collect(collectingAndThen(
                averagingInt(Task::points),
                value -> String.format(Locale.ROOT, "%.1f", value)));
        System.out.println("average=" + average);

        Comparator<Task> byPoints = Comparator.comparingInt(Task::points);
        Collector<Task, ?, String> topTitle = collectingAndThen(
                maxBy(byPoints),
                option -> option.map(Task::title).orElse("none"));
        System.out.println("topTitle=" + tasks.stream().collect(topTitle));
        System.out.println("emptyTopTitle=" + Stream.<Task>empty().collect(topTitle));

        Collector<Task, ?, Map<String, List<String>>> byTeam =
                collectingAndThen(
                        groupingBy(Task::team, TreeMap::new,
                                mapping(Task::title,
                                        collectingAndThen(toList(), List::copyOf))),
                        Collections::unmodifiableMap);

        Map<String, List<String>> groups = tasks.stream().collect(byTeam);
        System.out.println("groups=" + groups);
        System.out.println("nestedUnmodifiable=" +
                (rejectsMapChange(groups) && rejectsListChange(groups.get("A"))));
        System.out.println("parallelEqualsSequential=" +
                groups.equals(tasks.parallelStream().collect(byTeam)));
        System.out.println("emptyGroups=" + Stream.<Task>empty().collect(byTeam));

        Collector<String, ?, List<String>> freezingCollector =
                collectingAndThen(toList(), List::copyOf);
        System.out.println("identityFinish=" + freezingCollector.characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));
    }
}
```

Chạy:

```bash
javac CollectingAndThenDemo.java
java CollectingAndThenDemo
```

Kết quả chuẩn:

```text
names=[An, Binh, Chi]
namesUnmodifiable=true
average=4.0
topTitle=Auth
emptyTopTitle=none
groups={A=[API, Auth], B=[UI]}
nestedUnmodifiable=true
parallelEqualsSequential=true
emptyGroups={}
identityFinish=false
```

Giải thích kết quả:

- `namesUnmodifiable=true` vì `List.copyOf` tạo danh sách không cho thêm/xóa phần tử.
- `average=4.0` do ba điểm 3, 4 và 5.
- `topTitle=Auth` là Task có điểm lớn nhất; `emptyTopTitle=none` chứng minh finisher xử lý được `Optional.empty()`.
- `groups={A=[API, Auth], B=[UI]}` vì tên nhóm được sắp theo `TreeMap` và thứ tự tên công việc trong từng nhóm theo thứ tự gặp của nguồn có thứ tự.
- `nestedUnmodifiable=true` vì không thể `put` vào Map và không thể `add` vào danh sách trong nhóm.
- `parallelEqualsSequential=true` là so sánh cùng dữ liệu và cùng collector trên hai pipeline. Đây là bằng chứng kiểm thử ví dụ cụ thể, không phải tuyên bố mọi collector tùy biến luôn an toàn song song.
- `emptyGroups={}`: `groupingBy` trên Stream rỗng tạo Map rỗng và finisher bên ngoài vẫn trả Map rỗng không sửa được.
- `identityFinish=false`: vì adapter có bước hoàn thiện thực sự, không thể đánh dấu `IDENTITY_FINISH` để cho phép bỏ qua nó.

## 8. Nguồn rỗng: kiểm tra hợp đồng của downstream trước

`collectingAndThen` **không tự định nghĩa** kết quả khi Stream rỗng. Downstream làm việc đó trước, rồi finisher nhận kết quả.

| Downstream | Kết quả với Stream rỗng | Finisher ví dụ | Kết quả đầu ra |
| --- | --- | --- | --- |
| `toList()` | Danh sách rỗng | `List::copyOf` | Danh sách rỗng không sửa được |
| `counting()` | `0L` | `count -> "Total=" + count` | `"Total=0"` |
| `averagingInt(Task::points)` | `0.0` | Định dạng một chữ số thập phân | `"0.0"` |
| `maxBy(comparator)` | `Optional.empty()` | `o -> o.orElseThrow(...)` | Ném exception do nghiệp vụ |
| `maxBy(comparator)` | `Optional.empty()` | `o -> o.orElse(defaultValue)` | Trả giá trị dự phòng |
| `groupingBy(key)` | Map rỗng | `Collections::unmodifiableMap` | Map rỗng không sửa được |

**Cách chọn chuẩn:** Kiểm tra hành vi downstream rỗng trước, rồi định nghĩa rõ finisher sẽ trả kết quả dự phòng, báo lỗi hay biểu diễn “không có dữ liệu”. Đừng chỉ dựa vào test có phần tử.

Ví dụ minh họa muốn báo lỗi nếu danh sách rỗng:

```java
List<String> requiredNames = Stream.<String>empty().collect(
        Collectors.collectingAndThen(
                Collectors.toList(),
                list -> {
                    if (list.isEmpty()) {
                        throw new IllegalArgumentException("Phải có ít nhất một tên");
                    }
                    return List.copyOf(list);
                }));
```

Đoạn code trên sẽ ném `IllegalArgumentException` theo chính quy tắc đã viết trong finisher. Đây là ví dụ có chủ đích cho nhánh lỗi, không phải chương trình thành công.

## 9. Song song, thứ tự, `Collector.Characteristics` và chi phí

### 9.1. Khi song song, finisher nằm ở cuối quá trình thu thập

Một `parallelStream()` có thể tích lũy vào các vùng chứa trung gian rồi kết hợp chúng. Đối với `collect(collectingAndThen(downstream, finisher))` cấp ngoài, **finisher hoàn thiện kết quả đã hợp nhất**, không áp dụng lên từng phần tử, và không phải hàm combiner. Không viết finisher với kỳ vọng nó sẽ chạy riêng trên từng phân vùng song song.

Finisher nên là hàm rõ ràng, không phụ thuộc việc ai đang chạy hay trạng thái mutable bên ngoài. Nếu nó đọc một biến có thể thay đổi đồng thời, kết quả cuối có thể khó dự đoán.

### 9.2. `IDENTITY_FINISH` và các đặc tính collector

`Collector.Characteristics.IDENTITY_FINISH` nói rằng finisher có thể được bỏ qua vì kết quả tích lũy là chính kết quả trả về. `collectingAndThen` có bước biến đổi ở cuối nên **collector sau adapter không có `IDENTITY_FINISH`**, ngay cả khi downstream đã có đặc tính đó.

Các đặc tính khác như `UNORDERED` hoặc `CONCURRENT` phụ thuộc downstream và hợp đồng của collector; adapter không tự biến một collector không thread-safe thành thread-safe. Nên kiểm tra `collector.characteristics()` và tài liệu API, không suy luận từ tên phương thức.

### 9.3. Duy trì thứ tự dữ liệu

- `toList()` khi dùng cho nguồn có encounter order (như `List`) bảo toàn thứ tự gặp phần tử theo hợp đồng collector.
- `TreeMap::new` giúp Map có thứ tự khóa xác định; `HashMap` không cam kết thứ tự duyệt. `Map.copyOf` cũng không cam kết giữ thứ tự duyệt từ nguồn.
- Với nguồn unordered hoặc downstream có đặc tính unordered, không ép unit test kỳ vọng thứ tự cố định nếu API không bảo đảm.
- Một collector đúng hợp đồng vẫn có thể cho kết quả tương đương khi chạy song song, nhưng thời gian chạy không nhất thiết nhanh hơn.

### 9.4. Tránh biến finisher thành tác vụ nặng không cần thiết

`collectingAndThen(toList(), List::copyOf)` có thể phải duyệt/sao chép cấu trúc dữ liệu để tạo kết quả không sửa được. Nếu chỉ muốn unmodifiable list, `Stream.toList()`/`toUnmodifiableList()` thường đơn giản hơn. Khi finisher cần sắp xếp, xác minh cả tập hoặc đóng gói DTO thì chi phí đó là phần hợp lý của yêu cầu.

Nếu finisher cần sắp xếp bản thu thập, có thể viết:

```java
List<String> sorted = names.stream().collect(
        Collectors.collectingAndThen(Collectors.toList(), list -> {
            list.sort(Comparator.naturalOrder());
            return List.copyOf(list);
        }));
```

`list.sort(...)` chạy trên danh sách đã gom xong. `List.copyOf` khóa kết quả cuối. Đoạn này giả định các chuỗi không `null`; nếu có null thì cần chính sách so sánh và sao chép riêng.

## 10. Những lỗi dễ gặp và cách sửa

**Lỗi 1 — Nhầm finisher với phép biến đổi từng phần tử.**

`collectingAndThen(toList(), list -> ...)` nhận một **List**, không nhận lần lượt các phần tử. Để xử lý mỗi bản ghi, dùng `stream.map(...)` hoặc `Collectors.mapping(...)` khi ở bên trong downstream của `groupingBy`.

**Lỗi 2 — Chỉ khóa Map, quên danh sách con.**

`collectingAndThen(groupingBy(..., toList()), Collections::unmodifiableMap)` chỉ làm Map bên ngoài không sửa được. `List` giá trị vẫn có thể sửa. Muốn đầu ra khóa cả hai tầng, dùng `collectingAndThen(toList(), List::copyOf)` ở downstream từng nhóm **và** finisher ngoài Map.

**Lỗi 3 — Tin rằng unmodifiable đồng nghĩa với bất biến sâu.**

Một `List<PersonMutable>` không sửa được vẫn chứa các `PersonMutable` có thể đổi trạng thái. Cần tạo snapshot bất biến của phần tử (ví dụ record với thành phần bất biến) nếu nghiệp vụ yêu cầu.

**Lỗi 4 — Bỏ qua `null` khi dùng `List.copyOf`/`toUnmodifiableList`.**

Hai lựa chọn này không nhận phần tử null. Xác định chính sách: bỏ các giá trị null bằng `filter(Objects::nonNull)`, thay bằng giá trị hợp lệ, hoặc chủ động báo lỗi. Không lọc null âm thầm nếu null có ý nghĩa nghiệp vụ.

**Lỗi 5 — Dùng `orElseThrow` mà không tính trường hợp rỗng.**

`maxBy`/`minBy` trả Optional rỗng trên nguồn rỗng. Finisher dùng `orElseThrow(...)` sẽ ném lỗi. Đây là hành vi hợp lệ **nếu được yêu cầu**, nhưng phải có test kiểm tra nhánh rỗng.

**Lỗi 6 — Cho rằng mọi `collectingAndThen` đều cần thiết.**

Nếu đã có `Collectors.toUnmodifiableList()`, không cần kết hợp `toList()` với `List::copyOf` chỉ để khóa danh sách. Nếu mục tiêu là chuyển từng phần tử sang tên, hãy dùng `map`. Dùng adapter cho việc **hoàn thiện kết quả tổng**.

**Lỗi 7 — Tin rằng kết quả song song luôn có thứ tự ngẫu nhiên hoặc luôn nhanh hơn.**

Kết quả và encounter order phụ thuộc nguồn, các thao tác và collector. Test theo hợp đồng: so giá trị hay thứ tự chỉ khi API bảo đảm. Đánh giá hiệu năng qua benchmark có thiết kế tốt trên dữ liệu thực, không qua một lần bấm chạy.

**Lỗi 8 — Cố dùng finisher để sửa shared state bên ngoài.**

Với logic tính toán thuần, finisher nên nhận giá trị downstream và trả giá trị mới. Hạn chế thay đổi biến toàn cục, gọi hệ thống bên ngoài hoặc cố ghi log dùng làm bằng chứng số lần thực thi. Ngoại lệ có thể có ở tích hợp nghiệp vụ chủ đích, nhưng nên tách side effect khỏi pipeline thu thập để dễ kiểm thử.

## 11. Checklist áp dụng trong dự án

- [ ] Downstream nào thực sự cần thiết, và kiểu `R` của nó là gì?
- [ ] Muốn đầu ra là kiểu `RR` nào: List không sửa được, DTO, String, hay giá trị lấy từ Optional?
- [ ] Finisher có xử lý nguồn rỗng theo nghiệp vụ không?
- [ ] Có phần tử null không? `List.copyOf`/`toUnmodifiableList` có phù hợp không?
- [ ] Nếu kết quả là Map chứa List, cần khóa một tầng hay cả hai tầng?
- [ ] Có yêu cầu encounter order hay thứ tự khóa của Map không?
- [ ] Khi dùng song song, downstream có hợp đồng phù hợp không? Finisher có thuần và dễ dự đoán không?
- [ ] Test đã xác minh cả giá trị trả về, khả năng không sửa được và các nhánh rỗng/lỗi chưa?
- [ ] Trên Java 17+, liệu `toUnmodifiableList()` hoặc `Stream.toList()` đã đủ đơn giản hơn chưa?

## Tự luyện tập

1. Thu thập `Stream.of("A", "BB", "CCC")` bằng `collectingAndThen(counting(), n -> "Items: " + n)`. Kết quả là gì? **`"Items: 3"`**.
2. `Stream.<String>empty().collect(collectingAndThen(maxBy(Comparator.naturalOrder()), o -> o.orElse("N/A")))` cho ra gì? **`"N/A"`**.
3. Một `groupingBy` có `collectingAndThen(toList(), List::copyOf)` làm downstream có tự biến cả Map thành unmodifiable không? **Không**: các danh sách con không sửa được, Map ngoài chưa được khóa.
4. Với dữ liệu có `null`, `collectingAndThen(toList(), List::copyOf)` có luôn chạy thành công không? **Không**: `List.copyOf` ném `NullPointerException` nếu có phần tử null.
5. Dùng `collectingAndThen(toList(), List::copyOf)` trên Stream rỗng cho kết quả gì? **Danh sách rỗng không sửa được**, không phải `Optional.empty()`.

## Tài liệu tham khảo (API vẫn đang được sử dụng)

- [Oracle JDK 26 — Collectors.collectingAndThen và các Collector khác](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
- [Oracle JDK 25 — Collector và Characteristics](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.html)
- [Oracle JDK 25 — List.copyOf và unmodifiable lists](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html)
- [Oracle JDK 25 — Stream.toList và collect](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Oracle JDK 25 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html)
