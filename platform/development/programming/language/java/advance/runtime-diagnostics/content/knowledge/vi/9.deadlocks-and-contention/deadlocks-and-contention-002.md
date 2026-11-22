# 9.2 — Lần theo chuỗi chủ sở hữu khóa và dựng vòng chờ từ thread dump

## 1. Bài toán: thread nào đang đợi ai?

Khi một ứng dụng Java không tiến triển, nhiều thread có thể mang trạng thái `BLOCKED`, `WAITING` hoặc `TIMED_WAITING`. Chỉ nhìn trạng thái chưa đủ để kết luận deadlock: một worker có thể chờ task bình thường; một thread có thể đang đợi database; nhiều thread khác có thể cùng chờ một monitor đang được thread khác giữ. Câu hỏi chẩn đoán quan trọng hơn là:

> **Thread T đang đợi khóa L nào? L hiện được thread H nào giữ? H đang làm gì — có tiếp tục đợi một khóa do thread khác giữ hay không?**

Bằng cách nối các quan hệ **waiter → owner** từ thread dump, ta xây dựng **wait-for graph** (đồ thị chờ). Nếu tìm thấy vòng có hướng, chẳng hạn `A → B → C → A`, và các cạnh biểu thị đúng việc chờ quyền sở hữu lock, đó là bằng chứng về **deadlock do chu trình khóa** tại thời điểm chụp.

Sau bài này, người học cần:

1. Đọc header, thread state, stack frames, `waiting to lock`, `locked` và phần `Locked ownable synchronizers`.
2. Liên kết **đúng lock identity** giữa một thread đang chờ và thread sở hữu, thay vì chỉ ghép theo tên thread hay class.
3. Dựng đồ thị có hướng từ chuỗi `waiter → owner`, tìm vòng, và phân biệt một **chuỗi chờ chưa thành vòng** với deadlock.
4. Phân biệt `synchronized` monitor với `ReentrantLock`/`AbstractOwnableSynchronizer` và những kiểu chờ không có owner nhìn thấy.
5. Tái hiện một vòng chờ bằng Java 17, lấy thread dump bằng `jcmd`, rồi đối chiếu với `ThreadMXBean.findMonitorDeadlockedThreads()`.
6. Biết các giới hạn của snapshot, quyền attach, thời điểm lấy mẫu và bước khắc phục.

**Thông điệp chính:** thread dump là **bằng chứng về một thời điểm**, không phải lời giải thích tự động cho mọi dạng treo. Chỉ vẽ cạnh khi có bằng chứng rằng một thread thực sự đang **đợi quyền sở hữu lock do thread khác giữ**.

## 2. Các thành phần cần quan sát trong thread dump

Một thread dump HotSpot trên JDK 17 thường có header mỗi thread, stack trace, chú thích monitor và ở cấu hình phù hợp có thông tin ownable synchronizers. Ví dụ *minh họa cấu trúc*:

```text
"worker-A" #17 prio=5 tid=0x... nid=0x... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at demo.Service.step(Service.java:42)
        - waiting to lock <0x00000007abc01000> (a java.lang.Object)
        - locked <0x00000007abc02000> (a java.lang.Object)
```

Các số `#17`, `tid`, `nid`, địa chỉ object và số dòng ở đây **chỉ là ví dụ**, không phải output cố định. Ở Java/HotSpot, cách trình bày các trường có thể thay đổi theo JDK/OS.

| Dấu hiệu | Ý nghĩa thực tế | Điều không được suy diễn |
| --- | --- | --- |
| `"worker-A"` | Thread name, hữu ích cho con người đọc | Tên thread không nhất thiết duy nhất |
| `#17` | Thường là Java thread ID trong header HotSpot | Không phải PID của JVM |
| `nid=0x...` | Native thread ID của hệ điều hành ở dạng hex theo HotSpot | Không phải Java thread ID dạng decimal |
| `tid=0x...` | Con trỏ/định danh implementation của thread trong HotSpot | Không phải cùng loại với `nid` |
| `BLOCKED (on object monitor)` | Thread đang chờ quyền vào hoặc vào lại Java monitor | Không cho biết thời gian chờ nếu thiếu số liệu khác |
| `- waiting to lock <L>` | Thread đang cố lấy monitor có identity `L` | Chưa nói thread nào giữ nếu chỉ đọc dòng này |
| `- locked <M>` | Thread đã giữ monitor `M` ở frame tương ứng | Không có nghĩa đang chờ `M` |
| `Locked ownable synchronizers` | Các ownable synchronizers mà thread giữ khi được dump | Không đồng nghĩa với mọi primitive đồng bộ hoặc external resource |
| `Found one Java-level deadlock` | JVM chẩn đoán phát hiện chu trình khóa thuộc phạm vi hỗ trợ | Không có dòng này chưa chắc mọi dạng treo đều vô hại |

**Định danh lock trong dump phải được so sánh trong cùng JVM và cùng lần chụp.** `<0x...>` là biểu diễn tham chiếu/identity trong dump, không phải tên biến `LEFT`/`RIGHT` ở source, không phải địa chỉ bền vững qua mọi GC hoặc restart.

### 2.1. Ba dòng dễ nhầm

- `waiting to lock <L>`: chờ **giành quyền sở hữu monitor**; đây thường là ứng viên tạo một cạnh đồ thị nếu xác định được owner.
- `waiting on <L>`: đang ở cơ chế `Object.wait()`, thread đã **nhả monitor của chính object được wait** khi chờ notification; không tự động tạo cạnh “đang chờ thread giữ L”.
- `parking to wait for <L>`: chờ qua `LockSupport.park`/AQS; có thể là `ReentrantLock`, condition, queue hoặc scheduler. Chỉ khi có bằng chứng về **ownable synchronizer và owner** mới nối cạnh khóa tương ứng.

Stack frame như `Object.wait`, `LockSupport.park`, `ConditionObject.await` hay `Thread.sleep` mô tả **cơ chế chờ**, chưa tự động nói một thread khác đang giữ lock nào.

## 3. Mô hình đồ thị chờ: định nghĩa nút và cạnh

Dùng **wait-for graph** hướng từ **thread đang chờ** tới **thread giữ khóa**:

```text
Thread A --đợi khóa do B giữ--> Thread B
Thread B --đợi khóa do C giữ--> Thread C
Thread C --đợi khóa do A giữ--> Thread A
```

Ký hiệu gọn: `A → B`, `B → C`, `C → A`. Chu trình có hướng là `A → B → C → A`.

**Không đảo chiều cạnh.** Câu `A → B` đọc là “A **đang đợi** B nhả một khóa”; **không** phải “A đang giữ khóa mà B cần”.

Để dựng một cạnh phải có tối thiểu:

1. Thread `T` đang chờ **acquire** lock `L` tại thời điểm chụp;
2. Lock `L` được xác định là do thread `H` đang giữ hoặc do thông tin owner của JVM gắn với `H`;
3. `T` và `H` là hai thread của **cùng phiên JVM**, và identity của `L` được đối chiếu chính xác.

Khi đó thêm cạnh `T → H`, có thể gắn nhãn lock:

```text
T --[waiting for Lock L]--> H
```

Nếu dump cho biết T đang đợi nhưng **không thấy owner**, ghi `OWNER_UNKNOWN`; không tự tạo owner từ tên class, stack frame giống nhau hoặc kinh nghiệm.

### 3.1. Hai loại đồ thị hữu ích

**Bipartite thread–lock graph** giữ cả tài nguyên:

```text
T_A --waits-for--> L_B --owned-by--> T_B
T_B --waits-for--> L_A --owned-by--> T_A
```

**Thread wait-for graph** co cặp `L_B → T_B` thành một cạnh:

```text
T_A --waits for L_B--> T_B
T_B --waits for L_A--> T_A
```

Dạng đầu dễ **kiểm toán bằng chứng** từ từng dòng `waiting to lock` và `locked`. Dạng sau dễ tìm chu trình trong tập thread. Runbook nên ghi cả **lock ID, owner ID và trạng thái** thay vì chỉ chép sơ đồ A/B không có dữ liệu truy xuất.

## 4. Một ví dụ hai thread và hai monitor

Giả sử hai Java monitors `L1` và `L2`:

- `worker-A` giữ `L1` rồi cần `L2`.
- `worker-B` giữ `L2` rồi cần `L1`.

Ảnh chụp thread dump có thể chứa hai đoạn như sau (**địa chỉ rút gọn, chỉ minh họa**):

```text
"worker-A" #17 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at demo.Service.step(...)
        - waiting to lock <0xB200> (a java.lang.Object)
        - locked <0xA100> (a java.lang.Object)

"worker-B" #18 ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at demo.Service.otherStep(...)
        - waiting to lock <0xA100> (a java.lang.Object)
        - locked <0xB200> (a java.lang.Object)
```

Lần theo:

| Thread đang chờ | Muốn lấy lock | Owner được chứng minh bởi | Cạnh |
| --- | --- | --- | --- |
| `worker-A` | `0xB200` | `worker-B` có `- locked <0xB200>` | `worker-A → worker-B` |
| `worker-B` | `0xA100` | `worker-A` có `- locked <0xA100>` | `worker-B → worker-A` |

Đồ thị:

```text
         đợi L2
worker-A ---------> worker-B
worker-A <--------- worker-B
         đợi L1

=> cycle: worker-A → worker-B → worker-A
```

**Chỗ then chốt:** phải so `0xB200` của dòng waiting ở A với `0xB200` của dòng locked ở B; tương tự với `0xA100`. Không kết luận vòng chờ chỉ vì cả hai có state `BLOCKED` hoặc cùng chạy một method.

Nếu HotSpot có thể xác định deadlock trong dump, nó thường thêm phần `Found one Java-level deadlock`, chỉ rõ mỗi thread đang chờ monitor nào và monitor đó được ai giữ. Phần này là một nguồn xác minh độc lập của sơ đồ tự dựng, nhưng đừng giới hạn việc điều tra chỉ vào việc tìm cụm chữ này.

## 5. Quy trình đọc một thread dump theo từng bước

### Bước 1 — Thu đúng JVM, đúng thời điểm

Trên đúng host và trong ngữ cảnh quyền/PID namespace phù hợp:

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> help Thread.print
jcmd <PID> Thread.print -l > thread-dump.txt
```

`<PID>` là chỗ cần thay bằng PID **thực**, không gõ dấu góc khi chạy. `jcmd` trên JDK 17 cần dùng trên cùng host với JVM và đúng quyền effective user/group để attach. Container có thể dùng PID namespace khác; không thay PID host/container tùy tiện.

`-l` của `Thread.print` yêu cầu thêm thông tin các khóa `java.util.concurrent` khi runtime hỗ trợ. Đây là thao tác chẩn đoán có **impact** phụ thuộc số thread, không nên gọi theo vòng lặp quá dày trên production. Đọc `help Thread.print` để biết cú pháp và impact trên chính JVM đích.

**Ghi nhận:** UTC timestamp khi lấy dump, host/pod, PID, **process start time**, JDK version và sự kiện incident. PID có thể tái sử dụng sau restart; thread names cũng có thể được dùng lại.

### Bước 2 — Chọn các thread ứng viên

Tìm thread:

- `BLOCKED (on object monitor)` với `- waiting to lock <...>`;
- `WAITING (parking)` hoặc `TIMED_WAITING (parking)` trong các đoạn AQS/`ReentrantLock` nhưng cần xác minh owner;
- thread **đang giữ** khóa mà nhiều thread khác cùng đợi;
- thread thuộc request/worker pool đang ngừng tiến triển theo metrics/traces.

Không bỏ qua thread `RUNNABLE` nếu nó là **owner của một monitor** đang bị nhiều thread chờ: owner có thể bị kẹt ở I/O hoặc chạy quá lâu trong critical section. Một thread `WAITING` cũng có thể giữ một monitor khác; phải đọc phần `- locked` trước khi kết luận.

### Bước 3 — Ghi khóa mà từng thread đợi và khóa đang giữ

Tạo bảng trích xuất, không ghép vội:

| Thread identity | Thread state | Đang đợi lock | Khóa đang giữ | Stack top |
| --- | --- | --- | --- | --- |
| `worker-A/#17` | `BLOCKED` | `0xB200` | `0xA100` | `Service.step` |
| `worker-B/#18` | `BLOCKED` | `0xA100` | `0xB200` | `Service.otherStep` |

Đây là bảng **minh họa**. Thông tin owner nếu có ở phần deadlock summary hoặc `ThreadInfo.getLockOwnerId()` được dùng để kiểm tra chéo. Với thread names trùng nhau, ưu tiên thread ID, native ID và JVM instance, không nối bằng tên.

### Bước 4 — Nối waiter với owner

Lập chỉ mục `lock identity → owning thread`, sau đó với mỗi dòng `waiting to lock <L>` tìm thread đang `locked <L>` trong **cùng dump**. Đối với ownable synchronizers, kiểm tra danh sách các synchronizer đang giữ và thông tin `lockOwnerId` nếu có.

Không có owner → ghi cạnh **chưa xác định** thay vì gán cho một thread tùy ý. Nếu hai dump khác thời điểm cho thông tin trái nhau, không trộn lock ID/owner của hai ảnh chụp để “đủ” một vòng giả.

### Bước 5 — Truy vết chuỗi và tìm chu trình

Bắt đầu từ thread bị treo được quan tâm:

```text
T0 → owner(T0) → owner(owner(T0)) → ...
```

Dừng khi:

- đến thread không chờ khóa do thread khác giữ → **chuỗi dừng**, chưa có cycle;
- đến lock không xác định owner → **thiếu bằng chứng**;
- gặp lại một thread **đã xuất hiện trong đường hiện tại** → có **cycle**;
- nhận ra dữ liệu khác phiên JVM/timestamp → không được tiếp tục nối.

Để xác minh trên JVM HotSpot, đối chiếu mục deadlock summary hoặc `ThreadMXBean.findDeadlockedThreads()` (nếu các loại lock hỗ trợ). Ghi rõ bằng chứng từ từng cạnh.

### Bước 6 — Lặp lại có kiểm soát

Nếu không thấy vòng nhưng triệu chứng kéo dài, lấy 2–3 dump cách nhau một khoảng phù hợp với sự cố, ví dụ vài giây, rồi so các thread IDs và stack positions. Việc thread giữ monitor lâu có thể là **lock contention/convoy**, không phải cycle. Nếu có vòng Java monitor thật, các thread liên quan không tự tiến triển trừ khi ứng dụng có cơ chế can thiệp/khôi phục phù hợp.

**Không đọc một snapshot như một timeline**: số lần lặp lại chỉ giúp kiểm tra tính kéo dài, không trực tiếp cho thời điểm bắt đầu chờ hoặc tổng thời gian đã bị chặn.

## 6. Thuật toán tìm vòng trong wait-for graph

Khi mỗi thread chỉ có một lock acquisition đang chặn tại một thời điểm, đồ thị waiter → owner thường có **tối đa một cạnh ra** tại mỗi thread. Ta có thể lần theo successor và theo dõi các node đã thấy trong **đường hiện tại**:

```text
for each starting thread S:
    path = []
    indexInPath = {}

    T = S
    while T exists:
        if T already in indexInPath:
            report cycle = path[indexInPath[T] .. end] -> T
            break

        if T was already fully analyzed:
            break

        indexInPath[T] = length(path)
        append T to path
        T = ownerThreadOfLockWaitedBy(T)

    mark path nodes analyzed
```

Đây là **pseudocode**, không phải cú pháp Java. Khi có nhiều cạnh trong mô hình phụ thuộc rộng hơn (ví dụ lock trong hệ thống phân tán), có thể dùng DFS tìm back edge hoặc thuật toán strongly connected components (Tarjan/Kosaraju). Với quan hệ monitor đơn giản, chỉ cần lần owner liên tiếp là đủ.

Ví dụ **không thành vòng**:

```text
T1 → T2 → T3
           |
           +-- T3 không đợi lock nào có owner
```

Đây có thể là contention dài hoặc T3 đang chờ I/O. Không kết luận deadlock Java-level chỉ vì T1/T2 không tiến triển trong vài giây.

Ví dụ **một owner có nhiều waiter**:

```text
T1 ──┐
T2 ──┼──> H
T3 ──┘
```

Đó là **fan-in/lock convoy**, không phải cycle nếu H không chờ trở lại một nút trong đường. Phân biệt điều này giúp không áp dụng khắc phục deadlock cho trường hợp critical section quá dài.

## 7. `synchronized` monitor và ownable synchronizers

### 7.1. Monitor Java nội tại

Một khối:

```java
synchronized (lockA) {
    synchronized (lockB) {
        // critical section
    }
}
```

Chỉ là snippet minh họa. Nếu thread khác giữ `lockB` thì thread hiện tại bị `BLOCKED` khi cố enter monitor. Thread dump thường có `- waiting to lock <lockB>`; thread owner có `- locked <lockB>`.

Deadlock điển hình khi A lấy thứ tự `lockA → lockB`, B lấy `lockB → lockA`. Tránh bằng **global lock ordering** nhất quán ở tất cả code paths.

`synchronized` acquisition không phải interruptible theo cách `ReentrantLock.lockInterruptibly()` hỗ trợ; đơn giản gọi `Thread.interrupt()` không bảo đảm giải phóng deadlock monitor.

### 7.2. ReentrantLock và AbstractOwnableSynchronizer

`java.util.concurrent.locks.ReentrantLock` dùng AQS/ownable synchronizer. Thread dump với `jcmd Thread.print -l` có thể chứa:

```text
"worker-C" ... WAITING (parking)
   at jdk.internal.misc.Unsafe.park(Native Method)
   at java.util.concurrent.locks.LockSupport.park(...)
   at java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
   at java.util.concurrent.locks.ReentrantLock.lock(...)

   Locked ownable synchronizers:
     - <0x00000007abc03000> (a ...ReentrantLock$NonfairSync)
```

Đoạn trên **chỉ minh họa** cấu trúc, không phải khẳng định thread C vừa đợi vừa sở hữu cùng synchronizer. Trong thread dump thật, phần `Locked ownable synchronizers` liệt kê các **synchronizer hiện đang được thread giữ**, còn stack/parking block thể hiện nơi thread đang chờ. Phải đối chiếu **object identity và owner thực tế**.

Với `ThreadMXBean`, `findDeadlockedThreads()` có thể phát hiện các chu trình có cả monitors và ownable synchronizers nếu JVM hỗ trợ; `findMonitorDeadlockedThreads()` chỉ phát hiện monitor deadlocks. Trước khi yêu cầu danh sách ownable synchronizers qua `getThreadInfo(ids, true, true)`, kiểm tra `isObjectMonitorUsageSupported()` và `isSynchronizerUsageSupported()` để tránh `UnsupportedOperationException` ở runtime không hỗ trợ.

### 7.3. Những kiểu đợi không có cạnh owner rõ

- `Object.wait()` **nhả monitor của object được wait** trong khi chờ notification. Một dòng `waiting on` không đồng nghĩa thread khác đang sở hữu lock đó.
- `Condition.await()` gắn với `Lock` tương ứng **nhả lock khi await**, rồi reacquire trước khi trở về. Một thread đang condition-wait không tự động là waiter trong đồ thị lock-acquisition hiện tại.
- `LockSupport.park()` thường chỉ cho biết đang park; không phải mọi park đều có ownable synchronizer owner.
- `Semaphore`, `CountDownLatch`, `BlockingQueue`, `Future.get`, mạng/DB/file I/O và distributed locks có thể tạo phụ thuộc ngoài mô hình owner-of-monitor. Một số trường hợp cần event logs, tracing hoặc tài nguyên ngoài JVM để dựng đồ thị chờ rộng hơn.
- ReentrantReadWriteLock, StampedLock, custom lock, native mutex có semantics khác nhau; không tự gán owner duy nhất khi implementation không cung cấp bằng chứng.
- Deadlock do **nhiều tài nguyên** như database row locks giữa các services không nhất thiết được JVM thread dump hoặc ThreadMXBean báo cáo.

**Không có “Found one Java-level deadlock” ≠ không có deadlock trong toàn hệ thống.** Nó chỉ nói công cụ không phát hiện một chu trình thuộc loại có thể nhận diện tại thời điểm đó.

## 8. Demo Java 17+: tạo deadlock xác định và in đồ thị chờ

Demo sau tạo **hai object monitors**, cho hai threads giữ monitor đầu của mình rồi cùng lúc thử monitor còn lại. `CountDownLatch` làm cả hai thực sự giữ khóa đầu tiên trước khi cạnh chờ thứ hai hình thành. Chương trình sử dụng `ThreadMXBean.findMonitorDeadlockedThreads()` để phát hiện đúng loại deadlock monitor vừa tạo.

**Chỉ chạy trong môi trường thử nghiệm.** Chương trình cố ý tạo deadlock; không nhúng mẫu này vào service thật. Hai worker là **daemon threads** để JVM demo có thể kết thúc sau thời gian giữ mẫu mà không để lại một process Java treo vô hạn.

### 8.1. File `LockWaitGraphDemo.java` hoàn chỉnh

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;

public class LockWaitGraphDemo {
    private static final Object LEFT = new Object();
    private static final Object RIGHT = new Object();

    static void lockInOrder(Object first, Object second, CountDownLatch ready) {
        synchronized (first) {
            ready.countDown();
            try {
                ready.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            synchronized (second) {
                System.out.println("unreachable");
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        long holdMillis = args.length == 0 ? 60_000L : Long.parseLong(args[0]);
        CountDownLatch bothHoldingFirst = new CountDownLatch(2);

        Thread a = new Thread(() ->
            lockInOrder(LEFT, RIGHT, bothHoldingFirst), "worker-A");
        Thread b = new Thread(() ->
            lockInOrder(RIGHT, LEFT, bothHoldingFirst), "worker-B");
        a.setDaemon(true);
        b.setDaemon(true);
        a.start();
        b.start();

        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        long[] ids = null;
        for (int i = 0; i < 100; i++) {
            ids = mx.findMonitorDeadlockedThreads();
            if (ids != null && ids.length >= 2) break;
            Thread.sleep(25);
        }
        if (ids == null || ids.length < 2) {
            throw new IllegalStateException("monitor deadlock not detected");
        }

        ThreadInfo[] infos = mx.getThreadInfo(ids, 16);
        Arrays.stream(infos)
            .filter(Objects::nonNull)
            .sorted(Comparator.comparing(ThreadInfo::getThreadName))
            .forEach(info -> System.out.println(
                info.getThreadName() + " -> " + info.getLockOwnerName()));
        System.out.println("cycleDetected=true");
        System.out.flush();
        Thread.sleep(holdMillis);
    }
}
```

**Giải thích cơ chế:**

1. `worker-A` lấy `LEFT`, `worker-B` lấy `RIGHT`.
2. Mỗi thread gọi `ready.countDown()` khi **đang giữ monitor đầu**, sau đó đợi latch về 0. Chờ latch **không thả** monitor `LEFT`/`RIGHT` đã được lấy bằng `synchronized`.
3. Khi cả hai đã vào, latch mở; A cố lấy `RIGHT` do B giữ, còn B cố lấy `LEFT` do A giữ. Cả hai `BLOCKED` ở `synchronized(second)`.
4. `findMonitorDeadlockedThreads()` phát hiện các thread tạo một chu trình **monitor acquisition** và trả IDs; `getThreadInfo(ids, 16)` lấy tên và lock owner của từng thread.
5. `Comparator` sắp xếp theo tên để stdout của hai worker có thứ tự cố định.
6. Main thread sleep để người học lấy dump bên ngoài; daemon workers sẽ không giữ JVM còn sống sau khi main kết thúc.

### 8.2. Biên dịch và chạy

```bash
javac --release 17 LockWaitGraphDemo.java
java LockWaitGraphDemo
```

**Stdout chính xác đã kiểm chứng với JDK chạy thử:**

```text
worker-A -> worker-B
worker-B -> worker-A
cycleDetected=true
```

Hai dòng đầu chính là đồ thị `waiter → owner`, không phải thứ tự khởi chạy của threads. Dòng cuối xác nhận JVM phát hiện chu trình monitor. Chương trình có thời gian giữ mặc định **60 giây** sau khi in để bạn lấy thread dump. Trong lúc đó main thread đang sleep, không nằm trong cycle.

Để chỉ kiểm tra stdout nhanh mà không giữ JVM lâu, có thể chạy:

```bash
java LockWaitGraphDemo 0
```

Trong ví dụ này `0` là đối số `holdMillis` của **chương trình demo**, không phải PID cho `jcmd`. Dùng `jcmd 0 Thread.print` sẽ có ý nghĩa khác và có thể gửi command tới nhiều JVM, vì vậy **không làm như vậy**.

### 8.3. Từ terminal thứ hai: chụp thread dump của demo

Khi chương trình vẫn đang sleep:

```bash
jcmd -l
jcmd <PID> help Thread.print
jcmd <PID> Thread.print -l > deadlock-demo.txt
```

Thay `<PID>` bằng PID của `LockWaitGraphDemo` do `jcmd -l` cho biết; không dùng PID ví dụ từ tài liệu. Quan sát:

- Hai thread `worker-A` và `worker-B` với state `BLOCKED (on object monitor)`.
- Dòng `- waiting to lock <...>` trong từng thread và dòng `- locked <...>` ở thread còn lại.
- Trong HotSpot hỗ trợ detection, phần `Found one Java-level deadlock` nêu rõ thread nào chờ monitor do thread nào giữ.

**Dữ liệu biến động:** PID, Java thread IDs, `nid`, `tid`, object IDs, source line và phần còn lại của dump thay đổi theo lần chạy. Không dùng chúng làm “stdout chuẩn”; output ba dòng từ chương trình là kết quả cố định trong lần chạy đã kiểm chứng.

### 8.4. QA kỹ thuật của ví dụ

Mã đã **biên dịch với `javac --release 17`**, chạy và in chính xác ba dòng ở trên. Trong một JVM thử nghiệm sống, lệnh `jcmd <PID> Thread.print -l` chạy thành công và dump có tên hai worker cùng **deadlock summary**. Các process/tệp tạm phục vụ kiểm chứng đã được dọn sau thử nghiệm.

Điều này minh họa được **cả hai đường xác minh**: API `ThreadMXBean` từ bên trong JVM và công cụ `jcmd` từ bên ngoài.

## 9. Dùng ThreadMXBean để kiểm tra chéo kết quả dump

`ThreadMXBean` trong module `java.management` cung cấp:

| API | Phạm vi | Kết quả và giới hạn |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Chu trình chờ **object monitors** | Thread IDs hoặc `null`; không bao gồm ownable synchronizers |
| `findDeadlockedThreads()` | Object monitors **và ownable synchronizers** | Thread IDs hoặc `null`; có thể ném `UnsupportedOperationException` nếu JVM không hỗ trợ theo dõi ownable synchronizers |
| `getThreadInfo(ids, 16)` | Stack/lock owner cho IDs | `ThreadInfo[]`, thread đã kết thúc có thể `null` |
| `getThreadInfo(ids, true, true)` | Thêm monitors và ownable synchronizers đang giữ | Cần capability checks; có thể tốn chi phí |
| `isObjectMonitorUsageSupported()` | Có thể thu thập locked monitors không? | Dùng trước khi yêu cầu `lockedMonitors=true` |
| `isSynchronizerUsageSupported()` | Có thể thu thập locked ownable synchronizers không? | Dùng trước khi yêu cầu `lockedSynchronizers=true` |
| `ThreadInfo.getLockInfo()` | Lock object mà thread bị block/wait trên đó | Có thể `null` khi không áp dụng |
| `ThreadInfo.getLockOwnerId()` | Java thread ID của owner (nếu biết) | Có thể `-1` khi không xác định |
| `ThreadInfo.getLockOwnerName()` | Tên thread owner | Có thể `null` |
| `ThreadInfo.getLockedMonitors()` | Các monitors thread đang giữ | Chỉ có khi cách lấy ThreadInfo yêu cầu/hỗ trợ thông tin đó |
| `ThreadInfo.getLockedSynchronizers()` | Ownable synchronizers thread đang giữ | Chỉ có khi yêu cầu/hỗ trợ |

Dòng:

```java
ThreadInfo info = mx.getThreadInfo(threadId, 16);
long ownerId = info == null ? -1 : info.getLockOwnerId();
```

là **snippet minh họa**, cần một `ThreadMXBean mx` và biến `threadId` có thật. Nó giúp tạo cạnh `threadId → ownerId` khi `ownerId > 0` và loại lock/trạng thái phù hợp; nhưng `ownerId == -1` **không tự chứng minh** thread đang tiến triển hay không có deadlock ngoài phạm vi theo dõi.

**Không chạy `findDeadlockedThreads()` trong hot path liên tục.** JavaDoc nói đây là thao tác troubleshooting, có thể tốn chi phí; cần phân biệt việc chẩn đoán lúc sự cố với metrics nhẹ chạy mỗi request. Khi JVM không phản hồi attach hoặc MXBean query, dùng logs/OS/JFR và quy trình sự cố tương ứng; thiếu output không đồng nghĩa thiếu deadlock.

## 10. Những trường hợp không phải chu trình deadlock

### 10.1. Thread pool rỗi

`pool-worker` đang `WAITING` trong `BlockingQueue.take()` hoặc `LockSupport.park()` có thể chỉ đang chờ task. Không có bằng chứng nó chờ một khóa do worker khác giữ. **Không vẽ cạnh** chỉ vì thấy `WAITING`.

### 10.2. Lock convoy / owner chạy quá lâu

`T1`, `T2`, `T3` cùng `BLOCKED` đợi monitor `L` do `H` giữ. Nếu `H` đang chạy hoặc chờ external I/O **mà không chờ khóa nào trong graph**, ta có:

```text
T1 ──┐
T2 ──┼──> H
T3 ──┘
```

Đó là contention/fan-in, không phải cycle. Tìm stack của `H`, độ dài critical section, I/O bên trong lock, pause/GC và tải thực tế. Có thể xảy ra starvation hoặc latency cao dù không có deadlock.

### 10.3. Object.wait hoặc Condition.await

Một consumer chờ notification hoặc condition thường **nhả monitor/lock gắn với thao tác wait** rồi mới ngủ, nên không tự tạo cạnh waiter → owner cho lock đó. Nhưng thread có thể vẫn giữ **các lock khác**; muốn kết luận phải đọc toàn bộ held locks và những tài nguyên liên quan.

### 10.4. Thread chờ I/O, DB hoặc external lock

Một request có thể treo do socket read, database row lock, RPC hoặc queue downstream. JVM dump cho stack “chờ” nhưng không cung cấp owner Java thread của tài nguyên ngoài process. Không dựng một Java monitor cycle không có bằng chứng; kết hợp database lock graph, network metrics, distributed traces hoặc thread dumps của bên kia khi được phép.

### 10.5. Starvation và livelock

Starvation xảy ra khi một thread không được chạy/không lấy được tài nguyên trong thời gian dài; livelock là các thread vẫn đổi trạng thái nhưng không tạo tiến triển nghiệp vụ. Một static wait-for graph có thể **không có cycle** trong hai tình huống này. Quan sát nhiều mẫu và tiến triển nghiệp vụ, thay vì chỉ tìm `Found one Java-level deadlock`.

## 11. Kiểm tra nhiều dump để tránh kết luận sai

Một quy trình điều tra thường lấy **2–3 thread dumps** ở những mốc riêng phù hợp với triệu chứng, ví dụ cách nhau vài giây. Gắn nhãn:

```text
host: node-03
pid: 18432
process_start_utc: 2026-10-29T08:00:00Z
snapshot_utc: 2026-10-29T08:15:02Z
command: jcmd 18432 Thread.print -l
incident: elevated request latency
```

Đây là metadata **minh họa**, không phải output của công cụ. Mỗi snapshot phải được phân tích **nội bộ** trước khi nối từ ảnh này sang ảnh khác:

- Thread ID và JVM start time có nhất quán không? Thread names có bị trùng/recycle không?
- Cùng thread đang chờ **cùng lock** trong mỗi ảnh hay đang thay đổi liên tục?
- Owner hiện tại là ai, stack có đổi không?
- Có **cycle được chứng minh trong một snapshot** không, hay chỉ chuỗi chờ nối ghép từ các thời điểm khác nhau?
- Phần JVM-provided deadlock summary có xuất hiện và khớp với đồ thị dựng thủ công không?

**Tránh ghép “A đợi B ở dump 1” với “B đợi A ở dump 2” rồi tuyên bố có vòng đồng thời.** Hai cạnh ở hai thời điểm khác nhau chưa đủ là một deadlock. Nếu JVM có khả năng di chuyển object/biểu diễn địa chỉ khác nhau, không dùng mỗi `<0x...>` để nối identity qua các lần dump.

## 12. Khi phát hiện cycle: xác định chỗ sửa trong code

Đồ thị chờ trả lời **ai đợi ai**; để sửa phải tìm **vì sao code lấy khóa theo thứ tự xung đột**.

Quy trình:

1. Với từng cạnh `A → B`, tìm frame của A ngay tại `waiting to lock` và nơi B giữ khóa cùng identity (dòng `locked`/`getLockedMonitors`).
2. Vẽ thứ tự acquire từ code: ví dụ `processOrder()` lấy `accountLock → inventoryLock` trong khi `reserveInventory()` lấy `inventoryLock → accountLock`.
3. Kiểm tra các đường gọi qua callbacks, listeners hoặc synchronous RPC đang chạy **bên trong** critical section.
4. Đề xuất **thứ tự khóa toàn cục nhất quán**: luôn lấy `accountLock` trước `inventoryLock` trên mọi đường đi.
5. Khi dùng `ReentrantLock`, cân nhắc `tryLock(timeout)`/`lockInterruptibly()` nếu phù hợp, nhớ `unlock()` trong `finally` và kiểm soát rollback khi không lấy được khóa.
6. Thu nhỏ critical section, tránh I/O lâu hoặc lời gọi không kiểm soát trong lúc giữ khóa, thay shared mutable state bằng mô hình actor/queue hoặc immutable data khi hợp lý.
7. Viết regression test tái hiện hai luồng và xác nhận sau sửa **không còn cycle**, cả hai hoàn tất công việc thực.

**Không xem `Thread.stop()`, `Thread.suspend()` hay tùy tiện kill worker như giải pháp an toàn.** Những thao tác này có thể phá invariant hoặc làm hỏng state; nếu production đã deadlock thực và cần phục hồi, áp dụng quy trình incident/restart có kiểm soát và giữ bằng chứng trước.

### 12.1. Thứ tự lấy khóa nhất quán

Ví dụ sửa đối xứng:

```java
// Cả hai code path đều sử dụng cùng thứ tự.
synchronized (accountLock) {
    synchronized (inventoryLock) {
        updateState();
    }
}
```

Đây là **snippet minh họa**; cần có `accountLock`, `inventoryLock` và `updateState()` ở class thực. Không phải mọi bài toán đều cần giữ hai lock; đôi khi chỉ cần một lock bao quanh state nhỏ hoặc chuyển thành message passing.

Với nhiều lock được tạo động (ví dụ lock theo account ID), dùng khóa sắp thứ tự nhất quán theo ID và xử lý trường hợp trùng key. Nếu có callback thực thi từ ngoài, xác định trước khả năng callback lấy lại lock theo chiều ngược.

## 13. Các lỗi suy luận thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “Hai thread `BLOCKED` tức deadlock.” | Cùng chờ một owner có thể chỉ là contention. | Truy owner và tìm vòng có hướng. |
| “`WAITING` luôn là chờ monitor của thread khác.” | Có thể queue, `Object.wait`, condition, sleep/park. | Phân loại cơ chế chờ trước khi tạo cạnh. |
| “`- waiting on` = `- waiting to lock`.” | `Object.wait` nhả monitor trong lúc đợi notification. | Chỉ nối cạnh monitor acquisition khi có bằng chứng. |
| “Dùng tên thread là đủ.” | Tên có thể trùng, thread có thể kết thúc/recreate. | Dùng Java thread ID, native ID và JVM instance. |
| “`nid` là Java thread ID.” | `nid` là native ID trong HotSpot. | Không trộn với ThreadMXBean IDs. |
| “Object ID 0x... tồn tại qua mọi dump.” | Biểu diễn địa chỉ/identity có thể đổi. | Match trong cùng snapshot, có lifecycle context. |
| “Thấy `locked <L>` nghĩa thread đang chờ L.” | `locked` mô tả **đang giữ**. | Hướng cạnh là waiter → owner. |
| “Một waiter có thể gán owner theo class lock.” | Nhiều object cùng class khác identity. | Match **cùng lock identity**. |
| “Có `LockSupport.park` là một ReentrantLock deadlock.” | Park có nhiều nguyên nhân, không phải luôn có owner. | Đọc ownable synchronizers và owner ID. |
| “Không có deadlock summary nghĩa không có treo.” | JVM không thấy DB/I/O/external deadlock hoặc owner unknown. | Dùng logs/metrics/traces và công cụ bên ngoài. |
| “Trộn hai snapshot thành một graph.” | Cạnh có thể không đồng thời tồn tại. | Xây graph riêng cho từng timestamp. |
| “Dùng `jcmd 0` để chẩn đoán một JVM.” | PID 0 có thể gửi command tới nhiều JVM. | Chọn chính xác PID và process start time. |
| “Một dump chứng minh thread đã chờ 10 phút.” | Dump không tự ghi thời lượng chờ liên tục. | Dùng monitoring lịch sử và nhiều snapshots. |
| “Thấy cycle là kill thread để mở khóa.” | Không có thao tác an toàn chung để giải phóng lock ngoài luồng. | Sửa ordering, phục hồi có kiểm soát. |

## 14. Quy trình xử lý sự cố production

### A. Trước khi chụp

- Chọn **đúng host/pod/PID namespace**, PID, process start time và owner của JVM. Không dựa vào main class/JAR khi nhiều replica giống nhau.
- Xác minh JDK/JVM thích hợp, quyền attach và yêu cầu bảo mật. `jcmd` phải chạy ở đúng máy theo tài liệu JDK 17.
- Ghi mốc bắt đầu triệu chứng, hệ thống affected, throughput/latency/CPU/GC; tránh tạo snapshot quá dày trong JVM đang rất tải.
- Xác định liệu output có chứa stack/class names, đường dẫn hoặc thông tin nhạy cảm; lưu ở nơi đúng quyền.

### B. Thu bằng chứng

```bash
jcmd <PID> Thread.print -l > dump-1.txt
# Sau một khoảng phù hợp:
jcmd <PID> Thread.print -l > dump-2.txt
```

Đây là ví dụ shell, `<PID>` phải thay. Redirect `>` tạo file tại môi trường **client shell**. Chỉ chạy trên JVM đúng quyền; nếu có cảnh báo impact cao hoặc JVM không phản hồi, ưu tiên quy trình incident.

### C. Dựng và xác minh graph

- Tách từng block thread trong **một dump**.
- Ghi thread ID/name/state, lock đang đợi, held monitors và locked ownable synchronizers.
- Nối waiter → owner bằng **lock identity hoặc explicit owner metadata**.
- Phân nhánh OWNER_UNKNOWN khi bằng chứng thiếu.
- Tìm cycle, xác minh với `Found ... Java-level deadlock` và/hoặc `ThreadMXBean` nếu hỗ trợ.
- Nếu không có cycle, xem fan-in, owner stack, OS I/O, GC/logs và các thành phần ngoài JVM.

### D. Khắc phục và xác nhận

- Khi có cycle, định vị source code gây thứ tự acquire đối nghịch hoặc callback dưới lock.
- Chọn sửa global ordering/critical-section/lifecycle có test race, thay vì chỉ thay đổi thời gian sleep.
- Nếu cần restart production để phục hồi, bảo toàn chứng cứ và làm theo change/incident policy.
- Sau fix, chạy regression test đa luồng, tái lập tải, so sánh thread dumps và metrics để xác nhận tính tiến triển.

## 15. Checklist đánh giá kết quả

- [ ] Đã xác nhận **đúng JVM instance, PID, start time, namespace** chưa?
- [ ] Đã lấy dump có `-l` và biết impact của `Thread.print` chưa?
- [ ] Thread ID, name, `nid`, `tid` có được phân biệt đúng không?
- [ ] Mỗi cạnh `waiter → owner` có **lock identity/owner evidence** không?
- [ ] Đã phân biệt `waiting to lock` với `waiting on`/`parking to wait for` chưa?
- [ ] Đã tìm vòng **trong cùng một snapshot**, không ghép cạnh khác thời điểm chưa?
- [ ] `found deadlock` có khớp sơ đồ không? Nếu không có, đã xem giới hạn loại lock và dữ liệu chưa?
- [ ] Nếu chỉ fan-in, đã xem **owner stack/critical section** chưa?
- [ ] Nếu liên quan AQS/ReentrantLock, đã xem `Locked ownable synchronizers` và capability tương ứng chưa?
- [ ] Đã tách Java monitor deadlock khỏi DB/I/O/distributed lock waits chưa?
- [ ] Đã lưu thời gian, phiên JVM, lệnh, format và redaction của chứng cứ chưa?
- [ ] Đã có thay đổi code giải quyết lock ordering và regression test xác nhận chưa?

## 16. Tài liệu tham khảo Java SE 17

- [Oracle — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print`, `-l`, cách chọn PID, help và impact.
- [Oracle — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): `findMonitorDeadlockedThreads`, `findDeadlockedThreads`, `getThreadInfo`, locked monitors và ownable synchronizers.
- [Oracle — ThreadInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): `getLockInfo`, `getLockOwnerId`, `getLockedMonitors`, `getLockedSynchronizers` và thread state.
- [Oracle — LockInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/LockInfo.html): biểu diễn thông tin khóa đang chờ/được giữ.
- [Oracle — Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): semantics của `BLOCKED`, `WAITING` và `TIMED_WAITING`.
- [Oracle — Object.wait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#wait()): monitor release khi chờ.
- [Oracle — Lock / Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): semantics của `await` và release/reacquire lock.

**Kết luận kỹ thuật:** Từ thread dump, hãy xác định chính xác **đang chờ lock nào → lock do thread nào giữ → owner còn chờ ai**. Vẽ cạnh có hướng waiter → owner bằng cùng lock identity, truy vết đến khi dừng hoặc lặp. **Cycle cùng thời điểm** là tín hiệu deadlock monitor/ownable synchronizer thuộc phạm vi chẩn đoán; **không có cycle** có thể vẫn là contention, starvation hoặc external wait. Phân tích được chuỗi sở hữu khóa sẽ dẫn bạn từ triệu chứng “thread treo” tới thứ tự acquire cần sửa trong code.