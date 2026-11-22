# Chẩn đoán ứng dụng Java bằng `jcmd`

Bài này thuộc nhóm **Dự án thực hành** với đề bài **Chẩn đoán bằng jcmd**. `jcmd` là công cụ dòng lệnh của JDK dùng để gửi diagnostic command tới một JVM đang chạy trên cùng máy. Nó giúp lấy thông tin phiên bản và cấu hình JVM, thread dump, heap statistics, class histogram, Native Memory Tracking (NMT) và điều khiển Java Flight Recorder (JFR).

Bài thực hành dựng một ứng dụng Java nhỏ có thread đang ngủ, thread bị block khi lấy monitor và một lượng object được giữ trong heap. Sau đó dùng `jcmd` để tìm đúng process, kiểm tra trạng thái JVM, thu thập thread/heap snapshot, ghi JFR và đọc kết quả. Các lệnh đã được đối chiếu trên Zulu/OpenJDK 24.0.2 chạy Windows 11; source sample tương thích Java 17+.

## 1. Khi nào nên dùng `jcmd`?

Chọn `jcmd` khi cần hỏi một JVM đang chạy những câu hỏi cụ thể:

- Process này chạy JDK version, JVM vendor và command line nào?
- JVM được khởi động với heap size, GC hoặc VM flags nào?
- Thread nào đang RUNNABLE, BLOCKED, WAITING hay TIMED_WAITING?
- Thread nào đang giữ monitor mà thread khác đang chờ?
- Heap hiện có bao nhiêu vùng used/committed/reserved?
- Class nào có nhiều instance hoặc chiếm nhiều shallow bytes?
- JVM đang ghi nhận allocation, GC, lock contention hoặc execution sample như thế nào?
- Native memory của HotSpot được phân bổ vào heap, class metadata, thread stack, code cache và subsystem nào?

`jcmd` hữu ích vì một giao diện lệnh có thể gọi nhiều diagnostic command được JVM hỗ trợ. Nó không tự phân tích nguyên nhân gốc rễ. Người vận hành vẫn phải liên hệ output với workload, log, metrics, cấu hình và thời điểm xảy ra sự cố.

## 2. `jcmd` hoạt động như thế nào?

`jcmd` dùng cơ chế attach của JVM để gửi lệnh tới một Java process cục bộ. Cú pháp cơ bản:

~~~text
jcmd <pid | main-class> <command> [arguments]
~~~

Một số cách dùng:

~~~text
jcmd -l
jcmd 12345 help
jcmd 12345 VM.version
jcmd 12345 Thread.print -l
~~~

- `-l` liệt kê Java process cục bộ mà công cụ nhận diện được.
- `<pid>` là process ID của JVM đích.
- `<main-class>` có thể dùng để chọn process theo main class, nhưng PID thường rõ ràng hơn khi máy chạy nhiều instance.
- `help` liệt kê diagnostic command mà JVM đích hỗ trợ.
- `help <command>` hiển thị cú pháp, option và mức ảnh hưởng của command cụ thể.

Lệnh `jcmd help` không tương đương `jcmd <pid> help`: nếu thiếu PID, `jcmd` có thể hiểu `help` là tên main class cần tìm và trả lỗi không tìm thấy process.

`jcmd 0 <command>` gửi command tới tất cả JVM cục bộ được hỗ trợ. Chỉ dùng khi thực sự muốn tác động nhiều process; trong bài thực hành hãy chỉ định đúng một PID.

## 3. Điều kiện và quyền truy cập

Để attach thành công, cần lưu ý:

- JVM đích phải chạy trên cùng máy với `jcmd`; công cụ này không phải remote management client qua mạng.
- Người chạy `jcmd` thường cần cùng effective user và group với JVM đích.
- JVM phải cho phép attach. `-XX:+DisableAttachMechanism` vô hiệu hóa cơ chế này.
- Dùng JDK có `jcmd` trong thư mục `bin`; một runtime image tối giản có thể không chứa các công cụ chẩn đoán.
- Command và option phụ thuộc JDK/vendor/version. Luôn hỏi chính JVM đích bằng `jcmd <pid> help`.
- Trong container, chạy công cụ trong cùng container hoặc PID namespace phù hợp; PID nhìn từ host có thể khác PID bên trong container.
- PID có thể được hệ điều hành tái sử dụng sau khi process kết thúc. Hãy chạy `jcmd -l` lại trước khi chẩn đoán một process mới.

Nếu attach thất bại, không kết luận ngay ứng dụng đã chết. Kiểm tra process, user, container namespace, quyền truy cập, JVM flags và log của công cụ.

## 4. Quy trình chẩn đoán có thể lặp lại

Một quy trình thực tế thường đi theo thứ tự:

1. Xác định triệu chứng và khoảng thời gian xảy ra.
2. Tìm đúng Java process và ghi lại PID, command line, JDK version.
3. Thu thập thông tin JVM ít xâm lấn: version, flags, heap info.
4. Nếu nghi ngờ thread/lock, lấy thread dump; lặp lại sau vài giây để xem trạng thái có thay đổi không.
5. Nếu nghi ngờ memory, xem heap info và class histogram; chỉ tạo heap dump khi thực sự cần phân tích object graph.
6. Nếu cần hiểu hành vi theo thời gian, ghi JFR trong một khoảng ngắn và phân tích event.
7. Nếu nghi ngờ native memory, kiểm tra NMT khi JVM đã được bật tính năng này từ lúc khởi động.
8. Gắn mọi output với timestamp, PID, application version và workload tương ứng.

Một snapshot cho biết trạng thái tại một thời điểm. Nhiều snapshot cùng một workload giúp phân biệt trạng thái tạm thời với xu hướng kéo dài.

## 5. Tạo project thực hành

Tạo cấu trúc:

~~~text
jcmd-lab/
  src/
    com/
      example/
        diagnostics/
          JcmdLab.java
  out/
~~~

File `JcmdLab.java` tạo bốn dấu hiệu để quan sát:

- 48 mảng byte được giữ lại trong heap, tổng payload khoảng 3 MiB.
- `demo-sleeper` định kỳ ở trạng thái TIMED_WAITING.
- `demo-lock-owner` giữ một monitor trong lúc ngủ.
- `demo-lock-waiter` chờ monitor đó và xuất hiện ở trạng thái BLOCKED.

Lock owner tự nhả monitor sau 90 giây; đây là lock contention có thời hạn để thực hành, không phải deadlock vòng tròn.

## 6. Source code của ứng dụng mẫu

~~~java
package com.example.diagnostics;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public final class JcmdLab {
    private static final Object LOCK = new Object();
    private static final List<byte[]> RETAINED = new ArrayList<>();

    private JcmdLab() {
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 48; i++) {
            RETAINED.add(new byte[64 * 1024]);
        }

        System.out.println(
                "JCMD_LAB_READY pid=" + ProcessHandle.current().pid());
        System.out.println("RETAINED_ARRAYS=" + RETAINED.size());

        Thread sleeper = new Thread(() -> {
            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(1000);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-sleeper");
        sleeper.setDaemon(true);
        sleeper.start();

        CountDownLatch ownerReady = new CountDownLatch(1);
        Thread owner = new Thread(() -> {
            synchronized (LOCK) {
                ownerReady.countDown();
                try {
                    Thread.sleep(90_000);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-lock-owner");
        owner.setDaemon(true);
        owner.start();
        ownerReady.await();

        Thread waiter = new Thread(() -> {
            synchronized (LOCK) {
                System.out.println("WAITER_ACQUIRED_LOCK");
            }
        }, "demo-lock-waiter");
        waiter.setDaemon(true);
        waiter.start();

        Thread.sleep(120_000);
    }
}
~~~

`ProcessHandle.current().pid()` có từ Java 9. `CountDownLatch` bảo đảm lock owner đã lấy monitor trước khi waiter bắt đầu. `Thread.sleep()` bên trong khối `synchronized` giữ monitor trong thời gian ngủ, tạo tình huống BLOCKED có thể quan sát bằng thread dump.

## 7. Compile và chạy ứng dụng

Từ thư mục `jcmd-lab`, biên dịch cho Java 17:

Windows PowerShell:

~~~powershell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out src\com\example\diagnostics\JcmdLab.java
~~~

Linux/macOS:

~~~sh
javac --release 17 -encoding UTF-8 -Xlint:all -Werror -d out src/com/example/diagnostics/JcmdLab.java
~~~

Chạy ứng dụng với Native Memory Tracking ở chế độ summary:

Windows/Linux/macOS:

~~~text
java -XX:NativeMemoryTracking=summary -cp out com.example.diagnostics.JcmdLab
~~~

Output ban đầu có dạng:

~~~text
JCMD_LAB_READY pid=58340
RETAINED_ARRAYS=48
~~~

PID thực tế thay đổi theo máy. Giữ terminal này chạy và mở terminal thứ hai để thực hiện các lệnh `jcmd`. Ứng dụng mẫu tự kết thúc sau khoảng hai phút; có thể dừng sớm bằng Ctrl+C trong terminal chạy ứng dụng.

`-XX:NativeMemoryTracking=summary` phải được bật khi JVM khởi động. Nếu bỏ flag này, command `VM.native_memory` sẽ không có dữ liệu NMT để báo cáo.

## 8. Tìm đúng JVM process

Liệt kê process:

~~~text
jcmd -l
~~~

Ví dụ:

~~~text
58340 com.example.diagnostics.JcmdLab
~~~

Trên Windows PowerShell, có thể lọc process theo main class:

~~~powershell
jcmd -l | Select-String 'com.example.diagnostics.JcmdLab'
~~~

Sau khi xác định PID, lưu vào biến `$javaPid` để dùng cho các lệnh tiếp theo:

~~~powershell
$javaPid = 58340
jcmd $javaPid VM.version
~~~

PowerShell có biến tự động `$PID` chứa process ID của chính PowerShell. Dùng tên `$javaPid` để tránh ghi đè biến tự động đó.

Linux/macOS có thể lấy PID bằng:

~~~sh
JAVA_PID=$(jcmd -l | awk '/com.example.diagnostics.JcmdLab/ {print $1; exit}')
printf 'Target JVM PID: %s\n' "$JAVA_PID"
~~~

Nếu có nhiều instance cùng main class, đối chiếu command line, working directory hoặc service identity trước khi chọn PID. Không chạy diagnostic command lên PID chỉ vì nó là dòng đầu tiên trong danh sách.

## 9. Khám phá command mà JVM hỗ trợ

Liệt kê command:

~~~text
jcmd <pid> help
~~~

Xem chi tiết một command:

~~~text
jcmd <pid> help Thread.print
jcmd <pid> help GC.heap_dump
jcmd <pid> help JFR.start
~~~

Phần trợ giúp có thể cung cấp:

- Mô tả command.
- Cú pháp và option.
- Giá trị mặc định.
- Impact như Low, Medium hoặc High.
- Cảnh báo về pause, GC hoặc lượng dữ liệu có thể tạo.

Ví dụ trên JDK 24, `GC.heap_dump` được mô tả là High impact và có thể yêu cầu full GC; `JFR.check` và `JFR.dump` là Low impact. `JFR.start` có mức ảnh hưởng phụ thuộc settings đang dùng.

Đây là bước quan trọng trước khi chạy command trên production. Không giả định command có cùng option hoặc cùng mức impact trên mọi JDK.

## 10. Kiểm tra phiên bản, command line và VM flags

Xác nhận JVM version:

~~~text
jcmd <pid> VM.version
~~~

Xem command line dùng để khởi động process:

~~~text
jcmd <pid> VM.command_line
~~~

Xem VM flags hiện tại:

~~~text
jcmd <pid> VM.flags
~~~

Các thông tin này giúp xác định:

- JVM vendor/version.
- Main class hoặc JAR được chạy.
- Classpath/module path.
- Các `-X` và `-XX` flags.
- Heap sizing, GC collector và Native Memory Tracking configuration.

Có thể xem system properties:

~~~text
jcmd <pid> VM.system_properties
~~~

System properties và command-line arguments đôi khi chứa token, password, connection string hoặc đường dẫn nhạy cảm. Không dán nguyên output vào ticket/chat công khai; hãy lọc và che giá trị bí mật trước khi chia sẻ.

## 11. Lấy thread dump bằng `Thread.print`

Lấy thread dump có stack trace và thông tin lock:

~~~text
jcmd <pid> Thread.print -l
~~~

Có thể lưu output vào file:

Windows PowerShell:

~~~powershell
jcmd $javaPid Thread.print -l > thread-1.txt
~~~

Linux/macOS:

~~~sh
jcmd "$JAVA_PID" Thread.print -l > thread-1.txt 2>&1
~~~

`-l` yêu cầu in thông tin về các lock thuộc `java.util.concurrent` và synchronizer. `-e` yêu cầu extended thread information; xem `jcmd <pid> help Thread.print` để xác nhận option của JDK đang dùng.

Trong ứng dụng mẫu, tìm các thread:

~~~text
"demo-sleeper"
"demo-lock-owner"
"demo-lock-waiter"
~~~

Kết quả kiểm thử thực tế cho thấy:

~~~text
"demo-lock-waiter" ...
java.lang.Thread.State: BLOCKED (on object monitor)
- waiting to lock <...> (a java.lang.Object)
~~~

Thread owner ở trạng thái TIMED_WAITING vì đang ngủ trong khối `synchronized`. Thread waiter ở trạng thái BLOCKED vì đang chờ lấy monitor đó.

## 12. Đọc thread state và nhận diện deadlock

Các state thường gặp:

| State | Ý nghĩa | Cần điều tra khi |
|---|---|---|
| RUNNABLE | Thread đang chạy hoặc sẵn sàng chạy; có thể nằm trong native I/O | CPU cao kéo dài hoặc stack không tiến triển |
| BLOCKED | Thread chờ vào một intrinsic monitor (`synchronized`) | Nhiều thread cùng chờ một lock hoặc lock owner bị kẹt |
| WAITING | Thread chờ vô thời hạn một hành động từ thread khác | Có waiter không được signal/notify hoặc task không hoàn tất |
| TIMED_WAITING | Thread chờ có thời hạn, ví dụ `sleep`, `wait(timeout)` | Timeout lặp lại bất thường hoặc lịch chạy bị trễ |
| TERMINATED | Thread đã kết thúc | Task quan trọng kết thúc sớm hoặc không còn worker |

`RUNNABLE` không đồng nghĩa thread chắc chắn đang tiêu thụ CPU; thread có thể đang ở native call hoặc chờ I/O. Dùng JFR/OS metrics để hiểu CPU usage.

Một thread BLOCKED chưa đủ để kết luận deadlock. Trong ví dụ này, owner sẽ thức dậy và nhả monitor sau 90 giây, nên waiter có thể tiếp tục. Deadlock thực sự thường có chu trình phụ thuộc lock: thread A giữ lock X và đợi Y, trong khi thread B giữ Y và đợi X.

Hãy lấy ít nhất hai thread dump cách nhau vài giây:

~~~text
jcmd <pid> Thread.print -l
~~~

So sánh thread state, stack trace, monitor owner và vị trí chờ. Nếu cùng một thread lặp lại ở một stack mà không có tiến triển, hãy đối chiếu với log và workload. Thread dump thường có thông tin deadlock ở cuối output nếu JVM phát hiện được một Java-level deadlock.

## 13. Kiểm tra heap bằng `GC.heap_info`

Lấy snapshot heap:

~~~text
jcmd <pid> GC.heap_info
~~~

Ví dụ output rút gọn:

~~~text
garbage-first heap   total reserved 30932992K, committed 2113536K, used 14963K
region size 16384K, 1 young (16384K), 0 survivors (0K)
Metaspace       used 376K, committed 576K, reserved 1114112K
class space    used 27K, committed 128K, reserved 1048576K
~~~

Ý nghĩa:

- **used:** dung lượng đang được object/metadata sử dụng tại thời điểm lấy snapshot.
- **committed:** bộ nhớ JVM đã commit và có thể sử dụng.
- **reserved:** vùng địa chỉ JVM đã reserve.
- **Metaspace:** vùng lưu class metadata.
- **Class space:** phần metaspace dành cho compressed class pointers khi cấu hình JVM sử dụng.

Các con số thay đổi theo heap sizing, GC, class loading và workload. Một snapshot không chứng minh memory leak. Hãy so sánh nhiều lần trong cùng workload và kiểm tra sau các chu kỳ GC tự nhiên.

## 14. Xem class histogram bằng `GC.class_histogram`

Lệnh:

~~~text
jcmd <pid> GC.class_histogram
~~~

Output thường có các cột:

~~~text
num     #instances         #bytes  class name
------------------------------------------------
1:          8581        3526520  [B
2:          1716         212768  java.lang.Class
3:          8455         202920  java.lang.String
~~~

Histogram cho biết số instance và tổng shallow bytes theo class. Nó giúp tìm loại object có số lượng hoặc dung lượng lớn.

Trong ví dụ, 48 mảng `byte[]` được giữ lại nên class `[B` xuất hiện trong histogram. Tên class `[B` là biểu diễn JVM của `byte[]`.

`#bytes` trong histogram không phải retained heap size. Nó không tính toàn bộ object graph mà một object giữ sống. Muốn tìm object nào giữ tham chiếu tới phần lớn heap, cần heap dump và công cụ phân tích dominator/retained set như Eclipse Memory Analyzer.

`GC.class_histogram` có thể có impact High tùy heap size và số object. Hạn chế chạy lặp liên tục trên production. Kiểm tra `jcmd <pid> help GC.class_histogram` trước khi dùng.

## 15. Heap dump bằng `GC.heap_dump`

Heap dump tạo file HPROF để phân tích object graph:

Windows:

~~~powershell
New-Item -ItemType Directory -Force C:\diagnostics | Out-Null
jcmd $javaPid GC.heap_dump C:\diagnostics\heap.hprof
~~~

Linux:

~~~sh
mkdir -p /var/tmp/jvm-diagnostics
jcmd "$JAVA_PID" GC.heap_dump /var/tmp/jvm-diagnostics/heap.hprof
~~~

Theo command help của JDK 24, heap dump có impact High và mặc định yêu cầu full GC, trừ khi dùng option `-all`. Có thể yêu cầu nén:

~~~text
jcmd <pid> GC.heap_dump -gz=1 C:\diagnostics\heap.hprof.gz
~~~

Dùng `-all` khi muốn bao gồm cả object unreachable:

~~~text
jcmd <pid> GC.heap_dump -all C:\diagnostics\heap-all.hprof
~~~

Heap dump có thể lớn bằng phần đáng kể của heap và gây pause. Hãy kiểm tra dung lượng đĩa, quyền ghi và thời điểm phù hợp trước khi tạo.

Heap dump có thể chứa token, session, password, request payload, dữ liệu người dùng và nội dung nhạy cảm đang nằm trong memory. Bảo vệ file như dữ liệu production; giới hạn người truy cập, không gửi công khai và xóa theo retention policy. Bài thực hành này không tạo heap dump vì đây là command có tác động cao; cú pháp được kiểm tra bằng trợ giúp của JVM.

## 16. Ghi JFR từ một JVM đang chạy

Java Flight Recorder ghi event trong một khoảng thời gian. Có thể khởi động recording mà không restart ứng dụng:

~~~text
jcmd <pid> JFR.start name=diagnostic settings=default duration=30s filename=diagnostic.jfr
~~~

- `name=diagnostic` đặt tên recording.
- `settings=default` dùng cấu hình có sẵn với overhead thấp.
- `duration=30s` tự dừng recording sau 30 giây.
- `filename=diagnostic.jfr` chỉ định file output.

Kiểm tra recording đang chạy:

~~~text
jcmd <pid> JFR.check name=diagnostic
~~~

Output khi recording còn hoạt động có dạng:

~~~text
Recording 1: name=diagnostic duration=30s (running)
~~~

Khi thời lượng kết thúc, JVM ghi file theo cấu hình recording. Nếu chạy `JFR.check` sau khi recording đã kết thúc, có thể nhận `No available recordings`; điều này không có nghĩa file đã ghi bị mất. Hãy kiểm tra file và đọc bằng `jfr summary`.

Khi cần nhiều event hơn để điều tra trong một khoảng ngắn, có thể dùng:

~~~text
jcmd <pid> JFR.start name=profiled settings=profile duration=15s filename=profiled.jfr
~~~

`profile` thu thập nhiều dữ liệu hơn `default` và có overhead cao hơn. Chỉ dùng trong khoảng thời gian ngắn, phù hợp với workload và khả năng chịu tải của ứng dụng.

## 17. Dump hoặc dừng recording thủ công

Nếu cần ghi recording liên tục và chủ động chụp một khoảng dữ liệu:

~~~text
jcmd <pid> JFR.start name=rolling settings=default maxage=15m maxsize=250M
~~~

Khi cần lấy snapshot:

~~~text
jcmd <pid> JFR.dump name=rolling filename=incident.jfr
~~~

Sau khi hoàn tất:

~~~text
jcmd <pid> JFR.stop name=rolling
~~~

`JFR.dump` sao chép nội dung recording ra file; `JFR.stop` kết thúc recording. Nếu dùng `duration` và `filename` ngay từ `JFR.start`, thường không cần dump/stop thủ công.

Có thể yêu cầu đường dẫn GC roots:

~~~text
jcmd <pid> JFR.dump name=rolling filename=leak-investigation.jfr path-to-gc-roots=true
~~~

Thu thập GC root paths có thể làm ứng dụng pause và tốn thời gian. Chỉ bật khi đang điều tra nghi ngờ memory leak; không dùng mặc định cho recording thường ngày.

## 18. Phân tích file JFR bằng `jfr`

Xem tổng quan recording:

~~~text
jfr summary diagnostic.jfr
~~~

Xem một số event:

~~~text
jfr print --events jdk.ExecutionSample,jdk.GarbageCollection diagnostic.jfr
~~~

Có thể lọc thêm event lock contention khi recording có thu thập event đó:

~~~text
jfr print --events jdk.JavaMonitorEnter diagnostic.jfr
~~~

`jfr summary` hiển thị thời lượng, số chunk và số lượng event theo loại. `jfr print` xuất nội dung event phù hợp với bộ lọc.

Event thực tế phụ thuộc settings, workload và thời điểm recording. Nếu không có `jdk.ExecutionSample` trong một recording ngắn, có thể khoảng thời gian đó không có thread CPU activity đáng kể hoặc sampling không ghi được event phù hợp. Hãy ghi lại trong workload đại diện và kiểm tra event settings trước khi kết luận.

JFR recording có thể chứa thread name, class name, command line và event payload. Bảo vệ file `.jfr` theo quyền truy cập phù hợp, nhất là khi lấy từ production.

Java Mission Control (JMC) cung cấp giao diện để lọc event, xem thread timeline, allocation, GC và execution samples. JMC có thể cần cài riêng; file `.jfr` có thể được đọc bằng CLI `jfr` ngay trong JDK.

## 19. Native Memory Tracking với `VM.native_memory`

Heap chỉ là một phần bộ nhớ process. JVM còn dùng native memory cho thread stack, code cache, class metadata, GC structures và các subsystem khác.

Để bật NMT, khởi động JVM với:

~~~text
-XX:NativeMemoryTracking=summary
~~~

Hoặc dùng `detail` khi cần thông tin allocation call site chi tiết hơn và chấp nhận overhead bổ sung. Không thể bật NMT hồi tố bằng `jcmd` sau khi JVM đã khởi động.

Lấy summary:

~~~text
jcmd <pid> VM.native_memory summary
~~~

Tạo baseline:

~~~text
jcmd <pid> VM.native_memory baseline
~~~

Sau một khoảng workload, so sánh:

~~~text
jcmd <pid> VM.native_memory summary.diff
~~~

NMT phân loại reserved/committed native memory theo subsystem. Nó hữu ích khi RSS tăng nhưng Java heap không tăng tương ứng. NMT tập trung vào allocation mà HotSpot theo dõi; nó không bảo đảm bao quát mọi allocation của thư viện native bên thứ ba hoặc mọi bộ nhớ do hệ điều hành quản lý.

Nếu JVM không được khởi động với NMT, command sẽ báo tracking chưa được bật. Cần bật flag và khởi động lại process trong lần chạy tiếp theo để có dữ liệu.

## 20. Chọn command theo mức độ ảnh hưởng

Impact được JVM công bố trong `jcmd <pid> help <command>`. Trên JDK 24, một số command có phân loại:

| Command | Impact/cách dùng theo help JDK 24 | Mục đích |
|---|---|---|
| `VM.version` | Đọc metadata JVM | Xác nhận JVM version |
| `VM.command_line` | Đọc metadata JVM | Xem startup arguments |
| `VM.flags` | Đọc metadata JVM | Xem VM flags |
| `Thread.print` | Medium, phụ thuộc số thread | Thread dump |
| `GC.heap_info` | Medium | Heap snapshot |
| `GC.class_histogram` | High, phụ thuộc heap/object count | Histogram |
| `GC.heap_dump` | High | HPROF heap dump; mặc định yêu cầu full GC |
| `VM.native_memory` | Medium | NMT summary/detail |
| `JFR.check` | Low | Kiểm tra recording |
| `JFR.dump` | Low | Xuất recording |
| `JFR.start` | Medium; phụ thuộc settings | Bắt đầu recording |

Bảng này là hướng dẫn cho JDK 24; luôn kiểm tra help trên JVM thực tế. Với command có impact cao, cân nhắc thời điểm, heap size, disk capacity, pause tolerance và mức độ nhạy cảm của dữ liệu.

## 21. Lưu kết quả và so sánh theo thời gian

Một lần chẩn đoán nên có thư mục riêng:

~~~text
diagnostics/
  incident-2026-11-10/
    environment.txt
    vm-version.txt
    vm-flags.txt
    thread-1.txt
    thread-2.txt
    heap-info.txt
    class-histogram.txt
    recording.jfr
    jfr-summary.txt
~~~

Ghi lại:

- Timestamp và timezone.
- PID và main class.
- Application version/build identifier.
- JDK vendor/version.
- Command đã chạy và option.
- Triệu chứng đang quan sát.
- Workload hoặc request rate trong thời gian thu thập.
- Kết quả trước/sau khi thay đổi cấu hình.

Không so sánh hai heap snapshot nếu workload hoặc thời điểm GC hoàn toàn khác nhau mà không ghi rõ bối cảnh. Với thread dump, so sánh stack và lock owner. Với histogram, xem class count/shallow bytes có tăng liên tục không. Với JFR, xem event trong cùng cửa sổ thời gian của incident.

## 22. Troubleshooting khi `jcmd` không hoạt động

### Không tìm thấy process

**Nguyên nhân:** process đã kết thúc, chạy dưới user khác, nằm trong container/PID namespace khác hoặc `jcmd -l` không nhìn thấy nó.

**Cách xử lý:** kiểm tra process bằng công cụ hệ điều hành, chạy `jcmd -l` từ đúng host/container và xác nhận PID mới.

### `AttachNotSupportedException` hoặc attach thất bại

**Nguyên nhân:** user/group không khớp, attach bị disable, JVM chưa hỗ trợ attach trong môi trường đó hoặc thư mục attach tạm không truy cập được.

**Cách xử lý:** chạy dưới đúng user, kiểm tra `-XX:+DisableAttachMechanism`, container namespace và quyền truy cập filesystem.

### `Unknown diagnostic command`

**Nguyên nhân:** command không tồn tại trong JDK/vendor/version của JVM đích.

**Cách xử lý:** chạy `jcmd <pid> help`, rồi `jcmd <pid> help <command>` để xem tên và cú pháp được hỗ trợ.

### `VM.native_memory` báo chưa bật

**Nguyên nhân:** JVM không được khởi động với `-XX:NativeMemoryTracking=summary` hoặc `detail`.

**Cách xử lý:** thêm flag lúc launch và khởi động lại process theo kế hoạch triển khai; không thể bật tracking sau khi JVM đã chạy.

### JFR file chưa xuất hiện

**Nguyên nhân:** recording đang chạy, path tương đối trỏ vào working directory của process đích hoặc recording chưa được dump/stop.

**Cách xử lý:** kiểm tra `JFR.check`, dùng path tuyệt đối, chờ `duration` kết thúc hoặc chạy `JFR.dump` rồi kiểm tra file.

### Heap dump hết dung lượng hoặc không ghi được

**Nguyên nhân:** heap dump lớn, thư mục không đủ disk hoặc user chạy JVM không có quyền ghi.

**Cách xử lý:** chọn filesystem đủ dung lượng, kiểm tra quyền và chỉ tạo dump khi có kế hoạch lưu trữ/phân tích phù hợp. Không đổi đường dẫn sang thư mục public chỉ để né lỗi permission.

### Output quá dài

**Nguyên nhân:** JVM có nhiều thread/class hoặc `VM.system_properties` chứa nhiều giá trị.

**Cách xử lý:** redirect ra file, lọc theo thread/class cần tìm và che dữ liệu nhạy cảm trước khi chia sẻ.

## 23. Khi nào chọn công cụ khác?

`jcmd` là điểm bắt đầu tốt cho nhiều câu hỏi về một HotSpot JVM, nhưng một số công cụ bổ sung thông tin chuyên biệt:

| Công cụ | Chọn khi |
|---|---|
| `jps` | Chỉ cần liệt kê Java process |
| `jstack` | Cần thread dump bằng công cụ riêng |
| `jmap` | Cần heap histogram/dump theo workflow đang dùng |
| `jstat` | Cần theo dõi GC/heap statistics theo chu kỳ |
| `jconsole` | Cần GUI monitoring qua JMX |
| `jfr` | Cần đọc/phân tích recording |
| JMC | Cần phân tích JFR trực quan |
| Eclipse Memory Analyzer | Cần retained heap, dominator tree và object references |
| OS tools | Cần CPU/RSS/process I/O hoặc native process metrics |

Không nên chạy đồng thời nhiều công cụ lấy cùng một loại snapshot nếu chúng có thể gây pause hoặc tải thêm lên JVM. Hãy chọn output trả lời đúng câu hỏi đang điều tra.

## 24. Bài tập thực hành

Sau khi chạy `JcmdLab`, thực hiện các bài tập:

1. Dùng `jcmd -l` tìm PID và xác nhận bằng `VM.version`.
2. Dùng `VM.command_line` để kiểm tra `-XX:NativeMemoryTracking=summary`.
3. Chạy `Thread.print -l` và tìm `demo-lock-waiter`. Xác định monitor mà nó đang chờ.
4. Lấy thread dump lần hai sau 10 giây. So sánh waiter còn BLOCKED hay không.
5. Chạy `GC.heap_info` và ghi lại used/committed/reserved.
6. Chạy `GC.class_histogram`, tìm `[B` và đối chiếu với 48 mảng byte trong source.
7. Chạy `VM.native_memory summary`, sau đó baseline và summary.diff.
8. Ghi JFR 20 giây bằng `settings=default`, rồi chạy `jfr summary`.
9. Dùng `jfr print` lọc `jdk.ExecutionSample` và `jdk.GarbageCollection`.
10. Giải thích vì sao heap histogram không cho biết object nào giữ sống phần lớn heap.
11. Giải thích vì sao `demo-lock-waiter` BLOCKED chưa phải deadlock.
12. Thử `jcmd <pid> help GC.heap_dump` và liệt kê rủi ro trước khi thực hiện heap dump.

Khi kết thúc, dừng ứng dụng mẫu bằng Ctrl+C ở terminal chạy Java. Xóa các file diagnostic của lab nếu không còn cần dùng; không xóa file incident production trước khi hết thời hạn lưu trữ.

## 25. Checklist chẩn đoán an toàn

- [ ] Đã xác định đúng host/container, PID và main class.
- [ ] Đã xác nhận JVM version và command line.
- [ ] Đã xem `jcmd <pid> help` trước khi dùng command lạ.
- [ ] Đã bắt đầu bằng metadata và snapshot có impact thấp hơn.
- [ ] Thread dump được so sánh qua nhiều thời điểm khi cần.
- [ ] BLOCKED/WAITING được phân biệt với deadlock thực sự.
- [ ] Heap info và histogram được hiểu đúng giới hạn.
- [ ] Heap dump chỉ được tạo khi có lý do, dung lượng và nơi lưu phù hợp.
- [ ] JFR settings và duration được chọn theo mục tiêu.
- [ ] Native Memory Tracking đã bật từ lúc JVM khởi động.
- [ ] Output có timestamp, PID, JDK và application build.
- [ ] Command line, properties, JFR và heap dump được rà soát dữ liệu nhạy cảm.
- [ ] File diagnostic được lưu và chia sẻ theo đúng quyền truy cập.
- [ ] Không dùng PID cũ sau khi process restart.

## 26. Tài liệu tham khảo

- Oracle JDK 24 — `jcmd`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Oracle JDK 24 — `jfr`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html
- Oracle JDK 24 — `jps`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jps.html
- Oracle JDK 24 — `jstack`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstack.html
- Oracle JDK 24 — `jmap`: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmap.html
- Oracle JDK 24 — Java Flight Recorder: https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-api-programmers-guide.pdf
- Oracle Java Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- OpenJDK — Java Mission Control: https://openjdk.org/projects/jmc/
- Eclipse Memory Analyzer: https://eclipse.dev/mat/

`jcmd` giúp biến một JVM đang chạy thành nguồn bằng chứng có thể kiểm tra: process metadata cho biết nó được khởi động ra sao, thread dump cho biết thread đang chờ ở đâu, heap/NMT cho biết bộ nhớ được sử dụng thế nào và JFR cho biết hoạt động diễn ra trong một khoảng thời gian. Chọn command theo câu hỏi, kiểm tra impact trước khi chạy và so sánh nhiều snapshot để đưa ra kết luận có căn cứ.