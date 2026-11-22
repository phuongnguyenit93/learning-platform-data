# Chẩn đoán trạng thái bị chặn thay vì suy luận từ một ảnh chụp

## 1. Vấn đề thực tế: một dòng BLOCKED chưa đủ kết luận deadlock

Khi ứng dụng Java bị chậm, nhiều công cụ có thể cho thấy một luồng ở trạng thái `BLOCKED`, `WAITING` hoặc `TIMED_WAITING`. Phản ứng vội vàng thường là kết luận “luồng bị treo”, “có deadlock” hoặc “JVM ngừng hoạt động”. Thực tế, **trạng thái của một thread tại một thời điểm chỉ là một lát cắt**. Một luồng `BLOCKED` có thể đang đợi một monitor được giữ hợp lệ vài mili giây; một luồng `WAITING` có thể đang đợi job đến từ queue hoặc latch theo thiết kế; một luồng khác ở `RUNNABLE` có thể không xử lý công việc hữu ích dù chưa bị block bởi Java monitor.

Java cung cấp `java.lang.management.ThreadMXBean` và `java.lang.management.ThreadInfo` để quan sát **platform threads**: thread state, stack trace, khóa đang chờ, owner, counters và thời gian contention khi được JVM hỗ trợ. Những API nền tảng có từ Java 5, còn những overload `getThreadInfo(ids, lockedMonitors, lockedSynchronizers)` và `dumpAllThreads(lockedMonitors, lockedSynchronizers)` dùng để lấy thông tin monitor/ownable synchronizer được bổ sung từ **Java 6**. Chúng **vẫn còn trong Java SE 26**, nhưng giới hạn phạm vi **platform threads** cần được hiểu đúng trong ứng dụng Java 21+ có **virtual threads**.

**Quy tắc cốt lõi của bài:**

> Trạng thái thread là **tín hiệu mở đầu**. Muốn chẩn đoán đúng cần ghép nhiều ảnh chụp có timestamp, lock owner, stack traces, thời gian chờ, tiến độ ứng dụng, phụ thuộc bên ngoài và phép kiểm tra deadlock trong phạm vi API hỗ trợ.

Không phải mọi BLOCKED đều là deadlock, không phải mọi WAITING đều là lỗi, và một thread dump không chứng minh hệ thống đang khỏe hay đang treo vĩnh viễn.

### Mục tiêu sau bài

1. Phân biệt `Thread.State.BLOCKED`, `WAITING`, `TIMED_WAITING`, `RUNNABLE`, `TERMINATED` theo đúng Java contracts.
2. Dùng `ManagementFactory.getThreadMXBean()`, `ThreadMXBean.getThreadInfo(...)` và `dumpAllThreads(...)` để quan sát platform threads.
3. So sánh nhiều snapshots có timestamp, giữ đúng thread IDs và diễn giải sự thay đổi thay vì suy đoán từ một ảnh.
4. Đọc `getLockInfo()`, `getLockOwnerId()`, `getLockedMonitors()` và `getLockedSynchronizers()` để hình thành bằng chứng về lock contention.
5. Phân biệt monitor `synchronized` với ownable synchronizer như `ReentrantLock`, latch/queue waiting và các chờ I/O.
6. Hiểu `getBlockedCount()`, `getBlockedTime()`, `getWaitedCount()`, `getWaitedTime()` và cách kiểm tra/bật **contention monitoring** có kiểm soát.
7. Dùng `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` để tìm **chu trình deadlock**, không coi `null` là bảo đảm ứng dụng khỏe.
8. Kết hợp metrics tiến độ, latency, traces, lock wait graph và điều kiện phát triển theo thời gian.
9. Hiểu vì sao `ThreadMXBean` **không bao gồm virtual threads**; dùng `jcmd Thread.dump_to_file` và JFR khi phù hợp.
10. Chạy hai chương trình Java 17+ đã biên dịch/chạy thật để thấy sự khác biệt giữa **BLOCKED tạm thời** và **deadlock**, cũng như giữa **counter** và **duration monitoring**.
11. Thiết kế quy trình thu thập diagnostics an toàn, có phân quyền, quota và bảo vệ dữ liệu nhạy cảm.

~~~text
        Cảnh báo request latency tăng / timeout
                       |
                       v
         Snapshot #1: thread state = BLOCKED
                       |
              KHÔNG kết luận ngay
                       |
         +-------------+---------------+
         |                             |
         v                             v
   Lock owner?                  Work progress?
   LockInfo?                    Throughput / queue?
   Stack trace?                 External dependency?
         |                             |
         +-------------+---------------+
                       |
                       v
         Snapshot #2, #3 có timestamp
                       |
        +--------------+----------------+
        |              |                |
        v              v                v
   Owner đã nhả   Owner vẫn giữ    Cycle owner/wait
   và task tiến   nhưng app vẫn    được xác nhận?
   triển?         có progress?
        |              |                |
        v              v                v
   Contention     Slow lock /        Deadlock nghiêm túc
   tạm thời       convoy           theo phạm vi phát hiện
                       |
                       v
       Xác minh root cause bằng traces/JFR/metrics
~~~

## 2. Thread.State: trạng thái Java, không phải chẩn đoán cuối cùng

`java.lang.Thread.State` chứa sáu trạng thái: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` và `TERMINATED`. Chúng mô tả góc nhìn ở tầng Java, **không đồng nghĩa hoàn toàn với trạng thái kernel scheduler hoặc mức sử dụng CPU**.

| Java state | Ý nghĩa chính | Ngộ nhận dễ gặp |
| --- | --- | --- |
| `NEW` | Thread object chưa được start | “Không có lỗi” — có thể app quên start |
| `RUNNABLE` | Thread đang thực thi hoặc sẵn sàng thực thi theo JVM | “Đang sử dụng CPU 100%” — có thể đang chờ I/O/native |
| `BLOCKED` | Chờ lấy/re-enter **intrinsic monitor** của `synchronized` | “Chắc chắn deadlock” — có thể chờ vài ms |
| `WAITING` | Chờ vô thời hạn đến khi được đánh thức/điều kiện xảy ra | “Chắc chắn treo” — queue, latch, park, join hợp lệ |
| `TIMED_WAITING` | Chờ có giới hạn thời gian, ví dụ sleep/timed wait/park | “Timeout đang lỗi” — có thể là backoff bình thường |
| `TERMINATED` | Thread đã kết thúc thực thi | “Luồng bị terminate bất thường” — có thể hoàn thành bình thường |

### 2.1. Vì sao BLOCKED gắn với synchronized?

~~~java
private final Object monitor = new Object();

void update() {
    synchronized (monitor) {
        performCriticalWork();
    }
}
~~~

Đây là **đoạn trích minh họa**; `performCriticalWork()` do ứng dụng định nghĩa. Nếu A đang giữ monitor, B cố vào cùng `synchronized` thì B có thể được JVM báo `BLOCKED`. Nhưng B có thể được chạy ngay sau khi A thoát khối. **Chỉ một snapshot khi B BLOCKED không chứng minh deadlock.**

### 2.2. Vì sao ReentrantLock thường hiện WAITING?

~~~java
ReentrantLock lock = new ReentrantLock();
lock.lock();
try {
    performCriticalWork();
} finally {
    lock.unlock();
}
~~~

Đây là đoạn trích, cần import `java.util.concurrent.locks.ReentrantLock`. Khi B cố gọi `lock.lock()` mà A đang giữ, B có thể được park qua `LockSupport.park` và xuất hiện ở `WAITING`, dù đó vẫn là **lock contention thực sự**. Vì vậy “không có thread BLOCKED” **không** đồng nghĩa “không có vấn đề khóa”.

### 2.3. Một WAITING hợp lệ

~~~java
CountDownLatch ready = new CountDownLatch(1);
ready.await(); // Chờ một thread khác gọi ready.countDown().
~~~

Đoạn trích, cần import `java.util.concurrent.CountDownLatch`. Một thread đợi latch theo thiết kế có thể ở WAITING mà không có owner theo nghĩa monitor/ownable synchronizer. Không thể từ `WAITING + lockOwnerId=-1` suy rằng có deadlock; cũng không thể từ `lockOwnerId=-1` kết luận không có phụ thuộc.

### 2.4. RUNNABLE vẫn cần bằng chứng tiến độ

Một thread có thể RUNNABLE trong busy loop, trong native blocking I/O hoặc đang được scheduler chờ CPU. Theo tài liệu `Thread.State`, state không phản ánh chi tiết OS thread scheduling. Để biết task thực sự tiến triển, dùng request completion counters, queue depth, log timestamps, tracing span durations, Java Flight Recorder hoặc CPU profiling phù hợp; tránh coi `RUNNABLE` là “đang chạy tốt”.

## 3. Lý do một ảnh chụp đơn lẻ dễ đánh lừa

Giả sử tại 10:00:00.100 hệ thống có:

~~~text
thread=checkout-worker-7
state=BLOCKED
lock=java.lang.Object@1a2b3c
owner=pricing-worker-2
stack=CheckoutService.applyDiscount(...)
~~~

Đây là **minh họa dữ liệu**, không phải stdout chương trình. Thông tin này **chưa cho biết**:
- Owner bắt đầu giữ monitor khi nào?
- Owner đang thực hiện công việc có ích hay đang đợi tài nguyên khác?
- Thread BLOCKED sẽ tiến triển sau 1 ms hay sau 30 s?
- Có bao nhiêu requests cùng gặp contention?
- Owner có nằm trong một chu trình deadlock không?
- Có vấn đề ở database/network, hoặc chỉ critical section quá lớn?
- Một snapshot thứ hai có cùng lock/owner hay khác?
- Có bao nhiêu tasks hoàn thành trong cùng khoảng thời gian?

### 3.1. Ba tình huống đều có thể tạo một ảnh BLOCKED

| Tình huống | Một snapshot nhìn thấy | Bằng chứng bổ sung để phân biệt |
| --- | --- | --- |
| Contention ngắn | B đang chờ A giữ monitor | Snapshot sau B đã chạy xong; throughput vẫn tăng |
| Lock convoy / long critical section | Nhiều threads BLOCKED cùng một owner | Nhiều snapshots cùng owner, wait durations dài, owner trong I/O/long work |
| Deadlock | A và B chờ các locks do nhau nắm giữ | Owner-wait **cycle** hoặc `findDeadlockedThreads`, không có tiến độ đến khi có can thiệp |

Từ một trạng thái quan sát giống nhau, không thể suy ra ba nguyên nhân này. Quy trình hợp lý là **thu thập evidence rồi lập giả thuyết**.

### 3.2. Chụp nhiều lần có timestamp

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
for (int i = 0; i < 3; i++) {
    long captureNano = System.nanoTime();
    ThreadInfo[] infos = bean.dumpAllThreads(false, false, 12);
    // Chỉ phân tích threads cần thiết; không in toàn bộ dump định kỳ.
    inspect(captureNano, infos);
    Thread.sleep(100);
}
~~~

**Đoạn trích**, `inspect` do ứng dụng định nghĩa. `System.nanoTime()` hữu ích cho đo **khoảng thời gian tương đối** trong một process, không thay UTC timestamp khi tương quan với nhiều services. Ba snapshots không phải “quy tắc 100 ms” cố định: chọn frequency theo SLA, latency, incident severity và overhead. Đừng lấy thread dumps hàng chục lần/giây ở production.

### 3.3. Chụp nhiều lần vẫn không đủ chứng minh deadlock

Nếu A giữ monitor 2 giây do query chậm, B có thể BLOCKED ở cả ba snapshots cách nhau 100 ms. Nhưng sau khi query xong, A nhả monitor và B tiếp tục. **Ngay cả “BLOCKED lặp lại” chỉ chứng minh contention đang kéo dài trong quan sát**, chưa chứng minh bế tắc vĩnh viễn. Cần kiểm tra cycle, tiến độ owner và dependencies.

### 3.4. Các snapshots không phải transaction toàn JVM

Các threads có thể đổi trạng thái **trong lúc JVM lấy dump**. Không coi `ThreadInfo[]` là một ảnh chụp atomic trên tất cả threads tại cùng một nanosecond; các snapshots khác nhau là những bằng chứng gần thời điểm, chịu ảnh hưởng scheduling. Một owner ID hoặc stack frame biến mất giữa hai lần gọi có thể do thread kết thúc hoặc race chứ không phải do diagnostic API sai.

## 4. Thu thập có căn cứ với ThreadMXBean

### 4.1. Lấy platform ThreadMXBean

~~~java
import java.lang.management.*;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
~~~

Đây là **đoạn trích**. `ThreadMXBean` là MXBean của JVM có thể truy vấn qua platform MBeanServer nếu ứng dụng có JMX infrastructure. Không cần bật remote JMX để chẩn đoán local process.

### 4.2. getThreadInfo theo ID để quan sát đối tượng cụ thể

~~~java
long threadId = worker.getId();
ThreadInfo thread = bean.getThreadInfo(threadId, 20);
if (thread == null) {
    // Worker đã kết thúc, không tồn tại, hoặc là virtual thread.
}
~~~

Đoạn trích, `worker` là platform Thread object cần theo dõi. Overload `getThreadInfo(long, int)` giới hạn stack depth, nhưng **không tự lấy owned-monitor và synchronizer arrays**. Để lấy ownership, dùng overload với flags.

### 4.3. Lấy stack + monitors + ownable synchronizers

~~~java
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean synchronizers = bean.isSynchronizerUsageSupported();

ThreadInfo[] selected = bean.getThreadInfo(
        new long[]{threadId}, monitors, synchronizers, 20);
~~~

Đây là **đoạn trích Java 17+**. Kiểm tra hai capability flags trước khi yêu cầu. Nếu cần quan sát toàn bộ live platform threads:

~~~java
ThreadInfo[] all = bean.dumpAllThreads(
        monitors, synchronizers, 20);
~~~

**Phân biệt:** `getThreadInfo(ids,flags,maxDepth)` chỉ truy vấn IDs yêu cầu, `dumpAllThreads(flags,maxDepth)` lấy live platform threads mà JVM quản lý. Các overload ba/bốn tham số có `maxDepth` được bổ sung sau Java 6, hiện dùng được trên Java 17/26. `maxDepth` là số stack frames tối đa **cho mỗi thread**, không giới hạn số threads.

### 4.4. Tại sao phải hỏi khả năng JVM?

Nếu `isObjectMonitorUsageSupported()==false` mà gọi `dumpAllThreads(true,false)`, hoặc `isSynchronizerUsageSupported()==false` mà gọi `dumpAllThreads(false,true)`, API có thể ném `UnsupportedOperationException`. Ghi capability trong báo cáo:
- `monitorsCollected=true/false`;
- `synchronizersCollected=true/false`;
- `unsupported` **khác** `zero locks`.

Khi flags false, mảng `getLockedMonitors()`/`getLockedSynchronizers()` rỗng theo yêu cầu dù thread có thể vẫn đang giữ khóa.

### 4.5. Không dùng getAllThreadIds để suy toàn bộ app threads

`getAllThreadIds()` chỉ trả IDs của live **platform threads**, không bao gồm virtual threads Java 21+. Khi bạn lấy IDs rồi gọi `getThreadInfo(ids, ...)`, thread có thể kết thúc giữa hai thao tác, làm một số entries null. Do đó cần xử lý null thay vì cho rằng API lỗi.

## 5. ThreadInfo: ghép owner, lock và stack

`ThreadInfo` cung cấp nhiều tín hiệu hơn mỗi state:

| Method | Diễn giải | Giới hạn |
| --- | --- | --- |
| `getThreadId()` | ID của platform thread | Chỉ trong process/lifecycle, không phải business ID |
| `getThreadName()` | Tên thread | Có thể chứa dữ liệu nhạy cảm |
| `getThreadState()` | Java state ở snapshot | Không phải verdict |
| `getStackTrace()` | Đoạn stack tại thời điểm đọc | Có thể truncated |
| `getLockInfo()` | Object lock mà thread đang chờ/park liên quan | Có thể null/owner không xác định |
| `getLockOwnerId()` | ID owner theo JVM | `-1` nếu không xác định |
| `getLockOwnerName()` | Tên owner nếu biết | Có thể null |
| `getLockedMonitors()` | Monitors **thread đang giữ** | Yêu cầu flag & capability |
| `getLockedSynchronizers()` | Ownable synchronizers **thread đang giữ** | Yêu cầu flag & capability |
| `getBlockedCount()` | Tổng số lần thread bị BLOCKED để vào monitor | Không đo tổng thời gian |
| `getBlockedTime()` | Thời gian BLOCKED tích lũy gần đúng (ms) khi enabled | `-1` khi monitoring disabled |
| `getWaitedCount()` | Tổng số lần vào WAITING/TIMED_WAITING theo JVM | Không phải số lỗi |
| `getWaitedTime()` | Thời gian WAITING/TIMED_WAITING tích lũy gần đúng (ms) | `-1` khi monitoring disabled |

### 5.1. Waiting lock khác locks đã giữ

Một thread B có thể chờ monitor M:
- `B.getLockInfo()` nói **B đang chờ M**;
- `B.getLockOwnerId()` là thread A nếu JVM xác định;
- `A.getLockedMonitors()` có thể chứa **M** khi JVM hỗ trợ và đã yêu cầu.
- `B.getLockedMonitors()` không cần chứa M, vì B chưa có lock đó.

Ngược lại, một thread giữ `ReentrantLock` có thể có `LockInfo` trong `getLockedSynchronizers()`, còn thread chờ lock đó có thể đang `WAITING` do AQS/`LockSupport.park`. Không tìm mọi lock chỉ bằng `Thread.State.BLOCKED`.

### 5.2. MonitorInfo vs LockInfo

- `MonitorInfo` cung cấp class, identityHashCode, `getLockedStackDepth()` và `getLockedStackFrame()`; nó mô tả nơi monitor đang được giữ, khi có thông tin.
- `LockInfo` cung cấp class/identityHashCode cho locks; một ownable synchronizer như `ReentrantLock` có thể xuất hiện dưới **implementation class nội bộ** chứ không phải đúng tên `ReentrantLock`.
- `identityHashCode` không phải địa chỉ memory, không đảm bảo unique toàn JVM, không phải ID bền vững giữa các snapshots/restarts. Kết hợp class name, thread owner và stack.
- Không phải mọi java.util.concurrent primitive là ownable synchronizer: `Semaphore`, `CountDownLatch`, read lock và external DB locks không có cùng owner-model.

### 5.3. Đừng tự đảo ngược owner direction

~~~text
Thread B: state=BLOCKED, awaiting M, ownerId=A
Thread A: holds monitor M

B ---> waits for M ---> held by A
~~~

Đây là quan hệ đợi đơn hướng, **chưa là deadlock**. Deadlock cần một **chu trình** (ví dụ A đợi M2 do B giữ và B đợi M1 do A giữ), hoặc phép phát hiện chuyên dụng xác nhận cycle. Một owner đang chờ external I/O 30 giây có thể tạo lock convoy nghiêm trọng dù không có cycle nội JVM.

## 6. Đánh giá thời gian và tiến độ, không chỉ đếm trạng thái

### 6.1. BlockedCount vs BlockedTime

`getBlockedCount()` là tổng **số lần vào trạng thái BLOCKED để lấy/re-enter monitor**. Nó không đo thời gian. Một thread có 1.000 lần blocked nhanh có thể tác động khác với 1 lần blocked 30 giây. Để xem thời gian, JVM có thể cung cấp `getBlockedTime()` khi **thread contention monitoring** được bật.

Quan trọng: `getBlockedTime()` nói về **BLOCKED intrinsic monitor**, không phải một bộ đo **mọi** thời gian của `ReentrantLock`, network, DB, latch. `getWaitedTime()` đo thời gian WAITING/TIMED_WAITING theo Java definitions, không thể suy trực tiếp “nhiều waitedTime = bug”.

### 6.2. Contention monitoring là optional

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
boolean supported = bean.isThreadContentionMonitoringSupported();
if (supported) {
    boolean enabled = bean.isThreadContentionMonitoringEnabled();
    // Chỉ thay đổi enabled sau khi cân nhắc overhead/ownership.
}
~~~

Đây là đoạn trích. Contention monitoring có thể **disabled mặc định**, và bật có overhead tùy JVM. Không bật/tắt global JVM setting trong một API request chỉ để trả dashboard: đó là **shared state** có thể ảnh hưởng tools khác. Ví dụ runnable mục 9 bật/tắt trong **một tiến trình test riêng** và khôi phục cấu hình ban đầu ở finally.

### 6.3. Khi disabled, -1 nghĩa là unavailable

~~~java
ThreadInfo info = bean.getThreadInfo(workerId);
long blockedMs = info == null ? -1 : info.getBlockedTime();
~~~

Đây là đoạn trích. Nếu `blockedMs==-1`, nó có thể do contention monitoring disabled; **không phải “thread bị block âm một mili giây”**. Khi có số `>=0`, đó là **số đo tích lũy gần đúng** kể từ lúc monitoring enabled/re-enabled, không phải khoảng chờ của **một lần** `BLOCKED` chắc chắn. Không trừ hai giá trị qua một lần reset/enable state mà coi là chính xác.

### 6.4. Muốn đo duration của một event, ưu tiên instrumentation rõ ràng

Khi muốn biết thời gian một business operation chờ lock, có thể đo `System.nanoTime()` trước/sau acquisition (không log secrets) hoặc dùng JFR lock contention events. Đối với high throughput, lấy histogram/percentiles và sampling thích hợp. `ThreadInfo.getBlockedTime` hữu ích cho **thread-level aggregate evidence**, không thay transaction-level tracing.

### 6.5. Quan sát task progress song song

Một thread BLOCKED trong hai snapshots nhưng các threads khác vẫn xử lý requests có thể chỉ phản ánh localized contention. Ngược lại, mọi requests không tiến triển, queue depth tăng, owner chờ I/O lâu và error rate tăng là tín hiệu incident nặng hơn.

Các metrics thường cần đối chiếu:

| Tín hiệu | Cách đọc |
| --- | --- |
| Completed requests/second | Tăng hay giảm trong khoảng quan sát |
| Queue depth và oldest task age | Có backlog tăng bền vững không |
| Request latency p95/p99 | Khách hàng có bị ảnh hưởng không |
| Lock wait/hold durations | Critical section có bất thường không |
| Thread state distribution | Bao nhiêu threads đang BLOCKED/WAITING và thời gian |
| Owner stack & external dependency | Owner đang xử lý logic hay đang đợi DB/I/O |
| CPU, GC, safepoints, thread pool saturation | Có nguyên nhân khác ngoài lock không |
| Retries và timeouts | Có tạo thêm thắt cổ chai không |

Mục tiêu không phải thu thập tất cả metrics bất kể chi phí, mà là **kiểm chứng giả thuyết**.

## 7. Java 17+ runnable: hai ảnh BLOCKED, nhưng không có deadlock

Chương trình `BlockedTimelineDemo.java` cố ý tạo một tình huống có thể **chẩn đoán sai từ một ảnh chụp**:

- `owner-holding-monitor` giữ một object monitor bằng `synchronized` và đợi latch.
- `waiting-to-enter-monitor` cố vào cùng monitor nên vào `BLOCKED`.
- `waiting-for-latch` đợi một latch **không liên quan**, thường ở `WAITING` nhưng **không có lock owner**.
- `independent-progress` vẫn tăng một counter để chứng minh JVM có việc khác tiếp tục tiến triển.
- Main đợi trạng thái ổn định, lấy **hai `dumpAllThreads(...)` snapshots** cách nhau ~90 ms.
- Hai snapshots cùng xác nhận monitor bị chặn và owner ID nhất quán; có tiến độ của independent worker.
- `findDeadlockedThreads()`/`findMonitorDeadlockedThreads()` được dùng tùy capability, kiểm tra **các test threads này không thuộc chu trình deadlock**.
- Finally nhả latches và join tất cả workers; blocked thread thực sự **kết thúc**.
- Sau khi worker đã kết thúc, `getThreadInfo(id)` là `null`.

**Bài học:** Dù thấy `BLOCKED` ở hai snapshots, kết quả thật là **contention có thời hạn**. Một snapshot đơn lẻ thậm chí không phân biệt được tình huống này với khóa bị giữ quá lâu.

### 7.1. File BlockedTimelineDemo.java

~~~java
import java.lang.management.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class BlockedTimelineDemo {
    private static final Object MONITOR = new Object();
    private static final CountDownLatch OWNER_READY = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final CountDownLatch WAITER_RELEASE = new CountDownLatch(1);
    private static final AtomicBoolean STOP_TICKS = new AtomicBoolean();
    private static final AtomicInteger TICKS = new AtomicInteger();
    private static final AtomicReference<Throwable> FAILURE = new AtomicReference<>();

    static void check(boolean condition, String reason) {
        if (!condition) throw new AssertionError(reason);
    }

    static void awaitState(Thread thread, Thread.State expected) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline && thread.getState() != expected) {
            Thread.sleep(5);
        }
        check(thread.getState() == expected,
                "Expected " + expected + " but got " + thread.getState());
    }

    static ThreadInfo find(ThreadInfo[] snapshot, long id) {
        for (ThreadInfo info : snapshot) {
            if (info != null && info.getThreadId() == id) return info;
        }
        return null;
    }

    static ThreadInfo[] take(ThreadMXBean bean) {
        return bean.dumpAllThreads(bean.isObjectMonitorUsageSupported(),
                bean.isSynchronizerUsageSupported(), 20);
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        Thread owner = new Thread(() -> {
            try {
                synchronized (MONITOR) {
                    OWNER_READY.countDown();
                    RELEASE.await();
                }
            } catch (Throwable error) {
                FAILURE.compareAndSet(null, error);
            }
        }, "owner-holding-monitor");

        Thread blocked = new Thread(() -> {
            try {
                synchronized (MONITOR) {
                    // Eventually succeeds after the owner releases MONITOR.
                }
            } catch (Throwable error) {
                FAILURE.compareAndSet(null, error);
            }
        }, "waiting-to-enter-monitor");

        Thread unrelatedWaiter = new Thread(() -> {
            try {
                WAITER_RELEASE.await();
            } catch (Throwable error) {
                FAILURE.compareAndSet(null, error);
            }
        }, "waiting-for-latch");

        Thread progressing = new Thread(() -> {
            while (!STOP_TICKS.get()) {
                TICKS.incrementAndGet();
                try { Thread.sleep(8); }
                catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }, "independent-progress");

        owner.start();
        try {
            check(OWNER_READY.await(5, TimeUnit.SECONDS), "owner not ready");
            blocked.start();
            unrelatedWaiter.start();
            progressing.start();
            awaitState(blocked, Thread.State.BLOCKED);
            awaitState(unrelatedWaiter, Thread.State.WAITING);

            ThreadInfo[] first = take(bean);
            int firstTicks = TICKS.get();
            Thread.sleep(90);
            ThreadInfo[] second = take(bean);

            ThreadInfo blockedFirst = find(first, blocked.getId());
            ThreadInfo blockedSecond = find(second, blocked.getId());
            ThreadInfo waitingSecond = find(second, unrelatedWaiter.getId());
            ThreadInfo ownerSecond = find(second, owner.getId());

            check(blockedFirst != null && blockedSecond != null
                    && waitingSecond != null && ownerSecond != null,
                    "missing platform threads");
            boolean bothBlocked = blockedFirst.getThreadState() == Thread.State.BLOCKED
                    && blockedSecond.getThreadState() == Thread.State.BLOCKED;
            boolean sameOwner = blockedFirst.getLockOwnerId() == owner.getId()
                    && blockedSecond.getLockOwnerId() == owner.getId();
            boolean sameMonitor = blockedFirst.getLockInfo() != null
                    && blockedSecond.getLockInfo() != null
                    && blockedFirst.getLockInfo().getIdentityHashCode()
                       == System.identityHashCode(MONITOR)
                    && blockedSecond.getLockInfo().getIdentityHashCode()
                       == System.identityHashCode(MONITOR);
            boolean independentProgress = TICKS.get() > firstTicks;
            boolean unrelatedWaiting = waitingSecond.getThreadState() == Thread.State.WAITING
                    && waitingSecond.getLockOwnerId() == -1;

            check(bothBlocked, "not blocked in both samples");
            check(sameOwner, "owner changes");
            check(sameMonitor, "different monitor");
            check(independentProgress, "independent worker should advance");
            check(unrelatedWaiting, "latch waiter not identified");
            long[] deadlockedIds = bean.isSynchronizerUsageSupported()
                    ? bean.findDeadlockedThreads()
                    : bean.findMonitorDeadlockedThreads();
            boolean targetInDeadlock = deadlockedIds != null
                    && Arrays.stream(deadlockedIds).anyMatch(id ->
                        id == owner.getId() || id == blocked.getId());
            check(!targetInDeadlock, "scenario should be transient contention");
            System.out.println("blocked-samples=2");
            System.out.println("blocked-owner-consistent=" + sameOwner);
            System.out.println("blocked-monitor-consistent=" + sameMonitor);
            System.out.println("independent-work-progress=" + independentProgress);
            System.out.println("unrelated-latch-waiting=" + unrelatedWaiting);
            System.out.println("scenario-deadlock-detected=" + targetInDeadlock);
        } finally {
            RELEASE.countDown();
            WAITER_RELEASE.countDown();
            STOP_TICKS.set(true);
            if (owner.isAlive()) owner.join(5000);
            if (blocked.isAlive()) blocked.join(5000);
            if (unrelatedWaiter.isAlive()) unrelatedWaiter.join(5000);
            if (progressing.isAlive()) progressing.join(5000);
            check(!owner.isAlive() && !blocked.isAlive()
                    && !unrelatedWaiter.isAlive() && !progressing.isAlive(),
                    "test threads did not finish");
        }

        check(FAILURE.get() == null, "worker failure: " + FAILURE.get());
        check(blocked.getState() == Thread.State.TERMINATED,
                "blocked thread must eventually finish");
        check(bean.getThreadInfo(blocked.getId()) == null,
                "finished thread should disappear from ThreadMXBean");
        System.out.println("blocked-after-release=TERMINATED");
        System.out.println("threadinfo-after-join-null=true");
        System.out.println("workers-finished=true");
        System.out.println("tests=PASS");
    }
}
~~~

### 7.2. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 17 BlockedTimelineDemo.java
java BlockedTimelineDemo
~~~

**Stdout chính xác** đã kiểm thử trên OpenJDK 24 với source/target Java 17:

~~~text
blocked-samples=2
blocked-owner-consistent=true
blocked-monitor-consistent=true
independent-work-progress=true
unrelated-latch-waiting=true
scenario-deadlock-detected=false
blocked-after-release=TERMINATED
threadinfo-after-join-null=true
workers-finished=true
tests=PASS
~~~

### 7.3. Giải thích từng kết luận

`blocked-samples=2` cho biết cả hai lần thu thập đều bắt gặp B trong BLOCKED. `blocked-owner-consistent=true` và `blocked-monitor-consistent=true` chứng minh cùng đối tượng monitor và cùng owner tại hai thời điểm — **chưa chứng minh bế tắc**.

`independent-work-progress=true` cho thấy một worker khác vẫn tiến triển: ứng dụng không “đóng băng tất cả”. `unrelated-latch-waiting=true` chứng minh một WAITING không có lock owner không phải lỗi tự động. `scenario-deadlock-detected=false` chỉ áp dụng cho **những IDs của fixture**, không có nghĩa các threads khác trên JVM không thể deadlock.

Cuối cùng `blocked-after-release=TERMINATED` và `threadinfo-after-join-null=true` là bằng chứng quan trọng: khi owner nhả khóa, contender hoàn thành và thread không còn trong management registry. Nếu chỉ giữ snapshot đầu, bạn sẽ không thấy đoạn kết và có thể gắn nhãn incident sai.

### 7.4. Vì sao dùng latches thay Thread.sleep cố định để giữ owner?

Một test dùng `Thread.sleep(1000)` trong synchronized có thể bị nhiễu vì scheduling, máy chạy chậm, GC hoặc flaky CI. Ở đây owner đợi `RELEASE`; main chủ động nhả trong finally nên **không tạo deadlock vĩnh viễn**. Các asserts `awaitState` và timeouts giúp xác nhận trạng thái trước khi thu thập. Đây là **fixture kiểm thử**, không phải cách thiết kế critical section cho production code.

### 7.5. Những điều không thể kết luận từ demo

- Không chứng minh ứng dụng production không có deadlock.
- Không suy tất cả Java locks từ một `getLockInfo()`.
- Không khẳng định hai snapshots đồng bộ tuyệt đối.
- Không suy một owner giữ monitor 90ms là performance bug khi SLA khác nhau.
- Không dùng progress của một independent worker để khẳng định mọi request đều healthy.
- Không tự động terminate/interrupt owner khi thấy B BLOCKED.

## 8. So sánh kiểm thử: thiếu tiến độ, chờ hợp lệ và deadlock thật

Một hệ thống production cần phân biệt **tình huống trông tương tự nhưng có nguyên nhân khác**.

### 8.1. Cùng WAITING nhưng nguồn gốc khác

| Thread stack/state | Khả năng giải thích | Bằng chứng tiếp theo |
| --- | --- | --- |
| WAITING ở `CountDownLatch.await` | Đợi event/signal hợp lệ hoặc thiếu signal | Producer task đã chạy? deadline? |
| WAITING ở `Thread.join` | Đợi thread khác kết thúc | Target thread còn làm việc hay đang bị chặn? |
| WAITING ở `LockSupport.park` | AQS lock/condition/queue wait | `getLockInfo`, owner, queue length, progress |
| TIMED_WAITING ở `Thread.sleep` | Retry backoff hoặc timer | Deadline, error rate, retry count |
| BLOCKED tại `synchronized` | Chờ intrinsic monitor | Owner stack, hold time, lock ordering |
| RUNNABLE trong loop | Busy work hoặc starvation | CPU/JFR sampling, throughput |
| RUNNABLE trong native I/O | Có thể blocked tại OS/syscall | Socket timeouts, network traces |

### 8.2. Một owner đang xử lý I/O không phải là monitor deadlock cycle

Ví dụ A giữ monitor trong khi gọi remote service chậm; B chờ monitor do A giữ. `findDeadlockedThreads()` có thể trả null vì **không có cycle giữa Java locks**, nhưng B vẫn bị ảnh hưởng nhiều giây. Root cause là **critical section chứa blocking I/O**. Cách sửa là rút ngắn critical section, bỏ network I/O ra ngoài monitor nếu consistency cho phép, dùng concurrency design phù hợp hoặc timeouts/bulkheads/circuit breakers. Không coi “deadlock detector trả null” là trạng thái OK.

### 8.3. Thread pool starvation

Nếu mọi worker threads đều đợi futures mà không còn worker chạy tasks cần thiết để hoàn tất futures, hệ thống có thể đứng dù **không có Java monitor owner-cycle**. Điều tra executor queue length, active counts, task dependencies, thread pool size và work-stealing scheduling; không suy ra hết từ một Thread.State.

### 8.4. Application-level queues và database locks

Java `ThreadMXBean` không biết owner của database row lock, distributed mutex, Redis lock, external API rate limiter hoặc network infrastructure. Nếu các threads WAITING/BLOCKED liên quan tài nguyên ngoài JVM, phải sử dụng database diagnostics, traces và service logs tương ứng. `getLockOwnerId()==-1` **không phủ định** các phụ thuộc này.

## 9. Java 17+ runnable: blocked count khác blocked time

Chương trình `ContentionMetricsDemo.java` minh họa sự khác biệt giữa:
- **`getBlockedCount()`**: số lần thread bị BLOCKED để vào monitor;
- **`getBlockedTime()`**: thời gian blocked tích lũy gần đúng **chỉ khi contention monitoring enabled**.

Trong một JVM test độc lập, chương trình:
1. Kiểm tra `isThreadContentionMonitoringSupported()`.
2. Ghi trạng thái ban đầu `isThreadContentionMonitoringEnabled()`.
3. Nếu hỗ trợ, **tạm tắt** monitoring, tạo owner giữ monitor và contender bị BLOCKED.
4. `getBlockedCount()` của contender phải dương. Với monitoring disabled, `getBlockedTime()==-1`.
5. Nếu hỗ trợ, **bật** monitoring và giữ blocked thread thêm thời gian ngắn.
6. Xác minh `getBlockedTime()>=0` khi enabled, owner ID vẫn đúng.
7. Trong finally, nhả owner, join workers và **khôi phục trạng thái monitoring ban đầu**.

**Chỉ dùng thao tác bật/tắt contention monitoring trong chương trình độc lập này.** Trong production/shared JVM, việc đổi global management setting có thể có overhead và làm nhiễu metrics của tools khác.

### 9.1. File ContentionMetricsDemo.java

~~~java
import java.lang.management.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class ContentionMetricsDemo {
    private static final Object MONITOR = new Object();
    private static final CountDownLatch HOLDING = new CountDownLatch(1);
    private static final CountDownLatch RELEASE = new CountDownLatch(1);
    private static final AtomicReference<Throwable> FAILURE = new AtomicReference<>();

    static void check(boolean okay, String reason) {
        if (!okay) throw new AssertionError(reason);
    }

    static void untilBlocked(Thread t) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline && t.getState() != Thread.State.BLOCKED) {
            Thread.sleep(5);
        }
        check(t.getState() == Thread.State.BLOCKED, "thread not blocked");
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        boolean capability = bean.isThreadContentionMonitoringSupported();
        boolean originallyEnabled = capability
                && bean.isThreadContentionMonitoringEnabled();

        Thread owner = new Thread(() -> {
            try {
                synchronized (MONITOR) {
                    HOLDING.countDown();
                    RELEASE.await();
                }
            } catch (Throwable error) {
                FAILURE.compareAndSet(null, error);
            }
        }, "monitor-owner");

        Thread contender = new Thread(() -> {
            try {
                synchronized (MONITOR) {
                    // Obtains monitor after owner leaves synchronized block.
                }
            } catch (Throwable error) {
                FAILURE.compareAndSet(null, error);
            }
        }, "blocked-contender");

        try {
            if (capability) bean.setThreadContentionMonitoringEnabled(false);
            owner.start();
            check(HOLDING.await(5, TimeUnit.SECONDS), "owner not holding");
            contender.start();
            untilBlocked(contender);
            ThreadInfo withoutTime = bean.getThreadInfo(contender.getId(), 10);
            check(withoutTime != null && withoutTime.getBlockedCount() >= 1,
                    "blocked count should be positive");
            if (capability) check(withoutTime.getBlockedTime() == -1,
                    "time must be unavailable when monitoring disabled");

            if (capability) bean.setThreadContentionMonitoringEnabled(true);
            Thread.sleep(100);
            ThreadInfo afterEnable = bean.getThreadInfo(contender.getId(), 10);
            check(afterEnable != null, "thread absent during contention");
            boolean timeAvailable = capability && afterEnable.getBlockedTime() >= 0;
            if (capability) check(timeAvailable, "timing expected when enabled");
            check(afterEnable.getThreadState() == Thread.State.BLOCKED,
                    "still held by owner");
            check(afterEnable.getLockOwnerId() == owner.getId(), "owner id");

            System.out.println("contention-supported=" + capability);
            System.out.println("blocked-count-positive=true");
            System.out.println("disabled-time-unavailable=" +
                    (!capability || withoutTime.getBlockedTime() == -1));
            System.out.println("enabled-time-available=" + timeAvailable);
            System.out.println("blocked-owner-correct=true");
        } finally {
            RELEASE.countDown();
            if (owner.isAlive()) owner.join(5000);
            if (contender.isAlive()) contender.join(5000);
            if (capability) bean.setThreadContentionMonitoringEnabled(originallyEnabled);
            check(!owner.isAlive() && !contender.isAlive(),
                    "test threads still alive");
        }

        check(FAILURE.get() == null, "worker failure: " + FAILURE.get());
        System.out.println("contention-mode-restored=true");
        System.out.println("workers-finished=true");
        System.out.println("tests=PASS");
    }
}
~~~

### 9.2. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 17 ContentionMetricsDemo.java
java ContentionMetricsDemo
~~~

**Stdout chính xác** trên OpenJDK 24 (trên đó contention monitoring supported):

~~~text
contention-supported=true
blocked-count-positive=true
disabled-time-unavailable=true
enabled-time-available=true
blocked-owner-correct=true
contention-mode-restored=true
workers-finished=true
tests=PASS
~~~

### 9.3. Vì sao blockedTime không phải một đồng hồ chính xác cho mỗi lần block?

`getBlockedTime()` là số **approximate accumulated milliseconds** mà thread ở BLOCKED **từ khi contention monitoring được bật**. JVM có thể dùng timer với độ phân giải khác nhau và reset accumulated metrics khi monitoring re-enabled. Vì vậy:
- `-1` là unavailable, không phải số thời gian âm hợp lệ;
- `0` khi enabled không nhất thiết nghĩa “không có contention”, có thể làm tròn;
- Không so sánh số trước và sau một lần disable/re-enable như một delta liên tục;
- Không hứa timing chính xác nano giây;
- Không coi blockedTime là thời gian `ReentrantLock.lock()` hoặc DB/network wait;
- Để điều tra một request, dùng event-level instrumentation/JFR/trace spans khi phù hợp.

### 9.4. Chương trình là fixture, không phải agent production

Contender chỉ chờ một monitor test, không đo business throughput. Chương trình thay đổi global contention monitoring nhưng khôi phục trong finally; trong hệ thống thực, việc bật/tắt cần ownership rõ, permission, rollout và observability cost assessment.

## 10. Kiểm tra deadlock có cơ sở

### 10.1. Deadlock đòi chu trình phụ thuộc

Một deadlock kiểu monitor điển hình:

~~~text
Thread A: giữ monitor X -> chờ monitor Y
Thread B: giữ monitor Y -> chờ monitor X

       A waits on Y (owned by B)
       B waits on X (owned by A)

       A ---> B ---> A  (cycle)
~~~

Hai threads `BLOCKED` tự nó chưa tạo cycle; cần xác nhận **ai đợi khóa nào và owner là ai**. Một owner đợi DB 30 giây có thể không tạo cycle nội JVM mà vẫn gây incident lớn.

### 10.2. Hai API deadlock detection hiện hành

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
long[] monitorCycles = bean.findMonitorDeadlockedThreads();

boolean syncUsageSupported = bean.isSynchronizerUsageSupported();
long[] allSupportedCycles = syncUsageSupported
        ? bean.findDeadlockedThreads()
        : null;
~~~

**Đoạn trích**. `findMonitorDeadlockedThreads` tìm **monitor-only cycles**. `findDeadlockedThreads` tìm **monitor + ownable synchronizer cycles** nếu JVM hỗ trợ synchronizer usage; nó có thể ném UnsupportedOperationException nếu không hỗ trợ. Nếu bạn dùng nhánh null vì unsupported, phải ghi trạng thái **"not supported"**, không coi đó là “không tìm thấy deadlock”.

### 10.3. Giới hạn của phương pháp

Cả hai methods chỉ hỗ trợ **platform threads** và các loại lock theo API. Chúng không phát hiện:
- chu trình có virtual threads;
- deadlock ở database/distributed locks;
- thread pool starvation không có monitor owner cycle;
- chờ `CountDownLatch` không ai countDown;
- network I/O treo;
- application-level state-machine/livelock.

Vì vậy `findDeadlockedThreads()==null` chỉ có nghĩa **không tìm thấy deadlock theo phạm vi detector tại thời điểm đó**, không phải “mọi thứ OK”.

### 10.4. Không thử tạo permanent deadlock trong unit test chính

Hai non-daemon threads deadlock vĩnh viễn có thể khiến CI/JVM không kết thúc. Ví dụ `BlockedTimelineDemo` đã dùng latches + finally để **mô phỏng contention rồi dọn sạch**. Nếu cần kiểm thử detector thật, chạy trong tiến trình cô lập với timeout và cơ chế tự terminate tiến trình sau kiểm thử; không tạo permanent deadlock trong service/shared test runner.

## 11. Virtual threads Java 21+: cái không có trong ThreadMXBean

Java 21 đưa **virtual threads** vào Java chính thức. Theo Javadoc Java SE 26, `ThreadMXBean` chỉ quản lý **platform threads**:

- `dumpAllThreads(...)` không liệt kê virtual threads đang sống;
- `getAllThreadIds()` không bao gồm virtual-thread IDs;
- `getThreadInfo(virtualId)` trả `null` ngay cả khi virtual thread đang sống;
- `getThreadCount()` không phải tổng số mọi platform+virtual threads;
- deadlock detection của ThreadMXBean không phát hiện cycles chứa virtual threads.

**Không dùng ThreadMXBean như duy nhất nguồn quan sát** cho application có virtual threads. Một sự cố treo do các virtual tasks có thể **vắng mặt** trong dump của ThreadMXBean.

### 11.1. jcmd Thread.dump_to_file cho cả platform và virtual threads

JDK hiện đại cung cấp:

~~~bash
jcmd <pid> Thread.dump_to_file -format=text threads.txt
jcmd <pid> Thread.dump_to_file -format=json threads.json
~~~

Đây là **lệnh minh họa**, thay `<pid>` bằng PID process được cấp quyền, file path phù hợp và chú ý output có thể lớn. Tài liệu Oracle Java SE 26 nói `Thread.dump_to_file` chứa cả platform và virtual threads, timestamps và khóa liên quan, nhưng **không tạo ảnh chụp stop-the-world nhất quán**, và **không tự chạy deadlock detection**. Điều đó khác `ThreadMXBean` về scope và semantics.

**Tránh dùng `-format=plain` nếu JDK target yêu cầu `text` theo cú pháp docs hiện hành**; theo Oracle Java SE 26 lệnh hỗ trợ `-format=text` và `-format=json`.

### 11.2. JFR: xem điều gì xảy ra qua thời gian

**Java Flight Recorder** cung cấp các events liên quan lock contention, monitor enter, thread park, CPU scheduling, virtual-thread events và nhiều yếu tố khác tùy JDK/configuration. Nó hữu ích khi muốn trả lời:
- Có bao nhiêu lần chờ monitor kéo dài quá ngưỡng?
- Những stacks nào lặp lại?
- Owner mất bao lâu, có I/O/GC liên quan?
- Vấn đề tái diễn theo traffic/time window nào?
- Trạng thái chung khác nhau giữa platform và virtual tasks ra sao?

Không bật mọi high-volume events vô giới hạn: đặt thresholds, recording duration, max age/size, access control và redaction policy.

### 11.3. Thread.print không tương đương dump_to_file

`jcmd <pid> Thread.print -l` trên HotSpot có behavior khác với `Thread.dump_to_file` về phần virtual threads (có thể hiển thị mounted virtual threads). Khi yêu cầu toàn bộ virtual threads, dùng đúng công cụ/command theo JDK đang chạy; không suy rằng mọi lệnh “thread dump” giống nhau. Cũng không tự dựa vào JVM thread count từ một exporter nếu exporter chỉ truy cập ThreadMXBean.

## 12. Quy trình chẩn đoán theo nhiều bằng chứng

Đây là workflow thực tế, không yêu cầu dừng toàn JVM hoặc thay đổi đồng bộ runtime:

### Bước 1. Xác định triệu chứng theo người dùng

Ghi nhận:
- thời điểm, service/instance/JDK version;
- endpoint/operation đang bị chậm hoặc timeout;
- mức độ ảnh hưởng: tỉ lệ requests chậm, queue depth, throughput, error rate;
- có deploy/config/GC/traffic change gần đó không.

Nếu không có ảnh hưởng thực tế, một thread đang WAITING trong idle worker pool có thể là bình thường.

### Bước 2. Lấy snapshot có kiểm soát

Dùng ThreadMXBean đối với platform threads, giới hạn `maxDepth` và output. Kiểm tra monitor/synchronizer capabilities trước. Với Java 21+ có virtual threads, nếu phải quan sát chúng thì dùng `jcmd Thread.dump_to_file`/JFR phù hợp.

### Bước 3. Lập bản đồ waiting chain

Với mỗi thread đáng ngờ:
- state tại snapshot;
- stack trace;
- lock object class/identity;
- owner ID/name nếu có;
- ownable locks và object monitors owner đang giữ;
- blocked/wait counters/time nếu hỗ trợ;
- link với business task/trace nếu an toàn.

### Bước 4. Lặp lại khi sự cố vẫn xảy ra

Thu snapshot tiếp theo có timestamp, so **cùng thread ID và lock identity/owner**. Ghi tiến độ task/owner và changes, không chỉ so số BLOCKED. Thời gian giữa snapshots phải phù hợp service latency budget và quota.

### Bước 5. Kiểm tra cycle riêng biệt

Gọi deadlock detector theo đúng capability. Nếu có cycles, đối chiếu lock ownership/stack để xác định root cause. Nếu không có, vẫn đánh giá long critical section, I/O chậm, starvation, application dependencies và virtual threads.

### Bước 6. Đánh giá nguyên nhân và sửa thiết kế

Các hướng sửa có thể là:
- rút ngắn synchronized blocks;
- không giữ Java lock qua network/database blocking I/O nếu business consistency cho phép;
- thống nhất lock acquisition ordering;
- dùng lock timeouts/cancellation và đúng finally;
- giảm shared mutable state;
- sửa thread pool starvation/Future dependencies;
- tune queue/backpressure và external service timeouts;
- quan sát bằng JFR/tracing thay vì aggressive polling.

### Bước 7. Kiểm chứng sau sửa

Không chỉ xác nhận “không có BLOCKED ở một snapshot”; cần chứng minh:
- requests hoàn tất đúng;
- throughput/latency/error rate hồi phục;
- không còn waiting chain kéo dài bất thường;
- deadlock detector không báo chu trình thuộc phạm vi đã kiểm tra;
- áp lực CPU/GC/queue/locks không tạo regression;
- logic business/concurrency vẫn đúng qua integration/stress tests.

## 13. Security và hiệu năng của diagnostic tooling

### 13.1. Thread dumps có thể tiết lộ dữ liệu nội bộ

Stack traces, thread names và lock class names có thể chứa internal package names, tenant/user IDs do app tự đặt trong thread names, stack traces, infrastructure paths. Không trả raw dumps qua public HTTP endpoint hoặc lưu vào tickets/logs không kiểm soát.

Nên có:
- authentication, admin-only authorization;
- audit trail cho diagnostic operation;
- quotas về tần suất, size, stack depth, thời hạn lưu;
- redaction/handling nhạy cảm;
- retention và xóa tệp đúng policy;
- giới hạn quyền chạy `jcmd`/JFR trên host/container.

### 13.2. Chi phí snapshot không bằng 0

Các calls `dumpAllThreads` và `findDeadlockedThreads` dành cho troubleshooting, có thể tốn tài nguyên khi process có nhiều platform threads. Một JVM chạy hàng nghìn platform threads với stack deep và lock info có thể sinh lượng dữ liệu lớn. Không bật “dump every second” chỉ vì metric hiển thị đẹp.

### 13.3. Không điều khiển synchronization từ snapshot

`ThreadInfo` có thể đã lỗi thời ngay khi trả về. Đừng dùng owner ID để gọi `Thread.stop()`/`Thread.suspend()`, tự unlock object của thread khác hay can thiệp dữ liệu theo một dự đoán từ dump. Những kỹ thuật điều khiển luồng nguy hiểm/legacy không phải giải pháp. Sửa root cause concurrency, cancellation và timeouts đúng contract.

### 13.4. Đánh dấu scope của báo cáo

Một báo cáo chuyên nghiệp nên ghi rõ:

~~~text
timestampUtc=...
jvmId=...
jdkVersion=...
captureSource=ThreadMXBean.dumpAllThreads
threadScope=platform-only
monitorUsageSupported=true/false
synchronizerUsageSupported=true/false
contentionMonitoringSupported=true/false
contentionMonitoringEnabled=true/false
maxDepth=20
sampleCount=3
sampleSpacingMs=...
deadlockDetectionScope=platform-monitor-and-ownable-only
virtualThreadsIncluded=false
dataSensitivity=admin-only
~~~

Đây là **mẫu schema**, không phải stdout Java demo. `true/false` phải được đọc từ JVM thực tế; không invent dữ liệu production. Với `jcmd Thread.dump_to_file`, đổi `captureSource/threadScope/deadlockDetectionScope` theo công cụ đó thay vì dùng metadata của ThreadMXBean.

## 14. Những lỗi chẩn đoán phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách làm tốt hơn |
| --- | --- | --- |
| Thấy một BLOCKED rồi kết luận deadlock | Contention ngắn cũng tạo BLOCKED | Nhiều snapshots, owner cycle, progress |
| Thấy WAITING rồi kết luận app treo | Idle worker/latch/queue là chờ bình thường | Traces, backlog, deadlines |
| Thấy RUNNABLE rồi kết luận có tiến độ | Có thể busy loop/native I/O | CPU/JFR và request completion |
| Chụp mỗi snapshot không timestamp | Không biết có kéo dài không | Timestamp và spacing |
| Chụp ba snapshots rồi tự kết luận deadlock | Lock hold dài không nhất thiết cycle | findDeadlockedThreads và owner chain |
| Chỉ xem blocked thread, bỏ qua owner | Không thấy nguyên nhân giữ khóa | Xem owner stack/lock set |
| Lấy getLockedMonitors của blocked thread để tìm lock đang chờ | Đó là locks thread đang giữ | Dùng getLockInfo của waiter |
| Chỉ nhìn state BLOCKED để tìm ReentrantLock contention | AQS waiter thường WAITING | Dùng LockInfo/owners + stack |
| Dựa identityHashCode như global unique ID | Không bảo đảm unique/stable | Correlate process+class+time |
| Dùng getBlockedCount như duration | Count là số lần, không phải ms | getBlockedTime nếu enabled, traces |
| Hiểu blockedTime=-1 là -1 ms | Đó là unavailable khi disabled | Đánh dấu N/A |
| Đọc getBlockedTime như ReentrantLock wait time | Chỉ monitor BLOCKED time | JFR/instrumentation cho AQS |
| Bật/tắt contention monitoring ở mỗi request | Global state, overhead, reset | Ownership/config change rõ |
| Dùng findDeadlockedThreads()==null để tuyên bố healthy | Detector không thấy DB/latch/starvation | Kết hợp nhiều nguồn |
| Gọi findDeadlockedThreads khi synchronizer unsupported | Có thể UnsupportedOperationException | Check capability và report N/A |
| Coi ThreadMXBean là tất cả threads Java 21+ | Không có virtual threads | jcmd/JFR |
| getThreadInfo(vtId)==null nên kết luận thread đã chết | Virtual thread bị loại khỏi API | Virtual-aware diagnostics |
| Dùng jcmd dump như atomic snapshot tuyệt đối | Dump mới không nhất quán stop-the-world | Timestamps + correlation |
| Bật public endpoint trả full stack | Tiết lộ cấu trúc/sensitive names | Admin-only, redaction |
| Dump liên tục không quota | Allocation/latency overhead | Triggered/rate-limited capture |
| Dùng Thread.stop để “giải deadlock” | Không an toàn/legacy | Sửa lock ordering và cancellation |
| Giữ DB/network calls bên trong synchronized | Gây lock convoy | Giảm critical section |
| Không phân biệt test fixture và production code | Latches fixture cố giữ monitor | Chỉ dùng trong test riêng |
| Thấy ownerId=-1 rồi khẳng định không có dependency | Latch/DB/owner unknown | App traces và external diagnostics |
| Trộn uptime/system clock với nanoTime | Sai elapsed-time computation | Wall timestamp + monotonic duration riêng |
| Query global platform thread count để tính virtual tasks | Virtual excluded | Tool/counters virtual-aware |

## 15. Checklist kiểm thử và điều tra

| Tình huống | Bằng chứng/kết quả kỳ vọng |
| --- | --- |
| Một monitor giữ ngắn | BLOCKED snapshot sau đó thread hoàn tất |
| Hai snapshots cùng BLOCKED | Chưa đủ kết luận deadlock |
| Owner ID ổn định | Lock relationship được correlate |
| Owner thay đổi | Re-evaluate hypothesis, không dùng dữ liệu cũ |
| Independent task progress | JVM không bị dừng hoàn toàn |
| Latch waiter WAITING | Không có monitor owner bắt buộc |
| ReentrantLock waiter WAITING | Có thể là AQS contention |
| Blocking DB I/O trong owner | Không nhất thiết JVM deadlock |
| Queue depth tăng + throughput giảm | Dấu hiệu tác động tới app |
| Monitor-only cycle | findMonitorDeadlockedThreads phát hiện nếu có |
| Monitor + ownable cycle | findDeadlockedThreads nếu support |
| Thread pool starvation | Có thể không có monitor deadlock |
| External/distributed locks | Cần DB/distributed diagnostics |
| Thread finish giữa samples | getThreadInfo(id) có thể null |
| getBlockedCount | Số lần blocked, không phải duration |
| Contention monitoring disabled | getBlockedTime==-1 |
| Contention monitoring enabled | getBlockedTime>=0 (approximate) |
| Contention monitoring unsupported | Báo unsupported, không bật |
| isObjectMonitorUsageSupported false | Không request lockedMonitors=true |
| isSynchronizerUsageSupported false | Không request lockedSynchronizers=true |
| maxDepth=20 | ≤20 frames/thread, không giới hạn số threads |
| Java 21+ virtual thread live | Không nằm trong ThreadMXBean dump |
| Virtual-aware dump | jcmd Thread.dump_to_file hỗ trợ |
| JFR recording | Thresholds/retention/permissions phù hợp |
| Redaction/authorization | Không lộ stack/thread names nhạy cảm |
| Rate limit | Không làm diagnostics gây incident mới |
| Sau khi sửa code | Request latency/throughput hồi phục |
| Cleanup tests | Latches release, threads joined, settings restored |
| JDK upgrade | Revalidate semantics và tool formats |

### 15.1. Test không có deadlock cũng cần hoàn tất

Trong `BlockedTimelineDemo`, việc **chủ động release lock và join** là bằng chứng điều kiện test kết thúc, khác với assert `findDeadlockedThreads()==null` ở một thời điểm. Không thể lấy bài test demo này làm bằng chứng business app sẽ không deadlock; nhưng nó là ví dụ thực nghiệm cho thấy state snapshot không đủ.

### 15.2. Tần suất thu thập phải phù hợp sự cố

Một request bình thường cần milliseconds có thể dùng vài observations cách nhau 50–100 ms trong bài lab, nhưng production có SLA, JVM size và chi phí khác. **Không mặc định chụp 3 lần × 100ms cho mọi request**; thay vào đó dùng incident trigger, cooldown/rate limit và metrics có chi phí thấp. Nếu vấn đề xảy ra rất nhanh, ưu tiên event-based profiling/JFR hơn dump polling liên tục.

## 16. Câu hỏi tự đánh giá

**1.** Một thread `BLOCKED` có chắc là deadlock không?

**Đáp án:** Không. Nó đang chờ intrinsic monitor; có thể được giải phóng ngay sau đó.

**2.** Hai snapshots đều `BLOCKED` có chứng minh deadlock không?

**Đáp án:** Không. Chúng cho thấy contention kéo dài qua khoảng quan sát, nhưng vẫn cần owner cycle/progress/root cause.

**3.** Một thread `WAITING` có chắc là lỗi không?

**Đáp án:** Không. Chờ latch, queue, join hoặc `LockSupport.park` có thể đúng thiết kế.

**4.** `RUNNABLE` có nghĩa thread đang tiêu thụ CPU 100% không?

**Đáp án:** Không. Java state không tương đương OS CPU sampling.

**5.** `getLockInfo()` khác `getLockedMonitors()`?

**Đáp án:** getLockInfo mô tả lock thread đang chờ; getLockedMonitors mô tả monitors thread đang giữ.

**6.** `getLockOwnerId()==-1` nghĩa gì?

**Đáp án:** Owner không được xác định/không có owner theo API ở snapshot; không khẳng định mọi dependency đều vắng mặt.

**7.** `getBlockedCount()` có đo thời gian chờ không?

**Đáp án:** Không, đó là số lần BLOCKED khi lấy monitor.

**8.** `getBlockedTime()==-1` có phải một giá trị thời gian hợp lệ không?

**Đáp án:** Không, đó là unavailable khi contention monitoring disabled.

**9.** `getBlockedTime()` có đo thời gian `ReentrantLock.lock()` không?

**Đáp án:** Không trực tiếp; nó đo monitor BLOCKED time. Dùng JFR/tracing cho AQS/other waits.

**10.** Vì sao cần timestamp ở mỗi snapshot?

**Đáp án:** Để có thể so khoảng thời gian, sự thay đổi, không trộn owner/state của những thời điểm khác nhau.

**11.** `findMonitorDeadlockedThreads` và `findDeadlockedThreads` khác thế nào?

**Đáp án:** Phương thức đầu tìm monitor-only cycles; phương thức sau mở rộng monitor+ownable synchronizer cycles nếu JVM hỗ trợ.

**12.** Nếu detector không tìm thấy deadlock, application có chắc khỏe không?

**Đáp án:** Không. Có thể có starvation, database waits, virtual-thread issues và long critical sections.

**13.** ThreadMXBean có liệt kê virtual threads Java 21+ không?

**Đáp án:** Không; nó chỉ quản lý platform threads.

**14.** Công cụ nào có thể dump cả virtual threads?

**Đáp án:** `jcmd <pid> Thread.dump_to_file -format=json <file>` hoặc `-format=text` trên JDK hỗ trợ.

**15.** jcmd Thread.dump_to_file là snapshot atomic tuyệt đối không?

**Đáp án:** Không. Tài liệu nêu không dừng toàn VM, có timestamps và không tự deadlock detection.

**16.** Có nên chụp toàn bộ stack mỗi 10ms trên production không?

**Đáp án:** Không. Đó có thể là overhead lớn và rủi ro lộ dữ liệu; dùng triggered captures/rate limits.

**17.** Vì sao bài demo có independent progress thread?

**Đáp án:** Để chứng minh có work vẫn tiến triển trong khi một contender BLOCKED; không suy từ một thread rằng cả JVM đã freeze.

**18.** Vì sao bài demo có separate latch waiter?

**Đáp án:** Để thấy `WAITING` là một trạng thái hợp lệ và owner-independent, không tự đồng nghĩa deadlock.

**19.** Vì sao metrics contention monitoring không nên bật/tắt trong mỗi request?

**Đáp án:** Đây là JVM-global state, có overhead và reset counters/time semantics; cần kiểm soát ở mức ops/config.

**20.** Sau sửa lỗi, xác minh điều gì ngoài thread states?

**Đáp án:** Throughput, latency, error rate, queue progress, owner dependencies, regression/stress tests và diagnostics phù hợp.

### Bài tập thực hành

1. Biên dịch/chạy `BlockedTimelineDemo.java`; giải thích hai snapshots đều BLOCKED nhưng sau release thread TERMINATED.
2. Đổi khoảng cách giữa hai snapshots từ 90ms thành 200ms, thảo luận vì sao thời gian không tự chứng minh deadlock.
3. In `getLockOwnerName()`, `getLockInfo()` và `getStackTrace()` của blocked thread trong lab, phân biệt owner và waiter.
4. Thử `dumpAllThreads(false,false,5)`, xác nhận không có owned-monitor arrays dù lock đang được giữ.
5. Dùng `getThreadInfo(new long[]{ownerId,blockedId}, flags, 20)` thay dump toàn JVM khi chỉ quan tâm hai IDs.
6. Bỏ `RELEASE.countDown()` trong **một process test cô lập có timeout**, quan sát vì sao test có thể không kết thúc; không chạy trên shared build process.
7. Thêm một task độc lập tăng business counter và so với `TICKS` heartbeat.
8. Thử `ReentrantLock` waiter và quan sát WAITING/LockInfo, so sánh intrinsic monitor BLOCKED.
9. Thử `CountDownLatch.await` cùng một timed wait, giải thích state/timeouts.
10. Chạy `ContentionMetricsDemo`, xác nhận disabled blocked time -1 và enabled nonnegative trên JVM hỗ trợ.
11. Đổi code để khôi phục contention monitoring trong finally ngay cả khi assertion fail; xác minh ownership.
12. Ghi rõ blockedCount là số lần, không phải duration, trong một dashboard mock.
13. Thiết kế app tracing để đo owner giữ monitor bao lâu, không dùng thread snapshots làm timer.
14. Test `findMonitorDeadlockedThreads`/`findDeadlockedThreads` trong process cô lập với timeout.
15. Trên Java 21+, tạo một virtual thread rồi xem `getThreadInfo(virtualId)==null` dù nó đang sống.
16. Dùng `jcmd <pid> Thread.dump_to_file -format=json <file>` (đúng permission) và so với ThreadMXBean platform-only.
17. Dùng JFR để lấy contention events qua một khoảng thời gian trong local benchmark.
18. So sánh tiến độ requests/queue depth khi owner giữ lock 50ms và 500ms.
19. Tạo runbook điều tra service treo: symptom → samples → owner chain → progress → deadlock check → fix → regression tests.
20. Thiết kế admin-only diagnostic endpoint có maxDepth, rate limit, redaction, TTL và audit.
21. Viết test khi `getThreadInfo` trả null giữa hai snapshots vì thread đã terminate.
22. Viết thử phân biệt một task WAITING trên latch và một request waiting database query bằng application traces.
23. Kiểm tra một giá trị `getBlockedTime()==0` khi monitoring enabled, giải thích rounding/measurement semantics.
24. Đảm bảo tool dùng virtual-aware diagnostics khi service chuyển sang virtual-thread-per-task executor.

## 17. Tài liệu chính thức vẫn áp dụng

- [Oracle Java SE 26 — ThreadMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform-thread scope, getThreadInfo/dumpAllThreads, capability flags, contention monitoring và deadlock detection.
- [Oracle Java SE 26 — ThreadInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadInfo.html): state, lock owner, blocked/wait counters/time semantics.
- [Oracle Java SE 26 — Thread.State](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.State.html): NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING, TERMINATED.
- [Oracle Java SE 26 — Thread](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html): platform/virtual threads, IDs và lifecycle.
- [Oracle Java SE 26 — ManagementFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html): lấy ThreadMXBean hiện tại.
- [Oracle Java SE 26 — LockInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/LockInfo.html): locked/waiting object identity.
- [Oracle Java SE 26 — MonitorInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MonitorInfo.html): monitor ownership và locked stack frame.
- [Oracle Java SE 26 — ReentrantLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): ownable synchronizer behavior.
- [Oracle Java SE 26 — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html): waiting fixtures.
- [Oracle Java SE 26 — LockSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): park/unpark và WAITING.
- [Oracle Java SE 26 — ThreadMXBean deadlock contract](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html#findDeadlockedThreads()): cycle detection limits.
- [Oracle Java SE 26 — jcmd](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): Thread.dump_to_file, Thread.print.
- [Oracle Java SE 26 — Virtual Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): virtual-thread scope, virtual-aware dumps.
- [Oracle Java SE 26 — Java Flight Recorder API](https://docs.oracle.com/en/java/javase/26/jfapi/): event-based diagnostics.
- [Oracle Java SE 26 — Monitoring and Management Using JMX](https://docs.oracle.com/en/java/javase/26/management/): management/diagnostics infrastructure.
- [Oracle Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform-only MXBean in virtual-thread era.
- [Oracle Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): API available cho Java17 runnable examples.
- [Oracle Java SE 17 — ThreadInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): getter semantics và lock-owner information.

**Ghi nhớ:** Một `BLOCKED` chỉ là dữ liệu trạng thái tại thời điểm lấy snapshot, **không đủ kết luận deadlock**. Hãy thu nhiều observations, so lock owner/identity/stacks, đo latency/progress và dùng deadlock detector đúng phạm vi; hiểu `getBlockedCount` khác `getBlockedTime` và time `-1` là unavailable. Java ThreadMXBean chỉ quản lý **platform threads**; ứng dụng có virtual threads phải dùng thêm **jcmd/JFR**. Bằng chứng mạnh nhất là **điều gì thay đổi theo thời gian và root cause nào khiến công việc không tiến triển**, không phải một nhãn Thread.State đứng riêng.
