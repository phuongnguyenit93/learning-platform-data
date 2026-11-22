# 18.4. Phân biệt thời gian xử lý tác vụ với thời gian chờ trong hàng đợi

Một request có thể mất 800 ms để hoàn tất nhưng code xử lý chính chỉ chạy 30 ms. Phần lớn thời gian còn lại có thể đã trôi qua **trước khi worker nhận tác vụ**, do thread pool bận, hàng đợi đầy hoặc một tài nguyên khác chưa sẵn sàng. Ngược lại, một tác vụ bắt đầu gần như ngay lập tức nhưng mất 800 ms trong `run()` có thể đang chờ I/O, database connection, lock hoặc dịch vụ bên ngoài. Hai triệu chứng cần cách điều tra rất khác nhau.

Trong Java, chẩn đoán độ trễ chính xác bắt đầu bằng việc **định nghĩa rõ ranh giới thời gian**: khi nào công việc được nhận, khi nào đi vào queue, khi nào worker thực sự bắt đầu xử lý và khi nào kết thúc. Không nên gọi mọi khoảng thời gian “latency” rồi kết luận ngay code nghiệp vụ đang chậm.

Bài này dùng Java 17+, `ExecutorService` / `ThreadPoolExecutor` làm ví dụ chính, đồng thời liên hệ request HTTP, I/O bất đồng bộ, hàng đợi message và công cụ JVM/JFR. Mọi con số trong bảng là ví dụ minh họa trừ khi ghi rõ là output xác định từ code.

## 1. Bốn mốc cơ bản và ba khoảng cần tách

Giả sử một tác vụ đã được hệ thống chấp nhận để xử lý:

- `t_enqueue`: thời điểm tác vụ được đưa vào hoặc được gửi tới bộ lập lịch/hàng đợi ở ranh giới ta chọn đo.
- `t_start`: thời điểm worker bắt đầu thực hiện logic của tác vụ (đầu `Runnable.run()` hoặc `Callable.call()`).
- `t_finish`: thời điểm logic hoàn tất hoặc kết thúc bằng lỗi.
- `t_response`: thời điểm phía gọi nhận kết quả cuối, nếu có bước phản hồi/truyền mạng phía sau.

Các khoảng (dùng chung một thước đo thời gian trong một JVM):

```text
     submit/accepted             worker starts                     task finishes
t_enqueue ────────────────────── t_start ────────────────────────── t_finish
           <--- queue wait --->           <--- execution time --->
           <---------------- task residence / sojourn ----------->

task_queue_wait     = t_start  - t_enqueue
task_execution_time = t_finish - t_start
task_total_time     = t_finish - t_enqueue
task_total_time     = task_queue_wait + task_execution_time
```

Đẳng thức cuối **đúng cho từng tác vụ** khi ba timestamp dùng cùng đơn vị/clock và ranh giới nhất quán. Nếu tác vụ chưa từng bắt đầu (bị từ chối, hủy hoặc timeout trong queue), không có `t_start`/`t_finish` theo nghĩa này; không được gán bừa execution = 0 rồi đưa vào thống kê những tác vụ hoàn tất thành công.

`task_execution_time` ở đây là **wall-clock elapsed time** trong phạm vi thực thi tác vụ. Nó bao gồm cả lúc worker đang bị chặn ở I/O, đợi lock, chờ downstream, bị hệ điều hành ngừng lập lịch hoặc chịu pause của JVM. Đây **không phải CPU time**. Đo CPU time của thread cần công cụ khác và có ngữ nghĩa khác.

### Độ trễ end-to-end còn có các đoạn ngoài queue của executor

Đối với HTTP request:

```text
client gửi ── mạng / accept ── server nhận ── admission ── executor queue
                                                       │
                                                       ▼
                                               worker xử lý
                                                       │
                                                       ▼
                                         serialize/ghi response ── mạng ── client nhận
```

`response_latency` do client đo còn bao gồm network, middleware, admission, serialization, response write và nhiều tầng queue khác. Nếu chỉ đo `executor_task_total_time`, không được coi nó là toàn bộ response latency. Nếu bắt đầu đồng hồ **trước khi tác vụ thực sự vào queue**, phép đo còn bao gồm chi phí tạo wrapper, submit và chính sách admission; hãy đặt tên metric phản ánh đúng điểm bắt đầu.

## 2. Ví dụ ba tác vụ có cùng tổng thời gian nhưng nguyên nhân khác nhau

| Tình huống | `t_enqueue` | `t_start` | `t_finish` | Queue wait | Execution | Task total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A — xử lý I/O chậm, vào worker ngay | 0 ms | 5 ms | 805 ms | 5 ms | 800 ms | 805 ms |
| B — worker bận, logic nhanh | 0 ms | 770 ms | 805 ms | 770 ms | 35 ms | 805 ms |
| C — vừa chờ queue vừa chờ downstream | 0 ms | 400 ms | 805 ms | 400 ms | 405 ms | 805 ms |

Nếu dashboard chỉ hiển thị “805 ms/task”, ba tác vụ trông giống hệt nhau. Khi tách hai khoảng:

- **A:** tìm nguồn `execution_time` cao: socket read, file I/O, DB query, lock, blocking call hoặc CPU-bound work.
- **B:** code xử lý chỉ 35 ms; tìm nguyên nhân hàng đợi lâu: arrival burst, ít worker, tác vụ khác chiếm worker quá lâu hoặc backlog.
- **C:** cần xử lý **cả hai**: giảm áp lực queue và điều tra logic/downstream trong worker.

Cùng một người dùng có thể trải nghiệm p99 latency cao do queue dù **p99 execution** của các tác vụ vẫn thấp. Tối ưu một SQL query vốn chỉ 10 ms có thể không cải thiện đáng kể nếu request đã chờ 900 ms để được thực thi.

## 3. Queue wait nằm ở đâu trong Java `ThreadPoolExecutor`?

Với `ThreadPoolExecutor`, `execute()` nhận một `Runnable` và executor sẽ quyết định chạy ngay, tạo worker, hoặc đưa task vào `BlockingQueue`. Theo mô hình Java 17:

1. Nếu số worker đang chạy dưới `corePoolSize`, pool thường ưu tiên tạo worker để thực hiện task mới.
2. Khi đã đạt mức core, pool ưu tiên đưa task vào queue (nếu queue nhận được).
3. Khi queue không thể nhận, pool có thể tạo thêm worker đến `maximumPoolSize`; sau đó áp dụng `RejectedExecutionHandler`.
4. Với `SynchronousQueue`, đây là direct handoff; không có hàng chờ lưu tác vụ theo cách `ArrayBlockingQueue` hoạt động.

Vì vậy, **không có một queue wait dương bắt buộc cho mọi task**. Một task có thể bắt đầu gần ngay thời điểm submit, hoặc bị giữ hàng trăm ms. `maximumPoolSize` **không nhất thiết làm tăng thread** nếu queue unbounded luôn nhận được task. Ví dụ `Executors.newFixedThreadPool(n)` sử dụng queue không giới hạn theo thiết kế; backlog có thể tăng lâu trước khi có rejection.

| Cấu hình queue / policy | Hành vi thường thấy | Ý nghĩa khi đo |
| --- | --- | --- |
| `ArrayBlockingQueue(capacity)` | Có sức chứa cố định, khi đầy và pool không thể mở rộng sẽ reject hoặc dùng policy khác. | Có thể quan sát queue length + queue wait + rejected count. |
| `LinkedBlockingQueue` không giới hạn thực tế trong cấu hình dùng | Task có thể tích lũy lâu khi arrival rate vượt khả năng xử lý. | `queue wait` và heap/backlog có thể tăng; `maxPoolSize` không cứu được trong mô hình này. |
| `SynchronousQueue` | Handoff trực tiếp, không lưu backlog truyền thống. | Queue size thường không thể hiện áp lực; quan sát thread growth/rejection và submit latency. |
| `CallerRunsPolicy` | Khi không còn khả năng nhận task, **thread gọi** thực hiện task. | Queue wait của runnable có thể rất thấp nhưng **thời gian của caller** tăng; cần đo submit/admission latency. |
| `AbortPolicy` | Task bị từ chối bằng `RejectedExecutionException` khi không nhận được. | Task bị reject không có execution time; cần metric riêng. |

`getQueue().size()` cho snapshot độ dài queue tại lúc gọi và thay đổi liên tục; `getActiveCount()` và `getTaskCount()` là **ước lượng/quan sát tức thời**, không thay thế histogram **queue wait theo từng tác vụ**. Một queue size nhỏ không loại trừ p99 wait cao nếu lấy mẫu thưa, xử lý theo batch hoặc có các tầng queue ẩn.

## 4. Đo đúng với `System.nanoTime()`

Trong một JVM, `System.nanoTime()` là nguồn thời gian độ phân giải cao dành để đo **elapsed time**; nó có mốc gốc tùy ý, không phải Unix timestamp. Cách đúng:

```java
long queuedAt = System.nanoTime();

// submit/queue...

long startedAt = System.nanoTime();

// task work...

long finishedAt = System.nanoTime();

long queueWaitNs = startedAt - queuedAt;
long executionNs = finishedAt - startedAt;
long totalNs = finishedAt - queuedAt;
```

Đoạn trên là **minh họa trong cùng luồng công việc**, không phải chương trình chạy độc lập. Phải đặt `queuedAt` ngay ở phía submit và `startedAt` vào đầu wrapper chạy trong worker; nếu ghi cả hai trong `run()`, kết quả “queue wait” chỉ là vài instruction của cùng worker, hoàn toàn bỏ sót thời gian xếp hàng.

- Dùng **phép trừ** hai `nanoTime` cùng JVM. Không so trực tiếp giá trị `nanoTime` của hai JVM/container; mỗi JVM có mốc gốc tùy ý.
- Đơn vị nanosecond **không đồng nghĩa đồng hồ chính xác tới 1 ns**. Hệ điều hành, scheduler, độ phân giải clock và instrumentation đều tác động phép đo.
- Khi đổi sang mili-giây: `double ms = nanos / 1_000_000.0`. Nếu dùng phép chia nguyên hoặc `TimeUnit.NANOSECONDS.toMillis`, các phần nhỏ hơn 1 ms có thể bị làm tròn xuống.
- `Instant.now()`/`currentTimeMillis()` phù hợp để gắn **timestamp lịch** và đối chiếu log, nhưng có thể chịu clock adjustment. Trong cùng JVM, `nanoTime` phù hợp hơn để đo khoảng thời gian.
- Với trace qua nhiều service, sử dụng timestamp/clock được đồng bộ và ghi rõ sai số; không lấy `nanoTime` máy A trừ của máy B.

Để không làm lệch metrics khi có exception, đặt `finishedAt` trong `finally`; nếu tác vụ có nhiều đường return, không đo chỉ trên “happy path”.

## 5. Java 17+ — ví dụ hoàn chỉnh đo queue wait và execution

Ví dụ dưới đây tạo `ThreadPoolExecutor` có **một worker** và queue hữu hạn. Tác vụ thứ nhất giữ worker bằng một `CountDownLatch`. Trong lúc đó, tác vụ thứ hai đã được submit nhưng phải đợi; khi worker được thả, tác vụ thứ hai chạy khoảng 40 ms. Ví dụ dùng latch để tạo một khoảng queue wait có thể quan sát, không phải để giả lập I/O thực.

Lưu `QueueTimeDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class QueueTimeDemo {
    record Timing(long queuedNs, long startedNs, long finishedNs) {
        double queueWaitMs() {
            return (startedNs - queuedNs) / 1_000_000.0;
        }

        double executionMs() {
            return (finishedNs - startedNs) / 1_000_000.0;
        }

        double totalMs() {
            return (finishedNs - queuedNs) / 1_000_000.0;
        }
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(4));

        CountDownLatch workerOccupied = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);

        try {
            Future<?> blocker = pool.submit(() -> {
                workerOccupied.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            // Bảo đảm worker thứ nhất đã bắt đầu chạy.
            workerOccupied.await();

            // Mốc lấy ngay trước khi submit tác vụ thứ hai.
            long queuedAt = System.nanoTime();
            Future<Timing> measured = pool.submit(() -> {
                long startedAt = System.nanoTime();
                try {
                    Thread.sleep(40);
                } finally {
                    // Không giữ metric ở đây vì cần return sau try.
                }
                long finishedAt = System.nanoTime();
                return new Timing(queuedAt, startedAt, finishedAt);
            });

            // Giữ worker bận thêm khoảng 100 ms.
            Thread.sleep(100);
            releaseWorker.countDown();

            Timing t = measured.get();
            blocker.get();

            System.out.printf(
                    "queueWaitMs=%.1f executionMs=%.1f totalMs=%.1f%n",
                    t.queueWaitMs(), t.executionMs(), t.totalMs());
        } finally {
            releaseWorker.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac QueueTimeDemo.java
java QueueTimeDemo
```

**Output minh họa**, không phải stdout số học cố định:

```text
queueWaitMs=102.7 executionMs=40.3 totalMs=143.0
```

Các thời gian phụ thuộc JVM, scheduler và độ trễ thực tế của `sleep`; tổng ba số có thể lệch ở chữ số thập phân do làm tròn. Đẳng thức chính xác ở đơn vị nanosecond là `totalNs = queueWaitNs + executionNs`.

Trong code mẫu, `queuedAt` ghi **ngay trước `submit`**, do đó queue wait đo cả một phần overhead của lời gọi submit và dispatch. Nếu cần đo chính xác chỉ thời gian **cư trú trong queue**, phải có instrument tại lúc task thật sự được nhận vào queue và lúc được lấy ra; với những executor/queue khác nhau, boundary này có thể khác. Trong thực tế, timestamp trước `submit` vẫn là chỉ số có ích để đo “submission-to-start latency” nếu đặt tên rõ ràng.

Tác vụ `blocker` chỉ giữ worker để minh họa. Với service thật, task đầu có thể chiếm worker vì DB read, socket read, lock, CPU hoặc ngủ chờ retry. Người phân tích phải kiểm tra **vì sao worker bận**, chứ không chỉ tăng số worker một cách máy móc.

### Một biến thể an toàn hơn để bao phủ cả lỗi tác vụ

Ở hệ thống production, wrapper cần đo cả task thất bại. Cấu trúc hàm tổng quát:

```java
static Runnable timed(Runnable delegate, java.util.function.BiConsumer<Long, Long> sink) {
    long queuedAt = System.nanoTime();
    return () -> {
        long startedAt = System.nanoTime();
        try {
            delegate.run();
        } finally {
            long finishedAt = System.nanoTime();
            sink.accept(startedAt - queuedAt, finishedAt - startedAt);
        }
    };
}
```

Đây là **method minh họa**, không phải file độc lập; `sink` nhận `queueWaitNs`, `executionNs`. Cách này hoạt động khi task thực sự chạy. Với task bị cancel khi còn trong queue hoặc bị reject, callback sẽ không được gọi; phải bổ sung counter `rejected/cancelled/timed_out_before_start` ở tầng submit/admission.

Trong production, tránh để `sink` ném exception che mất lỗi gốc của `delegate`; metric sink nên nhẹ và có xử lý lỗi rõ ràng. Nếu cần đo thời gian “task từ khi bắt đầu đến khi thành công/thất bại”, lấy `finally` như trên để không bỏ các đuôi trễ nghiêm trọng vì exception.

## 6. Java 17+ — bài tập số liệu có stdout chính xác

Để kiểm tra công thức mà không phụ thuộc thread scheduling, hãy dùng các mốc thời gian **giả định**, không phải `System.nanoTime`. Lưu `LatencyMath.java`:

```java
public final class LatencyMath {
    public static void main(String[] args) {
        long enqueuedMs = 120;
        long startedMs = 610;
        long finishedMs = 650;

        long waitMs = startedMs - enqueuedMs;
        long executionMs = finishedMs - startedMs;
        long totalMs = finishedMs - enqueuedMs;

        System.out.printf("queue=%dms execution=%dms total=%dms%n",
                waitMs, executionMs, totalMs);
    }
}
```

Chạy:

```bash
javac LatencyMath.java
java LatencyMath
```

**Stdout chính xác:**

```text
queue=490ms execution=40ms total=530ms
```

Phép tính cho thấy tác vụ mất 530 ms nhưng chỉ thực thi 40 ms; tối ưu 5 ms trong code xử lý sẽ ít tác động nếu backlog vẫn giữ task gần nửa giây. Trong phép đo thật, ba mốc phải là khoảng thời gian tương đối cùng gốc; ví dụ này chỉ biểu diễn logic cộng/trừ.

## 7. Với I/O, “execution time” vẫn có thể chủ yếu là chờ

Đây là điểm dễ nhầm: khi một `Runnable` gọi `InputStream.read()` và thread bị block 500 ms, toàn bộ 500 ms vẫn nằm giữa `t_start` và `t_finish`. Nghĩa là **processing/execution wall time** có thể cao dù CPU thực dùng rất thấp.

Ví dụ một task truy vấn database:

```text
t_enqueue → (chờ executor 120 ms) → t_start
    → (đợi connection pool 60 ms)
    → (SQL query / network round-trip 380 ms)
    → (map kết quả 20 ms)
    → t_finish
```

Khi đó:

- Executor queue wait = **120 ms**.
- Execution wall time = `60 + 380 + 20 = 460 ms`.
- Task total = **580 ms**.
- “CPU xử lý dữ liệu” trong ví dụ chỉ được minh họa bằng đoạn map 20 ms, nhưng bản thân đoạn map cũng có thể có scheduling/GC và không nhất thiết tương đương CPU time.

**Có nhiều hàng đợi lồng nhau**: executor queue, database connection pool queue, upstream message broker, servlet accept queue, HTTP client connection pool, network device queue, và hệ điều hành chờ disk. Chỉ đo một tầng sẽ bỏ sót các tầng khác.

| Điểm chờ | Nằm ở đâu trong phép đo trên | Metric cần có |
| --- | --- | --- |
| Request đợi được accept hoặc được admission | Có thể **trước** `t_enqueue`. | ingress/accept/admission latency, pending requests. |
| Task nằm trong `ThreadPoolExecutor` queue | `t_enqueue → t_start`. | `executor_queue_wait`, queue depth, active workers. |
| Worker đợi lấy DB connection | **Bên trong** `execution_time` của task. | `db_pool_acquire_wait`, active/idle/pending connections. |
| Worker đợi socket read/file read | **Bên trong** `execution_time` nếu I/O đồng bộ. | `socket_read_duration`, `file_read_duration`, timeout/bytes. |
| Worker đợi lock hoặc condition | **Bên trong** `execution_time`. | lock wait/thread state/JFR contention event. |
| Response đợi socket writable hoặc được gửi đi | Có thể **sau** `t_finish` tùy boundary. | response write time, client RTT, network wait. |

Nếu đang dùng API **bất đồng bộ** (`CompletableFuture`, NIO, reactive pipeline), `Runnable.run()` có thể chỉ đăng ký I/O rồi kết thúc trong vài microsecond. Khi đó thời gian từ nhận request đến **future hoàn thành** mới là logical operation latency; không được lấy thời gian chạy callback đầu tiên làm toàn bộ xử lý nghiệp vụ. Cần đặt mốc riêng cho lúc gọi I/O, nhận completion, scheduler queue cho callback và khi tạo response.

## 8. Phân biệt latency do queue với latency do service

| Quan sát | Giả thuyết ưu tiên | Bằng chứng kiểm tra |
| --- | --- | --- |
| `queue_wait_p95` tăng; `execution_p95` tương đối ổn định | Executor bị backlog/saturation hoặc burst arrival. | Active threads gần giới hạn, queue depth/oldest age tăng, rejection/timeout. |
| `queue_wait` thấp; `execution` tăng cùng lúc DB latency | I/O/downstream chậm khi task đã bắt đầu. | DB query duration, pool acquire wait, socket wait, JFR I/O events. |
| `queue_wait` tăng sau khi `execution` tăng | Work chậm chiếm worker lâu làm hàng đợi tích lũy. | Timeline: service time tăng trước; queue tăng sau; thread dump cho biết worker làm gì. |
| `execution` thấp; client latency vẫn cao | Mất thời gian trước enqueue hoặc sau finish, hoặc tầng async khác. | HTTP receive/dispatch/write timestamps, network, callback enqueue. |
| Queue depth gần 0 nhưng reject tăng | Direct handoff/SynchronousQueue hoặc admission limit, capacity/policy. | Cấu hình queue, active threads, `RejectedExecutionException`, rate limiter. |
| Queue depth lớn, waiting cao, CPU thấp | Worker blocked I/O/lock hoặc downstream giới hạn concurrency. | Thread states, DB pool pending, JFR SocketRead/ThreadPark, lock events. |
| Queue wait thay đổi mạnh khi số worker tăng | Capacity/parallelism ảnh hưởng backlog. | So throughput/p95/error theo cùng workload; cảnh giác downstream quá tải. |
| Một số tác vụ đợi rất lâu, số khác bắt đầu ngay | Queue discipline, priority, long-running jobs hoặc starvation. | Tách theo loại task/priority; xem FIFO, scheduled delays và worker distribution. |

**Không tự động tăng thread pool khi thấy queue wait cao.** Nếu mọi worker đang đợi database vốn chỉ cho phép 20 connection, tăng worker từ 50 lên 200 có thể làm contention, memory và context switch xấu hơn. Nếu tác vụ CPU-bound và core đã sử dụng hết, nhiều thread cũng có thể tăng thời gian chuyển ngữ cảnh. Chọn can thiệp dựa trên nút thắt đã đo được.

## 9. Các chỉ số nên phát ra từ executor và I/O pipeline

Để vận hành, dùng ba nhóm telemetry:

**Histogram latency theo từng tác vụ:**

- `task_queue_wait_seconds`: submission/admission-to-start theo định nghĩa.
- `task_execution_seconds`: start-to-finish wall time, gồm blocking.
- `task_total_seconds`: submission-to-finish.
- `task_timeout_before_start_total` và `task_rejected_total`: tác vụ chưa từng bắt đầu.
- Nếu cần, thêm `db_connection_acquire_seconds`, `io_read_seconds`, `lock_wait_seconds`.

**Gauge tại thời điểm lấy mẫu:**

- `executor_active_threads`, `executor_pool_size`, `executor_max_threads`.
- `executor_queue_depth`, `executor_queue_capacity`, **tuổi task lâu nhất đang chờ** nếu có thể đo an toàn.
- `db_pool_pending` / `db_pool_active`, số connection và giới hạn.

**Counter và event correlation:**

- Submitted, started, completed, failed, cancelled, rejected và timed out theo trạng thái độc lập.
- Request rate, task type, worker pool name, release version, deployment instance.
- Trace ID/correlation ID để nối từ ingress → queue → start → downstream calls → completion.

Đặt **đơn vị một cách nhất quán**: exporter thường dùng giây, trong code tính ns; `duration_seconds` không nên chứa giá trị mili-giây. Gắn nhãn có cardinality hữu hạn như pool name, task category, result; không dùng raw request ID, user ID hay URL đầy đủ làm label của từng time series.

**Phân vị** `p50/p95/p99` cần đủ số mẫu và cửa sổ thời gian rõ ràng. Ví dụ 1 phút chỉ có 3 task thì một số `p99` rất thiếu ổn định. Dùng histogram phù hợp để tổng hợp qua instance; không lấy trung bình các p95 trên từng instance như p95 toàn cụm.

### Một bẫy toán học quan trọng: p95 không cộng được

Với **mỗi task**: `total = queue + execution`. Nhưng nói chung:

```text
p95(task_total) ≠ p95(task_queue_wait) + p95(task_execution)
```

Bởi các task có queue wait cao chưa chắc là các task có execution cao, và quantile không có tính tuyến tính. Muốn biết p95 total, đo hoặc tính **tổng theo từng task rồi xây histogram của total**, không cộng các p95 trên dashboard.

Tương tự, nếu số task chưa bắt đầu bị timeout/reject, percentile trên **các task đã hoàn thành** có thể trông “rất tốt” trong khi người dùng vẫn bị lỗi. Luôn hiển thị rejection, timeout, cancellation cùng latency.

## 10. Phân tích tải bằng tốc độ đến và năng lực xử lý

Để hiểu vì sao queue tăng, tách:

- `λ` (lambda): số task **đến** trung bình mỗi giây.
- `E[S]`: execution wall time trung bình mỗi task, tính bằng giây.
- `k`: số worker có thể thực hiện song song tác vụ (nếu mô hình worker pool đồng nhất).
- `ρ ≈ λ × E[S] / k`: mức sử dụng tương đối trong mô hình đơn giản, khi mỗi task chiếm một worker trong suốt `S` và hệ thống gần trạng thái ổn định.

Ví dụ: 40 task/s, trung bình task chiếm worker 0,2 s, có 10 worker ⇒ `ρ ≈ 40 × 0,2 / 10 = 0,8` (80%). Nếu arrivals tăng lên 55 task/s trong khi execution vẫn 0,2 s, nhu cầu trung bình là 11 worker và vượt capacity 10 worker; queue sẽ có xu hướng tăng hoặc hệ thống phải reject/điều chỉnh theo policy.

**Đây là mô hình gần đúng**, không bảo đảm p95 latency. Arrival burst, phân bố service time, priority, worker affinity, các tài nguyên downstream, timeouts và autoscaling có thể làm queue tăng cả khi mức sử dụng trung bình chưa tới 100%. Nếu service time tăng vì I/O blocked, `ρ` cũng tăng dù CPU hệ thống có thể còn nhàn.

### Little's Law, khi dùng đúng ranh giới

Ở một hệ thống ổn định với tốc độ đến/ra phù hợp, **Little's Law** cho quan hệ:

```text
L = λ × W
```

Nếu xét **chỉ hàng đợi**: `Lq = λ × Wq`, với `Lq` là **số task trung bình đang chờ**, `Wq` là **thời gian chờ trung bình**, `λ` là throughput dài hạn qua cùng ranh giới (đơn vị task/s). Ví dụ giả định `λ=40 task/s` và `Wq=0,25 s` ⇒ `Lq≈10 task`.

Không dùng `queueDepth_now ≈ rate_now × p95_wait`: Little's Law mô tả **giá trị trung bình dài hạn** khi điều kiện áp dụng phù hợp, không phải sự bằng nhau giữa một gauge tức thời và p95. Trong burst hoặc giai đoạn queue tăng vô hạn, giả định trạng thái ổn định không còn đúng.

## 11. JFR và thread dump hỗ trợ phân biệt ra sao?

JFR có thể cho biết **worker đang làm gì trong thời gian đã bắt đầu xử lý**. Một số nhóm event hữu ích (tùy settings/threshold/collector/JDK):

- `jdk.SocketRead` / `jdk.SocketWrite`: thời gian thực thi một thao tác I/O socket được JFR ghi nhận; chỉ những event thỏa cấu hình được thu.
- `jdk.FileRead` / `jdk.FileWrite`: thao tác I/O file có duration và dữ liệu liên quan.
- `jdk.JavaMonitorEnter`: dấu hiệu tranh chấp monitor, thường chỉ có event khi chờ vượt threshold.
- `jdk.ThreadPark`: khoảng park/chờ trong cơ chế `LockSupport`, có thể gợi ý wait trên synchronizer.
- CPU execution samples và stack trace: định hướng worker đang tiêu thụ CPU ở đâu.

Ví dụ bật recording ngắn trên HotSpot JDK 17+:

```bash
# Thay <pid> bằng PID thực, xác minh quyền ghi ở JVM đích.
jcmd <pid> JFR.start name=queue_diag settings=profile duration=120s filename=/tmp/queue-diag.jfr

# Sau khi file đã được ghi:
jfr summary /tmp/queue-diag.jfr
jfr print --events jdk.SocketRead,jdk.FileRead,jdk.ThreadPark /tmp/queue-diag.jfr
```

Output các công cụ phụ thuộc file thực tế, **không có bảng số liệu cố định**. `jdk.SocketRead` kéo dài 400 ms gợi ý một đoạn chờ I/O trong worker, nhưng **không cho biết tác vụ đã chờ bao lâu trong queue trước khi worker chạy**. JFR mặc định không tự biết `t_enqueue` của mọi `Runnable` nghiệp vụ. Muốn đo queue wait, cần **instrument chính ranh giới submit/start** như ví dụ.

Thread dump (`jcmd <pid> Thread.print` hoặc `jstack` khi được hỗ trợ) là snapshot trạng thái stack; một worker `WAITING` hay `TIMED_WAITING` có thể đang đợi I/O/synchronizer hoặc đang nhàn rỗi chờ task mới. Không kết luận từ một thread dump đơn lẻ rằng “mọi request đều đợi queue”; cần gắn stack với metric queue và timestamp.

### Ghi dấu queue/execution bằng custom JFR event

Khi cần correlate từng task mà không muốn log text cho mọi request, có thể tạo một custom JFR event với fields `queueWaitNanos`, `executionNanos`, task category và outcome. Đo trong wrapper, ghi event sau khi tác vụ kết thúc, và chọn threshold/sampling phù hợp để hạn chế overhead.

Ví dụ **phần class event**, không phải chương trình hoàn chỉnh:

```java
@jdk.jfr.Name("demo.TaskLatency")
@jdk.jfr.Label("Task latency")
@jdk.jfr.Category({"Application", "Executor"})
public class TaskLatencyEvent extends jdk.jfr.Event {
    @jdk.jfr.Label("Queue wait nanos")
    public long queueWaitNanos;

    @jdk.jfr.Label("Execution nanos")
    public long executionNanos;

    @jdk.jfr.Label("Task category")
    public String category;
}
```

Trong đoạn wrapper đo thực tế, set các field rồi gọi `commit()` khi event enabled. Không kỳ vọng custom event tự động có sẵn trong file `.jfr` nếu chưa bật `demo.TaskLatency`. Không gắn payload nhạy cảm hoặc request ID tùy ý vào JFR event, vì recording có thể lưu trên đĩa và được chia sẻ để điều tra.

## 12. I/O bất đồng bộ và message broker: đừng đặt ranh giới sai

### 12.1. HTTP async/reactive pipeline

Một HTTP handler gửi yêu cầu sang API bất đồng bộ có thể kết thúc callback sớm, còn `CompletableFuture` tiếp tục chờ kết quả mạng. Để không tính sai “processing”, chọn rõ hai metric:

- `callback_execution_seconds`: wall time của một callback cụ thể từ lúc worker chạy đến khi callback return.
- `logical_operation_duration_seconds`: từ lúc request được chấp nhận đến lúc **future hoàn thành/kết quả sẵn sàng**.

Có thể xuất thêm `callback_scheduler_queue_wait_seconds` nếu completion callback phải đợi executor khác. Nếu chỉ đo callback đầu tiên, dashboard có thể báo 2 ms dù người dùng chờ 900 ms.

### 12.2. Message queue/broker

Trong Kafka/RabbitMQ/JMS, có nhiều mốc:

```text
producer tạo message
 → gửi broker
 → broker lưu/đợi
 → consumer nhận/poll
 → consumer local executor queue
 → handler bắt đầu
 → xử lý
 → ack/commit
```

**Broker queue age** là khoảng từ lúc message được ghi vào broker đến khi consumer lấy ra (theo định nghĩa cụ thể). **Local executor wait** là từ lúc consumer giao task cho executor đến handler bắt đầu. **Handler duration** là từ handler bắt đầu đến khi xử lý xong. **Ack latency** có thể thêm một khoảng sau đó. Chúng là các metric khác nhau, không nên cùng đặt tên `message_processing_time`.

Với các timestamp thuộc hai máy, chú ý clock skew, broker timestamp semantics (create time vs append time), batching và redelivery. Nếu message được xử lý lại, cần xác định thời điểm đo là từ lần enqueue đầu tiên hay lần retry hiện tại; không gộp vô điều kiện.

### 12.3. Batch job và scheduled task

Một scheduled task có `plannedAt`, `eligibleAt`, `actualStartAt`, `finishedAt`. Nếu scheduler hoặc worker bị bận, `actualStartAt - plannedAt` là **schedule delay**, chưa chắc hoàn toàn là queue wait trong executor. Một batch 1.000 bản ghi có thể chờ đưa vào queue từng phần rồi chạy song song; cần xác định đơn vị đo là **batch** hay **mỗi item** để tỷ lệ và duration có ý nghĩa.

## 13. Phân biệt ba vấn đề trong một incident

### Case A — queue wait cao, execution thấp

Một service nhận 500 request/s trong burst; worker pool 16 thread đang bận, queue depth tăng. Metric:

```text
queue_wait_p95 = 650 ms
execution_p95  = 40 ms
task_total_p95 = 675 ms
rejections     = 0
```

Các số minh họa chỉ để mô tả. `task_total_p95` **không được tính** bằng cách cộng 650 + 40; nó được đo độc lập theo từng task. Hành động là xem arrival burst, capacity và task mix, xem có một số task lâu giữ worker không, đặt queue bound và deadline hợp lý. Nếu CPU thấp nhưng worker đang chặn network thì quay lại xét Case B như nguyên nhân gốc của backlog.

### Case B — queue wait thấp, execution cao

`queue_wait_p95 = 4 ms`, `execution_p95 = 820 ms`, DB connection acquire time `~300 ms`, socket read `~400 ms`. Mở rộng worker pool có thể **tệ hơn** nếu DB connection pool đã chật. Cần điều tra DB load, timeout, query plan, connection pool và downstream dependency; xem mốc nào tăng trước.

### Case C — cả hai tăng theo thời gian

Tại 10:00 upstream database latency tăng, khiến mỗi task giữ worker lâu hơn. Tới 10:02, executor queue depth và queue wait tăng mạnh vì worker chưa trả lại. Dashboard cho thấy tổng latency tăng, nhưng chuỗi sự kiện cho biết **execution tăng trước, queue tăng sau**. Giải pháp nên hướng vào upstream và giới hạn concurrency/backpressure; chỉ làm queue lớn hơn sẽ kéo dài thời gian chờ và tiêu thụ tài nguyên.

## 14. Những lỗi phổ biến khi đo và diễn giải

- **“Task chạy 20 ms nên response chắc chỉ 20 ms.”** Sai: queue wait, network, admission, serialization và callback async có thể cộng thêm đáng kể.
- **“Execution time chính là CPU time.”** Sai: wall time trong `run()` gồm I/O blocked, lock wait, GC pause và scheduler delay.
- **“Queue wait bằng `queue.size()`.”** Sai: size là số lượng, wait là khoảng thời gian; cần đo theo từng task.
- **“Lấy `nanoTime()` đầu `run()` và cuối `run()` là đủ để đo queue wait.”** Sai: đó chỉ đo execution.
- **“Timestamp ISO giữa hai JVM luôn trừ được chính xác.”** Sai: clock skew và clock adjustment làm sai lệch; ghi bối cảnh đồng bộ clock.
- **“Tăng worker luôn giảm queue wait.”** Sai: có thể đẩy nhiều I/O tới downstream, làm tăng contention và execution time.
- **“Queue size bằng 0 nghĩa không có áp lực.”** Sai: SynchronousQueue, sampling thưa và rejection có thể che tình trạng admission overload.
- **“Executor maxPoolSize sẽ được dùng hết trước khi queue.”** Sai: hành vi phụ thuộc core size, queue và saturation.
- **“`CallerRunsPolicy` nghĩa là mọi tác vụ luôn được worker pool xử lý.”** Sai: caller phải chạy task; ảnh hưởng latency submit và upstream.
- **“p95 tổng bằng p95 chờ + p95 chạy.”** Sai: quantile không có tính cộng; cần đo tổng từng task.
- **“Task bị cancel trong queue có execution 0 ms nên đưa vào histogram thành công.”** Sai: tách trạng thái không bao giờ bắt đầu, report timeout/cancel riêng.
- **“JFR FileRead 600 ms là queue wait 600 ms.”** Sai: duration event I/O xảy ra **trong quá trình chạy**; queue submit-to-start cần instrument riêng.
- **“Async callback return là request đã xong.”** Sai: phải theo dõi completion của toàn logical operation.
- **“Một lần `getActiveCount()` thấp thì pool không bị nghẽn.”** Sai: snapshot có thể lệch giai đoạn burst, cần time series/histogram.
- **“P99 tăng là do SQL chậm.”** Chưa đủ: phải xem queue_wait, execution, DB acquire, socket read và downstream trace cùng cửa sổ.
- **“Little's Law áp dụng trực tiếp cho queue depth tức thời và p95.”** Sai: đây là quan hệ giá trị trung bình với điều kiện áp dụng rõ ràng.

## 15. Checklist điều tra thực tế

Trước khi sửa mã hoặc tuning thread pool, trả lời:

1. **Ranh giới:** đang đo executor queue wait, DB connection wait, broker lag hay toàn request latency? Các mốc `enqueue/start/finish` ở đâu?
2. **Đồng hồ:** timestamp trong cùng JVM bằng `nanoTime` hay qua nhiều máy? Đơn vị và sai số là gì?
3. **Phân phối:** `p50/p95/p99` của **queue wait**, **execution**, **total** thay đổi độc lập thế nào? Còn rejected/timeout/cancelled?
4. **Queue:** loại queue, capacity, `corePoolSize`, `maximumPoolSize`, rejection handler và oldest wait là gì?
5. **Worker:** active/idle, thread states, CPU usage và backlog có diễn biến trùng nhau không?
6. **I/O:** DB pool acquire, query, socket/file I/O, lock wait, timeout và downstream latency tác động phần execution nào?
7. **Async:** nếu dùng callback/reactive, logical operation đã hoàn tất chưa hay chỉ có một callback vừa return?
8. **Thứ tự nguyên nhân:** execution tăng trước dẫn tới queue tăng, hay burst arrival làm queue tăng dù execution vẫn ổn định?
9. **Giải pháp:** đo lại cùng workload sau thay đổi concurrency, queue bound, backpressure, timeout hoặc tối ưu I/O; kiểm tra cả latency lẫn error/reject.
10. **Báo cáo:** nêu rõ instance, cửa sổ, số mẫu, đơn vị, công thức và metric boundary để người khác tái hiện.

**Ghi nhớ:** `queue_wait` trả lời **“task phải đợi bao lâu trước khi được worker bắt đầu?”**; `execution_time` trả lời **“worker giữ task trong bao lâu, kể cả lúc bị block?”**; `total_time` của task là **tổng hai phần theo từng task**, còn response latency có thể dài hơn. Việc đo riêng hai khoảng — cùng queue depth, rejection và I/O telemetry — giúp tránh tối ưu sai chỗ và tìm được nguyên nhân thật của độ trễ.

### Tài liệu tham khảo

- [Oracle Java 17 — ThreadPoolExecutor (queueing, pool size, rejection, monitoring)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Oracle Java 17 — System.nanoTime()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime())
- [Oracle Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Oracle Java 17 — ThreadMXBean (CPU time khác wall time)](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Oracle Java 17 — Java Flight Recorder Consumer APIs](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html)
- [OpenTelemetry — Messaging semantic conventions](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/)