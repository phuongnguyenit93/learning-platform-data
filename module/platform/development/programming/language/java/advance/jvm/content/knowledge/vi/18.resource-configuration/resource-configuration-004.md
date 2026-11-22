# -Xss, số luồng và ngân sách bộ nhớ ngoài heap

## 1. Bài toán: JVM còn cần bao nhiêu bộ nhớ khi heap đã được giới hạn?

Một cấu hình Java server có thể đặt `-Xmx512m` trong container giới hạn 1 GiB, nhưng vẫn bị hệ điều hành giết vì hết bộ nhớ; hoặc gặp `java.lang.OutOfMemoryError: unable to create native thread` dù biểu đồ **heap used** thấp. Nguyên nhân không có gì mâu thuẫn: **Java heap chỉ là một phần của bộ nhớ tiến trình**, còn **mỗi platform/native thread** cần stack và nhiều tài nguyên khác. 

Chủ đề thuộc nhóm **Cấu hình tài nguyên** trong JVM: phải hiểu quan hệ giữa `-Xss`, số platform threads, stack reservations/commit, giới hạn OS/cgroup và headroom dành cho **non-heap/native** memory, thay vì chỉ giảm `-Xmx` hay tăng `-Xss` theo cảm tính.

Hãy tách bốn câu hỏi:

1. **Độ sâu stack:** một luồng cần stack bao nhiêu để chạy các lời gọi Java/native an toàn? Việc này liên quan `StackOverflowError` và cấu trúc call chain.
2. **Số luồng sống đồng thời:** có bao nhiêu **platform/native threads** do ứng dụng và JVM tạo ra, gồm cả GC/JIT/runtime threads?
3. **Bộ nhớ ngoài heap:** metaspace, JIT code cache, direct buffers, GC bookkeeping, thread stacks, JNI/native allocations và mapped memory dùng bao nhiêu?
4. **Giới hạn thực thi:** OS/cgroup cho phép bao nhiêu resident/committed memory, native threads, PIDs/tasks và CPU?

**Không có công thức chính xác chung “native memory = số thread × `-Xss`”.** Đây chỉ là một thành phần **ước lượng về mức stack reservation**; actual committed/resident stack pages và phần native memory khác phải đo trên JVM/OS thật.

## 2. Phân biệt JVM stack, Java heap và OS/native stack

### 2.1. Java heap

Java objects và arrays thông thường nằm trong heap do JVM/GC quản lý. Các flags:

- `-Xms`: kích thước Java heap ban đầu.
- `-Xmx`: kích thước tối đa của Java heap.
- `-Xmx` **không** giới hạn toàn bộ RSS hoặc process committed memory.

Vì thế `-Xmx512m` không đồng nghĩa “Java chỉ được sử dụng 512 MiB RAM”.

### 2.2. JVM stack logic

Mỗi **Java execution thread** có call stack logic chứa frames của các method calls, locals, operand stack ở mức JVM bytecode và thông tin return/exception handling. Khi `a()` gọi `b()` rồi `c()`, stack tăng theo call depth; khi các lời gọi trả về, những frames không còn cần thiết được loại khỏi active call chain.

`StackOverflowError` là lỗi khi JVM không thể thỏa mãn yêu cầu thêm stack theo các giới hạn của runtime. Nó **không** có nghĩa Java heap đã dùng hết `Xmx`.

### 2.3. Native stack của platform thread

Trên HotSpot, một **platform thread** thường tương ứng một OS/native thread. OS cần native stack, thread ID, scheduling state, TLS/allocator/runtime resources. HotSpot có thể reserve vùng địa chỉ ảo cho native stack; các pages thực sự **committed** hoặc **resident** tùy OS và cách thread sử dụng stack.

~~~text
Java process
├── Java Heap          (-Xms, -Xmx)
├── Metaspace/Class metadata
├── JIT code cache
├── GC and JVM internal/native structures
├── Direct/native buffers, JNI, third-party allocations
├── Thread 1 (platform / OS) ── native stack 1
├── Thread 2 (platform / OS) ── native stack 2
├── ...
└── JVM service, GC and compiler native threads
~~~

Stack là tài nguyên của **từng OS thread** trong mô hình platform threads. Một pool có 500 workers bị blocking I/O nhưng vẫn còn sống có thể tiếp tục giữ **native stack reservations** của 500 threads, dù phần lớn không chạy CPU.

### 2.4. Virtual threads là trường hợp khác (Java 21+)

Từ Java 21, **virtual threads** có Java call stacks logic nhưng không buộc mỗi VT giữ một OS/native stack riêng suốt lifetime. Khi blocking operation hỗ trợ **unmount**, HotSpot có thể lưu continuation/stack chunks trên heap và dùng lại **carrier platform thread**.

**Điều này không biến stack memory thành 0**: mỗi VT vẫn có heap objects, stack chunks/locals và các references còn sống; carriers, GC/JIT/native threads vẫn dùng native stacks. Mã Java 17 chạy **platform threads** trong bài lab; `Thread.ofVirtual()` chỉ có API chuẩn từ Java 21.

**Kết luận phạm vi:** Công thức `số luồng × -Xss` là mô hình sơ bộ cho **platform thread stacks**, không được nhân với tổng số virtual threads.

## 3. `-Xss` là gì, đơn vị và default?

Theo Java launcher documentation của Oracle JDK 17, `-Xss` **sets the thread stack size**. Có thể dùng số bytes hoặc hậu tố `k`, `m`, `g`:

~~~bash
java -Xss256k -cp . StackDepthDemo
java -Xss512k -cp . StackDepthDemo
java -Xss1m   -cp . StackDepthDemo
~~~

Các ví dụ dùng Java 17+ trên **HotSpot/OS hỗ trợ**. VM có thể từ chối mức quá nhỏ, làm tròn theo alignment/pages hoặc áp các ràng buộc nền tảng. Không có một minimum portable áp cho mọi JVM/OS/architecture.

**Một số mặc định Oracle JDK 17 được tài liệu ghi nhận:**

| Nền tảng | Ví dụ default tham khảo |
| --- | --- |
| Linux/x64 64-bit | 1.024 KiB |
| macOS 64-bit | 1.024 KiB |
| Oracle Solaris 64-bit | 1.024 KiB |
| Windows | Phụ thuộc virtual memory/platform |

Đây là **giá trị trong tài liệu Java 17 của Oracle**, không phải giá trị bắt buộc cho mọi build ở mọi thời điểm. Kiểm tra đúng JVM thực bằng flags và NMT nếu quyết định capacity.

`-XX:ThreadStackSize=` là flag HotSpot liên quan, nhưng **đơn vị cơ bản của flag là kilobytes**, không giống cách trình bày bytes của `-Xss`. Tránh nhầm `-XX:ThreadStackSize=512` với 512 bytes; cũng tránh dùng cả hai flags chồng nhau khi không có lý do.

### `-Xss` không phải một ngưỡng live memory

Một platform thread cấu hình stack nominal 512 KiB **không nhất thiết làm RSS tăng đúng 512 KiB tại thời điểm tạo**. OS có thể reserve address space, commit/touch pages khi stack grow và có guard/shadow pages, alignment và metadata khác. Native stack limit còn có tác động từ JVM internals và OS mapping policies.

**Phân biệt rõ:**

- **Nominal/configured stack size:** input cho VM để cấu hình thread stack.
- **Reserved:** virtual address range dành trước, có thể lớn hơn số bytes touched.
- **Committed:** memory committed theo OS/JVM tracking.
- **Resident (RSS/Working Set):** pages đang thực sự resident theo OS accounting.
- **Guard/yellow/red/shadow pages:** vùng bảo vệ và an toàn khi stack gần chạm giới hạn, tính toán implementation-specific.

Đừng yêu cầu **NMT `Thread stack reserved`** bằng đúng `N_workers × Xss` vì category còn gồm main thread, GC/JIT/service threads và OS/VM overhead; size thực có thể được làm tròn.

## 4. Tác động lên `StackOverflowError`

Với nhiều lời gọi lồng sâu hoặc recursion, stack frames tích lũy trên thread stack. Giảm `-Xss` làm giảm ngân sách stack per platform thread trong nhiều tình huống, nên **có thể làm `StackOverflowError` xuất hiện ở độ sâu nhỏ hơn**.

Ví dụ:

~~~text
-Xss256k → ít không gian stack mỗi platform thread
-Xss512k → mức ở giữa
-Xss1m   → ngân sách stack lớn hơn

Không có hệ số cố định để biến giá trị này thành số method frames.
~~~

Kích thước một frame phụ thuộc Java bytecode, JVM interpreter vs JIT compiled code, inlining, locals, native transitions, architecture, debug flags và các optimizations. Cùng mã có thể tạo **độ sâu tối đa khác nhau** giữa JDK 17 và JDK mới, hoặc giữa cold và warm JIT state.

### Stack overflow khác out-of-memory do tạo thread

| Hiện tượng | Dấu hiệu | Hướng điều tra |
| --- | --- | --- |
| `StackOverflowError` | Call chain quá sâu/recursive bug; thêm stack frame thất bại | Stack trace, recursion/base condition, per-thread stack config |
| `OutOfMemoryError: Java heap space` | Cấp phát Java object thất bại | Heap live set, `-Xmx`, GC, allocations/retention |
| `OutOfMemoryError: Metaspace` | Class metadata/metaspace không đủ | Classloaders, generated classes, metaspace cap |
| `OutOfMemoryError: unable to create native thread` | JVM/OS không tạo được OS thread mới | Native memory, OS thread/PID quota, `pids.max`, `ulimit`, thread leaks |
| Container `OOMKilled` | Kernel/cgroup giết process; có thể không có Java exception | cgroup memory.current/events, RSS/anonymous/file charges |
| Direct buffer allocation failure | Native/direct buffer memory budget/cap hoặc pressure | Buffer pool/JNI/MaxDirectMemorySize/OS counters |

`unable to create native thread` **không nhất thiết chỉ do hết RAM**: OS có thể chặn vì **per-user process/thread limit, cgroup pids controller, global threads-max, security controls** hoặc resource reservation, ngay cả khi heap còn nhiều.

## 5. Java 17 runnable: giới hạn stack và recursion

Tạo file **`StackDepthDemo.java`**:

~~~java
public final class StackDepthDemo {
    private static volatile int depthReached;

    static void dive(int depth) {
        depthReached = depth;
        dive(depth + 1);
    }

    public static void main(String[] args) {
        try {
            dive(1);
        } catch (StackOverflowError expected) {
            System.out.println("caughtStackOverflow=true");
            System.out.println("depthPositive=" + (depthReached > 0));
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 StackDepthDemo.java
java -Xss256k StackDepthDemo
java -Xss1m StackDepthDemo
~~~

**Stdout đã biên dịch/chạy kiểm chứng trên JDK 24 Windows cho cả hai cấu hình:**

~~~text
caughtStackOverflow=true
depthPositive=true
~~~

Chương trình không in độ sâu cụ thể vì nó phụ thuộc VM build, platform, JIT state và stack frames. Field `volatile` lưu mức sâu đã chạm, nhưng thử nghiệm này **không** phải công cụ đo stack byte usage chính xác.

**Chỉ chạy kiểu lab có kiểm soát**, không bắt `StackOverflowError` rồi tiếp tục phục vụ production request như một phương án xử lý ổn định. Stack còn lại ở thời điểm lỗi có thể rất ít; xử lý/ghi log sâu hoặc tạo recursive error handler có thể lại gặp lỗi.

### Tại sao không khuyên tăng `-Xss` vô hạn?

Nếu method có recursive bug không có base case, tăng `-Xss` chỉ trì hoãn lỗi, tốn address space và có thể làm suy giảm khả năng tạo nhiều platform threads. Tối ưu thường là **sửa recursion** hoặc chuyển sang iteration/explicit work stack khi phù hợp. Tăng stack size nên dựa trên **độ sâu hợp lệ được kiểm thử** và ngân sách native memory thực.

## 6. Số platform threads tác động thế nào đến native memory?

Một mô hình **ước lượng đơn giản**:

\[
S_{\text{reserved, approx}} \approx N_{\text{platform}} \times S_{\text{per-thread nominal}}
\]

Trong đó `N_platform` là tổng platform/native threads tương ứng **không chỉ worker threads của ứng dụng**; `S_per-thread nominal` có thể khác cho JVM runtime/GC/compiler threads, main thread hoặc threads do native library tạo.

Đây **không phải phương trình chính xác cho RSS hoặc NMT Thread committed**. Đối với headroom, có thể lập một upper-bound style budget sử dụng số threads tối đa dự kiến nhân với stack size, cộng thêm các overhead, nhưng phải **đo lại** vì mỗi OS có reservation/commit khác nhau.

### Ví dụ tính tay mang tính minh họa

Một ứng dụng có **400 platform workers**, mỗi worker đặt nominal `-Xss512k`:

- Phần nominal workers stacks: `400 × 512 KiB = 204.800 KiB = 200 MiB` **quy mô vùng stack cấu hình**.
- Nếu thay bằng `-Xss1m`, phần nominal là `400 MiB`.
- Chênh nominal khoảng `200 MiB`, có thể quan trọng cho **virtual address reservations**, OS thread creation và committed memory headroom trong tình huống stack usage cao.
- **Không** tuyên bố 400 workers đang chờ chiếm đúng 200 MiB RSS; không tính được RSS chỉ bằng phép nhân này.

Ngoài 400 workers còn có main thread, ForkJoinPool workers, HTTP/JDBC pool/platform scheduler threads, GC workers, JIT compiler threads, JVM service threads và JNI threads. Số lượng OS threads cần đo từ tiến trình thật.

### Pool sizing trước stack tuning

Trong nhiều backend, thay vì giảm `-Xss` quá thấp để chứa 5.000 workers, cần hỏi:

- Tại sao phải có **5.000 platform threads**? Có thread leak hoặc unbounded pool không?
- Công việc chủ yếu chờ I/O hay chạy CPU?
- Downstream DB chỉ cho 50 connections hay có capacity lớn hơn?
- Có thể dùng bounded executor/queue, backpressure hoặc asynchronous APIs không?
- Nếu ứng dụng nâng lên Java 21+, virtual threads có hữu ích không, và giới hạn heap/DB còn đủ không?

`-Xss` là một phần của bài toán, không phải phép màu làm native threads không tốn memory.

## 7. Java 17 runnable: giữ tám platform threads đồng thời

Tạo file **`ThreadStackBudgetDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public final class ThreadStackBudgetDemo {
    public static void main(String[] args) throws Exception {
        int workers = 8;
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> threads = new ArrayList<>();

        for (int i = 0; i < workers; i++) {
            Thread t = new Thread(() -> {
                ready.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }, "budget-worker-" + i);
            t.start();
            threads.add(t);
        }

        ready.await();
        System.out.println("workersReady=" + workers);

        long pauseMs = Long.getLong("demo.pauseMs", 0L);
        if (pauseMs > 0) {
            System.out.println("inspectionWindowMs=" + pauseMs);
            Thread.sleep(pauseMs);
        }

        release.countDown();
        for (Thread t : threads) t.join();
        System.out.println("workersJoined=" + threads.size());
        System.out.println("allTerminated=" +
                threads.stream().noneMatch(Thread::isAlive));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 ThreadStackBudgetDemo.java
java -Xss512k ThreadStackBudgetDemo
~~~

**Stdout chính xác của chạy mặc định không đặt `demo.pauseMs`:**

~~~text
workersReady=8
workersJoined=8
allTerminated=true
~~~

Tám `new Thread` là **platform threads** trên Java 17; tất cả tới `CountDownLatch.await()` rồi chờ main giải phóng. Chương trình không cố tình tạo hàng nghìn threads và không có vòng lặp vô hạn.

`CountDownLatch` làm mốc kiểm chứng rõ ràng: `workersReady=8` bảo đảm cả tám đã chạy tới điểm chờ trước khi main tiếp tục. Nó không chứng minh số OS threads của toàn JVM là tám.

### Tạo cửa sổ để đo NMT/OS cùng một JVM

~~~bash
java -Xss512k -Xms64m -Xmx128m \
  -XX:NativeMemoryTracking=summary \
  -Ddemo.pauseMs=10000 ThreadStackBudgetDemo
~~~

Trên PowerShell:

~~~powershell
java -Xss512k -Xms64m -Xmx128m -XX:NativeMemoryTracking=summary -Ddemo.pauseMs=10000 ThreadStackBudgetDemo
~~~

Trong 10 giây sau `workersReady=8`, ở terminal khác tìm **PID thật** rồi lấy snapshot:

~~~text
jcmd
jcmd PID VM.native_memory summary scale=KB
jcmd PID Thread.print
jcmd PID VM.flags
~~~

`PID` là ký hiệu cần thay bằng process ID thật. `Thread.print` có thể in stacks/metadata của Java/platform threads, phù hợp Java 17; xem chính sách bảo mật khi lưu thread dump. NMT phải **bật từ lúc JVM startup** mới hoạt động.

### Kết quả đo thực tế của một lần chạy

Trên **JDK 24 Windows**, target source Java 17, process bật `-Xss512k -Xms64m -Xmx128m` và tạo tám workers đang chờ, một lần chụp cho:

~~~text
NMT Total: reserved=1607709KB, committed=169577KB
NMT Java Heap: reserved=131072KB, committed=67584KB
NMT Thread: reserved=17997KB, committed=1333KB
NMT stack: reserved=17920KB, committed=1256KB
OS native thread count: 30
OS WorkingSet64: 40738816 bytes
~~~

Số liệu trên đã được thu từ **một tiến trình đang chạy** bằng `jcmd` và Windows `Get-Process`, không phải output stdout của Java. Trong chính tiến trình ấy, nguồn Java in `workersReady=8`, `inspectionWindowMs=5000`, sau đó `workersJoined=8`, `allTerminated=true`.

**Cách đọc:**

1. OS có **30 native threads**, bao gồm tám app workers **và** JVM/JIT/GC/runtime/native threads.
2. NMT `Thread reserved 17997 KiB` không bằng `8 × 512 KiB` vì JVM còn threads khác, rounding và stack/VM structures.
3. Stack `reserved 17920 KiB` lớn hơn rất nhiều stack `committed 1256 KiB`: **không dùng reserved làm resident RAM**.
4. NMT `Total committed 169577 KiB` **bao gồm Java Heap committed**, không cộng thêm 67584 KiB.
5. Windows Working Set 40.738.816 bytes phản ánh process resident pages tại snapshot, **không phải** NMT committed.
6. Số đo là **một run/JDK/OS cụ thể**, không dự đoán stack usage trên Linux hay Java 17 runtime chính xác.

Điểm học tập là **nguồn đo và phạm vi**, không phải tuyên bố “mỗi worker luôn cần 512 KiB committed” hoặc “HotSpot luôn có đúng 30 native threads”.

## 8. Native memory ngoài stack: không được bỏ sót phần nào?

Để cấu hình tài nguyên cho server, cần dành ngân sách cho các vùng khác `Java Heap`:

| Thành phần | Cách chịu ảnh hưởng | Công cụ quan sát |
| --- | --- | --- |
| **Metaspace / class metadata** | Số classes, classloaders, dynamic proxies, class generation | NMT `Class`, JMX memory pools |
| **Compressed class space** | Reserved address space lớn có thể commit nhỏ | NMT `Class` reserved/committed |
| **JIT code cache** | Native compiled code, compiler tiers, warm-up | NMT `Code`, `jcmd Compiler.codecache` nếu hỗ trợ |
| **GC structures** | Collector, heap region sizes, remembered sets, concurrency | NMT `GC`, GC logs |
| **Native thread stacks** | Platform thread count, configured stack sizes, call depth | NMT `Thread` stack reserved/committed, OS thread count |
| **DirectByteBuffer / NIO** | Direct buffer allocations và lifetimes | `BufferPoolMXBean`, OS/native tools |
| **JNI/JNA/native libs** | `malloc`, native caches, 3rd-party clients | OS/native allocation profilers; NMT có thể bỏ sót |
| **Mapped files, shared libs** | File mappings và physical residency | Linux `/proc/PID/smaps_rollup`, PSS; Windows process counters |
| **JVM internal/runtime** | Symbol tables, compiler arenas, service allocations | NMT categories theo JDK |
| **OS/container memory charges** | File cache, kernel memory, sidecars/child processes | cgroup `memory.stat`, `memory.current` |

**NMT không phải toàn bộ native memory của mọi thư viện**. Oracle JDK 17 ghi rõ NMT chủ yếu theo dõi HotSpot VM internal allocations, không bao quát đủ third-party native memory. Vì vậy heap + NMT vẫn không nhất thiết mô tả toàn bộ RSS/cgroup usage.

### Cấu hình giới hạn vài vùng riêng

~~~bash
java -Xms256m -Xmx512m \
  -Xss512k \
  -XX:MaxDirectMemorySize=128m \
  -XX:MaxMetaspaceSize=128m \
  -XX:ReservedCodeCacheSize=64m \
  -jar service.jar
~~~

Các giá trị **chỉ là ví dụ có chủ đích**, không phải “bộ flags tốt nhất”. `service.jar` phải là application artifact thật. Chú ý:

- `MaxDirectMemorySize` giới hạn một phần cơ chế direct-buffer allocation của JVM; **không** giới hạn mọi JNI/native malloc.
- `MaxMetaspaceSize` có thể gây `OutOfMemoryError: Metaspace` nếu quá thấp; không biến mọi memory class loading thành một cap RSS hoàn hảo.
- `ReservedCodeCacheSize` giới hạn code cache capacity theo VM, có thể ảnh hưởng compiled code/JIT nếu thiếu; **không phải toàn bộ compiler native memory**.
- `-Xmx`/`-Xss` không kiểm soát OS page cache hay toàn bộ thread/process resources.
- Các maximums này không bảo đảm từng subsystem **dùng hết** giá trị đó; đồng thời có overhead khác **ngoài các maximums**.

**Phương pháp tốt hơn:** đặt budgets trên giấy, đo NMT/OS thật với cùng workload, rồi điều chỉnh có tính đến headroom.

## 9. Ngân sách bộ nhớ: cách tính sơ bộ để tránh OOM

Giả sử container có **1 GiB = 1.024 MiB memory limit**, chạy một JVM chính. Một bản phân bổ **minh họa cho thí nghiệm**, không phải số đo thực:

| Nhóm ngân sách | Số MiB giả định | Ý nghĩa |
| --- | ---: | --- |
| Java heap maximum | 512 | `-Xmx512m` |
| Direct-buffer allowance | 128 | NIO pool cap ví dụ, không cover all JNI |
| Metaspace allowance | 128 | Cấp cho classes/metadata theo VM |
| Code cache allowance | 64 | Dự phòng compiled code |
| 100 platform stacks nominal × 512 KiB | 50 | **Quy mô reservation**, không phải resident RAM cố định |
| GC/VM/JNI/runtime/OS headroom khác | 80 | Dự phòng tổng hợp có tính phỏng đoán |
| **Tổng budget kiểu bảo thủ** | **962** | Tổng giả định, **không phải RSS đo được** |
| **Phần còn lại dưới 1.024 MiB** | **62** | Headroom theo bảng giả định |

**Diễn giải quan trọng:**

- `100 × 512 KiB = 50 MiB` là **nominal stack-space budget**, không tự là 50 MiB RSS.
- Các allowance **có thể chồng lắp khi lấy số thực từ NMT/JMX**; bảng này là **kế hoạch upper-bound style theo nhóm tài nguyên** đã định nghĩa riêng, không phải phép cộng những counters từ công cụ.
- 62 MiB headroom như ví dụ có thể **quá mỏng** khi app có nhiều JNI libs, sidecars, peak memory hoặc một phần budget bị sai. Phải đo thêm peak, steady, startup spike, OS/cgroup file cache và sai số.
- Nếu bạn đặt `Xmx=900 MiB` trong 1 GiB limit, khả năng OOMKilled rất đáng lo ngay cả khi heap trung bình thấp.
- **Không sử dụng bảng để dự đoán chính xác số thread tối đa**. Hãy thu native thread count, NMT Thread reserved/committed, RSS và container memory theo tải thật.

### Công thức cho headroom mang tính mô hình

Có thể viết một phép lập ngân sách (không phải đẳng thức đo đạc):

\[
B_{\text{available}} = L_{\text{container}} - H_{\text{planned}} - N_{\text{planned}} - O_{\text{headroom}}
\]

Trong đó `H_planned` là allowance heap, `N_planned` là các allowance **ngoài heap không chồng lắp theo định nghĩa của bản kế hoạch**, và `O_headroom` dự phòng hệ điều hành, runtime/third-party allocations và peaks. Nếu các allowance được lấy từ NMT `Total` vốn **đã chứa Java Heap**, phải **không** cộng heap lại.

Để quyết định chạy production, **đối chiếu bảng với peak `memory.current`/`memory.peak`, RSS/PSS và NMT** chứ không chỉ nhìn các giới hạn cấu hình.

## 10. Giới hạn số luồng có thể đến từ đâu?

Số lượng platform threads không được quyết định bởi một `MaxThreads` flag portable duy nhất trong Java 17. Những nguồn giới hạn thường gặp:

1. **OS/process/thread quota**: mỗi OS thread là một scheduling entity cần tài nguyên kernel.
2. **Linux per-user limit** (`ulimit -u` và thực tế RLIMIT_NPROC tùy quyền/user namespaces).
3. **Linux system-wide** thread/pid limits (`/proc/sys/kernel/threads-max`, `pid_max`, và các giới hạn khác).
4. **Cgroup pids controller** (`pids.max`, `pids.current`, `pids.events`), giới hạn tasks/PIDs trong cgroup.
5. **Native address space / memory commit**: nhiều stacks/reservations và thread resources có thể thất bại dù heap còn trống.
6. **CPU/scheduler overhead**: lượng threads runnable quá lớn khiến context-switching/lock contention làm latency kém.
7. **Native library/runtime constraints**, ví dụ JNI clients hoặc internal pool sizes.

Các giới hạn OS thay đổi theo Linux/Windows, container orchestration, architecture và bảo mật. `ulimit -u` **không nhất thiết là limit hữu hiệu duy nhất**; cgroup PID controller cũng có thể chặn trước.

### Cgroup PID khác container memory

Một container có `memory.current` thấp nhưng `pids.current` đã sát `pids.max` có thể **không tạo được native thread mới**, dù vẫn còn RAM. Ngược lại, `pids.max` rất lớn không bảo đảm memory đủ cho mọi thread stack.

Chẩn đoán phân biệt:

~~~bash
cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
cat /sys/fs/cgroup/pids.events
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
~~~

Đường dẫn là ví dụ với **cgroup v2 được mount tại đó**; với cgroup v1 hoặc container mount namespace khác phải xác định cgroup thực tế. `pids.max` có thể là `max` (không có hard limit theo cơ chế ấy). `pids.current` đếm các tasks trong cgroup theo kernel rules, không phải đếm Java application worker threads.

Không nhầm limit container CPU với limit native thread count: **CPU quota thấp** làm nhiều runnable threads tranh CPU, nhưng không trực tiếp định nghĩa số PIDs tối đa.

## 11. Quan sát trên Linux và Windows

### 11.1. Linux: thread count + process memory

~~~bash
ps -o pid,nlwp,rss,vsz,comm -p PID
ps -L -p PID -o pid,lwp,stat,comm
cat /proc/PID/status
cat /proc/PID/smaps_rollup
~~~

Trong các lệnh trên, thay **PID** bằng process ID thật.

- `NLWP`: OS lightweight threads của process ở thời điểm đo; **không chỉ tám workers**.
- `ps -L`: liệt kê native/lightweight threads.
- `VmRSS`/`Rss`: resident footprint theo OS.
- `VmSize`/`VSZ`: process address space mappings/reservations.
- `smaps_rollup`: RSS/PSS/private/shared memory breakdown, tùy kernel/quyền.
- Không lấy RSS trừ heap used rồi gọi phần chênh là “thread stacks”; còn nhiều nguồn native khác.

### 11.2. Windows PowerShell

~~~powershell
Get-Process -Id 12345 |
    Select-Object Id,
        @{Name='NativeThreads';Expression={$_.Threads.Count}},
        WorkingSet64, PrivateMemorySize64, VirtualMemorySize64
~~~

`12345` chỉ là **PID ví dụ**, phải thay số đúng process. Windows `WorkingSet64`, `PrivateMemorySize64` và `VirtualMemorySize64` có nghĩa khác nhau. Không coi `VirtualMemorySize64` là RAM resident và không lấy `PrivateMemorySize64` làm synonym RSS Linux.

### 11.3. JDK/HotSpot tools

~~~text
jcmd
jcmd PID Thread.print
jcmd PID VM.native_memory summary scale=KB
jcmd PID VM.flags
jcmd PID GC.heap_info
~~~

Tất cả lệnh dùng **PID thật** trên cùng OS/container PID namespace và cần quyền attach. Các lệnh `jcmd PID ...` là **shell instructions** sau khi thay PID, không phải cú pháp Java source.

`Thread.print` hiển thị JVM-recognized Java/native thread stacks; dùng để phát hiện threads đang WAITING/BLOCKED/RUNNABLE, pool growth và số tên threads lặp. Tuy nhiên thread dump là một **snapshot trạng thái**, không đo RSS của từng stack.

### 11.4. Java ThreadMXBean

Java 17 có `ManagementFactory.getThreadMXBean()` và `getThreadCount()`, `getPeakThreadCount()`, `getTotalStartedThreadCount()`:

- Cho bạn JVM-level metrics về live threads, peak live threads và cumulative started count.
- Không phải OS `NLWP` hoàn toàn chính xác 1:1 vì JVM còn service/native threads không được bean phơi ra theo cùng phạm vi.
- `getTotalStartedThreadCount()` **không phải** số threads đang sống: nó tích lũy số thread đã start kể từ JVM initialization.
- Trên Java 21+ với virtual threads, các legacy `ThreadMXBean` views không mặc nhiên tính đầy đủ VTs theo số Java tasks; cần virtual-thread-aware tools.

**Đối chiếu OS count với JVM thread counts**, thay vì đòi chúng bằng nhau.

## 12. NMT: reserved/committed và stack line

Native Memory Tracking của HotSpot có thể bật từ startup:

~~~bash
java -XX:NativeMemoryTracking=summary \
  -Xss512k -Xms64m -Xmx128m ThreadStackBudgetDemo
~~~

Với process còn sống, in `jcmd PID VM.native_memory summary scale=KB`. Một phần output thường có cấu trúc:

~~~text
- Thread (reserved=..., committed=...)
    (thread #...)
    (stack: reserved=..., committed=...)
    (malloc=... #...)
    (arena=... #...)
~~~

**Các số là placeholders mô tả format NMT**, không phải output thực của một JVM cụ thể. `Thread` category có thể bao gồm cấu trúc thread data, stacks, arenas và metadata. “Thread stack reserved” và “Thread stack committed” không đồng nghĩa.

### NMT total đã bao gồm Java Heap

Ví dụ NMT:

~~~text
Total: reserved=..., committed=...
- Java Heap (reserved=..., committed=...)
- Thread (reserved=..., committed=...)
- Class (reserved=..., committed=...)
- Code (reserved=..., committed=...)
- GC (reserved=..., committed=...)
~~~

**Không tính** `Total committed + Java Heap committed` là process memory: heap **đã nằm trong NMT total**.

NMT **không** theo dõi mọi memory do JNI/third-party native library cấp phát, và reserved/committed khác OS RSS. Đối chiếu NMT với OS mappings là cần thiết nếu nghi native leak.

### Baseline/diff khi pool threads tăng

Có thể lấy baseline sau khi app ready:

~~~text
jcmd PID VM.native_memory baseline
jcmd PID VM.native_memory summary.diff scale=KB
~~~

Khi tăng pool size dưới workload có kiểm soát, xem liệu category `Thread` tăng và có bao nhiêu native threads/stack reservations. Nhưng nếu còn GC/compiler/class loading thay đổi, một delta NMT không cô lập chỉ thread stacks. Cần **OS thread count, app thread metric, named thread dumps và workload timeline**.

## 13. Thực nghiệm an toàn để đo tác động của `-Xss`

Thay vì cố “tạo thread cho đến khi JVM chết”, dùng lab **một lượng workers nhỏ, cố định**:

1. Chọn 2 cấu hình `-Xss512k` và `-Xss1m` cùng JDK/OS.
2. Giữ `Xms/Xmx`, collector, app binary, số workers (=8 trong ví dụ) và workload giống nhau.
3. Bật NMT summary **cho cả hai runs**, không bật một run/tắt run kia.
4. Mỗi run khởi động JVM process mới và giữ `demo.pauseMs` giống nhau.
5. Chụp NMT `Thread reserved/committed`, OS native thread count, RSS/Working Set và process VSZ.
6. Lặp vài lần; tránh dùng một run duy nhất để kết luận exact bytes.
7. Kết hợp với `StackDepthDemo` cho thấy ảnh hưởng stack limit lên call depth, nhưng không gán một phép đổi tuyến tính sâu=stack size.
8. Chỉ dùng các kết quả đo sau khi đã kiểm tra PID/time/OS/JDK flags.

**Cố tình spawn hàng trăm nghìn platform threads tới khi OS từ chối là thí nghiệm nguy hiểm** trên máy đang chạy dịch vụ; không thực hiện trên shared/dev host. Dùng limits thấp trong isolated test environment và giới hạn workers.

### Vì sao không dùng `-Xss` để giảm heap?

Giảm stack size chỉ thay một phần **native/OS thread stack budget**. Nó không thu nhỏ Java heap object retention, direct-buffer allocations, metaspace, code cache hay memory cgroup của sidecars. Cần xác định **nút thắt thật** trước khi thay flag.

## 14. Nhiều câu trả lời sai khi tuning thread stack

### 14.1. “Nếu container 1 GiB, cứ đặt `-Xmx1g`”

Sai: toàn tiến trình còn non-heap/native memory, stack, GC/code cache, file mappings; có thể OOMKilled. Nên dành **đủ headroom đã đo**, không dùng gần 100% memory limit chỉ cho heap max.

### 14.2. “Nếu heap còn 50%, JVM không thể tạo thread vì heap”

Không đủ: native threads bị giới hạn bởi OS memory/address space/PID quotas, không phải chỉ heap free. Thậm chí giảm `-Xmx` không bảo đảm giải được limit `pids.max`.

### 14.3. “`-Xss512k` nghĩa mỗi platform thread đang dùng đúng 512 KiB RAM”

Sai: đó là cấu hình stack size, không phải giá trị RSS từng thread. Xem NMT reserved/committed và OS resident metrics riêng.

### 14.4. “`-Xss` càng nhỏ càng tốt vì có thể tạo thêm workers”

Sai: một số call chains hợp lệ, recursion, frameworks và native transitions có thể cần stack sâu. Cấu hình quá nhỏ có thể bị VM từ chối hoặc gây `StackOverflowError`.

### 14.5. “`-Xss` càng lớn thì method Java chạy nhanh hơn”

Sai: tăng stack capacity không mặc nhiên cải thiện throughput. Nó có thể tăng memory reservations và làm giảm số native threads khả thi. Đo hiệu năng/stack depth thật.

### 14.6. “`-Xss` = số thread tối đa”

Sai: không có phép tính chính xác nếu không biết OS quotas, native memory committed/resident, process limits, JVM service threads và memory headroom.

### 14.7. “`-XX:MaxDirectMemorySize` cap mọi native allocation”

Sai: chỉ một phần cơ chế direct buffer được hỗ trợ; JNI libraries có thể có native allocations ngoài nó.

### 14.8. “Nếu NMT Thread reserved 20 MiB thì process RSS tăng đúng 20 MiB”

Sai: reservation không phải memory resident. Ngược lại, native allocations khác không được tracking có thể làm RSS tăng mà category Thread không đổi.

### 14.9. “Mọi thread trong JVM đều do application thread pool tạo”

Sai: còn JVM runtime, compiler, GC, management và native library threads. OS thread count thường lớn hơn số workers do app tạo.

### 14.10. “Virtual threads Java 21 dùng `-Xss` native stack riêng mỗi task”

Sai: virtual threads có stack chunks/continuation trên heap và được mounted lên carriers; không dùng native stack per VT suốt lifetime.

### 14.11. “Cgroup memory OOM và pids OOM là một”

Sai: memory controller và pids controller có counters/events/limits khác. Cần xem riêng.

### 14.12. “`ThreadMXBean.getTotalStartedThreadCount()` bằng current live threads”

Sai: cumulative started count khác live count. So nhiều metrics để phát hiện churn/leaks.

## 15. Checklist trước khi chỉnh `-Xss` hay số worker threads

- [ ] Xác định JVM vendor/version/build, OS/architecture, collector và cgroup/container.
- [ ] Ghi effective `-Xss`, `-Xms`, `-Xmx`, metaspace/direct/code cache flags.
- [ ] Xác định platform threads vs virtual threads (nếu Java 21+).
- [ ] Đo OS native thread count, peak thread count, Java thread names/pools.
- [ ] Kiểm tra thread leak, unbounded executor, blocking I/O và backpressure.
- [ ] Kiểm tra thread stack depth hợp lệ và các trường hợp recursion/large call chains.
- [ ] Không giảm stack dưới mức VM/platform chấp nhận.
- [ ] Đo NMT Thread reserved **và** committed, không nhầm với RSS.
- [ ] Đo process RSS/PSS/Working Set cùng timestamp và PID.
- [ ] Đo container memory.current/peak/stat/events và pids.current/max/events.
- [ ] Kiểm tra metaspace, GC, code cache, direct buffers và JNI native memory.
- [ ] Dành headroom cho startup spikes, peak workloads và shared/kernel charges.
- [ ] Ghi errors cụ thể: StackOverflowError, unable to create native thread, heap/metaspace OOME, cgroup OOMKilled.
- [ ] Test dưới CPU quota giống production; nhiều runnable threads vẫn có scheduler cost.
- [ ] Chạy thử nhiều lần, đánh giá p99/p99.9 latency/throughput và error rate.
- [ ] Không stress tới exhaustion trên production/shared host.
- [ ] Sau khi tuning, kiểm tra lại chất lượng dịch vụ và khả năng phục hồi.

## 16. Câu hỏi tự kiểm tra và đáp án

1. `-Xss` cấu hình gì? **Thread stack size**, theo VM/OS có rounding/giới hạn.
2. `-Xmx512m` có giới hạn toàn bộ RSS dưới 512 MiB không? **Không**.
3. 100 workers nominal `-Xss512k` có quy mô stack cấu hình bao nhiêu? **50 MiB**, không phải 50 MiB resident chắc chắn.
4. JVM có tám workers thì OS chỉ có tám threads? **Không**, còn VM/GC/JIT/service threads.
5. NMT Thread reserved = NMT Thread committed? **Không**.
6. NMT Thread reserved 18 MiB có phải 18 MiB RAM vật lý đã resident? **Không**.
7. `-Xss256k` có thể gây StackOverflowError sớm hơn `-Xss1m` không? **Có**, tùy call frames/JIT/VM.
8. StackOverflowError có đồng nghĩa heap OOME? **Không**.
9. `unable to create native thread` chỉ do hết RAM? **Không**, còn OS/cgroup PID/thread limits.
10. `pids.max` có phải `memory.max` không? **Không**, là hai bộ controller/limits khác.
11. `ThreadMXBean.getTotalStartedThreadCount()` có phải current live threads? **Không**.
12. `-XX:MaxDirectMemorySize` giới hạn mọi JNI malloc? **Không**.
13. NMT total có chứa Java Heap? **Có**; không cộng heap thêm lần nữa.
14. NMT có thấy hoàn toàn third-party native allocations? **Không**.
15. Cgroup memory.current có bằng RSS JVM? **Không nhất thiết**, cgroup có cache/kernel/other processes.
16. `-XX:ThreadStackSize=512` có nghĩa 512 bytes? **Không**, HotSpot flag cơ bản dùng KiB.
17. Virtual threads có một native stack riêng cố định mỗi VT? **Không**.
18. Một triệu virtual threads có nghĩa không tốn memory? **Sai**, có objects, stack chunks, locals và payloads.
19. Giảm worker pool có thể giảm native stack budget không? **Có** nếu giảm số platform threads sống.
20. Một thread đang WAITING có tự giải phóng native stack như thread đã exit? **Không** theo mô hình platform threads.
21. NMT summary.diff tăng có tự chứng minh thread leak? **Không**, cần tương quan số threads/pool/workload.
22. Có nên tạo threads tới khi process crash trên máy chung? **Không**.
23. Nên xem cả reserved và committed khi đọc NMT? **Có**.
24. Quyết định `-Xss` nên dựa trên gì? **Độ sâu call stack hợp lệ, giới hạn OS, native memory, thread count và phép đo**.

## 17. Nguồn tài liệu chính thống

- Oracle Java SE 17, **`java` command**, `-Xss`, `-XX:ThreadStackSize`, `-Xms`, `-Xmx`, direct/memory flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17, **Native Memory Tracking**: https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html
- Oracle JDK 17, **Diagnostic Tools / NMT categories**: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- Oracle JDK 17, **`jcmd`**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Java SE 17, **`Thread`** constructor and platform-thread lifecycle: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17, **`ThreadMXBean`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Java SE 17, **`MemoryMXBean`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
- Java Virtual Machine Specification 17, **JVM Stacks (§2.5.2)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.2
- Oracle Java SE 21, **Virtual Threads** (khác biệt carrier native stacks): https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- Linux kernel, **cgroup v2 pids controller**: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#pid
- Linux kernel, **cgroup v2 memory controller**: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html#memory

**Kết luận:** `-Xss` kiểm soát **ngân sách stack của một platform thread**, còn số platform threads quyết định tổng quy mô stack reservations; cả hai phải được xem cùng heap, metaspace, code cache, direct/native allocations và giới hạn OS/container. **Reserved, committed và RSS là ba đại lượng khác nhau**. Khi gặp StackOverflowError, kiểm tra call depth; khi không tạo được native thread, xem cả native memory lẫn PID/thread quotas; khi bị OOMKilled, xem cgroup/RSS và memory ngoài heap. Tối ưu đáng tin dùng **NMT + OS thread counts + JMX/GC + cgroup counters** dưới workload thật, không suy từ mỗi `Xmx` hoặc `N × Xss`.
