# Kiểm soát tốc độ khi hàng đợi đồng thời không giới hạn trong Java

## 1. Tại sao một hàng đợi thread-safe vẫn có thể làm hệ thống quá tải?

Trong mô hình producer–consumer, producers tạo công việc và đưa vào queue, còn consumers lấy công việc ra xử lý. `ConcurrentLinkedQueue`, `LinkedBlockingQueue` và các thành phần của `java.util.concurrent` giúp nhiều threads truy cập hàng đợi an toàn, nhưng **an toàn đồng thời không đồng nghĩa an toàn về bộ nhớ, độ trễ hoặc sức chịu tải**.

Giả sử một service nhận events, HTTP jobs hoặc tác vụ xử lý ảnh. Nó có 4 consumers, mỗi consumer xử lý hữu hạn việc mỗi giây, nhưng producers có thể thêm việc nhanh hơn. Nếu queue không có giới hạn thực tế, các events chưa xử lý **vẫn được giữ trong heap**: payload, buffers, request context, references, callbacks và object graphs. GC không thể thu hồi chúng khi queue còn giữ reference.

Hậu quả là backlog tăng, time-in-queue vượt deadline, clients retry, GC nặng hơn và cuối cùng có thể gặp `OutOfMemoryError`. Việc `offer` thành công **không có nghĩa** job có thể hoàn thành trong SLA hay đủ bộ nhớ để giữ mọi request.

**Đề bài trực tiếp:** “Kiểm soát tốc độ khi hàng đợi không giới hạn”, thuộc nhóm **“Hàng đợi đồng thời”**.

**Yêu cầu Special Note:** bài chỉ sử dụng kiến thức **vẫn còn áp dụng trên JDK hiện đại**, không dựa vào mẹo lỗi thời hoặc legacy. Java `ConcurrentLinkedQueue`, `LinkedBlockingQueue`, `ArrayBlockingQueue`, `BlockingQueue`, `Semaphore`, `ThreadPoolExecutor` vẫn có trong Java 17/21. Chương trình chính được biên dịch/chạy bằng **Java 21**, không sử dụng API bị loại bỏ.

### Sau bài học, bạn biết

- Phân biệt unbounded queue, bounded queue và “default capacity quá lớn”.
- Hiểu vì sao producer nhanh hơn consumer làm backlog tích lũy.
- Chọn bounded queue có `offer`/`offer(timeout)`/`put` theo deadline.
- Khi bắt buộc dùng unbounded queue, đặt **admission gate** bằng `Semaphore`.
- Phân biệt giới hạn **số item trong queue** với **số job queued + in-flight**.
- Đảm bảo acquire trước enqueue và release permit đúng một lần.
- Biết vì sao `queue.size()` + `offer()` không tạo được hard bound.
- Nhận ra bẫy unbounded queue của `Executors.newFixedThreadPool`.
- Tổ chức load shedding, backpressure, metrics, retries, shutdown.
- Chạy một chương trình Java 21 chứng minh các hành vi trên và output xác định.

## 2. Unbounded, bounded và các kiểu queue

| API | Capacity | Điều đáng chú ý |
| --- | --- | --- |
| `ConcurrentLinkedQueue<E>` | **Unbounded**, nonblocking FIFO | `offer` không tự đợi consumer; `poll` trả null nếu rỗng |
| `LinkedBlockingQueue<E>()` | Mặc định **`Integer.MAX_VALUE`** | Về vận hành hầu như unbounded; hết heap trước khi đạt limit |
| `LinkedBlockingQueue<E>(capacity)` | Bounded theo tham số | `offer` từ chối, `put` chờ khi full |
| `ArrayBlockingQueue<E>(capacity)` | Bounded fixed array | Bounded buffer FIFO, `offer/put/take`, optional fairness |
| `PriorityBlockingQueue<E>` | Logically unbounded | Sắp theo priority, không phải FIFO, vẫn có rủi ro backlog |
| `LinkedTransferQueue<E>` | Unbounded | Transfer/handoff, nhưng `offer` không tạo bound |
| `DelayQueue<E>` | Unbounded | Phần tử đợi đến hạn; nhiều delayed items vẫn chiếm bộ nhớ |
| `SynchronousQueue<E>` | Không chứa item nội bộ | Handoff trực tiếp, cần xem capacity của consumer/pool bên ngoài |

**Không giới hạn ≠ RAM vô hạn.** Một `LinkedBlockingQueue()` có giới hạn số học `Integer.MAX_VALUE`, nhưng trên máy thực bộ nhớ có thể hết trước nhiều bậc độ lớn. `ConcurrentLinkedQueue` unbounded theo contract nhưng có thể thất bại khi cạn tài nguyên.

### 2.1. `ConcurrentLinkedQueue`

~~~java
ConcurrentLinkedQueue<String> queue = new ConcurrentLinkedQueue<>();
queue.offer("A");
queue.offer("B");
String first = queue.poll(); // "A" nếu không có thread khác thao tác.
~~~

Đây là snippet minh họa, cần import `java.util.concurrent.ConcurrentLinkedQueue`. Queue không cho phần tử null. `offer` và `poll` không block theo cách `BlockingQueue.put/take`; `poll()` trả null khi rỗng, không có cơ chế đánh thức worker đang ngủ sau enqueue.

**Quan trọng:** `ConcurrentLinkedQueue.size()` **không O(1)**. Theo Javadoc Java SE 21, nó phải duyệt các phần tử, có thể tốn thời gian và cho kết quả không chính xác trong lúc queue đang bị sửa. Không dùng nó trong hot-path admission của mọi request.

### 2.2. `LinkedBlockingQueue`

~~~java
BlockingQueue<String> withoutBound = new LinkedBlockingQueue<>();
BlockingQueue<String> bounded = new LinkedBlockingQueue<>(256);
~~~

Đây là snippet minh họa, cần imports. Constructor không có tham số dùng capacity `Integer.MAX_VALUE`; constructor có tham số cho một bound thực dụng, ví dụ 256. Số 256 chỉ là ví dụ, **không phải capacity mặc định tối ưu cho mọi ứng dụng**.

Một hàng đợi “BlockingQueue” không đương nhiên tạo backpressure kịp thời nếu capacity của nó gần như vô hạn. Nếu queue quá lớn, `put` có thể không block trước lúc JVM chịu áp lực heap.

### 2.3. `ArrayBlockingQueue`

~~~java
BlockingQueue<String> q = new ArrayBlockingQueue<>(2);
boolean first = q.offer("A"); // true
boolean second = q.offer("B"); // true
boolean third = q.offer("C"); // false khi queue đầy.
~~~

Đây là snippet minh họa trong điều kiện chưa có consumer song song. `ArrayBlockingQueue` có capacity cố định ngay từ constructor và `offer` từ chối khi đầy. Fairness option của constructor có thể giúp thứ tự phục vụ những threads đang chờ công bằng hơn nhưng có trade-off throughput; fairness không tự giải quyết deadlines.

## 3. Tốc độ vào/ra và sự tăng trưởng backlog

Đặt:

- `λ` = tốc độ jobs được **nhận vào** (accepted/s).
- `μ` = tốc độ jobs được **hoàn tất** bởi consumers (completed/s).
- `Q` = jobs đang xếp hàng.

Khi tốc độ gần như ổn định và không có reject/drop, trong một khoảng thời gian:

\[
\Delta Q \approx (\lambda-\mu)\,\Delta t.
\]

Ví dụ producers gửi 150 jobs/s, consumers hoàn tất 100 jobs/s liên tục 60 giây; backlog có thể tăng khoảng **3.000 jobs**. Đây là **ước tính minh họa**, không phải công thức xác định số phần tử ở mọi thời điểm do concurrency, bursts, retries và task durations.

Nếu `λ>μ` đủ lâu thì queue hữu hạn **cuối cùng đầy**, queue không giới hạn chỉ trì hoãn failure bằng việc giữ thêm RAM.

### 3.1. Backlog trở thành thời gian chờ

Nếu backlog đang chờ khoảng 1000 jobs, consumers xử lý ổn định 100 jobs/s và không có job mới thì cần cỡ **10 giây** để drain chúng. Nếu request mới có deadline 2 giây, nhận vào cuối queue có thể gây timeout và retry trước khi được xử lý.

**Little’s law** `L=λW` trong điều kiện hệ thống ổn định liên hệ lượng việc trung bình, tốc độ và thời gian lưu trung bình. Đừng dùng nó như bảo đảm tuyệt đối trong giai đoạn queue tăng không ổn định.

### 3.2. Năng lực consumer có thể giảm bất ngờ

Một downstream database bị chậm, quota external API bị thu hẹp, GC tăng, CPU contention hay lock bottleneck đều làm `μ` giảm. Chỉ đặt rate limiter dựa trên benchmark tốt nhất có thể vẫn nhận nhanh hơn năng lực thực tế lúc service degraded.

### 3.3. Vì sao GC không cứu queue đang phình?

Queue còn giữ reference đến item, item có thể giữ request body lớn, byte arrays, maps, tracing metadata, callbacks, mutable state hoặc toàn bộ object graph. Khi các phần tử vẫn reachable, GC **không thể dọn chúng**. Giới hạn số item chưa chắc đủ nếu một item có payload 200 MB; cần **byte budget** và max payload per request.

## 4. Backpressure, admission và load shedding

**Backpressure:** downstream đang chậm khiến upstream giảm tốc độ/đợi có kiểm soát. **Admission control:** quyết định có nhận công việc mới không. **Load shedding:** từ chối hoặc bỏ công việc không quan trọng theo policy để tránh toàn hệ thống sụp đổ.

| Chính sách | Khi đầy | Khi phù hợp |
| --- | --- | --- |
| `offer` fail fast | Trả false ngay | HTTP request có deadline hoặc cần từ chối sớm |
| `offer(timeout)` | Chờ tối đa deadline | Burst ngắn, lượng waiting producers có giới hạn |
| `put` | Chờ tới khi có chỗ hoặc interrupt | Batch nội bộ có lifecycle và timeout bên ngoài |
| `CallerRunsPolicy` | Caller chạy job thay pool | Một số CPU workloads, chấp nhận chậm caller |
| Drop/coalesce/sampling | Không xử lý mọi item | Telemetry, refresh state; phải được business cho phép |
| Durable broker/queue | Lưu tồn đọng bền vững | Jobs không được mất, cần recovery |
| Throttle/rate limit | Giảm admission per interval | Làm mượt bursts, bảo vệ quota downstream |
| Scale consumers | Tăng processing capacity | Khi downstream vẫn scale được |

**Một rate limiter không tự là queue bound.** Nếu consumer tụt từ 100/s xuống 10/s mà rate limit cho phép 80/s, backlog vẫn tăng. Hãy kết hợp rate limiting với bounded admission/queue và thông tin tải thực.

### 4.1. Tránh busy retry

~~~java
while (!queue.offer(job)) {
    // Retry tức thì, không có deadline/backoff.
}
~~~

Đây là **phản ví dụ không nên dùng**. Khi queue đã full, vòng lặp có thể tiêu CPU và tăng contention, không đáp ứng interruption/shutdown và tạo retry storm. Dùng bounded wait, rõ lý do reject, exponential backoff+jitter hoặc upstream signal.

### 4.2. Chặn producer có thể chỉ chuyển chỗ backlog

Nếu hàng nghìn request threads cùng bị block trong `put`, các threads đó vẫn giữ stack, payload và connection context. Queue đã bounded nhưng số waiting producers lại unbounded. Cần thêm giới hạn **concurrent producers**, thời gian chờ và request/body size.

### 4.3. Không silently drop jobs cần bảo đảm

Với metrics không quan trọng, sampling/drop có thể là policy hợp lệ. Với thanh toán/đặt hàng/email bắt buộc, drop âm thầm thường không chấp nhận được; cần explicit rejection, durable handoff, job ID, trạng thái lỗi, idempotency và khả năng retry.

## 5. Cách 1: dùng bounded `BlockingQueue`

Đây thường là lựa chọn **đơn giản nhất** nếu bạn có quyền chọn queue:

~~~java
BlockingQueue<Job> queue = new ArrayBlockingQueue<>(256);
~~~

Snippet minh họa; `Job` và cơ chế xử lý do ứng dụng định nghĩa. Có thể dùng `LinkedBlockingQueue<>(256)` với trade-offs memory/throughput riêng.

### 5.1. Ba kiểu enqueue có semantics khác nhau

**Không đợi khi đầy:**

~~~java
boolean accepted = queue.offer(job);
if (!accepted) {
    // Báo reject/overload theo API contract.
}
~~~

**Chờ có hạn:**

~~~java
boolean accepted = queue.offer(job, 100, TimeUnit.MILLISECONDS);
if (!accepted) {
    // Admission timeout.
}
~~~

**Chờ vô hạn cho đến khi có chỗ hoặc interrupt:**

~~~java
queue.put(job);
~~~

Các snippets cần imports, biến `job/queue` và xử lý `InterruptedException` cho những API chờ. Với request thread có deadline, `put` có thể gây latency vô hạn nếu consumer không tiến triển. Với một queue logically unbounded, timed `offer` cũng không tự tạo một capacity thấp hữu ích.

### 5.2. Consumer bằng `take` hoặc `poll(timeout)`

~~~java
Job job = queue.take();
try {
    process(job);
} finally {
    // Dọn tài nguyên riêng của job theo ownership.
}
~~~

Đây là mã minh họa, cần `process` và shutdown. `take()` block khi queue rỗng; `poll(timeout)` hữu ích nếu cần định kỳ kiểm tra stop flag. Khi item được lấy khỏi bounded queue, queue slot được giải phóng **ngay**, không cần đợi job xử lý xong.

### 5.3. Giới hạn queued và giới hạn outstanding khác nhau

Nếu queue có 100 slots và worker pool có 8 consumers, có thể tồn tại **100 queued + 8 in-flight** (chưa kể producer side). Bounded queue bảo vệ backlog trong queue, nhưng nếu cần bound **mọi accepted-but-unfinished work**, thêm quota outstanding như `Semaphore` giữ permit tới terminal completion.

## 6. Vì sao `size()` trước `offer` không tạo giới hạn

~~~java
if (queue.size() < maxItems) {
    queue.offer(job);
}
~~~

Đây là **phản ví dụ**. Hai producers cùng thấy size=9 khi limit=10 rồi cùng enqueue, dẫn tới 11. Check và action không atomic. Với `ConcurrentLinkedQueue`, `size()` còn O(n) và có thể sai số khi concurrent mutation.

~~~java
if (semaphore.availablePermits() > 0) {
    queue.offer(job);
}
~~~

Cũng là **phản ví dụ**. `availablePermits()` chỉ là quan sát, không có reservation; producer khác có thể lấy permit ngay sau đó. Muốn nhận việc phải **`tryAcquire()`**.

## 7. Cách 2: giữ unbounded queue nhưng kiểm soát admission bằng `Semaphore`

Khi cần giữ `ConcurrentLinkedQueue` vì API/kiến trúc, đặt một cổng admission:

~~~text
PRODUCER
   |
   v
Semaphore.tryAcquire()
   | không có permit -> reject/timed wait/backoff
   v
ConcurrentLinkedQueue.offer(job)
   |
   v
Consumer.poll()
   |
   v
Xử lý job / terminal failure policy
   |
   v
release permit ĐÚNG MỘT LẦN
~~~

Queue vẫn **unbounded theo bản chất**; bound ở đây là **logic của wrapper**. Nó chỉ đúng nếu **mọi producer enqueue** đều qua wrapper và **mọi đường dequeue/cancel/clear/settlement** đều phục hồi permits chính xác.

### 7.1. Acquire phải xảy ra trước enqueue

Thứ tự đúng:

1. Xác nhận service còn accepting, validate input nhẹ.
2. `tryAcquire` hoặc `tryAcquire(timeout,unit)`.
3. Không có permit: **không enqueue**, trả response quá tải theo policy.
4. Có permit: enqueue. Nếu `offer` fail/throw, **release trong `finally`**.
5. Sau terminal processing/ACK hoặc terminal failure handoff, **release đúng một lần**.

Enqueue trước rồi mới acquire làm quota bị vượt trong thời gian chờ. Nếu tạo payload rất lớn **trước** acquire, producers vẫn có thể tiêu thụ RAM ngay cả khi queue gate từ chối; trong production nên admit trước khi materialize dữ liệu nặng khi kiến trúc cho phép.

### 7.2. Khi nào release permit?

- **Queue-only bound:** sau `poll` thành công (job không còn chờ trong queue).
- **Outstanding bound:** sau processing/terminal handling, gồm cả queued + in-flight.

Bài demo dùng **outstanding bound** để chứng minh: consumer lấy A ra nhưng đang processing, permit của A vẫn giữ; C không được nhận dù bên trong queue chỉ còn B. Sau khi consumer finish A, C mới được admit.

### 7.3. Double release và permit leak

`Semaphore.release()` không tự gắn permit với logical job. Nếu completion, timeout và cancellation callbacks cùng release cho một job, quota có thể **vượt số permits khởi tạo**. Nếu enqueue thất bại nhưng không release, quota bị **leak**. Dùng state machine/`AtomicBoolean` để đảm bảo chỉ một terminal settlement và release.

Một job có thể fail khi xử lý. Trả permit chỉ dọn **resource budget**, không tự retry, không tạo durability, không bảo đảm exactly-once hay rollback side effects. Cần policy nghiệp vụ riêng.

### 7.4. Consumer wakeup là phần việc bổ sung

`ConcurrentLinkedQueue.poll()` không đợi. Nếu queue từ rỗng sang có items mà consumers đang ngủ, wrapper cần cơ chế wakeup/notification đáng tin; không được bận CPU bằng busy polling hoặc tạo lost wakeups. Khi không có lý do bắt buộc giữ CLQ, **bounded BlockingQueue** đơn giản và ít lỗi hơn vì có `put/take`.

## 8. Bẫy executor: fixed worker không có nghĩa bounded waiting queue

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
~~~

Đoạn mã trên có **4 workers**, nhưng queue mặc định chứa tasks chờ là unbounded theo contract. Nếu submit nhanh hơn workers hoàn tất, hàng đợi `Runnable/Callable` có thể giữ số lượng rất lớn. Chỉ cấu hình worker count chưa đủ để chống OOM.

Một lựa chọn rõ ràng hơn:

~~~java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        4, 4,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<Runnable>(64),
        new ThreadPoolExecutor.AbortPolicy());
~~~

Đây là mảnh mã minh họa; ứng dụng cần import, shutdown và xử lý `RejectedExecutionException`. Nó giới hạn tối đa 4 running workers và khoảng 64 waiting tasks trong queue của executor khi vận hành thông thường; **không giới hạn** số producer threads, RAM tạo job từ ngoài hoặc tasks chạy ở các executor khác.

### 8.1. Vì sao `maximumPoolSize` không cứu unbounded queue?

`ThreadPoolExecutor` ưu tiên đưa tasks vào queue sau khi đạt `corePoolSize` trước khi tăng thêm workers tới `maximumPoolSize` trong các cấu hình thông dụng. Khi work queue là unbounded và luôn nhận được việc, pool có thể **không tăng vượt core size**. Chỉnh maximum lớn hơn không tự biến queue thành bounded.

### 8.2. `RejectedExecutionHandler`

| Policy | Hành vi khi saturated | Rủi ro |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` | Caller phải trả overload rõ ràng |
| `CallerRunsPolicy` | Chạy task trên caller nếu executor chưa shutdown | Request thread bị giữ lâu, thread context có thể khác |
| `DiscardPolicy` | Bỏ task | Dễ mất jobs nếu không có ACK policy |
| `DiscardOldestPolicy` | Bỏ task cũ rồi retry submit | Làm mất thứ tự, bỏ việc cũ chưa xử lý |

`CallerRunsPolicy` có thể làm producer chậm bằng cách buộc nó xử lý việc, nhưng **không phải** global hard rate limit nếu có nhiều producer độc lập. Phải đảm bảo task có thể chạy an toàn trên caller thread.

## 9. Ví dụ Java 21 hoàn chỉnh: bounded queue và semaphore gate

Chương trình sau có hai phần:

**Phần A:** `LinkedBlockingQueue()` rỗng có `remainingCapacity()=2147483647`; `ArrayBlockingQueue<>(2)` nhận A, B nhưng từ chối C. Sau khi poll A, nó nhận C và lấy B,C theo FIFO.

**Phần B:** `ConcurrentLinkedQueue<String>` được bọc bởi `AdmittedQueue` dùng `Semaphore(2)`. Producer nhận A và B, C bị từ chối ngay. Consumer poll A nhưng giữ permit tới lúc finish; một producer khác chờ bằng timed `tryAcquire`. Sau khi main cho consumer hoàn tất A, C được nhận. B và C vẫn giữ permits tới khi hoàn tất. Hai threads và main được điều phối bằng `CountDownLatch`/`Future.get(timeout)`, **không dùng `Thread.sleep`** để suy đoán lịch thực thi.

Chương trình chỉ xử lý `String`, không dùng mạng, không tạo dữ liệu ngoài. `AdmittedQueue` là **mẫu minh họa accounting**, không phải toàn bộ dispatcher production vì chưa có wakeup/close/retry protocol.

Tạo file `src/main/java/demo/QueueRateControlExample.java`:

~~~java
package demo;

import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class QueueRateControlExample {
    private QueueRateControlExample() {}

    private static final class AdmittedQueue {
        private final ConcurrentLinkedQueue<String> queue = new ConcurrentLinkedQueue<>();
        private final Semaphore slots;
        private final int limit;

        AdmittedQueue(int limit) {
            if (limit <= 0) {
                throw new IllegalArgumentException("limit must be positive");
            }
            this.limit = limit;
            this.slots = new Semaphore(limit);
        }

        boolean trySubmit(String item) {
            Objects.requireNonNull(item);
            if (!slots.tryAcquire()) {
                return false;
            }
            boolean accepted = false;
            try {
                accepted = queue.offer(item);
                return accepted;
            } finally {
                if (!accepted) {
                    slots.release();
                }
            }
        }

        boolean submitWithin(String item, long timeout, TimeUnit unit)
                throws InterruptedException {
            Objects.requireNonNull(item);
            if (!slots.tryAcquire(timeout, unit)) {
                return false;
            }
            boolean accepted = false;
            try {
                accepted = queue.offer(item);
                return accepted;
            } finally {
                if (!accepted) {
                    slots.release();
                }
            }
        }

        Delivery poll() {
            String item = queue.poll();
            return item == null ? null : new Delivery(item, slots);
        }

        int reserved() {
            return limit - slots.availablePermits();
        }
    }

    private static final class Delivery {
        private final String item;
        private final Semaphore slots;
        private final AtomicBoolean settled = new AtomicBoolean();

        Delivery(String item, Semaphore slots) {
            this.item = item;
            this.slots = slots;
        }

        String item() {
            return item;
        }

        void finish() {
            if (!settled.compareAndSet(false, true)) {
                throw new IllegalStateException("Delivery finished twice");
            }
            slots.release();
        }
    }

    private static void awaitReady(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Latch timed out");
        }
    }

    public static void main(String[] args) throws Exception {
        LinkedBlockingQueue<String> defaultLinked = new LinkedBlockingQueue<>();
        System.out.println("default-linked-max=" + defaultLinked.remainingCapacity());

        ArrayBlockingQueue<String> bounded = new ArrayBlockingQueue<>(2);
        System.out.println("bounded-first=" + bounded.offer("A"));
        System.out.println("bounded-second=" + bounded.offer("B"));
        System.out.println("bounded-third=" + bounded.offer("C"));
        System.out.println("bounded-poll=" + bounded.poll());
        System.out.println("bounded-retry=" + bounded.offer("C"));
        System.out.println("bounded-drain=" + bounded.poll() + "," + bounded.poll());

        AdmittedQueue gate = new AdmittedQueue(2);
        System.out.println("gate-first=" + gate.trySubmit("A"));
        System.out.println("gate-second=" + gate.trySubmit("B"));
        System.out.println("gate-third-immediate=" + gate.trySubmit("C"));

        CountDownLatch workerReady = new CountDownLatch(1);
        CountDownLatch producerReady = new CountDownLatch(1);
        CountDownLatch allowFinish = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<String> consumer = executor.submit(() -> {
                Delivery delivery = gate.poll();
                if (delivery == null) {
                    throw new IllegalStateException("Missing first delivery");
                }
                workerReady.countDown();
                try {
                    allowFinish.await();
                    return delivery.item();
                } finally {
                    delivery.finish();
                }
            });
            awaitReady(workerReady);
            System.out.println("reserved-while-processing=" + gate.reserved());

            Future<Boolean> producer = executor.submit(() -> {
                producerReady.countDown();
                return gate.submitWithin("C", 5, TimeUnit.SECONDS);
            });
            awaitReady(producerReady);
            System.out.println("reserved-before-finish=" + gate.reserved());
            allowFinish.countDown();
            System.out.println("worker-finished=" + consumer.get(5, TimeUnit.SECONDS));
            System.out.println("timed-producer-admitted="
                    + producer.get(5, TimeUnit.SECONDS));
            System.out.println("reserved-after-handoff=" + gate.reserved());

            Delivery second = gate.poll();
            Delivery third = gate.poll();
            if (second == null || third == null) {
                if (second != null) {
                    second.finish();
                }
                if (third != null) {
                    third.finish();
                }
                throw new IllegalStateException("Missing remaining deliveries");
            }
            try {
                System.out.println("gate-drain=" + second.item() + "," + third.item());
            } finally {
                second.finish();
                third.finish();
            }
            System.out.println("reserved-after-finish=" + gate.reserved());
            System.out.println("empty-poll=" + gate.poll());
        } finally {
            allowFinish.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                throw new IllegalStateException("Executor did not terminate");
            }
        }
        System.out.println("executor-terminated=" + executor.isTerminated());
    }
}
~~~

**Biên dịch và chạy bằng Java 21** từ thư mục chứa `src`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/QueueRateControlExample.java
java -cp out demo.QueueRateControlExample
~~~

**Stdout chính xác đã kiểm thử:**

~~~text
default-linked-max=2147483647
bounded-first=true
bounded-second=true
bounded-third=false
bounded-poll=A
bounded-retry=true
bounded-drain=B,C
gate-first=true
gate-second=true
gate-third-immediate=false
reserved-while-processing=2
reserved-before-finish=2
worker-finished=A
timed-producer-admitted=true
reserved-after-handoff=2
gate-drain=B,C
reserved-after-finish=0
empty-poll=null
executor-terminated=true
~~~

### 9.1. Ý nghĩa output

- `default-linked-max=2147483647`: capacity mặc định danh nghĩa của `LinkedBlockingQueue()` rỗng, không phải heap quota.
- `bounded-first/second=true`, `bounded-third=false`: queue capacity 2 chặn phần tử thứ ba.
- `bounded-poll=A`, `bounded-retry=true`, `bounded-drain=B,C`: sau khi lấy A, có chỗ cho C và FIFO được giữ.
- `gate-first/second=true`, `gate-third-immediate=false`: hai permits dành cho A/B, C chưa được nhận.
- `reserved-while-processing=2`, `reserved-before-finish=2`: consumer đã poll A nhưng chưa finish; quota vẫn đầy dù queue còn B.
- `worker-finished=A` và `timed-producer-admitted=true`: producer chờ được nhận C sau khi A giải phóng permit.
- `reserved-after-handoff=2` và `gate-drain=B,C`: B,C vẫn outstanding cho tới khi hoàn tất.
- `reserved-after-finish=0`: không có permit leak.
- `empty-poll=null`: queue rỗng.
- `executor-terminated=true`: pool do bài test sở hữu đã shutdown sạch.

### 9.2. Vì sao không phụ thuộc scheduling?

Main đặt A/B trước khi submit consumer. Consumer `poll` A, báo `workerReady` rồi bị giữ bởi `allowFinish.await()`. Main chỉ đọc `reserved` sau latch và **trước** khi mở cổng hoàn tất; quota chắc chắn vẫn là 2. Producer báo `producerReady` và phải chờ permit, nhưng main chưa mở `allowFinish` nên C không thể được nhận quá sớm. Cuối cùng, main đợi cả hai Futures rồi mới đọc trạng thái B,C và drain.

Timeout 5s chỉ giúp bài test không chờ vô hạn nếu có lỗi; không được coi là deadline chuẩn cho server production.

### 9.3. `AtomicBoolean` và `finally` giải quyết điều gì?

`Delivery.finish()` dùng `AtomicBoolean.compareAndSet(false,true)` để ngăn double release. Consumer A release trong `finally` khi scope processing kết thúc, kể cả khi bị interrupt. **Điều này chỉ quản lý permit**, không tự retry job khi xử lý fail. Business muốn at-least-once/exactly-once behavior phải có durable handoff và idempotency/ACK phù hợp.

## 10. Tính capacity bằng memory và latency budget

Đừng chọn 100000 hay một triệu items chỉ vì máy có nhiều RAM. Một quy trình thường gồm:

1. Đo `μ` dưới tải bình thường và tình huống downstream degraded.
2. Xác định tối đa một job được phép chờ bao lâu trước khi quá hạn.
3. Đo retained bytes-per-job, bao gồm payload, object graph và related futures.
4. Trừ bộ nhớ dành cho caches, active requests, buffers, thread stacks và GC reserve.
5. Ước tính capacity từ latency và memory budgets, có headroom.
6. Giới hạn đồng thời số workers và producer waiters.
7. Thêm byte quota nếu jobs chênh nhau lớn về kích thước.
8. Kiểm thử burst, slow consumers, retry storm và shutdown.
9. Theo dõi tail latency thay vì chỉ queue depth.

Ví dụ có 5000 jobs và mỗi job giữ khoảng 100 KiB payload, riêng payload đã chiếm cỡ **488 MiB**, chưa kể overhead. Đó là một ước lượng minh họa; thực tế phải dùng profiler/metrics. Bounded **item count** không ngăn một job đơn lẻ giữ hàng trăm MB.

### 10.1. Tốc độ và memory của producer cũng cần bound

Ngay cả khi queue admission có semaphore, nếu producer đọc/xử lý toàn bộ request body lớn **trước** khi `tryAcquire`, nó vẫn có thể tạo áp lực RAM trước khi bị reject. Khi kiến trúc cho phép, kiểm tra admission sớm và áp max request body/bytes để tránh materialize payload không được nhận.

## 11. Metrics và cảnh báo quá tải

| Metric | Ý nghĩa |
| --- | --- |
| `jobs.accepted` | Số jobs được nhận |
| `jobs.rejected` | Số jobs từ chối do quota |
| `admission.timeout` | Bounded wait hết hạn |
| `queue.depth` | Queue items còn chờ, phải đo phù hợp với kiểu queue |
| `queue.oldest_age` | Tuổi job chờ lâu nhất |
| `queue.wait_duration` | p50/p95/p99 time-in-queue |
| `jobs.in_flight` | Items đã poll nhưng chưa terminal outcome |
| `jobs.completed` / `jobs.failed` | Kết quả cuối |
| `jobs.retries` | Tải do retry |
| `permit.reserved` | Quota outstanding đã dùng |
| `producers.waiting` | Số threads/tasks đợi admission |
| `consumer.throughput` | Jobs/s tiêu thụ thực |
| `heap.used` / `gc.pause` | Memory và GC pressure |
| `downstream.latency` | Nút nghẽn sau consumer |

Không đặt `ConcurrentLinkedQueue.size()` trong hot path. Có thể maintain counters/metrics riêng khi admission và terminal settlement, nhưng chúng cũng là các snapshot khi đọc song song. `Semaphore.availablePermits()` là quan sát; việc quyết định acceptance phải thông qua `tryAcquire`.

Một mô hình accounting logic:

~~~text
accepted = completed + failed_terminal + outstanding
outstanding = queued + in_flight + reserved_but_not_enqueued
~~~

Quan hệ này cần mở rộng khi có retries, duplicate messages, DLQ hoặc nhiều tầng queue. Đừng coi các metrics đọc ở những thời điểm khác nhau là một transaction atomic.

### 11.1. Chỉ nhìn depth chưa đủ

Depth=1000 có thể không đáng lo nếu throughput 100000/s, nhưng cực nguy hiểm nếu consumer chỉ xử lý 10/s. **Oldest age, backlog growth, rejection rate, tail latency, heap/GC và downstream health** thường cung cấp tín hiệu tốt hơn.

## 12. Thất bại, cancellation, retries và permit ownership

### 12.1. Enqueue fail sau acquire

Nếu đã acquire rồi `queue.offer(item)` throw, `finally` phải release. Nếu không, vài failure paths có thể làm hết permits dù queue rỗng, gây **permit leak**.

### 12.2. Double release khi callbacks race

Success callback, timeout callback và cancel callback có thể chạy gần nhau. Nếu hai callback cùng `release`, semaphore không tự phát hiện reservation logic bị trả trùng và bound bị phá. Dùng atomic state transition hoặc idempotent terminal settlement.

### 12.3. Consumer exception

Nếu worker poll job nhưng fail trước commit, release permit chỉ giải phóng quota, **không chứng minh business task thành công**. Cần policy: retry có giới hạn, durable handoff, dead letter, failure log và client ACK. Không được bỏ job im lặng nếu ứng dụng yêu cầu không mất.

### 12.4. Clear/remove ngoài wrapper

Một đường `queue.clear()` hoặc `remove` trên raw queue sẽ bỏ jobs mà không tương ứng release permits/terminal outcomes, làm lệch accounting. Bọc kín queue và có một owner quản lý các mutations.

### 12.5. Retry storm và idempotency

Client timeout khi job vẫn đang chờ, rồi retry: hai jobs giống nhau có thể được xử lý hoặc commit hai lần nếu thiếu idempotency. Dùng job IDs, idempotency keys, exponential backoff+jitter, max attempts và trạng thái durable cho công việc quan trọng.

### 12.6. Đừng dựa vào `OutOfMemoryError` để phát tín hiệu reject

OOM là tình trạng nguy hiểm, lúc đó việc trả response/log/cleanup có thể không còn đáng tin cậy. Admission cần từ chối **trước** khi thiếu bộ nhớ.

## 13. Shutdown của pipeline với hàng đợi bounded

Một quy trình dừng điển hình:

~~~text
RUNNING
  |
  | đặt stopping, ngừng nhận việc mới
  v
QUIESCING
  |
  | hoàn tất/drain các jobs đã accept đến deadline
  v
DRAINING
  |
  | terminal failure/durable handoff/cancel nếu cần
  v
CLEANUP
  |
  | release reservations, shutdown executor, awaitTermination
  v
TERMINATED
~~~

**Race khó:** producer đọc `accepting=true` rồi context switch; shutdown manager dừng nhận và snapshot queue; sau đó producer mới enqueue. Job có thể bị bỏ sót. Một boolean đơn lẻ không tạo handoff nguyên tử; cần lock/state machine/serialized coordinator bảo vệ admission và stop cùng nhau.

Không dùng `queue.clear()` để dừng nếu jobs cần terminal outcome và permits đang được giữ. Nếu thực sự drop, phải settle từng job theo policy và release quota đúng một lần. Nếu cần bảo đảm qua crash, queue chỉ trong RAM không đủ, hãy dùng durable storage/broker.

### 13.1. `ExecutorService` phải được dừng theo ownership

`shutdown()` ngừng nhận tasks mới và cho tasks đã nhận hoàn tất; `awaitTermination(timeout)` cho biết đã dừng trong thời hạn chưa. `shutdownNow()` cố gắng dừng tasks và có thể interrupt workers, nhưng không bảo đảm I/O/transaction đã rollback. Không shutdown thread pool thuộc service khác. Nếu một job bị cancel nhưng đã có side effect, retries phải có idempotency.

## 14. Sai lầm và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chọn queue thread-safe rồi nghĩ memory tự an toàn | Backlog, OOM | Bounded admission |
| Không truyền capacity cho `LinkedBlockingQueue` | Default `Integer.MAX_VALUE` | Chọn capacity thực |
| Tin `newFixedThreadPool` cũng bounded tasks queue | Runnable backlog lớn | Bounded queue hoặc admission ngoài pool |
| Check `size` trước `offer` | TOCTOU race, O(n) với CLQ | `offer` của bounded queue hoặc `tryAcquire` |
| Check `availablePermits` rồi offer | Không có reservation | Atomic acquire |
| Acquire sau enqueue | Vượt quota | Acquire trước |
| Release lúc poll dù cần bound outstanding | Outstanding vượt quota | Release sau terminal outcome |
| Double release callback | Quota tăng giả | Atomic terminal state |
| Quên release khi offer fail | Permit leak | `finally` |
| Consumer exception và bỏ job | Business job loss | Retry/durable/error policy |
| Queue.clear bypass wrapper | Leak permits và mất jobs | Single-owner API |
| Busy retry khi reject | CPU spin/retry storm | Bounded wait/backoff |
| `put` vô hạn trong HTTP handler | Hàng nghìn threads block | Admission deadline và producer limit |
| Giới hạn số item nhưng quên payload size | Memory spike | Byte budget và max body |
| Chỉ đo depth, không đo age | Tail latency cao mà khó phát hiện | Oldest age và wait percentiles |
| Rate limiter cố định khi downstream tụt năng lực | Queue vẫn phình | Bound và feedback |
| Shutdown trước khi xử lý jobs đã accepted | Mất việc/permit leak | Drain/terminal handling có deadline |
| Drop critical jobs âm thầm | Không ACK, mất dữ liệu | Explicit reject hoặc durable handoff |

## 15. Câu hỏi tự kiểm tra

**1.** `ConcurrentLinkedQueue` là thread-safe; tại sao vẫn OOM?  
**Đáp án:** Queue unbounded, giữ reference tới items; nếu vào nhanh hơn ra đủ lâu, memory tăng.

**2.** `new LinkedBlockingQueue<>()` có capacity mặc định?  
**Đáp án:** `Integer.MAX_VALUE`, không phải quota heap hợp lý.

**3.** `ArrayBlockingQueue<>(2)` đã có A,B, `offer(C)`?  
**Đáp án:** `false` ngay nếu không có consumer song song.

**4.** `put(C)` khi bounded queue đầy?  
**Đáp án:** Block chờ space hoặc bị interrupt; không tự timeout.

**5.** `offer(C,100,TimeUnit.MILLISECONDS)` khi đầy?  
**Đáp án:** Chờ tối đa deadline, trả false khi hết thời gian; có thể bị interrupt.

**6.** `queue.size()<limit` rồi offer có tạo hard bound?  
**Đáp án:** Không. Hai producers có thể race; CLQ size còn O(n) và có thể không chính xác.

**7.** Nếu producers 150/s, consumers 100/s trong 60s thì backlog?  
**Đáp án:** Tăng cỡ 3000 jobs nếu bỏ qua biến động, rejects và các yếu tố khác.

**8.** Semaphore giúp gì?  
**Đáp án:** `tryAcquire` tạo reservation atomic trước enqueue; hết quota thì không nhận job.

**9.** Consumer poll job nhưng chưa xử lý xong; khi nào release?  
**Đáp án:** Với outstanding bound, chỉ sau terminal handling; queue-only bound có thể release sau poll.

**10.** Nếu offer throw sau acquire?  
**Đáp án:** Release permit trong finally.

**11.** Nếu callback success và timeout cùng release?  
**Đáp án:** Double release phá quota; dùng AtomicBoolean/CAS hoặc state machine.

**12.** `newFixedThreadPool(4)` có bounded waiting queue?  
**Đáp án:** Không. Số workers cố định, queue mặc định unbounded.

**13.** `maximumPoolSize` lớn có luôn cứu unbounded work queue?  
**Đáp án:** Không, pool có thể queue sau core mà không tăng workers.

**14.** `CallerRunsPolicy` luôn là giải pháp tốt?  
**Đáp án:** Không, nó giữ caller thread và có thể vi phạm deadline/context.

**15.** `ConcurrentLinkedQueue.poll()` có đợi khi rỗng?  
**Đáp án:** Không, trả null; cần wakeup riêng hoặc BlockingQueue.

**16.** Bounded queue tự bảo đảm không bao giờ OOM?  
**Đáp án:** Không. Job có thể rất lớn; còn threads, in-flight jobs, caches và buffers.

**17.** Chỉ rate limit 100/s có đủ nếu DB tụt xuống 10/s?  
**Đáp án:** Không, backlog vẫn tăng nếu admission vượt service rate.

**18.** Khi producer bị reject, busy-spin retry có lợi?  
**Đáp án:** Không. Gây CPU load và retry storm; dùng backoff/deadline.

**19.** Vì sao không được clear raw queue khi có semaphore reservations?  
**Đáp án:** Mất jobs và permit accounting lệch; cần settle từng job.

**20.** Permit release chứng minh job commit thành công?  
**Đáp án:** Không, đó chỉ là accounting; cần ACK, retry/durability và idempotency theo nghiệp vụ.

**21.** Queue RAM có phục hồi accepted jobs sau crash?  
**Đáp án:** Không. Dùng durable broker/DB nếu cần recovery.

**22.** Metrics nào nên theo dõi ngoài depth?  
**Đáp án:** Oldest age, wait p95/p99, throughput, rejects, in-flight, heap/GC, downstream latency.

## 16. Checklist triển khai

- [ ] Xác minh queue bounded hay unbounded theo constructor thực.
- [ ] Không đánh đồng thread-safe với bounded resource usage.
- [ ] Đo arrival rate, service rate, backlog growth và time-in-queue.
- [ ] Chọn capacity theo memory/latency budget và degraded throughput.
- [ ] Ưu tiên `ArrayBlockingQueue`/`LinkedBlockingQueue(capacity)` khi phù hợp.
- [ ] Nếu CLQ bắt buộc, mọi producer đi qua `Semaphore.tryAcquire`.
- [ ] Acquire trước enqueue; release khi enqueue failure.
- [ ] Phân biệt queued-only và queued+in-flight bound.
- [ ] Mọi accepted job có terminal outcome, permit release đúng một lần.
- [ ] Không bypass queue wrapper bằng clear/remove/raw enqueue.
- [ ] Không dùng `size()+offer` hay `availablePermits()+offer` làm gate.
- [ ] Có timed admission/reject/backoff, không infinite busy retry.
- [ ] Không giữ vô hạn request threads trong `put`.
- [ ] Giới hạn payload bytes và active producers/workers.
- [ ] Với executor, dùng bounded work queue hoặc external admission.
- [ ] Có policy rejection rõ; không silent drop jobs quan trọng.
- [ ] Có idempotency và retries có giới hạn nếu client timeout.
- [ ] Có durability và quota nếu job không được mất qua crash.
- [ ] Metrics gồm oldest-age, rejects, throughput, tail latency, RAM/GC.
- [ ] Shutdown stop-admitting trước, drain/terminal handling đến deadline.
- [ ] Test full/empty/racing producers, timeout, double finish, consumer fail, stop race và crash.
- [ ] Chỉ áp dụng Java concurrency API hiện hành, không dùng hướng dẫn legacy.

## 17. Tài liệu chính thức Java SE 21

- [ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): unbounded FIFO, nonblocking, `size` không O(1) và không luôn chính xác khi concurrent mutation.
- [LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): capacity mặc định `Integer.MAX_VALUE`, bounded constructor, offer/put.
- [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): fixed-capacity FIFO buffer, fairness, offer/put/take.
- [BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): operations và timeout/interruption contracts.
- [Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html): permits, tryAcquire và release.
- [ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queueing, worker limits, rejection policies.
- [Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): fixed thread pools.
- [ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown và awaitTermination.
- [LinkedTransferQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedTransferQueue.html): transfer queue unbounded.
- [PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): logically unbounded priority queue.
- [AtomicBoolean](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html): atomic terminal settlement.
- [CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): test state transitions mà không cần sleep.

**Kết luận:** queue unbounded có thể rất nhanh và thread-safe khi nhẹ tải, nhưng **không tự chống backlog, memory growth hay tail latency**. Dùng bounded queue có admission policy hoặc `Semaphore` chặn trước một queue bắt buộc giữ unbounded. Bound phải đi kèm handling cho fail/timeout/retry/shutdown, quản lý permits chính xác và đo queue age/throughput. Mục tiêu không phải nhận mọi job, mà là giữ hệ thống **ổn định, có giới hạn tài nguyên và báo quá tải có nghĩa** trên JDK hiện đại.
