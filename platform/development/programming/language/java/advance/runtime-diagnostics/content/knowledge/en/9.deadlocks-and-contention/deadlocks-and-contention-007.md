# 9.7 Đối chiếu số tác vụ đang chạy, đã hoàn thành, bị từ chối và độ dài hàng đợi

Khi một ứng dụng Java có dấu hiệu **treo, timeout, backlog tăng hoặc từ chối công việc**, thread dump cho biết các worker hiện đang ở stack nào, nhưng không cho biết đầy đủ số task **chưa đến lượt worker**, đã hoàn tất, hoặc đã bị từ chối ngay tại điểm submit. Có thể JVM chỉ có tám worker, cả tám đều chờ database, trong khi vài nghìn task đang xếp hàng. Nếu chỉ xem CPU và các thread ở trạng thái RUNNABLE, rất dễ bỏ sót nguồn nghẽn.

Trong Java 21, **ThreadPoolExecutor** cung cấp ba nhóm thông tin quan sát trực tiếp: **worker đang thực thi**, **task đã hoàn thành** và **work queue hiện tại**. Riêng số lần bị từ chối **không có getter chuẩn**; ứng dụng hoặc framework phải instrument tại **RejectedExecutionHandler** hoặc submission boundary. Điều cần làm là **đối chiếu số liệu theo cùng executor, cùng tiến trình và cùng cửa sổ thời gian**, sau đó kiểm chứng bằng thread dumps, JFR, request traces và downstream metrics.

Bốn khái niệm chính:

- **Active/running:** số worker đang thực thi một task. Task đó có thể chờ khóa, network hoặc Future; **active không đồng nghĩa CPU đang bận**.
- **Completed:** số task đã kết thúc execution trong worker của pool kể từ khi pool được tạo; **completed không đồng nghĩa nghiệp vụ thành công**.
- **Rejected:** sự kiện một submission không được executor tiếp nhận theo cơ chế rejection. Handler có thể **throw, chạy ở caller hoặc bỏ task**; callback không luôn bằng số request mất.
- **Queued:** số task nằm trong work queue nhưng chưa được worker lấy ra. Nó khác **upstream backlog**, số task active hoặc thời gian chờ.

Bài này nằm trong nhóm **9. Treo và tranh chấp** của module **Java Advance - runtime-diagnostics**. Các ví dụ theo **Java SE 21**, tập trung vào **ThreadPoolExecutor**; một số framework, ForkJoinPool, ScheduledThreadPoolExecutor và virtual-thread-per-task executor có ngữ nghĩa khác, cần đối chiếu riêng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đọc **getActiveCount(), getCompletedTaskCount(), getTaskCount(), getPoolSize(), getMaximumPoolSize()** và **getQueue().size()**.
2. Phân biệt **gauge**, **counter tích lũy**, **delta/rate** và snapshot không đồng thời.
3. Biết vì sao chỉ nhìn active worker, queue length hoặc số exception đều có thể dẫn đến chẩn đoán sai.
4. Hiểu **AbortPolicy, CallerRunsPolicy, DiscardPolicy, DiscardOldestPolicy**, bao gồm trường hợp task mất im lặng.
5. Viết **RejectedExecutionHandler** có bộ đếm rõ ràng, tránh double count và phân biệt rejection do shutdown với saturation.
6. Dùng hai mẫu để tính **completion rate**, **rejection rate** và **queue growth**, không suy luận một phương trình không được API bảo đảm.
7. Chạy lab Java 21 có một worker active, một task queued và một task rejected với stdout xác định.
8. Nhận diện **thread starvation deadlock**, downstream wait và CPU bottleneck bằng việc ghép executor metrics với thread dump/JFR.
9. Phân biệt queue bounded, unbounded, **SynchronousQueue**, delayed tasks và virtual threads.
10. Xây dựng runbook kiểm tra có thể thực hiện trên production mà hạn chế observer effect.

## 2. Vòng đời một task qua ThreadPoolExecutor

~~~text
Request / consumer / scheduler
              |
              v
       execute() hoặc submit()
              |
      +-------+----------+
      |                  |
  Chưa đủ core       Đã có core workers
  workers?           -> thử đưa vào queue
      |                  |
  Tạo worker             +----> Queue chờ worker
      |                  |
      |               Queue không nhận?
      |                  |
      |               Nếu chưa max, tạo worker
      |                  |
      +------------------+
              |
          Worker thực thi task
              |
          Kết thúc execution
              |
       completedTaskCount tăng

Nếu đã shutdown hoặc worker/queue không thể nhận:
       RejectedExecutionHandler
          - Abort: throw
          - CallerRuns: caller thực thi khi chưa shutdown
          - Discard: bỏ task
          - DiscardOldest: bỏ phần tử cũ, thử lại
~~~

Theo tài liệu Java 21:

- Khi số worker thấp hơn **corePoolSize**, executor thường ưu tiên tạo worker mới.
- Sau khi đã có core workers, executor ưu tiên **đưa task vào work queue**.
- Nếu queue không thể nhận, executor có thể tăng workers đến **maximumPoolSize**.
- Nếu đã shutdown hoặc không thể tiếp nhận, **RejectedExecutionHandler** xử lý.

**MaximumPoolSize không phải mục tiêu tự động mở rộng trong mọi cấu hình.** Ví dụ, khi work queue gần như vô hạn, task liên tục được xếp hàng và pool có thể không tăng vượt corePoolSize.

Một **request** có thể tạo nhiều Runnable, hoặc nhiều requests có thể được gom thành một task. Vì vậy, số task của pool không mặc nhiên bằng số HTTP requests, messages hoặc transaction.

## 3. Ý nghĩa và giới hạn của các getter

| API | Ý nghĩa | Cách phân loại | Giới hạn |
| --- | --- | --- | --- |
| **getCorePoolSize()** | Core worker count cấu hình | Cấu hình | Không phải active. |
| **getMaximumPoolSize()** | Trần số worker | Cấu hình | Không đảm bảo pool mở rộng tới đây. |
| **getPoolSize()** | Số worker hiện có | Gauge | Gồm cả worker idle. |
| **getActiveCount()** | **Ước lượng** số worker đang thực thi task | Gauge | Bao gồm task đang block/chờ. |
| **getLargestPoolSize()** | Peak workers từng có | Historical gauge | Không phản ánh mức bận hiện tại. |
| **getTaskCount()** | **Ước lượng** tổng tasks từng được scheduled | Counter | Không đồng nghĩa submission attempts. |
| **getCompletedTaskCount()** | **Ước lượng** tổng tasks workers đã chạy xong | Counter | Không đồng nghĩa business success. |
| **getQueue().size()** | Số task nằm trong queue khi đọc | Gauge | Không gồm active hoặc upstream backlog. |
| **getQueue().remainingCapacity()** | Slots còn lại theo queue | Gauge | Không đảm bảo submit tiếp theo được nhận. |
| **getRejectedExecutionHandler()** | Handler hiện được dùng | Metadata | Không trả về tổng số bị từ chối. |
| **isShutdown()** | Pool không nhận task mới như trước | Lifecycle | Giải thích rejections lúc deploy. |
| **isTerminating()/isTerminated()** | Tiến trình shutdown/termination | Lifecycle | Cần phân biệt pool chậm và đang dừng. |

**getActiveCount(), getTaskCount(), getCompletedTaskCount()** được JDK 21 mô tả là **approximate**. Các giá trị có thể thay đổi ngay trong lúc bạn gọi từng method. Không dùng một lần đọc để assert hệ phương trình đồng bộ toàn pool.

### 3.1. Active không có nghĩa RUNNABLE hoặc CPU busy

Nếu worker đang thực thi task rồi gọi **Future.get()**, chờ database hoặc lock, pool vẫn có thể tính nó là **active**. Thread dump có thể cho thấy worker ở **WAITING/BLOCKED**. Trường hợp active=8/8, queue tăng và CPU thấp thường gợi ý xem **I/O wait, lock contention, dependency hoặc thread starvation** trước khi tăng worker count.

Ngược lại, nếu worker ở RUNNABLE với CPU cao, completed rate thấp có thể do CPU-bound work, busy loop hoặc GC/throttling. **Cùng active=8** nhưng nguyên nhân và phương án khắc phục khác hẳn.

### 3.2. Completed không phải số request thành công

**getCompletedTaskCount()** tăng khi execution của task kết thúc trong worker. Một task có thể:

- Trả kết quả đúng.
- Ném RuntimeException/ExecutionException.
- Trả business error hoặc HTTP 500.
- Bị interrupt/cancel sau khi bắt đầu rồi kết thúc.
- Trả về nhanh vì fail-fast, trong khi request người dùng thất bại.

Với **submit(Callable)**, exception thường được lưu trong **Future**; việc thực thi đã kết thúc vẫn có thể được pool tính completed. Vì thế **completed rate cao** chưa có nghĩa throughput nghiệp vụ tốt. Cần đo **success, failure, timeout, canceled** tại lớp kết quả.

### 3.3. TaskCount không phải số gọi submit

**getTaskCount()** là ước lượng tổng tasks từng được scheduled. Nó khác **submitted attempts** khi có rejection, retry, CallerRuns, DiscardOldest, cancellation hoặc queue removal. Nếu một HTTP request submit ba tasks, taskCount tăng theo tasks, không theo một request. Một task bị từ chối ngay từ API gateway thì executor chưa biết tới nó.

Không gán metric tên **http_requests_total** từ getTaskCount. Hãy đặt tên chứa **executor_tasks_scheduled** và ghi rõ cách tính.

## 4. Độ dài hàng đợi: nhìn đúng backlog ở cấp pool

Queue length chỉ đo **phần tử đang chờ trong work queue của đúng executor**:

~~~text
Accepted task ở queue      -> tính trong queue.size()
Task worker đang thực thi  -> tính trong active, không còn queued
Request đang ở gateway     -> không nhất thiết vào queue của pool
Message đang ở broker      -> không nhất thiết vào queue của pool
Task chạy bằng CallerRuns  -> không nằm trong worker active/queue như thông thường
~~~

Ví dụ pool có 8 workers, queue capacity 100:

| Trạng thái | Active | Queued | Gợi ý |
| --- | ---: | ---: | --- |
| Vừa rảnh | 0 | 0 | Chưa thấy overload trong pool. |
| Burst nhỏ | 8 | 5 | Có thể bình thường nếu queue nhanh giảm. |
| Chậm kéo dài | 8 | 75 | Workers có thể xử lý quá chậm so với arrival. |
| Chạm capacity | 8 | 100 | Submissions mới có thể bị reject hoặc caller-runs. |
| Thất thường | 0 | 100 | Kiểm tra worker creation, shutdown, queue semantics và sampling. |

**Một snapshot có queue=75 không đủ kết luận** vì 75 tasks có thể được tiêu thụ chỉ trong vài mili giây. Cần ghi lại queue growth, time-in-queue, completion rate và task duration.

### 4.1. SynchronousQueue: queue 0 vẫn có thể saturated

**SynchronousQueue** truyền giao trực tiếp giữa producer và worker; nó không giữ hàng đợi backlog như ArrayBlockingQueue. **getQueue().size()** thường bằng 0 ngay cả khi pool đã max threads và đang reject tasks vì không có worker rảnh. **Queue=0 không chứng minh pool khỏe.**

### 4.2. Unbounded LinkedBlockingQueue: rejected 0 vẫn có thể quá tải

Một **Executors.newFixedThreadPool(n)** điển hình dùng **LinkedBlockingQueue không đặt capacity hữu hạn**. Nếu tốc độ đến lâu dài lớn hơn tốc độ hoàn tất, queue tăng mà chưa reject, dẫn đến chờ lâu và memory pressure.

Do đó **rejected=0 không chứng minh có đủ năng lực xử lý**. Với queue unbounded, việc sửa có thể là **bounded admission, timeout, concurrency limit, giảm retry** thay vì chờ đến lúc OOM.

### 4.3. Queue utilization chỉ áp dụng cho bounded queue rõ ràng

Với ArrayBlockingQueue capacity=100 và queued=75:

~~~text
queue_utilization = 75 / 100 = 75%
~~~

Không dùng phép tính đó trên **SynchronousQueue capacity=0**, queue unbounded hoặc delayed queue như thể cùng một đại lượng. **remainingCapacity()** là snapshot, không phải reservation; nhiều producers có thể cạnh tranh slots sau khi số đo được lấy.

## 5. Rejection policies quyết định ý nghĩa con số

**ThreadPoolExecutor không có getRejectedTaskCount()**. Khi không thể tiếp nhận task, executor gọi **RejectedExecutionHandler** theo policy đã chọn. Đây có thể là rejection do **saturation hoặc shutdown**.

| Handler của Java 21 | Thao tác | Hệ quả đo lường |
| --- | --- | --- |
| **AbortPolicy** | Ném RejectedExecutionException. | Task không được nhận; exception rõ. |
| **CallerRunsPolicy** | Caller chạy task trực tiếp trừ khi pool shutdown, khi ấy task bị bỏ. | Handler gọi nhưng task có thể hoàn tất; pool completed không bao trùm caller execution. |
| **DiscardPolicy** | Bỏ task im lặng. | Chỉ đếm exceptions sẽ không thấy task bị bỏ. |
| **DiscardOldestPolicy** | Bỏ task đầu queue và thử lại task mới nếu chưa shutdown. | Một task cũ bị mất; callback count khác số lost tasks. |

Một metric **rejected_total** thiếu mô tả dễ gây hiểu nhầm. Những khái niệm khác nhau gồm:

- **rejection_handler_calls_total**: tổng lần handler được gọi.
- **submission_exceptions_total**: tổng lần caller nhận RejectedExecutionException.
- **caller_runs_total**: tasks chạy trên thread submitter.
- **dropped_tasks_total**: tasks thực sự bị bỏ.
- **ingress_rejected_requests_total**: yêu cầu bị từ chối ngay ở gateway/rate limiter.

**Không cộng những counters này lại** nếu một submission có thể làm nhiều counter cùng tăng.

### 5.1. Ví dụ instrument handler đơn giản

~~~java
// Mã minh họa, rejectedCallbacks là AtomicLong ở bên ngoài đoạn này.
RejectedExecutionHandler handler = (task, pool) -> {
    rejectedCallbacks.incrementAndGet();
    throw new RejectedExecutionException(
            "executor cannot accept task");
};
~~~

Với handler này, callback dẫn đến exception. Nhưng **lý do handler gọi** vẫn có thể là pool đã shutdown chứ không chỉ saturation. Muốn đo nguyên nhân cần thêm trạng thái **isShutdown()**, timestamp và deployment events.

**Không tự ý thay handler của pool production chỉ để bổ sung metric** nếu thay đổi sẽ chuyển semantics từ CallerRuns/Discard sang Abort. Dùng wrapper không thay hành vi, tích hợp framework hoặc đo tại ingress.

### 5.2. CallerRunsPolicy là backpressure, không phải failure tuyệt đối

CallerRunsPolicy có thể giúp điều tiết producer bằng cách bắt **luồng submit** tự chạy task. Nhưng nếu caller là **HTTP event loop, consumer poll thread, scheduler hoặc thread đang giữ lock**, latency và khả năng phục vụ upstream có thể xấu đi.

Một dashboard chỉ xem active/completed của pool có thể bỏ sót CPU hoặc waiting time của tasks chạy trên caller. Theo dõi **caller_runs_total** và **time_spent_in_submit** để giải thích.

### 5.3. Discard có thể tạo Future chờ vô hạn

Nếu ứng dụng dùng **submit()** trả về **Future**, nhưng policy im lặng bỏ Runnable/FutureTask, người gọi **Future.get()** có thể không bao giờ nhận completion. **DiscardOldestPolicy** có thể loại một Future đã nằm trong queue mà không cancel nó. Vì vậy, silent discard gây rủi ro **treo logic** và làm thiếu metrics nghiệp vụ.

Không dùng silent discard cho task đòi kết quả/ack nếu chưa có thiết kế lifecycle, cancellation và deadline rõ ràng.

## 6. Hai mẫu đo: tính completion rate và rejection rate

**Active/queued** là gauges. **Completed/rejection-handler calls** là counters cần chênh lệch hai thời điểm.

Giả sử cùng một ThreadPoolExecutor, cách nhau 30 giây:

| Metric | t0 | t1 |
| --- | ---: | ---: |
| Active | 8 | 8 |
| Queue | 80 | 100 |
| Completed total | 2.400 | 3.000 |
| Handler calls total | 0 | 200 |
| Maximum workers | 8 | 8 |
| Queue capacity | 100 | 100 |

~~~text
completed delta  = 3000 - 2400 = 600
completion rate  = 600 / 30 = 20 tasks/s

handler delta    = 200 - 0 = 200
handler rate     = 200 / 30 ≈ 6.67 callbacks/s

queue delta      = 100 - 80 = 20
queue growth     = 20 / 30 ≈ 0.67 tasks/s
~~~

Cách đọc: pool bận liên tục, queue tăng đến capacity và handler có nhiều lần bị gọi. Đây là dấu hiệu saturation, **chưa là bằng chứng thiếu worker** vì có thể task duration tăng do DB/lock/network.

Không suy ngay:

~~~text
arrivalRate = completedRate + handlerRate + queueGrowthRate
~~~

bởi handler có thể caller-runs, tasks có thể bị cancel/drop, request khác tasks, counters không cùng phạm vi và các phép đo không đồng thời.

### 6.1. Counter resets và đồng hồ

Với metrics theo thời gian:

- Gắn **instance, process start time, executor identity**; khi JVM/pool restart, counters reset.
- Không tính delta âm thông thường khi t1 nhỏ hơn t0 do reset.
- Dùng thời điểm thực giữa samples; scrape interval có thể jitter.
- **System.nanoTime()** hợp để đo elapsed trong cùng JVM; wall clock giúp đối chiếu giữa máy.
- Nếu pool config thay đổi giữa t0/t1, ghi lại core/max/capacity và deployment event.

### 6.2. Java 21 runnable tính rate với stdout xác định

**Tệp PoolRateMath.java:**

~~~java
import java.util.Locale;

public final class PoolRateMath {
    record Sample(
            long timeNanos,
            long completed,
            long handlerCalls,
            int queued) {}

    public static void main(String[] args) {
        Sample a = new Sample(0L, 200L, 2L, 10);
        Sample b = new Sample(
                10_000_000_000L, 350L, 12L, 20);

        double seconds = (b.timeNanos() - a.timeNanos())
                / 1_000_000_000.0;
        double completedRate =
                (b.completed() - a.completed()) / seconds;
        double handlerRate =
                (b.handlerCalls() - a.handlerCalls()) / seconds;
        int queueDelta = b.queued() - a.queued();

        System.out.printf(Locale.ROOT,
                "completionRate=%.1f tasks/s%n", completedRate);
        System.out.printf(Locale.ROOT,
                "handlerRate=%.1f callbacks/s%n", handlerRate);
        System.out.println("queueDelta=" + queueDelta);
    }
}
~~~

~~~bash
javac --release 21 PoolRateMath.java
java PoolRateMath
~~~

**Stdout chính xác:**

~~~text
completionRate=15.0 tasks/s
handlerRate=1.0 callbacks/s
queueDelta=10
~~~

Đây là phép tính trên dữ liệu giả định. **Handler rate** được đo bằng callbacks/s, không tự suy thành lost requests/s khi policy không phải Abort.

## 7. Java 21 runnable: một worker chạy, một task chờ, một task bị từ chối

**QueueSaturationLab.java** thiết lập core=max=1, queue capacity=1 và handler tự đếm số lần rejection rồi throw. **CountDownLatch** giúp task đầu giữ worker cho tới khi đã đo xong, không dựa vào race của Thread.sleep.

**Tệp QueueSaturationLab.java:**

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class QueueSaturationLab {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicInteger rejected = new AtomicInteger();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(1),
                (task, executor) -> {
                    rejected.incrementAndGet();
                    throw new RejectedExecutionException(
                            "lab capacity reached");
                });

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            started.await();
            pool.execute(() -> {});

            try {
                pool.execute(() -> {});
            } catch (RejectedExecutionException expected) {
                // Handler đã đếm rejection; không tăng lần nữa.
            }

            System.out.println(
                    "before active=" + pool.getActiveCount()
                    + " completed=" + pool.getCompletedTaskCount()
                    + " queued=" + pool.getQueue().size()
                    + " rejected=" + rejected.get());

            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Lab pool did not terminate");
            }

            System.out.println(
                    "after active=" + pool.getActiveCount()
                    + " completed=" + pool.getCompletedTaskCount()
                    + " queued=" + pool.getQueue().size()
                    + " rejected=" + rejected.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

~~~bash
javac --release 21 QueueSaturationLab.java
java QueueSaturationLab
~~~

**Stdout khi chương trình hoàn tất bình thường:**

~~~text
before active=1 completed=0 queued=1 rejected=1
after active=0 completed=2 queued=0 rejected=1
~~~

**Giải thích tuần tự:**

1. Task thứ nhất đã chạy và báo **started**, rồi chờ latch; worker duy nhất vẫn bận: **active=1**.
2. Task thứ hai được đưa vào **ArrayBlockingQueue capacity=1**: **queued=1**.
3. Task thứ ba không thể vào queue hay thêm worker; handler tăng counter rồi ném **RejectedExecutionException**: **rejected=1**.
4. Trước khi release, chưa task worker nào kết thúc: **completed=0**.
5. Khi release và awaitTermination thành công, task 1 và task 2 kết thúc: **completed=2**, không còn active/queued. Task thứ ba không được worker thực thi.

Lệnh **shutdown()** vẫn cho các task đã nhận hoàn tất. **shutdownNow()** trong finally chỉ là cleanup nếu luồng điều khiển lỗi; nó không được gọi trước khi chụp trạng thái kết thúc bình thường.

**Lưu ý:** JDK gọi các getter là **ước lượng**. Demo dùng hai trạng thái được đồng bộ để minh họa, không biến nó thành snapshot nguyên tử cho production. Nếu bị interrupt hoặc JVM quá tải tới mức timeout 5 giây, chương trình báo lỗi thay vì hứa stdout đủ.

### 7.1. Vì sao thread dump không thấy task thứ hai?

Khi worker thứ nhất đang chờ CountDownLatch, một thread dump cho thấy stack của **task 1**. Task 2 mới nằm trong queue, chưa được worker lấy ra, nên **không có call stack đang chạy của task 2 trong worker**. Đây là lý do thread dump cần đi kèm **queue size, time-in-queue và submission logs**.

Đừng chạy saturation demo lên pool thật của ứng dụng production; lab này tạo pool độc lập nhỏ.

## 8. Tránh phương trình kiểm kê sai

Một phép tính tưởng hợp lý:

~~~text
outstanding = taskCount - completedTaskCount
outstanding = activeCount + queueSize
~~~

**Không có bảo đảm hai vế luôn bằng nhau.** Những khác biệt:

- **getTaskCount/getCompletedTaskCount/getActiveCount** là xấp xỉ khi concurrent.
- Các getter được gọi ở những thời điểm khác nhau.
- CallerRuns thực thi ngoài worker completed counter.
- DiscardOldest có thể loại một task đã queued.
- Task có thể bị canceled/removed, shutdownNow trả pending tasks.
- Submission được retry hoặc request tạo nhiều tasks.
- Work queue chỉ là một tầng, có thể còn broker/gateway/DB queues.
- Executor hoặc JVM restart khiến counter mất tính liên tục.

Nếu muốn accounting tuyệt đối ở business level, dùng **task IDs, task lifecycle transitions** và counters riêng cho **attempted, accepted, started, succeeded, failed, canceled, rejected, dropped**. Không ép thống kê pool ước lượng vào đẳng thức không được API cam kết.

## 9. Bảng chẩn đoán theo active, completed, queued, rejected

| Active | Completed rate | Queue | Rejection | Định hướng |
| --- | --- | --- | --- | --- |
| Cao | Cao | Thấp | Không | Pool bận nhưng có tiến triển, xem SLA/latency. |
| Cao | Thấp/0 | Tăng | Tăng khi đầy | Worker bị block, phụ thuộc chậm hoặc deadlock/starvation. |
| Cao | Cao | Chạm capacity | Tăng | Demand vượt capacity; xét backpressure/scale. |
| Thấp | Thấp | Thấp | Không | Có thể idle, hoặc nghẽn ở ingress ngoài pool. |
| Thấp | Thấp | Cao | Không rõ | Kiểm tra worker creation, lifecycle, shutdown hoặc queue semantics. |
| Cao | Cao | 0 | Tăng | Có thể SynchronousQueue. |
| 0 | 0 | 0 | Tăng | Có thể submissions tới executor đã shutdown. |
| Cao | Có tiến triển | Tăng đều | 0 | Có thể unbounded queue, chưa trigger rejection. |

**Đây là bảng lập giả thuyết**, không phải kết luận nhân quả. Cùng active=8, queue=100 có thể vì DB chậm, CPU throttle, lock contention, retry storm hoặc request rate hợp lệ quá cao.

### 9.1. Active cao, completed thấp, CPU thấp

Có thể workers đang **WAITING/BLOCKED** ở DB, HTTP client, socket, lock/monitor hoặc Future.get(). Thu thread dumps đúng thời điểm, xem DB connection pool, external API latency và các chu trình dependency.

### 9.2. Active cao, completed thấp, CPU cao

Có thể CPU-bound tasks, vòng lặp tốn tài nguyên, thread contention hoặc cgroup CPU quota. Dùng JFR/sampling profiler và CPU metrics, không tự tăng threads khi CPU đã hết headroom.

### 9.3. Completed tăng nhưng quality giảm

Pool có thể hoàn tất hàng nghìn tasks thất bại nhanh. Đối chiếu **business success rate, error/timeout rate và p95/p99**, không ca ngợi completed rate đơn lẻ.

### 9.4. Queue thấp nhưng request latency cao

Backlog có thể nằm ở API gateway, rate limiter, broker, connection pool hoặc caller-runs. **ThreadPoolExecutor queue** chỉ nhìn thấy những tasks đã được nhận vào queue đó. Instrument end-to-end request timeline.

## 10. Thread starvation deadlock từ Future dependency

Một fixed pool có **2 workers**. Task A và B đều đang chạy, cùng submit task con C và D về **chính pool đó** rồi chờ Future.get():

~~~text
Worker 1: Task A -> submit C -> Future.get(C)
Worker 2: Task B -> submit D -> Future.get(D)

Queue: [C, D]
Active: 2/2
Completed rate: 0
Handler calls: 0 nếu queue còn chỗ
~~~

C/D không có worker rảnh, còn A/B không chịu kết thúc. Đây là **thread starvation deadlock**, có thể không tạo chu trình monitor lock mà **ThreadMXBean.findDeadlockedThreads()** nhận ra. Số liệu **active=max + queue>0 + completed flat** gợi ý, stack Future.get xác nhận hướng điều tra.

**Không sửa bằng cách chỉ tăng queue capacity.** Cần tránh blocking join trong cùng fixed pool, tách executor, dùng asynchronous composition hoặc thay đổi dependency design; sau đó test correctness và load.

## 11. Instrumentation trong production

Một bộ metric gợi ý:

| Metric | Nguồn | Loại |
| --- | --- | --- |
| **executor_active_workers** | getActiveCount | Gauge |
| **executor_pool_size** | getPoolSize | Gauge |
| **executor_max_workers** | getMaximumPoolSize | Configuration |
| **executor_queue_size** | getQueue().size | Gauge |
| **executor_queue_capacity** | Bounded queue config | Configuration |
| **executor_completed_tasks_total** | getCompletedTaskCount | Counter xấp xỉ |
| **executor_scheduled_tasks_total** | getTaskCount | Counter xấp xỉ |
| **executor_rejection_handler_calls_total** | Instrument rejection handler | Counter custom |
| **executor_caller_runs_total** | Instrument CallerRuns | Counter custom |
| **executor_dropped_tasks_total** | Instrument drop policy | Counter custom |
| **executor_task_failures_total** | Task result handling | Counter custom |
| **executor_queue_wait_seconds** | Accepted time tới task start | Histogram |
| **executor_execution_seconds** | Task start tới task end | Histogram |
| **request_success_total** | Application boundary | Counter nghiệp vụ |

**Đây là các tên đề xuất**, không phải bộ tên chuẩn Java 21 hay của mọi phiên bản framework. Kiểm tra semantics thực tế trong Micrometer/JMX/Prometheus integration khi dùng.

### 11.1. Đếm đúng số task failed khi submit

Khi gọi **submit(Callable)**, executor có thể bọc task thành **FutureTask**. Trong subclass **ThreadPoolExecutor.afterExecute(Runnable, Throwable)**, tham số Throwable có thể là null dù Callable đã throw, vì exception được lưu trong Future. Vì vậy, đo failed ở **business completion boundary** hoặc task wrapper phù hợp; không coi t==null là success.

### 11.2. Không đếm rejection hai lần

Nếu handler tăng **rejection_handler_calls_total**, còn caller catch RejectedExecutionException tăng **submission_exceptions_total**, một submission có thể làm **cả hai metric tăng**. Chúng có chủ nghĩa khác nhau, không được cộng để báo tổng lost tasks. Định nghĩa một owner cho từng metric và giữ metadata về policy.

### 11.3. Cardinality, scope và units

Gắn labels **service, executor_name, instance, JVM start time**; tránh task ID/request ID/stacktrace làm label vì high cardinality. Dùng **tasks** cho count, **tasks/s** cho rate, **seconds** cho latency. Một aggregate queue size toàn cluster có thể che hot instance; đọc per replica trước khi gộp.

## 12. Một số executor không có cùng số đo

### 12.1. Virtual-thread-per-task executor

**Executors.newVirtualThreadPerTaskExecutor()** trên Java 21 tạo một virtual thread cho mỗi task thay vì shared ThreadPoolExecutor có getQueue/getActiveCount. Không ép cast sang ThreadPoolExecutor.

~~~java
// Đoạn minh họa, chưa phải chương trình độc lập.
try (var executor = java.util.concurrent.Executors
        .newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> processOneRequest());
}
~~~

Nếu cần active/queue/concurrency cho mô hình này, instrument **tại application admission, semaphore, request lifecycle hoặc downstream pool**. **ThreadMXBean.getThreadCount()** ở Java 21 chỉ đếm platform threads; nó không cho số virtual tasks sống.

### 12.2. ForkJoinPool

**ForkJoinPool** có getQueuedTaskCount, getQueuedSubmissionCount, getActiveThreadCount, getRunningThreadCount, getStealCount; phạm vi khác ThreadPoolExecutor:

- **getQueuedTaskCount** ước lượng tasks đang chờ ở worker queues.
- **getQueuedSubmissionCount** ước lượng external submissions chưa chạy.
- **getActiveThreadCount** có semantics work-stealing riêng.

Không gộp các values này với ThreadPoolExecutor queue size mà không gắn **executor_type** và diễn giải cụ thể.

### 12.3. ScheduledThreadPoolExecutor

Queue có thể chứa rất nhiều **delayed ScheduledFuture** chưa đến hạn chạy. Queue size cao không tự nghĩa worker đang không xử lý kịp. Đo **delay tới scheduled time, start delay, periodic task outcomes** và cancel lifecycle.

### 12.4. Framework-managed executors

Spring/Netty/Kafka/application servers có thể bọc hoặc thay executor. Phải biết framework dùng **ThreadPoolExecutor, event loop, scheduler hay virtual thread per task**, và rejection xảy ra trước/sau hàng đợi nào. Không suy luận từ tên thread pool hoặc một method trả ExecutorService chung.

## 13. Backpressure, queue sizing và SLA

Một thiết kế chống overload cần kết hợp:

1. **Giới hạn concurrency:** max workers, semaphore, DB connection slots.
2. **Giới hạn backlog:** bounded queue hoặc giới hạn chờ.
3. **Cơ chế từ chối rõ ràng:** 429/503, retry-after/backoff khi phù hợp, không silent drop.
4. **Đo queue wait và service time:** không chỉ queue length.
5. **Scaling và tối ưu dependency:** chỉ tăng workers nếu CPU/I/O/downstream còn capacity.

**Tăng queue giúp hấp thụ burst nhưng có thể làm request chờ quá SLA.** Một request chỉ có budget 200 ms mà phải đợi trong queue 1 giây sẽ không được cứu chỉ bằng việc thêm capacity queue.

### 13.1. Little's Law và giả định ổn định

Trong hệ thống ổn định, **Little's Law**:

\[
L = \lambda W
\]

với L là số công việc trung bình trong phạm vi xác định, λ là throughput ổn định, W là thời gian trung bình trong phạm vi đó. Nhưng một **queue snapshot** khi backlog đang tăng mạnh **không chứng minh thời gian chờ chính xác**. Instrument queue wait histograms và latency end-to-end.

### 13.2. Ví dụ năng lực xử lý giản lược

Nếu 8 workers, mỗi task tốn 100 ms trung bình, năng lực lý thuyết trong mô hình đơn giản khoảng **80 tasks/s**. Khi downstream chậm khiến mỗi task tốn 400 ms, năng lực khoảng **20 tasks/s**. Arrival 60/s làm queue tăng.

Đây là phép ước lượng, không phải capacity benchmark. Task duration distribution, GC, CPU, network, DB pool và concurrency limits làm kết quả thực tế khác. **Tăng worker vô điều kiện** có thể chỉ làm dependency quá tải hơn.

## 14. Thu thập bằng chứng với thread dump và JFR

Khi active cao, completed đứng và queue tăng:

- Lấy hai hoặc nhiều snapshots theo thời gian, so timestamp.
- Thu **jcmd Thread.print -l** hoặc thread dump phù hợp VM để xem worker stacks.
- Nếu stack tập trung ở **Future.get**, kiểm tra dependency cùng pool.
- Nếu stack ở **socket read/DB**, kiểm tra downstream latency/connection pool.
- Nếu stack ở **synchronized/locks**, điều tra contention và owner.
- Nếu stacks là CPU-bound, dùng JFR/CPU profiling và cgroup throttling metrics.
- Ghép **request trace IDs** để tránh chỉ suy luận từ một stack ngẫu nhiên.

Ví dụ JFR có giới hạn thời gian, chỉ dùng khi đã kiểm tra JVM, quyền, dung lượng và overhead:

~~~bash
jcmd 12345 JFR.start name=pool-triage \
  settings=profile duration=60s \
  filename=/diagnostics/pool-triage.jfr
~~~

**12345 và đường dẫn chỉ là ví dụ.** File được JVM target tạo trong filesystem của nó, không phải mặc định trên laptop chạy jcmd. JFR có thể giúp quan sát **execution samples, thread parks, monitor blocking, GC** nếu event đã được bật và recording window phù hợp. Đừng chụp dump liên tục mỗi 100 ms trên production.

## 15. Docker/Kubernetes và lifecycle metrics

Trong container, **active=max** không đồng nghĩa có đủ CPU thực:

- **CPU quota/throttling** có thể giảm tốc độ completed dù workers được lên lịch.
- **Memory limit** và unbounded queue có thể làm Pod OOM.
- **HPA dựa CPU** có thể không tự scale khi workload chủ yếu bị block ở DB và CPU thấp.
- **Multiple replicas** có thể phân phối tải lệch; nên xem queue/rejection per instance.
- **Rolling deploy/shutdown** reset pool counters và có thể tạo rejection spikes.
- **PID/mount namespace** ảnh hưởng cách lấy thread dump/JFR, không làm thay đổi nghĩa API Java.

Lệnh chỉ để xem bối cảnh Pod, không tự đọc queue của ứng dụng:

~~~bash
kubectl get pod api-worker-0 -o wide
kubectl describe pod api-worker-0
kubectl logs api-worker-0 -c app --since=10m
~~~

**Tên Pod là minh họa.** Để expose queue/rejection, ứng dụng/framework phải cung cấp metrics exporter hoặc custom MBean. Standard **ThreadMXBean** không có getter cho mọi ThreadPoolExecutor queues do ứng dụng tự tạo.

## 16. Runbook điều tra treo/tranh chấp của pool

**Bước 1 — Xác định đúng đối tượng.** Ghi app/JDK version, Pod/instance, pool name, executor type, core/max/queue capacity, rejection policy và task class.

**Bước 2 — Chụp ít nhất hai mẫu.** Đo active, poolSize, queue size, completed total, rejection handler total, lifecycle và timestamp. Xử lý counter reset, tính deltas/rates.

**Bước 3 — Phân loại triệu chứng.** Active full + completed flat + queue tăng gợi block/starvation. Queue full + handler tăng gợi admission limit. Queue 0 + handler tăng có thể SynchronousQueue. Handler tăng sau shutdown gợi lifecycle.

**Bước 4 — Đối chiếu bằng chứng.** Thread dump/JFR, request traces, DB/socket/lock metrics, CPU/GC, queue wait histogram, ingress rate và retry behavior.

**Bước 5 — Tìm nguyên nhân và hành động nhỏ nhất.** Sửa blocking dependency/deadlock, timeout, backpressure, retry storm, concurrency hoặc worker count chỉ khi có chứng cứ.

**Bước 6 — Kiểm tra sau sửa.** So workload tương đương: **business success throughput, p95/p99, queue wait, rejected/drop semantics, CPU/memory và downstream capacity**. Queue nhỏ đi không tự nghĩa user experience đã cải thiện.

**Bước 7 — Dọn quan sát.** Tắt temporary trace/recording, bảo vệ file chẩn đoán và lưu thông tin process/metric definitions.

## 17. Tình huống tự kiểm tra có lời giải

**A — Active 12/12, queue 200/200, completed rate thấp, rejected tăng.** Có chắc phải tăng workers?

**Đáp án:** chưa. Đây là dấu hiệu giới hạn pool. Cần xem stack, CPU/downstream, arrival/service time, rejection policy. Nếu DB chậm, tăng workers có thể làm tệ hơn.

**B — CPU thấp, active=max, completed gần 0.** Kiểm tra gì?

**Đáp án:** worker stacks, lock/connection pool/Future dependencies. Chờ I/O hoặc thread starvation có thể tạo active cao mà CPU thấp.

**C — Queue tăng 50.000, rejected=0.** Có an toàn không?

**Đáp án:** có thể đang dùng unbounded queue, leading to memory/latency pressure mà chưa reject. Cần bounded admission và timeout.

**D — Queue luôn 0, rejected cao.** Getter queue sai?

**Đáp án:** không nhất thiết; có thể là **SynchronousQueue** không giữ backlog.

**E — Rejection callbacks cao nhưng business success rate vẫn tốt.** Vì sao?

**Đáp án:** CallerRunsPolicy có thể chạy công việc tại caller. Đo caller latency và run counts, không gọi callback là lost request.

**F — Completed tăng nhưng HTTP 500 cũng tăng.** Mâu thuẫn không?

**Đáp án:** không. Completed chỉ phản ánh execution kết thúc, có thể kết thúc bằng error.

**G — Rejected spike đúng lúc rolling deploy.** Là overload?

**Đáp án:** có thể là pool shutdown, late submissions và routing chưa drain đúng. Kiểm tra isShutdown/deploy timeline.

**H — Hai workers chờ Futures của hai tasks cùng pool, queue có hai tasks.** Loại treo gì?

**Đáp án:** thread starvation deadlock. Cần sửa dependency graph/async composition, không chỉ tăng queue.

**I — Future bị DiscardOldest bỏ nhưng người gọi vẫn chờ.** Vấn đề gì?

**Đáp án:** Future có thể không bao giờ hoàn tất nếu không được cancel; cần thiết kế rejection/dropped lifecycle và timeout.

**J — Queue dài trong ScheduledThreadPoolExecutor.** Có nghĩa worker không theo kịp?

**Đáp án:** chưa chắc; queue có thể chứa delayed tasks. Cần biết deadline và độ trễ bắt đầu thật.

**K — newVirtualThreadPerTaskExecutor trả ExecutorService.** Có thể cast sang ThreadPoolExecutor để lấy active?

**Đáp án:** không. Metrics nên đo ở application admission/task lifecycle và giới hạn downstream.

**L — JVM restart giữa hai mẫu completed.** Có nên chia hiệu số âm cho thời gian?

**Đáp án:** không. Tách series theo process/pool identity và xử lý reset.

## 18. Sai lầm thường gặp và checklist

**Các sai lầm cần tránh:**

1. Active là số thread thật sự đang dùng CPU.
2. Completed là tổng request thành công.
3. ThreadPoolExecutor có sẵn getter tổng rejected.
4. Handler invocation chắc chắn là task bị mất.
5. Không có exception thì không có silent discard.
6. Queue=0 nghĩa không có saturation.
7. Rejected=0 nghĩa arrival không vượt capacity.
8. Max workers lớn nghĩa pool luôn tự mở rộng tới max.
9. Active + queued + completed + rejected bằng submitted tại mọi sample.
10. Một thread dump cho thấy đầy đủ tasks đang chờ queue.
11. Tăng maxPoolSize là cách sửa mọi timeout.
12. CallerRuns luôn an toàn cho HTTP event loop.
13. DiscardOldest không ảnh hưởng Future đã queued.
14. Queue size là thời gian chờ.
15. ThreadMXBean đo được mọi executor backlog.
16. ForkJoin queuedTaskCount giống ThreadPoolExecutor queue.size.
17. Scheduled queue có nhiều delayed tasks nghĩa đang overload.
18. Virtual threads bắt buộc có shared ThreadPoolExecutor queue.
19. Counter cộng/trừ xuyên JVM restart không cần xử lý.
20. Trung bình queue toàn cluster đủ để không bỏ sót hot replica.
21. shutdownNow pending tasks là các tasks rejected.
22. Completed rate tăng thì end-to-end SLA chắc chắn tốt.

**Checklist ngắn khi nhận cảnh báo:**

| Kiểm tra | Bằng chứng cần ghi |
| --- | --- |
| Pool identity | Name, implementation, instance, JVM start time. |
| Worker config | Core/max/poolSize/active. |
| Work queue | Type, capacity, size, remainingCapacity. |
| Progress | Completed rate trong cùng pool/process. |
| Rejection | Handler type và counter được định nghĩa rõ. |
| Lỗi nghiệp vụ | Success/failure/canceled/timeout rates. |
| Latency | Queue wait, service time, end-to-end p95/p99. |
| Các tầng khác | Gateway, broker, DB pool, external API. |
| Đóng/mở pool | Shutdown state, deployment/restarts. |
| Task dependency | Thread dumps, Future/lock ownership, JFR. |
| Giới hạn container | CPU throttle, memory/ephemeral capacity. |
| Kiểm tra hậu sửa | Before/after có workload tương đương. |

## 19. Tài liệu tham khảo chính thức

- [Java SE 21 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): cơ chế queueing, sizing, rejection và các getter approximate.
- [Java SE 21 — RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html): callback cho task không được tiếp nhận.
- [Java SE 21 — AbortPolicy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.AbortPolicy.html): từ chối bằng exception.
- [Java SE 21 — CallerRunsPolicy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html): xử lý trong caller.
- [Java SE 21 — DiscardPolicy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardPolicy.html): silent discard.
- [Java SE 21 — DiscardOldestPolicy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html): loại phần tử queue cũ và thử lại.
- [Java SE 21 — BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): size và remainingCapacity.
- [Java SE 21 — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): queued tasks/submissions và work stealing.
- [Java SE 21 — ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html): delayed/periodic queue.
- [Java SE 21 — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): factory methods và virtual thread per task.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): executor virtual threads và bản chất không pooling shared workers.
- [JDK 21 — jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): thread dump, JFR diagnostics.

**Kết luận:** để hiểu **treo và tranh chấp**, đừng xem active, completed, rejected và queued như bốn số đếm cùng một loại. **Active/queue là gauges; completed/rejection là counters cần delta/rate; rejection policy quyết định task bị throw, chạy trên caller hoặc bị bỏ.** Thread dump/JFR và business metrics giúp trả lời vì sao worker không tiến triển. Một kết luận đáng tin phải dựa trên **cùng process, cùng pool, cùng thời gian và cùng định nghĩa**.
