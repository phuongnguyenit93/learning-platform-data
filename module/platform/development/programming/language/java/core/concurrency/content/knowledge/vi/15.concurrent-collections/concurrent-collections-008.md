# PriorityBlockingQueue, DelayQueue và SynchronousQueue trong Java Concurrency

Trong các **concurrent collections** của Java, không phải queue nào cũng tuân theo quy tắc “thêm vào cuối, lấy ở đầu” theo FIFO. Có queue chọn phần tử theo **độ ưu tiên**, queue chỉ cho phép lấy phần tử **sau thời điểm hết hạn**, và queue **không lưu phần tử nào**, chỉ chuyển giao trực tiếp giữa hai thread.

Ba kiểu cần phân biệt:

- **`PriorityBlockingQueue<E>`**: hàng đợi có tính thread-safe, lấy phần tử theo **thứ tự ưu tiên** do `Comparable` hoặc `Comparator` quy định. Không có capacity giới hạn được cấu hình trong API.
- **`DelayQueue<E extends Delayed>`**: hàng đợi các phần tử có thời điểm đến hạn. `take()` chỉ trả **phần tử ở đầu khi delay của nó đã hết**; phần tử khác đã có trong queue nhưng chưa đến hạn vẫn chưa được lấy.
- **`SynchronousQueue<E>`**: **hàng đợi dung lượng bằng 0**. Mỗi lần `put` phải gặp một thao tác `take` tương ứng; không tồn tại backlog lưu bên trong queue.

Cả ba thuộc `java.util.concurrent`, triển khai `BlockingQueue<E>`, giúp phối hợp giữa producer và consumer mà không phải tự viết `wait/notify`. Nhưng **cách chờ, cách đặt hàng và khả năng tiếp nhận công việc** khác nhau rất lớn. Bài tập trung vào Java core, không phụ thuộc Spring hay thư viện ngoài JDK. Ví dụ biên dịch bằng Java 17+.

## 1. BlockingQueue là hợp đồng chung, không phải cùng hành vi

`BlockingQueue<E>` đưa ra các nhóm phương thức:

| Nhu cầu | Không chờ | Chờ vô thời hạn | Chờ có thời hạn |
|---|---|---|---|
| Thêm phần tử | `offer(e)` trả boolean; `add(e)` có thể ném khi không nhận được | `put(e)` | `offer(e, timeout, unit)` |
| Lấy và xóa phần tử | `poll()` trả phần tử hoặc `null`; `remove()` có thể ném nếu không có phần tử | `take()` | `poll(timeout, unit)` |
| Quan sát phần tử đầu | `peek()` | Không có thao tác chờ tương ứng | Không có thao tác chờ tương ứng |

Đối với một bounded FIFO queue như `ArrayBlockingQueue`, `put` chờ khi đầy và `take` chờ khi rỗng. Nhưng ba queue trong bài có những điều kiện riêng:

- **PriorityBlockingQueue:** không có bound do ứng dụng đặt, nên `put` thường **không chờ vì đầy**; `take` chờ khi queue rỗng.
- **DelayQueue:** không có bound do ứng dụng đặt, `put` thường không chờ vì đầy; `take` chờ khi **không có phần tử nào đã đến hạn ở đầu**. Queue có `size() > 0` vẫn có thể khiến `take` tiếp tục chờ.
- **SynchronousQueue:** không có slot lưu, nên `put` chờ **consumer ghép cặp**, `take` chờ **producer ghép cặp**; `offer(e)` không timeout thường trả `false` nếu ngay lúc đó không có consumer sẵn sàng nhận.

Không queue nào trong ba kiểu chấp nhận `null` làm phần tử. Vì vậy `poll()` trả `null` là một tín hiệu “chưa lấy được”, nhưng lý do có thể là **rỗng, chưa đến hạn hoặc không có giao dịch ghép cặp**.

## 2. PriorityBlockingQueue: phần tử có ưu tiên cao được lấy trước

`PriorityBlockingQueue` là một blocking queue xây dựng trên cơ chế ưu tiên kiểu heap. Thứ tự đầu queue được xác định bằng:

1. **Natural ordering** khi kiểu `E` triển khai `Comparable<E>`, hoặc
2. **Comparator** truyền vào constructor.

Giá trị “cao ưu tiên” **không mặc định là số lớn hơn**. Với comparator tăng dần theo `priority`, số nhỏ hơn sẽ đứng trước. Nếu muốn số lớn hơn lấy trước, có thể đảo comparator.

```java
PriorityBlockingQueue<Integer> queue =
        new PriorityBlockingQueue<>();

queue.offer(30);
queue.offer(10);
queue.offer(20);
// Ba lần poll tiếp theo cho: 10, 20, 30.
```

Đây là **trích đoạn**, cần import `java.util.concurrent.PriorityBlockingQueue`. Tác vụ thêm theo 30 → 10 → 20 nhưng được lấy theo 10 → 20 → 30.

### Những đặc tính cần nhớ

- **Không phải FIFO:** queue chọn phần tử theo thứ tự comparator/natural ordering.
- **Không tự ổn định thứ tự cho phần tử bằng nhau:** hai phần tử có `compare(a,b)==0` không được bảo đảm lấy theo thứ tự enqueue.
- **Không bounded theo capacity của người dùng:** constructor nhận `initialCapacity` chỉ chỉ định **dung lượng lưu trữ ban đầu**, không phải giới hạn cứng.
- **`remainingCapacity()` trả `Integer.MAX_VALUE`** theo hợp đồng, không có nghĩa heap JVM còn từng ấy phần tử trống.
- **Có thể gặp `OutOfMemoryError`** nếu producer liên tục enqueue nhanh hơn consumer lấy ra.
- **Iterator không cam kết trả phần tử theo thứ tự ưu tiên.** Muốn xử lý đúng thứ tự, hãy dùng `poll()`/`take()` (hoặc sao chép và sort để hiển thị).
- **Khóa sắp xếp phải ổn định khi phần tử nằm trong queue:** nếu sửa field ảnh hưởng comparator sau `offer`, cấu trúc heap không tự reorder theo thay đổi đó.

### Ví dụ 1 — Ưu tiên và tie-breaker ổn định

Khi nhiều task có cùng priority, ta thêm **sequence** vào comparator để tạo thứ tự xác định:

Tạo file **`PriorityQueueDemo.java`**:

```java
import java.util.Comparator;
import java.util.concurrent.PriorityBlockingQueue;

public class PriorityQueueDemo {
    record Job(int priority, long sequence, String name) {
    }

    public static void main(String[] args) throws InterruptedException {
        Comparator<Job> order =
                Comparator.comparingInt(Job::priority)
                          .thenComparingLong(Job::sequence);

        PriorityBlockingQueue<Job> queue =
                new PriorityBlockingQueue<>(11, order);

        queue.offer(new Job(5, 0, "report"));
        queue.offer(new Job(1, 2, "hotfix"));
        queue.offer(new Job(1, 1, "alert"));
        queue.offer(new Job(3, 3, "email"));

        while (!queue.isEmpty()) {
            Job job = queue.take();
            System.out.println(job.name() + " (" + job.priority() + ")");
        }

        System.out.println("Remaining capacity: "
                + queue.remainingCapacity());
    }
}
```

```bash
javac PriorityQueueDemo.java
java PriorityQueueDemo
```

Kết quả:

```text
alert (1)
hotfix (1)
email (3)
report (5)
Remaining capacity: 2147483647
```

**Vì sao đúng?** Comparator sắp tăng theo priority; nếu bằng nhau thì sắp theo sequence. `alert` và `hotfix` đều có priority=1 nhưng sequence=1 được lấy trước sequence=2. `Job` là record chỉ chứa `int`, `long`, `String` nên key sắp xếp không bị mutate sau enqueue. Biến `11` trong constructor là *initialCapacity*, dù queue vừa lấy bốn item thì `remainingCapacity` vẫn theo contract của queue không bounded.

Trong code production, sequence thường được cấp bằng `AtomicLong.getAndIncrement()` để các producer đồng thời có sequence duy nhất. Nếu đòi thứ tự tuyệt đối giữa các producer, phải định nghĩa rõ thứ tự nộp và cách gán sequence. Không tự suy thứ tự log từ nhiều thread chính là thứ tự offer của queue.

## 3. PriorityBlockingQueue không bảo đảm “task priority cao chạy xong trước”

Giả sử consumer A đã lấy task ưu tiên thấp và bắt đầu xử lý. Sau đó một task ưu tiên rất cao được enqueue. Queue **không preempt** task đang chạy ở consumer A để dành CPU cho task mới.

```text
t0: worker A lấy low-priority task và bắt đầu chạy.
t1: producer thêm high-priority task.
t2: worker B hoặc A ở vòng lấy tiếp nhận high-priority task.
t3: thứ tự hoàn thành còn phụ thuộc thời gian chạy.
```

Do đó cần phân biệt:

- **Priority of dequeue:** phần tử nào được lấy trước trong tập phần tử đang chờ?
- **Priority of execution/completion:** task nào bắt đầu, tiêu tốn CPU hoặc kết thúc trước?

`PriorityBlockingQueue` chỉ trực tiếp quyết định quy tắc **lấy từ queue**, không thay thế cơ chế ưu tiên thread của JVM/OS, không hủy tác vụ đã chạy và không đảm bảo hoàn thành có thứ tự. Nếu nhiều thread cùng `take()`, lời lấy của chúng có thể diễn ra gần nhau; lịch thực thi các task vẫn thay đổi.

### Vấn đề starvation

Nếu liên tục có item priority cao đến queue, các item ưu tiên thấp có thể bị chờ rất lâu (**starvation**). Queue không tự “aging” tăng độ ưu tiên của tác vụ đã chờ lâu. Khi thiết kế scheduler, có thể cân nhắc deadline, quota, aging, nhiều queue tách luồng hoặc giới hạn tốc độ nộp; việc đó vượt ra ngoài comparator đơn giản.

**Không thay field priority khi task đang nằm trong queue** để triển khai aging một cách ngây thơ. Cách an toàn cần một giao thức lấy ra/cập nhật/đưa lại hoặc cấu trúc scheduler được thiết kế cho priority động.

## 4. DelayQueue: lấy phần tử chỉ khi đã đến hạn

`DelayQueue<E extends Delayed>` giữ các object triển khai `Delayed`. Interface này yêu cầu:

```java
long getDelay(TimeUnit unit);
int compareTo(Delayed other);
```

Đây là **chữ ký phương thức**, không phải một class chạy độc lập. `Delayed` mở rộng `Comparable<Delayed>`. Trong một implementation thông thường:

- Mỗi phần tử lưu **deadline** bất biến được tính từ một mốc `System.nanoTime()` cộng thêm khoảng delay.
- `getDelay(unit)` trả khoảng thời gian còn lại; giá trị **≤ 0** nghĩa đã đến hạn.
- `compareTo` sắp phần tử theo deadline để **deadline sớm nhất ở đầu queue**.
- `take()` chỉ trả phần tử khi phần tử đứng đầu đã hết delay; nếu chưa, nó chờ.
- `poll()` trả `null` khi đầu queue chưa đến hạn, **ngay cả khi `size() > 0`**.

`DelayQueue` lưu nhiều item nhưng *không tự chạy task* khi đến hạn. Nó chỉ làm cho item đủ điều kiện được lấy; vẫn cần một consumer đang gọi `take()`/`poll` rồi tự thực hiện hành động nghiệp vụ.

### Đồng hồ và trật tự

Dùng `System.nanoTime()` để biểu diễn **thời hạn tương đối** cho delay, vì nó thích hợp đo khoảng thời gian, không phải thời điểm lịch. Không so sánh trực tiếp một deadline nanoTime với `System.currentTimeMillis()`: hai giá trị có ý nghĩa khác nhau.

Nếu dùng `System.nanoTime() + delayNanos`, cần để ý overflow với delay cực lớn hoặc các deadline được tạo xa nhau bất thường. Với thời hạn thông thường nhỏ hơn phạm vi khoảng thời gian an toàn, code dưới đây đủ minh họa. Trong ứng dụng thực, chuẩn hóa đơn vị `TimeUnit` và quy định delay âm/0 có được chấp nhận không.

## 5. Ví dụ 2 — DelayQueue với thời điểm hết hạn xác định

Ví dụ thêm phần tử **không theo thứ tự đến hạn**, rồi lấy bằng `take()`. Để stdout ổn định, deadline được tạo từ cùng một mốc, khác nhau rõ ràng; không in số mili giây thực tế, vì thời gian scheduling thay đổi giữa các lần chạy.

Tạo file **`DelayQueueDemo.java`**:

```java
import java.util.concurrent.DelayQueue;
import java.util.concurrent.Delayed;
import java.util.concurrent.TimeUnit;

public class DelayQueueDemo {
    static final class Message implements Delayed {
        private final String name;
        private final long deadlineNanos;

        Message(String name, long deadlineNanos) {
            this.name = name;
            this.deadlineNanos = deadlineNanos;
        }

        @Override
        public long getDelay(TimeUnit unit) {
            long remaining = deadlineNanos - System.nanoTime();
            return unit.convert(remaining, TimeUnit.NANOSECONDS);
        }

        @Override
        public int compareTo(Delayed other) {
            Message that = (Message) other;
            return Long.compare(this.deadlineNanos, that.deadlineNanos);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        DelayQueue<Message> queue = new DelayQueue<>();
        long now = System.nanoTime();

        queue.offer(new Message(
                "later", now + TimeUnit.MILLISECONDS.toNanos(150)));
        queue.offer(new Message(
                "ready", now - TimeUnit.MILLISECONDS.toNanos(10)));
        queue.offer(new Message(
                "soon", now + TimeUnit.MILLISECONDS.toNanos(50)));

        System.out.println("First: " + queue.take().name);
        System.out.println("Second: " + queue.take().name);
        System.out.println("Third: " + queue.take().name);
        System.out.println("Remaining: " + queue.size());
    }
}
```

```bash
javac DelayQueueDemo.java
java DelayQueueDemo
```

Kết quả:

```text
First: ready
Second: soon
Third: later
Remaining: 0
```

**Diễn giải:** cả ba phần tử được enqueue trước khi gọi take. `ready` đã quá hạn, đứng đầu và được trả ngay; `soon` có deadline sớm hơn `later`, nên được lấy tiếp khi đến hạn. `take()` có thể chờ tới lúc deadline tới, không phải cứ queue có phần tử là lấy ngay. Thời gian thực tế có thể thay đổi vì JVM/scheduler, nhưng **thứ tự theo deadline đã khai báo không đổi**.

`compareTo` ở ví dụ giả định mọi phần tử trong queue là cùng class `Message`; đây là đúng với `DelayQueue<Message>`. Nếu triển khai Delayed để trộn nhiều loại object, cần định nghĩa comparator tương thích, đối xứng, truyền tính và phản ánh đúng độ ưu tiên.

## 6. DelayQueue và ScheduledExecutorService có giống nhau?

Chúng liên quan về ý tưởng **đến hạn**, nhưng khác trách nhiệm:

| Công cụ | Chịu trách nhiệm gì? | Không tự làm gì? |
|---|---|---|
| `DelayQueue<E extends Delayed>` | Lưu item theo deadline, chỉ cho phép consumer lấy sau khi hết delay. | Không tự thực thi `Runnable`, không tạo scheduler worker. |
| `ScheduledExecutorService.schedule(...)` | Lên lịch thực thi `Runnable`/`Callable` sau delay. | Không đảm bảo bắt đầu đúng từng nano giây do lịch chạy. |
| `ScheduledThreadPoolExecutor` | Executor có worker và queue công việc hẹn giờ nội bộ. | Không tự bảo đảm business deadline của tác vụ hoặc I/O timeout. |

`ScheduledThreadPoolExecutor` dùng cơ chế queue trì hoãn nội bộ có liên quan ý tưởng **delayed work**, nhưng không nên suy rằng constructor của nó nhận một `DelayQueue` do người dùng cung cấp theo cách `ThreadPoolExecutor` nhận `BlockingQueue<Runnable>`.

Các trường hợp dùng DelayQueue trực tiếp: cache entry hết hạn, thông báo retry không được xử lý trước deadline, item cần được đưa vào pipeline sau thời gian chờ, timeout task do ứng dụng tự quản lý. Tuy nhiên, với **scheduler chỉ cần gọi Runnable vào một thời điểm**, `ScheduledExecutorService` thường đơn giản hơn.

### Một item có “delay 0” nghĩa là gì?

Nếu `getDelay(NANOSECONDS) <= 0`, item đủ điều kiện được lấy; **không** có nghĩa nó tự biến khỏi queue hoặc tự chạy. Consumer phải gọi `take()`/`poll()`. Nếu không có consumer, item đã đến hạn vẫn nằm trong queue và `size()` vẫn tính nó.

`drainTo(collection)` của `DelayQueue` chỉ chuyển các phần tử **đã hết delay** theo hợp đồng, không lấy các phần tử chưa đến hạn như một lệnh “drain toàn bộ bộ nhớ”. Một thao tác `clear()` (nếu được dùng) khác với chuyển quyền xử lý item đã đủ điều kiện.

## 7. DelayQueue: điều kiện chờ, tín hiệu và cancellation

Khi producer thêm một item có deadline **sớm hơn** item đang đứng đầu, consumer đang `take()` cần được đánh thức để đánh giá lại thời hạn đầu queue. `DelayQueue` xử lý điều phối này trong implementation, thay vì buộc bạn viết `Condition.awaitNanos()` bằng tay.

Cần lưu ý:

- `peek()` có thể trả phần tử **chưa đến hạn**; `poll()` khi chưa đến hạn lại trả `null`.
- `size() > 0` không đảm bảo `poll() != null`.
- `remainingCapacity()` là `Integer.MAX_VALUE`, nên không có bounded backlog tự nhiên; quá nhiều item có thể làm tăng heap.
- Nếu item thay đổi `deadlineNanos` **sau enqueue**, heap không tự sắp xếp lại. Giữ deadline immutable.
- Nếu consumer bị interrupt khi đang `take()`, nó có thể ném `InterruptedException`; code ứng dụng phải quản lý lifecycle và cleanup phù hợp.
- Nếu item bị hủy, cần định nghĩa rõ: xóa khỏi queue, đánh dấu canceled để consumer bỏ qua, hoặc để nguyên chờ rồi bỏ; không có một protocol cancellation nghiệp vụ tự động áp dụng cho mọi Delayed.
- Nếu có nhiều consumer, một item chỉ được lấy bởi một consumer; thứ tự **bắt đầu/hoàn tất xử lý** còn tùy scheduling.

Nếu cần **đúng một lần** thực thi qua nhiều JVM, DelayQueue in-memory không phải giải pháp đủ: tiến trình chết có thể làm mất item, và queue không cung cấp transaction/khôi phục.

## 8. SynchronousQueue: dung lượng 0, truyền tay trực tiếp

`SynchronousQueue<E>` khác hai queue trước về bản chất. Nó không chứa backlog nào, mà mỗi `put(e)` phải được ghép với một `take()` đang hoặc sắp đợi. Có thể hình dung một cuộc **rendezvous** giữa producer và consumer:

```text
Producer                             Consumer
--------                             --------
queue.put("work") ---- chờ ---->    queue.take()
                                        /
              ---- transfer item ------/
                    cả hai tiếp tục
```

Hợp đồng cơ bản:

- `put(e)` có thể chặn cho tới khi **một consumer nhận** e.
- `take()` có thể chặn cho tới khi **một producer gửi** e.
- `offer(e)` không chờ chỉ thành công nếu có một consumer phù hợp **sẵn sàng nhận ngay**.
- `offer(e, timeout, unit)` có thể đợi một khoảng cho có consumer; nếu không được ghép cặp sẽ trả false.
- `poll()` không chờ chỉ thành công khi có producer có thể chuyển giao ngay; `poll(timeout, unit)` đợi tới hạn cho producer.
- `size()` luôn là 0; `isEmpty()` luôn true; `remainingCapacity()` luôn 0; `peek()` luôn null.
- Không có phần tử tồn tại *giữa* lời gửi và lời nhận: chuyển giao xảy ra khi hai bên được ghép cặp.

**Đừng viết `if (queue.isEmpty()) ...` như cách kiểm tra xem SynchronousQueue có consumer đang chờ không.** Vì nó luôn báo empty theo contract, bất kể có thread đang đợi ở hai phía.

### Fairness

Constructor `new SynchronousQueue<>(true)` yêu cầu chính sách **fair** cho thứ tự thread đợi, còn mặc định là non-fair. Fairness ảnh hưởng việc chọn cặp waiter khi có cạnh tranh; nó **không tạo dung lượng**, không đảm bảo task chạy xong theo thứ tự và không biến chuyển giao thành giao dịch bền vững.

Fair mode có thể có đánh đổi hiệu năng tùy contention; không mặc định chọn nó hoặc bỏ nó mà không hiểu yêu cầu.

## 9. Ví dụ 3 — SynchronousQueue: offer thất bại, put chờ consumer

Ví dụ đầu tiên gọi `offer` khi chưa có consumer nên chắc chắn trả false. Sau đó tạo consumer, cho main `put` một item; `put` chỉ hoàn tất khi consumer nhận. `CountDownLatch` đồng bộ bước bắt đầu và `join()` bảo đảm kết quả in cuối không phụ thuộc thứ tự thread.

Tạo file **`SynchronousHandoffDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.atomic.AtomicReference;

public class SynchronousHandoffDemo {
    public static void main(String[] args) throws InterruptedException {
        SynchronousQueue<String> queue = new SynchronousQueue<>();
        System.out.println("Offer without consumer: "
                + queue.offer("early"));

        CountDownLatch consumerReady = new CountDownLatch(1);
        AtomicReference<String> received = new AtomicReference<>();

        Thread consumer = new Thread(() -> {
            consumerReady.countDown();
            try {
                received.set(queue.take());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        consumerReady.await();

        queue.put("delivered");
        consumer.join();

        System.out.println("Received: " + received.get());
        System.out.println("Queue size: " + queue.size());
        System.out.println("Remaining capacity: "
                + queue.remainingCapacity());
    }
}
```

```bash
javac SynchronousHandoffDemo.java
java SynchronousHandoffDemo
```

Kết quả khi không có interrupt ngoài:

```text
Offer without consumer: false
Received: delivered
Queue size: 0
Remaining capacity: 0
```

`consumerReady.countDown()` nằm ngay trước `take()`; main có thể gọi `put()` trước khi consumer thật sự vào take, nhưng khi đó **main chờ**, không mất item. Sau khi hai phía bắt cặp, `put` hoàn tất, `join` bảo đảm consumer đã ghi `received`. Đây là mô hình **backpressure tại lúc handoff**: producer không thể “đẩy vào queue cho xong” khi chưa có người nhận.

Không xem `SynchronousQueue` là queue capacity=1. Với capacity 1, producer có thể lưu một phần tử khi consumer chưa có mặt; còn SynchronousQueue **không lưu nổi một item** và luôn cần một phía giao dịch đối ứng.

## 10. Timeout và interrupt trên SynchronousQueue

Handoff có thể chờ rất lâu nếu không có đối tác. Vì vậy cancellation và timeout đặc biệt quan trọng:

```java
boolean transferred =
        queue.offer("work", 200, TimeUnit.MILLISECONDS);
```

Đây là trích đoạn cần khai báo `queue` và xử lý `InterruptedException`. Khi không có consumer trong thời gian đó, `transferred` trở thành false; nếu có consumer và ghép cặp thành công, trả true.

Một producer/consumer đợi trong `put`/`take` có thể bị interrupt. Thread nên xử lý `InterruptedException` theo chính sách lifecycle: ném tiếp, hoặc khôi phục cờ `Thread.currentThread().interrupt()` rồi thoát; **không nuốt interrupt và lặp vô hạn**.

Nếu bên gửi `put` kết thúc **thành công**, đã có consumer ghép cặp nhận phần tử. Nhưng điều đó **không** chứng minh consumer đã xử lý xong phần việc — consumer có thể vừa nhận item và đang tiếp tục chạy. Nếu cần xác nhận hoàn tất nghiệp vụ, dùng `Future`, latch, acknowledgement hoặc transaction riêng.

Mọi thao tác `offer/poll` không chờ đều bị ảnh hưởng bởi **thời điểm hai thread gặp nhau**; không nên viết test kỳ vọng nonblocking offer sẽ luôn true chỉ vì đã start một consumer. Một test đúng phải điều phối trạng thái chờ hoặc chọn `put/take` phù hợp.

## 11. SynchronousQueue trong ThreadPoolExecutor

`ThreadPoolExecutor` dùng `BlockingQueue<Runnable>` làm **work queue**. Trình tự tiếp nhận task thông thường:

1. Khi số worker thấp hơn `corePoolSize`, executor cố tạo worker để chạy task.
2. Sau khi đạt core, nó gọi `workQueue.offer(task)`.
3. Nếu `offer` thất bại, nó cố tạo thêm worker tới `maximumPoolSize`.
4. Nếu không thể nhận task và không thêm worker được, `RejectedExecutionHandler` quyết định việc từ chối.

Với **`SynchronousQueue`**, `offer(task)` thất bại khi không có worker rảnh đang chờ nhận trực tiếp. Vì queue không có slot, executor thường **tăng worker thay vì tích lũy backlog** khi có thêm task đang chạy, cho tới khi đạt maximum.

Điều này đối lập với `LinkedBlockingQueue` mặc định capacity lớn: sau khi đạt core, queue thường nhận task nên executor không cần tạo non-core worker trong đường admission thông thường.

### Ví dụ 4 — Hai worker đang bận, task thứ ba bị reject

Ta cấu hình core=1, max=2, `SynchronousQueue` và `AbortPolicy`. Hai task dùng latch để giữ worker bận; task thứ ba không có worker rảnh và pool đã đạt max nên bị từ chối. Nhờ điều phối latch, stdout không phụ thuộc tình cờ vào tốc độ task.

Tạo file **`SynchronousExecutorDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class SynchronousExecutorDemo {
    private static Runnable blockingTask(
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

    public static void main(String[] args) throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 0, TimeUnit.SECONDS,
                new SynchronousQueue<>(),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(blockingTask(firstStarted, release));
            firstStarted.await();

            pool.execute(blockingTask(secondStarted, release));
            secondStarted.await();

            boolean rejected = false;
            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException e) {
                rejected = true;
            }

            System.out.println("Pool size: " + pool.getPoolSize());
            System.out.println("Queue size: " + pool.getQueue().size());
            System.out.println("Third rejected: " + rejected);
        } finally {
            release.countDown();
            pool.shutdown();
        }

        boolean terminated = pool.awaitTermination(
                5, TimeUnit.SECONDS);
        System.out.println("Terminated: " + terminated);
        System.out.println("Completed worker tasks: "
                + pool.getCompletedTaskCount());
    }
}
```

```bash
javac SynchronousExecutorDemo.java
java SynchronousExecutorDemo
```

Kết quả bình thường:

```text
Pool size: 2
Queue size: 0
Third rejected: true
Terminated: true
Completed worker tasks: 2
```

Task thứ nhất chiếm core worker, task thứ hai không thể xếp hàng nên pool tạo worker thứ hai. Cả hai đều giữ ở `release` nên task thứ ba không tìm được worker đang đợi handoff và max=2 đã đạt: `AbortPolicy` ném `RejectedExecutionException`. Sau `release.countDown()`, hai worker hoàn tất; pool shutdown rồi `awaitTermination` xác nhận kết thúc.

Đừng suy rằng queue size=0 là “không có tác vụ”. Ở SynchronousQueue, **queue size luôn 0**, ngay cả khi nhiều worker đang chạy; để giám sát pool phải xem cả `getActiveCount()`, throughput, rejection và trạng thái lifecycle.

## 12. Vì sao Executors.newCachedThreadPool() cần thận trọng?

`Executors.newCachedThreadPool()` dùng cấu hình theo mô hình **direct handoff** với `SynchronousQueue`, có khả năng tạo nhiều worker mới khi chưa có worker rảnh để nhận task; giới hạn số thread tối đa rất cao theo implementation thông thường.

Ưu điểm: các task ngắn, phân bố không đều có thể được nhận nhanh, worker nhàn rỗi được tái sử dụng và dọn sau thời gian keep-alive.

Rủi ro: nếu task chặn lâu hoặc tốc độ nộp vượt xa khả năng hoàn tất, pool có thể tạo **quá nhiều thread**, gây tiêu thụ stack memory, context switching, tắc tài nguyên downstream hoặc `OutOfMemoryError`. Không tự xem cached pool là giới hạn năng lực hay backpressure an toàn.

Trong một dịch vụ cần giới hạn tài nguyên, có thể sử dụng `ThreadPoolExecutor` với **max worker cụ thể** và `SynchronousQueue`, cùng một rejection policy rõ ràng. Hoặc dùng bounded queue nếu muốn chấp nhận một lượng backlog hữu hạn. Lựa chọn dựa trên latency, CPU/I/O, hạn mức kết nối và SLA, không chỉ trên tên queue.

## 13. So sánh trực diện ba queue

| Tiêu chí | `PriorityBlockingQueue` | `DelayQueue` | `SynchronousQueue` |
|---|---|---|---|
| Lý do lấy phần tử | Theo **priority/comparator**. | Đầu queue đã **hết delay**. | Có producer và consumer **ghép cặp trực tiếp**. |
| Lưu phần tử trong queue | Có. | Có. | **Không**, capacity=0. |
| Dung lượng có bound qua constructor | Không. | Không. | Cố định bằng **0**. |
| `offer(e)` không chờ | Thường nhận nếu đủ bộ nhớ. | Thường nhận nếu đủ bộ nhớ. | Chỉ thành công nếu có consumer phù hợp ngay. |
| `take()` chờ khi | Queue rỗng. | Chưa có item đã đến hạn. | Chưa có producer ghép cặp. |
| `poll()` trả null khi | Rỗng. | Rỗng hoặc đầu chưa đến hạn. | Không có producer ghép cặp ngay. |
| `size()` | Số item đang lưu. | Số item gồm cả chưa đến hạn. | Luôn 0. |
| `remainingCapacity()` | `Integer.MAX_VALUE`. | `Integer.MAX_VALUE`. | 0. |
| Thứ tự FIFO tuyệt đối | Không; ưu tiên quyết định. | Không; deadline quyết định. | Không có backlog để FIFO item. |
| Fairness constructor | Không có option fair tương đương ArrayBlockingQueue. | Không có option fair công khai. | Có `SynchronousQueue(boolean fair)`. |
| Dùng điển hình | Ưu tiên công việc chờ, triage theo rank. | Hẹn giờ, retry delay, expire item. | Handoff đồng bộ, pool mở worker theo nhu cầu. |
| Rủi ro chính | Starvation priority thấp, memory backlog. | Memory backlog, hiểu sai thời điểm đến hạn. | Producer/consumer chờ vô hạn hoặc pool tạo nhiều worker. |

**Chọn queue theo điều kiện được phép lấy phần tử**, không chỉ vì cả ba đều triển khai BlockingQueue.

## 14. Java Memory Model và an toàn khi chuyển giao item

Các concurrent collection như BlockingQueue có hợp đồng memory consistency: những hành động của producer **trước khi đưa object vào queue** có quan hệ *happens-before* với những hành động của consumer **sau khi truy cập hoặc lấy object đó ra**.

Ví dụ ý tưởng:

```java
// Trích đoạn producer.
Message message = new Message();
message.payload = 42;
queue.put(message);

// Trích đoạn consumer (ở thread khác).
Message received = queue.take();
System.out.println(received.payload);
```

Đoạn này giả định `Message` và `queue` được định nghĩa thích hợp. Quan hệ happens-before bảo đảm dữ liệu đã được chuẩn bị **trước khi đưa vào queue** được chuyển giao theo quy tắc Java Memory Model (JMM). Điều đó **không biến mọi mutation sau khi enqueue thành thread-safe**.

- Với PriorityBlockingQueue, field ảnh hưởng comparator nên **immutable** khi phần tử đang nằm trong heap.
- Với DelayQueue, deadline nên **immutable** để thời điểm đã xếp hàng không bị thay đổi ngoài giao thức.
- Với SynchronousQueue, handoff trao quyền truy cập item cho consumer, nhưng producer tiếp tục sửa cùng object song song vẫn cần quy tắc ownership/synchronization.
- Nếu item giữ reference tới mutable data ở nơi khác, an toàn phải xét theo toàn bộ object graph chứ không chỉ reference của item.

Dùng `record`, final fields, defensive copy hoặc quy tắc chuyển quyền sở hữu sẽ giảm lỗi dữ liệu khi trao đổi giữa nhiều thread.

## 15. Timeout, interruption và shutdown không giống nhau

Cả ba queue đều có thao tác chờ có thể bị interrupt:

- `take()` có thể ném `InterruptedException` khi thread đang đợi bị interrupt.
- `put()` có thể chờ trong SynchronousQueue, nhưng với PriorityBlockingQueue/DelayQueue không bị chặn vì capacity theo hợp đồng unbounded; vẫn có contract interruption của interface khi sử dụng.
- `offer(timeout)`/`poll(timeout)` cho một thời hạn theo caller, nhưng lý do chưa ghép cặp/chưa đến hạn vẫn phụ thuộc từng queue.
- BlockingQueue **không có phương thức `close()` thống nhất**; muốn tắt producer–consumer cần sentinel, interrupt, timeout hoặc lifecycle state tùy thiết kế.

**Cancellation không tự rollback item đã chuyển giao.** Với SynchronousQueue, khi producer `put` xong, consumer đã nhận item nhưng có thể chưa xử lý. Với DelayQueue, item đã hết hạn nhưng chưa có consumer vẫn có thể nằm trong queue. Với PriorityBlockingQueue, task đã bị consumer lấy ra không tự trở lại queue chỉ vì worker bị interrupt.

Khi dùng queue cùng executor, owner phải quản lý `shutdown()`, `shutdownNow()`, `awaitTermination()` và tác vụ còn chờ theo hợp đồng của executor. Không được nhầm queue rỗng với pool đã hoàn tất mọi task.

## 16. Lỗi phổ biến khi dùng ba queue

| Sai lầm | Vì sao sai | Hướng sửa |
|---|---|---|
| Coi PriorityBlockingQueue là FIFO. | Order theo priority; item cùng priority không ổn định thứ tự. | Comparator có tie-breaker sequence nếu cần. |
| Thay đổi field priority sau offer. | Heap không tự heapify lại khi field mutable đổi. | Dùng key immutable hoặc remove/cập nhật/reinsert đúng giao thức. |
| Coi initialCapacity của PriorityBlockingQueue là bound. | Array có thể mở rộng; không phải giới hạn backlog. | Tự giới hạn producer/permit hoặc chọn queue bounded. |
| In iterator và kết luận đó là priority order. | Iterator không cam kết thứ tự. | Poll/take hoặc snapshot rồi sort. |
| Cho rằng priority cao đang chờ sẽ preempt task đã chạy. | Queue không quản lý CPU hay tác vụ đã dequeue. | Thiết kế scheduler/preemption/cancellation riêng. |
| Dùng DelayQueue nhưng Delayed.compareTo không nhất quán getDelay. | Head không phản ánh deadline sớm nhất. | So sánh deadline bất biến theo cùng thước đo. |
| Gọi `poll()` khi DelayQueue.size()>0 và nghĩ chắc lấy được. | Item có thể chưa hết delay. | Dùng take/timed poll và kiểm tra kết quả. |
| Nghĩ DelayQueue tự chạy Runnable đúng giờ. | Queue chỉ lưu và làm đủ điều kiện dequeue. | Dùng ScheduledExecutorService nếu cần tự chạy task. |
| Đổi deadline của Delayed object khi đã enqueue. | Queue không tự reorder. | Dùng immutable deadline; reinsert hoặc scheduler có protocol cập nhật. |
| Nghĩ SynchronousQueue có một slot buffer. | Capacity luôn bằng 0. | Dùng ArrayBlockingQueue(1) khi muốn lưu một phần tử. |
| Gọi SynchronousQueue.offer mà chưa có consumer. | Thường trả false ngay, item không được giữ. | Dùng put hoặc timed offer nếu muốn đợi đối tác. |
| Dựa vào SynchronousQueue.size() để biết số task pool. | Size luôn 0 dù worker đang xử lý. | Đo active tasks, completed, rejection, throughput. |
| Dùng cached pool với blocking task vô hạn. | Có thể tạo rất nhiều worker và cạn tài nguyên. | Giới hạn max thread, timeout và rejection/backpressure. |
| Nuốt InterruptedException khi đang chờ. | Hủy không có hiệu lực, có thể chờ vô hạn. | Ném tiếp hoặc khôi phục flag rồi thoát theo contract. |
| Chọn queue chỉ theo throughput một microbenchmark. | Không xét latency, backlog, ordering, memory, fairness. | Đo workload thật và xác định contract trước. |

## 17. Lựa chọn đúng theo tình huống

**Tình huống A — Xử lý công việc theo mức khẩn cấp:** Nếu task cần được lấy theo một `priority` đã biết và ít đổi, `PriorityBlockingQueue` là lựa chọn phù hợp. Cần kiểm soát starvation và giới hạn backlog vì queue không bounded theo constructor.

**Tình huống B — Retry sau 5 giây:** Nếu item chỉ được worker nhận lại sau deadline, `DelayQueue<Delayed>` giúp lưu item và chờ đúng lúc. Nếu chỉ muốn scheduler **tự chạy** một callback, dùng `ScheduledExecutorService`.

**Tình huống C — Bên gửi phải chờ bên nhận:** Nếu không muốn backlog mà cần transfer trực tiếp giữa hai bên, `SynchronousQueue` có ý nghĩa. Cần timeout/interrupt khi không có đối tác.

**Tình huống D — Executor không lưu backlog, tạo worker tới mức giới hạn:** `ThreadPoolExecutor` với `SynchronousQueue`, `corePoolSize`, `maximumPoolSize` và rejection policy rõ ràng. Nếu cần một backlog nhỏ thay vì handoff thuần, dùng bounded queue phù hợp.

**Tình huống E — Chỉ cần producer–consumer FIFO với capacity:** Dùng `ArrayBlockingQueue` hoặc `LinkedBlockingQueue(capacity)`, **không ép** một trong ba queue của bài giải quyết sai bài toán.

Trong mọi trường hợp, quyết định còn tùy CPU/I/O, số producer/consumer, độ trễ, mức độ quan trọng của ordering, lượng backlog chấp nhận được và cách dừng ứng dụng.

## 18. Checklist thiết kế và kiểm thử

1. **Định nghĩa điều kiện dequeue:** theo priority, theo deadline hay chỉ khi có người nhận?
2. **Xác định capacity:** unbounded theo API có nguy cơ heap; zero-capacity cần giao thức handoff.
3. **Định nghĩa so sánh:** comparator ổn định cho PriorityBlockingQueue; `compareTo` nhất quán deadline cho DelayQueue.
4. **Không mutate key khi đã enqueue:** immutable priority/deadline giúp cấu trúc ưu tiên đúng.
5. **Xác định timeout:** caller có thể đợi bao lâu, và nếu không có dữ liệu/đối tác thì làm gì?
6. **Có xử lý InterruptedException:** không nuốt yêu cầu hủy trong vòng lặp không giới hạn.
7. **Định nghĩa completion:** đã dequeue/handoff khác đã xử lý nghiệp vụ xong.
8. **Quản lý lifecycle:** producer–consumer không có `BlockingQueue.close()` chung; executor phải shutdown theo owner.
9. **Theo dõi overload:** queue depth/age cho priority/delay; active workers và rejection cho SynchronousQueue/executor.
10. **Test ordering đúng:** với priority tie-breaker, deadline khác nhau rõ ràng và các latch bảo đảm lịch chạy.
11. **Test cancellation:** khi consumer không nhận, khi item chưa đến hạn, khi shutdown đang diễn ra.
12. **Kiểm thử cả tính đúng lẫn hiệu năng:** starvation, heap, CPU, GC, latency và throughput.
13. **Đừng suy thứ tự hoàn thành từ thứ tự dequeue:** nhiều worker xử lý đồng thời sẽ có thời lượng khác nhau.
14. **Không tự dùng concurrent queue làm durable broker:** cần persistence/idempotency nếu dữ liệu phải sống qua JVM restart.

## 19. Câu hỏi tự kiểm tra

1. **PriorityBlockingQueue có FIFO không?** Không; phần tử lấy ra theo comparator/natural priority. Nếu bằng nhau, thứ tự không được bảo đảm.
2. **`new PriorityBlockingQueue<>(100)` có chặn thêm ở 100 item không?** Không; 100 là initial capacity.
3. **Vì sao cần tie-breaker sequence?** Để có thứ tự xác định giữa các task cùng priority nếu nghiệp vụ yêu cầu.
4. **Nếu sửa priority ngay trong object đang ở queue thì heap có tự reorder?** Không.
5. **DelayQueue cần interface gì?** `Delayed` với `getDelay(TimeUnit)` và `compareTo`.
6. **DelayQueue.size()>0 có bảo đảm poll trả item không?** Không; item đứng đầu có thể chưa hết delay.
7. **DelayQueue có tự gọi Runnable sau deadline không?** Không, chỉ cho phép consumer lấy item đến hạn.
8. **SynchronousQueue có bao nhiêu slot lưu?** Bằng 0, không có backlog.
9. **SynchronousQueue.offer(e) không timeout có luôn nhận item?** Không; cần có consumer đối ứng sẵn sàng.
10. **SynchronousQueue.put(e) xong có nghĩa consumer đã xử lý xong?** Không; chỉ cho biết handoff đã xảy ra.
11. **SynchronousQueue.size() phản ánh active worker không?** Không; luôn bằng 0.
12. **Vì sao SynchronousQueue làm ThreadPoolExecutor dễ mở non-core worker?** Vì queue không giữ task; offer thất bại khi không có worker rảnh nhận.
13. **`newCachedThreadPool()` có nguy cơ gì khi nhiều blocking task?** Pool có thể mở rất nhiều worker, gây cạn tài nguyên.
14. **BlockingQueue có close() chung không?** Không; phải thiết kế lifecycle/cancellation riêng.
15. **Queue memory consistency bảo đảm gì?** Hành động trước enqueue/handoff happens-before hành động sau dequeue/nhận tương ứng; không bảo vệ mutation cạnh tranh sau đó.
16. **Khi nào nên dùng ArrayBlockingQueue thay vì ba queue trên?** Khi chỉ cần FIFO bounded producer–consumer thông thường.

**Ghi nhớ:** `PriorityBlockingQueue` sắp theo **mức ưu tiên**, `DelayQueue` chờ **đến hạn**, `SynchronousQueue` yêu cầu **hai thread chuyển giao trực tiếp mà không có bộ đệm**. Cùng là BlockingQueue nhưng ordering, capacity, timeout, backpressure và tác động tới executor khác nhau; lựa chọn phải bắt đầu từ hợp đồng công việc.
