# Xác định nguyên nhân trước khi tinh chỉnh pool/lock

## 1. Vì sao phải chẩn đoán trước khi thay cấu hình?

Khi ứng dụng Java có nhiều thread chạy chậm, request timeout hoặc task chờ lâu, những thay đổi thường được đề xuất là **tăng số thread trong pool**, **tăng queue**, **đổi loại lock** hoặc **thay synchronized bằng cấu trúc concurrent**. Những thay đổi đó chỉ có ích nếu chúng tác động đúng nút thắt. Nếu vấn đề thật nằm ở cơ sở dữ liệu, network I/O, CPU đã bão hòa, deadlock hoặc khối lượng công việc không giới hạn, điều chỉnh pool/lock có thể làm throughput giảm, độ trễ tăng và lỗi khó truy vết hơn.

Nguyên tắc của bài này là:

> **Triệu chứng → bằng chứng → giả thuyết → kiểm chứng → thay đổi nhỏ → đo lại.**

Ví dụ: queue của executor tăng không chứng minh rằng pool "quá nhỏ"; có thể task bị chặn ở downstream. Thread ở trạng thái `WAITING` không tự chứng minh deadlock; nó có thể đang đợi việc hợp lệ từ queue. CPU cao cũng không tự chứng minh thiếu thread; nó có thể là dấu hiệu **đã có quá nhiều thread cùng tranh CPU**.

Phạm vi là **Java SE concurrency** (platform threads, `ExecutorService`, `ThreadPoolExecutor`, `synchronized`, `ReentrantLock`, `java.util.concurrent`, JVM diagnostics). Các nguyên tắc có thể áp dụng khi dùng framework, nhưng chẩn đoán và ví dụ ở đây không phụ thuộc Spring.

### Các dạng triệu chứng thường bị nhầm

| Triệu chứng | Giả thuyết cần kiểm tra | Bằng chứng quan trọng |
| --- | --- | --- |
| Task nằm trong queue lâu | Pool không đủ năng lực xử lý, downstream chậm, burst vượt capacity | Queue depth + queue wait time + task execution time + active workers |
| Throughput không tăng dù tăng threads | CPU bão hòa, lock contention, memory pressure, I/O giới hạn | CPU utilization, thread stack, JFR, throughput theo số threads |
| Nhiều thread `BLOCKED` | Tranh chấp intrinsic monitor (`synchronized`) | Stack trace, monitor owner, JFR monitor blocked events |
| Nhiều thread `WAITING` | Đợi queue, latch, condition, park, future, hoặc lock | Stack và đối tượng đang chờ, thời gian chờ, trạng thái tác vụ |
| Request treo vĩnh viễn | Deadlock, starvation, external dependency không trả lời | Nhiều thread dump theo thời gian, deadlock detection, timeout metrics |
| Pool báo `RejectedExecutionException` | Pool + queue hết sức chứa hoặc executor shutdown | Rejection count, queue depth, active workers, lifecycle |
| Latency p99 tăng nhưng average ít đổi | Pause, lock convoy, GC, scheduler, bursty queue | Latency distribution, JFR, GC, queue wait |
| CPU thấp, latency cao | Đợi I/O, lock, pool starvation, nguồn dữ liệu chậm | Thread dump và timing từng stage; không chỉ CPU tổng |
| Tăng queue khiến ít lỗi hơn nhưng chậm hơn | Queue che dấu overload, tăng thời gian chờ | Queue wait, p95/p99, age of oldest task, memory |

**Đầu tiên phải xác định mục tiêu:** cải thiện throughput (công việc/giây), latency end-to-end, giảm tail latency, giới hạn tài nguyên hay tăng khả năng chịu burst. Một tối ưu có thể cải thiện một chỉ số nhưng làm chỉ số khác xấu đi.

## 2. Mô hình hóa đường đi của một công việc

Một công việc được gửi vào executor thường có hành trình:

```text
Producer / caller
       |
       | submit/execute
       v
[Executor queue] ---- queue wait ----> [Worker thread]
                                            |
                                            +--> CPU computation
                                            +--> lock/condition
                                            +--> file/network/database I/O
                                            +--> wait for another future/task
                                            |
                                            v
                                       task complete
                                            |
                                            v
                                        result/ack
```

Thời gian end-to-end có thể phân tích thành:

```text
end-to-end latency ≈ queue wait + execution duration + response/coordination overhead
execution duration = useful work + waiting/blocking + scheduling overhead
```

Đây là phân rã *quan sát*, không phải công thức chính xác cho mọi pipeline: nếu có nhiều queue, retries hoặc xử lý song song, phải đo từng stage và chú ý các đoạn có thể chồng lấn.

Đừng gộp **thời gian queue** và **thời gian xử lý** thành một con số rồi kết luận `ThreadPoolExecutor` thiếu workers. Nếu `queue wait` lớn trong khi workers đang blocked ở socket hay lock, nguyên nhân gốc có thể ở bên ngoài pool.

Để điều tra, ghi tối thiểu: timestamp submit, timestamp bắt đầu task, timestamp kết thúc, trạng thái hoàn tất/lỗi/hủy và loại workload. Nếu có `Future`, phân biệt thời gian chờ ở caller khi `get()` với thời gian task chạy; `get()` chờ dài không chứng minh task đã chạy dài.

## 3. Thu thập baseline trước khi chỉnh

### 3.1 Những metric cần đo đồng thời

| Nhóm | Metric gợi ý | Mục đích |
| --- | --- | --- |
| Demand | submissions/s, burst size, số caller đồng thời | Biết nguồn gửi có vượt năng lực hay không |
| Completion | completed tasks/s, fail/cancel/reject count | Thấy lượng việc thực sự hoàn thành |
| Queue | depth, thời gian chờ, thời gian tồn đọng lâu nhất | Xác định backlog và latency do hàng đợi |
| Pool | current/core/max threads, active threads, pool utilization | Biết executor có bao nhiêu workers |
| Task | execution time, blocking time, timeout, exception | Phân biệt task chậm với queue chậm |
| CPU | process CPU, available cores, run queue, context switch | Nhận diện CPU saturation/oversubscription |
| Memory | heap occupancy, allocation rate, GC pauses | Xác định GC/memory pressure |
| Lock | blocked time, lock owner, contended monitor/synchronizer | Nhận diện tranh chấp và thứ tự lock |
| External | latency, timeout, concurrency và error rate của dependency | Không đổ lỗi cho pool nếu downstream là nút thắt |

Metric cần cùng **time window** và cùng workload. Một ảnh chụp queue tại một thời điểm có thể bỏ lỡ burst ngắn; throughput tăng nhưng p99 xấu đi là tín hiệu quan trọng.

### 3.2 Những chỉ số ThreadPoolExecutor chỉ là ảnh chụp/xấp xỉ

`ThreadPoolExecutor` có các API chẩn đoán:

```java
int poolSize = pool.getPoolSize();
int active = pool.getActiveCount();
int queued = pool.getQueue().size();
long submittedApprox = pool.getTaskCount();
long completedApprox = pool.getCompletedTaskCount();
```

Đây là **đoạn phương thức minh họa** dùng biến `pool` kiểu `ThreadPoolExecutor`, chưa phải chương trình độc lập. `getActiveCount()`, `getTaskCount()`, `getCompletedTaskCount()` cung cấp giá trị **ước lượng** vì pool và tasks có thể thay đổi trong lúc đọc. `getQueue().size()` chỉ là ảnh chụp queue tại thời điểm gọi; không được coi nhiều giá trị lấy liên tiếp là transaction nhất quán.

Đừng xem `getTaskCount() - getCompletedTaskCount()` là số pending chính xác theo mọi lúc, và đừng dựa vào `getQueue().size()` để trực tiếp điều khiển race-sensitive logic. Các số này hữu ích để vẽ xu hướng, đặt ngưỡng và hỗ trợ chẩn đoán.

### 3.3 Gắn tracing vào task đúng cách

Nếu cần phân biệt queue wait và execution time:

```java
long enqueuedAt = System.nanoTime();
executor.execute(() -> {
    long startedAt = System.nanoTime();
    try {
        runBusinessTask();
    } finally {
        long endedAt = System.nanoTime();
        recordQueueWait(startedAt - enqueuedAt);
        recordExecution(endedAt - startedAt);
    }
});
```

Đây là **mã minh họa**, giả định `executor`, `runBusinessTask`, `recordQueueWait`, `recordExecution` đã được cung cấp. `System.nanoTime()` phù hợp đo khoảng thời gian trôi qua trong cùng JVM; giá trị tuyệt đối không dùng làm giờ lịch. Với cancellation hoặc rejection, cần ghi nhận nhánh đó riêng, vì tác vụ bị từ chối sẽ không chạy vào lambda.

Việc thêm telemetry cũng có chi phí; tránh `println` trên mỗi thao tác nóng và dùng sampling/aggregation phù hợp.

## 4. Thí nghiệm Java 17+ độc lập: phân biệt queue đầy và worker đang bận

Đoạn sau cố ý tạo một worker đang chờ latch, hai task trong hàng đợi và một task bị từ chối. Nó cho thấy các tín hiệu cần quan sát **trước khi tăng pool size**. Đây là thí nghiệm có điều kiện điều khiển rõ ràng, không phải benchmark hiệu năng.

Tạo file `PoolDiagnosisDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PoolDiagnosisDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch running = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            pool.execute(() -> {
                running.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            running.await();

            pool.execute(() -> {});
            pool.execute(() -> {});

            System.out.println("queued=" + pool.getQueue().size());
            try {
                pool.execute(() -> {});
                System.out.println("rejected=false");
            } catch (RejectedExecutionException e) {
                System.out.println("rejected=true");
            }
        } finally {
            release.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Pool did not terminate");
        }
        System.out.println("completed=" + pool.getCompletedTaskCount());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 PoolDiagnosisDemo.java
java PoolDiagnosisDemo
```

Output bình thường của thử nghiệm đã kiểm tra bằng JDK:

```text
queued=2
rejected=true
completed=3
```

**Giải thích:**

1. Pool có đúng **1 worker tối đa**, queue có capacity **2** và policy `AbortPolicy`.
2. Task đầu tiên đếm `running` để main biết worker đã bắt đầu; sau đó worker chờ `release`. `running.await()` loại bỏ race giữa lúc submit và lúc kiểm tra queue.
3. Hai task rỗng tiếp theo chỉ được xếp vào queue, tạo `queued=2`. Vì worker duy nhất chưa thoát khỏi latch, queue vẫn đầy lúc kiểm tra.
4. Task thứ tư không thể được thực thi ngay và queue không còn chỗ, nên `execute()` ném `RejectedExecutionException`: in `rejected=true`.
5. Trong `finally`, main mở latch, yêu cầu shutdown và đợi kết thúc. Worker chạy xong task đầu và hai task đã được queue, nên `completed=3`; task bị từ chối **không** được tính hoàn tất.
6. Thí nghiệm không khẳng định "tăng pool là đúng": nó **cố ý chặn worker**. Với workload thật, phải biết worker bị chặn vì I/O, lock, điều kiện nghiệp vụ hay công việc CPU nặng.

Chương trình dùng các primitive của Java SE, không dùng framework hoặc dependency ngoài JDK. `getCompletedTaskCount()` trong môi trường concurrent có tính ước lượng, nhưng ở ví dụ sau `awaitTermination` thành công, toàn bộ ba task đã xong nên kết quả là 3. Nếu máy bị kẹt/timeout thì chương trình ném lỗi, không âm thầm trình bày kết quả đã hoàn tất.

### Rút ra một phép kiểm tra nguyên nhân

Giả sử hệ thống thực báo "queue luôn đầy". Trước khi tăng `maximumPoolSize`, cần hỏi:

- Worker đang **RUNNABLE dùng CPU**, đang chờ I/O, đang `BLOCKED` trên monitor, hay đợi `Future.get()` của task khác?
- Task duration và queue wait đang tăng cùng lúc hay chỉ có queue wait tăng?
- Submit rate có vượt completion rate trong một khoảng đủ dài không?
- Policy rejection làm gì: ném lỗi, chạy ở caller, drop hoặc cơ chế tùy biến?
- Queue là bounded hay unbounded? Với queue unbounded phổ biến, `maximumPoolSize` lớn có thể **không được dùng để tạo thêm workers** khi core threads đã hoạt động và task được queue.

Trả lời được các câu trên rồi mới chọn pool sizing, backpressure, giới hạn nguồn gửi hoặc sửa phần gây chặn.

## 5. Hiểu đúng hành vi ThreadPoolExecutor trước khi "tăng max"

`ThreadPoolExecutor` nhận các tham số chính: `corePoolSize`, `maximumPoolSize`, `keepAliveTime`, `BlockingQueue<Runnable>` và `RejectedExecutionHandler`. Cơ chế nhận task thông thường:

1. Nếu số workers ít hơn `corePoolSize`, executor ưu tiên tạo worker mới để chạy task.
2. Khi đã đủ core workers, nó thử đưa task vào queue.
3. Nếu queue không nhận được và số workers còn dưới `maximumPoolSize`, nó thử tạo worker bổ sung.
4. Nếu không thể nhận task hoặc executor không còn nhận việc, nó áp dụng rejection policy.

Chi tiết có đồng bộ/race/lifecycle trong implementation; trình tự trên là mô hình hành vi để hiểu cấu hình, không phải lời hứa mọi snapshot luôn khớp từng bước.

| Queue | Hệ quả | Khi cần chú ý |
| --- | --- | --- |
| `LinkedBlockingQueue` gần như không giới hạn | Task dễ tích tụ; `maximumPoolSize` thường không phát huy khi task cứ vào queue | Rủi ro tăng memory và queue latency khi overload kéo dài |
| `ArrayBlockingQueue` có giới hạn | Chặn tăng backlog vô hạn, có thể kích hoạt mở rộng workers tới max hoặc rejection | Phải chọn capacity dựa trên latency/memory và burst |
| `SynchronousQueue` | Không lưu task trong queue, trực tiếp handoff cho worker | Dễ tạo workers theo demand đến max; cần giới hạn hợp lý |
| Queue tự triển khai | Phụ thuộc semantics cụ thể | Xác minh blocking, capacity, fairness và contract |

**`Executors.newFixedThreadPool(n)`** theo mặc định dùng queue không giới hạn; nếu producer nhanh hơn consumers lâu dài, số queued tasks có thể tăng cao. **`Executors.newCachedThreadPool()`** có khả năng tăng số workers theo nhu cầu và tiềm ẩn tạo quá nhiều platform threads nếu thiếu giới hạn workload. Việc chọn factory tiện lợi không miễn trách nhiệm xác định giới hạn tài nguyên.

### Chọn kích thước pool từ bản chất công việc

- **CPU-bound:** khi worker dành phần lớn thời gian làm tính toán, nhiều workers hơn số logical CPUs thường không tăng throughput, có thể tăng context switch và contention. Đây là heuristic để bắt đầu đo, không phải công thức tuyệt đối.
- **Blocking I/O:** workers phải chờ I/O đáng kể, nên số workers có thể nhiều hơn số CPU. Tuy vậy downstream connection pool, tài nguyên hệ điều hành, memory và giới hạn remote service có thể trở thành nút thắt trước.
- **Mixed workload:** tách loại task khi cần, hoặc ít nhất đo tỷ lệ CPU/wait và queue của từng nhóm. Một nhóm task chậm có thể gây head-of-line blocking cho task nhanh.
- **Burst workload:** định nghĩa mức burst, tối đa queue wait chấp nhận được và cơ chế từ chối/điều tiết đầu vào. Tăng queue rất lớn có thể giảm số rejection nhưng lại gây timeout hàng loạt sau đó.

Không chọn `poolSize = 2 * CPU` hoặc `poolSize = 100` chỉ từ một công thức thuộc lòng. Hãy đo throughput và p95/p99 latency theo nhiều mức concurrency trong điều kiện kiểm soát.

## 6. Phân biệt các trạng thái thread từ thread dump

Thread dump là **ảnh chụp tại một thời điểm**. Trong Java platform threads, các trạng thái phổ biến:

| State | Ý nghĩa theo `Thread.State` | Không được suy ra |
| --- | --- | --- |
| `NEW` | Chưa start | Pool có lỗi |
| `RUNNABLE` | Đang chạy trong JVM hoặc sẵn sàng chạy; có thể ở native code | Chắc chắn đang dùng CPU 100% |
| `BLOCKED` | Chờ vào monitor của `synchronized` | Chắc chắn deadlock |
| `WAITING` | Chờ vô hạn vì `Object.wait`, `Thread.join`, `LockSupport.park`... | Chắc chắn bị lỗi |
| `TIMED_WAITING` | Chờ có thời hạn như `sleep`, timed `wait`, timed `join`, timed `park` | Chắc chắn task bị treo |
| `TERMINATED` | Thread đã kết thúc | Tự động cho biết kết quả của mọi task |

`ReentrantLock` sử dụng `AbstractQueuedSynchronizer` và cơ chế park; thread chờ lock có thể ở `WAITING`/`TIMED_WAITING`, khác thread chờ intrinsic monitor thường ở `BLOCKED`. Vì vậy chỉ đếm `BLOCKED` sẽ **bỏ sót lock contention** dạng khác.

Khi đọc stack trace, tìm **frame ứng dụng đầu tiên** gần lời gọi blocking và kiểm tra:

- Thread đang chờ lock nào, lock owner là thread nào?
- Nếu chờ `Future.get()`, task được chờ chạy ở pool nào? Có phải đang đợi chính pool đã hết workers?
- Nếu stack ở `SocketInputStream`/network I/O, thời gian chờ downstream và timeout bao nhiêu?
- Nếu nằm ở `BlockingQueue.take()`, đó có thể là **idle worker bình thường**.
- Có nhiều thread cùng kẹt tại cùng call site qua nhiều dump liên tiếp không?

### Khi nào cần nhiều thread dump?

Một dump đơn lẻ cho biết "thread đang ở đâu" nhưng không chứng minh thread đã ở đó bao lâu. Lấy **vài snapshot cách nhau một khoảng phù hợp với latency mong đợi**, so stack theo thread và liên hệ với metrics lúc đó. Không lấy dump liên tục với tần suất quá cao vì việc quan sát cũng có overhead.

**Ví dụ đọc kết quả:**

```text
worker-1 WAITING at LinkedBlockingQueue.take()
worker-2 WAITING at LinkedBlockingQueue.take()
```

Có thể là pool đang rảnh và không có task. Ngược lại:

```text
worker-1 WAITING at FutureTask.get()
worker-2 WAITING at FutureTask.get()
```

Nếu cả hai worker cùng chờ tasks mới được submit vào **chính pool hai workers đó**, đây là dấu hiệu của **thread starvation deadlock**: không worker nào rảnh để chạy task con. Stack riêng lẻ chưa đủ, cần xác minh mối quan hệ task cha–con và queue.

## 7. Chẩn đoán lock contention và deadlock

### 7.1 Lock contention

**Contention** xảy ra khi nhiều threads tranh cùng một lock và ít nhất một thread phải chờ. Nó không nhất thiết là lỗi; lock bảo vệ invariant là cần thiết. Vấn đề là thời gian giữ lock, tần suất lấy lock hoặc số thread tranh chấp khiến throughput/latency không đáp ứng yêu cầu.

Dấu hiệu:

- Nhiều threads cùng chờ một monitor/`ReentrantLock`.
- JFR cho thấy sự kiện monitor enter chậm hoặc thời gian chờ đáng kể.
- CPU tổng thấp nhưng throughput thấp vì phần lớn threads bị chặn.
- p99 tăng vào giờ cao điểm khi contention vượt ngưỡng.

**Phân tích critical section:** phần nào thật sự phải ở trong lock? Có blocking I/O, `Thread.sleep`, callback không kiểm soát, database call, logging đồng bộ hoặc nested lock bên trong không? Việc giữ lock trong khi gọi code ngoài quyền kiểm soát làm tăng thời gian giữ lock và nguy cơ deadlock.

Ưu tiên giảm công việc trong critical section nếu correctness cho phép, hoặc giảm shared mutable state. Chỉ đổi sang `ReadWriteLock`, `StampedLock`, atomics hoặc cấu trúc concurrent nếu workload thực sự phù hợp và đã kiểm tra semantics. Các abstraction đó không tự luôn nhanh hơn `synchronized`.

### 7.2 Deadlock thực sự

Deadlock là một nhóm threads/tác vụ **chờ lẫn nhau theo chu trình** và không thể tiến triển trong điều kiện hiện tại. Ví dụ hai monitors:

```text
Thread A: holds lockA -> waits for lockB
Thread B: holds lockB -> waits for lockA

A ----waiting----> B
^                   |
|------waiting------|
```

Các hướng xử lý đúng bản chất:

- Áp dụng một **thứ tự lấy nhiều lock nhất quán** trên mọi đường đi.
- Giảm nested locks và thời gian giữ lock.
- Với `ReentrantLock`, cân nhắc `tryLock(timeout)` và thiết kế nhánh fail/retry **có giới hạn**, kiểm tra được; timeout không tự sửa mọi loại deadlock.
- Tránh giữ lock khi chờ `Future.get()` hoặc callback có thể cần lock đó.
- Sửa các vòng phụ thuộc giữa tasks/executors, không chỉ tăng workers.

**Phân biệt với starvation:** một nhóm task có thể không chạy được vì workers đang chờ những task khác cùng pool mà không có *chu trình sở hữu monitor*. `ThreadMXBean.findDeadlockedThreads()` không bảo đảm tìm được mọi kiểu starvation hoặc wait-for-resource cycle.

### 7.3 ThreadMXBean trong Java SE

`java.lang.management.ManagementFactory.getThreadMXBean()` cung cấp API đọc thông tin về platform threads. Hai phương thức quan trọng:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
long[] deadlocked = mx.findDeadlockedThreads();
ThreadInfo[] infos = mx.dumpAllThreads(true, true);
```

Đây là **đoạn minh họa**, cần `import java.lang.management.ManagementFactory;`, `ThreadMXBean`, `ThreadInfo` và kiểm tra feature support. `findDeadlockedThreads()` có thể trả `null` nếu không phát hiện chu trình deadlock với monitors/ownable synchronizers được hỗ trợ. Nếu implementation không hỗ trợ chức năng nhất định, API có thể ném `UnsupportedOperationException`; kiểm tra `isSynchronizerUsageSupported()` và `isObjectMonitorUsageSupported()` trước khi yêu cầu thông tin tương ứng.

Có thể dùng `isThreadContentionMonitoringSupported()` và `setThreadContentionMonitoringEnabled(true)` để quan sát contention time khi JVM hỗ trợ. Monitoring contention thường **tắt mặc định** và có overhead; dùng theo nhu cầu, không tự bật toàn thời gian chỉ để thu một con số.

**Giới hạn quan trọng:** `ThreadMXBean` truyền thống tập trung vào **platform threads**; không hỗ trợ theo dõi và quản lý virtual threads qua cùng các phép liệt kê/detection này. Trên Java 21+ nếu ứng dụng dùng virtual threads, cần công cụ JFR/dump phù hợp môi trường và không suy ra rằng "không có thread trong MXBean" là không có công việc đang chạy.

## 8. Bộ công cụ chẩn đoán JVM

### 8.1 jcmd và thread dump

Trên JDK hỗ trợ, thực hiện trên cùng máy/đúng quyền truy cập process Java:

```shell
jcmd -l
jcmd <pid> help
jcmd <pid> Thread.print -l
```

`<pid>` là PID thực cần thay, không gõ nguyên ký hiệu ngoặc nhọn. `jcmd -l` liệt kê các Java processes có thể thấy; `Thread.print -l` in stack và các lock của `java.util.concurrent` khi được hỗ trợ. Thực tế tên command hoặc option có thể khác theo JDK/vendor; dùng `jcmd <pid> help` để xác nhận.

**Điểm quan trọng khi đọc dump:** phân biệt thread đang `RUNNABLE` với CPU sử dụng thực, `WAITING` vì idle queue với `WAITING` do `Future.get()`, và `BLOCKED` vì monitor với `WAITING` ở ownable synchronizer. Đối chiếu nhiều dump và metrics cùng thời gian.

### 8.2 JFR: ghi lại diễn tiến thay vì chỉ một snapshot

Java Flight Recorder (JFR) hỗ trợ quan sát runtime events với overhead được thiết kế tương đối thấp. Ví dụ thu bản ghi 60 giây từ Java process đang chạy:

```shell
jcmd <pid> JFR.start name=pool_diagnosis settings=profile duration=60s filename=pool-diagnosis.jfr
```

`settings=profile` cung cấp profile event sâu hơn `default`, có thể tăng overhead; cấu hình và quyền truy cập cần phù hợp môi trường. Có thể mở bản ghi bằng JDK Mission Control hoặc đọc với công cụ `jfr` của JDK phù hợp. Kết quả cần phân tích theo **time range** trùng lúc queue/latency tăng. Một bản ghi lúc hệ thống nhàn rỗi không giải thích sự cố lúc tải cao.

Các tín hiệu có ích: execution samples, CPU load, allocations, garbage collection, Java monitor blocked/park events và thời gian thread hoạt động. Không phải mọi sự kiện đều được bật ở mọi configuration; kiểm tra JFR template trước khi kết luận từ sự vắng mặt của một event.

### 8.3 GC và CPU profiling

Với HotSpot, có thể kích hoạt GC logging khi cần chẩn đoán, ví dụ:

```shell
java -Xlog:gc -jar app.jar
```

Đây là lệnh minh họa yêu cầu file `app.jar` có thật; khởi chạy mới với logging, không phải lệnh gắn log vào process hiện có. So khớp GC pause với latency spikes theo timestamp, không suy ra "GC là thủ phạm" từ việc chỉ thấy có GC.

CPU profiler giúp phân biệt busy computation và thời gian chờ, nhưng profiler có overhead. Với lock contention, lấy cả stack/lock owners/JFR thay vì chỉ nhìn một flame graph CPU.

### 8.4 Cần quan sát cả phụ thuộc ngoài JVM

Nếu worker chờ network, file I/O hay database, thông tin trong JVM chỉ là **một nửa câu chuyện**. Đối chiếu connection pool saturation, throughput downstream, retry storms, timeout, rate limit và hàng đợi phía dependency. Nếu downstream giới hạn 20 kết nối, nâng Java pool lên 200 workers có thể tạo thêm 180 threads chờ và làm tail latency tệ hơn.

## 9. Quy trình suy luận từ triệu chứng tới sửa lỗi

Một quy trình phù hợp với điều tra thực tế:

### Bước 1 — Định nghĩa sự cố bằng số

Ghi rõ thời điểm, workload, phiên bản JDK, số workers, queue capacity, rejection policy, CPU, p50/p95/p99 latency và tỷ lệ lỗi. Ví dụ: "p99 tăng từ mức thông thường lên 2 giây khi submissions tăng 3 lần và queue wait tăng tương ứng" có ích hơn "Java bị chậm".

### Bước 2 — Tách queue wait khỏi execution time

Nếu queue wait tăng còn task execution ổn định, vấn đề có thể là **thiếu năng lực xử lý so với tốc độ nhận việc**. Nếu execution time tăng trong khi số active workers đều bận, hãy xem workers đang làm gì. Nếu cả hai tăng, backlog có thể là *hậu quả* của task duration tăng.

### Bước 3 — Kiểm tra loại công việc

Phân biệt CPU-bound, blocking I/O, lock-bound, memory/GC-bound, mixed hoặc dependency-bound. Sử dụng thread dumps và JFR để tìm hot path và nơi chờ. Không tự quy mọi `WAITING` về deadlock.

### Bước 4 — Xác minh một giả thuyết có thể bác bỏ

Ví dụ:

- Giả thuyết **A**: worker quá ít cho các task I/O. Kiểm chứng: workers chờ I/O phần lớn thời gian, CPU còn dư, downstream có capacity, tăng workers có cải thiện completion throughput và p99 không?
- Giả thuyết **B**: lock giữ quá lâu. Kiểm chứng: nhiều threads đợi cùng monitor, owner giữ lock qua I/O, rút ngắn critical section làm giảm blocked time?
- Giả thuyết **C**: CPU đã bão hòa. Kiểm chứng: CPU gần ngưỡng core thực, thêm workers làm context switches tăng nhưng throughput không tăng?
- Giả thuyết **D**: các task đang chờ tasks con trên chính pool. Kiểm chứng: stack `Future.get()`, task con bị queue, không còn worker khả dụng; đổi dependency/scheduling thay vì chỉ thêm threads?

### Bước 5 — Thay đổi có giới hạn và đo lại

Ưu tiên sửa nguyên nhân đã xác minh: hạn chế fan-out, giảm blocking I/O trong lock, thay cấu trúc đợi lẫn nhau, thêm timeout, điều tiết producer, cache/giảm work, chọn pool size/queue capacity hợp lý. Thay đổi **một biến đáng kể mỗi lần** trong môi trường có tải đại diện.

So sánh trước/sau theo cùng loại dữ liệu và cách đo; kiểm tra correctness, throughput, p95/p99, CPU, memory/GC, backlog, rejection và khả năng phục hồi khi tải giảm.

### Bước 6 — Chuẩn bị rollback và chính sách overload

Một pool ổn ở tải thường vẫn có thể sụp khi burst. Thiết kế rõ: bounded queue, tín hiệu overload, backpressure/rate limit, rejection behavior, cancellation, timeout và resource cleanup. Không đổi mặc định sang `CallerRunsPolicy` mà chưa kiểm tra tác động: policy này khiến **caller chạy task khi pool bão hòa** (khi executor chưa shutdown), làm chậm caller và có thể thay đổi latency, điều khiển luồng hoặc gây blocking ngoài dự kiến.

## 10. Tình huống điển hình: pool starvation do task chờ task

Giả sử có fixed pool 2 workers. Hai task cha đã chiếm cả 2 workers; mỗi task cha submit một task con vào chính pool rồi đồng bộ chờ `Future.get()`. Hai task con nằm trong queue nhưng **không có worker trống**.

```text
fixed pool: 2 workers

worker-1: parent-A --> submit child-A --> Future.get() -- waits
worker-2: parent-B --> submit child-B --> Future.get() -- waits

queue: [child-A, child-B]      no free worker
```

**Triệu chứng:** CPU thấp, queue vẫn có task, mọi worker `WAITING`, request treo. Đây không nhất thiết là deadlock vì thứ tự monitor; `findDeadlockedThreads()` có thể không báo gì.

**Sửa đúng bản chất:** không đồng bộ đợi task con trên cùng executor giới hạn workers; thiết kế lại dependency, chuyển sang composition bất đồng bộ không block, phân tách pool hợp lý hoặc cho caller thực hiện công việc con nếu đảm bảo semantics. Tăng `maximumPoolSize` có thể không tác dụng với unbounded queue; tăng fixed worker count chỉ trì hoãn tái xuất hiện nếu fan-out cũng tăng.

Để kiểm chứng, đo số task cha đang blocking, task con trong queue và stack tại `Future.get()`. Sau sửa, xác minh throughput, correctness và khả năng kết thúc dưới tải cao.

## 11. Tình huống điển hình: tranh lock vs tăng thread

Giả sử có 16 worker đều gọi một method cập nhật shared map dưới `synchronized`. Mỗi lần giữ monitor 20 ms vì method còn ghi log hoặc gọi I/O. Dù tăng lên 64 workers, critical section về cơ bản vẫn chỉ cho một thread vào mỗi lần.

**Dấu hiệu:** nhiều threads `BLOCKED` trên cùng monitor, owner giữ lock trong phương thức chậm; throughput gần giới hạn do lock và blocked time tăng khi số workers tăng.

**Giải pháp có cơ sở:**

1. Di chuyển I/O, logging và phần tính toán độc lập ra ngoài critical section nếu vẫn giữ tính đúng đắn.
2. Thay coarse-grained lock bằng cấu trúc concurrent hoặc phân vùng state khi access pattern phù hợp.
3. Giảm fan-out để tránh tạo công việc tranh cùng lock vô ích.
4. Đo lại contention, throughput và correctness ở nhiều mức threads.

Không thay `synchronized` bằng `ReentrantLock` chỉ vì tên class trông tối ưu hơn. Cả hai vẫn có thể bảo vệ critical section dài, và đo contention mới cho biết lựa chọn có hữu ích không.

## 12. Ma trận quyết định trước khi tinh chỉnh

| Bằng chứng đã kiểm chứng | Hướng can thiệp thường hợp lý | Rủi ro cần đo |
| --- | --- | --- |
| CPU sát giới hạn, workers `RUNNABLE` làm tính toán | Giảm work/thuật toán, giảm oversubscription, giới hạn parallelism | Context switch, GC, throughput khi giảm threads |
| CPU thấp, workers chờ I/O, downstream còn capacity | Timeout, xử lý async hoặc tăng concurrency có giới hạn | Downstream saturation, connection pool, tail latency |
| Queue wait cao, execution thấp, active workers bận thực sự | Xem pool size phù hợp workload, admission control | Memory, rejection, p99, rate of completion |
| Queue tăng cùng downstream latency | Giải quyết dependency, giới hạn đầu vào và retries | Retry storm, cascading timeout |
| Nhiều threads chờ cùng monitor lâu | Giảm critical section/lock contention | Correctness, race, visibility |
| `Future.get()` từ task trên chính fixed pool | Bỏ blocking dependency hoặc thiết kế lại scheduling | Task ordering, cancellation, error propagation |
| Deadlock confirmed bằng chu trình lock | Sửa thứ tự lock, nested lock, acquisition protocol | Correctness, livelock, timeout semantics |
| GC pauses trùng với spikes và allocation cao | Giảm allocation bất hợp lý, xử lý heap/GC theo bằng chứng | Throughput, heap pressure, latency |
| Rejection do overload thật | Bounded queue, backpressure và chính sách fail rõ ràng | Caller impact, dropped work, retries |
| Metric chưa đầy đủ hoặc chỉ một snapshot | Tăng quan sát có kiểm soát | Overhead của instrumentation |

## 13. Những sai lầm thường gặp

- **Tăng threads khi CPU đã bão hòa:** tạo thêm scheduling overhead và cache misses, chưa chắc tăng work hoàn thành.
- **Tăng queue vô hạn để "hết lỗi":** chỉ chuyển overload thành độ trễ và memory pressure; nhiều task có thể hết hạn trước khi được chạy.
- **Chỉ quan sát `pool.getActiveCount()` mà không xem stacks:** active cao không nói worker đang làm CPU hay bị blocked.
- **Coi mọi `WAITING` là deadlock:** workers rảnh đợi queue là trạng thái bình thường.
- **Coi không có `BLOCKED` là không có lock contention:** `ReentrantLock` có thể dùng park và hiện `WAITING`.
- **Dùng `Thread.sleep` để "sửa race" trong diagnostic code:** sleep không chứng minh worker đã đến bước xác định; dùng latch/phaser/condition có tín hiệu rõ ràng.
- **Đọc một thread dump rồi sửa ngay:** trạng thái thread là snapshot, cần tương quan nhiều snapshot và metrics.
- **Đo chỉ average latency:** có thể bỏ lỡ phần đuôi p99, nơi queueing và contention thể hiện rõ.
- **Không xét rejection/cancellation:** throughput chỉ tính công việc hoàn tất không phản ánh các task đã mất/từ chối.
- **Không đóng executor:** thread pool còn sống làm ứng dụng khó dừng; cần `shutdown()` và, khi phù hợp, `awaitTermination()`/đường hủy.
- **Nhìn thấy thêm task hoàn tất nhưng bỏ qua correctness:** race, lost updates hoặc skip task không phải tối ưu.

## 14. Câu hỏi tự kiểm tra

**Q1. Queue dài có chứng minh pool size quá nhỏ?** Không. Phải xem completion rate, task execution duration và nguyên nhân workers đang bận/chờ.

**Q2. Thread state `RUNNABLE` có đồng nghĩa thread đang tiêu thụ CPU?** Không. Đây là state JVM bao gồm có thể đang đợi CPU hoặc ở native code; phải đo CPU time và trạng thái OS phù hợp.

**Q3. Thread state `WAITING` có đồng nghĩa deadlock?** Không. Có thể chờ queue, condition, latch, join hoặc future một cách hợp lệ. Cần stack, dependency và thời gian chờ.

**Q4. `findDeadlockedThreads()` trả `null` có chứng minh không có starvation?** Không. API chỉ phát hiện một số chu trình monitor/ownable synchronizer của platform threads, không tìm mọi tình huống wait-for-task.

**Q5. Vì sao tăng `maximumPoolSize` với unbounded queue có thể vô ích?** Khi core workers đã có và queue luôn nhận task, executor thường không cần tạo thêm workers tới maximum.

**Q6. Vì sao phải đo queue wait riêng task execution time?** Vì bottleneck có thể nằm trước khi task chạy hoặc trong task; hai vấn đề có cách xử lý khác nhau.

**Q7. Nên thay `synchronized` bằng `ReentrantLock` ngay khi thấy contention?** Không. Xem critical section, thời gian giữ lock, semantics và đo lại trước khi chọn cấu trúc thay thế.

**Q8. Một phép thử pool tăng từ 8 lên 16 workers làm throughput tăng 10%, có đủ để chốt?** Chưa. Cần xem variance, p95/p99, CPU, memory, error/rejection, downstream và workload đại diện ở tải thực.

## 15. Checklist chẩn đoán trước quyết định

- [ ] Xác định chính xác workload, khung thời gian và chỉ số gặp vấn đề.
- [ ] Có đồng thời submit rate, completion rate, rejection, queue depth, queue wait và execution time.
- [ ] Có CPU, memory/GC và số threads so với số core.
- [ ] Có thread dumps/JFR cùng thời điểm phát sinh triệu chứng, phân biệt trạng thái chờ hợp lệ với bất thường.
- [ ] Đã kiểm tra task có chờ `Future` của task khác trong cùng executor hay không.
- [ ] Đã xác nhận contention owner, thời gian giữ lock và call site trước khi đổi lock.
- [ ] Đã xác nhận downstream capacity, timeout và retries trước khi tăng parallelism.
- [ ] Đã xác định queue bounded/unbounded và rejection policy.
- [ ] Giả thuyết sửa lỗi có tiêu chí xác nhận và tiêu chí bác bỏ.
- [ ] Thay đổi nhỏ, có rollback, đo lại throughput, latency tail, error và correctness.

### Tài liệu Java SE / OpenJDK

- [`ThreadPoolExecutor` — Queueing, rejection và monitoring methods](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [`Thread.State` — định nghĩa các trạng thái thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html)
- [`ThreadMXBean` — CPU, contention monitoring và deadlock detection](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [`jcmd` — thread dump và JFR diagnostic commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [JDK Mission Control và JFR](https://openjdk.org/projects/jmc/)