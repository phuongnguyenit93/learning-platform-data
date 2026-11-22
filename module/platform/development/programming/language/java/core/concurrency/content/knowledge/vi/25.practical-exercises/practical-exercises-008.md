# Bài tập thực tế: Triển khai Semaphore giới hạn tài nguyên đồng thời trong Java

## 1. Đề bài và mục tiêu

Một ứng dụng Java có nhiều tác vụ chạy đồng thời, nhưng một tài nguyên khan hiếm chỉ phục vụ tối đa **3 tác vụ cùng lúc**. Tài nguyên có thể là thiết bị, kết nối tới hệ thống ngoài, phiên giao dịch đặc biệt, hoặc một thao tác rất tốn bộ nhớ. Khi 12 yêu cầu đến gần nhau, ứng dụng cần:

1. Cho tối đa 3 tác vụ vào đoạn sử dụng tài nguyên.
2. Các tác vụ còn lại chờ một khoảng thời gian hữu hạn hoặc thất bại có kiểm soát.
3. Bất kể thao tác thành công, ném exception hay bị interrupt sau khi đã vào, quyền truy cập đều được hoàn lại.
4. Kiểm chứng giới hạn bằng biến đếm thread-safe, không suy ra từ thứ tự dòng log.
5. Đo số lượt đang hoạt động, cực đại đồng thời, thời gian chờ và số lần timeout.
6. Phân biệt giới hạn truy cập tài nguyên với giới hạn số tác vụ nằm trong hàng đợi ExecutorService.

Bài thực hành này thuộc **Java Concurrency thuần JDK**, không dùng Spring hay thành phần thuộc chương Spring. Ví dụ dùng Java 17+.

### Tiêu chí nghiệm thu

- Một **Semaphore** được chia sẻ cho mọi tác vụ dùng cùng resource budget.
- Mỗi tác vụ phải lấy permit thành công **trước** khi sử dụng tài nguyên.
- Mỗi permit đã lấy được hoàn trả **đúng một lần** qua finally, kể cả khi có exception.
- Timeout/interrupt lúc chờ không làm phát sinh release giả.
- Trong thử nghiệm nhiều thread: 0 ≤ active ≤ limit và peak ≤ limit.
- Sau khi tất cả tác vụ hoàn thành: active = 0, availablePermits = limit.
- Giải thích được các giới hạn còn lại: queue backlog, downstream timeout, fairness và performance.

## 2. Semaphore là gì?

**java.util.concurrent.Semaphore** giữ một bộ đếm quyền truy cập gọi là **permit**. Với Semaphore(3), ban đầu có 3 permits. Lời gọi acquire() thành công lấy một permit; release() trả một permit.

~~~text
Ban đầu: available = 3

Thread A: acquire -> available = 2 -> dùng tài nguyên
Thread B: acquire -> available = 1 -> dùng tài nguyên
Thread C: acquire -> available = 0 -> dùng tài nguyên
Thread D: acquire -> phải chờ permit

Thread B: release -> một waiter có thể được cấp permit
Thread D: tiếp tục -> dùng tài nguyên
~~~

Semaphore là cơ chế **đếm quyền**, không tự quản lý kết nối, object, transaction hay vòng đời tài nguyên thực tế. Code ứng dụng phải tuân thủ giao thức:

~~~text
Xin permit -> chỉ sau khi được cấp mới vào vùng tài nguyên
           -> dù thoát theo đường nào cũng hoàn lại permit
~~~

Các API chính:

| API | Hành vi | Khi nào dùng |
|---|---|---|
| new Semaphore(N) | N permits, non-fair mặc định | Giới hạn số tác vụ đồng thời, ưu tiên throughput |
| new Semaphore(N, true) | N permits, bật tính công bằng khi cấp permit theo thứ tự ở điểm xếp hàng nội bộ | Muốn tránh một waiter bị chen liên tục |
| acquire() | Chặn đến khi có permit hoặc bị interrupt | Có thể chờ nhưng nên kiểm soát lifecycle |
| tryAcquire() | Thành công ngay hoặc trả false, không chờ | Fail-fast khi hệ thống đang bận |
| tryAcquire(timeout, unit) | Chờ tối đa một khoảng, trả boolean; có thể bị interrupt | Admission có deadline |
| release() | Tăng một permit; có thể đánh thức waiter | Chỉ sau acquire thành công |
| availablePermits() | Số permits có thể lấy ngay lúc quan sát | Telemetry hoặc kiểm tra khi hệ thống đã quiescent |
| getQueueLength() | Ước lượng số thread đang chờ permit | Theo dõi, không làm điều kiện đồng bộ chính |
| acquire(k), release(k) | Xin/trả nhiều permits một lần | Tài nguyên có trọng số |

**Cực kỳ quan trọng:** Semaphore không có ownership kiểu ReentrantLock. Thread chưa từng acquire vẫn có thể gọi release; nếu lập trình sai, availablePermits có thể vượt capacity ban đầu. Vì vậy cặp acquire/release được ứng dụng đảm bảo bằng cấu trúc code và kiểm thử.

### Semaphore và synchronized/Lock khác nhau

- synchronized/ReentrantLock chủ yếu dùng để bảo vệ **tính nhất quán của shared mutable state** trong critical section.
- Semaphore(N) chủ yếu giới hạn **số lượt thực hiện đồng thời** một hoạt động; N có thể lớn hơn 1.
- Semaphore(1) có thể dùng như binary semaphore, nhưng không thay thế mọi đặc tính ownership và reentrancy của ReentrantLock.
- Khi ba task cùng đi qua Semaphore(3), chúng **vẫn chạy cạnh tranh**. Nếu cả ba cùng sửa một HashMap không an toàn, Semaphore(3) không làm HashMap thread-safe.

## 3. Thiết kế lớp limiter có timeout và dọn dẹp

Ta tạo lớp **SemaphoreLimiter** với các thành phần:

- limit: số tác vụ tối đa cùng sử dụng tài nguyên.
- Semaphore: cấp permits chung, cấu hình fair=true trong ví dụ để dễ phân tích lịch chờ.
- execute(Callable, timeout, TimeUnit): chờ permit rồi chạy thao tác; ném TimeoutException nếu hết thời gian chờ.
- AtomicInteger active: số tác vụ đã vào vùng tài nguyên và chưa hoàn thành.
- AtomicInteger peak: giá trị active lớn nhất từng quan sát.

**Thiết kế thứ tự bắt buộc:**

~~~text
tryAcquire(timeout)
    |
    +-- false --------> TimeoutException, không release
    |
    +-- InterruptedException --> truyền lỗi, không release
    |
    +-- true ---------> tăng active
                         |
                         +-- operation.call()
                         |      |
                         |      +-- thành công / exception / interrupt
                         |
                         +-- finally: giảm active
                         +-- finally: release 1 permit
~~~

Timeout ở đây chỉ áp dụng **thời gian đợi permit**, không giới hạn thời gian của operation sau khi đã vào. Timeout của network/database/tác vụ thật cần được xử lý riêng.

## 4. Chương trình Java 17 hoàn chỉnh

Lưu file **SemaphoreLimiterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreLimiterDemo {
    static final class SemaphoreLimiter {
        private final int limit;
        private final Semaphore permits;
        private final AtomicInteger active = new AtomicInteger();
        private final AtomicInteger peak = new AtomicInteger();

        SemaphoreLimiter(int limit, boolean fair) {
            if (limit <= 0) {
                throw new IllegalArgumentException("limit must be positive");
            }
            this.limit = limit;
            this.permits = new Semaphore(limit, fair);
        }

        <T> T execute(Callable<T> operation, long timeout, TimeUnit unit)
                throws Exception {
            Objects.requireNonNull(operation, "operation");
            Objects.requireNonNull(unit, "unit");
            if (timeout < 0) {
                throw new IllegalArgumentException("negative timeout");
            }

            // No permit is owned when this returns false or is interrupted.
            if (!permits.tryAcquire(timeout, unit)) {
                throw new TimeoutException("No permit available");
            }

            try {
                int current = active.incrementAndGet();
                peak.accumulateAndGet(current, Math::max);
                try {
                    return operation.call();
                } finally {
                    active.decrementAndGet();
                }
            } finally {
                // Exactly one release for each successful acquisition.
                permits.release();
            }
        }

        int limit() { return limit; }
        int active() { return active.get(); }
        int peak() { return peak.get(); }
        int available() { return permits.availablePermits(); }
        int waitingEstimate() { return permits.getQueueLength(); }
    }

    public static void main(String[] args) throws Exception {
        final int limit = 3;
        final int tasks = 12;
        SemaphoreLimiter limiter = new SemaphoreLimiter(limit, true);
        ExecutorService pool = Executors.newFixedThreadPool(8);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < tasks; i++) {
                final int id = i;
                futures.add(pool.submit(() ->
                    limiter.execute(() -> {
                        // Simulates holding an external scarce resource.
                        Thread.sleep(60);
                        return id;
                    }, 10, TimeUnit.SECONDS)
                ));
            }

            int sum = 0;
            for (Future<Integer> future : futures) {
                sum += future.get();
            }

            if (sum != 66) {
                throw new AssertionError("Unexpected task results");
            }
            if (limiter.peak() > limit || limiter.active() != 0) {
                throw new AssertionError("Concurrency limit violated");
            }
            if (limiter.available() != limit) {
                throw new AssertionError("Permits were not restored");
            }

            System.out.println("Completed: " + futures.size());
            System.out.println("Result sum: " + sum);
            System.out.println("Peak within limit: " +
                    (limiter.peak() <= limiter.limit()));
            System.out.println("Active after finish: " + limiter.active());
            System.out.println("Permits restored: " + limiter.available());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }
}
~~~

Chạy tại thư mục chứa file:

~~~bash
javac SemaphoreLimiterDemo.java
java SemaphoreLimiterDemo
~~~

Khi toàn bộ các tác vụ kết thúc bình thường trước thời hạn, stdout:

~~~text
Completed: 12
Result sum: 66
Peak within limit: true
Active after finish: 0
Permits restored: 3
~~~

Con số **peak cụ thể** không in ra vì phụ thuộc lịch chạy, nhưng điều kiện peak ≤ 3 được kiểm tra. Nếu hệ điều hành quá tải hoặc tác vụ bị interrupt khiến không xin được permit trong 10 giây, Future.get() sẽ ném ExecutionException, và không nên coi stdout ở trên là cam kết thời gian chạy cho mọi máy.

### Giải thích cơ chế trong mã

**Semaphore phải được chia sẻ.** Một SemaphoreLimiter được tạo trước vòng for, rồi truyền tới tất cả task. Nếu mỗi task tự tạo Semaphore(3), không tồn tại một giới hạn chung.

**Đặt acquire trước finally.** tryAcquire(timeout, unit) trả false hoặc ném InterruptedException thì chưa lấy permit, không được release. Khi đã trả true, try/finally bao trọn đoạn sử dụng tài nguyên.

**Atomic metrics không thay thế Semaphore.** AtomicInteger đảm bảo biến đếm không bị lost update. Nhưng active.incrementAndGet() không tự giới hạn active; chính Semaphore xác định ai được vào. Metrics phục vụ kiểm tra và quan sát.

**Executor không phải Semaphore.** Fixed thread pool 8 worker có thể cho tới 8 tasks bắt đầu, trong đó tối đa 3 đi qua vùng cần permit, các worker khác có thể chờ. Pool kiểm soát thread hoạt động; Semaphore kiểm soát lượt sử dụng tài nguyên.

**Future.get() cần thiết.** Nó chờ các tác vụ hoàn thành và không im lặng nuốt lỗi từ Callable. Chỉ sau khi tất cả futures trả về thành công, phép so sánh final active=0 và available=3 mới là kiểm tra trạng thái kết thúc có ý nghĩa.

**Thread.sleep(60) chỉ mô phỏng thời gian giữ tài nguyên.** Nó không mô phỏng throughput của database, mạng hoặc phần cứng và không dùng để chứng minh thứ tự scheduling. Giá trị 60ms chỉ tạo một đoạn hoạt động đủ dễ quan sát.

## 5. Kiểm thử timeout bằng kết quả tất định

Để xác minh rằng việc xin permit thất bại không làm hỏng counter, ta chủ động lấy permit duy nhất bằng main thread trước khi gọi timed tryAcquire.

Lưu file **SemaphoreTimeoutDemo.java**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class SemaphoreTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore semaphore = new Semaphore(1, true);
        semaphore.acquire();
        try {
            boolean acquired =
                    semaphore.tryAcquire(100, TimeUnit.MILLISECONDS);
            System.out.println("Second acquire: " + acquired);
            System.out.println("While held: " +
                    semaphore.availablePermits());
        } finally {
            semaphore.release();
        }
        System.out.println("After release: " +
                semaphore.availablePermits());
    }
}
~~~

Chạy:

~~~bash
javac SemaphoreTimeoutDemo.java
java SemaphoreTimeoutDemo
~~~

Stdout:

~~~text
Second acquire: false
While held: 0
After release: 1
~~~

Vì main giữ permit xuyên suốt lời gọi timed tryAcquire, không thread nào có thể cấp permit thứ hai. Hàm trả false sau khoảng chờ được yêu cầu, rồi finally trả **permit đầu tiên**. Đây là kiểm tra logic độc lập với thời điểm in log.

### Mẫu sai: release cả khi xin permit thất bại

~~~java
boolean acquired = semaphore.tryAcquire();
try {
    if (acquired) {
        useResource();
    }
} finally {
    semaphore.release();  // BUG if acquired == false
}
~~~

Đây là đoạn lỗi minh họa, không biên dịch độc lập do useResource chưa được định nghĩa. Nếu acquired=false, finally vẫn tăng permits. Semaphore không có phép kiểm owner nên nhiều lần over-release có thể làm số task được phép vượt capacity. Cách đúng là chỉ vào try/finally sau acquire thành công, hoặc release có điều kiện trên cờ acquired được gán chính xác.

## 6. Kiểm thử nhánh exception: vẫn phải trả permit

Thêm method sau vào bên trong class **SemaphoreLimiterDemo** để tự luyện tập. Method này cần chạy **khi không có task khác đang dùng cùng limiter**, để so sánh trước/sau có ý nghĩa.

~~~java
static void testException(SemaphoreLimiter limiter) throws Exception {
    int before = limiter.available();

    try {
        limiter.execute(() -> {
            throw new IllegalStateException("simulated failure");
        }, 1, TimeUnit.SECONDS);
        throw new AssertionError("Exception was expected");
    } catch (IllegalStateException expected) {
        // Expected failure inside the protected operation.
    }

    if (limiter.available() != before || limiter.active() != 0) {
        throw new AssertionError("Permit leak after failure");
    }
}
~~~

Trường hợp này không cần một chương trình standalone mới; hãy gọi testException(limiter) trong main sau khi đã chờ tất cả futures. Exception từ operation.call() không làm bỏ qua hai finally trong execute(), vì vậy active giảm về 0 và permit được hoàn lại.

**Chú ý:** release permit không tự động đóng connection, rollback transaction hoặc giải phóng thiết bị. Nếu tài nguyên thật cần cleanup, operation nên dùng try-with-resources hoặc finally riêng cho resource, sau đó limiter mới trả quyền vào.

### InterruptedException và cancellation

- Khi chờ acquire() hoặc tryAcquire(timeout, unit), thread có thể bị interrupt; API ném InterruptedException. Khi đó không được gọi release vì chưa được cấp permit.
- Khi **đã lấy permit**, operation có thể bị interrupt (ví dụ Thread.sleep hoặc I/O hỗ trợ interruption). Dù exception được truyền lên, finally vẫn trả permit.
- Nếu một tầng bắt InterruptedException nhưng không truyền tiếp, thường cần phục hồi cờ interrupt bằng Thread.currentThread().interrupt() trước khi kết thúc hoặc xử lý hủy theo contract.
- Future.cancel(true) là yêu cầu interrupt, không bảo đảm công việc bên dưới lập tức dừng. I/O blocking hoặc code không hợp tác có thể tiếp tục giữ permit.
- Timed tryAcquire giới hạn **thời gian đợi để vào**, không giới hạn **thời gian chiếm tài nguyên**. Cần deadline riêng cho I/O hoặc tác vụ thật.

Ví dụ mẫu xử lý interruption ở tầng gọi:

~~~java
try {
    limiter.execute(operation, 500, TimeUnit.MILLISECONDS);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Stop or return according to the caller's cancellation contract.
}
~~~

Đây là đoạn minh họa tích hợp, chưa độc lập vì limiter và operation phải được khai báo theo context ứng dụng.

## 7. Fairness: có bảo đảm FIFO tuyệt đối không?

~~~java
Semaphore fair = new Semaphore(3, true);
Semaphore nonFair = new Semaphore(3, false);
~~~

- **Non-fair** không đảm bảo thứ tự waiter; task đến sau có thể lấy permit trước người đợi trước, đôi khi tăng throughput.
- **Fair** chọn waiter theo thứ tự đến **điểm xếp hàng nội bộ** của các lời gọi acquire. Nó không đảm bảo thread gọi hàm sớm hơn sẽ hoàn thành sớm hơn, cũng không thay đổi scheduling và thứ tự submit ở executor.
- **Một ngoại lệ quan trọng:** tryAcquire() tức thì có thể lấy permit còn trống dù Semaphore fair và đã có waiters. Nếu muốn tôn trọng fairness trong thử không chờ, tài liệu JDK gợi ý tryAcquire(0, TimeUnit.SECONDS), có thể ném InterruptedException.
- Fairness có thể làm thay đổi overhead, throughput và tail latency. Chọn true/false từ yêu cầu sản phẩm và benchmark thực tế, không chỉ từ trực giác.

Trong demo, fair=true ưu tiên cách cấp quyền dễ lý giải cho yêu cầu chờ tài nguyên. Mọi phép đo thứ tự start/end vẫn có thể khác vì tám worker được scheduler điều phối độc lập.

## 8. Cách chứng minh giới hạn bằng stress test

Biến active chỉ tăng khi đã lấy permit và giảm trước khi trả permit. Vì vậy nếu mọi task đi đúng đường execute(), bất biến cần kiểm tra là:

~~~text
0 <= active <= limit
0 <= peak <= limit

Sau khi tất cả công việc hoàn thành:
active == 0
availablePermits() == limit
~~~

Một kế hoạch kiểm thử hữu ích:

| Tình huống | Cách tạo | Kết quả cần kiểm |
|---|---|---|
| Tải thấp | 2 tasks, limit=3 | Không có timeout; peak ≤ 2 |
| Tải tranh chấp | 12 tasks, 8 workers, limit=3 | peak ≤ 3; cuối cùng active=0 |
| Quá hạn | Giữ hết permit, gọi timed tryAcquire | False hoặc TimeoutException theo lớp wrapper |
| Exception trong operation | Ném RuntimeException sau acquisition | Exception truyền lên, permits được trả |
| Interrupted waiter | Giữ permit, interrupt thread đang chờ | Không tiếp tục thao tác, không release giả |
| Task bị hủy sau khi vào | Interrupt công việc đang giữ permit | Cleanup chạy nếu operation kết thúc/hợp tác |
| Over-release regression | Cố gọi release hai lần trong phiên bản lỗi | Test phải phát hiện permits vượt capacity |
| Nhiều task liên tục | Lặp các batch độc lập | Không tích lũy permit leak theo thời gian |

Khi stress, có thể dùng CountDownLatch làm cổng xuất phát chung để tăng khả năng tranh chấp. Nhưng CountDownLatch **không chứng minh** một lịch chạy cụ thể; scheduler vẫn quyết định thời điểm từng worker được chạy. Hãy ghi mọi exception và dùng biến đếm nguyên tử thay vì suy luận từ thứ tự System.out.println.

Nếu muốn thăm dò các tương tác Java Memory Model tinh vi hơn, jcstress là công cụ khác ngoài JDK. Với bài tập Semaphore này, invariant active ≤ limit cùng các trường hợp timeout/exception/interruption là các bằng chứng gần mục tiêu hơn việc tìm một lịch chạy cụ thể.

## 9. Semaphore không giới hạn tổng backlog

Sơ đồ khi pool có 8 worker, Semaphore 3 permits, 12 task đã submit:

~~~text
12 tasks submitted
       |
       v
ExecutorService: up to 8 worker threads running tasks
       |
       +-- 3 workers acquire permits --> resource usage
       |
       +-- 5 workers may wait for permits
       |
       +-- other submitted tasks remain in executor queue
~~~

Giới hạn 3 chỉ áp dụng **vùng đã acquire permit**. Executors.newFixedThreadPool() dùng hàng đợi công việc về cơ bản không giới hạn; nếu producer submit liên tục nhanh hơn năng lực xử lý, queue có thể lớn dần, làm tăng bộ nhớ và độ trễ, dù Semaphore hoạt động đúng.

Để bảo vệ ứng dụng thực tế, xem xét thêm:

1. ThreadPoolExecutor với **bounded queue** và chính sách RejectedExecutionHandler minh bạch.
2. Rate limit hoặc backpressure tại điểm nhận dữ liệu, trước khi backlog lên quá cao.
3. Thời hạn chờ permit và thời hạn xử lý I/O thật, cùng timeout ở downstream.
4. Metrics executor queue depth, queue wait, rejected tasks và total end-to-end latency.
5. Điều phối tài nguyên sao cho không giữ lock/connection quý hiếm khác trong lúc chờ permit.

### Acquire trong task hay trước khi submit?

**Acquire trong task** như demo: tài nguyên được xin ngay trước thao tác, finally nằm cùng phạm vi; dễ đúng, nhưng có thể khiến worker bị chặn khi chưa thực hiện công việc.

**Acquire trước submit**: tạo áp lực ngược lên producer sớm hơn, nhưng khó quản lý ownership. Nếu submit ném RejectedExecutionException hoặc Future bị hủy **trước khi chạy**, permit đã lấy có thể bị rò nếu chỉ release bên trong task. Muốn cách này, cần một admission wrapper quản lý đầy đủ vòng đời submit/cancel/reject/complete.

Với Java 21 virtual threads, việc chờ Semaphore có thể tốn ít platform threads hơn. Nhưng virtual threads không tạo thêm CPU, không tăng capacity của downstream và không loại bỏ yêu cầu timeout, lifecycle hay giám sát backlog.

## 10. Những lỗi triển khai phổ biến

### Lỗi A — Acquire nằm trong try và release mù

~~~java
try {
    semaphore.acquire();
    useResource();
} finally {
    semaphore.release();
}
~~~

Nếu acquire() ném InterruptedException **trước khi lấy permit**, finally vẫn gọi release và tạo permit dư. Đặt acquire() trước try/finally hoặc duy trì cờ acquired chính xác.

### Lỗi B — Không dùng finally

~~~java
semaphore.acquire();
useResource();
semaphore.release();
~~~

Nếu useResource() ném exception, permit không được trả. Sau nhiều lỗi, các waiter có thể kẹt dù tài nguyên thực đã rảnh. Phải đưa release vào finally.

### Lỗi C — Mỗi task có Semaphore riêng

~~~java
void doTask() throws InterruptedException {
    Semaphore local = new Semaphore(3);
    local.acquire();
    try {
        useResource();
    } finally {
        local.release();
    }
}
~~~

Đây chỉ là đoạn minh họa lỗi. Mỗi task tạo một ngân sách mới nên **không giới hạn chung**. Semaphore phải thuộc về service/resource limiter được chia sẻ.

### Lỗi D — Kiểm tra availablePermits thay cho acquire

~~~java
if (semaphore.availablePermits() > 0) {
    useResource(); // No permit was reserved: a race.
}
~~~

availablePermits() chỉ là snapshot, không phải phép check-and-reserve nguyên tử. Nhiều thread có thể cùng thấy >0. Dùng acquire hoặc tryAcquire.

### Lỗi E — Release thêm trong catch rồi lại release trong finally

~~~java
semaphore.acquire();
try {
    useResource();
} catch (RuntimeException e) {
    semaphore.release(); // Double release path!
    throw e;
} finally {
    semaphore.release();
}
~~~

Mọi permit lấy thành công chỉ được release **một lần**. Không gọi riêng trong catch nếu finally đã làm nhiệm vụ đó.

### Lỗi F — Semaphore(3) làm shared state tự động an toàn

Ba task có thể cùng đi qua vùng protected. Nếu chúng đồng thời ghi một HashMap không thread-safe hoặc cùng sửa balance không đồng bộ, vẫn có data race. Dùng cấu trúc concurrent, atomic update hoặc khóa phù hợp **bên trong vùng**.

### Lỗi G — Chờ permit trong khi giữ một lock mà holder cần

T1 giữ lock X, rồi chờ permit; T2 giữ permit nhưng cần lock X để hoàn tất và release. Đây là chu trình deadlock. Xác định thứ tự lấy các loại tài nguyên và tránh block trong critical section không cần thiết.

### Lỗi H — Giả định timeout acquire là timeout operation

tryAcquire(100ms) chỉ giới hạn việc đợi **để bắt đầu**. Sau đó một lời gọi remote có thể bị treo vài phút, giữ permit và làm mọi waiter khác hết hạn. Thiết kế timeouts/cancellation ở tầng I/O riêng.

### Lỗi I — Coi getQueueLength là số tuyệt đối

getQueueLength() chỉ là ước lượng tức thời và đang thay đổi khi thread acquire/release. Nó hợp lý để quan sát xu hướng, không dùng để khẳng định invariant hoặc tự triển khai admission logic bằng if.

## 11. Chọn số permits phù hợp

Không có một limit đúng cho mọi workload.

- **Resource pool hữu hạn:** nếu chỉ có 3 thiết bị hoặc 3 connections dùng được, limit thường không vượt 3.
- **CPU-bound:** có thể bắt đầu đo quanh số logical processors được cấp. Nhưng Semaphore chỉ một công cụ giới hạn tác vụ, không làm code chạy nhanh hơn.
- **I/O-bound:** task thường chờ nên số task in-flight có thể lớn hơn số cores; tuy vậy downstream cũng có giới hạn kết nối, memory và quota riêng.
- **External API:** số yêu cầu đồng thời khác số yêu cầu/giây. Semaphore không tự áp dụng rate limit theo thời gian; nếu API có quota QPS cần thêm cơ chế rate limiter.

Một ước lượng trong trạng thái ổn định:

~~~text
Average in-flight work ≈ throughput × average time held
~~~

Nếu resource phục vụ 20 calls/giây và một call giữ quyền 0,1 giây trung bình, in-flight trung bình xấp xỉ 2. Nhưng không thể kết luận limit=2 đủ xử lý mọi burst, p99 latency hoặc nhu cầu headroom. Đo thực tế với workload đại diện và giới hạn của hệ thống ngoài.

Các metric cần theo dõi:

| Metric | Câu hỏi nó trả lời |
|---|---|
| active, peak | Có bao nhiêu task thực đang dùng resource, cực đại ra sao? |
| available permits | Sức chứa còn rảnh tại một thời điểm là bao nhiêu? |
| waiting estimate | Có nhiều worker đang chờ Semaphore không? |
| acquire wait duration | Yêu cầu mất bao lâu để vào? |
| acquire timeout count | Bao nhiêu lần không xin được quyền trong deadline? |
| hold duration | Một task giữ permit bao lâu? |
| operation error rate | Công việc được phép vào nhưng thất bại với tần suất nào? |
| executor queue length | Backlog đã tích tụ trước khi task tới Semaphore? |
| end-to-end p95/p99 | Người dùng có phải đợi lâu dù throughput vẫn cao? |

Quan sát thời gian chờ permit và thời gian giữ permit riêng để xác định vấn đề ở admission hay downstream. Đừng tăng limit chỉ để làm giảm waiting nếu resource thực không đủ sức phục vụ.

## 12. Bài tập mở rộng

**Bài A — Đổi limit và đo thời gian.** Chạy chương trình với limit lần lượt 1, 2, 3, 5, giữ nguyên 12 tasks và work. Ghi thời gian batch, peak và timeout. Giải thích vì sao sleep demo thường chồng lấp được thời gian chờ nhưng database thật có thể quá tải nếu tăng connections.

**Bài B — Fail-fast.** Thay timed tryAcquire bằng tryAcquire() không đợi. Khi hết permit, từ chối ngay. So sánh độ trễ và số lần reject với cách đợi tới 10 giây. Lưu ý tryAcquire() tức thì không tôn trọng fairness như các lời gọi timed acquire.

**Bài C — Failure injection.** Cho một nửa task ném IllegalStateException sau khi vào vùng. Chờ tất cả futures, chấp nhận và ghi nhận ExecutionException dự kiến, sau đó xác nhận active=0 và availablePermits=limit.

**Bài D — Interrupt waiter.** Một thread chính giữ toàn bộ permit, thread khác thử acquire(). Interrupt waiter và xác nhận nó không dùng tài nguyên hay release. Cuối cùng main release đúng số permit nó giữ. Có thể dùng CountDownLatch để đồng bộ điểm bắt đầu, nhưng tránh giả định một sleep đủ bảo đảm trạng thái WAITING.

**Bài E — ResourceLease tự đóng.** Thiết kế Lease implements AutoCloseable để có thể viết try-with-resources. Lease nên idempotent: close() hai lần vẫn chỉ release một permit, ví dụ bảo vệ bằng AtomicBoolean. Định nghĩa rõ trách nhiệm khi chuyển lease giữa threads.

**Bài F — Hàng đợi hữu hạn.** Thay fixed thread pool bằng ThreadPoolExecutor có ArrayBlockingQueue và chính sách reject. So sánh với phiên bản cũ khi producer submit nhanh hơn consumer; kiểm tra queue depth, rejection và memory để thấy khác biệt giữa semaphore và backpressure ở cổng vào.

## 13. Checklist hoàn thành

- [ ] Có đúng một Semaphore chia sẻ theo resource budget.
- [ ] Validate limit > 0, timeout không âm và tham số không null.
- [ ] Mọi operation phải acquire thành công trước khi dùng tài nguyên.
- [ ] Release đúng một lần theo finally, kể cả exception/interruption.
- [ ] Timed-out/rejected acquisition không gây over-release.
- [ ] active ≤ limit được kiểm tra trong thử nghiệm nhiều task.
- [ ] Sau khi mọi futures hoàn tất, active=0 và permits trở về limit.
- [ ] Không dùng availablePermits hay log order làm công cụ đồng bộ.
- [ ] Không nhầm fairness với thứ tự hoàn thành task.
- [ ] Có chính sách cho executor queue, timeout downstream và cancellation.
- [ ] Đo throughput, latency, thời gian chờ permit và thời gian giữ resource.
- [ ] Không dùng Semaphore thay thế việc đồng bộ dữ liệu chia sẻ không an toàn.

## 14. Tổng kết

**Semaphore(N)** giới hạn tối đa N tác vụ **đã xin permit và chưa trả** đi vào vùng tài nguyên, khi mọi task tuân thủ đúng hợp đồng acquire/release. Mẫu cốt lõi:

~~~java
semaphore.acquire();
try {
    useResource();
} finally {
    semaphore.release();
}
~~~

Nếu cần timeout, thay acquire() bằng tryAcquire(timeout, unit) và **chỉ** vào try/finally khi trả true. Đối với ứng dụng có tải lớn, kết hợp Semaphore với bounded queue, admission policy và timeouts của tài nguyên thật.

Tham khảo JDK chính thức: [Semaphore (Java 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html), [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html), [AtomicInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html), [TimeUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html).
