# 8.5 Đọc monitor đang giữ, khóa đang chờ và ownable synchronizer

Khi ứng dụng Java bị treo, timeout hoặc throughput giảm, thread dump thường có các dòng như `- locked <0x...>`, `- waiting to lock <0x...>`, `- waiting on <0x...>` hoặc `- parking to wait for <0x...>`. Chỉ một chữ khác nhau cũng có thể làm thay đổi hoàn toàn chẩn đoán: **thread đang giữ monitor**, **đang cạnh tranh để vào monitor**, **đang chờ thông báo sau `Object.wait()`**, hay **đang được park bởi một cơ chế đồng bộ kiểu `java.util.concurrent`**.

Ví dụ, một thread ở trạng thái `BLOCKED` chờ lấy monitor không nhất thiết là deadlock; nó có thể chỉ đang đợi vài mili giây. Một thread ở `WAITING (parking)` không nhất thiết nhàn rỗi: nó có thể đang đợi `ReentrantLock` do thread khác giữ, hoặc đang chờ một `Condition`, `CountDownLatch` hay công việc trong pool. Một thread mang dòng `- locked <...>` đang sở hữu monitor tại thời điểm chụp, nhưng **chưa thể** kết luận monitor ấy là nguyên nhân duy nhất của latency nếu chưa nối được cạnh “ai chờ ai”.

Bài này cung cấp cách đọc có hệ thống ba nhóm thông tin trong thread dump HotSpot/JDK 17+:

1. **Monitor đang giữ:** `synchronized` và dòng `- locked`; xác định thread chủ sở hữu và vị trí lock được lấy.
2. **Khóa đang chờ:** `waiting to lock`, `waiting on`, `parking to wait for`, kèm thread state và thông tin owner nếu có.
3. **Ownable synchronizer:** các loại đồng bộ độc quyền như `ReentrantLock` được quản lý theo `AbstractOwnableSynchronizer`; đọc phần `Locked ownable synchronizers` và giải thích khác biệt với object monitor.

Kết thúc bài, bạn sẽ biết phân biệt **contention, waiting, long hold, deadlock** và những trường hợp **chưa đủ bằng chứng**; đọc `ThreadInfo`/`ThreadMXBean` qua Java API; chọn công cụ phù hợp, tránh thu dump quá nhiều; và bảo vệ thông tin nhạy cảm trước khi chia sẻ.

## 1. Bản đồ khái niệm: thread, monitor và synchronizer

### 1.1 Java monitor là gì?

Mỗi Java object có thể dùng làm monitor cho cơ chế `synchronized`. Khi thread thực thi:

```java
synchronized (sharedObject) {
    doCriticalWork();
}
```

thread **phải lấy được monitor của `sharedObject` trước khi vào khối**. Nếu thread A đang giữ monitor và thread B muốn vào cùng monitor, B phải chờ. Với nền tảng Java/HotSpot thường gặp, B sẽ có trạng thái `BLOCKED (on object monitor)` tại thời điểm chụp; A có thể là `RUNNABLE`, `TIMED_WAITING` hoặc `WAITING` tùy công việc đang thực hiện **trong khi vẫn giữ monitor**.

Vì thế, khi tìm chủ khóa, **đừng chỉ tìm thread `RUNNABLE`**. Thread chủ có thể đang `sleep`, chờ I/O, đợi latch hoặc làm việc chậm khi vẫn ở trong `synchronized`.

### 1.2 Ownable synchronizer là gì?

Trong `java.util.concurrent.locks`, `AbstractOwnableSynchronizer` cung cấp khái niệm một đối tượng đồng bộ có **thread sở hữu độc quyền**. `AbstractQueuedSynchronizer` và một số cơ chế lock sử dụng thông tin này để điều khiển/quan sát ownership. `ReentrantLock` là ví dụ điển hình: thread gọi `lock()` thành công sở hữu khóa cho tới khi `unlock()` đủ số lần.

Điểm khác biệt:

- `synchronized` dùng **object monitor** do JVM quản lý, có quan hệ trực tiếp với object được dùng làm khóa.
- `ReentrantLock` dùng cơ chế đồng bộ thư viện; khi bị tranh chấp, các thread chờ thường **park** thay vì rơi vào trạng thái `BLOCKED` dành riêng cho monitor entry.
- Trong HotSpot thread dump, một ownable synchronizer có thể hiện dưới dạng **đối tượng nội bộ của lock**, chẳng hạn instance `ReentrantLock$NonfairSync`, chứ không phải object wrapper `ReentrantLock`.
- Không phải mọi đối tượng trong `java.util.concurrent` đều là ownable synchronizer: `CountDownLatch` và `Semaphore` là các cơ chế chờ/cấp phép không đồng nghĩa có owner độc quyền theo cách của `ReentrantLock`.
- `ReentrantReadWriteLock` có nhiều semantics khác nhau giữa read/write locks; không được kết luận “mọi synchronizer trong mọi implementation đều hiện đầy đủ owner”.

### 1.3 Ba câu hỏi phải đặt riêng

| Câu hỏi | Loại dữ liệu cần | Vì sao quan trọng |
| --- | --- | --- |
| **Thread này đang chờ gì?** | Thread state, `getLockInfo()`, stack frame, `waiting to lock/on/parking` | Phân biệt monitor entry, condition wait, parking |
| **Thread này đang giữ gì?** | `- locked`, `MonitorInfo[]`, `Locked ownable synchronizers`, `LockInfo[]` | Tìm chủ monitor/ownable lock ở snapshot |
| **Ai đang chờ ai?** | Lock object identity, `getLockOwnerId()`, chain và thời điểm dump | Lập quan hệ ownership, xác định cycle hoặc bottleneck |

Một dòng stack đơn lẻ trả lời rất ít. Cần **đọc cùng block của thread chờ và block của thread chủ khóa**, tốt nhất trong nhiều snapshot cách nhau có chủ đích.

## 2. Từ khóa thường gặp trong HotSpot thread dump

Một đoạn **mô phỏng** (tên thread, địa chỉ, số dòng đều chỉ để học, không phải dump đã chạy):

```text
"worker-B" #42 prio=5 tid=0x... nid=0x... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
    at demo.InventoryService.update(InventoryService.java:72)
    - waiting to lock <0x0000000710101010> (a java.lang.Object)
    at demo.InventoryService.process(InventoryService.java:45)

"worker-A" #41 prio=5 tid=0x... nid=0x... waiting on condition
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(Native Method)
    at demo.InventoryService.update(InventoryService.java:81)
    - locked <0x0000000710101010> (a java.lang.Object)
```

Dấu `0x...` trong ví dụ là **biểu diễn identifier nội bộ của tool/VM tại một lần dump**, không phải địa chỉ để truy cập bằng Java và không được xem là ID bất biến qua restart. Những dấu `...` khác là chi tiết được lược trong ví dụ giả, không phải cú pháp bắt buộc của mọi dump.

Từ đoạn này, có thể lập giả thuyết:

- B đang `BLOCKED` vì muốn lấy monitor của object có identifier `<0x0000000710101010>`.
- A đang ở trong `synchronized` giữ **đúng identifier đó**.
- A đang sleep trong critical section, nên B không thể vào cho tới khi A nhả khóa.
- Đây là **lock contention/long hold**; **chưa phải deadlock**, vì chưa có bằng chứng A lại đợi một khóa do B giữ.

**Không** khẳng định “thread B đang treo vĩnh viễn” chỉ từ một ảnh chụp; nếu A sắp hết sleep, B có thể chạy bình thường. Cần số liệu thời gian và nhiều snapshot.

### 2.1 Ý nghĩa của các marker

| Marker trong dump | Cách đọc thực tế | Không nên suy ra |
| --- | --- | --- |
| `- locked <id>` | Thread hiện giữ monitor tương ứng tại thời điểm quan sát | Thread này luôn là root cause |
| `- waiting to lock <id>` | Thread đang cạnh tranh lấy monitor để **vào `synchronized`** | Deadlock chắc chắn |
| `- waiting on <id>` | Thread đang chờ `Object.wait()`/notify trên monitor liên quan | Thread vẫn giữ **monitor đang wait trên** |
| `- parking to wait for <id>` | Thread dùng park/`LockSupport` với blocker object | Blocker nhất định do thread khác sở hữu |
| `Locked ownable synchronizers:` | Phần liệt kê các ownable synchronizers mà thread đang sở hữu | Danh sách tất cả khóa nói chung |
| `- None` trong mục ownable | Không ghi nhận synchronizer thuộc loại này ở snapshot | Thread không giữ monitor nào |
| `java.lang.Thread.State: BLOCKED` | Chờ monitor entry | Đang chờ CPU scheduler thuần túy |
| `java.lang.Thread.State: WAITING/TIMED_WAITING` | Chờ/park/wait/sleep tùy stack | Chắc chắn nhàn rỗi, không chiếm tài nguyên |
| `RUNNABLE` | State Java RUNNABLE tại snapshot | Đang tiêu thụ CPU liên tục |

Các chuỗi hiển thị, vị trí marker, các option và việc những thread nào được đưa vào dump có thể khác theo JDK/VM, đặc biệt với **virtual threads** ở các bản Java mới. Cần dựa trên JVM thực tế và thông tin bổ sung, không viết parser mong mọi dòng luôn đúng một biểu thức chính quy.

## 3. Monitor đang giữ: đọc dòng - locked

### 3.1 Monitor owner không nhất thiết đang thực thi

Một thread đi vào khối `synchronized(lock)` thành công sẽ giữ monitor đến khi rời khối, kể cả khi code trong khối:

- Gọi `Thread.sleep(...)`.
- Chờ một API I/O blocking.
- Chờ một `CountDownLatch.await()`.
- Gọi `LockSupport.park()`.
- Thực hiện xử lý CPU dài.
- Truy cập DB/network mà không có timeout phù hợp.

Những thao tác này **không tự động nhả monitor**; chúng có thể làm các thread khác bị `BLOCKED`. Ngoại lệ quan trọng: **`Object.wait()` nhả monitor của chính object đang được wait** trong thời gian đợi, sau đó phải lấy lại monitor trước khi trả về. Nó **không** tự nhả những monitor khác mà thread cũng đang giữ.

### 3.2 Đọc stack frame gần marker

Ví dụ giả định:

```text
"owner-thread" ...
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
    at demo.RemoteCall.awaitResponse(RemoteCall.java:118)
    at demo.Service.criticalSection(Service.java:60)
    - locked <0x0000000710111000> (a demo.Service)
```

Thread đã lấy monitor của `demo.Service` ở vùng `criticalSection`, sau đó park trong lời gọi ngoài. Khi nhiều thread khác đợi cùng ID, câu hỏi cần điều tra là **vì sao critical section kéo dài**, không phải chỉ “vì thấy WAITING”.

Một dòng `- locked` hiển thị gần frame có thể giúp định vị nơi `synchronized` được lấy. Với chương trình tối ưu/JIT hoặc một số loại frame, cách tool trình bày không nhất thiết trực tiếp tương đương source line; đọc cả call stack và đối chiếu source version.

### 3.3 MonitorInfo cung cấp gì?

`java.lang.management.MonitorInfo` kế thừa `LockInfo` và chứa:

- `getClassName()`: tên lớp của object monitor.
- `getIdentityHashCode()`: identity hash code do JVM báo; **không** phải địa chỉ bộ nhớ ổn định.
- `getLockedStackDepth()`: chỉ số stack frame nơi monitor được lock, có thể âm nếu không sẵn có.
- `getLockedStackFrame()`: frame nơi lock được lấy, có thể `null` nếu không sẵn có.

`ThreadInfo.getLockedMonitors()` trả danh sách các object monitors mà thread đang giữ **nếu lúc thu thông tin đã yêu cầu locked monitor usage và JVM hỗ trợ**. Mảng rỗng cũng có thể do *không thu loại thông tin đó*, không đồng nghĩa thread “chắc chắn không sở hữu monitor” trong mọi bối cảnh.

### 3.4 Một thread có thể giữ nhiều monitor

Ví dụ:

```java
synchronized (orderLock) {
    synchronized (inventoryLock) {
        updateInventory();
    }
}
```

Khi ở trong khối bên trong, thread giữ cả hai monitor. Nếu thread khác chờ `inventoryLock`, hãy tìm owner có `- locked <inventory-id>`; nếu owner lại chờ lock thứ ba, tiếp tục lần theo chuỗi. Thứ tự lấy nhiều lock không nhất quán có thể tạo deadlock nếu thành chu trình.

**Không** dựa vào thứ tự các dòng `- locked` trong dump để suy ra thứ tự tuyệt đối khi lock được lấy. Khi cần tìm lock-order inversion, đối chiếu stack/source và các cạnh chờ theo snapshot.

## 4. Khóa đang chờ: phân biệt waiting to lock, waiting on và parking

### 4.1 waiting to lock — tranh monitor entry

Với `synchronized(lock)`, thread muốn vào nhưng khóa đang bị giữ có thể xuất hiện:

```text
"contender" ...
   java.lang.Thread.State: BLOCKED (on object monitor)
    at demo.Service.criticalSection(Service.java:44)
    - waiting to lock <0x0000000710123000> (a java.lang.Object)
```

Đây là **cạnh chờ để lấy monitor**. Để tìm chủ, tìm một block thread khác có `- locked <0x0000000710123000>` trong **cùng snapshot**, hoặc dùng `ThreadInfo.getLockOwnerId()` nếu JVM cung cấp. Nếu không thấy chủ, các khả năng gồm: dump bị cắt, thread vừa nhả monitor, identity không trùng do ghép nhầm nhiều snapshots, tool không in đủ hoặc owner ngoài tập thread được thu.

Khi có nhiều contenders cho cùng monitor, đó là **điểm contention nóng**. Không suy “mọi thread BLOCKED đều chờ riêng nhau”: có thể hàng chục thread cùng đợi một owner.

### 4.2 waiting on — Object.wait có semantics nhả monitor

Với code:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

Trong thời gian ở `Object.wait()`, thread **nhả monitor `lock`** và chuyển sang trạng thái đợi notification hoặc timeout. Khi được notify hoặc wake khác, nó **phải giành lại monitor `lock` trước khi `wait` trả về**, do đó có thể trở thành `BLOCKED` khi cố reacquire.

Một dump mô phỏng có thể có:

```text
"waiter" ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(Native Method)
    - waiting on <0x0000000710134000> (a java.lang.Object)
```

**Không tìm một dòng `- locked` ở thread này cho đúng monitor đang `wait()`** rồi kết luận waiter vẫn sở hữu nó. Nếu thấy thread giữ **monitor khác**, điều đó vẫn có thể xảy ra vì `wait()` chỉ nhả monitor được gọi, không nhả mọi monitor.

Phân biệt `notify()`/`notifyAll()` với **việc lấy được monitor sau khi được đánh thức**: có notify không bảo đảm waiter lập tức chạy tiếp.

### 4.3 parking to wait for — cơ chế park

`LockSupport.park(blocker)` và các primitive đồng bộ dùng parker có thể hiện:

```text
"reentrant-waiter" ...
   java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(...)
    at java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire(...)
    - parking to wait for <0x0000000710145000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
```

Đây thường là thread chờ **AQS synchronizer của ReentrantLock**. Nó có thể mang trạng thái `WAITING` hoặc `TIMED_WAITING` tùy path có timeout và implementation. **Nó không bắt buộc là `BLOCKED`** vì `Thread.State.BLOCKED` dùng cho monitor entry. Nếu cần tìm owner, xem mục ownable synchronizers của threads còn lại hoặc owner ID do `ThreadInfo` cung cấp (nếu có).

Nhưng `park` còn có thể dùng trong:

- Thread pool chờ work.
- `Condition.await()`.
- `CountDownLatch.await()` hoặc `Semaphore.acquire()`.
- `CompletableFuture.join()` hoặc các cơ chế chờ completion.
- Scheduling/coordination của libraries.

Vì vậy một blocker object được hiển thị **không có nghĩa luôn tồn tại owner độc quyền**. Đọc stack để xác định loại primitive.

### 4.4 WAITING không phải lúc nào cũng là lỗi

Thread pool worker chờ task, scheduler thread đợi thời hạn, dispatcher chờ queue, thread chờ condition theo thiết kế có thể thường xuyên ở `WAITING`. Thấy nhiều WAITING **không tự chứng minh deadlock**; cần đối chiếu throughput, queue buildup, latency, khoảng thời gian và điều kiện đánh thức.

Ngược lại, thread ở `RUNNABLE` có thể đang gọi native I/O hoặc mất khả năng tiến triển; chỉ nhìn state cũng không chứng minh hệ thống khỏe.

## 5. Ownable synchronizers: đọc mục riêng của thread dump

### 5.1 Vì sao cần phần Locked ownable synchronizers?

Monitor locking và `java.util.concurrent.locks` có cơ chế khác nhau. Nếu chỉ xem `- locked` của `synchronized`, bạn có thể bỏ qua `ReentrantLock` đang bị giữ. Trên HotSpot, option in thông tin `java.util.concurrent` locks giúp thấy danh sách kiểu:

```text
"lock-holder" ...
   java.lang.Thread.State: WAITING (parking)
    ...
   Locked ownable synchronizers:
    - <0x0000000710156000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)

"lock-contender" ...
   java.lang.Thread.State: WAITING (parking)
    ...
    - parking to wait for <0x0000000710156000>
      (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
   Locked ownable synchronizers:
    - None
```

Đây là **đoạn minh họa** với cách biểu diễn có thể thay đổi theo phiên bản, không phải cam kết từng dòng của JDK cụ thể. Khi identity của blocker và synchronizer do owner giữ khớp trong **cùng dump**, có một gợi ý mạnh về cạnh chờ, cần đối chiếu `ThreadInfo`/stack nếu có.

**Không** nhầm `ReentrantLock` wrapper với đối tượng `Sync` nội bộ. Trong HotSpot, phần liệt kê có thể ghi class `java.util.concurrent.locks.ReentrantLock$NonfairSync` hoặc kiểu tương ứng theo fairness/implementation. Địa chỉ trong dump và identity hash code Java không được giả định chuyển đổi qua phép tính đơn giản.

### 5.2 Tại sao chỉ đọc một block thread chưa đủ?

Thread đang đợi `ReentrantLock` có stack AQS/LockSupport, nhưng nó không bắt buộc chứa tên thread đang giữ lock. Tìm owner bằng:

1. Lấy `LockInfo` của thread chờ, nếu có.
2. Xem `getLockOwnerId()`/`getLockOwnerName()` khi JVM biết.
3. So sánh object identity với `getLockedSynchronizers()` của các threads chủ ứng viên, trong phạm vi snapshot.
4. Đối chiếu stack nơi owner đang thực thi và business code đang giữ lock.
5. Xác nhận hiện tượng qua snapshot sau hoặc instrumentation.

`getLockedSynchronizers()` trả `LockInfo[]`, chứa class và identity hash, **không có thông tin frame nơi lock được lấy như `MonitorInfo`**. Vì thế stack/source của owner và cấu trúc code vẫn cần để xác định critical section.

### 5.3 Không phải mọi lock đều ownable

`AbstractOwnableSynchronizer` chỉ cung cấp cơ sở **ghi nhận owner độc quyền**. Một số primitives như semaphore cho phép nhiều permits, latch/cyclic barrier quản lý điều kiện không có owner kiểu mutex, nên danh sách “locked ownable synchronizers” không phải **bản liệt kê tất cả blocking dependencies**. Một `Condition.await()` tạm nhả lock liên quan trong quá trình đợi; thread có thể đang chờ signal chứ không giữ mutex.

Mục này đặc biệt quan trọng khi debug **thread pool starvation** hoặc hệ thống không tiến triển vì thiếu task/notification: có thể có rất nhiều WAITING/parking nhưng **không có cycle owner-lock-owner**.

## 6. Chọn công cụ thu dump để thấy đúng loại lock

### 6.1 jcmd Thread.print và -l

Với HotSpot/JDK 21, có thể xem help trước:

```bash
jcmd 4242 help Thread.print
jcmd 4242 Thread.print
jcmd 4242 Thread.print -l
```

`4242` là **PID ví dụ**, không phải JVM thật đã được phát hiện. `Thread.print` in stack traces; option `-l` yêu cầu in locks từ `java.util.concurrent` nếu JVM/tool hỗ trợ. Trên một số JDK, `-e` yêu cầu extended thread information; xác minh qua `help Thread.print` của đúng target/JDK.

**Chú ý hai lệnh khác nhau:**

- `jcmd -l`: **liệt kê JVM** mà công cụ nhận diện được.
- `jcmd 4242 Thread.print -l`: **in thread dump** của JVM cụ thể và yêu cầu thông tin ownable locks.

Nhầm hai cách dùng `-l` dễ dẫn tới thu thiếu dữ liệu.

### 6.2 jstack -l

Trên các JDK/tool tương ứng:

```bash
jstack -l 4242
```

`jstack -l` yêu cầu thu thông tin ownable synchronizers; phiên bản và quyền attach vẫn quan trọng. Trên JDK hiện đại, Oracle khuyến nghị dùng `jcmd` cho nhiều tác vụ chẩn đoán và kiểm tra command availability theo JDK thực.

Không thu dump bằng cách chọn nhầm PID, nhất là khi máy chạy nhiều JVM; xác minh process start time/instance, quyền, host/container PID namespace và bản JDK. Nếu attach bị vô hiệu hoặc process đã thoát, công cụ không tự vượt qua giới hạn đó.

### 6.3 ThreadMXBean.dumpAllThreads qua Java API

Trong JVM hiện tại:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.lang.management.ThreadInfo;

ThreadMXBean mx = ManagementFactory.getThreadMXBean();
if (mx.isObjectMonitorUsageSupported()
        && mx.isSynchronizerUsageSupported()) {
    ThreadInfo[] infos = mx.dumpAllThreads(true, true);
}
```

Đây là **đoạn minh họa**, cần đặt trong method/class. `dumpAllThreads(true,true)` yêu cầu cả locked monitors và locked ownable synchronizers. Trên Java 17, method trả thông tin các **platform threads** sống được JVM công bố; tính năng quan sát lock có thể không được hỗ trợ bởi một JVM implementation và ném `UnsupportedOperationException` nếu yêu cầu tính năng không hỗ trợ.

Nếu không cần toàn bộ threads, dùng `getThreadInfo(long[], boolean, boolean)` với IDs đã xác định. Thu nhiều lần, stack quá sâu hoặc application hàng nghìn threads có thể tạo chi phí CPU, memory và pause; không xem thao tác dump là hoàn toàn miễn phí.

### 6.4 Chú ý virtual threads trong Java 21+

JDK 21 đưa virtual threads thành tính năng chính thức. `ThreadMXBean.dumpAllThreads(...)` và các method deadlock detection được tài liệu hóa cho **platform threads**, không phải bản kiểm kê đầy đủ mọi virtual thread. Các công cụ thread dump có định dạng/cách hiển thị virtual threads khác nhau theo release.

Do đó khi service dùng virtual threads, thiếu tên một task trong platform thread dump **không chứng minh task ấy không tồn tại hay không chờ lock**. Cần công cụ/format hỗ trợ virtual threads của JDK đang chạy, JFR hoặc instrumentation phù hợp; không suy áp mọi parser HotSpot đời cũ vào output mới.

## 7. Đọc ThreadInfo và ThreadMXBean ở mức API

`ThreadInfo` là cấu trúc dữ liệu Java dùng để biểu diễn một snapshot thread ở một thời điểm. Các phương thức quan trọng:

| API | Ý nghĩa | Giới hạn cần nhớ |
| --- | --- | --- |
| `getThreadName()` | Tên thread | Có thể bị đặt động, chứa ID nhạy cảm |
| `getThreadId()` | Java thread ID | Không phải OS PID hoặc `nid` trong dump |
| `getThreadState()` | State tại snapshot | Có thể thay đổi ngay sau khi lấy |
| `getLockInfo()` | Lock/blocker object mà thread đang chờ, nếu có | `null` nếu không thuộc trường hợp hỗ trợ |
| `getLockOwnerId()` | ID thread sở hữu object thread đang chờ, nếu biết | `-1` khi không có/không biết owner |
| `getLockOwnerName()` | Tên owner, nếu có | `null` không chứng minh không có lock |
| `getLockedMonitors()` | Monitors thread đang giữ | Rỗng nếu không yêu cầu capture hoặc không giữ |
| `getLockedSynchronizers()` | Ownable synchronizers thread đang giữ | Không liệt kê mọi primitive đồng bộ |
| `getStackTrace()` | Stack trace đã được thu | Có thể rỗng nếu không yêu cầu |
| `getBlockedCount()` | Số lần bị block khi cố vào monitor | Counter, không tự cho duration từng event |
| `getBlockedTime()` | Thời gian block tích lũy khi contention monitoring bật | Có thể `-1` nếu không có số liệu |
| `getWaitedCount()` | Số lần wait/park theo semantics JVM | Không tự chỉ ra owner của mọi wait |
| `getWaitedTime()` | Thời gian chờ tích lũy khi được hỗ trợ/bật | Có thể `-1` và không phải latency p99 |

### 7.1 Một LockInfo không có nghĩa thread chờ object có owner

Theo Javadoc, `getLockInfo()` có thể mô tả:

- Monitor mà thread `BLOCKED` đang cố vào.
- Object monitor thread đang `wait()` để được notify.
- Blocker object của `LockSupport.park`, có thể là ownable synchronizer hoặc `Condition`.

Với `Object.wait`, object có thể **không có owner độc quyền** tại thời điểm thread chờ, vì waiter đã nhả monitor. Với `LockSupport.park` trên latch/condition, blocker có thể không có owner kiểu mutex. Vì vậy `getLockInfo()!=null` không đồng nghĩa “có thread khác đang giữ khóa”.

`getLockOwnerId() == -1` nói **owner không được xác định theo API** hoặc không có owner cho object đang chờ. Đừng in `-1` thành một thread ID thật; cũng không nên suy “không bao giờ có contention” chỉ vì một snapshot không tìm được owner.

### 7.2 Phân biệt class name, identity hash và text address

`LockInfo` cung cấp `getClassName()` và `getIdentityHashCode()`, dùng để mô tả object lock. Trong dump HotSpot, marker `<0x...>` thường là một định danh dạng hex khác với `System.identityHashCode`; **không tự ép chúng bằng cách đổi hệ cơ số**. Nếu muốn liên kết thông tin từ hai nguồn, phải xác minh semantics của tool, JVM, thời điểm, object identity và tính ổn định.

Object identity cũng không ổn định qua restart; JVM có thể tái sử dụng địa chỉ/hash trong một số bối cảnh. Nên so lock identity **trong cùng artifact/snapshot** và ghi timestamp/PID/JVM instance.

### 7.3 MonitorInfo và vị trí lấy monitor

`MonitorInfo.getLockedStackDepth()`/`getLockedStackFrame()` giúp trả lời “monitor được lấy ở frame nào?” nếu JVM cung cấp dữ liệu. Đây là khác biệt có ích so với ownable `LockInfo`: **không** mong `getLockedSynchronizers()` tự cung cấp source line nơi `ReentrantLock.lock()` xảy ra.

Phải đối chiếu source code thực, optimization và stack đầy đủ nếu muốn xác minh critical section. Không kết luận một line number trong dump tương đương chính xác với khoảng thời gian giữ lock.

### 7.4 Các chỉ số contention không tự bật trên mọi JVM

`ThreadMXBean.isThreadContentionMonitoringSupported()` trả tình trạng hỗ trợ; `isThreadContentionMonitoringEnabled()` cho biết đang bật không. Mặc định ở nhiều JVM, blocked/waited elapsed time chưa được thu, nên `getBlockedTime()`/`getWaitedTime()` có thể là `-1`. Bật monitoring bằng `setThreadContentionMonitoringEnabled(true)` là **thay đổi runtime có overhead** và cần quyền/chính sách vận hành; không bật tùy tiện trong một demo read-only.

Count/time tích lũy cũng không phải event-level latency; khi cần p95 lock wait, phải instrument một histogram hoặc dùng profiler/JFR phù hợp, không lấy tổng chia count rồi gọi p99.

## 8. Ví dụ Java 17+ hoàn chỉnh: tạo contention và quan sát cả hai loại lock

Chương trình sau **chỉ dùng API tiêu chuẩn Java 17+**, tạo **bốn platform threads mô phỏng trong chính JVM**:

- Một thread giữ monitor `synchronized`; thread khác cố vào monitor, thường `BLOCKED`.
- Một thread giữ `ReentrantLock`; thread khác gọi `lock()`, thường `WAITING (parking)`.
- Main thread gọi `ThreadMXBean.getThreadInfo(ids,true,true)` và in thông tin snapshot.
- Mọi khóa được thả trong `finally`, không tạo intentional deadlock, không kill threads, không attach JVM khác.

Có **chế độ mặc định** giải thích mô hình bằng stdout xác định; `--live` mới tạo threads và đọc số liệu thật nên kết quả tùy JDK/scheduler. Đây là cách phân biệt kiến thức ổn định với quan sát **có race**.

Lưu file `ThreadLockReadingDemo.java`:

```java
import java.lang.management.LockInfo;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class ThreadLockReadingDemo {
    static void printModel() {
        System.out.println("MONITOR_ENTRY=BLOCKED");
        System.out.println("OBJECT_WAIT=RELEASES_WAITED_MONITOR");
        System.out.println("REENTRANT_LOCK_WAIT=USUALLY_PARKING");
        System.out.println("OWNABLE_SECTION=LOCKED_OWNABLE_SYNCHRONIZERS");
        System.out.println("THREAD_DUMP=ONE_SNAPSHOT_NOT_DEADLOCK_PROOF");
    }

    static void awaitRelease(CountDownLatch release) {
        try {
            release.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    static void report(String alias, ThreadInfo info) {
        if (info == null) {
            System.out.println(alias + ".info=UNAVAILABLE");
            return;
        }

        LockInfo awaited = info.getLockInfo();
        System.out.println(alias + ".state=" + info.getThreadState());
        System.out.println(alias + ".waiting_lock_present=" + (awaited != null));
        System.out.println(alias + ".owner_known="
                + (info.getLockOwnerId() >= 0));
        System.out.println(alias + ".monitors_held="
                + info.getLockedMonitors().length);
        System.out.println(alias + ".ownable_held="
                + info.getLockedSynchronizers().length);
    }

    static void runLive() throws Exception {
        ThreadMXBean mx = ManagementFactory.getThreadMXBean();
        if (!mx.isObjectMonitorUsageSupported()
                || !mx.isSynchronizerUsageSupported()) {
            System.out.println("LIVE_LOCK_DETAILS=UNSUPPORTED");
            return;
        }

        Object monitor = new Object();
        ReentrantLock ownable = new ReentrantLock();
        CountDownLatch monitorReady = new CountDownLatch(1);
        CountDownLatch ownableReady = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread monitorOwner = new Thread(() -> {
            synchronized (monitor) {
                monitorReady.countDown();
                awaitRelease(release);
            }
        }, "demo-monitor-owner");

        Thread ownableOwner = new Thread(() -> {
            ownable.lock();
            try {
                ownableReady.countDown();
                awaitRelease(release);
            } finally {
                ownable.unlock();
            }
        }, "demo-ownable-owner");

        Thread monitorWaiter = new Thread(() -> {
            synchronized (monitor) {
                // Chỉ hoàn tất sau khi monitorOwner nhả monitor.
            }
        }, "demo-monitor-waiter");

        Thread ownableWaiter = new Thread(() -> {
            ownable.lock();
            try {
                // Chỉ hoàn tất sau khi ownableOwner unlock.
            } finally {
                ownable.unlock();
            }
        }, "demo-ownable-waiter");

        try {
            monitorOwner.start();
            ownableOwner.start();

            if (!monitorReady.await(3, TimeUnit.SECONDS)
                    || !ownableReady.await(3, TimeUnit.SECONDS)) {
                System.out.println("LIVE_SETUP=TIMED_OUT");
                return;
            }

            monitorWaiter.start();
            ownableWaiter.start();

            // Hạn chế race cho demo; không biến snapshot thành nguyên tử.
            for (int i = 0; i < 100; i++) {
                boolean monitorBlocked =
                        monitorWaiter.getState() == Thread.State.BLOCKED;
                boolean ownableWaiting =
                        ownableWaiter.getState() == Thread.State.WAITING
                        || ownableWaiter.getState()
                                == Thread.State.TIMED_WAITING;
                if (monitorBlocked && ownableWaiting) {
                    break;
                }
                Thread.sleep(10);
            }

            long[] ids = {
                monitorOwner.getId(), monitorWaiter.getId(),
                ownableOwner.getId(), ownableWaiter.getId()
            };
            ThreadInfo[] infos = mx.getThreadInfo(ids, true, true);

            String[] names = {
                "MONITOR_OWNER", "MONITOR_WAITER",
                "OWNABLE_OWNER", "OWNABLE_WAITER"
            };
            for (int i = 0; i < names.length; i++) {
                report(names[i], infos[i]);
            }
        } finally {
            release.countDown();
            monitorOwner.join(2000);
            ownableOwner.join(2000);
            monitorWaiter.join(2000);
            ownableWaiter.join(2000);
        }
    }

    public static void main(String[] args) throws Exception {
        printModel();
        if (args.length == 1 && "--live".equals(args[0])) {
            runLive();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac ThreadLockReadingDemo.java
java ThreadLockReadingDemo
```

**Stdout chính xác ở chế độ mặc định**:

```text
MONITOR_ENTRY=BLOCKED
OBJECT_WAIT=RELEASES_WAITED_MONITOR
REENTRANT_LOCK_WAIT=USUALLY_PARKING
OWNABLE_SECTION=LOCKED_OWNABLE_SYNCHRONIZERS
THREAD_DUMP=ONE_SNAPSHOT_NOT_DEADLOCK_PROOF
```

Đây là **mô hình khái niệm được in từ code**, không phải kết quả quan sát thread của một lần chạy cụ thể.

Để quan sát thực tế:

```bash
java ThreadLockReadingDemo --live
```

Chương trình in cùng năm dòng mô hình trước, sau đó là các dòng trạng thái có tiền tố `MONITOR_OWNER.`, `MONITOR_WAITER.`, `OWNABLE_OWNER.`, `OWNABLE_WAITER.`. **Đầu ra live không cố định**, vì thread state/scheduler/JVM support có thể khác lúc lấy mẫu. Trên một HotSpot/JDK phù hợp, thường thấy:

- `MONITOR_OWNER.monitors_held` lớn hơn 0 khi owner đang giữ monitor.
- `MONITOR_WAITER.state=BLOCKED` và có `waiting_lock_present=true`.
- `OWNABLE_OWNER.ownable_held` lớn hơn 0 nếu `ReentrantLock` được JVM báo là ownable synchronizer.
- `OWNABLE_WAITER.state=WAITING` hoặc `TIMED_WAITING` và có blocker object nếu đang đợi lấy lock.

Đây là **kỳ vọng có điều kiện**, không phải stdout tuyệt đối của mọi JDK/OS. Nếu JVM không hỗ trợ quan sát cả hai nhóm lock, sẽ có dòng `LIVE_LOCK_DETAILS=UNSUPPORTED`. Nếu threads không đến trạng thái sẵn sàng trong thời hạn chờ, có thể có `LIVE_SETUP=TIMED_OUT`. Câu lệnh vẫn không tạo deadlock có chủ ý.

### 8.1 Tại sao giữ latch khi đang cầm khóa?

`monitorOwner` giữ monitor trong khi chờ `release.await()`, cho phép `monitorWaiter` thực sự phải đợi vào monitor. `ownableOwner` giữ `ReentrantLock` và cũng chờ latch, làm `ownableWaiter` phải đợi `lock()`. Đó là mô phỏng **long hold có kiểm soát**, không phải ví dụ production tốt: giữ lock trong khi đợi điều kiện khác có thể gây contention nghiêm trọng.

`CountDownLatch.await()` ở hai owners khiến owner **WAITING**, nhưng chúng vẫn giữ monitor/ownable lock đã lấy. Điều này chứng minh **trạng thái WAITING của owner không có nghĩa owner đã nhả mọi khóa**.

### 8.2 Vì sao dùng ThreadMXBean thay vì in trực tiếp stack của các Thread?

`Thread.getAllStackTraces()` và `Thread.getStackTrace()` không cung cấp đầy đủ locked monitors/ownable synchronizers theo cùng contract. `ThreadMXBean.getThreadInfo(ids,true,true)` trả `ThreadInfo[]` với các field mà bài cần, có thể map theo ID. Kết quả có thể chứa `null` nếu thread tương ứng đã kết thúc trước lúc snapshot.

Trong production, nếu muốn giảm tác động, chỉ đọc IDs đã xác định. Với nhiều threads, `dumpAllThreads(true,true)` có chi phí phụ thuộc số threads/stack depth; không gọi liên tục mỗi vài mili giây để “bắt đúng deadlock” nếu hệ thống đang gặp áp lực.

### 8.3 Khi cần xem class name hoặc lock owner ID chi tiết

Đoạn `report` in owner **có biết hay không**, thay vì in số ID thay đổi mỗi lần. Khi làm chẩn đoán thật, có thể thêm:

```java
LockInfo waitingFor = info.getLockInfo();
if (waitingFor != null) {
    String lockClass = waitingFor.getClassName();
    int identityHash = waitingFor.getIdentityHashCode();
    long ownerId = info.getLockOwnerId();
}
```

Đây là **đoạn minh họa đặt trong method với `ThreadInfo info`**, không phải file độc lập. `getLockOwnerId()` có thể là `-1` khi không có/không xác định owner. Khi đối chiếu lock IDs, dùng cùng snapshot và ý nghĩa object identity do API cung cấp; không cố chuyển số ID thành địa chỉ vùng nhớ và truy cập trực tiếp.

## 9. Dựng đồ thị “ai chờ ai” từ thread dump

Một cách đọc có hệ thống:

1. Liệt kê các thread đang **BLOCKED trên monitor** và các thread **WAITING/TIMED_WAITING do park** ở stack liên quan lock.
2. Với mỗi thread chờ, ghi lock identity (cùng snapshot) và owner ID nếu có.
3. Tìm thread chủ sở hữu bằng `- locked` hoặc `Locked ownable synchronizers`/`ThreadInfo.getLockOwnerId()`.
4. Vẽ một cạnh **waiter → owner**, kèm loại lock và trạng thái/timestamp.
5. Đọc stack của owner: nó đang làm công việc dài, chờ I/O, chờ điều kiện khác hay lại đợi thêm một lock?
6. Nếu owner lại chờ lock do thread thứ ba giữ, tiếp tục cho đến khi tới thread có thể tiến triển hoặc một chu trình.
7. Xác nhận cạnh bằng snapshot khác; một cạnh có thể biến mất vì lock đã được nhả.

Ví dụ đồ thị **giả định**:

```text
T-worker-3 --waits monitor A--> T-worker-1
T-worker-4 --waits monitor A--> T-worker-1
T-worker-1 --waits DB response--> external service
```

Đây **không phải Java monitor deadlock cycle** theo nghĩa chặt. Đó là **lock convoy**: nhiều workers bị kẹt sau owner đang chờ I/O. Có thể khắc phục bằng giảm công việc bên trong critical section, xử lý I/O ngoài monitor, timeout và tối ưu bottleneck — nhưng phải phân tích ngữ cảnh và side effects.

Một đồ thị khác:

```text
Thread A --waits monitor L2--> Thread B
Thread B --waits monitor L1--> Thread A
```

Nếu mỗi thread **đang giữ** lock mà thread kia muốn, đây là chu trình phù hợp với deadlock. Cần kiểm chứng owner IDs, lock IDs và trạng thái trong cùng ảnh chụp; không dựng cycle từ các lock identifiers lấy ở các JVM/restarts khác nhau.

### 9.1 Bảng ghi nhận để tránh nhầm

| Trường | Ví dụ | Vì sao cần |
| --- | --- | --- |
| Capture timestamp | 2026-10-29T08:00:00Z | So sánh các snapshots |
| JVM identity | service-A, instance-1, process start | Không nối dump từ JVM khác |
| Thread alias | worker-3 | Tên có thể chứa PII nên dùng alias khi chia sẻ |
| Java thread ID | 42 | So owner ID trong cùng JVM |
| State | BLOCKED | Phân loại kiểu chờ |
| Waiting lock | Object@hash-A | Ghép với owner |
| Owner alias/ID | worker-1 / 41 | Dựng cạnh waits-for |
| Held monitors | Object@hash-A | Xác minh monitor ownership |
| Held synchronizers | AQS@hash-B | Xác minh ownable lock |
| Relevant stack | Service.update / RemoteCall | Xác định vùng code giữ/chờ khóa |
| Next observation | State sau 5 giây | Phân biệt transient và kéo dài |

Toàn bộ giá trị trong bảng là **mẫu giả**, không phải dữ liệu thực. Không đưa raw hostname, email, request payload hoặc token vào bản chia sẻ ngoài phạm vi.

## 10. Deadlock detection: vì sao một snapshot chưa đủ?

### 10.1 Monitor deadlock

Một chu trình classic có hai threads:

```java
// Thread A:
synchronized (lockA) {
    synchronized (lockB) { /* ... */ }
}

// Thread B:
synchronized (lockB) {
    synchronized (lockA) { /* ... */ }
}
```

Hai đoạn này chỉ là **minh họa lock-order inversion**, không phải chương trình độc lập và không nên chạy trên JVM production. Nếu A đã giữ `lockA`, B giữ `lockB` rồi cả hai cố lấy khóa còn lại, có thể tạo deadlock vĩnh viễn trừ khi process bị can thiệp hoặc có cơ chế thoát phù hợp.

Thread dump có thể thể hiện:

- A `- locked lockA`, `- waiting to lock lockB`.
- B `- locked lockB`, `- waiting to lock lockA`.

**Không** suy từ việc hai threads đều BLOCKED rằng chúng chắc chắn đợi nhau: có thể cả hai cùng chờ **một thread thứ ba**.

### 10.2 Ownable synchronizer deadlock

`ReentrantLock` cũng có thể tạo chu trình nếu thread A giữ lock1 chờ lock2, thread B giữ lock2 chờ lock1. Các waiters thường `WAITING (parking)`, không phải `BLOCKED`. Một rule detector chỉ tìm `Thread.State.BLOCKED` sẽ **bỏ sót** các deadlock liên quan ownable synchronizers.

### 10.3 ThreadMXBean hỗ trợ những phép phát hiện nào?

| API | Loại deadlock được hướng tới | Lưu ý |
| --- | --- | --- |
| `findMonitorDeadlockedThreads()` | Cycles của platform threads chờ lấy **object monitors** | Không bao quát ownable synchronizers |
| `findDeadlockedThreads()` | Cycles của platform threads chờ **object monitors hoặc ownable synchronizers** | Có thể không được JVM hỗ trợ và có chi phí |
| `isSynchronizerUsageSupported()` | JVM có hỗ trợ theo dõi ownable synchronizers? | Phải kiểm tra trước khi yêu cầu tính năng |
| `isObjectMonitorUsageSupported()` | JVM có hỗ trợ theo dõi monitors? | Phải kiểm tra trước khi thu locked monitors |

`findDeadlockedThreads()` có thể trả `null` khi không tìm thấy deadlock thuộc phạm vi hỗ trợ. **`null` không chứng minh hệ thống không có mọi dạng liveness failure**: ví dụ thread pool starvation, wait vô hạn không thành cycle, I/O treo, queue mất worker, deadlock liên quan resource bên ngoài hoặc virtual threads (ở các API/version không bao quát) có thể không được phát hiện.

### 10.4 Không dùng deadlock detector để thay phân tích nguyên nhân

Ngay cả khi tool báo “Found one Java-level deadlock”, cần xem code:

- Những locks nào bị lấy theo thứ tự trái ngược?
- Có thể loại một lock, thu hẹp critical section, thống nhất lock order không?
- Có gọi I/O/await trong lock hoặc trộn intrinsic monitors với ownable locks không?
- Một operation có side effects nếu timeout/interrupt xảy ra không?
- Có cần thiết kế retry/timeout/cancellation thay vì chỉ tăng pool size không?

**Không** cố khắc phục bằng tăng CPU, tăng heap hoặc tăng số worker nếu nguyên nhân là cycle giữ khóa. Những thao tác đó có thể không phá deadlock mà chỉ tăng số threads chờ.

## 11. Đọc nhiều thread dumps mà không tự đánh lừa mình

### 11.1 Vì sao cần chuỗi snapshots?

Một dump mô tả **một thời điểm**, nhưng ta muốn biết “đứng yên trong 30 giây” hoặc “điều kiện này lặp lại dưới tải”. Thu một vài snapshots cách nhau có chủ đích có thể cho biết:

- Cùng lock identity/owner/call stack tồn tại qua nhiều snapshot của cùng JVM.
- Số waiters trên monitor tăng hay giảm.
- Owner đang chờ I/O lâu hay thay đổi stack.
- Một thread có tiến triển, đổi state, hoặc biến mất vì request hoàn tất.
- Có cycle liên tục hay chỉ contention ngắn.

Ví dụ, 3 lần dump cách nhau vài giây trong một incident có thể hữu ích hơn hàng trăm lần lấy mẫu dồn dập. **Không có cadence mặc định cho mọi JVM**: phải cân nhắc số lượng threads, pause/overhead, yêu cầu incident và chính sách lấy dữ liệu.

### 11.2 Những thông tin phải giữ khi so

- JVM PID cùng **start time/instance**, không chỉ số PID (PID có thể được tái sử dụng).
- Timestamp UTC và khoảng cách đo thực.
- Java/JVM vendor/version, collector/container scope nếu cần.
- Tool dùng và flags như `Thread.print -l`.
- Số thread, trạng thái, lock/object identity trong **cùng snapshot**.
- Application workload: traffic/latency/CPU, state của dependency/DB.
- Nội dung đã redact nhưng vẫn giữ mapping alias nhất quán cho cùng incident.

Không ghép những monitor IDs giống nhau từ hai lần JVM restart rồi gọi đó là cùng object.

### 11.3 Đọc sample bị cắt hoặc không đầy đủ

Dump nhiều nghìn threads có thể rất lớn; output terminal, log collector hoặc file transfer có thể bị cắt. Nếu thấy waiter nhưng không thấy owner, có thể owner nằm ở phần bị cắt hoặc VM/tool không cung cấp ownership. Đừng tự kết luận owner là “system thread bí ẩn”.

Nên kiểm tra số lượng thread sections, phần cuối artifact, lỗi collector, exit code của lệnh và dung lượng file. Nếu phải chia sẻ, dùng artifact ở nơi được cấp quyền và trích xuất đã rà soát bảo mật; raw dump có thể chứa thread names, class names, file paths, request/session IDs hoặc URL nhạy cảm.

## 12. Phân biệt monitor wait với Condition.await và LockSupport.park

### 12.1 Object.wait() nhả monitor được wait

Ví dụ:

```java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
}
```

Trong pha wait, thread **không còn giữ monitor của `monitor`**. Khi thread được đánh thức do notify, interrupt hoặc spurious wakeup, nó phải reacquire monitor. Vì thế luôn dùng `while` kiểm tra điều kiện lại, không dùng `if` dựa vào giả định “notify đảm bảo điều kiện đúng”.

### 12.2 Condition.await() nhả associated ReentrantLock

Với `Condition` tạo từ `ReentrantLock.newCondition()`:

```java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
} finally {
    lock.unlock();
}
```

`condition.await()` nhả khóa được liên kết trong khi chờ (và giành lại trước khi trả về theo contract). Ở snapshot đang WAITING trên Condition, **đừng mặc định thread vẫn sở hữu associated ReentrantLock**. Dù vậy, nó có thể giữ những khóa khác ngoài lock liên quan. Condition operations có semantics về interrupt/timed wait khác nhau; xem Javadoc trước khi suy về lifecycle.

### 12.3 LockSupport.park() không phải Object.wait()

`LockSupport.park()` không yêu cầu thread sở hữu monitor của blocker và **không tự giải phóng tất cả locks** mà thread đang cầm. Khi một thread park trong khi giữ monitor hoặc ReentrantLock, các thread khác có thể chờ nó. Nếu dump có `parking to wait for`, đó có thể là một `ConditionObject`, AQS sync, latch hoặc scheduler; phải xem stack và loại blocker.

### 12.4 Tình huống không có owner

Ví dụ thread pool worker park trên work queue vì không có task. Trong đồ thị chờ, đây không phải cạnh tới một owner khóa cụ thể; nó chờ producer/điều kiện tương lai. Deadlock detector dựa trên object monitor/ownable cycles không phát hiện mọi trường hợp “không ai sẽ gửi task”.

Bởi vậy khi thao tác với `ThreadInfo.getLockOwnerId() == -1`, kết luận phù hợp là “không có owner được báo ở snapshot”, **không phải** “thread này chắc chắn an toàn”.

## 13. Phân tích các tình huống thực tế

### 13.1 Web request pool kẹt sau một synchronized method

**Quan sát giả định:** 50 worker threads `BLOCKED`, cùng `waiting to lock` một monitor. Owner là request worker đang `WAITING` tại network call trong `synchronized`.

**Giải thích:** đây có thể là **lock convoy** do critical section ôm I/O; latency tăng do owner không nhả khóa, nhiều request bị xếp hàng. Cần đo duration của I/O, xác minh owner vẫn giữ monitor qua snapshots, xem timeout và business consistency.

**Hướng cải thiện:** tách phần I/O ra ngoài critical section khi đúng semantics, giảm phạm vi synchronization, dùng cơ chế đồng bộ phù hợp và timeout. Không vội xóa `synchronized` nếu còn race condition dữ liệu.

### 13.2 Một ReentrantLock bị giữ bởi thread đang chờ latch

**Quan sát giả định:** nhiều waiters ở `WAITING (parking)` trong AQS; một owner có `Locked ownable synchronizers` tương ứng nhưng lại `WAITING` ở `CountDownLatch.await()`.

**Giải thích:** không phải mọi WAITING đều vô hại. Owner giữ một mutex trong khi đợi điều kiện khác, khiến các waiters bị kẹt. Cần tìm ai sẽ `countDown()` và có phụ thuộc ngược vào lock đó không.

Nếu producer cần lấy chính lock owner đang giữ để phát signal, có thể tạo vòng chờ **không được biểu diễn đơn giản bằng một chu trình hai ownable locks**. Cần đọc flow của ứng dụng và task scheduling, không trông chờ `findDeadlockedThreads()` phát hiện mọi kiểu liveness failure.

### 13.3 Đồ thị A → B → C nhưng không có cycle

**Quan sát giả định:** A chờ monitor của B, B chờ ReentrantLock của C, C đang xử lý CPU liên tục hoặc đợi DB.

**Giải thích:** vấn đề có thể là **bottleneck ở C**. Chưa phải deadlock nếu C có thể tiến triển và nhả khóa. Đo CPU, stack sau một khoảng, độ trễ DB và thời gian giữ lock; có thể là contention/choke point.

### 13.4 Hai threads đều BLOCKED nhưng không đợi nhau

**Quan sát giả định:** T1 và T2 cùng `waiting to lock <M>`, còn T3 giữ M. Không có cạnh T1 → T2 hoặc T2 → T1.

**Giải thích:** nhiều contenders trên một lock không tạo deadlock hai chiều; kiểm tra T3. Các chỉ số queue/concurrent request có thể giúp biết mức độ nghiêm trọng.

### 13.5 Mục ownable synchronizers in - None

**Quan sát:** một thread `BLOCKED` chờ `synchronized`, nhưng phần `Locked ownable synchronizers` ghi `- None`.

**Giải thích:** nó không được JVM báo đang giữ ownable synchronizer. Điều này **không phủ nhận** nó đang chờ monitor, hay owner ở thread khác. Cần đọc monitor markers và stack; hai nhóm không thay nhau.

### 13.6 JVM không báo owner và getLockOwnerId() == -1

**Quan sát:** một thread `WAITING` ở `LockSupport.park`, `getLockInfo()` có object nhưng owner id là `-1`.

**Giải thích:** blocker có thể không có khái niệm owner, tool không thu được thông tin, hoặc trạng thái thay đổi. Đọc primitive trong stack và lifecycle của condition/permit; đừng tự dựng owner giả.

### 13.7 Virtual threads khiến danh sách có vẻ thiếu

**Quan sát:** service Java 21 dùng virtual threads, nhưng `ThreadMXBean.dumpAllThreads(true,true)` chỉ thấy ít platform threads hơn request concurrency.

**Giải thích:** đó là giới hạn API/công cụ, không tự chứng minh tất cả request đã hoàn thành. Sử dụng dump/diagnostic hỗ trợ virtual threads theo đúng JDK, instrumentation và application traces. Không dùng `ThreadMXBean` như số lượng virtual tasks tuyệt đối.

## 14. Lỗi phân tích thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| “BLOCKED nghĩa là deadlock.” | Nhầm contention ngắn với cycle vĩnh viễn | Tìm owner/cycle, so nhiều snapshots |
| “WAITING nghĩa thread không giữ khóa.” | Bỏ sót owner chờ latch/I/O trong critical section | Xem `- locked` và ownable section |
| “- locked nghĩa thread đang chờ monitor.” | Đảo ngược mối quan hệ | `- locked` là **đang sở hữu**, `waiting to lock` mới là muốn lấy |
| “waiting on = waiting to lock.” | Nhầm `Object.wait()` với monitor entry | Đọc stack/state và semantics nhả monitor |
| “parking = blocked trên synchronized.” | Bỏ sót AQS/Condition/pool wait | Xem `LockSupport` stack và ownable locks |
| “ThreadInfo.getLockInfo() != null là owner known.” | Gán owner giả cho condition/latch | Xem `getLockOwnerId()` và primitive |
| “Ownable - None nghĩa không giữ khóa nào.” | Bỏ qua object monitors và các primitives khác | Đọc cả held monitors/synchronizers |
| “jcmd -l giúp in full locks.” | Nhầm option list JVM với option Thread.print | Dùng `jcmd PID Thread.print -l` |
| “Một lock ID giống qua hai JVM là cùng object.” | Lập graph sai do identity tái sử dụng | So trong cùng JVM/snapshot |
| “Một snapshot cho biết thread bị block 30 giây.” | Không có duration trực tiếp | Lấy snapshots/contended-time đã cấu hình |
| “Count blocked = time blocked.” | Counter và elapsed khác đơn vị | Đọc đúng `getBlockedCount/Time` |
| “MBean rỗng nghĩa Java không có locks.” | Có thể chưa bật capture/support hoặc chỉ platform threads | Kiểm tra flags/support/APIs |
| “findDeadlockedThreads null = không có liveness bug.” | Bỏ sót queue/I/O/starvation/virtual threads | Kết hợp traces, metrics và source |
| “Có nhiều WAITING thì tăng thread pool.” | Có thể tăng contention và memory | Tìm nguyên nhân wait và bottleneck |
| “Dump chỉ là stack, an toàn public.” | Thread names/paths/request IDs có thể nhạy cảm | Chia sẻ bản lọc theo chính sách |
| “jcmd Thread.print luôn rất nhẹ.” | Cost tăng theo số threads/stack depth | Thu có mục đích, thời hạn và quyền |

## 15. Quy trình xử lý incident mà không làm mất bằng chứng

Khi gặp throughput giảm hoặc requests treo:

1. **Khoanh phạm vi:** service, JVM instance, PID trong đúng host/container namespace, khoảng thời gian UTC và symptoms như request p99/queue.
2. **Chọn command:** đọc help của JDK phù hợp, thu thread dump có `-l` nếu cần ownable locks. Không dùng PID cũ/nhầm replica, không chạy script thu liên tục vô hạn.
3. **Bảo vệ artifacts:** lưu dump trong kênh hạn chế quyền; rà soát thread names, stack, URL, user/session IDs trước khi chia sẻ.
4. **Phân loại threads:** BLOCKED monitor entry, WAITING on Object.wait, WAITING/TIMED_WAITING park, RUNNABLE/native I/O.
5. **Tìm lock identity:** ghi đúng từng `waiting to lock`/`parking`/`locked`, phân biệt monitor và ownable sync.
6. **Ghép owner:** đối chiếu owner IDs/held-lock lists trong cùng snapshot; đánh dấu UNKNOWN khi không biết.
7. **Vẽ waits-for graph:** tập trung những locks có nhiều contenders, hoặc chu trình; phân biệt cycle và chain kết thúc ở I/O/CPU/work queue.
8. **Chụp lại có kiểm soát:** so stacks/states, số waiters, lock identity và application metrics để xác minh kéo dài/đang tiến triển.
9. **Tìm source root cause:** critical section dài, lock order đảo, missing signal, blocking I/O, executor starvation hoặc configuration.
10. **Khắc phục có kiểm soát:** thay đổi code/timeout/lock order và kiểm thử; khi cần restart, tuân thủ runbook và thu đủ bằng chứng trước.
11. **Hậu kiểm:** so throughput/latency/blocked time/busy threads, số lock waiters và khả năng tái hiện; không tuyên bố fix chỉ vì một dump sau đó ít thread BLOCKED.

Không thử ngắt thread tùy tiện bằng `Thread.stop()` (đã deprecated/không an toàn), xóa monitor bằng reflection hoặc kill JVM production để “phá lock” khi chưa có quyền và chưa hiểu tác động.

## 16. Checklist đọc một thread dump

- [ ] Xác định chính xác JVM instance/PID, JDK/version và thời điểm chụp.
- [ ] Dump có thông tin monitor và ownable synchronizers phù hợp nhu cầu (`-l` hoặc MXBean flags).
- [ ] Phân biệt state `BLOCKED`, `WAITING`, `TIMED_WAITING` và `RUNNABLE` theo stack, không chỉ nhãn.
- [ ] Đọc `- locked` là **held monitor**, không nhầm với waiting.
- [ ] Đọc `- waiting to lock` là **monitor entry blocked**.
- [ ] Đọc `- waiting on` là **Object.wait/notification**, có nhả monitor đang wait.
- [ ] Đọc `- parking to wait for` cùng loại primitive (AQS, Condition, latch, pool).
- [ ] Phần `Locked ownable synchronizers` chỉ nói về ownable locks, không thay toàn bộ monitor list.
- [ ] So lock IDs/`LockInfo` trong **cùng snapshot** để tìm owner.
- [ ] Kiểm tra `getLockOwnerId()==-1` và các trường không có dữ liệu, không tự invent owner.
- [ ] Đọc stack của **owner**: công việc dài, blocking I/O, chờ điều kiện hay lấy thêm lock?
- [ ] Có phân biệt lock convoy/long hold với deadlock cycle thực sự?
- [ ] Nếu có virtual threads, đã xem giới hạn `ThreadMXBean` và tool chưa?
- [ ] Có cân nhắc overhead của việc thu nhiều thread dumps và retention?
- [ ] Có đối chiếu thêm latency/CPU/queue/GC/DB traces ở cùng time window?
- [ ] Raw dump và các định danh nhạy cảm được lưu/chia sẻ đúng quyền?
- [ ] Những kết luận đều gắn **bằng chứng**, còn điểm chưa rõ được ghi “chưa xác minh”.

## 17. Bài tập tự kiểm tra

**Câu 1.** Thread A in `- locked <L>`. Thread B in `- waiting to lock <L>` với `BLOCKED`. Có thể kết luận gì?

**Đáp án:** Trong snapshot đó, A có bằng chứng đang giữ monitor `L` và B đang đợi để vào monitor `L`. Chưa đủ kết luận deadlock: cần biết A có đợi khóa do B giữ hoặc có thể hoàn thành critical section không.

**Câu 2.** Thread C ở `WAITING` nhưng có `Locked ownable synchronizers` chứa AQS sync. C có giữ lock không?

**Đáp án:** Có bằng chứng C đang giữ ownable synchronizer tương ứng theo dump, dù C đang WAITING. C có thể giữ `ReentrantLock` trong khi chờ latch/park trên đối tượng khác.

**Câu 3.** Tại sao `Thread.State.BLOCKED` không phải điều kiện bắt buộc của ReentrantLock contention?

**Đáp án:** `BLOCKED` dành cho monitor entry. ReentrantLock thường dùng AQS/LockSupport park; waiter có thể `WAITING` hoặc `TIMED_WAITING`.

**Câu 4.** `getLockInfo()` trả một object nhưng `getLockOwnerId() == -1`. Có phải JVM bug?

**Đáp án:** Không. Object có thể là blocker của Condition/latch hoặc owner không được xác định; cần đọc stack/primitive. Không có owner được báo không phải lỗi chắc chắn.

**Câu 5.** Khi `Object.wait()` chạy trong `synchronized(monitor)`, thread có giữ monitor đó trong lúc WAITING không?

**Đáp án:** Không; `wait()` nhả monitor mà nó wait trên và phải lấy lại trước khi trả về. Nó có thể vẫn giữ những monitor khác.

**Câu 6.** Một dump có 100 threads `WAITING (parking)`, nhưng không có ownership cycle. Có phải chắc chắn không có lỗi tiến triển?

**Đáp án:** Không. Có thể thread pool starvation, mất signal, chờ external dependency, lock convoy hoặc cơ chế bất đồng bộ thiếu task. Không có cycle monitor/ownable vẫn có thể là liveness bug.

**Câu 7.** `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` khác nhau thế nào?

**Đáp án:** Phương thức đầu tìm cycle trên object monitors; phương thức sau còn tính ownable synchronizers theo support. Cả hai không phải bộ phát hiện mọi kiểu liveness failure và không bao quát mọi virtual thread theo API/version.

**Câu 8.** Vì sao không so `<0x...>` của dump A với dump B sau khi JVM restart?

**Đáp án:** Marker là identity nội bộ trong từng artifact/VM, có thể tái sử dụng. Cần ghi JVM instance/start time và chỉ đối chiếu trong phạm vi được đảm bảo.

**Câu 9.** Nếu một thread `- locked <M>` rồi stack ở `Thread.sleep`, điều gì đáng kiểm tra?

**Đáp án:** Thread giữ monitor khi ngủ; các contenders khác có thể bị chặn. Xem critical-section duration, vì sao sleep trong lock, stack owner và số waiters trước khi thay code.

**Câu 10.** Dòng `Locked ownable synchronizers: - None` có chứng minh thread không giữ `synchronized` monitor không?

**Đáp án:** Không. Đây là một loại danh sách riêng. Phải xem `- locked`/`getLockedMonitors()` cho monitors.

## Tài liệu tham khảo

- [Java SE 21 — ThreadInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html): thread state, `getLockInfo()`, owner, locked monitors, locked synchronizers và giới hạn snapshot.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): `dumpAllThreads`, `getThreadInfo`, hỗ trợ monitor/ownable usage và deadlock detection.
- [Java SE 21 — MonitorInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MonitorInfo.html): class/identity, lock acquisition stack depth/frame.
- [Java SE 21 — LockInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/LockInfo.html): tên lớp và identity hash code của lock object.
- [Java SE 21 — AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html): semantics owner độc quyền và giới hạn thông tin ownership.
- [Java SE 21 — ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock ownership, park, unlock và fairness.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `Thread.print`, option `-l` cho `java.util.concurrent` locks.
- [Oracle JDK 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): `jstack -l`, interpretation và cost của thread dumps.

**Ghi nhớ:** `- locked` nói về **khóa đã sở hữu**; `- waiting to lock` nói về **monitor muốn lấy**; `- waiting on` nói về **Object.wait()`; `- parking to wait for` cần đọc cùng stack vì có thể là AQS lock, Condition hoặc chờ không có owner. `Locked ownable synchronizers` bổ sung phần locks của `java.util.concurrent`, không thay cho monitors. Muốn chẩn đoán, hãy **nối waiter → lock → owner**, đọc stack của owner, xác minh thời gian/tính lặp và chỉ gọi deadlock khi có cycle phù hợp.