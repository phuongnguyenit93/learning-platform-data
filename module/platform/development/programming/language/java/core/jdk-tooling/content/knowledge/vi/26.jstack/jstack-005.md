# Phát hiện deadlock trong Java bằng `jstack`

Deadlock (bế tắc) xảy ra khi hai hoặc nhiều thread chờ lẫn nhau để lấy tài nguyên mà thread khác đang giữ. Không thread nào trong chu trình có thể tiếp tục, nên phần công việc liên quan bị dừng vô thời hạn.

`jstack` chụp thread dump của một JVM đang chạy và tự kiểm tra deadlock. Khi tìm thấy chu trình khóa, output có thể chứa đoạn:

~~~text
Found one Java-level deadlock:
...
~~~

Lệnh thường dùng:

~~~text
jstack -l <PID>
~~~

Tùy chọn `-l` yêu cầu in thêm thông tin về lock, bao gồm các ownable synchronizer như `ReentrantLock`. Với JDK 24.0.2, `jstack -e <PID>` bổ sung thông tin mở rộng về thread. Oracle khuyến nghị dùng `jcmd` cho chẩn đoán JVM hiện đại; lệnh tương ứng là:

~~~text
jcmd <PID> Thread.print -l
~~~

Bài học này giải thích cách tạo thread dump, đọc chu trình khóa, phân biệt deadlock với các trạng thái chờ thông thường, và tái hiện lỗi bằng Java 17+. Các lệnh và output được kiểm tra với Zulu/OpenJDK 24.0.2.

## 1. Deadlock là gì?

Giả sử hai thread cùng cần hai khóa:

- Thread A lấy khóa `LOCK_A`, sau đó chờ `LOCK_B`.
- Thread B lấy khóa `LOCK_B`, sau đó chờ `LOCK_A`.

A không thể lấy `LOCK_B` vì B đang giữ nó. B không thể lấy `LOCK_A` vì A đang giữ nó. Cả hai cùng chờ vô hạn.

~~~text
Thread A                         Thread B
--------                         --------
holds LOCK_A                     holds LOCK_B
waits for LOCK_B  -------------> held by B
held by A         <------------- waits for LOCK_A

A waits for B, and B waits for A.
No thread can make progress.
~~~

Deadlock có thể xuất hiện với:

- `synchronized` và object monitor.
- `ReentrantLock` và các ownable synchronizer khác.
- Nhiều khóa được lấy theo thứ tự không nhất quán.
- Các phụ thuộc tài nguyên khác ở cấp ứng dụng, ví dụ hai dịch vụ chờ nhau hoặc một task chờ kết quả từ executor đã cạn worker.

`jstack` tập trung vào trạng thái thread và cơ chế đồng bộ mà JVM có thể quan sát. Một deadlock ở database, network hoặc hệ thống phân tán có thể làm thread Java bị chờ, nhưng không nhất thiết xuất hiện thành một chu trình khóa Java mà `jstack` có thể tự kết luận.

## 2. Bốn điều kiện thường dẫn đến deadlock

Mô hình Coffman mô tả bốn điều kiện cần cùng tồn tại để hình thành deadlock:

1. **Mutual exclusion:** tài nguyên chỉ một thread có thể sở hữu tại một thời điểm.
2. **Hold and wait:** thread giữ ít nhất một tài nguyên trong khi chờ tài nguyên khác.
3. **No preemption:** tài nguyên không thể bị lấy cưỡng bức khỏi thread đang giữ nó.
4. **Circular wait:** tồn tại một chu trình thread chờ tài nguyên do thread tiếp theo trong chu trình giữ.

Ví dụ hai monitor trong mục trước thỏa cả bốn điều kiện. Một cách phòng ngừa hiệu quả là loại bỏ circular wait bằng cách quy định một thứ tự lấy khóa thống nhất trong toàn bộ codebase.

Không phải mọi tình trạng chậm hoặc thread ở trạng thái `BLOCKED` đều là deadlock. Có thể chỉ một thread đang chờ khóa ngắn hạn và owner sẽ sớm giải phóng khóa. Cần kiểm tra quan hệ owner/waiter và chu trình trước khi kết luận.

## 3. Deadlock detection dựa trên wait-for graph

Có thể biểu diễn quan hệ chờ bằng đồ thị:

- Node thread đại diện cho một thread.
- Node lock đại diện cho một monitor hoặc synchronizer.
- Cạnh thread → lock nghĩa là thread đang chờ khóa.
- Cạnh lock → thread nghĩa là thread đó đang sở hữu khóa.

Nếu đồ thị có chu trình, các thread trong chu trình đang deadlock trên những tài nguyên mà JVM có thể theo dõi.

Ví dụ:

~~~text
Thread-A -> LOCK_B -> Thread-B -> LOCK_A -> Thread-A
~~~

Khi phát hiện deadlock, JVM có thể báo thread nào đang chờ monitor/synchronizer nào và thread nào đang giữ nó. Đây là thông tin quan trọng nhất khi đọc phần cuối của thread dump.

Địa chỉ object/monitor như `0x000000011f019580` chỉ là định danh trong lần chụp đó. Không dùng địa chỉ này để so sánh giữa hai lần chạy khác nhau hoặc để suy ra tên biến trong source. Hãy dùng tên thread, class, method và stack frame để truy về code.

## 4. Chọn đúng JVM và PID

Trước khi chụp thread dump, xác định đúng process:

~~~text
jps -l
~~~

Ví dụ output minh họa:

~~~text
18240 com.example.OrderService
29116 com.example.ReportWorker
~~~

PID thay đổi theo lần chạy. Hãy lấy PID hiện tại, sau đó xác nhận tên ứng dụng và môi trường deploy bằng process manager hoặc command line phù hợp.

Có thể kiểm tra thêm:

~~~text
jcmd 18240 VM.version
jcmd 18240 VM.command_line
~~~

Không nhầm PID của ứng dụng trên host với PID trong container. Nếu JVM chạy trong container/PID namespace riêng, hãy tìm PID và chạy diagnostic tool từ đúng môi trường hoặc dùng quy trình truy cập container của nền tảng.

## 5. Cú pháp `jstack` và các tùy chọn

Trợ giúp của JDK 24.0.2 hiển thị:

~~~text
jstack [-l][-e] <pid>
~~~

| Lệnh/tùy chọn | Ý nghĩa |
|---|---|
| `jstack <PID>` | In stack trace của các thread trong JVM và thực hiện deadlock detection |
| `jstack -l <PID>` | In thêm thông tin lock, bao gồm ownable synchronizers |
| `jstack -e <PID>` | In thêm thông tin mở rộng về thread |
| `jstack -l -e <PID>` | Kết hợp thông tin lock và thông tin thread mở rộng |
| `jstack -h` | Hiển thị trợ giúp |

Ví dụ:

~~~text
jstack 18240
jstack -l 18240
jstack -e 18240
jstack -l -e 18240
~~~

Nếu cần chẩn đoán `ReentrantLock`, hãy ưu tiên `-l`. Không có `-l`, thread dump vẫn hiển thị stack và monitor, nhưng có thể thiếu phần thông tin về ownable synchronizer mà thread đang giữ hoặc chờ.

`-e` không thay thế `-l`: nó bổ sung thông tin thread, trong khi `-l` bổ sung thông tin lock.

## 6. Dùng `jcmd Thread.print` trong JDK hiện đại

Oracle khuyến nghị dùng `jcmd` thay cho tiện ích `jstack` cũ để chẩn đoán JVM và ứng dụng Java. `jcmd` cũng cung cấp thread dump và tùy chọn lock:

~~~text
jcmd 18240 Thread.print
jcmd 18240 Thread.print -l
jcmd 18240 Thread.print -e
jcmd 18240 Thread.print -l -e
~~~

Xem cú pháp mà JVM đích hỗ trợ:

~~~text
jcmd 18240 help Thread.print
~~~

Trong JDK 24.0.2, help của `Thread.print` cho biết:

- `-l`: in thông tin về `java.util.concurrent` locks.
- `-e`: in thông tin mở rộng về thread.
- Impact: Medium, phụ thuộc số lượng thread.

`jcmd <PID> Thread.print -l` đã được kiểm tra trên JVM có deadlock và tạo phần báo cáo deadlock tương tự `jstack -l`.

Thread dump là snapshot tại thời điểm thu thập. Lệnh in dump không tự kết thúc ứng dụng; JVM tiếp tục chạy sau khi output được tạo.

## 7. Cách đọc một thread dump

Một thread entry thường có:

- Tên thread, ví dụ `"worker-A"`.
- Thread ID và native thread ID.
- Priority và trạng thái hiện tại.
- Stack trace cho biết thread đang ở method nào.
- Monitor hoặc synchronizer thread đang chờ và đang giữ.

Ví dụ rút gọn:

~~~text
"worker-A" #35 prio=5 ... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.OrderService.update(OrderService.java:42)
    - waiting to lock <0x000000011f019590> (a java.lang.Object)
    - locked <0x000000011f019580> (a java.lang.Object)
~~~

Cách đọc:

- `BLOCKED (on object monitor)`: thread đang chờ vào một `synchronized` block/method.
- `waiting to lock`: monitor mà thread muốn lấy.
- `locked`: monitor thread đang giữ.
- Stack frame `OrderService.update(...:42)`: vị trí code đang chờ khóa.

Với `ReentrantLock`, thread thường hiển thị `WAITING (parking)` và stack có thể đi qua `LockSupport.park`, `AbstractQueuedSynchronizer` hoặc `ReentrantLock.lock`. Đây là chờ synchronizer; không nhất thiết là deadlock nếu chưa có chu trình.

### 7.1. Trạng thái thread cần phân biệt

| State | Cách hiểu thường gặp |
|---|---|
| `RUNNABLE` | Thread đang chạy hoặc sẵn sàng chạy trong JVM; không nhất thiết đang dùng CPU liên tục |
| `BLOCKED` | Đang chờ lấy object monitor |
| `WAITING` | Đang chờ vô thời hạn một hành động khác, ví dụ `Object.wait()` hoặc park |
| `TIMED_WAITING` | Đang chờ có thời hạn, ví dụ `sleep()` hoặc timed wait |
| `TERMINATED` | Thread đã kết thúc |

Một thread `BLOCKED` không tự chứng minh deadlock. Một thread `WAITING` hoặc `TIMED_WAITING` cũng có thể hoàn toàn bình thường. Hãy xem lock owner, stack frame và phần deadlock summary.

## 8. Nhận diện phần deadlock summary

Khi JVM phát hiện chu trình, phần cuối output có thể giống:

~~~text
Found one Java-level deadlock:
=============================

"worker-A":
  waiting to lock monitor ... (object 0x..., a java.lang.Object),
  which is held by "worker-B"

"worker-B":
  waiting to lock monitor ... (object 0x..., a java.lang.Object),
  which is held by "worker-A"
~~~

Đây là bằng chứng rõ ràng cho chu trình hai thread:

- `worker-A` cần monitor do `worker-B` giữ.
- `worker-B` cần monitor do `worker-A` giữ.
- Không thread nào có thể tiến lên để giải phóng monitor còn lại.

Nếu có nhiều chu trình độc lập, output có thể báo nhiều deadlock. Đừng chỉ đếm thread ở trạng thái `BLOCKED`; một deadlock có thể gồm nhiều thread và nhiều lock.

Khi không có dòng deadlock summary, không thể kết luận ứng dụng hoàn toàn không bị bế tắc. Thread có thể chờ database, network, future, executor, distributed lock hoặc một điều kiện nghiệp vụ mà JVM không thể biểu diễn thành chu trình monitor/synchronizer.

## 9. Monitor deadlock với `synchronized`

` synchronized` sử dụng object monitor. Ví dụ:

~~~java
synchronized (LOCK_A) {
    synchronized (LOCK_B) {
        // critical section
    }
}
~~~

Nếu một thread lấy A rồi B, trong khi thread khác lấy B rồi A, hai thread có thể deadlock.

Trong thread dump, monitor thường được hiển thị bằng object identity:

~~~text
- waiting to lock <0x...> (a java.lang.Object)
- locked <0x...> (a java.lang.Object)
~~~

Đối chiếu object ID giữa các thread giúp xác định monitor mà một thread chờ đang được thread khác giữ. Phần summary thường làm việc này rõ hơn bằng câu `which is held by`.

Khi điều tra source:

1. Tìm method và dòng code từ stack frame.
2. Xác định object được dùng làm monitor.
3. Tìm tất cả code path có thể lấy cùng monitor.
4. Kiểm tra thứ tự lấy nhiều monitor.
5. Đối chiếu với các thread khác trong chu trình.

Không sửa bằng cách đổi tên thread hoặc thêm `sleep()`. Cần sửa thứ tự đồng bộ hoặc thiết kế vùng critical section.

## 10. Ownable synchronizer và `ReentrantLock`

`ReentrantLock` không dùng cú pháp `synchronized`; nó dựa trên ownable synchronizer. Vì vậy, khi điều tra loại khóa này, dùng `-l`:

~~~text
jstack -l 18240
~~~

Ví dụ output rút gọn:

~~~text
"lock-A":
   java.lang.Thread.State: WAITING (parking)
    at java.util.concurrent.locks.ReentrantLock.lock(...)
    - parking to wait for <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
   Locked ownable synchronizers:
    - <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)

"lock-B":
   java.lang.Thread.State: WAITING (parking)
    at java.util.concurrent.locks.ReentrantLock.lock(...)
    - parking to wait for <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
   Locked ownable synchronizers:
    - <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
~~~

Deadlock summary cho ownable synchronizer có thể nói:

~~~text
Found one Java-level deadlock:

"lock-A":
  waiting for ownable synchronizer ...,
  which is held by "lock-B"

"lock-B":
  waiting for ownable synchronizer ...,
  which is held by "lock-A"
~~~

Điểm cần nhớ:

- `-l` bổ sung thông tin về `java.util.concurrent` locks.
- `WAITING (parking)` có thể là thread đang chờ `ReentrantLock`.
- Chỉ khi owner/waiter tạo chu trình mới kết luận deadlock.
- Dùng `unlock()` trong `finally` để bảo đảm giải phóng khóa sau khi rời critical section; điều này giúp quản lý vòng đời khóa nhưng không tự ngăn circular wait.

## 11. Ví dụ Java 17+: tạo deadlock có thể tái hiện

Chương trình sau tạo hai monitor và hai thread. `CountDownLatch` đồng bộ điểm bắt đầu để mỗi thread giữ một monitor trước khi cả hai cùng thử lấy monitor còn lại.

Tạo file `DeadlockDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class DeadlockDemo {
    private static final Object LOCK_A = new Object();
    private static final Object LOCK_B = new Object();
    private static final CountDownLatch READY = new CountDownLatch(2);
    private static final CountDownLatch START = new CountDownLatch(1);

    private DeadlockDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        Thread first = new Thread(() -> {
            synchronized (LOCK_A) {
                READY.countDown();
                awaitStart();
                synchronized (LOCK_B) {
                    System.out.println("worker-A acquired both locks");
                }
            }
        }, "worker-A");

        Thread second = new Thread(() -> {
            synchronized (LOCK_B) {
                READY.countDown();
                awaitStart();
                synchronized (LOCK_A) {
                    System.out.println("worker-B acquired both locks");
                }
            }
        }, "worker-B");

        first.start();
        second.start();

        READY.await();
        START.countDown();

        System.out.println("DEADLOCK_DEMO_READY");
        Thread.sleep(300_000);
    }

    private static void awaitStart() {
        try {
            START.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Biên dịch bằng Java 17+:

~~~text
javac --release 17 DeadlockDemo.java
~~~

Chạy:

~~~text
java DeadlockDemo
~~~

Stdout:

~~~text
DEADLOCK_DEMO_READY
~~~

Sau khi thấy dòng trên, mở terminal thứ hai và tìm PID:

~~~text
jps -l
~~~

Giả sử PID của `DeadlockDemo` là `18240`, chụp thread dump:

~~~text
jstack -l 18240
~~~

Hoặc dùng `jcmd`:

~~~text
jcmd 18240 Thread.print -l
~~~

Kết quả mong đợi gồm:

- Thread `"worker-A"` ở trạng thái `BLOCKED`.
- Thread `"worker-B"` ở trạng thái `BLOCKED`.
- Một monitor mỗi thread đang giữ.
- Một monitor mỗi thread đang chờ.
- Phần `Found one Java-level deadlock` chỉ rõ hai thread giữ khóa cho nhau.

Hai dòng `worker-A acquired both locks` và `worker-B acquired both locks` sẽ không xuất hiện vì chương trình cố ý tạo deadlock. Khi kết thúc bài lab, dừng process thử nghiệm bằng `Ctrl+C` trong terminal chạy chương trình hoặc dừng đúng PID bằng process manager. Không để chương trình deadlock tiếp tục chạy nền.

## 12. Biến thể `ReentrantLock`

Có thể tái hiện cùng lỗi với hai `ReentrantLock`:

~~~java
private static final ReentrantLock LOCK_A = new ReentrantLock();
private static final ReentrantLock LOCK_B = new ReentrantLock();

static void firstPath() {
    LOCK_A.lock();
    try {
        LOCK_B.lock();
        try {
            // critical section
        } finally {
            LOCK_B.unlock();
        }
    } finally {
        LOCK_A.unlock();
    }
}

static void secondPath() {
    LOCK_B.lock();
    try {
        LOCK_A.lock();
        try {
            // critical section
        } finally {
            LOCK_A.unlock();
        }
    } finally {
        LOCK_B.unlock();
    }
}
~~~

Đây là hai code path minh họa thứ tự lấy khóa ngược nhau. Nếu hai thread chạy đồng thời và mỗi thread lấy được khóa đầu tiên, chúng có thể chờ nhau vô hạn ở khóa thứ hai.

Để phân tích loại deadlock này, dùng `jstack -l` hoặc `jcmd <PID> Thread.print -l`. Không bỏ `-l` khi cần xem ownable synchronizer details.

## 13. Phát hiện deadlock bằng `ThreadMXBean`

Ứng dụng cũng có thể kiểm tra deadlock bằng Management API. `ThreadMXBean.findDeadlockedThreads()` tìm chu trình liên quan đến object monitor và ownable synchronizer trên platform threads.

Ví dụ:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public final class DeadlockCheck {
    private DeadlockCheck() {
    }

    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        long[] ids = bean.findDeadlockedThreads();

        if (ids == null) {
            System.out.println("NO_PLATFORM_DEADLOCK");
            return;
        }

        ThreadInfo[] infos = bean.getThreadInfo(ids, true, true);
        for (ThreadInfo info : infos) {
            if (info != null) {
                System.out.println(
                        "DEADLOCK_THREAD=" + info.getThreadName());
            }
        }
    }
}
~~~

Biên dịch:

~~~text
javac --release 17 DeadlockCheck.java
~~~

Chương trình phải chạy bên trong cùng JVM cần kiểm tra. Nó không thể kiểm tra JVM khác chỉ bằng cách gọi `ManagementFactory.getThreadMXBean()`.

`findMonitorDeadlockedThreads()` chỉ tìm deadlock liên quan đến object monitor. `findDeadlockedThreads()` mở rộng sang ownable synchronizer như `ReentrantLock`. API được thiết kế cho troubleshooting, không dùng làm cơ chế điều khiển đồng bộ trong business logic; thao tác có thể tốn chi phí và JVM có thể không hỗ trợ monitor/synchronizer usage monitoring.

JDK 24 API mô tả các phương thức này tìm deadlock của platform threads; chu trình có virtual thread không được các phương thức này phát hiện. Nếu ứng dụng sử dụng virtual threads, hãy xác nhận giới hạn của phiên bản JDK và kết hợp thread dump, JFR, application tracing và các công cụ quan sát phù hợp.

## 14. Thu thập thread dump trong production

Khi production bị treo hoặc có dấu hiệu deadlock:

1. Xác định đúng host/container, service và PID.
2. Ghi nhận thời gian, phiên bản JDK và triệu chứng người dùng gặp.
3. Chụp thread dump bằng `jcmd <PID> Thread.print -l`.
4. Nếu cần, chụp thêm một hoặc hai dump cách nhau vài giây để so sánh.
5. Giữ nguyên timestamp và PID của từng dump.
6. Tìm deadlock summary, thread name, lock owner và stack frame.
7. Đối chiếu với log ứng dụng, request ID, database monitoring và metrics.
8. Chỉ restart hoặc kill process theo quy trình incident sau khi đã lưu bằng chứng cần thiết.

Ví dụ lưu output trong PowerShell:

~~~powershell
$javaPid = 18240
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

jcmd $javaPid Thread.print -l |
    Set-Content -Encoding UTF8 ".\thread-dump-$stamp.txt"
~~~

macOS/Linux:

~~~sh
java_pid=18240
stamp=$(date +%Y%m%d-%H%M%S)

jcmd "$java_pid" Thread.print -l \
    > "thread-dump-$stamp.txt"
~~~

Thread dump có thể chứa tên class, đường dẫn, SQL, URL và dữ liệu nghiệp vụ nằm trong stack hoặc thread name. Bảo vệ file như log vận hành nhạy cảm; chỉ chia sẻ với người có quyền truy cập phù hợp.

Không chụp thread dump liên tục với tần suất cao khi hệ thống đang quá tải. Mỗi lần dump phải attach và thu thập stack của nhiều thread; `jcmd Thread.print` có impact Medium phụ thuộc số lượng thread.

## 15. Deadlock, contention, starvation và livelock

Các tình trạng sau có biểu hiện giống nhau nhưng nguyên nhân khác:

| Hiện tượng | Biểu hiện | Cách phân biệt |
|---|---|---|
| Deadlock | Một nhóm thread chờ lẫn nhau vô hạn | Có chu trình owner/waiter hoặc deadlock summary |
| Lock contention | Nhiều thread tranh một lock | Có owner bận; không nhất thiết có chu trình |
| Starvation | Một thread không được cấp CPU/lock hoặc tài nguyên đủ lâu | Không nhất thiết có chu trình khóa |
| Livelock | Thread vẫn hoạt động nhưng liên tục nhường/đổi trạng thái và không hoàn thành | CPU có thể vẫn hoạt động; không có deadlock lock cycle |
| I/O hang | Thread chờ network, file hoặc database | Stack thường dừng ở I/O/JDBC/socket; JVM không nhất thiết tìm thấy chu trình |

Nếu không có deadlock summary nhưng ứng dụng vẫn treo, hãy kiểm tra:

- Thread có đang chờ `Future.get()` hoặc `CompletableFuture.join()` không?
- Thread pool có hết worker vì các task chờ lẫn nhau không?
- JDBC call có chờ database lock hoặc connection pool không?
- Network request có timeout không?
- Có distributed lock hoặc message dependency giữa các service không?

`jstack` cho biết thread đang ở đâu; nó không thay thế tracing, database deadlock report hoặc phân tích dependency giữa các hệ thống.

## 16. Cách phòng ngừa deadlock

Các biện pháp có hiệu quả thực tế:

**Thống nhất thứ tự lấy khóa.** Nếu code cần A và B, mọi code path đều lấy A trước B. Không để một path lấy B rồi A.

**Giảm phạm vi critical section.** Chỉ giữ khóa trong đoạn code cần bảo vệ state. Tránh thực hiện network I/O, database call hoặc callback không kiểm soát khi đang giữ lock.

**Tránh nested lock nếu không cần.** Mỗi lớp khóa lồng nhau làm tăng số quan hệ cần kiểm soát.

**Dùng timeout hoặc interruptible acquisition khi phù hợp.** `ReentrantLock.tryLock(timeout, unit)` và `lockInterruptibly()` cho phép thiết kế đường thoát; cần xử lý retry/backoff và rollback đúng nghiệp vụ.

**Không chờ Future trong cùng executor đã cạn worker.** Thiết kế task dependency và executor capacity để tránh thread pool starvation.

**Ưu tiên immutable object và concurrency utilities.** Giảm chia sẻ mutable state giúp giảm số khóa và nguy cơ circular wait.

**Tài liệu hóa lock order.** Ghi rõ thứ tự khóa ở API/class có nhiều critical section và review khi thêm khóa mới.

`try/finally` để gọi `unlock()` là bắt buộc với `ReentrantLock`, nhưng chỉ bảo đảm giải phóng khóa khi code thoát khỏi vùng giữ khóa. Nó không tự giải quyết một chu trình mà cả hai thread đều đang chờ trước khi vào `finally`.

## 17. Troubleshooting thường gặp

### `jstack` không kết nối được process

**Nguyên nhân:** PID sai, process đã thoát, chạy khác user, attach bị vô hiệu hóa hoặc process nằm trong namespace khác.

**Cách xử lý:** xác nhận PID bằng `jps -l`/OS process manager, kiểm tra user và `-XX:+DisableAttachMechanism`, chạy tool trên đúng host/container.

### Thread dump có `BLOCKED` nhưng không có deadlock summary

**Nguyên nhân:** thread đang chờ monitor nhưng owner có thể sẽ giải phóng khóa; chưa có chu trình.

**Cách xử lý:** xem owner và stack của cả hai bên, chụp thêm dump sau vài giây và xác định có chu trình hay không.

### Không thấy `ReentrantLock` trong output

**Nguyên nhân:** dump được chụp không có tùy chọn long listing.

**Cách xử lý:** dùng `jstack -l <PID>` hoặc `jcmd <PID> Thread.print -l`.

### Thread ở `WAITING (parking)` nhưng không rõ lý do

**Nguyên nhân:** thread có thể đang chờ `ReentrantLock`, semaphore, condition, executor hoặc một cơ chế park khác.

**Cách xử lý:** xem stack frame quanh `LockSupport.park`, `AbstractQueuedSynchronizer`, `ReentrantLock` và phần owner/synchronizer details.

### Không có deadlock summary nhưng request vẫn treo

**Nguyên nhân:** ứng dụng có thể đang chờ database, network, future, queue hoặc distributed lock mà JVM không nhận diện thành monitor cycle.

**Cách xử lý:** kết hợp thread dump với application tracing, database monitoring, request log, timeout và executor metrics.

### Deadlock biến mất trước khi chụp dump

**Nguyên nhân:** lỗi xảy ra theo tải hoặc timing; một thread đã thoát khỏi chu trình trước thời điểm capture.

**Cách xử lý:** lưu dump ngay khi alert xảy ra, ghi timestamp và tương quan với log. Cân nhắc JFR hoặc telemetry để thu thập sự kiện trước khi sự cố kết thúc.

### `ThreadMXBean.findDeadlockedThreads()` trả `null`

**Nguyên nhân:** không có chu trình platform-thread monitor/ownable synchronizer tại thời điểm gọi; hoặc deadlock nằm ở tài nguyên ngoài phạm vi API.

**Cách xử lý:** xác nhận thời điểm kiểm tra và kiểm tra thêm I/O, executor, database, distributed lock và virtual thread limitations.

## 18. Checklist điều tra deadlock

- [ ] Đã xác định đúng JVM, host/container và PID.
- [ ] Đã ghi nhận JDK vendor/version và thời điểm chụp.
- [ ] Đã chụp `jcmd <PID> Thread.print -l` hoặc `jstack -l <PID>`.
- [ ] Đã dùng `-l` để xem ownable synchronizer khi có `ReentrantLock`.
- [ ] Đã xem phần `Found one Java-level deadlock` nếu có.
- [ ] Đã xác định thread nào chờ lock nào và thread nào đang giữ lock.
- [ ] Đã truy ngược stack frame đến class, method và dòng source.
- [ ] Đã phân biệt `BLOCKED`, `WAITING` và `TIMED_WAITING`.
- [ ] Đã kiểm tra thêm thread dump nếu cần xác nhận trạng thái kéo dài.
- [ ] Đã xem xét deadlock ở database, network, executor hoặc distributed system.
- [ ] Đã bảo vệ thread dump vì output có thể chứa dữ liệu nhạy cảm.
- [ ] Đã xác định lock order hoặc dependency gây circular wait.
- [ ] Đã sửa và kiểm thử lại các code path lấy khóa.
- [ ] Đã xác nhận hệ thống phục hồi và không còn chu trình deadlock.

## 19. Tài liệu tham khảo

- Oracle JDK 24 — Diagnostic Tools, phần `jstack`, thread dump và deadlock detection: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — `jcmd` Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Java SE 24 — `ThreadMXBean` API: https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Java SE 24 — `ReentrantLock` API: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html

`jstack -l` giúp xác định chu trình giữa thread và monitor/ownable synchronizer; `jcmd <PID> Thread.print -l` là lựa chọn được Oracle khuyến nghị cho chẩn đoán hiện đại. Hãy dựa vào deadlock summary, lock owner và stack frame để tìm code gây circular wait, sau đó sửa thứ tự lấy khóa hoặc thiết kế phụ thuộc tài nguyên.