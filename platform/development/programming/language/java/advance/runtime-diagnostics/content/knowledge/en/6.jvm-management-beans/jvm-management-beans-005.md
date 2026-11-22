# 6.5 ThreadMXBean cho số platform thread, CPU time, contention và phát hiện deadlock

## Mục tiêu học tập

Khi Java service có throughput giảm, CPU cao, số thread tăng dần hoặc request chờ rất lâu, các phép đo ở mức process chưa đủ để biết **luồng nào đang chạy**, **luồng nào đang chờ khóa** và **có chu trình deadlock trong JVM hay không**. `java.lang.management.ThreadMXBean` là một API chuẩn để quan sát hệ thống thread trong JVM, hỗ trợ lập số liệu định lượng và lấy snapshot phục vụ chẩn đoán.

Sau bài học, bạn có thể:

- Lấy `ThreadMXBean` từ `ManagementFactory` và phân biệt **live, peak, total started, daemon thread count**.
- Đọc CPU time ở mức thread theo nanosecond, kiểm tra `isThreadCpuTimeSupported()` / `isThreadCpuTimeEnabled()` và tính **chênh lệch giữa hai thời điểm** thay vì nhầm số tích lũy là CPU%.
- Hiểu `ThreadInfo`, `getBlockedCount()`, `getBlockedTime()`, `getWaitedCount()`, `getWaitedTime()` và phạm vi của contention monitoring.
- Phân biệt `findMonitorDeadlockedThreads()` với `findDeadlockedThreads()`; biết cách lấy lock owner, stack trace và giới hạn của việc phát hiện deadlock.
- Dùng **Java 17+ chạy được** cho cả snapshot thông thường và một lab monitor deadlock an toàn trong tiến trình thử nghiệm.
- Viết kết luận chẩn đoán có timestamp, workload, cờ hỗ trợ đo, phạm vi platform threads và các yếu tố gây nhiễu.

## 1. ThreadMXBean là gì và “platform thread” nghĩa là gì?

`ThreadMXBean` thuộc module `java.management`, package `java.lang.management`. JVM cung cấp một instance cho hệ thống quản lý thread, thường truy cập bằng:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
```

Đây là đoạn minh họa cần đặt trong phương thức/class có các import tương ứng; không phải một chương trình độc lập. Một cách khác là truy vấn qua JMX với ObjectName **`java.lang:type=Threading`**.

**Phạm vi theo phiên bản:**

- **Java 17:** Java SE 17 chưa có virtual threads thành tính năng chính thức của nền tảng. Các thread bạn tạo bằng `new Thread(...)` là **platform threads** (các thread do JVM và OS quản lý theo mô hình thread nền tảng). Những con số `ThreadMXBean` phản ánh hệ thống thread này.
- **Java 21 trở lên:** Java có **virtual threads**, nhưng `java.lang.management.ThreadMXBean` là công cụ quản lý/giám sát **platform threads**, không phải bộ đếm và profiler toàn diện cho từng virtual thread. Không dùng `getThreadCount()` để suy tổng số virtual threads. Các thread thực thi/carrier cần được phân biệt với virtual tasks đang được multiplex trên chúng.

Bởi vậy trong bài này, “thread count” có nghĩa **số platform threads đang sống trong JVM tại thời điểm đo**, không phải request đang xử lý, số task trong queue, CPU cores, Java virtual threads hoặc tổng số kernel threads trên cả node.

Đối với một dịch vụ được triển khai trong container, cũng cần phân biệt **process/JVM scope** với các metric `pids.current` của cgroup, thread count trong OS và số thread của sidecar/tiến trình khác.

### 1.1 Tại sao API này quan trọng với runtime diagnostics?

`ThreadMXBean` trả lời bốn câu hỏi khác nhau:

| Câu hỏi | Nhóm API | Tín hiệu có được |
| --- | --- | --- |
| JVM có bao nhiêu platform thread? | `getThreadCount()`, `getPeakThreadCount()`, `getTotalStartedThreadCount()`, `getDaemonThreadCount()` | Quy mô thread, đỉnh lịch sử, churn, daemon ratio |
| Thread nào tiêu thụ CPU? | `getThreadCpuTime(id)`, `getThreadUserTime(id)` | CPU nanoseconds tích lũy theo từng thread |
| Thread bị block/wait ở đâu? | `getThreadInfo(...)`, `ThreadInfo`, contention counters/times | State, stack, monitor/lock owner, sự kiện/time chờ |
| Có chu trình chờ khóa trong JVM? | `findMonitorDeadlockedThreads()`, `findDeadlockedThreads()` | Các thread ID thuộc deadlock được JVM phát hiện |

Đây là một **nguồn chứng cứ**, không phải cơ chế tự động sửa lỗi hay đồng bộ luồng. Khi thực thi dưới tải, phải kết hợp số đo với logs, request traces, queue depth, CPU process/container, GC và thời gian chờ dependency.

## 2. Các bộ đếm số lượng platform thread

### 2.1 Bốn phép đo dễ nhầm

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();

int live = mx.getThreadCount();
int peak = mx.getPeakThreadCount();
long started = mx.getTotalStartedThreadCount();
int daemon = mx.getDaemonThreadCount();
```

**Ý nghĩa chính xác:**

- **`getThreadCount()`:** số thread *đang sống* ở thời điểm đọc, bao gồm daemon và non-daemon.
- **`getPeakThreadCount()`:** mức *cao nhất của live thread count* kể từ lúc JVM bắt đầu hoặc từ lần gọi `resetPeakThreadCount()` gần nhất. Nó không phải số thread tối đa cấu hình cho ứng dụng.
- **`getTotalStartedThreadCount()`:** tổng số thread đã được tạo **và bắt đầu chạy** kể từ lúc JVM khởi động. Đây là **counter tích lũy**, thông thường không giảm khi thread kết thúc.
- **`getDaemonThreadCount()`:** số daemon threads còn sống tại thời điểm đo; không phải số background jobs hay số thread “không quan trọng”.

Ví dụ giả định:

```text
time=T1: live=80, peak=120, totalStarted=1200, daemon=43
time=T2: live=82, peak=135, totalStarted=1650, daemon=44
```

Trong khoảng T1–T2, số thread sống chỉ tăng 2 nhưng tổng số đã khởi động tăng **450**. Điều này có thể cho thấy vòng đời thread churn lớn (tạo/hủy liên tục). Chưa thể tự kết luận là memory leak hay pool sai cấu hình: ứng dụng có thể xử lý nhiều công việc ngắn bằng thread riêng hoặc có chính sách thread factory đặc biệt.

**Lưu ý phạm vi counter:**

- `peak` phụ thuộc thời điểm reset; `resetPeakThreadCount()` **thay đổi mốc chẩn đoán toàn JVM**, không phải thao tác chỉ đọc. Không tự reset khi đang điều tra để “làm biểu đồ đẹp”.
- `started` tích lũy từ lúc JVM start, không so trực tiếp giữa hai process có uptime khác nhau. Nên tính delta và quy đổi số thread được khởi động/giây theo cùng cửa sổ.
- Cùng một thread pool cố định 50 worker có thể có 50 platform threads sống nhưng hàng nghìn queued tasks; **thread count không đo queue length hoặc số user**.
- Một lần đọc không phải snapshot nguyên tử của mọi counter. `live`, `peak`, `started` có thể đổi giữa các lời gọi nếu chương trình đang tạo/hủy thread.

### 2.2 Công thức theo cửa sổ

Với hai mẫu tại T1/T2:

```text
deltaStarted = totalStarted(T2) - totalStarted(T1)
threadStartRatePerSecond = deltaStarted / elapsedSeconds
liveChange = live(T2) - live(T1)
```

Ví dụ từ số liệu trên trong 30 giây: `deltaStarted=450`, tương đương **15 thread starts/giây**. Đây là tín hiệu churn, không phải chắc chắn có 15 thread mới còn sống sau mỗi giây.

Cần gắn run ID, thời gian và workload. Nếu throughput tăng gấp 10, thread start rate tăng có thể hợp lý; nếu workload giữ nguyên nhưng rate ngày càng tăng và latency/GC xấu, cần điều tra thread factory/executor lifecycles.

## 3. Lấy danh sách thread và thông tin hiện tại

```java
long[] ids = mx.getAllThreadIds();
ThreadInfo[] infos = mx.getThreadInfo(ids, 20);
```

- `getAllThreadIds()` trả các ID của thread đang sống vào thời điểm lấy danh sách. Khi sau đó gọi `getThreadInfo`, một số thread có thể đã kết thúc.
- `getThreadInfo(ids, 20)` lấy thông tin và stack trace tối đa **20 frame** trên mỗi thread; phần tử ứng với ID đã chết có thể là `null`. Giới hạn độ sâu giúp hạn chế output.
- `getThreadInfo(id)` **không** tự lấy stack trace: đây tương đương `getThreadInfo(id, 0)`.
- `dumpAllThreads(lockedMonitors, lockedSynchronizers)` cung cấp snapshot rộng hơn; các option lấy lock info và stack traces có thể tốn chi phí đáng kể khi số thread lớn.

Những trường có ích của `ThreadInfo`:

| API | Diễn giải |
| --- | --- |
| `getThreadId()`, `getThreadName()` | Nhận diện thread trong lần quan sát |
| `getThreadState()` | Một trạng thái như `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` |
| `getStackTrace()` | Call path tại thời điểm chụp (có thể rỗng/thiếu frame) |
| `getLockInfo()`, `getLockName()` | Khóa/đối tượng mà thread đang chờ, nếu có |
| `getLockOwnerId()`, `getLockOwnerName()` | Owner của khóa đang chờ, nếu JVM có thể xác định |
| `getLockedMonitors()`, `getLockedSynchronizers()` | Những khóa đã nắm giữ khi yêu cầu thu thông tin tương ứng và JVM hỗ trợ |

**Thread ID** là số dương `long`. Trong Java 17 có thể lấy ID của một `Thread` bằng `Thread.getId()`. ID duy nhất trong vòng đời thread nhưng **có thể được sử dụng lại sau khi thread kết thúc**; đừng dùng ID không có timestamp/process identity như khóa nghiệp vụ tồn tại vĩnh viễn.

### 3.1 Thread state không cho biết ngay nguyên nhân

- **`RUNNABLE`:** có thể đang thực thi hoặc đang sẵn sàng chờ CPU theo ngữ nghĩa của JVM; không tự chứng minh thread đang tiêu thụ CPU cao.
- **`BLOCKED`:** thường chờ giành **object monitor** để vào `synchronized`; hữu ích khi nghi monitor contention.
- **`WAITING`:** chờ không giới hạn tại các cơ chế như `Object.wait()`, `Thread.join()` hoặc `LockSupport.park()`.
- **`TIMED_WAITING`:** tương tự nhưng có thời hạn (sleep, timed wait, park...).
- **`TERMINATED`:** một thread đã kết thúc sẽ không còn được liệt kê trong tập live; `getThreadInfo(id)` có thể trả `null`.

Một worker pool có nhiều `WAITING` vì đang đợi task là trạng thái **bình thường**, không phải deadlock. Một thread `BLOCKED` tại một thời điểm cũng có thể chỉ là contention ngắn; cần nhiều mẫu/counters/latency để định lượng.

## 4. Đọc CPU time theo thread

### 4.1 CPU time khác wall-clock time

`getThreadCpuTime(long id)` trả tổng thời gian CPU mà thread đã tiêu thụ (user + system mode nếu JVM phân biệt), đơn vị **nanoseconds**. Đây là **CPU time tích lũy**, không phải độ dài tồn tại của thread, elapsed time của request hoặc phần trăm CPU tại một thời điểm.

`getThreadUserTime(id)` chỉ đo CPU time ở user mode theo phạm vi implementation; không lấy `getThreadCpuTime - getThreadUserTime` làm một profiler kernel chính xác nếu chưa hiểu hỗ trợ/độ chính xác của JVM/OS.

**Ví dụ cùng một thread:**

```text
Wall sample T1: 0.0 s, thread CPU time = 5.100 s
Wall sample T2: 0.2 s, thread CPU time = 5.150 s
deltaCpu = 0.050 s; deltaWall = 0.200 s
CPU share trên cơ sở một logical CPU = 0.050/0.200*100 = 25.0%
```

Tỷ lệ 25% ở đây là **mức sử dụng tương đương 0,25 logical CPU trong cửa sổ** của một thread. Nó không phải “25% CPU của toàn máy 16 core” và không đo được thời gian thread bị block/chờ I/O. Tổng tỷ lệ của nhiều thread có thể vượt 100% khi chúng thực sự chạy song song trên nhiều CPU logic.

Khi so container CPU limit khác host CPU count, cần giữ rõ **mẫu số**: một core, quota của container hay tổng node. CPU time đo được không trực tiếp cho biết thread bị throttling bao lâu.

### 4.2 Luôn kiểm tra hỗ trợ và trạng thái bật

Trước khi đo thread bất kỳ:

```java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();

if (mx.isThreadCpuTimeSupported() && mx.isThreadCpuTimeEnabled()) {
    long cpuNanos = mx.getThreadCpuTime(threadId);
    if (cpuNanos >= 0) {
        // Có CPU-time sample hợp lệ cho thread đang sống.
    }
}
```

Đây là **mã minh họa tích hợp**, với `threadId` là ID dương của thread thực; cần import `ManagementFactory` và `ThreadMXBean`.

Các trường hợp cần xét:

- `isThreadCpuTimeSupported() == false`: JVM không hỗ trợ đo CPU time của thread bất kỳ, không gọi `getThreadCpuTime` như thể chắc chắn có số.
- `isThreadCpuTimeEnabled() == false`: hỗ trợ có thể tồn tại nhưng đo đang tắt; `getThreadCpuTime(id)` thường trả `-1`.
- `getThreadCpuTime(id) == -1`: có thể vì thread đã chết/không tồn tại hoặc vì đo đang tắt; **không phải 0 nanoseconds**.
- `isCurrentThreadCpuTimeSupported()`: khả năng đo current thread riêng; không mặc định cả hai khả năng hỗ trợ là giống nhau trên mọi VM.
- Kích hoạt `setThreadCpuTimeEnabled(true)` là thay đổi cấu hình đo trên JVM và có thể tốn tài nguyên; chỉ thực hiện khi có quyền, mục đích và chiến lược khôi phục. Không lén bật trên production để có metric đẹp hơn.

Javadoc Java 17 nói độ phân giải ở **nanoseconds**, nhưng **không đảm bảo độ chính xác nanoseconds**. CPU-time một thread là **counter tích lũy trong vòng đời được đo**; nếu bật đo sau khi thread đã chạy, mốc thời gian bắt đầu accounting có thể phụ thuộc VM. Khi tính delta phải dùng **cùng thread ID, cùng process, cùng trạng thái đo và một khoảng thời gian xác định**.

### 4.3 Tìm top CPU threads đúng cách

Quy trình có giá trị hơn một lần sort CPU time:

1. Tại T1 lấy `getAllThreadIds()`, rồi CPU time của các ID sống.
2. Tại T2 lấy ID/counter lần nữa sau cửa sổ cố định, ví dụ 10 giây; tính `deltaCpuNs` với các thread tồn tại ở cả hai mẫu.
3. Chỉ giữ delta **không âm**, bỏ `-1`/thread chết; kiểm tra thread ID có thể tái sử dụng nếu khoảng đo dài hoặc thread churn rất cao.
4. Xếp hạng **CPU delta**, không xếp theo tổng CPU time từ lúc JVM khởi động.
5. Với thread nghi vấn, thu `ThreadInfo`/stack/JFR CPU samples để biết **đoạn code nào** đang tốn CPU.

Một thread đã chạy 10 giờ có thể có tổng CPU time cao nhưng đang ngủ ở hiện tại. Ngược lại, một thread mới chạy vòng lặp vô hạn có tổng CPU time thấp song **delta** cực cao trong 10 giây gần nhất.

## 5. Contention: blocked count/time và waited count/time

### 5.1 “Blocked” khác “waited”

`ThreadInfo` cung cấp:

- `getBlockedCount()`: số lần thread bị block để vào/re-enter **monitor**.
- `getBlockedTime()`: thời gian **tích lũy xấp xỉ**, tính bằng **milliseconds**, thread bị block để vào monitor kể từ khi contention monitoring được bật thích hợp.
- `getWaitedCount()`: số lần thread ở trạng thái chờ thông báo theo semantics của API.
- `getWaitedTime()`: thời gian tích lũy xấp xỉ, tính bằng milliseconds, thread chờ notification/ở trạng thái waiting tương ứng kể từ khi contention monitoring được bật.

Chúng không phải “tổng thời gian chờ tất cả loại I/O”, cũng không thay thế trace đo latency request. `BLOCKED` do chờ `synchronized` khác `WAITING` do `Object.wait`, `Thread.join`, park hay chờ task. Trường `getBlockedTime` không đo mọi loại `ReentrantLock`/database/network wait dưới một nhãn chung.

### 5.2 Phải biết trạng thái bật contention monitoring

```java
if (mx.isThreadContentionMonitoringSupported()) {
    boolean enabled = mx.isThreadContentionMonitoringEnabled();
    ThreadInfo info = mx.getThreadInfo(threadId);
    if (info != null) {
        long blockedCount = info.getBlockedCount();
        long blockedMs = info.getBlockedTime();
        long waitedCount = info.getWaitedCount();
        long waitedMs = info.getWaitedTime();
        // Nếu enabled == false, blockedMs/waitedMs có thể là -1.
    }
}
```

Đây là đoạn minh họa tích hợp. Trong Java 17, contention monitoring **mặc định tắt** theo tài liệu; hãy đọc trạng thái thực tế thay vì đoán. Khi monitoring tắt, `getBlockedTime()` và `getWaitedTime()` trả `-1`, trong khi count có ngữ nghĩa khác; **không thay -1 bằng 0** vì mất phân biệt “không đo” và “đo được không có thời gian chờ”.

Bật/tắt bằng:

```java
mx.setThreadContentionMonitoringEnabled(true);
```

Lệnh này **thay đổi trạng thái quan sát của JVM**, cần quyền quản trị, chỉ khi `isThreadContentionMonitoringSupported()` là true; có thể gây overhead. Khi re-enable, thống kê thời gian liên quan có thể được reset, nên không so sánh raw counter qua mốc bật/tắt như cùng một chuỗi liên tục. Trong production nên dùng chính sách cấu hình/giám sát đã thống nhất và ghi timestamp của thời điểm bật.

### 5.3 Diễn giải đúng bằng delta

Ví dụ hoàn toàn **giả định** về một platform thread ở cùng JVM:

| Chỉ số | T1 | T2 | Chênh lệch |
| --- | ---: | ---: | ---: |
| Blocked count | 20 | 24 | +4 lần |
| Blocked time (ms) | 110 | 118 | +8 ms |
| Waited count | 7 | 8 | +1 lần |
| Waited time (ms) | 80 | 100 | +20 ms |

Tại T1–T2, nếu đo hợp lệ và chưa reset, có thể nói thread thêm **4 lần blocked** và tích lũy thêm khoảng **8 ms blocked time**. Không thể kết luận “đợi khóa trung bình 2 ms cho mọi transaction” vì đấy là số đo trên một thread và một khoảng ngắn, chưa chắc đại diện cho toàn workload.

Với một thread có `blockedCount` tăng nhưng `blockedTime` thấp, có thể có nhiều contention rất ngắn. Với `blockedTime` tăng mạnh, cần xem owner, stack và các thay đổi về số request/tải trong cùng cửa sổ.

### 5.4 Vì sao một snapshot chưa giải quyết được contention?

`ThreadInfo` mô tả một thời điểm. Nếu thấy 30 workers cùng `BLOCKED` đợi một monitor, cần điều tra:

- Lock nào bị tranh chấp? `getLockInfo`/`getLockName`.
- Thread nào đang giữ? `getLockOwnerId`/`getLockOwnerName`.
- Owner đang chạy ở đâu? Lấy `ThreadInfo`/stack của owner.
- Có xảy ra mỗi lần peak traffic hay ngẫu nhiên? So sánh nhiều mẫu, blocked deltas và p95/p99/throughput.
- Lock có giữ khi I/O hoặc xử lý dài? Cần trace/call path, không sửa code chỉ dựa trên state.

Các thread `WAITING` trong idle executor thường hoàn toàn bình thường. Nếu một dependency chậm, các worker có thể `WAITING`/park mà không có **monitor deadlock**. Đừng đánh đồng mọi sự chờ với lỗi đồng bộ.

## 6. Phát hiện deadlock: hai API không giống nhau

### 6.1 Deadlock là gì?

Deadlock trên khóa thường xảy ra khi có **chu trình chờ**:

```text
Thread A giữ monitor M1, đang chờ M2
Thread B giữ monitor M2, đang chờ M1
              A ----waits-for----> B
              ^                    |
              |-----waits-for------|
```

Khi cả hai giữ khóa và chờ khóa còn lại, chúng không tự tiến được nếu không có can thiệp khác. `ThreadMXBean` có thể phát hiện một số chu trình chờ khóa tại thời điểm kiểm tra.

### 6.2 So sánh `findMonitorDeadlockedThreads` và `findDeadlockedThreads`

| Method | Phạm vi | Return | Lưu ý |
| --- | --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Chu trình chờ khi giành **object monitor** (khóa dùng bởi `synchronized`) | `long[]` các ID hoặc `null` khi không tìm thấy | Không bao gồm mọi loại ownable synchronizer |
| `findDeadlockedThreads()` | Chu trình liên quan **object monitor và ownable synchronizer** như một số `java.util.concurrent.locks` | `long[]` hoặc `null` | Có thể ném `UnsupportedOperationException` nếu VM không hỗ trợ quan sát ownable synchronizers |

Nên kiểm tra `isSynchronizerUsageSupported()` trước khi dùng cách phát hiện rộng hơn. Nếu tính năng không được hỗ trợ, có thể dùng phương án monitor-only nhưng phải **ghi giới hạn phạm vi**. Không biến `null` thành “không tồn tại bất cứ deadlock nào”; kết quả chỉ là **không phát hiện chu trình thuộc loại hỗ trợ vào đúng thời điểm đó**.

Các API deadlock detection là dành cho troubleshooting và **có thể tốn chi phí** khi số thread/lock lớn. Không gọi liên tục ở tần suất cao trên JVM đang quá tải.

### 6.3 Lấy bằng chứng cụ thể sau khi phát hiện

Với các ID trả về:

```java
long[] deadlocked = mx.findMonitorDeadlockedThreads();
if (deadlocked != null) {
    ThreadInfo[] infos = mx.getThreadInfo(deadlocked, 32);
    for (ThreadInfo info : infos) {
        if (info != null) {
            System.out.println(info.getThreadName()
                    + " waitingFor=" + info.getLockName()
                    + " owner=" + info.getLockOwnerName());
        }
    }
}
```

Đây là đoạn minh họa tích hợp, stdout phụ thuộc JVM. Khi có sự cố thực, cần lưu thêm stack trace, lock owner ID, danh sách locks đang giữ và timestamp, đồng thời xác minh object monitors/ownable synchronizers có được hỗ trợ khi yêu cầu lock details.

`findDeadlockedThreads()` **không** phát hiện mọi tình huống “ứng dụng treo”:

- Thread A chờ database, thread B chờ network mà dependency ngoài JVM không đáp ứng.
- Task trong pool chờ `Future.get()` của task khác nhưng không có chu trình object monitor/ownable synchronizer được JVM nhận diện.
- Starvation do thread pool đã kín hoặc lock ở tiến trình khác.
- Live lock, I/O không có deadline, deadlock phân tán giữa nhiều service.
- Deadlock xảy ra rồi biến mất trước lần chụp.

Với các ca đó, phải điều tra queue, thread stacks, traces, lịch tác vụ, deadline và hệ thống phụ thuộc. “Không tìm thấy monitor deadlock” không đồng nghĩa “đường request không bị tắc nghẽn”.

## 7. Java 17+: một chương trình gồm dữ liệu cố định, snapshot và deadlock lab

Bài demo dưới đây có **ba chế độ rõ ràng**:

- **`fixture`**: tính delta từ các số giả định, cho stdout **chính xác và độc lập môi trường**.
- **`snapshot`**: quan sát `ThreadMXBean` của JVM đang chạy với feature checks, **không bật/tắt** CPU/contention monitoring; output thay đổi theo OS/JDK/trạng thái.
- **`deadlock`**: trên **một JVM lab mới**, tạo hai daemon platform threads cố tình deadlock bằng `synchronized`, rồi dùng `findMonitorDeadlockedThreads()` tìm chúng. Không chạy chế độ này trong service thật; daemon threads còn deadlock cho tới khi JVM lab kết thúc.

Tạo tệp **`ThreadMxBeanLab.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class ThreadMxBeanLab {
    private static final ThreadMXBean MX =
            ManagementFactory.getThreadMXBean();

    static void fixture() {
        long cpuBeforeNs = 5_100_000_000L;
        long cpuAfterNs = 5_150_000_000L;
        long elapsedNs = 200_000_000L;

        double share = 100.0 *
                (cpuAfterNs - cpuBeforeNs) / elapsedNs;

        long blockedBefore = 20;
        long blockedAfter = 24;
        long blockedMsBefore = 110;
        long blockedMsAfter = 118;

        System.out.println("live=80 peak=120 started=1200 (fixture)");
        System.out.printf(java.util.Locale.ROOT,
                "cpuDeltaMs=50 wallMs=200 cpuShare=%.1f%%%n", share);
        System.out.printf(java.util.Locale.ROOT,
                "blockedCountDelta=%d blockedTimeDeltaMs=%d%n",
                blockedAfter - blockedBefore,
                blockedMsAfter - blockedMsBefore);
        System.out.println("deadlockResult=null means not detected");
    }

    static void snapshot() {
        System.out.println("live=" + MX.getThreadCount());
        System.out.println("peak=" + MX.getPeakThreadCount());
        System.out.println("started=" + MX.getTotalStartedThreadCount());
        System.out.println("daemon=" + MX.getDaemonThreadCount());

        boolean cpuSupport = MX.isThreadCpuTimeSupported();
        System.out.println("cpuSupported=" + cpuSupport);
        if (cpuSupport) {
            boolean enabled = MX.isThreadCpuTimeEnabled();
            System.out.println("cpuEnabled=" + enabled);
            if (enabled) {
                long id = Thread.currentThread().getId();
                System.out.println("currentThreadCpuNs="
                        + MX.getThreadCpuTime(id));
            }
        }

        boolean contention =
                MX.isThreadContentionMonitoringSupported();
        System.out.println("contentionSupported=" + contention);
        if (contention) {
            System.out.println("contentionEnabled="
                    + MX.isThreadContentionMonitoringEnabled());
        }

        long[] ids = MX.getAllThreadIds();
        Arrays.sort(ids);
        int shown = 0;
        for (long id : ids) {
            ThreadInfo info = MX.getThreadInfo(id, 3);
            if (info == null) {
                continue; // Thread ended between the two reads.
            }
            System.out.println("thread=" + info.getThreadName()
                    + " state=" + info.getThreadState());
            if (++shown == 5) {
                break;
            }
        }

        long[] monitorDeadlocks = MX.findMonitorDeadlockedThreads();
        System.out.println("monitorDeadlockDetected="
                + (monitorDeadlocks != null));
    }

    static void lockInOrder(Object first, Object second,
            CountDownLatch ready, CountDownLatch proceed) {
        synchronized (first) {
            ready.countDown();
            try {
                proceed.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            synchronized (second) {
                // Two threads hold opposite first locks in this lab.
            }
        }
    }

    static void deadlockLab() throws InterruptedException {
        Object first = new Object();
        Object second = new Object();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch proceed = new CountDownLatch(1);

        Thread a = new Thread(
                () -> lockInOrder(first, second, ready, proceed),
                "lab-deadlock-A");
        Thread b = new Thread(
                () -> lockInOrder(second, first, ready, proceed),
                "lab-deadlock-B");

        a.setDaemon(true);
        b.setDaemon(true);
        a.start();
        b.start();

        if (!ready.await(5, TimeUnit.SECONDS)) {
            System.out.println("lab=not-ready");
            return;
        }
        proceed.countDown();

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            long[] ids = MX.findMonitorDeadlockedThreads();
            if (ids != null) {
                boolean foundA = Arrays.stream(ids)
                        .anyMatch(id -> id == a.getId());
                boolean foundB = Arrays.stream(ids)
                        .anyMatch(id -> id == b.getId());
                if (foundA && foundB) {
                    System.out.println(
                            "monitorDeadlock=lab-deadlock-A,lab-deadlock-B");
                    ThreadInfo[] info = MX.getThreadInfo(
                            new long[] {a.getId(), b.getId()}, 5);
                    for (ThreadInfo t : info) {
                        if (t != null) {
                            System.out.println(t.getThreadName()
                                    + " state=" + t.getThreadState());
                        }
                    }
                    return;
                }
            }
            Thread.sleep(20);
        }
        System.out.println("monitorDeadlock=not-detected-in-time");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java ThreadMxBeanLab fixture|snapshot|deadlock");
            return;
        }
        switch (args[0]) {
            case "fixture" -> fixture();
            case "snapshot" -> snapshot();
            case "deadlock" -> deadlockLab();
            default -> System.out.println("Unknown mode");
        }
    }
}
```

Biên dịch bằng **JDK 17 trở lên**:

```bash
javac ThreadMxBeanLab.java
java ThreadMxBeanLab fixture
```

Stdout **chính xác** của `fixture`:

```text
live=80 peak=120 started=1200 (fixture)
cpuDeltaMs=50 wallMs=200 cpuShare=25.0%
blockedCountDelta=4 blockedTimeDeltaMs=8
deadlockResult=null means not detected
```

Cách tính: `(5_150_000_000 - 5_100_000_000) ns = 50 ms`, `200_000_000 ns = 200 ms`, vì thế `cpuShare = 50/200 * 100 = 25.0%`. `blockedCount` tăng 4, `blockedTime` tăng 8 ms. Đây là **bộ số liệu giả định**, không phải thống kê thu từ chương trình Java đang thực thi.

Chạy **snapshot thực**:

```bash
java ThreadMxBeanLab snapshot
```

Lệnh này in các bộ đếm hiện tại, tính năng CPU/contention có được hỗ trợ/bật hay không, một số thread và tình trạng phát hiện monitor deadlock. **Không có stdout cố định**: số thread, thời gian CPU, tên thread, ID và cờ tính năng khác nhau theo VM/OS/thời điểm; `cpuSupported=false` không tự động là lỗi.

Thực hành **deadlock chỉ trong JVM lab**:

```bash
java ThreadMxBeanLab deadlock
```

Trong JVM hỗ trợ phát hiện monitor deadlock và lên lịch các threads bình thường, output dự kiến khi vòng chờ đã hình thành:

```text
monitorDeadlock=lab-deadlock-A,lab-deadlock-B
lab-deadlock-A state=BLOCKED
lab-deadlock-B state=BLOCKED
```

Chế độ này **cố tình tạo deadlock**, hai thread được đánh dấu `daemon` để không giữ process lab sống mãi sau khi `main` kết thúc. Trên máy quá tải hoặc implementation không phát hiện kịp thời, có thể in `lab=not-ready` hoặc `monitorDeadlock=not-detected-in-time`. Không nhận các trường hợp đó là bằng chứng “không có deadlock” trong ứng dụng nói chung. Không đưa đoạn tạo deadlock vào production hoặc unit test chạy chung JVM dài hạn.

**Điểm QA code:**

- `getThreadId()` của `ThreadInfo` và `getId()` của `Thread` là API có trên Java 17.
- Cơ chế `CountDownLatch` bảo đảm cả hai luồng đã giữ monitor đầu tiên trước khi cho phép chúng tìm monitor thứ hai, tạo chu trình chờ đối xứng.
- `Arrays.sort(ids)` giúp một phần thứ tự snapshot ổn định nhưng không bảo đảm danh sách thread cố định.
- Demo `snapshot` chỉ **đọc** trạng thái monitoring, không gọi setter thay đổi khả năng đo trên JVM.
- Trong `deadlock`, các thread daemon có thể vẫn blocked khi chương trình kết thúc; đó là tính chất cố ý của lab, **không** phải hướng thiết kế ứng dụng.

## 8. Đọc dữ liệu trong chẩn đoán Java thật

### 8.1 CPU cao nhưng throughput không tăng

**Triệu chứng:** process CPU cao, p99 tăng, throughput đứng yên.

Thu dữ liệu:

1. Ghi offered/received/completed RPS, request mix, GC, CPU quota/throttling và timestamp.
2. Lấy per-thread CPU time ở hai thời điểm, tính **CPU delta** trong cùng cửa sổ.
3. Tìm top threads; lấy stack/JFR CPU profile để xem call path; đối chiếu threads làm việc chính và GC/JIT threads.
4. Tìm trường hợp busy-spin, serialization nặng, polling chặt, retry loop hoặc lock contention; không gán nguyên nhân chỉ từ tên thread.

Một thread mang tên `worker-4` có CPU delta cao chưa chứng minh task/endpoint nào gây CPU, vì pool có thể chạy nhiều task trên cùng thread. Cần trace/task ID, sampling và workload correlation.

### 8.2 Số thread tăng liên tục

**Triệu chứng:** `live` tăng cùng RSS/native memory hoặc xuất hiện lỗi tạo thread.

Thu:

- `getThreadCount`, `getPeakThreadCount`, `getTotalStartedThreadCount` theo thời gian.
- Số task đang chờ, pool size/active count, số worker theo tên, thread creation rate, socket/file descriptor usage.
- Thread dumps/stack của các thread tương tự để xem nơi chúng chờ.
- Giới hạn container PID/memory/OS và thread stack size nếu liên quan.

**Kết luận có thể:** live tăng và started tăng là dấu hiệu thread tích lũy; chưa đủ để nói “leak”. Các thread có thể sống hợp lệ theo yêu cầu tải; cần xác nhận những thread nào **đáng lẽ đã kết thúc** mà vẫn bị giữ.

Nếu `started` tăng nhanh nhưng live ổn định, dấu hiệu phù hợp hơn với **churn**, có thể gây overhead tạo/hủy thread, chứ không nhất thiết leak.

### 8.3 Thread contention khiến request chậm

**Triệu chứng:** nhiều request chậm ở một đoạn `synchronized`.

Thu:

- Mẫu `getThreadInfo` tại các mốc T1/T2; xem `BLOCKED`, `getLockOwnerName`, stack frame của owner.
- Blocked count/time deltas khi contention monitoring thực sự bật.
- CPU delta để biết owner đang tính toán hay cũng bị tắc ở nguồn khác.
- Request latency, throughput, tải và lock hold time nếu instrument được.

**Kết luận thận trọng:** tăng blocked time cùng lock owner phù hợp giả thuyết monitor contention. Không tuyên bố đã xác nhận nguyên nhân khi chưa chứng minh lock nằm trên đường xử lý chậm và khi chưa loại trừ dependency/GC/scheduling effects.

### 8.4 Service treo và nghi deadlock

**Quy trình an toàn:**

1. Thu stack trace/thread dump và metrics trước khi thay đổi trạng thái.
2. Gọi phát hiện monitor deadlock; nếu hỗ trợ synchronizer, cân nhắc phát hiện loại rộng hơn.
3. Với ID thu được, lấy thread names, lock owner, lock/monitor info, call paths và timestamp.
4. Kiểm tra đây có phải **chu trình chờ tương hỗ** hay chỉ nhiều threads cùng chờ một worker chậm.
5. Lưu evidence, phân tích lock ordering và hồi quy; không “sửa” bằng cách gọi setter monitoring hoặc reset counter.

**Từ chối kết luận quá mạnh:** cả hai API trả `null` không chứng minh hệ thống không deadlock ở network, DB hoặc ở thời điểm khác.

## 9. Truy cập qua JMX và công cụ chẩn đoán

Vì `ThreadMXBean` là platform MXBean, bạn có thể dùng local code hoặc các công cụ JMX thích hợp như JConsole/VisualVM/JMX client để xem `java.lang:type=Threading`. Trong môi trường server:

- Mọi thao tác từ xa cần thiết lập xác thực, TLS và kiểm soát truy cập phù hợp; không mở JMX remote công khai chỉ để xem vài chỉ số.
- API và operation thay đổi trạng thái như `setThreadCpuTimeEnabled`, `setThreadContentionMonitoringEnabled`, `resetPeakThreadCount` cần được quản lý riêng, không để dashboard tự ý gọi.
- Thread dump/deadlock detection có thể tốn CPU, bộ nhớ và pause; không polling quá dày.
- Thread names, stack traces, class/method names hoặc request-related context có thể là thông tin hệ thống nhạy cảm; phân quyền và giới hạn retention.
- Trong container hoặc cluster, xác nhận kết nối/agent đang nhắm đúng JVM instance, không vô tình đo JVM sidecar hay process vừa restart.

Nếu không thể gắn agent JMX, có thể thu bằng code instrumentation hoặc `jcmd Thread.print`/JFR theo chính sách vận hành; mỗi lựa chọn có phạm vi và chi phí riêng. Không giả định mọi công cụ trả chính xác cùng một tập thread tại cùng một thời điểm.

## 10. Hiệu năng, tác dụng phụ và hạn chế đo lường

### 10.1 Những phép đo có thể làm thay đổi điều kiện quan sát

| Thao tác | Nhóm ảnh hưởng | Thực hành |
| --- | --- | --- |
| `getThreadCount()`, `getPeakThreadCount()` | Quan sát nhẹ tương đối | Chấp nhận biến thiên giữa hai lời gọi |
| `getThreadCpuTime(id)` | Đọc counter CPU | Kiểm tra enabled/supported; tránh polling rất dày |
| `setThreadCpuTimeEnabled(true)` | **Thay đổi trạng thái theo dõi** | Phải có quyền và kế hoạch; có overhead |
| `setThreadContentionMonitoringEnabled(true)` | **Thay đổi trạng thái theo dõi** | Ghi lúc bật, tác động tới mốc thống kê |
| `getThreadInfo(ids, depth)` | Snapshot stack/lock | Giới hạn số ID và depth nếu có thể |
| `dumpAllThreads(...)` | Thu toàn bộ thread stack/locks | Có thể nặng với JVM nhiều thread |
| `findDeadlockedThreads()` | Phân tích quan hệ chờ khóa | Không gọi dày, hiểu capability và null result |
| `resetPeakThreadCount()` | **Thay đổi lịch sử peak** | Không reset khi đang cần đối chiếu lịch sử |

Việc lấy `ThreadInfo` hoặc deadlock detection có thể làm nhiễu wall-clock/CPU của hệ thống đang tải cao. Gắn timestamp cho chính thời điểm chụp, đo khoảng thời gian thực thi lệnh và theo dõi symptom trước/sau thao tác.

### 10.2 Cách hiểu `-1`, `null` và `false`

- CPU time `-1`: thread chết/không tồn tại hoặc đo disabled; có thể là trạng thái không hợp lệ để tính delta.
- Blocked/waited time `-1`: contention monitoring bị tắt, **không** có nghĩa thread chưa từng đợi.
- `ThreadInfo == null`: thread không còn sống tại lần đọc hoặc ID không tồn tại.
- `long[] deadlocks == null`: không phát hiện chu trình khóa thuộc phạm vi của method **tại lần kiểm tra đó**.
- `is…Supported() == false`: tính năng không có trên VM/implementation hiện tại, không phải bug của ứng dụng.

Đừng dùng `Math.max(0, value)` để “làm sạch” mọi số âm trước khi báo cáo: biến `-1` thành `0` sẽ làm dashboard báo **sai** rằng CPU wait/blocked time bằng không.

### 10.3 Giới hạn khác cần ghi

- **Sampling bias:** chụp một lần có thể bỏ sót luồng bận trong vài millisecond.
- **Thread churn:** ID từ T1 có thể đã chết trước T2; delta per-thread không còn ý nghĩa.
- **Container CPU quota:** CPU-time và utilization phải được đặt cạnh throttle/cgroup metrics.
- **Framework task scheduling:** một worker phục vụ nhiều task; CPU-time thread không thể quy trực tiếp thành một request.
- **JVM khác nhau:** hỗ trợ CPU/contention monitoring, overhead và thời điểm đo có thể khác implementation.
- **Phiên bản Java:** kết quả `getThreadCount` không đo lượng virtual threads trên JDK mới.
- **Thời gian tích lũy:** restart JVM hoặc reset peak/bật monitoring làm thay đổi ý nghĩa counter.
- **Deadlock scope:** chỉ nhận diện lock cycle thuộc loại hỗ trợ; không phát hiện mọi deadlock logic/phân tán.

## 11. Mẫu báo cáo chẩn đoán ThreadMXBean

```text
RUN CONTEXT
- Service/build, JVM vendor/version, container/pod/PID:
- Workload: offered/received/completed RPS, concurrency, request mix:
- Start/end time, timezone, sampling interval, run IDs:

THREAD COUNTS
- live, peak, totalStarted, daemon per sample:
- deltaStarted / thread-start rate:
- pool size/queue depth/active workers correlation:

CPU
- isThreadCpuTimeSupported / isThreadCpuTimeEnabled:
- IDs, names, deltaCpuNs, deltaWallNs, per-core-equivalent share:
- stack/JFR evidence for top CPU threads:
- container quota/throttling and process CPU:

CONTENTION
- isThreadContentionMonitoringSupported / Enabled:
- start/stop time of any monitoring configuration change:
- blocked/waited counts and times (per thread, per window):
- lock owner, stack/frame evidence, state distribution:

DEADLOCK
- findMonitorDeadlockedThreads: IDs/null/unsupported context:
- findDeadlockedThreads: IDs/null/unsupported context:
- lock cycle, ThreadInfo/stack, timestamp:
- external waits not covered by MXBean:

CONCLUSION
- Confirmed observation:
- Hypotheses supported and alternative explanations:
- Limitations (sampling, duration, thread churn, JDK, workload):
- Risk, remediation owner, verification steps:
```

Đây là mẫu **cấu trúc**, không phải báo cáo đã có số đo thực. Nếu dùng trong production, thêm link tới metrics/log/trace/JFR, lưu đúng quyền truy cập, không phát tán nội dung stack nhạy cảm.

## 12. Những nhầm lẫn phổ biến

1. **Dùng `getThreadCount()` như số request hoặc task đang xử lý.** Worker thread thường được tái sử dụng; queue cần đo riêng.
2. **Xem `getTotalStartedThreadCount()` là số thread đang sống.** Đây là tổng đã khởi động từ lúc JVM start.
3. **Thấy peak cao rồi nói hiện đang thiếu thread.** Peak là lịch sử, có thể được reset; phải xem live và nhu cầu hiện tại.
4. **Lấy tổng CPU time để xếp top CPU tại hiện tại.** Cần delta trong cùng cửa sổ.
5. **Quên `isThreadCpuTimeSupported`/Enabled.** `-1` không phải thời gian CPU bằng 0.
6. **Lấy CPU share của một thread chia cho số core và gọi CPU của toàn container mà không ghi mẫu số.** Các định nghĩa CPU% có thể khác nhau.
7. **Bật contention monitoring mà không ghi thời điểm/tác động.** Có overhead và có thể reset số liệu thời gian.
8. **Đồng nhất `BLOCKED` và `WAITING`.** Chờ intrinsic monitor khác chờ notification/park/I/O.
9. **Coi `getBlockedTime=-1` là không có contention.** Đây thường là dấu hiệu không đo thời gian.
10. **Gọi `findMonitorDeadlockedThreads` rồi tuyên bố không có deadlock với `ReentrantLock`.** Method monitor-only có phạm vi hẹp hơn.
11. **Gọi `findDeadlockedThreads` không kiểm tra ownable synchronizer support.** Có thể `UnsupportedOperationException`.
12. **Coi `null` deadlock result là “ứng dụng không thể treo”.** Có thể là pool starvation hoặc external wait.
13. **Chỉ lấy một thread dump.** State là snapshot; cần nhiều mẫu/metrics để chẩn đoán hiện tượng theo thời gian.
14. **Quên ID có thể tái sử dụng.** Gắn process identity, timestamp và name/stack.
15. **Chụp full stacks liên tục trên JVM quá tải.** Công cụ chẩn đoán có thể làm tăng độ trễ.
16. **Không phân biệt platform và virtual threads.** Kết quả ThreadMXBean của JDK mới không phản ánh tổng số virtual tasks.
17. **Nhầm CPU-time với latency.** Thread chờ I/O nhiều có thể tiêu thụ CPU thấp nhưng làm request chậm.
18. **Dùng ThreadMXBean làm cơ chế đồng bộ.** Nó phục vụ giám sát, không bảo đảm snapshot nguyên tử hoặc thứ tự khóa để điều khiển logic nghiệp vụ.

## 13. Câu hỏi tự kiểm tra

1. `getThreadCount()`, `getPeakThreadCount()` và `getTotalStartedThreadCount()` khác nhau ở điểm nào? Khi nào tổng started tăng nhanh nhưng live không tăng?
2. CPU time tăng 50 ms trong cửa sổ 200 ms thì mức sử dụng tương đương một logical CPU là bao nhiêu phần trăm? Có đồng nghĩa 25% CPU của một node 32 core không?
3. Điều kiện nào khiến `getThreadCpuTime(id)` trả `-1`? Vì sao không được thay `-1` bằng 0?
4. Bạn gọi `getThreadInfo(ids, 20)` sau `getAllThreadIds()` và gặp phần tử `null`. Đây có phải lỗi JVM không?
5. Vì sao `getBlockedCount()` và `getBlockedTime()` không cùng đơn vị? Các giá trị này có đo mọi loại chờ database/network không?
6. `isThreadContentionMonitoringSupported()` trả true nhưng `getBlockedTime()=-1`. Những kiểm tra tiếp theo là gì?
7. Sự khác nhau về lock types giữa `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` là gì? Trường hợp nào cần kiểm tra ownable synchronizer support?
8. Hai worker đều `WAITING` trong thread dump. Điều đó đã đủ chứng minh deadlock chưa? Bạn sẽ kiểm tra lock owner/queue/stack ra sao?
9. Trong Java 21+, `ThreadMXBean.getThreadCount()` có thể được dùng làm số virtual threads đang chạy không? Cần những công cụ/số đo gì khác?
10. Một service có p99 tăng trong khi per-thread CPU time thấp. Những giả thuyết về I/O, GC, lock, thread pool starvation hoặc throttling cần được xem xét?
11. Những operation nào trong `ThreadMXBean` **thay đổi trạng thái đo** thay vì chỉ đọc? Bạn phải ghi gì trong timeline?
12. Nếu `findDeadlockedThreads()` trả `null` một lần, kết luận mạnh nhất có thể nói là gì?

## Nguồn tham khảo

- Oracle Java SE 17 — ThreadMXBean: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java SE 17 — ThreadInfo: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- Oracle Java SE 21 — ThreadMXBean (làm rõ phạm vi platform threads trên JVM có virtual threads): https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html

**Ghi nhớ:** `ThreadMXBean` đo **số platform threads, CPU time tích lũy, contention và các chu trình deadlock thuộc loại khóa được hỗ trợ**. Muốn chẩn đoán chính xác, phải đọc khả năng hỗ trợ, phân biệt metric tích lũy với delta, so số liệu trong cùng workload/cửa sổ, và không biến `null` hoặc `-1` thành kết luận “không có lỗi”.