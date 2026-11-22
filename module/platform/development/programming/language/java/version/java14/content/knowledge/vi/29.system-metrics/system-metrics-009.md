# Đối chiếu số liệu với JFR và công cụ hệ điều hành

> **Ngữ cảnh:** Java 14 → *Số liệu hệ thống* → **Đối chiếu số liệu với JFR và công cụ hệ điều hành**. JFR Event Streaming có từ Java 14 (JEP 349) và vẫn được hỗ trợ trên JDK hiện đại. Bài dùng **Java 17+**, `jdk.jfr`, `jdk.management`, `jcmd` và `jfr`; không sử dụng những cờ JFR thương mại cũ hoặc phương thức MXBean đã deprecated.

## 1. Nguyên tắc: khác số không có nghĩa một công cụ đo sai

Một JVM có thể được JFR báo **CPU khoảng 20%**, trong khi Linux `top` hiện **160% CPU cho process Java**. JVM heap có thể đang dùng **500 MiB** trong khi RSS của process là **900 MiB**, và `jdk.PhysicalMemory` cho thấy tổng memory hệ thống đang dùng **24 GiB**. Những số này **có thể đều đúng**, bởi chúng đo phạm vi và đơn vị khác nhau.

Để đối chiếu phải thống nhất ít nhất năm yếu tố:

1. **Scope:** host/máy, môi trường VM/container, cgroup, JVM process, Java thread hay Java heap?
2. **Đơn vị:** CPU fraction trong `[0,1]`, phần trăm, nanoseconds, seconds, bytes, KiB, MiB hay page count?
3. **Kiểu metric:** giá trị tức thời (*gauge*), counter tích lũy, trung bình trong một khoảng hay thời lượng event?
4. **Thời gian:** khoảng lấy mẫu, UTC timestamp, thời điểm callback hay event start/end; độ lệch đồng hồ?
5. **Nguồn và cấu hình:** JDK/version, JFR settings/period, OS tool/counter, virtual machine, quota, quyền đọc và container boundaries?

**Không so trực tiếp** Java heap với RAM toàn máy; không so một số CPU time cộng dồn với CPU load gần đây; không yêu cầu JFR periodic sample và một OS snapshot xảy ra ở **hai thời điểm khác nhau** phải bằng nhau.

~~~text
JVM application
  +-- JFR: CPU load, GC, heap summary, thread events
  +-- MXBean: process CPU time/load, heap snapshot
  +-- OS: process CPU, RSS, virtual memory, host RAM
  +-- cgroup: container CPU quota, usage, memory limits
                       |
                 Căn phạm vi + PID
                 Căn thời gian + units
                       |
                Kiểm tra giả thuyết
~~~

JFR bổ trợ công cụ OS: JFR biết **bối cảnh JVM**, còn OS biết **tài nguyên process và host**. Kết hợp cả hai giúp tránh quy kết nguyên nhân sai.

## 2. Bảng ghép metric theo đúng đại lượng

| Câu hỏi | JFR hoặc API Java | OS tool tương ứng | Không được nhầm |
| --- | --- | --- | --- |
| CPU toàn máy/môi trường bao nhiêu? | `jdk.CPULoad.machineTotal`, `OperatingSystemMXBean.getCpuLoad()` | Linux `top`/`sar`; Windows Processor counter; macOS `top` | Không phải CPU chỉ của JVM |
| JVM process dùng CPU bao nhiêu? | `jdk.CPULoad.jvmUser+jvmSystem`, `getProcessCpuLoad()` | `pidstat -u`, `ps %cpu`, process counters | Normalize per-core vs tổng CPUs |
| CPU time tích lũy? | `getProcessCpuTime()` (nanoseconds) | `Get-Process.CPU` (seconds), `/proc/PID/stat` | Counter tích lũy, không phải tải tức thời |
| Java heap used? | `MemoryMXBean.getHeapMemoryUsage().getUsed()`; `jdk.GCHeapSummary` | `jcmd PID GC.heap_info` | Heap không bằng process RSS |
| Memory toàn môi trường? | `jdk.PhysicalMemory.totalSize/usedSize`; `getTotalMemorySize()` | `free -h`, `/proc/meminfo`, Windows RAM counters | Không phải RAM riêng Java |
| Resident process memory? | Không có một JFR event luôn tương đương RSS | `ps rss`, `/proc/PID/status`, Windows WorkingSet64 | Có native, mappings, shared memory |
| Hoạt động GC? | `jdk.GarbageCollection`, `jdk.GCHeapSummary` | `-Xlog:gc*`, heap diagnostics | GC pause khác response latency |
| Java/OS threads? | `ThreadMXBean`, JFR thread events | `pidstat -t`, `ps -L` | Virtual threads không nhất thiết có OS thread 1:1 |
| Container CPU/RAM? | JVM environment-specific views | cgroup v2 `cpu.stat`, `memory.current` | Counter của cả cgroup, không chỉ một PID |

JFR events có thể **không xuất hiện** nếu không bật, không có hoạt động phù hợp hoặc recording quá ngắn. Không được chuyển “không có event” thành “giá trị bằng 0”.

## 3. CPU: hiểu đúng `jdk.CPULoad` và MXBean

### 3.1. Các trường của JFR

JFR `jdk.CPULoad` trong OpenJDK hiện đại có các trường `float`:

- `jvmUser`: phần CPU gần đây JVM process tiêu thụ ở user mode.
- `jvmSystem`: phần CPU gần đây JVM process tiêu thụ ở system/kernel mode.
- `machineTotal`: CPU load của máy/môi trường mà JFR đo.

Giá trị được biểu diễn dạng **fraction**: `0.52` tương ứng **52%**. `jfr print` có thể hiển thị thành `52%` nhờ annotation content type, nhưng Java `RecordedEvent.getFloat("jvmUser")` đọc **0.52**, không phải 52. Đừng nhân 100 hai lần.

Tổng `jvmUser+jvmSystem` biểu diễn process CPU theo định nghĩa của event, không đồng nhất với `machineTotal` và không nhất thiết trùng số phần trăm do OS tools in. Khoảng lấy mẫu do event period và triển khai quyết định.

### 3.2. API quản lý OS còn áp dụng

`com.sun.management.OperatingSystemMXBean` (module `jdk.management`) cung cấp:

| API | Kiểu/đơn vị | Ý nghĩa |
| --- | --- | --- |
| `getCpuLoad()` | `double` trong `[0,1]` hoặc âm | Recent CPU của operating environment |
| `getProcessCpuLoad()` | `double` trong `[0,1]` hoặc âm | Recent CPU riêng JVM process |
| `getProcessCpuTime()` | `long` nanoseconds hoặc `-1` | CPU time process tích lũy |
| `getTotalMemorySize()` | `long` bytes | Total memory của operating environment |
| `getFreeMemorySize()` | `long` bytes | Free memory của operating environment |

**Tên hiện hành:** từ Java 14, `getSystemCpuLoad()`, `getTotalPhysicalMemorySize()`, `getFreePhysicalMemorySize()` **deprecated**. Hướng dẫn mới dùng `getCpuLoad()`, `getTotalMemorySize()` và `getFreeMemorySize()`.

Lưu ý `getProcessCpuLoad()` và `getCpuLoad()` là các số gần đây với **cửa sổ quan sát phụ thuộc implementation**; lần gọi đầu có thể chưa có mẫu, caller khác có thể ảnh hưởng sampling. Không assert một giá trị MXBean phải bằng đúng một JFR event.

### 3.3. Một JVM có thể dùng hơn 100% CPU theo `top`

Một số OS tools tính **mỗi logical core là 100%**. Process chạy song song trên nhiều cores có thể hiển thị **160%**.

Để hiểu tỷ lệ này, đo delta theo hai thời điểm:

~~~text
deltaCpuNs   = cpuTimeAfter - cpuTimeBefore
deltaWallNs  = nanoTimeAfter - nanoTimeBefore

coreEquivalents = deltaCpuNs / deltaWallNs
normalizedApprox = coreEquivalents / effectiveProcessorCount
~~~

Nếu process dùng **1.6 giây CPU** trong **1.0 giây wall time**, nó tiêu thụ trung bình **1.6 core equivalents**. Công cụ tính per-core có thể hiển thị **160%**. Nếu có đúng **8 logical processors** cùng làm mẫu số, tỷ lệ tổng capacity ước lượng là **1.6/8 = 0.20**, tức **20%**.

Đây là **cách giải thích gần đúng**, không phải hợp đồng về sự bằng nhau. `Runtime.getRuntime().availableProcessors()` có thể bị ảnh hưởng bởi cpuset/quota/container và cách làm tròn; trên các container có CPU quota fractional, cách quy đổi cần xem chính sách thực tế.

`System.nanoTime()` phù hợp **đo độ dài khoảng thời gian**, không phải epoch timestamp để join với JFR `Instant`.

## 4. Memory: Java heap khác RSS và RAM hệ thống

- **Heap used:** `MemoryMXBean.getHeapMemoryUsage().getUsed()` trả bytes được JVM báo dùng cho Java heap. `committed`, `max` và `used` khác nhau. `max` có thể là `-1` nếu không xác định.
- **Process RSS/Working Set:** memory resident của process, gồm heap resident **và** thread stacks, metaspace, JIT code cache, direct buffers, native libraries, JNI allocations, mmap, shared mappings.
- **JFR `jdk.PhysicalMemory`:** `totalSize`/`usedSize` mô tả physical memory toàn môi trường hệ thống theo implementation, **không phải RSS riêng JVM**.
- **cgroup `memory.current`:** bytes được tính cho **cả cgroup**, không nhất thiết chỉ một Java PID.

~~~text
Host/OS memory
  +-- nhiều processes, kernel, cache
  +-- Java process resident memory
       +-- resident Java heap
       +-- native/non-heap metadata and JIT code
       +-- thread stacks, direct buffers, mmap
       +-- shared mappings
~~~

Sơ đồ trên chỉ để hiểu phạm vi: các vùng có thể chia sẻ pages, nên **không cộng từng dòng như các tập độc lập**.

### 4.1. Đơn vị cần nhớ

| Giá trị | Đơn vị điển hình |
| --- | --- |
| `getHeapMemoryUsage().getUsed()` | bytes |
| `jdk.PhysicalMemory.totalSize` và `usedSize` | bytes |
| `ps rss` / `ps vsz` trên Linux | KiB |
| `/proc/PID/status`: `VmRSS` | KiB, kernel estimate |
| Windows `WorkingSet64` | bytes |
| cgroup `memory.current` | bytes |

`1 MiB = 1_048_576 bytes`; tránh nhầm MiB nhị phân và MB thập phân, đặc biệt khi số được in bởi các công cụ khác nhau.

**Ví dụ:** heap used **500 MiB**, RSS **900 MiB**, OS memory used **24 GiB**. Không kết luận ngay **400 MiB** chênh lệch là “native leak”; muốn tìm nguyên nhân cần đo thêm trực tiếp các vùng memory, metaspace, threads, direct buffers, mmap, NMT và thay đổi theo thời gian.

**Native Memory Tracking (NMT)** có thể giúp phân nhóm HotSpot native memory nếu đã bật theo cấu hình JVM từ lúc khởi động, nhưng có overhead và không đo mọi allocation bên ngoài HotSpot. NMT committed cũng **không tự bằng RSS**.

### 4.2. Heap và GC events gắn với thời điểm khác nhau

`jdk.GarbageCollection` ghi một hoạt động GC và duration. `jdk.GCHeapSummary` (khi được bật và event phát sinh) có `heapUsed` cùng ngữ cảnh **Before/After GC**, thường có `gcId`. `MemoryMXBean` là snapshot theo thời điểm gọi; `GC.heap_info` là chẩn đoán heap từ JVM.

Đừng so heap **Before GC** của JFR với RSS được đọc **20 giây sau** để tuyên bố “GC không trả RAM”. Ngoài live objects, còn có heap committed giữ lại để tái sử dụng và OS page residency.

## 5. Căn đúng mốc thời gian, PID và sampling window

Một quy trình thực tế:

1. Xác định **PID đúng**, JVM version/distribution, host OS, architecture, container identity và thời điểm process khởi chạy.
2. Bắt đầu recording và OS monitoring sao cho **hai khoảng đo chồng lấn**, ví dụ 60 giây.
3. Lấy OS samples theo interval cố định (thí dụ 1 giây) và gắn **UTC timestamp**.
4. Dùng `RecordedEvent.getStartTime()/getEndTime()` (`Instant`) để đặt JFR events lên timeline; không dùng timestamp của file `.jfr` được copy.
5. Khi so CPU load, so **các cửa sổ thời gian gần tương ứng**, không so một instant với một average.
6. Với CPU time/cgroup counters tích lũy, **lấy delta**; với gauge như heap used, dùng snapshot gần nhau.
7. Nếu nhiều host, xác minh clock synchronization (NTP/chrony hoặc cơ chế tương đương); clock drift có thể đảo giả thứ tự sự kiện.

~~~java
// Đặt trong handler có biến RecordedEvent event:
java.time.Instant start = event.getStartTime();
System.out.println(start); // ISO-8601 UTC

// Khi cần hiển thị giờ địa phương:
System.out.println(
        start.atZone(java.time.ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

Đổi timezone chỉ đổi cách trình bày. `System.nanoTime()` không phải timestamp UTC, chỉ thích hợp lấy hiệu thời gian trong JVM.

**Sai lệch hợp lý:** JFR periodic events có period/chunk/flush; `pidstat` hay Performance Counters có interval khác. Hai timestamp cùng giây trên màn hình không đồng nghĩa hai phép đo cùng cửa sổ.

## 6. Dùng `jcmd` để ghi JFR và `jfr` để đọc

### 6.1. Xác định đúng PID JVM

~~~bash
jcmd -l
~~~

Trong ví dụ Linux sau, thay **12345** bằng PID JVM thực, và bảo đảm output path có quyền ghi:

~~~bash
jcmd 12345 JFR.start name=SystemCompare settings=default duration=60s filename=/tmp/system-compare.jfr
jcmd 12345 JFR.check
~~~

Khi recording còn chạy, có thể dump mà không nhất thiết dừng recording:

~~~bash
jcmd 12345 JFR.dump name=SystemCompare filename=/tmp/system-compare-snapshot.jfr
~~~

`JFR.check` kiểm tra recording **đang chạy**, còn `jfr summary` kiểm tra **file đã lưu**. `jcmd` cần attach đúng process và quyền thực tế (thường cùng effective user/host; container có thể cần phù hợp PID namespace).

`settings=default` và `settings=profile` có cấu hình events/overhead khác nhau. Muốn kiểm tra event và period, dùng `JFR.check verbose=true`, `jfr metadata` và cấu hình `.jfc` hoặc Java Recording API. Không bảo đảm mọi recording có mọi event.

### 6.2. Đọc file

~~~bash
jfr summary /tmp/system-compare.jfr
jfr print --events jdk.CPULoad,jdk.PhysicalMemory /tmp/system-compare.jfr
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary /tmp/system-compare.jfr
jfr metadata --events CPULoad /tmp/system-compare.jfr
~~~

`jfr print` hỗ trợ `--json`, `--xml` và `--exact`. Khi kết hợp lọc theo category và event, theo tài liệu Oracle các bộ lọc có thể được kết hợp theo **union**, không phải phép intersection.

Nếu file thiếu event, kiểm tra **event enabled, platform và thời lượng**; đừng tự gán giá trị 0.

### 6.3. Heap snapshot từ cùng JVM

~~~bash
jcmd 12345 GC.heap_info
~~~

Đây là thông tin **Java heap**, không phải process RSS. Oracle `jcmd` ghi impact của `GC.heap_info` là **Medium**; cần cân nhắc tần suất trong production.

Không dùng cờ JFR thương mại legacy của các thế hệ JDK cũ; `jcmd JFR.start` và các API/launcher options hiện đại là lựa chọn phù hợp.

## 7. Linux: lấy OS metrics trên đúng PID

Ví dụ PID `12345` vẫn đang chạy:

~~~bash
pid=12345
date -u '+%Y-%m-%dT%H:%M:%SZ'

# Process CPU, elapsed, RSS và virtual size:
ps -p "$pid" -o pid,etime,%cpu,rss,vsz,cmd

# Dữ liệu theo cửa sổ một giây từ sysstat khi có:
pidstat -u -r -p "$pid" 1 5

# Memory và thread count theo process:
grep -E 'VmRSS|VmSize|VmHWM|Threads' "/proc/$pid/status"

# RAM toàn hệ thống:
free -h
~~~

- `ps %cpu` có cách tính riêng và **không nhất thiết** là CPU của đúng một giây gần nhất.
- `pidstat` cho các mẫu theo interval, cần đọc cách định nghĩa `%CPU` của bản sysstat.
- `rss` và `vsz` thông thường là KiB; `vsz` là virtual memory, **không phải resident**.
- Linux kernel ghi rõ `VmRSS` trong `/proc/PID/status` chỉ là ước lượng có thể lệch. Với phân tích chi tiết hơn, xem `/proc/PID/smaps_rollup` (nếu có quyền), nhưng chi phí đọc cao hơn.
- `free -h` là số liệu **host**, có page cache/buffers và không tương đương JVM RSS.

### Thread CPU

~~~bash
pidstat -t -u -p "$pid" 1 5
ps -L -p "$pid" -o pid,tid,pcpu,comm
~~~

JFR `jdk.ThreadCPULoad` có thể giúp nhìn theo Java thread nếu event được bật; OS TID/CPU thread khác tên Java thread. Với **virtual threads (Java 21+)**, không giả định mọi virtual thread có một OS thread riêng.

## 8. Windows PowerShell và macOS Terminal

### 8.1. Windows

~~~powershell
$javaPid = 12345
Get-Date -Format o
Get-Process -Id $javaPid |
    Select-Object Id, ProcessName, CPU, WorkingSet64, PrivateMemorySize64

# Ví dụ performance counter trên Windows tiếng Anh:
Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples 5
~~~

`Get-Process.CPU` là **số giây CPU tích lũy**, không phải %CPU tức thời. `WorkingSet64` là bytes đang resident theo Windows; `PrivateMemorySize64` đo điều khác nữa, không được dùng thay Java heap used.

`Get-Counter` có tên counters được **địa phương hóa**: ví dụ tên tiếng Anh có thể không tồn tại trên Windows ngôn ngữ khác. Dùng `Get-Counter -ListSet *` để tìm tên thực tế.

**Chú ý:** `$PID` là biến tự động biểu thị PID **PowerShell hiện tại**, không phải JVM cần quan sát. Dùng biến riêng `$javaPid`.

### 8.2. macOS

~~~bash
pid=12345
date -u '+%Y-%m-%dT%H:%M:%SZ'
ps -p "$pid" -o pid,etime,%cpu,rss,vsz,command
top -l 1
vm_stat
~~~

MacOS `ps` có các khác biệt so với GNU/Linux; `vm_stat` thường báo **page count**, phải biết page size trước khi tính bytes. `top -l 1` là snapshot, không tự trùng interval với JFR.

## 9. Container/cgroup tạo thêm một phạm vi đo

Trong container, phân biệt **host**, **cgroup/container**, **JVM process**. Một cgroup có thể có nhiều processes. JFR/MXBean có thể quan sát phạm vi không trùng dashboard theo JVM vendor, JDK version và container policy.

Trên **Linux cgroup v2**, các file thường gặp tại mount cgroup tương ứng là:

~~~bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.events
~~~

| File/counter | Cách hiểu |
| --- | --- |
| `cpu.max` | Quota và period CPU của cgroup |
| `cpu.stat usage_usec` | CPU time tích lũy của cgroup, microseconds |
| `cpu.stat nr_throttled` / `throttled_usec` | Số lần/thời gian throttle khi có cung cấp |
| `memory.current` | Current memory usage bytes của **toàn cgroup** |
| `memory.max` | Memory limit; `max` có thể nghĩa không giới hạn tại cấp đó |
| `memory.events oom/oom_kill` | Kernel memory events, khác Java heap exception |

Đường dẫn `/sys/fs/cgroup` chỉ là ví dụ. Dùng `/proc/PID/cgroup` và mount info để tìm **đúng cgroup của JVM**; trên cgroup v1 các đường dẫn khác.

Một JVM có heap chưa đầy vẫn có thể bị **OOMKilled** bởi cgroup vì native memory, stacks, page cache, mmap và process khác. Kernel kill process không đồng nghĩa có `OutOfMemoryError` của Java heap.

## 10. Chương trình Java 17+ minh họa đối chiếu hai nguồn

Ví dụ tạo JFR recording **3,5 giây**, bật `jdk.CPULoad`/`jdk.PhysicalMemory`, lấy số MXBean, đọc events từ file tạm. Kết quả dùng **boolean kiểm tra kiểu/phạm vi**, không in CPU và RAM thật thành số cố định.

**File: `JfrSystemComparisonDemo.java`**

~~~java
import java.lang.management.ManagementFactory;
import com.sun.management.OperatingSystemMXBean;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrSystemComparisonDemo {
    public static void main(String[] args) throws Exception {
        OperatingSystemMXBean os =
                ManagementFactory.getPlatformMXBean(OperatingSystemMXBean.class);
        if (os == null) {
            System.out.println("extendedOsBean=UNAVAILABLE");
            return;
        }

        Path file = Files.createTempFile("jfr-os-reconcile-", ".jfr");
        try {
            long beforeCpuNs = os.getProcessCpuTime();
            long beforeWallNs = System.nanoTime();
            try (Recording recording = new Recording()) {
                recording.enable("jdk.CPULoad")
                        .withPeriod(Duration.ofMillis(500));
                recording.enable("jdk.PhysicalMemory")
                        .withPeriod(Duration.ofMillis(500));
                recording.setToDisk(true);
                recording.start();
                Thread.sleep(3500);
                recording.stop();
                recording.dump(file);
            }
            long afterWallNs = System.nanoTime();
            long afterCpuNs = os.getProcessCpuTime();
            List<RecordedEvent> events = RecordingFile.readAllEvents(file);

            long cpuEvents = events.stream().filter(e ->
                    e.getEventType().getName().equals("jdk.CPULoad")).count();
            long memoryEvents = events.stream().filter(e ->
                    e.getEventType().getName().equals("jdk.PhysicalMemory"))
                    .count();

            System.out.println("pidPositive=" + (ProcessHandle.current().pid() > 0));
            System.out.println("wallTimePositive=" + (afterWallNs > beforeWallNs));
            System.out.println("cpuTimeSupported=" +
                    (beforeCpuNs >= 0 && afterCpuNs >= beforeCpuNs));
            System.out.println("processCpuLoadValidOrUnavailable=" +
                    isLoadValidOrUnavailable(os.getProcessCpuLoad()));
            System.out.println("systemCpuLoadValidOrUnavailable=" +
                    isLoadValidOrUnavailable(os.getCpuLoad()));
            System.out.println("jfrCpuEventsPresent=" + (cpuEvents > 0));
            System.out.println("jfrPhysicalMemoryEventsPresent=" +
                    (memoryEvents > 0));

            for (RecordedEvent event : events) {
                if (event.getEventType().getName().equals("jdk.CPULoad")) {
                    float user = event.getFloat("jvmUser");
                    float system = event.getFloat("jvmSystem");
                    float machine = event.getFloat("machineTotal");
                    System.out.println("jfrCpuFieldsValid=" +
                            (validLoad(user) && validLoad(system)
                                    && validLoad(machine)));
                    break;
                }
            }
            for (RecordedEvent event : events) {
                if (event.getEventType().getName().equals("jdk.PhysicalMemory")) {
                    long total = event.getLong("totalSize");
                    long used = event.getLong("usedSize");
                    System.out.println("jfrPhysicalMemoryValid=" +
                            (total > 0 && used >= 0 && used <= total));
                    break;
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static boolean validLoad(double fraction) {
        return !Double.isNaN(fraction) && fraction >= 0 && fraction <= 1;
    }

    private static boolean isLoadValidOrUnavailable(double fraction) {
        return fraction < 0 || validLoad(fraction);
    }
}
~~~

**Biên dịch và chạy** bằng JDK 17+ có `jdk.jfr` và `jdk.management`:

~~~bash
javac --release 17 -encoding UTF-8 JfrSystemComparisonDemo.java
java JfrSystemComparisonDemo
~~~

**Stdout trong một lần kiểm thử trên Windows/JDK 24 (exit 0):**

~~~text
pidPositive=true
wallTimePositive=true
cpuTimeSupported=true
processCpuLoadValidOrUnavailable=true
systemCpuLoadValidOrUnavailable=true
jfrCpuEventsPresent=true
jfrPhysicalMemoryEventsPresent=true
jfrCpuFieldsValid=true
jfrPhysicalMemoryValid=true
~~~

Giải thích:

- `pidPositive` kiểm tra PID JVM dương; trong container PID có thể khác host.
- `wallTimePositive` chỉ khẳng định monotonic time tăng, không bắt buộc đúng 3500 ms.
- `cpuTimeSupported` kiểm tra API có CPU time hợp lệ; platform khác có thể trả `-1`.
- Hai dòng `*CpuLoadValidOrUnavailable` chấp nhận giá trị `[0,1]` hoặc giá trị âm khi không khả dụng.
- Hai dòng `*EventsPresent` xác nhận periodic events **thực sự xuất hiện ở lần chạy này**. Recording quá ngắn, JDK khác hoặc event bị tắt có thể không có.
- `jfrCpuFieldsValid` kiểm tra 3 fields CPU float fractions hợp lệ; không có ý định đo benchmark.
- `jfrPhysicalMemoryValid` kiểm tra các field memory ở đơn vị **bytes hệ thống**, không phải JVM RSS.

**Giới hạn quan trọng:** những boolean `true` trong stdout là **quan sát đã kiểm thử trên JDK 24**, không phải kết quả được bảo đảm trên mọi JVM. Chương trình không lấy số CPU/RAM thật làm output cố định. Nếu đọc recording rất lớn, `readAllEvents` sẽ tốn RAM; dùng `RecordingFile` đọc tuần tự hoặc `RecordingStream` để xử lý live. `RecordingStream.start()` chặn thread gọi, còn `startAsync()` chạy trên thread riêng; cần có cơ chế đóng hợp lệ.

## 11. Kịch bản chẩn đoán với cả hai nguồn

### 11.1. JVM process CPU cao và p99 latency tăng

1. Xác nhận đúng PID/process CPU từ OS và JFR, cùng interval.
2. Ghép thời điểm `jdk.CPULoad` với `jdk.GarbageCollection`, `jdk.GCHeapSummary`, thread metrics, request latency.
3. Nếu GC pause/duration tăng, xem logs và heap/allocation rates; nếu không, tìm busy-loop, contention, JIT/compiler, workload CPU-heavy hoặc process khác.
4. Với container, kiểm tra `cpu.stat` throttling: p99 có thể tăng khi quota không đủ dù process không còn khả năng dùng thêm CPU.

**Không mặc định CPU cao là do GC.**

### 11.2. RSS tăng nhưng heap ổn định

1. Xem là RSS hay virtual size (`VmSize`) và thời điểm có đúng không.
2. Xem direct buffers, native allocations, metaspace, code cache, thread stacks, mmap, JNI/shared pages.
3. Sử dụng NMT nếu đã bật, OS memory maps và nhiều samples.
4. Không gọi ngay phần `RSS - heapUsed` là “native memory leak”.

### 11.3. Java heap thấp nhưng pod bị OOMKilled

1. Đọc `memory.current`, `memory.max`, `memory.events` và restart reason.
2. Kiểm tra non-heap, off-heap, page cache và các processes chung cgroup.
3. Phân biệt **kernel OOMKilled** với **Java heap OutOfMemoryError**: kernel kill có thể không để lại Java stack trace hoặc JFR dump cuối.
4. Không tăng `-Xmx` vô điều kiện, vì có thể làm cgroup memory pressure nặng hơn.

## 12. Lỗi hiểu sai hay gặp

| Hiểu sai | Cách hiểu đúng |
| --- | --- |
| “JFR CPU 20% và OS 160% phải có lỗi.” | Kiểm tra per-core vs normalized CPU, core count, window |
| “`getProcessCpuTime()` là tải CPU tức thời.” | Counter nanoseconds tích lũy, phải tính delta |
| “`jdk.PhysicalMemory.usedSize` là RSS Java.” | Nó mô tả memory của môi trường, không riêng JVM |
| “Heap used bằng process RSS.” | RSS gồm native memory, thread stacks, code/mappings |
| “Thiếu JFR event nghĩa là số liệu bằng 0.” | Có thể chưa bật hoặc không có event trong window |
| “`ps vsz` là RAM thực tế đã dùng.” | Đó là virtual address space, khác resident |
| “Cgroup `memory.current` là của riêng một PID.” | Cgroup có thể có nhiều processes |
| “CPU time 1.6 giây trong 1 giây wall là vô lý.” | Multicore process có thể dùng CPU song song |
| “Kernel OOMKilled chính là Java OutOfMemoryError.” | Hai tầng giới hạn và cách thất bại khác |
| “Mọi timestamp cùng giây là cùng mẫu.” | Sampling windows và JFR batching khác nhau |
| “`VmRSS` là phép đo chính xác tuyệt đối.” | Linux kernel ghi rõ là ước lượng |
| “Có file `.jfr` thì không cần bảo vệ.” | Có thể chứa stack traces, file paths, class/thread names nhạy cảm |

## 13. Checklist thực hành và bài tập

**Checklist:**

- [ ] Đã chọn **đúng JVM PID** và biết JDK version, OS, VM/container.
- [ ] Xác định host/process/cgroup/thread/heap trước khi so các metric.
- [ ] Đã kiểm tra JFR events hiện diện bằng `jfr summary`/`jfr metadata`.
- [ ] Thu JFR và OS samples trên **cùng khoảng thời gian**.
- [ ] Chuẩn hóa UTC, period, fraction/percent, bytes/KiB/MiB, nanoseconds/seconds.
- [ ] Dùng delta cho CPU time và cgroup counters; không coi counter là gauge.
- [ ] Không so heap used/RSS/physical RAM như cùng một đại lượng.
- [ ] Với container, kiểm tra quota, throttling, memory events và cgroup thật.
- [ ] Coi missing/unavailable là **thiếu số liệu**, không mặc định bằng 0.
- [ ] Đánh giá overhead và quyền truy cập `jcmd`, JFR, `/proc` và file `.jfr`.
- [ ] Lấy nhiều samples trước khi kết luận về GC, leak hoặc throttling.

**Bài tập:**

1. Giải thích CPU 160% per-core tương ứng khoảng 20% normalized ở hệ 8 CPUs khi process dùng 1.6 core equivalents.
2. Viết chương trình lấy delta `getProcessCpuTime()`/`System.nanoTime()`. Vì sao ratio có thể lớn hơn 1?
3. Chạy `JfrSystemComparisonDemo` trên JDK 17+. Nếu thiếu event `jdk.CPULoad`, bạn sẽ kiểm tra điều gì?
4. Chạy `pidstat -u -r -p PID 1 5` (Linux) và lấy JFR CPU trong cùng giai đoạn. Những khác biệt window cần chú ý?
5. Phân biệt `Get-Process.CPU`, `WorkingSet64` và `getProcessCpuLoad()` trên Windows.
6. Heap 500 MiB, RSS 900 MiB: vì sao chưa đủ kết luận memory leak?
7. Giải thích `jdk.GCHeapSummary` khác `jdk.PhysicalMemory` theo scope và thời điểm.
8. Trên container, `memory.current` gần `memory.max` trong khi heap thấp: cần điều tra gì?
9. Lập cấu trúc dữ liệu với `timestampUTC, source, metricName, scope, unit, value, interval, pid, jdkVersion` để so JFR/OS.
10. So sánh câu hỏi được trả lời bởi `JFR.check` (recording đang chạy) và `jfr summary` (file đã lưu).

## 14. Tài liệu hiện hành

- [Oracle Java SE 25 – OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html): CPU load/time, memory và các phương thức deprecated từ Java 14.
- [Oracle JDK 25 – jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `GC.heap_info`.
- [Oracle JDK 25 – jfr](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `summary`, `print`, `metadata`, JSON output.
- [Oracle Java SE 25 – JFR settings](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): periodic events và cấu hình period.
- [Oracle Java SE 25 – RecordingFile](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc `RecordedEvent`.
- [OpenJDK JFR metadata](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/jfr/metadata/metadata.xml): fields của `jdk.CPULoad` và `jdk.PhysicalMemory`.
- [Linux kernel – proc filesystem](https://docs.kernel.org/filesystems/proc.html): `VmRSS`, `VmSize`, process status.
- [Microsoft Learn – Get-Counter](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.diagnostics/get-counter?view=powershell-5.1): Windows counters và sampling.
- [OpenJDK JEP 349 – JFR Event Streaming](https://openjdk.org/jeps/349): streaming API từ Java 14.

**Ghi nhớ:** JFR cho **ngữ cảnh JVM**, OS tools cho **phạm vi process/host**, cgroup cho **quota và consumption của container**. Đối chiếu đáng tin đòi hỏi **đúng PID, đúng scope, đúng đơn vị và thời gian**. `jdk.CPULoad` khác per-core `%CPU` khi chưa quy đổi; `jdk.PhysicalMemory` không phải JVM RSS và Java heap không bằng process resident memory.