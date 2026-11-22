# Phân tích thread latency bằng Java Flight Recorder (JFR)

Thread latency là khoảng thời gian một thread không thể tiếp tục phần việc cần làm đúng lúc. Thread có thể đang chờ lock, đợi tín hiệu, park trong thread pool, ngủ, chờ dữ liệu từ socket/file hoặc bị ảnh hưởng bởi GC. Những khoảng chờ này có thể làm request chậm dù CPU của JVM không cao.

Java Flight Recorder (JFR) ghi lại các event có timestamp và thời lượng để tìm những điểm thread bị dừng, đồng thời ghi các mẫu stack của thread đang thực thi code. Đây là công cụ phù hợp để phân biệt ứng dụng đang tốn thời gian vì lock, I/O, scheduling, GC hay xử lý CPU. JDK Mission Control (JMC) giúp xem bản ghi dưới dạng timeline, bảng và biểu đồ; công cụ `jfr` có thể lọc và in event ngay trên terminal.

JFR ghi nhận duration event (có start time và duration), instant event (ghi nhận tại một thời điểm) và sample event (lấy mẫu theo chu kỳ). Phân tích latency chủ yếu dùng duration event; CPU profiling dùng sample event.

## 1. Hiểu đúng thread latency

### 1.1. Latency khác CPU time và throughput

Ba khái niệm này đo những điều khác nhau:

| Chỉ số | Ý nghĩa | Ví dụ |
|---|---|---|
| Request latency | Thời gian từ lúc nhận request đến lúc trả kết quả | Request mất 800 ms |
| Thread CPU time | Thời gian thread thực sự được CPU thực thi | Thread dùng CPU 120 ms |
| Throughput | Số tác vụ hoàn tất trong một đơn vị thời gian | 500 request/giây |

Một request mất 800 ms nhưng thread chỉ dùng CPU 120 ms có thể đã dành phần lớn thời gian còn lại để chờ database, socket, lock hoặc queue. Nếu chỉ nhìn CPU, bạn có thể bỏ qua nguyên nhân thật.

Latency cũng không phải một event đơn lẻ. Một request có thể lần lượt chờ connection pool, đọc socket, chờ lock rồi mới xử lý tiếp. Các event JFR giúp tìm những khoảng chờ đó, nhưng không tự động tính được end-to-end request latency nếu ứng dụng chuyển request qua nhiều thread hoặc nhiều service.

### 1.2. Thread-stalling event là gì?

Thread-stalling event là event có thời lượng trong lúc thread không thực thi phần code ứng dụng cần thiết. Ví dụ:

- Một thread chờ vào synchronized monitor.
- Một thread gọi `Object.wait` để đợi notification.
- Một thread park trong `LockSupport` hoặc cơ chế đồng bộ của thư viện.
- Một thread ngủ bằng `Thread.sleep`.
- Một thread chờ dữ liệu socket hoặc file I/O.

JFR ghi timestamp, duration, thread và có thể kèm stack trace. Stack trace chỉ ra vị trí code bắt đầu thao tác chờ; với lock contention, event còn có thể chỉ ra thread đang giữ monitor.

Không phải mọi khoảng chờ đều là lỗi. Thread scheduler ngủ theo lịch, worker đợi queue hoặc thread chờ một tác vụ khác có thể là hành vi bình thường. Hãy xem event xảy ra trên thread nào, có nằm trên critical path của request hay không và có tăng khi latency tăng hay không.

## 2. Những event JFR cần xem

Tên event dưới đây là tên đầy đủ thường dùng trong HotSpot JDK 21.

| Event | Điều nó ghi lại | Dấu hiệu cần điều tra |
|---|---|---|
| `jdk.JavaMonitorEnter` | Thread bị chặn khi muốn vào synchronized monitor | Nhiều event dài, cùng lock hoặc cùng stack site |
| `jdk.JavaMonitorWait` | Thread gọi `Object.wait` và chờ notification/timeout | Wait kéo dài, notifier không đến hoặc điều kiện không được đáp ứng |
| `jdk.ThreadPark` | Thread park qua `LockSupport` và các cơ chế dựa trên park | Worker, Future, queue hoặc lock chờ quá lâu |
| `jdk.ThreadSleep` | Thread ngủ bằng `Thread.sleep` | Polling/sleep nằm trên đường xử lý request |
| `jdk.SocketRead` / `jdk.SocketWrite` | Thời gian đọc/ghi socket | Chờ peer, network, backpressure hoặc upstream |
| `jdk.FileRead` / `jdk.FileWrite` | Thời gian đọc/ghi file | Storage chậm hoặc file I/O đồng bộ |
| `jdk.ExecutionSample` | Mẫu stack của thread đang thực thi Java code | Method xuất hiện nhiều khi CPU cao |
| `jdk.NativeMethodSample` | Mẫu stack trong native method | Native call chiếm nhiều thời gian thực thi |
| `jdk.ThreadCPULoad` / `jdk.CPULoad` | CPU load theo thread/JVM và hệ thống | Thread hoặc process tiêu thụ CPU cao |
| `jdk.GCPhasePause` / `jdk.GarbageCollection` | GC và các pause phase | Pause trùng với thời điểm latency tăng |

### 2.1. Phân biệt JavaMonitorEnter và JavaMonitorWait

Hai event này dễ bị nhầm:

- `jdk.JavaMonitorEnter` xuất hiện khi thread muốn vào synchronized block/method nhưng monitor đang được thread khác giữ. Trong event, `eventThread` là thread chờ và `previousOwner` cho biết thread giữ lock trước đó.
- `jdk.JavaMonitorWait` xuất hiện khi code gọi `Object.wait`. Thread nhường monitor và chờ thread khác gọi notify/notifyAll hoặc hết timeout. Đây là cơ chế chờ điều kiện, không nhất thiết là lock contention.

Nếu nhiều thread có `JavaMonitorEnter` dài tại cùng stack site, hãy tìm owner của monitor và xem owner đang làm gì trong critical section. Nếu nhiều thread có `JavaMonitorWait`, hãy kiểm tra điều kiện chờ, notifier và logic đánh thức.

### 2.2. Phân biệt park, sleep và I/O

- `ThreadPark` thường liên quan `LockSupport.park`, `ReentrantLock`, queue, Future hoặc executor. Một worker park khi không có việc có thể hoàn toàn bình thường.
- `ThreadSleep` là khoảng ngủ do code yêu cầu. Hãy tìm xem sleep có nằm trong request path, vòng polling hoặc retry loop không.
- `SocketRead` cho biết thread chờ dữ liệu từ socket. Event có thể có host, port, số byte và stack trace. Thời gian đọc dài có thể liên quan service upstream, network hoặc peer gửi dữ liệu chậm.
- `SocketWrite` có thể kéo dài khi peer đọc chậm hoặc buffer/network bị backpressure.
- `FileRead` và `FileWrite` giúp phát hiện file I/O đồng bộ đang chặn worker.

Không kết luận network chậm chỉ từ một `SocketRead` dài. Hãy đối chiếu host/port, bytes, thời điểm, log của upstream và trace của request.

### 2.3. Phân biệt CPU-bound và wait-bound

Nếu các thread quan trọng có nhiều `ExecutionSample` tại cùng method và CPU load cao, ứng dụng có thể CPU-bound. Dùng Hot Methods/Call Tree trong JMC để tìm method được sample nhiều.

Nếu request chậm nhưng CPU load thấp và có nhiều event lock/socket/park dài, vấn đề có thể là chờ tài nguyên hoặc chờ một dependency. Thread đang blocked thường không xuất hiện trong execution samples vì nó không chạy Java code trong thời gian đó.

Execution samples là dữ liệu sampling, không phải phép đo chính xác thời gian chạy từng method. Dùng chúng để tìm hotspot tương đối, rồi xác nhận bằng profiling hoặc phép đo phù hợp.

### 2.4. GC cũng có thể gây latency

GC có nhiều phase chạy đồng thời với ứng dụng; tổng thời gian một GC không đồng nghĩa toàn bộ thời gian đó là application pause. Khi điều tra latency, xem `jdk.GCPhasePause` và tổng pause time. Đối chiếu timestamp của pause với spike latency thay vì chỉ nhìn tổng thời gian GC.

## 3. Tạo flight recording

### 3.1. Tìm PID của JVM

Liệt kê các JVM mà `jcmd` nhìn thấy:

~~~bash
jcmd -l
~~~

Hoặc:

~~~bash
jps -l
~~~

Dùng PID của đúng instance. Trong Docker hoặc process namespace riêng, PID bên trong container có thể khác PID trên host; hãy tìm PID trong đúng namespace.

`jcmd` phải chạy trên cùng máy với JVM đích và bằng cùng effective user/group identifiers đã dùng để khởi chạy JVM. Nếu attach thất bại, kiểm tra PID, user, container và chính sách Attach API.

### 3.2. Ghi một khoảng thời gian ngắn

Với JVM đang chạy, bắt đầu recording bằng:

~~~bash
jcmd 12345 JFR.start name=thread-latency settings=profile duration=30s filename=thread-latency.jfr
~~~

Thay `12345` bằng PID thật. Recording kéo dài 30 giây và tự kết thúc, ghi file `thread-latency.jfr` trong working directory của JVM đích. Có thể dùng đường dẫn tuyệt đối nếu muốn lưu vào thư mục riêng; bảo đảm process có quyền ghi.

Kiểm tra recording đang chạy:

~~~bash
jcmd 12345 JFR.check name=thread-latency verbose=true
~~~

`settings=profile` thu thập nhiều dữ liệu hơn `default` và phù hợp với recording ngắn để điều tra. Template `default` có overhead thấp hơn và phù hợp với recording liên tục. Cả hai đều có thể được tùy chỉnh theo event cần quan sát.

### 3.3. Ghi khi khởi chạy ứng dụng

Nếu muốn recording bắt đầu cùng ứng dụng:

~~~bash
java -XX:StartFlightRecording=delay=10s,duration=60s,name=thread-latency,filename=thread-latency.jfr,settings=profile -cp out MyApplication
~~~

Lệnh này đợi 10 giây sau khi JVM khởi chạy, ghi 60 giây rồi lưu file. Cách này hữu ích khi lỗi xuất hiện ngay trong startup hoặc khi cần tái hiện cùng một workload.

### 3.4. Recording liên tục và lấy dữ liệu khi có sự cố

Có thể duy trì recording nhẹ với template `default`, giới hạn dữ liệu lưu trên disk:

~~~bash
jcmd 12345 JFR.start name=continuous settings=default disk=true maxage=1h maxsize=512m
~~~

Khi latency tăng, lấy phần dữ liệu gần nhất mà không dừng recording:

~~~bash
jcmd 12345 JFR.dump name=continuous filename=incident.jfr maxage=10m
~~~

`JFR.dump` ghi dữ liệu ra file và recording tiếp tục chạy. Khi cần kết thúc:

~~~bash
jcmd 12345 JFR.stop name=continuous filename=continuous-final.jfr
~~~

Dùng `JFR.check` để xem tên và trạng thái recording. Kiểm tra `jcmd <pid> help JFR.start`, `help JFR.dump` và `help JFR.stop` trên JVM đích nếu cần cú pháp chi tiết.

## 4. Phân tích recording bằng JDK Mission Control

JDK Mission Control (JMC) mở file `.jfr` và hiển thị event theo timeline. JMC không nằm trong mọi bản cài JDK tiêu chuẩn; cài JMC phù hợp với môi trường rồi mở recording.

Các khu vực hữu ích khi tìm thread latency:

1. **Automated Analysis Results:** xem các cảnh báo và gợi ý ban đầu về bottleneck.
2. **Java Application → Threads:** xem timeline hoạt động, trạng thái và stack trace của từng thread.
3. **Threads → Latencies:** xem loại event gây latency, chẳng hạn Java Monitor Wait, Java Monitor Blocked và Java Thread Park.
4. **Contention / Lock Instances:** xem lock nào bị tranh chấp, thread nào chờ và stack trace nơi lock được lấy.
5. **I/O:** xem Socket Read/Write và File Read/Write theo host, file, thread và event.
6. **Hot Methods / Call Tree:** xem code được sample nhiều khi ứng dụng CPU-bound.
7. **JVM Internals → Garbage Collections:** đối chiếu pause time và GC event với khoảng latency tăng.

Trong timeline, mỗi thread có một hàng và các đoạn event thể hiện thời gian thread bị chờ. Chọn event dài để xem stack trace, thread, lock owner hoặc host. Nếu nhiều event cùng xuất hiện ở một thời điểm, hãy xem chúng có cùng ảnh hưởng đến critical path của request hay không.

## 5. Phân tích recording bằng jfr trên terminal

### 5.1. Xem tổng quan recording

~~~bash
jfr summary thread-latency.jfr
~~~

Summary cho biết thời lượng recording, số lượng từng event và kích thước dữ liệu. Nếu không thấy event cần thiết, kiểm tra recording template và event setting trước khi kết luận ứng dụng không có hiện tượng đó.

### 5.2. In các event gây thread stall

~~~bash
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.ThreadSleep,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite --stack-depth 32 thread-latency.jfr
~~~

Lọc một loại event để dễ đọc:

~~~bash
jfr print --events jdk.JavaMonitorEnter --stack-depth 32 thread-latency.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite thread-latency.jfr
jfr print --events jdk.ThreadPark,jdk.ThreadSleep thread-latency.jfr
~~~

Một event monitor contention có thể có dạng:

~~~text
jdk.JavaMonitorEnter {
  startTime = 19:52:46.716
  duration = 85.3 ms
  monitorClass = java.lang.Object
  previousOwner = "fixture-lock-holder"
  eventThread = "fixture-lock-waiter"
  stackTrace = [
    ThreadLatencyFixture.lambda$main$1()
    java.lang.Thread.run()
  ]
}
~~~

Ở đây, `fixture-lock-waiter` chờ khoảng 85 ms để lấy monitor do `fixture-lock-holder` giữ. Stack trace chỉ ra nơi thread waiter muốn vào lock; kiểm tra code của owner để tìm critical section giữ lock quá lâu.

### 5.3. Xem CPU và GC

~~~bash
jfr print --events jdk.ExecutionSample,jdk.NativeMethodSample,jdk.ThreadCPULoad,jdk.CPULoad thread-latency.jfr
jfr print --events jdk.GCPhasePause,jdk.GarbageCollection thread-latency.jfr
~~~

Nếu JDK đang dùng cung cấp các view tổng hợp, xem danh sách trước:

~~~bash
jfr help view
~~~

Một số bản JDK có view như `latencies-by-type`, `contention-by-thread`, `contention-by-site`, `socket-reads-by-host` và `thread-cpu-load`. Khi view tồn tại, có thể gọi:

~~~bash
jfr view latencies-by-type thread-latency.jfr
jfr view contention-by-thread thread-latency.jfr
jfr view contention-by-site thread-latency.jfr
~~~

Danh sách view tích hợp thay đổi theo JDK release. Nếu không có view cần thiết, dùng `jfr print` hoặc mở file bằng JMC. `jfr metadata` giúp xem tên event, category và field layout của bản ghi.

## 6. Đọc kết quả và tìm nguyên nhân

| Dấu hiệu trong recording | Giả thuyết cần kiểm tra | Bước tiếp theo |
|---|---|---|
| Nhiều `JavaMonitorEnter` dài cùng lock | Critical section giữ monitor quá lâu | Tìm previousOwner, stack trace và code trong synchronized block |
| Nhiều `JavaMonitorWait` dài | Thread chờ notification/điều kiện không được đáp ứng | Kiểm tra notifier, timeout, queue và logic signal |
| Nhiều `ThreadPark` trên worker | Worker đợi queue, Future, semaphore hoặc lock | Xem executor, queue depth và stack trace của producer/consumer |
| `SocketRead` dài trên request thread | Chờ upstream hoặc network | Nhóm theo host/port, đối chiếu upstream latency và network metrics |
| `SocketWrite` dài | Peer đọc chậm hoặc backpressure | Kiểm tra consumer, buffer và throughput mạng |
| `FileRead`/`FileWrite` dài | File/storage I/O chậm | Xem file path, storage latency và stack trace |
| Nhiều `ExecutionSample` tại một method, CPU cao | Code CPU-bound | Dùng Hot Methods/Call Tree và profile method |
| GC pause trùng với request chậm | Stop-the-world pause góp phần vào latency | Xem GCPhasePause, pause time và allocation pressure |
| Không có stall event nhưng CPU cao | Thời gian chủ yếu nằm trong code đang chạy | Phân tích execution samples và CPU metrics |

### 6.1. Tìm lock contention

Bắt đầu từ event `JavaMonitorEnter` có duration dài. Ghi lại:

- Thread chờ lock (event thread).
- Thread giữ lock trước đó (previous owner).
- Loại monitor và stack trace của thread chờ.
- Lock address để đối chiếu các event cùng monitor trong một recording.

Sau đó tìm stack của owner ở các event/thread timeline gần cùng thời điểm. Owner có thể đang làm I/O, ghi log, gọi callback hoặc xử lý logic lâu trong synchronized block. Nếu có nhiều waiter cùng một owner, critical section đó có thể giới hạn concurrency.

Không kết luận deadlock chỉ từ contention. Deadlock là chu trình chờ lock; contention có thể chỉ là một thread giữ lock lâu rồi giải phóng.

### 6.2. Tìm I/O bottleneck

Nhóm `SocketRead`/`SocketWrite` theo host và thread. Nếu một host chiếm phần lớn tổng thời gian chờ, đối chiếu với metrics của service đó. Kiểm tra số byte, số lần đọc/ghi và stack trace để biết request nào tạo ra I/O.

Với file I/O, xem file nào được đọc/ghi nhiều và thời gian từng event. Một file log hoặc storage chậm có thể chặn nhiều worker nếu ứng dụng thực hiện I/O đồng bộ.

Tổng thời gian I/O cộng dồn trên nhiều thread có thể lớn hơn thời lượng recording vì các event xảy ra đồng thời. Không cộng duration của mọi thread rồi xem kết quả như thời gian ứng dụng bị chậm theo wall-clock.

### 6.3. Tìm CPU bottleneck

Khi CPU load cao, xem `ExecutionSample` và `NativeMethodSample`. Nhóm stack theo method để tìm code chiếm nhiều sample. Dùng JMC Hot Methods và Call Tree để lần từ method nóng về caller.

Sampling cho biết method nào xuất hiện nhiều trong các thời điểm lấy mẫu; nó không phải phép đo tuyệt đối thời gian từng method. So sánh với CPU metrics của process và máy để biết JVM hay một process khác đang dùng CPU.

### 6.4. Kiểm tra virtual thread trên JDK 21

JDK 21 có event `jdk.VirtualThreadPinned`. Event này ghi lại virtual thread bị pin vào carrier thread lâu hơn threshold mặc định 20 ms. Khi bị pin, carrier không được giải phóng để chạy virtual thread khác.

Trên JDK 21, blocking operation trong `synchronized` block/method hoặc native/foreign method có thể gây pinning. Nếu ứng dụng dùng virtual thread, lọc event:

~~~bash
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed thread-latency.jfr
~~~

Pinning kéo dài và lặp lại có thể làm giảm khả năng mở rộng của server. Xem stack trace và operation gây pinning; cân nhắc thay vùng synchronized giữ lâu quanh I/O bằng cơ chế lock phù hợp sau khi xác nhận bằng recording. Quy tắc pinning thay đổi theo JDK release, vì vậy hãy đối chiếu đúng phiên bản đang chạy.

Virtual thread giúp ứng dụng xử lý nhiều tác vụ chờ I/O đồng thời và cải thiện throughput; nó không làm code CPU chạy nhanh hơn hoặc tự động giảm latency của một request riêng lẻ.

## 7. Tùy chỉnh threshold để thấy event ngắn

JFR event duration có thể bị lọc bởi threshold trong template. Nếu threshold là 10 ms, event 2 ms sẽ không được ghi. Ngưỡng cụ thể phụ thuộc event và template; tài liệu JDK 21 mô tả mặc định synchronization events trong JMC là trên 10 ms, trong khi nhiều Java Application events có threshold khác.

Kiểm tra settings đang chạy:

~~~bash
jcmd 12345 JFR.check name=thread-latency verbose=true
~~~

Nếu cần xem contention ngắn hơn, có thể giảm threshold trong một recording ngắn:

~~~bash
jcmd 12345 JFR.start name=short-contention settings=profile duration=20s filename=short-contention.jfr jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorWait#threshold=5ms jdk.ThreadPark#threshold=5ms jdk.SocketRead#threshold=5ms jdk.SocketWrite#threshold=5ms
~~~

Hoặc tạo file cấu hình dùng lại:

~~~bash
jfr configure --input "$JAVA_HOME/lib/jfr/profile.jfc" --output latency.jfc jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorWait#threshold=5ms jdk.ThreadPark#threshold=5ms jdk.SocketRead#threshold=5ms jdk.SocketWrite#threshold=5ms
~~~

Sau đó dùng file cấu hình này trong `JFR.start` với `settings=/path/to/latency.jfc`. Threshold thấp hơn tạo nhiều event hơn, tăng kích thước recording và có thể làm overhead cao hơn. Hãy hạ ngưỡng cho event cần điều tra, ghi trong thời gian ngắn và theo dõi tác động.

Không bật heap statistics khi đang đo latency nếu không cần dữ liệu heap. Tùy chọn này có thể kích hoạt old GC lúc bắt đầu và kết thúc recording, tự tạo pause ảnh hưởng kết quả đo.

## 8. Thực hành Java 17+: tạo nhiều loại thread latency

Ví dụ sau tạo các thread để quan sát:

- `fixture-lock-holder` giữ monitor một lúc; `fixture-lock-waiter` liên tục chờ monitor đó.
- `fixture-monitor-wait` gọi `Object.wait` có timeout.
- `fixture-parker` dùng `LockSupport.parkNanos`.
- `fixture-sleeper` dùng `Thread.sleep`.
- `fixture-socket-reader` chờ byte từ socket loopback.
- `fixture-cpu-worker` chạy vòng tính toán để tạo CPU samples.

Tạo file `ThreadLatencyFixture.java`:

~~~java
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.LockSupport;

public final class ThreadLatencyFixture {
    private static final Object LOCK = new Object();
    private static volatile boolean running = true;
    private static volatile long checksum;

    public static void main(String[] args) throws Exception {
        ServerSocket server = new ServerSocket(
            0, 16, InetAddress.getLoopbackAddress()
        );

        Thread lockHolder = new Thread(() -> {
            while (running) {
                synchronized (LOCK) {
                    try {
                        Thread.sleep(90);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                pause(5);
            }
        }, "fixture-lock-holder");

        Thread lockWaiter = new Thread(() -> {
            while (running) {
                synchronized (LOCK) {
                    checksum++;
                }
                pause(5);
            }
        }, "fixture-lock-waiter");

        Thread monitorWaiter = new Thread(() -> {
            Object waitLock = new Object();
            while (running) {
                synchronized (waitLock) {
                    try {
                        waitLock.wait(55);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
            }
        }, "fixture-monitor-wait");

        Thread parker = new Thread(() -> {
            while (running) {
                LockSupport.parkNanos(55_000_000L);
            }
        }, "fixture-parker");

        Thread sleeper = new Thread(() -> {
            while (running) {
                pause(55);
            }
        }, "fixture-sleeper");

        Thread socketReader = new Thread(() -> {
            try (Socket socket = server.accept()) {
                while (running && socket.getInputStream().read() != -1) {
                    // Wait for the next byte from the local client.
                }
            } catch (Exception e) {
                if (running) {
                    throw new RuntimeException(e);
                }
            }
        }, "fixture-socket-reader");

        Thread socketWriter = new Thread(() -> {
            try (Socket socket = new Socket(
                    InetAddress.getLoopbackAddress(), server.getLocalPort())) {
                while (running) {
                    socket.getOutputStream().write(1);
                    socket.getOutputStream().flush();
                    pause(65);
                }
            } catch (Exception e) {
                if (running) {
                    throw new RuntimeException(e);
                }
            }
        }, "fixture-socket-writer");

        Thread cpuWorker = new Thread(() -> {
            long value = 1;
            while (running) {
                value = value * 1664525 + 1013904223;
                checksum ^= value;
            }
        }, "fixture-cpu-worker");

        Thread[] threads = {
            lockHolder, lockWaiter, monitorWaiter, parker,
            sleeper, socketReader, socketWriter, cpuWorker
        };

        for (Thread thread : threads) {
            thread.setDaemon(true);
            thread.start();
        }

        System.out.println("ThreadLatencyFixture ready");
        new CountDownLatch(1).await();
    }

    private static void pause(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Biên dịch và chạy ở terminal thứ nhất:

~~~bash
javac --release 17 -d out ThreadLatencyFixture.java
java -cp out ThreadLatencyFixture
~~~

Stdout chính xác:

~~~text
ThreadLatencyFixture ready
~~~

Chương trình tiếp tục chạy để bạn có thời gian lấy recording. Đây là workload thử nghiệm tạo wait có chủ ý; không dùng logic này trong ứng dụng thật.

Ở terminal thứ hai, tìm PID rồi ghi recording 8 giây:

~~~bash
jcmd -l
jcmd 12345 JFR.start name=thread-latency settings=profile duration=8s filename=thread-latency.jfr
~~~

Khi recording hoàn tất:

~~~bash
jfr summary thread-latency.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.ThreadSleep,jdk.SocketRead,jdk.ExecutionSample thread-latency.jfr
~~~

Nếu JDK có view latency tổng hợp:

~~~bash
jfr help view
jfr view latencies-by-type thread-latency.jfr
jfr view contention-by-thread thread-latency.jfr
~~~

Trong recording của fixture, bạn sẽ thấy event monitor contention gắn với `fixture-lock-waiter` và owner `fixture-lock-holder`; event socket read gắn với `fixture-socket-reader`; park/wait/sleep gắn với các thread tương ứng. CPU samples sẽ xuất hiện cho thread thực thi code và có thể gồm cả JIT compiler thread.

Dừng fixture bằng `Ctrl+C` ở terminal thứ nhất sau khi đã thu thập dữ liệu.

## 9. Quy trình điều tra latency trong ứng dụng thật

1. Xác định request hoặc operation chậm bằng metrics/APM; ghi lại p50, p95, p99 và thời điểm xảy ra.
2. Xác định JVM/PID, JDK release, workload và instance bị ảnh hưởng.
3. Bắt đầu JFR trước hoặc trong cửa sổ sự cố; chọn `default` cho continuous recording hoặc `profile` cho khoảng điều tra ngắn.
4. Dùng JMC Automated Analysis Results và Threads/Latencies để tìm loại event chiếm thời gian.
5. Nhóm event theo thread, lock, stack site hoặc host; xem những event dài và lặp lại trên critical path.
6. Nếu thấy lock contention, tìm owner và code giữ lock; nếu thấy socket/file I/O, đối chiếu dependency và storage metrics.
7. Nếu CPU cao, phân tích execution samples, Hot Methods và Call Tree.
8. Nếu pause GC trùng với spike, xem `GCPhasePause` và tổng pause time.
9. Đối chiếu với application log, trace ID, request metrics và recording của một thời điểm bình thường.
10. Thay đổi một nguyên nhân đã xác nhận, chạy lại cùng workload và so sánh p95/p99 cùng event profile.

JFR không tự biết một event thuộc HTTP request nào nếu ứng dụng không ghi request context. Khi cần nối event với business operation, dùng distributed tracing hoặc tạo custom JFR event chứa request/operation identifier đã được kiểm soát. Không đưa dữ liệu nhạy cảm vào custom event.

## 10. Giới hạn và lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy event lock | Event tắt, threshold quá cao hoặc contention quá ngắn | Kiểm tra `JFR.check verbose=true` và hạ threshold trong recording ngắn |
| Không thấy SocketRead/SocketWrite | Template không bật event hoặc thời gian I/O dưới threshold | Kiểm tra event setting và thêm event vào cấu hình |
| Có latency nhưng không có stall event | CPU-bound, event chưa được bật hoặc chờ dưới threshold | Xem ExecutionSample/CPU load và kiểm tra template |
| Nhiều ThreadSleep nhưng ứng dụng vẫn ổn | Thread ngủ theo lịch hoặc polling có chủ ý | Xác định thread có nằm trên critical path không |
| JavaMonitorWait bị hiểu nhầm là lock contention | `Object.wait` là chờ điều kiện và nhường monitor | Phân biệt với JavaMonitorEnter; xem notifier và timeout |
| Không attach được bằng jcmd | Sai PID, khác user/group hoặc sai container namespace | Chạy cùng máy/user với JVM và xác nhận PID |
| Không có file .jfr | Recording chưa dừng, sai working directory hoặc process không có quyền ghi | Kiểm tra JFR.check/JFR.stop và đường dẫn file |
| File recording rất lớn | Recording quá dài, nhiều event hoặc threshold quá thấp | Giới hạn duration/maxage/maxsize và chỉ bật event cần thiết |
| JFR ảnh hưởng latency đo được | Dùng profile chi tiết, threshold quá thấp hoặc bật heap statistics | Dùng default khi phù hợp, rút ngắn recording và tắt heap statistics |
| View jfr không tồn tại | Built-in views khác nhau theo JDK release | Chạy `jfr help view` hoặc dùng `jfr print`/JMC |

### 10.1. Event threshold có thể che mất khoảng chờ ngắn

Nhiều event duration không được ghi nếu thời lượng thấp hơn threshold. Vì vậy, recording không có `JavaMonitorEnter` dài không chứng minh hệ thống không có lock contention. Hãy kiểm tra threshold của event và cân nhắc hạ xuống vài millisecond trong một recording ngắn.

Đừng đặt threshold thấp cho tất cả event trong recording dài mà không đo overhead. Event nhiều hơn làm file lớn và có thể tăng chi phí thu thập.

### 10.2. Bảo vệ flight recording

File JFR có thể chứa stack trace, tên class/method, thread name, host/IP, file path, system properties và thông tin môi trường. Chỉ lưu file ở nơi được phép, giới hạn người có quyền đọc và lọc dữ liệu trước khi chia sẻ ra ngoài. Xóa file theo retention policy sau khi điều tra xong.

## 11. Checklist trước khi kết luận

- [ ] Đã xác định latency của request bằng metrics/APM.
- [ ] Đúng PID, JVM instance và JDK release.
- [ ] Recording bao phủ đúng khoảng xảy ra sự cố.
- [ ] Template và threshold có bật các event cần điều tra.
- [ ] Đã phân biệt JavaMonitorEnter với JavaMonitorWait.
- [ ] Đã xác định thread waiter, lock owner và stack site khi có contention.
- [ ] Đã xem SocketRead/Write và FileRead/Write khi nghi I/O.
- [ ] Đã xem ExecutionSample/CPU load khi nghi CPU-bound.
- [ ] Đã đối chiếu GC pause nếu thời điểm trùng với latency spike.
- [ ] Đã kiểm tra VirtualThreadPinned nếu ứng dụng dùng virtual thread trên JDK 21.
- [ ] Không xem tổng duration event trên nhiều thread là end-to-end request latency.
- [ ] Đã đối chiếu log, trace và recording baseline.
- [ ] Recording không bật heap statistics ngoài nhu cầu đo latency.
- [ ] File JFR được bảo vệ và xóa theo retention policy.

## 12. Ghi nhớ

JFR giúp tìm thời gian thread bị chặn và thời gian thread thực thi code. Bắt đầu từ event duration như `JavaMonitorEnter`, `JavaMonitorWait`, `ThreadPark`, `ThreadSleep`, `SocketRead` và `FileRead` để tìm các khoảng chờ. Khi không có nhiều stall event nhưng CPU cao, xem `ExecutionSample` và Hot Methods. Nếu GC pause trùng với spike, phân tích `GCPhasePause`.

Dùng JMC để đọc timeline, Latencies, Contention và I/O; dùng `jfr summary` và `jfr print` để lọc event trên terminal. Hạ threshold chỉ khi cần thấy wait ngắn và theo dõi overhead. Cuối cùng, đối chiếu JFR với request metrics và trace: event duration giúp giải thích nơi thread dừng lại, còn request latency vẫn phải được đo ở cấp ứng dụng.

Tài liệu tham khảo:

- [Diagnostic Tools — Java SE 21: Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — Java SE 21: JFR.start/JFR.dump/JFR.stop](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [The jfr Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 21](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf)
- [Virtual Threads — Java SE 21: JFR Events and Pinning](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java Mission Control and Flight Recorder Demo Series — Latencies/Contention](https://www.oracle.com/webfolder/technetwork/tutorials/obe/java/mc-jfr/index.html)