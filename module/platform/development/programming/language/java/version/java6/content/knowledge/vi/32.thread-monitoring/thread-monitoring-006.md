# Phân biệt monitor với ownable synchronizer khi theo dõi luồng Java

Khi phân tích một ứng dụng Java có nhiều luồng, bạn có thể thấy hai nhóm tài nguyên đồng bộ trong `ThreadInfo`: **object monitors** và **ownable synchronizers**. Cả hai đều có thể bảo đảm truy cập loại trừ tương hỗ, nhưng chúng là **hai loại đối tượng đồng bộ khác nhau**; cách chúng được sử dụng, cách luồng chờ, và cách JVM báo cáo thông tin lock cũng khác nhau.

- **Object monitor** là khóa nội tại (*intrinsic monitor*) gắn với một đối tượng Java, điển hình được lấy khi vào `synchronized (someObject)` hoặc một `synchronized` method. Luồng đang chờ **vào** monitor thường có trạng thái **`BLOCKED`**.
- **Ownable synchronizer** là synchronizer có khái niệm **một luồng đang sở hữu độc quyền**. Java có cơ sở `java.util.concurrent.locks.AbstractOwnableSynchronizer`; ví dụ quen thuộc nhất trong bài là **`ReentrantLock`** (bên trong sử dụng AbstractQueuedSynchronizer/AQS). Luồng tranh chấp `ReentrantLock.lock()` thường **park** và xuất hiện ở trạng thái **`WAITING`** chứ không phải `BLOCKED`.
- **`ThreadInfo.getLockedMonitors()`** trả về `MonitorInfo[]` cho object monitors **luồng đang sở hữu**.
- **`ThreadInfo.getLockedSynchronizers()`** trả về `LockInfo[]` cho ownable synchronizers **luồng đang sở hữu**.
- **`ThreadInfo.getLockInfo()`** mô tả đối tượng mà luồng **đang đợi**, có thể là monitor, synchronizer/parking blocker hoặc một đối tượng dùng để chờ. Không nhầm với **danh sách khóa luồng đã sở hữu**.

Đặc biệt, `ThreadMXBean` trong **Java SE 26 chỉ giám sát platform threads**; các API này **không hỗ trợ lấy thông tin từng virtual thread**. Nếu ứng dụng dùng virtual threads, hãy dùng công cụ và API quan sát phù hợp phiên bản như `jcmd Thread.dump_to_file` và khả năng quan sát scheduler, không giả định `ThreadMXBean.dumpAllThreads` đã chứa mọi virtual thread.

Bài thuộc nhóm **Theo dõi luồng**, tập trung vào đề bài **“Phân biệt monitor với ownable synchronizer”**. Chỉ dùng Java APIs còn áp dụng trên **Java 17+ / Java SE 26**, tránh kiến thức và kỹ thuật đồng bộ lỗi thời. Ví dụ Java 17+ hoàn chỉnh tạo 4 **platform threads**, mô phỏng tranh chấp `synchronized` và `ReentrantLock`, dùng `ThreadMXBean` lấy snapshot chi tiết, kiểm chứng **23/23 assertions PASS** trên JDK trong môi trường làm việc. Chương trình không tạo deadlock không phục hồi, không mở network port, và có cleanup trong `finally`.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Diễn giải monitor nội tại và ownable synchronizer theo đúng khái niệm Java Management.
2. Phân biệt `synchronized`/`Object.wait()` với `ReentrantLock`/`Condition.await()`.
3. Dùng `ManagementFactory.getThreadMXBean()` và kiểm tra `isObjectMonitorUsageSupported()`, `isSynchronizerUsageSupported()`.
4. Hiểu `Thread.State.BLOCKED` (chờ vào monitor) khác `WAITING`/`TIMED_WAITING` (đợi notification, join, park, timed waits).
5. Đọc `getLockedMonitors`/`getLockedSynchronizers` để xác định **khóa đã giữ**.
6. Đọc `getLockInfo`/`getLockOwnerId`/`getLockOwnerName` để xác định **khóa đang chờ** và **luồng chủ sở hữu**, khi JVM cung cấp được.
7. Hiểu `MonitorInfo` là subclass của `LockInfo`, bổ sung `getLockedStackDepth` và `getLockedStackFrame`.
8. Biết `LockInfo.getClassName` và `getIdentityHashCode` mô tả đối tượng khóa, không phải business identifier.
9. Giải thích vì sao `ReentrantLock` có ownable synchronizer nội bộ, còn `Semaphore`/shared read locks không tự động có một owner độc quyền.
10. Phân biệt `findMonitorDeadlockedThreads` với `findDeadlockedThreads`.
11. Biết thread contention monitoring là chức năng **khác** với thu thập lock ownership.
12. Không dùng snapshot `ThreadInfo` làm cơ chế ra quyết định đồng bộ đang chạy (TOCTOU).
13. Đánh giá tác động snapshot/dump khi nhiều threads và giới hạn của virtual threads.
14. Chạy chương trình kiểm thử minh bạch, đọc đúng 23 PASS labels và áp dụng vào troubleshooting.

## 2. Monitor là gì?

Mỗi đối tượng Java có thể được dùng làm intrinsic lock khi vào một khối `synchronized`:

```java
private final Object guard = new Object();

void increment() {
    synchronized (guard) {
        count++;
    }
}
```

Đây là mảnh code, cần có biến `count` và class. Khi một luồng đã vào khối `synchronized (guard)`, nó sở hữu **monitor gắn với chính object `guard`**. Một luồng khác muốn vào cùng monitor phải đợi. Nếu không lấy được monitor ngay, luồng cạnh tranh được JVM biểu diễn là **`BLOCKED`**.

Monitor cũng được lấy cho `synchronized` instance method, với monitor của `this`, hoặc `static synchronized` method, với monitor của `Class` object tương ứng.

**Monitor là khái niệm ở cấp object**, không nhất thiết có một đối tượng `Lock` hay `ReentrantLock` do lập trình viên tạo. Một object bình thường, chẳng hạn `new Object()`, đã có thể làm monitor lock.

### 2.1. Một monitor có thể được giữ đệ quy

`synchronized` là **reentrant**: cùng một thread có thể vào nhiều khối synchronized trên cùng một monitor mà không tự chặn mình. JVM theo dõi ownership/entry count. Khi thoát toàn bộ các khối/method tương ứng, monitor mới được thả để thread khác có thể vào.

Đây là điểm tương đồng với `ReentrantLock`, nhưng **reentrant behavior không biến intrinsic monitor thành AQS synchronizer**.

### 2.2. Khi một thread chờ monitor

Ví dụ:

```text
Thread A                       Thread B
    |                              |
synchronized (guard) {             |
    ...                            |
    hold guard                    synchronized (guard) {
    ...                            ^ chờ vào monitor -> BLOCKED
}                                  |
    |                            acquired guard
```

Trạng thái `BLOCKED` nghĩa thread chờ **monitor lock**, không phải một nhãn tổng quát cho mọi kiểu “không làm việc”. Một thread bị giữ bởi file I/O, `LockSupport.park` hoặc `ReentrantLock.lock` thường không thuộc `BLOCKED` chỉ vì nó đang phải đợi.

### 2.3. Object.wait khác chờ vào synchronized

Khi thread đã sở hữu monitor `guard` và gọi `guard.wait()`, nó **tạm thời nhả monitor đó** và chuyển vào **`WAITING`** (hoặc `TIMED_WAITING` nếu có timeout) để chờ notify/interrupt/spurious wakeup. Khi thức dậy, nó phải lấy lại monitor trước khi tiếp tục.

Vì vậy:

- **Chờ vào monitor**: `BLOCKED`.
- **Chờ trong `Object.wait()`**: `WAITING`/`TIMED_WAITING`, monitor dùng để wait đã được nhả.
- **Chờ để lấy lại monitor sau wait**: có thể chuyển sang `BLOCKED`.

Một thread có thể vẫn sở hữu **những monitor khác** khi nó gọi `wait` trên một monitor riêng; không suy ra từ trạng thái WAITING rằng thread không giữ bất cứ khóa nào.

## 3. Ownable synchronizer là gì?

Theo Java SE 26, `AbstractOwnableSynchronizer` là cơ sở cho synchronizers có thể thuộc **sở hữu độc quyền** của một thread. Nó cung cấp khả năng lưu thông tin owner để các lớp con/công cụ quản lý và chẩn đoán. **Bản thân `AbstractOwnableSynchronizer` không tự quản lý lock, không tự bảo đảm mutex**; subclass phải cập nhật owner phù hợp.

`AbstractQueuedSynchronizer` (AQS) và `AbstractQueuedLongSynchronizer` kế thừa cơ sở này. Một `ReentrantLock` dùng một synchronizer nội bộ kế thừa AQS; khi thread đã lấy lock ở chế độ độc quyền, monitoring có thể báo **đối tượng synchronizer nội bộ** là thứ thread sở hữu.

```java
ReentrantLock lock = new ReentrantLock();

lock.lock();
try {
    // Critical section.
} finally {
    lock.unlock();
}
```

Đây là mảnh code độc lập về cú pháp khi có import `java.util.concurrent.locks.ReentrantLock` và nằm trong method. Mẫu `lock()/try/finally/unlock()` là thực hành hiện hành; không để `unlock()` bị bỏ qua khi xảy ra exception.

### 3.1. Ownable không chỉ đơn giản là “một object Lock”

Một Java object bất kỳ đều có thể dùng làm `synchronized (object)`, **kể cả một instance `ReentrantLock`**. Nhưng điều này dùng **monitor của ReentrantLock object**, không phải acquisition bằng `lock.lock()` trên synchronizer nội bộ.

Hai đoạn code sau **không khóa lẫn nhau theo cùng một cơ chế**:

```java
ReentrantLock lock = new ReentrantLock();

// Lấy intrinsic monitor của Java object "lock".
synchronized (lock) {
    // Chỉ tương tranh với những code synchronized (lock).
}

// Lấy exclusive lock của AQS synchronizer bên trong ReentrantLock.
lock.lock();
try {
    // Chỉ tương tranh với các lần lock()/tryLock()/lockInterruptibly().
} finally {
    lock.unlock();
}
```

Đây là đoạn minh họa; không dùng lẫn hai cơ chế để bảo vệ cùng shared state. Nếu thread A `synchronized(lock)`, thread B vẫn có thể `lock.lock()`; chúng không cùng bảo vệ critical section.

### 3.2. Các công cụ java.util.concurrent liên quan

| Cơ chế | Có khái niệm owner độc quyền không? | JVM ThreadMXBean có thể báo gì? |
| --- | --- | --- |
| `synchronized (obj)` | Có owner của intrinsic object monitor. | `MonitorInfo` trong `getLockedMonitors()`. |
| `ReentrantLock.lock()` | Có một thread owner độc quyền. | `LockInfo` của AQS synchronizer nội bộ trong `getLockedSynchronizers()`. |
| `ReentrantReadWriteLock.WriteLock` | Exclusive writer có owner. | Có thể hiển thị ownable synchronizer khi đang giữ write lock. |
| `ReentrantReadWriteLock.ReadLock` | Nhiều readers có thể cùng giữ; không có một exclusive owner theo cùng mô hình. | Đừng mặc định mỗi reader xuất hiện như một ownable lock. |
| `Semaphore` | Quản lý permits, thường không gắn với một owner thread độc quyền. | Không đánh đồng permits đang giữ với ownable synchronizer owner. |
| `CountDownLatch` | Chờ count xuống 0, không theo mô hình một owner độc quyền. | Waiter có thể park trên internal synchronizer; không vì thế latch “được sở hữu” như ReentrantLock. |
| `Condition.await()` | Waiter thường nhả associated lock khi chờ. | Có thể WAITING với parking blocker; không nhất thiết giữ ownable lock trong thời gian await. |
| `LockSupport.park()` | Chỉ là primitive chờ/đánh thức. | WAITING/TIMED_WAITING, không tự có exclusive owner. |

**Không phải mọi subclass AQS hoặc mọi `Lock` implementation đều mặc nhiên là một ownable synchronizer theo cách ThreadMXBean có thể báo.** Thông tin owner phụ thuộc thiết kế và việc cập nhật owner state của synchronizer.

### 3.3. Tại sao ReentrantLock waiter thường WAITING?

`ReentrantLock` có cơ chế xếp hàng/park cho thread không lấy được lock. Khi luồng bị park, trạng thái trong `Thread.State` thường là **`WAITING`** (hoặc `TIMED_WAITING` khi dùng timed waits), không phải `BLOCKED`, bởi `BLOCKED` dành cho **monitor acquisition**.

Đây là khác biệt có ích khi xem thread dump:

```text
synchronized (monitor) tranh chấp
    -> Thread.State.BLOCKED
    -> waiting for object monitor
    -> owner holds object monitor

ReentrantLock.lock() tranh chấp
    -> usually Thread.State.WAITING
    -> parking on AQS sync
    -> owner holds ownable synchronizer
```

Đừng biến “WAITING nghĩa là ReentrantLock” thành quy tắc chắc chắn: `Object.wait()`, `Thread.join()` và `LockSupport.park()` cũng có thể khiến thread WAITING.

## 4. ThreadMXBean: quan sát cả hai loại khóa

`ThreadMXBean` là management interface từ module `java.management`. Đối tượng platform MXBean lấy bằng:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

Hai lớp nằm trong `java.lang.management`. Trong JMX platform MBeanServer, ObjectName chuẩn cho threading bean là `java.lang:type=Threading`.

**Kiểm tra capability trước khi yêu cầu snapshot chi tiết**:

```java
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean synchronizers = bean.isSynchronizerUsageSupported();
```

Nếu không hỗ trợ mà bạn gọi `getThreadInfo(ids, true, true)`, Javadoc cho phép `UnsupportedOperationException` tương ứng. Không hardcode rằng mọi JVM/provider luôn hỗ trợ. Ví dụ runnable ở mục 9 có nhánh `SKIPPED` rõ ràng khi thiếu capability, thay vì đưa ra thông tin khóa sai.

### 4.1. Lấy snapshot đầy đủ

```java
long[] threadIds = {ownerId, waiterId};
ThreadInfo[] infos = bean.getThreadInfo(threadIds, true, true);
```

Trong overload này:

- `true` thứ nhất: yêu cầu danh sách **monitors** đang giữ.
- `true` thứ hai: yêu cầu danh sách **ownable synchronizers** đang giữ.
- Kết quả ánh xạ theo **thứ tự IDs đầu vào**, nhưng mỗi entry có thể là `null` nếu thread đã kết thúc/không tồn tại/không thuộc nhóm được hỗ trợ.
- Bản này lấy stack traces và synchronization info; có thể gây chi phí đáng kể khi hệ thống có nhiều threads.
- Overload `getThreadInfo(ids, true, true, maxDepth)` trên Java 17+ giới hạn stack depth nhưng vẫn cần capability support.

Nếu chỉ gọi `getThreadInfo(id)` hoặc `getThreadInfo(ids,false,false)`, các mảng locked monitors/synchronizers **đều rỗng**, **kể cả khi thread đang giữ khóa**. Điều này không chứng minh ứng dụng không dùng locks: bạn **chưa yêu cầu** metadata ownership.

### 4.2. Bảng API để đọc đúng

| API | Trả về | Trả lời câu hỏi |
| --- | --- | --- |
| `ThreadInfo.getThreadState()` | `Thread.State` | Thread đang ở trạng thái JVM nào? |
| `ThreadInfo.getLockedMonitors()` | `MonitorInfo[]` | Thread đang **sở hữu** object monitors nào? |
| `ThreadInfo.getLockedSynchronizers()` | `LockInfo[]` | Thread đang **sở hữu** ownable synchronizers nào? |
| `ThreadInfo.getLockInfo()` | `LockInfo` hoặc null | Thread đang **chờ** khóa/blocker nào? |
| `ThreadInfo.getLockOwnerId()` | ID hoặc `-1` | Owner của đối tượng thread đang đợi, nếu xác định được? |
| `ThreadInfo.getLockOwnerName()` | Tên hoặc null | Tên owner, nếu xác định được? |
| `ThreadInfo.getStackTrace()` | `StackTraceElement[]` | Thread đang thực hiện/chờ ở lời gọi nào? |
| `MonitorInfo.getLockedStackDepth()` | int | Frame index nơi monitor được lấy, nếu có. |
| `MonitorInfo.getLockedStackFrame()` | StackTraceElement hoặc null | Frame nơi monitor được lấy. |
| `LockInfo.getClassName()` | String | Runtime class của lock/blocker được báo. |
| `LockInfo.getIdentityHashCode()` | int | `System.identityHashCode` của lock/blocker. |

**Cẩn thận về getLockInfo:** nó mô tả đối tượng **đang chờ**, không phải “khóa duy nhất thread sở hữu”. Một owner thread có thể đang sở hữu `ReentrantLock` nhưng lại đồng thời WAITING trên `CountDownLatch`; khi đó `getLockInfo()` có thể trỏ tới internal latch synchronizer, trong khi `getLockedSynchronizers()` cho biết lock riêng đang giữ.

### 4.3. MonitorInfo mở rộng LockInfo

`MonitorInfo extends LockInfo`, nên nó có các trường `className` và `identityHashCode`, cùng metadata riêng:

- `getLockedStackDepth()`: vị trí frame trong `ThreadInfo.getStackTrace()` nơi monitor được lấy.
- `getLockedStackFrame()`: frame acquisition tương ứng nếu có.

`LockInfo` của ownable synchronizer chỉ cung cấp **tên class và identity hash** theo hợp đồng chung, không có `getLockedStackFrame()` như `MonitorInfo`. Vì vậy đừng giả định hai arrays có cùng cấu trúc.

### 4.4. Tên ReentrantLock và đối tượng AQS bên trong

Với `ReentrantLock`, `getLockedSynchronizers()` thường chứa một `LockInfo` có class name liên quan **`ReentrantLock$NonfairSync`/`ReentrantLock$FairSync`** hoặc subclass AQS tương ứng, **không nhất thiết class name đúng bằng `java.util.concurrent.locks.ReentrantLock`**.

Đó là **synchronizer internal owner**, không phải API public để cast sang `ReentrantLock`. Đừng hardcode chính xác private nested class name làm application logic: implementation details có thể đổi theo phiên bản JDK.

Ví dụ kiểm thử chỉ xác nhận tên class có chứa `ReentrantLock` và identity của `LockInfo` ở owner trùng với `getLockInfo()` của waiter trong **cùng snapshot**.

## 5. Thread states: đọc đúng, không suy đoán quá mức

Theo `Thread.State`:

| Trạng thái | Khi nào phổ biến | Lock tương ứng trong bài |
| --- | --- | --- |
| `NEW` | Thread chưa bắt đầu. | Chưa có contention. |
| `RUNNABLE` | Có thể chạy trong JVM; không nhất thiết đang dùng CPU liên tục. | Có thể đang giữ monitor/ownable lock. |
| `BLOCKED` | Đợi lấy/re-lấy một **object monitor**. | `synchronized`; không phải mọi kiểu chờ. |
| `WAITING` | Đợi vô thời hạn do `Object.wait`, `Thread.join`, `LockSupport.park`, v.v. | `ReentrantLock.lock()` contested thường WAITING. |
| `TIMED_WAITING` | Chờ có giới hạn do `sleep`, timed `wait/join/park`. | `tryLock(timeout)`/`Condition.await(timeout)` có thể ở đây. |
| `TERMINATED` | Thread đã hoàn thành. | Snapshot có thể không còn ThreadInfo. |

**Thread state là trạng thái tức thời**, không chứng minh mức độ contention theo thời gian. Một thread có thể vừa ở `BLOCKED`, ngay sau đó được owner nhả lock và chuyển `RUNNABLE`. Hãy kết hợp snapshot, timing, stack trace, owner chain, metrics và repeated observations.

### 5.1. BLOCKED không đồng nghĩa deadlock

Nếu thread A giữ monitor để làm việc 20 ms còn B đang `BLOCKED` chờ, đó là contention bình thường. Deadlock đòi hỏi **chu trình chờ lẫn nhau** không thể tiến triển theo mô hình khóa liên quan.

Một thread WAITING trên ReentrantLock cũng không tự tạo deadlock. Nó có thể nhận lock sau khi owner hoàn tất công việc.

### 5.2. Một thread có thể sở hữu cả hai loại khóa

`ThreadInfo.getLockedMonitors()` và `getLockedSynchronizers()` không phân hoạch threads thành hai loại cố định. Cùng một thread có thể:

```java
synchronized (guard) {
    reentrant.lock();
    try {
        // Thread đang giữ object monitor và ownable synchronizer.
    } finally {
        reentrant.unlock();
    }
}
```

Đây là mảnh code; cần `guard`/`reentrant`, imports và object lifecycle. Trong trường hợp đó **hai arrays đều có thể không rỗng**. Nếu một thread lại chờ trên condition/latch trong khi giữ một lock khác, cần phân tích đầy đủ lock order để tránh deadlock.

## 6. ThreadMXBean không thay công cụ synchronization

Thông tin `ThreadInfo` là snapshot dùng cho **diagnostics**, không phải primitive để quyết định:

```text
if (threadInfo.getLockedMonitors().length == 0) {
    // Sai: kết luận an toàn để truy cập shared data không khóa.
}
```

Snapshot có thể đã lỗi thời ngay khi trả về. Ngay cả khi không thấy khóa, thread khác vẫn có thể lấy lock ngay sau đó. Điều khiển tính đúng của concurrency phải dùng primitives như `synchronized`, `Lock`, concurrent collections, atomics, semaphores, conditions... chứ không dựa vào management metadata.

**Đặc biệt quan trọng:** `ThreadMXBean.getThreadInfo` và `ThreadInfo.getLockOwnerId` không phải access control. Không dùng nó để xác định user/tenant hoặc phân quyền business operations.

### 6.1. Thread contention monitoring là tính năng riêng

`ThreadMXBean.isThreadContentionMonitoringSupported()` cho biết có thể đo thời gian/counters contention hay không. Nếu có, `setThreadContentionMonitoringEnabled(true)` bật thống kê có thể tốn chi phí.

- `ThreadInfo.getBlockedCount()/getBlockedTime()` chủ yếu đo việc chờ **monitor acquisition/reentry**.
- `ThreadInfo.getWaitedCount()/getWaitedTime()` liên quan thời gian thread ở **WAITING/TIMED_WAITING** theo API.
- `getBlockedTime()/getWaitedTime()` có thể trả `-1` khi monitoring không bật/không hỗ trợ.
- Đừng dùng `blockedTime` như một thước đo duy nhất cho `ReentrantLock` contention; ReentrantLock có thể park WAITING chứ không phải monitor BLOCKED.
- Tách CPU time monitoring (`isThreadCpuTimeSupported`) khỏi lock ownership; CPU clock không tự nói thread đang chờ lock nào.

Trong bài demo, **không bật contention monitoring** để tránh thay đổi cấu hình JVM toàn cục; nó chỉ chụp trạng thái/sở hữu khóa và kiểm tra các dữ kiện trực tiếp.

## 7. Nhận biết deadlock: monitor-only vs cả ownable synchronizers

`ThreadMXBean` cung cấp hai method **không đồng nhất**:

| Method | Phạm vi phát hiện | Điều không đảm bảo |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Chu trình chờ **object monitors** giữa platform threads. | Không phát hiện chu trình dùng ownable synchronizers. |
| `findDeadlockedThreads()` | Chu trình chờ **object monitors hoặc ownable synchronizers** giữa platform threads. | Không phải phát hiện mọi kiểu resource deadlock; không phát hiện chu trình có virtual threads theo Java SE 26 API. |

Nếu JVM không hỗ trợ ownable synchronizer monitoring, `findDeadlockedThreads()` có thể ném `UnsupportedOperationException`. Cả hai API được thiết kế cho troubleshooting và có thể tốn chi phí.

### 7.1. Ví dụ lý thuyết của monitor deadlock

```text
Platform Thread A
  owns monitor X
  waits to acquire monitor Y

Platform Thread B
  owns monitor Y
  waits to acquire monitor X

=> findMonitorDeadlockedThreads có thể phát hiện chu trình.
=> findDeadlockedThreads cũng có thể phát hiện.
```

### 7.2. Ví dụ deadlock qua ReentrantLock

```text
Platform Thread A
  owns ReentrantLock L1 (ownable)
  waits to acquire ReentrantLock L2

Platform Thread B
  owns ReentrantLock L2 (ownable)
  waits to acquire ReentrantLock L1

=> findMonitorDeadlockedThreads không đủ phạm vi.
=> findDeadlockedThreads có thể phát hiện chu trình.
```

Đó là **sơ đồ**, không phải code thực thi. Chương trình demo bên dưới **cố ý không tạo deadlock thật** để tránh treo JVM hoặc để lại threads không thể phục hồi; nó kiểm tra ownership/waiting bằng latches có timeout và `finally` release.

### 7.3. Phòng tránh deadlock thay vì chỉ phát hiện

Các biện pháp:

- Chốt **thứ tự lấy khóa nhất quán** trên mọi code paths.
- Giảm số locks giữ đồng thời và thời gian critical sections.
- Không gọi I/O lâu trong `synchronized` hoặc `ReentrantLock` khi có thể tránh.
- Dùng `tryLock(timeout)`/`lockInterruptibly` nếu thiết kế cần hủy/từ bỏ chờ.
- Đảm bảo mọi `lock()` có `unlock()` trong `finally`.
- Không dùng `Thread.stop`, `Thread.suspend` hoặc các kỹ thuật deprecated/unsafe để “giải quyết” deadlock.
- Đánh giá mixed monitor+ownable order ở code reviews.
- Có thread dumps và metrics khi gặp sự cố.

## 8. Công cụ chẩn đoán thực tế

**Trong code**: dùng `ManagementFactory.getThreadMXBean()`, kiểm tra support flags, lấy snapshots theo thread IDs cụ thể thay vì dump mọi thread liên tục.

**Trên hệ thống**: `jcmd` của JDK có các lệnh để lấy thread dump, nhưng tên command/capabilities phụ thuộc phiên bản JVM; kiểm tra:

```bash
jcmd -l
jcmd <pid> help
jcmd <pid> Thread.print -l
```

`<pid>` ở trên là placeholder của lệnh mẫu, không phải nội dung README sẽ chạy nguyên xi. `Thread.print -l` được tài liệu Java SE 26 mô tả là in **platform threads và mounted virtual threads** cùng `java.util.concurrent` locks. Trên JDK hiện hành, `Thread.dump_to_file` hỗ trợ xuất toàn bộ threads ra file ở dạng plain/JSON, hữu ích khi phân tích virtual threads quy mô lớn:

```bash
jcmd <pid> Thread.dump_to_file -format=json /tmp/threads.json
```

**Đường dẫn và PID ở các lệnh này cần thay theo máy, hệ điều hành và quyền**. Không chạy lệnh trên môi trường không có quyền, và không lộ thread dumps có thể chứa thông tin nhạy cảm (class names, stack frames, arguments và references). Trên Windows, dùng đường dẫn file thực theo chuẩn Windows; `/tmp` chỉ là ví dụ Linux.

### 8.1. Giới hạn quan trọng với virtual threads

Trên Java 21+ có virtual threads. Tài liệu `ThreadMXBean` Java SE 26 nhấn mạnh **không hỗ trợ monitoring/management của virtual threads**; `getAllThreadIds()` chỉ có platform thread IDs; `getThreadInfo(virtualThreadId)` trả null. `dumpAllThreads(...)` và `findDeadlockedThreads()` trong MXBean không phát hiện đầy đủ virtual threads.

Vì vậy:

- Demo dùng `new Thread(...)` kiểu platform phù hợp Java 17.
- Đừng lấy `ThreadMXBean.getThreadCount()` làm tổng số **platform + virtual** threads trên JDK hiện đại.
- Khi điều tra virtual thread contention, dùng công cụ có hỗ trợ như `jcmd Thread.dump_to_file`, JFR events và observability phù hợp.
- Đừng lặp lại lời khẳng định lỗi thời rằng **mọi synchronized đều gây virtual-thread pinning**; hành vi đã thay đổi qua các phiên bản JVM hiện hành, cần kiểm tra JDK mục tiêu. Bài này không dùng pinning như tiêu chí phân biệt monitor/ownable.

## 9. Ví dụ hoàn chỉnh: MonitorVsOwnableDemo.java

Chương trình tạo hai tình huống tranh chấp:

**Tình huống A — monitor:**

- `monOwner` vào `synchronized (monitor)` và giữ object monitor.
- `monWaiter` cố vào cùng khối, trở thành `BLOCKED`.
- Snapshot: `monOwner.getLockedMonitors` chứa đúng identity hash của `monitor`; `monWaiter.getLockInfo` trỏ tới monitor đó và `getLockOwnerId` trỏ về `monOwner`.
- `MonitorInfo` có acquisition stack frame/depth.

**Tình huống B — ownable synchronizer:**

- `synOwner` lấy `ReentrantLock` và giữ nó.
- `synWaiter` gọi `lock()` và park vì lock đã bị giữ; trạng thái `WAITING`/`TIMED_WAITING` theo thời điểm.
- Snapshot: `synOwner.getLockedSynchronizers` chứa AQS `LockInfo`; `synWaiter.getLockInfo` trùng class/identity và `getLockOwnerId` trỏ về `synOwner`.
- Không nhầm AQS internal sync với intrinsic monitor; `synOwner.getLockedMonitors()` rỗng trong trường hợp kiểm thử.

`CountDownLatch` giữ owners tại critical sections trong khoảng thời gian có kiểm soát. Main chờ hai waiters vào trạng thái tranh chấp (có deadline 5 giây) trước khi chụp snapshot. Cuối cùng `release.countDown()` đánh thức owners, các threads thoát và được `join`.

**Không cần dependency ngoài JDK. Không tạo network connection. Không có locks vĩnh viễn hoặc deadlock không thể dọn.**

### 9.1. Source đầy đủ

Lưu đúng tên file **`MonitorVsOwnableDemo.java`**, mã hóa UTF-8:

```java
import java.lang.management.LockInfo;
import java.lang.management.ManagementFactory;
import java.lang.management.MonitorInfo;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class MonitorVsOwnableDemo {
    private static int passed;

    private static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        passed++;
        System.out.println(name + "=PASS");
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Latch deadline exceeded");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    private static void untilBlocked(Thread monitorWaiter,
                                     Thread synchronizerWaiter)
            throws InterruptedException {
        long end = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < end) {
            Thread.State monitorState = monitorWaiter.getState();
            Thread.State syncState = synchronizerWaiter.getState();
            if (monitorState == Thread.State.BLOCKED
                    && (syncState == Thread.State.WAITING
                    || syncState == Thread.State.TIMED_WAITING)) {
                return;
            }
            Thread.sleep(5);
        }
        throw new AssertionError("Contending threads did not park/block");
    }

    private static ThreadInfo[] snapshot(
            ThreadMXBean bean, Thread... threads) {
        long[] ids = new long[threads.length];
        for (int i = 0; i < threads.length; i++) {
            ids[i] = threads[i].getId(); // Compatible with Java 17
        }
        return bean.getThreadInfo(ids, true, true);
    }

    private static boolean matches(LockInfo info, LockInfo target) {
        return info != null && target != null
                && info.getClassName().equals(target.getClassName())
                && info.getIdentityHashCode()
                       == target.getIdentityHashCode();
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        boolean monitors = bean.isObjectMonitorUsageSupported();
        boolean synchronizers = bean.isSynchronizerUsageSupported();
        if (!monitors || !synchronizers) {
            System.out.println(
                    "SKIPPED: JVM lacks detailed lock monitoring");
            return;
        }

        Object monitor = new Object();
        ReentrantLock explicit = new ReentrantLock();
        CountDownLatch monitorHeld = new CountDownLatch(1);
        CountDownLatch explicitHeld = new CountDownLatch(1);
        CountDownLatch monitorAttempt = new CountDownLatch(1);
        CountDownLatch explicitAttempt = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread monOwner = new Thread(() -> {
            synchronized (monitor) {
                monitorHeld.countDown();
                await(release);
            }
        }, "demo-monitor-owner");

        Thread synOwner = new Thread(() -> {
            explicit.lock();
            try {
                explicitHeld.countDown();
                await(release);
            } finally {
                explicit.unlock();
            }
        }, "demo-ownable-owner");

        Thread monWaiter = new Thread(() -> {
            monitorAttempt.countDown();
            synchronized (monitor) {
                // Monitor được lấy sau khi owner nhả.
            }
        }, "demo-monitor-waiter");

        Thread synWaiter = new Thread(() -> {
            explicitAttempt.countDown();
            explicit.lock();
            try {
                // Ownable synchronizer được lấy sau khi owner nhả.
            } finally {
                explicit.unlock();
            }
        }, "demo-ownable-waiter");

        try {
            monOwner.start();
            synOwner.start();
            await(monitorHeld);
            await(explicitHeld);

            monWaiter.start();
            synWaiter.start();
            await(monitorAttempt);
            await(explicitAttempt);
            untilBlocked(monWaiter, synWaiter);

            ThreadInfo[] infos = snapshot(bean,
                    monOwner, monWaiter, synOwner, synWaiter);
            ThreadInfo mi = infos[0], mw = infos[1],
                    si = infos[2], sw = infos[3];

            check("platformThreadsVisible",
                    mi != null && mw != null
                    && si != null && sw != null);
            check("monitorsSupported", monitors);
            check("ownableSynchronizersSupported", synchronizers);
            check("monitorWaiterBlocked",
                    mw.getThreadState() == Thread.State.BLOCKED);
            check("monitorOwnerId",
                    mw.getLockOwnerId() == monOwner.getId());
            check("monitorOwnerName", "demo-monitor-owner".equals(
                    mw.getLockOwnerName()));

            MonitorInfo ownedMonitor = null;
            for (MonitorInfo item : mi.getLockedMonitors()) {
                if (item.getClassName().equals(Object.class.getName())
                        && item.getIdentityHashCode()
                        == System.identityHashCode(monitor)) {
                    ownedMonitor = item;
                }
            }
            check("monitorOwnerHasMonitor", ownedMonitor != null);
            check("monitorHasAcquisitionFrame", ownedMonitor != null
                    && ownedMonitor.getLockedStackDepth() >= 0
                    && ownedMonitor.getLockedStackFrame() != null);
            check("monitorWaiterTargetSameObject",
                    matches(mw.getLockInfo(), ownedMonitor));
            check("monitorOwnerHasNoExclusiveAQS",
                    mi.getLockedSynchronizers().length == 0);
            check("monitorWaiterOwnsNoMonitors",
                    mw.getLockedMonitors().length == 0);

            check("ownableWaiterParked",
                    sw.getThreadState() == Thread.State.WAITING
                    || sw.getThreadState() == Thread.State.TIMED_WAITING);
            check("ownableOwnerId",
                    sw.getLockOwnerId() == synOwner.getId());
            check("ownableOwnerName", "demo-ownable-owner".equals(
                    sw.getLockOwnerName()));
            check("ownableOwnerHasNoMonitors",
                    si.getLockedMonitors().length == 0);

            LockInfo[] ownedSyncs = si.getLockedSynchronizers();
            check("ownableOwnerHasSynchronizer",
                    ownedSyncs.length >= 1);
            check("ownableLockIsAQS", ownedSyncs.length >= 1
                    && ownedSyncs[0].getClassName()
                    .contains("ReentrantLock"));
            boolean same = false;
            for (LockInfo lock : ownedSyncs) {
                if (matches(sw.getLockInfo(), lock)) same = true;
            }
            check("ownableWaiterTargetSameSynchronizer", same);
            check("ownableWaiterOwnsNoSynchronizers",
                    sw.getLockedSynchronizers().length == 0);
            check("ownableWaiterNotMonitorBlocked",
                    sw.getThreadState() != Thread.State.BLOCKED);
            check("twoLockClassesDiffer",
                    !mw.getLockInfo().getClassName().equals(
                            sw.getLockInfo().getClassName()));
            check("lockedMonitorsSubclassLockInfo",
                    ownedMonitor instanceof LockInfo);

            ThreadInfo[] lightweight = bean.getThreadInfo(
                    new long[]{
                        monOwner.getId(), synOwner.getId()
                    }, false, false);
            check("lightweightSnapshotNoOwnedLocks",
                    lightweight[0] != null && lightweight[1] != null
                    && lightweight[0].getLockedMonitors().length == 0
                    && lightweight[1].getLockedSynchronizers().length == 0);

            final int expected = 23;
            if (passed != expected) {
                throw new AssertionError("Expected " + expected
                        + " assertions, got " + passed);
            }
            System.out.println("checks=" + passed + "/" + expected);
        } finally {
            release.countDown();
            for (Thread t : new Thread[]{
                    monOwner, monWaiter, synOwner, synWaiter}) {
                if (t.isAlive()) {
                    t.join(3000);
                    if (t.isAlive()) t.interrupt();
                }
            }
        }
    }
}
```

### 9.2. Lệnh biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 MonitorVsOwnableDemo.java
java MonitorVsOwnableDemo
```

Không cần Maven, Gradle hoặc thư viện bên ngoài. `ThreadMXBean` và `ThreadInfo` thuộc module chuẩn `java.management`; `ReentrantLock`, `CountDownLatch` thuộc `java.base`. Nếu dùng named module, khai báo `requires java.management;`. Java 17 chưa có virtual thread API chính thức nên code chỉ dùng platform threads.

**Điều kiện capability:** trên JVM không hỗ trợ monitor/synchronizer ownership introspection, chương trình in một dòng:

```text
SKIPPED: JVM lacks detailed lock monitoring
```

và không chạy assertions, để tránh thông tin sai. Trên JDK đã thử, cả hai capability flags đều `true` và toàn bộ 23 assertions chạy.

### 9.3. Stdout chính xác đã kiểm chứng trên JDK chạy thử

```text
platformThreadsVisible=PASS
monitorsSupported=PASS
ownableSynchronizersSupported=PASS
monitorWaiterBlocked=PASS
monitorOwnerId=PASS
monitorOwnerName=PASS
monitorOwnerHasMonitor=PASS
monitorHasAcquisitionFrame=PASS
monitorWaiterTargetSameObject=PASS
monitorOwnerHasNoExclusiveAQS=PASS
monitorWaiterOwnsNoMonitors=PASS
ownableWaiterParked=PASS
ownableOwnerId=PASS
ownableOwnerName=PASS
ownableOwnerHasNoMonitors=PASS
ownableOwnerHasSynchronizer=PASS
ownableLockIsAQS=PASS
ownableWaiterTargetSameSynchronizer=PASS
ownableWaiterOwnsNoSynchronizers=PASS
ownableWaiterNotMonitorBlocked=PASS
twoLockClassesDiffer=PASS
lockedMonitorsSubclassLockInfo=PASS
lightweightSnapshotNoOwnedLocks=PASS
checks=23/23
```

**23 dòng PASS và một dòng tổng kết.** Chương trình không in giá trị thread IDs, identity hash hoặc thời điểm nên output có thể so khớp chính xác trên JVM hỗ trợ tính năng. Vì scheduler/runtime khác nhau, có thể cần tăng deadline test trên máy CI quá tải, không coi timing trong test như benchmark throughput.

## 10. Giải thích kết quả của chương trình

### 10.1. Giai đoạn thiết lập threads

Hai owners được khởi động trước và `CountDownLatch` xác nhận họ đã giữ khóa tương ứng. Sau đó mới khởi động hai waiters. `untilBlocked(...)` đợi tới khi một waiter ở `BLOCKED` và waiter kia ở `WAITING`/`TIMED_WAITING`.

Bởi vậy snapshot có điều kiện rõ ràng, không phụ thuộc việc `Thread.sleep(100)` tình cờ cho thread chạy đúng lịch. Có deadline 5 giây để fail thay vì treo vĩnh viễn.

### 10.2. Các checks của monitor

- `monitorWaiterBlocked`: `monWaiter` đang đợi intrinsic monitor.
- `monitorOwnerId` và `monitorOwnerName`: JMX cho biết đúng luồng đang sở hữu monitor.
- `monitorOwnerHasMonitor`: `getLockedMonitors()` của owner có khóa `java.lang.Object` cùng `System.identityHashCode(monitor)`.
- `monitorHasAcquisitionFrame`: `MonitorInfo` có frame nơi monitor được lấy.
- `monitorWaiterTargetSameObject`: `getLockInfo()` của waiter trùng với `MonitorInfo` của owner theo class/identity.
- `monitorOwnerHasNoExclusiveAQS`: monitor owner trong tình huống này không sở hữu ownable synchronizer nào.
- `monitorWaiterOwnsNoMonitors`: waiter chưa lấy được monitor đang tranh chấp.

**Đừng áp dụng `getLockedMonitors().length==0` cho một thread vừa chưa yêu cầu monitor metadata**, bởi overload `getThreadInfo(..., false, false)` luôn bỏ các arrays ownership.

### 10.3. Các checks của ownable synchronizer

- `ownableWaiterParked`: `synWaiter` đợi `ReentrantLock`, thường `WAITING`/`TIMED_WAITING`.
- `ownableOwnerId`/`ownableOwnerName`: owner của synchronizer là `synOwner`.
- `ownableOwnerHasNoMonitors`: thread này không lấy intrinsic monitor nào trong test.
- `ownableOwnerHasSynchronizer`: `getLockedSynchronizers()` có `LockInfo` đại diện AQS state.
- `ownableLockIsAQS`: class name của synchronizer liên quan đến ReentrantLock, chứ không phải `Object` intrinsic monitor.
- `ownableWaiterTargetSameSynchronizer`: `getLockInfo` của waiter khớp class/identity của synchronizer do owner giữ.
- `ownableWaiterOwnsNoSynchronizers`: waiter chưa có exclusive ownership.
- `ownableWaiterNotMonitorBlocked`: không ở `BLOCKED` chỉ vì không lấy được ReentrantLock.
- `twoLockClassesDiffer`: monitor object và ReentrantLock internal synchronizer là hai loại lock khác nhau.
- `lockedMonitorsSubclassLockInfo`: `MonitorInfo` kế thừa `LockInfo`.

### 10.4. Lightweight snapshot không nói điều gì?

`lightweightSnapshotNoOwnedLocks` gọi overload `getThreadInfo(ids,false,false)`. Các arrays ownership rỗng **dù owner vẫn đang giữ monitor/ReentrantLock**. Đây là bằng chứng rằng **“array rỗng” chưa đủ kết luận không có khóa**: phải xem capabilities, overload flags, thread lifecycle và thời điểm snapshot.

### 10.5. Cleanup

`finally` gọi `release.countDown()` để hai owner tiếp tục và thả lock; sau đó `join` những threads còn sống, và interrupt nếu cần. Không có deadlock không thể phục hồi. Đoạn cleanup phù hợp môi trường học tập, không phải engine đảm bảo dừng mọi user-supplied blocking operation trong production.

## 11. So sánh trực tiếp hai cơ chế

| Câu hỏi | Object monitor | Ownable synchronizer |
| --- | --- | --- |
| Tạo bằng gì? | Mọi object dùng trong `synchronized`. | Synchronizer độc quyền, ví dụ AQS bên trong `ReentrantLock`. |
| Lấy khóa bằng gì? | `monitorenter` / vào `synchronized`. | `lock()`/`tryLock()`/`lockInterruptibly()` của API Lock. |
| Trả khóa bằng gì? | Ra khối `synchronized`, JVM tự thoát monitor. | `unlock()` trong `finally`; cần đúng owner. |
| Waiter bị tranh chấp thường ở state nào? | `BLOCKED`. | `WAITING` hoặc `TIMED_WAITING` do park. |
| Owner được ghi ở đâu? | JVM monitor ownership. | AQS/AbstractOwnableSynchronizer owner state. |
| JMX locked array | `getLockedMonitors()`. | `getLockedSynchronizers()`. |
| Loại item | `MonitorInfo`. | `LockInfo`. |
| Stack frame acquisition? | `MonitorInfo.getLockedStackFrame()` nếu có. | Không có MonitorInfo acquisition-frame API tương đương. |
| Waiting target | `ThreadInfo.getLockInfo()`. | `ThreadInfo.getLockInfo()` có thể là AQS sync/parking blocker. |
| Deadlock monitor-only API | `findMonitorDeadlockedThreads`. | Không đủ phạm vi khi có ownable lock. |
| Deadlock rộng hơn | `findDeadlockedThreads`. | `findDeadlockedThreads` trên platform threads. |
| Có timeout lấy khóa không? | Không có timeout acquisition gắn trực tiếp với `synchronized`. | `tryLock(timeout, unit)` với ReentrantLock. |
| Có interruptible acquisition không? | Không có `synchronized.lockInterruptibly`. | `lockInterruptibly()` hỗ trợ. |
| Có điều kiện đợi? | `Object.wait/notify/notifyAll`. | `Condition.await/signal/signalAll`. |
| Có tự giải quyết deadlock không? | Không. | Không. |

Đừng nói monitor “đã lỗi thời” chỉ vì có `ReentrantLock`. Cả `synchronized` và `ReentrantLock` đều là công cụ hiện hành; lựa chọn phụ thuộc nhu cầu về interruptibility, timed acquisition, conditions, độ dễ đọc và contention/performance đo được.

## 12. Sai lầm thường gặp khi xem thread dumps

| Sai lầm | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “Bất cứ thread nào phải chờ đều BLOCKED.” | Bỏ sót ReentrantLock/park waits. | BLOCKED chủ yếu là chờ monitor; WAITING cũng có thể là lock contention. |
| “WAITING là không giữ khóa.” | Bỏ sót owner đang giữ lock khác trong khi đợi latch/condition. | Xem cả lockedMonitors và lockedSynchronizers. |
| “getLockInfo là lock thread đã giữ.” | Nhầm waiting target và ownership. | getLockInfo cho đối tượng đang chờ. |
| “getLockedMonitors rỗng nghĩa không có khóa.” | Bỏ qua ownable synchronizers hoặc snapshot flags=false. | Kiểm tra hai arrays và flags. |
| “ReentrantLock hiện dưới class ReentrantLock.” | Không tìm thấy đúng khóa. | Có thể là AQS internal sync LockInfo. |
| “Mọi AQS đều có một owner.” | Đọc sai Semaphore/ReadLock/latch. | Ownable là ownership độc quyền đúng contract. |
| “MonitorInfo và LockInfo có cùng API stack frame.” | Không thể đọc acquisition stack của ownable như monitor. | MonitorInfo bổ sung frame/depth. |
| “ThreadInfo là snapshot hoàn toàn nhất quán mãi mãi.” | Quyết định dựa trên dữ liệu đã đổi. | Dùng cho diagnostic, không điều khiển synchronization. |
| “findMonitorDeadlockedThreads tìm mọi deadlock.” | Không thấy chu trình ReentrantLock. | Dùng findDeadlockedThreads khi hỗ trợ. |
| “findDeadlockedThreads tìm deadlock virtual threads.” | Bỏ sót issue trên Java 21+. | ThreadMXBean chỉ platform threads; dùng tools cho virtual. |
| “ThreadMXBean.getThreadCount là toàn bộ platform + virtual.” | Metrics sai khi có nhiều virtual threads. | Theo Java SE 26, chỉ đếm platform threads. |
| “BlockedTime đo mọi lần chờ ReentrantLock.” | Sai số liệu contention. | BlockedTime chủ yếu monitor; thêm JFR/lock metrics. |
| “Một WAITING thread đồng nghĩa deadlock.” | Báo động giả với latch/queue/sleep. | Tìm owner chain và cycles. |
| “Synchronized trên ReentrantLock object == gọi lock.lock.” | Critical sections không bảo vệ lẫn nhau. | Intrinsic monitor và AQS lock tách biệt. |
| “Dùng Thread.stop/suspend để giải deadlock.” | Rất nguy hiểm, deprecated. | Thiết kế lock order, cancel/restart có kiểm soát. |
| “Dump tất cả threads mỗi giây không tốn gì.” | Có thể ảnh hưởng latency/overhead. | Lấy mẫu có kiểm soát, scope hẹp. |
| “Tên thread và stack trace là dữ liệu công khai.” | Có thể rò thông tin nội bộ. | Giới hạn quyền truy cập, bảo vệ dumps. |

## 13. Hướng dẫn chẩn đoán một ứng dụng chậm

**Bước 1 — Xác định hiện tượng.** Latency cao, thread pool không tiến triển, requests treo hay CPU cao? Không mặc định lỗi do monitor.

**Bước 2 — Lấy snapshot đúng phạm vi.** Trên platform threads, kiểm tra `ThreadMXBean` support flags và lấy `getThreadInfo(ids,true,true)` cho nhóm thread nghi ngờ. Nếu nhiều virtual threads, chọn tool có hỗ trợ virtual threads.

**Bước 3 — Phân loại state.** BLOCKED monitor entry, WAITING park/join/condition, TIMED_WAITING có deadline, RUNNABLE nhưng có thể chờ native I/O. Đọc stack trace song song với state.

**Bước 4 — Kiểm tra waiting target.** `getLockInfo()` và `getLockOwnerId()` nếu có, không dựa vào tên method duy nhất. Với parked AQS, xác minh internal synchronizer/owner.

**Bước 5 — Kiểm tra locks đã giữ.** `getLockedMonitors()` và `getLockedSynchronizers()` của owner. Nếu một thread đang giữ monitor rồi chờ ownable lock, vẽ dependency chain.

**Bước 6 — Tìm cycles.** Nếu nghi deadlock platform threads, dùng `findDeadlockedThreads()` khi supported; monitor-only API không đủ cho mixed locks.

**Bước 7 — Tìm nguyên nhân giữ khóa lâu.** I/O dưới critical section, nhiều work trong synchronized, missed unlock, await/notify sai, lock order ngược, excessive contention hay thread starvation.

**Bước 8 — Sửa và kiểm thử.** Giảm lock scope, nhất quán lock order, bounded waits, try/finally, load test và regression tests. Dùng snapshot để xác minh thay đổi, không đưa code management API vào đường critical path.

## 14. Checklist thực hành hiện hành

- [ ] Đã xác định luồng là platform hay virtual?
- [ ] Đã kiểm tra `isObjectMonitorUsageSupported` và `isSynchronizerUsageSupported`?
- [ ] Có dùng đúng overload `getThreadInfo(ids,true,true)` khi muốn ownership?
- [ ] Có kiểm tra entry `null` khi thread biến mất?
- [ ] Có phân biệt `getLockInfo` (đang đợi) với `getLockedMonitors`/`getLockedSynchronizers` (đang giữ)?
- [ ] Có xem `Thread.State.BLOCKED` đúng là monitor entry?
- [ ] Có xem WAITING/PARKED và call stacks thay vì kết luận “luồng rảnh”?
- [ ] Có kiểm tra `MonitorInfo.getLockedStackFrame` nếu được JVM hỗ trợ?
- [ ] Có đọc class/identity của LockInfo mà không phụ thuộc private AQS class name cứng?
- [ ] Có kiểm tra waiting owner ID/name theo snapshot?
- [ ] Có nhớ thread có thể sở hữu monitor và ownable synchronizer cùng lúc?
- [ ] Có phân biệt `Object.wait`, `Condition.await` và `ReentrantLock.lock`?
- [ ] Có nhớ shared read locks/semaphores không nhất thiết có exclusive owner?
- [ ] Có dùng `findDeadlockedThreads` khi suspect mixed lock cycles?
- [ ] Có tránh dùng `ThreadMXBean` để ra quyết định synchronization lúc runtime?
- [ ] Có bảo vệ thread dump/logs và hạn chế tần suất snapshot nặng?
- [ ] Có kiểm tra contention counters chỉ khi contention monitoring supported/enabled?
- [ ] Có dùng tools cho virtual threads vì `ThreadMXBean` không hỗ trợ?
- [ ] Có lock ordering và `try/finally/unlock` được review?
- [ ] Có test timeout/cleanup để không tạo deadlocks không thể dọn trong CI?

## 15. Bài tập thực hành

**A — Monitor contention.** Chạy `MonitorVsOwnableDemo`, tìm `monitorWaiterBlocked=PASS` và giải thích vì sao thread A giữ monitor còn B ở BLOCKED.

**B — ReentrantLock contention.** Tìm `ownableWaiterParked=PASS`; tại sao thread tranh chấp không thuộc BLOCKED mặc dù chưa có khóa?

**C — Hai arrays.** In số `getLockedMonitors`/`getLockedSynchronizers` của hai owners trong lab, không in dữ liệu nhạy cảm. Giải thích sự khác nhau.

**D — Waiting target.** So `mw.getLockInfo()` với MonitorInfo của owner, `sw.getLockInfo()` với ownable LockInfo của owner.

**E — Thread IDs.** So `getLockOwnerId()` với `Thread.getId()` trong Java17; vì sao không hardcode thread IDs trong expected stdout?

**F — Stack acquisition.** In `MonitorInfo.getLockedStackDepth()/getLockedStackFrame()`. Trong trường hợp thiếu stack metadata, nên làm gì?

**G — Lightweight snapshot.** Gọi `getThreadInfo(ids,false,false)` rồi giải thích vì sao ownership arrays rỗng dù threads vẫn giữ khóa.

**H — Mixed locks.** Viết ví dụ giữ monitor A rồi ReentrantLock B. Chỉ chạy với timeout/cleanup; dự đoán hai locked arrays của owner.

**I — Object.wait.** Thread giữ monitor rồi gọi `wait`, thread khác notify. Phân biệt WAITING, BLOCKED khi reentry và monitor ownership.

**J — Condition.await.** Tạo `Condition` từ ReentrantLock và cho thread await. Kiểm tra lock được nhả khi đợi và lấy lại trước khi tiếp tục.

**K — Semaphore.** Dùng `Semaphore` cho 3 workers. Vì sao không thể suy 3 permits đang giữ thành 3 exclusive ownable synchronizers?

**L — ReadWriteLock.** So owner của writer với nhiều read lock holders, phân biệt exclusive vs shared mode.

**M — Deadlock lý thuyết.** Vẽ chu trình A giữ monitor X chờ ReentrantLock Y, B giữ Y chờ X; chọn API chẩn đoán và cách sửa lock order.

**N — Instrumentation.** Khi JVM hỗ trợ, bật contention monitoring trong môi trường kiểm thử, so blockedTime và waitedTime. Không bật bừa trên production.

**O — Virtual threads.** Trên JDK21+, tạo virtual thread riêng và tra `ThreadMXBean.getThreadInfo`; so với tool hỗ trợ virtual threads, không dùng source Java17 của bài để gọi API không có.

**P — Operations.** Lấy thread dump theo yêu cầu, kiểm tra quyền truy cập, thông tin nhạy cảm, snapshot overhead và retention policy.

## 16. Câu hỏi tự kiểm tra

**1. Object monitor được lấy bằng gì?** — `synchronized` statement/method trên object.

**2. Ownable synchronizer có nghĩa gì?** — Synchronizer có thể được sở hữu độc quyền bởi một thread; ví dụ AQS bên trong ReentrantLock.

**3. AbstractOwnableSynchronizer tự triển khai mutual exclusion?** — Không; nó cung cấp khái niệm owner cho subclasses/tools.

**4. `Thread.State.BLOCKED` thường là khi nào?** — Chờ monitor lock khi vào/reenter synchronized.

**5. ReentrantLock tranh chấp thường đưa waiter tới state gì?** — `WAITING` do park, hoặc `TIMED_WAITING` với timed operations.

**6. `getLockedMonitors()` trả gì?** — `MonitorInfo[]` của monitors thread đang sở hữu, khi requested/supported.

**7. `getLockedSynchronizers()` trả gì?** — `LockInfo[]` của ownable synchronizers thread đang sở hữu, khi requested/supported.

**8. `getLockInfo()` là ownership array?** — Không; thông tin đối tượng thread đang chờ.

**9. MonitorInfo hơn LockInfo ở metadata nào?** — `getLockedStackDepth/getLockedStackFrame` nơi monitor được lấy.

**10. LockInfo của ReentrantLock phải class name đúng `ReentrantLock`?** — Không; thường là internal AQS sync class.

**11. Thread vừa WAITING có thể vẫn giữ lock khác?** — Có.

**12. Vì sao `getThreadInfo(ids,false,false)` trả ownership arrays rỗng?** — Vì caller không yêu cầu metadata locked monitors/synchronizers.

**13. `findMonitorDeadlockedThreads` có phát hiện ReentrantLock deadlock?** — Không đủ phạm vi; `findDeadlockedThreads` mở rộng sang ownable synchronizers.

**14. ThreadMXBean Java SE26 có giám sát virtual threads không?** — Không; chỉ platform threads.

**15. CountDownLatch có phải exclusive ownable lock?** — Không; dù implementation sử dụng AQS trong cơ chế chờ.

**16. synchronized trên object ReentrantLock có đồng nghĩa lock.lock không?** — Không, là hai khóa khác nhau.

**17. Ownership snapshot có thể dùng thay lock để đồng bộ không?** — Không, chỉ dành diagnostics.

**18. Java code ví dụ có cần mở remote JMX không?** — Không. `ManagementFactory.getThreadMXBean()` dùng platform MXBean cục bộ.

**19. Vì sao kiểm tra support flags trước introspection?** — Các tính năng monitor/synchronizer usage có thể không được JVM hỗ trợ.

**20. Demo đã kiểm chứng bao nhiêu assertions?** — 23/23 trên JDK hỗ trợ, biên dịch với `--release 17`.

## 17. Nguồn chính thức, còn áp dụng

- [Oracle Java SE 26 — ThreadMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html): monitoring platform threads, support flags, getThreadInfo, dumpAllThreads, findMonitorDeadlockedThreads và findDeadlockedThreads, virtual thread limitations.
- [Oracle Java SE 26 — ThreadInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadInfo.html): state, waiting LockInfo, owner ID/name, lockedMonitors, lockedSynchronizers, contention counts/times.
- [Oracle Java SE 26 — MonitorInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MonitorInfo.html): intrinsic object monitor, acquisition frame/depth, subclass của LockInfo.
- [Oracle Java SE 26 — LockInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/LockInfo.html): class name và identity hash của lock object.
- [Oracle Java SE 26 — AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html): single-thread exclusive ownership model, base cho AQS/AbstractQueuedLongSynchronizer.
- [Oracle Java SE 26 — AbstractQueuedSynchronizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html): cơ chế xếp hàng/đồng bộ, support exclusive/shared modes.
- [Oracle Java SE 26 — ReentrantLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): mutual exclusion, ownership, lock/unlock/tryLock/lockInterruptibly và metrics.
- [Oracle Java SE 26 — Thread.State](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.State.html): ý nghĩa BLOCKED, WAITING, TIMED_WAITING.
- [Oracle Java SE 26 — LockSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): park/unpark và blocker instrumentation.
- [Oracle Java SE 26 — The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): Thread.print -l, Thread.dump_to_file và diagnostics.
- [Oracle Java SE 26 — Virtual Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): virtual threads monitoring và scheduler.
- [Oracle Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): kiểm chứng API tương thích Java 17.
- [Oracle Java SE 17 — MonitorInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MonitorInfo.html): metadata monitor ở Java17.

**Kết luận:** Intrinsic **monitor** và **ownable synchronizer** đều có thể đồng bộ độc quyền, nhưng chúng không phải cùng một đối tượng/primitive. **`BLOCKED` thường chỉ chờ monitor**, còn tranh chấp `ReentrantLock` thường **park ở WAITING**. Đọc **`getLockedMonitors()`** cho monitors đã giữ và **`getLockedSynchronizers()`** cho ownable synchronizers đã giữ, kết hợp `getLockInfo()/getLockOwnerId()` để truy theo đối tượng đang đợi. Luôn kiểm tra JVM support flags, snapshot flags, thread lifecycle và giới hạn platform-vs-virtual threads của ThreadMXBean hiện hành.
