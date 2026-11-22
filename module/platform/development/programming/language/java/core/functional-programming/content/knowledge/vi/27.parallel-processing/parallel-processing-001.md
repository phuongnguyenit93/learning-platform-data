# parallelStream(), parallel() và sequential() trong Java

Java Stream API hỗ trợ hai **chế độ thực thi** của một pipeline: **tuần tự (sequential)** và **song song (parallel)**. Chế độ tuần tự thường dễ suy luận và có ít chi phí điều phối hơn. Chế độ song song cho phép Stream framework phân chia công việc để xử lý trên nhiều luồng khi phù hợp, nhưng **không bảo đảm** mọi pipeline đều dùng nhiều thread hoặc chạy nhanh hơn.

Ba API thường gặp nhất là:

- **`collection.parallelStream()`**: tạo một Stream **ban đầu ở chế độ song song** từ `Collection`.
- **`stream.parallel()`**: yêu cầu Stream pipeline **chuyển sang chế độ song song**.
- **`stream.sequential()`**: yêu cầu Stream pipeline **chuyển sang chế độ tuần tự**.

Để so sánh, `collection.stream()` thông thường tạo Stream tuần tự. Cả hai mode có thể dùng các intermediate và terminal operations như `map`, `filter`, `collect`, `reduce`, `toList`, nhưng cách triển khai công việc bên trong và những cam kết về thứ tự gọi callback cần được hiểu đúng.

**Điểm quan trọng nhất:** `parallel()` và `sequential()` là thao tác cấu hình mode của **cả pipeline khi terminal operation thực thi**, không phải lời hứa rằng đoạn `map` trước `parallel()` chạy tuần tự còn đoạn `map` sau nó chạy song song. Nếu một pipeline gọi thay đổi mode nhiều lần, **lựa chọn mode cuối cùng** là lựa chọn có hiệu lực khi thực thi.

Bài học tập trung vào cú pháp, target của từng API, thực thi lazy, encounter order, `forEach`/`forEachOrdered`, reduce/collect đúng, shared mutable state và cách quyết định có nên dùng parallel.

## 1. Stream tuần tự và song song là gì?

Một Stream là **pipeline thao tác trên nguồn dữ liệu**, không phải một collection đã lưu sẵn kết quả biến đổi. Pipeline thường gồm:
1. **Source**: `List`, mảng, dãy `IntStream`, hoặc nguồn khác.
2. **Intermediate operations**: `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`… thường **lazy**.
3. **Terminal operation**: `toList`, `collect`, `sum`, `reduce`, `count`, `forEach`, `findFirst`… kích hoạt việc thực thi.

Ở chế độ **sequential**, pipeline sử dụng cách đánh giá tuần tự. Ở chế độ **parallel**, thư viện **có thể** chia công việc thành các phần, xử lý trên nhiều thread rồi kết hợp kết quả, nhưng chi tiết lập lịch là implementation detail.

Mã minh họa trong một phương thức:

```java
List<Integer> source = List.of(1, 2, 3, 4, 5);

List<Integer> sequential = source.stream()
        .map(n -> n * n)
        .toList();

List<Integer> parallel = source.parallelStream()
        .map(n -> n * n)
        .toList();
```

Cần import `java.util.List`. Với nguồn List có thứ tự, cả hai kết quả đều là `[1, 4, 9, 16, 25]`. Tuy nhiên, **kết quả có thứ tự giống nhau không chứng minh hai pipeline chạy theo cùng lịch trình**.

**Cần phân biệt**: chế độ parallel không đồng nghĩa chạy bất đồng bộ theo nghĩa trả về `Future`. Một terminal operation như `toList()` thông thường **chờ kết quả hoàn tất** rồi mới trả về danh sách. Parallel Stream cũng không tự cung cấp cơ chế retry, timeout, transaction hoặc hủy công việc bất kỳ theo nhu cầu ứng dụng.

## 2. collection.parallelStream(): tạo nguồn ở chế độ parallel

`parallelStream()` là phương thức của interface **`Collection<E>`**, nên những collection như `List` hoặc `Set` cung cấp API này.

```java
List<String> items = List.of("A", "B", "C");
Stream<String> work = items.parallelStream();
boolean parallel = work.isParallel(); // true
```

Đây là mảnh mã cần import `java.util.List` và `java.util.stream.Stream`. `isParallel()` là phép kiểm tra **cờ mode của Stream**, không phải phép đo số worker threads đang hoạt động.

Nguồn thường gặp:

```java
Stream<Integer> a = numbers.stream();         // sequential
Stream<Integer> b = numbers.parallelStream(); // parallel
```

Ở đây `numbers` là một `Collection<Integer>` có sẵn. **Không có `parallelStream()` trên đối tượng `Stream`** theo API `Stream`. Nếu đã có một Stream, hãy dùng `parallel()`.

Ví dụ đúng và sai cần phân biệt:

```java
Stream<Integer> s = numbers.stream().parallel(); // đúng
// numbers.stream().parallelStream(); // SAI: Stream không có parallelStream()
```

`parallelStream()` không thay đổi chính collection thành một “collection song song”. Mỗi lần gọi tạo Stream mới; khi gọi terminal operation, Stream sẽ duyệt nguồn phù hợp hợp đồng của nó. Không được sửa nguồn đang duyệt nếu việc đó vi phạm yêu cầu non-interference.

### Có nên dùng parallelStream() trên mọi Collection?

Không. Ví dụ, một List rất nhỏ chỉ có vài phần tử và phép tính đơn giản thường không đủ công việc để bù chi phí chia/gộp. Một source khó chia có thể không tận dụng parallel tốt như mảng, `ArrayList` hoặc `IntStream.range`.

Nếu nguồn không có **encounter order** xác định, ví dụ một `HashSet`, parallel không tự tạo một thứ tự ổn định. Đừng viết unit test giả định `HashSet.parallelStream().toList()` luôn giữ đúng thứ tự đã thấy trong một lần chạy.

## 3. stream.parallel(): chuyển mode của pipeline

`parallel()` là phương thức của `BaseStream` và có sẵn trên object stream cũng như primitive streams:

```java
Stream<Integer> s = numbers.stream().parallel();
IntStream ints = IntStream.rangeClosed(1, 10).parallel();
LongStream longs = LongStream.of(10L, 20L).parallel();
DoubleStream doubles = DoubleStream.of(1.0, 2.0).parallel();
```

Đây là mảnh mã cần các import trong `java.util.stream` tương ứng; `numbers` là Collection có sẵn. Không phải mỗi phần tử được biến thành một thread riêng. Framework quyết định cách thực thi, chia dữ liệu và kết hợp kết quả.

Một pipeline có thể được cấu hình như sau:

```java
List<Integer> result = numbers.stream()
        .filter(n -> n > 0)
        .parallel()
        .map(n -> n * 2)
        .toList();
```

Nó là **một** pipeline được cấu hình parallel, chứ không phải một phần `filter` đã chắc chắn chạy xong tuần tự trước khi `parallel` được gọi. Intermediate operations thường chưa chạy khi terminal operation chưa bắt đầu.

**Gọi `parallel()` không tự thực thi dữ liệu.** Muốn có kết quả, bạn vẫn cần terminal operation như `toList`, `collect` hoặc `sum`.

## 4. stream.sequential(): trở về chế độ tuần tự

`sequential()` cũng là phương thức của `BaseStream`; nó yêu cầu pipeline thực thi tuần tự:

```java
Stream<Integer> s = numbers.parallelStream().sequential();
boolean parallel = s.isParallel(); // false
```

Bạn có thể dùng `sequential()` khi một pipeline ban đầu nhận từ nguồn song song nhưng cần tránh overhead, cần logic hành vi tuần tự đơn giản hơn, hoặc cần làm rõ lựa chọn ở một ngữ cảnh cụ thể.

**Không nên dùng `sequential()` để “sửa” callback có side effect sai hợp đồng.** Một pipeline tuần tự vẫn có thể sai nếu nó sửa nguồn đang được duyệt, dùng phép toán không đúng hoặc phụ thuộc vào state không hợp lệ. Mode tuần tự chỉ thay đổi cơ chế thực thi, không bảo đảm mọi callback là an toàn và đúng.

### Lựa chọn cuối cùng quyết định mode

```java
Stream<Integer> a = numbers.stream().parallel().sequential();
Stream<Integer> b = numbers.parallelStream().sequential().parallel();

// a.isParallel() -> false
// b.isParallel() -> true
```

Hai dòng trên tạo hai pipeline mới. Dù code đọc từ trái sang phải, các lời gọi thay đổi mode **không chia pipeline thành các giai đoạn thực thi độc lập**.

Nếu thật sự cần “tính pha 1 tuần tự, lưu kết quả, sau đó pha 2 song song”, hãy **materialize kết quả pha 1** (ví dụ bằng `toList()`) rồi tạo **một Stream mới** từ kết quả đó:

```java
List<Integer> phaseOne = numbers.stream()
        .map(n -> n * 2)
        .toList();

List<Integer> phaseTwo = phaseOne.parallelStream()
        .map(n -> n + 1)
        .toList();
```

Đây là mảnh mã với `numbers` là Collection số. Chỉ lúc này mới có ranh giới thật giữa hai terminal/pipeline, và ứng dụng sẽ chịu chi phí lưu trữ kết quả trung gian. Không ép chia pha khi không có lý do.

## 5. Chương trình Java 17: so sánh ba API và mode cuối cùng

Lưu thành tệp **`ParallelModeSwitchDemo.java`**:

```java
import java.util.List;
import java.util.stream.Stream;

public class ParallelModeSwitchDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

        Stream<Integer> fromStream = numbers.stream();
        Stream<Integer> fromParallel = numbers.parallelStream();
        Stream<Integer> switchedToSequential =
                numbers.stream().parallel().sequential();
        Stream<Integer> switchedBackToParallel =
                numbers.parallelStream().sequential().parallel();

        System.out.println("streamParallel=" + fromStream.isParallel());
        System.out.println("parallelStreamParallel=" + fromParallel.isParallel());
        System.out.println("switchedSequential="
                + switchedToSequential.isParallel());
        System.out.println("switchedParallel="
                + switchedBackToParallel.isParallel());

        System.out.println("streamResult=" + fromStream
                .map(n -> n * n).toList());
        System.out.println("parallelResult=" + fromParallel
                .map(n -> n * n).toList());
        System.out.println("sequentialAgain=" + switchedToSequential
                .map(n -> n + 1).toList());
        System.out.println("parallelAgain=" + switchedBackToParallel
                .map(n -> n + 1).toList());
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac -encoding UTF-8 ParallelModeSwitchDemo.java
java ParallelModeSwitchDemo
```

**Stdout chính xác:**

```text
streamParallel=false
parallelStreamParallel=true
switchedSequential=false
switchedParallel=true
streamResult=[1, 4, 9, 16, 25, 36]
parallelResult=[1, 4, 9, 16, 25, 36]
sequentialAgain=[2, 3, 4, 5, 6, 7]
parallelAgain=[2, 3, 4, 5, 6, 7]
```

Vì đầu vào là một List có encounter order, `toList()` giữ thứ tự kết quả ở cả hai mode. Cờ `isParallel()` thể hiện mode đã chọn, không phải một phép đo throughput hoặc chứng minh số lượng thread.

Mỗi Stream ở ví dụ được dùng **đúng một terminal operation** rồi thôi. Không được gọi lại `toList()`, `count()` hoặc `sum()` trên một Stream đã tiêu thụ. Muốn chạy lại, tạo Stream mới từ nguồn.

## 6. Encounter order khác với thứ tự thực thi

**Encounter order** là thứ tự phần tử do source và pipeline xác định. Với `List.of("A","B","C","D")`, encounter order là A, B, C, D. **Execution order** là thứ tự các thao tác thực tế diễn ra khi framework đánh giá pipeline.

Trong parallel stream:
- `map`, `filter` hoặc các lambda có thể được thực thi trên các phần tử theo một thứ tự khác nhau.
- Các worker có thể hoàn tất công việc theo các thời điểm khác nhau.
- Một số terminal operations vẫn **phải bảo toàn encounter order** trong kết quả, nếu Stream có order và terminal yêu cầu.
- `forEach` **không bảo đảm** thứ tự action; `forEachOrdered` bảo đảm theo encounter order, nhưng không ép mọi bước upstream phải chạy tuần tự.

| API | Trên ordered parallel Stream | Ý nghĩa thực tế |
| --- | --- | --- |
| `toList()` | Giữ encounter order | Kết quả ổn định về thứ tự, nội bộ có thể song song |
| `collect(Collectors.toList())` | Collector phù hợp bảo toàn encounter order | Không nên suy luận loại List cụ thể |
| `forEach(action)` | Không bảo đảm thứ tự action | Không dùng để ghi log có thứ tự bắt buộc |
| `forEachOrdered(action)` | Action chạy theo encounter order | Có thể tốn chi phí điều phối |
| `findFirst()` | Chọn phần tử đầu tiên theo encounter order khi có | Ràng buộc order có thể tăng chi phí |
| `findAny()` | Có thể chọn bất kỳ phần tử phù hợp | Không dựa vào việc luôn trả phần tử đầu |
| `unordered()` | Tháo bỏ ràng buộc encounter order | Không có nghĩa xáo trộn ngẫu nhiên |

**Thứ tự trong List kết quả và thứ tự side effect không phải một.** Ví dụ, `parallelStream().map(...).toList()` có thể cho danh sách đúng thứ tự dù các lời gọi `map` hoàn thành ngoài thứ tự. Đừng dùng danh sách đầu ra để suy luận thứ tự callback.

## 7. Chương trình Java 17: output có thứ tự dù xử lý parallel

Tạo tệp **`ParallelOrderDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class ParallelOrderDemo {
    public static void main(String[] args) {
        List<String> words = List.of("A", "B", "C", "D");

        List<String> result = words.parallelStream()
                .map(word -> word.toLowerCase(Locale.ROOT))
                .toList();

        System.out.println("result=" + result);

        System.out.print("orderedAction=");
        words.parallelStream().forEachOrdered(System.out::print);
        System.out.println();

        System.out.println("first=" + words.parallelStream()
                .findFirst()
                .orElse("-"));

        boolean anyBelongs = words.parallelStream()
                .findAny()
                .filter(words::contains)
                .isPresent();
        System.out.println("anyBelongs=" + anyBelongs);
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 ParallelOrderDemo.java
java ParallelOrderDemo
```

**Stdout chính xác:**

```text
result=[a, b, c, d]
orderedAction=ABCD
first=A
anyBelongs=true
```

`findAny()` có thể trả A, B, C hoặc D. Chương trình **không in giá trị được chọn**, mà chỉ kiểm tra nó có thuộc danh sách hay không; nhờ vậy stdout xác định. `forEachOrdered` in ABCD vì nguồn List có thứ tự.

Nếu thay `forEachOrdered` bằng `forEach` trên parallel Stream, ví dụ không thể cam kết in ABCD. Có thể tình cờ đúng thứ tự một vài lần chạy, nhưng đó không phải hợp đồng của API.

Với `findFirst` trên một Stream **unordered**, không nên suy luận phần tử đầu tiên cố định, bởi nguồn/pipeline không mang yêu cầu về thứ tự gặp.

## 8. Laziness: đổi mode không chạy intermediate operations

Các intermediate operations như `map` và `filter` thường **lazy**. Ví dụ:

```java
Stream<Integer> pipeline = numbers.stream()
        .filter(n -> n % 2 == 0)
        .parallel()
        .map(n -> n * 10);

// Đến đây chưa có terminal operation.
List<Integer> result = pipeline.toList();
```

Đoạn là mảnh mã cần `List`, `Stream` và một collection `numbers` có sẵn. Việc gọi `parallel()` không làm chạy ngay `filter` hoặc `map`; `toList()` mới yêu cầu kết quả.

Tính lazy kéo theo:
- `Stream` thường chỉ tiêu thụ **một lần**. Không dùng lại pipeline đã có terminal operation.
- Short-circuit operations có thể không duyệt hết phần tử nếu điều kiện kết thúc đã được thỏa.
- Trong parallel, có thể có công việc đang chạy ở phần khác khi một terminal quyết định dừng.
- Không đặt **side effect bắt buộc** trong `peek` hoặc `map`, rồi kỳ vọng mỗi nguồn chắc chắn tạo đúng một log. JDK có thể tối ưu hóa một số bước nếu không ảnh hưởng kết quả terminal theo hợp đồng Stream.

Với `count()` trên nguồn có kích thước đã biết và các bước không thay đổi số lượng, một triển khai có thể biết kết quả mà không cần gọi từng mapper; bởi vậy `peek(System.out::println)` không nên được dùng làm công cụ đảm bảo “mỗi phần tử đã chạy qua”.

## 9. reduce đúng khi xử lý song song

`reduce` kết hợp các phần tử theo một phép toán. Với parallel, framework có thể tính kết quả cho từng phần rồi gộp, nên toán tử phải có tính **associative** và identity đúng nếu dùng overload có identity.

- **Associativity:** `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)`.
- **Identity:** `e ⊕ a = a` và `a ⊕ e = a`.

Ví dụ đúng với dữ liệu nhỏ:

```java
int total = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .reduce(0, Integer::sum); // 55
```

Phép cộng có identity 0, phù hợp cho phép gộp song song trong ví dụ. Ngược lại:

```java
int unreliable = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .reduce(0, (a, b) -> a - b);
```

Đoạn thứ hai **biên dịch được nhưng không có ngữ nghĩa rút gọn mong muốn**: phép trừ không kết hợp, nên kết quả có thể khác so với thứ tự giảm tuần tự. Không in stdout cố định cho đoạn đó.

### Một bẫy khác: accumulator mutable trong reduce

Mẫu sau không nên dùng:

```java
// CỐ Ý SAI VỀ THIẾT KẾ, đặc biệt nguy hiểm với parallel:
List<Integer> values = java.util.stream.IntStream.rangeClosed(1, 10)
        .boxed()
        .parallel()
        .reduce(
            new java.util.ArrayList<Integer>(),
            (list, number) -> {
                list.add(number);
                return list;
            },
            (left, right) -> {
                left.addAll(right);
                return left;
            }
        );
```

Đây là mảnh minh họa **không an toàn**: mutable identity có thể bị nhiều nhánh giảm sử dụng và sửa; điều đó vi phạm hợp đồng reduction và có thể làm sai kết quả. Dùng `collect` để tạo container độc lập cho các phần việc.

Cũng lưu ý tổng `int`/`long` có thể tràn với dữ liệu lớn, `double` có sai số làm tròn theo cách nhóm phép cộng khác nhau. Parallel mode không giải quyết các giới hạn số học đó.

## 10. collect đúng: để framework quản lý trạng thái

Nếu mục tiêu là gom các phần tử vào List, Set hoặc Map, hãy dùng collector phù hợp thay vì sửa một collection dùng chung từ `forEach`.

```java
List<Integer> values = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .boxed()
        .toList();
```

Trên Java 17, `Stream.toList()` trả List **không thể sửa qua API** và giữ encounter order cho nguồn có thứ tự. Nếu cần List mutable, dùng:

```java
List<Integer> mutable = java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .boxed()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));
```

Đây là hai mảnh mã độc lập, có import `List`. `Collectors.toCollection(ArrayList::new)` chọn kiểu container kết quả. Với parallel Stream, framework có thể tạo nhiều container rồi gộp; nó **không đòi** bạn tự dùng `synchronizedList` để cập nhật chung một List ngoài pipeline.

Ví dụ nhóm theo thuộc tính:

```java
Map<Integer, Long> counts = words.parallelStream()
        .collect(java.util.stream.Collectors.groupingBy(
                String::length,
                java.util.TreeMap::new,
                java.util.stream.Collectors.counting()
        ));
```

Đây là mảnh mã với `words` kiểu `Collection<String>` và import `java.util.Map;`. `TreeMap` giúp khi in Map có thứ tự khóa tăng dần, thay vì phụ thuộc thứ tự duyệt HashMap.

**Collector không nhất thiết phải có đặc tính `CONCURRENT` để dùng trong parallel Stream.** Collector bình thường có thể được framework áp dụng lên các state độc lập rồi gộp. Chỉ những collector thật sự hỗ trợ cập nhật đồng thời trên cùng một state và phù hợp các điều kiện liên quan mới nên công bố `CONCURRENT`.

## 11. Chương trình Java 17: reduce và collect an toàn trên parallel

Lưu thành **`ParallelAggregationDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelAggregationDemo {
    public static void main(String[] args) {
        int sequentialSum = IntStream.rangeClosed(1, 10).sum();
        int parallelSum = IntStream.rangeClosed(1, 10)
                .parallel()
                .reduce(0, Integer::sum);

        List<Integer> evens = IntStream.rangeClosed(1, 10)
                .parallel()
                .filter(n -> n % 2 == 0)
                .boxed()
                .toList();

        List<String> words = List.of("a", "bb", "ccc", "dd");
        Map<Integer, Long> lengthCounts = words.parallelStream()
                .collect(Collectors.groupingBy(
                        String::length,
                        TreeMap::new,
                        Collectors.counting()
                ));

        String joined = words.parallelStream()
                .collect(Collectors.joining("-"));

        System.out.println("sequentialSum=" + sequentialSum);
        System.out.println("parallelSum=" + parallelSum);
        System.out.println("evens=" + evens);
        System.out.println("lengthCounts=" + lengthCounts);
        System.out.println("joined=" + joined);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ParallelAggregationDemo.java
java ParallelAggregationDemo
```

**Stdout chính xác:**

```text
sequentialSum=55
parallelSum=55
evens=[2, 4, 6, 8, 10]
lengthCounts={1=1, 2=2, 3=1}
joined=a-bb-ccc-dd
```

Trong ví dụ:
- `Integer::sum` với identity 0 cho kết quả nhất quán với tổng dãy 1..10.
- `evens` giữ encounter order của nguồn `IntStream.rangeClosed` vì `filter` và `toList` có ngữ nghĩa bảo toàn thứ tự trên nguồn ordered.
- `groupingBy` với `TreeMap::new` trả Map sắp khóa theo độ dài chuỗi.
- `joining("-")` bảo toàn encounter order với ordered Stream, nên không phụ thuộc thứ tự các worker hoàn thành.

Không có phép cập nhật một List hay Map shared từ bên ngoài pipeline.

## 12. Side effect và shared mutable state

Một trong những lỗi nguy hiểm nhất khi đổi từ `stream()` sang `parallelStream()` là giữ lại callback vốn sửa biến chung.

**Ví dụ sai cần tránh:**

```java
List<Integer> output = new java.util.ArrayList<>();
java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(output::add); // không an toàn
```

Đoạn trên là minh họa **anti-pattern**, không phải chương trình được khuyến nghị. `ArrayList` không hỗ trợ nhiều thread đồng thời cập nhật mà không đồng bộ phù hợp. Có thể mất phần tử, xảy ra data race, nhận thứ tự bất kỳ hoặc lỗi cấu trúc.

Cách đúng khi chỉ cần dữ liệu:

```java
List<Integer> output = java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .boxed()
        .toList();
```

Hai mảnh mã là **các phương án thay thế**, không phải hai khai báo `output` trong cùng phạm vi.

Nếu cần **side effect** như gửi email, ghi file hoặc cập nhật cơ sở dữ liệu, việc đổi sang parallel có thể gây sai thứ tự, tranh chấp tài nguyên hoặc khó xử lý lỗi. Cần quyết định rõ kiến trúc concurrency, transaction và retry — không mặc định `parallelStream().forEach` mang sẵn những bảo đảm đó.

### Stateless và non-interfering

Các hàm truyền vào `map`, `filter`, `reduce` nên ưu tiên:
- **Stateless:** kết quả không phụ thuộc vào trạng thái mutable bị thay đổi bởi những lần gọi khác.
- **Non-interfering:** không sửa nguồn đang được Stream duyệt trái hợp đồng.
- **Deterministic khi nghiệp vụ cần:** cùng đầu vào tạo cùng kết quả; không phụ thuộc thread được giao hoặc thời điểm chạy.

Tài nguyên riêng mà callback chỉ đọc có thể phù hợp nếu thread-safe khi dùng song song. Nhưng đừng cho rằng một client HTTP, repository hoặc formatter mutable bất kỳ đều an toàn cho nhiều thread mà chưa kiểm tra hợp đồng của thư viện.

## 13. Chương trình Java 17: phân vùng song song không có shared List

Tạo file **`ParallelPartitionModeDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelPartitionModeDemo {
    public static void main(String[] args) {
        List<Integer> numbers = IntStream.rangeClosed(1, 8)
                .boxed()
                .toList();

        Map<Boolean, List<Integer>> partition = numbers.parallelStream()
                .collect(Collectors.partitioningBy(n -> n > 4));

        long evenCount = numbers.stream()
                .parallel()
                .filter(n -> n % 2 == 0)
                .count();

        List<Integer> changed = numbers.parallelStream()
                .sequential()
                .map(n -> n * 2)
                .toList();

        System.out.println("higher=" + partition.get(true));
        System.out.println("lower=" + partition.get(false));
        System.out.println("evenCount=" + evenCount);
        System.out.println("sequentialResult=" + changed);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ParallelPartitionModeDemo.java
java ParallelPartitionModeDemo
```

**Stdout chính xác:**

```text
higher=[5, 6, 7, 8]
lower=[1, 2, 3, 4]
evenCount=4
sequentialResult=[2, 4, 6, 8, 10, 12, 14, 16]
```

`partitioningBy` phân chia theo điều kiện `n > 4`, hai nhánh Boolean luôn tồn tại; chương trình truy cập từng nhánh bằng `get(true)`, `get(false)` thay vì in trực tiếp Map với thứ tự key không được bảo đảm. `sequential()` đặt lại mode tuần tự cho pipeline cuối, dù nguồn ban đầu được tạo bằng `parallelStream()`.

Ví dụ không dùng dữ liệu quá nhỏ để đưa ra **kết luận hiệu năng**: nó chỉ minh họa ngữ nghĩa và cách viết không chia sẻ một `ArrayList` mutable.

## 14. Chọn sequential hay parallel theo điều kiện thực tế

Không có quy tắc “parallel luôn nhanh gấp số core”. Parallel có overhead chia công việc, lập lịch, đồng bộ, phối hợp, kết hợp kết quả và có thể tăng bộ nhớ trung gian.

| Tình huống | Nghiêng về sequential | Có thể cân nhắc parallel |
| --- | --- | --- |
| Dữ liệu ít, mỗi phép toán rất nhẹ | Có | Ít lợi ích |
| Dữ liệu lớn, nguồn dễ chia | Tùy kiểm thử | Có cơ hội |
| Tác vụ CPU-bound độc lập | Tùy kích thước | Hợp lý nếu đủ nặng |
| Đọc/ghi I/O có blocking | Thường cần thiết kế concurrency riêng | Không tự giải quyết blocking |
| Yêu cầu thứ tự chặt và stateful operations | Dễ đơn giản hơn | Có thể tốn chi phí |
| Shared mutable state hoặc side effect | Đòi sửa thiết kế trước | Không nên chuyển trực tiếp |
| Phép reduce associative, collector đúng | Đúng | Có thể đúng và tận dụng chia/gộp |
| CPU/common pool đang bận | Dễ tránh cạnh tranh | Có thể bị tranh chấp |

### Pool và thread

Triển khai Stream parallel trong JDK thường dựa vào cơ chế **Fork/Join**, hay dùng common pool trong các ngữ cảnh phổ biến. Đây không phải lời hứa “mỗi phần tử là một task” hoặc “mỗi pipeline có một pool riêng”. Số worker thread và cách chúng được chọn không phải chi tiết mà logic nghiệp vụ được phép phụ thuộc.

Không nên in `Thread.currentThread().getName()` rồi kết luận rằng đó là hợp đồng của Stream. Nếu ứng dụng cần kiểm soát worker pool, cancellation, timeout hoặc backpressure theo tác vụ, cân nhắc một abstraction concurrency được thiết kế riêng như `ExecutorService` hoặc `CompletableFuture` (và chính sách quản lý tài nguyên phù hợp).

### Đo hiệu năng đúng

Dùng **JMH** hoặc phương pháp benchmark nghiêm túc:
1. Đảm bảo code tuần tự và song song **tương đương về kết quả** trên cùng dữ liệu.
2. Test kích thước nguồn và độ nặng xử lý thực tế.
3. Làm nóng JIT, đo nhiều lần trong môi trường ổn định.
4. Quan sát CPU, garbage collection, allocation và contention.
5. Chỉ giữ parallel khi benchmark có lợi và logic vẫn dễ bảo trì.

Không lấy một lần `System.nanoTime()` làm bằng chứng tổng quát. Bài này cố ý dùng stdout giá trị tính toán thay vì “số mili-giây” vì thời gian thay đổi theo máy, JDK và tải hệ thống.

## 15. Những hiểu lầm phổ biến

1. **“parallelStream() là phương thức của Stream.”** Sai; nó thường được gọi trên Collection. Đã có Stream thì dùng `parallel()`.
2. **“parallel() chạy ngay các phép map/filter.”** Sai; intermediate operations vẫn lazy.
3. **“parallel() tạo một thread cho mỗi phần tử.”** Sai; cách chia và lập lịch do framework quyết định.
4. **“parallel().sequential() tạo hai pha chạy khác mode.”** Sai; mode cuối chi phối pipeline khi terminal thực thi.
5. **“isParallel() chứng minh đã chạy nhiều thread.”** Sai; chỉ đọc cờ mode.
6. **“parallel luôn nhanh hơn.”** Sai; overhead và contention có thể lớn hơn phần lợi.
7. **“parallelStream().toList() luôn đảo thứ tự.”** Sai với ordered source và terminal giữ order.
8. **“parallel forEach luôn theo encounter order.”** Sai; dùng `forEachOrdered` nếu cần action theo thứ tự.
9. **“forEachOrdered khiến mọi upstream tuần tự.”** Sai; chỉ đảm bảo thứ tự action theo encounter order.
10. **“findAny luôn là phần tử đầu.”** Sai; được phép trả phần tử bất kỳ.
11. **“Một Stream có thể gọi nhiều terminal.”** Sai; hãy tạo Stream mới khi cần chạy lại.
12. **“Dùng mutable identity với reduce song song là ổn.”** Sai; có thể phá hợp đồng và gây race.
13. **“Dùng external ArrayList trong parallel forEach để gom dữ liệu.”** Nguy hiểm vì concurrent updates.
14. **“Bất kỳ toán tử reduce nào cũng song song được.”** Sai; cần identity và associativity.
15. **“Collector phải CONCURRENT mới dùng được với parallel.”** Sai; collector thường có thể dùng nhiều accumulator riêng và kết hợp.
16. **“sequential chắc chắn sửa được bug side effect.”** Sai; mode không thay thế thiết kế logic đúng.
17. **“unordered() có nghĩa xáo phần tử ngẫu nhiên.”** Sai; chỉ bỏ ràng buộc encounter order.
18. **“Đổi sang parallel là async không chặn caller.”** Sai với những terminal operation thông thường trả kết quả sau khi hoàn tất.

## 16. Bài tập và đáp án

**Câu 1.** Có `List<Integer> numbers`. Hai cách tạo pipeline parallel là gì?

**Đáp án:** `numbers.parallelStream()` hoặc `numbers.stream().parallel()`.

**Câu 2.** `numbers.parallelStream().sequential().isParallel()` là gì?

**Đáp án:** `false`. `sequential()` là lựa chọn mode cuối.

**Câu 3.** `numbers.stream().parallel().sequential().parallel().isParallel()` là gì?

**Đáp án:** `true`. Mode được cấu hình cuối cùng là parallel; không tạo ba pha thực thi riêng.

**Câu 4.** Vì sao `parallelStream().map(f).toList()` vẫn có thể giữ thứ tự List nguồn?

Vì encounter order của nguồn ordered có thể được bảo toàn theo hợp đồng của `toList()`, dù các lời gọi mapper thực thi song song.

**Câu 5.** Nên dùng `forEach` hay `forEachOrdered` để in A, B, C đúng thứ tự từ một ordered Stream?

**Đáp án:** `forEachOrdered`. `forEach` trên parallel không bảo đảm thứ tự action.

**Câu 6.** `reduce(0, (a,b) -> a-b)` có đảm bảo kết quả tương đương tuần tự khi parallel không?

**Không.** Phép trừ không associative, nên cách chia và nhóm có thể làm thay đổi kết quả.

**Câu 7.** Vì sao không nên viết `parallelStream().forEach(sharedList::add)` với sharedList là ArrayList?

Vì ArrayList không an toàn cho nhiều cập nhật đồng thời; có thể mất phần tử hoặc sai state. Dùng `toList()` hoặc collector phù hợp.

**Câu 8.** Khi nào nên dùng `sequential()` trên một Stream nhận từ nơi khác?

Khi bạn cần yêu cầu pipeline cuối được thực thi tuần tự để giảm overhead hoặc giữ cách tính đơn giản hơn, nhưng vẫn phải đảm bảo pipeline có logic đúng.

**Câu 9.** Nếu cần pha 1 tuần tự và pha 2 song song thật sự, chỉ gọi `stream.map(f).parallel().map(g)` có đủ không?

**Không.** Hãy materialize kết quả pha 1 bằng terminal operation (ví dụ `toList()`), sau đó tạo Stream mới parallel cho pha 2. Đó là hai pipeline thực sự.

**Câu 10.** Làm thế nào biết parallel đáng dùng trong sản phẩm?

Kiểm tra tính đúng đắn trên cả hai mode và benchmark trên workload thật; không suy luận từ tên phương thức hoặc số core.

**Ghi nhớ:** `parallelStream()` **khởi tạo** một Stream song song từ Collection; `parallel()` **yêu cầu chuyển** Stream sang song song; `sequential()` **yêu cầu chuyển** Stream về tuần tự. Mode cuối áp dụng cho **toàn pipeline khi terminal chạy**. Tốc độ và thứ tự thực thi không được bảo đảm chỉ vì chọn parallel; hãy ưu tiên hàm stateless, phép gộp đúng và các terminal giữ order khi nghiệp vụ cần.
