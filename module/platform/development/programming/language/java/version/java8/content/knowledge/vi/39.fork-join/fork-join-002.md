# Fork/Join: Common parallelism và tác động lên nhiều thư viện

**Chủ đề cha:** Fork/Join. **Trọng tâm:** Hiểu `ForkJoinPool.commonPool()`, mức `common parallelism`, cách pool dùng chung ảnh hưởng đến `CompletableFuture`, parallel stream, `Arrays.parallelSort`, các phép bulk của `ConcurrentHashMap` và những phần mềm/thư viện sử dụng Fork/Join. Học cách quan sát, kiểm thử, tránh starve vì blocking I/O và cách ly nhóm công việc khi cần SLA khác nhau.

**Đối tượng:** Lập trình viên Java 8+ đang vận hành ứng dụng đa luồng. Các API nền `ForkJoinPool`, `ForkJoinTask`, `CompletableFuture` và Stream vẫn **được hỗ trợ trong Java hiện hành**. Các chương trình độc lập bên dưới sử dụng **Java 17+**, nêu lệnh `javac`/`java` và stdout đáng tin. Các API bổ sung từ **Java 19+** được ghi rõ và không dùng trong chương trình `--release 17`.

> **Kết luận cần nắm ngay:** Common pool là một **tài nguyên thực thi chia sẻ trong một JVM**, không phải "mỗi thư viện có một pool riêng". Khi một nhóm công việc chiếm tài nguyên common pool, các nhóm khác phụ thuộc vào nó **có thể** tăng thời gian chờ, dù chúng được khởi tạo bởi API hoàn toàn khác. **Common parallelism** là số lượng worker hoạt động mục tiêu, **không** phải giới hạn cứng số task, số request, số thread đã tạo, hay lời hứa tất cả chương trình sẽ chạy song song đúng bấy nhiêu worker. Không tùy tiện tăng hoặc ép nhỏ common parallelism để "sửa" một tác vụ có blocking I/O; khi cần độc lập về tài nguyên, chủ động chọn `Executor` khác cho workload quan trọng.

## 1. Fork/Join xử lý điều gì?

Fork/Join là mô hình chia bài toán thành các phần có thể xử lý song song và gộp kết quả. `ForkJoinPool` là `ExecutorService` dùng cơ chế **work stealing**: worker có hàng đợi công việc của mình và có thể "lấy trộm" việc từ worker khác khi rảnh. Điều này hữu ích với tác vụ CPU-bound có thể phân rã thành các subtask tương đối ngắn.

Ví dụ một bài toán tính tổng mảng:

```text
                       Sum(1..1000)
                      /             \
               Sum(1..500)       Sum(501..1000)
                  /    \            /    \
                 ...   ...         ...   ...
                      join kết quả
```

Khi một `RecursiveTask` gọi `fork()` để đẩy phần việc, sau đó `join()` để lấy kết quả, pool có thể phân bố các phần việc giữa worker. Mục tiêu là **giảm thời gian xử lý CPU** khi chi phí chia/gộp hợp lý, không phải tăng độ song song vô hạn.

### 1.1. Ba thực thể hay bị nhầm

- `ForkJoinPool`: đối tượng quản lý **tập worker và việc lên lịch**; có thể là common pool hoặc pool riêng do ứng dụng tạo.
- `ForkJoinTask`: đơn vị tính toán mà pool thực thi; các triển khai hay dùng là `RecursiveTask<V>` (trả kết quả) và `RecursiveAction` (không trả kết quả).
- `ForkJoinPool.commonPool()`: trả về một **common pool được chia sẻ**, tồn tại ở cấp JVM (không phải mỗi lời gọi tạo mới).

`ForkJoinPool.commonPool() == ForkJoinPool.commonPool()` là true khi so reference trong cùng JVM. Một `new ForkJoinPool(2)` **khác** common pool, có parallelism riêng, vòng đời riêng và nên được đóng phù hợp khi không còn dùng.

### 1.2. Work stealing không đồng nghĩa tất cả API parallel dùng cùng một executor

Một thư viện **có thể** xây trên ForkJoinPool nhưng tạo pool riêng, thậm chí dùng `ThreadPoolExecutor`, virtual threads hoặc non-blocking event loop thay thế. Từ khóa "parallel" trong tên API **không tự chứng minh** nó dùng common pool.

Cần phân biệt:

1. **Bảo đảm của API** được Javadoc mô tả, ví dụ `CompletableFuture` async không truyền `Executor`.
2. **Hành vi của triển khai JDK thường gặp**, ví dụ parallel stream từ code ứng dụng ngoài Fork/Join worker thường được thực thi qua common pool.
3. **Hành vi thư viện bên thứ ba**, có thể cấu hình executor riêng hoặc thay scheduler giữa các phiên bản.

Không chỉ đoán executor từ tên thread khi chưa kiểm chứng hợp đồng thư viện.

## 2. Common parallelism là gì?

`ForkJoinPool.getCommonPoolParallelism()` trả **mức parallelism mục tiêu** của common pool. `ForkJoinPool.commonPool().getParallelism()` truy vấn mức mục tiêu của chính pool đó.

Trong vận hành thông thường, mức này liên hệ với số CPU JVM coi là khả dụng, cấu hình common pool và phiên bản JDK. Không hard-code công thức "luôn N-1" hoặc "luôn N" cho mọi JVM, container và tình trạng cấu hình. Hãy **đọc giá trị trực tiếp trên tiến trình thật**, vì JVM có thể nhìn thấy CPU quota/CPU count khác với máy chủ vật lý.

Một số khái niệm khác:

| Thông số | Ý nghĩa | Không nên hiểu là |
| --- | --- | --- |
| `Runtime.getRuntime().availableProcessors()` | Số processor khả dụng theo JVM | Số core vật lý tuyệt đối của host |
| `ForkJoinPool.getCommonPoolParallelism()` | Parallelism mục tiêu common pool | Số request tối đa |
| `pool.getParallelism()` | Mục tiêu parallelism của pool | Số thread đang chạy ngay lúc đó |
| `pool.getPoolSize()` | Số worker đã bắt đầu và chưa kết thúc | Số worker đang thực thi code CPU |
| `pool.getRunningThreadCount()` | Ước lượng số worker không bị chặn bởi join/managed sync | Số task đang chờ queue |
| `pool.getActiveThreadCount()` | Ước lượng worker đang chạy hoặc steal task | Số request nghiệp vụ thành công |
| `pool.getQueuedTaskCount()` | Ước lượng task trong worker queues | Tổng mọi task chưa bắt đầu |
| `pool.getQueuedSubmissionCount()` | Ước lượng task submit nhưng chưa chạy | Số task trong worker queues |
| `pool.getStealCount()` | Ước lượng tổng steal đã hoàn tất | Chỉ số throughput hoàn chỉnh |

**Điểm cốt lõi:** Parallelism 4 không có nghĩa chỉ có đúng 4 task được tạo, cũng không bảo đảm luôn chỉ 4 thread tồn tại. Pool có thể dùng worker phụ khi một số worker được nhận diện là đang chặn qua cơ chế hỗ trợ. Ngược lại, số worker có sẵn không tạo thêm CPU vật lý.

### 2.1. Parallelism không phải kích thước hàng đợi

Cấu hình parallelism giới hạn mục tiêu **năng lực worker tích cực**; nó không tự áp một số lượng request tối đa đang được submit. Có thể có rất nhiều task nằm trong hàng đợi, mỗi task tiêu tốn metadata/bộ nhớ và làm latency tăng. Khi cần **admission/backpressure**, phải dùng cơ chế capacity riêng, thay vì coi `getParallelism()` như quota.

### 2.2. Parallelism không phải tốc độ

Tăng từ 4 lên 8 không bảo đảm throughput tăng gấp đôi:

- Máy chỉ có 4 core hữu hiệu thì 8 tác vụ CPU nặng có thể cạnh tranh CPU.
- Code có lock, shared state, memory bandwidth contention, cache miss hoặc GC bottleneck.
- Tác vụ quá nhỏ sẽ tốn phí split/queue/join nhiều hơn công việc thực.
- Tác vụ phụ thuộc I/O và chờ nhiều thì vấn đề chính có thể là resource downstream, không phải CPU.
- Những workload dùng chung common pool tranh chấp nhau.

**Ưu tiên phân loại công việc và đo CPU thực tế** trước khi tuning parallelism.

## 3. Ai có thể dùng common pool trong Java hiện hành?

Nhiều API khác nhau có thể liên quan cùng một tài nguyên:

| Thành phần | Khi nào dùng chung? | Mức bảo đảm cần hiểu |
| --- | --- | --- |
| `ForkJoinPool.commonPool().submit(...)` | Gọi trực tiếp | **Chắc chắn** submit vào common pool |
| `ForkJoinTask.fork()` | Nếu chạy ngoài worker Fork/Join cụ thể | Có cơ chế dùng common pool cho fork từ bên ngoài |
| `CompletableFuture.supplyAsync(supplier)` | Không truyền executor | Mặc định common pool khi pool có parallelism hơn một; có ngoại lệ thấp |
| `CompletableFuture.runAsync(runnable)` | Không truyền executor | Cùng nguyên tắc mặc định |
| `thenApplyAsync(fn)`, `thenCombineAsync(... )` | Không truyền executor | Dùng default async executor của CompletableFuture |
| `parallelStream()` và `stream().parallel()` | Pipeline song song JDK | Thường dùng common pool, nhưng Stream API không cam kết tên executor cụ thể |
| `Arrays.parallelSort(...)` | Mảng đủ lớn để có tác vụ song song | JDK docs nêu rõ sử dụng common pool cho các parallel tasks |
| `Arrays.parallelPrefix(...)` / `parallelSetAll(...)` | Các phép mảng có thể chạy song song | Phụ thuộc triển khai JDK và granularity; kiểm tra Javadoc/runtime |
| `ConcurrentHashMap` bulk `forEach/search/reduce` | Khi `parallelismThreshold` cho phép | Javadoc chỉ rõ các phép parallel computation dùng common pool |
| Thư viện bên thứ ba | Nếu thư viện chọn default FJP / CompletableFuture async | **Không** mặc định mọi thư viện cùng dùng pool; tra hợp đồng và cấu hình của nó |

**Kết quả quan trọng:** Một module A dùng `parallelStream` có thể chịu tác động latency khi module B dùng `CompletableFuture.runAsync` cho một công việc chặn, vì chúng có thể cần worker của cùng pool. Một hàm `Arrays.parallelSort` trên mảng lớn cũng có thể tham gia tranh chấp worker với các phép reduce bulk trên `ConcurrentHashMap` trong chính JVM đó.

Đừng suy ra mọi lời gọi của từng API luôn tạo task thực sự ở worker common pool. Thư viện có thể chọn nhánh **tuần tự** cho dữ liệu nhỏ hoặc thực thi một phần công việc trên **thread caller**. Phải phân biệt **khả năng** sử dụng common pool với **cam kết** mọi element đều được xử lý ở một worker của pool.

## 4. CompletableFuture: Ảnh hưởng mặc định xuyên module

`CompletableFuture` tiêu chuẩn quy định các async method **không nhận `Executor`** chủ yếu dùng `ForkJoinPool.commonPool()`, **nếu pool hỗ trợ hơn một parallel worker**. Trong trường hợp parallelism thấp, triển khai chuẩn sử dụng executor tạo một thread cho mỗi async task. Ở các non-static methods, subclass có thể override `defaultExecutor()` (API từ Java 9+), nên không được khẳng định mọi subclass giống hệt nhau.

Ví dụ:

```java
CompletableFuture<String> fromNetwork =
        CompletableFuture.supplyAsync(
                () -> blockingRemoteCall()); // Không executor!
```

Đây là **phản ví dụ minh họa**, `blockingRemoteCall()` chưa được định nghĩa; không phải chương trình độc lập.

**Rủi ro:**

1. Không có executor được chọn rõ ràng nên tác vụ blocking có thể chiếm worker chung.
2. Thư viện khác đang chạy CPU task trên common pool có thể phải chờ.
3. Một pipeline ngược lại có thể chịu tác động khi parallel stream/parallelSort chạy CPU nặng.
4. Khi `getCommonPoolParallelism() <= 1`, CompletableFuture tiêu chuẩn có thể tạo **thread riêng cho mỗi async task**, không phải "một worker chung". Việc ép parallelism xuống thấp có thể làm số thread tăng bất ngờ.
5. Thay đổi common parallelism là thay đổi tài nguyên **của cả JVM**, không chỉ một service con.

### 4.1. Ba kiểu callback không có cùng hành vi

```java
CompletableFuture<Result> result =
        CompletableFuture.supplyAsync(
                this::fetchBlocking, ioExecutor)
        .thenApply(this::parseTiny)
        .thenApplyAsync(this::cpuHeavy, cpuExecutor);
```

Đây là **minh họa trong một class**, chưa khai báo Result, phương thức hoặc các executor.

- `supplyAsync(..., ioExecutor)` gửi thao tác blocking vào pool I/O riêng.
- `thenApply(...)` **không async**; callback có thể được thực hiện ở thread hoàn tất stage hoặc thread khác đang làm completion. Nó **không** có cam kết luôn chạy trên I/O executor, nhưng cũng **không tự chuyển** sang CPU executor.
- `thenApplyAsync(..., cpuExecutor)` gửi đoạn tính CPU vào executor CPU được chỉ định.
- Nếu viết `thenApplyAsync(this::cpuHeavy)` **không executor**, nó thường trở về default executor/common pool chứ **không thừa kế** ioExecutor một cách mặc định.

### 4.2. Khi callback là blocking I/O

Với HTTP/JDBC blocking, thread của `supplyAsync` có thể bị giữ cho tới khi I/O hoàn tất. Tính "async" ở đây nghĩa là **caller không cần chờ trực tiếp**, không đồng nghĩa API nguồn trở thành non-blocking.

Nếu thư viện đã có API non-blocking trả `CompletableFuture` như `HttpClient.sendAsync` (Java 11+), dùng future do API trả về và chain tiếp thay vì bọc nó trong `supplyAsync(() -> client.sendAsync(...).join())`. Đẩy `join` vào một worker chỉ để chặn chờ future làm tài nguyên worker bị chiếm.

### 4.3. Cross-module starvation

Giả sử thư viện X có 20 lời gọi `CompletableFuture.supplyAsync` chờ các truy vấn chậm; thư viện Y dùng `parallelStream` để tính CPU trên một tập dữ liệu; module Z chạy các phép xử lý mảng song song. Nếu tất cả phụ thuộc vào common pool trong cùng JVM, worker đang đợi có thể giảm worker sẵn sàng phục vụ tính toán Y/Z.

Đây là **nguy cơ chậm/starvation**, không phải lời khẳng định "chắc chắn deadlock" ở mọi JDK. ForkJoinPool có cơ chế bù worker trong một số kiểu chặn được nhận diện, nhưng **không có bảo đảm** bù hết mọi blocked I/O hoặc synchronization bên ngoài.

## 5. Parallel stream: "parallel" không phải "pool dành riêng"

Các biểu thức:

```java
long sum = data.parallelStream()
        .mapToLong(this::calculate)
        .sum();

long other = data.stream()
        .parallel()
        .mapToLong(this::calculate)
        .sum();
```

Đây là **đoạn minh họa trong một class**, `data` và `calculate` chưa được định nghĩa. Cả hai yêu cầu pipeline chạy song song, nhưng API Stream **không cung cấp tham số executor** ở `parallel()` hoặc `parallelStream()`.

Trong JDK thông dụng, parallel stream chạy nhờ Fork/Join và thường liên quan common pool khi caller ở ngoài Fork/Join. Tuy nhiên:

- Spec `java.util.stream` **không cam kết một pool cố định** cho mọi hoàn cảnh.
- Một pipeline bắt đầu bên trong một ForkJoin worker có thể chịu tác động cách triển khai chọn pool đang chạy; **không dựa vào behavior này như API công khai bảo đảm để cách ly**.
- Thread caller có thể thực thi **một phần** của pipeline; đừng assert mọi element được map bởi `ForkJoinPool.commonPool-worker-N`.
- Với số phần tử nhỏ hoặc công việc nhẹ, việc song song có thể **chậm hơn** tuần tự vì chi phí chia/gộp.

### 5.1. Những yêu cầu về lambda của Stream

Hàm mapper/filter/reducer dùng trong parallel stream nên **stateless, non-interfering**, không sửa nguồn dữ liệu đang duyệt khi nguồn không hỗ trợ concurrent mutation. Ví dụ:

```java
List<Integer> output = new ArrayList<>();
data.parallelStream().forEach(output::add); // Sai cho ArrayList.
```

Đây là **phản ví dụ**, `data` chưa khai báo, không phải code an toàn. `ArrayList.add` không thread-safe khi các worker cùng ghi.

Cách đúng thường là một collector phù hợp:

```java
List<Integer> output = data.parallelStream()
        .map(x -> x * 2)
        .toList();
```

Đây là đoạn trong phương thức với `data` kiểu `List<Integer>`; `Stream.toList()` có từ **Java 16+**, nên dùng được ở Java 17+ nhưng **không biên dịch ở Java 8**. Với Java 8, dùng `collect(Collectors.toList())` và không giả định collection kết quả là mutable theo cùng một hợp đồng qua mọi API.

### 5.2. Hàm blocking trong mapper gây gì?

`parallelStream().map(x -> synchronousHttpCall(x))` có thể khiến worker chờ network. Nó thường không phù hợp với mục tiêu Fork/Join CPU-bound, dễ làm chậm cả những công việc khác dùng shared pool. Dùng API I/O phù hợp, executor I/O riêng và **giới hạn số request đồng thời**.

Không chỉ tăng `common.parallelism` để xử lý trường hợp này; việc tăng có thể cho thêm worker nhưng không giải quyết connection pool, rate limit downstream hay memory áp lực.

### 5.3. Nested parallel streams có an toàn không?

Một stream parallel gọi tiếp stream parallel khác có thể tạo nhiều subtask hơn và khiến độ phức tạp scheduling tăng đáng kể. Một số phép inner chỉ chạy ít task, một số có thể tạo tranh chấp. Không mặc định rằng hai cấp song song tạo "parallelism bình phương" hiệu quả.

Trong xử lý dữ liệu lồng nhau, thường nên chọn **một cấp phân tách có đủ granularity**, tránh `parallel()` ở mọi tầng. Việc tính cùng kết quả không có nghĩa hiệu năng tương tự nhau; dùng profiling và benchmark.

## 6. Arrays.parallelSort và parallelPrefix: Không phải module riêng

`Arrays.parallelSort` trong Java 8+ dùng thuật toán sort-merge có thể chia mảng thành các phần rồi sắp xếp/gộp. Javadoc nói rõ **ForkJoin common pool** được dùng để thực thi các parallel tasks; với mảng nhỏ, thuật toán có thể rơi về nhánh tuần tự.

```java
Integer[] values = {8, 1, 5, 3, 2};
Arrays.parallelSort(values);
System.out.println(Arrays.toString(values));
// [1, 2, 3, 5, 8]
```

Đây là đoạn **trong phương thức**, import `java.util.Arrays`. Mảng này quá nhỏ để dùng làm benchmark Fork/Join, nhưng phép sort vẫn đúng.

### 6.1. Vì sao ảnh hưởng đến "thư viện tưởng không liên quan"?

Một module A có thể gọi `Arrays.parallelSort` khi tổng hợp báo cáo; module B khởi chạy `CompletableFuture.supplyAsync` không executor; module C tính `parallelStream`. Nếu các implementation cùng dùng common pool, chúng có thể cạnh tranh worker và cache/CPU. Lỗi hiệu năng xuất hiện ở **module B** nhưng nguyên nhân đến từ lần báo cáo lớn của **module A**.

Không kết luận module B bị chậm do pool chỉ dựa vào một snapshot thread dump. Phải đo queue, CPU, latency và tương quan thời gian của các workload.

### 6.2. Parallel prefix và parallel setAll

`Arrays.parallelPrefix` áp dụng một phép tích lũy song song. Hàm kết hợp nên **associative và không có side effect** theo contract. `Arrays.parallelSetAll` cũng dùng cơ chế thực thi song song cho phép áp dụng generator theo index.

**Cẩn thận phép cộng số thực:** Floating-point không thật sự associative theo toán học trên số thực vì có rounding theo thứ tự, nên các phép prefix/reduction song song `double` có thể khác kết quả tuần tự một lượng nhỏ. Không lấy sai khác đó làm bằng chứng common pool làm hỏng dữ liệu; nó là ràng buộc của phép toán dấu phẩy động và thứ tự kết hợp.

## 7. ConcurrentHashMap bulk operations cũng góp tải lên common pool

`ConcurrentHashMap` có các phép bulk:

- `forEach(parallelismThreshold, action)` và các overload có transformer.
- `search(parallelismThreshold, searchFunction)`.
- `reduce...(...)`, `reduceValuesToInt`, `reduceEntries` và các overload.

Các method này nhận `parallelismThreshold` — ngưỡng **ước lượng số phần tử** để lựa chọn triển khai tuần tự hoặc chia subtask:

- `Long.MAX_VALUE`: **ngăn parallelism** đối với phép bulk này.
- `1`: khuyến khích parallelism tối đa theo cơ chế của phép bulk, nếu dữ liệu/tài nguyên cho phép.
- Một ngưỡng trung gian: đánh đổi overhead với throughput.

Javadoc của `ConcurrentHashMap` xác nhận common pool được dùng cho các tính toán song song trong nhóm bulk operations. **Ngưỡng này không phải số worker**; `parallelismThreshold=1` không có nghĩa "chạy một thread", mà là ngưỡng số entry để bắt đầu chia việc.

### 7.1. Ví dụ: Tính tổng giá trị có ngưỡng 1

```java
ConcurrentHashMap<String, Integer> values =
        new ConcurrentHashMap<>();
values.put("a", 2);
values.put("b", 3);
values.put("c", 4);

int total = values.reduceValuesToInt(
        1,
        Integer::intValue,
        0,
        Integer::sum);
// total == 9
```

Đây là đoạn trong phương thức, import `java.util.concurrent.ConcurrentHashMap`. `basis=0` là identity cho phép cộng; `Integer::sum` associative và commutative với toán `int` modulo 2^32, phù hợp cho phần demo không overflow.

### 7.2. Chạy song song không có snapshot nguyên tử toàn map

`ConcurrentHashMap` cho phép cập nhật đồng thời khi bulk operation chạy; một lần `reduce` không nhất thiết đại diện cho một snapshot **nguyên tử toàn map** nếu các writer vẫn thay đổi entries. `parallelismThreshold` chỉ điều chỉnh cách phân tách công việc, **không** biến phép reduce thành giao dịch snapshot.

Nếu cần một tổng kiểm toán chặt khi có writer đồng thời, phải tổ chức đồng bộ/snapshot theo yêu cầu domain. `reduceValuesToLong(1,...)` không tự bảo đảm kết quả cuối đồng nhất với một thời điểm tuyến tính hóa của toàn map.

### 7.3. Không dùng threshold để "cách ly khỏi thư viện khác"

Một thư viện gọi `ConcurrentHashMap.forEach(1, ...)` có thể sử dụng common pool. Đổi threshold lên `Long.MAX_VALUE` giúp bỏ phần chia song song của phép bulk đó, nhưng **không cô lập mọi lời gọi** của ứng dụng và không thay thế thiết kế executor. Chọn threshold dựa trên map size, cost mỗi entry, CPU availability và benchmark.

## 8. Chương trình Java 17+: Nhiều API cùng tính kết quả

Tạo file **`CommonPoolConsumersDemo.java`**:

```java
import java.util.Arrays;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ForkJoinPool;
import java.util.stream.IntStream;

public class CommonPoolConsumersDemo {
    public static void main(String[] args) {
        ForkJoinPool common = ForkJoinPool.commonPool();

        System.out.println("Same common instance: "
                + (common == ForkJoinPool.commonPool()));

        CompletableFuture<Integer> future =
                CompletableFuture.supplyAsync(() -> 21)
                        .thenApplyAsync(n -> n * 2);
        System.out.println("CF result: " + future.join());

        int parallelSum = IntStream.rangeClosed(1, 1_000)
                .parallel()
                .sum();
        System.out.println("Parallel sum: " + parallelSum);

        Integer[] numbers = {8, 1, 5, 3, 2};
        Arrays.parallelSort(numbers);
        System.out.println("Sorted: " + Arrays.toString(numbers));

        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();
        map.put("a", 2);
        map.put("b", 3);
        map.put("c", 4);

        int mapSum = map.reduceValuesToInt(
                1, Integer::intValue, 0, Integer::sum);
        System.out.println("Map bulk sum: " + mapSum);

        int taskResult = common.submit(() -> 7).join();
        System.out.println("Task result: " + taskResult);
    }
}
```

Chạy:

```bash
javac --release 17 CommonPoolConsumersDemo.java
java CommonPoolConsumersDemo
```

**Stdout:**

```text
Same common instance: true
CF result: 42
Parallel sum: 500500
Sorted: [1, 2, 3, 5, 8]
Map bulk sum: 9
Task result: 7
```

**Cách diễn giải đúng:**

1. Hai lời gọi `ForkJoinPool.commonPool()` trả cùng một đối tượng pool trong JVM.
2. `CompletableFuture.supplyAsync/thenApplyAsync` không truyền executor, nên dùng cơ chế default executor được Javadoc mô tả; không kiểm tra tên worker vì cấu hình parallelism rất thấp có thể kích hoạt fallback.
3. `IntStream` tính tổng 1..1000 bằng 500500, kết quả toán học không phụ thuộc thứ tự task; việc stream song song có dùng bao nhiêu worker là đặc tính thực thi, không được kiểm định ở stdout này.
4. `Arrays.parallelSort` có thể dùng common pool khi thực sự chia mảng; mảng demo nhỏ có thể sort tuần tự.
5. `ConcurrentHashMap.reduceValuesToInt(1,...)` có cùng con số 9; việc thiếu/lệch snapshot dưới concurrent writer không xảy ra vì demo không có writer đồng thời.
6. `common.submit(() -> 7)` **chắc chắn** submit vào pool đó.
7. Không có lời gọi nào in thứ tự lên lịch, thread ID hoặc số processor; đó là lý do stdout **xác định** trên môi trường JDK 17+ thông thường.

Demo chứng minh một số API và kết quả tương ứng, **không** phải benchmark về contention/common pool hay bằng chứng mọi operation luôn dùng một worker common pool.

## 9. Tác động chéo: Shared pool có thể bị chiếm bởi blocking

ForkJoinPool được tối ưu cho công việc có thể fork/join hiệu quả. Trong một ứng dụng phục vụ request, sai lầm thường thấy là đặt tác vụ network/DB/đọc stream blocking vào một async stage không chỉ định executor.

Ví dụ kiến trúc nguy hiểm:

```java
CompletableFuture<Data> a =
        CompletableFuture.supplyAsync(
                () -> jdbcRepository.load(id));

CompletableFuture<Summary> b =
        CompletableFuture.supplyAsync(
                () -> cpuHeavyReport());
```

Đây là **mã minh họa thiếu các khai báo**, không phải chương trình độc lập. Hai `supplyAsync` đều chọn default async executor. Nếu phía JDBC chờ connection hoặc socket trong thời gian dài, phần báo cáo CPU có thể phải cạnh tranh worker với các task khác.

### 9.1. Thread starvation là gì?

**Starvation** xảy ra khi một nhóm công việc không nhận đủ thời gian thực thi/tài nguyên trong thời gian cần thiết, dù bản thân chúng sẵn sàng chạy. Nó khác với **deadlock**: deadlock là một vòng chờ không thể tự tiến triển; starvation có thể chỉ là chờ quá lâu.

Kịch bản có thể xảy ra:

```text
common pool target parallelism = P
        |
        +-- nhiều task A chờ blocking I/O
        +-- CPU stage B chuẩn bị chạy
        +-- parallel stream C chia việc
        +-- Arrays.parallelSort D submit task
        |
        V
active CPU capacity giảm / queue wait tăng
        |
        +-- latency của B/C/D tăng dù code không đổi
```

Sơ đồ là **mô hình rủi ro**, không phải mô tả luật scheduling cố định cho mọi JDK. Nhiều kiểu join/managed blocking có thể được pool bù worker, nên không thể khẳng định một blocking task luôn giữ vĩnh viễn đúng một trong P worker.

### 9.2. Cơ chế bù worker và ManagedBlocker

`ForkJoinPool` có thể nhận biết một số trường hợp worker bị chặn bởi join hoặc `ForkJoinPool.ManagedBlocker` và bổ sung worker để duy trì parallelism. `ForkJoinPool.managedBlock(blocker)` cho phép khai báo một hoạt động có thể chặn theo hợp đồng `ManagedBlocker`.

**Nhưng:**

- Việc bù worker là khả năng runtime, **không** phải lời hứa mọi wait/blocked I/O đều được bù.
- Javadoc cảnh báo không bảo đảm điều chỉnh phù hợp khi gặp I/O chặn hoặc đồng bộ unmanaged.
- Worker bổ sung không tạo thêm CPU vật lý; nó giúp tránh để CPU rảnh khi có tác vụ đang chờ.
- Cấu hình giới hạn worker spare và tài nguyên JVM có thể hạn chế bù.
- Việc thêm work-stealing/managedBlock vào mọi nơi **không thay thế timeout và backpressure** đối với DB/network.

Trong thiết kế dịch vụ, thường tốt hơn khi **không sử dụng common pool cho blocking I/O kéo dài**, thay vì cố cứu bằng managedBlock nếu có thể phân tách executor ngay từ đầu.

### 9.3. `join()` có thể giúp hoặc gây rủi ro?

Trong Fork/Join thuần CPU, `RecursiveTask.join()` có cơ chế phối hợp nhằm tránh chờ vô ích khi một worker có thể thực thi công việc khác. Nhưng nếu một task chạy trong executor nhỏ **submit một task con vào chính executor đó rồi dùng blocking wait mà scheduler không giải quyết được**, có thể gây starvation hoặc deadlock.

Không viết kết luận "mọi `join` đều deadlock" — đó là sai. Hãy phân biệt `RecursiveTask.fork()/join()` trong thuật toán chia để trị với `CompletableFuture.join()` dùng để block một thread chờ I/O/future phụ thuộc. Với CompletableFuture, ưu tiên `thenCompose`/`thenCombine` thay cho callback tạo task con rồi chặn đợi kết quả.

## 10. Cách ly bằng Executor tường minh: Chiến lược thực tế

Mục tiêu khi tách pool là tránh để **một dependency chậm** chiếm trực tiếp worker của **nhóm tính CPU quan trọng**. Với CompletableFuture:

```java
CompletableFuture<Data> loaded =
        CompletableFuture.supplyAsync(
                () -> blockingLoad(), ioExecutor);

CompletableFuture<Result> calculated =
        loaded.thenApplyAsync(
                data -> cpuTransform(data), cpuExecutor);
```

Đây là **mẫu kiến trúc** có các phương thức/kiểu giả định, không chạy độc lập.

- `ioExecutor`: nhóm phục vụ blocking I/O, chọn số worker theo số connection/downstream capacity, có queue/cơ chế admission rõ.
- `cpuExecutor`: nhóm dành cho công việc CPU; chọn parallelism theo CPU khả dụng và đo đạc thực tế.
- `thenApplyAsync(..., cpuExecutor)`: chuyển stage CPU nặng sang executor CPU đúng chủ ý.
- Nếu `thenComposeAsync(..., cpuExecutor)` trả một future I/O, future I/O **không tự chuyển** thành CPU work; stage bên trong vẫn theo executor của chính nó.
- Callback nhỏ như đổi tên một trường có thể dùng `thenApply` non-async để tránh overhead; không ép tất cả stage async bằng mọi giá.

### 10.1. Đây là cách ly về scheduling, không phải CPU vật lý tuyệt đối

Hai executor **vẫn chia sẻ CPU, RAM, GC, network và DB** của JVM/máy. Pool riêng giúp không trực tiếp nhốt worker của nhóm CPU trong một lệnh I/O blocking, nhưng nếu cả hai nhóm cùng ngốn CPU hoặc cấp phát quá mạnh, chúng vẫn ảnh hưởng nhau.

Khi cần SLA/priority thật sự khác nhau, ngoài executor riêng còn có thể phải tính tới admission, thread priority policy, process/container isolation và kiểm soát tài nguyên downstream.

### 10.2. Không tạo executor mới cho từng request

`Executors.newFixedThreadPool(4)` trong mỗi request sẽ tạo thêm nhóm worker và queue, tăng gánh bộ nhớ cũng như khó shutdown. Hãy quản lý pool theo vòng đời service hoặc module, có giới hạn và observability. Số worker 4 chỉ là **giá trị minh họa**, không thể áp mọi ứng dụng.

### 10.3. Fixed thread pool có hàng đợi mặc định không giới hạn

`Executors.newFixedThreadPool(n)` tạo pool có số worker cố định, nhưng queue mặc định có thể chứa rất nhiều task. Nếu service tiếp nhận tải vô hạn, việc "có pool riêng" **không đủ** để tránh queue growth/OOM/latency.

Cân nhắc `ThreadPoolExecutor` với `ArrayBlockingQueue` bounded, `RejectedExecutionHandler` hoặc semaphore/rate limiter/admission control. Khi queue đầy, trả lỗi quá tải rõ ràng thay vì âm thầm tích task hoặc làm event-loop thread bị kéo vào I/O blocking qua `CallerRunsPolicy`.

## 11. Java 17+ runnable: I/O đang chờ, CPU vẫn tiến triển

Tạo file **`IsolatedExecutorStagesDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class IsolatedExecutorStagesDemo {
    static String simulatedBlockingIo(
            CountDownLatch started,
            CountDownLatch release) {
        started.countDown();

        try {
            release.await();
            return "loaded";
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", ex);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService io = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "io-worker"));
        ExecutorService cpu = Executors.newSingleThreadExecutor(
                task -> new Thread(task, "cpu-worker"));

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> blocked =
                    CompletableFuture.supplyAsync(
                            () -> simulatedBlockingIo(
                                    started, release),
                            io);

            started.await();

            CompletableFuture<Integer> fastCpu =
                    CompletableFuture.supplyAsync(
                            () -> 21 * 2, cpu);

            System.out.println("CPU while IO waits: "
                    + fastCpu.get(3, TimeUnit.SECONDS));

            release.countDown();
            System.out.println("IO result: " + blocked.join());

            CompletableFuture<String> routed =
                    CompletableFuture.supplyAsync(
                            () -> Thread.currentThread()
                                    .getName(), io)
                            .thenApplyAsync(
                                    first -> first + " -> "
                                            + Thread.currentThread()
                                                    .getName(),
                                    cpu);

            System.out.println("Route: " + routed.join());
        } finally {
            release.countDown();
            io.shutdown();
            cpu.shutdown();
            io.awaitTermination(3, TimeUnit.SECONDS);
            cpu.awaitTermination(3, TimeUnit.SECONDS);
        }
    }
}
```

Chạy:

```bash
javac --release 17 IsolatedExecutorStagesDemo.java
java IsolatedExecutorStagesDemo
```

**Stdout khi máy cấp thời gian chạy bình thường:**

```text
CPU while IO waits: 42
IO result: loaded
Route: io-worker -> cpu-worker
```

Đoạn `fastCpu.get(3, TimeUnit.SECONDS)` tạo **deadline bảo vệ test**: trên máy quá tải bất thường, chương trình có thể ném `TimeoutException` thay vì in dòng đầu. Đây là hạn chế hợp lý của test concurrency có deadline, không phải một guarantee về thời gian hoàn thành ở mọi máy.

**Tại sao ví dụ hữu ích:**

1. Latch `started` xác nhận thread I/O đã bước vào hàm chờ.
2. Lúc đó một task CPU vẫn được gửi vào executor khác, không cần đợi thread I/O trả về.
3. `release` chỉ mở **sau khi** kết quả CPU được lấy, nên minh họa rõ isolation về worker.
4. Pipeline `routed` gửi supplier vào executor I/O và continuation CPU vào executor CPU; tên thread chỉ dùng để kiểm tra sự lựa chọn executor, không dùng làm request ID.
5. `finally` mở latch dù có exception, dừng pools và chờ có hạn để không giữ JVM chạy mãi.
6. `CountDownLatch.await` chỉ là **mô phỏng chờ**, không đại diện cho throughput của HTTP/JDBC thật.

**Không dùng demo này để kết luận tách pool sẽ làm mọi ứng dụng nhanh hơn.** Nó kiểm chứng một tính chất scheduling cụ thể; hiệu năng phải đo bằng load test và số liệu môi trường thật.

## 12. Tự tạo ForkJoinPool riêng cho thuật toán chia để trị

Nếu thư viện hoặc ứng dụng triển khai trực tiếp thuật toán `RecursiveTask`, có thể tạo pool riêng với parallelism tường minh:

```java
ForkJoinPool reportPool = new ForkJoinPool(2);

try {
    long result = reportPool.invoke(
            new SumTask(1, 1_001));
} finally {
    reportPool.shutdown();
}
```

Đây là đoạn trong class có `SumTask` (sẽ được định nghĩa ở ví dụ đầy đủ bên dưới). `2` là parallelism của **pool riêng**, không đụng global common pool. Với thuật toán có task CPU vừa phải và đủ lớn, cách này cho phép cách ly lịch thực thi khỏi các lời gọi `CompletableFuture` mặc định.

### 12.1. Khi nào nên tạo pool riêng?

Một số lý do hợp lý:

- Báo cáo CPU nặng cần mức parallelism hoặc SLA khác workload thường.
- Muốn đo đạc/giới hạn riêng luồng công việc Fork/Join.
- Có các phép `RecursiveTask` phân rã sâu và chi phí lớn.
- Muốn kiểm soát lifecycle của pool theo ứng dụng.
- Không muốn một mô-đun dùng shared pool cho cả các service khác.

Không tạo **hàng trăm pool riêng** vì sẽ gây oversubscription CPU và chi phí quản lý lớn; pool riêng không miễn phí.

### 12.2. Tại sao không ép parallel stream chạy trên private ForkJoinPool bằng mẹo?

Có những ví dụ đặt `parallelStream` bên trong `privatePool.submit(() -> ...).join()` và quan sát nó dùng worker của privatePool ở một số JDK. Tuy nhiên, API Stream **không cung cấp executor parameter** và không cam kết cách chọn pool khi được gọi từ một ForkJoin worker. Đây có thể là behavior của implementation, **không nên dựa vào để cung cấp isolation như một API contract dài hạn**.

Khi yêu cầu chính là **control executor**, hãy ưu tiên API có tham số `Executor`, hoặc tự dùng `RecursiveTask`/`ForkJoinPool` cho thuật toán chia để trị, hoặc chọn thư viện parallel processing công bố scheduler tường minh. Đừng viết test dựa vào tên thread rồi xem đó là hợp đồng của `parallelStream`.

## 13. Java 17+ runnable: RecursiveTask trên pool riêng

Tạo file **`PrivateForkJoinPoolDemo.java`**:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class PrivateForkJoinPoolDemo {
    static final class SumTask extends RecursiveTask<Long> {
        private final int from;
        private final int toExclusive;

        SumTask(int from, int toExclusive) {
            this.from = from;
            this.toExclusive = toExclusive;
        }

        @Override
        protected Long compute() {
            if (toExclusive - from <= 100) {
                long sum = 0;
                for (int n = from; n < toExclusive; n++) {
                    sum += n;
                }
                return sum;
            }

            int middle = (from + toExclusive) >>> 1;
            SumTask left = new SumTask(from, middle);

            left.fork();
            long right = new SumTask(
                    middle, toExclusive).compute();

            return left.join() + right;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool privatePool = new ForkJoinPool(2);

        try {
            System.out.println("Private parallelism: "
                    + privatePool.getParallelism());
            System.out.println("Different from common: "
                    + (privatePool != ForkJoinPool.commonPool()));
            System.out.println("Private sum: "
                    + privatePool.invoke(
                            new SumTask(1, 1_001)));
        } finally {
            privatePool.shutdown();
        }
    }
}
```

Chạy:

```bash
javac --release 17 PrivateForkJoinPoolDemo.java
java PrivateForkJoinPoolDemo
```

**Stdout:**

```text
Private parallelism: 2
Different from common: true
Private sum: 500500
```

**Giải thích:**

- `new ForkJoinPool(2)` tạo pool riêng với target 2.
- `privatePool != ForkJoinPool.commonPool()` là true vì đó là hai instance.
- `SumTask` tách tổng 1..1000 thành các đoạn, tính phần phải trong worker hiện tại, `fork` phần trái và `join` kết quả; tổng cuối là 500500.
- `shutdown` chỉ dừng pool riêng. Không gọi `shutdown` của common pool với hy vọng giải phóng toàn bộ công việc async của ứng dụng.
- Mốc chia 100 là **ngưỡng minh họa**; thực tế phải chọn theo kích thước bài toán và overhead, không dùng 100 như hằng tối ưu trong production.

### 13.1. Fork/Join không phù hợp với mọi loại tác vụ

Nếu mỗi subtask gọi API blocking hoặc giữ lock dài, ưu thế work stealing có thể bị hạn chế. Với I/O blocking, chọn executor I/O/virtual threads thích hợp; với CPU chia để trị, ForkJoinPool riêng có thể hợp lý. Đừng thay một `ThreadPoolExecutor` đang quản lý queue/backpressure tốt bằng ForkJoinPool chỉ vì tên "Fork/Join" nghe nhanh hơn.

## 14. Kiểm thử parallel stream, prefix và side effects đúng cách

Một test kiểu:

```java
stream.parallel().forEach(
        x -> nonThreadSafeList.add(x));
```

là một anti-pattern nếu list không đồng bộ. Khi nhiều worker thêm, có thể mất phần tử hoặc hỏng state; lỗi này thuộc shared mutable state, không phải do "common parallelism quá nhỏ".

**Thực hành đúng:** Sử dụng phép map/reduce/collect với hàm stateless và associative khi cần kết quả xác định, rồi kiểm chứng expected độc lập.

### 14.1. Java 17+ runnable: Kết quả độc lập thứ tự scheduling

Tạo file **`SafeParallelOperationsDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

public class SafeParallelOperationsDemo {
    public static void main(String[] args) {
        long sumOfSquares =
                IntStream.rangeClosed(1, 1_000)
                        .parallel()
                        .mapToLong(x -> (long) x * x)
                        .sum();

        List<Integer> doubled =
                IntStream.rangeClosed(1, 5)
                        .parallel()
                        .map(x -> x * 2)
                        .boxed()
                        .toList();

        int[] prefix = {2, 1, 0, 3};
        Arrays.parallelPrefix(prefix, Integer::sum);

        System.out.println("Squares: " + sumOfSquares);
        System.out.println("Doubled: " + doubled);
        System.out.println("Prefix: " + Arrays.toString(prefix));
    }
}
```

Chạy:

```bash
javac --release 17 SafeParallelOperationsDemo.java
java SafeParallelOperationsDemo
```

**Stdout:**

```text
Squares: 333833500
Doubled: [2, 4, 6, 8, 10]
Prefix: [2, 3, 3, 6]
```

**Vì sao xác định:** Công thức tổng bình phương 1..1000 cho 333833500, không overflow `long`. `IntStream.rangeClosed` là nguồn **có encounter order**; `toList()` giữ encounter order khi nguồn có thứ tự theo hợp đồng. `Arrays.parallelPrefix` với phép cộng `int` cho prefix sum cố định với dữ liệu nhỏ. Không có shared mutable `ArrayList.add` bên trong mapper.

Nếu dùng `forEach`, thứ tự action không được bảo đảm khi pipeline parallel; `forEachOrdered` có thể bảo toàn thứ tự encounter khi yêu cầu, nhưng có thể thêm synchronization/giảm throughput. Đừng ép thứ tự khi logic thật sự không cần.

## 15. Cấu hình common parallelism: Toàn JVM chứ không phải mỗi thư viện

Một system property lịch sử và vẫn được JDK hỗ trợ:

```text
java.util.concurrent.ForkJoinPool.common.parallelism
```

Có thể truyền khi khởi động JVM, ví dụ:

```bash
java -Djava.util.concurrent.ForkJoinPool.common.parallelism=2 CommonParallelismProbe
```

Với **JDK 17** và những phiên bản trước JDK 19, đây là một trong các cơ chế cấu hình common pool. Nhưng trong **Javadoc JDK 26 hiện hành**, việc dùng system property này được ghi là **không khuyến khích**, và API `ForkJoinPool.setParallelism(int)` được nêu như lựa chọn điều chỉnh target parallelism (được bổ sung từ **Java 19**). **Không gọi `setParallelism` từ chương trình biên dịch `--release 17`**, vì API chưa tồn tại trong target đó.

**Điều không nên làm:** Trong một library dùng chung, tùy tiện đổi cấu hình common pool của cả JVM chỉ để đẩy nhanh một bộ phận. Việc này có thể thay đổi scheduling/throughput/latency của `CompletableFuture`, parallel stream, `Arrays.parallelSort`, CHM bulk và mã ứng dụng khác.

### 15.1. Một vài thuộc tính khác từ Javadoc ForkJoinPool

JDK hiện hành còn hỗ trợ những system property liên quan cấu hình common pool:

| Thuộc tính | Ý nghĩa tóm tắt |
| --- | --- |
| `java.util.concurrent.ForkJoinPool.common.parallelism` | Target parallelism của common pool; JDK 26 khuyên tránh dùng nếu có thể |
| `java.util.concurrent.ForkJoinPool.common.threadFactory` | Class thực hiện `ForkJoinWorkerThreadFactory` cho common pool |
| `java.util.concurrent.ForkJoinPool.common.exceptionHandler` | Handler cho lỗi không bắt được ở worker |
| `java.util.concurrent.ForkJoinPool.common.maximumSpares` | Giới hạn số worker phụ khi cần giữ target parallelism; JDK 26 mô tả giá trị mặc định 256 |

**Không coi `maximumSpares=256` là lời hứa JVM luôn tạo 256 worker phụ**; đây là giới hạn theo thiết kế JDK, còn việc tạo worker phụ phụ thuộc điều kiện wait, resource và thuật toán runtime.

Đừng set property về parallelism=0 để cố "tắt" mọi tác vụ async. Javadoc cảnh báo mạnh vì một số tác vụ có thể không thực thi như kỳ vọng, và implementation có thể có hành vi đặc biệt đối với intrinsically async tasks.

### 15.2. API `setParallelism` chỉ dành cho JDK 19+

Trong mã Java 19+ có thể truy cập:

```java
ForkJoinPool common = ForkJoinPool.commonPool();
int previous = common.setParallelism(newTarget);
```

Đây là **đoạn minh họa trong phương thức cho JDK 19+**, không chạy độc lập: `newTarget` chưa khai báo. Theo JDK 26 Javadoc, `setParallelism(int)` điều chỉnh target parallelism cho việc tạo/sử dụng/kết thúc worker tương lai; có thể ném `UnsupportedOperationException` nếu common pool đã được cấu hình parallelism qua system property, và ném `IllegalArgumentException` cho tham số không hợp lệ.

Vì thay đổi này ảnh hưởng **toàn common pool**, hãy chỉ gọi tại vị trí cấu hình/vận hành có quyền điều phối toàn ứng dụng, có số liệu đo và rollback. Không thay đổi giữa request hoặc test độc lập nếu test có thể chạy song song với code khác trong cùng JVM.

### 15.3. Đặt property khi nào?

System property dùng để thiết lập common pool được đọc khi pool được khởi tạo. Đừng gọi `System.setProperty(..., "8")` sau khi thư viện đã dùng common pool rồi kỳ vọng worker lập tức đổi target; đây không phải cơ chế đổi config đáng tin cậy. Để kiểm thử property ở JVM mới, truyền `-D...` **khi khởi động**, không ở giữa chương trình.

### 15.4. Parallelism = 1 và CompletableFuture đặc biệt

Trong `CompletableFuture` tiêu chuẩn, default async executor có thể sử dụng **một thread mới cho mỗi task async** khi common pool không hỗ trợ hơn một parallel worker. Do đó hạ common parallelism xuống 1 **không đồng nghĩa** mọi `CompletableFuture.supplyAsync` sẽ chạy tuần tự trong một worker.

Một chương trình có thể chuyển từ worker share chung sang phát sinh thread-per-task khi cấu hình thấp; số thread, memory pressure và behavior latency có thể đổi đáng kể. Đây là lý do không sử dụng parallelism thấp như một dạng concurrency limit cho dịch vụ.

## 16. Java 17+ runnable: In cấu hình thực tế của JVM

Tạo file **`CommonParallelismProbe.java`**:

```java
import java.util.concurrent.ForkJoinPool;

public class CommonParallelismProbe {
    public static void main(String[] args) {
        ForkJoinPool pool = ForkJoinPool.commonPool();

        System.out.println("Available CPUs: "
                + Runtime.getRuntime().availableProcessors());
        System.out.println("Common parallelism: "
                + ForkJoinPool.getCommonPoolParallelism());
        System.out.println("Pool target: "
                + pool.getParallelism());

        String configured = System.getProperty(
                "java.util.concurrent.ForkJoinPool.common.parallelism",
                "<unset>");
        System.out.println("Property: " + configured);

        System.out.println("Pool size now: " + pool.getPoolSize());
        System.out.println("Active estimate: "
                + pool.getActiveThreadCount());
        System.out.println("Queued submissions estimate: "
                + pool.getQueuedSubmissionCount());
    }
}
```

Chạy:

```bash
javac --release 17 CommonParallelismProbe.java
java CommonParallelismProbe
java -Djava.util.concurrent.ForkJoinPool.common.parallelism=2 CommonParallelismProbe
```

**Đầu ra có số động theo máy/JVM**, ví dụ một máy có nhiều CPU và chưa có task nào:

```text
Available CPUs: <số CPU mà JVM nhìn thấy>
Common parallelism: <target>
Pool target: <target>
Property: <unset> hoặc giá trị khởi động
Pool size now: <số worker đã tạo>
Active estimate: <ước lượng>
Queued submissions estimate: <ước lượng>
```

Khối trên là **mẫu định dạng đầu ra**, không phải stdout cố định, vì tài nguyên của mỗi máy/container và lịch sử sử dụng common pool khác nhau. Nếu chạy với `-D...=2`, trong môi trường hỗ trợ cấu hình này đúng như JDK mô tả, dòng `Property` là `2`; các số khác cần đọc trực tiếp, không hard-code.

**Không so sánh "Pool size now" với "Common parallelism" rồi kết luận lỗi nếu khác.** Pool có thể chưa tạo worker hoặc có worker bổ sung. Các số active/queue là thông tin quan sát tại một thời điểm, không phải test correctness.

## 17. Quan sát và chẩn đoán common pool bị nghẽn

Nếu latency đột nhiên tăng ở nhiều module khi workload tăng, hãy phân tích theo nhiều lớp:

### 17.1. Chỉ số ForkJoinPool

| Chỉ số | Dùng để phân tích | Giới hạn |
| --- | --- | --- |
| `getParallelism()` | Target của common pool | Không biểu thị actual threads |
| `getPoolSize()` | Số worker tồn tại | Có thể khác target |
| `getRunningThreadCount()` | Worker đang không bị chặn trong join/managed sync | Chỉ là ước lượng |
| `getActiveThreadCount()` | Worker đang active/steal | Có thể overestimate |
| `getQueuedSubmissionCount()` | Task submit từ ngoài chưa bắt đầu | Ước lượng, không phải tất cả task |
| `getQueuedTaskCount()` | Task chờ trong worker deques | Không gồm external submissions |
| `getStealCount()` | Số task bị worker khác steal đã hoàn thành | Không tự là chứng minh pool tối ưu |
| `isQuiescent()` | Pool dường như đang rảnh | Có thể chưa phản ánh ngay lập tức |
| `pool.toString()` | Thông tin snapshot cho chẩn đoán nhanh | Không phải giao diện metric cam kết format ổn định |

Đừng chọn **một** chỉ số như steal count cao/thấp để kết luận tốt/xấu. Một giá trị steal cao có thể cho thấy thuật toán phân tách hợp lý, hoặc chỉ là nhiều task nhỏ; cần kết hợp throughput, queue wait, CPU và workload.

### 17.2. JFR và thread dump

Trong Java hiện hành, có thể dùng **Java Flight Recorder (JFR)**, thread dumps và profiling để tìm:

- Worker đang ở mã CPU hay đợi `SocketInputStream`/JDBC/lock.
- Task có thời gian chạy quá dài so với granularity của pool.
- Số lượng worker và các điểm chờ `CompletableFuture.join/get`.
- CPU saturation/GC và memory allocation khi tạo quá nhiều task.
- Tương quan giữa peak batch `parallelSort`/parallel stream với latency request async.

Thực hành tốt: **gắn nhãn workload** ở tầng application metrics/log/tracing để biết tác vụ nào do module nào submit. Tên mặc định của common worker là gợi ý, nhưng **không phải bằng chứng chắc chắn** toàn bộ code cùng một nguồn; thread có thể được đổi tên/custom factory và callback non-async có thể chạy trên caller.

### 17.3. Không nhầm "pool hết thread" với "host hết CPU"

- **Nhiều worker blocked và CPU rảnh:** có thể là starvation do blocking I/O, lock hoặc dependency.
- **CPU bão hòa, worker chạy đầy:** tăng parallelism có thể làm contention lớn hơn; tối ưu thuật toán/giảm task, giới hạn input.
- **Queue tăng còn CPU rảnh:** có thể do target quá thấp, phụ thuộc bị chặn hoặc cách submit/task granularity sai.
- **Latency tăng nhưng pool rảnh:** nguyên nhân có thể nằm ở network/database, GC, request admission hoặc nơi khác.

Vì common pool dùng chung, cần nhìn **toàn JVM**, không chỉ thread dump của một module.

## 18. Lifecycle và tính chất daemon của common pool

`ForkJoinPool.commonPool()` có vòng đời gắn với JVM, không phải pool riêng do một component tạo và sở hữu.

- `commonPool().shutdown()` và `shutdownNow()` **không làm thay đổi trạng thái hoạt động** của common pool theo Javadoc. Không dùng chúng như cách "dừng thư viện X" hoặc "reset pool".
- `ForkJoinPool` hiện hành khởi tạo workers là **daemon threads**; một tác vụ async đang chạy không đủ giữ JVM tiếp tục sống nếu main thread kết thúc và không còn non-daemon threads. Với CLI batch/job, phải chủ động chờ kết quả hoặc `awaitQuiescence` theo contract trước khi kết thúc tiến trình.
- `System.exit(...)` kết thúc JVM; công việc common pool đang chạy không được tự động bảo đảm hoàn tất trước exit.
- Pool **riêng** phải có lifecycle đóng/`shutdown`/`awaitTermination` phù hợp. Với Java 19+ có thể dùng `ExecutorService.close()`, nhưng các ví dụ Java 17 ở đây dùng `shutdown` để tương thích.

### 18.1. Đừng để unit test chung làm ô nhiễm application process

Một unit test tạo hàng nghìn task blocking trên common pool có thể khiến test khác trong cùng JVM chậm hoặc flaky. Tốt hơn dùng executor được tạo riêng cho mỗi test (và đóng nó), kết quả/latch có thời hạn, không làm giả định về số common worker.

Tương tự, đừng set system property thay đổi common pool ngay giữa nhiều test trong một JVM: một số code đã khởi tạo pool, một số chưa, dẫn đến kết quả khó tái lập. Nếu bắt buộc test cấu hình khởi động, chạy từng trường hợp trên **JVM mới**.

## 19. Thư viện bên thứ ba: Kiểm chứng trước khi tuning

Một library framework có thể:

1. Gọi `CompletableFuture.supplyAsync` không truyền executor, từ đó dùng default.
2. Khai báo một `Executor` hoặc scheduler riêng cho operations của nó.
3. Dùng Reactor/Rx/event loop/asynchronous HTTP client có thread model khác.
4. Dùng các parallel stream hoặc phép mảng song song trong nội bộ.
5. Trả `CompletionStage` đã được hoàn thành nhờ event loop, nhưng callback không-async do caller hoàn thành stage.
6. Dùng thread pool có giới hạn theo cấu hình framework mà thư viện tự quản lý.

Không nói chung "mọi thư viện Java tự động share commonPool" — **sai**. Cách tra cứu tốt là đọc docs cấu hình executor/scheduler, kiểm tra code path thực (profiling, thread dump, test staging), rồi đo tương quan latency.

### 19.1. Tác động lan truyền thường khó nhìn thấy

Ví dụ service A triển khai logging/batch report bằng `parallelStream`, service B dùng `CompletableFuture` default để xử lý kết quả, service C dùng `Arrays.parallelSort`. Trong một JVM, hoạt động của A có thể làm B/C chậm hơn. Người vận hành chỉ nhìn lỗi `TimeoutException` ở B có thể nghĩ network lỗi, trong khi thực tế request đã **chờ queue trước cả khi bắt đầu I/O**.

Do đó cần phân biệt:
- Thời gian **xếp hàng chờ executor**.
- Thời gian **thực thi CPU**.
- Thời gian **chờ I/O/connection**.
- Thời gian từ request tới response.
- Tỉ lệ timeout/rejection và resource usage.

Không có phép tuning "common parallelism=64" nào thay thế các số liệu này.

### 19.2. Thay default executor của thư viện có khả thi?

Nếu API có overload nhận `Executor`, thường nên truyền executor riêng. Nếu framework có config scheduler, chọn đúng config của framework. Nếu thư viện **không cho cấu hình**, có thể cần thay cách gọi, chọn API khác, báo issue hoặc cô lập workload ở process/container khác. **Không** sửa global common pool chỉ vì không thấy cách chọn executor ngay lập tức.

## 20. Giới hạn tài nguyên: Common pool khác backpressure

Một vụ tải đột biến có thể tạo hàng chục nghìn `CompletableFuture`, subtask hoặc requests. Dù common parallelism chỉ là 8, số đối tượng task trong heap vẫn có thể rất lớn. Target 8 **không từ chối task thứ 9**, không đảm bảo bounded queue và không giới hạn I/O connection.

Đối với blocking I/O cần SLA, xem xét:

- Executor I/O được quản lý theo vòng đời service.
- Bounded queue (`ArrayBlockingQueue`, cấu hình `ThreadPoolExecutor`) hoặc admission semaphore.
- Timeout thật cho HTTP/JDBC/socket, không chỉ `CompletableFuture.orTimeout`.
- Phản hồi quá tải/`RejectedExecutionException` rõ ở ranh giới submit.
- Retry hữu hạn với backoff khi nghiệp vụ cho phép.
- Giới hạn concurrency theo connection pool/downstream capacity.
- Observability cho cả **queue wait** lẫn execution time.

### 20.1. CompletableFuture timeout không tự ngắt I/O

`CompletableFuture.orTimeout(...)` (Java 9+) có thể hoàn tất future exceptionally khi quá hạn, nhưng **không bảo đảm I/O đang blocking bị hủy hoặc socket được đóng**. Tương tự, `CompletableFuture.cancel(true)` không có tác dụng interrupt underlying task trong triển khai chuẩn. Vì vậy nếu CPU/common pool bị kẹt bởi client I/O không cấu hình timeout, thêm `orTimeout` **chỉ cải thiện thời gian caller nhìn thấy lỗi**, không tự giải phóng worker.

### 20.2. Virtual threads Java 21+: Lựa chọn khác cho blocking I/O

Từ Java 21, virtual threads được hỗ trợ chính thức. `Executors.newVirtualThreadPerTaskExecutor()` thích hợp cho nhiều tác vụ chủ yếu **chờ blocking I/O**, giúp runtime tận dụng platform carrier threads hiệu quả hơn khi API hỗ trợ unmount. Nhưng virtual threads **không làm CPU nặng chạy nhanh hơn** và **không** loại bỏ giới hạn connections, quota downstream hay need for admission. Đừng coi virtual threads là một phần của Java 8 hoặc Java 17.

Với các pipeline CPU và I/O hỗn hợp, có thể dùng virtual-thread-per-task cho những blocking calls phù hợp và executor CPU hữu hạn cho stage tính toán. Đo hiệu quả của kiến trúc thực tế thay vì mặc định luôn nhanh hơn dùng pool truyền thống.

## 21. Thiết kế thay đổi cấu hình và kiểm thử tác động chéo

Giả sử hệ thống thực sự có vấn đề shared pool:

1. **Thu thập baseline:** throughput, p50/p95/p99, CPU usage, common pool metrics, GC, I/O latency, queue wait.
2. **Phân loại call site:** `CompletableFuture` default async, parallel stream, `parallelSort`, CHM bulk, code Fork/Join trực tiếp, library bên thứ ba.
3. **Tìm các tác vụ chặn/đắt:** nhất là blocking HTTP/JDBC trong commonPool, nested parallel streams, phép giảm có callback dài.
4. **Tách workload quan trọng** bằng explicit executors và kiểm soát capacity; tránh sửa global trước.
5. **Đo lại end-to-end** trong tải đồng thời tương tự production, không chỉ chạy một phép tổng mảng.
6. **Nếu cần thay common parallelism**, xác định ai sở hữu quyết định JVM-wide; thử một cấu hình tại một thời điểm và có kế hoạch rollback.
7. **Kiểm thử cả hai hướng:** giảm tải batch có giúp latency request? Batch còn đáp ứng SLA? Concurrency tổng có làm CPU quota/DB pool quá tải không?
8. **Chống regression:** test kỹ thuật tập trung vào tính đúng; test tải tập trung vào hiệu năng, không dùng tên worker/số core cố định làm assertion.

### 21.1. Các tình huống kiểm thử nên có

| Kịch bản | Điều cần đo/kiểm tra |
| --- | --- |
| Chỉ có CompletableFuture CPU | Throughput/latency của pipeline khi không có tải khác |
| Chỉ có parallel stream CPU | Tính đúng và CPU scaling với số phần tử đủ lớn |
| Hai workload chạy đồng thời | Latency p95/p99 và queue wait của từng workload |
| Một dependency I/O chậm | Có worker common bị chặn không, CPU job có bị trễ không |
| Tách I/O sang executor riêng | CPU stage vẫn được khởi chạy khi I/O worker đang chờ |
| `Arrays.parallelSort` dữ liệu lớn | Tác động lên workload async song song |
| CHM bulk threshold=1 và MAX_VALUE | Đổi overhead/số worker có ảnh hưởng đúng mức? |
| Common parallelism thấp | CompletableFuture default có fallback thread-per-task không |
| Giới hạn container CPU | JVM thấy CPU khác host không, pool target bao nhiêu |
| Nhiều request gắn vào một service | Hàng đợi/admission có bounded không |
| Shutdown JVM khi còn async task | Ứng dụng có chờ task quan trọng hoàn tất không |
| Callback dùng shared mutable state | Có race/lost update dưới parallel execution không |

Không đo kích thước "100 tasks" duy nhất và kết luận chung cho mọi workload. Task granularity, độ dài callback và số core quyết định nhiều đến scheduling overhead.

## 22. Những lỗi thường gặp về common parallelism

1. **Tưởng `commonPool()` tạo một pool mới mỗi lần:** nó trả shared instance của JVM.
2. **Tưởng mỗi thư viện sử dụng một common pool riêng:** các code path cùng chọn common pool có thể chia sẻ worker.
3. **Tưởng mọi thư viện đều dùng common pool:** third-party và framework có thể chọn executor khác.
4. **Tưởng common parallelism là số task tối đa:** task queue có thể nhiều hơn.
5. **Tưởng `getParallelism() == getPoolSize()` tại mọi thời điểm:** target khác số worker tồn tại.
6. **Tưởng common parallelism bằng đúng số core vật lý của host:** JVM/container/config có thể khác.
7. **Tưởng tăng parallelism làm CPU vật lý nhiều hơn:** chỉ thay đổi lịch thực thi, không tăng core.
8. **Tưởng `parallelStream` có executor argument:** API không cho chọn executor trực tiếp.
9. **Dùng mẹo gọi parallel stream trong custom ForkJoinPool rồi xem đó là API contract:** không portable như explicit executor.
10. **Tưởng mọi element parallel stream luôn chạy ở common worker:** caller có thể tham gia, pipeline nhỏ có thể chạy tuần tự.
11. **Dùng `parallelStream` với blocking HTTP/JDBC:** worker có thể chờ, ảnh hưởng workload khác.
12. **Dùng `CompletableFuture.supplyAsync(blockingCall)` không executor rồi nghĩ nó cách ly:** default thường dùng common pool.
13. **Dùng `thenApplyAsync(fn)` không executor rồi tưởng kế thừa IO pool trước:** default async executor có thể khác.
14. **Tưởng `thenApply(fn)` chắc chắn chạy ở executor trước:** non-async continuation có thể chạy trên thread hoàn thành hoặc caller.
15. **Tưởng `Arrays.parallelSort` có private pool riêng:** Javadoc nêu common pool cho parallel tasks.
16. **Tưởng `ConcurrentHashMap.parallelismThreshold=1` nghĩa là một worker:** là threshold số entry, không phải số thread.
17. **Tưởng bulk reduce của CHM là atomic snapshot khi writer còn chạy:** không có bảo đảm tổng map nhất quán theo một thời điểm.
18. **Tưởng CHM threshold MAX_VALUE tắt mọi use of commonPool trong toàn ứng dụng:** chỉ ảnh hưởng phép bulk đó.
19. **Tưởng common pool bù mọi blocked I/O:** docs nói rõ unmanaged blocking không có bảo đảm bù.
20. **Tưởng mọi `join()` đều deadlock:** ForkJoinTask join được thiết kế phối hợp; rủi ro phụ thuộc workflow và executor.
21. **Tưởng mọi `join()` luôn an toàn:** nested blocking wait trong worker nhỏ có thể starve/deadlock.
22. **Đặt `-D...common.parallelism=1` rồi tưởng mọi CompletableFuture dùng đúng một worker:** triển khai chuẩn có fallback thread-per-task.
23. **Đặt `common.parallelism=0` để "tắt thread" vô hại:** Javadoc cảnh báo có thể gây thiếu tiến triển.
24. **Dùng `System.setProperty` sau khi common pool khởi tạo rồi mong config đổi ngay:** property khởi động không phải API runtime tuning.
25. **Dùng `ForkJoinPool.setParallelism` trong mã Java 17:** method được bổ sung từ Java 19.
26. **Thay common parallelism trong thư viện tự động khi một request lớn:** gây tác động global, khó đoán.
27. **Gọi commonPool.shutdown để dừng một module:** không có tác dụng shutdown common pool theo contract.
28. **Dựa vào daemon common threads để tự lưu xong dữ liệu khi main kết thúc:** phải chờ công việc quan trọng.
29. **Chỉ đọc `getQueuedTaskCount` mà bỏ external submissions:** không phải tổng queue.
30. **Coi `getStealCount` càng lớn càng tốt:** chỉ là metric hỗ trợ, không trực tiếp biểu thị SLA.
31. **Test dựa tên thread common-worker-N:** tên/số worker và policy có thể đổi.
32. **Dùng `Thread.sleep` để chứng minh tất cả worker bị starve:** sleep không đại diện I/O thật, cơ chế compensation có thể khác.
33. **Chạy benchmark không warmup và dùng mảng quá nhỏ:** overhead có thể lấn át thực tế.
34. **Dùng shared ArrayList.add trong parallel forEach:** data race độc lập với số worker.
35. **Dùng mutable source list đang được sửa trong lúc stream chạy:** vi phạm non-interference với nhiều nguồn không concurrent.
36. **Dùng reduction không associative rồi mong cùng kết quả trên mọi lịch chạy:** kết quả có thể không đúng/deterministic.
37. **Dùng global common pool như queue retry vô hạn:** không có admission/backpressure riêng.
38. **Nhầm CompletionStage non-async callback với một lần submit riêng:** callback có thể chạy trên thread hoàn thành.
39. **Kết luận module A gây lỗi module B chỉ từ một thread dump:** cần đo queue wait, CPU, downstream và trace.
40. **Chỉ tăng worker count khi DB bị nghẽn connection:** không giải quyết bottleneck thực, có thể làm quá tải nặng hơn.

## 23. Checklist code review và vận hành

- [ ] Có biết **call sites** nào dùng `ForkJoinPool.commonPool()` trực tiếp không?
- [ ] Có `CompletableFuture.supplyAsync/runAsync/thenApplyAsync` thiếu explicit executor ở đường đi quan trọng không?
- [ ] Những stage đó là **CPU-bound**, **blocking I/O**, hay **non-blocking callback**?
- [ ] Có parallel stream với mapper/filter chứa HTTP/JDBC/lock/sleep không?
- [ ] Có `Arrays.parallelSort`/`parallelPrefix` khối lượng lớn hoặc CHM bulk operations cùng thời gian với request latency-sensitive không?
- [ ] Có phân biệt **common target parallelism** với actual pool size/active threads không?
- [ ] Có kiểm tra số CPU JVM thật sự nhìn thấy trong container không?
- [ ] Có hiểu JDK Stream không cam kết API chọn custom executor không?
- [ ] Có giữ hàm mapper/reducer stateless, không mutate source và associative khi cần không?
- [ ] Có tách blocking I/O ra executor chuyên biệt hoặc virtual-thread model tương thích không?
- [ ] Executor riêng có bounded capacity/backpressure và timeout downstream không?
- [ ] Có tránh gọi `join/get` bên trong worker để chờ một future có thể cần cùng worker không?
- [ ] Có chọn một cấp parallelism hợp lý thay vì nested parallel mọi nơi không?
- [ ] Có tránh dùng global common.parallelism property như cách tùy tiện sửa một module không?
- [ ] Nếu dùng `setParallelism`, có xác nhận JDK 19+, quyền điều phối JVM-wide và các ngoại lệ config không?
- [ ] Có đo `getQueuedTaskCount` và `getQueuedSubmissionCount` riêng, không cộng thiếu/dựa vào một số sai không?
- [ ] Có metric throughput, latency p95/p99, queue wait, CPU, GC, rejection và downstream latency không?
- [ ] Có test tài nguyên khi tải từ **nhiều module cùng lúc**, không chỉ test một API một mình?
- [ ] Có chờ hoặc kết thúc có trật tự những async tasks quan trọng khi JVM tắt không?
- [ ] Có quản lý `shutdown` của các pool riêng mà không cố shutdown common pool không?
- [ ] Unit test có output xác định mà không phụ thuộc thứ tự scheduling/thread name ngẫu nhiên không?
- [ ] Có benchmark trước khi tuyên bố tuning mức parallelism làm hệ thống nhanh hơn không?

## 24. Câu hỏi ôn tập

1. `ForkJoinPool.commonPool()` có tạo một instance mới ở mỗi lần gọi không?
2. Common parallelism là số worker đang chạy, số CPU vật lý hay một **mức mục tiêu**?
3. Vì sao `getPoolSize` có thể khác `getParallelism`?
4. Hai module dùng `CompletableFuture.supplyAsync` không executor có thể cạnh tranh tài nguyên với nhau không?
5. `CompletableFuture.thenApply` và `thenApplyAsync` khác gì về nơi chạy callback?
6. Nếu common parallelism không hỗ trợ hơn một worker, CompletableFuture tiêu chuẩn có thể dùng cơ chế gì?
7. Parallel stream API có tham số `Executor` không? Có thể mặc định chắc chắn mọi code path chạy common pool không?
8. Vì sao `Arrays.parallelSort` có thể ảnh hưởng đến latency của CompletableFuture async khác trong cùng JVM?
9. `ConcurrentHashMap.forEach(1,fn)` có nghĩa dùng một worker không?
10. `parallelismThreshold=Long.MAX_VALUE` của CHM bulk operation có ý nghĩa gì?
11. Tại sao blocking I/O trong common pool có thể gây starvation?
12. `ForkJoinPool.managedBlock` có bảo đảm bù mọi waiting socket không?
13. Nếu muốn dùng pool Fork/Join riêng cho `RecursiveTask`, API nào cho phép target parallelism rõ?
14. Nếu muốn stage CPU của CompletableFuture chạy ở executor riêng, nên dùng lời gọi nào?
15. `getQueuedTaskCount` có tính luôn các external submissions chưa chạy không?
16. Có nên dùng `ForkJoinPool.commonPool().shutdown()` để "dừng" một thư viện không?
17. Khi đặt system property common.parallelism ở đầu JVM, tác động có thể lan sang những loại API nào?
18. Vì sao set property về 1 không đủ để giới hạn tổng số async task?
19. `ForkJoinPool.setParallelism` có từ Java 8 hay Java 19?
20. Nếu CPU utilization 100% và parallel stream chậm, tăng common parallelism có chắc giúp không?
21. Vì sao dùng `Thread.currentThread().getName()` làm assertion cố định cho parallel stream là không portable?
22. Vì sao phải đo queue wait và downstream latency riêng thay vì chỉ nhìn thời gian đáp ứng?
23. Khi JDK Stream được chạy bên trong private ForkJoinPool worker, có được dựa vào việc chọn pool hiện hành làm API contract không?
24. Khi service xử lý I/O blocking cần tối đa N kết nối, dùng common parallelism=N có tạo đúng giới hạn tài nguyên không?

**Đáp án gợi ý:** (1) Không, shared instance. (2) Target parallelism, không phải quota request hay actual worker count. (3) Worker có thể chưa tạo hoặc bổ sung khi blocked. (4) Có. (5) thenApply không chọn executor; thenApplyAsync có default/explicit executor. (6) Thread-per-task fallback của CompletableFuture tiêu chuẩn. (7) Không, và không có bảo đảm executor cụ thể của Stream API cho mọi hoàn cảnh. (8) Parallel tasks có thể cùng dùng common worker. (9) Không, threshold entry count. (10) Ngăn chia song song của bulk operation đó. (11) Worker chờ I/O có thể không phục vụ CPU tasks. (12) Không. (13) `new ForkJoinPool(n)` kết hợp `invoke/submit`. (14) `thenApplyAsync(fn, cpuExecutor)`. (15) Không. (16) Không có tác dụng dừng common pool. (17) CompletableFuture default, parallel stream implementations, Arrays.parallelSort, CHM bulk và direct common tasks. (18) Async fallback không phải đúng một worker; queue vẫn không giới hạn. (19) Java 19. (20) Không. (21) Scheduling, worker factory và fallback có thể khác nhau. (22) Để phân biệt nghẽn executor, CPU và network/DB. (23) Không nên dựa vào implementation detail. (24) Không, cần connection pool/semaphore/admission riêng.

**Kết luận:** Common parallelism quyết định **mức worker mục tiêu của ForkJoinPool.commonPool()`, nhưng một JVM có thể có **nhiều thư viện chia sẻ pool**, từ CompletableFuture default async, Arrays.parallelSort, các bulk methods của ConcurrentHashMap tới parallel streams trong triển khai JDK. Khi một workload có blocking I/O, CPU nặng hoặc queue lớn, nó có thể làm tăng latency của những phần code tưởng không liên quan. Hãy **đọc cấu hình pool thật**, tách **blocking I/O khỏi common pool**, chọn `Executor` rõ khi API hỗ trợ, dùng private ForkJoinPool cho thuật toán phân rã cần isolation, kiểm soát admission và đo **latency/queue/CPU/downstream**. Không coi tăng common.parallelism là giải pháp tổng quát; và nhớ rằng `setParallelism` là API **Java 19+**, còn ví dụ Java 17 sử dụng những API tương thích. Đây là toàn bộ kiến thức Java vẫn áp dụng trong hiện tại, không cần kỹ thuật ngày giờ/luồng đã lỗi thời.

## Nguồn tham khảo chính thức Java — API hiện hành

- `ForkJoinPool` Java SE 26: commonPool, parallelism, work-stealing, managedBlock, system properties, setParallelism, worker metrics, shutdown: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- `ForkJoinTask`, `RecursiveTask`: fork/join, pool-specific submit và thuật toán chia để trị: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinTask.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RecursiveTask.html
- `CompletableFuture`: default asynchronous executor, fallback khi common parallelism thấp, async vs non-async, explicit executor: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- `java.util.stream`: parallel pipelines, stateless/non-interference, side effects, ordering và reduction: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
- `Arrays`: parallelSort, parallelPrefix và parallelSetAll: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html
- `ConcurrentHashMap`: parallelismThreshold và bulk operations dùng common pool: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- `ThreadPoolExecutor`: bounded queue, rejection và capacity: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- `ExecutorService`: lifecycle và quản lý pool riêng: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html
- `HttpClient` và CompletableFuture async I/O (Java 11+): https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html
