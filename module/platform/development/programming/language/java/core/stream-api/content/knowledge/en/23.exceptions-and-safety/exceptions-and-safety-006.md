# Xử lý thay đổi nguồn và `ConcurrentModificationException`

Trong **Java Stream API**, việc viết `filter`, `map`, `reduce` hoặc `collect` thường dựa trên một giả định quan trọng: **nguồn dữ liệu không bị can thiệp trong lúc pipeline đang duyệt**. Nếu một lambda vừa đọc vừa xóa phần tử khỏi `ArrayList`, hoặc một thread khác thay đổi `HashMap` trong khi stream xử lý, kết quả có thể là `ConcurrentModificationException` (CME), dữ liệu thiếu, dữ liệu không nhất quán, hoặc một lỗi khó tái hiện.

Bài này thuộc chương **Ngoại lệ và tính an toàn**. Mục tiêu không phải tìm cách “né ngoại lệ” bằng `try/catch`, mà là hiểu hợp đồng *non-interference*, phân biệt các loại nguồn, thiết kế snapshot đúng thời điểm, và kiểm thử kết quả an toàn với nguồn mutable, nguồn snapshot và nguồn concurrent.

## 1. Ví dụ mở đầu: vừa duyệt vừa sửa danh sách

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4, 5));

// SAI: sửa chính nguồn mà Stream đang duyệt.
values.stream().forEach(n -> {
    if (n % 2 == 0) {
        values.remove(n);
    }
});
```

Một lần chạy có thể ném `ConcurrentModificationException`, nhưng không có hợp đồng nào bảo đảm **mọi lần** đều ném, hoặc ngoại lệ xuất hiện ở cùng vị trí. Vấn đề gốc là code **sửa collection trong khi pipeline đang duyệt chính collection đó**.

Hai cách sửa đúng tùy mục tiêu:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4, 5));

// Cách A: không sửa nguồn; trả danh sách mới (Java 16+).
List<Integer> odds = source.stream()
    .filter(n -> n % 2 != 0)
    .toList();

System.out.println(source); // [1, 2, 3, 4, 5]
System.out.println(odds);   // [1, 3, 5]

// Cách B: thực sự muốn xóa tại chỗ, ngoài một traversal Stream.
source.removeIf(n -> n % 2 == 0);
System.out.println(source); // [1, 3, 5]
```

**Câu hỏi thiết kế đầu tiên:** dữ liệu nguồn phải giữ nguyên để dùng tiếp, hay ứng dụng thực sự muốn thay đổi collection gốc? Hãy chọn API theo nhu cầu này trước khi nghĩ đến thread và hiệu năng.

## 2. CME là dấu hiệu gì, và không bảo đảm điều gì?

`java.util.ConcurrentModificationException` là ngoại lệ runtime báo rằng một collection hoặc cấu trúc dữ liệu đã phát hiện thay đổi không phù hợp khi đang được duyệt. Với nhiều collection thông thường, iterator/spliterator có cơ chế *fail-fast*: phát hiện thay đổi cấu trúc dựa trên trạng thái theo dõi sửa đổi của nguồn.

Những điểm cần hiểu:

1. CME **có thể xảy ra trong một thread duy nhất**. Tên “Concurrent” không chứng minh có nhiều thread.
2. Phát hiện fail-fast thường là **best-effort**, không phải một hợp đồng rằng mọi thay đổi trái phép đều bị phát hiện.
3. **Không ném CME không có nghĩa code đúng hoặc thread-safe**. Race và dữ liệu không nhất quán vẫn có thể xảy ra.
4. CME **không rollback** các side effect đã xảy ra trong pipeline, như cập nhật database, ghi tệp, gửi HTTP.
5. Bắt CME rồi thử lại **không phải cách thay thế** cho khóa, snapshot, hoặc việc thiết kế dữ liệu bất biến.

| Hiện tượng | Ý nghĩa cần xem xét |
| --- | --- |
| CME khi dùng `ArrayList.stream()` | Có thể có thay đổi cấu trúc trong lúc traversal. |
| CME khi dùng `HashMap.entrySet().stream()` | Có thể có thêm/xóa entry không phù hợp. |
| Không có CME nhưng kết quả sai | Có thể do data race, side effect, mapper phụ thuộc trạng thái hoặc nguồn weakly consistent. |
| `IllegalStateException` khi dùng lại Stream | Stream đã bị tiêu thụ; là vấn đề khác với CME. |
| `UnsupportedOperationException` khi sửa danh sách kết quả | Danh sách có thể là unmodifiable; không nên nhầm với CME. |

**Quy tắc:** hãy dùng CME làm **tín hiệu để điều tra lỗi**, không dùng nó như một phép kiểm tra tính nhất quán hay cơ chế đồng bộ.

## 3. Structural modification khác thay đổi dữ liệu của phần tử

Ở `ArrayList`, các thao tác `add` và `remove` làm thay đổi cấu trúc danh sách. `set(index, value)` thường chỉ thay một vị trí đang tồn tại mà không tăng bộ đếm structural modification.

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));

names.add("Dung");    // Thay đổi cấu trúc.
names.remove("An");   // Thay đổi cấu trúc.
names.set(0, "Bao");  // Thay giá trị tại vị trí đã có.
```

Với `ArrayList`, `set` thường **không khiến cơ chế fail-fast phát hiện thay đổi**, nhưng điều đó **không cấp phép** cho một thread sửa phần tử trong lúc stream khác đang đọc. Reader có thể quan sát hỗn hợp dữ liệu cũ và mới, và nếu không có đồng bộ đúng còn có thể xảy ra data race.

Thay đổi trường mutable của một object nằm bên trong `List` cũng có thể làm kết quả `map`, `filter` và `sorted` không ổn định dù số phần tử của danh sách không đổi.

| Thay đổi | Có chắc phát sinh CME? | Kết luận |
| --- | --- | --- |
| `ArrayList.add/remove` khi đang duyệt | Không chắc; thường có thể bị phát hiện | Không an toàn nếu không có thiết kế phối hợp. |
| `ArrayList.set` khi đang duyệt | Thường không bị phát hiện là structural modification | Vẫn có thể tạo kết quả sai hoặc race. |
| Sửa thuộc tính mutable của phần tử | Không nhất thiết | Vẫn ảnh hưởng ý nghĩa các hàm trong pipeline. |
| Thêm/xóa entry của `HashMap` | Có thể bị phát hiện | Không dùng với writer concurrent không đồng bộ. |
| `ConcurrentHashMap.put/remove` | Traversal hỗ trợ thay đổi concurrent theo hợp đồng | Có thể nhìn thấy một phần cập nhật, không phải snapshot. |

## 4. Hợp đồng `non-interference` và `stateless`

Các hàm truyền cho phần lớn phép toán Stream phải thỏa:

- **Non-interfering:** không thay đổi nguồn dữ liệu không-concurrent trong lúc pipeline chạy.
- **Stateless:** không dựa vào một trạng thái mutable dùng chung khiến kết quả phụ thuộc thứ tự/lịch xử lý.
- **Đúng về ngữ nghĩa:** không dùng side effect để thay thế kết quả mà terminal operation phải bảo đảm.

```java
import java.util.List;
import java.util.Locale;

List<String> raw = List.of(" an ", " binh ");

List<String> normalized = raw.stream()
    .map(String::strip)
    .map(s -> s.toUpperCase(Locale.ROOT))
    .toList(); // Java 16+

System.out.println(normalized); // [AN, BINH]
```

`String` là bất biến; các bước trên không sửa nguồn. Đây là kiểu pipeline dễ kiểm thử và có thể cân nhắc chạy song song khi khối lượng tính toán đủ lớn.

Một lỗi **khác** cần phân biệt là sửa **biến kết quả dùng chung**:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> input = List.of(1, 2, 3, 4);
List<Integer> output = new ArrayList<>();

// SAI khi song song: nhiều worker cùng add vào ArrayList không thread-safe.
input.parallelStream().forEach(output::add);
```

`output` không phải nguồn của pipeline, nên ví dụ này không nhất thiết gây CME. Nó vẫn sai vì ghi trạng thái mutable chia sẻ không an toàn. Thay bằng:

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> output = input.parallelStream()
    .map(n -> n * 2)
    .collect(Collectors.toList());
```

`collect` quản lý các bộ tích lũy và combiner theo hợp đồng, nhưng **danh sách kết quả trả về không tự trở thành thread-safe** cho những lần cập nhật đồng thời về sau.

## 5. Lazy execution và late binding: sửa trước terminal operation

Intermediate operations như `filter`, `map` thường **lazy**: lúc tạo pipeline chưa nhất thiết duyệt dữ liệu. Nhiều Spliterator, trong đó có Spliterator của `ArrayList`, có tính chất **late-binding**: việc gắn trạng thái nguồn có thể được trì hoãn tới khi traversal bắt đầu.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> source = new ArrayList<>(List.of("A", "B"));

Stream<String> pipeline = source.stream()
    .filter(s -> !s.isEmpty());

source.add("C"); // Xảy ra trước terminal operation.

System.out.println(pipeline.toList()); // [A, B, C] với ArrayList này.
```

Đối với `ArrayList` trên, việc thêm trước traversal được quan sát do late binding. **Không khái quát** kết quả này cho mọi nguồn: một nguồn snapshot hoặc Spliterator tự viết có thể “chốt” dữ liệu ở thời điểm khác.

Điều **không được suy ra**: “vì Stream lazy nên tôi có thể sửa nguồn bất cứ khi nào”. Sau khi traversal đã bắt đầu, thay đổi nguồn thường vi phạm non-interference. Và dù collection có thể duyệt lại, **đối tượng Stream không thể được dùng lại sau terminal operation**:

```java
Stream<String> once = source.stream();
long count = once.count();
// once.findFirst(); // Không hợp lệ: Stream đã tiêu thụ.
```

## 6. Vì sao sửa nguồn từ `forEach`, `peek` hoặc `filter` là nguy hiểm?

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

// SAI: sửa nguồn trong consumer.
// numbers.stream().forEach(n -> numbers.remove(n));

// SAI: sửa nguồn trong predicate.
// numbers.stream().filter(n -> {
//     numbers.add(99);
//     return n > 0;
// }).toList();

// SAI: side effect trong peek.
// numbers.stream().peek(n -> numbers.remove(n)).count();
```

Ví dụ cuối còn liên quan tới **tối ưu**: với nguồn có kích thước biết trước, `count()` có thể được thực hiện mà **không gọi `peek` cho từng phần tử**. Vì vậy, việc một lần thử “không bị CME” có thể đơn giản là callback đã không chạy.

Hãy chọn giải pháp theo mục tiêu:

| Mục tiêu | API thích hợp |
| --- | --- |
| Chọn phần tử phù hợp, giữ nguyên nguồn | `stream().filter(...).toList()` hoặc `collect(toList())` |
| Xóa phần tử tại chỗ | `list.removeIf(...)` ngoài traversal Stream cạnh tranh |
| Thay thế phần tử tại chỗ | `list.replaceAll(...)` với quy tắc truy cập phù hợp |
| Xóa qua iterator tuần tự | `Iterator.remove()` đúng hợp đồng iterator |
| Biến đổi ra phiên bản mới | `stream().map(...).toList()` |
| Xử lý một ảnh chụp ổn định | Tạo snapshot an toàn rồi mở Stream trên snapshot |

Những API cập nhật collection cũng **không biến một `ArrayList` thành thread-safe** nếu có writer concurrent khác không được phối hợp.

## 7. Nhiều thread và `parallelStream()`

Một `parallelStream()` chỉ cho phép framework chia công việc; nó không khóa nguồn, không tạo transaction và không biến collection mutable thành bất biến.

```text
Thread đọc                         Thread ghi
----------                         ----------
shared.stream().map(...)
      |
đọc phần tử A                      shared.add(newValue)
      |
đọc tiếp hoặc kết thúc
```

Nếu `shared` là `ArrayList` không được phối hợp đúng, kết quả có thể là CME, các giá trị được đọc không như mong đợi, hoặc dấu hiệu race khác. Số lần thử và vị trí các thread được lập lịch không chứng minh tính đúng đắn.

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> shared = new ArrayList<>();
for (int i = 0; i < 10_000; i++) {
    shared.add(i);
}

// Không được chạy concurrent với một writer sửa shared mà thiếu phối hợp:
// long sum = shared.parallelStream()
//     .mapToLong(Integer::longValue)
//     .sum();
```

Đặc biệt, nếu mapper có side effect như gửi một request HTTP, một CME xảy ra về sau **không hoàn tác request đã gửi**. Muốn chạy lại an toàn phải thiết kế idempotency, transaction hoặc cơ chế bù riêng, không chỉ `catch` rồi retry.

## 8. Các loại nguồn có ngữ nghĩa duyệt khác nhau

Không phải mọi collection đều có cơ chế fail-fast giống nhau:

| Nguồn | Cách xử lý thay đổi trong lúc duyệt | Điều không được suy ra |
| --- | --- | --- |
| `ArrayList` | Iterator/spliterator thường fail-fast *best-effort* đối với sửa cấu trúc sai phép | CME không là bảo đảm phát hiện race |
| `HashMap` | Iterator/spliterator có thể phát hiện thay đổi cấu trúc | Không thread-safe với writer ngoài |
| `List.of` / `List.copyOf` | Không thể sửa cấu trúc qua API của list | Phần tử mutable bên trong chưa chắc bất biến |
| `CopyOnWriteArrayList` | Duyệt snapshot của mảng tương ứng | Không thấy mọi thay đổi mới sau snapshot |
| `ConcurrentHashMap` | Iterator/spliterator **weakly consistent** | Không có ảnh chụp nguyên tử nhiều khóa |
| Collection tự định nghĩa | Theo iterator/spliterator và đặc tính đã công bố | Không suy từ tên lớp hoặc từ `parallel()` |

Hai thuật ngữ hữu ích:

- **Snapshot traversal:** duyệt phiên bản dữ liệu được chốt ở một thời điểm được API xác định; writer có thể tiếp tục nhưng lần duyệt không đổi cấu trúc snapshot.
- **Weakly consistent traversal:** duyệt có thể quan sát một số cập nhật đồng thời và không hứa nhìn toàn bộ tại một thời điểm duy nhất.

Không dùng từ “fail-safe” như một lời hứa mơ hồ rằng collection sẽ trả đúng mọi kết quả khi thay đổi đồng thời.

## 9. Snapshot: hướng mặc định khi báo cáo cần nhất quán

Nếu cần tính toán trên **một bộ dữ liệu cố định**, cách trực quan là tạo bản sao cấu trúc rồi chạy Stream trên bản sao đó.

```java
import java.util.ArrayList;
import java.util.List;

List<String> mutable = new ArrayList<>(List.of("A", "B", "C"));
List<String> snapshot = new ArrayList<>(mutable);

mutable.add("D");

System.out.println(snapshot.stream().toList()); // [A, B, C]
System.out.println(mutable); // [A, B, C, D]
```

Nếu không cần sửa danh sách snapshot và nguồn không chứa `null`, Java 10+ có `List.copyOf`:

```java
import java.util.List;

List<String> snapshot = List.copyOf(mutable);
// snapshot.add("E"); // UnsupportedOperationException
```

**Giới hạn quan trọng:**

1. **Sao chép cũng là một lượt đọc.** Không được sao chép từ một `ArrayList` mà writer đang thay đổi nếu chưa có cơ chế phối hợp.
2. **Snapshot của list thường là bản sao nông.** Nếu phần tử là một object mutable và thread khác sửa object, kết quả đọc các trường của object vẫn có thể thay đổi.
3. `List.copyOf` **từ chối phần tử null**; cần chính sách xử lý null nếu nguồn cho phép.
4. Snapshot của một list Java **không tự bảo đảm** tính nhất quán giao dịch của nhiều bảng dữ liệu hoặc nhiều hệ thống.

Khi nhiều thread có quyền ghi, hãy chọn: khóa khi snapshot, ngừng writer tạm thời, cấu trúc snapshot có sẵn, hoặc cơ chế snapshot/version ở tầng lưu trữ.

## 10. `Collections.synchronizedList`: đồng bộ cả bước duyệt/chụp

`Collections.synchronizedList` đồng bộ các thao tác của wrapper, nhưng với iterator, spliterator hoặc Stream, việc duyệt trong lúc có writer vẫn cần **đồng bộ bên ngoài** theo đúng hợp đồng.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<Integer> shared = Collections.synchronizedList(
    new ArrayList<>(List.of(10, 20, 30))
);

// Mọi writer phải cập nhật qua wrapper shared / cùng giao thức khóa.
List<Integer> snapshot;
synchronized (shared) {
    snapshot = new ArrayList<>(shared);
}

// Chạy xử lý bên ngoài khóa để không giữ khóa lâu.
long sum = snapshot.stream()
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(sum); // 60
```

Mẫu này chỉ an toàn khi **mọi writer tuân thủ cùng khóa/quy ước**, không giữ một tham chiếu tới `ArrayList` gốc rồi sửa trực tiếp. Có thể giữ `synchronized (shared)` trong toàn bộ terminal operation, nhưng một pipeline tốn CPU hoặc I/O có thể **giữ khóa rất lâu** và chặn writer.

Thường nên chụp snapshot ngắn bên trong khóa, sau đó xử lý bên ngoài. Đồng bộ một thao tác riêng lẻ không có nghĩa một chuỗi thao tác qua Stream trở thành **nguyên tử**.

## 11. `CopyOnWriteArrayList`: an toàn cho nhiều lượt đọc, ít lượt ghi

`CopyOnWriteArrayList` duy trì mảng mới khi ghi và cung cấp iterator/spliterator có **ngữ nghĩa snapshot**. Với nguồn này, một lần duyệt đã có snapshot không bị CME vì thêm/xóa về sau.

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Stream;

CopyOnWriteArrayList<String> events =
    new CopyOnWriteArrayList<>(List.of("E1", "E2"));

Stream<String> captured = events.stream();
events.add("E3");

System.out.println(captured.toList()); // [E1, E2]
System.out.println(events);           // [E1, E2, E3]
```

Đổi lại, ghi bằng `add`/`remove`/`set` có thể phải sao chép mảng, tốn CPU và bộ nhớ khi danh sách lớn hoặc tần suất ghi cao. Vì vậy, **đừng thay mọi `ArrayList` thành `CopyOnWriteArrayList` chỉ để né CME**.

Snapshot này giữ **tham chiếu phần tử**, không sao chép sâu object mutable. Nếu cần trạng thái bất biến hoàn toàn, kiểu phần tử và quy trình xuất bản dữ liệu cũng cần được thiết kế phù hợp.

## 12. `ConcurrentHashMap`: có thể thay đổi concurrent, nhưng không có snapshot đa khóa

`ConcurrentHashMap` được thiết kế cho truy cập đọc/ghi đồng thời. Iterator/spliterator của nó **weakly consistent**: có thể quan sát một số thay đổi trong lúc duyệt, không ném CME chỉ vì những thao tác concurrent bình thường.

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

ConcurrentHashMap<String, Long> balances =
    new ConcurrentHashMap<>();
balances.put("A", 100L);
balances.put("B", 200L);

// Một thread khác có thể đang sửa balances.
Map<String, Long> observed = balances.entrySet().stream()
    .collect(Collectors.toMap(
        Map.Entry::getKey,
        Map.Entry::getValue
    ));
```

Trong ví dụ trên, `observed` gồm những gì traversal đã **quan sát được**, không được bảo đảm là số dư đồng thời đúng tại một thời điểm duy nhất.

```text
Tại T1: A=100, B=200
Writer đổi A rồi đổi B
Reader có thể thấy A mới và B cũ
```

Tổng từ `balances.values().parallelStream().mapToLong(...).sum()` có thể phản ánh các thời điểm khác nhau. Nếu nghiệp vụ cần báo cáo chốt sổ, hãy dùng snapshot/version/transaction thích hợp.

`ConcurrentHashMap` cũng **không cho phép khóa hoặc giá trị null**. Và việc dùng `Collectors.groupingByConcurrent` hoặc `Collectors.toConcurrentMap` ở terminal operation **không làm nguồn `ArrayList` mutable trở nên an toàn**: collector xử lý **cách xây kết quả**, không giải quyết thay đổi nguồn.

## 13. Unmodifiable view không phải snapshot

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> mutable = new ArrayList<>(List.of("A", "B"));

List<String> view = Collections.unmodifiableList(mutable);
List<String> snapshot = List.copyOf(mutable);

mutable.add("C");

System.out.println(view);     // [A, B, C]
System.out.println(snapshot); // [A, B]
```

`Collections.unmodifiableList(mutable)` chỉ chặn sửa thông qua **view**, nhưng underlying list vẫn có thể đổi và view phản ánh thay đổi đó. `List.copyOf(mutable)` cho snapshot **cấu trúc** không bị thay đổi theo underlying list.

Tương tự, `Stream.toList()` (Java 16+) trả list unmodifiable **sau khi stream đã hoàn thành**; nó không ngăn được race xảy ra **trong lúc đọc nguồn**.

## 14. Ví dụ Java hoàn chỉnh: tách cập nhật, snapshot và duyệt

Chương trình Java 17+ minh họa ba thao tác khác nhau: tạo kết quả mới, sửa nguồn tại chỗ, và chụp snapshot để đọc ổn định.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class SourceMutationSafetyDemo {
    private SourceMutationSafetyDemo() {}

    static List<Integer> positives(List<Integer> source) {
        return source.stream()
            .filter(n -> n > 0)
            .toList();
    }

    static void removeNonPositive(List<Integer> source) {
        source.removeIf(n -> n <= 0);
    }

    static List<Integer> safeSnapshot(List<Integer> synchronizedSource) {
        synchronized (synchronizedSource) {
            return List.copyOf(synchronizedSource);
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers =
            new ArrayList<>(List.of(-2, -1, 0, 1, 2, 3));

        System.out.println(positives(numbers)); // [1, 2, 3]
        System.out.println(numbers); // [-2, -1, 0, 1, 2, 3]

        removeNonPositive(numbers);
        System.out.println(numbers); // [1, 2, 3]

        List<Integer> shared = Collections.synchronizedList(
            new ArrayList<>(List.of(10, 20, 30))
        );

        List<Integer> snapshot = safeSnapshot(shared);
        shared.add(40);

        System.out.println(snapshot); // [10, 20, 30]
        System.out.println(shared);   // [10, 20, 30, 40]

        long sum = snapshot.stream()
            .mapToLong(Integer::longValue)
            .sum();
        System.out.println(sum); // 60
    }
}
```

**Điều kiện sử dụng:**

- `positives` không sửa input, nhưng **không tự khóa** input. Người gọi phải bảo đảm nguồn ổn định khi xử lý.
- `removeNonPositive` chỉ nên chạy khi không có traversal khác đang cạnh tranh hoặc đã có phối hợp phù hợp.
- `safeSnapshot` đúng khi nguồn được chia sẻ theo **cùng giao thức đồng bộ**; tất cả writer phải dùng wrapper/khóa phù hợp.
- `List.copyOf` yêu cầu không có phần tử null, và chỉ sao chép cấu trúc/tham chiếu.

## 15. Kiểm thử bằng bất biến, không bằng lịch xuất hiện CME

Một test như “cho hai thread đọc/ghi `ArrayList` và mong luôn thấy CME” thường **flaky**: kết quả phụ thuộc scheduling và fail-fast best-effort. Hãy kiểm tra **hợp đồng của thiết kế an toàn** thay vì dựa vào ngoại lệ phải xuất hiện.

Ví dụ JUnit Jupiter 5; đặt cùng package với `SourceMutationSafetyDemo` hoặc khai báo import phù hợp:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;

class SourceMutationSafetyDemoTest {
    @Test
    void streamFilterDoesNotMutateSource() {
        List<Integer> input = new ArrayList<>(List.of(-1, 0, 1, 2));
        List<Integer> result = SourceMutationSafetyDemo.positives(input);

        assertEquals(List.of(1, 2), result);
        assertEquals(List.of(-1, 0, 1, 2), input);
    }

    @Test
    void removeIfMutatesOnlyWhenRequested() {
        List<Integer> input = new ArrayList<>(List.of(-1, 0, 1, 2));
        SourceMutationSafetyDemo.removeNonPositive(input);

        assertEquals(List.of(1, 2), input);
    }

    @Test
    void snapshotStructureRemainsStable() {
        List<Integer> shared = Collections.synchronizedList(
            new ArrayList<>(List.of(10, 20))
        );
        List<Integer> snapshot =
            SourceMutationSafetyDemo.safeSnapshot(shared);

        shared.add(30);

        assertEquals(List.of(10, 20), snapshot);
        assertEquals(List.of(10, 20, 30), shared);
        assertThrows(UnsupportedOperationException.class,
            () -> snapshot.add(40));
    }
}
```

Các test trên xác minh các tính chất **xác định**: dữ liệu sau lọc đúng, thao tác update đúng thời điểm và snapshot không đổi khi nguồn có thay đổi cấu trúc. Trong ứng dụng có concurrency thực, hãy thêm kiểm thử nhiều thread với giao thức đồng bộ rõ ràng và stress test; **không lấy số lần CME làm tiêu chí duy nhất**.

## 16. Hiệu năng và chi phí bộ nhớ của từng lựa chọn

| Phương án | Chi phí điển hình | Khi nào phù hợp |
| --- | --- | --- |
| `filter(...).toList()` | Cấp phát danh sách kết quả, giữ các phần tử được chọn. | Muốn tạo kết quả mới mà không sửa nguồn. |
| `removeIf` trên `ArrayList` | Duyệt và thay đổi cấu trúc theo triển khai. | Chủ đích xóa tại chỗ, không có traversal cạnh tranh. |
| `new ArrayList<>(source)` | Sao chép O(n) tham chiếu và vùng nhớ. | Muốn tách lượt xử lý khỏi thay đổi cấu trúc về sau. |
| `List.copyOf(source)` | Tạo list unmodifiable; có thể sao chép phần tử/tham chiếu. | Không có null; muốn snapshot cấu trúc. |
| `Collections.synchronizedList` | Khóa và thời gian chờ giữa reader/writer. | Có một giao thức đồng bộ nhất quán. |
| `CopyOnWriteArrayList` | Writer có thể sao chép cả mảng khi cập nhật. | Đọc nhiều, ghi rất ít. |
| `ConcurrentHashMap` | Chi phí của cấu trúc đồng thời và cập nhật. | Map cần đọc/ghi concurrent, chấp nhận weak consistency. |

Các con số chi phí chỉ là xu hướng; cần đo trên workload thực. Nếu mục tiêu là **báo cáo chính xác**, so sánh hiệu năng phải gồm chi phí bảo đảm nhất quán như chụp snapshot hoặc khóa. Đừng so một phiên bản có snapshot với một phiên bản đọc nguồn đang bị sửa mà bỏ qua tính đúng rồi kết luận phiên bản sai “nhanh hơn”.

Với benchmark JMH, đo tách biệt chi phí snapshot và chi phí xử lý nếu muốn hiểu từng thành phần; đồng thời có phép đo **end-to-end** nếu muốn quyết định thiết kế hệ thống. Không đưa ra số speedup khi chưa có dữ liệu thực tế.

## 17. Những lỗi thường gặp

| Nhận định hoặc cách làm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| “CME luôn xuất hiện nếu list bị sửa.” | Fail-fast chỉ là best-effort. | Thiết kế truy cập đúng, không dựa vào ngoại lệ. |
| “Chỉ có một thread thì không thể bị CME.” | Một thread vẫn có thể sửa nguồn khi đang duyệt. | Tách bước sửa và bước Stream. |
| “`set` không tăng modCount nên hoàn toàn an toàn.” | Dữ liệu đọc có thể thay đổi giữa pipeline. | Giữ trạng thái ổn định hoặc phối hợp đúng. |
| “Bắt CME rồi retry là đủ.” | Có thể đã thực hiện side effect, race vẫn tồn tại. | Snapshot/khóa/transaction/idempotency. |
| “`parallelStream` tự xử lý thread safety.” | Parallel chỉ chia việc, không bảo vệ nguồn. | Chọn nguồn và collector theo hợp đồng. |
| “Concurrent collector chữa được nguồn mutable.” | Collector chỉ bảo vệ tích lũy, không bảo vệ nguồn. | Sửa thiết kế đọc/ghi nguồn. |
| “Unmodifiable view là snapshot.” | View có thể phản ánh underlying list. | Sao chép một cách an toàn. |
| “ConcurrentHashMap cho bản báo cáo tại một thời điểm.” | Traversal weakly consistent, không snapshot đa khóa. | Snapshot/version ở tầng nghiệp vụ. |
| “CopyOnWriteArrayList không có chi phí.” | Mỗi ghi có thể sao chép mảng. | Chọn theo tỷ lệ đọc/ghi. |
| “List.copyOf đóng băng mọi object.” | Chỉ ngăn sửa list; phần tử mutable vẫn đổi. | Dùng immutable value hoặc sao chép sâu khi cần. |

## 18. Bài tập thực hành

**Bài 1 — Không can thiệp nguồn.** Cho một `ArrayList` chứa `[1,2,3,4]`, chỉ ra lỗi trong `list.stream().forEach(n -> list.remove(n))`. Viết lại hai phiên bản: tạo list mới và xóa tại chỗ bằng `removeIf`.

**Bài 2 — Lazy và late-binding.** Tạo một stream từ `ArrayList`, thêm phần tử trước terminal operation, quan sát kết quả. Giải thích vì sao không thể suy ra được phép thêm/xóa **trong khi traversal chạy**.

**Bài 3 — Thay giá trị.** Đổi `set(0, ...)` khi một thread khác đang đọc danh sách. Vì sao có thể không có CME nhưng vẫn không thể coi dữ liệu đang đọc là nhất quán?

**Bài 4 — View so với snapshot.** Tạo `Collections.unmodifiableList(source)` và `List.copyOf(source)`, rồi thêm phần tử vào `source`. Dự đoán hai kết quả và giải thích khác biệt.

**Bài 5 — Synchronized snapshot.** Viết hàm lấy snapshot từ `Collections.synchronizedList` trong `synchronized (shared)`, sau đó chạy thống kê ở ngoài khóa. Khi nào mẫu này không còn an toàn?

**Bài 6 — Copy-on-write.** Lấy Stream từ `CopyOnWriteArrayList`, thêm một phần tử, rồi chạy terminal operation. So sánh với `ArrayList` và lý giải chi phí khi ghi nhiều.

**Bài 7 — Concurrent map.** Quan sát một `ConcurrentHashMap` trong lúc writer cập nhật nhiều khóa. Tại sao stream có thể không ném CME nhưng kết quả vẫn không phải snapshot giao dịch?

**Bài 8 — Kiểm thử.** Thay một test `assertThrows(ConcurrentModificationException.class, ...)` phụ thuộc timing bằng những test xác định kiểm tra lọc đúng, snapshot ổn định và cập nhật đúng thời điểm.

**Bài 9 — Giao dịch và side effect.** Nếu một Stream vừa ghi DB vừa duyệt một nguồn mutable và gặp CME giữa chừng, kết quả DB đã ghi có tự rollback không? Hãy đề xuất cơ chế transaction/idempotency.

**Bài 10 — So sánh hiệu năng.** Thiết kế benchmark cho `ArrayList` ổn định, snapshot từ list có writer, và `CopyOnWriteArrayList` dưới nhiều tỷ lệ đọc/ghi. Chỉ kết luận sau khi các phương án đáp ứng cùng yêu cầu nhất quán.

## 19. Checklist trước khi sử dụng

- [ ] Đã biết nguồn là immutable, fail-fast, snapshot hay weakly consistent.
- [ ] Không sửa nguồn trong các lambda `map`, `filter`, `peek` hoặc `forEach`.
- [ ] Đã phân biệt sửa cấu trúc, sửa giá trị phần tử và sửa trạng thái bên trong object.
- [ ] Không dùng CME làm cơ chế đồng bộ hoặc làm phép kiểm tra tính đúng đắn.
- [ ] Không phụ thuộc CME chắc chắn xuất hiện trong một test.
- [ ] Có chính sách rõ ràng khi nguồn được nhiều thread đọc/ghi.
- [ ] Nếu tạo snapshot, chính bước sao chép cũng được phối hợp an toàn.
- [ ] Với `synchronizedList`, mọi writer tuân thủ cùng giao thức khóa.
- [ ] Hiểu snapshot của `CopyOnWriteArrayList` và chi phí write/copy.
- [ ] Hiểu `ConcurrentHashMap` weakly consistent không đồng nghĩa nhất quán đa khóa.
- [ ] Không nhầm unmodifiable view với snapshot cấu trúc.
- [ ] Không coi concurrent collector là biện pháp bảo vệ nguồn mutable.
- [ ] Không tái sử dụng Stream sau terminal operation.
- [ ] Không dựa vào `peek` để tạo side effect bắt buộc.
- [ ] Đã kiểm tra trường hợp nguồn rỗng, null, thay đổi trước và trong traversal.
- [ ] Nếu có side effect hoặc I/O, đã thiết kế transaction/retry/idempotency riêng.
- [ ] Đã kiểm tra kết quả theo hợp đồng nghiệp vụ trước khi tối ưu hiệu năng.

**Ghi nhớ:** `ConcurrentModificationException` chỉ là tín hiệu *best-effort* cho một số cách sửa nguồn không hợp lệ; nó **không phải** bảo đảm thread-safety. Với Stream API, hãy giữ lambda không can thiệp nguồn, tách giai đoạn cập nhật khỏi giai đoạn duyệt, chụp snapshot dưới cơ chế phối hợp nếu cần báo cáo ổn định, và chọn collection concurrent khi bạn chấp nhận đúng ngữ nghĩa của nó. **Kết quả đúng và nhất quán quan trọng hơn việc chỉ tránh được ngoại lệ.**

**Tài liệu tham khảo:** [Stream — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html), [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/ConcurrentModificationException.html), [ArrayList](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/ArrayList.html), [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html), [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).
