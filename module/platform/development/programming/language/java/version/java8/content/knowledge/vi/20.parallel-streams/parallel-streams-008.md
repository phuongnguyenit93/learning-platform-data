# Race condition do sửa biến, collection bên ngoài khi dùng Parallel Stream

**Chủ đề:** Stream song song (parallel stream) trong Java. Bài học tập trung vào lỗi xuất hiện khi các lambda trong pipeline đọc/ghi **biến có thể thay đổi** hoặc **collection nằm bên ngoài stream** và nhiều tác vụ chạy đồng thời. Các khuyến nghị dựa trên Stream API, Java Memory Model và các thư viện concurrency vẫn được sử dụng trên JDK hiện đại. Ví dụ hoàn chỉnh sử dụng **Java 17+**.

## 1. Vấn đề: Stream song song và trạng thái dùng chung

Trong Java, `parallelStream()` hoặc `stream().parallel()` cho phép Stream framework phân chia công việc cho nhiều tác vụ, có thể thực thi trên nhiều thread. Framework được phép quyết định cách phân chia, số thread và thời điểm gọi lambda; **không có bảo đảm mỗi phần tử chạy trên một thread riêng** hoặc thứ tự kết thúc giống thứ tự nguồn.

Một **race condition** xảy ra khi kết quả phụ thuộc vào lịch xen kẽ của các thao tác đồng thời mà chương trình chưa phối hợp đúng. Một **data race** là trường hợp đặc biệt: có các truy cập xung đột tới cùng trạng thái, ít nhất một truy cập là ghi và không có quan hệ đồng bộ (*happens-before*) cần thiết. Hậu quả có thể là **mất cập nhật**, dữ liệu thiếu/trùng, collection ở trạng thái không nhất quán, ngoại lệ ngẫu nhiên hoặc kết quả khác nhau giữa các lần chạy.

Ví dụ dạng sai dễ thấy:

```java
int[] counter = {0};
List<Integer> results = new ArrayList<>();

IntStream.range(0, 100_000)
        .parallel()
        .forEach(n -> {
            counter[0]++;  // Ghi vào cùng một ô mảng từ nhiều tác vụ
            results.add(n); // Ghi vào cùng một ArrayList không đồng bộ
        });
```

**Đây là đoạn minh họa lỗi, không phải chương trình được khuyến nghị chạy hay có stdout cố định.** Nếu đặt trong một phương thức, cần import `java.util.List`, `java.util.ArrayList` và `java.util.stream.IntStream`. Nó có thể cho `counter[0]` nhỏ hơn 100.000, `results.size()` sai, mất phần tử hoặc phát sinh ngoại lệ khi `ArrayList` mở rộng nội bộ. Không được suy đoán nó *luôn* lỗi trong mọi lần chạy: race condition có thể bị che giấu bởi lịch thực thi.

**Tại sao `counter[0]++` sai?** Phép tăng gồm đọc, tính toán rồi ghi; không phải một thao tác nguyên tử. Hai thread cùng đọc 10, cùng cộng thành 11 rồi cùng ghi 11 → mất một lần tăng. Đặt biến trong `int[]` chỉ để lambda có thể tham chiếu tới biến final/effectively-final, **không** làm giá trị phần tử trong mảng an toàn cho truy cập đồng thời.

## 2. Captured variable và quy tắc effectively final

Java lambda có thể tham chiếu local variable được khai báo `final` hoặc **effectively final** (không gán lại sau khởi tạo):

```java
int factor = 2;
int total = IntStream.rangeClosed(1, 3)
        .parallel()
        .map(n -> n * factor)
        .sum(); // 12
```

Đây là **đoạn mã trong phương thức**, cần import `java.util.stream.IntStream`. `factor` không bị thay đổi; lambda chỉ đọc giá trị ổn định nên an toàn về mặt captured state.

Ngược lại, mã sau **không biên dịch**:

```java
int total = 0;
IntStream.rangeClosed(1, 3).forEach(n -> total += n);
```

Lý do: lambda không được gán lại local variable `total` đã bị capture. Chuyển sang `int[]` hoặc `AtomicInteger` chỉ để vượt qua lỗi biên dịch có thể che dấu thiết kế phụ thuộc trạng thái dùng chung. Khi mục tiêu là tính tổng, viết `IntStream.rangeClosed(1, 3).sum()`.

Cũng phải phân biệt **tham chiếu effectively final** với **đối tượng bất biến**:

```java
List<Integer> shared = new ArrayList<>(); // tham chiếu không gán lại
IntStream.range(0, 10).parallel().forEach(shared::add);
```

Đây vẫn là đoạn mã sai: dù biến `shared` effectively final, **nội dung ArrayList vẫn có thể bị nhiều thread sửa đồng thời**. Tương tự cho `StringBuilder`, `HashMap`, mảng, các trường mutable của object và các bộ đếm không đồng bộ.

## 3. Ba lớp an toàn phải tách riêng

| Câu hỏi | Rủi ro khi trả lời sai | Ví dụ |
| --- | --- | --- |
| Lambda có cập nhật trạng thái bên ngoài không? | Data race, mất cập nhật, tác dụng phụ khó dự đoán | `count[0]++`, `builder.append(...)` |
| Có sửa **nguồn** đang được stream duyệt không? | Vi phạm non-interference, kết quả không xác định/ngoại lệ | `list.parallelStream().forEach(list::remove)` |
| Có yêu cầu **thứ tự kết quả** không? | `parallel().forEach(...)` không tôn trọng encounter order | `sharedList.add(n)`, ghi file theo thứ tự |

Một collection thread-safe chỉ giải quyết **một phần** của bài toán. `Collections.synchronizedList(...)` đồng bộ thao tác `add`; `ConcurrentLinkedQueue` hỗ trợ thêm phần tử đồng thời. Nhưng thứ tự chúng nhận phần tử vẫn theo thời điểm các tác vụ chạy, **không mặc nhiên là thứ tự phần tử của stream**, và việc sửa nguồn đang duyệt vẫn cần xem xét hợp đồng non-interference.

## 4. Nguyên tắc chuẩn của Stream API: non-interfering và stateless

Các biểu thức hành vi cung cấp cho `filter`, `map`, `flatMap`, `reduce` và phần lớn phương thức Stream nên:

- **Non-interfering:** không sửa nguồn dữ liệu của stream trong lúc pipeline đang được thực thi, trừ những trường hợp nguồn và API có cơ chế concurrent modification được tài liệu hóa rõ ràng. Điều này áp dụng cả sequential stream; parallel làm rủi ro xuất hiện thường xuyên hơn.
- **Stateless:** không dựa vào trạng thái mutable bị thay đổi trong khi pipeline chạy (đặc biệt trạng thái dùng chung giữa nhiều phần tử). Ví dụ `filter(n -> n > 10)` và `map(n -> n * n)` là stateless; `map(n -> sharedCounter++)` là stateful và có race.
- **Không giả định lịch gọi lambda:** framework có thể thực thi ở các thread khác nhau, tối ưu hoặc bỏ qua những phép biến đổi không cần thiết trong một số pipeline. Side effect trong `peek`/`map` không phải nền tảng tin cậy cho đếm số lần xử lý hoặc logic nghiệp vụ.

`forEach` là terminal operation chủ động thực hiện side effect, hữu ích cho logging/I/O hoặc cập nhật hệ thống đã được thiết kế thread-safe. Tuy nhiên **side effect phải tự bảo đảm đồng bộ khi truy cập trạng thái chia sẻ**, và trong parallel pipeline, `forEach` không cam kết thứ tự.

Khi mục tiêu là **tạo giá trị mới từ dữ liệu**, hãy biểu diễn qua biến đổi và reduction/collector thay vì sửa object ngoại vi.

## 5. Cách sửa số 1: dùng reduction/terminal operation thay bộ đếm dùng chung

### 5.1. Thay `counter++` bằng `count()` và `sum()`

Một phép cộng như:

```java
long[] total = {0};
LongStream.rangeClosed(1, 10_000)
        .parallel()
        .forEach(n -> total[0] += n); // Sai: read-modify-write trên long[] dùng chung
```

nên đổi thành:

```java
long total = LongStream.rangeClosed(1, 10_000)
        .parallel()
        .sum(); // 50_005_000
```

Đây là các đoạn mã đặt bên trong một phương thức và cần import `java.util.stream.LongStream`. Phần sai không có stdout cố định; phần đúng trả giá trị ổn định với dữ liệu trên.

**Vì sao đúng?** Stream framework thực hiện phép reduction, có thể tính các kết quả trung gian riêng rồi gộp bằng phép cộng. Không có một `long[]` do bạn tự tạo bị nhiều tác vụ cập nhật trực tiếp. Với miền số rất lớn vẫn phải kiểm tra `long` overflow; phép `sum()` không biến kết quả thành số nguyên độ chính xác vô hạn.

### 5.2. Ví dụ Java 17+ chạy được

Tạo file **`ParallelStreamSafeDemo.java`**:

```java
import java.util.List;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class ParallelStreamSafeDemo {
    public static void main(String[] args) {
        long sum = LongStream.rangeClosed(1, 10_000)
                .parallel()
                .sum();

        long evenCount = IntStream.range(0, 1_000)
                .parallel()
                .filter(n -> n % 2 == 0)
                .count();

        List<Integer> squares = IntStream.rangeClosed(1, 5)
                .parallel()
                .map(n -> n * n)
                .boxed()
                .toList();

        List<String> normalized = List.of(" A ", "B", " ", "C")
                .parallelStream()
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .toList();

        System.out.println("Sum: " + sum);
        System.out.println("Even: " + evenCount);
        System.out.println("Squares: " + squares);
        System.out.println("Normalized: " + normalized);
    }
}
```

Chạy:

```bash
javac --release 17 ParallelStreamSafeDemo.java
java ParallelStreamSafeDemo
```

**Stdout chính xác:**

```text
Sum: 50005000
Even: 500
Squares: [1, 4, 9, 16, 25]
Normalized: [A, B, C]
```

- `sum()` và `count()` là reduction/terminal operations theo hợp đồng Stream; không cần side effect vào biến bên ngoài.
- `IntStream.rangeClosed(1, 5)` và `List.of(...).parallelStream()` là các nguồn **có encounter order**; `toList()` giữ encounter order của kết quả khi nguồn có thứ tự, kể cả khi các phần tử được tính toán song song.
- `Stream.toList()` có từ **Java 16**, trả list **không sửa được**. Nếu phải tương thích với phiên bản cũ hơn, có thể `collect(Collectors.toList())`; nếu cần một `ArrayList` mutable cụ thể thì `collect(Collectors.toCollection(ArrayList::new))`.
- Việc đặt `parallel()` chỉ cho phép xử lý song song, không biến `map` và `filter` thành side effect an toàn khi chúng truy cập dữ liệu mutable dùng chung.

## 6. Cách sửa số 2: gom vào List bằng `collect()`, không bằng `forEach(shared::add)`

**Sai (không nên chạy như ví dụ kết quả xác định):**

```java
List<Integer> output = new ArrayList<>();
IntStream.range(0, 10_000)
        .parallel()
        .forEach(output::add);
```

Lỗi gồm hai mặt: `ArrayList` không an toàn cho ghi đồng thời, và `forEach` không bảo đảm thứ tự. Thay `ArrayList` bằng `Collections.synchronizedList(new ArrayList<>())` có thể giúp thao tác `add` không giẫm lên nhau, **nhưng vẫn không bảo đảm output theo 0, 1, 2,...**. Dùng queue concurrent cũng không tự giữ encounter order.

**Đúng:**

```java
List<Integer> output = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
```

Đây là đoạn mã trong một phương thức, cần import `java.util.List` và `java.util.stream.IntStream`; `output` chứa các giá trị theo thứ tự 0 đến 9.999. Stream tự quản lý việc gom phần tử; danh sách trả về `toList()` không cho sửa. Nếu cần mutable list:

```java
List<Integer> output = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));
```

Đoạn này cần thêm `java.util.stream.Collectors` và `java.util.ArrayList`. **Không cần làm `ArrayList` thành synchronized list** trong trường hợp này: collector sử dụng các container trung gian riêng theo quy tắc mutable reduction rồi kết hợp chúng; đó là lý do `collect(...)` hỗ trợ parallel an toàn với collector chuẩn, miễn không thêm shared mutable state vào accumulator/combiner.

### 6.1. `collect(supplier, accumulator, combiner)` cũng giải quyết được

```java
List<Integer> output = IntStream.range(0, 10)
        .boxed()
        .parallel()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );
```

Đây là một **đoạn mã trong phương thức** với các import `List`, `ArrayList` và `IntStream`. Nó là mutable reduction, có supplier tạo mỗi container mới và combiner nhập phần tử từ container thứ hai vào container thứ nhất. Với đầu vào có thứ tự ở đây, `output` là `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`.

**Không viết `reduce(new ArrayList<>(), (list, x) -> { list.add(x); return list; }, ...)`** để gom dữ liệu: `reduce` kỳ vọng phép reduction tuân thủ identity/associativity, còn sửa một identity mutable dùng chung có thể gây race và trộn kết quả khi chạy song song. Muốn mutable result container, dùng `collect`.

## 7. Cách sửa số 3: nhóm và đếm bằng Collector

Giả sử chương trình muốn đếm ngôn ngữ xuất hiện trong danh sách. Thay vì `parallelStream().forEach(...)` cập nhật một `HashMap` ngoài pipeline, dùng collector.

Tạo file **`ParallelGroupingDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

public class ParallelGroupingDemo {
    public static void main(String[] args) {
        List<String> words =
                List.of("java", "go", "java", "rust", "go");

        Map<String, Long> grouped = words.parallelStream()
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        Collectors.counting()
                ));

        ConcurrentMap<String, Long> concurrent = words.parallelStream()
                .collect(Collectors.groupingByConcurrent(
                        Function.identity(),
                        Collectors.counting()
                ));

        System.out.println("groupingBy: java=" + grouped.get("java")
                + ", go=" + grouped.get("go")
                + ", rust=" + grouped.get("rust"));

        System.out.println("groupingByConcurrent: java="
                + concurrent.get("java")
                + ", go=" + concurrent.get("go")
                + ", rust=" + concurrent.get("rust"));
    }
}
```

Chạy:

```bash
javac --release 17 ParallelGroupingDemo.java
java ParallelGroupingDemo
```

**Stdout chính xác:**

```text
groupingBy: java=2, go=2, rust=1
groupingByConcurrent: java=2, go=2, rust=1
```

Trong ví dụ, truy cập **theo key cụ thể** nên kết quả in xác định; không dùng `Map.toString()` để tuyên bố thứ tự iteration của `HashMap` hoặc `ConcurrentMap`.

So sánh:

| Collector | Bảo đảm liên quan đến song song | Thứ tự |
| --- | --- | --- |
| `groupingBy(classifier, downstream)` | Framework có thể tạo nhiều map tạm rồi dùng combiner; không yêu cầu map kết quả là concurrent | Với downstream có yêu cầu encounter order, framework phải tôn trọng ngữ nghĩa của collector, nhưng loại map/iteration order **không được cam kết** |
| `groupingByConcurrent(classifier, downstream)` | Collector concurrent, unordered, dùng `ConcurrentMap` để tích lũy | Không bảo đảm thứ tự phần tử trong các nhóm; chỉ dùng khi không cần thứ tự đó |
| `toConcurrentMap(...)` | Collector concurrent để tạo map, có chính sách xử lý key trùng khi cần | Không mặc nhiên cho kết quả duyệt key theo encounter order |

Điểm quan trọng: một collector concurrent **không bắt buộc** downstream list sau khi collect là thread-safe cho các thao tác tùy ý. Đừng chỉnh sửa các list kết quả từ nhiều thread mà không có thiết kế đồng bộ riêng. Với `groupingByConcurrent`, nếu cần giữ **thứ tự phần tử trong từng nhóm**, không được dựa vào tốc độ để bỏ qua yêu cầu thứ tự.

## 8. Khi thực sự cần side effect: AtomicInteger, LongAdder và concurrent collections

Có trường hợp cần cập nhật một **metric độc lập**, truyền tín hiệu, hoặc gọi một API yêu cầu side effect. Lúc đó phải chọn cơ chế đồng bộ phù hợp.

### 8.1. `AtomicInteger` / `AtomicLong`

`AtomicInteger.incrementAndGet()` và `AtomicLong.addAndGet(delta)` là thao tác cập nhật nguyên tử; chúng tránh kiểu mất cập nhật của `counter[0]++`. Tuy nhiên nguyên tử hóa **một biến** không làm các hành động khác (đọc map, cập nhật list, ghi file) trở thành một transaction.

Ví dụ **đoạn mã trong phương thức**, cần import `java.util.concurrent.atomic.AtomicInteger` và `java.util.stream.IntStream`:

```java
AtomicInteger counter = new AtomicInteger();

IntStream.range(0, 1_000)
        .parallel()
        .forEach(n -> counter.incrementAndGet());

System.out.println(counter.get()); // 1000
```

Mã đúng về mặt cập nhật counter, nhưng với mục tiêu chỉ muốn biết số phần tử, **`count()` vẫn rõ ràng hơn**, giảm side effect và có thể tránh chi phí tranh chấp biến atomic.

### 8.2. `LongAdder` khi nhiều thread cùng cập nhật metric

`LongAdder` được thiết kế cho bộ đếm có contention cao. Ví dụ chương trình hoàn chỉnh **`LongAdderDemo.java`**:

```java
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.IntStream;

public class LongAdderDemo {
    public static void main(String[] args) {
        LongAdder visits = new LongAdder();

        IntStream.range(0, 1_000)
                .parallel()
                .forEach(n -> visits.increment());

        System.out.println("Visits: " + visits.sum());
    }
}
```

Chạy `javac --release 17 LongAdderDemo.java` và `java LongAdderDemo`:

```text
Visits: 1000
```

Vì terminal `forEach` đã hoàn thành trước khi đọc `visits.sum()`, chương trình trên nhận số đếm đầy đủ. **`LongAdder.sum()` không phải snapshot nguyên tử** nếu các thread khác đang cập nhật cùng lúc; nó không thay thế một bộ đếm nguyên tử khi cần đọc giá trị chính xác ở một thời điểm giữa quá trình ghi. Khi chỉ tổng hợp phần tử đã qua stream, `count()`/`sum()` vẫn nên là lựa chọn đầu tiên.

### 8.3. Collection an toàn cho truy cập đồng thời

- `ConcurrentHashMap` hỗ trợ nhiều thao tác concurrent như `compute`, `merge` và `putIfAbsent` theo hợp đồng API. Nếu cần gom map, ưu tiên `toConcurrentMap` hoặc `groupingByConcurrent` trước khi tự làm `forEach`/`compute`.
- `ConcurrentLinkedQueue` cho phép nhiều producer thêm phần tử mà không làm hỏng cấu trúc queue, nhưng **không cam kết thứ tự encounter order** của parallel stream; thứ tự thêm phụ thuộc lịch tác vụ.
- `Collections.synchronizedList(new ArrayList<>())` cung cấp đồng bộ cho các phương thức riêng lẻ của list. Khi **duyệt iterator của list trong lúc luồng khác sửa**, vẫn phải đồng bộ ngoài theo hướng dẫn của API. Nó cũng không tự biến việc “kiểm tra rồi hành động” thành một thao tác nguyên tử.
- `CopyOnWriteArrayList` thích hợp cho dữ liệu đọc/duyệt thường xuyên và cập nhật hiếm; mỗi lần sửa tạo chi phí sao chép, nên không hợp lý để nhận hàng triệu kết quả từ một parallel stream.

Sự hiện diện của cấu trúc thread-safe không có nghĩa mọi quy tắc truy cập hoặc thứ tự của bài toán đã được đáp ứng. Hãy xác định **atomicity**, **visibility**, **iteration order**, **tính độc lập dữ liệu** và **chi phí** trước khi chọn.

## 9. Khác biệt giữa sửa collection **đích** và sửa collection **nguồn**

### 9.1. Sửa nguồn đang duyệt thường vi phạm non-interference

Ví dụ sai:

```java
List<Integer> source = new ArrayList<>(
        List.of(1, 2, 3, 4, 5)
);

source.parallelStream()
        .forEach(source::remove); // SAI: sửa source trong lúc duyệt
```

Đoạn trên **chỉ để phân tích**, không có stdout hoặc loại ngoại lệ cố định. Lỗi có thể là kết quả bỏ sót, hành vi không xác định hoặc `ConcurrentModificationException` tùy collection và lịch thực thi. Thay vì sửa source khi đang duyệt, hãy xây **kết quả lọc mới** rồi dùng kết quả đó, hoặc hoàn tất stream trước khi thực hiện thay đổi nguồn bằng API collection phù hợp.

Ví dụ an toàn:

```java
List<Integer> oddNumbers = source.parallelStream()
        .filter(n -> n % 2 != 0)
        .toList(); // [1, 3, 5]; source chưa bị thay đổi
```

Đây là đoạn mã đặt **sau khi tạo `source` ổn định**, bên trong phương thức. Nếu source đang bị **một thread khác** cập nhật khi stream duyệt, việc bản thân lambda không sửa source vẫn chưa đủ; cần snapshot an toàn hoặc phối hợp truy cập phù hợp.

### 9.2. Chụp snapshot trước khi chạy stream

Nếu một collection mutable có thể thay đổi từ nơi khác, chọn điểm đồng bộ hợp lý để lấy một snapshot ổn định trước khi xử lý. Ví dụ khi chắc chắn không có cập nhật đồng thời trong lúc chụp:

```java
List<Integer> snapshot = List.copyOf(source);
List<Integer> processed = snapshot.parallelStream()
        .map(n -> n * 2)
        .toList();
```

`List.copyOf` có từ Java 10 và không nhận phần tử `null`. **Bản thân lời gọi `List.copyOf(source)` không tự đồng bộ với một writer đang sửa source**: nếu chụp snapshot đồng thời thì phải bảo vệ thời điểm sao chép bằng cơ chế phù hợp. Snapshot cũng chỉ bất biến ở mức **cấu trúc list**; nếu phần tử là các object mutable và bị thread khác sửa, chúng vẫn có thể tạo data race khi đọc.

## 10. `forEach` và `forEachOrdered`: an toàn khác với giữ thứ tự

`forEach` là terminal operation có side effect chủ định. Trong parallel stream, nó **không bảo đảm encounter order**; action có thể chạy ở các thời điểm và thread khác nhau. Nếu action truy cập shared state, caller phải tự đồng bộ.

`forEachOrdered` thực hiện action theo encounter order **nếu stream có encounter order**, và theo hợp đồng API xử lý action theo thứ tự từng phần tử. Điều này giải quyết yêu cầu thứ tự action ở terminal operation trong một số tình huống, nhưng có thể làm giảm lợi ích parallelism, không sửa lỗi mutate source trong các bước khác và không làm trạng thái bên ngoài tự an toàn với những thread không thuộc pipeline.

Đặt cạnh nhau:

```java
IntStream.rangeClosed(1, 5)
        .parallel()
        .forEach(System.out::print); // Thứ tự in không được cam kết

IntStream.rangeClosed(1, 5)
        .parallel()
        .forEachOrdered(System.out::print); // In 12345
```

Đây là **đoạn mã độc lập bên trong phương thức**, cần import `java.util.stream.IntStream`; dòng đầu không có stdout cố định (có thể trùng thứ tự mong đợi ở một lần chạy), dòng thứ hai in `12345` khi không có output xen vào từ thread khác. Đây là ví dụ về **thứ tự action**, không phải mẫu gom dữ liệu có thể mở rộng; khi muốn trả danh sách có thứ tự, `toList()`/`collect(...)` diễn đạt ý định rõ hơn.

## 11. Lỗi về visibility và tác vụ “kiểm tra rồi cập nhật”

Ngay cả khi chương trình dường như chạy đúng trên máy phát triển, thiếu quan hệ đồng bộ trong Java Memory Model có thể khiến một thread không nhìn thấy cập nhật của thread khác đúng thời điểm mong muốn. Từ khóa `volatile` có thể hỗ trợ visibility cho biến riêng lẻ, **nhưng `volatile int count` với `count++` vẫn không nguyên tử** vì phép tăng là chuỗi đọc–tính–ghi.

Tương tự:

```java
if (!map.containsKey(key)) {
    map.put(key, value);
}
```

Hai bước kiểm tra rồi ghi không tự trở thành một thao tác nguyên tử chỉ vì `map` là một `ConcurrentHashMap`. Nếu thực sự chia sẻ map giữa nhiều thread, hãy chọn các thao tác nguyên tử theo key như `putIfAbsent`, `computeIfAbsent` hoặc `merge`, và bảo đảm function truyền vào phù hợp với hợp đồng concurrent API. Với bài toán gom phần tử Stream, vẫn nên dùng Collector trước.

## 12. Cách chọn giữa sequential, parallel và concurrent collector

| Tình huống | Giải pháp thường phù hợp |
| --- | --- |
| Chỉ tính tổng, đếm, min/max, trung bình | `sum`, `count`, `summaryStatistics`, `reduce` phù hợp |
| Chuyển list, lọc và giữ encounter order | `filter`/`map` rồi `toList` hoặc `collect(toList())` |
| Tạo map nhóm và cần encounter order trong mỗi nhóm | `groupingBy` với downstream thích hợp; cân nhắc chi phí combiner |
| Tạo map nhóm, không cần encounter order | `groupingByConcurrent`, đo hiệu năng trên dữ liệu thực |
| Cần theo dõi counter ngoài luồng để phối hợp với hệ thống khác | `AtomicInteger`/`AtomicLong` hoặc `LongAdder` tùy nhu cầu về tính chính xác từng thời điểm |
| Cần cập nhật một dịch vụ hoặc ghi log | Kiểm tra thread safety, idempotency, rate limit và thứ tự; có thể cân nhắc pipeline tuần tự hoặc mô hình worker riêng |
| Nguồn mutable bị thread khác cập nhật | Phối hợp snapshot, khóa hoặc data source hỗ trợ concurrent theo hợp đồng |
| Nguồn nhỏ, thao tác rẻ, logic nhạy cảm với thứ tự | `stream()` tuần tự hoặc vòng lặp thường dễ hiểu và ổn định hơn |

Không dùng `parallel()` chỉ để mong hệ thống tự giải quyết đồng bộ. Nó **tăng cơ hội các thao tác chạy đồng thời**, chứ không sửa lỗi thiết kế shared mutable state.

## 13. Debug và kiểm tra race condition trong thực tế

1. **Tìm state bị capture:** các tham chiếu như `counter`, `resultList`, `map`, `StringBuilder`, `entity` trong lambda. Biến tham chiếu final không có nghĩa object bất biến.
2. **Phân loại truy cập:** chỉ đọc dữ liệu ổn định hay có ghi? Có thể hai phần tử cùng ghi một object không? Có thread bên ngoài pipeline cùng truy cập không?
3. **Kiểm tra source:** stream có đang duyệt collection mà một lambda/thread khác sửa không? Nếu có, chuyển sang pipeline không can thiệp nguồn hoặc snapshot được đồng bộ.
4. **Xác định yêu cầu thứ tự:** có cần encounter order cho kết quả không? Dùng `toList` hoặc collector giữ thứ tự; `forEach` song song không có bảo đảm đó.
5. **Thay bằng reduction/collector:** trước khi thêm lock/atomic, xem bài toán có thể biểu đạt bằng `sum`, `count`, `collect`, `groupingBy` hay không.
6. **Nếu bắt buộc có side effect:** chọn cấu trúc an toàn, ranh giới transaction/atomicity và đồng bộ phù hợp. Không cho rằng chỉ thay `ArrayList` bằng một collection synchronized là giải quyết mọi yêu cầu.
7. **Kiểm thử kết quả có thể dự đoán:** kiểm tra tập phần tử, số lượng, giá trị tổng, tính duy nhất và thứ tự khi có ràng buộc. Chạy nhiều lần/stress test có thể giúp phát hiện race nhưng **không thể chứng minh hết race** khi chưa tái hiện lỗi.
8. **Đo hiệu năng:** mutex, atomic tranh chấp, collector concurrent và giữ thứ tự đều có chi phí; chỉ giữ `parallel` khi có lợi ích thực tế.

## 14. Các hiểu nhầm thường gặp

- **“Biến được capture là effectively final thì nội dung cũng bất biến.”** Sai: final trên tham chiếu không làm list, array hay object mà nó trỏ đến thread-safe.
- **“`counter[0]++` trong lambda chạy song song giống cộng tuần tự.”** Sai: đây là read-modify-write không nguyên tử.
- **“`Collections.synchronizedList` giữ thứ tự của parallel stream.”** Sai: nó đồng bộ thao tác list, không phục hồi encounter order của `forEach`.
- **“`ConcurrentHashMap` làm mọi phép kiểm tra rồi ghi thành atomic.”** Sai: cần dùng các phương thức có hợp đồng nguyên tử đúng thao tác.
- **“`volatile` đủ cho `count++`.”** Sai: volatility không biến phép tăng thành một phép atomic.
- **“`parallelStream()` sẽ chạy mỗi phần tử một thread.”** Sai: chiến lược phân chia/chạy do framework quyết định.
- **“Chạy 100 lần đều đúng nghĩa là không có race.”** Sai: một lịch chạy lỗi có thể chưa xuất hiện.
- **“`forEachOrdered` là cách tốt nhất để gom list theo thứ tự.”** Không hẳn: `collect`/`toList` thường đơn giản và tự quản lý kết quả hơn.
- **“`LongAdder.sum()` là ảnh chụp atomic trong lúc nhiều thread cập nhật.”** Sai: có thể không phản ánh một thời điểm duy nhất.
- **“`groupingByConcurrent` vừa concurrent vừa bảo toàn thứ tự phần tử trong từng nhóm.”** Sai: collector này là unordered.
- **“`Collectors.toList()` phải trả `ArrayList`.”** API không bảo đảm implementation cụ thể; `Collectors.toCollection(ArrayList::new)` khi thật sự cần loại mutable đó.
- **“`parallel()` khiến code với side effect tự an toàn.”** Sai: thread safety và non-interference vẫn do tác giả mã bảo đảm.

## 15. Câu hỏi tự kiểm tra

1. Vì sao `int[] count = {0}` được lambda capture nhưng `count[0]++` vẫn có thể mất cập nhật?
2. Nếu muốn lấy số lượng phần tử thỏa điều kiện từ một triệu số, nên chọn `parallel().forEach(n -> counter.incrementAndGet())` hay `filter(...).count()`? Vì sao?
3. Vì sao `parallel().forEach(synchronizedList::add)` có thể chứa đủ phần tử nhưng thứ tự không khớp nguồn?
4. Một source list đang được thread khác bổ sung phần tử: chỉ chuyển sang `parallelStream()` có giải quyết được tính nhất quán khi duyệt không? Cần gì để có snapshot ổn định?
5. `groupingBy` và `groupingByConcurrent` khác nhau thế nào về bảo đảm thứ tự và cơ chế giảm song song?
6. Tại sao dùng một `ArrayList` mutable làm identity của `reduce` có thể sai trong parallel stream?
7. Khi nào chọn `LongAdder` thay `AtomicLong` và vì sao `sum()` của LongAdder không phải snapshot atomic giữa lúc cập nhật?

**Gợi ý:** (1) final chỉ áp dụng cho tham chiếu; phép tăng không nguyên tử. (2) terminal `count()` loại bỏ shared state. (3) khóa không áp đặt encounter order cho parallel `forEach`. (4) phải phối hợp writer và snapshot hoặc dùng nguồn concurrent có semantics phù hợp. (5) concurrent collector unordered và có thể tích lũy chung; groupingBy thường gom các map tạm. (6) mutable identity vi phạm quy tắc reduction; dùng `collect`. (7) LongAdder tốt cho contention cao khi không cần snapshot chính xác giữa cập nhật.

**Ghi nhớ:** Với parallel stream, lỗi race condition thường không nằm ở `parallel()` mà nằm ở **lambda ghi vào trạng thái mutable chia sẻ hoặc sửa nguồn đang duyệt**. Hãy ưu tiên phép biến đổi stateless, `sum`/`count`/`reduce` đúng cách và `collect`/Collector chuẩn. Chỉ dùng atomic, đồng bộ hoặc concurrent collection khi yêu cầu side effect thật sự tồn tại và đã xác định rõ tính nguyên tử, thứ tự cùng vòng đời dữ liệu.

## Tài liệu Java chính thức đang áp dụng

- Stream package — Non-interference, statelessness, mutable reduction, ordering, side effects: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
- Stream — `forEach`, `forEachOrdered`, `collect`, `toList`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html
- Collectors — `groupingBy`, `groupingByConcurrent` và các collector chuyên biệt: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html
- ConcurrentHashMap — `compute`, `merge` và thao tác đồng thời: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- LongAdder — `increment` và ý nghĩa `sum()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- Collections — `synchronizedList`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html
