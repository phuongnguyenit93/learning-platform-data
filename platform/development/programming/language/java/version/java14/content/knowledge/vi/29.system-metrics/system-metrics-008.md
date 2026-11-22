# Ảnh hưởng của giới hạn tài nguyên trong container đến số liệu hệ thống của JVM

## 1. Mục tiêu và bối cảnh

Khi Java chạy trong **Docker, Kubernetes hoặc Linux container**, các số liệu CPU và RAM nhìn thấy từ **host** không nhất thiết là tài nguyên mà **tiến trình JVM** được phép sử dụng. Linux có thể giới hạn container thông qua **cgroups**, CPU affinity/cpuset và cấu hình của container runtime. JVM HotSpot hiện đại có **container awareness** để xem xét những giới hạn này khi lựa chọn kích thước Java heap, số processor khả dụng, GC workers và các quyết định tự động khác.

Bài học thuộc chủ đề cha **Số liệu hệ thống**, tập trung vào **ảnh hưởng của giới hạn tài nguyên trong container** đối với các metric và hành vi quan sát được, chứ không chỉ là hướng dẫn chạy một container.

Sau bài học, bạn có thể:

1. Phân biệt **host CPU/RAM**, **container request/limit**, **cgroup quota/usage** và **số liệu JVM**.
2. Hiểu ý nghĩa của `Runtime.availableProcessors()`, `Runtime.maxMemory()` và `MemoryMXBean` khi đặt CPU/memory limits.
3. Giải thích công dụng của `-XX:+UseContainerSupport`, `-XX:ActiveProcessorCount`, `-Xmx` và `-XX:MaxRAMPercentage`.
4. Đọc các chỉ số cgroups v2 như `cpu.max`, `cpu.stat`, `memory.max`, `memory.current` và `memory.events`.
5. Phân biệt **CPU throttling**, **Java heap OutOfMemoryError**, **native memory pressure** và **OOMKilled từ Linux/cgroup**.
6. Biên dịch/chạy một chương trình **Java 17+ độc lập** in CPU/heap/cgroup metrics, có chế độ tự kiểm tra với stdout chính xác.
7. Lập phương án quan sát bằng Docker/Kubernetes, `-XshowSettings:system`, `-Xlog:os+container=trace` và Native Memory Tracking mà không kết luận quá mức từ một nguồn.

**Kiến thức hiện hành:** HotSpot đã có container awareness trước Java 14; hỗ trợ **cgroups v2** được hoàn thiện ở các release mới hơn (theo tài liệu Kubernetes, OpenJDK/HotSpot từ JDK 15 trở lên, cùng các bản backport tương ứng). Bài dùng **JDK 17 trở lên với bản vá hiện hành**, không đồng nhất Java 14 ban đầu với JDK hiện đại và không khuyến nghị cơ chế CPU-shares legacy.

## 2. Ba tầng tài nguyên cần tách biệt

Giả sử một máy Linux có **32 logical CPUs, 64 GiB RAM**. Một JVM trên đó chạy trong container có **CPU limit 2 cores và memory limit 1 GiB**.

```text
Host (32 logical CPUs, 64 GiB RAM)
              |
              v
 Container runtime / cgroups
    CPU quota: tương đương 2 cores
    Memory hard limit: 1 GiB
              |
              v
       Java HotSpot JVM
       /               \
availableProcessors()  max Java heap (Xmx/ergonomics)
       |                |
GC/ForkJoin/executors  heap + metaspace + native memory
       |                |
       v                v
throughput / latency   GC / memory pressure / OOM
```

Con số trên là **ví dụ cấu hình**, không phải kết quả đo. `Runtime.availableProcessors()` có thể phản ánh quota/cpuset và cờ JVM; nó không nhất thiết bằng số CPU của host và cũng không biểu diễn được một quota lẻ dưới dạng số thực.

| Tầng | Ý nghĩa | Nguồn thường dùng |
| --- | --- | --- |
| **Host** | Toàn bộ CPU/RAM vật lý hoặc VM | OS inventory, host monitoring |
| **Container/cgroup** | Resource limit và usage của nhóm tiến trình | Docker/Kubernetes, Linux cgroups |
| **JVM** | CPU count/heap sizing/GC mà JVM đang nhận diện | `Runtime`, `MemoryMXBean`, JVM flags |
| **Ứng dụng** | Thông lượng, độ trễ, lỗi và timeout thực tế | Metrics nghiệp vụ, tracing, load generator |

**Không coi hai metric có cùng đơn vị là cùng bản chất.** `memory.max` là memory hard limit cấp cgroup; `Runtime.maxMemory()` là giới hạn **Java heap**; `memory.current` là usage cấp cgroup; `heap used` là dữ liệu JVM. Chúng hoàn toàn có thể khác nhau mà không có lỗi nào.

## 3. Linux cgroups v1 và v2

Linux **control groups (cgroups)** tổ chức và quản lý tài nguyên cho nhóm task/process. Những hệ thống Linux hiện đại thường sử dụng **cgroups v2**, nhưng vẫn có máy sử dụng **v1**. Các file và đường dẫn giữa hai phiên bản không giống nhau. Đừng viết ứng dụng chỉ đọc một file v1 rồi kết luận JVM không bị giới hạn khi triển khai trên v2.

Các file thường gặp **trong một cgroup v2 được expose tới container**:

| File | Cách đọc | Điều cần tránh suy diễn |
| --- | --- | --- |
| `cpu.max` | Hai giá trị quota và period, hoặc quota `max` | Không phải số “thread được phép tạo” |
| `cpu.stat` | CPU usage và thống kê throttling | Counter tích lũy, không phải request latency |
| `cpu.weight` | Trọng số tương đối khi tranh chấp CPU | Không phải hard limit |
| `cpuset.cpus.effective` | Tập CPU khả dụng theo cpuset | Không phải % CPU usage |
| `memory.max` | Hard memory limit theo bytes, hoặc `max` | Không phải max Java heap |
| `memory.current` | Memory đang được cgroup/descendants sử dụng | Không chỉ heap Java |
| `memory.high` | Ngưỡng pressure/reclaim/throttling | Không đồng nghĩa `memory.max` |
| `memory.events` | Counter `high`, `max`, `oom`, `oom_kill` | Cần lấy delta theo thời gian |
| `memory.swap.max` | Giới hạn swap riêng theo cgroups v2 | Không áp dụng cùng cách trên mọi kernel |
| `pids.max` | Giới hạn số task/process/thread | Có thể làm JVM không tạo được thread |

Ví dụ `cpu.max`:

```text
150000 100000
```

Nghĩa là tối đa **150.000 microseconds CPU time trên mỗi chu kỳ 100.000 microseconds** theo cơ chế quota: trung bình khoảng **1,5 CPU**. Đây là **CPU bandwidth**, không phải một “CPU vật lý rưỡi” và không đảm bảo application threads không bị trì hoãn.

Nếu file chứa:

```text
max 100000
```

thì **tại cgroup này** không có hard CPU quota. Cgroup cha, cpuset/affinity, VM hoặc chính sách host vẫn có thể giới hạn tài nguyên.

Ví dụ `memory.max`:

```text
536870912
```

Giá trị tương đương **512 MiB**, không phải 512 MB hệ thập phân. Giá trị `max` nghĩa là tại file đó không có giới hạn memory hữu hạn; **không** đảm bảo tổng hệ thống vô hạn.

**Đừng ghi trực tiếp vào những file cgroup trong môi trường production chỉ để thực hành.** Thay limit bằng Docker/Kubernetes/admin API được phép. Đọc số liệu theo **cgroup thực của tiến trình** và tính đến cgroup cha; không tự tin rằng `/sys/fs/cgroup` luôn là đúng vị trí mount trên mọi host/container.

## 4. CPU requests và CPU limits trong Kubernetes

Trong một container của Kubernetes, ví dụ:

```yaml
resources:
  requests:
    cpu: "250m"
    memory: "256Mi"
  limits:
    cpu: "1"
    memory: "512Mi"
```

Đây là **một fragment của container spec**, không phải Pod manifest hoàn chỉnh.

- `requests.cpu=250m`: tương đương yêu cầu 0,25 CPU cho scheduling và chính sách chia sẻ tài nguyên; **không phải giới hạn cứng** CPU.
- `limits.cpu=1`: thông thường được áp dụng bằng CPU quota để giới hạn ngân sách CPU, có thể gây **throttling** nếu workload dùng hết trong kỳ.
- `requests.memory=256Mi`: scheduler sử dụng để quyết định vị trí đặt Pod, **không tự đặt Java heap đúng 256 MiB**.
- `limits.memory=512Mi`: thường được kernel áp dụng bằng **memory cgroup hard limit**; khi vượt và không reclaim được, container có thể bị OOMKilled.
- Giá trị thực có thể đến từ defaults hoặc chính sách namespace; xem **Pod spec đang được áp dụng**, không chỉ YAML nguồn.

**Giới hạn CPU khác với số runnable threads.** Một Pod được giới hạn 1 CPU vẫn có thể có hàng chục Java threads, nhưng tổng thời gian CPU có thể bị hạn chế. CPU limit không chặn từng thread ngay ở lúc tạo; `pids.max` lại là cơ chế riêng có thể ảnh hưởng tạo task/thread.

**Một khác biệt lịch sử quan trọng:** JDK 19 HotSpot ngừng dùng **CPU shares** để tính active processor count theo mặc định, vì shares là trọng số tương đối chứ không phải quota. Một số JDK cũ hoặc bản backport/vendor có cách tính khác. Không dùng flags khôi phục hành vi shares đã deprecated làm lời khuyên mới; hãy xác nhận JDK hiện hành và các giá trị CPU thực.

## 5. JVM HotSpot nhận biết container như thế nào?

Với HotSpot trên Linux được hỗ trợ, tùy chọn:

```text
-XX:+UseContainerSupport
```

thường **được bật sẵn theo mặc định**. JVM dùng thông tin container/OS để quyết định những giá trị ergonomics phù hợp, ví dụ active processor count và memory dành cho việc chọn heap. Trong điều kiện thích hợp, một JVM đặt trong Pod nhỏ không còn phải coi toàn bộ host RAM/CPU là ngân sách riêng của mình.

Cờ ngược:

```text
-XX:-UseContainerSupport
```

**không xóa giới hạn kernel.** Nó chỉ tắt việc HotSpot dùng container information trong những quyết định tương ứng. Kết quả có thể là JVM tính heap/threads dựa vào host hoặc dữ liệu không phù hợp, làm tăng nguy cơ bị throttling hoặc OOMKilled.

**Không khuyến nghị vô hiệu hóa UseContainerSupport ở production** chỉ vì muốn JVM nhìn thấy “nhiều CPU/RAM hơn”. Nếu con số không như mong đợi, kiểm tra JDK vendor/build/patch, cgroups v1/v2, namespace, cấu hình container, các JVM options và logs.

### Công cụ kiểm tra hiện hành

Trên JVM phù hợp:

```bash
java -XshowSettings:system -version
```

`-XshowSettings:system` là công cụ Java launcher để in thông tin system/container mà JVM thấy trên Linux, khi nền tảng hỗ trợ. Output có thể khác giữa JDK build; đừng hardcode một định dạng duy nhất.

Để điều tra sâu:

```bash
java -Xlog:os+container=trace -version
```

`trace` rất chi tiết; không bật vô hạn trên production mà không giới hạn log volume. Nếu không thấy container metrics, điều đó **chưa chứng minh container không có cgroup limit**: có thể do cgroup mount, runtime permissions, JDK cũ/patch hoặc không hỗ trợ trên OS hiện tại.

**Giới hạn tính di động:** Những `-XX` flags trên thuộc HotSpot; các JVM implementation khác có thể cung cấp tùy chọn/semantics khác. Container awareness được tài liệu Oracle mô tả cho **Linux**; không suy từ tài liệu Linux ra tính năng tương tự trên macOS/Windows host.

## 6. Runtime.availableProcessors(): nên hiểu là gì?

API chuẩn:

```java
int cpuCount = Runtime.getRuntime().availableProcessors();
```

Giá trị là số processor mà **JVM xem là khả dụng cho nó**, luôn ≥1. Theo Java API, con số này **có thể thay đổi trong một lần chạy JVM**; không tự coi nó là host core count cố định.

Các tác động:

- JVM có thể dùng CPU count cho **GC worker sizing**, JIT/parallel task defaults và những lựa chọn thread concurrency.
- Các thư viện ứng dụng có thể lấy CPU count để cấu hình executor hoặc `ForkJoinPool`.
- CPU quota **1,5 core** là băng thông CPU, còn `availableProcessors()` trả về **int**, không phải chính xác 1,5.
- Số CPU không cho biết **% CPU load**, mức throttling, CPU sử dụng tức thời hay thời gian chờ I/O.
- CPU count nhỏ không đồng nghĩa ứng dụng chỉ được tạo chừng đó Java threads.

### Override bằng ActiveProcessorCount

Với HotSpot, có thể dùng:

```text
-XX:ActiveProcessorCount=2
```

Theo Oracle, option này **override số CPU** mà JVM dùng trong các quyết định sizing như GC/ForkJoin, kể cả khi `UseContainerSupport` bị tắt. Nó có thể hữu ích khi automatic detection chưa phù hợp, hoặc trong benchmark cần kiểm soát số CPU nhận thức.

**Nó không cấp thêm CPU quota cho container.** Nếu container chỉ có ngân sách 0,5 CPU, đặt `ActiveProcessorCount=8` chỉ tạo ảo giác nhiều processor ở tầng runtime sizing, không nới giới hạn kernel. Quá nhiều GC/application threads có thể làm contention hoặc throttling tệ hơn.

Không dùng option này như phép sửa mặc định cho mọi vấn đề hiệu năng. Đo throughput, latency và throttling sau khi thay; sizing tốt còn phụ thuộc workload CPU-bound hay I/O-bound.

## 7. Giới hạn RAM container và Java heap là hai việc khác nhau

Những API/cờ thường được xem:

| Chỉ số/cờ | Phạm vi đúng |
| --- | --- |
| `Runtime.maxMemory()` | Max **Java heap** mà JVM có thể cố sử dụng |
| `Runtime.totalMemory()` | Heap memory hiện được JVM cấp phát/committed theo API |
| `Runtime.freeMemory()` | Phần free trong heap đã cấp phát theo API |
| `MemoryMXBean.getHeapMemoryUsage()` | Sử dụng/committed/max của heap |
| `MemoryMXBean.getNonHeapMemoryUsage()` | Những vùng **non-heap do JVM quản lý** |
| `-Xmx256m` | Max Java heap xấp xỉ 256 MiB |
| `-Xms64m` | Initial Java heap xấp xỉ 64 MiB |
| `-XX:MaxRAMPercentage=60` | Định hướng max heap theo % RAM JVM dùng cho ergonomics |
| `memory.max` (cgroups v2) | Hard memory limit của **cgroup**, không riêng Java heap |
| `memory.current` (cgroups v2) | Memory hiện đang hạch toán cho **cgroup và descendants** |

Nếu **container memory limit là 512 MiB** và đặt **`-Xmx256m`**, điều đó không tạo “256 MiB RAM còn trống bảo đảm”. Tổng memory còn bị ảnh hưởng bởi:

- JVM metaspace, class metadata và code cache.
- Java/native thread stacks.
- GC metadata, JIT/compiler memory.
- Direct byte buffers, JNI và thư viện native.
- Memory-mapped files, shared libraries.
- Page cache, kernel accounting và process khác trong cùng cgroup.

`-Xmx` **chỉ giới hạn heap**, không phải total RSS hay cgroup usage. Heap used không bằng RSS; `memory.current` cũng không phải heap used.

### MaxRAMPercentage không giới hạn tổng RAM

Nếu chạy:

```text
-XX:MaxRAMPercentage=60
```

JVM dùng một tỷ lệ phần trăm của **RAM được xác định cho mục đích heap sizing**, còn chịu các điều chỉnh/rounding của ergonomics và các flags khác. Không suy rằng **JVM tổng thể** sẽ dùng tối đa 60% limit. Với container 512 MiB, phép tính lý thuyết `512 × 60% ≈ 307,2 MiB` chỉ là cách hình dung, **không phải một kết quả Runtime.maxMemory() bắt buộc chính xác**.

Với workload có nhiều direct buffers, threads, JNI hoặc metaspace, đặt heap sát memory limit có thể khiến container bị kill dù heap chưa đầy.

### Thay đổi limit khi tiến trình đang chạy

Một số quyết định như **max heap** đã được xác lập khi JVM khởi động; thay Pod/container memory limit trong lúc chạy **không cam kết** JVM lập tức co giãn max heap đúng với limit mới. Một số CPU-related metrics có thể thay đổi, nhưng không phải mọi executor đã được tạo sẽ tự điều chỉnh.

Khi điều chỉnh resources, hãy xác định khả năng cập nhật tại runtime của JVM, thư viện và orchestrator cụ thể; có thể cần **rollout/restart có kiểm soát** để được sizing dự kiến.

## 8. CPU throttling: vì sao throughput và p99 đổi khi giới hạn CPU?

Trong cgroups v2, `cpu.stat` có thể có:

```text
usage_usec 129000000
nr_periods 20000
nr_throttled 1600
throttled_usec 43000000
```

Đây là **số liệu minh họa**, không phải kết quả từ container của người học. Các counters có ý nghĩa theo kernel/cgroup; chúng **tích lũy** nên cần đo **delta** trong cửa sổ benchmark.

Giả sử CPU limit = 1 core nhưng JVM có nhiều runnable threads. Khi ứng dụng và các task nền dùng hết CPU budget trong một period:

- Runnable threads có thể bị **throttled**, phải chờ kỳ mới.
- Throughput requests/s có thể giảm.
- Tail latency p95/p99 có thể tăng dù không có GC pause dài.
- GC workers và JIT/background tasks phải chia sẻ CPU budget với application threads.
- Số thread nhiều hơn không tự tăng CPU bandwidth; còn có thể tăng context switching và contention.

**Không đồng nhất CPU throttling với GC pause.** Một request có thể chậm do quota, lock, network, database, hoặc queueing; muốn tìm nguyên nhân cần tương quan thời gian từ tracing/JFR/GC log và OS metrics.

Để đánh giá CPU throttling, lấy hai snapshot `cpu.stat` trước/sau khi chạy cùng tải; tính delta của `nr_throttled` và `throttled_usec`. Một lần đọc không cho biết thay đổi trong test hiện tại.

## 9. Phân biệt OutOfMemoryError với container OOMKilled

### A. Java heap OutOfMemoryError

Một ứng dụng có thể nhận:

```text
java.lang.OutOfMemoryError: Java heap space
```

Điều này cho thấy JVM không đáp ứng được yêu cầu cấp phát trong heap theo giới hạn/chính sách hiện tại. Nó **khác** với việc kernel kill do container memory cgroup. JVM có thể ghi stack trace, GC log hoặc heap dump nếu cấu hình phù hợp; không nên cho rằng luôn còn đủ tài nguyên để xử lý/tiếp tục an toàn.

**Kiểm tra:** heap used/max, GC activity, object retention, heap dump và khả năng memory leak. Không tăng `-Xmx` tự động nếu Pod đang gần memory hard limit.

### B. Native memory hoặc pids limit

Ví dụ:

```text
java.lang.OutOfMemoryError: unable to create native thread
```

Có thể liên quan native memory/thread stack, `pids.max`, OS task limits hoặc thread pool không được giới hạn; không chứng minh Java heap đã đầy.

Trường hợp direct buffer/memory-mapped files/JNI cũng có nguồn lỗi và giới hạn riêng. Khi chẩn đoán, hãy kiểm tra vùng non-heap/native, thread count, NMT và cgroup pids thay vì chỉ xem `-Xmx`.

### C. OOM kill do kernel/cgroup

Khi `memory.max` bị chạm và kernel không reclaim đủ, **OOM killer** có thể gửi `SIGKILL` tới một tiến trình trong cgroup. Kubernetes có thể báo termination reason **`OOMKilled`**.

Điểm quan trọng:

- Có thể **không có** `java.lang.OutOfMemoryError` hoặc Java stack trace.
- **SIGKILL không cho JVM chạy shutdown hooks** như một lối thoát bình thường.
- Exit status **137** thường tương ứng SIGKILL, nhưng **không tự chứng minh OOM**; cần termination reason, `memory.events` và logs.
- Memory cgroup có thể chạm giới hạn khi heap used còn thấp, do native memory/page cache/các process khác.

| Dấu hiệu | Giả thuyết | Nơi xác minh |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Heap vượt khả năng cấp phát | GC logs, heap usage/dump |
| `unable to create native thread` | Thread task quota / native memory | `pids.max`, pool/thread count |
| `Reason: OOMKilled` | Cgroup/kernel OOM termination | Pod status, `memory.events` |
| Exit `137` nhưng không có OOM reason | SIGKILL từ một nguyên nhân khác | Container termination logs, OS |
| Heap không cao, RSS/memory.current cao | Non-heap/native/cache | NMT, OS memory, process inventory |

**Quy tắc:** Không gán mọi restart là “Java heap OOM”, và không coi tăng heap là cách sửa khi vấn đề thật nằm ở **tổng giới hạn memory container**.

## 10. Chương trình Java 17+ đầy đủ để đọc số liệu JVM và cgroups v2

Tạo file **`ContainerLimitsDemo.java`**. Đây là chương trình **chỉ đọc** số liệu, không chủ động stress CPU/RAM hoặc gây OOM:

- `--check`: ba dòng xác minh cơ bản, có **stdout chính xác** trên JDK 17+.
- Không có tham số: in CPU count, heap/non-heap usage và một số file cgroup v2 **nếu chúng được expose tại mount path thông dụng**.
- Nếu không thấy file cgroup, in `unavailable`; nếu thiếu quyền đọc/lỗi I/O, in `unreadable`. Những giá trị này **không xác minh mọi hierarchy của container**.

```java
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ContainerLimitsDemo {
    private static final long MIB = 1024L * 1024L;
    private static final Path CGROUP_V2 =
            Path.of("/sys/fs/cgroup");

    private ContainerLimitsDemo() {
    }

    private static String readCgroupV2(String name) {
        Path file = CGROUP_V2.resolve(name);
        try {
            if (!Files.isRegularFile(file)) {
                return "unavailable";
            }
            String text = Files.readString(
                    file, StandardCharsets.UTF_8).strip();
            int newline = text.indexOf('\n');
            return newline < 0
                    ? text
                    : text.substring(0, newline).strip();
        } catch (IOException | SecurityException ex) {
            return "unreadable";
        }
    }

    private static String mib(long bytes) {
        return bytes < 0
                ? "unavailable"
                : Long.toString(bytes / MIB);
    }

    private static void showCgroup(String name) {
        System.out.println("cgroupV2." + name + "="
                + readCgroupV2(name));
    }

    public static void main(String[] args) {
        if (args.length > 1
                || (args.length == 1
                    && !"--check".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: ContainerLimitsDemo [--check]");
        }

        Runtime runtime = Runtime.getRuntime();
        int cpus = runtime.availableProcessors();
        long maxHeap = runtime.maxMemory();

        if (args.length == 1) {
            boolean cpusOk = cpus >= 1;
            boolean heapOk = maxHeap > 0;
            boolean versionOk =
                    Runtime.version().feature() >= 17;

            System.out.println(
                    "processorsPositive=" + cpusOk);
            System.out.println(
                    "maximumHeapPositive=" + heapOk);
            System.out.println(
                    "jdkAtLeast17=" + versionOk);

            if (!cpusOk || !heapOk || !versionOk) {
                throw new AssertionError(
                        "Unexpected JVM environment");
            }
            return;
        }

        MemoryMXBean bean =
                ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = bean.getHeapMemoryUsage();
        MemoryUsage nonHeap = bean.getNonHeapMemoryUsage();

        System.out.println(
                "javaMajor=" + Runtime.version().feature());
        System.out.println(
                "os=" + System.getProperty("os.name"));
        System.out.println("availableProcessors=" + cpus);
        System.out.println("runtimeMaxHeapMiB="
                + mib(maxHeap));
        System.out.println("heapUsedMiB="
                + mib(heap.getUsed()));
        System.out.println("heapCommittedMiB="
                + mib(heap.getCommitted()));
        System.out.println("nonHeapUsedMiB="
                + mib(nonHeap.getUsed()));

        showCgroup("cpu.max");
        showCgroup("cpuset.cpus.effective");
        showCgroup("memory.max");
        showCgroup("memory.current");
        showCgroup("memory.high");
        showCgroup("memory.swap.max");
    }
}
```

### Biên dịch và chạy

Với **JDK 17+**, tại thư mục chứa file:

```bash
javac --release 17 ContainerLimitsDemo.java
java ContainerLimitsDemo --check
java ContainerLimitsDemo
```

**Stdout chính xác của `--check` trên JDK 17+ bình thường:**

```text
processorsPositive=true
maximumHeapPositive=true
jdkAtLeast17=true
```

Giá trị này không phụ thuộc host CPU count, heap capacity, Docker hay cgroup version. Tuy nhiên **`--check` không xác minh container detection đã hoạt động**; nó chỉ kiểm tra ba bất biến cơ bản.

### Chế độ in metric thực tế

Khi chạy `java ContainerLimitsDemo`, cấu trúc output gồm các dòng:

```text
javaMajor=<phiên bản JDK>
os=<tên hệ điều hành>
availableProcessors=<số JVM xem là khả dụng>
runtimeMaxHeapMiB=<MiB hoặc trạng thái>
heapUsedMiB=<MiB hoặc trạng thái>
heapCommittedMiB=<MiB hoặc trạng thái>
nonHeapUsedMiB=<MiB hoặc trạng thái>
cgroupV2.cpu.max=<quota/period hoặc unavailable>
cgroupV2.cpuset.cpus.effective=<CPU list hoặc unavailable>
cgroupV2.memory.max=<bytes, max hoặc unavailable>
cgroupV2.memory.current=<bytes hoặc unavailable>
cgroupV2.memory.high=<bytes, max hoặc unavailable>
cgroupV2.memory.swap.max=<bytes, max hoặc unavailable>
```

Các đoạn `<...>` là **chú thích mô tả các trường có giá trị phụ thuộc môi trường**, không phải chuỗi stdout literal. Ví dụ **không gán số đo giả** khi không có container thật. Trên Windows/macOS các cgroup paths Linux thường không tồn tại, nên in `unavailable`.

**Giới hạn cố ý:** Reader trong demo chỉ truy cập `/sys/fs/cgroup`, không phân tích đầy đủ mountinfo/hierarchy, cgroup ancestors hay cgroups v1. HotSpot có thể tự nhận diện cgroup thông qua thông tin phức tạp hơn. Nếu reader in `unavailable`, **không kết luận “JVM không hỗ trợ container”**; đối chiếu với `-XshowSettings:system` và môi trường thực.

### Ý nghĩa từng số đo

- `runtimeMaxHeapMiB` từ `Runtime.maxMemory()`: max Java heap, không phải memory limit tổng container.
- `heapUsedMiB`/`heapCommittedMiB`: snapshot từ `MemoryMXBean`. Giá trị đổi theo allocation/GC và **không bằng RSS**.
- `nonHeapUsedMiB`: các vùng non-heap mà JVM management API báo cáo, **không bao phủ mọi native allocations**.
- `cpu.max`: quota/period của cgroup được expose; có thể còn cgroup cha chặt hơn.
- `cpuset.cpus.effective`: tập CPU hiệu lực ở cgroup; không phải số lượng request workers.
- `memory.max`: hard limit bytes hoặc `max`; `memory.current`: usage cấp cgroup, không chỉ heap JVM.
- `memory.high`: pressure/throttling threshold, không phải hard OOM cap; `memory.swap.max`: hạn mức swap theo cgroups v2.

## 11. Thử nghiệm Docker không gây OOM

Khi đã biên dịch `ContainerLimitsDemo.class` trên máy có Java 17+, một ví dụ cho **Bash/Linux** với Docker Engine được phép dùng:

```bash
docker run --rm \
  --cpus=2 --memory=512m \
  --mount type=bind,src="$(pwd)",dst=/work,readonly \
  -w /work \
  eclipse-temurin:21-jdk \
  java -Xms64m -Xmx256m -cp /work ContainerLimitsDemo
```

Image JDK cần được tải từ registry nếu chưa có; trong môi trường có chính sách bảo mật, dùng **image được tổ chức cho phép**, không tự coi image bên ngoài là đáng tin. Mount read-only giúp container **đọc class đã build**, không ghi sang thư mục nguồn.

Trên Docker Desktop, Linux container chạy trong VM; không đồng nhất cgroup số liệu ở trong VM với host macOS/Windows.

**Không suy ra stdout cố định** cho `availableProcessors` hoặc `heapMax`. Đối chiếu:

1. Resource flags do Docker nhận (`--cpus`, `--memory`).
2. Các file cgroup nếu được expose.
3. `Runtime.availableProcessors()`/`Runtime.maxMemory()` thật.
4. `java -XshowSettings:system -version` trong chính container.
5. Số liệu Docker/OS khi app chạy đủ lâu, thay vì chỉ một snapshot lúc khởi động.

Nếu thử `-Xmx128m` so với `-Xmx256m`, giữ **cùng CPU/memory limit** để nhận ra thay đổi heap sizing không tự thay kernel quota.

### Một phép kiểm chứng khác

Chạy trong cùng container với `-XX:ActiveProcessorCount` khác nhau:

```bash
java -XX:ActiveProcessorCount=1 -cp /work ContainerLimitsDemo
java -XX:ActiveProcessorCount=4 -cp /work ContainerLimitsDemo
```

Đây là các lệnh **chạy bên trong container**; nếu chạy ngoài và không có `/work`, hãy đổi classpath về nơi có class. Số processor JVM báo có thể thay đổi theo override, nhưng file `cpu.max` phải phản ánh **cùng resource quota** do Docker cấp, không tự tăng bốn lần.

## 12. Kubernetes: phân tích requests, limits và Pod restarts

Một cấu hình mẫu trong `containers:`:

```yaml
containers:
  - name: java-api
    image: approved-java-image
    resources:
      requests:
        cpu: "250m"
        memory: "256Mi"
      limits:
        cpu: "1"
        memory: "512Mi"
```

Đây là **fragment minh họa**, không phải manifest đủ để deploy. `approved-java-image` cần thay bằng image hợp lệ đã được bảo mật/đăng ký tại cluster.

Khi quan sát trên cluster với quyền phù hợp:

```bash
kubectl describe pod POD_NAME -n NAMESPACE
kubectl logs POD_NAME -n NAMESPACE --previous
kubectl top pod POD_NAME -n NAMESPACE
```

Thay `POD_NAME` và `NAMESPACE` bằng tên thực; nếu Pod có nhiều container hãy chọn đúng container khi kiểm tra logs/metrics. `kubectl top` phụ thuộc metrics pipeline và thường lấy mẫu trễ, **không báo heap used của JVM**.

**Nếu Pod OOMKilled:** ghi memory limit, restart history, termination reason, `memory.events`, peak cgroup usage và logs của container trước. Kiểm tra cả non-heap/native memory; không mặc định tăng max heap.

**Nếu p99 tăng khi giảm CPU limit:** đo `cpu.stat` throttling delta, JVM GC logs và request tracing. CPU throttling có thể làm p99 tăng **ngay cả khi GC pause không lớn**.

**Nếu requests khác limits:** xác định phần nào ảnh hưởng scheduling và phần nào là kernel hard cap. Không dự đoán JDK active CPU count chỉ từ requests.cpu nếu chưa xác minh Java version/patch và cgroups.

## 13. JVM diagnostic tools vẫn áp dụng hiện nay

### Xem container detection và lựa chọn JVM

```bash
java -XshowSettings:system -version
java -Xlog:os+container=trace -version
java -XX:+PrintFlagsFinal -version
```

Các command có output khác nhau theo JDK/HotSpot/vendor. `-Xlog:os+container=trace` có thể rất dài; dùng cho troubleshooting, không bật liên tục thiếu giới hạn log.

### Thu GC logs

```bash
java -Xmx256m -Xlog:gc*:file=gc.log:time,level,tags \
  -cp . ContainerLimitsDemo
```

Đây là cú pháp xuống dòng dành cho **Bash/POSIX shell**; Windows PowerShell có thể đặt trên một dòng. Chương trình demo rất ngắn, có thể chưa tạo đủ workload để xuất hiện nhiều GC events; **không có pause không đồng nghĩa GC đã tắt**.

### Native Memory Tracking (NMT)

Có thể bật một cấp độ NMT ngay khi JVM khởi động:

```bash
java -XX:NativeMemoryTracking=summary -Xmx256m \
  -cp . ContainerLimitsDemo
```

Với JVM chạy lâu và NMT đã được bật, lệnh chẩn đoán:

```bash
jcmd JVM_PID VM.native_memory summary
```

Thay `JVM_PID` bằng PID thực. `jcmd` phụ thuộc quyền attach/PID namespace/security settings, không bảo đảm hoạt động trong mọi container. **NMT không phải toàn bộ RSS và không theo dõi mọi memory do native libraries khác cấp phát**; dùng cùng OS metrics.

### Nguồn dữ liệu từ Java và OS

- `MemoryMXBean`: heap/non-heap usage do JVM quản lý.
- `Runtime`: số CPU khả dụng theo nhận diện JVM và giới hạn heap.
- GC logs/JFR: pause time, allocation và thread/CPU behavior khi được bật phù hợp.
- cgroups: quota, limits, throttling và memory usage ở mức nhóm.
- Orchestrator: requests, limits, restart state, OOMKilled và metrics bên ngoài.
- App: throughput, p95/p99, error rate, queueing và dependency latency.

**Gắn nhãn đơn vị và phạm vi cho mỗi metric**: bytes vs MiB, CPU quota/period vs số core, percent vs cores, RSS vs committed heap và JFR GC pause vs request latency.

## 14. Những tình huống chẩn đoán điển hình

| Quan sát | Nguyên nhân khả dĩ, chưa phải kết luận | Cần đo tiếp |
| --- | --- | --- |
| Heap max JVM rất lớn trong Pod limit nhỏ | Detection cgroups sai, flags override, JDK cũ | Version/patch, `-XshowSettings:system`, flags |
| CPU count nhỏ hơn host | Cgroup quota/cpuset hoặc override | `cpu.max`, affinity, `ActiveProcessorCount` |
| CPU used cao, p99 xấu | Throttling, queueing, GC/JIT, app CPU bound | `cpu.stat` delta, tracing, GC log |
| CPU limit giảm và throughput giảm | Hết CPU budget, tăng contention | Load generator, throttling, worker count |
| Heap used thấp nhưng Pod OOMKilled | Native memory, page cache, process khác | `memory.current/events`, RSS, NMT |
| Nhiều native thread errors | `pids.max` hoặc native stack budget | Thread count, cgroup pids, OS limits |
| GC count tăng khi memory limit giảm | Heap sizing nhỏ hơn hoặc workload khác | `-Xmx`, GC logs, allocation pressure |
| Đọc cgroup files ra unavailable | Không có mount đúng, OS khác, reader đơn giản | Cgroup version, JVM diagnostics, mountinfo |
| Đổi limits nhưng pool không đổi | Pool sizing một lần khi khởi động | Executor config, restart/rollout strategy |

Các nguyên nhân trong bảng là **giả thuyết phải kiểm tra**, không là quan hệ nhân quả tuyệt đối.

## 15. Hướng dẫn A/B test tài nguyên container

Để tránh nhầm biến:

1. **Giữ nguyên** JDK vendor/build, application binary, dependency, GC, workload và load generator.
2. Chọn **một biến đổi**: CPU limit hoặc memory limit. Nếu đổi cả hai, khó quy nguyên nhân.
3. Ghi request/limit thực tế, cpuset, cgroup version, kernel và số lượng container/proc.
4. Xác nhận JVM nhận diện tài nguyên bằng `-XshowSettings:system` và số liệu trong chương trình.
5. Giữ cấu hình `-Xmx`/MaxRAMPercentage có chủ đích; nếu đổi memory limit và muốn xem JVM auto sizing, ghi rõ heap max thay đổi là biến phụ.
6. Warm up class loading/JIT, đo ở tải ổn định, lặp nhiều run; không chỉ chọn run nhanh nhất.
7. Thu throughput, error rate, p50/p95/p99, GC pause count/max, cgroup CPU throttling delta, memory peak, restart.
8. Đo đồng thời metrics để tương quan timeline; **snapshot không đủ kết luận hiệu ứng giới hạn**.
9. Giữ overhead logs/JFR giống nhau giữa các nhánh, hoặc tách lượt diagnostics riêng.
10. Báo rõ độ phân tán và khoảng tin cậy khi có thể; nếu thay đổi nằm trong noise, báo “chưa đủ bằng chứng”.

**Bảng báo cáo nên có:**

| Metric | Run A | Run B |
| --- | --- | --- |
| Docker/K8s CPU limit | Giá trị cấu hình thật | Giá trị cấu hình thật |
| JVM active processor count | Đọc từ Java | Đọc từ Java |
| Memory limit và max heap | Cgroup + Runtime | Cgroup + Runtime |
| Throughput requests/s | App metrics | App metrics |
| p99 latency (ms) | Histogram | Histogram |
| CPU throttling delta | `cpu.stat` | `cpu.stat` |
| GC pause p99 / max (ms) | GC log/JFR | GC log/JFR |
| Memory peak / OOM kills | OS/orchestrator | OS/orchestrator |

Không điền **số liệu giả** vào các ô “giá trị thật”. Nếu tăng CPU quota mà throughput không tăng, application có thể bị nghẽn I/O, lock hoặc downstream; kiểm tra trước khi “tuning” thêm CPU flags.

## 16. Các sai lầm thường gặp

**1. “JVM báo 2 CPU nghĩa là host có 2 core.”** Sai. Con số là processors **khả dụng theo JVM**, chịu ảnh hưởng limits/affinity/flags.

**2. “CPU request 250m có nghĩa CPU không được dùng quá 250m.”** Sai. Request tham gia scheduling/chia sẻ, còn CPU limit/quota mới là cơ chế hard bandwidth cap tương ứng.

**3. “0,5 CPU đồng nghĩa chỉ được tạo 0,5 Java thread.”** Sai. Quota là ngân sách CPU, còn threads là đối tượng lập lịch.

**4. “ActiveProcessorCount=8 sẽ cấp thêm CPU cho container.”** Sai. Cờ HotSpot thay sizing nhận thức, không nới quota OS.

**5. “Tắt UseContainerSupport là bỏ được giới hạn Docker.”** Sai. Kernel cgroups vẫn giới hạn/kill process.

**6. “Xmx là tổng RAM ứng dụng.”** Sai. Heap chỉ là một phần của RSS/cgroup memory.

**7. “Runtime.maxMemory() luôn bằng memory.max.”** Sai. Một cái là max heap, một cái hard limit toàn cgroup.

**8. “Có OOMKilled thì chắc chắn từng có Java OutOfMemoryError.”** Sai. Kernel có thể SIGKILL mà không có exception JVM.

**9. “Exit 137 chắc chắn do heap overflow.”** Sai. Cần xem SIGKILL/termination reason và cgroup logs.

**10. “memory.current là heap used.”** Sai. Cgroup usage có thể gồm native, cache và những process khác.

**11. “NMT summary là tổng RSS.”** Sai. NMT theo dõi phạm vi HotSpot, không hoàn chỉnh mọi native allocations.

**12. “Không đọc được /sys/fs/cgroup/memory.max nghĩa là container không giới hạn RAM.”** Sai. Có thể khác mount hoặc dùng cgroups v1, hoặc quyền đọc bị chặn.

**13. “Một lần đọc cpu.stat đủ kết luận throttling của benchmark.”** Sai. Counter tích lũy; lấy delta đúng cửa sổ.

**14. “JDK 14 trên cgroups v2 hoạt động như JDK 17/26.”** Sai. Support và backports khác nhau; dùng JDK hiện hành và xác minh.

**15. “Tăng Xmx sẽ chữa mọi memory restart.”** Sai. Nếu container limit thấp hoặc native memory cao, tăng heap có thể khiến kill nặng hơn.

**16. “Chỉ cần GC pause là biết vì sao request chậm.”** Sai. CPU throttling, I/O, lock và network có thể là nguyên nhân.

## 17. Checklist nghiệm thu và bài tập

### Checklist

- [ ] Xem `java -version`/vendor/build/patch thực tế.
- [ ] Xác định cgroups v1/v2, container runtime và kernel.
- [ ] Ghi rõ CPU/memory requests và limits đã áp dụng.
- [ ] Kiểm tra `availableProcessors()`, `Runtime.maxMemory()` và mọi JVM override.
- [ ] So sánh heap/non-heap JVM với cgroup memory usage và OS RSS.
- [ ] Thu `cpu.stat` delta nếu nghi CPU throttling.
- [ ] Thu `memory.events` và termination reason nếu Pod restart.
- [ ] Phân biệt heap OOME, native resource lỗi và OOMKilled.
- [ ] Xác minh `-XshowSettings:system`/`-Xlog:os+container` khi detection đáng ngờ.
- [ ] Không tự ghi cgroup files hoặc cố OOM trong production.
- [ ] Đo application throughput/latency và GC để kết luận dựa trên tác động thực.
- [ ] Ghi rõ nguồn/đơn vị/cửa sổ thời gian của tất cả metrics.

### Bài 1 — Biên dịch, xác minh

Chạy `ContainerLimitsDemo --check` và so khớp **ba dòng stdout**. Sau đó chạy chế độ thường, ghi lại `availableProcessors`, `runtimeMaxHeapMiB` và `cgroupV2.memory.max`. Giải thích vì sao không phải các giá trị đều phải bằng nhau.

### Bài 2 — Giới hạn heap và container

Giữ Docker memory limit 512 MiB, so sánh `-Xmx128m` với `-Xmx256m`. Chỉ ra thay đổi nào thuộc JVM heap và vì sao memory hard limit cgroup không tự đổi theo `-Xmx`.

### Bài 3 — CPU override

Giữ CPU quota cố định, chạy `-XX:ActiveProcessorCount=1` và `=4`. Quan sát số processor JVM báo và `cpu.max`. Giải thích vì sao tăng số processors nhận thức không có nghĩa được cấp thêm CPU bandwidth.

### Bài 4 — Cgroup v2

Trên Linux với file cgroup v2 được expose:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
```

Lấy hai snapshot ở thời điểm khác nhau để tính throttling/OOM counters delta. Nếu các đường dẫn không tồn tại, xác định đúng cgroup version/mount thay vì tự tạo file.

### Bài 5 — OOMKilled nhưng heap còn thấp

Một Pod memory limit 256 MiB, heap used khoảng 150 MiB nhưng trạng thái `OOMKilled`. Liệt kê ít nhất ba nguồn dùng memory ngoài heap và đề xuất công cụ xác minh. Không tự kết luận cần tăng max heap.

### Bài 6 — CPU limit và latency

Giữ cùng Java image/workload, so sánh CPU limits hai mức. Thu request p95/p99, `cpu.stat` delta, GC pause timeline và error rate. Giải thích vì sao p99 có thể tăng dù GC pause không đổi.

### Bài 7 — Kubernetes requests khác limits

Giữ `limits.cpu=1` và tăng `requests.cpu` từ 250m lên 500m. Phân biệt tác động scheduling/shares với hard CPU quota. Đối chiếu JDK version cụ thể trước khi dự đoán thay đổi `availableProcessors()`.

### Bài 8 — Thread count và pids.max

Nếu không tạo được thêm Java thread, hãy kiểm tra `pids.max`, thread count và native memory. Giải thích vì sao tăng `-Xmx` không giải quyết trực tiếp giới hạn số task của cgroup.

### Bài 9 — Bảng ngân sách RAM

Với container limit 1 GiB, ứng dụng có nhiều threads, direct buffers và class metadata, đề xuất cách chọn heap cap có headroom. Ghi rõ bạn cần đo thêm những metric nào thay vì dùng một tỷ lệ “chuẩn” cố định.

**Tiêu chí hoàn thành:** Người học phân biệt host/cgroup/JVM/application metrics, đọc được số liệu Java 17+, không nhầm CPU quota với thread count, hiểu heap vs container memory và phân biệt Java OutOfMemoryError với OOMKilled.

## 18. Nguồn tham khảo đang được hỗ trợ

- [Oracle Java SE 26 — java command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): `UseContainerSupport`, `ActiveProcessorCount`, `MaxRAMPercentage`, `-Xmx`, `-XshowSettings:system` và `-Xlog:os+container=trace`.
- [Oracle Java SE 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn tương thích với bài thực hành Java 17+.
- [Oracle Java SE 26 — OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html): semantics của processor count và sự thay đổi tại runtime.
- [Oracle Java SE 17 — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `availableProcessors`, `maxMemory`, `freeMemory`/`totalMemory`.
- [Oracle Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap measurement.
- [Oracle Java SE 26 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/vm/native-memory-tracking.html): NMT và giới hạn phạm vi dữ liệu.
- [Linux Kernel — Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.max`, `cpu.stat`, `memory.max`, `memory.current`, `memory.events`, `pids.max`.
- [Kubernetes — About cgroup v2](https://kubernetes.io/docs/concepts/architecture/cgroups/): điều kiện hỗ trợ và khuyến nghị cho JVM.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory requests và limits.
- [Oracle Java 19 Release Notes — CPU Shares](https://www.oracle.com/java/technologies/javase/19-relnote-issues.html): thay đổi cách tính active processor count từ CPU shares.

**Ghi nhớ:** **CPU quota không phải số thread; max Java heap không phải giới hạn RAM toàn container; Java OutOfMemoryError không đồng nghĩa với OOMKilled.** Hãy đối chiếu cấu hình container, cgroups, JVM diagnostics và số liệu ứng dụng trước khi kết luận giới hạn tài nguyên đang làm thay đổi hiệu năng như thế nào.