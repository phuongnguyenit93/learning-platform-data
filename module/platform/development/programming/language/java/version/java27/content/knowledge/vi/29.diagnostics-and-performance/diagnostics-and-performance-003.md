# `jcmd`, thread dump và phân tích tác vụ bị chặn trong Java 27

Trong chương **Chẩn đoán và hiệu năng**, một ứng dụng Java có thể vẫn đang chạy, CPU không cao, heap chưa đầy, nhưng API trả lời rất chậm hoặc hoàn toàn không trả lời. Nguyên nhân có thể là **tranh chấp khóa**, **deadlock**, task chờ connection pool, executor không có worker rảnh, network I/O bị kéo dài hoặc một vòng lặp CPU không kết thúc.

Java 27 cung cấp các công cụ chẩn đoán được hỗ trợ để thu thập bằng chứng từ JVM đang chạy, đặc biệt là **`jcmd`** và **thread dump**. Một thread dump cho biết các thread đang làm gì tại thời điểm quan sát, call stack nào đang chạy hoặc chờ, cùng một số thông tin về monitor và synchronizer. Nó hữu ích để **khoanh vùng nguyên nhân**, nhưng **không tự giải thích toàn bộ ứng dụng**.

Bài học tập trung vào cách dùng `jcmd` và thread dump trên **HotSpot/OpenJDK Java 27**, bao gồm **platform thread** lẫn **virtual thread**. Mục tiêu là phân biệt trạng thái `BLOCKED`, `WAITING`, `TIMED_WAITING` và `RUNNABLE`; tìm quan hệ **người chờ — tài nguyên — chủ sở hữu**; điều tra các nút thắt ở executor/JDBC/I/O; sau đó xác minh bằng nhiều snapshot, Java Flight Recorder (JFR) và metrics.

> **Nguyên tắc điều tra:** thu thập bằng chứng trước khi thay đổi cấu hình, dùng công cụ theo đúng quyền vận hành, tránh những hướng dẫn cũ chỉ dựa vào `jstack` hoặc coi mọi thread `WAITING` là lỗi. Trong Java 27, các công cụ chẩn đoán virtual thread có phạm vi quan sát khác với thread dump truyền thống.

## 1. Tình huống nào cần thread dump?

Một thread dump đặc biệt hữu ích khi ứng dụng:

- Không hoàn tất request dù process vẫn tồn tại.
- Có độ trễ p95/p99 tăng nhưng CPU hoặc heap chưa giải thích được.
- Ghi log “waiting for connection”, “task timed out” hoặc “thread pool exhausted”.
- Có quá nhiều thread đang chờ cùng một khóa hoặc cùng một tài nguyên.
- Dừng ở giai đoạn shutdown vì tác vụ hoặc executor không kết thúc.
- Tiêu thụ CPU cao do một hay nhiều thread chạy vòng lặp.
- Chạy nhiều virtual threads và nghi chúng đang chờ tài nguyên hoặc scheduler không kịp phục vụ.

**Đừng chỉ nhìn một chỉ số rồi kết luận.** Ví dụ CPU thấp cùng với số request đang chờ tăng có thể xuất hiện khi nhiều task đang đợi database; CPU cao có thể là tính toán hợp lệ, GC hoặc một loop sai; còn `WAITING` có thể là trạng thái bình thường của worker nhàn rỗi.

### 1.1. Bộ ba bằng chứng nền tảng

```text
                Triệu chứng ứng dụng
              latency / timeout / errors
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
     Thread dumps   JVM/JFR data   Resource metrics
     stack + locks   timeline       DB pool, queue,
                                   network, CPU, GC
          |             |             |
          +-------------+-------------+
                        v
               Giả thuyết nguyên nhân
                        |
                        v
               Tái hiện và xác minh
```

Thread dump trả lời **đang chờ ở đâu**; metrics và tracing trả lời **chờ bao lâu, bao nhiêu yêu cầu bị ảnh hưởng, tài nguyên nào đã cạn**. Hai lớp thông tin bổ sung nhau.

## 2. `jcmd` là gì và dùng như thế nào?

`jcmd` là công cụ đi kèm JDK, gửi **diagnostic command** tới JVM đang chạy. Nó có thể in thread stack, thu JFR recording, xem các thông số JVM, trạng thái compiler hoặc một số thông tin GC.

Cú pháp cơ bản:

```text
jcmd -l
jcmd <pid> help
jcmd <pid> help Thread.print
jcmd <pid> help Thread.dump_to_file
```

Trong đó `<pid>` là process ID của **JVM đích**, không phải PID của một thread. Nếu có nhiều Java processes, cần nhận diện đúng ứng dụng và môi trường trước khi attach.

**Điều kiện vận hành quan trọng:**

1. Công cụ phải được chạy ở nơi có thể truy cập JVM đích; thông thường cùng máy và quyền user/group phù hợp.
2. Trong container, PID namespace có thể làm `jcmd -l` không hiển thị process mong muốn; phải xác định PID từ đúng namespace/container.
3. Attach mechanism có thể bị vô hiệu hóa hoặc bị chính sách bảo mật chặn.
4. Tên và tùy chọn diagnostic command phụ thuộc JVM/version. Dùng `jcmd <pid> help` trên JVM **đang chạy**, không chỉ tin tài liệu của JDK khác.
5. Output có thể chứa class name, đường dẫn, tên thread hoặc dữ liệu nhạy cảm. Chỉ gửi cho người có quyền và lưu với thời hạn thích hợp.

Không chạy lệnh trên mọi JVM bằng PID `0` chỉ để “tìm thử”; hãy chọn process cụ thể, đặc biệt trong môi trường chia sẻ.

### 2.1. Tìm process đúng

```text
jcmd -l
```

Ví dụ output mang tính minh họa:

```text
18452 com.example.orders.Main
18703 org.example.BatchRunner
```

Chọn đúng PID của service cần điều tra. Nếu process được chạy bên trong container, một shell bên ngoài container có thể không nhận diện nó theo cùng PID; nên dùng công cụ quản lý container hoặc attach trong namespace phù hợp.

### 2.2. Kiểm tra command trước khi thu dump

```text
jcmd 18452 help Thread.print
jcmd 18452 help Thread.dump_to_file
```

Đây là cách kiểm tra nhanh những option mà JVM đích hỗ trợ. Trên một số JDK vendor khác HotSpot, command set có thể khác.

## 3. Hai loại thread dump quan trọng trong Java 27

Trên Java 27, cần phân biệt:

1. **`Thread.print`**: HotSpot VM thread dump truyền thống, hữu ích cho platform threads và các virtual threads **đang mounted**.
2. **`Thread.dump_to_file`**: thread dump đơn giản, có thể xuất text/JSON và liệt kê **platform lẫn virtual threads**, kể cả những virtual threads không được thể hiện đầy đủ trong `Thread.print`.

| Đặc điểm | `Thread.print` | `Thread.dump_to_file` |
| --- | --- | --- |
| Đầu ra | Console của `jcmd` | File plain text hoặc JSON |
| Platform threads | Có | Có |
| Virtual threads | Các virtual threads đang mounted | Cả virtual threads; phù hợp cho workload lớn |
| Monitor/lock detail | Có thông tin stack và lock, hỗ trợ `-l` | Có thread state và thông tin lock theo định dạng mới |
| Deadlock detection | Thread dump truyền thống có thể phục vụ phát hiện deadlock platform threads | **Không tự chạy deadlock detection** |
| Tính nhất quán | HotSpot VM dump kiểu snapshot truyền thống | **Không phải snapshot đồng nhất**; có timestamp theo thread |
| Thông tin VM/OS chi tiết | Phong phú hơn, có thể có native/VM details | Không chứa tất cả object address/JNI/heap details của dump truyền thống |
| Kích thước output | Phụ thuộc số thread được in | Có thể rất lớn khi có nhiều virtual threads |

**Không dùng `Thread.print` làm bằng chứng “chỉ có từng này virtual thread”.** Những virtual thread đang unmounted và chờ I/O có thể không hiện diện như trong `Thread.dump_to_file`.

### 3.1. Lấy dump truyền thống

```text
jcmd <pid> Thread.print -l
```

`-l` yêu cầu in thêm thông tin về `java.util.concurrent` locks/ownable synchronizers khi JVM hỗ trợ. Có thể dùng `-e` cho extended thread information:

```text
jcmd <pid> Thread.print -e -l
```

Chạy lệnh trong quá trình service có sự cố; đầu ra thường khá dài. Có thể lưu lại qua cơ chế redirect của shell đang vận hành, nhưng không ghi đè một file chẩn đoán trước đó mà chưa chủ ý.

### 3.2. Lấy dump toàn bộ thread, gồm virtual threads

```text
jcmd <pid> Thread.dump_to_file -format=json threads-01.json
```

Có thể dùng định dạng plain text mặc định bằng cách **bỏ** tùy chọn format:

```text
jcmd <pid> Thread.dump_to_file threads-01.txt
```

Theo **trang man `jcmd` Java 27**, các giá trị format hợp lệ là `plain` hoặc `json` (mặc định `plain`). Một số bài hướng dẫn dùng cách viết `-format=text` ở các phiên bản/tài liệu khác; khi viết script cho Java 27, hãy ưu tiên `plain`/`json` và xác minh bằng `help` của JVM đích.

**Cẩn thận vị trí file:** đường dẫn tương đối có thể được diễn giải theo working directory của **JVM đích**, không phải thư mục hiện tại của người chạy `jcmd`. Trong môi trường vận hành, nên sử dụng đường dẫn tuyệt đối tới thư mục đã cấp quyền.

### 3.3. Không ghi đè dump cũ vô ý

Mặc định `Thread.dump_to_file` không cho phép overwrite file đã tồn tại; có tùy chọn `-overwrite` nếu bạn thật sự cần. Để điều tra thay đổi theo thời gian, hãy đặt tên theo thứ tự hoặc timestamp thay vì ghi đè.

```text
jcmd <pid> Thread.dump_to_file -format=json /var/tmp/threads-01.json
jcmd <pid> Thread.dump_to_file -format=json /var/tmp/threads-02.json
jcmd <pid> Thread.dump_to_file -format=json /var/tmp/threads-03.json
```

Đây là **lệnh minh họa** cho hệ thống kiểu Unix. Đường dẫn trên Windows/container phải được thay bằng đường dẫn phù hợp và được phép ghi.

## 4. Thread dump không phải một kết luận hoàn chỉnh

Một thread dump là **mẫu quan sát**. Thread đang chờ ở thời điểm thu dump có thể tiếp tục ngay sau đó. Ngược lại, một task kẹt rất lâu có thể chỉ hiện một stack cố định qua nhiều mẫu.

Với `Thread.dump_to_file`, tài liệu Java 27 nhấn mạnh dump **không dừng toàn JVM để chụp một snapshot đồng nhất**. Mỗi thread có timestamp, vì vậy các thread có thể được quan sát ở những thời điểm hơi khác nhau. Điều này đặc biệt quan trọng khi định suy ra **chu trình lock ownership** từ một file duy nhất.

### 4.1. Quy trình lấy nhiều snapshot

```text
T0: Xác nhận triệu chứng và lưu metrics.
T1: Thread dump số 1.
T2: Thread dump số 2 sau một khoảng hợp lý.
T3: Thread dump số 3 nếu triệu chứng còn kéo dài.
T4: Đối chiếu stack, state, lock owner, queue, pool metrics.
```

Khoảng giữa các mẫu tùy sự cố: vài giây cho request treo, lâu hơn cho timeout hiếm. Không có chu kỳ cứng đúng cho mọi ứng dụng. Mục tiêu là phân biệt **chờ ngắn hợp lệ** với **chờ kéo dài bất thường**.

Nếu đang điều tra một sự cố có thể biến mất nhanh, ưu tiên thu các thông tin ít xâm lấn và gắn timestamp/correlation ID trước khi can thiệp.

## 5. Đọc phần header của một platform thread

Một đoạn thread dump truyền thống minh họa:

```text
"order-worker-7" #53 daemon prio=5 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.orders.Inventory.reserve(Inventory.java:84)
        - waiting to lock <0x000000071234abcd> (a java.lang.Object)
        at com.example.orders.OrderService.place(OrderService.java:121)
```

Tùy JDK và option, header có thể chứa:

- **Tên thread**: hữu ích nhất khi code đặt tên có chủ đích.
- **Thread ID** (`#53` hoặc một trường ID khác): dùng để ghép dữ liệu trong JVM.
- **Native thread ID** (`nid`) đối với platform thread: hữu ích khi đối chiếu OS-level CPU profiler.
- **Daemon/priority/elapsed/cpu** nếu format cung cấp.
- **Thread state** và **stack frames**.

Dòng `Inventory.reserve(Inventory.java:84)` cho biết điểm thực thi liên quan đến trạng thái chờ. Nhưng muốn biết **tại sao** chờ, cần kết hợp lock identifier, owner, các stack của thread khác và logic nguồn.

**Không đồng nhất Java thread ID với OS thread ID.** Trong virtual-thread scheduling, không có một OS thread gắn cố định với mỗi virtual thread trong toàn bộ vòng đời.

### 5.1. Ý nghĩa các dòng lock

Trong một số dump truyền thống:

```text
- waiting to lock <0x...>
- locked <0x...>
```

`waiting to lock` mô tả monitor mà thread muốn chiếm; `locked` mô tả monitor mà thread đang giữ tại một frame. Có thể dò cùng object identifier ở các thread khác nhau **trong cùng một dump phù hợp** để tìm owner.

Địa chỉ và biểu diễn lock là chi tiết VM; đừng xem chúng là định danh ổn định giữa các lần chạy JVM.

## 6. Hiểu đúng các `Thread.State`

Java định nghĩa các trạng thái cơ bản:

| State | Ý nghĩa chính | Có phải lỗi không? |
| --- | --- | --- |
| `NEW` | Thread đã tạo nhưng chưa start | Thường bình thường |
| `RUNNABLE` | Đang thực thi trong JVM hoặc ở trạng thái runnable theo mô hình JVM | Không tự suy ra CPU đang bận |
| `BLOCKED` | Chờ để vào hoặc vào lại **object monitor** (`synchronized`) | Có thể là contention hợp lệ hoặc tắc nghẽn |
| `WAITING` | Chờ vô thời hạn cho một hành động khác | Có thể bình thường, cần xem điều kiện chờ |
| `TIMED_WAITING` | Chờ tối đa một thời hạn | Có thể bình thường; thời gian chờ vẫn cần quan sát |
| `TERMINATED` | Thread đã kết thúc | Thường không còn trong dump live threads |

**`BLOCKED` có nghĩa kỹ thuật cụ thể:** đang chờ monitor của Java. Một thread chờ `ReentrantLock.lock()` hoặc `Semaphore.acquire()` thường sẽ thấy stack liên quan `LockSupport.park`/AQS và state `WAITING`, **không phải bắt buộc `BLOCKED`**.

### 6.1. `RUNNABLE` không đồng nghĩa chắc chắn đốt CPU

Một thread có state `RUNNABLE` có thể đang ở một đường gọi I/O/native hoặc đang có khả năng chạy, không nhất thiết tiêu thụ 100% CPU. Muốn xác định CPU hotspot, so sánh **CPU time delta theo thread**, JFR/execution samples và OS metrics.

### 6.2. `WAITING` không đồng nghĩa deadlock

Ví dụ worker nhàn rỗi chờ queue:

```text
java.lang.Thread.State: WAITING (parking)
  at jdk.internal.misc.Unsafe.park(...)
  at java.util.concurrent.locks.LockSupport.park(...)
  at java.util.concurrent.LinkedBlockingQueue.take(...)
```

Đó có thể là trạng thái **bình thường** khi chưa có task. Nếu API response bị treo, hãy hỏi: task đã được submit chưa? Có đang nằm trong queue chưa? Worker có đang bận ở một bước khác không?

### 6.3. `TIMED_WAITING` không đảm bảo timeout sẽ giải quyết toàn bộ request

Một task `Thread.sleep`, `Condition.await(timeout, unit)` hoặc timed socket operation có thể ở trạng thái chờ có thời hạn. Tuy nhiên **deadline của một phép chờ** không đồng nghĩa **deadline tổng của request**. Một request có thể lần lượt trải qua nhiều lần chờ và vẫn vi phạm SLA.

## 7. Phân loại nút thắt từ stack và trạng thái

| Stack/frame thường thấy | Khả năng cần điều tra | Bằng chứng bổ sung |
| --- | --- | --- |
| `synchronized`/monitorenter; `BLOCKED` | Contention trên object monitor | Monitor owner, thời gian giữ lock |
| `ReentrantLock`, `AbstractQueuedSynchronizer`, `LockSupport.park` | Chờ lock hoặc synchronizer | AQS owner, queue length, contention metrics |
| `Semaphore.acquire` | Hết permit tới tài nguyên giới hạn | Available permits, request rates |
| `CountDownLatch.await` | Task chờ một signal không đến | Ai phải countDown, lifecycle và timeout |
| `FutureTask.get`/`CompletableFuture.join` | Chờ một kết quả bất đồng bộ | Future producer, executor queue/cancellation |
| `ThreadPoolExecutor.getTask`/`BlockingQueue.take` | Worker đang chờ task | Queue/active worker; thường bình thường |
| JDBC driver/pool `getConnection` | Pool cạn, connection giữ quá lâu | Active/idle/pending, checkout duration |
| HTTP client, `SocketRead`, TLS/driver I/O | Downstream chậm hoặc network stall | Timeout, server latency, retries, TCP metrics |
| `Object.wait`/`Condition.await` | Chờ điều kiện | Signal path, producer/consumer |
| Một method liên tục `RUNNABLE` | CPU loop hoặc công việc CPU-heavy | CPU samples, stack delta, profiler |
| Virtual thread scheduler queue cao | Có nhiều task chưa được schedule/tiếp tục | `Thread.vthread_scheduler`, JFR, CPU/load |

Bảng này chỉ gợi ý. Cùng một frame có thể xuất hiện trong hoạt động hợp lệ và trong sự cố; phải đặt nó vào **bối cảnh workload**.

## 8. Đồ thị wait-for: người chờ, tài nguyên và owner

Một cách đọc dump hiệu quả là dựng sơ đồ:

```text
Task A ------ waits for ------> Lock X
                                |
                                | owned by
                                v
                              Task B
                                |
                                +------ waits for ------> Lock Y
                                                         |
                                                         | owned by
                                                         v
                                                       Task C
```

Nếu Task C đang xử lý I/O lâu, A và B có thể cùng chậm dù bản thân chúng không gọi mạng. **Điểm gốc** không nhất thiết là thread đang có nhiều người chờ nhất: có thể là một owner giữ lock quá lâu hoặc một downstream đã không phản hồi.

### 8.1. Deadlock khi có một chu trình

```text
Thread A giữ Lock X ------ chờ Lock Y
    ^                         |
    |                         v
Thread B chờ Lock X <---- giữ Lock Y
```

Nếu cả A và B không thể tiến triển vì mỗi bên cần khóa đang do bên kia giữ, đó là **deadlock**. Tuy nhiên **không phải mọi chuỗi chờ dài đều là deadlock**: một owner có thể giải phóng tài nguyên sau khi hoàn tất công việc.

### 8.2. Những câu hỏi cần đặt ra

1. Thread đang **chờ tài nguyên nào**?
2. Ai đang **giữ hoặc có trách nhiệm sản xuất** tài nguyên đó?
3. Owner đang **làm gì**: tính toán, I/O, chờ lock khác hay đã bị lỗi?
4. Có **vòng chờ khép kín** hay chỉ một chuỗi cuối cùng vẫn có tiến triển?
5. Tình trạng này có lặp lại qua nhiều dump không?
6. Có deadline/cancellation để phá chờ kéo dài không?

## 9. Ví dụ hoàn chỉnh: tái hiện `BLOCKED` an toàn

Chương trình sau tạo hai **platform threads**. Một thread giữ monitor trong thời gian ngắn, thread còn lại cố vào cùng monitor và phải chờ. Chương trình tự kết thúc, **không tạo deadlock vĩnh viễn**.

Lưu thành `BlockedTaskDemo.java` khi thực hành:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class BlockedTaskDemo {
    private static final Object MONITOR = new Object();
    private static final CountDownLatch HELD = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread holder = Thread.ofPlatform()
            .name("demo-monitor-holder")
            .start(() -> {
                synchronized (MONITOR) {
                    HELD.countDown();

                    try {
                        // Giữ monitor đủ lâu để chụp thread dump.
                        RELEASE.await(30, TimeUnit.SECONDS);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                }
            });

        // Bảo đảm holder đã vào synchronized trước contender.
        HELD.await();

        Thread contender = Thread.ofPlatform()
            .name("demo-monitor-contender")
            .start(() -> {
                synchronized (MONITOR) {
                    System.out.println("Contender acquired monitor");
                }
            });

        long pid = ProcessHandle.current().pid();
        System.out.println("PID: " + pid);
        System.out.println("Capture dump before monitor is released");

        try {
            Thread.sleep(15_000);
        } finally {
            RELEASE.countDown();
        }

        holder.join();
        contender.join();
        System.out.println("Demo finished");
    }
}
```

Biên dịch và chạy:

```text
javac BlockedTaskDemo.java
java BlockedTaskDemo
```

Trong lúc chương trình đang chạy, mở một terminal khác để lấy dump bằng PID được in ra:

```text
jcmd <pid> Thread.print -l
```

Hoặc:

```text
jcmd <pid> Thread.dump_to_file -format=json blocked-demo.json
```

**Kỳ vọng quan sát** khi capture đúng thời điểm:

- `demo-monitor-holder` đang sở hữu `MONITOR` và chờ trên `CountDownLatch`.
- `demo-monitor-contender` ở trạng thái `BLOCKED`, muốn vào cùng monitor.
- Sau khi main gọi `RELEASE.countDown()`, holder rời synchronized, contender lấy được monitor và chương trình kết thúc.

Nếu bạn thu dump sau khi đã giải phóng monitor, contender có thể không còn `BLOCKED`; đó là tính chất của snapshot, **không phải code demo sai**.

### 9.1. Phân tích nguyên nhân từ ví dụ

Đây là một **lock contention có thời hạn**, không phải deadlock. Owner `demo-monitor-holder` có điều kiện hoàn tất: `RELEASE.await` được main giải phóng, và bản thân await có timeout. Vì vậy cả hai thread có đường tiến triển.

Tình huống sẽ đáng lo nếu owner chờ một tín hiệu mà **chính contender phải phát**, trong khi contender không thể vào monitor để làm việc. Khi đó có thể xuất hiện một chu trình chờ ở cấp logic.

### 9.2. Không nên giữ monitor khi chờ I/O dài

Ví dụ demo giữ monitor khi chờ latch để dễ quan sát; đó **không phải design pattern khuyến nghị**. Trong production, hãy giảm thời gian giữ lock, tránh gọi remote API hoặc xử lý nhiều dữ liệu trong critical section, và dùng timeout/lock discipline phù hợp.

## 10. Điều tra `ReentrantLock`, AQS và `LockSupport`

Với `ReentrantLock`, một waiter thường **không** có `Thread.State.BLOCKED`, dù nghiệp vụ đang bị chặn bởi một khóa. Stack có thể bao gồm:

```text
java.lang.Thread.State: WAITING (parking)
  at jdk.internal.misc.Unsafe.park(...)
  at java.util.concurrent.locks.LockSupport.park(...)
  at java.util.concurrent.locks.AbstractQueuedSynchronizer...
  at java.util.concurrent.locks.ReentrantLock.lock(...)
```

Đừng bỏ qua thread này chỉ vì bộ lọc tìm `BLOCKED` không thấy gì.

### 10.1. Owner của `ReentrantLock` là ai?

`Thread.print -l` và các thông tin locked ownable synchronizers có thể giúp nhận diện lock, nhưng việc biết **ai sở hữu** còn tùy loại synchronizer và mức thông tin dump cung cấp. Cần đối chiếu:

- Các frame acquire/release.
- Lock identifier và owner information (nếu có).
- Metrics về lock wait time.
- Code sở hữu instance `ReentrantLock`.
- Trace của task có khả năng đang giữ lock trong một lệnh gọi dài.

Nếu ứng dụng kiểm soát code, có thể đo lock contention bằng telemetry có kiểm soát; không cần expose mọi lock internals ra HTTP endpoint.

### 10.2. `Condition.await` là chờ điều kiện, không phải chờ vào lock

Với `Condition.await()`, thread **nhả associated lock** theo contract rồi đợi signal. Thread dump có thể biểu thị nó đang park/wait. Việc tìm một owner giữ lock không đủ để kết luận nguyên nhân; phải xem **ai có nhiệm vụ gọi `signal()` hoặc `signalAll()`** và predicate nào phải trở thành true.

## 11. Thread pool cạn, queue đầy và producer/consumer

Một API có thể treo mà không hề có deadlock monitor:

```text
HTTP request
    |
    v
submit task vào ThreadPoolExecutor
    |
    +--> task nằm trong queue, chưa được worker nhận
    |
    +--> caller gọi Future.get() và chờ
```

Nếu tất cả worker đang xử lý tác vụ lâu hoặc đang chờ những task nằm trong **cùng pool**, hệ thống có thể tự tạo **thread starvation deadlock** (tắc nghẽn do không có worker rảnh), dù JVM không phát hiện một chu trình monitor lock.

### 11.1. Bẫy submit rồi đợi trong cùng executor

Đoạn code minh họa anti-pattern:

```java
// PSEUDOCODE — tránh thiết kế kiểu này nếu executor nhỏ:
// executor.submit(() -> {
//     Future<?> child = executor.submit(someOtherTask);
//     child.get(); // Parent chiếm worker và đợi child chưa được chạy.
// });
```

Nếu pool chỉ có một worker và parent giữ worker đó để chờ child, child nằm trong queue và không ai chạy. `findDeadlockedThreads()` có thể **không phát hiện** kiểu tắc nghẽn này vì không tồn tại chu trình object monitor/ownable synchronizer theo API.

### 11.2. Cần xem metrics gì?

| Metric | Dấu hiệu đáng chú ý |
| --- | --- |
| `activeCount` của executor | Gần tối đa trong thời gian dài |
| Queue size/age | Tăng và task cũ không được lấy ra |
| Completed task count | Không tăng tương xứng với task được submit |
| Rejection count | Tác vụ bị từ chối do policy/quota |
| Task duration | Những task giữ worker quá lâu |
| Future wait time | Caller chờ kết quả từ task không có cơ hội chạy |

Không tăng pool size vô hạn như một cách sửa tạm: có thể chuyển sự cố sang database, CPU hoặc giới hạn hệ điều hành.

## 12. JDBC pool, semaphore và downstream I/O

Những hệ thống dùng virtual thread hoặc executor lớn thường bị giới hạn bởi **tài nguyên downstream**, chứ không phải số thread tạo được.

Ví dụ 200 request đồng thời cần JDBC, nhưng pool chỉ có 20 connections:

```text
200 tasks
   |
   +--- 20 tasks mượn được JDBC connections
   |
   +-- 180 tasks chờ pool trả connection
```

Những task chờ pool thường xuất hiện ở các frame/condition của pool implementation, có thể là `WAITING` hoặc `TIMED_WAITING`, không bắt buộc `BLOCKED`.

### 12.1. Chẩn đoán đúng cần ba lớp

1. **Thread dump:** task đang chờ ở `getConnection()` hoặc một pool acquisition method.
2. **Pool metrics:** active/idle/pending, thời gian mượn, timeout, leak detection.
3. **DB metrics:** truy vấn đang chạy, lock wait, transaction duration, connection limits.

Nếu 20 connection đang được giữ bởi các truy vấn rất chậm, tăng pool lên 100 có thể làm database quá tải nặng hơn. Hãy tìm **vì sao 20 connection không được trả** trước.

### 12.2. Mạng không có nghĩa là deadlock

Một thread đứng ở `SocketDispatcher.read`, HTTP client hoặc driver network I/O có thể đang chờ server gửi dữ liệu. Muốn xác nhận:

- Request đã đến server chưa?
- Server có đang xử lý truy vấn chậm không?
- Connect/read/request timeout đã được đặt đúng chưa?
- Có retry storm hoặc rate limit không?
- Có DNS/TLS/proxy/network issue không?

Một thread dump không đo được RTT, network packet loss hoặc toàn bộ trạng thái server khác. Kết hợp distributed tracing và server-side telemetry.

## 13. Virtual threads: cách thu dump cho một lượng task rất lớn

Virtual thread là `Thread` do Java runtime quản lý; nó có thể được mount lên carrier platform thread, rồi unmount khi chờ I/O. Một virtual thread đang chờ có thể vẫn giữ task/context nhưng **không chiếm carrier**.

Dùng:

```text
jcmd <pid> Thread.dump_to_file -format=json vthreads-01.json
```

Lệnh này phù hợp hơn `Thread.print` khi muốn quan sát **nhiều virtual threads**, gồm cả những thread không mounted tại thời điểm thu dump.

### 13.1. Đọc thread dump virtual thread khác điều gì?

- Có thể có **rất nhiều task** chờ hợp lệ.
- Nhìn state không đủ để biết carrier scheduler có bị tắc không.
- Cần gom nhóm stack theo **nơi chờ** để thấy điểm nghẽn tập trung.
- Một vài virtual threads vẫn chạy CPU-bound có thể chiếm carrier lâu.
- JSON dump có thể rất lớn; dùng công cụ phân tích thay vì mở toàn bộ bằng text editor.
- `Thread.dump_to_file` **không tự dò deadlock**, nhất là khi phân tích nhiều lock/task liên quan.

### 13.2. `Thread.vthread_scheduler`

```text
jcmd <pid> Thread.vthread_scheduler
```

Command giúp quan sát trạng thái scheduler và các delayed-task schedulers của virtual threads. Khi số tác vụ chờ/queued cao hoặc rất ít carrier đang tiến triển, kết hợp với CPU, task submission rate và stack traces để tìm nguyên nhân.

```text
jcmd <pid> Thread.vthread_pollers
```

Command này cung cấp thông tin về I/O pollers phục vụ các virtual threads chờ network/socket I/O.

**Không diễn giải scheduler queue lớn một cách độc lập thành bug.** Queue còn phụ thuộc số task được submit, tình trạng I/O, parallelism, thời điểm snapshot và loại workload.

### 13.3. `synchronized` và pinning trong Java 27

Một số bài viết về virtual threads trên Java 21–23 hướng dẫn thay **mọi** `synchronized` bằng `ReentrantLock` để tránh **carrier pinning**. Trong **Java 27**, nội dung đó đã **lỗi thời**: JEP 491 (từ JDK 24) đã loại bỏ nguyên nhân pinning do sử dụng Java monitors trong các trường hợp blocking thông thường.

Pinning vẫn có thể tồn tại trong các tình huống liên quan **native/foreign calls** hoặc những đường thực thi không thể unmount theo runtime. Khi cần điều tra, dùng JFR event `jdk.VirtualThreadPinned` trên JDK thực tế và xem lý do được ghi.

Không xem “có synchronized” là bằng chứng pinning trong Java 27. Tuy vậy, **lock contention thực sự vẫn có thể làm các task chờ lâu**; việc bỏ pinning không xóa các quy tắc đồng bộ của Java.

## 14. Deadlock detection: giới hạn quan trọng của `ThreadMXBean`

Java cung cấp API quản lý thread:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

Các phương thức:

- `findMonitorDeadlockedThreads()`: tìm chu trình chờ **object monitors**.
- `findDeadlockedThreads()`: tìm chu trình của **object monitors và ownable synchronizers** theo khả năng JVM.
- `dumpAllThreads(...)`: lấy thông tin platform-thread cùng stack/lock trong phạm vi API.

**Điểm đặc biệt của Java 27:** `ThreadMXBean` **không hỗ trợ giám sát/quản lý virtual threads**. Phát hiện deadlock từ các phương thức trên **chỉ áp dụng cho platform threads**; các chu trình chứa virtual thread sẽ không được tìm bằng các method đó.

### 14.1. Ví dụ kiểm tra deadlock trong chính JVM

Đoạn dưới đây phải được **tích hợp vào tiến trình cần chẩn đoán**. Tạo một process Java riêng rồi gọi method này không tự đọc được threads của service khác.

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public final class DeadlockProbe {
    private DeadlockProbe() { }

    public static void reportPlatformThreadDeadlocks() {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        final long[] deadlocked;
        try {
            deadlocked = bean.findDeadlockedThreads();
        } catch (UnsupportedOperationException ex) {
            System.err.println("Ownable synchronizer inspection unsupported");
            return;
        }

        if (deadlocked == null || deadlocked.length == 0) {
            System.out.println("No supported platform-thread deadlock found");
            return;
        }

        ThreadInfo[] details = bean.getThreadInfo(
            deadlocked, true, true
        );

        for (ThreadInfo info : details) {
            if (info != null) {
                System.err.println(info);
            }
        }
    }
}
```

**Không hiểu “No supported platform-thread deadlock found” là không có tắc nghẽn trong toàn hệ thống.** API không phát hiện application-level starvation, mọi loại resource deadlock hoặc chu trình liên quan virtual threads.

### 14.2. Vì sao deadlock detector không đủ?

Một thread chờ Redis, một thread giữ database connection, và một task bị kẹt do mất callback có thể tạo vòng chờ ở tầng nghiệp vụ mà JVM không biết đó là cùng một tài nguyên logic.

Khi không có phát hiện deadlock tự động, cần dựng **wait-for graph** từ stack, metric và workflow, rồi xác minh bằng thao tác/thay đổi có kiểm soát.

## 15. JFR: từ ảnh chụp sang lịch sử sự kiện

Thread dump giúp nhìn **một thời điểm**. **Java Flight Recorder (JFR)** bổ sung **timeline** cho latency, lock contention, park, monitor wait, I/O và các sự kiện virtual thread mà recording có cấu hình ghi lại.

Bắt đầu một recording ngắn:

```text
jcmd <pid> JFR.start name=ThreadInvestigation settings=profile duration=60s filename=threads.jfr
```

Xem trạng thái recording:

```text
jcmd <pid> JFR.check
```

Dùng Java Mission Control (JMC) hoặc công cụ phân tích JFR tương thích. Có thể in những event cụ thể:

```text
jfr print --events jdk.ThreadPark,jdk.JavaMonitorEnter,jdk.JavaMonitorWait threads.jfr
```

Với virtual threads:

```text
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed threads.jfr
```

Tên event và sự kiện được bật có thể phụ thuộc JDK/JFR configuration. **Không thấy event không chứng minh sự kiện chưa từng xảy ra** nếu cấu hình recording không thu event đó, threshold cao hoặc dữ liệu đã bị lọc.

### 15.1. Event nên tìm theo triệu chứng

| Nhóm JFR | Có thể giúp gì? |
| --- | --- |
| `jdk.JavaMonitorEnter` | Xác định lock contention khi vào monitor |
| `jdk.JavaMonitorWait` | Quan sát việc chờ/thời lượng trên monitor |
| `jdk.ThreadPark` | Quan sát task park trong synchronizer hoặc chờ |
| `jdk.SocketRead` / `jdk.SocketWrite` | Thời lượng I/O network |
| `jdk.VirtualThreadPinned` | Chẩn đoán pinning còn tồn tại và lý do |
| `jdk.VirtualThreadSubmitFailed` | Khó khăn khi scheduler nhận/tiếp tục virtual thread |
| CPU/execution samples | Xác định CPU hotspots khác với wait bottlenecks |

JFR events có threshold và overhead. Nếu đang tìm một đợt chờ ngắn, kiểm tra threshold và recording profile có thu đúng sự kiện, thay vì chỉ nhìn kết quả trống.

### 15.2. Thread dump và JFR kết hợp thế nào?

```text
Thread dump #1/#2:
  140 tasks ở waiting stack "DataSource.getConnection"
        |
        v
JFR / trace:
  Thời gian chờ connection tăng mạnh từ 09:12
        |
        v
Pool + DB metrics:
  20/20 connections active; 5 transactions chạy > 1 phút
        |
        v
Giả thuyết có chứng cứ:
  Transaction/query giữ connection lâu làm queue tích tụ
```

Không nhất thiết phải tăng thread pool; hướng sửa có thể là tối ưu truy vấn, timeout/rollback và đóng connection đúng scope.

## 16. Thứ tự đọc dump khi đang xử lý sự cố thực tế

Khi mở một dump nhiều nghìn dòng, **không nên đọc tuần tự từ dòng đầu tới cuối** rồi chọn một stack ngẫu nhiên.

### Bước 1: Xác định những nhóm thread quan trọng

Phân loại theo:
- Tên thread hoặc prefix của service (ví dụ `http-worker`, `db-sync`, `job-`).
- Thread state.
- Top stack frames hoặc signature của các method đang chờ.
- Đường gọi cụ thể của nghiệp vụ.
- Platform/virtual thread, nếu format biểu thị.

### Bước 2: Đếm theo nhóm stack

Ví dụ bảng tổng hợp minh họa:

| Stack signature | Số task | State điển hình |
| --- | ---: | --- |
| `HikariPool.getConnection` | 230 | WAITING/TIMED_WAITING |
| `CompletableFuture.join` | 80 | WAITING |
| `SocketDispatcher.read` | 22 | RUNNABLE/WAITING tùy kiểu thread/runtime |
| `Inventory.reserve` | 12 | BLOCKED |
| `ThreadPoolExecutor.getTask` | 8 | WAITING — có thể hoàn toàn bình thường |

Số liệu trên chỉ là **ví dụ**, không phải một kết quả đo trên hệ thống thật. Tập trung vào nhóm đông bất thường và những nhóm liên quan trực tiếp đến request bị ảnh hưởng.

### Bước 3: Tìm owner hoặc producer

Nếu đang chờ lock, xác định owner. Nếu đang chờ `Future`, tìm task sản xuất kết quả. Nếu đang chờ connection pool, tìm các request đang giữ connection. Nếu network I/O chờ lâu, tìm server/downstream và deadline.

### Bước 4: So sánh nhiều snapshot

Nếu 230 task vẫn đứng ở cùng chỗ sau nhiều lần lấy dump và số pending requests tiếp tục tăng, đó là bằng chứng mạnh hơn nhiều so với một snapshot đơn lẻ.

### Bước 5: Xác minh bằng metric và tracing

Những con số cần đối chiếu: request duration, rate, error, active/idle connections, executor queue length, CPU usage, JFR park/monitor events, network timeout.

### Bước 6: Sửa nguyên nhân và kiểm thử lại

Sau khi sửa, chạy cùng workload rồi so sánh thời gian chờ, số task pending, throughput/p99 và khả năng shutdown. Không kết luận thành công chỉ vì thread dump không còn một stack đã thấy trước đó.

## 17. CPU spike khác với task bị chặn

Nếu CPU process cao, ưu tiên xác định thread hoặc code path sử dụng CPU. Những thread `RUNNABLE` có thể là điểm bắt đầu, nhưng **trạng thái RUNNABLE không đo CPU time**.

Trong môi trường cho phép, có thể kết hợp:
- OS-level per-thread CPU usage.
- `jcmd <pid> Thread.print -e` và thông tin CPU được cung cấp.
- JFR execution samples/CPU profiling.
- Các stack được quan sát liên tiếp tại cùng vị trí.

Ví dụ một vòng lặp tính toán:

```java
static long busyWork(long n) {
    long sum = 0;
    for (long i = 0; i < n; i++) {
        sum += (i * 31) ^ (i >>> 3);
    }
    return sum;
}
```

Một thread nằm trong method này lâu **không nhất thiết là lỗi**: workload có thể thật sự cần nhiều CPU. Cần hỏi liệu task có progress, có deadline hay input bất thường, và có chiếm CPU làm nghẽn request khác không.

### 17.1. Phân biệt CPU contention với lock contention

- CPU cao, ít thread chờ lock: xem profile CPU, thuật toán, GC hoặc load.
- CPU thấp, nhiều thread chờ khóa: xem lock owner và duration.
- CPU cao **và** nhiều thread chờ: owner có thể đang giữ lock trong tính toán quá nặng, nhưng cần chứng minh từ stack/metrics.

## 18. Vấn đề đặc biệt trong virtual-thread scheduler

Virtual threads giúp nhiều task chờ I/O mà không giữ một platform carrier cho mỗi task. Nhưng **không làm mọi tác vụ miễn phí** và không tự sửa deadlock hay resource exhaustion.

Các tình huống cần xem:

1. **Nhiều task chờ downstream:** có thể bình thường ở mức concurrency cho phép; cần metrics timeout/pool.
2. **Nhiều task CPU-bound:** virtual threads không thay thế scheduling strategy cho công việc CPU nặng.
3. **Carrier pinning còn tồn tại:** xem `jdk.VirtualThreadPinned` với lý do, đặc biệt native/foreign operations.
4. **Scheduler queue tăng liên tục:** đối chiếu CPU availability, task arrival/completion, pinning và GC.
5. **ThreadLocal giữ object lớn:** nhiều virtual threads đang sống có thể giữ memory dù không chiếm carrier.
6. **Deadlock có virtual threads:** API `ThreadMXBean.findDeadlockedThreads()` không phát hiện chu trình liên quan chúng.

**Không pool virtual threads để “điều trị” nhiều task đang chờ một service chậm.** Giới hạn tài nguyên khan hiếm bằng connection pool, `Semaphore` hoặc cơ chế rate limit phù hợp; sửa thời hạn và nguyên nhân downstream.

## 19. Lệnh chẩn đoán và mức độ tác động

`jcmd` cho biết một số command có **impact** (Low/Medium/High). Không nên coi tất cả là những thao tác đọc không ảnh hưởng hệ thống.

| Công cụ/lệnh | Mục đích | Cân nhắc vận hành |
| --- | --- | --- |
| `jcmd <pid> help` | Kiểm tra command set | Thường ít tác động |
| `Thread.print -l` | Stack và lock của platform/mounted virtual threads | Medium; output có thể lớn |
| `Thread.dump_to_file -format=json` | Dump gồm virtual threads vào file | Medium, phụ thuộc số thread; cần dung lượng đĩa |
| `Thread.vthread_scheduler` | Xem scheduler | Thường low impact |
| `Thread.vthread_pollers` | Xem I/O pollers | Thường low impact |
| `JFR.start` | Bắt đầu recording | Overhead tùy cấu hình, duration và event |
| `GC.class_histogram` | Thống kê object classes | Có thể tác động đáng kể tới heap/GC |
| `GC.heap_dump` | Ghi heap dump HPROF | **High impact**, file có thể rất lớn và nhạy cảm |

**Không lấy heap dump làm bước đầu tiên chỉ vì API treo**. Heap dump hữu ích khi nghi giữ object/memory leak, nhưng không phải công cụ trực tiếp nhất để điều tra `ReentrantLock`, JDBC pool wait hoặc `Future.get()`.

### 19.1. Bảo mật dữ liệu chẩn đoán

Một dump có thể chứa tên method/class, package nội bộ, đường dẫn và đôi khi dữ liệu/log context. File JFR/heap dump còn có thể chứa thông tin nhạy cảm hơn.

- Thu thập theo quyền được cấp.
- Ghi rõ thời gian, PID, JVM version và môi trường.
- Lưu file trong thư mục có ACL/permissions hợp lý.
- Không đưa raw dump lên kênh công khai.
- Đặt thời hạn retention và xóa theo quy trình sau điều tra.
- Tránh lấy nhiều dump lớn liên tục khi đĩa đang gần đầy.

## 20. Quy trình ứng cứu khi service treo

Dưới đây là một **runbook** ngắn, áp dụng cho Java 27 HotSpot với quyền vận hành phù hợp.

### 20.1. Thu bằng chứng

1. Ghi timestamp, service version, host/container, request rate, p99, error rate, CPU, heap/GC, pool metrics.
2. Xác định đúng JVM:
   ```text
   jcmd -l
   jcmd <pid> VM.version
   ```
3. Thu dump truyền thống để xem lock/platform threads:
   ```text
   jcmd <pid> Thread.print -l
   ```
4. Nếu có virtual threads hoặc muốn phân tích toàn bộ:
   ```text
   jcmd <pid> Thread.dump_to_file -format=json threads-01.json
   ```
5. Khi triệu chứng còn kéo dài, thu thêm các dump ở thời điểm khác:
   ```text
   jcmd <pid> Thread.dump_to_file -format=json threads-02.json
   ```
6. Với sự cố lặp lại, dùng JFR recording có thời hạn:
   ```text
   jcmd <pid> JFR.start name=HangStudy settings=profile duration=60s filename=hang.jfr
   ```

### 20.2. Phân loại và ưu tiên

| Triệu chứng sau khi thu | Ưu tiên điều tra |
| --- | --- |
| Nhiều `BLOCKED` cùng một monitor | Owner giữ monitor, critical section, lock order |
| Nhiều `WAITING` ở AQS/ReentrantLock | Lock contention, synchronizer ownership |
| Nhiều tasks chờ `Future.get()` | Producer task, executor queue, dependency cycle |
| Nhiều tasks chờ DB pool | Pool active/pending, connection leak, slow transactions |
| Nhiều tasks ở socket read | Downstream latency/timeout/network |
| Nhiều virtual threads và scheduler queue cao | Scheduler metrics, CPU, pinning, arrival/completion |
| Nhiều thread chạy cùng CPU-heavy frame | CPU sampling, algorithm, input characteristics |
| JVM reports platform-thread deadlock | Lock cycle/lock ordering, khôi phục có kiểm soát |

### 20.3. Hành động khắc phục

- Giảm thời gian giữ lock; **không** gọi network/database lâu khi đang giữ monitor nếu có thể tránh.
- Thiết kế thứ tự acquire locks nhất quán, giới hạn scope và xem xét timeout/cancellation.
- Không submit vào cùng executor rồi chờ trong một worker pool nhỏ nếu có thể gây starvation.
- Đặt request/read/connect timeout và tổng deadline cho I/O.
- Trả connection về pool bằng lifecycle chuẩn; điều tra long-running queries.
- Với virtual threads, giới hạn **tài nguyên** thay vì cố pool virtual threads.
- Thử nghiệm fix trên staging/load test, kiểm tra throughput, tail latency và tình trạng queue.
- Nếu cần restart service trong sự cố production, thực hiện theo runbook/authorization; dump không thay thế quy trình xử lý dữ liệu dang dở hoặc rollback transaction.

## 21. Các bẫy thường gặp khi phân tích thread dump

| Sai lầm | Tại sao sai? | Cách xử lý đúng |
| --- | --- | --- |
| Thấy một thread `WAITING` là kết luận deadlock | Worker idle cũng WAITING | Kiểm tra stack, vai trò task, owner/producer và thời gian |
| Chỉ đếm các thread `BLOCKED` | AQS/ReentrantLock/Semaphore có thể xuất hiện `WAITING` | Phân tích cả stack `LockSupport.park` |
| Nhìn `RUNNABLE` rồi kết luận CPU 100% | State không đo CPU usage | Dùng CPU time/JFR/OS metrics |
| Chỉ lấy một dump | Có thể bắt được trạng thái chờ rất ngắn | Lấy nhiều mẫu và đối chiếu |
| Coi `Thread.print` bao gồm mọi virtual thread | Nó không liệt kê đầy đủ các unmounted virtual threads | Dùng `Thread.dump_to_file` |
| Coi JSON dump là ảnh chụp nguyên tử | Dump virtual threads không đồng nhất và có timestamp | Không suy chu trình khóa chỉ từ một mẫu |
| Chờ `Thread.dump_to_file` tự báo deadlock | Command này không chạy deadlock detection | Dùng công cụ bổ sung và dựng wait-for graph |
| Dùng `ThreadMXBean` để đếm/tìm deadlock mọi virtual thread | API không hỗ trợ virtual threads | Dùng thread dump virtual/JFR/task metrics |
| Thấy caller ở `Future.get()` rồi sửa caller | Có thể producer hoặc executor bị nghẽn | Truy tìm task tạo kết quả |
| Thấy JDBC chờ rồi tăng connection pool vô hạn | Có thể query giữ connection quá lâu | Xem DB/transaction/connection lifetime |
| Dùng `-format=text` theo ví dụ cũ mà không kiểm tra | Man page Java 27 dùng `plain`/`json` | Omit format hoặc dùng `-format=json`; kiểm tra help |
| Dùng kinh nghiệm Java 21 để nói mọi `synchronized` pinning trong 27 | JEP 491 đã thay đổi hành vi từ JDK 24 | Xem JFR pinning reason thực tế |
| Thu heap dump rất lớn cho mọi lỗi treo | Có tác động và rủi ro dữ liệu cao | Ưu tiên thread/JFR/metrics theo triệu chứng |
| Tăng thread pool rồi bỏ qua queue/pool | Có thể chỉ dời bottleneck xuống downstream | Sửa dependency, timeout, giới hạn tài nguyên |
| Coi “không phát hiện deadlock” nghĩa ứng dụng chắc chắn tiến triển | Detector có phạm vi giới hạn | Kiểm tra starvation, logical waits và virtual threads |

## 22. Checklist chẩn đoán ứng dụng Java 27

Trước khi báo cáo nguyên nhân chính, hãy tự kiểm tra:

1. [ ] Đúng PID/JDK/host/container của tiến trình gặp sự cố?
2. [ ] Có timestamp, request metrics và mô tả triệu chứng cụ thể?
3. [ ] Đã kiểm tra `jcmd <pid> help` để dùng command đúng với JVM đích?
4. [ ] Đã lấy nhiều snapshot thay vì một file duy nhất nếu sự cố kéo dài?
5. [ ] Có phân biệt `Thread.print` với `Thread.dump_to_file` khi dùng virtual threads?
6. [ ] Có phân loại `BLOCKED`, `WAITING`, `TIMED_WAITING`, `RUNNABLE` theo stack và ngữ cảnh?
7. [ ] Có xác định được lock owner hoặc task producer phía sau waiter không?
8. [ ] Có kiểm tra `Future.get`/executor queue để loại trừ thread starvation?
9. [ ] Có kiểm tra DB/HTTP downstream metrics và deadline khi thấy I/O wait?
10. [ ] Với virtual threads, có xem scheduler/pollers và JFR pinning khi phù hợp?
11. [ ] Có nhớ `ThreadMXBean` không phát hiện deadlock có virtual thread?
12. [ ] Có tránh những hướng dẫn pinning/format đã lỗi thời không?
13. [ ] Có ghi lại giả thuyết **và bằng chứng phản bác** trước khi thay đổi code?
14. [ ] Hành động thu dump có được phép và không gây thêm rủi ro đĩa/CPU/bảo mật?
15. [ ] Sau khi sửa, có load test và kiểm tra queue, latency, throughput, shutdown không?

**Ghi nhớ:** một thread bị chặn không phải là sự cố; **tác vụ chờ không tiến triển đúng hạn** mới là tín hiệu cần điều tra. Để giải thích hiện tượng đó, cần nối được ba yếu tố: **stack đang chờ điều gì**, **ai sở hữu hoặc tạo ra điều được chờ**, và **vì sao điều kiện giải phóng không xảy ra đúng lúc**. `jcmd`, thread dump và JFR giúp thu bằng chứng cho phép trả lời những câu hỏi đó.

## Tài liệu tham khảo chính thức

- [Java SE 27 — The `jcmd` Command](https://download.java.net/java/early_access/jdk27/docs/specs/man/jcmd.html): `Thread.print`, `Thread.dump_to_file`, `Thread.vthread_scheduler`, `Thread.vthread_pollers`, impact và options. Khi Java 27 được phát hành chính thức, có thể dùng bản man page tương ứng của bản phát hành.
- [Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html): thread dump, quan sát scheduler, JFR và đặc điểm virtual thread/carrier.
- [Java SE 27 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html): cách dùng các công cụ điều tra JVM, thread state và lock details.
- [Java SE 27 — Troubleshoot Process Hangs and Loops](https://docs.oracle.com/en/java/javase/27/troubleshoot/troubleshoot-process-hangs-loops.html): workflow điều tra process treo hoặc loop.
- [Java SE 27 API — `Thread.State`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.State.html): các trạng thái thread chuẩn.
- [Java SE 27 API — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/ThreadMXBean.html): quản lý **platform threads**, deadlock detection và giới hạn hỗ trợ virtual threads.
- [Java SE 27 API — `ThreadInfo`](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/ThreadInfo.html): lock owner, stack, monitor và synchronizer data.
- [Java SE 27 API — `ReentrantLock`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): trạng thái lock, acquire/release và conditions.
- [Java SE 27 API — `ThreadPoolExecutor`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): worker pool, queue, task metrics.
- [Java SE 27 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/27/jfapi/flight-recorder.html): event recording, profiling và phân tích thời gian.
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi trạng thái pinning khi dùng monitors trên JDK hiện đại.
