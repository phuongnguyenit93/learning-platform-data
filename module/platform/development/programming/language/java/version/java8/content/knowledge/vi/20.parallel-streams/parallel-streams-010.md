# Pipeline lồng nhau và tranh chấp tài nguyên trong Java Parallel Stream

Trong Java, một Stream có thể tạo **pipeline con ngay trong `map`, `flatMap` hoặc `forEach`**. Khi cả pipeline ngoài lẫn pipeline trong đều dùng `parallel()`/`parallelStream()`, chương trình có **song song lồng nhau** (*nested parallelism*). Cú pháp này hợp lệ, nhưng **nhiều tầng song song không có nghĩa là nhiều hiệu năng hơn**. Chi phí lập lịch, chờ kết quả, tranh chấp CPU, khóa và kết nối có thể lớn hơn phần việc hữu ích.

Ví dụ thường gặp là xử lý dữ liệu phân cấp: `batches → scores`, `orders → orderLines`, `departments → employees`, `files → records`. Một hệ thống còn có thể lồng những truy cập HTTP, database hoặc ghi tệp trong từng bước; đây là nơi **resource contention** dễ khiến toàn ứng dụng chậm hơn.

Mục tiêu bài học:
- Nhận diện các dạng pipeline lồng nhau và **chọn tầng cần song song**.
- Phân biệt **tính đúng**, **thread-safety** và **hiệu năng**.
- Hiểu vai trò `ForkJoinPool`/common pool và các loại tranh chấp tài nguyên.
- Tránh ghi chung `ArrayList`, `HashMap`, biến đếm hoặc đồng bộ hóa không cần thiết.
- Biết khi nào dùng `reduce`, `collect`, `groupingByConcurrent`, `ExecutorService`, batching và giới hạn concurrency.
- Đo đúng trước khi tối ưu, không khẳng định một biến thể luôn nhanh nhất.

Các API `Stream`, `ForkJoinPool` và `ExecutorService` vẫn là kiến thức đang được sử dụng trong Java hiện đại. Các ví dụ chạy trên **JDK 17+**; một số cú pháp như `record` và `Stream.toList()` được bổ sung sau Java 8, sẽ được chú thích rõ.

## 1. Năm cách tổ chức xử lý dữ liệu nhiều cấp

Giả sử có `List<Batch> batches`, mỗi `Batch` giữ một `List<Integer> scores`. Ta muốn tính tổng tất cả `scores`. Có những phương án sau:

**(1) Cả hai tầng tuần tự** — baseline đơn giản:

```java
long sum = batches.stream()
        .mapToLong(b -> b.scores().stream()
                .mapToLong(Integer::longValue).sum())
        .sum();
```

**(2) Ngoài song song, trong tuần tự** — mỗi batch là một công việc độc lập:

```java
long sum = batches.parallelStream()
        .mapToLong(b -> b.scores().stream()
                .mapToLong(Integer::longValue).sum())
        .sum();
```

**(3) Ngoài tuần tự, trong song song** — xử lý lần lượt các batch, nhưng mỗi batch có thể chia nhỏ:

```java
long sum = batches.stream()
        .mapToLong(b -> b.scores().parallelStream()
                .mapToLong(Integer::longValue).sum())
        .sum();
```

**(4) Cả hai tầng song song** — nested parallel stream:

```java
long sum = batches.parallelStream()
        .mapToLong(b -> b.scores().parallelStream()
                .mapToLong(Integer::longValue).sum())
        .sum();
```

**(5) Trải phẳng rồi song song một lần** — không cần ranh giới batch khi tổng hợp:

```java
long sum = batches.stream()
        .flatMapToLong(b -> b.scores().stream()
                .mapToLong(Integer::longValue))
        .parallel()
        .sum();
```

Không có phương án nào mặc định nhanh nhất. Với 1.000 batch, mỗi batch 3 số, xử lý tuần tự từng batch nhưng song song ở cấp ngoài thường hợp lý để **thử nghiệm**. Nếu chỉ có 2 batch nhưng mỗi batch chứa hàng triệu số thì phải xem khả năng phân hoạch ở cấp trong/trải phẳng. Nếu tất cả phép tính nhẹ, xử lý tuần tự có thể nhanh hơn vì tránh overhead. Phải đo trên dữ liệu thật.

`parallelStream()` **không tạo một thread cho mỗi phần tử**, và hai lời gọi song song **không có nghĩa tạo hai thread pool riêng**. Runtime phân chia công việc thành task rồi sử dụng các worker sẵn có.

## 2. Ví dụ Java 17+ đầy đủ: kết quả bằng nhau, lịch thực thi khác nhau

Tạo tệp `NestedPipelineDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class NestedPipelineDemo {
    record Batch(String name, List<Integer> scores) {}

    public static void main(String[] args) {
        List<Batch> batches = List.of(
                new Batch("A", List.of(1, 2, 3)),
                new Batch("B", List.of(4, 5)),
                new Batch("C", List.of(6)));

        long nested = batches.parallelStream()
                .mapToLong(b -> b.scores().parallelStream()
                        .mapToLong(Integer::longValue).sum())
                .sum();

        long outerOnly = batches.parallelStream()
                .mapToLong(b -> b.scores().stream()
                        .mapToLong(Integer::longValue).sum())
                .sum();

        long innerOnly = batches.stream()
                .mapToLong(b -> b.scores().parallelStream()
                        .mapToLong(Integer::longValue).sum())
                .sum();

        long onePipeline = batches.stream()
                .flatMapToLong(b -> b.scores().stream()
                        .mapToLong(Integer::longValue))
                .parallel()
                .sum();

        Map<String, Long> totals = batches.parallelStream()
                .collect(Collectors.toMap(
                        Batch::name,
                        b -> b.scores().stream()
                                .mapToLong(Integer::longValue).sum()));

        System.out.println("nested = " + nested);
        System.out.println("outerOnly = " + outerOnly);
        System.out.println("innerOnly = " + innerOnly);
        System.out.println("onePipeline = " + onePipeline);
        System.out.println("per batch = " + new TreeMap<>(totals));
    }
}
```

```bash
javac -encoding UTF-8 NestedPipelineDemo.java
java NestedPipelineDemo
```

```text
nested = 21
outerOnly = 21
innerOnly = 21
onePipeline = 21
per batch = {A=6, B=9, C=6}
```

**Giải thích:** Tất cả phương án đều có cùng tổng toán học: `1+2+3+4+5+6 = 21`. `TreeMap` giúp in Map theo thứ tự khóa để có stdout cố định; `Collectors.toMap` không cam kết thứ tự của Map trả về và ví dụ giả định tên batch không trùng. Không có số liệu thời gian trong stdout vì bài học này **không dùng một lần chạy để kết luận tốc độ**.

`record` cần Java 16+, `List.of` cần Java 9+. Nếu phải dùng đúng JDK 8, thay `record` bằng class có constructor/getter và `List.of` bằng `Arrays.asList`; cơ chế Stream, `Collectors`, `parallelStream` vẫn có từ Java 8.

## 3. Vì sao nested parallelism có thể làm chậm?

Một pipeline ngoài chia batch thành task; mỗi task lại có thể tạo tác vụ song song để xử lý danh sách bên trong. Các task phải được xếp lịch và kết hợp kết quả. Khi quá nhỏ, phần **phí tổ chức** có thể vượt lợi ích của nhiều worker.

```text
outer parallel stream
  ├─ batch A → inner parallel → task → task → combine
  ├─ batch B → inner parallel → task → task → combine
  └─ batch C → inner parallel → task → task → combine
                       ↓
              shared CPU / worker pool
                       ↓
                outer reduction
```

Các nguồn chi phí chính:
- **Task creation/scheduling:** phân chia đầu vào, đưa task vào hàng đợi, work-stealing và kết hợp kết quả.
- **Nested completion:** outer task cần kết quả của inner pipeline trước khi hoàn thành bước `mapToLong`; chi tiết thực thi/chờ phụ thuộc implementation.
- **CPU contention:** nhiều task muốn chạy cùng lúc nhưng số lõi vật lý là hữu hạn.
- **Cache và memory bandwidth:** nhiều worker truy cập bộ nhớ hoặc cùng cache line; allocation/GC tăng.
- **Imbalance:** một batch rất nặng, các batch khác rất nhẹ. Chia theo batch có thể không phân bổ đều công việc.
- **Competition với workload khác:** ứng dụng có thể cùng lúc thực thi nhiều parallel stream, fork/join task hoặc công việc khác.

Đừng suy ra số thread bằng `số batch × số phần tử`. Nhiều task không đồng nghĩa tạo từng ấy thread. Điều cần đánh giá là **có bao nhiêu tác vụ thực sự cần CPU hoặc chờ tài nguyên cùng lúc**, không phải đếm số chữ `parallel`.

### `flatMap` không phải thuốc tăng tốc vạn năng

Trải phẳng thành một pipeline có thể giảm độ phức tạp về cấu trúc và bớt nested operations. Tuy nhiên, việc chia công việc tùy thuộc nguồn và `Spliterator`; với một batch cực lớn và nhiều batch nhỏ, một pipeline có `flatMapToLong` chưa chắc phân hoạch tối ưu cho mọi trường hợp. Nếu cần giữ thông tin batch hoặc kết quả theo nhóm, flatten có thể phải mang theo khóa nhóm và thêm bước grouping.

## 4. `ForkJoinPool`, common pool và tính chia sẻ tài nguyên

Trong các JDK phổ biến, parallel stream sử dụng cơ chế thực thi task của `ForkJoinPool` với **work-stealing**. Khi chạy từ thread ứng dụng thông thường, các tác vụ của parallel stream thường sử dụng `ForkJoinPool.commonPool()`; khi đang ở trong một `ForkJoinPool` worker, ngữ cảnh pool có thể khác. Đây là chi tiết triển khai cần hiểu khi chẩn đoán, **không phải lời hứa của Stream API rằng mọi pipeline luôn dùng common pool**.

`ForkJoinPool` phù hợp với công việc tính toán có thể chia nhỏ, nơi các worker lấy task của nhau để cân bằng. Nhưng **common pool là tài nguyên chung của tiến trình**. Nếu một nghiệp vụ đẩy nhiều task nặng vào đó, những công việc khác cũng cần common pool có thể bị chậm.

Lưu ý:
- `Stream.parallel()` bật chế độ song song nhưng **không nhận `Executor` làm tham số**. Không có API `parallelStream(executor)` trong `Stream` chuẩn.
- Không gọi `ForkJoinPool.commonPool().shutdown()` để “dọn tài nguyên của một stream”; đây là pool chia sẻ và shutdown không có tác dụng như đối với private pool.
- Không tự ý thay đổi `java.util.concurrent.ForkJoinPool.common.parallelism` trên toàn JVM chỉ vì một pipeline chậm: thay đổi cấu hình chung có thể ảnh hưởng nhiều thư viện.
- Custom `ForkJoinPool` có thể phù hợp cho kiến trúc task chuyên biệt, nhưng cách chạy parallel stream bên trong task custom pool có chi tiết implementation. Nếu cần hợp đồng điều phối chặt, nên thiết kế bằng `ExecutorService`/fork-join tasks trực tiếp thay vì giả định Stream cho chọn executor.
- **Nested parallel không mặc định gây deadlock.** Rủi ro deadlock/starvation đến từ phụ thuộc tác vụ, giữ khóa, blocking và thiết kế tài nguyên.

## 5. Tranh chấp tài nguyên: không chỉ có CPU

**Contention** xảy ra khi nhiều tác vụ cần cùng một tài nguyên hữu hạn: CPU, mutex, bộ đếm, database connection, HTTP connection, tốc độ truy vấn, băng thông ổ đĩa hoặc memory allocator.

| Tài nguyên | Tình huống trong pipeline lồng nhau | Hậu quả | Hướng xử lý |
| --- | --- | --- | --- |
| CPU | Nhiều tác vụ tính toán cùng lúc | Overhead, tranh lõi, throughput không tăng | Chọn một tầng, tăng kích thước batch, benchmark |
| `synchronized`/`Lock` | Mọi mapper cập nhật cùng object | Chặn worker, nối đuôi nhau | Giảm critical section; thu kết quả cục bộ bằng collector |
| `AtomicInteger` | Tất cả phần tử tăng một biến chung | Contentious writes/cache-line contention | `count()`, `sum()`, `reduce()` |
| `ConcurrentHashMap` | Nhiều phần tử cùng ghi một key nóng | Hotspot dù cấu trúc thread-safe | Phân hoạch khác, kiểm tra key skew, collector phù hợp |
| DB connection pool | Mỗi dòng hàng gọi query, pool có 8 connection | Chờ connection, timeout | Batch query, giới hạn concurrency, tránh N+1 |
| HTTP/API | Nhiều yêu cầu bị chặn/chờ rate limit | 429, backlog, retry storm | Rate limit, backpressure, timeout/cancel, batching |
| Tệp/ổ đĩa | Nhiều worker đọc cùng thiết bị | I/O queue tăng, băng thông không tăng | Đo throughput, cân nhắc sequential/batch I/O |
| Heap/GC | Mỗi task tạo Map/list/buffer | Allocation/GC và memory pressure | Giảm intermediate allocations, tránh pipeline lồng quá sâu |

**Thread-safe không có nghĩa là nhanh**. Một `ConcurrentHashMap` hay `AtomicInteger` có thể giữ đúng dữ liệu nhưng vẫn là hotspot. Ngược lại, một chương trình chạy nhanh ở vài lần thử không chứng minh nó đúng nếu có data race.

## 6. Sai lầm thường gặp: shared mutable state trong lambda

### Ghi vào `ArrayList` chung là không an toàn

```java
List<Integer> results = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(results::add); // SAI: ArrayList.add không thread-safe.
```

Đây là **phản ví dụ**, không phải chương trình khuyến nghị. Nhiều worker cùng sửa `ArrayList` có thể gây lost updates hoặc làm hỏng cấu trúc dữ liệu. Việc kết quả “có vẻ đúng” trên một máy không biến cách làm thành đúng.

Thay bằng collector/terminal operation:

```java
List<Integer> results = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList(); // Java 16+
```

`Stream.toList()` tạo danh sách **unmodifiable** và giữ encounter order nếu nguồn có thứ tự. Trên Java 8 có thể dùng `collect(Collectors.toList())`; API này không cam kết lớp triển khai hoặc khả năng sửa của danh sách. Nếu cần danh sách có thể sửa, chọn collector hoặc copy có mục đích.

### `AtomicInteger` đúng về đồng bộ, nhưng tạo điểm tranh chấp

```java
AtomicInteger count = new AtomicInteger();
IntStream.range(0, 10_000)
        .parallel()
        .forEach(i -> count.incrementAndGet());
System.out.println(count.get()); // 10000
```

`incrementAndGet` nguyên tử, nhưng mọi task tranh quyền cập nhật **một địa chỉ bộ nhớ**. Nếu chỉ cần đếm, không cần ghi trạng thái chung:

```java
long count = IntStream.range(0, 10_000)
        .parallel()
        .count(); // 10000
```

Khi thật sự cần bộ đếm concurrent cho nhiều tác vụ độc lập, `LongAdder` có thể có lợi dưới mức tranh chấp cao, nhưng không nên đổi một phép `count()` thuần túy thành side effect chỉ để sử dụng API concurrent.

### `synchronized` có thể khiến xử lý có phần tuần tự

```java
Object lock = new Object();
long total = IntStream.range(0, 1_000)
        .parallel()
        .mapToLong(i -> {
            synchronized (lock) {
                return i;
            }
        })
        .sum();
// total == 499500
```

Ví dụ minh họa chạy trong phương thức đã import `IntStream`. Kết quả đúng nhưng tất cả task cùng đi qua một critical section. Với phép cộng đơn giản, `IntStream.range(0, 1000).asLongStream().sum()` diễn đạt bài toán tốt hơn và không cần khóa.

Không giữ lock khi đợi HTTP/DB/Future/inner task. Nếu task A giữ khóa và chờ task B mà B phải lấy cùng khóa đó, có thể xảy ra **vòng chờ**. Deadlock đến từ thiết kế phụ thuộc, **không phải vì một code fragment có hai lần `parallel()`**.

## 7. Dùng reduction thay cho cập nhật trạng thái chung

Các phép `sum()`, `count()`, `reduce()` và `collect()` được thiết kế để kết hợp kết quả từ những phần công việc. Với phép toán kết hợp (associative), identity đúng và accumulator stateless, runtime có thể gom nhiều kết quả cục bộ mà không buộc mọi mapper ghi vào một biến ngoài pipeline.

Ví dụ:

```java
long total = IntStream.rangeClosed(1, 10_000)
        .parallel()
        .asLongStream()
        .sum();
// 50005000
```

Với collector tùy biến, phải bảo đảm quy tắc `supplier`, `accumulator`, `combiner` và các characteristics. Không sử dụng một `ArrayList` mutable duy nhất làm shared result container của các partition khi collector không được thiết kế concurrent.

### `groupingBy` và `groupingByConcurrent`

- `Collectors.groupingBy` hỗ trợ parallel collection, thường bằng nhiều Map cục bộ được **merge** ở bước combiner. Điều này có thể tốn chi phí nếu dữ liệu lớn và nhiều khóa.
- `Collectors.groupingByConcurrent` dùng concurrent collector, có thể tránh một số chi phí merge và hoạt động tốt trong vài bài toán phân nhóm; **không cam kết thứ tự các phần tử bên trong mỗi nhóm**. Downstream collector được tích hợp thông qua hợp đồng Collector, không có nghĩa mọi thao tác sửa cấu trúc ngoài pipeline đều an toàn.
- Với key phân phối lệch, một vài key xuất hiện cực nhiều có thể gây contention. Concurrent collection **không đồng nghĩa lock-free** hoặc nhanh hơn cho mọi workload.
- Nếu yêu cầu thứ tự encounter order của danh sách theo từng nhóm là quan trọng, cân nhắc `groupingBy`/collector khác có semantics phù hợp.

Sự lựa chọn tùy tính đúng và performance benchmark, không phải cứ thấy `parallel()` là thay toàn bộ collector bằng loại Concurrent.

## 8. Ví dụ đầy đủ: song song an toàn và kết quả xác định

Tạo tệp `SafeAggregationDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class SafeAggregationDemo {
    public static void main(String[] args) {
        long sum = IntStream.rangeClosed(1, 10_000)
                .parallel()
                .asLongStream()
                .sum();

        long count = IntStream.range(0, 10_000)
                .parallel()
                .count();

        Map<Integer, Long> grouped = IntStream.range(0, 10_000)
                .parallel()
                .boxed()
                .collect(Collectors.groupingByConcurrent(
                        n -> n % 4,
                        Collectors.counting()));

        List<Integer> ordered = IntStream.range(0, 5)
                .parallel()
                .boxed()
                .toList();

        AtomicInteger atomic = new AtomicInteger();
        IntStream.range(0, 10_000)
                .parallel()
                .forEach(x -> atomic.incrementAndGet());

        System.out.println("sum = " + sum);
        System.out.println("count = " + count);
        System.out.println("grouped = " + new TreeMap<>(grouped));
        System.out.println("ordered = " + ordered);
        System.out.println("atomic = " + atomic.get());
    }
}
```

```bash
javac -encoding UTF-8 SafeAggregationDemo.java
java SafeAggregationDemo
```

```text
sum = 50005000
count = 10000
grouped = {0=2500, 1=2500, 2=2500, 3=2500}
ordered = [0, 1, 2, 3, 4]
atomic = 10000
```

`count` và `sum` không cần shared mutable accumulator trong lambda. `groupingByConcurrent` trả kết quả đếm ổn định; `TreeMap` chỉ phục vụ in thứ tự khóa. `ordered` giữ encounter order, dù worker xử lý các phần tử lúc nào không được bảo đảm. `atomic` cho kết quả đúng về thread-safety, **nhưng điều đó không chứng minh cách cập nhật chung này có performance tốt**.

## 9. Blocking I/O: nơi nested parallel dễ lộ nhược điểm

Khi mapper thực hiện HTTP, database, tệp hoặc chờ mutex/semaphore, worker có thể phải **dừng chờ** thay vì tính toán. `ForkJoinPool` có cơ chế quản lý việc chia task nhưng không bảo đảm tự bù đủ worker trong mọi tình huống **unmanaged blocking I/O** hoặc đồng bộ hóa bên ngoài. `ForkJoinPool.ManagedBlocker` là API hỗ trợ trường hợp chặn được khai báo; không phải cách tự động sửa mọi lời gọi I/O trong stream.

Đoạn sau chỉ **minh họa cấu trúc nguy hiểm**, không phải mã Java độc lập vì thiếu khai báo biến nghiệp vụ:

```java
orders.parallelStream().forEach(order ->
        order.lines().parallelStream().forEach(line ->
                externalService.process(line)));
```

Nếu cả hai cấp đều tạo các thao tác cần connection từ pool hữu hạn, nhiều task có thể chờ nhau gián tiếp. Timeout và retry có thể đẩy thêm tải lên hệ thống. Nếu mỗi phần tử mở một truy vấn, còn có nguy cơ **N+1 queries**.

Giải pháp thường đáng thử trước:
1. **Batch I/O** và truy vấn một lần cho nhiều phần tử, nếu backend hỗ trợ.
2. **Giới hạn số request đồng thời** theo connection pool, tài nguyên dịch vụ và SLA.
3. **Timeout, cancellation, retry có giới hạn**, tránh retry storm.
4. **Bounded queue/backpressure** nếu tốc độ phát sinh công việc lớn hơn tốc độ xử lý.
5. Phân biệt **CPU-bound** (parallel stream có thể phù hợp) với **I/O-bound** (thường cần mô hình điều phối tài nguyên khác).

Với Java 21+, virtual threads có thể phù hợp cho nhiều tác vụ blocking I/O đồng bộ, nhưng chúng **không làm tăng số CPU core hay số database connection**. Cần vẫn áp đặt giới hạn lưu lượng. Không dùng `parallelStream` như một bộ điều tiết API rate limit.

## 10. Ví dụ đầy đủ: Executor giới hạn số worker

Đôi khi cần điều phối công việc bên ngoài Stream với quyền kiểm soát số task chạy đồng thời. `ExecutorService` và `ThreadPoolExecutor` là công cụ hiện hành cho việc này.

Tạo `BoundedTasksDemo.java`:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BoundedTasksDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            List<Callable<Integer>> tasks = List.of(
                    () -> 1,
                    () -> 4,
                    () -> 9,
                    () -> 16);

            int sum = 0;
            for (Future<Integer> future : pool.invokeAll(tasks)) {
                sum += future.get();
            }
            System.out.println("bounded sum = " + sum);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 BoundedTasksDemo.java
java BoundedTasksDemo
```

```text
bounded sum = 30
```

`newFixedThreadPool(2)` chạy tối đa hai task cùng lúc trên worker của pool, không tạo bốn worker cho bốn `Callable`. `invokeAll` chờ công việc kết thúc và trả `Future` theo thứ tự danh sách đầu vào. `shutdown()` ngừng nhận việc mới; chương trình mẫu nhỏ đã chờ đủ mọi `Future` trước khi shutdown.

**Đừng nhầm giới hạn worker với backpressure hoàn chỉnh:** `Executors.newFixedThreadPool` dùng hàng đợi không có giới hạn kích thước cố định. Với sản xuất task liên tục, cần thiết kế queue có giới hạn hoặc cơ chế chặn/từ chối với `ThreadPoolExecutor` và timeout/cancel khi cần. Một pool hai worker vẫn có thể giữ hàng triệu task chờ nếu thiếu backpressure.

Ví dụ dùng `try/finally` để chạy trên JDK 17+. Các API vòng đời như `close()` trên `ExecutorService` có khác biệt theo phiên bản JDK; khi cần mã JDK 17, `shutdown`/`awaitTermination` và quản lý interruption rõ ràng hơn là giả định có thể tự động close bằng `try-with-resources`.

## 11. Deadlock, starvation, blocking và contention khác gì nhau?

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Contention** | Nhiều task tranh tài nguyên hữu hạn | 12 task đợi một mutex hoặc 4 connection |
| **Blocking** | Một task chờ I/O, khóa, Future hoặc quota | HTTP chậm, connection pool hết slot |
| **Starvation** | Task không có cơ hội tiến triển đủ vì tài nguyên luôn bị chiếm | Work queue kéo dài, task chờ lâu |
| **Deadlock** | Các bên có phụ thuộc chờ lẫn nhau thành vòng | Outer giữ khóa A, chờ inner; inner chờ A |
| **Oversubscription** | Quá nhiều runnable work so với năng lực xử lý hiệu quả | Lập lịch nhiều task nhưng CPU/bộ nhớ đã bão hòa |

Nested parallel **không tự động sinh deadlock**; một phép tổng thuần tính toán có thể chạy hoàn toàn đúng. Deadlock cần có vòng phụ thuộc thực sự, thường liên quan lock, task join hoặc tài nguyên được giữ khi chờ một công việc khác. Hãy kiểm tra thread dump, lock owner, pool state và đường chờ khi nghi ngờ deadlock, thay vì gắn nhãn mọi lần chậm là deadlock.

Có thể có **thread-safe nhưng contention cao**. Với `synchronized`, tính đúng được bảo vệ bằng khóa nhưng throughput giảm nếu critical section quá lớn. Với `AtomicInteger`, update đúng nguyên tử nhưng nhiều core phải cạnh tranh trên cùng biến.

## 12. Thứ tự, side effects và đặc tính kết hợp của reduce

- `parallelStream().forEach(System.out::println)` **không cam kết thứ tự**. Không dùng stdout từ `forEach` để xác định thứ tự phần tử của pipeline.
- `forEachOrdered` giữ encounter order khi nguồn có thứ tự, nhưng có thể tốn chi phí phối hợp và giảm lợi ích song song.
- `Stream.toList()` trả danh sách theo encounter order nếu nguồn có thứ tự, không hứa mapper luôn được gọi theo thứ tự đó hoặc trên cùng thread.
- Lambda nên **non-interfering, stateless**. Không sửa `ArrayList` nguồn trong khi Stream đang duyệt, kể cả khi chạy tuần tự; việc sửa nguồn có thể làm sai kết quả hoặc ném ngoại lệ.
- Đừng lạm dụng `peek`/`map` để thực hiện side effect bắt buộc. Một số terminal như `count()` có thể tối ưu không duyệt từng phần tử trong điều kiện thích hợp; side effect có thể không được gọi như bạn mong đợi.
- `reduce(identity, accumulator)` phải bảo đảm identity và tính **associative** khi muốn kết quả đúng với nhiều cách phân hoạch. Phép trừ không phải phép gộp kết hợp đơn giản; phép cộng `double` có sai số phụ thuộc thứ tự tính trong nhiều trường hợp.
- Khi dùng mutable collector tùy biến, các accumulator/combiner phải tuân thủ hợp đồng. Không dùng một container mutable chia sẻ cho mọi partition trừ khi collector thực sự được thiết kế concurrent và đáp ứng các yêu cầu an toàn.

## 13. Checklist lựa chọn chiến lược theo workload

| Hoàn cảnh | Thử trước | Tránh |
| --- | --- | --- |
| Rất ít nhóm, mỗi nhóm có vài item | Tuần tự cả hai cấp | Bật song song chỉ để “tối ưu” |
| Nhiều nhóm độc lập, CPU-bound, chi phí gần đồng đều | Outer `parallelStream`, inner tuần tự | Tự bật thêm inner parallel khi chưa đo |
| Ít nhóm nhưng mỗi nhóm rất lớn | Inner parallel hoặc cải thiện partition | Chia outer thành quá ít task |
| Không cần kết quả theo nhóm | Một pipeline `flatMap...parallel` | Giữ nhiều nested pipelines không cần thiết |
| Cần kết quả per-group | Outer parallel, inner tuần tự và collector đúng | Shared mutable Map/List không đồng bộ |
| Có DB/HTTP blocking | Batch + bounded executor/concurrency + timeout | Dùng parallel stream làm rate limiter |
| Nhiều giá trị cùng một key | Đo `groupingBy` và `groupingByConcurrent` | Cho rằng concurrent luôn nhanh hơn |
| Phải giữ thứ tự kết quả | Thu kết quả theo encounter order/`forEachOrdered` | Dùng `forEach` rồi dựa vào thứ tự log |

Đây là hướng dẫn **để đo thử**, không phải kết luận hiệu năng tổng quát. Điều kiện quyết định là số lõi, chi phí mỗi item, số lượng nhóm, kích thước nguồn, mức độ lệch, latency tài nguyên ngoài và tải đồng thời từ phần còn lại của ứng dụng.

## 14. Đo và chẩn đoán hiệu năng đúng cách

1. **Có baseline tuần tự.** Đảm bảo mọi biến thể trả cùng giá trị; correctness phải được kiểm tra trước performance.
2. **Dùng dữ liệu đại diện.** Thử các trường hợp nhóm đều, nhóm lệch nhiều, nhiều batch nhỏ, batch lớn và số request cao.
3. **Warm-up rồi đo nhiều lần.** JVM JIT, GC, allocation, tải máy và cache có thể làm biến động mạnh; với microbenchmark nên dùng **JMH** thay vì một `System.nanoTime()` đơn lẻ.
4. **Đo throughput và latency**, không chỉ thời gian của một task. Với dịch vụ, xem cả p95/p99 latency và ảnh hưởng của một workload tới workload khác.
5. **Quan sát tài nguyên.** CPU usage, blocked threads, queue, connection wait, GC, allocation, fork/join active tasks, thread dump, tốc độ I/O.
6. **Chọn cách đơn giản đạt mục tiêu.** Nếu outer-only và nested cho hiệu năng tương đương, outer-only thường dễ kiểm soát hơn.
7. **Kiểm tra ngoại lệ và dọn tài nguyên.** Không bỏ qua failure của Future, timeout hay cancellation. Đừng dùng parallel stream với source IO như `Files.lines` mà quên đóng Stream khi cần.

Thước đo “càng nhiều thread càng nhanh” dễ sai. Khi CPU bão hòa, thêm runnable work có thể tăng context switching/cache pressure; khi I/O bão hòa, thêm request có thể tăng queue và timeout. Chẩn đoán đúng **tài nguyên giới hạn** rồi mới chọn mức concurrency.

## 15. Lỗi phổ biến

1. **Hai tầng `parallelStream()` và tưởng tăng tốc gấp đôi.** Thường chỉ tạo thêm cơ hội phân rã task và overhead.
2. **Dùng shared `ArrayList`/`HashMap` trong `forEach`.** Data race và khả năng hỏng dữ liệu.
3. **Bọc mọi ghi bằng một `synchronized` lớn.** Có thể đúng dữ liệu nhưng làm vô hiệu phần lớn song song.
4. **Dùng `AtomicInteger` cho phép đếm mà `count()` đã làm được.** Đúng nhưng tạo tranh chấp không cần thiết.
5. **Cho rằng `groupingByConcurrent` giữ thứ tự phần tử trong nhóm.** Không có bảo đảm ấy.
6. **Nhầm thread pool với connection pool.** 16 worker không tạo 16 connection nếu pool DB chỉ cho 8.
7. **Cho rằng virtual threads (Java 21+) làm tăng tốc CPU-bound.** Virtual threads giúp nhiều tác vụ chờ I/O, không tạo thêm lõi CPU.
8. **Lập trình blocking trong common pool mà không kiểm soát.** Task có thể chờ tài nguyên và ảnh hưởng workload khác.
9. **Cho rằng nested parallel luôn deadlock.** Deadlock phụ thuộc vòng chờ/khóa/nguồn lực, không phải cú pháp Stream.
10. **Dựa vào thứ tự `forEach` khi song song.** Thứ tự callback có thể thay đổi.
11. **Tối ưu dựa trên vài phần tử và một lần đo.** Chưa đủ bằng chứng về hiệu năng.
12. **Dùng lại một Stream sau terminal operation.** `collect`, `sum`, `count` tiêu thụ pipeline; lấy Stream mới từ collection khi cần chạy lại.

## 16. Bài tập tự kiểm tra

**Câu 1.** Vì sao `groups.parallelStream().map(g -> g.items().parallelStream()...)` không chắc nhanh hơn chỉ song song ở ngoài?  
**Đáp án:** Cần thêm lập lịch, phân chia, gom task; các tầng vẫn cùng cạnh tranh CPU/worker và tài nguyên hữu hạn. Hiệu năng cần benchmark.

**Câu 2.** Có đúng là mỗi lời gọi `parallelStream()` tạo pool riêng không?  
**Đáp án:** Không. Stream API không có bảo đảm đó; JDK phổ biến dùng `ForkJoinPool`, thường là common pool từ caller thông thường.

**Câu 3.** `AtomicInteger` có giải quyết data race khi tăng đếm không? Có đảm bảo tốc độ tốt không?  
**Đáp án:** `incrementAndGet` nguyên tử cho đếm đúng, nhưng nhiều task có thể tranh cùng biến; `count()` thường phù hợp hơn.

**Câu 4.** Trong parallel stream, `ArrayList.add` vào chung một danh sách có an toàn không?  
**Đáp án:** Không. Dùng `collect`/`toList` hoặc cơ chế có contract phù hợp.

**Câu 5.** Tại sao dùng parallel stream để gọi 10.000 truy vấn trên pool có 8 kết nối là rủi ro?  
**Đáp án:** Connection vẫn hữu hạn. Các task có thể đợi, làm tăng queue, timeout, retry; cần batch/giới hạn concurrency.

**Câu 6.** `groupingByConcurrent` có luôn nhanh và đảm bảo thứ tự trong nhóm không?  
**Đáp án:** Không. Có thể có hotspot, contention, và không bảo đảm encounter order trong mỗi nhóm.

**Câu 7.** Nếu cần đầu ra theo thứ tự từ một Stream có thứ tự, nên dùng `forEach` hay `forEachOrdered`?  
**Đáp án:** `forEachOrdered` hoặc thu dữ liệu thành list/mảng theo thứ tự rồi trình bày, tùy yêu cầu.

**Câu 8.** Deadlock có mặc định xảy ra khi dùng nested parallel không?  
**Đáp án:** Không. Chỉ xuất hiện khi có vòng phụ thuộc/chờ, thường liên quan giữ khóa hoặc tài nguyên.

**Câu 9.** Khi chỉ cần tổng mọi item, vì sao cân nhắc `flatMapToLong` rồi một lần `parallel()`?  
**Đáp án:** Giảm cấu trúc lồng nhau, mô tả một pipeline tính toán; nhưng khả năng partition vẫn phụ thuộc nguồn và phải đo.

**Câu 10.** Vì sao Java 17 không nên giả định `ExecutorService` dùng được trong `try-with-resources`?  
**Đáp án:** API `AutoCloseable`/`close` của ExecutorService được bổ sung ở những phiên bản sau. Trên JDK 17, sử dụng `shutdown()` trong `finally` cùng chính sách chờ và dọn task phù hợp.

## 17. Kết luận

**Phân tầng song song là quyết định kiến trúc, không chỉ là thay `stream()` bằng `parallelStream()`.** Nested parallel stream có thể đúng và đôi khi hữu ích, nhưng cũng có thể tăng scheduling overhead, khóa, áp lực bộ nhớ hoặc bão hòa tài nguyên I/O. Bắt đầu bằng pipeline tuần tự làm chuẩn, chỉ song song một tầng khi có lý do, dùng reduction/collector thay mutable state và giới hạn concurrency với tài nguyên ngoài. Đánh giá dựa trên **tính đúng + throughput/latency thực tế**.

### Tài liệu Java API chính thức

- [java.util.stream — Parallelism, non-interference, statefulness, side effects, concurrent reduction](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
- [Stream — parallel, flatMap, reduce, collect, forEach, forEachOrdered](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Collectors — groupingBy, groupingByConcurrent và các collector chuẩn](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html)
- [ForkJoinPool — commonPool, work-stealing, ManagedBlocker](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html) và [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — quản lý lifecycle, worker và queue.
