# Sử dụng lệnh jstack để phân tích thread dump Java

## 1. jstack dùng để làm gì?

`jstack` là công cụ dòng lệnh đi kèm JDK, dùng để lấy thread dump từ một Java Virtual Machine (JVM) đang chạy. Thread dump là ảnh chụp trạng thái các thread tại một thời điểm, bao gồm tên thread, trạng thái, stack trace và thông tin lock tùy tùy chọn.

Thread dump giúp điều tra các tình huống:

- Ứng dụng phản hồi chậm hoặc treo.
- Request bị chờ lâu, thread pool cạn hoặc worker không xử lý thêm tác vụ.
- Nhiều thread ở trạng thái `BLOCKED` do tranh chấp monitor.
- Thread ở trạng thái `WAITING` hoặc `TIMED_WAITING` lâu hơn dự kiến.
- Deadlock giữa các thread.
- Thread đang lặp ở một đoạn code hoặc thường xuyên chờ I/O.
- Cần so sánh trạng thái thread trước và sau khi xảy ra sự cố.

`jstack` không sửa trạng thái ứng dụng, không tự kết thúc thread và không phải profiler CPU. Công cụ lấy dữ liệu để người vận hành phân tích. Với sự cố chỉ xuất hiện trong thời gian ngắn, một thread dump có thể bỏ lỡ nguyên nhân; nên thu thập nhiều snapshot cách nhau vài giây và đối chiếu với log, metric, JFR hoặc profiler.

## 2. Cú pháp và tùy chọn

Cú pháp của JDK 24:

~~~bash
jstack [-l][-e] <pid>
~~~

Trong đó `pid` là process ID của JVM đang chạy. Trợ giúp của công cụ có các tùy chọn:

| Tùy chọn | Công dụng |
|---|---|
| `-l` | Long listing: in thêm thông tin về lock, monitor và synchronizer. |
| `-e` | Extended listing: in thêm thông tin mở rộng về thread. |
| `-h`, `-?`, `-help` | Hiển thị trợ giúp. |

Ví dụ:

~~~bash
jstack 18420
jstack -l 18420
jstack -e 18420
jstack -h
~~~

- Dùng lệnh không có option khi cần stack trace cơ bản.
- Dùng `-l` khi điều tra lock contention hoặc deadlock.
- Dùng `-e` khi cần thêm thông tin về thread, chẳng hạn CPU time, thời gian tồn tại, allocated bytes hoặc số class được định nghĩa trên các JDK hỗ trợ.

Danh sách option phụ thuộc phiên bản JDK. Trong môi trường kiểm chứng JDK 24.0.2, `jstack -h` liệt kê `-l` và `-e`. Một số hướng dẫn cũ có thể đề cập `-F` hoặc `-m`; không mặc định các option đó tồn tại trên JDK đang dùng. Luôn kiểm tra `jstack -h` trước khi đưa lệnh vào runbook.

## 3. Xác định PID của ứng dụng Java

Trước khi lấy thread dump, tìm đúng JVM:

~~~bash
jcmd -l
~~~

Output ví dụ:

~~~text
18420 com.example.orders.OrderService
27116 com.example.worker.BatchWorker
~~~

Số ở đầu dòng là PID. Nếu có nhiều ứng dụng Java, đối chiếu main class hoặc command line để chọn đúng tiến trình.

Có thể dùng công cụ hệ điều hành để tìm PID:

~~~bash
# Linux
ps -ef | grep java

# Windows PowerShell
Get-CimInstance Win32_Process -Filter "Name = 'java.exe'" |
    Select-Object ProcessId, CommandLine
~~~

Ưu tiên PID cụ thể thay vì chọn ngẫu nhiên một Java process. Ghi lại PID, tên ứng dụng, host/container và thời điểm thu thập để các snapshot có thể được đối chiếu chính xác.

## 4. Điều kiện kết nối tới JVM đích

`jstack` attach vào JVM trên cùng máy. Một số điều kiện thường gặp:

- Chạy lệnh trên host có JVM đích hoặc trong môi trường container có thể nhìn thấy PID của JVM.
- User chạy `jstack` thường phải trùng với user đã khởi chạy JVM.
- JVM phải cho phép Attach mechanism; nếu attach bị tắt hoặc môi trường chặn attach, công cụ có thể không kết nối được.
- Dùng công cụ từ JDK phù hợp với runtime của ứng dụng để giảm khác biệt phiên bản.
- JVM đích phải còn sống và phản hồi được diagnostic request.

`jstack` không phải công cụ kết nối từ xa qua địa chỉ IP. Với JVM trên máy khác, cần truy cập đúng host hoặc dùng cơ chế chẩn đoán từ xa đã được tổ chức triển khai.

Trong container, PID bên trong container có thể khác PID nhìn từ host. Chạy công cụ trong đúng PID namespace hoặc dùng PID host tương ứng, đồng thời bảo đảm quyền truy cập cần thiết.

## 5. Lấy thread dump cơ bản

Sau khi có PID, chạy:

~~~bash
jstack 18420
~~~

Output thường bắt đầu bằng timestamp và thông tin JVM:

~~~text
2026-11-10 19:03:25
Full thread dump OpenJDK 64-Bit Server VM (24.0.2+12 mixed mode, sharing):
~~~

Tiếp theo là danh sách các thread, mỗi thread gồm header và stack trace. Một đoạn minh họa:

~~~text
"main" #3 prio=5 os_prio=0 cpu=46.88ms elapsed=0.96s tid=0x... nid=55784
   java.lang.Thread.State: WAITING (on object monitor)
        at java.lang.Object.wait0(Native Method)
        at java.lang.Object.wait(Object.java:389)
        at java.lang.Thread.join(Thread.java:1860)
~~~

Địa chỉ bộ nhớ, PID, thread ID, CPU time và số dòng stack thay đổi theo lần chạy. Không dùng các giá trị này như output cố định trong script kiểm thử.

Để lưu kết quả ra file:

~~~bash
jstack 18420 > thread-dump.txt
~~~

Trên PowerShell:

~~~powershell
jstack 18420 | Out-File -Encoding utf8 thread-dump.txt
~~~

Thread dump là dữ liệu phục vụ điều tra; lưu ở thư mục có quyền truy cập phù hợp và đặt tên file gắn với ứng dụng, PID và thời điểm thu thập.

## 6. Lấy thông tin lock bằng tùy chọn -l

Khi cần biết thread nào đang giữ lock và thread nào đang chờ lock, dùng:

~~~bash
jstack -l 18420
~~~

Output có thể chứa các dòng:

~~~text
"worker-A" #37 prio=5 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderService.update(OrderService.java:42)
        - waiting to lock <0x000000011f019408> (a java.lang.Object)
        - locked <0x000000011f0193f8> (a java.lang.Object)
~~~

Ý nghĩa:

- `waiting to lock`: thread đang chờ lấy monitor tại địa chỉ được ghi.
- `locked`: thread đang sở hữu monitor tương ứng.
- Địa chỉ monitor giúp liên kết thông tin chờ và sở hữu giữa các thread trong cùng dump.

Với `ReentrantLock` hoặc các synchronizer dựa trên `java.util.concurrent`, thông tin bổ sung về ownable synchronizer có thể xuất hiện trong long listing. Hãy đọc phần lock cùng stack trace để biết code nào giữ lock và code nào đang chờ.

Không kết luận deadlock chỉ vì có một thread `BLOCKED`. Một thread có thể chờ lock trong thời gian ngắn rồi tiếp tục. Cần xem chuỗi sở hữu/chờ giữa nhiều thread và kiểm tra xem trạng thái đó có lặp lại qua nhiều snapshot không.

## 7. Lấy thông tin thread mở rộng bằng tùy chọn -e

Dùng:

~~~bash
jstack -e 18420
~~~

Trong JDK 24, extended listing có thể bổ sung các trường như:

- `cpu`: CPU time được ghi nhận cho thread.
- `elapsed`: thời gian thread đã tồn tại.
- `allocated`: lượng bộ nhớ được cấp phát bởi thread.
- `defined_classes`: số class được thread định nghĩa.
- `tid` và `nid`: thông tin nhận diện thread trong JVM và hệ điều hành.

Ví dụ header:

~~~text
"demo-sleeping" #35 [63112] daemon prio=5 os_prio=0
  cpu=0.00ms elapsed=1.27s allocated=1296B defined_classes=2
  tid=0x... nid=63112 waiting on condition
~~~

Các trường và định dạng có thể thay đổi theo JDK. CPU time trong một snapshot không thay thế CPU profiler; cần so sánh nhiều snapshot hoặc kết hợp với hệ thống metric để nhận diện thread đang tiêu thụ CPU liên tục.

## 8. Hiểu các trạng thái thread

Java định nghĩa trạng thái thread trong `java.lang.Thread.State`. Thread dump thường hiển thị trạng thái sau header:

~~~text
java.lang.Thread.State: RUNNABLE
~~~

Các trạng thái chính:

| Trạng thái | Ý nghĩa | Dấu hiệu thường gặp |
|---|---|---|
| `NEW` | Thread đã được tạo nhưng chưa gọi `start()`. | Thường không xuất hiện như một thread đang chạy trong dump. |
| `RUNNABLE` | Thread đang thực thi trong JVM hoặc sẵn sàng được hệ điều hành cấp CPU. | Có thể đang chạy code, xử lý native call hoặc chờ tài nguyên hệ điều hành. |
| `BLOCKED` | Thread đang chờ lấy intrinsic monitor để vào hoặc tái nhập vùng `synchronized`. | Có dòng `waiting to lock`. |
| `WAITING` | Thread chờ vô thời hạn một thread khác thực hiện hành động. | `Object.wait()`, `Thread.join()` hoặc `LockSupport.park()` không timeout. |
| `TIMED_WAITING` | Thread chờ trong một khoảng thời gian giới hạn. | `Thread.sleep()`, `wait(timeout)`, `join(timeout)` hoặc `parkNanos()`. |
| `TERMINATED` | Thread đã kết thúc. | Thường không còn nằm trong danh sách thread đang sống. |

Một số lưu ý quan trọng:

- `RUNNABLE` không đồng nghĩa với CPU đang luôn chạy thread. Thread có thể đang chờ I/O hoặc tài nguyên native.
- `BLOCKED` là trạng thái chờ monitor; nó khác với `WAITING` do `Object.wait()` hoặc `LockSupport.park()`.
- Thread gọi `Object.wait()` sẽ nhả monitor đang giữ trong lúc chờ; khi được đánh thức, nó phải lấy lại monitor trước khi tiếp tục.
- `Thread.sleep()` không nhả intrinsic monitor mà thread đang giữ.
- Một thread `WAITING` có thể hoàn toàn bình thường, ví dụ worker chờ queue nhận tác vụ.

Hãy kết hợp trạng thái với stack trace, lock owner và thời gian quan sát. Không đánh giá sức khỏe ứng dụng chỉ bằng số lượng thread ở một trạng thái.

## 9. Đọc stack trace của một thread

Stack trace trong thread dump hiển thị chuỗi lời gọi method từ vị trí hiện tại đi ngược lên các caller.

Ví dụ:

~~~text
"pool-1-thread-3" #28 prio=5 ...
   java.lang.Thread.State: RUNNABLE
        at com.example.service.OrderService.calculate(OrderService.java:85)
        at com.example.service.OrderService.process(OrderService.java:51)
        at com.example.worker.OrderWorker.run(OrderWorker.java:29)
        at java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1144)
        at java.util.concurrent.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:642)
        at java.lang.Thread.run(Thread.java:1583)
~~~

Đọc từ trên xuống:

1. Dòng đầu tiên là frame hiện tại hoặc vị trí thread đang dừng.
2. Các frame tiếp theo cho biết đường gọi đã đưa thread tới vị trí đó.
3. Frame thuộc code ứng dụng thường giúp xác định service, method và dòng source cần điều tra.
4. Frame thuộc JDK hoặc framework cho biết thread đang ở executor, queue, lock, socket hay API runtime nào.

Một số frame có thể hiển thị `Native Method` hoặc không có số dòng source nếu class không chứa debug line information.

Khi nhiều thread có stack giống nhau trong executor, hãy xem chúng cùng chờ ở queue, cùng chạy một method, hay cùng bị chặn tại một lock. Điều đó giúp phân biệt worker nhàn rỗi với worker bị kẹt.

## 10. Nhận diện deadlock

Deadlock xảy ra khi các thread giữ tài nguyên mà thread khác cần, tạo thành một chu trình chờ không thể tự tiến triển.

Ví dụ:

- Thread A giữ lock A rồi chờ lock B.
- Thread B giữ lock B rồi chờ lock A.
- A không thể lấy B vì B đang giữ.
- B không thể lấy A vì A đang giữ.

Khi JVM nhận diện được monitor deadlock, thread dump có thể in:

~~~text
Found one Java-level deadlock:
=============================

"demo-deadlock-A":
  waiting to lock monitor ...,
  which is held by "demo-deadlock-B"

"demo-deadlock-B":
  waiting to lock monitor ...,
  which is held by "demo-deadlock-A"
~~~

Đây là dấu hiệu rõ ràng về chu trình lock. Phần sau thường liệt kê Java stack information của từng thread trong deadlock để chỉ ra vị trí source đang chờ và lock đang được giữ.

Nếu không có dòng `Found one Java-level deadlock`, điều đó không chứng minh hệ thống không có mọi dạng deadlock. Thread dump có thể không nhận diện được chu trình logic qua database, network, queue, callback hoặc giao thức ứng dụng. Cũng có thể sự cố chưa xuất hiện đúng lúc lấy snapshot.

## 11. Ví dụ Java 17 tạo deadlock để thực hành

Tạo file `JstackDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class JstackDemo {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();
    private static final Object WAIT_LOCK = new Object();

    public static void main(String[] args) throws Exception {
        Thread sleeper = new Thread(() -> {
            while (true) {
                try {
                    Thread.sleep(60_000);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "demo-sleeping");
        sleeper.setDaemon(true);
        sleeper.start();

        Thread waiter = new Thread(() -> {
            synchronized (WAIT_LOCK) {
                try {
                    WAIT_LOCK.wait();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-waiting");
        waiter.setDaemon(true);
        waiter.start();

        CountDownLatch bothOwnLocks = new CountDownLatch(2);

        Thread first = new Thread(() -> {
            synchronized (LOCK_A) {
                bothOwnLocks.countDown();
                try {
                    bothOwnLocks.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                synchronized (LOCK_B) {
                    System.out.println("first acquired both locks");
                }
            }
        }, "demo-deadlock-A");

        Thread second = new Thread(() -> {
            synchronized (LOCK_B) {
                bothOwnLocks.countDown();
                try {
                    bothOwnLocks.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
                synchronized (LOCK_A) {
                    System.out.println("second acquired both locks");
                }
            }
        }, "demo-deadlock-B");

        first.start();
        second.start();
        System.out.println("JstackDemo ready");
        Thread.currentThread().join();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 JstackDemo.java
java JstackDemo
~~~

Stdout trước khi lấy dump:

~~~text
JstackDemo ready
~~~

Chương trình cố ý tạo một deadlock giữa hai thread không daemon nên JVM tiếp tục chạy. Thread `demo-sleeping` ở `TIMED_WAITING`, thread `demo-waiting` ở `WAITING` do `Object.wait()`, còn hai thread deadlock ở `BLOCKED`.

Trong terminal khác, tìm PID:

~~~bash
jcmd -l
~~~

Giả sử PID là `18420`, lấy dump:

~~~bash
jstack 18420
jstack -l 18420
jstack -e 18420
~~~

Trong dump đã kiểm chứng trên JDK 24.0.2, JVM báo `Found one Java-level deadlock` và chỉ ra thread A chờ monitor do B giữ, còn B chờ monitor do A giữ. Địa chỉ lock, PID và số dòng source thực tế sẽ thay đổi theo lần chạy.

Sau khi thực hành, dừng chương trình mẫu bằng cách kết thúc process trong terminal chạy ứng dụng hoặc dùng công cụ hệ điều hành. Không dùng chương trình deadlock này trong môi trường production.

## 12. Phân tích một dump để tìm nguyên nhân

Một quy trình đọc dump thực tế:

1. Xác nhận header có đúng JVM, phiên bản và timestamp.
2. Tìm phần `Found one Java-level deadlock` nếu nghi ngờ deadlock.
3. Tìm các thread `BLOCKED` và đối chiếu `waiting to lock` với thread đang `locked` cùng monitor.
4. Nhóm các thread theo tên, pool hoặc stack trace giống nhau.
5. Kiểm tra các thread `RUNNABLE` có cùng dừng ở một method, vòng lặp hoặc native call không.
6. Xem thread `WAITING` có đang chờ queue, future, latch hoặc condition hợp lý không.
7. So sánh các dump tiếp theo để xác định trạng thái có kéo dài hay thay đổi.
8. Đối chiếu với log, request latency, CPU, GC, database và network metrics.

Ví dụ, nếu nhiều thread của cùng request pool đều `BLOCKED` tại một dòng `synchronized`, trong khi một thread khác giữ monitor đó và stack trace nằm trong thao tác chậm, đây là hướng điều tra đáng ưu tiên.

Nếu nhiều worker ở `WAITING` tại `LinkedBlockingQueue.take()`, đó có thể chỉ là worker nhàn rỗi đang chờ tác vụ. Nếu tất cả worker đều chờ một dịch vụ ngoài hoặc một lock, cần kiểm tra dependency và thời gian chờ.

## 13. Thu thập nhiều thread dump theo thời gian

Một snapshot cho biết trạng thái tại một thời điểm. Với sự cố treo hoặc CPU cao, lấy một số snapshot cách nhau vài giây giúp phân biệt trạng thái tạm thời với trạng thái bị kẹt.

Ví dụ trên Linux/macOS:

~~~bash
PID=18420
jstack -l "$PID" > thread-1.txt
sleep 5
jstack -l "$PID" > thread-2.txt
sleep 5
jstack -l "$PID" > thread-3.txt
~~~

Ví dụ PowerShell:

~~~powershell
$targetPid = 18420
1..3 | ForEach-Object {
    $file = "thread-$_.txt"
    jstack -l $targetPid | Out-File -Encoding utf8 $file
    Start-Sleep -Seconds 5
}
~~~

So sánh:

- Thread vẫn nằm ở cùng stack frame qua nhiều dump có thể đang chờ lâu hoặc bị kẹt.
- Thread `RUNNABLE` có stack thay đổi liên tục có thể đang tiến triển bình thường.
- Nhiều thread cùng chờ một monitor qua nhiều dump cho thấy lock contention kéo dài.
- Một thread deadlock sẽ thường giữ nguyên quan hệ lock chờ/giữ cho tới khi có can thiệp.

Không thu thập quá dày hoặc không giới hạn số lượng file. Thread dump có thể lớn ở JVM có hàng nghìn thread; đặt tên file theo timestamp và giữ lại những snapshot cần thiết.

## 14. Dùng jcmd như một lựa chọn thay thế

`jcmd` có thể lấy thread dump từ JVM đang chạy mà không cần gọi trực tiếp `jstack`.

In thread dump ra terminal:

~~~bash
jcmd 18420 Thread.print
~~~

In thêm thông tin lock:

~~~bash
jcmd 18420 Thread.print -l
~~~

In thêm thông tin thread:

~~~bash
jcmd 18420 Thread.print -e
~~~

Trong JDK 24, `Thread.print` hỗ trợ `-l` và `-e` tương tự mục đích của các option `jstack`.

Có thể lưu thread dump vào file dạng plain text hoặc JSON bằng `Thread.dump_to_file`:

~~~bash
jcmd 18420 Thread.dump_to_file -format=plain thread-dump.txt
jcmd 18420 Thread.dump_to_file -format=json thread-dump.json
~~~

Command này có option `-overwrite` nếu cần cho phép ghi đè file đã tồn tại; mặc định là không ghi đè. Kiểm tra `jcmd 18420 help Thread.dump_to_file` trên JVM đích để xác nhận cú pháp.

Dùng `jstack` khi cần thao tác nhanh, quen thuộc từ terminal. Dùng `jcmd` khi quy trình vận hành đã chuẩn hóa diagnostic command hoặc cần xuất JSON để xử lý bằng công cụ khác.

## 15. Phân biệt jstack với JFR và heap dump

Các công cụ chẩn đoán JVM cung cấp những loại dữ liệu khác nhau:

| Công cụ | Dữ liệu chính | Dùng khi |
|---|---|---|
| `jstack` | Thread state, stack trace, lock và deadlock tại thời điểm chụp. | Điều tra treo, lock contention, deadlock. |
| `JFR` | Chuỗi sự kiện runtime theo thời gian. | Điều tra latency, GC, allocation, I/O và hoạt động thread. |
| Heap dump | Object graph và trạng thái heap tại một thời điểm. | Điều tra memory leak, retained objects, heap tăng bất thường. |
| CPU profiler | Mẫu hoặc thời gian CPU theo method. | Tìm method tiêu tốn CPU. |

Thread dump không cho biết toàn bộ object nào đang chiếm heap, cũng không phải bằng chứng đầy đủ về CPU hot path. Chọn công cụ dựa trên triệu chứng; có thể kết hợp thread dump với JFR để hiểu cả trạng thái tại thời điểm chụp và lịch sử event trước đó.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jstack` không tìm thấy lệnh | JDK `bin` chưa nằm trong PATH. | Kiểm tra `JAVA_HOME` và gọi đúng executable trong thư mục `bin`. |
| Không tìm thấy PID | PID sai hoặc process đã kết thúc. | Chạy lại `jcmd -l` hoặc kiểm tra process bằng công cụ hệ điều hành. |
| `AttachNotSupportedException` | JVM tắt Attach mechanism hoặc môi trường chặn attach. | Kiểm tra JVM options, user và quyền của container/host. |
| Lỗi ghi file | Thư mục đích không tồn tại hoặc thiếu quyền ghi. | Tạo thư mục và kiểm tra quyền file system. |
| Thread dump không có lock detail | Chạy không có `-l`. | Lấy lại dump bằng `jstack -l PID`. |
| Không thấy deadlock trong dump | Deadlock chưa xuất hiện, không phải Java monitor deadlock hoặc chu trình nằm ngoài phạm vi nhận diện. | Lấy nhiều dump, xem lock chain và kiểm tra database, queue, network hoặc application protocol. |
| Nhiều thread `RUNNABLE` | Thread có thể đang chạy, chờ native I/O hoặc được hệ điều hành xếp lịch. | So sánh nhiều dump và đối chiếu CPU metrics/JFR. |
| Nhiều thread `WAITING` | Worker có thể đang chờ queue, future, latch hoặc condition. | Đọc stack frame và xác định điều kiện đánh thức thread. |
| Không nhận option từ hướng dẫn cũ | Option không có trong phiên bản JDK hiện tại. | Chạy `jstack -h` để xem option thực tế. |
| File dump quá lớn | JVM có nhiều thread hoặc stack trace dài. | Lưu vào thư mục đủ dung lượng, thu thập số lượng snapshot hợp lý và lọc khi phân tích. |
| Thread dump khác nhau giữa các lần | Thread đang thay đổi trạng thái hoặc ứng dụng tiếp tục xử lý. | Ghi timestamp từng dump và so sánh thread name, stack, state, lock. |

## 17. Checklist khi điều tra production

- Đã xác định đúng JVM, PID, host/container và JDK version.
- Đã xác nhận user có quyền attach vào process.
- Đã lưu ít nhất một dump cơ bản và một dump có lock detail khi cần.
- Đã dùng `-e` nếu cần thông tin thread mở rộng và JDK hỗ trợ.
- Đã xem thread state cùng stack trace, không kết luận từ một trạng thái riêng lẻ.
- Đã kiểm tra `Found one Java-level deadlock` và lock owner nếu có.
- Đã lấy thêm snapshot cách nhau vài giây khi cần xác định trạng thái kéo dài.
- Đã đối chiếu với log, CPU, latency, GC và dependency metrics.
- Đã lưu timestamp, PID và tên ứng dụng cùng mỗi file dump.
- File thread dump được bảo vệ vì có thể tiết lộ package, class, method và cấu trúc nội bộ.
- Đã kết thúc tiến trình mẫu hoặc recording thử nghiệm sau khi thực hành.
- Đã ghi lại kết luận và bằng chứng từ stack frame/lock cụ thể.

## 18. Tài liệu tham khảo

- [The jstack Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstack.html)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Thread.State — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Thread.State.html)

`jstack` cung cấp thread dump để quan sát trạng thái, stack trace và lock của JVM đang chạy. Hãy bắt đầu bằng PID chính xác, dùng `-l` khi điều tra lock, dùng `-e` khi cần thông tin thread mở rộng, rồi so sánh nhiều snapshot và đối chiếu với log/metric để xác định nguyên nhân treo, contention hoặc deadlock.
