# findDeadlockedThreads và phát hiện vòng chờ trong Java

## 1. Khi ứng dụng Java “đứng yên”: deadlock hay chỉ đang đợi?

Một ứng dụng có thể ngừng phản hồi dù CPU không cao, request không hoàn tất và các worker threads vẫn tồn tại. Nhưng **mọi thread ở trạng thái WAITING hoặc BLOCKED không mặc nhiên bị deadlock**: chúng có thể đang chờ một lock hợp lệ, chờ tín hiệu từ queue, chờ database hoặc chờ công việc khác kết thúc.

**Deadlock (vòng chờ khóa)** xảy ra khi các threads nằm trong một **chu trình phụ thuộc sở hữu khóa**: A chờ khóa do B nắm, B lại chờ khóa do A nắm (hoặc một chu trình dài hơn). Không thread nào trong chu trình tự tiến lên để giải phóng khóa đang giữ.

Trong Java, API chẩn đoán hiện hành:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
long[] deadlockedIds = bean.findDeadlockedThreads();
~~~

Đoạn trên là snippet (cần import `java.lang.management.ThreadMXBean` và `ManagementFactory`). `deadlockedIds` chứa IDs của các **platform threads** bị deadlock trên **object monitors** hoặc **ownable synchronizers**, hoặc **null** nếu không phát hiện chu trình tương ứng. Đây là công cụ phục vụ **diagnostics**, không phải hàm sửa deadlock hay thay thế thiết kế lock đúng.

Bài này tập trung vào `ThreadMXBean.findDeadlockedThreads()` trong ngữ cảnh chủ đề **Theo dõi luồng**, kèm cách chứng minh vòng chờ bằng `ThreadInfo.getLockOwnerId()`, cách phân biệt với `findMonitorDeadlockedThreads()`, giới hạn trên virtual threads và ví dụ Java 21+ chạy thực tế.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **monitor deadlock**, **ownable synchronizer deadlock**, contention thông thường và những hiện tượng “treo” khác.
2. Gọi `ManagementFactory.getThreadMXBean()` và dùng đúng `findDeadlockedThreads()`.
3. Kiểm tra `isSynchronizerUsageSupported()` trước khi dùng API phụ thuộc khả năng JVM.
4. Hiểu rõ `null` khi **không tìm thấy chu trình**, và `UnsupportedOperationException` nếu khả năng giám sát synchronizer không được hỗ trợ.
5. Lấy `ThreadInfo[]` bằng `getThreadInfo(ids, lockedMonitors, lockedSynchronizers)` để xem tên thread, trạng thái, khóa đang chờ, owner ID, stacks và các khóa đang giữ.
6. Vẽ **wait-for graph** và chứng minh A → B → A.
7. Tránh kết luận sai chỉ dựa vào `BLOCKED` hoặc `WAITING`.
8. Biết giới hạn: API quản lý platform threads, **không phát hiện các chu trình có virtual threads**, cũng không giải quyết mọi kiểu phụ thuộc ở application layer.
9. Tạo báo cáo chẩn đoán nhỏ, giới hạn thông tin nhạy cảm, không tự mở JMX remote port.
10. Phòng ngừa bằng thứ tự khóa thống nhất, tránh nested locks dài, và các primitive có khả năng timeout/cancellation khi thích hợp.

**Special Note:** Chỉ kiến thức vẫn hiện hành. Bài dùng `Thread.threadId()` và `Thread.ofPlatform()` trên **Java 21+** thay cho `Thread.getId()` (đã deprecated từ Java 19), dù những API `ThreadMXBean` cốt lõi cũng có từ các bản Java cũ và vẫn được Java 17/26 hỗ trợ.

## 2. Mô hình wait-for graph: cạnh nào tạo thành deadlock?

Hãy đặt mỗi **thread** là một đỉnh. Khi A đang chờ **lock do B sở hữu**, vẽ cạnh có hướng A → B:

~~~text
Thread A --waits for lock held by--> Thread B
Thread B --waits for lock held by--> Thread A

Equivalent wait-for graph:

    A ----> B
    ^       |
    |       v
    +-------+
~~~

Khi có một chu trình khép kín, ta có **vòng chờ ownership**. Trong ví dụ:

- A giữ lock L1, yêu cầu lock L2.
- B giữ lock L2, yêu cầu lock L1.
- A không thể lấy L2 trước khi B thả nó; B không thể lấy L1 trước khi A thả nó.

Với ba threads:

~~~text
A owns L1; waits L2 (owned by B)
B owns L2; waits L3 (owned by C)
C owns L3; waits L1 (owned by A)

A -> B -> C -> A
~~~

Không nhất thiết deadlock chỉ có 2 threads. `findDeadlockedThreads()` có thể trả về IDs của nhiều threads thuộc một hoặc nhiều cycles.

### 2.1. Chờ mà không có chu trình

~~~text
Thread Owner owns L
Thread Contender wants L

Contender -> Owner
Owner -> (not waiting for a lock held by Contender)
~~~

Ở đây Contender có thể mang state `BLOCKED`, nhưng nếu Owner tiếp tục làm việc và thả L thì Contender tiến lên. **Không có vòng**, nên không phải deadlock theo quan hệ sở hữu khóa. Ví dụ thứ hai trong bài chứng minh trực tiếp hiện tượng này.

### 2.2. Điều kiện cần và ngoại lệ thực tế

Những điều kiện thường dẫn tới deadlock gồm mutual exclusion, hold-and-wait, no preemption và circular wait. Trong Java, `synchronized` có cơ chế monitor exclusivity; những code giữ một lock trong khi chờ lock khác có thể tạo chu trình. `ReentrantLock` cũng có khả năng xảy ra tương tự nếu lấy nhiều khóa không theo thứ tự cố định.

Tuy nhiên, **không thể suy luận ngược** rằng một ứng dụng không trả response trong 30 giây thì bắt buộc có deadlock. Có thể đó là network timeout, retry storm, thread pool starvation, GC pause, livelock, hung native I/O, blocking database transaction hoặc `CountDownLatch.await()` không được đếm xuống. `findDeadlockedThreads()==null` chỉ nói **không phát hiện được chu trình thuộc phạm vi API tại thời điểm kiểm tra**.

## 3. Hai nhóm khóa được `findDeadlockedThreads` hỗ trợ

| Loại | Ví dụ | Thread state thường quan sát | Có thể được `findDeadlockedThreads` nhận ra? |
| --- | --- | --- | --- |
| **Object monitor** | `synchronized(lock)`, chờ monitor entry | `BLOCKED` | Có |
| **Ownable synchronizer** | `ReentrantLock.lock()` | Thường `WAITING` hoặc trạng thái khác tùy điểm dừng | Có, khi JVM hỗ trợ giám sát ownable synchronizers |
| CountDownLatch | `await()` | `WAITING`/`TIMED_WAITING` | Không tự thành cạnh ownership được API phát hiện |
| Semaphore | `acquire()` | `WAITING` | Không đảm bảo được phát hiện như ownable lock |
| Condition | `condition.await()` | `WAITING` | Không tự tạo ownership edge cho một cycle |
| CompletableFuture | `join()` | `WAITING` | Không có JMX lock-owner graph chung |
| I/O/database/external service | Network/read/transaction wait | Phụ thuộc thời điểm/runtime | Không thuộc cam kết nhận diện monitor/ownable synchronizer cycles |
| Virtual thread | Có thể mắc kẹt khi chờ locks/resources | Phụ thuộc runtime | **Không được ThreadMXBean này giám sát** |

`java.util.concurrent.locks.AbstractOwnableSynchronizer` là abstraction ghi nhận **exclusive owner** của một synchronizer. `ReentrantLock` là ví dụ quan trọng. Không phải mọi loại synchronization primitive đều có ownership semantics mà JMX detector quan sát được; đặc biệt không suy ra mọi lời gọi `LockSupport.park()` đều có lock owner rõ ràng.

### 3.1. Vòng chờ monitor với `synchronized`

~~~java
Object left = new Object();
Object right = new Object();

// Thread A
synchronized (left) {
    synchronized (right) {
        // Work.
    }
}

// Thread B
synchronized (right) {
    synchronized (left) {
        // Work.
    }
}
~~~

Đây là **snippet minh họa rủi ro**, không phải hai methods độc lập hoàn chỉnh. Nếu Thread A đã giữ `left` và B đã giữ `right` rồi cùng yêu cầu khóa còn lại, sẽ tạo vòng A → B → A. Nhưng điều đó **không chắc xảy ra trong mọi lần chạy** nếu lịch thực thi cho phép một thread lấy cả hai khóa trước. Ví dụ chạy đầy đủ ở mục 10 dùng `CountDownLatch` để ép một tình huống có thể quan sát ổn định.

### 3.2. Vòng chờ `ReentrantLock`

~~~java
ReentrantLock left = new ReentrantLock();
ReentrantLock right = new ReentrantLock();

// Thread A: left.lock(), sau đó right.lock().
// Thread B: right.lock(), sau đó left.lock().
~~~

Đây là snippet khái niệm. Khi A và B giữ khóa đầu tiên và yêu cầu khóa thứ hai, chúng có thể deadlock dù không thread nào mang `Thread.State.BLOCKED`. `ReentrantLock.lock()` thường đợi bằng cơ chế park và có thể hiện `WAITING`. Do đó chỉ tìm những threads đang `BLOCKED` là **không đủ**.

### 3.3. “Ownable synchronizer” không đồng nghĩa mọi lock

Một thread đợi token từ `Semaphore` hoặc tín hiệu từ `CountDownLatch` có thể bị chặn vô hạn, nhưng không có một **thread owner của lock** được biểu diễn giống `ReentrantLock` để `getLockOwnerId()` tạo wait-for edge. Với các dạng liveness failure như vậy, phải xem ứng dụng/queue/cancellation, thread dumps, dependency graphs hoặc công cụ quan sát chuyên dụng khác.

## 4. API trung tâm: `ThreadMXBean.findDeadlockedThreads()`

Chữ ký JDK:

~~~java
long[] findDeadlockedThreads()
~~~

JavaDoc hiện hành quy định phương thức tìm **cycles of platform threads** đang đợi sở hữu một `object monitor` hoặc `ownable synchronizer`.

**Kết quả:**

- `long[]`: IDs của những platform threads nằm trong các cycles được phát hiện.
- `null`: **không có** deadlocked platform threads theo detector lúc gọi.
- `UnsupportedOperationException`: JVM **không hỗ trợ giám sát ownable synchronizer usage**.
- Là hoạt động **diagnostic có thể tốn chi phí**; không gọi vô hạn trong mọi request.

### 4.1. Gọi an toàn có fallback

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

long[] ids;
if (bean.isSynchronizerUsageSupported()) {
    ids = bean.findDeadlockedThreads();
} else {
    ids = bean.findMonitorDeadlockedThreads();
}
~~~

Đây là snippet trong method có quyền truy cập JVM metrics. Khi không hỗ trợ ownable synchronizer usage, fallback chỉ phát hiện **monitor cycles**; không nên báo kết luận “không có bất kỳ deadlock nào” nếu fallback trả `null`.

### 4.2. Không nhầm `null` với mảng rỗng

~~~java
if (ids == null || ids.length == 0) {
    System.out.println("No supported lock cycle detected");
}
~~~

JavaDoc chuẩn mô tả `null` nếu không có deadlocked threads. Việc cũng chấp nhận mảng rỗng làm code phòng thủ hơn khi xây tầng adapter/tooling. **Không** lặp trên `ids.length` trước khi null-check.

Không dựa vào **thứ tự ID** trong mảng trả về để suy luận thứ tự các cạnh; dùng `ThreadInfo.getLockOwnerId()` mới biết owner relation. Một lần detector có thể trả nhiều cycles; cần group nếu muốn báo thành các nhóm.

### 4.3. Vì sao detector không sửa deadlock?

Một deadlock trên monitor hoặc `ReentrantLock.lock()` thông thường **không có một lời gọi JMX nào “unlock từ ngoài” một cách an toàn**. JVM chỉ đang báo các platform thread IDs và lock graph.

Không dùng `Thread.stop()`, `Thread.suspend()` hay forced release/`Unsafe` để “cứu” chương trình: những kỹ thuật dừng cưỡng bức/lỗi thời có thể phá invariants và để dữ liệu không nhất quán. Hành động vận hành có thể là thu thập bằng chứng, giảm traffic, khởi động lại có kiểm soát hoặc khôi phục trạng thái qua cơ chế transaction/idempotency do hệ thống định nghĩa.

## 5. So sánh `findDeadlockedThreads` và `findMonitorDeadlockedThreads`

| Tiêu chí | `findDeadlockedThreads()` | `findMonitorDeadlockedThreads()` |
| --- | --- | --- |
| Object monitors (`synchronized`) | Có | Có |
| Ownable synchronizers (`ReentrantLock`) | Có nếu được hỗ trợ | **Không** |
| Quan sát virtual threads | Không | Không |
| Trả kết quả | IDs hoặc null | IDs hoặc null |
| Cần `isSynchronizerUsageSupported()` | Có để biết có thể gọi | Không cần cho riêng monitor detection |
| Khi có unsupported synchronizer monitoring | Có thể ném `UnsupportedOperationException` | Vẫn có thể dùng để tìm monitor cycles |
| Mục đích | Phát hiện rộng hơn các lock-owner cycles | Phát hiện riêng monitor cycles |
| Sửa lock tự động | Không | Không |

`findMonitorDeadlockedThreads` **không deprecated** và vẫn hiện hành; nó hữu ích khi runtime không hỗ trợ ownable synchronizer monitoring hoặc bạn muốn phân loại chính xác monitor-only cycle. Trong demo, monitor detector trả IDs của hai threads dùng `synchronized` nhưng **không** trả cặp dùng `ReentrantLock`, còn general detector thấy cả hai cặp.

### 5.1. Kiểm tra khả năng JVM trước khi yêu cầu lock details

~~~java
boolean monitorDetails = bean.isObjectMonitorUsageSupported();
boolean synchronizerDetails = bean.isSynchronizerUsageSupported();

ThreadInfo[] details = bean.getThreadInfo(
        ids, monitorDetails, synchronizerDetails);
~~~

Hai flags này ảnh hưởng việc `getThreadInfo` lấy **danh sách các khóa đang sở hữu**. Nếu truyền `true` cho một loại unsupported, JVM có thể ném `UnsupportedOperationException`. Đừng nhầm `isObjectMonitorUsageSupported()` với câu trả lời “có deadlock hay không”; nó chỉ cho biết runtime có thể cung cấp chi tiết giám sát monitor usage.

## 6. ThreadInfo: từ ID đến bằng chứng vòng chờ

`ThreadMXBean` trả IDs, chưa đủ để biết vì sao ứng dụng bị treo. `ThreadInfo` mô tả trạng thái/các khóa tại một snapshot.

~~~java
ThreadInfo[] infos =
        bean.getThreadInfo(ids, true, true);
~~~

Đây là snippet chỉ an toàn nếu JVM hỗ trợ **cả** object monitor và ownable synchronizer usage; ở nơi khác dùng flags từ `isObjectMonitorUsageSupported()` và `isSynchronizerUsageSupported()` như mục trên.

| Method `ThreadInfo` | Trả về | Cách dùng |
| --- | --- | --- |
| `getThreadId()` | `long` | Định danh thread trong snapshot |
| `getThreadName()` | `String` | Tên thread dùng cho báo cáo |
| `getThreadState()` | `Thread.State` | `BLOCKED`, `WAITING`, ... |
| `getLockInfo()` | `LockInfo` hoặc null | Khóa thread đang đợi |
| `getLockName()` | Chuỗi biểu diễn khóa nếu có | Phục vụ chẩn đoán |
| `getLockOwnerId()` | ID owner hoặc -1 | **Cạnh A → B** trong wait-for graph |
| `getLockOwnerName()` | Tên owner nếu có | Dễ đọc hơn ID |
| `getStackTrace()` | `StackTraceElement[]` | Vị trí code đang chờ |
| `getLockedMonitors()` | `MonitorInfo[]` | Object monitors đang sở hữu, khi được yêu cầu |
| `getLockedSynchronizers()` | `LockInfo[]` | Ownable synchronizers đang sở hữu, khi được yêu cầu |

**Quan trọng:** `getLockOwnerId()==-1` nghĩa là không xác định được owner của lock được chờ hoặc không có owner; không được tự tạo cạnh A → B từ tên khóa hay stack trace. `getLockInfo()` có thể null nếu thread không ở điểm chờ lock liên quan. `ThreadInfo` là snapshot: thread có thể kết thúc hoặc đổi state giữa detector và lần gọi `getThreadInfo`; với IDs không còn sống, entry có thể là `null`.

### 6.1. Chứng minh một cycle từ các edges

Với cặp deadlock:

~~~text
ThreadInfo A: threadId=101, lockOwnerId=102, waitingFor=L2
ThreadInfo B: threadId=102, lockOwnerId=101, waitingFor=L1
~~~

Đây là **số ID minh họa**, không phải output cố định. Từ đây:

~~~text
101 -> 102 -> 101
~~~

là một chu trình. Thông tin state `BLOCKED`/`WAITING` giúp hiểu kiểu khóa, nhưng yếu tố quyết định là **edges sở hữu**.

### 6.2. Phân biệt locked và waiting-on locks

Một thread có thể:

- **Own** nhiều monitors/synchronizers, được ghi trong `getLockedMonitors()`/`getLockedSynchronizers()`.
- **Wait** để lấy một lock khác, được ghi trong `getLockInfo()`.
- Có `getLockOwnerId()` trỏ tới thread **sở hữu** lock đang đợi.

Đừng lập đồ thị dựa trên `lockedMonitors` của một thread rồi cho rằng mọi thread cùng thấy monitor object đều đang chờ nhau. Cần nối **waiter → owner**.

### 6.3. Bounded stack trace và bảo vệ dữ liệu

Để xem stack frames:

~~~java
StackTraceElement[] frames = info.getStackTrace();
for (int n = 0; n < Math.min(frames.length, 5); n++) {
    System.out.println("  at " + frames[n]);
}
~~~

`info` là `ThreadInfo` đã lấy. Trên production, thread names/stacks có thể chứa tên tenant, đường dẫn nội bộ, cấu trúc code hay thông tin nghiệp vụ. Chỉ xuất về hệ thống logs/monitoring được cấp quyền, giới hạn số frames và retention.

### 6.4. `ThreadInfo.getThreadId()` khác `Thread.getId()`

`ThreadInfo.getThreadId()` vẫn là **API được hỗ trợ** để lấy ID trong snapshot. Ngược lại, `Thread.getId()` đã **deprecated từ Java 19**; code ví dụ Java 21+ dùng `Thread.threadId()` (final, từ Java 19). Nhờ đó code minh họa không dựa trên API được khuyến nghị thay thế.

## 7. Giới hạn quan trọng trong Java 21–26: virtual threads

Java 21 đưa virtual threads thành tính năng chính thức. **ThreadMXBean không hỗ trợ quản lý/giám sát virtual threads** theo Java SE 26 JavaDoc; `findDeadlockedThreads()` và `findMonitorDeadlockedThreads()` chỉ phát hiện cycles **toàn bộ nằm trong nhóm platform threads**. **Chu trình có virtual thread không được những methods này tìm ra.**

Điều đó có nghĩa:

- `findDeadlockedThreads()==null` **không thể** chứng minh ứng dụng dùng virtual threads không có deadlock.
- `getAllThreadIds()`/`getThreadInfo(id)` của ThreadMXBean không bao gồm virtual threads.
- Một virtual thread đang chờ khóa do platform thread nắm, và platform thread chờ một điều kiện phụ thuộc virtual thread, có thể tạo liveness failure **ngoài khả năng phát hiện tự động** của API này.
- Dùng các công cụ thread dumps và observability khác để điều tra, đặc biệt với virtual-thread-heavy workloads.

### 7.1. `jcmd Thread.dump_to_file` có thể hỗ trợ xem virtual threads

Tài liệu Oracle Java SE 26 mô tả `jcmd` thread dump file bao gồm **platform và virtual threads**. Với một PID được quyền quản lý:

~~~sh
jcmd <pid> Thread.dump_to_file -format=json <secure-diagnostic-file>
~~~

Đây là **cú pháp minh họa**; `<pid>` và `<secure-diagnostic-file>` là placeholders do người vận hành chọn. Cần JDK tool, process permissions phù hợp và nơi lưu file được bảo vệ.

**Đừng nhầm:** thread dump của `Thread.dump_to_file` **không tự chạy thuật toán deadlock detection**, dù nó cung cấp thông tin thread/lock để phân tích. Nó cũng **không phải snapshot nhất quán tuyệt đối**: threads có thể thay đổi trong lúc dump. Không tuyên bố chỉ một file dump là đủ chứng minh chắc chắn mọi liveness issue.

### 7.2. `jcmd Thread.print -l` khác gì?

JDK cung cấp:

~~~sh
jcmd <pid> Thread.print -l
~~~

Lệnh này báo các platform threads và mounted virtual threads cùng thông tin synchronization tùy options/JDK. Với virtual threads, hướng dẫn Oracle khuyến nghị `Thread.dump_to_file` để xem rộng hơn. Không chủ động chạy jcmd trong demo vì đó là thao tác ngoài tiến trình và có thể truy cập thông tin hệ thống nhạy cảm; bài chỉ hướng dẫn cú pháp cho môi trường được phép.

## 8. Những điều `findDeadlockedThreads` không kết luận được

| Hiện tượng | Detector có thể trả null? | Hướng điều tra khác |
| --- | --- | --- |
| Deadlock platform threads trên intrinsic monitors | Thường phải tìm thấy nếu cycle đang tồn tại và VM hỗ trợ | ThreadInfo owner graph |
| Deadlock platform threads trên ReentrantLock | Phát hiện khi ownable monitoring được hỗ trợ | ThreadInfo/getLockedSynchronizers |
| Một thread bị BLOCKED chờ lock sẽ được thả | Có, vì không có chu trình | Kiểm owner graph, tiến triển |
| Threads WAITING trên CountDownLatch không bao giờ countDown | Có | Latch lifecycle, thread dump, app-level dependencies |
| Thread pool starvation do task chờ task khác trong cùng pool | Có | Executor queue, active counts, task graph |
| Futures chờ theo chu trình ở tầng ứng dụng | Có | Dependency graph của CompletableFuture/task orchestration |
| Semaphore permits bị leak | Có | Semaphore/queue instrumentation |
| Remote DB transaction deadlock | Có | DB deadlock reports, transaction/lock views |
| I/O chờ mãi không timeout | Có | Network/file timeouts và thread traces |
| Livelock, bận CPU nhưng không tiến triển | Có | CPU profiling, progress counters |
| Vòng gồm một virtual thread | **Không phát hiện** theo ThreadMXBean | Virtual-thread dump, application-level analysis |
| App đã chết/không liên lạc được với JVM | Không thể gọi | Crash logs/OS/JVM tools |

Một số cơ chế khác cũng tạo `WAITING` hoặc `TIMED_WAITING` nhưng không có cạnh owner tương ứng. API này nhằm phát hiện **lock ownership cycles**, không phải công cụ tổng quát nhận diện mọi lý do ngừng tiến triển.

## 9. Chọn Java 21+ cho bài chạy thử

Hai API dùng trong source hoàn chỉnh:

- `Thread.threadId()` — có từ Java 19, thay cho `Thread.getId()` deprecated.
- `Thread.ofPlatform().daemon().name(...).unstarted(...)` — tạo **platform thread** hiện hành, phân biệt rõ với virtual thread, dùng được trên Java 21+.

`ThreadMXBean.findDeadlockedThreads()` vốn đã có từ Java 6 và vẫn được hỗ trợ; các ví dụ chọn Java 21+ **để tránh API deprecated** và minh họa chính xác platform thread semantics thời hiện tại. Nếu phải duy trì source compatibility Java 17, cần thay riêng phần tạo thread/đọc ID theo API bản đó; không sao chép `Thread.threadId()` vào `javac --release 17` vì Java 17 chưa có method này.

Lệnh compile ở đây sử dụng:

~~~sh
javac --release 21 DeadlockCycleDemo.java
java DeadlockCycleDemo
~~~

Đây là **bài tạo deadlock có chủ ý**; chỉ chạy trong JVM thử nghiệm riêng. Source dùng **daemon platform threads** để tiến trình vẫn thoát sau khi in kết quả. Không đưa phần tạo deadlock vào service thật.

## 10. Chương trình #1: tái hiện monitor cycle và ReentrantLock cycle

### 10.1. Thiết kế kiểm thử không dựa vào may rủi của scheduler

Chương trình `DeadlockCycleDemo.java` thực hiện:

1. Tạo cặp `monitor-A` và `monitor-B`: mỗi thread giữ monitor khác nhau.
2. Dùng `CountDownLatch monitorHeld` để bảo đảm **cả hai đã giữ khóa thứ nhất**.
3. Chỉ sau đó mở `monitorGo` để cả hai yêu cầu monitor thứ hai → cycle.
4. Poll `findMonitorDeadlockedThreads()` có deadline hữu hạn, xác nhận thấy **cặp IDs cụ thể**, không dựa vào số lượng threads của cả JVM.
5. Kiểm `isSynchronizerUsageSupported()`; nếu false, giải thích không thể test ownable-synchronizer detection.
6. Tạo cặp `reentrant-A` và `reentrant-B` với hai `ReentrantLock` và latch tương tự.
7. Poll `findDeadlockedThreads()` xác nhận đủ **bốn IDs** của hai cycles.
8. Kiểm `findMonitorDeadlockedThreads()` không ghi nhận cặp ReentrantLock-only.
9. Lấy `getThreadInfo(ids, monitorSupported, synchronizerSupported)`, đối chiếu `getLockOwnerId()` thành **hai vòng 2 cạnh**.
10. Kiểm monitor pair `BLOCKED`, lock pair `WAITING` trên JVM thử nghiệm.
11. Xem locked monitors/synchronizers khi JVM hỗ trợ.
12. Chỉ tạo **daemon platform threads**, nên app thử nghiệm có thể thoát dù chúng bị deadlock.

**Lưu ý về ổn định:** Các thread states `BLOCKED`/`WAITING` là kết quả đã quan sát với HotSpot/JDK24 trong test; khi xây monitoring dùng `getLockOwnerId` và detector thay vì chỉ tin tên thread state. Polling có timeout để chương trình không treo vô hạn nếu JVM không hoàn tất bước setup.

### 10.2. Mã đầy đủ `DeadlockCycleDemo.java`

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class DeadlockCycleDemo {
    private static void check(boolean ok, String detail) {
        if (!ok) throw new AssertionError(detail);
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out at setup gate");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted setup", ex);
        }
    }

    private static Thread monitorWorker(
            String name, Object first, Object second,
            CountDownLatch held, CountDownLatch go) {
        Thread thread = Thread.ofPlatform().daemon().name(name)
                .unstarted(() -> {
                    synchronized (first) {
                        held.countDown();
                        await(go);
                        synchronized (second) {
                            throw new AssertionError("unreachable");
                        }
                    }
                });
        thread.start();
        return thread;
    }

    private static Thread lockWorker(
            String name, ReentrantLock first, ReentrantLock second,
            CountDownLatch held, CountDownLatch go) {
        Thread thread = Thread.ofPlatform().daemon().name(name)
                .unstarted(() -> {
                    first.lock();
                    try {
                        held.countDown();
                        await(go);
                        second.lock();
                        try {
                            throw new AssertionError("unreachable");
                        } finally {
                            second.unlock();
                        }
                    } finally {
                        first.unlock();
                    }
                });
        thread.start();
        return thread;
    }

    private static boolean containsAll(long[] ids, long... targets) {
        if (ids == null) return false;
        for (long target : targets) {
            if (Arrays.stream(ids).noneMatch(id -> id == target)) {
                return false;
            }
        }
        return true;
    }

    private static long[] awaitDetected(
            ThreadMXBean bean, boolean onlyMonitors, long... targets)
            throws Exception {
        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(5);
        do {
            long[] found = onlyMonitors
                    ? bean.findMonitorDeadlockedThreads()
                    : bean.findDeadlockedThreads();
            if (containsAll(found, targets)) {
                return found;
            }
            Thread.sleep(15);
        } while (System.nanoTime() < deadline);
        throw new AssertionError("Expected cycle not detected");
    }

    private static void checkOwnerPair(
            Map<Long, ThreadInfo> info, Thread left, Thread right) {
        ThreadInfo a = info.get(left.threadId());
        ThreadInfo b = info.get(right.threadId());
        check(a != null && b != null, "Missing ThreadInfo");
        check(a.getLockOwnerId() == right.threadId()
                && b.getLockOwnerId() == left.threadId(),
                "No two-way owner cycle");
        check(a.getLockInfo() != null && b.getLockInfo() != null,
                "Missing waited-on LockInfo");
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        System.out.println("ThreadMXBean acquired: true");

        Object monitorA = new Object();
        Object monitorB = new Object();
        CountDownLatch monitorHeld = new CountDownLatch(2);
        CountDownLatch monitorGo = new CountDownLatch(1);
        Thread ma = monitorWorker(
                "monitor-A", monitorA, monitorB, monitorHeld, monitorGo);
        Thread mb = monitorWorker(
                "monitor-B", monitorB, monitorA, monitorHeld, monitorGo);
        await(monitorHeld);
        System.out.println(
                "Both monitor threads hold first lock: true");
        monitorGo.countDown();
        awaitDetected(bean, true, ma.threadId(), mb.threadId());
        System.out.println("Monitor-only cycle detected: true");

        if (!bean.isSynchronizerUsageSupported()) {
            System.out.println(
                    "Ownable synchronizer monitoring unavailable: true");
            System.out.println(
                    "Monitor deadlock remains observable: true");
            return;
        }
        System.out.println(
                "Ownable synchronizer monitoring supported: true");
        awaitDetected(bean, false, ma.threadId(), mb.threadId());
        System.out.println(
                "General detector includes monitor cycle: true");

        ReentrantLock lockA = new ReentrantLock();
        ReentrantLock lockB = new ReentrantLock();
        CountDownLatch locksHeld = new CountDownLatch(2);
        CountDownLatch lockGo = new CountDownLatch(1);
        Thread la = lockWorker(
                "reentrant-A", lockA, lockB, locksHeld, lockGo);
        Thread lb = lockWorker(
                "reentrant-B", lockB, lockA, locksHeld, lockGo);
        await(locksHeld);
        System.out.println(
                "Both ReentrantLock threads hold first lock: true");
        lockGo.countDown();
        long[] all = awaitDetected(bean, false,
                ma.threadId(), mb.threadId(),
                la.threadId(), lb.threadId());
        System.out.println(
                "General detector finds both cycles: true");

        long[] monitorsOnly = bean.findMonitorDeadlockedThreads();
        check(containsAll(
                monitorsOnly, ma.threadId(), mb.threadId())
                && Arrays.stream(monitorsOnly)
                        .noneMatch(id ->
                                id == la.threadId()
                                || id == lb.threadId()),
                "Monitor-only detector included ReentrantLock pair");
        System.out.println(
                "Monitor-only detector excludes ReentrantLock cycle: true");

        long[] ids = {
                ma.threadId(), mb.threadId(),
                la.threadId(), lb.threadId()
        };
        boolean withMonitors =
                bean.isObjectMonitorUsageSupported();
        ThreadInfo[] infos = bean.getThreadInfo(
                ids, withMonitors, true);
        Map<Long, ThreadInfo> byId = new HashMap<>();
        for (ThreadInfo info : infos) {
            check(info != null, "Deadlocked thread vanished");
            byId.put(info.getThreadId(), info);
        }
        checkOwnerPair(byId, ma, mb);
        checkOwnerPair(byId, la, lb);
        System.out.println(
                "ThreadInfo owner edges form two 2-cycles: true");

        check(byId.get(ma.threadId()).getThreadState()
                        == Thread.State.BLOCKED
                && byId.get(mb.threadId()).getThreadState()
                        == Thread.State.BLOCKED,
                "Unexpected monitor state");
        System.out.println(
                "Monitor pair state is BLOCKED: true");

        check(byId.get(la.threadId()).getThreadState()
                        == Thread.State.WAITING
                && byId.get(lb.threadId()).getThreadState()
                        == Thread.State.WAITING,
                "Unexpected ReentrantLock state");
        System.out.println(
                "ReentrantLock pair state is WAITING: true");

        check(byId.get(la.threadId())
                        .getLockedSynchronizers().length > 0
                && byId.get(lb.threadId())
                        .getLockedSynchronizers().length > 0,
                "Owned synchronizers not captured");
        System.out.println(
                "Owned synchronizers captured: true");

        if (withMonitors) {
            check(byId.get(ma.threadId())
                            .getLockedMonitors().length > 0
                    && byId.get(mb.threadId())
                            .getLockedMonitors().length > 0,
                    "Owned monitors not captured");
            System.out.println(
                    "Owned object monitors captured: true");
        } else {
            System.out.println(
                    "Object monitor lock inventory unavailable: true");
        }

        check(all.length >= 4, "Too few deadlocked threads");
        check(ma.isDaemon() && mb.isDaemon()
                && la.isDaemon() && lb.isDaemon(),
                "Demo deadlocked non-daemon threads");
        System.out.println(
                "Deadlock demo threads are daemon: true");
        System.out.println(
                "No force-stop or unsafe unlock attempted: true");
    }
}
~~~

### 10.3. Compile và kết quả đã kiểm thử

Lưu đúng tên `DeadlockCycleDemo.java`:

~~~sh
javac --release 21 DeadlockCycleDemo.java
java DeadlockCycleDemo
~~~

**Đã biên dịch và chạy thật trên JDK 24, với JVM hỗ trợ ownable synchronizer + object monitor usage. Stdout chính xác 15 dòng:**

~~~text
ThreadMXBean acquired: true
Both monitor threads hold first lock: true
Monitor-only cycle detected: true
Ownable synchronizer monitoring supported: true
General detector includes monitor cycle: true
Both ReentrantLock threads hold first lock: true
General detector finds both cycles: true
Monitor-only detector excludes ReentrantLock cycle: true
ThreadInfo owner edges form two 2-cycles: true
Monitor pair state is BLOCKED: true
ReentrantLock pair state is WAITING: true
Owned synchronizers captured: true
Owned object monitors captured: true
Deadlock demo threads are daemon: true
No force-stop or unsafe unlock attempted: true
~~~

Nếu JVM không hỗ trợ ownable synchronizer monitoring, demo **dừng sớm sau monitor cycle** với hai dòng fallback khác. Không lấy output 15 dòng này làm yêu cầu trên mọi JVM; các assertions về monitor/ReentrantLock state được test với JDK/VM nêu ở trên.

### 10.4. Phân tích từng giai đoạn

**Giai đoạn monitor:** Cả `monitor-A` và `monitor-B` phải lấy xong first lock trước khi `monitorGo.countDown()`. Khi cửa được mở, mỗi thread cố vào monitor do thread còn lại giữ. `findMonitorDeadlockedThreads()` tìm thấy chu trình, không cần dựa vào thứ tự scheduler.

**Giai đoạn ownable synchronizer:** `ReentrantLock.lock()` giữ exclusive owner và chờ bằng synchronizer mechanism. `findDeadlockedThreads()` thấy cả hai monitor deadlocked threads và hai ReentrantLock deadlocked threads. Monitor-only detector không xem ReentrantLock pair.

**Owner graph:** `getThreadInfo` trả snapshots; `checkOwnerPair` kiểm `A.getLockOwnerId()==B.threadId()` và ngược lại cho cả hai cặp. Đây là bằng chứng rõ hơn việc chỉ nói “có hai threads WAITING”.

**Locked inventories:** `getLockedMonitors()`/`getLockedSynchronizers()` cho thấy những lock threads sở hữu; nó khác `getLockInfo()` là lock đang chờ lấy.

**Daemon setup:** Các thread cố ý bị deadlock là daemon platform threads, để chương trình học **không giữ tiến trình chạy mãi**. Một thread daemon vẫn có thể giữ locks trong lúc JVM sống; đây không phải biện pháp xử lý deadlock cho ứng dụng thật. Không lấy logic này dùng trong server.

**Không force-unlock:** `synchronized` monitors chỉ tự được release khi thoát block, còn `ReentrantLock` phải được unlock bởi owner theo semantics. Một deadlock không dễ “tự cứu” từ main thread; bài học nhấn mạnh phòng ngừa và chẩn đoán.

## 11. Chương trình #2: một thread BLOCKED nhưng **không deadlock**

Ví dụ `ContentionIsNotDeadlockDemo.java` tạo tình huống rất thường gặp: một thread `owner` vào `synchronized(lock)`, một thread `contender` cố vào cùng monitor và bị `BLOCKED`.

Main thread:

1. Dùng `CountDownLatch ownerEntered` đảm bảo Owner đã giữ monitor.
2. Khởi động Contender, đợi bắt đầu.
3. Poll `ThreadMXBean.getThreadInfo(contender.threadId(),10)` đến khi xác nhận `BLOCKED`.
4. Kiểm `getLockOwnerId() == owner.threadId()`.
5. Gọi cả monitor-only detector và general detector (nếu supported): **không có cycle bao gồm hai IDs**.
6. `finally` mở `permitRelease`: Owner ra khỏi `synchronized`, Contender lấy monitor và thoát.
7. `join` với timeout, kiểm cả hai thread kết thúc.

Sơ đồ:

~~~text
Contender --waits for L--> Owner
Owner --waiting for release signal from main--> Main
Main --does not hold L--> releases signal

No owner-lock cycle; Contender eventually proceeds.
~~~

**Đừng nhầm:** Owner đang `WAITING` trên latch do main điều khiển, nhưng nó không chờ một lock do Contender sở hữu. Điều kiện tạo deadlock **theo lock-owner graph** không xảy ra.

### 11.1. Mã đầy đủ `ContentionIsNotDeadlockDemo.java`

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class ContentionIsNotDeadlockDemo {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(4, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Latch deadline");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    }

    private static boolean includes(long[] ids, long target) {
        return ids != null &&
                Arrays.stream(ids).anyMatch(id -> id == target);
    }

    public static void main(String[] args) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        Object lock = new Object();
        CountDownLatch ownerEntered = new CountDownLatch(1);
        CountDownLatch permitRelease = new CountDownLatch(1);
        CountDownLatch contenderStarted = new CountDownLatch(1);

        Thread owner = Thread.ofPlatform().name("one-lock-owner")
                .unstarted(() -> {
                    synchronized (lock) {
                        ownerEntered.countDown();
                        await(permitRelease);
                    }
                });
        Thread contender = Thread.ofPlatform()
                .name("one-lock-contender")
                .unstarted(() -> {
                    contenderStarted.countDown();
                    synchronized (lock) {
                        // This succeeds when owner releases it.
                    }
                });

        owner.start();
        await(ownerEntered);
        contender.start();
        await(contenderStarted);

        try {
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(4);
            ThreadInfo waitingInfo;
            do {
                waitingInfo = bean.getThreadInfo(
                        contender.threadId(), 10);
                if (waitingInfo != null
                        && waitingInfo.getThreadState()
                                == Thread.State.BLOCKED) {
                    break;
                }
                Thread.sleep(10);
            } while (System.nanoTime() < deadline);

            check(waitingInfo != null
                    && waitingInfo.getThreadState()
                            == Thread.State.BLOCKED,
                    "Contender not observed BLOCKED");
            System.out.println("Contender is BLOCKED: true");

            check(waitingInfo.getLockOwnerId()
                            == owner.threadId(),
                    "Incorrect monitor owner");
            System.out.println(
                    "Owner edge contender -> owner: true");

            long[] monitorCycles =
                    bean.findMonitorDeadlockedThreads();
            check(!includes(
                        monitorCycles, owner.threadId())
                    && !includes(
                        monitorCycles, contender.threadId()),
                    "False positive monitor deadlock");
            System.out.println(
                    "No monitor deadlock in the pair: true");

            if (bean.isSynchronizerUsageSupported()) {
                long[] allCycles =
                        bean.findDeadlockedThreads();
                check(!includes(
                            allCycles, owner.threadId())
                        && !includes(
                            allCycles, contender.threadId()),
                        "False positive generalized deadlock");
                System.out.println(
                    "No general deadlock in the pair: true");
            } else {
                System.out.println(
                    "General detector unavailable: true");
            }
        } finally {
            permitRelease.countDown();
        }

        owner.join(4000);
        contender.join(4000);
        check(!owner.isAlive() && !contender.isAlive(),
                "Threads did not finish after lock release");
        System.out.println(
                "Both threads terminate after release: true");
        System.out.println(
                "No deadlock was intentionally created: true");
    }
}
~~~

### 11.2. Chạy và stdout

~~~sh
javac --release 21 ContentionIsNotDeadlockDemo.java
java ContentionIsNotDeadlockDemo
~~~

**Đã biên dịch và chạy trên JDK 24. Stdout 6 dòng:**

~~~text
Contender is BLOCKED: true
Owner edge contender -> owner: true
No monitor deadlock in the pair: true
No general deadlock in the pair: true
Both threads terminate after release: true
No deadlock was intentionally created: true
~~~

Trong JVM không hỗ trợ ownable synchronizer monitoring, dòng thứ tư là `General detector unavailable: true` thay vì câu kiểm `findDeadlockedThreads()`. Nhóm hai threads vẫn được giải phóng qua `finally`.

### 11.3. Bài học quan trọng

Đây là một ví dụ **contention hợp lệ**:

- `BLOCKED` chỉ cho biết một thread chưa vào được monitor.
- `getLockOwnerId()` xác định thread đang giữ monitor.
- Không có cạnh lock ownership quay ngược từ Owner đến Contender.
- Sau khi Owner thả monitor, Contender kết thúc bình thường.
- Detector không coi nhóm đó là deadlock.

Không hiển thị cảnh báo **deadlock** cho tất cả threads đang `BLOCKED`. Với hệ thống monitoring, bạn có thể cảnh báo **long contention** hoặc latency cao như một loại vấn đề khác; dùng tên alert chính xác để tránh điều tra sai.

## 12. Chương trình #3: công cụ báo cáo deadlock không tự tạo lock

Hai ví dụ trước tạo lock scenarios để học. Khi muốn dùng trong một ứng dụng/service, **đừng cố tình tạo deadlock**. Chương trình nhỏ `ThreadDeadlockReport.java` chỉ đọc `ThreadMXBean` của JVM đang chạy.

Nó:

1. Xác định khả năng giám sát ownable synchronizers.
2. Gọi `findDeadlockedThreads()` hoặc fallback `findMonitorDeadlockedThreads()`.
3. Nếu không thấy cycle, in kết quả và phạm vi phát hiện.
4. Nếu có cycles, sắp xếp IDs để report ổn định, lấy `ThreadInfo` kèm lock inventory khi được hỗ trợ.
5. In `threadId`, thread name, state, ownerId, lock chờ, số monitors/synchronizers đang giữ.
6. Nếu dùng `--stacks`, in tối đa **5 stack frames/thread**.
7. Không sửa threads, không unlock, không tạo JMX remote connector.

**Hạn chế:** Nó kiểm **JVM hiện tại**. Khi chạy như một process độc lập mới, nó không quan sát deadlocks của một JVM khác. Với JVM khác, chạy diagnostics trong process đó, dùng JMX remote **được bảo vệ** hoặc công cụ JVM có quyền phù hợp.

### 12.1. Source `ThreadDeadlockReport.java`

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;

public final class ThreadDeadlockReport {
    public static void main(String[] args) {
        if (args.length > 1
                || (args.length == 1
                && !"--stacks".equals(args[0]))) {
            System.err.println(
                    "Usage: java ThreadDeadlockReport [--stacks]");
            System.exit(2);
        }

        ThreadMXBean bean =
                ManagementFactory.getThreadMXBean();
        boolean synchronizers =
                bean.isSynchronizerUsageSupported();
        boolean monitors =
                bean.isObjectMonitorUsageSupported();

        long[] deadlocked = synchronizers
                ? bean.findDeadlockedThreads()
                : bean.findMonitorDeadlockedThreads();

        if (deadlocked == null || deadlocked.length == 0) {
            System.out.println(
                    "No platform-thread lock cycle detected.");
            System.out.println("Coverage: monitor"
                    + (synchronizers
                            ? " + ownable synchronizers"
                            : " only"));
            return;
        }

        Arrays.sort(deadlocked);
        ThreadInfo[] infos = bean.getThreadInfo(
                deadlocked, monitors, synchronizers);
        System.out.println(
                "Platform threads in lock cycles: "
                + deadlocked.length);

        for (int i = 0; i < deadlocked.length; i++) {
            ThreadInfo info = infos[i];
            if (info == null) {
                System.out.println(
                        "id=" + deadlocked[i]
                        + " vanished before details read");
                continue;
            }
            System.out.println(
                    "id=" + info.getThreadId()
                    + " name=" + info.getThreadName()
                    + " state=" + info.getThreadState()
                    + " ownerId=" + info.getLockOwnerId()
                    + " waitingFor=" + info.getLockInfo()
                    + " ownedMonitors="
                    + info.getLockedMonitors().length
                    + " ownedSynchronizers="
                    + info.getLockedSynchronizers().length);

            if (args.length == 1) {
                StackTraceElement[] frames =
                        info.getStackTrace();
                for (int n = 0;
                        n < Math.min(5, frames.length); n++) {
                    System.out.println("  at " + frames[n]);
                }
            }
        }
        System.out.println(
                "This is a diagnostic snapshot, not a recovery action.");
    }
}
~~~

### 12.2. Biên dịch và đầu ra trong JVM bình thường

~~~sh
javac --release 21 ThreadDeadlockReport.java
java ThreadDeadlockReport
~~~

Trong một JVM test mới không có lock deadlock, **stdout đã được kiểm chính xác**:

~~~text
No platform-thread lock cycle detected.
Coverage: monitor + ownable synchronizers
~~~

Nếu JVM không hỗ trợ ownable synchronizers, câu thứ hai thay bằng `Coverage: monitor only`.

Trong một JVM có deadlock, kết quả **không cố định**: nó phụ thuộc số IDs, thread names, locks và call stacks thực tế. Chương trình có thể in:

~~~text
Platform threads in lock cycles: <number>
id=<thread-id> name=<thread-name> state=<state> ownerId=<owner-id> waitingFor=<lock-info> ownedMonitors=<count> ownedSynchronizers=<count>
This is a diagnostic snapshot, not a recovery action.
~~~

Đây là **mẫu có placeholders**, không phải stdout được chép từ máy người dùng. IDs/lock info/call stacks không thể tiên đoán. Hãy chạy `--stacks` khi cần vị trí code, tránh bật stack trace công khai liên tục.

### 12.3. Giữ riêng chẩn đoán và khắc phục

Một báo cáo thể hiện vòng chờ là bằng chứng để xác định code đang giữ khóa sai thứ tự, không phải hành động tự giải phóng mọi locks. Ứng dụng production nên thu thập **một vài** snapshots kèm timestamps và revision, rồi sửa chương trình/triển khai bản vá; không gọi một API ngầm force-unlock từ ngoài.

## 13. Thiết kế công cụ giám sát production

### 13.1. Polling đúng mục đích

`ThreadMXBean.findDeadlockedThreads()` là **diagnostic operation có thể đắt**. Đừng gọi sau mỗi HTTP request hoặc mỗi lần ghi log. Nếu app cần watchdog, chọn chu kỳ hợp lý theo SLO, ví dụ khi phát hiện triệu chứng không tiến triển, có backoff và rate limit; không tuyên bố một tần suất cố định phù hợp mọi JVM.

Gợi ý chính sách:

- Bình thường: theo dõi request latency, queue depth, thread count, stuck request count.
- Khi có cảnh báo hang hoặc tăng thời gian chờ: kích hoạt deadlock scan có giới hạn.
- Nếu có IDs: lưu timestamp, thread IDs/names, owner edges, top stack frames và lock details đã redact.
- Nếu null: kiểm timeout, contention, starvation, remote dependencies, GC và virtual threads thay vì kết luận hệ thống hoàn toàn khỏe.
- Không làm scan quá nhiều lần nếu có hàng nghìn threads; công cụ chuyên biệt/JFR và profiling có thể hỗ trợ phân tích nguyên nhân.

### 13.2. Không dựa vào thread contention monitoring timing để bật deadlock detection

`isThreadContentionMonitoringSupported()`/`setThreadContentionMonitoringEnabled(true)` liên quan **thống kê thời gian blocked/waited**. Nó không phải điều kiện phải bật để `findDeadlockedThreads()` nhận diện ownership cycle. Thay vì bật mọi loại metrics tốn chi phí, kiểm `isSynchronizerUsageSupported()` cho khả năng general detector và chỉ lấy stats phù hợp khi cần.

### 13.3. Snapshot không nguyên tử xuyên suốt mọi lệnh

Sau `findDeadlockedThreads()`, thread list có thể thay đổi trước khi `getThreadInfo(ids,...)`; `ThreadInfo[]` có thể chứa `null`. Thậm chí những IDs được detector trả về có thể không còn sống ở runtime/case đặc biệt. Code reporter xử lý null entries và không tự suy ra mọi stack/owner line trong bản báo cáo là một transaction atomic.

### 13.4. Một thread không thể có thứ tự owner graph xác định từ mảng IDs

Nếu detector trả `long[]{idA, idB, idC}`, không kết luận `idA→idB→idC→idA` theo thứ tự mảng; mảng không cam kết thứ tự cycle. Phải map mỗi `ThreadInfo.getThreadId()` đến `getLockOwnerId()` để dựng cạnh, rồi mới phân nhóm cycles.

### 13.5. Đừng “cứu” live deadlock bằng interrupt mù

`Thread.interrupt()` không đảm bảo phá `synchronized` monitor entry hoặc `ReentrantLock.lock()` không interruptible. `ReentrantLock.lockInterruptibly()`/`tryLock(timeout)` cho phép xây dựng giao thức tránh đợi mãi **nếu ứng dụng dùng đúng chúng từ đầu**, nhưng không làm Java tự động phục hồi khi code đã mắc deadlock trong monitor entry.

Khi có deadlock thực sự trong production:

1. Giữ nguyên bằng chứng (thread dump, logs, revision, input context nếu phù hợp bảo mật).
2. Xác định thread ownership edges và vị trí code giữ/gọi lock.
3. Ngăn tăng tải nếu cần.
4. Thực hiện restart/rollback có kiểm soát theo runbook/transaction semantics.
5. Sửa root cause (thứ tự khóa, nested calls, lock scope, timeout).
6. Viết regression test có latches để tái hiện, không dựa vào sleep ngẫu nhiên.

## 14. Cách phòng tránh deadlock theo cấu trúc code

### 14.1. Đặt thứ tự lấy locks nhất quán

Thay vì A lấy L1 rồi L2 nhưng B lấy L2 rồi L1, mọi nơi dùng **một thứ tự chung**:

~~~java
synchronized (lockA) {
    synchronized (lockB) {
        updateSharedState();
    }
}
~~~

Đây là snippet (biến `lockA`/`lockB` và `updateSharedState()` do ứng dụng cung cấp). Nếu tất cả threads luôn lấy `lockA` trước `lockB`, vòng chờ đảo chiều với hai locks đó không thể xảy ra. Với nhiều objects cần thứ tự, dùng định danh/ordering bền vững, xử lý trường hợp tie một cách an toàn.

Không đồng bộ trên object từ input tùy ý như String interned/class literal công khai; nên dùng private lock objects để không bị code ngoài đồng bộ nhầm vào cùng lock.

### 14.2. Giảm phạm vi giữ khóa

Sai:

~~~java
synchronized (stateLock) {
    sendHttpRequest();
    writeToDatabase();
    updateState();
}
~~~

Đây là **anti-pattern**: giữ monitor trong lúc I/O/DB có thể lâu hoặc gọi service khác. Nếu request chờ vào code cũng dùng lock, nguy cơ starvation hoặc chu trình phụ thuộc tăng.

Tốt hơn: đọc/cập nhật local snapshot dưới lock ngắn, thực hiện I/O bên ngoài lock nếu invariants và consistency model cho phép, rồi commit có kiểm tra hoặc dùng transaction boundary rõ ràng.

### 14.3. Dùng tryLock khi muốn bounded waiting

~~~java
boolean acquired = lock.tryLock(200, TimeUnit.MILLISECONDS);
if (!acquired) {
    throw new IllegalStateException("Lock acquisition timed out");
}
try {
    updateState();
} finally {
    lock.unlock();
}
~~~

Đây là snippet sử dụng `ReentrantLock lock` và method `updateState()` do ứng dụng định nghĩa; method phải xử lý `InterruptedException`. Nó tránh một chờ vô hạn **ở điểm lấy lock đó**, nhưng không loại mọi kiểu deadlock, ví dụ nếu code đã giữ một lock khác và xử lý timeout sai.

### 14.4. Lock interruptibly

~~~java
lock.lockInterruptibly();
try {
    updateState();
} finally {
    lock.unlock();
}
~~~

Đây là snippet. Khi policy cho phép cancellation, một thread đang đợi lock có thể được interrupt. Nhưng **tôn trọng interrupt đúng cách** và bảo toàn state, không catch rồi tiếp tục như chưa bị hủy.

### 14.5. Không gọi callback bên ngoài khi đang giữ internal lock

Ví dụ: callback logging, plugin event handler hoặc user-supplied listener có thể đột ngột lấy lock khác. Nếu code gọi callback trong `synchronized`, bạn mất quyền kiểm soát lock ordering. Nên snapshot data rồi gọi callbacks ngoài critical section khi nghiệp vụ cho phép.

### 14.6. Với application-level dependency cycles, cần graph riêng

`CompletableFuture` tasks chờ nhau, job queues phụ thuộc nhau, DB transactions hoặc cross-service calls có thể tạo deadlock logic mà `ThreadMXBean` không thấy. Dùng task IDs/dependency edges, DB lock reports, request traces và bounded timeouts; không ép mọi vấn đề quy về intrinsic monitors.

## 15. Monitoring qua JMX và công cụ vận hành

`ManagementFactory.getThreadMXBean()` phù hợp chẩn đoán **JVM hiện tại**. Platform MBeanServer thường có Threading MXBean dưới ObjectName:

~~~text
java.lang:type=Threading
~~~

Công cụ JMX được phép có thể gọi các operations của Threading MXBean qua MBeanServerConnection. Trên máy sử dụng Java/JConsole/JMC, các công cụ chẩn đoán có thể giúp xem threads và deadlocks. Nhưng nếu kết nối **từ xa**, phải bảo vệ remote JMX bằng authentication, authorization, TLS, firewall/ACL và timeouts; không mở management port không bảo vệ ra Internet.

### 15.1. Thread dump từ JVM mục tiêu

Với tiến trình khác được phép quản trị, một hướng an toàn hơn việc viết code gọi remote methods tùy ý là thu thập thread dump theo runbook. Trên Java 26:

~~~sh
jcmd <pid> Thread.print -l
jcmd <pid> Thread.dump_to_file -format=json <secure-file>
~~~

- `Thread.print -l`: thông tin platform threads/mounted virtual threads và synchronization details theo công cụ/JDK.
- `Thread.dump_to_file`: thread dump file bao gồm cả virtual threads, hữu ích khi ThreadMXBean không hỗ trợ chúng, nhưng **không tự phân tích deadlock**.
- Những dumps này có thể tiết lộ tên threads, file paths, stack traces, business internals. Bảo vệ file access, retention và chia sẻ.

Không đưa lệnh này vào chương trình test vì test phải **không ảnh hưởng JVM khác** và không cần quyền hệ điều hành bổ sung.

### 15.2. JFR và Java Mission Control

Java Flight Recorder (JFR) cùng Java Mission Control là những công cụ hiện hành cho phân tích performance/threads/locks theo sự kiện. Chúng hỗ trợ quan sát blocking và lock contention theo runtime/JDK; cấu hình loại sự kiện, ngưỡng và retention cần được xác nhận trên JVM cụ thể. **Đừng tuyên bố JFR tự phát hiện mọi virtual-thread deadlock**. Thông tin sự kiện có thể giúp bạn tái dựng nguyên nhân nhưng không thay `ThreadMXBean` hoặc application-level graph khi cần kết luận cycle.

## 16. Một tình huống vận hành: API không phản hồi nhưng detector trả null

Triệu chứng: HTTP request bị timeout, thread pool đầy, `findDeadlockedThreads() == null`. Chẩn đoán không nên kết luận “không có vấn đề concurrency”.

Hãy phân loại:

| Điều quan sát | Giả thuyết tiếp theo |
| --- | --- |
| Nhiều `BLOCKED` cùng một monitor nhưng owner vẫn tiến triển | Lock contention/hot lock |
| Nhiều `WAITING` trên queue/condition | Worker rảnh, thiếu task hoặc tín hiệu bị bỏ |
| Nhiều tasks chờ `CompletableFuture.join()` | Dependency cycle/starvation ở tầng task |
| Blocking DB calls | Connection pool / SQL locks / transaction timeouts |
| Network read/connect chờ rất lâu | Deadline/timeout/remote service |
| CPU cao, stack lặp | Livelock/spin hoặc thuật toán chậm |
| Threads có count ổn nhưng request timeout | Saturation ở queue/pool/IO, not necessarily deadlock |
| Dùng virtual threads, ThreadMXBean không có IDs | Virtual-thread diagnostics / jcmd dump |
| JVM bị dừng do GC dài | GC logs/JFR/heap pressure |

Tính đúng đắn của kết luận nằm ở **chuỗi bằng chứng**, không ở một giá trị null.

## 17. Các sai lầm thường gặp

| Sai lầm | Vì sao sai | Sửa thế nào |
| --- | --- | --- |
| Xem `Thread.State.BLOCKED` là deadlock | Contention không nhất thiết có cycle | Kiểm lock owner graph và forward progress |
| Xem `WAITING` là deadlock | Queue/latch/future có thể chờ bình thường | Phân tích resource dependency |
| Gọi `findMonitorDeadlockedThreads` để tìm ReentrantLock deadlock | API chỉ monitor | Gọi `findDeadlockedThreads` khi supported |
| Gọi `findDeadlockedThreads` khi không hỗ trợ ownable synchronizer usage | Có thể ném UnsupportedOperationException | Kiểm `isSynchronizerUsageSupported()`, fallback monitor |
| Bật contention monitoring mới mong detector chạy | Hai khả năng khác nhau | Không bắt buộc bật blocked/waited time |
| Đọc `ids.length` khi detector trả null | NullPointerException | Null-check trước |
| Dùng thứ tự mảng IDs làm thứ tự cycle | Không cam kết ordering | Dựng edges từ `getLockOwnerId()` |
| Dùng `Thread.getId()` trong Java 21+ demo mới | Method deprecated từ 19 | Dùng `Thread.threadId()` |
| Dùng `Thread.ofVirtual()` rồi mong ThreadMXBean thấy cycle | API không giám sát virtual threads | Dùng platform threads cho test detector; công cụ khác cho virtual |
| Xem `findDeadlockedThreads()==null` là “không có deadlock trong cả hệ thống” | Giới hạn platform/ownable/monitor và snapshot | Nêu rõ phạm vi phát hiện |
| Dựa vào một lần quét làm state bất biến | Threads thay đổi giữa các calls | Chấp nhận null ThreadInfo, thu thập snapshots hợp lý |
| Gọi getThreadInfo với cả hai flags true trên VM không hỗ trợ | UnsupportedOperationException | Dùng capability flags |
| Ghi toàn bộ thread dump vào public logs | Lộ đường dẫn/nội bộ/dữ liệu | Redact, limit frames, protected storage |
| Tạo demo deadlock bằng non-daemon threads | JVM test không thoát | Chỉ demo isolated JVM + daemon threads |
| Cố interrupt một thread đang vào synchronized để “gỡ” deadlock | Intrinsic monitor entry không interruptible | Phòng ngừa, restart/rollback có kiểm soát |
| Force stop/suspend threads | Có thể phá invariants, lỗi thời/không an toàn | Không dùng |
| Sleep một khoảng rồi khẳng định test deadlock | Timing flaky | Dùng CountDownLatch xác nhận first locks |
| Poll detector liên tục trong mọi request | Diagnostic có thể tốn CPU/safepoint cost | Scan có kiểm soát/trigger-on-symptom |
| Gọi `jcmd dump_to_file` là tự động phân tích deadlock | Nó tạo dump, không phân tích cycles | Dùng ThreadMXBean/JConsole/analysis phù hợp |
| Không định nghĩa lock order | Dễ tạo A→B→A | Thứ tự toàn cục, scope ngắn |
| Gọi I/O bên trong lock | Tăng thời gian giữ lock/chu trình phụ thuộc | Tách I/O khỏi critical section |
| Quên finally với ReentrantLock | Lock leak khi exception | `try/finally unlock` |
| Thấy 2 waiting threads rồi kết luận chúng chờ nhau | Chưa biết owner edges | Đọc ThreadInfo getLockOwnerId |
| Chỉ xử lý Java monitors mà bỏ DB/remote | Các liveness issue bên ngoài | Xem observability tầng liên quan |
| “Giải deadlock” bằng cách random retry tất cả requests | Có thể gây side effects/overload | Idempotency + recovery runbook |

## 18. Ma trận kiểm thử thực tế

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Monitor A ↔ B | Hai threads giữ monitor khác nhau, đợi chéo | `findMonitorDeadlockedThreads` tìm đúng IDs |
| Cùng monitor cycle | Gọi `findDeadlockedThreads` | Bao gồm monitor IDs nếu supported |
| ReentrantLock A ↔ B | Hai ownable synchronizers, lấy chéo | General detector tìm đúng pair |
| ReentrantLock-only với monitor detector | Gọi monitor-only | Không có ReentrantLock IDs |
| Hai cycles độc lập | Monitor pair + Reentrant pair | General detector tìm ≥4 IDs |
| Không có deadlock | JVM sạch | `null` (reporter in “No ...”) |
| Một Contender BLOCKED | Owner đang giữ monitor nhưng sẽ release | Không có cycle cho pair |
| Contention giải phóng | `CountDownLatch` cho owner thoát | Cả hai threads hoàn tất |
| Owner graph | `getLockOwnerId()` | A→B và B→A |
| Monitor state | Monitor deadlock pair | `BLOCKED` trên JVM thử nghiệm |
| ReentrantLock state | Ownable deadlock pair | `WAITING` trên JVM thử nghiệm |
| Locked monitor details | VM hỗ trợ monitor usage | `getLockedMonitors()` có entries |
| Locked synchronizer details | VM hỗ trợ ownable usage | `getLockedSynchronizers()` có entries |
| Không hỗ trợ ownable usage | Mock/runtime hỗ trợ ít | Fallback monitor-only |
| ThreadInfo biến mất | Thread hoàn tất giữa scan và read | Null-check, không NPE |
| Có virtual threads | Java 21+ | Không kỳ vọng ThreadMXBean phát hiện cycle có virtual thread |
| CountDownLatch chờ mãi | Không có lock-owner cycle | Detector có thể trả null |
| Thread dump JSON | JVM được phép | Có virtual threads nhưng không auto deadlock analysis |
| Java 21 compatibility | `javac --release 21` | Cả ba demos biên dịch |
| No deprecated Thread.getId | Dùng `threadId()` | Không dựa vào API deprecated |
| Thread test không treo process | Deadlocked daemons | JVM demo thoát sau stdout |
| Report không tự tạo deadlock | Process sạch | Hai dòng stdout đã kiểm |
| Reporting privacy | Bounded stack output | Không log toàn bộ nội dung nhạy cảm |
| Monitoring overhead | Trigger-on-symptom/rate limit | Tránh scan quá thường xuyên |

## 19. Câu hỏi tự kiểm tra

**1. `findDeadlockedThreads()` khác `findMonitorDeadlockedThreads()` ra sao?**

Phương thức đầu phát hiện cycles gồm **object monitors và ownable synchronizers** (khi JVM hỗ trợ); phương thức thứ hai chỉ phát hiện **object monitor** deadlocks.

**2. `findDeadlockedThreads()` trả gì nếu không phát hiện cycle?**

`null`, không tự trả boolean hay số lượng 0.

**3. Khi nào `findDeadlockedThreads()` có thể ném `UnsupportedOperationException`?**

Khi JVM không hỗ trợ monitoring of ownable synchronizer usage. Kiểm `isSynchronizerUsageSupported()` và fallback phù hợp.

**4. Một thread đang `BLOCKED` có phải deadlock không?**

Không. Có thể chỉ bị contention; cần có cycle trong wait-for owner graph.

**5. `ReentrantLock` deadlock có bắt buộc `BLOCKED` không?**

Không. Trên test HotSpot, nó xuất hiện `WAITING`. Phải dùng general detector và owner edges.

**6. A → B là đủ để khẳng định deadlock không?**

Không. Cần có chu trình khép kín, ví dụ A → B → A hoặc A → B → C → A.

**7. `getLockOwnerId()` dùng để làm gì?**

Để biết ID thread đang sở hữu lock mà thread hiện tại chờ; dùng tạo edge waiter → owner.

**8. `getLockOwnerId()==-1` nghĩa là gì?**

Không xác định owner hoặc không có owner cho khóa đang được chờ; không tự suy diễn edge.

**9. `getLockedSynchronizers()` và `getLockInfo()` khác nhau ra sao?**

Method đầu mô tả những ownable synchronizers thread **đang giữ**; method sau mô tả lock thread **đang chờ**.

**10. Vì sao phải kiểm `isObjectMonitorUsageSupported()` trước khi yêu cầu getThreadInfo(...,true,...) ?**

Nếu JVM không hỗ trợ chi tiết owned monitors, yêu cầu true có thể ném UnsupportedOperationException.

**11. `findDeadlockedThreads()` có sửa lock hay interrupt thread không?**

Không. Nó chỉ tìm cycles để chẩn đoán.

**12. Có nên dùng `Thread.stop()` để cứu deadlock không?**

Không. Đó là API nguy hiểm/lỗi thời, có thể làm hỏng shared state/invariants. Ưu tiên phòng ngừa, triage và recovery có kiểm soát.

**13. Vì sao ví dụ deadlock tạo daemon platform threads?**

Để JVM test có thể thoát dù cố ý tạo cycle. Đây không phải pattern cho production.

**14. Tại sao demo dùng CountDownLatch thay vì chỉ `Thread.sleep(100)`?**

Latch đảm bảo cả hai threads **đã nắm khóa đầu tiên** trước khi yêu cầu khóa thứ hai; sleep không cho bằng chứng đồng bộ.

**15. `Thread.getId()` có nên dùng trong code Java21+ mới không?**

Không nên; nó đã deprecated từ Java19. Dùng `Thread.threadId()`.

**16. Vì sao code trong bài compile `--release 21` dù ThreadMXBean API đã có từ Java6?**

Để dùng threadId và platform thread builders hiện hành, tránh ví dụ dùng API deprecated. API detector vẫn có trên Java17 và Java26.

**17. Virtual-thread deadlock có được findDeadlockedThreads phát hiện không?**

Không. JavaDoc hiện hành nêu cycles chứa virtual threads không được tìm bởi ThreadMXBean.

**18. `jcmd Thread.dump_to_file` có bao gồm virtual threads không?**

Có trong JDK hiện hành, nhưng **không tự chạy deadlock detection** và snapshot không hoàn toàn đồng thời.

**19. Nếu detector trả null nhưng JVM vẫn treo, làm gì?**

Kiểm contention, pool starvation, futures/latches, DB, I/O, GC, CPU, virtual threads và các dependencies bên ngoài.

**20. `getAllThreadIds()` có bao gồm virtual threads không?**

Không theo `ThreadMXBean` hiện hành; nó mô tả live platform threads.

**21. Có nên dùng ThreadInfo snapshot để đồng bộ ứng dụng không?**

Không. Nó phục vụ diagnostics, có thể lỗi thời ngay khi lấy; lock/cancellation logic phải nằm ở ứng dụng.

**22. Vì sao không được kết luận thứ tự cycle từ thứ tự IDs trả về?**

Không có ordering guarantee; phải đọc owner ID của từng ThreadInfo.

**23. Nếu có hai cycles độc lập, `findDeadlockedThreads` trả gì?**

Nó có thể trả IDs của các platform threads thuộc cả hai cycles; dùng getThreadInfo/owner edges để phân nhóm nếu cần.

**24. `isThreadContentionMonitoringEnabled()` có cần bật để detect deadlock không?**

Không. Contention timing metrics và deadlock detection là hai khả năng khác nhau.

**25. Cách phòng tránh đơn giản và mạnh nhất với nhiều locks?**

Định nghĩa và tuân thủ **thứ tự lấy locks thống nhất**, rút ngắn critical sections, tránh chờ I/O dưới lock, dùng bounded waits/cancellation khi appropriate.

**26. Có thể dùng TryLock timeout để tự phá mọi deadlock không?**

Không. Nó giúp tránh đợi vô hạn ở những điểm dùng `tryLock`, nhưng vẫn cần xử lý rollback/release locks đang giữ và consistency.

**27. Nếu gọi `ThreadDeadlockReport` trong một JVM sạch, có xem được deadlock của JVM đang chạy ở port khác không?**

Không. `ManagementFactory.getThreadMXBean()` áp dụng cho **JVM hiện tại**; cần JMX/attach tooling có quyền để chẩn đoán process khác.

**28. Stack trace có thể chứa dữ liệu nhạy cảm không?**

Có; tránh in toàn bộ vào public logs, giới hạn và kiểm soát nơi lưu.

**29. Một operation `findDeadlockedThreads` nên gọi mỗi request không?**

Không; nó có thể tốn chi phí, nên dùng cho diagnostics hoặc monitoring có giới hạn.

**30. Kết luận quan trọng nhất khi đọc một báo cáo deadlock?**

Đừng chỉ xem thread states. Hãy nối **waiter → lock owner**, tìm **chu trình** và đối chiếu code đang giữ lock để xác định root cause.

## 20. Tóm tắt kiến thức

- **`ThreadMXBean.findDeadlockedThreads()`** tìm cycles của **platform threads** đang chờ **object monitors** hoặc **ownable synchronizers**; trả IDs hoặc null.
- **`findMonitorDeadlockedThreads()`** chỉ tìm monitor cycles; hữu ích khi ownable monitoring không được hỗ trợ.
- **`ThreadInfo.getLockOwnerId()`** là chìa khóa dựng wait-for graph; `getLockedMonitors`/`getLockedSynchronizers` cho biết những khóa thread đang sở hữu.
- Một thread `BLOCKED` hoặc `WAITING` **không tự chứng minh** có deadlock.
- Java 21+ hỗ trợ `Thread.threadId()` và `Thread.ofPlatform()`, tránh `Thread.getId()` deprecated; các ví dụ đã biên dịch và chạy.
- **Virtual threads nằm ngoài phạm vi ThreadMXBean deadlock detection**; `jcmd Thread.dump_to_file` có thể hỗ trợ điều tra nhưng không tự phát hiện vòng chờ.
- Detector dùng cho **chẩn đoán**, không để cưỡng bức mở khóa. Phòng ngừa bằng lock ordering, giới hạn thời gian giữ khóa, bounded waits và thiết kế task dependencies rõ ràng.

### Tài liệu chính thức, kiến thức vẫn áp dụng

- [Oracle Java SE 26 — ThreadMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html): phạm vi platform threads, `findDeadlockedThreads`, `findMonitorDeadlockedThreads`, capability flags và `getThreadInfo`.
- [Oracle Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): đối chiếu API cơ bản với Java17.
- [Oracle Java SE 26 — ThreadInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadInfo.html): thread states, lockOwnerId, LockInfo, locked monitors và synchronizers.
- [Oracle Java SE 26 — LockInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/LockInfo.html): thông tin lock tại điểm chờ/ownership.
- [Oracle Java SE 26 — MonitorInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MonitorInfo.html): stack depth của owned monitors.
- [Oracle Java SE 26 — ManagementFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html): lấy `ThreadMXBean` và platform management.
- [Oracle Java SE 26 — Thread](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html): `threadId()` thay thế `getId()` deprecated; platform và virtual threads.
- [Oracle Java SE 26 — ReentrantLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): ownable synchronizer và lock/unlock/tryLock/lockInterruptibly.
- [Oracle Java SE 26 — CountDownLatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phối hợp test setup bằng latch.
- [Oracle Java SE 26 — Virtual Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): virtual thread diagnostics và thread dump file limitations.
- [Oracle Java SE 26 — jcmd](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): `Thread.print` và `Thread.dump_to_file` diagnostics.
- [Oracle Java SE 26 — Monitoring and Management Guide](https://docs.oracle.com/en/java/javase/26/management/java-se-monitoring-and-management-guide.pdf): JConsole Detect Deadlock và theo dõi JVM.
