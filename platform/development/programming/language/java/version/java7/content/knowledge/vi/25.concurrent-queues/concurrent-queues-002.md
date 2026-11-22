# TransferQueue và LinkedTransferQueue — bàn giao dữ liệu giữa các luồng trong Java

**Chủ đề:** Java 7 — Hàng đợi đồng thời  
**Bài học:** TransferQueue cùng LinkedTransferQueue  
**Môi trường:** Java 17+; các API `java.util.concurrent.TransferQueue` và `java.util.concurrent.LinkedTransferQueue` được đưa vào từ Java 7 và **vẫn được hỗ trợ trong các bản Java hiện hành**. Các ví dụ chạy độc lập trên JDK 17+, không yêu cầu Maven, Gradle hoặc thư viện bên ngoài.

## 1. Vấn đề: “đưa vào hàng đợi” khác “đã có người nhận”

Trong một hệ thống producer–consumer, producer tạo nhiệm vụ còn consumer nhận nhiệm vụ để xử lý. Với hàng đợi thông thường, producer chỉ cần đưa phần tử vào queue:

```text
Producer                       Queue                       Consumer
   |                              |                             |
   +-- offer(job) ---------------->|                             |
   |<----- trả về ngay ------------+                             |
   |                              |---- take(job) -------------->|
   |                              |                             +-- process(job)
```

Khi `offer` thành công, điều đó chỉ có nghĩa queue **đã chấp nhận phần tử**, không có nghĩa consumer đã lấy nó, càng không có nghĩa xử lý nghiệp vụ đã hoàn tất.

Một số ứng dụng cần tín hiệu mạnh hơn: producer **chờ cho tới khi có consumer nhận phần tử**, nhằm phối hợp hai phía:

```text
Producer                       LinkedTransferQueue              Consumer
   |                                  |                             |
   +-- transfer(job) ---------------->|                             |
   |               chờ consumer nhận  |                             |
   |                                  +-- take(job) ---------------->|
   |<--------- transfer trả về -------+                             |
   |                                                                +-- process(job)
```

**`TransferQueue<E>`** là interface hỗ trợ cả hai kiểu: **enqueue không chờ người nhận** hoặc **transfer có xác nhận rằng người nhận đã lấy phần tử**. **`LinkedTransferQueue<E>`** là một implementation dựa trên liên kết các nodes, **không giới hạn capacity theo cấu hình**.

**Giới hạn quan trọng nhất:** `transfer(e)` chờ đến khi consumer **nhận** phần tử bằng `take` hoặc `poll`, **không chờ consumer xử lý xong**, không chờ database commit, không phải transaction và không cung cấp exactly-once business execution. Nếu cần xác nhận **đã xử lý xong**, ứng dụng phải có acknowledgment riêng.

### 1.1. Mục tiêu bài học

Sau bài này, bạn cần:

1. Giải thích quan hệ `TransferQueue` → `BlockingQueue` và lý do chọn `LinkedTransferQueue`.
2. Phân biệt `offer`, `put`, `transfer`, `tryTransfer` và `tryTransfer` có timeout.
3. Biết lúc nào producer bị block và lúc nào phần tử không được enqueue.
4. Dùng `take`, `poll` và cơ chế interrupt/timeout để xây producer–consumer không treo.
5. Hiểu `hasWaitingConsumer` và `getWaitingConsumerCount` chỉ biểu diễn snapshot/estimate, **không phải cơ chế đồng bộ nghiệp vụ**.
6. Phòng tránh nguy cơ RAM tăng vô hạn của queue unbounded; áp dụng quota hoặc semaphore để tạo backpressure.
7. Tách tín hiệu “đã nhận” với acknowledgment “đã xử lý”.
8. Thiết kế shutdown, xử lý lỗi, memory visibility và correctness khi nhiều producer/consumer đồng thời.
9. Kiểm chứng bằng chương trình Java 17+ biên dịch và chạy được, kết quả không phụ thuộc scheduling ngẫu nhiên.

## 2. Cấu trúc API và ý nghĩa của interface

Sơ đồ quan hệ kế thừa:

```text
java.lang.Iterable<E>
        |
java.util.Collection<E>
        |
java.util.Queue<E>
        |
java.util.concurrent.BlockingQueue<E>
        |
java.util.concurrent.TransferQueue<E>           (interface)
        ^
        |
java.util.concurrent.LinkedTransferQueue<E>     (implementation)
```

`TransferQueue<E>` **kế thừa `BlockingQueue<E>`**, vì thế nó vẫn cung cấp các thao tác queue thông thường như `offer`, `put`, `take`, `poll`, `peek` và `drainTo`. Nó **bổ sung** nhóm operations để producer lựa chọn đợi consumer nhận.

Trong Java hiện hành, implementation chuẩn quen thuộc nhất là `LinkedTransferQueue<E>`. Hãy khai báo theo interface nếu muốn giữ abstraction:

```java
TransferQueue<String> messages = new LinkedTransferQueue<>();
```

Đây là snippet có thể nằm trong một method/class đã import `java.util.concurrent.*`. Nếu cần các operations riêng của implementation như `size`/`drainTo`, chúng cũng được kế thừa từ các interface queue/collection thích hợp.

### 2.1. Khác nhau giữa “unbounded” và “vô hạn bộ nhớ”

`LinkedTransferQueue` được định nghĩa là **unbounded**: không có một **capacity limit** cấu hình sẵn như `ArrayBlockingQueue<>(100)`. Điều đó không có nghĩa JVM có RAM vô hạn.

- `put(e)` không block vì queue đầy theo capacity, và `offer(e)` không trả false chỉ vì hết slot theo cấu hình.
- Queue vẫn có thể giữ rất nhiều nodes/objects, dẫn đến tăng heap, GC pressure và `OutOfMemoryError` trong hệ thống bị quá tải.
- `remainingCapacity()` của `LinkedTransferQueue` luôn trả `Integer.MAX_VALUE`, **không phải lượng RAM thực còn dùng được**.
- Một service dùng queue unbounded cần backpressure ở **tầng khác** (ví dụ semaphore giới hạn in-flight, admission control, rate limit, per-tenant quota), hoặc chọn queue bounded nếu handoff semantics không cần thiết.

**Không sử dụng `remainingCapacity()` của `LinkedTransferQueue` làm điều kiện cho phép nhận thêm bao nhiêu payload theo RAM.**

### 2.2. TransferQueue interface có thể có implementation bounded không?

Có. Hợp đồng `TransferQueue` **không bắt buộc tất cả implementations đều unbounded**. JavaDoc nêu rõ implementations có thể có capacity giới hạn; với một implementation như vậy, producer còn có thể phải chờ **chỗ trống** trước khi chờ consumer nhận. `LinkedTransferQueue` cụ thể là unbounded, nên phần lớn ví dụ trong bài không có bước chờ capacity.

## 3. So sánh các thao tác producer

| Operation | Mục tiêu | Có thể chờ consumer nhận? | Khi không có consumer |
| --- | --- | --- | --- |
| `offer(e)` | Thêm phần tử vào queue, trả boolean | **Không** | Với LinkedTransferQueue, trả `true` và phần tử được giữ trong queue |
| `add(e)` | Thêm phần tử, trả boolean | **Không** | Với LinkedTransferQueue, trả `true` |
| `put(e)` | Thêm phần tử theo hợp đồng BlockingQueue | **Không do capacity** với LinkedTransferQueue | Phần tử được queue; method không chờ đến lúc consumer lấy |
| `offer(e,t,u)` | Thêm phần tử với thời gian chờ chỗ trống theo BlockingQueue | **Không do capacity** với LinkedTransferQueue | Trả `true` ngay với queue unbounded; timeout không trở thành “chờ nhận” |
| `transfer(e)` | Chuyển phần tử **và chờ consumer nhận** | **Có** | Enqueue phần tử chờ được lấy; producer block tới khi có consumer nhận hoặc bị interrupt |
| `tryTransfer(e)` | Chỉ chuyển nếu có consumer **đang chờ** | **Không block** | Trả `false` và **không enqueue** |
| `tryTransfer(e,t,u)` | Chờ consumer nhận tối đa timeout | **Có, có giới hạn** | Nếu hết thời hạn, trả `false` và **không để phần tử lại trong queue** |

**Lưu ý:** với các implementations khác của `TransferQueue`, chính sách capacity có thể khác; bảng tập trung vào `LinkedTransferQueue` khi giải thích các thao tác inherited `BlockingQueue`.

### 3.1. Vì sao tên put có thể gây nhầm?

Trong `BlockingQueue` **có giới hạn capacity**, `put` có thể block khi queue đầy. Nhưng `LinkedTransferQueue` **không có capacity giới hạn**, nên `put` của implementation này chỉ enqueue, không chờ consumer nhận và không chờ slot trống.

**Mẫu sai về kỳ vọng:**

```java
queue.put(job);
// Sai nếu cho rằng đến dòng này, consumer đã nhận hoặc xử lý job.
markJobAsProcessed(job);
```

Đây chỉ là snippet minh họa logic sai, `queue`/`job` và `markJobAsProcessed` là thành phần ứng dụng.

### 3.2. Với transfer, consumer có cần đứng chờ sẵn không?

**Không.** Nếu consumer đang chờ trong `take` hoặc timed `poll`, phần tử có thể được chuyển trực tiếp. Nếu không có consumer chờ, `LinkedTransferQueue.transfer` chèn phần tử vào queue và **đợi** tới khi consumer nhận. Vì vậy nó khác với `tryTransfer(e)` nonblocking.

### 3.3. “Bàn giao” không bảo đảm xử lý xong

`transfer(e)` trở về sau khi phần tử được **received** bởi consumer, không sau khi business logic của consumer thành công. Consumer hoàn toàn có thể crash ngay sau `take()` và trước DB commit.

Nếu nghiệp vụ yêu cầu “producer biết job đã ghi thành công”, dùng `CompletableFuture<Result>`/correlation ID/response channel/ack protocol và chỉ complete sau khi consumer xử lý thành công. Với message quan trọng qua process boundaries, cân nhắc durable messaging và idempotency; một in-memory transfer queue không phải hàng đợi bền vững.

## 4. Ví dụ chính: producer chờ đến khi consumer take()

Tạo `TransferQueueHandoffDemo.java`:

```java
import java.util.concurrent.*;
public class TransferQueueHandoffDemo {
  public static void main(String[] args) throws Exception {
    TransferQueue<String> queue = new LinkedTransferQueue<>();
    ExecutorService executor = Executors.newFixedThreadPool(2);
    CountDownLatch ready = new CountDownLatch(1);
    try {
      Future<?> producer = executor.submit(() -> {
        ready.countDown();
        queue.transfer("alpha");
        return null;
      });
      if (!ready.await(5, TimeUnit.SECONDS)) throw new IllegalStateException("not started");
      System.out.println("producer-done-before-consumer=" + producer.isDone());
      Future<String> consumer = executor.submit(queue::take);
      System.out.println("taken=" + consumer.get(5, TimeUnit.SECONDS));
      producer.get(5, TimeUnit.SECONDS);
      System.out.println("producer-done-after-consumer=" + producer.isDone());
      System.out.println("queue-empty=" + queue.isEmpty());
    } finally {
      executor.shutdownNow();
      executor.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac -encoding UTF-8 -Xlint:all TransferQueueHandoffDemo.java
java TransferQueueHandoffDemo
```

**stdout đã chạy kiểm thử:**

```text
producer-done-before-consumer=false
taken=alpha
producer-done-after-consumer=true
queue-empty=true
```

### 4.1. Phân tích thứ tự có thể kiểm chứng

1. Producer chạy trong executor, thông báo `ready` trước khi gọi `transfer("alpha")`.
2. Main đợi `ready` rồi in `producer.isDone()`: trước khi tạo consumer, producer **chưa có cách để hoàn tất transfer**, nên `false`.
3. Main submit consumer gọi `queue.take()`.
4. Consumer nhận `alpha`, thao tác transfer được thỏa; cả producer và consumer cuối cùng hoàn tất.
5. Main `get(5,SECONDS)` hai Futures **trên thread test**, không để các worker đợi vô hạn.
6. Queue đã lấy phần tử nên `isEmpty()` là `true`.

**Kỹ thuật kiểm thử:** sử dụng `CountDownLatch` để đánh dấu producer đã bắt đầu, không sử dụng `Thread.sleep` để đoán thứ tự. `Future.isDone()` không được dùng làm giao thức handoff trong ứng dụng; nó chỉ minh họa trong harness này.

### 4.2. Vì sao hai threads là đủ?

Một producer cần khả năng block tại `transfer`, trong khi consumer cần một thread có thể chạy tới `take`. Pool hai worker threads cho phép cả hai tiến. Nếu tạo **single-thread pool** rồi submit producer transfer trước consumer take, producer sẽ giữ thread chờ, còn consumer nằm trong queue của executor không được chạy → **thread-pool starvation deadlock**.

Giải pháp không phải đơn giản tăng threads vô hạn: có thể thay bằng `offer` + consumer async workflow nếu không yêu cầu handoff, hoặc đảm bảo executor/threads đủ capacity cho các dependencies và có timeouts/recovery.

## 5. Enqueue thông thường: offer, put, add đều không đợi receipt

Tạo `TransferQueueOfferPutDemo.java`:

```java
import java.util.concurrent.*;
public class TransferQueueOfferPutDemo {
  public static void main(String[] args) throws Exception {
    LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();
    System.out.println("offer-success=" + queue.offer("A"));
    queue.put("B");
    queue.add("C");
    System.out.println("initial-size=" + queue.size());
    System.out.println("take1=" + queue.take());
    System.out.println("take2=" + queue.take());
    System.out.println("take3=" + queue.take());
    System.out.println("unbounded-capacity=" + (queue.remainingCapacity() == Integer.MAX_VALUE));
    boolean rejected = false;
    try { queue.offer(null); }
    catch (NullPointerException ex) { rejected = true; }
    System.out.println("reject-null=" + rejected);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all TransferQueueOfferPutDemo.java
java TransferQueueOfferPutDemo
```

**stdout đã kiểm thử:**

```text
offer-success=true
initial-size=3
take1=A
take2=B
take3=C
unbounded-capacity=true
reject-null=true
```

**Vì sao FIFO ở đây đáng tin?** Chỉ có **một producer** lần lượt gọi `offer("A")`, `put("B")`, `add("C")` rồi cùng thread `take` cả ba; `LinkedTransferQueue` duy trì thứ tự FIFO **đối với từng producer**.

**Không suy từ ví dụ rằng hai producers chạy đồng thời phải có một thứ tự được dự đoán trước**. Queue có thể xen kẽ các phần tử từ các producers khác nhau theo scheduling. Nếu cần thứ tự nghiệp vụ toàn cục, hãy gắn sequence numbers, serialize ở một coordinator hoặc áp dụng protocol ordering ngoài queue.

### 5.1. Null không có nghĩa là “đã hết dữ liệu”

`LinkedTransferQueue` **không cho phép phần tử `null`** và ném `NullPointerException`. `poll()` trả `null` khi queue rỗng, nên nếu cho phép lưu `null` thì không phân biệt được dữ liệu thật và tín hiệu “không có item”.

**Shutdown không dùng null sentinel.** Dùng một message/record đặc biệt kiểu-safe (poison pill), cancellation token hoặc đóng component sở hữu workers theo giao thức rõ. Phần 13 có ví dụ với hai consumers.

### 5.2. Chỉ khi consumer chưa có sẵn mới cần lưu trong queue?

Không hẳn. `offer`/`put` luôn diễn đạt **enqueue operation**. Nếu consumer đang chờ, implementation có thể đưa item trực tiếp đến consumer; nếu chưa có consumer, item được lưu để lấy sau. Nhưng **producer không chờ consumer xử lý** ở các operations thông thường.

## 6. tryTransfer(e): thử bàn giao ngay, không tạo backlog

`tryTransfer(e)` có nghĩa **“có consumer đang chờ ngay lúc này để nhận e hay không?”**

- Nếu có consumer đang đợi trong `take` hoặc timed `poll`, method có thể chuyển phần tử, trả `true`.
- Nếu không có, method trả `false` **ngay** và **không enqueue e**.
- Không được viết `queue.tryTransfer(job);` rồi bỏ qua boolean nếu không muốn làm mất job.
- Đây **không** phải alias của `offer(e)`.

### 6.1. Ví dụ runnable: không có consumer thì không enqueue

Tạo `TransferQueueTryTransferNoConsumerDemo.java`:

```java
import java.util.concurrent.*;
public class TransferQueueTryTransferNoConsumerDemo {
  public static void main(String[] args) throws Exception {
    TransferQueue<String> queue = new LinkedTransferQueue<>();
    System.out.println("immediate-transfer=" + queue.tryTransfer("not-queued"));
    System.out.println("empty-after-immediate=" + queue.isEmpty());
    System.out.println("timed-transfer=" + queue.tryTransfer("also-not-queued", 20, TimeUnit.MILLISECONDS));
    System.out.println("empty-after-timeout=" + queue.isEmpty());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all TransferQueueTryTransferNoConsumerDemo.java
java TransferQueueTryTransferNoConsumerDemo
```

**stdout đã kiểm thử:**

```text
immediate-transfer=false
empty-after-immediate=true
timed-transfer=false
empty-after-timeout=true
```

Không có consumer nào được tạo, nên cả thử ngay và chờ 20 ms đều không thể handoff. Hai lần trả `false` không để phần tử tồn tại trong queue.

**Khi nào hữu ích?** Khi dữ liệu có thể bị bỏ nếu không có người nghe (ví dụ một event telemetry best-effort mà ứng dụng đã quy định rõ policy). Nếu không được phép mất job, **hãy xử lý false**: chuyển sang `offer` nếu có quota, retry có kiểm soát hoặc báo thất bại lên caller.

### 6.2. Anti-pattern dễ mất dữ liệu

```java
queue.tryTransfer(job);      // Trả false nhưng bị bỏ qua.
markAsAccepted(job);         // Nghiệp vụ cho rằng job đã được giao.
```

Đây là snippet minh họa anti-pattern, không phải chương trình độc lập. Nếu không có waiting consumer, job **không nằm trong queue** nhưng hệ thống đã đánh dấu accepted. Hãy phân biệt trạng thái **rejected/no-receiver** với **delivered**.

## 7. hasWaitingConsumer và getWaitingConsumerCount chỉ là snapshot

`TransferQueue` cung cấp:

- `hasWaitingConsumer()`: có ít nhất một consumer đang chờ trong `take()` hoặc timed `poll()` ở thời điểm quan sát không?
- `getWaitingConsumerCount()`: **ước lượng** số consumers đang chờ, có thể đã thay đổi ngay trước khi caller nhận kết quả.

Theo JavaDoc, **không nên sử dụng số consumers đang chờ làm synchronization control**. Sau `hasWaitingConsumer()==true`, consumer có thể timeout/cancel hoặc bị producer khác ghép cặp trước khi bạn gọi `tryTransfer`. Đây là classic **check-then-act race**.

**Đúng:** gọi `tryTransfer(e)` rồi kiểm tra **boolean thực**.  
**Không đúng:** kiểm tra `hasWaitingConsumer()` một lần rồi mặc nhiên `transfer` sẽ không block.

### 7.1. Ví dụ runnable: consumer chờ và tryTransfer thành công

Tạo `TransferQueueTryTransferWaitingDemo.java`:

```java
import java.util.concurrent.*;
public class TransferQueueTryTransferWaitingDemo {
  public static void main(String[] args) throws Exception {
    TransferQueue<String> queue = new LinkedTransferQueue<>();
    ExecutorService executor = Executors.newSingleThreadExecutor();
    try {
      Future<String> waiting = executor.submit(queue::take);
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
      while (!queue.hasWaitingConsumer() && System.nanoTime() < deadline) {
        Thread.onSpinWait(); // test harness only
      }
      if (!queue.hasWaitingConsumer()) throw new IllegalStateException("no waiting consumer");
      System.out.println("has-waiting-before=true");
      System.out.println("try-transfer=" + queue.tryTransfer("direct"));
      System.out.println("received=" + waiting.get(5, TimeUnit.SECONDS));
      System.out.println("has-waiting-after=" + queue.hasWaitingConsumer());
    } finally {
      executor.shutdownNow();
      executor.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all TransferQueueTryTransferWaitingDemo.java
java TransferQueueTryTransferWaitingDemo
```

**stdout đã kiểm thử:**

```text
has-waiting-before=true
try-transfer=true
received=direct
has-waiting-after=false
```

**Giải thích kiểm thử:** harness chỉ có một consumer đang chờ và chưa có producer khác. Vòng kiểm tra `hasWaitingConsumer` cùng deadline 5 giây giúp test chờ đến khi consumer đã vào `take`; sau đó main thử bàn giao trực tiếp và đợi Future kết quả.

**Không copy vòng `Thread.onSpinWait()` vào production.** Nó là dụng cụ kiểm thử có thời hạn, có thể tốn CPU. Trong code nghiệp vụ, `tryTransfer` **chính nó** là operation có kết quả quyết định. Việc lấy snapshot rồi spin có thể thay đổi ngay dưới tải nhiều threads và không phải concurrency protocol đáng tin.

### 7.2. Tại sao getWaitingConsumerCount có thể tốn chi phí?

Đếm consumers đang chờ có thể cần duyệt cấu trúc nội bộ và JavaDoc gọi đây là **estimate**. Nó có ích cho monitoring/heuristics ở tần suất thấp; không nên polling liên tục mỗi request để “đợi đúng hai consumers” rồi mới dispatch.

## 8. tryTransfer(e, timeout, unit): handoff có deadline

Hợp đồng timed overload:

```java
boolean delivered =
        queue.tryTransfer(message, 2, TimeUnit.SECONDS);
```

Đây là snippet. Nếu consumer nhận kịp, method trả `true`. Nếu hết thời hạn mà không có consumer nhận, method trả `false` và **phần tử không bị để lại trong queue**. Nếu thread đang chờ bị interrupt, ném `InterruptedException` và cũng không để phần tử lại theo contract.

**Không nhầm với `offer(e, timeout, unit)` của LinkedTransferQueue:** `offer` là enqueue không chờ capacity; timed `tryTransfer` là chờ **consumer receipt**.

### 8.1. Ví dụ runnable: consumer đến trong thời hạn

Tạo `TransferQueueTimedTransferSuccessDemo.java`:

```java
import java.util.concurrent.*;
public class TransferQueueTimedTransferSuccessDemo {
  public static void main(String[] args) throws Exception {
    TransferQueue<String> queue = new LinkedTransferQueue<>();
    ExecutorService executor = Executors.newFixedThreadPool(2);
    CountDownLatch started = new CountDownLatch(1);
    try {
      Future<Boolean> producer = executor.submit(() -> {
        started.countDown();
        return queue.tryTransfer("timed-handoff", 5, TimeUnit.SECONDS);
      });
      if (!started.await(5, TimeUnit.SECONDS)) throw new IllegalStateException("not started");
      Future<String> consumer = executor.submit(queue::take);
      System.out.println("transfer-success=" + producer.get(5, TimeUnit.SECONDS));
      System.out.println("taken=" + consumer.get(5, TimeUnit.SECONDS));
      System.out.println("remaining=" + queue.size());
    } finally {
      executor.shutdownNow();
      executor.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all TransferQueueTimedTransferSuccessDemo.java
java TransferQueueTimedTransferSuccessDemo
```

**stdout đã kiểm thử:**

```text
transfer-success=true
taken=timed-handoff
remaining=0
```

Producer được tạo trước, consumer được tạo sau khi producer thông báo bắt đầu. Consumer lấy message trong thời hạn 5 giây; `tryTransfer` trả true. Đây là timeout của **handoff**, không phải deadline xử lý nghiệp vụ của consumer sau `take`.

### 8.2. Nếu timeout thì có thể retry y hệt không?

Chỉ khi contract nghiệp vụ cho phép. `tryTransfer` trả `false` khi không handoff, nên tại tầng queue element **không bị để lại**. Nhưng application-level workflow có thể đã làm bước khác trước đó. Retry phải xét identity/idempotency, số lần thử, request deadline và resource quotas.

Ví dụ producer xây một message có request ID và một worker có thể nhận bản retry từ nguồn khác. Nếu yêu cầu không tạo duplicate work, phải có deduplication tại tầng ứng dụng.

### 8.3. Interrupt trong khi chờ

`transfer` và timed `tryTransfer` là **interruptible blocking operations** theo hợp đồng. Caller có thể nhận `InterruptedException`; khi đó không để lại phần tử đang chờ trong queue. Theo thói quen Java hiện đại, nếu method không truyền exception lên trên, thường restore interrupt flag bằng `Thread.currentThread().interrupt()` trước khi rời boundary.

**Đừng bắt InterruptedException rồi tiếp tục chờ vô hạn** mà không có cleanup/cancellation policy. Với service shutdown, interruption là tín hiệu quan trọng.

## 9. Ví dụ interrupt: producer đang đợi được giải phóng

Tạo `TransferQueueInterruptDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
public class TransferQueueInterruptDemo {
  public static void main(String[] args) throws Exception {
    LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();
    CountDownLatch started = new CountDownLatch(1);
    AtomicReference<String> outcome = new AtomicReference<>("PENDING");
    Thread producer = new Thread(() -> {
      started.countDown();
      try {
        queue.transfer("orphan");
        outcome.set("RECEIVED");
      } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        outcome.set("INTERRUPTED");
      }
    }, "waiting-producer");
    producer.start();
    try {
      if (!started.await(5, TimeUnit.SECONDS)) throw new IllegalStateException("not started");
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
      while (!queue.contains("orphan") && System.nanoTime() < deadline) Thread.onSpinWait();
      if (!queue.contains("orphan")) throw new IllegalStateException("no waiting transfer");
      producer.interrupt();
      producer.join(5000);
      if (producer.isAlive()) throw new IllegalStateException("producer did not exit");
      System.out.println("outcome=" + outcome.get());
      System.out.println("queue-empty=" + queue.isEmpty());
    } finally {
      producer.interrupt();
      producer.join(5000);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all TransferQueueInterruptDemo.java
java TransferQueueInterruptDemo
```

**stdout đã kiểm thử:**

```text
outcome=INTERRUPTED
queue-empty=true
```

Trong test không có consumer. Producer thực hiện `transfer("orphan")`, phần tử chờ ở queue. Main đợi đến khi phần tử đã hiện diện bằng `contains` rồi interrupt producer. Producer nhận `InterruptedException`, restore interrupt flag và kết thúc; element không bị giữ lại trong queue theo contract.

**Lưu ý:** `contains` có thể cần duyệt nodes và không phù hợp làm cơ chế giám sát throughput của queue lớn; vòng `Thread.onSpinWait` chỉ phục vụ harness có deadline, không phải mẫu retry production.

### 9.1. Tại sao không dùng một Future.cancel(true) rồi mặc định tác vụ chắc chắn dừng?

`Future.cancel(true)` là một yêu cầu interrupt/best effort; nó không cam kết mọi arbitrary code dừng ngay. Trong demo, ta sở hữu trực tiếp thread, đợi join và đọc outcome để **xác minh thực sự đã thoát**.

Trong hệ thống thực, với `ExecutorService`, hãy dùng cancellation policy rõ, timed waits và kiểm tra worker terminal states. `LinkedTransferQueue` tự nó không có API `close()` để đánh thức tất cả producer/consumer đang chờ; việc cleanup thuộc về component sở hữu workers và messages.

## 10. Memory consistency: dữ liệu ghi trước handoff được nhìn thấy sau take

Một producer có thể xây object hoặc payload trong một thread rồi đặt nó vào queue; consumer ở thread khác lấy object. Tài liệu `LinkedTransferQueue` bảo đảm **memory consistency effects**: các actions xảy ra trước khi đưa object vào queue **happen-before** các actions sau khi thread khác lấy/access object đó từ queue.

Điều này giúp producer publish dữ liệu tới consumer an toàn hơn việc viết một reference vào non-volatile field rồi đợi consumer tự đoán khi nào dữ liệu sẵn sàng.

### 10.1. Ví dụ runnable: consumer nhìn thấy mảng đã được producer điền

Tạo `TransferQueueVisibilityDemo.java`:

```java
import java.util.concurrent.*;
public class TransferQueueVisibilityDemo {
  public static void main(String[] args) throws Exception {
    TransferQueue<int[]> queue = new LinkedTransferQueue<>();
    ExecutorService executor = Executors.newFixedThreadPool(2);
    try {
      Future<?> producer = executor.submit(() -> {
        int[] numbers = new int[3];
        numbers[0] = 3;
        numbers[1] = 5;
        numbers[2] = 7;
        queue.transfer(numbers);
        return null;
      });
      Future<Integer> consumer = executor.submit(() -> {
        int[] values = queue.take();
        return values[0] + values[1] + values[2];
      });
      System.out.println("visible-sum=" + consumer.get(5, TimeUnit.SECONDS));
      producer.get(5, TimeUnit.SECONDS);
      System.out.println("handoff-completed=true");
    } finally {
      executor.shutdownNow();
      executor.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all TransferQueueVisibilityDemo.java
java TransferQueueVisibilityDemo
```

**stdout đã kiểm thử:**

```text
visible-sum=15
handoff-completed=true
```

Producer tạo `int[]` rồi ghi lần lượt 3, 5, 7 **trước** khi transfer. Consumer nhận đúng các giá trị và tính tổng 15. Không cần thêm `volatile` cho từng phần tử mảng vì handoff qua concurrent collection tạo quan hệ happens-before thích hợp.

**Cảnh báo:** bảo đảm này không biến `int[]` thành immutable. Nếu producer **tiếp tục sửa mảng sau khi đặt vào queue**, consumer có thể đồng thời đọc/sửa và gây race. Nên chuyển quyền sở hữu payload, dùng immutable record hoặc copy khi cần. Queue quản lý an toàn phần tử trong cấu trúc của nó; nó không tự đồng bộ mọi mutation về sau của object đó.

### 10.2. Dùng record để truyền message

Java 17 có thể dùng `record` làm message dạng immutable container:

```java
record Job(long id, String text) {}

TransferQueue<Job> queue = new LinkedTransferQueue<>();
queue.offer(new Job(42, "READY"));
```

Đây là snippet. `record` bất biến ở mức **fields references/primitive values**, nhưng nếu component là `List` hoặc `byte[]` mutable, bản thân record **không deep-immutable**. Dùng `List.copyOf`/defensive copy nếu business contract yêu cầu snapshot.

## 11. Backpressure: queue unbounded vẫn cần quota

`LinkedTransferQueue` không tự giới hạn số phần tử. Dưới tải cao:

```text
Producers produce 100k messages/s
Consumers process 20k messages/s

Backlog grows ~80k messages/s
    -> heap retention
    -> GC overhead
    -> long queueing delay
    -> out-of-memory risk
```

Đó là **minh họa toán học với tốc độ giả định**, không phải benchmark của `LinkedTransferQueue`. Dù `offer`/`put` hoạt động rất nhanh, nếu hệ thống **nhận công việc nhanh hơn xử lý**, queue sẽ tích lũy payload.

**Các giải pháp:**

1. Chọn `ArrayBlockingQueue` hoặc `LinkedBlockingQueue(capacity)` khi cần bounded queue mà không cần `transfer`.
2. Nếu vẫn cần semantics của `TransferQueue`, dùng một **admission semaphore** hoặc quota ở tầng ứng dụng.
3. Chỉ release permit khi job đã **hoàn tất xử lý** hoặc được chuyển thành terminal failure có policy, chứ không chỉ vì consumer vừa `take`.
4. Đặt max payload size, max in-flight bytes/jobs, max concurrent producers và per-tenant quotas.
5. Theo dõi rejection/queue age và phản hồi `BUSY`/throttle khi quá tải.
6. Không đợi một permit trên một thread mà chính nó cần để giải phóng permit: vẫn có thể tạo dependency cycle.

### 11.1. Ví dụ runnable: giới hạn hai jobs đang in-flight

Tạo `TransferQueueBoundedIngressDemo.java`:

```java
import java.util.concurrent.*;
public class TransferQueueBoundedIngressDemo {
  public static void main(String[] args) throws Exception {
    LinkedTransferQueue<Integer> queue = new LinkedTransferQueue<>();
    Semaphore inFlight = new Semaphore(2);
    CountDownLatch twoQueued = new CountDownLatch(1);
    ExecutorService executor = Executors.newFixedThreadPool(2);
    try {
      Future<?> producer = executor.submit(() -> {
        for (int i = 1; i <= 5; i++) {
          inFlight.acquire();
          queue.put(i);
          if (i == 2) twoQueued.countDown();
        }
        return null;
      });
      if (!twoQueued.await(5, TimeUnit.SECONDS)) throw new IllegalStateException("not queued");
      System.out.println("queued-before-consumer=" + queue.size());
      System.out.println("permits-before-consumer=" + inFlight.availablePermits());
      Future<Integer> consumer = executor.submit(() -> {
        int total = 0;
        for (int i = 0; i < 5; i++) {
          int value = queue.take();
          total += value;
          inFlight.release(); // Release only after processing the item.
        }
        return total;
      });
      producer.get(5, TimeUnit.SECONDS);
      System.out.println("processed-sum=" + consumer.get(5, TimeUnit.SECONDS));
      System.out.println("permits-after=" + inFlight.availablePermits());
    } finally {
      executor.shutdownNow();
      executor.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all TransferQueueBoundedIngressDemo.java
java TransferQueueBoundedIngressDemo
```

**stdout đã kiểm thử:**

```text
queued-before-consumer=2
permits-before-consumer=0
processed-sum=15
permits-after=2
```

**Giải thích:**

- Semaphore cấp hai permits. Producer phải `acquire()` trước mỗi `put()`.
- Khi đã enqueue hai items đầu, hết permits; producer **không thể enqueue item thứ ba** trước khi consumer release permit.
- Main cố ý chỉ khởi động consumer sau khi nhận `twoQueued`, nên quan sát được queue có 2 items và permits=0 một cách deterministic.
- Consumer `take` và “xử lý” bằng cộng tổng rồi mới `release` permit.
- Sau 5 jobs, kết quả là 15 và cả hai permits trở lại.

**Đây là mô hình dạy học, chưa phải production error-handling đầy đủ.** Nếu sau `acquire` mà publish vào queue thất bại, phải release permit để không rò quota. Nếu consumer lỗi khi xử lý, phải release đúng một lần khi job vào trạng thái terminal (ví dụ `try/finally` gắn với lifecycle message), đồng thời chuyển job sang fail/retry policy. Nếu dùng retry, tránh double release. Mỗi permit đại diện một job **in-flight**, không phải một thread.

### 11.2. Tại sao không lấy size() làm giới hạn?

`LinkedTransferQueue.size()` có thể **O(n)** vì phải duyệt cấu trúc, và số trả về có thể không chính xác nếu queue được chỉnh sửa đồng thời. Logic:

```java
if (queue.size() < 1000) {
    queue.offer(job);
}
```

Đây là snippet **không an toàn để enforce quota**: nhiều producers có thể đồng thời thấy dưới 1000 rồi cùng enqueue vượt giới hạn; kiểm tra size và offer không atomic. Hãy dùng `Semaphore`/bounded queue/admission controller.

### 11.3. Vì sao transfer() không phải backpressure end-to-end?

`transfer` chặn producer cho đến khi consumer **nhận**, giúp hạn chế tiến độ producer trong một số pattern. Nhưng consumer có thể tiếp tục đưa item vào **một hàng đợi xử lý thứ hai**, hoặc chỉ đọc rồi chưa xử lý. Khi đó producer được giải phóng dù backend vẫn nghẽn.

Vì vậy **transfer backpressure là ở ranh giới receipt**, không phải tự động ở ranh giới DB commit/business completion. Nếu cần giảm tải theo end-to-end processing, giữ quota tới khi **processing acknowledged** như ví dụ semaphore hoặc reply promise.

## 12. Sự khác biệt quan trọng: received không phải processed

Để chứng minh bằng chương trình, ta dùng một consumer có chủ ý:

1. Nhận message qua `take()`.
2. Báo đã nhận bằng `CountDownLatch`.
3. Chờ main cho phép xử lý bằng một latch thứ hai.
4. Sau đó mới hoàn thành `CompletableFuture<String>` đại diện **business acknowledgment**.

Producer dùng `transfer`. Main có thể thấy producer hoàn tất **trong khi consumer vẫn chưa được phép xử lý**.

### 12.1. Ví dụ runnable: transfer xong trước business ack

Tạo `TransferQueueReceiptVsAckDemo.java`:

```java
import java.util.concurrent.*;
public class TransferQueueReceiptVsAckDemo {
  public static void main(String[] args) throws Exception {
    LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();
    CountDownLatch received = new CountDownLatch(1);
    CountDownLatch allowProcessing = new CountDownLatch(1);
    CompletableFuture<String> processed = new CompletableFuture<>();
    ExecutorService executor = Executors.newFixedThreadPool(2);
    try {
      Future<?> consumer = executor.submit(() -> {
        String message = queue.take();
        received.countDown();
        allowProcessing.await();
        processed.complete(message + "-processed");
        return null;
      });
      Future<?> producer = executor.submit(() -> {
        queue.transfer("request");
        return null;
      });
      if (!received.await(5, TimeUnit.SECONDS)) throw new IllegalStateException("not received");
      producer.get(5, TimeUnit.SECONDS);
      System.out.println("transfer-finished=true");
      System.out.println("processed-before-release=" + processed.isDone());
      allowProcessing.countDown();
      consumer.get(5, TimeUnit.SECONDS);
      System.out.println("processed-result=" + processed.get(5, TimeUnit.SECONDS));
    } finally {
      allowProcessing.countDown();
      executor.shutdownNow();
      executor.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all TransferQueueReceiptVsAckDemo.java
java TransferQueueReceiptVsAckDemo
```

**stdout đã kiểm thử:**

```text
transfer-finished=true
processed-before-release=false
processed-result=request-processed
```

**Diễn giải từng dấu mốc:**

- Consumer thực hiện `take()`, nên producer `transfer("request")` có thể trở về.
- Consumer chưa xử lý message vì đang chờ `allowProcessing`.
- Main **đã xác nhận `producer.get` thành công** nhưng `processed.isDone()==false`.
- Chỉ khi main mở latch, consumer mới hoàn tất `processed` với `request-processed`.
- Đây là bằng chứng thực hành rằng **queue receipt** và **business completion acknowledgment** là hai sự kiện độc lập.

### 12.2. Cần ack chính xác thì thiết kế sao?

Một mô hình phổ biến trong cùng JVM:

```text
record Request(id, payload, CompletableFuture<Result> reply)

Producer:
    create CompletableFuture<Result>
    transfer(request) hoặc offer(request)
    await reply outside queue protocol, with timeout/cancellation policy

Consumer:
    take(request)
    try process
        reply.complete(result) on success
    catch failure
        reply.completeExceptionally(failure)
```

Đây là **pseudocode kiến trúc**, không phải chương trình Java biên dịch độc lập; nó cho thấy ranh giới handoff và ranh giới business completion.

**Phải có giới hạn in-flight, timeout và error handling:** nếu consumer chết sau take nhưng trước complete, promise có thể pending vô hạn. Một queue trong RAM không có automatic retries/ack persistence; với reliability xuyên JVM/process, cần durable broker hoặc giao thức transaction phù hợp.

## 13. Shutdown nhiều consumers bằng poison pill

`LinkedTransferQueue` không có `close()` trên interface để làm tất cả `take()` tự ném end-of-stream. Một pattern đơn giản cho nhóm workers cố định là **poison pill** — một message đặc biệt báo consumer dừng.

Nếu có **N consumers**, thông thường phải gửi **N poison pills**, vì một consumer lấy một message rồi rời loop; không có broadcast tự động.

### 13.1. Ví dụ runnable: hai consumers nhận bốn jobs và dừng

Tạo `TransferQueuePoisonPillDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
public class TransferQueuePoisonPillDemo {
  record Job(int number, boolean stop) {}
  public static void main(String[] args) throws Exception {
    LinkedTransferQueue<Job> queue = new LinkedTransferQueue<>();
    for (int n = 1; n <= 4; n++) queue.offer(new Job(n, false));
    queue.offer(new Job(0, true));
    queue.offer(new Job(0, true));
    AtomicInteger total = new AtomicInteger();
    AtomicInteger stopped = new AtomicInteger();
    ExecutorService executor = Executors.newFixedThreadPool(2);
    try {
      Future<?>[] consumers = new Future<?>[2];
      for (int worker = 0; worker < consumers.length; worker++) {
        consumers[worker] = executor.submit(() -> {
          while (true) {
            Job job = queue.take();
            if (job.stop()) { stopped.incrementAndGet(); return null; }
            total.addAndGet(job.number());
          }
        });
      }
      for (Future<?> consumer : consumers) consumer.get(5, TimeUnit.SECONDS);
      System.out.println("processed-total=" + total.get());
      System.out.println("stopped-consumers=" + stopped.get());
      System.out.println("remaining=" + queue.size());
    } finally {
      executor.shutdownNow();
      executor.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all TransferQueuePoisonPillDemo.java
java TransferQueuePoisonPillDemo
```

**stdout đã kiểm thử:**

```text
processed-total=10
stopped-consumers=2
remaining=0
```

Bốn messages có numbers 1,2,3,4 nên tổng được xử lý bằng `AtomicInteger` là 10. Hai poison pills ở sau messages cùng producer đảm bảo hai consumer eventually nhận tín hiệu dừng sau khi các items trước chúng được lấy. Thứ tự worker nào xử lý job nào **không được dự đoán** và không cần dự đoán để tính tổng.

**Những giới hạn cần lưu ý:**

- Poison pill cần **giao thức ownership**: sau khi phát tín hiệu dừng, không producer khác tiếp tục enqueue business jobs một cách vô kiểm soát.
- Với nhiều producers đồng thời, phải chặn submissions mới và drain/điều phối trước khi phát poison pills; nếu producer enqueue jobs *sau* poison, các jobs đó có thể bị bỏ lại.
- Nếu consumer fail bất ngờ, số workers còn sống không bằng số poison, và coordinator phải xử lý failure/shutdown.
- Poison pill bằng record có `boolean stop` là **ví dụ**, hệ thống thực nên có sealed message types hoặc protocol states rõ để không nhầm job hợp lệ với control message.
- Nếu yêu cầu tránh mất jobs khi JVM crash, queue trong RAM không đủ; dùng persistent storage/broker.

## 14. drainTo, peek, poll và xử lý theo batch

Vì `LinkedTransferQueue` là `BlockingQueue`, bạn có thể dùng:

- `take()`: đợi phần tử, lấy và xóa.
- `poll()`: lấy và xóa nếu có, trả `null` khi rỗng.
- `poll(timeout, unit)`: đợi tối đa thời hạn để lấy item.
- `peek()`: nhìn phần tử đầu **không xóa**, hoặc null nếu rỗng.
- `drainTo(collection,maxElements)`: lấy tối đa số phần tử **đang có** sang collection.
- `drainTo(collection)`: chuyển những phần tử đang có sang collection.

**Không coi các bulk operations là atomic snapshot** dưới concurrent producers/consumers. JavaDoc lưu ý một số bulk operations của `LinkedTransferQueue` không bảo đảm atomic khi các threads khác đang cập nhật.

### 14.1. Ví dụ runnable: lấy hai phần tử đầu theo batch

Tạo `TransferQueueDrainDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
public class TransferQueueDrainDemo {
  public static void main(String[] args) throws Exception {
    LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();
    queue.offer("a");
    queue.offer("b");
    queue.offer("c");
    List<String> batch = new ArrayList<>();
    System.out.println("removed=" + queue.drainTo(batch, 2));
    System.out.println("batch=" + batch);
    System.out.println("peek=" + queue.peek());
    System.out.println("last=" + queue.take());
    System.out.println("empty=" + queue.isEmpty());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all TransferQueueDrainDemo.java
java TransferQueueDrainDemo
```

**stdout đã kiểm thử:**

```text
removed=2
batch=[a, b]
peek=c
last=c
empty=true
```

Không có producer/consumer đồng thời trong ví dụ này; do đó batch có đúng `a,b` và phần tử cuối là `c`. Trong hệ thống thực, nếu workers đồng thời lấy messages, `drainTo` sẽ lấy **tối đa** maxElements trong một trạng thái đang thay đổi; không dùng nó làm transaction “lấy chính xác N messages và khóa queue lại”.

### 14.2. drainTo và transfer đang chờ

Một producer đang chờ `transfer` có thể được giải phóng khi phần tử của nó được **nhận bởi một consumer operation**. Các thao tác lấy phần tử khỏi queue có semantics nhận, nhưng đừng biến `drainTo` thành giả định rằng toàn bộ batch đã được **xử lý nghiệp vụ**. Kết quả chỉ là những items đã được chuyển sang collection đích.

Nếu batch xử lý thất bại sau drain, các items đã rời queue. Muốn retry bền vững, ứng dụng phải có retry/dead-letter/durable persistence policy.

## 15. Ordering, fairness và nhiều producers

JavaDoc `LinkedTransferQueue` định nghĩa FIFO **đối với từng producer**. Nếu producer P1 gửi A rồi B, thứ tự nhận của các phần tử riêng của P1 phản ánh thứ tự enqueue của nó. Nhưng khi nhiều producers chạy đồng thời, lịch thực thi quyết định chúng xen kẽ ra sao.

```text
Producer P1: A1 ---- A2 ---- A3
Producer P2: ---- B1 ---- B2

Possible consumer sequence:
  A1, B1, A2, A3, B2

Không được khẳng định thứ tự toàn hệ thống luôn là:
  A1, A2, A3, B1, B2
```

**Handoff không bảo đảm fairness theo tenant/request**. `LinkedTransferQueue` không cung cấp một cấu hình fairness như một số concurrent queues khác. Nếu business yêu cầu priority hoặc strict global order, cần một thiết kế khác: per-key partitions, sequence IDs, single sequencer, priority queue hoặc ordered aggregator.

**Không suy từ một chạy thử đúng thứ tự rằng mọi lần chạy sẽ như vậy.** Thread scheduler, CPU contention và producer rates có thể thay đổi.

### 15.1. Mutable objects và cùng reference

Queue trao **reference** tới object, không tự tạo bản copy. Nếu bạn `offer(mutableJob)` rồi sửa các fields không đồng bộ, consumer có thể nhìn dữ liệu thay đổi không được kiểm soát. Chọn immutable messages/defensive copy, hoặc có ownership protocol cụ thể.

### 15.2. Iterators weakly consistent

Iterator/Spliterator của `LinkedTransferQueue` là **weakly consistent**: nó có thể quan sát một phần updates concurrent thay vì một snapshot cố định và không có quy tắc fail-fast giống `ArrayList` iterator.

Do đó:

- Không dùng `iterator()` để xác nhận tất cả jobs đã được nhận.
- Không dùng `stream()` trên queue đang thay đổi để tính con số kế toán mang tính quyết định.
- Không dùng `size()` làm cơ chế đồng bộ, vì chi phí O(n) và kết quả có thể thay đổi.
- Muốn thống kê số jobs accepted/processed, dùng counters riêng được cập nhật đúng tại lifecycle transitions và có idempotency rules.

## 16. Khi nào chọn TransferQueue, SynchronousQueue hay BlockingQueue khác?

| Cấu trúc | Capacity / behavior | Có handoff semantics tương đương? | Tình huống phù hợp |
| --- | --- | --- | --- |
| `LinkedTransferQueue<E>` | **Unbounded** linked nodes | `transfer`/`tryTransfer` có thể chờ người nhận; `offer`/`put` vẫn enqueue | Một producer đôi lúc cần confirmation “consumer đã nhận”, đôi lúc chỉ cần enqueue |
| `SynchronousQueue<E>` | **Zero capacity**; mỗi put cần consumer tương ứng | `put`/`take` tạo rendezvous, không lưu backlog | Cần handoff trực tiếp, không lưu messages chờ |
| `ArrayBlockingQueue<E>` | Bounded fixed-size array | `put` có thể chờ slot, **không chờ receipt** | Muốn memory/backpressure đơn giản theo capacity |
| `LinkedBlockingQueue<E>` | Có thể bounded với constructor capacity | `put` chờ slot nếu đầy, không chờ receipt | Producer–consumer thông thường, có quota theo phần tử |
| `ConcurrentLinkedQueue<E>` | Unbounded nonblocking queue | **Không** cung cấp blocking `take` hoặc `transfer` | Producer/consumer cần tự tổ chức waiting/scheduling |
| `PriorityBlockingQueue<E>` | Unbounded priority-order | Không có `transfer` semantics | Cần lấy theo priority thay vì FIFO |
| `DelayQueue<E>` | Unbounded, phần tử chỉ khả dụng khi delay hết | Không có `transfer` semantics | Scheduled delayed items theo delay |
 
### 16.1. Chọn đúng theo câu hỏi nghiệp vụ

**Cần đẩy task vào hàng đợi có khả năng từ chối khi đầy?** Chọn bounded `ArrayBlockingQueue`/`LinkedBlockingQueue(capacity)` hoặc admission controller.

**Cần một producer biết consumer đã lấy item?** `LinkedTransferQueue.transfer` hoặc timed `tryTransfer` có ý nghĩa.

**Cần producer biết consumer đã xử lý và lưu DB thành công?** Không có queue primitive nào tự đủ; dùng completion promise/ack hoặc durable broker với ack semantics rõ.

**Cần giao trực tiếp không lưu backlog?** `SynchronousQueue` phù hợp nếu mỗi producer và consumer phải rendezvous, nhưng vẫn không xác nhận business processing.

**Cần priority/order khác FIFO?** Dùng queue/protocol phù hợp thay vì tin `LinkedTransferQueue` sẽ tự ưu tiên.

### 16.2. SynchronousQueue không phải subclass của TransferQueue

JavaDoc `TransferQueue` dùng `SynchronousQueue` **làm ví dụ so sánh** zero-capacity queue, nhưng `SynchronousQueue` là một `BlockingQueue` khác, **không phải implementation của interface `TransferQueue`**. Không cast `SynchronousQueue` sang `TransferQueue`.

## 17. Xử lý lỗi, timeout và lifecycle của consumer

Một pipeline trên JVM có ít nhất bốn trạng thái liên quan:

```text
CREATED → QUEUED → RECEIVED → PROCESSING → SUCCEEDED
                        |            |
                        |            +→ FAILED / RETRY / DEAD_LETTER
                        +→ PROCESSOR_CRASH_BEFORE_ACK
```

Các methods queue chỉ mô tả một phần trạng thái này. Ví dụ `offer` đưa vào QUEUED, `transfer` trả khi RECEIVED, nhưng **PROCESSING/SUCCEEDED** do code consumer quyết định.

### 17.1. Các đường lỗi cần xử lý

| Lỗi | Hậu quả | Phản ứng phù hợp |
| --- | --- | --- |
| `tryTransfer` trả `false` | Message chưa được giao/không enqueue | Báo no consumer, fallback có quota hoặc retry theo policy |
| Timed `tryTransfer` hết hạn | Chưa handoff, message không còn trong queue | Trả timeout, đừng đánh dấu delivered |
| `transfer` bị interrupt khi chờ | Handoff bị hủy, không để element enqueued | Restore interrupt/propagate cancellation |
| `offer` thành công nhưng consumer crash trước take | Message có thể vẫn nằm queue trong JVM, nhưng không có người xử lý | Supervisor, restart consumer hoặc drain/stop |
| Consumer crash **sau take** | Message đã rời queue, có nguy cơ mất job | Ack/retry/durable design |
| Consumer xử lý xong nhưng ack bị mất | Producer có thể retry và gây duplicate side effects | Idempotency + request ID |
| Queue backlog tăng không giới hạn | Heap/GC pressure và latency | Bounded admission/quota/rate limiting |
| Producer bị block mãi trong `transfer` | Thread leak/starvation/deadlock | Timed tryTransfer, cancellation, executor capacity |
| Worker chờ `take` khi service shutdown | Thread không thoát tự nhiên | Interrupt hoặc poison pill theo ownership |
| Poison pill gửi trước khi dừng producers | Jobs mới xếp sau poison và bị bỏ | Stop submissions rồi drain/coordinate shutdown |
| Queue bị dùng như durable storage | Mất state khi JVM crash | Persistent store/broker nếu cần durability |

### 17.2. Không retry mù quáng

Một request có thể được consumer **nhận** nhưng xử lý lỗi ở bước sau; việc producer thử gửi lại có thể tạo duplicate. Nếu business cần “exactly once”, phải phân biệt at-most-once/at-least-once processing, idempotency keys, transaction boundaries và semantics của hệ thống lưu trữ.

**`TransferQueue` không tự cung cấp exactly-once**. Nó là primitive đồng bộ trong bộ nhớ tiến trình Java.

### 17.3. Consumer errors nên hoàn tất promise

Nếu message chứa `CompletableFuture<Result> reply`, consumer cần hoàn tất promise trên cả hai nhánh:

```java
try {
    Result result = process(job);
    reply.complete(result);
} catch (Exception failure) {
    reply.completeExceptionally(failure);
}
```

Đây là snippet minh họa, `Result`/`process`/`job`/`reply` là thành phần ứng dụng. Nếu chỉ log lỗi và không `completeExceptionally`, producer có thể chờ mãi. Không bắt `Throwable` rồi coi mọi JVM `Error` là lỗi nghiệp vụ bình thường.

## 18. Kiến trúc producer–consumer hiện đại có giới hạn

Một thiết kế production căn bản:

```text
Client/API request
      |
      v
Validate payload + authentication
      |
      v
Admission control (max in-flight, max payload bytes)
      |
      +--> reject with backpressure response if full
      |
      v
TransferQueue<Job> / bounded queue
      |
      v
Consumer worker pool (known capacity)
      |
      v
Business validation and processing
      |
      +--> complete reply Future on success/failure
      +--> release in-flight permit exactly once
      |
      v
Producer sees processing result/timeout through reply Future

Shutdown supervisor:
  stop producers -> stop admitting jobs -> drain/fail pending jobs
  -> signal consumers (poison/interrupt) -> await termination with deadline
```

### 18.1. Những policy nên được định nghĩa rõ

- **Admission:** nếu không còn permit, producer chờ có thời hạn hay trả BUSY?
- **Delivery:** yêu cầu handoff (`transfer`), best-effort (`tryTransfer`), hay enqueue (`offer`)?
- **Processing:** processor có retry không, retry bao lần, giới hạn thời gian?
- **Acknowledgment:** nhận queue hay business completion mới được coi là thành công?
- **Ordering:** FIFO per producer, per-key order hay không quan trọng?
- **Ownership:** ai tạo/đóng executor, ai phát poison pills, ai release permit?
- **Memory:** max số messages/bytes giữ trong JVM?
- **Failure:** consumer crash sau take có phục hồi job không, storage ở đâu?
- **Observability:** accepted/received/completed/failed counts có được phân biệt?
- **Shutdown:** có chấp nhận bỏ pending best-effort messages không?

### 18.2. Bảo mật

Queue không tự làm input validation. Một producer chưa được xác thực có thể gửi payload rất lớn hoặc flood `offer`; unbounded queue có nguy cơ DoS memory. Dùng authentication, per-client quotas, validation và giới hạn serialized payload.

Không log API tokens, credentials hoặc message bodies nhạy cảm khi debugging backlog. Đảm bảo consumer không execute untrusted code trực tiếp chỉ vì message đến từ một concurrent collection.

## 19. Hiệu năng và giám sát đúng cách

`LinkedTransferQueue` có thể hiệu quả trong concurrent producer–consumer workloads, nhưng kết quả phụ thuộc:

- Tỷ lệ producer/consumer và số cores.
- Sự cân bằng giữa enqueue và handoff trực tiếp.
- Kích thước payload/object allocations.
- Tần suất `transfer` blocking so với `offer`/`tryTransfer`.
- Số threads, context switches và scheduler.
- CPU cache contention, memory allocation và GC.
- Tài nguyên đích như database pool/network endpoints.
- Logging, instrumentation và processing cost mỗi item.

**Không hứa `LinkedTransferQueue` luôn nhanh hơn `ArrayBlockingQueue` hoặc `SynchronousQueue`.** Mỗi cấu trúc có trade-offs khác nhau; benchmark phải so cùng semantics/capacity/backpressure.

### 19.1. Những metrics hữu ích

| Metric | Cách diễn giải |
| --- | --- |
| Accepted count | Số jobs đã được queue/admission chấp nhận |
| Transfer success/failure/timeout count | Handoff thực sự có consumer nhận hay không |
| Processing success/failure count | Kết quả nghiệp vụ, **khác receipt** |
| In-flight permits used | Áp lực trên quota thực |
| Queue age (P50/P95/P99) | Thời gian job chưa được consumer lấy |
| Processing latency (P50/P95/P99) | Thời gian consumer làm việc |
| Active producer threads waiting | Có nhiều transfer đang blocked không? |
| Waiting consumers estimate | Có consumers chờ việc hay không; **chỉ heuristic** |
| Consumer throughput | Năng lực xử lý thực |
| Executor queued tasks/rejections | Worker pool có bị nghẽn không? |
| Heap usage/GC pauses | Queue unbounded có giữ quá nhiều data không? |
| Dead-letter/retry volume | Chất lượng và độ tin cậy xử lý |

**Không lấy `size()` mỗi millisecond để làm metric chính:** JavaDoc ghi nhận size không constant-time và có thể không chính xác dưới concurrent modifications. Nếu cần một gauge nhẹ, duy trì count độc lập khi lifecycle transitions có tính nhất quán, và hiểu gauge vẫn có giới hạn của quan sát đồng thời.

### 19.2. Kiểm thử và benchmark

Để đo throughput:

1. Tạo workloads đại diện cho production (payload sizes, producers/consumers, processing cost).
2. Warm up JVM/JIT, chạy nhiều iterations và dùng JMH nếu cần microbenchmark.
3. Đo CPU, memory/allocations, GC, queue age và percentiles, không chỉ operations/second.
4. So `offer`, `transfer`, `tryTransfer` **trong cùng điều kiện semantics**, vì transfer có blocking khác với enqueue.
5. Dùng executor với đủ capacity, tránh deadlock nhân tạo.
6. Đặt deadline cho mọi integration test có thể chờ.
7. Không dựa vào `Thread.sleep(10)` để khẳng định consumer đang chờ.
8. Để kiểm tra hành vi nhận, dùng latch/futures hoặc state synchronization phù hợp trong harness.
9. Không khẳng định ordering của nhiều producers nếu test không áp đặt thứ tự.
10. Test shutdown khi có producer `transfer` đang block và consumer `take` đang block.
11. Test hệ thống đầy quota nhưng queue internal chưa đầy.
12. Test consumer failure sau `take` trước business ack.
13. Test cancellation và không rò permits sau failure.

### 19.3. Why hasWaitingConsumer is not a “free capacity” signal

`hasWaitingConsumer` nói rằng có consumer đang chờ **ở thời điểm chụp trạng thái**. Nó không cho biết consumer có đủ CPU/DB capacity để xử lý công việc phức tạp, cũng không đảm bảo consumer vẫn chờ lúc bạn giao việc. Consumer có thể `take` xong rồi bị block ở một tài nguyên khác.

Bởi vậy không dùng `hasWaitingConsumer` để quyết định có được nhận request/chiếm RAM vượt quota hay không.

## 20. Những lỗi phổ biến và cách sửa

| Anti-pattern | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Gọi `queue.put(e)` rồi nghĩ consumer đã nhận | Với LinkedTransferQueue, put chỉ enqueue | Dùng `transfer` nếu cần receipt, hoặc ack riêng |
| Gọi `queue.transfer(e)` rồi nghĩ DB đã commit | Transfer chỉ đợi take/poll | Completion promise sau business success |
| Bỏ qua `tryTransfer(e)` trả false | Item không enqueue và bị mất | Xử lý false/fallback rõ |
| Nghĩ timed `tryTransfer` false vẫn giữ message | Contract không để lại item | Đừng mark delivered; retry đúng policy |
| Nghĩ `offer(e,timeout)` đợi consumer | Unbounded LinkedTransferQueue chỉ enqueue | Dùng timed `tryTransfer` |
| Nghĩ remainingCapacity phản ánh RAM | Luôn `Integer.MAX_VALUE` | Dùng quotas/monitor heap |
| Dùng `size()<N` rồi enqueue làm bounded policy | Không atomic, size O(n)/racy | Bounded queue/semaphore |
| Tạo single-thread executor cho producer transfer rồi consumer take | Producer giữ thread, consumer không chạy | Bố trí execution capacity hoặc dùng nonblocking pattern |
| Block hàng nghìn producers trong `transfer` | Thread starvation/RAM | Timed handoff, admission limits |
| Dùng snapshot `hasWaitingConsumer` để đảm bảo transfer không block | Check-then-act race | Tin vào result của `tryTransfer` |
| Dùng `getWaitingConsumerCount` làm barrier | Approximation, không đồng bộ | Latch/barrier/explicit coordination |
| Gửi `null` làm poison pill | Queue không cho null | Control message kiểu-safe |
| Dùng 1 poison pill cho N consumers | Một consumer dừng, còn N-1 vẫn chờ | N pills/explicit interrupt/termination |
| Gửi poison khi producers còn enqueue | Jobs có thể xuất hiện sau stop signals | Stop admission trước shutdown |
| Producer sửa object sau enqueue không đồng bộ | Data race | Immutable payload/ownership |
| Nhiều producers cần strict global order | FIFO per producer không xác định interleaving | Sequence IDs/ordered coordinator |
| Duyệt iterator làm snapshot kế toán | Weakly consistent | Snapshot/metrics ở tầng khác |
| Dùng transfer để “bảo đảm exactly once” | Không có business ack/durable state | Idempotency, transactions, broker nếu cần |
| Consumer lỗi sau take mà không báo producer | Job rời queue, reply pending | Ack error và retry/dead-letter policy |
| `shutdownNow` rồi quên workers chờ transfer | Có thể còn tasks chưa thoát/cleanup | Deadline, cancellation, awaitTermination |
| Không restore interrupt khi đã catch | Làm mất cancellation signal | Propagate hoặc restore interrupt |
| Dùng queue unbounded cho public API flood | DoS memory | Auth/quota/backpressure |
| Benchmark offer so transfer rồi kết luận implementation nhanh/chậm | Hai operations có blocking semantics khác | So workload tương đồng |
| Cho rằng queue là persistent | JVM crash mất dữ liệu | Durable storage khi yêu cầu |

## 21. Checklist code review

1. Nhu cầu thực sự là **enqueue**, **consumer receipt** hay **business processing acknowledgment**?
2. Có đang dùng `TransferQueue` interface và `LinkedTransferQueue` implementation đúng chỗ không?
3. Có phân biệt `offer`/`put` với `transfer`/`tryTransfer` không?
4. Có kiểm tra boolean của `tryTransfer` thay vì bỏ qua không?
5. Với `tryTransfer(timeout)`, có xử lý false và không đánh dấu delivered không?
6. Khi `transfer` bị interrupt, có xử lý đúng và không retry mù quáng không?
7. Có hiểu `LinkedTransferQueue` **unbounded** và `remainingCapacity==Integer.MAX_VALUE` không?
8. Có admission limit theo số jobs/bytes hoặc lựa chọn bounded queue phù hợp không?
9. Có tránh dùng `size()` làm quota vì O(n) và race không?
10. Có tránh dùng `hasWaitingConsumer()`/`getWaitingConsumerCount()` làm synchronization control không?
11. Có đảm bảo executor có threads/capacity cho cả producer đang chờ và consumer sẽ lấy không?
12. Có tránh chờ transfer trong callback/event loop cần để consumer tiến không?
13. Có dùng immutable messages hoặc ownership protocol cho objects sau enqueue không?
14. Có phân biệt queue delivery và processing completion qua reply/ack không?
15. Có record request IDs/idempotency khi retry có thể làm duplicate không?
16. Có xử lý consumer fail **sau take** trước ack không?
17. Có xử lý producer fail sau khi đã enqueue mà không tạo double-submission không?
18. Có bao giờ sử dụng null làm message hoặc sentinel không? Nếu có, phải sửa.
19. Có xác định ordering per producer so với global ordering requirement không?
20. Có tránh mutate collection khi iterator/stream đang chạy và phụ thuộc snapshot không?
21. Có xử lý memory consistency và không sửa mutable object sau publish không?
22. Có giới hạn kích thước payload để tránh DoS RAM không?
23. Khi shutdown, có ngừng submissions trước khi gửi poison pills không?
24. Có đủ stop signals cho số consumers đang chạy không?
25. Có policy cho worker futures bị cancel/interrupted/hết deadline không?
26. Có release semaphore permit **chính xác một lần** theo terminal lifecycle không?
27. Có phân biệt transfer timeout với processing timeout không?
28. Có metrics separate accepted/received/processed/failed và queue age không?
29. Có không dùng `drainTo` làm transaction atomic snapshot dưới concurrency không?
30. Có test không consumer, consumer đến sau, consumer đến trước, interrupted và shutdown không?
31. Có test single-thread starvation và xử lý lỗi không treo CI không?
32. Có biết các APIs này vẫn áp dụng trong Java 17+ và không phải legacy không?

## 22. Bài tập thực hành

**Bài 1 — Enqueue và receipt.** Chạy `TransferQueueOfferPutDemo` và `TransferQueueHandoffDemo`. Vẽ thời điểm method trả về với `offer`, `put` và `transfer`. Vì sao chỉ phương thức cuối chứng minh consumer đã nhận?

**Bài 2 — Một producer, nhiều messages.** Gửi `A, B, C, D` từ cùng một producer qua `offer`, rồi dùng một consumer `take`. Xác minh FIFO và đối chiếu với các producers concurrent.

**Bài 3 — Không có consumer.** Chạy `TransferQueueTryTransferNoConsumerDemo`. Thử timeout 0, 50 và 100 ms; giải thích vì sao queue vẫn rỗng.

**Bài 4 — Waiting consumer.** Chạy `TransferQueueTryTransferWaitingDemo`. Thay waiting `take` bằng `poll(timeout)`; dùng deadline trong harness và không dùng snapshot count làm business synchronization.

**Bài 5 — Timed handoff.** Chạy `TransferQueueTimedTransferSuccessDemo`; làm consumer đến sau timeout trong một test khác và kiểm tra item không bị giữ lại. Không để test tự treo.

**Bài 6 — Interruption.** Chạy `TransferQueueInterruptDemo`. Vì sao `InterruptedException` không đồng nghĩa business processing đã thất bại ở một workflow khác? Nêu chính sách retry an toàn.

**Bài 7 — Memory publication.** Chạy `TransferQueueVisibilityDemo`. Thay payload bằng một record immutable chứa các field số nguyên. Giải thích happens-before qua queue.

**Bài 8 — Mutable payload.** Cố tình cho producer sửa một `int[]` sau enqueue (test sandbox) để nhận diện data race. Sửa bằng copy-on-handoff hoặc immutable data.

**Bài 9 — Backpressure.** Chạy `TransferQueueBoundedIngressDemo` với 3 permits và 8 items; kiểm tra queue không vượt quota khi chưa có consumer xử lý.

**Bài 10 — Ack sau processing.** Chạy `TransferQueueReceiptVsAckDemo`. Thêm case consumer thất bại sau take và complete promise exceptionally; producer phải nhìn thấy lỗi này thay vì tin transfer đã thành công là job success.

**Bài 11 — Poison pills.** Chạy `TransferQueuePoisonPillDemo` với 3 consumers. Gửi ba stop messages, đảm bảo không có producer khác enqueue sau stop.

**Bài 12 — Controlled shutdown.** Trong test, để một consumer block ở `take` rồi gọi `shutdownNow()`; đợi Future/awaitTermination trong deadline. So sánh với worker nhận poison.

**Bài 13 — Drain.** Chạy `TransferQueueDrainDemo` với 5 messages và `drainTo(batch,3)`. Giải thích vì sao batch lấy ra không tự được xử lý xong.

**Bài 14 — LinkedTransferQueue.size.** Quan sát `size` khi không có concorrency để minh họa; dưới concurrent load, vì sao giá trị có thể racy và chi phí O(n)?

**Bài 15 — WaitingConsumerCount.** Quan sát `getWaitingConsumerCount()` với 2 consumers đang chờ. Vì sao không được dùng số này để quyết định exactly-once assignment?

**Bài 16 — SynchronousQueue.** Viết cùng ví dụ với `SynchronousQueue` và `put`. Khác biệt nào do zero capacity, và tại sao không thể cast nó sang `TransferQueue`?

**Bài 17 — Bounded queue.** Thay `LinkedTransferQueue` bằng `ArrayBlockingQueue<>(2)` và `put`. So sánh điều kiện producer block: hết chỗ trống, không phải chờ consumer nhận một job cụ thể.

**Bài 18 — Ordering.** Tạo hai producers gửi messages có sequence IDs; consumers thu đủ messages rồi sort theo producer ID/sequence. Nêu sự khác nhau giữa FIFO per producer và global business ordering.

**Bài 19 — Resource limits.** Thiết kế một public API nhận messages có max payload bytes, per-client quota, active jobs limit và processing deadlines; mô tả khi nào trả BUSY.

**Bài 20 — Production review.** Xây service producer–consumer với `LinkedTransferQueue<Job>`, workers cố định, ack futures, max in-flight semaphore, graceful shutdown, idempotency keys và metrics; chỉ xác nhận business success sau processing.

## 23. Kết luận

- `TransferQueue<E>` mở rộng `BlockingQueue<E>`, cho producer lựa chọn **enqueue** hoặc **đợi consumer nhận**; `LinkedTransferQueue<E>` là implementation unbounded còn hợp lệ trong Java 17+.
- `offer`/`put` **không chờ consumer nhận** với LinkedTransferQueue; `transfer` **đợi receipt**; `tryTransfer(e)` chỉ thành công nếu có waiting consumer; timed `tryTransfer` cho deadline.
- `tryTransfer` trả `false` thì **phần tử không được enqueue**. Bỏ qua boolean có thể làm mất dữ liệu.
- `transfer` hoàn tất khi consumer **take/poll**, **không có nghĩa business processing thành công**. Muốn processing acknowledgment, phải có reply/completion protocol riêng.
- LinkedTransferQueue **không giới hạn capacity**, nhưng heap hữu hạn. Cần bounded admission/backpressure và tránh dùng `size()` làm quota.
- `hasWaitingConsumer`/`getWaitingConsumerCount` chỉ là snapshot/estimate; **không** dùng làm check-then-act synchronization.
- Queue cung cấp happens-before khi publish item tới consumer, nhưng **không khiến payload mutable tự thread-safe**.
- Cần đủ execution capacity để blocked transfer và consumer tiến; đồng thời thiết kế interrupt, timeout và shutdown để không giữ threads vô hạn.
- Poison pills có thể giúp dừng N consumers khi phát N stop signals đúng thời điểm; queue không có close/transaction/durable persistence tự động.
- Chọn queue theo nhu cầu: `SynchronousQueue` cho rendezvous zero-capacity, bounded BlockingQueue cho capacity backpressure, `LinkedTransferQueue` khi cần kết hợp enqueue và handoff.
- Các phương thức và nguyên tắc trong bài dựa trên Java SE hiện hành, không sử dụng kiến thức lỗi thời hoặc legacy.

## Tài liệu chính thức

- [TransferQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TransferQueue.html): `transfer`, `tryTransfer`, timed transfer, waiting consumer counts và behavior khi timeout/interruption.
- [LinkedTransferQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedTransferQueue.html): unbounded queue, FIFO per producer, `size` O(n), memory consistency, `put`/`offer`.
- [TransferQueue — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TransferQueue.html): phiên bản nền tương thích Java 17.
- [LinkedTransferQueue — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedTransferQueue.html): contract của implementation trên JDK 17.
- [BlockingQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html): put/take, memory effects, capacity và drainTo.
- [SynchronousQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): rendezvous zero capacity.
- [ArrayBlockingQueue — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded queue với backpressure khi đầy.
- [Semaphore — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html): kiểm soát số jobs in-flight.
- [ExecutorService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, shutdown, cancel, termination.
- [CompletableFuture — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): business processing acknowledgment thành công/thất bại.
