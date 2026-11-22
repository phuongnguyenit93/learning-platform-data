# Concurrent queue, blocking queue và backpressure trong Java

## 1. Tại sao hàng đợi thread-safe chưa đủ?

Trong một hệ thống có **producer** tạo công việc và **consumer** xử lý công việc, hàng đợi (queue) giúp tách hai tốc độ thực thi. Producer có thể thêm tác vụ mà không cần đợi consumer xử lý xong từng tác vụ; consumer lấy các mục trong queue để làm việc.

~~~text
    Producer A ----\
                    \         +-----------------+        +-------------+
    Producer B ------> ------>| Shared Queue    |------->| Consumer(s) |
                    /         +-----------------+        +-------------+
    Producer C ----/
~~~

Vấn đề có ba lớp khác nhau:

1. **Thread safety:** các thao tác thêm/lấy từ nhiều thread không phá hỏng cấu trúc hàng đợi, không làm mất phần tử chỉ vì race nội bộ.
2. **Blocking / signaling:** producer có thể đợi khi queue đầy; consumer có thể đợi khi queue trống, thay vì tự spin liên tục.
3. **Backpressure:** hệ thống có cơ chế **giới hạn, làm chậm hoặc từ chối** công việc đầu vào khi downstream không theo kịp, nhằm không tiêu thụ tài nguyên vô hạn.

**Concurrent queue** giải quyết chủ yếu vấn đề 1. **Blocking queue** cung cấp các primitive cho vấn đề 1 và 2. **Backpressure** là chiến lược kiểm soát tải toàn tuyến dựa trên queue, giới hạn xử lý đồng thời, admission control, timeout và chính sách quá tải; không tự động xuất hiện chỉ vì dùng một collection có chữ “concurrent”.

Bài này nói về Java Concurrency nói chung, sử dụng thư viện chuẩn `java.util.concurrent` mà không gắn với một framework cụ thể.

## 2. Queue, ConcurrentLinkedQueue và BlockingQueue khác gì?

**`Queue<E>`** là interface cơ bản trong Collections Framework. Nó quy định các thao tác thêm, lấy, xem phần tử ở đầu queue nhưng không mặc định bảo đảm thread-safe hoặc hỗ trợ đợi.

**`ConcurrentLinkedQueue<E>`** là hàng đợi FIFO thread-safe, **không giới hạn capacity nội tại**, với các thao tác thêm/lấy không chờ đến khi queue đầy/trống. Thuật toán đồng thời của nó dựa trên các primitive non-blocking. `offer(e)` thêm phần tử và thông thường trả `true`; `poll()` trả `null` nếu lúc đó trống. Không dùng `null` làm phần tử.

**`BlockingQueue<E>`** là interface mở rộng Queue, bổ sung **`put`/`take`** để chờ và các overload **`offer(timeout)`/`poll(timeout)`** để chờ có hạn. BlockingQueue có cả implementation **bounded** và **không có giới hạn dung lượng hữu ích theo cấu hình**. Vì vậy “BlockingQueue” không đồng nghĩa với “hàng đợi luôn có backpressure”.

| Khía cạnh | `ConcurrentLinkedQueue` | `BlockingQueue` với implementation bounded |
|---|---|---|
| Thread-safe cho thao tác queue | Có | Có |
| Khi trống, `poll()` | Trả `null` ngay | Trả `null` ngay |
| Đợi có phần tử bằng `take()` | Không có phương thức này | Có |
| Khi đầy | Không có giới hạn capacity nội tại | `offer()` có thể trả false; `put()` đợi |
| Đợi còn chỗ có timeout | Không có | `offer(e, timeout, unit)` |
| Cơ chế kiểm soát tải | Cần giới hạn ngoài | Có thể tạo backpressure với capacity và chính sách phù hợp |
| Ví dụ thích hợp | Danh sách thông báo nội bộ cần truy xuất non-blocking, lượng vào đã được giới hạn | Producer–consumer với hàng chờ bounded và giao thức overload rõ |

**Không phải mọi Queue giữ FIFO.** `PriorityBlockingQueue` ưu tiên theo ordering của phần tử/comparator, không phải FIFO; `DelayQueue` cho phép lấy phần tử khi hết độ trễ. Cần chọn theo hợp đồng **thứ tự**, **capacity** và **blocking** cụ thể.

## 3. Bốn kiểu xử lý khi BlockingQueue không thể đáp ứng ngay

Tài liệu Java mô tả bốn nhóm thao tác:

| Hành động | Ném ngoại lệ ngay | Giá trị đặc biệt ngay | Chờ không giới hạn thời gian | Chờ có timeout |
|---|---|---|---|---|
| **Thêm** | `add(e)` | `offer(e)` → boolean | `put(e)` | `offer(e, time, unit)` → boolean |
| **Lấy và xóa đầu** | `remove()` | `poll()` → E hoặc `null` | `take()` → E | `poll(time, unit)` → E hoặc `null` |
| **Chỉ xem đầu** | `element()` | `peek()` → E hoặc `null` | Không có | Không có |

### Thao tác thêm

- `add(e)`: nếu queue bị giới hạn và đầy, thông thường ném `IllegalStateException`; phù hợp khi thất bại được coi là điều bất thường.
- `offer(e)`: **không chờ** chỗ trống. Trên queue bounded, trả `false` nếu không thêm được vì đầy. Đừng bỏ qua giá trị trả về: bỏ qua có thể làm **mất công việc âm thầm**.
- `put(e)`: có thể **block vô thời hạn** tới khi có capacity; có thể ném `InterruptedException` nếu caller bị ngắt trong khi đợi.
- `offer(e, timeout, unit)`: chờ tối đa một thời hạn; trả false nếu không có chỗ trong hạn. Đây thường là một primitive tốt khi có SLA/deadline.

### Thao tác lấy

- `poll()`: lấy và xóa đầu ngay nếu có; trả `null` nếu trống.
- `take()`: chờ cho đến khi có phần tử; là thao tác phổ biến của consumer thread.
- `poll(timeout, unit)`: chờ có hạn và trả `null` nếu không có phần tử; phù hợp khi consumer còn cần định kỳ kiểm tra trạng thái stop.
- `peek()`: chỉ xem đầu, không xóa; không dùng cho mô hình “nhận việc để xử lý” vì nhiều consumer có thể thấy cùng một phần tử.

Tất cả các triển khai `BlockingQueue` chuẩn **không chấp nhận null**; `null` là giá trị biểu thị không lấy được từ `poll()`. Không dùng null làm poison pill.

**Timeout không phải hủy downstream:** khi `offer(timeout)` trả false, **phần tử đó chưa được nhận vào queue**, caller phải quyết định trả lỗi, retry có giới hạn hoặc lưu ở nơi khác. Khi `poll(timeout)` trả null, chỉ biết không lấy được trong thời hạn, không có nghĩa hệ thống đã kết thúc.

## 4. Chọn implementation phù hợp

| Implementation | Capacity | Thứ tự/chức năng | Lưu ý thực tế |
|---|---|---|---|
| `ConcurrentLinkedQueue` | Không bounded nội tại | FIFO, thao tác non-blocking | Không tạo admission backpressure; `size()` O(n), không nên polling liên tục |
| `ArrayBlockingQueue(capacity)` | **Bounded bắt buộc** | FIFO, backing array | Dễ đặt ngân sách phần tử; có tùy chọn fairness, có thể giảm throughput |
| `LinkedBlockingQueue(capacity)` | Bounded nếu **truyền capacity** | FIFO, linked nodes | Constructor không capacity mặc định gần như không giới hạn hữu ích (`Integer.MAX_VALUE`) |
| `SynchronousQueue` | **0 phần tử chờ** | Rendezvous trao trực tiếp producer–consumer | `put` cần có consumer nhận; không có buffer; `offer` có thể thất bại khi không có người nhận |
| `PriorityBlockingQueue` | Không bounded nội tại | Priority | Không bảo đảm FIFO; `put` không chờ vì queue đầy theo một capacity cố định |
| `DelayQueue` | Không bounded nội tại | Chỉ lấy phần tử đã hết delay | Phù hợp scheduling; không thay thế bounded work queue |
| `LinkedBlockingDeque(capacity)` | Bounded nếu cấu hình | Thêm/lấy hai đầu | Dùng nếu thực sự cần deque; cân nhắc fairness và starvation của tác vụ |

**Cẩn thận với default:** `new LinkedBlockingQueue<>()` dùng capacity `Integer.MAX_VALUE`. Dù là BlockingQueue, producer thông thường **không bị chặn vì đầy** trước khi áp lực bộ nhớ trở thành vấn đề. Muốn giới hạn thực sự, sử dụng ví dụ `new LinkedBlockingQueue<>(1000)` hoặc `new ArrayBlockingQueue<>(1000)`.

**`remainingCapacity()` không giữ chỗ:** kết quả là một snapshot có thể lỗi thời ngay vì producer khác cùng đang thêm. Tránh kiểu `if (queue.remainingCapacity() > 0) queue.add(task)`. Dùng một lời gọi nguyên tử theo hợp đồng: `offer`, `put` hoặc `offer(timeout)`.

## 5. Ví dụ Java 17: các thao tác non-blocking và bounded

Ví dụ này cố ý chỉ có một thread để đầu ra xác định, minh họa hợp đồng API trước khi đi vào đa luồng.

Lưu **QueueApiDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;

public class QueueApiDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentLinkedQueue<String> concurrent =
                new ConcurrentLinkedQueue<>();
        concurrent.offer("A");
        concurrent.offer("B");

        System.out.println("nonblocking peek=" + concurrent.peek());
        System.out.println("nonblocking poll=" + concurrent.poll());
        System.out.println("nonblocking next=" + concurrent.poll());

        ArrayBlockingQueue<Integer> bounded = new ArrayBlockingQueue<>(2);
        System.out.println("bounded add 1=" + bounded.offer(1));
        System.out.println("bounded add 2=" + bounded.offer(2));
        System.out.println("bounded add 3=" + bounded.offer(3));
        System.out.println("bounded remaining=" + bounded.remainingCapacity());
        System.out.println("bounded take=" + bounded.take());
        System.out.println("bounded offer 3=" + bounded.offer(3));
        System.out.println("bounded poll 2=" + bounded.poll());
        System.out.println("bounded poll 3=" + bounded.poll());
    }
}
~~~

Chạy:

~~~bash
javac QueueApiDemo.java
java QueueApiDemo
~~~

Stdout:

~~~text
nonblocking peek=A
nonblocking poll=A
nonblocking next=B
bounded add 1=true
bounded add 2=true
bounded add 3=false
bounded remaining=0
bounded take=1
bounded offer 3=true
bounded poll 2=2
bounded poll 3=3
~~~

Điểm cần hiểu: `offer(3)` thất bại khi `ArrayBlockingQueue` đầy là tín hiệu **không nhận thêm**. Sau khi consumer `take()` lấy một phần tử, có một vị trí trống và `offer(3)` thành công. Trong một hệ thống có nhiều producer, không được suy luận trạng thái capacity sau một lời gọi quan sát riêng mà không có phép thêm thật.

## 6. Backpressure xảy ra khi nào?

Ký hiệu:

- `λ` (*lambda*): tốc độ công việc đến, ví dụ **requests/giây**.
- `μ` (*mu*): tốc độ consumer xử lý được ở tải hiện tại.
- `Q`: số công việc đang **chờ trong queue**.
- `K`: capacity tối đa của queue.
- `I`: số công việc **đang được xử lý**, không còn nằm trong queue.

Khi `λ > μ` kéo dài, lượng tồn đọng tăng xấp xỉ theo chênh lệch `λ - μ` cho tới khi queue đầy hoặc tài nguyên cạn. Một queue unbounded chỉ **dịch thời điểm quá tải** từ producer sang bộ nhớ, GC và độ trễ chờ; nó không làm consumer nhanh hơn.

~~~text
Incoming rate λ = 150 tasks/s
Processing rate μ = 100 tasks/s
Backlog growth ≈ 50 tasks/s

Sau 20 s: thêm khoảng 1.000 task còn đợi
(nếu tốc độ ổn định và không có cơ chế giới hạn khác).
~~~

Với queue capacity `K = 200` và bắt đầu trống, nếu chênh lệch thực sự là 50 task/s và các điều kiện lý tưởng giữ nguyên, queue có thể đầy sau khoảng 4 giây. Đây là mô hình gần đúng, **không phải công thức chọn capacity production**: tốc độ thực tế biến thiên, có burst, công việc tốn thời gian khác nhau và queue có thể được làm rỗng trong lúc nhận tải.

Khi hệ thống ổn định, **Little's Law** biểu diễn quan hệ trung bình `L = λ × W`: số mục trung bình trong **một phần hệ thống được xác định rõ** bằng throughput trung bình nhân với thời gian lưu trú trung bình. Nếu tính queue riêng, dùng **thời gian chờ queue**; nếu tính cả đang xử lý, dùng **thời gian trong hệ thống**. Không lấy queue length nhân throughput để suy ra throughput, cũng không áp dụng máy móc khi backlog tăng không ổn định.

**Backpressure** nghĩa là khi downstream chậm, upstream phải **nhận biết và thay đổi hành vi**: bị block, chờ có hạn, giảm tốc, bị từ chối, bỏ tác vụ không quan trọng hoặc chuyển sang tầng lưu bền vững. Queue bounded chỉ tạo **điểm phát hiện áp lực**; chính sách ở điểm đó quyết định hệ thống có thực sự tự bảo vệ không.

## 7. Ví dụ Java 17: chứng minh put/take có thể block

Thay vì dùng `Thread.sleep()` để đoán thứ tự, chương trình dưới đây dùng **CountDownLatch**. Queue capacity 1 đã chứa `first`, vì vậy một producer gọi `put("second")` chưa thể hoàn tất cho đến khi main lấy `first`. Sau đó, khi queue trống, một consumer chờ bằng `take()` và chỉ hoàn tất sau khi main thêm `third`.

Lưu **BlockingBackpressureDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BlockingBackpressureDemo {
    public static void main(String[] args) throws Exception {
        ArrayBlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch putting = new CountDownLatch(1);
        CountDownLatch taking = new CountDownLatch(1);

        try {
            queue.put("first");

            Future<?> producer = executor.submit(() -> {
                putting.countDown();
                queue.put("second");
                return null;
            });

            putting.await();
            System.out.println("producer done before space=" + producer.isDone());
            System.out.println("take=" + queue.take());
            producer.get(5, TimeUnit.SECONDS);
            System.out.println("next=" + queue.take());

            Future<String> consumer = executor.submit(() -> {
                taking.countDown();
                return queue.take();
            });

            taking.await();
            System.out.println("consumer done while empty=" + consumer.isDone());
            queue.put("third");
            System.out.println("consumer got=" + consumer.get(5, TimeUnit.SECONDS));
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac BlockingBackpressureDemo.java
java BlockingBackpressureDemo
~~~

Stdout khi worker hoàn thành trong thời hạn kiểm tra:

~~~text
producer done before space=false
take=first
next=second
consumer done while empty=false
consumer got=third
~~~

**Tại sao logic chắc chắn?** Trước `queue.take()` đầu tiên, `queue` đầy nên producer không thể hoàn tất `put("second")`. Trước `queue.put("third")`, queue trống và consumer không thể hoàn tất `take()`. Hai latch chỉ xác nhận worker đã đến vùng mã tương ứng, tránh race do đoán thời điểm worker bắt đầu.

Đây là **backpressure tự nhiên ở vị trí producer**: producer bị chặn thay vì tạo một backlog vô hạn. Tuy nhiên, `put()` có thể chờ vô hạn nếu không còn consumer, nên môi trường có yêu cầu latency/deadline thường nên cân nhắc `offer(timeout)` và quản lý shutdown/interrupt.

## 8. Thiết kế chính sách khi queue đầy

Một queue bounded muốn hoạt động tốt phải đi cùng **chính sách overload rõ ràng**, không chỉ một con số capacity.

### A. Chờ vô thời hạn: put(e)

Phù hợp với pipeline nội bộ có cam kết consumer tiếp tục hoạt động, producer được phép chờ và không có SLA đầu vào quá nghiêm ngặt. Cần có cách dừng/interruption; một worker producer bị kẹt mãi trong `put()` có thể khiến shutdown không hoàn tất.

### B. Chờ có hạn: offer(e, timeout, unit)

Đây thường là lựa chọn an toàn cho ingestion có deadline:

~~~java
// MÃ MINH HỌA: queue là BlockingQueue<Job>, job là một tác vụ.
if (!queue.offer(job, 100, TimeUnit.MILLISECONDS)) {
    // Không nhận thêm vào queue trong deadline.
    rejectOrDefer(job);
}
~~~

Đoạn code trên **không phải chương trình độc lập**; `Job` và `rejectOrDefer` là logic ứng dụng giả định. Lời gọi overload có timeout cũng có thể ném `InterruptedException`. Cần xử lý theo chính sách caller; tránh nuốt interrupt.

### C. Từ chối nhanh: offer(e) trả false

Thích hợp khi upstream có cơ chế retry/backoff, thông điệp lỗi tải cao hoặc mô hình load shedding. Không nên gửi lại yêu cầu **ngay lập tức vô hạn**, vì retry storm có thể làm quá tải nặng hơn.

### D. Loại bỏ/hợp nhất công việc

Với metric tổng hợp, telemetry hoặc trạng thái cập nhật liên tục, có thể **coalesce** nhiều bản cập nhật thành bản mới nhất, hoặc drop những event không quan trọng theo chính sách minh bạch. Không áp dụng cách này cho thanh toán, giao dịch hoặc công việc không được phép mất. Mọi drop cần metric và giải thích ý nghĩa nghiệp vụ.

### E. Lưu bền vững và xử lý sau

Khi không thể mất dữ liệu, có thể dùng cơ chế lưu trữ bền vững với retry và xác nhận tiêu thụ. **BlockingQueue chỉ là hàng đợi trong bộ nhớ JVM**, không tự bảo đảm xử lý sau crash, không cung cấp durable acknowledgement, deduplication hay exactly-once processing.

### F. Giới hạn concurrency ở downstream

Queue bounded chưa giới hạn triệt để số request in-flight, connection, task phụ hoặc retry đang hoạt động ở các tầng khác. Có thể cần `Semaphore` để giới hạn số thao tác đồng thời và admission control tại cửa vào. Đặt queue capacity, worker count và downstream concurrency theo tài nguyên thực sự thay vì chọn độc lập.

## 9. Ví dụ Java 17: offer có timeout và quyết định từ chối

Với queue capacity 1 đang đầy và **không có consumer**, `offer("late", 30ms)` không thể thêm, trả false khi hết thời hạn. Sau khi lấy phần tử cũ, producer có thể thử lại.

Lưu **TimedOfferDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

public class TimedOfferDemo {
    public static void main(String[] args) throws Exception {
        ArrayBlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        queue.put("first");

        boolean accepted = queue.offer(
                "late", 30, TimeUnit.MILLISECONDS);
        System.out.println("accepted while full=" + accepted);
        System.out.println("oldest=" + queue.take());

        boolean acceptedAfterDrain = queue.offer(
                "late", 30, TimeUnit.MILLISECONDS);
        System.out.println("accepted after drain=" + acceptedAfterDrain);
        System.out.println("received=" + queue.take());
    }
}
~~~

Chạy:

~~~bash
javac TimedOfferDemo.java
java TimedOfferDemo
~~~

Stdout:

~~~text
accepted while full=false
oldest=first
accepted after drain=true
received=late
~~~

Đây là ví dụ **đơn giản về timeout trên queue**, không phải chính sách retry hoàn chỉnh. Trong production, phải xác định còn đủ thời gian theo **deadline toàn request** không, và có thể retry bao nhiêu lần. Nếu không có capacity sau timeout thì caller cần trả về trạng thái “chưa được nhận” hoặc thực hiện hành động khác có thể quan sát được.

## 10. Ví dụ Java 17: pipeline nhiều consumer và graceful shutdown

Một pipeline cần giải quyết cả **hàng đợi bounded** lẫn **lifecycle**. Ví dụ dưới đây có một producer, hai consumer và capacity 2. Producer gửi số từ 1 đến 6. Sau khi producer hoàn tất việc đưa tất cả số vào queue, main đặt **hai poison pill** (một cho mỗi consumer). Các consumer xử lý bình phương và ngừng khi gặp sentinel.

Để stdout ổn định, chương trình **sắp xếp kết quả** sau khi cả hai consumer kết thúc, thay vì in ngay trên worker vốn có thứ tự không xác định.

Lưu **BoundedPipelineDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BoundedPipelineDemo {
    private static final int STOP = Integer.MIN_VALUE;

    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);
        ConcurrentLinkedQueue<Integer> processed = new ConcurrentLinkedQueue<>();
        ExecutorService executor = Executors.newFixedThreadPool(3);

        Callable<Void> consume = () -> {
            while (true) {
                int value = queue.take();
                if (value == STOP) {
                    return null;
                }
                processed.add(value * value);
            }
        };

        try {
            Future<Void> first = executor.submit(consume);
            Future<Void> second = executor.submit(consume);
            Future<?> producer = executor.submit(() -> {
                for (int i = 1; i <= 6; i++) {
                    queue.put(i);
                }
                return null;
            });

            producer.get(); // Tất cả phần tử dữ liệu đã được nhận.
            queue.put(STOP);
            queue.put(STOP); // Một sentinel cho mỗi consumer.

            first.get();
            second.get();

            List<Integer> sorted = new ArrayList<>(processed);
            Collections.sort(sorted);
            System.out.println("processed=" + sorted);
            System.out.println("count=" + sorted.size());
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac BoundedPipelineDemo.java
java BoundedPipelineDemo
~~~

Stdout:

~~~text
processed=[1, 4, 9, 16, 25, 36]
count=6
~~~

**Đặc điểm đúng:**

- `queue.put(i)` sẽ chờ khi queue capacity 2 đầy, làm producer chậm theo khả năng tiêu thụ.
- Mọi consumer cùng `take()`, mỗi phần tử được một consumer lấy khỏi queue (không có chuyện hai consumer cùng `take()` một phần tử).
- `ConcurrentLinkedQueue` dùng để **thu thập kết quả của ví dụ**, không làm work queue đầu vào; dữ liệu hữu hạn chỉ có sáu kết quả. Nó không thay thế một output queue bounded nếu kết quả cũng có thể tăng vô hạn trong ứng dụng thật.
- `producer.get()` phải hoàn tất **trước** khi gửi sentinel; nếu gửi sentinel sớm, consumer có thể dừng trước khi nhận hết dữ liệu.
- Hai sentinel dành cho hai consumer. Nếu consumer count khác, cách gửi poison pill cũng phải phù hợp.

**Giới hạn của ví dụ:** Poison pill chỉ là một giao thức dừng **tự chọn**, không phải tính năng của BlockingQueue. Sentinel phải là giá trị **không thể nhầm với dữ liệu thật**. Nếu có nhiều producer, chỉ được phát sentinel khi tất cả producer đã ngừng gửi. Nếu consumer fail trước khi nhận sentinel và queue đầy, producer gửi sentinel có thể kẹt; production cần giám sát failure, timeout, đóng nhận việc, cancellation và quy trình xử lý phần tử còn tồn đọng.

## 11. ThreadPoolExecutor: bounded queue và cơ chế từ chối

Khi dùng `ThreadPoolExecutor`, hàng đợi của executor đóng vai trò **buffer chờ chạy task**, nhưng không đồng nghĩa task đang chạy. Cấu hình quan trọng bao gồm:

- `corePoolSize`, `maximumPoolSize`.
- `BlockingQueue<Runnable> workQueue` với capacity hữu hạn hay không.
- `RejectedExecutionHandler` được gọi khi executor không thể nhận thêm tác vụ theo quy tắc pool hoặc khi đang shutdown.

Các chính sách từ chối tiêu biểu:

| Chính sách | Hành vi khi saturated | Lưu ý |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Caller phải xử lý và trả trạng thái overload rõ ràng |
| `CallerRunsPolicy` | Thực thi task **ngay trong thread gọi execute** khi executor chưa shutdown | Làm chậm caller, tạo backpressure nhưng có thể ảnh hưởng độ trễ request/UI; khi đã shutdown, chính sách không chạy tác vụ |
| `DiscardPolicy` | Bỏ task bị từ chối | Dễ mất công việc âm thầm nếu không đo lường |
| `DiscardOldestPolicy` | Bỏ một task cũ từ queue rồi thử gửi lại | Dữ liệu có thể mất, cần hiểu thứ tự/priority và quy tắc nghiệp vụ |

**Bẫy:** `Executors.newFixedThreadPool(n)` theo implementation chuẩn dùng một **LinkedBlockingQueue không giới hạn capacity hữu ích**. Dù số worker là n, queue vẫn có thể phình lên khi tiếp nhận nhanh hơn xử lý. Nếu cần kiểm soát lượng backlog, tạo `ThreadPoolExecutor` với queue bounded và rejection policy rõ ràng.

### Ví dụ Java 17: CallerRunsPolicy làm chậm bên gửi

Lưu **CallerRunsDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CallerRunsDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean executedByCaller = new AtomicBoolean();
        Thread caller = Thread.currentThread();

        try {
            Future<?> busy = pool.submit(() -> {
                started.countDown();
                release.await();
                return null;
            });
            started.await();

            Future<?> queued = pool.submit(() -> "queued");
            pool.execute(() -> executedByCaller.set(
                    Thread.currentThread() == caller));

            System.out.println("caller ran=" + executedByCaller.get());
            release.countDown();
            busy.get();
            queued.get();
            System.out.println("all accepted work finished=true");
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Chạy:

~~~bash
javac CallerRunsDemo.java
java CallerRunsDemo
~~~

Stdout:

~~~text
caller ran=true
all accepted work finished=true
~~~

Worker duy nhất đang đợi latch, queue capacity 1 đã có tác vụ thứ hai. Khi gọi `execute` tác vụ thứ ba, executor đang saturated, nên `CallerRunsPolicy` thực thi tác vụ **ngay trên thread caller**, không đưa thêm vào queue. Điều này có thể tạo backpressure cho một producer đồng bộ, nhưng nếu caller là thread xử lý HTTP/UI, thời gian request cũng tăng. Nếu caller chịu trách nhiệm nhận tiếp nhiều yêu cầu thì chính sách có thể ảnh hưởng rộng hơn dự kiến.

**Quan trọng:** `CallerRunsPolicy` không phải đảm bảo “không bao giờ mất task” khi pool shutdown; hãy kiểm tra lifecycle và dùng rejection policy phù hợp với yêu cầu độ tin cậy.

## 12. Hạn chế số request in-flight bằng Semaphore

Một queue bounded chỉ giới hạn **mục đang chờ trong queue**, chưa chắc giới hạn tổng tất cả phần việc đang chạy ở các pool phụ hoặc số outbound request tới database. Nếu tải downstream là nút thắt, dùng `Semaphore` để giới hạn số phép xử lý có thể bắt đầu đồng thời:

~~~java
// MINH HỌA (không phải class độc lập):
if (!slots.tryAcquire(100, TimeUnit.MILLISECONDS)) {
    rejectRequest();
    return;
}
try {
    callDownstreamWithTimeout();
} finally {
    slots.release();
}
~~~

Ở đây `slots` là `Semaphore` đã khai báo, `rejectRequest()` và `callDownstreamWithTimeout()` là logic nghiệp vụ giả định. Điểm then chốt là **chỉ release khi đã acquire thành công**, và release trong `finally` để không rò permit khi tác vụ lỗi.

Không nên giữ permit trong khi một công việc chưa đến lượt xử lý **nếu permit chỉ dành cho giới hạn xử lý đang chạy**. Nếu muốn giới hạn **toàn bộ hệ thống đang tiếp nhận**, bao gồm queued + running, định nghĩa rõ phạm vi permit và acquire trước admission; release khi công việc thật sự xong hoặc bị loại bỏ. Việc chọn vị trí acquire quyết định bạn đang giới hạn thành phần nào.

## 13. Thiết kế shutdown và xử lý interruption

**`BlockingQueue` không có phương thức `close()` chung**. Vì vậy producer/consumer phải tự có protocol kết thúc: cờ trạng thái + interrupt; sentinel/poison pill; hoặc quản lý vòng đời `ExecutorService` và `Future`.

Một quy trình có kiểm soát:

1. **Chặn producer mới** hoặc chuyển hệ thống sang trạng thái STOPPING.
2. **Dừng hoặc chờ producer hiện tại** theo policy; không để producer tiếp tục enqueue sau khi đã đặt sentinel.
3. Quyết định **drain queue** (xử lý hết) hay **discard** (bỏ có ghi nhận). Không có đáp án chung.
4. Nếu drain, bảo đảm consumer còn sống đủ để lấy việc; chỉ phát tín hiệu stop **sau khi** producer không còn thêm việc.
5. Chờ consumer hoàn tất có **deadline**; nếu quá hạn, cân nhắc interrupt và phương án xử lý các mục chưa xong.
6. Phân biệt “queue trống” với “mọi công việc đã xử lý thành công”: consumer có thể đã lấy phần tử nhưng vẫn đang chạy hoặc bị lỗi.

Khi `put()`/`take()`/`offer(timeout)` ném `InterruptedException`, đừng nuốt rồi loop vô hạn. Thông thường truyền tiếp exception; hoặc khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` rồi thoát nếu catch tại chỗ. Chỉ gọi `shutdownNow()` không đảm bảo mọi side effect bên ngoài được rollback hoặc task bị kill tức thì.

**Poison pill** có rủi ro khi số consumer động, khi một consumer chết, khi queue đầy hoặc khi có nhiều producer chưa ngừng. Cần xác định policy và ownership trước khi dùng để shutdown trong production.

## 14. Monitoring: nhìn vào toàn bộ pipeline

Các metric có giá trị:

- **Ingress rate** và **completion rate**, theo từng loại công việc.
- **Queue depth** và **queue capacity**, đặc biệt là tỷ lệ chiếm dụng `depth / capacity`.
- **Queue wait time** (p50/p95/p99), **processing time** và **end-to-end latency**.
- Số lượng **active consumer/worker**, số yêu cầu **in-flight** và **downstream saturation**.
- Tần suất `offer` trả false, **put blocked duration**, timeout, rejection, drop và retry.
- Số task lỗi, số lần phải shutdown/escalation và backlog tồn sau shutdown.

`ConcurrentLinkedQueue.size()` là thao tác **O(n)**, có thể phản ánh kết quả không chính xác nếu queue bị sửa đồng thời; không polling nó với tần suất cao để làm metric chi tiết. Với queue khác, `size()` hoặc `remainingCapacity()` cũng chỉ là snapshot cho quan sát, **không phải chỗ đã được giữ trước cho một producer**.

Nếu backlog tăng liên tục, cần kiểm tra liệu do ingress rate tăng, consumer chậm, downstream timeout/lock contention, số worker giảm hay do retry đang khuếch đại tải. **Tăng capacity** chỉ làm tăng thời gian chịu burst và thường tăng độ trễ chờ; nó không sửa được bottleneck trong trạng thái quá tải kéo dài.

## 15. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `ConcurrentLinkedQueue` rồi nghĩ sẽ tự backpressure | Producer tiếp tục thêm, backlog tăng | Giới hạn admission bên ngoài hoặc dùng bounded BlockingQueue |
| `new LinkedBlockingQueue<>()` mà không đặt capacity | Queue có thể tăng đến áp lực bộ nhớ | Truyền capacity hữu hạn |
| Bỏ qua `offer()` trả false | Task không được nhận nhưng không ai biết | Xử lý rejection/drop/retry có metric |
| Gọi `put()` trên thread phải đáp ứng deadline ngắn | Có thể chờ vô hạn | Dùng `offer(timeout)` với deadline rõ |
| Busy-spin `while (queue.poll() == null) {}` | Đốt CPU | Dùng `take()`, `poll(timeout)` hoặc tín hiệu phù hợp |
| Dùng `peek()` thay `take()/poll()` để nhận việc | Nhiều consumer có thể xử lý cùng mục | Dùng thao tác lấy và xóa |
| Đọc `size()` rồi mới `add()` như một giao dịch | Race giữa kiểm tra và insert | Dùng `offer/put` theo hợp đồng |
| Nghĩ bounded queue là bảo đảm không mất dữ liệu | Crash, consumer lỗi, drop vẫn gây mất | Định nghĩa durability/ack/retry riêng |
| Gửi poison pill trước khi producer xong | Consumer dừng, dữ liệu còn lại bị bỏ | Hoàn tất producer trước khi gửi sentinel |
| Retry không backoff khi queue đầy | Retry storm, tải tăng thêm | Budget retry và backoff có jitter |
| Coi queue empty là tất cả task xong | Task có thể đang chạy hoặc fail | Theo dõi in-flight và completion |
| Cứ tăng queue capacity để giải quyết overload | Latency/heap tăng, bottleneck còn đó | Giới hạn ingress, tối ưu consumer/downstream |

## 16. Checklist chọn cơ chế và bài tập suy luận

Trước khi đưa pipeline vào sản xuất, hãy trả lời:

1. Queue cần FIFO, ưu tiên, delay hay rendezvous? Có dùng đúng implementation không?
2. Capacity được **giới hạn hữu hạn** ở đâu? Nếu không, hệ thống có ngân sách heap và cơ chế upstream admission riêng chưa?
3. Producer sẽ **chờ, chờ có hạn, bị từ chối, drop hoặc lưu bền vững** khi queue đầy?
4. Consumer xử lý nhanh hơn tốc độ nhập **trung bình dài hạn** không? Có đo thực tế không?
5. Đã giới hạn số công việc đang xử lý, connection và request downstream riêng chưa?
6. Đã có timeout, retry budget, backoff và idempotency phù hợp cho work item chưa?
7. Có đo queue wait/processing/end-to-end latency, rejection và memory/GC không?
8. Shutdown có thể dừng producer, drain/discard, dừng consumer và thông báo phần việc chưa xong một cách có kiểm soát không?
9. Khi một consumer chết, ai phát hiện? Có cơ chế retry, quarantine hoặc dead-letter nếu nghiệp vụ cần không?
10. Nếu backlog tăng 50 task/s trong 60 giây, queue sẽ thêm bao nhiêu mục; hệ thống sẽ phản ứng ở thời điểm nào?

**Ghi nhớ:** **Concurrent queue** cung cấp thao tác thread-safe và thường không chặn; **BlockingQueue** cung cấp cơ chế chờ khi trống/đầy tùy implementation và capacity; **backpressure** là việc **điều chỉnh lượng công việc được nhận** khi downstream không theo kịp. Trong Java, hãy kết hợp **bounded queue**, `offer/put/take` đúng ngữ nghĩa, deadline, rejection policy, giới hạn in-flight và quan sát end-to-end thay vì kỳ vọng một queue giải quyết mọi vấn đề.

## 17. Tài liệu API chuẩn Java

- [Java SE 17 – Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html)
- [Java SE 17 – BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [Java SE 17 – ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html)
- [Java SE 17 – ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
