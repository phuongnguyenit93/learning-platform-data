# ArrayBlockingQueue so với LinkedBlockingQueue trong Java Concurrency

## 1. Bài toán: chọn hàng đợi blocking phù hợp

Trong mô hình **producer–consumer**, producers sinh công việc rồi đưa vào một hàng đợi dùng chung; consumers lấy công việc ra để xử lý. Khi producers nhanh hơn consumers, hệ thống cần quyết định điều gì xảy ra với những công việc chưa xử lý: **chờ**, **từ chối**, hay **tích lũy backlog**.

Java cung cấp hai lựa chọn rất phổ biến trong `java.util.concurrent`:

- `ArrayBlockingQueue<E>`: hàng đợi **FIFO, dung lượng cố định**, lưu phần tử bằng một mảng, có tùy chọn fairness cho các threads đang chờ.
- `LinkedBlockingQueue<E>`: hàng đợi **FIFO, dựa trên linked nodes**, có thể chọn giới hạn dung lượng; **nếu không truyền capacity**, giới hạn danh nghĩa là `Integer.MAX_VALUE`.

Cả hai đều implement `BlockingQueue<E>`; đều hỗ trợ `put()` và `take()` có thể **chờ** khi hàng đợi đầy/rỗng. Điểm khác nhau quan trọng nằm ở **cấu trúc lưu trữ, cách giới hạn backlog, chi phí cấp phát, concurrency giữa producer/consumer và ảnh hưởng đến thread pool**.

Sau bài này, bạn sẽ:

1. Phân biệt bản chất **bounded** của ArrayBlockingQueue với **optionally bounded** của LinkedBlockingQueue.
2. Sử dụng đúng `add`, `offer`, `put`, `offer(timeout)`, `poll`, `take` và `poll(timeout)`.
3. Hiểu cả hai là FIFO **trong phạm vi thứ tự phần tử vào/ra queue**, không đảm bảo thứ tự hoàn thành của nhiều workers.
4. Giải thích fairness của ArrayBlockingQueue, các locks và chi phí lưu trữ của hai implementation.
5. Biết vì sao LinkedBlockingQueue không giới hạn thực tế có thể gây backlog/heap pressure và khiến `maximumPoolSize` của ThreadPoolExecutor không phát huy.
6. Áp dụng backpressure, bounded capacity, timeout, cancellation, poison pill và shutdown producer–consumer.
7. Chạy các ví dụ Java 17+ minh họa dung lượng/FIFO, giao nhận blocking, interruption và tương tác ThreadPoolExecutor.
8. Lựa chọn theo benchmark thay vì khẳng định một queue luôn nhanh hơn.

**Phạm vi:** Java SE/JVM concurrency nói chung, không phụ thuộc framework. Ví dụ dùng JDK 17+.

## 2. BlockingQueue là hợp đồng chung

`BlockingQueue<E>` mở rộng `Queue<E>` để hỗ trợ các thao tác thêm/lấy phần tử khi điều kiện chưa cho phép thực hiện ngay. Có **bốn cách phản ứng** với queue đầy hoặc rỗng.

| Thao tác | Ném exception | Giá trị đặc biệt tức thì | Chờ vô thời hạn | Chờ có timeout |
|---|---|---|---|---|
| Thêm phần tử | `add(e)` | `offer(e)` | `put(e)` | `offer(e, timeout, unit)` |
| Lấy và xóa phần tử | `remove()` | `poll()` | `take()` | `poll(timeout, unit)` |
| Chỉ xem đầu queue | `element()` | `peek()` | Không có trong interface | Không có trong interface |

Ý nghĩa cần nhớ:

- `add(e)`: nếu không chèn được do giới hạn dung lượng, có thể ném `IllegalStateException`. Không dùng như cách bình thường để chờ chỗ.
- `offer(e)`: thử ngay. Trả `true` nếu đã thêm; trả `false` nếu **hiện không còn chỗ**, không chờ.
- `put(e)`: có thể block cho tới khi có chỗ; ném `InterruptedException` nếu thread bị interrupt trong lúc chờ theo hợp đồng.
- `offer(e, timeout, unit)`: chờ tối đa khoảng thời gian cho phép; trả false nếu không có chỗ trong hạn; cũng có thể ném InterruptedException.
- `remove()`: lấy đầu queue, ném `NoSuchElementException` nếu rỗng.
- `poll()`: lấy đầu queue hoặc trả `null` nếu rỗng, không chờ.
- `take()`: chờ cho tới khi có phần tử, hoặc ném InterruptedException khi bị yêu cầu hủy.
- `poll(timeout, unit)`: chờ tối đa khoảng thời gian, trả null khi không có phần tử trong hạn.

**Không thêm `null` vào BlockingQueue.** Cả hai class ném `NullPointerException` cho phần tử null. Vì vậy `poll()==null` được dùng để biểu thị **không có phần tử** thay vì một giá trị hợp lệ của queue.

~~~java
BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);

queue.put("task-A");                   // có thể chờ khi đầy
boolean accepted = queue.offer("task-B"); // thử ngay
String first = queue.take();            // có thể chờ khi rỗng
String second = queue.poll();           // trả null nếu rỗng
~~~

Đây là **đoạn trích trong một method**, cần imports phù hợp và khai báo/handle `InterruptedException` cho `put/take`. Ví dụ không có threads cạnh tranh, nhưng những method này vẫn giữ contract blocking của chúng.

## 3. ArrayBlockingQueue: mảng cố định với capacity bắt buộc

Khởi tạo:

~~~java
BlockingQueue<String> queue =
        new ArrayBlockingQueue<>(100);
~~~

`ArrayBlockingQueue` là FIFO queue có **capacity cố định** được chỉ định khi tạo. Giá trị capacity phải ít nhất 1. Khi đã khởi tạo, không có `setCapacity` để thay đổi kích cỡ của mảng theo ý muốn.

Hình dung queue capacity 4:

~~~text
Mảng backing cố định 4 slots
┌────┬────┬────┬────┐
│ A  │ B  │    │    │
└────┴────┴────┴────┘
  ↑   ↑
  head/tail tiến theo vòng khi insert/remove

size = 2
remainingCapacity = 2

put(C) → đưa C vào slot trống
put(D) → queue đầy (size=4)
put(E) → producer phải đợi có consumer lấy bớt
~~~

ArrayBlockingQueue dùng cơ chế **circular array** với các chỉ số đưa phần tử vào/lấy phần tử ra. Việc có mảng cố định mang lại vài đặc điểm:

- Không cần cấp phát một **node wrapper mới** cho mỗi lần enqueue như linked nodes thông thường.
- Số reference slots của queue được cấp phát gần mức capacity ngay từ đầu; một queue capacity rất lớn vẫn có chi phí backing array ngay khi tạo, kể cả rỗng.
- Khi size đạt capacity, `offer` trả false, còn `put` đợi. Điều này tạo **backpressure** nếu producers dùng blocking API đúng cách.
- Cấu trúc có giới hạn giúp dự toán số **phần tử đang chờ**; tuy nhiên bản thân từng phần tử có thể rất lớn, nên capacity không tự đảm bảo memory usage dưới bất kỳ ngân sách nào.
- ArrayBlockingQueue có tùy chọn **fairness** cho những producers/consumers đang chờ quyền truy cập queue.

Constructor fairness:

~~~java
BlockingQueue<String> fairQueue =
        new ArrayBlockingQueue<>(100, true);
~~~

Tham số `fair=true` áp dụng chính sách FIFO cho các threads **đang chờ** khi thêm/lấy phần tử. Mặc định fairness là false. Tài liệu JDK cho biết bật fairness thường **giảm throughput** nhưng có thể giảm độ biến thiên thời gian đợi và tránh starvation giữa các waiter trong một số workload.

**Fairness không phải FIFO completion order của những task được consumers thực thi sau khi `take`.** Consumer A lấy task trước nhưng xử lý mất 20 giây; consumer B lấy task sau nhưng hoàn tất sau 2ms. B có thể xong trước A.

## 4. LinkedBlockingQueue: liên kết nodes, capacity tùy chọn

Khởi tạo có giới hạn:

~~~java
BlockingQueue<String> bounded =
        new LinkedBlockingQueue<>(100);
~~~

Khởi tạo không truyền giới hạn:

~~~java
BlockingQueue<String> effectivelyUnbounded =
        new LinkedBlockingQueue<>();
~~~

Theo Javadoc Java 17, constructor không tham số có capacity **`Integer.MAX_VALUE`**. Điều này **không đồng nghĩa vô hạn thực sự**: queue vẫn chịu giới hạn số nguyên, heap, overhead mỗi node và khả năng producer tạo/giữ đối tượng. Trên thực tế, chương trình có thể hết memory **rất lâu trước khi** đạt giới hạn danh nghĩa.

LinkedBlockingQueue sử dụng các **linked nodes** được tạo động khi thêm phần tử, trừ khi việc thêm sẽ vượt capacity. Mô hình:

~~~text
head → [node A] → [node B] → [node C] → tail
           ↑          ↑          ↑
         tham chiếu đến payload/task

Capacity = 100 (nếu truyền 100)
Size = 3
Remaining = 97

Không truyền capacity:
  bound danh nghĩa = Integer.MAX_VALUE
  queue vẫn có thể giữ backlog rất lớn
~~~

Điểm chú ý:

- LinkedBlockingQueue **có thể bounded** nếu gọi constructor với capacity dương. Không được nói mọi LinkedBlockingQueue đều unbounded.
- Nó **không** có tham số fairness boolean trong API constructor tiêu chuẩn tương đương `ArrayBlockingQueue(int, boolean)`.
- Mỗi lần chèn có thể cần node mới; tăng allocation và áp lực GC dưới một số workloads.
- Đổi lại, với producer/consumer hoạt động đồng thời, cấu trúc lock phân tách có thể cho throughput tốt trong nhiều tình huống.
- Oracle JDK mô tả linked queues **thường có throughput cao hơn** array-based queues nhưng **hiệu năng kém dễ dự đoán hơn** trong nhiều ứng dụng concurrent. Đây là xu hướng được tài liệu mô tả, **không phải benchmark guarantee**.
- Khi queue lớn, các nodes và references giữ payload trong heap; payload có thể không được garbage-collected cho tới khi bị lấy khỏi queue hoặc xóa.

### LinkedBlockingQueue cũng có backpressure nếu được bounded

~~~java
BlockingQueue<Job> workQueue =
        new LinkedBlockingQueue<>(500);
~~~

Đây là đoạn method giả định `Job` là class ứng dụng. Với capacity 500, hành vi khi đầy tương tự về mặt BlockingQueue contract: `offer` trả false, `put` chờ, timed `offer` có thể timeout.

Khả năng bounded vs unbounded là lựa chọn **constructor**, không phải thuộc tính bất biến của mọi implementation linked queue.

## 5. Bảng đối chiếu hai class

| Tiêu chí | ArrayBlockingQueue | LinkedBlockingQueue |
|---|---|---|
| Cấu trúc | Mảng vòng (circular array) | Linked nodes |
| Thứ tự | FIFO | FIFO |
| Capacity | **Bắt buộc**, cố định sau tạo | **Tùy chọn**; truyền capacity hoặc mặc định Integer.MAX_VALUE |
| Constructor không tham số | Không có | Có |
| `put` khi đầy | Block, interruptible | Block nếu đạt bound |
| `take` khi rỗng | Block, interruptible | Block, interruptible |
| `offer` khi đầy | False | False nếu bounded và đầy |
| `poll` khi rỗng | Null | Null |
| Chấp nhận null | Không | Không |
| Optional fairness | Có, `new ArrayBlockingQueue<>(n, true)` | Không có tham số fairness constructor tương tự |
| Đồng bộ nội bộ | Một `ReentrantLock` quản lý queue + điều kiện notEmpty/notFull | Locks riêng cho put và take + atomic count |
| Storage overhead | Backing array reference slots cấp sẵn | Linked nodes cấp phát động |
| Lưu lượng lớn | Có thể tốt, tùy contention/fairness | Có thể throughput cao hơn trong một số tình huống |
| Memory predictability | Dễ chặn backlog bằng capacity | Dễ chặn bằng capacity **nếu truyền bound**; nguy cơ nếu để mặc định |
| `ThreadPoolExecutor` khi queue đầy | Có thể mở rộng workers tới max/reject | Bounded: tương tự; mặc định: queue nhận lâu, max ít phát huy |

**Không có “winner” tuyệt đối.** Dựa trên tỷ lệ producers/consumers, memory, kích thước task, thời gian giữ queue, CPU/NUMA, contention và GC, kết quả benchmark có thể thay đổi.

## 6. Locking nội bộ: tại sao throughput có thể khác?

### ArrayBlockingQueue: một ReentrantLock

Một ArrayBlockingQueue dùng một lock bảo vệ các operations quan trọng trên mảng, cùng conditions `notEmpty` và `notFull`. Về nguyên tắc, cùng lock đó phối hợp cả enqueue và dequeue.

~~~text
Producer          single queue lock        Consumer
   |                    |                      |
   +---- enqueue ------►|                      |
                        |◄------ dequeue ------+
                        |
            notEmpty / notFull conditions
~~~

Khi nhiều producers và consumers hoạt động đồng thời, các thao tác trên queue có thể cạnh tranh lock chung. Tuy nhiên, việc giữ queue đơn giản, không tạo node mới cho từng item và có locality khác có thể giúp throughput trong một số workload.

### LinkedBlockingQueue: hai locks cho hai đầu

Implementation JDK của LinkedBlockingQueue dùng một lock cho phía `put` và một lock cho phía `take`, phối hợp bằng `AtomicInteger count` và conditions thích hợp.

~~~text
Producer                 LinkedBlockingQueue                Consumer
   |                       putLock                              |
   +---- enqueue ----------►|                                   |
                            |     AtomicInteger count          |
                            |            |                     |
                            |         takeLock ◄----- dequeue--+
~~~

Cách tách lock có thể cho **một producer và một consumer** tiến hành thêm/lấy đồng thời trong nhiều trường hợp, cải thiện throughput. Nhưng mỗi node được tạo/thu hồi và đồng bộ về size có overhead; cũng có những operations cần phối hợp cả hai locks.

**Đừng suy rằng hai locks = luôn nhanh gấp đôi.** Throughput phải đo với cùng workload, JVM, GC, number of producers/consumers, capacity, CPU, queue depth và kích thước phần tử.

## 7. Fairness: có trên ArrayBlockingQueue, không đồng nghĩa priority

~~~java
ArrayBlockingQueue<String> queue =
        new ArrayBlockingQueue<>(8, true);
~~~

`fair=true` hướng tới thứ tự **FIFO của các threads đã bị block** khi insert/remove. Nó không:
- biến queue thành priority queue;
- đảm bảo mọi task được xử lý xong theo FIFO;
- đảm bảo mọi thread có cùng CPU time;
- làm cho requests mới được ưu tiên theo thời điểm đến ở cấp ứng dụng;
- bảo đảm mọi thao tác không blocking có latency y hệt nhau;
- làm database/I/O của worker trở thành fair.

Đặc biệt, fairness của **queue access** không phải fairness của toàn bộ `ThreadPoolExecutor`. ThreadPoolExecutor còn có worker creation, scheduling, queueing, rejection và task duration.

Khi nào cân nhắc bật fairness?
- Có nhiều producers/consumers thường xuyên bị block tại queue.
- Muốn giảm khả năng một thread phải đợi quá lâu trong tình huống tranh lock.
- Chấp nhận tradeoff throughput/latency.
- Đã benchmark với đặc điểm tải thật.

Với đa số workload thông thường, bắt đầu từ mặc định `fair=false` rồi đo là hợp lý.

## 8. API quan trọng: backpressure phụ thuộc cách caller dùng queue

Giả sử capacity=2, hai task đã chiếm queue:

| Lời gọi thêm | Kết quả | Tác động lên producer |
|---|---|---|
| `queue.add(third)` | `IllegalStateException` khi queue đầy | Producer phải xử lý lỗi |
| `queue.offer(third)` | `false` | Producer có thể reject/route elsewhere |
| `queue.put(third)` | Block cho tới khi có chỗ hoặc bị interrupt | Producer bị chậm lại, tạo backpressure |
| `queue.offer(third, 100, MILLISECONDS)` | Chờ tối đa 100ms; false nếu quá hạn | Có timeout cho việc tiếp nhận |

Không thể nói “bounded queue tự làm producer chậm” trong mọi trường hợp. Nó làm producer chậm **nếu ứng dụng dùng `put` hoặc timed `offer` và chấp nhận đợi**. Dùng `offer` không chờ sẽ chuyển áp lực thành **từ chối**, còn dùng `add` có thể ném exception.

Tương tự phía consumer:

~~~java
String item = queue.take(); // chờ khi rỗng
String now = queue.poll();  // null ngay nếu rỗng
String maybe = queue.poll(1, TimeUnit.SECONDS);
~~~

Đoạn trích trong method khai báo/handle InterruptedException cho `take` và timed `poll`.

### Hai loại “trống”

1. Queue đang rỗng **tại thời điểm kiểm tra** không có nghĩa producers đã kết thúc.
2. Producers đã kết thúc không có nghĩa queue đang rỗng; còn nhiều tasks cần xử lý.

Do đó phải có protocol **kết thúc producer–consumer** rõ ràng (poison pill, close flag kèm timeout, executor shutdown hoặc ownership khác) thay vì suy từ một lần `queue.isEmpty()`.

## 9. Ví dụ độc lập 1: capacity, FIFO và offer

Chương trình chạy cùng một kịch bản trên ArrayBlockingQueue capacity=2 và LinkedBlockingQueue capacity=2. Nó xác nhận cả hai implement contract tương đương ở các thao tác cơ bản.

Lưu **BlockingQueueComparisonDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

public class BlockingQueueComparisonDemo {
    private static void check(String name, BlockingQueue<Integer> queue)
            throws InterruptedException {
        queue.add(10);
        queue.add(20);

        boolean thirdAccepted = queue.offer(30);
        int remaining = queue.remainingCapacity();

        int first = queue.take();
        boolean laterAccepted = queue.offer(30);
        int second = queue.take();
        int third = queue.take();

        System.out.println(name + ": offerWhenFull=" + thirdAccepted
                + ", remainingWhenFull=" + remaining
                + ", offerAfterTake=" + laterAccepted
                + ", fifo=" + first + "," + second + "," + third);
    }

    public static void main(String[] args) throws InterruptedException {
        check("array", new ArrayBlockingQueue<>(2));
        check("linked", new LinkedBlockingQueue<>(2));
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac BlockingQueueComparisonDemo.java
java BlockingQueueComparisonDemo
~~~

Output chính xác khi không có thread khác truy cập hai queues:

~~~text
array: offerWhenFull=false, remainingWhenFull=0, offerAfterTake=true, fifo=10,20,30
linked: offerWhenFull=false, remainingWhenFull=0, offerAfterTake=true, fifo=10,20,30
~~~

Giải thích: mỗi queue nhận 10 và 20 thì đầy. `offer(30)` trả false, không thêm phần tử. `take()` lấy 10; sau đó `offer(30)` trả true. Hai lần take kế tiếp trả 20 và 30. `remainingCapacity()` được chụp **ngay khi đầy** nên bằng 0.

**Bài học:** Cùng `BlockingQueue` contract, code producer–consumer có thể chuyển giữa hai implementations mà không đổi ý nghĩa cơ bản của `put/take/offer/poll`; nhưng memory/performance/queue policy sẽ khác.

## 10. Ví dụ độc lập 2: producer bị chặn ở put, consumer giải phóng chỗ

Chương trình dùng một queue capacity=1 và một producer. Queue đã chứa `"first"` trước khi producer cố thêm `"second"`. Main nhận một tín hiệu bắt đầu, lấy phần tử đầu, sau đó đợi producer hoàn tất và lấy phần tử mới. Kết quả không phụ thuộc tên thread hay `sleep`.

Lưu **QueueProducerConsumerDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class QueueProducerConsumerDemo {
    private static void run(String name, BlockingQueue<String> queue)
            throws InterruptedException {
        queue.put("first");
        CountDownLatch producerStarted = new CountDownLatch(1);
        AtomicBoolean producerInserted = new AtomicBoolean(false);

        Thread producer = new Thread(() -> {
            producerStarted.countDown();
            try {
                queue.put("second");
                producerInserted.set(true);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, name + "-producer");

        producer.start();
        producerStarted.await();

        // Có thể producer đã vào put() hoặc chưa, nhưng queue vẫn đầy
        // cho tới khi main lấy "first".
        String first = queue.take();
        producer.join();
        String second = queue.take();

        System.out.println(name + ": " + first + " -> " + second
                + ", inserted=" + producerInserted.get());
    }

    public static void main(String[] args) throws InterruptedException {
        run("array", new ArrayBlockingQueue<>(1));
        run("linked", new LinkedBlockingQueue<>(1));
    }
}
~~~

Chạy:

~~~bash
javac QueueProducerConsumerDemo.java
java QueueProducerConsumerDemo
~~~

Output:

~~~text
array: first -> second, inserted=true
linked: first -> second, inserted=true
~~~

**Vì sao an toàn?**

- Queue capacity=1 đã chứa first, nên second **không thể chèn thành công trước khi first được lấy**.
- Main đợi signal producer đã bắt đầu, rồi lấy first. Nếu producer đã vào `put`, nó được đánh thức khi queue có chỗ; nếu chưa vào `put`, nó sẽ chèn sau.
- Main dùng `producer.join()` để biết producer đã hoàn tất trước khi lấy second; không dựa vào một số mili giây `sleep`.
- `producerInserted` chỉ được đặt true **sau** khi put thành công.
- Tính đúng của ví dụ giả định không có yêu cầu interrupt ngoài và chương trình được cấp lịch chạy bình thường. Một `put` trên queue đầy có thể **chờ**; ở đây consumer luôn giải phóng chỗ.

Đừng viết test “sau `Thread.sleep(50)` chắc chắn producer đang WAITING”: scheduler không đảm bảo thời điểm đó. Latch thể hiện thứ tự điều phối, còn bản chất capacity đảm bảo không có chỗ cho second trước take.

## 11. Interruption và hủy khi đang chờ hàng đợi

Cả `put` lẫn `take` đều là các điểm chờ hỗ trợ `InterruptedException`. Khi một worker được yêu cầu shutdown, logic thường cần thoát một cách hợp tác:

~~~java
void consume(BlockingQueue<Job> queue) {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            Job job = queue.take();
            process(job);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }
    }
}
~~~

Đây là method minh họa tích hợp, `Job` và `process` do ứng dụng định nghĩa. `take` bị interrupt khi chờ thì method restore flag và return. Không bắt `InterruptedException` rồi âm thầm lặp vô hạn, vì điều đó có thể làm worker không phản hồi shutdown.

### Ví dụ độc lập 3: producer bị interrupt khi queue đầy

Lưu **QueueInterruptionDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public class QueueInterruptionDemo {
    private static void run(String name, BlockingQueue<String> queue)
            throws InterruptedException {
        queue.put("original");
        CountDownLatch producerStarted = new CountDownLatch(1);
        AtomicBoolean cancelled = new AtomicBoolean(false);

        Thread producer = new Thread(() -> {
            producerStarted.countDown();
            try {
                queue.put("new");
            } catch (InterruptedException e) {
                cancelled.set(true);
                Thread.currentThread().interrupt();
            }
        }, name + "-producer");

        producer.start();
        producerStarted.await();
        producer.interrupt();
        producer.join();

        System.out.println(name + ": cancelled=" + cancelled.get()
                + ", remaining=" + queue.take());
    }

    public static void main(String[] args) throws InterruptedException {
        run("array", new ArrayBlockingQueue<>(1));
        run("linked", new LinkedBlockingQueue<>(1));
    }
}
~~~

Chạy:

~~~bash
javac QueueInterruptionDemo.java
java QueueInterruptionDemo
~~~

Output:

~~~text
array: cancelled=true, remaining=original
linked: cancelled=true, remaining=original
~~~

Queue capacity=1 đầy với original. Producer chưa thể thành công khi thêm new; main gửi interrupt trước khi có consumer lấy original. Dù interrupt đến **ngay trước** hay **trong khi** put đang chờ, put phản ứng bằng InterruptedException; không có "new" được thêm. Producer đánh dấu cancelled rồi kết thúc; main join trước khi đọc trạng thái. Sau đó main lấy original vẫn đang trong queue.

**Giới hạn:** Interruption là **tín hiệu hợp tác**, không phải rollback cho side effects đã thực hiện ở các bước khác. Nếu producer thực hiện ghi database rồi mới put, việc bị interrupt khi put không tự hoàn tác database write.

## 12. ThreadPoolExecutor: khác biệt ảnh hưởng trực tiếp số workers

Khi hai queues được dùng làm `workQueue` của `ThreadPoolExecutor`, sự khác biệt về capacity có ảnh hưởng lớn đến việc executor tạo thêm workers.

Javadoc mô tả chính sách tiếp nhận task:

1. Khi workers dưới `corePoolSize`, ưu tiên tạo worker mới.
2. Khi đã đạt core, ưu tiên `workQueue.offer(task)`.
3. Chỉ khi queue không nhận được task mới thử tạo extra worker tới `maximumPoolSize`.
4. Nếu không queue được và không tạo worker thêm được, dùng `RejectedExecutionHandler`.

~~~text
execute(task)
    |
    +-- workers < core ? --------> tạo core worker
    |
    +-- queue.offer(task) ? -----> xếp hàng
    |
    +-- workers < max ? ---------> tạo extra worker
    |
    +---------------------------> reject/handler
~~~

Sơ đồ là **mô hình admission**, không mô tả đầy đủ các kiểm tra lại khi shutdown hoặc race. Điểm cốt lõi: **max không được dùng chỉ vì queue đang dài**.

### ArrayBlockingQueue(capacity) với ThreadPoolExecutor

Với `new ArrayBlockingQueue<>(10)`, queue có khả năng từ chối offer khi đủ 10 tasks chờ. Nếu worker count vẫn dưới max, executor có thể tạo thêm workers để chạy những task mới đến. Nếu cả max workers và queue đều đầy, handler được gọi.

### LinkedBlockingQueue() không truyền capacity

Với `new LinkedBlockingQueue<>()`, queue có capacity danh nghĩa rất lớn. Sau khi có core workers, những task mới thường tiếp tục được queue, **không kích hoạt tăng workers tới max** trong điều kiện bình thường. Nếu producer nhanh hơn consumer, memory và queue wait time có thể tăng rất lớn.

### LinkedBlockingQueue(capacity) với ThreadPoolExecutor

Với `new LinkedBlockingQueue<>(10)`, queue **cũng đầy** khi đạt capacity 10. Vì thế nó có thể kích hoạt extra workers/rejection **tương tự** ArrayBlockingQueue có capacity 10. Lựa chọn array hay linked **không tự quyết định** max có phát huy; quan trọng là **bound có thực sự được cấu hình hay không**.

Đừng dùng `maximumPoolSize=100` rồi kết luận pool sẽ tăng tới 100 nếu queue mặc định vẫn đủ chỗ.

## 13. Ví dụ độc lập 4: cùng core/max nhưng queue dẫn tới hành vi khác nhau

Lưu **QueueExecutorComparisonDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class QueueExecutorComparisonDemo {
    private static Runnable gated(
            CountDownLatch started, CountDownLatch release) {
        return () -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };
    }

    private static void boundedArray() throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch extraStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        boolean rejected = false;

        try {
            pool.execute(gated(firstStarted, release));
            firstStarted.await();
            pool.execute(() -> { }); // occupies one queue slot
            pool.execute(gated(extraStarted, release)); // extra worker
            extraStarted.await();
            try {
                pool.execute(() -> { }); // no more queue or workers
            } catch (RejectedExecutionException e) {
                rejected = true;
            }

            System.out.println("array: workers=" + pool.getPoolSize()
                    + ", queued=" + pool.getQueue().size()
                    + ", rejected=" + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    private static void unboundedLinked() throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 30, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>(),
                new ThreadPoolExecutor.AbortPolicy()
        );
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(gated(firstStarted, release));
            firstStarted.await();
            pool.execute(() -> { });
            pool.execute(() -> { });

            System.out.println("linked: workers=" + pool.getPoolSize()
                    + ", queued=" + pool.getQueue().size()
                    + ", maximum=" + pool.getMaximumPoolSize());
        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        boundedArray();
        unboundedLinked();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac QueueExecutorComparisonDemo.java
java QueueExecutorComparisonDemo
~~~

Output khi không có external interruption và workers không bị lỗi ngoài dự kiến:

~~~text
array: workers=2, queued=1, rejected=true
linked: workers=1, queued=2, maximum=2
~~~

**Tại sao?**

- **Array:** worker lõi đã được giữ ở latch, task thứ hai vào queue capacity=1. Task thứ ba làm queue offer thất bại nên executor tạo extra worker thứ hai. Cả hai workers còn bận, queue vẫn đầy, task thứ tư được chuyển qua AbortPolicy và bị reject.
- **Linked mặc định:** worker lõi đang bị giữ bận, hai task tiếp theo đều được queue vì capacity rất lớn. `maximumPoolSize=2` không có nghĩa executor phải tạo worker thứ hai khi queue vẫn nhận.
- Các latch giữ workers đúng thời điểm in, không phụ thuộc `Thread.sleep()`; sau đó main release các workers rồi shutdown pool.

**Thử nghiệm tiếp:** Thay `new LinkedBlockingQueue<>()` bằng `new LinkedBlockingQueue<>(1)` trong nhánh linked và chỉnh kịch bản tương tự nhánh array. Khi bounded, linked queue cũng có thể đầy và kích hoạt extra worker/rejection theo cùng admission rules.

**Không suy “array luôn tăng workers còn linked không bao giờ tăng”.** Hai hành vi khác nhau trong demo vì **capacity được chọn khác**, không phải chỉ vì backing representation.

## 14. Memory: queue bounded không có nghĩa total application memory bounded

Với ArrayBlockingQueue:
- Backing array có số slots cố định, thuận tiện dự toán overhead ở cấp queue.
- Nhưng mỗi element có thể giữ một object graph lớn. 100 tasks mỗi task capture 100 MB dữ liệu vẫn có thể vượt heap.
- Task đang chạy trên workers **không nằm trong work queue**, nên tổng số “requests in system” còn gồm active tasks.

Với LinkedBlockingQueue:
- Mỗi enqueue có thể tạo một linked node và giữ references tới payload.
- Nếu queue mặc định rất lớn, backlog tích lũy không được điều tiết ở cấp application.
- Nếu cấu hình capacity có hạn, số **items chờ** vẫn bị giới hạn, nhưng node allocation/GC có thể ảnh hưởng throughput.
- Khi task bị cancel nhưng vẫn ở queue, có thể còn giữ references cho tới khi được remove/thu hồi theo cơ chế quản lý; không mặc định cancel tự dọn mọi cấu trúc queue ngay.

Dự toán capacity tối thiểu cần xem:

~~~text
Outstanding work =
  running tasks + queued tasks + upstream pending tasks

Memory budget xấp xỉ:
  queue overhead
  + payloads trong queued tasks
  + state của running tasks
  + các buffers/caches khác
~~~

Công thức là mô hình định tính, **không phải số byte bảo đảm**. Muốn định lượng cần đo object sizes, sampling profiler, heap occupancy, allocation rate, queue depth và GC trên workload thật.

### Queue length cao là dấu hiệu gì?

Một queue dài cho thấy producer đang vượt qua năng lực xử lý trong một khoảng thời gian, hoặc consumers đang bị block/lỗi/chậm. Không nhất thiết queue implementation kém. Các nguyên nhân thường gồm:
- remote I/O chậm, connection pool nhỏ;
- số consumers ít;
- producer burst quá lớn;
- tasks giữ lock lâu hoặc retry liên tục;
- downstream rate limit;
- thiếu cancellation cho công việc đã hết hạn.

Tăng capacity có thể **giấu lỗi bằng cách tăng thời gian chờ**, không làm throughput tự tăng.

## 15. Backpressure: thiết kế từ hệ quả khi đầy

Hãy định nghĩa rõ yêu cầu nghiệp vụ:

1. **Được phép chặn producer?** Dùng `put` hoặc timed `offer`; tránh block event loop hoặc thread quan trọng tới deadline.
2. **Được phép từ chối?** Dùng `offer`, thông báo “quá tải” hoặc đường retry có kiểm soát.
3. **Phải xử lý mọi task?** Cần durable messaging/ack/retry protocol ngoài queue RAM nếu phải chịu process crash.
4. **Có hạn chờ?** Dùng timed `offer` và `poll`; nếu quá hạn, trả outcome rõ ràng.
5. **Có thể bỏ việc hết hạn?** Đặt deadline/expiry logic theo nghiệp vụ; queue không tự biết một HTTP request đã hết thời hạn.
6. **Có nhiều consumers không?** Chọn số consumers theo throughput thực, connection limit và memory budget.
7. **Tác vụ phụ thuộc nhau?** Tránh producer/consumer giữ tài nguyên rồi block trong queue tạo wait-cycle.

`BlockingQueue` không phải database transaction, không có persistent acknowledgment và không bảo đảm exactly-once execution khi process crash. Các operations queue an toàn trong JVM, nhưng sự bền vững/tính duy nhất xuyên hệ thống phải được xử lý riêng.

## 16. Shutdown producer–consumer đúng cách

`BlockingQueue` **không có phương thức close() chuẩn trong interface**. Một consumer đang ở `take()` trên queue rỗng có thể chờ mãi nếu producers đã kết thúc mà không có shutdown protocol.

Các cách hay gặp:
- **Poison pill:** enqueue một giá trị đặc biệt mà consumer nhận diện để thoát.
- **Interrupt:** khi phù hợp, interrupt consumer, để `take` ném InterruptedException và task cleanup.
- **Timed poll + lifecycle flag:** consumer thức dậy định kỳ, kiểm tra producerDone và queue đã được drain hay chưa.
- **ExecutorService.shutdown()/awaitTermination():** quản lý workers khi queue là work queue của executor, nhưng caller cần biết khác biệt giữa shutdown và shutdownNow.

### Poison pill không phải null

Vì `BlockingQueue` không nhận null, không dùng null làm sentinel được enqueue. Dùng đối tượng sentinel cụ thể hoặc một kiểu wrapper:

~~~java
sealed interface Message permits Data, Stop {}

record Data(String payload) implements Message {}

record Stop() implements Message {}
~~~

Đây là các khai báo kiểu Java 17 (cần đặt trong file/class phù hợp). Consumer kiểm tra `instanceof Stop` để thoát. Trong ứng dụng nhiều consumers, thông thường phải có **đủ stop tokens** cho số consumers cần kết thúc, hoặc một protocol broadcast/lifecycle tương đương.

**Đừng gửi stop quá sớm:** nếu producer còn có thể enqueue công việc sau stop token, consumer có thể dừng trước khi xử lý toàn bộ dữ liệu. Cần thứ tự “producers đã ngừng sinh việc → xác định queue drain/stop protocol → consumers kết thúc”.

### Không tin queue.isEmpty() một mình

~~~java
if (queue.isEmpty()) {
    return; // Có thể sai: producer chưa xong, item mới sẽ đến.
}
~~~

Đây là anti-pattern khi consumer được kỳ vọng chạy cho tới khi công việc toàn hệ thống hoàn tất. `isEmpty` chỉ nói trạng thái tại một thời điểm; không có transaction kết hợp với lifecycle của producers. Nếu cần chờ work mới, dùng `take`; nếu cần điều kiện kết thúc, dùng tín hiệu owner và kiểm tra đồng bộ thích hợp.

### Giới hạn của drainTo

`drainTo(collection)` chuyển nhiều phần tử đang có từ queue vào collection cho caller xử lý. Nó có thể giảm overhead so với gọi take nhiều lần trong một số workload. Tuy nhiên:
- Không có nghĩa các producers đồng thời bị dừng.
- Không đảm bảo toàn bộ queue còn rỗng sau khi drain vì producer mới có thể enqueue.
- Nếu collection đích ném exception trong quá trình chuyển, tình trạng một số phần tử đã được chuyển có thể làm cần xử lý recovery.
- Không gọi `drainTo(queue)` để chuyển vào chính nó; API từ chối/không hợp lệ.

## 17. FIFO và thứ tự thực thi: hai khái niệm khác nhau

Cả hai queues cung cấp FIFO cho các phần tử theo thứ tự chèn vào queue. Nhưng với **hai consumers**, thứ tự **xử lý xong** không được đảm bảo:

~~~text
Queue ban đầu: A, B

Consumer 1 take(A), xử lý 10 giây.
Consumer 2 take(B), xử lý 1 giây.

B có thể hoàn tất trước A
dù A được lấy ra khỏi queue trước B.
~~~

Tương tự nếu queue là `ThreadPoolExecutor.workQueue`, một task có thể được đưa trực tiếp tới extra worker thay vì xếp hàng khi queue đầy; thứ tự start/completion toàn pool không phải FIFO tuyệt đối.

Nếu nghiệp vụ yêu cầu xử lý **cùng một entity theo đúng thứ tự**, cân nhắc:
- Một consumer tuần tự cho mỗi partition/key.
- Phân vùng theo key và serialize từng partition.
- Sequence/version checking ở nơi commit kết quả.
- Idempotent operations và ordering protocol xuyên hệ thống.

Fairness flag của ArrayBlockingQueue không tự giải quyết thứ tự commit của nhiều workers.

## 18. Thread safety không có nghĩa mọi tổ hợp operations là atomic

Cả hai queues bảo vệ các operations của chúng theo hợp đồng concurrent collection; nhưng thao tác ghép như sau có thể bị tranh chấp:

~~~java
if (!queue.isEmpty()) {
    E item = queue.poll(); // vẫn có thể null
    use(item);
}
~~~

Đây là **pseudocode Java-like**, `E` và `use` giả định được định nghĩa. Giữa `isEmpty` và `poll`, một consumer khác có thể lấy phần tử cuối.

Giải pháp:
- Nếu cần lấy ngay nếu có, dùng **một `poll()`**, kiểm tra `null`.
- Nếu cần chờ, dùng **`take()`** hoặc timed `poll`.
- Nếu cần “kiểm tra rồi cập nhật nhiều tài nguyên cùng lúc”, thiết kế giao thức/lock phù hợp; BlockingQueue không làm mọi state ngoài queue thành atomic.
- Không dựa vào `remainingCapacity()` rồi mới `offer()` như một phép giữ chỗ. Producer khác có thể chiếm chỗ giữa hai lời gọi.

### Memory visibility/happens-before

Theo contract concurrent collections, **các hành động trong producer trước khi đặt đối tượng vào queue happen-before các hành động của consumer sau khi truy cập/lấy phần tử đó ra**. Vì vậy producer khởi tạo payload trước `put` và consumer nhận payload qua `take` sẽ có bảo đảm visibility phù hợp.

Tuy nhiên, nếu producer **tiếp tục sửa object mutable sau khi enqueue** mà thiếu đồng bộ, vẫn có thể data race. Queue publish reference an toàn; nó không biến mọi mutation tương lai của object thành thread-safe.

~~~java
record Event(String message) {}

BlockingQueue<Event> queue = new ArrayBlockingQueue<>(8);
queue.put(new Event("ready"));
Event received = queue.take();
System.out.println(received.message());
~~~

Đây là đoạn trích trong method có exception handling. Event record với thành phần immutable String phù hợp để chuyển ownership. Nếu event chứa List mutable, cần defensive copy/immutable snapshot để tránh thay đổi sau publication.

## 19. Benchmark và tuning: không kết luận chỉ từ tên implementation

Oracle Javadoc mô tả LinkedBlockingQueue thường có throughput cao hơn ArrayBlockingQueue trong nhiều tình huống, nhưng ít dễ dự đoán hơn. Điều này không đồng nghĩa:
- luôn nhanh hơn trên mọi CPU/JDK;
- có latency thấp hơn ở mọi percentile;
- có footprint thấp hơn;
- luôn ít contention hơn;
- có thể bỏ qua memory bounds.

Một thử nghiệm đúng cần:
1. So sánh **cùng capacity** khi nghiên cứu cấu trúc array vs linked.
2. Giữ cùng số producers/consumers.
3. Giữ cùng kích thước/phần việc mỗi item.
4. Đo throughput, p50/p95/p99 enqueue/dequeue latency, allocation rate và GC.
5. Tách case queue thường rỗng, thường đầy và dao động giữa hai trạng thái.
6. Thử fairness false/true nếu dùng ArrayBlockingQueue.
7. Thử bounded/unbounded **như hai policy riêng**, không gộp khác biệt vào so sánh tốc độ implementation.
8. Đo thread blocking time, context switches, heap usage và connection/resource pressure.
9. Dùng công cụ benchmark phù hợp như JMH khi cần số liệu nghiêm túc; không tự viết một vòng `System.nanoTime` duy nhất rồi kết luận.
10. Kiểm tra cả shutdown/cancellation/overload behavior, không chỉ happy path.

Trong một số hệ thống, giảm queue capacity tạo rejection sớm hơn nhưng **bảo vệ memory và tail latency** tốt hơn. Đây có thể là kết quả đúng về mặt vận hành ngay cả khi throughput cực đại giảm nhẹ.

## 20. Bảng quyết định: nên dùng loại nào?

| Tình huống | Gợi ý khởi đầu | Lý do |
|---|---|---|
| Cần giới hạn backlog rõ ràng, tối thiểu node allocation | `ArrayBlockingQueue<>(capacity)` | Backing array cố định, bounded từ đầu |
| Cần policy công bằng cho các waiter | `ArrayBlockingQueue<>(capacity, true)` | Có fairness flag; phải đánh đổi throughput |
| Muốn linked queue nhưng vẫn cần backpressure | `LinkedBlockingQueue<>(capacity)` | Optional bound, FIFO, put/take đầy đủ |
| Workload producer/consumer cạnh tranh cao | Benchmark cả hai **cùng capacity** | Linked có thể throughput tốt nhưng không đảm bảo trên mọi hệ thống |
| Dùng ThreadPoolExecutor với max cần phát huy khi queue đầy | **Một bounded queue**, array hoặc linked | Queue phải hết capacity mới kích hoạt extra workers |
| Muốn hấp thụ backlog không giới hạn thực tế | Cần cân nhắc kỹ, thường **không mặc định** | Linked không giới hạn capacity dễ tăng memory/latency |
| Muốn direct handoff, không giữ backlog | Xem `SynchronousQueue` | Một lựa chọn khác, không phải Array/Linked |
| Muốn queue không blocking cho nhiều producers/consumers | Xem `ConcurrentLinkedQueue` | Không có `take/put` blocking semantics |
| Muốn ưu tiên task theo priority | Xem `PriorityBlockingQueue` | Không phải FIFO như hai queue ở đây |
| Cần persistence/ack/retry sau process crash | Broker/durable store + protocol phù hợp | In-memory BlockingQueue không cung cấp durability |

Quyết định thực tế thường phụ thuộc **giới hạn queue** và **policy khi đầy** nhiều hơn chênh lệch tối ưu giữa array và linked.

## 21. Các lỗi code review hay gặp

**Lỗi 1 — Gọi LinkedBlockingQueue mặc định là “vô hạn thật”.** Capacity danh nghĩa là Integer.MAX_VALUE nhưng memory có hạn.

**Lỗi 2 — Nói LinkedBlockingQueue luôn unbounded.** Constructor `new LinkedBlockingQueue<>(n)` tạo bounded queue.

**Lỗi 3 — Nói ArrayBlockingQueue tự tăng capacity.** Capacity cố định sau khi tạo; không có auto-resize.

**Lỗi 4 — Gọi `offer` rồi không kiểm tra boolean.** Khi queue đầy, task có thể bị bỏ mà application tưởng đã nhận.

**Lỗi 5 — Dùng `put` ngay trong event-loop hoặc request thread không được phép block.** Khi queue đầy, caller có thể chờ lâu.

**Lỗi 6 — Bật fairness và mặc định mọi tasks sẽ hoàn tất đúng FIFO.** Fairness của threads chờ không quyết định thời gian xử lý.

**Lỗi 7 — Cấu hình ThreadPoolExecutor max rất lớn với unbounded LinkedBlockingQueue rồi nghĩ pool tự mở rộng.** Executor ưu tiên queue sau core.

**Lỗi 8 — Đặt capacity lớn để “sửa” consumer chậm.** Backlog tăng/latency tăng, throughput không tự tốt lên.

**Lỗi 9 — Dùng `null` như poison pill.** BlockingQueue không nhận null.

**Lỗi 10 — Consumer thấy `isEmpty()==true` thì thoát dù producers còn chạy.** Race với việc enqueue mới.

**Lỗi 11 — Nuốt InterruptedException trong vòng `take/put`.** Worker có thể không phản hồi shutdown.

**Lỗi 12 — Dựa vào `remainingCapacity` rồi `offer` và cho rằng có chỗ chắc chắn.** Check-then-act giữa hai threads không atomic.

**Lỗi 13 — Đem queue throughput benchmark ở hai capacity quá khác rồi quy cho cấu trúc array vs linked.** Cần so sánh cùng workload/policy.

**Lỗi 14 — Giữ mutable payload sau enqueue rồi thay field không đồng bộ.** Visibility khi publish không bảo vệ mutation tiếp theo.

**Lỗi 15 — Dùng `size()` làm điều kiện điều phối chính xác giữa nhiều threads.** Snapshot có thể đổi ngay; không phải reservation.

**Lỗi 16 — Nghĩ queue rỗng thì không có active tasks.** Worker có thể đang xử lý phần tử đã dequeue.

**Lỗi 17 — Dùng ArrayBlockingQueue capacity hàng triệu mà không tính cost backing array.** Mảng reference slots được cấp phát theo capacity.

**Lỗi 18 — Chọn LinkedBlockingQueue vì nghĩ “không có lock”.** Nó là blocking queue có đồng bộ locks; không phải lock-free.

**Lỗi 19 — Cho rằng FIFO queue nghĩa đúng một lần xử lý.** Task có thể throw, process crash hoặc caller retry; không có durable ack.

**Lỗi 20 — Đặt poison pill quá sớm hoặc thiếu tokens cho consumers.** Có thể mất việc cuối hoặc để consumers khác chờ vô hạn.

## 22. Checklist trước khi triển khai

- [ ] Queue có **capacity rõ ràng** và được chọn theo memory/latency budget?
- [ ] Nếu dùng LinkedBlockingQueue không tham số, đã hiểu bound=Integer.MAX_VALUE và rủi ro backlog?
- [ ] Đã phân biệt nhu cầu `offer` (không chờ), `put` (chờ), timed offer và `add` (exception)?
- [ ] Producer được phép block tới bao lâu? Có timeout/cancellation?
- [ ] Consumer dùng take/poll đúng với lifecycle và deadline?
- [ ] Có cần fairness giữa các waiter không? Đã đo tradeoff?
- [ ] Payloads có immutable/ownership rõ ràng sau enqueue?
- [ ] Có xử lý InterruptedException không nuốt tín hiệu?
- [ ] Có signal kết thúc producer–consumer (poison pill/interrupt/flag) hợp lệ?
- [ ] Queue có nhiều consumers và cần bảo toàn ordering nghiệp vụ không?
- [ ] Nếu là ThreadPoolExecutor workQueue, đã kiểm tra core→queue→max→reject?
- [ ] RejectedExecutionHandler có báo rõ task không được nhận không?
- [ ] Đã đo queue size, time-in-queue, throughput và tail latency?
- [ ] Có tính cả tasks đang chạy, backlog upstream và memory payload?
- [ ] Có case tất cả consumers block/throw, producers tiếp tục sinh việc?
- [ ] Đã load-test saturation và process shutdown, không chỉ throughput bình thường?

## 23. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `new LinkedBlockingQueue<>()` có phải một queue không bao giờ đầy?

**Đáp án:** Không. Capacity mặc định là `Integer.MAX_VALUE`, và heap có giới hạn. Ứng dụng có thể hết memory trước khi chạm tới bound danh nghĩa.

**Câu 2.** Cả hai queue đều FIFO, vậy hai consumers có chắc hoàn tất công việc theo đúng thứ tự lấy khỏi queue không?

**Đáp án:** Không. FIFO mô tả thứ tự phần tử được lấy; processing duration khác nhau làm completion có thể đảo.

**Câu 3.** `ArrayBlockingQueue<>(2)` đã có 2 items. `offer(newItem)` làm gì?

**Đáp án:** Trả `false` ngay, không block và không thêm phần tử.

**Câu 4.** Cùng queue đó, `put(newItem)` làm gì?

**Đáp án:** Có thể chờ đến khi consumer lấy bớt item, hoặc ném InterruptedException nếu thread bị interrupt khi chờ.

**Câu 5.** Vì sao ArrayBlockingQueue thường có memory predictability tốt cho queue capacity?

**Đáp án:** Nó dùng một backing array kích thước cố định, không tạo linked node cho mỗi item. Nhưng payloads giữ trong slots và active tasks vẫn tiêu thụ bộ nhớ.

**Câu 6.** LinkedBlockingQueue có thể bounded không?

**Đáp án:** Có: `new LinkedBlockingQueue<>(capacity)` với capacity dương.

**Câu 7.** Một ThreadPoolExecutor core=2 max=10 dùng unbounded LinkedBlockingQueue. Khi hai workers đều bận, tasks mới có làm pool tự tăng lên 10 ngay không?

**Đáp án:** Thông thường không. Work queue tiếp tục nhận tasks, executor ưu tiên queue sau khi đạt core.

**Câu 8.** Nếu muốn max phát huy khi backlog đạt giới hạn, có nhất thiết phải dùng ArrayBlockingQueue không?

**Đáp án:** Không. `LinkedBlockingQueue<>(n)` cũng bounded và có thể kích hoạt thêm workers khi đầy.

**Câu 9.** Fairness=true có đảm bảo business tasks kết thúc FIFO không?

**Đáp án:** Không. Fairness là chính sách với threads đang đợi queue access, không phải thứ tự hoàn tất của worker computation.

**Câu 10.** Vì sao không nên dùng `queue.isEmpty()` để quyết định consumer thoát khi producer còn hoạt động?

**Đáp án:** Producer có thể thêm item ngay sau khi kiểm tra; cần lifecycle/termination protocol riêng.

**Câu 11.** Với BlockingQueue, `poll()==null` có thể là một phần tử null thực sự được enqueue không?

**Đáp án:** Không. Queue không nhận null; null là tín hiệu không có phần tử tại thời điểm poll.

**Câu 12.** Đã có capacity bounded, vậy toàn bộ JVM có chắc không thể OOM không?

**Đáp án:** Không. Payloads có thể lớn, running tasks/upstream queues cũng dùng memory, ngoài ra còn nhiều nguồn cấp phát khác.

## 24. Tài liệu Java chính thức

- **ArrayBlockingQueue (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- **LinkedBlockingQueue (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
- **BlockingQueue (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- **ThreadPoolExecutor (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- **Concurrent Collections memory consistency (Java 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
- **Java Language Specification, Threads and Locks:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html

**Kết luận:** `ArrayBlockingQueue` và `LinkedBlockingQueue` đều là **FIFO BlockingQueue**, nhưng Array sử dụng **mảng cố định**, có fairness flag, còn Linked dùng **linked nodes** và chỉ bounded nếu **bạn chỉ định capacity** (mặc định Integer.MAX_VALUE). Chọn đúng cần xét **backpressure, queue capacity, allocation/GC, contention, task latency và tương tác với ThreadPoolExecutor**. Đừng suy unbounded backlog là giải pháp quá tải; hãy đặt giới hạn và chính sách khi đầy phù hợp với nghiệp vụ.
