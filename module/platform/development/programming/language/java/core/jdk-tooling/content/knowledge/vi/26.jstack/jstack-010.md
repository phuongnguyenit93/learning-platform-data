# jstack và jcmd: thu thập và phân tích thread dump

Thread dump là ảnh chụp trạng thái các thread trong một JVM tại một thời điểm. Nó cho biết thread nào đang chạy, chờ, bị block khi lấy lock và stack trace hiện tại của từng thread. Đây là dữ liệu quan trọng khi ứng dụng bị treo, request xử lý chậm, CPU tăng cao hoặc nhiều thread tranh chấp tài nguyên.

Hai công cụ thường gặp là `jstack` và `jcmd`. Cả hai có thể lấy thread dump từ JVM đang chạy, nhưng Oracle đánh dấu `jstack` là *experimental and unsupported* và khuyến nghị dùng `jcmd` cho chẩn đoán mới. Bài này trình bày cả hai lệnh để bạn đọc được runbook cũ, đồng thời xây dựng quy trình mới dựa trên `jcmd`.

## 1. Thread dump giúp trả lời câu hỏi gì?

Một thread dump có thể giúp xác định:

- Thread đang thực thi đoạn code nào khi snapshot được tạo.
- Thread nào đang chờ monitor hoặc lock.
- Thread nào đang ở trạng thái `WAITING` hoặc `TIMED_WAITING`.
- Nhiều thread có đang chờ cùng một lock do một thread khác giữ hay không.
- Có chu trình chờ lock tạo thành Java-level deadlock hay không.
- Thread pool có nhiều worker bị kẹt trong cùng một method hoặc cùng một dependency hay không.

Thread dump là snapshot, không phải bản ghi liên tục. Nó chỉ thể hiện trạng thái tại thời điểm thu thập. Một thread ở `BLOCKED` trong một snapshot có thể lấy được lock ngay sau đó; một stack trace riêng lẻ không đủ để kết luận ứng dụng bị deadlock.

### 1.1. Những tình huống nên lấy thread dump

| Triệu chứng | Điều cần tìm trong dump |
|---|---|
| Request bị treo | Thread xử lý request đang chờ ở method, lock hoặc I/O nào |
| CPU tăng cao | Các thread `RUNNABLE` có stack lặp lại ở cùng một đoạn code |
| Throughput giảm | Thread pool worker bị block hoặc cùng chờ một tài nguyên |
| Ứng dụng không phản hồi | Main thread, event loop và các worker đang ở trạng thái nào |
| Deadlock | Chu trình thread chờ lock do thread khác giữ |
| Nghi ngờ lock contention | Nhiều thread cùng chờ một monitor/ownable synchronizer |

Nếu cần xem xu hướng theo thời gian, hãy kết hợp nhiều thread dump hoặc dùng Java Flight Recorder (JFR). Một thread dump không thể cho biết đầy đủ lịch sử CPU, latency hay sự kiện lock contention đã xảy ra trước đó.

## 2. Phân biệt jstack và jcmd

### 2.1. jstack

`jstack` là tiện ích dòng lệnh để in stack trace của các Java thread trong một Java process được chỉ định bằng PID.

Cú pháp cơ bản:

~~~bash
jstack <pid>
~~~

In thêm thông tin lock:

~~~bash
jstack -l <pid>
~~~

Tùy chọn `-l` (*long listing*) yêu cầu công cụ tìm và in thêm thông tin về lock, bao gồm ownable synchronizers dùng bởi các API như `java.util.concurrent.locks`. Điều này hữu ích khi điều tra `ReentrantLock` và các lock không phải intrinsic monitor.

Trợ giúp:

~~~bash
jstack -h
~~~

Tài liệu Oracle JDK 21 chỉ liệt kê `-l` và `-h`/`-help` trong trang man. Một số bản JDK mới hơn có thể cung cấp thêm tùy chọn, ví dụ `-e` để in thông tin thread mở rộng. Hãy xem `jstack -h` của toolchain đang dùng trước khi dựa vào một tùy chọn cụ thể.

### 2.2. jcmd

`jcmd` gửi diagnostic command trực tiếp tới JVM đang chạy. Để in thread dump, dùng command `Thread.print`:

~~~bash
jcmd <pid> Thread.print
~~~

In thêm lock:

~~~bash
jcmd <pid> Thread.print -l
~~~

In thông tin thread mở rộng:

~~~bash
jcmd <pid> Thread.print -e
~~~

Trong JDK 21, `Thread.print` hỗ trợ `-l` để in các lock `java.util.concurrent` và `-e` để in thông tin mở rộng. Tác động của command được Oracle mô tả là *Medium*, phụ thuộc số lượng thread.

Có thể hỏi JVM đích về cú pháp chính xác:

~~~bash
jcmd <pid> help Thread.print
~~~

### 2.3. Bảng so sánh

| Tiêu chí | jstack | jcmd |
|---|---|---|
| Chọn process | PID | PID hoặc main class |
| In thread dump | `jstack <pid>` | `jcmd <pid> Thread.print` |
| In thông tin lock | `-l` | `Thread.print -l` |
| Extended thread information | Tùy phiên bản; kiểm tra `jstack -h` | `Thread.print -e` |
| Ghi dump ra file | Redirect stdout của shell | Redirect stdout hoặc dùng `Thread.dump_to_file` nếu JVM hỗ trợ |
| Deadlock detection | Có | `Thread.print` cũng hiển thị deadlock khi JVM phát hiện |
| Tình trạng công cụ | Experimental/unsupported | Công cụ chẩn đoán được Oracle khuyến nghị |
| Phù hợp | Runbook cũ và thao tác quen thuộc | Chẩn đoán và automation mới |

**Khuyến nghị:** dùng `jcmd` cho quy trình mới. Giữ `jstack` để hiểu lệnh trong runbook legacy hoặc khi môi trường hiện tại vẫn sử dụng công cụ này.

## 3. Xác định PID của JVM

Trước khi lấy thread dump, cần chọn đúng Java process.

Liệt kê JVM mà `jcmd` phát hiện:

~~~bash
jcmd -l
~~~

Ví dụ:

~~~text
5485 jdk.jcmd/sun.tools.jcmd.JCmd
2125 com.example.orders.OrderApplication
7810 org.example.worker.BatchWorker
~~~

Có thể dùng `jps -l` hoặc lệnh hệ điều hành như `ps` để tìm process. Trong Docker, `jcmd -l` từ host có thể không liệt kê JVM chạy trong một Docker process riêng; hãy kiểm tra PID trong đúng container/PID namespace.

Sau khi xác định PID:

~~~bash
jstack -l 2125
jcmd 2125 Thread.print -l
~~~

`jstack` nhận PID của Java process. `jcmd` có thể nhận PID hoặc main class; nếu main class khớp nhiều process thì command có thể được gửi tới tất cả process khớp tên. Trong môi trường nhiều instance, dùng PID cụ thể để tránh lấy nhầm dump.

### 3.1. Điều kiện attach và quyền truy cập

Theo tài liệu Oracle, `jcmd` phải chạy trên cùng máy với JVM đích và bằng cùng effective user/group identifiers đã dùng để khởi chạy JVM. Attach còn chịu ảnh hưởng của quyền hệ điều hành, container policy và trạng thái Attach API của process.

Nếu lệnh báo không thể attach:

- Xác nhận PID còn tồn tại và thuộc đúng ứng dụng.
- Xác nhận tool chạy trên cùng host hoặc trong đúng container/PID namespace.
- Kiểm tra user/group của terminal và process.
- Dùng tool từ JDK phù hợp với phiên bản JVM đích.
- Kiểm tra JVM có bị khởi chạy với `-XX:+DisableAttachMechanism` hay không.

Không cần mở cổng mạng cho `jcmd` hoặc `jstack`; đây là cơ chế attach cục bộ. Nếu cần chẩn đoán từ xa, hãy dùng cơ chế quản trị từ xa đã được xác thực và bảo vệ như JMX hoặc nền tảng monitoring.

## 4. Thu thập thread dump bằng jstack

### 4.1. In ra terminal

~~~bash
jstack 2125
~~~

Lệnh in stack trace của các thread thuộc JVM có PID `2125`. Mỗi thread thường có tên, thread number, native thread ID, trạng thái và các stack frame.

### 4.2. In thêm lock và owner

~~~bash
jstack -l 2125
~~~

Dùng `-l` khi cần xem thông tin monitor/ownable synchronizer. Output có thể chứa những dòng như:

~~~text
"worker-1" #35 prio=5 tid=... nid=... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.Service.update(Service.java:42)
    - waiting to lock <0x0000000123456780> (a java.lang.Object)
    - locked <0x0000000123456790> (a java.lang.Object)
~~~

Cách đọc:

- `waiting to lock`: thread đang chờ lấy lock đó.
- `locked`: thread hiện đang giữ lock tương ứng.
- Địa chỉ object trong dấu `<...>` giúp đối chiếu lock giữa các thread trong cùng dump.
- Stack frame gần đầu thường cho biết method nơi thread bị chặn.

### 4.3. Lưu output vào file

Trên Linux/macOS:

~~~bash
jstack -l 2125 > thread-2125-01.txt 2>&1
~~~

Trên Windows PowerShell:

~~~powershell
jstack -l 2125 *> thread-2125-01.txt
~~~

Dùng tên file có PID và thời điểm để không ghi đè snapshot cũ. Đặt file trong thư mục chỉ người có trách nhiệm xử lý sự cố được phép đọc.

## 5. Thu thập thread dump bằng jcmd

### 5.1. In ra terminal

~~~bash
jcmd 2125 Thread.print
~~~

Đây là cách trực tiếp để in thread dump. Command hỗ trợ mọi thread mà JVM cung cấp qua diagnostic interface, cùng stack trace tương ứng.

### 5.2. Bổ sung thông tin lock

~~~bash
jcmd 2125 Thread.print -l
~~~

Dùng tùy chọn này khi nghi ngờ tranh chấp lock, đặc biệt với các cấu trúc thuộc `java.util.concurrent`. Nếu cần thêm thông tin thread mở rộng:

~~~bash
jcmd 2125 Thread.print -e
~~~

Có thể kết hợp hai tùy chọn:

~~~bash
jcmd 2125 Thread.print -e -l
~~~

Các tùy chọn của diagnostic command phải dùng đúng cú pháp mà JVM đích hỗ trợ. Kiểm tra trước:

~~~bash
jcmd 2125 help Thread.print
~~~

### 5.3. Lưu thread dump vào file

Cách tương thích rộng là redirect output của shell:

~~~bash
jcmd 2125 Thread.print -l > thread-2125-01.txt 2>&1
~~~

Từ JDK 22 trở lên, nhiều JDK cung cấp thêm diagnostic command `Thread.dump_to_file` để ghi thread dump trực tiếp ra file dạng plain text hoặc JSON. Kiểm tra command trên target JVM:

~~~bash
jcmd 2125 help Thread.dump_to_file
~~~

Nếu được hỗ trợ, có thể dùng:

~~~bash
jcmd 2125 Thread.dump_to_file threads-2125.json
jcmd 2125 Thread.dump_to_file -format=json threads-2125.json
jcmd 2125 Thread.dump_to_file -format=plain threads-2125.txt
~~~

JVM tạo file trong working directory của process nếu truyền đường dẫn tương đối. Dùng đường dẫn tuyệt đối khi cần kiểm soát vị trí lưu. Nếu đường dẫn có dấu cách, truyền argument theo đúng quy tắc quoting của shell và diagnostic command.

Mặc định command không ghi đè file đã tồn tại. Chỉ dùng `-overwrite` khi thực sự muốn thay thế file cũ:

~~~bash
jcmd 2125 Thread.dump_to_file -overwrite -format=json threads-2125.json
~~~

`Thread.dump_to_file` có impact Medium, phụ thuộc số lượng thread. Nếu cần lock details hoặc deadlock analysis, ưu tiên `Thread.print -l`; định dạng file cần được kiểm tra theo đúng phiên bản JDK.

## 6. Cách đọc thread state

Thread dump thường hiển thị trạng thái Java qua `java.lang.Thread.State`.

| State | Ý nghĩa | Cách diễn giải |
|---|---|---|
| `RUNNABLE` | Thread đang chạy hoặc sẵn sàng chạy trong JVM | Xem stack frame để biết đang tính toán, xử lý hoặc ở native call |
| `BLOCKED` | Thread đang chờ vào synchronized monitor | Tìm thread đang giữ monitor mà nó cần |
| `WAITING` | Thread chờ vô thời hạn một thread khác thực hiện hành động | Kiểm tra `Object.wait`, `LockSupport.park`, `CountDownLatch.await`, `join` |
| `TIMED_WAITING` | Thread chờ có thời hạn | Kiểm tra `Thread.sleep`, timed wait, timed park hoặc timed join |
| `NEW` | Thread chưa bắt đầu | Thường không xuất hiện như thread hoạt động trong dump |
| `TERMINATED` | Thread đã kết thúc | Không còn hoạt động để chẩn đoán trong JVM |

`RUNNABLE` không đảm bảo thread đang tiêu thụ CPU liên tục. Thread có thể đang chờ I/O trong native code hoặc chờ được OS scheduler cấp CPU. Cần đọc stack trace và đối chiếu với số liệu hệ điều hành.

### 6.1. BLOCKED khác WAITING

`BLOCKED` là trạng thái chờ lấy intrinsic monitor, thường do một thread khác đang giữ lock được yêu cầu. Trong dump, tìm:

~~~text
java.lang.Thread.State: BLOCKED (on object monitor)
- waiting to lock <0x...>
~~~

`WAITING` thường biểu thị thread đang chờ một điều kiện hoặc tín hiệu. Ví dụ:

~~~text
java.lang.Thread.State: WAITING (parking)
at java.util.concurrent.CountDownLatch.await(...)
~~~

Thread đang chờ latch được mở. Điều đó có thể hoàn toàn bình thường nếu nó đang đợi một tác vụ khác hoàn thành.

`TIMED_WAITING` cũng có thể bình thường, chẳng hạn thread scheduler đang ngủ để chờ chu kỳ tiếp theo. Đừng kết luận ứng dụng bị treo chỉ dựa vào tên state.

## 7. Phát hiện và phân tích deadlock

Deadlock xảy ra khi hai hoặc nhiều thread tạo thành chu trình chờ tài nguyên: mỗi thread giữ một lock và chờ lock do thread khác giữ. Không thread nào có thể tiếp tục để giải phóng lock của mình.

Ví dụ hai thread:

~~~text
Thread A giữ LOCK_A và chờ LOCK_B
Thread B giữ LOCK_B và chờ LOCK_A
~~~

Cả `jstack` và `jcmd Thread.print` có thể phát hiện Java-level deadlock. Output có dạng:

~~~text
Found one Java-level deadlock:
=============================

"demo-deadlock-A":
  waiting to lock monitor ... (object ..., a java.lang.Object),
  which is held by "demo-deadlock-B"

"demo-deadlock-B":
  waiting to lock monitor ... (object ..., a java.lang.Object),
  which is held by "demo-deadlock-A"
~~~

Để đọc kết quả:

1. Xác định thread nào đang chờ lock.
2. Xác định thread nào đang giữ lock đó.
3. Theo dõi tiếp lock mà thread giữ đang chờ.
4. Nếu chu trình quay lại thread ban đầu, có deadlock.
5. Dùng stack frame để tìm dòng code lấy lock và thứ tự lấy lock.

Không phải mọi thread `BLOCKED` đều bị deadlock. Một thread có thể bị block tạm thời trong khi thread giữ lock vẫn đang chạy bình thường. Deadlock cần một chu trình chờ không thể tự giải quyết.

### 7.1. Không có deadlock vẫn có thể có hang

Nếu output không có dòng `Found one Java-level deadlock`, ứng dụng vẫn có thể bị treo do:

- Thread chờ một event hoặc notification không bao giờ tới.
- Thread chờ I/O hoặc một dependency bên ngoài phản hồi.
- Một monitor được giữ quá lâu nhưng không tạo chu trình deadlock.
- Thread pool cạn worker vì tất cả worker cùng chờ một tài nguyên.
- Một thread đang chờ Future/CompletableFuture mà tác vụ hoàn thành không được thực thi.

Trong trường hợp này, xem stack trace của các thread đang chờ, thread giữ lock, thread pool worker và các thread liên quan đến network/database. So sánh nhiều snapshot để phân biệt trạng thái tạm thời với trạng thái bị kẹt lâu dài.

## 8. So sánh nhiều thread dump theo thời gian

Một snapshot là ảnh chụp tại một thời điểm. Khi điều tra hang hoặc CPU spike, hãy lấy một chuỗi snapshot cách nhau vài giây, ví dụ ba lần trong khoảng 5–10 giây nếu hệ thống cho phép.

Ví dụ:

~~~bash
jcmd 2125 Thread.print -l > dump-01.txt 2>&1
sleep 5
jcmd 2125 Thread.print -l > dump-02.txt 2>&1
sleep 5
jcmd 2125 Thread.print -l > dump-03.txt 2>&1
~~~

Trên Windows PowerShell:

~~~powershell
jcmd 2125 Thread.print -l *> dump-01.txt
Start-Sleep -Seconds 5
jcmd 2125 Thread.print -l *> dump-02.txt
Start-Sleep -Seconds 5
jcmd 2125 Thread.print -l *> dump-03.txt
~~~

Khi so sánh, tập trung vào:

- Thread có cùng tên/thread ID nhưng stack frame không đổi qua nhiều snapshot.
- Thread liên tục ở `BLOCKED` và cùng chờ một monitor.
- Thread pool có số lượng worker bị block tăng dần.
- Thread `RUNNABLE` xuất hiện ở cùng method qua nhiều snapshot trong lúc CPU cao.
- Thread chờ một dependency mà không có thread nào xử lý kết quả tương ứng.

Nếu thread di chuyển qua nhiều stack frame, nó có thể vẫn đang tiến triển. Nếu thread đứng nguyên ở một stack frame trong nhiều snapshot, cần kiểm tra lock, I/O và điều kiện chờ. Dữ liệu dump nên được đối chiếu với log, metrics và trace của ứng dụng.

## 9. Thực hành Java 17+: tạo deadlock và các trạng thái thread

Ví dụ sau tạo bốn thread dễ nhận diện trong thread dump:

- `demo-deadlock-A` giữ `LOCK_A` rồi chờ `LOCK_B`.
- `demo-deadlock-B` giữ `LOCK_B` rồi chờ `LOCK_A`.
- `demo-waiting` chờ một `CountDownLatch` không được mở.
- `demo-sleeping` ngủ trong một khoảng thời gian dài.

Tệp `ThreadDumpFixture.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class ThreadDumpFixture {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothOwnFirstLock = new CountDownLatch(2);

        Thread first = new Thread(() -> {
            synchronized (LOCK_A) {
                bothOwnFirstLock.countDown();
                await(bothOwnFirstLock);
                synchronized (LOCK_B) { }
            }
        }, "demo-deadlock-A");

        Thread second = new Thread(() -> {
            synchronized (LOCK_B) {
                bothOwnFirstLock.countDown();
                await(bothOwnFirstLock);
                synchronized (LOCK_A) { }
            }
        }, "demo-deadlock-B");

        Thread waiting = new Thread(() -> {
            try {
                new CountDownLatch(1).await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-waiting");

        Thread sleeping = new Thread(() -> {
            try {
                Thread.sleep(600_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "demo-sleeping");

        first.start();
        second.start();
        waiting.start();
        sleeping.start();

        System.out.println("ThreadDumpFixture ready");
        new CountDownLatch(1).await();
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }
}
~~~

Biên dịch và chạy ở terminal thứ nhất:

~~~bash
javac --release 17 ThreadDumpFixture.java
java ThreadDumpFixture
~~~

Stdout chính xác:

~~~text
ThreadDumpFixture ready
~~~

Chương trình được thiết kế để tiếp tục chạy cho tới khi bạn dừng process. Đây là fixture học tập; không dùng logic deadlock này trong ứng dụng thật.

### 9.1. Lấy dump bằng jstack

Ở terminal thứ hai, thay `12345` bằng PID thực tế của fixture:

~~~bash
jstack -l 12345 > fixture-jstack.txt 2>&1
~~~

Tìm các tên thread:

~~~text
demo-deadlock-A
demo-deadlock-B
demo-waiting
demo-sleeping
Found one Java-level deadlock
~~~

Hai thread deadlock sẽ có trạng thái `BLOCKED`. Thread chờ latch ở `WAITING`, còn thread ngủ ở `TIMED_WAITING`.

### 9.2. Lấy dump bằng jcmd

~~~bash
jcmd 12345 Thread.print -l > fixture-jcmd.txt 2>&1
~~~

Có thể thêm thông tin mở rộng:

~~~bash
jcmd 12345 Thread.print -e -l > fixture-jcmd-extended.txt 2>&1
~~~

Trong JDK có hỗ trợ `Thread.dump_to_file`, có thể lưu JSON:

~~~bash
jcmd 12345 Thread.dump_to_file -format=json fixture-threads.json
~~~

JDK 21 không liệt kê `Thread.dump_to_file` trong tài liệu command reference của nó; command này có trong tài liệu JDK 22 trở lên. Luôn kiểm tra `jcmd 12345 help Thread.dump_to_file` trên JVM đích trước khi dùng.

Dừng fixture bằng `Ctrl+C` ở terminal thứ nhất sau khi đã thu thập dump.

## 10. Chọn công cụ theo tình huống

| Nhu cầu | Công cụ nên dùng |
|---|---|
| Lấy một snapshot nhanh từ JVM đang chạy | `jcmd <pid> Thread.print` |
| Điều tra lock contention | `jcmd <pid> Thread.print -l` |
| Cần output mở rộng | `jcmd <pid> Thread.print -e` nếu target hỗ trợ |
| Ghi dump ra file plain/JSON | `Thread.dump_to_file` nếu target JDK cung cấp |
| Đọc runbook hoặc script cũ | `jstack <pid>` / `jstack -l <pid>` |
| Phân tích core dump sau crash | `jhsdb jstack` |
| Theo dõi sự kiện theo thời gian, latency hoặc lock profile | JFR và JDK Mission Control |

### 10.1. Phân tích core dump bằng jhsdb jstack

Nếu JVM đã crash và có core dump, `jstack` thông thường không phải cách xử lý chính. Dùng Serviceability Agent:

~~~bash
jhsdb jstack --exe /opt/jdk-21/bin/java --core /var/crash/core.12345
~~~

Để in cả native stack frame:

~~~bash
jhsdb jstack --mixed --pid 12345
~~~

`--mixed` thuộc `jhsdb jstack`, không phải tùy chọn thông thường của `jstack`. Với core dump, executable cần khớp binary đã tạo ra core. Phân tích postmortem có yêu cầu hệ điều hành và debugger riêng; cần dùng đúng JDK và kiến trúc.

## 11. Quyền truy cập, phiên bản và giới hạn

### 11.1. Attach cần đúng host và user

`jcmd` phải chạy trên cùng máy với JVM và cùng effective user/group identifiers theo tài liệu Oracle. Quyền hệ điều hành, container và Attach API cũng ảnh hưởng khả năng attach.

Nếu process được khởi chạy với `-XX:+DisableAttachMechanism`, các công cụ attach có thể không kết nối được. Trong container, PID hiển thị bên trong có thể khác PID trên host; chạy công cụ trong đúng namespace và dùng đúng PID.

### 11.2. Dùng tool phù hợp với JVM đích

Các công cụ chẩn đoán có thể thay đổi giữa JDK release và vendor. Oracle JDK 21 đánh dấu `jstack` là experimental/unsupported và ghi rõ công cụ có thể không còn trong bản JDK tương lai.

Nên:

- Dùng `jcmd` cho runbook và automation mới.
- Dùng `jstack` khi cần tương thích script cũ hoặc theo quy trình hiện hữu đã được kiểm thử.
- Kiểm tra `jstack -h` và `jcmd <pid> help Thread.print` trên đúng JDK.
- Dùng tool từ JDK phù hợp với JVM đích.
- Khi nâng JDK, kiểm tra lại option, output và parser của pipeline.

Trên Windows, nếu thiếu `dbgeng.dll`, tài liệu Oracle cho biết có thể cần cài Debugging Tools for Windows. `PATH` cần chứa vị trí `jvm.dll` của target process hoặc thư mục tương ứng với core dump.

### 11.3. Thread dump không phải CPU profiler

Thread dump cung cấp stack snapshot. Nó không đo chính xác CPU time của từng method, không lưu lịch sử event và không thể thay thế profiler.

Nếu CPU cao, so sánh nhiều dump và đối chiếu OS thread ID/CPU metrics. Nếu cần biết method nào chiếm thời gian, latency hoặc lock contention theo timeline, dùng JFR/JDK Mission Control hoặc profiler phù hợp.

## 12. Bảo vệ dữ liệu trong thread dump

Thread dump thường chứa tên thread, class/method, stack frame, lock identity, tên worker và thông tin môi trường. Tùy ứng dụng, thread name hoặc stack có thể để lộ customer ID, URL, tenant, tên queue hoặc thông tin nội bộ.

Một số quy tắc vận hành:

- Chỉ lưu dump vào thư mục có quyền đọc giới hạn.
- Không upload dump lên ticket hoặc kho công khai.
- Che dữ liệu nhạy cảm trước khi chia sẻ cho bên ngoài.
- Giới hạn số snapshot và thời gian lưu trữ.
- Gắn PID, hostname, thời điểm và phiên bản JDK vào tên file hoặc metadata.
- Khi thu thập trong production, ghi nhận người thực hiện và lý do lấy dump.

Thread dump thường nhẹ hơn heap dump, nhưng command vẫn có impact phụ thuộc số lượng thread và trạng thái JVM. Tránh chạy lặp quá dày trên một process đang quá tải.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `jstack` không tìm thấy PID | PID sai, process đã kết thúc hoặc namespace không khớp | Xác minh lại bằng `jcmd -l`/`ps` |
| `AttachNotSupportedException` | Attach API bị tắt hoặc runtime không hỗ trợ | Kiểm tra startup flag, JDK và runtime |
| `Operation not permitted` / access denied | User/group hoặc OS policy không cho attach | Chạy bằng account được phép và kiểm tra quyền |
| `jcmd` không thấy JVM trong Docker | JVM ở container/PID namespace riêng | Chạy `ps` và công cụ trong đúng container |
| `Unknown diagnostic command` | JVM đích không cung cấp command | Chạy `jcmd <pid> help` trên chính process |
| `Thread.dump_to_file` không tồn tại | JDK quá cũ hoặc vendor không cung cấp | Dùng redirect output của `Thread.print` |
| Không có deadlock nhưng app vẫn treo | Chờ I/O, notification, pool exhaustion hoặc lock bị giữ lâu | Phân tích stack của các thread chờ và lấy nhiều snapshot |
| Dump quá lớn | JVM có quá nhiều thread hoặc stack sâu | Lưu vào file, giới hạn số lần capture và kiểm tra đúng PID |
| File dump không tạo được | Working directory/quyền ghi/disk space sai | Dùng đường dẫn có quyền ghi và đủ dung lượng |
| Windows báo thiếu `dbgeng.dll` | Thiếu Debugging Tools for Windows | Cài thành phần debug và kiểm tra `PATH` |

## 14. Quy trình lấy và phân tích thread dump

1. Xác nhận triệu chứng và thời điểm xảy ra.
2. Xác định PID, main class, hostname/container và phiên bản JDK.
3. Kiểm tra `jcmd <pid> help Thread.print` để biết option có sẵn.
4. Lấy snapshot đầu tiên bằng `jcmd <pid> Thread.print -l`.
5. Nếu sự cố kéo dài, lấy thêm 2–3 snapshot cách nhau vài giây.
6. Tìm thread `BLOCKED`, `WAITING`, `TIMED_WAITING` và các thread `RUNNABLE` đáng chú ý.
7. Đối chiếu monitor/ownable synchronizer và deadlock report.
8. So sánh stack frame giữa các snapshot.
9. Liên hệ với log, metrics, request trace và trạng thái thread pool.
10. Lưu report đã lọc thông tin nhạy cảm và ghi lại kết luận cùng hành động xử lý.

## 15. Checklist trước khi kết luận

- [ ] Đúng PID và đúng JVM instance.
- [ ] Đúng JDK/tool version với target process.
- [ ] Có thread dump với lock details khi nghi ngờ lock contention.
- [ ] Đã xem deadlock section nếu JVM phát hiện.
- [ ] Đã phân biệt `BLOCKED`, `WAITING` và `TIMED_WAITING`.
- [ ] Đã xem stack frame của thread đang giữ lock và thread đang chờ.
- [ ] Đã lấy nhiều snapshot nếu cần xác định trạng thái kéo dài.
- [ ] Không kết luận deadlock chỉ từ một thread `BLOCKED`.
- [ ] Đã đối chiếu log, metrics và dependency bên ngoài.
- [ ] File dump được bảo vệ và có thời điểm/PID rõ ràng.

## 16. Ghi nhớ

`jstack` và `jcmd` đều có thể lấy thread dump từ JVM đang chạy. `jstack -l` là lệnh quen thuộc trong runbook cũ, nhưng Oracle đánh dấu `jstack` là experimental/unsupported và khuyến nghị dùng `jcmd` cho chẩn đoán mới.

Bắt đầu bằng `jcmd <pid> Thread.print`; thêm `-l` khi cần xem lock và `-e` khi cần thông tin mở rộng. Với JDK mới có `Thread.dump_to_file`, bạn có thể lưu dump dạng plain text hoặc JSON. Để tìm deadlock, theo dõi chu trình thread chờ lock; để điều tra hang, so sánh nhiều snapshot và đối chiếu với log/metrics. Nếu JVM đã crash, dùng `jhsdb jstack` để phân tích core dump.

Tài liệu tham khảo:

- [The jstack Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstack.html)
- [The jcmd Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Diagnostic Tools — Java SE 21](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — Java SE 22 (Thread.dump_to_file)](https://docs.oracle.com/en/java/javase/22/docs/specs/man/jcmd.html)
- [Troubleshooting Guide — Diagnose a Hung Process](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf)