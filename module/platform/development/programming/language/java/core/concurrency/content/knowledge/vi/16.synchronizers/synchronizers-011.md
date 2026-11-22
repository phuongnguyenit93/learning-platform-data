# Khi nên dùng BlockingQueue thay vì tự phối hợp luồng trong Java

## 1. Bài toán: producer–consumer tưởng đơn giản nhưng nhiều hợp đồng ẩn

Một thread tạo dữ liệu, thread khác xử lý dữ liệu. Ví dụ: thread đọc log đẩy các sự kiện vào một hàng đợi; nhiều worker chờ nhận để tính toán hoặc ghi kết quả. Bạn có thể tự viết `synchronized` + `wait()/notifyAll()` hoặc `ReentrantLock` + `Condition`. Nhưng khi làm như vậy, bạn cũng phải tự chịu trách nhiệm về tất cả những vấn đề sau:

- Hàng đợi rỗng thì consumer **chờ** như thế nào mà không đốt CPU?
- Producer thêm phần tử xong phải **đánh thức ai**, tại thời điểm nào?
- Nhiều producers/consumers cùng chạy có thể đánh thức nhầm nhóm thread không?
- Khi queue đầy, producer **đợi, từ chối hay bỏ dữ liệu**?
- Nếu thread bị interrupt trong khi đang chờ, trạng thái dữ liệu và interrupt phải xử lý ra sao?
- Có bị **lost notification**, kiểm tra điều kiện ngoài lock, hoặc dùng `if` thay `while` không?
- Khi shutdown, consumer đang chờ `take()` sẽ được kết thúc như thế nào?
- Tính **FIFO, fairness, ordering hoàn tất** và memory visibility được bảo đảm tới mức nào?

`java.util.concurrent.BlockingQueue<E>` có sẵn giao thức handoff có đồng bộ giữa producers và consumers, cùng các phương thức chặn, không chặn và chờ có thời hạn. Khi bài toán đúng là **truyền các phần tử qua hàng đợi giữa các thread**, việc dùng collection chuyên dụng này thường đơn giản và ít lỗi hơn viết protocol chờ–báo thức thủ công.

Bài học thuộc **Synchronizers** trong **Java Advance - concurrency**, chủ đề trực tiếp **“Khi nên dùng BlockingQueue thay vì tự phối hợp luồng”**. Phạm vi là Java SE 17+ nói chung; không đưa framework/API riêng của Spring vì phần liên quan Spring đã có chương riêng.

### Sau bài học, bạn có thể

1. Mô tả `BlockingQueue` cung cấp những hợp đồng gì: handoff, wait, timeout, boundedness, visibility và ordering.
2. Phân biệt `put/take`, `offer/poll`, các phiên bản timed, `add/remove/element` và giá trị sentinel `null`.
3. Giải thích vì sao tự viết `wait/notifyAll` cần vòng `while`, cùng monitor, state invariant và cleanup.
4. Chọn `ArrayBlockingQueue`, `LinkedBlockingQueue`, `SynchronousQueue`, `PriorityBlockingQueue` hoặc loại queue khác theo mục tiêu.
5. Nhận ra trường hợp **không nên dùng queue**, ví dụ chỉ đợi một sự kiện, cấp số permit, chờ nhiều thread tới barrier hoặc lấy kết quả của một computation.
6. Thiết kế bounded queue và backpressure thay vì dùng hàng đợi vô hạn như nơi chứa mọi backlog.
7. Xử lý interruption, shutdown, poison pill cho nhiều consumer, cancellation, lỗi producer và queue bị đầy.
8. Giải thích sự khác biệt giữa **thứ tự lấy khỏi queue** và **thứ tự hoàn tất công việc**.
9. Chạy năm chương trình Java 17+ độc lập có đầu ra xác định, kiểm chứng được.

## 2. BlockingQueue chính xác là gì?

`BlockingQueue<E>` là interface kế thừa `Queue<E>`. Ngoài thao tác thêm/lấy/xem phần tử, nó có các thao tác cho phép thread **đợi** tới khi trạng thái queue đáp ứng điều kiện.

~~~text
Producer A -----\
                 \                    put / offer
Producer B ------>  [ BlockingQueue ]  --------------+
                 /          |                        |
Producer C -----/      buffer hoặc rendezvous        v
                                             Consumer 1
                                             Consumer 2
                                             Consumer 3
~~~

Queue là **ranh giới trao đổi dữ liệu**, không phải một thread, không tự chạy `Runnable`, không tự tạo worker và không tự quản lý vòng đời nghiệp vụ. Caller vẫn cần `Thread`/`ExecutorService` để chạy producer/consumer.

Có hai điều kiện chờ cơ bản:
- **Queue rỗng:** consumer gọi `take()` hoặc timed `poll(timeout,unit)` có thể phải đợi tới khi có item.
- **Queue đầy (với queue bounded):** producer gọi `put()` hoặc timed `offer(e,timeout,unit)` có thể phải đợi tới khi có chỗ trống.

Những điều kiện chờ này được implementation của `BlockingQueue` đồng bộ và đánh thức theo contract. Bạn không phải tự duy trì biến `notEmpty`, `notFull` hay gọi `notifyAll` trên mỗi đường cập nhật.

### BlockingQueue khác Collection thông thường ở đâu?

`ArrayDeque`, `LinkedList` và `ArrayList` không tự thread-safe để nhiều thread cùng `add/remove`. `Collections.synchronizedList`/`synchronizedCollection` có thể bảo vệ các method riêng lẻ, nhưng **không cung cấp trực tiếp giao thức “chờ có dữ liệu/chờ có chỗ”** qua `put/take`. `ConcurrentLinkedQueue` hỗ trợ concurrent FIFO nonblocking nhưng không có `take()` để block khi rỗng.

`BlockingQueue` cung cấp **cả quyền truy cập đồng thời lẫn giao thức chờ** phù hợp producer–consumer. Đây là lý do chọn queue thay vì chỉ chọn một collection có phương thức thread-safe.

## 3. Bốn nhóm thao tác và cách xử lý khi không thể thực hiện ngay

Hợp đồng `BlockingQueue` có bốn kiểu phản ứng với hai hành động **insert** và **remove**:

| Cách xử lý | Thêm phần tử | Lấy phần tử | Khi không làm ngay được |
| --- | --- | --- | --- |
| Ném exception | `add(e)` | `remove()` | Ném exception khi queue full/empty tương ứng |
| Trả giá trị đặc biệt | `offer(e)` | `poll()` | `false` khi không thêm được, `null` khi rỗng |
| Chờ vô hạn nếu không bị interrupt | `put(e)` | `take()` | Thread có thể chờ tới khi điều kiện thay đổi |
| Chờ có thời hạn | `offer(e,t,u)` | `poll(t,u)` | Trả `false/null` khi hết thời hạn |

Đối với thao tác **đọc đầu queue mà không lấy**:
- `element()` ném `NoSuchElementException` khi rỗng.
- `peek()` trả `null` khi rỗng.

**Lưu ý:** `poll()==null` có ý nghĩa queue hiện không có item, bởi `BlockingQueue` **không cho phép thêm phần tử `null`**. Đừng thiết kế `null` vừa là dữ liệu hợp lệ vừa là tín hiệu kết thúc của chính BlockingQueue.

### Ví dụ chọn method theo chính sách nghiệp vụ

- **Không thể mất dữ liệu, chấp nhận đợi:** `put(event)`, đồng thời phải bảo đảm shutdown/cancel đánh thức producer khi cần.
- **Hệ thống cần reject khi quá tải:** `offer(event)` rồi xử lý `false` bằng log/metric/retry thích hợp.
- **Có deadline chặt:** `offer(event, remaining, unit)` hoặc `poll(remaining, unit)`.
- **Không muốn block thread consumer:** `poll()` và dùng một scheduler/event mechanism khác để quyết định lần kiểm tra tiếp theo.
- **Consumer phải chờ việc mới:** `take()` nếu có giao thức kết thúc rõ ràng.

Không thay `put()` bằng vòng lặp liên tục `while (!queue.offer(x)) {}`. Vòng quay nóng này có thể chiếm CPU, tăng contention và không có chiến lược backpressure hợp lý.

### Interrupt khi đang chờ

`put`, `take` và phiên bản timed có `InterruptedException`. Khi bị interrupt:
- Primitive có thể thoát khỏi chờ bằng exception.
- Bạn phải quyết định propagate exception hoặc restore interrupt status và **ngừng/đổi trạng thái công việc**.
- Việc thoát do interrupt không đồng nghĩa đã hoàn tất lưu dữ liệu hay remote transaction.
- Nếu producer phải bảo đảm không mất item, cần xác định item chưa gửi có thể retry/idempotent hoặc được chuyển sang đường xử lý nào.

Cẩn trọng với việc **nuốt `InterruptedException` rồi tiếp tục vòng lặp vô hạn**: request đã hủy nhưng worker lại tiếp tục chờ như chưa có gì.

## 4. Memory visibility: handoff cũng là một đồng bộ hóa

Theo contract memory consistency của `BlockingQueue`:

> Hành động của một thread trước khi đặt một object vào BlockingQueue happens-before các hành động sau khi thread khác truy cập hoặc lấy object đó từ queue.

Điều này giúp **publish dữ liệu trước handoff** cho consumer:

~~~java
record Message(int id, String payload) {}

Message message = new Message(7, "ready");
queue.put(message);

// Thread consumer:
Message received = queue.take();
use(received.payload());
~~~

Đây là snippet gồm code ở hai threads, với `queue` và `use` cần khai báo. Dữ liệu được tạo trước `put` sẽ được công bố tới thread nhận theo contract, không cần tự gọi `volatile` chỉ để truyền một object immutable qua queue.

**Nhưng** memory visibility không tự làm object mutable an toàn khi nhiều threads còn cùng sửa nó sau khi enqueue:
- Producer đặt một `ArrayList` vào queue rồi tiếp tục thêm phần tử trong khi consumer đang iterate list: vẫn có nguy cơ data race.
- Một object có nhiều field cần invariant chung không trở thành immutable vì được enqueue.
- Dùng immutable message, ownership transfer (producer giao xong không sửa nữa), hoặc locking thích hợp.

BlockingQueue giúp **handoff/visibility**, không thay thế nguyên tắc quản lý shared mutable state.

## 5. Vì sao tự viết wait/notify dễ sai?

Một bounded buffer tự xây cần ít nhất hai predicate:
- `notEmpty`: `size > 0`, cho phép consumer lấy.
- `notFull`: `size < capacity`, cho phép producer thêm.

Các predicate phải được kiểm tra **dưới cùng monitor/lock** được dùng để chờ và đánh thức. Mẫu monitor đúng về cơ bản:

~~~java
synchronized (monitor) {
    while (queue.isEmpty()) {
        monitor.wait();
    }

    E item = queue.removeFirst();
    monitor.notifyAll();
    return item;
}
~~~

Đây là snippet trong method `take`, giả định `monitor`, `queue` được khai báo và method cho phép ném `InterruptedException`. Vì `wait()` nhả monitor và lấy lại monitor trước khi trả, vòng `while` **kiểm tra lại điều kiện sau khi thức dậy**.

### Lỗi 1 — dùng if thay while

Sai:

~~~java
synchronized (monitor) {
    if (queue.isEmpty()) {
        monitor.wait();
    }
    return queue.removeFirst();
}
~~~

Một thread có thể tỉnh vì **spurious wakeup** hoặc vì thread khác đã lấy item trước khi nó giành lại lock. Nếu bỏ qua kiểm tra lại, consumer có thể xóa trên queue rỗng. `while` là yêu cầu correctness, không phải “biện pháp dự phòng hiếm gặp”.

### Lỗi 2 — kiểm tra predicate ngoài lock

Sai:

~~~java
if (queue.isEmpty()) {
    synchronized (monitor) {
        monitor.wait();
    }
}
~~~

Giữa lần kiểm tra `isEmpty` và lần thật sự wait, producer có thể thêm dữ liệu/notify. Consumer sau đó mới wait và có thể **bỏ lỡ tín hiệu**, dù dữ liệu đã có. Tên lỗi thường gọi là **lost notification** hoặc missed signal trong giao thức chờ sai.

### Lỗi 3 — notify một waiter không phù hợp

Khi cùng monitor có cả producers đang chờ `notFull` và consumers đang chờ `notEmpty`, `notify()` đánh thức một waiter bất kỳ; có thể đánh thức một nhóm không tiến triển, nhất là trong thiết kế phức tạp. `notifyAll()` thường đơn giản hơn cho correctness khi chỉ dùng một monitor, đổi lại có thể gây nhiều thread thức dậy và tranh lock.

Nếu dùng `ReentrantLock` và hai `Condition` như `notEmpty` và `notFull`, bạn có thể signal đúng hàng đợi điều kiện hơn, nhưng phải tự xử lý lock, predicate, interrupt và close. **BlockingQueue đã đóng gói phần cơ chế này** trong API.

### Lỗi 4 — quên trạng thái shutdown

Một consumer đang chờ ở `wait()` có thể không bao giờ tỉnh nếu producer đã chết trước khi gửi tín hiệu. `BlockingQueue.take()` cũng **không tự giải quyết vòng đời**, nhưng ít nhất đưa bạn tới giao thức chặn chuẩn với interruption, timed wait và khả năng gửi terminal signal.

### Lỗi 5 — tự viết queue mà quên backpressure

Nếu mọi producer cứ `add` vào một `ArrayDeque` tăng vô hạn, buffer có thể cạn bộ nhớ. Một bounded queue cần xử lý `notFull` và quyết định liệu producer chờ hay drop/reject. `ArrayBlockingQueue(capacity)` đã cung cấp việc quản lý capacity và chờ tương ứng.

**Kết luận phần này:** Bạn có thể tự xây monitor buffer đúng, nhưng để đạt tương đương một BlockingQueue production, phải thiết kế và test nhiều góc cạnh concurrency. Nếu không có invariant rất đặc biệt, ưu tiên collection đã chuẩn hóa.

## 6. Ví dụ 1 — Bounded producer–consumer bằng ArrayBlockingQueue

Tạo file **`BoundedHandoffDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BoundedHandoffDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<?> producer = pool.submit(() -> {
                try {
                    queue.put(10);
                    queue.put(20);
                    queue.put(30);
                    queue.put(-1); // Sentinel dành cho một consumer.
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("producer interrupted", e);
                }
            });

            Future<List<Integer>> consumer = pool.submit(() -> {
                List<Integer> received = new ArrayList<>();
                while (true) {
                    int value = queue.take();
                    if (value == -1) {
                        return received;
                    }
                    received.add(value);
                }
            });

            producer.get();
            List<Integer> result = consumer.get();

            System.out.println("received=" + result);
            System.out.println("remaining=" + queue.size());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy Java 17+:

~~~bash
javac BoundedHandoffDemo.java
java BoundedHandoffDemo
~~~

Stdout khi không có interruption/lỗi bên ngoài:

~~~text
received=[10, 20, 30]
remaining=0
~~~

**Giải thích từng điểm:**
1. `ArrayBlockingQueue<>(2)` cho tối đa hai phần tử đang nằm trong buffer; đây là giới hạn backlog tại ranh giới queue.
2. Producer đưa `10,20,30,-1` theo thứ tự. Khi buffer đầy, `put` có thể chờ cho tới lúc consumer lấy bớt.
3. Consumer dùng `take()` để chờ item khi rỗng, không tự gọi `wait`, không cần busy polling.
4. Có **một producer và một consumer**, nên thứ tự nhận là FIFO `10,20,30`. `-1` được dành riêng để kết thúc.
5. Main gọi `Future.get()`, đảm bảo producer và consumer hoàn tất thành công trước khi đọc result và size.
6. Chương trình không dự đoán thread nào chạy trước hoặc có bao nhiêu lần producer thật sự phải chờ; điều đó phụ thuộc lịch chạy.

**Production caveat:** Nếu producer bị lỗi trước khi gửi sentinel, consumer có thể đợi mãi. `Future.get()` cũng có thể đợi vô hạn. Cần thiết kế deadline, cancellation, close protocol hoặc coordinator phát terminal signal khi producer thất bại; **BlockingQueue không có method close() chung trong interface**.

### Vì sao không dùng LinkedList + synchronized cho cùng bài toán?

Có thể làm vậy, nhưng bạn phải viết thêm:
- Kiểm tra buffer rỗng/đầy trong vòng while.
- Nhả lock khi chờ rồi lấy lại lock.
- Signal producer khi consumer lấy item và ngược lại.
- Xử lý interruption, shutdown, capacity và ordering.
- Kiểm thử race ở những thời điểm mất notify.

BlockingQueue cho đúng abstraction: **dữ liệu qua một hàng đợi có thể chặn**.

## 7. Ví dụ 2 — Chọn offer/poll và timed methods theo backpressure

Không phải ứng dụng nào cũng chấp nhận chờ vô thời hạn. Với UI request, message ingestion hoặc API có SLO, bạn có thể dùng `offer`/`poll`.

Tạo file **`TimedQueuePolicyDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

public class TimedQueuePolicyDemo {
    public static void main(String[] args) throws Exception {
        ArrayBlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);

        boolean accepted1 = queue.offer(1);
        boolean accepted2 = queue.offer(2);
        boolean accepted3 = queue.offer(3);

        boolean timedAccepted = queue.offer(
                4, 20, TimeUnit.MILLISECONDS);

        System.out.println("accepted=" +
                accepted1 + "," + accepted2 + "," + accepted3);
        System.out.println("timedAccepted=" + timedAccepted);
        System.out.println("poll1=" + queue.poll());
        System.out.println("poll2=" + queue.poll());
        System.out.println("pollEmpty=" + queue.poll());
        System.out.println("timedPollEmpty=" +
                queue.poll(20, TimeUnit.MILLISECONDS));
    }
}
~~~

Chạy:

~~~bash
javac TimedQueuePolicyDemo.java
java TimedQueuePolicyDemo
~~~

Stdout không có interruption bên ngoài:

~~~text
accepted=true,true,false
timedAccepted=false
poll1=1
poll2=2
pollEmpty=null
timedPollEmpty=null
~~~

Ở đây không có consumer khác, nên buffer capacity 2 chắc chắn full khi gọi `offer(4,20ms)`. Timed offer hết hạn rồi trả false. Hai lần `poll` lấy 1 rồi 2 theo FIFO; lần sau queue rỗng, cả poll thường và timed poll đều trả null.

**Chính sách ứng dụng phải quyết định khi `offer` trả false:**
- Trả 429/503 hoặc một loại “busy” phù hợp ở tầng API.
- Ghi metric rejected.
- Retry với exponential backoff và deadline tổng.
- Chuyển sang storage bền vững nếu nghiệp vụ không được phép mất sự kiện.
- Drop/coalesce nếu dữ liệu có thể bỏ (ví dụ sensor sampling).

Bản thân `offer(false)` không tự quyết định business semantics. Không retry mãi trong một thread pool nhỏ mà không có timeout — nó có thể làm hệ thống kiệt worker.

## 8. Chọn implementation BlockingQueue phù hợp

| Implementation | Thứ tự chính | Capacity | Blocking semantics | Nên cân nhắc khi |
| --- | --- | --- | --- | --- |
| `ArrayBlockingQueue<E>` | FIFO | **Cố định, bounded** | `put/take`, timed `offer/poll` | Pipeline có giới hạn backlog rõ |
| `LinkedBlockingQueue<E>` | FIFO | Có thể bounded khi truyền capacity; mặc định rất lớn | `put/take`, timed API | Producer–consumer FIFO với cấu trúc linked |
| `SynchronousQueue<E>` | Handoff trực tiếp | **0 item buffered** | Producer/consumer đợi partner | Rendezvous, giao việc trực tiếp |
| `LinkedBlockingDeque<E>` | Hai đầu, FIFO nếu dùng last/first | Capacity tùy chọn | Blocking ở hai đầu | Work deque, yêu cầu push/pop riêng |
| `PriorityBlockingQueue<E>` | Priority/comparator | **Không bounded theo constructor** | `take` khi rỗng; put không chờ vì capacity logic | Priority scheduler không yêu cầu FIFO |
| `DelayQueue<E extends Delayed>` | Theo delay expiry | Không bounded | `take` đợi item đến hạn | Xử lý sự kiện sau độ trễ |
| `LinkedTransferQueue<E>` | FIFO, có transfer semantics | Unbounded về cấu trúc | `transfer` có thể chờ consumer nhận | Handoff với lựa chọn transfer trực tiếp |

### ArrayBlockingQueue: baseline rõ cho bounded backlog

- Backing array cố định theo capacity.
- FIFO cho các phần tử đã enqueue theo thứ tự xác định.
- Tùy chọn `fair=true` để cân nhắc fairness giữa threads chờ truy cập; fairness **không** có nghĩa xử lý hoàn tất FIFO hoặc priority.
- Boundedness giúp giới hạn số item đang đợi, nhưng không thay thế chính sách upstream khi queue đầy.

Thường là điểm xuất phát dễ lý luận cho **producer–consumer có backpressure**.

### LinkedBlockingQueue: đừng nhầm mặc định là “vừa đủ”

`new LinkedBlockingQueue<>()` có capacity mặc định `Integer.MAX_VALUE`; nó không chờ producer do một ngưỡng nhỏ như 1.000 trừ khi bạn cấu hình:

~~~java
BlockingQueue<Event> queue = new LinkedBlockingQueue<>(1_000);
~~~

Đây là snippet giả định class `Event` đã tồn tại. Một backlog mặc định rất lớn có thể làm cạn memory nếu tốc độ producer vượt consumer kéo dài. “Unbounded về contract thực tế” không có nghĩa máy có bộ nhớ vô hạn.

### PriorityBlockingQueue: không phải FIFO

`PriorityBlockingQueue` trả phần tử theo comparator/natural order; nếu nhiều phần tử có priority bằng nhau, **không bảo đảm FIFO ổn định**. Nếu cần tie-break, thêm sequence vào comparator. Không dùng `iterator()` để giả định thứ tự priority: iterator không phải ordered drain.

Nó có thể block consumer lúc rỗng, nhưng producer `put` không tạo backpressure bounded kiểu `ArrayBlockingQueue`. Nếu cần vừa priority vừa bounded backlog, phải thiết kế admission control khác; **không thể đổi constructor capacity ban đầu rồi coi đó là hard limit**.

### DelayQueue: chờ đến khi item đến hạn

`DelayQueue` là BlockingQueue đặc biệt: phần tử phải implement `Delayed`; consumer `take` chỉ trả item khi delay đã hết. Dù queue có item vật lý, `poll()` có thể trả null khi chưa item nào hết hạn. Không phù hợp thay một FIFO work queue nếu bạn cần xử lý ngay.

### Deque: hành động nào quyết định ordering

`LinkedBlockingDeque` có thể lấy/thêm ở cả đầu và cuối. Nếu dùng `putLast` + `takeFirst` thì theo FIFO; nếu dùng `putFirst` + `takeFirst` thì theo LIFO cho các phần tử tương ứng. “Có ordering” chưa đủ: phải chỉ rõ **thao tác ở đầu nào**.

## 9. Ví dụ 3 — SynchronousQueue: trao đổi trực tiếp không buffer

`SynchronousQueue` có capacity bằng 0: một lần `put(x)` cần một consumer tương ứng nhận; nó không chứa item trong buffer. Vì vậy:
- `offer(x)` không chờ sẽ trả false nếu chưa có consumer chờ phù hợp.
- `put(x)` có thể block tới khi một `take()` nhận.
- `remainingCapacity()` luôn 0.
- Nó hữu ích khi muốn ràng buộc tốc độ producer vào consumer nhưng **không** tự tạo retry/durable storage.

Tạo file **`SynchronousHandoffDemo.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;

public class SynchronousHandoffDemo {
    public static void main(String[] args) throws Exception {
        SynchronousQueue<String> queue = new SynchronousQueue<>();

        boolean offeredWithoutReceiver = queue.offer("early");

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<?> sender = pool.submit(() -> {
                try {
                    queue.put("payload");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("sender interrupted", e);
                }
            });

            Future<String> receiver = pool.submit(queue::take);

            sender.get();
            String result = receiver.get();

            System.out.println("immediateOffer=" + offeredWithoutReceiver);
            System.out.println("received=" + result);
            System.out.println("remainingCapacity=" +
                    queue.remainingCapacity());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac SynchronousHandoffDemo.java
java SynchronousHandoffDemo
~~~

Stdout khi không có interruption/lỗi bên ngoài:

~~~text
immediateOffer=false
received=payload
remainingCapacity=0
~~~

**Vì sao tất định?** Lần `offer("early")` chạy trong main trước khi tạo task consumer nên chưa có thread đợi nhận, kết quả false. Sau khi hai tasks được submit, sender và receiver rendezvous qua `put/take`, dù thứ tự worker start khác nhau. `Future.get()` đợi cả hai hoàn tất; không có item lưu trữ trong queue.

**Liveness:** Một `SynchronousQueue.put()` có thể chờ mãi nếu không có consumer, và `take()` có thể chờ mãi nếu không có producer. Với thread pool chỉ có **một worker**, nếu producer chiếm worker và block ở put còn consumer cũng submit vào đúng pool ấy, có thể bị thread-starvation deadlock. Đừng coi handoff trực tiếp là giải pháp thần kỳ không cần đủ worker hoặc giao thức shutdown.

## 10. Lifecycle và shutdown: BlockingQueue không có close() chung

Một điểm dễ bỏ sót khi chuyển từ `wait/notify` sang queue: bạn không phải tự viết chờ rỗng/đầy, **nhưng vẫn phải thiết kế “không còn dữ liệu nữa”**.

`BlockingQueue` không định nghĩa một method `close()` để tự động làm mọi consumer đang chờ `take()` thoát. Nếu producer đã xong nhưng không thông báo, consumer vẫn có thể chờ vô hạn.

Các chiến lược phổ biến:
1. **Poison pill/sentinel:** gửi một giá trị đặc biệt cho mỗi consumer.
2. **Interruption:** coordinator giữ worker `Future` hoặc thread handles, gửi cancel/interrupt theo contract.
3. **Timed poll + closed flag:** consumer định kỳ kiểm tra `closed` (và drain các item còn lại), tránh chờ vô hạn.
4. **Wrapper abstraction có close:** tự định nghĩa trạng thái `closed`, giao thức đánh thức và bảo vệ atomicity của close so với enqueue.
5. **Executor lifecycle:** nếu không cần tự lập trình event-loop, có thể dùng `ExecutorService.submit` và `shutdown/awaitTermination` để quản lý task queue và worker ở tầng cao.

**Poison pill chỉ là một item**, không tự nhân bản cho N consumers. Nếu một consumer ăn pill rồi thoát, N-1 consumers khác vẫn có thể đang đợi.

### Ví dụ 4 — Kết thúc chính xác ba consumers bằng ba sentinels

Tạo file **`MultiConsumerStopDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class MultiConsumerStopDemo {
    public static void main(String[] args) throws Exception {
        int consumerCount = 3;
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(4);
        ExecutorService pool = Executors.newFixedThreadPool(4);

        AtomicInteger processed = new AtomicInteger();
        AtomicInteger total = new AtomicInteger();

        try {
            List<Future<?>> consumers = new ArrayList<>();

            for (int i = 0; i < consumerCount; i++) {
                consumers.add(pool.submit(() -> {
                    try {
                        while (true) {
                            int value = queue.take();
                            if (value == -1) {
                                return;
                            }
                            processed.incrementAndGet();
                            total.addAndGet(value);
                        }
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException("consumer interrupted", e);
                    }
                }));
            }

            Future<?> producer = pool.submit(() -> {
                try {
                    for (int i = 1; i <= 9; i++) {
                        queue.put(i);
                    }
                    for (int i = 0; i < consumerCount; i++) {
                        queue.put(-1);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("producer interrupted", e);
                }
            });

            producer.get();
            for (Future<?> consumer : consumers) {
                consumer.get();
            }

            System.out.println("processed=" + processed.get());
            System.out.println("sum=" + total.get());
            System.out.println("remaining=" + queue.size());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Chạy:

~~~bash
javac MultiConsumerStopDemo.java
java MultiConsumerStopDemo
~~~

Stdout khi không bị interruption/lỗi ngoài ý muốn:

~~~text
processed=9
sum=45
remaining=0
~~~

**Lập luận:**
- Producer gửi 9 item thật `1..9`, sau đó **đúng ba sentinel** cho ba consumer.
- Queue FIFO và producer duy nhất bảo đảm các pills được enqueue **sau** các item thật.
- Ba consumers mỗi consumer thoát ngay khi nhận một pill, không có consumer “ăn hai pill” vì đã return sau pill đầu.
- Mọi item thật được một consumer lấy một lần; `AtomicInteger` bảo vệ tổng và số item processed khi các consumer ghi đồng thời.
- Main đợi producer và tất cả consumers qua `Future.get()` rồi mới đọc kết quả.
- `1+2+...+9=45`, nên output không phụ thuộc consumer nào lấy phần tử nào.
- Pool có bốn worker: ba consumer có thể chờ và producer vẫn có worker để gửi dữ liệu. Nếu dùng pool chỉ một worker và submit consumers trước, producer có thể không bao giờ có cơ hội chạy.

### Những điều poison pill không giải quyết

- Nếu producer bị lỗi **trước khi enqueue pills**, consumers có thể treo. Coordinator phải có đường hủy/wakeup độc lập.
- Với nhiều producer, **chỉ producer cuối cùng hoặc coordinator biết mọi producer đã kết thúc** mới có thể gửi terminal signal sau toàn bộ work; nếu pill đến quá sớm, consumer có thể bỏ lại work của producer khác.
- Nếu dữ liệu hợp lệ có thể bằng `-1`, sentinel int trùng dữ liệu là lỗi thiết kế. Dùng một marker/type phân biệt (sealed hierarchy, enum/record wrapper).
- Một queue bị full có thể khiến producer **block cả khi đang enqueue pills**. Do đó cần deadline/cancellation khi shutdown.
- Nếu một consumer đã chết vì lỗi trước khi nhận pill, pill có thể ở lại hoặc khiến các consumers còn lại xử lý sai termination count.
- Queue đảm bảo dequeue item một lần trong các thao tác bình thường, **không** đảm bảo business processing exactly-once nếu worker chết sau take mà trước commit. Cần ack/retry/durable queue và idempotency khi yêu cầu.

## 11. Ví dụ 5 — Tự phối hợp bằng monitor: có thể đúng nhưng phức tạp hơn

Để so sánh công bằng, sau đây là một **monitor bounded buffer đúng cho happy path**, không cố tình viết sai. Nó dùng `ArrayDeque`, `synchronized`, `while`, `wait()` và `notifyAll()`. Như vậy ta thấy chính xác phần code mà BlockingQueue giúp ẩn đi.

Tạo file **`ManualMonitorBufferDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.concurrent.atomic.AtomicInteger;

public class ManualMonitorBufferDemo {
    static final class BoundedBuffer {
        private final ArrayDeque<Integer> items = new ArrayDeque<>();
        private final int capacity;

        BoundedBuffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity <= 0");
            }
            this.capacity = capacity;
        }

        synchronized void put(int value) throws InterruptedException {
            while (items.size() == capacity) {
                wait();
            }
            items.addLast(value);
            notifyAll();
        }

        synchronized int take() throws InterruptedException {
            while (items.isEmpty()) {
                wait();
            }
            int value = items.removeFirst();
            notifyAll();
            return value;
        }

        synchronized int size() {
            return items.size();
        }
    }

    public static void main(String[] args) throws Exception {
        BoundedBuffer buffer = new BoundedBuffer(2);
        AtomicInteger sum = new AtomicInteger();

        Thread producer = new Thread(() -> {
            try {
                for (int i = 1; i <= 5; i++) {
                    buffer.put(i);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                for (int i = 0; i < 5; i++) {
                    sum.addAndGet(buffer.take());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println("sum=" + sum.get());
        System.out.println("remaining=" + buffer.size());
    }
}
~~~

Chạy:

~~~bash
javac ManualMonitorBufferDemo.java
java ManualMonitorBufferDemo
~~~

Stdout trên đường không bị interruption ngoài ý muốn:

~~~text
sum=15
remaining=0
~~~

**Tại sao nó đúng trong demo?**
- `put`/`take` synchronized trên cùng instance `BoundedBuffer`, nên `wait`/`notifyAll` sử dụng cùng monitor.
- Predicate `size==capacity` và `isEmpty` được đọc/ghi dưới lock, không có lost-notification race giữa check và wait.
- `wait()` nhả monitor khi chờ; lúc tỉnh lấy lại monitor rồi **kiểm tra lại bằng while**.
- `notifyAll()` đánh thức waiters để họ tự xác minh predicate, không dự đoán ai tỉnh trước.
- Buffer FIFO bằng `addLast` + `removeFirst`, capacity 2; 5 phần tử `1..5` cho tổng 15.
- Main `join` cả hai threads trước khi đọc biến cộng và buffer size.

**Vẫn chỉ là một ví dụ tối giản**: chưa có `offer` không chặn, `poll(timeout)`, `put(timeout)`, close, poison-pill protocol nhiều consumers, chính sách xử lý producer failure, fairness, structured diagnostics hoặc saturation management.

### Khi nào tự viết Condition/monitor vẫn hợp lý?

Có, nếu đồng bộ hóa gắn với **một invariant riêng không thể diễn đạt bằng queue**. Ví dụ:
- Một máy trạng thái cần đợi nhiều điều kiện liên quan `state == RUNNING && count >= N`.
- Cần atomic transition nhiều field dưới cùng lock.
- Cần đợi chính trạng thái thay đổi, **không phải một item được truyền**.
- Cần tín hiệu phát tới mọi listener mà không tiêu thụ từng message (broadcast).

Trong các trường hợp đó `ReentrantLock + Condition` hoặc `synchronized + wait/notifyAll` có thể là abstraction đúng. Nhưng nếu chỉ đang lặp lại buffer producer–consumer thông thường, hãy ưu tiên BlockingQueue chuẩn.

## 12. BlockingQueue hay synchronizer khác? Chọn theo đối tượng chờ

| Bài toán | Abstraction nên xem trước | Vì sao |
| --- | --- | --- |
| Chuyển các item từ producers sang consumers; consumer chờ khi rỗng | **`BlockingQueue`** | Dữ liệu và cơ chế wait cùng một abstraction |
| Giới hạn buffer và tạo backpressure cho producers | **Bounded BlockingQueue** | Có capacity + `put/offer(timeout)` |
| Một thread đợi sự kiện xảy ra đúng một lần | `CountDownLatch` | Chờ signal, không cần một item bị lấy khỏi queue |
| Một nhóm thread cùng chờ để qua nhiều pha | `CyclicBarrier` / `Phaser` | Phối hợp phase giữa nhiều participants |
| Giới hạn số công việc truy cập tài nguyên chung | `Semaphore` | Quản lý số permit, không phải FIFO job queue |
| Một thread đợi một kết quả tính toán | `Future` / `CompletableFuture` | Kết quả và failure/cancellation của computation |
| Một lock phối hợp condition tùy biến | `ReentrantLock + Condition` | Bảo vệ invariant state riêng |
| Muốn chạy nhiều `Runnable/Callable` bằng worker pool | `ExecutorService` | Quản lý scheduling, worker, Future và lifecycle |
| Event broadcast cho nhiều subscribers | Mô hình pub/sub/callback phù hợp | Queue dùng nhiều consumers thường chia item, không broadcast |
| Muốn luôn nhận **giá trị mới nhất** thay vì backlog | `AtomicReference`/`volatile` + signal | Queue giữ các item cũ, không tự coalesce |
| Cần xử lý message bền vững sau restart | Persistent broker/storage protocol | BlockingQueue thuần in-memory, không durable |

### Queue không thay semaphore

`Semaphore(3)` cho phép tối đa ba threads đồng thời giữ permit, bất kể “item công việc” có hay không. `ArrayBlockingQueue(3)` giới hạn **ba item trong buffer**, chứ **không** giới hạn ba task đang xử lý sau khi chúng đã `take` item ra khỏi queue. Nếu cần giới hạn số HTTP requests đang in-flight, có thể cần semaphore (hoặc bounded executor/admission control) chứ không phải chỉ một queue.

### Queue không thay CountDownLatch

`CountDownLatch.await()` đợi một tín hiệu **không tiêu thụ** cho tất cả waiters. Nếu thay bằng một queue chứa đúng một token, consumer đầu tiên `take` sẽ lấy mất token; các waiters còn lại không tự vượt qua. Điều này làm sai semantics broadcast/one-time release.

### Queue không thay Future

Một `Future<T>` đại diện một computation và cung cấp outcome với `get()`, `ExecutionException`, `CancellationException` và completion semantics. Một BlockingQueue có thể truyền một `Result` được wrapper tự thiết kế, nhưng phải tự làm failure/cancel/correlation. Nếu chỉ muốn chạy callable rồi lấy kết quả, `executor.submit(callable)` thường đơn giản hơn tự lập trình request/result queues.

## 13. Ordering: FIFO dequeue không bảo đảm FIFO completion

Giả sử producer enqueue A rồi B vào FIFO queue. Hai consumers có thể:
- Consumer 1 take A, xử lý 500 ms.
- Consumer 2 take B, xử lý 10 ms.
- B được commit trước A.

~~~text
FIFO enqueue/dequeue:   A -> B
Processing workers:     A ---------finish
                         B -finish
Commit order:           B -> A   (có thể)
~~~

Nếu business cần output đúng thứ tự, hãy thiết kế **sequence number, reorder buffer, serial commit**, hoặc một consumer xử lý tuần tự. Queue không tự đồng bộ “task A hoàn tất trước task B”.

Với nhiều producers thực hiện `put` đồng thời, thứ tự enqueue hiệu lực do scheduling và synchronization thực tế quyết định. Nó không tự là thứ tự “request xuất hiện trong logs” nếu các timestamps/logs được tạo ngoài điểm enqueue.

Với `PriorityBlockingQueue`, dequeue order dựa trên comparator, không phải FIFO. Với `SynchronousQueue`, không có buffer; một lần put được match với take tương ứng. Với `DelayQueue`, item chỉ sẵn sàng khi delay hết hạn.

**Đừng dùng `size()` hoặc `isEmpty()` như một lock:**

~~~java
if (!queue.isEmpty()) {
    E item = queue.remove();
}
~~~

Đây là snippet rủi ro khi nhiều consumers: giữa `isEmpty` và `remove`, thread khác có thể lấy phần tử cuối. Nếu chỉ muốn claim item khi có, dùng `poll()`; nếu muốn đợi, dùng `take()`.

## 14. Boundedness, backpressure và giới hạn bộ nhớ

Một câu hỏi quan trọng hơn “queue nào nhanh nhất” là **“điều gì xảy ra khi producer nhanh hơn consumer 10 phút?”**

Nếu mỗi giây nhận 10.000 items nhưng consumer xử lý 8.000 items, backlog tăng khoảng 2.000 items/s. Sau 10 phút là khoảng 1,2 triệu items, chưa tính bộ nhớ cho payload, node, object graph, metrics. Queue không bounded có thể tiêu thụ rất nhiều RAM trước khi bị lỗi.

Với bounded queue capacity `C`:
- Chỉ tối đa C items đang đợi trong queue (không bao gồm những items consumers đã take và đang xử lý).
- `put` có thể block producer lúc full.
- `offer` có thể reject ngay.
- `offer(timeout)` cho phép chờ có giới hạn.
- Caller có thể dùng queue depth, rejected count, producer wait time để điều tiết.

**Không đồng nhất capacity với toàn bộ in-flight requests.** Nếu có 100 consumers đang xử lý và queue capacity 100, có thể có tới khoảng 200 items vừa đang xử lý vừa đang đợi (chưa tính những request chưa vào queue và các stage khác).

### Backpressure nên lan ngược lên upstream

Một bounded queue chỉ tạo ra áp lực tại nơi producer gọi `put/offer`. Nếu upstream chấp nhận request vô hạn rồi tạo một task chờ đưa vào queue cho mỗi request, backlog vẫn tồn tại **ở thread/task layer thay vì trong queue**. Cần admission control tại đúng ranh giới, timeout và bounded executor hoặc cơ chế điều tiết đầu vào.

### Các loại lỗi và quyết định phải rõ

- **Full queue:** reject, retry, shed load, hoặc backpressure.
- **Empty queue:** wait, timed poll hoặc idle scheduler.
- **Shutdown:** không nhận item mới, drain hay discard theo policy.
- **Producer failure:** làm sao consumer nhận được trạng thái kết thúc?
- **Consumer failure:** item đã take nhưng chưa xử lý xong được retry không?
- **Timeout/cancellation:** caller không còn cần kết quả; có cần gỡ item khỏi queue không?
- **Duplicate:** retry có thể khiến cùng business item xuất hiện nhiều lần.
- **Poison-pill admission:** queue đầy có thể block lúc gửi terminal messages.
- **Durability:** in-memory queue mất dữ liệu khi process chết.

Nếu nghiệp vụ cần **at-least-once delivery, retry và durable acknowledgement**, BlockingQueue thuần không phải message broker có persistent log. Một worker `take` item rồi crash có thể làm item ấy mất khỏi queue dù chưa commit.

## 15. Shutdown an toàn cần giao thức ngoài queue

Với pipeline nhiều producer/consumer, hãy xem shutdown như một **state machine**:

~~~text
RUNNING
   |
   | stop accepting new items
   v
CLOSING
   |
   | producers finish / cancel
   | drain outstanding items nếu policy yêu cầu
   | notify consumers qua sentinel/close/interrupt
   v
STOPPED
~~~

Một chính sách graceful-drain thường thực hiện:
1. Không nhận thêm producers mới.
2. Đợi hoặc hủy producers đang chạy trong deadline.
3. Đảm bảo không có item mới được enqueue **sau** terminal markers.
4. Đưa terminal signal cho đúng số consumers hoặc dùng close protocol.
5. Đợi consumers thực sự thoát và cleanup, có deadline cho lỗi/treo.
6. Shutdown executor đúng ownership.

Không tùy tiện `shutdownNow()` ngay khi queue hết item nếu consumer vẫn phải commit công việc đã take. `ExecutorService.shutdown()` ngừng nhận task mới nhưng cho task đã submit chạy tiếp; `shutdownNow()` chỉ best-effort interrupt. Cả hai không tự tạo “closed state” cho `BlockingQueue` mà code của bạn giữ.

### Poison pill không nên bị nhầm với exception

Một pill là **dữ liệu theo một quy ước đặc biệt**. Nếu bạn cần phân biệt hết nguồn thành công, lỗi, cancel và retryable failure, hãy định nghĩa wrapper như:

~~~java
sealed interface Event permits Data, End, Failure {}
record Data(int id) implements Event {}
record End() implements Event {}
record Failure(String reason) implements Event {}
~~~

Đây là snippet định nghĩa sealed hierarchy Java 17; không phải file độc lập. Caller quyết định `End` có nghĩa graceful stop còn `Failure` có nghĩa ngừng với lỗi. Nếu nhiều consumers dùng một queue, nên thiết kế riêng routing/broadcast của terminal messages, không mặc định một marker cho cả nhóm.

## 16. Lưu ý về cancellation và interrupts

Khi một thread đang ở `take/put`, `Thread.interrupt()` có thể khiến blocking operation ném `InterruptedException`. Nhưng:
- Nếu task bắt exception rồi **tiếp tục loop vô điều kiện**, cancellation có thể bị vô hiệu.
- `Thread.interrupted()` (static) đọc và **xóa** interrupt status của thread hiện tại; `isInterrupted()` chỉ đọc.
- Nếu method có thể khai báo `throws InterruptedException`, thường propagate để coordinator quyết định.
- Nếu không thể propagate, restore flag bằng `Thread.currentThread().interrupt()` và **thoát theo policy**.
- `Future.cancel(true)` yêu cầu interrupt runner ở những implementation tương ứng, nhưng không bảo đảm mọi I/O/CPU loop dừng tức thì.
- Một task đã take item rồi bị hủy cần xác định **ownership của item**: retry, chuyển trả queue hay ghi failure. Tự `queue.offer(item)` trong finally có thể fail nếu queue full và cũng có nguy cơ duplicate nếu commit đã thành công.

Không dùng `Thread.stop()` để hủy cưỡng bức. Hủy an toàn phải giữ invariants và resource cleanup.

### Timeout khi đợi không đồng nghĩa task đã bị hủy

`queue.poll(timeout)` trả null khi hết thời gian chờ item, nhưng thread có thể tiếp tục xử lý việc khác. `future.get(timeout)` timeout chỉ giới hạn caller chờ một computation. Cần xác định **deadline toàn pipeline**, không tái cấp thời gian chờ ở mỗi stage và không suy remote side effect được rollback.

### Nếu một consumer đã nhận item nhưng xử lý thất bại?

Queue đã remove item ở thời điểm `take()` thành công. Không có `ack/nack` tích hợp trong interface `BlockingQueue`. Nếu cần retry/at-least-once:
- Gói item vào trạng thái task có ID.
- Có một owner/coordinator theo dõi in-flight.
- Định nghĩa retry policy và chống duplicate bằng idempotency.
- Với durability vượt process lifetime, dùng persistent storage/broker/giao thức phù hợp.

Một queue trong RAM chỉ là synchronizer/data structure; không tự giải quyết transaction delivery semantics.

## 17. Vì sao không dùng một queue cho mọi dạng tín hiệu?

Sự tiện lợi của `take` có thể khiến lập trình viên dùng queue như một “đường hầm truyền mọi trạng thái”. Điều này làm coupling và deadlock khó chẩn đoán.

**Trường hợp một sự kiện đã xảy ra:** dùng `CountDownLatch` để nhiều thread cùng vượt qua khi count về 0. Queue chỉ chuyển một token cho một taker.

**Trường hợp cần một hàng đợi công việc:** dùng `BlockingQueue` hoặc submit tasks cho `ExecutorService`. Nếu bạn đang tự tạo N worker threads, tự dequeue `Runnable` và tự quản lý shutdown, có thể bạn đang viết lại một executor.

**Trường hợp giới hạn truy cập DB connection:** dùng `Semaphore` hoặc connection pool có contract rõ. Queue capacity hạn chế item chờ, không tự giới hạn số consumer đang giữ DB connection.

**Trường hợp nhiều điều kiện state phức tạp:** dùng `ReentrantLock + Condition` để giữ invariant trong một critical section; queue chỉ biểu diễn một loại dữ liệu/ordering, không transaction nhiều field.

**Trường hợp broadcast:** queue multi-consumer thông thường **phân phối** mỗi item cho một consumer, không broadcast mỗi item cho tất cả; cần pub/sub với nhiều per-subscriber queues hoặc abstraction phù hợp.

**Trường hợp “luôn lấy giá trị mới nhất”:** một `AtomicReference` có publication và notification phù hợp có thể tốt hơn queue tích lũy giá trị cũ. Nếu cần coalescing, đừng để backlog chứa mọi phiên bản vô ích.

## 18. Kiểm thử producer–consumer không bị flaky

Đừng chỉ dùng `Thread.sleep(100)` để “đợi consumer bắt đầu”. Scheduler không bảo đảm thread đã tới vị trí mong muốn sau thời gian đó. Test nên dùng:
- `CountDownLatch` xác nhận producer/consumer đã vào một đoạn cụ thể.
- `Future.get(timeout)` để test có thời hạn thay vì treo toàn test suite.
- Bounded queue nhỏ (capacity 1 hoặc 2) để ép đường full/empty.
- `AtomicInteger` hoặc result reduction khi cần đếm multi-consumer.
- Assertion trên **tập item và tổng số lần nhận**, không đoán thread nào xử lý item nào.
- Test interrupt khi consumer đang `take` và producer đang `put`.
- Test producer thất bại trước terminal signal.
- Test multiple consumers và đúng số pills hoặc close protocol.
- Test shutdown khi queue đang full.
- Test producer thêm sau khi close hoặc một pill được enqueue quá sớm.
- Test cancellation sau khi item đã take nhưng trước commit.
- Test không có leak permits/locks, không còn blocked worker quá deadline.

### Những kịch bản bắt buộc

| Kịch bản | Expected behavior |
| --- | --- |
| Producer nhanh, consumer chậm, queue bounded | `put` có thể đợi; không vượt capacity |
| Queue rỗng, consumer dùng `take` | Consumer chờ, không busy spin |
| Queue full, producer dùng `offer` | Trả false, caller xử lý reject |
| Queue full, timed offer | Đợi tối đa thời hạn theo contract, trả false nếu không có chỗ |
| Có N consumers, chỉ 1 poison pill | Không bảo đảm cả N consumers thoát |
| Producer chết trước pill | Cần coordinator cancellation/close để tránh treo |
| Multi-consumer và FIFO queue | Dequeue theo queue order, completion order có thể khác |
| Producer handoff mutable object rồi sửa tiếp | Cần ownership/synchronization |
| Một consumer chết sau take | Item có thể mất nếu không có retry/ack ngoài queue |
| Shutdown executor khi workers vẫn chờ | Phải có protocol xử lý interruption và cleanup |

### Performance test đúng trọng tâm

So sánh `ArrayBlockingQueue`, `LinkedBlockingQueue(capacity)`, `SynchronousQueue` hoặc nonblocking queue **trên cùng workload thực**:
- Tốc độ producer/consumer, burst size và số cores.
- Throughput (items/s), p95/p99 queue wait và end-to-end latency.
- CPU utilization khi idle: busy-spin vs blocking.
- Allocation/GC và memory theo backlog.
- Count rejected/timed-out/cancelled.
- Time to graceful shutdown.
- Fairness/starvation nếu nhiều producers/consumers.

Không kết luận “ArrayBlockingQueue luôn nhanh nhất” hoặc “LinkedBlockingQueue luôn nhanh hơn” từ một thử nghiệm nhỏ. Dùng JMH hoặc benchmark harness thích hợp; luôn kiểm tra correctness và làm rõ môi trường JVM/hardware.

## 19. Những lỗi phổ biến khi áp dụng BlockingQueue

1. **Dùng `ArrayList`/`ArrayDeque` đồng thời mà không đồng bộ.** Có data race/corruption; dùng đúng concurrent/BlockingQueue hoặc lock.
2. **Tự viết `wait()` với `if`.** Spurious wakeup và cạnh tranh sau notify có thể làm predicate sai; dùng while dưới cùng monitor.
3. **Đọc condition ngoài lock rồi mới wait.** Dễ missed notification; bảo vệ check–wait cùng giao thức đồng bộ.
4. **Dùng `notify()` tùy tiện khi có nhiều loại waiter.** Có thể đánh thức nhóm không tiến triển; cân nhắc notifyAll/Conditions đúng.
5. **Cho rằng `BlockingQueue` có `close()`.** Không có method close chung; phải thiết kế lifecycle.
6. **Cho rằng `take()` trả null báo kết thúc.** `take()` chờ tới khi có item, không dùng null sentinel.
7. **Đặt null vào BlockingQueue.** Không được phép; null dành làm giá trị “không có item” của `poll/peek`.
8. **Dùng `put()` trên unbounded queue và mong có backpressure nhỏ.** Không có capacity đủ nhỏ để tạo áp lực theo yêu cầu; cấu hình bounded.
9. **Dùng `offer()` nhưng bỏ qua false.** Item có thể bị từ chối mà hệ thống vẫn báo thành công.
10. **Busy-poll bằng vòng lặp `poll()` liên tục.** Có thể đốt CPU; dùng take/timed poll hoặc scheduler.
11. **Dùng một pill cho nhiều consumers.** Chỉ một consumer nhận pill; những consumer khác có thể treo.
12. **Producer phát pill trước khi mọi producers hoàn tất.** Một consumer có thể kết thúc trước khi hết work.
13. **Dùng một sentinel trùng giá trị dữ liệu thật.** Consumer có thể bỏ nhầm dữ liệu; dùng type marker.
14. **Giả định FIFO queue bảo đảm FIFO processing completion.** Nhiều consumers có thể xử lý xong đảo thứ tự.
15. **Dùng `isEmpty` rồi `remove` như một operation atomic.** Check-then-act race; dùng poll/take.
16. **Dùng `PriorityBlockingQueue` làm bounded work queue.** Không có hard capacity do constructor cung cấp.
17. **Dùng `SynchronousQueue` với một worker producer block còn consumer cũng xếp sau trong cùng pool.** Có thể starvation deadlock.
18. **Ngừng producer nhưng không thông báo consumer.** Consumer tiếp tục chờ vô hạn.
19. **Nuốt `InterruptedException`.** Cancel/shutdown không được tôn trọng.
20. **Tưởng handoff tự deep-freeze payload.** Mutable object tiếp tục bị sửa vẫn không an toàn.
21. **Tưởng queue bảo đảm exactly-once business processing.** Item đã take có thể mất khi consumer chết trước commit.
22. **Không bounded backlog tại upstream.** Queue đầy nhưng vô hạn request threads đứng chờ put vẫn gây overload.
23. **Dùng queue để giải quyết barrier/broadcast.** Sai semantics; dùng đúng synchronizer.
24. **Thay executor bằng một hệ thống worker tự viết khi không cần.** Tăng trách nhiệm xử lý queue, failures, lifecycle và scheduling.
25. **Không đo peak writes/bursts và shutdown latency.** Thiết kế có thể hoạt động ở demo nhưng sụp dưới tải thực.

## 20. Checklist ra quyết định

Trước khi chọn BlockingQueue, trả lời:

1. Có thật sự **các item được chuyển từ producer sang consumer** không?
2. Consumer phải **đợi khi rỗng** hay có thể thăm dò nonblocking?
3. Producer phải **đợi khi đầy**, reject/drop hay retry?
4. Có cần **capacity cứng** cho backlog không?
5. Thứ tự thực sự cần: FIFO, priority, delayed, LIFO hay hoàn tất theo sequence?
6. Nhiều consumers có được chia các items hay mỗi item cần broadcast tới tất cả?
7. Payload có immutable hoặc chuyển ownership sau enqueue không?
8. Có cần snapshot/multi-field transaction thay vì chỉ queue item không?
9. Producer và consumer có được bảo đảm có đủ worker để tiến triển?
10. Có deadline/cancellation cho `put/take` đang chờ không?
11. Khi producer lỗi, consumer được thông báo thế nào?
12. Nếu nhiều producers, ai có quyền phát terminal marker cuối?
13. Với N consumers, có đủ pills hoặc close protocol không?
14. Nếu queue full lúc shutdown, có đường tiến triển không?
15. Item đã take nhưng xử lý fail có cần retry/durable ack không?
16. Có cần backpressure lên upstream để không phình backlog ở nơi khác?
17. Có phải một event signal cho tất cả waiters, không phải queue? Nếu vậy, dùng `CountDownLatch`.
18. Có phải giới hạn số resource in-use? Nếu vậy, xem `Semaphore`.
19. Có cần nhiều phases/barrier? Nếu vậy, xem `Phaser/CyclicBarrier`.
20. Có đơn giản chỉ là `Callable` chạy nền? Nếu vậy, xem `ExecutorService.submit`.
21. Đã test race và worker failure bằng latch/timed get chưa?
22. Đã đo throughput, wait latency, memory và shutdown dưới tải chưa?

## 21. Câu hỏi tự kiểm tra và đáp án

1. **BlockingQueue thay thế phần nào của monitor producer–consumer?** Queue data structure, đồng bộ thêm/lấy, chờ rỗng/đầy, wakeup và visibility.
2. **Khi queue rỗng, `take()` trả gì?** Nó chờ tới khi có item hoặc bị interrupt theo contract, không trả null để báo rỗng.
3. **Khi queue rỗng, `poll()` trả gì?** `null` ngay, không chờ.
4. **Với queue bounded đã đầy, `offer(e)` trả gì?** `false`.
5. **Với queue bounded đã đầy, `put(e)` làm gì?** Có thể block đợi có chỗ hoặc bị interrupt.
6. **`offer(e,t,u)` hết hạn trả gì?** `false` nếu không thêm được trước thời hạn.
7. **Có thể dùng `null` làm poison pill không?** Không; BlockingQueue không cho phần tử null.
8. **Vì sao `wait` phải nằm trong while?** Spurious wakeup và cạnh tranh có thể làm predicate sai khi thức dậy.
9. **Vì sao check ngoài lock rồi wait nguy hiểm?** Producer có thể thay đổi state/notify giữa check và wait, gây missed signal.
10. **Có thể gọi BlockingQueue rồi coi payload mutable tự thread-safe không?** Không; cần ownership/immutable hoặc synchronization riêng.
11. **Có memory happens-before từ producer put tới consumer take không?** Có, theo contract của BlockingQueue với object được truyền.
12. **ArrayBlockingQueue có capacity tùy chọn không giới hạn không?** Không; capacity cố định theo constructor.
13. **LinkedBlockingQueue không truyền capacity mặc định lớn bao nhiêu?** `Integer.MAX_VALUE`.
14. **SynchronousQueue có buffer không?** Không, capacity 0; yêu cầu rendezvous producer–consumer.
15. **PriorityBlockingQueue có FIFO như ArrayBlockingQueue không?** Không; theo comparator/natural priority.
16. **PriorityBlockingQueue có bounded backlog theo constructor capacity không?** Không.
17. **Queue FIFO có bảo đảm kết quả của các consumer được commit FIFO không?** Không; xử lý song song có thể đảo thứ tự hoàn tất.
18. **Một poison pill có dừng mọi N consumers không?** Không; một pill thường chỉ bị một consumer take.
19. **Nếu producer chết trước pill, cần gì?** Coordinator/close/cancel/timeout để consumer không treo.
20. **BlockingQueue có close() chung không?** Không.
21. **Item đã take rồi consumer chết có tự quay lại queue không?** Không; cần retry/ack policy.
22. **Queue capacity C có giới hạn C active tasks sau take không?** Không; capacity chỉ giới hạn items đang nằm trong queue.
23. **Chờ một tín hiệu one-shot cho nhiều threads nên dùng gì?** `CountDownLatch`.
24. **Giới hạn số connection dùng đồng thời nên cân nhắc gì?** `Semaphore`/resource pool có contract phù hợp.
25. **Chạy một Callable và lấy kết quả nên xem gì?** `ExecutorService.submit`/`Future`.
26. **Dùng queue thay broadcast event có đúng không?** Không mặc định; consumers chia items chứ không nhận tất cả.
27. **`poll()==null` có nghĩa producer đã đóng chưa?** Không; chỉ hiện tại không có item sẵn sàng.
28. **`future.get(timeout)` timeout có tự cancel producer không?** Không; cần quyết định cancel riêng.
29. **Vì sao unbounded queue có nguy cơ OOM?** Producers có thể tích lũy item nhanh hơn consumers xử lý.
30. **Khi nào nên tự viết Condition thay queue?** Khi bài toán là invariant state riêng hoặc nhiều predicates không biểu diễn đúng bằng item handoff.

## 22. Tổng kết

**Dùng `BlockingQueue` khi bạn thật sự cần một hàng đợi công việc hoặc dữ liệu giữa các threads**, đặc biệt khi consumer phải đợi rỗng, producer cần chờ hoặc nhận reject khi đầy, và bạn muốn tránh tự viết các giao thức `wait/notify/Condition` vốn dễ gây race, missed notification và spurious wakeup bugs.

- Chọn **`ArrayBlockingQueue`** khi muốn bounded FIFO và backpressure rõ ràng.
- Chọn **`LinkedBlockingQueue(capacity)`** nếu phù hợp với linked FIFO; đừng vô tình để capacity gần vô hạn khi có nguy cơ backlog.
- Chọn **`SynchronousQueue`** nếu cần handoff trực tiếp, không buffer.
- Chọn **`PriorityBlockingQueue`** hoặc **`DelayQueue`** khi thứ tự ưu tiên/thời gian đến hạn là yêu cầu, lưu ý boundedness và ordering khác FIFO.
- Dùng **`offer/poll`** khi không được phép chờ vô thời hạn; **`put/take`** khi muốn block và đã thiết kế được lifecycle.
- Không quên **interruption, poison pill/close protocol, capacity, backpressure, resource ownership và error handling**.

Nếu điều bạn cần **không phải item handoff**, hãy chọn đúng synchronizer: `CountDownLatch` cho one-time signal, `Phaser` cho phases, `Semaphore` cho permits, `Condition` cho invariant state, hoặc `Future/ExecutorService` cho kết quả một computation. BlockingQueue **giảm gánh nặng phối hợp luồng**, nhưng không tự giải quyết business transaction, retry, durable messaging, exactly-once processing hay graceful shutdown.

## Tài liệu tham khảo Java SE 17

- [BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): bảng method, happens-before, không cho null, thiếu close protocol chung.
- [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO và fairness.
- [LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): optional capacity và FIFO.
- [SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): rendezvous zero-capacity.
- [PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): priority, không bounded, tie ordering.
- [DelayQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/DelayQueue.html): delayed items.
- [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html): thao tác ở hai đầu.
- [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): one-shot synchronization.
- [Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): giới hạn permits.
- [Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): wait/signal tùy predicate.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý task/worker/lifecycle.
- [Object.wait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#wait()): monitor wait, spurious wakeup và monitor ownership.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): benchmark concurrency có kiểm soát.
