# Ảnh hưởng của blocking I/O và chờ điều kiện đến vòng đời Thread trong Java

## Mục tiêu của bài học

Một `Thread` trong Java không nhất thiết đang tính toán mỗi khi nó còn sống. Nó có thể **chờ dữ liệu từ I/O**, **chờ một điều kiện được thỏa mãn**, **chờ lấy monitor lock**, hoặc **ngủ trong một khoảng thời gian**. Những kiểu chờ này tạo ra biểu hiện khác nhau trong `Thread.State`, ảnh hưởng tới thời gian phản hồi, mức sử dụng tài nguyên và khả năng phục vụ tác vụ mới.

Sau bài này, bạn có thể:
- Phân biệt **I/O blocking** với **chờ điều kiện** và với **tranh chấp monitor**.
- Đọc đúng sáu trạng thái Java `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`; giải thích vì sao một thread **đang đợi I/O vẫn có thể hiện `RUNNABLE`**.
- Hiểu vì sao `Object.wait()`/`notifyAll()`, `Condition.await()`/`signalAll()` và `BlockingQueue.take()` cho phép thread chờ công việc mà không cần quay vòng tiêu CPU.
- Nhận ra tác động của chờ dài đối với thread pool, độ dài queue, throughput và tail latency.
- Chạy ví dụ Java 17+ để quan sát thread chờ điều kiện và thread đợi dữ liệu trên stream; biết giới hạn của phép chụp trạng thái bằng `getState()`.
- Chọn timeout, interruption, giới hạn concurrency và các công cụ chẩn đoán phù hợp với từng loại chờ.

**Phạm vi:** cơ chế thread và concurrency của Java/JVM nói chung. Các cơ chế, annotation hay cấu hình asynchronous riêng của Spring thuộc chương khác.

## 1. Một thread sống không có nghĩa là nó luôn thực thi CPU

Giả sử một worker đang xử lý yêu cầu đọc dữ liệu:

~~~text
NEW
 |
 | start()
 v
RUNNABLE ----> gọi read() mà chưa có dữ liệu ----> chờ I/O
   ^                                               |
   |                        dữ liệu đến / I/O xong  |
   +-----------------------------------------------+
   |
   +---- chờ predicate qua wait() ---> WAITING hoặc TIMED_WAITING
   |                                     |
   |        signal/notify/timeout        |
   +-------------------------------------+
   |
   +---- cố lấy monitor bị giữ --------> BLOCKED
   |                                     |
   |         lấy được monitor           |
   +-------------------------------------+
   |
   +---- kết thúc run() ----------------> TERMINATED
~~~

Sơ đồ trên mô tả **nguyên nhân một thread tạm ngừng công việc và cách nó tiếp tục**, không khẳng định chờ I/O là một trạng thái enum riêng. Java không có `Thread.State.IO_BLOCKED`. Ngay cả khi đang đợi thao tác I/O ở hệ điều hành, Java có thể vẫn ghi nhận thread là `RUNNABLE`. Không có trạng thái enum `RUNNING` riêng: `RUNNABLE` bao gồm thread đủ điều kiện được chạy, đang chạy hoặc có thể chờ tài nguyên ngoài JVM tùy tình huống.

**Cần phân biệt hai tầng:**
1. **Trạng thái JVM** do `Thread.getState()` hoặc thread dump báo: một ảnh chụp thô phục vụ giám sát.
2. **Nguyên nhân thực tế của sự chờ**: system call đọc socket, `Object.wait()`, một `Lock`, chờ dữ liệu từ queue, chờ CPU được lập lịch... Nguyên nhân này thường cần kết hợp stack trace, thông tin lock, metric và log để xác định.

Một thread có thể thay đổi trạng thái nhiều lần trong một mili giây. `getState()` chỉ là snapshot ở thời điểm đọc; dùng nó để hiểu hiện tượng, **không** để điều khiển logic phối hợp các thread.

## 2. Sáu trạng thái Thread.State cần nắm

| `Thread.State` | Ý nghĩa trong Java | Ví dụ liên quan |
| --- | --- | --- |
| `NEW` | Tạo đối tượng `Thread` nhưng chưa gọi `start()` | `new Thread(task)` |
| `RUNNABLE` | Thread đủ điều kiện chạy hoặc đang thực thi theo góc nhìn JVM; có thể đang chờ tài nguyên OS | CPU work, một số dạng socket/file I/O blocking |
| `BLOCKED` | Đang **chờ monitor lock** để vào/re-enter `synchronized` | Thread A giữ monitor, B cố vào `synchronized(monitor)` |
| `WAITING` | Chờ một hành động khác, không đặt hạn thời gian | `Object.wait()`, `Thread.join()`, `LockSupport.park()` |
| `TIMED_WAITING` | Chờ trong tối đa một khoảng thời gian | `Thread.sleep(500)`, `Object.wait(500)`, `Thread.join(500)`, `LockSupport.parkNanos(...)` |
| `TERMINATED` | `run()` đã kết thúc bình thường hoặc do exception không được xử lý | Sau khi worker chấm dứt |

Lưu ý quan trọng:

- Tên **`BLOCKED` trong enum Java có nghĩa hẹp**: chờ *monitor* của `synchronized`. “Blocking I/O” trong thuật ngữ lập trình **không tự động tương ứng `Thread.State.BLOCKED`**.
- Chờ `ReentrantLock.lock()` hoặc `Condition.await()` có thể được triển khai bằng parking và được quan sát ở `WAITING`/`TIMED_WAITING`; không tự quy chúng về `BLOCKED` chỉ vì “đang đợi lock”.
- Trạng thái Java là trạng thái của JVM; không phải bản sao trực tiếp trạng thái runnable/sleeping của hệ điều hành.
- Thread chuyển trạng thái do điều kiện thực thi, không phải vì tên hay ID của nó. `notifyAll()` chỉ là tín hiệu, không có nghĩa thread được chạy ngay lập tức.

## 3. Blocking I/O: phải đợi dữ liệu hoặc thiết bị

### 3.1. Blocking xảy ra ở đâu?

Một lời gọi I/O **blocking** chỉ trả về sau khi thao tác có kết quả, đạt EOF, gặp lỗi, bị đóng/hủy theo hợp đồng API hoặc đạt timeout nếu API hỗ trợ. Ví dụ:

~~~java
int firstByte = inputStream.read();
~~~

Nếu `InputStream` chưa có byte nào, `read()` có thể đợi. Bên trong phương thức đọc, thread gọi chưa thể tiếp tục thực thi phần code sau `read()`. Trường hợp khác, lời gọi có thể trả về ngay khi đã có dữ liệu, đã đến EOF hoặc luồng đã bị lỗi; **gọi API blocking không đồng nghĩa lần nào cũng thực sự chờ**.

Ví dụ thực tế:
- Đọc socket TCP bằng stream truyền thống khi dữ liệu chưa tới.
- Chờ nhận kết quả từ thiết bị hoặc file system; mức độ block phụ thuộc API, bộ đệm và hệ điều hành.
- Chờ `accept()` của server socket truyền thống khi chưa có kết nối mới.
- Đọc một pipe chưa có byte từ phía ghi.

**Không nhầm elapsed time với CPU time.** Một lời gọi `read()` kéo dài 700 ms có thể tiêu rất ít CPU trong phần lớn thời gian đó, bởi thread đang chờ dữ liệu. Tuy nhiên nó vẫn chiếm **một công việc đang mở**, có thể giữ socket, bộ nhớ, stack, chỗ trong thread pool hoặc quota của tài nguyên khác.

### 3.2. Tác động lên vòng đời và hiệu năng

Với pool có **4 platform worker threads**, nếu cả bốn đang chờ I/O nhiều giây, một task thứ năm có thể đợi trong queue dù CPU của máy còn rảnh. Quan sát thường gặp:

~~~text
4 workers đều đang chờ remote I/O
             |
             +--> CPU có thể còn thấp
             |
             +--> worker pool bận hết
                        |
                        +--> task mới xếp hàng
                        +--> queue wait tăng
                        +--> end-to-end latency tăng
~~~

Tăng số worker **có thể** giúp chạy đồng thời nhiều công việc chờ I/O hơn, nhưng chỉ đến giới hạn thật: số connection, memory, file descriptor, throughput phía dịch vụ phụ thuộc và mức tải được nhận. Nếu mỗi request chờ downstream mất 2 giây, mở thêm nhiều thread không làm downstream hoàn tất nhanh hơn; còn có nguy cơ tăng backlog và làm hệ thống phụ thuộc quá tải.

Thực tế nên đo:
- Thời gian vào queue và thời gian từ lúc worker bắt đầu đến khi hoàn thành.
- Số tác vụ/worker đang chờ I/O, số kết nối đang dùng và số kết nối còn chờ.
- Timeout, retry, kết quả lỗi, số yêu cầu được nhận và số được xử lý thành công.
- p95/p99 latency; CPU thấp **không** đủ kết luận hệ thống có năng lực dư.

### 3.3. Vì sao getState() có thể vẫn là RUNNABLE?

Với một số thao tác blocking I/O cổ điển, JVM quan sát thread ở `RUNNABLE` vì nó đang ở trong lời gọi native/hệ điều hành; hệ điều hành thực tế có thể đang đợi network hay disk. Những API/triển khai khác có thể dùng monitor hoặc công cụ đồng bộ nội bộ khiến bạn nhìn thấy `WAITING` hoặc `TIMED_WAITING`.

Vì vậy:

~~~java
Thread.State snapshot = readerThread.getState();
System.out.println(snapshot);
~~~

Dòng này cho biết **snapshot Java state**, không đủ bằng chứng để khẳng định reader đang tính toán, đã nhận dữ liệu hoặc đang bị block ở socket. Muốn biết chính xác hơn, cần stack trace, thông tin I/O, metrics và một phép đo trước–sau lời gọi.

**Không suy luận ngược:** thấy `RUNNABLE` không chứng minh CPU bận; thấy `WAITING` không chứng minh nguồn chờ là `Object.wait()` của chính code bạn.

## 4. Chờ điều kiện: đợi một predicate trở thành đúng

Khác với chờ I/O từ nguồn dữ liệu bên ngoài, **condition waiting** xuất hiện khi thread cần một trạng thái phối hợp giữa các thread, ví dụ:

- Buffer vẫn trống → consumer chờ producer thêm phần tử.
- Công việc chưa được đánh dấu hoàn tất → thread khác chờ tín hiệu hoàn thành.
- Chưa đủ tài nguyên/số giấy phép → tác vụ chờ quyền tiếp tục.
- Một cờ `ready` do thread khác cập nhật chưa thành `true`.

Mấu chốt là **predicate của điều kiện**, ví dụ `ready == true` hoặc `!queue.isEmpty()`. Tín hiệu `notify/``signal` chỉ thông báo “có thể điều kiện đã thay đổi”; thread được đánh thức vẫn phải kiểm tra predicate. Không dùng tín hiệu đơn thuần làm nguồn sự thật.

### 4.1. busy-wait so với blocking wait

Cách sai về hiệu năng nếu dùng vòng lặp nóng:

~~~java
while (!ready) {
    // Liên tục kiểm tra điều kiện; có thể tiêu CPU cao.
}
~~~

Vòng lặp như vậy còn có rủi ro **visibility** nếu biến `ready` được cập nhật bởi thread khác nhưng không có quan hệ happens-before (chẳng hạn qua `volatile`, lock hoặc atomic). Thêm `volatile` giúp thấy giá trị, nhưng **không** ngăn vòng lặp nóng dùng CPU. `Thread.yield()` cũng không phải giải pháp phối hợp đáng tin.

Cách có cấu trúc là cho thread **ngủ chờ tín hiệu** bằng `wait()`, `Condition.await()` hoặc primitive cấp cao như `BlockingQueue.take()`, `CountDownLatch.await()`. Những cách này tránh đốt CPU trong khi không có việc làm và đặt ra quy tắc đồng bộ rõ ràng.

### 4.2. Object.wait() giải phóng monitor của chính đối tượng

Mẫu chuẩn:

~~~java
final Object monitor = new Object();
boolean ready = false; // Trong code thực: biến nằm trong object chia sẻ được bảo vệ bởi monitor.

// Thread chờ (minh họa, không phải một chương trình độc lập):
synchronized (monitor) {
    while (!ready) {
        monitor.wait(); // Giải phóng monitor; vào wait set.
    }
    // Khi trở lại đây, thread đã lấy lại monitor và ready == true.
}
~~~

Để thread khác cập nhật `ready`, nó cũng phải vào `synchronized (monitor)` và gọi `monitor.notifyAll()` **trong monitor đó**. `wait()`:
1. Yêu cầu thread hiện tại đang giữ đúng monitor, nếu không ném `IllegalMonitorStateException`.
2. Tạm nhả monitor **của đối tượng gọi `wait()`** trong lúc chờ; không tự nhả các monitor khác thread đang giữ.
3. Có thể kết thúc do `notify`/`notifyAll`, interruption hoặc **spurious wakeup**; `wait()` không timeout mặc định.
4. Trước khi trả về bình thường hoặc ném `InterruptedException`, thread phải lấy lại monitor đó.

**Luôn kiểm tra điều kiện bằng `while`, không dùng `if`**: sau khi được đánh thức, điều kiện có thể vẫn sai vì spurious wakeup hoặc thread khác đã tiêu thụ tài nguyên trước.

Sự kiện `notifyAll()` **không chuyển quyền sở hữu monitor ngay**. Thread phát tín hiệu vẫn giữ monitor cho đến khi rời khối synchronized. Các thread được đánh thức phải cạnh tranh để lấy lại monitor, có thể tạm xuất hiện ở `BLOCKED`.

### 4.3. Chờ có timeout

Các API `wait(long timeoutMillis)` hoặc `Condition.await(long, TimeUnit)` giúp đặt giới hạn. Với `Object.wait(0)`, giá trị 0 nghĩa là **chờ không thời hạn**, không phải trả về ngay.

Khi timeout, chỉ có nghĩa “đã hết thời gian chờ theo hợp đồng API”; **không** có nghĩa predicate đã thành đúng. Ví dụ ý tưởng:

~~~java
long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(2);
synchronized (monitor) {
    while (!ready) {
        long remainingNanos = deadline - System.nanoTime();
        if (remainingNanos <= 0) {
            throw new java.util.concurrent.TimeoutException("ready timeout");
        }
        java.util.concurrent.TimeUnit.NANOSECONDS.timedWait(monitor, remainingNanos);
    }
}
~~~

Đây là **đoạn mã minh họa**, giả định `monitor` và `ready` cùng tồn tại trong phạm vi hợp lệ; khi dùng trong method cần khai báo/xử lý `InterruptedException` và `TimeoutException`. `timedWait` ở đây là phương thức tiện ích của `TimeUnit`, vẫn dựa vào monitor wait. Sử dụng đồng hồ `System.nanoTime()` cho khoảng thời gian, không dùng đồng hồ lịch để tính deadline nội bộ. Trong code production, xử lý deadline cộng số lớn cần cân nhắc overflow, và có thể ưu tiên primitive concurrency có timeout sẵn.

## 5. Phân biệt wait(), sleep(), join(), BLOCKED và Condition.await()

| Tình huống | Tài nguyên/tín hiệu đang chờ | Java state thường thấy | Có giải phóng monitor/lock? |
| --- | --- | --- | --- |
| `Thread.sleep(500)` | Đồng hồ trôi qua | `TIMED_WAITING` | **Không tự nhả** monitor đang giữ |
| `Object.wait()` | Notify/interrupt/spurious wakeup | `WAITING` | Nhả monitor của object dùng `wait()` và lấy lại trước khi trở về |
| `Object.wait(500)` | Tín hiệu hoặc timeout | `TIMED_WAITING` | Nhả monitor tương ứng |
| Cố vào `synchronized` đang bị thread khác giữ | Monitor lock | `BLOCKED` | Chưa lấy được monitor đó |
| `Thread.join()` | Thread mục tiêu kết thúc | `WAITING` | Không có quy tắc “nhả mọi lock” |
| `Thread.join(500)` | Thread mục tiêu kết thúc hoặc timeout | `TIMED_WAITING` | Không có quy tắc “nhả mọi lock” |
| `Condition.await()` với `ReentrantLock` | `signal`/`signalAll`/interrupt/spurious wakeup | Thường `WAITING` | Nhả **lock gắn với Condition**, lấy lại trước khi trở về |
| `BlockingQueue.take()` trên queue trống | Có phần tử mới | Thường `WAITING` | Primitive tự quản lý khóa/điều kiện bên trong |
| I/O blocking đọc socket | Dữ liệu/EOF/lỗi/timeout | Phụ thuộc API và JVM; có thể `RUNNABLE` | **Không tự nhả** những monitor hoặc `Lock` ngoài lời gọi I/O |

Hai lỗi phổ biến:

**Lỗi A — giữ monitor trong khi ngủ**

~~~java
synchronized (monitor) {
    Thread.sleep(1000);
}
~~~

Trong giây đó, thread vẫn giữ monitor. Thread khác cần vào `synchronized(monitor)` phải đợi `BLOCKED`. `sleep()` chỉ tạm ngừng chạy; nó không phải cơ chế chờ predicate và không giải phóng monitor.

**Lỗi B — giữ lock trong khi gọi I/O rất chậm**

~~~java
synchronized (monitor) {
    byte[] data = inputStream.readNBytes(1024);
    // Nếu nguồn dữ liệu chậm, các thread khác có thể mắc kẹt
    // khi chờ cùng monitor, dù CPU không bận.
}
~~~

Đoạn trên chỉ minh họa tác động giữ lock; để dùng cần biến `inputStream` được khai báo và xử lý `IOException`. Nên giới hạn critical section tới cập nhật trạng thái dùng chung, tránh đưa thao tác I/O có thời gian khó dự đoán vào vùng khóa khi không thực sự cần.

## 6. Ví dụ Java 17+: thread chờ điều kiện rồi được đánh thức

Chương trình này minh họa bốn mốc: thread đã khởi chạy, đi vào `wait()` khi `ready=false`, được thread khác `notifyAll()`, và kết thúc. Biến `ready` chỉ được đọc/ghi khi giữ cùng monitor để bảo đảm tính đúng đắn và visibility.

Tạo tệp **`ConditionLifecycleDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class ConditionLifecycleDemo {
    private static final Object MONITOR = new Object();
    private static boolean ready;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (MONITOR) {
                entered.countDown();

                while (!ready) {
                    try {
                        MONITOR.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        System.out.println("worker-interrupted");
                        return;
                    }
                }
            }
            System.out.println("worker-finished");
        }, "condition-worker");

        System.out.println("before-start=" + worker.getState());
        worker.start();
        entered.await(); // Chắc chắn worker đã vào synchronized ít nhất một lần.

        // Snapshot: có thể là RUNNABLE hoặc WAITING tùy thời điểm.
        System.out.println("during-wait=" + worker.getState());

        synchronized (MONITOR) {
            ready = true;
            MONITOR.notifyAll();
        }

        worker.join(); // Đợi worker hoàn thành.
        System.out.println("after-join=" + worker.getState());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ConditionLifecycleDemo.java
java ConditionLifecycleDemo
~~~

Một đầu ra **có thể** quan sát:

~~~text
before-start=NEW
during-wait=WAITING
worker-finished
after-join=TERMINATED
~~~

**`during-wait` không được cam kết luôn là `WAITING`**: ngay sau `entered.countDown()`, worker vẫn có thể chưa gọi `wait()`. Nếu main lấy `MONITOR` trước, worker có thể chưa chờ, rồi sau đó nhìn thấy `ready=true` và bỏ qua `wait()`. Trên những lượt khác, snapshot có thể là `RUNNABLE`, `BLOCKED` hoặc trạng thái phù hợp với lịch chạy. Điểm đáng tin là `before-start=NEW`, việc cuối cùng in `worker-finished` (khi không bị ngắt), rồi `after-join=TERMINATED`.

Tại sao chương trình không bị “lost notification”?
- `ready` được kiểm tra **dưới cùng monitor** với thao tác cập nhật/`notifyAll()`.
- Nếu main đặt `ready=true` trước khi worker kịp `wait()`, worker sẽ thấy predicate đúng và **không chờ**. Không phụ thuộc vào việc có “ghi nhớ” tín hiệu notify hay không.
- Nếu worker đã `wait()`, thao tác wait nhả monitor và main có thể vào để thay đổi predicate rồi phát tín hiệu.
- `while` bảo vệ khỏi wakeup giả hoặc thay đổi predicate trong chương trình phức tạp hơn.

Lưu ý `CountDownLatch` trong demo chỉ điều phối điểm quan sát `entered.await()`; nó **không bảo đảm** worker đã chuyển vào WAITING. Nếu cần viết test về trạng thái, hãy dùng công cụ đồng bộ chủ động và timeout; đừng kiểm tra một `getState()` duy nhất như một assertion chắc chắn.

## 7. Ví dụ Java 17+: một reader chờ dữ liệu I/O

Để quan sát blocking I/O mà không cần server/mạng bên ngoài, dùng một cặp `PipedInputStream` / `PipedOutputStream`. Reader gọi `read()` khi chưa có byte nào; writer ở thread main gửi ký tự `A` sau một khoảng chờ.

Đây là **một pipe trong bộ nhớ của Java**, thích hợp cho thí nghiệm, không đại diện chính xác cho mọi loại socket hoặc native file I/O. Phần `Thread.State` quan sát được phụ thuộc cách `PipedInputStream` triển khai chờ.

Tạo file **`BlockingIoLifecycleDemo.java`**:

~~~java
import java.io.IOException;
import java.io.PipedInputStream;
import java.io.PipedOutputStream;
import java.util.concurrent.CountDownLatch;

public class BlockingIoLifecycleDemo {
    public static void main(String[] args) throws Exception {
        try (PipedInputStream input = new PipedInputStream();
             PipedOutputStream output = new PipedOutputStream(input)) {

            CountDownLatch startingRead = new CountDownLatch(1);
            Thread reader = new Thread(() -> {
                try {
                    startingRead.countDown();
                    int value = input.read(); // Có thể chờ cho tới khi có byte.
                    System.out.println("received=" + (char) value);
                } catch (IOException e) {
                    System.out.println("io-error=" + e.getClass().getSimpleName());
                }
            }, "pipe-reader");

            reader.start();
            startingRead.await();

            Thread.sleep(100); // Chỉ tạo khoảng trống để quan sát.
            System.out.println("while-reading=" + reader.getState());

            output.write('A');
            output.flush();

            reader.join();
            System.out.println("after-join=" + reader.getState());
        }
    }
}
~~~

Chạy:

~~~bash
javac BlockingIoLifecycleDemo.java
java BlockingIoLifecycleDemo
~~~

Trên lượt chạy bình thường, ví dụ đầu ra:

~~~text
while-reading=TIMED_WAITING
received=A
after-join=TERMINATED
~~~

Chỉ hai dòng **`received=A`** và **`after-join=TERMINATED`** được kỳ vọng ổn định khi I/O thành công và thread đã hoàn thành. **`while-reading` là snapshot, không có giá trị cố định**: có thể là `TIMED_WAITING`, `WAITING`, `RUNNABLE` hoặc trạng thái khác hợp lệ theo thời điểm/implementation. Nếu stream lỗi, nhánh `io-error=...` sẽ xuất hiện thay cho dữ liệu thành công.

Quan sát quan trọng: điều kiện để reader tiến lên là **có byte từ phía writer**, chứ không phải việc main đánh thức monitor của reader bằng `notifyAll()`. Cũng không nên gọi `reader.interrupt()` rồi mặc định mọi `InputStream.read()` sẽ thoát ngay: hỗ trợ interruption khác nhau theo API và đường I/O.

Trong ví dụ, main gọi `reader.join()` để đợi kết quả; thao tác `join()` là **một kiểu chờ khác** của main thread, không làm reader tự chuyển sang RUNNABLE.

## 8. Condition.await() và các primitive thay cho wait/notify thủ công

`Object.wait()/notifyAll()` giúp hiểu cơ chế monitor, nhưng trong code nghiệp vụ, primitive concurrency cấp cao thường đơn giản và ít lỗi hơn.

### 8.1. ReentrantLock + Condition

Với `java.util.concurrent.locks.ReentrantLock`, điều kiện gắn với lock được tạo bởi `newCondition()`:

~~~java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

// Đoạn minh họa trong một class có trạng thái chia sẻ:
private final ReentrantLock lock = new ReentrantLock();
private final Condition canProceed = lock.newCondition();
private boolean ready = false;

public void awaitReady() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (!ready) {
            canProceed.await(); // Nhả lock; chờ; lấy lại lock trước khi trả về.
        }
    } finally {
        lock.unlock();
    }
}

public void markReady() {
    lock.lock();
    try {
        ready = true;
        canProceed.signalAll();
    } finally {
        lock.unlock();
    }
}
~~~

Đây là **đoạn thành viên class**, không phải chương trình độc lập. Khi ghép vào class hợp lệ, các method minh họa sự khác nhau của `await` và `signalAll` với `wait` và `notifyAll`:
- `Condition.await()` phải được gọi khi thread giữ **lock tương ứng**. Nó nhả lock khi chờ và lấy lại trước khi trả về.
- `signalAll()` không mang predicate; thread được đánh thức vẫn kiểm tra lại `ready` trong `while`.
- Luôn `unlock()` trong `finally`; khi interruption xảy ra trong `await()`, phép thu hồi lock được xử lý theo hợp đồng `Condition` trước khi unwinding.
- `lockInterruptibly()` có thể bị gián đoạn trong lúc đợi lấy lock. `lock()` có semantics khác, vì thế cần chọn theo yêu cầu hủy tác vụ.

### 8.2. BlockingQueue.take() diễn đạt điều kiện “có phần tử”

Nếu nhu cầu thật sự là **consumer chờ producer đưa công việc**, `BlockingQueue` giúp bỏ thao tác `wait/notify` thủ công:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

public class QueueWaitDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();

        Thread consumer = new Thread(() -> {
            try {
                String value = queue.take(); // Đợi cho đến khi có phần tử.
                System.out.println("consumed=" + value);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("consumer-interrupted");
            }
        }, "consumer");

        consumer.start();
        queue.put("work");
        consumer.join();
    }
}
~~~

Lưu file **`QueueWaitDemo.java`**, chạy:

~~~bash
javac QueueWaitDemo.java
java QueueWaitDemo
~~~

Khi không có interruption:

~~~text
consumed=work
~~~

Nếu main `put` trước khi consumer `take`, consumer lấy phần tử ngay và **không cần vào WAITING**. Nếu consumer `take` trước khi có phần tử, nó chờ theo cơ chế nội bộ của queue. Trong cả hai trường hợp chương trình vẫn đúng: **dữ liệu trong queue là trạng thái cần thiết**, không phụ thuộc vào một tín hiệu bị bỏ lỡ.

Với `LinkedBlockingQueue<>()` không truyền capacity, mặc định capacity lớn (tối đa `Integer.MAX_VALUE`); trong hệ thống nhận tải thực, nên cân nhắc queue hữu hạn, timeout và chính sách từ chối phù hợp thay vì tích backlog không giới hạn theo mục đích thiết kế.

### 8.3. CountDownLatch và join có mục đích khác

- `CountDownLatch.await()`: chờ một bộ đếm về 0; dùng cho tín hiệu một lần, sau khi về 0 thì không reset.
- `Thread.join()`: chờ **thread mục tiêu kết thúc**; không phải chờ dữ liệu mạng và không có ý nghĩa rằng “tác vụ logic” đã hoàn thành nếu nó tiếp tục ở worker khác.
- `Future.get()`: chờ kết quả của task hoặc nhận exception; có biến thể có timeout.
- `Semaphore.acquire()`: chờ giấy phép; thích hợp giới hạn số tác vụ cùng dùng tài nguyên khan hiếm.

Dùng primitive phù hợp sẽ khiến intent rõ hơn và giảm nguy cơ deadlock, missed signal và race condition.

## 9. Interrupt, timeout, đóng tài nguyên và cancellation

Một thread có thể chờ vô hạn nếu nguồn dữ liệu, điều kiện hoặc tín hiệu hoàn thành không bao giờ đến. Vì thế, thiết kế concurrency phải trả lời: **khi nào ngừng chờ và ai chịu trách nhiệm giải phóng tài nguyên?**

### 9.1. Interruption là yêu cầu hợp tác, không phải dừng cưỡng bức

`Thread.interrupt()` đặt interrupt status và có hành vi riêng cho một số thao tác chờ.

Ví dụ đối với `Object.wait()`, `Thread.sleep()`, `Thread.join()` và nhiều primitive `java.util.concurrent`, interrupt có thể làm ném `InterruptedException`, đồng thời cờ interrupt bị xóa khi exception được phát sinh. Mẫu xử lý khi code không thể ném tiếp exception:

~~~java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Khôi phục cờ cho lớp gọi ngoài.
    return;
}
~~~

Đây là **đoạn minh họa** nằm trong method nhận biết biến `queue`. Nếu API của bạn có thể khai báo `throws InterruptedException`, thường nên để exception truyền lên thay vì nuốt. Không tiếp tục vòng lặp chờ vô hạn sau khi bắt và bỏ qua interrupt nếu task cần khả năng hủy.

**Với I/O: quy tắc khác nhau theo API.** Ví dụ thao tác đang block trên `InterruptibleChannel` có thể khiến channel đóng và ném `ClosedByInterruptException`; `Selector` có xử lý interrupt riêng. Không có bảo đảm chung rằng `interrupt()` sẽ ngắt mọi `InputStream.read()` hoặc mọi native call trong Java 17. Hãy dùng timeout của đúng API, cancellation và/hoặc đóng tài nguyên theo hợp đồng được tài liệu hóa. Cẩn thận để thread vẫn có đường thoát trong khi ứng dụng shutdown.

### 9.2. Timeout phải có ranh giới và hậu quả rõ ràng

Ví dụ khi chờ queue, thay `take()` bằng `poll(2, TimeUnit.SECONDS)`: nếu hết hạn, kết quả `null` nghĩa là **không lấy được phần tử trước deadline**, không phải queue đã hỏng. Với socket truyền thống, có thể cấu hình read timeout bằng API tương ứng (`Socket#setSoTimeout`); timeout đọc khác với timeout kết nối và không thay thế deadline đầu-cuối của yêu cầu.

Một chính sách hoàn chỉnh cần phân biệt:
- **Timeout**: thời gian chờ tối đa cho một operation.
- **Cancellation**: người dùng/hệ thống yêu cầu không làm tiếp công việc.
- **Backpressure/admission control**: giảm tải được nhận khi tài nguyên/hàng đợi đầy.
- **Resource cleanup**: đóng stream/socket, trả connection, nhả lock trong `finally` hoặc try-with-resources.

Nếu chỉ tăng timeout nhưng không giải quyết nguồn chờ, số task bị giữ lại có thể tăng và làm các request sau chậm hơn.

## 10. Bài toán thread pool và virtual threads

### 10.1. Platform threads là tài nguyên hữu hạn

Một platform thread thường tương ứng với một thread của hệ điều hành. Trong mô hình **thread-per-request**, nếu mỗi request chủ yếu block ở I/O, số thread cần để giữ nhiều request đồng thời có thể lớn dù CPU còn rảnh. Điều này gây:
- Chi phí stack, scheduling và thread management.
- Queue chờ worker rảnh trong `ExecutorService` hữu hạn.
- Gia tăng connection, open files và áp lực lên dịch vụ phụ thuộc.

Tác vụ chờ I/O có thể hưởng lợi từ concurrency cao hơn so với tác vụ CPU-bound, nhưng giới hạn hợp lý phụ thuộc **tài nguyên thực tế và SLO**. Cần đo latency, successful throughput, số request chờ, lỗi và pool utilization, không chọn thread count chỉ từ số core.

### 10.2. Virtual threads (Java 21+) thay đổi chi phí của việc chờ

Virtual threads là một cơ chế thread nhẹ hơn cho workload có nhiều tác vụ độc lập chờ I/O. Với những hoạt động blocking được JVM hỗ trợ, virtual thread có thể **nhường carrier platform thread** trong thời gian chờ, cho phép carrier phục vụ virtual thread khác. Điều này giúp các mô hình có nhiều tác vụ chờ thuận tiện hơn.

Nhưng cần nhớ:
- Virtual threads **không tăng số CPU core** và không làm remote service trả lời nhanh hơn.
- Chúng vẫn tiêu memory, file descriptor, connection và capacity của tài nguyên phụ thuộc.
- Không suy ra trạng thái chính xác của carrier từ `Thread.currentThread().getState()` của virtual thread.
- Một số blocking hoặc native/foreign operations, cơ chế đồng bộ và hành vi pinning phụ thuộc phiên bản JDK cụ thể; cần dùng tài liệu/quan sát đúng JDK khi phân tích vấn đề này.
- `Thread.State` và các API `wait/interrupt` vẫn phải được hiểu theo hợp đồng Java; virtual thread không biến chờ không có timeout thành an toàn vô điều kiện.

Các ví dụ chạy được trong bài dùng Java 17 và platform threads để cô lập nguyên nhân chờ. Phần virtual threads chỉ cung cấp bối cảnh Java 21+ chứ không yêu cầu dùng API mới để chạy demo.

## 11. Chẩn đoán “thread bị kẹt” bằng thông tin nào?

### 11.1. Đọc stack và Java state cùng nhau

Dùng `Thread.getState()` để nhìn trạng thái hiện tại, kết hợp `Thread.getStackTrace()` hoặc thread dump (ví dụ `jcmd <pid> Thread.print` trên JDK hỗ trợ). Đối với CPU, lock và thread hoạt động trong Java process, có thể dùng Java Flight Recorder (JFR), Java Mission Control (JMC) hoặc `ThreadMXBean` nếu hỗ trợ các phép đo liên quan.

| Dấu hiệu | Có thể đang xảy ra | Cần kiểm chứng tiếp |
| --- | --- | --- |
| Thread dump có `BLOCKED`, stack tại `synchronized` | Cạnh tranh monitor | Ai giữ monitor, giữ trong bao lâu, có lock-order cycle không |
| `WAITING` ở `Object.wait()` hoặc `Condition.await()` | Đang đợi predicate/tín hiệu | Predicate được cập nhật ở đâu, ai signal, có đường timeout/hủy không |
| `TIMED_WAITING` ở `Thread.sleep` | Đang ngủ theo thời gian | Có đang giữ lock, sleep có thay thế waiting logic một cách sai lầm không |
| `RUNNABLE` với stack trong `SocketInputStream.read` hoặc native read | Có thể đang đợi I/O | Remote latency, socket timeout, connection count, log trước/sau read |
| Nhiều pool workers active, CPU thấp, queue dài | Nhiều worker có thể đang chờ I/O/lock | Đo wait duration, queue size, pool metrics và downstream |
| `TERMINATED` nhưng task nghiệp vụ chưa có kết quả cuối | Đường xử lý có thể đã chuyển sang thread khác hoặc thất bại | Correlation ID, Future/status của task, luồng dữ liệu |

**Không kết luận deadlock chỉ vì thread ở `WAITING` lâu.** Một consumer không có công việc có thể chờ hoàn toàn hợp lệ. Deadlock cần bằng chứng có chu trình phụ thuộc khóa/tài nguyên khiến các bên không thể tiến triển; `ThreadMXBean.findDeadlockedThreads()` có thể giúp phát hiện một số trường hợp, nhưng không thay thế phân tích nguyên nhân chờ I/O hay dependency bên ngoài.

### 11.2. Đo thời gian ở đúng ranh giới

Đo các quãng riêng biệt bằng `System.nanoTime()`:

~~~text
submit/enqueue ---- queue wait ---- start worker
                                         |
                                         +-- waiting for lock
                                         +-- blocking I/O
                                         +-- condition wait
                                         +-- CPU work
                                         |
                                       complete
~~~

**Task latency = queue wait + elapsed time trong worker**, còn **CPU time** chỉ tính thời gian CPU thực sự được sử dụng. Nếu một worker chờ I/O 1 giây rồi xử lý CPU 5 ms, elapsed khoảng 1 giây không có nghĩa CPU đã chạy 1 giây.

Dùng histogram/p95/p99 và các chỉ số đối ứng (timeout/rejection/connection/CPU). Thread state snapshot cho biết **đang ở trạng thái nào lúc lấy mẫu**; số đo thời gian mới cho biết **chờ bao lâu**.

## 12. Những lỗi thường gặp và cách khắc phục

1. **Thấy `RUNNABLE` rồi khẳng định thread đang tiêu CPU.** Có thể thread đang ở native/blocking I/O hoặc chờ lập lịch. Cần kết hợp stack, CPU time và I/O metrics.
2. **Gọi mọi kiểu chờ là `BLOCKED`.** Trong `Thread.State`, `BLOCKED` là chờ monitor; `WAITING` và `TIMED_WAITING` có nghĩa khác.
3. **Dùng `Thread.sleep()` để “đợi khi có dữ liệu”.** Sleep không gắn với predicate hoặc tín hiệu, có thể trễ vô ích hoặc polling liên tục. Ưu tiên primitive concurrency có điều kiện.
4. **Gọi `wait()` bên ngoài `synchronized`.** Có thể bị `IllegalMonitorStateException`. Phải giữ đúng monitor.
5. **Dùng `if` thay cho `while` quanh `wait/await`.** Không chống được spurious wakeup hoặc cạnh tranh điều kiện sau khi được đánh thức.
6. **Chỉ gọi `notify()` để sửa mọi lỗi không tiến triển.** Tín hiệu không thay predicate; cũng có thể đánh thức sai waiter nếu nhiều điều kiện chung monitor. Dùng predicate đúng và `notifyAll()`/`signalAll()` khi thích hợp, hoặc abstraction cấp cao.
7. **Nghĩ `notifyAll()` khiến thread chạy ngay.** Waiter còn cần lấy lại monitor/lock; thứ tự đánh thức không chứng minh thứ tự chạy.
8. **Giữ lock trong lúc I/O chậm.** Một thread chờ network vẫn có thể giữ monitor, làm thread khác chuyển thành `BLOCKED`.
9. **Nuốt `InterruptedException` và tiếp tục vòng lặp.** Có thể làm cancellation/shutdown bị kẹt. Truyền exception lên hoặc khôi phục interrupt status và thoát đúng đường.
10. **Tăng vô hạn số worker để giải quyết I/O chậm.** Có thể chuyển bottleneck sang connection, database, memory, file descriptor hoặc downstream; phải đo và giới hạn concurrent work.
11. **Không đặt timeout cho chờ phụ thuộc bên ngoài.** Một request lỗi có thể giữ tài nguyên vô hạn. Cần timeout và cleanup theo đúng API.
12. **Kiểm tra `getState() == WAITING` để quyết định có gọi notify không.** Snapshot có race và không thể thay thế predicate dưới cùng cơ chế đồng bộ.
13. **Cho rằng virtual threads xóa mọi giới hạn.** Chúng giảm chi phí thread trong nhiều tình huống chờ, nhưng không xóa giới hạn tài nguyên hoặc yêu cầu timeout/cancellation.

## 13. Câu hỏi tự kiểm tra

1. Một thread đang chờ byte qua socket và `getState() == RUNNABLE`. Điều đó có chứng minh nó đang chạy CPU không? **Không.** Java state có thể không thể hiện chi tiết chờ I/O ở OS.
2. Một thread cố vào `synchronized(lock)` khi thread khác đang giữ monitor. Java state có thể là gì? **`BLOCKED`.**
3. Tại sao `Object.wait()` cho phép producer vào cùng monitor còn `Thread.sleep()` trong `synchronized` thì không? **`wait()` nhả monitor liên quan; `sleep()` không nhả monitor.**
4. Tại sao phải viết `while (!ready) monitor.wait()` thay vì `if`? **Predicate có thể vẫn sai do spurious wakeup hoặc thread khác thay đổi tình trạng trước khi waiter lấy lại monitor.**
5. `notifyAll()` có bảo đảm waiter bắt đầu chạy ngay không? **Không.** Waiter còn phải cạnh tranh lấy lại monitor.
6. Pool bốn worker đều đợi database 2 giây, CPU tiến trình chỉ 10%, queue đang tăng. Vì sao? **Worker slot đã bị chiếm bởi task đang chờ; CPU thấp không đồng nghĩa worker còn rảnh.**
7. `interrupt()` có bảo đảm ngắt mọi lời gọi I/O trong Java 17 không? **Không.** Hợp đồng tùy loại stream/channel; cần timeout/cancellation/close phù hợp.
8. Khi quan sát trạng thái `WAITING` trong `BlockingQueue.take()`, đó có phải dấu hiệu deadlock? **Chưa chắc.** Queue trống và consumer chờ dữ liệu là tình trạng bình thường.
9. Virtual threads giúp vấn đề nào và không giúp điều gì? **Giảm chi phí giữ nhiều tác vụ đồng thời đang chờ ở các blocking operations được hỗ trợ; không tăng CPU hay tốc độ nguồn dữ liệu.**

## Kết luận

**Blocking I/O** làm tiến trình thực thi của một công việc phải đợi dữ liệu hoặc tài nguyên bên ngoài; **condition waiting** làm thread đợi một predicate do các thread phối hợp thay đổi. Cả hai đều có thể ngăn task hoàn tất dù CPU rảnh. Tuy vậy, **`Thread.State.BLOCKED` chỉ nói về chờ monitor lock**, trong khi I/O có thể quan sát là `RUNNABLE` và condition waiting thường xuất hiện là `WAITING` hoặc `TIMED_WAITING`.

Khi thiết kế Java concurrency, hãy biểu diễn điều kiện bằng predicate và primitive phù hợp, tránh giữ lock lúc chờ I/O, có timeout/cancellation/cleanup, và đo cả queue wait lẫn thời gian chờ thực tế. **Không dùng snapshot `getState()` làm cơ chế đồng bộ hoặc làm kết luận duy nhất về hiệu năng.**

### Tham khảo Java API

- [Java SE 17 — Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): định nghĩa sáu trạng thái và giới hạn khi suy ra OS state.
- [Java SE 17 — Object.wait/notify](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): nhả monitor, reacquire, interruption và spurious wakeup.
- [Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `sleep()`, `join()`, `interrupt()`.
- [Java SE 17 — Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): `await`, `signal` và quy tắc lock.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `take`, `poll`, `put`.
- [Java SE 17 — PipedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PipedInputStream.html): đọc pipe khi chưa có byte.
