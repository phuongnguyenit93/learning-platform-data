# Ngăn xếp của luồng ảo và giới hạn của sơ đồ mỗi luồng có một native stack

## 1. Mô hình cũ đúng với platform thread, không đúng với mọi Java thread

Một sơ đồ JVM thường gặp là:

~~~text
Java Thread A ── OS thread A ── native stack A
Java Thread B ── OS thread B ── native stack B
Java Thread C ── OS thread C ── native stack C
~~~

Đó là mô hình gần đúng cho **platform threads** trên HotSpot: mỗi platform thread gắn với một OS thread trong lifetime của nó, dùng native stack/context của OS thread. Từ **Java 21**, có thêm **virtual threads**: chúng vẫn là `java.lang.Thread` với danh tính, locals, call stack và exception handling, nhưng **không nắm riêng một OS thread/native stack trong toàn lifetime**.

~~~text
             VIRTUAL THREADS (logical concurrent tasks)
               VT-1       VT-2       VT-3 ... VT-10000
                 |          |          |
                 +----------+----------+-------+
                            |
                       JVM scheduler
                            |
           mount VT đang chạy lên một carrier
                            |
                  +---------+---------+
                  |                   |
              carrier-1            carrier-2
                  |                   |
             OS thread 1          OS thread 2
                  |                   |
           native stack 1      native stack 2

VT bị park/unmount: giữ execution state/call stack logic,
có thể ở các stack chunk objects trên Java heap.
Không cần 10000 OS/native stacks riêng cho 10000 VTs.
~~~

**Kết luận phải phân biệt hai mệnh đề:**

- Một virtual thread **có Java stack logic** chứa frames, variables, method calls và trạng thái exception handling.
- Virtual thread **không sở hữu một native stack riêng cố định**; nó dùng một carrier platform thread khi đang chạy và có thể **unmount** khi chờ một blocking operation được JDK hỗ trợ.

Không suy ra “VT luôn chạy trong heap mà chẳng dùng OS thread”. Khi thực thi CPU instructions, một VT vẫn **được mount trên một platform/OS carrier thread**.

## 2. Mốc Java 17, 19, 20, 21 và 24

| JDK | Tình trạng virtual threads | Hệ quả |
| --- | --- | --- |
| **17** | Không có API chuẩn virtual threads | Không thể compile `Thread.ofVirtual()` bằng `--release 17` |
| **19** | JEP 425: preview lần đầu | Phải dùng tính năng preview của đúng runtime |
| **20** | JEP 436: preview lần hai | Vẫn là preview |
| **21** | **JEP 444** chính thức đưa virtual threads vào Java | `Thread.ofVirtual()`, `isVirtual()`, `newVirtualThreadPerTaskExecutor()` |
| **24** | **JEP 491** cải thiện monitor/synchronized pinning | Kết luận về pinning JDK 21 không còn áp nguyên xi |

**Các ví dụ runnable trong bài yêu cầu Java 21+**, dù tên module là Java Advance - jvm. Nếu triển khai thực tế vẫn dùng JDK 17 thì học phần này dùng để hiểu sự thay đổi trong thiết kế JVM; muốn dùng API virtual threads ổn định cần JDK 21 trở lên.

Lệnh:

~~~bash
javac --release 21 VirtualThreadParkingDemo.java
java VirtualThreadParkingDemo
~~~

`--release 21` là **API/language target tại thời điểm biên dịch**. Chạy bytecode ấy trên JDK 24 vẫn sử dụng scheduler, HotSpot và GC của **JDK 24**, không phải tự động mô phỏng mọi chi tiết của JDK 21.

## 3. Ba ý nghĩa của “stack” cần tách bạch

### 3.1. Java call stack logic

Một luồng thực thi `handleRequest() → authenticate() → fetch() → read()` có các Java frames về mặt ngữ nghĩa JVM. Frames chứa trạng thái của method, locals/operand stack ở cấp bytecode và thông tin return/exception.

~~~text
VT logical call stack:

handleRequest()
    └── authenticate()
        └── fetch()
            └── readFromSocket()  ← tạm dừng chờ I/O
~~~

Khi hoạt động I/O kết thúc, chương trình phải **tiếp tục đúng call chain và locals**, không buộc tác giả viết lại bằng callback state machine.

### 3.2. Native stack của platform/carrier thread

Platform thread gắn với OS thread; OS thread dùng native stack và context do OS/JVM quản lý. Với kiểu “platform thread per request”, một request blocking giữ OS thread của nó suốt quá trình chờ. Native stack có thể reserved/committed/resident khác nhau, vì vậy không phải cứ `-Xss1m` thì mọi stack đã dùng đúng 1 MiB RAM vật lý.

**Carrier** là platform thread được scheduler sử dụng để thực thi virtual thread. Native stack của carrier là tài nguyên thuộc carrier, **không phải tài nguyên gắn cứng với một VT suốt lifetime**.

### 3.3. Continuation và stack chunks trên heap

HotSpot triển khai virtual-thread continuation và lưu stack trạng thái suspend qua các **stack chunk objects nằm trên Java heap do GC quản lý**, theo JEP 444. Stack có thể grow/shrink theo độ sâu thực thi. Một VT có call stack nông và chỉ chờ network không cần cùng footprint với VT có nhiều frames sâu.

Không mô tả rằng **mọi frame luôn nằm 100% trên heap ngay cả khi VT đang chạy**: execution vẫn chạy trên carrier OS stack và VM có thể chuyển/bảo toàn frames khi mount/unmount. Cách biểu diễn memory chính xác là chi tiết implementation HotSpot/JDK.

Quan trọng: JVM Specification mô tả abstract JVM stacks; không bắt buộc mọi JVM vendor phải tổ chức virtual-thread stack chunks y hệt HotSpot.

## 4. Mount, park, unmount và resume

~~~text
Time →
Carrier OS thread:
  | VT-A runs | VT-B runs ........ | VT-C runs | VT-A resumes |

VT-A:
  xử lý → blocking socket read → PARK/UNMOUNT → I/O ready → RESUME
                                     |
                              continuation state
                              heap stack chunks
~~~

Một chu kỳ khái niệm:

1. `Thread.ofVirtual().start(task)` tạo VT, lên lịch task.
2. Scheduler **mount** VT trên carrier khả dụng.
3. VT chạy Java code trên OS thread của carrier.
4. VT gặp một blocking operation được JDK hỗ trợ cho việc unmount (ví dụ một số socket I/O, `BlockingQueue.take()` hoặc `CountDownLatch.await()` trong điều kiện thích hợp).
5. JVM giữ execution state/stack để có thể resume, **unmount** VT, trả carrier về scheduler.
6. Khi hoạt động có thể tiếp tục, VT được đánh thức/schedule, có thể **mount lên carrier khác**.
7. Code chạy tiếp theo Java stack logic cũ, giữ `try/catch/finally` và locals theo contract.

**Không có bảo đảm VT luôn dùng một carrier cụ thể**, cũng không có API portable `getMyCarrierThread()`. `Thread.currentThread()` trong code VT trả về **chính VT**, không phải carrier.

### Điểm unmount không đồng nghĩa mọi method call

Virtual thread không tự unmount khi gọi một method ngắn, đọc một field hay tính toán CPU. Nó vẫn sử dụng carrier trong khi làm việc; nếu code CPU-bound không block, virtual thread vẫn chiếm khả năng thực thi của một OS thread như bình thường.

Một số đoạn native/JNI hoặc đường blocking không hỗ trợ unmount có thể **pin carrier**. Vì vậy câu “mọi blocking call đều giải phóng carrier” là sai.

## 5. So sánh platform stack và virtual stack

| Câu hỏi | Platform thread | Virtual thread |
| --- | --- | --- |
| Là Java `Thread` object? | Có | Có |
| Có Java frames/stack trace logic? | Có | Có |
| Có OS thread dành riêng suốt lifetime? | Có theo cơ chế platform threads | **Không** |
| Có native OS stack dành riêng suốt lifetime? | Thường có | **Không** |
| Có cần carrier OS thread khi chạy CPU? | Tự là OS thread | Có, sử dụng carrier |
| Khi chờ I/O được hỗ trợ, có thể nhả OS thread? | Thông thường không trong synchronous platform-thread I/O | **Có thể unmount** |
| Có thể tiếp tục trên carrier khác? | Không áp dụng | **Có** |
| Execution state khi unmount có thể nằm ở heap chunks? | Không theo cùng mô hình | **Có** |
| Số lượng có thể vượt xa OS threads? | Bị OS thread resources giới hạn | **Có**, tùy heap và các tài nguyên khác |
| CPU-bound method có tự chạy nhanh hơn? | Không có cam kết | Không có cam kết |

**“Virtual thread không có stack”** là phát biểu sai. Nếu chúng không có stack logic thì code đồng bộ Java với nested calls, recursion, exceptions và debugger stack traces sẽ không có semantics quen thuộc.

## 6. Vì sao stack chunks trên heap làm virtual threads rẻ hơn?

Platform-thread-per-request có thể cần một OS thread, native stack, OS context và scheduler resources cho mỗi request đang chờ. Với VT, carrier được tái sử dụng khi task blocked/unmounted; nhiều call stacks logic được giữ trên heap theo nhu cầu.

Ví dụ kiến trúc:

~~~text
10000 synchronous requests đang chờ network:

Platform-thread-per-request:
  gần 10000 platform/OS threads nếu không bị pool giới hạn
  rất nhiều native stacks và OS scheduling state

Virtual-thread-per-request:
  10000 Java VT objects và waiting continuations có thể tồn tại
  một số carriers được scheduler tái sử dụng khi VTs unmount
  stack chunks/locals được GC quản lý trên heap
~~~

Đây chỉ là **mô hình khả năng mở rộng**, không phải công thức memory hay lời hứa rằng số carriers luôn bằng `Runtime.availableProcessors()` hoặc VT chỉ tốn 1 KiB. JVM còn tạo GC/JIT/service threads, còn scheduler/native code có thể dùng additional platform threads.

### VT vẫn tiêu thụ heap và giữ object sống

Một call stack parked có thể tham chiếu tới object lớn ở local:

~~~java
static void handle() throws InterruptedException {
    byte[] payload = new byte[2_000_000];
    Thread.sleep(100);
    consume(payload);
}
~~~

Đây là **mảnh code minh họa** với `consume` do application định nghĩa. Vì `payload` cần được dùng **sau khi sleep**, object 2 MB vẫn phải sống qua khoảng chờ, dù carrier có thể đã được giải phóng. Với 10.000 VT giữ mỗi VT một mảng 2 MB, riêng payload lên đến **khoảng 20 GB**, chưa tính overhead và stacks.

Tạo nhiều VT chỉ rẻ khi mỗi task thực sự có footprint vừa phải. Nên theo dõi **heap live set, request buffering, ThreadLocal state, số tasks đang chờ, scheduler queues** chứ không chỉ đếm native OS threads.

### Virtual stack chunks và GC roots

Theo JEP 444, virtual-thread stacks trên heap **không được đối xử giống native platform stacks như GC roots**. Những object mà frames của một continuation reachable đang tham chiếu tới vẫn có thể reachable qua **heap object graph**. Không suy luận “VT đã unmount nên object trong local được tự động GC”.

### StackOverflowError vẫn có thể xảy ra

VT có khả năng stack grow/shrink nhưng không có **stack vô hạn**. Đệ quy sâu vẫn có thể ném `StackOverflowError`.

JEP 444 còn mô tả một **giới hạn JDK 21/G1**: implementation khi ấy không hỗ trợ humongous stack chunk objects; nếu chunk trở nên lớn cỡ nửa G1 region (có thể nhỏ như 512 KiB), có thể bị `StackOverflowError`. Đây là **chi tiết version/collector-specific**, không được áp thành luật bất biến của mọi JDK/JVM.

`-Xss` có liên quan đến stack size/limits theo HotSpot, nhưng **không có nghĩa** `-Xss1m` đặt riêng 1 MiB native stack cho mỗi VT như OS platform thread. Phải phân biệt limit cấu hình với cách representation/cấp phát thực.

## 7. Ví dụ Java 21 hoàn chỉnh: 1.200 virtual threads cùng chờ latch

Tạo file **`VirtualThreadParkingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class VirtualThreadParkingDemo {
    public static void main(String[] args) throws Exception {
        final int tasks = 1200;
        CountDownLatch allWaiting = new CountDownLatch(tasks);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<Boolean>> futures = new ArrayList<>();

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < tasks; i++) {
                futures.add(executor.submit(() -> {
                    boolean virtual = Thread.currentThread().isVirtual();
                    allWaiting.countDown();
                    release.await();
                    return virtual;
                }));
            }
            allWaiting.await();
            System.out.println("tasksReady=" + tasks);
            release.countDown();

            int completed = 0;
            boolean allVirtual = true;
            for (Future<Boolean> future : futures) {
                allVirtual &= future.get();
                completed++;
            }
            System.out.println("completed=" + completed);
            System.out.println("allVirtual=" + allVirtual);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 21 VirtualThreadParkingDemo.java
java VirtualThreadParkingDemo
~~~

**Stdout dự đoán theo API Java 21 (hãy biên dịch bằng `javac --release 21` và chạy trên JDK 21+ để tự kiểm chứng):**

~~~text
tasksReady=1200
completed=1200
allVirtual=true
~~~

Ý nghĩa:

- `newVirtualThreadPerTaskExecutor()` tạo **một virtual thread cho từng task**, chứ không tạo pool 1.200 OS threads.
- Mỗi task báo đã tới latch qua `allWaiting.countDown()` rồi chờ `release.await()`.
- Chờ bằng cơ chế `CountDownLatch` được JDK hỗ trợ cho VT có thể làm VT **unmount**, nhường carrier cho task khác.
- Main chỉ in `tasksReady=1200` sau khi tất cả tasks đã tới điểm đó.
- Sau `release.countDown()`, `Future.get()` đợi từng task hoàn tất và nhận kết quả `Thread.currentThread().isVirtual()`.
- `try-with-resources` bảo đảm executor được đóng đúng lifecycle.

**Không suy ra từ stdout rằng JVM dùng chính xác bao nhiêu carriers/OS threads**: ví dụ không đo carrier count. OS/JVM scheduler có thể có parallelism, compensation và thread services khác nhau. Muốn đưa số liệu performance phải đo bằng OS/JFR tools ở workload cụ thể.

Nếu chỉ có JDK 17, source sẽ **không compile với `javac --release 17`** vì API virtual threads chưa tồn tại trong Java SE 17.

## 8. Ví dụ Java 21 hoàn chỉnh: VT vẫn có call stack logic

Tạo file **`VirtualStackTraceDemo.java`**:

~~~java
import java.util.Arrays;

public final class VirtualStackTraceDemo {
    static long descend(int remaining) {
        if (remaining == 0) {
            return Arrays.stream(Thread.currentThread().getStackTrace())
                    .filter(frame ->
                            frame.getMethodName().equals("descend"))
                    .count();
        }
        return descend(remaining - 1);
    }

    public static void main(String[] args) throws Exception {
        Thread worker = Thread.ofVirtual()
                .name("logical-task")
                .start(() -> {
                    System.out.println("virtual=" +
                            Thread.currentThread().isVirtual());
                    System.out.println("logicalFrames=" + descend(5));
                });

        worker.join();
        System.out.println("terminated=" + !worker.isAlive());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 21 VirtualStackTraceDemo.java
java VirtualStackTraceDemo
~~~

**Stdout quan sát trên OpenJDK 24:**

~~~text
virtual=true
logicalFrames=6
terminated=true
~~~

Gọi `descend(5)` lồng sáu lần, tạo call-chain logic ở các giá trị 5, 4, 3, 2, 1, 0. `Thread.currentThread().getStackTrace()` chạy **trong chính VT** và ở JVM thử nghiệm đếm được 6 frames tên `descend`.

`getStackTrace()` có các giới hạn implementation khi stack walking/virtual machine frames; đừng coi mọi JDK bắt buộc hiển thị cùng số frame trong mọi trường hợp. Kết quả **nói rõ một lần chạy**; mục tiêu bài là chứng minh concept VT vẫn có logical call stack, không phải thứ gì đó “không stack”.

`worker.join()` đợi VT kết thúc; `terminated=true` không có nghĩa carrier platform thread của nó bị shutdown.

## 9. Pinning là gì? Tại sao cần phân biệt JDK 21 với JDK 24?

**Pinning** xảy ra khi VT **không thể unmount** khỏi carrier trong một đoạn có blocking operation. Carrier OS thread có thể bị block cùng VT, nên những VTs khác không tận dụng được carrier ấy. Pinning **không nhất thiết làm sai correctness**, nhưng pinning nhiều và lâu có thể làm ứng dụng mất scalability.

### JDK 21–23: synchronized + blocking có thể pin

Ở JDK 21, virtual thread thực hiện blocking operation **trong `synchronized` method hoặc block** có thể giữ carrier bị pin. Ví dụ minh họa:

~~~java
synchronized (lock) {
    readFromRemoteService();  // có thể block lâu
}
~~~

Đoạn này **không độc lập để chạy**, vì `lock` và `readFromRemoteService()` cần do ứng dụng định nghĩa.

Không nên kết luận “mọi synchronized đều xấu”: vùng synchronized rất ngắn để cập nhật state trong memory thường không phải bottleneck. Rủi ro là **thường xuyên và lâu dài** khi block I/O trong monitor. Ở JDK 21, với những chỗ đó, một thiết kế sử dụng `ReentrantLock` có thể tránh pinning monitor-related:

~~~java
lock.lock();
try {
    readFromRemoteService();
} finally {
    lock.unlock();
}
~~~

Ở đây `lock` là `ReentrantLock` do ứng dụng tạo. **Không thay tất cả synchronized một cách máy móc**: phải xét semantics monitor, `wait/notify`, reentrancy, ordering và code exception paths.

### JDK 24+: JEP 491 cải thiện monitor behavior

**JEP 491 — Synchronize Virtual Threads without Pinning** được triển khai trong JDK 24: virtual threads có thể unmount khi block theo các trường hợp Java monitor/synchronization đã được cải thiện. Do đó phát biểu “JDK 24 luôn pin mọi blocking I/O nằm trong synchronized” là **không còn đúng**.

Nhưng **native frames/JNI/foreign calls và một số platform-specific operations** vẫn có thể giữ carrier trong những tình huống khác. Không hứa JDK 24 “xóa sạch mọi pinning”.

| Trường hợp | JDK 21–23 | JDK 24+ |
| --- | --- | --- |
| Blocking dưới Java `synchronized` | Rủi ro monitor pinning | JEP 491 giải quyết các trường hợp monitor tương ứng |
| JNI/native/foreign operation | Có thể giữ carrier | Vẫn có những trường hợp giữ carrier |
| JDK blocking API hỗ trợ unmount, không pinned | Thường nhả carrier | Thường nhả carrier |
| CPU-bound code không block | Tiếp tục dùng carrier | Tiếp tục dùng carrier |

Khi phân tích production, ghi **JDK vendor/build, JVM implementation, OS, thư viện native và JFR settings**. Không sao chép bảng pinning từ tài liệu JDK 21 như định luật vĩnh viễn.

## 10. Virtual threads không thay cho CPU cores hoặc resource limits

Virtual threads được thiết kế để tăng **concurrency của các task thường xuyên chờ I/O**, không làm một phép tính CPU-bound chạy nhanh hơn tự động.

Một hệ thống có 8 CPU cores không thể cùng thực thi một triệu Java CPU-bound tasks ở đúng một thời điểm chỉ vì tạo một triệu virtual threads. Chúng vẫn phải chia sẻ carriers, scheduler và 8 cores đó.

Ví dụ một request làm 2 ms CPU rồi chờ database 100 ms: platform-thread-per-request có thể giữ OS thread lúc chờ; VT có thể nhường carrier khi I/O hỗ trợ unmount, giúp OS thread phục vụ task khác. Nhưng request ấy **vẫn cần thời gian database**; throughput có thể tăng khi nút thắt trước đây là OS threads, còn single-request latency không nhất thiết giảm.

**Downstream vẫn là bottleneck**: 10 DB connections không trở thành 10.000 connections. Nếu 10.000 VTs gọi database cùng lúc thì connection pool, rate limiting, file descriptors, socket buffers và heap retention vẫn giới hạn khả năng phục vụ.

### Bounded concurrency thay vì pooling VTs

JEP 444 khuyên **virtual thread per task**, không pool virtual threads vì chúng là đơn vị task nhẹ, không phải expensive OS worker để tái sử dụng.

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    // Mỗi submit tạo một VT mới cho task.
    var future = executor.submit(() -> performOperation());
    var result = future.get();
    process(result);
}
~~~

Đoạn này là **mảnh minh họa**, phải có `performOperation()`/`process()` thật. Với những downstreams có giới hạn, dùng `Semaphore`, connection pool hoặc backpressure:

~~~java
semaphore.acquire();
try {
    return callDatabase();
} finally {
    semaphore.release();
}
~~~

`semaphore` và `callDatabase()` ở đây thuộc application và code cần xử lý interruption đúng. VT chờ semaphore có thể nhả carrier, nhưng giới hạn concurrency của downstream vẫn phải được duy trì.

## 11. ThreadLocal, object retention và memory budget

Virtual threads hỗ trợ `ThreadLocal` giống platform threads, nhưng một “cache per thread” trở thành vấn đề khi **mỗi task có thread riêng**.

~~~java
private static final ThreadLocal<byte[]> SCRATCH =
        ThreadLocal.withInitial(() -> new byte[1_000_000]);
~~~

Đây là **field minh họa**, không phải chương trình chạy. Một platform thread pool 32 workers có thể tạo khoảng 32 buffers nếu mỗi worker truy cập một lần. Với 20.000 VTs cùng sử dụng ThreadLocal này, có thể có 20.000 buffers tương đương **khoảng 20 GB bytes**, chưa tính objects/stack chunks.

Thay vì cache tài nguyên lớn theo thread, cân nhắc **immutable shared objects, bounded pools, request-scoped data và explicit cleanup**. Thread-local state trong carrier **không** được mặc nhiên xem là ThreadLocal của VT. `Thread.currentThread()` trong VT trả VT, và thread-local namespaces không trộn với carrier.

Tính toán ngân sách:

~~~text
Java heap:
    request payloads, business objects
  + virtual Thread objects
  + stack chunks / continuation state
  + ThreadLocals và Futures/scheduler metadata

Native/process memory:
    carrier OS thread stacks
  + GC/JIT/VM service threads và internal structures
  + JNI/native allocations
  + mapped/direct buffers và OS resources
~~~

Không cộng các số reserved/committed/RSS bừa bãi; chúng có ý nghĩa khác nhau. **Không lấy `N_virtual × -Xss` làm công thức bắt buộc của native stack usage.**

## 12. Quan sát virtual threads: vì sao `ps` và ThreadMXBean là chưa đủ?

OS biết **native threads** (carriers, GC/JIT workers, native library threads...), không biết tất cả virtual threads như một OS thread riêng. Vì vậy:

~~~text
OS native thread count  != logical virtual-thread count
ThreadMXBean count       != số virtual threads đang tồn tại
~~~

JEP 444 ghi rằng trong JDK 21 `ThreadMXBean` tập trung quản lý platform threads và không liệt kê mọi virtual threads như thread manager truyền thống. Nhiều API `ThreadGroup` cũng có giới hạn vì virtual threads không được xem là active group members theo kiểu cũ.

### `jcmd` virtual-thread-aware dumps

Trên JDK 21+, có thể dùng `Thread.dump_to_file`:

~~~text
jcmd PID Thread.dump_to_file -format=text threads.txt
jcmd PID Thread.dump_to_file -format=json threads.json
~~~

Chữ `PID` là chỗ **thay bằng process ID thật**, không phải câu lệnh shell có biến PID mặc định. Cần JDK tools/quyền attach phù hợp. Dump này có thể biểu diễn logical virtual threads/stack traces tốt hơn nhiều dạng legacy dumps.

Với rất nhiều VTs, dump có thể **rất lớn** và ảnh hưởng CPU/memory/disk. Stack traces còn có thể tiết lộ class names/methods/metadata nhạy cảm; kiểm soát quyền truy cập.

### JFR virtual-thread events

Các events JDK 21 có thể dùng:

- `jdk.VirtualThreadStart`/`jdk.VirtualThreadEnd`: theo dõi vòng đời; thường **không bật mặc định** do event volume.
- `jdk.VirtualThreadPinned`: quan sát blocking khi pinned, tùy thresholds/settings (tài liệu JDK 21 mô tả threshold mặc định khoảng 20 ms).
- `jdk.VirtualThreadSubmitFailed`: lỗi khi schedule/start/unpark một VT.

Đọc từ recording đã có:

~~~bash
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
~~~

File `recording.jfr` phải được tạo trước. Event availability, settings và thresholds phụ thuộc JDK version; nếu event không xuất hiện, không khẳng định tuyệt đối “không pinning”.

Trên JDK 21, property:

~~~bash
java -Djdk.tracePinnedThreads=full MyMain
~~~

có thể giúp phát hiện một số pinning call stacks (`MyMain` cần là main class có thật). Với JDK 24+, JEP 491 đã thay đổi monitor behavior; không dựa vào absence of trace làm bằng chứng scheduler hoàn hảo.

## 13. Một bảng thiết kế cho tình huống 10.000 requests I/O

Giả sử có 10.000 requests chờ network trong khi mỗi request chỉ cần ít CPU.

| Tiêu chí | Platform-thread-per-request | Virtual-thread-per-request |
| --- | --- | --- |
| Thread cho mỗi request logic | Platform thread | Virtual thread |
| Native OS stack per request | Thường phải giữ | Không yêu cầu độc lập per VT |
| Blocking I/O | OS thread bị chiếm trong kiểu truyền thống | Có thể unmount VT và reuse carrier |
| Code tuần tự với `try/finally` | Tự nhiên | Cũng tự nhiên |
| Memory cho request context | Heap objects và platform stack | Heap objects và VT stack chunks |
| Downstream connection limit | Vẫn phải quản lý | **Vẫn phải quản lý** |
| CPU-bound throughput | Bị giới hạn CPU | **Vẫn bị giới hạn CPU** |
| JVM pinning pitfalls | Không theo virtual scheduler | Cần xét JDK/native/synchronized version |
| Profiling | Native+Java thread tools | Virtual-thread-aware dumps/JFR cần thiết |

**Không thể chọn VT chỉ từ số native stacks ít hơn**. Phải đo end-to-end throughput, p99/p99.9, RSS/heap live set, CPU/carriers, executor task backlog, connection pools và lỗi timeout/OOM trong workload thật.

### Khi nào VT có ích nhất?

- Nhiều concurrent tasks chủ yếu **chờ I/O** có APIs hỗ trợ suspension.
- Application cần code đồng bộ dễ đọc, một task một thread, cần mở rộng vượt giới hạn OS threads truyền thống.
- Resource limits (DB, sockets, heap) có backpressure rõ ràng.

### Khi nào VT không cứu được?

- CPU-bound hot loops đã saturate cores.
- Database đã đầy tải và connection pool chờ dài.
- Mỗi VT giữ payload lớn quá lâu, khiến heap/GC pressure cao.
- Native code pin carriers lâu ở nơi blocking thường xuyên.
- Hệ thống dùng async framework tối ưu sẵn với rất ít OS threads và không có vấn đề thread scarcity.

## 14. Những hiểu sai điển hình

1. **“Mỗi instance `Thread` đều có native stack riêng.”** Sai với VTs.
2. **“Virtual thread không có call stack.”** Sai; vẫn có logical Java frames và stack traces.
3. **“VT không cần OS thread để chạy CPU.”** Sai; cần carrier.
4. **“Carrier của VT cố định.”** Sai; có thể đổi khi resume.
5. **“Thread.currentThread() trả carrier.”** Sai; trả virtual thread.
6. **“VT đang park luôn giữ OS thread.”** Không khi operation được hỗ trợ unmount và không pinned.
7. **“Mọi blocking call đều unmount.”** Sai; native/platform-specific/pinning.
8. **“Virtual-thread stack là native OS stack bằng `-Xss`.”** Sai.
9. **“VT stack chunk không nằm trên heap.”** Sai với HotSpot/JEP 444.
10. **“Heap không tăng khi tạo hàng nghìn parked VTs.”** Sai; chunks, locals, payloads, metadata có footprint.
11. **“VT không bao giờ StackOverflowError.”** Sai.
12. **“VT chạy CPU-bound nhanh hơn platform thread.”** Không phải mục tiêu.
13. **“Java 17 hỗ trợ stable `Thread.ofVirtual()`.”** Sai; Java 21.
14. **“JDK 24 vẫn luôn pin trong synchronized.”** Sai nói chung do JEP 491.
15. **“JDK 24 không còn bất kỳ pinning nào.”** Sai; native cases vẫn tồn tại.
16. **“Cần pool các VT giống OS threads.”** Không phù hợp mô hình virtual-thread-per-task.
17. **“ThreadLocal của carrier là ThreadLocal của VT.”** Sai.
18. **“Tăng số VTs làm tăng số DB connections.”** Sai.
19. **“ThreadMXBean đếm tất cả virtual threads trong JDK 21.”** Sai.
20. **“OS thread count thấp chứng minh heap memory thấp.”** Sai.
21. **“Một VT có thể chạy CPU đồng thời trên hai carriers.”** Sai; một VT tại một thời điểm chỉ có một execution flow.
22. **“Stack chunks được GC quản lý nên mọi object local lúc VT park đều được GC.”** Sai.
23. **“Thấy `logicalFrames=6` tức VT đã unmount sáu lần.”** Sai; đó là call frames logic, không phải scheduler transitions.
24. **“Java API hứa số carrier threads cố định.”** Sai.

## 15. Bài tập tự kiểm tra

1. Một JVM có 10.000 VTs và 32 carriers, có cần 10.000 native stack reservations per VT không? **Không**.
2. VT đang chạy CPU thực sự chạy ở đâu? **Trên carrier platform/OS thread**.
3. VT bị unmount có mất locals/Java frames không? **Không**, runtime giữ continuation state để resume.
4. Heap stack chunks có nghĩa VT không thể stack overflow không? **Không**.
5. Tính năng stable virtual threads được phát hành ở Java nào? **Java 21, JEP 444**.
6. `--release 21` trên JDK 24 làm runtime thành JDK 21 không? **Không**.
7. `newVirtualThreadPerTaskExecutor()` tạo 1 OS thread cho mỗi submit không? **Không**.
8. `Thread.currentThread().isVirtual()` trong VT trả gì? **True**.
9. Một socket I/O có hỗ trợ unmount thì carrier có thể phục vụ VT khác trong lúc chờ không? **Có**.
10. Mọi JNI operation có đảm bảo unmount không? **Không**.
11. JDK 21 blocking trong synchronized có thể pin carrier không? **Có**.
12. JDK 24 cải thiện điều đó bằng JEP nào? **JEP 491**.
13. JEP 491 đã loại bỏ mọi native-related pinning chưa? **Chưa**.
14. Chạy 1.200 tasks trong ví dụ có chứng minh đúng 2 carriers không? **Không**, không đo carrier count.
15. Vì sao không dùng `ThreadMXBean.getThreadCount()` làm toàn bộ VT count ở JDK 21? **MXBean chủ yếu quản lý platform threads**.
16. Để xem stacks của VTs bằng JDK tools dùng lệnh gì? **`jcmd PID Thread.dump_to_file -format=json ...`**.
17. 10.000 VT mỗi VT giữ `byte[2_000_000]` qua sleep tạo memory pressure cỡ nào? **Khoảng 20 GB bytes payload trước overhead**.
18. Khi DB chỉ có 20 connections, tạo 10.000 VTs có tự tăng DB throughput vô hạn không? **Không**.
19. VTs có lợi chủ yếu với CPU-bound hay I/O-blocking concurrency? **I/O-blocking concurrency**.
20. Câu đúng hơn là “VT không có stack” hay “VT có Java stack logic nhưng không có native OS stack riêng cố định”? **Câu thứ hai**.

## 16. Tài liệu tham khảo chính thống

- **OpenJDK JEP 444 — Virtual Threads** (final in JDK 21, stack chunks, GC interactions): https://openjdk.org/jeps/444
- **Oracle Java SE 21 — Virtual Threads**, carrier scheduling, debugging, pinning và hướng thiết kế: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- **Java SE 21 `Thread` API**, `Thread.ofVirtual()` và `isVirtual()`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html
- **Java SE 21 `Executors` API**, virtual-thread-per-task executor: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html
- **OpenJDK JEP 425/436**, preview JDK 19/20: https://openjdk.org/jeps/425 và https://openjdk.org/jeps/436
- **OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24):** https://openjdk.org/jeps/491
- **Oracle Java SE 24 migration changes** ghi nhận JEP 491: https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html
- **Oracle JDK 21 `jcmd`**, Thread.dump_to_file: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **JVMS 21 §2.5 Runtime Data Areas**, abstract JVM stacks: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5

**Kết luận:** Virtual thread là **Java thread thật ở cấp ngữ nghĩa**: có locals, call stack, stack traces và exception handling. Nhưng từ JDK 21, nó **không cần một OS thread/native stack dành riêng cho cả lifetime**; JVM mount VT lên **carrier** khi chạy, có thể lưu continuation/stack chunks trên **Java heap** và trả carrier lại scheduler khi VT chờ hỗ trợ unmount. Sơ đồ “mỗi Java thread = một native stack” chỉ nên dùng cho platform threads. Sự mở rộng concurrency không loại bỏ giới hạn CPU, heap, native pinning, downstream connections và cần đọc đúng khác biệt **JDK 21 so với JDK 24+**.
