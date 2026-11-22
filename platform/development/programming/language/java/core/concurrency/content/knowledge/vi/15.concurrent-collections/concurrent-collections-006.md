# ConcurrentLinkedQueue và ConcurrentLinkedDeque trong Java

> **Trọng tâm:** `ConcurrentLinkedQueue<E>` là **hàng đợi FIFO thread-safe, không giới hạn dung lượng ở tầng API, sử dụng thuật toán non-blocking**; `ConcurrentLinkedDeque<E>` là **deque thread-safe, cũng unbounded**, cho phép thêm/lấy ở **hai đầu**. Các thao tác riêng lẻ như `offer/poll` hoặc `offerFirst/pollLast` có thể được nhiều thread gọi đồng thời mà không cần bao chúng bằng một monitor của ứng dụng. Nhưng **không blocking** không đồng nghĩa “tự đợi khi rỗng”, và **thread-safe collection** không đồng nghĩa mọi chuỗi nhiều thao tác, snapshot, quota hoặc object được chứa đều trở nên nguyên tử.

Bài thuộc nhóm **Concurrent Collections**, phạm vi **Java concurrency nói chung** (Java SE 17+). Không bàn đến Spring.

## 1. Bối cảnh: vì sao không dùng ArrayDeque hoặc LinkedList tùy tiện?

Trong một pipeline producer–consumer, nhiều producer cùng gửi việc, nhiều consumer cùng nhận. Nếu chia sẻ một `ArrayDeque`/`LinkedList` thông thường rồi gọi `add/remove` đồng thời mà không đồng bộ, chương trình có thể rơi vào data race, mất cập nhật, nhìn thấy trạng thái thiếu nhất quán, hoặc làm sai cấu trúc dữ liệu.

Một phương án là dùng `synchronized` quanh mọi truy cập; một phương án khác là chọn collection được thiết kế cho concurrent access.

~~~text
Nhiều producers                               Nhiều consumers
    P1 ── offer(J1) ─┐                 ┌─ poll() ──> C1
    P2 ── offer(J2) ─┼─> Queue FIFO ───┤
    P3 ── offer(J3) ─┘                 └─ poll() ──> C2

Mỗi phần tử được dequeue tối đa một lần bởi một poll thành công.
Nhưng thứ tự xử lý/xong việc giữa C1 và C2 không được đảm bảo.
~~~

`ConcurrentLinkedQueue` phù hợp khi nhiều thread cần trao đổi phần tử theo hướng vào **đuôi**, lấy từ **đầu**. Khi phải thao tác cả hai đầu, dùng `ConcurrentLinkedDeque`.

**Phân biệt quan trọng:** Cả hai là concurrent collections **không chặn** (*non-blocking*); chúng không phải `BlockingQueue` / `BlockingDeque`. Khi rỗng, `poll()` trả `null` ngay, không đợi producer. Khi đầy theo nghĩa bộ nhớ thực tế, không có một limit vận hành được cấu hình sẵn cho `offer` trả `false` và tạo backpressure.

## 2. Hai lớp: giống và khác nhau ở đâu?

| Thuộc tính | `ConcurrentLinkedQueue<E>` | `ConcurrentLinkedDeque<E>` |
| --- | --- | --- |
| Vai trò | FIFO queue: thêm cuối, lấy đầu | Deque: thêm/lấy đầu và cuối |
| Interface chính | `Queue<E>` | `Deque<E>`, đồng thời là `Queue<E>` |
| Dữ liệu lưu | Các phần tử `E`, node liên kết | Các phần tử `E`, node liên kết hai hướng về mặt giao diện |
| Thao tác thường gặp | `offer`, `poll`, `peek` | `offerFirst`, `offerLast`, `pollFirst`, `pollLast`, `push`, `pop` |
| Chấp nhận null? | **Không** | **Không** |
| Capacity giới hạn bởi API? | Unbounded | Unbounded |
| `put()` / `take()` chờ? | **Không có** | **Không có** |
| Iterator | *Weakly consistent*, không fail-fast | *Weakly consistent*, thêm `descendingIterator` |
| `size()` | O(n), không là snapshot tin cậy dưới concurrent modifications | O(n), tương tự |
| Bulk operations | Không mặc nhiên atomic trên toàn tập | Không mặc nhiên atomic trên toàn tập |
| Phù hợp | Nhiều producers/consumers, FIFO handoff không chặn | Work list hai đầu, FIFO/LIFO, lấy việc từ hai đầu |

“Unbounded” ở đây nói về **không có capacity hữu hạn định nghĩa sẵn** cho phương thức enqueue; không phải JVM có vô hạn heap. Chứa quá nhiều work có thể giữ lại object graph lớn và gây `OutOfMemoryError`.

### Sơ đồ Queue và Deque

~~~text
ConcurrentLinkedQueue:
  head                         tail
   v                            v
 [A] -> [B] -> [C] -> [D] -> [E]
  ^                           |
  | poll()                    +-- offer(F) vào cuối

ConcurrentLinkedDeque:
  first                         last
    v                            v
  [A] <-> [B] <-> [C] <-> [D] <-> [E]
    ^                            ^
    |                            |
 pollFirst()/offerFirst()    pollLast()/offerLast()
~~~

Các sơ đồ diễn tả **logic của API**, không mô tả chi tiết con trỏ/node hoặc từng bước CAS trong implementation OpenJDK. Không suy từ hình vẽ rằng mọi operation đều là O(1) trong tình trạng contention hoặc cleanup nội bộ.

## 3. API Queue: offer, poll, peek và phương thức ném exception

Với `ConcurrentLinkedQueue<E>`:

| Phương thức | Ý nghĩa | Nếu queue trống |
| --- | --- | --- |
| `offer(e)` | Thêm phần tử vào đuôi, thường trả `true` | Không áp dụng; `null` bị từ chối |
| `add(e)` | Thêm vào đuôi | Không áp dụng |
| `poll()` | Lấy **và xóa** phần tử đầu | Trả `null` |
| `peek()` | Đọc phần tử đầu nhưng **không xóa** | Trả `null` |
| `remove()` (không tham số) | Lấy và xóa phần tử đầu | Ném `NoSuchElementException` |
| `element()` | Đọc đầu mà không xóa | Ném `NoSuchElementException` |
| `remove(object)` | Xóa một phần tử khớp `equals` nếu tìm thấy | Trả boolean |
| `isEmpty()` | Hỏi có rỗng tại thời điểm quan sát | Có thể đổi ngay sau lời gọi |

Không nhầm hai overload `remove()` và `remove(Object)`: một cái lấy head và có thể ném exception khi rỗng, cái còn lại tìm/xóa phần tử theo giá trị.

### Ví dụ 1 — FIFO, peek và null

Tạo `LinkedQueueBasics.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;

public class LinkedQueueBasics {
    public static void main(String[] args) {
        ConcurrentLinkedQueue<String> queue =
                new ConcurrentLinkedQueue<>();

        System.out.println("offer A = " + queue.offer("A"));
        System.out.println("offer B = " + queue.offer("B"));

        System.out.println("peek = " + queue.peek());
        System.out.println("poll 1 = " + queue.poll());
        System.out.println("poll 2 = " + queue.poll());
        System.out.println("poll empty = " + queue.poll());

        try {
            queue.offer(null);
        } catch (NullPointerException expected) {
            System.out.println("null rejected = true");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac LinkedQueueBasics.java
java LinkedQueueBasics
~~~

Stdout xác định:

~~~text
offer A = true
offer B = true
peek = A
poll 1 = A
poll 2 = B
poll empty = null
null rejected = true
~~~

`peek` không xóa A; `poll` xóa A rồi B, và `poll` tiếp trả `null`. Cấm `null` làm element là cần thiết vì API đã dùng `null` để biểu thị queue rỗng. Trong một protocol end-of-stream, hãy dùng **sentinel non-null** có type rõ ràng, không dùng null làm poison pill.

`poll()==null` không báo hệ thống đã hết work mãi mãi: producer có thể `offer` một item ngay sau lúc poll trả về. Muốn kết thúc consumer, cần một completion protocol (producer-done, sentinel, lifecycle coordinator), không chỉ kiểm tra rỗng một lần.

## 4. FIFO của Queue không phải thứ tự hoàn thành của nhiều consumer

FIFO nói rằng những phần tử **được enqueue theo một thứ tự xác định** sẽ được lấy từ head theo thứ tự đó. Khi nhiều producer đồng thời `offer`, **thứ tự xen kẽ giữa producers không cố định**.

Ví dụ:

~~~text
Producer P1: offer(A1) -> offer(A2)
Producer P2: offer(B1) -> offer(B2)

Một thứ tự enqueue hợp lệ:
 A1, B1, B2, A2
Một thứ tự khác:
 B1, A1, A2, B2

Không được mặc định toàn bộ A chạy trước toàn bộ B.
~~~

Trong mỗi producer, các lần `offer` được thực hiện theo thứ tự chương trình; nhưng tổng thứ tự giữa các producer do interleaving quyết định. Khi nhiều consumer cùng `poll`, item được một consumer lấy khỏi queue không còn được `poll` bởi consumer khác. Tuy vậy consumer A có thể xử lý chậm hơn consumer B; **completion order có thể khác dequeue order**.

Điều này quyết định cách viết test: kiểm tra **tập hợp job, số lần nhận và kết quả cuối**, không in/log name thread rồi gán một trình tự cố định cho scheduler.

## 5. Ví dụ 2 — ba producer, hai consumer, không mất hoặc trùng item

Ví dụ này dùng hai consumer `poll` **đồng thời** khi ba producer `offer` các ID độc nhất. Một cờ hoàn tất cho biết **tất cả producer đã kết thúc**. Khi queue đang tạm rỗng nhưng producer chưa xong, consumer chưa được phép thoát.

Tạo `ConcurrentQueueWorkers.java` (Java 17+):

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentQueueWorkers {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<Integer> work =
                new ConcurrentLinkedQueue<>();
        Set<Integer> unique = ConcurrentHashMap.newKeySet();
        AtomicBoolean producersDone = new AtomicBoolean(false);
        AtomicInteger processed = new AtomicInteger();

        Runnable consumerLogic = () -> {
            while (true) {
                Integer item = work.poll();

                if (item != null) {
                    unique.add(item);
                    processed.incrementAndGet();
                    continue;
                }
                if (producersDone.get()) {
                    return; // Không còn producer gửi thêm item.
                }
                Thread.yield(); // Demo ngắn; không là backpressure.
            }
        };

        Thread[] consumers = {
                new Thread(consumerLogic, "consumer-1"),
                new Thread(consumerLogic, "consumer-2")
        };
        for (Thread consumer : consumers) {
            consumer.start();
        }

        Thread[] producers = new Thread[3];
        for (int p = 0; p < producers.length; p++) {
            final int producerId = p;
            producers[p] = new Thread(() -> {
                for (int i = 0; i < 1_000; i++) {
                    work.offer(producerId * 1_000 + i);
                }
            });
            producers[p].start();
        }

        for (Thread producer : producers) {
            producer.join();
        }
        producersDone.set(true);

        for (Thread consumer : consumers) {
            consumer.join();
        }

        System.out.println("processed = " + processed.get());
        System.out.println("unique = " + unique.size());
        System.out.println("queue empty = " + work.isEmpty());
    }
}
~~~

Chạy:

~~~bash
javac ConcurrentQueueWorkers.java
java ConcurrentQueueWorkers
~~~

Stdout sau khi tất cả threads hoàn tất:

~~~text
processed = 3000
unique = 3000
queue empty = true
~~~

Mỗi producer đưa 1.000 ID riêng, tổng 3.000 item. Mỗi `poll` thành công loại **một** item; hai consumer không cùng nhận chính item ấy. `unique` ghi nhận tập hợp ID đã nhận; `processed` đếm số lần xử lý. Sau `join` tất cả producer, main đặt cờ volatile/atomic `producersDone=true`; vì không còn người thêm item, consumer có thể thoát khi poll trả null. `join` consumer rồi mới tổng kết.

**Đây là demo về tính đúng đắn, không phải kiểu consumer loop tốt cho production.** `Thread.yield()` không có bảo đảm thời gian đợi và có thể gây CPU spinning. Khi cần đợi item đến mà không tốn CPU, thường nên sử dụng **`BlockingQueue.take()`** với completion protocol rõ ràng. Cách dùng `ConcurrentLinkedQueue` phù hợp hơn khi caller có việc khác để làm nếu poll rỗng, hoặc hệ thống có một notification/event-loop protocol được kiểm soát.

### Điều gì xảy ra nếu không có producersDone?

Nếu mỗi consumer chỉ `while ((item = queue.poll()) != null)` thì có thể thoát **quá sớm** trong lúc producer chưa kịp enqueue item đầu tiên, hoặc giữa hai lần enqueue. Vì vậy phải tách hai câu hỏi:

- “Queue đang rỗng ở thời điểm này?”
- “Không bao giờ còn producer phát thêm work?”

Chỉ câu thứ hai mới giúp xác định điểm đóng pipeline.

## 6. Deque: hai đầu và ba mô hình truy cập

`ConcurrentLinkedDeque<E>` triển khai `Deque<E>`. Từ *deque* là *double-ended queue*: người dùng có thể thêm hoặc lấy ở head và tail.

Các phương thức quan trọng:

| Nhóm | Đầu (`first`) | Cuối (`last`) |
| --- | --- | --- |
| Thêm | `addFirst(e)` / `offerFirst(e)` | `addLast(e)` / `offerLast(e)` |
| Lấy/xóa khi có, trả null nếu rỗng | `pollFirst()` | `pollLast()` |
| Xem, không xóa, trả null nếu rỗng | `peekFirst()` | `peekLast()` |
| Lấy/xóa, ném exception nếu rỗng | `removeFirst()` | `removeLast()` |
| Xem, ném exception nếu rỗng | `getFirst()` | `getLast()` |
| Xóa theo giá trị | `removeFirstOccurrence(o)` | `removeLastOccurrence(o)` |

Các phép `Queue.offer(e)`, `Queue.poll()`, `Queue.peek()` khi áp dụng trên Deque tương đương **offerLast / pollFirst / peekFirst** theo hướng FIFO.

Ngoài ra `Deque.push(e)` tương đương thêm vào đầu, còn `Deque.pop()` lấy và xóa ở đầu (ném `NoSuchElementException` nếu rỗng), tạo phong cách **LIFO stack**.

~~~text
FIFO queue trên deque:
  offerLast(A), offerLast(B), offerLast(C)
  pollFirst() -> A, rồi B, rồi C

LIFO stack trên deque:
  push(A), push(B), push(C)   (thêm đầu)
  pop() -> C, rồi B, rồi A

Đọc hai đầu:
  pollFirst()  -> lấy phần tử đầu
  pollLast()   -> lấy phần tử cuối
~~~

Đừng nhầm stack push/pop của `Deque` với `java.util.Stack` legacy; `Deque` là interface hiện đại cho cả FIFO và LIFO. Tuy nhiên khi nhiều thread cùng thao tác, đừng dựa trên một thứ tự pop/poll ngẫu nhiên như một lịch chạy cố định.

## 7. Ví dụ 3 — dùng Deque làm FIFO, LIFO và xóa phần tử trùng

Tạo `LinkedDequeBasics.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentLinkedDeque;

public class LinkedDequeBasics {
    public static void main(String[] args) {
        ConcurrentLinkedDeque<String> deque =
                new ConcurrentLinkedDeque<>();

        deque.offerLast("A");
        deque.offerLast("B");
        deque.offerFirst("urgent");

        System.out.println("first = " + deque.peekFirst());
        System.out.println("last = " + deque.peekLast());

        System.out.println("pop = " + deque.pop());
        System.out.println("pollLast = " + deque.pollLast());
        System.out.println("pollFirst = " + deque.pollFirst());
        System.out.println("empty = " + deque.isEmpty());

        deque.push("one");
        deque.push("two");
        System.out.println("stack pop = " + deque.pop());

        deque.clear();
        deque.offerLast("X");
        deque.offerLast("Y");
        deque.offerLast("X");

        System.out.println("remove last X = "
                + deque.removeLastOccurrence("X"));
        System.out.println("first after remove = " + deque.pollFirst());
        System.out.println("last after remove = " + deque.pollLast());
    }
}
~~~

Chạy:

~~~bash
javac LinkedDequeBasics.java
java LinkedDequeBasics
~~~

Stdout:

~~~text
first = urgent
last = B
pop = urgent
pollLast = B
pollFirst = A
empty = true
stack pop = two
remove last X = true
first after remove = X
last after remove = Y
~~~

Cả ba item đầu tiên được lấy đúng theo vị trí logic. Với phần stack, `push("two")` đặt nó trước `"one"` nên `pop()` trả `two`. Sau khi clear và thêm X,Y,X, `removeLastOccurrence("X")` xóa **X ở cuối**, không phải X ở đầu. Đây là chương trình chạy tuần tự để stdout xác định; tính đúng đắn khi nhiều writers đến từ contract concurrent collection, không phải từ việc ví dụ chỉ có main thread.

### Chọn hướng thao tác một cách nhất quán

Nếu consumer luôn lấy `pollFirst` nhưng producer dùng `offerFirst` cho “priority work”, các job mới có thể liên tục đứng trước job cũ và làm job cũ bị trì hoãn rất lâu. Đó là chính sách nghiệp vụ **LIFO/priority tương đối**, không còn FIFO chung.

Nếu cần thứ tự ưu tiên thực sự theo comparator, `PriorityBlockingQueue` hoặc một cơ chế scheduling chuyên biệt có thể phù hợp hơn. ConcurrentLinkedDeque không tự sắp xếp theo priority và không bảo đảm fairness của từng task.

## 8. Ví dụ 4 — hai consumer lấy ở hai đầu cùng một Deque

Một thiết kế có thể dùng consumer A lấy đầu và consumer B lấy cuối để phân tán công việc; mỗi `pollFirst`/`pollLast` thành công loại đúng một phần tử. Nhưng **đừng gọi đó là implementation của work-stealing ForkJoinPool**: work-stealing có protocol, placement, task queues và scheduling riêng, không chỉ “một deque với hai thread”.

Tạo `TwoEndedConsumers.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedDeque;
import java.util.concurrent.ConcurrentLinkedQueue;

public class TwoEndedConsumers {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedDeque<Integer> deque =
                new ConcurrentLinkedDeque<>();
        for (int id = 1; id <= 10; id++) {
            deque.offerLast(id);
        }

        ConcurrentLinkedQueue<Integer> consumed =
                new ConcurrentLinkedQueue<>();

        Thread headWorker = new Thread(() -> {
            Integer id;
            while ((id = deque.pollFirst()) != null) {
                consumed.offer(id);
            }
        });
        Thread tailWorker = new Thread(() -> {
            Integer id;
            while ((id = deque.pollLast()) != null) {
                consumed.offer(id);
            }
        });

        headWorker.start();
        tailWorker.start();
        headWorker.join();
        tailWorker.join();

        List<Integer> ordered = new ArrayList<>(consumed);
        Collections.sort(ordered);

        System.out.println("consumed = " + ordered);
        System.out.println("remaining empty = " + deque.isEmpty());
    }
}
~~~

Chạy:

~~~bash
javac TwoEndedConsumers.java
java TwoEndedConsumers
~~~

Stdout:

~~~text
consumed = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
remaining empty = true
~~~

Để output không phụ thuộc OS scheduling, demo **pre-populate cả 10 item trước khi chạy consumer**, rồi sort kết quả sau `join`. Không in tên thread đã nhận item nào: một worker có thể lấy nhiều item trước khi worker kia được CPU, nhưng tập hợp cuối vẫn phải đủ 10 item, không trùng.

Lưu ý: nếu producer có thể thêm item **sau** lúc consumer thấy deque rỗng, vòng lặp trên vẫn có thể thoát sớm. Với hệ thống live, cần giao thức completion như phần queue phía trên hoặc một blocking structure phù hợp.

## 9. Không-blocking có ý nghĩa gì?

Các lớp này dùng thuật toán đồng bộ dựa trên các primitive như CAS để hỗ trợ thao tác concurrent mà không yêu cầu caller acquire một lock ứng dụng bao quanh `offer/poll`. Riêng `ConcurrentLinkedQueue` được Javadoc mô tả là dùng thuật toán **non-blocking** dựa trên công trình của Michael & Scott; `ConcurrentLinkedDeque` cũng cung cấp các concurrent insertion/removal/access operations an toàn.

Tuy nhiên:

- **Không-blocking khác không-chờ-vĩnh-viễn ở tầng ứng dụng.** Nếu bạn tự viết vòng chờ cho tới khi nhận item, chính vòng đó vẫn có thể đợi mãi khi producer không gửi.
- **Không-blocking khác wait-free.** Một thread riêng lẻ có thể bị trì hoãn/retry dưới contention hoặc scheduling; không có cam kết nó hoàn tất mọi operation sau số bước cố định.
- **Không-blocking khác không dùng CPU.** Một poll loop rất nóng có thể tiêu CPU, dù không bị mutex block.
- **Không-blocking khác không có memory cost.** Nodes/objects, garbage collection và cache-coherence traffic vẫn có chi phí.
- **Không-blocking khác không thể bị starvation.** Fairness giữa các consumer và tốc độ xử lý không được những lớp này bảo đảm.
- **Không-blocking khác atomic batch.** `offer(x)` và `offer(y)` là hai operation; thread khác có thể chen vào.

Vì vậy một concurrent queue có thể rất hiệu quả với workload phù hợp, nhưng benchmark thực tế vẫn cần xét contention, throughput, tail latency, allocation rate và payload retention.

## 10. Khi nào poll() trả null và tại sao busy spinning có thể nguy hiểm?

`ConcurrentLinkedQueue.poll()` hoặc `ConcurrentLinkedDeque.pollFirst()` trả `null` **ngay** khi không tìm thấy item ở thời điểm operation. Chúng không có `take()` để block chờ. Nếu viết:

~~~java
// Snippet cảnh báo, không phải chương trình hoàn chỉnh.
while (true) {
    Job job = queue.poll();
    if (job != null) {
        process(job);
    }
}
~~~

Một consumer không có job sẽ liên tục poll một queue rỗng; nó có thể tốn một lõi CPU đáng kể, gây can nhiễu các thread khác, và vẫn **không có termination protocol**.

Những hướng thiết kế:

1. Nếu nhiệm vụ đúng nghĩa **chờ đến khi có item**, dùng `BlockingQueue.take()` (hoặc `BlockingDeque.takeFirst/takeLast`).
2. Nếu cần poll không chặn, caller có thể **làm việc hữu ích khác** khi queue rỗng.
3. Nếu event loop phải poll, dùng một chiến lược yield/park/backoff có giới hạn và **cơ chế tín hiệu đánh thức** thích hợp; không lấy `Thread.sleep` như giải pháp duy nhất cho latency.
4. Nếu consumer cần kết thúc, dùng producer-completion signal/poison pill phù hợp, không chỉ kiểm tra `isEmpty`.
5. Nếu task có deadline, cân nhắc timed `poll(timeout, unit)` của **BlockingQueue**, không phải một overload có sẵn trên ConcurrentLinkedQueue.

### Bảng lựa chọn nhanh

| Nhu cầu | Cấu trúc phù hợp để cân nhắc |
| --- | --- |
| FIFO, non-blocking poll từ nhiều producers/consumers | `ConcurrentLinkedQueue` |
| Hai đầu, non-blocking, không cần capacity limit | `ConcurrentLinkedDeque` |
| FIFO, consumer muốn **block khi rỗng**, có optional capacity | `LinkedBlockingQueue` |
| FIFO bounded queue, backpressure cụ thể | `ArrayBlockingQueue` |
| Deque, consumer muốn block và có capacity | `LinkedBlockingDeque` |
| Handoff trực tiếp khi producer và consumer gặp nhau | `SynchronousQueue` |
| Trạng thái chia sẻ theo key | `ConcurrentHashMap` |
| Có priority ordering | `PriorityBlockingQueue` (cũng cần thiết kế overload riêng) |

Không có một cấu trúc “luôn nhanh nhất”. Kiểu thứ tự, chờ, capacity, fairness và khả năng drain là phần của yêu cầu nghiệp vụ.

## 11. `size()` O(n) và không được dùng như admission control

`ConcurrentLinkedQueue` và `ConcurrentLinkedDeque` dùng nodes liên kết, nên `size()` **không phải O(1)** như nhiều collection phổ biến. Việc tính size có thể phải duyệt các nodes: O(n). Nếu nhiều thread thêm/xóa đồng thời, số đếm nhận được có thể **không phản ánh một snapshot nhất quán**.

Hai hiểu nhầm phổ biến:

- “Queue thread-safe thì `size()` luôn là số chính xác của queue tại một mốc chung.” Không.
- “Tôi dùng `if (queue.size() < LIMIT) queue.offer(x)` là đã giới hạn queue.” Không.

Ngay cả nếu size chính xác ở thời điểm **đọc**, giữa check và offer, thread khác có thể thêm item. Với nhiều producers, limit bị vượt.

### Ví dụ 5 — hai producer cùng vượt giới hạn giả 1 item

Tạo `UnsafeCapacityCheck.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;

public class UnsafeCapacityCheck {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<Integer> queue =
                new ConcurrentLinkedQueue<>();
        CountDownLatch bothPassedCheck = new CountDownLatch(2);
        CountDownLatch allowEnqueue = new CountDownLatch(1);

        Runnable producer = () -> {
            if (queue.size() < 1) { // SAI: check rồi offer không atomic.
                bothPassedCheck.countDown();
                try {
                    allowEnqueue.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                queue.offer(1);
            }
        };

        Thread a = new Thread(producer);
        Thread b = new Thread(producer);
        a.start();
        b.start();

        bothPassedCheck.await();
        allowEnqueue.countDown();
        a.join();
        b.join();

        System.out.println("size after offers = " + queue.size());
        System.out.println("limit respected = " + (queue.size() <= 1));
    }
}
~~~

Chạy:

~~~bash
javac UnsafeCapacityCheck.java
java UnsafeCapacityCheck
~~~

Stdout khi không có interruption ngoài:

~~~text
size after offers = 2
limit respected = false
~~~

`bothPassedCheck.await()` buộc **cả hai thread kiểm tra size=0 trước khi ai được offer**. Sau khi mở latch, cả hai offer thành công, queue chứa 2 item mặc dù “giới hạn” dự kiến chỉ là 1. Kết quả là lỗi *check-then-act*, không phải lỗi của CAS bên trong `ConcurrentLinkedQueue`.

**Giải pháp đúng:** Khi cần capacity hữu hạn và cơ chế từ chối/chờ, sử dụng `ArrayBlockingQueue(cap)`, `LinkedBlockingQueue(cap)` hoặc `LinkedBlockingDeque(cap)`. Nếu buộc phải dùng concurrent linked structure cùng `Semaphore` để giới hạn in-flight, phải thiết kế acquisition/release-once cho toàn lifecycle (producer exception, dequeue, cancellation, shutdown), không chỉ dùng `size`.

`size()` có thể phù hợp cho **debug/monitoring thô** khi hiểu chi phí và độ chính xác, đặc biệt khi collection đã **quiescent** (không còn concurrent mutation). Nó không phải một primitive đồng bộ.

## 12. `peek()` rồi `poll()`: hai operation không phải một transaction

Một lỗi khá phổ biến:

~~~java
// MÃ SAI về check-then-act khi có nhiều consumer.
if (queue.peek() != null) {
    Job job = queue.poll();
    process(job); // job vẫn có thể null!
}
~~~

`peek()` và `poll()` riêng lẻ an toàn, nhưng consumer khác có thể lấy item trong khoảng giữa. `peek()` không giữ chỗ/phong tỏa phần tử cho caller. Cách đúng hơn:

~~~java
Job job = queue.poll();
if (job != null) {
    process(job);
}
~~~

Hãy gắn điều kiện xử lý với **chính kết quả poll** thay vì suy luận từ một peek cũ.

### Ví dụ 6 — chứng minh race peek-then-poll bằng latch

Tạo `PeekThenPollRace.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class PeekThenPollRace {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<Integer> queue =
                new ConcurrentLinkedQueue<>();
        queue.offer(42);

        CountDownLatch bothPeeked = new CountDownLatch(2);
        CountDownLatch allowPoll = new CountDownLatch(1);
        AtomicInteger gotItem = new AtomicInteger();
        AtomicInteger gotNull = new AtomicInteger();

        Runnable consumer = () -> {
            if (queue.peek() != null) {
                bothPeeked.countDown();
                try {
                    allowPoll.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }

                Integer item = queue.poll();
                if (item == null) {
                    gotNull.incrementAndGet();
                } else {
                    gotItem.incrementAndGet();
                }
            }
        };

        Thread a = new Thread(consumer);
        Thread b = new Thread(consumer);
        a.start();
        b.start();

        bothPeeked.await();
        allowPoll.countDown();
        a.join();
        b.join();

        System.out.println("got item = " + gotItem.get());
        System.out.println("got null = " + gotNull.get());
    }
}
~~~

Chạy:

~~~bash
javac PeekThenPollRace.java
java PeekThenPollRace
~~~

Stdout:

~~~text
got item = 1
got null = 1
~~~

Hai consumer **đều thấy 42 trong peek**, nhưng sau đó chỉ một consumer có thể thành công khi poll; consumer kia nhận null. Nhờ latch điều khiển thời điểm poll, ví dụ không phụ thuộc “đôi khi scheduler may mắn tạo race”. Điều cần nhớ: **mỗi method thread-safe không hợp thành một transaction thread-safe ở tầng nghiệp vụ**.

## 13. Iterator và Spliterator weakly consistent

Hai lớp cung cấp iterator/spliterator có khả năng chạy trong khi collection bị thread khác sửa. Javadoc gọi là **weakly consistent**:

- Không fail-fast bằng `ConcurrentModificationException` chỉ vì có đồng thời add/remove.
- Có thể quan sát một số thay đổi xảy ra trong lúc iterator đang chạy.
- Không có nghĩa iterator là snapshot cố định tại lúc được tạo.
- Không bảo đảm nhìn thấy **mọi** item được thêm sau lúc iterator được tạo.
- Không được coi traversal là nguyên tử hoặc có một thời điểm duy nhất mô tả toàn bộ kết quả.
- `ConcurrentLinkedDeque.descendingIterator()` cho phép duyệt hướng từ cuối về đầu nhưng cũng weakly consistent.
- `spliterator()` cung cấp một cách duyệt song song/partition traversal phù hợp hợp đồng, không biến source đang mutate thành snapshot toàn phần.

Một ví dụ không nên viết test khẳng định số phần tử luôn chính xác trong lúc đang enqueue:

~~~java
// Snippet minh họa, không độc lập.
Iterator<Integer> it = queue.iterator();
queue.offer(99);
while (it.hasNext()) {
    System.out.println(it.next()); // Không kết luận chắc có/không thấy 99.
}
~~~

Với `ConcurrentLinkedQueue`, contract iterator cung cấp thêm bảo đảm về những phần tử đã có trong queue từ khi iterator được tạo; tuy nhiên điều này **không** trao quyền dùng iterator làm một snapshot toán học của toàn bộ dữ liệu đang biến đổi. Đọc kỹ phạm vi bảo đảm trong Javadoc thay vì gọi mọi hành vi là “hoàn toàn ngẫu nhiên”.

### Khi nào muốn snapshot thật?

- Nếu **mọi producers/consumers đã dừng**, sao chép/duyệt queue khi không còn mutation cho kết quả ổn định hơn; ví dụ sau `join` tất cả threads.
- Nếu muốn **một transaction snapshot** giữa lúc có writers, concurrent queue một mình không đủ; cần một protocol khóa/snapshot/versioning hoặc một data model khác.
- Nếu chỉ cần monitoring gần đúng, có thể lấy số liệu approximate và đánh dấu là estimate.
- Nếu cần tổng tiền/inventory/billing nhất quán, không dùng `forEach` trên queue đang mutate làm bằng chứng cân đối giao dịch.

### Ví dụ 7 — duyệt snapshot sau khi worker đã dừng

Tạo `StableQueueTraversal.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

public class StableQueueTraversal {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<Integer> queue =
                new ConcurrentLinkedQueue<>();

        Thread producer = new Thread(() -> {
            queue.offer(1);
            queue.offer(2);
            queue.offer(3);
        });
        producer.start();
        producer.join();

        List<Integer> snapshot = new ArrayList<>(queue);
        System.out.println("snapshot = " + snapshot);
        System.out.println("queue unchanged = " + !queue.isEmpty());
    }
}
~~~

Chạy:

~~~bash
javac StableQueueTraversal.java
java StableQueueTraversal
~~~

Stdout:

~~~text
snapshot = [1, 2, 3]
queue unchanged = true
~~~

Đây là snapshot ổn định vì **producer đã `join` và không có thread khác sửa queue**. Constructor `new ArrayList<>(queue)` tự nó không tạo transaction trước writers đang chạy. `join` còn tạo quan hệ happens-before từ producer đã hoàn tất tới main, bên cạnh semantics publication của concurrent queue.

## 14. Bulk operations không nguyên tử trên toàn collection

Các thao tác như `addAll`, `removeIf`, `forEach`, `clear` hoặc duyệt và xử lý hàng loạt có thể tương tác với nhiều phần tử. Javadoc cảnh báo các bulk operations thêm/xóa/quan sát nhiều elements **không được bảo đảm atomic** trong presence of concurrent modifications.

Ví dụ:

~~~java
// MÃ MINH HỌA, không có transaction batch.
queue.addAll(List.of("A", "B", "C"));
~~~

Nếu consumer đang chạy, nó có thể quan sát một phần các item đã được thêm trước khi `addAll` trả về. Không kết luận rằng “một batch A,B,C xuất hiện đồng thời như một transaction”.

Tương tự, `removeIf(predicate)` có thể xem/xóa các phần tử trong một khoảng thời gian; những item được producer thêm đồng thời có thể nằm ngoài đợt duyệt hoặc chưa được xử lý theo cách bạn mong muốn. `clear()` không phải cơ chế “đóng queue” và không khóa producers khỏi enqueue thêm.

Với những trường hợp cần **atomic batch publication**, có thể đặt cả batch vào **một immutable holder object** (ví dụ `Queue<List<Job>>`) rồi offer holder đó thành một phần tử; cần thiết kế ai xử lý batch, idempotency, memory footprint, failure policy và mức atomic ở tầng nghiệp vụ. Một queue operation chỉ đảm bảo tính nguyên tử khi **đưa một reference tới batch** vào queue, không thực hiện transaction các side effects bên trong batch.

## 15. Memory visibility và happens-before

Concurrent collections được thiết kế không chỉ để tránh corrupt structure mà còn để cung cấp hiệu ứng **memory consistency** cho việc chuyển giao object qua collection.

Theo Java SE 17 Javadoc của `ConcurrentLinkedQueue` và `ConcurrentLinkedDeque`: những hành động của một thread **trước khi đặt object vào collection** *happen-before* những hành động của thread khác **sau khi access hoặc remove chính element đó** từ collection.

~~~text
Producer:
  Task t = new Task(7, "ready");
  queue.offer(t);
      |         publication qua concurrent collection
      +-------------- happens-before --------------+
                                                   |
Consumer:                                          v
  Task received = queue.poll();
  // Khi nhận được t, các ghi trước offer được publish phù hợp.
~~~

Điều này rất hữu ích cho producer–consumer. Không cần giữ cùng một `synchronized` ở bên ngoài **chỉ để publish một object đã khởi tạo đầy đủ**, nếu mọi trao đổi qua concurrent collection đúng contract.

Nhưng cần phân biệt:

- **Safe publication** của state đã chuẩn bị trước enqueue.
- **Mutation sau publication** của object ấy.

Khi producer `offer` một `ArrayList` rồi tiếp tục sửa list trong lúc consumer đọc, queue **không** bảo vệ các sửa đổi đó. Tương tự, việc một element là `AtomicReference<Mutable>` không làm object mutable bên trong trở nên thread-safe. Nên dùng immutable values, defensive copy, ownership transfer không sửa thêm, hoặc synchronization riêng cho mutable state.

### Ví dụ 8 — chuyển record immutable qua queue

Tạo `QueueSafePublication.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;

public class QueueSafePublication {
    record Message(int id, String payload) {}

    public static void main(String[] args) throws InterruptedException {
        ConcurrentLinkedQueue<Message> queue =
                new ConcurrentLinkedQueue<>();
        CountDownLatch published = new CountDownLatch(1);

        Thread producer = new Thread(() -> {
            Message message = new Message(7, "ready");
            queue.offer(message);
            published.countDown();
        });

        producer.start();
        published.await();

        Message received = queue.poll();
        System.out.println("id = " + received.id());
        System.out.println("payload = " + received.payload());

        producer.join();
    }
}
~~~

Chạy:

~~~bash
javac QueueSafePublication.java
java QueueSafePublication
~~~

Stdout:

~~~text
id = 7
payload = ready
~~~

`Message` là record chứa hai component bất biến: một primitive và một `String` immutable. Producer tạo record đầy đủ **trước offer**, consumer nhận reference qua queue. Trong ví dụ, `CountDownLatch` chỉ điều phối thời điểm để output chắc chắn có item; ngay cả khi consumer poll liên tục và nhận thành công không dùng latch, semantics của concurrent queue vẫn hỗ trợ publication của những ghi xảy ra trước offer.

Đừng lấy code này làm bằng chứng rằng queue tự đảm bảo atomic transaction giữa **nhiều** messages hoặc tự phục hồi khi producer bị crash trước offer.

## 16. Queue rỗng, hoàn tất producer và graceful shutdown

Không có `close()` chung trên `ConcurrentLinkedQueue`/`ConcurrentLinkedDeque` để mọi consumer đang poll tự nhận end-of-stream. Muốn dừng có trật tự, cần định nghĩa **protocol hoàn tất**.

Một mô hình:

~~~text
RUNNING
  | producer gửi work
  v
STOP_ACCEPTING
  | ngừng nhận work mới; đợi producer hiện hữu enqueue xong
  v
PRODUCERS_FINISHED
  | gửi tín hiệu STOP hoặc bật flag completion đúng quy tắc
  v
DRAINING
  | consumer xử lý work đã nhận
  v
CONSUMERS_FINISHED
  | join/ack tất cả consumers; kiểm tra failure/in-flight
  v
TERMINATED
~~~

Có vài lựa chọn:

1. **Completion flag:** Coordinator đợi producer rồi đặt `AtomicBoolean done=true`. Consumer không thoát khi poll null **trước** lúc flag true; sau khi flag true, queue rỗng có thể là điều kiện kết thúc. Ví dụ `ConcurrentQueueWorkers` dùng cách này.
2. **Poison-pill sentinel:** Sau khi mọi producer kết thúc, enqueue các STOP elements theo protocol; nếu N consumers cùng poll, cần tính số tokens/ownership và cách bảo đảm mọi consumer nhận được tín hiệu.
3. **BlockingQueue:** Khi consumer cần chờ thay vì poll vòng, dùng `BlockingQueue.take()` cùng sentinel/completion logic. Cần xử lý capacity đầy và cancellation khi shutdown.
4. **Quản lý in-flight:** Consumer có thể đã poll item ra khỏi queue nhưng chưa xử lý xong. `isEmpty()` không phải bằng chứng mọi task đã hoàn tất; cần `join`/`Future.get`/ack từ tasks.

Khi một consumer nhận STOP và thoát nhưng vẫn còn item được producer thêm **sau STOP**, item có thể bị bỏ lại. Do đó phải đóng admission/đợi producer trước khi phát signal. Đây là giao thức **ứng dụng**, không phải tính chất tự động của concurrent queue.

## 17. Backpressure và rủi ro unbounded memory

Một điểm phân biệt lớn với bounded blocking queue:

- `ConcurrentLinkedQueue.offer(e)` không có limit cấu hình; đối với item hợp lệ, nó được thiết kế để enqueue thay vì trả `false` khi đã tới một capacity nghiệp vụ.
- `ConcurrentLinkedDeque.offerFirst/offerLast(e)` cũng không có bound.
- Nếu producer nhanh hơn consumer lâu dài, object tồn đọng có thể tăng, làm heap retention, GC pressure và latency tăng.
- Task có thể giữ reference tới payload, closure hoặc cấu trúc lớn; bộ nhớ tiêu thụ không chỉ bằng chi phí node.
- Nếu memory cạn, JVM có thể gặp `OutOfMemoryError`; đây không phải “rejection policy” dễ khôi phục.
- `isEmpty()` và `size()` không cung cấp admission control nguyên tử.

Ví dụ đơn giản: producer trung bình gửi 10.000 item/s trong khi consumer chỉ xử lý được 8.000 item/s. Backlog tăng khoảng 2.000 item/s trong giai đoạn ấy; sau 5 phút có thể tồn đọng khoảng 600.000 item, trước khi xét load variation và retries. Đây là phép tính định hướng, không phải dự báo hard guarantee.

**Hướng giải quyết:** dùng bounded structure khi cần hạn chế work đang chờ; đặt rate limiting, explicit rejection, backpressure, giới hạn in-flight, deadlines hoặc load shedding có chủ đích. “Non-blocking” tự nó không ngăn overload.

### Không dùng ConcurrentLinkedDeque làm priority queue vô hạn

Một số hệ thống `offerFirst(urgent)` để ưu tiên job mới, `offerLast(normal)` cho job thường. Cách này đơn giản nhưng nếu urgent đến liên tục, normal có thể chờ rất lâu. Nó cũng không hỗ trợ mức priority khác nhau bằng comparator, deadline scheduling hay fairness giữa categories. Cần đánh giá work starvation và SLA trước khi chọn thiết kế.

## 18. Khi nào chọn BlockingQueue hoặc BlockingDeque?

`ConcurrentLinkedQueue` và `ConcurrentLinkedDeque` **không có** các method `put`, `take` hay timed `offer/poll` do `BlockingQueue` cung cấp. Nếu điều bạn cần là producer **chờ khi đầy** và consumer **ngủ khi rỗng**, chọn loại có blocking semantics phù hợp.

| Trường hợp | Công cụ dễ phù hợp |
| --- | --- |
| Một consumer không muốn spin khi rỗng | `LinkedBlockingQueue.take()` |
| Cần capacity cố định, kiểm soát memory | `ArrayBlockingQueue(capacity)` |
| Cần hai đầu và blocking wait | `LinkedBlockingDeque(capacity)` |
| Cần chờ tối đa 1 giây rồi timeout | `BlockingQueue.poll(1, TimeUnit.SECONDS)` |
| Không cần blocking, poll nhanh, nhiều thread | `ConcurrentLinkedQueue.poll()` |
| Non-blocking hai đầu với head/tail semantics | `ConcurrentLinkedDeque.pollFirst/pollLast` |

### Ví dụ 9 — BlockingQueue thay thế polling nóng

Tạo `BlockingQueueConsumer.java` (Java 17+):

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BlockingQueueConsumer {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

        Thread worker = new Thread(() -> {
            try {
                String first = queue.take();
                String second = queue.take();
                System.out.println("received = " + first + "," + second);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        worker.start();
        queue.put("A");
        queue.put("B");
        worker.join();
    }
}
~~~

Chạy:

~~~bash
javac BlockingQueueConsumer.java
java BlockingQueueConsumer
~~~

Stdout:

~~~text
received = A,B
~~~

Nếu queue rỗng, `take()` đợi cho tới khi producer gửi item hoặc thread bị interrupt. Nếu bounded queue đầy, `put` cũng có thể đợi capacity. Đây là **blocking producer–consumer protocol**, không phải hoạt động của `ConcurrentLinkedQueue`.

Không nên dùng ví dụ này cho một consumer vô hạn mà không có phương án shutdown: `take()` có thể đợi mãi nếu không còn producer. Cần sentinel/interrupt/cancellation đúng lifecycle.

## 19. Deque và cách dùng trong work-stealing có giới hạn

Các work-stealing schedulers thường có khái niệm worker sở hữu một deque công việc, còn worker khác có thể lấy bớt nhiệm vụ từ đầu đối diện. `ConcurrentLinkedDeque` cung cấp thao tác hai đầu thread-safe, nhưng **không đủ để tự tạo một ForkJoinPool**:

- Một work-stealing scheduler cần quyết định task placement, ownership và queue ordering.
- Cần cơ chế đánh thức workers khi có work, tránh busy spinning không kiểm soát.
- Cần completion counting, task dependencies, cancellation và exception reporting.
- Cần chính sách bound memory và workload admission.
- Cần quản lý lifecycle của executor và worker thread.
- Cần kiểm soát fairness, starvation, ưu tiên và thời điểm shutdown.
- Cần đo contention, locality, cache misses và overhead của việc đưa/lấy task.

Trong ứng dụng, nếu chỉ cần chạy một thuật toán Fork/Join đệ quy trên CPU, hãy cân nhắc `ForkJoinPool` và `RecursiveTask` thay vì xây scheduler riêng từ một concurrent deque. `ConcurrentLinkedDeque` hữu ích khi **điều khiển hai đầu là yêu cầu trực tiếp của data flow**, không phải vì tên gọi trông giống work-stealing.

## 20. Bulk iteration, toArray và snapshot semantics

`toArray()` hoặc `new ArrayList<>(queue)` sao chép những phần tử được duyệt ở một thời điểm thực thi. Nhưng nếu producers/consumers vẫn sửa collection:

- Chúng **không** tự tạo một transaction snapshot.
- Có thể phản ánh những trạng thái ở các thời điểm khác nhau.
- Thứ tự và số lượng có thể biến đổi khi traversal diễn ra.
- Các object được copy là **references**, không deep clones. Nếu object mutable vẫn bị writer khác sửa, bản copy không làm chúng immutable.
- Iterator weakly consistent không đảm bảo một snapshot toàn cục phù hợp để làm financial reconciliation.

Nếu cần chụp snapshot để debug, đợi một điểm *quiescent* do coordinator xác nhận hoặc dùng data structure/protocol khác. Không dùng `size` rồi `toArray` và coi hai kết quả phải luôn khớp trong lúc concurrent mutation.

### `descendingIterator()` trên ConcurrentLinkedDeque

`deque.descendingIterator()` duyệt ngược từ tail về head. Ví dụ với deque chứa [A,B,C] và không có concurrent writer, chiều forward là A,B,C; chiều descending là C,B,A. Khi writer thêm/xóa đồng thời, chiều duyệt vẫn tuân contract weak consistency chứ không tạo snapshot.

Nếu cần thực thi business logic “xử lý mọi element đúng một lần” giữa lúc concurrent update, **iterator không phải consumer queue protocol**. Dùng `pollFirst`/`pollLast` để lấy quyền sở hữu item và xử lý, cùng ack/completion policy.

## 21. Object mutable trong queue: thread-safe container không đủ

Đây là ví dụ lỗi:

~~~java
// Snippet minh họa không an toàn nếu có mutation cạnh tranh.
class MutableTask {
    int attempts;
}

ConcurrentLinkedQueue<MutableTask> queue =
        new ConcurrentLinkedQueue<>();

MutableTask task = new MutableTask();
queue.offer(task);
task.attempts++; // Producer tiếp tục mutate sau publication.
~~~

Nếu consumer đồng thời đọc `attempts` hoặc cũng tăng `attempts`, các truy cập này có thể là data race. `offer` đảm bảo publication của trạng thái **trước** offer theo contract, không tự bảo vệ mutation **sau** offer.

Cách làm:

- Ưu tiên **record/immutable task description** như `Message(int id,String payload)`.
- Nếu dùng object mutable, thực hiện **ownership transfer** rõ: producer không sửa sau khi enqueue; consumer sở hữu object khi poll thành công.
- Nếu cùng object vẫn được nhiều threads dùng, đồng bộ field bên trong bằng lock, atomics hoặc protocol đúng.
- Nếu consumer cần trả kết quả cho producer, dùng một kênh/result `Future`/ack phù hợp, không để cả hai tự sửa field thường không khóa.
- Tránh tạo hai queue chứa cùng reference tới mutable object rồi nghĩ mỗi queue bảo vệ độc lập.

### Đừng nhầm visibility với atomicity của workflow

Even if a consumer correctly sees `attempts=0` at time of receiving item, việc thêm 1 vào attempts cùng lúc với thread khác vẫn có thể lost update. Queue không biến `attempts++` thành atomic RMW. Dùng `AtomicInteger`/lock/immutable replacement khi cần.

## 22. Test concurrency: kiểm chứng invariant, tránh phụ thuộc scheduler

Các ví dụ trong bài chọn đầu ra cố định bằng một trong các cách:

- **Chạy tuần tự:** ví dụ API cơ bản, để thứ tự FIFO/LIFO hiển nhiên.
- **Join tất cả threads:** tổng kết sau khi không còn producer/consumer tác động.
- **Tạo ID độc nhất và sort kết quả:** không suy đoán consumer nào được phần tử nào.
- **CountDownLatch:** điều phối chính xác một interleaving cho lỗi check-then-act.
- **Immutable record:** tránh data race ở state được trao qua queue.
- **CountDownLatch completion flag:** phân biệt queue tạm rỗng với producers đã kết thúc.

Nhưng hãy nhớ các demo có `await()` không timeout được viết để làm rõ semantics trên đường chạy bình thường; **test suite production nên dùng timed waits**, `try/finally` cleanup, và fail-fast nếu thread không tiến triển. Không dựa vào `Thread.sleep(100)` rồi đoán chắc race đã xảy ra.

### Những metric đáng theo dõi

- Enqueued/sec và dequeued/sec, tính cả từng đầu deque khi có ý nghĩa.
- End-to-end work latency (submit → start → complete), không chỉ poll latency.
- Pending/in-flight counts qua counter/ack protocol riêng nếu cần chính xác.
- Heap retained bởi queued payloads, node allocations và GC.
- CPU usage của consumer khi queue rỗng, đặc biệt poll loops.
- Duplicate processing/missing job hoặc số ack theo nghiệp vụ.
- Cancellation, retry, dead-letter và shutdown duration.
- Contention và tail latency trong workload thật.

Không tự cài một exact counter bằng `size()` mỗi khi hiển thị dashboard; phép duyệt O(n) trên queue dài có thể tự tạo chi phí đáng kể và vẫn không đảm bảo số đếm đồng bộ với producers.

## 23. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `ArrayDeque` thường với nhiều writer | Data race/corruption | `ConcurrentLinkedDeque` hoặc lock phù hợp |
| Hiểu `ConcurrentLinkedQueue.poll()` như `take()` | Consumer spin hoặc thoát sớm | Dùng blocking collection khi cần chờ |
| Enqueue `null` làm sentinel | `NullPointerException` | Sentinel non-null rõ kiểu |
| Dựa vào `queue.size() < capacity` | Race, vượt hạn mức, O(n) | Bounded queue hoặc admission protocol |
| `if (peek()!=null) poll()` rồi tin non-null | Consumer khác có thể lấy mất | Kiểm tra chính kết quả `poll()` |
| Dùng `forEach`/`toArray` làm snapshot chính xác | Weakly consistent, concurrent modifications | Quiescent point hoặc snapshot protocol |
| Nghĩ `addAll` xuất hiện nguyên tử | Consumer có thể thấy một phần batch | Đưa một immutable batch holder vào một slot hoặc lock thích hợp |
| Một thread sửa object sau khi `offer` | Data race với consumer | Immutable values hoặc ownership transfer |
| Cho rằng FIFO tức completion FIFO nhiều consumers | Xử lý hoàn thành khác thứ tự dequeue | Ack/result ordering nếu cần |
| Poll vòng vô hạn khi rỗng | Tốn CPU và không có termination | `BlockingQueue.take()` hoặc wait/notification protocol |
| Dùng unbounded queue với producer quá nhanh | Heap, GC, latency tăng | Capacity, backpressure, deadlines |
| Tin deque tự sắp xếp priority | Job thường có thể bị đói | Priority/scheduling cấu trúc phù hợp |
| Dựa vào iterator để “claim job” | Có thể xử lý cùng item bằng nhiều callers | `poll` để chuyển quyền sở hữu |
| Dùng `clear` như close/shutdown | Producer vẫn có thể enqueue lại | Stop admission + completion protocol |
| Không phân biệt active với queued tasks | `isEmpty` không có nghĩa xử lý xong | Count in-flight, await ack |
| Nghĩ non-blocking = wait-free | Không có bound số bước cho từng caller | Hiểu progress guarantee và contention |
| Tự implement work-stealing chỉ với CLDeque | Thiếu scheduler/lifecycle/fairness | Dùng ForkJoinPool khi phù hợp |

## 24. Câu hỏi tự kiểm tra

**1.** `ConcurrentLinkedQueue` có phải FIFO không?  
**Đáp án:** Có, phần tử được thêm vào tail và poll ở head. Nhưng nếu nhiều producers cùng enqueue, thứ tự xen kẽ giữa họ không cố định.

**2.** `poll()` trên queue rỗng chặn cho tới khi có item?  
**Đáp án:** Không. Nó trả `null` ngay; dùng `BlockingQueue.take()` nếu cần chờ.

**3.** `ConcurrentLinkedQueue.offer(null)` có được không?  
**Đáp án:** Không, ném `NullPointerException`. Null được dùng làm dấu hiệu rỗng của poll/peek.

**4.** Tại sao `size()` không phải primitive giới hạn queue?  
**Đáp án:** Nó là O(n), có thể không chính xác khi đang có concurrent modifications, và check-then-offer không atomic.

**5.** Có thể chắc rằng `peek()!=null` ngay sau đó `poll()!=null` không?  
**Đáp án:** Không. Consumer khác có thể poll phần tử đó trước; phải kiểm tra trực tiếp giá trị poll.

**6.** `ConcurrentLinkedDeque.push(x)` và `pop()` dùng đầu nào?  
**Đáp án:** Đầu first/head; tạo LIFO stack. `offerLast` và `pollFirst` tạo FIFO.

**7.** Một consumer pollFirst và một consumer pollLast trên deque có thể nhận cùng một item không?  
**Đáp án:** Một phần tử cụ thể không thể bị cả hai poll thành công đồng thời; mỗi successful removal lấy một element khỏi deque.

**8.** Iterator đang chạy có ném `ConcurrentModificationException` khi producer tiếp tục add?  
**Đáp án:** Không theo contract iterator weakly consistent của hai concurrent collections; nhưng không tạo snapshot nguyên tử.

**9.** `addAll(List.of(a,b,c))` có nguyên tử trên cả batch không?  
**Đáp án:** Không có bảo đảm đó; consumer có thể nhìn thấy một phần khi operation còn đang thực hiện.

**10.** `ConcurrentLinkedQueue` có bảo đảm memory visibility từ producer đến consumer qua element không?  
**Đáp án:** Có, hành động trước khi producer đặt element vào queue happens-before hành động sau khi consumer access/remove element ấy theo API; mutation sau publication vẫn cần protocol riêng.

**11.** Khi `queue.isEmpty()` true, có thể kết luận pipeline đã done không?  
**Đáp án:** Không. Producer có thể gửi thêm, hoặc consumer đã lấy item nhưng còn đang xử lý. Cần completion/ack protocol.

**12.** Một application muốn producer đợi khi queue đầy, consumer đợi khi queue rỗng và giới hạn 128 item. Nên chọn gì?  
**Đáp án:** Ví dụ `new ArrayBlockingQueue<>(128)` hoặc `LinkedBlockingQueue<>(128)`, với `put/take` và shutdown protocol; không tự đặt limit bằng `ConcurrentLinkedQueue.size`.

**13.** Khi task mới “urgent” luôn được `offerFirst` và consumer `pollFirst`, các task “normal” có thể bị trì hoãn dài không?  
**Đáp án:** Có. Đây không phải priority/fairness scheduler hoàn chỉnh; cần đánh giá starvation.

**14.** Queue thread-safe có khiến `job.count++` trên object lấy ra cũng thread-safe?  
**Đáp án:** Không. Phải bảo vệ mutable object hoặc giao quyền sở hữu rõ.

## Tài liệu tham khảo chính thức

- [`ConcurrentLinkedQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): FIFO, non-blocking, weakly consistent iterator, size O(n), bulk operations và memory consistency.
- [`ConcurrentLinkedDeque` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html): deque hai đầu, non-blocking concurrency, weak iterators, size và bulk semantics.
- [`Queue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html): `offer/poll/peek`, `add/remove/element`.
- [`Deque` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html): first/last, stack và queue mappings.
- [`BlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): blocking/timed methods và capacity.
- [`ArrayBlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): FIFO bounded queue.
- [`LinkedBlockingDeque` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html): blocking hai đầu, optional capacity.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model và happens-before.

**Ghi nhớ:** `ConcurrentLinkedQueue` giải bài toán FIFO concurrent không blocking; `ConcurrentLinkedDeque` giải bài toán thao tác concurrent ở hai đầu. Cả hai **không** phải blocking queues, **không** có capacity limit tự động, **không** biến `size/iterator/bulk operation` thành snapshot nguyên tử, và **không** bảo vệ mutation của object được chứa. Khi yêu cầu liên quan shutdown, quota hoặc nhiều bước, hãy thiết kế protocol rõ ràng ngoài bản thân collection.