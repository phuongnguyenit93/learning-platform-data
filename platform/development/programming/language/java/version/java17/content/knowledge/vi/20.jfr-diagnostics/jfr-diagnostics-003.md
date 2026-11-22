# Thread dump để phân tích chờ, khóa và deadlock trong Java 17

**Chủ đề:** Java 17 → Chẩn đoán và JFR  
**Trọng tâm:** Thu thập và đọc thread dump để tìm thread đang chờ, tranh chấp khóa, thread pool bị nghẽn và deadlock; hiểu trạng thái thread, monitor, ownable synchronizer, lock owner và cách kết hợp nhiều snapshot với các công cụ chẩn đoán của JDK 17.

Thread dump là ảnh chụp trạng thái các thread của JVM tại một thời điểm. Nó cho biết thread đang chạy ở stack frame nào, đang chờ monitor hay synchronizer nào, thread nào đang giữ khóa và JVM có phát hiện chu trình deadlock hay không. Đây là dữ liệu quan trọng khi ứng dụng phản hồi chậm, một request bị treo, CPU tăng cao hoặc các worker không tiến triển.

Trong JDK 17, cách thực tế để lấy thread dump từ một JVM đang chạy là dùng **`jcmd <pid> Thread.print -l`**. Tùy chọn `-l` yêu cầu in thêm thông tin về các khóa của `java.util.concurrent`. Một dump đơn lẻ chỉ phản ánh một thời điểm; để phân biệt trạng thái chờ bình thường với thread bị kẹt, thường cần thu thập nhiều dump cách nhau một khoảng thời gian và so sánh.

## 1. Thread dump chứa những gì?

Một thread dump thường chứa các nhóm thông tin:

- **Thread header:** tên thread, thread ID, priority, trạng thái native hoặc thông tin CPU/thời gian nếu JVM cung cấp.
- **Thread state:** `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` và các trạng thái vòng đời khác.
- **Stack trace:** chuỗi lời gọi method tại thời điểm chụp.
- **Monitor information:** monitor mà thread đang giữ, đang chờ để vào hoặc đang chờ được đánh thức.
- **Ownable synchronizers:** các khóa đồng bộ như `ReentrantLock` và synchronizer dựa trên `AbstractOwnableSynchronizer`.
- **Deadlock report:** nếu JVM phát hiện chu trình khóa deadlock ở thời điểm chụp.

Một thread dump là snapshot chẩn đoán. Nó không phải lịch sử đầy đủ của thread, không cho biết chính xác thread đã ở trạng thái đó bao lâu nếu không có dữ liệu bổ sung, và không tự giải thích nguyên nhân nghiệp vụ của một lời gọi đang chờ.

## 2. Lấy thread dump bằng jcmd trên JDK 17

`jcmd` là công cụ chẩn đoán đi kèm JDK. Nó gửi diagnostic command tới một JVM đang chạy trên cùng máy và trả về kết quả. Với Java 17, lệnh thường dùng:

~~~shell
jcmd -l
~~~

Lệnh này liệt kê các tiến trình Java mà công cụ có thể nhận diện. Sau khi xác định PID của ứng dụng:

~~~shell
jcmd <pid> Thread.print -l
~~~

Ví dụ nếu PID là `12345`:

~~~shell
jcmd 12345 Thread.print -l
~~~

`Thread.print` in stack trace của các thread. Tùy chọn `-l` in thêm thông tin về các khóa `java.util.concurrent`, hữu ích khi điều tra `ReentrantLock` hoặc các synchronizer tương tự.

### 2.1. Lưu dump vào file

Trên Linux/macOS:

~~~shell
jcmd 12345 Thread.print -l > thread-dump-01.txt 2>&1
~~~

Trên Windows PowerShell:

~~~powershell
jcmd 12345 Thread.print -l | Out-File -Encoding utf8 thread-dump-01.txt
~~~

Ghi lại thời điểm, PID, hostname/container và tải hệ thống cùng file dump. Khi so sánh nhiều snapshot, các metadata này giúp xác định dump nào thuộc cùng một JVM và được thu thập trong điều kiện nào.

### 2.2. Tùy chọn mở rộng

JDK 17 hỗ trợ các tùy chọn của `Thread.print`:

| Lệnh | Ý nghĩa |
| --- | --- |
| `jcmd <pid> Thread.print` | In thread dump và stack trace. |
| `jcmd <pid> Thread.print -l` | In thêm thông tin về các khóa `java.util.concurrent`. |
| `jcmd <pid> Thread.print -e` | In extended thread information. |
| `jcmd <pid> Thread.print -e -l` | Kết hợp thông tin mở rộng và thông tin khóa. |

Có thể xem mô tả chính xác của command trên JDK đang chạy bằng:

~~~shell
jcmd <pid> help Thread.print
~~~

Tùy chọn được hỗ trợ phụ thuộc vào command và phiên bản JDK. Khi điều tra trên production, ưu tiên lệnh ngắn gọn đủ thông tin và kiểm tra help của chính JVM mục tiêu.

### 2.3. jstack là lựa chọn khác

JDK cũng cung cấp `jstack` để in stack trace của các thread:

~~~shell
jstack -l 12345
~~~

`-l` yêu cầu in thêm thông tin về các khóa. `jstack` vẫn là công cụ có trong JDK 17, nhưng trong quy trình chẩn đoán hiện nay có thể ưu tiên `jcmd` vì nó cung cấp một giao diện thống nhất để gửi nhiều diagnostic command tới JVM.

### 2.4. Tín hiệu hệ điều hành

Trên hệ điều hành Unix-like, gửi `SIGQUIT` tới tiến trình Java thường khiến HotSpot in thread dump ra standard output của JVM (console/log mà tiến trình đang ghi):

~~~shell
kill -3 12345
~~~

Tín hiệu này được JVM xử lý để tạo dump; nó không có nghĩa là yêu cầu JVM thoát như `SIGTERM`. Dump thường xuất hiện trong log hoặc console của tiến trình, không nhất thiết ở terminal đang chạy lệnh `kill`.

Trên Windows, `Ctrl+Break` trong console gắn với tiến trình Java có thể yêu cầu JVM in thread dump. Với môi trường service/container không có console tương tác, dùng `jcmd` thường thuận tiện hơn.

## 3. Điều kiện để jcmd kết nối được tới JVM

`jcmd` thường cần chạy trên cùng máy với tiến trình Java mục tiêu và dưới cùng user phù hợp. Một số yếu tố có thể ảnh hưởng:

- JVM chạy trong container hoặc namespace khác, khiến PID/đường dẫn attach không giống host.
- User hiện tại không có quyền attach tới tiến trình.
- JVM được khởi chạy với cơ chế tắt attach.
- JDK dùng để chạy `jcmd` không tương thích hoặc không thể tìm đúng tiến trình.
- Tiến trình đang quá tải hoặc ở trạng thái khiến thao tác attach không phản hồi nhanh.

Nếu `jcmd -l` không thấy tiến trình, hãy xác minh PID ở hệ điều hành, user, container và JDK của ứng dụng. Không nên kết luận JVM đã dừng chỉ vì danh sách của `jcmd` không hiển thị nó.

Trong production, hãy lưu ý thread dump có thể chứa tên lớp, đường dẫn, tên tài khoản, SQL, URL hoặc dữ liệu nhạy cảm xuất hiện trong stack trace và tên thread. Bảo vệ file dump theo chính sách log và dữ liệu vận hành của hệ thống.

## 4. Hiểu các trạng thái thread trong Java

`java.lang.Thread.State` định nghĩa sáu trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `NEW` | Thread đã được tạo nhưng chưa gọi `start()`. |
| `RUNNABLE` | Thread đang chạy trong JVM hoặc sẵn sàng được hệ điều hành cấp CPU; cũng có thể đang thực hiện I/O native. |
| `BLOCKED` | Thread đang chờ lấy intrinsic monitor để vào một `synchronized` block/method. |
| `WAITING` | Thread chờ vô thời hạn một hành động từ thread khác. |
| `TIMED_WAITING` | Thread chờ trong một khoảng thời gian giới hạn. |
| `TERMINATED` | Thread đã kết thúc. |

Thread dump thường tập trung vào các thread đang tồn tại. Không phải mọi trạng thái trong enum đều xuất hiện trong mỗi dump.

### 4.1. RUNNABLE

`RUNNABLE` không bảo đảm thread đang tiêu thụ CPU tại đúng thời điểm chụp. Thread có thể đang:

- Thực thi bytecode.
- Sẵn sàng chạy nhưng chờ CPU.
- Ở trong một lời gọi native hoặc I/O mà JVM vẫn báo `RUNNABLE`.

Muốn xác định một thread `RUNNABLE` có phải nguyên nhân CPU cao, cần xem stack trace và đối chiếu CPU time, OS thread hoặc JFR. Một snapshot chỉ cho biết thread đang ở đâu, không đủ để chứng minh nó là CPU hot spot.

### 4.2. BLOCKED

`BLOCKED` có nghĩa thread đang chờ lấy một intrinsic monitor, thường do một thread khác đang giữ khóa của `synchronized` block hoặc method.

Ví dụ:

~~~java
public class SharedCounter {
    private int value;

    public synchronized void increment() {
        value++;
    }
}
~~~

Nếu thread A đang ở trong `increment()` và giữ monitor của `SharedCounter`, thread B gọi `increment()` trên cùng object sẽ phải chờ. Trong dump, B có thể xuất hiện:

~~~text
java.lang.Thread.State: BLOCKED (on object monitor)
    at SharedCounter.increment(SharedCounter.java:5)
    - waiting to lock <0x00000000...> (a SharedCounter)
~~~

Thread đang `BLOCKED` chưa sở hữu monitor mà nó đang chờ. Cần tìm thread đang giữ đúng monitor đó để hiểu vì sao nó chưa được giải phóng.

### 4.3. WAITING

`WAITING` là trạng thái chờ vô thời hạn cho một sự kiện hoặc hành động khác. Các nguyên nhân thường gặp:

- `Object.wait()` không có timeout.
- `Thread.join()` không có timeout.
- `LockSupport.park()`.
- Các cấu trúc đồng bộ dựa trên `AbstractQueuedSynchronizer`, ví dụ `ReentrantLock`, `Condition`, `CountDownLatch` hoặc `FutureTask`.

Trong dump, có thể thấy:

~~~text
java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
~~~

Stack trên thường xuất hiện khi thread đang park để chờ một synchronizer hoặc sự kiện. Nó không tự động có nghĩa là deadlock. Ví dụ, worker thread đang rảnh và chờ task trong queue có thể hoàn toàn bình thường.

Khi gọi `Object.wait()`, thread phải đang sở hữu monitor tương ứng; JVM giải phóng monitor đó trong lúc thread chờ và thread chỉ tiếp tục sau khi được notify/notifyAll, được đánh thức bởi interrupt hoặc điều kiện liên quan khác. Đây là khác biệt với `BLOCKED`, nơi thread đang chờ để lấy monitor và chưa vào vùng synchronized.

### 4.4. TIMED_WAITING

`TIMED_WAITING` là chờ có timeout. Ví dụ:

- `Thread.sleep(timeout)`.
- `Object.wait(timeout)`.
- `Thread.join(timeout)`.
- `LockSupport.parkNanos(...)` hoặc `parkUntil(...)`.

Ví dụ dump:

~~~text
java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(Native Method)
~~~

Một thread ngủ theo lịch hoặc chờ timeout có thể là hành vi dự kiến. Cần xem code path, timeout và số lần lặp để xác định có bất thường hay không.

## 5. Phân biệt monitor và ownable synchronizer

Java có nhiều cơ chế khóa. Thread dump cần được đọc đúng loại khóa để không nhầm lẫn.

### 5.1. Intrinsic monitor

Monitor là cơ chế đồng bộ gắn với mọi object Java và được sử dụng bởi `synchronized`.

Ví dụ:

~~~java
synchronized (lock) {
    updateState();
}
~~~

Một thread vào vùng đồng bộ sẽ sở hữu monitor của `lock`. Thread khác muốn vào vùng đồng bộ trên cùng object phải chờ.

Thread dump có thể ghi:

~~~text
- locked <0x00000000...> (a java.lang.Object)
- waiting to lock <0x00000000...> (a java.lang.Object)
- waiting on <0x00000000...> (a java.lang.Object)
~~~

Ý nghĩa:

- `locked`: thread đang giữ monitor.
- `waiting to lock`: thread đang chờ để lấy monitor.
- `waiting on`: thread đã gọi `Object.wait()` trên monitor và đang chờ được đánh thức.

### 5.2. Ownable synchronizer

Các khóa như `ReentrantLock` không sử dụng cú pháp `synchronized`, nhưng vẫn có cơ chế sở hữu và chờ. Chúng thường dựa trên `AbstractOwnableSynchronizer` hoặc `AbstractQueuedSynchronizer`.

Khi dùng:

~~~java
ReentrantLock lock = new ReentrantLock();

lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
~~~

Thread chờ khóa có thể ở `WAITING (parking)` thay vì `BLOCKED`, bởi nó đang park trong cơ chế synchronizer. Nếu chạy `Thread.print -l`, phần thông tin khóa bổ sung có thể cho biết ownable synchronizer đang bị giữ.

Ví dụ phần cuối dump:

~~~text
Locked ownable synchronizers:
    - <0x00000000...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
~~~

Đừng chỉ tìm từ `BLOCKED` khi điều tra lock contention. Với `ReentrantLock`, `Semaphore` và các cấu trúc concurrent khác, thread có thể ở trạng thái waiting/parking.

## 6. Đọc cấu trúc một thread entry

Một entry minh họa có thể trông như sau:

~~~text
"worker-3" #28 prio=5 os_prio=0 cpu=120.00ms elapsed=42.10s
   tid=0x000001f... nid=0x2a34 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.service.OrderService.update(OrderService.java:84)
    at com.example.worker.OrderWorker.run(OrderWorker.java:41)
    - waiting to lock <0x00000000...> (a com.example.service.OrderService)
~~~

Các trường thường gặp:

| Trường | Ý nghĩa |
| --- | --- |
| `"worker-3"` | Tên thread do ứng dụng hoặc runtime đặt. |
| `#28` | Thread ID trong JVM dump. |
| `prio=5` | Priority của thread. |
| `cpu=...` | CPU time nếu định dạng/runtime cung cấp. |
| `elapsed=...` | Thời gian thread đã tồn tại hoặc elapsed information theo định dạng dump. |
| `tid=...` | Định danh thread nội bộ của JVM. |
| `nid=...` | Native thread ID trên hệ điều hành. |
| `java.lang.Thread.State` | Trạng thái Java-level. |
| `at ...` | Stack frame, thường đọc từ frame trên cùng xuống dưới. |
| `waiting to lock` | Monitor mà thread đang chờ. |

Định dạng chính xác thay đổi theo nhà cung cấp JVM và phiên bản JDK. Không nên parse thread dump bằng regex cứng dựa trên một ví dụ duy nhất nếu công cụ phải hỗ trợ nhiều runtime.

## 7. Phân tích lock contention

Lock contention xảy ra khi nhiều thread cùng cần một khóa và phải xếp hàng chờ. Nó có thể làm giảm throughput ngay cả khi không có deadlock.

### 7.1. Dấu hiệu trong dump

- Nhiều thread ở trạng thái `BLOCKED`.
- Nhiều stack trace có cùng frame đang chờ một monitor.
- Các thread cùng chờ một object ID.
- Một thread giữ monitor đó nhưng stack trace ở trong đoạn xử lý lâu.
- Với synchronizer, nhiều thread `WAITING (parking)` và phần ownable synchronizer chỉ ra cùng một lock owner.

### 7.2. Tìm lock owner

Giả sử dump có:

~~~text
"request-12":
    java.lang.Thread.State: BLOCKED (on object monitor)
    - waiting to lock <0x1234> (a com.example.Cache)

"request-15":
    java.lang.Thread.State: BLOCKED (on object monitor)
    - waiting to lock <0x1234> (a com.example.Cache)

"cache-maintenance":
    java.lang.Thread.State: RUNNABLE
    - locked <0x1234> (a com.example.Cache)
    at com.example.Cache.rebuild(Cache.java:120)
~~~

Hai request đang chờ cùng monitor `<0x1234>`. Thread `cache-maintenance` đang giữ monitor đó và thực thi `Cache.rebuild`. Đây là dấu hiệu contention quanh vùng critical section của cache.

Tiếp theo cần xem:

1. `rebuild` có thực hiện I/O, gọi network hoặc truy vấn database trong khi giữ khóa không?
2. Vòng lặp hoặc thao tác bên trong có thời gian xử lý dài không?
3. Có thể giảm phạm vi `synchronized` hoặc chuyển công việc nặng ra ngoài vùng giữ khóa không?
4. Có thể thay một khóa toàn cục bằng khóa theo key/partition không?

Không nên kết luận chỉ dựa trên số lượng `BLOCKED`. Một thread chờ ngắn có thể là bình thường; nhiều snapshot cho thấy cùng một owner và cùng stack trace mới là bằng chứng mạnh hơn về contention kéo dài.

## 8. Nhận diện deadlock

Deadlock xảy ra khi một nhóm thread giữ tài nguyên mà thread khác cần, tạo thành chu trình chờ không thể tự tiến triển.

Ví dụ hai khóa:

~~~java
final Object lockA = new Object();
final Object lockB = new Object();

Thread first = new Thread(() -> {
    synchronized (lockA) {
        synchronized (lockB) {
            System.out.println("first completed");
        }
    }
}, "first");

Thread second = new Thread(() -> {
    synchronized (lockB) {
        synchronized (lockA) {
            System.out.println("second completed");
        }
    }
}, "second");
~~~

Nếu `first` giữ `lockA` và chờ `lockB`, trong khi `second` giữ `lockB` và chờ `lockA`, hai thread tạo chu trình:

~~~text
first  holds lockA  ── waits for lockB
  ^                                  |
  |                                  v
second waits for lockA  ── holds lockB
~~~

Không thread nào có thể vào vùng đồng bộ thứ hai để giải phóng khóa đang giữ. Đây là deadlock.

### 8.1. Dấu hiệu deadlock trong thread dump

HotSpot thường thêm phần thông báo ở cuối dump khi phát hiện Java-level deadlock, ví dụ:

~~~text
Found one Java-level deadlock:
=============================

"first":
  waiting to lock monitor 0x... (object ...)
  which is held by "second"

"second":
  waiting to lock monitor 0x... (object ...)
  which is held by "first"
~~~

Định dạng cụ thể có thể khác. Hãy đọc mối quan hệ:

- Thread nào đang chờ khóa nào?
- Thread nào đang giữ khóa đó?
- Owner có đang chờ khóa khác không?
- Chuỗi owner/waiter có quay lại thread ban đầu không?

Nếu có chu trình, JVM có thể báo deadlock rõ ràng. Dù không có phần báo cáo này, vẫn cần kiểm tra lock graph thủ công khi nghi ngờ deadlock qua synchronizer hoặc tài nguyên ngoài JVM.

### 8.2. Deadlock với ReentrantLock

Deadlock không chỉ xuất hiện với `synchronized`. Hai thread có thể lấy `ReentrantLock` theo thứ tự ngược nhau:

~~~java
ReentrantLock lockA = new ReentrantLock();
ReentrantLock lockB = new ReentrantLock();

// Thread 1: lockA.lock(); rồi lockB.lock()
// Thread 2: lockB.lock(); rồi lockA.lock()
~~~

Trong dump, thread chờ `ReentrantLock` thường xuất hiện ở `WAITING (parking)`. Khi dùng `-l`, phần ownable synchronizers giúp xác định lock nào đang được giữ. `Thread.print -l` vì thế hữu ích hơn dump chỉ có stack trace khi điều tra loại khóa này.

### 8.3. Không phải mọi vòng chờ đều là deadlock Java

Thread dump có thể không phát hiện đầy đủ các tình huống:

- Deadlock giữa nhiều process hoặc service qua database, message broker hoặc network.
- Thread chờ tài nguyên native hoặc callback mà JVM không quản lý như một monitor.
- Chu trình phụ thuộc logic ứng dụng nhưng không tạo một monitor/synchronizer cycle mà JVM nhận diện.
- Starvation hoặc thread pool exhaustion khiến công việc không tiến triển dù không có chu trình khóa.

Vì vậy, kết quả “No deadlocks found” không chứng minh toàn hệ thống không bị deadlock ở tầng database, distributed system hoặc logic ứng dụng.

## 9. Chụp nhiều thread dump để tìm trạng thái bị kẹt

Một dump đơn lẻ chỉ là snapshot. Ví dụ, thấy thread ở `WAITING` có thể hoàn toàn bình thường nếu nó đang đợi queue. Để đánh giá tiến triển, thu thập nhiều snapshot cách nhau một khoảng thời gian phù hợp với workload.

Ví dụ:

~~~shell
jcmd 12345 Thread.print -l > dump-01.txt
~~~

Sau một khoảng ngắn:

~~~shell
jcmd 12345 Thread.print -l > dump-02.txt
~~~

Tiếp tục lấy:

~~~shell
jcmd 12345 Thread.print -l > dump-03.txt
~~~

Với sự cố request treo, có thể bắt đầu bằng ba dump cách nhau khoảng 5–10 giây, sau đó điều chỉnh theo thời gian xử lý bình thường và tải hệ thống. Đây là khoảng quan sát tham khảo, không phải quy tắc cố định.

Khi so sánh:

- Thread có cùng ID và cùng stack trace ở nhiều dump có thể đang chờ lâu hoặc lặp lại cùng code path.
- Thread `RUNNABLE` có cùng stack trace trong nhiều dump, cùng CPU time tăng nhanh, có thể đang chạy vòng lặp hoặc làm việc CPU-bound.
- Nhiều thread liên tục chờ cùng monitor và cùng owner cho thấy contention kéo dài.
- Thread pool worker `WAITING` thay đổi theo task queue thường là trạng thái bình thường.
- Nếu thread biến mất ở dump sau, nó có thể đã hoàn tất hoặc bị kết thúc.

Tên thread có thể được tái sử dụng. Khi đối chiếu, ưu tiên thread ID, native ID và ngữ cảnh ứng dụng, đồng thời lưu ý ID chỉ có ý nghĩa trong vòng đời tiến trình tương ứng.

## 10. Phân biệt các vấn đề thường gặp

| Tình huống | Dấu hiệu thường thấy | Hướng điều tra |
| --- | --- | --- |
| Thread pool đang rảnh | Nhiều worker `WAITING (parking)` trong queue take/poll. | Kiểm tra queue có task không; trạng thái idle có thể bình thường. |
| Lock contention | Nhiều thread chờ cùng monitor/synchronizer; một owner giữ khóa lâu. | Xem stack của owner và thời gian giữ khóa. |
| Deadlock | Chu trình thread chờ khóa do thread khác giữ; có thể có báo cáo deadlock ở cuối dump. | Vẽ lock graph, xác định chu trình và thứ tự lấy khóa. |
| CPU hot loop | Thread `RUNNABLE`, stack trace lặp lại qua nhiều dump, CPU time tăng. | Đối chiếu CPU per-thread và JFR/OS profiler. |
| Thread pool exhaustion | Request thread chờ future/task; worker pool không còn worker rảnh hoặc worker chờ lẫn nhau. | Kiểm tra kích thước pool, queue, nested task submission và dependency. |
| I/O chậm | Thread ở `RUNNABLE` trong native I/O hoặc stack trace ở client/socket/database. | Kiểm tra latency dịch vụ ngoài, socket và JFR/network metrics. |
| Starvation | Một số thread không được chạy dù không có deadlock cycle rõ ràng. | Kiểm tra scheduler, lock fairness, pool sizing và tải. |

### 10.1. Nhiều worker WAITING có thể là bình thường

Ví dụ một thread pool không có công việc:

~~~text
"pool-1-thread-1":
    java.lang.Thread.State: WAITING (parking)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.LinkedBlockingQueue.take(...)
~~~

Worker đang chờ lấy task từ queue. Nếu queue rỗng và ứng dụng không có request, đây là trạng thái idle mong đợi. Chỉ khi có backlog mà worker không xử lý, hoặc task bị kẹt ở một dependency, mới cần điều tra sâu hơn.

### 10.2. Thread pool exhaustion do chờ task con

Một lỗi thiết kế có thể xảy ra khi mọi worker trong pool đều chạy task cha, rồi mỗi task cha submit task con vào cùng pool và chờ kết quả bằng `Future.get()`. Không còn worker rảnh để chạy task con, nên task cha cứ chờ.

Dump có thể cho thấy nhiều worker `WAITING` trong `FutureTask.get` hoặc `CompletableFuture.join`, trong khi queue vẫn có task. Đây không nhất thiết là deadlock monitor; nó là starvation do cấu trúc sử dụng pool.

Hướng xử lý:

- Tránh chờ đồng bộ task con được submit vào cùng pool có giới hạn worker.
- Dùng composition bất đồng bộ thay vì block chờ kết quả nếu phù hợp.
- Tách executor cho loại công việc có vòng đời khác nhau.
- Đánh giá kích thước pool và dependency graph, không chỉ tăng số thread một cách mù quáng.

## 11. Dùng ThreadMXBean để phát hiện deadlock trong code

Ngoài việc đọc dump, Java Management API cung cấp `ThreadMXBean` để truy vấn deadlock.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public class DeadlockDetector {
    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        long[] ids = bean.findDeadlockedThreads();

        if (ids == null || ids.length == 0) {
            System.out.println("No monitor or ownable-synchronizer deadlock found.");
            return;
        }

        ThreadInfo[] infos = bean.getThreadInfo(ids, true, true);
        for (ThreadInfo info : infos) {
            System.out.println(info);
        }
    }
}
~~~

`findDeadlockedThreads()` tìm chu trình deadlock liên quan tới intrinsic monitors và ownable synchronizers nếu JVM hỗ trợ việc kiểm tra đó. Nó bao quát rộng hơn `findMonitorDeadlockedThreads()`, vốn chỉ tìm deadlock liên quan tới monitor.

Các phương thức này chỉ phát hiện deadlock mà JVM có thể nhận diện qua các cơ chế khóa được quản lý. Chúng không phát hiện deadlock phân tán, deadlock ở database hoặc mọi dạng starvation.

### 11.1. Phân biệt hai phương thức

| API | Phạm vi |
| --- | --- |
| `findMonitorDeadlockedThreads()` | Tìm chu trình chờ intrinsic monitor (`synchronized`). |
| `findDeadlockedThreads()` | Tìm chu trình chờ monitor và ownable synchronizers như `ReentrantLock`, nếu được hỗ trợ. |

Nếu ứng dụng dùng `ReentrantLock` hoặc synchronizer khác, `findDeadlockedThreads()` là lựa chọn tổng quát hơn.

## 12. Cách đọc stack trace để tìm nguyên nhân

Đọc thread entry theo thứ tự:

1. **Tên và state:** xác định thread nào có vấn đề và đang ở trạng thái gì.
2. **Frame trên cùng:** xác định lời gọi hiện tại hoặc điểm chờ trực tiếp.
3. **Các frame phía dưới:** lần theo đường đi từ code ứng dụng đến thư viện/JDK.
4. **Lock annotation:** xác định monitor đang chờ hoặc đang giữ.
5. **Lock owner:** tìm thread sở hữu khóa được nhắc đến.
6. **Snapshot khác:** xác định thread có tiến triển hay vẫn mắc ở cùng vị trí.

Ví dụ:

~~~text
"http-worker-7":
    java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.cache.Cache.get(Cache.java:72)
    at com.example.service.ProductService.load(ProductService.java:118)
    at com.example.web.ProductController.show(ProductController.java:44)
    - waiting to lock <0xabc> (a com.example.cache.Cache)
~~~

Đọc từ trên xuống: thread đang chờ monitor trong `Cache.get`; request đi qua `ProductService.load` và `ProductController.show`. Tìm entry có `- locked <0xabc>` để xác định owner, rồi xem owner đang thực hiện công việc gì trong lúc giữ cache monitor.

Không chỉ nhìn frame trên cùng. Một thread có thể đang chờ ở `Unsafe.park` hoặc `Object.wait`, nhưng frame phía dưới mới cho biết nó đang chờ queue, future, condition hay một cơ chế cụ thể.

## 13. Các nguyên nhân deadlock thường gặp và cách phòng tránh

### 13.1. Lấy khóa theo thứ tự khác nhau

Thread A lấy khóa A rồi B; thread B lấy khóa B rồi A. Cả hai có thể giữ một khóa và chờ khóa còn lại.

**Cách phòng tránh:** quy định thứ tự lấy khóa toàn hệ thống, ví dụ luôn lấy khóa theo ID tăng dần. Mọi code path phải tuân thủ cùng quy tắc.

### 13.2. Gọi code bên ngoài khi đang giữ khóa

Một thread giữ monitor rồi gọi network, database, callback hoặc plugin. Code bên ngoài có thể chờ một thread khác đang cần monitor đó.

**Cách phòng tránh:** giảm phạm vi critical section; thu thập dữ liệu cần thiết trong khóa, nhả khóa rồi thực hiện I/O hoặc gọi callback.

### 13.3. Lồng nhiều khóa và khóa theo đối tượng

Nhiều lớp cùng quản lý khóa có thể tạo thứ tự lấy khóa không nhất quán, đặc biệt khi callback gọi ngược vào lớp khác.

**Cách phòng tránh:** xác định ownership của lock, tài liệu hóa thứ tự, giảm lồng khóa và dùng một cơ chế đồng bộ hóa rõ ràng.

### 13.4. Dùng tryLock và timeout có chủ đích

Với `ReentrantLock`, `tryLock(timeout, unit)` có thể giúp tránh chờ vô hạn trong một số thiết kế. Tuy nhiên, timeout chỉ giúp luồng xử lý có cơ hội phục hồi; nó không tự giải quyết tính nhất quán dữ liệu hoặc rollback thao tác đã thực hiện.

Nếu dùng timeout, cần định nghĩa rõ:

- Khi không lấy được khóa thì trả lỗi, thử lại hay bỏ tác vụ?
- Có thể retry an toàn không?
- Có giới hạn số lần retry và backoff không?
- Có giữ một khóa khác trong lúc chờ không?

## 14. Thread dump và JFR bổ trợ cho nhau

Thread dump cho biết snapshot stack và trạng thái khóa. Java Flight Recorder (JFR) ghi lại sự kiện theo thời gian, hữu ích để xem xu hướng và tương quan giữa thread, CPU, monitor contention, I/O và các hoạt động JVM.

| Thread dump | JFR |
| --- | --- |
| Snapshot tại một thời điểm. | Dữ liệu sự kiện theo một khoảng thời gian. |
| Rất hữu ích để xem stack và quan hệ owner/waiter. | Hữu ích để xác định khi nào contention xảy ra và kéo dài bao lâu. |
| Có thể nhìn thấy deadlock cycle JVM phát hiện được. | Có thể cung cấp sự kiện monitor contention và ngữ cảnh thời gian, tùy cấu hình recording. |
| Thường dễ thu thập khi sự cố đang diễn ra. | Phù hợp để theo dõi và phân tích sau khi sự cố xảy ra. |

Nếu dump cho thấy một monitor thường xuyên bị tranh chấp nhưng chưa rõ tần suất, JFR có thể bổ sung bằng chứng về thời gian và stack trace của sự kiện contention. Ngược lại, nếu JFR cho thấy thời gian chờ dài, một thread dump tại thời điểm sự cố giúp tìm owner và trạng thái của các thread liên quan.

## 15. Quy trình thực hành khi ứng dụng bị treo

Một quy trình có thể áp dụng:

### Bước 1: Ghi nhận bối cảnh

Ghi thời điểm sự cố, PID, phiên bản JDK, hostname/container, tải CPU, memory, số request đang chờ và dịch vụ phụ thuộc.

### Bước 2: Thu thập nhiều dump

~~~shell
jcmd <pid> Thread.print -l > dump-01.txt
jcmd <pid> Thread.print -l > dump-02.txt
jcmd <pid> Thread.print -l > dump-03.txt
~~~

Chọn khoảng cách giữa các lần chụp dựa trên thời gian xử lý bình thường và mức độ nghiêm trọng. Không tạo dump liên tục quá dày nếu chưa có lý do.

### Bước 3: Xem phần deadlock report

Tìm các dòng `Found one Java-level deadlock` hoặc phần mô tả thread đang chờ khóa do thread khác giữ. Nếu có chu trình, lập danh sách thread và lock liên quan.

### Bước 4: Nhóm thread theo state và stack

Đếm các thread `BLOCKED`, `WAITING`, `TIMED_WAITING`, `RUNNABLE`. Nhóm theo frame ứng dụng trên cùng, lock ID, queue hoặc synchronizer.

### Bước 5: Tìm owner và code giữ khóa

Với monitor, tìm dòng `- locked <id>`. Với ownable synchronizer, xem phần `Locked ownable synchronizers` và thread đang sở hữu nó. Lần theo stack của owner để tìm công việc kéo dài.

### Bước 6: So sánh snapshot

Kiểm tra thread nào vẫn ở cùng vị trí, owner có thay đổi không, queue có giảm không và CPU time có tăng không. Phân biệt một trạng thái chờ ngắn với một trạng thái không tiến triển.

### Bước 7: Đối chiếu JFR, log và hệ thống ngoài

Nếu stack chờ ở database, socket hoặc future, kiểm tra latency dịch vụ ngoài, pool connection, timeout và log tương ứng. Nếu nghi CPU hot loop, dùng JFR hoặc công cụ profiling để định lượng.

### Bước 8: Sửa nguyên nhân và xác minh

Sửa thứ tự khóa, thu hẹp critical section, thay đổi mô hình pool hoặc xử lý timeout theo đúng nguyên nhân. Sau khi triển khai, kiểm tra lại thread dump và metric dưới tải đại diện để xác nhận contention/deadlock đã giảm.

## 16. Những lỗi thường gặp

| Lỗi | Vì sao dễ kết luận sai | Cách làm phù hợp |
| --- | --- | --- |
| Thấy `WAITING` rồi kết luận thread bị treo | Worker rảnh, queue consumer hoặc thread chờ signal có thể bình thường. | Xem stack trace và tải công việc. |
| Chỉ tìm `BLOCKED` để tìm lock contention | `ReentrantLock` và synchronizer thường park trong `WAITING`. | Thu thập dump với `-l`, xem ownable synchronizers. |
| Thấy `RUNNABLE` rồi kết luận đang dùng CPU cao | JVM state không đồng nghĩa CPU đang chạy liên tục. | Đối chiếu CPU time, OS thread và JFR. |
| Dùng một dump để kết luận deadlock | Một snapshot có thể bắt đúng lúc chờ ngắn. | Lấy nhiều snapshot và tìm chu trình owner/waiter. |
| Không thấy deadlock report nên kết luận không có deadlock | Deadlock có thể ở database, native code hoặc tầng phân tán. | Kiểm tra dependency và lock graph ngoài JVM. |
| Chỉ xem thread đang chờ | Không tìm owner thì chưa biết nguyên nhân giữ khóa. | Tìm monitor/synchronizer đang được giữ và đọc stack owner. |
| Cho rằng mọi `WAITING (parking)` đều là lỗi | Queue, future, condition và lock đều có thể park bình thường. | Xác định đối tượng đang chờ và điều kiện đánh thức. |
| Chụp dump quá dày | Tạo dữ liệu lớn và có thể tăng tác động lên hệ thống. | Chọn khoảng cách đủ để thấy tiến triển. |
| Không lưu timestamp và PID | Khó đối chiếu các dump và log. | Gắn metadata vào từng file. |
| Chia sẻ dump không kiểm soát | Stack có thể chứa thông tin nhạy cảm. | Bảo vệ file và che dữ liệu trước khi chia sẻ. |

## 17. Câu hỏi thường gặp

**Nên dùng `jcmd` hay `jstack` trong Java 17?**  
Cả hai đều có trong JDK 17. `jcmd <pid> Thread.print -l` là cách thuận tiện để lấy dump kèm thông tin khóa; `jstack -l <pid>` là lựa chọn khác.

**`BLOCKED` khác `WAITING` thế nào?**  
`BLOCKED` là chờ lấy intrinsic monitor để vào vùng `synchronized`. `WAITING` là chờ vô thời hạn một sự kiện, ví dụ `Object.wait`, `Thread.join` hoặc `LockSupport.park`.

**Tại sao thread chờ ReentrantLock thường là WAITING chứ không phải BLOCKED?**  
`ReentrantLock` sử dụng synchronizer dựa trên cơ chế park/unpark, không phải intrinsic monitor của `synchronized`. Dùng `Thread.print -l` để xem thêm thông tin ownable synchronizer.

**Nhiều thread WAITING có phải deadlock không?**  
Không. Worker chờ queue, scheduler hoặc condition có thể là trạng thái bình thường. Deadlock cần có chu trình chờ tài nguyên mà các bên đang giữ.

**Một thread dump có phát hiện được deadlock không?**  
HotSpot có thể in báo cáo Java-level deadlock khi phát hiện chu trình monitor hoặc ownable synchronizer. Tuy nhiên, dump không bao quát mọi deadlock ở database, native code hoặc hệ thống phân tán.

**Nên lấy bao nhiêu thread dump?**  
Ba snapshot cách nhau khoảng 5–10 giây là điểm bắt đầu thực tế cho nhiều sự cố, nhưng phải điều chỉnh theo thời gian xử lý bình thường, loại workload và mức độ ảnh hưởng.

**Thread dump có cho biết thread nào đang dùng CPU nhiều nhất không?**  
Một số định dạng có CPU time, nhưng để xác định hot thread cần đối chiếu nhiều snapshot và công cụ như JFR hoặc OS profiler.

**Có thể lấy dump khi JVM không phản hồi không?**  
Thường vẫn có thể thử `jcmd` hoặc tín hiệu hệ điều hành, nhưng thành công phụ thuộc trạng thái JVM, attach mechanism, quyền và môi trường chạy. Nếu JVM bị kẹt sâu hoặc tiến trình không còn đáp ứng, có thể cần phương án chẩn đoán cấp hệ điều hành.

**Thread dump có thay thế JFR không?**  
Không. Dump là snapshot stack/lock; JFR ghi sự kiện theo thời gian. Hai công cụ bổ sung cho nhau.

## 18. Tài liệu tham khảo chính thức

- [Java SE 17 Tool Specifications — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): cú pháp gửi diagnostic command tới JVM đang chạy.
- [Java SE 17 Tool Specifications — jstack](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstack.html): lấy stack trace của các thread Java.
- [Java SE 17 API — Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): định nghĩa các trạng thái thread.
- [Java SE 17 API — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): truy vấn thread và phát hiện deadlock.
- [Java SE 17 API — ThreadInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): thông tin thread, monitor và synchronizer đang giữ.
- [Java SE 17 API — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): khóa loại ownable synchronizer.
- [Java Flight Recorder Runtime Guide](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder-configurations.html): cấu hình và sử dụng JFR để ghi nhận sự kiện runtime.

**Nguyên tắc áp dụng:** Lấy thread dump bằng `jcmd <pid> Thread.print -l`, đọc state và stack trace, xác định monitor/synchronizer mà thread đang chờ, rồi tìm owner của khóa. So sánh nhiều snapshot để phân biệt trạng thái chờ bình thường với contention kéo dài hoặc không tiến triển; dùng JFR, log và metric hệ thống để xác minh nguyên nhân trước khi thay đổi code.
