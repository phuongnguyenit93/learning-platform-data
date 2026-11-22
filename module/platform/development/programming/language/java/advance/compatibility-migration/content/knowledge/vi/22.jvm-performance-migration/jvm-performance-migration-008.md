# Thread pool, virtual thread và giới hạn của việc đổi mô hình thực thi

Khi nâng cấp ứng dụng Java lên JDK hiện đại, nhóm phát triển thường muốn thay các `ExecutorService`, worker pool hoặc mô hình request-per-thread cũ bằng **virtual threads**. Đây là một bước tiến đáng kể của Java concurrency: ứng dụng có thể duy trì số lượng rất lớn tác vụ đang chờ I/O mà không cần tạo tương ứng từng **platform thread** đắt đỏ do hệ điều hành quản lý.

Tuy nhiên, **virtual thread không phải giải pháp tăng tốc tự động**. Đổi `Executors.newFixedThreadPool(100)` thành `Executors.newVirtualThreadPerTaskExecutor()` không làm CPU có thêm core, connection pool của database mở rộng vô hạn hay downstream API xử lý được nhiều request hơn. Nó cũng không tự sửa race condition, deadlock, transaction quá dài, thiếu timeout, overload hoặc cách quản lý `ThreadLocal`.

Bài này thuộc chủ đề **Java Advance Compatibility Migration**, nhóm **JVM và hiệu năng**, tập trung vào cách vận hành thread pool truyền thống, bản chất của virtual threads, các trường hợp được lợi, giới hạn cần tôn trọng và lộ trình chuyển đổi có thể đo lường và rollback.

## 1. Ba khái niệm thường bị đánh đồng

Trước khi thay executor, cần phân biệt:

- **Concurrency (đồng thời):** số công việc đang có thể tiến triển, bao gồm cả việc chờ I/O.
- **Parallelism (song song):** số công việc thực sự chạy CPU tại cùng một thời điểm, phụ thuộc core và tài nguyên xử lý.
- **Throughput (thông lượng):** số request/task hoàn tất trong một đơn vị thời gian.

Ví dụ, một HTTP server có 200 request đang xử lý, nhưng 180 request trong số đó đang chờ database và chỉ 20 request thực sự dùng CPU. Concurrency có thể là 200, nhưng CPU parallelism không phải 200.

Virtual threads chủ yếu giúp ứng dụng **duy trì concurrency cao với chi phí thread thấp hơn**, nhất là trong workload có nhiều thời gian chờ. Nó không đồng nghĩa tăng khả năng xử lý CPU hoặc mở rộng những tài nguyên downstream đã bão hòa.

### 1.1. Platform thread

Platform thread là `java.lang.Thread` gắn với một thread hệ điều hành theo mô hình truyền thống. Tạo rất nhiều platform threads có chi phí stack memory, scheduling và quản lý tài nguyên đáng kể.

Ví dụ:

```java
Thread worker = new Thread(() -> {
    performBlockingOperation();
});
worker.start();
```

Với hàng nghìn hoặc hàng chục nghìn tác vụ I/O, việc cấp một platform thread riêng cho từng request có thể trở nên tốn kém và khó kiểm soát.

### 1.2. Thread pool

Thread pool tái sử dụng một tập thread để chạy nhiều task. Ví dụ `newFixedThreadPool(32)` tạo tối đa khoảng 32 worker platform threads hoạt động theo cấu hình pool.

Task vượt năng lực của pool phải đợi trong queue hoặc gặp chính sách từ chối, tùy executor. Số thread hữu hạn vừa giới hạn tài nguyên, vừa có thể trở thành nút thắt khi thread dành phần lớn thời gian chờ network/database.

### 1.3. Virtual thread

Virtual thread là một implementation của `Thread` được JDK quản lý với chi phí thấp hơn đáng kể cho nhiều trường hợp chờ blocking I/O. Nhiều virtual threads có thể được thực thi qua tập nhỏ hơn các **carrier platform threads**.

Virtual thread vẫn là một `Thread`: có stack trace, interruption, tên, khả năng dùng `ThreadLocal` và nhiều API quen thuộc. Nhưng cơ chế scheduling, memory footprint và hành vi khi block khác platform thread.

**Virtual thread nên được hiểu là đơn vị thực thi theo task**, không phải một worker platform thread giá rẻ cần duy trì và tái sử dụng trong pool.

## 2. Dòng thời gian hỗ trợ virtual threads theo JDK

| JDK | Trạng thái | Ý nghĩa migration |
|---|---|---|
| Java 8–17 | Chưa có virtual threads trong Java SE tiêu chuẩn | Dùng platform threads, executor pools, async/reactive hoặc các thư viện concurrency |
| JDK 19 | Virtual threads ở trạng thái preview (JEP 425) | Chủ yếu cho thử nghiệm, cần điều kiện preview phù hợp |
| JDK 20 | Tiếp tục preview (JEP 436) | Không nên coi preview API/behavior là hợp đồng ổn định |
| JDK 21 | Virtual threads trở thành tính năng chính thức (JEP 444) | Có thể dùng `Thread.ofVirtual()` và `Executors.newVirtualThreadPerTaskExecutor()` trong code sản phẩm được hỗ trợ |
| JDK 24 | JEP 491 thay đổi hành vi pinning do `synchronized` | Cần phân biệt những chẩn đoán pinning trước/sau JDK 24 |
| JDK mới hơn | Phụ thuộc bản release, update và tooling | Kiểm tra documentation/observability của JDK thực tế, không sao chép nguyên cách khắc phục từ Java 21 |

Một ví dụ tài liệu sử dụng Java 21 là mốc nền ổn định hợp lý cho virtual threads. Điều này không có nghĩa mọi framework, driver hoặc monitoring agent đang chạy cùng JDK 21 đều đã xử lý virtual threads tối ưu.

### 2.1. Virtual thread không tương đương preview structured concurrency

Một số tài liệu đồng thời đề cập **structured concurrency** hoặc **scoped values**. Đây là các chủ đề liên quan đến quản lý lifetime và context, nhưng mức ổn định/API của chúng phụ thuộc từng JDK release.

Không nên ngầm hiểu rằng cài JDK 21 có thể sử dụng mọi ví dụ structured concurrency mới nhất mà không bật preview hoặc cập nhật API. Nội dung bài này ưu tiên virtual threads API chính thức trong JDK 21.

## 3. Cơ chế hoạt động: virtual thread và carrier thread

Mô hình khái niệm:

```text
Request A ---> Virtual Thread A ----\
Request B ---> Virtual Thread B -----\
Request C ---> Virtual Thread C ------> Scheduler ---> Carrier platform threads
Request D ---> Virtual Thread D -----/                   (số lượng hữu hạn)
Request E ---> Virtual Thread E ----/
```

Khi virtual thread đang chạy code Java, nó được **mounted** lên một carrier thread. Khi nó thực hiện một thao tác blocking mà JDK có thể hỗ trợ unmount, virtual thread có thể tách khỏi carrier; carrier tiếp tục chạy virtual thread khác.

Khi I/O sẵn sàng, virtual thread được sắp lịch tiếp tục.

Điểm quan trọng:

1. Virtual thread không nhất thiết dùng cùng một carrier trong toàn bộ thời gian tồn tại.
2. Một virtual thread có thể chờ lâu mà không giữ một carrier trong suốt khoảng chờ, nếu blocking operation hỗ trợ unmount.
3. Khi chạy CPU, virtual thread vẫn cần một carrier/platform thread để thực thi instruction.
4. Scheduler không tạo thêm CPU cores; số tác vụ thực sự chạy song song vẫn hữu hạn.
5. Không phải mọi kiểu blocking, native call hoặc tương tác framework đều có hành vi unmount giống nhau.

### 3.1. Khi nhiều tác vụ chờ I/O

Giả sử 5.000 request mỗi request gọi một API mất 200 ms, trong khi CPU chỉ cần vài millisecond để xử lý trước và sau response.

Với thread pool hữu hạn, 200 worker có thể phải chờ I/O và các request còn lại đợi queue. Virtual threads có thể giảm tình trạng platform threads bị chiếm trong thời gian chờ.

Tuy nhiên, 5.000 request **vẫn có thể gây quá tải API downstream**. Mô hình thực thi không tự tạo rate limit, backpressure hay connection pool.

### 3.2. Khi tác vụ tốn CPU

Nếu 5.000 request cùng mã hóa dữ liệu lớn, xử lý hình ảnh hoặc thực hiện phép tính CPU-bound, virtual threads không làm toàn bộ chạy song song. Scheduler vẫn bị giới hạn bởi CPU và chi phí chuyển ngữ cảnh.

Trong workload CPU-bound, fixed pool có kích thước theo số core và các giới hạn vận hành phù hợp thường dễ kiểm soát hơn.

## 4. Thread pool truyền thống: lợi ích và giới hạn

Đoạn code Java quen thuộc:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class FixedPoolExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                Executors.newFixedThreadPool(16)) {

            Future<String> result = executor.submit(() -> {
                Thread.sleep(200);
                return "done";
            });

            System.out.println(result.get());
        }
    }
}
```

Ví dụ giả định chạy trên JDK hỗ trợ `ExecutorService.close()` như JDK 21. Với Java 8/11, có thể dùng `try/finally` và `shutdown()` thay cho try-with-resources.

Fixed pool có hai tác dụng thực tế:

- **Tái sử dụng platform threads**, tránh tạo/huỷ liên tục.
- **Giới hạn số task được chạy cùng lúc** bởi worker count.

Nhưng thread pool cũng có những vấn đề riêng.

### 4.1. Queue có thể tích tụ quá nhiều task

`Executors.newFixedThreadPool` sử dụng một work queue có khả năng tăng rất lớn trong các tình huống thông thường. Việc chỉ giới hạn 16 workers không đồng nghĩa ứng dụng chỉ giữ 16 requests trong bộ nhớ.

Nếu tốc độ nhận request vượt tốc độ xử lý trong thời gian dài, queue tăng, latency tăng và cuối cùng có thể gây áp lực heap.

Khi cần backpressure rõ ràng, có thể dùng `ThreadPoolExecutor` với bounded queue, rejection policy hoặc kiểm soát admission ở tầng HTTP/message consumer.

### 4.2. Một thread chờ database vẫn chiếm worker

Nếu 16 worker cùng chờ network hoặc database, task mới không được thực thi ngay dù CPU có thể rảnh. Đây là lý do virtual threads hấp dẫn đối với ứng dụng blocking I/O truyền thống.

### 4.3. Pool không bảo đảm đồng bộ dữ liệu

Chạy task trong pool không ngăn race condition. Nếu nhiều task dùng chung `HashMap`, mutable field hoặc một transaction object không thread-safe, race và visibility issue vẫn tồn tại.

Thay pool bằng virtual threads có thể làm những bug concurrency ít gặp trở nên thường xuyên hơn do số task chạy đồng thời tăng.

## 5. Cách tạo virtual thread trong Java 21

### 5.1. Tạo trực tiếp từ `Thread.ofVirtual()`

```java
public final class VirtualThreadExample {
    public static void main(String[] args) throws InterruptedException {
        Thread thread = Thread.ofVirtual()
                .name("inventory-query")
                .start(() -> {
                    System.out.println(Thread.currentThread());
                    System.out.println(
                            "isVirtual = " + Thread.currentThread().isVirtual());
                });

        thread.join();
    }
}
```

Với JDK 21, `Thread.ofVirtual()` là API chính thức. `join()` chờ virtual thread hoàn tất; nếu bỏ chờ mà chỉ tạo virtual threads trong chương trình main ngắn, process có thể kết thúc trước khi task hoàn thành.

### 5.2. `newVirtualThreadPerTaskExecutor()`

Cách dùng phổ biến hơn trong code ứng dụng:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class VirtualExecutorExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int i = 0; i < 100; i++) {
                final int id = i;
                futures.add(executor.submit(() -> {
                    Thread.sleep(100);
                    return "task-" + id;
                }));
            }

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
```

Mỗi task được executor nhận sẽ chạy trên một virtual thread mới. Executor này **không phải fixed virtual-thread pool** và không áp đặt giới hạn 100/1.000 thread theo cách fixed pool.

`ExecutorService.close()` chờ các task liên quan hoàn tất theo ngữ nghĩa của API, nên cần quản lý timeout, cancellation và shutdown nếu công việc có thể chờ không giới hạn.

### 5.3. Vì sao không nên tạo virtual-thread pool?

Virtual threads được thiết kế để tạo theo công việc. Nếu giới hạn chúng bằng một pool nhỏ chỉ để “tiết kiệm thread”, ứng dụng có thể mất lợi thế concurrency khi I/O block.

Ví dụ, tạo một fixed-thread executor với virtual-thread factory (nếu cấu hình theo cách được hỗ trợ) thường không phải giải pháp được khuyến nghị cho request-per-task. Nếu cần giới hạn **số lời gọi database**, hãy giới hạn chính lời gọi database bằng connection pool, semaphore, rate limiter hoặc admission control.

**Phân biệt giới hạn tài nguyên với giới hạn số virtual threads.**

## 6. So sánh ba mô hình thực thi

| Đặc điểm | Platform thread-per-request | Fixed platform thread pool | Virtual thread-per-task |
|---|---|---|---|
| Chi phí khi có nhiều task đang chờ | Cao | Worker bị chiếm, queue tăng | Thường thấp hơn đáng kể |
| Khả năng quản lý concurrency I/O | Bị giới hạn bởi OS threads | Giới hạn bởi pool size | Có thể rất cao |
| CPU parallelism | Theo core | Theo core/pool | Vẫn theo core/carriers |
| Tái sử dụng thread | Có thể không | Có | Không cần pool virtual threads |
| Bounded task admission | Phải thiết kế | Có thể bằng queue/rejection | Phải thiết kế riêng |
| Khả năng dùng blocking style | Có | Có | Có, với I/O được hỗ trợ |
| Bảo vệ database/remote API | Không tự có | Worker count đôi khi giới hạn gián tiếp | Không tự có |
| Rủi ro ThreadLocal | Có | State leak khi tái sử dụng worker | Tạo nhiều per-task states |
| Quan sát stack trace | Có | Có | Có, nhưng số virtual threads có thể rất lớn |
| Phù hợp CPU-bound | Có giới hạn | Thường dễ điều khiển | Không tự tạo lợi thế CPU |

Không nên coi bảng này là dự báo hiệu năng định lượng. Kết quả thực tế phụ thuộc tỉ lệ chờ I/O, latency, connection pool, request size, GC, scheduler, framework và downstream service.

## 7. Virtual threads phù hợp workload nào?

### 7.1. Nhiều tác vụ blocking I/O độc lập

Các tình huống tiềm năng:

- HTTP/gRPC clients sử dụng blocking I/O theo stack hỗ trợ.
- Gọi database qua JDBC blocking API.
- Truy vấn nhiều API đối tác.
- Xử lý request-per-thread trong web server có hỗ trợ virtual threads.
- Batch task phải chờ file/network mà không cần giữ platform worker.
- Một số hệ thống message processing chờ I/O dài.

Đặc điểm quan trọng là **thời gian chờ chiếm tỷ trọng cao** so với thời gian dùng CPU.

### 7.2. Code synchronous dễ đọc và dễ theo dõi

Một flow:

```java
Order order = repository.load(orderId);
Price price = pricingClient.getPrice(order);
repository.save(order.withPrice(price));
```

có thể giữ phong cách tuần tự dễ đọc khi thực thi trên virtual thread, thay vì buộc phải biểu diễn mọi bước bằng chuỗi callback.

Tuy nhiên, code synchronous không tự kiểm soát concurrency, timeout và transaction lifetime. Những vấn đề này vẫn cần thiết kế.

### 7.3. Virtual threads không đương nhiên tốt hơn reactive

Reactive và event-loop frameworks cũng có thể xử lý rất nhiều I/O concurrency hiệu quả, thường dùng asynchronous APIs và backpressure được xây dựng trong mô hình lập trình.

Chuyển một hệ thống reactive đang hoạt động tốt sang virtual threads không bảo đảm tăng hiệu năng; có thể phải viết lại flow, context propagation và cancellation semantics.

Nên cân nhắc **độ phức tạp code, thư viện đang dùng và kết quả benchmark**, không quyết định dựa trên “virtual thread luôn mới hơn”.

## 8. Trường hợp virtual threads không mang lại lợi ích lớn

### 8.1. CPU-bound task

Ví dụ tính toán băm hàng loạt hoặc nén dữ liệu:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class CpuWorkExample {
    public static void main(String[] args) {
        int cpuCount = Runtime.getRuntime().availableProcessors();

        try (ExecutorService executor =
                Executors.newFixedThreadPool(cpuCount)) {
            for (int i = 0; i < 100; i++) {
                executor.submit(() -> computeHeavyResult());
            }
        }
    }

    private static void computeHeavyResult() {
        // Minh họa một tác vụ CPU-bound.
        long total = 0;
        for (long i = 0; i < 10_000_000L; i++) {
            total += i;
        }
        if (total == Long.MIN_VALUE) {
            System.out.println(total);
        }
    }
}
```

Đây là ví dụ mô hình, không phải microbenchmark chuẩn. Workload CPU-bound cần được giới hạn theo cores, độ ưu tiên, latency và memory. Dùng virtual threads vô hạn có thể chỉ làm số runnable tasks tăng, gây cạnh tranh CPU và khó kiểm soát tail latency.

### 8.2. Blocking native/JNI hoặc thư viện chưa hỗ trợ

Không phải mọi thao tác block đều có thể unmount virtual thread khỏi carrier theo cùng cách. Một thư viện gọi native API, giữ native/foreign frame hoặc sử dụng cơ chế đồng bộ đặc biệt có thể khiến carrier bị giữ lâu hoặc gây các hạn chế khác.

Cần kiểm tra JDK version và native library/framework tương ứng, không khẳng định mọi I/O luôn “free” khi dùng virtual threads.

### 8.3. Công việc bị giới hạn bởi dịch vụ bên ngoài

Nếu database chỉ cho phép 50 connections, dùng 50.000 virtual threads không biến nó thành database hỗ trợ 50.000 queries đồng thời. Những virtual threads dư sẽ chờ connection hoặc đợi semaphore, tiêu thụ bộ nhớ và kéo dài latency.

### 8.4. Tác vụ quá nhỏ nhưng được tạo hàng triệu lần

Virtual threads rẻ hơn platform threads nhưng không miễn phí. Tạo một virtual thread cho từng phép cộng cực nhỏ có thể tốn overhead scheduling lớn hơn lợi ích.

Đối với xử lý dữ liệu CPU cực nhỏ, sử dụng loop, batch, vectorization hoặc mô hình parallelism phù hợp thường hiệu quả hơn.

## 9. Backpressure: vấn đề quan trọng nhất khi chuyển đổi

Một fixed thread pool có giới hạn worker, nên vô tình trở thành giới hạn concurrency đối với một số downstream. Khi chuyển sang virtual-thread-per-task executor, giới hạn này có thể biến mất.

Ví dụ trước migration:

```text
Fixed pool 32 workers
      |
      v
Database pool 20 connections
```

Sau migration:

```text
20.000 virtual tasks
      |
      v
Database pool 20 connections
```

20 connections vẫn là giới hạn thực. Số task chờ mượn connection có thể tăng mạnh khi hệ thống nhận burst traffic.

### 9.1. Giới hạn tài nguyên bằng `Semaphore`

Ví dụ Java 21:

```java
import java.util.concurrent.Semaphore;

public final class LimitedRepository {
    private final Semaphore permits = new Semaphore(20);
    private final OrderRepository delegate;

    public LimitedRepository(OrderRepository delegate) {
        this.delegate = delegate;
    }

    public Order load(long id) throws InterruptedException {
        permits.acquire();
        try {
            return delegate.load(id);
        } finally {
            permits.release();
        }
    }
}
```

`OrderRepository` và `Order` là kiểu nghiệp vụ minh họa, không phải class Java SE. Mẫu này cho thấy semaphore bảo vệ vùng gọi database và luôn trả permit ở `finally`.

Ưu điểm: nhiều virtual threads có thể chờ permit mà không cần tương ứng nhiều platform threads. Nhưng **semaphore không tự giới hạn số request đã được nhận vào hệ thống**. Nếu 1 triệu request được nhận cùng lúc, vẫn có thể có rất nhiều task đang chờ semaphore.

### 9.2. Cần giới hạn từ điểm nhận việc

Đối với production, còn cần:

- HTTP server admission control và giới hạn concurrent requests.
- Bounded queue ở message consumer/job dispatcher.
- Rate limiting cho API đối tác.
- Circuit breaker và bulkhead cho mỗi downstream.
- Connection pool sizing và thời gian chờ lấy connection.
- Thời hạn request và cancellation.
- Cơ chế trả `429`/`503` hoặc retry-after khi quá tải.

Virtual threads không thay thế những cơ chế này. **Backpressure nên nằm ở biên nhận request và từng tài nguyên khan hiếm**, không chỉ giới hạn số carrier threads.

### 9.3. Timeout ở mọi điểm chờ

Một semaphore hoặc connection pool có thể chờ rất lâu. Ví dụ giới hạn thời gian lấy permit:

```java
import java.time.Duration;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class TimedAdmission {
    private final Semaphore permits = new Semaphore(20);

    public void execute(Runnable action) throws InterruptedException {
        boolean acquired = permits.tryAcquire(
                Duration.ofSeconds(2).toMillis(),
                TimeUnit.MILLISECONDS);

        if (!acquired) {
            throw new IllegalStateException("Hệ thống đang quá tải");
        }

        try {
            action.run();
        } finally {
            permits.release();
        }
    }
}
```

Mẫu này minh họa giới hạn thời gian chờ permit, không tự áp dụng timeout cho chính `action.run()`. Cần timeout ở database, HTTP client và tổng deadline request.

## 10. Little's Law và sức chứa thực tế

Với hệ thống ở trạng thái ổn định, Little's Law mô tả mối quan hệ:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số công việc trung bình đang ở trong hệ thống.
- \(\lambda\): tốc độ công việc hoàn tất/đến trong trạng thái ổn định.
- \(W\): thời gian trung bình mỗi công việc ở trong hệ thống.

Ví dụ minh họa: nếu hệ thống hoàn tất trung bình 500 requests/giây và mỗi request ở trong hệ thống 0,2 giây, số request đồng thời trung bình xấp xỉ 100.

Nếu downstream chậm từ 200 ms lên 2 giây nhưng tốc độ đến không giảm, số request đang chờ có thể tăng khoảng mười lần trong điều kiện ổn định tương ứng. Virtual threads có thể giảm chi phí platform threads khi phải chờ, nhưng **không rút ngắn thời gian downstream**.

Nếu tốc độ đến vượt tốc độ phục vụ bền vững, queue có thể tăng không giới hạn dù dùng platform hay virtual threads. Khi đó cần shedding, rate limiting, scaling downstream hoặc điều chỉnh kiến trúc.

## 11. Pinning: phải phân biệt JDK 21 và JDK mới hơn

**Pinning** là tình huống virtual thread đang block nhưng không thể tách khỏi carrier theo cơ chế thông thường. Điều này có thể làm giảm lợi ích khi số lượng virtual threads chờ cao.

Tuy nhiên, nguyên nhân pinning **thay đổi giữa các thế hệ JDK**.

### 11.1. JDK 21–23: synchronized có thể gây pinning

Ở JDK 21 và một số release đầu của virtual threads, virtual thread thực thi trong `synchronized` block/method rồi block ở một số thao tác có thể giữ carrier thread.

Ví dụ:

```java
public final class LegacyClient {
    private final Object lock = new Object();

    public String loadData() throws InterruptedException {
        synchronized (lock) {
            // Mô phỏng I/O blocking bên trong monitor:
            Thread.sleep(300);
            return "data";
        }
    }
}
```

Trên các JDK chịu giới hạn này, blocking trong monitor có thể gây pinning. Vấn đề nghiêm trọng hơn nếu hàng nghìn request cùng làm như vậy.

Các hướng xử lý khi còn dùng JDK 21–23:

1. Xác định đoạn `synchronized` thật sự chứa long blocking operation.
2. Rút ngắn critical section khi vẫn bảo toàn thread safety.
3. Tránh giữ monitor trong lúc gọi I/O nếu có thể.
4. Khi phù hợp, cân nhắc lock có cơ chế phù hợp hơn như `ReentrantLock`.
5. Kiểm thử race condition, fairness và performance trước khi thay lock.

**Không thay mọi `synchronized` bằng `ReentrantLock` theo công thức máy móc.** Một monitor dùng cho critical section rất ngắn không nhất thiết gây vấn đề, còn việc đổi lock có thể làm thay đổi semantics và gây bug.

### 11.2. JDK 24: thay đổi quan trọng của JEP 491

JEP 491 cải thiện hành vi virtual threads với các monitor `synchronized`, loại bỏ nguyên nhân pinning do synchronization ở cơ chế tương ứng. Vì vậy, lời khuyên “mọi blocking trong `synchronized` đều pin carrier” **không còn đúng một cách tổng quát trên JDK 24 trở đi**.

Điều này không có nghĩa mọi nguồn pinning hoặc blocking khó quản lý đều biến mất. Các tương tác native/foreign và một số tình huống runtime đặc thù vẫn cần được kiểm tra theo JDK và thư viện thực tế.

Khi migration, ghi rõ:

```text
Runtime JDK:
  - 21/22/23: đánh giá monitor pinning theo cơ chế cũ
  - 24+: xem thay đổi JEP 491 và những giới hạn còn lại
```

Không sao chép nguyên cách chẩn đoán Java 21 sang mọi JDK mới.

### 11.3. `synchronized` vẫn có thể gây contention

Ngay cả khi monitor không còn pin carrier, `synchronized` vẫn có thể bảo vệ một vùng chỉ cho một thread vào mỗi lần. Nếu một ứng dụng khóa toàn bộ thao tác database dưới cùng monitor, throughput vẫn bị tuần tự hóa vì lock contention.

**Giảm pinning không đồng nghĩa xóa giới hạn logic của critical section.**

## 12. Quan sát pinning và virtual threads

### 12.1. JFR (Java Flight Recorder)

JFR hỗ trợ quan sát hành vi JVM với overhead được thiết kế cho profiling/production diagnostics theo mức cấu hình. Trên các JDK có sự kiện tương ứng, có thể dùng những event liên quan virtual threads, pinning, scheduling và allocation.

Ví dụ khởi chạy ghi profile ngắn:

```bash
java \
  -XX:StartFlightRecording=filename=recording.jfr,duration=60s,settings=profile \
  -jar app.jar
```

Nội dung event thực tế phụ thuộc JDK version và cấu hình recording. Không nên kết luận “không có `jdk.VirtualThreadPinned` event là chắc chắn không có vấn đề concurrency”: event có thể bị tắt, có threshold hoặc semantics đã thay đổi giữa các JDK.

### 12.2. `jdk.tracePinnedThreads` trên các JDK đầu

Một số JDK đầu có thể sử dụng:

```bash
java -Djdk.tracePinnedThreads=full -jar app.jar
```

để hỗ trợ tìm tình huống pinning do monitor/native frames. Đây là công cụ chẩn đoán có tính phiên bản: trên JDK mới sau thay đổi pinning, thuộc tính có thể không còn ý nghĩa như trước.

Cần dựa vào công cụ chẩn đoán và JFR phù hợp với **JDK đang chạy**, không chỉ bật một property rồi xem việc không có output là bằng chứng an toàn.

### 12.3. Thread dump và `jcmd`

JDK hiện đại hỗ trợ các cách lấy thread dump thích hợp cho virtual threads, ví dụ dùng `jcmd`:

```bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Thay `<pid>` bằng PID thật của tiến trình Java; đây là lệnh mẫu, cú pháp/hỗ trợ tùy JDK. File dump có thể rất lớn khi hệ thống có nhiều virtual threads.

Với môi trường cần truy vết production, hãy giới hạn tần suất chụp dump, bảo vệ thông tin nhạy cảm và chọn công cụ/format phù hợp với số lượng virtual threads.

### 12.4. Metrics nên đo

- Request throughput và p50/p95/p99 latency.
- CPU utilization, CPU throttling và available processors.
- Heap, GC pauses, allocation rate và memory footprint.
- Virtual thread count hoặc trạng thái hoạt động theo công cụ được hỗ trợ.
- Carrier utilization và dấu hiệu scheduling contention khi có thể quan sát.
- Database connection pool active/idle/waiters/timeout.
- HTTP client pool, outbound request concurrency và retry rate.
- Queue depth, rejected requests, timeout và cancellation.
- Pinning hoặc monitor contention nếu JDK cung cấp event phù hợp.
- Downstream error rate, rate limit và circuit breaker state.

Một con số “có 100.000 virtual threads” không tự chứng minh hệ thống tốt hay xấu. Phải đọc cùng latency, resource saturation và workload.

## 13. ThreadLocal: không bị xóa nhưng trở nên đắt hơn khi lạm dụng

Virtual threads hỗ trợ `ThreadLocal`, tuy nhiên mô hình **một virtual thread cho một task** có thể tạo rất nhiều thread cùng lúc. Nếu mỗi thread giữ object lớn trong ThreadLocal, tổng bộ nhớ tăng đáng kể.

Ví dụ rủi ro:

```java
private static final ThreadLocal<byte[]> BUFFER =
        ThreadLocal.withInitial(() -> new byte[1024 * 1024]);
```

Nếu hàng nghìn virtual threads cùng tạo buffer 1 MiB, memory usage có thể rất lớn. Điều này khác fixed platform pool chỉ có vài chục worker giữ buffer.

### 13.1. Dùng context ngắn, không giữ object lớn

Nên tránh lưu:

- Cache có kích thước lớn theo từng thread.
- Database connection trong `ThreadLocal`.
- Mutable session object sống quá lâu.
- Pooled resource cần đóng mà lifecycle gắn vào thread.
- Buffer lớn không có giới hạn.

Có thể truyền request context qua parameter hoặc context propagation mechanism của framework phù hợp.

### 13.2. MDC/logging context

Một framework logging có thể dùng ThreadLocal để giữ trace ID, user context hoặc request metadata. Virtual thread được tạo mới cho mỗi task nên **không được giả định context từ platform worker sẽ tự chuyển sang child task**.

Ví dụ logic context cần có phạm vi:

```java
try {
    putTraceId(traceId);
    performRequest();
} finally {
    clearTraceId();
}
```

`putTraceId` và `clearTraceId` là placeholder cho API logging thực tế. Cần kiểm tra cách framework hỗ trợ propagation khi tạo task mới, nhất là khi dùng asynchronous completions hoặc thread hops.

### 13.3. Không giả định thread identity ổn định theo worker pool

Một số thư viện legacy dùng `Thread.currentThread()` hoặc `ThreadLocal` như một key để lưu resource cho worker dùng lại qua nhiều request. Mô hình đó không còn phù hợp khi mỗi request có một virtual thread mới.

Thread-per-task nên ưu tiên **request-scoped data** hoặc dependency injection scopes được framework quản lý, không phụ thuộc worker reuse.

## 14. JDBC, connection pool và transaction lifetime

Virtual threads có thể phù hợp với JDBC synchronous programming vì chúng cho phép code chờ database mà không buộc phải dành một platform thread cho toàn bộ thời gian chờ, khi driver và runtime tương tác phù hợp.

Nhưng database vẫn giới hạn bởi:

- Maximum connections.
- Query execution slots, locks và I/O capacity.
- Transaction isolation và contention.
- Statement timeout và network timeout.
- Connection pool wait queue.
- Database-side CPU, buffer cache và disk throughput.

### 14.1. Không bỏ connection pool

Một hiểu nhầm là virtual threads khiến connection pool không còn cần thiết. Thực tế connection pool bảo vệ tài nguyên **database connection**, khác với pool bảo vệ platform threads.

Ví dụ:

```text
Virtual threads = 10.000
HikariCP maximumPoolSize = 30
```

Hệ thống không có 10.000 database connections. Nhiều request sẽ chờ quyền lấy connection; latency và timeout vẫn có thể tăng.

Cần dựa trên benchmark để chọn connection pool size, tránh tăng lên hàng nghìn chỉ vì virtual thread count lớn.

### 14.2. Transaction không được giữ mở vô hạn

Một virtual thread có thể chờ I/O lâu mà không chiếm carrier, nhưng transaction của nó vẫn có thể giữ connection hoặc row locks. Đó là tài nguyên thật và có thể gây deadlock hoặc làm database bão hòa.

Không mở transaction xuyên qua những lời gọi external API chậm nếu business correctness không đòi hỏi và thiết kế có thể tách được.

### 14.3. Driver và pool phải tương thích

Một số JDBC driver hoặc pool library dùng synchronized sections, ThreadLocal hoặc native calls. Khi migration, kiểm tra version hỗ trợ JDK mới, JDK21 pinning behavior nếu liên quan, timeout và cancellation semantics.

Đừng chỉ kiểm tra `SELECT 1` rồi kết luận mọi transaction flow đã tương thích.

## 15. HTTP client và thời gian chờ I/O

Một HTTP call synchronous có thể rất dễ đọc trên virtual thread:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HttpClientExample {
    public static void main(String[] args) throws Exception {
        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://example.com"))
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();

            HttpResponse<String> response =
                    client.send(request, HttpResponse.BodyHandlers.ofString());

            System.out.println(response.statusCode());
        }
    }
}
```

Đoạn code minh họa cấu trúc HTTP client ở JDK có hỗ trợ `HttpClient.close()` như JDK 21; network call có thể thất bại tùy môi trường. Trong ứng dụng thật, hãy quản lý client lifecycle, connection reuse, auth và TLS theo yêu cầu sản phẩm.

### 15.1. Virtual thread không thay thế request timeout

Nếu request thiếu timeout, nhiều virtual threads có thể bị giữ ở trạng thái chờ lâu. Dù carrier được giải phóng trong quá trình chờ hỗ trợ, hệ thống vẫn giữ request context, memory, deadline và potentially downstream slots.

Cần cấu hình:

- Connection timeout.
- Request/read timeout.
- Tổng deadline của nghiệp vụ.
- Retry policy với exponential backoff và jitter khi phù hợp.
- Idempotency khi thực hiện retry.
- Rate limiting và circuit breaker.
- Cancellation/interruption propagation.

### 15.2. Đừng bắn hàng trăm nghìn outbound requests đồng thời

Virtual-thread-per-task executor có thể nhận rất nhiều tác vụ, nhưng API đối tác thường có rate limit. Ví dụ một đối tác cho phép 200 requests/giây; 50.000 virtual threads không làm giới hạn biến mất.

Giới hạn outbound request concurrency/rate ở vị trí thích hợp trước khi submit hoặc tại downstream client layer.

## 16. Interruption, cancellation và shutdown

Virtual threads sử dụng cơ chế interruption của `Thread`, nhưng code ứng dụng vẫn phải **hợp tác với cancellation**.

### 16.1. Đừng nuốt `InterruptedException`

Sai:

```java
try {
    Thread.sleep(1000);
} catch (InterruptedException ignored) {
    // Bỏ qua hoàn toàn, task tiếp tục chạy.
}
```

Cách tốt hơn khi phương thức không thể throw:

```java
try {
    Thread.sleep(1000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Hoặc để phương thức khai báo `throws InterruptedException` và cho layer điều phối quyết định.

### 16.2. `Future.cancel(true)` yêu cầu hủy, không bảo đảm mọi task kết thúc ngay

Ví dụ:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class CancellationExample {
    public static void main(String[] args) {
        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            Future<?> future = executor.submit(() -> {
                try {
                    while (!Thread.currentThread().isInterrupted()) {
                        Thread.sleep(100);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            future.cancel(true);
        }
    }
}
```

Một task đang trong code native, thao tác không hỗ trợ cancel hoặc xử lý interrupt sai có thể không kết thúc ngay. Hãy thiết kế deadline, close resources và kiểm tra luồng shutdown thực tế.

### 16.3. Task lifetime phải có owner

Một ứng dụng không nên chỉ tạo virtual threads rồi quên chúng:

```java
Thread.ofVirtual().start(() -> callPartnerApi());
```

Nếu request bị hủy hoặc ứng dụng shutdown, ai có trách nhiệm chờ, hủy hoặc thu thập lỗi của task? Trong backend cần có owner ở request/service lifecycle hoặc một thành phần điều phối cụ thể.

Virtual threads giúp đơn giản hóa blocking code nhưng **không thay thế quản lý lifetime**.

## 17. Tương thích framework và servlet container

### 17.1. Server hỗ trợ virtual threads không đồng nghĩa toàn stack tối ưu

Một số web server và framework hỗ trợ cấu hình request handling bằng virtual threads. Nhưng hiệu quả cuối cùng phụ thuộc:

- Servlet/request dispatcher implementation.
- Filter/interceptor chain.
- JDBC pool và driver.
- HTTP client library.
- Logging/tracing instrumentation.
- Transaction manager.
- ThreadLocal/context propagation.
- Security framework.
- Application code và các critical sections.

Nếu một filter cũ giữ monitor trong lúc gọi API ngoài trên JDK 21, hiệu năng có thể không đạt kỳ vọng dù server hỗ trợ virtual-thread-per-request.

### 17.2. Spring Boot và các framework hiện đại

Một số phiên bản Spring Boot/framework cung cấp tùy chọn bật virtual threads, nhưng **cú pháp, điều kiện hỗ trợ và các hệ quả lifecycle khác nhau theo version**. Không sao chép một property của phiên bản mới sang bản cũ và coi là đã bật.

Khi bật ở framework:

1. Kiểm tra ma trận JDK/framework hỗ trợ chính thức.
2. Xác nhận request executor hoặc task executor thực tế đổi sang virtual threads.
3. Kiểm tra scheduler, background jobs và application liveness.
4. Kiểm tra async/messaging/transaction semantics.
5. Chạy test với phiên bản runtime và container cuối.

Một số cấu hình scheduler có thể tiếp tục dùng platform threads; bật virtual threads cho HTTP request không tự chuyển mọi task trong ứng dụng.

### 17.3. Virtual threads và tính daemon

Virtual threads là daemon threads. Nếu một ứng dụng chỉ còn virtual threads và không còn non-daemon threads giữ JVM hoạt động, process có thể kết thúc khi main hoặc lifecycle chính kết thúc.

Trong ứng dụng backend, cần để framework/container quản lý lifecycle đúng cách. Không dựa vào các background virtual threads để giữ process sống.

## 18. Locks, race condition và thread safety

Một số hệ thống được xây dựng dựa trên giả định worker pool chỉ có 20 threads. Khi đổi sang virtual threads, nhiều request có thể đồng thời thực hiện các thao tác trước đây hiếm khi tranh chấp.

Ví dụ code không thread-safe:

```java
public final class Counter {
    private long value;

    public void increment() {
        value++;
    }

    public long get() {
        return value;
    }
}
```

`value++` không atomic. Với nhiều virtual threads, giá trị có thể bị mất cập nhật; nhưng bug này cũng tồn tại với platform threads.

Có thể dùng `AtomicLong`, lock hoặc thiết kế bất biến theo nhu cầu:

```java
import java.util.concurrent.atomic.AtomicLong;

public final class SafeCounter {
    private final AtomicLong value = new AtomicLong();

    public long increment() {
        return value.incrementAndGet();
    }

    public long get() {
        return value.get();
    }
}
```

Lựa chọn atomic/locking phải dựa trên invariant nghiệp vụ, không chỉ để sửa một phép tăng đơn giản.

### 18.1. Không chia sẻ state theo request

Các đối tượng như mutable request DTO, `EntityManager` hoặc transaction context không nên được chia sẻ giữa tasks nếu thư viện không bảo đảm thread safety.

Nhiều virtual threads có thể cùng gọi singleton service; singleton phải được thiết kế cho concurrent access hoặc sử dụng state không chia sẻ.

### 18.2. Deadlock vẫn xảy ra

Virtual threads không giải quyết circular lock dependencies. Nếu task A giữ lock X và chờ Y, task B giữ Y và chờ X, deadlock vẫn tồn tại.

Deadlock có thể khó phát hiện hơn khi số lượng tasks rất cao; cần thread dump, lock-order policy và test contention.

## 19. Bài toán pooling tài nguyên ngoài threads

Thread pool truyền thống thường bị dùng làm “nút điều chỉnh” của nhiều resource cùng lúc. Khi bỏ giới hạn số workers, phải xác định lại các resource constraints.

| Tài nguyên | Giới hạn thật | Biện pháp kiểm soát |
|---|---|---|
| CPU | Số core/quota | Bounded CPU executor, giảm parallelism khi bão hòa |
| Database connections | Pool size và server limit | Connection pool, short transactions, timeout |
| Outbound HTTP | Rate/concurrency limit | Semaphore, rate limiter, connection management |
| File descriptors | OS limit | Close đúng lifecycle, admission control |
| Heap memory | Request state, buffers, queue | Bounded admission, đo allocation và GC |
| External API quota | Hạn mức của bên cung cấp | Retry-after, backoff, circuit breaker |
| Message broker | Prefetch/in-flight/ack rate | Consumer concurrency, backpressure |
| Third-party native library | Thread safety và native handles | Pool/semaphore riêng, version compatibility |
| Logging/monitoring | Queue/buffer/network sink | Async log backpressure, sampling và tracing policy |

**Không chuyển từ giới hạn platform thread sang “không giới hạn” nếu các tài nguyên này chưa được bảo vệ.**

## 20. Benchmark đúng cách trước khi kết luận cải thiện hiệu năng

Một benchmark virtual threads cần mô phỏng đúng workload.

### 20.1. Các thông số cần giữ cố định

- JDK vendor/update và JVM flags.
- CPU quota, RAM, GC configuration.
- Số connection pool của database/HTTP.
- Dataset, transaction isolation và query complexity.
- Request arrival pattern, payload size.
- Network latency và downstream capacity.
- Framework, application server và agents.
- Bản build và dependency graph.

Nếu vừa bật virtual threads vừa nâng ORM, JDK, connection pool và API gateway, rất khó quy cải thiện cho mô hình thực thi.

### 20.2. So sánh bằng cùng SLO

Ví dụ:

```text
Baseline (platform thread pool):
  throughput: X request/s
  p95 latency: Y ms
  CPU: Z%
  DB waiters: A

Candidate (virtual threads):
  throughput: ...
  p95 latency: ...
  CPU: ...
  DB waiters: ...
```

Cần thử nhiều mức tải, bao gồm burst, steady state và overload. Không chỉ đo peak throughput rồi bỏ qua p99 latency, error rate và memory.

### 20.3. Warmup và JIT

Java có JIT compilation, profile-guided optimizations và GC. Một microbenchmark chạy vài giây có thể cho kết quả bị ảnh hưởng bởi warmup.

Đối với microbenchmark về concurrency, dùng công cụ có phương pháp phù hợp như JMH khi cần, nhưng **không lấy kết quả benchmark sleep đơn giản làm bằng chứng hiệu năng production**. Workload thực tế cần load testing end-to-end.

### 20.4. Chọn đúng chỉ số thành công

Virtual threads có thể không giảm latency của **một** lời gọi database, nhưng giúp xử lý **nhiều** lời gọi chờ I/O trong cùng tài nguyên thread. Vì vậy hãy đo throughput ở mục tiêu concurrency, số task chờ, tail latency và saturation của downstream.

Nếu bottleneck thực sự nằm ở database CPU, thay threads có thể không mang lại cải thiện đáng kể.

## 21. Quy trình migration đề xuất

### Bước 1 — Chụp baseline

Thu thập request throughput, latency, queue depth, active threads, CPU, heap, DB/HTTP pool saturation, timeout và error rate trên runtime hiện tại.

Ghi cả JDK/framework/driver versions để đối chiếu sau migration.

### Bước 2 — Phân loại workload

Tách:

- Blocking I/O nhiều thời gian chờ.
- CPU-bound work.
- Native/JNI blocking.
- Long-lived streaming connections.
- Background jobs và scheduled tasks.
- Request handling và batch processing.

Không chuyển tất cả thành virtual threads chỉ vì một module có lợi.

### Bước 3 — Kiểm tra khả năng hỗ trợ của JDK và thư viện

Chọn JDK 21+ có virtual threads chính thức, đánh giá các bản cập nhật và khác biệt pinning sau JDK 24. Kiểm tra:

- Framework/server executor support.
- JDBC driver và connection pool.
- HTTP client behavior.
- Logging/tracing/monitoring agents.
- Synchronized/native calls.
- Test/mocking/instrumentation libraries.

### Bước 4 — Chọn phạm vi migration hẹp

Ví dụ chuyển executor cho một endpoint/blocking service có lưu lượng rõ, không thay toàn bộ concurrency architecture một lần.

Giữ khả năng bật/tắt theo feature flag hoặc deploy cấu hình riêng khi framework cho phép.

### Bước 5 — Thiết kế lại giới hạn concurrency

Nếu fixed pool trước đây giới hạn 50 calls tới external API, phải thay bằng giới hạn tài nguyên rõ như semaphore, rate limiter hoặc bulkhead. Thiết lập timeouts và bounded admission.

### Bước 6 — Chuyển code thực thi

Ví dụ thay:

```java
ExecutorService executor = Executors.newFixedThreadPool(64);
```

bằng:

```java
ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor();
```

nhưng chỉ khi logic có thể dùng thread-per-task, executor lifecycle được quản lý và tài nguyên downstream đã được bảo vệ. Đây là thay đổi **mô hình concurrency**, không phải phép đổi cú pháp bảo đảm tương thích.

### Bước 7 — Xem lại context và thread safety

Kiểm tra `ThreadLocal`, MDC, security context, transaction boundaries, mutable state và code gắn tài nguyên vào worker thread. Bổ sung context propagation và cleanup khi cần.

### Bước 8 — Kiểm tra pinning/native

Trên JDK 21–23, tìm vùng synchronized chứa blocking operation. Trên JDK 24+, xem lại theo JEP 491 và các giới hạn còn lại. Kiểm tra JNI/native library và driver.

### Bước 9 — Chạy test nhiều mức tải

Test cả tải bình thường, burst và overload. Quan sát database waiters, connection timeouts, p95/p99 latency, heap/GC và downstream error rate.

### Bước 10 — Pilot và rollback

Triển khai trên tỷ lệ traffic nhỏ, so sánh SLO với baseline. Có cơ chế quay về executor cũ nếu phát sinh overload, regression hoặc incompatibility.

### Bước 11 — Cập nhật vận hành

Điều chỉnh dashboard, alerts, runbook, thread dump procedure, profiling/JFR và capacity planning. Với virtual threads, đếm platform threads không còn đại diện đầy đủ cho số request in-flight.

## 22. Những hiểu lầm thường gặp

### “Virtual thread là thread hệ điều hành nhẹ”

Không hoàn toàn. Virtual threads là Java threads do JDK quản lý và được scheduler thực thi trên các carrier platform threads. Chúng không ánh xạ 1:1 tới OS threads.

### “Virtual threads làm CPU chạy nhanh hơn”

Sai. CPU-bound work vẫn phụ thuộc năng lực xử lý thực tế và có thể cần bounded parallelism.

### “Đổi executor sang virtual threads thì không cần queue/backpressure”

Sai. Admission control và các giới hạn của database/HTTP/API còn quan trọng hơn khi ứng dụng dễ tạo nhiều tác vụ đồng thời.

### “Virtual threads luôn unmount khi block”

Không thể khẳng định với mọi thư viện/native operation/JDK. Cần xem cơ chế runtime, pinning và JFR/observability thực tế.

### “Bất cứ `synchronized` nào cũng pin virtual thread trên mọi JDK”

Sai. Hành vi trên JDK 21–23 khác sau cải tiến JEP 491 ở JDK 24; ngay cả khi không pin, lock contention vẫn có thể giới hạn throughput.

### “Chỉ cần một fixed virtual-thread pool là an toàn”

Không nhất thiết. Virtual threads thường được tạo theo task; việc giới hạn resource nên áp dụng theo chính resource. Fixed pool có thể che giấu thiếu backpressure hoặc làm mất lợi ích chờ I/O.

### “ThreadLocal hoạt động giống hệt về chi phí khi có 100.000 requests”

Sai. Mỗi virtual thread có thể có ThreadLocal state. Lưu object lớn hoặc transaction resource per thread có thể gây áp lực bộ nhớ và lifecycle.

### “Không thấy lỗi khi startup nghĩa là driver/agent hỗ trợ”

Sai. Lỗi có thể xuất hiện ở transaction tải cao, tracing, timeout, native call, cancellation hoặc pinning.

### “Bật virtual threads là đã dùng structured concurrency”

Sai. Virtual threads là execution primitive; structured concurrency là mô hình lifetime/cancellation khác và API tùy release có thể ở trạng thái preview.

## 23. Checklist trước khi công bố migration thành công

- [ ] Đã xác định JDK runtime hỗ trợ virtual threads và phiên bản framework/driver tương ứng.
- [ ] Đã phân loại CPU-bound, blocking I/O, native calls và background tasks.
- [ ] Đã có baseline throughput, p95/p99, CPU, heap, queue và downstream capacity.
- [ ] Đã phân biệt virtual thread count với CPU parallelism.
- [ ] Đã kiểm tra fixed pool/queue cũ đang vô tình giới hạn tài nguyên nào.
- [ ] Đã bổ sung bounded admission, rate limits, timeouts và cancellation.
- [ ] Đã giữ connection pool và transaction boundaries đúng nghiệp vụ.
- [ ] Đã kiểm tra `ThreadLocal`, MDC, security context, transaction context và cleanup.
- [ ] Đã kiểm tra shared mutable state, race conditions và deadlocks.
- [ ] Đã đánh giá pinning với cách chẩn đoán phù hợp JDK 21–23 hoặc 24+.
- [ ] Đã kiểm tra JNI/native integration khi có.
- [ ] Đã đảm bảo executor/task lifecycle và shutdown có owner.
- [ ] Đã thử burst/overload, không chỉ lưu lượng thấp.
- [ ] Đã theo dõi downstream saturation và lỗi rate limit.
- [ ] Đã kiểm thử artifact và JVM thực tế của production.
- [ ] Đã cập nhật dashboard/JFR/runbook cho virtual threads.
- [ ] Đã có chiến lược rollout từng phần và rollback.
- [ ] Đã dựa trên dữ liệu đo được, không dựa vào kỳ vọng tốc độ “miễn phí”.

## 24. Kết luận

Thread pools giải quyết việc tái sử dụng và giới hạn platform workers, trong khi virtual threads giúp Java viết code blocking theo phong cách đơn giản mà vẫn duy trì concurrency cao cho nhiều tác vụ chờ I/O. Nhưng **đổi mô hình thực thi không làm biến mất các giới hạn vật lý và nghiệp vụ**: CPU cores, database connections, API rate limits, heap, transaction locks, ThreadLocal state và khả năng tương thích của driver/agent vẫn quyết định sức chứa thực tế.

Trong Java Advance Compatibility Migration, hãy chọn virtual threads khi workload thật sự có lợi, dùng JDK và framework được hỗ trợ, bảo vệ tài nguyên downstream bằng backpressure/admission control, xem lại pinning theo đúng thế hệ JDK và quản lý cancellation/lifetime rõ ràng. Chỉ công bố cải thiện sau khi load test trên runtime thật cho thấy throughput, latency, ổn định và hiệu quả tài nguyên đạt mục tiêu. **Virtual threads là công cụ mở rộng concurrency, không phải phép thay thế toàn diện cho thiết kế hệ thống chịu tải.**
