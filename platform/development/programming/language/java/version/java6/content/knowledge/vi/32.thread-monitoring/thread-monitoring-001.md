# ThreadMXBean và theo dõi platform thread trong Java

## 1. Mục tiêu và phạm vi

Trong ứng dụng Java chạy lâu, các tình trạng CPU tăng, request bị treo, số lượng luồng tăng đột ngột hoặc deadlock thường cần được điều tra bằng **quan sát luồng**. Java có MXBean chuẩn `java.lang.management.ThreadMXBean` thuộc module `java.management` để đọc **thông tin về các platform threads** mà JVM đang quản lý.

**Điểm quan trọng nhất của bài:** kể từ khi virtual threads trở thành tính năng ổn định ở Java 21, thuật ngữ “luồng Java” **không còn đồng nghĩa với “luồng được ThreadMXBean nhìn thấy”**. Theo Java SE 26, `ThreadMXBean` hỗ trợ **platform threads**, không hỗ trợ giám sát hoặc quản lý **virtual threads**. Nếu không phân biệt hai loại, bạn sẽ diễn giải sai số lượng luồng, thread dump, CPU time và deadlock detection.

Bài **“ThreadMXBean và theo dõi platform thread”** thuộc nhóm **Theo dõi luồng**. Các kỹ năng đạt được:

1. Lấy MXBean bằng `ManagementFactory.getThreadMXBean()` và hiểu `ObjectName` của nó trong JMX.
2. Đọc đúng `getThreadCount`, `getPeakThreadCount`, `getTotalStartedThreadCount`, `getDaemonThreadCount` và `getAllThreadIds`.
3. Dùng `ThreadInfo` để quan sát trạng thái, stack traces, `lockOwnerId` và locks mà một platform thread đang giữ.
4. Giới hạn stack depth khi gọi `getThreadInfo`/`dumpAllThreads` để tránh thu thập quá mức.
5. Phân biệt **CPU time (nanoseconds)** với **contention/waited time (milliseconds)** và wall-clock latency.
6. Kiểm tra `isThreadCpuTimeSupported`, `isCurrentThreadCpuTimeSupported`, `isThreadContentionMonitoringSupported`, `isObjectMonitorUsageSupported` và `isSynchronizerUsageSupported` trước khi dùng tính năng tùy chọn.
7. Phân biệt `findMonitorDeadlockedThreads` với `findDeadlockedThreads` cho `synchronized` và `ReentrantLock`.
8. Hiểu lý do `getThreadInfo(virtualThreadId)` trả `null`, CPU time cho virtual thread có thể trả `-1` và thread count không chứa virtual threads.
9. Dùng các công cụ hiện hành để quan sát virtual threads: `jcmd Thread.dump_to_file`, JDK Flight Recorder (JFR) và `jdk.management.VirtualThreadSchedulerMXBean` (JDK 24+).
10. Viết một chương trình Java 17 cơ bản, một fixture Java 21 kiểm thử 79 trường hợp và một probe JDK 24 đọc scheduler MXBean.
11. Thiết kế monitoring không có các tác dụng phụ nguy hiểm lên JVM production, thread pools và dữ liệu riêng tư.

**Tài liệu chuẩn:** Java SE 26 `ThreadMXBean`/`ThreadInfo`, JDK 26 `jcmd` và `VirtualThreadSchedulerMXBean`. Các chương trình được kiểm thử thực tế trên **OpenJDK 24**: Java 17 **6/6**, Java 21 **79/79**, Java 24 scheduler probe **4/4**. Không dùng công cụ hay cách thao tác luồng đã bị deprecated như `Thread.stop`/`Thread.suspend`.

## 2. Platform thread và virtual thread

### 2.1. Platform thread

**Platform thread** là đối tượng `Thread` thường được ánh xạ tới một kernel thread do hệ điều hành lập lịch. Các platform threads bao gồm nhiều worker trong thread pools truyền thống và chính thread chạy `main`.

Ở Java 21+:

```java
Thread worker = Thread.ofPlatform()
        .name("worker-platform")
        .start(() -> {
            // Handle a bounded task.
        });
worker.join();
```

Đây là **snippet**, không phải chương trình độc lập; ví dụ được phép dùng vì `Thread.ofPlatform` là API hiện hành. Dùng `Thread.currentThread().isVirtual()` để phân biệt trong JVM.

### 2.2. Virtual thread

**Virtual thread** là lightweight Java thread do JVM lập lịch lên các carrier platform threads. Trong Java 21+:

```java
Thread task = Thread.ofVirtual()
        .name("task-virtual")
        .start(() -> {
            // Blocking-style Java task.
        });
task.join();
```

Virtual thread không phải một kernel thread riêng theo quan hệ 1:1. **Carrier platform threads** vẫn tồn tại và có thể được ThreadMXBean tính đến, nhưng **virtual threads được chở trên carrier không xuất hiện thành các entry riêng** trong API ThreadMXBean.

### 2.3. Phạm vi giám sát chính xác

| API của `java.lang.management.ThreadMXBean` | Platform thread | Virtual thread |
| --- | --- | --- |
| `getThreadCount()` | Được tính | Không được tính |
| `getDaemonThreadCount()` | Đếm daemon platform threads | Không được tính |
| `getPeakThreadCount()` | Được tính | Không được tính |
| `getTotalStartedThreadCount()` | Đếm platform threads đã start | Không được tính |
| `getAllThreadIds()` | Trả IDs của platform threads còn sống | Không trả IDs |
| `getThreadInfo(id)` | Có thể trả `ThreadInfo` nếu còn sống | Trả `null` |
| `getThreadCpuTime(id)` | Có thể trả ns, cần feature/enabled | Trả `-1` khi tính năng được hỗ trợ |
| `dumpAllThreads(...)` | Bao gồm platform threads | Không bao gồm |
| `findMonitorDeadlockedThreads()` | Tìm vòng deadlock giữa platform threads bằng monitors | Không phát hiện vòng có virtual thread |
| `findDeadlockedThreads()` | Tìm monitor/ownable synchronizer deadlocks của platform threads | Không phát hiện vòng có virtual thread |

**Không suy rằng ứng dụng dùng 50.000 virtual threads thì `getThreadCount()` phải khoảng 50.000.** Chỉ số này đo platform threads. Với virtual-thread-heavy application, nó không phản ánh concurrency cuối cùng của mọi user tasks.

### 2.4. JDK version và module

- `ThreadMXBean` thuộc module **`java.management`**, tồn tại từ trước Java 17 và vẫn hiện hành trong Java SE 26.
- `Thread.ofVirtual()` và virtual threads ổn định từ **Java 21**. Code dùng trực tiếp API này **không biên dịch với `--release 17`**.
- `Thread.threadId()` là lựa chọn API hiện hành trong Java 21+ để lấy ID, thay vì phụ thuộc `Thread.getId()` đã được đánh dấu deprecated trong các JDK mới. Trong source Java 17 cơ bản của bài, ta **không cần** gọi `getId()`.
- `jdk.management.VirtualThreadSchedulerMXBean` có từ **JDK 24**, thuộc module `jdk.management`, là **API riêng để quan sát scheduler**, không thay thế ThreadInfo của từng virtual thread.

## 3. Lấy ThreadMXBean và nhận diện JMX MBean

Cách trực tiếp:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

Đây là snippet phải đặt trong class/method. `ManagementFactory.getThreadMXBean()` lấy instance quản trị hệ thống luồng của JVM; JVM có **một** ThreadMXBean cho mô hình chuẩn này.

Trong platform `MBeanServer`, tên cố định là:

```text
java.lang:type=Threading
```

Đọc qua JMX:

```java
MBeanServer mbs = ManagementFactory.getPlatformMBeanServer();
ObjectName threading = new ObjectName("java.lang:type=Threading");
int count = (Integer) mbs.getAttribute(threading, "ThreadCount");
```

Đây là snippet, cần `MBeanServer` và `ObjectName` imports và xử lý checked JMX exceptions.

**Không bắt buộc mở JMX remote** để dùng các method này. Khi sử dụng `ManagementFactory.getThreadMXBean()` hoặc platform server trong cùng JVM, việc lấy dữ liệu nằm ở local management interface.

### 3.1. Ý nghĩa “MXBean”

`ThreadMXBean` là một platform MXBean. Khi một client đọc thông qua JMX raw interface, `ThreadInfo` được ánh xạ sang một **`CompositeData`** theo Open Types. Có thể dựng lại:

```java
ThreadInfo info = ThreadInfo.from((CompositeData) raw);
```

Ở đây `raw` là kết quả Open Data từ một JMX operation; cast chỉ đúng nếu method trả dữ liệu khác null và là CompositeData. Khi gọi typed `ThreadMXBean.getThreadInfo(...)` trực tiếp, bạn **đã có `ThreadInfo`**, không cần `from`.

## 4. Nhóm chỉ số số lượng platform threads

| Method | Trả về | Cách hiểu đúng |
| --- | --- | --- |
| `getThreadCount()` | `int` | Số **platform threads còn sống** tại thời điểm đo |
| `getDaemonThreadCount()` | `int` | Số daemon platform threads còn sống |
| `getPeakThreadCount()` | `int` | Đỉnh platform threads kể từ JVM start hoặc lần reset peak gần nhất |
| `getTotalStartedThreadCount()` | `long` | Tổng platform threads đã được tạo và start kể từ khi JVM start |
| `getAllThreadIds()` | `long[]` | IDs của các platform threads còn sống tại snapshot; không có virtual IDs |
| `resetPeakThreadCount()` | `void` | **Thay đổi trạng thái metrics dùng chung**: reset peak về số đang sống |

### 4.1. Những chỉ số không tương đương

`getTotalStartedThreadCount()` tích lũy và không phải “số worker hiện tại”; nó có thể lớn hơn nhiều `getThreadCount()` trong JVM có thread churn. `getPeakThreadCount()` phản ánh đỉnh, không phải trung bình. `getDaemonThreadCount()` chỉ là một tập con của platform threads còn sống, không có virtual threads.

`getAllThreadIds().length` và `getThreadCount()` không nhất thiết bằng nhau khi đọc liên tiếp, vì threads được start/terminate giữa hai lời gọi. Không tạo alert nghiêm trọng chỉ vì một snapshot lệch vài IDs.

### 4.2. Thread IDs không phải định danh vĩnh viễn

`Thread.threadId()` (Java 19+) trả một số `long` dương, unique **trong vòng đời của thread**. Sau khi thread kết thúc, ID **có thể được tái sử dụng**. Vì vậy:
- Không dùng thread ID làm business ID lâu dài.
- Không lưu thread IDs trong database như identity độc nhất qua nhiều lần restart.
- Không điều khiển synchronization chỉ dựa vào ThreadInfo snapshot và ID.
- Nếu một ID không tồn tại lúc truy vấn, `getThreadInfo(id)` trả `null`.

JDK26 tài liệu rõ `getThreadInfo(id <= 0)` ném `IllegalArgumentException`. Một ID `Long.MAX_VALUE` hợp lệ về mặt dương nhưng gần như chắc chắn không thuộc luồng sống trong fixture; `getThreadInfo` trả null.

### 4.3. Không reset peak trong monitoring chung

`resetPeakThreadCount()` **không phải phép đọc**. Nó thay global peak statistic cho JVM và có thể ảnh hưởng dashboards/alerting khác. Nếu muốn biết đỉnh kể từ thời điểm đo của *riêng* ứng dụng monitoring, hãy tính rolling maximum trong hệ thống metrics ngoài JVM thay vì reset số liệu hệ thống một cách không phối hợp.

## 5. ThreadInfo là snapshot, không phải đối tượng Thread

`java.lang.management.ThreadInfo` là đối tượng **thông tin chụp tại một thời điểm** về platform thread. Nó không phải một handle cho phép dừng, ưu tiên hay sửa chạy của thread. Những trường hữu ích:

| Field/method | Ý nghĩa |
| --- | --- |
| `getThreadId()` | ID của platform thread |
| `getThreadName()` | Tên thread tại snapshot |
| `getThreadState()` | `Thread.State` tại snapshot |
| `isDaemon()` | Thread daemon hay không |
| `getPriority()` | Thread priority |
| `getStackTrace()` | Stack trace được yêu cầu, có giới hạn depth |
| `getLockName()` / `getLockInfo()` | Lock mà thread đang chờ |
| `getLockOwnerId()` / `getLockOwnerName()` | Owner của lock nếu biết |
| `getLockedMonitors()` | Monitors thread đang giữ, nếu request/support |
| `getLockedSynchronizers()` | Ownable synchronizers thread đang giữ, nếu request/support |
| `getBlockedCount()` / `getWaitedCount()` | Số lần block/wait được quan sát |
| `getBlockedTime()` / `getWaitedTime()` | Thời gian tích lũy tương ứng, **milliseconds** và cần contention monitoring |
| `isInNative()` | Thread đang thực thi native code theo định nghĩa JDK |

Snapshot không atomic trên toàn JVM: giữa lúc lấy IDs và hỏi ThreadInfo, threads có thể kết thúc. Những trạng thái thay đổi nhanh không phải lúc nào cũng tái hiện được.

### 5.1. Thread.State và ý nghĩa chẩn đoán

| State | Gợi ý nguyên nhân | Không được suy diễn |
| --- | --- | --- |
| `NEW` | Thread chưa start | Thường không xuất hiện trong live ThreadMXBean |
| `RUNNABLE` | Đang chạy hoặc sẵn sàng chạy trong JVM | Không chắc CPU thực sự đang dùng 100%; có thể chờ I/O native |
| `BLOCKED` | Chờ vào `synchronized` monitor | Không đồng nghĩa deadlock |
| `WAITING` | Chờ vô thời hạn vì `Object.wait`, `join`, parking hoặc cơ chế tương tự | Không chắc lỗi |
| `TIMED_WAITING` | Chờ có timeout như `sleep`/timed wait/park | Không chắc hiệu năng kém |
| `TERMINATED` | Thread đã kết thúc | ThreadMXBean getThreadInfo của ID đã chết trả null |

Một platform thread ở `BLOCKED` có thể bình thường nếu một critical section ngắn đang được giữ bởi thread khác. Deadlock chỉ hình thành khi có **chu trình chờ locks**, không phải chỉ một thread đợi lock.

### 5.2. Lấy ThreadInfo theo ID và độ sâu

```java
ThreadInfo noStack = bean.getThreadInfo(id);     // depth = 0
ThreadInfo fiveFrames = bean.getThreadInfo(id, 5);
ThreadInfo[] many = bean.getThreadInfo(new long[]{id1, id2}, 8);
```

Đây là snippet, cần `bean` và các thread IDs đã được tạo. `getThreadInfo(id)` tương đương `getThreadInfo(id,0)`; **không trả stack**. `maxDepth == 0` có nghĩa không trả stack, còn số âm ném `IllegalArgumentException`. `Integer.MAX_VALUE` có thể yêu cầu toàn bộ stack nhưng tốn chi phí và dễ lộ thông tin.

Với array IDs:
- `result.length == ids.length`.
- `result[i]` tương ứng `ids[i]`.
- Nếu thread đó virtual, đã kết thúc hoặc không tồn tại, phần tử tương ứng **`null`**.
- Không xóa các null rồi đánh mất alignment, đặc biệt khi cùng một mảng IDs phục vụ dashboard.

### 5.3. Lấy monitors và synchronizers có guard

```java
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean syncs = bean.isSynchronizerUsageSupported();

ThreadInfo[] details = bean.getThreadInfo(
        selectedIds, monitors, syncs, 8);
```

Đây là snippet (tên `selectedIds` do ứng dụng chọn). Khi `lockedMonitors` hoặc `lockedSynchronizers` được yêu cầu nhưng VM không hỗ trợ, method có thể ném `UnsupportedOperationException`. Một số overload/default implementation cũng có thể không được mọi provider hỗ trợ; cần xử lý.

- `getLockedMonitors()` rỗng nếu không request hoặc thread không giữ monitor.
- `getLockedSynchronizers()` rỗng nếu không request hoặc không giữ synchronizer.
- Không coi “mảng rỗng” là bằng chứng thread không dùng bất kỳ lock nào nếu trước đó bạn **không bật** cờ thu thập tương ứng.

### 5.4. Không dùng snapshot để điều khiển synchronization

Không viết “nếu ThreadInfo báo RUNNABLE thì gửi interrupt” hoặc “nếu lockOwnerId cố định thì kill thread”. Snapshot là để **quan sát/troubleshoot**; quyền sở hữu lock và trạng thái có thể thay đổi ngay sau phép đo. Quản lý vòng đời threads phải dựa trên structured concurrency, cancellation, futures, executor shutdown và synchronization contracts, không dựa trên dữ liệu giám sát đọc muộn.

## 6. Thread dumps và giới hạn chi phí

```java
ThreadInfo[] dump =
        bean.dumpAllThreads(false, false, 8);
```

Trong JDK 10+ overload ba tham số có `maxDepth`, thích hợp để bounded diagnostics. Các flag false yêu cầu không lấy owned locks; nếu cần lock details, kiểm tra capabilities và chỉ bật khi chẩn đoán.

`dumpAllThreads` trả **platform threads**, không bao gồm virtual threads, ngay cả khi JVM có rất nhiều virtual tasks. `dumpAllThreads(true,true)` có thể tốn chi phí hơn; không đưa vào HTTP health handler chạy mỗi giây hoặc cho user bất kỳ gọi.

Hướng dẫn production:
1. Lấy những số đếm lightweight thường xuyên hơn.
2. Chỉ lấy ThreadInfo cho một số IDs đã chọn (high CPU, nghi blocked).
3. Giới hạn `maxDepth`, số lượng threads và tần suất snapshot.
4. Dùng thread dump sâu khi on-call điều tra sự cố thực.
5. Quản lý quyền đọc, retention và redaction cho stack traces, lock names, paths.
6. Có sampling/backoff và tránh ghi quá nhiều dữ liệu trong error logs.

## 7. Thread CPU time — nanoseconds, không phải wall time

### 7.1. Các capability flags

`ThreadMXBean` có:
- `isThreadCpuTimeSupported()`: JVM hỗ trợ CPU time **cho platform threads bất kỳ**?
- `isCurrentThreadCpuTimeSupported()`: JVM hỗ trợ current platform thread CPU/user time?
- `isThreadCpuTimeEnabled()`: CPU-time measurement đang enabled hay không?
- `setThreadCpuTimeEnabled(boolean)`: bật/tắt một khả năng tùy chọn, có thể **tốn chi phí**.

Không được mặc định mọi JVM đều bật CPU measurement. Trước khi gọi method có thể ném `UnsupportedOperationException`, kiểm tra support flag phù hợp.

### 7.2. Các phép đo

```java
long cpuNanos = bean.getThreadCpuTime(platformThreadId);
long userNanos = bean.getThreadUserTime(platformThreadId);
```

Là **nanoseconds** CPU đã tiêu thụ; giá trị có precision nanoseconds nhưng **không được hứa accuracy nanoseconds**. User time là phần CPU trong user mode nếu provider phân biệt user/system; total CPU gồm user+system.

**Không nhầm**:
- CPU time 10 ms với request latency 10 ms.
- `ThreadInfo.getBlockedTime` 10 **milliseconds** với `getThreadCpuTime` 10 **nanoseconds**.
- CPU time của platform carrier với CPU time được phân bổ chính xác cho từng virtual task.

CPU time là tích lũy theo thread; để ước lượng tỷ lệ sử dụng CPU trên một interval:
```text
cpuDeltaNanos = cpuNanos(t2) - cpuNanos(t1)
wallDeltaNanos = t2 - t1
cpuRatio = cpuDeltaNanos / wallDeltaNanos
```

Đây là **công thức ước lượng**, không đảm bảo một con số “% hệ thống” trực tiếp. Nếu thread terminate, ID bị reuse hoặc CPU measurement bị reset/bật giữa hai lần đo, delta có thể không dùng được. Nhiều CPU cores, scheduling, sample interval và permission/capability ảnh hưởng diễn giải. Nếu muốn percent process-level, dùng các metrics phù hợp với CPU/process khác.

### 7.3. Giá trị `-1` và lỗi

`getThreadCpuTime(id)`/`getThreadUserTime(id)` trả `-1` khi:
- ID là virtual thread.
- Thread đó không tồn tại hoặc đã chết.
- CPU measurement bị disable.
- Một số khả năng không có hoặc bị hạn chế theo contract.

Nếu JVM **không hỗ trợ** tính năng cho thread được yêu cầu, method có thể ném `UnsupportedOperationException` thay vì trả `-1`. **Đừng chuyển `-1` thành CPU=0**; 0 là phép đo hợp lệ, -1 nghĩa **không có dữ liệu**.

### 7.4. Tránh thay global setting trong production

`setThreadCpuTimeEnabled(true)` là thay đổi behavior của ThreadMXBean ở phạm vi JVM. Không nên bật/tắt theo request của một dashboard hoặc khi mỗi alert nổ; việc thay đổi có thể ảnh hưởng chi phí và consumers khác.

Nếu cần thử trong một chương trình độc lập, ghi nhớ giá trị ban đầu, chỉ bật khi supported rồi **khôi phục trong `finally`**. Nhưng khôi phục cũng không “undo” mọi số liệu đã được tính trong khoảng thời gian test.

## 8. Thread contention monitoring — blocked/waited time

`isThreadContentionMonitoringSupported()` cho biết VM có hỗ trợ đo contention không. Khi enabled:
- `getBlockedCount()`: số lần thread bị chặn khi vào/reenter object monitor.
- `getWaitedCount()`: số lần thread chờ notification/timing theo các trường hợp được JVM theo dõi.
- `getBlockedTime()`: tổng **milliseconds** thread chờ object monitor từ khi contention measurement được bật.
- `getWaitedTime()`: tổng **milliseconds** chờ theo cơ chế do JDK mô tả.

`getBlockedTime()` và `getWaitedTime()` trả **`-1` khi contention monitoring disabled**. Không suy `-1` là “chưa từng blocked”. Khi bật lại monitoring, tích lũy thời gian có thể được reset theo contract; một số counts tiếp tục là số lần lũy kế.

### 8.1. Mẫu guard

```java
if (bean.isThreadContentionMonitoringSupported()) {
    boolean enabled = bean.isThreadContentionMonitoringEnabled();
    if (enabled) {
        ThreadInfo info = bean.getThreadInfo(id, 0);
        if (info != null && info.getBlockedTime() >= 0) {
            // Time in milliseconds; this is an observation.
        }
    }
}
```

Đây là snippet, không tự bật/tắt trên JVM production. Nếu cần quyết định bật thật, hãy kiểm soát từ configuration/startup và đo overhead.

### 8.2. Contention time không phải toàn bộ latency

Một thread có thể ngủ, chờ socket I/O, chờ database, chờ condition, đợi queue, hoặc bị OS preempt. `getBlockedTime()` chỉ đo phạm vi **object monitor contention** theo API, không phải toàn bộ thời gian request trì hoãn hay tất cả công cụ synchronization.

Đừng đổ lỗi cho “lock contention” chỉ vì request chậm mà không có số liệu blockCount/blockTime tương ứng.

## 9. Object monitor và ownable synchronizer

### 9.1. Object monitor — `synchronized`

```java
synchronized (lock) {
    // Own the monitor for lock.
}
```

Một platform thread chờ vào vùng `synchronized` có `Thread.State.BLOCKED`. `ThreadInfo` có thể cung cấp `getLockInfo()`, `getLockOwnerId()`, `getLockOwnerName()` và danh sách `MonitorInfo` mà owner giữ.

Khi lấy monitor details cần `isObjectMonitorUsageSupported()` và request `lockedMonitors=true`. Sử dụng chi tiết để xác định **điểm tranh chấp** và critical section, không can thiệp trực tiếp vào monitor.

### 9.2. Ownable synchronizer — `ReentrantLock`

`java.util.concurrent.locks.ReentrantLock` là một `AbstractOwnableSynchronizer` có owner thread. Nó không phải Java object monitor của `synchronized`, nên:
- `findMonitorDeadlockedThreads()` chỉ tìm deadlock **object monitors**.
- `findDeadlockedThreads()` có thể tìm cả monitors **và ownable synchronizers**, nếu JVM hỗ trợ `isSynchronizerUsageSupported()`.
- Khi chụp lock details, dùng `lockedSynchronizers=true` để lấy `LockInfo` tương ứng.

Nhiều cơ chế đồng bộ khác nhau không nhất thiết nằm trong hai nhóm có thể giám sát này. Không suy `findDeadlockedThreads()==null` nghĩa toàn bộ chương trình không thể treo.

## 10. Deadlock detection và giới hạn

### 10.1. Hai API cần chọn đúng

| Method | Phạm vi deadlock | Virtual threads |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Chu trình platform threads chờ **object monitors** | Không tìm vòng có virtual |
| `findDeadlockedThreads()` | Chu trình platform threads chờ monitors hoặc **ownable synchronizers** | Không tìm vòng có virtual |

`findDeadlockedThreads()` có thể ném `UnsupportedOperationException` nếu JVM không hỗ trợ monitoring ownable synchronizers. Method chỉ dành cho **troubleshooting**, chi phí có thể đáng kể.

### 10.2. Ví dụ tình huống

```text
Platform A owns ReentrantLock L1, waits for L2
Platform B owns ReentrantLock L2, waits for L1
              |
              v
findDeadlockedThreads(): returns both IDs
findMonitorDeadlockedThreads(): does not return this cycle
```

Chương trình Java 21 trong bài dựng đúng tình huống này với `lockInterruptibly()`, phát hiện hai IDs, rồi `interrupt()` cả hai và `join()` để giải phóng locks.

**Lưu ý đặc biệt:** Đoạn mã tạo deadlock là **fixture có giới hạn trong JVM test riêng**, không dùng trong production. Không tạo deadlock bằng hai `synchronized` không thể interrupt rồi để lại process bị treo. `ReentrantLock.lockInterruptibly` cho phép dừng vòng chờ thử nghiệm sạch sẽ.

### 10.3. Phát hiện deadlock không tự sửa deadlock

`findDeadlockedThreads` chỉ trả IDs. Nó không:
- Tự nhả locks.
- Ưu tiên một thread hoặc hủy request.
- Giải quyết tất cả application-level waits.
- Nhìn thấy deadlocks có virtual threads trong cycle.
- Chứng minh an toàn khi không tìm thấy cycle ở một snapshot.

Giải pháp thật phải sửa lock ordering, giảm nested locks, có timeouts/cancellation, thiết kế state ownership và kiểm thử concurrency.

## 11. Dùng JMX để giám sát ThreadMXBean

Platform JMX cho phép raw client đọc:
```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName on = new ObjectName("java.lang:type=Threading");

Integer count = (Integer) server.getAttribute(on, "ThreadCount");
```

Với operation `getThreadInfo`, giá trị `ThreadInfo` được ánh xạ qua Open Types:

```java
Object raw = server.invoke(
        on, "getThreadInfo",
        new Object[]{platformId, 5},
        new String[]{"long", "int"});

ThreadInfo converted =
        ThreadInfo.from((CompositeData) raw);
```

Hai snippets cần imports và biến `platformId` còn sống. Tham số signature dùng `"long"`/`"int"` theo raw method signature. Nếu ID đã chết hoặc virtual, kết quả có thể null — phải kiểm tra trước khi cast.

Điều này cho phép công cụ JMX không biết application-specific class vẫn đọc state/thread metadata. Tuy nhiên, **JMX remote connector** là một attack surface riêng: cần auth/TLS/authorization/firewall và bảo vệ diagnostic data.

## 12. Quan sát virtual threads bằng công cụ đúng

Kể từ Java 21, JDK có công cụ riêng cho virtual threads. **Không thay `ThreadMXBean` bằng cách trộn virtual threads vào `getAllThreadIds`** hoặc tự coi carrier count là virtual count.

### 12.1. `jcmd Thread.dump_to_file`

Theo tài liệu Oracle JDK 26, có thể dump **platform và virtual threads** bằng:

```bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

`<pid>` là PID thật của JVM đang chẩn đoán (thay bằng số cụ thể khi chạy); đây là **lệnh vận hành**, không phải lệnh dùng trực tiếp trong fixture. Trên JVM/OS phù hợp cần quyền attach tương ứng và đường dẫn output có thể ghi. JSON thuận tiện cho tooling; `-format=plain` cũng được JDK 26 `jcmd` mô tả.

Cần phân biệt:
- `jcmd <pid> Thread.print` chủ yếu liệt kê platform threads và **các mounted virtual threads**, không phải toàn bộ virtual tasks đang unmounted.
- `Thread.dump_to_file` liệt kê **cả platform và virtual threads**, nhưng là observation không phải **một snapshot toàn cục nhất quán** và không tự chạy deadlock detection.
- Thu thập dump có thể lớn và chứa tên luồng, stack, path hoặc thông tin nhạy cảm. Chỉ cấp quyền cho on-call/operations có thẩm quyền, giới hạn retention.

### 12.2. `VirtualThreadSchedulerMXBean` — JDK 24+

Đây là API **`jdk.management.VirtualThreadSchedulerMXBean`**, có từ **JDK 24**, không phải `java.lang.management.ThreadMXBean`. Nó được đăng ký ở:

```text
jdk.management:type=VirtualThreadScheduler
```

Thông tin khả dụng:
- `getParallelism()`: target parallelism của scheduler.
- `getPoolSize()`: số platform workers mà scheduler đã tạo và chưa terminate, có thể `-1` nếu unknown.
- `getMountedVirtualThreadCount()`: ước lượng số virtual threads đang mounted, có thể `-1`.
- `getQueuedVirtualThreadCount()`: ước lượng queue, có thể `-1`.
- `setParallelism(int)`: **thay đổi scheduler**; không gọi khi chỉ muốn quan sát.

**Không suy từ `getPoolSize()` có chính xác bao nhiêu virtual threads đang tồn tại**; đây là số platform threads của scheduler, không phải số virtual tasks. Queued/mounted counts là estimates theo API. Bài có chương trình JDK 24 nhỏ để test scheduler API mà **chỉ đọc**.

### 12.3. JDK Flight Recorder (JFR)

JFR có các sự kiện hữu ích tùy cấu hình/runtime, ví dụ:
- `jdk.VirtualThreadStart` và `jdk.VirtualThreadEnd`.
- `jdk.VirtualThreadPinned`.
- `jdk.VirtualThreadSubmitFailed`.

Không mặc định mọi event được bật hoặc có cùng threshold ở mọi cấu hình JFR. Nên xác minh JDK 26 runtime, recording settings, event settings và retention. JFR hữu ích khi cần đo **vòng đời/sự kiện virtual threads**, thay vì dùng `ThreadMXBean.getThreadCount` làm proxy.

## 13. Nguyên tắc sampling và chi phí

### 13.1. Tầng nhẹ — định kỳ

Với mỗi lần scrape nhẹ:
- `getThreadCount()`.
- `getDaemonThreadCount()`.
- `getPeakThreadCount()` nhưng **không reset** tự tiện.
- `getTotalStartedThreadCount()`.
- Các JVM/OS CPU metrics phù hợp nếu cần theo dõi process tổng thể.

Đặt sampling interval phù hợp tải và mục tiêu quan sát. Nếu thread pool chạm ngưỡng, cần so sánh cùng queue size, request rate, blocked tasks và thời gian phản hồi trước khi kết luận leak.

### 13.2. Tầng chẩn đoán — khi có tín hiệu

Khi có dấu hiệu bất thường:
1. Lấy `getAllThreadIds()` và một tập IDs có giới hạn.
2. Lấy `getThreadInfo(ids, 8)` để xem trạng thái/stack ngắn.
3. Chỉ thu chi tiết monitors/synchronizers khi capability hỗ trợ và có giá trị điều tra.
4. Nếu nghi deadlock, dùng API tương ứng, có timeout và logging an toàn.
5. Với virtual workloads, dùng `jcmd Thread.dump_to_file` hoặc JFR thay vì ThreadMXBean.
6. Ghi nhận timestamp, build JDK, process identity, deployment version và sampling context.

### 13.3. Không coi stack trace là public metrics

Stack traces có thể mang:
- Tên methods/classes nội bộ.
- File paths, package names.
- Dữ liệu từ class names/tasks và message.
- Thông tin lock identities/owners và timing.

Không xuất thẳng thread dump trên public `/health` hoặc logs không có access control. Khi cần export, định nghĩa retention, masking, compressed storage và audit. Mọi probes phải giới hạn tổng số threads và size output.

## 14. Chương trình cơ bản tương thích Java 17

File `PlatformThreadBasic17.java` kiểm tra phần **platform thread** mà không cần API virtual threads. Nó:
- Lấy ThreadMXBean.
- Kiểm tra platform thread count và IDs có giá trị.
- Kiểm tra thứ tự của `getThreadInfo(ids,0)`.
- Xác nhận depth 0 không có stack frames.
- Không gọi `Thread.getId()` đã bị deprecated trên JDK mới.
- Không thay global CPU/contention state và không mở remote JMX.

### 14.1. Toàn bộ file `PlatformThreadBasic17.java`


```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;

public final class PlatformThreadBasic17 {
    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        if (bean == null) throw new AssertionError("missing ThreadMXBean");
        System.out.println("PASS bean-present");

        if (bean.getThreadCount() < 1)
            throw new AssertionError("no live platform thread");
        System.out.println("PASS platform-count-positive");

        long[] ids = bean.getAllThreadIds();
        if (ids.length == 0)
            throw new AssertionError("no platform thread IDs");
        System.out.println("PASS platform-ids-present");

        ThreadInfo[] infos = bean.getThreadInfo(ids, 0);
        if (infos.length != ids.length)
            throw new AssertionError("index alignment");
        System.out.println("PASS threadinfo-aligned");

        if (Arrays.stream(infos).noneMatch(info -> info != null))
            throw new AssertionError("missing live platform ThreadInfo");
        System.out.println("PASS one-live-platform-snapshot");

        if (Arrays.stream(infos).anyMatch(info ->
                info != null && info.getStackTrace().length != 0))
            throw new AssertionError("unexpected stack with depth zero");
        System.out.println("PASS zero-stack-depth");
        System.out.println("passed=6");
    }
}
```

### 14.2. Chạy trên JDK 17 trở lên

```bash
javac --release 17 -encoding UTF-8 PlatformThreadBasic17.java
java PlatformThreadBasic17
```

Stdout đã xác minh trên OpenJDK 24:

```text
PASS bean-present
PASS platform-count-positive
PASS platform-ids-present
PASS threadinfo-aligned
PASS one-live-platform-snapshot
PASS zero-stack-depth
passed=6
```

Bộ test không giả định có tên thread, tổng số threads, thời gian CPU hay monitor cụ thể của hệ điều hành. Do threads có thể kết thúc giữa các phép đọc, code chỉ yêu cầu **có ít nhất một ThreadInfo còn sống** chứ không đòi mọi ID trong snapshot đều còn sống.

## 15. Chương trình Java 21: 79 kiểm thử platform vs virtual, CPU và deadlock

Vì cần dùng `Thread.ofVirtual` và `Thread.threadId` hiện hành, file `PlatformThreadMXBeanDemo.java` đặt baseline **Java 21** (không tương thích `--release 17`). Trong một JVM thử nghiệm riêng, chương trình:

1. Lấy chuẩn `ThreadMXBean` và xác minh `java.lang:type=Threading`.
2. Khởi chạy một platform thread và một virtual thread, giữ chúng sống bằng `CountDownLatch`.
3. Xác minh ID platform nằm trong `getAllThreadIds` và ID virtual **không nằm**.
4. Kiểm tra `getThreadInfo` của platform có dữ liệu, virtual trả null.
5. Kiểm tra array alignment với ID platform/virtual/missing.
6. Kiểm tra độ sâu stack `0`/`5` và bounded `dumpAllThreads(...,4)`.
7. Đọc platform MBeanServer raw `ThreadCount` và `ThreadInfo` dạng `CompositeData`, dựng lại bằng `ThreadInfo.from`.
8. Chỉ đo CPU time nếu JVM hỗ trợ, khôi phục trạng thái enabled ban đầu.
9. Chỉ bật contention timing trong JVM test nếu supported; khôi phục trong `finally`.
10. Tạo một thread giữ object monitor và một platform thread khác bị `BLOCKED`; xác minh owner ID/name và `MonitorInfo` nếu supported.
11. Tạo **deadlock có thể hủy bằng interrupt** với hai `ReentrantLock`, cho `findDeadlockedThreads` phát hiện và kiểm tra `findMonitorDeadlockedThreads` không nhầm loại khóa.
12. Giải phóng monitor, interrupt/join deadlock fixture và dọn cả platform/virtual worker.
13. Xác minh ThreadInfo của worker platform đã terminate là null.
14. In kết quả **79/79 assertions PASS** trên OpenJDK24.

### 15.1. Chỉ dùng trong JVM test riêng

Fixture cố ý bật tùy chọn đo CPU/contention nếu được hỗ trợ để xác minh behavior, và cố ý tạo deadlock tạm thời để test detection. Đây **không phải mã monitoring production để copy chạy trong mọi request**. Test:
- Không sử dụng network, JMX remote hoặc OS process attach.
- Không gọi `Thread.stop()`/`Thread.suspend()`.
- Dùng `lockInterruptibly()` để kết thúc deadlock fixture, tránh treo thread không thể cleanup.
- Đặt timeout bounded khi chờ latch/state/deadlock.
- Khôi phục cờ CPU/contention nếu nó đã tự bật.
- Chỉ in tên các kiểm thử, không in stack traces hoặc tên các luồng thật khác của hệ thống.

### 15.2. Toàn bộ file `PlatformThreadMXBeanDemo.java`


```java
import java.lang.management.ManagementFactory;
import java.lang.management.MonitorInfo;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

public final class PlatformThreadMXBeanDemo {
    private static int passed;

    static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError("FAIL " + name);
        System.out.println("PASS " + name);
        passed++;
    }

    static boolean contains(long[] ids, long id) {
        for (long found : ids) if (found == id) return true;
        return false;
    }

    static boolean await(CountDownLatch latch) {
        try {
            return latch.await(5, TimeUnit.SECONDS);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    static void requireWait(CountDownLatch latch) {
        if (!await(latch)) throw new IllegalStateException("latch timeout");
    }

    static ThreadInfo waitForState(ThreadMXBean bean, Thread thread,
                                   Thread.State state) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(4);
        while (System.nanoTime() < deadline) {
            ThreadInfo info = bean.getThreadInfo(thread.threadId(), 8);
            if (info != null && info.getThreadState() == state) {
                return info;
            }
            Thread.sleep(5);
        }
        throw new AssertionError("Expected state not reached: " + state);
    }

    static long[] waitForDeadlock(ThreadMXBean bean, long idA,
                                  long idB) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            long[] ids = bean.findDeadlockedThreads();
            if (ids != null && contains(ids, idA) && contains(ids, idB)) {
                return ids;
            }
            Thread.sleep(10);
        }
        throw new AssertionError("Expected ownable synchronizer deadlock");
    }

    static boolean rejectsInvalidThreadId(ThreadMXBean bean) {
        try {
            bean.getThreadInfo(0);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    static boolean rejectsNegativeDepth(ThreadMXBean bean, long id) {
        try {
            bean.getThreadInfo(id, -1);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        check("thread-mxbean-present", bean != null);
        check("thread-mxbean-in-java-management",
                bean.getClass().getModule().isNamed());
        check("standard-threading-objectname",
                bean.getObjectName().equals(
                        new ObjectName("java.lang:type=Threading")));
        check("current-thread-is-platform",
                !Thread.currentThread().isVirtual());
        check("current-thread-id-positive",
                Thread.currentThread().threadId() > 0);

        CountDownLatch platformExit = new CountDownLatch(1);
        CountDownLatch platformReady = new CountDownLatch(1);
        Thread platform = Thread.ofPlatform().name("demo-platform")
                .daemon(true).unstarted(() -> {
                    platformReady.countDown();
                    requireWait(platformExit);
                });
        CountDownLatch virtualExit = new CountDownLatch(1);
        CountDownLatch virtualReady = new CountDownLatch(1);
        Thread virtual = Thread.ofVirtual().name("demo-virtual")
                .unstarted(() -> {
                    virtualReady.countDown();
                    requireWait(virtualExit);
                });
        platform.start();
        virtual.start();

        boolean originalCpu = false;
        boolean cpuSupported =
                bean.isThreadCpuTimeSupported();
        boolean currentCpuSupported =
                bean.isCurrentThreadCpuTimeSupported();
        boolean changedCpu = false;
        boolean contentionSupported =
                bean.isThreadContentionMonitoringSupported();
        boolean originalContention = false;
        boolean changedContention = false;
        try {
            check("platform-worker-ready", await(platformReady));
            check("virtual-worker-ready", await(virtualReady));
            check("platform-is-alive", platform.isAlive());
            check("virtual-is-alive", virtual.isAlive());
            check("platform-flag-not-virtual", !platform.isVirtual());
            check("virtual-flag-is-virtual", virtual.isVirtual());
            check("distinct-thread-ids",
                    platform.threadId() != virtual.threadId());
            long[] ids = bean.getAllThreadIds();
            check("platform-in-all-thread-ids",
                    contains(ids, platform.threadId()));
            check("virtual-excluded-from-all-thread-ids",
                    !contains(ids, virtual.threadId()));
            check("thread-count-positive", bean.getThreadCount() > 0);
            check("peak-at-least-current-count",
                    bean.getPeakThreadCount() >= bean.getThreadCount());
            check("started-count-at-least-one",
                    bean.getTotalStartedThreadCount() >= 1);
            check("daemon-count-within-total",
                    bean.getDaemonThreadCount() <= bean.getThreadCount());
            check("threadinfo-virtual-null",
                    bean.getThreadInfo(virtual.threadId()) == null);

            ThreadInfo info = bean.getThreadInfo(platform.threadId());
            check("threadinfo-platform-not-null", info != null);
            check("threadinfo-matching-id",
                    info.getThreadId() == platform.threadId());
            check("threadinfo-matching-name",
                    info.getThreadName().equals("demo-platform"));
            check("threadinfo-platform-daemon", info.isDaemon());
            check("threadinfo-state-waiting",
                    info.getThreadState() == Thread.State.WAITING
                            || info.getThreadState()
                                    == Thread.State.TIMED_WAITING);
            check("threadinfo-no-stack-by-default",
                    info.getStackTrace().length == 0);
            check("threadinfo-unavailable-lock-data",
                    info.getLockedMonitors().length == 0
                            && info.getLockedSynchronizers().length == 0);
            ThreadInfo limited = bean.getThreadInfo(
                    platform.threadId(), 5);
            check("bounded-stack-depth",
                    limited.getStackTrace().length <= 5);
            check("bounded-stack-nonempty-for-wait",
                    limited.getStackTrace().length > 0);
            ThreadInfo[] aligned = bean.getThreadInfo(
                    new long[] {platform.threadId(), virtual.threadId(),
                            Long.MAX_VALUE}, 0);
            check("batch-snapshot-alignment", aligned.length == 3);
            check("batch-first-is-platform", aligned[0] != null);
            check("batch-virtual-is-null", aligned[1] == null);
            check("batch-missing-is-null", aligned[2] == null);
            check("single-nonexistent-is-null",
                    bean.getThreadInfo(Long.MAX_VALUE) == null);
            check("zero-id-rejected", rejectsInvalidThreadId(bean));
            check("negative-stack-depth-rejected",
                    rejectsNegativeDepth(bean, platform.threadId()));

            ThreadInfo[] dump = bean.dumpAllThreads(false, false, 4);
            check("bounded-dump-has-platform",
                    Arrays.stream(dump).anyMatch(
                            t -> t.getThreadId() == platform.threadId()));
            check("bounded-dump-excludes-virtual",
                    Arrays.stream(dump).noneMatch(
                            t -> t.getThreadId() == virtual.threadId()));
            check("all-dump-stacks-bounded",
                    Arrays.stream(dump).allMatch(
                            t -> t.getStackTrace().length <= 4));
            check("dump-no-lock-collections",
                    Arrays.stream(dump).allMatch(
                            t -> t.getLockedMonitors().length == 0
                                    && t.getLockedSynchronizers().length == 0));

            MBeanServer jmx = ManagementFactory.getPlatformMBeanServer();
            ObjectName name = new ObjectName("java.lang:type=Threading");
            check("jmx-platform-mbean-registered",
                    jmx.isRegistered(name));
            check("jmx-thread-count-attribute-integer",
                    jmx.getAttribute(name, "ThreadCount") instanceof Integer);
            check("jmx-daemon-thread-count-attribute-integer",
                    jmx.getAttribute(name, "DaemonThreadCount")
                            instanceof Integer);
            Object raw = jmx.invoke(name, "getThreadInfo",
                    new Object[]{platform.threadId(), 5},
                    new String[]{"long", "int"});
            check("jmx-threadinfo-is-composite",
                    raw instanceof CompositeData);
            ThreadInfo converted = ThreadInfo.from((CompositeData) raw);
            check("compositedata-restores-threadinfo",
                    converted.getThreadId() == platform.threadId());
            check("compositedata-stack-depth-bounded",
                    converted.getStackTrace().length <= 5);

            check("cpu-support-capability-consistent",
                    !cpuSupported || currentCpuSupported);
            if (cpuSupported || currentCpuSupported) {
                originalCpu = bean.isThreadCpuTimeEnabled();
                if (!originalCpu) {
                    bean.setThreadCpuTimeEnabled(true);
                    changedCpu = true;
                }
                check("cpu-measurement-enabled",
                        bean.isThreadCpuTimeEnabled());
                if (cpuSupported) {
                    check("platform-cpu-nanos-nonnegative",
                            bean.getThreadCpuTime(platform.threadId()) >= 0);
                    check("virtual-cpu-not-reported",
                            bean.getThreadCpuTime(virtual.threadId()) == -1);
                    check("terminated-or-unknown-cpu-negative-one",
                            bean.getThreadCpuTime(Long.MAX_VALUE) == -1);
                    check("platform-user-cpu-nanos-nonnegative",
                            bean.getThreadUserTime(platform.threadId()) >= 0);
                }
                if (currentCpuSupported) {
                    check("current-thread-cpu-nonnegative",
                            bean.getCurrentThreadCpuTime() >= 0);
                    check("current-thread-user-cpu-nonnegative",
                            bean.getCurrentThreadUserTime() >= 0);
                }
            }
            check("current-platform-threadinfo-present",
                    bean.getThreadInfo(Thread.currentThread().threadId())
                            != null);
            if (contentionSupported) {
                originalContention =
                        bean.isThreadContentionMonitoringEnabled();
                if (!originalContention) {
                    bean.setThreadContentionMonitoringEnabled(true);
                    changedContention = true;
                }
                check("contention-enabled-in-fixture",
                        bean.isThreadContentionMonitoringEnabled());
                ThreadInfo measured =
                        bean.getThreadInfo(platform.threadId(), 0);
                check("blocked-count-nonnegative",
                        measured.getBlockedCount() >= 0);
                check("waited-count-nonnegative",
                        measured.getWaitedCount() >= 0);
                check("blocked-millis-nonnegative",
                        measured.getBlockedTime() >= 0);
                check("waited-millis-nonnegative",
                        measured.getWaitedTime() >= 0);
            }

            Object monitor = new Object();
            CountDownLatch monitorHeld = new CountDownLatch(1);
            CountDownLatch releaseMonitor = new CountDownLatch(1);
            Thread holder = Thread.ofPlatform().name("demo-holder")
                    .daemon(true).unstarted(() -> {
                        synchronized (monitor) {
                            monitorHeld.countDown();
                            requireWait(releaseMonitor);
                        }
                    });
            Thread blocked = Thread.ofPlatform().name("demo-blocked")
                    .daemon(true).unstarted(() -> {
                        synchronized (monitor) {
                            // Only proceeds after holder is released.
                        }
                    });
            try {
                holder.start();
                check("monitor-holder-ready", await(monitorHeld));
                blocked.start();
                ThreadInfo blockedInfo = waitForState(
                        bean, blocked, Thread.State.BLOCKED);
                check("blocked-platform-thread-state",
                        blockedInfo.getThreadState()
                                == Thread.State.BLOCKED);
                check("blocked-lock-owner-platform-id",
                        blockedInfo.getLockOwnerId()
                                == holder.threadId());
                check("blocked-thread-has-lock-info",
                        blockedInfo.getLockInfo() != null);
                check("blocked-thread-lock-owner-name",
                        blockedInfo.getLockOwnerName().equals("demo-holder"));
                if (bean.isObjectMonitorUsageSupported()) {
                    ThreadInfo[] withMonitors =
                            bean.getThreadInfo(new long[] {
                                    holder.threadId(), blocked.threadId()
                            }, true, false, 8);
                    check("locked-monitor-held-by-owner",
                            withMonitors[0].getLockedMonitors().length >= 1);
                    check("blocked-thread-does-not-own-target-monitor",
                            Arrays.stream(
                                    withMonitors[1].getLockedMonitors())
                                    .noneMatch(m -> m.getIdentityHashCode()
                                            == System.identityHashCode(monitor)));
                }
            } finally {
                releaseMonitor.countDown();
                holder.join(3000);
                blocked.join(3000);
            }
            check("blocked-pair-cleaned-up",
                    !holder.isAlive() && !blocked.isAlive());

            boolean syncSupported = bean.isSynchronizerUsageSupported();
            check("synchronizer-capability-repeatable-read",
                    bean.isSynchronizerUsageSupported() == syncSupported);
            if (syncSupported) {
                ReentrantLock left = new ReentrantLock();
                ReentrantLock right = new ReentrantLock();
                CountDownLatch leftHeld = new CountDownLatch(1);
                CountDownLatch rightHeld = new CountDownLatch(1);
                Thread a = Thread.ofPlatform().name("demo-deadlock-a")
                        .daemon(true).unstarted(() -> {
                            left.lock();
                            try {
                                leftHeld.countDown();
                                requireWait(rightHeld);
                                right.lockInterruptibly();
                                try { /* unreachable before cancellation */ }
                                finally { right.unlock(); }
                            } catch (InterruptedException e) {
                                Thread.currentThread().interrupt();
                            } finally { left.unlock(); }
                        });
                Thread b = Thread.ofPlatform().name("demo-deadlock-b")
                        .daemon(true).unstarted(() -> {
                            right.lock();
                            try {
                                rightHeld.countDown();
                                requireWait(leftHeld);
                                left.lockInterruptibly();
                                try { /* unreachable before cancellation */ }
                                finally { left.unlock(); }
                            } catch (InterruptedException e) {
                                Thread.currentThread().interrupt();
                            } finally { right.unlock(); }
                        });
                try {
                    a.start();
                    b.start();
                    check("deadlock-first-lock-held", await(leftHeld));
                    check("deadlock-second-lock-held", await(rightHeld));
                    long[] deadlocked = waitForDeadlock(
                            bean, a.threadId(), b.threadId());
                    check("ownable-synchronizer-deadlock-detected",
                            contains(deadlocked, a.threadId())
                                    && contains(deadlocked, b.threadId()));
                    long[] monitorOnly =
                            bean.findMonitorDeadlockedThreads();
                    check("monitor-only-excludes-reentrantlock-cycle",
                            monitorOnly == null
                            || !(contains(monitorOnly, a.threadId())
                                    && contains(monitorOnly, b.threadId())));
                    ThreadInfo[] withSynchronizers =
                            bean.getThreadInfo(new long[]{
                                    a.threadId(), b.threadId()
                            }, false, true, 8);
                    check("ownable-synchronizer-owner-present",
                            withSynchronizers[0].getLockedSynchronizers()
                                    .length > 0
                            && withSynchronizers[1].getLockedSynchronizers()
                                    .length > 0);
                } finally {
                    a.interrupt();
                    b.interrupt();
                    a.join(3000);
                    b.join(3000);
                }
                check("deadlock-fixture-interruptibly-cleaned",
                        !a.isAlive() && !b.isAlive());
            }
            check("positive-platform-id-while-alive",
                    platform.threadId() > 0);
        } finally {
            platformExit.countDown();
            virtualExit.countDown();
            platform.join(3000);
            virtual.join(3000);
            if (changedContention) {
                bean.setThreadContentionMonitoringEnabled(
                        originalContention);
            }
            if (changedCpu) bean.setThreadCpuTimeEnabled(originalCpu);
        }
        check("platform-worker-terminated", !platform.isAlive());
        check("virtual-worker-terminated", !virtual.isAlive());
        check("post-termination-threadinfo-null",
                bean.getThreadInfo(platform.threadId()) == null);
        check("thread-management-bean-still-available",
                ManagementFactory.getThreadMXBean() == bean);
        System.out.println("passed=" + passed);
    }
}
```

### 15.3. Biên dịch và chạy

```bash
javac --release 21 -encoding UTF-8 PlatformThreadMXBeanDemo.java
java PlatformThreadMXBeanDemo
```

Chạy bằng JDK 21 trở lên hỗ trợ virtual threads, trên JVM có `java.management`. Fixture đã được biên dịch `--release 21` và thực thi trên **OpenJDK 24**.

### 15.4. Stdout thật đã xác minh

```text
PASS thread-mxbean-present
PASS thread-mxbean-in-java-management
PASS standard-threading-objectname
PASS current-thread-is-platform
PASS current-thread-id-positive
PASS platform-worker-ready
PASS virtual-worker-ready
PASS platform-is-alive
PASS virtual-is-alive
PASS platform-flag-not-virtual
PASS virtual-flag-is-virtual
PASS distinct-thread-ids
PASS platform-in-all-thread-ids
PASS virtual-excluded-from-all-thread-ids
PASS thread-count-positive
PASS peak-at-least-current-count
PASS started-count-at-least-one
PASS daemon-count-within-total
PASS threadinfo-virtual-null
PASS threadinfo-platform-not-null
PASS threadinfo-matching-id
PASS threadinfo-matching-name
PASS threadinfo-platform-daemon
PASS threadinfo-state-waiting
PASS threadinfo-no-stack-by-default
PASS threadinfo-unavailable-lock-data
PASS bounded-stack-depth
PASS bounded-stack-nonempty-for-wait
PASS batch-snapshot-alignment
PASS batch-first-is-platform
PASS batch-virtual-is-null
PASS batch-missing-is-null
PASS single-nonexistent-is-null
PASS zero-id-rejected
PASS negative-stack-depth-rejected
PASS bounded-dump-has-platform
PASS bounded-dump-excludes-virtual
PASS all-dump-stacks-bounded
PASS dump-no-lock-collections
PASS jmx-platform-mbean-registered
PASS jmx-thread-count-attribute-integer
PASS jmx-daemon-thread-count-attribute-integer
PASS jmx-threadinfo-is-composite
PASS compositedata-restores-threadinfo
PASS compositedata-stack-depth-bounded
PASS cpu-support-capability-consistent
PASS cpu-measurement-enabled
PASS platform-cpu-nanos-nonnegative
PASS virtual-cpu-not-reported
PASS terminated-or-unknown-cpu-negative-one
PASS platform-user-cpu-nanos-nonnegative
PASS current-thread-cpu-nonnegative
PASS current-thread-user-cpu-nonnegative
PASS current-platform-threadinfo-present
PASS contention-enabled-in-fixture
PASS blocked-count-nonnegative
PASS waited-count-nonnegative
PASS blocked-millis-nonnegative
PASS waited-millis-nonnegative
PASS monitor-holder-ready
PASS blocked-platform-thread-state
PASS blocked-lock-owner-platform-id
PASS blocked-thread-has-lock-info
PASS blocked-thread-lock-owner-name
PASS locked-monitor-held-by-owner
PASS blocked-thread-does-not-own-target-monitor
PASS blocked-pair-cleaned-up
PASS synchronizer-capability-repeatable-read
PASS deadlock-first-lock-held
PASS deadlock-second-lock-held
PASS ownable-synchronizer-deadlock-detected
PASS monitor-only-excludes-reentrantlock-cycle
PASS ownable-synchronizer-owner-present
PASS deadlock-fixture-interruptibly-cleaned
PASS positive-platform-id-while-alive
PASS platform-worker-terminated
PASS virtual-worker-terminated
PASS post-termination-threadinfo-null
PASS thread-management-bean-still-available
passed=79
```

**Kết quả:** 79/79 PASS. Tất cả các chi tiết mang tính race trong fixture đều dùng latches và bounded retry để tránh phụ thuộc một sleep cố định. Riêng việc support metrics/lock capabilities **phụ thuộc JVM**; trên OpenJDK24 đã dùng để kiểm thử, các tính năng tương ứng có sẵn nên 79 bài kiểm tra được thực thi. Nếu chạy trên provider khác, một số nhánh có thể bỏ qua và số PASS nhỏ hơn — đó không phải là lỗi dữ liệu nếu feature thực sự unsupported.

### 15.5. Những điểm nên đọc lại trong mã

| Nhóm test | Assertions tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Identity | `standard-threading-objectname` | MXBean đúng platform name |
| Dual thread kinds | `platform-in-all-thread-ids`, `virtual-excluded-from-all-thread-ids` | Không nhầm platform/virtual |
| Snapshot | `threadinfo-virtual-null`, `threadinfo-platform-not-null` | ThreadInfo chỉ hỗ trợ platform |
| Depth | `bounded-stack-depth`, `dump-no-lock-collections` | Kiểm soát chi phí/trường nhận |
| Batch IDs | `batch-snapshot-alignment`, `batch-virtual-is-null` | Bảo toàn index/null |
| Invalid inputs | `zero-id-rejected`, `negative-stack-depth-rejected` | Validation API |
| JMX raw | `jmx-threadinfo-is-composite` | Open Data được dùng qua MBeanServer |
| CPU | `platform-cpu-nanos-nonnegative`, `virtual-cpu-not-reported` | CPU time không áp cho virtual |
| Contention | `blocked-millis-nonnegative` | Có guard capability và enabled |
| Object monitor | `blocked-lock-owner-platform-id`, `locked-monitor-held-by-owner` | Phân tích khóa `synchronized` |
| Ownable deadlock | `ownable-synchronizer-deadlock-detected` | ReentrantLock cycle |
| Monitor-only check | `monitor-only-excludes-reentrantlock-cycle` | Hai deadlock APIs không tương đương |
| Cleanup | `deadlock-fixture-interruptibly-cleaned`, `post-termination-threadinfo-null` | Không để JVM test bị treo |

## 16. Probe JDK 24+: MXBean của virtual-thread scheduler

Đây là **API bổ sung của JDK24** chứ không làm ThreadMXBean quan sát virtual threads. Probe chỉ **đọc** scheduler, không gọi `setParallelism()`. Để chạy source, cần JDK 24+ và module `jdk.management`.

### 16.1. File `VirtualScheduler24Probe.java`


```java
import java.lang.management.ManagementFactory;
import jdk.management.VirtualThreadSchedulerMXBean;

public final class VirtualScheduler24Probe {
    public static void main(String[] args) {
        VirtualThreadSchedulerMXBean bean =
                ManagementFactory.getPlatformMXBean(
                        VirtualThreadSchedulerMXBean.class);
        if (bean == null) throw new AssertionError("unavailable");
        System.out.println("PASS scheduler-mxbean-present");
        if (bean.getParallelism() < 1)
            throw new AssertionError("invalid target parallelism");
        System.out.println("PASS scheduler-parallelism-positive");
        if (!bean.getObjectName().toString().equals(
                "jdk.management:type=VirtualThreadScheduler"))
            throw new AssertionError("unexpected ObjectName");
        System.out.println("PASS scheduler-objectname");
        if (bean.getPoolSize() < -1)
            throw new AssertionError("invalid pool size");
        System.out.println("PASS pool-size-optional");
        System.out.println("passed=4");
    }
}
```

### 16.2. Biên dịch và chạy bằng JDK 24+

```bash
javac --release 24 --add-modules jdk.management -encoding UTF-8 VirtualScheduler24Probe.java
java --add-modules jdk.management VirtualScheduler24Probe
```

Stdout OpenJDK24:

```text
PASS scheduler-mxbean-present
PASS scheduler-parallelism-positive
PASS scheduler-objectname
PASS pool-size-optional
passed=4
```

Đây chỉ là **4 assertions** về availability, ObjectName, target parallelism và khả năng `getPoolSize()` trả số hoặc sentinel `-1`. Nó không chứng minh số lượng virtual threads đang sống và không nên được dùng như một phép đếm virtual-thread chính xác.

## 17. Quy trình xử lý sự cố trên production

### 17.1. CPU process tăng cao

1. Xác minh CPU cao là CPU process/host chứ không chỉ request latency.
2. Xem `getThreadCount`, `getTotalStartedThreadCount` và peak để phân biệt thread churn với thread leak.
3. Nếu `isThreadCpuTimeSupported()` và enabled, lấy CPU counters cho các platform IDs có thời gian sống đủ dài.
4. So **delta trong một interval**; không so tích lũy từ threads với tuổi thọ khác nhau.
5. Với virtual workloads, đừng gán CPU carrier trực tiếp cho một virtual user task.
6. Dùng JFR/profiler/JDK diagnostics phù hợp để xem hotspots, và kiểm tra pool/queue/application metrics.

### 17.2. Requests bị treo

1. Xác định request đang chờ HTTP, database, lock, queue, I/O hay thread starvation.
2. Lấy `ThreadInfo` bounded cho platform threads đang nghi ngờ.
3. Xem state `BLOCKED`, lock owner và stack, không kết luận deadlock chỉ từ BLOCKED.
4. Khi nghi lock cycle, gọi `findDeadlockedThreads` nếu supported.
5. Nếu workload chủ yếu virtual threads, dùng `jcmd Thread.dump_to_file` để thấy virtual tasks.
6. Trên phiên bản phù hợp, kết hợp JFR events/VirtualThreadSchedulerMXBean cho scheduler pressure.

### 17.3. Số thread tăng bất thường

- `getThreadCount` tăng có thể do pool size tăng, cached thread pool không giới hạn, thread leaks hoặc carrier workers. Nó **không** trực tiếp chứng minh số virtual tasks tăng.
- `getTotalStartedThreadCount` tăng trong khi live count ổn định có thể do thread churn.
- `getPeakThreadCount` bị reset bởi một thành phần khác có thể làm biểu đồ peak đột ngột giảm; tránh dùng reset trong hệ thống có nhiều monitoring clients.
- Kiểm tra thread pool metrics riêng (active/queue/completed/rejected) và cấu hình executors thay vì chỉ dựa vào MXBean.

### 17.4. Deadlock không được phát hiện

Một `null` trả về từ `findDeadlockedThreads` **không loại trừ**:
- Virtual-thread deadlocks (ngoài phạm vi).
- Application-level circular waits trên futures/queues/network.
- Starvation nhưng không có chu trình ownable monitor/lock.
- Cycles liên quan cơ chế synchronization không được JVM hỗ trợ.
- Race giữa thời điểm chẩn đoán và deadlock thực tế.

Hãy kết hợp timeout, diagnostics logs/JFR/dumps và code review cụ thể.

## 18. Các lỗi thường gặp

**1. Coi ThreadMXBean là virtual-thread counter.**  
Sai. ThreadMXBean chỉ giám sát platform threads.

**2. Nhầm carrier platform thread với virtual thread.**  
Một carrier được tính như platform thread, không đại diện duy nhất cho một virtual request.

**3. Coi `getAllThreadIds()` chứa mọi `Thread` object.**  
Không chứa virtual IDs và chỉ thu live platform IDs tại thời điểm snapshot.

**4. Mong `getThreadInfo(virtualId)` trả details.**  
Theo Java SE26 nó trả null, kể cả virtual vẫn còn sống.

**5. Dùng `getThreadInfo(id)` rồi kỳ vọng stack trace.**  
Overload đơn chỉ lấy depth 0.

**6. Quên check null cho ThreadInfo.**  
ID có thể đã chết hoặc virtual/missing; đừng dereference ngay.

**7. Dùng thread ID làm user ID vĩnh viễn.**  
ID có thể được reuse sau termination.

**8. So counts lấy ở hai thời điểm như atomic snapshot.**  
Threads thay đổi đồng thời, số lượng có thể lệch.

**9. Quên giới hạn maxDepth.**  
Huge stack dumps tốn chi phí và lộ dữ liệu.

**10. Lấy `dumpAllThreads(true,true)` liên tục mỗi giây.**  
Rủi ro overhead trên JVM production; chỉ dùng khi cần điều tra.

**11. Cho rằng `RUNNABLE` đồng nghĩa 100% CPU.**  
Không; Thread.State và CPU usage đo các khía cạnh khác nhau.

**12. Cho rằng `BLOCKED` đồng nghĩa deadlock.**  
Một thread chờ một monitor bình thường không phải deadlock.

**13. Nhầm `getBlockedTime` milliseconds với `getThreadCpuTime` nanoseconds.**  
Tạo biểu đồ sai đơn vị.

**14. Coi CPU `-1` là 0.**  
`-1` là không đo được/không áp dụng, không phải không sử dụng CPU.

**15. Gọi CPU measurement không kiểm tra support flag.**  
Có thể ném UnsupportedOperationException.

**16. Đặt `setThreadCpuTimeEnabled(true)` trong từng HTTP request.**  
Là thay đổi global/overhead không kiểm soát.

**17. Quên contention monitoring có thể disabled.**  
`getBlockedTime/getWaitedTime` trả -1 khi disabled.

**18. Gọi `setThreadContentionMonitoringEnabled` tùy tiện trong production.**  
Có thể làm reset timing stats và ảnh hưởng các consumers khác.

**19. Lấy lockedMonitors khi JVM không hỗ trợ.**  
Phải kiểm tra capability và xử lý UnsupportedOperationException.

**20. Coi lockedMonitors rỗng là không dùng locks khi flag request là false.**  
Dữ liệu chưa được thu, không phải bằng chứng.

**21. Dùng `findMonitorDeadlockedThreads` để tìm vòng chỉ có ReentrantLock.**  
Cần `findDeadlockedThreads` nếu ownable synchronizers supported.

**22. Nghĩ findDeadlockedThreads nhìn thấy virtual cycles.**  
Không theo ThreadMXBean Java SE26.

**23. Tạo deadlock bằng synchronized rồi cố interrupt để thoát.**  
Interrupt không giải phóng monitor acquire; fixture dùng ReentrantLock.lockInterruptibly.

**24. Reset peak mỗi lần scrape.**  
Làm mất số liệu đỉnh dùng chung và che các incidents.

**25. Không quản lý permissions của JMX remote.**  
Một JMX endpoint không bảo vệ có thể lộ dữ liệu/cho phép operations.

**26. In stack traces đầy đủ vào public /health.**  
Rò rỉ metadata nội bộ và tốn chi phí.

**27. Trộn `jcmd Thread.print` với `Thread.dump_to_file`.**  
Công cụ cho các tập virtual threads khác nhau; chọn đúng mục tiêu.

**28. Lấy VirtualThreadSchedulerMXBean poolSize làm virtual-thread count.**  
Pool size là platform workers, không phải virtual instances.

**29. Dùng API JDK24+ trong project build --release 17.**  
Không biên dịch; tách Java17/21/24 fixtures theo đúng version.

**30. Tin stdout của demo là thuộc tính chung của mọi JVM.**  
Các capabilities/CPU time/daemon counts khác nhau theo provider và runtime; code production cần guards.

## 19. Checklist xây hệ thống quan sát luồng

- [ ] Cần phân biệt platform vs virtual ngay từ dashboard schema.
- [ ] Xác nhận JDK/runtime version của service.
- [ ] Giám sát platform counts từ ThreadMXBean đúng ngữ nghĩa.
- [ ] Không dùng platform count để suy virtual thread count.
- [ ] Lấy `getThreadInfo` có giới hạn số IDs/maxDepth.
- [ ] Kiểm tra ThreadInfo null/missing.
- [ ] Không dùng thread IDs làm business identity dài hạn.
- [ ] Đặt units nhất quán: CPU nanoseconds, contention milliseconds.
- [ ] Kiểm tra capability/enabled flags trước CPU/time/lock detail.
- [ ] Bật measurement trong cấu hình được kiểm soát, không theo request.
- [ ] Không reset peak khi nhiều monitoring components dùng chung.
- [ ] Chọn đúng deadlock method theo monitor vs ownable synchronizer.
- [ ] Ghi nhận `findDeadlockedThreads` không thấy virtual cycles.
- [ ] Khi có virtual threads, dùng JFR và `jcmd Thread.dump_to_file`.
- [ ] Với JDK24+, cân nhắc scheduler-level MXBean, không gọi setParallelism khi chỉ quan sát.
- [ ] Phân biệt worker pool active/queue metrics và platform ThreadMXBean count.
- [ ] Có retention/redaction cho stack traces, paths và lock names.
- [ ] Bảo vệ JMX connector bằng auth, TLS, network boundaries và permissions.
- [ ] Kiểm thử trên đúng deployment JDK/provider; nhánh unsupported phải hoạt động an toàn.
- [ ] Thu metrics đủ thưa để không gây chậm JVM đang có sự cố.

## 20. Câu hỏi tự kiểm tra

**1. ThreadMXBean giám sát loại thread nào trong Java SE26?**  
Platform threads, **không** giám sát virtual threads.

**2. Lấy instance ThreadMXBean thế nào?**  
`ManagementFactory.getThreadMXBean()`.

**3. MBean ObjectName chuẩn là gì?**  
`java.lang:type=Threading`.

**4. `getThreadCount` có tính 100.000 virtual threads đang chạy không?**  
Không. Chỉ tính platform threads.

**5. `getAllThreadIds` có bao gồm virtual thread IDs không?**  
Không.

**6. `getThreadInfo(virtualId)` trả gì?**  
`null`.

**7. `getThreadInfo(id)` mặc định có stack trace không?**  
Không; tương đương depth 0.

**8. ThreadInfo từ một ID đã chết có thể là gì?**  
`null`.

**9. Thread ID có được đảm bảo unique mãi mãi?**  
Không; chỉ unique trong vòng đời và có thể reuse sau khi chấm dứt.

**10. `getPeakThreadCount` có ý nghĩa gì?**  
Đỉnh live platform threads từ startup hoặc lần reset peak gần nhất.

**11. `resetPeakThreadCount` có read-only không?**  
Không; nó thay đổi global metric.

**12. CPU time và blocked time dùng đơn vị gì?**  
CPU **nanoseconds**; blocked/waited **milliseconds**.

**13. CPU time = -1 có nghĩa 0% CPU không?**  
Không. Không đo được/không áp dụng.

**14. Có thể gọi CPU time trên mọi JVM không?**  
Không. Phải kiểm tra capabilities và trạng thái enabled.

**15. Contentious blockedTime = -1 khi nào?**  
Khi contention monitoring disabled.

**16. Một thread ở BLOCKED có phải deadlocked không?**  
Không nhất thiết.

**17. findMonitorDeadlockedThreads và findDeadlockedThreads khác nhau ở đâu?**  
Method thứ hai có thể bao gồm ownable synchronizers bên cạnh object monitors.

**18. findDeadlockedThreads có phát hiện chu trình có virtual threads không?**  
Không theo ThreadMXBean Java SE26.

**19. Làm sao dump cả platform và virtual threads?**  
Dùng `jcmd <pid> Thread.dump_to_file -format=json <file>` trong JDK hỗ trợ.

**20. VirtualThreadSchedulerMXBean bắt đầu từ JDK mấy?**  
JDK 24.

**21. Scheduler poolSize có bằng virtual thread count không?**  
Không; đó là số platform scheduler workers.

**22. Có thể dùng ThreadMXBean để quyết định interrupt thread nào không?**  
Không nên; snapshot không phải synchronization controller.

**23. JVM của fixture có mở JMX remote port không?**  
Không. Nó chỉ dùng platform MBeanServer local.

**24. Vì sao fixture deadlock dùng ReentrantLock.lockInterruptibly?**  
Cho phép phát hiện deadlock rồi giải phóng bằng interrupt, tránh để chương trình test bị treo.

**25. Vì sao chỉ có 79 tests trên một JVM mà JDK khác có thể ít hơn?**  
Các tùy chọn CPU/contention/lock monitoring phụ thuộc support flags.

**26. Tại sao có ba mã nguồn Java17/21/24?**  
Mỗi API có minimum Java version khác nhau; tách rõ giúp code biên dịch đúng target.

## 21. Nguồn tài liệu chính thức hiện hành

- [Oracle Java SE 26 — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform-only scope, thread counts/IDs, CPU time, contention, stack snapshots, deadlock detection, capabilities.
- [Oracle Java SE 26 — `ThreadInfo`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadInfo.html): ID/name/state, lock owner, blocked/waited metrics, stacks, `from(CompositeData)`.
- [Oracle Java SE 26 — `ManagementFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html): access platform MXBeans và MBeanServer.
- [Oracle Java SE 26 — `LockInfo`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/LockInfo.html): lock identity information.
- [Oracle Java SE 26 — `MonitorInfo`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MonitorInfo.html): owned object monitor details.
- [Oracle Java SE 26 — `Thread`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html): platform/virtual, `isVirtual()` và `threadId()`.
- [Oracle JDK 26 — Virtual Threads Guide](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): thread dumps, JFR và virtual-thread operations.
- [Oracle JDK 26 — `jcmd` command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): `Thread.dump_to_file` options và `Thread.print`.
- [Oracle Java SE 26 — `VirtualThreadSchedulerMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html): JDK24+ scheduler-level monitoring, queued/mounted estimates.
- [Oracle Java SE 26 — `com.sun.management.ThreadMXBean`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): JDK-specific extension cho allocated bytes và batch CPU metrics khi available.
- [Oracle Java SE 26 — `MBeanServer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServer.html): raw JMX operations/attributes.
- [Oracle Java SE 26 — `CompositeData`](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeData.html): Open Data mapping of `ThreadInfo`.

**Kết luận:** `ThreadMXBean` là công cụ chuẩn để **theo dõi platform threads**, không phải toàn bộ virtual threads. Với platform threads, dùng counts, ThreadInfo bounded snapshots, CPU/contension capabilities và deadlock methods đúng loại lock. Với virtual workloads, bổ sung JFR, `jcmd Thread.dump_to_file` và JDK24+ scheduler MXBean. Không biến thông tin giám sát thành cơ chế điều khiển synchronization, không đo “Internet/ứng dụng có khỏe hay không” chỉ từ thread count, và không thay đổi global measurement settings trong request path.
