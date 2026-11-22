# Deadlock, cạn luồng và giới hạn của việc tăng số luồng

Trong ứng dụng Spring Framework, nhiều yêu cầu HTTP, tác vụ `@Async`, công việc `@Scheduled` và thao tác I/O có thể cùng cần luồng để tiến triển. Khi hệ thống chậm hoặc đứng, tăng số luồng thường là phản xạ đầu tiên, nhưng cách này có thể không giải quyết được vấn đề, thậm chí khiến độ trễ và mức sử dụng tài nguyên tăng thêm.

Bài học này tập trung vào **ba vấn đề khác nhau**: deadlock (các luồng chờ nhau theo vòng), cạn luồng/thread-pool starvation (không còn luồng rảnh để thực hiện công việc cần thiết) và giới hạn của việc mở rộng số luồng. Ví dụ Java dùng Java 17 trở lên; phần cấu hình Spring là ví dụ tích hợp, cần có thư viện Spring trong dự án.

## 1. Luồng, tác vụ và hàng đợi: mô hình cần nắm

**Luồng (thread)** là đơn vị thực thi; **tác vụ (task)** là công việc được giao cho một luồng; **executor/thread pool** nhận tác vụ và quản lý các worker thay vì mỗi tác vụ đều phải tạo một luồng mới.

Trong hệ thống điển hình:

~~~text
Caller (HTTP / scheduler / event)
        |
        v
   TaskExecutor
        |
        +--> worker rảnh ---------> chạy tác vụ ---------> hoàn tất
        |
        +--> hàng đợi (nếu bận) --> chờ đến lượt
        |
        +--> từ chối (khi đã đạt giới hạn theo cấu hình)
~~~

Ba đại lượng phải quan sát đồng thời:

- **Active workers**: số luồng đang bận thực thi tác vụ. Một luồng đang chờ I/O hoặc chờ `Future.get()` vẫn có thể được tính là đang bận.
- **Queue depth và thời gian chờ trong queue**: công việc đã nhận nhưng chưa có worker thực hiện. Hàng đợi tăng liên tục có thể che giấu sự cố cho đến khi độ trễ rất lớn.
- **Throughput, latency và rejection**: tác vụ hoàn tất mỗi giây, thời gian xử lý (đặc biệt p95/p99) và số tác vụ bị từ chối.

**Không đồng nhất số luồng lớn với khả năng xử lý lớn.** Một luồng đang giữ khóa hoặc đợi database chưa tạo ra kết quả, dù nó chiếm chỗ trong pool.

## 2. Phân biệt đúng triệu chứng

| Hiện tượng | Cơ chế cốt lõi | Dấu hiệu thường gặp | Tăng luồng có chữa tận gốc? |
| --- | --- | --- | --- |
| **Deadlock trên khóa Java** | Các luồng giữ khóa và chờ khóa của nhau theo vòng kín | Thread dump chỉ ra chu trình sở hữu/chờ monitor hoặc ownable synchronizer; công việc không tiến triển | **Không**; phải phá vòng phụ thuộc khóa |
| **Thread-pool starvation** | Tất cả worker bận/chờ, trong khi công việc để giải phóng chúng lại nằm trong queue của chính pool đó, hoặc tác vụ quan trọng liên tục không được cấp thời gian | Active chạm ngưỡng; queue đọng; stack nhiều `Future.get()`/`join()` | Tăng pool có thể làm hết triệu chứng trong một tải cụ thể, nhưng phụ thuộc nguy hiểm vẫn tồn tại |
| **Pool saturation / quá tải** | Tốc độ đến vượt tốc độ hoàn thành, hoặc I/O chậm chiếm hết worker | Queue tăng, rejection, latency tăng; có thể không có chu trình deadlock | Đôi khi có ích với I/O-bound, nhưng chỉ tới giới hạn tài nguyên phía sau |
| **Resource starvation** | Luồng chờ connection pool, khóa DB, socket hoặc tài nguyên khác bị giới hạn | Nhiều stack chờ datasource/HTTP client; pool tài nguyên đầy | Tăng worker thường làm nhiều luồng chờ hơn |
| **CPU contention / quá nhiều runnable threads** | Nhiều luồng tranh CPU, cache, lock, lịch chạy | CPU cao, context switch nhiều, throughput không tăng | Thường **không** |
| **Livelock / retry liên tục** | Tác vụ vẫn chạy nhưng liên tục phản ứng/retry mà không đạt tiến triển | CPU hoặc log hoạt động mạnh, kết quả không hoàn tất | Không; phải sửa điều kiện tiến triển và chiến lược retry |

Một luồng ở trạng thái `BLOCKED` hoặc `WAITING` **chưa đủ** để kết luận deadlock. Thread đang đợi việc, ngủ theo lịch, hoặc chờ kết quả hợp lệ cũng có thể ở các trạng thái đó. Cần xem nó chờ **ai/cái gì**, và có vòng phụ thuộc hay không.

## 3. Deadlock là gì và tại sao xảy ra?

Giả sử luồng T1 giữ khóa A rồi cố lấy B, trong khi T2 giữ khóa B rồi cố lấy A:

~~~text
T1: giữ A -----> đợi B (do T2 giữ)
                 ^              |
                 |              v
T2: đợi A <----- giữ B
~~~

Không bên nào có thể tới đoạn nhả khóa đã giữ. Deadlock cổ điển xuất hiện khi đồng thời có bốn điều kiện Coffman:

1. **Mutual exclusion:** tài nguyên/khóa chỉ có một chủ sở hữu tại một thời điểm.
2. **Hold and wait:** luồng giữ ít nhất một tài nguyên trong khi đợi thêm tài nguyên khác.
3. **No preemption:** không thể tự ý thu hồi khóa khỏi luồng đang giữ.
4. **Circular wait:** tồn tại chu trình luồng/tài nguyên chờ nhau.

Phá được **ít nhất một điều kiện** sẽ loại được dạng deadlock tương ứng. Trong Java, cách thực tế nhất thường là **quy định thứ tự lấy khóa thống nhất** và không giữ khóa khi thực hiện thao tác có thể chặn lâu.

### 3.1. Ví dụ Java 17: tạo và phát hiện deadlock có kiểm soát

Tạo tệp `DeadlockDemo.java`:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;

public class DeadlockDemo {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();
    private static final CountDownLatch READY = new CountDownLatch(2);

    private static void takeLocks(Object first, Object second) {
        synchronized (first) {
            READY.countDown();
            try {
                READY.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            synchronized (second) {
                System.out.println("Both locks acquired");
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread t1 = new Thread(() -> takeLocks(LOCK_A, LOCK_B), "worker-A");
        Thread t2 = new Thread(() -> takeLocks(LOCK_B, LOCK_A), "worker-B");
        t1.setDaemon(true);
        t2.setDaemon(true);
        t1.start();
        t2.start();

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        for (int i = 0; i < 100; i++) {
            long[] deadlocked = bean.findMonitorDeadlockedThreads();
            if (deadlocked != null) {
                System.out.println("Deadlock detected: " + deadlocked.length + " threads");
                return;
            }
            Thread.sleep(50);
        }
        System.out.println("No deadlock detected within the check window");
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 DeadlockDemo.java
java DeadlockDemo
~~~

Kết quả trên JVM hỗ trợ phát hiện monitor deadlock (ví dụ OpenJDK/HotSpot):

~~~text
Deadlock detected: 2 threads
~~~

`CountDownLatch` buộc cả hai luồng **đã giữ khóa đầu tiên** trước khi cố lấy khóa thứ hai; vì thứ tự đối nghịch, chúng tạo vòng chờ. Ví dụ dùng daemon threads **chỉ để tiến trình minh họa có thể kết thúc** sau khi báo lỗi; daemon không phải biện pháp xử lý deadlock. Dòng `Both locks acquired` không xuất hiện trong kịch bản deadlock. `findMonitorDeadlockedThreads()` phát hiện vòng chờ của monitor do `synchronized` quản lý; `findDeadlockedThreads()` mở rộng tới ownable synchronizers như `ReentrantLock` nếu JVM hỗ trợ.

### 3.2. Khắc phục: luôn lấy khóa theo cùng thứ tự

Nếu hai nhánh đều cần A và B, cả hai phải lấy **A rồi B**, bất kể nhánh nào chạy trước:

~~~java
private static void updateBothLocks() {
    synchronized (LOCK_A) {
        synchronized (LOCK_B) {
            // Vùng cập nhật trạng thái chung phải ngắn và không chứa I/O chặn.
        }
    }
}
~~~

Đây là **đoạn phương pháp minh họa** dùng lại hai biến `LOCK_A` và `LOCK_B` từ lớp trước, không phải chương trình độc lập. Hai luồng có thể phải chờ nhau, nhưng không tạo chu trình A→B và B→A. Trong thiết kế thực tế, còn nên giảm số khóa, rút ngắn critical section, tránh gọi callback/HTTP/DB hoặc chờ `Future` khi đang giữ khóa. Với `ReentrantLock`, `tryLock(timeout, unit)` giúp tránh chờ vô hạn **nếu mọi đường thoát đều nhả các khóa đã lấy trong `finally`**.

**Phân biệt deadlock Java với deadlock database:** hai transaction có thể khóa các hàng SQL theo thứ tự ngược nhau; database thường phát hiện và hủy một transaction. Trường hợp đó cần xem log/SQL/transaction order và chính sách retry phù hợp, không được kết luận chỉ từ `ThreadMXBean`.

## 4. Cạn luồng: khi worker chờ chính công việc cần worker

Một lỗi đặc biệt dễ mắc là **task A đang chạy trong pool nhỏ, lại submit task B vào cùng pool rồi chờ đồng bộ kết quả B**. Nếu mọi worker đều đang làm như A, không worker nào còn rảnh để chạy B. Đây thường được gọi là *thread-starvation deadlock*; nó có thể không xuất hiện trong công cụ phát hiện chu trình monitor deadlock.

### 4.1. Ví dụ Java 17: pool một luồng tự chặn chính mình

Tạo tệp `PoolStarvationDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class PoolStarvationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(1);
        try {
            Future<String> outer = pool.submit(() -> {
                Future<String> inner = pool.submit(() -> "OK");
                return inner.get();
            });
            try {
                System.out.println(outer.get(500, TimeUnit.MILLISECONDS));
            } catch (TimeoutException expected) {
                System.out.println("TIMEOUT: worker waits for a task queued in its own pool");
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PoolStarvationDemo.java
java PoolStarvationDemo
~~~

Kết quả:

~~~text
TIMEOUT: worker waits for a task queued in its own pool
~~~

Diễn biến chính xác: worker duy nhất chạy `outer` → `outer` đưa `inner` vào queue → `outer` gọi `inner.get()`, chiếm worker khi chờ → `inner` không có worker để chạy → luồng main hết thời gian chờ sau 500 ms. `shutdownNow()` ngắt worker nhằm kết thúc chương trình minh họa; việc ngắt này không làm cấu trúc phụ thuộc ban đầu trở nên đúng.

**Sửa tại nguyên nhân:** nếu `inner` chỉ là bước tiếp theo của cùng công việc, gọi logic đó trực tiếp trong `outer`; hoặc tổ chức chuỗi bất đồng bộ không chặn worker trên kết quả của task cùng pool. Tách pool chỉ hợp lý khi đã xác định hai loại công việc có nhu cầu tài nguyên và giới hạn độc lập. Không dùng pool lớn hơn để che vòng phụ thuộc.

### 4.2. Các nguồn cạn luồng khác trong ứng dụng Spring

- Tác vụ `@Async` gọi `get()`/`join()` chờ những tác vụ khác cũng chạy trên executor đã bão hòa.
- Nhiều tác vụ `@Scheduled` chạy lâu hoặc chặn I/O trên một scheduler ít worker khiến lịch chạy kế tiếp bị trì hoãn.
- Luồng request của Spring MVC bị giữ vì gọi HTTP, JDBC hoặc dịch vụ khác không có timeout hữu hạn. Nếu datasource chỉ có 10 connection khả dụng, thêm 100 request threads không tạo ra 100 connection.
- Callback sử dụng chung pool với tác vụ đang chờ callback, gây phụ thuộc kiểu “mọi worker đều bận chờ”.
- Queue không giới hạn nhận tiếp công việc dù năng lực xử lý phía sau thấp: hệ thống chưa từ chối ngay nhưng tăng dần thời gian chờ và bộ nhớ.

Trong Spring WebFlux, **chặn event-loop bằng thao tác blocking** là một lỗi khác: một số ít event-loop threads có thể bị giữ lâu và làm chậm nhiều request. Phải dùng API không chặn hoặc chuyển blocking work sang scheduler phù hợp và có giới hạn; tăng `@Async` pool không tự giải quyết vấn đề trên event loop.

## 5. Vì sao tăng số luồng có giới hạn?

### 5.1. Công việc CPU-bound và I/O-bound

- **CPU-bound:** tính toán chiếm CPU liên tục. Nếu hệ thống có khoảng P lõi CPU thực sự được cấp, cho chạy nhiều hơn P tác vụ CPU-bound cùng lúc thường tăng tranh lịch chạy/context switching mà không tăng tương ứng throughput. Thử nghiệm bắt đầu quanh mức song song CPU hữu dụng rồi đo, thay vì lấy một con số cố định cho mọi máy.
- **I/O-bound:** luồng dành nhiều thời gian chờ mạng/đĩa/database. Có thể cần concurrency lớn hơn số lõi CPU để che độ trễ chờ, nhưng mức tối ưu phụ thuộc giới hạn socket/connection pool, tốc độ backend, timeout và bộ nhớ.
- **Khóa dùng chung:** nếu mọi tác vụ đều phải vào một critical section, thêm worker có thể chỉ làm dài hàng chờ khóa.
- **Phụ thuộc tuần tự:** một giai đoạn bắt buộc chạy nối tiếp tạo giới hạn tốc độ; thêm worker cho các giai đoạn khác không loại bỏ nút thắt đó.

Ví dụ tính nhẩm: endpoint cần 200 ms sử dụng một database connection, còn database pool chỉ có 10 connection. Trong mô hình lý tưởng (không có chi phí khác), tối đa khoảng `10 / 0,2 = 50` lượt truy vấn/giây ở bước này. Tăng executor từ 20 lên 200 worker không làm pool DB vượt giới hạn 10; các worker mới có thể chỉ đứng chờ connection, khiến p95/p99 xấu đi. Đây là phép minh họa giới hạn tài nguyên, **không phải dự báo throughput thực tế**.

### 5.2. Ước lượng concurrency bằng Little's Law

Ở trạng thái ổn định, `L = λ × W`, với L là số công việc trung bình đang ở trong hệ, λ là tốc độ hoàn tất/đến trung bình và W là thời gian trung bình mỗi công việc lưu lại. Nếu throughput ổn định 60 tác vụ/giây và mỗi tác vụ cần trung bình 0,5 giây trong đoạn đang đo, concurrency trung bình xấp xỉ 30.

Phải xác định rõ W đang đo **thời gian chiếm worker** hay **tổng thời gian gồm queue**. Little's Law giúp đối chiếu số liệu, không tự đưa ra kích cỡ pool tối ưu khi tải biến động, đuôi độ trễ dài, I/O có giới hạn hoặc hệ thống chưa ổn định.

### 5.3. Chi phí của thread quá nhiều

Mỗi platform thread cần stack và metadata native, có chi phí lập lịch và chuyển ngữ cảnh; nhiều task đồng thời còn tăng contention trên lock, connection, cache và vùng heap chứa request/queue. Stack có thể là bộ nhớ **được dành chỗ** chứ không phải luôn đã cam kết toàn bộ, nên không nên áp dụng công thức “mỗi thread luôn tốn chính xác 1 MB RAM”.

Nếu tăng thread count từ 32 lên 256 nhưng throughput gần như không tăng trong khi CPU, queue wait, database wait hoặc GC pressure tăng, tín hiệu đó cho thấy cần tìm bottleneck thay vì tiếp tục tăng.

**Java 21+ virtual threads** có thể giảm chi phí giữ hàng loạt luồng chờ I/O so với platform threads trong một số workload, nhưng **không** xóa deadlock, không mở rộng connection pool/database và không biến thao tác CPU-bound thành vô hạn khả năng song song. Các ví dụ runnable trong bài vẫn dùng Java 17.

## 6. ThreadPoolTaskExecutor trong Spring Framework

`ThreadPoolTaskExecutor` bọc `ThreadPoolExecutor` và thường dùng làm executor của `@Async`. Cần hiểu **thứ tự nhận task** với cấu hình core, queue và max:

1. Khi số worker hiện tại dưới `corePoolSize`, executor tạo thêm worker cho task mới.
2. Khi đã đạt core, executor **ưu tiên đưa task vào queue nếu queue còn chỗ**.
3. Chỉ khi queue không nhận thêm được task, executor mới có thể mở thêm worker tới `maxPoolSize`.
4. Nếu cả worker lẫn queue đều tới giới hạn, task bị từ chối theo rejection policy.

Vì vậy, đặt `maxPoolSize = 100` nhưng giữ **queue không giới hạn** không có nghĩa pool sẽ chủ động tăng tới 100. Với mặc định của `ThreadPoolTaskExecutor` (core 1, max và queue rất lớn), phần lớn công việc có thể chỉ luân phiên qua một worker và queue ngày càng dài. Hãy cấu hình rõ giới hạn theo workload.

### 6.1. Ví dụ cấu hình bounded executor cho công việc blocking I/O

Đoạn sau là **mã tích hợp Spring**, yêu cầu Spring Framework và ứng dụng đã scan các bean; không phải chương trình `javac` độc lập:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Configuration
@EnableAsync
class ExecutorConfig {
    @Bean("ioExecutor")
    ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("io-worker-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();
        return executor;
    }
}

@Service
class AuditService {
    @Async("ioExecutor")
    public CompletableFuture<String> record(String eventId) {
        // Thay bằng nghiệp vụ thực, có timeout I/O riêng nếu gọi dịch vụ ngoài.
        return CompletableFuture.completedFuture("saved:" + eventId);
    }
}
~~~

Trong ví dụ, từ lúc đầy 4 core workers, executor xếp queue tối đa 32 task đang chờ; khi queue đầy, có thể mở thêm đến 8 workers. Sau khi toàn bộ worker bận và queue đầy, chính sách `AbortPolicy` dẫn đến lỗi từ chối (Spring có thể biểu diễn bằng `TaskRejectedException`). Các số **4/8/32 là ví dụ**, không phải giá trị tối ưu mặc định; cần đo thời gian chạy, độ trễ queue, dung lượng downstream và tải đỉnh rồi chọn.

Điểm cần nhớ:

- `@EnableAsync` kích hoạt xử lý `@Async`; `@Async("ioExecutor")` chọn bean executor có tên tương ứng.
- Với chế độ proxy mặc định, **gọi phương thức `@Async` từ phương thức khác trong cùng instance** (*self-invocation*) sẽ không đi qua proxy, nên không thực hiện async theo cách mong đợi. Lời gọi phải đi qua Spring-managed proxy.
- `@Async` chuyển nơi thực thi công việc sang worker; thao tác blocking trong method vẫn blocking **worker đó**. `CompletableFuture.completedFuture(...)` ở đây chỉ là kiểu kết quả từ method đang chạy trong worker.
- Không gọi `join()`/`get()` vô thời hạn trên tập task con trong chính pool đang xử lý task cha. Dùng composition không chặn hoặc thiết kế lại ranh giới phụ thuộc.
- Từ chối task cần hành vi có chủ đích: trả lỗi phù hợp, retry có backoff ở tầng được phép, kiểm soát tốc độ gửi hoặc ghi vào hàng đợi bền vững nếu nghiệp vụ đòi hỏi. Rejection không nên bị âm thầm nuốt.
- `CallerRunsPolicy` có thể tạo backpressure bằng cách cho **thread gửi task** chạy task, nhưng trên luồng HTTP/event-loop/scheduler có thể gây block ngoài ý muốn; không chọn theo thói quen.
- Gắn timeout/cancellation cho JDBC/HTTP client và các tác vụ chờ được phép ngắt. Timeout `Future.get(timeout)` chỉ giới hạn **thời gian caller chờ**; nó không mặc nhiên dừng I/O trong task đang chạy.
- Nếu một luồng gọi `@Async` nằm trong transaction, không giả định ngữ cảnh transaction thread-bound của caller tự động chuyển sang worker. Thiết kế transaction boundary trong chính công việc async khi cần.

Một `@Scheduled` chạy công việc lâu nên có scheduler/cấu hình concurrency thích hợp và chính sách không chạy chồng ngoài ý muốn. Không gộp mọi loại công việc vào cùng một pool chỉ vì cùng là “background task”.

## 7. Phát hiện sự cố từ bằng chứng

### 7.1. Thread dump và kiểm tra Java deadlock

Khi có dấu hiệu đứng, lấy **nhiều thread dump ở những thời điểm khác nhau** của cùng process để thấy có tiến triển hay không. Trên JDK có công cụ `jcmd` hoặc `jstack`, ví dụ process id là 12345:

~~~bash
jcmd 12345 Thread.print -l
jstack -l 12345
~~~

Thay 12345 bằng PID thực tế; cần quyền truy cập process và JDK tooling phù hợp. Khi đọc dump:

- Với deadlock trên monitor, xem chuỗi “waiting to lock” và “locked” tạo thành vòng; công cụ có thể báo “Found one Java-level deadlock”.
- Với `ReentrantLock`, xem ownable synchronizers và `ThreadMXBean.findDeadlockedThreads()` nếu JVM hỗ trợ.
- Với pool starvation, các worker có thể đang ở `FutureTask.get`/`CompletableFuture.join`, trong khi task chờ vẫn nằm trong executor queue. Kiểu phụ thuộc này **không nhất thiết** được thông báo như Java monitor deadlock.
- Với I/O chậm, nhiều stack có thể đợi socket, datasource hoặc remote API; kết hợp client metrics/log để xác định chỗ chờ.
- Với `WAITING` hay `TIMED_WAITING`, cần giải thích theo stack và trạng thái công việc, không quy tất cả là lỗi.

Có thể lấy thêm thread thông tin từ JMX/`ThreadMXBean`; công cụ kiểm tra lock phục vụ chẩn đoán, không nên gọi liên tục ở tần suất cao trong hot path sản xuất.

### 7.2. Đo executor và tài nguyên phía sau

Khi dùng `ThreadPoolTaskExecutor`, theo dõi `getActiveCount()`, `getPoolSize()`, `getCorePoolSize()`, `getMaxPoolSize()`, `getQueueSize()` (trên phiên bản Spring hỗ trợ), số task hoàn tất và số lần rejection. Song song cần theo dõi:

- Độ dài queue **và tuổi của task lâu nhất**; chỉ nhìn số lượng worker có thể bỏ qua hàng đợi dài.
- Độ trễ end-to-end p50/p95/p99, throughput hoàn tất và timeout/error rate.
- CPU hữu dụng theo quota/container, context switches, GC, heap/native memory và số thread.
- Số connection đang dùng/đang chờ của datasource, HTTP connection pool, hàng đợi hoặc rate limit của dịch vụ downstream.
- Thời gian chờ lock, stack lặp lại, truy vấn DB chậm và transaction đang mở.

**Dấu hiệu dễ nhầm:** `activeCount == maxPoolSize` không tự nó là deadlock; có thể chỉ là tải cao. Ngược lại, `activeCount < maxPoolSize` cũng không chứng minh pool có đủ sức xử lý: queue còn chỗ sẽ khiến executor chưa mở tới max.

### 7.3. Quy trình khoanh vùng theo bằng chứng

1. **Xác nhận triệu chứng:** tách “không task nào hoàn tất”, “hoàn tất chậm” và “nhiều task bị từ chối”; ghi thời điểm và mức tải.
2. **Chụp thread dumps cùng metrics:** nhìn trạng thái worker, stack, lock owner, active/queue/rejection và kết nối phụ thuộc.
3. **Tìm vòng chờ:** nếu thấy lock A→B→A, sửa thứ tự khóa/critical section; nếu thấy worker chờ task con của chính pool, sửa dependency blocking.
4. **Tìm tài nguyên giới hạn:** nếu nhiều worker đợi DB/network, đo capacity và latency tại đó trước khi tăng worker.
5. **Thực hiện một thay đổi có kiểm soát:** ví dụ rút ngắn I/O timeout, đặt queue bounded, sửa code chờ, hoặc điều chỉnh pool; kiểm tra lại throughput, p95/p99, lỗi và tài nguyên.
6. **Thử tải tăng dần và tải kéo dài:** xác nhận hệ thống đạt điểm ổn định, có chiến lược xử lý khi quá tải và hồi phục khi downstream chậm.

## 8. Nguyên tắc thiết kế để tránh tái phát

**Với khóa:** quy định thứ tự lấy lock toàn hệ thống; giảm phạm vi `synchronized`; không gọi hàm lạ, callback, I/O hoặc chờ future khi đang giữ nhiều khóa; cân nhắc bất biến dữ liệu và cấu trúc concurrent sẵn có thay cho khóa thủ công. Khóa phải được nhả đúng trên mọi đường thoát.

**Với task graph:** tránh task cha giữ worker để chờ tác vụ con bắt buộc chạy trong cùng pool; biểu diễn quan hệ bằng luồng xử lý tuần tự hoặc composition. Nếu bắt buộc có bước blocking, dành concurrency budget riêng dựa trên số kết nối và timeout cụ thể.

**Với backpressure:** dùng queue có giới hạn, kiểm soát số task đang xử lý và kết nối downstream. Khi vượt năng lực, từ chối sớm hoặc điều tiết nguồn vào một cách minh bạch. “Nhận mọi việc để xếp hàng” thường chỉ dời lỗi từ rejection sang timeout và tăng dùng bộ nhớ.

**Với timeout và retry:** timeout end-to-end phải bao gồm thời gian queue + thời gian thực thi + các I/O; retry phải có giới hạn, backoff/jitter và phù hợp idempotency. Retry ồ ạt lúc downstream chậm có thể làm cạn worker nhanh hơn.

**Với phân chia pool:** tách CPU-bound khỏi blocking I/O khi khác nhau rõ ràng về tài nguyên; tránh chia pool chỉ vì tên chức năng. Kích thước pool, queue, connection pool và ngưỡng admission phải được thiết kế **cùng nhau**.

## 9. Tình huống tổng hợp trong ứng dụng Spring

Giả sử một dịch vụ Spring MVC dùng `@Async("ioExecutor")` để xuất báo cáo. Mỗi tác vụ cần một DB connection và gọi một API ngoài. Khi tải cao, quan sát thấy:

| Số liệu giả định | Quan sát |
| --- | --- |
| Executor | 8/8 workers bận; queue gần đầy 32/32 |
| Database pool | 10/10 connections đang dùng; có thread đợi lấy connection |
| API ngoài | p99 cao và thỉnh thoảng timeout |
| Đầu ra | Thông lượng không tăng, request bị timeout hoặc task bị reject |

Đây **chưa đủ bằng chứng** để kết luận deadlock. Thread dump không thấy vòng khóa, nhưng thấy nhiều worker đợi I/O. Nếu chỉ nâng `maxPoolSize` từ 8 lên 64, nhiều task hơn có thể đồng thời tranh 10 DB connections và API đang chậm; queue chờ chỉ chuyển từ executor sang connection pool, trong khi độ trễ có thể xấu hơn.

Hướng xử lý dựa trên nguyên nhân là: xác định bước I/O nào chậm; đặt timeout hữu hạn và hủy khi phù hợp; giảm thời gian giữ connection; kiểm soát số task đồng thời vào downstream; bounded queue và phản hồi quá tải; cân nhắc tăng database/HTTP pool **chỉ khi hệ thống phía sau chịu được**. Sau đó thử tải và so sánh throughput, p95/p99, rejection, connection wait. Nếu thread dump thực sự thấy vòng khóa, ưu tiên sửa deadlock đó trước khi tuning pool.

## 10. Tự kiểm tra kiến thức

**Câu 1. Hai thread đều `BLOCKED` có chắc deadlock không?** Không. Cần chứng minh chúng chờ nhau theo vòng (hoặc một chu trình dài hơn). Chờ cùng một lock rồi lần lượt được cấp lock không phải deadlock.

**Câu 2. Tại sao đặt `maxPoolSize=100` nhưng chỉ thấy vài worker?** Với `ThreadPoolExecutor`, sau core, task thường được xếp vào queue trước. Nếu queue rất lớn, nó chưa có lý do mở thêm tới max; phải nhìn `queueCapacity` và các metrics.

**Câu 3. Ví dụ pool một worker chờ `inner.get()` thuộc loại gì?** Thread-pool starvation do task dependency: worker giữ chỗ, task cần chạy để giải phóng worker lại nằm trong chính queue. Trình phát hiện monitor deadlock có thể không nhìn thấy.

**Câu 4. Khi nào thêm worker có thể giúp?** Khi worker chủ yếu chờ I/O, downstream còn năng lực, và concurrency chưa chạm giới hạn CPU, memory, connection, rate limit hay queue. Quyết định phải được xác nhận bằng tải thực tế.

**Câu 5. Virtual threads có giải quyết deadlock hoặc connection pool cạn không?** Không. Chúng thay đổi chi phí mô hình luồng chờ của một số workload, không làm mất vòng khóa và không tăng năng lực database.

**Câu 6. Một task bị timeout khi gọi `Future.get(500, MILLISECONDS)` có tự bị hủy không?** Không. Timeout chỉ chấm dứt lượt chờ của caller. Muốn yêu cầu hủy phải gọi `cancel(...)` hoặc dùng cơ chế timeout/hủy của I/O, và task phải hợp tác với interruption/cancellation.

## 11. Tài liệu tham khảo

- Spring Framework — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework — `ThreadPoolTaskExecutor` implementation/API: https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.java
- Java SE 17 — Monitoring and Management / deadlock diagnosis: https://docs.oracle.com/en/java/javase/17/management/using-jconsole.html
- Java SE — `ThreadMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
