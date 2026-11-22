# getLockedMonitors, getLockedSynchronizers và stack tương ứng: phân tích khóa luồng Java hiện đại

## 1. Mục tiêu: ai đang giữ khóa, bị chặn ở đâu và stack nói điều gì?

Khi điều tra một ứng dụng Java chậm, đơ hoặc nghi bị deadlock, câu hỏi quan trọng không chỉ là một luồng đang ở trạng thái `RUNNABLE`, `WAITING` hay `BLOCKED`. Người vận hành còn cần xác định:

- **Luồng đang sở hữu những object monitors nào?** Ví dụ monitor của `synchronized (lock)` hoặc một method `synchronized`.
- **Luồng đang sở hữu những ownable synchronizers nào?** Ví dụ `ReentrantLock` hoặc write lock của `ReentrantReadWriteLock`.
- **Vị trí stack tương ứng với nơi monitor được chiếm là gì?**
- **Luồng đang chờ một khóa khác hay đang giữ khóa?** Hai điều này hoàn toàn khác nhau.
- **Luồng nào sở hữu khóa đang gây tắc nghẽn?** Có thể theo `getLockOwnerId()`, `getLockOwnerName()` và `getLockInfo()` trong trường hợp phù hợp.
- **Kết quả thread dump có phải snapshot nhất quán và đầy đủ không?** Không thể giả định mọi luồng, đặc biệt virtual threads, đều có mặt trong `ThreadMXBean`.

Java SE 17+ vẫn hỗ trợ các API trong `java.lang.management`:

- `ThreadMXBean` lấy **snapshot** các platform threads.
- `ThreadInfo.getLockedMonitors()` trả `MonitorInfo[]` cho monitors **đang được sở hữu**.
- `ThreadInfo.getLockedSynchronizers()` trả `LockInfo[]` cho **ownable synchronizers đang được sở hữu**.
- `ThreadInfo.getStackTrace()` cho stack tương ứng **thời điểm chụp**.
- `MonitorInfo.getLockedStackDepth()/getLockedStackFrame()` liên hệ **monitor cụ thể** tới vị trí nhận monitor trong stack.
- `ThreadInfo.getLockInfo()/getLockOwnerId()` chỉ về đối tượng luồng đang **đợi** và chủ sở hữu nếu có thể xác định.

**Khác biệt trọng tâm của bài:** `MonitorInfo` có **locked stack depth/frame**; `LockInfo` trong mảng `getLockedSynchronizers()` **không có field stack frame lúc chiếm khóa**. Có thể dùng stack của thread để suy luận chỗ dùng `ReentrantLock`, nhưng không được nói `getLockedSynchronizers()` tự trả chính xác dòng `lock()`.

Các lớp thuộc **module `java.management`**, vẫn đang được hỗ trợ ở **Java SE 25**. Bài dùng mã chạy **Java 21+** (một phiên bản LTS hiện đại) vì chọn API `Thread.threadId()` thay cho `Thread.getId()` đã deprecated từ Java 19. `ThreadMXBean`, `ThreadInfo`, `MonitorInfo` và `LockInfo` cũng có trên Java 17; riêng việc dùng `Thread.ofPlatform`/`threadId` trong ví dụ yêu cầu Java 21+.

## 2. Đặt đúng ranh giới giữa monitor, synchronizer và stack

~~~text
Platform thread "lock-owner-demo"
  |
  +-- EXCLUSIVE.lock()       (ReentrantLock / ownable synchronizer)
  |       |
  |       +-- synchronized (MONITOR)   (object monitor)
  |               |
  |               +-- CountDownLatch.await()
  |                       |
  |                       +-- Thread.State = WAITING
  |
  +-- ThreadMXBean.getThreadInfo(ids, true, true)
            |
            +-- ThreadInfo.getLockedMonitors()
            |      +-- MonitorInfo(identity of MONITOR)
            |             +-- getLockedStackDepth()
            |             +-- getLockedStackFrame() -> holdBoth(...)
            |
            +-- ThreadInfo.getLockedSynchronizers()
            |      +-- LockInfo(ReentrantLock internal synchronizer)
            |             +-- className, identityHashCode
            |             +-- KHÔNG có getLockedStackFrame()
            |
            +-- ThreadInfo.getStackTrace()
                   +-- current stack, including holdBoth(...)
~~~

Cùng lúc, một platform thread thứ hai có thể đang cố vào `synchronized(MONITOR)`:

~~~text
Thread "lock-contender-demo"
    |
    +-- state = BLOCKED
    +-- ThreadInfo.getLockInfo() -> MONITOR it tries to acquire
    +-- ThreadInfo.getLockOwnerId() -> lock-owner-demo threadId
    +-- getLockedMonitors() -> KHÔNG chứa MONITOR vì chưa chiếm được
~~~

**Một thread ở trạng thái WAITING vẫn có thể giữ khóa.** Trong minh họa, chủ sở hữu đang đợi `CountDownLatch.await()` và **không nhả** Java monitor bao ngoài; thread khác sẽ `BLOCKED` khi cố vào monitor đó. Ngược lại, `Object.wait()` trên đúng monitor sẽ nhả monitor ấy trong thời gian chờ — không gộp hai tình huống này.

### Ba loại thông tin cần tách rời

| Câu hỏi | API | Ý nghĩa |
| --- | --- | --- |
| Luồng *đang giữ* monitor nào? | `getLockedMonitors()` | Danh sách monitor đã được lock bởi thread |
| Luồng *đang giữ* ownable synchronizer nào? | `getLockedSynchronizers()` | Danh sách ownable synchronizers, không phải tất cả java.util.concurrent structures |
| Monitor được chiếm tại frame nào? | `MonitorInfo.getLockedStackFrame()` và `getLockedStackDepth()` | Vị trí liên quan tới stack snapshot |
| Luồng *đang đợi* đối tượng nào? | `ThreadInfo.getLockInfo()` | Lock/blocker của trạng thái bị chặn hoặc waiting |
| Ai sở hữu lock mà luồng đang đợi? | `getLockOwnerId()`, `getLockOwnerName()` | Có thể không biết: -1/null |
| Thread đang làm gì? | `getThreadState()` và `getStackTrace()` | Tình trạng và các stack frames tại snapshot |
| Một deadlock đã được JVM phát hiện? | `ThreadMXBean.findDeadlockedThreads()` | Phát hiện một số chu trình deadlock của platform threads |

**`getLockInfo()` khác `getLockedMonitors()`.** Tên `getLockInfo` là **số ít** và chỉ mô tả đối tượng mà thread **đang chờ**, không phải tất cả các lock nó đang giữ. Một thread có thể đang giữ monitor A và ReentrantLock B nhưng đang `WAITING` trên một latch C.

## 3. Các lớp API và hợp đồng của chúng

| API | Thuộc module | Vai trò |
| --- | --- | --- |
| `ManagementFactory.getThreadMXBean()` | `java.management` | Lấy singleton ThreadMXBean của JVM hiện tại |
| `ThreadMXBean.getThreadInfo(long[], boolean, boolean)` | `java.management` | Snapshot thread IDs với lựa chọn monitors/synchronizers |
| `ThreadMXBean.dumpAllThreads(boolean, boolean)` | `java.management` | Snapshot tất cả **platform threads** đang sống |
| `ThreadMXBean.getThreadInfo(ids, monitors, synchronizers, maxDepth)` | `java.management` | Giới hạn stack depth, có từ Java 10 |
| `ThreadMXBean.dumpAllThreads(monitors, synchronizers, maxDepth)` | `java.management` | Thread dump có giới hạn depth, có từ Java 10 |
| `ThreadMXBean.isObjectMonitorUsageSupported()` | `java.management` | Có hỗ trợ thu thập monitor ownership không |
| `ThreadMXBean.isSynchronizerUsageSupported()` | `java.management` | Có hỗ trợ thu thập ownable synchronizer ownership không |
| `ThreadInfo.getLockedMonitors()` | `java.management` | Mảng `MonitorInfo[]` |
| `ThreadInfo.getLockedSynchronizers()` | `java.management` | Mảng `LockInfo[]` |
| `ThreadInfo.getStackTrace()` | `java.management` | Mảng `StackTraceElement[]` |
| `MonitorInfo.getLockedStackDepth()` | `java.management` | Chỉ số trong stack trace tương ứng monitor acquisition |
| `MonitorInfo.getLockedStackFrame()` | `java.management` | StackTraceElement lúc chiếm monitor, nếu có |
| `LockInfo.getClassName()/getIdentityHashCode()` | `java.management` | Identity của đối tượng lock |
| `ThreadInfo.getLockInfo()/getLockOwnerId()` | `java.management` | Đối tượng thread đang chờ và owner nếu có |
| `Thread.threadId()` | `java.base` | ID luồng ổn định trong vòng đời, Java 19+ |
| `Thread.ofPlatform()` | `java.base` | Tạo platform thread tường minh, Java 19+ |

**Khả năng runtime là điều kiện cần:** trước khi yêu cầu chi tiết lock ownership, kiểm tra hai flags:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean synchronizers = bean.isSynchronizerUsageSupported();
if (!monitors || !synchronizers) {
    System.out.println("Runtime does not support both lock views");
}
~~~

Đây là **snippet trong method**, Java 17+. Nếu đòi `true` cho capability mà VM không hỗ trợ, `getThreadInfo(..., true, true)` hoặc `dumpAllThreads(true,true)` có thể ném `UnsupportedOperationException`. Tùy nghiệp vụ, có thể chọn flag `false` cho capability thiếu để vẫn lấy phần còn lại, hoặc bỏ qua detail, thay vì crash monitoring service.

## 4. getLockedMonitors: monitor đang được sở hữu

Một object monitor là cơ chế intrinsic synchronization của Java: khi thread đi vào `synchronized(object)` hoặc method `synchronized`, nó sở hữu monitor tương ứng cho đến khi thoát khỏi phần synchronized (ngoại trừ khi gọi `Object.wait` đúng monitor đó).

~~~java
Object lock = new Object();
synchronized (lock) {
    // Thread đang sở hữu monitor của lock.
}
~~~

Đây là snippet trong method, không độc lập. Một platform thread có thể sở hữu nhiều monitors lồng nhau; `getLockedMonitors()` trả mảng `MonitorInfo[]` cho những monitors ấy trong snapshot.

`MonitorInfo` **extends `LockInfo`**, nên một item có:

- `getClassName()`: tên class của đối tượng monitor;
- `getIdentityHashCode()`: `System.identityHashCode(monitorObject)`;
- `getLockedStackDepth()`: chỉ số stack (nếu biết);
- `getLockedStackFrame()`: frame tại điểm acquisition (nếu biết).

**Đối chiếu identity:**

~~~java
boolean same = monitorInfo.getClassName().equals(lock.getClass().getName())
        && monitorInfo.getIdentityHashCode()
                == System.identityHashCode(lock);
~~~

Đây là snippet trong method có `monitorInfo` và `lock`. Identity hash có thể **trùng** giữa những objects khác nhau; className + identityHashCode hữu ích để correlation trong snapshot, **không phải object ID duy nhất toàn JVM/qua restart**. Không đưa identity hash vào security authorization logic.

### Stack depth là index, không phải “số cấp khóa”

~~~java
MonitorInfo monitor = ...;
StackTraceElement[] stack = owner.getStackTrace();
int depth = monitor.getLockedStackDepth();
if (depth >= 0 && depth < stack.length) {
    StackTraceElement acquiredAt = monitor.getLockedStackFrame();
    boolean matches = acquiredAt != null
            && acquiredAt.equals(stack[depth]);
}
~~~

Đây là snippet trong method, `owner` là `ThreadInfo`. Theo Javadoc, `getLockedStackDepth()` là **index vào mảng `ThreadInfo.getStackTrace()`**; index 0 là frame trên cùng của stack snapshot. Nó **không** phải số nested monitors đã chiếm, không phải stack size và cũng **không phải độ sâu của ReentrantLock**.

Nếu stack location không có sẵn, depth **âm** và `getLockedStackFrame()` có thể trả **null**. Không dereference null hoặc index -1. Khi dùng maxDepth nhỏ, có thể làm mất frame acquisition hoặc không có đủ thông tin như full stack; không kết luận monitor không tồn tại chỉ vì không nhìn thấy frame tương ứng.

### Stack của monitor được lấy lúc nào?

Ví dụ:

~~~java
void work() {
    synchronized (monitor) {             // acquisition site
        waitForCondition();              // stack top có thể là await/park
    }
}
~~~

Nếu snapshot chụp trong `waitForCondition`, top stack có thể hiển thị `park`/`await`, còn `MonitorInfo.getLockedStackFrame()` trỏ về method `work` ở frame sâu hơn. Vì vậy **stack top không nhất thiết là nơi monitor đã được chiếm**. Tính năng này rất hữu ích khi một thread giữ monitor quá lâu vì blocking I/O hoặc chờ một resource khác.

## 5. getLockedSynchronizers: ownable locks, không có locked stack frame

`ThreadInfo.getLockedSynchronizers()` trả `LockInfo[]` của **ownable synchronizers** mà platform thread đang nắm. Javadoc định nghĩa ownable synchronizer là synchronizer có thể được sở hữu độc quyền bởi một thread và dựa trên `AbstractOwnableSynchronizer` hoặc subclass.

Ví dụ của JDK:
- `ReentrantLock`: đối tượng theo dõi thường là **internal synchronizer** của lock, có class name kiểu `ReentrantLock$NonfairSync` hoặc `FairSync`; đừng hardcode tên internal class.
- `ReentrantReadWriteLock.WriteLock`: write lock là ownable synchronizer.
- **Read lock** của `ReentrantReadWriteLock` là cơ chế shared, **không** được mô tả như một *exclusively-owned* synchronizer qua API này.
- `Semaphore`, `CountDownLatch`, một số primitives dùng shared AQS, **không** tự có owner exclusivity theo contract trên.
- `StampedLock` không phải một ownable `AbstractOwnableSynchronizer` theo contract trên, và thường không có entry tương ứng trong `getLockedSynchronizers()`.

Nếu mảng trống **không có nghĩa** thread không dùng bất kỳ primitive đồng bộ nào. Nó có thể đang cầm read lock, semaphore permit, stamped lock hoặc một cơ chế custom không đăng ký ownership theo AQS.

### LockInfo không mang stack acquisition

~~~java
for (LockInfo synchronizer : info.getLockedSynchronizers()) {
    String className = synchronizer.getClassName();
    int identity = synchronizer.getIdentityHashCode();
    // Không có synchronizer.getLockedStackFrame().
}
~~~

Đây là snippet trong method đã có `ThreadInfo info`. `LockInfo` chỉ có class name, identity hash, `toString()` và các methods tạo/convert; không có `getLockedStackDepth` hoặc `getLockedStackFrame`. **Đừng ép kiểu `LockInfo` của ReentrantLock thành `MonitorInfo`.**

Có thể xem `info.getStackTrace()` để tìm nơi ứng dụng đang gọi các methods mà nó đi qua `lock.lock()`, nhưng thường thread đã đi qua call acquisition và đang làm việc khác. Không thể tự khẳng định một stack frame bất kỳ chính là nơi gọi `lock()` lúc đầu. Để biết lock acquisition site chính xác, hãy:
- Instrument ở wrapper lock hoặc vùng business critical section;
- Dùng JFR/metrics/profiling và correlation IDs khi phù hợp;
- Thêm logging có giới hạn về thread/operation/lock identity, không log secrets;
- Theo dõi **current stack** và biết đây chỉ là bằng chứng tương quan, không phải acquisition stack đã được bảo toàn trong `LockInfo`.

## 6. ThreadInfo.getLockInfo là khóa *đang đợi*, không phải *đang giữ*

Ví dụ một thread bị chặn khi cố vào:

~~~java
synchronized (monitor) {
    // Nếu monitor đang bị thread khác giữ,
    // thread này ở trạng thái BLOCKED trước khi vào block.
}
~~~

Một `ThreadInfo` của thread đang `BLOCKED` có thể cung cấp:

~~~java
ThreadInfo blocked = ...;
LockInfo waitingFor = blocked.getLockInfo();
long ownerId = blocked.getLockOwnerId();
String ownerName = blocked.getLockOwnerName();
~~~

Đây là snippet trong method, cần một snapshot hợp lệ. `getLockInfo()` trả **lock object mà thread đang cố acquire hoặc waiting/park trên đó**; `getLockOwnerId()` trả ID owner hoặc **-1** khi không xác định được. `getLockOwnerName()` có thể `null`.

Trong program runnable:
- `lock-owner-demo` giữ `MONITOR` và `EXCLUSIVE`.
- `lock-contender-demo` cố vào `synchronized(MONITOR)` và ở `BLOCKED`.
- `waiting.getLockInfo()` mang identity của `MONITOR`, nhưng `waiting.getLockedMonitors()` **không** chứa `MONITOR` vì nó **chưa** acquire.
- `waiting.getLockOwnerId()` trỏ về `holder.threadId()` tại snapshot.

**WAITING không phải BLOCKED.** `Thread.State.BLOCKED` trong Java liên quan chờ monitor entry. Một thread dùng `ReentrantLock.lock()` có thể chờ bằng `LockSupport.park`, từ đó trạng thái thường là `WAITING`/`TIMED_WAITING`; `getLockInfo` có thể trỏ tới blocker/AQS synchronizer. Thread không nhất thiết ở `BLOCKED` chỉ vì “đang chờ một lock”.

## 7. Lấy snapshot đúng và đúng tham số

Ví dụ:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
ThreadInfo[] snapshots = bean.getThreadInfo(
        new long[]{worker.threadId(), contender.threadId()},
        true, true);
~~~

Đây là snippet Java 21+ vì `threadId()`; giả sử `worker` và `contender` đã started. Hai boolean lần lượt là **lockedMonitors** và **lockedSynchronizers**, không phải “include stack” hoặc “include blocked threads”.

Các overload:

| Lời gọi | Nội dung |
| --- | --- |
| `getThreadInfo(long id)` | Snapshot cơ bản, **không** lấy stack và locked arrays |
| `getThreadInfo(long id, int maxDepth)` | Lấy stack tới maxDepth, **không** lấy locked arrays |
| `getThreadInfo(long[] ids)` | Snapshot nhiều IDs, không stack và locked arrays |
| `getThreadInfo(long[] ids, int maxDepth)` | Stack, nhưng **không** lấy monitors/synchronizers |
| `getThreadInfo(ids, true, true)` | Full stack và cả hai nhóm locks nếu VM hỗ trợ |
| `getThreadInfo(ids, true, true, maxDepth)` | Cả hai nhóm locks + giới hạn stack depth |
| `dumpAllThreads(true,true)` | Tất cả live **platform threads** với full stack và locks |
| `dumpAllThreads(true,true,maxDepth)` | Platform threads với giới hạn stack depth |

**Khi overload không yêu cầu lock arrays, hai mảng trống** ngay cả nếu thread đang sở hữu khóa. Đây là một lỗi chẩn đoán rất phổ biến: dùng `bean.getThreadInfo(threadId)`, nhìn thấy `getLockedMonitors().length == 0` và suy ra thread không giữ monitor. Kết luận ấy sai vì **không yêu cầu dữ liệu ownership**.

### Thread ID, null và thứ tự mảng

- `getThreadInfo(long[] ids,...)` trả mảng có phần tử tương ứng theo **vị trí input IDs**.
- Nếu thread đã chết, không tồn tại hoặc là **virtual thread**, vị trí tương ứng có thể là **null** theo JDK hiện hành.
- `threadId()` trả ID dương ổn định trong vòng đời Thread; ID không phải mã nhận diện business/user, không phải OS thread ID.
- Với JDK 21+, ưu tiên `Thread.threadId()` (final, hiện hành). `Thread.getId()` được đánh dấu deprecated từ Java 19, dù code Java 17 cũ vẫn còn chạy được.
- Nếu request nhiều thread IDs, dùng một snapshot call thay vì gọi riêng từng thread nhiều lần để giảm độ lệch thời gian, nhưng **không giả định tất cả threads được snapshot atomically**.

### maxDepth và giá trị -1

`getThreadInfo(ids,true,true,maxDepth)` chỉ yêu cầu tối đa `maxDepth` stack elements. `maxDepth=0` không có Java stack; giá trị âm là invalid. Nếu cần quan hệ acquisition frame chính xác, thường cần stack đủ dài hoặc full stack. `MonitorInfo.getLockedStackDepth()` có thể âm nếu JVM không có frame tương ứng. Đừng diễn giải độ sâu âm thành index hay một exception không kiểm soát.

`dumpAllThreads(true,true)` có thể **đắt** ở hệ thống rất nhiều platform threads; ưu tiên chọn một số IDs nghi vấn, lấy một snapshot có giới hạn/cadence, dùng diagnostics chuyên dụng khi cần dump toàn JVM.

## 8. Chương trình Java 21+ hoàn chỉnh: một luồng giữ cả monitor lẫn ReentrantLock

Chương trình **`ThreadLocksSnapshotDemo.java`** hoạt động **chỉ trong JVM**, không mở socket, không truy cập internet, không cần thư viện ngoài. Nó tạo hai **platform threads**:

1. `holder` lock một `ReentrantLock`, sau đó vào `synchronized(MONITOR)`.
2. Trong synchronized block, holder báo `ready` và chờ `CountDownLatch.await()`; vẫn giữ cả monitor và ReentrantLock.
3. `contender` cố acquire cùng monitor và bị `BLOCKED`.
4. Thread main kiểm tra JVM có hỗ trợ monitor/synchronizer tracking; lấy **một snapshot** chứa cả hai.
5. Tìm đúng `MonitorInfo` của `MONITOR` theo class/identity hash và kiểm `getLockedStackDepth/getLockedStackFrame` nằm đúng `ThreadInfo.getStackTrace()`.
6. Kiểm `LockInfo[]` của holder có synchronizer của `ReentrantLock`.
7. Kiểm contender ở `BLOCKED`, đang chờ đúng `MONITOR` và owner ID là holder.
8. Kiểm overload cơ bản `getThreadInfo(id)` **không có lock arrays**.
9. So sánh `dumpAllThreads(true,true,maxDepth)` có chứa platform holder.
10. Dọn threads trong `finally`, không tạo deadlock cố ý, không dùng `Thread.stop()`.

**Vì code dùng `Thread.threadId()` và `Thread.ofPlatform()`, cần JDK 21+**. Đây là ví dụ hiện đại, được biên dịch trên JDK 24 bằng `--release 21`. Những APIs ThreadMXBean/ThreadInfo nói ở trên vẫn áp dụng từ Java 17.

~~~java
import java.lang.management.LockInfo;
import java.lang.management.ManagementFactory;
import java.lang.management.MonitorInfo;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class ThreadLocksSnapshotDemo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock EXCLUSIVE = new ReentrantLock();

    private static void holdBoth(CountDownLatch ready, CountDownLatch release) {
        EXCLUSIVE.lock();
        try {
            synchronized (MONITOR) {
                ready.countDown();
                release.await();
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } finally {
            EXCLUSIVE.unlock();
        }
    }

    private static boolean waitUntilBlocked(Thread thread)
            throws InterruptedException {
        for (int i = 0; i < 300; i++) {
            if (thread.getState() == Thread.State.BLOCKED) return true;
            Thread.sleep(10);
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        boolean monitorsSupported = bean.isObjectMonitorUsageSupported();
        boolean synchronizersSupported = bean.isSynchronizerUsageSupported();
        System.out.println("monitor usage supported: " + monitorsSupported);
        System.out.println("synchronizer usage supported: " + synchronizersSupported);
        if (!monitorsSupported || !synchronizersSupported) {
            System.out.println("detail unsupported: true");
            return;
        }

        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch contenderReady = new CountDownLatch(1);
        Thread holder = Thread.ofPlatform().name("lock-owner-demo")
                .unstarted(() -> holdBoth(ready, release));
        Thread contender = Thread.ofPlatform().name("lock-contender-demo")
                .unstarted(() -> {
                    contenderReady.countDown();
                    synchronized (MONITOR) {
                        // Acquires the monitor only after holder releases it.
                    }
                });

        try {
            holder.start();
            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Holder did not acquire locks");
            }
            contender.start();
            if (!contenderReady.await(5, TimeUnit.SECONDS)
                    || !waitUntilBlocked(contender)) {
                throw new IllegalStateException("Contender was not BLOCKED");
            }

            long ownerId = holder.threadId();
            long contenderId = contender.threadId();
            ThreadInfo[] snapshots = bean.getThreadInfo(
                    new long[]{ownerId, contenderId}, true, true);
            ThreadInfo owning = snapshots[0];
            ThreadInfo waiting = snapshots[1];
            if (owning == null || waiting == null) {
                throw new IllegalStateException("Missing thread snapshot");
            }

            MonitorInfo[] monitors = owning.getLockedMonitors();
            LockInfo[] synchronizers = owning.getLockedSynchronizers();
            MonitorInfo acquired = Arrays.stream(monitors)
                    .filter(m -> m.getIdentityHashCode()
                            == System.identityHashCode(MONITOR)
                            && m.getClassName().equals(MONITOR.getClass().getName()))
                    .findFirst().orElseThrow();
            int depth = acquired.getLockedStackDepth();
            StackTraceElement[] stack = owning.getStackTrace();

            System.out.println("holder waiting on latch: "
                    + (owning.getThreadState() == Thread.State.WAITING));
            System.out.println("owner holds object monitor: "
                    + (monitors.length >= 1));
            System.out.println("monitor stack depth available: " + (depth >= 0));
            System.out.println("monitor depth equals frame index: "
                    + (depth < stack.length && depth >= 0
                    && acquired.getLockedStackFrame().equals(stack[depth])));
            System.out.println("monitor acquired in holdBoth: "
                    + "holdBoth".equals(acquired.getLockedStackFrame().getMethodName()));
            System.out.println("owner holds ReentrantLock synchronizer: "
                    + Arrays.stream(synchronizers).anyMatch(s ->
                    s.getClassName().contains("ReentrantLock")));
            System.out.println("contender BLOCKED: "
                    + (waiting.getThreadState() == Thread.State.BLOCKED));
            System.out.println("contender waits for owner id: "
                    + (waiting.getLockOwnerId() == ownerId));
            System.out.println("contender lock identity matches monitor: "
                    + (waiting.getLockInfo() != null
                    && waiting.getLockInfo().getIdentityHashCode()
                            == System.identityHashCode(MONITOR)));
            System.out.println("contender owns no target monitor: "
                    + Arrays.stream(waiting.getLockedMonitors()).noneMatch(m ->
                    m.getIdentityHashCode() == System.identityHashCode(MONITOR)));

            ThreadInfo shallow = bean.getThreadInfo(ownerId);
            System.out.println("basic snapshot lacks owned-lock arrays: "
                    + (shallow != null
                    && shallow.getLockedMonitors().length == 0
                    && shallow.getLockedSynchronizers().length == 0));
            ThreadInfo[] all = bean.dumpAllThreads(true, true, 12);
            System.out.println("dumpAllThreads includes holder: "
                    + Arrays.stream(all).anyMatch(i -> i.getThreadId() == ownerId));
        } finally {
            release.countDown();
            holder.join(5000);
            contender.join(5000);
            if (holder.isAlive() || contender.isAlive()) {
                holder.interrupt();
                contender.interrupt();
                throw new IllegalStateException("Test threads did not stop");
            }
        }
        System.out.println("threads terminated: true");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 21 ThreadLocksSnapshotDemo.java
java ThreadLocksSnapshotDemo
~~~

**Stdout chính xác** đã chạy trên **OpenJDK 24.0.2** (Java 21 bytecode/API target):

~~~text
monitor usage supported: true
synchronizer usage supported: true
holder waiting on latch: true
owner holds object monitor: true
monitor stack depth available: true
monitor depth equals frame index: true
monitor acquired in holdBoth: true
owner holds ReentrantLock synchronizer: true
contender BLOCKED: true
contender waits for owner id: true
contender lock identity matches monitor: true
contender owns no target monitor: true
basic snapshot lacks owned-lock arrays: true
dumpAllThreads includes holder: true
threads terminated: true
~~~

### Đọc kết quả theo contract

**Hai dòng `usage supported`:** runtime có khả năng lấy object monitors và ownable synchronizers. Nếu dùng JVM/provider khác không hỗ trợ, program sẽ in `detail unsupported: true` và dừng trước khi khởi tạo threads. Đừng coi output OpenJDK thành lời hứa mọi VM đều hỗ trợ.

**`holder waiting on latch: true`:** holder đang `WAITING`, nhưng nó vẫn **giữ object monitor và ReentrantLock**. Đây là bằng chứng cụ thể rằng WAITING không có nghĩa “không cầm khóa”.

**`monitor stack depth available`, `monitor depth equals frame index` và `monitor acquired in holdBoth`:** `MonitorInfo` chứa frame acquisition, depth trỏ vào mảng `owning.getStackTrace()` ở cùng snapshot. Stack top lúc này có thể ở `CountDownLatch.await/LockSupport.park`, không phải `holdBoth`.

**`owner holds ReentrantLock synchronizer`:** mảng `LockInfo[]` nhận diện synchronizer của `ReentrantLock`. Program kiểm tên class chứa `ReentrantLock` thay vì hardcode `$NonfairSync` vì class implementation có thể thay đổi. `LockInfo` **không cung cấp acquisition stack frame**, nên output cũng không tuyên bố có.

**`contender BLOCKED`, `waits for owner id` và `lock identity matches monitor`:** luồng khác chờ acquire monitor, chủ sở hữu là holder. Trong khi ấy, `contender owns no target monitor` bảo đảm không nhầm đối tượng đang chờ với đối tượng đã sở hữu.

**`basic snapshot lacks owned-lock arrays: true`:** `bean.getThreadInfo(ownerId)` là overload snapshot cơ bản, **không** yêu cầu lấy locked monitors/synchronizers. Hai arrays trống vì API call không lấy dữ liệu, không phải vì holder đã nhả khóa.

**`dumpAllThreads includes holder`:** live platform thread được liệt kê trong dump snapshot. Không in toàn bộ JVM dump vì nó chứa stack/IDs của các library threads khác và thay đổi theo môi trường.

**`threads terminated`:** test giải phóng latch, chờ threads kết thúc và dọn tài nguyên. Không cố tạo deadlock gây treo process.

## 9. Virtual threads trong Java hiện đại: giới hạn rất quan trọng

Từ Java 21, **virtual threads** đã là tính năng phổ biến. Tuy nhiên Javadoc Java SE 25 xác định `java.lang.management.ThreadMXBean` chỉ quản lý **platform threads**, **không** quản lý virtual threads.

Hệ quả:
- `dumpAllThreads(true,true)` **không liệt kê virtual threads**.
- `getThreadInfo(new long[]{virtual.threadId()},...,...)` trả phần tử **null** cho virtual thread ID.
- Một `null` không tự chứng minh thread đã chết; cũng có thể là virtual thread.
- `getAllThreadIds()` và các số lượng liên quan của ThreadMXBean phản ánh platform threads theo contract.
- `getLockedMonitors()/getLockedSynchronizers()` không cung cấp một bảng “mọi khóa của mọi virtual threads” qua management API này.

**Đây là giới hạn của API**, không phải lỗi nên chữa bằng cách bật một deprecated flag. Đối với điều tra virtual threads trên HotSpot JDK hiện đại, xem `jcmd` thread dumps có hỗ trợ virtual threads, Java Flight Recorder/JFR events và các công cụ quan sát mà runtime cung cấp. Một `jcmd Thread.dump_to_file` có thể bao gồm virtual threads nhưng format/scope **khác** ThreadMXBean/JMX thread dump truyền thống. Không sử dụng nó như bằng chứng mọi monitor/reentrant lock đều được capture đồng nhất.

### Ví dụ Java 21+ số 2: ThreadMXBean không liệt kê virtual thread

File **`VirtualThreadVisibilityDemo.java`** tạo một virtual thread chạy thật, chờ latch cho phép main kiểm tra snapshot, sau đó dọn nó. Không mở network, không ép tạo hàng nghìn virtual threads.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class VirtualThreadVisibilityDemo {
    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        CountDownLatch ready = new CountDownLatch(1);
        CountDownLatch finish = new CountDownLatch(1);
        Thread virtual = Thread.ofVirtual().name("virtual-observation-demo")
                .unstarted(() -> {
                    ready.countDown();
                    try {
                        finish.await();
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                    }
                });
        try {
            virtual.start();
            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Virtual worker did not start");
            }
            long id = virtual.threadId();
            ThreadInfo[] selected = bean.getThreadInfo(new long[]{id}, false, false);
            boolean listed = Arrays.stream(bean.dumpAllThreads(false, false, 8))
                    .anyMatch(info -> info.getThreadId() == id);
            System.out.println("virtual thread running: " + virtual.isAlive());
            System.out.println("ThreadMXBean getThreadInfo is null: "
                    + (selected.length == 1 && selected[0] == null));
            System.out.println("dumpAllThreads excludes virtual: " + !listed);
        } finally {
            finish.countDown();
            virtual.join(5000);
            if (virtual.isAlive()) {
                virtual.interrupt();
                throw new IllegalStateException("Virtual worker did not stop");
            }
        }
        System.out.println("virtual thread terminated: true");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 21 VirtualThreadVisibilityDemo.java
java VirtualThreadVisibilityDemo
~~~

**Stdout chính xác** trên OpenJDK 24.0.2:

~~~text
virtual thread running: true
ThreadMXBean getThreadInfo is null: true
dumpAllThreads excludes virtual: true
virtual thread terminated: true
~~~

Program chứng minh quản lý thread bằng ThreadMXBean **không bao phủ virtual threads**. Nó không chứng minh virtual thread không dùng synchronized hoặc locks; chỉ là **API chụp snapshot này không báo cáo các luồng ấy**.

### JFR và jcmd dành cho virtual threads

Trong HotSpot JDK 25, diagnostic command:

~~~bash
jcmd <pid> Thread.dump_to_file -format=plain thread-dump.txt
jcmd <pid> Thread.dump_to_file -format=json thread-dump.json
~~~

Đây là **minh họa lệnh**: thay `<pid>` bằng process ID có quyền quan sát, dùng đường dẫn file trong vùng được phép ghi. `jcmd` hỗ trợ `Thread.dump_to_file`; dạng output plain/JSON có thể chứa virtual threads theo runtime và phiên bản. Không dùng `-format=text` cho JDK25 vì man page dùng giá trị **`plain`** hoặc **`json`**.

**Lưu ý:** thread dump là dữ liệu nội bộ nhạy cảm; stack có thể tiết lộ tên class, paths, query, lock contention và đôi khi thông tin người dùng. Chỉ chạy bởi người được phân quyền, lưu file có ACL phù hợp và xóa theo retention policy.

## 10. Quan hệ stack: current stack, acquisition stack, blocked stack

Ba loại “stack” thường bị trộn lẫn:

| Stack | Có ở API nào? | Diễn giải |
| --- | --- | --- |
| **Current call stack** | `ThreadInfo.getStackTrace()` | Luồng đang gọi gì tại thời điểm snapshot |
| **Monitor acquisition frame** | `MonitorInfo.getLockedStackFrame()`/`getLockedStackDepth()` | Frame đã acquire monitor, nếu JVM có dữ liệu |
| **Ownable synchronizer acquisition frame** | **Không có** trong `LockInfo` | Không thể lấy trực tiếp từ `getLockedSynchronizers()` |

Khi contender ở `BLOCKED`:
- Current stack thường có frame cố vào một `synchronized` block.
- `getLockInfo` cho identity của monitor đang bị tranh chấp.
- `getLockOwnerId` có thể tìm thread giữ monitor.
- Owner's `getLockedMonitors` và acquisition frame giúp biết lock do owner lấy ở code path nào.

Khi contender `WAITING` trên `ReentrantLock`:
- Thread state có thể là WAITING do `LockSupport.park`, không nhất thiết BLOCKED.
- `getLockInfo` có thể mô tả AQS synchronizer đang chờ.
- Owner's `getLockedSynchronizers` mô tả ownable lock; nhưng **không có acquisition stack frame cho ReentrantLock**.
- Cần kết hợp current stack, lock ownership, contention metrics/JFR và business traces.

**Tránh chọn một stack frame đơn lẻ để buộc tội “đây là dòng gây deadlock”.** Stack chỉ là snapshot, có nhiều lock orders và threads khác liên quan. Phân tích vòng chờ đầy đủ, đặc biệt khi một thread vừa giữ lock A vừa đợi lock B.

## 11. Deadlocks: monitor-only và cả ownable synchronizers

`ThreadMXBean` có hai methods:

| API | Phạm vi phát hiện |
| --- | --- |
| `findMonitorDeadlockedThreads()` | Chu trình deadlock **chỉ do object monitors** |
| `findDeadlockedThreads()` | Chu trình deadlock do **object monitors hoặc ownable synchronizers**, nếu VM hỗ trợ |

Dùng trên JVM hỗ trợ:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
long[] deadlocked = bean.findDeadlockedThreads();
if (deadlocked != null && deadlocked.length > 0) {
    // Thu snapshot chi tiết của các platform threads này;
    // không tự tạo deadlock trong production để thử.
    ThreadInfo[] details = bean.getThreadInfo(deadlocked, true, true);
}
~~~

Đây là snippet trong method; trước khi gọi với `true,true` cần xét capability flags, và theo provider một số deadlock operations có thể không được hỗ trợ. `findDeadlockedThreads` có thể trả **null** nếu không tìm thấy chu trình, và không báo cáo mọi loại deadlock của hệ thống như I/O, database transactions, network, semaphore permits, custom non-ownable synchronizers hoặc virtual-thread-specific conditions.

**Không coi “không tìm thấy deadlock” là “không có vấn đề liveness”.** Starvation, long-held locks, missed signals, livelock và deadlock không nằm trong model API vẫn có thể tồn tại. JDK thread dump + metrics + application traces là các nguồn bổ sung.

### Pattern chẩn đoán vòng chờ

~~~text
Thread A
  owns: MONITOR_A / ReentrantLock X
  waits: MONITOR_B (owner = Thread B)

Thread B
  owns: MONITOR_B / ReentrantLock Y
  waits: MONITOR_A (owner = Thread A)

=> Vòng chờ A -> B -> A liên quan object monitors,
   có thể được findMonitorDeadlockedThreads phát hiện.
~~~

Đây là **sơ đồ**, không phải runnable code. Không nên viết bài học bằng cách tạo hai threads deadlock vô thời hạn mà không có cách shutdown; demo chính cố ý chỉ tạo **contention có thể giải phóng**, không có cycle.

## 12. Điều kiện snapshot có thể gây hiểu nhầm

### 12.1. Thread kết thúc giữa hai lần đọc

`ThreadInfo[]` có thể chứa `null` cho thread đã chấm dứt giữa lúc bạn thu ID và lấy snapshot. `dumpAllThreads` cũng có thể trả bản ghi cho một thread đã kết thúc vào thời điểm caller nhận kết quả. Handle null, đừng phát sinh lỗi `NullPointerException` trong công cụ giám sát.

### 12.2. Current stack và lock arrays không phải lịch sử

`getLockedMonitors/getLockedSynchronizers` cho **khóa đang nắm tại snapshot**, không phải danh sách mọi khóa từng nắm. Nếu lock được release trước khi snapshot hoặc acquire ngay sau đó, nó không có mặt. Đừng dùng thông tin này để tính chính xác số lần acquisition hay fairness trong toàn ứng dụng.

### 12.3. getLockedSynchronizers không bao phủ mọi locking mechanism

ReentrantLock ownable được report; read-lock shared, semaphore permits, countdown latches, stamped locks, custom synchronization không theo `AbstractOwnableSynchronizer` có thể không được đại diện như owner locks. Đừng suy luận một thread an toàn để interrupt/stop chỉ vì array rỗng.

### 12.4. Thread state và blocked-owner đôi khi không đủ

- `BLOCKED` thường liên quan monitor entry.
- `WAITING/TIMED_WAITING` có thể là Object.wait, LockSupport.park, Condition.await, latch await...
- `RUNNABLE` có thể là CPU work hoặc native I/O tùy runtime, không tự đồng nghĩa CPU saturation.
- `getLockOwnerId() == -1` có thể do không có owner tương ứng, không xác định được hoặc thread không đợi một khóa có chủ sở hữu duy nhất.

### 12.5. Snapshot mang thông tin nhạy cảm

Một full JVM thread dump có thể chứa method names, package names, tenant identifiers, class loader paths hoặc thông tin vận hành. Trong application phục vụ nhiều tenants, giới hạn quyền truy cập JMX/memory dumps, không phát toàn bộ stack cho endpoint công khai, không gửi file dump vào ticket không kiểm soát.

### 12.6. Cách chụp có overhead

Lấy full stack và object monitor/synchronizer usage trên JVM có hàng nghìn platform threads có thể gây latency/safepoint pressure tùy provider. `ThreadMXBean.getThreadInfo(ids,true,true)` được tài liệu gọi là dành cho **troubleshooting**, không phải vòng polling tốc độ rất cao trong hot path. Chỉ lấy khi có incident hoặc cadence/budget rõ ràng, thường kèm JFR.

## 13. Từ StackTraceElement tới nơi giữ monitor

Khi nhận một `MonitorInfo`:

~~~java
for (MonitorInfo m : info.getLockedMonitors()) {
    int depth = m.getLockedStackDepth();
    StackTraceElement frame = m.getLockedStackFrame();
    if (depth >= 0 && depth < info.getStackTrace().length && frame != null) {
        System.out.println(m.getClassName() + " acquired at "
                + frame.getClassName() + "." + frame.getMethodName());
    }
}
~~~

Đây là snippet trong method có `ThreadInfo info`. Đừng mặc định `frame.getLineNumber()` lúc nào cũng có giá trị dương: line number có thể là -1 nếu class không được build với đầy đủ debug line data, bị native code, synthetic frames hoặc bị VM rút gọn. `getClassName`/`getMethodName` giúp chẩn đoán nhưng không phải security boundary.

### Mapping chính xác hơn với versioned source

Nếu production dùng bản release khác bản source đang mở trong IDE, line numbers từ stack có thể chỉ sang dòng không còn cùng nội dung. Hãy giữ:
- Build ID/revision của artifact đang chạy;
- JDK version/provider;
- Tên class/method, frame line number;
- Thread name/id và timestamp snapshot;
- Trạng thái, source monitor/synchronizer identity;
- Trace/correlation ID bên application nếu có.

Đừng gắn stack dump với source code từ một branch bất kỳ rồi kết luận sai về critical section.

## 14. Hạn chế của identityHashCode và cách so sánh khóa

`LockInfo.getClassName()` và `getIdentityHashCode()` được tạo từ tên class và `System.identityHashCode(Object)`. `LockInfo.toString()` thường mang dạng:

~~~text
java.lang.Object@6a7b8c9d
java.util.concurrent.locks.ReentrantLock$NonfairSync@4b5c6d7e
~~~

Đây là ví dụ dạng hiển thị, **không phải output của chương trình**; hash và loại synchronizer nội bộ có thể khác. Identity hash:
- Không phải hash của `equals()`;
- Có thể trùng, không phải ID mã hóa bảo mật;
- Không có tính ổn định xuyên process/restart;
- Không tiết lộ object reference thật qua standard API;
- Không cho biết thời điểm lock được acquire.

Trong demo, ta so `System.identityHashCode(MONITOR)` và tên class `java.lang.Object`. Đó là một assertion hữu ích trong một process/instance cụ thể. Với production, nếu nhiều objects cùng class/identity hash trùng, cần thêm context code, trace và object mapping nội bộ.

## 15. Thực hành quan sát an toàn trên JVM thật

### Bước 1. Xác định nền tảng và nhóm threads

Dùng `ManagementFactory.getThreadMXBean()` để thu `getThreadCount()`, `getPeakThreadCount()` hoặc `getAllThreadIds()` của **platform threads**. Với virtual threads, dùng diagnostics thích hợp như JFR hoặc HotSpot thread dumps; đừng nghĩ số platform threads thấp nghĩa tổng số tác vụ concurrent thấp.

### Bước 2. Kiểm capability và chỉ bật khi cần

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean synchronizers = bean.isSynchronizerUsageSupported();
ThreadInfo[] view = bean.dumpAllThreads(monitors, synchronizers, 40);
~~~

Đây là snippet trong method. Nó tránh truyền `true` cho capability không hỗ trợ, đồng thời giới hạn stack depth 40 để giảm chi phí. Nó không phải một mẫu yêu cầu cứ phải dump mọi thread trong hot loop.

### Bước 3. Phân nhóm ownership/waiting

Thay vì chỉ đếm tất cả `BLOCKED`:
1. Tìm những threads `BLOCKED` theo monitor.
2. Nhóm theo `getLockInfo()` className + identityHashCode.
3. Với mỗi lock, tìm owner qua `getLockOwnerId()`, sau đó owner `getLockedMonitors()`.
4. Dùng `MonitorInfo.getLockedStackFrame()` để tìm điểm acquire.
5. Xem owner đang làm gì ở current stack: I/O, latch, logging, DB call?
6. Kiểm ownable synchronizers mà owner cũng đang giữ.
7. Thu snapshot khác sau một khoảng có giới hạn để biết contention kéo dài hay chỉ chớp nhoáng.

Đây là **quy trình chẩn đoán**, không phải bảo đảm làm rõ mọi deadlock. Một monitor-owner ID có thể bị mất khi thread đổi trạng thái giữa snapshots.

### Bước 4. Kết hợp các quan sát khác

- **JFR**: profile lock contention, blocked events, thread states và thời gian khi cần; bật cấu hình recording có kiểm soát.
- **jcmd**: lấy thread dumps để phân tích manual hoặc JSON bằng công cụ thích hợp.
- **Ứng dụng**: timers quanh critical section, metrics long-held lock, structured logs không có secrets.
- **Database/network tracing**: phân biệt thread giữ monitor nhưng kẹt I/O, query DB, RPC hay external API.
- **CI stress tests**: kiểm thử lock ordering/concurrency logic trong môi trường được cô lập.

## 16. Bảng kiểm thử và kịch bản cần có

| Tình huống | Kỳ vọng |
| --- | --- |
| JVM hỗ trợ object monitor monitoring | `isObjectMonitorUsageSupported()==true` |
| JVM hỗ trợ ownable synchronizer monitoring | `isSynchronizerUsageSupported()==true` |
| JVM thiếu một capability | Tránh gọi overload đòi unsupported detail |
| Holder vào synchronized(MONITOR) | MonitorInfo của MONITOR xuất hiện |
| Holder sở hữu ReentrantLock | LockInfo cho internal ownable sync xuất hiện |
| Holder đang await latch | Có thể WAITING nhưng vẫn giữ locks |
| Monitor getLockedStackDepth | Index hợp lệ hoặc âm nếu không có |
| Monitor getLockedStackFrame | Nếu có, khớp `stack[depth]` |
| Monitor acquisition method | Khi stack đủ, frame dẫn tới vùng synchronized |
| Synchronizer LockInfo | Có className/identityHashCode, không acquisition frame |
| Contender đang chờ monitor | `Thread.State.BLOCKED` |
| Contender.getLockInfo | Mô tả MONITOR đang muốn acquire |
| Contender.getLockOwnerId | Bằng ID holder trong snapshot |
| Contender.getLockedMonitors | Không chứa monitor chưa acquire |
| Overload `getThreadInfo(threadId)` | Locked arrays trống dù thread đang giữ khóa |
| `dumpAllThreads(true,true)` | Chứa live platform threads |
| Thread ID từ Java 21+ | `threadId()` hiện hành, không dùng deprecated getId |
| Thread vừa kết thúc | Một phần tử `ThreadInfo[]` có thể null |
| Request virtual thread ID | ThreadMXBean trả null |
| DumpAllThreads và virtual threads | Không bao gồm virtual threads |
| Thread giữ ReentrantReadWriteLock read lock | Không là exclusive ownable `LockInfo` theo contract |
| Thread giữ ReentrantReadWriteLock write lock | Có thể xuất hiện như ownable synchronizer |
| Thread đang chờ ReentrantLock | Có thể WAITING/TIMED_WAITING chứ không nhất thiết BLOCKED |
| Stack bị giới hạn depth | Không suy ra acquisition frame luôn sẵn |
| ThreadMXBean.getLockOwnerId() == -1 | Chấp nhận unknown owner; không đoán |
| Thao tác khi capability unsupported | Không làm crash monitoring process |
| Deadlock chỉ monitors | findMonitorDeadlockedThreads có thể phát hiện |
| Deadlock cả ownable synchronizers | findDeadlockedThreads có thể phát hiện khi supported |
| Application I/O hangs | Chỉ lock dump chưa chắc đủ kết luận |
| Không có deadlock | Không loại trừ starvation/livelock |
| High-frequency full dumps | Cần giới hạn overhead/cadence |
| Monitoring security | JMX/stack dumps không public, không lộ dữ liệu nhạy cảm |
| Cleanup test | Release latch/join, không leak threads |

### Không biến test thành deadlock thật

Một bài học về locks không cần cố ý tạo hai threads giữ hai monitors đảo thứ tự và kẹt vĩnh viễn. Một test như vậy có thể làm JVM không thoát, làm CI bị treo và khó dọn an toàn. Ví dụ chính chỉ tạo contention có thể giải phóng bằng latch. Nếu cần deadlock testing, chạy trong một **process con có timeout/kill và thu thread dump** rồi dọn process theo kịch bản.

## 17. Những lỗi rất hay gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Thấy mảng `getLockedMonitors()` rỗng rồi bảo thread không giữ lock | Snapshot đã gọi overload không lấy locks | Dùng `getThreadInfo(ids,true,true)` |
| Nhầm `getLockInfo()` với locks đang giữ | `getLockInfo` là lock đang đợi | Dùng getLockedMonitors/getLockedSynchronizers |
| Coi mọi `WAITING` là không giữ monitor | Có thể đang chờ latch trong synchronized | Kiểm ownership và stack |
| Coi mọi `BLOCKED` là ReentrantLock | BLOCKED thường monitor entry | Phân biệt monitor/AQS park |
| Coi mọi ReentrantLock có acquisition stack frame | LockInfo không có lockedStackFrame | Instrument/JFR nếu cần |
| Ép `LockInfo` của synchronizer thành `MonitorInfo` | Hai loại thông tin khác nhau | Chỉ MonitorInfo có locked frame |
| Hardcode class `ReentrantLock$NonfairSync` | Chi tiết internal/provider/fairness khác nhau | Nhìn className/identity theo contract |
| Coi identity hash là object ID duy nhất toàn JVM | Hash có thể va chạm | Bổ sung context và process identity |
| Coi maxDepth nhỏ vẫn đủ trace monitor | Frame có thể bị cắt | Dùng full/depth đủ và xét -1/null |
| Đọc `getLockedStackDepth` như số lock đang giữ | Đây là stack index | Đối chiếu `getStackTrace()[depth]` |
| Bỏ kiểm `isObjectMonitorUsageSupported` | Có thể bị UnsupportedOperationException | Capability detection |
| Bỏ kiểm `isSynchronizerUsageSupported` | Có thể bị UnsupportedOperationException | Capability detection |
| Không check ThreadInfo null | Thread kết thúc/virtual/nonexistent | Bỏ qua hoặc resnapshot |
| Coi dumpAllThreads gồm virtual threads | ThreadMXBean chỉ platform threads | Dùng jcmd/JFR virtual diagnostics |
| Coi đọc snapshot là synchronization control | Race và stale information | Không điều khiển lock logic từ snapshot |
| Dùng `Thread.getId()` trong code Java 21+ mới | Deprecated từ Java 19 | Dùng final `threadId()` |
| Bật thread contention monitoring mọi lúc | Có overhead | Chỉ bật khi phù hợp và runtime hỗ trợ |
| Coi `findDeadlockedThreads()==null` là không có vấn đề | Không bao trùm non-ownable/I/O/virtual | JFR/stack/DB logs |
| Thấy `Thread.State.RUNNABLE` là đang dùng CPU | Có thể native/I/O | Kết hợp CPU/JFR/tracing |
| Gửi dump qua public API | Lộ stack/nội bộ | AuthN/AuthZ, encryption, retention |
| In hàng nghìn lock identities liên tục | High-cardinality logs | Sampling/aggregation/incident capture |
| Quên release latch trong test | Treo JVM | finally + countDown + join |
| Dùng `Thread.stop()` để thoát deadlock | Deprecated/unsafe | Thiết kế cancellation/interruptible locks |

## 18. Tự kiểm tra kiến thức

1. **`getLockedMonitors()` trả kiểu nào?** `MonitorInfo[]`.
2. **`getLockedSynchronizers()` trả kiểu nào?** `LockInfo[]`.
3. **Hai methods thuộc class nào?** `java.lang.management.ThreadInfo`.
4. **Lấy ThreadInfo với cả hai mảng populated?** `ThreadMXBean.getThreadInfo(ids,true,true)` sau khi kiểm support.
5. **Lấy ThreadMXBean bằng gì?** `ManagementFactory.getThreadMXBean()`.
6. **MonitorInfo kế thừa lớp nào?** `LockInfo`.
7. **MonitorInfo thêm gì?** `getLockedStackDepth` và `getLockedStackFrame`.
8. **LockedStackDepth là gì?** Chỉ số của acquisition frame trong `getStackTrace()`.
9. **Depth âm có ý nghĩa gì?** Frame acquisition không có sẵn.
10. **Có thể gọi getLockedStackFrame trên ReentrantLock LockInfo không?** Không.
11. **LockInfo mô tả những field chính nào?** ClassName và identityHashCode.
12. **Danh sách synchronizers có bao gồm mọi semaphore permit?** Không.
13. **ReentrantReadWriteLock read lock có phải ownable exclusive không?** Không.
14. **Thread ở WAITING có thể giữ monitor không?** Có.
15. **Object.wait nhả monitor nào?** Monitor mà nó gọi wait đúng trên object ấy.
16. **CountDownLatch.await trong synchronized có tự nhả monitor bao ngoài không?** Không.
17. **BLOCKED thường là gì?** Chờ monitor entry.
18. **ReentrantLock.lock có nhất thiết cho thread state BLOCKED không?** Không, thường dùng park.
19. **getLockInfo mô tả sở hữu hay đang chờ?** Khóa/blocker mà thread đang chờ.
20. **getLockOwnerId là gì khi không biết chủ?** -1.
21. **Snapshot có thể null ở trường hợp nào?** Thread đã chết/nonexistent/virtual.
22. **getThreadInfo(id) có tự lấy owned-lock arrays không?** Không.
23. **dumpAllThreads(true,true) bao gồm virtual threads không?** Không.
24. **Tạo platform thread tường minh trên Java21+?** `Thread.ofPlatform()`.
25. **ID thread hiện hành Java21+?** `threadId()`.
26. **getId() được khuyến nghị cho code mới không?** Không, deprecated từ Java19.
27. **findMonitorDeadlockedThreads khác findDeadlockedThreads thế nào?** Monitor-only vs monitors+ownable synchronizers.
28. **Một deadlock qua database lock có được ThreadMXBean luôn phát hiện không?** Không.
29. **Có thể dùng stack snapshot làm audit log đầy đủ không?** Không.
30. **Acquisition stack của monitor và current stack có thể khác nhau không?** Có.
31. **Một thread đã nhả monitor trước snapshot có còn trong getLockedMonitors không?** Không.
32. **Có thể suy ra owner id bằng lock identity mà không thấy getLockOwnerId không?** Không được tự đoán.
33. **Tại sao cần capability flags?** Một số VM không hỗ trợ ownership tracking.
34. **Tại sao full thread dumps cần hạn chế?** Có chi phí và dữ liệu nhạy cảm.
35. **Dùng gì để điều tra virtual threads?** HotSpot jcmd thread dump/JFR và tools phù hợp.
36. **Một identityHashCode có là khóa duy nhất không?** Không, có thể va chạm.
37. **Nên lưu gì cùng dump để đối chiếu source?** Artifact build ID, JDK version, timestamp và context.
38. **Một monitor held khi owner đang WAITING trên latch có chặn thread khác không?** Có.
39. **Có nên dùng ThreadMXBean để quyết định lúc nào thread được phép acquire monitor không?** Không, đó là API quan sát.
40. **Khi thấy nhiều BLOCKED, bước tiếp?** Tìm lock info, owner, owners' locked monitors và stack acquisition, rồi đối chiếu metrics/traces.

## 19. Tài liệu chính thức vẫn còn áp dụng

- [Java SE 25 — ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html): snapshot các platform threads, flags lấy locked monitors/synchronizers, capability tests, maxDepth, deadlock detection và virtual-thread exclusion.
- [Java SE 25 — ThreadInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html): `getLockedMonitors/getLockedSynchronizers/getLockInfo/getLockOwnerId/getStackTrace`.
- [Java SE 25 — MonitorInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MonitorInfo.html): `getLockedStackDepth` và `getLockedStackFrame` liên hệ monitor acquisition tới stack.
- [Java SE 25 — LockInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/LockInfo.html): class name, identity hash và ownable synchronizers.
- [Java SE 25 — ManagementFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html): `getThreadMXBean()` của JVM.
- [Java SE 25 — Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): `threadId()` hiện hành, `Thread.ofPlatform()` và virtual threads.
- [Java SE 25 — AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html): contract bộ đồng bộ sở hữu độc quyền.
- [Java SE 25 — ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock/unlock và điều kiện ownership.
- [Java SE 25 — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): read/write locking model.
- [Java SE 25 — jcmd command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `Thread.dump_to_file` với format plain hoặc json.
- [Oracle Java SE 25 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/25/jfapi/): API/JFR overview cho thread/lock telemetry.
- [Oracle Java SE 25 — Virtual Threads](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html): virtual-thread diagnostics, JFR và thread dumps.

**Kết luận:** `ThreadInfo.getLockedMonitors()` cho biết **monitors đang giữ** và, qua `MonitorInfo`, **stack frame nơi monitor được acquire**. `getLockedSynchronizers()` cho biết **ownable synchronizers đang giữ**, nhưng `LockInfo` **không lưu acquisition stack**; chỉ có class/identity. `getLockInfo/getLockOwnerId` mô tả điều **đang đợi**, không phải điều đang giữ. Phải thu snapshot bằng overload `getThreadInfo(ids,true,true)` sau capability checks, đọc cả owner và contender, xử lý null/-1, chú ý current stack khác acquisition frame và không dùng snapshots làm synchronization control. Đặc biệt ở Java 21+, **ThreadMXBean không bao gồm virtual threads**, nên quan sát concurrency hiện đại cần kết hợp JFR/jcmd và application traces.