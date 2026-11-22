# dumpAllThreads với monitor, synchronizer

## 1. Mục tiêu: đọc trạng thái khóa đang diễn ra trong JVM

Khi một ứng dụng Java chạy nhiều luồng, tình huống treo hoặc chậm có thể liên quan tới hai kiểu đồng bộ thường gặp: **object monitor** của `synchronized` và **ownable synchronizer** như `ReentrantLock`. Quan sát stack trace đơn thuần đôi khi chưa đủ: ta cần biết **luồng nào đang giữ khóa**, luồng nào **đang đợi khóa**, loại khóa nào và mã nguồn đang giữ monitor tại stack frame nào.

Java Management API cung cấp **`java.lang.management.ThreadMXBean.dumpAllThreads(boolean lockedMonitors, boolean lockedSynchronizers)`** để lấy thông tin về các **platform threads** còn sống, gồm stack traces và thông tin đồng bộ khi JVM hỗ trợ. Overload này có từ **Java 6 (Since 1.6)** và **vẫn hiện hành trong Java SE 26**. API `ThreadMXBean` nói chung có từ Java 5, còn overload ba tham số giới hạn độ sâu stack trace là bổ sung từ **Java 10**.

**Giới hạn cực kỳ quan trọng trên Java hiện đại:** `ThreadMXBean` **không quản lý virtual threads**. Từ Java 21, những virtual threads đang chạy **không xuất hiện** trong `dumpAllThreads(...)` hay `getAllThreadIds()`; `getThreadInfo(virtualThreadId)` trả `null`. Điều này không có nghĩa virtual thread đã chết hoặc ứng dụng không có contention. Để thu thập dumps gồm cả virtual threads, có thể dùng công cụ phù hợp của JDK như **`jcmd <pid> Thread.dump_to_file ...`**, với quyền truy cập và giới hạn chi phí được kiểm soát.

Bài tập trung vào **cách dùng API hiện hành** để chẩn đoán, không dựa trên các kỹ thuật điều khiển luồng không an toàn hay đã lỗi thời. Không dùng thread dump làm một thuật toán đồng bộ, không cố tình giữ application locks trong production chỉ để lấy snapshot.

### Sau bài này bạn có thể

1. Lấy `ThreadMXBean` từ `ManagementFactory.getThreadMXBean()`.
2. Phân biệt `dumpAllThreads(false,false)`, `dumpAllThreads(true,true)` và biến thể `dumpAllThreads(...,maxDepth)`.
3. Kiểm tra `isObjectMonitorUsageSupported()` và `isSynchronizerUsageSupported()` **trước** khi yêu cầu lock details.
4. Phân biệt **monitor** (`synchronized`) với **ownable synchronizer** (`ReentrantLock`, write lock của `ReentrantReadWriteLock`).
5. Đọc `ThreadInfo`: `getThreadId`, `getThreadName`, `getThreadState`, `getLockInfo`, `getLockOwnerId`, `getStackTrace`.
6. Đọc `MonitorInfo`: monitor class/identity, `getLockedStackDepth`, `getLockedStackFrame`.
7. Đọc `LockInfo[]` từ `getLockedSynchronizers()` và hiểu giới hạn của thông tin sở hữu khóa.
8. Nhận diện khác biệt **luồng đang giữ khóa** với luồng **đang chờ khóa**.
9. So sánh API `getThreadInfo(ids, flags)`, `dumpAllThreads`, `findDeadlockedThreads` và các công cụ `jcmd`/JFR.
10. Chạy **hai chương trình runnable** đã kiểm thử: Java 17+ với platform threads và Java 21+ với virtual thread scope.
11. Thiết kế diagnostics an toàn: lấy snapshot có giới hạn, không leak stack traces/secrets, không dump liên tục ở production.

~~~text
             ThreadMXBean (platform threads)
                         |
            dumpAllThreads(true, true)
                         |
      +------------------+--------------------+
      |                  |                    |
 ThreadInfo owner    ThreadInfo blocked    ThreadInfo waiting
      |                  |                    |
 getLockedMonitors  getLockInfo()          getLockInfo()
      |                  |                    |
 getLockedSynchronizers getLockOwnerId()  getLockOwnerId()
      |                  |                    |
 monitor/sync owner      +---------+----------+
      |                            |
      +----------------------------+
                 lock owner relationship

 Lưu ý: virtual threads KHÔNG thuộc tập ThreadMXBean.dumpAllThreads
~~~

## 2. ThreadMXBean và overload dumpAllThreads

### 2.1. Lấy ThreadMXBean

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean mx = ManagementFactory.getThreadMXBean();
~~~

Đây là **đoạn trích**, không phải một file có `main`. `ManagementFactory.getThreadMXBean()` trả platform MXBean của JVM hiện tại. Các thuộc tính của thread management có thể được truy cập qua **platform MBeanServer** với ObjectName `java.lang:type=Threading`, nhưng không cần mở JMX remote connector để gọi API local.

### 2.2. Hai boolean có ý nghĩa chính xác

~~~java
ThreadInfo[] infos = mx.dumpAllThreads(
        true,  // lockedMonitors: lấy các object monitors luồng đang giữ
        true   // lockedSynchronizers: lấy các ownable synchronizers đang giữ
);
~~~

`true` không có nghĩa “liệt kê các luồng đang deadlock”, “tìm mọi loại khóa trong hệ thống” hay “bật thread contention monitoring”. Nó chỉ yêu cầu trả **thông tin monitors và ownable synchronizers đã khóa** trong `ThreadInfo` của các platform threads.

| Lời gọi | Stack trace | Monitors luồng đang giữ | Ownable synchronizers luồng đang giữ |
| --- | --- | --- | --- |
| `dumpAllThreads(false,false)` | Có, toàn bộ stack theo overload 2 args | Không đưa vào kết quả | Không đưa vào kết quả |
| `dumpAllThreads(true,false)` | Có | Có, nếu JVM hỗ trợ | Không |
| `dumpAllThreads(false,true)` | Có | Không | Có, nếu JVM hỗ trợ |
| `dumpAllThreads(true,true)` | Có | Có, nếu JVM hỗ trợ | Có, nếu JVM hỗ trợ |
| `dumpAllThreads(m,s,5)` | Có, tối đa 5 frames/thread | Theo m và khả năng JVM | Theo s và khả năng JVM |
| `dumpAllThreads(false,false,0)` | Không lấy stack frames | Không | Không |

**Đừng suy từ mảng rỗng rằng không có contention.** Nếu gọi `dumpAllThreads(false,false)` thì `ThreadInfo.getLockedMonitors()` và `getLockedSynchronizers()` trả mảng rỗng **theo yêu cầu của bạn**, ngay cả khi luồng đang giữ khóa.

### 2.3. Query khả năng trước khi bật flags

~~~java
boolean monitors = mx.isObjectMonitorUsageSupported();
boolean synchronizers = mx.isSynchronizerUsageSupported();

ThreadInfo[] snapshot = mx.dumpAllThreads(
        monitors, synchronizers);
~~~

Đây là **đoạn trích**. Cách này chọn mức độ dữ liệu mà JVM thật sự hỗ trợ. Nếu bạn gọi `dumpAllThreads(true,false)` khi monitor usage **không** được hỗ trợ, hoặc `dumpAllThreads(false,true)` khi ownable synchronizer usage không được hỗ trợ, Javadoc quy định **`UnsupportedOperationException`**.

Một ứng dụng diagnostic có thể:
- Ghi metadata **monitorSupported/synchronizerSupported**.
- Với capability không có, **không khẳng định “0 locks”** mà báo “không hỗ trợ quan sát”.
- Nếu cần policy bắt buộc phải có thông tin khóa, **fail rõ**, không che lỗi.
- Không tự bật flags rồi bắt mọi exception bằng `catch(Exception ignored)`, vì sẽ che lấp vấn đề môi trường.

### 2.4. Khác biệt với contention monitoring

`ThreadMXBean.isThreadContentionMonitoringSupported()` và `isThreadContentionMonitoringEnabled()` dùng cho **thời gian blocked/waited**. Chúng **không phải điều kiện tiên quyết** để lấy `getLockedMonitors()`/`getLockedSynchronizers()` bằng dumpAllThreads.

| Nhóm tính năng | API liên quan | Ý nghĩa |
| --- | --- | --- |
| Monitor ownership | `isObjectMonitorUsageSupported()` | Có thể lấy object monitors do threads giữ |
| Synchronizer ownership | `isSynchronizerUsageSupported()` | Có thể lấy ownable synchronizers do threads giữ |
| Contention durations | `isThreadContentionMonitoringSupported()` / `isThreadContentionMonitoringEnabled()` | Có thể đo thời gian blocked/waited |
| CPU accounting | `isThreadCpuTimeSupported()` / `isThreadCpuTimeEnabled()` | CPU time, **không phải lock ownership** |
| Deadlock cycles | `findMonitorDeadlockedThreads()` / `findDeadlockedThreads()` | Phát hiện chu trình deadlock platform threads theo loại khóa |

Không nên gọi `setThreadContentionMonitoringEnabled(true)` chỉ để dump locks. Việc bật đo contention có thể có overhead và phải được quyết định theo nhu cầu quan sát của hệ thống.

### 2.5. Overload maxDepth từ Java 10

~~~java
ThreadInfo[] bounded = mx.dumpAllThreads(
        monitors, synchronizers, 8);
~~~

`maxDepth` là số **stack trace elements tối đa của mỗi thread**, không phải số thread tối đa. `maxDepth=0` cho stack rỗng; số âm gây `IllegalArgumentException`. Overload này vẫn trả thông tin monitor/synchronizer theo flags, nhưng stack frame tương ứng của một monitor có thể không nằm trong phần stack bị cắt nên không phải lúc nào cũng xác định được location chi tiết.

Nếu làm tool với Java 17+, nên sử dụng `maxDepth` để hạn chế output và memory khi không cần toàn bộ stack. Nếu cần xác định chính xác đoạn code giữ monitor, lấy stack depth đủ lớn và hiểu snapshot không phải một event log đầy đủ.

## 3. Object monitor: khóa của synchronized

### 3.1. Cơ chế monitor

Mỗi object Java có thể đóng vai trò **intrinsic monitor** cho `synchronized`:

~~~java
Object monitor = new Object();

synchronized (monitor) {
    // Luồng hiện tại giữ intrinsic monitor của object.
    doWork();
}
~~~

Đây là đoạn trích; `doWork()` là phương thức do ứng dụng định nghĩa. Nếu luồng A giữ monitor và luồng B muốn vào cùng synchronized block, B có thể ở **Thread.State.BLOCKED** cho đến khi A nhả monitor.

### 3.2. MonitorInfo mô tả khóa đang giữ

`ThreadInfo.getLockedMonitors()` trả mảng `MonitorInfo[]`. Một phần tử cung cấp:
- `getClassName()`: tên Java class của monitor object;
- `getIdentityHashCode()`: `System.identityHashCode` của object;
- `getLockedStackDepth()`: chỉ số frame trong `ThreadInfo.getStackTrace()` nơi monitor được lấy, hoặc số âm khi không biết;
- `getLockedStackFrame()`: `StackTraceElement` tại vị trí lấy monitor, có thể là `null` khi không biết.

~~~java
for (MonitorInfo monitorInfo : threadInfo.getLockedMonitors()) {
    System.out.println(monitorInfo.getClassName());
    System.out.println(monitorInfo.getIdentityHashCode());
    System.out.println(monitorInfo.getLockedStackDepth());
    System.out.println(monitorInfo.getLockedStackFrame());
}
~~~

**Đoạn trích**, `threadInfo` có từ một snapshot đã yêu cầu lockedMonitors=true. Một `getLockedStackDepth()` hợp lệ là **index** (thường 0-based) vào stack trace được trả; **không phải depth của Java synchronized nesting** hay số lần reentrant acquisition. Nếu depth âm hoặc frame null thì thông tin frame không có sẵn.

### 3.3. Theo dõi luồng đang bị chặn vì monitor

Một luồng **đang đợi lấy** monitor được mô tả bằng:
- `getThreadState()==Thread.State.BLOCKED` trong trường hợp chờ vào synchronized block;
- `getLockInfo()` / `getLockName()`: đối tượng khóa mà luồng đang chờ;
- `getLockOwnerId()` và `getLockOwnerName()` nếu JVM biết luồng đang giữ monitor.

**Khác nhau quan trọng:**
- `ownerInfo.getLockedMonitors()`: các monitors **owner đang nắm giữ**.
- `blockedInfo.getLockInfo()`: monitor **blocked thread đang đợi**, không phải monitor nó đã sở hữu.

Không lấy mảng `blockedInfo.getLockedMonitors()` để suy rằng blocked thread không bị monitor chặn; nó có thể đang chờ một monitor mà thread khác nắm giữ.

### 3.4. BLOCKED khác WAITING

- `BLOCKED`: thường là **chờ vào/re-enter intrinsic monitor**.
- `WAITING` hoặc `TIMED_WAITING`: có thể do `Object.wait`, `Thread.join`, `LockSupport.park`, `Condition.await` hoặc chờ trong concurrency utilities.
- Một thread gọi `Object.wait()` **thả monitor đó khi đợi**, sau đó cần re-acquire trước khi tiếp tục.
- Chờ `ReentrantLock.lock()` thường liên quan `LockSupport.park` và có thể biểu hiện `WAITING` thay vì `BLOCKED`.

Vì vậy không phải mọi thread trong WAITING đều deadlocked, và không phải mọi BLOCKED kéo dài đều deadlocked. Cần quan sát lock owners, stacks, thời gian, tiến độ và nhiều snapshots.

## 4. Ownable synchronizer: khóa quản lý bởi java.util.concurrent

### 4.1. Khái niệm ownable synchronizer

**Ownable synchronizer** được định nghĩa dựa trên `AbstractOwnableSynchronizer` (hoặc subclass), có thể ghi nhận **một owner thread** khi khóa độc quyền. Ví dụ phổ biến:
- `ReentrantLock`;
- **write lock** của `ReentrantReadWriteLock`.

Không phải tất cả `java.util.concurrent` locks và mọi đối tượng đồng bộ đều có owner quan sát được theo API này. **Read lock của `ReentrantReadWriteLock`** không được coi là ownable synchronizer theo contract tương ứng. `Semaphore`/`CountDownLatch` không phải “một khóa có một owner” theo cùng nghĩa; không mong `getLockedSynchronizers()` liệt kê tất cả resources đang làm thread chờ.

### 4.2. ReentrantLock ví dụ

~~~java
ReentrantLock lock = new ReentrantLock();

lock.lock();
try {
    // Luồng này đang giữ exclusive lock.
    process();
} finally {
    lock.unlock();
}
~~~

**Đoạn trích**, cần import `java.util.concurrent.locks.ReentrantLock`, `process()` do bạn định nghĩa. `finally` rất quan trọng: nếu quên unlock sau exception, các threads khác có thể đợi mãi.

### 4.3. LockInfo cho ownable synchronizer

`ThreadInfo.getLockedSynchronizers()` trả **`LockInfo[]`**: các synchronizers mà thread **đang giữ** lúc snapshot. `LockInfo` cung cấp:
- `getClassName()`;
- `getIdentityHashCode()`;
- `toString()` với dạng thường thấy `className@hexIdentity`.

Với `ReentrantLock`, class nhận được có thể là implementation nội bộ như `java.util.concurrent.locks.ReentrantLock$NonfairSync` hoặc `FairSync` — **không nhất thiết là `java.util.concurrent.locks.ReentrantLock`**. Đừng hardcode class name nội bộ làm một hợp đồng API bền vững giữa các JDK/vendors.

~~~java
for (LockInfo locked : info.getLockedSynchronizers()) {
    System.out.println(locked.getClassName());
    System.out.println(locked.getIdentityHashCode());
}
~~~

**Đoạn trích**, `info` là `ThreadInfo` có lockedSynchronizers=true và JVM hỗ trợ. `getIdentityHashCode()` **không phải địa chỉ memory** và có thể trùng giữa các object; nó hữu ích để correlate các snapshot với class name/owner/state nhưng **không** dùng làm security token hoặc unique global ID.

### 4.4. Ownable synchronizer mà thread đang đợi

Luồng cố `lock.lock()` khi người khác giữ `ReentrantLock` có thể:
- nằm trong `WAITING`;
- `getLockInfo()` chỉ object synchronizer nó đang đợi;
- `getLockOwnerId()` trỏ tới owner (nếu có thể xác định).

Cùng lúc, **owner** có thể có synchronizer đó trong `getLockedSynchronizers()`. Khi phân tích, ghép **waiting lock identity/owner** với **held lock info của owner**, không chỉ nhìn một thread riêng lẻ.

### 4.5. Lock info không phải mọi trạng thái đồng bộ

API không cung cấp một đồ thị đầy đủ cho:
- tất cả read locks;
- mọi `StampedLock` ownership/stamp;
- condition predicates;
- application-level semaphores/queues;
- database locks;
- filesystem/distributed locks.

Một dump không cho biết “luồng này chắc chắn đang chờ DB transaction X” nếu không có application traces bổ sung. Thông tin Java lock ownership là **một lát cắt**, không phải event stream.

## 5. ThreadInfo: cấu trúc của một snapshot

`java.lang.management.ThreadInfo` chứa những dữ liệu phổ biến:

| Method | Diễn giải |
| --- | --- |
| `getThreadId()` | JVM thread ID của platform thread tại snapshot |
| `getThreadName()` | Tên thread, cần tránh chứa PII |
| `getThreadState()` | `RUNNABLE/BLOCKED/WAITING/TIMED_WAITING/...` |
| `getStackTrace()` | Stack trace tại thời điểm thu thập |
| `getLockInfo()` | Lock đang đợi nếu biết |
| `getLockName()` | Biểu diễn chuỗi của lock đang đợi |
| `getLockOwnerId()` | ID owner, `-1` nếu không xác định |
| `getLockOwnerName()` | Tên owner khi xác định |
| `getLockedMonitors()` | MonitorInfo[] các monitors đã yêu cầu |
| `getLockedSynchronizers()` | LockInfo[] các ownable synchronizers đã yêu cầu |
| `getBlockedCount()` | Số lần bị chặn khi enter/reenter monitor |
| `getBlockedTime()` | Thời gian blocked nếu contention monitoring có hỗ trợ/bật |
| `getWaitedCount()` | Số lần wait |
| `getWaitedTime()` | Thời gian waited theo contention monitoring |

### 5.1. Snapshot không phải chân lý bất biến

Trong khi JVM tạo `ThreadInfo[]`, threads vẫn có thể:
- thoát khỏi synchronized block;
- được đánh thức;
- lấy/nhả `ReentrantLock`;
- kết thúc;
- đổi state.

Vì vậy **không coi toàn bộ mảng là một transaction nhất quán được đông cứng tại cùng một nanosecond**. `ThreadInfo` đại diện một snapshot để chẩn đoán. Không dùng `getLockOwnerId()` để tự quyết định interrupt/kill một thread hoặc sửa đồng bộ của chương trình dựa trên snapshot có thể đã cũ.

### 5.2. Tránh hiểu sai blocked/waited time

`getBlockedTime()` và `getWaitedTime()` có thể trả **`-1`** nếu contention monitoring không bật/không hỗ trợ hoặc thời gian chưa có. Không biến `-1` thành “-1 ms” trong dashboard hoặc kết luận không contention. Đây là nhóm metrics riêng với `dumpAllThreads(true,true)`.

### 5.3. Null và kết quả thiếu

- `getThreadInfo(id)` trả `null` khi thread không tồn tại, đã chết hoặc là virtual thread.
- `getThreadInfo(long[] ids,...)` bảo toàn vị trí trong array nhưng mỗi slot có thể `null`.
- `dumpAllThreads(...)` chỉ chứa **live platform threads** đã quan sát; một thread vừa kết thúc có thể không còn.
- Không có `ThreadInfo` không phải bằng chứng task chưa từng chạy.
- `getLockOwnerId()==-1` có nghĩa owner không được xác định, không có nghĩa chắc chắn không có owner.

### 5.4. Thread ID không phải một vĩnh viễn

Thread ID có ý nghĩa trong vòng đời thread/JVM, không phải một system-wide stable business identifier. Đối với log correlation, kết hợp thread name, process identity, thời điểm snapshot, application task correlation context khi an toàn; không dựa trên ID duy nhất xuyên nhiều JVMs.

## 6. Quy trình lấy thread dump có kiểm soát

### 6.1. Thu thập tối thiểu đủ dùng

~~~java
ThreadMXBean mx = ManagementFactory.getThreadMXBean();
boolean monitors = mx.isObjectMonitorUsageSupported();
boolean synchronizers = mx.isSynchronizerUsageSupported();

ThreadInfo[] snapshot = mx.dumpAllThreads(
        monitors, synchronizers, 16);

for (ThreadInfo info : snapshot) {
    if (info == null) continue;
    System.out.printf(
        "name=%s state=%s blockedOn=%s owner=%d monitors=%d syncs=%d%n",
        info.getThreadName(), info.getThreadState(),
        info.getLockInfo(), info.getLockOwnerId(),
        info.getLockedMonitors().length,
        info.getLockedSynchronizers().length);
}
~~~

Đây là **đoạn trích**, Java 17+, không phải chương trình chạy đầy đủ. Hạn chế `maxDepth` và chọn thời điểm/cadence phù hợp. Ngay cả khi không in toàn bộ stack, việc yêu cầu lock details trên nhiều threads vẫn có chi phí.

### 6.2. Chỉ theo dõi một nhóm threads

Nếu biết IDs của các platform threads cần điều tra, có thể chọn:

~~~java
long[] ids = {threadA.getId(), threadB.getId()};
ThreadInfo[] selected = mx.getThreadInfo(
        ids, monitors, synchronizers);
~~~

**Đoạn trích**, yêu cầu Java 6+; `threadA/threadB` là các Thread được bạn xác định. Cần xử lý `null` ở từng vị trí. Các overload có `maxDepth` cho thread IDs có từ Java 10+; dùng khi cần hạn chế stack.

### 6.3. getAllThreadIds rồi getThreadInfo có phải atomic?

Không. Khi bạn gọi:

~~~java
long[] ids = mx.getAllThreadIds();
ThreadInfo[] selected = mx.getThreadInfo(ids, monitors, synchronizers);
~~~

**Đoạn trích**. Threads có thể kết thúc giữa hai lời gọi; kết quả theo ID có thể chứa `null`. `dumpAllThreads` tiện hơn khi muốn **một lần gọi** để lấy toàn bộ live platform threads với lock details. Không cần lấy IDs rồi lookup từng thread riêng lẻ khi đã có `dumpAllThreads`.

### 6.4. Chọn độ sâu và frequency

- Trường hợp quan sát health định kỳ: ưu tiên counters/metrics rẻ; không dump stack của mọi thread mỗi giây.
- Khi nhận sự cố blocked/waited lâu: lấy 1–3 snapshots có khoảng cách và correlation context an toàn.
- Với production có hàng ngàn threads, cân nhắc `maxDepth`, output quotas và rate limiting.
- Dump đầy đủ có thể tạo allocation/stop-the-world-ish overhead tùy implementation, không nên khẳng định “chi phí luôn thấp”.
- Chỉ người có quyền quản trị được phép kích hoạt, xem và lưu diagnostics.

## 7. Java 17+ runnable: monitor và ReentrantLock trong cùng snapshot

Chương trình `ThreadDumpLocksDemo.java` tạo **ba platform threads** với trạng thái có thể tái tạo:

1. `demo-owner` vào `synchronized (MONITOR)`, sau đó lấy `ReentrantLock` và chờ một `CountDownLatch`.
2. `demo-monitor-waiter` cố vào cùng monitor: bị **BLOCKED**.
3. `demo-synchronizer-waiter` cố lấy ReentrantLock của owner: chờ qua synchronizer, thường ở **WAITING**.
4. Main đợi hai waiters đi vào state dự kiến (tối đa 5 giây).
5. `dumpAllThreads(monitorSupported,synchronizerSupported)` thu snapshots.
6. Dùng `MonitorInfo` và `System.identityHashCode(MONITOR)` để xác nhận owner đang giữ monitor.
7. Dùng `LockInfo` và class name chứa `ReentrantLock` để nhận diện ownable synchronizer thuộc owner.
8. Dùng `getLockOwnerId()` của hai waiters để kiểm chứng cả hai đang đợi cùng thread owner.
9. Gọi `dumpAllThreads(false,false)` xác nhận locked arrays **rỗng vì flags tắt**.
10. Gọi `dumpAllThreads(false,false,5)` kiểm tra giới hạn stack depth.
11. Gọi `getThreadInfo(ids,flags)` để lấy targeted ThreadInfo.
12. `finally` nhả latch, join đủ ba threads và kiểm tra không còn workers.

Đây là bài lab an toàn **không tạo deadlock vĩnh viễn**: owner được nhả trong finally. Trên JVM khác capability flags có thể false; bài vẫn lấy snapshot theo khả năng được báo, **không báo zero locks khi chức năng không hỗ trợ**. Xuất hiện `monitor-supported=true` và `synchronizer-supported=true` là kết quả **cụ thể trên OpenJDK 24 đã kiểm thử**, không phải lời hứa cho mọi provider/JVM.

### 7.1. File ThreadDumpLocksDemo.java

~~~java
import java.lang.management.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.ReentrantLock;

public final class ThreadDumpLocksDemo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock EXCLUSIVE_LOCK = new ReentrantLock();
    private static final CountDownLatch OWNER_READY = new CountDownLatch(1);
    private static final CountDownLatch RELEASE_OWNER = new CountDownLatch(1);
    private static final AtomicReference<Throwable> WORKER_FAILURE = new AtomicReference<>();

    static void check(boolean okay, String message) {
        if (!okay) throw new AssertionError(message);
    }

    static void waitForState(Thread thread, Set<Thread.State> expected) throws Exception {
        long end = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < end && !expected.contains(thread.getState())) {
            Thread.sleep(10);
        }
        check(expected.contains(thread.getState()),
                thread.getName() + " was " + thread.getState());
    }

    static ThreadInfo find(ThreadInfo[] infos, long threadId) {
        for (ThreadInfo info : infos) {
            if (info != null && info.getThreadId() == threadId) return info;
        }
        return null;
    }

    static boolean containsMonitor(ThreadInfo info) {
        return Arrays.stream(info.getLockedMonitors())
                .anyMatch(m -> m.getClassName().equals(Object.class.getName())
                        && m.getIdentityHashCode() == System.identityHashCode(MONITOR)
                        && m.getLockedStackDepth() >= 0
                        && m.getLockedStackFrame() != null);
    }

    static boolean containsSynchronizer(ThreadInfo info) {
        return Arrays.stream(info.getLockedSynchronizers())
                .anyMatch(s -> s.getClassName().contains("ReentrantLock"));
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        boolean monitors = mx.isObjectMonitorUsageSupported();
        boolean synchronizers = mx.isSynchronizerUsageSupported();

        Thread owner = new Thread(() -> {
            try {
                synchronized (MONITOR) {
                    EXCLUSIVE_LOCK.lock();
                    try {
                        OWNER_READY.countDown();
                        RELEASE_OWNER.await();
                    } finally {
                        EXCLUSIVE_LOCK.unlock();
                    }
                }
            } catch (Throwable error) {
                WORKER_FAILURE.compareAndSet(null, error);
            }
        }, "demo-owner");

        Thread monitorWaiter = new Thread(() -> {
            try {
                synchronized (MONITOR) { /* Acquired after owner releases */ }
            } catch (Throwable error) {
                WORKER_FAILURE.compareAndSet(null, error);
            }
        }, "demo-monitor-waiter");

        Thread synchronizerWaiter = new Thread(() -> {
            try {
                EXCLUSIVE_LOCK.lock();
                try { /* Acquired after owner releases */ }
                finally { EXCLUSIVE_LOCK.unlock(); }
            } catch (Throwable error) {
                WORKER_FAILURE.compareAndSet(null, error);
            }
        }, "demo-synchronizer-waiter");

        owner.start();
        try {
            check(OWNER_READY.await(5, TimeUnit.SECONDS), "owner was not ready");
            monitorWaiter.start();
            synchronizerWaiter.start();
            waitForState(monitorWaiter, Set.of(Thread.State.BLOCKED));
            waitForState(synchronizerWaiter, Set.of(
                    Thread.State.WAITING, Thread.State.TIMED_WAITING));

            ThreadInfo[] full = mx.dumpAllThreads(monitors, synchronizers);
            ThreadInfo owned = find(full, owner.getId());
            ThreadInfo blocked = find(full, monitorWaiter.getId());
            ThreadInfo queued = find(full, synchronizerWaiter.getId());
            check(owned != null && blocked != null && queued != null,
                    "platform threads absent");
            check(blocked.getThreadState() == Thread.State.BLOCKED,
                    "monitor waiter not BLOCKED");
            check(blocked.getLockInfo() != null
                            && blocked.getLockInfo().getIdentityHashCode()
                                == System.identityHashCode(MONITOR),
                    "monitor wait target identity");
            check(blocked.getLockOwnerId() == owner.getId(),
                    "monitor owning thread id");
            check(queued.getLockOwnerId() == owner.getId(),
                    "synchronizer owning thread id");

            boolean lockedMonitorFound = monitors && containsMonitor(owned);
            boolean lockedSyncFound = synchronizers && containsSynchronizer(owned);
            if (monitors) check(lockedMonitorFound, "monitor not found");
            if (synchronizers) check(lockedSyncFound, "synchronizer not found");

            ThreadInfo basic = find(mx.dumpAllThreads(false, false), owner.getId());
            check(basic != null && basic.getLockedMonitors().length == 0
                    && basic.getLockedSynchronizers().length == 0,
                    "disabled flags must omit owned locks");

            ThreadInfo bounded = find(
                    mx.dumpAllThreads(false, false, 5), owner.getId());
            check(bounded != null && bounded.getStackTrace().length <= 5,
                    "bounded depth");
            ThreadInfo byId = mx.getThreadInfo(
                    new long[] {owner.getId()}, monitors, synchronizers)[0];
            check(byId != null && byId.getThreadId() == owner.getId(),
                    "targeted lookup");

            System.out.println("monitor-supported=" + monitors);
            System.out.println("synchronizer-supported=" + synchronizers);
            System.out.println("owner-in-dump=true");
            System.out.println("monitor-owner-id-matches=true");
            System.out.println("monitor-waiter-state=BLOCKED");
            System.out.println("synchronizer-owner-id-matches=true");
            System.out.println("owned-monitor-reported=" + lockedMonitorFound);
            System.out.println("owned-synchronizer-reported=" + lockedSyncFound);
            System.out.println("disabled-flags-empty=true");
            System.out.println("bounded-stack-depth=true");
            System.out.println("targeted-thread-lookup=true");
        } finally {
            RELEASE_OWNER.countDown();
            owner.join(5000);
            if (monitorWaiter.isAlive()) monitorWaiter.join(5000);
            if (synchronizerWaiter.isAlive()) synchronizerWaiter.join(5000);
            check(!owner.isAlive() && !monitorWaiter.isAlive()
                    && !synchronizerWaiter.isAlive(), "worker threads still alive");
        }
        check(WORKER_FAILURE.get() == null, "worker error: " + WORKER_FAILURE.get());
        System.out.println("workers-finished=true");
        System.out.println("tests=PASS");
    }
}
~~~

### 7.2. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 17 ThreadDumpLocksDemo.java
java ThreadDumpLocksDemo
~~~

**Stdout thực tế** đã xác nhận khi chạy trên OpenJDK 24 với target Java 17:

~~~text
monitor-supported=true
synchronizer-supported=true
owner-in-dump=true
monitor-owner-id-matches=true
monitor-waiter-state=BLOCKED
synchronizer-owner-id-matches=true
owned-monitor-reported=true
owned-synchronizer-reported=true
disabled-flags-empty=true
bounded-stack-depth=true
targeted-thread-lookup=true
workers-finished=true
tests=PASS
~~~

### 7.3. Phân tích kết quả

- `monitor-supported=true` và `synchronizer-supported=true`: JVM test hỗ trợ quan sát cả hai.
- `owner-in-dump=true`: platform thread `demo-owner` xuất hiện trong snapshot.
- `monitor-owner-id-matches=true`: luồng chờ monitor nhận biết ID của thread đang giữ monitor.
- `monitor-waiter-state=BLOCKED`: thread đang chờ vào `synchronized`.
- `synchronizer-owner-id-matches=true`: thread đợi ReentrantLock cũng nhận biết cùng owner.
- `owned-monitor-reported=true`: `MonitorInfo[]` trên owner có object monitor đúng class/identityHashCode và stack frame khi có sẵn.
- `owned-synchronizer-reported=true`: `LockInfo[]` trên owner có ownable synchronizer của `ReentrantLock`.
- `disabled-flags-empty=true`: khi yêu cầu `false,false`, hai mảng ownership rỗng **theo yêu cầu**, dù lock thực tế vẫn đang bị giữ.
- `bounded-stack-depth=true`: overload ba tham số giới hạn frames ở 5/thread.
- `targeted-thread-lookup=true`: `getThreadInfo(ids, flags)` lấy đúng platform thread theo ID.
- `workers-finished=true`: nhả latch và join; bài test không để threads treo.
- `tests=PASS`: những assertions trong fixture đều đạt.

**Điều không nên kết luận:** Một lần `tests=PASS` không chứng minh mọi provider trả giống nhau, không chứng minh mọi app lock được ThreadMXBean quan sát, không chứng minh không có deadlock trong hệ thống khác. Đây là chương trình kiểm tra **cụ thể về platform-thread locks**.

### 7.4. Vì sao dùng latches để giữ trạng thái ổn định?

Nếu chạy các thread liên tục rồi dump khi ngẫu nhiên, owner có thể đã nhả khóa trước lúc lấy snapshot. Vì vậy bài test dùng:
- `OWNER_READY` để biết owner đã giữ cả monitor và ReentrantLock;
- `RELEASE_OWNER` để giữ owner trong vùng khóa cho tới khi main hoàn tất assertions;
- `waitForState` để đợi monitor-waiter vào BLOCKED và synchronizer-waiter vào WAITING;
- finally để nhả và cleanup kể cả khi một assertion thất bại.

Đây là thiết kế **deterministic test fixture**; không đưa cách cố tình giữ monitors lâu như vậy vào request-serving production code.

## 8. Virtual threads: giới hạn của ThreadMXBean trên Java 21+

### 8.1. Những gì API không hiển thị

Từ Java 21, virtual threads là tính năng chính thức. Tuy chúng cũng là `java.lang.Thread` và có `threadId()`, Javadoc Java SE 26 quy định `ThreadMXBean` **chỉ quản lý platform threads**. Cụ thể:

- `dumpAllThreads(false,false)`/`dumpAllThreads(true,true)` **không đưa virtual-thread IDs vào ThreadInfo[]**.
- `getAllThreadIds()` chỉ cho platform threads.
- `getThreadInfo(virtualThread.threadId())` trả `null` kể cả khi virtual thread đang sống.
- `getThreadCount()` đo live platform threads; **không phản ánh tổng số virtual threads đang chạy**.
- `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` không tìm các chu trình có virtual threads.

**Chú ý:** Việc không thấy virtual thread trong dump **không có nghĩa virtual thread không thể dùng `synchronized` hay `ReentrantLock`**. Đó là giới hạn của **management API**, không phải giới hạn chức năng đồng bộ của Java.

### 8.2. Java 21+ runnable: một platform, một virtual thread đều đang sống

Chương trình `VirtualThreadScopeDemo.java` mở:
- Một platform thread;
- Một virtual thread;
- Cả hai đang đợi cùng `CountDownLatch` để chắc chắn **chưa kết thúc** khi snapshot.

Sau đó kiểm tra `dumpAllThreads(false,false,5)` tìm thấy platform nhưng **không** thấy virtual; `getThreadInfo(virtual.threadId())` là `null`. Cuối cùng release latch và join cả hai.

**Không biên dịch chương trình này bằng `--release 17`**, vì `Thread.ofVirtual`/virtual threads là API chính thức từ **Java 21**. Chương trình mục 7 dùng `--release 17` độc lập.

### 8.3. File VirtualThreadScopeDemo.java

~~~java
import java.lang.management.*;
import java.util.*;
import java.util.concurrent.*;

public final class VirtualThreadScopeDemo {
    static void check(boolean okay, String message) {
        if (!okay) throw new AssertionError(message);
    }

    static boolean contains(ThreadInfo[] infos, long id) {
        return Arrays.stream(infos)
                .anyMatch(info -> info != null && info.getThreadId() == id);
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        Runnable task = () -> {
            ready.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };
        Thread platform = Thread.ofPlatform().name("test-platform").start(task);
        Thread virtual = Thread.ofVirtual().name("test-virtual").start(task);
        try {
            check(ready.await(5, TimeUnit.SECONDS), "threads not ready");
            check(platform.isAlive() && virtual.isAlive(), "threads not alive");
            ThreadInfo[] dump = mx.dumpAllThreads(false, false, 5);
            boolean platformVisible = contains(dump, platform.threadId());
            boolean virtualVisible = contains(dump, virtual.threadId());
            ThreadInfo virtualInfo = mx.getThreadInfo(virtual.threadId());
            boolean bounded = Arrays.stream(dump)
                    .allMatch(info -> info == null || info.getStackTrace().length <= 5);
            check(platformVisible, "missing platform thread");
            check(!virtualVisible, "virtual thread unexpectedly reported");
            check(virtualInfo == null, "getThreadInfo should omit virtual");
            check(bounded, "max depth exceeded");
            System.out.println("platform-visible=" + platformVisible);
            System.out.println("virtual-visible=" + virtualVisible);
            System.out.println("virtual-getThreadInfo-null=" + (virtualInfo == null));
            System.out.println("bounded-depth-at-most-5=" + bounded);
        } finally {
            release.countDown();
            platform.join(5000);
            virtual.join(5000);
            check(!platform.isAlive() && !virtual.isAlive(), "threads still alive");
        }
        System.out.println("workers-finished=true");
        System.out.println("tests=PASS");
    }
}
~~~

### 8.4. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 21 VirtualThreadScopeDemo.java
java VirtualThreadScopeDemo
~~~

**Stdout thực tế** trên OpenJDK 24 khi biên dịch target Java 21:

~~~text
platform-visible=true
virtual-visible=false
virtual-getThreadInfo-null=true
bounded-depth-at-most-5=true
workers-finished=true
tests=PASS
~~~

### 8.5. Giải thích ý nghĩa

- `platform-visible=true`: platform thread có trong dump.
- `virtual-visible=false`: virtual thread vẫn sống nhưng không được ThreadMXBean dump đưa vào.
- `virtual-getThreadInfo-null=true`: Javadoc quy định ThreadMXBean không cung cấp info về virtual thread ID.
- `bounded-depth-at-most-5=true`: `maxDepth=5` áp dụng trên ThreadInfo[] được trả cho platform threads.
- `workers-finished=true`: cả hai đã được thả latch và join sạch.
- `tests=PASS`: xác nhận ranh giới API, không phải phát hiện một thread đã chết.

Đây là ví dụ quan trọng cho các ứng dụng Java 21+ sử dụng `Executors.newVirtualThreadPerTaskExecutor()` hoặc structured concurrency. Đừng hiển thị `ThreadMXBean.getThreadCount()` với nhãn “total app threads including virtual threads”; metric đó sẽ bị hiểu sai.

## 9. JDK tools phù hợp khi cần xem cả virtual threads

### 9.1. jcmd Thread.dump_to_file (JDK hiện đại)

Với runtime đang chạy có PID và quyền diagnostics phù hợp:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json thread-dump.json
~~~

~~~bash
jcmd <pid> Thread.dump_to_file -format=plain thread-dump.txt
~~~

Đây là **lệnh minh họa**, thay `<pid>` bằng PID thực; chỉ chạy ở process bạn được phép quản lý. Theo tài liệu Java SE 26, lệnh này tạo dump vào file plain text hoặc JSON **gồm cả platform và virtual threads**. File JSON dành cho công cụ phân tích; không nên tự suy mọi fields của format sẽ bất biến giữa các JDK versions mà không có parser tests.

**Khác với ThreadMXBean:** lệnh thu thập chuyên dụng này có thể quan sát virtual threads, nhưng có những đặc tính riêng. Tài liệu Oracle nêu dump **không phải ảnh chụp nhất quán dừng toàn JVM**; nó thu thập các threads mà không stop-the-world, có timestamps và thông tin khóa theo format, nhưng **không tự thực hiện deadlock detection**. Vì vậy nó không phải “ThreadMXBean.dumpAllThreads với cùng semantics và thêm virtual threads”.

### 9.2. jcmd Thread.print

~~~bash
jcmd <pid> Thread.print -l
~~~

Trong Java SE 26, `Thread.print` trình bày platform threads và **mounted virtual threads**, tham số `-l` thêm thông tin `java.util.concurrent` locks. Không đồng nhất lệnh này với `Thread.dump_to_file` khi cần “toàn bộ virtual threads”, vì `Thread.print` có phạm vi khác về virtual threads. `Thread.dump_to_file` được tài liệu mô tả là lệnh xuất tất cả threads vào file.

### 9.3. Java Flight Recorder

**JFR (Java Flight Recorder)** hỗ trợ điều tra các sự kiện có yếu tố thời gian, ví dụ monitor enter, thread park, lock contention và các virtual thread events theo JDK/configuration. Nó có thể hữu ích khi một snapshot không đủ để trả lời **vấn đề xảy ra lúc nào, kéo dài bao lâu và tái diễn bao nhiêu lần**.

Không cần bật mọi sự kiện theo tần suất cao ở production một cách mù quáng; chọn cấu hình recording, sampling/threshold, retention, redaction và quyền truy cập theo security/operations policy.

### 9.4. Thread dumps có thể chứa dữ liệu nhạy cảm

Stack trace và thread names có thể để lộ:
- tên class/packages/module nội bộ;
- logic business;
- usernames/tenant IDs trong tên thread;
- secrets nếu ứng dụng dùng thread-local names hoặc diagnostic messages không an toàn;
- cấu trúc hệ thống và thư viện.

Không đưa raw dumps vào log công khai, ticket không bảo mật hay endpoint HTTP cho người dùng. Dùng quyền admin, thời hạn lưu trữ, file permissions, encryption at rest khi cần và chính sách xóa phù hợp.

## 10. Deadlock detection không giống dump lock ownership

`ThreadMXBean` cung cấp hai đường kiểm tra deadlock cho **platform threads**:

~~~java
long[] monitorCycles = mx.findMonitorDeadlockedThreads();
long[] monitorOrSynchronizerCycles =
        mx.isSynchronizerUsageSupported()
        ? mx.findDeadlockedThreads()
        : null;
~~~

Đây là **đoạn trích**, không phải chương trình độc lập. Hai APIs trả **mảng thread IDs** khi tìm thấy deadlock, hoặc **`null`** khi không phát hiện (phân biệt với empty array khi thiết kế reporting). `findDeadlockedThreads()` có thể ném `UnsupportedOperationException` nếu JVM không hỗ trợ synchronizer usage; kiểm tra support như trên. Biến `null` ở nhánh không hỗ trợ trong đoạn trích **không được coi là “không có deadlock”**; hãy lưu trạng thái `unsupported` riêng.

### 10.1. Monitor-only deadlock

Luồng A giữ monitor X rồi chờ monitor Y; luồng B giữ Y rồi chờ X. `findMonitorDeadlockedThreads()` tìm chu trình liên quan object monitors. Nó **không** phát hiện deadlock chỉ có `ReentrantLock`, không phát hiện chu trình liên quan virtual threads.

### 10.2. Mixed monitor và ownable synchronizer deadlock

Nếu luồng A giữ monitor M và chờ ReentrantLock R, trong khi B giữ R và chờ M, `findDeadlockedThreads()` có thể nhận diện chu trình kết hợp monitors + ownable synchronizers, với điều kiện JVM hỗ trợ. `findMonitorDeadlockedThreads()` không đủ cho trường hợp này.

### 10.3. Không phải mọi “treo” đều được xác định là deadlock

Một request có thể treo do:
- chờ database query/network I/O;
- chờ `CountDownLatch` không có thread sở hữu;
- chờ `Semaphore` permits;
- starvation của thread pool;
- lock convoy/long critical section;
- infinite loop hoặc CPU starvation;
- virtual thread/structured task chờ resource.

Những trường hợp đó có thể không tạo một chu trình deadlock thuộc phạm vi `ThreadMXBean`. **`findDeadlockedThreads()==null` không chứng minh application khỏe**. Kết hợp latency metrics, tracing, application logs và diagnostics phù hợp.

### 10.4. Không tạo deadlock thật trong bài test mặc định

Tạo hai non-daemon threads deadlock cố ý có thể khiến JVM không thoát và ảnh hưởng build agent. Demo của bài dùng **latches có cleanup** để tạo trạng thái BLOCKED/WAITING rõ mà không gây deadlock thật. Nếu cần bài thực hành deadlock detection, đặt tiến trình test riêng có timeout, cô lập và không để production lẫn vào.

## 11. Thiết kế diagnostic endpoint an toàn

Một tính năng “dump threads” trong application admin tool cần chính sách rõ:

1. **Chỉ admin được phép**; authentication/authorization và audit phải có trước khi gọi API.
2. Giới hạn **rate** và concurrency, ví dụ một snapshot đang chạy tại một thời điểm.
3. Giới hạn **maxDepth**, số lượng lines, số bytes serialize và thời gian giữ dump.
4. **Không log toàn bộ** `ThreadInfo.toString()` trực tiếp ở mọi request định kỳ.
5. Redact/kiểm soát **thread names**, class paths và dữ liệu nhạy cảm.
6. Đánh dấu rõ **capability flags**, JDK version, timestamp, PID/JVM identity.
7. Ghi nhận `ThreadMXBean` chỉ nhìn **platform threads** trên Java 21+.
8. Có thể chạy chẩn đoán ở worker/background request thread có deadline, nhưng không tạo vòng poll dày.
9. Ghi metric về thời gian dump và số threads, không để file dumps phát triển vô hạn.
10. Nếu cần virtual threads, dùng `jcmd Thread.dump_to_file`/JFR theo quy trình ops thay vì hứa hẹn sai từ MXBean.
11. Không dùng snapshot để tự ý `Thread.stop()`, không tự “unlock” monitor của thread khác; các cách đó không an toàn.
12. Phân biệt vấn đề **security** (quyền xem dump) với vấn đề **correctness** (thông tin dump có giới hạn).

### 11.1. Mẫu dữ liệu báo cáo gọn

~~~text
timestampUtc=...
jvmId=...
source=ThreadMXBean.dumpAllThreads
scope=platform-threads-only
monitorUsageSupported=true/false
synchronizerUsageSupported=true/false
requestedMaxDepth=16
capturedPlatformThreads=N
redactedSensitiveNames=true
snapshotConsistency=best-effort
~~~

Đây chỉ là **mẫu schema minh họa**, không phải stdout từ một chương trình runnable. `N` được lấy từ `snapshot.length` tại thời điểm đó; không nên coi là count của tất cả Java virtual threads.

### 11.2. Không dùng identityHashCode làm identity ngoài JVM

`MonitorInfo/LockInfo.getIdentityHashCode()` có ý nghĩa hỗ trợ correlate lock objects **trong process và thời điểm snapshot**, không phải ID ổn định xuyên restart hay đảm bảo unique. Cần kết hợp class name/owner/stack/correlation để tránh kết luận sai.

### 11.3. Guard nếu JVM không hỗ trợ

Một diagnostic endpoint có thể trả:

~~~java
boolean haveMonitors = mx.isObjectMonitorUsageSupported();
boolean haveSynchronizers = mx.isSynchronizerUsageSupported();

ThreadInfo[] infos = mx.dumpAllThreads(haveMonitors, haveSynchronizers);

String monitorStatus = haveMonitors ? "collected" : "unsupported";
String syncStatus = haveSynchronizers ? "collected" : "unsupported";
~~~

**Đoạn trích**. Lỗi thường gặp là in `getLockedMonitors().length==0` khi capability false rồi ghi “no monitor locks”: report đó **sai về ý nghĩa**. Cần thể hiện unavailable/unsupported riêng.

## 12. Lỗi phổ biến và cách khắc phục

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Gọi `dumpAllThreads(true,true)` mà không kiểm tra JVM | Có thể ném UnsupportedOperationException | Query hai capability flags |
| `dumpAllThreads(false,false)` thấy arrays rỗng, kết luận không có locks | Flags tắt thu thập ownership | Bật flags nếu supported |
| Coi monitor và synchronizer là một | Intrinsic monitor và AQS ownership khác nhau | Phân tích MonitorInfo vs LockInfo |
| Dùng `getLockedSynchronizers()` để tìm mọi Java locks | Chỉ ownable synchronizers | Kết hợp application diagnostics |
| Kết luận WAITING = deadlock | WAITING có nhiều nguyên nhân | Xem lock owner, frames, deadlines, tiến độ |
| Kết luận BLOCKED = deadlock | Có thể chỉ là lock contention tạm thời | Đối chiếu nhiều snapshots |
| Nhầm getLockInfo với getLockedMonitors | Waiting lock khác held locks | Ghép waiting/owner info |
| Đọc `getLockOwnerId()==-1` như “không có owner” | Owner có thể chưa xác định | Báo owner unknown |
| Dùng MonitorInfo stack depth như nesting level | Đó là index trong stack trace | Đọc getLockedStackFrame đúng |
| Hardcode ReentrantLock$NonfairSync nội bộ | Provider/JDK implementation detail | Dựa API fields và nhiều tín hiệu |
| Dùng identityHashCode làm global lock ID | Không globally unique/stable | Kết hợp per-process context |
| Coi snapshot atomic tuyệt đối | Thread states thay đổi trong quá trình thu | Ghi thời điểm, lặp có kiểm soát |
| Gọi `dumpAllThreads(...,maxDepth)` ở Java 6 source | Overload ba args có từ Java 10 | Compile target Java 10+ |
| Gọi virtual thread APIs trên `--release 17` | Virtual threads từ Java 21 | Tách file Java 21+ |
| Coi thread count của MXBean là mọi threads trong Java 21+ | Chỉ platform threads | Dùng virtual-aware diagnostics |
| `getThreadInfo(vtId)==null` nên nghĩ thread chết | Virtual threads không được theo dõi | Dùng jcmd/JFR khi cần |
| Coi `findDeadlockedThreads()==null` là no hangs | Chỉ phát hiện một loại cycles nhất định | Điều tra locks, I/O, resource starvation |
| Giữ deliberate deadlock trong unit test | JVM/build có thể không thoát | Isolated process với timeout hoặc latch fixture |
| Đọc snapshot mỗi 10ms ở production | Overhead và dữ liệu lớn | Rate limits, trigger-based captures |
| Dump stacks ra public API/log | Có thể lộ thông tin hệ thống/PII | Admin-only, redaction và retention |
| Bật contention monitoring để xem locks | Không bắt buộc, có overhead | Dùng capability riêng |
| Dùng Thread.stop()/suspend() chữa treo | Không an toàn/legacy | Sửa lock ordering, timeouts, cancellation |
| Gửi thread dump không có metadata JDK/scope | Dễ hiểu sai virtual/platform thread | Ghi JDK, flags, timestamp |
| Dùng Thread.print đồng nghĩa dump_to_file | Virtual-thread coverage khác nhau | Chọn công cụ theo nhu cầu |
| Nhầm `maxDepth` là max thread count | Chỉ giới hạn frames/thread | Lựa chọn output quota riêng |

## 13. Checklist kiểm thử và triển khai

| Test | Kỳ vọng |
| --- | --- |
| `ManagementFactory.getThreadMXBean` | Trả ThreadMXBean của process |
| `isObjectMonitorUsageSupported` | Ghi rõ capability |
| `isSynchronizerUsageSupported` | Ghi rõ capability |
| `dumpAllThreads(true,true)` trên VM hỗ trợ | Có MonitorInfo/LockInfo khi locks thực sự được giữ |
| `dumpAllThreads(false,false)` | Owner lock arrays rỗng do flags |
| `dumpAllThreads(false,false,5)` | Mỗi stack có ≤5 frames |
| `dumpAllThreads(...,-1)` | IllegalArgumentException |
| Monitor owner giữ synchronized | LockedMonitors có object phù hợp |
| Monitor waiter chờ synchronized | ThreadState BLOCKED |
| Monitor waiter getLockOwnerId | Trỏ tới owner nếu JVM xác định |
| MonitorInfo identityHash | Khớp với monitor fixture |
| MonitorInfo lockedStackDepth | Index hợp lệ khi frame có sẵn |
| ReentrantLock owner | LockedSynchronizers có ownable lock |
| ReentrantLock waiter | Owner ID/lock target phù hợp |
| Owner release latch | Cả waiters kết thúc |
| getThreadInfo(ids,flags) | Lấy targeted platform thread, null khi không còn |
| Platform/virtual cùng đang sống | Chỉ platform có trong ThreadMXBean dump |
| getThreadInfo(virtualId) | Null |
| maxDepth=0 | Không có stack frames |
| Virtual-aware jcmd dump | Có virtual threads theo công cụ và JDK |
| findMonitorDeadlockedThreads | Chỉ monitor cycles (nếu tồn tại) |
| findDeadlockedThreads | Monitor+ownable cycles, không virtual |
| Contention monitoring disabled | Locked info vẫn có thể thu độc lập |
| JVM capability false | Báo unsupported, không báo zero locks |
| No deadlock trong fixture | Tests kết thúc, không leaked workers |
| App nhiều threads | Diagnostic có rate/output limits |
| JDK 17/21/26 upgrade | Regression tests và semantics phù hợp |
| JMX remote access | Không mở unauthenticated diagnostic exposure |
| Log output | Không chứa sensitive names/stack data |
| Cleanup | Releases, joins, không giữ latches/locks vĩnh viễn |

### 13.1. Những trường hợp khó cần thêm bằng chứng

- Một thread có state `WAITING` vì `LockSupport.park` nhưng không có `LockInfo` xác định owner rõ.
- Một thread trong `RUNNABLE` nhưng CPU usage thấp do native syscall hoặc I/O; Java Thread.State không phải OS scheduler state tuyệt đối.
- Một ứng dụng Java 21+ có hàng trăm ngàn virtual threads nhưng ThreadMXBean trả vài chục platform threads.
- Một `StampedLock` hoặc read lock có contention, nhưng `getLockedSynchronizers()` không liệt kê như ReentrantLock owner.
- Một request chậm do DB row lock hoặc remote service; `findDeadlockedThreads` của JVM không phát hiện.
- Một deadlock chỉ liên quan virtual threads; ThreadMXBean không nhận diện.
- Một thread kết thúc trong lúc dump, khiến results qua `getThreadInfo(ids)` có null.

Các tình huống trên không phải bug tự động của API. Chúng cần trace/metrics, công cụ khác hoặc mô hình chẩn đoán rộng hơn.

## 14. Câu hỏi tự đánh giá

**1.** `dumpAllThreads(true,true)` khác `dumpAllThreads(false,false)` ở điểm nào?

**Đáp án:** Cùng thu stack traces của live platform threads; true,true thêm thông tin monitors và ownable synchronizers **đang được giữ** nếu JVM hỗ trợ.

**2.** Nếu `isSynchronizerUsageSupported()==false` mà vẫn gọi `dumpAllThreads(false,true)`?

**Đáp án:** Có thể bị `UnsupportedOperationException`; nên kiểm tra capability trước.

**3.** Có cần bật `setThreadContentionMonitoringEnabled(true)` để lấy MonitorInfo không?

**Đáp án:** Không, đó là tính năng đo thời gian contention riêng.

**4.** `getLockedMonitors()` là locks thread đang chờ hay đang giữ?

**Đáp án:** Đang **giữ** tại snapshot.

**5.** `getLockInfo()` trong ThreadInfo nói điều gì?

**Đáp án:** Lock mà thread đang blocked/waiting, nếu có và được JVM biết.

**6.** `MonitorInfo.getLockedStackDepth()` là gì?

**Đáp án:** Index của stack frame nơi monitor được lấy hoặc số âm nếu không biết; không phải nested-lock count.

**7.** `MonitorInfo.getLockedStackFrame()` có luôn khác null không?

**Đáp án:** Không, null khi không có thông tin frame.

**8.** `ReentrantLock` luôn xuất hiện dưới đúng class name `ReentrantLock`?

**Đáp án:** Không, LockInfo có thể cho biết implementation `ReentrantLock$...Sync`.

**9.** `ReentrantReadWriteLock.ReadLock` có được ownable synchronizer list bảo đảm liệt kê không?

**Đáp án:** Không. Tài liệu nhắc **write lock**, không phải read lock, là ví dụ ownable synchronizer.

**10.** `Thread.State.BLOCKED` có nghĩa deadlock?

**Đáp án:** Không. Nó chỉ thể hiện chờ monitor; deadlock cần chu trình ownership/waiting.

**11.** `Thread.State.WAITING` chỉ xảy ra khi chờ `ReentrantLock`?

**Đáp án:** Không, nhiều cơ chế chờ như CountDownLatch, Object.wait, join, park.

**12.** ThreadMXBean có liệt kê virtual threads của Java 21+ không?

**Đáp án:** Không, chỉ platform threads.

**13.** `getThreadInfo(virtualThread.threadId())` trả gì khi virtual thread đang sống?

**Đáp án:** `null` theo contract hiện hành.

**14.** Công cụ JDK nào có thể dump cả platform và virtual threads?

**Đáp án:** `jcmd <pid> Thread.dump_to_file -format=json|plain <file>` trên JDK hỗ trợ.

**15.** `jcmd Thread.dump_to_file` có tự phát hiện deadlock không?

**Đáp án:** Không; nó tạo thread dump, cần phân tích hoặc dùng công cụ/API deadlock riêng.

**16.** `findMonitorDeadlockedThreads` và `findDeadlockedThreads` khác nhau?

**Đáp án:** Phương thức đầu xét object monitors; phương thức sau xét monitors và ownable synchronizers nếu JVM hỗ trợ, đều không tìm chu trình liên quan virtual threads.

**17.** `dumpAllThreads(..., 8)` có nghĩa chỉ lấy tám threads?

**Đáp án:** Không, chỉ giới hạn tối đa tám stack frames **cho mỗi thread**.

**18.** Khi `getLockOwnerId()==-1` có thể khẳng định không ai giữ lock?

**Đáp án:** Không. Nó có nghĩa owner không xác định được qua API tại snapshot.

**19.** Có nên bật public HTTP endpoint cho mọi người tải thread dumps?

**Đáp án:** Không; stacks và thread names có thể nhạy cảm và thu thập có chi phí. Chỉ authorized admin, có quotas/audit/redaction.

**20.** Có nên dùng `Thread.stop()` để kết thúc luồng đang giữ monitor theo dump?

**Đáp án:** Không. Đây là biện pháp không an toàn; sửa concurrency design, lock ordering, bounded waits/cancellation và monitoring.

### Bài tập thực hành

1. Chạy `ThreadDumpLocksDemo.java`, xác nhận cả 12 dòng stdout trên JDK hỗ trợ monitor/synchronizer usage.
2. Đổi `dumpAllThreads(monitors,synchronizers)` thành `dumpAllThreads(false,false)`, xem vì sao ownership arrays rỗng.
3. Gọi `dumpAllThreads(monitors,synchronizers,3)` và kiểm tra stack frame count; thảo luận ảnh hưởng tới MonitorInfo lockedStackFrame.
4. Thêm logging `info.getThreadName()/getThreadState()` có redaction, tránh hardcode tên object từ production.
5. In `getLockInfo()` của monitor-waiter, đối chiếu identityHashCode với `MONITOR`.
6. In `getLockedSynchronizers()` của owner, giải thích tên `ReentrantLock$NonfairSync` là implementation detail.
7. Đổi `ReentrantLock` sang `ReentrantReadWriteLock.WriteLock` và test ownable synchronizer capture.
8. Dùng `ReentrantReadWriteLock.ReadLock` và ghi nhận giới hạn ownership model.
9. Thử `getThreadInfo(new long[]{id},true,true)` trên JVM không hỗ trợ bằng cách mô phỏng policy fallback, đảm bảo không coi unsupported là 0.
10. Gọi `dumpAllThreads(false,false,0)`, xác nhận stack trace arrays empty.
11. Gọi `dumpAllThreads(false,false,-1)` và assert IllegalArgumentException (trong unit test cô lập).
12. Chạy `VirtualThreadScopeDemo.java` với `--release 21`, xác nhận virtual thread vẫn sống nhưng không có ThreadInfo.
13. So sánh `ThreadMXBean.getThreadCount()` với số virtual tasks đang chạy trên Java 21+, giải thích khác biệt scope.
14. Dùng `jcmd <pid> Thread.dump_to_file -format=json <file>` trong test được phép; so sánh virtual-thread coverage.
15. Thử `jcmd <pid> Thread.print -l` và nêu vì sao coverage khác dump_to_file.
16. Dùng JFR để quan sát một sự kiện monitor enter dài với threshold/cấu hình phù hợp.
17. Thiết kế một diagnostic MXBean hoặc admin command chỉ expose **aggregated** thread counts/lock symptoms, không lộ full stacks.
18. Viết parser ThreadInfo giúp thống kê số threads BLOCKED theo class name, không đưa PII vào logs.
19. Tạo hai snapshots cách nhau vài giây, kiểm tra một owner có thực sự giữ khóa kéo dài không.
20. Xây runbook ứng phó incident: authorized capture → redact → correlate traces → fix root cause → cleanup.
21. Thử một lock ordering problem trong **process test riêng có timeout**, không để deadlock threads trong process build chính.
22. Kiểm thử worker cleanup khi một assertion cố ý fail, đảm bảo release latch và join không làm treo JVM.

## 15. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — ThreadMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html): `dumpAllThreads` hai/ba tham số, capabilities, deadlock và virtual-thread exclusion.
- [Oracle Java SE 26 — ThreadInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadInfo.html): thread state, lock owner, lockedMonitors/lockedSynchronizers và MXBean mapping.
- [Oracle Java SE 26 — MonitorInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MonitorInfo.html): monitor identity, lockedStackDepth/lockedStackFrame.
- [Oracle Java SE 26 — LockInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/LockInfo.html): ownable synchronizer identity.
- [Oracle Java SE 26 — ManagementFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html): getThreadMXBean và platform management access.
- [Oracle Java SE 26 — Thread](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html): platform/virtual threads, states, IDs.
- [Oracle Java SE 26 — ReentrantLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): ownable exclusive locks.
- [Oracle Java SE 26 — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): write lock vs read lock.
- [Oracle Java SE 26 — AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html): ownable synchronizers contract.
- [Oracle Java SE 26 — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html): synchronization fixture without permanent deadlock.
- [Oracle Java SE 26 — Thread.State](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.State.html): BLOCKED/WAITING/TIMED_WAITING.
- [Oracle Java SE 26 — MBeanServer](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServer.html): Threading MXBean access qua JMX.
- [Oracle Java SE 26 — jcmd tool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): Thread.dump_to_file và Thread.print.
- [Oracle Java SE 26 — Virtual Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): virtual-thread-aware dumps, JFR/observability.
- [Oracle Java SE 26 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/26/jfapi/): recording và diagnostics.
- [Oracle Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): virtual threads excluded từ Java 21.
- [Oracle Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): Java17 target và method availability.
- [Oracle Java SE 17 — ThreadInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): type/lock info cho Java17 demo.

**Ghi nhớ:** `ThreadMXBean.dumpAllThreads(lockedMonitors, lockedSynchronizers)` là API **vẫn hiện hành** để chụp **platform-thread** stack + held monitor/ownable synchronizer information. **Hai flags phải được dùng cùng capability checks**; `false,false` trả locked arrays rỗng do không yêu cầu, không chứng minh không có contention. `MonitorInfo` cho biết monitor đang giữ và frame khi có dữ liệu; `LockInfo` cho biết ownable synchronizer đang giữ, còn `getLockInfo()/getLockOwnerId()` giúp phân tích luồng đang chờ. **Virtual threads Java 21+ không xuất hiện trong ThreadMXBean**, muốn quan sát cả hai loại luồng có thể dùng `jcmd Thread.dump_to_file` hoặc JFR theo quy trình vận hành. Không dùng snapshot để điều khiển synchronization, không thu dumps tần suất cao và không công khai dữ liệu quản trị.
