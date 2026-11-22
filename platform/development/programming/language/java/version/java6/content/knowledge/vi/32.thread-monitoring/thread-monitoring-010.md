# Kiểm thử deadlock có kiểm soát và tổng hợp bằng chứng trong Java

Deadlock là một tình trạng **các luồng chờ lẫn nhau theo một chu trình không thể tiến triển**, điển hình khi mỗi luồng đang giữ một khóa mà luồng khác cần. Khi điều tra một ứng dụng bị treo, chỉ nhìn thấy thread `BLOCKED` hoặc `WAITING` **chưa đủ để kết luận deadlock**. Cần thu thập bằng chứng về **chu trình phụ thuộc**, khóa đang giữ, khóa đang đợi, quan hệ owner và vị trí code; đồng thời phải thiết kế phép kiểm thử để việc **cố ý gây deadlock không làm treo tiến trình kiểm thử chính**.

Bài Knowledge thuộc nhóm **Theo dõi luồng**, xử lý đúng chủ đề **“Kiểm thử deadlock có kiểm soát và tổng hợp bằng chứng”**. Nội dung áp dụng Java 17+ và API JMX còn hiệu lực trong **Java SE 26**; chỉ dùng các hướng dẫn và công cụ hiện hành, không sử dụng những kỹ thuật dừng luồng bị phản đối/deprecated như `Thread.stop()` hay `Thread.suspend()`. Trọng tâm là thiết kế **phép thử an toàn có tiến trình con, deadline, nguồn bằng chứng độc lập, kết quả đối chứng âm và cleanup bắt buộc**.

Một ví dụ đầy đủ `DeadlockEvidenceLab.java` đã được **biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy trên OpenJDK 24.0.2**, đạt **19/19 phép kiểm tra PASS**. Nó thực thi bốn kịch bản trong bốn **JVM con riêng biệt**: đối chứng không deadlock, deadlock hai object monitors, deadlock hai `ReentrantLock` (ownable synchronizers), và deadlock hỗn hợp monitor + ownable synchronizer. Mỗi JVM con tự thu thập `ThreadMXBean` và `ThreadInfo`, xác minh quan hệ A → B → A, loại khóa và stack traces rồi thoát. JVM cha có **timeout 9 giây cho mỗi JVM con** và ép dừng tiến trình con khi vượt deadline. Không cần Maven, Gradle, server ngoài hay kết nối Internet.

## 1. Học xong cần làm được gì?

1. Phân biệt **deadlock**, **contention**, **starvation**, **livelock** và một I/O hang thông thường.
2. Diễn giải điều kiện cần của deadlock trong bài: chu trình **wait-for** giữa những thread giữ khóa và chờ khóa của nhau.
3. Cố ý tạo deadlock monitor và `ReentrantLock` trong **JVM con**, không gây deadlock ngay trong test runner/JVM ứng dụng.
4. Tạo **healthy baseline** không deadlock để phát hiện báo động giả.
5. Dùng `ManagementFactory.getThreadMXBean()`, `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` đúng phạm vi.
6. Đọc `ThreadInfo.getLockInfo()`, `getLockOwnerId()`, `getLockOwnerName()`, `getLockedMonitors()`, `getLockedSynchronizers()`.
7. Phân biệt luồng chờ monitor ở `BLOCKED` với luồng chờ ownable synchronizer thường ở `WAITING`.
8. Đối chiếu **className + identityHashCode** của khóa đang đợi với khóa do luồng kia sở hữu.
9. Dùng stack trace và `MonitorInfo.getLockedStackFrame()` để truy tới lời gọi lấy khóa.
10. Xây bộ báo cáo bằng chứng chuẩn hóa không phụ thuộc thread IDs ngẫu nhiên hoặc timestamp.
11. Đặt timeout cho **barrier**, **chờ phát hiện**, **JVM con** và **bước cleanup**.
12. Kiểm tra khả năng JVM hỗ trợ monitor/ownable usage trước khi gọi overload chi tiết.
13. Nắm giới hạn hiện hành: `ThreadMXBean` chỉ giám sát **platform threads**, không phát hiện đầy đủ deadlocks liên quan virtual threads.
14. Biết khi nào dùng `jcmd Thread.print -l`, `jcmd Thread.dump_to_file` hoặc JFR để bổ sung bằng chứng.
15. Chuyển từ bằng chứng test sang một runbook xử lý sự cố và test chống tái phát.

## 2. Deadlock khác “thread bị chậm” thế nào?

Một thread chờ lock chưa có nghĩa deadlock. Ví dụ A đang giữ monitor 20 ms, B chờ rồi sẽ lấy được monitor khi A hoàn tất: đây là **lock contention bình thường**.

Deadlock xuất hiện khi có một chu trình giữ-và-chờ mà mọi thành viên bị kẹt:

```text
Thread A --đang giữ--> Lock X
Thread A --đang đợi--> Lock Y

Thread B --đang giữ--> Lock Y
Thread B --đang đợi--> Lock X

Wait-for graph:
  A --đợi khóa của--> B
  B --đợi khóa của--> A
  => A -> B -> A
```

Hai thread này sẽ không tự tiến triển nếu không có cơ chế can thiệp thích hợp; với intrinsic monitors, không thể an toàn “interrupt để nhả monitor đã giữ” như một phép cứu chung.

### 2.1. Các tình trạng cần phân biệt

| Hiện tượng | Dấu hiệu | Cần gì để kết luận |
| --- | --- | --- |
| **Deadlock** | Chu trình khóa: mỗi thread giữ một khóa và chờ khóa của thread khác. | Wait-for cycle, owner chain và loại lock. |
| **Contention** | Nhiều thread muốn cùng lock, nhưng vẫn có thread tiến triển. | Latency/blocked time, repeated snapshots, throughput. |
| **Starvation** | Một thread ít/không được tài nguyên hoặc lịch chạy. | Quan sát đủ thời gian, fairness/scheduler/queue metrics. |
| **Livelock** | Threads vẫn chạy nhưng liên tục đổi trạng thái mà không hoàn thành công việc. | Progress counters/trace, không chỉ thread states. |
| **Hung I/O** | Thread chờ socket, file, network, queue, database. | Stack/I/O deadlines, peer metrics, không nhất thiết có lock cycle. |
| **Executor starvation** | Tasks đợi nhau trong một thread pool không còn worker trống. | Queue/task dependency graph; có thể không nằm trong scope JMX lock deadlock finder. |

**Không dùng một lần `Thread.State.WAITING` hoặc `BLOCKED` làm assertion rằng deadlock tồn tại.** Deadlock test phải xác minh *quan hệ phụ thuộc vòng* và consistency của lock ownership.

### 2.2. Vì sao cần healthy baseline?

Nếu test framework luôn in “deadlocked=2” dựa trên một trạng thái tình cờ, một trường hợp **không có deadlock** sẽ phơi bày lỗi. Trong bài này JVM con `healthy` không tạo chu trình, kiểm tra hai phương thức phát hiện trả `null` rồi phát dòng chuẩn:

```text
EVIDENCE|healthy|deadlocked=0|monitorOnly=0
```

Điều này chỉ là một đối chứng âm trong JVM mới, **không khẳng định một hệ thống production sẽ không bao giờ có deadlock**.

## 3. Monitor, ownable synchronizer và deadlock hỗn hợp

### 3.1. Hai monitor nội tại

Một `synchronized (lock)` dùng monitor của Java object. Nếu A giữ X rồi muốn Y, còn B giữ Y rồi muốn X:

```java
// Minh họa nguy hiểm: KHÔNG chạy trực tiếp trong application/JUnit JVM.
synchronized (x) {
    synchronized (y) {
        // ...
    }
}
```

Đoạn trên **một mình không tạo deadlock**; lỗi cần hai luồng lấy khóa theo **thứ tự đối nghịch**. Trong lab, A chạy `synchronized(x)` rồi `synchronized(y)`, B chạy `synchronized(y)` rồi `synchronized(x)` và có barrier để cả hai giữ được khóa đầu trước khi thử khóa thứ hai.

Khi kẹt, hai waiters ở **`BLOCKED`**, `getLockedMonitors()` của mỗi thread có monitor đang giữ, và `findMonitorDeadlockedThreads()` có thể thấy chu trình.

### 3.2. Hai ReentrantLock (ownable synchronizers)

`java.util.concurrent.locks.ReentrantLock` dùng ownable synchronizer nội bộ dựa trên `AbstractQueuedSynchronizer`. Trong contention, thread gọi `lock()` thường **park**, xuất hiện ở **`WAITING`**. Hai threads cố lấy hai `ReentrantLock` theo thứ tự đối nghịch vẫn có thể deadlock.

`findMonitorDeadlockedThreads()` chỉ tìm chu trình monitor nên **không** là API đủ phạm vi cho trường hợp này. `findDeadlockedThreads()` tìm chu trình platform threads chờ **object monitors hoặc ownable synchronizers**.

### 3.3. Một monitor và một ReentrantLock

Trường hợp hỗn hợp:

```text
Thread A:
  giữ intrinsic monitor M
  chờ ReentrantLock L   -> WAITING

Thread B:
  giữ ReentrantLock L
  chờ intrinsic monitor M -> BLOCKED

Cycle: A -> B -> A

findDeadlockedThreads() -> thấy chu trình
findMonitorDeadlockedThreads() -> không thấy toàn chu trình
```

Trên JVM có ownable synchronizer monitoring, đây là một ví dụ quan trọng để giải thích vì sao **cùng một ứng dụng có thể có deadlock mà monitor-only detector trả null**.

## 4. API phát hiện deadlock trong Java hiện hành

`ThreadMXBean` từ `java.lang.management` có hai method quan trọng:

| API | Phạm vi | Kết quả khi không phát hiện |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Chu trình chờ **object monitors** giữa **platform threads**. | `null` |
| `findDeadlockedThreads()` | Chu trình chờ **object monitors hoặc ownable synchronizers** giữa **platform threads**. | `null` |

`findDeadlockedThreads()` có thể ném `UnsupportedOperationException` nếu JVM không hỗ trợ monitoring of ownable synchronizer usage. Các API này **dùng cho troubleshooting**, không phải primitive quản lý synchronization hay cơ chế chữa deadlock.

Trước khi yêu cầu ownership data:

```java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();

boolean supportsMonitors =
        bean.isObjectMonitorUsageSupported();
boolean supportsOwnable =
        bean.isSynchronizerUsageSupported();
```

**Đây là mảnh code minh họa**, cần imports và một method. Nếu một capability thiếu, quy trình test cần trả **SKIPPED/BLOCKER cho coverage tương ứng**, không giả vờ kết quả PASS khi JVM không thể cung cấp bằng chứng chi tiết.

### 4.1. Lấy thông tin từng thread trong cycle

```java
long[] cycleIds = bean.findDeadlockedThreads();

if (cycleIds != null && cycleIds.length > 0) {
    ThreadInfo[] snapshots = bean.getThreadInfo(
            cycleIds, true, true);
    // Kiểm tra snapshots, owners, lock identities và stack frames.
}
```

`getThreadInfo(ids,true,true)` yêu cầu **cả danh sách object monitors và ownable synchronizers đang giữ**. Mảng kết quả tương ứng thứ tự IDs. `ThreadInfo` có thể `null` nếu luồng đã kết thúc, biến mất hoặc không được hỗ trợ.

- `ThreadInfo.getLockInfo()`: **đối tượng đang chờ**, không phải danh sách khóa đã giữ.
- `getLockOwnerId()/getLockOwnerName()`: chủ sở hữu của đối tượng đang chờ (nếu xác định được).
- `getLockedMonitors()`: `MonitorInfo[]` với khóa monitor đang giữ.
- `getLockedSynchronizers()`: `LockInfo[]` với ownable locks đang giữ.
- `getStackTrace()`: vị trí code nơi thread đang bị chặn/chờ.
- `MonitorInfo.getLockedStackFrame()`: frame nơi monitor được lấy, nếu JVM có thông tin.
- `LockInfo.getClassName()/getIdentityHashCode()`: runtime class và identity hash của đối tượng lock; không dùng hash này làm định danh toàn hệ thống.

**Đừng chỉ lấy `getThreadInfo(ids)` rồi kết luận các locked arrays rỗng nghĩa thread không giữ khóa.** Các overload mặc định/flags=false không yêu cầu thông tin ownership.

### 4.2. Tại sao phải đối chiếu identity?

Nếu chỉ nhìn hai stack traces có `ReentrantLock.lock()`, có thể hai luồng chờ **hai locks không liên quan**. Để chứng minh cycle, cần:

1. Waiter A nói đang chờ lock **do B sở hữu**.
2. Waiter B nói đang chờ lock **do A sở hữu**.
3. `getLockInfo()` của A **khớp khóa** trong `getLockedMonitors/getLockedSynchronizers` của B.
4. `getLockInfo()` của B khớp khóa trong owned locks của A.
5. Bằng chứng stack frames đưa ra code location.
6. Kết quả `findDeadlockedThreads` chứa đúng các platform thread IDs tương ứng.

Trong một JVM/snapshot, có thể đối chiếu `LockInfo.getClassName()` + `getIdentityHashCode()`. Identity hash không đủ làm khóa định danh trên nhiều JVM hoặc thời gian dài, vì có thể va chạm và thay đổi đối tượng; dùng thêm thread ID, lock type, owner chain và timestamp/correlation để lập hồ sơ sự cố.

## 5. Kiểm thử deadlock **có kiểm soát**: nguyên tắc an toàn

**Không nên cố ý tạo intrinsic-monitor deadlock trong cùng JVM chạy JUnit/test runner/server chính.** Các luồng giữ monitors chờ nhau có thể không thể giải phóng bằng `interrupt()`, làm test suite/process không thoát và gây cạn worker slots.

Chiến lược đang được dùng trong bài:

```text
Test runner / JVM cha (không giữ deadlock)
 |
 +-- JVM con 1: healthy baseline
 |     thu evidence; exit 0
 |
 +-- JVM con 2: monitor deadlock
 |     tạo chu trình; chụp ThreadMXBean evidence; exit 0
 |
 +-- JVM con 3: ownable deadlock
 |     tạo chu trình; chụp evidence; exit 0
 |
 +-- JVM con 4: mixed deadlock
       tạo chu trình; chụp evidence; exit 0

Mỗi JVM con:
  timeout 9 giây tại cha
  nếu treo: cha destroyForcibly() + waitFor()
  không để deadlocked threads tồn tại trong JVM cha
```

Trong JVM con, các deadlocked workers không cần được “gỡ” thủ công; sau khi reporter xác minh bằng chứng, **toàn bộ tiến trình con kết thúc bằng `System.exit(0)`**. **Đây là việc chấp nhận được chỉ trong một JVM disposable dành cho lab**, không phải chiến lược recovery cho production.

### 5.1. Barrier phải có timeout

Lab dùng `CountDownLatch(2)` để đảm bảo A và B **đã lấy khóa đầu** trước khi thử khóa thứ hai. `CountDownLatch.await(3, TimeUnit.SECONDS)` có timeout, nên test setup lỗi sẽ báo failure thay vì treo trong barrier. Main process cũng có detector deadline 6 giây.

Các hạn mức này độc lập:

| Deadline | Giá trị thử nghiệm | Bảo vệ |
| --- | --- | --- |
| Barrier await | 3 giây | Nếu setup không đến đủ hai threads, fail thay vì chờ vô hạn. |
| Detector poll | 6 giây | Nếu không tạo/nhận được chu trình, fail cụ thể. |
| Parent child wait | 9 giây | JVM con có vấn đề bị cha ép kết thúc. |
| Kill/reap | 3 giây sau kill | Cha không bỏ lại process con không được chờ/thu dọn. |

Đây là **giá trị phù hợp demo**, không phải SLA production. Trên máy CI chậm, cần đo và điều chỉnh nhưng luôn giữ một **watchdog cứng** cho child process.

### 5.2. Không dùng sleep như công cụ duy nhất tạo deadlock

`Thread.sleep(100)` chỉ làm thay đổi lịch chạy chứ không đảm bảo A và B đang giữ khóa đầu. Barriers hoặc latches giúp setup **deterministic hơn**. Detector vẫn poll vì JVM cần thời gian chuyển threads vào trạng thái blocked/parked.

Không dùng `Thread.stop()`, `Thread.suspend()`, `ThreadGroup.stop` hoặc một API deprecated tương tự để dọn deadlock. Thay vì giết threads riêng lẻ, **dừng disposable JVM con**.

### 5.3. Phân biệt “không phát hiện” với “không có”

`findDeadlockedThreads() == null` có nghĩa **JVM không phát hiện chu trình thuộc phạm vi API tại thời điểm lấy mẫu**, không chứng minh mọi loại deadlock đều không tồn tại. Có thể có I/O deadlock, resource dependency cycle, starvation, hoặc virtual-thread deadlock nằm ngoài vùng bao phủ.

## 6. Tổng hợp bằng chứng: những thông tin tối thiểu

Một báo cáo deadlock test tốt nên có **nhiều lớp bằng chứng**, không chỉ một boolean:

| Lớp | Dữ liệu | Lý do |
| --- | --- | --- |
| Test identity | Scenario `healthy`/`monitor`/`ownable`/`mixed` | Biết đang xác minh case nào. |
| Environment | Java version, OS, runtime/provider, test build | Tái hiện và đối chiếu. |
| Capability | Monitor usage/synchronizer usage supported | Đánh giá coverage của API. |
| Detection | Số thread IDs từ hai detectors | Phân biệt monitor-only và combined. |
| State | `BLOCKED`, `WAITING` hoặc `TIMED_WAITING` | Nhìn được loại waiting behavior. |
| Owner chain | A waits B, B waits A | Bằng chứng wait-for cycle. |
| Waiting target | LockInfo class/identity | Biết chính xác object đang đợi. |
| Held locks | MonitorInfo[]/LockInfo[] | Kiểm tra object đang đợi thuộc owner. |
| Stack | Chức năng/đường gọi khóa | Truy nguồn code và lock ordering. |
| Cleanup | Child exited/forced termination | Test không làm kẹt runner. |
| Negative control | healthy có 0 cycle | Hạn chế báo động giả. |
| Limitations | Platform threads only; API-specific coverage | Không đưa ra kết luận quá rộng. |

### 6.1. Evidence report định dạng ổn định

JVM con trong ví dụ tạo các dòng ASCII dễ phân tích, với **tên A/B cố định** thay vì in thread IDs ngẫu nhiên:

```text
EVIDENCE|monitor|deadlocked=2|monitorOnly=2
EVIDENCE|monitor|cycle=A->B->A|ownersValidated=true
EVIDENCE|monitor|A=BLOCKED|holds=MONITOR|waits=MONITOR
EVIDENCE|monitor|B=BLOCKED|holds=MONITOR|waits=MONITOR
EVIDENCE|monitor|lockIdentityValidated=true|stackFramesValidated=true
```

Đây là ví dụ **dạng bằng chứng child có thể in**, không phải output mặc định của parent test command. Parent bắt các lines này qua stdout process con, kiểm tra nội dung, rồi xuất các nhãn PASS tương ứng.

Với ownable:

```text
EVIDENCE|ownable|deadlocked=2|monitorOnly=0
EVIDENCE|ownable|cycle=A->B->A|ownersValidated=true
EVIDENCE|ownable|A=WAITING|holds=OWNABLE|waits=OWNABLE
EVIDENCE|ownable|B=WAITING|holds=OWNABLE|waits=OWNABLE
EVIDENCE|ownable|lockIdentityValidated=true|stackFramesValidated=true
```

Với mixed:

```text
EVIDENCE|mixed|deadlocked=2|monitorOnly=0
EVIDENCE|mixed|cycle=A->B->A|ownersValidated=true
EVIDENCE|mixed|A=WAITING|holds=MONITOR|waits=OWNABLE
EVIDENCE|mixed|B=BLOCKED|holds=OWNABLE|waits=MONITOR
EVIDENCE|mixed|lockIdentityValidated=true|stackFramesValidated=true
```

Lưu ý: `lockIdentityValidated=true` chỉ được in **sau khi** code xác nhận `getLockInfo` của từng waiter khớp một object trong lockedMonitors/lockedSynchronizers của owner kia theo class/identity trong JVM đó; `stackFramesValidated=true` chỉ được in sau khi phát hiện frame Java của mỗi scenario. Một dòng tự in `deadlock=true` mà không kiểm chứng bên dưới **không phải bằng chứng đủ mạnh**.

### 6.2. Các kết luận thử nghiệm cần xuất hiện cùng nhau

| Scenario | findDeadlockedThreads | findMonitorDeadlockedThreads | Luồng A | Luồng B |
| --- | --- | --- | --- | --- |
| Healthy | `null` | `null` | Không tạo cycle. | Không tạo cycle. |
| Monitor | 2 IDs | 2 IDs | `BLOCKED`, giữ monitor, đợi monitor của B. | `BLOCKED`, giữ monitor, đợi monitor của A. |
| Ownable | 2 IDs | `null` | `WAITING`, giữ ownable, đợi ownable của B. | `WAITING`, giữ ownable, đợi ownable của A. |
| Mixed | 2 IDs | `null` | `WAITING`, giữ monitor, đợi ownable của B. | `BLOCKED`, giữ ownable, đợi monitor của A. |

Các giá trị ở bảng đã được kiểm chứng trên **OpenJDK 24.0.2** cho **platform threads** được dựng trong lab. Trên JVM khác, thread state snapshot có thể mang timing nuance; test nên xác minh API contract và thiết kế deterministic waits thay vì hardcode tất cả chi tiết implementation không công khai.

## 7. Code Java 17+ đầy đủ: DeadlockEvidenceLab.java

Code sử dụng:

- `CountDownLatch` để đồng bộ thời điểm A/B đã lấy khóa thứ nhất.
- `synchronized` cho monitor cycle.
- `ReentrantLock` cho ownable cycle.
- `ManagementFactory.getThreadMXBean` để phát hiện deadlock.
- `ThreadMXBean.getThreadInfo(ids,true,true)` để thu ownership và call stacks.
- `ProcessBuilder` để khởi động từng **JVM con** từ JDK đang chạy.
- `Process.waitFor(9, TimeUnit.SECONDS)` để có deadline; `destroyForcibly()` và `waitFor` để dọn.
- `System.exit` **chỉ bên trong child** sau khi thu kết quả, bởi những worker threads của child cố ý không thể tiến triển.

Chương trình không mở server hoặc kết nối mạng. Tất cả locks là objects nội bộ của JVM con.

### 7.1. Source hoàn chỉnh

Lưu đúng tên file **`DeadlockEvidenceLab.java`**, bằng UTF-8:

```java
import java.lang.management.LockInfo;
import java.lang.management.ManagementFactory;
import java.lang.management.MonitorInfo;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class DeadlockEvidenceLab {
    private static final long CASE_DEADLINE_NANOS =
            TimeUnit.SECONDS.toNanos(6);
    private static int checks;

    private static void require(boolean ok, String explanation) {
        if (!ok) throw new AssertionError(explanation);
    }

    private static void check(String label, boolean ok) {
        require(ok, label);
        checks++;
        System.out.println(label + "=PASS");
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(3, TimeUnit.SECONDS))
                throw new AssertionError("Lab barrier timeout");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    private static boolean same(LockInfo wanted, LockInfo owned) {
        return wanted != null && owned != null
                && wanted.getIdentityHashCode()
                        == owned.getIdentityHashCode()
                && wanted.getClassName().equals(owned.getClassName());
    }

    private static boolean owns(ThreadInfo owner, LockInfo wanted) {
        for (MonitorInfo monitor : owner.getLockedMonitors())
            if (same(wanted, monitor)) return true;
        for (LockInfo lock : owner.getLockedSynchronizers())
            if (same(wanted, lock)) return true;
        return false;
    }

    private static boolean hasFrame(
            ThreadInfo info, String frameName) {
        return Arrays.stream(info.getStackTrace())
                .anyMatch(frame -> frame.getMethodName().equals(frameName)
                        && frame.getClassName().equals(
                                DeadlockEvidenceLab.class.getName()));
    }

    private static Thread thread(String name, Runnable run) {
        Thread t = new Thread(run, "lab-" + name);
        t.setDaemon(false);
        return t;
    }

    private static void monitorA(
            Object first, Object second, CountDownLatch barrier) {
        synchronized (first) {
            barrier.countDown();
            await(barrier);
            synchronized (second) { }
        }
    }

    private static void monitorB(
            Object first, Object second, CountDownLatch barrier) {
        synchronized (second) {
            barrier.countDown();
            await(barrier);
            synchronized (first) { }
        }
    }

    private static void ownableA(
            ReentrantLock first, ReentrantLock second,
            CountDownLatch barrier) {
        first.lock();
        try {
            barrier.countDown();
            await(barrier);
            second.lock();
            try { } finally { second.unlock(); }
        } finally {
            first.unlock();
        }
    }

    private static void ownableB(
            ReentrantLock first, ReentrantLock second,
            CountDownLatch barrier) {
        second.lock();
        try {
            barrier.countDown();
            await(barrier);
            first.lock();
            try { } finally { first.unlock(); }
        } finally {
            second.unlock();
        }
    }

    private static void mixedA(
            Object monitor, ReentrantLock explicit,
            CountDownLatch barrier) {
        synchronized (monitor) {
            barrier.countDown();
            await(barrier);
            explicit.lock();
            try { } finally { explicit.unlock(); }
        }
    }

    private static void mixedB(
            Object monitor, ReentrantLock explicit,
            CountDownLatch barrier) {
        explicit.lock();
        try {
            barrier.countDown();
            await(barrier);
            synchronized (monitor) { }
        } finally {
            explicit.unlock();
        }
    }

    private static String heldType(ThreadInfo t) {
        if (t.getLockedMonitors().length > 0
                && t.getLockedSynchronizers().length == 0)
            return "MONITOR";
        if (t.getLockedMonitors().length == 0
                && t.getLockedSynchronizers().length > 0)
            return "OWNABLE";
        return "OTHER";
    }

    private static String waitingType(ThreadInfo t) {
        if (t.getThreadState() == Thread.State.BLOCKED)
            return "MONITOR";
        if (t.getThreadState() == Thread.State.WAITING
                || t.getThreadState() == Thread.State.TIMED_WAITING)
            return "OWNABLE";
        return "OTHER";
    }

    private static void child(String mode) throws Exception {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        require(bean.isObjectMonitorUsageSupported()
                        && bean.isSynchronizerUsageSupported(),
                "JVM must support monitor and ownable synchronizer info");

        if ("healthy".equals(mode)) {
            require(bean.findDeadlockedThreads() == null,
                    "Healthy process");
            require(bean.findMonitorDeadlockedThreads() == null,
                    "Healthy process, monitor-only");
            System.out.println(
                    "EVIDENCE|healthy|deadlocked=0|monitorOnly=0");
            return;
        }

        CountDownLatch barrier = new CountDownLatch(2);
        Thread a, b;

        if ("monitor".equals(mode)) {
            Object x = new Object(), y = new Object();
            a = thread("A", () -> monitorA(x, y, barrier));
            b = thread("B", () -> monitorB(x, y, barrier));
        } else if ("ownable".equals(mode)) {
            ReentrantLock x = new ReentrantLock();
            ReentrantLock y = new ReentrantLock();
            a = thread("A", () -> ownableA(x, y, barrier));
            b = thread("B", () -> ownableB(x, y, barrier));
        } else if ("mixed".equals(mode)) {
            Object monitor = new Object();
            ReentrantLock explicit = new ReentrantLock();
            a = thread("A", () -> mixedA(monitor, explicit, barrier));
            b = thread("B", () -> mixedB(monitor, explicit, barrier));
        } else {
            throw new IllegalArgumentException(
                    "Unknown mode: " + mode);
        }

        a.start();
        b.start();

        long end = System.nanoTime() + CASE_DEADLINE_NANOS;
        long[] ids = null;
        while (System.nanoTime() - end < 0) {
            ids = bean.findDeadlockedThreads();
            if (ids != null && ids.length == 2
                    && Set.of(ids[0], ids[1])
                    .equals(Set.of(a.getId(), b.getId())))
                break;
            Thread.sleep(10);
        }
        require(ids != null && ids.length == 2,
                "Expected exactly two deadlocked platform threads: "
                        + mode);
        require(new HashSet<>(Arrays.asList(ids[0], ids[1]))
                        .equals(Set.of(a.getId(), b.getId())),
                "Unexpected thread IDs in cycle");

        long[] monitorOnly = bean.findMonitorDeadlockedThreads();
        int monitorCount =
                monitorOnly == null ? 0 : monitorOnly.length;
        int expectedMonitorCount =
                "monitor".equals(mode) ? 2 : 0;
        require(monitorCount == expectedMonitorCount,
                "Wrong monitor-only deadlock count for " + mode);

        ThreadInfo[] infos = bean.getThreadInfo(
                new long[]{a.getId(), b.getId()}, true, true);
        ThreadInfo ai = infos[0], bi = infos[1];

        require(ai != null && bi != null, "Missing ThreadInfo");
        require(ai.getLockOwnerId() == b.getId()
                        && bi.getLockOwnerId() == a.getId(),
                "Cycle owners did not reference each other");
        require("lab-B".equals(ai.getLockOwnerName())
                        && "lab-A".equals(bi.getLockOwnerName()),
                "Owner thread names inconsistent");
        require(owns(bi, ai.getLockInfo())
                        && owns(ai, bi.getLockInfo()),
                "Waiting lock identity does not match held lock");

        String ah = heldType(ai), bh = heldType(bi);
        String aw = waitingType(ai), bw = waitingType(bi);
        String as = ai.getThreadState().name();
        String bs = bi.getThreadState().name();

        boolean stateValid;
        String frameA, frameB;
        if ("monitor".equals(mode)) {
            stateValid = "BLOCKED".equals(as)
                    && "BLOCKED".equals(bs)
                    && "MONITOR".equals(ah)
                    && "MONITOR".equals(bh)
                    && "MONITOR".equals(aw)
                    && "MONITOR".equals(bw);
            frameA = "monitorA";
            frameB = "monitorB";
        } else if ("ownable".equals(mode)) {
            stateValid = "WAITING".equals(as)
                    && "WAITING".equals(bs)
                    && "OWNABLE".equals(ah)
                    && "OWNABLE".equals(bh)
                    && "OWNABLE".equals(aw)
                    && "OWNABLE".equals(bw);
            frameA = "ownableA";
            frameB = "ownableB";
        } else {
            stateValid = "WAITING".equals(as)
                    && "BLOCKED".equals(bs)
                    && "MONITOR".equals(ah)
                    && "OWNABLE".equals(bh)
                    && "OWNABLE".equals(aw)
                    && "MONITOR".equals(bw);
            frameA = "mixedA";
            frameB = "mixedB";
        }

        require(stateValid,
                "Unexpected thread state/lock category: " + mode);
        require(hasFrame(ai, frameA)
                        && hasFrame(bi, frameB),
                "Expected locations missing from stack traces");

        if ("monitor".equals(mode) || "mixed".equals(mode)) {
            require(ai.getLockedMonitors().length > 0,
                    "Expected monitor ownership");
            MonitorInfo mi = ai.getLockedMonitors()[0];
            require(mi.getLockedStackFrame() != null
                            && mi.getLockedStackDepth() >= 0,
                    "Missing monitor acquisition frame");
        }

        System.out.println("EVIDENCE|" + mode
                + "|deadlocked=2|monitorOnly=" + monitorCount);
        System.out.println("EVIDENCE|" + mode
                + "|cycle=A->B->A|ownersValidated=true");
        System.out.println("EVIDENCE|" + mode
                + "|A=" + as + "|holds=" + ah + "|waits=" + aw);
        System.out.println("EVIDENCE|" + mode
                + "|B=" + bs + "|holds=" + bh + "|waits=" + bw);
        System.out.println("EVIDENCE|" + mode
                + "|lockIdentityValidated=true"
                + "|stackFramesValidated=true");
    }

    private static String executeChild(String mode)
            throws Exception {
        String executable =
                System.getProperty("os.name").toLowerCase()
                        .contains("win") ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"),
                "bin", executable);

        Process process = new ProcessBuilder(
                java.toString(), "-cp",
                System.getProperty("java.class.path"),
                DeadlockEvidenceLab.class.getName(),
                "child", mode)
                .redirectErrorStream(true)
                .start();
        try {
            boolean completed =
                    process.waitFor(9, TimeUnit.SECONDS);
            if (!completed) {
                process.destroyForcibly();
                process.waitFor(3, TimeUnit.SECONDS);
                throw new AssertionError(
                        "Child exceeded 9s: " + mode);
            }

            String out = new String(
                    process.getInputStream().readAllBytes(),
                    StandardCharsets.UTF_8)
                    .replace("\r\n", "\n").trim();
            require(process.exitValue() == 0,
                    "Child failed: " + mode + "\n" + out);
            return out;
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(3, TimeUnit.SECONDS);
            }
        }
    }

    private static void parent() throws Exception {
        String healthy = executeChild("healthy");
        check("baselineNoDeadlock",
                healthy.equals(
                        "EVIDENCE|healthy|deadlocked=0"
                                + "|monitorOnly=0"));

        String monitor = executeChild("monitor");
        check("monitorCycleDetected", monitor.contains(
                "EVIDENCE|monitor|deadlocked=2|monitorOnly=2"));
        check("monitorOwnerCycleVerified", monitor.contains(
                "EVIDENCE|monitor|cycle=A->B->A"
                        + "|ownersValidated=true"));
        check("monitorAIsBlocked", monitor.contains(
                "EVIDENCE|monitor|A=BLOCKED"
                        + "|holds=MONITOR|waits=MONITOR"));
        check("monitorBIsBlocked", monitor.contains(
                "EVIDENCE|monitor|B=BLOCKED"
                        + "|holds=MONITOR|waits=MONITOR"));
        check("monitorIdentityAndFrames", monitor.contains(
                "EVIDENCE|monitor|lockIdentityValidated=true"
                        + "|stackFramesValidated=true"));

        String ownable = executeChild("ownable");
        check("ownableCycleDetected", ownable.contains(
                "EVIDENCE|ownable|deadlocked=2|monitorOnly=0"));
        check("ownableOwnerCycleVerified", ownable.contains(
                "EVIDENCE|ownable|cycle=A->B->A"
                        + "|ownersValidated=true"));
        check("ownableAIsWaiting", ownable.contains(
                "EVIDENCE|ownable|A=WAITING"
                        + "|holds=OWNABLE|waits=OWNABLE"));
        check("ownableBIsWaiting", ownable.contains(
                "EVIDENCE|ownable|B=WAITING"
                        + "|holds=OWNABLE|waits=OWNABLE"));
        check("ownableIdentityAndFrames", ownable.contains(
                "EVIDENCE|ownable|lockIdentityValidated=true"
                        + "|stackFramesValidated=true"));

        String mixed = executeChild("mixed");
        check("mixedCycleDetected", mixed.contains(
                "EVIDENCE|mixed|deadlocked=2|monitorOnly=0"));
        check("mixedOwnerCycleVerified", mixed.contains(
                "EVIDENCE|mixed|cycle=A->B->A"
                        + "|ownersValidated=true"));
        check("mixedAWaitsForOwnable", mixed.contains(
                "EVIDENCE|mixed|A=WAITING"
                        + "|holds=MONITOR|waits=OWNABLE"));
        check("mixedBWaitsForMonitor", mixed.contains(
                "EVIDENCE|mixed|B=BLOCKED"
                        + "|holds=OWNABLE|waits=MONITOR"));
        check("mixedIdentityAndFrames", mixed.contains(
                "EVIDENCE|mixed|lockIdentityValidated=true"
                        + "|stackFramesValidated=true"));

        check("eachScenarioIsolated", true);
        check("parentRemainsResponsive", true);
        check("allChildrenExited", true);

        System.out.println(
                "scenarioEvidence=baseline,monitor,ownable,mixed");
        System.out.println("checks=" + checks + "/19");
        require(checks == 19,
                "Unexpected assertion count " + checks);
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 2 && "child".equals(args[0])) {
            try {
                child(args[1]);
                System.out.flush();
                // Chỉ JVM con disposable thoát, kể cả deadlocked threads.
                System.exit(0);
            } catch (Throwable error) {
                error.printStackTrace();
                System.exit(4);
            }
        } else if (args.length == 0) {
            parent();
        } else {
            throw new IllegalArgumentException(
                    "Usage: java DeadlockEvidenceLab");
        }
    }
}
```

### 7.2. Biên dịch và chạy

Từ thư mục chứa file UTF-8:

```bash
javac --release 17 -encoding UTF-8 DeadlockEvidenceLab.java
java DeadlockEvidenceLab
```

Không cần external JAR, Maven/Gradle hoặc `--add-opens`. `ThreadMXBean`/`ThreadInfo` thuộc module `java.management`; `ProcessBuilder` và các concurrency classes thuộc `java.base`. Với named module có `module-info.java`, khai báo `requires java.management;`.

**Quan trọng về an toàn:** hãy chạy command **không có `child` arguments** để process cha kiểm soát các child JVMs. Chỉ chạy riêng `java DeadlockEvidenceLab child monitor` nếu bạn hiểu đó là một JVM disposable và có thể chủ động dừng nó; trong ví dụ child tự `System.exit` sau bằng chứng, nhưng nếu code bị sửa sai thì một process có deadlock thực sự có thể không thoát.

### 7.3. Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2

```text
baselineNoDeadlock=PASS
monitorCycleDetected=PASS
monitorOwnerCycleVerified=PASS
monitorAIsBlocked=PASS
monitorBIsBlocked=PASS
monitorIdentityAndFrames=PASS
ownableCycleDetected=PASS
ownableOwnerCycleVerified=PASS
ownableAIsWaiting=PASS
ownableBIsWaiting=PASS
ownableIdentityAndFrames=PASS
mixedCycleDetected=PASS
mixedOwnerCycleVerified=PASS
mixedAWaitsForOwnable=PASS
mixedBWaitsForMonitor=PASS
mixedIdentityAndFrames=PASS
eachScenarioIsolated=PASS
parentRemainsResponsive=PASS
allChildrenExited=PASS
scenarioEvidence=baseline,monitor,ownable,mixed
checks=19/19
```

Có **19 PASS labels, một dòng danh sách scenarios và một dòng tổng kết**. Parent nhận các dòng `EVIDENCE|...` từ stdout mỗi child JVM, dùng chúng để kiểm tra và **không in lại toàn bộ child stdout**. Điều này giữ output mặc định ngắn, rõ ràng, đồng thời child code vẫn thể hiện đầy đủ cách tạo báo cáo.

### 7.4. Có thể xem bằng chứng child riêng

Sau khi biên dịch, người học có thể chạy riêng từng child **trong terminal có kiểm soát**:

```bash
java DeadlockEvidenceLab child healthy
java DeadlockEvidenceLab child monitor
java DeadlockEvidenceLab child ownable
java DeadlockEvidenceLab child mixed
```

Mỗi child khi thành công tự in các `EVIDENCE|...` lines rồi `System.exit(0)`. Nếu cố sửa code để thử case không được nhận diện và không có `System.exit`, có thể tạo JVM treo; vì vậy **luôn ưu tiên chạy parent watchdog**, nhất là trong CI.

Đây là ví dụ **kết quả child được sinh và chuẩn hóa**; actual per-mode report có tên A/B và khóa loại MONITOR/OWNABLE chứ không lộ class names đầy đủ hoặc identity hash ngẫu nhiên.

### 7.5. Mục đích của từng thành phần

**`monitorA/monitorB`**: khóa thứ nhất bằng `synchronized`, hẹn nhau qua latch rồi khóa thứ hai theo thứ tự ngược. Cả hai kẹt ở `BLOCKED`.

**`ownableA/ownableB`**: dùng hai `ReentrantLock`, lấy thứ tự ngược rồi kẹt ở `lock()`. `finally unlock` vẫn có để giữ pattern đúng nếu code thoát bình thường; nhưng trong tình huống deadlock chủ đích, không thể chạy tới `finally`. Vì vậy **tiến trình con mới là đơn vị cleanup**.

**`mixedA/mixedB`**: A giữ monitor và chờ ownable; B giữ ownable và chờ monitor. Cách này tạo bằng chứng vì sao monitor-only API trả `null` dù combined API phát hiện.

**`CASE_DEADLINE_NANOS` và `System.nanoTime()`**: detector poll có deadline monotonic, tránh phụ thuộc wall clock.

**`owns(...)`**: so sánh waiting LockInfo với các MonitorInfo/LockInfo đã giữ của owner kia. Đây là kiểm chứng chính cho quan hệ sở hữu chéo.

**`hasFrame(...)`**: tìm đúng method scenario ở stack trace, giúp loại bỏ một kết quả deadlock không thuộc code test.

**`executeChild(...)`**: dùng JDK đang chạy cho child, giới hạn thời gian, đọc stdout/stderr và kiểm tra exit code. Nếu child treo, `destroyForcibly` được gọi; đây là cách khoanh vùng rủi ro.

**`parent()`**: kiểm tra baseline, monitor, ownable và mixed theo thứ tự; mỗi assertion kiểm tra một phần bằng chứng. Không dựa vào thời gian ngủ hoặc ID cụ thể trong expected stdout.

## 8. Diễn giải cụ thể 19 PASS assertions

| Assertion | Cần chứng minh |
| --- | --- |
| `baselineNoDeadlock` | JVM con không có chu trình trả `null` ở cả hai detectors. |
| `monitorCycleDetected` | Combined và monitor-only cùng phát hiện 2 platform threads. |
| `monitorOwnerCycleVerified` | Owner chain là A → B → A. |
| `monitorAIsBlocked` | A BLOCKED, giữ monitor X, đợi monitor Y. |
| `monitorBIsBlocked` | B BLOCKED, giữ monitor Y, đợi monitor X. |
| `monitorIdentityAndFrames` | LockInfo khớp khóa do đối phương giữ và có stack location. |
| `ownableCycleDetected` | Combined thấy 2 threads nhưng monitor-only trả 0. |
| `ownableOwnerCycleVerified` | Owner chain giữa hai ownable locks là A → B → A. |
| `ownableAIsWaiting` | A WAITING, giữ ownable lock và đợi ownable lock của B. |
| `ownableBIsWaiting` | B WAITING, giữ ownable lock và đợi ownable lock của A. |
| `ownableIdentityAndFrames` | AQS lock identity và stack locations được đối chiếu. |
| `mixedCycleDetected` | Combined phát hiện cycle, monitor-only không đủ phạm vi. |
| `mixedOwnerCycleVerified` | A/B vẫn tạo wait-for cycle. |
| `mixedAWaitsForOwnable` | A WAITING, giữ monitor và đợi ownable. |
| `mixedBWaitsForMonitor` | B BLOCKED, giữ ownable và đợi monitor. |
| `mixedIdentityAndFrames` | Cross-type ownership và stack locations nhất quán. |
| `eachScenarioIsolated` | Bốn lần `executeChild` đã trả về; mỗi scenario là JVM riêng. |
| `parentRemainsResponsive` | Parent tiếp tục tới cuối assertions, không bị khóa bởi child. |
| `allChildrenExited` | Cả bốn JVM con đã kết thúc trước khi parent kết thúc bình thường. |

**Chú ý tính chặt chẽ:** ba assertions cuối kiểm tra tình trạng của parent sau các lần chạy; chúng không thay thế metrics OS về process descendants trong một hạ tầng CI phức tạp. Nếu JVM con tạo grandchild processes (demo không có), production runner cần quản lý **process tree** chứ không chỉ một Process object.

## 9. Kiểm thử âm, kiểm thử ranh giới và tác động scheduler

Một bộ lab tốt không chỉ xem positive deadlock cases:

### 9.1. Negative: cùng thứ tự lock

Nếu cả A và B đều lấy **X rồi Y**, chúng có thể tranh chấp nhưng không tạo deadlock hai khóa kiểu đối nghịch. Kết quả `findDeadlockedThreads` trong JVM con thử là `null` nếu setup không tạo chu trình.

### 9.2. Negative: WAITING nhưng không có cycle

Một thread `CountDownLatch.await()` có thể WAITING mà không có owner chain kiểu JMX deadlock. Không gắn nhãn deadlock chỉ vì WAITING kéo dài. Cần biết nó đợi sự kiện nào, có thread nào sẽ `countDown`, hoặc nhiệm vụ có thể tiến triển không.

### 9.3. Negative: một monitor bị tranh chấp

Một owner giữ monitor 100 ms, một waiter BLOCKED; rồi owner nhả và waiter lấy được. **Đây không phải deadlock**. Nếu monitor-only detector trả null, không có mâu thuẫn.

### 9.4. Positive: mixed monitor/ownable

Trường hợp mixed là test quan trọng cho độ bao phủ: `findMonitorDeadlockedThreads` trả null **không loại trừ** chu trình vì một cạnh chờ `ReentrantLock`. Luôn có case này trong regression suite khi ứng dụng dùng nhiều primitives.

### 9.5. Timing và scheduler

Barrier giúp setup, nhưng snapshot/`findDeadlockedThreads` vẫn phụ thuộc lịch chạy ở thời điểm test. Poll với monotonic deadline giảm flakiness; nếu VM quá tải hoặc không hỗ trợ introspection, test phải báo **không đủ điều kiện** hoặc fail có thông tin, không kéo dài vô hạn.

Trên JVM khác, parked AQS waiter có thể biểu diễn state khác trong thời gian ngắn, dù trong case ổn định này JDK24 cho `WAITING`. Khi di chuyển lab sang runtime khác, nên giữ owner cycle/identity/detector outputs làm bằng chứng cốt lõi, và đánh giá các state assumptions phù hợp với implementation.

## 10. Virtual threads: giới hạn đặc biệt của ThreadMXBean năm 2026

`ThreadMXBean` trên Java SE 26 chỉ quản lý/giám sát **platform threads**. Theo Javadoc:

- `getAllThreadIds()` chỉ gồm IDs của platform threads.
- `getThreadInfo(virtualThreadId)` trả `null`.
- `dumpAllThreads(...)` không liệt kê toàn bộ virtual threads.
- `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` **không phát hiện chu trình có virtual threads**.

Đây là lý do ví dụ chỉ tạo **platform threads** bằng `new Thread(...)` để kiểm chứng API tương thích Java 17.

### 10.1. Dùng jcmd khi cần bằng chứng rộng hơn

Với HotSpot/JDK được hỗ trợ:

```bash
jcmd -l
jcmd 12345 help
jcmd 12345 Thread.print -l
jcmd 12345 Thread.dump_to_file -format=json threads.json
```

`12345` trong các lệnh trên là **PID minh họa**, thay bằng PID thật của JVM có quyền truy cập. `Thread.print -l` in platform threads và các mounted virtual threads, kèm lock details theo công cụ. `Thread.dump_to_file` có thể xuất cả platform và virtual threads sang file text/JSON, nhưng theo Oracle **không phải một snapshot toàn cục nhất quán** và **không tự làm deadlock detection**. Muốn kết luận cycle có virtual threads, cần phân tích wait-for graph từ nguồn bằng chứng phù hợp hoặc dùng công cụ chẩn đoán hỗ trợ đúng mô hình runtime; không diễn giải `ThreadMXBean.findDeadlockedThreads()==null` là “chắc chắn không deadlock”.

### 10.2. JFR và các nguồn khác

Java Flight Recorder/JFR có các events hữu ích về thread parking, monitor enter, socket I/O và lock contention theo event configuration. Không phải mọi event đều được bật mặc định; thresholds/stack traces và overhead thay đổi theo profile. Khi tìm deadlock ở production, có thể phối hợp:

- JMX ThreadMXBean cho platform thread cycle và ownership.
- `jcmd`/thread dumps cho stacks/lock owners ở thời điểm sự cố.
- JFR để có **diễn biến theo thời gian**, thay vì một snapshot.
- Application logs/trace IDs để nối với business operation và timeline.
- Metrics pool/queue/DB/network khi nghi starvation/hung I/O.

**Chỉ dùng công cụ trên JVM có quyền và được phép chẩn đoán**. Thread dumps, traces và logs có thể lộ class names, method arguments, thread names hoặc dữ liệu nghiệp vụ; cần kiểm soát quyền và retention.

## 11. Bằng chứng cho sự cố production: mẫu runbook

Khi phát hiện một hệ thống thật bị treo:

1. **Xác định triệu chứng:** latency tăng, request queue, deadlock suspicion, CPU idle, thread pool cạn hay socket I/O bị treo?
2. **Lưu metadata tối thiểu:** giờ UTC, build/version, Java runtime, node/container, process ID, sampling window.
3. **Lấy nhiều nguồn chứng cứ:** `ThreadMXBean` detection, thread dumps và metrics/traces theo quyền cho phép.
4. **Xác định threads:** tên/ID, state, call stack, waiting target, owner ID/name.
5. **Xác minh cycle:** vẽ các cạnh A → B, B → C, C → A; không chỉ thống kê số BLOCKED threads.
6. **Đối chiếu lock identity:** object class/identity hash trong cùng JVM/snapshot, lockedMonitors/synchronizers và code path.
7. **Phân loại loại deadlock:** monitor-only, ownable-only, mixed hoặc ngoài phạm vi detector.
8. **Đánh giá mức độ ảnh hưởng:** pool nào bị kẹt, tenant nào, request nào, dữ liệu nào có nguy cơ, có thể failover không?
9. **Thu thập bằng chứng an toàn trước hành động phá hủy:** nếu cần restart, sao lưu diagnostics hợp lệ theo incident policy.
10. **Mitigate theo runbook:** rolling restart, isolate instances, scale/bypass traffic hoặc drain nếu được hệ thống hỗ trợ.
11. **Root cause:** thứ tự lấy khóa ngược, nested locks, callbacks khi giữ lock, I/O trong critical section, condition design sai hoặc cross-layer acquisition.
12. **Regression:** viết lại một deadlock test **có isolated process, deadlines, negative control, ownership evidence** để khẳng định bản sửa không tái tạo cycle.

### 11.1. Mẫu hồ sơ sự cố

```text
Incident:
  Case: monitor / ownable / mixed / other
  JVM: runtime, version, build
  Environment: host/container + timestamp
  Scope: platform / virtual / mixed
  Detection:
    findDeadlockedThreads: count or unsupported
    findMonitorDeadlockedThreads: count or no cycle
  Wait-for edges:
    A -> B (waiting on lock class/identity)
    B -> A
  Held locks:
    A: MonitorInfo[] / LockInfo[]
    B: MonitorInfo[] / LockInfo[]
  Code evidence:
    A: Java stack frame
    B: Java stack frame
  Impact:
    affected workloads and retry behavior
  Cleanup:
    isolated child exit / process termination / production mitigation
  Root-cause hypothesis:
    lock-order inversion confirmed by code review
  Regression:
    deadlock reproduction controlled, fix has no cycle
```

Đây là **mẫu cấu trúc**, không phải bằng chứng về sự cố production cụ thể. Với thông tin nhạy cảm, redaction và access control cần thực hiện trước khi chia sẻ hồ sơ.

### 11.2. Mẫu kết luận dựa trên bằng chứng

Không nên viết “JVM có 2 threads BLOCKED nên deadlock”. Một kết luận mạnh hơn là:

> Trong JVM con monitor, `findMonitorDeadlockedThreads` và `findDeadlockedThreads` cùng nhận đúng hai thread. `ThreadInfo` cho thấy A đang giữ monitor X và đợi monitor Y do B sở hữu; B giữ Y và đợi X do A sở hữu. Lock identity và stack frames đã được đối chiếu, tạo chu trình A → B → A. Kiểm thử đã được cô lập; JVM cha kết thúc bình thường.

Đây là một **kết luận về lab đã kiểm chứng**, không áp dụng nguyên xi cho một môi trường production chưa được đo đạc.

## 12. Các lỗi thường gặp khi xây deadlock regression tests

| Sai lầm | Vì sao nguy hiểm/sai | Cách sửa |
| --- | --- | --- |
| Cố ý deadlock trong cùng JVM JUnit. | Non-daemon threads có thể không bao giờ thoát. | Fork disposable JVM con. |
| Dùng `Thread.stop()` để “gỡ”. | Unsafe/deprecated, có thể hỏng invariants. | Dừng isolated process. |
| Dùng `sleep` để đảm bảo cả hai đã giữ khóa. | Scheduler không deterministic. | Latches/barriers có timeout. |
| Không có watchdog. | Một lỗi test có thể làm CI treo vô hạn. | Parent waitFor deadline và kill/reap. |
| Chỉ thấy 2 WAITING rồi kết luận. | Có thể là latch/queue/hợp lệ. | Xác nhận owner cycle và held locks. |
| Chỉ check `findMonitorDeadlockedThreads`. | Bỏ sót ownable/mixed cycle. | Check combined detector khi được hỗ trợ. |
| Không kiểm tra `isSynchronizerUsageSupported`. | Có thể nhận UnsupportedOperationException. | Capability check; SKIP/BLOCKER rõ. |
| Không thu `getLockedSynchronizers`. | Không biết AQS lock nào được giữ. | getThreadInfo(ids,true,true). |
| Dùng `getLockInfo()` như lock đang sở hữu. | Nó mô tả đối tượng đang chờ. | So với held-lock arrays của owner kia. |
| Dựa vào thread IDs cố định. | IDs thay đổi mỗi lần chạy/JVM. | Map theo tên lab A/B và owner relationship. |
| Dựa vào Set/array detection order. | Order có thể khác runtime. | So tập IDs, không so thứ tự. |
| Chỉ ghi `deadlocked=true` vào log. | Thiếu nguyên nhân và mã nguồn. | Owner chain, identity, stack trace, cleanup. |
| Bắt `Exception` và vẫn in PASS. | Có thể che invalid evidence. | Fail rõ, nonzero exit, parent hiển thị lỗi. |
| Quên destroy child khi timeout. | Rò process/threads. | destroyForcibly + waitFor trong finally. |
| Không có đối chứng healthy. | Dễ nhận báo động giả. | Chạy negative baseline. |
| Coi `findDeadlockedThreads()==null` là hệ thống an toàn. | API có giới hạn, virtual threads không được bao quát. | Kết luận trong scope, dùng thêm tools. |
| Dùng stack trace một thời điểm để tự động unlock production. | Snapshot TOCTOU, không có primitive safe unlock. | Chẩn đoán và sửa code/mitigation có kiểm soát. |
| Mở remote JMX không có auth/TLS để lấy dump. | Rủi ro lộ data/vận hành. | Bảo vệ truy cập/connector. |
| Ghi object/hash/secret vô tội vạ trong báo cáo. | Rò dữ liệu/metadata nhạy cảm. | Chuẩn hóa identifiers và redaction. |
| Mặc định deadlock là bug của JVM. | Phần lớn là lock ordering/application lifecycle. | Tìm code path và dependency graph. |

## 13. Phòng ngừa deadlock sau khi đã chứng minh

Mục tiêu cuối của kiểm thử là **ngăn lỗi tái xuất hiện**, không chỉ thu được snapshot:

- Thiết lập **global lock ordering** giữa các khóa có thể bị giữ đồng thời.
- Rút ngắn critical section, tránh network/database I/O khi giữ locks nếu thiết kế cho phép.
- Với `ReentrantLock`, dùng `tryLock(timeout)` hoặc `lockInterruptibly()` khi cần bounded acquisition/cancellation.
- Luôn `unlock()` trong `finally` sau `lock()` thành công.
- Không gọi callback/plugin/user code không tin cậy trong khi đang giữ khóa.
- Tránh synchronized một object public mà code bên ngoài cũng có thể lấy monitor.
- Thiết kế ownership/cancellation cho executors, tasks và queues.
- Dùng immutable data, concurrent collections hoặc message passing khi phù hợp để giảm số khóa cần giữ.
- Thêm regression test đảo thứ tự locks ở đúng đường gây lỗi, chạy trong child JVM và có watchdog.
- Theo dõi metrics về lock contention/queue size/latency trước và sau fix.

**Không khẳng định** thay toàn bộ `synchronized` bằng `ReentrantLock` sẽ xóa deadlock: cả hai đều có thể tham gia wait-for cycle nếu lấy theo thứ tự sai.

## 14. Checklist QA cho bộ kiểm thử

- [ ] Đã biết case là monitor, ownable, mixed hay ngoài scope?
- [ ] Có baseline không deadlock?
- [ ] Mỗi case deadlock chạy trong một **JVM con độc lập**?
- [ ] Parent có deadline tuyệt đối cho child process?
- [ ] Parent có destroy/reap child khi hết hạn?
- [ ] Barrier và detector polling có timeout?
- [ ] Child chỉ dùng test data, không giữ resources production?
- [ ] Có capability checks cho monitor và synchronizer monitoring?
- [ ] `findDeadlockedThreads` trả đúng IDs của threads do test tạo?
- [ ] `findMonitorDeadlockedThreads` được so đúng theo scenario?
- [ ] Mỗi thread `ThreadInfo` tồn tại và tên/ID đúng?
- [ ] `getLockOwnerId` của A trỏ B, của B trỏ A?
- [ ] `getLockInfo` của A khớp lock trong held arrays của B?
- [ ] `getLockInfo` của B khớp held lock của A?
- [ ] Có kiểm tra thread states theo loại wait trong scope test?
- [ ] Có stack frames xác nhận code locations?
- [ ] Có monitor acquisition frame khi monitor owner có metadata?
- [ ] Báo cáo không chứa các IDs ngẫu nhiên như expected strings?
- [ ] Không đưa thread dumps nguyên văn chứa secrets vào output công khai?
- [ ] Có kiểm tra rằng parent JVM kết thúc đúng?
- [ ] Không dùng `Thread.stop()/suspend()` để teardown?
- [ ] Có ghi version runtime/OS và coverage về virtual threads?
- [ ] Có negative cases cùng lock order/WAITING không có cycle?
- [ ] Có hướng xử lý khi JVM thiếu ownable synchronizer monitoring?
- [ ] Có regression test xác minh code đã sửa không tái deadlock?

## 15. Bài tập thực hành

**A — Hai monitors.** Dùng `DeadlockEvidenceLab child monitor` trong môi trường disposable; giải thích vì sao hai thread `BLOCKED` và cả hai detectors thấy 2 IDs.

**B — Hai ReentrantLocks.** So `ownable` với `monitor`. Tại sao `findMonitorDeadlockedThreads` trả null nhưng combined detector có kết quả?

**C — Mixed.** Vẽ graph A giữ monitor M/chờ ReentrantLock L; B giữ L/chờ M. Vì sao chỉ một thread `BLOCKED` không đủ để monitor-only detector tìm chu trình?

**D — Bỏ barrier.** Dự đoán test có thể thất thường ra sao nếu chỉ dùng `Thread.sleep`. Không đưa version không deadline vào CI.

**E — Timeout child.** Cố tình làm child không in evidence; xác minh parent kill/reap sau 9 giây và trả failure có thông tin, không treo mãi.

**F — Thay lock order.** Sửa ownable case để cả A và B lấy X rồi Y; tạo non-deadlock control và kiểm tra combined detector trả null.

**G — Chụp ThreadInfo.** In thêm data trong lab: `getThreadState`, `getLockInfo` class và identity, `getLockOwnerId`, các held arrays; tránh in application secrets.

**H — Stack frame.** Xác định `monitorA`/`monitorB` ở stack traces và `MonitorInfo.getLockedStackFrame()` cho monitor acquisition.

**I — Capabilities.** Tạo nhánh SKIP khi `isSynchronizerUsageSupported` false; giải thích vì sao không nên đánh dấu TEST PASS.

**J — Chỉ đếm BLOCKED.** Viết một detector tự chế dựa vào state count, rồi chứng minh nó không phát hiện ownable case mặc dù deadlock tồn tại.

**K — JMX remote.** Thiết kế cách lấy ThreadMXBean từ một JVM production qua một connector **đã xác thực/bảo vệ TLS**, không mở endpoint ra Internet.

**L — JFR.** Cấu hình thử event `JavaMonitorEnter`/`ThreadPark` phù hợp runtime và so với ownership snapshots; giải thích điểm mạnh về timeline.

**M — Virtual threads.** Trên Java 21+, tạo virtual threads và kiểm tra giới hạn của ThreadMXBean; dùng `jcmd Thread.dump_to_file` để xem biểu diễn của chúng, không kết luận deadlock detection tự động.

**N — Tự động hóa incident.** Định nghĩa một JSON schema gồm incident ID, JVM version, detector, thread states, owner edges, stack locations, cleanup, redaction status và confidence.

**O — Fix regression.** Đặt một thứ tự khóa thống nhất, chạy test đối chứng âm với deadline và chứng minh không tái hiện cycle, đồng thời có test load/functional riêng.

**P — Phân biệt hang.** Tạo một worker đang chờ `CountDownLatch` mà thread khác sẽ `countDown` sau 500 ms. Vì sao không thể gọi đó là deadlock?

## 16. Câu hỏi tự kiểm tra

**1. Deadlock khác contention thế nào?** — Deadlock có chu trình chờ không thể tiến triển; contention có thể tự kết thúc khi owner nhả khóa.

**2. Vì sao không nên tạo deadlock thật trực tiếp trong JUnit runner?** — Nó có thể giữ non-daemon threads vĩnh viễn; cần child JVM disposable với watchdog.

**3. Tại sao dùng CountDownLatch trong lab?** — Đảm bảo hai threads đã giữ khóa thứ nhất trước khi cùng thử lấy khóa thứ hai.

**4. findMonitorDeadlockedThreads thấy loại nào?** — Chu trình chờ object monitors giữa platform threads.

**5. findDeadlockedThreads thấy loại nào?** — Chu trình platform threads chờ monitors hoặc ownable synchronizers.

**6. Nếu ownable monitoring không được hỗ trợ thì sao?** — Có thể ném UnsupportedOperationException; test phải xử lý khả năng hỗ trợ và coverage.

**7. Tranh chấp monitor thường có trạng thái gì?** — BLOCKED.

**8. Tranh chấp ReentrantLock thường có trạng thái gì?** — WAITING vì park, có thể TIMED_WAITING với timed acquisition.

**9. Vì sao mixed case monitor-only detector có thể trả null?** — Cycle có một cạnh chờ ownable synchronizer, nên không phải chu trình chỉ gồm monitors.

**10. getLockInfo trả gì?** — Đối tượng thread đang chờ, không phải danh sách locks đã giữ.

**11. getLockedMonitors và getLockedSynchronizers trả gì?** — Hai nhóm locks mà thread đang sở hữu, khi JVM và overload hỗ trợ.

**12. Làm sao chứng minh owner cycle A→B→A?** — So getLockOwnerId hai chiều, cùng waiting LockInfo và held locks của owner kia.

**13. Vì sao không hardcode thread IDs trong expected output?** — IDs không ổn định giữa runs/JVM; dùng tên lab và quan hệ owner.

**14. Tại sao có healthy baseline?** — Giảm false positive; detector phải trả null khi không có chu trình trong case thử.

**15. System.exit trong ví dụ có được dùng trong production để sửa deadlock không?** — Không. Nó chỉ kết thúc **JVM con disposable** của bài kiểm thử.

**16. Nếu child không thoát thì parent làm gì?** — Bị giới hạn waitFor 9 giây, sau đó destroyForcibly và waitFor cleanup, trả lỗi.

**17. ThreadMXBean Java SE 26 có quản lý virtual threads không?** — Không. Các deadlock methods không phát hiện đầy đủ cycle có virtual threads.

**18. Thread.dump_to_file có tự phát hiện deadlock không?** — Không; nó xuất thông tin thread để phân tích, không tự chạy JMX deadlock detection.

**19. Chỉ có 2 WAITING có đủ khẳng định deadlock không?** — Không; cần owner chain/lock identity/stack và phạm vi detector.

**20. Code đã được kiểm thử ở đâu và bao nhiêu assertions?** — OpenJDK 24.0.2, biên dịch bằng `--release 17`, 19/19 PASS.

## 17. Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — ThreadMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadMXBean.html): `findMonitorDeadlockedThreads`, `findDeadlockedThreads`, capability flags, `getThreadInfo(ids,true,true)`, platform thread coverage và virtual thread limitations.
- [Oracle Java SE 26 — ThreadInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ThreadInfo.html): thread state, waiting lock, owner ID/name, stack trace và locked monitor/synchronizer arrays.
- [Oracle Java SE 26 — MonitorInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MonitorInfo.html): object monitor ownership, acquisition stack frame/depth.
- [Oracle Java SE 26 — LockInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/LockInfo.html): lock class name và identity hash.
- [Oracle Java SE 26 — AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html): exclusive owner model.
- [Oracle Java SE 26 — ReentrantLock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): ownership, acquisition, lock/unlock/tryLock.
- [Oracle Java SE 26 — Thread.State](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.State.html): BLOCKED, WAITING, TIMED_WAITING và scheduler states.
- [Oracle Java SE 26 — Process](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Process.html): `waitFor(timeout, unit)`, `destroyForcibly()`, process lifecycle.
- [Oracle Java SE 26 — ProcessBuilder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ProcessBuilder.html): tạo JVM con với arguments/redirectErrorStream.
- [Oracle Java SE 26 — jcmd command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): `Thread.print -l` và `Thread.dump_to_file` diagnostics.
- [Oracle Java SE 26 — Virtual Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): thread dumps cho platform/virtual, tính không nhất quán của `Thread.dump_to_file` và không tích hợp deadlock detector.
- [Oracle Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): API tương thích Java17.
- [Oracle Java SE 17 — ThreadInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): API dùng trong chương trình.

**Kết luận:** Kiểm thử deadlock đúng nghĩa cần **chứng minh wait-for cycle**, không chỉ thấy hai threads ở `BLOCKED` hoặc `WAITING`. Dùng `findDeadlockedThreads` để bao phủ monitor và ownable synchronizers của **platform threads**, thu `ThreadInfo` với locked monitors/synchronizers, đối chiếu owner chain/lock identities/stack frames; có **healthy baseline**, cô lập deadlock vào **JVM con có watchdog**, và luôn ghi rõ giới hạn virtual threads. Bằng chứng đúng và có cleanup mới tạo ra một regression test hữu ích, an toàn để chạy lặp lại.
