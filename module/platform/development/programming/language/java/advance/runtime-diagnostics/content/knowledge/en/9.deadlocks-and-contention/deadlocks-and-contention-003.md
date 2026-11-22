# 9.3 findMonitorDeadlockedThreads, findDeadlockedThreads và phạm vi platform thread

## Mục tiêu học tập

Một ứng dụng Java có thể ngừng đáp ứng dù process vẫn chạy, CPU không cao và các request threads không thoát khỏi trạng thái chờ. Một trong những khả năng cần kiểm tra là **deadlock**: nhiều thread chờ lock theo một chu trình, khiến không thread nào trong chu trình tiến triển để giải phóng lock mà thread khác cần. Java Management API cung cấp hai phương thức trên `ThreadMXBean` để phát hiện một số chu trình deadlock ngay trong JVM:

- `findMonitorDeadlockedThreads()`: tìm chu trình giữa các **platform threads chờ Java object monitors** (ví dụ `synchronized`).
- `findDeadlockedThreads()`: tìm chu trình giữa các **platform threads chờ object monitors hoặc ownable synchronizers** (ví dụ `ReentrantLock`).

Hai phương thức có tên gần giống nhau nhưng **khác tập lock được xét**, có điều kiện hỗ trợ và cùng giới hạn rất quan trọng: **Java SE 21 `ThreadMXBean` không quản lý/giám sát virtual threads**, nên **chu trình có virtual thread tham gia không được hai phương thức này tìm thấy**.

Sau bài học, bạn sẽ:

1. Phân biệt monitor deadlock, ownable-synchronizer deadlock, contention, starvation và những loại chờ ngoài phạm vi kiểm tra.
2. Hiểu contract về kiểu trả về `long[]`, giá trị `null`, thread ID, `UnsupportedOperationException` và chi phí của các phép phát hiện.
3. Từ ID tìm được, thu `ThreadInfo`, lock owner, stack, monitors và synchronizers để dựng **wait-for graph** có bằng chứng.
4. Viết và chạy một lab Java 17+ cố ý tạo hai kiểu deadlock, dự đoán kết quả của từng phương thức và không để lab treo vô hạn.
5. Hiểu cụ thể vì sao số liệu platform threads không bao phủ virtual threads ở JDK 21, cách mở rộng điều tra bằng thread dump/JFR.
6. Thiết kế cách chẩn đoán production vừa an toàn, vừa phân biệt rõ **“không phát hiện deadlock thuộc phạm vi API”** và **“hệ thống không có vấn đề treo”**.

> Phạm vi chính: Java 17+ với trọng tâm semantics **Java SE 21**, đặc biệt `ThreadMXBean` trong module `java.management`. Những ví dụ có chủ đích tạo deadlock **chỉ dành cho JVM lab**; tuyệt đối không nhúng nguyên mẫu gây deadlock vào service production.

## 1. Đặt nền tảng: deadlock là một chu trình chờ lock

### 1.1 Một chu trình hai thread

Giả sử:

- Platform thread **A** đang giữ lock **L1**, rồi chờ lock **L2**.
- Platform thread **B** đang giữ **L2**, rồi chờ **L1**.
- Hai thread đều không thể đi tới dòng giải phóng lock do đang chờ lock còn lại.

Biểu diễn bằng **wait-for graph**:

```text
Thread A --đợi lock L2 do--> Thread B
Thread B --đợi lock L1 do--> Thread A

Chu trình: A -> B -> A
```

Nếu không có cơ chế hủy/timeout hoặc can thiệp bên ngoài, cả hai thread có thể kẹt mãi. Java-level deadlock detection tìm các **chu trình ownership/waiting** mà JVM có thể mô hình hóa theo loại lock cụ thể, chứ không thử tự quyết định “thread này trông không khỏe”.

Một hệ thống có thể bị treo **mà không có chu trình Java lock**:

- A chờ network read và downstream không phản hồi.
- Mọi worker đang đợi một queue/connection pool, nhưng không sở hữu các lock tạo thành vòng.
- Livelock: các thread vẫn chạy và đổi trạng thái liên tục nhưng không hoàn thành công việc.
- Starvation: thread không được nhận CPU/công việc/tài nguyên vì lịch hoặc cạnh tranh không công bằng.
- Deadlock giữa các transactions ở DB, nhiều services hoặc external distributed locks.
- Virtual-thread cycle, một số native locks, hay các primitives không nằm trong contract của hai API.

Vì vậy **`null` không phải chứng cứ phủ định mọi dạng treo**.

### 1.2 Monitor và ownable synchronizer khác nhau

**Intrinsic object monitor** là cơ chế khóa gắn với object, dùng bởi `synchronized`, `synchronized(this)` hoặc static synchronized methods. Ví dụ:

```java
// Đoạn minh họa đặt trong một method; không phải chương trình độc lập.
synchronized (accountMonitor) {
    synchronized (ledgerMonitor) {
        updateLedger();
    }
}
```

Các biến/method trên thuộc ứng dụng. Thread muốn vào `synchronized` nhưng monitor do thread khác giữ thường có trạng thái Java `BLOCKED`.

**Ownable synchronizer** là một bộ đồng bộ có thể thuộc độc quyền một thread và dựa vào `AbstractOwnableSynchronizer` hoặc lớp con để quản lý ownership. Theo tài liệu Java SE 21, **`ReentrantLock`** và **write lock của `ReentrantReadWriteLock`** là hai ví dụ; **read lock của `ReentrantReadWriteLock` không phải ownable synchronizer** theo cùng nghĩa.

```java
// Đoạn minh họa; giả định lock là ReentrantLock.
lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
```

Khi chờ `ReentrantLock.lock()`, thread có thể hiển thị `WAITING (parking)` thay vì `BLOCKED`. Không được dùng quy tắc “chỉ BLOCKED mới là deadlock”; **ownable-synchronizer cycle** có thể hiện dưới các trạng thái chờ khác monitor entry.

### 1.3 Vì sao cần hai detector?

Một detector chỉ biết về object monitors sẽ không nhất thiết nhận ra các chu trình sở hữu `ReentrantLock`. Java cung cấp:

| API | Loại chu trình được phát hiện | Không bao phủ |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Platform threads chờ **object monitors** trong một vòng ownership | Ownable synchronizer-only cycles, virtual threads, external locks |
| `findDeadlockedThreads()` | Platform threads chờ **object monitors hoặc ownable synchronizers** trong một vòng | Virtual threads, chờ ngoài hai loại lock trên và nhiều loại resource deadlock |
| `dumpAllThreads(...)` | **Thông tin snapshot** platform threads gồm stack/lock theo khả năng VM | Không tự kết luận mọi stuck thread là deadlocked; không gồm virtual threads trong Java 21 |

Bài toán là **phát hiện có phạm vi**, không phải phán quyết cuối cùng về sức khỏe ứng dụng.

## 2. ThreadMXBean nằm ở đâu?

Trong Java:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean = ManagementFactory.getThreadMXBean();
```

Đây là **mã minh họa**, cần đặt trong method/class để biên dịch. `ManagementFactory.getThreadMXBean()` trả management bean của **JVM hiện tại**, không phải JVM khác ở một máy remote. Cùng interface này có thể được truy cập qua **platform MBeanServer** hoặc JMX connector được bảo vệ, với ObjectName chuẩn:

```text
java.lang:type=Threading
```

Các phương thức chính liên quan bài học:

```java
long[] monitorIds = bean.findMonitorDeadlockedThreads();
long[] allIds = bean.findDeadlockedThreads();
boolean monitorSupported = bean.isObjectMonitorUsageSupported();
boolean synchronizerSupported = bean.isSynchronizerUsageSupported();
```

Đoạn này **không phải chương trình độc lập**; ngoài ra, dòng gọi `findDeadlockedThreads()` cần được bảo vệ nếu VM không hỗ trợ ownable synchronizer usage.

### 2.1 Lấy đúng scope: platform threads

Java SE 21 ghi rõ `ThreadMXBean` hỗ trợ theo dõi và quản lý **platform threads**, vốn thường ánh xạ lên kernel/OS threads. **Virtual threads** là một kiểu `Thread` khác, được scheduler quản lý linh hoạt, có thể mount/unmount khỏi carrier platform threads.

`ThreadMXBean` **không hỗ trợ quản lý/giám sát virtual threads** trong Java 21; hai detector **không tìm chu trình có virtual threads tham gia**. Đó là một giới hạn được công bố trong API contract, không phải bug của một dashboard.

Kéo theo:

- `getThreadCount()` là số **live platform threads** theo bean, không phải tổng Java logical tasks/virtual threads.
- `getAllThreadIds()` trả ID các **live platform threads**; không gồm virtual thread IDs.
- `dumpAllThreads(...)` trả thông tin **live platform threads**; không cho danh sách đầy đủ virtual threads.
- `getThreadInfo(id)` với một **virtual thread ID** trả `null` theo contract ở Java 21.
- `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` chỉ xét **cycles gồm platform threads**; có thể bỏ lỡ chu trình giữa virtual threads hoặc chu trình hỗn hợp có virtual thread.

Một ứng dụng có 20.000 virtual threads nhưng `getThreadCount()` chỉ vài chục **không có nghĩa** 19.970 threads đã thoát; hai số đo có đối tượng thống kê khác nhau.

## 3. findMonitorDeadlockedThreads(): chỉ object monitors

### 3.1 Contract chính xác

Chữ ký:

```java
long[] findMonitorDeadlockedThreads()
```

Ý nghĩa trên Java SE 21:

- Tìm **chu trình platform threads bị deadlock khi chờ lấy object monitor**.
- Bao gồm tình huống chờ vào `synchronized` và một số tình huống **chờ tái nhận monitor sau `Object.wait()`** theo contract.
- Một monitor deadlock xảy ra khi mỗi thread trong vòng đợi monitor đang thuộc một thread kế tiếp trong vòng.
- Trả **mảng ID của các platform threads phát hiện bị deadlocked**.
- Nếu không phát hiện deadlock thuộc phạm vi này, trả **`null`**, không phải bắt buộc `new long[0]`.
- Không phát hiện **cycles có virtual threads**; cũng không xét ownable synchronizers như `ReentrantLock`.
- Được thiết kế cho **troubleshooting**, không phải điều khiển synchronization; có thể tốn chi phí.

Ví dụ đọc trả về:

```java
long[] ids = bean.findMonitorDeadlockedThreads();
if (ids == null) {
    System.out.println("No monitor deadlock detected in platform threads");
} else {
    System.out.println("Monitor deadlocked platform threads: " + ids.length);
}
```

Đoạn trên chỉ minh họa trong method có `bean`. Thông điệp nên được hiểu là **“detector không phát hiện trong phạm vi vào thời điểm gọi”**, không phải “ứng dụng không treo”.

### 3.2 Deadlock hai monitors

Giả sử:

```text
platform-A:
  giữ intrinsic monitor A
  đang chờ intrinsic monitor B

platform-B:
  giữ intrinsic monitor B
  đang chờ intrinsic monitor A

monitor wait-for graph: platform-A -> platform-B -> platform-A
```

Trong một JVM HotSpot hỗ trợ bình thường, khi cả hai đã bước vào trạng thái chờ, cả `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` **đều có thể** phát hiện vòng này. Kết quả không bắt buộc là ID theo thứ tự tên, không có hợp đồng rằng ID nào xuất hiện trước.

### 3.3 Trường hợp thường không bị API này phát hiện

- A và B dùng `ReentrantLock` thay cho `synchronized`: detector chỉ monitor sẽ không thấy vòng khóa thuần ownable synchronizer.
- A bị treo vì HTTP request không có timeout: không có object monitor cycle rõ.
- Một thread chờ `Condition.await()`, executor/queue hoặc I/O lâu: chỉ có trạng thái chờ chưa đủ tạo cycle ownership monitors.
- Deadlock chứa ít nhất một virtual thread trong Java 21: ngoài phạm vi API.
- Thread chết/restart ngay lúc đo: snapshot có thể không ổn định; không suy từ một lần trả `null` rằng không có vấn đề trong cửa sổ trước đó.

## 4. findDeadlockedThreads(): cả monitors lẫn ownable synchronizers

### 4.1 Contract chính xác

Chữ ký:

```java
long[] findDeadlockedThreads()
```

Khác biệt chính là detector xét **object monitor hoặc ownable synchronizer**. Trong một vòng:

- A có thể giữ ownable synchronizer L1 và đợi L2.
- B giữ L2 và đợi L1.
- Hoặc tùy cấu trúc, chu trình có thể chứa cả monitor lẫn ownable synchronizer.

Khi phát hiện, trả `long[]` gồm **ID của platform threads** trong chu trình; khi không phát hiện, trả **`null`**. Nếu JVM **không hỗ trợ monitoring ownable synchronizer usage**, phương thức có thể ném **`UnsupportedOperationException`**.

Vì vậy dùng:

```java
if (bean.isSynchronizerUsageSupported()) {
    long[] ids = bean.findDeadlockedThreads();
    // null => không phát hiện cycle thuộc phạm vi API tại thời điểm đo
} else {
    // Không gọi findDeadlockedThreads; ghi "unsupported".
}
```

Đoạn này là minh họa, không phải chương trình độc lập. Trong môi trường quản lý có security restrictions, lệnh còn có thể ném `SecurityException` nếu caller thiếu `ManagementPermission("monitor")` theo contract JDK 21. Đừng biến exception thành “không phát hiện deadlock”.

### 4.2 So sánh hai API khi dùng ReentrantLock

Ví dụ tình huống:

```text
platform-A:
  giữ ReentrantLock L1
  gọi L2.lock() và đang chờ

platform-B:
  giữ ReentrantLock L2
  gọi L1.lock() và đang chờ

ownable synchronizer wait-for graph: A -> B -> A
```

Khi đã deadlock trên JVM có support:

- `findMonitorDeadlockedThreads()` thường **`null`** — không có monitor cycle.
- `findDeadlockedThreads()` có thể trả ID của **A và B** — vì xét ownable synchronizers.

**Không suy luận rằng mọi primitive trong `java.util.concurrent` đều được `findDeadlockedThreads()` hiểu.** Ví dụ semaphore thường không có một exclusive owner theo `AbstractOwnableSynchronizer`; read lock của `ReentrantReadWriteLock` không thuộc danh mục ownable synchronizer như write lock. Hãy đọc contracts từng primitive khi đánh giá detector coverage.

### 4.3 isObjectMonitorUsageSupported và isSynchronizerUsageSupported

Hai capability probes nói về **monitoring usage** của VM:

| Phương thức | Ý nghĩa |
| --- | --- |
| `isObjectMonitorUsageSupported()` | VM có thể cung cấp thông tin object monitor usage khi dump thread details không? |
| `isSynchronizerUsageSupported()` | VM có thể cung cấp thông tin ownable synchronizer usage không? |
| `findDeadlockedThreads()` | **Phụ thuộc ownable support**, có thể ném `UnsupportedOperationException` |
| `getThreadInfo(ids, true, true)` | Chỉ bật tham số locked monitors/synchronizers nếu hỗ trợ; nếu không có thể ném `UnsupportedOperationException` |

Đừng coi `isObjectMonitorUsageSupported() == false` đồng nghĩa `findMonitorDeadlockedThreads()` chắc chắn bị cấm: contract của phép tìm monitor deadlock và contract của **liệt kê toàn bộ monitors đang giữ** là các mục riêng. Theo dõi cả lỗi thực tế và tài liệu VM.

## 5. Thứ được trả về là thread ID, không phải ThreadInfo

Hai detector trả `long[]` (hoặc `null`), **không trả ThreadInfo[]** và cũng không cho bạn trực tiếp biết source line. Với mỗi ID, cần hỏi thêm thông tin bằng `ThreadMXBean.getThreadInfo(...)`.

Ví dụ khai thác đúng:

```java
// Đặt bên trong method, với bean đã lấy từ ManagementFactory.
long[] ids = bean.isSynchronizerUsageSupported()
        ? bean.findDeadlockedThreads()
        : bean.findMonitorDeadlockedThreads();

if (ids != null) {
    boolean monitors = bean.isObjectMonitorUsageSupported();
    boolean ownables = bean.isSynchronizerUsageSupported();

    java.lang.management.ThreadInfo[] infos =
            bean.getThreadInfo(ids, monitors, ownables, 32);

    for (java.lang.management.ThreadInfo info : infos) {
        if (info == null) {
            continue; // Thread có thể đã thoát giữa hai lần đo.
        }
        System.out.println(info.getThreadName());
        System.out.println(info.getThreadState());
        System.out.println(info.getLockName());
        System.out.println(info.getLockOwnerName());
    }
}
```

Đây là **đoạn minh họa**, không độc lập. `getThreadInfo(long[], boolean, boolean, int)` trả thông tin có **stack depth tối đa 32** trong ví dụ; các flag yêu cầu locked monitors/synchronizers chỉ được bật nếu VM support. Một thread có thể kết thúc giữa lúc detector trả ID và lúc lấy `ThreadInfo`; API có thể trả phần tử `null`. Như vậy phải thiết kế quy trình với **race conditions**, không giả định snapshot xuyên nhiều lệnh là nguyên tử.

### 5.1 ThreadInfo chứa gì?

Một `ThreadInfo` thường cho:

- `getThreadId()` — ID thread trong JVM, **không phải native OS TID/PID**.
- `getThreadName()` — tên thread; không buộc unique.
- `getThreadState()` — `BLOCKED`, `WAITING`, `TIMED_WAITING`... theo mô hình Java.
- `getLockInfo()`/`getLockName()` — lock mà thread đang chờ nếu có thông tin.
- `getLockOwnerId()`/`getLockOwnerName()` — thread được biết đang sở hữu lock mà thread này chờ; **`-1`** hoặc `null` có thể chỉ không biết/không có owner.
- `getStackTrace()` — các stack frames giúp tìm class/method và điểm đang chờ.
- `getLockedMonitors()` — monitors thread đang giữ khi requested/supported.
- `getLockedSynchronizers()` — ownable synchronizers thread đang giữ khi requested/supported.

Một Java monitor có thể in `java.lang.Object@7f39...`. Đó là class + identity-hash-based representation của lock, **không phải tên nghiệp vụ** và không phải pointer heap công khai đáng tin trên mọi VM. `ThreadInfo.getLockOwnerId()` hữu ích hơn khi dựng cạnh chờ **thread → owner**.

### 5.2 Vẽ wait-for graph bằng dữ liệu thực

Giả sử sau khi lấy thông tin, bạn thấy:

```text
threadId=42, name=checkout-A, lockOwnerId=43, lock=java.lang.Object@aaa
threadId=43, name=checkout-B, lockOwnerId=42, lock=java.lang.Object@bbb
```

Đây là **dữ liệu mô phỏng**, không phải output lab. Bạn có hai cạnh:

```text
checkout-A (42) --waiting for lock owned by--> checkout-B (43)
checkout-B (43) --waiting for lock owned by--> checkout-A (42)
```

Hai cạnh tạo vòng A→B→A. Muốn giải thích nguyên nhân trong source, cần xem **stack frames ở thời điểm chờ**, method đang nắm lock và thứ tự gọi. Không được chỉ dựa vào tên `checkout-A`/`checkout-B` vì tên thread có thể trùng hoặc đổi trong một vòng đời.

### 5.3 Không trộn ID giữa những JVM khác nhau

`ThreadMXBean` thread IDs có nghĩa trong JVM chạy tại **một thời điểm**. Thread ID là số dương, unique trong lifetime của thread nhưng **có thể tái sử dụng sau khi thread chết**. Các process khác nhau hoàn toàn có thể có thread ID giống nhau. Gắn dữ liệu với service, host/container, PID **và process start time**, cộng timestamp UTC trước khi so snapshot.

Đặc biệt, `getThreadInfo(id) == null` có thể nghĩa thread đã chết, không tồn tại hoặc là virtual thread ID (Java 21), **không chứng minh** detector trả ID sai hay sự cố đã tự khắc phục.

## 6. Lab 1: tạo deadlock intrinsic monitors trên Java 17+

Bài thực hành hoàn chỉnh ở mục 8 có hai chế độ `monitor` và `ownable`. Trước khi xem code, hãy dự đoán chế độ monitor:

```text
Platform thread monitor-A:
  synchronized(A) {
      đợi monitor-B giữ B
      synchronized(B) { ... }
  }

Platform thread monitor-B:
  synchronized(B) {
      đợi monitor-A giữ A
      synchronized(A) { ... }
  }
```

Một `CountDownLatch(2)` bảo đảm **cả hai đã lấy lock đầu tiên** trước khi thử lock thứ hai. Nhờ đó tránh race trong đó thread A lấy cả A lẫn B trước khi B kịp giữ B; nếu không dùng latch, lab có thể không hình thành deadlock.

Khi cả hai thread thật sự chờ lẫn nhau:

| API | Dự kiến trên HotSpot có hỗ trợ |
| --- | --- |
| `findMonitorDeadlockedThreads()` | Hai ID trong cycle, không bảo đảm thứ tự |
| `findDeadlockedThreads()` | Cũng phát hiện hai ID nếu ownable monitoring supported |
| `getThreadInfo(...).getThreadState()` | Thường `BLOCKED` cho hai thread chờ `synchronized` |
| `getLockOwnerId()` | ID của thread đang giữ monitor mà thread hiện tại cần |

Một API trả kết quả **sau khi deadlock đã hình thành**, nên lab tránh kỳ vọng tại đúng nanosecond hai threads vào vòng. Đó là lý do code chờ một khoảng ngắn và kiểm tra một số lần có giới hạn.

### 6.1 Điều monitor detector **không** nói

Phương thức không báo bạn phương pháp sửa thứ tự lock, không bảo đảm lấy được stack từ một process đã restart, và không tự động giải phóng monitors. Một detected cycle là dữ kiện mạnh rằng các platform threads đang kẹt theo mô hình lock mà VM theo dõi. Để xác định sửa ở đâu, cần tìm lần nắm lock trước, thứ tự acquire, callback/tầng thư viện lồng nhau và số lượng code paths có cùng lock objects.

**Không dùng `Thread.stop()` để “chữa” deadlock production**: phương thức này bị deprecated vì không an toàn; giết một thread đang giữ monitors có thể làm hỏng invariant hoặc dữ liệu. Cần sửa thiết kế locking và có quy trình xử lý incident.

## 7. Lab 2: deadlock ReentrantLock chỉ được detector rộng thấy

Đối với `ReentrantLock`, mỗi thread sở hữu một `ReentrantLock` khác nhau, cùng đi tới acquire lock thứ hai sau latch:

```text
Platform thread ownable-A:
  giữ ReentrantLock L1
  thử lock(L2) --> đợi thread ownable-B

Platform thread ownable-B:
  giữ ReentrantLock L2
  thử lock(L1) --> đợi thread ownable-A

Cycle: ownable-A -> ownable-B -> ownable-A
```

Trên HotSpot có support:

- `findMonitorDeadlockedThreads()` thường trả `null` vì **không phải intrinsic monitor cycle**.
- `findDeadlockedThreads()` tìm được hai platform thread IDs đang kẹt trên **ownable synchronizers**.
- Thread states có thể là `WAITING (parking)`, không phải `BLOCKED`.
- `ThreadInfo.getLockedSynchronizers()` với flag tương ứng có thể chỉ ra lock mà mỗi thread đang sở hữu.

Điểm này là bài học quan trọng: **không thể thay `findDeadlockedThreads()` bằng `findMonitorDeadlockedThreads()` trong hệ thống dùng `ReentrantLock` rồi tin kết quả `null` nghĩa “không deadlock”.**

### 7.1 Phân biệt exclusive lock và semaphore

`ReentrantLock` có exclusive owner theo `AbstractOwnableSynchronizer`. `Semaphore` có permits nhưng không mô tả một **owner thread duy nhất** theo cùng contract. Hai tasks có thể chờ permits vô hạn hoặc tạo circular dependencies mức ứng dụng mà detector không nhận diện. Vì vậy “sử dụng `java.util.concurrent`” không đủ để khẳng định detector rộng bao phủ mọi tình huống.

Tương tự, một `Condition.await()` tạm thời **nhả associated lock** khi chờ và nhận lại khi hoàn tất theo contract. Một thread chờ condition chưa chắc đang giữ một lock trong wait-for cycle có thể xác định. Đừng coi mọi `WAITING` ở `LockSupport.park` là ownable-synchronizer deadlock.

## 8. Bài thực hành hoàn chỉnh Java 17+: so sánh hai detector

Tạo file **`DeadlockMxBeanLab.java`**. Chương trình có hai chế độ command line:

- `monitor` — cố ý tạo chu trình bằng `synchronized`.
- `ownable` — cố ý tạo chu trình bằng `ReentrantLock`.

**Chỉ chạy trong terminal lab, không nhúng mã tạo deadlock vào ứng dụng thật.** Threads được đặt **daemon** để process vẫn thoát sau khi main in kết quả; `daemon` không tự giải deadlock và **không phải cách xử lý deadlock production**.

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public final class DeadlockMxBeanLab {
    private static final Object MONITOR_A = new Object();
    private static final Object MONITOR_B = new Object();
    private static final ReentrantLock LOCK_A = new ReentrantLock();
    private static final ReentrantLock LOCK_B = new ReentrantLock();

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Lab interrupted", e);
        }
    }

    private static void monitorCycle(Object first, Object second,
                                     CountDownLatch firstLocksHeld) {
        synchronized (first) {
            firstLocksHeld.countDown();
            await(firstLocksHeld);
            synchronized (second) {
                // Với hai thread đảo thứ tự locks, đoạn này không tới.
            }
        }
    }

    private static void ownableCycle(ReentrantLock first, ReentrantLock second,
                                     CountDownLatch firstLocksHeld) {
        first.lock();
        try {
            firstLocksHeld.countDown();
            await(firstLocksHeld);
            second.lock();
            try {
                // Với hai thread đảo thứ tự locks, đoạn này không tới.
            } finally {
                second.unlock();
            }
        } finally {
            first.unlock();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("DeadlockMxBeanLab READY");
        String mode = args.length == 1 ? args[0] : "";
        if (!mode.equals("monitor") && !mode.equals("ownable")) {
            System.out.println("Usage: java DeadlockMxBeanLab monitor|ownable");
            return;
        }

        System.out.println("mode=" + mode);
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        if (mode.equals("ownable") && !bean.isSynchronizerUsageSupported()) {
            System.out.println("ownable detection unsupported on this JVM");
            return;
        }

        CountDownLatch firstLocksHeld = new CountDownLatch(2);

        Runnable a = mode.equals("monitor")
                ? () -> monitorCycle(MONITOR_A, MONITOR_B, firstLocksHeld)
                : () -> ownableCycle(LOCK_A, LOCK_B, firstLocksHeld);
        Runnable b = mode.equals("monitor")
                ? () -> monitorCycle(MONITOR_B, MONITOR_A, firstLocksHeld)
                : () -> ownableCycle(LOCK_B, LOCK_A, firstLocksHeld);

        Thread ta = new Thread(a, mode + "-A");
        Thread tb = new Thread(b, mode + "-B");
        ta.setDaemon(true);
        tb.setDaemon(true);
        ta.start();
        tb.start();

        firstLocksHeld.await(); // Cả hai đang giữ lock thứ nhất.

        long[] monitorIds = null;
        long[] allIds = null;
        for (int attempt = 0; attempt < 5; attempt++) {
            Thread.sleep(200L); // Cho phép hai thread vào lock thứ hai.
            monitorIds = bean.findMonitorDeadlockedThreads();
            if (bean.isSynchronizerUsageSupported()) {
                allIds = bean.findDeadlockedThreads();
            }

            if (mode.equals("monitor") && monitorIds != null) {
                break;
            }
            if (mode.equals("ownable") && allIds != null) {
                break;
            }
        }

        System.out.println("monitorCycleDetected=" + (monitorIds != null));
        if (bean.isSynchronizerUsageSupported()) {
            System.out.println("allCycleDetected=" + (allIds != null));
        } else {
            System.out.println("allCycleDetected=unsupported");
        }

        long[] ids = allIds != null ? allIds : monitorIds;
        if (ids != null) {
            boolean monitors = bean.isObjectMonitorUsageSupported();
            boolean synchronizers = bean.isSynchronizerUsageSupported();

            ThreadInfo[] details =
                    bean.getThreadInfo(ids, monitors, synchronizers, 24);

            for (ThreadInfo info : details) {
                if (info != null) {
                    System.out.println("thread=" + info.getThreadName()
                            + " state=" + info.getThreadState()
                            + " waitsForOwner=" + info.getLockOwnerName());
                }
            }
        }

        System.out.println("DeadlockMxBeanLab DONE");
    }
}
```

Biên dịch:

```bash
javac DeadlockMxBeanLab.java
```

Chạy mỗi chế độ **ở một process JVM lab riêng**, bởi mỗi lần sẽ tạo một chu trình không giải được trong process đó:

```bash
java DeadlockMxBeanLab monitor
java DeadlockMxBeanLab ownable
```

**Dòng stdout đầu tiên chính xác trong cả hai chế độ**:

```text
DeadlockMxBeanLab READY
```

Dòng kế tiếp tương ứng là **`mode=monitor`** hoặc **`mode=ownable`**. Các giá trị detection sau đó **phụ thuộc timing, implementation và support**; không phải stdout byte-for-byte được hứa trên mọi JVM.

Trên HotSpot JDK 21 với ownable support hoạt động và deadlock đã hình thành, **kỳ vọng điển hình**:

| Chạy lab | monitorCycleDetected | allCycleDetected | Thread state thường gặp |
| --- | --- | --- | --- |
| `java DeadlockMxBeanLab monitor` | `true` | `true` | Hai thread ở `BLOCKED` |
| `java DeadlockMxBeanLab ownable` | `false` | `true` | Hai thread ở `WAITING (parking)` |

Khi đọc dòng `thread=...`, thứ tự hai thread IDs **không được API bảo đảm**. `waitsForOwner` phụ thuộc thời điểm/VM, nên không đặt expected output cố định. Nếu hệ thống không hỗ trợ ownable usage, chương trình in thông báo unsupported và **không gọi** detector rộng trong chế độ ownable.

### 8.1 Vì sao main có thể kết thúc khi threads đã deadlock?

Hai threads cố ý tạo deadlock được đặt `daemon=true`, nên **chúng không giữ JVM tiếp tục chạy khi chỉ còn daemon threads**. Main có thể in `DONE` rồi kết thúc, và VM exit. Điều đó chỉ giúp lab không treo vô thời hạn sau khi quan sát, **không có nghĩa deadlock được giải phóng**.

Nếu bạn thay bằng **non-daemon threads**, JVM có thể tiếp tục chạy mãi do các thread deadlocked không thoát. Khi đó cần dừng lab bằng quy trình thử nghiệm, **không coi `Thread.stop()` hoặc `System.exit()` là fix cho deadlock production**.

### 8.2 Vì sao phải dùng CountDownLatch?

Không có `CountDownLatch`, scheduler có thể cho A lấy lock thứ nhất lẫn thứ hai rồi nhả trước khi B bắt đầu; khi đó **không có deadlock** và detector trả `null` dù source code có thứ tự lock đảo. Latch đảm bảo mỗi thread đã giữ lock đầu tiên trước khi cùng tiến tới yêu cầu lock thứ hai.

Đây là kỹ thuật để tạo **điều kiện test có kiểm soát**, không dùng để đồng bộ phần mềm thật bằng cách cố giữ locks qua một pha chờ.

### 8.3 Tại sao kết quả ở lab có thể khác bảng?

- JVM không phải HotSpot hoặc có capability khác.
- Lab chưa kịp hình thành cycle tại một snapshot; máy quá tải/scheduling trễ.
- Security policy chặn các operations.
- Process cũ đã thoát, bạn đang xem terminal của một lần chạy mới.
- Có thay đổi code lab, thread bị interrupt hoặc lỗi trong lúc giữ/gọi locks.
- Detector có overhead và timing khác trong VM implementation.

Để kiểm chứng, gắn PID, lấy `jcmd <PID> Thread.print -l` **trong lúc process còn chạy** (với lab daemon thoát nhanh, bạn có thể cần giữ main lâu hơn theo kế hoạch riêng), hoặc ghi thêm `ThreadInfo`. Không suy từ một test ngoài cửa sổ rằng API sai.

### 8.4 Cách đọc một kết quả chứa owner

Giả sử output mô phỏng:

```text
monitorCycleDetected=true
allCycleDetected=true
thread=monitor-A state=BLOCKED waitsForOwner=monitor-B
thread=monitor-B state=BLOCKED waitsForOwner=monitor-A
```

Hai dòng cuối biểu diễn vòng A→B→A; đây **không phải stdout bắt buộc** về thứ tự hoặc số lượng dòng thực của mọi VM. Với ownable mode, state có thể là `WAITING` thay `BLOCKED` nhưng owner vẫn cho biết vòng; không dùng state một mình để kết luận.

## 9. Java 21 virtual threads: giới hạn cần chứng minh bằng API

Java 21 có `Thread.startVirtualThread(...)`, nhưng `ThreadMXBean` chỉ giám sát **platform threads**. Phần này dùng một **lab riêng chỉ chạy trên JDK 21+** để kiểm tra một virtual thread đang còn sống có xuất hiện trong `getThreadInfo` hay không.

Tạo file **`VirtualThreadMxBeanScopeLab.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;

public final class VirtualThreadMxBeanScopeLab {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread virtual = Thread.startVirtualThread(() -> {
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        entered.await(); // Virtual thread đã bắt đầu và chưa thoát.
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();

        System.out.println("isVirtual=" + virtual.isVirtual());
        System.out.println("mxbeanInfoPresent=" +
                (bean.getThreadInfo(virtual.threadId()) != null));

        release.countDown();
        virtual.join();
    }
}
```

Biên dịch và chạy **JDK 21 hoặc cao hơn**, **không** dùng JDK 17 vì các APIs virtual thread chưa được đưa vào chuẩn Java 17:

```bash
javac VirtualThreadMxBeanScopeLab.java
java VirtualThreadMxBeanScopeLab
```

**Stdout chính xác trên Java SE 21 theo contract:**

```text
isVirtual=true
mxbeanInfoPresent=false
```

Lý do: thread thực sự là virtual (được tạo bằng `startVirtualThread`); `ThreadMXBean.getThreadInfo` không theo dõi virtual threads nên trả `null` ngay cả khi thread vẫn đang chờ latch. **Đừng diễn giải false thành virtual thread đã kết thúc hoặc không có work cần xử lý.**

### 9.1 Tại sao không thể suy luận chu trình virtual từ platform-thread counters?

Virtual threads có thể **unmount** khỏi carrier platform thread khi chờ; trạng thái logical task không tương đương số platform workers. Ví dụ:

- Hai virtual threads cùng dùng `ReentrantLock` theo thứ tự ngược và tạo chu trình.
- `findDeadlockedThreads()` có thể trả `null` vì cả hai là virtual threads.
- `getAllThreadIds()` không liệt kê ID virtual threads, dù chúng còn sống.
- Một platform thread đợi virtual thread qua `join` cũng không tự tạo một **platform-only monitor/ownable cycle** thuộc phạm vi detector.

Tài liệu JDK 21 nói rõ các cycles có virtual threads **không được hai methods tìm thấy**. Vì vậy khi chạy application theo mô hình nhiều virtual threads, “deadlock detector của ThreadMXBean báo không có deadlock” cần được trình bày theo **giới hạn API**, không phải xác nhận hệ thống hoàn toàn không kẹt.

### 9.2 Nguồn dữ liệu bổ sung cho virtual threads

Tùy JDK/vendor, cân nhắc:

- `jcmd <PID> help Thread.dump_to_file` rồi dùng command nếu **target hỗ trợ**; Java 21 có hướng dẫn thread dump riêng cho virtual threads dạng text/JSON. File được **JVM đích** ghi tại filesystem của nó.
- **JFR** để quan sát events/samples liên quan virtual threads, ví dụ `jdk.VirtualThreadPinned` hoặc `jdk.VirtualThreadSubmitFailed` nếu có trong cấu hình JFR của JDK đang chạy.
- App-level timeout/queue/request tracing, structured task scopes khi được hỗ trợ, metrics của executor/scheduler hoặc instrumentation phù hợp.
- Nghi vấn native lock, external DB/redis/distributed lock: quan sát hệ thống tương ứng, không suy từ một MXBean.

Một thread dump chỉ là snapshot lúc thu; JFR được bật trước sự cố mới có thể chứa timeline trước đó. Không giả định mọi tùy chọn trong JDK mới đều có trên chính JVM 21 đang chạy; **kiểm tra `jcmd PID help` và tài liệu vendor**.

## 10. Hai detector không tìm những gì?

### 10.1 Contention thông thường không phải deadlock

Một thread đang giữ monitor trong 10 ms, các thread khác `BLOCKED` rồi tất cả tiếp tục chạy, đó là contention. Có thể làm latency tăng, nhưng **không có chu trình chờ vĩnh viễn**. Deadlock detection trả `null` vẫn phù hợp.

Nếu contention cao, hãy xem `ThreadInfo`, JFR lock/park events, request p99 và thời lượng giữ locks; vấn đề có thể là lock scope rộng chứ không phải deadlock cycle.

### 10.2 Starvation và thread pool exhaustion

Một thread pool có 20 workers, tất cả workers chờ futures chạy trên **chính pool** nhưng không còn worker rảnh để chạy các futures ấy. Đây có thể là **thread starvation deadlock** ở cấp scheduling/queue, không nhất thiết tạo ownership cycle của object monitor hoặc ownable synchronizer. Hai phương thức tìm Java lock cycles có thể trả `null`.

Cần kiểm tra queue, active worker count, tasks waiting/runnable, dependency graph, timeout policies và structured concurrency/executor design. Nếu có thể, thu vài thread dumps cách nhau phù hợp và đối chiếu throughput.

### 10.3 I/O, DB và distributed resource deadlocks

- Java thread đợi socket read khi downstream đứng im.
- Một SQL transaction bị chặn bởi lock ở database.
- Một service giữ distributed lock trong Redis, chờ kết quả từ service khác đang cần lock đó.
- Native code của thư viện tự dùng mutex ngoài những object monitors/ownable synchronizers được Java Management API theo dõi.

Các hiện tượng có thể làm hệ thống treo rất giống deadlock nhưng **không được hai detectors đảm bảo nhận diện**. Hãy xem database lock graph, trace/span, network telemetry, native profiler và logs có quyền phù hợp.

### 10.4 Livelock

Livelock là trường hợp các threads **vẫn làm việc, đổi trạng thái và phản ứng lẫn nhau** nhưng liên tục không hoàn thành mục tiêu. Có thể không tồn tại thread nào ở trạng thái chờ monitor tạo chu trình rõ. Cần time-series progress, counters, traces và profiler để xác nhận.

### 10.5 Virtual threads hoặc hỗn hợp

Chỉ cần một virtual thread trong cycle là **nằm ngoài phạm vi hai methods** ở Java 21. Một platform thread có thể đang chờ một virtual thread hoặc ngược lại; detector không có contract tìm toàn bộ kiểu mixed cycle. Đừng dùng output của ThreadMXBean như “chứng nhận không deadlock” cho một hệ thống virtual-thread-heavy.

## 11. Phân biệt giá trị null, unsupported và thông tin bị giới hạn

Ba trạng thái rất khác nhau:

| Trạng thái | Diễn giải đúng | Bước kế tiếp |
| --- | --- | --- |
| `find...() == null` | Detector không tìm thấy cycle thuộc **phạm vi nó hỗ trợ** vào thời điểm gọi | Kiểm tra loại lock, virtual threads, thời điểm capture; xem metrics/dump |
| `UnsupportedOperationException` ở `findDeadlockedThreads()` | JVM không hỗ trợ monitoring ownable synchronizers (hoặc capability tương ứng) | Dùng monitor-only detector nếu phù hợp; ghi rõ unsupported |
| `SecurityException` | Caller bị chặn theo policy/quyền monitoring | Xin quyền/đường chẩn đoán hợp lệ; không bypass |
| `getThreadInfo(id) == null` | Thread có thể đã chết/không tồn tại hoặc là virtual ID; có race giữa calls | Kiểm tra identity/time và thu snapshot mới |
| `ids != null` | Có platform threads nằm trong cycle được tìm thấy | Thu ThreadInfo/stack/owners, phân tích lock acquisition order và triage incident |

Không được chuyển **unsupported** thành `false` hoặc `null` trong telemetry một cách im lặng. Nếu dashboard xuất `deadlock_detected=0` khi detector chưa chạy thành công, người xem sẽ hiểu nhầm “đã kiểm tra và không có”. Tách **status** của phép kiểm tra và **result**:

```text
check_status = success | unsupported | denied | error
result       = found | not_found | unknown
scope        = platform_threads, object_monitors | object_monitors_and_ownable
captured_at  = timestamp
```

Đây là schema đề xuất để giải thích, **không phải output API**. Khi không chạy được, giữ `result=unknown`, tránh tạo false reassurance.

### 11.1 Giá trị ID cần đọc đúng

`ThreadMXBean` ID là **long Java thread ID**, không phải:

- OS process PID.
- HotSpot native thread ID `nid=0x...` trong text thread dump.
- VM internal `tid=0x...` pointer.
- Một ID duy nhất toàn cluster hoặc bền vững qua JVM restart.

Nếu so `ThreadInfo` với `jcmd Thread.print`/`jstack`, phải đối chiếu thông tin nhận dạng process, tên, Java thread ID và native ID theo format của chính JVM. Không đoán từ hai số cùng giá trị.

### 11.2 Bài toán race khi đọc state

Chuỗi gọi có thể là:

```text
T0: findDeadlockedThreads() -> IDs
T1: getThreadInfo(IDs, ...) -> stack/lock details
T2: serialize/export data -> logs/dashboard
```

Vì JVM hoạt động song song, thông tin tại T0 và T1 **không phải một giao dịch snapshot nguyên tử**. Với một deadlock monitors thật và không có external intervention, chu trình thường tồn tại lâu; nhưng code tổng quát vẫn cần xử lý thread đã chết/đã restart/đã đổi trạng thái. Không ép `ThreadInfo` bị null thành một object giả.

## 12. Tác động vận hành: không dùng detector làm khóa đồng bộ

Tài liệu API nói rõ hai methods dành cho **troubleshooting**, không phải **synchronization control**, và có thể là thao tác tốn chi phí. Do đó:

- Không gọi `findDeadlockedThreads()` trên mỗi request HTTP chỉ để quyết định có được lock tiếp không.
- Không dùng kết quả `null` để bỏ qua timeout/lock ordering hoặc “tự tin” hệ thống an toàn.
- Không lập lịch kiểm tra mỗi mili-giây trên JVM có rất nhiều platform threads mà chưa đo overhead.
- Không gọi đồng thời trên toàn bộ replicas lúc một sự cố CPU/memory pressure đang diễn ra mà không cân nhắc tác động.
- Nếu dùng JMX remote, giới hạn network/authentication/authorization; management endpoints có thể có operations khác làm đổi JVM state.
- Không biến các thông tin lock/stack có thể lộ kiến trúc nội bộ, thread names, paths hoặc request identifiers thành dữ liệu công khai.

Trong production, quy trình hợp lý là **kích hoạt theo triệu chứng** (latency spike/stall), thu 1–3 snapshots có thời điểm rõ, kết hợp metric/trace và ghi giới hạn. Nếu cần monitoring nền, đo và đặt cadence phù hợp thay vì mặc định cứ 100 ms gọi detector.

### 12.1 Có nên tự động “giải deadlock”?

Deadlock detector **không sửa source code hay giải phóng lock**. Phương án như `Thread.stop()` bị deprecated và không an toàn; ép chết thread đang giữ lock có thể làm hỏng invariant/dữ liệu. Việc interrupt một thread bị `BLOCKED` khi chờ intrinsic monitor **không bảo đảm** thoát khỏi `synchronized`; `ReentrantLock.lockInterruptibly()` chỉ có cơ chế interrupt khi **code sử dụng API đó**.

Cách sửa bền vững thường là:

- Định nghĩa thứ tự acquire locks **nhất quán** trên mọi code path.
- Giảm nested locking và thời gian giữ lock; tránh I/O/blocking calls khi giữ lock.
- Dùng `try/finally` để release `ReentrantLock` đúng chỗ.
- Cân nhắc `tryLock(timeout, unit)` để có giới hạn chờ phù hợp và xử lý timeout an toàn.
- Thiết kế task/executor dependencies tránh starvation và circular joins.
- Test với concurrency stress, kiểm tra deadlock conditions trong integration tests.

### 12.2 Ví dụ thay đổi thứ tự lock

**Không an toàn — hai đường code đảo thứ tự**:

```text
Path A: acquire accountLock -> acquire ledgerLock
Path B: acquire ledgerLock  -> acquire accountLock
```

**An toàn hơn — quy tắc cùng thứ tự**:

```text
Path A: acquire accountLock -> acquire ledgerLock
Path B: acquire accountLock -> acquire ledgerLock
```

Việc thống nhất thứ tự loại bỏ chính **chu trình hai lock** minh họa này nếu không có code paths khác phá quy tắc. Tuy nhiên, không tự chứng minh hết mọi deadlock trong toàn hệ thống; còn các locks khác và dependencies bên ngoài.

## 13. Khi muốn kiểm tra từ JConsole, JMX hoặc jcmd

### 13.1 Local Java API và remote JMX

`ManagementFactory.getThreadMXBean()` đọc **JVM chạy code đó**. JConsole/JMX client kết nối tới ObjectName `java.lang:type=Threading` của **JVM đích** có thể truy cập operations hoặc attributes mà JMX expose theo quyền. Nhưng:

- Remote JMX phải cấu hình xác thực, TLS, network restrictions và role permissions.
- Không giả định mọi operation đều read-only hoặc rẻ; thread dump/deadlock detection có overhead.
- Nếu JVM đích không cho remote attach/JMX, không tự expose unauthenticated port để xem nhanh.
- Tên ObjectName giống nhau ở mọi process, nên **target endpoint/host/PID/start time** mới cho biết bạn đang xem instance nào.

### 13.2 So với jcmd và jstack

Trên HotSpot JDK 21, có thể dùng:

```bash
jcmd 12345 Thread.print -l
jstack -l 12345
```

**12345 là PID giả định**, không được copy lên host thật nếu chưa kiểm tra. Những lệnh này tạo **thread dump**, không giống việc gọi detector trả một mảng ID. Dump có thể chứa phần Java-level deadlock khi VM hỗ trợ, cùng monitors/ownable synchronizers và stacks hữu ích để tìm vị trí acquire.

- `jcmd Thread.print -l` thường được ưu tiên nếu HotSpot hỗ trợ và có tool cùng quyền attach.
- `jstack` JDK 21 được tài liệu man page đánh dấu experimental/unsupported; kiểm tra tool options của JDK đang chạy.
- Các text thread dumps truyền thống **không có nghĩa** liệt kê đầy đủ unmounted virtual threads.
- Nếu cần virtual threads, tham khảo `jcmd PID help Thread.dump_to_file` của JVM đích/JDK21 để xem có lệnh riêng và output JSON/text hay không.
- Lệnh `jcmd ... > file.txt` lưu file ở shell caller; `Thread.dump_to_file` viết file phía **JVM đích**.

Dù `findDeadlockedThreads()` trả `null`, vài snapshots thread dump và JFR có thể giúp tìm starvation/lock contention/virtual-thread blocking khác phạm vi detector.

## 14. Kịch bản điều tra production: từ không phản hồi đến bằng chứng

### Bước 1 — Xác định sự cố thật

Ghi incident window UTC, service, pod/instance, host, PID, start time, JVM build, GC/JDK, workload và tỷ lệ lỗi. “Request treo” không đủ phân loại deadlock ngay lập tức.

### Bước 2 — Kiểm tra capability

Lấy `ThreadMXBean` từ đúng JVM, kiểm tra `isSynchronizerUsageSupported()` và `isObjectMonitorUsageSupported()` để biết có thể thu lock details nào. Ghi trạng thái unsupported/permission error rõ ràng, không biến thành “false”.

### Bước 3 — Chạy detector phù hợp

Nếu chỉ nghi synchronized monitor cycle, `findMonitorDeadlockedThreads()` có thể là điểm bắt đầu. Nếu ứng dụng dùng `ReentrantLock`/ownable synchronizers và VM hỗ trợ, dùng `findDeadlockedThreads()` để có coverage rộng hơn. Cả hai đều có thể tốn chi phí nên tránh gọi quá dày.

### Bước 4 — Thu thông tin thread/lock chi tiết

Khi có IDs, lấy `ThreadInfo` với stack depth phù hợp, locked monitors/synchronizers nếu VM hỗ trợ. Ghi **thread name/ID, state, lockName, owner ID/name, top relevant stack frames**. Nếu output bị truncated, ghi rõ giới hạn.

### Bước 5 — Dựng wait-for graph và đối chiếu source

Dựng cạnh từ thread chờ đến thread sở hữu lock. Xác nhận vòng và đối chiếu code path đã acquire locks theo thứ tự nào. Source line phải thuộc **đúng JAR/build đang chạy**, không mở branch hiện tại rồi suy line number chưa chắc khớp.

### Bước 6 — Kiểm tra ngoài phạm vi

Nếu detector trả `null` nhưng application kẹt: kiểm tra **virtual threads**, pool starvation, network/DB waits, distributed locks, native locks và livelocks. Dùng JFR, OS metrics, tracing, thread dumps và DB diagnostics theo câu hỏi.

### Bước 7 — Sửa thiết kế và kiểm thử

Viết lại lock ordering/timeout/scope, thêm concurrency regression test, benchmark contention/throughput và quan sát sau rollout. Không dùng kill/`Thread.stop()` như giải pháp dài hạn cho deadlock đã được tìm thấy.

Một mẫu báo cáo **giả định**:

```yaml
captureTimeUtc: "2026-10-29T09:10:00Z"
service: "inventory-api"
instance: "inventory-2"
pid: 12345
processStartUtc: "2026-10-29T08:10:00Z"
javaVersion: "21.0.x"
detector: "ThreadMXBean.findDeadlockedThreads"
scope: "platform_threads, monitors_and_ownable_synchronizers"
capabilities:
  ownableSynchronizerUsage: true
result: "found"
threadCount: 2
cycle:
  - "worker-A waits for worker-B"
  - "worker-B waits for worker-A"
evidence: "ThreadInfo stack and lockOwnerId captured separately"
limitations:
  - "Virtual-thread cycles outside ThreadMXBean scope"
  - "Snapshots are not atomic across API calls"
```

Các tên, thời điểm và ID trên **chỉ minh họa cấu trúc**, không phải một case thực tế. Khi báo cáo incident, thay bằng dữ liệu đọc được; không điền `result=found` nếu detector chưa chạy thành công.

## 15. Lỗi phổ biến cần tránh

| Nhầm lẫn | Diễn giải đúng |
| --- | --- |
| “Hai API tên gần giống nhau nên thay thế nhau.” | `findMonitorDeadlockedThreads` chỉ monitors; `findDeadlockedThreads` còn ownable synchronizers. |
| “ReentrantLock deadlock luôn ở trạng thái BLOCKED.” | Thường có `WAITING (parking)`; `BLOCKED` đặc trưng cho monitor entry. |
| “`findMonitorDeadlockedThreads() == null` nghĩa toàn bộ app không deadlock.” | Không tìm thấy **monitor-only platform cycles** tại thời điểm đo. |
| “`findDeadlockedThreads()` bao phủ mọi `java.util.concurrent`.” | Chỉ ownable synchronizers phù hợp contract, không phải mọi semaphore/queue/read-lock/external wait. |
| “Mảng ID null tương đương UnsupportedOperationException.” | Null = không phát hiện; exception = detector không thể thực hiện đầy đủ. |
| “Các API tự trả source line và root cause.” | Chỉ trả IDs; cần `ThreadInfo`/stacks/lock owner và source mapping. |
| “ThreadMXBean đếm tất cả virtual threads Java 21.” | Chỉ platform threads trong Java 21; cycles có virtual threads không được phát hiện. |
| “Nếu threadInfo null thì deadlock đã biến mất.” | Có thể thread đã thoát, không tồn tại hoặc là virtual thread ID; có race. |
| “Dùng isSynchronizerUsageSupported là bật tính năng ownable monitoring.” | Đó là **capability query**, không phải setter; không thay đổi state. |
| “Cứ có một thread BLOCKED là deadlock.” | Có thể contention tạm thời; phải tồn tại ownership cycle. |
| “No Java monitor deadlock nghĩa DB không có deadlock.” | DB/distributed/native resource locks ngoài phạm vi này. |
| “Deadlock detection là phương pháp đảm bảo thread scheduler không bao giờ treo.” | Chỉ là diagnostic snapshot thuộc loại lock cụ thể; không dùng để synchronization control. |
| “Nên kiểm tra mỗi request để phòng deadlock.” | Có thể tốn chi phí; dùng lock ordering/timeouts/test và diagnostics có mục tiêu. |
| “Có thể giải deadlock bằng Thread.stop().” | Deprecated và không an toàn, dễ phá invariant; sửa code/điều phối khôi phục an toàn. |
| “Thread ID giống nhau trên hai pods nghĩa cùng thread.” | IDs có phạm vi JVM/lifetime, có thể tái sử dụng. |
| “Thread dump luôn liệt kê mọi virtual threads.” | Truyền thống thường tập trung platform threads; chọn nguồn hỗ trợ virtual threads. |

## 16. Tự kiểm tra và đáp án

**1.** Hai platform threads giữ hai `synchronized` monitors theo thứ tự ngược. Phương thức nào có khả năng phát hiện?

**Đáp án:** `findMonitorDeadlockedThreads()`; nếu VM hỗ trợ ownable synchronizer usage, `findDeadlockedThreads()` cũng bao phủ monitor cycles.

**2.** Hai platform threads deadlock trên hai `ReentrantLock`. `findMonitorDeadlockedThreads()` trả `null` có phải kết luận không deadlock?

**Đáp án:** không. Detector chỉ monitor không bao phủ ReentrantLock cycle. Dùng `findDeadlockedThreads()` nếu VM hỗ trợ.

**3.** JVM không hỗ trợ ownable synchronizer monitoring và `findDeadlockedThreads()` ném `UnsupportedOperationException`. Dashboard nên xuất `deadlockDetected=false`?

**Đáp án:** không. Ghi `check_status=unsupported` và `result=unknown`; có thể dùng detector monitor-only riêng, nhưng vẫn thiếu ownable coverage.

**4.** `findDeadlockedThreads()` trả một `long[]` với hai phần tử. Đó là hai PID hoặc hai native TID?

**Đáp án:** không. Đó là **Java thread IDs trong JVM hiện tại**; dùng `getThreadInfo` để đọc tên/state/owners/stacks.

**5.** Lỗi ở DB khiến request threads chờ 30 giây nhưng hai detectors trả `null`. Có mâu thuẫn không?

**Đáp án:** không. DB lock và remote wait có thể ngoài phạm vi monitor/ownable wait-for cycles của Java platform threads.

**6.** Java 21 có 10.000 virtual threads đang chờ; `getThreadCount()` báo 40. Có nghĩa chỉ 40 threads còn sống?

**Đáp án:** không. Bean đếm **platform threads**, không bao gồm virtual threads theo Java 21 contract.

**7.** Một virtual thread đang còn sống, gọi `getThreadInfo(virtual.threadId())` trong Java 21 thì sao?

**Đáp án:** trả `null` theo contract, không chứng minh virtual thread đã kết thúc.

**8.** Vì sao nên đọc `isSynchronizerUsageSupported()` trước `findDeadlockedThreads()`?

**Đáp án:** để biết VM có hỗ trợ ownable synchronizer usage; nếu không, method có thể ném `UnsupportedOperationException`. Đồng thời nên xử lý exceptions từ quyền truy cập.

**9.** Vì sao lab dùng `CountDownLatch(2)` trước khi hai threads đòi lock thứ hai?

**Đáp án:** để bảo đảm cả hai **đã sở hữu lock đầu tiên**, tránh race khiến một thread lấy cả hai locks rồi nhả trước khi thread kia tham gia.

**10.** Tại sao `findMonitorDeadlockedThreads()` không được gọi mỗi mili-giây trong request handler?

**Đáp án:** là diagnostic có thể đắt, không phải primitive điều khiển đồng bộ; phải dùng khóa đúng thiết kế, timeout/metrics và chẩn đoán theo mục tiêu.

**11.** Nhìn thấy hai threads `BLOCKED` cùng lock, đã đủ nói có deadlock?

**Đáp án:** chưa. Phải có vòng chờ ownership. Một thread giữ lock rồi nhả là contention, không phải chu trình.

**12.** Một cycle gồm platform thread và virtual thread. Detector Java 21 bảo đảm tìm thấy không?

**Đáp án:** không. Tài liệu chỉ bảo đảm tìm cycles gồm platform threads; chu trình có virtual threads không được hai APIs này tìm thấy.

## 17. Checklist thực hành

- Nhớ **`findMonitorDeadlockedThreads` = object monitors**, **`findDeadlockedThreads` = monitors + ownable synchronizers**.
- Cả hai nhắm **platform threads** ở Java 21; virtual-thread cycles ngoài phạm vi.
- **`null`** = không tìm thấy cycle thuộc scope/timestamp, không phải “healthy”.
- `findDeadlockedThreads()` có thể **`UnsupportedOperationException`**; check `isSynchronizerUsageSupported()`.
- Dùng `getThreadInfo(ids, lockedMonitors, lockedSynchronizers, maxDepth)` để lấy owner/lock/stack; xử lý các `null` trong kết quả.
- Thread IDs không phải OS PID/TID, không dùng xuyên JVM/restart.
- Deadlock lock ownership khác contention, starvation, livelock, DB/distributed/native lock.
- Chạy lab `DeadlockMxBeanLab` Java 17+ ở **hai process riêng** cho `monitor` và `ownable`.
- Chạy lab Java 21+ `VirtualThreadMxBeanScopeLab` để thấy `getThreadInfo(virtualId) == null` ngay cả khi virtual thread còn sống.
- Ghi timestamp, service/instance/PID/start time, capability, scope, kết quả và giới hạn.
- Không dùng detector làm **synchronization control**, không lặp dày và không tự release locks bằng thao tác nguy hiểm.
- Sửa bền vững bằng **lock ordering thống nhất**, giảm phạm vi giữ khóa, xử lý timeout và concurrency regression tests.

**Kết luận:** hai phương thức deadlock detection của `ThreadMXBean` rất hữu ích khi có platform threads chờ object monitors và ownable synchronizers. Tuy nhiên, chúng **không tương đương về coverage**, có giới hạn quyền/hỗ trợ/chi phí và đặc biệt **không giám sát virtual threads** ở JDK 21. Kết quả đáng tin cần kết hợp IDs với `ThreadInfo`, lock owner graph, stack frames và đúng incident context; `null` chỉ là “không phát hiện trong phạm vi API”, không phải xác nhận ứng dụng không có vấn đề treo.

### Tài liệu tham khảo chính thức

- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): phạm vi platform threads, hai phương thức detection, `isSynchronizerUsageSupported`, `getThreadInfo` và các ngoại lệ.
- [Java SE 21 — ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html): owner ID/name, lockName, state, stack frames, locked monitors và ownable synchronizers.
- [Java SE 21 — LockInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/LockInfo.html): định nghĩa object monitor/ownable synchronizer và ví dụ ReentrantLock/write-lock.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): cách lấy ThreadMXBean của JVM.
- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual threads, thread dump riêng và JFR events.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print`, diagnostic command support/impact.
