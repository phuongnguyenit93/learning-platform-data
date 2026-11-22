# 10.1 Quan hệ giữa virtual thread, carrier thread và platform thread trong Java 21

## Mục tiêu học tập

Java 21 đưa **virtual threads** thành tính năng chính thức của ngôn ngữ/nền tảng Java qua **JEP 444**. Virtual threads cho phép mô hình **một luồng xử lý cho mỗi tác vụ/request** tiếp tục dùng mã tuần tự dễ đọc, trong khi số luồng của hệ điều hành không phải tăng tỷ lệ 1:1 với số tác vụ đang chờ I/O.

Nhưng trong quá trình chẩn đoán runtime, ba cụm từ rất dễ bị hiểu nhầm:

- **Platform thread:** đối tượng `java.lang.Thread` được JVM gắn với một OS/kernel thread, thường theo tỷ lệ 1:1 trong suốt vòng đời của platform thread.
- **Virtual thread:** một đối tượng `java.lang.Thread` thực thi logic ứng dụng, được **JVM schedule** lên platform threads khi có thể chạy; không chiếm riêng một OS thread trong toàn bộ thời gian sống.
- **Carrier thread:** **một platform thread đang đóng vai trò phương tiện chạy một virtual thread** tại một thời điểm. Carrier **không phải loại Thread thứ ba** của Java SE 21.

Quan hệ giữa chúng giải thích vì sao một ứng dụng có thể tồn tại hàng chục nghìn virtual threads dù hệ điều hành chỉ thấy số platform/kernel threads ít hơn rất nhiều, vì sao `Thread.currentThread()` bên trong virtual thread vẫn trả **virtual Thread** chứ không phải carrier, và vì sao một số đoạn `synchronized`/native code trong **JDK 21** có thể **pin** carrier làm mất lợi thế mở rộng khi tác vụ bị chặn lâu.

Sau bài học, bạn sẽ:

1. Mô tả chính xác platform thread, virtual thread, carrier và OS thread, không trộn **logical task** với **physical execution resource**.
2. Hiểu các bước **mount → chạy → unmount/park → carrier được tái sử dụng → remount**, phân biệt lịch của JVM với lịch của hệ điều hành.
3. Sử dụng đúng `Thread.ofVirtual()`, `Thread.startVirtualThread()`, `Thread.ofPlatform()` và `Executors.newVirtualThreadPerTaskExecutor()` của **Java 21**.
4. Giải thích khả năng mở rộng với blocking I/O, giới hạn khi CPU-bound/pinning, và vì sao **virtual threads không làm một task chạy nhanh hơn**.
5. Viết và chạy chương trình Java 21 minh họa định danh logical virtual thread, một trăm tác vụ chờ và giới hạn của `ThreadMXBean`.
6. Chẩn đoán tình huống platform/carrier tăng, JFR báo pinning, thread dumps thiếu virtual threads hoặc application vẫn bị nghẽn ở DB pool.
7. Phân biệt những điều Java API **bảo đảm** với chi tiết scheduler/HotSpot **phụ thuộc triển khai**, không suy đoán carrier identity từ tên luồng.

> **Phạm vi:** Java **21**, không dùng cú pháp preview từ Java 19/20; các API ở đây cần JDK 21+ để biên dịch. Lưu ý quan trọng: đặc điểm **pinning do `synchronized`** trình bày dưới đây phản ánh **JDK 21**; các JDK mới hơn có thể thay đổi cơ chế runtime. Khi áp dụng vào production, luôn xác nhận **JDK/vendor/build thật sự đang chạy**.

## 1. Bức tranh tổng thể: chỉ có hai loại Java Thread

Theo Java SE 21, `java.lang.Thread` đại diện cho một luồng thực thi và có **hai loại chính**: **platform thread** và **virtual thread**. Cả hai đều là đối tượng `Thread`, đều có ID, tên, khả năng `join()`/`interrupt()`/`ThreadLocal` theo API tương ứng; chúng khác nhau chủ yếu ở cách được lập lịch và mối quan hệ với tài nguyên OS.

| Góc nhìn | Platform thread | Virtual thread |
| --- | --- | --- |
| Kiểu đối tượng Java | `java.lang.Thread` | `java.lang.Thread` |
| `isVirtual()` | `false` | `true` |
| Ai quyết định khi nào chạy? | OS scheduler quyết định chạy kernel/OS thread tương ứng | JVM virtual-thread scheduler quyết định khi nào **mount** lên carrier; OS vẫn schedule chính carrier |
| Quan hệ với OS thread | Thông thường 1:1 trong suốt vòng đời | Có thể chạy trên **những carrier khác nhau theo thời gian**, không giữ một OS thread riêng khi đang unmounted |
| Stack/resource | OS thread stack và tài nguyên kernel thường lớn hơn | Stack/continuation được JVM quản lý, có thể lưu dưới dạng các stack chunks trên heap khi unmount |
| Độ phù hợp | Công việc CPU-bound, tasks cố định, native/low-level cases, thread pools truyền thống | Nhiều tác vụ độc lập dành phần lớn thời gian chờ blocking I/O |
| Số lượng khả thi | Thường giới hạn bởi số OS threads, memory và resource limits | Có thể rất lớn, nhưng **không vô hạn**: heap, scheduler, application state và tài nguyên ngoài JVM vẫn có giới hạn |
| Daemon/priority | Có thể daemon hoặc non-daemon, priority theo API | Luôn **daemon** và có **fixed priority** theo contract Java 21 |
| `ThreadMXBean` của Java 21 | Giám sát platform threads | **Không giám sát virtual threads** qua API này |
| Cách tạo tiêu biểu | `new Thread(task)` hoặc `Thread.ofPlatform()` | `Thread.ofVirtual()`, `Thread.startVirtualThread()`, per-task executor |

**Carrier thread không nằm ở cột thứ ba**, bởi carrier chính là một **platform thread** mà scheduler đang dùng để thực thi virtual thread. Một platform thread có thể là carrier trong giai đoạn này và sau đó mang virtual thread khác. Không có API Java SE 21 công khai bảo đảm một virtual thread gắn mãi với một carrier cố định.

### 1.1 Cụm từ “virtual” không có nghĩa “không chạy trên OS thread”

CPU vẫn thực thi instructions trên những OS threads thực. Virtual thread là **đơn vị scheduling logic của Java**, không phải một CPU giả lập. Khi virtual thread thực sự chạy Java bytecode/native instructions, nó phải được **mount** lên một carrier platform thread, rồi carrier đó được OS scheduler chạy trên CPU core.

Do đó:

- **100.000 virtual threads** không đồng nghĩa **100.000 OS threads**.
- **1 virtual thread** không đồng nghĩa **1 carrier riêng**.
- **100.000 virtual threads** cũng không đồng nghĩa **100.000 tasks đang tính toán đồng thời trên CPU**.
- Khi virtual thread đang ở trạng thái blocked mà JVM có thể **unmount**, carrier được dùng cho công việc khác.
- Khi một virtual thread chạy CPU-bound liên tục, nó chiếm execution time của carrier tương tự một tác vụ CPU-bound khác; scheduler không tạo thêm năng lực CPU.
- Một platform thread có thể làm code ứng dụng truyền thống hoặc đóng vai trò carrier; “carrier” là **vai trò trong quan hệ scheduling**, không phải subtype `CarrierThread` công khai của `Thread`.

### 1.2 Ví dụ diễn giải 10.000 request

Giả sử một HTTP server nhận 10.000 requests đồng thời, mỗi request dành phần lớn thời gian **đợi database/network**, còn CPU xử lý thực tế khá ngắn.

**Mô hình platform thread-per-request truyền thống:**

```text
Request #1    -> platform thread #1  -> OS thread #1  -> có thể block khi đọc DB
Request #2    -> platform thread #2  -> OS thread #2  -> có thể block khi đọc DB
...
Request #N    -> platform thread #N  -> OS thread #N  -> tài nguyên kernel tăng theo N
```

**Mô hình virtual thread-per-request:**

```text
Request #1    -> virtual thread #1    \
Request #2    -> virtual thread #2     \
...                                   -> JVM scheduler -> các carrier platform threads
Request #N    -> virtual thread #N     /                   -> OS threads -> CPUs
```

Khi nhiều request đang đợi I/O và được unmount, nhiều virtual threads có thể tồn tại độc lập trong khi số carriers nhỏ hơn nhiều. **N không quyết định cứng số carriers**: lượng CPU, blocking/pinning, JDK scheduler policy, tài nguyên container và loại workload mới quyết định vận hành thực tế.

Ví dụ này là **mô hình khái niệm**, không phải cam kết rằng cứ 10.000 requests thì JDK dùng đúng 8 hoặc 16 carriers. Nếu DB connection pool chỉ có 50 connections, virtual threads không tự tạo 10.000 DB connections; những tác vụ khác vẫn phải chờ resource giới hạn của database/application.

## 2. Platform thread: mối nối với OS scheduler

### 2.1 Từ Java Thread đến kernel thread

Một platform thread là đối tượng `java.lang.Thread` mà triển khai JDK thường ánh xạ tới một OS/kernel thread. Trong mô hình HotSpot tiêu biểu:

```text
Java platform Thread object
    |
    | thường gắn 1:1 trong lifetime
    v
OS/kernel thread (có native TID, stack, scheduling state)
    |
    v
Operating-system scheduler -> CPU
```

Lợi ích: hành vi tích hợp với hệ điều hành dễ hiểu, phù hợp tasks CPU-bound và native libraries. Giới hạn: một OS thread sống lâu thường giữ kernel bookkeeping/native stack, tốn memory/address space/scheduling overhead; số OS threads không thể mở rộng tùy ý.

Khi code platform thread gọi một I/O blocking thực sự tại OS level, **OS thread đó có thể phải chờ**, không sẵn để chạy Java task khác như một carrier được trả lại khi virtual thread unmount.

### 2.2 Tạo platform thread trong Java 21

```java
// Đoạn minh họa đặt trong một method; cần có main hoặc gọi nơi khác.
Thread thread = Thread.ofPlatform()
        .name("legacy-worker")
        .start(() -> System.out.println(
                Thread.currentThread().isVirtual()));
thread.join();
```

Trong ví dụ đơn lẻ không có writer stdout khác, dòng in từ worker là `false`. `Thread.ofPlatform()` là builder Java 21; `new Thread(task)` vẫn tạo platform thread.

Một platform thread có thể được dùng trong `ThreadPoolExecutor`/`Executors.newFixedThreadPool()` và được **reuse** cho nhiều tasks. Đó là mô hình truyền thống tiết kiệm số threads so với tạo mỗi request một OS thread. Đừng đánh đồng **platform thread** với **platform thread pool**: một đối tượng platform thread có thể tồn tại độc lập hoặc là worker của một pool.

### 2.3 OS thread ID khác Java thread ID

`Thread.threadId()` trả **Java thread ID**, không phải PID của process và không đảm bảo bằng native thread ID/LWP/TID. Trong HotSpot thread dump, `nid=0x...` thường biểu diễn native thread ID theo hexadecimal đối với platform thread.

Với virtual thread, Java thread ID tiếp tục định danh virtual `Thread`, **không biến thành OS TID của carrier**. Khi virtual thread unmount/remount, không được xem ID đó như bằng chứng nó vẫn chạy trên cùng một OS thread.

## 3. Virtual thread: logical thread có danh tính ổn định

### 3.1 Virtual thread vẫn là Thread thật trong Java API

Virtual thread không phải `CompletableFuture`, không phải coroutine library tùy ý, cũng không phải một task chỉ có callback. Đây là **đối tượng Java `Thread`** có lifecycle, stack trace, interruption, exception handling và khả năng truyền dữ liệu thread-local theo API.

Các cách tạo trên Java 21:

```java
Thread t1 = Thread.startVirtualThread(() -> work());
Thread t2 = Thread.ofVirtual().name("request-42").start(() -> work());
Thread t3 = Thread.ofVirtual().unstarted(() -> work());
t3.start();
```

Đây là **đoạn minh họa không độc lập**: method `work()` là giả định. Cả ba thread đều là virtual; `t3` không bắt đầu cho tới `start()`. Các method `startVirtualThread`, `ofVirtual` và `isVirtual` là Java 21 APIs, **không biên dịch trên JDK 17**.

### 3.2 Thread.currentThread() trả virtual thread, không phải carrier

Khi code của một virtual thread đang chạy trên carrier, ví dụ:

```java
// Đoạn minh họa đặt bên trong Runnable của một virtual thread.
Thread current = Thread.currentThread();
System.out.println(current.isVirtual());
```

`Thread.currentThread()` trả **logical virtual Thread**. Dù CPU đang thực thi code thông qua một carrier platform thread, Java code không “nhìn thấy mình biến thành carrier”. Điều này bảo toàn:

- Thread identity và `threadId()` của virtual thread.
- `ThreadLocal` và `InheritableThreadLocal` của virtual thread theo lifecycle/context.
- Interruption state và API `join()`/`isAlive()` theo logical thread.
- Thông tin stack/exception của logical task.
- Tên virtual thread nếu đã được gán.

**Không có Java SE 21 public method `Thread.getCarrierThread()`** để ứng dụng tự suy hoặc khóa chặt carrier identity. Đừng đọc `Thread.currentThread().getName()` rồi gán tên đó cho OS worker; tên đó là của **virtual thread**.

### 3.3 Những thuộc tính đặc biệt của virtual threads

| Tính chất Java 21 | Ý nghĩa vận hành |
| --- | --- |
| `isVirtual() == true` | Đây là virtual Thread |
| `isDaemon() == true` | Virtual threads là daemon; không tự giữ JVM sống khi các non-daemon threads đã hoàn tất |
| Priority fixed | Không dùng `setPriority` để ưu tiên scheduling virtual tasks như một cơ chế điều khiển throughput |
| Default name rỗng | Virtual thread không tự có tên thân thiện; đặt tên ở builder nếu muốn phân tích logs |
| `threadId()` | ID riêng của logical virtual Thread, không phải OS native TID |
| `join()` | Có thể đợi một virtual thread kết thúc từ thread khác |
| `ThreadLocal` | Được hỗ trợ, nhưng tạo nhiều virtual threads có thể nhân rộng memory retention nếu dùng mỗi task một cache lớn |
| Exception/stack | Mỗi virtual thread có luồng lỗi logic và stack của nó, dù carrier thay đổi |

Do virtual threads là daemon, đoạn sau **không nên dùng** khi muốn bảo đảm mọi task hoàn thành:

```java
// Chỉ minh họa anti-pattern: main có thể kết thúc trước task.
Thread.startVirtualThread(() -> doLongTask());
```

Method `doLongTask` là giả định. Khi main/platform non-daemon thread cuối cùng kết thúc, JVM có thể shutdown dù virtual task chưa hoàn tất. Nên `join()`, chờ `Future.get()`, hoặc dùng `try-with-resources` với executor thích hợp để quản lý completion và failure.

### 3.4 Virtual thread không nhất thiết cần pool

Với platform threads, tạo/huỷ OS thread thường có chi phí lớn nên thread pools là thực hành phổ biến. Virtual threads **rẻ hơn nhiều** và được thiết kế cho mô hình **mỗi task một virtual thread**, không phải tái sử dụng cùng một virtual thread cho nhiều requests.

`Executors.newVirtualThreadPerTaskExecutor()` tạo **virtual thread mới cho mỗi task**. Nó không phải fixed-size pool gồm vài virtual threads chạy luân phiên nhiều tasks.

Dùng virtual thread **per-task** giúp giữ:

- Một task/request có call stack và context riêng.
- Dạng code tuần tự có `try/catch/finally` dễ đọc.
- Cancellation/interruption theo đơn vị task.
- Không cần biến mã nghiệp vụ thành callback chain chỉ để tránh chặn OS thread.

Nhưng resource khác như connections, rate-limited APIs, file descriptors, queue capacity vẫn cần giới hạn rõ ràng.

## 4. Carrier: vai trò của một platform thread trong lúc virtual thread được mount

### 4.1 Mount là gì?

Khi JVM scheduler chọn một virtual thread đang runnable, nó **mount** virtual thread lên một **carrier platform thread** để thực thi code. OS scheduler sau đó quyết định khi nào carrier được chạy trên CPU core.

```text
Virtual task A (logical Thread A)
   |
   | JVM: mount
   v
Carrier P1 = một platform Thread
   |
   v
OS thread TID=... -> được OS scheduler chạy trên core
```

Điểm cốt lõi: nếu trong lúc A đang mount, code gọi `Thread.currentThread()`, nó vẫn nhận đối tượng **virtual A**, không nhận đối tượng carrier P1. Carrier là nền tảng vật lý mà scheduler sử dụng, không phải một đối tượng mới của ứng dụng.

### 4.2 Unmount và remount

Khi A gọi một thao tác blocking được JVM hỗ trợ để **park/unmount** (ví dụ một số socket I/O hoặc các điểm chờ trong thư viện chuẩn), VM có thể lưu stack/continuation của A, **unmount** A khỏi carrier P1, rồi đưa carrier P1 về để chạy một virtual thread khác.

Khi I/O hoàn tất hoặc task được unpark, scheduler sẽ đưa A trở lại hàng đợi runnable. A có thể được **remount** lên P1 hoặc lên **carrier P2 khác**. **Không có bảo đảm rằng lần remount sẽ dùng cùng OS thread**.

```text
Thời điểm      Logical virtual A                 Carrier platform threads
----------     ---------------------------------  --------------------------
T0             A runnable                        P1 rảnh, P2 rảnh
T1             A mount và chạy                    P1 chạy A
T2             A gọi I/O và cần chờ               JVM unmount A khỏi P1
T3             A vẫn chờ I/O                      P1 chạy B; P2 chạy C
T4             I/O của A hoàn tất                 A trở lại runnable
T5             A remount và tiếp tục              P2 có thể chạy A

A vẫn là **một** virtual Thread trong mọi thời điểm T0..T5.
```

Đây là **timeline khái niệm**, không phải cam kết cứ gọi một API cụ thể là có đúng sáu bước hay remount trên P2. Scheduler/OS rất động; các đoạn code có thể không yield vì I/O hoàn thành ngay, hoặc vì native/pinning khiến không unmount được.

### 4.3 Không phải lúc nào chặn cũng unmount

Điểm dễ hiểu sai là “virtual thread không bao giờ giữ carrier khi blocking”. Trong **JDK 21**, điều đó **không đúng**. Một số blocking operations được JDK tích hợp để unmount; những tình huống pinning hay native/foreign code có thể chặn **cả carrier**.

Do đó cần phân biệt:

- **Virtual thread đang chờ và đã unmount:** không chiếm carrier trong thời gian chờ.
- **Virtual thread đang chạy trên carrier:** chiếm execution slot để thực hiện work.
- **Virtual thread bị pin và chặn:** carrier không được giải phóng; chi phí có thể tương tự OS thread bị block.
- **Virtual thread chờ connection pool:** có thể unmount nhưng request vẫn chưa có connection, nên throughput có thể không cải thiện.
- **Carrier bị OS scheduler preempt:** virtual thread có thể vẫn mounted nhưng không thực thi tại thời điểm OS dành CPU cho thread khác.

Một virtual thread không tự **song song hóa** code bên trong: mỗi virtual thread thực thi một luồng tuần tự; nếu muốn tận dụng nhiều CPU cores, cần nhiều runnable tasks và thuật toán phù hợp.

## 5. Ai lập lịch phần nào?

### 5.1 Hai tầng scheduling

```text
Các virtual Threads A,B,C,D,...
               |
               | JVM virtual-thread scheduler:
               | chọn runnable task để mount
               v
      Carrier platform Threads P1,P2,...
               |
               | OS scheduler:
               | gán OS threads lên CPU cores
               v
           CPU execution
```

- **JVM** quyết định virtual thread nào được mount/remount và khi nào park/unpark.
- **OS** quyết định platform/kernel thread nào (bao gồm carriers) có CPU time.
- Có thể có **nhiều virtual threads hơn số carriers** nhờ chờ I/O không chiếm carrier.
- Số tasks **đang thực thi CPU đồng thời** vẫn bị giới hạn bởi cores/quota, carrier availability và work scheduling.
- Carrier không phải ownership bền vững của request; một request không được phép gắn business state vào carrier identity.

### 5.2 Scheduler của triển khai JDK 21

Trong **OpenJDK/HotSpot Java 21**, bộ lập lịch virtual threads mặc định dựa trên **`ForkJoinPool`** riêng, sử dụng các carrier platform threads. Đây là **chi tiết của JDK implementation**, không phải lời hứa mọi JVM/vendor đều có cùng worker naming, queue policy và số carriers.

Java 21 `Thread` API liệt kê hai system properties của reference implementation:

| Property | Ý nghĩa | Mặc định tham khảo từ JDK 21 API |
| --- | --- | --- |
| `jdk.virtualThreadScheduler.parallelism` | Số platform threads có sẵn để lập lịch virtual threads theo target parallelism | **Số available processors** |
| `jdk.virtualThreadScheduler.maxPoolSize` | Trần số platform threads mà scheduler có thể sử dụng theo cơ chế quản lý pool | **256** |

Ví dụ chạy lab và đặt **parallelism** bằng 2:

```bash
java -Djdk.virtualThreadScheduler.parallelism=2 VirtualCarrierRelationLab
```

Không suy ra “scheduler chỉ có đúng hai Java platform threads ở mọi snapshot”. JVM còn GC/JIT/management threads; chính scheduler cũng có thể có logic compensation/worker count khác target parallelism trong một số tình huống. Trần max pool là một giới hạn của scheduler, **không phải hạn mức số virtual threads**.

Đặc biệt trong JDK 21, scheduler **không tự mở rộng parallelism để bù cho pinning** theo cách có thể giả định “cứ pin thì spawn carrier mới”. Thay vì chỉ tăng parallelism, cần phát hiện các đoạn code pin lâu và thường xuyên.

**Không chỉnh hai properties chỉ vì thấy nhiều virtual threads chờ.** Đo CPU quota, JFR pinning, response times, workload mix, pool/connection limits và benchmark trên cùng JDK build trước khi thay scheduler tuning.

### 5.3 Carrier có thể khác nhau ngay trong cùng một call stack logic

Giả sử `processRequest()` gọi `loadFromDatabase()`. Sau khi virtual thread unmount ở network I/O rồi remount, Java source nhìn thấy như một lời gọi tuần tự bình thường:

```java
// Đoạn minh họa, các method thuộc ứng dụng và không độc lập.
Order order = repository.findById(id); // Có thể chờ I/O.
validate(order);
sendResponse(order);
```

Giữa `findById` và `validate`, logical virtual thread vẫn giữ exception context, stack và `ThreadLocal` theo API, dù carrier có thể đổi. Ứng dụng **không cần** nhận biết carrier hoặc khôi phục thủ công call stack sau một callback; đó là giá trị lớn của virtual threads.

## 6. Lab Java 21 chạy độc lập: định danh thread và số task chờ

Ví dụ này chỉ dùng **Java 21 standard library**, không cần Internet, database, framework. Nó có hai phần:

1. Một virtual thread có tên rõ, dùng latch để giữ **còn sống** trong lúc main đọc identity và `ThreadMXBean`.
2. Một executor tạo **100 virtual threads** chờ latch; main đợi chúng **đã tới điểm chờ** rồi mới in số tasks. Đây là thí nghiệm về **logical concurrency**, không phải phép đo chính xác số carrier của VM.

Tạo file **`VirtualCarrierRelationLab.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public final class VirtualCarrierRelationLab {
    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicReference<Thread> seenInside = new AtomicReference<>();

        Thread virtual = Thread.ofVirtual()
                .name("demo-virtual")
                .start(() -> {
                    seenInside.set(Thread.currentThread());
                    entered.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });

        entered.await();
        Thread captured = seenInside.get();

        System.out.println("main.isVirtual=" +
                Thread.currentThread().isVirtual());
        System.out.println("worker.isVirtual=" + captured.isVirtual());
        System.out.println("worker.sameObject=" + (captured == virtual));
        System.out.println("worker.name=" + captured.getName());
        System.out.println("worker.isDaemon=" + captured.isDaemon());
        System.out.println("mxbean.seesWorker=" +
                (ManagementFactory.getThreadMXBean()
                        .getThreadInfo(virtual.threadId()) != null));

        release.countDown();
        virtual.join();

        final int totalTasks = 100;
        CountDownLatch reachedWaitPoint = new CountDownLatch(totalTasks);
        CountDownLatch allowToFinish = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < totalTasks; i++) {
                results.add(executor.submit(() -> {
                    reachedWaitPoint.countDown();
                    allowToFinish.await();
                    return Thread.currentThread().isVirtual();
                }));
            }

            reachedWaitPoint.await();
            System.out.println("tasks.reachedWaitPoint=" + totalTasks);
            System.out.println("platformThreads.observed=" +
                    ManagementFactory.getThreadMXBean().getThreadCount());

            allowToFinish.countDown();
            boolean everyTaskVirtual = true;
            for (Future<Boolean> result : results) {
                everyTaskVirtual &= result.get();
            }
            System.out.println("tasks.allVirtual=" + everyTaskVirtual);
        }
    }
}
```

Biên dịch và chạy **JDK 21**:

```bash
javac VirtualCarrierRelationLab.java
java VirtualCarrierRelationLab
```

**Sáu dòng stdout đầu tiên chính xác trên một JVM Java 21 chạy bằng launcher tiêu chuẩn:**

```text
main.isVirtual=false
worker.isVirtual=true
worker.sameObject=true
worker.name=demo-virtual
worker.isDaemon=true
mxbean.seesWorker=false
```

Những dòng sau có dạng:

```text
tasks.reachedWaitPoint=100
platformThreads.observed=<so-platform-threads-thuc-te>
tasks.allVirtual=true
```

Trong đó `platformThreads.observed` là **giá trị thực tế phụ thuộc JVM, máy, GC, scheduler và thời điểm đo**; placeholder trong khối minh họa **không phải stdout thực**. Hai dòng `tasks.reachedWaitPoint=100` và `tasks.allVirtual=true` là kỳ vọng xác định nếu chương trình chạy bình thường và không có interruption/error từ môi trường.

### 6.1 Những điều lab chứng minh

- `Thread.ofVirtual().name("demo-virtual").start(...)` tạo đối tượng virtual `Thread` cụ thể.
- Bên trong task, `Thread.currentThread()` chính là **đối tượng `virtual`** đã trả cho main; do đó `worker.sameObject=true`.
- Virtual thread **vẫn đang sống** khi main kiểm tra `getThreadInfo` vì nó đang chờ `release`; `mxbean.seesWorker=false` là giới hạn **platform-only** của `ThreadMXBean` trong Java 21, không phải do thread đã kết thúc.
- Tên virtual thread do ứng dụng đặt tồn tại độc lập với tên carrier.
- Virtual thread là daemon. Main đợi `join()` và `Future.get()` để chương trình không thoát sớm.
- `newVirtualThreadPerTaskExecutor` tạo virtual thread **mới cho mỗi task**, không pool các virtual `Thread` rồi tái sử dụng nhiều task khác nhau.
- Khi 100 task đã tới điểm chờ, ta có 100 logical tasks đang phối hợp chờ latch; số `getThreadCount()` là **platform threads** và không phải 100 virtual tasks cộng lại.

### 6.2 Điều lab **không** chứng minh

Không được suy từ giá trị `platformThreads.observed` rằng “chính xác X carriers đã chạy 100 tasks”. `ThreadMXBean.getThreadCount()` bao gồm **nhiều platform threads khác**, như main, JIT/management/helper threads mà bean báo cáo, và **không tách riêng carrier pool**. Để đo carrier/scheduler cần telemetry/JFR/OS observations phù hợp với VM implementation.

Ngoài ra, `reachedWaitPoint.countDown()` xảy ra **ngay trước** `allowToFinish.await()`; thời điểm main in ra 100 cho thấy tất cả tasks **đã tới điểm trước khi chờ**, không đảm bảo snapshot nguyên tử rằng đúng 100 tasks đều đang parked trong cùng nanosecond. Đó là khác biệt giữa **đồng bộ thí nghiệm** và **quan sát runtime thực**.

### 6.3 Vì sao không dùng Thread.sleep để in “carrier ID”?

Trong Java SE 21, `Thread.currentThread()` khi được gọi bên trong virtual thread luôn trả virtual `Thread`. Không có public API bảo đảm `currentThread().threadId()` là ID carrier. Nếu in ID trước và sau `sleep()`, nó **vẫn là ID của virtual thread**, kể cả nếu remount trên carrier khác.

Tương tự, dựa vào tên `ForkJoinPool-...-worker-...` thấy trong một thread dump không chứng minh một request giữ nguyên carrier đó suốt vòng đời. Carrier có thể thay đổi, và thread dump chỉ chụp một thời điểm.

### 6.4 Vì sao code cần JDK 21?

Những API này **không có trong Java 17**:

- `Thread.ofVirtual()` và `Thread.startVirtualThread()`.
- `Thread.isVirtual()` và `Thread.threadId()` (bản APIs như dùng trong lab).
- `Executors.newVirtualThreadPerTaskExecutor()`.

Virtual threads đã từng là preview ở JDK 19/20 nhưng được **finalize** ở Java 21. Để học đúng JDK 21, biên dịch với `javac` JDK 21 và chạy bằng `java` của JDK 21; tránh tình huống `javac` từ JDK 21 nhưng `java` trong `PATH` lại từ JDK 17 khiến code chạy thất bại.

Có thể xác minh:

```bash
java -version
javac -version
```

Hai lệnh này cho biết **runtime/compiler của terminal hiện tại**, không tự chứng minh Java service production đang dùng cùng bản. Khi chẩn đoán một service thật, xác minh version của **JVM process đích**.

## 7. Mount/unmount và blocking I/O: lý do virtual threads có thể mở rộng

### 7.1 Điều gì diễn ra với thao tác có thể park?

Mô hình đơn giản:

```text
Virtual A đang chạy             JVM nhận I/O cần chờ
   |                                    |
   v                                    v
carrier P1 chạy A ---> A bị park/unmount; state được giữ
                          |
                          +-- P1 chạy virtual B
                          |
                      I/O completion / unpark
                          |
                          v
                    A runnable lần nữa
                          |
                          v
                    A remount trên carrier sẵn có
```

Khi virtual thread đang unmounted, nó không “mất” Java call stack. Runtime bảo toàn trạng thái logic để code tiếp tục tại điểm sau operation. Phần stack có thể được quản lý trong heap dưới dạng **stack chunks/continuations** khi unmount, thay vì mỗi virtual thread giữ một native OS stack độc lập suốt thời gian sống.

Đây là lý do nhiều tác vụ block I/O có thể đồng tồn tại với ít carriers hơn số virtual threads.

### 7.2 Các blocking APIs có được hỗ trợ hoàn toàn không?

Không được hứa “mọi I/O sẽ nhả carrier”. JDK 21 tích hợp nhiều blocking operations của thư viện chuẩn với virtual-thread scheduler, nhưng:

- Blocking operation hoàn thành ngay có thể không cần unmount.
- Một native call, FFM foreign function hoặc library chưa tích hợp tốt có thể **pin** carrier hoặc thực hiện OS blocking thật.
- Một lệnh `synchronized` ở stack có thể ngăn unmount lúc block (JDK 21).
- Các JDBC drivers/network libraries có thể có cách đồng bộ riêng; kiểm tra thực tế.
- Các thao tác CPU-bound vẫn phải dùng carrier để thực thi, không tự tăng CPU capacity.

**`Thread.sleep(...)` và nhiều kiểu blocking wait** thường có thể park/unmount trên Java 21 nếu không bị pin, nhưng không sử dụng chúng để suy đoán carrier identity hoặc định lượng exact context-switch count.

### 7.3 CPU-bound vẫn chịu giới hạn vật lý

Giả sử server có 8 CPU cores/quota tương đương 8 cores:

- Tạo 100.000 virtual threads đang **chờ network** có thể hợp lý nếu heap, connection pools và backend chịu được.
- Tạo 100.000 virtual threads cùng chạy **mã tính toán nặng** không tạo 100.000 CPU cores.
- Nếu các tasks CPU-bound liên tục tranh CPU, scheduler vẫn phải chia thời gian trên số carriers và cores hữu hạn, có thể tăng latency.
- Với CPU-heavy workloads, giới hạn parallelism/task count và dùng work queues/profiler phù hợp vẫn quan trọng.

Oracle nhấn mạnh: **virtual threads cung cấp scale/throughput**, không bảo đảm một task đơn lẻ nhanh hơn (latency). Nếu backend vẫn có capacity giới hạn, throughput end-to-end tiếp tục bị chặn bởi backend.

## 8. Pinning trong JDK 21: khi virtual thread không nhả carrier được

### 8.1 Pinning là gì?

**Pinning** là khi virtual thread đang thực thi hoặc chặn ở một trạng thái khiến JVM không thể **unmount** nó khỏi carrier trong một số blocking operations. Khi đó carrier (và OS thread tương ứng) có thể bị giữ trong thời gian chờ.

Theo tài liệu **Oracle JDK 21**, hai tình huống chính:

1. Virtual thread đang chạy code bên trong **`synchronized` block/method**, rồi gặp một blocking operation cần yield.
2. Virtual thread đang chạy **native method** hoặc **foreign function** (trong phạm vi APIs tương ứng) và không thể unmount.

**Pinning không tự là bug correctness.** Một synchronized block rất ngắn chỉ chỉnh sửa biến in-memory có thể hoàn toàn bình thường. Vấn đề về **scalability** xuất hiện khi nhiều virtual threads **thường xuyên bị chặn lâu trong lúc pin**, khiến số carriers có thể dùng để xử lý runnable tasks giảm.

### 8.2 Anti-pattern JDK 21: I/O dài trong synchronized

```java
// Minh họa bên trong một class; remoteFetch() giả định có blocking I/O.
private final Object guard = new Object();

void load() throws Exception {
    synchronized (guard) {
        remoteFetch();
    }
}
```

Đoạn code không độc lập; `remoteFetch()` là giả định. Nếu `load()` chạy trên virtual thread và `remoteFetch()` bị block lâu, trong **JDK 21** việc đang giữ monitor có thể **pin virtual thread** và giữ carrier. Nếu hàng trăm requests đi qua cùng pattern, có thể làm giảm throughput.

**Không cần thay mọi synchronized bằng ReentrantLock.** Chỉ ưu tiên sửa những đường hot path **thường xuyên** gọi blocking operations khi giữ monitor. Với synchronized thuần CPU/critical section ngắn, đổi khóa có thể chỉ tăng complexity mà không cải thiện hệ thống.

### 8.3 Cách thiết kế thay thế khi cần

Nếu lock là bắt buộc để bảo vệ state nhưng I/O không nhất thiết phải ở trong critical section:

```java
// Mã minh họa; không độc lập vì remoteFetch/applyResult do ứng dụng định nghĩa.
Data snapshot;
synchronized (guard) {
    snapshot = readSnapshot();
}

Result result = remoteFetch(snapshot);

synchronized (guard) {
    applyResult(result);
}
```

Cần **thiết kế tính nhất quán**: nếu state có thể đổi giữa hai critical sections, phải dùng version checking, validation hoặc transaction semantics phù hợp. Đừng kéo I/O ra ngoài lock một cách máy móc nếu điều đó phá atomicity/correctness.

Nếu bắt buộc phải giữ **exclusive lock xuyên blocking operation**, Java 21 docs gợi ý xem `ReentrantLock` ở hot paths:

```java
// Minh họa bên trong class, không độc lập.
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

void loadWithExplicitLock() throws Exception {
    lock.lock();
    try {
        remoteFetch();
    } finally {
        lock.unlock();
    }
}
```

`ReentrantLock` dùng explicit unlock và có ngữ nghĩa riêng; có thể giúp tránh vấn đề pinning do intrinsic monitor trong JDK 21, **không tự loại bỏ lock contention hoặc nhu cầu bảo vệ state**. Nếu nhiều requests vẫn phải chờ cùng lock, throughput có thể vẫn bị serialize.

### 8.4 Pinning có được “scheduler tự bù carriers” không?

Không nên giả định như vậy. Đối với **pinning** trong OpenJDK/JDK 21, scheduler **không tăng parallelism chỉ để bù** các carriers bị giữ bởi pinned blocking operations. Nhiều pinned virtual threads có thể khiến application không đủ carriers để chạy tasks khác dù nhiều logical virtual threads vẫn runnable.

Không tìm giải pháp đầu tiên bằng cách tăng bừa `jdk.virtualThreadScheduler.parallelism` hoặc `maxPoolSize`: bạn có thể chỉ che triệu chứng, tăng OS thread pressure và vẫn giữ block dài trong critical section. Trước tiên xác định **nguồn pinning** và contention.

### 8.5 Đây là vấn đề phiên bản Java 21

Phần này mô tả **JDK 21**. Các phiên bản Java mới hơn có thể thay đổi cơ chế pinning quanh monitors. Không đưa nhận định “synchronized luôn pin virtual thread” làm chân lý vĩnh viễn của tất cả Java releases. Khi nâng JDK, xác nhận lại documentation/JFR behavior trên **bản đang chạy**, không chỉ áp dụng mẹo dành riêng Java 21.

## 9. Chẩn đoán pinning và carrier với JFR, jcmd và logging

### 9.1 JFR VirtualThreadPinned

**JDK Flight Recorder (JFR)** có event:

- `jdk.VirtualThreadPinned`: virtual thread bị pin đủ lâu vượt ngưỡng cấu hình khi blocking. Oracle JDK 21 ghi event này thường được bật mặc định với **threshold 20 ms** trong cấu hình liên quan.
- `jdk.VirtualThreadStart` / `jdk.VirtualThreadEnd`: lifecycle events, thường **disabled by default**, cần bật khi thật sự cần.
- `jdk.VirtualThreadSubmitFailed`: scheduler không thể submit/start/unpark virtual thread vì vấn đề tài nguyên hoặc trạng thái khác cần điều tra; thường enabled theo JDK 21 defaults.

Một lệnh xem JFR recording đã có:

```bash
# Tham khảo: file recording.jfr thực sự có sẵn ở máy gọi jfr.
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
```

Lệnh này **đọc file JFR có sẵn**, không tự bắt đầu một recording hay lấy dữ liệu từ JVM khác. Kết quả phụ thuộc thời điểm recording, threshold, event configuration và việc JVM thực sự xảy ra pinning. Không thấy event có thể do chưa bật, chưa chạm threshold hoặc không có hiện tượng trong cửa sổ; không tự chứng minh **“không hề có pinning”**.

### 9.2 jdk.tracePinnedThreads trên JDK 21

Để điều tra hot paths trong **JDK 21**, Oracle docs mô tả system property:

```bash
java -Djdk.tracePinnedThreads=full YourApp
java -Djdk.tracePinnedThreads=short YourApp
```

`full` có thể in stack trace liên quan khi virtual thread block trong trạng thái pinned, tô đậm/đánh dấu native frames hoặc frames đang giữ monitors; `short` hạn chế thông tin hơn. Đây là **cú pháp startup minh họa**, thay `YourApp` bằng main class/launcher thật. Output có thể rất nhiều và chứa tên internal methods/paths; phải đánh giá overhead và log sensitivity.

Không giả định tùy chọn này được hỗ trợ y hệt ở **JDK mới hơn**, hay có thể gắn động vào mọi JVM. Dùng đúng tài liệu version và ưu tiên JFR có overhead/retention phù hợp nếu production policy cho phép.

### 9.3 Thread.dump_to_file và traditional thread dumps

Tài liệu Oracle JDK 21 có cơ chế tạo **virtual-thread-aware thread dump**:

```bash
# Trước hết kiểm tra danh sách command do JVM đích hỗ trợ.
jcmd 12345 help Thread.dump_to_file

# Nếu supported, JVM đích ghi file JSON ở đường dẫn của nó:
jcmd 12345 Thread.dump_to_file -format=json /approved/threads-12345.json
```

**12345 là PID giả định**, đường dẫn cũng là ví dụ. Một số JDK builds có khác biệt command availability; `jcmd PID help` của **JVM đích** là nguồn quyết định. File được ghi ở **filesystem của JVM**, đặc biệt lưu ý container mount namespace/permissions; không tự xuất hiện trên laptop vì lệnh được gọi từ shell bên ngoài.

Các lệnh truyền thống:

```bash
jcmd 12345 Thread.print -l
jstack -l 12345
```

thường tập trung vào **platform threads** và lock info, không đảm bảo chứa đầy đủ mọi **unmounted virtual thread** của Java 21. Vì vậy đừng kết luận “chỉ có 40 threads” chỉ từ một traditional thread dump khi app có hàng nghìn virtual tasks.

### 9.4 ThreadMXBean không giám sát virtual threads trong Java 21

Trong Java SE 21, `ManagementFactory.getThreadMXBean()` phục vụ **platform threads**:

- `getThreadCount()` là số live platform threads theo bean, **không phải** tất cả virtual threads.
- `getAllThreadIds()` không liệt kê virtual thread IDs.
- `getThreadInfo(virtualThread.threadId())` trả **`null`**, kể cả khi virtual thread còn sống.
- `dumpAllThreads(...)` không phải bản dump đầy đủ tất cả virtual threads.
- `findMonitorDeadlockedThreads()` và `findDeadlockedThreads()` không tìm chu trình deadlock **có virtual thread tham gia** theo contract Java 21.

Do vậy không dùng `ThreadMXBean`/JConsole Threads tab để suy ra số lượng virtual tasks, mức độ nghẽn virtual hoặc bảo đảm không có virtual-thread deadlock. Sử dụng JFR, jcmd dump phù hợp, application-level metrics và trace context.

### 9.5 CPU của carrier không tự là CPU của một virtual task

OS tools như `top -H`, `ps -L` hoặc hệ monitor process thường quan sát **OS/kernel threads**, tức carriers và nhiều platform threads khác. Một carrier có thể lần lượt chạy virtual A, B, C... trong cùng cửa sổ sampling.

Vì vậy:

- “Carrier P1 đã dùng 80% CPU” **không** có nghĩa một virtual thread A dùng 80% CPU suốt khoảng đó.
- Virtual thread A có thể đã chuyển carrier khi remount.
- Để tìm hot methods/logical work, dùng **JFR CPU samples** và correlation/trace IDs phù hợp.
- Đừng đồng nhất HotSpot `nid=0x...` của carrier với `Thread.threadId()` của một virtual task.
- Nếu có native blocking/pinning, JFR/stack có thể giúp định vị đúng code path; một OS CPU sample riêng lẻ không kết luận được pinning.

## 10. Threads, tasks, carriers, connections: bốn loại tài nguyên khác nhau

Trong nhiều ứng dụng web, câu hỏi “virtual threads có giải quyết hết vấn đề thread pool?” cần trả lời bằng việc phân biệt bốn đại lượng:

1. **Logical tasks / virtual threads:** số đơn vị công việc đồng thời, thường mỗi request một virtual thread.
2. **Carrier/platform threads:** số OS execution slots mà JVM dùng để chạy những virtual threads **runnable hoặc pinned** tại các thời điểm.
3. **CPU cores/quota:** năng lực tính toán vật lý/scheduler mà OS cung cấp.
4. **External capacity:** DB pool, HTTP connection pool, rate limit, file descriptors, memory, downstream throughput, queue sizes và network latency.

### 10.1 Một ví dụ throughput định lượng

Giả sử:

- Server tiếp nhận trung bình 500 requests/giây.
- Mỗi request mất trung bình 0,2 giây, phần lớn là chờ backend.
- Theo ước lượng steady-state **Little's law**, concurrency trung bình khoảng:

```text
concurrency ~= throughput × responseTime
            ~= 500 requests/s × 0,2 s
            ~= 100 requests
```

Nếu downstream chậm và response time tăng lên 5 giây cùng throughput, concurrency có thể lên khoảng **2.500 requests**. Virtual threads giúp không nhất thiết cần 2.500 OS threads để giữ các requests đang chờ, **nhưng không làm backend phục vụ 2.500 queries đồng thời nếu DB pool bị giới hạn 50 connections**.

Để quản lý resource limits, dùng **semaphore/rate limit/connection pool** phù hợp. Nhưng đừng dùng fixed-size **virtual thread pool** như cách giả lập giới hạn resource; hãy giới hạn **resource thực** và để mỗi task giữ logical thread riêng theo thiết kế.

### 10.2 Virtual thread không giảm latency I/O chậm

Nếu một SQL query mất 300 ms ở DB, virtual threads không làm query tự hoàn thành trong 3 ms. Lợi ích là khi request đang chờ 300 ms, carrier có thể phục vụ request khác. Tổng throughput có thể tăng nếu trước đây bị kẹt bởi số platform threads, nhưng nếu DB đã quá tải thì tạo thêm concurrency có thể **làm latency tệ hơn**.

Mục tiêu thiết kế:

- Thích hợp với **I/O-heavy concurrent workloads**.
- Không hứa tăng tốc mỗi tác vụ CPU-heavy.
- Đặt timeouts/cancellation/limits đúng chỗ.
- Theo dõi CPU, heap, carrier pinning và downstream capacity.
- Benchmark cùng workload và percentile latency, không chỉ so số threads.

### 10.3 ThreadLocal trong hệ thống nhiều virtual tasks

Virtual threads hỗ trợ `ThreadLocal`; giá trị gắn với **virtual thread**, không gắn với carrier. Dùng để giữ correlation context nhẹ có thể phù hợp, nhưng một pattern cũ như “mỗi thread có một DB connection, parser buffer lớn hoặc cache đắt” dễ tạo memory amplification khi mỗi request tạo virtual thread mới.

Ví dụ:

```java
// Minh họa một anti-pattern tiềm ẩn ở ứng dụng có nhiều virtual threads.
private static final ThreadLocal<byte[]> BIG_BUFFER =
        ThreadLocal.withInitial(() -> new byte[1024 * 1024]);
```

Nếu có 5.000 virtual threads mỗi thread thật sự khởi tạo `BIG_BUFFER` 1 MiB, mức lý thuyết cho buffer là khoảng **5.000 MiB** (chưa kể overhead). Đây là tính toán giả định, **không phải số memory mà mọi ứng dụng tự dùng**. Giải pháp có thể là giảm buffer, giới hạn concurrency, quản lý resource sharing an toàn hoặc chọn context propagation thích hợp; không áp dụng một giải pháp chung trước khi đo.

Và vì virtual threads không reuse, một `ThreadLocal` cache “được tạo một lần cho thread pool worker” có thể trở thành **cache theo request** khi di chuyển sang virtual per-task model. Đây là thay đổi vòng đời cần review khi migration.

## 11. Những lỗi thiết kế khi nhầm carrier với virtual thread

| Nhầm lẫn | Điều đúng trên Java 21 |
| --- | --- |
| “Virtual thread không có Thread object.” | Virtual thread chính là một đối tượng `java.lang.Thread`. |
| “Carrier là loại Java Thread thứ ba.” | Carrier là **platform thread đang mang virtual thread**; Java SE có hai loại Thread. |
| “Virtual thread chạy mà không cần OS thread.” | Khi code thực sự chạy, nó được mount lên carrier OS-backed. |
| “Một virtual thread gắn cố định với một carrier.” | Có thể remount trên carrier khác sau khi unmount. |
| “`Thread.currentThread()` trả carrier trong mã virtual.” | Trả **virtual Thread**, không phải carrier. |
| “`threadId()` của virtual = native TID.” | Đó là Java logical thread ID, không phải OS native TID. |
| “Bất cứ blocking call nào cũng nhả carrier.” | Pinning/native/unsupported blocking có thể giữ carrier trong JDK 21. |
| “`synchronized` luôn sai với virtual threads.” | Nguy cơ là **blocking thường xuyên và dài khi pinned**; critical section ngắn có thể bình thường. |
| “Dùng ReentrantLock xong là không thể bị kẹt.” | Lock contention/deadlock vẫn có thể tồn tại; chỉ thay cơ chế pinning theo tình huống. |
| “Scheduler tạo vô hạn carriers khi pinning.” | JDK 21 không bù pinning theo cách đó; có limits và tác động OS. |
| “Mỗi virtual thread tốn native stack cố định như platform.” | Stack/continuation được JVM quản lý linh hoạt; vẫn tiêu thụ heap/resources. |
| “100.000 virtual threads = 100.000 request xử lý CPU song song.” | CPU runnable work bị giới hạn bởi carriers/cores/quota. |
| “Virtual threads tự làm DB connection pool không còn cần thiết.” | DB connections, QPS, file descriptors và downstream limits vẫn tồn tại. |
| “Virtual thread nên reuse bằng fixed thread pool.” | Thiết kế khuyến nghị là **virtual thread per task**; giới hạn resource thực, không pool virtual threads. |
| “Virtual threads không có ThreadLocal.” | Có, nhưng per-task multiplicity khiến caches lớn nguy hiểm. |
| “Virtual threads là non-daemon nên tự giữ JVM sống.” | Virtual threads là **daemon**; phải join/wait cho completion. |
| “ThreadMXBean.getThreadCount chứa hết virtual threads.” | Java 21 `ThreadMXBean` chỉ giám sát platform threads. |
| “Traditional thread dump luôn có đủ unmounted virtual threads.” | Cần virtual-thread-aware dump/JFR, không suy từ platform-only output. |
| “CPU của carrier xác định CPU của virtual request X.” | Carrier có thể phục vụ nhiều virtual threads qua thời gian. |
| “Virtual threads giảm latency của một RPC 300 ms.” | Chúng giúp capacity/throughput trong workload chờ I/O, không tự giảm thời gian RPC. |

## 12. Quy trình chẩn đoán thực tế

### Bước 1 — Xác nhận đúng JVM và JDK 21

Ghi service, environment, process PID/start time, container/node, JDK vendor/version/build và Java flags. Không lấy version của `java -version` chạy trong terminal khác thay cho version process production. Nếu nghi behavior pinning thay đổi, xác minh **exact JDK update release**.

### Bước 2 — Xác định câu hỏi

Ví dụ:

- “Vì sao số requests chờ tăng nhưng OS thread count không tăng?”
- “Vì sao sau migration sang virtual threads, CPU vẫn cao?”
- “Vì sao p99 latency xấu đi khi DB chậm?”
- “Có pinned carriers trong hot path không?”
- “Vì sao ThreadMXBean chỉ thấy 60 threads khi app tạo hàng nghìn tasks?”
- “Có virtual-thread deadlock hoặc starvation mà platform-only detector bỏ sót không?”

Không kết luận carrier saturation chỉ từ số virtual tasks. Tách CPU-bound, I/O-bound, resource starvation và pinning.

### Bước 3 — Thu số liệu theo đúng scope

| Cần biết | Nguồn phù hợp | Giới hạn |
| --- | --- | --- |
| JVM/platform thread count | `ThreadMXBean`, OS metrics, `jcmd Thread.print` | Không bao phủ đầy đủ virtual tasks trên Java 21 |
| Virtual task lifecycle/pinning | JFR events `jdk.VirtualThread*` theo config | Recording/event thresholds có thể bỏ hiện tượng ngắn |
| Virtual thread stacks hiện tại | `jcmd PID help Thread.dump_to_file`, tool phù hợp | Tool availability và dung lượng output phụ thuộc JDK/build |
| CPU hotspot | JFR CPU samples, profiler và OS CPU | Cần thời gian sampling/correlation |
| External bottleneck | DB/HTTP pool metrics, network/traces, rate limits | Ngoài phạm vi ThreadMXBean |
| Pinning code path | `jdk.VirtualThreadPinned` hoặc `jdk.tracePinnedThreads` trên JDK 21 | Chỉ khi feature/recording được bật, có threshold/overhead |
| Resource memory | Heap/non-heap metrics, JFR allocation, container RSS | Không suy “mỗi virtual thread dùng 0 byte” |

### Bước 4 — So sánh timeline và giả thuyết

Nếu JFR báo pinned events dày ở một method gọi I/O trong `synchronized`, đó là **bằng chứng tốt** để xem lại lock scope trên JDK 21. Nếu không có pinned events nhưng DB pool wait cao, có thể resource capacity mới là bottleneck. Nếu CPU luôn 100% với nhiều runnable virtual tasks, cần CPU profiling/scheduling analysis.

Cân nhắc **duration/frequency** của pinning, không chỉ số sự kiện. Một event 25 ms ở warm-up chưa đồng nghĩa production không thể scale, trong khi pinning liên tục nhiều giây ở hot endpoint có thể nghiêm trọng.

### Bước 5 — Chọn giải pháp theo nguyên nhân

- Pinning do blocking trong synchronized: tách I/O khỏi monitor hoặc dùng cơ chế lock phù hợp khi bảo đảm correctness.
- DB pool exhaustion: điều chỉnh concurrency, connection limit, SQL latency, timeouts và load shedding.
- CPU saturation: tối ưu CPU-heavy code hoặc scale cores/instances; không tăng số virtual threads vô hạn.
- ThreadLocal memory pressure: loại per-thread resource caches không phù hợp, dùng shared resource pool có lifecycle rõ.
- Missing virtual thread visibility: thêm JFR/virtual-aware dump, correlation IDs và metrics app-level.
- Long request latency: xem downstream/timeout/retry, không kết luận virtual threads “chạy chậm”.

### Bước 6 — Báo cáo kết luận kèm giới hạn

Mẫu mô tả giả định:

```yaml
captureTimeUtc: "2026-10-29T09:30:00Z"
service: "checkout-service"
jvmVersion: "21.0.x"
virtualTaskModel: "one virtual thread per incoming request"
observation:
  requestsInFlight: 2500
  platformThreadCount: 56
  cpuUtilization: "medium"
  databasePoolWait: "high"
  pinnedJfrEvents: "not observed in this recording"
hypotheses:
  - "database connection capacity may limit throughput"
notProven:
  - "no pinning exists outside recording window"
  - "platformThreadCount measures total virtual threads"
nextSteps:
  - "correlate pool wait with p99 latency"
  - "review DB query and timeout behavior"
```

Các con số và tên trên **chỉ là ví dụ**, không phải dữ liệu của một process đã quan sát. Kết luận tốt luôn tách **đã đo** và **chưa chứng minh**.

## 13. Tự kiểm tra và đáp án

**Câu 1.** Java 21 có mấy loại đối tượng `Thread` chính? Carrier là loại nào?

**Đáp án:** **hai loại**: platform và virtual. Carrier là **một platform thread đang được dùng để chạy virtual thread**, không phải loại thứ ba.

**Câu 2.** Bên trong virtual thread, `Thread.currentThread().isVirtual()` trả gì khi thread đang mounted trên carrier?

**Đáp án:** **`true`**. `Thread.currentThread()` trả virtual Thread logic, không phải carrier.

**Câu 3.** Một virtual thread chờ I/O, JVM unmount và carrier chạy một virtual thread khác. Khi I/O hoàn tất, virtual thread cũ có bắt buộc remount đúng carrier cũ không?

**Đáp án:** **không**. JVM có thể chọn carrier khác, và Java code không cần tự lưu carrier identity.

**Câu 4.** OS có 16 cores thì có thể có 10.000 virtual threads không?

**Đáp án:** có thể nếu memory/resources cho phép, nhất là phần lớn đang chờ I/O. Nhưng **không có 10.000 tác vụ tính toán CPU đồng thời**; năng lực tính toán vẫn chịu giới hạn cores/quota.

**Câu 5.** Virtual threads làm mỗi SQL query nhanh gấp 10 lần?

**Đáp án:** **không**. Chúng giúp tăng khả năng phục vụ nhiều concurrent waiting tasks nếu giới hạn trước đây là OS threads; DB latency/capacity không tự biến mất.

**Câu 6.** Java 21 pinning liên quan `synchronized` trong trường hợp nào?

**Đáp án:** khi virtual thread **bị block lúc vẫn ở trong synchronized block/method** (và một số native/foreign calls), không unmount được, giữ carrier. Critical sections ngắn không có blocking lâu thường không cần thay.

**Câu 7.** Có cần thay tất cả `synchronized` bằng `ReentrantLock` để chạy virtual threads?

**Đáp án:** không. Chỉ sửa những hot paths **thường xuyên và lâu** bị pin; giữ correctness, lock ordering và resource policy.

**Câu 8.** Java 21 `ThreadMXBean.getThreadCount()` hiển thị 40, còn ứng dụng có 5.000 virtual requests chờ. Có bất thường không?

**Đáp án:** không nhất thiết; `ThreadMXBean` đo **platform threads**, không đếm virtual threads.

**Câu 9.** Một JFR recording không có `jdk.VirtualThreadPinned`. Chứng minh không hề có pinning?

**Đáp án:** không. Có thể ngoài cửa sổ recording, dưới threshold, event tắt, hoặc trong các nhánh chưa được thu.

**Câu 10.** ThreadLocal có chuyển từ virtual thread A sang carrier khi A unmount không?

**Đáp án:** không. `ThreadLocal` gắn với **logical Thread A**, không phải carrier; chính vì thế per-thread caches lớn có thể làm memory tăng khi có rất nhiều virtual threads.

**Câu 11.** Tại sao `newVirtualThreadPerTaskExecutor()` không phải virtual-thread pool?

**Đáp án:** nó tạo **virtual thread mới mỗi task**, không giữ một số virtual threads để tái sử dụng tasks. Carrier platform threads mới là execution resources do scheduler quản lý.

**Câu 12.** Nếu virtual threads đều là daemon, vì sao cần `Future.get()` hoặc `join()`?

**Đáp án:** để đợi work hoàn thành và xử lý lỗi; nếu main/non-daemon threads kết thúc trước, JVM có thể shutdown khi còn virtual tasks chưa hoàn tất.

**Câu 13.** Carrier P1 dùng 90% CPU. Có thể kết luận request A của virtual thread đã dùng 90% CPU?

**Đáp án:** không. P1 có thể mang nhiều virtual threads lần lượt; cần CPU sampling/trace correlation để phân bổ hotspots theo logical work.

**Câu 14.** Điều chỉnh `jdk.virtualThreadScheduler.parallelism` từ 8 lên 100 có luôn cải thiện throughput?

**Đáp án:** không. CPU quota, pinning, memory, external pool/DB limits và overhead có thể khiến kết quả xấu đi. Cần benchmark và đo nguyên nhân.

**Câu 15.** Vì sao bài này dùng Java 21 chứ không thể biên dịch ví dụ virtual threads trên Java 17?

**Đáp án:** virtual threads trở thành tính năng chính thức tại Java 21 với `Thread.ofVirtual`, `isVirtual` và per-task executor; Java 17 chưa có các API đó.

## 14. Checklist thực hành và vận hành

- Hiểu Java 21 chỉ có **platform Thread** và **virtual Thread**; carrier là **vai trò của platform Thread**.
- Nắm hai tầng scheduling: **JVM mount virtual → carrier platform → OS schedule carrier trên CPU**.
- Hiểu **unmount** khi park/blocking operation hỗ trợ; carrier có thể được tái sử dụng, remount không buộc cùng carrier.
- Trong virtual code, `Thread.currentThread()` là **virtual Thread**, không phải carrier.
- Không dùng `threadId()`/tên virtual Thread để suy OS TID của carrier.
- Biết virtual threads là **daemon**, có priority cố định, tên mặc định rỗng và hỗ trợ ThreadLocal.
- Viết code Java 21 với `Thread.ofVirtual`, `Thread.startVirtualThread` hoặc `Executors.newVirtualThreadPerTaskExecutor`; chờ completion và xử lý failure.
- Không pool/reuse virtual threads chỉ để giới hạn DB/HTTP capacity; giới hạn **resource thực**.
- Phân biệt I/O-bound scale với CPU-bound work; virtual threads tăng **throughput tiềm năng**, không hứa giảm latency task.
- Với **JDK 21**, tìm các hot paths blocking trong `synchronized`/native gây **pinning**; không thay toàn bộ monitors một cách máy móc.
- Dùng JFR `jdk.VirtualThreadPinned`, tùy chọn trace pinning của đúng JDK 21 và thread dumps có support virtual.
- Biết `ThreadMXBean`/OS tools chủ yếu thấy **platform threads**, không dùng để đếm đầy đủ virtual tasks.
- Xác minh đúng JVM/PID/start time/JDK build, container/CPU quota, downstream resource limits và cửa sổ incident.
- Không kết luận root cause từ một thread count, một carrier name hoặc một snapshot; đối chiếu metrics/JFR/traces và tính khả dụng của công cụ.

**Kết luận:** virtual thread là **đơn vị thực thi logic**, platform thread là **đơn vị Java OS-backed**, và carrier là **platform thread được scheduler dùng tạm thời để chạy virtual thread**. Quan hệ mount/unmount cho phép nhiều concurrent I/O-waiting tasks dùng ít OS threads hơn, nhưng **không loại bỏ giới hạn CPU hay external resources**. Khi chẩn đoán Java 21, cần nắm rõ pinning, identity, scheduler và giới hạn của platform-only observability để tránh những kết luận sai về số threads, CPU và khả năng mở rộng.

### Tài liệu tham khảo chính thức

- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): platform/virtual/carrier, mount/unmount, JDK 21 pinning, API tạo thread, JFR events, `Thread.dump_to_file`.
- [OpenJDK — JEP 444: Virtual Threads](https://openjdk.org/jeps/444): mục tiêu, thiết kế scheduling, tính mở rộng, giới hạn và quyết định API finalize ở Java 21.
- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): phân biệt platform/virtual, `currentThread()`, `isVirtual()`, daemon/priority, scheduler system properties.
- [Java SE 21 — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor()`.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): giới hạn chỉ quản lý platform threads.
- [Oracle JDK 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): serviceability commands theo JVM đích.
- [Oracle JDK 21 — Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.html): JFR recording và event configuration.
