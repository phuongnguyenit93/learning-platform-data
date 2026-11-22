# Pipeline có backpressure bằng LinkedBlockingDeque — Thực hành Java 17+

## 1. Tình huống thực tế và mục tiêu

Một service Java nhận dữ liệu từ HTTP, file hoặc message broker. Producer tạo công việc nhanh, nhưng consumers phải gọi database, xử lý ảnh hoặc gửi RPC chậm hơn. Nếu producer vẫn enqueue vô hạn, backlog có thể tăng mãi và gây:

- Giữ hàng nghìn payloads trong heap, tăng thời gian GC và nguy cơ `OutOfMemoryError`.
- Queue waiting latency lớn đến mức kết quả không còn hữu ích khi được xử lý.
- Request upstream được xác nhận “accepted” nhưng thực tế không có khả năng phục vụ đúng deadline.
- Các threads và futures tích tụ trước hoặc sau queue, che giấu tắc nghẽn thật.

**Backpressure** là cơ chế buộc upstream phải phản ứng trước năng lực xử lý của downstream: **chờ khi hết chỗ**, **từ chối có kiểm soát**, **giảm tốc** hoặc chuyển sang một durable channel được thiết kế phù hợp.

Trong một JVM, `java.util.concurrent.LinkedBlockingDeque<E>` có constructor với **capacity hữu hạn** và các thao tác blocking/timed. Nó rất phù hợp cho pipeline producer–consumer đơn giản, kể cả pipeline hai tầng. Các API dưới đây thuộc `java.base`, còn được dùng trong **Java SE 25** và mã mẫu **biên dịch với Java 17**.

Sau bài học này, bạn có thể:
1. Phân biệt `putLast`, `offerLast`, `offerLast(timeout)` và `takeFirst`.
2. Tạo hàng đợi **bounded** và chứng minh được producer bị chặn khi queue đầy.
3. Dùng timeout để phản hồi overload mà không âm thầm bỏ việc.
4. Xây hai workers tiêu thụ jobs và shutdown sạch bằng STOP markers.
5. Tạo hai bounded queues để thấy backpressure **lan ngược** qua nhiều stages.
6. Xử lý interruption, race, lỗi worker, retry, idempotency và những giới hạn về durability.
7. Quan sát queue depth, offer timeout, queue latency và downstream saturation.

## 2. Cấu trúc của một pipeline bounded

~~~text
   Producer (có thể nhanh hơn consumer)
      |
      | putLast(job) hoặc offerLast(job, timeout)
      v
   +-------------------------------------+
   | LinkedBlockingDeque<Job>(capacity=2)|
   |    [Job 1]  [Job 2]                 |
   +-------------------------------------+
          |
          | takeFirst() -> giải phóng 1 slot
          v
   Consumer / bounded worker pool
          |
          v
   Database / file / API / output sink

   Nếu deque đầy: producer phải chờ hoặc nhận false.
   Nếu deque rỗng: consumer takeFirst() sẽ chờ.
~~~

Cơ chế này làm chậm chính thread đang `putLast`, thay vì tạo thêm một in-memory buffer vô hạn. Nhưng **capacity chỉ giới hạn phần tử đang nằm trong deque**. Nó không bao gồm jobs đã được consumers lấy và đang xử lý, pending Futures trong một thread pool khác, HTTP requests hoặc các bytes do upstream giữ.

### Bounded khác unbounded

~~~java
LinkedBlockingDeque<String> bounded = new LinkedBlockingDeque<>(128);
LinkedBlockingDeque<String> riskyDefault = new LinkedBlockingDeque<>();
~~~

Đây là **snippet trong method**, không phải file độc lập; cần import `LinkedBlockingDeque`. Constructor không đối số có capacity `Integer.MAX_VALUE`; về thực tế nó không ngăn queue mở rộng đến giới hạn heap. Hãy truyền **capacity ≥ 1** (capacity 0 hoặc âm làm constructor ném `IllegalArgumentException`), chọn dựa trên payload memory/latency/downstream budget.

Một slot chỉ chứa **một object reference tới job**: nếu job giữ một byte array 10 MB thì 128 slots có thể giữ object graphs cực lớn. Đừng coi hàng đợi “128 phần tử” là ngân sách 128 bytes.

## 3. Vì sao là Deque thay vì Queue?

`LinkedBlockingDeque` implements `BlockingDeque`, `BlockingQueue` và `Deque`; nó có **đầu** và **cuối**. Hướng mặc định cho pipeline FIFO:

~~~text
putLast(A) -> [A]
putLast(B) -> [A, B]
putLast(C) -> [A, B, C]

takeFirst() -> A
takeFirst() -> B
takeFirst() -> C
~~~

Có thể dùng `putFirst` hoặc `offerFirst` để chèn gấp, và `takeLast` để lấy cuối, nhưng **những lựa chọn đó làm thay đổi thứ tự**. Một queue dùng hai đầu **vẫn chia sẻ một capacity duy nhất**; không có một quota riêng cho đầu và quota riêng cho cuối.

Nếu không cần hai đầu, `ArrayBlockingQueue` hoặc `LinkedBlockingQueue(capacity)` cũng có thể phù hợp. Sự khác biệt chính của bài là chọn `LinkedBlockingDeque` để vừa hỗ trợ FIFO, vừa có khả năng xây ưu tiên/retry có chủ đích khi cần.

## 4. Những thao tác gây backpressure

Các hình thức xử lý khi **queue đầy**:

| Method | Nếu có chỗ | Nếu đầy |
| --- | --- | --- |
| `addLast(e)` | Thêm ở cuối | Ném `IllegalStateException` |
| `offerLast(e)` | Trả `true` | Trả `false` ngay |
| `putLast(e)` | Thêm ở cuối | **Chờ** có chỗ hoặc bị interrupted |
| `offerLast(e,t,unit)` | Trả `true` | Chờ tới deadline, rồi `false` |
| `addFirst(e)` | Thêm ở đầu | Ném `IllegalStateException` |
| `offerFirst(e)` | Trả `true` | Trả `false` ngay |
| `putFirst(e)` | Thêm ở đầu | Chờ có chỗ hoặc bị interrupted |
| `offerFirst(e,t,unit)` | Trả `true` | Chờ tới deadline, rồi `false` |

Khi **queue rỗng**:

| Method | Nếu có việc | Nếu rỗng |
| --- | --- | --- |
| `takeFirst()` | Lấy và xóa phần tử đầu | **Chờ** hoặc InterruptedException |
| `pollFirst()` | Lấy/xóa | Trả `null` ngay |
| `pollFirst(t,unit)` | Lấy/xóa | Chờ deadline, rồi `null` |
| `removeFirst()` | Lấy/xóa | `NoSuchElementException` |
| `peekFirst()` | Xem, không xóa | Trả `null` |
| `takeLast()` | Lấy/xóa phần tử cuối | Chờ hoặc bị interrupted |

`put(e)` của `BlockingQueue` tương đương `putLast(e)`; `take()` tương đương `takeFirst()` khi dùng `BlockingDeque`. API **cấm null elements**; `putLast(null)` ném `NullPointerException`. Vì vậy `null` của `pollFirst(timeout)` có nghĩa “không có phần tử được lấy trong thời gian chờ”, không phải job null hợp lệ.

### Chọn API theo SLA

- **Background ETL** có thể chờ: `putLast` tạo tín hiệu backpressure rất rõ.
- **HTTP ingress có deadline**: `offerLast(job,100,TimeUnit.MILLISECONDS)` để tránh treo thread quá lâu.
- **Best-effort telemetry**: `offerLast(job)` và đếm dropped/rejected nếu policy cho phép.
- **Critical transactions**: không ack thành công chỉ vì đã đặt vào deque trong RAM; cần durable commit/ack trước, hoặc durable broker.

~~~java
boolean accepted = queue.offerLast(job, 200, TimeUnit.MILLISECONDS);
if (!accepted) {
    // Từ chối quá tải hoặc chuyển sang durable queue theo policy.
}
~~~

Đây là **snippet trong method** có biến `queue`/`job`, import `TimeUnit` và xử lý `InterruptedException`. `false` là overload có ý nghĩa, **không được im lặng bỏ job** rồi trả thành công cho bên gửi. Retry cũng phải có giới hạn và backoff, nếu không sẽ tạo retry storm.

## 5. Thực hành số 1 — queue đầy, producer bị block, timeout và interrupt

Mục tiêu: chứng minh cơ chế `putLast` thật sự bị chặn khi không có capacity, rồi tự tiếp tục sau khi `takeFirst` giải phóng một slot. Đồng thời kiểm `offerLast` và interruption.

**File `DequeBackpressureBasics.java` — chương trình độc lập Java 17+:**

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public final class DequeBackpressureBasics {
    public static void main(String[] args) throws Exception {
        LinkedBlockingDeque<String> deque = new LinkedBlockingDeque<>(1);
        deque.putLast("first");
        System.out.println("bounded queue full: " + (deque.size() == 1));
        System.out.println("offerLast rejects immediately: "
                + !deque.offerLast("second"));
        System.out.println("offerLast times out on full queue: "
                + !deque.offerLast("second", 100, TimeUnit.MILLISECONDS));

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            CountDownLatch started = new CountDownLatch(1);
            Future<?> future = executor.submit(() -> {
                started.countDown();
                try {
                    deque.putLast("second");
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(interrupted);
                }
            });
            if (!started.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Producer did not start");
            }

            boolean blocked;
            try {
                future.get(100, TimeUnit.MILLISECONDS);
                blocked = false;
            } catch (TimeoutException expected) {
                blocked = true;
            }
            System.out.println("putLast waits for a slot: " + blocked);
            System.out.println("first item consumed: "
                    + "first".equals(deque.takeFirst()));
            future.get(2, TimeUnit.SECONDS);
            System.out.println("producer resumed: " + future.isDone());
            System.out.println("second item consumed: "
                    + "second".equals(deque.takeFirst()));
            System.out.println("queue drained: " + deque.isEmpty());
        } finally {
            executor.shutdownNow();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }

        LinkedBlockingDeque<String> interruptedQueue =
                new LinkedBlockingDeque<>(1);
        interruptedQueue.putLast("reserved");
        AtomicBoolean sawInterrupt = new AtomicBoolean();
        CountDownLatch entered = new CountDownLatch(1);
        Thread blockedProducer = new Thread(() -> {
            entered.countDown();
            try {
                interruptedQueue.putLast("not-inserted");
            } catch (InterruptedException expected) {
                sawInterrupt.set(true);
                Thread.currentThread().interrupt();
            }
        }, "interruptible-producer");
        blockedProducer.start();
        if (!entered.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Interrupt test did not start");
        }
        blockedProducer.interrupt();
        blockedProducer.join(2000);
        if (blockedProducer.isAlive()) {
            throw new IllegalStateException("Producer failed to stop");
        }
        System.out.println("blocked putLast handles interruption: "
                + sawInterrupt.get());
        System.out.println("interrupted item was not inserted: "
                + (interruptedQueue.size() == 1
                && "reserved".equals(interruptedQueue.peekFirst())));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 DequeBackpressureBasics.java
java DequeBackpressureBasics
~~~

**Stdout chính xác** đã kiểm thử trên OpenJDK 24.0.2 với `javac --release 17`:

~~~text
bounded queue full: true
offerLast rejects immediately: true
offerLast times out on full queue: true
putLast waits for a slot: true
first item consumed: true
producer resumed: true
second item consumed: true
queue drained: true
blocked putLast handles interruption: true
interrupted item was not inserted: true
~~~

### Giải thích bằng timeline

~~~text
t0: queue capacity=1; putLast(first) -> [first]
t1: offerLast(second) -> false, không thay queue
t2: timed offerLast(second,100ms) -> false sau deadline
t3: worker gọi putLast(second), phải chờ
t4: main Future.get(100ms) -> TimeoutException, worker chưa hoàn tất
t5: main takeFirst() -> first, giải phóng một slot
t6: worker tiếp tục putLast(second) -> [second]
t7: main takeFirst() -> second; queue rỗng
~~~

`Future.get(timeout)` chỉ **hết thời gian chờ lấy kết quả**, **không tự hủy worker**. Trong test, sau khi lấy `first`, chúng ta vẫn gọi `future.get` để xác nhận producer hoàn tất. Đoạn interrupt ở cuối dùng một deque riêng, luôn đầy và không có consumer, nên thread bị ngắt đang đợi có chỗ; nó xử lý `InterruptedException` rồi kết thúc. Không dùng `Thread.stop()` hoặc spin-wait.

**Tính xác định của test:** các `CountDownLatch` tạo ranh giới hoạt động, queue full là trạng thái có chủ đích. Dù vậy một runtime quá chậm hoặc CI bị treo có thể ảnh hưởng timeout 100 ms; điều chỉnh test deadlines theo môi trường, tránh biến timing thành một lời hứa scheduler tuyệt đối.

## 6. Thực hành số 2 — nhiều consumers, overload có deadline, graceful shutdown

Một pipeline thực tế có thể có một producer và hai consumers. Hàng đợi là `BlockingDeque<Job>` capacity 2; consumer threads được giữ chờ lúc đầu để thử overload rồi mới cho xử lý. Producer gửi đúng 6 jobs có ID 1..6.

**Giao thức chính:**
1. Khởi chạy hai fixed consumers nhưng khóa ở `mayConsume.await()`.
2. Enqueue 1,2, queue đầy; thử offer job3 trả false ngay và sau deadline.
3. Thả `mayConsume`; enqueue 3..6 bằng timed offer, kiểm từng kết quả.
4. Đợi `CountDownLatch completed` xác nhận 6 jobs đi hết processing logic demo.
5. Enqueue **hai STOP markers không-null** ở **cuối** deque, mỗi consumer một marker.
6. Đợi workers Future, shutdown executor và kiểm queue empty.

### File BoundedPipelineDemo.java

~~~java
import java.util.Set;
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class BoundedPipelineDemo {
    private record Job(int id, boolean stop) {}
    private static final Job STOP = new Job(-1, true);
    private static final int WORKERS = 2;
    private static final int TOTAL = 6;

    public static void main(String[] args) throws Exception {
        BlockingDeque<Job> queue = new LinkedBlockingDeque<>(2);
        CountDownLatch mayConsume = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(TOTAL);
        Set<Integer> ids = ConcurrentHashMap.newKeySet();
        AtomicInteger duplicates = new AtomicInteger();
        AtomicInteger stopSignals = new AtomicInteger();
        ExecutorService consumers = Executors.newFixedThreadPool(WORKERS);
        boolean successful = false;
        try {
            Future<?>[] workers = new Future<?>[WORKERS];
            for (int i = 0; i < workers.length; i++) {
                workers[i] = consumers.submit(() -> {
                    try {
                        mayConsume.await();
                        while (true) {
                            Job job = queue.takeFirst();
                            if (job.stop()) {
                                stopSignals.incrementAndGet();
                                return;
                            }
                            if (!ids.add(job.id())) {
                                duplicates.incrementAndGet();
                            }
                            completed.countDown();
                        }
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            queue.putLast(new Job(1, false));
            queue.putLast(new Job(2, false));
            System.out.println("configured capacity: 2");
            System.out.println("prefill reaches capacity: "
                    + (queue.size() == 2));
            System.out.println("immediate overload rejected: "
                    + !queue.offerLast(new Job(3, false)));
            System.out.println("deadline overload rejected: "
                    + !queue.offerLast(new Job(3, false),
                            100, TimeUnit.MILLISECONDS));

            mayConsume.countDown();
            for (int id = 3; id <= TOTAL; id++) {
                boolean accepted = queue.offerLast(
                        new Job(id, false), 3, TimeUnit.SECONDS);
                if (!accepted) {
                    throw new IllegalStateException("Job " + id + " not accepted");
                }
            }
            boolean completedInTime = completed.await(5, TimeUnit.SECONDS);
            if (!completedInTime) {
                throw new IllegalStateException("Processing deadline exceeded");
            }
            for (int i = 0; i < WORKERS; i++) {
                boolean sent = queue.offerLast(STOP, 3, TimeUnit.SECONDS);
                if (!sent) {
                    throw new IllegalStateException("Could not send STOP");
                }
            }
            for (Future<?> worker : workers) {
                worker.get(5, TimeUnit.SECONDS);
            }
            consumers.shutdown();
            successful = consumers.awaitTermination(5, TimeUnit.SECONDS);

            boolean allIds = ids.equals(Set.of(1, 2, 3, 4, 5, 6));
            System.out.println("all six accepted jobs completed: "
                    + completedInTime);
            System.out.println("exactly ids 1..6 seen: " + allIds);
            System.out.println("no duplicate processing: "
                    + (duplicates.get() == 0));
            System.out.println("one stop signal per worker: "
                    + (stopSignals.get() == WORKERS));
            System.out.println("queue empty after shutdown: "
                    + queue.isEmpty());
            System.out.println("workers terminated: " + successful);
        } finally {
            mayConsume.countDown();
            if (!successful) {
                consumers.shutdownNow();
                if (!consumers.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Workers stuck on shutdown");
                }
            }
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 BoundedPipelineDemo.java
java BoundedPipelineDemo
~~~

**Stdout chính xác** trên OpenJDK 24.0.2:

~~~text
configured capacity: 2
prefill reaches capacity: true
immediate overload rejected: true
deadline overload rejected: true
all six accepted jobs completed: true
exactly ids 1..6 seen: true
no duplicate processing: true
one stop signal per worker: true
queue empty after shutdown: true
workers terminated: true
~~~

### Giải thích kết quả

- `queue.size()==2` lúc consumers đang chờ chứng minh queue đã đầy.
- Một lời gọi `offerLast` fail **không làm biến mất job đã nhận**: trong demo, job 3 chưa được chấp nhận ở lần thử đầu, rồi được gửi lại **đúng một lần** sau khi đã thả consumers.
- `ConcurrentHashMap.newKeySet()` hỗ trợ hai consumers ghi nhận IDs an toàn; `AtomicInteger` đếm duplicate và số stop markers.
- `CountDownLatch completed` được giảm sau khi mỗi job đi qua logic xử lý demo; production chỉ nên đánh dấu completed khi business operation đã có kết quả rõ ràng.
- STOP là một `record Job(-1,true)`, không phải null; được enqueue sau khi cả 6 jobs đã hoàn tất và không còn producer gửi thêm.
- `ExecutorService.shutdown()` được gọi sau khi đã gửi STOP; worker `takeFirst()` không tự thoát chỉ vì executor shutdown.
- `shutdownNow()` trong `finally` là **emergency cleanup nếu bài test lỗi**, không phải lối shutdown bình thường đảm bảo không mất jobs.

**Một chú ý quan trọng:** `takeFirst` chỉ đảm bảo một queue element được **một consumer** remove, **không** đảm bảo business side effect đúng một lần. Consumer có thể chết sau take trước DB commit; job đã bị remove và có thể mất. Nếu cần durable exactly-once-like behavior, phải dùng persistent broker/transactional outbox, acknowledgment, idempotent processing và reconciliation.

## 7. Thực hành số 3 — Backpressure lan ngược qua hai tầng

Một hàng đợi bounded đơn lẻ chưa phản ánh hết pipeline. Hãy nối **hai deque capacity 1**:

~~~text
Producer
   | input.putLast(d)
   v
[Input queue, capacity=1]        [c]
   |
Stage A: takeFirst -> transform -> output.putLast
   |  đã lấy b, nhưng BLOCKED vì output full
   v
[Output queue, capacity=1]       [a]
   |
Stage B bị giữ chờ
   |
   v
Final consumer
~~~

Trình tự có thể dựng deterministic bằng latches:
- Stage A đưa `a` vào output.
- Stage B chưa được phép consume, nên output vẫn đầy.
- Stage A lấy `b`, cố đưa vào output nhưng **bị block**.
- Producer đưa `c` vào input, làm input đầy.
- Producer thứ hai cố đưa `d` vào input và **bị block**, dù nó không giao tiếp trực tiếp với Stage B.
- Khi cho Stage B chạy, áp lực được giải phóng từ dưới lên, và cả bốn item được xử lý theo FIFO.

### File TwoStageBackpressureDemo.java

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class TwoStageBackpressureDemo {
    public static void main(String[] args) throws Exception {
        LinkedBlockingDeque<String> input = new LinkedBlockingDeque<>(1);
        LinkedBlockingDeque<String> output = new LinkedBlockingDeque<>(1);
        CountDownLatch forwardedFirst = new CountDownLatch(1);
        CountDownLatch secondTaken = new CountDownLatch(1);
        CountDownLatch downstreamAllowed = new CountDownLatch(1);
        CountDownLatch upstreamStarted = new CountDownLatch(1);
        List<String> results = new ArrayList<>();
        ExecutorService executor = Executors.newFixedThreadPool(3);
        boolean finished = false;
        try {
            Future<?> stageOne = executor.submit(() -> {
                try {
                    for (int index = 0; index < 4; index++) {
                        String item = input.takeFirst();
                        if (index == 1) secondTaken.countDown();
                        output.putLast(item);
                        if (index == 0) forwardedFirst.countDown();
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(interrupted);
                }
            });
            Future<?> stageTwo = executor.submit(() -> {
                try {
                    downstreamAllowed.await();
                    for (int i = 0; i < 4; i++) {
                        results.add(output.takeFirst());
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(interrupted);
                }
            });

            input.putLast("a");
            if (!forwardedFirst.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First forwarding timed out");
            }
            input.putLast("b");
            if (!secondTaken.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Second forwarding did not start");
            }
            input.putLast("c");
            Future<?> upstream = executor.submit(() -> {
                upstreamStarted.countDown();
                try {
                    input.putLast("d");
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(interrupted);
                }
            });
            if (!upstreamStarted.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Upstream producer did not start");
            }
            System.out.println("downstream buffer full: "
                    + (output.size() == 1));
            System.out.println("upstream buffer full: "
                    + (input.size() == 1));
            boolean blocked;
            try {
                upstream.get(150, TimeUnit.MILLISECONDS);
                blocked = false;
            } catch (TimeoutException expected) {
                blocked = true;
            }
            System.out.println("upstream blocked by downstream: " + blocked);

            downstreamAllowed.countDown();
            upstream.get(3, TimeUnit.SECONDS);
            stageOne.get(3, TimeUnit.SECONDS);
            stageTwo.get(3, TimeUnit.SECONDS);
            executor.shutdown();
            finished = executor.awaitTermination(3, TimeUnit.SECONDS);
            System.out.println("producer resumed after release: "
                    + upstream.isDone());
            System.out.println("FIFO across two stages: "
                    + results.equals(List.of("a", "b", "c", "d")));
            System.out.println("both buffers drained: "
                    + (input.isEmpty() && output.isEmpty()));
            System.out.println("all threads terminated: " + finished);
        } finally {
            downstreamAllowed.countDown();
            if (!finished) {
                executor.shutdownNow();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Threads did not stop");
                }
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TwoStageBackpressureDemo.java
java TwoStageBackpressureDemo
~~~

**Stdout chính xác** đã xác minh trên OpenJDK 24.0.2, `javac --release 17`:

~~~text
downstream buffer full: true
upstream buffer full: true
upstream blocked by downstream: true
producer resumed after release: true
FIFO across two stages: true
both buffers drained: true
all threads terminated: true
~~~

Dòng `upstream blocked by downstream: true` chính là **bằng chứng lan truyền backpressure**: producer cuối không bị chặn bởi Stage B trực tiếp, mà do Stage B chậm → output queue đầy → Stage A không chuyển được `b` → input queue đầy → producer không đưa được `d`.

**Chỉ một Stage A và một Stage B** nên ví dụ giữ FIFO đơn giản. Nếu nhiều consumers song song, **thứ tự lấy deque** có thể là FIFO nhưng **thứ tự hoàn tất** có thể khác. Cần per-key ordering/partition hoặc sequence-aware sink khi business đòi hỏi ordering.

## 8. Thiết kế shutdown cho pipeline chạy liên tục

`LinkedBlockingDeque` **không có close() để đánh dấu end-of-stream**; một worker `takeFirst()` có thể chờ vô hạn khi không còn jobs. Lệnh `ExecutorService.shutdown()` chỉ dừng nhận các **task submissions vào executor**, **không tự đánh thức** worker đang block trên một deque riêng.

Giao thức dừng an toàn khi dùng STOP markers:

~~~text
RUNNING
   |
   +-> Ngừng nhận job mới (admission closed)
   |
   +-> Đợi mọi producer không còn gửi queue
   |
   +-> Đợi hoặc bảo đảm những jobs đã nhận được xử lý/ack
   |
   +-> putLast(STOP) / offerLast(STOP, deadline)
       một marker cho MỖI worker
   |
   +-> Worker nhận STOP từ takeFirst và thoát
   |
   +-> Future.get / executor.shutdown / awaitTermination
   |
   +-> Kiểm remaining queue + outstanding business work
   v
TERMINATED
~~~

STOP marker còn được gọi là **poison pill** trong một số thiết kế producer–consumer. Đây **không phải null**; dùng một object/record sentinel có field rõ. Với hai consumers, đặt **hai markers ở tail** để hai workers đều có thể kết thúc. Không đẩy STOP lên đầu bằng `putFirst` khi còn jobs cần drain, vì STOP có thể vượt công việc.

**Không gửi STOP khi producer còn được phép ghi job mới**: một job có thể được enqueue sau marker, lúc đó workers đã rời đi. Cần barrier/lifecycle flag ngăn việc mới trước khi dừng. Khi deque đầy, gửi marker cũng có thể phải chờ; dùng bounded deadline và kế hoạch fallback.

Nếu worker chết trước khi nhận marker, hoặc một công việc đang xử lý bị treo, graceful shutdown có thể không hoàn tất trong deadline. `shutdownNow()` chỉ là best-effort interrupt: nó **không** cung cấp transactional rollback hay cam kết đã xử lý hết các jobs. Chỉ gọi “graceful” khi biết được trạng thái của tất cả công việc được nhận.

### Khi nào dùng pollFirst thay takeFirst?

~~~java
while (!Thread.currentThread().isInterrupted()) {
    Job next = queue.pollFirst(250, TimeUnit.MILLISECONDS);
    if (next == null) {
        // Không có phần tử trước deadline, kiểm shutdown flag rồi tiếp tục.
        continue;
    }
    process(next);
}
~~~

Đây là snippet trong method đã có `Job`, `queue` và `process`, cần xử lý `InterruptedException`. Ưu điểm: định kỳ kiểm lifecycle flag. Nhược điểm: có polling latency và phải xử lý race với producers. STOP markers hoặc đúng cancellation protocol thường rõ ràng hơn trong finite pipeline.

## 9. InterruptedException và cancellation đúng cách

Các thao tác chặn như `putLast`, `takeFirst` và timed `offerLast` có thể ném `InterruptedException`. Nguyên tắc là **propagate** nếu method cho phép hoặc **đặt lại interrupt flag rồi dừng** nếu tầng hiện tại không thể ném tiếp:

~~~java
try {
    queue.putLast(job);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return; // Dừng method, không tiếp tục vòng lặp bỏ qua interrupt.
}
~~~

Đây là snippet trong method trả void; `job`, `queue` có sẵn. Không dùng vòng `while(true)` bắt InterruptedException rồi bỏ qua: worker có thể không bao giờ dừng, khiến shutdown timeout.

Interruption khi đang chờ chỗ và interruption **sau khi consumer đã lấy job** có hậu quả khác nhau. Nếu consumer đã take job nhưng bị gián đoạn giữa transaction, **deque không tự đưa job trở lại**. Cần quyết định rollback, idempotency, retry hoặc dead-letter ở lớp nghiệp vụ. Không coi việc deque thread-safe là exactly-once delivery.

## 10. FIFO, priority, retry và starvation

Đối với FIFO, producer **thêm ở tail** và consumer **lấy ở head**. Khi dùng `offerFirst` cho urgent job hoặc retry, bạn chèn phần tử vượt các jobs đang đợi. Điều này có thể hợp lý với ưu tiên nhỏ nhưng nguy hiểm:

- Jobs bình thường có thể bị **starvation** nếu một luồng liên tục chèn retries vào head.
- FIFO per-key có thể bị vi phạm, khiến business state update sai.
- Retry ngay có thể lặp lỗi liên tục trong khi downstream chưa hồi phục.
- `offerFirst` có thể false nếu queue đầy; code vẫn phải có fallback.
- Requeue đã xử lý một phần có thể tạo duplicate side effects.

Thay vì retry vô hạn ở head, nên có `maxAttempts`, delayed retry scheduling/backoff, idempotency key, dead-letter và cơ chế kiểm soát tải. `LinkedBlockingDeque` **không phải delayed scheduler** và không có built-in retry semantics.

`LinkedBlockingDeque` cũng **không có fairness constructor**; đừng hứa rằng producer bị block lâu nhất chắc chắn được cấp slot trước hoặc consumers luôn được phục vụ theo thứ tự đăng ký. FIFO của các **phần tử đã nhận** khác fairness giữa các **threads đang tranh capacity**.

## 11. Quan hệ happens-before và an toàn dữ liệu

Theo Javadoc `BlockingDeque`, những hành động của thread trước khi đặt một object vào deque **happen-before** những hành động của consumer sau khi truy cập/lấy phần tử đó. Đây là công cụ **safe publication** cho producer–consumer.

~~~java
record Event(int id, String body) {}
Event event = new Event(42, "ready");
queue.putLast(event);
// Thread consumer khác: Event received = queue.takeFirst();
~~~

Đây là snippet minh họa trong method với biến queue kiểu phù hợp; `record` có trong Java 17. Tuy nhiên, queue chỉ đảm bảo việc đồng bộ khi bàn giao. Nếu producer tiếp tục **sửa mutable payload sau enqueue**, có thể có race; ưu tiên immutable records/DTOs hoặc explicit ownership transfer.

Thread-safe queue không tự làm thread-safe business objects, counters hoặc DB writes. Trong ví dụ 2, IDs nằm trong concurrent set, counters là atomic, và `CountDownLatch` quản lý completion signal. Trong ví dụ 3, một thread duy nhất ghi `ArrayList results`, còn main đọc sau `Future.get()` — đó là một synchronization boundary hợp lệ.

## 12. Capacity và đo lường tải

Một queue capacity `C` giới hạn **queued items**, không phải total in-flight:

~~~text
producer/pending HTTP request  [ngoài deque]
               |
         deque capacity 50     [tối đa 50 đang chờ]
               |
           8 consumers         [có thể thêm 8 đang chạy]
               |
         DB connection pool    [giới hạn riêng]
~~~

Cần tính cả những buffers/threads phía trước và phía sau. Nếu muốn một tổng in-flight cap, dùng `Semaphore` như admission permit được giữ tới khi job hoàn tất, hoặc thiết kế bounded pipeline xuyên các stages.

### Chọn capacity theo SLO, không đoán mò

- `queueCapacity`: memory budget, maximum payload size, burst characteristics.
- `workerCount`: throughput và giới hạn downstream DB/RPC.
- `maxQueueWait`: thời gian tối đa job được phép chờ trước khi trở nên stale.
- `offerTimeout`: deadline upstream có thể chờ mà không gây timeout dây chuyền.
- `rejectionPolicy`: fail fast, 429/503, bounded retry, durable handoff hoặc sampling/drop được định nghĩa.
- `drainTimeout`: thời gian deploy/shutdown cho phép pipeline hoàn tất.

Little’s law `L = λ × W` giúp ước tính mean in-flight count từ arrival/throughput và mean total time ở hệ thống ổn định. Ví dụ 200 jobs/s × 0,1 s ≈ 20 jobs trung bình trong hệ thống, **không có nghĩa phải đặt queue capacity chính xác 20**. Distribution tail latency, capacity và overload policy đều cần đo.

### Metrics nên đo

| Metric | Mục đích |
| --- | --- |
| `queue_depth`/`remaining_capacity` | Biết queue bão hòa |
| `queue_wait_seconds` | Độ trễ từ enqueue tới dequeue |
| `offer_wait_seconds` | Producer phải chờ bao lâu |
| `offer_timeout_total`/`rejected_total` | Số jobs từ chối có chủ đích |
| `processing_duration_seconds` | Thời gian thực thi và downstream latency |
| `worker_active`/`worker_failed` | Sức khỏe consumers |
| `job_success_total`/`job_failure_total` | Outcome sau commit, không phải sau take |
| `retry_total`/`dead_letter_total` | Tải lỗi và giới hạn retries |
| `shutdown_drain_seconds` | Khoảng thời gian ngừng nhận đến hoàn tất |

`size()` và `remainingCapacity()` chỉ là snapshot; thread khác có thể thay đổi capacity ngay sau khi đọc. Không làm:

~~~java
if (queue.remainingCapacity() > 0) {
    queue.addLast(job); // Race: slot có thể bị thread khác chiếm.
}
~~~

Đây là anti-pattern. Thay bằng `offerLast(job)` rồi kiểm boolean — quyết định nhận job nằm trong cùng operation.

## 13. Hạn chế quan trọng: ThreadPoolExecutor có queue của riêng nó

Một bẫy thường gặp: người lập trình dùng `Executors.newFixedThreadPool(4)` rồi submit **hàng triệu** jobs trực tiếp. Default fixed pool sử dụng **unbounded work queue** trong implementation JDK, nên dù chỉ có 4 threads, pending Runnables/Futures vẫn có thể chiếm lượng RAM lớn.

~~~java
ExecutorService pool = Executors.newFixedThreadPool(4);
for (Job job : tooManyJobs) {
    pool.submit(() -> process(job)); // Có thể dồn unbounded pending tasks.
}
~~~

Đây là anti-pattern **minh họa** (biến `Job`, `tooManyJobs`, `process` do ứng dụng cung cấp), không phải class độc lập. Trong các ví dụ runnable, executor chỉ nhận **2–3 worker tasks cố định**, còn các **business jobs** luôn đi qua bounded `LinkedBlockingDeque`.

Nếu cần giới hạn task submission trực tiếp, xem `ThreadPoolExecutor` với `ArrayBlockingQueue` và `RejectedExecutionHandler` có chính sách, hoặc kiểm soát bằng `Semaphore`. Không chỉ đặt deque bounded ở một tầng trong khi các tầng khác có unbounded executors hoặc retry buffers.

Virtual threads trong Java 21+ giảm chi phí nhiều blocking operations nhưng **không** biến workload vô hạn thành bounded; vẫn cần admission control và downstream limits.

## 14. Không có durability hoặc exactly-once

In-memory queue không phải broker. Khi consumer `takeFirst` một job, phần tử đã **rời queue**. Nếu JVM crash ngay sau đó nhưng trước DB commit, job có thể mất. Nếu producer retry vì không chắc job đã được nhận hay chưa, có thể enqueue lại và xử lý duplicate.

Với tác vụ không được mất:
- Persist job trước khi trả accepted, hoặc dùng durable message broker.
- Có ack sau commit kết quả; reconcile khi crash.
- Thêm idempotency key vào business operation.
- Có bounded retries, backoff và dead-letter.
- Cân nhắc transaction/outbox nếu cần atomically phát event cùng state update.

`LinkedBlockingDeque` tự nó cung cấp **thread-safe queue operations**, **không** cung cấp delivery guarantees xuyên process failure.

## 15. Các thao tác giám sát và batch: dùng đúng, tránh mất việc

`size()` là số elements tại thời điểm gọi; `remainingCapacity()` là số slots lý tưởng còn lại. Cả hai **không reserve capacity** và có thể stale ngay sau khi trả về.

`drainTo(Collection,maxElements)` loại tối đa một số phần tử khỏi deque và đưa vào collection. Dùng để batch processing nhưng phải nhớ jobs **đã rời queue**:

~~~java
List<Job> batch = new ArrayList<>();
int moved = queue.drainTo(batch, 100);
if (moved > 0) {
    // Chỉ ack sau khi xử lý batch thành công.
}
~~~

Đây là snippet trong method với queue/Job phù hợp, cần imports. Nếu batch xử lý lỗi, queue **không tự lấy lại jobs**. `clear()` cũng xóa toàn bộ jobs đang chờ; nó **không** phải graceful shutdown.

Iterator/spliterator của `LinkedBlockingDeque` là **weakly consistent**, không phải snapshot atomic khóa toàn queue. Đừng dựa vào việc duyệt iterator để khẳng định chắc chắn tất cả jobs đã được xử lý khi nhiều producers/consumers còn hoạt động.

## 16. So sánh một số lựa chọn hiện hành

| Cấu trúc | Giới hạn | Phù hợp |
| --- | --- | --- |
| `LinkedBlockingDeque(capacity)` | Bounded rõ | Pipeline FIFO hoặc hai đầu, chặn/timeout |
| `LinkedBlockingDeque()` | Max int | Không nên dùng khi cần memory backpressure |
| `ArrayBlockingQueue(capacity)` | Bounded array | FIFO không cần hai đầu, footprint predictable |
| `LinkedBlockingQueue(capacity)` | Bounded linked | FIFO một đầu |
| `SynchronousQueue` | Không lưu buffer | Direct handoff tới consumer |
| `ConcurrentLinkedDeque` | Không có blocking/capacity | Khi có admission khác |
| `PriorityBlockingQueue` | Unbounded mặc định | Priority nhưng phải thêm giới hạn riêng |
| `DelayQueue` | Unbounded mặc định | Delay scheduling với admission riêng |
| `Semaphore` | Bounded permits | Giới hạn total in-flight resources |
| `Flow.Publisher/Subscriber` | Request(n) demand | Reactive backpressure nếu toàn stream tôn trọng demand |
| `ThreadPoolExecutor` + bounded queue | Tùy cấu hình | Bounded task submission |
| `Executors.newVirtualThreadPerTaskExecutor()` | Không phải bounded queue | Java21+, cần backpressure riêng |

**Chọn cấu trúc đơn giản nhất phù hợp semantics**. Nếu chỉ cần FIFO, `ArrayBlockingQueue` thường dễ lý giải. Nếu cần hai đầu hoặc muốn minh họa `putFirst/putLast`, `LinkedBlockingDeque` thích hợp.

## 17. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Khắc phục |
| --- | --- | --- |
| Không truyền capacity | Hàng đợi có thể phình gần giới hạn RAM | Constructor bounded |
| Capacity 0/âm | IllegalArgumentException | Capacity ít nhất 1 |
| `putLast` vô thời hạn ở HTTP thread | Request timeout/hung | Timed offer |
| `offerLast` false nhưng bỏ qua | Mất job hoặc sai acknowledgment | Overload policy rõ |
| Dùng null làm stop marker | NullPointerException | STOP object/record |
| Gửi STOP trước khi producers dừng | Job nằm sau STOP không ai xử lý | Dừng admission trước |
| Một STOP cho nhiều workers | Worker khác chờ mãi | Marker/worker hoặc khác protocol |
| Dùng `putFirst(STOP)` | STOP vượt qua jobs | Đặt ở tail sau drain |
| Gọi `shutdown` nhưng worker vẫn `takeFirst` | Không tự wake consumer | STOP/interrupt |
| Lạm dụng `shutdownNow` | Có thể bỏ mất việc đang xử lý | Graceful drain khi cần |
| Nuốt `InterruptedException` | Executor không stop | Propagate/restore flag |
| `size()==0` nên exit | Producer có thể enqueue ngay sau | Lifecycle barrier |
| `remainingCapacity>0` rồi add | Race | `offerLast` atomic |
| FIFO dequeue = FIFO completion | Nhiều workers hoàn tất khác order | Partition/single consumer |
| Dùng `offerFirst` cho mọi retry | Starvation/reorder | Bounded retry + scheduler |
| Gắn mutable job rồi sửa sau enqueue | Data race | Immutable DTO |
| Chỉ queue bounded nhưng futures unbounded | Memory vẫn tăng | Limit upstream/executor |
| Nghĩ queue capacity là total in-flight | Jobs đang xử lý nằm ngoài | Semaphore/overall admission |
| Nghĩ take = commit | Crash sau take mất job | Durable ack/idempotency |
| `clear()` khi shutdown | Drop jobs | Drain/stop policy rõ |
| `drainTo` rồi không xử lý batch | Jobs biến mất khỏi queue | Batch ack/retry rõ |
| Producer không xử lý InterruptedException | Hủy không đúng | Cancellation semantics |
| Worker exception không được giám sát | Producer chặn mãi | Monitor Future/health |
| Queue full nhưng chỉ tăng capacity | Giấu overload, tăng latency | SLO sizing + overload policy |
| Logging raw payloads | Lộ secrets/PII | Minimize/redact telemetry |

## 18. Checklist kiểm thử và tự đánh giá

| Case | Kỳ vọng |
| --- | --- |
| `new LinkedBlockingDeque<>(1)` | Thành công |
| Queue đầy, `offerLast` | False ngay |
| Queue đầy, timed offer | False sau deadline |
| Queue đầy, `putLast` | Block/interruptible |
| Consumer lấy 1 phần tử | Producer đang chờ có thể tiếp tục |
| FIFO `putLast/takeFirst` | Job cũ lấy trước |
| Queue rỗng, `takeFirst` | Block |
| Queue rỗng, `pollFirst(timeout)` | Null |
| null element | NullPointerException |
| Producer đang block bị interrupt | Thread kết thúc có kiểm soát |
| Hai workers được khởi tạo | Không làm tăng số job queue |
| Queue đầy trước thả gate | Timeout/rejection đúng |
| 6 jobs accepted | 6 jobs xử lý |
| 2 STOP markers | 2 workers dừng |
| Future.get hết hạn | TimeoutException, không tự cancel |
| Shutdown bình thường | Workers và queue sạch |
| 2-stage output đầy | Stage A bị block |
| 2-stage input đầy | Upstream producer bị block |
| Thả downstream gate | Upstream producer tiếp tục |
| Multiple consumers | Completion order có thể khác FIFO |
| Failure sau dequeue | Không tự retry |
| Concurrent size/remainingCapacity | Chỉ gauge, không reservation |
| Executor queue unbounded | Bị phát hiện là backpressure gap |
| Job payload lớn | Có memory/bytes budget |
| Telemetry backend lỗi | Bounded logging/export policy |
| JVM crash | Không giả queue có durability |

**Tự kiểm tra nhanh:**
1. Vì sao constructor mặc định không phù hợp backpressure? — Capacity `Integer.MAX_VALUE`.
2. `putLast` khi queue đầy? — Chờ đến khi có chỗ hoặc interrupted.
3. `offerLast` khi queue đầy? — Trả `false`; phiên bản timed đợi tối đa deadline.
4. `takeFirst` làm gì? — Chờ có job, lấy và xóa đầu deque.
5. Tại sao không dùng `null` làm sentinel? — Queue cấm null.
6. STOP markers được gửi khi nào? — Sau khi ngừng admission và có shutdown ordering rõ.
7. Một STOP đủ cho hai workers không? — Không nếu cả hai dùng marker protocol.
8. Vì sao không gửi STOP bằng `putFirst`? — Có thể vượt jobs đang chờ.
9. Backpressure nhiều tầng xảy ra khi nào? — Downstream queue full làm stage trước block, rồi upstream queue full.
10. Queue bound có giới hạn tổng memory không? — Chỉ giới hạn số queued elements; payload, running jobs và upstream ngoài.
11. Đã `takeFirst` có nghĩa business đã commit không? — Không.
12. Multiple consumers có bảo đảm FIFO completion không? — Không.
13. `remainingCapacity` có reserve chỗ không? — Không.
14. Virtual threads có tự giới hạn công việc không? — Không.
15. Lựa chọn khi critical job không được mất? — Durable broker/outbox, ack và idempotency.
16. Trước khi deploy cần metrics gì? — Queue depth/age, offer wait, reject, processing latency/failure và worker health.

## 19. Tài liệu chính thức còn áp dụng

- [Java SE 25 — LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html): optional bound, constructor, queue/deque operations, remainingCapacity, drainTo, weakly consistent iterators.
- [Java SE 25 — BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html): bốn cách xử lý queue full/empty, FIFO equivalents và memory consistency effects.
- [Java SE 25 — BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html): chặn, timed operations, visibility/happens-before.
- [Java SE 25 — ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html): lifecycle, shutdown/shutdownNow, awaitTermination và Future.
- [Java SE 25 — Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html): get timeout và task completion.
- [Java SE 25 — CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordination trong unit/integration tests.
- [Java SE 25 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queue policy và rejection.
- [Java SE 25 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO alternative.
- [Java SE 25 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): thread-safe set/counters.
- [Java SE 25 — Semaphore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html): total in-flight permits.
- [Java SE 25 — Flow](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Flow.html): request(n) demand-based reactive API.
- [Java SE 25 — Executors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html): workers và executors configuration.

**Kết luận:** `LinkedBlockingDeque<>(capacity)` triển khai backpressure trong một JVM khi **producer dùng `putLast` hoặc timed `offerLast`**, còn consumer dùng **`takeFirst`**. Bounded queues ở nhiều stages có thể truyền áp lực ngược upstream. Nhưng một queue thread-safe không tự đem đến exactly-once, durability, FIFO completion của nhiều workers hoặc giới hạn mọi outstanding requests. Một pipeline production cần chọn admission/rejection policy, stop/interrupt protocol, worker supervision, idempotency và metrics bên cạnh cấu hình capacity.