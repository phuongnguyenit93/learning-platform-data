# So sánh mức dùng CPU, heap, native memory và số thread hệ điều hành

Khi đánh giá một ứng dụng Java 21, cần quan sát đồng thời CPU, Java heap, native memory và số thread hệ điều hành. Bốn nhóm số liệu này phản ánh các phần khác nhau của tiến trình. CPU cho biết mức tiêu thụ năng lực xử lý; heap cho biết bộ nhớ dành cho object Java; native memory cho biết các vùng cấp phát ngoài heap, còn RSS phản ánh các trang bộ nhớ resident của toàn tiến trình, bao gồm cả heap lẫn native; số OS thread cho biết số kernel thread mà tiến trình đang giữ.

Đặc biệt, ứng dụng dùng virtual thread có thể có hàng chục nghìn thread Java nhưng chỉ dùng một số lượng platform thread nhỏ hơn nhiều. Vì vậy, không được lấy số virtual thread làm số OS thread, cũng không được dùng riêng ThreadMXBean để kết luận tổng số thread Java đang tồn tại.

## 1. Phân biệt bốn nhóm số liệu

| Nhóm | Đang đo điều gì? | Nguồn đo thường dùng |
|---|---|---|
| CPU | CPU time hoặc tỷ lệ CPU của JVM process và toàn máy | OperatingSystemMXBean, JFR, OS tools |
| Java heap | Object memory đang dùng, đã commit và giới hạn tối đa | MemoryMXBean, GC logs, jcmd |
| Native/off-heap memory | Bộ nhớ JVM cấp phát ngoài Java heap, direct buffers và native allocations | NMT, BufferPoolMXBean, OS RSS/PSS |
| OS thread | Số kernel thread của tiến trình, gồm application và JVM internal threads | OS tools, process explorer |

Không cộng hoặc so sánh các con số mà chưa hiểu phạm vi. Ví dụ, heap committed không đồng nghĩa RSS; NMT committed không bao phủ mọi native allocation; ThreadMXBean không đếm virtual thread.

## 2. Đo CPU của JVM process và CPU toàn hệ thống

CPU có thể được biểu diễn bằng CPU time tích lũy hoặc CPU load trong một khoảng thời gian:

- **Process CPU time** là tổng thời gian CPU mà các thread của JVM đã sử dụng.
- **Process CPU load** là mức CPU gần đây của riêng JVM process.
- **System CPU load** là mức CPU gần đây của toàn môi trường hệ điều hành.

Trong Java 21, có thể dùng **com.sun.management.OperatingSystemMXBean** để đọc CPU của process:

~~~java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;

class ProcessCpuSnapshot {
    public static void main(String[] args) {
        java.lang.management.OperatingSystemMXBean base =
                ManagementFactory.getOperatingSystemMXBean();

        if (!(base instanceof OperatingSystemMXBean os)) {
            System.out.println("Process CPU metrics are unavailable");
            return;
        }

        System.out.println("availableProcessors = "
                + os.getAvailableProcessors());
        System.out.println("processCpuLoad = "
                + os.getProcessCpuLoad());
        System.out.println("processCpuTimeNs = "
                + os.getProcessCpuTime());
        System.out.println("systemCpuLoad = "
                + os.getCpuLoad());
    }
}
~~~

Các phương thức load trả về giá trị trong khoảng 0.0 đến 1.0; giá trị âm nghĩa là không có dữ liệu. Process CPU load bằng 1.0 nghĩa là JVM đang sử dụng toàn bộ năng lực CPU khả dụng trong khoảng quan sát. Giá trị này đã chuẩn hóa theo năng lực CPU của môi trường, nên không nhất thiết giống cách một công cụ hệ điều hành hiển thị phần trăm theo từng core.

**getProcessCpuTime()** trả về CPU time tích lũy tính bằng nanosecond. Có thể lấy hai mẫu cách nhau một khoảng để tính tỷ lệ:

~~~java
import com.sun.management.OperatingSystemMXBean;
import java.lang.management.ManagementFactory;

class ProcessCpuInterval {
    public static void main(String[] args) throws InterruptedException {
        java.lang.management.OperatingSystemMXBean base =
                ManagementFactory.getOperatingSystemMXBean();
        if (!(base instanceof OperatingSystemMXBean os)) {
            System.out.println("Process CPU time is unavailable");
            return;
        }

        long cpuBefore = os.getProcessCpuTime();
        long wallBefore = System.nanoTime();
        Thread.sleep(1_000);
        long cpuAfter = os.getProcessCpuTime();
        long wallAfter = System.nanoTime();

        if (cpuBefore >= 0 && cpuAfter >= cpuBefore) {
            long elapsedCpu = cpuAfter - cpuBefore;
            long elapsedWall = wallAfter - wallBefore;
            double capacity =
                    (double) elapsedWall * os.getAvailableProcessors();
            double percentOfMachine = 100.0 * elapsedCpu / capacity;
            System.out.printf("Process CPU = %.1f%%%n", percentOfMachine);
        }
    }
}
~~~

Công thức trên biểu diễn phần trăm tổng năng lực CPU khả dụng. Nếu muốn biểu diễn mức dùng tương đương một core, không chia cho số processor. Hãy ghi rõ cách chuẩn hóa khi lưu dashboard để tránh so sánh hai metric có định nghĩa khác nhau.

Không chỉ nhìn process CPU. Nếu process CPU thấp nhưng system CPU cao, máy hoặc container host có thể đang bị workload khác cạnh tranh. Nếu process CPU cao, hãy kiểm tra hot methods, allocation, GC, serialization, lock contention và các tác vụ nền.

## 3. Đo Java heap: used, committed và max

Java heap là vùng nhớ chứa object và array được quản lý bởi garbage collector. Ba số liệu quan trọng:

- **Used**: dung lượng heap đang được sử dụng tại thời điểm lấy mẫu.
- **Committed**: dung lượng heap JVM đã bảo đảm có thể dùng.
- **Max**: giới hạn heap tối đa; có thể không xác định và được biểu diễn bằng -1.

Có thể đọc heap bằng **MemoryMXBean**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

class HeapSnapshot {
    public static void main(String[] args) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

        System.out.println("heapUsed = " + heap.getUsed());
        System.out.println("heapCommitted = " + heap.getCommitted());
        System.out.println("heapMax = " + heap.getMax());
    }
}
~~~

Các giá trị được trả về theo byte. Nên chuyển sang MiB hoặc GiB khi hiển thị, nhưng giữ byte trong dữ liệu gốc để tính toán chính xác.

Heap used có thể dao động mạnh trước và sau GC. Khi so sánh hai phiên bản ứng dụng, hãy ghi lại xu hướng theo thời gian và mức used sau các chu kỳ GC tương đương; không kết luận memory leak từ một lần chụp heap.

Có thể kiểm tra thông tin heap từ tiến trình đang chạy:

~~~bash
jcmd <pid> GC.heap_info
~~~

GC logs và JFR giúp giải thích vì sao heap tăng, GC chạy bao lâu và allocation rate thay đổi như thế nào. Heap dump có thể hữu ích khi điều tra retained objects, nhưng có chi phí cao và cần được tạo có chủ đích.

## 4. Đo non-heap memory và direct buffers

Non-heap memory của Java bao gồm các vùng như Metaspace và code cache. Đây là số liệu JVM quản lý, nhưng không đại diện cho toàn bộ native memory của tiến trình.

**MemoryMXBean.getNonHeapMemoryUsage()** cung cấp used, committed và max cho vùng non-heap mà JVM quản lý. Có thể dùng **MemoryPoolMXBean** để xem từng pool như Metaspace hoặc Code Cache.

Direct buffer là một nguồn off-heap đáng chú ý. **BufferPoolMXBean** cung cấp số buffer, tổng capacity và memory used cho các pool như direct và mapped:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

class BufferPoolSnapshot {
    public static void main(String[] args) {
        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            System.out.printf(
                    "%s: count=%d, capacity=%d, used=%d%n",
                    pool.getName(),
                    pool.getCount(),
                    pool.getTotalCapacity(),
                    pool.getMemoryUsed()
            );
        }
    }
}
~~~

BufferPoolMXBean giúp theo dõi direct/mapped buffers do các buffer pool được JVM expose. Nó không đo mọi native allocation của thư viện bên thứ ba hoặc mã JNI.

## 5. Dùng Native Memory Tracking để xem bộ nhớ nội bộ JVM

**Native Memory Tracking (NMT)** theo dõi các vùng bộ nhớ được HotSpot JVM quản lý và phân nhóm theo subsystem; báo cáo có thể gồm Java Heap cùng các vùng như Class, Thread, Code, GC và Internal. NMT tắt mặc định; phải bật lúc khởi động JVM:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Hai chế độ:

| Chế độ | Dữ liệu |
|---|---|
| summary | Tổng hợp theo subsystem như Java Heap, Class, Thread, Code, GC và Internal |
| detail | Thêm thông tin allocation theo call site và vùng virtual memory |

Sau khi tiến trình đã chạy, dùng jcmd:

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

Lệnh baseline lưu mốc hiện tại. Sau một khoảng chạy workload, summary.diff cho thấy subsystem nào tăng hoặc giảm so với mốc. Có thể dùng detail và detail.diff khi cần điều tra sâu hơn.

NMT phải được bật khi khởi động; không thể bật hoặc khởi động lại NMT bằng jcmd sau khi JVM đã chạy. NMT có overhead hiệu năng và bộ nhớ, tài liệu Oracle ước lượng khoảng 5–10%, vì vậy hãy cân nhắc mức độ chi tiết và môi trường đo.

**Giới hạn quan trọng:** NMT theo dõi allocation nội bộ HotSpot, không theo dõi đầy đủ native memory do JNI hoặc thư viện native bên thứ ba tự cấp phát. NMT cũng không thay thế công cụ hệ điều hành để xem RSS của tiến trình.

## 6. Đo RSS và bộ nhớ tiến trình ở hệ điều hành

**RSS (Resident Set Size)** là lượng trang bộ nhớ của tiến trình hiện đang nằm trong RAM. RSS có thể gồm heap, native memory, code, stack, thư viện dùng chung và các vùng memory-mapped.

RSS khác với:

- Heap used: object đang dùng trong Java heap.
- Heap committed: vùng heap JVM đã commit.
- NMT committed: vùng bộ nhớ HotSpot commit theo subsystem.
- Virtual size: tổng vùng địa chỉ ảo được map/reserve, không đồng nghĩa RAM thực đang dùng.

Trên Linux, có thể xem nhanh:

~~~bash
ps -o pid,rss,vsz,nlwp,comm -p <pid>
top -H -p <pid>
pidstat -p <pid> -u -r -t 1
grep -E 'VmRSS|VmSize|Threads' /proc/<pid>/status
cat /proc/<pid>/smaps_rollup
~~~

RSS và VSZ thường hiển thị theo KiB trong các công cụ này. **nlwp** là số lightweight process, tương ứng số kernel thread của process. smaps_rollup cung cấp thông tin chi tiết hơn về vùng memory map; PSS có thể giúp phân bổ trang dùng chung theo tỷ lệ thay vì cộng toàn bộ RSS của từng process.

Trên Windows, có thể kiểm tra working set, private memory và số thread bằng PowerShell:

~~~powershell
$process = Get-Process -Id <pid>
$process | Select-Object Id, CPU, WorkingSet64, PrivateMemorySize64
$process.Threads.Count
~~~

Trong PowerShell, thuộc tính CPU là tổng CPU time tích lũy tính bằng giây, không phải phần trăm CPU tức thời. Lấy hai mẫu theo thời gian để tính tốc độ tiêu thụ CPU. Task Manager, Process Explorer và Performance Monitor cũng có thể hiển thị CPU, working set, private bytes và thread count. Các bộ đếm có tên tương tự nhưng định nghĩa khác nhau; hãy ghi rõ đang dùng Working Set, Private Bytes hay Commit Size.

Trên macOS, có thể dùng Activity Monitor và các công cụ hệ thống như top hoặc vmmap để xem CPU, resident memory, thread và vùng memory map.

## 7. Phân biệt native memory với RSS

Không nên lấy RSS trừ heap used rồi kết luận phần còn lại là native memory chính xác. Các lý do:

- Heap committed có thể lớn hơn heap used.
- NMT reserved và committed là khái niệm quản lý vùng nhớ của JVM, không đồng nhất với số trang đang resident.
- RSS có thể bao gồm trang thư viện dùng chung, memory-mapped file và các trang được chia sẻ.
- NMT không thấy mọi allocation từ JNI hoặc thư viện native bên ngoài HotSpot.
- Direct buffer, allocator và native library có vòng đời riêng; số liệu có thể không xuất hiện trong cùng một metric.

Hãy đối chiếu nhiều nguồn:

1. MemoryMXBean và MemoryPoolMXBean cho heap/non-heap JVM.
2. BufferPoolMXBean cho direct/mapped buffers.
3. NMT cho subsystem native nội bộ HotSpot.
4. RSS/PSS và container memory cho footprint mà hệ điều hành nhìn thấy.

Nếu RSS tăng nhưng heap used ổn định, hãy kiểm tra NMT diff, direct buffers, JNI/native libraries, thread stacks và memory-mapped regions. Nếu NMT ổn định nhưng RSS tăng, nguyên nhân có thể nằm ngoài phạm vi NMT hoặc do thay đổi resident pages.

## 8. Đếm platform thread và OS thread

**Platform thread** thường được ánh xạ tới kernel thread của hệ điều hành. JVM còn tạo các thread nội bộ cho GC, JIT compiler, service, signal handling và các hoạt động runtime.

**ThreadMXBean** cung cấp số platform thread:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

class PlatformThreadSnapshot {
    public static void main(String[] args) {
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();

        System.out.println("livePlatformThreads = "
                + threads.getThreadCount());
        System.out.println("peakPlatformThreads = "
                + threads.getPeakThreadCount());
        System.out.println("startedPlatformThreads = "
                + threads.getTotalStartedThreadCount());
    }
}
~~~

Các phương thức trên đếm các platform thread JVM đang quản lý, không bao gồm virtual thread. Số OS thread thường gần với số platform thread này, nhưng có thể khác do native thread được thư viện tạo ngoài cơ chế Thread của Java hoặc khác biệt triển khai; dùng công cụ hệ điều hành để biết con số kernel thread thực tế.

Trên Linux, trường **Threads** trong /proc/<pid>/status hoặc cột **NLWP** của ps cho biết số OS thread. Trên Windows, thuộc tính Threads của process hoặc Process Explorer hiển thị số thread hệ điều hành.

Không giả định số OS thread bằng số worker mà ứng dụng tự tạo. JVM có thread nội bộ và framework có thể tạo thêm platform thread.

## 9. Virtual thread không phải OS thread

Virtual thread là đối tượng Thread do JVM quản lý. Khi chạy, nó được mount lên một platform thread gọi là carrier; khi thực hiện thao tác blocking được hỗ trợ, nó có thể unmount để carrier chạy virtual thread khác.

Vì vậy:

- Hàng chục nghìn virtual thread không có nghĩa tiến trình có hàng chục nghìn OS thread.
- OS thread count chủ yếu phản ánh platform threads, carrier threads và JVM internal threads.
- ThreadMXBean.getThreadCount() không đếm virtual thread.
- Stack của virtual thread được quản lý theo các stack chunk trong heap; nó không cần một native thread stack cố định cho mỗi virtual thread.

Để quan sát virtual thread trên Java 21, có thể dùng JFR events hoặc thread dump định dạng mới:

~~~bash
jcmd <pid> Thread.dump_to_file -format=json virtual-threads.json
~~~

Lệnh này liệt kê cả platform thread và virtual thread. File JSON có thể rất lớn khi ứng dụng tạo nhiều virtual thread, nên chỉ tạo khi cần điều tra và lưu file ở vị trí có đủ dung lượng.

JFR có các event jdk.VirtualThreadStart và jdk.VirtualThreadEnd để quan sát vòng đời virtual thread; hai event này tắt mặc định. Event jdk.VirtualThreadPinned và jdk.VirtualThreadSubmitFailed được bật mặc định trong cấu hình JDK 21. Có thể dùng custom JFR configuration để bật start/end khi cần đếm hoặc phân tích vòng đời.

Có thể tạo một recording ngắn để phân tích:

~~~bash
jcmd <pid> JFR.start name=performance settings=profile duration=60s filename=performance.jfr
jfr summary performance.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed performance.jfr
~~~

Recording với profile settings có overhead; dùng cùng cấu hình khi so sánh hai lần chạy và tránh bật sự kiện không cần thiết trong thời gian dài.

## 10. Đọc CPU, memory và thread cùng một lúc

Một dấu hiệu chỉ có ý nghĩa khi đặt cạnh các nhóm số liệu khác:

| Quan sát | Hướng điều tra |
|---|---|
| CPU cao, heap ổn định, OS thread ổn định | Hot method, CPU-bound work, serialization, compression hoặc GC CPU |
| CPU cao, heap tăng nhanh | Allocation rate lớn, object churn, GC cạnh tranh CPU |
| CPU thấp, heap tăng và RSS tăng | Live set/cache tăng, backlog giữ object hoặc native allocation |
| Heap ổn định, RSS tăng, NMT Thread tăng | Số platform thread hoặc stack native tăng |
| Heap ổn định, RSS tăng, NMT không tăng | JNI/native library, direct memory hoặc memory mapping ngoài phạm vi NMT |
| OS thread tăng cùng CPU và context switching | Thread pool/platform thread tăng quá mức hoặc workload tạo nhiều thread |
| OS thread ổn định nhưng virtual thread tăng | Nhiều task đang chờ; kiểm tra downstream, queue, timeout và heap giữ context |
| CPU thấp nhưng latency cao và virtual thread nhiều | Blocking I/O, semaphore/connection pool wait hoặc dependency chậm |

Các dấu hiệu trên là giả thuyết điều tra, không phải kết luận tự động. Cần kiểm tra stack, JFR, GC logs, NMT diff và metrics của dịch vụ phụ thuộc.

## 11. Đo trong container

Khi chạy trong container, giới hạn CPU và memory của cgroup có thể khác tài nguyên vật lý của host. JVM hiện đại nhận biết container limits, nhưng dashboard vẫn cần phân biệt:

- CPU process so với CPU quota được cấp.
- Heap max so với memory limit của container.
- RSS của JVM process so với memory.current của toàn cgroup.
- Thread count của JVM process so với giới hạn PID/thread của cgroup.

Trên Linux cgroup v2, các file như memory.current, memory.max, cpu.stat và pids.current cung cấp số liệu ở cấp cgroup. Nếu cgroup chứa nhiều process hoặc sidecar, số liệu đó không chỉ thuộc JVM.

Đừng đặt -Xmx bằng memory.max. Cần để lại ngân sách cho metaspace, code cache, thread stacks, direct buffers, native libraries, page cache và các tiến trình khác trong cùng cgroup.

## 12. Quy trình so sánh hai lần chạy

Để so sánh một bản build, cấu hình GC hoặc cách xử lý concurrency, hãy giữ điều kiện đo nhất quán:

1. Dùng cùng JDK build, container limit, CPU quota, heap flags và cấu hình GC.
2. Dùng cùng dữ liệu, request mix, concurrency và thời gian chạy.
3. Warm up JIT, connection pool và cache trước khi lấy mẫu.
4. Ghi baseline CPU, heap, NMT, RSS và OS thread count.
5. Chạy workload trong cùng khoảng thời gian và lấy mẫu theo cùng chu kỳ.
6. So sánh throughput, latency p95/p99 cùng với bốn nhóm tài nguyên.
7. Lặp lại nhiều lần và xem độ dao động; không kết luận từ một lần chạy.
8. Nếu bật NMT hoặc JFR, giữ cùng chế độ thu thập ở cả hai lần để overhead không làm sai lệch phép so sánh.

Nên lưu timestamp, PID, phiên bản JDK, số processor khả dụng, memory limit, heap flags và workload profile cùng mỗi bộ số liệu. Nếu thay nhiều biến cùng lúc, sẽ khó xác định thay đổi nào gây ra kết quả.

## 13. Checklist đo lường

- [ ] Tách process CPU load khỏi system CPU load.
- [ ] Ghi rõ cách chuẩn hóa CPU percent theo số processor.
- [ ] Đo heap used, committed và max theo thời gian.
- [ ] Theo dõi non-heap pools và direct/mapped buffers.
- [ ] Bật NMT từ startup khi cần phân tích native memory.
- [ ] Dùng NMT baseline/diff và nhớ NMT không bao phủ JNI/native allocations bên ngoài HotSpot.
- [ ] Đo RSS/PSS ở hệ điều hành, không suy ra native memory bằng phép trừ heap đơn giản.
- [ ] Dùng ThreadMXBean để đếm platform threads, không dùng nó để đếm virtual threads.
- [ ] Dùng OS tools để đếm kernel threads thực tế.
- [ ] Dùng JFR hoặc Thread.dump_to_file JSON khi cần quan sát virtual threads.
- [ ] Trong container, so sánh với CPU/memory/PID cgroup limits.
- [ ] Giữ workload, warm-up, sampling interval và công cụ đo nhất quán khi so sánh.

## Tài liệu tham khảo

- [Java SE 21 API: OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html)
- [Java SE 21 API: MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Java SE 21 API: ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Java SE 21 API: BufferPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Java SE 21: Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html)
- [Java SE 21: The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Java SE 21: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java SE 21: Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
