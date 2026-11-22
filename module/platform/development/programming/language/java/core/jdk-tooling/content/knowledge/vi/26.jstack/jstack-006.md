# Phân tích blocked thread bằng jstack

## 1. Blocked thread là gì?

Trong Java, một thread ở trạng thái `BLOCKED` khi nó đang chờ lấy một intrinsic monitor để vào hoặc tái nhập một vùng `synchronized`. Monitor là cơ chế đồng bộ hóa mà JVM dùng để bảo vệ vùng code chỉ cho phép một thread sở hữu tại một thời điểm.

Ví dụ, nếu thread A đang thực thi bên trong `synchronized (lock)`, thread B muốn vào một vùng `synchronized (lock)` khác dùng cùng object phải chờ. Trong lúc chưa lấy được monitor, thread B có trạng thái `BLOCKED`.

Thread bị blocked không nhất thiết là lỗi. Một khoảng chờ lock ngắn có thể là hành vi bình thường khi nhiều thread cập nhật cùng một cấu trúc dữ liệu. Vấn đề cần điều tra khi thời gian chờ kéo dài, số lượng thread blocked tăng, request không hoàn thành hoặc throughput giảm.

`jstack` giúp lấy thread dump để tìm thread nào đang chờ, thread nào đang giữ monitor, stack trace của hai phía, số lượng worker bị ảnh hưởng và tình trạng contention có kéo dài qua nhiều snapshot hay không.

## 2. Phân biệt BLOCKED với các trạng thái thread khác

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| `RUNNABLE` | Thread đang thực thi hoặc sẵn sàng được hệ điều hành cấp CPU. | Đang chạy code ứng dụng hoặc native call. |
| `BLOCKED` | Đang chờ lấy intrinsic monitor để vào `synchronized`. | Thread B chờ monitor do thread A đang giữ. |
| `WAITING` | Chờ một hành động khác mà không có thời hạn. | `Object.wait()`, `Thread.join()` không timeout, `LockSupport.park()`. |
| `TIMED_WAITING` | Chờ một khoảng thời gian xác định. | `Thread.sleep()`, `Object.wait(timeout)`, `Thread.join(timeout)`. |

Điểm quan trọng:

- Thread gọi `Object.wait()` sẽ nhả monitor đang giữ trong lúc chờ. Khi được đánh thức, nó phải lấy lại monitor trước khi tiếp tục; trong lúc chưa lấy lại được monitor, nó có thể ở trạng thái `BLOCKED`.
- `Thread.sleep()` không nhả intrinsic monitor. Nếu thread gọi sleep bên trong `synchronized`, nó tiếp tục giữ lock trong suốt thời gian ngủ.
- `BLOCKED` mô tả việc chờ intrinsic monitor, không phải mọi dạng chờ lock trong Java.
- Thread chờ `ReentrantLock.lock()` thường park qua `LockSupport` và có thể xuất hiện là `WAITING` hoặc `TIMED_WAITING`, không nhất thiết là `BLOCKED`.

Không kết luận một thread bị kẹt chỉ từ tên trạng thái. Cần đọc stack trace, lock owner, thời gian chờ và các snapshot tiếp theo.

## 3. Nguyên nhân phổ biến làm thread bị blocked

Một thread giữ monitor lâu có thể khiến nhiều thread khác phải chờ. Những nguyên nhân thường gặp gồm:

**Critical section quá dài.** Một vùng `synchronized` thực hiện quá nhiều công việc, xử lý collection lớn hoặc gọi nhiều method khác.

**I/O hoặc lời gọi bên ngoài bên trong lock.** Thread giữ monitor trong lúc gọi database, HTTP service, đọc file hoặc chờ một tài nguyên khác. Thời gian phản hồi của dependency có thể kéo dài thời gian giữ lock.

**Sleep hoặc wait không phù hợp.** Gọi `Thread.sleep()` bên trong vùng `synchronized` giữ monitor trong thời gian ngủ. Điều này có thể chặn mọi thread cần cùng monitor.

**Nhiều thread tranh chấp cùng object.** Một lock toàn cục hoặc một object dùng chung trên nhiều request có thể trở thành điểm nghẽn.

**Lock lồng nhau theo thứ tự không nhất quán.** Hai thread lấy nhiều monitor theo thứ tự ngược nhau có thể tạo deadlock.

**Callback gọi ngược vào code dùng chung.** Một callback hoặc listener được gọi trong khi lock vẫn đang giữ có thể tiếp tục lấy thêm lock và mở rộng chuỗi phụ thuộc.

**Xử lý trong thread pool bị chặn.** Nếu nhiều worker cùng blocked, pool có thể hết thread khả dụng và request mới phải chờ dù CPU còn thấp.

## 4. Xác định JVM và lấy thread dump

Trước tiên tìm PID của ứng dụng:

~~~bash
jcmd -l
~~~

Ví dụ:

~~~text
18420 com.example.orders.OrderService
27116 com.example.worker.BatchWorker
~~~

Lấy thread dump cơ bản:

~~~bash
jstack 18420
~~~

Lấy thêm thông tin monitor, lock và ownable synchronizer:

~~~bash
jstack -l 18420
~~~

Trong JDK 24, `jstack` hỗ trợ:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-l` | Long listing, in thêm thông tin lock. |
| `-e` | Extended listing, in thêm thông tin mở rộng của thread. |
| `-h` hoặc `-?` | Hiển thị trợ giúp. |

Ví dụ:

~~~bash
jstack -e 18420
jstack -h
~~~

Trên Windows PowerShell, lưu dump ra file:

~~~powershell
jstack 18420 | Out-File -Encoding utf8 thread-dump.txt
jstack -l 18420 | Out-File -Encoding utf8 thread-dump-locks.txt
~~~

Trên Linux/macOS:

~~~bash
jstack 18420 > thread-dump.txt
jstack -l 18420 > thread-dump-locks.txt
~~~

`jstack` attach tới JVM trên cùng máy. User chạy công cụ thường phải trùng với user chạy JVM, JVM phải cho phép Attach mechanism và PID phải nhìn thấy trong môi trường đang chạy lệnh. Trong container, kiểm tra PID namespace và quyền attach.

## 5. Đọc phần thread header và trạng thái

Một thread dump thường có header tương tự:

~~~text
"worker-7" #42 prio=5 os_prio=0 cpu=18.75ms elapsed=32.41s
  tid=0x... nid=0x... waiting for monitor entry
  java.lang.Thread.State: BLOCKED (on object monitor)
~~~

Các trường thường gặp:

- Tên trong dấu ngoặc kép là thread name.
- `#42` là số thứ tự thread trong JVM.
- `prio` là priority.
- `cpu` và `elapsed` là thông tin thời gian trên các JDK hỗ trợ.
- `tid` là thông tin nhận diện thread trong JVM.
- `nid` là native thread ID.
- `waiting for monitor entry` cho biết thread đang chờ vào monitor.
- `java.lang.Thread.State: BLOCKED` là trạng thái Java của thread.

Giá trị PID, thread ID, địa chỉ lock và CPU time thay đổi theo lần chạy. Hãy dùng chúng để liên kết dữ liệu trong cùng một dump, không coi đó là định danh cố định qua các lần restart.

## 6. Dùng jstack -l để tìm thread đang giữ lock

Trong long listing, các dòng quan trọng thường có dạng:

~~~text
"demo-blocked-contender" #36 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at BlockedThreadDemo.lambda$main$1(BlockedThreadDemo.java:32)
        - waiting to lock <0x000000011f019370> (a java.lang.Object)

"demo-lock-holder" #35 ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Thread.java:513)
        - locked <0x000000011f019370> (a java.lang.Object)
~~~

Cả hai dòng dùng cùng một địa chỉ monitor:

- Thread `demo-blocked-contender` đang chờ lấy monitor `0x...`.
- Thread `demo-lock-holder` đang sở hữu monitor đó.
- Stack trace của holder chỉ ra code đang giữ lock.
- Stack trace của contender chỉ ra code muốn vào vùng synchronized.

Đây là cách xác định chủ sở hữu lock trong một dump: tìm dòng `waiting to lock` của thread blocked, ghi lại địa chỉ monitor, rồi tìm thread có dòng `locked` với cùng địa chỉ.

Địa chỉ trong ví dụ chỉ mang tính minh họa. Trong dump thực tế, hãy đối chiếu nguyên văn cùng một địa chỉ trong cùng file.

Không nhầm `waiting to lock` với `waiting on`. Thread gọi `Object.wait()` thường hiển thị thông tin chờ monitor theo cơ chế wait/notify và có thể nhả monitor trong lúc chờ. Thread đang `BLOCKED` cần lấy monitor để vào vùng synchronized.

## 7. Phân biệt thread blocked và thread giữ lock

Trong một tình huống contention, thread bị blocked và thread gây ra sự chờ có vai trò khác nhau:

| Vai trò | Dấu hiệu trong dump | Câu hỏi cần trả lời |
|---|---|---|
| Thread blocked | `BLOCKED`, `waiting to lock <id>` | Thread đang muốn thực hiện thao tác nào? |
| Thread giữ lock | `- locked <id>` | Thread đang giữ lock trong method nào? |
| Thread khác cùng chờ | Cùng `waiting to lock <id>` | Có bao nhiêu request hoặc worker bị ảnh hưởng? |

Ví dụ, một thread xử lý request có thể giữ monitor trong lúc gọi dịch vụ bên ngoài. Mười thread khác cùng chờ monitor. Nếu chỉ đọc stack của mười thread blocked, ta biết chúng đang chờ nhưng chưa biết nguyên nhân. Stack của thread giữ lock mới cho biết công việc đang kéo dài bên trong critical section.

Vì vậy, luôn đọc cả thread chờ và thread sở hữu lock. Nếu owner không xuất hiện rõ trong dump, kiểm tra toàn bộ phần monitor/synchronizer, lấy snapshot khác và xem xét việc lock được quản lý qua thư viện hoặc native code.

## 8. Ví dụ Java 17: một thread giữ lock, một thread bị blocked

Tạo file `BlockedThreadDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class BlockedThreadDemo {
    private static final Object SHARED_LOCK = new Object();

    public static void main(String[] args) throws Exception {
        CountDownLatch lockHeld = new CountDownLatch(1);
        CountDownLatch contenderStarted = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (SHARED_LOCK) {
                System.out.println("holder acquired lock");
                lockHeld.countDown();

                try {
                    Thread.sleep(60_000);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-lock-holder");

        Thread contender = new Thread(() -> {
            try {
                lockHeld.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            System.out.println("contender attempting lock");
            contenderStarted.countDown();

            synchronized (SHARED_LOCK) {
                System.out.println("contender acquired lock");
            }
        }, "demo-blocked-contender");

        holder.start();
        lockHeld.await();
        contender.start();
        contenderStarted.await();

        System.out.println("BlockedThreadDemo ready");
        Thread.currentThread().join();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 BlockedThreadDemo.java
java BlockedThreadDemo
~~~

Stdout trước khi lấy dump:

~~~text
holder acquired lock
contender attempting lock
BlockedThreadDemo ready
~~~

Chương trình cố ý để thread holder ngủ trong vùng `synchronized`. Thread ngủ vẫn giữ `SHARED_LOCK`. Thread contender đã bắt đầu chạy nhưng không thể vào vùng synchronized nên ở trạng thái `BLOCKED`.

Trong terminal khác, tìm PID bằng `jcmd -l` rồi lấy dump:

~~~bash
jstack -l 18420
~~~

Kết quả đã kiểm chứng trên JDK 24.0.2 cho thấy:

~~~text
"demo-lock-holder" ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
   - locked <0x...> (a java.lang.Object)

"demo-blocked-contender" ...
   java.lang.Thread.State: BLOCKED (on object monitor)
   - waiting to lock <0x...> (a java.lang.Object)
~~~

Địa chỉ lock ở hai dòng trùng nhau. Điều này xác nhận contender đang chờ monitor mà holder sở hữu. Sau khi thực hành, dừng chương trình mẫu trong terminal hoặc kết thúc process bằng công cụ hệ điều hành; không chạy ví dụ cố ý giữ lock này trong production.

## 9. Vì sao thread BLOCKED không đồng nghĩa với deadlock?

Lock contention xảy ra khi một thread đang giữ lock và các thread khác phải chờ. Nếu owner hoàn tất công việc rồi nhả lock, những thread chờ sẽ lần lượt tiếp tục.

Deadlock là một trường hợp nghiêm trọng hơn: có một chu trình phụ thuộc mà mỗi thread giữ một tài nguyên và chờ tài nguyên do thread khác giữ. Không thread nào trong chu trình có thể tự tiến triển.

Ví dụ deadlock hai lock:

- Thread A giữ lock A và chờ lock B.
- Thread B giữ lock B và chờ lock A.

Trong thread dump, JVM có thể phát hiện và in:

~~~text
Found one Java-level deadlock:
=============================

"thread-A":
  waiting to lock monitor ...,
  which is held by "thread-B"

"thread-B":
  waiting to lock monitor ...,
  which is held by "thread-A"
~~~

Một thread blocked đơn lẻ không tạo thành deadlock. Nhiều thread cùng chờ một owner cũng có thể chỉ là contention nếu owner vẫn có thể hoàn tất và nhả lock.

Nếu không thấy `Found one Java-level deadlock`, không thể kết luận rằng hệ thống không có mọi loại deadlock. Chu trình chờ qua database, network, queue hoặc giao thức ứng dụng có thể nằm ngoài phạm vi mà JVM nhận diện.

## 10. Nhận diện lock contention kéo dài qua nhiều dump

Một thread dump là ảnh chụp tại một thời điểm. Để biết thread có bị blocked kéo dài hay chỉ chờ trong thời gian ngắn, hãy lấy nhiều snapshot cách nhau vài giây.

Linux/macOS:

~~~bash
PID=18420
jstack -l "$PID" > thread-1.txt
sleep 5
jstack -l "$PID" > thread-2.txt
sleep 5
jstack -l "$PID" > thread-3.txt
~~~

Windows PowerShell:

~~~powershell
$targetPid = 18420
1..3 | ForEach-Object {
    $file = "thread-$_.txt"
    jstack -l $targetPid | Out-File -Encoding utf8 $file
    Start-Sleep -Seconds 5
}
~~~

Khi so sánh các dump:

1. Tìm thread name và stack frame giống nhau.
2. Kiểm tra thread vẫn ở `BLOCKED` qua các snapshot hay đã chuyển sang trạng thái khác.
3. So sánh địa chỉ monitor mà thread đang chờ trong từng dump.
4. Tìm owner tương ứng và xem stack trace của owner có tiến triển không.
5. Đếm số thread đang chờ cùng monitor.
6. Đối chiếu với request latency, queue depth, throughput và CPU.

Dấu hiệu contention kéo dài gồm nhiều thread blocked trên cùng monitor trong nhiều snapshot, owner vẫn ở cùng critical section và request latency tăng. Nếu owner thay đổi hoặc các thread nhanh chóng thoát khỏi BLOCKED, đó có thể là tranh chấp ngắn hạn.

Không so sánh địa chỉ monitor giữa các lần restart JVM như định danh ổn định. Địa chỉ có thể thay đổi khi process hoặc object được tạo lại.

## 11. Xác định tác động lên thread pool và request

Blocked thread có thể làm giảm số worker sẵn sàng xử lý request. Ví dụ, một executor có 20 worker; nếu 15 worker bị blocked trên cùng một monitor, chỉ còn 5 worker có thể thực hiện công việc khác.

Khi đọc dump của ứng dụng server:

- Nhóm thread theo tên pool, chẳng hạn `http-nio-...-exec` hoặc `pool-...-thread`.
- Tìm xem nhiều worker có cùng stack frame blocked không.
- Xác định monitor owner có đang xử lý request chậm hoặc gọi dependency bên ngoài không.
- Kiểm tra queue của executor có tăng và request mới có bị chờ không.
- Đối chiếu thời điểm dump với log request và latency metrics.

Đừng chỉ tăng số thread pool để che vấn đề. Nếu mọi worker đều cần cùng một lock, tăng số worker có thể chỉ làm tăng số thread đang chờ và bộ nhớ stack mà không cải thiện throughput.

## 12. Cách khắc phục nguyên nhân blocked thread

Hướng xử lý phụ thuộc vào code đang giữ lock:

**Rút ngắn critical section.** Chỉ giữ lock quanh thao tác cập nhật trạng thái dùng chung. Thực hiện tính toán độc lập, chuyển đổi dữ liệu và chuẩn bị request bên ngoài vùng synchronized.

**Không gọi I/O hoặc dịch vụ ngoài khi đang giữ monitor.** Đọc/ghi file, truy vấn database, gọi HTTP hoặc chờ queue có thể mất thời gian không dự đoán được. Nếu cần, lấy snapshot dữ liệu dưới lock rồi gọi dependency sau khi đã nhả lock.

**Không sleep trong vùng synchronized.** Nếu cần trì hoãn, nhả lock trước khi chờ. `Thread.sleep()` không tự giải phóng monitor.

**Dùng thứ tự lấy lock nhất quán.** Nếu nhiều thao tác cần hai lock, tất cả đường code phải lấy chúng theo cùng một thứ tự toàn cục để tránh chu trình chờ.

**Giảm phạm vi chia sẻ.** Tách một lock toàn cục thành các lock theo tài nguyên hoặc partition khi tính đúng đắn cho phép. Cân nhắc concurrent collection hoặc immutable data để giảm đồng bộ hóa thủ công.

**Dùng timeout khi API lock hỗ trợ.** Với `ReentrantLock`, `tryLock(timeout, unit)` cho phép bỏ qua hoặc xử lý lại khi không lấy được lock trong thời gian quy định. Intrinsic monitor của `synchronized` không có timeout acquisition.

**Không giữ lock qua callback không kiểm soát.** Callback có thể gọi ngược vào code khác và tạo thêm phụ thuộc lock. Cân nhắc sao chép dữ liệu cần thiết, nhả lock rồi mới gọi callback.

## 13. Ví dụ thiết kế lại thứ tự lấy lock

Giả sử nhiều method cần cả `LOCK_A` và `LOCK_B`. Một quy tắc đơn giản là luôn lấy A trước B:

~~~java
private static final Object LOCK_A = new Object();
private static final Object LOCK_B = new Object();

static void updateBoth() {
    synchronized (LOCK_A) {
        synchronized (LOCK_B) {
            updateSharedState();
        }
    }
}
~~~

Mọi đường code truy cập hai lock phải tuân theo cùng thứ tự. Nếu một method khác lấy B rồi mới lấy A, nguy cơ deadlock vẫn còn.

Với code có nhiều lock, có thể định nghĩa thứ tự dựa trên ID tài nguyên hoặc thứ tự cố định của đối tượng. Việc thống nhất thứ tự giúp loại bỏ chu trình chờ do các lock đó tạo ra.

Đây là đoạn code minh họa cho quy tắc đồng bộ hóa; method `updateSharedState()` phải được cung cấp bởi ứng dụng. Không gọi code chậm hoặc I/O bên trong hai vùng lock nếu có thể đưa ra ngoài.

## 14. Phân biệt BLOCKED trên synchronized và chờ ReentrantLock

`BLOCKED` trong Java thread state chỉ mô tả việc chờ intrinsic monitor, thường liên quan tới `synchronized`.

Với `ReentrantLock`, thread chờ lock thường dùng cơ chế park. Thread dump có thể hiển thị stack tương tự:

~~~text
java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
    at java.util.concurrent.locks.ReentrantLock.lock(...)
~~~

Khi dùng `jstack -l`, phần `Locked ownable synchronizers` có thể giúp nhận diện lock mà một thread đang sở hữu. Đối chiếu stack trace của thread chờ với thông tin synchronizer của thread giữ lock.

Không bỏ qua thread `WAITING (parking)` chỉ vì câu hỏi đang điều tra blocked thread. Trong một ứng dụng, cả intrinsic monitor và explicit lock đều có thể gây contention; trạng thái và cách hiển thị trong dump khác nhau.

## 15. Dùng jcmd và các công cụ khác để đối chiếu

`jcmd` cung cấp diagnostic command `Thread.print` để in thread dump:

~~~bash
jcmd 18420 Thread.print
jcmd 18420 Thread.print -l
~~~

Lưu thread dump dạng file:

~~~bash
jcmd 18420 Thread.dump_to_file -format=plain thread-dump.txt
jcmd 18420 Thread.dump_to_file -format=json thread-dump.json
~~~

Trong JDK 24, `Thread.dump_to_file` hỗ trợ format plain hoặc JSON. Tùy chọn `-overwrite` cho phép ghi đè file đã tồn tại; mặc định là không ghi đè. Xem `jcmd PID help Thread.dump_to_file` để xác nhận cú pháp trên JVM đích.

Các công cụ chẩn đoán khác có mục tiêu riêng:

| Công cụ | Dữ liệu chính | Dùng khi |
|---|---|---|
| `jstack` | Thread state, stack trace, monitor và deadlock tại thời điểm chụp. | Điều tra blocked thread, lock contention và deadlock. |
| `JFR` | Chuỗi sự kiện runtime theo thời gian. | Điều tra latency, allocation, GC, I/O và hoạt động thread. |
| Heap dump | Object graph và trạng thái heap tại một thời điểm. | Điều tra memory leak hoặc heap tăng bất thường. |
| CPU profiler | Mẫu hoặc thời gian CPU theo method. | Tìm method tiêu tốn CPU. |

Thread dump không cho biết toàn bộ object nào đang chiếm heap và không thay thế CPU profiler. Chọn công cụ theo triệu chứng; có thể kết hợp thread dump với JFR để hiểu cả trạng thái hiện tại và lịch sử event trước đó.

## 16. Lỗi thường gặp khi phân tích blocked thread

| Triệu chứng hoặc kết luận sai | Nguyên nhân | Cách xử lý |
|---|---|---|
| Thấy một thread BLOCKED và kết luận deadlock | BLOCKED chỉ cho biết đang chờ monitor; owner có thể sớm nhả lock. | Xác định owner và lấy thêm snapshot trước khi kết luận. |
| Chỉ đọc stack trace của thread chờ | Bỏ qua code đang giữ monitor. | Tìm cùng monitor ID trong các dòng `- locked` của owner. |
| Thấy holder ở TIMED_WAITING và nghĩ nó không giữ lock | `Thread.sleep()` không nhả monitor. | Kiểm tra các dòng `- locked` và vị trí sleep trong synchronized. |
| Không thấy BLOCKED nhưng request vẫn chờ lock | Có thể đang chờ ReentrantLock hoặc synchronizer qua park. | Tìm `WAITING (parking)`, `LockSupport.park` và ownable synchronizer. |
| Nhiều worker blocked nhưng CPU thấp | Thread đang chờ lock, không tiêu thụ nhiều CPU trong lúc chờ. | Kiểm tra owner, critical section, queue depth và latency. |
| Không thấy owner trong đoạn output đã lọc | Output bị cắt hoặc owner nằm ở phần khác của dump. | Đọc toàn bộ dump và tìm cùng monitor ID. |
| Địa chỉ lock khác nhau giữa các snapshot | Object hoặc process đã thay đổi; địa chỉ không phải ID ổn định. | Đối chiếu thread name, stack và lock trong từng dump riêng. |
| Tăng thread pool nhưng throughput không tăng | Các worker mới cũng tranh chấp cùng lock. | Sửa critical section và điểm đồng bộ hóa gây nghẽn. |
| Không có dòng Java-level deadlock | Chỉ có contention hoặc deadlock nằm ngoài monitor mà JVM nhận diện. | Kiểm tra chu trình lock, database, queue, network và nhiều snapshot. |
| Thread dump không kết nối được JVM | Sai PID, khác user, Attach bị tắt hoặc sai PID namespace. | Kiểm tra `jcmd -l`, quyền và môi trường attach. |

## 17. Quy trình điều tra blocked thread trong production

1. Ghi nhận thời điểm request chậm, latency, throughput và queue depth.
2. Xác định PID, host/container, JDK version và user của JVM.
3. Lấy thread dump bằng `jstack -l PID` để có lock information.
4. Tìm các thread `BLOCKED` và gom nhóm theo monitor ID.
5. Với mỗi monitor có nhiều thread chờ, tìm owner có dòng `- locked` cùng ID.
6. Đọc stack trace của owner để xác định critical section đang giữ lock.
7. Lấy thêm hai hoặc ba snapshot cách nhau vài giây để xác nhận tình trạng kéo dài.
8. Đối chiếu owner với log, request, database, network và dependency metrics.
9. Sửa code hoặc cấu hình theo nguyên nhân thực tế; tránh tăng thread pool một cách mù quáng.
10. Kiểm thử lại bằng tải đại diện và thu thập thread dump mới để xác nhận thời gian chờ giảm.

Thread dump có thể chứa package, class, method, đường dẫn và thông tin nội bộ. Lưu file với quyền hạn phù hợp, giới hạn thời gian lưu và review trước khi chia sẻ ra ngoài tổ chức.

## 18. Checklist trước khi kết thúc điều tra

- Đã xác định đúng JVM và PID.
- Đã dùng `jstack -l` để lấy thông tin monitor.
- Đã phân biệt thread BLOCKED với RUNNABLE, WAITING và TIMED_WAITING.
- Đã tìm được monitor ID mà thread đang chờ.
- Đã tìm owner giữ cùng monitor ID.
- Đã đọc stack trace của cả thread chờ và thread giữ lock.
- Đã kiểm tra trường hợp `Thread.sleep()` bên trong synchronized.
- Đã xem xét ReentrantLock và ownable synchronizer nếu không có BLOCKED rõ ràng.
- Đã lấy nhiều snapshot khi cần xác định contention kéo dài.
- Đã kiểm tra deadlock và các phụ thuộc ngoài JVM.
- Đã đối chiếu số thread chờ với queue depth, latency và throughput.
- Đã xác định hướng sửa critical section hoặc thứ tự lock.
- Đã kiểm thử lại sau khi sửa và bảo vệ file dump theo chính sách dữ liệu.

## 19. Tài liệu tham khảo

- [The jstack Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstack.html)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Thread.State — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Thread.State.html)
- [Intrinsic Locks and Synchronization — Java Tutorials](https://docs.oracle.com/javase/tutorial/essential/concurrency/locksync.html)

`jstack` giúp điều tra blocked thread bằng cách kết hợp trạng thái `BLOCKED`, stack trace và thông tin monitor từ `jstack -l`. Hãy xác định cả thread đang chờ lẫn thread đang giữ lock, so sánh nhiều snapshot và sửa critical section hoặc thứ tự lấy lock theo nguyên nhân đã xác nhận.
