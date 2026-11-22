# 9.9 Kiểm chứng tiến triển sau sửa lỗi bằng số thao tác hoàn thành và thời gian chờ

## Mục tiêu học tập

Sửa lỗi deadlock, livelock, starvation hoặc một thao tác chờ quá lâu **không kết thúc ở chỗ ứng dụng hết báo lỗi, thread dump trông “đẹp hơn”, hay process khởi động lại thành công**. Câu hỏi cuối cùng là: **công việc có thực sự tiến triển trở lại, đúng thời hạn và dưới tải tương đương hay không?**

Một luồng có thể ở trạng thái `RUNNABLE` nhưng chỉ retry mà không hoàn tất giao dịch. CPU có thể giảm sau một thay đổi nhưng hàng đợi vẫn dài dần. Thread dump không còn chu trình monitor deadlock nhưng service vẫn chờ database. Vì vậy cần đo **thao tác đã hoàn thành**, **thời gian chờ** và **tác động trên toàn đường xử lý**, so sánh trước–sau một cách có kiểm soát.

Sau bài học, bạn có thể:

1. Định nghĩa “progress hữu ích” bằng terminal business outcomes: succeeded, failed, timed out, cancelled; không nhầm attempts, accepted, started với completed.
2. Tạo các bộ đếm tích lũy, tính **delta/completion rate**, success throughput, error rate và phát hiện counter reset.
3. Đo **queue wait**, **lock acquisition wait**, **dependency wait**, **total operation latency**, **oldest queued/in-flight age** bằng mốc thời gian và đơn vị đúng.
4. Phân tích p50/p95/p99 cùng sample count, phân biệt trung bình với tail, tránh nhầm `ThreadInfo.getBlockedTime()` thành toàn bộ thời gian chờ nghiệp vụ.
5. Thiết kế phép so sánh trước–sau ở **cùng tải, cùng cửa sổ, cùng định nghĩa**, có warm-up, baseline, repeat runs, guardrails và giới hạn kết luận.
6. Chạy ví dụ **Java 17+ độc lập** với chế độ fixture cho stdout cố định và chế độ mô phỏng một executor có queue để thấy counters/queue wait thực.
7. Thiết lập tiêu chí PASS/FAIL cho sửa lỗi deadlock, livelock, starvation, long wait, bao gồm phát hiện hồi quy trong production.
8. Viết báo cáo kỹ thuật rõ đã quan sát gì, chỉ là giả thuyết gì và bước kiểm chứng tiếp theo.

---

## 1. “Tiến triển” không đồng nghĩa “hoạt động”

Giả sử một Java service có hai thay đổi sau sửa lỗi:

- Trước sửa: CPU ở 95%, retry 10.000 lần/phút, completed business orders bằng 0.
- Sau sửa: CPU còn 30%, retry 100 lần/phút, completed orders tăng thành 200/phút.

Tín hiệu thứ hai tốt hơn **về tiến độ hữu ích**, nhưng vẫn cần xem latency, failure rate, queue và tải có giống nhau không. Nếu sau sửa chỉ có 1/10 lưu lượng, completed orders giảm hay CPU giảm **không tự chứng minh** cải thiện.

Một ví dụ khác: sau khi restart, `ThreadMXBean.findDeadlockedThreads()` trả `null` và request đầu tiên thành công. Điều này xác nhận snapshot mới không phát hiện lock cycle, nhưng **chưa chứng minh** nguyên nhân gốc đã bị loại bỏ: thread ordering lỗi có thể tái xuất hiện sau hàng giờ đồng thời cao.

**Định nghĩa thực dụng:** Một hệ thống có progress nếu các đơn vị công việc được nhận/đủ điều kiện xử lý chuyển thành **trạng thái kết thúc có thể kiểm chứng**, với tỷ lệ và thời gian phù hợp SLO và độ lớn hàng đợi không tăng vô hạn ở mức tải đã thỏa thuận.

### 1.1 Những mốc vòng đời cần tách bạch

```text
RECEIVED / OFFERED
      |
      v
ACCEPTED INTO SYSTEM ----- REJECTED
      |
      v
QUEUED / PENDING
      |
      v
STARTED / IN_FLIGHT
      |
      v
SUCCESS | FAILED | TIMED_OUT | CANCELLED
```

Không phải mọi dịch vụ đều dùng đúng sơ đồ này; có thể có retry, dead-letter queue, ack/requeue, transaction rollback, deduplication và trạng thái chưa biết. Hãy chọn một mô hình vòng đời **phù hợp nghiệp vụ** rồi định nghĩa từng metric bằng sự kiện thực.

Ví dụ:

- `accepted_total`: số yêu cầu được hệ thống **chấp nhận** theo một quyết định rõ ràng.
- `started_total`: số yêu cầu đã bắt đầu thực thi; không phải nhận vào queue.
- `completed_total`: số yêu cầu đã đạt terminal outcome (trong phạm vi đã định).
- `succeeded_total`: số yêu cầu đã hoàn tất **thành công về nghiệp vụ**.
- `failed_total`: số yêu cầu kết thúc thất bại; có thể tách timeout/cancel theo chính sách.
- `retried_total`: số lần thử lại; **không** tự biểu thị số yêu cầu duy nhất đã hoàn tất.
- `in_flight`: gauge số đơn vị công việc đã bắt đầu, chưa kết thúc.
- `queue_depth`: gauge số đơn vị đang chờ chưa bắt đầu.
- `oldest_queued_age_ms`: tuổi của phần tử cũ nhất tại thời điểm quan sát.

Nếu một job được retry ba lần rồi success, business outcome có thể là **1 success**, trong khi attempts là 4; đừng trộn hai cấp đo.

## 2. Bộ chỉ số tối thiểu để xác nhận sửa lỗi

| Chỉ số | Loại | Ý nghĩa | Cảnh báo khi dùng |
| --- | --- | --- | --- |
| `completed_total` | Counter `long` | Số công việc đạt terminal outcome từ lúc instance start | Bao gồm cả thất bại nếu hợp đồng quy định |
| `succeeded_total` | Counter `long` | Progress hữu ích đã commit/ack thành công | Không cộng trùng retry |
| `failed_total` | Counter `long` | Công việc kết thúc lỗi | Lỗi không tự chứng minh đã xử lý an toàn |
| `accepted_total` | Counter `long` | Lưu lượng được chấp nhận | Không phải completed |
| `retry_attempts_total` | Counter `long` | Hoạt động thử lại | Có thể tăng khi progress bằng 0 |
| `queue_depth` | Gauge `long/int` | Số phần tử chờ hiện tại | Một snapshot có thể thiếu transient spikes |
| `in_flight` | Gauge `long/int` | Số công việc đang chạy chưa kết thúc | Có thể cao vì dependency chậm |
| `oldest_queued_age_ms` | Gauge `long` | Công việc chờ lâu nhất | Rất có ích để phát hiện starvation |
| `queue_wait_ms` | Distribution | Từ accepted/enqueued tới start | Không bao gồm service time |
| `lock_wait_ms` | Distribution | Từ bắt đầu yêu cầu lock tới giành được lock | Không phải thời gian **giữ** khóa |
| `dependency_wait_ms` | Distribution | Chờ DB/RPC/HTTP hoặc tín hiệu cụ thể | Phải ghi loại dependency và timeout |
| `end_to_end_latency_ms` | Distribution | Từ ranh giới đầu đến terminal outcome | Cần ghi có gồm thời gian queue không |
| `deadline_exceeded_total` | Counter `long` | Operation quá thời hạn đã định | Timeout caller không đảm bảo remote work đã dừng |

Không nhất thiết xuất mọi metric ngay lập tức. Chọn **ít nhưng đủ để trả lời câu hỏi**. Ví dụ nếu sửa lỗi một queue không tiến triển, completed/succeeded rate và oldest queue age là cốt lõi; thread count/CPU chỉ là chứng cứ phụ trợ.

### 2.1 Counter và gauge khác nhau

Counter thường tăng trong vòng đời instance; gauge có thể tăng/giảm:

```text
Time       completed_total  queue_depth  in_flight
T1                1000           60         8
T2                1040           80         8
T3                1120           30         5
```

`completed_total` tăng 40 rồi tăng 80; `queue_depth` lúc đầu **tăng**, sau **giảm**; `in_flight` không nhất thiết tương quan tuyến tính với số hoàn tất. Cần thêm received/accepted và elapsed time mới biết tốc độ xử lý có bắt kịp offered load không.

Đối với JVM restart, counter có thể reset về 0: không lấy `completed(T2)-completed(T1)` xuyên qua hai process làm số âm rồi báo “tiến độ đảo ngược”. Gắn `process_start_time`, instance ID/pod, build và timestamp.

### 2.2 Chỉ đếm tasks “đã chạy xong” chưa chắc phản ánh nghiệp vụ

`ThreadPoolExecutor.getCompletedTaskCount()` theo Javadoc Java 17 là **số tác vụ đã hoàn tất thực thi mà executor ước lượng**, không phải “đơn hàng giao thành công”, và trong khi workers thay đổi thì kết quả là **xấp xỉ**. Một `FutureTask` có thể chứa exception nhưng task vẫn hoàn tất ở góc nhìn executor.

Vì thế, khi xác nhận sửa lỗi:
- Dùng executor metrics cho **công suất và trạng thái pool**.
- Dùng **business counters** ở thời điểm commit/ack/terminal event để chứng minh tiến độ đúng nghĩa.
- Đối chiếu `Future.get()`/exceptional completion, retry, transaction outcome và idempotency để không đếm thất bại là thành công.

## 3. Công thức completion rate và progress rate

Cho hai mẫu trên **cùng instance**, không reset counter, tại thời điểm `T1`, `T2`:

```text
elapsedSeconds = (monotonicTimeT2 - monotonicTimeT1) / 1e9

completedDelta = completedTotal(T2) - completedTotal(T1)
successDelta   = succeededTotal(T2) - succeededTotal(T1)
failureDelta   = failedTotal(T2) - failedTotal(T1)

completionRate = completedDelta / elapsedSeconds
successRate    = successDelta / elapsedSeconds
failureRate    = failureDelta / elapsedSeconds
```

Đơn vị các rate là **operations/second**. `completionRate` trả lời “bao nhiêu operation đi tới trạng thái kết thúc mỗi giây”; `successRate` trả lời “bao nhiêu operation thực sự thành công mỗi giây”.

**Cần cả hai.** Nếu một bản sửa thay xử lý có lỗi bằng việc trả thất bại cực nhanh, `completionRate` có thể tăng đáng kể trong khi `successRate` không cải thiện. Sửa lỗi tiến triển hữu ích phải giữ đúng ý nghĩa và tiêu chí thành công.

### 3.1 Một ví dụ định lượng trước–sau

Giả định hai cửa sổ **30 giây**, offered/accepted load trong mỗi cửa sổ đều **240 yêu cầu**, cùng phần cứng, build khác nhau theo đúng một sửa lỗi:

| Metric trên cửa sổ 30s | Trước | Sau |
| --- | ---: | ---: |
| Accepted | 240 | 240 |
| Completed terminal outcomes | 60 | 240 |
| Succeeded | 57 | 237 |
| Failed | 3 | 3 |
| Completion rate | 2,00/s | 8,00/s |
| Success rate | 1,90/s | 7,90/s |
| p95 queue wait | 1.200 ms | 90 ms |
| Accepted trừ completed trong cửa sổ | 180 | 0 |

Công thức:

```text
completionRateGain = 8.00 / 2.00 = 4.00 lần

p95WaitReduction =
    (1200 ms - 90 ms) / 1200 ms * 100 = 92.50%
```

Các con số này là **fixture giả định**, không phải dữ liệu từ production. Chúng gợi ý dịch vụ sau sửa hoàn tất được nhiều operation hơn và giảm tail queue wait. **Chưa** đủ kết luận nhân quả tuyệt đối vì còn phải đối chiếu điều kiện tải, kiểu request, dữ liệu, cache, warm-up, số lần đo và các guardrails về correctness.

**Một nuance quan trọng:** `acceptedDelta - completedDelta = 180` biểu thị sự chênh lệch dòng vào/ra trong cửa sổ, **không tự động bằng queue depth cuối cửa sổ**. Một số operation có thể đang in-flight, queue đầu kỳ không bằng 0, có huỷ/retry/requeue, hoặc snapshots không nguyên tử. Chỉ khi đã có mô hình cân bằng trạng thái đầy đủ mới suy được backlog cụ thể.

### 3.2 Công thức tỷ lệ lỗi của một cửa sổ

```text
windowFailureFraction =
    failureDelta / completedDelta
```

Chỉ tính khi `completedDelta > 0`, cùng mẫu số/định nghĩa và không reset. Trong fixture:

- Trước: 3 / 60 = **5%** terminal outcomes thất bại.
- Sau: 3 / 240 = **1,25%** terminal outcomes thất bại.

Số thất bại tuyệt đối **không thay đổi**; fraction giảm một phần vì mẫu số completed tăng. Không tuyên bố đã xử lý nguyên nhân lỗi nghiệp vụ chỉ vì fraction nhỏ hơn, đặc biệt khi tập request/độ khó có thể đã thay đổi.

## 4. Đo thời gian chờ ở đúng ranh giới

“Wait time” không phải một số duy nhất. Trong một quy trình xử lý:

```text
accepted
  |--- queue wait ---|
                     started
                       |--- lock acquisition wait ---|
                                                         lock acquired
                       |----------- service time ----------------|
                                                                   terminal outcome

accepted |---------------- end-to-end latency -------------------> terminal outcome
```

**Tách ranh giới trước khi đo:**

| Thành phần | Bắt đầu | Kết thúc | Ngữ nghĩa |
| --- | --- | --- | --- |
| `queue_wait` | Yêu cầu được accepted/enqueued | Worker thực sự lấy task để chạy | Thời gian **chờ được phục vụ** |
| `lock_wait` | Bắt đầu yêu cầu giành lock | Giành được lock hoặc timeout | Chi phí **chờ khóa** |
| `lock_hold` | Giành được lock | Release lock | Thời gian **giữ khóa**, khác lock_wait |
| `dependency_wait` | Bắt đầu lời gọi DB/HTTP/RPC hoặc await | Có response/failure/timeout | Thời gian của dependency cụ thể |
| `service_time` | Worker bắt đầu xử lý | Terminal outcome | Có thể bao gồm lock/dependency waits |
| `end_to_end` | Accepted hoặc received theo hợp đồng | Terminal outcome | Có thể bao gồm queue wait và service time |

Đừng cộng một cách cơ học `lock_wait + dependency_wait + service_time`: `service_time` thường đã **bao gồm** các thành phần wait bên trong, nên cộng sẽ đếm trùng.

### 4.1 Chọn đồng hồ: `System.nanoTime()` cho elapsed

Đối với thời lượng trong cùng JVM:

```java
long before = System.nanoTime();
try {
    // Lời gọi cần đo thời lượng.
} finally {
    long elapsedNanos = System.nanoTime() - before;
    // Ghi duration vào histogram/timer thích hợp.
}
```

Đây là **đoạn minh họa tích hợp**, không phải chương trình độc lập. `System.nanoTime()` trả mốc tham chiếu tùy ý phù hợp để tính **chênh lệch trong một JVM**, không phải epoch timestamp. Muốn ghép event với logs/trace của nhiều máy, ghi timestamp UTC như `Instant.now()` **riêng**.

Đo thời gian bằng `System.currentTimeMillis()` có thể bị ảnh hưởng bởi điều chỉnh wall clock; dùng cho thời điểm diễn ra sự kiện, không ưu tiên cho tính elapsed chính xác. Cần cùng nguồn clock và một cặp start/end cho mỗi operation.

### 4.2 Đo queue wait

Đặt timestamp **trước khi enqueue** và ghi lần worker bắt đầu chạy:

```java
long enqueuedAt = System.nanoTime();
executor.execute(() -> {
    long queueWaitNanos = System.nanoTime() - enqueuedAt;
    // metrics.recordQueueWait(queueWaitNanos);
    runBusinessWork();
});
```

Đây là đoạn mã **tích hợp**, `executor` và `runBusinessWork()` phải được định nghĩa. Trong production, cần xử lý rejection: một request bị từ chối không nên biến thành accepted thành công; đếm `rejected_total` và thống nhất khi nào accepted thật sự được ghi.

Với framework có scheduler, batch consumer hoặc message broker, “enqueued” có thể nằm ở hệ thống khác. `System.nanoTime()` **không thể được trừ trực tiếp giữa hai JVM**, vì origin tùy từng process. Đối với queue phân tán, dùng timestamp sự kiện có clock sync, broker metrics/traces và hiểu sai lệch đồng hồ.

### 4.3 Đo lock acquisition wait

Với `ReentrantLock`:

```java
long waitingSince = System.nanoTime();
lock.lock();
long acquiredAt = System.nanoTime();
try {
    // metrics.recordLockWait(acquiredAt - waitingSince);
    updateSharedState();
} finally {
    lock.unlock();
}
```

Đây cũng là đoạn mã tích hợp. Đo khoảng chờ lấy lock **khác** đo khoảng giữ lock. Phải đảm bảo unlock trong `finally`; nếu dùng `tryLock`/`lockInterruptibly`, còn cần ghi timeout/interrupted attempts riêng và không `unlock` khi chưa giành được lock.

Với `synchronized`, việc instrument chính xác thời điểm trước/sau block thường phải thiết kế cẩn thận:

```java
long start = System.nanoTime();
synchronized (sharedMonitor) {
    long acquired = System.nanoTime();
    // Đo elapsed trước khi vào monitor và cập nhật metric phù hợp.
}
```

**Không** ghi metrics bằng code gây blocking lâu bên trong vùng lock để tránh tạo contention mới trong quá trình giám sát.

### 4.4 Đo chờ dependency và timeout

Một HTTP client có thể trải qua DNS, connect, TLS, pool acquisition và response read. “HTTP latency” là tổng hay chỉ một phần cần được xác định. Với JDBC có connection pool, thời gian **chờ lấy connection** khác thời gian thực thi query.

Đặt timestamps, trace spans và deadline ở đúng ranh giới:

- Caller đã chờ bao lâu?
- Downstream đã nhận request chưa?
- Có timeout ở tầng connect/read/query/overall?
- Caller timeout có **hủy được** tác vụ phía remote không?
- Có retry làm request phát sinh nhiều lần không?

Khi request chậm nhưng queue wait thấp, nguyên nhân có thể nằm trong service time/dependency. Khi queue wait cao nhưng service time ổn, có thể là thiếu workers, scheduling starvation hoặc offered load vượt capacity.

## 5. Histogram, p50/p95/p99 và số mẫu

Average latency thấp **không** loại trừ tail latency rất xấu. Giả sử 99 request mất 10 ms, 1 request mất 20 giây, thì average vẫn không kể đầy đủ trải nghiệm của phần request chậm nhất.

Theo dõi **distribution** của queue wait, lock wait và end-to-end latency, không chỉ một tổng thời gian.

### 5.1 Ý nghĩa percentile

- **p50:** median gần trung vị, nửa mẫu có wait không vượt quá ngưỡng này theo định nghĩa percentile dùng.
- **p95:** khoảng 95% mẫu trong cửa sổ có wait không vượt ngưỡng p95.
- **p99:** khoảng 99% mẫu tương tự; nhạy với tail và cần số mẫu đủ lớn.

Percentile phụ thuộc thuật toán ước lượng, interpolation/nearestrank, histogram bucket layout, cỡ mẫu và cửa sổ. Nếu lab có **8 samples**, nearest-rank p95 sẽ thường là **giá trị lớn nhất**, rất nhiễu. Không dùng số p95 của một lab nhỏ để tuyên bố SLO production.

### 5.2 Không tính p95 toàn cluster bằng trung bình p95

Nếu replica A có p95 = 50 ms và B có p95 = 500 ms, `(50+500)/2 = 275 ms` **không** là p95 chung. Cần dữ liệu phân phối/histogram được tổng hợp đúng hoặc traces/raw samples có phương pháp phù hợp.

Ngoài ra, so sánh p95 trước–sau phải dùng **cùng percentile algorithm**, window duration, sampling strategy và loại operations. Nếu sau sửa chỉ đo các request thành công, nhưng trước sửa đo cả timeout, việc giảm p95 có thể chỉ là thay đổi population.

### 5.3 Kiểm tra số lượng mẫu và no-data

Một thời gian chờ “0 ms” khác với **chưa có sample**. Nếu hoàn toàn không có request trong một phút, p95 của cửa sổ đó có thể **không xác định**, không nên mặc định 0 rồi kết luận mọi request phản hồi tức thì.

Báo `sampleCount` bên cạnh distribution/quantiles, và phân biệt:

- 0 samples: không đủ dữ liệu;
- measured zero: thực sự có sample xấp xỉ 0 theo độ phân giải;
- metric missing: exporter không đo/không truy cập được;
- timeout/cancelled: đã ghi với ngữ nghĩa phù hợp, không loại khỏi mọi biểu đồ mà không nói.

Một ứng dụng chưa có request không nhất thiết bị “stalled”; phát hiện stall cần điều kiện **offered/accepted work > 0** và không có progress trong một khoảng vượt ngưỡng.

## 6. Công cụ JVM: dùng để giải thích, không thay thế business progress

`ThreadMXBean`, `ThreadInfo`, `jcmd Thread.print` và JFR là nguồn chứng cứ runtime. Chúng giúp xác định *vì sao* waits thay đổi, nhưng không tự xác nhận business operation đã thành công.

### 6.1 ThreadMXBean và contention

Java 17 có:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();

boolean supported =
        mx.isThreadContentionMonitoringSupported();
if (supported && mx.isThreadContentionMonitoringEnabled()) {
    ThreadInfo info = mx.getThreadInfo(threadId);
    if (info != null) {
        long blockedCount = info.getBlockedCount();
        long blockedMs = info.getBlockedTime();
        long waitedMs = info.getWaitedTime();
        // Chỉ phân tích cùng thread và cùng cửa sổ.
    }
}
```

Đoạn trên **không độc lập**: cần `ThreadMXBean`, `ThreadInfo`, `ManagementFactory` imports và một `threadId` dương hợp lệ. Mặc định contention monitoring của nhiều JVM **tắt**; khi không enabled, `getBlockedTime()` / `getWaitedTime()` có thể trả **`-1`**, không phải 0.

**Các giới hạn cốt lõi:**

- `getBlockedTime()` là thời gian tích lũy ước lượng chờ **intrinsic monitor** (`BLOCKED`), không phải tất cả waits của `ReentrantLock`, HTTP, database hay queue.
- `getWaitedTime()` phản ánh thời gian ở trạng thái waiting/timed waiting theo ngữ nghĩa API, không thay cho transaction-level latency.
- Counter/time thuộc một thread; worker trong pool có thể xử lý nhiều business operations, vì vậy không thể trực tiếp gán mỗi millisecond chờ của thread cho một request.
- Thống kê thời gian có thể reset khi monitoring được bật lại; không tính delta băng qua thay đổi cấu hình theo dõi.
- `setThreadContentionMonitoringEnabled(true)` là **thao tác thay đổi trạng thái quan sát của JVM** và có overhead; muốn bật trong production phải được phép, ghi timestamp và so chi phí.

### 6.2 Thread dump và deadlock detection

Một vài mẫu thread dumps sau sửa có thể kiểm tra lock graph và call paths có còn vấn đề. Với HotSpot và quyền hợp lệ:

```bash
jcmd 12345 Thread.print -l
```

`12345` trong lệnh là **PID minh họa**, phải thay bằng PID target JVM thật. Kiểm tra `jcmd 12345 help Thread.print` nếu không chắc options trên JDK hiện tại.

`ThreadMXBean.findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` có thể tìm chu trình monitor/ownable synchronizer theo phạm vi được hỗ trợ. Kết quả `null` sau sửa chỉ có nghĩa **không phát hiện loại cycle ấy tại thời điểm đo**, không chứng minh hệ thống đã xử lý xong request hoặc hết pool starvation.

**Thứ tự ưu tiên:** đo progress business trước, sau đó dùng stacks/lock owner/CPU/JFR để giải thích nguyên nhân. Không lấy một thread state `RUNNABLE` hoặc `WAITING` làm tiêu chí PASS duy nhất.

### 6.3 CPU thay đổi không đồng nghĩa throughput tốt hơn

Sửa livelock bằng cách thêm `Thread.sleep(100)` có thể làm CPU giảm, retries giảm nhưng **completed work vẫn bằng 0**; đó không phải sửa lỗi thành công. Ngược lại, sau khi bỏ lock contention, CPU có thể tăng vì workers giờ thực sự xử lý nhiều requests hơn.

Vì vậy cần so CPU cùng **completed/succeeded rate, p95/p99 wait, queue age, errors** dưới cùng workload. CPU là **guardrail và tín hiệu phụ trợ**, không phải mục tiêu cuối cùng nếu SLO hướng đến nghiệp vụ.

## 7. Thiết kế phép thử trước–sau đáng tin

Một phép so sánh gồm **baseline → thay đổi → xác minh**. Nếu thay workload, process identity, số workers, cache và định nghĩa counter đồng thời, bạn không còn biết nguyên nhân cải thiện.

### 7.1 Ghi một “measurement contract”

Trước khi chạy, xác nhận:

| Thành phần | Nội dung phải cố định hoặc ghi lại |
| --- | --- |
| Scope | Service/component, endpoint/job class, JVM/instance và build |
| Load | Arrival rate, concurrency, mix, payload size, dữ liệu đầu vào |
| Duration | Warm-up, steady-state window, measurement interval |
| Metric definition | Accepted/started/completed/succeeded/failed/retry semantics |
| Units | operations/s, milliseconds, percentages, queue depth |
| Sampling | Histogram buckets, quantile method, sample count, missing data |
| Runtime | JDK/GC/CPU quota/memory, number of workers, pool/queue sizes |
| Environment | Downstream versions/availability, DB state, caches, network |
| Pass criteria | Completion and success rate, maximum age/p95 wait, timeout/error guardrails |
| Failure protocol | Nếu không tiến triển, thời điểm dừng test và thu evidence an toàn |

Nếu trước sửa chạy 1.000 concurrent requests mà sau sửa chỉ 10, sự thay đổi không phải đối chứng phù hợp cho kết luận “đã giải quyết starvation dưới tải 1.000”.

### 7.2 Warm-up và nhiều lần chạy

JIT compilation, class loading, lazy initialization, cache warm-up, connection pooling và GC có thể làm lần đầu chậm khác lần sau. Thực hành:

1. Khởi chạy baseline đủ lâu để tiến tới trạng thái gần ổn định khi có thể.
2. Tách **warm-up interval** ra khỏi measurement window.
3. Lấy nhiều cửa sổ liên tiếp (hoặc nhiều run) với timestamp và sample count.
4. Lặp lại dưới đúng tình huống đã kích hoạt lỗi trước đây, không chỉ tải trung bình.
5. Deploy một sửa lỗi cụ thể; giữ các cấu hình khác ổn định trong phạm vi có thể.
6. Lấy dữ liệu sau sửa bằng cùng công cụ, cùng contract và cùng số lượng/tần suất mẫu.
7. So cả trung tâm lẫn đuôi phân phối (p50/p95/p99), rate và backlog.
8. Nếu kết quả biến động mạnh, ghi khoảng dao động và giả thuyết; không chọn duy nhất một run tốt nhất.

**Đừng tự sửa số liệu** bằng cách bỏ các khoảng thất bại hoặc timeout khỏi tập đo rồi so với baseline có đủ thất bại. Nếu có sample bị loại, quy tắc phải được công bố giống nhau trước và sau.

### 7.3 So sánh đúng cửa sổ và đúng instance

Với counters tích lũy, mỗi rate cần **hai mốc thuộc cùng instance**, không có reset. Nếu một lần rollout thay pod, hãy bắt đầu series mới hoặc dùng công cụ hiểu reset.

Với histograms rolling, cần cùng window và population. Với log/traces, cần thống nhất timestamp/timezone và clock skew khi liên quan nhiều máy. Một số times đo bằng `nanoTime` trong JVM này **không so trực tiếp tuyệt đối** với `nanoTime` của JVM khác.

### 7.4 Một phép thử PASS cần cả hiệu quả và correctness

Ví dụ tiêu chí giả định cho job queue:

- Sau warm-up, offered load 8 jobs/s, duy trì 10 phút.
- Success throughput tối thiểu 7,8 jobs/s; completions theo dõi đủ.
- p95 queue wait nhỏ hơn 200 ms; p99 hoặc oldest queue age không vượt ngân sách đã định.
- Failure/timeout/cancellation rate không tăng so với baseline bất thường.
- Queue depth không tăng có xu hướng vô hạn; no stuck oldest task.
- Không tái hiện lock cycle/đường không tiến triển trong stress test.
- CPU/RSS/GC/connection pool/DB latency vẫn trong guardrails.

Các con số ở trên **chỉ là ví dụ** để minh họa cách viết acceptance criteria; phải thay bằng SLO và workload thật. Nếu không đạt, kết luận `NOT_VERIFIED`/`FAIL` theo định nghĩa, không cố suy từ một vài request thành công.

## 8. Java 17: chương trình đo hoàn tất và queue wait

Chương trình **`ProgressVerificationLab.java`** có hai chế độ:

- `fixture`: dùng dữ liệu giả định trước–sau ở phần 3 để tính rate, hệ số cải thiện và mức giảm p95 queue wait; stdout **cố định**, không chạy tasks thật.
- `observe`: tạo một **ThreadPoolExecutor hai workers**, nộp tám tasks mô phỏng, trong đó một task chủ động thất bại; thu accepted/started/completed/succeeded/failed và queue wait. Tổng số outcome có thể kiểm tra; **elapsed time, queue p95 và thứ tự chạy phụ thuộc máy**. Đây chỉ là lab nhỏ, không phải benchmark production.

Dùng Java 17 hoặc mới hơn, không cần thư viện ngoài.

Tạo tệp **`ProgressVerificationLab.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class ProgressVerificationLab {
    record Window(String name, long accepted, long completed,
                  long succeeded, long failed,
                  double durationSeconds, long queueP95Millis) {
        double completionRate() {
            return completed / durationSeconds;
        }
    }

    static void fixture() {
        Window before = new Window(
                "before", 240, 60, 57, 3, 30.0, 1200);
        Window after = new Window(
                "after", 240, 240, 237, 3, 30.0, 90);

        for (Window w : new Window[] {before, after}) {
            System.out.printf(Locale.ROOT,
                    "%s accepted=%d completed=%d succeeded=%d "
                    + "failed=%d rate=%.2f/s queueP95=%dms%n",
                    w.name(), w.accepted(), w.completed(),
                    w.succeeded(), w.failed(),
                    w.completionRate(), w.queueP95Millis());
        }

        double rateGain =
                after.completionRate() / before.completionRate();
        double p95Reduction = 100.0 *
                (before.queueP95Millis() - after.queueP95Millis())
                / before.queueP95Millis();

        System.out.printf(Locale.ROOT,
                "completionRateGain=%.2fx queueP95Reduction=%.2f%%%n",
                rateGain, p95Reduction);
    }

    static final class Metrics {
        final AtomicLong accepted = new AtomicLong();
        final AtomicLong started = new AtomicLong();
        final AtomicLong completed = new AtomicLong();
        final AtomicLong succeeded = new AtomicLong();
        final AtomicLong failed = new AtomicLong();
        final AtomicInteger inFlight = new AtomicInteger();

        // Chỉ dành cho lab nhỏ; production nên dùng histogram
        // giới hạn bộ nhớ thay vì giữ mọi thời lượng.
        final List<Long> queueWaitNanos =
                Collections.synchronizedList(new ArrayList<>());

        void onStart(long queuedAtNanos) {
            long now = System.nanoTime();
            queueWaitNanos.add(Math.max(0L, now - queuedAtNanos));
            started.incrementAndGet();
            inFlight.incrementAndGet();
        }

        void onFinish(boolean successful) {
            if (successful) {
                succeeded.incrementAndGet();
            } else {
                failed.incrementAndGet();
            }
            completed.incrementAndGet();
            inFlight.decrementAndGet();
        }

        long queueP95Millis() {
            List<Long> copy;
            synchronized (queueWaitNanos) {
                copy = new ArrayList<>(queueWaitNanos);
            }
            if (copy.isEmpty()) {
                return -1; // Chưa có mẫu, không phải 0 ms.
            }
            Collections.sort(copy);
            int index = (int) Math.ceil(0.95 * copy.size()) - 1;
            return TimeUnit.NANOSECONDS.toMillis(copy.get(index));
        }
    }

    static void observe() throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(16),
                work -> new Thread(work, "progress-lab-worker"));

        Metrics metrics = new Metrics();
        List<Future<?>> futures = new ArrayList<>();
        long sampleStart = System.nanoTime();

        try {
            for (int i = 0; i < 8; i++) {
                final int jobId = i;
                final long enqueuedAt = System.nanoTime();

                Future<?> future = pool.submit(() -> {
                    metrics.onStart(enqueuedAt);
                    boolean success = false;
                    try {
                        Thread.sleep(jobId == 0 ? 80L : 15L);
                        if (jobId == 3) {
                            throw new IllegalStateException(
                                    "synthetic lab failure");
                        }
                        success = true;
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                                "lab interrupted", ex);
                    } finally {
                        metrics.onFinish(success);
                    }
                });

                // Đã được pool chấp nhận; không đếm rejected.
                metrics.accepted.incrementAndGet();
                futures.add(future);
            }

            int futureFailures = 0;
            for (Future<?> future : futures) {
                try {
                    future.get(3, TimeUnit.SECONDS);
                } catch (ExecutionException ex) {
                    futureFailures++;
                }
            }

            pool.shutdown();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "pool did not terminate");
            }

            long elapsedNanos = System.nanoTime() - sampleStart;
            System.out.printf(Locale.ROOT,
                    "accepted=%d started=%d completed=%d "
                    + "succeeded=%d failed=%d "
                    + "futureFailures=%d inFlight=%d%n",
                    metrics.accepted.get(), metrics.started.get(),
                    metrics.completed.get(), metrics.succeeded.get(),
                    metrics.failed.get(), futureFailures,
                    metrics.inFlight.get());

            System.out.printf(Locale.ROOT,
                    "elapsedMs=%d queueP95Ms=%d%n",
                    TimeUnit.NANOSECONDS.toMillis(elapsedNanos),
                    metrics.queueP95Millis());
        } finally {
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java ProgressVerificationLab fixture|observe");
            return;
        }
        switch (args[0]) {
            case "fixture" -> fixture();
            case "observe" -> observe();
            default -> System.out.println("Unknown mode");
        }
    }
}
```

### 8.1 Biên dịch và chạy fixture

```bash
javac ProgressVerificationLab.java
java ProgressVerificationLab fixture
```

Stdout **chính xác** của chế độ `fixture`:

```text
before accepted=240 completed=60 succeeded=57 failed=3 rate=2.00/s queueP95=1200ms
after accepted=240 completed=240 succeeded=237 failed=3 rate=8.00/s queueP95=90ms
completionRateGain=4.00x queueP95Reduction=92.50%
```

**Giải thích:** `60 / 30 = 2.00` và `240 / 30 = 8.00`; `8/2 = 4.00`; `(1200-90)/1200*100=92.50`. Code dùng `Locale.ROOT` để định dạng thập phân bằng dấu chấm, không phụ thuộc locale máy.

Hai giá trị p95 trong fixture **được cung cấp sẵn** như dữ liệu giả định, không phải percentile mà chương trình tính từ request timestamps. Đây là **đối chứng toán học của báo cáo**, không chứng minh một bản sửa thật đã hoạt động.

### 8.2 Chạy một workload thật trong JVM lab

```bash
java ProgressVerificationLab observe
```

Khi các tasks hoàn tất trong khoảng timeout của lab và không có can thiệp ngoài, **dòng counters** dự kiến:

```text
accepted=8 started=8 completed=8 succeeded=7 failed=1 futureFailures=1 inFlight=0
```

Dòng timing có dạng:

```text
elapsedMs=<số đo thực tế> queueP95Ms=<số đo thực tế>
```

**Hai chỗ trong dấu ngoặc nhọn ở trên là mô tả định dạng, không phải stdout cố định.** Máy bận, OS scheduling, JIT, độ phân giải clock và việc các tasks xếp queue sẽ thay đổi thời lượng. Trong khi đó một task có `jobId==3` ném `IllegalStateException` có chủ đích; `submit()` lưu exception trong `Future`, nên code bắt `ExecutionException` trong loop và tăng `futureFailures`. Nó vẫn được tính là **completed terminal outcome nhưng failed**, không phải success.

Điều này trực tiếp kiểm chứng một bẫy vận hành: **nếu chỉ đếm tasks đã kết thúc, một sửa lỗi có thể trông thành công dù toàn bộ tasks trả failure**. Phải giữ riêng success/failure và business correctness.

### 8.3 Hạn chế của lab observe

- Chỉ có tám tasks; p95 nearest-rank hầu như là **max sample**, không phù hợp chứng minh SLO.
- `queueWaitNanos` được giữ trong một `List` để dễ hiểu; **không dùng** với hàng triệu requests production vì memory tăng không giới hạn. Trong sản phẩm thật dùng bounded histogram/reservoir hoặc metrics library có hành vi được kiểm chứng.
- Các counters là atomic độc lập, không có **snapshot nguyên tử giữa nhiều thuộc tính** trong lúc công việc đang chạy. Sau khi chờ tất cả futures và pool terminate thì số liệu lab đã ổn định.
- Queue của lab được giới hạn ở 16; số tasks là 8, nên không cố tình test `RejectedExecutionException`. Trong production phải ghi **rejections và admission** đúng, không đếm task bị từ chối là accepted.
- Timing đo queue wait từ trước submit đến lúc Runnable bắt đầu; bao gồm một phần overhead submit/scheduling, khác định nghĩa queue wait nội bộ của một message broker. Ghi contract của hệ thống thật.
- `Thread.sleep(80)` chỉ giả lập operation chờ, không phải nguyên nhân thực của contention. Thay thời gian sleep rồi thấy throughput tăng không chứng minh sửa lỗi deadlock.
- `pool.shutdownNow()` trong `finally` là cleanup lab. Không áp dụng vô điều kiện trên pool production đang phục vụ user requests.

## 9. Vì sao một cửa sổ tốt chưa đủ chứng minh đã sửa lỗi?

Một lần sau sửa đạt completion rate cao có thể do:

- Workload thấp hơn baseline, ít request cạnh tranh tài nguyên.
- Cache đã warm, DB vừa purge/compact hoặc downstream đã phục hồi độc lập.
- Sửa lỗi chỉ che biểu hiện bằng retry nhanh, nhưng thất bại vẫn tiếp diễn.
- Service restart đã phá lock/dependency cycle trong memory, bug vẫn còn trong code.
- Metrics đổi định nghĩa: “accepted” hay “completed” không còn tính các retries/timeouts như trước.
- Collector bỏ mất samples khi CPU overload hoặc agent restart.
- Đang thấy **backlog drain**: completed rate tạm thời cao hơn offered rate, sau đó trở lại mức cũ.
- Chưa chạy đủ lâu để tái hiện race condition hiếm hoặc starvation nhiều phút.
- Một nhóm requests khác bị ảnh hưởng xấu hơn; tổng throughput che tail của nhóm nhỏ.
- Người đo đã chọn đúng run nhanh nhất để báo cáo mà bỏ các run kém.

### 9.1 Thiết kế phép thử lặp lại

Một cách thực hành:

1. Tái hiện failure với controlled test và lấy baseline nhiều lần.
2. Xác nhận reproducibility: sau bao lâu progress dừng, điều kiện nào kích hoạt.
3. Chỉ áp dụng một fix hoặc một nhóm thay đổi có quan hệ chặt.
4. Chạy lại với cùng arrival pattern, payload/data, pool size, JVM flags, quotas, dependencies và duration.
5. So công việc hoàn thành **mỗi cửa sổ**, success rate, wait p95/p99, oldest pending age và errors.
6. Thử overload giới hạn, cancellation/timeout, repeated runs và rollback/canary nếu cần.
7. Lấy thread dump/JFR khi symptom tái hiện; không chỉ khi mọi thứ bình thường.
8. Ghi kết luận có độ tin cậy, mẫu số, khoảng quan sát và những thứ chưa kiểm tra.

Một change có thể thật sự cải thiện contention nhưng làm fairness kém hơn: cần kiểm tra cả throughput tổng lẫn **per-class oldest wait** và tail latency.

## 10. Bộ tiêu chí theo từng loại lỗi đã sửa

### 10.1 Sau sửa deadlock

**Trước:** một số threads giữ khóa chéo, không hoàn tất nghiệp vụ; lock graph cho thấy chu trình.

**Sau:** ở workload tái hiện, accepted vẫn đến; completed và succeeded tăng ổn định; các locks được cấp phát/nhả đúng, không còn cycle trong các mẫu có ý nghĩa; p95/p99 lock/queue wait nằm trong ngân sách; không có request tồn tại mãi.

**Cần kiểm tra:**

- Các code paths lấy locks theo thứ tự toàn cục nhất quán, kể cả error paths.
- Bằng chứng thu bằng `ThreadMXBean` nếu dùng đúng loại synchronizer và JVM hỗ trợ.
- Không đơn giản bỏ một lock gây race/data corruption để tăng throughput.
- Tải cao/contended paths không tái tạo cycle.

**Giới hạn:** `findDeadlockedThreads()==null` ở một thời điểm không chứng minh không còn mọi logical/distributed deadlock. Business completion và thời gian chờ qua nhiều mẫu là chứng cứ bổ sung cần thiết.

### 10.2 Sau sửa livelock

**Trước:** retry/attempt count tăng nhanh, có activity/CPU nhưng committed operations gần bằng 0.

**Sau:** số **successfully committed operations** tăng; tỷ lệ `successDelta / attemptDelta` được cải thiện; retries được giới hạn và có backoff/deadline; queue oldest age không tăng mãi; latency không vượt budget.

**Cần kiểm tra:**

- `retried_total` giảm có phải do code bỏ retry và trả failure ngay không?
- `succeeded_total` có tăng dưới cùng loại xung đột không?
- Retry jitter/backoff không làm p99 quá cao hoặc làm task bị starvation.
- Khi downstream thật sự down, có bounded failure thay vì infinite retry loop.

CPU giảm nhưng successDelta vẫn bằng 0: **chưa thể PASS**.

### 10.3 Sau sửa starvation

**Trước:** một class task bị bỏ đói, oldest queue age tăng trong khi task khác vẫn có progress.

**Sau:** tất cả các class công việc có cơ hội được phục vụ theo policy; per-class completion rate và oldest wait nằm trong deadline; không có nhóm bị trì hoãn vô hạn dưới tải dự kiến.

**Cần kiểm tra:**

- Tổng completed/s tăng nhưng low-priority p99/oldest age có cải thiện không?
- Fair lock/priority aging có làm throughput quá thấp không?
- Bounded queue/rejections có được báo minh bạch không?
- Một số task có cần capacity reservation/bulkhead riêng để không bị long-running tasks chiếm slot?

Một nhóm request quan trọng có queue wait 10 phút trong khi service tổng 1.000 RPS vẫn có thể là starvation nghiêm trọng.

### 10.4 Sau sửa thao tác chờ quá lâu

**Trước:** request chờ `Future.get`, network, DB, lock, condition hoặc latch không giới hạn, chiếm worker quá deadline.

**Sau:** có deadline/timeout hợp lý, request được trả terminal outcome rõ; active waits/queue age không tăng vô hạn; tỷ lệ success đúng SLO; cancellation/cleanup hoạt động theo semantics; downstream/worker hồi phục.

**Cần kiểm tra:**

- Timeout tăng nhưng success giảm? Đây có thể là fail-fast hữu ích để bảo vệ tài nguyên, **không đồng nghĩa nghiệp vụ đã được phục hồi**.
- Caller đã timeout nhưng remote job vẫn chạy và tạo tác dụng phụ? Cần kiểm tra idempotency/cancellation.
- Thời gian trong queue có được trừ khỏi tổng budget hay chỉ timeout từ lúc task bắt đầu?
- Có mất dữ liệu/duplicate processing do retry hay không?

## 11. Kiểm chứng không làm nhiễu hệ thống

Thu số liệu có chi phí. Nếu cứ mỗi 100 ms chụp full thread dump hoặc bật contention monitoring không đánh giá overhead, phép đo có thể làm tình hình xấu hơn.

**Ưu tiên thứ tự ít xâm lấn:**

1. Counters, histograms, request traces và queue metrics ứng dụng **đã instrument**.
2. JVM/process/container metrics có sẵn: CPU, GC, memory, thread count, cgroup throttling.
3. Chụp một số thread dumps có timestamp khi cần khóa/stack evidence.
4. JFR sampling hoặc contention monitoring có kiểm soát và ghi thời gian bật/tắt.
5. Chỉ thu snapshot nặng khi câu hỏi chẩn đoán không được giải bằng số nhẹ.

Nhớ đọc trạng thái khả dụng của `ThreadMXBean` trước khi dùng CPU/blocked/waited time; `-1` hoặc `null` có thể là chưa đo/không có thread/tính năng không hỗ trợ, **không** phải measured zero.

Khi ghi log/traces, hạn chế request payload, secrets và dữ liệu nhạy cảm; kiểm soát retention và quyền truy cập. Không tạo một metric label mới cho mỗi request/user/trace ID, vì cardinality bùng nổ và có nguy cơ lộ thông tin.

## 12. Kiểm chứng “hết kẹt” cần xét cả backlog và arrival rate

Giả sử sau sửa:

```text
Offered load:    100 jobs/s
Completed rate:   80 jobs/s
Queue depth:      1,000 → 1,200 → 1,400 ...
```

Dịch vụ **có tiến triển** (80 jobs/s) nhưng **không theo kịp tải** (100 jobs/s), backlog vẫn lớn dần. Không nên gọi là phục hồi đầy đủ.

Một ví dụ khác:

```text
Offered load:     80 jobs/s
Completed rate:  100 jobs/s
Queue depth:    1,000 → 700 → 400 ...
```

Hệ thống có thể đang **xả backlog**: completed tạm thời lớn hơn offered, queue giảm. Đây là dấu hiệu tích cực nếu success/correctness còn đảm bảo, nhưng cần tiếp tục đo **sau khi backlog ổn định**, vì completion rate có thể giảm khi queue cạn.

Với mẫu số đúng, quan hệ trực giác:

```text
changeInBacklog ≈ acceptedDuringWindow
                  - startedDuringWindow
                  + requeuedDuringWindow
                  - removedQueuedItems
```

Đây là **mô hình minh họa**, không phải invariant áp dụng cho mọi queue; cần tính cả worker transfers, cancellations, failures, transaction retries và snapshot consistency. Đừng lấy `accepted - completed` làm queue depth nếu chưa ghi rõ `inFlight` và những trạng thái trung gian.

### 12.1 Oldest age bổ sung điều gì?

Queue depth ổn định không bảo đảm fairness. Một priority scheduler có thể liên tục nhận và hoàn tất high-priority tasks, trong khi một low-priority job bị kẹt suốt hàng giờ. Tổng queue depth gần như không đổi, nhưng **oldest age của nhóm nạn nhân tăng mãi**.

Vì vậy khi sửa starvation, ngoài throughput tổng phải đo:
- accepted/completed per class;
- waiting age per class;
- oldest unserved job duration;
- p95/p99 queue wait cho đúng group;
- rejected/cancelled/deadline exceeded per class.

Không cần biến mỗi job ID thành metric label; aggregation hữu hạn theo priority/class đủ cho dashboard, ID chi tiết ở logs/traces.

### 12.2 Little's Law: quan hệ hỗ trợ diễn giải, không phải phán quyết

Trong một **hệ thống ổn định** với các giả thiết phù hợp, Little's Law viết:

```text
Average number of jobs in system
    ≈ throughput per second × average time in system

L ≈ λ × W
```

Ví dụ hệ thống hoàn tất 10 jobs/s và thời gian trung bình trong hệ thống khoảng 2 s, mức WIP trung bình theo quan hệ xấp xỉ 20 jobs. Nhưng không dùng công thức để suy “đang bị deadlock” từ một snapshot: nó dựa trên averages và điều kiện ổn định, không phản ánh p99 hoặc tình trạng hệ thống đang tăng backlog vô hạn.

## 13. Không đánh tráo correctness lấy completion rate

Một số cách làm throughput tăng nhưng sản phẩm sai:

- Bỏ xác thực/validation để request trả success nhanh hơn.
- Bỏ ghi transaction/commit hoặc bỏ chờ kết quả DB trước khi ack.
- Nuốt exception rồi tăng `succeeded_total` dù nghiệp vụ chưa hoàn tất.
- Timeout caller nhưng retry lại nhiều lần gây duplicate payments.
- Nới lock/ordering mà không giữ invariant, tạo race condition.
- Loại nhóm request chậm ra khỏi báo cáo sau sửa để p95 đẹp hơn.

**Business progress** phải được xác minh bằng kết quả thực: record đã commit, job ack sau khi xử lý đúng, response đáp ứng contract, không mất/nhân bản dữ liệu. Vì vậy acceptance criteria phải bao gồm **correctness**, success/failure semantics, idempotency và reconciliation khi cần.

Nếu số `completed` tăng vì thêm 1.000 failures nhanh thì hệ thống có thể **fail-fast tốt hơn** (bảo vệ tài nguyên) nhưng chưa thể gọi là nghiệp vụ đã hồi phục. Báo đúng hai kết luận riêng: *đã giới hạn thời gian chờ* và *tỷ lệ thành công còn chưa đạt mục tiêu*.

## 14. Một ma trận đọc bằng chứng nhanh

| Quan sát sau sửa | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| Completed rate > 0, trước đó bằng 0 | Có dấu hiệu tiến triển trở lại | Đã đạt SLO/correctness dưới mọi tải |
| Succeeded rate ổn định, failures thấp hơn | Business progress cải thiện ở cửa sổ đo | Nguyên nhân thay đổi chắc chắn chỉ do code fix |
| Queue p95 giảm, oldest age giảm | Chờ trong queue có tín hiệu tốt hơn | Không có request cá biệt bị bỏ đói |
| Retry rate giảm, success rate tăng | Giảm retries vô ích, cải thiện output | Livelock không tái xuất dưới tải biên |
| ThreadMXBean không thấy deadlock cycle | Không phát hiện cycle thuộc loại API hỗ trợ lúc đo | Không có deadlock logic/phân tán/ở thời điểm khác |
| CPU giảm nhưng completed=0 | Không chứng minh đã có progress | Vấn đề đã được sửa |
| `Future.get(timeout)` báo timeout | Caller đã hết ngân sách chờ | Remote task đã dừng |
| Pool `getCompletedTaskCount` tăng | Executor có tasks kết thúc | Business operations đều thành công |
| p99 latency tăng, trung bình giảm | Tail bị xấu đi cho một số công việc | Fix chắc chắn thành công về SLO |
| Một run đạt mục tiêu, các run khác thất bại | Có điều kiện mà fix hoạt động | Đã loại bỏ bug concurrency một cách tin cậy |

## 15. Mẫu báo cáo kiểm chứng trước–sau

```text
IDENTITY
- Service, build/revision, JVM vendor/version, PID/pod:
- Fix description and hypothesized failure mechanism:
- Baseline incident timestamp and reproduction conditions:

MEASUREMENT CONTRACT
- Work type and definition of accepted/completed/succeeded/failed:
- Units: operations/s, queue/lock/dependency wait in ms:
- Window duration, sample count, percentile algorithm:
- Workload: offered load, concurrency, request mix, payload size:
- Environment: CPU quota, GC, pool/queue sizes, dependency state:

BEFORE FIX
- Accepted/completed/succeeded/failed counts per window:
- Completion rate, success rate, retries and failure fraction:
- Queue depth, oldest age, in-flight age:
- p50/p95/p99 queue wait, lock wait, e2e latency:
- Thread dump/JFR/lock owner evidence:
- CPU/GC/DB/network guardrails:

AFTER FIX
- Same metrics under comparable conditions:
- Completion/success rate improvement:
- Wait/tail percentile changes and absolute differences:
- Backlog trend, fairness per class, deadline exceed count:
- Correctness/idempotency/duplicate/lost-work checks:

QA / UNCERTAINTY
- Number of runs, warm-up excluded, variance:
- Counter resets, missing samples, observer overhead:
- What is observed vs hypothesized:
- PASS/FAIL/INCONCLUSIVE criteria:
- Remaining risk, regression tests, rollout/canary owner:
```

Mẫu trên nên được điền bằng **số liệu có timestamp và nguồn rõ**. Nếu thiếu khả năng đo một metric, ghi `not measured`, `unsupported` hoặc `insufficient samples` thay vì tự điền 0.

Một báo cáo đáng tin có thể nêu:

> “Ở 5 cửa sổ 30 giây dưới workload 8 accepted requests/s, sau sửa completion rate tăng từ khoảng 2 lên 8/s, p95 queue wait giảm, tỷ lệ success không xấu đi và oldest queue age không còn tăng. Trong phạm vi test có kiểm soát, các tiêu chí PASS; vẫn cần theo dõi canary trong peak traffic và tải có conflict hiếm.”

Đây là **mẫu cách viết nhận định**, không phải kết quả đã thu từ hệ thống thật. Luôn phân biệt “phép thử đạt” với “đã chứng minh không thể xảy ra race condition ở mọi lịch chạy”.

## 16. Các sai lầm thường gặp

1. **Đếm attempts thay completed.** Livelock có thể có vô số retries nhưng 0 progress.
2. **Đếm completed executor tasks thành thành công nghiệp vụ.** Tasks có thể kết thúc do exception.
3. **Chỉ so CPU.** CPU giảm có thể đơn giản vì workers ngủ/chờ nhiều hơn.
4. **Chỉ so live thread count.** Ít thread hơn không chứng minh queue được phục vụ.
5. **Lấy một điểm counter tích lũy làm throughput.** Phải tính delta trên cùng instance/cửa sổ.
6. **Không xử lý counter reset sau restart.** Có thể tính rate âm hoặc kết luận sai.
7. **Gộp accepted, started và completed.** Không phân biệt queue wait và service time.
8. **Nhầm queue wait với end-to-end latency.** Chỉ giảm một thành phần chưa chắc giảm toàn bộ.
9. **Cộng service time và dependency wait khi dependency đã nằm trong service time.** Đếm trùng.
10. **Dùng `System.nanoTime` như UTC timestamp.** Nó đo elapsed, không phải wall-clock.
11. **So timestamps nanoTime giữa các JVM.** Origin khác nhau.
12. **Không ghi sample count cho p95/p99.** Percentile của 8 mẫu rất nhiễu.
13. **Tính trung bình p95 giữa replicas.** Không cho p95 toàn cluster.
14. **Biến missing sample thành 0 ms.** Che lỗi exporter và false improvement.
15. **Loại timeout/failure khỏi tập đo sau sửa nhưng không loại ở baseline.** Population không còn giống nhau.
16. **So trước–sau với tải khác nhau.** Không còn đối chứng nhân quả hợp lệ.
17. **Quên warm-up/JIT/cache.** Một run đầu có thể chậm bất thường.
18. **Chọn run tốt nhất.** Che variance và bug race hiếm.
19. **Chỉ chạy một lần.** Chưa đủ chứng cứ với deadlock/starvation chỉ xuất hiện dưới lịch chạy đặc biệt.
20. **Không đo oldest queue age.** Tổng throughput có thể cao nhưng một nhóm vẫn bị starvation.
21. **Tin deadlock detector trả null là sửa xong.** API chỉ quan sát loại cycle hỗ trợ tại một thời điểm.
22. **Bật contention monitoring mà không ghi thời điểm.** Dữ liệu time có thể reset, overhead đổi kết quả.
23. **Biến `-1` của ThreadInfo thành 0.** `-1` thường là chưa có đo hợp lệ.
24. **Báo completion rate tăng khi chỉ tăng failures nhanh.** Không phân biệt success/correctness.
25. **Chỉ kiểm tra lúc backlog drain.** Cần đo tiếp khi steady state mới hình thành.
26. **Không đo deadline trong queue.** Task có thể hết ngân sách trước khi worker bắt đầu.
27. **Quên cancellation/idempotency.** Timeout caller không hủy tác dụng phụ phía remote.
28. **Instrumentation quá nặng.** Getter/tracing/dumps có thể tạo contention mới.
29. **Đặt user IDs vào labels.** Cardinality và privacy risk lớn.
30. **Restart trước khi thu evidence.** Có thể mất thread graph, queue age và timeline gốc.
31. **Tuyên bố “không có treo” vì một request thành công.** Cần cả tail/population và stress reproduction.
32. **Không có tiêu chí PASS được định nghĩa trước.** Dễ chọn metric thuận lợi để kể chuyện sau khi xem kết quả.

## 17. Tự kiểm tra kiến thức

1. Tại sao một counter retry tăng không đủ chứng minh hệ thống có progress?
2. Phân biệt `accepted_total`, `started_total`, `completed_total`, `succeeded_total` với ví dụ một request retry ba lần.
3. Từ 60 lên 240 completed operations trong hai cửa sổ 30 giây, completion rate tăng bao nhiêu lần?
4. Nếu sau sửa `completedRate` tăng nhưng `succeededRate` không tăng, bạn phải xem những outcome nào?
5. `System.nanoTime()` dùng cho elapsed hay timestamp giữa nhiều hosts? Vì sao?
6. Đo queue wait bắt đầu/kết thúc ở đâu? Có cần bao gồm thời gian worker đang thực thi không?
7. Vì sao `getBlockedTime()` của ThreadInfo không phải toàn bộ thời gian chờ DB/RPC?
8. `ThreadMXBean.findDeadlockedThreads()` trả null, liệu đã xác nhận hết starvation chưa?
9. Vì sao p99 queue wait có thể tăng dù mean giảm? Bạn cần thêm loại dữ liệu gì?
10. Tại sao một p95 trên 8 mẫu không đủ để kiểm chứng SLO production?
11. Có thể lấy trung bình p95 của hai replicas để có p95 toàn cluster không?
12. Nếu accepted rate 100/s nhưng completed rate 80/s duy trì, backlog sẽ thế nào trong mô hình đơn giản?
13. Tại sao queue depth ổn định vẫn có thể che starvation của low-priority jobs?
14. Cách nào phân biệt một spike completed rate do backlog drain với một cải thiện steady-state?
15. Trước/sau tải khác nhau 10 lần thì báo cáo nên ghi giới hạn gì?
16. Sau sửa có timeout nhanh hơn nhưng success giảm: nên kết luận sửa lỗi thành công hay chỉ fail-fast?
17. `Future.get(timeout)` có tự đảm bảo task đã bị hủy chưa? Cần kiểm tra gì?
18. Những guardrails nào nên đo cùng completion rate để bảo đảm không đánh đổi correctness?
19. Khi nào dùng repeated tests, canary và chaos/failure injection có kiểm soát?
20. Viết một acceptance criterion đo được cho việc khắc phục queue starvation và một tiêu chí cho deadlock.

## Nguồn tham khảo

- Oracle Java SE 17 — `System.nanoTime()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
- Oracle Java SE 17 — `ThreadMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java SE 17 — `ThreadInfo`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- Oracle Java SE 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Oracle Java SE 17 — `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Oracle Java SE 17 — `LongAdder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- Oracle Java SE 17 — `jcmd`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html

**Ghi nhớ:** xác nhận sửa lỗi treo/tranh chấp bằng **công việc kết thúc đúng nghĩa**, **thông lượng thành công**, **thời gian chờ và tail latency**, **queue age** cùng **correctness/guardrails** dưới tải tương đương. CPU, thread states hay không thấy lock cycle chỉ là dữ liệu hỗ trợ. Một bản sửa được coi là kiểm chứng trong phạm vi bài test khi các tiêu chí đã định đạt qua nhiều cửa sổ phù hợp và không tạo ra tác dụng phụ hoặc mất tiến độ ở nhóm công việc khác.