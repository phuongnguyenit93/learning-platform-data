# jcmd Thread.print, jstack và ThreadMXBean: chẩn đoán luồng trong Java

> Phạm vi: Java SE/JDK 17+, tập trung quan sát concurrency trong JVM bằng thread dump và API `java.lang.management`. Các lệnh và mẫu đầu ra được kiểm chứng với OpenJDK 21. Nội dung chỉ nói về concurrency Java nói chung; không sử dụng Spring.

## 1. Mục tiêu của bài học

Khi ứng dụng Java chậm, treo hoặc sử dụng CPU bất thường, câu hỏi cần trả lời không chỉ là “có bao nhiêu thread?” mà còn là:

- Thread nào đang thực thi mã, chờ lock, chờ tín hiệu, ngủ hoặc đợi I/O?
- Có hai hoặc nhiều thread giữ khóa của nhau dẫn đến **deadlock** không?
- Có **lock contention** khiến throughput suy giảm dù không deadlock?
- Vị trí chờ nào lặp lại nhiều lần trong các bản chụp thời gian khác nhau?
- Làm thế nào thu thập bằng chứng mà không cần sửa mã hoặc khởi động lại ứng dụng?

Ba công cụ giải quyết các nhu cầu khác nhau:

| Công cụ | Cách dùng | Phù hợp nhất |
| --- | --- | --- |
| **`jcmd <pid> Thread.print`** | Công cụ JDK gửi diagnostic command vào JVM đang chạy | Lấy thread dump từ bên ngoài; tùy chọn thông tin lock và mở rộng |
| **`jstack -l <pid>`** | Công cụ JDK lấy stack trace và thông tin khóa | Thu thập dump nhanh hoặc so sánh với `jcmd` |
| **`ThreadMXBean`** | API Java `ManagementFactory.getThreadMXBean()` | Lấy thông tin trong mã, tự động phát hiện deadlock, lấy thread count/CPU/contended time nếu JVM hỗ trợ |

**Thread dump là một ảnh chụp tại thời điểm lấy mẫu**, không phải lịch sử đầy đủ. Không kết luận root cause chỉ từ một thread ở trạng thái `WAITING` hay `BLOCKED`: cần kết hợp stack, chủ sở hữu khóa, tiến triển qua nhiều mẫu, thời gian thực thi, tải hệ thống và log.

## 2. Bắt đầu từ PID và môi trường JDK

Các công cụ này nằm trong bản phân phối **JDK**. Mở terminal có `java`, `jcmd` và `jstack` trên `PATH`, hoặc gọi trực tiếp từ thư mục `bin` của JDK.

```bash
java -version
jcmd -l
```

`jcmd -l` thường in PID và main class/JAR của các JVM có thể phát hiện. Sau khi xác định đúng quy trình:

```bash
jcmd <pid> VM.version
jcmd <pid> help
jcmd <pid> help Thread.print
```

Trong các lệnh mẫu, **thay `<pid>` bằng PID thực**, chẳng hạn `jcmd 12345 Thread.print`. `<pid>` là ký hiệu minh họa, không gõ nguyên các dấu ngoặc nhọn vào shell.

Lưu ý vận hành:

1. Chạy công cụ trên **cùng máy hoặc cùng môi trường PID** với JVM. Với container, PID trong container và PID trên host có thể khác; `jcmd -l` từ host không phải lúc nào liệt kê JVM trong container. Có thể cần vào đúng container hoặc namespace để chẩn đoán.
2. Việc attach chịu ràng buộc quyền truy cập hệ điều hành. `jcmd` thông thường yêu cầu cùng effective user/group với tiến trình Java đích; môi trường bảo mật có thể hạn chế attach.
3. Dùng JDK phù hợp, lý tưởng cùng bản Java hoặc bản tương thích với JVM đang chạy; các diagnostic command và flag có thể khác giữa phiên bản hoặc JVM vendor.
4. `jcmd -l` không tìm thấy ứng dụng **không chứng minh** ứng dụng đã dừng. Xác minh PID qua công cụ quản lý tiến trình của hệ điều hành; kiểm tra container, quyền và cấu hình attach.
5. Thread dump có thể chứa tên thread, class/method và đường đi nghiệp vụ. Lưu log/dump trong vị trí được bảo vệ; cân nhắc giảm thiểu dữ liệu nhạy cảm khi chia sẻ.

## 3. `jcmd Thread.print`: lấy ảnh chụp thread

Cú pháp thực hành với HotSpot/OpenJDK 21:

```bash
jcmd <pid> Thread.print
jcmd <pid> Thread.print -l
jcmd <pid> Thread.print -e
jcmd <pid> Thread.print -l -e
```

Các option của diagnostic command:

- **`-l`**: bổ sung thông tin các khóa thuộc `java.util.concurrent` (ownable synchronizers), hữu ích với `ReentrantLock` và một số cơ chế lock khác.
- **`-e`**: in thông tin mở rộng về thread nếu implementation hỗ trợ.
- **`help Thread.print`**: hỏi JVM mục tiêu xem chính xác những option nào khả dụng.

Ví dụ lưu bản chụp qua redirection:

```bash
jcmd 12345 Thread.print -l -e > thread-dump-1.txt
```

`12345` chỉ là PID minh họa. File tạo ở thư mục làm việc của shell, không phải mặc định trong thư mục JVM. Trên máy cần giữ cả output lỗi, hãy xem thông báo terminal và exit code; nếu thất bại do attach hoặc quyền, file có thể không chứa dump hợp lệ.

`Thread.print` có chi phí chẩn đoán phụ thuộc số lượng thread và lượng metadata thu thập; tài liệu JDK xếp tác động của nó ở mức **Medium**, thay đổi theo số thread. Tránh gọi liên tục với tần suất quá cao trên JVM có số thread rất lớn, đặc biệt khi đang bão hòa tài nguyên.

### 3.1. Một thread dump thể hiện gì?

Một mục thread dump có dạng minh họa đã rút gọn:

```text
"worker-A" #31 ... java.lang.Thread.State: BLOCKED (on object monitor)
    at example.Worker.process(Worker.java:42)
    - waiting to lock <0x00000007ab...> (a java.lang.Object)
    at example.Worker.run(Worker.java:18)

"worker-B" #32 ... java.lang.Thread.State: TIMED_WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.parkNanos(...)
```

Đây là **minh họa định dạng**, không phải stdout từ chương trình ở phần 7; tên, địa chỉ khóa, `nid`, số dòng và cách JVM trình bày có thể khác.

Các thành phần cần đọc:

- **Tên thread**: do JVM/framework hoặc ứng dụng đặt; đặt tên có ý nghĩa giúp chẩn đoán nhanh.
- **Thread state**: trạng thái Java tại thời điểm lấy mẫu, không phải phần trăm CPU hay độ nghiêm trọng.
- **Stack frames**: phương thức hiện tại và chuỗi lời gọi; tìm điểm bắt đầu mã ứng dụng và lời gọi đang chờ.
- **`waiting to lock` / `parking to wait for`**: đối tượng/lock mà thread đang đợi.
- **`locked` / `Locked ownable synchronizers`**: khóa thread đang giữ, nếu dump và JVM cung cấp.
- **Thông tin `nid`**: native thread ID thường hiển thị dưới dạng hex trên HotSpot; hữu ích khi đối chiếu thread CPU ở công cụ hệ điều hành. **Không nhầm** `nid` với Java thread ID hoặc PID của cả tiến trình.

Không khẳng định một thread `RUNNABLE` đang sử dụng CPU mạnh. Tùy API native và implementation, `RUNNABLE` cũng có thể quan sát khi thread đang ở thao tác I/O hoặc lời gọi hệ thống.

### 3.2. Thu thập nhiều snapshot để xem tiến triển

Nếu một request dường như treo, lấy 2–3 dump cách nhau vài giây (khoảng cách tùy tải và thời gian xử lý dự kiến). So sánh **cùng thread hoặc cùng nhóm worker**:

- Stack và chủ sở hữu khóa có giữ nguyên không?
- Thread có luôn chờ cùng một monitor/lock?
- Lượng thread chờ tăng lên trong khi thread phục vụ công việc thực tế ít đi?
- Có deadlock được dump liệt kê hoặc vòng chờ khóa nhìn thấy qua owner IDs?
- Thread có chuyển động qua các frame trong các lần lấy mẫu?

Ba dump giống nhau là dấu hiệu cần điều tra, **chưa tự chứng minh deadlock**: một thread chờ trên queue khi chưa có việc có thể hoàn toàn bình thường.

## 4. `jstack`: công cụ stack dump độc lập

Với JDK 21:

```bash
jstack <pid>
jstack -l <pid>
jstack -l 12345 > jstack-1.txt
```

`-l` bật phần **long listing** để in thêm thông tin lock; hữu ích khi cần liên hệ thread với `java.util.concurrent.locks`. `jstack` thường đưa ra thông tin deadlock nếu phát hiện vòng khóa phù hợp.

Tài liệu JDK 21 đánh dấu lệnh `jstack` là **experimental/unsupported**; trong vận hành nên ưu tiên `jcmd Thread.print` khi có thể vì đó là đường diagnostic command được tài liệu chính thức mô tả và hỗ trợ rộng hơn trên HotSpot. Chỉ dùng option có trong `jstack -help` của phiên bản đã cài: không giả định option cũ như `-F` hoặc `-m` còn khả dụng ở mọi JDK.

### 4.1. So sánh `jcmd` và `jstack`

| Khía cạnh | `jcmd Thread.print` | `jstack` |
| --- | --- | --- |
| Mục tiêu | Diagnostic command vào một JVM đang chạy | Lấy Java stack của tiến trình JVM |
| Cờ lock trên JDK 21 | `-l`; thêm `-e` để có thông tin mở rộng | `-l` |
| Tính mở rộng | `jcmd` có nhiều diagnostic command khác | Tập trung vào thread stack |
| Phiên bản/cú pháp | Kiểm tra `jcmd <pid> help Thread.print` | Kiểm tra `jstack -help` |
| Khi cần script | Có thể redirect output text và parse cẩn thận | Cũng redirect được, nhưng format không phải stable machine API |

Đừng xây parser production dựa vào số cột hoặc regex duy nhất của một dump: format, native ID, header, lock footer và thông tin virtual thread có thể đổi theo phiên bản JDK.

## 5. `ThreadMXBean`: lấy bằng chứng ngay trong chương trình

Java SE cung cấp interface `java.lang.management.ThreadMXBean` trong module **`java.management`**. Truy cập singleton quản lý thread của JVM:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

Đây là đoạn mã đặt **bên trong** class/phương thức Java phù hợp, không phải một chương trình có `main` độc lập. `ThreadMXBean` cho phép lấy thông tin các **platform threads** và các trạng thái quản lý tương ứng.

### 5.1. Các API cần biết

| API | Ý nghĩa | Giới hạn cần nhớ |
| --- | --- | --- |
| `getThreadCount()` | Số platform thread đang sống | Snapshot tức thời; không bao gồm virtual threads trên JDK 21 |
| `getPeakThreadCount()` | Đỉnh số platform threads kể từ khi khởi động/reset | Không phản ánh đỉnh lịch sử trước reset |
| `getTotalStartedThreadCount()` | Tổng platform thread đã được bắt đầu | Giá trị tích lũy, không phải số thread hiện tại |
| `getAllThreadIds()` | Java IDs của các platform thread còn sống | Thread có thể kết thúc trước khi lấy `ThreadInfo` |
| `getThreadInfo(ids, depth)` | Trạng thái, lock owner, stack tối đa `depth` frame | Một phần tử có thể là `null` nếu thread đã hết |
| `dumpAllThreads(monitors, synchronizers)` | Snapshot stack và khóa của platform threads | Kiểm tra hỗ trợ monitor/synchronizer; có chi phí |
| `findMonitorDeadlockedThreads()` | Tìm chu kỳ deadlock do **object monitors** (`synchronized`) | Không phát hiện riêng deadlock của `ReentrantLock` |
| `findDeadlockedThreads()` | Tìm chu kỳ deadlock qua monitors **và ownable synchronizers** | JVM phải hỗ trợ synchronizer monitoring |
| `getThreadCpuTime(id)` | CPU nanoseconds tích lũy cho platform thread | Cần capability bật; có thể trả `-1` |
| `isThreadContentionMonitoringSupported()` | JVM có hỗ trợ đo blocked/waited time? | Hỗ trợ không có nghĩa đã bật |

API `findMonitorDeadlockedThreads()` **chỉ** phát hiện chu kỳ monitor. `findDeadlockedThreads()` có phạm vi rộng hơn, nhưng không phát hiện được mọi dạng ứng dụng “treo”: chờ network, cờ không bao giờ được đặt, chờ future, starvation hoặc phụ thuộc logic không được mô hình bằng ownership của monitor/ownable synchronizer.

### 5.2. Ví dụ lấy snapshot an toàn

Đoạn sau là logic minh họa **bên trong một phương thức Java**:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean synchronizers = bean.isSynchronizerUsageSupported();

ThreadInfo[] threads = bean.dumpAllThreads(monitors, synchronizers);
for (ThreadInfo info : threads) {
    if (info == null) continue;
    System.out.printf("%s [%s] owner=%s%n",
            info.getThreadName(),
            info.getThreadState(),
            info.getLockOwnerName());
}
```

Cần import `java.lang.management.ThreadInfo` và `ThreadMXBean`. Chỉ bật thu thập lock metadata khi JVM thông báo hỗ trợ để tránh `UnsupportedOperationException`. Các giá trị được in phụ thuộc tiến trình thực nên **không có stdout cố định** cho đoạn này.

### 5.3. Lấy CPU time và contention time

```java
if (bean.isThreadCpuTimeSupported() && !bean.isThreadCpuTimeEnabled()) {
    bean.setThreadCpuTimeEnabled(true);
}
long cpuNanos = bean.isThreadCpuTimeSupported()
        ? bean.getThreadCpuTime(threadId) : -1L;
```

Đoạn trên chỉ minh họa trong ngữ cảnh có `bean` và `threadId`, không phải chương trình độc lập. Việc bật CPU time có thể tốn tài nguyên và trong môi trường hạn chế có thể bị từ chối; cần xử lý lỗi/cấu hình cho phù hợp. `-1` có thể nghĩa là đo bị vô hiệu hóa, thread đã kết thúc/không hợp lệ hoặc không được hỗ trợ cho loại thread. CPU time đo *thời gian sử dụng CPU*, không đo thời gian wall-clock. Muốn biết mức tăng CPU, lấy hai mẫu của **cùng thread ID** và so sánh chênh lệch khi cả hai mẫu hợp lệ.

Để phân tích blocked/waited time bằng `ThreadInfo`, kiểm tra `isThreadContentionMonitoringSupported()`, và chỉ khi cần mới bật `setThreadContentionMonitoringEnabled(true)`. Tính năng thường tắt mặc định và có overhead. `getBlockedTime()` / `getWaitedTime()` có thể trả `-1` khi monitoring chưa bật; số lần `getBlockedCount()` và `getWaitedCount()` cần được hiểu đúng theo định nghĩa Java API, không suy ra “tổng thời gian chờ” từ số lần đợi.

## 6. Phân tích thread state, lock owner và tình huống thực tế

### 6.1. Phân biệt trạng thái

| `Thread.State` | Ý nghĩa tại thời điểm lấy mẫu | Diễn giải cần cẩn thận |
| --- | --- | --- |
| `NEW` | Chưa được `start()` | Không nằm trong danh sách **live threads** phổ biến của dump |
| `RUNNABLE` | Có thể đang chạy hoặc sẵn sàng chạy trong JVM | Không khẳng định thread đang tiêu thụ 100% CPU |
| `BLOCKED` | Đang chờ vào **intrinsic monitor** của `synchronized` | Tìm `waiting to lock`, lock owner, stack và thời gian chờ |
| `WAITING` | Đợi không có timeout; ví dụ `Object.wait()`, `Thread.join()`, `LockSupport.park()` | Thread pool nhàn rỗi ở queue có thể chờ rất lâu và vẫn bình thường |
| `TIMED_WAITING` | Đợi có giới hạn thời gian; ví dụ `sleep()`, `wait(timeout)`, timed park | Không tự động là lỗi; có thể là backoff/timer định kỳ |
| `TERMINATED` | Đã hoàn tất | Thường không có trong dump các thread sống |

**`BLOCKED`** ở Java state chỉ liên quan chờ intrinsic monitor; một `ReentrantLock.lock()` có thể hiện trạng thái `WAITING` hoặc `TIMED_WAITING` thông qua `LockSupport.park` khi bị contention. Vì vậy, không tìm mỗi từ “BLOCKED” rồi kết luận không có tranh chấp lock.

### 6.2. Deadlock khác contention và starvation

- **Deadlock:** một chu kỳ chờ khóa, chẳng hạn A giữ khóa 1 chờ khóa 2, B giữ khóa 2 chờ khóa 1. Không luồng nào tiến được nếu không có hành động giải phóng/hủy khác; với `synchronized` trong ví dụ dưới, không có timeout tự động.
- **Contention:** nhiều luồng muốn cùng tài nguyên nhưng owner vẫn làm việc và thỉnh thoảng nhả khóa. Có thể chậm nghiêm trọng song **không phải deadlock**.
- **Starvation:** tác vụ không được lên lịch/cấp tài nguyên đủ, có thể do pool cạn worker, ưu tiên hoặc công việc chiếm mãi tài nguyên. `findDeadlockedThreads()` trả `null` vẫn có thể xảy ra starvation.
- **Blocking I/O:** thread chờ socket/file hoặc downstream. Stack có thể ở API I/O; kiểm tra độ trễ downstream và timeout thay vì mặc định đổ lỗi cho monitor.
- **Livelock:** nhiều thread tiếp tục thay đổi trạng thái và sử dụng CPU nhưng không tiến tới kết quả. Dump tại một thời điểm có thể không chỉ rõ vấn đề; cần nhiều mẫu và chỉ số tiến độ nghiệp vụ.

### 6.3. Cách đọc lock owner

Với `ThreadInfo`:

- `getLockName()` chỉ đối tượng khóa đang chờ, nếu có.
- `getLockOwnerName()` / `getLockOwnerId()` mô tả thread đang giữ khóa, khi thông tin này xác định được.
- `getLockedMonitors()` là tập object monitors thread đang giữ (khi yêu cầu & được JVM hỗ trợ).
- `getLockedSynchronizers()` là tập ownable synchronizers thread đang giữ (khi yêu cầu & được hỗ trợ).

Tìm một **chuỗi sở hữu**: A đợi khóa do B giữ; B lại đợi khóa do C giữ; C đợi khóa do A giữ. Nếu có vòng, kiểm tra bằng `findDeadlockedThreads()` hoặc phần deadlock footer của dump. Tên thread chỉ là nhãn, **Java thread ID** giúp phân biệt các thread trùng tên; native ID và Java ID không có cùng hệ quy chiếu.

## 7. Bài thực hành Java 17+: tự dựng deadlock, kiểm tra bằng cả ba công cụ

Chương trình dưới đây tạo **hai platform daemon threads** cố tình giữ hai monitor theo thứ tự đối nghịch. Hai `CountDownLatch`? Không cần: một latch `BOTH_LOCKED` bảo đảm cả hai thread đã giữ khóa thứ nhất trước khi cố lấy khóa thứ hai. `ThreadMXBean` tìm được chu kỳ deadlock; chương trình tạm dừng ở `System.in.read()` để người học chạy `jcmd` và `jstack` trong terminal khác.

> Deadlock ở đây **cố ý tạo ra trong phòng thí nghiệm**. Không sao chép thứ tự khóa đối nghịch vào mã ứng dụng thật. Thread đặt daemon để JVM có thể thoát khi người học nhấn Enter.

Lưu vào tệp **`ThreadDumpLab.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.Comparator;
import java.util.concurrent.CountDownLatch;

public class ThreadDumpLab {
    private static final Object LEFT = new Object();
    private static final Object RIGHT = new Object();
    private static final CountDownLatch BOTH_LOCKED = new CountDownLatch(2);

    private static void awaitPeer() {
        BOTH_LOCKED.countDown();
        try {
            BOTH_LOCKED.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private static Thread newWorker(String name, Object first, Object second) {
        Thread worker = new Thread(() -> {
            synchronized (first) {
                awaitPeer();
                synchronized (second) {
                    // Không tới được đây khi cả hai giữ khóa ngược chiều.
                }
            }
        }, name);
        worker.setDaemon(true);
        return worker;
    }

    public static void main(String[] args) throws Exception {
        Thread left = newWorker("demo-left-first", LEFT, RIGHT);
        Thread right = newWorker("demo-right-first", RIGHT, LEFT);
        left.start();
        right.start();

        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        long[] ids = null;
        for (int attempt = 0; attempt < 100; attempt++) {
            ids = bean.findMonitorDeadlockedThreads();
            if (ids != null) break;
            Thread.sleep(50);
        }
        if (ids == null) throw new IllegalStateException("No deadlock detected");

        ThreadInfo[] infos = bean.getThreadInfo(ids, 10);
        Arrays.sort(infos, Comparator.comparing(ThreadInfo::getThreadName));
        System.out.println("deadlock found: " + infos.length);
        for (ThreadInfo info : infos) {
            System.out.println(info.getThreadName() + ": "
                    + info.getThreadState() + ", waits for " + info.getLockOwnerName());
        }
        System.out.println("Press Enter to exit...");
        System.in.read();
    }
}
```

Biên dịch và chạy (terminal A):

```bash
javac ThreadDumpLab.java
java ThreadDumpLab
```

Stdout trên OpenJDK 21 (đã biên dịch và chạy):

```text
deadlock found: 2
demo-left-first: BLOCKED, waits for demo-right-first
demo-right-first: BLOCKED, waits for demo-left-first
Press Enter to exit...
```

Chương trình đang **chờ Enter**. Mở terminal B để tìm PID và lấy dump:

```bash
jcmd -l
jcmd <pid> Thread.print -l -e > jcmd-threads.txt
jstack -l <pid> > jstack-threads.txt
```

Thay PID của `ThreadDumpLab` vào `<pid>`. Tìm các chuỗi `demo-left-first`, `demo-right-first`, `BLOCKED` và phần báo **Java-level deadlock** ở cuối dump. Trên OpenJDK 21, tôi đã xác minh cả hai lệnh trả exit code 0 và tìm thấy tên của cả hai thread cùng báo cáo `Found one Java-level deadlock`. Địa chỉ khóa/ID/stack line thay đổi theo mỗi lần chạy nên không trình bày chúng như stdout bất biến.

**Diễn giải từng bước:**

1. `left` vào `synchronized(LEFT)`, `right` vào `synchronized(RIGHT)`.
2. Mỗi thread giảm `BOTH_LOCKED` và đợi đến khi **cả hai** đã có khóa đầu tiên; đây là lý do ví dụ không dựa vào `Thread.sleep()` để “hy vọng xảy ra deadlock”.
3. Sau khi latch về 0, `left` cố lấy `RIGHT` mà `right` đang giữ; `right` cố lấy `LEFT` mà `left` đang giữ.
4. Hai thread đều `BLOCKED`. `findMonitorDeadlockedThreads()` trả về Java IDs của chu kỳ monitor; `getThreadInfo(ids, 10)` đưa trạng thái và lock owner của các thread đó.
5. Mảng `ThreadInfo` được sắp xếp theo tên trước khi in để stdout ổn định; PID/native IDs vẫn thay đổi.
6. Hai thread là daemon nên việc nhấn Enter khiến `main` thoát và JVM có thể kết thúc dù chúng vẫn deadlock. Điều này **không phải sửa deadlock**: chỉ là kết thúc quy trình thí nghiệm.

Mặc dù `findMonitorDeadlockedThreads` lặp tối đa khoảng 5 giây, thời gian vòng lặp không phải hạn mức chờ thực thi tất cả trường hợp. Trong máy rất tải hoặc JVM không hỗ trợ attach/monitoring theo kỳ vọng, cần kiểm tra lỗi thay vì giả định kết quả giống ví dụ.

### 7.1. Phân tích khác biệt giữa API và dump

- **`ThreadMXBean`** cho phép chương trình đọc Java thread IDs và trả lời câu hỏi deadlock một cách máy đọc được.
- **`jcmd`** cho phép người vận hành quan sát khi ứng dụng không có sẵn code thu thập. Nó in stack của các thread JVM quan sát được; đừng nhầm ID native với `ThreadInfo.getThreadId()`.
- **`jstack`** là lựa chọn bổ sung để kiểm tra chéo; ở JDK 21 nó cũng báo deadlock của ví dụ.
- Cả ba cùng phản ánh **JVM hiện tại**, không mô tả thread đã chết hay toàn bộ lịch sử. Với outage chỉ xảy ra thoáng qua, cần nhiều mẫu hoặc một cơ chế ghi dữ liệu theo thời gian.

## 8. Quy trình xử lý sự cố thường gặp

### 8.1. Ứng dụng treo, không trả kết quả

1. Xác minh **đúng JVM** (PID, main class, uptime, phiên bản và container).
2. Lấy `jcmd <pid> Thread.print -l -e` và lưu kèm timestamp; nếu cần lặp lại thành vài snapshot cách nhau khoảng thời gian phù hợp.
3. Tìm deadlock footer, các thread `BLOCKED` và owner chain. Nếu không có deadlock, kiểm tra `WAITING`, `TIMED_WAITING`, pool queue và các điểm chờ `Future.get`, `CountDownLatch.await`, `Object.wait`, `LockSupport.park`.
4. Đối chiếu với log, deadline, counters hoặc request IDs của ứng dụng. Việc nhiều thread đều đợi trên một queue trống thường bình thường; việc executor có toàn bộ worker đợi `Future.get()` từ công việc khác gửi **vào chính pool đó** có thể là starvation.
5. Điều chỉnh nguyên nhân: thứ tự chiếm lock, giảm thời gian giữ khóa, tách pool tác vụ phụ thuộc, thêm timeout/hủy hợp lệ hoặc giảm số worker cạnh tranh tài nguyên.

### 8.2. CPU cao

Một thread dump riêng lẻ không xếp hạng lượng CPU. Dùng công cụ hệ điều hành xác định native thread tiêu thụ CPU, đổi TID sang định dạng phù hợp với `nid` của HotSpot khi cần đối chiếu; hoặc bật/đọc `ThreadMXBean.getThreadCpuTime(id)` khi JVM hỗ trợ và theo dõi **delta** qua nhiều mẫu. Tìm vòng lặp/busy spin trong stack và đo thêm CPU profiler/JFR khi phù hợp.

Không nhầm một thread `RUNNABLE` với một CPU core đang sử dụng 100%, cũng không coi `Thread.State.BLOCKED` là “CPU cao”. Đây là thông tin về trạng thái synchronization ở một thời điểm.

### 8.3. Throughput giảm hoặc thread pool cạn kiệt

Nếu nhiều thread giữ nguyên stack tại các đoạn chờ queue/future/lock, xem:

- Có một tài nguyên bị tranh chấp khiến hàng loạt worker chờ?
- Có một pool vừa gửi việc vào **chính nó** vừa đợi kết quả từ task chưa được chạy?
- Có I/O chậm hoặc giới hạn downstream làm worker bận chờ?
- Có quá nhiều thread và context switching, hay số worker quá ít so với đặc tính công việc?

Kết hợp dump với **active worker**, queue length, rejection count, task completion rate và queue wait. Thread dump giúp nhìn *đang chờ ở đâu*; metrics giúp biết *mức độ ảnh hưởng và diễn biến theo thời gian*.

## 9. Giới hạn và lưu ý khi chạy trên Java hiện đại

### 9.1. Virtual threads trên Java 21

`ThreadMXBean` chuẩn của Java SE 21 giám sát **platform threads**, **không** cung cấp danh sách/trạng thái đầy đủ của virtual threads. Vì thế:

- `getThreadCount()` không đếm tổng virtual threads.
- `getAllThreadIds()`, `getThreadInfo(...)`, `dumpAllThreads(...)` không cung cấp điều tra toàn bộ virtual threads.
- Hai phương thức `find...DeadlockedThreads()` không tìm chu kỳ chứa virtual threads trong Java 21.

Tương tự, **không giả định** bản `jcmd Thread.print`/`jstack` của mọi JDK sẽ hiển thị mọi virtual thread đang tồn tại. Kiểm tra phiên bản JDK và khả năng hỗ trợ virtual-thread diagnostics; khi sự cố liên quan virtual threads, có thể cần JFR, thread dump format/công cụ chuyên dụng được JVM đang sử dụng hỗ trợ. Đừng kết luận “không có virtual thread nào chờ” chỉ vì chúng không xuất hiện trong một kiểu dump.

### 9.2. Overhead, snapshot và dữ liệu nhạy cảm

- Lấy toàn bộ stack và lock metadata có chi phí, tăng theo số thread; thu thập có điều độ.
- Kết quả thread IDs và stack là **snapshot**: thread có thể kết thúc giữa lúc lấy ID và lúc hỏi thông tin, khiến phần tử `ThreadInfo` thành `null`.
- Bật contention monitoring hoặc CPU time monitoring khi cần thiết, đánh giá chi phí trong môi trường chạy thực.
- Dump có thể phơi bày tên worker, package và cấu trúc luồng nghiệp vụ. Áp dụng kiểm soát truy cập, retention và xử lý dữ liệu phù hợp.
- Công cụ attach có thể không dùng được vì container, quyền hoặc JVM flag; lỗi attach không chứng minh có deadlock hay không deadlock.

### 9.3. Không biến API chẩn đoán thành cơ chế đồng bộ

Không dùng `getThreadState()`, `getThreadCount()`, `getThreadInfo()` hay thống kê `blockedTime` để quyết định phân quyền lock, tiến trình nghiệp vụ hoặc xem task “đã hoàn thành” hay chưa. Đây là dữ liệu monitoring, có race và overhead. Logic đồng bộ phải dựa trên cơ chế thích hợp như `synchronized`, `Lock`, `CountDownLatch`, `CompletableFuture`, `volatile` hoặc primitive đồng bộ khác.

## 10. Sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Coi mọi `WAITING` là treo | Idle worker thường đợi queue/condition | Đọc frame, owner và tiến trình nghiệp vụ |
| Chỉ tìm `BLOCKED` để phát hiện mọi lock contention | `ReentrantLock` có thể chờ qua `park` | Kết hợp lock metadata, `-l` và stack |
| Coi `findDeadlockedThreads() == null` nghĩa là không có sự cố | Nó chỉ tìm một số chu kỳ khóa | Kiểm tra starvation, livelock, I/O và virtual threads |
| Dùng một dump để kết luận CPU hotspot | Dump không đo CPU tích lũy | So sánh CPU delta, dùng profiler/JFR |
| So sánh Java thread ID trực tiếp với `nid` | Đây là hai ID khác hệ quy chiếu | Đổi đúng native TID; xác minh bản JVM |
| Cho rằng `getThreadInfo` luôn non-null | Thread có thể chết giữa hai lần đọc | Kiểm tra `null` |
| Bật contention metrics lâu dài mà không đo overhead | Tracking có chi phí | Chỉ bật theo mục tiêu quan sát cụ thể |
| Ghi đè file dump khi lấy nhiều mẫu | Mất bằng chứng theo thời gian | Ghi tách file có timestamp và bối cảnh |
| Giả định `jcmd -l` thấy JVM trong container khác | PID namespace có thể khác | Xác minh PID trong đúng namespace |
| Giả định toàn bộ virtual threads xuất hiện trong ThreadMXBean trên JDK 21 | API chuẩn chỉ hỗ trợ platform threads | Dùng công cụ hỗ trợ virtual thread diagnostics cho phiên bản JVM |

## 11. Kiểm tra việc học

Thực hành lần lượt:

1. Tạo và chạy `ThreadDumpLab.java`. Giải thích vì sao chỉ có một `CountDownLatch` đã đủ làm deadlock xảy ra nhất quán.
2. Dùng `jcmd -l` xác định đúng PID, lưu một dump với `Thread.print -l -e` và một dump `jstack -l`. Tìm tên hai thread và phần deadlock footer.
3. Thay tên hai thread trong mã rồi chạy lại. Kết quả tên thread thay đổi; giải thích vì sao Java IDs, native IDs và lock addresses vẫn không nên được coi là dữ liệu cố định.
4. Sửa cả hai worker để lấy monitor theo **cùng một thứ tự**, sau đó bỏ đoạn giữ chương trình để chẩn đoán. Xác nhận không còn chu kỳ deadlock và giải thích tại sao việc áp dụng thứ tự khóa thống nhất ngăn vòng chờ.
5. Tự viết một hàm dùng `ThreadMXBean` kiểm tra khả năng hỗ trợ synchronizer usage và in thông tin owner của thread được chọn. Xử lý trường hợp thread đã kết thúc giữa hai lần lấy mẫu.
6. Giải thích vì sao `getThreadCount()` trên JDK 21 không thể dùng để đếm virtual threads, và vì sao một dump không đủ chứng minh không xảy ra starvation.

## 12. Ghi nhớ

- **`jcmd Thread.print`** là đường lấy thread dump từ ngoài JVM và có các flag `-l`, `-e` trên JDK 21.
- **`jstack -l`** cung cấp stack và thông tin khóa; kiểm tra hỗ trợ theo phiên bản JDK.
- **`ThreadMXBean`** cung cấp API trong chương trình để truy vấn platform threads, CPU/contended time theo capability và hai dạng kiểm tra deadlock.
- **Deadlock** là chu kỳ chờ, **contention** là tranh chấp có thể còn tiến triển, **starvation** là không được cấp tài nguyên đủ; không thể đánh đồng bằng tên một trạng thái thread.
- Kết luận dựa trên **nhiều snapshot + lock ownership + metrics + tiến độ nghiệp vụ**; không phụ thuộc duy nhất vào một stack frame.

Tài liệu tham khảo chính thức:

- [The jcmd Command — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [The jstack Command — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstack.html)
- [ThreadMXBean — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [ThreadInfo — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [Diagnostic Tools — Java SE 21 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
