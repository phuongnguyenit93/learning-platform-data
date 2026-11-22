# BlockingQueue: put(), take(), offer(), poll() trong Java

Khi nhiều thread cần truyền công việc hoặc dữ liệu qua lại, việc tự dùng một `List`, một biến cờ và vòng lặp liên tục kiểm tra có thể gây race condition, chờ bận (*busy waiting*) hoặc làm mất dữ liệu. `java.util.concurrent.BlockingQueue<E>` là một abstraction **queue thread-safe**, đồng thời cung cấp các thao tác **đợi khi chưa thể thêm hoặc lấy phần tử**. Nó là nền tảng thường gặp của mô hình **producer–consumer**, hàng đợi tác vụ, bộ đệm giới hạn dung lượng và *backpressure* trong Java.

Bốn phương thức trọng tâm là:

- `put(e)`: đưa phần tử vào, **chờ nếu chưa có chỗ**.
- `take()`: lấy và loại bỏ phần tử đầu hàng đợi, **chờ nếu hàng đợi rỗng**.
- `offer(e)`: thử thêm **ngay**, trả `false` nếu không thể thêm vào lúc đó.
- `poll()`: thử lấy **ngay**, trả `null` nếu không có phần tử.

Các overload `offer(e, timeout, unit)` và `poll(timeout, unit)` cung cấp **thời gian chờ có giới hạn**. Cần hiểu sự khác nhau này trước khi thiết kế đường hủy, timeout, dừng consumer và xử lý hàng đợi đầy.

Bài Knowledge thuộc chủ đề **Phối hợp luồng**, áp dụng cho **Java concurrency nói chung (Java 17+)** và không đi vào các cơ chế riêng của Spring.

Sau bài này, bạn có thể:
1. Chọn đúng một trong các thao tác thêm/lấy/đợi/thử của `BlockingQueue`.
2. Viết producer–consumer có dữ liệu truyền an toàn mà không phải tự dùng `wait/notify`.
3. Biết tác động của queue **bounded** và **unbounded** lên backpressure và bộ nhớ.
4. Xử lý `InterruptedException`, timeout, poison pill và cách kết thúc worker có trật tự.
5. Hiểu visibility theo Java Memory Model khi chuyển giao dữ liệu qua queue.
6. Nhận diện giới hạn: queue không có `close()` chuẩn, không biến object mutable bên trong thành thread-safe, và không tự bảo đảm shutdown hay xử lý task đúng một lần.

## 1. BlockingQueue là gì và tại sao hữu ích?

`BlockingQueue<E>` thuộc `java.util.concurrent` và mở rộng ý tưởng của `Queue<E>`. Nó cung cấp những phép thao tác đồng thời để nhiều producer thêm và nhiều consumer lấy phần tử mà không phải tự khóa một `ArrayList`. Tùy implementation, thứ tự lấy phần tử có thể là FIFO, theo priority, theo thời điểm đến hạn, hoặc handoff trực tiếp: **`BlockingQueue` không hứa tất cả implementation đều FIFO**.

Mô hình ý tưởng:

~~~text
Producer A ---- put/offer ----+
                              |
Producer B ---- put/offer ----+--> [ BlockingQueue<E> ] --> take/poll --> Consumer X
                              |                      \--> take/poll --> Consumer Y
Producer C ---- put/offer ----+

Khi queue BOUNDED đầy: put() đợi chỗ trống.
Khi queue rỗng:        take() đợi phần tử.
offer() và poll():     trả kết quả ngay, không chờ.
~~~

Một queue thread-safe giúp điều phối thao tác trên **cấu trúc hàng đợi**, nhưng không tự trả lời mọi câu hỏi nghiệp vụ: có bao nhiêu consumer? Dừng thế nào? Nếu xử lý thất bại có retry không? Có bảo đảm đúng một lần hay không? Dữ liệu có immutable không? Các câu hỏi đó cần một giao thức riêng.

### 1.1. Tại sao không dùng vòng lặp poll liên tục?

~~~java
// Mã chỉ minh họa anti-pattern; queue đã được khai báo.
while (true) {
    Message message = queue.poll();
    if (message != null) {
        process(message);
    }
}
~~~

Nếu hàng đợi rỗng, vòng lặp có thể **quay liên tục và tốn CPU**. Những tên `Message` và `process` ở đây chỉ là placeholder để minh họa, **không phải chương trình độc lập**. Với worker cần chờ đến khi có dữ liệu, `take()` là cách diễn đạt đúng hơn; nếu cần định kỳ kiểm tra shutdown, `poll(timeout, unit)` có thể phù hợp.

## 2. Bốn nhóm phương thức: ném lỗi, trả trạng thái, chờ, chờ có hạn

`BlockingQueue` định nghĩa những lựa chọn có ý nghĩa khác nhau khi không thể thao tác ngay:

| Thao tác | Ném ngoại lệ ngay | Trả giá trị/trạng thái ngay | Chờ vô hạn đến khi khả thi | Chờ có thời hạn |
| --- | --- | --- | --- | --- |
| **Thêm** | `add(e)` | `offer(e)` | `put(e)` | `offer(e, timeout, unit)` |
| **Lấy và loại bỏ** | `remove()` | `poll()` | `take()` | `poll(timeout, unit)` |
| **Xem đầu, không loại bỏ** | `element()` | `peek()` | Không có trong API | Không có trong API |

Đây là bảng chính theo hợp đồng `BlockingQueue`, đặc biệt quan trọng với queue **có giới hạn dung lượng**.

**Với queue đầy:**
- `add(e)` ném `IllegalStateException` nếu không thêm được do giới hạn dung lượng.
- `offer(e)` trả `false` nếu không thêm được ngay.
- `put(e)` chờ đến khi có chỗ; có thể ném `InterruptedException`.
- `offer(e, timeout, unit)` chờ tối đa thời hạn, trả `true` nếu thêm được, `false` nếu hết hạn; có thể ném `InterruptedException`.

**Với queue rỗng:**
- `remove()` và `element()` ném `NoSuchElementException`.
- `poll()` và `peek()` trả `null`.
- `take()` đợi đến khi có phần tử, rồi **lấy và loại bỏ**; có thể ném `InterruptedException`.
- `poll(timeout, unit)` đợi tối đa thời hạn để lấy phần tử; trả `null` nếu hết hạn; có thể ném `InterruptedException`.

Phân biệt `peek()` với `poll()`: `peek()` chỉ xem phần tử đầu, không lấy ra; `poll()` xóa phần tử khỏi queue khi thành công. Không có thao tác `peek` đợi vô hạn trong interface này.

### 2.1. Vì sao không có null element?

Các implementation của `BlockingQueue` **không cho phép đưa `null` vào queue**. Lý do quan trọng: `poll()` và `peek()` dùng `null` làm dấu hiệu “không có phần tử”, vì vậy một giá trị `null` thực trong queue sẽ gây nhập nhằng.

~~~java
// Mã minh họa: queue là BlockingQueue<String> đã tạo.
queue.offer(null); // Ném NullPointerException.
~~~

Nếu nghiệp vụ có khái niệm “không có dữ liệu” hoặc “kết thúc”, hãy dùng một **kiểu thông điệp rõ ràng** như record chứa trạng thái, một sentinel object không phải null, hoặc cơ chế cancellation/shutdown khác.

## 3. Ví dụ không chặn: offer() và poll()

`ArrayBlockingQueue` có **dung lượng cố định**, thích hợp để minh họa queue đầy/rỗng và backpressure. Chương trình Java 17+ sau không có thread phụ nên stdout xác định.

~~~java
// OfferPollDemo.java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class OfferPollDemo {
    public static void main(String[] args) {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);

        System.out.println("offer 10: " + queue.offer(10));
        System.out.println("offer 20: " + queue.offer(20));
        System.out.println("offer 30: " + queue.offer(30));

        System.out.println("poll: " + queue.poll());
        System.out.println("poll: " + queue.poll());
        System.out.println("poll empty: " + queue.poll());
    }
}
~~~

~~~bash
javac OfferPollDemo.java
java OfferPollDemo
~~~

Stdout:

~~~text
offer 10: true
offer 20: true
offer 30: false
poll: 10
poll: 20
poll empty: null
~~~

Lý do:
1. Queue có capacity 2 nên nhận 10 và 20.
2. Lúc đầy, `offer(30)` trả `false` **ngay**, không chờ.
3. `ArrayBlockingQueue` có thứ tự FIFO nên `poll()` lấy 10 rồi 20.
4. Khi không còn phần tử, `poll()` trả `null` ngay.

Cách dùng phù hợp: đường xử lý muốn **thử nhận việc** và quyết định ngay nếu queue quá tải (báo busy, drop theo chính sách, retry ở nơi khác). Nếu không kiểm tra giá trị `false` từ `offer` mà coi như đã gửi thành công, ứng dụng có thể âm thầm **mất công việc**.

## 4. Ví dụ chặn: put() và take()

`put(e)` là cách một producer gửi phần tử khi chấp nhận **đợi lúc queue đầy**. `take()` là cách consumer chờ nhận việc khi **queue rỗng**. Cả hai là interruptible blocking operations.

### 4.1. Producer–consumer với queue giới hạn

Đây là ví dụ đầy đủ Java 17+ có một producer, một consumer và sentinel kết thúc. Thứ tự kết quả trong danh sách xác định nhờ queue FIFO; chỉ in khi hai thread đã kết thúc.

~~~java
// ProducerConsumerDemo.java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class ProducerConsumerDemo {
    private static final String END = "__END__";

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
        List<String> received = new ArrayList<>();

        Thread producer = new Thread(() -> {
            try {
                queue.put("alpha");
                queue.put("beta");
                queue.put(END);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                while (true) {
                    String item = queue.take();
                    if (END.equals(item)) {
                        break;
                    }
                    received.add(item);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println("Received: " + received);
        System.out.println("Remaining: " + queue.size());
    }
}
~~~

~~~bash
javac ProducerConsumerDemo.java
java ProducerConsumerDemo
~~~

Khi không có interrupt ngoài ý muốn, stdout:

~~~text
Received: [alpha, beta]
Remaining: 0
~~~

**Giải thích chi tiết:**
- Queue có capacity 2; producer có thể bị chặn tại `put(END)` cho tới khi consumer lấy bớt dữ liệu. Không có busy waiting hoặc gọi `notify` thủ công.
- Một producer đưa các phần tử theo thứ tự `alpha → beta → END`. `ArrayBlockingQueue` giữ FIFO, một consumer lấy theo đúng thứ tự.
- `END` là marker không phải `null`; khi lấy marker, consumer thoát.
- Danh sách `ArrayList` chỉ do **một consumer** ghi; main chỉ đọc sau khi `consumer.join()`, vì vậy ví dụ không có sửa đồng thời lên danh sách.
- Việc catch `InterruptedException` trong code demo chỉ khôi phục cờ interrupt và thoát worker; nếu producer bị interrupt trước khi gửi `END`, consumer có thể vẫn đợi mãi. **Không lấy ví dụ tối giản này làm giao thức shutdown toàn diện**: trong production cần một supervisor có cơ chế hủy/đánh thức cả producer và consumer, xử lý việc enqueue sentinel thất bại, và deadline khi chờ hoàn tất.

### 4.2. Queue đầy mang lại backpressure

Với queue dung lượng B, producer có thể đưa tối đa B phần tử chưa được consumer lấy ra. Nếu producer nhanh hơn consumer trong thời gian dài, `put()` **đợi có chỗ**, làm chậm quá trình nhận việc ở đầu nguồn: đây là một dạng **backpressure**.

Backpressure giúp giới hạn dữ liệu tồn đọng nhưng cũng tạo ra một đường chờ mới. Nếu producer giữ một khóa mà consumer cần để lấy/hoàn tất công việc, producer bị chặn trong `put()` có thể góp phần tạo deadlock. Nên tránh giữ lock ngoài không cần thiết trong lúc có thao tác queue chặn.

**Chặn không đồng nghĩa xử lý thành công:** `put()` trả về nghĩa là phần tử đã được đưa vào queue, **không** có nghĩa consumer đã xử lý xong. `take()` trả về nghĩa là phần tử đã được lấy ra khỏi queue, **không** có nghĩa xử lý nghiệp vụ đã thành công. Nếu cần xác nhận kết quả, phải có một kênh ack/result riêng.

## 5. Timed offer() và poll(): chờ có giới hạn

`offer(e, timeout, unit)` và `poll(timeout, unit)` đặc biệt hữu ích khi:
- Producer có deadline và không được chờ vô hạn.
- Consumer cần định kỳ kiểm tra điều kiện dừng, metrics hoặc trạng thái hệ thống.
- Caller muốn chọn phương án fallback khi queue đầy/rỗng quá lâu.

Chương trình độc lập sau dùng một queue có capacity 1 và thời hạn ngắn:

~~~java
// TimedQueueDemo.java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class TimedQueueDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(1);
        queue.put(7);

        boolean sent = queue.offer(8, 50, TimeUnit.MILLISECONDS);
        System.out.println("Offer while full: " + sent);

        System.out.println("Take: " + queue.take());

        Integer missing = queue.poll(50, TimeUnit.MILLISECONDS);
        System.out.println("Poll while empty: " + missing);

        System.out.println("Offer available: " +
            queue.offer(9, 50, TimeUnit.MILLISECONDS));
        System.out.println("Poll available: " +
            queue.poll(50, TimeUnit.MILLISECONDS));
    }
}
~~~

~~~bash
javac TimedQueueDemo.java
java TimedQueueDemo
~~~

Trong điều kiện chạy bình thường, không có interrupt ngoài ý muốn, stdout:

~~~text
Offer while full: false
Take: 7
Poll while empty: null
Offer available: true
Poll available: 9
~~~

Không có thread khác can thiệp:
- Queue ban đầu đầy với 7, nên `offer(8, 50, MILLISECONDS)` chờ tối đa thời hạn và cuối cùng trả `false`.
- `take()` lấy 7, tạo chỗ trống.
- `poll(50, MILLISECONDS)` chờ trên queue rỗng rồi trả `null`.
- Khi có chỗ, timed `offer(9, ...)` trả `true`; `poll(...)` lấy 9.

**Timeout không có nghĩa là lệnh gửi được giữ lại để tự động tiếp tục sau đó.** Nếu timed offer trả `false`, phần tử 8 **không được thêm** vào queue. Caller phải quyết định retry, từ chối, ghi log, gửi nơi khác hoặc bỏ theo chính sách. Nếu timed poll trả `null`, không có phần tử nào được lấy bởi lời gọi đó.

### 5.1. InterruptedException có ý nghĩa gì?

`put()`, `take()` và các timed overload khai báo `throws InterruptedException`. Khi thread đang chờ và bị interrupt, lời gọi có thể ném ngoại lệ để caller hợp tác dừng. Nếu tầng gọi có thể khai báo `throws InterruptedException` thì thường nên truyền tiếp; nếu phải catch, có thể phục hồi cờ:

~~~java
// Mã minh họa bên trong một worker có biến queue:
try {
    process(queue.take());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return; // Thoát worker theo giao thức của ứng dụng.
}
~~~

`process` là phương thức giả định đã khai báo; đoạn không độc lập. Không thực hiện vòng lặp vô hạn kiểu catch rồi bỏ qua interrupt, vì nó có thể khiến worker không chịu dừng. Nhưng cũng không nên giả định `interrupt` dừng cưỡng bức mọi đoạn code hoặc tự hoàn tác thao tác nghiệp vụ mà consumer đã thực hiện.

**Phân biệt interrupt và timeout:** timed `poll` trả `null` khi hết hạn, nhưng **ném `InterruptedException` khi bị gián đoạn trong lúc chờ**. Hai trường hợp cần chính sách xử lý khác nhau.

## 6. Các implementation quan trọng và lựa chọn dung lượng

Không phải mọi `BlockingQueue` có cùng cấu trúc, giới hạn và thứ tự.

| Implementation | Đặc trưng | Dung lượng / thứ tự / tình huống |
| --- | --- | --- |
| `ArrayBlockingQueue<E>` | Mảng có capacity cố định | **Bounded**, FIFO; thích hợp cho buffer có giới hạn |
| `LinkedBlockingQueue<E>` | Các node liên kết | FIFO; có thể cấp capacity, mặc định giới hạn ở `Integer.MAX_VALUE` |
| `SynchronousQueue<E>` | Handoff trực tiếp giữa producer và consumer | **Không lưu phần tử** (capacity 0); `put` cần một bên nhận tương ứng |
| `PriorityBlockingQueue<E>` | Queue dựa trên priority | Về API **logically unbounded**, lấy theo mức ưu tiên chứ không phải FIFO chung |
| `DelayQueue<E extends Delayed>` | Phần tử chỉ lấy được khi hết delay | Unbounded theo API; `take()` chờ tới phần tử đến hạn |
| `LinkedTransferQueue<E>` | Queue dựa trên linked nodes, hỗ trợ transfer | Unbounded theo API; có thể handoff/transfer trực tiếp tùy thao tác |

### 6.1. Bounded không giống unbounded

Với một queue **bounded** như `new ArrayBlockingQueue<>(100)`, số phần tử chờ được giới hạn. Khi đầy:
- `put` chờ.
- `offer` trả `false`.
- Timed `offer` chờ tối đa thời hạn rồi quyết định.

Với một queue **logically unbounded**, producer thường không bị giới hạn bởi một capacity hữu hạn được cấu hình trong API. Điều này **không có nghĩa RAM vô hạn**: nếu tốc độ producer lâu dài lớn hơn consumer, backlog có thể gây áp lực bộ nhớ hoặc `OutOfMemoryError`. `LinkedBlockingQueue` không truyền capacity có giới hạn khai báo mặc định là `Integer.MAX_VALUE`, cực lớn về mặt vận hành; hãy cân nhắc truyền capacity rõ ràng.

`remainingCapacity()` có thể hữu ích để quan sát, nhưng trong hệ thống nhiều thread, đây là giá trị nhất thời: một thread khác có thể thêm/lấy ngay sau phép kiểm tra. **Không viết `if (remainingCapacity() > 0) put(...)` rồi tưởng có quyền đặt chỗ nguyên tử.** Cứ dùng `offer`/`put` trực tiếp theo đúng chính sách.

### 6.2. Fairness của ArrayBlockingQueue

`ArrayBlockingQueue` có constructor cho phép cấu hình `fair`:

~~~java
// Mã minh họa:
BlockingQueue<String> queue = new ArrayBlockingQueue<>(8, true);
~~~

Với fairness=true, các thread producer/consumer đang bị chặn được phục vụ theo chính sách xếp hàng công bằng hơn theo hợp đồng implementation. Điều này có thể giảm khả năng một thread phải chờ lâu nhưng cũng thường làm giảm throughput. Không suy diễn fairness của queue thành “mọi task đều được xử lý đúng thứ tự thời gian thực” hoặc “scheduler Java sẽ luôn công bằng”.

### 6.3. SynchronousQueue không phải queue một phần tử

`SynchronousQueue` **không có capacity lưu trữ nội bộ**: mỗi lần insert phải gặp một remove tương ứng từ thread khác. Vì vậy `offer(e)` không đợi sẽ thường trả `false` nếu chưa có consumer đang chờ; `put(e)` chờ cho tới khi có bên nhận phối hợp.

Ví dụ Java 17+ dưới có hai thread trao một phần tử:

~~~java
// SynchronousHandoffDemo.java
import java.util.concurrent.SynchronousQueue;

public class SynchronousHandoffDemo {
    public static void main(String[] args) throws InterruptedException {
        SynchronousQueue<String> queue = new SynchronousQueue<>();

        Thread consumer = new Thread(() -> {
            try {
                queue.take();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        queue.put("parcel");
        consumer.join();

        System.out.println("Size: " + queue.size());
        System.out.println("Handoff completed");
    }
}
~~~

~~~bash
javac SynchronousHandoffDemo.java
java SynchronousHandoffDemo
~~~

Khi không bị interrupt ngoài ý muốn, stdout:

~~~text
Size: 0
Handoff completed
~~~

`put("parcel")` hoàn tất khi có bên nhận tương ứng. `size()` là 0 vì `SynchronousQueue` không có khả năng chứa phần tử. Đây là một **handoff**, không phải một buffer có sức chứa 1. Việc `consumer.join()` chờ consumer kết thúc không đồng nghĩa consumer đã hoàn thành xử lý nghiệp vụ phức tạp nào; ví dụ consumer chỉ lấy phần tử.

## 7. Bảo đảm visibility giữa producer và consumer

`BlockingQueue` là concurrent collection của `java.util.concurrent` và có **memory consistency effects** được JDK đặc tả. Hành động của thread producer **trước khi đặt một object vào queue** *happens-before* hành động của thread khác **sau khi truy cập hoặc lấy phần tử đó** từ queue.

Ví dụ minh họa:

~~~java
// Mã minh họa, không phải file độc lập.
final class Message {
    int value;
}
Message message = new Message();
message.value = 42;          // Producer chuẩn bị dữ liệu.
queue.put(message);          // Bàn giao qua BlockingQueue.

// Trong consumer khác:
Message received = queue.take();
System.out.println(received.value); // Nhìn thấy 42 nếu không ghi cạnh tranh khác.
~~~

Quan hệ này giúp producer **công bố dữ liệu đã chuẩn bị** cho consumer mà không cần tự gắn `volatile` lên mọi field của object chỉ phục vụ handoff. Nhưng **đặt object mutable vào queue không tự làm nó bất biến**. Nếu producer tiếp tục sửa `message.value` trong lúc consumer đọc, vẫn có khả năng data race và kết quả không mong muốn.

**Mẫu tốt:** chuẩn bị object xong → put → không sửa object đó nữa, hoặc dùng message bất biến (`record` với thành phần immutable). Đối với queue chứa reference tới một object mutable dùng chung bởi nhiều thread, cần quy tắc ownership/copy/synchronization riêng.

### 7.1. Giao tiếp bằng message thay vì shared mutable state

Thay vì hai thread cùng sửa một `ArrayList`, có thể để producer đưa **từng message** vào queue, và chỉ consumer cập nhật trạng thái xử lý. Điều này giúp giảm phạm vi dữ liệu chia sẻ và làm rõ ranh giới ownership.

Tuy nhiên, queue chỉ bảo vệ quá trình enqueue/dequeue. Nếu cùng một message được gửi đến nhiều nơi, hoặc sau khi `take` consumer chia sẻ reference cho thread khác, trách nhiệm bảo vệ state vẫn tồn tại.

## 8. Thiết kế shutdown: BlockingQueue không có close() chuẩn

`BlockingQueue` **không khai báo phương thức `close()` để tự đánh thức mọi consumer**. Nếu mọi producer đã ngừng nhưng consumer vẫn ở `take()` trên một queue rỗng, nó có thể chờ vô hạn. Vì vậy phải thiết kế tín hiệu kết thúc.

Các cách thường gặp:
1. **Poison pill/sentinel:** gửi một phần tử đặc biệt, consumer thấy thì thoát. Đúng lúc với giao thức có số producer/consumer được biết.
2. **Interrupt/cancellation:** supervisor gửi interrupt cho consumer đang `take()`, worker xử lý `InterruptedException` rồi thoát theo chính sách.
3. **Timed poll + cờ dừng:** worker dùng `poll(timeout, unit)`, định kỳ kiểm tra một điều kiện kết thúc được công bố đúng cách.
4. **Quản lý executor:** dừng nhận công việc, phối hợp producers/consumers, hủy khi cần và `awaitTermination`. `ExecutorService.shutdown()` một mình không đánh thức task đang chờ mãi trên queue nếu task không có đường dừng.

### 8.1. Poison pill có nhiều consumer

Khi có N consumer đang lấy độc lập từ cùng queue, **một poison pill chỉ được một consumer lấy**. Nếu muốn tất cả N consumer đều thoát qua sentinel, thường phải gửi **N phần tử sentinel**, sau khi toàn bộ producer đã hoàn tất gửi công việc thường.

Ví dụ đầy đủ Java 17+, hai consumer, bốn task. Chỉ in kết quả từ main sau `join` nên không lệ thuộc vào thứ tự xử lý của consumer:

~~~java
// MultipleConsumersShutdownDemo.java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

public class MultipleConsumersShutdownDemo {
    record Work(int id, boolean stop) {}
    private static final Work STOP = new Work(-1, true);

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Work> queue = new ArrayBlockingQueue<>(3);
        AtomicInteger processed = new AtomicInteger();

        Runnable consumer = () -> {
            try {
                while (true) {
                    Work item = queue.take();
                    if (item.stop()) {
                        break;
                    }
                    processed.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(consumer, "consumer-A");
        Thread b = new Thread(consumer, "consumer-B");
        a.start();
        b.start();

        for (int i = 1; i <= 4; i++) {
            queue.put(new Work(i, false));
        }
        queue.put(STOP); // Một pill cho consumer A hoặc B.
        queue.put(STOP); // Pill thứ hai cho consumer còn lại.

        a.join();
        b.join();
        System.out.println("Processed: " + processed.get());
        System.out.println("Remaining: " + queue.size());
    }
}
~~~

~~~bash
javac MultipleConsumersShutdownDemo.java
java MultipleConsumersShutdownDemo
~~~

Khi không có interrupt ngoài ý muốn và không có task lỗi, stdout:

~~~text
Processed: 4
Remaining: 0
~~~

Vì hai STOP được enqueue **sau toàn bộ bốn task** trên `ArrayBlockingQueue` FIFO, không consumer nào lấy STOP trước khi bốn phần tử công việc đã được lấy ra. Hai consumer mỗi người chỉ thoát sau khi lấy một STOP. `processed.incrementAndGet()` là phép tăng nguyên tử; sau khi main `join` cả hai, giá trị là 4.

**Giới hạn của poison pill:**
- Nếu có **nhiều producer** và một producer gửi STOP khi producer khác còn gửi việc, consumer có thể dừng sớm, bỏ sót task phía sau. Cần phối hợp producer completion trước khi gửi pill.
- Nếu consumer bị lỗi/dừng sớm, các lệnh `put(STOP)` có thể kẹt khi queue đầy mà không còn consumer đủ để lấy; cần supervisor, timeout/cancellation.
- Nếu một consumer tái enqueue STOP để consumer khác biết, phải thiết kế rất cẩn thận vì thứ tự và việc lặp lại có thể khó chứng minh. Với số consumer biết trước, một pill trên mỗi consumer thường đơn giản hơn.
- Phải chọn sentinel **không trùng với dữ liệu hợp lệ**. Record có `boolean stop` trong ví dụ phân biệt rõ thông điệp dừng với công việc thường.

## 9. Xử lý task lỗi, đảm bảo hoàn tất và backpressure

### 9.1. Queue chỉ bàn giao, không phải xử lý đúng một lần

Khi `take()` trả về một task, task đã bị loại khỏi queue. Nếu consumer sau đó ném exception trước khi xử lý xong, queue **không tự đưa task trở lại**. Muốn retry/ack, bạn cần cơ chế riêng:
- Nơi lưu trạng thái xử lý hoặc lưu trữ bền vững nếu cần chống mất khi process dừng.
- Quy tắc retry giới hạn, idempotency, xử lý task độc hại (*poison message*).
- Giám sát những consumer chết bất ngờ và việc queue tồn đọng.
- Hợp đồng at-most-once, at-least-once hoặc exactly-once ở cấp nghiệp vụ; bản thân `BlockingQueue` in-memory không bảo đảm delivery bền vững hay exactly-once khi có crash.

### 9.2. Bounded queue và overload

Một hệ thống có queue capacity 1.000 vẫn có thể quá tải nếu producer tạo việc lâu dài nhanh hơn consumer xử lý. Các chính sách khác nhau:

| Chính sách | Cách biểu đạt gần đúng | Đánh đổi |
| --- | --- | --- |
| **Đợi khi đầy** | `put(e)` | Backpressure mạnh, nhưng có thể làm caller chờ vô hạn |
| **Từ chối nhanh** | `if (!offer(e)) reject()` | Latency có giới hạn tại enqueue, phải có xử lý từ chối |
| **Chờ có deadline** | `offer(e, timeout, unit)` | Có thể thoát khi quá hạn, cần chính sách fallback |
| **Bỏ bớt** | `offer(e)` rồi discard có chủ đích | Chấp nhận mất một số sự kiện, chỉ đúng nếu nghiệp vụ cho phép |
| **Tăng năng lực consumer** | Nhiều consumer hơn, nếu workload cho phép | Có contention, ordering, tài nguyên và chi phí vận hành |

Đừng “khắc phục” backpressure bằng cách chọn một queue không giới hạn rồi để backlog tăng mãi. Điều đó chỉ chuyển vấn đề từ chờ producer sang **tích tụ bộ nhớ**.

### 9.3. FIFO không đồng nghĩa hoàn tất theo thứ tự

Với một `ArrayBlockingQueue` và hai consumer, phần tử A có thể được **lấy ra trước** B nhưng xử lý A lại **kết thúc sau** B do công việc hoặc lịch thread khác nhau. Queue FIFO quy định **thứ tự dequeue**, không bảo đảm thứ tự hoàn tất nghiệp vụ nhiều worker. Nếu yêu cầu giữ thứ tự kết quả, phải có một consumer, cơ chế sequence/reorder, hoặc kiến trúc tương ứng.

## 10. Những sai lầm thường gặp

- **“put() trả về là consumer đã làm xong.”** Sai; chỉ nghĩa là enqueue thành công.
- **“take() cũng chỉ xem đầu queue.”** Sai; nó lấy **và loại bỏ** phần tử.
- **“offer() sẽ tự đợi khi queue đầy.”** Sai với overload không timeout; nó trả `false` ngay.
- **“poll() chặn cho tới lúc có việc.”** Sai; nó trả `null` ngay nếu rỗng.
- **“Timed offer trả false nhưng việc sẽ tự được gửi sau.”** Sai; không có enqueue của phần tử đó.
- **“BlockingQueue chứa được null.”** Sai; null dùng để báo trạng thái không có phần tử.
- **“Tất cả BlockingQueue đều FIFO.”** Sai; priority/delay/handoff có semantics khác.
- **“ArrayBlockingQueue capacity 2 có thể tăng dung lượng tự động.”** Sai; capacity cố định.
- **“LinkedBlockingQueue mặc định là buffer nhỏ an toàn.”** Sai; capacity mặc định rất lớn, cần cân nhắc áp lực RAM.
- **“SynchronousQueue chứa một phần tử chờ.”** Sai; capacity nội tại bằng 0, handoff trực tiếp.
- **“Một poison pill dừng mọi consumer.”** Sai; một phần tử chỉ được một consumer lấy.
- **“shutdown() luôn giải phóng worker đang take().”** Sai nếu không có tín hiệu/dừng theo giao thức.
- **“Queue làm object bên trong tự động immutable.”** Sai; giao tiếp bằng queue tạo memory-ordering cho dữ liệu trước handoff, không bảo vệ những lần sửa đồng thời sau đó.
- **“remainingCapacity() > 0 cho phép đặt chỗ.”** Sai; giá trị có thể thay đổi ngay sau khi đọc.
- **“Đọc queue.size() rồi mới quyết định enqueue/dequeue là một phép atomic.”** Sai; đó là check–then–act bị cạnh tranh.
- **“Queue không cần quản lý timeout/interrupt.”** Sai với blocking operations.
- **“Consumer lấy task thì queue đảm bảo xử lý đúng một lần ngay cả khi crash.”** Sai; cần cơ chế xử lý lỗi/durable store riêng.

## 11. Checklist thiết kế và kiểm thử

1. **Xác định mục đích:** queue dùng để đệm công việc hay handoff trực tiếp? Cần FIFO, priority hay delay?
2. **Chọn capacity:** peak backlog cho phép, memory budget, tốc độ producer/consumer, chính sách khi queue đầy.
3. **Chọn API theo yêu cầu:** `put` nếu chấp nhận đợi; `offer` nếu từ chối nhanh; timed offer nếu có deadline; `take` khi muốn đợi việc; timed poll nếu cần kiểm tra liveness định kỳ.
4. **Xử lý mọi kết quả:** kiểm tra `offer` trả false, `poll` trả null, xử lý `InterruptedException` và timeout như các trạng thái khác nhau.
5. **Quy định ownership message:** producer chuẩn bị xong trước enqueue, tránh sửa concurrent sau handoff; cân nhắc record bất biến.
6. **Xác định giao thức shutdown:** producer nào thông báo hoàn tất? Ai đặt poison pill? Có bao nhiêu consumer? Điều gì xảy ra nếu một worker lỗi hoặc bị hủy?
7. **Xác định yêu cầu xử lý:** có ack, retry, deduplication, idempotency hoặc durable persistence không?
8. **Đo và giám sát:** queue length, thời gian chờ enqueue/dequeue, throughput, số consumer hoạt động, tốc độ backlog tăng.
9. **Kiểm thử đúng lịch xấu:** queue đầy, rỗng, producer bị interrupt, consumer chết, timed offer thất bại, nhiều producer cùng kết thúc.
10. **Không suy luận từ stress test đơn lẻ:** kiểm tra invariant và đường thoát bằng các điểm đồng bộ có kiểm soát.

### Mẫu kiểm tra nhanh khi đọc code

| Nếu nhìn thấy | Hãy hỏi |
| --- | --- |
| `queue.put(item)` bên trong một synchronized block | Có nguy cơ chờ queue trong lúc giữ lock mà consumer cần không? |
| `if (!queue.offer(item)) { }` | Việc bị từ chối được xử lý hay âm thầm mất? |
| `while (queue.poll() == null)` | Có busy spin tiêu thụ CPU không? |
| `queue.take()` trong worker chạy mãi | Ai sẽ đánh thức/dừng nó khi hệ thống shutdown? |
| Một sentinel duy nhất, nhiều consumer | Những consumer còn lại sẽ thoát bằng đường nào? |
| `LinkedBlockingQueue<>()` không capacity | Có nguy cơ backlog chiếm bộ nhớ quá lớn không? |
| `queue.size()` để quyết định chính xác lượng tồn | Giá trị này có thay đổi giữa check và action không? |
| Worker tạo object rồi vẫn sửa sau `put` | Có data race trên object mutable không? |

## 12. Câu hỏi tự kiểm tra

**1.** `ArrayBlockingQueue<Integer>` có capacity 1, đang chứa 10. `offer(20)` trả gì?  
**Đáp án:** `false` ngay, vì không còn capacity. `put(20)` sẽ chờ tới khi có chỗ (hoặc bị interrupt).

**2.** Queue rỗng. `poll()` và `take()` khác nhau thế nào?  
**Đáp án:** `poll()` trả `null` ngay; `take()` chờ có phần tử và có thể bị interrupt.

**3.** `poll(100, MILLISECONDS)` hết thời gian nhưng không có item, trả gì?  
**Đáp án:** `null`. Nếu thread bị interrupt trong lúc chờ, có thể ném `InterruptedException`.

**4.** Sau `put(task)`, producer có thể kết luận task đã được consumer xử lý thành công?  
**Đáp án:** Không. `put` chỉ xác nhận enqueue thành công; cần ack/result riêng để biết trạng thái nghiệp vụ.

**5.** Vì sao không nên đưa `null` vào `BlockingQueue`?  
**Đáp án:** Vì `poll`/`peek` dùng `null` báo rỗng; API cấm null element.

**6.** Có ba consumer chờ `take()` và producer kết thúc. Một STOP message đủ dừng cả ba không?  
**Đáp án:** Không. Một message chỉ được một consumer lấy. Nếu dùng poison pill, thường gửi ba pill sau khi mọi producer hoàn tất.

**7.** `SynchronousQueue` có thể chứa bao nhiêu item đợi?  
**Đáp án:** Zero. Mỗi lần gửi thành công cần gặp một thao tác nhận tương ứng.

**8.** `new LinkedBlockingQueue<>()` có phải queue bounded nhỏ?  
**Đáp án:** Không. Giới hạn khai báo mặc định là `Integer.MAX_VALUE`, vì vậy cần cân nhắc cấu hình capacity để tránh tích tụ bộ nhớ.

**9.** Producer khởi tạo `Message.value = 42`, đưa object vào BlockingQueue rồi consumer lấy ra. Có bảo đảm visibility của ghi trước enqueue không?  
**Đáp án:** Có, theo memory consistency effects của concurrent collection, miễn giao thức phù hợp và không có ghi cạnh tranh sau đó.

**10.** Nếu queue FIFO có hai consumer, task A được lấy trước B, A chắc chắn hoàn tất trước B?  
**Đáp án:** Không. Thứ tự dequeue không đồng nghĩa thứ tự hoàn tất xử lý song song.

**11.** Nếu `offer(e, 1, SECONDS)` trả false thì queue có tự gửi e khi trống chỗ sau đó không?  
**Đáp án:** Không. Caller phải quyết định retry hoặc fallback.

**12.** Nếu hệ thống cần xử lý công việc tồn tại qua JVM crash, `BlockingQueue` trong bộ nhớ có đủ không?  
**Đáp án:** Không. Cần cơ chế lưu bền/ack/recovery theo yêu cầu nghiệp vụ; queue chỉ đảm nhiệm phối hợp trong JVM.

**Ghi nhớ:** `put/take` là các thao tác **chờ**; `offer/poll` dạng không timeout là **thử ngay**; timed `offer/poll` là **chờ có hạn**. Chọn capacity và chính sách backpressure rõ ràng, xử lý interrupt và shutdown chủ động, và đừng nhầm **enqueue/dequeue thành công** với **xử lý nghiệp vụ thành công**.

### Tài liệu tham khảo chính thức

- Java SE 17 `BlockingQueue` (bảng bốn nhóm thao tác và memory consistency): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- Java SE 17 `ArrayBlockingQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html
- Java SE 17 `LinkedBlockingQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
- Java SE 17 `SynchronousQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html
- Java SE 17 `java.util.concurrent` package: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html