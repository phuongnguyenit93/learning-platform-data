# Điều kiện áp dụng thu thập đồng thời với CONCURRENT và UNORDERED

Khi sử dụng Java Stream API, việc gọi `parallelStream()` hoặc `parallel()` **không có nghĩa** mọi phần tử sẽ được ghi đồng thời vào cùng một `List` hay `Map`. Cách gom kết quả phụ thuộc vào **hợp đồng của Collector** và **yêu cầu thứ tự của Stream**. Đặc biệt, hai đặc tính `Collector.Characteristics.CONCURRENT` và `Collector.Characteristics.UNORDERED` quyết định khi nào trình thực thi **được phép** chọn chiến lược nhiều luồng cùng tích lũy vào một bộ chứa.

Bài học thuộc chương **Thu thập đồng thời** của module `JAVA_STREAM_API`. Ta sẽ phân tích điều kiện chính xác để concurrent reduction xảy ra, phân biệt concurrent collector với parallel stream và concurrent data structure, sử dụng `toConcurrentMap`/`groupingByConcurrent`, tự xây Collector an toàn, nhận diện các lỗi chia sẻ trạng thái, mất thứ tự và ảnh hưởng hiệu năng. Các ví dụ tiếp nối kiến thức về pipeline lazy, `filter`, `map`, `reduce`, `collect`, `Spliterator` và giới hạn của thực thi song song.

Các API trọng tâm có từ **Java 8**. Các ví dụ dùng `Arrays.asList` hoặc `IntStream` để tránh phụ thuộc Java 9+.

## 1. Từ collect thông thường đến concurrent reduction

Một `Collector<T, A, R>` định nghĩa:

- `T`: kiểu phần tử đầu vào;
- `A`: kiểu bộ tích lũy trung gian;
- `R`: kiểu kết quả cuối.

Năm thành phần của Collector:

| Thành phần | Vai trò |
| --- | --- |
| `supplier()` | Tạo một bộ tích lũy `A` mới, ban đầu rỗng |
| `accumulator()` | Đưa một phần tử `T` vào một bộ tích lũy `A` |
| `combiner()` | Gộp hai bộ tích lũy `A` khi có nhiều nhánh |
| `finisher()` | Chuyển `A` thành `R` nếu cần |
| `characteristics()` | Cho phép trình thực thi dựa vào các cam kết về tính đồng thời, thứ tự, bước hoàn tất |

Khi xử lý song song, Java có thể thực hiện **nhiều bộ chứa riêng**:

```text
               Stream<T>
                   |
         chia thành nhiều phần
            /             \
           v               v
     supplier()       supplier()
         A1               A2
          |                |
    accumulator      accumulator
          |                |
          +---- combiner --+
                   |
                finisher
                   |
                  R
```

Chiến lược này **không yêu cầu** từng bộ chứa `A1` và `A2` chịu được nhiều luồng cùng cập nhật trong một thời điểm, miễn các nhánh không đồng thời sửa cùng bộ chứa và combiner đúng hợp đồng.

Một chiến lược khác là **tích lũy chung vào một container**:

```text
                 Stream<T>
                     |
           nhiều tác vụ song song
            /       |       \
           v        v        v
      accumulator accumulator accumulator
            \       |       /
             \      v      /
                 A chung
                    |
                 finisher
                    |
                    R
```

Khi cùng một `A` nhận các lời gọi accumulator đồng thời, bản thân collector phải **thực sự an toàn cho cập nhật đồng thời**. Chỉ đặt `parallel()` hoặc dùng một `ConcurrentHashMap` làm kết quả không đủ để suy ra cả pipeline được xử lý theo chiến lược này.

## 2. Ý nghĩa chính xác của CONCURRENT và UNORDERED

`Collector.Characteristics` có ba cờ:

| Đặc tính | Cam kết | Không có nghĩa |
| --- | --- | --- |
| `CONCURRENT` | Accumulator **có thể** được gọi đồng thời từ nhiều luồng với **cùng một đối tượng A** | Không tự chuyển Stream thành parallel; không tự tạo khóa hoặc đồng bộ |
| `UNORDERED` | Phép thu thập **không cam kết giữ encounter order** của các phần tử đầu vào | Không phải phép xáo trộn dữ liệu; không nói accumulator thread-safe |
| `IDENTITY_FINISH` | Có thể dùng trực tiếp bộ tích lũy `A` làm kết quả `R`, bỏ qua finisher chuyển đổi | Không liên quan tới tính đồng thời hoặc tính bất biến |

Hai đặc tính đang xét là **hai cam kết độc lập**.

**`CONCURRENT` trả lời:** “Nhiều luồng cùng gọi accumulator trên một bộ chứa có an toàn theo hợp đồng hay không?”

**`UNORDERED` trả lời:** “Kết quả có cần phản ánh encounter order hay không?”

Một collector có thể là `CONCURRENT` nhưng không `UNORDERED` nếu nó thực sự có khả năng tích lũy đồng thời mà vẫn có yêu cầu thứ tự. Tuy nhiên, điều đó **không tự cho phép** thu thập chung vào một container từ một ordered parallel stream, vì còn phải bảo toàn ràng buộc thứ tự. Ngược lại, một collector có `UNORDERED` nhưng không `CONCURRENT` cho phép bỏ yêu cầu thứ tự, **không cho phép** nhiều luồng tự do sửa cùng `ArrayList`.

`IDENTITY_FINISH` là chủ đề khác: nếu finisher thực sự phải chuyển `A` thành kiểu `R` khác, chẳng hạn `LongAdder` thành `Long`, không được khai báo `IDENTITY_FINISH`.

## 3. Điều kiện để được phép tích lũy đồng thời vào một A

Đối với thao tác kết thúc `stream.collect(collector)`, điều kiện cần để trình thực thi có thể chọn chiến lược **concurrent reduction với container dùng chung** là:

1. Stream đang xử lý **song song**.
2. Collector khai báo **`CONCURRENT`**.
3. **Ít nhất một** trong hai điều sau đúng:
   - Stream không có yêu cầu encounter order (`unordered`); **hoặc**
   - Collector khai báo **`UNORDERED`**.

Viết như một biểu thức logic:

```text
shared-container concurrent reduction được phép khi:

stream.isParallel()
    && collector có CONCURRENT
    && (!stream có encounter order || collector có UNORDERED)
```

Lưu ý đây là **điều kiện cho phép**, không phải bảo đảm về số luồng, cách chia công việc, số lần gọi supplier hoặc việc framework phải thực sự chọn chiến lược chung trong mọi lần chạy.

### Bảng quyết định

| Stream | Characteristics của Collector | Có thể tích lũy đồng thời vào cùng A? | Giải thích |
| --- | --- | --- | --- |
| Tuần tự | `CONCURRENT + UNORDERED` | Không cần | Pipeline không thực thi các nhánh song song |
| Song song, có encounter order | Không có `CONCURRENT` | **Không** | Không có cam kết accumulator dùng chung an toàn |
| Song song, có encounter order | Chỉ `UNORDERED` | **Không** | Bỏ thứ tự không tạo thread-safety |
| Song song, có encounter order | Chỉ `CONCURRENT` | **Không theo chiến lược chung** | Collector vẫn yêu cầu giữ thứ tự |
| Song song, có encounter order | `CONCURRENT + UNORDERED` | **Có thể** | Collector cho phép cả cập nhật chung và bỏ yêu cầu thứ tự |
| Song song, không có encounter order | Chỉ `CONCURRENT` | **Có thể** | Nguồn/pipeline không yêu cầu giữ thứ tự |
| Song song, không có encounter order | `CONCURRENT + UNORDERED` | **Có thể** | Đủ cả hai điều kiện |
| Song song, bất kỳ thứ tự | Chỉ `IDENTITY_FINISH` | **Không** | Finisher đồng nhất không bảo đảm accumulator an toàn |

Nếu một Collector **không** có `CONCURRENT`, nó vẫn **có thể dùng với parallel stream**. Java có thể tạo nhiều bộ tích lũy độc lập và gọi `combiner` để ghép kết quả. Điều bị hạn chế là việc nhiều tác vụ đồng thời ghi vào **chính cùng một** bộ chứa khi collector không tuyên bố hỗ trợ.

## 4. Encounter order của Stream khác với UNORDERED của Collector

*Encounter order* là thứ tự logic do nguồn và các thao tác trung gian quy định. `List.stream()` thường có encounter order theo vị trí của danh sách. Một số nguồn như `HashSet` không cung cấp cam kết thứ tự gặp ổn định.

`UNORDERED` của Collector **khác** thao tác `BaseStream.unordered()`:

- `stream.unordered()` thay đổi hợp đồng thứ tự của pipeline downstream.
- `collector.characteristics().contains(UNORDERED)` nói rằng chính phép thu thập không cần giữ encounter order.

Ví dụ danh sách có thứ tự:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> input = Arrays.asList("A", "B", "A", "C");

List<String> result = input.parallelStream()
        .collect(Collectors.toList());

System.out.println(result); // [A, B, A, C]
```

`Collectors.toList()` không phải concurrent collector; nó vẫn có thể chạy cùng parallel stream bằng cách tích lũy và kết hợp các phần theo hợp đồng. Khi nguồn có encounter order, kết quả `toList` giữ thứ tự các phần tử đầu vào.

Ngược lại:

```java
import java.util.Set;

Set<String> unique = input.parallelStream()
        .collect(Collectors.toSet());

System.out.println(unique.size());     // 3
System.out.println(unique.contains("A")); // true
```

`Collectors.toSet()` là **unordered collector**, nhưng **không đồng nghĩa concurrent collector**. Tập kết quả không cam kết thứ tự duyệt cụ thể; việc thiếu yêu cầu thứ tự không tự làm accumulator an toàn cho nhiều luồng cùng sửa.

Cũng không nên coi `unordered()` là một phép random shuffle: nó loại bỏ ràng buộc encounter order, không bắt buộc xáo trộn các phần tử.

## 5. Kiểm tra Characteristics thay vì đoán

Có thể tự quan sát đặc tính do Collector khai báo:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, Set<String>> toSet = Collectors.toSet();

System.out.println(
        toSet.characteristics().contains(
                Collector.Characteristics.UNORDERED
        )
); // true

System.out.println(
        toSet.characteristics().contains(
                Collector.Characteristics.CONCURRENT
        )
); // false

Collector<String, ?, Map<String, String>> toMap =
        Collectors.toMap(s -> s, s -> s);

System.out.println(
        toMap.characteristics().contains(
                Collector.Characteristics.CONCURRENT
        )
); // false
```

`characteristics()` cho biết **cam kết được công bố**; nó không tự kiểm tra xem code tùy chỉnh có thực sự thread-safe hay không. Nếu người viết Collector đánh dấu sai, framework có thể dựa vào lời khai đó để thực thi theo cách không an toàn.

Không nên chỉ dựa vào tên kiểu dữ liệu. Một Collector trả về `ConcurrentMap` là một dấu hiệu đáng xem xét, nhưng để biết có phải concurrent collector hay không vẫn phải đọc **hợp đồng Collector** và kiểm tra characteristics của chính nó.

## 6. toConcurrentMap: trường hợp phù hợp để tích lũy đồng thời

`Collectors.toConcurrentMap` tạo một `ConcurrentMap<K,U>` và là **concurrent, unordered collector**. Khi khóa bị trùng, cần chỉ định một merge function phù hợp.

Ví dụ đếm số sự kiện theo mã:

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> events = Arrays.asList(
        "WARN", "INFO", "WARN", "ERROR", "INFO", "WARN"
);

ConcurrentMap<String, Long> counts = events.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Function.identity(),
                code -> 1L,
                Long::sum
        ));

System.out.println(counts.get("WARN"));  // 3
System.out.println(counts.get("INFO"));  // 2
System.out.println(counts.get("ERROR")); // 1
```

Pipeline trên:

1. Nguồn `List` có encounter order.
2. `parallelStream()` cho phép thực thi nhiều nhánh.
3. `toConcurrentMap` có cả `CONCURRENT` và `UNORDERED`, nên framework **được phép** tích lũy vào một ConcurrentMap dùng chung.
4. `Long::sum` gộp các giá trị khi cùng khóa xuất hiện.
5. Kết quả không yêu cầu thứ tự duyệt các khóa.

Đây là ví dụ phù hợp vì kết quả **đếm theo mã** không phụ thuộc mã nào được xử lý trước.

**Cẩn trọng với khóa trùng:** overload chỉ nhận `keyMapper` và `valueMapper` sẽ ném `IllegalStateException` nếu gặp khóa trùng. Muốn cộng, chọn tối đa, ghi đè có quy tắc hoặc báo lỗi tùy nghiệp vụ, phải chọn đúng merge function.

### Tránh dùng “giữ giá trị tới trước” cho dữ liệu unordered

```java
// KHÔNG đáng tin cậy nếu cần sự kiện "đến đầu tiên" theo thứ tự nguồn.
ConcurrentMap<String, Event> firstByKey = eventsStream
        .parallel()
        .collect(Collectors.toConcurrentMap(
                Event::key,
                Function.identity(),
                (a, b) -> a
        ));
```

Đây là **mã phác thảo**; `Event` và `eventsStream` đại diện cho kiểu và Stream của ứng dụng. Vì `toConcurrentMap` là unordered collector, `a` trong merge function không bảo đảm là phần tử xuất hiện đầu tiên theo encounter order. Nếu nghiệp vụ cần bản ghi mới nhất, nên dùng comparator theo `timestamp` cùng khóa phụ ổn định để chọn, không dùng vị trí gộp.

## 7. groupingByConcurrent: gom nhóm không yêu cầu thứ tự

`Collectors.groupingByConcurrent` là concurrent, unordered collector cho phép nhóm phần tử bằng một classifier.

Đếm các từ theo chữ cái đầu:

```java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

List<String> words = Arrays.asList(
        "java", "junit", "spring", "sql", "stream"
);

ConcurrentMap<Character, Long> byInitial =
        words.parallelStream()
             .collect(Collectors.groupingByConcurrent(
                     word -> word.charAt(0),
                     Collectors.counting()
             ));

System.out.println(byInitial.get('j')); // 2
System.out.println(byInitial.get('s')); // 3
```

Không cần giữ thứ tự các từ khi mục tiêu là đếm, nên đặc tính unordered phù hợp.

Tuy nhiên, một điểm thường bị hiểu sai: `Collectors.counting()` (downstream) không phải concurrent collector. Điều đó **không làm `groupingByConcurrent` sai**. Collector ngoài chịu trách nhiệm điều phối cập nhật an toàn vào các bộ tích lũy downstream; không được tự mang container downstream ra ngoài để nhiều luồng sửa mà không có bảo vệ.

### Danh sách trong từng nhóm không cam kết thứ tự

```java
ConcurrentMap<Character, List<String>> grouped =
        words.parallelStream()
             .collect(Collectors.groupingByConcurrent(
                     word -> word.charAt(0)
             ));

System.out.println(grouped.get('j').size()); // 2
```

Ta biết nhóm `'j'` chứa hai phần tử `"java"` và `"junit"`, nhưng **không nên khẳng định thứ tự của hai phần tử đó**. `groupingByConcurrent` là unordered collector, ngay cả khi nguồn là `List` có encounter order.

Hơn nữa, `ConcurrentMap<K,List<V>>` **không làm bản thân từng `List<V>` tự động thread-safe** để tiếp tục sửa từ các luồng sau khi collect. Tính đúng đắn khi thu thập thuộc trách nhiệm implementation của Collector; tính an toàn của các thao tác về sau là vấn đề riêng.

Nếu UI hoặc báo cáo cần thứ tự từng nhóm, hãy dùng collector phù hợp để giữ order, hoặc sắp xếp từng danh sách theo một **khóa rõ ràng** sau khi thu thập.

## 8. Tự xây concurrent collector an toàn bằng LongAdder

`LongAdder` hỗ trợ nhiều luồng đồng thời cập nhật số đếm/tổng. Nó là lựa chọn tốt để minh họa một Collector có cả `CONCURRENT` và `UNORDERED`.

```java
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;
import java.util.stream.IntStream;

Collector<Integer, LongAdder, Long> sumCollector =
        Collector.of(
                LongAdder::new,
                (adder, n) -> adder.add(n),
                (left, right) -> {
                    left.add(right.sum());
                    return left;
                },
                LongAdder::sum,
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );

long total = IntStream.rangeClosed(1, 100_000)
        .boxed()
        .parallel()
        .collect(sumCollector);

System.out.println(total); // 5000050000
```

Phân tích hợp đồng:

- `supplier` tạo bộ chứa `LongAdder` mới, ban đầu tổng bằng 0.
- `accumulator` gọi `LongAdder.add`; nhiều luồng có thể cập nhật **cùng** đối tượng.
- `combiner` gộp tổng từ `right` vào `left`; vẫn phải đúng cho các đường thực thi không dùng bộ chứa chung.
- `finisher` trả `long` từ `LongAdder.sum`, được boxing thành `Long`.
- `CONCURRENT` đúng vì accumulator chấp nhận cập nhật đồng thời.
- `UNORDERED` đúng vì tổng các số nguyên ở đây không cần thứ tự gặp phần tử.
- **Không** có `IDENTITY_FINISH` vì `A = LongAdder`, `R = Long`.

`LongAdder.sum()` không phải một phép chụp snapshot tuyến tính hóa trong khi các luồng **vẫn đang ghi**. Trong một phép collect hợp lệ, finisher được áp dụng khi giai đoạn tích lũy đã hoàn tất, vì thế cách dùng trên phù hợp.

Với tổng số nguyên quá lớn, ngay cả `long` có thể tràn. Nếu nghiệp vụ yêu cầu phát hiện tràn, tính chính xác tuyệt đối hoặc thứ tự đặc biệt, cần một thiết kế số học khác. Và nếu chỉ cần tổng `int` hoặc `long`, `mapToLong(...).sum()` thường đơn giản hơn Collector tự viết.

### Vì sao combiner vẫn phải đúng?

Có những tình huống pipeline không sử dụng chiến lược container chung. Collector vẫn phải đáp ứng các hợp đồng identity/associativity của `combiner`, bất kể một lần chạy cụ thể có gọi nó hay không.

Sai:

```java
// SAI: bộ chứa phải được gộp, không thể bỏ dữ liệu nhánh right.
(left, right) -> left
```

Đoạn trên chỉ là hình minh họa lambda `combiner`. Nếu dùng trong Collector có nhiều container trung gian, kết quả từ nhánh phải sẽ bị mất.

Đúng với `LongAdder`:

```java
(left, right) -> {
    left.add(right.sum());
    return left;
}
```

Phép gộp phải tương thích với việc accumulator đã thêm phần tử vào mỗi bộ chứa, không chỉ “trông hợp lý” khi chạy tuần tự.

## 9. Anti-pattern: gắn CONCURRENT vào ArrayList

`ArrayList` không tự hỗ trợ nhiều luồng cùng gọi `add` trên một instance. Vì vậy không được tạo Collector dưới đây rồi công bố `CONCURRENT`:

```java
import java.util.ArrayList;
import java.util.stream.Collector;

// VÍ DỤ SAI: KHÔNG dùng trong ứng dụng.
Collector<Integer, ArrayList<Integer>, ArrayList<Integer>> unsafe =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );
```

Nếu Java chọn chiến lược tích lũy chung, `ArrayList.add` có thể chạy đồng thời từ nhiều tác vụ dẫn đến mất phần tử, trạng thái sai hoặc lỗi khó tái hiện.

Không nên xem việc chạy thử một lần với kết quả đúng là bằng chứng an toàn luồng. Race condition có thể chỉ xuất hiện với tải lớn hoặc lịch thực thi khác.

Cách phù hợp khi chỉ cần List:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> safe = IntStream.range(0, 1000)
        .boxed()
        .parallel()
        .collect(Collectors.toList());

System.out.println(safe.size()); // 1000
```

`toList` là Collector không concurrent; framework có thể dùng nhiều bộ chứa độc lập và gộp lại an toàn theo hợp đồng của nó. Kết quả không yêu cầu caller phải chia sẻ một `ArrayList` đang được nhiều luồng sửa.

Nếu muốn viết Collector danh sách của riêng mình, **không khai báo `CONCURRENT`** trừ khi accumulator và toàn bộ container thật sự hỗ trợ cập nhật chung. Chỉ bọc Map bằng `ConcurrentHashMap` mà các giá trị bên trong vẫn là `ArrayList` cũng chưa chứng minh được an toàn của cập nhật vào danh sách đó.

## 10. UNORDERED không sửa được phép gộp sai

Hai đặc tính chỉ quyết định một số quyền tối ưu. Chúng **không chữa** một hàm merge không có tính kết hợp hoặc phụ thuộc tác dụng phụ.

Ví dụ sai về ý nghĩa khi dùng phép trừ làm merge:

```java
// SAI nếu kỳ vọng một kết quả bất biến khi thay đổi cách phân nhánh.
Collectors.toConcurrentMap(
        item -> item.key(),
        item -> item.value(),
        (a, b) -> a - b
)
```

Đây là mã phác thảo với `item` thuộc một kiểu do ứng dụng định nghĩa. Phép trừ không có tính kết hợp:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Parallel collect có thể kết hợp các kết quả từng phần theo cách khác nhau. Với những phép như đếm hoặc tổng số nguyên trong miền không tràn, `Long::sum` là phép gộp phù hợp. Nếu cần chọn đối tượng ưu tiên, dùng một quy tắc ổn định như `BinaryOperator.maxBy(comparator)`, với cách xử lý hòa điểm xác định rõ.

### Tính kết hợp khác tính giao hoán

`(a, b) -> a` (giữ toán hạng trái) và `(a, b) -> b` (giữ toán hạng phải) có thể được xem là kết hợp theo cách nhóm, nhưng **không giao hoán**: đổi thứ tự đầu vào đổi kết quả. Với concurrent, unordered collector, không nên dùng chúng để hiện thực hóa “bản ghi xuất hiện trước/sau theo encounter order”.

Nếu phép toán không quan tâm thứ tự, hãy chứng minh điều đó từ yêu cầu nghiệp vụ, không suy luận chỉ từ việc dữ liệu được lưu trong Map.

## 11. CONCURRENT của Collector khác với ConcurrentMap và Spliterator.CONCURRENT

Từ “concurrent” xuất hiện ở ba tầng khác nhau:

| Tầng | Dấu hiệu | Ý nghĩa |
| --- | --- | --- |
| **Nguồn** | `Spliterator.CONCURRENT` | Nguồn được thiết kế để chịu một dạng thay đổi cấu trúc đồng thời theo hợp đồng |
| **Collector** | `Collector.Characteristics.CONCURRENT` | Accumulator có thể được gọi đồng thời trên cùng bộ tích lũy |
| **Cấu trúc kết quả** | `ConcurrentHashMap`, `ConcurrentMap` | Một số thao tác trên Map có bảo đảm đồng thời theo hợp đồng lớp/map |

Chúng **không thể thay thế cho nhau**. Một nguồn có `Spliterator.CONCURRENT` không bắt buộc collector là concurrent. Một `ConcurrentMap` có thể được tạo từ code tuần tự. Một Collector tự viết khai báo `CONCURRENT` sẽ không tự biến phần tử đầu vào hoặc object bên trong Map thành thread-safe.

Tương tự, đặc tính `Collector.Characteristics.IDENTITY_FINISH` chỉ nói về việc có thể dùng `A` trực tiếp làm `R`. Nó không chứng minh accumulator an toàn đồng thời.

### Stream unordered không nhất thiết là nguồn concurrent

`stream.unordered()` có thể bỏ ràng buộc encounter order, nhưng không biến một `ArrayList` đang bị nhiều thread sửa thành nguồn an toàn. Nếu các thao tác `map`, `filter` hoặc classifier sửa một cấu trúc bên ngoài mà không đồng bộ, rủi ro vẫn tồn tại dù collector ở cuối là concurrent.

## 12. Chiến lược sử dụng parallel + unordered một cách có chủ đích

Nếu **kết quả thật sự không cần thứ tự**, ta có thể diễn đạt điều đó ở pipeline hoặc Collector.

Ví dụ đếm từ:

```java
import java.util.Arrays;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = Arrays.asList(
        "a", "b", "a", "c", "b"
).parallelStream()
 .unordered()
 .collect(Collectors.toConcurrentMap(
         Function.identity(),
         x -> 1L,
         Long::sum
 ));

System.out.println(counts.get("a")); // 2
```

`unordered()` trong ví dụ này **không bắt buộc** để cho phép chiến lược chung, vì `toConcurrentMap` đã có `UNORDERED`. Việc thêm nó chỉ làm rõ rằng pipeline downstream không đòi encounter order. Không nên thêm `unordered()` vào mọi pipeline như một thói quen: nó có thể đổi ý nghĩa của `findFirst`, `limit`, `skip` hoặc những thao tác chọn phần tử “đầu tiên”.

Nếu collector chỉ khai báo `CONCURRENT` (không `UNORDERED`), việc pipeline bỏ encounter order có thể cho phép con đường tích lũy chung. Nhưng điều đó chỉ hợp lệ nếu **nghiệp vụ thật sự cho phép thay đổi thứ tự**, kể cả ở các thao tác trung gian trước khi collect.

### Khi cần kết quả có thứ tự

Nếu yêu cầu giữ thứ tự của một `List`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> ordered = Arrays.asList("C", "A", "B")
        .parallelStream()
        .collect(Collectors.toList());

System.out.println(ordered); // [C, A, B]
```

Đây không phải ví dụ concurrent accumulation vào một List chung, nhưng **vẫn là thu thập từ Stream song song**. Không cần đánh đổi thứ tự nếu yêu cầu nghiệp vụ phụ thuộc vào nó.

Nếu cần danh sách sắp xếp theo thời gian, hãy mô tả khóa sắp xếp và tính ổn định, đừng chỉ chọn một concurrent collector rồi mặc định các phần tử sẽ vào theo thời gian.

## 13. Trường hợp downstream phức tạp và null

### Grouping có downstream không đồng thời

`groupingByConcurrent(classifier, downstream)` hỗ trợ downstream collector như `counting`, `mapping` hoặc `toList`. Collector ngoài có trách nhiệm đảm bảo tích lũy đúng hợp đồng dù downstream không tuyên bố `CONCURRENT`. Không dùng điều đó để kết luận **mỗi container downstream tự nhiên an toàn** khi đem ra dùng ngoài quá trình collect.

Khi nhiều phần tử cùng khóa, có thể phát sinh tranh chấp lớn trên bucket tương ứng; hiệu năng chịu ảnh hưởng mạnh của **phân bố khóa**, không chỉ số lõi CPU.

### Khóa null không được giải quyết nhờ CONCURRENT

`groupingByConcurrent` không chấp nhận classifier trả `null`. `ConcurrentHashMap` cũng không cho phép khóa null. Nếu nguồn có khóa vắng mặt, cần thiết kế chính sách **lọc, thay bằng khóa đại diện không va chạm, hoặc biểu diễn bằng `Optional`** trước khi phân nhóm.

`toConcurrentMap` cũng không nên nhận key/value mapper có thể trả null. Đặc biệt, giá trị null không phải một “giá trị mặc định” an toàn của `ConcurrentMap`. Hãy chuẩn hóa dữ liệu đầu vào hoặc mô hình hóa trạng thái vắng mặt rõ ràng.

### Giữ đủ nhóm hay chỉ nhóm đã thấy?

`groupingByConcurrent` chỉ có thể tạo nhóm từ các phần tử mà classifier thực sự quan sát. Nó **không tự sinh nhóm chưa xuất hiện**. Nếu báo cáo cần hiển thị mọi danh mục (kể cả số lượng 0), phải bổ sung danh sách khóa miền nghiệp vụ sau khi thu thập hoặc thiết kế nguồn/báo cáo chứa đầy đủ khóa dự kiến.

## 14. Khi nào concurrent collector có thể chậm hơn?

`CONCURRENT + UNORDERED` **không bảo đảm** tăng tốc. Chúng mở ra một lựa chọn thực thi, còn hiệu quả phụ thuộc công việc cụ thể.

| Yếu tố | Ảnh hưởng thường gặp |
| --- | --- |
| Nguồn ít phần tử | Overhead phân nhánh và phối hợp có thể lớn hơn phép xử lý |
| Nhiều phần tử chung một khóa | Các cập nhật tranh chấp cùng bucket/container |
| Nhiều khóa độc lập | Có thể phân tán cập nhật tốt hơn, nhưng Map lớn tốn bộ nhớ |
| Accumulator xử lý rẻ | Đồng bộ/atomic operation có thể chiếm phần lớn thời gian |
| Accumulator CPU nặng, thuần | Parallel có thể có lợi nếu nguồn chia được |
| Nguồn I/O tuần tự | Đọc nguồn có thể trở thành nút thắt |
| Bắt buộc encounter order | Một số tối ưu concurrent không được phép |
| Downstream giữ `List` lớn | Kích thước dữ liệu và bộ nhớ tăng theo số phần tử |
| Sắp xếp/loại trùng trước collect | Stateful operations có thể phát sinh bộ đệm và phối hợp |
| Số học dấu phẩy động | Cách nhóm phép cộng có thể làm thay đổi sai số thấp |

Ví dụ đếm vài chục phần tử bằng `parallelStream().collect(toConcurrentMap(...))` có thể **chậm hơn** `stream().collect(toMap(...))`, vì tạo tác vụ và cập nhật concurrent map không miễn phí.

Đo hiệu năng trên dữ liệu đại diện: lượng phần tử, số khóa duy nhất, tỷ lệ trùng, chiều dài chuỗi khóa, chi phí classifier, loại downstream, JDK và số luồng thực tế. Không dùng một lần chạy không warm-up làm kết luận chắc chắn.

Nếu mục tiêu chỉ là tổng số nguyên, `IntStream.sum()` hay `LongStream.sum()` thường đơn giản và không đòi tự thiết kế Collector.

## 15. Kiểm tra tính đúng đắn khi chạy song song

Không đủ để nhìn một lần kết quả và kết luận collector an toàn. Cần kiểm tra ít nhất:

1. **Supplier:** có tạo bộ tích lũy đúng trạng thái ban đầu, độc lập khi được gọi nhiều lần không?
2. **Accumulator:** có an toàn nếu nhiều luồng cùng thao tác lên một `A` không? Nếu không, không khai báo `CONCURRENT`.
3. **Combiner:** có gộp đủ dữ liệu của cả hai nhánh, đúng identity và associativity không?
4. **Finisher:** có cần chuyển kiểu `A → R` không? Nếu có, không dùng `IDENTITY_FINISH`.
5. **Thứ tự:** các kết quả có cần “đầu tiên”, “cuối cùng” hoặc ổn định theo encounter order không?
6. **Pipeline trước collect:** classifier, `map`, `filter` có stateless, non-interfering và không ghi ra biến dùng chung không?
7. **Trường hợp biên:** nguồn rỗng, một phần tử, nhiều phần tử cùng khóa, khóa null, giá trị quá lớn.
8. **Lặp lại thực thi:** kết quả thống kê có bất biến trong nhiều lượt tuần tự và song song không?
9. **Sau khi collect:** có người dùng khác tiếp tục sửa object mutable trong Map cùng lúc không?
10. **Tài nguyên:** nguồn giữ file/Reader/socket đã được đóng ở chủ sở hữu chưa?

Một ví dụ so sánh kết quả tuần tự với concurrent collector:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> data = Arrays.asList(
        "A", "B", "A", "C", "B", "A"
);

Map<String, Long> sequential = data.stream()
        .collect(Collectors.toMap(
                Function.identity(),
                x -> 1L,
                Long::sum
        ));

ConcurrentMap<String, Long> concurrent = data.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Function.identity(),
                x -> 1L,
                Long::sum
        ));

System.out.println(sequential.equals(concurrent)); // true
```

Ở đây hai Map có **cùng nội dung khóa–giá trị**, không có yêu cầu thứ tự. Đây là kiểm tra minh họa, **không thay thế** việc chứng minh an toàn luồng hoặc các bài kiểm tra với tải lớn.

## 16. Vòng đời Stream và nguồn giữ tài nguyên

`collect` là terminal operation: nó tiêu thụ pipeline một lần nhưng **không tự đóng** các nguồn I/O. Đặc tính `CONCURRENT`/`UNORDERED` không thay đổi quy tắc này.

Ví dụ tổng hợp dòng log theo mức độ nghiêm trọng:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static ConcurrentMap<String, Long> countLevels(Path path)
        throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.contains(":"))
                .map(line -> line.substring(0, line.indexOf(':')))
                .collect(Collectors.toConcurrentMap(
                        level -> level,
                        level -> 1L,
                        Long::sum
                ));
    }
}
```

Ví dụ này chạy tuần tự vì không gọi `parallel()`. Collector vẫn concurrent và unordered **về khả năng** nhưng không có nghĩa Java tự tạo các nhánh song song. Chọn `toConcurrentMap` chỉ vì đang đọc tệp không mang lại lợi ích tự động; với nguồn I/O, hãy cân nhắc đặc điểm `Spliterator` và chi phí đọc trước khi quyết định song song.

Phần ví dụ giả định dòng có dấu `:` trước dữ liệu thông điệp và khóa trước dấu hai chấm là hợp lệ. Nếu dữ liệu thật có dòng sai định dạng hoặc khóa rỗng, hãy có chính sách xác thực. Khi quá trình đọc tệp gặp lỗi, Stream có thể ném `UncheckedIOException` trong lúc tiêu thụ; `try-with-resources` vẫn đóng nguồn.

## 17. Checklist lựa chọn Collector phù hợp

| Nhu cầu | Lựa chọn gợi ý | Vì sao |
| --- | --- | --- |
| Giữ phần tử theo thứ tự nguồn | `Collectors.toList()` | Thu thập có ordered semantics, không cần container dùng chung |
| Cần tập các giá trị không trùng | `Collectors.toSet()` | Unordered nhưng không có cam kết concurrent |
| Gom Map và merge theo khóa, không cần concurrent | `Collectors.toMap(...)` | Hợp đồng đơn giản, vẫn dùng được với parallel |
| Gom Map concurrent, không quan tâm encounter order | `Collectors.toConcurrentMap(...)` | Concurrent + unordered |
| Gom nhóm theo khóa và không cần thứ tự trong nhóm | `Collectors.groupingByConcurrent(...)` | Concurrent + unordered |
| Gom nhóm với thứ tự phần tử trong từng nhóm quan trọng | `Collectors.groupingBy(...)` với downstream phù hợp | Không đánh đổi encounter order |
| Chỉ tính tổng hoặc đếm số | `sum()`, `count()` | Terminal operation chuyên dụng |
| Cần custom concurrent accumulator | `Collector.of(...)` với container thực sự hỗ trợ | Chứng minh hợp đồng trước khi khai báo cờ |
| Muốn kết quả cuối khác kiểu container | Collector có finisher thật | Không khai báo `IDENTITY_FINISH` |
| Chỉ cần giữ “bản ghi mới nhất” | Merge theo timestamp + khóa phụ ổn định | Không dựa vào thứ tự cập nhật concurrent |

Trước khi thêm `parallel()`, hãy hỏi: “Nếu các phần tử được xử lý theo thứ tự khác, yêu cầu nghiệp vụ có còn đúng không?” Nếu câu trả lời là không, **đừng dùng `UNORDERED` chỉ vì muốn nhanh hơn**.

## 18. Các lỗi phổ biến

| Sai lầm | Vì sao sai hoặc nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Nghĩ `parallelStream` tự chia sẻ một container giữa mọi luồng | Java có thể dùng nhiều container độc lập và combiner | Hiểu hai chiến lược collect |
| Chỉ thêm `UNORDERED` rồi cho nhiều luồng sửa `ArrayList` | Unordered không đảm bảo thread-safe | Phải có `CONCURRENT` **và** accumulator đúng hợp đồng |
| Khai báo `CONCURRENT` cho `ArrayList::add` | Có thể race, mất dữ liệu | Bỏ cờ, dùng `toList` hoặc container thích hợp |
| Nghĩ `CONCURRENT` tự hàm ý `UNORDERED` | Hai đặc tính độc lập | Kiểm tra nhu cầu thứ tự riêng |
| Nghĩ `CONCURRENT` luôn khiến collector dùng một container | Framework không bị buộc chọn chiến lược đó | Viết combiner đúng |
| Dùng `groupingByConcurrent` và mong List trong nhóm có encounter order | Collector unordered | Chọn collector giữ thứ tự hoặc sắp xếp sau |
| Thấy `ConcurrentMap` rồi cho rằng mọi giá trị mutable an toàn | Thread-safety của Map không lan sang value object | Đồng bộ/đóng băng dữ liệu đúng mô hình |
| Dùng `(a,b) -> a` cho “đến đầu tiên” trong `toConcurrentMap` | Thứ tự xung đột không phản ánh encounter order | Chọn theo thuộc tính dữ liệu |
| Dùng phép merge không có tính kết hợp | Kết quả phụ thuộc cách phân nhánh | Thiết kế phép gộp hợp lệ |
| Chỉ cần tổng nhưng tự tạo concurrent collector phức tạp | Thêm code, boxing, overhead | `LongStream.sum()` |
| Chọn `IDENTITY_FINISH` cho kết quả phải đổi kiểu | Finisher có thể bị bỏ qua | Bỏ cờ và giữ finisher |
| Bật parallel cho nguồn nhỏ hoặc khó chia | Chi phí phối hợp lớn | Đo trước khi tối ưu |
| `collect` xong nghĩ nguồn tệp tự đóng | Terminal operation không tự `close` | `try-with-resources` |

## 19. Câu hỏi tự kiểm tra

1. `parallelStream()` có bắt buộc mọi luồng dùng chung một bộ tích lũy không? **Không**. Nó có thể dùng nhiều bộ chứa rồi combiner.
2. `CONCURRENT` của Collector bảo đảm gì? **Accumulator có thể được gọi đồng thời trên cùng một bộ chứa `A`**.
3. `UNORDERED` có nghĩa Java bắt buộc xáo trộn dữ liệu không? **Không**, chỉ không cam kết encounter order.
4. Với Stream parallel có encounter order, điều kiện nào cho phép một container tích lũy chung? **Collector có cả `CONCURRENT` và `UNORDERED`**.
5. Với Stream parallel không có encounter order, collector chỉ có `CONCURRENT` (không `UNORDERED`) có thể tích lũy chung không? **Có thể**, nếu collector thực sự an toàn theo hợp đồng.
6. `Collectors.toSet()` là unordered thì có đồng nghĩa concurrent không? **Không**.
7. `Collectors.toList()` có thể dùng với parallel stream dù không concurrent không? **Có**; framework có thể kết hợp các container riêng.
8. Vì sao `LongAdder` phù hợp cho custom concurrent accumulator? **Nó hỗ trợ nhiều luồng cập nhật cùng bộ đếm**.
9. Khi `A` là `LongAdder` và `R` là `Long`, có dùng `IDENTITY_FINISH` không? **Không**, finisher cần chuyển kết quả.
10. `groupingByConcurrent(..., toList())` có cam kết giữ thứ tự gặp phần tử trong mỗi nhóm không? **Không**.
11. `ConcurrentMap<K,List<V>>` có làm các List giá trị an toàn cho cập nhật đồng thời từ caller không? **Không**.
12. Nếu cần sự kiện mới nhất, tại sao không dùng merge `(a,b) -> b` trên concurrent collector? **Vì thứ tự gộp không phải timestamp**.
13. `UNORDERED` của Collector có khác `stream.unordered()` không? **Có**; một cờ mô tả phép thu thập, một thao tác bỏ ràng buộc order của pipeline.
14. Khi nào concurrent collector có thể chậm hơn? **Khi nguồn nhỏ, accumulator rẻ, khóa tranh chấp nhiều hoặc chi phí phối hợp cao**.
15. `collect` có đóng `Files.lines` tự động không? **Không**; phải đóng Stream bằng `try-with-resources`.

**Nguyên tắc áp dụng:** Chỉ coi **thu thập đồng thời vào cùng một container** là hợp lệ khi Stream chạy song song, Collector thực sự có `CONCURRENT`, và yêu cầu thứ tự được thỏa bằng một Stream unordered **hoặc** một Collector `UNORDERED`. Các cờ là **cam kết tính đúng đắn**, không phải công tắc tăng tốc. Hãy ưu tiên collector chuẩn, giữ accumulator/combiner đúng hợp đồng, tách biệt an toàn luồng của Map với giá trị bên trong, và chỉ tối ưu song song khi kết quả không đổi về ngữ nghĩa cùng với số đo hiệu năng thực tế.
