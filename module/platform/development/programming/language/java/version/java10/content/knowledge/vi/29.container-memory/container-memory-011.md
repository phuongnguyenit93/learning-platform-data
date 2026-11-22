# Đối chiếu cấu hình JVM với chỉ số bộ nhớ của container

*Chủ đề cha: Bộ nhớ trong container — Java 10. Bài Knowledge hướng dẫn đọc **bộ nhớ JVM**, **bộ nhớ process** và **bộ nhớ toàn cgroup/container**, đặt chúng cạnh giới hạn Docker/Kubernetes để tránh kết luận sai về heap, native memory, RSS và OOM. Nội dung tập trung vào HotSpot trên Linux cgroup v1/v2 và các API Java vẫn còn áp dụng trong JDK hiện đại; ví dụ độc lập biên dịch bằng Java 17 trở lên.*

## 1. Câu hỏi thực tế: JVM báo 256 MiB heap, container dùng 500 MiB — có lỗi không?

Giả sử một service Java chạy với:

```bash
java -Xms64m -Xmx256m -jar app.jar
```

và một container có memory limit 512 MiB. Bạn quan sát:

- JVM báo `Runtime.getRuntime().maxMemory()` khoảng 256 MiB.
- `MemoryMXBean.getHeapMemoryUsage().getUsed()` có thể chỉ là 100 MiB.
- Linux cgroup v2 `memory.current` của container có thể là 300–500 MiB.
- Dashboard có thể hiển thị RSS, working set hoặc một metric bộ nhớ khác.

**Các con số này không bắt buộc bằng nhau.** Chúng đo **những miền khác nhau**:

1. **Heap max**: giới hạn/công suất của Java object heap mà JVM được cấu hình để sử dụng.
2. **Heap used/committed**: dung lượng heap thực sự đang dùng/đã committed theo Java management API.
3. **Native/non-heap memory**: metaspace, code cache/JIT, thread stacks, cấu trúc GC, direct buffers và các cấp phát ngoài heap.
4. **Process RSS**: các trang bộ nhớ resident của một process, có thể bao gồm trang shared.
5. **Cgroup `memory.current`**: tổng bộ nhớ được kernel hạch toán cho cgroup **và các descendant cgroups**, bao gồm nhiều loại bộ nhớ của các process, cache file và kernel-related charges.

Vì vậy:

```text
   Container memory limit (memory.max) ─ giới hạn kernel
   ┌──────────────────────────────────────────────────────────┐
   │ Java process:                                            │
   │   ┌─────────────── Java heap ─────────────────────┐      │
   │   │ used; committed; maximum (-Xmx/ergonomics)    │      │
   │   └───────────────────────────────────────────────┘      │
   │   Metaspace / class metadata / JIT code cache            │
   │   Thread stacks / JVM runtime structures                 │
   │   Direct/mapped buffers / other native allocations       │
   │   Shared file-backed mappings (tùy OS accounting)        │
   │                                                          │
   │ Other processes trong cgroup, page cache, kernel charges│
   └──────────────────────────────────────────────────────────┘

   memory.current = kernel accounting của cgroup, KHÔNG phải heap.used
```

Sơ đồ chỉ phân loại **nguồn chi phí**, không phải công thức cộng số học chính xác: có thể có giao nhau giữa các nhóm, trang shared, cache được reclaim, biến động theo thời điểm và các bộ đếm không chụp cùng một lúc.

**Nguyên tắc quan trọng nhất:** `-Xmx` **không phải giới hạn RSS**, và `memory.max` **không phải Java heap maximum**.

## 2. Mục tiêu học tập

Sau bài học bạn có thể:

1. Giải thích các khái niệm `-Xms`, `-Xmx`, `InitialRAMPercentage`, `MaxRAMPercentage` và `UseContainerSupport` theo cách hiện đại.
2. Dùng `Runtime.maxMemory()`, `totalMemory()`, `freeMemory()` và `MemoryMXBean` mà không nhầm các loại số.
3. Nhận diện bộ nhớ ngoài heap như metaspace, code cache, JVM native allocations và NIO direct buffers.
4. Đọc `BufferPoolMXBean` để khảo sát direct/mapped buffers; hiểu số liệu đó cũng không phải toàn bộ native memory.
5. Dùng HotSpot Native Memory Tracking (NMT) và `jcmd` đúng mục đích, biết vùng NMT không bao phủ.
6. Đọc cgroup v2 `memory.max`, `memory.current`, `memory.peak`, `memory.stat`, `memory.events` và `memory.swap.current`.
7. Biết tên tệp tương ứng của cgroup v1 và cẩn thận với giá trị “unlimited” rất lớn.
8. Phân biệt Kubernetes `requests.memory` với `limits.memory`, Docker `--memory`, limit ở cgroup cha và swap.
9. Biết vì sao `-Xmx` nhỏ hơn memory limit vẫn có thể gặp `OOMKilled`.
10. Phân biệt Java `OutOfMemoryError` với kernel OOM kill / exit code 137.
11. So hai container hoặc hai cấu hình JVM bằng **cùng ứng dụng/JDK/workload**, đo đúng thời điểm, tránh cộng đúp.
12. Viết một chương trình Java 17+ in thông tin heap/non-heap/cgroup cạnh nhau và một chương trình khác thử heap với direct memory.
13. Biết chọn ngưỡng heap và headroom dựa vào thực nghiệm, không dựa vào một hệ số cố định áp cho mọi ứng dụng.
14. Giải thích chính xác các trường hợp `memory.max=max`, heap `max=-1`, NMT `reserved` lớn và container memory usage tăng do page cache.

## 3. Mốc Java 10 và cách làm trong JDK hiện đại

**Java 10** cải thiện khả năng container-aware của HotSpot trên Linux: JVM có thể nhận biết giới hạn tài nguyên cgroup/Docker thay vì mặc nhiên lấy toàn bộ RAM host. Đây là bối cảnh của chủ đề “Bộ nhớ trong container” trong module Java 10.

Trên JDK hiện đại như Java 17/21/25, các công cụ cốt lõi vẫn phù hợp:

- `-XX:+UseContainerSupport`: HotSpot/Linux hỗ trợ container/cgroup và thường bật mặc định. Cờ `-XX:-UseContainerSupport` vô hiệu hóa phát hiện, không phải cách tối ưu được khuyến nghị khi đã triển khai container.
- `-XX:MaxRAMPercentage=p`: cho phép JVM chọn mức heap maximum dựa trên bộ nhớ mà JVM xác định là khả dụng, có tính đến hạn chế môi trường khi được hỗ trợ.
- `-XX:InitialRAMPercentage=p`: phần trăm đầu vào cho heap initial sizing khi dùng cơ chế chọn tự động.
- `-Xmx<size>` và `-Xms<size>`: đặt maximum và initial Java heap theo kích thước tuyệt đối.
- `-XshowSettings:system`: xem thông tin hệ thống/container mà launcher nhận biết khi nền tảng hỗ trợ, đặc biệt trên Linux.
- `-Xlog:os+container=debug`: xem log phát hiện cgroup/container của HotSpot.
- `-XX:NativeMemoryTracking=summary|detail` và `jcmd VM.native_memory`: phân tích một phần native/JVM memory.
- `MemoryMXBean`, `MemoryPoolMXBean`, `BufferPoolMXBean`: các management API vẫn áp dụng trong Java hiện đại.

**Tránh công thức legacy `MaxRAMFraction`/`InitialRAMFraction`**: các lựa chọn dạng Fraction đã bị deprecated; dùng percentage flags hoặc `-Xmx` khi cần kiểm soát rõ.

**Không hứa rằng hai JDK vendors hoặc phiên bản HotSpot có cùng heap mặc định** chỉ vì cùng memory limit. Ergonomics, GC, module/runtime image và cgroup support có thể khác; phải đo trên JDK sẽ triển khai.

## 4. Bảng đối chiếu theo đúng miền đo

| Lớp đo | Chỉ số/API | Đơn vị | Đang trả lời câu hỏi nào? |
| --- | --- | --- | --- |
| JVM cấu hình | `-Xmx`, `-Xms` | Kích thước bộ nhớ | Heap có mức tối đa và mức đầu như thế nào? |
| JVM cấu hình | `MaxRAMPercentage` | % | JVM tự chọn max heap từ ngân sách nhận biết ra sao khi không đặt Xmx? |
| JVM runtime | `Runtime.maxMemory()` | Bytes | Java heap có thể tăng tối đa khoảng bao nhiêu? |
| JVM runtime | `Runtime.totalMemory()` | Bytes | Tổng dung lượng heap hiện JVM cấp/committed theo Runtime |
| JVM runtime | `Runtime.freeMemory()` | Bytes | Dung lượng chưa dùng **bên trong heap đang cấp**, không phải RAM còn trống của container |
| JVM management | `MemoryMXBean.heap.used` | Bytes | Heap đang chứa bao nhiêu dung lượng used ước lượng? |
| JVM management | `MemoryMXBean.heap.committed` | Bytes | JVM đã committed bao nhiêu heap? |
| JVM management | `MemoryMXBean.heap.max` | Bytes hoặc `-1` | Giới hạn heap tối đa nếu xác định được |
| JVM management | `MemoryMXBean.nonHeap.*` | Bytes | Một số vùng non-heap quản lý bởi JVM; **không** bao hết native |
| NIO | `BufferPoolMXBean.getMemoryUsed()` | Bytes hoặc `-1` | Ước lượng memory của buffer pool trực tiếp/mapped |
| HotSpot NMT | `reserved` và `committed` theo category | Bytes | Phân tích vùng JVM-managed native/virtual memory; không đồng nghĩa container current |
| Process OS | RSS / PSS / private memory | Bytes | Các trang resident/được chia sẻ của process theo OS |
| Cgroup v2 | `memory.max` | Bytes hoặc `max` | Hard memory ceiling của cgroup |
| Cgroup v2 | `memory.current` | Bytes | Memory đang được hạch toán cho cgroup và descendants |
| Cgroup v2 | `memory.peak` | Bytes | Đỉnh usage được kernel ghi nhận, có ngữ nghĩa reset/availability theo kernel |
| Cgroup v2 | `memory.high` | Bytes hoặc `max` | Ngưỡng reclaim/throttling; khác hard limit |
| Cgroup v2 | `memory.stat` | Các bytes theo key | Phân rã charge theo loại memory |
| Cgroup v2 | `memory.events` | Bộ đếm | OOM, high/max, OOM kill events |
| Cgroup v2 | `memory.swap.current` | Bytes | Swap usage riêng theo cgroup v2 |
| Docker/Kubernetes | `--memory` / `limits.memory` | Bytes/quy ước units | Hệ triển khai yêu cầu kernel giới hạn bao nhiêu? |

**Không cộng trực tiếp mọi hàng.** Ví dụ `heap.committed` nằm trong chi phí của process, NMT có phần giao nhau với heap/non-heap, RSS có trang shared, còn `memory.current` bao gồm thêm cache/kernel/other processes. Cộng chúng sẽ **đếm lặp**.

## 5. Hiểu kỹ Java heap: used, committed, max

Giả sử bạn chạy:

```bash
java -Xms64m -Xmx256m -jar app.jar
```

Trong một lần đo có thể thấy:

```text
heap.usedMiB       = 50
heap.committedMiB  = 66
heap.maxMiB        = 256
```

**Đây chỉ là ví dụ giả lập có đánh nhãn, không phải stdout cố định**. Một chương trình thật có thể báo giá trị khác do GC/heap alignment/tại thời điểm lấy mẫu.

Các quan hệ cần hiểu:

- **Used**: dung lượng heap đang được dùng theo bộ đo của JVM. Có thể biến động mạnh giữa các lần GC.
- **Committed**: dung lượng được JVM đảm bảo sẵn sàng sử dụng; không nhất thiết toàn bộ các trang đã resident trong RAM vật lý ngay lập tức.
- **Max**: giới hạn dung lượng heap JVM có thể mở rộng tới; **không** nói lúc này JVM đã dùng toàn bộ số đó.
- **`-Xms`** là kích thước heap ban đầu mong muốn (và thường gắn với initial committed region), không trực tiếp là số RAM vật lý cư trú.
- **`-Xmx`** là giới hạn heap, không tính metaspace, threads, direct/native memory, JIT code, kernel cache hoặc các process phụ.
- **`Runtime.freeMemory()`** chỉ là phần chưa dùng bên trong tổng heap hiện JVM cấp; không phải “container còn trống bao nhiêu MiB”.

`MemoryMXBean.getNonHeapMemoryUsage()` biểu diễn một số vùng “non-heap” do memory management API mô tả. Nó **không bao gồm mọi native memory** của HotSpot, thread stacks, thư viện native hoặc tất cả direct buffers. Vì vậy **`heap.used + nonHeap.used` không phải RSS, càng không phải `memory.current`**.

### 5.1. Tại sao `Runtime.maxMemory()` và `-Xmx` có thể khác số tròn?

JVM có thể điều chỉnh kích thước theo page/granularity của garbage collector, heap alignment và ergonomics. Đừng assert bằng chuỗi “256 MB” nếu bạn đã viết `-Xmx256m` mà hệ thống báo giá trị khác vài MiB.

Nếu cần kiểm tra giá trị thực được chọn, dùng `Runtime.maxMemory()` và/hoặc in flags tại khởi động:

```bash
java -Xms64m -Xmx256m -XX:+PrintFlagsFinal -version
```

Trong output rất dài, tìm các flag như `InitialHeapSize`, `MaxHeapSize`, `MaxRAMPercentage` và `UseContainerSupport`. Phần này giúp **kiểm tra cấu hình JVM**, không tự nói container đang dùng đúng từng ấy RAM.

### 5.2. `MaxRAMPercentage` và `-Xmx` không giống nhau

Hai cấu hình:

```bash
java -XX:MaxRAMPercentage=50.0 -jar app.jar
java -Xmx256m -jar app.jar
```

Lệnh đầu cho JVM **tự tính** maximum heap theo bộ nhớ runtime nhận biết, với các quy tắc GC/ergonomics. Lệnh sau yêu cầu **maximum heap tuyệt đối**.

Nếu container có `memory.max` khoảng 512 MiB, `MaxRAMPercentage=50` thường dẫn tới max heap xấp xỉ 256 MiB, nhưng kết quả cuối còn phụ thuộc runtime. Nếu container tăng limit lên 1 GiB và không thay lệnh đầu, JVM có thể chọn heap max lớn hơn. Với lệnh thứ hai, `-Xmx256m` vẫn có mục tiêu heap max 256 MiB dù container có thêm memory headroom.

**Khi đã đặt `-Xmx` tường minh, đừng cố suy heap maximum từ `MaxRAMPercentage`.** Xác nhận flag thật, tránh một biến môi trường khác như `JAVA_TOOL_OPTIONS` hoặc script startup thêm cờ.

## 6. Java process còn sử dụng gì ngoài heap?

### 6.1. Metaspace và class metadata

Dữ liệu class metadata phần lớn do HotSpot quản lý ngoài Java object heap. Class loading, nhiều classloaders hoặc tạo class động có thể làm metaspace tăng trong khi `heap.used` vẫn thấp.

`-XX:MaxMetaspaceSize` có thể đặt giới hạn riêng khi cần; không đưa tất cả non-heap vào `-Xmx`. Có thể xem thêm `MemoryPoolMXBean` với pool tên “Metaspace”, nhưng loại pool/tên có thể phụ thuộc JVM implementation.

### 6.2. JIT và code cache

JVM có thể biên dịch hot methods thành native machine code và giữ trong code cache. Memory này cũng không phải Java heap chứa application objects. Chi phí có thể thay khi warm-up và request patterns đổi.

### 6.3. Stack của platform threads

Mỗi platform thread có stack và native structures, thường liên quan `-Xss` và OS/JVM setup. **`-Xss` không phải tổng trần memory của JVM**. Nhiều threads có thể làm số native pages cần dùng và vùng virtual memory reserved tăng, nhưng reserved không có nghĩa tất cả resident.

Với virtual threads (Java 21+), stack và scheduling có mô hình khác platform threads; không nhân số virtual threads với `-Xss` rồi xem là resident memory chính xác.

### 6.4. Direct/mapped buffers

`ByteBuffer.allocateDirect(...)` có thể cấp bộ nhớ ngoài Java heap cho nội dung buffer. `BufferPoolMXBean` có thể báo ước lượng memory của các pool `direct` hoặc `mapped`. Giá trị này khác với heap used và có thể chưa bao gồm các cấp phát native của thư viện bên thứ ba.

`-XX:MaxDirectMemorySize` giới hạn phần direct-buffer memory theo hợp đồng HotSpot, **không** phải trần mọi native allocation. Một số thư viện dùng native allocator riêng; để điều tra phải hiểu thư viện nào chịu trách nhiệm.

### 6.5. GC, NMT, libc và kernel charges

GC metadata, các vùng native của HotSpot, library code, `mmap`, các native libraries (JNI), memory allocator, page tables và kernel data structures đều có thể làm footprint của process/cgroup tăng. Không có một API Java heap duy nhất tự bao trùm mọi bộ nhớ ấy.

### 6.6. File cache và các process khác trong cgroup

Cgroup `memory.current` có thể bao gồm **filesystem page cache**, `tmpfs`/shared memory, kernel charges và memory của các process **khác** cùng cgroup/descendants. Một sidecar, shell, monitoring process hoặc nhiều JVM có thể cùng làm current tăng.

Bởi vậy, nếu chỉ có số `memory.current` mà không xem `memory.stat` và số process trong cgroup, bạn không thể kết luận “Java heap leak”.

## 7. Chương trình Java 17+ đối chiếu ba nhóm thông tin

Tạo file **`ContainerMemoryProbe.java`**. Ví dụ này:

- In phiên bản Java/processor count của tiến trình.
- In JVM heap max và `MemoryMXBean` heap/non-heap usage.
- In direct/mapped buffer pool nếu có.
- Thử đọc các file **cgroup v2** ở đường dẫn phổ biến `/sys/fs/cgroup`; nếu thiếu, trả `unavailable`.
- Không cố gọi kết quả của cgroup v2 trên Windows/cgroup v1 là “0” hoặc “unlimited”.

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ContainerMemoryProbe {
    private static final long MIB = 1024L * 1024;

    private static String mib(long bytes) {
        return bytes < 0 ? "unknown" : Long.toString(bytes / MIB);
    }

    private static void report(String prefix, MemoryUsage usage) {
        System.out.println(prefix + ".usedMiB=" + mib(usage.getUsed()));
        System.out.println(prefix + ".committedMiB="
                + mib(usage.getCommitted()));
        System.out.println(prefix + ".maxMiB=" + mib(usage.getMax()));
    }

    private static void cgroup(String name) {
        Path file = Path.of("/sys/fs/cgroup", name);
        try {
            if (Files.isReadable(file)) {
                System.out.println("cgroup." + name + "="
                        + Files.readString(file)
                          .trim().replace("\n", ";"));
            } else {
                System.out.println("cgroup." + name
                        + "=unavailable");
            }
        } catch (Exception ex) {
            System.out.println("cgroup." + name
                    + "=read-error:"
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        System.out.println("javaFeature="
                + Runtime.version().feature());
        System.out.println("processors="
                + Runtime.getRuntime().availableProcessors());
        System.out.println("heap.maxRuntimeMiB="
                + mib(Runtime.getRuntime().maxMemory()));

        var memory = ManagementFactory.getMemoryMXBean();
        report("heap", memory.getHeapMemoryUsage());
        report("nonHeap", memory.getNonHeapMemoryUsage());

        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class)) {
            if (pool.getName().equals("direct")
                    || pool.getName().equals("mapped")) {
                System.out.println("buffer."
                        + pool.getName() + ".usedMiB="
                        + mib(pool.getMemoryUsed()));
            }
        }

        cgroup("memory.max");
        cgroup("memory.high");
        cgroup("memory.current");
        cgroup("memory.peak");
        cgroup("memory.events");
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 ContainerMemoryProbe.java
java -Xms64m -Xmx256m -XX:MaxDirectMemorySize=64m ContainerMemoryProbe
```

**Ví dụ đã được chạy trên OpenJDK 21 trong một Linux cgroup v2 có memory limit 4 GiB**; trích những dòng đã đo ở một thời điểm:

```text
javaFeature=21
processors=4
heap.maxRuntimeMiB=256
heap.usedMiB=2
heap.committedMiB=66
heap.maxMiB=256
nonHeap.usedMiB=2
nonHeap.committedMiB=8
nonHeap.maxMiB=unknown
buffer.mapped.usedMiB=0
buffer.direct.usedMiB=0
cgroup.memory.max=4294967296
cgroup.memory.high=max
cgroup.memory.current=543936512
cgroup.memory.peak=589357056
cgroup.memory.events=low 0;high 0;max 0;oom 0;oom_kill 0;oom_group_kill 0
```

**Đây là một mẫu đo thực tế, không phải stdout cố định để assert trên mọi máy.** `processors`, `used/committed`, `memory.current`, `peak`, event counters, và các pool đều thay đổi theo runtime, container và thời điểm. Một JDK 17 hoặc 25 không phải báo đúng các giá trị của ví dụ JDK 21.

Giải thích mẫu:

1. `-Xmx256m` làm JVM báo max heap 256 MiB trên runtime thử nghiệm.
2. `heap.usedMiB=2` chỉ nói heap đang dùng ít, không nói container chỉ dùng 2 MiB.
3. `nonHeap.usedMiB=2` không phải tổng native memory.
4. `memory.max=4294967296` tương đương **4096 MiB (4 GiB)** cho cgroup này.
5. `memory.current=543936512` là **kernel accounting của cgroup**, có thể bao gồm nhiều process/cache, không được suy ra tất cả ~519 MiB đến từ Java heap của chương trình nhỏ.
6. `memory.high=max` nghĩa cgroup đó không đặt ngưỡng high tường minh; không chứng minh mọi ancestor không giới hạn.
7. Các event counters bằng 0 trong mẫu chỉ nói chưa thấy sự kiện được tính trong cgroup ở thời điểm đọc đó; không chứng minh mọi bản deploy khác không gặp OOM.

### 7.1. Chú ý tính portable

Chương trình Java **vẫn chạy trên Windows/macOS**: các đường dẫn Linux `/sys/fs/cgroup` không tồn tại, nên phần cgroup có thể in `unavailable`. Điều này không phải lỗi Java heap. Nó cũng có thể in unavailable trên Linux **cgroup v1**, hoặc khi mount namespace không expose các file v2 tại đúng đường dẫn.

Không khẳng định đây là parser tổng quát cho mọi cgroup layout. Trong production cần chọn đúng controller/path theo `/proc/self/cgroup` và mountinfo nếu môi trường phức tạp. Mục tiêu của probe là **đặt các miền đo cạnh nhau** để phân tích, không thay thế một agent đo cgroup có hỗ trợ đủ v1/v2.

### 7.2. Vì sao phần cgroup giữ bytes thay vì đổi sang MiB?

File cgroup trả bytes. In raw giúp kiểm tra dữ liệu kernel mà không mất phần dư vì phép chia nguyên. Khi lên dashboard, bạn có thể đổi:

```text
MiB = bytes / 1_048_576
GiB = bytes / 1_073_741_824
```

Không nhầm MB (thập phân) với MiB (nhị phân). Những giá trị `-Xmx256m` thường được hiểu theo cách tính kích thước JVM và có thể bị alignment; đọc **giá trị thực từ API/flag** nếu cần chính xác.

## 8. Ví dụ Java 17+: phân biệt heap allocation và direct buffer

Chương trình sau cố ý cấp phát lượng nhỏ, có kiểm soát để thấy direct buffer không được tính chung như một byte array trong Java heap. Không dùng thử nghiệm gây OOM hoặc cố tăng đến memory limit trên máy dùng chung.

Tạo file **`HeapDirectFootprintDemo.java`**:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;

public final class HeapDirectFootprintDemo {
    private static final int MIB = 1024 * 1024;

    private static long directUsed() {
        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class)) {
            if (pool.getName().equals("direct")) {
                return pool.getMemoryUsed();
            }
        }
        return -1;
    }

    public static void main(String[] args) {
        byte[] heap = new byte[16 * MIB];
        ByteBuffer direct = ByteBuffer.allocateDirect(8 * MIB);

        for (int i = 0; i < heap.length; i += 4096) {
            heap[i] = 1;
        }
        for (int i = 0; i < direct.capacity(); i += 4096) {
            direct.put(i, (byte) 1);
        }

        int result = heap[0] + direct.get(0);
        System.out.println("result=" + result);
        System.out.println("directPoolAtLeast8MiB="
                + (directUsed() >= 8L * MIB));
        System.out.println("heapMaxMiB="
                + Runtime.getRuntime().maxMemory() / MIB);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 HeapDirectFootprintDemo.java
java -Xms64m -Xmx256m -XX:MaxDirectMemorySize=64m HeapDirectFootprintDemo
```

Stdout đã kiểm thử trên OpenJDK 21 với những flags trên:

```text
result=2
directPoolAtLeast8MiB=true
heapMaxMiB=256
```

**Điểm học:** 16 MiB byte array nằm trên Java heap; 8 MiB nội dung direct buffer nằm ngoài heap và được `BufferPoolMXBean` báo một ước lượng riêng. Mọi phần đều có thể ảnh hưởng tới container memory accounting. Tuy nhiên, **không** lấy `16 + 8` rồi suy `memory.current` phải tăng đúng 24 MiB: class loading, file cache, page accounting, GC, padding và thời điểm đo cũng ảnh hưởng.

**Giới hạn của kiểm thử:** output `result=2` là xác định; hai dòng còn lại phản ánh cấu hình HotSpot/JDK được thử. Nếu một runtime dùng GC hoặc alignment khác, `heapMaxMiB` có thể lệch so với con số tròn, và direct-pool estimates phải được kiểm tra theo API.

## 9. Đọc cgroup v2: giới hạn, usage, peak, events

Trên **Linux cgroup v2**, các file thường có thể đọc qua mount `/sys/fs/cgroup` trong một container với cấu hình phù hợp:

```bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.high
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.swap.current
```

Không phải tất cả file đều có trên mọi kernel/runtime image/mount. Đừng kết luận “không có memory limit” chỉ vì đường dẫn bạn đoán không tồn tại: có thể là cgroup v1, mount khác, cgroup namespace khác hoặc quyền truy cập khác.

### 9.1. `memory.max`: hard limit

Ví dụ:

```text
536870912
```

Đó là **512 MiB**. Nếu file trả `max`, cgroup đó không có hard limit tường minh ở file đang đọc; **không** đồng nghĩa toàn bộ node vô hạn RAM. Cgroup parent/ancestor có thể giới hạn thấp hơn, host có giới hạn vật lý và Kubernetes scheduling vẫn áp dụng.

Linux memory controller có thể reclaim pages; giới hạn bộ nhớ và OOM enforcement có tính động. Không kỳ vọng `memory.current` luôn dưới hard limit theo một bất đẳng thức tuyệt đối ở mọi thời điểm đo.

### 9.2. `memory.current`: hiện đang dùng trong cgroup

Theo tài liệu kernel, `memory.current` là tổng memory đang được dùng bởi **cgroup và descendants**. Nó không nói “heap của Java process” hoặc “RSS của PID Java”, cũng không phải con số duy nhất của container nếu các cgroup/process liên quan được sắp nhiều tầng.

Nó có thể bao gồm:

- Anonymous memory có thể liên quan heap/native memory.
- File-backed page cache và một số shared memory/tmpfs.
- Kernel memory đã được hạch toán như page tables, socket buffers, slab.
- Các process khác cùng cgroup.

Đọc `memory.stat` để hiểu thành phần, đừng lấy một `memory.current` cao rồi tự chẩn đoán Java heap leak.

### 9.3. `memory.peak`: usage cao nhất

`memory.peak` trên cgroup v2 hỗ trợ theo dõi peak. Trong kernel hiện đại, ngữ nghĩa reset có thể gắn với file descriptor riêng; **không nên tùy ý ghi để reset trong production** khi chỉ được phép quan sát.

Một chương trình Java rất ngắn có thể khởi động và kết thúc nhanh; khi bạn đọc `peak` sau đó, các page đã được reclaim hoặc các process khác vẫn có mặt. Ghi rõ khoảng thời gian quan sát và cgroup đã được tạo lúc nào.

### 9.4. `memory.high` khác `memory.max`

- `memory.high`: ngưỡng kích hoạt reclaim/throttling khi memory pressure cao, không phải trần tuyệt đối như max.
- `memory.max`: hard limit cuối cùng; kernel có thể OOM kill nếu reclaim không đủ.
- `memory.low` và `memory.min`: các cơ chế bảo vệ memory khỏi reclaim theo hợp đồng kernel, không phải biến Java heap flags.

Không dùng `memory.high` để suy lượng Java heap tối đa. Một pod có thể có memory limit được thể hiện qua max, nhưng high/low được triển khai thêm theo policy khác.

### 9.5. `memory.swap.current`

Trên cgroup v2, swap được theo dõi riêng bằng `memory.swap.current` và quản lý qua `memory.swap.max` khi được expose. Swap không đồng nghĩa RAM resident, và một container có thể chậm do swap dù không thấy lượng heap used vượt giới hạn.

Không mặc định swap đã tắt vì dùng `--memory`; cấu hình Docker/kernel về swap phải được quan sát. Đừng cộng raw swap counters vào `memory.current` rồi gọi tổng đó là “RSS”.

## 10. Đọc `memory.stat` để hiểu vì sao usage lớn

Một số field có ích:

| Key ở cgroup v2 | Ý nghĩa và lưu ý |
| --- | --- |
| `anon` | Anonymous memory, thường gồm nhiều phần resident của heap và native allocations |
| `file` | Bộ nhớ cache file system, gồm tmpfs/shared memory theo kernel accounting |
| `kernel` | Một số tổng kernel memory charges, có thể bao gồm nhiều category chi tiết |
| `kernel_stack` | Bộ nhớ kernel stacks |
| `pagetables` | Page tables; không phải Java object heap |
| `sock` | Socket/network buffer charges |
| `slab` | Slab allocator-related charges |
| `shmem` | Một phần bộ nhớ shared/tmpfs được phân rã thêm |
| `file_mapped` | Thông tin file-backed memory có mapping, tùy kernel |
| `inactive_file` / `active_file` | Các phần của file cache theo trạng thái kernel, thường dùng trong các quy tắc working-set dashboard |

Ví dụ:

```bash
cat /sys/fs/cgroup/memory.stat
```

**Các field là cấu trúc key–value, thứ tự có thể thay đổi và kernel bổ sung keys mới.** Đừng dùng “dòng thứ 3 luôn là anon” để parse hoặc giả định mọi Linux kernel expose cùng danh sách.

Không cộng `anon+file+kernel+shmem+file_mapped` rồi so với `memory.current`: có những field là **phân rã/quan sát chồng lên nhau**. Tài liệu kernel hướng dẫn tìm đúng key theo tên và hiểu semantics, không tổng hợp bừa.

### 10.1. Vì sao Java heap used thấp, `file` vẫn cao?

Một service đọc JAR, ghi file tạm, xử lý upload, đọc database local hoặc dùng volume có thể tạo page cache. Kernel có thể hạch toán những trang cache đó vào cgroup. Một số cache được reclaim khi memory pressure, nhưng không có nghĩa mọi byte `file` đều có thể được bỏ tức thì mà không ảnh hưởng hiệu năng.

Nếu dashboard “container memory” tăng trong khi Java heap used ổn định, kiểm tra `memory.stat` để xem `file`, `anon` và kernel charges thay đổi thế nào. Không quy tất cả thành leak của `byte[]`.

### 10.2. Nhiều process hay sidecar

Nếu hai JVM cùng ở một cgroup, `memory.current` không tự tách từng JVM. Nếu pod có nhiều container, mỗi container thường có cgroup và hệ thống metric riêng; pod-level aggregated metrics có thể là tổng/tham chiếu hierarchy khác. Phải xác định **scope của metric** trước khi so với JVM process.

**Một process Java không được lấy container toàn bộ rồi trừ mỗi heap của nó để suy “native memory JVM”.** Phần dư còn có thể là file cache, process khác và kernel.

## 11. Cgroup v1: còn tồn tại nhưng đọc khác tên file

Một số Linux runtime vẫn dùng cgroup v1 hoặc môi trường hỗn hợp. Trong controller memory v1, các tên thường gặp:

| Vai trò | Cgroup v2 | Cgroup v1 (vị trí tùy mount) |
| --- | --- | --- |
| Hard limit | `memory.max` | `memory.limit_in_bytes` |
| Current usage | `memory.current` | `memory.usage_in_bytes` |
| Peak usage | `memory.peak` | `memory.max_usage_in_bytes` |
| Chi tiết usage | `memory.stat` | `memory.stat` (keys/semantics khác) |
| Events/OOM | `memory.events` | `memory.failcnt`, `memory.oom_control` và logs |
| Swap | `memory.swap.current` | Có thể liên quan `memory.memsw.*` khi kernel hỗ trợ |

Ví dụ đường dẫn phổ biến cho cgroup v1:

```bash
cat /sys/fs/cgroup/memory/memory.limit_in_bytes
cat /sys/fs/cgroup/memory/memory.usage_in_bytes
cat /sys/fs/cgroup/memory/memory.stat
```

**Đây chỉ là đường dẫn ví dụ**, không phải mọi host/container mount cùng layout. Cgroup v1 có thể trả một số nguyên cực lớn khi giới hạn về thực chất không được đặt. **Đừng coi số sentinel lớn là RAM vật lý có thật**. Phải đối chiếu cgroup thực tế, config container và memory giới hạn của host/ancestor.

Nếu ứng dụng triển khai trên cgroup v2, không cần quay về “mẹo” parse v1 legacy chỉ để học Java 10. Ngược lại, khi hạ tầng thực sự dùng v1, phải hiểu đúng semantics thay vì cố đọc `memory.max` rồi gán “0”.

## 12. Kiểm tra JVM có thật sự phát hiện container không

Hai lệnh hỗ trợ chẩn đoán HotSpot hiện đại trên Linux:

```bash
java -XshowSettings:system -version
java -Xlog:os+container=debug -version
```

Lưu ý:

- Phải chạy **bên trong container** với cùng runtime/JDK image và cgroup context. Chạy `java -version` ngoài host không thể chứng minh container JVM nhìn thấy `memory.max`.
- `-XshowSettings:system` và mức độ thông tin container phụ thuộc nền tảng/JDK. Trên Windows, không tự kỳ vọng output cgroup Linux.
- `-Xlog:os+container` là log debug của **HotSpot**; không phải Java SE API bất biến ở mọi vendor.
- `-XX:+UseContainerSupport` thông thường bật mặc định khi HotSpot/Linux hỗ trợ, nhưng có thể bị tắt bằng options từ environment.
- Kiểm tra `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, launcher script hoặc Helm manifest nếu JVM thực tế nhận các flags khác lệnh bạn tưởng.
- Cgroup parent limits và nested mounts có thể khiến bạn đọc một file không đại diện đúng budget của JVM.

**Không dùng `-XX:-UseContainerSupport` để chữa sự chênh lệch bằng cách khiến JVM nhìn thấy host RAM.** Tắt hỗ trợ container có thể khiến heap được sizing quá lớn so với memory limit của pod và làm rủi ro OOM kill tăng.

### 12.1. Xem flags heap đang áp

```bash
java -XX:+PrintFlagsFinal -version
```

Khi cần so:

```bash
java -XX:MaxRAMPercentage=50.0 -XX:+PrintFlagsFinal -version
java -Xmx256m -XX:+PrintFlagsFinal -version
```

Tìm giá trị `MaxHeapSize` và nguồn flag (“command line” hay “ergonomic/default”). Không chỉ đọc dòng `MaxRAMPercentage=50` rồi suy trần heap nếu `-Xmx`/launcher/GC flags khác đang có hiệu lực.

## 13. Chạy cùng ứng dụng trong Docker với hai mức memory limit

Để đối chiếu đúng, build **một image** từ `ContainerMemoryProbe.java` và chạy với các giới hạn container khác nhau, giữ mã, JDK và môi trường càng giống nhau càng tốt.

Tạo file **`Dockerfile`**:

```dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY ContainerMemoryProbe.java .
RUN javac --release 17 ContainerMemoryProbe.java && \
    jar --create --file memory-probe.jar \
    --main-class ContainerMemoryProbe ContainerMemoryProbe.class

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/memory-probe.jar /app/memory-probe.jar
ENTRYPOINT ["java","-XX:MaxRAMPercentage=50.0","-jar","/app/memory-probe.jar"]
```

Build trên Linux host hoặc Docker Desktop Linux Engine đang hoạt động:

```bash
docker build -t java-memory-probe:21 .
```

Các tags `21-jdk`/`21-jre` là ví dụ dùng JDK có hỗ trợ và còn phổ biến; để benchmark reproducible, pin digest của image và ghi JDK build thật. Nếu không có Docker Engine chạy, chỉ có CLI `docker` sẽ **không** đủ để áp cgroup quota.

### 13.1. Thử `MaxRAMPercentage` khi memory limit thay đổi

```bash
docker run --rm --memory=512m java-memory-probe:21

docker run --rm --memory=1g java-memory-probe:21
```

Cả hai lệnh chạy **cùng image và cùng `MaxRAMPercentage=50`**, nhưng hard limit khác. Kỳ vọng trên HotSpot/Linux container-aware:

- Ở 512 MiB, `heap.maxRuntimeMiB` thường ở quanh 256 MiB (có thể lệch do ergonomics).
- Ở 1 GiB, `heap.maxRuntimeMiB` có thể tăng lên quanh 512 MiB.
- `cgroup.memory.max` trong cgroup v2 sẽ cho biết hard limit thực tế khi được expose.
- `cgroup.memory.current` có thể khác xa heap used và không cố định, do các thành phần được kernel charge.
- Không có một stdout số cụ thể bắt buộc cho mọi JDK/GC/container runtime.

**Không được xem việc heap max tăng là bằng chứng `memory.current` cũng lập tức tăng bấy nhiêu**. Heap max là **capacity**, cgroup current là **usage**.

### 13.2. Thử `-Xmx` cố định khi memory limit thay đổi

Dùng lại cùng image nhưng override ENTRYPOINT:

```bash
docker run --rm --memory=512m \
  --entrypoint java java-memory-probe:21 \
  -Xms64m -Xmx256m -jar /app/memory-probe.jar

docker run --rm --memory=1g \
  --entrypoint java java-memory-probe:21 \
  -Xms64m -Xmx256m -jar /app/memory-probe.jar
```

Khi JVM được khởi động với `-Xmx256m`, trần heap mục tiêu giữ khoảng 256 MiB ở cả hai trường hợp; container limit khác nên **headroom bên ngoài heap** khác. Chỉ nhìn `heap.maxRuntimeMiB` sẽ không nhận ra khác biệt về nguy cơ memory pressure khi limit bị giảm.

### 13.3. Ma trận cần ghi nhận

| Kịch bản | Memory limit | Java heap policy | Kỳ vọng về max heap | Điều phải đo thực |
| --- | --- | --- | --- | --- |
| A | 512 MiB | `MaxRAMPercentage=50` | Gần 256 MiB nếu detection phù hợp | `memory.max`, current, heap max/used, native, events |
| B | 1 GiB | `MaxRAMPercentage=50` | Gần 512 MiB nếu detection phù hợp | Như A, giữ cùng workload |
| C | 512 MiB | `-Xmx256m` | Gần 256 MiB | Headroom, peak/current, native, OOM |
| D | 1 GiB | `-Xmx256m` | Gần 256 MiB | Headroom, peak/current, native, OOM |
| E | 512 MiB | `-Xmx450m` | Gần 450 MiB | Nguy cơ OOM cao hơn do thiếu non-heap headroom |
| F | 1 GiB | `-Xms128m -Xmx512m` | Gần 512 MiB | Used/committed và peak khi tải cao |

Các con số “gần” là **phỏng đoán có điều kiện về cấu hình**, không phải kết quả benchmark thật. Khi thử E hoặc một cấu hình thiếu headroom, không chạy workload tạo memory pressure nguy hiểm trên hạ tầng dùng chung; chỉ thiết kế kiểm thử được giám sát trên môi trường tách biệt.

## 14. Kubernetes: requests.memory khác limits.memory

Một Pod manifest minh họa:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-memory-study
spec:
  containers:
    - name: app
      image: your-registry/java-memory-probe:21
      resources:
        requests:
          memory: "256Mi"
        limits:
          memory: "512Mi"
```

`your-registry/java-memory-probe:21` là **đường dẫn image minh họa**, cần thay bằng image thật trong registry được cluster truy cập.

Giải thích:

- `requests.memory: "256Mi"`: thông tin giúp scheduler chọn node và thể hiện mức yêu cầu tài nguyên theo chính sách Kubernetes; nó **không tự đặt JVM -Xmx256m**.
- `limits.memory: "512Mi"`: giới hạn bộ nhớ container được kernel/cgroup áp dụng trên Linux node.
- Nếu container memory vượt khả năng kernel reclaim trong giới hạn, process có thể bị OOM kill. Kubernetes thường đánh dấu trạng thái **`OOMKilled`** khi nó xác định được nguyên nhân này.
- Một số cơ chế nâng cao như MemoryQoS có thể áp thêm protection/throttling trên cgroup v2; do đó requests có thể ảnh hưởng cách hệ thống bảo vệ/reclaim khi feature được cấu hình, **nhưng vẫn không đồng nghĩa request là hard limit hoặc Java heap max**.
- Nếu một namespace có `LimitRange`/admission policy, giá trị thực có thể được mặc định/điều chỉnh. Hãy xem Pod **đã được admission** và cgroup của container thay vì chỉ xem YAML ban đầu.

**Không tự gán một giá trị `-Xmx` bằng memory request hoặc memory limit trừ khi quy tắc sizing đã được thiết kế và kiểm thử.** JVM có thể dùng percentage-based ergonomics từ limit mà nó thấy; application vẫn phải dành khoảng trống cho native/GC/threads/cache.

### 14.1. Dashboard “working set” cũng cần xác định nguồn

Một số dashboard Kubernetes/cAdvisor trình bày working set hoặc container memory usage theo cách tính riêng (ví dụ trừ một phần inactive file cache). Đây **không tự bằng** Java heap used, cgroup `memory.current` hoặc RSS của một process. Cần đọc tên metric, định nghĩa và cgroup scope đúng trong stack giám sát.

Không lấy một con số 400 MiB trên dashboard rồi suy `-Xmx` là 400 MiB.

## 15. HotSpot Native Memory Tracking (NMT)

Khi heap used ổn định nhưng container memory tiếp tục tăng, **Native Memory Tracking** có thể giúp phân tích phần internal JVM memory.

Bật NMT ngay khi khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Hoặc khi cần phân rã kỹ hơn:

```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Sau khi có một **process đang chạy đủ lâu** và có JDK `jcmd` phù hợp, dùng:

```bash
jcmd <pid> VM.native_memory summary scale=MB
```

Ký hiệu `<pid>` phải được thay bằng PID thật, không phải literal shell redirection. Có thể tạo baseline và diff:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff scale=MB
```

Trong production, công cụ attach/permissions, Java process identity, container PID namespace, JDK installation và security policy có thể ảnh hưởng việc `jcmd` kết nối được hay không. Image chỉ chứa **JRE** có thể không kèm `jcmd`; dùng image chẩn đoán/JDK phù hợp khi được phép.

### 15.1. NMT đo được và không đo được

NMT ghi nhận những vùng memory nội bộ của HotSpot theo các nhóm như Java Heap, Class, Thread, Code, GC, Compiler, Internal. Nó thường trình bày:

- **Reserved**: dải địa chỉ ảo được đặt trước; không đồng nghĩa toàn bộ đã nằm trong RAM.
- **Committed**: memory JVM đã committed; vẫn không là một bản sao hoàn hảo của `memory.current`/RSS.
- **Category breakdown**: giúp khoanh vùng HotSpot subsystem nào tăng giữa hai thời điểm.

**Giới hạn theo Oracle:** NMT không bao quát mọi allocation của **third-party native code** và một số cấp phát thư viện JDK; nó cũng **không cung cấp thông tin hoàn chỉnh về CDS archive memory**. Vì vậy **NMT tổng committed không nhất thiết bằng RSS hoặc cgroup current**.

NMT có overhead, nhất là `detail`; không bật rộng rãi trên mọi process production nếu chưa cân nhắc tác động hiệu năng và chi phí quan sát.

### 15.2. Native leak khác Java heap leak

Nếu `heap.used` tăng sau mỗi GC và heap dump cho thấy object giữ lại, vấn đề có thể ở object graph Java. Nếu `heap.used` ổn định nhưng RSS/cgroup tăng, kiểm tra native allocator, direct buffers, threads, memory-mapped files, kernel/file cache, hoặc process khác.

**Không phán đoán tuyệt đối:** một Java heap leak cũng có thể làm committed heap/RSS tăng, và GC activity có thể làm native metrics biến động. Phải xem trend nhiều mẫu, breakdown và workload.

## 16. NIO direct buffers và phần còn thiếu trong `nonHeap.used`

`ByteBuffer.allocateDirect` yêu cầu một vùng memory ngoài Java heap cho nội dung bytes. `BufferPoolMXBean` được giới thiệu từ lâu, vẫn tồn tại trong Java SE 17/21 và có:

- `getName()`: tên buffer pool, ví dụ direct/mapped.
- `getCount()`: ước lượng số buffers trong pool.
- `getTotalCapacity()`: tổng capacity bytes.
- `getMemoryUsed()`: ước lượng bytes memory JVM dùng cho pool hoặc `-1` nếu không có giá trị.

`getMemoryUsed()` và `getTotalCapacity()` có thể khác nhau do alignment, allocator và chi tiết triển khai. **Đừng cộng `BufferPoolMXBean` vào `MemoryMXBean.nonHeap.used` như các tập chắc chắn không giao nhau**, hoặc dùng buffer pools để kết luận tất cả off-heap allocations đã được tính.

Khi ứng dụng dùng Netty, JNI hoặc native libraries, có thể có những vùng direct/native không hiện đầy đủ trong buffer pool MXBeans. Khi cần chẩn đoán sâu, phối hợp NMT (với giới hạn của NMT) và công cụ OS như `/proc/<pid>/smaps_rollup`.

## 17. Java OutOfMemoryError khác kernel OOM kill

Đây là phân biệt quan trọng nhất khi thấy ứng dụng “hết bộ nhớ”.

| Triệu chứng | Ai phát hiện trước? | Điều cần xem |
| --- | --- | --- |
| `java.lang.OutOfMemoryError: Java heap space` | JVM/GC không cấp được object trong heap | `heap.used/max`, live objects, GC log, heap dump nếu phù hợp |
| `OutOfMemoryError` liên quan direct buffer memory | JVM không cấp được direct-buffer allocation theo giới hạn/điều kiện | Direct pool, `MaxDirectMemorySize`, native pressure |
| `OutOfMemoryError: Metaspace` | JVM hết khả năng cấp class metadata | Classloaders, metaspace limits, class unloading |
| Native allocation failure | JVM/native allocator không cấp được vùng cần thiết | NMT, native logs, OS limits, virtual address space |
| `OOMKilled` / SIGKILL khi cgroup hết memory | Linux kernel/cgroup OOM enforcement | `memory.max`, `memory.current/peak`, `memory.events`, container runtime/Kubernetes status |
| `exit code 137` | Process bị SIGKILL trong ngữ cảnh shell/container Linux | Cần xác minh nguồn SIGKILL; không mặc định mọi 137 là OOM |

**Kernel OOM kill có thể xảy ra mà Java không kịp ném `OutOfMemoryError` hoặc ghi heap dump.** Ngược lại, JVM có thể ném `OutOfMemoryError: Java heap space` ngay cả khi cgroup còn dư memory vì `-Xmx` đã tới trần.

### 17.1. `memory.events` cần đọc theo delta và scope

Ví dụ file cgroup v2 có thể chứa keys:

```text
low 0
high 0
max 0
oom 0
oom_kill 0
oom_group_kill 0
```

Các keys/version khác có thể xuất hiện; đây **không phải số cố định**.

- `max`: số lần tiến tới hard max boundary theo kernel accounting, không phải số process bị kill.
- `oom`: các sự kiện OOM trong cgroup theo kernel semantics.
- `oom_kill`: số process bị OOM killer kill liên quan cgroup, nhưng không tương đương số lỗi Java `OutOfMemoryError`.
- `high`: liên quan vượt ngưỡng high/reclaim/throttling.

Vì counter có thể cộng dồn từ khi cgroup tồn tại và `memory.events` có thể mang thông tin hierarchical, hãy đo **delta trước/sau** đúng khoảng sự cố và xem `memory.events.local` nếu cần phân biệt sự kiện của cgroup này với descendants.

### 17.2. Vì sao `-Xmx < memory.max` vẫn bị OOM kill?

Giả sử:

```text
cgroup memory.max     = 512 MiB
Java maximum heap     = 384 MiB
Native + metaspace    = ~80 MiB (minh họa)
Other/cache/kernel    = ~80 MiB (minh họa)
Potential combined    = ~544 MiB
```

Các số `~80 MiB` chỉ là ví dụ giả định, không phải ước tính mặc định chuẩn cho mọi JVM. Nhưng chúng cho thấy **có thể vượt limit ngay cả khi Java heap chưa vượt `-Xmx`**. Cần để headroom cho phần ngoài heap và các peak.

Không sửa bằng cách tùy tiện tăng `-Xmx` đến sát limit hoặc tắt OOM killer. Hãy đo resource breakdown và thay cấu hình từ bằng chứng, đồng thời xem nhu cầu throughput/GC.

## 18. Process RSS/PSS không bằng container `memory.current`

Trên Linux, một số công cụ:

```bash
cat /proc/<pid>/smaps_rollup
```

Thay `<pid>` bằng PID thật, chỉ chạy khi bạn có quyền xem process và hệ thống expose `/proc` tương ứng.

- **RSS**: resident pages được tính cho process, bao gồm cả các trang shared có thể bị cộng lặp nếu bạn cộng RSS nhiều process.
- **PSS**: chia tỷ lệ phần shared pages theo số process mapping, thường hữu ích khi so tổng footprint của nhiều process.
- **Private_Dirty/Private_Clean**: giúp xem những trang gắn với riêng process theo OS.
- **Cgroup `memory.current`**: memory được charge cho cgroup và descendants, không phải tổng RSS đơn giản.

Một số trang page cache không được một Java process map vào RSS nhưng vẫn hạch toán trong cgroup. Một số shared pages có thể xuất hiện trong RSS của nhiều process. Vì vậy **không tính `native = memory.current - heap.used`** và không khẳng định tổng RSS của mọi process phải bằng current.

Nếu có nhiều container/sidecar, cần xác định scope của metric và chủ thể nào sở hữu charges. Không cộng `memory.stat.anon + memory.stat.file + memory.stat.shmem` tùy ý vì các field breakdown có phần chồng nhau.

## 19. Thiết kế phép đo đáng tin: cùng thời điểm, cùng scope

### 19.1. Ghi một bản chụp theo từng lớp

Trong một khoảng đo có kiểm soát, thu:

1. **JVM settings**: JDK vendor/build; `-Xms`, `-Xmx`, `MaxRAMPercentage`, `UseContainerSupport`, GC, `MaxDirectMemorySize`, NMT mode.
2. **JVM measurements**: heap used/committed/max, non-heap, direct buffer pools, GC/threads.
3. **Process measurements**: RSS/PSS, native breakdown (nếu được phép), file descriptors/threads khi cần.
4. **Cgroup measurements**: memory.max, current, peak, high, stat keys anon/file/kernel, swap và events.
5. **Kubernetes/Docker**: request/limit đã được áp, cgroup path, container ID/node, restart reason/OOMKilled, image digest.
6. **Workload**: request rate, dữ liệu, tải I/O, GC pauses, thời điểm warm-up và logging.

Không phải mọi nguồn có khả năng cung cấp một snapshot atomic tại cùng nanosecond. Hãy ghi timestamp/time window và tránh đòi tổng các mẫu thu tuần tự phải cân chính xác từng byte.

### 19.2. So baseline và peak

Với một service dài hạn:

- **Sau startup/ready**: đo baseline để thấy class loading và initial heap.
- **Sau warm-up**: đo khi JIT, connection pool và cache đã ổn định.
- **Dưới tải mục tiêu**: đo heap, direct/native, file cache và current/peak.
- **Khi tải giảm**: xem memory có thu hồi không; một heap committed giữ cao không đồng nghĩa leak.
- **Sau GC phù hợp**: xem live heap trend, không ép full GC production chỉ để “giảm RAM cho đẹp”.
- **Trong nhiều replica**: đo từng cgroup/container, tránh lẫn scope với pod/node total.

Một startup process có heap used rất ít nhưng khi hệ thống hoạt động bình thường có thể đạt peak native/cache lớn hơn nhiều. **Không sizing limit chỉ từ số đo startup**.

### 19.3. Cách tính headroom có kiểm soát

Không có tỷ lệ universal “`Xmx` phải bằng 80% memory limit” cho mọi Java service. Chọn headroom bằng quan sát:

```text
Memory budget của container
  >= peak Java heap committed/resident cần thiết
   + peak native/non-heap/direct/thread/GC contribution
   + kernel + file cache + các process cùng cgroup
   + margin cho biến động và burst
```

Đây là **bảng kiểm chi phí**, không phải công thức cộng chính xác có thể lấy trực tiếp từ các metric chồng lấn. Phân tích theo process/cgroup thực tế, giữ margin cho peak/fragmentation và chọn giá trị `-Xmx` hoặc `MaxRAMPercentage` sau benchmark.

Đừng chỉ nhìn max heap và lấy `limit - Xmx` làm “số MiB native còn chắc chắn được phép dùng”: nếu có phần heap chưa resident thì headroom runtime khác, còn kernel có page cache/process khác.

## 20. Thực hành kết hợp `-Xms`, `-Xmx`, NMT và cgroup

Một quy trình vận hành an toàn:

1. Bắt đầu bằng memory limit từ deployment và cgroup thực tế.
2. Dùng percentage sizing hoặc `-Xmx` theo chính sách, giữ đủ native headroom.
3. In `Runtime.maxMemory()`/MemoryMXBean từ **process thật**.
4. Đọc `memory.max/current/stat/events` từ **cgroup của process đó**.
5. Với native pressure, bật NMT có chọn lọc trong environment chẩn đoán.
6. Dùng `jcmd` trên process phù hợp (với permission) để xem native summary/diff.
7. Đọc `memory.stat` và process RSS/PSS để loại trừ file cache/process khác.
8. Phân biệt Java `OutOfMemoryError` với kernel OOM kill dựa trên log và cgroup events.
9. Chạy cùng workload qua nhiều memory limits/heap policies.
10. So peak, tail latency, throughput, error rate, GC time và restart count.
11. Ghi run metadata để tái hiện và quyết định `-Xmx`/memory limit.
12. Cảnh báo trước khi cgroup sát hard limit, xem event trends, không chỉ alert khi OOMKilled.

### 20.1. Lệnh quan sát ở Linux container

```bash
# Trong container có các file cgroup v2:
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events

# JVM/HotSpot:
java -XshowSettings:system -version
java -Xlog:os+container=debug -version
```

Các lệnh này đọc config khác nhau; để đo process đang chạy, còn cần JVM metrics hoặc attach `jcmd` vào process tương ứng. Không lấy output `java -version` của một JVM mới thay số đo heap của service khác.

### 20.2. Không chạy thử OOM nguy hiểm trên máy dùng chung

Để kiểm tra behavior khi limit quá thấp, chỉ làm trong môi trường container/staging có resource limit, giám sát và rollback rõ. Có thể gây SIGKILL, gián đoạn service hoặc đẩy node vào memory pressure nếu cấu hình sai. Bài học tập trung **đối chiếu và chẩn đoán**; không yêu cầu cố tình tạo một allocation vô hạn để “chứng minh” kernel OOM.

## 21. Trường hợp đặc biệt và bẫy diễn giải

### 21.1. `memory.max=max` nhưng JVM heap có giới hạn

Một cgroup không đặt hard limit trong `memory.max` vẫn bị giới hạn bởi host/ancestor hoặc flags JVM; `Runtime.maxMemory()` có thể chỉ vài GiB do `MaxRAMPercentage` hoặc `-Xmx`. Không suy “không giới hạn” là có thể dùng RAM vô tận.

### 21.2. `MemoryUsage.getMax() == -1`

Theo Java management API, `-1` có thể nghĩa **không xác định** đối với một memory pool/area. Không đổi thành “-1 MiB dung lượng” hoặc “vô hạn chắc chắn”. Để in report, bài dùng `unknown`.

### 21.3. NMT `reserved` cực lớn

JVM có thể reserve một vùng **virtual address space** lớn trong khi committed và resident nhỏ hơn nhiều. Nếu NMT nói reserved 4 GiB, không khẳng định nó đã chiếm 4 GiB physical RAM.

### 21.4. `heap.committed` cao nhưng heap used giảm sau GC

JVM không phải luôn lập tức trả committed heap pages lại cho OS sau mỗi GC. Một số collectors có chính sách shrink/uncommit khác nhau. Heap committed cao và heap used thấp trong một khoảng thời gian chưa đủ chứng minh leak.

### 21.5. Heap used ổn định, `memory.current` tăng

Kiểm tra native allocations, direct/mapped, threads, page cache, kernel charges hoặc process khác. Nếu `memory.stat.file` tăng, đây có thể là tác động I/O. Nếu `anon` tăng, cần nhìn process/NMT/OS breakdown; không tự xác định ngay nguyên nhân.

### 21.6. Kubernetes working set thấp hơn `memory.current`

Một số metric working-set loại trừ một phần inactive file cache theo định nghĩa riêng. Con số khác nhau không nhất thiết bug; cần xem metric implementation và kernel charge. Cơ chế OOM vẫn do cgroup limit/pressure thực tế, không đơn thuần ngưỡng dashboard đang vẽ.

### 21.7. `memory.events.oom_kill` không tăng nhưng container restart

Có thể do health check, app exception, manual restart, node eviction hoặc một cơ chế khác. Exit 137 thường tương ứng SIGKILL, nhưng **không đủ chứng minh** memory cgroup OOM mà không xem reason/events/logs.

### 21.8. Limit thay đổi trong khi JVM đang chạy

JVM có thể xác định heap maximum và một số ergonomics lúc startup. Thay cgroup memory limit khi process đang chạy **không bắt buộc làm `Runtime.maxMemory()` được chọn lại tương ứng**, và Java heap cap có thể vẫn cố định. Khi điều chỉnh chính sách memory, hãy xác minh có cần restart JVM và đo lại process thật.

### 21.9. Mapped files và shared pages

Các trang CDS/AppCDS, shared libraries và memory-mapped files có thể xuất hiện trong RSS của nhiều JVM. **Cộng RSS tất cả JVM dễ đếm lặp shared pages**, còn cgroup có cơ chế charge riêng. Với nhiều JVM, PSS/private memory và cgroup accounting thường hữu ích hơn một phép cộng đơn giản.

### 21.10. Swap và container OOM

Nếu swap bật, một phần anonymous pages có thể bị swap làm latency tăng; nếu swap bị hạn chế, OOM có thể xảy ra sớm hơn. Docker `--memory-swap` có semantics **RAM+swap** khi sử dụng với `--memory`. Không khẳng định một memory limit tự tắt swap trong mọi cấu hình.

## 22. Những nhầm lẫn phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`-Xmx=512m` nghĩa container chỉ dùng tối đa 512 MiB.” | `-Xmx` giới hạn Java heap, không giới hạn RSS/native/cache |
| “`MemoryMXBean.heap.used` là `memory.current`.” | Một số đo JVM heap, một số đo toàn cgroup |
| “Heap used + nonHeap used = toàn bộ JVM RSS.” | NonHeap MXBean không bao hết native; RSS còn phụ thuộc pages/mappings |
| “`Runtime.freeMemory()` là RAM còn trống của pod.” | Là phần chưa dùng trong Java heap đã cấp |
| “Heap max bằng heap used hiện tại.” | Max là capacity, used là tại thời điểm đo |
| “`-Xms` luôn nằm toàn bộ trong RAM resident.” | Initial heap/committed không đồng nghĩa resident pages |
| “`MaxRAMPercentage` đặt hard limit của container.” | Chỉ ảnh hưởng sizing Java heap của JVM |
| “`MaxRAMPercentage=50` luôn trả chính xác 50% trên mọi JDK.” | Ergonomics/GC/alignment và runtime ảnh hưởng |
| “Đã đặt `-Xmx` thì JVM không cần chừa native headroom.” | Vẫn cần metaspace, threads, GC, direct buffers và cache |
| “`MaxDirectMemorySize` giới hạn mọi off-heap memory.” | Chỉ điều khiển một phần direct buffer memory của JVM |
| “`MemoryMXBean.nonHeap` chứa mọi JNI allocation.” | Không |
| “NMT committed bằng container current.” | NMT chưa bao phủ third-party/JDK library, kernel/file cache và accounting khác |
| “NMT reserved là RAM vật lý đã dùng.” | Reserved là virtual address space |
| “`memory.max=max` có nghĩa host RAM vô hạn.” | Có thể có ancestor/host limits |
| “`memory.current` chỉ có một Java process.” | Gồm cgroup + descendants và có thể nhiều process/cache |
| “`memory.stat.file` là toàn bộ leak của Java heap.” | Có thể là page cache/tmpfs/shared memory |
| “Có thể cộng mọi field `memory.stat` để ra total.” | Một số field là breakdown chồng lấn |
| “K8s request 256Mi tự đặt `-Xmx256m`.” | Request chủ yếu dùng scheduling/resource policy, không set Xmx |
| “Memory limit sẽ làm JVM ném OutOfMemoryError trước kernel kill.” | Kernel có thể SIGKILL process mà không có Java exception |
| “Exit 137 luôn là OOMKilled.” | Cần thêm OOM event/reason; SIGKILL có nhiều nguồn |
| “Java heap OOME có nghĩa container đã chạm limit.” | Heap có thể hết `-Xmx` dù cgroup còn headroom |
| “Cgroup v1 và v2 dùng cùng tên file.” | Khác interface/path và một số semantics |
| “`memory.peak` luôn là peak từ lúc app start.” | Theo lifetime/reset của cgroup, không nhất thiết trùng app |
| “`-XshowSettings:system` trên Windows phải có cgroup.” | Linux container detection phụ thuộc platform |
| “Có Docker CLI là đã có Docker Engine và Linux cgroup.” | Không; daemon/runtime phải hoạt động |
| “Số liệu heap và container phải bằng byte-for-byte.” | Khác phạm vi, loại memory và thời điểm lấy mẫu |
| “Một lần số đo startup đủ sizing production.” | Cần đo peak/trend dưới workload đại diện |
| “OOM của native leak sẽ thấy hết trong NMT.” | NMT không bao hết third-party native/JDK library allocations |

## 23. Bài tập và đáp án

### Bài 1 — Ba số khác nhau

`heap.max=256 MiB`, `heap.used=90 MiB`, `memory.current=390 MiB`. Có lỗi đo không?

**Đáp án:** chưa có bằng chứng lỗi. Heap max là giới hạn/capacity, heap used là usage object heap, còn cgroup current gồm nhiều vùng native, cache, kernel và có thể process khác.

### Bài 2 — Chọn đúng công cụ

Muốn biết maximum Java heap đã được JVM chọn khi chạy pod, nên gọi gì?

**Đáp án:** `Runtime.getRuntime().maxMemory()` hoặc `MemoryMXBean.heap.max` từ **chính process đó**, đối chiếu với `-XX:+PrintFlagsFinal`/startup flags. Không suy từ Kubernetes `requests.memory`.

### Bài 3 — Container giới hạn 512 MiB

Dùng `-Xmx500m` đã chắc an toàn?

**Đáp án:** không. JVM còn dùng native/non-heap/threads/GC, file cache và kernel charges. Phải đo peak và chừa headroom; không có một tỷ lệ tối ưu cố định.

### Bài 4 — Percentage vs absolute

Cùng image, `MaxRAMPercentage=50`, tăng container limit từ 512 MiB lên 1 GiB. Heap max chắc chắn cố định 256 MiB?

**Đáp án:** không. Nếu JVM phát hiện limit và dùng percentage ergonomics, heap maximum thường có thể tăng. Với `-Xmx256m` tường minh, trần heap không được tự tăng chỉ vì đổi limit.

### Bài 5 — Cgroup `memory.max`

File trả `536870912`. Giới hạn là bao nhiêu MiB?

**Đáp án:** 512 MiB vì `536870912 / 1_048_576 = 512`.

### Bài 6 — Cgroup `memory.high`

`memory.high=400 MiB`, `memory.max=512 MiB`. Cái nào là hard limit?

**Đáp án:** `memory.max`. `high` là ngưỡng reclaim/throttling theo memory controller, không phải hard cap giống max.

### Bài 7 — Swap

Một container có `memory.current=400 MiB`, `memory.swap.current=100 MiB`. Có được gọi RSS của JVM là 500 MiB không?

**Đáp án:** không. Cgroup memory và swap accounting khác process RSS, và có thể có nhiều process/charge. Phải định nghĩa chỉ số đang tính.

### Bài 8 — File cache

`heap.used` không đổi, `memory.stat.file` và `memory.current` cùng tăng sau khi service đọc nhiều file. Có thể kết luận Java heap leak không?

**Đáp án:** không. File cache có thể làm usage cgroup tăng. Tiếp tục đo anon/native/heap trend và xem reclaim behavior.

### Bài 9 — NMT

NMT báo `reserved=8 GiB`, `committed=350 MiB`. Có chắc JVM đã chiếm 8 GiB RAM vật lý?

**Đáp án:** không. Reserved là địa chỉ ảo, không đồng nghĩa resident pages.

### Bài 10 — Java heap OOME

JVM ném `OutOfMemoryError: Java heap space` nhưng `memory.current` chỉ bằng 55% memory.max. Vì sao?

**Đáp án:** có thể chạm `-Xmx` trước khi container hết RAM. Nâng container limit riêng lẻ không tự làm heap cap của JVM tăng nếu `-Xmx` đã cố định.

### Bài 11 — OOMKilled

Kubernetes ghi `OOMKilled`, không có Java stack trace OOME. Có vô lý không?

**Đáp án:** không. Kernel có thể kill process khi cgroup hết memory trước khi JVM kịp ném/catch exception. Xem `memory.events`, peak/limit và container reason.

### Bài 12 — Direct buffer

Trong `HeapDirectFootprintDemo`, 8 MiB direct buffer có nhất thiết nằm trong Java heap used không?

**Đáp án:** không. Nội dung direct buffer là memory ngoài heap; `BufferPoolMXBean` có thể báo memory used của direct pool. Java object wrapper vẫn có thể nằm trong heap.

### Bài 13 — Parent cgroup

`memory.max=max` ở cgroup hiện tại. Có thể kết luận không có hard limit nào không?

**Đáp án:** không. Parent/ancestor cgroups hoặc node RAM vẫn có thể giới hạn.

### Bài 14 — Nhiều JVM

Hai JVM cùng map shared pages; cộng RSS của chúng có thể đếm lặp không?

**Đáp án:** có. PSS giúp phân bổ shared pages, còn cgroup memory.current là bộ đo cấp cgroup.

### Bài 15 — Cgroup v1

Trên hệ thống không có `/sys/fs/cgroup/memory.max` nhưng có `memory.limit_in_bytes`. Có phải Java bỏ qua memory limit?

**Đáp án:** không thể kết luận. Có thể đó là cgroup v1; đọc controller/path và JVM container log phù hợp.

### Bài 16 — CI test

Nên assert `memory.current == heap.used` trên mọi runner để phát hiện leak?

**Đáp án:** không. Chúng đo hai miền khác nhau. Assert correctness, API invariants và giám sát trend/threshold từ thực nghiệm trên workload đại diện.

### Bài 17 — NMT limitation

NMT không thấy mức tăng đến từ thư viện C bên thứ ba. Có phải OS metrics chắc chắn sai?

**Đáp án:** không. NMT không bao hết third-party native allocations. Dùng công cụ OS/profiler của allocator nếu cần.

### Bài 18 — Tăng limit lúc runtime

Container limit tăng, nhưng `Runtime.maxMemory()` của JVM đang chạy không đổi. Có phải JVM bug?

**Đáp án:** không nhất thiết. Maximum heap và ergonomics có thể được chọn lúc startup. Xác minh flags/version và cân nhắc restart nếu chính sách mới cần heap cap khác.

## 24. Checklist triển khai và vận hành

1. **Đang đọc `-Xmx`, heap used hay container memory?** Ghi rõ phạm vi từng số.
2. Đã ghi JDK vendor/build, GC, image digest, JVM arguments và env flags?
3. Đã biết host dùng cgroup v1, v2 hay layout khác?
4. Có đọc đúng `memory.max`/`memory.limit_in_bytes` của process/cgroup?
5. Có kiểm tra ancestor limits, swap và container policy?
6. Có phân biệt request với hard limit Kubernetes không?
7. Có dùng `Runtime.maxMemory`/MemoryMXBean để xác minh heap thật?
8. Có hiểu `Runtime.freeMemory` không phải container free RAM?
9. Có phân biệt heap used, committed, max không?
10. Có xem memory non-heap không bao hết native allocations?
11. Có xem direct buffers và native library footprint khi cần?
12. Có dùng `-XX:MaxRAMPercentage` hoặc `-Xmx` theo chính sách rõ?
13. Có tránh deprecated Fraction flags trong code/config mới?
14. Có giữ headroom cho metaspace, JIT, stacks, GC và page cache?
15. Có kiểm tra `UseContainerSupport` và log phát hiện cgroup khi nghi ngờ?
16. Có đo container current/peak/stat/events theo cùng scope/timestamp?
17. Có tránh cộng trùng `heap`, NMT, RSS và cgroup counters không?
18. Có phân tích `memory.stat.file`/`anon`/`kernel` nếu container current cao?
19. Có đọc `memory.events.oom/oom_kill` theo delta và đúng hierarchy?
20. Có phân biệt Java OOME với cgroup OOMKilled và exit 137 không?
21. Có bật NMT đúng lúc và hiểu nó không bao hết thư viện bên thứ ba?
22. Có đọc NMT committed khác virtual reserved không?
23. Có xem RSS/PSS/private thay vì tổng RSS nhiều JVM?
24. Có chạy cùng app/JDK/workload khi so memory limits và heap policies?
25. Có đo startup, steady state và peak dưới tải đại diện?
26. Có xét GC policy, virtual threads/platform threads và native caches không?
27. Có giữ image/JAR/JDK không đổi khi benchmark container limit?
28. Có tránh test OOM vô hạn trên shared production/CI runner không?
29. Có log metadata đủ để đối chiếu phiên bản sau nâng JDK?
30. Có chính sách alert và restart/rollback khi memory pressure hoặc OOM?
31. Có tránh dựa vào một snapshot ở thời điểm JVM còn idle?
32. Có hiểu working-set dashboard không tự bằng cgroup current hoặc Java heap?

## 25. Tổng kết

**Cấu hình JVM và chỉ số bộ nhớ container phải được đối chiếu, không được đồng nhất.** `-Xmx`/`MaxRAMPercentage` quyết định sức chứa Java heap; `MemoryMXBean` báo các vùng heap/non-heap của JVM; `BufferPoolMXBean` giúp theo dõi một phần direct/mapped memory; HotSpot NMT phân tích một phần memory nội bộ. Trong khi đó, Linux cgroup `memory.max/current/peak/stat/events` quản lý và ghi nhận **bộ nhớ của cgroup**, có thể gồm native memory, file cache, kernel charges và nhiều process.

Java 10 đánh dấu bước mở rộng phát hiện tài nguyên container của HotSpot, nhưng hướng dẫn hiện đại phải dùng cgroup v1/v2 đúng môi trường, flags percentage/absolute còn được hỗ trợ, công cụ NMT/JDK hiện hành và Kubernetes memory requests/limits đúng nghĩa. **Heap used thấp không bảo đảm container còn nhiều memory; -Xmx thấp hơn memory.max cũng không bảo đảm tránh OOMKilled.**

Để vận hành có căn cứ: thu **JVM heap + non-heap/native + process RSS/PSS + cgroup limit/current/stat/events** trong cùng giai đoạn tải, hiểu phạm vi và giao nhau của số đo, phân biệt Java OOME với kernel OOM, sau đó mới chọn heap policy, memory limit và alert thresholds. Những ví dụ Java 17+ cho thấy cách xuất các thông tin cạnh nhau mà không đưa ra một “đẳng thức bộ nhớ” sai.

### Tài liệu tham khảo chính thức còn áp dụng

- [Oracle Java SE 21 — The java Command: MaxRAMPercentage, InitialRAMPercentage, UseContainerSupport, NativeMemoryTracking](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle Java SE 17 — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html)
- [Oracle Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Oracle Java SE 21 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Oracle Java SE 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html)
- [Linux Kernel — Control Group v2 Memory Controller](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)
- [Docker — Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/)
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [OpenJDK JDK-8146115 — Improve Docker container detection](https://bugs.openjdk.org/browse/JDK-8146115)
- [Oracle Java SE 21 — jcmd command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)