# 22.4 Tái hiện pool bão hòa và tách thời gian chờ hàng đợi khỏi thời gian chạy

> **Module:** Java Advance – runtime-diagnostics, phần **22. Thực hành tổng hợp**. Bài lab Java 17+ dùng `ThreadPoolExecutor` với một worker và hàng đợi có giới hạn để tạo ra trạng thái bão hòa một cách có kiểm soát. Bằng các mốc `submit → start → finish`, ta tách **độ trễ chờ được thực thi** khỏi **độ trễ khi task đã chạy**, từ đó phân biệt lỗi overload, backlog, tác vụ chậm và cách xử lý phù hợp.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Diễn giải cách `corePoolSize`, `maximumPoolSize`, `BlockingQueue` và `RejectedExecutionHandler` quyết định một task được chạy, xếp hàng hay từ chối.
2. Tái hiện trạng thái **một task đang chạy + một task chờ trong queue + task thứ ba bị reject**, không phụ thuộc may rủi của `Thread.sleep()` ở thời điểm submit.
3. Đo riêng **submit-to-start latency** và **run duration** bằng `System.nanoTime()`, kiểm tra quan hệ với tổng task latency.
4. Giải thích vì sao task chạy 40 ms nhưng caller có thể chờ 300 ms hoặc hơn.
5. Dùng queue depth, active workers, rejection, wait/run histograms, thread dumps, JFR và application metrics để nhận diện nguyên nhân bão hòa.
6. Thiết kế cách giới hạn tải và tuning có chứng cứ, không mặc định “tăng pool” hoặc “đổi sang queue vô hạn” là sửa được bottleneck.

**Tình huống xuất phát:** Người dùng báo API mất 900 ms, nhưng profiler thấy đoạn xử lý business chỉ khoảng 40 ms. Nếu task nằm trong executor queue gần 850 ms trước lúc worker rảnh, tối ưu 40 ms còn 30 ms chỉ tiết kiệm được 10 ms. Phải đo **hai pha** trước khi chọn giải pháp.

## 2. Phân biệt ba khoảng thời gian

Đối với một task đã được pool nhận:

```text
Caller                            ThreadPoolExecutor                    Worker
   |                                     |                                 |
   | -- submit task -------------------->|                                 |
   |    tSubmit                          | -- queue / dispatch wait ------>|
   |                                     |                         tStart ->| call()
   |                                     |                                 |  work...
   |                                     |                         tEnd   ->| finish
   | <------------------------- Future/result -----------------------------|
```

Đo bằng **cùng một đồng hồ monotonic**:

```text
submitToStartNanos = tStart - tSubmit
runNanos           = tEnd   - tStart
totalNanos         = tEnd   - tSubmit

totalNanos == submitToStartNanos + runNanos
```

- `tSubmit`: thời điểm caller chuẩn bị gửi task, ngay trước `execute/submit`.
- `tStart`: dòng đầu được thực thi trong task wrapper của worker.
- `tEnd`: task kết thúc phần công việc được đo.

**Tên chính xác:** `submitToStart` là khoảng **từ khi chuẩn bị submit đến khi bắt đầu chạy**. Nó thường gần với thời gian chờ executor queue, nhưng còn có chi phí admission, tạo worker, dispatch và scheduling. Nếu cần chính xác thời gian *nằm bên trong queue*, phải instrument tại thời điểm enqueue/dequeue hoặc custom queue/executor. Bài này dùng `submitToStart` như chỉ báo thực tiễn, không tuyên bố nó chỉ gồm queue residence.

**`runNanos` là thời gian elapsed, không phải thời gian CPU tiêu thụ.** Một worker đã nhận task nhưng đang `Thread.sleep`, chờ DB/socket, lock, semaphore hoặc filesystem vẫn bị chiếm cho đến khi task kết thúc. Phân loại phần **chờ bên trong task** khác với **chờ trước khi task có worker**.

### 2.1. `Future.get()` không phải queue wait

Một lời gọi `future.get()` chờ 500 ms có thể bao gồm:

- Task còn trong queue.
- Task đã bắt đầu và đang làm việc.
- Worker bị chờ network/DB bên trong task.
- Scheduling và thời điểm caller thực sự bắt đầu chờ.

Vì vậy không được lấy thời gian `Future.get()` rồi gán nhãn `queueWaitMs`. Ngoài ra `Future.get(timeout)` hết giờ chỉ khiến caller thôi chờ; task **không tự động bị hủy**. Nếu cần hủy phải xét `cancel`, interrupt và cách đóng resource theo contract của ứng dụng.

### 2.2. End-to-end request còn nhiều pha

```text
request arrival
   -> ingress queue
   -> parse/auth
   -> pool admission / submit
   -> submit-to-start
   -> task run (CPU + I/O + locks + business logic)
   -> result-handling / serialization
   -> response sent
```

Tổng latency từ client có thể lớn hơn cả `submitToStart + run`, và một số phần có thể chạy chồng nhau khi async. Không cộng các số đo **có ranh giới trùng lặp** rồi gọi là tổng request latency. Luôn ghi điểm bắt đầu/kết thúc mà metric thực sự bao phủ.

### 2.3. Task chưa từng chạy

| Trạng thái | Có `tStart`/`tEnd` không? | Cách ghi nhận |
| --- | --- | --- |
| Accepted và completed | Có | `submitToStart`, `run`, `total`, outcome |
| Accepted rồi failed trong `run` | Có | Đo bằng `finally` và ghi `FAILED` |
| Rejected vì full hoặc shutdown | **Không** | Rejection count, reason và thời gian phản hồi submit riêng |
| Cancelled khi vẫn queued | Chưa có `tStart` | Cancellation/expiration metrics riêng, không ép `run=0` vào latency histogram thành công |
| CallerRunsPolicy chạy trên caller | Có start/end nhưng **không chạy ở pool worker** | Ghi execution location, caller latency và backpressure riêng |

## 3. Cách `ThreadPoolExecutor` quyết định queue và số worker

`ThreadPoolExecutor` phối hợp ba giới hạn:

- **`corePoolSize`:** số core workers mục tiêu.
- **`maximumPoolSize`:** trần workers có thể dùng khi queue không nhận thêm task.
- **`workQueue`:** giữ những task đã accept nhưng **chưa được worker lấy ra**.

Quy tắc quan trọng của HotSpot/JDK `ThreadPoolExecutor`:

1. Nếu số worker hiện chạy còn ít hơn core, executor thường ưu tiên **tạo worker**.
2. Khi đã có đủ core workers, executor thường ưu tiên **đưa task vào queue** thay vì lập tức mở rộng tới max.
3. Nếu queue không nhận task, executor mới thử tạo thêm worker tới `maximumPoolSize`.
4. Nếu max workers đã chạm trần và queue không nhận thêm, task được xử lý bởi `RejectedExecutionHandler`.
5. Executor đã shutdown cũng có thể từ chối task; **rejection không mặc định đồng nghĩa saturation**.

**Lab chọn cấu hình:**

```text
corePoolSize = 1
maximumPoolSize = 1
queue capacity = 1
handler = AbortPolicy

Task A -> worker #1 (đang chạy/chờ latch)
Task B -> workQueue[0] (đang chờ worker #1)
Task C -> không còn slot hoặc worker -> REJECTED
```

Ở thời điểm giữ ổn định: `active workers≈1`, `queue.size()=1`, tổng số task **đã được chấp nhận và chưa hoàn tất** là 2. Queue depth **không** phải 2 vì task A đang chạy đã ra khỏi queue.

### 3.1. Bounded queue và unbounded queue

- `new ArrayBlockingQueue<>(1)` tạo queue có **một vị trí rõ ràng**; khi đầy có thể tạo thêm worker nếu max>core, hoặc reject theo policy.
- `Executors.newFixedThreadPool(n)` thường sử dụng **unbounded LinkedBlockingQueue**. Khi core threads bận, task mới có thể cứ được queue. Kết quả là tail latency và memory tăng mà không thấy reject ngay. Với queue unbounded, `maximumPoolSize` thường không phát huy vai trò vượt core vì queue không báo đầy.
- `Executors.newCachedThreadPool()` có chiến lược mở rộng threads khác, không phải backpressure bounded mặc định.
- `Executors.newVirtualThreadPerTaskExecutor()` trên JDK 21+ không đặt giới hạn business concurrency chỉ bằng việc virtual threads rẻ hơn platform threads. Database connections, remote API limits, buffers và memory vẫn hữu hạn; có thể dùng semaphore/bulkhead/timeout phù hợp.

Một pool lớn hơn chưa chắc nhanh hơn. Nếu 200 workers cùng chờ 10 connection DB thì áp lực nhớ, context-switch và downstream contention có thể **tệ hơn**. Cần đo nguyên nhân occupied time.

## 4. Lab độc lập Java 17+: một running, một queued, một rejected

Chương trình sau hoàn toàn tự chạy bằng JDK, không cần server, DB, network hay thư viện ngoài:

- `ThreadPoolExecutor(1, 1, ..., ArrayBlockingQueue<>(1), AbortPolicy)`.
- Task `first` chiếm worker và chờ `CountDownLatch`.
- Main chờ `first` bắt đầu rồi submit task `queued`.
- Main xác nhận queue đã đầy, thử task thứ ba để nhận `RejectedExecutionException`.
- Main **giữ task đầu thêm 250 ms**, sau đó release worker; task thứ hai chỉ làm việc khoảng 40 ms.
- Hai task đầu được đo bằng cùng đồng hồ monotonic `System.nanoTime()`.

### 4.1. Tạo file `PoolQueueTimingLab.java`

```java
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class PoolQueueTimingLab {
    record Sample(String name, long submittedAt, long startedAt, long endedAt) {
        long submitToStartNanos() { return startedAt - submittedAt; }
        long runNanos() { return endedAt - startedAt; }
        long totalNanos() { return endedAt - submittedAt; }
    }

    static Callable<Sample> measured(
            String name, long submittedAt, Callable<Void> work) {
        return () -> {
            long startedAt = System.nanoTime();
            work.call();
            return new Sample(name, submittedAt, startedAt, System.nanoTime());
        };
    }

    static void show(Sample sample) {
        System.out.printf(Locale.ROOT,
            "%s submitToStartMs=%.2f runMs=%.2f totalMs=%.2f%n",
            sample.name(),
            sample.submitToStartNanos() / 1_000_000.0,
            sample.runNanos() / 1_000_000.0,
            sample.totalNanos() / 1_000_000.0);
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException, TimeoutException {
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(1),
            new ThreadPoolExecutor.AbortPolicy());
        try {
            Future<Sample> first = pool.submit(measured(
                "first", System.nanoTime(), () -> {
                    firstStarted.countDown();
                    releaseFirst.await();
                    return null;
                }));

            if (!firstStarted.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not start");
            }

            Future<Sample> queued = pool.submit(measured(
                "queued", System.nanoTime(), () -> {
                    Thread.sleep(40);
                    return null;
                }));

            boolean saturated = pool.getActiveCount() == 1
                && pool.getQueue().size() == 1
                && pool.getQueue().remainingCapacity() == 0;

            boolean thirdRejected = false;
            try {
                pool.execute(() -> {});
            } catch (RejectedExecutionException expected) {
                thirdRejected = true;
            }

            // Keep the one worker occupied while the second task waits.
            Thread.sleep(250);
            releaseFirst.countDown();

            Sample a = first.get(3, TimeUnit.SECONDS);
            Sample b = queued.get(3, TimeUnit.SECONDS);

            System.out.println("saturated=" + saturated);
            System.out.println("thirdRejected=" + thirdRejected);
            System.out.println("completed=2");
            System.out.println("queuedStartedAfterFirstEnded=" +
                (b.startedAt() >= a.endedAt()));
            System.out.println("queuedWaitPositive=" +
                (b.submitToStartNanos() > 0));
            System.out.println("latencyIdentity=" +
                (b.totalNanos() == b.submitToStartNanos() + b.runNanos()));
            show(a);
            show(b);
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("pool did not terminate");
            }
        }
    }
}
```

**Giới hạn của lab:** `measured(...)` ở đây tạo `Sample` sau một task **thành công**. Vì cả hai task demo đều hoàn tất bình thường, nó cho số liệu đúng. Với code production, muốn giữ metrics khi task ném exception cần ghi trong `finally`; trình bày ở mục 6. Dòng `completed=2` nằm sau **hai `Future.get()` đã thành công**, mô tả số tác vụ của kịch bản, không phải `ThreadPoolExecutor.getCompletedTaskCount()` được đọc trực tiếp.

### 4.2. Biên dịch và chạy

```bash
javac PoolQueueTimingLab.java
java PoolQueueTimingLab
```

Đã kiểm tra bằng `javac --release 17` và chạy nhiều lần trên OpenJDK 24. Sáu dòng đầu là những kiểm tra logic đã được xác nhận trên môi trường thử nghiệm:

```text
saturated=true
thirdRejected=true
completed=2
queuedStartedAfterFirstEnded=true
queuedWaitPositive=true
latencyIdentity=true
```

Hai dòng sau **thay đổi số đo** theo máy, thời điểm và tải. Ví dụ một lần chạy thực tế:

```text
first submitToStartMs=6.82 runMs=253.72 totalMs=260.54
queued submitToStartMs=253.93 runMs=40.44 totalMs=294.37
```

Đây là **output minh họa từ một lần chạy**, không phải giá trị cố định. Nhận định có giá trị: `queued` đã **chờ ~254 ms trước khi được chạy** nhưng **chỉ xử lý ~40 ms**. Nếu chỉ nhìn `runMs`, chúng ta sẽ bỏ sót phần lớn tail latency.

### 4.3. Tại sao latch làm phép thử ổn định?

`firstStarted.await(3, SECONDS)` bảo đảm task thứ nhất thực sự vào worker trước khi submit task thứ hai. Khi worker đang đợi `releaseFirst`, task thứ hai phải nằm trong queue, vì pool không thể có worker thứ hai. Hàng đợi capacity 1 đã đầy thì task thứ ba bị `AbortPolicy` reject.

Không nên dùng `Thread.sleep(100)` đơn thuần để *hy vọng* worker thứ nhất bắt đầu trước task thứ hai; đó là race dễ làm kết quả khác nhau ở máy chậm/CI. `CountDownLatch` tạo một ranh giới đồng bộ có thể lặp lại. Lệnh `Thread.sleep(250)` sau bước xác nhận chỉ để **giữ thời gian chờ đủ dài cho việc đo**, không phải để quyết định logic đúng/sai của trình tự task.

`getActiveCount()` là **ước lượng**, `getQueue().size()` là ảnh chụp tại thời điểm gọi. Chúng chỉ đủ ổn định trong lab vì latch giữ worker. Trong hệ thống đang chạy thật, worker có thể hoàn tất giữa lúc bạn đọc gauge và lúc submit task khác; không xây chính sách admission bằng `if (queue.size()<capacity) submit(...)` vì có race.

### 4.4. Diễn giải số liệu đúng đơn vị

Với task `queued` trong mẫu:

```text
tSubmit -> tStart = 253.93 ms  (chờ được thực thi)
tStart  -> tEnd   =  40.44 ms  (task đang chạy)
tSubmit -> tEnd   = 294.37 ms  (task latency tổng)
```

Trên nanoseconds, `total = submitToStart + run` đúng theo đại số. Khi hiển thị hai chữ số thập phân, đôi khi tổng các số đã làm tròn có sai khác ~0,01 ms; **không** kết luận mất thời gian hoặc sai clock chỉ vì rounding.

Lưu ý `first` có `runMs≈254 ms` nhưng phần lớn đang **đợi latch**, không chạy CPU. Từ góc nhìn pool, nó vẫn chiếm một worker và ngăn task `queued` tiến triển.

## 5. Đọc đúng runtime metrics của `ThreadPoolExecutor`

| API | Giá trị trả về | Không nên suy ra |
| --- | --- | --- |
| `getCorePoolSize()` | Core worker configuration | Số thread thực đang bận |
| `getMaximumPoolSize()` | Max worker configuration | Pool luôn tự mở rộng tới max khi core bận |
| `getPoolSize()` | Số worker threads hiện có | Active workers hoặc task throughput |
| `getActiveCount()` | **Ước lượng** threads đang thực thi task | CPU busy % hoặc số request hoàn tất |
| `getQueue().size()` | Tasks đang đợi trong queue lúc quan sát | Tasks đang chạy hoặc queue đã từng chờ bao lâu |
| `getQueue().remainingCapacity()` | Chỗ trống tức thời | Submit tiếp theo chắc chắn được accepted |
| `getLargestPoolSize()` | Số worker đồng thời lớn nhất từng có | Latency hiện tại |
| `getTaskCount()` | **Ước lượng** tasks đã được lên lịch | Rejected count hay task success rate |
| `getCompletedTaskCount()` | **Ước lượng** tasks đã hoàn tất | Kết quả nghiệp vụ hoặc số tasks chính xác trên mọi snapshot |

**Queue depth có thể đang bằng 0 mà p99 wait vẫn cao.** Ví dụ task đã chờ 10 giây, sau đó vừa được worker lấy ra và queue trống. Snapshot 1 phút/lần sẽ không thấy backlog trong quá khứ; `submitToStart` được ghi **trên từng task** vẫn cho biết mức chờ dài. Do đó hãy dùng cả `queue.depth`, `oldestQueuedAge` (nếu có) và histogram delay, không chỉ gauge queue depth.

Các pool có chức năng khác nhau phải được gắn tên ổn định; không trộn metric của request pool, DB connection pool, message consumer pool và scheduler. Nên gắn `poolName`, `taskType`, `outcome` từ tập giá trị **hữu hạn**, không gắn request ID làm time-series label.

## 6. Instrument hai pha trong ứng dụng thật

### 6.1. Điểm đo tối thiểu

```text
tSubmitted = System.nanoTime()       // ngay trước execute/submit
tStarted   = System.nanoTime()       // đầu wrapper trong worker
... phần công việc được instrument ...
tFinished  = System.nanoTime()       // finally

submitToStart = tStarted - tSubmitted
execution     = tFinished - tStarted
total         = tFinished - tSubmitted
```

Sử dụng `System.nanoTime()` để đo **duration** vì nó phục vụ tính thời gian trôi qua trong cùng process; `System.currentTimeMillis()` là wall clock có thể bị điều chỉnh bởi NTP/clock changes. Nếu muốn đối chiếu timeline với JFR/logs, ghi thêm wall-clock timestamp **riêng**, không trộn nó vào phép trừ latency.

Đặt `tSubmitted` gần nơi gọi `execute/submit`. Nếu caller đã chờ admission semaphore hoặc chờ HTTP request queue trước đó thì thời gian này **nằm ngoài** submit-to-start, cần metric riêng. Đặt `tStarted` tại đầu task wrapper, `tFinished` trong `finally` cho cả success/failure. Với async continuation, xác định rõ task nào được đo; không tự gọi submit-to-start là end-to-end user request latency.

### 6.2. Snippet minh họa có `finally`

Đây là **mảnh code cần các biến/phụ thuộc** `executor`, `metrics`, `performBusinessOperation()` do ứng dụng định nghĩa; không phải chương trình độc lập:

```java
long submittedAt = System.nanoTime();

try {
    executor.execute(() -> {
        long startedAt = System.nanoTime();
        String outcome = "SUCCESS";
        try {
            performBusinessOperation();
        } catch (RuntimeException failure) {
            outcome = "FAILED";
            throw failure;
        } finally {
            long finishedAt = System.nanoTime();
            metrics.recordSubmitToStart(startedAt - submittedAt);
            metrics.recordRun(finishedAt - startedAt, outcome);
        }
    });
} catch (RejectedExecutionException rejection) {
    metrics.incrementRejected("submission_rejected");
    throw rejection;
}
```

Điểm cốt lõi: task đã nhận nhưng **failed khi chạy** vẫn phải có duration; task bị **rejected trước khi chạy** chỉ được quan sát ở submit site. `RejectedExecutionException` còn có thể xảy ra khi executor đã shutdown, không được tự đặt reason `"saturated"` nếu chưa kiểm tra runtime lifecycle. Một metric callback trong `finally` có thể ném exception và che lỗi gốc nếu tự triển khai không cẩn thận; dùng metrics library an toàn, không blocking và không làm side effect nghiệp vụ.

Nếu cần bao cả `Error`, checked exception, interrupt và cancellation, dùng wrapper/outcome mapping bao quát hơn, bảo vệ ngoại lệ gốc. Nếu dùng `ExecutorService.submit()`, task thường được bọc trong `FutureTask`; `afterExecute(Runnable, Throwable)` có thể nhận `Throwable=null` dù `Future.get()` sau đó thấy `ExecutionException`. Không đếm failure chỉ bằng đối số `Throwable` của `afterExecute` khi chưa hiểu cách submit/wrapping.

### 6.3. Vẫn phải phân biệt worker time và CPU time

Một task đã bắt đầu có thể có:

```text
submit-to-start =   3 ms
run             = 900 ms
  CPU           =  10 ms
  wait DB       = 880 ms
  serialization =  10 ms
```

Ở đây `run` cao do worker bị chiếm bởi **I/O wait**, không phải queue. Tăng worker có thể làm số task chờ DB tăng lên; cần metric pool acquire, DB query latency, socket timeout, lock/park và CPU profiling.

Ngược lại:

```text
submit-to-start = 850 ms
run             =  40 ms
```

báo hiệu phần chờ trước worker là thành phần chủ đạo. Tuy nhiên bão hòa có thể do **arrival spike** hoặc do **những task khác** chạy lâu; hãy đo đầy đủ các taskType, không chỉ task đang được báo lỗi.

## 7. Quan sát bão hòa bằng metrics, thread dumps và JFR

### 7.1. Bộ metrics tối thiểu

| Metric | Loại | Dùng để |
| --- | --- | --- |
| `executor.active` | Gauge | Số worker đang chạy task, gần đúng |
| `executor.pool.size` | Gauge | Số worker tồn tại |
| `executor.queue.depth` | Gauge | Backlog hiện tại |
| `executor.queue.capacity` | Gauge/config | Giới hạn thực tế |
| `executor.submitted` | Counter | Số lần ứng dụng cố gắng nộp |
| `executor.accepted` | Counter | Số task được chấp nhận theo policy |
| `executor.rejected` | Counter | Số lần reject; phân loại shutdown/overload nếu xác minh được |
| `executor.submit_to_start` | Histogram/Timer | p50/p95/p99 chờ trước khi bắt đầu |
| `executor.run` | Histogram/Timer | p50/p95/p99 trong worker, cả success/failure theo semantics rõ |
| `executor.total` | Histogram/Timer | Độ trễ submit-to-end của task |
| `executor.oldest_queued_age` | Gauge khi đo được | Task chờ lâu nhất, hữu ích khi queue tăng |
| `request.end_to_end` | Histogram/Timer | Latency người dùng thấy, gồm cả các pha ngoài pool |

**Không** suy success rate nghiệp vụ từ `getCompletedTaskCount`: hoàn thành `FutureTask` có thể bao task đã thất bại. Rejection cần capture ở submit path; với `CallerRunsPolicy`, handler có thể chạy task ngay trong caller và không ném exception, nên thiết kế metrics theo execution location/outcome.

Không đặt `taskId`, `correlationId`, email hoặc URL chứa query trong metric labels vì cardinality cao. Giữ correlation code opaque trong logs/tracing/JFR có retention và quyền phù hợp.

### 7.2. Thread dump không hiển thị stack của task còn trong queue

Khi JVM còn chạy và có quyền attach:

```bash
jcmd <PID> Thread.print -l > thread-t0.txt
sleep 5
jcmd <PID> Thread.print -l > thread-t1.txt
```

Thay `<PID>` bằng PID thật, ghi timestamp capture và hiểu chi phí của dump. Thread dump phản ánh **worker đã được task chiếm**, gồm các frame I/O, lock, park hoặc business code. Một `Runnable`/`Callable` đang **ngồi trong `ArrayBlockingQueue` chưa có worker riêng**, vì vậy nó **không có stack trace thực thi riêng** trong thread dump.

Trong lab, worker đầu đang chờ `CountDownLatch.await()`; task thứ hai chưa chạy và không có stack riêng. Trạng thái `WAITING` của worker giải thích **tại sao worker không rảnh**, còn queue metric giải thích **task thứ hai đang đợi**. Không gộp hai điều thành “task thứ hai bị blocked trong code của nó”.

**`RUNNABLE` không đồng nghĩa CPU 100%**; worker có thể đang chờ OS I/O. Khi active=max nhưng CPU thấp, kiểm tra thread dumps, network/DB latencies, native calls và các lock events.

### 7.3. JFR hỗ trợ điều tra run time

JFR có các event như `jdk.ThreadPark`, `jdk.JavaMonitorEnter`, socket/file I/O, CPU sampling, GC pauses, allocation — tùy phiên bản và settings. Chúng giúp tìm nguyên nhân **worker đã bắt đầu nhưng vẫn chiếm lâu**. JFR mặc định **không biết** trường business `task X đã chờ trong executor queue Y bao nhiêu ms`; muốn biết phải instrument submit/start hoặc custom event trong ứng dụng.

Có thể tạo custom JFR event chứa `poolName`, `taskType`, `submitToStartNanos`, `runNanos` và `outcome`, với String labels có giới hạn. Không ghi request body, token hoặc correlation ID không được phép; nên giảm event rate/thêm threshold khi production load lớn.

Ví dụ lệnh JFR khi JVM còn sống và có quyền attach:

```bash
jcmd <PID> JFR.start name=pool-diagnostics settings=profile duration=2m filename=pool.jfr
jcmd <PID> JFR.check name=pool-diagnostics
jfr summary pool.jfr
jfr print --events jdk.ThreadPark,jdk.JavaMonitorEnter pool.jfr
```

File `pool.jfr` chỉ có sau khi recording đã hoàn tất/dump. Nếu cần snapshot trong khi recording vẫn chạy:

```bash
jcmd <PID> JFR.dump name=pool-diagnostics filename=pool-now.jfr
```

JFR threshold/sampling có thể khiến một sự kiện không xuất hiện. **Vắng event** không chứng minh rằng task không hề chờ. Dùng JDK Mission Control (JMC) để đối chiếu timeline khi cần.

## 8. Chính sách từ chối và backpressure

| Handler | Khi pool đầy | Tác dụng phụ |
| --- | --- | --- |
| `ThreadPoolExecutor.AbortPolicy` | Ném `RejectedExecutionException` | Caller phải xử lý lỗi có kiểm soát; dễ theo dõi overload |
| `CallerRunsPolicy` | Chạy task trong **caller thread** khi executor chưa shutdown | Giảm tốc producer nhưng có thể làm ingress thread bận lâu |
| `DiscardPolicy` | Bỏ task **im lặng** | Có thể mất công việc; đặc biệt nguy hiểm nếu caller giữ `Future` chờ mãi |
| `DiscardOldestPolicy` | Bỏ một task cũ ở queue và thử submit lại | Làm mất task, thay đổi fairness/ordering; không phù hợp việc quan trọng nếu không có hợp đồng bù trừ |

Khi dùng `ExecutorService.submit()` với handler discard, task có thể bị loại dù caller đã nhận một `Future`, khiến chờ kết quả không có hồi kết phù hợp. Với công việc yêu cầu durability/acknowledgment, dùng durable queue hoặc messaging với delivery, idempotency, retry và deadline được thiết kế rõ, **không** xem in-memory `ThreadPoolExecutor` như sổ cái giao dịch.

Các lựa chọn giảm tải thực tế:

- **Bounded admission:** giới hạn số task được nhận; trả overload rõ ràng (ví dụ HTTP 429/503 khi đúng hợp đồng).
- **CallerRunsPolicy có chủ đích:** có thể giảm tốc nguồn submit, nhưng không áp dụng mù cho event-loop, request acceptor hoặc thread nhạy với latency.
- **Bulkhead/semaphore:** hạn chế đồng thời đến downstream độc lập với thread pool.
- **Deadline/timeout:** tránh tasks không còn hữu ích tiếp tục chờ hàng phút; nhưng cancellation phải phù hợp API, không chỉ `Future.get(timeout)`.
- **Circuit breaker và rate limiting:** giảm tải downstream đang lỗi.
- **Retry có giới hạn và backoff:** không vòng lặp retry tức thì khi `RejectedExecutionException` vì nó làm overload trầm trọng hơn.
- **Scale có kiểm chứng:** CPU-bound jobs cần xem CPU budget/GC, I/O-bound jobs cần xem connection limits/buffers, không chỉ số threads.

**Đừng chọn queue rất lớn chỉ để tránh rejection.** Queue lớn có thể làm backlog vô hình và hầu hết requests hết SLO trước khi tới worker; tăng queue chỉ giúp **đệm burst**, không làm tăng throughput nền của service.

## 9. Ma trận chẩn đoán wait time và run time

| Dấu hiệu | Giả thuyết cần kiểm tra | Bằng chứng bổ sung | Hướng xử lý |
| --- | --- | --- | --- |
| Submit-to-start p99 cao, run p99 vẫn thấp/ổn định, queue tăng | Arrival vượt service capacity hoặc burst dài | Tasks/s, active, rejected, queue age, core/max | Bounded load, tối ưu admission, scale/concurrency có căn cứ |
| Run p99 cao, submit-to-start cũng tăng | Workers bị giữ lâu do I/O, lock, downstream hoặc CPU | Thread dumps, JFR parks/socket, DB wait, CPU profile | Giảm blocking, sửa downstream, timeout/bulkhead |
| Run p99 cao nhưng queue thấp | Task nội tại chậm, chưa có backlog lớn | TaskType breakdown, GC, I/O, CPU | Tối ưu phần run, không tập trung queue |
| Queue depth hiện bằng 0 nhưng wait p99 cao | Gauge sampling bỏ lỡ burst quá khứ | Histograms per-task, event timeline | Đo submit→start và oldest queued age |
| Rejection tăng, queue full và active≈max | Bão hòa admission thật | Policy, traffic burst, max/queue config | Backpressure hoặc capacity tuning |
| Rejection tăng nhưng queue=0 và active≈0 | Pool shutdown, lifecycle/race | `isShutdown`, restart logs | Sửa lifecycle chứ không tăng workers |
| CPU thấp, active=max, queue cao | Workers chờ DB/network/lock | Thread dump, JFR, dependency metrics | Sửa phần chờ trong run |
| CPU cao, active=max, queue cao | CPU-bound load, GC pressure | CPU profiler, GC, allocation, throughput | Tối ưu compute hoặc scale phù hợp |
| CallerRunsPolicy và ingress latency tăng | Caller đang thực thi task bị overflow | Caller thread stacks, admission rate | Điều chỉnh overload response/policy |
| Không reject nhưng queue latency tăng không ngừng | Unbounded queue đang tích backlog | Queue length, oldest age, heap pressure | Đưa giới hạn/backpressure, giảm arrival |

Một pool bão hòa là **triệu chứng về capacity**, không phải kết luận nguyên nhân gốc. Nó có thể bắt nguồn từ peak arrival, threads chờ DB, lock contention, GC pause, task hang hoặc deployment giảm pool size. Cần kết hợp wait/run histograms với trạng thái workers và dependency metrics.

## 10. Ước lượng tải, tránh lạm dụng công thức

Ký hiệu:

- `λ`: số task vào mỗi giây (arrival rate).
- `E[S]`: thời gian trung bình task chiếm worker (execution/occupied time).
- `c`: số workers có thể thực thi đồng thời.

Năng lực xử lý lý tưởng có thể ước lượng thô khoảng **`c / E[S]` tasks/s** nếu các tasks đủ độc lập và không có bottleneck khác. Trong thực tế cần tính contention, I/O, biến thiên service time, GC và CPU budget. Nếu arrival rate **duy trì** cao hơn throughput thực tế, backlog tích tụ và queue bounded cuối cùng reject/backpressure.

**Ví dụ:** 4 workers, task chiếm worker trung bình 100 ms thì capacity lý tưởng khoảng 40 tasks/s. Nếu arrival duy trì 60 tasks/s mà execution không giảm, queue có xu hướng tăng; nới queue làm **chậm xảy ra rejection**, không tăng năng lực xử lý.

Định luật Little **`L = λ × W`** dùng cho hệ thống ổn định với ranh giới đo đồng nhất và các giá trị trung bình dài hạn. Không áp thẳng vào một burst 250 ms trong lab rồi coi nó là bảo đảm p99. Với production, xem distributions (p50/p95/p99), task mix, periods of saturation, SLO và dependency headroom.

## 11. Thực hành mở rộng

### A. Thử `CallerRunsPolicy`

Thay handler cuối trong constructor bằng:

```java
new ThreadPoolExecutor.CallerRunsPolicy()
```

Giữ `core=1, max=1, queue=1`. Task thứ ba có thể chạy **ngay trên main/caller** thay vì bị reject; assertion `thirdRejected=true` của lab gốc **không còn đúng**. Đo thời gian caller bị chiếm và so với throughput submit. Trình bày lợi ích backpressure và rủi ro giữ HTTP/event-loop thread.

### B. Thêm worker

Thử `core=2, max=2, queue capacity=1`. Giữ **cả hai** workers bằng latches, thêm task queued rồi submit task kế để thấy rejection. Không chỉ đổi số workers mà giữ một latch rồi giả định trạng thái giống lab gốc; khi hai workers rảnh, trình tự admission sẽ khác.

### C. Queue unbounded nhưng số task hữu hạn

Dùng:

```java
ExecutorService pool = Executors.newFixedThreadPool(1);
```

Submit hữu hạn 20 tasks, mỗi task xử lý ~40 ms, instrument `submitToStart`. Quan sát task nộp sau có delay tăng dù không bị reject. Không dùng vòng lặp vô hạn làm đầy heap chỉ để minh họa.

### D. Task thất bại và bị hủy

Tạo một task ném `IllegalStateException`, một task được cancel khi còn queued. Cập nhật wrapper ghi run/outcome trong `finally`, không che exception gốc, đếm rejection/cancellation riêng. Không đưa tasks chưa bao giờ bắt đầu vào histogram runtime thành công.

### E. Caller timeout

Thử `future.get(50, TimeUnit.MILLISECONDS)` khi task đang queued. Sau `TimeoutException`, kiểm tra nó có thể vẫn ở queue/đang chạy. Nếu gọi `cancel(true)`, xác minh task có hỗ trợ interruption và cleanup hay không. Giải thích **caller wait budget** khác queue wait đo bằng tSubmit/tStart.

### F. Thread dump và JFR

Giữ worker lâu hơn trong một thử nghiệm riêng, chụp `jcmd Thread.print -l` khi pool đầy. Xác định stack của **task A trong worker**, và giải thích vì sao không thể tìm một Java stack riêng của **task B còn queued**. Nếu tự tạo JFR event, đo submit-to-start/run theo taskType với data giới hạn, so timeline với JFR ThreadPark/I/O events.

## 12. Những nhầm lẫn thường gặp

1. **“Task accepted là task đã chạy.”** Sai: nó có thể nằm trong queue.
2. **“40 ms trong `run()` là 40 ms request latency.”** Sai: còn queue, ingress và response processing.
3. **“Thời gian `Future.get()` chính là queue wait.”** Sai: nó có thể chứa run time và scheduling.
4. **“Queue depth=0 nên không từng backlog.”** Sai: snapshot sau burst không phản ánh lịch sử.
5. **“`getActiveCount()=max` nghĩa CPU 100%.”** Sai: workers có thể chờ I/O/lock.
6. **“`maxPoolSize` lớn thì executor mở ngay khi core bận.”** Sai: thường **queue trước**, chỉ vượt core khi queue không nhận thêm.
7. **“Unbounded queue chống overload.”** Sai: nó có thể che rejection nhưng tăng heap và tail latency.
8. **“`CallerRunsPolicy` vẫn dùng worker.”** Sai: nó có thể chạy ở caller.
9. **“`DiscardPolicy` giống trả lỗi rõ ràng.”** Sai: task có thể biến mất không báo.
10. **“Không rejection nghĩa tất cả requests đạt SLO.”** Sai: chúng có thể timeout trước khi bắt đầu chạy.
11. **“`Future.get(timeout)` đã hủy task.”** Sai: hết giờ của caller không mặc định cancel.
12. **“`shutdownNow()` bảo đảm mọi worker dừng tức thì.”** Sai: nó cố interrupt và trả tasks chưa chạy; task bỏ qua interrupt có thể tiếp tục.
13. **“`afterExecute(Throwable)` luôn thấy mọi lỗi của `submit()`.”** Sai: `FutureTask` có thể giữ exception.
14. **“`currentTimeMillis` là đồng hồ duration ổn định.”** Sai: dùng `nanoTime`.
15. **“Tăng pool sẽ sửa DB pool đang cạn.”** Sai: chỉ thêm workers chờ DB nếu không mở thêm capacity thật.
16. **“Virtual threads làm concurrency vô hạn an toàn.”** Sai: downstream capacity vẫn hữu hạn.
17. **“`submitToStart + run` luôn bằng HTTP latency.”** Sai: còn các pha ngoài executor.
18. **“Một lần lab đã đủ chọn pool size production.”** Sai: cần tải đại diện, tail latency, memory, CPU và SLO.

## 13. Checklist chẩn đoán và tiêu chí bài thực hành

- [ ] Lab tạo đúng **1 running + 1 queued + 1 rejected** ở `core=max=1`, queue capacity 1.
- [ ] Có `tSubmit`, `tStart`, `tEnd` từ **cùng `System.nanoTime()`**, tính đúng các duration trên nanoseconds.
- [ ] Chứng minh task `queued` có wait đáng kể trong khi run ngắn; hiểu `submitToStart` bao cả dispatch.
- [ ] Không tính rejected, cancelled-before-start vào latency histogram của tasks đã chạy.
- [ ] Biết `runNanos` là occupied wall time, không phải CPU time.
- [ ] Có queue depth, active count, rejection rate, submit-to-start và run histograms với scopes rõ.
- [ ] Xác minh shutdown vs overload khi có `RejectedExecutionException`.
- [ ] Dùng thread dump/JFR để tìm **vì sao workers bị chiếm**, không tìm stack cho queued task chưa chạy.
- [ ] Tách timeout của caller, queue delay, task runtime và request end-to-end.
- [ ] Chọn bounded concurrency, backpressure/retry/deadline phù hợp; không tăng pool/queue mù quáng.
- [ ] Kiểm chứng thay đổi ở tải tương đương bằng throughput, rejection, p95/p99 và resource budget.

**Kết luận:** Một task có thể **chạy nhanh nhưng bắt đầu rất muộn** khi pool bão hòa. Tách `submit→start` khỏi `start→finish` biến hiện tượng “API chậm” thành dữ kiện rõ ràng: đang **đợi worker** hay **chậm sau khi worker bắt đầu**. Kết hợp số đo từng task với trạng thái hàng đợi, chính sách reject và nguyên nhân blocking bên trong workers để chọn giải pháp đúng.

## Tài liệu tham khảo

- [Oracle JDK 21 — ThreadPoolExecutor: core/max, work queues và RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Oracle JDK 21 — ArrayBlockingQueue: capacity và remainingCapacity](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [Oracle JDK 21 — ExecutorService: submit/shutdown](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle JDK 21 — Future: get(timeout), cancellation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Oracle JDK 21 — System.nanoTime đo thời gian elapsed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime())
- [Oracle JDK 21 — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Oracle JDK 21 — jcmd: Thread.print và JFR](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
