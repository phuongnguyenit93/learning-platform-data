# Java 7 — Hàng đợi đồng thời: Ngắt luồng, hủy công việc và quy trình kết thúc

## 1. Phạm vi và mục tiêu

`BlockingQueue`, `ConcurrentLinkedQueue`, `SynchronousQueue` và những hàng đợi đồng thời khác giúp các thread trao đổi công việc. Nhưng queue không tự biết khi nào ứng dụng nên dừng. Khi producer/consumer đang đợi, việc **interrupt**, **cancel một Future**, **đóng executor**, **đánh dấu hết dữ liệu** và **thu hồi công việc chưa xử lý** là những việc khác nhau.

Bài học thuộc chủ đề cha **Hàng đợi đồng thời**, đề bài trực tiếp **Ngắt luồng, hủy công việc và quy trình kết thúc**, sử dụng API còn được hỗ trợ trên **Java 17+**. Những API Java concurrent queues có từ trước Java 7 vẫn áp dụng hiện nay; chúng không bị coi là legacy chỉ vì được giới thiệu trước đó.

Học xong, bạn cần:

- Phân biệt `BlockingQueue.take/put` bị chặn với `offer/poll` tức thì và overload timed.
- Biết interrupt là **tín hiệu hợp tác**, không phải thread kill.
- Bắt `InterruptedException` đúng, biết lúc nào cần `Thread.currentThread().interrupt()`.
- Biết `Future.cancel(true)` và `ExecutorService.shutdownNow()` chỉ cố dừng công việc; không hoàn tác side effects.
- Hiểu `BlockingQueue` không cung cấp `close()` hoặc `shutdown()`; cần giao thức riêng.
- Thiết kế poison-pill đúng số consumers và chỉ sau khi mọi producers ngừng gửi việc.
- Chọn timed poll với stop flag khi không muốn sentinel, có điều kiện chống producer/stop race.
- Không xem `queue.isEmpty()` là chứng minh mọi jobs thành công, vì còn in-flight tasks.
- Theo dõi accepted / queued / in-flight / processed / failed / acknowledged, có recovery policy.
- Biết sự khác biệt giữa queues bounded, unbounded, zero-capacity và nonblocking.
- Quản lý đúng executor owner/lifecycle và deadlines.
- Chạy và hiểu 16 chương trình Java 17 đã kiểm thử.

**Nguyên tắc chính:** Queue chỉ là cấu trúc dữ liệu trao đổi công việc. Đúng đắn của việc dừng đòi hỏi **protocol giữa producer, consumer, coordinator và executor owner**.

## 2. Mô hình vòng đời producer–consumer

```text
             [ACCEPTING]
 Producer P1 --------------------> +-----------------+
 Producer P2 --------------------> | BlockingQueue<E>| --> Consumer C1 --> work/ack
                                  +-----------------+ --> Consumer C2 --> work/ack
                                             |
                                      [STOPPING]
       1. Ngừng nhận đầu vào mới
       2. Ngừng/join mọi producer
       3. Drain hoặc xử lý phần việc đã nhận
       4. Gửi đủ tín hiệu dừng / bật stop protocol
       5. Đợi consumers và lấy outcomes
       6. Owner shutdown executor, awaitTermination
       7. Reconcile phần queued/in-flight/failed
```

Một số trạng thái cần phân biệt:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Accepted | Producer đã enqueue thành công; `offer=false` không phải accepted |
| Queued | Item vẫn nằm trong queue |
| In-flight | Consumer đã lấy item khỏi queue nhưng chưa xử lý xong |
| Processed | Handler đã hoàn tất nghiệp vụ |
| Acknowledged | Outcome được ghi nhận bền vững nếu hệ thống cần |
| Failed | Handler báo lỗi hoặc bị hủy; có thể cần retry |
| Stop ingress | Không tiếp nhận request mới |
| Producers done | Không producer nào có thể enqueue thêm sau cut-off |
| Consumers done | Các worker loops đã kết thúc và Futures được thu thập |
| Executor terminated | Pool đã shutdown và threads/tasks đã kết thúc |

**`queue.isEmpty()==true` không có nghĩa `allProcessed==true`.** Một item đã được `take` sẽ biến mất khỏi queue kể cả khi handler sau đó thất bại.

## 3. Các thao tác BlockingQueue khi đầy/rỗng

Java 17 `BlockingQueue<E>` phân các thao tác thành bốn hình thức:

| | Báo exception | Trả kết quả ngay | Chờ vô thời hạn | Chờ có timeout |
| --- | --- | --- | --- | --- |
| Thêm item | `add(e)` | `offer(e)` | `put(e)` | `offer(e,time,unit)` |
| Lấy item | `remove()` | `poll()` | `take()` | `poll(time,unit)` |
| Xem đầu queue | `element()` | `peek()` | — | — |

Khi bounded queue **đầy**, `offer(e)` trả `false`, `add(e)` ném `IllegalStateException`, `put(e)` chờ có chỗ, timed `offer` có thể trả false khi hết hạn.

Khi queue **rỗng**, `poll()` trả `null`, `remove()` ném `NoSuchElementException`, `take()` chờ có item, timed `poll` có thể trả `null` khi hết hạn.

`put`, `take` và hai timed overloads có thể ném `InterruptedException`. Các overload trả ngay `offer(e)`/`poll()` **không tự chờ** sự kiện queue thay đổi.

### 3.1. Không dùng null làm STOP

`BlockingQueue` **không chấp nhận null elements**. `poll()` dùng null để báo không có item, nên `q.put(null)` không thể là “end-of-stream”; hãy dùng một non-null typed token hoặc signal ngoài queue.

### 3.2. Không dùng isEmpty rồi take

```java
if (!queue.isEmpty()) {
    queue.take();
}
```

Đây là **mảnh minh họa anti-pattern**: thread khác có thể lấy item sau `isEmpty`, khiến `take` vẫn block. Muốn lấy ngay dùng `poll()`; muốn có deadline dùng `poll(timeout,unit)`.

## 4. Chương trình A — QueueOperationsDemo.java

```java
import java.util.concurrent.*;

public final class QueueOperationsDemo {
 public static void main(String[] args) throws Exception {
   BlockingQueue<String> q = new ArrayBlockingQueue<>(1);
   boolean first = q.offer("A");
   boolean second = q.offer("B");
   boolean addThrew = false;
   try { q.add("C"); }
   catch (IllegalStateException ex) { addThrew = true; }
   boolean timedOffer = q.offer("D", 30, TimeUnit.MILLISECONDS);
   String taken = q.take();
   boolean emptyPoll = q.poll() == null;
   boolean timedEmpty = q.poll(30, TimeUnit.MILLISECONDS) == null;
   System.out.println("offerFirst=" + first);
   System.out.println("offerSecond=" + second);
   System.out.println("addFullRejected=" + addThrew);
   System.out.println("timedOfferFull=" + timedOffer);
   System.out.println("take=" + taken);
   System.out.println("pollEmpty=" + emptyPoll);
   System.out.println("timedPollEmpty=" + timedEmpty);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 QueueOperationsDemo.java
java QueueOperationsDemo
```

Stdout đã kiểm thử:

```text
offerFirst=true
offerSecond=false
addFullRejected=true
timedOfferFull=false
take=A
pollEmpty=true
timedPollEmpty=true
```

Queue capacity 1 chỉ nhận `A`. `offer("B")` báo false, `add("C")` ném lỗi, timed offer cũng hết hạn vì không có consumer. Sau `take`, queue rỗng nên poll trả null.

**Không bỏ qua giá trị false:** Nếu producer không kiểm kết quả của `offer`, nó có thể báo “đã gửi job” dù thực tế queue từ chối. Bounded queue tạo backpressure nhưng caller phải xử lý outcome.

## 5. Thread.interrupt không phải kill

`Thread.interrupt()` đặt tín hiệu interruption; nhiều blocking operations như `BlockingQueue.take()` và `BlockingQueue.put()` sẽ ném `InterruptedException` khi đang chờ.

Khi consumer bị interrupt:
- Nó có thể thôi `take` và thoát vòng lặp.
- Nó **không tự đóng queue** và không tự interrupt mọi consumers khác.
- Nó phải báo outcome/cancellation cho coordinator nếu business yêu cầu.
- Nếu bắt `InterruptedException` tại boundary thoát task, thường cần khôi phục cờ bằng `Thread.currentThread().interrupt()`.

Khi producer bị interrupt ở `put`, item đang cố enqueue **không được coi là accepted chỉ vì method từng được gọi**. Theo dõi kết quả request và job IDs.

### 5.1. Bắt exception rồi tiếp tục mãi là lỗi

```java
for (;;) {
    try {
        queue.take();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // Continuing endlessly is wrong.
    }
}
```

Đây là anti-pattern minh họa. Với cờ interrupt tiếp tục được set, lần take sau có thể lại bị interrupt ngay, thành vòng lặp bận. Nếu quyết định dừng, hãy **break/return**; nếu quyết định tiếp tục, phải có interruption policy riêng.

## 6. Chương trình B — InterruptTakeDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class InterruptTakeDemo {
 public static void main(String[] args) throws Exception {
   BlockingQueue<String> q = new ArrayBlockingQueue<>(1);
   CountDownLatch ready = new CountDownLatch(1);
   AtomicBoolean caught = new AtomicBoolean();
   AtomicBoolean restored = new AtomicBoolean();
   Thread worker = new Thread(() -> {
     ready.countDown();
     try { q.take(); }
     catch (InterruptedException e) {
       caught.set(true);
       Thread.currentThread().interrupt();
       restored.set(Thread.currentThread().isInterrupted());
     }
   });
   try {
     worker.start();
     if (!ready.await(5, TimeUnit.SECONDS)) throw new AssertionError();
     worker.interrupt();
     worker.join(5000);
     if (worker.isAlive()) throw new IllegalStateException("worker still alive");
     System.out.println("caughtInterrupt=" + caught.get());
     System.out.println("restoredFlag=" + restored.get());
     System.out.println("queueEmpty=" + q.isEmpty());
     System.out.println("workerExited=" + (!worker.isAlive()));
   } finally {
     worker.interrupt();
     worker.join(5000);
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InterruptTakeDemo.java
java InterruptTakeDemo
```

Stdout đã kiểm thử:

```text
caughtInterrupt=true
restoredFlag=true
queueEmpty=true
workerExited=true
```

Worker được interrupt và thoát khỏi `take` bằng exception. Demo khôi phục interrupt flag rồi rời thread. Queue vẫn rỗng; không tồn tại trạng thái queue-closed tự phát.

**Tính chắc chắn của test:** `ready` chỉ xác nhận worker đã bắt đầu; interrupt có thể đến ngay trước hoặc trong lời gọi take, cả hai đều hợp lệ. Không giả định thread scheduler phải chạy trong một số milliseconds cố định.

## 7. Producer chờ put khi queue đầy

Nếu consumer bị dừng trong khi producer đang `put` vào bounded queue đầy, producer có thể chờ mãi. Vì vậy shutdown phải có kế hoạch cho **cả producer và consumer**, không chỉ gửi STOP cho một phía.

## 8. Chương trình C — InterruptPutDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class InterruptPutDemo {
 public static void main(String[] args) throws Exception {
   BlockingQueue<String> q = new ArrayBlockingQueue<>(1);
   q.put("A");
   CountDownLatch ready = new CountDownLatch(1);
   AtomicBoolean interrupted = new AtomicBoolean();
   AtomicBoolean restored = new AtomicBoolean();
   Thread producer = new Thread(() -> {
     ready.countDown();
     try { q.put("B"); }
     catch (InterruptedException e) {
       interrupted.set(true);
       Thread.currentThread().interrupt();
       restored.set(Thread.currentThread().isInterrupted());
     }
   });
   try {
     producer.start();
     if (!ready.await(5, TimeUnit.SECONDS)) throw new AssertionError();
     producer.interrupt();
     producer.join(5000);
     if (producer.isAlive()) throw new IllegalStateException();
     System.out.println("putInterrupted=" + interrupted.get());
     System.out.println("restoredFlag=" + restored.get());
     System.out.println("headRemains=" + q.take());
     System.out.println("secondNotEnqueued=" + q.isEmpty());
   } finally {
     producer.interrupt();
     producer.join(5000);
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InterruptPutDemo.java
java InterruptPutDemo
```

Stdout đã kiểm thử:

```text
putInterrupted=true
restoredFlag=true
headRemains=A
secondNotEnqueued=true
```

`A` đã đầy chỗ; producer cố put `B` và bị interrupt nên không enqueue `B` trong kịch bản này. **Không khái quát** rằng hủy một producer có thể đảo ngược các enqueue đã hoàn thành trước đó.

## 9. Future.cancel: hủy tác vụ không phải hủy toàn queue

`ExecutorService.submit` trả `Future`. Theo Java 17:

- `cancel(false)` có thể ngăn task **chưa bắt đầu** chạy; không yêu cầu interrupt task đang chạy.
- `cancel(true)` cố interrupt thread đang chạy task khi implementation biết nó.
- `isCancelled` cho biết future đã bị hủy theo contract, không xác nhận code cleanup hoặc side effects đã dừng tức thì.
- `Future.get` trên Future đã hủy ném `CancellationException`.
- `Future.get(timeout)` timeout **không tự cancel** task.
- Cancel consumer task không tự loại bỏ các business jobs còn nằm trong queue.
- Job đã được `take` không tự quay trở lại queue nếu task bị cancel.

`Thread.interrupt` và `Future.cancel` nên là một phần của **cooperative cancellation protocol**: handler tôn trọng tín hiệu, tự cleanup và owner theo dõi in-flight work.

## 10. Chương trình D — FutureCancellationDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class FutureCancellationDemo {
 public static void main(String[] args) throws Exception {
   BlockingQueue<String> q = new ArrayBlockingQueue<>(1);
   CountDownLatch entered = new CountDownLatch(1);
   CountDownLatch exited = new CountDownLatch(1);
   AtomicBoolean observed = new AtomicBoolean();
   ExecutorService pool = Executors.newSingleThreadExecutor();
   try {
     Future<Integer> f = pool.submit(() -> {
       entered.countDown();
       try { q.take(); return 1; }
       catch (InterruptedException e) {
         observed.set(true);
         Thread.currentThread().interrupt();
         return -1;
       } finally { exited.countDown(); }
     });
     if (!entered.await(5, TimeUnit.SECONDS)) throw new AssertionError();
     boolean requested = f.cancel(true);
     if (!exited.await(5, TimeUnit.SECONDS))
       throw new IllegalStateException("worker stuck");
     System.out.println("cancelRequested=" + requested);
     System.out.println("futureCancelled=" + f.isCancelled());
     System.out.println("workerObservedInterrupt=" + observed.get());
     System.out.println("queueEmpty=" + q.isEmpty());
   } finally {
     pool.shutdownNow();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FutureCancellationDemo.java
java FutureCancellationDemo
```

Stdout đã kiểm thử:

```text
cancelRequested=true
futureCancelled=true
workerObservedInterrupt=true
queueEmpty=true
```

Test không chỉ kiểm `isCancelled` mà còn đợi `exited` và biết worker thực sự bắt interrupt. Dù task catch rồi return -1, Future đã canceled nên caller không dùng `get` để lấy -1 như một kết quả thành công.

## 11. Cancel một task đang xếp hàng, không interrupt worker đang chạy

Khi executor chỉ có một worker đang bận, Future thứ hai có thể đang chờ trong queue nội bộ executor. `cancel(false)` có thể ngăn Future thứ hai thực thi. Cần phân biệt **executor task queue** với business `BlockingQueue`.

## 12. Chương trình E — CancelQueuedTaskDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class CancelQueuedTaskDemo {
 public static void main(String[] args) throws Exception {
   ExecutorService pool = Executors.newSingleThreadExecutor();
   CountDownLatch started = new CountDownLatch(1);
   CountDownLatch release = new CountDownLatch(1);
   AtomicBoolean queuedRan = new AtomicBoolean();
   try {
     Future<?> first = pool.submit(() -> {
       started.countDown();
       release.await();
       return null;
     });
     if (!started.await(5, TimeUnit.SECONDS)) throw new AssertionError();
     Future<?> second = pool.submit(() -> {
       queuedRan.set(true);
       return null;
     });
     boolean cancelled = second.cancel(false);
     release.countDown();
     first.get(5, TimeUnit.SECONDS);
     pool.shutdown();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
     System.out.println("cancelQueued=" + cancelled);
     System.out.println("futureCancelled=" + second.isCancelled());
     System.out.println("queuedTaskRan=" + queuedRan.get());
   } finally {
     release.countDown();
     pool.shutdownNow();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 CancelQueuedTaskDemo.java
java CancelQueuedTaskDemo
```

Stdout đã kiểm thử:

```text
cancelQueued=true
futureCancelled=true
queuedTaskRan=false
```

`first` chiếm worker tới khi main release latch, nên `second` bị cancel trước khi có cơ hội chạy. Không assert độ dài queue executor như một output cố định vì implementation khác nhau.

## 13. Tín hiệu dừng poison pill

`BlockingQueue` **không có phương thức đóng**. Với queue FIFO, một giao thức graceful thường dùng một **non-null STOP token**:

```text
[legitimate-job-1] [legitimate-job-2] [STOP]
             consumer take -> process 1 -> process 2 -> STOP -> exit
```

Điều kiện quan trọng:

1. **Không producer nào enqueue thêm sau STOP**.
2. Consumer lấy STOP rồi **thoát**, không xử lý token như business payload.
3. Với N consumers độc lập, thường cần **N tokens** (hoặc giao thức truyền tiếp đã chứng minh đúng).
4. Queue phải đủ chỗ hoặc consumer đang tiến để `put(STOP)` không chặn vĩnh viễn.
5. Không dùng `null` làm STOP.
6. Không dùng STOP dưới dạng một giá trị do user cũng có thể gửi nếu không phân biệt bằng type/identity.
7. STOP trên priority/delay queues có thể không đứng sau tất cả work, không thể suy từ FIFO.

### 13.1. Nên dùng typed message

Java 17 hỗ trợ `record` và sealed types, có thể biểu diễn `WorkMessage` khác `StopMessage`. Trong ví dụ đơn giản dưới đây, một object String unique làm sentinel; `item == STOP` so sánh **identity**, không so sánh text của user.

## 14. Chương trình F — PoisonPillOneDemo.java

```java
import java.util.concurrent.*;

public final class PoisonPillOneDemo {
 private static final String STOP = new String("STOP");
 public static void main(String[] args) throws Exception {
   BlockingQueue<String> q = new ArrayBlockingQueue<>(3);
   ExecutorService pool = Executors.newSingleThreadExecutor();
   try {
     Future<String> f = pool.submit(() -> {
       StringBuilder out = new StringBuilder();
       while (true) {
         String item = q.take();
         if (item == STOP) return out.toString();
         out.append(item);
       }
     });
     q.put("A");
     q.put("B");
     q.put(STOP);
     String result = f.get(5, TimeUnit.SECONDS);
     System.out.println("processed=" + result);
     System.out.println("queueEmpty=" + q.isEmpty());
     System.out.println("stopWasLast=true");
   } finally {
     pool.shutdownNow();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 PoisonPillOneDemo.java
java PoisonPillOneDemo
```

Stdout đã kiểm thử:

```text
processed=AB
queueEmpty=true
stopWasLast=true
```

STOP đi sau A và B trong FIFO queue. Consumer return sau token. Trong một hệ thống nhiều producers, coordinator phải **đợi mọi producer hoàn tất** trước khi gửi token cuối.

## 15. Hai consumers cần hai STOP tokens

Nếu chỉ gửi một STOP cho hai consumers chờ `take`, một worker có thể thoát và worker còn lại vẫn chờ mãi. `executor.shutdown()` không thay queue gửi token thứ hai.

```text
Queue: [job1][job2][STOP][STOP]
C1: work ... takes STOP -> exits
C2: work ... takes STOP -> exits
```

Không cần dự đoán C1 xử lý những job nào; lịch chạy là nondeterministic. Kiểm outcome bằng job IDs và Futures, không hardcode thứ tự consumers.

## 16. Chương trình G — MultiConsumerStopDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.*;

public final class MultiConsumerStopDemo {
 record Job(int id, boolean stop) {}
 public static void main(String[] args) throws Exception {
   BlockingQueue<Job> q = new ArrayBlockingQueue<>(8);
   Job STOP = new Job(-1, true);
   for (int i = 1; i <= 6; i++) q.add(new Job(i, false));
   q.add(STOP);
   q.add(STOP);
   Set<Integer> seen = ConcurrentHashMap.newKeySet();
   AtomicInteger processed = new AtomicInteger();
   AtomicInteger stopped = new AtomicInteger();
   ExecutorService pool = Executors.newFixedThreadPool(2);
   try {
     Callable<Void> consumer = () -> {
       while (true) {
         Job j = q.take();
         if (j.stop()) {
           stopped.incrementAndGet();
           return null;
         }
         if (!seen.add(j.id()))
           throw new AssertionError("duplicate " + j.id());
         processed.incrementAndGet();
       }
     };
     Future<Void> a = pool.submit(consumer);
     Future<Void> b = pool.submit(consumer);
     a.get(5, TimeUnit.SECONDS);
     b.get(5, TimeUnit.SECONDS);
     System.out.println("processed=" + processed.get());
     System.out.println("unique=" + seen.size());
     System.out.println("stoppedConsumers=" + stopped.get());
     System.out.println("queueEmpty=" + q.isEmpty());
     System.out.println("allIdsPresent=" +
       seen.equals(Set.of(1,2,3,4,5,6)));
   } finally {
     pool.shutdownNow();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MultiConsumerStopDemo.java
java MultiConsumerStopDemo
```

Stdout đã kiểm thử:

```text
processed=6
unique=6
stoppedConsumers=2
queueEmpty=true
allIdsPresent=true
```

Hai STOP được đặt **sau sáu jobs**, queue capacity=8 để setup không chờ. Hai workers đều thoát; số jobs distinct là 6. **Không** dựa consumer nào kết thúc trước hoặc mỗi consumer xử lý bao nhiêu.

Lưu ý: `record` là Java 16+ và hợp lệ với `--release 17`. Với dự án compile ở Java 7 nguyên bản, dùng class thường thay record; phần giới thiệu hiện nay lấy Java 17 làm baseline.

## 17. Nhiều producers: phải join xong rồi mới gửi STOP

Giả sử P1 vẫn đang `put` trong khi coordinator đã gửi STOP do P2 vừa hoàn tất. Consumer có thể thấy STOP trước item muộn của P1, làm item ấy bị bỏ lại. Vì vậy:

- Đóng ingress, ngừng tạo jobs mới.
- Chờ **tất cả** producer Futures thành công hoặc có policy với producer lỗi.
- Chỉ sau đó gửi đủ STOP tokens.
- Đợi tất cả consumer Futures và kiểm outcomes.

**Cờ AtomicBoolean stop một mình không xóa được race.** Producer có thể đọc `accepting=true` rồi bị preempt; coordinator đặt false và gửi STOP; sau đó producer tiếp tục `offer(job)`. Cần lifecycle gate hoặc join producers thật sự.

## 18. Chương trình H — ProducerCompletionDemo.java

```java
import java.util.concurrent.*;
import java.util.*;

public final class ProducerCompletionDemo {
 private static final String STOP = new String("STOP");
 public static void main(String[] args) throws Exception {
   BlockingQueue<String> q = new ArrayBlockingQueue<>(3);
   ExecutorService producers = Executors.newFixedThreadPool(2);
   ExecutorService consumers = Executors.newSingleThreadExecutor();
   try {
     Future<Set<String>> received = consumers.submit(() -> {
       Set<String> found = new TreeSet<>();
       while (true) {
         String item = q.take();
         if (item == STOP) return found;
         found.add(item);
       }
     });
     Future<?> one = producers.submit(() -> {
       q.put("P1");
       return null;
     });
     Future<?> two = producers.submit(() -> {
       q.put("P2");
       return null;
     });
     one.get(5, TimeUnit.SECONDS);
     two.get(5, TimeUnit.SECONDS);
     q.put(STOP);
     Set<String> result = received.get(5, TimeUnit.SECONDS);
     System.out.println("received=" + result);
     System.out.println("allProducersDone=true");
     System.out.println("queueEmpty=" + q.isEmpty());
   } finally {
     producers.shutdownNow();
     consumers.shutdownNow();
     if (!producers.awaitTermination(5, TimeUnit.SECONDS) ||
         !consumers.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ProducerCompletionDemo.java
java ProducerCompletionDemo
```

Stdout đã kiểm thử:

```text
received=[P1, P2]
allProducersDone=true
queueEmpty=true
```

Không đoán thứ tự P1/P2 được enqueue; `TreeSet` cho output ổn định. Coordinator đợi hai producers hoàn tất trước khi gửi STOP. Nếu Future producer thất bại, owner phải xác định phần work đã accepted/chưa accepted, không tự báo hoàn tất.

## 19. Timed poll và cờ dừng thay poison pill

Có thể dùng consumer loop:

```java
while (accepting.get() || !queue.isEmpty()) {
    E item = queue.poll(100, TimeUnit.MILLISECONDS);
    if (item != null) process(item);
}
```

Đây là **pseudocode**: `E`, `queue`, `accepting`, `process` cần định nghĩa. Ý tưởng là consumer thức dậy định kỳ để kiểm stop condition mà không cần STOP token.

**Điều kiện an toàn:** `accepting=false` chỉ được set khi **không producer nào còn khả năng enqueue**. Nếu set false khi producers còn chạy, consumer có thể thấy queue rỗng và thoát rồi producer lại enqueue item.

Timed poll tránh busy-spin nhưng **timeout chờ item không giới hạn thời gian process(item)**.

## 20. Chương trình I — TimedPollStopDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class TimedPollStopDemo {
 public static void main(String[] args) throws Exception {
   BlockingQueue<String> q = new ArrayBlockingQueue<>(2);
   AtomicBoolean accepting = new AtomicBoolean(true);
   CountDownLatch received = new CountDownLatch(1);
   ExecutorService pool = Executors.newSingleThreadExecutor();
   try {
     Future<String> worker = pool.submit(() -> {
       StringBuilder sb = new StringBuilder();
       while (accepting.get() || !q.isEmpty()) {
         String item = q.poll(50, TimeUnit.MILLISECONDS);
         if (item != null) {
           sb.append(item);
           received.countDown();
         }
       }
       return sb.toString();
     });
     q.put("A");
     if (!received.await(5, TimeUnit.SECONDS)) throw new AssertionError();
     accepting.set(false);
     System.out.println("processed=" + worker.get(5, TimeUnit.SECONDS));
     System.out.println("finishedWithoutPoison=true");
     System.out.println("queueEmpty=" + q.isEmpty());
   } finally {
     accepting.set(false);
     pool.shutdownNow();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 TimedPollStopDemo.java
java TimedPollStopDemo
```

Stdout đã kiểm thử:

```text
processed=A
finishedWithoutPoison=true
queueEmpty=true
```

Main là producer duy nhất; nó chờ worker nhận A rồi mới đặt false. Không còn producer khác có thể thêm item. Trường hợp multi-producer thực tế cần stop/join protocol rõ ràng, không lấy ví dụ này làm bằng chứng AtomicBoolean đủ xử lý mọi race.

## 21. ExecutorService.shutdown() không tự đánh thức queue.take()

`ExecutorService.shutdown()` từ chối các **tasks submit mới vào executor**, nhưng cho tasks đã submit được xử lý tiếp. Nó **không** tự chuyển trạng thái BlockingQueue sang closed và không tự gửi STOP.

```text
Consumer task: q.take() on empty queue, waiting
Owner: executor.shutdown()
Consumer task: still waiting
Owner: executor.awaitTermination(40ms) -> false
Coordinator: q.put(STOP)
Consumer task: returns
Owner: awaitTermination(...) -> true
```

Shutdown executor và kết thúc business queue là **hai giao thức khác nhau**. Cần dừng producer/consumer trước rồi owner đóng executor, hoặc ít nhất phát tín hiệu đủ để các tasks bên trong có thể hoàn tất.

## 22. Chương trình J — GracefulExecutorDemo.java

```java
import java.util.concurrent.*;

public final class GracefulExecutorDemo {
 private static final String STOP = new String("STOP");
 public static void main(String[] args) throws Exception {
   BlockingQueue<String> q = new ArrayBlockingQueue<>(1);
   ExecutorService pool = Executors.newSingleThreadExecutor();
   CountDownLatch ready = new CountDownLatch(1);
   try {
     Future<String> f = pool.submit(() -> {
       ready.countDown();
       while (true) {
         String item = q.take();
         if (item == STOP) return "stopped";
       }
     });
     if (!ready.await(5, TimeUnit.SECONDS)) throw new AssertionError();
     pool.shutdown();
     boolean early = pool.awaitTermination(40, TimeUnit.MILLISECONDS);
     q.put(STOP);
     String answer = f.get(5, TimeUnit.SECONDS);
     boolean later = pool.awaitTermination(5, TimeUnit.SECONDS);
     System.out.println("terminatedBeforeSignal=" + early);
     System.out.println("consumerResult=" + answer);
     System.out.println("terminatedAfterSignal=" + later);
   } finally {
     q.offer(STOP);
     pool.shutdownNow();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 GracefulExecutorDemo.java
java GracefulExecutorDemo
```

Stdout đã kiểm thử:

```text
terminatedBeforeSignal=false
consumerResult=stopped
terminatedAfterSignal=true
```

`executor.shutdown()` không tác động tới queue riêng. Main vẫn có quyền `q.put(STOP)` sau khi shutdown executor vì đây **không phải** submit task vào executor. Khi consumer nhận STOP, executor mới hoàn tất.

## 23. ExecutorService.shutdownNow(): best effort, không rollback

`shutdownNow()` thường cố dừng các tasks chưa bắt đầu và cố interrupt tasks đang chạy, rồi **trả về ngay**. Nó không tự đợi termination; phải dùng `awaitTermination`.

Những điều không được hứa:

- Không cam kết ngắt tất cả CPU jobs đang chạy và không kiểm interrupt.
- Không cam kết rollback database/file writes đã xảy ra.
- Không cam kết một danh sách pending tasks có cùng cấu trúc trên mọi implementation.
- `ForkJoinPool.shutdownNow()` có hợp đồng riêng, trả danh sách rỗng trên Java 17.
- Không cam kết queue business tự đóng hoặc tự mất hết items.

`ThreadPoolExecutor` và `ForkJoinPool` có behavior chi tiết khác nhau. Giữ job IDs/Futures ở application layer nếu cần retry.

## 24. Chương trình K — ImmediateShutdownDemo.java

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class ImmediateShutdownDemo {
 public static void main(String[] args) throws Exception {
   BlockingQueue<String> q = new ArrayBlockingQueue<>(1);
   ExecutorService pool = Executors.newSingleThreadExecutor();
   CountDownLatch entered = new CountDownLatch(1);
   CountDownLatch exited = new CountDownLatch(1);
   AtomicBoolean interrupted = new AtomicBoolean();
   try {
     Future<?> f = pool.submit(() -> {
       entered.countDown();
       try { q.take(); }
       catch (InterruptedException ex) {
         interrupted.set(true);
         Thread.currentThread().interrupt();
       } finally { exited.countDown(); }
     });
     if (!entered.await(5, TimeUnit.SECONDS)) throw new AssertionError();
     pool.shutdownNow();
     if (!exited.await(5, TimeUnit.SECONDS))
       throw new IllegalStateException("not exited");
     boolean done = pool.awaitTermination(5, TimeUnit.SECONDS);
     System.out.println("consumerSawInterrupt=" + interrupted.get());
     System.out.println("workerExited=" + (exited.getCount() == 0));
     System.out.println("poolTerminated=" + done);
     System.out.println("queueStillEmpty=" + q.isEmpty());
   } finally {
     pool.shutdownNow();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ImmediateShutdownDemo.java
java ImmediateShutdownDemo
```

Stdout đã kiểm thử:

```text
consumerSawInterrupt=true
workerExited=true
poolTerminated=true
queueStillEmpty=true
```

Trong demo không có business item chưa xử lý; shutdownNow khiến blocked `take` ném exception. Trên hệ thống thật, nếu consumer đang `process(job)`, interruption có thể không ngừng logic ngay; phải có cancellation checkpoints và recovery policy.

## 25. Queue empty không có nghĩa processed: lỗi sau khi take()

```java
Job job = queue.take();
process(job);
```

Đây là pseudocode, cần class `Job` và handler `process`. `take` đã remove item, nên nếu `process` ném lỗi hoặc process crash, queue **không tự enqueue lại**. Vì vậy:

- Tách thống kê accepted/queued/in-flight/processed/failed.
- Theo dõi job ID, attempts, error category và retry policy.
- Nếu cần survive process crash, dùng durable broker/job store và acknowledgement.
- Nếu cần exactly-once business effects, dùng idempotency/transactions/dedup; queue trong heap không tự đảm bảo.
- Đừng re-offer mù quáng khi đã có side effects một phần.

## 26. Chương trình L — FailedConsumerDemo.java

```java
import java.util.concurrent.*;

public final class FailedConsumerDemo {
 public static void main(String[] args) throws Exception {
   BlockingQueue<String> q = new LinkedBlockingQueue<>(2);
   q.put("BAD");
   ExecutorService pool = Executors.newSingleThreadExecutor();
   try {
     Future<Integer> consumer = pool.submit(() -> {
       String value = q.take();
       if (value.equals("BAD"))
         throw new IllegalStateException("failed-item");
       return 1;
     });
     boolean failed = false;
     try { consumer.get(5, TimeUnit.SECONDS); }
     catch (ExecutionException e) {
       failed = e.getCause() instanceof IllegalStateException;
     }
     System.out.println("failureObserved=" + failed);
     System.out.println("itemAlreadyRemoved=" + q.isEmpty());
     System.out.println("queueNotDurable=true");
   } finally {
     pool.shutdownNow();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 FailedConsumerDemo.java
java FailedConsumerDemo
```

Stdout đã kiểm thử:

```text
failureObserved=true
itemAlreadyRemoved=true
queueNotDurable=true
```

Queue rỗng vì consumer đã lấy BAD; Future báo lỗi qua `ExecutionException`. Không được suy business work thành công từ `q.isEmpty()==true`.

## 27. drainTo chỉ lấy phần còn trong queue

`BlockingQueue.drainTo(collection,maxElements)` chuyển tối đa `maxElements` items **đang sẵn có** sang một collection. Nó **không** thu hồi item đã được consumer lấy ra và đang xử lý.

Các cảnh báo:

- Nếu producers vẫn đang enqueue, drain không đóng queue; items mới có thể tiếp tục đến.
- Nếu collection đích ném exception khi thêm, một số items có thể đã được chuyển một phần.
- Với concurrency, size/remainingCapacity không là snapshot cố định.
- Poison tokens có thể bị drain nhầm và làm consumer còn chờ.
- Không coi drainTo là persisted checkpoint hay transaction.

## 28. Chương trình M — DrainToDemo.java

```java
import java.util.concurrent.*;
import java.util.*;

public final class DrainToDemo {
 public static void main(String[] args) {
   BlockingQueue<String> q = new ArrayBlockingQueue<>(4);
   q.add("A");
   q.add("B");
   q.add("C");
   q.add("D");
   List<String> drained = new ArrayList<>();
   int removed = q.drainTo(drained, 2);
   System.out.println("removed=" + removed);
   System.out.println("drained=" + drained);
   System.out.println("queueHead=" + q.peek());
   System.out.println("remaining=" + q.size());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DrainToDemo.java
java DrainToDemo
```

Stdout đã kiểm thử:

```text
removed=2
drained=[A, B]
queueHead=C
remaining=2
```

Demo không có producers/consumers hoạt động đồng thời lúc drain nên kết quả xác định. Trong hệ thống concurrent, cần coordination trước khi dùng drainTo làm recovery.

## 29. Memory publication qua BlockingQueue

Java 17 bảo đảm **memory consistency**: hành động trước khi producer đặt một object vào concurrent queue **happen-before** hành động của consumer sau khi access/remove object tương ứng.

Như vậy, producer ghi message fields rồi `put`; consumer `take` và đọc fields thấy những thay đổi đã được publish. **Không** vì vậy mà việc sửa tiếp object sau put tự thread-safe; giữ dữ liệu immutable hoặc phối hợp synchronization đúng.

## 30. Chương trình N — MemoryVisibilityQueueDemo.java

```java
import java.util.concurrent.*;

public final class MemoryVisibilityQueueDemo {
 static final class Message { int data; }
 public static void main(String[] args) throws Exception {
   BlockingQueue<Message> q = new ArrayBlockingQueue<>(1);
   ExecutorService pool = Executors.newSingleThreadExecutor();
   try {
     Future<Integer> received = pool.submit(() -> q.take().data);
     Message msg = new Message();
     msg.data = 42;
     q.put(msg);
     int result = received.get(5, TimeUnit.SECONDS);
     System.out.println("readValue=" + result);
     System.out.println("publishedBeforePut=" + (result == 42));
   } finally {
     pool.shutdownNow();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MemoryVisibilityQueueDemo.java
java MemoryVisibilityQueueDemo
```

Stdout đã kiểm thử:

```text
readValue=42
publishedBeforePut=true
```

`Message.data` không khai báo volatile nhưng được ghi trước `put`, đọc sau `take`, nên hợp đồng memory ordering áp dụng. Dữ liệu đã publish không đồng nghĩa business handler đã ack hay commit.

## 31. SynchronousQueue: handoff không có bộ nhớ đệm

`SynchronousQueue` có capacity **0**, không lưu phần tử trong nội bộ. Một `put(e)` cần một `take()` tương ứng; nếu không có receiver, `offer(e)` ngay có thể trả false.

Shutdown rủi ro hơn khi dùng poison token:

- Nếu không còn consumer, `put(STOP)` có thể block mãi.
- `remainingCapacity()` và `size()` bằng 0 không nói nó không thể handoff.
- Đừng đo queue backlog bằng `size` của SynchronousQueue.
- Khi dùng timed `offer` để gửi STOP, phải xử lý false và báo tình trạng consumers còn sống.

## 32. Chương trình O — SynchronousHandoffDemo.java

```java
import java.util.concurrent.*;

public final class SynchronousHandoffDemo {
 public static void main(String[] args) throws Exception {
   SynchronousQueue<String> q = new SynchronousQueue<>(true);
   boolean withoutReceiver = q.offer("X");
   ExecutorService pool = Executors.newSingleThreadExecutor();
   try {
     Future<String> produced = pool.submit(() -> {
       q.put("Y");
       return "sent";
     });
     String got = q.take();
     String producerResult = produced.get(5, TimeUnit.SECONDS);
     System.out.println("offerWithoutReceiver=" + withoutReceiver);
     System.out.println("received=" + got);
     System.out.println("producerResult=" + producerResult);
     System.out.println("remainingCapacity=" + q.remainingCapacity());
     System.out.println("size=" + q.size());
   } finally {
     pool.shutdownNow();
     if (!pool.awaitTermination(5, TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 SynchronousHandoffDemo.java
java SynchronousHandoffDemo
```

Stdout đã kiểm thử:

```text
offerWithoutReceiver=false
received=Y
producerResult=sent
remainingCapacity=0
size=0
```

Lời gọi offer X thất bại vì chưa có receiver; khi producer put Y và main take, dữ liệu được handoff trực tiếp. Không có item nằm lại trong internal queue.

## 33. ConcurrentLinkedQueue không có take/put

`ConcurrentLinkedQueue` là FIFO queue nonblocking, unbounded; nó có `offer`, `poll`, `peek`, nhưng **không implement BlockingQueue** nên không có `take`/`put`/timed poll.

- Vòng `while(q.poll()==null)` có thể busy-spin tốn CPU.
- `size()` không constant-time và có thể thiếu chính xác khi có concurrent mutations.
- Nếu muốn consumer ngủ chờ, dùng BlockingQueue hoặc external signaling như Semaphore.
- Vì unbounded, cần kiểm producer rate/backpressure ở application layer.
- Nonblocking không có nghĩa có native close hay guaranteed cancellation.

## 34. Chương trình P — ConcurrentLinkedQueueDemo.java

```java
import java.util.concurrent.*;

public final class ConcurrentLinkedQueueDemo {
 public static void main(String[] args) {
   ConcurrentLinkedQueue<String> q = new ConcurrentLinkedQueue<>();
   q.offer("A");
   q.offer("B");
   System.out.println("peek=" + q.peek());
   System.out.println("first=" + q.poll());
   System.out.println("second=" + q.poll());
   System.out.println("pollEmpty=" + (q.poll() == null));
   System.out.println("supportsBlockingTake=false");
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ConcurrentLinkedQueueDemo.java
java ConcurrentLinkedQueueDemo
```

Stdout đã kiểm thử:

```text
peek=A
first=A
second=B
pollEmpty=true
supportsBlockingTake=false
```

Dòng `supportsBlockingTake=false` do demo in để ghi nhớ API, không phải reflection test. Không được viết `q.take()` trên ConcurrentLinkedQueue rồi kỳ vọng biên dịch.

## 35. Các loại queue cần shutdown protocol khác nhau

| Queue | Backpressure/capacity | Lưu ý |
| --- | --- | --- |
| `ArrayBlockingQueue(n)` | Bounded, FIFO | Poison sau jobs khi producers dừng |
| `LinkedBlockingQueue(n)` | Bounded, FIFO | Có thể dùng cùng protocol |
| `LinkedBlockingQueue()` | Mặc định Integer.MAX_VALUE | Thực tế gần unbounded, rủi ro memory |
| `SynchronousQueue` | Capacity 0, handoff | STOP cần consumer đồng thời chờ |
| `ConcurrentLinkedQueue` | Unbounded, nonblocking | Không có take; cần wake mechanism |
| `PriorityBlockingQueue` | Unbounded, ưu tiên | STOP có thể được lấy trước jobs |
| `DelayQueue` | Unbounded, delayed items | STOP có thể bị delay hoặc lấy không đúng thời điểm |
| `LinkedTransferQueue` | Unbounded, có transfer semantics | Transfer có thể đợi receiver, không tự close |
| `LinkedBlockingDeque` | Có thể bounded, hai đầu | Chọn đầu enqueue/dequeue phù hợp, tránh đảo STOP |

Với queue ưu tiên/thời gian, **không được** dùng FIFO poison-pill logic máy móc. Cần protocol xác định mọi việc cần xử lý đã hoàn tất, hoặc external cancellation/stop conditions.

## 36. Giao thức graceful shutdown có thứ tự

Một quy trình gợi ý cho **FIFO BlockingQueue**, nhiều producers và N consumers:

```text
[1] STOP_INGRESS
    -> không nhận business work mới

[2] STOP + JOIN_PRODUCERS
    -> không thread nào có thể enqueue sau điểm cắt
    -> lấy outcomes của producer Futures

[3] DRAIN_ACCEPTED_WORK
    -> consumers tiếp tục xử lý những jobs được nhận
    -> coordinator chèn N STOP tokens sau jobs, nếu dùng sentinel
    -> put/offer token phải được kiểm, có deadline nếu cần

[4] JOIN_CONSUMERS
    -> đợi N consumer Futures, xử lý ExecutionException/Cancellation
    -> xác minh accepted / processed / failed / pending

[5] SHUTDOWN_OWNED_EXECUTORS
    -> shutdown(), awaitTermination(deadline)
    -> nếu kẹt, escalate shutdownNow() theo policy
    -> vẫn phải xem xét items chưa hoàn tất

[6] RECONCILE
    -> retry/dead-letter/ack theo contract nghiệp vụ
```

### 36.1. Ai có quyền gửi STOP?

Coordinator/owner biết **khi nào producers hoàn tất** và **có bao nhiêu consumers cần dừng**. Một producer riêng lẻ không nên tự gửi STOP khi nó xong nếu producers khác còn có thể enqueue.

### 36.2. Bounded queue đầy khiến STOP bị kẹt

`put(STOP)` có thể block khi queue đầy mà consumers không còn tiến. Khi shutdown cần deadline, dùng `offer(STOP,timeout,unit)` và kiểm `false`; nếu thất bại, báo lỗi/abort theo policy. Không ghi log “stopped” khi token chưa được chấp nhận.

### 36.3. Không dùng queue.isEmpty làm join

Ngay khi consumer `take` item cuối, queue có thể empty dù handler đang xử lý. Đợi consumer Future và job acknowledgements, không dùng riêng size/empty.

### 36.4. Race giữa accepting và offer

`if(accepting.get()) q.offer(job)` không atomic với `accepting.set(false)` của coordinator. Producer có thể vượt qua check rồi enqueue muộn sau STOP. Phải có lifecycle gate/join producers, không chỉ một boolean.

## 37. Abort, deadlines và khôi phục

Nếu hết thời hạn hoặc hệ thống gặp lỗi không thể phục hồi:

1. Dừng ingress và ngăn producers tạo việc mới.
2. Tín hiệu cancellation tới worker tasks/Futures thuộc quyền điều phối.
3. Chờ worker phản hồi interrupt/cancellation nếu có.
4. Executor owner gọi `shutdownNow()` khi chính sách yêu cầu.
5. Gọi `awaitTermination` có timeout và kiểm kết quả.
6. Thu hồi phần pending trong queue khi phù hợp, nhưng nhớ còn in-flight work.
7. Ghi nhận failed jobs/ids, retry/dead-letter từ store bền vững nếu cần.

`shutdownNow()` **không rollback** side effects. Một job có thể đã ghi DB hoặc gửi external request trước khi bị interrupt. Với jobs quan trọng, cần idempotency keys, transactions hoặc compensation.

### 37.1. drainTo không phải close

`drainTo` lấy phần items còn queue, không lấy những gì consumer đã remove; không phải transactional checkpoint. Khi hệ thống vẫn có producers/consumers, kết quả drain có thể thay đổi theo race.

### 37.2. Theo dõi Future exceptional

`Future.get` có thể ném `ExecutionException` với cause từ handler, hoặc `CancellationException` khi bị hủy. `isDone()==true` có thể là success, failure hoặc cancellation; không đồng nghĩa job thành công.

### 37.3. Timeouts không tự cancel

`Future.get(5,SECONDS)` hết hạn chỉ làm caller thôi chờ; task có thể còn chạy. Khi cần hủy, caller phải quyết định `cancel` và thu thập cleanup outcome.

### 37.4. Chỉ owner shutdown executor

Một library mượn executor từ DI/container không được gọi `shutdown/shutdownNow` làm các modules khác bị từ chối. `ExecutorService` trên **Java 17 chưa có `close()`/`AutoCloseable`** (bổ sung từ Java 19); các ví dụ dùng `try/finally`.

## 38. Bounded backpressure và tránh starvation

Bounded application `BlockingQueue` không làm internal queue của `Executors.newFixedThreadPool` cũng tự bounded. Nếu cần giới hạn submissions vào executor, dùng `ThreadPoolExecutor` có queue/capacity và rejection policy phù hợp.

Một deadlock dễ xảy ra:

```text
Executor has ONE worker.
Producer task gets worker and blocks put() on FULL business queue.
Consumer task is submitted to SAME executor but is queued.
Consumer cannot run to take() because producer holds only worker.
Producer cannot unblock because consumer cannot run.
```

Cần phân bố worker threads đủ, tách producer/consumer executors hoặc sử dụng nonblocking/async design. `Thread.interrupt`/`shutdownNow` có thể giúp abort nhưng không phải giải pháp correctness.

Các rủi ro khác:

- `LinkedBlockingQueue()` unbounded làm memory tăng khi producer nhanh.
- Nhiều queue/pools cộng lại vượt CPU/memory budget.
- Handler có blocking I/O và thiếu timeout.
- Producer bỏ qua false của timed offer.
- Consumer busy-spin trên `ConcurrentLinkedQueue.poll`.
- Dựa vào số lượng q.size làm metrics tuyệt đối khi concurrency cao.

## 39. Ma trận QA của 16 chương trình

| Chương trình | Mục tiêu đã kiểm | Kết quả quan trọng |
| --- | --- | --- |
| QueueOperationsDemo | Four BlockingQueue forms | offer false, timed false, take A |
| InterruptTakeDemo | Interrupt blocked take | caught, restored, worker exited |
| InterruptPutDemo | Interrupt blocked put | A còn, B chưa enqueue |
| FutureCancellationDemo | cancel(true) đang take | future canceled, worker thấy interrupt |
| CancelQueuedTaskDemo | cancel(false) pending task | task chưa chạy, canceled |
| PoisonPillOneDemo | 1 consumer + 1 STOP | processed AB, queue empty |
| MultiConsumerStopDemo | 2 consumers + 2 STOP | 6 unique, stopped 2 |
| ProducerCompletionDemo | Chờ 2 producers rồi STOP | P1 và P2 được nhận |
| TimedPollStopDemo | stop flag + timed poll | processed A, không poison |
| GracefulExecutorDemo | shutdown không wake take | false trước token, true sau |
| ImmediateShutdownDemo | shutdownNow interrupt take | worker exited, pool terminated |
| FailedConsumerDemo | Consumer thất bại sau take | item removed nhưng Future failed |
| DrainToDemo | Drain pending items | A B drained, C D còn |
| MemoryVisibilityQueueDemo | Happens-before qua queue | đọc 42 |
| SynchronousHandoffDemo | Capacity0/receiver handoff | offer false, Y delivered |
| ConcurrentLinkedQueueDemo | Nonblocking poll | A B null, không take |

Mười sáu class độc lập đã được biên dịch với `javac --release 17 -encoding UTF-8` và chạy thành công, stdout như trình bày. Thời hạn 30ms/40ms/5s trong các demos để không làm test chờ vô hạn, **không phải guarantee về latency**.

### 39.1. Tránh golden tests phụ thuộc lịch chạy

Không assert thread A phải nhận job 1, số threads active chính xác hoặc một `get` hoàn tất trong 1ms. Nên assert jobs unique, số consumers đã thoát, kết quả/cancellation/exception và resource cleanup.

## 40. Những lỗi thường gặp

1. Coi `BlockingQueue` có phương thức `close()` trong Java 17.
2. Gọi `executor.shutdown()` rồi nghĩ queue.take được đánh thức.
3. Đưa null vào queue làm STOP.
4. Chỉ gửi một STOP token cho nhiều consumers.
5. Gửi STOP khi một producer vẫn có thể enqueue.
6. Không kiểm `offer(STOP)` trả false trên bounded queue.
7. Gửi STOP vào queue đầy khi consumers đã ngừng.
8. Dùng FIFO STOP logic trên PriorityBlockingQueue hoặc DelayQueue.
9. Bắt InterruptedException rồi lặp vô hạn dù interrupt flag vẫn set.
10. Bắt interrupt rồi bỏ tín hiệu mà không có policy.
11. Coi cancel(true) luôn dừng computation và side effects ngay.
12. Nghĩ Future.get(timeout) tự hủy job.
13. Dùng queue.isEmpty/size==0 như “all work done”.
14. Consumer lấy item rồi throw, không có retry/idempotency.
15. Dùng drainTo như một giao dịch thu hồi cả in-flight work.
16. Không xử lý ExecutionException của consumer Futures.
17. Chỉ shutdownNow mà không awaitTermination.
18. Không kiểm awaitTermination trả false.
19. Dùng unbounded queues với producer rate không giới hạn.
20. Busy-spin `ConcurrentLinkedQueue.poll()` khi rỗng.
21. Nghĩ ConcurrentLinkedQueue có take/put.
22. Coi SynchronousQueue.size==0 đồng nghĩa không có put đang đợi.
23. Cùng pool một worker cho producer blocked và consumer queued.
24. Shutdown executor được mượn từ thư viện khác.
25. Dùng null, user text hoặc mutable shared token làm STOP mơ hồ.
26. Coi isDone của Future là success.
27. Dùng sleeps để giả lập synchronization trong tests.
28. Không có quy trình dừng riêng producer, consumer và pool.
29. Không có cách recovery khi process crash.
30. Tự nhận “exactly once” chỉ nhờ BlockingQueue trong heap.

## 41. Câu hỏi và đáp án

**1.** `BlockingQueue` có `close()`? **Không**; thiết kế giao thức kết thúc.

**2.** `take()` queue rỗng làm gì? **Chờ item hoặc bị interrupt**.

**3.** `poll()` queue rỗng? **Trả null ngay**.

**4.** `poll(1,SECONDS)` queue rỗng? **Chờ tối đa khoảng 1 giây, null nếu timeout; có thể bị interrupt**.

**5.** `offer(e)` queue đầy? **False**.

**6.** `put(e)` queue đầy? **Chờ chỗ hoặc InterruptedException**.

**7.** Có thể dùng null STOP không? **Không**.

**8.** Catch InterruptedException khi quyết định thoát? **Propagate hoặc restore cờ ở boundary phù hợp**.

**9.** `Thread.interrupt` là kill thread? **Không**, tín hiệu hợp tác.

**10.** `Future.cancel(true)` đảm bảo handler đã rollback? **Không**.

**11.** Future đã cancel có `get()` trả partial result? **Không; CancellationException**.

**12.** `cancel(false)` có thể ngăn job chưa chạy? **Có**.

**13.** `executor.shutdown()` đánh thức queue.take? **Không**.

**14.** Hai consumers cần bao nhiêu STOP token đơn giản? **Hai**.

**15.** Gửi STOP trước khi producers xong có thể xảy ra gì? **Consumer thoát, item sau STOP bị bỏ lại**.

**16.** Timed poll + stop flag cần điều kiện gì? **Không còn producer nào enqueue sau khi stop được công bố**.

**17.** `isEmpty()==true` chứng minh all processed? **Không; còn in-flight**.

**18.** Handler throw sau take, item tự quay lại queue? **Không**.

**19.** Cần sống qua JVM crash? **Durable broker/store, ack, retry/idempotency**.

**20.** `drainTo` có thu hồi item worker đã lấy? **Không**.

**21.** `SynchronousQueue` capacity bao nhiêu? **0**.

**22.** SynchronousQueue.offer không receiver có thể false? **Có**.

**23.** `ConcurrentLinkedQueue` có take? **Không**.

**24.** Vòng poll không chờ trên queue rỗng có rủi ro gì? **Busy-spin CPU**.

**25.** `LinkedBlockingQueue()` default capacity? **Integer.MAX_VALUE**, cần cân nhắc memory.

**26.** `shutdownNow()` chắc chắn dừng task không check interrupt? **Không**.

**27.** Tại sao không shutdown shared executor từ borrower? **Ảnh hưởng tasks của modules khác**.

**28.** `Future.get(timeout)` có hủy task? **Không**.

**29.** Queue.publish dữ liệu trước put được consumer thấy nhờ gì? **Happens-before**.

**30.** Cờ AtomicBoolean dừng producer có tự đồng bộ tuyệt đối với offer? **Không**, cần coordination/join.

**31.** Executor có worker bị chặn put, consumer queued cùng pool một worker: lỗi gì? **Starvation/deadlock**.

**32.** Thứ tự graceful shutdown? **Stop ingress → join producers → send stop signals → join consumers → shutdown executors → reconcile jobs**.

## 42. Checklist trước khi vận hành

- [ ] Queue type và capacity phù hợp; có backpressure.
- [ ] Phân biệt business queue với executor internal queue.
- [ ] Kiểm `offer` false và `poll` null.
- [ ] Biết `put/take` và timed variants có thể throw InterruptedException.
- [ ] Không dùng null làm poison.
- [ ] Có typed STOP/non-null sentinel.
- [ ] Một STOP cho mỗi consumer theo protocol.
- [ ] Producers đã dừng hẳn trước khi gửi STOP.
- [ ] Xử lý queue đầy khi gửi STOP với timeout/recovery.
- [ ] Không dùng FIFO STOP trên priority/delay queue một cách mù quáng.
- [ ] Timed poll + stop flag chỉ thoát khi không thể có enqueue mới.
- [ ] InterruptedException được propagate/restore hợp lý và worker thoát.
- [ ] Không restore interrupt rồi loop vô hạn.
- [ ] Cancel(true) và shutdownNow được coi là best effort.
- [ ] Chờ consumer Futures và inspect exceptions/cancellation.
- [ ] Owner quản lý shutdown/awaitTermination của executor riêng.
- [ ] Không đóng executor được mượn hoặc common pool.
- [ ] Không tin isEmpty nghĩa all processed.
- [ ] Theo dõi accepted, queued, in-flight, processed, failed và ack.
- [ ] Khi cần không mất job, có durable store/ack/retry/idempotency.
- [ ] Không dùng drainTo thay durable checkpoint.
- [ ] Không busy-spin ConcurrentLinkedQueue.
- [ ] Có kiểm thử bounded/full/empty/interrupt/cancel/STOP/deadline.
- [ ] Không phụ thuộc thread scheduling hoặc exact timing.
- [ ] Sử dụng API còn hoạt động trên Java 17+.

## 43. Tài liệu Java SE 17 chính thức

- [`BlockingQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): bốn nhóm operations, interruption, absence of intrinsic close/shutdown, memory consistency.
- [`ArrayBlockingQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO queue.
- [`LinkedBlockingQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): bounded/unbounded capacity choices.
- [`SynchronousQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): direct handoff, capacity zero.
- [`ConcurrentLinkedQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): nonblocking FIFO, `size()` characteristics.
- [`PriorityBlockingQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): priority ordering.
- [`DelayQueue<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html): timed/expired elements.
- [`ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, shutdown, shutdownNow, awaitTermination.
- [`ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): work queues, rejection, shutdownNow.
- [`ForkJoinPool`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): implementation-specific shutdownNow.
- [`Future<V>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): cancellation/get status.
- [`Thread`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): interruption.
- [`TimeUnit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): deadline parameters.

**Kết luận:** **Ngắt thread**, **hủy một Future**, **cho consumer thoát vòng lặp** và **shutdown executor** không đồng nghĩa. Queue không có close native; muốn dừng đúng, trước hết ngăn producers enqueue, xử lý/ghi nhận phần việc đã nhận, phát đủ stop signals hoặc dùng polling có điều kiện, rồi chờ consumers trước khi owner đóng executor. Nếu cần abort, interrupt/cancel/shutdownNow chỉ là best effort; phải theo dõi in-flight work, failures và recovery thay vì tin rằng queue rỗng nghĩa toàn bộ công việc đã thành công.