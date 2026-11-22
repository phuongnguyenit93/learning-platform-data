# Kiểm chứng tác vụ đồng thời khi đổi JVM hoặc thư viện concurrency

Một hệ thống Java có thể vượt qua toàn bộ bước biên dịch khi nâng từ JDK 8 lên 11, 17 hoặc 21, nhưng vẫn phát sinh các lỗi khó tái hiện: mất cập nhật, xử lý cùng một yêu cầu hai lần, tác vụ không kết thúc, thời gian đáp ứng tăng đột biến hoặc kết quả chỉ sai dưới tải cao. Đặc biệt, khi nâng thư viện thực thi bất đồng bộ, thay thread pool, cập nhật reactive framework hoặc bắt đầu dùng virtual threads, **lịch chạy của các tác vụ có thể khác trước** dù business logic gần như không đổi.

Vì vậy, kiểm chứng concurrency trong Java Advance Compatibility Migration không chỉ là chạy thử vài tác vụ và thấy không có exception. Cần xác minh đồng thời **tính đúng đắn (safety)**, **khả năng hoàn thành (liveness)**, **khả năng xử lý tải (throughput/latency)** và **khả năng quan sát, hủy, khôi phục** trong môi trường JDK/thư viện mới.

Bài học thuộc chương **JVM và hiệu năng**, tập trung vào cách xây dựng baseline, thiết kế phép thử có thể tái lập, phát hiện lỗi do interleaving thay đổi và kiểm chứng thực tế khi đổi JVM hoặc thư viện concurrency. Các ví dụ dùng Java/JUnit và những API concurrency phổ biến; nguyên tắc áp dụng tương tự với executor, scheduler, reactive pipeline và nền tảng xử lý tác vụ khác.

## 1. Kiểm chứng concurrency thực sự là kiểm chứng điều gì?

### 1.1. Bốn trục chất lượng cần tách riêng

| Trục | Câu hỏi phải trả lời | Ví dụ lỗi |
| --- | --- | --- |
| **Safety** | Kết quả và bất biến nghiệp vụ có luôn đúng không? | Hai worker cùng trừ số dư làm mất một cập nhật; xử lý trùng một event. |
| **Liveness** | Tác vụ có tiến triển và kết thúc khi điều kiện phù hợp không? | Deadlock; một Future chờ mãi; task bị starvation. |
| **Performance** | Dưới cùng tải, throughput, latency và tài nguyên thay đổi ra sao? | p99 tăng vì thread-pool queue; GC tăng; CPU cao nhưng throughput thấp. |
| **Operability** | Có thể dừng, hủy, quan sát và phục hồi tác vụ không? | Shutdown không thoát; interrupt bị nuốt; không có metric queue hoặc trace. |

Một lần test thành công ở trục safety không chứng minh hệ thống không deadlock. Ngược lại, throughput tăng không chứng minh không có lost update. Hãy ghi nhận các trục này độc lập trong báo cáo migration.

### 1.2. Vì sao đổi JDK hoặc thư viện khiến lỗi “cũ” lộ ra?

Một ứng dụng có data race có thể chạy ổn định trong một môi trường cụ thể do may mắn về scheduling. Sau migration, những thay đổi sau có thể làm interleaving khác:

- Compiler, JIT, garbage collector hoặc CPU architecture khác.
- Số CPU mà JVM nhận diện được trong container thay đổi, kéo theo kích cỡ pool mặc định.
- Bản thư viện mới thay đổi executor, queue, timeout, batching hoặc callback scheduling.
- Reactive scheduler chuyển task sang thread khác; context không còn được truyền theo cách cũ.
- Workload có nhiều tác vụ hoặc blocking operations hơn.
- Nâng API bất đồng bộ thay đổi thứ tự completion hoặc cách lan truyền exception.
- Virtual threads (Java 21+) thay mô hình tạo thread cho nhiều task chặn I/O.

**Điểm phân biệt quan trọng:** JDK mới không nhất thiết tạo ra bug. Nó có thể chỉ làm lộ một giả định concurrency vốn chưa đúng theo Java Memory Model. Mặt khác, thư viện có thể thực sự thay đổi contract, default executor hoặc cơ chế cancellation. Điều tra phải dựa trên bằng chứng, không quy mọi lỗi cho scheduler mới.

## 2. Chụp baseline trước khi đổi JVM hoặc dependency

### 2.1. Baseline phải gắn với đúng cấu hình

Ghi tối thiểu:

- JDK vendor, phiên bản đầy đủ và JDK thực chạy ứng dụng.
- OS, kiến trúc CPU, số processor JVM nhận diện, container CPU/memory quota.
- JVM flags liên quan GC, heap, container awareness và thread scheduling.
- Phiên bản thư viện concurrency, framework, reactive runtime và dependency bắc cầu.
- Thread-pool cấu hình: core/max size, queue type/capacity, keep-alive, rejection policy.
- Workload: số request/task đồng thời, tỉ lệ CPU-bound/I/O-bound, payload và phân phối độ trễ downstream.
- Timeout, retry, backoff, idempotency và shutdown policy.
- Metrics và traces ở trạng thái bình thường và dưới tải.
- Bản test/report hiện có: số task hoàn thành, số lỗi, p50/p95/p99, deadlock/leak đã biết.

Ví dụ, một service có thể dùng `Executors.newFixedThreadPool(16)` nhưng executor của `CompletableFuture.supplyAsync(...)` lại mặc định dùng `ForkJoinPool.commonPool()` nếu không truyền executor. Cần ghi cả **executor tường minh và executor ngầm định**.

### 2.2. Tạo ma trận trước/sau

| Mẫu | JDK | Thư viện concurrency | Workload | Mục tiêu |
| --- | --- | --- | --- | --- |
| A – baseline | JDK cũ | Lib cũ | Tải kiểm soát | Chốt hành vi và số liệu hiện tại. |
| B – chỉ JDK đổi | JDK đích | Lib cũ nếu được hỗ trợ | Cùng tải | Tách tác động JVM. |
| C – chỉ lib đổi | JDK còn được hỗ trợ | Lib mới | Cùng tải | Tách tác động thư viện. |
| D – tổ hợp đích | JDK đích | Lib mới | Cùng tải | Xác nhận cấu hình sẽ triển khai. |

Không phải mọi tổ hợp đều được nhà cung cấp hỗ trợ. Nếu B hoặc C là tổ hợp không hợp lệ, **không ép chạy để kết luận compatibility**. Thay bằng những chặng upgrade được hỗ trợ và ghi rõ giới hạn của phép so sánh.

### 2.3. Chọn invariants thay vì “đúng thứ tự thread”

Đối với concurrency, không nên thiết kế test yêu cầu thread A luôn chạy trước thread B nếu không có ràng buộc happens-before thật sự. Hãy kiểm tra tính chất bất biến:

- Tổng số giao dịch được ghi nhận bằng số giao dịch thành công được chấp nhận.
- Mỗi task có một trạng thái kết thúc hợp lệ: completed, failed hoặc cancelled.
- Không có task ở trạng thái xử lý vô hạn sau khi deadline đã hết.
- Không có hai worker cùng sở hữu một lock/lease độc quyền tại cùng thời điểm.
- Không có duplicate side effect khi retry.
- Đầu ra tương đương về mặt nghiệp vụ, dù completion order có thể khác.
- Queue và số tác vụ đang chờ bị chặn theo chính sách, không tăng vô hạn.

## 3. Java Memory Model: nguồn gốc của nhiều lỗi ẩn

### 3.1. Data race và visibility

Xem một biến đếm:

```java
public final class UnsafeCounter {
    private int value;

    public void increment() {
        value++;
    }

    public int get() {
        return value;
    }
}
```

`value++` là một thao tác **đọc → cộng → ghi**, không phải một cập nhật atomic. Hai thread có thể cùng đọc giá trị cũ rồi ghi cùng một giá trị mới, dẫn đến lost update.

Tệ hơn, nếu không có cơ chế đồng bộ thích hợp, thread khác không có bảo đảm nhìn thấy bản cập nhật theo kỳ vọng. Test có thể pass hàng nghìn lần nhưng vẫn sai theo Java Memory Model.

### 3.2. `volatile` không biến phép cộng thành atomic

`volatile` cung cấp những bảo đảm về visibility và ordering theo Java Memory Model cho truy cập biến, nhưng không biến toàn bộ biểu thức đọc-sửa-ghi thành atomic.

```java
private volatile int value;

void increment() {
    value++; // Vẫn không atomic.
}
```

Đây là lỗi cần phân biệt khi migration. Tăng tần suất chạy test chỉ có thể làm lỗi xuất hiện thường hơn; nó không biến code thành đúng.

### 3.3. Dùng primitive đồng bộ phù hợp

Với bộ đếm đơn giản:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class SafeCounter {
    private final AtomicInteger value = new AtomicInteger();

    public int incrementAndGet() {
        return value.incrementAndGet();
    }

    public int get() {
        return value.get();
    }
}
```

Với invariant liên quan nhiều biến, có thể cần `synchronized`, `Lock`, transaction hoặc thiết kế không chia sẻ state. Dùng nhiều `AtomicInteger` riêng lẻ không tự bảo đảm một bất biến cần cập nhật **đồng thời nhiều trường**.

### 3.4. Happens-before là điều kiện để tin cậy vào quan sát

Một số quan hệ happens-before phổ biến trong Java:

- Unlock của một monitor xảy ra trước lock kế tiếp của cùng monitor.
- Ghi vào một biến `volatile` xảy ra trước lần đọc tiếp theo phù hợp với quan hệ synchronization của biến đó.
- Những thao tác trước khi gọi `Thread.start()` xảy ra trước hành động trong thread được bắt đầu.
- Các hành động trong một thread xảy ra trước khi thread khác `join()` thành công.
- Hành động trong task có quan hệ memory consistency với việc submit và lấy kết quả thông qua các API `ExecutorService`/`Future` theo contract.
- Những API đồng bộ trong `java.util.concurrent` công bố memory-consistency effects tương ứng.

Những quan hệ này giúp thiết kế test đúng. Chỉ chờ bằng `Thread.sleep(100)` **không tạo một quan hệ happens-before phù hợp** giữa producer và consumer và không phải cách xác minh visibility.

### 3.5. Safe publication và đối tượng bất biến

Nếu một object được chia sẻ giữa các thread trước khi xây dựng xong, thread khác có thể nhìn thấy state không như dự kiến.

Ưu tiên:

- Immutable objects, field `final` và construction an toàn.
- Publish qua concurrent collection, `volatile` reference, lock hoặc queue có bảo đảm phù hợp.
- Không để `this` thoát ra ngoài constructor trước khi khởi tạo xong.
- Tránh dùng mutable singleton không đồng bộ cho dữ liệu theo request.

Khi nâng framework DI hoặc thay đổi lifecycle, hãy kiểm tra các object có được publish sớm hơn hoặc gọi từ nhiều thread hơn không.

## 4. Những API concurrency hay thay đổi hành vi khi migration

### 4.1. `ExecutorService` và ThreadPoolExecutor

`ThreadPoolExecutor` có những quyết định quan trọng:

- Core pool size và maximum pool size.
- Queue: bounded hay unbounded.
- Keep-alive và thread factory.
- Rejected execution handler.
- Cách shutdown, interrupt và chờ task kết thúc.
- Cách task xử lý blocking I/O.

Ví dụ một pool với queue giới hạn:

```java
import java.util.concurrent.*;

ExecutorService executor = new ThreadPoolExecutor(
        4,
        8,
        30,
        TimeUnit.SECONDS,
        new ArrayBlockingQueue<Runnable>(200),
        new ThreadPoolExecutor.AbortPolicy()
);
```

Khi đạt giới hạn, `AbortPolicy` có thể ném `RejectedExecutionException` thay vì âm thầm giữ thêm mọi task. Đó là một lựa chọn backpressure/rejection cần phản ánh trong contract API của hệ thống.

Trái lại, một queue không giới hạn có thể giữ một lượng task lớn trong memory và làm p99 latency tăng mạnh trước khi service gặp vấn đề. Cỡ pool không phải tham số đủ để mô tả khả năng xử lý tải; **queue và rejection policy quan trọng không kém**.

### 4.2. Thay đổi giá trị mặc định của framework

Khi nâng một framework, executor được auto-configure có thể đổi:

- Kích thước pool mặc định.
- Tên thread.
- Queue capacity.
- Cách chạy task khi không có executor được khai báo.
- Propagation của `ThreadLocal`, MDC hoặc security context.
- Cơ chế timeout và xử lý exception.

Do đó, kiểm thử phải xác minh **effective runtime configuration**, không chỉ nhìn file properties của phiên bản cũ. Một property bị rename/bỏ qua có thể khiến framework dùng default mới mà không báo lỗi rõ.

### 4.3. `CompletableFuture` và executor ngầm định

Ví dụ:

```java
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(() -> loadData());
```

Overload không truyền executor thường dùng `ForkJoinPool.commonPool()` theo contract của `CompletableFuture`, với những điều kiện triển khai cụ thể theo môi trường. Nếu cần cô lập tài nguyên, truyền executor rõ ràng:

```java
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(
                () -> loadData(),
                ioExecutor
        );
```

Điều cần kiểm chứng:

- `thenApply` có thể chạy trong thread hoàn thành stage trước hoặc thread gọi tùy tình huống; không coi nó tương đương `thenApplyAsync`.
- `thenApplyAsync` dùng executor theo overload và contract, có thể khác thread mà ứng dụng kỳ vọng.
- Exception được đóng gói trong `CompletionException` khi dùng `join()`, hoặc `ExecutionException` khi dùng `get()`.
- Thứ tự completion của nhiều future không đồng nghĩa thứ tự submission.
- Cancellation của `CompletableFuture` không đồng nghĩa luôn interrupt được tác vụ nền.

Nếu framework hoặc thư viện mới đổi cách tạo/combine future, cần test ngữ nghĩa của **failure propagation, timeout và cancellation**, không chỉ kết quả thành công.

### 4.4. `ForkJoinPool` và common pool

`ForkJoinPool` phù hợp với nhiều tác vụ có thể chia nhỏ, thường được nhắc tới trong parallel streams hoặc một số API asynchronous. Pool có cơ chế work stealing khác fixed thread pool truyền thống.

Một vài rủi ro:

- Đưa blocking I/O kéo dài vào pool thiết kế cho CPU-bound work.
- Sử dụng `parallelStream()` nhưng phụ thuộc vào thứ tự xử lý side effect.
- Dùng `ForkJoinPool.commonPool()` chung cho nhiều tính năng, khiến một nhóm task ảnh hưởng nhóm khác.
- Giả định mức song song luôn bằng một hằng số, trong khi JVM có thể nhìn thấy số CPU khác theo container/OS.

Không nên đo performance chỉ bằng tổng số thread tạo ra. Cần theo dõi task queue, blocked/parked threads, CPU utilization, latency và throughput.

### 4.5. `ScheduledExecutorService` và thời gian

Những task chạy định kỳ có thể khác hành vi khi:

- Máy chạy có clock/CPU khác.
- Tác vụ mất nhiều thời gian hơn chu kỳ.
- Timeout bị hiểu nhầm giữa duration và deadline.
- Framework đổi default scheduler hoặc queue.
- App pause do GC hoặc tài nguyên CPU bị giới hạn.

Phân biệt:

- `scheduleAtFixedRate`: lập lịch theo nhịp cố định về nguyên tắc; những lần thực thi của cùng task định kỳ không chạy chồng lên nhau theo contract của `ScheduledThreadPoolExecutor`.
- `scheduleWithFixedDelay`: chờ một khoảng delay sau khi lần chạy trước kết thúc.

Không viết test yêu cầu mỗi lần chạy có timestamp chính xác tuyệt đối. Hãy kiểm tra cửa sổ thời gian, số lần thực thi hợp lý, không có overlap ngoài contract và việc shutdown có dừng scheduler.

### 4.6. Reactive library và scheduler

Với Reactor, RxJava hoặc một runtime reactive khác, khái niệm tác vụ không nhất thiết tương ứng 1:1 với thread. Các toán tử như publish/subscribe scheduling, event loop và backpressure quyết định nơi callback chạy.

Khi nâng thư viện, cần đối chiếu migration guide về:

- Scheduler mặc định và thread affinity.
- Blocking call trong non-blocking/event-loop thread.
- Backpressure, buffer limit và overflow behavior.
- Retry/timeout semantics.
- Cancellation khi subscriber hủy.
- Propagation của tracing, security và MDC context.
- Ordering giữa các operators và signal terminal.

Không dùng `ThreadLocal` như thể mọi callback chắc chắn chạy cùng một thread. Nên dùng cơ chế context propagation được framework hỗ trợ và xác minh ở đường chạy thực tế.

### 4.7. Virtual threads khi chuyển sang Java 21+

Virtual threads trở thành một tính năng chuẩn từ Java 21. Chúng hỗ trợ mô hình thread-per-task với chi phí thấp hơn cho nhiều workload chặn I/O so với platform threads, nhưng **không tự làm CPU-bound work chạy nhanh hơn**.

Ví dụ Java 21+:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {
    for (int i = 0; i < 1000; i++) {
        executor.submit(() -> performBlockingIo());
    }
}
```

Một số điểm cần xác minh:

- Bounded **concurrency tới tài nguyên ngoài** vẫn cần thiết: database pool, HTTP downstream, file handles và rate limit có giới hạn dù virtual threads nhiều.
- Không dùng thread pool cũ làm throttle mà không thay bằng semaphore/bulkhead khi chuyển sang thread-per-task.
- `ThreadLocal`, MDC và request context có thể phát sinh chi phí hoặc vấn đề propagation tùy framework.
- Trong Java 21, một số tình huống liên quan `synchronized` và native/foreign calls có thể dẫn đến pinning; hành vi pinning và công cụ quan sát có thể thay đổi ở các JDK mới hơn, nên kiểm chứng theo **JDK đích**, không áp dụng kết luận của Java 21 cho mọi phiên bản.
- Shutdown, interrupt, deadline và exception handling vẫn cần contract rõ ràng.
- Một thư viện blocking cũ có thể tương thích về chức năng nhưng gây nghẽn resource ở mức downstream.

Virtual threads là thay đổi kiến trúc thực thi; test concurrency và load test phải được thiết kế lại theo nguồn giới hạn tài nguyên thực tế.

## 5. Safety: kiểm chứng kết quả và bất biến dưới cạnh tranh

### 5.1. Lost update

Giả sử hai task cùng tăng bộ đếm 1.000 lần; kết quả đúng là 2.000. Với `int value++` không đồng bộ, kết quả có thể thấp hơn.

Ví dụ một test được thiết kế để chứng minh cách dùng `AtomicInteger` đúng, dùng JUnit Jupiter:

```java
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class ConcurrentCounterTest {
    @Test
    void incrementsAreNotLost() throws Exception {
        int workers = 8;
        int perWorker = 1_000;
        AtomicInteger counter = new AtomicInteger();

        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new TimeoutException("Start signal missing");
                    }
                    for (int j = 0; j < perWorker; j++) {
                        counter.incrementAndGet();
                    }
                    return null;
                }));
            }

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            for (Future<?> f : futures) {
                f.get(10, TimeUnit.SECONDS);
            }

            assertEquals(workers * perWorker, counter.get());
        } finally {
            start.countDown(); // Không để worker chờ nếu assertion lỗi.
            pool.shutdownNow();
            assertTrue(pool.awaitTermination(10, TimeUnit.SECONDS));
        }
    }
}
```

Mục đích của `CountDownLatch` ở đây là **tăng khả năng các task bắt đầu gần nhau**, không phải điều khiển chính xác từng instruction. Test này giúp kiểm tra một invariant quan trọng, nhưng không chứng minh mọi thuật toán lock-free đều đúng trên mọi interleaving.

Với test thử một implementation không an toàn, có thể dùng cùng harness để tìm lỗi. Tuy nhiên **đừng assert rằng race nhất định phải xuất hiện ở mỗi lần chạy**: data race có thể không biểu lộ trong một lần test.

### 5.2. Atomicity của nhiều bước

Xét một nghiệp vụ “kiểm tra còn chỗ rồi đặt vé”:

```java
if (availableSeats.get() > 0) {
    availableSeats.decrementAndGet();
    issueTicket();
}
```

`AtomicInteger` chỉ đảm bảo mỗi thao tác atomic riêng lẻ, **không đảm bảo cả chuỗi check → decrement → side effect là một transaction**. Hai task có thể cùng thấy còn 1 chỗ rồi cùng đặt.

Các lựa chọn đúng có thể là CAS loop, lock, transaction database, compare-and-set ở store hoặc một hàng đợi xử lý độc quyền, tùy hệ thống. Test cần kiểm tra bất biến “không phát hành quá số vé”, không chỉ kiểm tra số lượt gọi `decrementAndGet`.

### 5.3. Concurrent collections

Sử dụng `ConcurrentHashMap`, `ConcurrentLinkedQueue` hay `BlockingQueue` không có nghĩa mọi logic xung quanh chúng đều atomic.

Ví dụ không an toàn cho một thao tác compound:

```java
if (!map.containsKey(key)) {
    map.put(key, createValue());
}
```

Nhiều thread có thể cùng chạy `createValue()`. Với contract thích hợp, dùng API atomic như `computeIfAbsent`:

```java
Value value = map.computeIfAbsent(key, k -> createValue(k));
```

Tuy nhiên mapping function có các giới hạn về side effect, reentrancy, blocking và exception theo contract của `ConcurrentHashMap`. Không mặc định mọi callback sẽ chạy đúng một lần trong mọi cấu hình, đặc biệt nếu thay đổi cấu trúc map hoặc kết hợp retry ở tầng ứng dụng.

### 5.4. Idempotency của task nghiệp vụ

Với message queue hoặc job processing, một task có thể bị chạy lại sau timeout/retry. Thread safety trong JVM **không đủ** bảo đảm idempotency của side effect ngoài JVM.

Bài test phải xem xét:

- Một event có ID giống nhau được nhận đồng thời hai lần.
- Worker bị crash giữa ghi DB và ack message.
- Task bị timeout nhưng downstream vẫn hoàn thành.
- Job được resubmit sau restart.
- Kết quả cuối cùng không được trừ tiền hai lần hay phát sinh hai đơn hàng.

Cơ chế xử lý có thể cần idempotency key, unique constraint, transaction hoặc outbox pattern. Đổi executor không giải quyết được các invariant nghiệp vụ phân tán này.

## 6. Liveness: deadlock, starvation, livelock và backlog

### 6.1. Deadlock do thứ tự lock

Hai thread lần lượt giữ hai lock theo thứ tự ngược nhau:

```java
synchronized (lockA) {
    synchronized (lockB) {
        update();
    }
}

// Một đường code khác:
synchronized (lockB) {
    synchronized (lockA) {
        update();
    }
}
```

Khi hai đường chạy xen kẽ, một thread giữ A chờ B và thread kia giữ B chờ A. Lỗi có thể hiếm khi lộ trên JDK cũ nhưng xuất hiện nhiều hơn dưới scheduler/load mới.

Hướng khắc phục: quy định **thứ tự lock nhất quán**, giảm lock scope, tránh gọi callback không kiểm soát trong khi giữ lock và dùng timeout/lock strategy phù hợp nếu cần.

### 6.2. Starvation trong fixed thread pool

Giả sử pool có hai thread và mỗi task lại submit task con vào **chính pool đó**, rồi đồng bộ chờ `Future.get()`:

```java
ExecutorService pool = Executors.newFixedThreadPool(2);

Callable<String> outer = () -> {
    Future<String> inner =
            pool.submit(() -> "done");
    return inner.get();
};
```

Nếu cả hai worker đang chạy hai `outer` tương tự, cả hai có thể chờ task con trong queue trong khi không còn worker rảnh để thực thi chúng. Đây là một dạng **thread starvation deadlock** do cấu trúc chờ, không nhất thiết có Java monitor deadlock.

Hướng xử lý: tránh blocking dependency cycle trong cùng limited pool; tách executor hợp lý, dùng asynchronous composition hoặc thiết kế pipeline không chặn worker.

### 6.3. Livelock và retry storm

Livelock xảy ra khi các thread vẫn hoạt động nhưng không tiến triển hữu ích. Ví dụ nhiều worker liên tục tranh cùng tài nguyên, retry ngay lập tức và gây áp lực lớn mà không có thành công.

Khi nâng thư viện retry/scheduler, kiểm tra:

- Retry có giới hạn và backoff/jitter không?
- Có phân biệt lỗi tạm thời và lỗi vĩnh viễn không?
- Có deadline toàn cục không?
- Có bulkhead/rate limit khi downstream lỗi không?
- Metrics có tách attempts, successes và failures không?

Throughput của “số lần retry” tăng không phải bằng chứng throughput nghiệp vụ tăng.

### 6.4. Queue backlog và backpressure

Cần kiểm tra mô hình:

```text
Request arrival rate
        |
        v
Admission / rate limit
        |
        v
Executor queue  ---> Rejected / dropped / backpressure policy
        |
        v
Workers
        |
        v
Downstream DB / HTTP / filesystem
```

Nếu tốc độ đến lớn hơn năng lực xử lý bền vững, queue sẽ phình ra. Một migration có thể thay queue mặc định từ bounded sang unbounded, làm service ít báo lỗi ngay nhưng tăng memory và tail latency.

Nên xác định chính sách khi quá tải: từ chối có kiểm soát, chờ giới hạn, shed load hoặc giảm tốc producer. Test tải phải kiểm tra cả **cách hệ thống thất bại khi quá tải**, không chỉ lúc tải vừa phải.

## 7. Cancellation, interruption và shutdown

### 7.1. `Future.cancel(true)` không phải “giết thread”

Với `Future`, `cancel(true)` yêu cầu hủy và có thể gửi interrupt tới thread đang chạy. Tác vụ có kết thúc kịp thời hay không phụ thuộc vào code và thao tác I/O/blocking có phản ứng với interrupt hay không.

Không nên viết logic nghiệp vụ dựa trên giả định rằng cancel chắc chắn dừng mọi side effect ngay lập tức.

### 7.2. Không nuốt `InterruptedException`

Một lỗi thường gặp:

```java
try {
    blockingOperation();
} catch (InterruptedException e) {
    // Bỏ qua, tiếp tục chạy.
}
```

Nếu thread đang được yêu cầu shutdown hoặc hủy, nuốt interrupt có thể khiến task chạy quá deadline. Một cách phù hợp với worker có thể dừng:

```java
try {
    blockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Nếu method khai báo `throws InterruptedException`, có thể ném tiếp thay vì tự xử lý. Việc restore interrupt flag phải đi cùng quyết định ngừng hoặc truyền tín hiệu lên caller. Đừng tiếp tục vòng lặp vô hạn sau khi restore flag mà không có chính sách thoát rõ ràng.

### 7.3. Shutdown theo hai giai đoạn

Với `ExecutorService` truyền thống:

```java
static void shutdownGracefully(ExecutorService pool)
        throws InterruptedException {
    pool.shutdown(); // Không nhận task mới.

    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
        pool.shutdownNow(); // Yêu cầu interrupt task đang chạy.

        if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
            System.err.println("Executor chưa kết thúc");
        }
    }
}
```

Ví dụ này cần được bọc ở mức ứng dụng để xử lý `InterruptedException` của thread điều phối, thời gian drain request, transaction, queue và resource cleanup phù hợp. `shutdownNow()` không bảo đảm tất cả task dừng ngay; một task không phản ứng với interrupt có thể tiếp tục chạy.

### 7.4. Deadline thay cho timeout rời rạc

Nếu một request có deadline 2 giây nhưng gọi ba bước tuần tự với timeout 2 giây mỗi bước, tổng thời gian có thể lên tới nhiều giây. Khi thay executor hoặc pipeline, lỗi deadline có thể lộ rõ hơn.

Nên chuyển **remaining time budget** qua các bước, đo bằng nguồn thời gian monotonic phù hợp (chẳng hạn `System.nanoTime()` cho duration), và giữ cancellation propagation nhất quán.

Không dùng `System.currentTimeMillis()` làm đồng hồ đo duration chính trong test nhạy timeout vì wall clock có thể bị điều chỉnh.

## 8. Thiết kế test concurrency đáng tin hơn

### 8.1. Không phối hợp task bằng `Thread.sleep`

Test kiểu:

```java
startWorker();
Thread.sleep(100);
assertEquals(expected, state);
```

dễ flaky vì 100 ms không chứng minh worker đã đến đúng giai đoạn. Trên CI bị giới hạn CPU hoặc khi JIT/GC hoạt động, worker có thể chưa chạy; ngược lại, sleep dài hơn chỉ làm test chậm chứ không đảm bảo correctness.

Ưu tiên:

- `CountDownLatch` để chờ readiness/start signal.
- `CyclicBarrier` hoặc `Phaser` cho các mốc nhiều bên.
- `BlockingQueue` để truyền sự kiện/kết quả.
- `Future.get(timeout, unit)` để chờ task hoàn thành và nhận exception.
- Test hook/instrumentation chỉ trong test để điều khiển các giai đoạn quan trọng.
- Clock/scheduler có thể điều khiển trong unit test với logic theo thời gian.

### 8.2. Start barrier không quyết định toàn bộ interleaving

Một `CountDownLatch` cho nhiều worker bắt đầu gần nhau giúp tạo contention, nhưng không bảo đảm thứ tự từng instruction. Đừng viết test dựa vào một chuỗi liên lịch chạy không được đồng bộ.

Nếu cần tái hiện một lịch chạy cụ thể, dùng test seam để dừng task ở các điểm trước/sau read/write và điều phối bằng barrier rõ. Với thuật toán concurrent phức tạp, cân nhắc công cụ stress hoặc model checking chuyên biệt.

### 8.3. Luôn đưa exception từ worker về test thread

Một lỗi hay gặp:

```java
executor.submit(() -> {
    throw new IllegalStateException("Worker failed");
});

// Test thread kết thúc mà không gọi Future.get().
```

Với `submit`, exception thường nằm trong `Future`. Nếu test không gọi `get()` hoặc kiểm tra completion, test có thể **pass giả**.

Nên lưu `Future` và gọi `get(timeout, unit)`; khi exception xảy ra, test nhận `ExecutionException` với cause thực tế để thất bại có ý nghĩa.

### 8.4. Timeout phải hữu hạn và dọn được tài nguyên

Một test có barrier bị kẹt vô hạn sẽ treo cả CI. Hãy:

- Chọn timeout có ý nghĩa cho readiness và completion.
- Dùng `finally` để phát tín hiệu giải phóng barrier nếu test thất bại.
- Hủy future và shutdown executor khi cần.
- Chờ termination với timeout.
- Giữ thread dump hoặc diagnostic khi timeout.
- Không dùng `assertTimeoutPreemptively` một cách thiếu cân nhắc nếu task chứa transaction, thread-local hoặc side effect không thể hủy; preemptive timeout có thể chạy phần test ở thread khác và không bảo đảm task nền đã dừng.

### 8.5. Tách correctness test và performance test

Unit test nên có invariant rõ, điều phối bằng primitive đồng bộ và thời gian chạy ngắn. Performance test nên có warmup, tải được kiểm soát, đo percentile và thống kê nhiều lần.

Đừng assert “task phải hoàn thành dưới 5 ms” trong unit test chạy trên CI chia sẻ. Đó là nguồn flaky test; ngưỡng performance cần môi trường đo riêng và chính sách sai số phù hợp.

## 9. Công cụ stress và kiểm tra thuật toán concurrent

### 9.1. Vì sao lặp test 1.000 lần vẫn chưa đủ?

Một thuật toán lock-free có thể sai trên một interleaving hiếm hoặc trên kiến trúc CPU khác. Chạy một JUnit test nhiều lần tăng cơ hội gặp lỗi, nhưng không tạo bằng chứng hình thức rằng mọi interleaving đều đúng.

Cần kết hợp:

- Unit tests cho business invariants.
- Stress tests với mức cạnh tranh đa dạng.
- Test fault injection và cancellation.
- Kiểm tra happens-before bằng thiết kế thuật toán.
- Công cụ concurrency testing chuyên biệt khi phù hợp.

### 9.2. jcstress

**OpenJDK jcstress** là công cụ dùng cho những phép thử concurrency ở mức Java Memory Model. Một test thường có nhiều actor thực hiện những thao tác trên state chung, sau đó thu thập outcomes có thể quan sát.

Nó hữu ích cho:

- Kiểm chứng visibility/ordering.
- So sánh implementation trước/sau thay đổi.
- Phát hiện outcome bất ngờ ở data race.
- Thử trên nhiều JDK/kiến trúc nếu có môi trường.

Không dùng kết quả “không phát hiện outcome sai” để kết luận một thuật toán bất kỳ đã được chứng minh đúng hoàn toàn. Cần định nghĩa các outcomes hợp lệ theo memory model và đọc kết quả thống kê.

### 9.3. Linearizability và state-machine testing

Với concurrent map, queue, cache hoặc client library có API nhiều thao tác, đôi khi cần kiểm chứng **linearizability**: kết quả của một lịch sử lời gọi concurrent phải tương đương một thứ tự tuần tự nào đó tuân theo ràng buộc thời gian thực của các thao tác không chồng lấn.

Có thể dùng một checker/harness tương ứng, tạo lịch sử:

```text
T1: put(k, A) --------> complete
T2:      get(k) -----> returns ?
T3:            put(k, B) -----> complete
```

Sau đó kiểm tra liệu outcome có thể giải thích bằng một thứ tự tuyến tính hợp lệ hay không.

Không phải mọi API bất đồng bộ đều cam kết linearizability; phải xác định contract trước khi áp tiêu chí.

### 9.4. Race detector không thay thiết kế đồng bộ

Các công cụ/agent có thể quan sát pattern truy cập, nhưng Java concurrency chịu nhiều tầng tối ưu compiler/JIT và semantics memory model. Không tồn tại một test đơn giản bảo đảm loại bỏ mọi race condition của hệ thống phức tạp.

Trong migration, điều quan trọng là **ghi mức độ tự tin và rủi ro còn lại**, thay vì tuyên bố “đã stress test nên chắc chắn không có race”.

## 10. Fault injection: kiểm chứng khi sự cố xảy ra

### 10.1. Những lỗi nên chủ động mô phỏng

Một task concurrent có thể bị ảnh hưởng bởi:

- Downstream API timeout hoặc trả lỗi 5xx.
- Database pool hết connection.
- Message queue mất kết nối.
- Thread bị interrupt.
- Một future thất bại trước future khác.
- Một executor bị shutdown khi còn task đang chờ.
- Queue đạt capacity và từ chối task.
- Process restart giữa task và commit/ack.
- GC pause hoặc CPU quota bị siết dưới tải.

Test failure path cần kiểm tra **kết quả nghiệp vụ** lẫn **trạng thái tài nguyên**: task có bị retry vô hạn không, connection có bị trả pool không, callback có được gọi đúng một lần không.

### 10.2. Cancellation trong pipeline nhiều stage

Ví dụ:

```java
CompletableFuture<Result> pipeline =
        CompletableFuture.supplyAsync(
            () -> fetchFromRemote(), ioExecutor
        ).thenApply(result -> transform(result));
```

Nếu request bên ngoài hủy, việc cancel `pipeline` không mặc nhiên đảm bảo tác vụ `fetchFromRemote()` đang chạy bị interrupt hoặc downstream request bị hủy. Cần kiểm chứng cơ chế cancellation mà HTTP client và abstraction sử dụng.

Khi thay thư viện concurrency, kiểm tra behavior của:

- `cancel` trên future nguồn và future cuối.
- Timeout trước và sau khi downstream bắt đầu.
- Exception trên stage đầu tiên.
- Nhiều stage hoàn thành gần như đồng thời.
- Resource cleanup nếu subscriber/consumer bỏ theo dõi kết quả.

### 10.3. Xử lý quá tải và retry cùng lúc

Nếu thread pool từ chối task, retry ngay lập tức với cùng tốc độ có thể khiến service bận quay vòng và làm quá tải trầm trọng hơn.

Đặt rõ policy: retry khi nào, tối đa bao nhiêu, backoff bao lâu, có jitter không và có bỏ request sau deadline không. Test nên assert *bounded retries* và *bounded queue*, không assert số lượng thread tăng lên là hệ thống đã mở rộng thành công.

## 11. Context propagation: dữ liệu theo request đi đâu khi đổi thread?

### 11.1. `ThreadLocal` không phải request context tự động

Nhiều code legacy lưu:

- Request ID/MDC.
- User identity/security context.
- Transaction hoặc session.
- Locale/timezone.
- Tracing span.
- Tenant ID.

vào `ThreadLocal` và giả định callback tiếp theo vẫn chạy trên cùng thread.

Sau khi dùng `CompletableFuture`, reactive scheduler hoặc executor khác, callback có thể chạy trên thread không giữ context đó. Kết quả có thể là log thiếu correlation ID hoặc tệ hơn, thao tác với nhầm tenant/security context nếu cách cleanup/reuse không đúng.

### 11.2. Cần cơ chế truyền context tường minh

Các hướng tiếp cận có thể gồm:

- Truyền context như tham số bất biến trong lời gọi task.
- Dùng wrapper cho `Runnable`/`Callable` với capture/restore context có kiểm soát.
- Dùng cơ chế propagation do framework tracing/security/reactive hỗ trợ.
- Giới hạn lifetime context và luôn cleanup sau task trong executor reuse.

Ví dụ truyền tường minh:

```java
final class RequestContext {
    final String requestId;
    final String tenantId;

    RequestContext(String requestId, String tenantId) {
        this.requestId = requestId;
        this.tenantId = tenantId;
    }
}

void handleAsync(RequestContext context, Executor executor) {
    CompletableFuture.runAsync(
        () -> process(context.requestId, context.tenantId),
        executor
    );
}
```

Trong code thực tế cần quản lý bảo mật và tránh đưa thông tin nhạy cảm vào log không cần thiết.

### 11.3. Virtual threads và context

Virtual threads cũng có `ThreadLocal` riêng theo semantics Java, nhưng việc tạo rất nhiều thread mới có thể khiến mô hình lưu state lớn trong `ThreadLocal` trở nên đắt đỏ hoặc không còn giống pool reuse cũ.

Đừng giả định virtual thread “thừa hưởng” mọi context framework cũ theo đúng cách ứng dụng kỳ vọng. Kiểm tra transaction, security, tracing và MDC bằng integration test trên JDK/framework version thực tế.

## 12. Quan sát runtime: thread dump, JFR và metrics

### 12.1. Những metric cần có

Đối với executor/thread pool truyền thống:

- Active threads, current/core/max pool size.
- Queue length và queue wait time.
- Task submitted/completed/rejected.
- Task execution latency và end-to-end latency.
- Cancellation/timeouts.
- CPU, memory/heap, GC pause.
- Thời gian chờ connection/database/network.

Đối với reactive/virtual-thread architecture, cần thêm metrics phù hợp với event loop, scheduler và downstream concurrency. Không dùng số lượng thread như KPI duy nhất.

### 12.2. Thread dump

Khi có deadlock hoặc task bị kẹt, thu thập thread dump của JVM đang chạy. Ví dụ:

```bash
jcmd <pid> Thread.print -l
```

Thông tin có thể giúp thấy thread đang `BLOCKED`, `WAITING`, `TIMED_WAITING`, lock owner và stack trace. Tuy nhiên, không phải mọi loại starvation đều hiện như deadlock monitor; cần đối chiếu queue metrics và luồng nhiệm vụ.

Các công cụ và tùy chọn thread dump có thể khác theo JDK; với virtual threads số lượng rất lớn, cần lựa chọn cơ chế dump/quan sát phù hợp với JDK đích thay vì in một lượng stack trace khổng lồ không có mục tiêu.

### 12.3. Java Flight Recorder (JFR)

JFR hữu ích để khảo sát CPU samples, lock contention, thread park, allocation, GC và nhiều loại sự kiện runtime. Có thể khởi động một recording có giới hạn:

```bash
jcmd <pid> JFR.start name=concurrency-check duration=60s filename=concurrency.jfr
```

Cần chọn recording settings và kích thước/duration theo môi trường. Không bật toàn bộ sự kiện ở mức chi tiết cao trên production nếu chưa đánh giá overhead.

Phân tích bằng Java Mission Control hoặc công cụ tương thích với recording của JDK. Chú ý liên hệ giữa spikes p99 và thời điểm GC/lock contention/đợi downstream.

### 12.4. JFR không chứng minh safety

Một profile JFR có thể cho thấy thread bị park lâu hoặc nhiều contention, nhưng không chứng minh phép cập nhật dữ liệu là atomic. Ngược lại, metrics có thể bình thường dù race hiếm gây sai dữ liệu.

Phải kết hợp quan sát runtime với test invariant, stress test và điều tra mã nguồn.

### 12.5. Logging có thể thay đổi lịch chạy

Thêm log ở mọi instruction để “bắt race” có thể làm scheduling thay đổi khiến lỗi biến mất. Đây là dạng **observer effect**.

Ưu tiên:

- Log có cấu trúc tại sự kiện có ý nghĩa (submit, start, complete, cancel, fail).
- Correlation ID theo request/task.
- Metrics aggregation thay vì debug log quá dày.
- JFR/profiling có sampling được kiểm soát.
- Trace/counter có chi phí phù hợp.

Đừng kết luận race được sửa chỉ vì bật debug logging làm test pass.

## 13. Đo hiệu năng concurrency cho có ý nghĩa

### 13.1. Throughput không đủ

Khi đổi thread pool từ 8 lên 64 thread, throughput có thể tăng, giữ nguyên hoặc giảm tùy workload. Nếu downstream database chỉ có 10 connections, việc thêm nhiều thread có thể chỉ làm queue chuyển chỗ.

Theo dõi ít nhất:

- Completed business operations/second.
- Error/rejection/timeout rate.
- p50, p95 và p99 end-to-end latency.
- Queue wait time và execution time.
- CPU, memory, GC, context switches khi có số liệu.
- Connection pool utilization và downstream latency.

Kết quả cần đặt trong cùng workload và tài nguyên. Không so sánh một lần chạy trên laptop với một lần chạy trên container có CPU quota khác rồi quy toàn bộ chênh lệch cho JDK.

### 13.2. JIT warmup và microbenchmark

Một microbenchmark Java cần tính đến JIT compilation, dead-code elimination, constant folding, allocation optimization và tác động warmup. **JMH** là công cụ chuyên dụng thường được dùng để đo microbenchmark Java tốt hơn một vòng lặp `System.nanoTime()` thủ công.

Đừng dùng JMH thay cho integration load test: nó giúp đo phép toán nhỏ trong điều kiện được kiểm soát, nhưng không mô phỏng đầy đủ database, network, queue hay scheduler ở production.

### 13.3. Phân loại workload

| Loại | Đặc điểm | Điểm cần đánh giá |
| --- | --- | --- |
| CPU-bound | Chủ yếu tính toán. | Parallelism gần năng lực CPU, contention, cache locality, GC. |
| Blocking I/O | Chờ network/DB/filesystem. | Thread model, downstream pool, timeout, cancellation. |
| Mixed | Vừa tính toán vừa I/O. | Tách pool hoặc phân bổ resource tránh starvation. |
| Reactive | Event loop/scheduler, non-blocking flow. | Blocking trong event loop, backpressure, context. |
| Batch/parallel stream | Chia nhỏ nhiều task. | Work stealing, common pool interference, ordering. |

Việc đổi framework concurrency có thể làm một workload chuyển giữa các nhóm, nên cần đo cả tình huống tải đại diện lẫn burst/outlier.

### 13.4. So sánh có kiểm soát

Cố định:

- Input dataset và tỉ lệ các endpoint.
- Số client và arrival rate.
- CPU/memory limits, DB pool, downstream versions.
- JDK flags và GC policy nếu mục tiêu là đo riêng library.
- Duration/warmup, số lượt chạy và cách báo cáo percentile.

Ghi rõ các yếu tố không thể cố định (JDK đổi GC defaults, OS image khác...). Khi đó, báo cáo là so sánh **tổ hợp hệ thống**, không phải một phép đo nhân quả thuần túy của JDK.

## 14. Container, CPU quota và auto-sizing

### 14.1. `availableProcessors()` có thể thay đổi

Một số framework/executor tính default concurrency dựa vào:

```java
int processors = Runtime.getRuntime().availableProcessors();
```

Trong container, số CPU mà JVM nhận diện có thể chịu tác động của quota/limits và chính sách container awareness. Khi đổi JDK hoặc cách triển khai, giá trị quan sát được có thể khác.

Nếu common pool parallelism, worker pool hoặc framework scheduler dùng `availableProcessors()`, một giá trị mới có thể thay đổi throughput, queueing và timing của race.

### 14.2. Không giả định CPU = số logical CPU của host

Đối với deployment container, cần ghi nhận:

- CPU requests/limits/quota.
- Phiên bản JDK và container awareness.
- `availableProcessors()` tại runtime.
- Cấu hình thread pool thực tế sau startup.
- Throttling metrics.
- Memory limit và số lượng thread/stack.

Nếu ứng dụng trở nên chậm sau migration, cần xác định có phải pool bị thu nhỏ do CPU limit hay không trước khi điều chỉnh thuật toán.

### 14.3. Thread pool quá lớn cũng có chi phí

Tăng pool size có thể gây:

- Context switching.
- Tranh lock.
- Memory footprint của stack/platform threads.
- Áp lực lên database/HTTP connections.
- Thời gian chờ dài hơn do downstream quá tải.

Không dùng cấu hình “max threads = vài nghìn” như giải pháp mặc định. Với virtual threads, số task có thể nhiều nhưng vẫn cần giới hạn các tài nguyên có capacity hữu hạn.

## 15. Kịch bản kiểm chứng end-to-end

### 15.1. Bối cảnh

Giả sử service xử lý đơn hàng có pipeline:

```text
HTTP request
    |
    v
Validate
    |
    v
Submit task vào executor
    |
    +----> Check inventory (DB)
    |
    +----> Reserve payment (remote API)
    |
    v
Persist order state
    |
    v
Publish event
```

Dự án đang nâng JDK và đồng thời đổi thư viện async client. Trước migration, một lỗi timeout hiếm gặp làm client retry và có thể tạo đặt hàng hai lần.

### 15.2. Các invariant bắt buộc

- Một idempotency key chỉ tạo một order logical.
- Inventory không bị trừ quá số lượng sẵn có.
- Payment không bị charge hai lần cho cùng giao dịch.
- Khi task bị hủy, state cuối thuộc một tập đã xác định; không để record “processing” tồn tại vô hạn.
- Event phát ra chỉ khi trạng thái DB đã commit theo contract.
- Khi downstream chậm, queue không tăng vô hạn.
- Security/request context không rơi mất giữa async stages.

### 15.3. Test bình thường

Chạy nhiều request đồng thời với các ID khác nhau; xác minh đủ kết quả, dữ liệu chính xác và không có task bị mất.

Chạy nhiều request đồng thời với **cùng idempotency key**; xác minh chỉ có một side effect phù hợp contract.

### 15.4. Test cạnh tranh

Dùng latch hoặc barrier để nhiều worker cùng đến bước kiểm tra inventory. Không giả định race sẽ tự xảy ra trong một lần test. Kiểm tra invariant sau khi tất cả futures kết thúc hoặc hết deadline.

### 15.5. Fault injection

Mô phỏng remote API timeout, DB rollback, executor rejection, process restart và cancellation ngay trước khi commit. Kiểm tra retry, compensation và trạng thái cuối.

### 15.6. Load test trước/sau

So sánh cùng workload trên baseline và cấu hình mới. Báo cáo p99, throughput, queue, CPU, GC, error/timeout/rejection, số connection đang dùng và số task còn tồn đọng sau khi ngừng nhận request.

### 15.7. Phương án rollback

Nếu deployment mới có dấu hiệu tăng duplicate side effect hoặc backlog, rollback code có thể chưa đủ vì state DB/queue đã thay đổi. Cần kiểm tra tương thích dữ liệu, xử lý lại message và cách xác định các task có thể đã hoàn thành dù client thấy timeout.

## 16. Quy trình migration theo từng bước

### Bước 1: Đóng băng phạm vi thay đổi

Chốt JDK cũ/đích, version concurrency library, framework version và các executor/scheduler sẽ thay. Tránh đổi nhiều biến không liên quan trong một lượt nếu muốn phân tích nguyên nhân.

### Bước 2: Thu thập baseline

Ghi cấu hình JVM, dependency, thread pools, CPU/container quotas, số task, latency, queue, lỗi, timeout, shutdown behavior. Lưu test reports và workload.

### Bước 3: Xác định contract concurrency

Viết rõ safety invariants, liveness requirements, ordering guarantees, deadline, retry, cancellation, context propagation và throughput mục tiêu.

Nếu API/library guide công bố thay đổi behavior, biến mỗi thay đổi thành một test hoặc tiêu chí quan sát cụ thể.

### Bước 4: Xây dựng test harness

Dùng latch/barrier cho cạnh tranh, bounded timeouts cho completion, Future.get để nhận exception, test cleanup để không rò thread. Bổ sung stress test cho phần thuật toán đồng bộ có rủi ro cao.

### Bước 5: Nâng JDK/tooling ở cấu hình được hỗ trợ

Kiểm tra build tool, JVM flags, Byte Buddy/ASM/agent, JFR support và thư viện concurrency đang dùng. Nếu các bản kết hợp không được hỗ trợ, đi qua chặng migration chính thức.

### Bước 6: Nâng thư viện concurrency theo guide

Đối chiếu thay đổi API/default executor, queue/scheduler, context, timeout và cancellation. Không chỉ sửa compilation errors; xác nhận effective runtime behavior.

### Bước 7: Kiểm chứng correctness/liveness trước performance

Chạy unit/integration concurrency tests, fault injection, shutdown/restart, queue overload và stress harness. Không chấp nhận performance cải thiện nếu safety invariant bị vi phạm.

### Bước 8: Đo performance có kiểm soát

Sử dụng workload cố định, warmup hợp lý và nhiều lượt đo. Báo cáo throughput/latency/errors/resources, không chỉ thời gian của một request thành công.

### Bước 9: Canary và quan sát production-like

Triển khai với lượng traffic có giới hạn khi có cơ chế an toàn. Theo dõi backlog, task completion, duplicates, p99, CPU/GC, blocked threads và downstream saturation. Có ngưỡng rollback được xác định trước.

### Bước 10: Chốt tài liệu và loại bỏ workaround

Cập nhật executor configuration, timeout/retry policy, JVM/toolchain, cách thu thread dump/JFR, runbook xử lý backlog và các cảnh báo remaining risk.

## 17. Những sai lầm thường gặp

**“Test chạy 100 lần đều pass nên không có data race.”** Sai. Lịch chạy được quan sát chưa bao phủ mọi interleaving. Phải dùng synchronization đúng theo Java Memory Model và test phù hợp.

**“`volatile` sửa được `counter++`.”** Sai. Visibility và atomicity là hai vấn đề khác nhau.

**“Thêm thread luôn tăng throughput.”** Sai. Có thể làm downstream quá tải, tranh lock và tăng p99.

**“Thread.sleep đủ để chờ worker.”** Sai. Sleep không bảo đảm worker đã đến một mốc cụ thể hoặc tạo quan hệ đồng bộ cần thiết.

**“`Future.cancel(true)` luôn dừng task.”** Sai. Task và I/O phải đáp ứng cancellation/interrupt theo contract.

**“CompletableFuture callback luôn ở cùng thread request.”** Sai. Phải xem loại stage, executor và completion path.

**“Build xanh tức mọi async task đều thành công.”** Sai. Exception có thể bị giữ trong Future hoặc xử lý ở callback không được test quan sát.

**“Không có deadlock trong thread dump nghĩa hệ thống không bị kẹt.”** Sai. Starvation, bounded resource contention và downstream waits có thể tạo liveness failure khác monitor deadlock.

**“Virtual threads giải quyết mọi giới hạn concurrency.”** Sai. Database connection, downstream rate limit và CPU vẫn có capacity hữu hạn.

**“JDK mới làm hỏng code đang đúng.”** Không nhất thiết. Một lỗi có thể đã tồn tại nhưng chỉ lộ ra khi scheduling hoặc môi trường đổi. Cần phân biệt data race cũ với thay đổi contract thực sự của thư viện.

## 18. Checklist kiểm chứng trước khi phát hành

- [ ] Đã ghi rõ JDK vendor/version, concurrency library và framework version trước/sau.
- [ ] Đã kiểm tra CPU quota/container awareness và `availableProcessors()` thực tế.
- [ ] Đã kiểm kê explicit/implicit executors, common pool và scheduler.
- [ ] Đã ghi pool size, queue capacity, rejection policy, timeouts và shutdown policy.
- [ ] Đã định nghĩa safety invariants và các side effects cần idempotency.
- [ ] Đã kiểm tra atomicity, visibility, safe publication và thứ tự đồng bộ quan trọng.
- [ ] Đã thiết kế test cạnh tranh bằng latch/barrier thay vì dựa vào sleep.
- [ ] Đã dùng bounded timeouts, đọc exception từ Future và cleanup executor.
- [ ] Đã kiểm tra cancellation/interrupt, deadline, retry và failure propagation.
- [ ] Đã kiểm tra deadlock, starvation, livelock, queue backlog và overload behavior.
- [ ] Đã kiểm tra context propagation: MDC, tracing, security, tenant và transaction.
- [ ] Đã xác minh reactive/virtual-thread semantics nếu dự án dùng.
- [ ] Đã thử fault injection cho timeout, shutdown, downstream failure và restart.
- [ ] Đã thu metrics throughput, p95/p99, errors, queue, CPU, GC và downstream usage.
- [ ] Đã so sánh performance trên workload và tài nguyên có kiểm soát.
- [ ] Đã chuẩn bị thread dump/JFR/runbook khi có sự cố liveness.
- [ ] Đã có canary, ngưỡng rollback và phương án xử lý side effects còn dang dở.
- [ ] Đã lưu bằng chứng test và xác nhận những bất biến nghiệp vụ còn đúng sau migration.

## 19. Tổng kết

Khi đổi JVM hoặc thư viện concurrency, nhiệm vụ kiểm chứng phải vượt xa việc mã nguồn biên dịch thành công và một vài test tuần tự chạy qua. Cần kiểm tra **safety**, **liveness**, **performance** và **operability** dưới những lịch chạy và điều kiện tải khác nhau. Java Memory Model là nền tảng để đánh giá visibility/atomicity; các executor, future, scheduler, reactive runtime và virtual threads bổ sung những contract riêng về scheduling, cancellation và quản lý tài nguyên.

Trong Java Advance Compatibility Migration, hãy bắt đầu bằng baseline và business invariants, tạo test có phối hợp rõ ràng, thử các failure path, quan sát JVM bằng metrics/thread dumps/JFR, rồi so sánh kết quả trên JDK và dependency đích. Chỉ khi hệ thống vừa **đúng về dữ liệu**, vừa **tiến triển và phục hồi được**, vừa **đạt các mục tiêu hiệu năng đã định** thì mới có đủ bằng chứng để coi migration concurrency thành công.
