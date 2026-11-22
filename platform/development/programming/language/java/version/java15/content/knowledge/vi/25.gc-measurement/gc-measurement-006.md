# Đo heap, metaspace, RSS và CPU khi đánh giá Garbage Collection (Java 15+)

## 1. Mục tiêu: đo đúng thứ cần đo

Khi một ứng dụng Java gặp **GC pause dài, tăng bộ nhớ, CPU cao hoặc bị container OOMKilled**, có ít nhất bốn đại lượng cần tách riêng:

1. **Java heap:** vùng bộ nhớ JVM dùng chủ yếu để chứa các Java objects/arrays; được quản lý bởi garbage collector.
2. **Metaspace:** bộ nhớ phục vụ metadata của lớp trong HotSpot; thuộc phạm vi **non-heap** của JVM, không phải heap chứa đối tượng thông thường.
3. **RSS (Resident Set Size):** lượng trang bộ nhớ vật lý đang thường trú được hệ điều hành tính cho **process**, có thể bao gồm cả phần Java heap, code, thread stacks, native memory và các trang ánh xạ khác.
4. **CPU:** lượng thời gian CPU mà tiến trình/luồng dùng trong một khoảng; cần phân biệt **CPU của JVM process**, **CPU toàn hệ thống/container** và **thời gian tạm dừng do GC**.

Bốn chỉ số trả lời **những câu hỏi khác nhau**. Chẳng hạn, **heap used** có thể ổn định nhưng **RSS** vẫn tăng do direct buffers, native allocations hoặc nhiều thread. **GC pause** nhỏ không có nghĩa API p99 tốt nếu GC worker hoặc application threads đang tranh CPU.

Bài này thuộc nhóm **Đo lường GC** trong Java 15, sử dụng API vẫn còn được hỗ trợ trong Java hiện đại: `MemoryMXBean`, `MemoryPoolMXBean`, `OperatingSystemMXBean`, `GarbageCollectorMXBean`, `jcmd`, Native Memory Tracking (NMT), JFR và công cụ hệ điều hành. Ví dụ đầy đủ được biên dịch ở mức **Java 17** và chạy kiểm chứng trên **Azul Zulu JDK 24**.

**Quy tắc quan trọng:** luôn ghi **JDK build, vendor, GC, OS/container, kích thước heap, mốc thời gian và workload** cùng số đo. Không so các số đo tại thời điểm hoặc phạm vi khác nhau rồi kết luận nguyên nhân tăng bộ nhớ/CPU.

## 2. Bảng phân biệt các đại lượng

| Chỉ số | Phạm vi | Đơn vị thường gặp | Lấy bằng gì? | Không phải là gì? |
| --- | --- | --- | --- | --- |
| **Heap used** | Java heap đã dùng ở thời điểm snapshot | bytes / MiB | `MemoryMXBean.getHeapMemoryUsage().getUsed()` | Không phải toàn bộ RAM tiến trình |
| **Heap committed** | Heap được JVM bảo đảm sẵn để dùng | bytes / MiB | `getCommitted()` | Không phải RSS và không phải số object còn sống |
| **Heap max** | Giới hạn quản lý heap mà JVM biết | bytes / MiB hoặc `-1` | `getMax()`, cấu hình `-Xmx` | Không phải giới hạn tổng memory container |
| **Non-heap used** | Những pool JVM không thuộc heap | bytes / MiB | `getNonHeapMemoryUsage()` | Không bao gồm mọi native allocation |
| **Metaspace used** | Pool metadata lớp của HotSpot | bytes / MiB | `MemoryPoolMXBean` tên `Metaspace` | Không phải kích thước toàn bộ non-heap |
| **RSS** | Bộ nhớ vật lý thường trú của process theo OS | KiB / MiB | `ps`, `/proc`, công cụ process OS | Không bằng heap used/committed |
| **Process CPU time** | Tổng CPU time của JVM process (cộng nhiều thread) | nanoseconds | `com.sun.management.OperatingSystemMXBean.getProcessCpuTime()` | Không phải wall-clock duration |
| **Process CPU load** | CPU activity gần đây của process | tỷ lệ 0–1 hoặc giá trị âm nếu không hỗ trợ | `getProcessCpuLoad()` | Không phải chỉ phần CPU của GC |
| **GC pause** | Thời gian ứng dụng bị dừng vì hoạt động GC tương ứng | ms / histogram | `-Xlog:gc*`, JFR | Không phải process CPU time |

**Chú ý về phạm vi:** NMT (HotSpot) cho thấy bộ nhớ **reserved/committed** theo các subsystem của JVM; **NMT không phải bộ đo RSS** và không bao quát mọi thư viện native bên thứ ba. Với container, số `memory.current` của cgroup v2 cũng **không phải RSS riêng một process**: nó phản ánh mức sử dụng bộ nhớ được cgroup hạch toán, có thể bao gồm page cache và nhiều tiến trình.

## 3. Hiểu `MemoryUsage`: used, committed, max, init

API `java.lang.management.MemoryUsage` có bốn số đo:

```text
init       : kích thước ban đầu JVM yêu cầu (có thể không xác định)
used       : lượng đang dùng
committed  : lượng được bảo đảm sẵn để JVM sử dụng
max        : giới hạn quản lý bộ nhớ (có thể không xác định)
```

Theo hợp đồng API, `used <= committed` và khi `max` được định nghĩa, `committed <= max`. Giá trị `init` hoặc `max` **có thể bằng `-1`**, nghĩa là không xác định; **không lấy `-1` chia cho MiB rồi in thành bộ nhớ âm**.

Các chỉ số này thuộc **phạm vi vùng bộ nhớ JVM đang được báo cáo**. Không áp công thức `RSS = heap committed + non-heap committed`: bộ nhớ vật lý có thể khác committed memory do page residency, shared pages, stacks, direct buffers và nhiều phần cấp phát native.

### 3.1. Heap usage không nhất thiết bằng “live objects”

`heap.used` là snapshot lượng đang chiếm trong vùng heap. Nó có thể chứa object **chưa thể thu hồi tại thời điểm lấy mẫu**, kể cả những object sẽ được GC thu dọn trong một chu kỳ sau.

Không nên khẳng định `heap.used` chính xác là “live set” nếu không có định nghĩa phép đo phù hợp. Để xem xu hướng live set, có thể so heap used **sau các collection tương đương**, kết hợp GC log, allocation rate và load profile. **Đừng ép `System.gc()` trên production chỉ để tạo một số đo đẹp**: explicit GC có thể gây ảnh hưởng hiệu năng và không nhất thiết phản ánh hành vi thật.

### 3.2. Heap committed và heap max

- `-Xms` ảnh hưởng heap initial/minimum theo cấu hình VM.
- `-Xmx` là cấu hình giới hạn heap tối đa cho HotSpot.
- `heap.max` thường phản ánh trần heap mà VM sử dụng trong cấu hình đang chạy.
- `heap.committed` có thể mở rộng hoặc thu hẹp tùy collector, flags và áp lực bộ nhớ.

Ví dụ ở một process được chạy với `-Xms64m -Xmx128m`, `heap.max` quan sát được là khoảng **128 MiB**. Nhưng **container memory limit 256 MiB không đồng nghĩa `-Xmx256m` luôn an toàn**, bởi còn non-heap và native memory.

## 4. Đo heap và non-heap qua API chuẩn Java

`MemoryMXBean` thuộc module `java.management`, là API chính thức của Java SE. Trong method Java:

```java
MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = memory.getHeapMemoryUsage();
MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();

long heapUsedBytes = heap.getUsed();
long heapCommittedBytes = heap.getCommitted();
long heapMaxBytes = heap.getMax();
long nonHeapUsedBytes = nonHeap.getUsed();
```

Các import:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
```

Đây là **snippet**; chương trình chạy hoàn chỉnh nằm ở phần 8.

Muốn in MiB, dùng:

```java
double usedMiB = heapUsedBytes / 1024.0 / 1024.0;
```

**1 MiB = 1.048.576 bytes**; không nhầm với MB thập phân (1.000.000 bytes). Trong báo cáo, ghi rõ **MiB/KiB** hoặc **MB/kB**, tránh chỉ ghi số `256` không đơn vị.

### 4.1. Tại sao non-heap không phải toàn bộ native memory?

`MemoryMXBean.getNonHeapMemoryUsage()` tổng hợp các non-heap memory pools mà JVM công bố. Ở HotSpot, các pool có thể bao gồm Metaspace, Compressed Class Space và các vùng CodeHeap/Code Cache.

Nhiều native allocations khác (ví dụ direct buffers, JNI/native library, native thread stacks hay cấu trúc GC) không nhất thiết được tổng hợp vào con số này. Do đó một tình huống **heap used = 100 MiB, non-heap used = 30 MiB, RSS = 500 MiB** không tự động là “JVM báo sai”. Nó cho biết cần đo thêm các thành phần ngoài heap/non-heap pools.

## 5. Đo Metaspace chính xác hơn

### 5.1. Metaspace là gì?

Trong HotSpot hiện đại, **Metaspace** quản lý metadata gắn với classes/classloaders. Khác với Java objects thông thường, class metadata nằm ở phần quản lý bộ nhớ ngoài Java object heap. Áp lực Metaspace có thể tăng khi:

- Load nhiều lớp trong một tiến trình.
- Sinh lớp động, proxy hoặc bytecode runtime.
- Có nhiều classloader có vòng đời dài.
- Classloader bị giữ tham chiếu, gây **classloader leak** và ngăn unloading.
- Mở rộng ứng dụng làm tăng số classes/classloaders theo thiết kế.

**Không suy ra ngay “Metaspace leak” từ một vài lần tăng.** JVM có thể cache metadata và tăng pool lúc warmup. Cần xem xu hướng ổn định của class count, class unloading, classloader lifecycle và mức memory sau tải lặp lại.

### 5.2. Dùng `MemoryPoolMXBean` thay vì cộng nhầm

`MemoryPoolMXBean` mô tả từng pool heap hoặc non-heap. Trên **HotSpot**, có thể tìm pool có tên `Metaspace`:

```java
for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
    if (pool.getType() == MemoryType.NON_HEAP
            && pool.getName().equals("Metaspace")) {
        MemoryUsage usage = pool.getUsage();
        if (usage != null) {
            System.out.println("Metaspace used bytes = " + usage.getUsed());
        }
    }
}
```

Đoạn này là snippet trong method có import và xử lý phù hợp.

**Tên pool là thông tin implementation-specific:** nếu runtime không có pool tên `Metaspace` (ví dụ VM khác), đừng tự tạo số `0` hoặc coi không có Metaspace là lỗi dữ liệu. Hãy ghi **not available for this VM** và tham khảo công cụ quản trị tương ứng.

### 5.3. Phân biệt Metaspace với Compressed Class Space

HotSpot có thể công bố riêng `Metaspace` và `Compressed Class Space`. Chúng không phải cùng một pool và không nên đếm trùng khi lập báo cáo. Nếu muốn quan sát **tổng native memory liên quan classes**, nên dùng thêm `jcmd <PID> VM.metaspace` hoặc NMT `Class` category (khi được bật), thay vì cộng các số đo không rõ phạm vi.

`MaxMetaspaceSize` là một tùy chọn HotSpot còn được hỗ trợ nhưng **không phải giải pháp mặc định cho mọi leak**. Giới hạn quá chặt có thể dẫn tới `OutOfMemoryError: Metaspace`; muốn sửa memory leak cần xử lý classloader lifecycle hoặc nguyên nhân cấp phát metadata.

## 6. RSS: bộ nhớ vật lý của tiến trình, không phải JVM heap

### 6.1. RSS đo cái gì?

**Resident Set Size (RSS)** là lượng trang bộ nhớ thường trú mà hệ điều hành hạch toán cho process ở thời điểm đo. Nó khác:

- **Heap used:** object footprint được JVM báo cáo.
- **Heap committed:** dung lượng heap JVM đã cam kết.
- **Virtual memory size (VSZ/VIRT):** không gian địa chỉ ảo, có thể lớn hơn rất nhiều RSS.
- **NMT reserved:** vùng địa chỉ JVM đặt trước; không đồng nghĩa toàn bộ đã cư trú trong RAM.
- **Container memory usage:** hạch toán của cgroup, không nhất thiết trùng RSS riêng một PID.

RSS có thể bao gồm những phần không nhìn thấy trong `MemoryMXBean`: native allocations, thread stacks, direct buffers, JIT-compiled code, GC metadata, loaded libraries và file mappings. Các trang được chia sẻ có thể được hạch toán theo cơ chế của OS; không cộng RSS các process một cách máy móc để suy ra RAM vật lý duy nhất đang dùng.

### 6.2. Đo RSS trên Linux

Với PID thực tế lấy từ `ProcessHandle.current().pid()` hoặc `ps`, trong shell Linux:

```bash
ps -o pid,rss,%cpu -p 12345
```

Trên nhiều Linux `ps`, cột `RSS` tính bằng **KiB**; cột `%CPU` của `ps` thường là mức đo trong phạm vi đời sống process hoặc thống kê do công cụ định nghĩa, **không mặc nhiên là mức CPU tức thời trong 1 giây**.

Có thể kiểm tra:

```bash
grep -E 'VmRSS|VmHWM|VmSize' /proc/12345/status
```

- `VmRSS`: RSS được kernel báo cho process, thường tính kB/KiB theo giao diện Linux.
- `VmHWM`: mức resident peak (*high-water mark*) nếu kernel công bố.
- `VmSize`: kích thước không gian địa chỉ ảo; **không** phải RSS.

Khi cần số đo chi tiết hơn và quyền truy cập cho phép, Linux có thể có `/proc/12345/smaps_rollup` với trường `Rss:`, nhưng đọc vùng này có thể đắt hơn và phụ thuộc kernel/permission. Không poll `smaps_rollup` tần suất quá cao trên production nếu chưa đánh giá overhead.

**PID thay đổi theo từng lần chạy.** Không sao chép PID `12345` nguyên xi; nó chỉ là minh họa cú pháp.

### 6.3. Đo working set trên Windows

Với PowerShell và PID thực của Java process:

```powershell
Get-Process -Id 12345 | Select-Object Id, ProcessName, WorkingSet64, PrivateMemorySize64
```

- `WorkingSet64` báo kích thước working set theo bytes, một khái niệm tương tự resident memory trên Windows.
- `PrivateMemorySize64` báo **private memory** theo nghĩa Windows; **không phải** Java heap used và không thay cho working set.
- Một phép so RSS Linux với Windows Working Set cần ghi rõ công cụ/định nghĩa và không giả định chúng tuyệt đối giống nhau trên mọi OS.

Nếu chỉ cần xem tổng quan, Task Manager/Process Explorer có thể cho process memory, nhưng khi làm phân tích nhiều lần nên thu số liệu có timestamp và đơn vị rõ ràng.

### 6.4. Đo trên macOS

Một lựa chọn quan sát process:

```bash
ps -o pid,rss,%cpu -p 12345
```

Đơn vị/cách trình bày cần đọc theo `man ps` của macOS; không mặc định các công cụ trên mọi hệ điều hành có định nghĩa giống hệt Linux.

## 7. CPU: không nhầm elapsed time và CPU time

### 7.1. CPU time của JVM process

`com.sun.management.OperatingSystemMXBean` (module **`jdk.management`**, phần mở rộng quản trị được cung cấp ở các OpenJDK/HotSpot JDK hiện đại) có:

```java
long cpuNanoseconds = osBean.getProcessCpuTime();
double recentProcessCpuLoad = osBean.getProcessCpuLoad();
```

`getProcessCpuTime()` trả tổng thời gian CPU process đã dùng, **đơn vị nanoseconds**, hoặc `-1` nếu nền tảng không hỗ trợ. Độ phân giải biểu diễn nanoseconds **không có nghĩa kết quả chính xác tới 1 ns**. CPU process bao gồm **application threads và JVM internal threads**, trong đó có GC/JIT threads.

`getProcessCpuLoad()` phản ánh mức sử dụng CPU gần đây theo định nghĩa của implementation, có thể trả **giá trị âm** khi chưa có số liệu. Đặc biệt, lần gọi đầu tiên hoặc sampling ngắn có thể không đại diện. Không diễn giải một số `0.00` đơn lẻ thành “GC không dùng CPU”.

### 7.2. Tính CPU bằng hai snapshot

Lấy các mốc:

```text
wallDeltaNs = wallEndNs - wallStartNs
cpuDeltaNs  = processCpuEndNs - processCpuStartNs

cpuCoreEquivalents = cpuDeltaNs / wallDeltaNs
cpuPercentOfAvailable = 100 * cpuCoreEquivalents / availableProcessors
```

Cần `wallDeltaNs > 0`, CPU time không âm và CPU delta hợp lệ. **`cpuCoreEquivalents` có thể lớn hơn 1** nếu process dùng nhiều core song song. Ví dụ nếu trong 1 giây wall time, process dùng tổng cộng 2 giây CPU time từ nhiều thread, giá trị gần **2 core-equivalents**.

`cpuPercentOfAvailable` là một cách **chuẩn hóa tham khảo** với `OperatingSystemMXBean.getAvailableProcessors()`, không nhất thiết giống `%CPU` của `top`, Task Manager hoặc phần trăm CPU quota của container. HotSpot có tính container-awareness trong những cấu hình được hỗ trợ, nhưng behavior của CPU quota/cpuset có thể khác giữa JVM build, cgroups và flags.

### 7.3. CPU process không phải CPU GC

Dù CPU process lên 80%, chưa thể kết luận **GC tiêu thụ 80%**. CPU có thể đến từ:

- Application threads xử lý request.
- GC worker threads.
- JIT compiler.
- Framework/background workers.
- Native libraries/JNI.

Muốn phân tích phần GC cụ thể, dùng **GC unified logging**, **JFR** và khi phù hợp CPU profiling. Tránh suy luận từ một số liệu tổng CPU của toàn JVM.

## 8. Chương trình Java 17+ chạy được: heap, non-heap, metaspace và CPU

Ví dụ này chỉ dùng các API công khai còn được hỗ trợ. Phần `java.management` là Java SE API; riêng `com.sun.management.OperatingSystemMXBean` là **API mở rộng JDK**, vì thế chương trình kiểm tra `instanceof` và xử lý tình huống VM không cung cấp.

**Lưu ý:** Không có một lời gọi chuẩn `MemoryMXBean.getRSS()` trong Java SE; chương trình **cố ý in `rss=OS_TOOL_REQUIRED`** để nhắc phải đo RSS bằng OS/cgroup monitoring. Nó không bịa RSS bằng cách cộng heap với non-heap.

Tạo file **`MemoryCpuProbe.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.lang.management.OperatingSystemMXBean;
import java.util.Locale;

public class MemoryCpuProbe {
    static double mib(long bytes) {
        return bytes / 1024.0 / 1024.0;
    }

    static void showUsage(String name, MemoryUsage usage) {
        System.out.printf(Locale.ROOT,
                "%s.usedMiB=%.2f committedMiB=%.2f maxMiB=%s%n",
                name, mib(usage.getUsed()), mib(usage.getCommitted()),
                usage.getMax() < 0 ? "undefined"
                        : String.format(Locale.ROOT, "%.2f", mib(usage.getMax())));
    }

    public static void main(String[] args) throws InterruptedException {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        showUsage("heap", memory.getHeapMemoryUsage());
        showUsage("nonHeap", memory.getNonHeapMemoryUsage());

        boolean metaspaceFound = false;
        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            if (pool.getType() == MemoryType.NON_HEAP
                    && pool.getName().equals("Metaspace")) {
                MemoryUsage usage = pool.getUsage();
                if (usage != null) {
                    showUsage("metaspace", usage);
                    metaspaceFound = true;
                }
            }
        }
        System.out.println("metaspaceFound=" + metaspaceFound);

        OperatingSystemMXBean baseOs = ManagementFactory.getOperatingSystemMXBean();
        System.out.println("availableProcessors=" + baseOs.getAvailableProcessors());
        System.out.println("pid=" + ProcessHandle.current().pid());

        if (baseOs instanceof com.sun.management.OperatingSystemMXBean os) {
            long wallStart = System.nanoTime();
            long cpuStart = os.getProcessCpuTime();
            Thread.sleep(250);
            long cpuEnd = os.getProcessCpuTime();
            long wallEnd = System.nanoTime();
            if (cpuStart >= 0 && cpuEnd >= cpuStart && wallEnd > wallStart) {
                double cpuCores = (double) (cpuEnd - cpuStart)
                        / (wallEnd - wallStart);
                System.out.printf(Locale.ROOT, "cpuCoreEquivalents=%.4f%n", cpuCores);
                System.out.printf(Locale.ROOT, "cpuPercentOfAvailable=%.2f%%%n",
                        cpuCores * 100.0 / baseOs.getAvailableProcessors());
            } else {
                System.out.println("processCpuTime=unavailable");
            }
            double processLoad = os.getProcessCpuLoad();
            System.out.println("processCpuLoadAvailable=" + (processLoad >= 0.0));
        } else {
            System.out.println("processCpuTime=unavailable");
            System.out.println("processCpuLoadAvailable=false");
        }

        System.out.println("gcBeanCount="
                + ManagementFactory.getGarbageCollectorMXBeans().size());
        System.out.println("rss=OS_TOOL_REQUIRED");

        if (args.length == 1 && "--hold".equals(args[0])) {
            System.out.println("holdingSeconds=20");
            Thread.sleep(20_000);
        }
    }
}
```

Biên dịch với JDK 17 trở lên:

```bash
javac --release 17 MemoryCpuProbe.java
java -Xms64m -Xmx128m MemoryCpuProbe
```

### 8.1. Stdout từ một lần chạy kiểm chứng

Mã đã được **biên dịch bằng `javac --release 17` và chạy trên Azul Zulu JDK 24**. Đây là **stdout chính xác của một lần chạy**, không phải giá trị cố định cần trùng trên mọi máy:

```text
heap.usedMiB=2.11 committedMiB=66.00 maxMiB=128.00
nonHeap.usedMiB=2.42 committedMiB=8.13 maxMiB=undefined
metaspace.usedMiB=0.64 committedMiB=0.81 maxMiB=undefined
metaspaceFound=true
availableProcessors=28
pid=49856
cpuCoreEquivalents=0.0000
cpuPercentOfAvailable=0.00%
processCpuLoadAvailable=true
gcBeanCount=3
rss=OS_TOOL_REQUIRED
```

Ở lần chạy khác, **heap, metaspace, CPU, GC beans, PID, processors và non-heap values đều có thể thay đổi** do JDK, GC, nền tảng, cgroup, thời điểm chụp và công việc nền. Ví dụ trên chạy rất ngắn và có `Thread.sleep(250)`, vì vậy CPU time delta gần 0 là bình thường; **đừng dùng kết quả này để benchmark CPU dưới tải thực tế**.

Đặc biệt:
- `maxMiB=undefined` xuất hiện vì một số memory pools báo `getMax() == -1`, **không đồng nghĩa max = 0**.
- `metaspaceFound=true` là quan sát của HotSpot trong ví dụ; một VM khác có thể dùng tên pool khác.
- `rss=OS_TOOL_REQUIRED` là lời nhắc cố ý: Java API này không trực tiếp cho RSS process.
- `gcBeanCount=3` tùy collector; **không phải số lần GC đã chạy**. Để đếm collection hãy dùng các `GarbageCollectorMXBean` và hiểu đúng counters.

### 8.2. Giữ tiến trình sống để lấy RSS từ công cụ OS

Chương trình hỗ trợ tùy chọn `--hold` để giữ process thêm **20 giây**, đủ cho một lần quan sát OS trong môi trường thông thường:

```bash
java -Xms64m -Xmx128m MemoryCpuProbe --hold
```

Khi thấy dòng `pid=...`, dùng PID đó trong **terminal thứ hai**:

Linux:

```bash
ps -o pid,rss,%cpu -p 12345
grep -E 'VmRSS|VmHWM' /proc/12345/status
```

Windows PowerShell:

```powershell
Get-Process -Id 12345 | Select-Object Id, WorkingSet64, PrivateMemorySize64
```

Thay `12345` bằng PID chương trình in ra. Mỗi lần chạy sẽ có PID khác nhau. Nếu process đã thoát trước khi đo, chạy lại với `--hold` hoặc đo trên tiến trình service chạy dài hạn; không dùng PID cũ của một process khác.

**Lưu ý quyền truy cập:** một số container/sandbox không cho đọc `/proc/<pid>/status` hoặc truy vấn process khác user. Khi đó dùng process/container monitoring có sẵn, không tự ý nới quyền hệ thống production.

## 9. Đo trên JVM đang chạy bằng `jcmd`

Với **HotSpot JDK có công cụ `jcmd` và quyền attach**, chạy:

```text
jcmd <PID> GC.heap_info
jcmd <PID> VM.metaspace
jcmd <PID> VM.flags
jcmd <PID> VM.command_line
```

- `GC.heap_info`: tổng quan heap và GC layout tùy collector.
- `VM.metaspace`: thông tin Metaspace theo HotSpot implementation, hữu ích khi điều tra class metadata.
- `VM.flags` và `VM.command_line`: xác nhận JVM startup flags và runtime thực tế.
- Độ chi tiết của output có thể khác theo JDK/GC; kiểm tra `jcmd <PID> help` để biết commands hiện có.

**Không dùng `GC.class_histogram` hoặc heap dump liên tục như một công cụ metrics nhẹ**: chúng có thể tiêu tốn tài nguyên, ảnh hưởng độ trễ và có thể chứa dữ liệu nhạy cảm. Đối với metrics liên tục, ưu tiên MXBeans/JMX, JFR hoặc exporter được vận hành có kiểm soát.

## 10. Native Memory Tracking: khi RSS tăng nhưng heap ổn định

### 10.1. Bật NMT khi khởi động HotSpot

Native Memory Tracking (NMT) vẫn là công cụ hỗ trợ chẩn đoán trong HotSpot hiện đại. Phải bật ngay khi khởi động JVM:

```bash
java -XX:NativeMemoryTracking=summary -Xms256m -Xmx512m -jar app.jar
```

Các mức chính:

- `off`: không theo dõi (mặc định nếu không bật).
- `summary`: tổng hợp JVM native memory theo subsystem như Java Heap, Class, Thread, Code, GC.
- `detail`: thêm thông tin vùng/call sites (chi tiết và overhead cao hơn).

NMT có overhead; chỉ bật mức cần thiết và xác nhận khả năng vận hành, nhất là ở service nhạy CPU/latency.

### 10.2. Chụp baseline và so thay đổi

Sau khi ứng dụng warmup, dùng:

```text
jcmd <PID> VM.native_memory summary
jcmd <PID> VM.native_memory baseline
jcmd <PID> VM.native_memory summary.diff
```

Thực hiện `baseline` một lần tại mốc đã xác định, sau đó gọi `summary.diff` vào các thời điểm sau để thấy **mức thay đổi kể từ baseline**. Nếu bật mức `detail`, có thể dùng `detail` hoặc `detail.diff` tương ứng. Không so số chụp trước warmup với trạng thái full load rồi tự kết luận leak.

**Giới hạn quan trọng của NMT:**

- `reserved`: không gian địa chỉ ảo JVM đặt trước.
- `committed`: vùng JVM đã cam kết; **không bằng RSS**.
- NMT theo dõi bộ nhớ mà HotSpot/JVM quản lý; có thể **không theo dõi tất cả allocations của thư viện native bên ngoài**.
- Output có thể không phản ánh đầy đủ shared mappings, file-backed pages và mọi thứ mà OS/cgroup tính.

Vì vậy nếu **RSS vẫn tăng nhưng các category NMT tương đối ổn định**, cần phân tích thêm `/proc`, direct buffers, JNI, native libraries, threads, memory mappings hoặc công cụ OS. **Đừng lấy `RSS - heap.used` rồi kết luận đó chính xác là “native leak”.**

## 11. Đo memory và CPU của container: đừng nhầm process với cgroup

Trong Docker/Kubernetes chạy Linux, có ít nhất **ba lớp metric**:

1. **JVM metrics:** heap, metaspace, GC pauses, Java threads.
2. **Process metrics:** RSS, process CPU time, file descriptors, process memory maps.
3. **Cgroup/container metrics:** tổng memory/CPU mà cgroup hạch toán, quota, throttling; có thể chứa nhiều process và page cache.

Với **cgroups v2**, trong môi trường nơi các đường dẫn tương ứng đúng với cgroup của process, có thể kiểm tra:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpu.max
```

Ý nghĩa:

- `memory.current`: lượng memory cgroup đang sử dụng, **bytes**; không phải RSS riêng JVM.
- `memory.max`: giới hạn cứng của memory cgroup, hoặc `max` nếu không giới hạn tại mức này.
- `memory.events`: counters liên quan ngưỡng và OOM.
- `cpu.stat`: CPU usage theo microseconds và những counters khác; khi controller phù hợp còn có throttle stats.
- `cpu.max`: quota/period, có thể chứa `max` nếu không giới hạn tại cgroup đó.

Đường dẫn và khả năng đọc khác giữa cgroups v1/v2, nested cgroups và container runtime. **Không tự khẳng định** `/sys/fs/cgroup/` luôn là cgroup của Java process trên mọi máy. Với Kubernetes, nên dùng metrics collector/container monitoring được cấu hình chính thức, đồng bộ thời gian với JMX/JFR.

Một container có `memory.current` cao nhưng process RSS không cao tương ứng có thể do page cache hoặc process khác trong cgroup. Ngược lại, RSS tăng cùng `memory.events` và OOMKilled dù heap used ổn định gợi ý xem **native memory**, không chỉ điều chỉnh Java heap GC.

### 11.1. CPU trong container

CPU process có thể được biểu diễn như **core-equivalents** trong một khoảng thời gian, còn metric cgroup biểu diễn CPU usage và CPU throttling theo giới hạn/quota. Một JVM chạy trên host 32 core nhưng được quota 2 CPU không nên kết luận “CPU còn trống 30 core” chỉ vì host utilization thấp.

Khi đo, cần ghi các cột riêng:

```text
process_cpu_cores
container_cpu_usage_cores
container_cpu_limit_cores
container_cpu_throttled_periods_or_time
host_cpu_utilization
```

Không trộn lẫn `getProcessCpuLoad()` với số `%CPU` từ `ps` hoặc `cpu.stat` nếu chưa chuẩn hóa đơn vị, số CPU và khoảng thời gian đo.

## 12. Ghép số liệu GC để tìm nguyên nhân

### 12.1. Trường hợp A — heap used tăng mãi

Nếu heap used sau các chu kỳ GC tương đương vẫn tăng theo thời gian, kết hợp:

- Allocation rate.
- GC pause/cycle counts.
- Class histogram/heap dump **khi được phép và phù hợp**.
- Reference retention, cache growth, queue/buffer backlog.
- Biểu đồ heap used và heap committed cùng thời điểm.

Không chỉ nhìn heap used một lần rồi gọi là memory leak. Một số cache có thể tăng đến kích thước ổn định theo thiết kế.

### 12.2. Trường hợp B — heap ổn nhưng Metaspace tăng

Kiểm tra:

- Metaspace pool used/committed.
- Số class đã load/unload (`ClassLoadingMXBean`).
- Classloader lifecycle và các framework tạo class động.
- `jcmd VM.metaspace`, NMT `Class` category khi đã bật.
- Xu hướng qua warmup, tải cao và sau khi ngưng tải.

Nếu metadata tăng vì một framework tải thêm class trong giai đoạn khởi động, đó có thể là bình thường. **Classloader leak** cần thêm bằng chứng classloader không được thu hồi và objects liên quan còn bị giữ.

### 12.3. Trường hợp C — RSS tăng nhưng heap/metaspace ổn

Cần tìm thành phần ngoài object heap:

- Direct/native buffers.
- JNI/native libraries.
- Thread count và native stack reservation/commit.
- JVM code cache, GC structures, allocator fragmentation.
- File mappings, shared libraries và OS-specific page accounting.
- NMT `Thread`, `Code`, `GC` và các category khác; `/proc/<pid>/smaps_rollup` nếu được phép.

Đừng vội tăng `-Xmx`: heap không nhất thiết là nguyên nhân. Cũng không mặc định mọi chênh lệch RSS là leak; một số bộ cấp phát có thể giữ memory để tái sử dụng.

### 12.4. Trường hợp D — CPU cao, GC pause thấp

Kiểm tra process CPU, CPU throttling container, app profiling, JFR GC events và GC threads. Với các GC đồng thời như ZGC/Shenandoah, **một phần GC work chạy concurrent** nên CPU overhead có thể tăng dù GC pauses ngắn.

Cần so **p99 request latency**, throughput, CPU, RSS và allocation stalls trước khi kết luận collector mới tốt hoặc xấu.

### 12.5. Trường hợp E — container OOMKilled dù `heap.max < memory.limit`

Container memory limit bao trùm hơn Java heap. Có thể có Metaspace, code cache, direct buffers, thread stacks, native allocations và page cache. `heap.max` thấp hơn limit vẫn **không bảo đảm** process/container không OOM.

Điều tra bằng timeline: heap/non-heap pools, process RSS, cgroup `memory.current`, `memory.events`, NMT nếu có, và số thread/direct buffers theo workload. Kiểm tra cấu hình `-Xmx` với memory budget của **toàn bộ** container.

## 13. Phương pháp sampling và cảnh báo

Đo một snapshot là hữu ích để debug nhưng **không đủ** để kết luận nguyên nhân. Một dashboard nên có ít nhất:

| Metric | Phạm vi | Chu kỳ/loại dữ liệu |
| --- | --- | --- |
| JVM heap used/committed/max | JVM | Gauge, theo chu kỳ |
| Metaspace used/committed | JVM pool | Gauge, theo chu kỳ |
| Process RSS/working set | OS process | Gauge, theo chu kỳ |
| Container memory current/limit | Cgroup | Gauge |
| Process CPU time | OS/JVM | **Counter tích lũy**; lấy rate từ delta |
| Container CPU usage + throttling | Cgroup | Counter; lấy rate/delta |
| GC pause durations | JVM GC | Event/histogram |
| GC collection count/time | JVM GC beans | Counter, semantics tùy collector |
| Class count, live threads | JVM | Gauge |
| Request p95/p99/p99.9 latency | Ứng dụng | Histogram/summary |

**Đồng bộ thời gian sampling** và ghi version/GC flags. Không so RSS lúc spike với heap snapshot lấy 10 phút trước rồi gán nguyên nhân.

Đối với cảnh báo:

- Cảnh báo **memory headroom** theo container usage/limit và xu hướng RSS, không chỉ heap used%.
- Cảnh báo **CPU throttling** đi cùng request p99 và process CPU rate.
- Cảnh báo **Metaspace tăng dài hạn** theo classloader/class count, không chỉ một lần vượt ngưỡng.
- Với collector đồng thời, theo dõi **allocation stalls** và GC cycle metrics, không chỉ pause duration.
- Hạn chế cardinality của labels; không gắn PID hoặc request ID vào mọi time series dài hạn nếu gây nổ số series.

### 13.1. Những công cụ nên dùng ở mức độ phù hợp

- **JMX/MXBeans:** API nhẹ, phù hợp metric định kỳ.
- **JFR:** quan sát phân phối event GC, allocation, CPU/JVM activity theo profile hiện hành.
- **`jcmd`:** kiểm tra heap/metaspace/NMT khi cần điều tra có kiểm soát.
- **OS process tools:** RSS/working set, process CPU, memory maps.
- **Container monitoring:** cgroup memory/CPU/throttling, OOM metrics.
- **Application telemetry:** p99 latency, throughput và error rate.

Không dùng heap dump, class histogram chi tiết hoặc NMT `detail` với tần suất cao trên production mà không đánh giá overhead và rủi ro dữ liệu nhạy cảm.

## 14. Những nhầm lẫn phổ biến

1. **“`-Xmx` là giới hạn RAM toàn process.”** Sai: đó là trần heap theo JVM; native memory và non-heap vẫn tồn tại.
2. **“Heap used chính là RSS.”** Sai: khác phạm vi và cách hạch toán.
3. **“NMT committed bằng RSS.”** Sai: committed không đồng nghĩa trang đang resident.
4. **“Non-heap used bằng toàn bộ native memory.”** Sai: nhiều allocation không nằm trong memory pools của `MemoryMXBean`.
5. **“Metaspace tăng nghĩa chắc chắn classloader leak.”** Sai: có thể là class loading bình thường; cần bằng chứng vòng đời.
6. **“Giá trị `getMax() == -1` là -1 byte đang dùng.”** Sai: là không xác định.
7. **“Heap used giảm sau mỗi GC nên RSS phải giảm ngay.”** Sai: JVM/allocator/OS có thể giữ committed/resident pages để tái sử dụng.
8. **“`getProcessCpuTime()` là wall time.”** Sai: là tổng CPU time, có thể vượt wall delta khi nhiều threads chạy song song.
9. **“`getProcessCpuLoad()` âm nghĩa CPU âm.”** Sai: dữ liệu chưa khả dụng hoặc không được hỗ trợ.
10. **“Process CPU cao chắc chắn do GC.”** Sai: còn app threads, JIT, native code.
11. **“Cgroup `memory.current` là RSS của JVM.”** Sai: là memory được cgroup hạch toán, có thể tính cả cache và process khác.
12. **“`ps %CPU` luôn bằng CPU ratio trong Java.”** Sai: khác cửa sổ sampling và chuẩn hóa.
13. **“RSS tăng trong một thời điểm chứng minh memory leak.”** Sai: cần xu hướng, phân tích mappings và workload.
14. **“Heap dump liên tục không ảnh hưởng sản xuất.”** Sai: có thể tốn thời gian, I/O và chứa dữ liệu bí mật.
15. **“Một GC có pause thấp thì request p99 luôn thấp.”** Sai: phải đo CPU, throughput, stalls và contention.
16. **“Một số đo trên laptop đủ cho container production.”** Sai: cần cùng JDK build, OS, limits và workload.

## 15. Checklist thực hành trước khi kết luận GC/memory

- [ ] Xác định đúng **JDK version/build, vendor, GC, OS, PID, container image, heap flags**.
- [ ] Đã đo heap **used/committed/max** và xử lý `max == -1`?
- [ ] Đã đo non-heap và tách riêng **Metaspace** trên HotSpot?
- [ ] Có số **RSS process hoặc Windows Working Set**, không tự suy ra từ heap?
- [ ] Có số container `memory.current`, limit và OOM events nếu chạy trong cgroup?
- [ ] CPU time đo qua ít nhất hai snapshot với **wall-time delta** phù hợp?
- [ ] Có phân biệt process CPU, GC CPU, host CPU và container throttling?
- [ ] Metrics có đồng bộ timestamp, cùng workload và thời điểm warmup?
- [ ] Đã xem GC pauses, allocation stalls và request p99/p99.9?
- [ ] Khi RSS cao nhưng heap ổn, đã kiểm tra NMT/native buffers/thread stacks?
- [ ] Khi Metaspace tăng, đã kiểm tra class count và classloader lifecycle?
- [ ] Đã tránh dùng công cụ nặng trên production không có kế hoạch?
- [ ] Có ghi rõ **MiB/bytes**, PID, CPU ratio và cửa sổ đo?
- [ ] Các nhận định đều dựa trên **chuỗi số đo** chứ không chỉ một lần snapshot?

**Kết luận:** Đo lường GC hiệu quả không chỉ là lấy `heap.used`. Cần đồng thời quan sát **heap, metaspace, RSS và CPU** với đúng phạm vi và đơn vị; đối chiếu GC logs, NMT/JFR và cgroup metrics khi cần. **Không coi committed memory hoặc container memory usage là RSS của JVM**, không coi process CPU time là CPU của GC, và không kết luận leak từ một snapshot riêng lẻ. Đây là những nguyên tắc còn áp dụng cho Java 15+ và các JDK hiện đại.

## 16. Tài liệu chính thức còn hiệu lực

- [Oracle Java SE 27 — MemoryMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/MemoryMXBean.html): `getHeapMemoryUsage()`, `getNonHeapMemoryUsage()`.
- [Oracle Java SE 27 — MemoryUsage](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/MemoryUsage.html): `init`, `used`, `committed`, `max`, giá trị `-1`.
- [Oracle Java SE 27 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): quan sát từng memory pool, peak usage.
- [Oracle Java SE 27 — OperatingSystemMXBean extension](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): `getProcessCpuTime()`, `getProcessCpuLoad()` và phạm vi thông tin OS/JVM.
- [Oracle JDK 27 — jcmd reference](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): `GC.heap_info`, `VM.metaspace`, `VM.native_memory`.
- [Oracle JDK 27 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/27/vm/native-memory-tracking.html): phạm vi theo dõi, baseline, categories và hạn chế NMT.
- [Oracle JDK 27 — Troubleshooting Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html): phân tích JVM/native memory, công cụ chẩn đoán.
- [Oracle JDK 27 — java command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `-XX:NativeMemoryTracking`, `-Xms`, `-Xmx`, logging và JVM settings.
- [Linux Kernel — Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `memory.current`, `memory.max`, `cpu.stat`, `cpu.max` và các đơn vị.
- [Docker — Container runtime metrics](https://docs.docker.com/engine/containers/runmetrics/): memory/CPU metrics và lưu ý khác nhau giữa cgroups.

Bài học chỉ dùng API Java chính thức và công cụ còn được hỗ trợ, đồng thời phân biệt rõ API Java SE với phần mở rộng JDK và các chỉ số phụ thuộc hệ điều hành; không sử dụng cơ chế legacy hay các phương pháp GC lỗi thời.