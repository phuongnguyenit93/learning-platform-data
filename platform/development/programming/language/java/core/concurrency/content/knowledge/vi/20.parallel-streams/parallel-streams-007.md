# Collector concurrent so với collector tuần tự trong Java Parallel Streams

## Mục tiêu và phạm vi

Trong Java Stream API, `parallelStream()` quyết định khả năng xử lý song song, còn `Collector` định nghĩa **cách biến nhiều phần tử thành một kết quả**. Hai khái niệm này độc lập: collector không concurrent vẫn có thể được dùng hợp lệ trong một parallel stream.

Sau bài này, bạn có thể:

1. Phân biệt **non-concurrent collector** và **concurrent collector** khi chạy parallel reduction.
2. Giải thích ba đặc tính `CONCURRENT`, `UNORDERED` và `IDENTITY_FINISH`, cùng điều kiện cho phép nhiều worker ghi vào một result container.
3. Chọn giữa `groupingBy` và `groupingByConcurrent`, `toMap` và `toConcurrentMap`; hiểu tác động đến encounter order, thread safety và contention.
4. Thiết kế collector tự tạo đúng contract, kiểm tra output và tránh lạm dụng song song hóa.
5. Đánh giá hiệu năng bằng dữ liệu và phép đo hợp lý, không dựa vào tên API.

Nội dung hoàn toàn thuộc **Java SE concurrency, Stream và Collector**, chạy được từ Java 17 trở lên.

## 1. Parallel stream và concurrent collector là hai quyết định khác nhau

Ví dụ:

~~~java
// Minh họa: cần import java.util.List và java.util.stream.Collectors.
List<String> words = List.of("ant", "ape", "bee");

List<String> uppercase = words.parallelStream()
        .map(String::toUpperCase)
        .collect(Collectors.toList());
~~~

`parallelStream()` cho phép xử lý các phần dữ liệu song song. `Collectors.toList()` là collector **non-concurrent**, nhưng lời gọi vẫn đúng. Với danh sách đầu vào có encounter order, kết quả có thứ tự `[ANT, APE, BEE]`, dù `map` có thể thực thi ở các worker khác nhau.

**Non-concurrent** không có nghĩa “chỉ chạy tuần tự”. Nó có nghĩa accumulator của collector **không bảo đảm** an toàn khi nhiều thread cùng ghi vào **một** container. Framework có thể tạo các container tích lũy độc lập, để các worker xử lý riêng rồi dùng combiner gộp kết quả.

~~~text
Parallel source
     |
     +--> Worker A --> Accumulator A (private container A)
     |                                     \
     +--> Worker B --> Accumulator B --------> combiner --> result
     |                                     /
     +--> Worker C --> Accumulator C ------/
~~~

Đây là mô hình khái niệm; số worker, số container và cách chia/merge phụ thuộc implementation. Vì các container chưa bị chia sẻ để ghi đồng thời, các collector non-concurrent có thể sử dụng `ArrayList`/`HashMap` bên trong. Việc collector nội bộ sử dụng một cấu trúc không thread-safe **không khiến** `parallelStream().collect(Collectors.groupingBy(...))` tự động bị data race.

Mặt khác, một stream tuần tự vẫn có thể sử dụng collector concurrent. Trong trường hợp đó không có nhiều worker đồng thời tích lũy, nên khả năng concurrent không có lợi ích riêng.

## 2. Collector contract: supplier, accumulator, combiner, finisher

Một `Collector<T,A,R>` mô tả cách tích lũy đầu vào kiểu `T` vào container trung gian `A` rồi tạo kết quả `R`:

| Thành phần | Vai trò |
| --- | --- |
| `supplier()` | Tạo một container tích lũy mới. |
| `accumulator()` | Đưa phần tử `T` vào container `A`. |
| `combiner()` | Gộp hai container `A` theo cách đúng ngữ nghĩa reduction. |
| `finisher()` | Chuyển container `A` thành kết quả `R`. |
| `characteristics()` | Khai báo những bảo đảm cho runtime tối ưu hóa phép thu gom. |

Collector phải thỏa những quy tắc như tính tương thích của accumulator/combiner, tính kết hợp của phép gộp và tính độc lập với cách dữ liệu được chia. Với một phép tổng: kết quả phải như nhau dù nhóm thành `(a+b)+c` hay `a+(b+c)`. Nếu hàm gộp có side effect ngoài hoặc phụ thuộc vào lịch chạy của thread, kết quả song song dễ sai.

### Ba đặc tính cần phân biệt

- **`CONCURRENT`:** accumulator có thể được gọi **đồng thời với cùng một result container** mà vẫn đúng. Điều này cần container và thao tác cập nhật thực sự hỗ trợ concurrency.
- **`UNORDERED`:** collector không cam kết bảo toàn encounter order của các phần tử. Nó **không có nghĩa** collector tự động thread-safe.
- **`IDENTITY_FINISH`:** finisher là phép đồng nhất; representation container tích lũy có thể được dùng trực tiếp như kết quả. Không được khai báo khi finisher biến đổi kiểu hoặc cấu trúc.

Ví dụ `Collectors.toSet()` có thể unordered nhưng **không concurrent**. `Collectors.groupingByConcurrent(...)` là concurrent **và** unordered. Còn `Collectors.toList()` không concurrent và thường phải tôn trọng encounter order khi thu gom ordered stream.

**Điều kiện để stream có thể dùng concurrent reduction:**

1. Stream phải **parallel**;
2. Collector phải có đặc tính **`CONCURRENT`**;
3. **Hoặc** stream là unordered, **hoặc** collector có `UNORDERED`.

Khi các điều kiện này đúng, implementation **có thể** cho nhiều worker tích lũy vào **cùng một** container, giảm nhu cầu tạo/gộp nhiều container riêng. API không bắt buộc implementation luôn thực hiện tối ưu ấy. Nếu collector không có `CONCURRENT`, thêm `stream.unordered()` **không** biến accumulator thành thread-safe.

~~~text
Parallel source
    |           |           |
  worker A    worker B    worker C
    |           |           |
    +-----------+-----------+
                |
         Shared container
         concurrent updates
                |
              result
~~~

Concurrent reduction giúp giảm chi phí **combiner**, nhưng có thể tăng tranh chấp cập nhật chung; vì vậy **concurrent không bảo đảm nhanh hơn**.

## 3. Encounter order: thứ tự đầu vào có quan trọng không?

**Encounter order** là thứ tự gặp các phần tử của nguồn ordered, ví dụ `List.of("ant", "ape", "bee")`. Không nên nhầm thứ tự worker thực thi với thứ tự kết quả được API cam kết.

Với dữ liệu có thứ tự, `groupingBy(key)` sử dụng collector non-concurrent và giữ ngữ nghĩa thu gom có thứ tự trong danh sách từng nhóm. Ngược lại, `groupingByConcurrent(key)` **không bảo đảm** list thuộc một khóa duy trì encounter order. Nó có thể chứa cùng phần tử nhưng xuất hiện theo trình tự khác.

- Nếu kết quả dùng để **thống kê tần suất hoặc gom nhóm không phụ thuộc thứ tự**, collector unordered thường phù hợp.
- Nếu phần tử trong nhóm phải theo **thứ tự sự kiện**, cần chọn collector giữ encounter order hoặc sắp xếp rõ ràng theo timestamp/sequence sau khi gom.
- Với `.unordered()`, bạn tuyên bố có thể bỏ ràng buộc encounter order ở các bước phù hợp; runtime có quyền tối ưu nhưng không có nghĩa mọi kết quả sẽ đảo ngẫu nhiên.
- `ConcurrentMap` không đảm bảo thứ tự duyệt các khóa. Không dùng thứ tự in ra của `ConcurrentHashMap` làm contract dữ liệu.

Chỉ thay `groupingBy` bằng `groupingByConcurrent` sau khi xác nhận việc mất thứ tự **không thay đổi yêu cầu nghiệp vụ**.

## 4. Ví dụ Java 17+: groupingBy và groupingByConcurrent

Tạo tệp `GroupingCollectorsDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class GroupingCollectorsDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "ant", "ape", "bear", "bee", "cat", "cow", "dog", "duck");

        Map<Character, List<String>> grouped = words.parallelStream()
                .collect(Collectors.groupingBy(s -> s.charAt(0)));

        ConcurrentMap<Character, List<String>> groupedConcurrent =
                words.parallelStream()
                     .collect(Collectors.groupingByConcurrent(s -> s.charAt(0)));

        System.out.println("groupingBy a: " + grouped.get('a'));

        List<String> a = new ArrayList<>(groupedConcurrent.get('a'));
        Collections.sort(a);
        System.out.println("groupingByConcurrent a sorted: " + a);

        boolean sameMembers = grouped.keySet().equals(groupedConcurrent.keySet())
                && grouped.keySet().stream().allMatch(key -> {
                    List<String> left = new ArrayList<>(grouped.get(key));
                    List<String> right = new ArrayList<>(groupedConcurrent.get(key));
                    Collections.sort(left);
                    Collections.sort(right);
                    return left.equals(right);
                });
        System.out.println("Same members: " + sameMembers);

        ConcurrentMap<Character, Long> counts = words.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        s -> s.charAt(0), Collectors.counting()));
        System.out.println("Counts: " + new TreeMap<>(counts));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GroupingCollectorsDemo.java
java GroupingCollectorsDemo
~~~

Đầu ra chính xác:

~~~text
groupingBy a: [ant, ape]
groupingByConcurrent a sorted: [ant, ape]
Same members: true
Counts: {a=2, b=2, c=2, d=2}
~~~

Phân tích:

1. `grouped` là `Map<Character,List<String>>` được tạo bởi collector **non-concurrent**. Stream xử lý song song nhưng không dùng một `HashMap` chung bị nhiều thread tự ý sửa.
2. `groupedConcurrent` là `ConcurrentMap<Character,List<String>>`. Collector có đặc tính concurrent, unordered, nên thứ tự phần tử trong list nhóm `a` **không phải contract**.
3. Tạo `ArrayList` bản sao rồi `sort` là cách cố định thứ tự khi **hiển thị/so sánh**, không đồng nghĩa collector đã bảo toàn thứ tự.
4. `sameMembers` kiểm tra hai phía có cùng khóa, cùng thành viên mỗi khóa **sau chuẩn hóa thứ tự**.
5. `Collectors.counting()` là downstream collector để tổng hợp số phần tử theo từng nhóm; `TreeMap` chỉ chuẩn hóa thứ tự khóa khi in.

### Điều thường bị hiểu sai về downstream

`groupingByConcurrent(classifier, Collectors.counting())` **hợp lệ**, dù bản thân `counting()` không quảng bá `CONCURRENT`. Collector ngoài phải phối hợp an toàn việc tích lũy downstream cho từng key. Tuy nhiên điều đó có thể đòi hỏi đồng bộ hoặc điều phối theo key và làm giảm lợi ích nếu hàng triệu phần tử dồn vào vài key “nóng”.

Còn dạng `groupingByConcurrent(classifier)` trả về `ConcurrentMap<K,List<T>>` nhưng **không bảo đảm các list kết quả thread-safe để bên ngoài tiếp tục gọi `add()` từ nhiều thread**. An toàn của quá trình thu gom do collector quản lý không tương đương an toàn cho mọi thao tác trên các object sau khi thu gom xong.

## 5. So sánh các collector thường dùng

| Collector | Có `CONCURRENT`? | Thứ tự | Mục đích |
| --- | --- | --- | --- |
| `toList()` | Không | Tôn trọng encounter order với ordered stream | Cần danh sách theo thứ tự nguồn |
| `toSet()` | Không | Không cam kết encounter order | Loại phần tử trùng |
| `groupingBy(key)` | Không | Có ngữ nghĩa encounter order trong nhóm của ordered stream | Gom nhóm theo khóa, có combiner |
| `groupingByConcurrent(key)` | Có, unordered | Không cam kết thứ tự phần tử trong nhóm | Gom nhóm song song, không cần thứ tự |
| `toMap(key, value, merge)` | Không | Không bảo đảm iteration order của Map | Gộp các giá trị theo khóa |
| `toConcurrentMap(key, value, merge)` | Có, unordered | Không cam kết thứ tự khóa/merge theo encounter order | Gom vào ConcurrentMap |
| `counting()` | Không | Giá trị số đếm không phụ thuộc thứ tự | Đếm phần tử hoặc dùng downstream |

**Phân biệt với loại collection trả về:** một `ConcurrentMap` là cấu trúc hỗ trợ cập nhật concurrent, nhưng `Collector.CONCURRENT` nói về **contract của accumulator trong quá trình reduce**. Chỉ nhìn kiểu trả về chưa đủ suy ra chiến lược collect, và một map thread-safe cũng không bảo đảm các object giá trị trong map đều thread-safe.

### Khóa trùng với `toMap`/`toConcurrentMap`

Khi mapper tạo khóa trùng, overload `toConcurrentMap(keyMapper,valueMapper)` không có hàm merge sẽ ném ngoại lệ do duplicate key. Có thể dùng overload ba tham số:

~~~java
// Minh họa: values là Stream hoặc Collection các Item có method category().
ConcurrentMap<String, Integer> frequencies = values.parallelStream()
        .collect(Collectors.toConcurrentMap(
                item -> item.category(),
                item -> 1,
                Integer::sum));
~~~

Phép merge `Integer::sum` phù hợp đếm tần suất vì kết hợp được và không nhạy thứ tự.

Ngược lại, phép merge `(oldValue, newValue) -> newValue` **không** bảo đảm chọn phần tử *cuối cùng theo encounter order* trong concurrent unordered collector. Nếu mục tiêu là “record có timestamp mới nhất”, dùng comparator theo timestamp và tiêu chí phá hòa rõ ràng. Các phép merge không associative như phép trừ cũng không có ngữ nghĩa song song ổn định khi grouping lại.

## 6. Ví dụ Java 17+: tự tạo collector concurrent đúng contract

Một ví dụ đơn giản dùng `LongAdder`, bộ cộng hỗ trợ nhiều thread cùng cập nhật, để thu gom tổng. Tạo tệp `ConcurrentCollectorDemo.java`:

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ConcurrentCollectorDemo {
    public static void main(String[] args) {
        Collector<Integer, ?, Long> concurrentSum = Collector.of(
                LongAdder::new,
                (adder, value) -> adder.add(value),
                (left, right) -> {
                    left.add(right.sum());
                    return left;
                },
                LongAdder::sum,
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED);

        long sum = IntStream.rangeClosed(1, 1000)
                .boxed()
                .parallel()
                .collect(concurrentSum);
        System.out.println("Sum = " + sum);

        ConcurrentMap<String, Integer> frequency =
                IntStream.rangeClosed(1, 10)
                        .parallel()
                        .boxed()
                        .collect(Collectors.toConcurrentMap(
                                n -> n % 2 == 0 ? "even" : "odd",
                                n -> 1,
                                Integer::sum));
        System.out.println("Even count = " + frequency.get("even"));
        System.out.println("Odd count = " + frequency.get("odd"));
        System.out.println("Collector concurrent = " +
                concurrentSum.characteristics()
                        .contains(Collector.Characteristics.CONCURRENT));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ConcurrentCollectorDemo.java
java ConcurrentCollectorDemo
~~~

Đầu ra:

~~~text
Sum = 500500
Even count = 5
Odd count = 5
Collector concurrent = true
~~~

Tại sao collector này đúng?

- `supplier` dùng `LongAdder::new`: tạo container thích hợp cho concurrent update.
- `accumulator` dùng `adder.add(value)`: nhiều worker có thể cộng vào cùng container an toàn.
- `combiner` thêm tổng của container phải vào container trái. Concurrent collector vẫn **cần** combiner hợp lệ trong contract dù runtime có thể chọn dùng một container.
- `finisher` dùng `LongAdder::sum` trả về `Long`. Không khai báo `IDENTITY_FINISH` vì `A` là `LongAdder`, còn `R` là `Long`.
- Tổng là phép toán không phụ thuộc thứ tự nên `UNORDERED` phù hợp. `LongAdder.sum()` không phải snapshot nguyên tử nếu vẫn có cập nhật đồng thời; ở đây finisher chạy sau khi quá trình collect đã hoàn thành.
- `toConcurrentMap` dùng `Integer::sum` để gộp 10 phần tử vào hai khóa: `even` và `odd`.

Ví dụ minh họa **tính đúng của contract**, không khẳng định `LongAdder` nhanh hơn phép `IntStream.sum()` thông thường. Với tổng số, `mapToLong(...).sum()` thường là cách ngắn gọn, dễ hiểu; hãy dùng collector tự tạo chỉ khi cần cấu trúc tích lũy và contract cụ thể.

## 7. Những lỗi nguy hiểm với concurrent collector

### Lỗi 1: quảng bá CONCURRENT nhưng dùng ArrayList không an toàn

~~~java
// ĐOẠN SAI (minh họa, không dùng trong ứng dụng):
Collector<String, List<String>, List<String>> broken = Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        Collector.Characteristics.CONCURRENT,
        Collector.Characteristics.UNORDERED);
~~~

Đoạn sai cần `java.util.ArrayList`, `java.util.List` và `java.util.stream.Collector`; nó không phải chương trình độc lập. `ArrayList.add()` **không an toàn** khi nhiều thread cập nhật cùng list. Khai báo `CONCURRENT` sai sự thật có thể gây mất phần tử, sai size hoặc hỏng trạng thái. Một test đôi khi chạy “đúng” không chứng minh code an toàn: lịch xen kẽ thực thi thay đổi giữa các lần chạy.

Cách khắc phục tùy yêu cầu: bỏ `CONCURRENT` để dùng mô hình container riêng + combiner, hoặc dùng container và accumulator thực sự concurrent, như `ConcurrentLinkedQueue` nếu thứ tự không quan trọng. Cần đánh giá overhead và tính đúng trước khi gắn cờ tối ưu.

### Lỗi 2: side effect ngoài Collector

~~~java
// ĐOẠN SAI: shared là một ArrayList dùng chung chưa đồng bộ.
words.parallelStream()
     .peek(shared::add)
     .collect(Collectors.toList());
~~~

Đây là mã minh họa với `shared` và `words` chưa khai báo. Dù `toList()` chuẩn xử lý đúng, `peek(shared::add)` vẫn có data race vì ghi vào list **ngoài collector**. Không dùng side effect trong `map`, `filter`, `peek` để gom kết quả; hãy diễn tả phép biến đổi và dùng collector phù hợp.

### Lỗi 3: hiểu lầm về thứ tự

`groupingByConcurrent` có thể cho các list đúng thành viên nhưng thứ tự khác nguồn. Không dùng `list.get(0)` để suy ra “sự kiện đầu tiên” nếu trình tự được yêu cầu mà collector không bảo đảm. Thay vào đó lưu timestamp/sequence và lựa chọn theo quy tắc xác định.

### Lỗi 4: tranh chấp key nóng

Nếu 90% dữ liệu thuộc một khóa, nhiều worker có thể cùng cập nhật vùng dữ liệu của khóa đó. Chi phí đồng bộ/contended update dễ lấn át lợi ích bỏ combiner. Thử phân chia theo partition rồi gộp tổng hợp, hoặc dùng collector non-concurrent, sau khi có số đo cho workload thực.

### Lỗi 5: quá nhiều công việc nhỏ

Parallel stream có chi phí chia việc, ForkJoin scheduling, tạo object và gộp kết quả. Nếu mỗi phần tử xử lý quá nhẹ, stream tuần tự có thể nhanh hơn. Collector concurrent cũng không thay thế việc thiết kế độ hạt công việc thích hợp.

## 8. Khi nào collector concurrent có thể hữu ích hơn?

| Đặc điểm workload | Tác động dự kiến |
| --- | --- |
| Nhiều phần tử, nhiều key, phân bố đều | Các cập nhật có cơ hội phân tán; giảm việc merge map riêng. |
| Rất ít key, tần suất tập trung | Contention cao; concurrent có thể không lợi. |
| Cần thứ tự ổn định trong từng nhóm | Collector unordered có thể vi phạm yêu cầu. |
| Downstream counting hoặc reduce đơn giản | Có thể thử hai lựa chọn và đo throughput thực tế. |
| Downstream tạo list/set lớn | Allocation, bộ nhớ và đồng bộ per-key có thể chiếm ưu thế. |
| Dữ liệu rất nhỏ | Overhead của parallelism thường không đáng. |
| Nguồn chia khó, xử lý không đồng đều | Bottleneck ở Spliterator/task partition vẫn còn dù đổi collector. |

Một collector “concurrent” giúp **cho phép** concurrent reduction, không đảm bảo **lúc nào cũng dùng** shared container, càng không đảm bảo nhanh hơn collector non-concurrent. Với grouping, `groupingBy` có thể tốn chi phí gộp nhiều map; `groupingByConcurrent` có thể tốn chi phí tranh ghi vào map và một số key. Kết quả phụ thuộc dữ liệu và mục tiêu.

## 9. Phương pháp benchmark đáng tin

Để quyết định trên ứng dụng thực:

1. **Kiểm chứng correctness trước:** xác nhận số phần tử input bằng tổng số phần tử trong nhóm, số khóa và giá trị thống kê; nếu unordered thì chuẩn hóa thứ tự khi so sánh.
2. **So sánh cùng workload:** thử `stream().collect(groupingBy(...))`, `parallelStream().collect(groupingBy(...))` và `parallelStream().collect(groupingByConcurrent(...))`. Không so sánh hai cách chỉ khác thứ tự input hay kiểu dữ liệu.
3. **Thử phân bố khác nhau:** ít key nóng, nhiều key đều; dữ liệu nhỏ/lớn; `counting` so với thu gom `List`.
4. **Sử dụng JMH** khi cần kết luận hiệu năng vi mô: warm-up, nhiều iteration, fork JVM; không dựa vào một lượt `System.nanoTime()`.
5. **Đo các yếu tố phù hợp:** throughput, latency, CPU sử dụng, allocation, GC, contention và chi phí combiner; thông tin CPU quota/cores/JDK rất quan trọng.
6. **Kiểm tra hệ quả chung:** parallel streams thường dùng common `ForkJoinPool`; benchmark một mình có thể khác ứng dụng chạy nhiều công việc đồng thời.
7. **Chọn cách đơn giản khi đủ nhanh:** correctness, thứ tự theo contract và khả năng bảo trì quan trọng hơn một lợi ích rất nhỏ không ổn định.

Bài thực hành: tạo 100.000 số từ `0` tới `99_999`, gom theo khóa `n % k` với `k = 2`, `100` và `10_000`. So sánh tính đúng của `groupingBy` và `groupingByConcurrent` rồi benchmark. Quan sát trường hợp ít khóa nóng và trường hợp nhiều khóa, đừng tự suy ra collector concurrent luôn tối ưu.

## 10. Checklist chọn Collector

- **Cần giữ thứ tự trong List?** Ưu tiên collector tôn trọng encounter order hoặc post-process bằng tiêu chí thứ tự thực sự.
- **Cần gom nhóm nhưng không cần thứ tự?** Thử `groupingByConcurrent` và benchmark với `groupingBy`.
- **Cần thống kê theo khóa, có trùng?** Chọn `toConcurrentMap` có merge function associative, có ngữ nghĩa rõ ràng.
- **Tự xây collector?** Kiểm tra supplier/accumulator/combiner/finisher, tính độc lập với cách chia dữ liệu, và chỉ khai báo `CONCURRENT` khi accumulator thật sự an toàn với một container chung.
- **Dùng downstream không concurrent?** Không mặc định collector ngoài sai; nhưng phải hiểu synchronization/contended-key behavior của collector tổng thể.
- **Đã có kết quả nhanh hơn?** Xác minh correctness, input, warm-up, phân bố key, CPU và GC trước khi kết luận.

Điểm cần ghi nhớ: **parallel stream có thể chạy song song với collector không concurrent nhờ container riêng và combiner. Concurrent collector chỉ cho phép tích lũy đồng thời trên cùng container khi contract về thread safety và thứ tự cho phép. Lựa chọn đúng dựa vào ngữ nghĩa dữ liệu và phép đo thực tế.**

### Tham khảo Java chính thức

- [Java 21 Stream package: parallelism, ordering và concurrent reduction](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html)
- [Java 21 Collector API: Characteristics và contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html)
- [Java 21 Collectors API: groupingBy, groupingByConcurrent, toConcurrentMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html)
- [JMH: Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/)