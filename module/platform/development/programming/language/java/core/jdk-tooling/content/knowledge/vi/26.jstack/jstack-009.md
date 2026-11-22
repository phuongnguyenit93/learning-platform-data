# Cách đọc thread dump trong Java

Thread dump là ảnh chụp stack trace và trạng thái của các thread trong một tiến trình JVM tại một thời điểm. Nó giúp điều tra ứng dụng bị treo, phản hồi chậm, deadlock, tranh chấp lock, thread pool cạn worker hoặc nhiều thread chờ I/O.

Trong JDK 17, có thể lấy thread dump bằng `jstack`, `jcmd` hoặc cơ chế Control+Break của JVM. Bài này tập trung vào cách đọc từng phần của dump: thread header, trạng thái, stack frame, monitor, ownable synchronizer và quan hệ giữa thread đang chờ với thread đang giữ lock. Phần thực hành tạo một deadlock có thể tái hiện để bạn đối chiếu output.

> **Khuyến nghị công cụ:** Oracle đánh dấu `jstack` là công cụ experimental. Với chẩn đoán mới, Oracle khuyến nghị `jcmd`; lệnh tương ứng là `jcmd PID Thread.print -l`.

## 1. Thread dump là gì?

Một thread dump là bản ghi trạng thái của các thread mà JVM nhìn thấy tại thời điểm yêu cầu. Nó thường chứa:

- Tên thread và một số thông tin định danh.
- Thread là daemon hay non-daemon.
- Trạng thái Java hiện tại, ví dụ `RUNNABLE`, `BLOCKED` hoặc `WAITING`.
- Stack trace từ frame hiện tại ngược về các lời gọi trước đó.
- Monitor lock mà thread đang giữ hoặc đang chờ.
- Thông tin về các lock thuộc `java.util.concurrent`, nếu bật chế độ hiển thị lock.
- Phần chẩn đoán deadlock nếu JVM phát hiện chu trình khóa.

Thread dump là snapshot, không phải bản ghi lịch sử. Nó cho biết thread đang ở đâu lúc chụp, nhưng một snapshot đơn lẻ thường không đủ để kết luận nguyên nhân của sự cố. Để nhận biết thread bị kẹt lâu, hãy so sánh nhiều dump được chụp cách nhau vài giây.

Việc tạo thread dump không tự kết thúc ứng dụng. JVM tiếp tục chạy sau khi in thông tin thread.

## 2. Tìm PID của JVM

Trước tiên, xác định đúng tiến trình Java cần điều tra:

~~~powershell
jps -lv
~~~

Ví dụ output:

~~~text
8120 com.example.ThreadDumpDeadlockDemo
9204 org.apache.catalina.startup.Bootstrap
10440 jdk.jcmd/sun.tools.jps.Jps
~~~

Trong ví dụ, PID của ứng dụng là `8120`. Có thể dùng `jcmd -l` để liệt kê các JVM mà công cụ nhận diện:

~~~powershell
jcmd -l
~~~

Lưu ý:

- Thực hiện trên cùng máy với JVM đích.
- Dùng tài khoản có quyền attach phù hợp với tài khoản đã chạy JVM.
- Với Docker/container, cần kiểm tra PID trong đúng container hoặc PID namespace.
- Nếu ứng dụng chạy bằng service, hãy tìm PID của service JVM, không nhầm với PID của wrapper hoặc shell script.

## 3. Lấy thread dump bằng jstack

Lệnh cơ bản:

~~~powershell
jstack 8120
~~~

Để có thêm thông tin về lock:

~~~powershell
jstack -l 8120
~~~

Tùy chọn `-l` yêu cầu công cụ tìm và in thêm thông tin về ownable synchronizers, bao gồm các lock thuộc `java.util.concurrent.locks`. Không có `-l`, output chủ yếu thể hiện thông tin monitor của Java.

Lưu ra file để phân tích:

~~~powershell
jstack -l 8120 > thread-dump.txt
~~~

Trên Linux/macOS, có thể dùng đường dẫn tương ứng:

~~~bash
jstack -l 8120 > thread-dump.txt
~~~

Nếu không có `jstack` trong PATH, gọi trực tiếp từ thư mục `bin` của JDK. JRE/runtime tối giản có thể không cài các công cụ chẩn đoán của JDK.

## 4. Dùng jcmd để lấy thread dump

Với JDK 17, đây là cách được Oracle khuyến nghị cho chẩn đoán JVM mới:

~~~powershell
jcmd 8120 Thread.print
~~~

Để in thêm thông tin lock:

~~~powershell
jcmd 8120 Thread.print -l
~~~

Có thể yêu cầu thêm thông tin thread mở rộng nếu JVM hỗ trợ:

~~~powershell
jcmd 8120 Thread.print -e
~~~

Xem các tùy chọn mà tiến trình đích hỗ trợ:

~~~powershell
jcmd 8120 help Thread.print
~~~

Lưu output:

~~~powershell
jcmd 8120 Thread.print -l > thread-dump.txt
~~~

`Thread.print -l` có vai trò tương đương với `jstack -l` trong trường hợp đọc lock. Tùy chọn `-e` của `Thread.print` yêu cầu thông tin thread mở rộng; hãy kiểm tra help của đúng JVM trước khi dùng.

## 5. Lấy dump bằng Control+Break hoặc tín hiệu hệ điều hành

Ngoài công cụ attach, HotSpot JVM hỗ trợ cơ chế Control+Break:

| Nền tảng | Cách yêu cầu dump | Nơi xuất output |
|---|---|---|
| Linux | `kill -QUIT PID` hoặc `kill -3 PID` | Standard output của tiến trình Java |
| Linux terminal | Ctrl + backslash tại console ứng dụng | Standard output của tiến trình |
| Windows console | Ctrl + Break tại cửa sổ chạy Java | Console hoặc log được redirect |
| Mọi nền tảng có attach phù hợp | `jcmd PID Thread.print -l` | Terminal chạy lệnh |

Ví dụ trên Linux:

~~~bash
kill -QUIT 8120
~~~

Tín hiệu `SIGQUIT` yêu cầu JVM in thread dump; nó không tương đương `kill -9` và không phải lệnh kết thúc tiến trình. `kill -3 PID` gửi cùng tín hiệu trên Linux. Hãy kiểm tra log của ứng dụng nếu standard output được chuyển hướng vào file hoặc hệ thống log.

Trên Windows, dùng Ctrl+Break khi có console phù hợp. Ctrl+C thường gửi yêu cầu ngắt chương trình và có thể làm ứng dụng kết thúc; đừng nhầm Ctrl+C với Ctrl+Break.

Nếu JVM được chạy với `-Xrs`, cơ chế xử lý tín hiệu/console của JVM bị giảm hoặc tắt; thread dump qua SIGQUIT trên Linux và Ctrl+Break trên Windows có thể không khả dụng. Trong trường hợp đó, dùng `jcmd` nếu attach được.

## 6. Cấu trúc tổng quát của một thread dump

Một dump thường có phần mở đầu, nhiều thread entry và có thể có phần deadlock ở cuối.

Ví dụ rút gọn:

~~~text
2026-11-10 10:15:30
Full thread dump Java HotSpot(TM) 64-Bit Server VM (17.0.x mixed mode):

"main" #1 prio=5 os_prio=0 tid=0x000001 nid=0x100 waiting on condition
   java.lang.Thread.State: WAITING
        at java.lang.Object.wait(Native Method)
        at java.lang.Thread.join(Thread.java:...)
        at com.example.Main.main(Main.java:20)

"worker-1" #31 daemon prio=5 os_prio=0 tid=0x000002 nid=0x201 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Service.update(Service.java:42)
        - waiting to lock <0x00000001> (a java.lang.Object)
        - locked <0x00000002> (a java.lang.Object)

"worker-2" #32 daemon prio=5 os_prio=0 tid=0x000003 nid=0x202 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.Service.refresh(Service.java:58)
        - waiting to lock <0x00000002> (a java.lang.Object)
        - locked <0x00000001> (a java.lang.Object)
~~~

Đây là ví dụ minh họa cấu trúc, không phải output cố định của mọi JVM. Tên trường, số định danh, line number và phần mở rộng có thể khác theo JDK, hệ điều hành và loại VM.

Các thread Java thường được in trước, tiếp theo là các thread nội bộ của VM. Mỗi entry thường có header, trạng thái Java, stack frame và thông tin lock nếu có.

## 7. Đọc thread header

Một header HotSpot có thể có dạng:

~~~text
"worker-1" #31 daemon prio=5 os_prio=0 tid=0x000002 nid=0x201 waiting for monitor entry
~~~

Ý nghĩa các trường phổ biến:

| Trường | Ý nghĩa |
|---|---|
| `"worker-1"` | Tên thread do ứng dụng hoặc runtime đặt |
| `#31` | Số định danh Java thread trong output |
| `daemon` | Thread daemon; JVM không chờ riêng thread daemon để giữ tiến trình sống |
| `prio=5` | Java thread priority |
| `os_prio=0` | Priority theo cách ánh xạ của hệ điều hành, nếu có |
| `tid=...` | Định danh/cấu trúc thread ở phía VM |
| `nid=...` | Native thread ID do hệ điều hành cấp |
| `waiting for monitor entry` | Gợi ý trạng thái đang chờ lấy monitor |

Không nên xem `tid`, `nid` hoặc các giá trị dạng địa chỉ là ID ổn định qua nhiều lần dump hay nhiều lần khởi chạy. Chúng hữu ích để đối chiếu trong cùng snapshot và khi kết hợp với công cụ hệ điều hành.

Tên thread thường là dấu hiệu rất hữu ích. Ví dụ `http-nio-8080-exec-12` có thể là worker xử lý request HTTP; `pool-3-thread-2` có thể thuộc một executor; `scheduler-1` có thể là thread lập lịch. Tên thực tế phụ thuộc framework và cách ứng dụng đặt tên.

## 8. Đọc Java thread state

Dòng trạng thái thường có dạng:

~~~text
java.lang.Thread.State: BLOCKED (on object monitor)
~~~

Các trạng thái trong Java:

| Trạng thái | Ý nghĩa | Dấu hiệu thường gặp |
|---|---|---|
| `NEW` | Thread đã được tạo nhưng chưa start | Thường không xuất hiện trong dump của thread đang chạy |
| `RUNNABLE` | Thread đang thực thi hoặc sẵn sàng được hệ điều hành cấp CPU | Stack có thể nằm trong code ứng dụng hoặc native call |
| `BLOCKED` | Đang chờ lấy intrinsic monitor để vào synchronized block/method | `waiting to lock` |
| `WAITING` | Chờ vô thời hạn một hành động từ thread khác | `Object.wait()`, `Thread.join()` không timeout, `LockSupport.park()` |
| `TIMED_WAITING` | Chờ có thời hạn | `Thread.sleep()`, `wait(timeout)`, `join(timeout)`, `parkNanos()` |
| `TERMINATED` | Thread đã kết thúc | Thường không còn là thread sống trong snapshot |

### 8.1. RUNNABLE không đồng nghĩa CPU luôn ở mức cao

`RUNNABLE` là trạng thái Java. Thread có thể đang chạy trên CPU, đang sẵn sàng chạy hoặc đang ở một số native operation. Vì vậy, một thread `RUNNABLE` không tự chứng minh nó đang tiêu thụ CPU liên tục.

Muốn phát hiện vòng lặp CPU cao, chụp nhiều dump cách nhau vài giây và so sánh stack của cùng thread. Nếu thread vẫn `RUNNABLE` và liên tục xuất hiện ở cùng một đường code nóng, đó là manh mối để điều tra thêm bằng profiler hoặc Java Flight Recorder.

### 8.2. BLOCKED chỉ nói về monitor

`BLOCKED` có nghĩa thread đang chờ vào một monitor được bảo vệ bởi `synchronized`. Đây không phải tên chung cho mọi loại I/O hoặc mọi dạng chờ.

Một thread chờ `ReentrantLock`, `BlockingQueue`, `Future` hoặc `LockSupport.park()` thường hiển thị `WAITING` hoặc `TIMED_WAITING`, tùy API và timeout.

### 8.3. WAITING và TIMED_WAITING có thể là bình thường

Một thread pool rảnh có thể chờ tác vụ mới. Thread scheduler có thể ngủ giữa hai lần chạy. Thread đang gọi `Object.wait()` có thể đang chờ notification hợp lệ.

Không kết luận ứng dụng bị treo chỉ vì thấy nhiều `WAITING`. Hãy xem stack frame, thread name, quan hệ lock và việc trạng thái có thay đổi qua nhiều snapshot hay không.

## 9. Đọc stack frame

Một stack frame Java thường có dạng:

~~~text
at com.example.OrderService.submit(OrderService.java:84)
~~~

Đọc từ trên xuống:

1. Frame đầu gần vị trí thread đang thực hiện hoặc đang chờ nhất.
2. Các frame tiếp theo là chuỗi lời gọi ngược về caller.
3. Frame thấp hơn giúp lần ra luồng xử lý đã đưa thread tới vị trí hiện tại.

Các dạng đặc biệt:

- `Native Method`: frame thuộc native method hoặc không có line Java tương ứng.
- `Unknown Source`: runtime không có thông tin source/line cho frame.
- `Compiled Code`: một số output có thể biểu diễn frame đã biên dịch theo cách riêng.
- `...`: tài liệu hoặc ví dụ có thể rút gọn stack; dump thực tế có thể dài hơn.

Tìm frame đầu tiên thuộc package của ứng dụng. Những frame phía trên có thể là framework, thư viện hoặc JDK; frame ứng dụng thường giúp xác định method cần đọc trong source.

Nếu stack dừng ở `SocketDispatcher.read0`, `FileDispatcherImpl.read0` hoặc native I/O frame, thread có thể đang chờ I/O. Kiểm tra endpoint, timeout, kết nối và thread đang sở hữu công việc đó. Một thread chờ I/O chưa đủ để kết luận hệ thống bị deadlock.

## 10. Đọc monitor và thông tin lock

Khi một thread đang giữ hoặc chờ intrinsic monitor, dump có thể hiển thị:

~~~text
- waiting to lock <0x00000001> (a java.lang.Object)
- locked <0x00000002> (a java.lang.Object)
~~~

Ý nghĩa:

- `waiting to lock`: thread đang cố lấy monitor có ID tương ứng nhưng chưa lấy được.
- `locked`: thread đang giữ monitor đó tại thời điểm chụp.
- Cùng một ID monitor trong một dump giúp đối chiếu thread nào đang chờ và thread nào đang giữ lock.

Ví dụ, nếu thread A có `waiting to lock <0x01>` và thread B có `locked <0x01>`, thread B là ứng viên đang giữ monitor mà A cần. Tiếp tục kiểm tra stack của B để hiểu vì sao B chưa nhả lock hoặc đang chờ monitor khác.

### 10.1. waiting on khác waiting to lock

`waiting on <...>` thường liên quan đến `Object.wait()`. Khi gọi `wait()`, thread phải đang sở hữu monitor; lời gọi sẽ nhả monitor trong lúc chờ notification hoặc timeout, rồi cần lấy lại monitor trước khi tiếp tục.

`waiting to lock <...>` là đang chờ vào monitor của synchronized block/method.

Hai trạng thái này khác nhau về cơ chế và cách tìm thread cần điều tra.

### 10.2. Ownable synchronizer và ReentrantLock

Các cấu trúc như `ReentrantLock` dùng cơ chế synchronizer của `java.util.concurrent`, không chỉ là intrinsic monitor. Dùng `jstack -l` hoặc `jcmd PID Thread.print -l` để xem thêm thông tin ownable synchronizer.

Output minh họa:

~~~text
- parking to wait for <0x00000003> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
~~~

`parking to wait for` thường liên quan tới `LockSupport.park()` hoặc cơ chế chờ dựa trên AQS. Để hiểu ai đang giữ lock, xem phần ownable synchronizer được in trong dump dài và đối chiếu các thread khác.

## 11. Nhận diện deadlock

Deadlock xảy ra khi một nhóm thread tạo thành chu trình chờ tài nguyên: mỗi thread giữ một lock và chờ lock đang do thread khác trong chu trình nắm giữ.

Ví dụ:

~~~text
Thread A giữ Lock A và chờ Lock B
Thread B giữ Lock B và chờ Lock A
~~~

Không thread nào có thể tiếp tục để nhả lock mà thread còn lại cần.

HotSpot có thể in phần phát hiện deadlock ở cuối dump:

~~~text
Found one Java-level deadlock:
=============================
"lock-A-then-B":
  waiting to lock monitor ..., which is held by "lock-B-then-A"
"lock-B-then-A":
  waiting to lock monitor ..., which is held by "lock-A-then-B"

Found 1 deadlock.
~~~

Đây là ví dụ minh họa. Cụm từ và chi tiết ID có thể thay đổi theo phiên bản JVM.

Cách đọc:

1. Ghi lại thread đầu tiên và lock mà nó đang chờ.
2. Xác định thread nào đang giữ lock đó.
3. Mở entry của thread giữ lock và tìm lock tiếp theo nó đang chờ.
4. Lặp lại cho đến khi quay lại thread đầu tiên.
5. Tìm các frame ứng dụng đang giữ/chờ lock để xác định thứ tự khóa gây ra chu trình.

`jstack` có deadlock detection cho các deadlock Java mà VM có thể nhận diện. Tuy nhiên, không phải mọi tình trạng chờ đều là deadlock. Ví dụ, thread chờ database, network service hoặc distributed lock bên ngoài JVM có thể làm request bị treo mà không tạo ra một chu trình monitor trong dump.

## 12. Phân biệt deadlock, lock contention và thread pool starvation

| Hiện tượng | Dấu hiệu trong dump | Hướng điều tra |
|---|---|---|
| Deadlock | Chu trình thread giữ lock và chờ lock khác; có thể có báo cáo deadlock | Thứ tự lấy lock, nested synchronized, lock ownership |
| Lock contention | Nhiều thread cùng `BLOCKED` trên một monitor | Critical section quá dài, lock dùng chung, công việc I/O bên trong synchronized |
| Thread pool starvation | Nhiều tác vụ chờ future/queue, worker đều bận hoặc chờ tài nguyên phụ thuộc | Kích thước pool, blocking task, tác vụ phụ thuộc cùng executor |
| I/O bottleneck | Stack dừng ở socket/file/native I/O | Endpoint, timeout, network, disk, connection pool |
| CPU bottleneck | Một số thread `RUNNABLE` lặp lại cùng stack qua nhiều dump | Hot method, busy loop, profiler/JFR |
| Thread leak | Số thread tăng theo thời gian, nhiều thread cùng nhóm hoặc cùng stack tạo mới | Vòng đời executor, thread creation, task không kết thúc |

Lock contention không nhất thiết là deadlock. Một thread có thể chờ lock vì thread khác đang thực hiện critical section dài rồi sẽ nhả lock. Chụp thêm dump để xem owner có tiến triển hay vẫn mắc kẹt.

Thread pool starvation có thể xuất hiện khi mọi worker của một pool đều chờ kết quả của task khác nhưng task đó lại cần chính pool đang bị chiếm hết. Khi thấy `Future.get()`, `CompletableFuture.join()` hoặc queue wait, hãy truy dấu executor nào đang chạy task và executor nào cần thực hiện phần còn lại.

## 13. Phân tích nhiều thread dump theo thời gian

Một dump là snapshot tức thời. Khi điều tra hang hoặc chậm bất thường, nên lấy một nhóm snapshot, ví dụ ba lần cách nhau khoảng năm giây.

PowerShell:

~~~powershell
$javaPid = 8120
1..3 | ForEach-Object {
    "===== $(Get-Date -Format o) =====" | Out-File -Encoding utf8 -Append thread-dumps.txt
    jcmd $javaPid Thread.print -l | Out-File -Encoding utf8 -Append thread-dumps.txt
    Start-Sleep -Seconds 5
}
~~~

Linux/macOS:

~~~bash
java_pid=8120
for i in 1 2 3; do
    date -Is >> thread-dumps.txt
    jcmd "$java_pid" Thread.print -l >> thread-dumps.txt
    sleep 5
done
~~~

Khi so sánh, tập trung vào:

- Thread nào giữ nguyên trạng thái và stack qua nhiều lần chụp.
- Thread nào liên tục `BLOCKED` trên cùng một monitor.
- Owner của lock có thay đổi hoặc có tiến triển hay không.
- Số lượng thread theo nhóm tên có tăng bất thường không.
- Thread `RUNNABLE` nào lặp lại cùng các frame ứng dụng.
- Các thread đang chờ cùng một endpoint, queue hoặc connection pool.

Không cần chụp dump liên tục với tần suất quá cao. Thread dump lớn có thể gây tải và tạo nhiều dữ liệu cần lưu trữ; chọn khoảng thời gian đủ để nhìn thấy tiến triển mà vẫn giữ ảnh chụp hữu ích.

## 14. Ví dụ thực hành: tạo deadlock có thể tái hiện

Tạo file `ThreadDumpDeadlockDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class ThreadDumpDeadlockDemo {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();
    private static final CountDownLatch BOTH_HOLD_FIRST_LOCK =
            new CountDownLatch(2);

    public static void main(String[] args) throws InterruptedException {
        Thread a = new Thread(
                () -> lockInOrder(LOCK_A, LOCK_B),
                "lock-A-then-B"
        );
        Thread b = new Thread(
                () -> lockInOrder(LOCK_B, LOCK_A),
                "lock-B-then-A"
        );

        a.start();
        b.start();

        // Giữ main sống để có thể attach và chụp thread dump.
        new CountDownLatch(1).await();
    }

    private static void lockInOrder(Object first, Object second) {
        synchronized (first) {
            BOTH_HOLD_FIRST_LOCK.countDown();

            try {
                BOTH_HOLD_FIRST_LOCK.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            synchronized (second) {
                System.out.println("Acquired both locks");
            }
        }
    }
}
~~~

Chương trình cố ý tạo deadlock: thread A giữ `LOCK_A` rồi chờ `LOCK_B`; thread B giữ `LOCK_B` rồi chờ `LOCK_A`. CountDownLatch bảo đảm cả hai thread đã giữ lock đầu tiên trước khi bước vào phần lấy lock thứ hai.

Biên dịch:

~~~powershell
javac ThreadDumpDeadlockDemo.java
~~~

Chạy chương trình:

~~~powershell
java ThreadDumpDeadlockDemo
~~~

Chương trình không in thông báo thành công vì hai thread bị deadlock trước khi vào phần `println`. Nó tiếp tục chạy để bạn chụp dump từ terminal thứ hai.

Tìm PID:

~~~powershell
jps -l
~~~

Lấy dump:

~~~powershell
jcmd <PID> Thread.print -l
~~~

Hoặc:

~~~powershell
jstack -l <PID>
~~~

Trong output, tìm hai thread:

- `lock-A-then-B`
- `lock-B-then-A`

Bạn sẽ thấy cả hai có trạng thái `BLOCKED (on object monitor)`. Mỗi thread có một dòng `waiting to lock` và một dòng `locked`. Cuối dump, HotSpot thường phát hiện chu trình và in phần `Found one Java-level deadlock`.

Sau khi đã quan sát, quay lại terminal chạy chương trình và nhấn Ctrl+C để kết thúc ví dụ thử nghiệm.

## 15. Những điều thread dump không thể kết luận một mình

Thread dump rất hữu ích nhưng có giới hạn:

- Không cho biết chính xác CPU usage lịch sử của từng thread.
- Không cho biết toàn bộ thời gian thread đã chờ trước thời điểm chụp.
- Không giải thích đầy đủ trạng thái của database, broker, network hoặc distributed lock.
- Không chứng minh một thread `RUNNABLE` đang tiêu thụ CPU cao.
- Không cho biết mọi local variable hoặc toàn bộ dữ liệu trong heap.
- Không thay thế heap dump, profiler, JFR hoặc log ứng dụng.

Kết hợp các nguồn dữ liệu:

| Câu hỏi | Công cụ bổ sung |
|---|---|
| Thread có đang tiêu thụ CPU cao không? | OS thread metrics, JFR, profiler |
| Thread chờ lock bao lâu? | JFR lock events, nhiều thread dump |
| Có GC pause kéo dài không? | GC log, JFR, JDK Mission Control |
| Heap đang giữ object nào? | Heap dump và heap analyzer |
| Native memory tăng ở đâu? | Native Memory Tracking và công cụ hệ điều hành |
| Request bị chậm ở endpoint nào? | Application tracing, metrics và log đã redact |

Oracle JDK 17 tích hợp Java Flight Recorder. JFR có thể ghi thread samples, lock profile và các sự kiện runtime theo thời gian, giúp tìm bottleneck mà một snapshot không thể thể hiện.

## 16. Bảo vệ thread dump trước khi chia sẻ

Thread dump thường không chứa toàn bộ local variable, nhưng vẫn có thể tiết lộ:

- Tên thread chứa tên tenant, user, job hoặc request.
- Package, class, method và cấu trúc nội bộ của ứng dụng.
- Đường dẫn file, endpoint hoặc tên dịch vụ nội bộ xuất hiện trong tên thread hoặc stack.
- Thông tin lock, pool và cấu trúc vận hành.
- Một số chuỗi hoặc thông tin nhạy cảm nếu ứng dụng đưa chúng vào thread name hay diagnostic message.

Trước khi tải dump lên ticket, gửi cho bên hỗ trợ hoặc chia sẻ công khai:

1. Rà soát và redact tên người dùng, tenant, endpoint và đường dẫn nhạy cảm.
2. Không đính kèm log hoặc heap dump chứa credential nếu không cần.
3. Giới hạn quyền truy cập file dump và thời gian lưu.
4. Ghi lại PID, thời gian chụp, JDK version và triệu chứng đi kèm.
5. Giữ bản gốc trong kho sự cố được kiểm soát nếu cần điều tra sâu.

Không sửa nội dung bản gốc trước khi lưu bằng chứng. Nếu cần chia sẻ bản đã redact, tạo một bản sao riêng.

## 17. Lỗi thường gặp khi lấy thread dump

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jstack is not recognized` | Chưa cài JDK hoặc thư mục `bin` không có trong PATH | Dùng JDK và gọi công cụ bằng đường dẫn đầy đủ |
| `Unable to open socket file` | Sai PID, sai user hoặc attach bị hạn chế | Xác minh PID, tài khoản và namespace |
| Không thấy JVM bằng `jps` | JVM chạy trong container namespace khác | Chạy công cụ trong đúng container hoặc dùng PID namespace |
| `jstack` không phản hồi | JVM hoặc attach mechanism đang gặp vấn đề | Thử `jcmd PID Thread.print -l` theo quyền vận hành; không tự ý kill process |
| Không có lock `java.util.concurrent` trong output | Chưa bật chế độ long listing | Dùng `jstack -l` hoặc `jcmd PID Thread.print -l` |
| Không có deadlock report | Không có chu trình lock JVM được phát hiện tại thời điểm chụp | So sánh nhiều dump và kiểm tra chờ I/O, pool, database hoặc lock bên ngoài |
| Không thấy dump sau `kill -QUIT` | Standard output được redirect hoặc JVM dùng `-Xrs` | Kiểm tra log output và dùng `jcmd` nếu attach được |
| Output quá dài | Ứng dụng có nhiều thread hoặc stack sâu | Lưu vào file, lọc theo thread name và so sánh các snapshot |

Với core dump sau sự cố, dùng Serviceability Agent thay cho attach vào tiến trình sống:

~~~bash
jhsdb jstack --exe /path/to/java --core /path/to/core
~~~

Tùy hệ điều hành và loại core file, cần cung cấp đúng executable và file core tương ứng. Đọc tài liệu `jhsdb` của JDK đang dùng trước khi phân tích postmortem.

## 18. Quy trình điều tra sự cố bằng thread dump

Một quy trình thực tế:

1. Ghi nhận triệu chứng, thời điểm và PID ứng dụng.
2. Xác định JDK version, host/container và tài khoản đang chạy JVM.
3. Lấy một thread dump bằng `jcmd PID Thread.print -l`.
4. Nếu sự cố đang tiếp diễn, lấy thêm hai snapshot cách nhau vài giây.
5. Phân nhóm thread theo tên, trạng thái và stack đầu tiên thuộc code ứng dụng.
6. Tìm `BLOCKED`, `waiting to lock`, `parking to wait for` và phần deadlock report.
7. Với mỗi lock bị chờ, tìm thread đang giữ lock đó.
8. Nếu không có deadlock, kiểm tra I/O, executor, connection pool và các dependency bên ngoài.
9. Đối chiếu với metrics, log, tracing và JFR.
10. Lưu dump gốc có kiểm soát, redact bản chia sẻ và ghi lại kết luận cùng bằng chứng.

Không sửa code hoặc tăng thread pool chỉ dựa trên một dòng trạng thái. Trước tiên phải xác định thread đang chờ điều gì, ai sở hữu tài nguyên, và trạng thái đó có lặp lại qua nhiều snapshot hay không.

## 19. Checklist đọc thread dump

- [ ] Đã xác định đúng PID và JDK của tiến trình.
- [ ] Đã lấy dump bằng `jcmd PID Thread.print -l` hoặc `jstack -l PID`.
- [ ] Đã lưu output đầy đủ vào file.
- [ ] Đã đọc thread name, daemon, ID và trạng thái.
- [ ] Đã tìm frame đầu tiên thuộc code ứng dụng.
- [ ] Đã phân biệt `BLOCKED`, `WAITING`, `TIMED_WAITING` và `RUNNABLE`.
- [ ] Đã phân biệt `waiting to lock`, `waiting on`, `locked` và `parking to wait for`.
- [ ] Đã đối chiếu thread đang chờ với thread giữ lock.
- [ ] Đã xem phần deadlock report nếu có.
- [ ] Đã so sánh nhiều snapshot khi điều tra hang hoặc CPU cao.
- [ ] Đã kiểm tra I/O, executor và connection pool nếu không có deadlock.
- [ ] Đã kết hợp metrics, log hoặc JFR khi cần thêm bằng chứng.
- [ ] Đã redact dữ liệu nhạy cảm trước khi chia sẻ dump.

Thread dump là ảnh chụp stack và trạng thái thread của JVM. Hãy bắt đầu từ thread header và `java.lang.Thread.State`, sau đó đọc stack frame để tìm vị trí trong ứng dụng. Dùng `waiting to lock`, `locked`, `waiting on` và `parking to wait for` để nối quan hệ giữa thread và tài nguyên. Khi nghi ngờ hang hoặc deadlock, lấy nhiều snapshot và kiểm tra chu trình chờ; với JDK 17, ưu tiên `jcmd PID Thread.print -l` cho chẩn đoán mới.

## Tài liệu tham khảo

- Oracle, Java SE 17 Troubleshooting Guide — Diagnostic Tools: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- Oracle, Java SE 17 — The jcmd Utility: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, Java SE 17 — The jstack Utility: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstack.html
- Oracle, Java SE 17 — The java Command and Control+Break Handler: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
