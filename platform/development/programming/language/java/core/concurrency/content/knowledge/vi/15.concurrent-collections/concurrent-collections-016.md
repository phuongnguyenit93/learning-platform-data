# TransferQueue và BlockingDeque: chuyển giao trực tiếp và thao tác hai đầu

Trong Java Concurrency, `BlockingQueue<E>` cho phép nhiều thread truyền dữ liệu qua một hàng đợi có cơ chế đồng bộ và chờ. Hai interface mở rộng giúp giải quyết những bài toán đặc biệt:

- **`TransferQueue<E>`** bổ sung khái niệm **chuyển giao tới consumer**: producer có thể chọn giữa đưa phần tử vào queue như thông thường và **đợi cho đến khi một consumer thực sự nhận phần tử đó**.
- **`BlockingDeque<E>`** (double-ended queue) bổ sung **hai đầu vào/ra**: producer và consumer có thể thêm/lấy từ đầu hoặc cuối, theo FIFO, LIFO, hoặc một giao thức ưu tiên đơn giản do ứng dụng quyết định.

Implementation thường dùng của JDK:

- `LinkedTransferQueue<E>`: concurrent queue không có capacity giới hạn cấu hình, triển khai `TransferQueue<E>`.
- `LinkedBlockingDeque<E>`: concurrent deque có thể **bounded** bằng capacity trong constructor; nếu không truyền, capacity theo API là `Integer.MAX_VALUE`.

Hai interface này **khác `SynchronousQueue`** và không thay thế mọi `BlockingQueue` khác. Muốn dùng đúng cần hiểu rõ **enqueue**, **dequeue**, **handoff**, **xử lý xong**, **backpressure**, **thứ tự thực thi** và **lifecycle**. Bài tập trung hoàn toàn vào Java/JDK concurrency, dùng ví dụ độc lập với Java 17+, không phụ thuộc framework bên ngoài.

## 1. Từ BlockingQueue đến hai cơ chế mở rộng

Xét pipeline producer–consumer đơn giản:

```text
Producer                  Queue                    Consumer
---------                 -----                    --------
tạo item  ------------>   lưu hoặc handoff  ---->  nhận item
                                                     |
                                                     v
                                               xử lý nghiệp vụ
```

Có **ba mốc khác nhau**:

1. **Đã gửi vào queue:** queue đã chấp nhận item, nhưng chưa chắc consumer nhận.
2. **Đã được consumer lấy ra:** consumer đã thực hiện thao tác nhận hợp lệ; chưa chắc xử lý xong.
3. **Đã xử lý xong:** consumer đã hoàn thành logic nghiệp vụ và cleanup tương ứng.

`TransferQueue.transfer(e)` hỗ trợ đợi tới **mốc thứ 2**, chứ **không tự tạo acknowledgement cho mốc thứ 3**. `BlockingDeque` không bổ sung acknowledgement; nó bổ sung **quyền chọn đầu nào** để gửi hoặc nhận.

Khi có nhiều producer/consumer, việc chọn đầu và thời điểm handoff là một phần của thiết kế đồng bộ. Những khái niệm này không nên được đồng nhất với “task Future đã hoàn tất” hoặc “transaction đã commit”.

## 2. TransferQueue là gì?

`TransferQueue<E>` **extends `BlockingQueue<E>`**. Nó giữ những phương thức quen thuộc như `offer`, `put`, `take`, `poll`, đồng thời bổ sung:

| API của TransferQueue | Ý nghĩa |
|---|---|
| `transfer(e)` | Chuyển phần tử tới một consumer, **chờ** cho đến khi consumer nhận. Có thể bị interrupt. |
| `tryTransfer(e)` | **Chỉ** chuyển trực tiếp nếu có consumer phù hợp đang đợi; không chờ. Trả `true` nếu chuyển được, `false` nếu chưa có ai nhận ngay. |
| `tryTransfer(e, timeout, unit)` | Đợi tối đa khoảng thời gian cho consumer nhận, trả `true` khi handoff, `false` nếu hết hạn. Có thể ném `InterruptedException`. |
| `hasWaitingConsumer()` | Trả thông tin consumer có thể đang chờ để nhận trực tiếp, **mang tính thời điểm**. |
| `getWaitingConsumerCount()` | Số lượng consumer đang đợi **ước lượng**, dùng để giám sát/heuristic, không để đảm bảo một giao dịch tiếp theo. |

Các method `take()` và `poll()` của `BlockingQueue` vẫn là phía **consumer**. Nếu producer gọi `transfer(e)` trong lúc chưa có consumer, nó có thể phải đợi và phần tử có thể được đăng ký trong queue để consumer lấy sau; khi consumer lấy, transfer mới có thể hoàn tất.

### offer(), put() và transfer() không tương đương

Một `LinkedTransferQueue<String>` có thể nhận phần tử bằng:

```java
queue.offer("event");      // Enqueue; không đợi consumer xử lý/lấy.
queue.put("event");        // Với LinkedTransferQueue, không chờ vì queue đầy.
queue.transfer("event");   // Đợi một consumer nhận phần tử.
```

Đây là trích đoạn cần khai báo `queue` và xử lý `InterruptedException`. Cả ba đưa dữ liệu tới consumer theo contract nhưng **cách producer biết lúc nào được tiếp tục là khác nhau**. Không đọc `transfer()` thành “đợi consumer xử lý xong”: consumer có thể đang tính toán rất lâu sau khi lấy phần tử.

### Điều kiện của tryTransfer(e)

`tryTransfer(e)` không timeout là một giao dịch **không chờ**. Nếu không có consumer có thể nhận ngay:

- Trả `false`.
- **Không lưu item lại trong queue**.
- Không tạo một lần gửi trì hoãn sẽ tự diễn ra khi consumer xuất hiện.

Đây là khác biệt lớn với `offer(e)` trên `LinkedTransferQueue`: `offer` có thể enqueue dù chưa có consumer, còn `tryTransfer` không chờ thì chỉ thành công nếu chuyển ngay được.

## 3. LinkedTransferQueue: unbounded, trực tiếp khi có thể

`LinkedTransferQueue<E>` là implementation thread-safe của `TransferQueue<E>`, hỗ trợ nhiều producer và consumer. Những tính chất quan trọng:

- **Không có constructor capacity** để đặt bound như `ArrayBlockingQueue<>(capacity)`.
- `remainingCapacity()` là `Integer.MAX_VALUE` theo hợp đồng queue không bounded; **không có nghĩa bộ nhớ vô hạn**.
- `offer()` và `put()` không bị chặn vì đầy capacity; nếu backlog tăng quá mức vẫn có nguy cơ thiếu bộ nhớ.
- `transfer()` cung cấp cơ chế **đợi consumer nhận**, là một hình thức đồng bộ khác với enqueue thông thường.
- `tryTransfer()` không chờ phù hợp với tình huống chỉ muốn gửi nếu consumer đang sẵn sàng.
- Các phép kiểm tra như `hasWaitingConsumer()`, `getWaitingConsumerCount()` và `size()` là quan sát **có thể thay đổi ngay** khi đọc; `size()` của queue liên kết đồng thời có thể tốn công duyệt, không nên dùng làm điều kiện tính đúng của giao dịch.
- Iterator thuộc nhóm **weakly consistent**: không ném `ConcurrentModificationException` chỉ vì update đồng thời, nhưng không nên kỳ vọng snapshot cố định khi các thread đang sửa queue.

**Không dùng** `if (queue.hasWaitingConsumer()) queue.tryTransfer(e)` như một bảo đảm không thất bại: consumer có thể bị đánh thức/nhận item khác trước lần `tryTransfer`. Nếu yêu cầu là “chuyển nếu có thể ngay”, chỉ cần tin vào **giá trị trả về của `tryTransfer`**.

## 4. Ví dụ 1 — tryTransfer() và transfer() khác nhau ra sao?

Chương trình đầu tiên thử `tryTransfer` lúc chưa có consumer; phép thử phải thất bại và không enqueue. Sau đó tạo một producer gọi `transfer()`, main trở thành consumer và nhận bằng `take()`.

Tạo file **`TransferQueueBasics.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TransferQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class TransferQueueBasics {
    public static void main(String[] args) throws InterruptedException {
        TransferQueue<String> queue = new LinkedTransferQueue<>();
        System.out.println("Immediate transfer: "
                + queue.tryTransfer("not-sent"));
        System.out.println("Queue empty: " + queue.isEmpty());

        CountDownLatch producerEntered = new CountDownLatch(1);
        AtomicBoolean transferReturned = new AtomicBoolean();

        Thread producer = new Thread(() -> {
            producerEntered.countDown();
            try {
                queue.transfer("payload");
                transferReturned.set(true);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        producer.start();
        producerEntered.await();

        String received = queue.take();
        producer.join();

        System.out.println("Received: " + received);
        System.out.println("Transfer returned: "
                + transferReturned.get());
        System.out.println("Remaining: " + queue.size());
    }
}
```

```bash
javac TransferQueueBasics.java
java TransferQueueBasics
```

Kết quả trong lần chạy bình thường, không có external interrupt:

```text
Immediate transfer: false
Queue empty: true
Received: payload
Transfer returned: true
Remaining: 0
```

**Tại sao kết quả xác định?**

1. `tryTransfer("not-sent")` được gọi trước khi có bất kỳ consumer nào, vì vậy trả false và không giữ item lại.
2. Producer bắt đầu rồi gọi `transfer("payload")`. Main có thể gọi `take()` trước hay sau thời điểm producer thực sự đi vào transfer; cả hai trường hợp đều ghép cặp thành công khi hai phía có mặt.
3. `producer.join()` đợi producer kết thúc, nên `transferReturned` chắc chắn là true sau khi handoff thành công.
4. `size() == 0` vì item duy nhất đã được consumer lấy ra. Không có lời hứa rằng producer bị chặn bao nhiêu mili giây; lịch chạy thread là không xác định.

Ở hệ thống thực tế, producer nên có đường xử lý interruption và timeout nếu handoff có thể chờ lâu. Demo cố ý đơn giản để quan sát contract.

## 5. Timed transfer: giới hạn thời gian đợi consumer

Nếu không chắc consumer có xuất hiện, dùng:

```java
boolean accepted = queue.tryTransfer(
        message, 500, TimeUnit.MILLISECONDS);
```

Đây là trích đoạn, cần khai báo `queue`/`message` và bắt hoặc ném `InterruptedException`. Khi hết hạn chưa có consumer nhận, phương thức trả false. Nếu đã có handoff, trả true. Thời hạn này giới hạn **đợi consumer nhận**, không giới hạn thời gian consumer xử lý.

### Ví dụ 2 — Timed tryTransfer thất bại rồi thành công

Chương trình trước tiên đợi một thời gian rất ngắn trong khi **chưa tạo consumer**, nên chắc chắn không có người nhận. Sau đó khởi động consumer, dùng timed transfer để hai phía gặp nhau mà không phụ thuộc việc consumer đã gọi `take()` sớm hay muộn hơn producer.

Tạo file **`TransferQueueTimeout.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TransferQueue;
import java.util.concurrent.atomic.AtomicReference;

public class TransferQueueTimeout {
    public static void main(String[] args) throws InterruptedException {
        TransferQueue<String> queue = new LinkedTransferQueue<>();

        boolean noConsumer = queue.tryTransfer(
                "ignored", 30, TimeUnit.MILLISECONDS);
        System.out.println("Transfer without consumer: "
                + noConsumer);

        CountDownLatch ready = new CountDownLatch(1);
        AtomicReference<String> received = new AtomicReference<>();

        Thread consumer = new Thread(() -> {
            ready.countDown();
            try {
                received.set(queue.take());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        ready.await();

        boolean transferred = queue.tryTransfer(
                "delivered", 5, TimeUnit.SECONDS);
        consumer.join();

        System.out.println("Timed transfer succeeded: "
                + transferred);
        System.out.println("Consumer received: "
                + received.get());
        System.out.println("Queue empty: " + queue.isEmpty());
    }
}
```

```bash
javac TransferQueueTimeout.java
java TransferQueueTimeout
```

Kết quả trong lần chạy bình thường, consumer được lập lịch trong thời hạn năm giây:

```text
Transfer without consumer: false
Timed transfer succeeded: true
Consumer received: delivered
Queue empty: true
```

**Giải thích:** không có consumer nào khi gọi timed transfer đầu, nên nó trả false và không enqueue. Ở lượt hai, main được phép chờ tối đa năm giây cho consumer lấy item; `ready` giúp biết consumer đã khởi động, nhưng không tự chứng minh consumer đã đi vào `take()` đúng thời điểm. Timed transfer tự xử lý việc **đợi giao cặp**. Nếu consumer không được CPU trong thời hạn, phương thức vẫn có thể trả false, vì timeout **không bảo đảm phía khác chạy đúng hẹn**; đây là lý do ví dụ ghi rõ điều kiện scheduling.

Không dựa vào `Thread.sleep()` để “canh consumer đã chờ” rồi gọi `tryTransfer()` không timeout. Việc đó tạo test race. Nếu cần chắc chắn chuyển khi consumer đến, dùng `transfer()` hoặc timed variant với xử lý timeout.

## 6. Handoff không đồng nghĩa business completion

Một producer gọi `transfer(item)` có thể trở về ngay sau khi consumer **nhận** item, ngay cả khi consumer mới bắt đầu xử lý và chưa hoàn tất.

```text
Producer                         Consumer
--------                         --------
transfer(item) ----- handoff ---> take()
    |                                |
    v                                v
trở về                      process(item) ... còn chạy
```

Khi cần xác nhận consumer **đã xử lý xong**, phải bổ sung cơ chế acknowledgement như `CompletableFuture`, `CountDownLatch`, một Future riêng, thông điệp kết quả hoặc transaction ở tầng nghiệp vụ. Không đồng nhất queue transfer với hoàn thành giao dịch bên ngoài JVM.

### Ví dụ 3 — Transfer trả về trước khi consumer xử lý xong

Tạo file **`TransferIsNotProcessing.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TransferQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class TransferIsNotProcessing {
    public static void main(String[] args) throws InterruptedException {
        TransferQueue<String> queue = new LinkedTransferQueue<>();
        CountDownLatch received = new CountDownLatch(1);
        CountDownLatch transferReturned = new CountDownLatch(1);
        CountDownLatch finishProcessing = new CountDownLatch(1);
        AtomicReference<String> item = new AtomicReference<>();
        AtomicBoolean processed = new AtomicBoolean();

        Thread producer = new Thread(() -> {
            try {
                queue.transfer("job");
                transferReturned.countDown();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                item.set(queue.take());
                received.countDown();
                finishProcessing.await();
                processed.set(true);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();

        received.await();
        transferReturned.await();

        System.out.println("Received: " + item.get());
        System.out.println("Processed at handoff: "
                + processed.get());

        finishProcessing.countDown();
        producer.join();
        consumer.join();

        System.out.println("Processed after release: "
                + processed.get());
    }
}
```

```bash
javac TransferIsNotProcessing.java
java TransferIsNotProcessing
```

Đầu ra trong lần chạy bình thường:

```text
Received: job
Processed at handoff: false
Processed after release: true
```

Main đợi cả hai tín hiệu: consumer đã nhận và producer đã được `transfer()` cho trở về. Tuy nhiên, `finishProcessing` vẫn đóng, nên consumer **chưa thể đặt `processed=true`**. Sau khi main mở latch và `join()` consumer, xử lý mới được xác nhận hoàn tất. Bài học quan trọng: **hàng đợi xác nhận nhận item, không tự xác nhận xử lý nghiệp vụ**.

Trong production, nếu processing có thể thất bại, cần ghi trạng thái success/failure riêng thay vì một boolean. Nếu consumer đột ngột chết sau khi nhận item, producer đã có thể hoàn thành transfer mà công việc vẫn chưa hoàn tất; cần retry/acknowledgement theo hợp đồng hệ thống.

## 7. TransferQueue khác SynchronousQueue ở đâu?

Cả hai đều có khái niệm producer gặp consumer, nhưng **không giống nhau**.

| Đặc điểm | `LinkedTransferQueue` | `SynchronousQueue` |
|---|---|---|
| Có thể chứa backlog? | **Có**, nếu dùng `offer()`/`put()` hoặc phần tử transfer đang chờ người nhận. | **Không**, capacity bằng 0. |
| `put(e)` | Chèn phần tử, không phải chờ consumer chỉ vì queue đầy. | Chờ consumer nhận trực tiếp. |
| `offer(e)` không timeout | Thường enqueue thành công nếu đủ tài nguyên. | Chỉ thành công nếu có consumer đối ứng ngay. |
| `transfer(e)` | Có; chờ consumer nhận. | Không có method tên `transfer`; `put(e)` tạo handoff. |
| `tryTransfer(e)` | Có; chỉ gửi nếu consumer đang đợi. | Không có method tên `tryTransfer`; `offer(e)` có semantics handoff tương tự ở mức điều kiện nhận ngay. |
| `remainingCapacity()` | `Integer.MAX_VALUE`. | 0. |
| Khi consumer chưa xuất hiện | `offer` có thể để lại backlog; `transfer` sẽ chờ. | `put` chờ, `offer` thất bại. |

**Chọn theo contract:** cần linh hoạt giữa enqueue bình thường và đợi consumer thật sự nhận → TransferQueue. Cần **cấm mọi backlog**, chỉ cho handoff ghép cặp → SynchronousQueue.

Không được xem việc queue chưa có người nhận là lý do tự động chọn TransferQueue: nếu ứng dụng cần giới hạn tài nguyên và không chấp nhận backlog vô hạn, phải tự đặt cơ chế backpressure hoặc chọn queue bounded khác.

## 8. BlockingDeque là gì?

`Deque<E>` (double-ended queue) cho phép thêm hoặc lấy phần tử từ **cả đầu và cuối**. `BlockingDeque<E>` **extends `BlockingQueue<E>` và `Deque<E>`**, bổ sung các phương thức có thể chờ khi đầu vào đầy/đầu ra rỗng.

Hình dung:

```text
                   LinkedBlockingDeque
       HEAD                                 TAIL
        |                                     |
putFirst(v) --> [urgent] [normal1] [normal2] <-- putLast(v)
takeFirst() <-- [urgent] [normal1] [normal2] --> takeLast()
        ^                                     ^
       đầu                                   cuối
```

Phía producer có thể thêm ở đầu/càng gần `HEAD` để những consumer lấy đầu nhận item sớm hơn. Hoặc một thread có thể dùng `push/pop` để mô phỏng LIFO stack. **Đây là quyền chọn thứ tự lấy trong deque, không phải cơ chế tự ưu tiên CPU của Java scheduler.**

## 9. Bảng API hai đầu của BlockingDeque

| Chức năng | Đầu (first/head) | Cuối (last/tail) |
|---|---|---|
| Thêm, báo lỗi khi đầy | `addFirst(e)` | `addLast(e)` |
| Thêm không chờ, trả boolean | `offerFirst(e)` | `offerLast(e)` |
| Thêm, chờ có chỗ | `putFirst(e)` | `putLast(e)` |
| Thêm, chờ tối đa timeout | `offerFirst(e, timeout, unit)` | `offerLast(e, timeout, unit)` |
| Lấy, báo lỗi khi rỗng | `removeFirst()` | `removeLast()` |
| Lấy không chờ, trả null khi rỗng | `pollFirst()` | `pollLast()` |
| Lấy, chờ có item | `takeFirst()` | `takeLast()` |
| Lấy, chờ tối đa timeout | `pollFirst(timeout, unit)` | `pollLast(timeout, unit)` |
| Xem, không xóa | `peekFirst()` | `peekLast()` |
| Xóa một occurrence | `removeFirstOccurrence(e)` | `removeLastOccurrence(e)` |

Hành vi trên các overload không chờ/timeout khác nhau khi queue **đầy** hoặc **rỗng**, giống quy ước của `BlockingQueue`. Với queue bounded, `offerFirst`/`offerLast` trả false khi đầy; `putFirst`/`putLast` chờ có chỗ; `takeFirst`/`takeLast` chờ có item.

### Phương thức kế thừa của BlockingQueue dùng đầu nào?

Khi dùng `BlockingDeque` như một `BlockingQueue`, các phương thức thông thường có quy ước:

- `add(e)`, `offer(e)`, `put(e)` tương ứng **thêm cuối** (`addLast/offerLast/putLast`).
- `remove()`, `poll()`, `take()` tương ứng **lấy đầu** (`removeFirst/pollFirst/takeFirst`).
- `element()`, `peek()` xem **đầu**.

Do đó dùng `put()` và `take()` thông thường trên deque sẽ cho đường FIFO theo thứ tự enqueue thành công, trong khi dùng `push()`/`pop()` sẽ tạo đường LIFO.

## 10. LinkedBlockingDeque: bounded, hai đầu và thread-safe

`LinkedBlockingDeque<E>` là implementation có các node liên kết, hỗ trợ nhiều thread đồng thời thêm/lấy ở hai đầu, với:

```java
BlockingDeque<String> bounded = new LinkedBlockingDeque<>(100);
BlockingDeque<String> defaultCapacity = new LinkedBlockingDeque<>();
```

Đây là trích đoạn, cần import `java.util.concurrent.BlockingDeque` và `LinkedBlockingDeque`.

- Constructor có `capacity` tạo **giới hạn số phần tử** (phải lớn hơn 0), áp dụng **chung cho cả hai đầu**.
- Constructor không tham số có capacity `Integer.MAX_VALUE` theo hợp đồng; không có nghĩa bộ nhớ vô hạn.
- Hai đầu **dùng chung một tổng capacity**; không phải mỗi đầu có capacity riêng.
- Không có built-in priority comparator cho deque; ứng dụng tự quyết định đầu nào được thêm và đầu nào được lấy.
- Không có fairness constructor tương đương `ArrayBlockingQueue(capacity, true)`; không được tự suy thứ tự ưu tiên công bằng giữa các producer/consumer đang chờ.
- `null` không được phép; `pollFirst/Last()` trả null để biểu thị không có phần tử.
- Iterator là weakly consistent đối với sửa đổi đồng thời, không được coi như snapshot bất biến.
- Không có hard guarantee mọi task chèn ở đầu sẽ **chạy xong trước** các task ở cuối: các consumer có thể đã lấy item khác hoặc đang xử lý.

Nếu dung lượng ngắn, deque có thể tạo backpressure ở cả đầu và cuối. Tuy nhiên, vẫn phải chọn rõ quyền ưu tiên giữa các loại công việc: **liên tục thêm ở đầu** có thể làm những item chờ ở cuối bị đói (*starvation*).

## 11. Ví dụ 4 — FIFO, LIFO và thao tác hai đầu

Dùng một thread để kiểm tra chính xác thứ tự: đặt “urgent” ở đầu, “normal” ở cuối, thử thêm khi capacity đầy, lấy từ hai phía, rồi dùng `push/pop` như stack.

Tạo file **`BlockingDequeBasics.java`**:

```java
import java.util.concurrent.LinkedBlockingDeque;

public class BlockingDequeBasics {
    public static void main(String[] args) throws InterruptedException {
        LinkedBlockingDeque<String> deque =
                new LinkedBlockingDeque<>(3);

        System.out.println("Add normal1: "
                + deque.offerLast("normal1"));
        System.out.println("Add urgent: "
                + deque.offerFirst("urgent"));
        System.out.println("Add normal2: "
                + deque.offerLast("normal2"));
        System.out.println("Add overflow: "
                + deque.offerFirst("overflow"));

        System.out.println("Take first: " + deque.takeFirst());
        System.out.println("Take last: " + deque.takeLast());
        System.out.println("Take remaining: " + deque.takeFirst());

        deque.push("one");
        deque.push("two");
        System.out.println("Pop 1: " + deque.pop());
        System.out.println("Pop 2: " + deque.pop());
        System.out.println("Remaining: " + deque.size());
    }
}
```

```bash
javac BlockingDequeBasics.java
java BlockingDequeBasics
```

Kết quả:

```text
Add normal1: true
Add urgent: true
Add normal2: true
Add overflow: false
Take first: urgent
Take last: normal2
Take remaining: normal1
Pop 1: two
Pop 2: one
Remaining: 0
```

**Giải thích:** sau ba lần `offer`, deque từ HEAD đến TAIL là `[urgent, normal1, normal2]`. Queue đã đầy nên `offerFirst("overflow")` không làm thay đổi thứ tự. `takeFirst` lấy urgent, `takeLast` lấy normal2, còn normal1 ở giữa. Sau đó `push("one")` đặt one ở đầu, `push("two")` đặt two phía trước one; `pop()` lấy từ đầu nên ra two rồi one.

LIFO ở đây là hành vi **deque được dùng như stack**, không phải API nào cũng đột nhiên trở thành LIFO. Nếu dùng `offerLast()` và `takeFirst()` thông thường, đường lấy là FIFO.

## 12. push()/pop() khác addFirst()/removeFirst() thế nào?

`Deque.push(e)` về ngữ nghĩa tương đương **`addFirst(e)`**, còn `pop()` tương đương **`removeFirst()`**. Các API này **không có tham số timeout**. Với `LinkedBlockingDeque` bounded, nếu đầy, `push`/ `addFirst` có thể ném `IllegalStateException`; nếu rỗng, `pop`/ `removeFirst` có thể ném `NoSuchElementException`.

Khi cần block và đợi có chỗ/dữ liệu, hãy dùng `putFirst()` và `takeFirst()`. Khi chỉ muốn thử một lần không chờ, dùng `offerFirst()` và `pollFirst()`.

Cần phân biệt:

```java
deque.push(item);       // Thêm đầu; nếu đầy có thể ném.
deque.offerFirst(item); // Thêm đầu; trả false nếu đầy.
deque.putFirst(item);   // Thêm đầu; có thể chờ nếu đầy.
```

Đây là trích đoạn với `deque` và `item` đã khai báo; `putFirst` có thể ném `InterruptedException`. Những lựa chọn này quan trọng khi producer không được block trên event loop hoặc request thread.

## 13. Ví dụ 5 — putFirst() chờ vì deque bounded đầy

Chương trình dùng deque capacity=1; main đặt “existing” vào trước. Producer cố `putFirst("urgent")` nhưng không có chỗ, nên phải đợi main lấy item cũ. Mục tiêu là minh họa **backpressure** ở đầu và cuối dùng chung capacity.

Tạo file **`BlockingDequeBackpressure.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.atomic.AtomicBoolean;

public class BlockingDequeBackpressure {
    public static void main(String[] args) throws InterruptedException {
        LinkedBlockingDeque<String> deque =
                new LinkedBlockingDeque<>(1);

        deque.putLast("existing");
        CountDownLatch producerEntered = new CountDownLatch(1);
        AtomicBoolean producerFinished = new AtomicBoolean();

        Thread producer = new Thread(() -> {
            producerEntered.countDown();
            try {
                deque.putFirst("urgent");
                producerFinished.set(true);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        producer.start();
        producerEntered.await();

        String old = deque.takeLast();
        producer.join();
        String urgent = deque.takeFirst();

        System.out.println("Removed old: " + old);
        System.out.println("Received next: " + urgent);
        System.out.println("Producer finished: "
                + producerFinished.get());
        System.out.println("Queue empty: " + deque.isEmpty());
    }
}
```

```bash
javac BlockingDequeBackpressure.java
java BlockingDequeBackpressure
```

Kết quả trong lần chạy bình thường:

```text
Removed old: existing
Received next: urgent
Producer finished: true
Queue empty: true
```

**Tại sao?** Khi producer được start, deque vẫn đang chứa existing nên `putFirst("urgent")` không thể hoàn tất nếu item cũ chưa được lấy. Main gọi `takeLast()`, giải phóng slot; producer đưa urgent vào đầu và kết thúc, được `join()` xác nhận. Sau đó main lấy urgent và thấy queue rỗng.

`producerEntered` chỉ xác nhận producer vào trước lời gọi `putFirst`; nó **không được dùng làm bằng chứng producer đã chắc chắn bị block** tại đúng thời điểm main chờ. Tuy nhiên, invariant capacity=1 và item existing có sẵn bảo đảm urgent không thể thêm trước khi item existing được lấy, nên kết quả không dựa vào lịch chạy tình cờ.

## 14. BlockingDeque có phù hợp làm hàng đợi ưu tiên không?

Có thể dùng một deque để tách công việc mức ưu tiên đơn giản:

```java
if (urgent) {
    deque.putFirst(job);
} else {
    deque.putLast(job);
}

// Consumer ưu tiên đầu hàng:
Job next = deque.takeFirst();
```

Đây là trích đoạn, cần định nghĩa `deque`, `job`, `urgent` và xử lý `InterruptedException`. Tuy nhiên, việc này **không phải priority scheduling tổng quát**:

- Hai urgent mới đều `putFirst` nên urgent mới hơn có thể nằm **trước** urgent cũ hơn (LIFO trong nhóm urgent).
- Nếu liên tục có urgent, normal đã ở cuối có thể bị **starvation**.
- Consumer có thể đã lấy normal trước khi urgent đến; không có preemption.
- Nhiều consumer chạy song song có thể hoàn tất task khác thứ tự lấy.
- Không có comparator để sắp theo nhiều mức ưu tiên hoặc deadline.

Nếu cần **priority theo comparator**, cân nhắc `PriorityBlockingQueue`. Nếu muốn một số lượng slot **dành riêng** cho công việc khẩn cấp, một deque bounded với tổng capacity không tự cung cấp quota theo lớp công việc; cần semaphore, nhiều queue hoặc logic admission riêng.

## 15. Deque và work-stealing: giống bề ngoài nhưng không tương đương ForkJoinPool

Trong các thuật toán song song, một deque có thể lưu task theo mô hình:

- Worker ưu tiên xử lý công việc mới ở một đầu.
- Worker khác có thể lấy công việc từ đầu đối diện để cân bằng tải.

Đây là **ý tưởng của work-stealing deque**, nhưng **không có nghĩa `LinkedBlockingDeque` chính là cơ chế deque nội bộ của `ForkJoinPool`**. `ForkJoinPool` có cấu trúc hàng đợi và cơ chế scheduling riêng được tối ưu cho `ForkJoinTask`, không thể thay thế một-một bằng cách đặt `LinkedBlockingDeque<Runnable>` rồi suy ra cùng hiệu năng hoặc cùng quy tắc.

Khi tự làm một scheduler dùng BlockingDeque, phải thiết kế thêm:

1. Quyền sở hữu và trách nhiệm worker.
2. Chính sách lấy từ đầu/cuối.
3. Vòng đời queue, shutdown/cancellation và poison pill hoặc tín hiệu đóng.
4. Xử lý exception/timeout của task.
5. Điều phối starvation/fairness và giám sát backlog.
6. Hạn mức worker, memory và backpressure.

Nếu bài toán là đệ quy chia để trị CPU-bound, nên xem `ForkJoinPool` như một công cụ sẵn có thay vì tự tái tạo work-stealing engine từ BlockingDeque.

## 16. Deque trong ThreadPoolExecutor và điểm cần tránh

`ThreadPoolExecutor` nhận constructor có `BlockingQueue<Runnable>`. Vì `BlockingDeque<Runnable>` extends `BlockingQueue<Runnable>`, có thể dùng:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2, 4, 30, TimeUnit.SECONDS,
        new LinkedBlockingDeque<Runnable>(100),
        new ThreadPoolExecutor.AbortPolicy()
);
```

Đây là trích đoạn, cần import `java.util.concurrent.*` và quản lý `shutdown()`. Tuy nhiên, **`execute()` của ThreadPoolExecutor theo contract bình thường dùng `workQueue.offer(command)`**, tức là thêm về cuối của BlockingDeque; worker lấy qua phương thức `take()`, tương ứng lấy từ đầu. Vì vậy cấu hình trên hoạt động như **FIFO bounded work queue thông thường**, không tự biến pool thành priority scheduler hai đầu.

**Không khuyến nghị trực tiếp gọi `executor.getQueue().putFirst(task)` để “ưu tiên task”**: thao tác trực tiếp trên queue bỏ qua một phần admission/lifecycle, kiểm tra trạng thái shutdown và chính sách rejection của `execute()`. Nếu cần priority scheduler cho executor, cần thiết kế API submit/admission có contract rõ ràng hoặc dùng cấu trúc/Executor phù hợp, không chỉ thêm task vào deque đang được executor quản lý.

Cũng cần nhớ: với queue bounded, khi số core workers đã đủ, pool thử enqueue; chỉ khi queue không nhận thêm được thì mới thử non-core worker tới maximum. Với unbounded deque, non-core worker có thể không được tạo dưới tải bình thường vì queue tiếp tục nhận task.

## 17. Cancellation, interrupt và shutdown

Cả hai loại queue đều có những thao tác có thể **chờ vô thời hạn**:

- `TransferQueue.transfer(e)`: đợi consumer nhận.
- `TransferQueue.tryTransfer(e, timeout, unit)`: đợi có giới hạn.
- `BlockingDeque.putFirst/putLast(e)`: đợi chỗ trống khi bounded deque đầy.
- `BlockingDeque.takeFirst/takeLast()`: đợi phần tử khi deque rỗng.
- `BlockingDeque.offerFirst/Last(e, timeout, unit)` và `pollFirst/Last(timeout, unit)`: đợi có giới hạn.

Các method chờ có thể ném `InterruptedException`. Worker nên:

- Chấp nhận/ném tiếp interruption khi method có hợp đồng đó.
- Nếu bắt exception để kết thúc mà không ném tiếp, thường khôi phục flag bằng `Thread.currentThread().interrupt()`.
- Không nuốt exception rồi gọi lại `transfer` hoặc `take` vô hạn.
- Đặt timeout khi caller không thể chờ vô hạn.
- Quy định rõ cleanup của resource do producer/consumer sở hữu.

**Một điểm khó:** nếu producer bị interrupt đúng lúc consumer cũng nhận một item, phải dựa vào hợp đồng giao dịch thực tế, không tự đoán kết quả của một thao tác cắt ngang luôn là “chắc chắn chưa gửi”. Với công việc có side effect, dùng ID/idempotency hoặc acknowledgement riêng nếu cần retry an toàn.

`TransferQueue` và `BlockingDeque` **không có phương thức `close()` thống nhất**. Để dừng worker, có thể dùng cancellation flag, interruption, sentinel/poison pill hoặc lifecycle của executor. Poison pill phải được thiết kế cho số consumer và thứ tự lấy phù hợp; với deque có hai đầu, chèn sentinel sai đầu có thể khiến consumer bỏ qua item cần xử lý hoặc dừng quá sớm.

## 18. JMM: công bố dữ liệu an toàn qua queue

Theo hợp đồng memory consistency của `BlockingQueue`, các hành động xảy ra **trước khi producer đưa một object vào queue** có quan hệ *happens-before* với các hành động của consumer **sau khi truy cập/lấy object đó ra** bằng queue. Điều này áp dụng cho các implementation đúng contract của `TransferQueue` và `BlockingDeque`.

Ví dụ minh họa:

```java
// Producer (trích đoạn):
Message message = new Message();
message.payload = 42;
queue.put(message);

// Consumer trong thread khác:
Message item = queue.take();
System.out.println(item.payload);
```

Đoạn này chưa độc lập, cần class `Message`, queue phù hợp và xử lý `InterruptedException`. Việc chuyển giao qua queue giúp consumer thấy trạng thái object đã chuẩn bị trước enqueue/handoff. Nhưng **không tự làm các mutation sau khi chuyển giao trở nên thread-safe**: producer tiếp tục sửa cùng object trong lúc consumer đọc vẫn cần đồng bộ hoặc ownership rõ ràng.

Đặc biệt:

- Với `LinkedTransferQueue`, `transfer(e)` chờ nhận không đồng nghĩa object đã immutable; tránh producer tiếp tục sửa khi consumer xử lý.
- Với `LinkedBlockingDeque`, hai đầu cùng chia sẻ collection được đồng bộ hóa, nhưng các object bên trong có thể vẫn mutable và cần giao thức riêng.
- Với các phép thử `hasWaitingConsumer()`, `size()`, `remainingCapacity()`, đừng dùng giá trị quan sát làm bước cấp phép duy nhất cho một hành động cạnh tranh. Chính `offer/tryTransfer/put/take` mới quyết định thành công tại thời điểm thao tác.

Nếu có kết quả xử lý cần báo về producer, dùng Future/latch/queue trả lời hoặc primitive đồng bộ khác; happens-before của việc **nhận input** không tự công bố **kết quả xử lý chưa xảy ra**.

## 19. Những lỗi thường gặp

| Lỗi | Vì sao sai? | Cách xử lý |
|---|---|---|
| Cho rằng `transfer(e)` nghĩa consumer xử lý xong. | Nó chỉ chờ consumer nhận item. | Dùng acknowledgement riêng cho business completion. |
| Gọi `tryTransfer(e)`, thấy false, nghĩ item sẽ được nhận sau. | Thất bại không enqueue. | Dùng `offer`, `transfer` hoặc timed variant theo yêu cầu. |
| Gọi `offer(e)` rồi tưởng đợi được consumer. | `offer` chỉ enqueue khi chấp nhận. | Dùng `transfer(e)` nếu cần đợi nhận. |
| Dùng `hasWaitingConsumer()` rồi cho rằng tryTransfer chắc chắn true. | State có thể thay đổi trước lời chuyển giao. | Dựa trên kết quả trực tiếp của tryTransfer. |
| Cho rằng LinkedTransferQueue có bound theo constructor. | Queue không có capacity giới hạn do người dùng đặt. | Giới hạn producer bằng semaphore/quota hoặc dùng queue bounded khác. |
| Dùng `size()` để quyết định admission chính xác. | Snapshot race và có thể tốn duyệt. | Dùng API nguyên tử hoặc giới hạn riêng. |
| Nhầm `BlockingDeque.put(e)` với thêm đầu. | Nó thêm **cuối**, giống `putLast`. | Dùng `putFirst` khi cần ưu tiên đầu. |
| Nghĩ `push()` chờ có chỗ khi deque đầy. | Push tương đương addFirst, có thể ném. | Dùng `putFirst` hoặc timed offerFirst. |
| Nghĩ `pop()` chờ khi deque rỗng. | Pop tương đương removeFirst, có thể ném. | Dùng `takeFirst` hoặc timed pollFirst. |
| Nghĩ `LinkedBlockingDeque<>(2)` có hai slot mỗi đầu. | Tổng capacity chỉ là hai. | Quản lý một capacity chung cho cả deque. |
| Dùng putFirst liên tục và tưởng mọi normal task sẽ tới lượt. | Task ở cuối có thể bị starvation. | Thiết kế quota/fairness/aging riêng. |
| Nghĩ task thêm đầu sẽ preempt task đã chạy. | Deque chỉ quyết định thứ tự lấy item chưa dequeue. | Không dựa vào queue để ngắt tác vụ đang chạy. |
| Trực tiếp thêm task vào `executor.getQueue()`. | Bỏ qua executor admission/rejection/lifecycle. | Dùng execute/submit hoặc scheduler thiết kế riêng. |
| Dùng deque làm work-stealing và cho rằng giống ForkJoinPool. | ForkJoinPool có cơ chế riêng, tối ưu cho ForkJoinTask. | Sử dụng đúng abstraction/concurrency model. |
| Nuốt InterruptedException và tiếp tục chờ mãi. | Hủy không được tôn trọng. | Ném tiếp hoặc restore interrupt rồi thoát. |
| Dừng consumer bằng sentinel không xét đầu lấy. | Có thể dừng trước khi xử lý item còn tồn. | Thiết kế rõ thứ tự/số sentinel và completion. |

## 20. Chọn API theo bài toán

| Nhu cầu | Lựa chọn cân nhắc | Vì sao |
|---|---|---|
| Producer muốn enqueue ngay, không cần consumer đã nhận. | `LinkedTransferQueue.offer(e)` hoặc queue phù hợp. | Không đợi handoff. |
| Producer muốn chờ tới khi consumer nhận, không cần xử lý xong. | `TransferQueue.transfer(e)`. | Chờ mốc receipt, có thể interrupt. |
| Chỉ gửi nếu hiện tại có consumer sẵn sàng. | `TransferQueue.tryTransfer(e)`. | Không chờ, không enqueue khi thất bại. |
| Chờ consumer tối đa N ms. | `tryTransfer(e, N, unit)`. | Handoff có timeout, phải xử lý false. |
| Cấm toàn bộ backlog, luôn handoff trực tiếp. | `SynchronousQueue`. | Capacity bằng 0, không có queue lưu. |
| Có backlog bounded, cần thêm/lấy ở hai đầu. | `LinkedBlockingDeque<>(capacity)`. | Hai đầu và backpressure. |
| Chỉ cần FIFO bounded. | `ArrayBlockingQueue` hoặc `LinkedBlockingQueue(capacity)`. | Đơn giản hơn deque khi không cần hai đầu. |
| Cần ưu tiên theo comparator. | `PriorityBlockingQueue` với comparator rõ. | Deque không tự sort nhiều priority. |
| Cần đợi task hoàn tất, biết thành công/lỗi. | `Future`, `CompletableFuture` hoặc acknowledgement riêng. | Queue transfer không đại diện kết quả xử lý. |

**Khác biệt cốt lõi:** TransferQueue giúp producer chọn **enqueue hay đợi consumer nhận**; BlockingDeque giúp producer/consumer chọn **đầu hay cuối**. Chúng giải quyết **hai chiều khác nhau** của bài toán concurrent coordination.

## 21. Checklist thiết kế và kiểm thử

1. **Xác định completion:** đã enqueue, đã nhận hay đã xử lý xong?
2. **Chọn giao thức transfer:** offer/put cho gửi thông thường, transfer/tryTransfer cho handoff.
3. **Có giới hạn chờ:** dùng timed transfer/timed deque operations hoặc cancellation khi có nguy cơ deadlock/liveness.
4. **Không suy state từ snapshot:** hasWaitingConsumer/size/remainingCapacity chỉ phục vụ quan sát.
5. **Giới hạn memory:** LinkedTransferQueue và default LinkedBlockingDeque có khả năng giữ backlog rất lớn; theo dõi arrival và service rate.
6. **Chọn đầu deque:** urgent ở first, normal ở last, consumer lấy first; hiểu LIFO trong nhóm urgent và starvation.
7. **Đặt capacity hợp lý:** bounded LinkedBlockingDeque có tổng capacity, không có quota mỗi đầu.
8. **Xác định đối tượng sở hữu:** ai enqueue, ai consume, ai dừng worker và ai cleanup?
9. **Không lặp retry vô hạn:** false/timeout/interruption cần đường xử lý rõ.
10. **Bảo vệ mutable payload:** immutable object/record hoặc giao thức ownership và đồng bộ sau handoff.
11. **Dùng lifecycle:** queue không có close chung; executor shutdown và chờ termination khi là owner.
12. **Kiểm thử có điều phối:** latch để tránh kết quả theo lịch chạy, kiểm tra timeout, cancel, queue đầy và consumer biến mất.
13. **Tách handoff khỏi acknowledgement:** consumer nhận không nghĩa đã thành công; nghiệp vụ quan trọng cần xác nhận riêng.
14. **Đừng lẫn với ForkJoin work-stealing:** hai đầu là primitive, không phải một scheduler hoàn chỉnh.
15. **Đo production:** queue depth, wait duration, backlog age, số transfer timeout, active consumers, throughput và GC.

## 22. Câu hỏi tự kiểm tra

1. **TransferQueue mở rộng interface nào?** `BlockingQueue<E>`.
2. **`transfer(e)` chờ điều gì?** Chờ có consumer nhận phần tử, không đợi xử lý xong.
3. **`tryTransfer(e)` false có enqueue item không?** Không.
4. **`tryTransfer(e, timeout, unit)` trả false khi nào?** Không có handoff trong thời hạn.
5. **`hasWaitingConsumer()` có bảo đảm lời tryTransfer kế tiếp thành công?** Không, vì trạng thái cạnh tranh thay đổi.
6. **LinkedTransferQueue có bounded capacity bằng constructor không?** Không.
7. **`offer(e)` trên LinkedTransferQueue có đợi consumer không?** Không; có thể enqueue.
8. **TransferQueue và SynchronousQueue có giống nhau không?** Không; TransferQueue có khả năng backlog với offer/put, SynchronousQueue capacity=0.
9. **BlockingDeque có hai đầu nào?** First/head và last/tail.
10. **`put(e)` trên BlockingDeque thêm ở đâu?** Ở cuối, tương đương putLast.
11. **`take()` trên BlockingDeque lấy ở đâu?** Ở đầu, tương đương takeFirst.
12. **`push()`/`pop()` tương đương phương thức nào?** addFirst/removeFirst; không tự block khi đầy/rỗng.
13. **`LinkedBlockingDeque<>(3)` có ba slot cho mỗi đầu không?** Không, tổng cộng ba phần tử.
14. **Tại sao putFirst nhiều có thể gây starvation?** Các phần tử cũ ở cuối bị liên tục chen trước bởi phần tử mới.
15. **BlockingDeque có tự thực hiện priority scheduling cho ThreadPoolExecutor không?** Không; executor thông thường enqueue cuối và take đầu.
16. **Có thể thêm task bằng executor.getQueue().putFirst để ưu tiên không?** Không nên; bỏ qua admission/lifecycle của executor.
17. **Handoff cung cấp happens-before gì?** Các hành động producer trước khi đưa item vào queue happens-before các hành động consumer sau khi lấy item.
18. **Nhận item có nghĩa nghiệp vụ đã commit không?** Không; cần acknowledgement/transaction riêng.
19. **Cần gì để dừng worker đang đợi transfer/take?** Interruption, timeout hoặc giao thức lifecycle phù hợp.
20. **Khi nào LinkedBlockingDeque tốt hơn BlockingQueue FIFO đơn giản?** Khi có nhu cầu rõ ràng thêm/lấy từ cả hai đầu.

**Ghi nhớ:** **`TransferQueue` điều khiển thời điểm producer biết consumer đã nhận; `BlockingDeque` điều khiển việc thêm/lấy ở hai đầu.** Đừng nhầm handoff với hoàn tất nghiệp vụ, hai đầu với cơ chế priority tự động, hoặc queue thread-safe với payload mutable luôn an toàn. Chọn API theo hợp đồng phối hợp, timeout, dung lượng và lifecycle của hệ thống.
