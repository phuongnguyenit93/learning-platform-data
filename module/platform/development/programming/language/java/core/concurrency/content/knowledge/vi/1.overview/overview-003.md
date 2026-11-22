# CPU-bound và I/O-bound: chọn cách thực thi trong Java

Khi xử lý đồng thời trong Java, câu hỏi đầu tiên cần trả lời là: **tác vụ dùng CPU để tính toán phần lớn thời gian, hay chủ yếu chờ một tài nguyên bên ngoài?** Đặc tính này quyết định số lượng worker, mô hình API, cơ chế giới hạn tải và chỉ số cần đo. Bài này tập trung vào Java nói chung (thread, executor, I/O, virtual thread); các cơ chế riêng của Spring được học ở chương tương ứng.

## 1. Phân biệt CPU-bound, I/O-bound và workload hỗn hợp

**CPU-bound**: phần lớn thời gian hữu ích của tác vụ tiêu tốn cho tính toán trên CPU, ví dụ nén dữ liệu, hashing, xử lý ảnh, thuật toán số học, parse dữ liệu lớn đã nằm trong RAM. Nếu CPU đã bận tối đa, tăng số thread không tăng số phép toán CPU thực thi đồng thời; quá nhiều runnable thread còn tăng chuyển ngữ cảnh và chi phí cache.

**I/O-bound**: tác vụ dành nhiều thời gian chờ thao tác bên ngoài hoàn thành, như đọc/ghi đĩa, truy vấn database, chờ HTTP response, chờ socket. Với blocking I/O và platform thread truyền thống, thread có thể bị giữ trong lúc chờ dù không dùng CPU để tính toán yêu cầu ấy. Cho nhiều tác vụ cùng chờ thường tăng thông lượng, nhưng không thể bỏ qua giới hạn connection, quota, heap và downstream.

**Mixed workload**: các pha có đặc tính khác nhau. Ví dụ nhận ảnh (chờ mạng) → giải mã/resize (CPU) → tải lên storage (chờ mạng). Không nên gán nhãn CPU-bound/I/O-bound một lần cho cả ứng dụng; hãy phân loại **từng pha** và xác định nút nghẽn.

| Dấu hiệu | Khả năng | Cần kiểm chứng bằng |
| --- | --- | --- |
| CPU sát giới hạn, có nhiều runnable thread, tăng pool không cải thiện throughput | CPU-bound | CPU profiler, quota CPU, độ lớn task, contention |
| CPU còn rảnh, request chờ socket/DB/đĩa lâu | I/O-bound | tracing latency, I/O metrics, connection pool |
| CPU thấp nhưng hệ thống chậm | Chờ I/O, khóa, hàng đợi hoặc rate limit | thread dump, lock contention, queue depth |
| CPU cao và nhiều request chậm | Hỗn hợp hoặc quá tải nhiều tài nguyên | đo CPU time, wait time và từng pha |

Cẩn thận với `Thread.State`: `WAITING`/`TIMED_WAITING` không luôn là I/O; thread có thể đợi lock, `Future.get()`, `Thread.sleep()`. `BLOCKED` là chờ monitor lock, không tự đồng nghĩa với blocking network I/O. Không kết luận chỉ từ một thread dump.

## 2. Mô hình thời gian, throughput và concurrency

Gọi `C` là thời gian CPU hữu ích của một tác vụ, `W` là thời gian chờ, và `T ≈ C + W` khi chưa tính thêm queue. `C/T` lớn cho thấy tính toán chi phối; `W/T` lớn cho thấy chờ chi phối. Đây là mô hình suy nghĩ, không phải công thức tự động chọn số thread.

- **Parallelism:** số công việc thực sự được CPU xử lý đồng thời, bị giới hạn bởi năng lực CPU vật lý/ảo và mức CPU được cấp.
- **Concurrency:** số công việc đang tiến triển xen kẽ hoặc cùng lúc, kể cả những công việc đang đợi I/O. Concurrency có thể lớn hơn parallelism nhiều lần.
- **Latency:** thời gian từ lúc nhận một tác vụ tới lúc xong, bao gồm thời gian chờ queue. **Throughput:** số tác vụ hoàn thành mỗi giây.
- **Tail latency:** p95/p99 cho biết các yêu cầu chậm; throughput tăng không có nghĩa latency vẫn tốt.

**Little’s Law** áp dụng khi hệ thống ổn định: `L = λ × R`, trong đó `L` là số tác vụ trung bình trong hệ thống, `λ` là throughput (tác vụ/giây), `R` là thời gian trung bình (giây). Nếu mục tiêu là 100 request/giây và mỗi request mất trung bình 0,2 giây thì trung bình cần khoảng 20 request đồng thời đang ở trong hệ thống. Đây là ước lượng số request in-flight, **không phải mệnh lệnh đặt thread pool = 20**; giới hạn kết nối, độ biến thiên latency, rate limit và queue vẫn quyết định mức an toàn.

Với CPU-bound, định luật Amdahl giải thích phần thuật toán không song song hóa được sẽ giới hạn mức tăng tốc. Tạo nhiều thread không làm tăng số core, không loại bỏ khóa, cache contention hay chi phí phân phối task. Với I/O-bound, concurrency giúp che thời gian chờ nhưng quá nhiều request có thể làm downstream chậm đi và tạo vòng lặp quá tải.

## 3. Chọn mô hình thực thi trong Java

| Tình huống | Lựa chọn thường hợp lý | Điều cần chú ý |
| --- | --- | --- |
| Tính toán nặng trên nhiều tập dữ liệu độc lập | Fixed-size `ExecutorService` gần số CPU khả dụng | Benchmark độ lớn task, contention, memory bandwidth |
| Thuật toán chia để trị, tác vụ con không đồng đều | `ForkJoinPool` nếu thật sự phù hợp | Work-stealing có overhead; tránh blocking dài không quản lý |
| Blocking I/O trên Java 17 | Pool platform thread hữu hạn, bounded queue/admission control | Một thread bị giữ khi đợi; hạn chế thread, memory, connection |
| Nhiều blocking I/O độc lập trên Java 21+ | `Executors.newVirtualThreadPerTaskExecutor()` + giới hạn I/O | Rẻ hơn platform thread khi chờ; không làm CPU nhanh hơn |
| API đã có non-blocking/asynchronous I/O | `HttpClient.sendAsync`, các API NIO/async thích hợp | Callback/completion, error handling, timeout, executor cho pha CPU |
| Vài task rất nhỏ | Chạy tuần tự | Tránh overhead lập lịch và đồng bộ |
| Pipeline I/O → CPU → I/O | Điều tiết riêng mỗi pha | Tránh blocking trên completion/event-loop thread; không làm nghẽn CPU pool |

**Platform thread** truyền thống tương ứng với thread hệ điều hành và tốn tài nguyên hơn khi có rất nhiều yêu cầu chờ. **Virtual thread (ổn định từ Java 21)** được JVM lên lịch trên carrier platform thread; khi đi vào thao tác blocking tương thích, carrier có thể được dùng cho tác vụ khác. Java code vẫn có thể viết tuần tự, nhưng virtual thread không tạo thêm core CPU và không tăng quota của database/API.

**Asynchronous I/O** nghĩa là API trả lại kết quả tương lai hoặc callback để thread gọi có thể làm việc khác trong lúc chờ I/O. `CompletableFuture` tự nó không biến lời gọi blocking thành non-blocking: bọc mã blocking trong `supplyAsync` vẫn cần một thread để chạy. Các tác vụ async không truyền executor thường dùng `ForkJoinPool.commonPool()`; dồn blocking I/O dài vào common pool có thể ảnh hưởng các công việc khác.

## 4. Ví dụ CPU-bound trên Java 17: fixed pool

Ví dụ chạy độc lập sau chia bài toán đếm số nguyên tố từ 2 đến 100 thành bốn đoạn. Dữ liệu nhỏ chỉ để minh họa cấu trúc; **không dùng kết quả thời gian chạy để chứng minh multi-thread nhanh hơn**.

Tạo `CpuBoundExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CpuBoundExample {
    private static boolean isPrime(int n) {
        if (n < 2) return false;
        for (int d = 2; (long) d * d <= n; d++) {
            if (n % d == 0) return false;
        }
        return true;
    }

    private static int countPrimes(int from, int to) {
        int count = 0;
        for (int n = from; n <= to; n++) {
            if (isPrime(n)) count++;
        }
        return count;
    }

    public static void main(String[] args) throws Exception {
        int workers = Math.min(4, Runtime.getRuntime().availableProcessors());
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int start = 2; start <= 100; start += 25) {
                final int from = start;
                final int to = Math.min(start + 24, 100);
                futures.add(pool.submit(() -> countPrimes(from, to)));
            }

            int total = 0;
            for (Future<Integer> f : futures) total += f.get();
            System.out.println("So nguyen to tu 2 den 100: " + total);
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CpuBoundExample.java
java CpuBoundExample
```

Stdout chính xác:

```text
So nguyen to tu 2 den 100: 25
```

`submit` đưa `Callable` vào executor và trả `Future`; `get()` chờ, trả kết quả hoặc ném `ExecutionException` nếu task lỗi. Vòng cộng kết quả theo danh sách nên kết quả không phụ thuộc thứ tự chạy các worker. `shutdown()` không nhận task mới; trong ví dụ, mọi `get()` đã xong trước khi shutdown. Số worker lấy từ `availableProcessors()` chỉ là điểm bắt đầu: trong container/môi trường chia sẻ, cần xác minh CPU thực được cấp và đo throughput/latency. Với bài toán nhỏ hoặc ít task, tuần tự có thể nhanh hơn vì overhead.

**Lưu ý production:** `Executors.newFixedThreadPool` có queue không giới hạn kích thước trong triển khai chuẩn. Pool cố định **không** tự giới hạn số task đang chờ trong queue. Với nguồn request liên tục, dùng queue hữu hạn, backpressure hoặc admission control.

## 5. Ví dụ I/O-bound trên Java 17: pool platform thread có giới hạn

Để chạy offline và giữ output xác định, mã dùng `Thread.sleep(50)` **mô phỏng thời gian chờ**, không phải thao tác I/O thật và không dùng làm benchmark mạng/đĩa. Trong ứng dụng thực, vị trí này có thể là truy vấn DB hoặc HTTP blocking call đã cấu hình timeout.

Tạo `BlockingWaitExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BlockingWaitExample {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<String>> futures = new ArrayList<>();
            for (int i = 1; i <= 8; i++) {
                final int id = i;
                futures.add(pool.submit(() -> {
                    Thread.sleep(50); // Chỉ mô phỏng thời gian chờ I/O
                    return "ok-" + id;
                }));
            }

            for (Future<String> f : futures) f.get();
            System.out.println("Da hoan thanh " + futures.size() + " tac vu");
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac BlockingWaitExample.java
java BlockingWaitExample
```

Stdout:

```text
Da hoan thanh 8 tac vu
```

Bốn platform thread xử lý tám tác vụ; khi một thread chờ `sleep`, nó không xử lý task khác trong pool. Tăng số thread có thể cải thiện throughput nếu workload chủ yếu chờ I/O, nhưng bị giới hạn bởi stack memory, OS thread, connection pool, rate limit và downstream. `Future.get()` trong ví dụ không có timeout để minh họa luồng đơn giản; production phải đặt timeout ở client I/O và có thể dùng `get(timeout, unit)` cho deadline phía caller. Timeout của `get` **không tự hủy** thao tác đang chạy.

## 6. Java 21+: virtual thread cho blocking I/O

Virtual thread giúp xử lý nhiều blocking call mà không phải dành một platform thread riêng cho mỗi request chờ. Ví dụ sau chạy với Java 21+, không cần bật preview feature.

Tạo `VirtualThreadWaitExample.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadWaitExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                 Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> futures = new ArrayList<>();
            for (int i = 1; i <= 20; i++) {
                final int id = i;
                futures.add(executor.submit(() -> {
                    Thread.sleep(50); // Chỉ mô phỏng blocking I/O
                    return "ok-" + id;
                }));
            }

            for (Future<String> f : futures) f.get();
            System.out.println("Da hoan thanh " + futures.size() + " tac vu");
        }
    }
}
```

```bash
javac VirtualThreadWaitExample.java
java VirtualThreadWaitExample
```

Stdout:

```text
Da hoan thanh 20 tac vu
```

`newVirtualThreadPerTaskExecutor()` tạo virtual thread cho từng task. `try` quản lý vòng đời executor, đóng và chờ hoàn thành khi thoát scope. Đây vẫn là mô phỏng wait; không có bằng chứng benchmark I/O thật. Nếu thay `sleep` bằng phép tính CPU nặng, virtual thread **không** cho phép 20 tác vụ cùng tính trên 20 core khi máy chỉ có vài core.

**Không cần pool virtual thread nhỏ để “tiết kiệm thread”.** Thay vào đó phải giới hạn số request tới resource cụ thể: connection pool, semaphore, rate limiting và số pending task. Virtual thread vẫn chiếm heap cho stack/data mỗi tác vụ; có hàng vạn request chờ vẫn có thể gây OOM hoặc quá tải downstream. Trên một số JDK cũ (đặc biệt Java 21–23), blocking khi giữ `synchronized` monitor có thể pin carrier platform thread; các JDK mới đã cải tiến hành vi này. Dùng JFR và profile của runtime/thư viện đang triển khai để kiểm chứng, nhất là khi thư viện thực hiện blocking I/O trong critical section.

## 7. Khi đã có asynchronous I/O

`java.net.http.HttpClient` có từ Java 11. `sendAsync` trả `CompletableFuture<HttpResponse<T>>` để caller không phải chờ đồng bộ tới lúc nhận HTTP response. Đoạn sau là **snippet**, giả sử biến `endpoint` có kiểu `java.net.URI` và trỏ tới URI phù hợp; đoạn này không phải chương trình độc lập và không có stdout cố định:

```java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(endpoint)
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> response =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

CompletableFuture<Integer> length =
        response.thenApply(r -> r.body().length());
```

Import cần thiết: `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `java.time.Duration` và `java.util.concurrent.CompletableFuture`. `thenApply` biến đổi kết quả sau khi response có sẵn. Nếu bước xử lý body tiêu tốn CPU lớn, dùng `thenApplyAsync(..., cpuExecutor)` để tách sang executor CPU. Gọi `join()`/`get()` ngay trên completion thread hoặc event-loop có thể làm mất lợi ích non-blocking. Cần xử lý lỗi bằng `handle`/`exceptionally`, timeout và việc hủy chuỗi công việc.

**Async hay virtual thread?** Nếu API đã non-blocking và kiến trúc sử dụng pipeline `CompletableFuture` tốt, async hợp lý. Nếu phần lớn thư viện là blocking và chạy Java 21+, virtual thread giúp code tuần tự, `try/catch` và quản lý tài nguyên rõ ràng. Chọn theo API và workload hiện tại; cả hai đều phải kiểm soát tải.

## 8. Giới hạn tải: thread, queue, connection và deadline

Hai thứ phải điều tiết riêng: (1) số công việc **đang hoạt động/chờ tài nguyên**, (2) số công việc **đang xếp hàng chờ được thực thi**. Dùng fixed pool mà queue vô hạn có thể dẫn tới latency tăng rất lâu, memory tăng và cuối cùng quá tải. Với platform thread, `ThreadPoolExecutor` + `ArrayBlockingQueue` hữu hạn và rejection policy có chủ đích giúp giới hạn công việc nhận vào. `CallerRunsPolicy` đôi khi tạo backpressure nhưng có thể chặn caller và kéo theo tắc nghẽn lan truyền; phải kiểm tra đường đi request.

Có thể tham khảo heuristic cho blocking I/O trên platform thread: `N_threads ≈ N_cpu × U_target × (1 + W/C)`, trong đó `U_target` là mức CPU utilization mục tiêu, `W` là thời gian đợi, `C` là thời gian tính CPU. Chỉ dùng như **điểm xuất phát để thử nghiệm**, không phải giới hạn an toàn tuyệt đối vì context switch, lock, connection pool, queue và memory có thể chi phối. Với CPU-bound, bắt đầu với số worker xấp xỉ CPU hiệu dụng rồi đo. Với virtual thread, thay câu hỏi “pool bao nhiêu thread?” bằng “tối đa bao nhiêu I/O call đang dùng resource này?”.

Ví dụ **snippet** giới hạn tối đa 20 lời gọi blocking I/O cùng lúc khi sử dụng virtual thread:

```java
Semaphore permits = new Semaphore(20);

try {
    permits.acquire();
    try {
        // Thực hiện một blocking I/O call có timeout tại đây.
    } finally {
        permits.release();
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Hủy hoặc báo trạng thái phù hợp.
}
```

Cần import `java.util.concurrent.Semaphore`; body I/O do ứng dụng bổ sung. `Semaphore` giới hạn phần thực thi **sau khi lấy permit**, không giới hạn số virtual thread đang đợi permit. Nếu input đến liên tục vô hạn, cần thêm bounded request queue, giới hạn số task chờ, admission control hoặc rate limit tại nguồn.

Ví dụ DB pool chỉ có 30 connection: dù có thể tạo 10.000 virtual thread, không thể có 10.000 truy vấn chiếm connection đồng thời nếu pool giới hạn 30. Khi thấy thời gian đợi lấy connection cao, tối ưu truy vấn, transaction, workload và mức tải trước khi tăng concurrency.

## 9. Timeout, hủy, lỗi và lifecycle

- **Timeout tại I/O client**: cấu hình connect/read/request timeout hoặc deadline tùy API; tránh request chờ vô hạn. `Future.get(timeout, unit)` chỉ giới hạn thời gian caller chờ, không tự dừng task đang chạy.
- **Cancellation**: `Future.cancel(true)` có thể interrupt thread đang chạy, nhưng task phải hợp tác và API I/O có semantics hủy riêng. Không giả định thao tác bên ngoài đã rollback khi Java task bị hủy.
- **Interrupt**: khi bắt `InterruptedException` mà không ném tiếp, thông thường khôi phục bằng `Thread.currentThread().interrupt()` rồi kết thúc/điều phối hủy phù hợp. Không nuốt interrupt.
- **Lỗi từ task**: `Future.get()` bọc lỗi trong `ExecutionException`; `CompletableFuture.join()` có thể bọc trong `CompletionException`. Ghi log nguyên nhân gốc và correlation id, tránh chỉ thấy wrapper.
- **Đóng executor**: dừng nhận task, chờ có deadline và dùng `shutdownNow()` khi chính sách yêu cầu. Quản lý vòng đời executor ở component phù hợp; không tạo platform-thread executor cho từng request rồi bỏ mặc.
- **Dữ liệu dùng chung**: immutable object, ownership, concurrent collection hoặc synchronization thích hợp để tránh data race. Tăng/giảm thread count không giải quyết deadlock, race condition hay lock contention.

## 10. Cách đo và ra quyết định dựa trên số liệu

1. **Xác định mục tiêu**: throughput, p95/p99 latency, CPU cost, memory, tail latency hay lỗi khi downstream chậm? Nắm giới hạn CPU container/VM, connection và rate limit.
2. **Lấy baseline dưới tải đại diện**: requests/sec, latency trung bình và p95/p99, CPU sử dụng, heap/GC, queue depth, active thread, active connection và timeout/errors.
3. **Định vị nút nghẽn**: Java Flight Recorder (JFR), CPU profiler, thread dump (`jcmd <pid> Thread.print`), application tracing và metric I/O. Đo CPU time và wall-clock time của từng pha; CPU thấp có thể do lock, I/O hoặc throttling.
4. **Thử từng chiến lược**: tuần tự so với fixed CPU pool cho tác vụ tính toán; platform-thread bounded pool/virtual thread/async cho I/O. Giữ dữ liệu và downstream tương đương; tăng concurrency có kiểm soát.
5. **Quan sát điểm gãy**: nếu thêm concurrency không tăng throughput mà queue, p99, timeout hoặc memory tăng thì hệ thống đã chạm nút nghẽn. Giảm tải hoặc cải thiện tài nguyên/thuật toán tương ứng.
6. **Kiểm tra sau triển khai**: load spike, downstream slowdown, client disconnect/cancellation, graceful shutdown; đặt cảnh báo trên queue wait, saturation, errors và resource exhaustion.

`Runtime.getRuntime().availableProcessors()` trong JVM hiện đại thường phản ánh cấu hình processor mà runtime thấy, có thể chịu ảnh hưởng cgroup/container; không tự coi đó là bảo đảm hiệu năng. Benchmark CPU-bound phải đủ lớn để chi phí tạo task không chi phối, và đo cả memory/cache contention.

## 11. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo hàng trăm thread cho CPU-bound dù chỉ vài core | Context switch/cache contention, chậm hơn | CPU pool sát năng lực CPU, đo và điều chỉnh |
| Chạy blocking I/O dài trong `ForkJoinPool.commonPool()` tùy tiện | Starvation và khó kiểm soát queue | Dùng executor I/O riêng, virtual thread hoặc async API |
| Tin virtual thread làm thuật toán tính toán nhanh hơn | CPU vẫn nghẽn, quá nhiều runnable task | Giới hạn CPU parallelism, tối ưu thuật toán |
| Tin virtual thread đồng nghĩa downstream vô hạn | Hết DB connections, rate limit, socket/heap | Semaphore, connection cap, queue bound, timeout |
| Dùng `Thread.sleep` như benchmark HTTP/DB | Đo giả lập, bỏ qua downstream và latency đuôi | Benchmark I/O thật trong điều kiện vận hành |
| Chỉ xem throughput trung bình | Bỏ sót p99, queue và lỗi | Theo dõi tail latency, queue, saturation, errors |
| `get()` không deadline, nuốt interrupt | Request treo và shutdown khó | Timeout, cancel và propagation đúng |
| Tạo executor rồi không đóng | Rò rỉ thread/resource | Quản lý vòng đời rõ ràng |

## 12. Bốn tình huống áp dụng

**A. Hash một triệu bản ghi trong RAM.** Chủ yếu CPU-bound: chia thành lô độc lập, dùng số worker gần số CPU hữu dụng, đo kích thước lô và memory pressure. Virtual thread không tăng tốc hash.

**B. Tổng hợp kết quả từ 10 HTTP API.** Chủ yếu chờ I/O: nếu dùng blocking client trên Java 21+, virtual thread + timeout mỗi call + giới hạn đồng thời theo API là một lựa chọn dễ đọc. Nếu API đã hỗ trợ `sendAsync`, pipeline bất đồng bộ cũng phù hợp. Không vượt quota dịch vụ.

**C. Download ảnh → resize → upload.** Download/upload I/O-bound; resize CPU-bound. Điều tiết từng pha và chuyển bước resize sang CPU executor; tránh xử lý ảnh nặng trực tiếp trên event-loop/completion thread. Cân nhắc stream để không lưu cả file lớn trong heap.

**D. Database query với pool 30 connection.** Tăng platform/virtual thread không tạo thêm connection. Nếu query chậm, đo thời gian chờ connection, thời gian SQL, transaction, index và throughput của DB; tăng concurrency chỉ khi DB và pool thực sự chịu được.

## 13. Checklist trước khi chốt thiết kế

- Từng pha là **tính toán**, **chờ I/O**, hay **chờ lock/queue**? Có profile và số đo không?
- Java 17 hay Java 21+? API hỗ trợ non-blocking thật hay chỉ bọc blocking call trong `CompletableFuture`?
- CPU được cấp thực tế là bao nhiêu? Downstream cho phép bao nhiêu connection/request cùng lúc?
- Active tasks và pending queue bị giới hạn thế nào? Khi overload sẽ chờ, từ chối hay giảm tải?
- Có timeout, error propagation, cancellation, xử lý interrupt và đóng executor đúng chưa?
- Thử tải thực tế có cải thiện throughput **và** p95/p99 mà không làm tăng errors, queue, memory hoặc saturation không?

**Nguyên tắc áp dụng:** CPU-bound → giới hạn tính toán song song theo năng lực CPU; I/O-bound → dùng concurrency để che thời gian chờ trong giới hạn tài nguyên; Java 21+ virtual thread giúp code blocking I/O quy mô lớn rõ ràng; API non-blocking hiện hữu có thể tận dụng async. Với nghiệp vụ hỗn hợp, chia giai đoạn và đo đạc từng phần.