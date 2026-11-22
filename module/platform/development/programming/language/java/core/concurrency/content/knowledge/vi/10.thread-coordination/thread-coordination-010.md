# Poison pill và kết thúc consumer có trật tự trong Java

> **Ý chính:** *Poison pill* là một **thông điệp đặc biệt** được đặt vào luồng công việc (thường qua `BlockingQueue`) để consumer hiểu rằng nó cần **kết thúc vòng nhận việc sau khi xử lý các công việc đã đứng trước tín hiệu đó**. Muốn kết thúc có trật tự, phải kiểm soát thứ tự producer ngừng gửi, thời điểm enqueue poison, số consumer và việc chờ consumer thật sự hoàn tất. **Poison pill không phải lệnh cưỡng bức dừng thread, không phải cơ chế xử lý thất bại và không tự đóng queue hay executor.**

Bài thuộc nhóm **Phối hợp luồng**, tập trung vào Java SE concurrency (`Thread`, `BlockingQueue`, `CountDownLatch`, `ExecutorService`). Không bao gồm cơ chế của Spring; các ví dụ có thể biên dịch/chạy với Java 17+.

## 1. Bài toán: consumer chờ mãi khi không còn producer

Mô hình producer–consumer có một hoặc nhiều producer tạo nhiệm vụ, một hoặc nhiều consumer lấy việc từ queue để xử lý:

~~~text
Producer A ─┐
            ├── put(work) --> [ BlockingQueue ] --> take() --> Consumer
Producer B ─┘
~~~

Consumer thường có vòng lặp:

~~~java
// Snippet minh họa, chưa phải chương trình độc lập.
while (true) {
    Work work = queue.take();
    process(work);
}
~~~

`BlockingQueue.take()` **đợi** khi queue chưa có phần tử. Khi producer đã dừng hẳn và queue đã cạn, consumer có thể tiếp tục chờ vô hạn nếu chương trình **không có một giao thức thông báo kết thúc**.

`BlockingQueue` của Java 17 có `put`, `take`, `offer`, `poll`, nhưng **không có một thao tác close()/shutdown() phổ quát** khiến tất cả reader đang `take()` tự động nhận end-of-stream. Có nhiều giao thức giải quyết vấn đề, và poison pill là một mẫu đơn giản.

## 2. Poison pill hoạt động như thế nào?

Poison pill là một **item được consumer nhận từ chính kênh nhận việc**, nhưng thay vì xử lý như công việc thông thường, consumer nhận ra đây là **end-of-stream** và rời vòng lặp.

~~~text
Producer:   put(W1) --> put(W2) --> put(W3) --> put(STOP)
Queue FIFO: [W1, W2, W3, STOP]
Consumer:   take W1 → process
            take W2 → process
            take W3 → process
            take STOP → break/return
~~~

Đối với một queue FIFO điển hình như `ArrayBlockingQueue` hoặc `LinkedBlockingQueue`, các item được **enqueue trước STOP** sẽ được lấy khỏi queue trước STOP. Nếu consumer **xử lý đồng bộ từng item tới xong trước khi gọi take tiếp**, lúc thấy STOP, toàn bộ công việc phía trước nó đã được xử lý xong bởi consumer đó. Với nhiều consumer, các nhiệm vụ lấy trước STOP có thể vẫn **đang được xử lý đồng thời** ở consumer khác; do đó muốn biết **toàn hệ thống đã xong**, phải chờ mọi consumer kết thúc hoặc có acknowledgment thích hợp.

### Ba loại sự kiện cần phân biệt

| Loại | Ai phát? | Consumer làm gì? | Có nghĩa là hệ thống xong chưa? |
| --- | --- | --- | --- |
| **Work item** | Producer | Thực hiện nghiệp vụ, ghi kết quả hoặc báo lỗi | Chưa |
| **Poison pill / STOP** | Coordinator hoặc producer cuối cùng, đúng thời điểm | Dừng việc lấy thêm item, dọn dẹp và thoát consumer | Chỉ consumer ấy đã nhận lệnh dừng, chưa chắc mọi thread khác xong |
| **Interrupt / cancellation** | Thread khác hoặc môi trường điều khiển | Phản ứng theo chính sách interrupt, có thể thoát sớm | Không tương đương drain toàn bộ work |
| **Shutdown của executor** | Chủ sở hữu executor | Ngừng nhận task mới, thực thi task đã nhận theo hợp đồng | Không tự gửi poison cho một queue ứng dụng |

Mẫu này nên được coi là một **protocol của ứng dụng**, không phải cú pháp đặc biệt hay API built-in tên `PoisonPill` của Java.

## 3. Thiết kế kiểu message: không dùng null hoặc chuỗi trùng dữ liệu

Một cách naïve là dùng String `"STOP"` làm tín hiệu. Nhưng nếu producer có quyền gửi dữ liệu người dùng bằng String, một payload hợp lệ tên `"STOP"` có thể bị hiểu nhầm thành lệnh dừng. Một chuỗi có tên lạ vẫn có rủi ro **collision** hoặc lỗi encoding/normalization.

`BlockingQueue` **không nhận `null` làm phần tử**: `put(null)`/`offer(null)` ném `NullPointerException`. Ngoài ra `poll()` trả `null` để báo không lấy được item, nên null không phải cách biểu diễn tốt cho poison.

Một mẫu mạnh hơn trong Java 17 là **message type rõ ràng**:

~~~java
// Đoạn kiểu dữ liệu minh họa (đặt trong một class Java).
sealed interface Message permits Job, Stop {}
record Job(int id) implements Message {}
enum Stop implements Message { INSTANCE }
~~~

Ở đây `Job` là dữ liệu bình thường, còn `Stop.INSTANCE` là một singleton enum xác định. Consumer kiểm tra bằng **identity** `message == Stop.INSTANCE`; không có payload bình thường nào tự biến thành enum này vì trùng nội dung.

Phân loại:

- **In-band signal:** STOP đi qua chính queue, giữ được quan hệ thứ tự enqueue/dequeue của queue.
- **Out-of-band signal:** một cờ `volatile`, interruption, close của kênh riêng hoặc completion signal. Có thể thích hợp hơn trong một số bài toán, nhưng phải thiết kế cả cách wakeup consumer đang chặn ở `take()`.
- **Completion acknowledgement:** sau khi phát STOP, chủ sở hữu vẫn phải `join()`/`Future.get()`/đợi latch để biết consumer đã thật sự rời vòng chạy.

## 4. Ví dụ 1 — một producer, một consumer, FIFO và kết thúc đúng thứ tự

Tạo tệp `SingleConsumerPoison.java` (Java 17+):

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class SingleConsumerPoison {
    sealed interface Message permits Job, Stop {}
    record Job(int id) implements Message {}
    enum Stop implements Message { INSTANCE }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(2);

        Thread consumer = new Thread(() -> {
            try {
                while (true) {
                    Message message = queue.take();
                    if (message == Stop.INSTANCE) {
                        System.out.println("consumer stopped");
                        return;
                    }

                    Job job = (Job) message;
                    System.out.println("processed " + job.id());
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();

        queue.put(new Job(1));
        queue.put(new Job(2));
        queue.put(Stop.INSTANCE); // Sau tất cả work; capacity=2 vẫn ổn.
        consumer.join();

        System.out.println("joined = " + !consumer.isAlive());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SingleConsumerPoison.java
java SingleConsumerPoison
~~~

Stdout trong điều kiện bình thường, không có interruption bên ngoài:

~~~text
processed 1
processed 2
consumer stopped
joined = true
~~~

**Diễn giải theo hợp đồng:**

1. `ArrayBlockingQueue` là FIFO. Main enqueue hai `Job` theo thứ tự 1, 2 và sau đó mới enqueue `Stop.INSTANCE`.
2. Vì queue chỉ chứa tối đa hai item, `put(Stop.INSTANCE)` **có thể block** khi queue đầy; consumer lấy item tạo thêm chỗ trống. Đây là **backpressure**, không phải lỗi.
3. Consumer xử lý từng `Job` ngay trong vòng nhận việc và chỉ dừng sau khi `take()` trả `Stop.INSTANCE`.
4. `consumer.join()` chờ **thread consumer kết thúc** trước khi main in trạng thái cuối. Nếu bỏ `join()`, việc đã enqueue STOP không đủ chứng minh consumer đã xử lý xong.
5. Không gọi `Thread.stop()` và không cần `Thread.sleep()` để “đợi cho đủ lâu”.

Vì chỉ có một consumer, thứ tự in công việc là xác định. Với nhiều consumer, thứ tự **hoàn thành** các nhiệm vụ khác nhau có thể không trùng thứ tự lấy từ queue.

**Điều kiện ngầm:** producer không được tiếp tục enqueue thêm work **sau** STOP. Nếu một item nằm phía sau STOP, consumer có thể thoát và bỏ item đó lại trong queue.

## 5. Giao thức shutdown có trật tự: đóng admission → đợi producer → phát STOP → đợi consumer

Đây là chuỗi phối hợp nên thiết kế **ngay từ đầu**, không chỉ thêm một dòng `queue.put(POISON)` trong `finally`:

~~~text
RUNNING
   |
   | 1. Không nhận/yêu cầu công việc mới nữa
   v
STOP_ACCEPTING
   |
   | 2. Producer đang chạy hoàn tất việc enqueue hoặc báo lỗi
   v
PRODUCERS_FINISHED
   |
   | 3. Coordinator enqueue đúng số STOP
   v
STOP_SENT
   |
   | 4. Consumer xử lý item trước STOP, nhận STOP rồi thoát
   v
CONSUMERS_TERMINATED
   |
   | 5. Thu kết quả, đóng tài nguyên và công bố trạng thái cuối
   v
CLOSED
~~~

**Quan trọng:** bước 1 và 2 là chuyện của *producer lifecycle*. Nếu vẫn cho một producer mới bắt đầu sau khi đã phát STOP, protocol bị phá. Bước 4 là chuyện của *consumer lifecycle*. Không được gọi toàn bộ hệ thống đã hoàn tất chỉ vì STOP đã vào queue.

### Ai được gửi poison?

Cách rõ nhất là một **coordinator** (thread điều phối) biết tất cả producer đã ngừng phát work, sau đó mới enqueue STOP. Với một producer duy nhất, producer có thể gửi poison ở cuối nếu nó thực sự sở hữu lifecycle của toàn bộ dòng công việc. Với nhiều producer độc lập, **mỗi producer tự gửi một STOP khi xong** thường sai: producer nhanh có thể phát STOP trong khi producer khác còn tạo work.

Nếu có nhiều producer, dùng `Thread.join()`, `Future.get()` hoặc `CountDownLatch` để xác nhận **tất cả đã kết thúc**, kiểm tra lỗi của họ, rồi coordinator mới phát STOP. Lưu ý `join` chỉ xác nhận thread kết thúc; không tự chứng minh producer đã enqueue đủ dữ liệu nếu producer bị hủy hoặc lỗi giữa chừng.

## 6. Nhiều consumer: thường cần một poison pill cho mỗi consumer đang đợi

Giả sử có hai consumer dùng chung một queue. Mỗi `take()` **lấy và loại bỏ** phần tử khỏi queue; poison pill không được broadcast tự động đến tất cả người đọc.

~~~text
Queue: [Job 1, Job 2, STOP, STOP]

Consumer A: take Job 1 ... take STOP -> exit
Consumer B: take Job 2 ... take STOP -> exit
~~~

Mỗi consumer xử lý một STOP rồi **thoát**, nên với `N` consumer có thể đang block ở `take()`, một protocol đơn giản gửi **N STOP messages** sau khi toàn bộ producer đã dừng. Đây là quy tắc **đếm theo số consumer**, không theo số producer và không theo số work item.

Nếu chỉ gửi một STOP cho hai consumer, một consumer thoát, consumer còn lại có thể chờ vô hạn khi queue trống. Nếu số consumer có thể thay đổi hoặc consumer có thể chết trước khi nhận STOP, số lượng STOP phải được quản lý theo **đăng ký/ownership thực tế**, hoặc dùng cơ chế shutdown khác.

### Ví dụ 2 — hai consumer, hai STOP, tổng kết không phụ thuộc scheduling

Tạo `MultipleConsumersPoison.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

public class MultipleConsumersPoison {
    sealed interface Message permits Job, Stop {}
    record Job(int id) implements Message {}
    enum Stop implements Message { INSTANCE }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(3);
        ConcurrentLinkedQueue<Integer> processed = new ConcurrentLinkedQueue<>();
        AtomicInteger stopped = new AtomicInteger();

        Runnable consumerWork = () -> {
            try {
                while (true) {
                    Message message = queue.take();
                    if (message == Stop.INSTANCE) {
                        stopped.incrementAndGet();
                        return; // Consumer này chỉ lấy một STOP.
                    }
                    processed.add(((Job) message).id());
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(consumerWork, "consumer-a");
        Thread b = new Thread(consumerWork, "consumer-b");
        a.start();
        b.start();

        for (int id = 1; id <= 6; id++) {
            queue.put(new Job(id));
        }
        queue.put(Stop.INSTANCE);
        queue.put(Stop.INSTANCE);

        a.join();
        b.join();

        List<Integer> sorted = new ArrayList<>(processed);
        Collections.sort(sorted);

        System.out.println("processed = " + sorted);
        System.out.println("stopped = " + stopped.get());
        System.out.println("queue empty = " + queue.isEmpty());
    }
}
~~~

Chạy:

~~~bash
javac MultipleConsumersPoison.java
java MultipleConsumersPoison
~~~

Đầu ra xác định khi hai consumer hoạt động bình thường:

~~~text
processed = [1, 2, 3, 4, 5, 6]
stopped = 2
queue empty = true
~~~

Không in tên thread nhận từng công việc vì **phân phối công việc giữa A/B không xác định**; thay vào đó thu kết quả bằng `ConcurrentLinkedQueue`, sau khi `join` cả hai thì sort để xác minh đủ 6 ID.

Hai STOP nằm **sau tất cả sáu work items** trong một FIFO queue. Mỗi consumer nhận STOP sẽ return, không tiếp tục lấy STOP thứ hai; như vậy cả hai cuối cùng đều có tín hiệu. Sau khi hai thread kết thúc, không còn work được enqueue phía sau STOP nên queue trống trong kịch bản này.

**Đừng lạm dụng `queue.isEmpty()` để xác định đã xử lý xong khi consumer vẫn chạy.** Một worker có thể đã lấy item ra khỏi queue nhưng đang thực hiện công việc mất nhiều thời gian. `isEmpty()` chỉ là ảnh chụp queue tại thời điểm đọc, không phải acknowledgment hoàn thành.

## 7. Nhiều producer: đợi mọi nguồn việc hoàn tất trước khi phát STOP

Giả sử producer A và B tạo các Job khác nhau. Nếu A tự gửi STOP khi xong, B có thể vẫn đưa thêm Job sau STOP, khiến consumer thoát sớm. Thứ tự đúng là một coordinator đợi **cả A và B**, sau đó mới phát STOP.

### Ví dụ 3 — hai producer, một consumer, coordinator phát poison

Tạo `CoordinatedProducers.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class CoordinatedProducers {
    sealed interface Message permits Job, Stop {}
    record Job(int id) implements Message {}
    enum Stop implements Message { INSTANCE }

    private static Thread producer(
            BlockingQueue<Message> queue, int from, int to) {
        return new Thread(() -> {
            try {
                for (int id = from; id <= to; id++) {
                    queue.put(new Job(id));
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(3);
        List<Integer> processed = new ArrayList<>();

        Thread consumer = new Thread(() -> {
            try {
                while (true) {
                    Message message = queue.take();
                    if (message == Stop.INSTANCE) {
                        return;
                    }
                    processed.add(((Job) message).id());
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });

        Thread firstProducer = producer(queue, 1, 3);
        Thread secondProducer = producer(queue, 4, 6);

        consumer.start();
        firstProducer.start();
        secondProducer.start();

        firstProducer.join();
        secondProducer.join();

        // Chỉ coordinator gửi STOP sau KHI CẢ HAI producer đã kết thúc.
        queue.put(Stop.INSTANCE);
        consumer.join();

        Collections.sort(processed);
        System.out.println("processed = " + processed);
        System.out.println("remaining = " + queue.size());
    }
}
~~~

Chạy:

~~~bash
javac CoordinatedProducers.java
java CoordinatedProducers
~~~

Đầu ra trong điều kiện không bị ngắt:

~~~text
processed = [1, 2, 3, 4, 5, 6]
remaining = 0
~~~

Hai producer có thể xen kẽ enqueue Job ID theo thứ tự không đoán trước; chỉ **tập hợp** Job nhận được là xác định. `Collections.sort(processed)` chạy ở main **sau** khi `consumer.join()` nên không có data race trên `ArrayList`: chỉ một consumer sửa list, main đọc sau khi consumer kết thúc.

**Giới hạn production:** Producer demo trên bắt `InterruptedException` và thoát nhưng không báo lỗi riêng. Nếu một producer bị interrupt trước khi gửi đủ 3 Job, coordinator vẫn có thể gửi STOP và program không được coi đó là “đã xử lý đủ yêu cầu”. Trong hệ thống thật, cần thu **producer result/failure** bằng `Future.get()`, một kênh error, hoặc status rõ ràng và áp dụng policy: drain phần đã nhận, retry phần chưa gửi, hoặc chuyển sang shutdown bất thường. **Kết thúc thread không đồng nghĩa producer thành công.**

Nếu cần bảo đảm tuyệt đối producer không gửi sau điểm đóng admission, phải có một cơ chế ownership/gate hoặc một coordinator quản lý các job sources; chỉ nhìn `queue.size() == 0` không cho biết các producer đã dừng.

## 8. Ví dụ sai có thể tái hiện chắc chắn: STOP được enqueue quá sớm

Một lỗi nguy hiểm là phát STOP **trước khi các producer thật sự dừng**. Điều này không chỉ là race hiếm: ta có thể dựng một lịch xen kẽ xác định để thấy một Job bị bỏ lại.

Tạo `EarlyPoisonBug.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class EarlyPoisonBug {
    sealed interface Message permits Job, Stop {}
    record Job(int id) implements Message {}
    enum Stop implements Message { INSTANCE }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> queue = new LinkedBlockingQueue<>();
        CountDownLatch sendLateJob = new CountDownLatch(1);
        List<Integer> processed = new ArrayList<>();

        Thread lateProducer = new Thread(() -> {
            try {
                sendLateJob.await();
                queue.put(new Job(2)); // Đến SAU STOP.
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });

        Thread consumer = new Thread(() -> {
            try {
                while (true) {
                    Message message = queue.take();
                    if (message == Stop.INSTANCE) {
                        return;
                    }
                    processed.add(((Job) message).id());
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        lateProducer.start();

        queue.put(new Job(1));
        queue.put(Stop.INSTANCE); // LỖI: lateProducer chưa xong!
        sendLateJob.countDown();

        lateProducer.join();
        consumer.join();

        System.out.println("processed = " + processed);
        System.out.println("leftover = " + queue.peek());
    }
}
~~~

Chạy:

~~~bash
javac EarlyPoisonBug.java
java EarlyPoisonBug
~~~

Đầu ra được điều khiển bởi thứ tự enqueue:

~~~text
processed = [1]
leftover = Job[id=2]
~~~

Dù consumer và producer nào được OS chạy trước, các phép enqueue có thứ tự: `Job(1)` → `Stop` → `Job(2)`. Một consumer duy nhất xử lý Job 1 rồi gặp STOP và return. Job 2 không có consumer nào xử lý, còn nằm trong queue.

**Cách sửa:** không phát STOP cho tới khi late producer và mọi producer khác đã xác nhận hoàn tất việc enqueue; trong demo, thứ tự đúng là phát `sendLateJob.countDown()`, đợi `lateProducer.join()` rồi mới `queue.put(Stop.INSTANCE)`. Nhưng còn phải xử lý trường hợp producer kết thúc vì lỗi, không chỉ kết thúc thread.

## 9. `BlockingQueue` capacity và nguy cơ shutdown bị kẹt

Poison pill là **một phần tử thông thường** đối với queue. Nếu dùng bounded queue, khi queue đầy:

~~~java
queue.put(Stop.INSTANCE); // Có thể BLOCK tới khi có consumer lấy item.
~~~

Trong shutdown bình thường, chờ chỗ trống thường hợp lệ: các consumer đang drain work sẽ tạo capacity. Nhưng có các trường hợp **không tiến triển**:

- Không còn consumer sống để `take()`.
- Consumer bị kẹt ở I/O hoặc lỗi nghiệp vụ không thoát; queue vẫn đầy.
- Các producer đang chờ `put` nhưng coordinator phát STOP trong khi consumer chưa được start/scheduled.
- Dùng executor có số thread quá nhỏ: mọi worker pool đều đang chạy producer bị block ở `put`, còn consumer task **xếp hàng trong cùng pool và chưa được cấp worker**.
- Coordinator giữ một lock mà consumer cần để hoàn thành, đồng thời coordinator đang chờ `put(POISON)` tạo thành vòng chờ.
- Consumer gặp STOP và thoát nhưng còn Job phía sau, không còn thread nào xử lý chúng.

Vì vậy, cần chiến lược về **timeout, interrupt, lỗi và tài nguyên**. Đối với bounded queue, có thể dùng `offer(poison, timeout, unit)` để giới hạn thời gian chờ enqueue:

~~~java
// Snippet trong phương thức có thể ném InterruptedException.
boolean inserted = queue.offer(
        Stop.INSTANCE, 5, java.util.concurrent.TimeUnit.SECONDS);
if (!inserted) {
    // Chuyển sang nhánh shutdown lỗi/timeout; KHÔNG giả định đã dừng.
}
~~~

**Rất quan trọng:** `offer` trả `false` nghĩa là poison **chưa được đưa vào queue**. Không được đánh dấu consumer đã nhận STOP hoặc gọi shutdown thành công. Nhánh fallback phải có nghĩa thực: báo lỗi cho coordinator, thử lại có giới hạn, interrupt/cancel consumer, hoặc chuyển trạng thái hệ thống theo policy.

`offer` timed không tự bảo đảm việc xử lý xong trong 5 giây. Nó chỉ giới hạn **thời gian chờ chỗ trống để enqueue**.

### `put` và `take` đều interruptible

`BlockingQueue.put`/`take` có thể ném `InterruptedException`. Không nên bắt exception rồi lặng lẽ tiếp tục vô hạn. Với consumer muốn thoát khi bị ngắt:

~~~java
// Snippet minh họa, không phải chương trình độc lập.
try {
    while (true) {
        Message message = queue.take();
        if (message == Stop.INSTANCE) {
            break;
        }
        process(message);
    }
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Dọn dẹp và báo kết thúc bất thường; có thể còn work trong queue.
} finally {
    cleanupConsumerResources();
}
~~~

`Thread.currentThread().interrupt()` khôi phục cờ interrupt khi tầng hiện tại không xử lý tiếp; cụ thể nên thoát task, để chủ sở hữu quyết định trạng thái/hủy phù hợp. Không nhầm việc consumer thoát do interruption với **graceful drain** của poison pill.

## 10. Consumer gặp exception khi xử lý một Job

Poison pill chỉ điều phối **điểm kết thúc bình thường**. Khi `process(job)` ném exception, cần policy riêng:

| Policy | Ý nghĩa | Rủi ro/đổi chác |
| --- | --- | --- |
| **Fail-fast** | Consumer dừng và báo lỗi cho coordinator | Queue có thể còn backlog, poison có thể không được nhận |
| **Retry có giới hạn** | Retry với backoff/deadline | Cần tránh lặp vô hạn, idempotency với side effects |
| **Dead-letter** | Lưu thất bại ở kênh riêng rồi tiếp tục | Cần bảo đảm lưu/report lỗi và quyền truy cập |
| **Skip và ghi nhận** | Bỏ Job lỗi, xử lý những Job khác | Chỉ hợp lệ khi nghiệp vụ chấp nhận dữ liệu thiếu |
| **Cancel toàn pipeline** | Dừng producer và consumer, giải phóng tài nguyên | Không phải graceful shutdown; phải xử lý item đang dở |

Mọi lựa chọn cần trả lời: Job hiện tại được coi là **done**, **failed** hay **pending**? Nếu consumer bỏ qua exception và tiếp tục nhận STOP, việc consumer kết thúc **không chứng minh tất cả Job thành công**.

### Ack sau xử lý, không phải sau `take`

Nếu cần cam kết hoàn thành, hãy tạo/ghi nhận acknowledgment **sau** khi `process(job)` thành công. `take()` chỉ chứng minh item đã rời queue, không chứng minh kết quả đã được lưu. Đối với công việc có side effect ngoài bộ nhớ JVM (database/mạng), còn phải thiết kế idempotency và cách xử lý việc bị gián đoạn giữa xử lý và ack.

Poison pill không tự đảm bảo **exactly-once processing**. Nó là tín hiệu end-of-stream của giao thức queue, không phải transaction hoặc durability mechanism.

## 11. Phối hợp với `ExecutorService`: poison và shutdown là hai lớp khác nhau

Có hai vòng đời:

- **Consumer loop** do ứng dụng viết: thường `queue.take()` lặp vô hạn cho tới STOP hoặc cancellation.
- **ExecutorService** chạy task consumer: sở hữu worker threads, nhận task mới và cung cấp cơ chế `shutdown()`/`awaitTermination()`.

Gọi `executor.shutdown()` **không tự thêm STOP vào queue của ứng dụng**. Nếu một consumer task đã được submit và đang kẹt ở `take()`, graceful executor shutdown vẫn phải chờ task đó tự kết thúc; nếu không có STOP/cancellation, executor có thể không terminated.

Ngược lại, consumer nhận STOP và return **không tự đóng executor**. Chủ sở hữu vẫn phải gọi shutdown theo chính sách phù hợp.

Một quy trình logic:

~~~text
A. Ngừng tiếp nhận work mới vào hệ thống.
B. Đợi producer tasks hoàn thành (kiểm tra Future.get để biết lỗi).
C. Enqueue đủ STOP cho các consumer thực sự đang nhận queue.
D. Đợi consumer tasks kết thúc qua Future.get/join.
E. ExecutorService.shutdown và awaitTermination nếu đang quản lý executor.
F. Đóng file/socket/tài nguyên khác theo policy; ghi nhận kết quả pipeline.
~~~

Nếu `ExecutorService` dùng để quản lý cả producer và consumer, đảm bảo **đủ worker để consumer thực sự chạy** trong lúc producer đợi bounded queue. Ví dụ một pool có 2 thread, 2 producer đã chiếm cả hai và block tại `put`, còn consumer mới chỉ đang ở queue của executor: đây là **thread-pool starvation deadlock**. Có thể dùng pool riêng, số worker phù hợp hoặc kiến trúc không block producer khi không có consumer.

### So sánh các API dừng

| Cơ chế | Làm gì? | Không làm gì? |
| --- | --- | --- |
| `queue.put(STOP)` | Gửi tín hiệu bằng queue, giữ thứ tự của các lần enqueue hợp lệ | Không tự đợi consumer; không ép thread dừng |
| `Thread.join()` | Đợi một thread kết thúc | Không tự báo lỗi xử lý work, không đặt STOP |
| `Future.get()` | Đợi task và lấy kết quả/exception của task được submit | Không tự đóng queue |
| `ExecutorService.shutdown()` | Không nhận task mới, cho task đã nhận tiếp tục theo hợp đồng | Không tự phát STOP vào queue tùy ý |
| `ExecutorService.awaitTermination(...)` | Đợi executor terminated sau shutdown | Không tự sửa một consumer kẹt `take()` |
| `ExecutorService.shutdownNow()` | Cố interrupt task đang chạy và trả task chưa chạy, best effort | Không bảo đảm drain work hoặc terminate tức thì |
| `Thread.interrupt()` | Phát tín hiệu interrupt cho thread | Không bảo đảm mọi code dừng ngay hay xử lý xong backlog |

Với mục tiêu **graceful drain**, ưu tiên cho consumer tự thấy STOP và return; dùng timeout/cancellation path riêng khi shutdown không thể tiến triển hoặc yêu cầu khẩn cấp. `shutdownNow()` không tương đương “poison pill nhanh hơn”.

## 12. FIFO ordering và giới hạn của tính trật tự

Một nguyên tắc hay bị hiểu sai: “STOP được enqueue sau Job thì các Job chắc chắn đã hoàn thành trước mọi STOP được xử lý”. Cần phân biệt:

1. **Thứ tự enqueue:** Trong một FIFO queue, Job được enqueue trước poison nằm trước nó theo thứ tự queue.
2. **Thứ tự dequeue:** Các item trước STOP được lấy trước STOP (bỏ qua các thao tác khác làm thay đổi queue như remove/drain).
3. **Thứ tự xử lý:** Nếu chỉ **một consumer**, xử lý synchronous trước lần `take` tiếp, mỗi Job trước STOP được xử lý trước khi consumer thoát.
4. **Nhiều consumer:** Một consumer có thể nhận STOP và thoát trong khi consumer khác **vẫn xử lý Job đã lấy trước đó**. Vì vậy đợi **tất cả consumers** hoặc nhận đủ ack mới kết luận pipeline đã hoàn thành.
5. **Consumer dispatch async:** Nếu một consumer chỉ lấy Job rồi submit sang executor khác và ngay lập tức `take` tiếp, nó có thể nhận STOP và thoát **trước khi các task đã chuyển tiếp hoàn tất**. Cần đợi downstream tasks riêng.

Không phải mọi implementation `BlockingQueue` đều giữ FIFO theo cùng semantics. Ví dụ `PriorityBlockingQueue` lấy theo **priority/comparator**, vì vậy STOP không nhất thiết đứng sau Job dù enqueue sau; một poison có priority cao có thể được lấy trước backlog. `DelayQueue` chỉ trả những phần tử đã hết delay. `SynchronousQueue` không có vùng lưu backlog; `put` trực tiếp trao phần tử cho consumer đợi. **Giao thức phải phù hợp với queue thực sự chọn.**

Nếu dùng `PriorityBlockingQueue`, hãy thiết kế thứ tự poison sao cho không phá backlog và vẫn bảo đảm không còn producer enqueue Job, hoặc chọn kênh completion riêng. Với nhiều worker và priority khác nhau, cần giải bài toán termination cụ thể; không mang quy tắc FIFO sang queue khác rồi kết luận luôn đúng.

## 13. Tín hiệu STOP nằm cùng queue mang lại điều gì?

`BlockingQueue` có bảo đảm *memory consistency*: hành động producer **trước khi** đặt một object vào queue *happen-before* hành động consumer **sau khi** lấy object ấy khỏi queue. Điều này giúp truyền dữ liệu work đã chuẩn bị tới consumer an toàn, nếu dữ liệu đó không bị mutate vô kỷ luật sau publication.

Ngoài ra:

- STOP đi qua cùng đường nhận việc nên consumer không cần polling cờ liên tục.
- Với queue FIFO, STOP có thứ tự tương đối rõ ràng với các work item đã được enqueue trước nó.
- Consumer có một nhánh chuyển trạng thái đơn giản: Work → process, Stop → cleanup/return.
- Hệ thống vẫn phải có cơ chế **dừng admission** và **đợi acknowledgments**. Queue memory visibility không tự thay các yêu cầu này.

**Không nên kết luận:** vì producer đã `put(job)` thì job chắc chắn được xử lý thành công; queue chỉ xác nhận enqueue (đối với `put` đã trả về), còn việc xử lý cần ack/result riêng.

## 14. Tổng hợp trạng thái shutdown và lỗi cần kiểm tra

Một coordinator có thể quản lý pipeline qua trạng thái:

| Trạng thái | Có nhận Job mới? | Producer còn tạo Job? | Consumer hoạt động? | Điều cần quan sát |
| --- | --- | --- | --- | --- |
| `RUNNING` | Có | Có | Có | Độ sâu queue, lỗi, tốc độ xử lý |
| `STOP_ACCEPTING` | Không | Đang xả việc đã nhận | Có | Producer hoàn thành hoặc failure |
| `SIGNALING_STOP` | Không | Không | Có | Enqueue đủ STOP thành công |
| `DRAINING` | Không | Không | Một phần còn hoạt động | Job in flight, ack, lỗi |
| `TERMINATED` | Không | Không | Không | Task join/Future.get đã xong, final status |
| `FAILED/CANCELLED` | Theo policy | Có thể dừng sớm | Có thể bị ngắt | Backlog/in-flight/dead-letter/khả năng retry |

Bảng là **mô hình ứng dụng**, không phải enum có sẵn trong JDK. Dấu chấm hết của consumer không đương nhiên là một trạng thái business success. Với producer lỗi, phải định nghĩa số lượng Job thực sự được chấp nhận và kết quả mong đợi.

### Checklist thiết kế

- **Nguồn work:** Ai được phép enqueue? Làm sao chặn producer mới khi chuẩn bị đóng?
- **Số consumer:** Cố định hay co giãn? Ai biết con số để phát STOP?
- **Tín hiệu:** Có kiểu riêng không? Có thể nhầm với payload hay null không?
- **Queue:** FIFO hay priority/delay/handoff? Có bounded capacity không?
- **Thứ tự:** STOP có chắc sau **mọi item đã được chấp nhận**?
- **Producer failure:** `join` hay `Future.get` có đủ để xác nhận thành công? Cần ghi nhận thiếu item không?
- **Consumer failure:** Consumer chết khi còn backlog thì STOP sẽ được ai nhận? Có giám sát và cancellation path không?
- **Ack:** “lấy khỏi queue” hay “xử lý thành công” là tiêu chí hoàn tất?
- **Timeout:** `put(STOP)` và `join` có thể chờ vô hạn không? Nếu timeout sẽ làm gì?
- **Downstream:** Consumer có submit async task khác không? Đã đợi downstream completion chưa?
- **Tài nguyên:** Connection/file/socket/callback cleanup đặt ở `finally` nào? Ai đóng executor?
- **Quan sát:** Metrics accepted/processed/failed/in-flight/stopped count có ý nghĩa nhất quán không?

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ gửi một poison cho nhiều consumer | Consumer còn lại có thể chờ `take()` mãi | Một STOP cho mỗi consumer theo protocol, hoặc cơ chế broadcast khác |
| Mỗi producer tự gửi STOP khi xong | STOP có thể đứng trước work của producer khác | Coordinator đợi **mọi producer** rồi phát STOP |
| Enqueue STOP khi admission còn mở | Item đến sau STOP bị bỏ lại | Ngừng nhận mới, đợi nguồn đang chạy, mới enqueue poison |
| Dùng chuỗi `"STOP"` trùng dữ liệu | Payload hợp lệ bị hiểu thành lệnh dừng | Kiểu message riêng/enum sentinel |
| Dùng `null` làm poison | `BlockingQueue` không nhận null | Sentinel non-null có kiểu rõ ràng |
| Gọi `queue.clear()` rồi phát STOP | Mất backlog chưa xử lý | Phân biệt abort với graceful drain |
| Không `join`/`Future.get` sau phát STOP | Bắt đầu đóng tài nguyên khi consumer còn chạy | Đợi termination và kiểm tra lỗi |
| Dựa vào `queue.isEmpty()` làm bằng chứng done | Job đã dequeue còn đang xử lý | Theo dõi in-flight, ack, task completion |
| Bounded queue đầy, `put(POISON)` vô hạn | Coordinator shutdown có thể treo | Timeout/fallback và giám sát consumer |
| Consumer bị interrupt nhưng coi là graceful | Work có thể còn backlog | Báo cancel/failure, kế hoạch retry/cleanup |
| Consumer exception rồi âm thầm thoát | Poison bị bỏ lại, mất Job | Báo lỗi, điều phối restart/cancel |
| Producer/consumer cùng pool quá nhỏ | Producer block làm consumer không được chạy | Thiết kế capacity/pool, pool tách hoặc nonblocking |
| Dùng `PriorityBlockingQueue` và tin enqueue order | STOP được lấy trước backlog | Xét comparator/priority, chọn protocol khác |
| Consumer dispatch async rồi nhận STOP là xong | Downstream task chưa hoàn tất | Đợi các Future/ack downstream |
| Dùng `shutdownNow` để thay poison | Ngắt xử lý, không drain backlog | Chọn rõ graceful hay immediate cancellation |
| Tin poison bảo đảm exactly-once | Không xử lý crash, retry, side effects | Idempotency, ack, persistent queue/transaction phù hợp |

## 16. Tự kiểm tra

**Câu 1.** Có ba consumer cùng `take()` từ một `ArrayBlockingQueue` FIFO, sau khi mọi producer ngừng, coordinator chỉ enqueue một poison. Đã đủ để cả ba rời vòng lặp chưa?  
**Đáp án:** Chưa. Một `take` loại bỏ poison, nên chỉ một consumer nhận; theo giao thức mỗi consumer nhận một STOP, cần ba STOP hoặc giải pháp khác.

**Câu 2.** Producer A gửi xong và enqueue STOP, producer B vẫn có thể enqueue Job. Bài toán là gì?  
**Đáp án:** Consumer có thể gặp STOP trước Job của B rồi thoát, để lại backlog. Phải đóng admission/đợi mọi producer trước khi phát STOP.

**Câu 3.** `queue.isEmpty() == true` nhưng consumer đang thực hiện Job vừa `take()`. Có thể đóng database ngay không?  
**Đáp án:** Không thể dựa vào `isEmpty()`. Job đã rời queue nhưng chưa xử lý xong; cần completion acknowledgment.

**Câu 4.** `BlockingQueue.put(STOP)` có thể chặn dù việc gửi poison đúng lúc không?  
**Đáp án:** Có, nếu queue bounded đang đầy. Trong graceful shutdown, consumer tiến triển sẽ tạo capacity. Nếu consumer chết/kẹt, cần timeout và failure policy.

**Câu 5.** Tại sao `BlockingQueue.put(null)` không thể là poison?  
**Đáp án:** Queue không chấp nhận null; các thao tác enqueue null ném `NullPointerException`.

**Câu 6.** Một consumer nhận STOP rồi return, executor có tự terminated ngay không?  
**Đáp án:** Không. Executor có lifecycle riêng, vẫn cần `shutdown`/`awaitTermination` phù hợp.

**Câu 7.** Gọi `ExecutorService.shutdown()` trước khi consumer task thoát có tự khiến `take()` trả về end-of-stream không?  
**Đáp án:** Không. Shutdown chỉ ngăn task mới; consumer task đã được nhận vẫn chờ queue theo logic của nó.

**Câu 8.** Producer gọi `put(Job)` thành công, có đồng nghĩa Job được xử lý thành công không?  
**Đáp án:** Không. Put chỉ xác nhận đã enqueue. Cần ack sau processing hoặc kết quả task.

**Câu 9.** Nếu consumer lấy Job rồi submit công việc cho executor khác, sau đó nhận STOP, đã hoàn thành mọi Job trước STOP chưa?  
**Đáp án:** Chưa chắc. Consumer mới hoàn tất dispatch; phải đợi downstream task completion.

**Câu 10.** Tại sao `PriorityBlockingQueue` cần thiết kế poison khác với FIFO queue?  
**Đáp án:** Vì dequeue theo comparator/priority, không phải thứ tự enqueue; STOP có thể được lấy trước các Job được enqueue trước nó.

## Tài liệu chính thức

- [`BlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `put`/`take`, timed `offer`/`poll`, không nhận null, không có close/shutdown chung, memory consistency.
- [`ArrayBlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO queue cho producer–consumer.
- [`LinkedBlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): FIFO linked queue, tùy chọn capacity.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối các giai đoạn.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination`, `Future`.
- [`Thread` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `join`, `interrupt`, thread lifecycle.
- [`PriorityBlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): ordering theo priority, khác queue FIFO.

**Ghi nhớ:** Poison pill có ý nghĩa khi **đứng sau toàn bộ work đã được chấp nhận** và được **mọi consumer cần dừng** nhận theo protocol rõ ràng. Trình tự bền vững là **đóng nhận việc → đợi producer → gửi đủ STOP → đợi consumer → kiểm tra kết quả và giải phóng tài nguyên**.