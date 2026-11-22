# Thread priority trong Java: ý nghĩa và giới hạn bảo đảm

> **Trọng tâm:** `Thread.setPriority(int)` chỉ đặt mức ưu tiên *đề nghị* cho bộ lập lịch của platform thread. Giá trị cao hơn **không cam kết** chạy trước, chạy nhanh hơn, được cấp một tỉ lệ CPU nhất định hoặc hoàn thành sớm hơn. Vì vậy, không dùng priority làm điều kiện đúng/sai của chương trình đồng thời.

## 1. Thread priority giải quyết điều gì?

Khi nhiều thread sẵn sàng chạy nhưng số lõi CPU hoặc tài nguyên xử lý có hạn, hệ điều hành/JVM phải quyết định thread nào được thực thi. `Thread` của Java có thuộc tính `priority` để cung cấp một tín hiệu về mức độ ưu tiên tương đối của **platform thread**. Priority không phải thứ tự công việc trong hàng đợi, cũng không phải deadline, cơ chế cấp quyền truy cập tài nguyên hay mức độ quan trọng của dữ liệu.

Phân biệt bốn khái niệm:

| Khái niệm | Trả lời câu hỏi | Priority có bảo đảm không? |
| --- | --- | --- |
| **Scheduling** (lập lịch) | Thread nào có cơ hội chạy khi CPU khan hiếm? | Chỉ là một gợi ý, tùy JVM/OS. |
| **Ordering** (thứ tự) | Tác vụ A bắt buộc được xử lý trước B? | **Không.** Dùng hàng đợi/phối hợp rõ ràng. |
| **Synchronization** (đồng bộ) | Dữ liệu chung có đúng và nhất quán? | **Không.** Dùng lock, volatile, atomic, concurrent collections... |
| **Deadline / latency** | Công việc kết thúc trước thời hạn nào? | **Không.** Cần thiết kế tài nguyên, timeout, đo đạc, kiểm soát tải. |

Ngay cả khi thread có priority cao hơn, nó có thể đang `BLOCKED` để lấy khóa, `WAITING` để nhận tín hiệu, `TIMED_WAITING` vì ngủ/chờ thời hạn, hoặc chờ I/O. Priority không làm các điều kiện chờ đó biến mất.

## 2. Các mức priority và Java API

`java.lang.Thread` định nghĩa ba hằng số và khoảng giá trị hợp lệ:

| Hằng số | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| `Thread.MIN_PRIORITY` | `1` | Mức nhỏ nhất |
| `Thread.NORM_PRIORITY` | `5` | Mức mặc định thông dụng |
| `Thread.MAX_PRIORITY` | `10` | Mức lớn nhất |

Các số nguyên từ `1` đến `10` đều có thể truyền vào `setPriority(int)`. Đây là **thang priority do API Java biểu diễn**, không đồng nghĩa với các cấp priority của hệ điều hành. Cách JVM ánh xạ, số mức được phân biệt thực sự và ảnh hưởng của nó có thể khác nhau theo nền tảng và cấu hình.

Các thao tác chính:

~~~java
thread.setPriority(Thread.MIN_PRIORITY);  // Yêu cầu mức 1.
thread.setPriority(Thread.NORM_PRIORITY); // Yêu cầu mức 5.
thread.setPriority(Thread.MAX_PRIORITY);  // Yêu cầu mức 10.
int configuredPriority = thread.getPriority();
~~~

- `setPriority` với giá trị ngoài `1..10` ném `IllegalArgumentException`; không có cơ chế tự kẹp giá trị đầu vào không hợp lệ vào khoảng này.
- Đối với **platform thread**, mức thực tế được ghi nhận trong Java không vượt quá mức tối đa mà `ThreadGroup` của thread cho phép. Vì vậy, yêu cầu `10` có thể dẫn tới giá trị `getPriority()` thấp hơn `10` trong một group có trần thấp.
- `getPriority()` trả về thuộc tính priority của thread trong Java. **Không** hiểu đó là bằng chứng hệ điều hành đã ưu tiên chạy thread, hoặc là phép đo CPU share.
- Có thể cấu hình priority cho platform thread trước `start()`, hoặc thay đổi khi thread đang sống; thay đổi sau khi chạy không đồng nghĩa tác động tức thời, cố định hoặc có thể dự báo đến scheduler.
- Platform thread mới thường **kế thừa priority** của thread tạo nó, đồng thời chịu giới hạn `ThreadGroup`. Không nên dựa vào tính kế thừa ngầm khi cần một cấu hình cụ thể; hãy đặt rõ ràng cho thread được tạo ra.

`ThreadGroup` là API cũ và hiếm khi cần cho mã Java mới; hiểu giới hạn priority của nó giúp giải thích vì sao `setPriority(MAX_PRIORITY)` không phải lúc nào cũng khiến `getPriority() == 10`.

## 3. Ví dụ Java 17+ có đầu ra xác định

Tạo tệp `PriorityBasics.java`:

~~~java
public class PriorityBasics {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                () -> System.out.println(
                        "inside = " + Thread.currentThread().getPriority()),
                "demo-worker");

        // MIN_PRIORITY luôn nằm trong phạm vi hợp lệ của platform thread.
        worker.setPriority(Thread.MIN_PRIORITY);
        System.out.println("before start = " + worker.getPriority());

        worker.start();
        worker.join(); // Bảo đảm worker in xong trước dòng cuối.

        try {
            worker.setPriority(Thread.MAX_PRIORITY + 1);
        } catch (IllegalArgumentException expected) {
            System.out.println("out of range");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PriorityBasics.java
java PriorityBasics
~~~

Đầu ra:

~~~text
before start = 1
inside = 1
out of range
~~~

Điều ví dụ chứng minh: ta có thể thiết lập và đọc **giá trị priority trong Java**; `join()` tạo thứ tự chờ hoàn thành nên vị trí các dòng in được xác định. Ví dụ **không** chứng minh rằng priority `1` chạy chậm hay priority `10` chạy nhanh. Hai dòng đầu phản ánh trạng thái cấu hình, không phải kết quả lập lịch CPU.

Nếu thay `MIN_PRIORITY` bằng `MAX_PRIORITY`, giá trị đọc thường là `10` trong group mặc định, nhưng có thể bị giới hạn bởi group. Không được viết bài test bắt buộc mọi môi trường đều quan sát một mức CPU/tốc độ giống nhau.

## 4. Vì sao không có bảo đảm “priority cao chạy trước”?

Một số nguyên nhân có thể cùng xuất hiện:

1. **Lập lịch phụ thuộc nền tảng.** JVM phối hợp với hệ điều hành để chạy platform thread; chính sách scheduler, độ ưu tiên native, permission, cgroup/container và tải máy ảnh hưởng đến kết quả. Java API không hứa lịch thực thi toàn cục theo priority.
2. **Nhiều lõi có thể chạy song song.** Thread priority thấp vẫn có thể chạy đồng thời với thread priority cao; khái niệm “trước” thường không có nghĩa khi cả hai được cấp CPU.
3. **Trạng thái sẵn sàng khác trạng thái chạy.** Thread ưu tiên cao có thể đang chờ lock, I/O, tín hiệu hoặc bị tạm dừng bởi cơ chế khác; thread thấp hơn vẫn có thể tiến triển.
4. **Hiệu năng không chỉ phụ thuộc thời gian CPU.** Khóa, bộ nhớ, cache CPU, JIT, garbage collection, đồng bộ, I/O và thuật toán có thể chi phối thời gian hoàn thành.
5. **Không có fairness hay starvation-freedom từ API.** Không có cam kết mỗi thread sẽ nhận CPU sau một khoảng tối đa, hoặc thread thấp sẽ không bị “đói” tài nguyên dưới tải.

Không suy ra các mệnh đề sau từ priority:

- `high.start()` rồi `low.start()` ⇒ `high` in ra trước `low`.
- `high.getPriority() > low.getPriority()` ⇒ `high` luôn lấy lock trước.
- `high` có priority `10` ⇒ luôn hoàn thành trước deadline.
- `low` có priority `1` ⇒ sẽ không bao giờ được chạy.
- Hai thread cùng priority ⇒ chia CPU 50/50 hoặc thực thi theo FIFO.

**Một lần chạy thử** tình cờ cho kết quả “đúng thứ tự” không biến hành vi đó thành hợp đồng của Java.

## 5. Thí nghiệm quan sát: đo, nhưng không suy ra hợp đồng

Ví dụ sau cố ý tạo hai platform thread tính toán cạnh tranh CPU. Lưu thành `PriorityObservation.java`:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public class PriorityObservation {
    public static void main(String[] args) throws InterruptedException {
        AtomicBoolean running = new AtomicBoolean(true);
        long[] counts = new long[2];

        Thread low = new Thread(() -> {
            long n = 0;
            while (running.get()) {
                n++;
            }
            counts[0] = n;
        }, "low");

        Thread high = new Thread(() -> {
            long n = 0;
            while (running.get()) {
                n++;
            }
            counts[1] = n;
        }, "high");

        low.setPriority(Thread.MIN_PRIORITY);
        high.setPriority(Thread.MAX_PRIORITY);

        low.start();
        high.start();

        Thread.sleep(1_500);
        running.set(false);

        low.join();
        high.join();

        System.out.println("low = " + counts[0]);
        System.out.println("high = " + counts[1]);
    }
}
~~~

Chạy với:

~~~bash
javac PriorityObservation.java
java PriorityObservation
~~~

Chương trình in hai **số đếm tùy lần chạy**; không có stdout số học cố định. Tùy hệ điều hành, CPU, số lõi, tải hệ thống, warm-up JIT và cách ánh xạ priority, `high` có thể đếm nhiều hơn, gần bằng, thậm chí ít hơn `low`. Không nên dùng so sánh số đếm này làm unit test hay cam kết sản phẩm.

Điểm đúng về concurrency trong ví dụ: `running.get()`/`set(false)` của `AtomicBoolean` cung cấp cơ chế quan sát tín hiệu dừng giữa các thread; `join()` chờ cả hai kết thúc và cung cấp quan hệ *happens-before* để main đọc `counts` sau khi worker ghi. **Priority không chịu trách nhiệm cho tính an toàn bộ nhớ này.**

Vòng lặp bận ở đây chỉ dùng để minh họa scheduler trong môi trường thử nghiệm ngắn. Trong ứng dụng thật, tránh đốt CPU bằng busy-wait chỉ để “tranh quyền ưu tiên”; chọn blocking queue, wait/notify, lock/condition, semaphore hoặc API concurrent phù hợp.

Muốn thực nghiệm có ý nghĩa hơn, hãy ghi lại JDK/JVM, OS, giới hạn CPU/container, số core, các priority được `getPriority()` trả về, và đo nhiều lần sau warm-up. Kết quả đo vẫn chỉ mô tả **môi trường đã đo**.

## 6. Priority không thay thế đồng bộ, tính đúng đắn hay hủy tác vụ

### 6.1. Không thể dùng priority làm tín hiệu “xong việc”

Sai về thiết kế:

~~~java
// Minh họa lỗi logic; không phải chương trình độc lập.
producer.setPriority(Thread.MAX_PRIORITY);
producer.start();
consumer.start(); // Không thể suy ra producer đã tạo dữ liệu xong.
~~~

Nếu consumer cần kết quả của producer, hãy dùng một quan hệ phối hợp có hợp đồng, ví dụ:

~~~java
// Minh họa API phối hợp, không phải chương trình độc lập.
producer.start();
producer.join();   // Chỉ sau khi producer kết thúc mới tiếp tục.
consumer.start();
~~~

Trong bài toán thực tế không nên `join` mọi tác vụ theo chuỗi nếu cần throughput song song; có thể dùng `BlockingQueue`, `CountDownLatch`, `Future`, `CompletableFuture` hoặc cơ chế bảo vệ dữ liệu phù hợp. Điều cốt lõi là **thứ tự phụ thuộc dữ liệu phải được mã hóa trực tiếp**.

### 6.2. Priority không tạo *happens-before*

Java Memory Model quy định cách thread quan sát ghi/đọc giữa các thread. Việc gọi `setPriority`, hoặc thấy một thread có priority cao hơn, **không tự tạo** quan hệ *happens-before* giữa các thao tác trên dữ liệu dùng chung. Phải dùng các cơ chế có ngữ nghĩa đồng bộ, chẳng hạn `volatile`, `synchronized`, `Lock`, atomic variable, `Thread.start()`, `Thread.join()`, hay các lớp `java.util.concurrent` theo hợp đồng riêng.

### 6.3. Priority không chữa deadlock, starvation hay priority inversion

- **Deadlock:** các thread giữ khóa rồi chờ lẫn nhau; tăng priority không phá được vòng chờ.
- **Starvation:** một thread có thể đợi rất lâu để lấy CPU/lock/tác vụ tiếp theo; Java priority không cung cấp cam kết công bằng.
- **Priority inversion:** một thread ưu tiên cao đợi khóa do thread ưu tiên thấp giữ; thread khác có thể khiến thread giữ khóa chậm được chạy. Một số hệ điều hành có kỹ thuật như *priority inheritance* ở một số loại khóa, nhưng **không được mặc định Java monitor (synchronized) có cam kết priority inheritance di động giữa mọi JVM/OS**.

Biện pháp thiết kế thường thiết thực hơn: giữ critical section ngắn, tránh giữ khóa trong lúc I/O, giảm cạnh tranh tài nguyên, xác lập thứ tự lấy khóa, dùng timeout khi phù hợp và quan sát thread dump.

### 6.4. Priority không thay thế interruption

`interrupt()` là tín hiệu hợp tác để dừng/hủy công việc hoặc đánh thức một số thao tác chờ có khả năng bị ngắt. `setPriority(MAX_PRIORITY)` không buộc thread đang chờ hoàn thành, không ép thread thoát khỏi `sleep()`, `wait()` hay thao tác blocking; xử lý `InterruptedException` và chính sách hủy cần được thiết kế độc lập.

## 7. Cần “tác vụ quan trọng được chọn trước”? Dùng hàng đợi ưu tiên

Nếu yêu cầu là: *“Khi worker lấy tác vụ tiếp theo, tác vụ khẩn phải được chọn trước tác vụ thông thường đang chờ”*, thì hãy biểu diễn **ưu tiên tác vụ** trong cấu trúc dữ liệu, thay vì nâng priority của worker thread.

Ví dụ Java 17+ sử dụng `PriorityBlockingQueue`. Lưu thành `PriorityQueueExample.java`:

~~~java
import java.util.concurrent.PriorityBlockingQueue;

public class PriorityQueueExample {
    record Task(int importance, long arrival, String name)
            implements Comparable<Task> {
        @Override
        public int compareTo(Task other) {
            int byImportance = Integer.compare(
                    other.importance, this.importance); // Cao trước
            if (byImportance != 0) {
                return byImportance;
            }
            return Long.compare(this.arrival, other.arrival); // FIFO khi bằng
        }
    }

    public static void main(String[] args) {
        PriorityBlockingQueue<Task> queue = new PriorityBlockingQueue<>();

        // Nạp hết trước khi lấy để minh họa thứ tự lựa chọn.
        queue.add(new Task(1, 0, "background"));
        queue.add(new Task(10, 1, "urgent"));
        queue.add(new Task(5, 2, "normal"));
        queue.add(new Task(10, 3, "urgent-later"));

        while (!queue.isEmpty()) {
            System.out.println(queue.remove().name());
        }
    }
}
~~~

Chạy:

~~~bash
javac PriorityQueueExample.java
java PriorityQueueExample
~~~

Kết quả xác định:

~~~text
urgent
urgent-later
normal
background
~~~

Ở đây `compareTo` đặt quy tắc nghiệp vụ rõ ràng: `importance` lớn hơn được **lấy khỏi queue trước**; khi bằng nhau, `arrival` nhỏ hơn được lấy trước. Sự sắp xếp này là hợp đồng của cấu trúc dữ liệu theo comparator, khác với gợi ý CPU scheduling.

Giới hạn phải hiểu đúng:

- Priority queue ưu tiên **phần tử đang chờ được lấy ra**, không thể giành lại (preempt) công việc worker đã lấy và đang chạy.
- Nếu nhiều worker lấy và chạy cùng lúc, **thứ tự hoàn thành** có thể khác thứ tự lấy việc.
- `PriorityBlockingQueue` là queue **không giới hạn dung lượng theo capacity cố định**; dưới tải liên tục phải thiết kế giới hạn, admission control/backpressure và cơ chế chống starvation cho tác vụ ưu tiên thấp. `put` không tạo chờ vì queue đầy như `ArrayBlockingQueue`.
- Trong demo, `arrival` được cấp tuần tự; hệ thống đa producer cần một số thứ tự duy nhất/an toàn thread hoặc định nghĩa rõ cách xử lý trường hợp bằng điểm.
- Nếu một luồng tác vụ ưu tiên cao liên tục đến, tác vụ thấp có thể nằm chờ lâu; cân nhắc quota, age-based priority hoặc các queue riêng có phân bổ tài nguyên.

## 8. Platform thread và virtual thread khác nhau ở điểm nào?

Từ **Java 21**, Java hỗ trợ virtual thread như một lựa chọn ổn định. Cần phân biệt:

| | Platform thread | Virtual thread (Java 21+) |
| --- | --- | --- |
| Scheduling | Thông thường JVM dựa trên thread của hệ điều hành | Được runtime Java lập lịch trên các carrier platform thread |
| `getPriority()` | Thuộc tính `1..10` trong giới hạn group | Luôn là `Thread.NORM_PRIORITY` (`5`) |
| `setPriority(int)` | Thay đổi giá trị Java-level trong giới hạn group; hiệu ứng OS phụ thuộc nền tảng | **Bỏ qua yêu cầu thay đổi** (giá trị đầu vào vẫn phải nằm trong khoảng hợp lệ) |
| Nên dùng priority để kiểm soát thứ tự công việc? | Không | Không |

Đoạn độc lập sau **chỉ chạy trên JDK 21+**. Lưu thành `VirtualPriority.java`:

~~~java
public class VirtualPriority {
    public static void main(String[] args) throws InterruptedException {
        Thread virtual = Thread.ofVirtual().unstarted(
                () -> System.out.println(
                        "inside = " + Thread.currentThread().getPriority()));

        virtual.setPriority(Thread.MAX_PRIORITY);
        System.out.println("configured = " + virtual.getPriority());

        virtual.start();
        virtual.join();
    }
}
~~~

Chạy `javac VirtualPriority.java` rồi `java VirtualPriority` trên JDK 21+. Kết quả:

~~~text
configured = 5
inside = 5
~~~

Không đem kỳ vọng về platform-thread priority áp dụng lên virtual thread. Nếu cần chọn công việc nào xử lý trước, hãy quyết định ở mức queue, điều phối và giới hạn tải.

## 9. Thiết kế thực tế khi có yêu cầu ưu tiên

| Nhu cầu thật | Cơ chế nên xem xét | Điều cần xác minh |
| --- | --- | --- |
| Tác vụ khẩn được **lấy trước** trong danh sách chờ | `PriorityBlockingQueue`/queue có comparator, tie-break và aging | Có chống starvation? Đa worker có làm đảo thứ tự hoàn thành? |
| Tác vụ quan trọng cần **độ trễ thấp** khi tải tăng | Tách executor/queue, dự trữ năng lực, backpressure, giới hạn concurrency | p95/p99 latency dưới tải, timeout, saturation |
| Chạy công việc **sau một khoảng trễ** hoặc lặp theo lịch | `ScheduledExecutorService` | Lịch chạy chỉ là mục tiêu, không phải real-time deadline chắc chắn |
| Bảo đảm **A xong mới đến B** | `join`, `Future`, `CompletableFuture`, synchronization primitive | Quan hệ phụ thuộc, xử lý lỗi/hủy |
| Chia tài nguyên **công bằng** | Semaphore/lock có chính sách fairness khi có hỗ trợ, quota, weighted queue | Fairness cũng có chi phí và giới hạn riêng |
| Công việc có **hạn xử lý bắt buộc** | Kiến trúc kiểm soát thời gian thực, phân tích worst-case, admission control | JVM/GC/OS thông thường không tự cấp hard real-time guarantee |

`Thread.setPriority` có thể được thử như một **tinh chỉnh phụ thuộc môi trường** khi đã đo được vấn đề, hiểu chính sách scheduler và chấp nhận kết quả không di động. Nó không nên là cơ chế duy nhất để bảo vệ correctness, fairness hay deadline.

### Checklist khi đánh giá một thay đổi priority

1. Mục tiêu là **thứ tự lấy việc**, **độ trễ**, **CPU share**, hay **tính đúng đắn**? Viết thành yêu cầu kiểm chứng được.
2. Đây là platform thread hay virtual thread? Có trần `ThreadGroup` hoặc chính sách OS/container liên quan không?
3. Sau khi `setPriority`, `getPriority()` trả gì? Có cơ sở nào chứng minh scheduler hưởng ứng?
4. Benchmark có warm-up, nhiều lần chạy, tải đại diện, số lõi và metrics p95/p99/CPU đúng không?
5. Thiết kế có còn chạy **đúng** khi scheduler hoàn toàn bỏ qua priority không?
6. Có phương án queue, executor, giới hạn tải hay đồng bộ rõ ràng dễ bảo trì hơn không?

Nếu câu trả lời cho mục 5 là **không**, thiết kế đang phụ thuộc vào một giả định mà Java không bảo đảm; cần sửa cơ chế phối hợp.

## 10. Lỗi hiểu thường gặp và tự kiểm tra

**Lỗi 1: “`MAX_PRIORITY` là ưu tiên tuyệt đối.”** Không: `10` chỉ là giá trị lớn nhất của thang Java, có thể bị group giới hạn và không suy ra mức native/CPU chắc chắn.

**Lỗi 2: “`getPriority()==10` chứng minh OS ưu tiên đúng.”** Không: getter đọc thuộc tính Java, không đo lịch CPU thực thi.

**Lỗi 3: “Priority cao nên không cần lock/volatile/join.”** Không: dữ liệu chia sẻ và quan hệ phụ thuộc có quy tắc Java Memory Model độc lập với priority.

**Lỗi 4: “Priority queue và thread priority là một.”** Không: queue xác định phần tử nào được lấy trước; thread priority chỉ gợi ý scheduler cho platform thread.

**Lỗi 5: “Mọi thread Java đều chỉnh được priority.”** Không: virtual thread của Java 21+ có priority cố định `5`, yêu cầu thay đổi bị bỏ qua.

**Lỗi 6: “Benchmark một lần là bằng chứng.”** Không: scheduler, tải máy, JIT và khác biệt JVM/OS khiến kết quả có thể thay đổi.

Câu hỏi tự kiểm tra:

1. Nếu thread `T1` priority `10` đang đợi monitor của `T2` priority `1`, priority có bảo đảm `T1` giành được monitor trong 10 ms không? **Không.**
2. Nếu `T1` in trước `T2` ở 100 lượt thử, có thể dùng priority để bảo đảm thứ tự in ở production không? **Không.**
3. Khi cần tác vụ `urgent` được chọn từ các tác vụ *đang xếp hàng* trước `normal`, cơ chế nào diễn đạt trực tiếp quy tắc này? **Hàng đợi ưu tiên có comparator.**
4. Trong Java 21, `setPriority(10)` trên virtual thread khiến `getPriority()` trả bao nhiêu? **`5`.**

## Tham khảo API chính thức

- [`Thread` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `MIN_PRIORITY`, `NORM_PRIORITY`, `MAX_PRIORITY`, `setPriority`, `getPriority`, platform/virtual thread.
- [`PriorityBlockingQueue` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): cơ chế xếp thứ tự và đặc tính không giới hạn capacity.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): memory model, *happens-before*, synchronization.

**Ghi nhớ:** Priority là thuộc tính scheduling có giới hạn; mọi điều kiện về thứ tự, bộ nhớ, độ trễ và hủy tác vụ quan trọng đều cần một cơ chế có hợp đồng rõ ràng.