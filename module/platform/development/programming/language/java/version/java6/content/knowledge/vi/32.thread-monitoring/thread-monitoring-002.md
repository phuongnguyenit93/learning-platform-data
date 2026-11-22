# Theo dõi luồng: LockInfo, MonitorInfo và thông tin khóa

## 1. Mục tiêu và bối cảnh

Khi một ứng dụng Java chậm hoặc có những platform threads bị kẹt, câu hỏi quan trọng không chỉ là “thread đang ở trạng thái gì?” mà còn là **“thread đang chờ khóa nào, khóa đó do ai giữ, thread đang sở hữu những khóa nào, và đã chiếm object monitor ở vị trí stack nào?”**. Trong Java SE hiện hành, package `java.lang.management` cung cấp ba loại dữ liệu có liên hệ chặt chẽ:

- **`LockInfo`:** danh tính kỹ thuật của **một đối tượng khóa** trong snapshot JMX, gồm class name và `System.identityHashCode`. Dùng với các khóa mà thread đang chờ, hoặc các **ownable synchronizers** thread đang giữ.
- **`MonitorInfo extends LockInfo`:** thông tin của **object monitor** đang được thread giữ khi vào `synchronized`, cộng vị trí stack của câu lệnh/method đã chiếm monitor (`lockedStackDepth`, `lockedStackFrame`).
- **`ThreadInfo` + `ThreadMXBean`:** bối cảnh của thread và danh sách các khóa: thread state, `getLockInfo`, `getLockOwnerId`, `getLockedMonitors`, `getLockedSynchronizers`, stack trace và công cụ tìm deadlock.

Bài này thuộc chủ đề cha **Theo dõi luồng**, không phải tài liệu dạy thay thế toàn bộ Java concurrency. Trọng tâm là **đọc dữ liệu chẩn đoán thật**, phân biệt lock wait và lock ownership, chọn đúng API và xử lý các giới hạn của thread dump.

Sau bài học bạn sẽ:

1. Phân biệt `LockInfo` và `MonitorInfo`, **đối tượng đang chờ** và **đối tượng đã giữ**.
2. Hiểu vì sao `BLOCKED` với `synchronized` khác `WAITING` với `ReentrantLock` trong một tình huống cụ thể.
3. Đọc `ThreadInfo.getLockInfo()` và `getLockOwnerId()/getLockOwnerName()` một cách có kiểm tra null/-1.
4. Tìm các `MonitorInfo` qua `getLockedMonitors()`, đối chiếu `getLockedStackDepth` với mảng `getStackTrace()` khi frame được cung cấp.
5. Đọc `getLockedSynchronizers()` cho `ReentrantLock`/`AbstractOwnableSynchronizer`; hiểu implementation object bên trong có thể khác `ReentrantLock` wrapper.
6. Lấy snapshot bằng `ManagementFactory.getThreadMXBean()`, `getThreadInfo(long[],boolean,boolean,int)` và `dumpAllThreads(boolean,boolean,int)`.
7. Kiểm tra `isObjectMonitorUsageSupported()` và `isSynchronizerUsageSupported()` trước khi yêu cầu thống kê khóa.
8. Phân biệt “không giữ khóa” với “không yêu cầu lấy thông tin khóa”; biết các overloads đơn giản trả arrays rỗng.
9. Đọc đúng `LockInfo.from(CompositeData)`, `MonitorInfo.from(CompositeData)` và `ThreadInfo.from(CompositeData)` khi gọi platform MXBean qua raw `MBeanServer`.
10. Dùng `findDeadlockedThreads()` khác `findMonitorDeadlockedThreads()` đúng ngữ nghĩa, không tạo deadlock thật trong ứng dụng chỉ để thử.
11. Biết **ThreadMXBean không giám sát virtual threads** trên JDK 26; khi cần thread dumps gồm virtual threads, sử dụng công cụ `jcmd Thread.dump_to_file`/JFR đúng trường hợp.
12. Biết chi phí/giới hạn snapshot, bảo mật thread dumps và các tình huống dễ kết luận sai.
13. Chạy một ví dụ **Java 17+ độc lập đã được biên dịch `javac --release 17`, thực thi trên OpenJDK 24**, với **61/61 assertions PASS** trên threads/locks thật.

**Special Note:** Chỉ lấy kiến thức vẫn áp dụng hiện nay. Các API `LockInfo`, `MonitorInfo`, `ThreadInfo`, `ThreadMXBean` và `ManagementFactory` thuộc **module `java.management`**, được Oracle Java SE 26 tài liệu hóa. Ví dụ dùng `CountDownLatch`, `ReentrantLock`, JMX Open Data và JDK công khai; không dựa vào `Thread.stop()`, `Thread.suspend()`, `Thread.resume()` hay internal `sun.*`. Không trình bày cách lấy lock snapshot như một phương pháp điều khiển đồng bộ, không giả định `ThreadMXBean` nhìn thấy virtual threads.

## 2. Bức tranh chung: thread giữ khóa và thread chờ khóa

```text
                   MONITOR / synchronized
┌────────────────────────────────────────────────────────────────┐
│ Thread "demo-monitor-owner"                                     │
│   synchronized (MONITOR) { ... }                                │
│   ThreadInfo.getLockedMonitors()                                │
│       └── MonitorInfo(Object monitor, acquisition stack frame)  │
│                                                                │
│ Thread "demo-monitor-contender"                                 │
│   synchronized (MONITOR) { ... }   [BLOCKED]                     │
│   ThreadInfo.getLockInfo() -> LockInfo(Object monitor)          │
│   ThreadInfo.getLockOwnerId() -> owner thread ID                 │
└────────────────────────────────────────────────────────────────┘

                REENTRANTLOCK / ownable synchronizer
┌────────────────────────────────────────────────────────────────┐
│ Thread "demo-reentrant-owner"                                   │
│   lock.lock(); ...                                               │
│   ThreadInfo.getLockedSynchronizers() -> LockInfo(AQS Sync)     │
│                                                                │
│ Thread "demo-reentrant-contender" [WAITING in tested JDK]        │
│   lock.lock() -> park/wait                                        │
│   ThreadInfo.getLockInfo() -> LockInfo(AQS Sync)                 │
│   ThreadInfo.getLockOwnerId() -> owner thread ID                 │
└────────────────────────────────────────────────────────────────┘
```

Các box trên mô tả **hai kịch bản thực đã được kiểm thử**, không khẳng định mọi WAITING thread đều chờ ReentrantLock hoặc mọi BLOCKED đều là deadlock. Ngoài các locks này còn có `Object.wait()`, `LockSupport.park()`, `Condition.await()`, I/O waits, thread parking, class initialization và các cơ chế đồng bộ khác. Việc có lock wait trong một snapshot **không tự là deadlock**.

### 2.1. “Đang chờ” khác “đang giữ”

Một `ThreadInfo` có những mục dữ liệu dễ nhầm:

| API | Ý nghĩa | Thread owner hay waiter? |
| --- | --- | --- |
| `getLockInfo()` | Lock object mà thread đang blocked/waiting liên quan tới | **Waiter**, nếu có |
| `getLockOwnerId()` | ID của thread giữ lock mà thread này đang chờ; `-1` nếu không biết/không có | **Waiter → owner** |
| `getLockOwnerName()` | Tên owner khi biết; có thể `null` | **Waiter → owner** |
| `getLockName()` | Chuỗi miêu tả đối tượng lock đang đợi; có thể `null` | **Waiter** |
| `getLockedMonitors()` | Các object monitors thread **đang giữ** | **Owner** |
| `getLockedSynchronizers()` | Các ownable synchronizers thread **đang giữ** | **Owner** |
| `getThreadState()` | `BLOCKED`, `WAITING`, `TIMED_WAITING`, ... | Trạng thái quan sát |
| `getStackTrace()` | Call stack tại snapshot, có thể rỗng/bị rút gọn | Bối cảnh |

**Không thể thay `getLockInfo()` bằng `getLockedMonitors()[0]`**. Một bên miêu tả “đang chờ”, một bên miêu tả “đang sở hữu”; hai thread khác nhau có thể có LockInfo và MonitorInfo cùng class/identity trong cùng snapshot.

### 2.2. Các trạng thái thường gặp

| State | Ví dụ | Nhận xét khi nhìn LockInfo |
| --- | --- | --- |
| `BLOCKED` | Đợi chiếm object monitor để vào `synchronized` | `getLockInfo` thường là monitor đang bị giữ; có thể có owner |
| `WAITING` | `Object.wait`, `LockSupport.park`, `Condition.await` | Cần xem stack để biết đang đợi notification/condition/park gì |
| `TIMED_WAITING` | Timed wait, parkNanos, sleep | Không phải cứ TIMED_WAITING là đang đợi mutex |
| `RUNNABLE` | Đang chạy hoặc sẵn sàng | Có thể vẫn đang giữ monitors/synchronizers |
| `NEW` / `TERMINATED` | Chưa start / đã kết thúc | Không mong lấy được ThreadInfo live như một running thread |

Với `Object.wait()`, thread có thể tạm **nhả monitor mà nó đã wait trên đó** khi chờ notification rồi phải tái chiếm trước khi đi tiếp. Không suy diễn “WAITING” tức đang giữ tất cả locks; quan sát `getLockedMonitors` và semantics của phương thức đồng bộ cụ thể.

## 3. LockInfo: class name và identity hash code

### 3.1. Cấu trúc API

`java.lang.management.LockInfo` có:
- `getClassName()`: tên class đầy đủ của **đối tượng khóa được JMX biểu diễn**.
- `getIdentityHashCode()`: `System.identityHashCode(lockObject)` của đối tượng đó.
- `toString()`: thông thường `className + "@" + Integer.toHexString(identityHashCode)`.
- Constructor công khai `new LockInfo(String className, int identityHashCode)`.
- `static LockInfo.from(CompositeData)`: chuyển một giá trị MXBean Open Data thành LockInfo.

```java
LockInfo info = new LockInfo("demo.TestLock", 0x2a);
System.out.println(info.getClassName());
System.out.println(info.getIdentityHashCode());
System.out.println(info.toString());
```

**Snippet độc lập về đối tượng**; trong class có imports và main, stdout lần lượt:

```text
demo.TestLock
42
demo.TestLock@2a
```

Ở đây `42` đến từ `0x2a`. Dữ liệu tự tạo bằng constructor **không tự chứng minh** JVM thực đang sở hữu một lock; muốn dữ liệu thực dùng `ThreadMXBean` snapshot.

### 3.2. Identity hash không phải thread ID hay địa chỉ bộ nhớ

Giá trị `getIdentityHashCode()`:
- Là `int` giống `System.identityHashCode(lockObject)` của JVM.
- **Không phải** `ThreadInfo.getThreadId()`.
- **Không phải** memory address được bảo đảm, dù `toString` có dạng `class@hex`.
- **Không bảo đảm duy nhất tuyệt đối** giữa các object khác nhau (identity hash collisions có thể tồn tại).
- Không phụ thuộc một object override `hashCode()` như business key; identityHashCode bỏ qua override đó.

Để đối chiếu owner/waiter **trong cùng snapshot**, kết hợp **class name + identity hash code**, thread state, owner ID và stack trace. Đừng dùng khóa `className@hex` làm global identifier bền vững qua thời gian/JVM/process/restart.

### 3.3. LockInfo có thể là một object triển khai bên trong

Đối với `ReentrantLock`, `ThreadInfo.getLockedSynchronizers()` trên HotSpot/Sun JDK thường cho `LockInfo` của một implementation dựa trên `AbstractQueuedSynchronizer` (ví dụ một subclass `ReentrantLock$...Sync`). Nó **không nhất thiết** có className bằng `java.util.concurrent.locks.ReentrantLock` hoặc identityHashCode bằng `System.identityHashCode(reentrantLockWrapper)`.

Ví dụ runnable xác minh **cùng class/identity giữa LockInfo waiter và LockInfo owner**, thay vì giả định nó bằng object wrapper. Đó là cách đối chiếu phù hợp hơn.

## 4. MonitorInfo: vị trí monitor được chiếm giữ

`java.lang.management.MonitorInfo extends LockInfo`, mô tả **một object monitor đang bị thread giữ**. Hai thuộc tính bổ sung:

- `getLockedStackDepth()`: chỉ số trong `ThreadInfo.getStackTrace()` nơi monitor được chiếm giữ; **số âm** nếu không có thông tin.
- `getLockedStackFrame()`: `StackTraceElement` tương ứng; **null** khi không có frame.

Trong snapshot có đầy đủ stack, nếu `depth >= 0` và `depth < stack.length`:

```java
for (MonitorInfo m : threadInfo.getLockedMonitors()) {
    int depth = m.getLockedStackDepth();
    StackTraceElement frame = m.getLockedStackFrame();
    if (depth >= 0 && depth < threadInfo.getStackTrace().length) {
        System.out.println(frame.equals(threadInfo.getStackTrace()[depth]));
    }
}
```

Đây là snippet cần `ThreadInfo threadInfo` đã được lấy **cùng snapshot với monitor info**. Không lấy monitor của snapshot A rồi so với stack trace lấy ở snapshot B vì thread có thể đã đổi trạng thái và stack.

### 4.1. MonitorInfo có thể không có stack frame

Javadoc cho phép `getLockedStackDepth()` trả giá trị âm và `getLockedStackFrame()` trả null nếu không thể xác định. Constructor enforce consistency:

```java
MonitorInfo unknown = new MonitorInfo("demo.Monitor", 99, -1, null);
assert unknown.getLockedStackDepth() < 0;
assert unknown.getLockedStackFrame() == null;
```

Nếu truyền `stackDepth >= 0` nhưng `stackFrame == null`, constructor ném `IllegalArgumentException`. Ngược lại, depth âm mà frame non-null cũng không hợp lệ. Đừng vì một MonitorInfo không có frame mà suy ra monitor không tồn tại.

### 4.2. Stack index không phải source-code line number

`getLockedStackDepth()` là **mảng index**, bắt đầu từ 0, vào `ThreadInfo.getStackTrace()`. Nó không phải số dòng source file; số dòng được lấy riêng từ `StackTraceElement.getLineNumber()` và có thể không hiện diện nếu thiếu debug symbols. `getLockedStackFrame()` có tên class, method, file/line khi khả dụng.

### 4.3. Monitor không phải mọi kiểu lock

`MonitorInfo` áp dụng cho **object monitors** của `synchronized`, không phải bất kỳ `java.util.concurrent.locks.Lock` nào. `ReentrantLock`/`StampedLock`, `Semaphore`, `Condition` và các synchronizers có semantics khác; riêng `getLockedSynchronizers` ghi nhận **ownable synchronizers** được VM hỗ trợ, không phải tất cả synchronizer primitives. Không giả định `Semaphore` permits hoặc `Condition` waiters hiện thành MonitorInfo.

## 5. ThreadInfo kết nối các mảnh dữ liệu

`java.lang.management.ThreadInfo` là một **snapshot cho một platform thread**. Nó lưu thread name/ID/state, lock waiter, lock owner, owned object monitors, ownable synchronizers, stack trace và thông tin contention tùy khả năng JVM.

### 5.1. Lấy thread bị blocked

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
ThreadInfo[] infos = bean.getThreadInfo(
        new long[]{threadId}, true, true, Integer.MAX_VALUE);
ThreadInfo blocked = infos[0];

if (blocked != null) {
    LockInfo waitingFor = blocked.getLockInfo();
    long ownerId = blocked.getLockOwnerId();
    String ownerName = blocked.getLockOwnerName();
}
```

**Snippet** yêu cầu `long threadId` hợp lệ và JVM hỗ trợ both lock monitoring modes; luôn kiểm tra `isObjectMonitorUsageSupported()` và `isSynchronizerUsageSupported()` trước khi truyền true. Nếu thread đã dừng hoặc là virtual thread, có thể nhận **null**. Lấy lock info chỉ để chẩn đoán, không dùng kết quả để quyết định thứ tự acquire/unlock trong logic chương trình.

### 5.2. Phân biệt những overloads dễ nhầm

| Lời gọi | Stack trace | LockedMonitors | LockedSynchronizers |
| --- | --- | --- | --- |
| `getThreadInfo(id)` | **rỗng** | rỗng | rỗng |
| `getThreadInfo(id, maxDepth)` | Có tới `maxDepth` frames | rỗng | rỗng |
| `getThreadInfo(ids, false, false, maxDepth)` | Có tới `maxDepth` frames | rỗng | rỗng |
| `getThreadInfo(ids, true, true, maxDepth)` | Có tới `maxDepth` frames | Lấy nếu JVM hỗ trợ | Lấy nếu JVM hỗ trợ |
| `dumpAllThreads(true, true, maxDepth)` | Các platform threads live | Lấy nếu JVM hỗ trợ | Lấy nếu JVM hỗ trợ |

**Arrays rỗng không chứng minh thread không giữ monitor**, nếu code gọi overload không yêu cầu dữ liệu khóa! Chính bài runnable chứng minh `getThreadInfo(id)` trả về thread nhưng `getLockedMonitors()`/`getLockedSynchronizers()` là mảng rỗng, dù snapshot đầy đủ vẫn phát hiện locks.

### 5.3. Cờ hỗ trợ và UnsupportedOperationException

`ThreadMXBean` cung cấp:
- `isObjectMonitorUsageSupported()`: có thể lấy monitors đang giữ?
- `isSynchronizerUsageSupported()`: có thể lấy ownable synchronizers đang giữ?
- `getThreadInfo(ids, lockedMonitors, lockedSynchronizers, maxDepth)`.
- `dumpAllThreads(lockedMonitors, lockedSynchronizers, maxDepth)`.

Nếu yêu cầu true cho loại không được hỗ trợ, các APIs tương ứng có thể ném `UnsupportedOperationException`; đừng giả định mọi JVM/provider đều như OpenJDK 24.

Một đoạn code áp dụng với provider có capability không đồng đều:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
boolean monitors = bean.isObjectMonitorUsageSupported();
boolean syncs = bean.isSynchronizerUsageSupported();
ThreadInfo[] snapshot =
        bean.dumpAllThreads(monitors, syncs, 64);
```

Đây là snippet an toàn về flags. `64` chỉ giới hạn số stack frames, **không** giới hạn số threads, số monitors hay lượng dữ liệu cuối cùng của toàn snapshot. Với hệ thống lớn, cần kiểm soát tần suất dump và cardinality.

### 5.4. Thread IDs, nulls và races

`getAllThreadIds()` liệt kê IDs của các **live platform threads** tại thời điểm gọi. Đến khi gọi `getThreadInfo(ids,...)`, một thread có thể kết thúc. Khi đó entry ở đúng vị trí trong output array có thể là **null**, không được dereference ngay.

**Không dùng `Thread.getId()` trong ví dụ Java mới**: method này được deprecated trên các JDK mới hơn; thay vào đó lấy IDs từ `ThreadInfo.getThreadId()` khi đang phân tích snapshot, hoặc dùng `Thread.threadId()` nếu target Java runtime bảo đảm có API đó. Bài runnable vẫn compile Java 17 bằng cách chọn thread bằng tên từ dump và dùng `ThreadInfo.getThreadId()`.

### 5.5. LockOwnerId và LockOwnerName có thể thiếu

`getLockOwnerId()` có thể là **-1** nếu thread không blocked/waiting trên một đối tượng có owner xác định được. `getLockOwnerName()` có thể là null. `getLockInfo()` cũng có thể null khi thread không trong các trạng thái chờ được API mô tả. Không thay missing owner bằng số 0 hay tạo phantom thread.

### 5.6. Snapshot không phải transactional/global atomic state

`ThreadMXBean` được thiết kế để troubleshooting. Trạng thái threads thay đổi liên tục; thứ tự array không phải chronology, một thread có thể chết sau khi dump. Các metrics như blocked/waited time cần `isThreadContentionMonitoringSupported()` và policy bật đo, có overhead và được mặc định tắt ở nhiều JVMs. Không khẳng định một dump duy nhất là bằng chứng toàn hệ thống bị deadlock.

## 6. Đọc object monitor qua synchronized

Trong ví dụ:

```java
private static final Object MONITOR = new Object();

Thread owner = new Thread(() -> {
    synchronized (MONITOR) {
        // giữ monitor trong lúc có contender đang thử vào
    }
}, "demo-monitor-owner");

Thread contender = new Thread(() -> {
    synchronized (MONITOR) {
        // chỉ vào đây khi owner đã nhả
    }
}, "demo-monitor-contender");
```

Đây là **skeleton minh họa**, chưa có latches/bắt đầu/cleanup; file runnable ở mục 11 sử dụng `CountDownLatch` để giữ trạng thái ổn định trong test.

Trong snapshot:
- Owner có `MonitorInfo` trong `getLockedMonitors()` với `getClassName() == "java.lang.Object"` và `getIdentityHashCode() == System.identityHashCode(MONITOR)`.
- Contender có `getThreadState() == BLOCKED` và `getLockInfo()` miêu tả **cùng monitor**.
- Contender `getLockOwnerId()` là ID owner trong cùng snapshot.
- Owner `MonitorInfo.getLockedStackFrame()` cho vị trí chiếm monitor; `getLockedStackDepth()` là index.
- Sau khi owner rời `synchronized`, contender đi tiếp; chờ monitor **không tự là deadlock**.

Ví dụ kiểm thử **không** dựa trên `Thread.sleep(1000)` để “hy vọng” contention xảy ra. Nó dùng `CountDownLatch` giữ lock và `waitState` chờ thread chuyển sang `BLOCKED` trước khi snapshot.

## 7. Đọc ownable synchronizer qua ReentrantLock

`ReentrantLock` thuộc `java.util.concurrent.locks`, thường dựa trên một `AbstractQueuedSynchronizer` bên trong. Với ownable synchronizers:
- Thread owner có `LockInfo[] getLockedSynchronizers()`.
- Thread đang đợi `lock.lock()` có thể được ghi nhận với `ThreadInfo.getLockInfo()`; trong fixture OpenJDK 24 nó ở `WAITING`.
- `getLockOwnerId()` cho owner khi JVM xác định được.
- `LockInfo.getClassName()` có thể là class internal của synchronizer (`ReentrantLock$...Sync`), **không phải class của object `ReentrantLock` được app giữ**.

### 7.1. So sánh có cấu trúc, tránh hash sai đối tượng

```java
LockInfo waiting = waiterInfo.getLockInfo();

boolean foundOwner = Arrays.stream(ownerInfo.getLockedSynchronizers())
        .anyMatch(held ->
                held.getClassName().equals(waiting.getClassName())
                && held.getIdentityHashCode() == waiting.getIdentityHashCode());
```

Đây là snippet dùng `ThreadInfo waiterInfo` và `ownerInfo` được chụp trong cùng lượt, và đã kiểm tra `waiting != null`. **Không** lấy `System.identityHashCode(reentrantLock)` rồi kỳ vọng nó phải bằng hash của internal `AbstractQueuedSynchronizer`.

### 7.2. Không quy mọi WAITING cho một lock

`LockSupport.park()` có blocker object tùy primitive. `Condition.await()` có thể khiến thread **nhả ReentrantLock** trong lúc chờ condition; stack trace và lock list sẽ khác trường hợp đang cạnh tranh `lock.lock()`. Trong các tình huống lạ, `getLockOwnerId() == -1` dù `getLockInfo() != null`. Hãy đọc cả stack, state, owner và held locks thay vì suy đoán từ một property.

### 7.3. ReentrantLock là lock có release rõ ràng

Nếu đang viết business code với ReentrantLock, luôn `unlock()` trong `finally` sau `lock()` thành công:

```java
lock.lock();
try {
    // thao tác trên trạng thái dùng chung
} finally {
    lock.unlock();
}
```

Đây là snippet, `lock` là `ReentrantLock`. Phần đo lock bằng ThreadMXBean chỉ **quan sát**, không thay `lock/unlock`. Không gọi `unlock()` của một lock do thread khác sở hữu dựa trên “thấy owner trong dump”.

## 8. Đọc kết quả JMX MXBean dưới dạng CompositeData

`ThreadMXBean` là một MXBean platform có `ObjectName = "java.lang:type=Threading"`. Khi dùng typed `ManagementFactory.getThreadMXBean()`, bạn nhận trực tiếp `ThreadInfo`. Khi gọi **raw JMX `MBeanServer.invoke`**, các kiểu phức tạp có thể được chuyển thành JMX **Open Data**:

- `ThreadInfo` → `CompositeData`.
- `ThreadInfo[]` → `CompositeData[]`.
- `LockInfo` → `CompositeData` với fields `className` và `identityHashCode`.
- `MonitorInfo` → `CompositeData` với fields khóa cơ bản và `lockedStackDepth`/`lockedStackFrame`.
- `StackTraceElement` → `CompositeData` có method/class/file/line và metadata khác tùy version.

### 8.1. Raw JMX call vào Threading MXBean

```java
MBeanServer platform = ManagementFactory.getPlatformMBeanServer();
ObjectName threadBean =
        new ObjectName(ManagementFactory.THREAD_MXBEAN_NAME);

Object value = platform.invoke(
        threadBean,
        "getThreadInfo",
        new Object[]{ids, Boolean.TRUE, Boolean.TRUE},
        new String[]{"[J", "boolean", "boolean"}
);
CompositeData[] result = (CompositeData[]) value;
```

Đây là snippet có `long[] ids` (platform thread IDs live). Chữ ký `[J` là **JVM name cho long[]**; raw invocation parameter là array các IDs, boolean flags. **Không** lấy Java name `"java.lang.Long[]"` tùy ý thay cho JMX operation signature.

### 8.2. Tái dựng LockInfo và MonitorInfo

```java
CompositeData waiter = result[1];
LockInfo waiting = LockInfo.from(
        (CompositeData) waiter.get("lockInfo"));

CompositeData owner = result[0];
CompositeData[] monitorRows =
        (CompositeData[]) owner.get("lockedMonitors");

for (CompositeData row : monitorRows) {
    MonitorInfo m = MonitorInfo.from(row);
    System.out.println(m.getClassName());
}
ThreadInfo typedWaiter = ThreadInfo.from(waiter);
```

Đây là snippet, giả định `result[0]` là owner và `result[1]` là waiter như mã fixture; **không áp dụng thứ tự này cho mọi raw result** nếu mảng input IDs khác. Phải kiểm tra element null khi thread có thể kết thúc. `LockInfo.from(null)`, `MonitorInfo.from(null)` và `ThreadInfo.from(null)` trả null. Nếu `CompositeData` không phù hợp mapped type, `from` có thể ném `IllegalArgumentException`.

### 8.3. Không tự parse ThreadInfo.toString như một API

`ThreadInfo.toString()` tạo text thuận tiện cho con người, nhưng định dạng **phụ thuộc implementation**. Tool có nhu cầu xử lý logic nên đọc `ThreadInfo`, `CompositeData`, `CompositeType` và fields công khai thay vì dùng regex trên toString hay hardcode số cột trong một thread dump.

### 8.4. Schema version có thể có fields mới

`ThreadInfo.from(CompositeData)` mô tả mapped attributes cho các Java runtime versions. Client Open Data cần tôn trọng actual schema/optional fields; không giả định bản `CompositeData` của mọi JDK chỉ có đúng các fields JDK 6. Các fields `daemon`, `priority` và stack trace metadata được bổ sung theo thời gian. Dùng `ThreadInfo.from(...)` hoặc introspection `CompositeType` thay vì tự duy trì mapping thiếu field.

## 9. Phát hiện deadlock, contention và điểm mù

### 9.1. Hai API deadlock có phạm vi khác nhau

| API | Phạm vi | Trả về |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Chu trình các **platform threads** đợi chiếm object monitors | `long[]` IDs hoặc `null` |
| `findDeadlockedThreads()` | Chu trình các **platform threads** đợi object monitors **hoặc ownable synchronizers** | `long[]` IDs hoặc `null` |

`findDeadlockedThreads()` rộng hơn, nhưng phụ thuộc khả năng theo dõi ownable synchronizers của JVM; cần kiểm tra capability và xử lý `UnsupportedOperationException` theo Javadoc. Deadlock do resource khác, vòng chờ application protocol, database locks, network or conditions có thể **không** được báo bởi hai methods này.

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
long[] deadlocked = bean.isSynchronizerUsageSupported()
        ? bean.findDeadlockedThreads()
        : bean.findMonitorDeadlockedThreads();
if (deadlocked != null) {
    ThreadInfo[] report = bean.getThreadInfo(
            deadlocked,
            bean.isObjectMonitorUsageSupported(),
            bean.isSynchronizerUsageSupported(),
            64);
    // Sanitized alert + investigation; không tự động terminate thread.
}
```

**Snippet** để chẩn đoán, không tự resolve deadlock. Nếu dùng `findDeadlockedThreads` từ runtime/provider không hỗ trợ, cần fallback hợp lệ và không che lỗi. Bài runnable ở mục 11 **không cố tình tạo deadlock**, chỉ xác minh hai methods trả null với bốn threads đang tranh chấp nhưng sẽ được giải phóng.

### 9.2. Contention không đồng nghĩa deadlock

Nếu thread A đang giữ monitor và B blocked đợi monitor đó, nhưng A đang chờ một latch sẽ được release bởi controller, không có vòng chờ A↔B, vì vậy **không phải deadlock**. Thread dump có thể cho `BLOCKED` hàng nghìn lần trong ứng dụng có contention cao. Phải xem **wait-for graph** và thời gian kéo dài, không chỉ thấy trạng thái.

### 9.3. Không dùng ThreadMXBean như đồng bộ chính

Javadoc nói rõ thread information dành cho **monitoring**, không dùng để điều khiển đồng bộ. Vì snapshot có thể cũ ngay sau khi lấy:
- Không gọi `unlock`, `notify` hoặc `interrupt` dựa duy nhất vào lock owner ID trong snapshot.
- Không giả định một thread vẫn giữ lock sau khi bạn nhận được array.
- Không dùng phát hiện deadlock để tự động `Thread.stop`/suspend (các methods nguy hiểm/lỗi thời).
- Không đưa thread dump chứa secrets vào endpoint public.

### 9.4. Contention statistics là một tính năng khác

`ThreadInfo.getBlockedCount()`/`getBlockedTime()` và `getWaitedCount()`/`getWaitedTime()` liên quan tới thống kê contention/wait. Thời gian blocked/waited cần hỗ trợ của JVM và thread contention monitoring đã bật; có thể trả `-1` khi bị disable/không hỗ trợ. Đừng nhầm **lock ownership snapshot** với **thống kê thời gian tắc nghẽn** hoặc CPU profiling.

## 10. Java virtual threads và phương án quan sát hiện hành

**JDK 26 `ThreadMXBean` không theo dõi/quản lý virtual threads.** Các methods như `getAllThreadIds()`, `getThreadInfo(id)`, `dumpAllThreads(...)` và `findDeadlockedThreads()` có phạm vi platform threads theo contract. Nếu một app có hàng nghìn virtual threads, việc `ThreadMXBean` không hiển thị chúng **không có nghĩa chúng đã kết thúc hoặc ứng dụng không có lock contention**.

### 10.1. Dùng jcmd để có dump bao gồm virtual threads

Theo tài liệu JDK 26, `jcmd Thread.dump_to_file` có thể tạo thread dump gồm platform và virtual threads. Ví dụ trong môi trường quản trị có quyền attach vào **process do bạn vận hành**:

```bash
jcmd <PID> Thread.dump_to_file -format=plain threads.txt
jcmd <PID> Thread.dump_to_file -format=json threads.json
```

`<PID>` ở đây là **placeholder được thay bằng PID thực** khi chạy, không copy nguyên ký hiệu góc vào shell. `plain`/`json` là các giá trị được `jcmd` JDK 26 command reference mô tả. Nếu muốn overwrite output file đang có, command có option `-overwrite` — không dùng trừ khi đã kiểm soát file đích.

Lưu ý **`Thread.dump_to_file` không perform deadlock detection**. Dump chứa trạng thái/lock info nhưng không phải một snapshot toàn hệ thống đồng nhất; có timestamp riêng từng thread. Đọc kèm metrics/JFR để xác nhận giả thuyết.

### 10.2. Đừng nhầm hai dạng jcmd thread dump

- `jcmd <PID> Thread.print -l`: HotSpot thread dump cho platform threads và mounted virtual threads, có thêm thông tin native/VM theo version.
- `jcmd <PID> Thread.dump_to_file -format=json threads.json`: thread dump file cho **tất cả virtual threads** và platform threads; phù hợp tooling phân tích dạng JSON.
- `ThreadMXBean.dumpAllThreads(...)`: API quản trị **platform threads**, hỗ trợ lấy structured `LockInfo/MonitorInfo`.

Các công cụ không có cùng đầu ra, không nên gọi một cái rồi kỳ vọng các fields/độ bao phủ giống hệt cái khác.

### 10.3. JFR cho bài toán cạnh tranh và blocking kéo dài

Java Flight Recorder (JFR) có thể giúp chẩn đoán sự kiện lock contention, thread parking, virtual thread behavior và performance impact theo runtime/JFR configuration. Không mặc định bật mọi event threshold/capture stack trace; chọn recording policy phù hợp về overhead, dữ liệu nhạy cảm và retention. Khi virtual threads chiếm phần lớn workload, phối hợp JFR và `jcmd Thread.dump_to_file` thay vì chỉ nhìn ThreadMXBean.

## 11. Ví dụ Java 17+ đầy đủ: hai loại khóa và 61 checks thực

### 11.1. Thiết kế fixture

Chương trình `ThreadLockInfoDemo.java` được chạy thật trên Windows **OpenJDK 24**, biên dịch bằng `javac --release 17`:

- Dùng `new Object()` với `synchronized` để tạo **object monitor**.
- Dùng `new ReentrantLock()` để tạo **ownable synchronizer**.
- Bốn platform threads được đặt tên cố định; hai threads giữ khóa và đợi latch, hai threads cạnh tranh khóa tương ứng.
- Dùng `CountDownLatch` và `waitState(...)` thay vì ngủ một khoảng ngẫu nhiên rồi chụp snapshot. Trên runtime thử, monitor contender đạt `BLOCKED`; ReentrantLock contender đạt `WAITING`.
- `ThreadMXBean.dumpAllThreads(true,true,Integer.MAX_VALUE)` thu data của bốn threads; sau đó `getThreadInfo(ids,true,true,Integer.MAX_VALUE)` kiểm tra order/held locks.
- Các overloads không lấy lock info được kiểm chứng trả arrays rỗng; stack depth được giới hạn.
- Raw JMX platform MXBean `java.lang:type=Threading` trả `CompositeData[]`; test chuyển về LockInfo/MonitorInfo/ThreadInfo.
- Tạo `LockInfo`/`MonitorInfo` nhân tạo để kiểm tra constructor và validation, không trộn chúng với dữ liệu JVM quan sát thật.
- **Không tạo deadlock không thể thu hồi**. Trong `finally`, hai latches được release rồi `join` tất cả threads, không `Thread.stop` hoặc ép unlock từ thread khác.

**Khả năng thực thi:** Fixture yêu cầu JVM hỗ trợ monitor và ownable synchronizer monitoring. Nếu một provider không hỗ trợ, hai assertions đầu sẽ fail có thông báo. Trên OpenJDK 24 đã kiểm thử, chúng đều PASS. Không giả định portable exact `WAITING` state trên mọi JVM/provider, nhưng trong fixture thực tế tên/threads và các states đều được đối chiếu.

### 11.2. Toàn bộ file `ThreadLockInfoDemo.java`

```java
import java.lang.management.LockInfo;
import java.lang.management.ManagementFactory;
import java.lang.management.MonitorInfo;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantLock;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

public final class ThreadLockInfoDemo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock REENTRANT = new ReentrantLock();

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=true");
    }
    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS))
                throw new AssertionError("latch timeout");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new AssertionError(ex);
        }
    }
    private static void waitState(Thread thread, Thread.State target)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (thread.getState() != target) {
            if (System.nanoTime() >= deadline)
                throw new AssertionError("unexpected state: " + thread.getState());
            Thread.sleep(5);
        }
    }
    private static ThreadInfo byName(ThreadInfo[] infos, String name) {
        return Arrays.stream(infos)
                .filter(x -> x != null && x.getThreadName().equals(name))
                .findFirst().orElseThrow(() -> new AssertionError(name));
    }
    private static void join(Thread thread) throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive())
            throw new AssertionError("thread still alive: " + thread.getName());
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        check("monitorSupport", mx.isObjectMonitorUsageSupported());
        check("synchronizerSupport", mx.isSynchronizerUsageSupported());
        CountDownLatch monitorHeld = new CountDownLatch(1);
        CountDownLatch monitorRelease = new CountDownLatch(1);
        CountDownLatch monitorAttempt = new CountDownLatch(1);
        CountDownLatch reentrantHeld = new CountDownLatch(1);
        CountDownLatch reentrantRelease = new CountDownLatch(1);
        CountDownLatch reentrantAttempt = new CountDownLatch(1);
        AtomicBoolean monitorEntered = new AtomicBoolean();
        AtomicBoolean reentrantEntered = new AtomicBoolean();

        Thread monitorOwner = new Thread(() -> {
            synchronized (MONITOR) {
                monitorHeld.countDown();
                await(monitorRelease);
            }
        }, "demo-monitor-owner");
        Thread monitorContender = new Thread(() -> {
            monitorAttempt.countDown();
            synchronized (MONITOR) {
                monitorEntered.set(true);
            }
        }, "demo-monitor-contender");
        Thread reentrantOwner = new Thread(() -> {
            REENTRANT.lock();
            try {
                reentrantHeld.countDown();
                await(reentrantRelease);
            } finally {
                REENTRANT.unlock();
            }
        }, "demo-reentrant-owner");
        Thread reentrantContender = new Thread(() -> {
            reentrantAttempt.countDown();
            REENTRANT.lock();
            try {
                reentrantEntered.set(true);
            } finally {
                REENTRANT.unlock();
            }
        }, "demo-reentrant-contender");

        try {
            monitorOwner.start();
            await(monitorHeld);
            monitorContender.start();
            await(monitorAttempt);
            waitState(monitorContender, Thread.State.BLOCKED);
            reentrantOwner.start();
            await(reentrantHeld);
            reentrantContender.start();
            await(reentrantAttempt);
            waitState(reentrantContender, Thread.State.WAITING);

            ThreadInfo[] snapshot =
                    mx.dumpAllThreads(true, true, Integer.MAX_VALUE);
            ThreadInfo mo = byName(snapshot, "demo-monitor-owner");
            ThreadInfo mc = byName(snapshot, "demo-monitor-contender");
            ThreadInfo ro = byName(snapshot, "demo-reentrant-owner");
            ThreadInfo rc = byName(snapshot, "demo-reentrant-contender");
            check("platformThreadsCaptured",
                    mo != null && mc != null && ro != null && rc != null);
            check("distinctThreadIds",
                    mo.getThreadId() != mc.getThreadId()
                    && ro.getThreadId() != rc.getThreadId());
            check("monitorContenderBlocked",
                    mc.getThreadState() == Thread.State.BLOCKED);
            check("monitorNotEnteredYet", !monitorEntered.get());
            check("monitorWaitLockPresent", mc.getLockInfo() != null);
            check("monitorWaitClassName",
                    mc.getLockInfo().getClassName().equals("java.lang.Object"));
            check("monitorWaitIdentity",
                    mc.getLockInfo().getIdentityHashCode()
                            == System.identityHashCode(MONITOR));
            check("monitorWaitOwnerId",
                    mc.getLockOwnerId() == mo.getThreadId());
            check("monitorWaitOwnerName",
                    "demo-monitor-owner".equals(mc.getLockOwnerName()));
            check("monitorWaitLockName",
                    mc.getLockName().equals(mc.getLockInfo().toString()));
            MonitorInfo monitor = Arrays.stream(mo.getLockedMonitors())
                    .filter(x -> x.getClassName().equals("java.lang.Object")
                            && x.getIdentityHashCode()
                                    == System.identityHashCode(MONITOR))
                    .findFirst().orElseThrow();
            check("monitorOwnerHoldsLock", monitor != null);
            check("monitorInfoIsLockInfo", monitor instanceof LockInfo);
            check("monitorStackDepthValid",
                    monitor.getLockedStackDepth() >= 0
                    && monitor.getLockedStackDepth()
                            < mo.getStackTrace().length);
            check("monitorFrameMatchesStack",
                    monitor.getLockedStackFrame().equals(
                            mo.getStackTrace()[monitor.getLockedStackDepth()]));
            check("monitorClassName",
                    monitor.getClassName().equals("java.lang.Object"));
            check("monitorIdentityHash",
                    monitor.getIdentityHashCode()
                            == System.identityHashCode(MONITOR));
            check("monitorOwnerStackVisible", mo.getStackTrace().length > 0);

            check("reentrantContenderWaiting",
                    rc.getThreadState() == Thread.State.WAITING);
            check("reentrantNotEnteredYet", !reentrantEntered.get());
            check("reentrantWaitLockPresent", rc.getLockInfo() != null);
            check("reentrantWaitOwnerId",
                    rc.getLockOwnerId() == ro.getThreadId());
            check("reentrantWaitOwnerName",
                    "demo-reentrant-owner".equals(rc.getLockOwnerName()));
            LockInfo owned = Arrays.stream(ro.getLockedSynchronizers())
                    .filter(x -> x.getClassName().equals(rc.getLockInfo().getClassName())
                            && x.getIdentityHashCode()
                                    == rc.getLockInfo().getIdentityHashCode())
                    .findFirst().orElseThrow();
            check("ownableLockVisible", owned != null);
            check("ownableLockMatchesWaiter",
                    owned.getIdentityHashCode()
                            == rc.getLockInfo().getIdentityHashCode());
            check("ownableLockType",
                    owned.getClassName().contains("ReentrantLock"));
            check("ownableClassNotAssumedToBePublicLock",
                    owned.getClassName().equals(rc.getLockInfo().getClassName()));
            check("ownerNotHoldingFixtureMonitor",
                    Arrays.stream(ro.getLockedMonitors()).noneMatch(x ->
                            x.getIdentityHashCode()
                                    == System.identityHashCode(MONITOR)));

            long[] ids = {mo.getThreadId(), mc.getThreadId(),
                    ro.getThreadId(), rc.getThreadId()};
            ThreadInfo[] selected =
                    mx.getThreadInfo(ids, true, true, Integer.MAX_VALUE);
            check("getThreadInfoPreservesIdOrder",
                    selected.length == 4
                    && selected[0].getThreadId() == ids[0]
                    && selected[1].getThreadId() == ids[1]
                    && selected[2].getThreadId() == ids[2]
                    && selected[3].getThreadId() == ids[3]);
            check("getThreadInfoIncludesMonitor",
                    selected[0].getLockedMonitors().length > 0);
            check("getThreadInfoIncludesSynchronizer",
                    selected[2].getLockedSynchronizers().length > 0);
            ThreadInfo[] shallow = mx.getThreadInfo(ids, false, false, 8);
            check("falseFlagOmitsMonitors",
                    Arrays.stream(shallow).allMatch(x ->
                            x != null && x.getLockedMonitors().length == 0));
            check("falseFlagOmitsSynchronizers",
                    Arrays.stream(shallow).allMatch(x ->
                            x != null && x.getLockedSynchronizers().length == 0));
            check("maxDepthBoundsStack",
                    Arrays.stream(shallow).allMatch(x ->
                            x.getStackTrace().length <= 8));
            ThreadInfo noStack = mx.getThreadInfo(mc.getThreadId());
            check("simpleGetThreadInfoOmitsStack",
                    noStack.getStackTrace().length == 0);
            check("simpleGetThreadInfoOmitsMonitors",
                    noStack.getLockedMonitors().length == 0);
            check("simpleGetThreadInfoOmitsSynchronizers",
                    noStack.getLockedSynchronizers().length == 0);
            check("noDeadlock", mx.findDeadlockedThreads() == null);
            check("noMonitorDeadlock",
                    mx.findMonitorDeadlockedThreads() == null);

            MBeanServer platform = ManagementFactory.getPlatformMBeanServer();
            ObjectName threading = new ObjectName(
                    ManagementFactory.THREAD_MXBEAN_NAME);
            Object raw = platform.invoke(threading, "getThreadInfo",
                    new Object[]{ids, Boolean.TRUE, Boolean.TRUE},
                    new String[]{"[J", "boolean", "boolean"});
            check("rawMxbeanReturnsCompositeArray",
                    raw instanceof CompositeData[]);
            CompositeData[] rawRows = (CompositeData[]) raw;
            check("rawArrayHasFourEntries", rawRows.length == 4);
            check("rawWaiterLockComposite",
                    rawRows[1].get("lockInfo") instanceof CompositeData);
            LockInfo fromWaiter = LockInfo.from(
                    (CompositeData) rawRows[1].get("lockInfo"));
            check("lockInfoFromCompositeData",
                    fromWaiter.getIdentityHashCode()
                            == System.identityHashCode(MONITOR));
            check("rawMonitorArrayIsComposite",
                    rawRows[0].get("lockedMonitors")
                            instanceof CompositeData[]);
            MonitorInfo fromMonitor = Arrays.stream(
                    (CompositeData[]) rawRows[0].get("lockedMonitors"))
                    .map(MonitorInfo::from)
                    .filter(x -> x.getIdentityHashCode()
                            == System.identityHashCode(MONITOR))
                    .findFirst().orElseThrow();
            check("monitorInfoFromCompositeData",
                    fromMonitor.getClassName().equals("java.lang.Object"));
            check("rawSynchronizerArrayIsComposite",
                    rawRows[2].get("lockedSynchronizers")
                            instanceof CompositeData[]);
            check("synchronizerLockInfoFromCompositeData",
                    Arrays.stream((CompositeData[])
                            rawRows[2].get("lockedSynchronizers"))
                        .map(LockInfo::from)
                        .anyMatch(x -> x.getClassName().equals(owned.getClassName())
                                && x.getIdentityHashCode()
                                        == owned.getIdentityHashCode()));
            check("threadInfoFromCompositeData",
                    ThreadInfo.from(rawRows[1]).getLockOwnerId()
                            == mo.getThreadId());
            check("lockInfoFromNull", LockInfo.from(null) == null);
            check("monitorInfoFromNull", MonitorInfo.from(null) == null);
            check("threadInfoFromNull", ThreadInfo.from(null) == null);

            LockInfo synthetic = new LockInfo("demo.TestLock", 0x2a);
            check("syntheticLockClass",
                    synthetic.getClassName().equals("demo.TestLock"));
            check("syntheticLockIdentity", synthetic.getIdentityHashCode() == 42);
            check("syntheticLockToString",
                    synthetic.toString().equals("demo.TestLock@2a"));
            MonitorInfo noFrame = new MonitorInfo("demo.Monitor", 99, -1, null);
            check("missingFrameIsNull", noFrame.getLockedStackFrame() == null);
            check("missingFrameDepthIsNegative",
                    noFrame.getLockedStackDepth() < 0);
            boolean badFrameRejected = false;
            try {
                new MonitorInfo("demo.Bad", 8, 1, null);
            } catch (IllegalArgumentException expected) {
                badFrameRejected = true;
            }
            check("invalidFrameRejected", badFrameRejected);

            System.out.println("monitorOwner=demo-monitor-owner");
            System.out.println("monitorContender=BLOCKED");
            System.out.println("ownableOwner=demo-reentrant-owner");
            System.out.println("ownableContender=WAITING");
        } finally {
            monitorRelease.countDown();
            reentrantRelease.countDown();
            for (Thread t : new Thread[]{monitorOwner, monitorContender,
                    reentrantOwner, reentrantContender}) {
                if (t.getState() != Thread.State.NEW) join(t);
            }
            check("allDemoThreadsFinished",
                    !monitorOwner.isAlive() && !monitorContender.isAlive()
                    && !reentrantOwner.isAlive() && !reentrantContender.isAlive());
            check("monitorEventuallyEntered", monitorEntered.get());
            check("reentrantEventuallyEntered", reentrantEntered.get());
        }
    }
}
```

### 11.3. Biên dịch và chạy

Lưu toàn bộ source ở trên thành file có tên đúng **`ThreadLockInfoDemo.java`**. Chỉ cần JDK 17+:

```bash
javac --release 17 ThreadLockInfoDemo.java
java ThreadLockInfoDemo
```

Không cần Maven, Spring, thư viện ngoài, mạng, JMX remote hay cổng mới. Chương trình dùng module `java.management` có sẵn. Khi dùng project có `module-info.java`, cần:

```java
module demo.threadlocks {
    requires java.management;
}
```

Đây là **snippet ở file riêng `module-info.java`**, không đặt cùng `ThreadLockInfoDemo.java` dạng classpath ví dụ. Runtime tùy chỉnh `jlink` phải bao gồm module java.management nếu ứng dụng cần ThreadMXBean.

### 11.4. Stdout chính xác trên OpenJDK 24

```text
monitorSupport=true
synchronizerSupport=true
platformThreadsCaptured=true
distinctThreadIds=true
monitorContenderBlocked=true
monitorNotEnteredYet=true
monitorWaitLockPresent=true
monitorWaitClassName=true
monitorWaitIdentity=true
monitorWaitOwnerId=true
monitorWaitOwnerName=true
monitorWaitLockName=true
monitorOwnerHoldsLock=true
monitorInfoIsLockInfo=true
monitorStackDepthValid=true
monitorFrameMatchesStack=true
monitorClassName=true
monitorIdentityHash=true
monitorOwnerStackVisible=true
reentrantContenderWaiting=true
reentrantNotEnteredYet=true
reentrantWaitLockPresent=true
reentrantWaitOwnerId=true
reentrantWaitOwnerName=true
ownableLockVisible=true
ownableLockMatchesWaiter=true
ownableLockType=true
ownableClassNotAssumedToBePublicLock=true
ownerNotHoldingFixtureMonitor=true
getThreadInfoPreservesIdOrder=true
getThreadInfoIncludesMonitor=true
getThreadInfoIncludesSynchronizer=true
falseFlagOmitsMonitors=true
falseFlagOmitsSynchronizers=true
maxDepthBoundsStack=true
simpleGetThreadInfoOmitsStack=true
simpleGetThreadInfoOmitsMonitors=true
simpleGetThreadInfoOmitsSynchronizers=true
noDeadlock=true
noMonitorDeadlock=true
rawMxbeanReturnsCompositeArray=true
rawArrayHasFourEntries=true
rawWaiterLockComposite=true
lockInfoFromCompositeData=true
rawMonitorArrayIsComposite=true
monitorInfoFromCompositeData=true
rawSynchronizerArrayIsComposite=true
synchronizerLockInfoFromCompositeData=true
threadInfoFromCompositeData=true
lockInfoFromNull=true
monitorInfoFromNull=true
threadInfoFromNull=true
syntheticLockClass=true
syntheticLockIdentity=true
syntheticLockToString=true
missingFrameIsNull=true
missingFrameDepthIsNegative=true
invalidFrameRejected=true
monitorOwner=demo-monitor-owner
monitorContender=BLOCKED
ownableOwner=demo-reentrant-owner
ownableContender=WAITING
allDemoThreadsFinished=true
monitorEventuallyEntered=true
reentrantEventuallyEntered=true
```

**61/61 guarded assertions PASS**, cùng 4 dòng trạng thái/nhãn mẫu cố định. `check(name, ok)` ném `AssertionError` nếu điều kiện sai; chỉ in `name=true` khi đúng. Lượt chạy được biên dịch với `javac --release 17` và thực thi bằng OpenJDK 24 trên Windows. Cả bốn threads kết thúc bình thường sau `countDown()/join()`; không có exception từ thread nền. Test file/class nằm trong thư mục tạm rồi được dọn, không chỉnh sửa repository.

### 11.5. Vì sao stdout không có ID/identityHashCode cụ thể?

- Thread IDs và identity hash codes phụ thuộc JVM/process và không cố định.
- Code kiểm tra các quan hệ đúng: cùng class/hash giữa waiter và monitor owner, owner ID đúng, stack frame tương ứng.
- Ví dụ chỉ in những giá trị ổn định như names, state quan sát và kết quả assert.
- Với environment khác, thread state của ReentrantLock waiter có thể khác chi tiết thời điểm; đây là một **fixture đã kiểm thử** không phải specification về scheduler cho mọi JVM.
- Không dựa vào thứ tự JMX `dumpAllThreads` để chọn threads: chọn bằng tên, sau đó tạo mảng IDs có thứ tự chủ động.

### 11.6. Ý nghĩa 61 checks theo nhóm

| Nhóm | Một số assertions | Bằng chứng |
| --- | --- | --- |
| Provider capabilities | `monitorSupport`, `synchronizerSupport` | JVM test hỗ trợ thống kê monitors/ownable synchronizers |
| Thread selection | `platformThreadsCaptured`, `distinctThreadIds` | Chọn đúng bốn platform threads |
| Monitor contender | `monitorContenderBlocked`, `monitorWaitClassName`, `monitorWaitIdentity` | Waiter đang đợi đúng Object monitor |
| Owner identity | `monitorWaitOwnerId`, `monitorWaitOwnerName`, `monitorWaitLockName` | Gắn waiter với owner |
| Owner monitor | `monitorOwnerHoldsLock`, `monitorInfoIsLockInfo` | MonitorInfo mô tả lock được owner giữ |
| Stack acquisition | `monitorStackDepthValid`, `monitorFrameMatchesStack` | lockedStackDepth là index vào stack cùng snapshot |
| Ownable | `reentrantContenderWaiting`, `ownableLockMatchesWaiter`, `ownableLockType` | ReentrantLock được biểu diễn bằng ownable synchronizer của implementation |
| Snapshot flags | `getThreadInfoIncludesMonitor`, `falseFlagOmitsMonitors` | Dùng flags quyết định có snapshot owned locks |
| Shallow info | `simpleGetThreadInfoOmitsStack`, `maxDepthBoundsStack` | Overloads và giới hạn stack |
| Deadlock | `noDeadlock`, `noMonitorDeadlock` | Contention có kiểm soát không tạo chu trình deadlock |
| Raw MXBean | `rawMxbeanReturnsCompositeArray`, `rawWaiterLockComposite` | Open Data MXBean mapping đúng |
| Conversion | `lockInfoFromCompositeData`, `monitorInfoFromCompositeData`, `threadInfoFromCompositeData` | `from(CompositeData)` reconstruct objects |
| Constructor | `syntheticLockToString`, `missingFrameDepthIsNegative`, `invalidFrameRejected` | LockInfo/MonitorInfo contracts |
| Cleanup | `allDemoThreadsFinished`, `monitorEventuallyEntered`, `reentrantEventuallyEntered` | Nhả locks và join thành công |

## 12. Quy trình chẩn đoán lock contention trong ứng dụng thực

### Bước 1 — Xác định phạm vi thread cần xem

Ứng dụng đang chạy platform threads hay virtual threads? ThreadMXBean chỉ theo dõi platform threads. Ghi JDK version/runtime, `ThreadMXBean.isObjectMonitorUsageSupported()` và `isSynchronizerUsageSupported()`.

### Bước 2 — Chụp thông tin đúng flags và giới hạn

Nếu chỉ quan tâm một số platform thread IDs, `getThreadInfo(ids, true, true, maxDepth)` giảm phạm vi so với dump toàn JVM. Nếu cần phát hiện owner của waiter chưa biết, dump các threads có liên quan và nối theo `getLockOwnerId()`. Với ứng dụng lớn, tránh dump sâu liên tục trên hot path; sampling có chủ đích trong diagnostics.

### Bước 3 — Tách wait chain

Với từng ThreadInfo:
1. Ghi `getThreadName/getThreadId/getThreadState`.
2. Kiểm tra `getLockInfo()`: lock nào đang đợi?
3. Kiểm tra `getLockOwnerId/getLockOwnerName`: ai đang giữ, có owner biết được không?
4. Tìm ThreadInfo của owner trong cùng snapshot theo ID.
5. Đối chiếu monitor trong `getLockedMonitors` hoặc synchronizer trong `getLockedSynchronizers`, kết hợp class/hash + stack.
6. Xem stack của waiter và owner để suy đoán code path và blocking primitive.
7. Lặp nếu owner đang chờ một lock khác; kiểm tra chu trình để phân biệt deadlock/chain hữu hạn.
8. So sánh nhiều snapshots theo thời gian; ưu tiên evidence lặp lại thay vì một stack tức thời.

### Bước 4 — Phân biệt một holder tắc với deadlock

Nếu owner đang chờ external I/O hoặc một latch có controller sẽ release, đó có thể là **prolonged lock hold** chứ không phải deadlock chu trình lock. Nếu chu trình 2+ owners-waiters, `findDeadlockedThreads` có thể phát hiện (phạm vi chỉ platform monitor/ownable sync). Cần xem trace trước khi sửa code.

### Bước 5 — Khắc phục ở mã nguồn, không phải bằng MXBean

Các cách khắc phục thường là:
- Giảm critical section.
- Tránh remote I/O/blocking operations khi đang giữ monitor.
- Dùng lock order nhất quán.
- Thiết kế timeout/cancellation bằng API phù hợp, không “force-unlock” owner từ thread khác.
- Với ReentrantLock, đảm bảo try/finally sau lock.
- Hạn chế dùng một coarse-grained global monitor cho workload nhiều concurrent requests.
- Nếu kết quả chỉ phản ánh virtual threads bị parked, dùng tooling phù hợp hơn thay vì gọi một platform thread là culprit.

## 13. Troubleshooting thường gặp

| Triệu chứng | Khả năng | Cách xác minh / xử lý |
| --- | --- | --- |
| `getLockedMonitors()` rỗng nhưng thấy `synchronized` | Đã gọi overload không yêu cầu monitors; hoặc snapshot khác thời điểm | Dùng true flag nếu supported |
| `getLockedSynchronizers()` rỗng với ReentrantLock | Flag false hoặc JVM không hỗ trợ/không giữ tại thời điểm chụp | Check `isSynchronizerUsageSupported` + true |
| `getLockInfo() == null` | Thread không blocked/waiting như quy định | Kiểm tra state và stack |
| `getLockOwnerId() == -1` | Không có owner xác định | Không tự gán ID đoán |
| `BLOCKED` xuất hiện nhiều | Contention monitor | So owner/stack, không vội kết luận deadlock |
| `WAITING` nhưng lock owner không rõ | Park/Condition/Object.wait | Đọc stack, blocker và semantics primitive |
| ClassName là `ReentrantLock$NonfairSync` | Lock object nội bộ của AQS | So cùng class+identity giữa waiter/owner, không so wrapper |
| Hash của `ReentrantLock` khác `LockInfo` | So hai object khác nhau | Dùng actual LockInfo của synchronizer |
| MonitorInfo depth âm | Không có acquisition frame | Chấp nhận null frame, xem stack/other data |
| Index vào stack bị lệch | Ghép hai snapshots khác nhau | Lấy MonitorInfo và stack từ cùng ThreadInfo |
| `getThreadInfo(id)` stack rỗng | Overload mặc định không lấy stack | Dùng overload có maxDepth |
| `getThreadInfo(ids)` có null | Thread đã kết thúc/ID không thuộc platform live | Kiểm tra null và race |
| `UnsupportedOperationException` | JVM không hỗ trợ requested lock monitoring | Kiểm tra capability flags |
| `findDeadlockedThreads()==null` nhưng app treo | Không có lock-cycle loại được hỗ trợ hoặc chỉ virtual threads/other waits | Xem stacks/JFR/other diagnostics |
| Raw MXBean result là CompositeData | MXBean chuyển Java types sang OpenData | Dùng `ThreadInfo.from/LockInfo.from/MonitorInfo.from` |
| `ClassCastException` raw result → ThreadInfo | Cast sai lớp nhìn JMX | Chuyển từ CompositeData hoặc dùng typed API |
| `MBeanServer.invoke` signature not found | Sai tên operation hoặc raw Java type signature | Dùng `getThreadInfo` với `"[J","boolean","boolean"` |
| `ThreadInfo.toString` bị đổi format | Không có text serialization guarantee | Truy cập API fields |
| Virtual threads không xuất hiện | ThreadMXBean không hỗ trợ virtual threads | `jcmd Thread.dump_to_file`, JFR |
| CPU/blockedTime là `-1` | Monitoring disabled/not supported | Kiểm tra flags và overhead |
| Thread dump nhiều dữ liệu nhạy cảm | Stack traces/locks lộ implementation details | Access control, sanitize và retention |
| Dump tốn CPU/latency | Snapshot sâu/toàn JVM quá thường xuyên | Lấy IDs cụ thể, giới hạn maxDepth/tần suất |

## 14. Kiểm thử tự luyện

**Bài 1 — Identity:** In `className` và `Integer.toHexString(identityHashCode)` của LockInfo từ một waiter thật. Vì sao giá trị này không phải memory address và không thể dùng làm global key?

**Bài 2 — Monitor acquire frame:** Chụp monitor owner từ snapshot. So `monitor.getLockedStackFrame()` với `thread.getStackTrace()[monitor.getLockedStackDepth()]` nếu depth hợp lệ.

**Bài 3 — Overloads:** Với cùng thread owner, lấy `getThreadInfo(id)` rồi `getThreadInfo(new long[]{id},true,true,64)`. So stack/locked monitors. Giải thích “array rỗng” khi không request data.

**Bài 4 — ReentrantLock:** Bổ sung một `ReentrantLock` thứ hai, tạo waiter có kiểm soát. So `getLockInfo` ở waiter với `getLockedSynchronizers` ở owner.

**Bài 5 — Wait với Condition:** Dùng `Condition.await` theo cách có timeout/cancellation để quan sát state/lock owner; phân biệt condition wait với tranh chấp lock trực tiếp.

**Bài 6 — Deadlock detector:** Dùng một thiết kế dependency graph (không tạo deadlock không thể thu hồi) và so `findMonitorDeadlockedThreads` với `findDeadlockedThreads`. Nếu muốn integration test deadlock thật, chạy nó trong **process riêng** có timeout cứng và không dùng nó trong business JVM.

**Bài 7 — JMX raw:** Gọi `MBeanServer.invoke` lấy `CompositeData[]` và xác minh `lockInfo`/`lockedMonitors`/`lockedSynchronizers` trong attributes.

**Bài 8 — Mapping:** Dùng `MonitorInfo.from(CompositeData)` và `LockInfo.from(CompositeData)` đúng schema; thử object `CompositeData` sai schema để quan sát `IllegalArgumentException`.

**Bài 9 — ThreadInfo.from:** Chuyển một raw `CompositeData` của Threading MXBean về ThreadInfo, so lock owner ID và thread state với typed `ThreadMXBean`.

**Bài 10 — Missing owner:** Tạo `LockSupport.parkNanos` theo timeout để quan sát lock owner có thể không xác định. Không giả định mọi park có owner.

**Bài 11 — Virtual threads:** Trên JDK 21+, tạo các virtual threads thử; so khả năng quan sát bằng ThreadMXBean và `jcmd Thread.dump_to_file -format=json`. Không bỏ qua security policy attach/JFR.

**Bài 12 — Safe monitoring:** Đo overhead của `dumpAllThreads(true,true, Integer.MAX_VALUE)` với 10, 1.000 và nhiều platform threads trong benchmark riêng. Điều chỉnh tần suất, không chạy dump liên tục trên đường xử lý request.

**Bài 13 — Snapshot consistency:** Chụp hai lần cùng các threads sau khi holder nhả lock. So từng ThreadInfo và giải thích vì sao snapshot sau có thể null hoặc trạng thái khác.

**Bài 14 — Secret handling:** Viết một tool chỉ log thread ID/state/lock class/hash có kiểm soát, bỏ stack frames chứa thông tin nhạy cảm và dùng retention policy rõ ràng.

## 15. Câu hỏi ôn tập

**1. `LockInfo` chứa những gì?** Class name và identity hash code của lock object.

**2. `MonitorInfo` khác gì?** Extends LockInfo và bổ sung lockedStackDepth/lockedStackFrame cho owned object monitor.

**3. MonitorInfo là loại khóa của ReentrantLock?** Không; nó mô tả object monitor của synchronized.

**4. `ThreadInfo.getLockInfo` có phải lock do thread đang giữ?** Không; đó thường là lock thread đang chờ.

**5. `getLockedMonitors` nói về waiter hay owner?** Các monitors thread đã giữ: owner.

**6. `getLockedSynchronizers` nói về gì?** Ownable synchronizers thread đã giữ, nếu lấy thông tin này.

**7. `getLockOwnerId()==-1` có nghĩa thread 0 giữ lock?** Không; không có owner xác định.

**8. Identity hash code là địa chỉ bộ nhớ thật?** Không có guarantee.

**9. Hash code của ReentrantLock wrapper có bắt buộc bằng LockInfo của AQS sync không?** Không.

**10. `getLockedStackDepth` là line number trong Java source?** Không, nó là index vào StackTraceElement[].

**11. MonitorInfo depth âm có luôn là dữ liệu hỏng?** Không; có thể không có thông tin frame.

**12. `getThreadInfo(id)` có lấy monitors/synchronizers không?** Không, arrays rỗng, stack cũng rỗng.

**13. Dùng API nào để lấy cả hai loại lock?** `getThreadInfo(ids,true,true,maxDepth)` hoặc `dumpAllThreads(true,true,maxDepth)` khi supported.

**14. `isObjectMonitorUsageSupported` kiểm tra gì?** JVM có hỗ trợ quan sát object monitors.

**15. `isSynchronizerUsageSupported` kiểm tra gì?** JVM có hỗ trợ ownable synchronizers.

**16. `getThreadInfo` có thể trả null cho ID hợp lệ không?** Có, nếu thread không live, virtual thread hoặc đã kết thúc.

**17. `findMonitorDeadlockedThreads` có xét ReentrantLock deadlocks không?** Không; method chỉ monitor locks.

**18. `findDeadlockedThreads` xét những gì?** Deadlock cycles của platform threads trên monitors hoặc ownable synchronizers.

**19. Một BLOCKED thread có luôn là deadlock?** Không.

**20. `ThreadMXBean` có quan sát virtual threads không?** Không theo JDK 26 contract.

**21. Công cụ nào có thread dump gồm virtual threads?** `jcmd Thread.dump_to_file` trên JDK hiện hành.

**22. `Thread.dump_to_file` có tự phát hiện deadlock?** Không.

**23. Raw Threading MXBean trả `ThreadInfo[]` hay `CompositeData[]`?** Raw MXBean mapping trả `CompositeData[]` trong ví dụ.

**24. Dùng `LockInfo.from` có nhận `CompositeData` sai schema không?** Có thể ném `IllegalArgumentException`.

**25. Có nên parse `ThreadInfo.toString()` làm format ổn định?** Không.

**26. Thông tin lock snapshot có được dùng để unlock ở thread khác?** Không.

**27. ThreadInfo snapshot có bảo đảm atomic giữa mọi threads?** Không nên giả định.

**28. Java code nguồn của bài tương thích bản nào?** `javac --release 17`; chạy thực tế OpenJDK 24.

**29. 61/61 assertions PASS có chứng minh production-ready và không thể deadlock?** Không; chỉ kiểm tra fixture lock/monitor/JMX trên một runtime.

## Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — LockInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/LockInfo.html): className, identityHashCode, toString, from(CompositeData).
- [Oracle Java SE 26 — MonitorInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MonitorInfo.html): lockedStackDepth, lockedStackFrame và constructor validation.
- [Oracle Java SE 26 — ThreadInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadInfo.html): lock owner, blocked lock, held monitors/synchronizers, stack và JMX mapping.
- [Oracle Java SE 26 — ThreadMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html): getThreadInfo, dumpAllThreads, support flags, deadlock APIs, platform-thread scope.
- [Oracle Java SE 26 — ManagementFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html): getThreadMXBean/getPlatformMBeanServer và ObjectName.
- [Oracle Java SE 26 — java.management module](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/module-summary.html): Java Management/JMX public APIs.
- [Oracle Java SE 26 — JMX MXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MXBean.html): Open Data mapping của LockInfo, MonitorInfo, ThreadInfo.
- [Oracle Java SE 26 — ReentrantLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): ownable lock, ownership, try/finally.
- [Oracle Java SE 26 — LockSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): parking, blocker và ownership caveats.
- [Oracle Java SE 26 — Virtual Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): giám sát virtual threads, JFR, jcmd thread dumps.
- [Oracle Java SE 26 — jcmd](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): Thread.dump_to_file, Thread.print và các format options.
- [Oracle Java SE 26 — CompositeData](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/CompositeData.html): JMX raw structured result.

**Ghi nhớ cuối bài:** **`LockInfo`** trả lời “đối tượng khóa này là gì?”, còn **`MonitorInfo`** trả lời thêm “object monitor này được thread giữ từ stack frame nào?”. `ThreadInfo.getLockInfo()` nói về **khóa đang đợi**; `getLockedMonitors()/getLockedSynchronizers()` nói về **khóa đang giữ**; `getLockOwnerId()` nối waiter đến owner khi có thể. Đọc `ThreadMXBean` với flags true và capability checks; nhớ các overload đơn giản có thể trả empty lock arrays dù thread thực sự giữ khóa. Không dùng identity hash làm địa chỉ, không coi mọi BLOCKED/WAITING là deadlock và không dùng snapshot để điều khiển locks. Với virtual threads hãy dùng `jcmd Thread.dump_to_file`/JFR vì ThreadMXBean chỉ hỗ trợ platform threads. Bài Java17+ đã chạy thật với **61/61 checks PASS**, không có deadlock, cleanup sạch.
