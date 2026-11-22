# Java 10 – Bộ nhớ trong container: Kiểm thử giới hạn bộ nhớ theo tải và số luồng thực tế

> **Ngữ cảnh:** Java 10 → **Bộ nhớ trong container** → **Kiểm thử giới hạn bộ nhớ theo tải và số luồng thực tế**. Java 10 đánh dấu cải tiến nhận diện CPU/RAM của Docker/Linux container trong HotSpot (JDK-8146115). Bài học sử dụng kiến thức **vẫn áp dụng trên JDK 17+ và các JDK hiện đại**: kiểm memory cgroup, tải đồng thời, số platform threads thật, heap/off-heap/native memory, Native Memory Tracking (NMT), Kubernetes OOMKilled và giám sát peak. Ví dụ Java được biên dịch bằng `javac --release 17` và chạy kiểm chứng trên OpenJDK 21. Java 10 là mốc lịch sử, **không phải JDK khuyến nghị cho production mới**.

## 1. Mục tiêu và nguyên tắc

Bạn sẽ biết cách:

1. Phân biệt **container memory limit**, Java heap `-Xmx` và tổng memory mà kernel thực tính.
2. Đo **memory peak** dưới các mức tải và **số worker threads đang sống** khác nhau.
3. Tách **Kubernetes memory request** khỏi **memory limit**.
4. Đọc Linux cgroup v2: `memory.max`, `memory.current`, `memory.peak`, `memory.high`, `memory.events`, `memory.stat`, `memory.swap.max`.
5. Đọc cgroup v1: `memory.limit_in_bytes`, `memory.usage_in_bytes`, `memory.max_usage_in_bytes`, `memory.failcnt`.
6. Dùng `-XshowSettings:system` và `-Xlog:os+container=trace` để kiểm HotSpot đã nhận resource limits thế nào trên Linux hỗ trợ.
7. Phân biệt **heap used/committed/reserved**, **NMT native committed/reserved**, **RSS/PSS** và **cgroup memory.current**.
8. Hiểu tác động của **platform thread stacks**, `-Xss`, direct buffers, JNI, metaspace, GC/JIT memory và page cache.
9. Bật `-XX:NativeMemoryTracking=summary` rồi lấy `jcmd PID VM.native_memory summary` hoặc `summary.diff`.
10. Phân biệt Java `OutOfMemoryError` với kernel `OOMKilled` và lý do exit 137 không đủ kết luận.
11. Giải thích vì sao số thread pool cấu hình khác số **live platform threads**, và virtual threads Java 21+ không có OS stack riêng 1:1.
12. Dựng thí nghiệm hai mức tải bằng Java 17+, xem stdout đã kiểm chứng và bản NMT quan sát.
13. Thiết kế ma trận load test an toàn, đo cả peak, concurrency, GC, latency và OOM events trước/sau.

**Kết luận:** `-Xmx128m` **không** giới hạn Java process ở 128 MiB tổng RAM. Ngược lại, báo cáo NMT có thể ghi **hàng GiB “reserved”** nhưng chỉ một phần nhỏ **committed/resident**. Phải đo ở **cả JVM và Linux cgroup**, tại **đúng thời điểm workload và threads còn sống**.

## 2. Vì sao Java 10 có liên quan?

HotSpot trước đây có thể suy resource ergonomics từ RAM/CPU của **host**, dù Java process chạy trong Docker với một giới hạn nhỏ hơn. Java 10 đưa vào cải tiến **JDK-8146115 – Improve docker container detection and resource configuration usage**, để JVM nhận diện những giới hạn container từ Linux cgroups khi được hỗ trợ.

Trong HotSpot/Linux, `UseContainerSupport` là cơ chế đã được bật mặc định ở các bản thích hợp. JDK về sau tiếp tục cải thiện hỗ trợ, đặc biệt **cgroups v2** và cách tính CPU/heap. Không thể giả định behavior của JDK 10 giống hệt JDK 17, 21 hay 25.

**Kiến thức còn áp dụng:** JVM cần biết resource limits; heap không chiếm toàn bộ process memory; kernel có thể OOM kill dù JVM chưa chạm `-Xmx`; cần xét số thread thực tế và peak tải.

**Không áp dụng mẹo lỗi thời:** không dùng `-XX:+UseCGroupMemoryLimitForHeap` như lời khuyên triển khai hiện đại; không vô hiệu `UseContainerSupport` chỉ để JVM nhận nhiều RAM host hơn. Hãy dùng JDK còn được hỗ trợ và kiểm version/update thực tế.

Nguồn: [Oracle JDK 10 Release Notes](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html), [Oracle JDK 25 Java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).

## 3. Một Java process sử dụng những loại memory nào?

~~~text
Container/cgroup memory accounting
├── Java heap: objects, arrays, active requests, caches
├── JVM native/off-heap
│   ├── Metaspace và class metadata
│   ├── Code cache, JIT compiler, GC structures
│   ├── Platform thread stacks và runtime thread data
│   ├── Direct ByteBuffer / buffers / JNI native allocations
│   └── Native libraries, TLS, memory mappings
├── File-backed pages/page cache/tmpfs được tính theo kernel rules
├── Kernel accounting và những chi phí liên quan
└── Các process khác trong cùng cgroup (nếu có)
~~~

Bản đồ này chỉ giúp hiểu các nhóm: **không** lấy số báo cáo của những công cụ khác phạm vi rồi cộng thô, vì cgroup accounting, RSS, virtual memory và NMT có thể đếm/định nghĩa khác nhau.

| Số đo | Đo cái gì? | Không được suy ra |
| --- | --- | --- |
| `-Xmx` | Mức trần Java heap JVM cấu hình | Giới hạn cả container |
| `Runtime.maxMemory()` | Giá trị heap max từ Java API | Tổng native/RSS |
| Heap used | Heap object space đang dùng | Heap reserved, container current |
| Heap committed | Vùng heap VM đã cam kết cung cấp | Tất cả bytes đều resident |
| NMT reserved | Không gian địa chỉ ảo JVM reserve | RAM vật lý thực đang dùng |
| NMT committed | Memory JVM native tracking đã commit | Toàn bộ process RSS/cgroup |
| RSS | Resident pages trong process | Tổng physical RAM duy nhất khi có shared pages |
| PSS | Resident shared pages được chia tỷ lệ cho process | Cgroup total nếu có page cache/kernel |
| `memory.current` | Memory hiện được charge cho cgroup/descendants | Java heap used |
| `memory.peak` | Peak cgroup memory theo mốc kernel theo dõi | Giá trị current |
| `memory.events` | Các counters pressure/limits/OOM của cgroup | Số Java exceptions |

### 3.1. Vì sao `-Xmx` bằng limit thường nguy hiểm?

Nếu container limit là 512 MiB và JVM được đặt `-Xmx512m`, **không còn khoảng dự phòng rõ ràng** cho metaspace, code cache, GC, thread stacks, direct memory và các memory charge khác. Container có thể bị kernel kill trước khi Java heap đạt max.

Một giá trị thử như `-Xmx256m` có thể dành headroom, nhưng **không tự chứng minh đủ**: phải đo memory peak với framework/workload thật. Một web server có 1000 platform threads, nhiều direct buffers hoặc JNI native allocations có thể khác rất xa một JVM nhỏ chỉ chạy `main`.

## 4. Kubernetes request/limit khác nhau

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: memory-lab
spec:
  containers:
    - name: app
      image: eclipse-temurin:21-jdk
      resources:
        requests:
          memory: 256Mi
          cpu: 500m
        limits:
          memory: 512Mi
          cpu: "2"
      command: ["java", "-Xms64m", "-Xmx128m", "-version"]
~~~

Đây là **manifest cấu trúc minh họa**, không phải mô hình production khuyến nghị hay lệnh kiểm tải thực. Khi triển khai, cần pin image/digest và cấu hình theo policy.

- **Memory request 256Mi:** tài nguyên dùng cho scheduler/resource policy; không phải hard memory cap.
- **Memory limit 512Mi:** giới hạn memory do container runtime và kernel thực thi, thường dẫn tới **OOM kill** nếu memory không reclaim được khi bị áp lực.
- **CPU limit:** ảnh hưởng tốc độ thực thi GC/ứng dụng và thời gian in-flight requests giữ memory, nhưng không thay thế memory limit.
- **512Mi** là 512 × 1.048.576 bytes; phân biệt Mi (base 2) với M (base 10).

Kubernetes ghi rõ memory limits được thực thi theo **memory pressure phản ứng**, không phải luôn ném Java exception ngay khi vượt một byte. Một cgroup có thể tạm vượt hard limit trong những điều kiện kernel cho phép; khi không reclaim được, OOM killer được sử dụng.

### 4.1. Đọc tài nguyên đúng nơi

~~~bash
kubectl get pod memory-lab -n java-lab -o yaml
kubectl describe pod memory-lab -n java-lab
~~~

Chỉ chạy khi Pod/namespace đó tồn tại và có quyền. Kubernetes admission/LimitRange có thể thêm default request/limit, vì vậy đọc **Pod spec thực tế sau admission**. Trong Pod có nhiều containers, không lấy giới hạn sidecar hoặc host thay cho Java container.

## 5. Cgroup v2: đo hard limit, current và peak

Với unified cgroup v2, trong Linux container có mount phù hợp có thể đọc:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.high
cat /sys/fs/cgroup/memory.events
~~~

Đường dẫn `/sys/fs/cgroup` là ví dụ phổ biến, **không phải đảm bảo** cho mọi mount namespace/nested cgroup. Nếu thiếu hoặc nghi đọc nhầm, xác định cgroup path của **đúng Java PID** thông qua `/proc/self/cgroup`, `/proc/PID/cgroup` và mountinfo trong điều kiện được phép.

### 5.1. `memory.max` là hard cap

Ví dụ output:

~~~text
536870912
~~~

Tương đương **512 MiB**. Nếu là:

~~~text
max
~~~

nghĩa là cgroup **không có hard memory limit tại cấp đó**, không phải hệ thống có RAM vô hạn: ancestor constraints, host memory và node competition vẫn có thể giới hạn nó.

### 5.2. `memory.current` là cgroup memory charge

Nó có thể gồm memory của các process trong cgroup/descendants, anonymous pages, file cache/tmpfs và một phần kernel charge. Nó không bằng Java `Runtime.totalMemory()`, không đồng nhất với `-Xmx` và **không phải chỉ JVM heap used**.

Nếu `memory.current` tăng còn heap used ổn, điều tra **direct/native memory, mmap/file cache, sidecars, tmpfs** trước khi kết luận heap leak.

### 5.3. `memory.peak` cho đỉnh tải

`memory.peak` (khi kernel hỗ trợ) theo dõi mức usage cao nhất theo semantics của kernel, giúp phát hiện burst mà một scraper 30–60 giây có thể bỏ lỡ. Nếu không có file, dùng peak metrics từ giám sát hoặc tương đương cgroup v1. Không coi file vắng mặt là peak=0.

### 5.4. `memory.high` không phải `memory.max`

`memory.high` là ngưỡng kích hoạt reclaim/throttle khi quá mức; `memory.max` là hard memory limit bảo vệ cuối. High pressure có thể làm **latency tăng** trước khi kernel thật sự OOM kill. Không gộp hai file thành “memory limit” duy nhất.

### 5.5. `memory.events` và OOM

~~~text
low 0
high 3
max 2
oom 1
oom_kill 1
oom_group_kill 0
~~~

Đây là **output minh họa định dạng**, không phải số thực lấy từ Pod người học.

- `high`: số lần cgroup chịu high-boundary reclaim/throttling theo kernel.
- `max`: sự kiện memory usage sắp/vượt max boundary và phải thử reclaim.
- `oom`: điều kiện OOM theo định nghĩa kernel, không phải Java exception counter.
- `oom_kill`: số tiến trình của cgroup bị OOM killer giết theo kernel accounting.
- `oom_group_kill`: các group kill khi kernel/policy hỗ trợ.

`memory.events` có tính **hierarchical**, còn `memory.events.local` phản ánh cgroup hiện tại khi interface hỗ trợ. Chỉ số events **tích lũy**, nên đo trước/sau một lượt tải và lấy delta thay vì nhìn một số cũ rồi gán nó cho sự cố mới.

### 5.6. `memory.stat` giúp giải thích thành phần

~~~bash
grep -E '^(anon|file|kernel|shmem|slab|sock) ' \
  /sys/fs/cgroup/memory.stat
~~~

- `anon`: anonymous mappings, có thể gồm phần Java heap/native anonymous memory.
- `file`: filesystem page cache, tmpfs/shared memory tùy accounting.
- `kernel` và các subfields như `slab`/`sock`: memory kernel charge.
- Các trường có thể là **tổng/tiểu mục chồng lấn**; không cộng vô điều kiện.

### 5.7. Swap là quy định khác

~~~bash
cat /sys/fs/cgroup/memory.swap.current
cat /sys/fs/cgroup/memory.swap.max
~~~

`memory.swap.max` hạn chế swap usage, không phải cơ chế tự động cộng thêm RAM vào `memory.max`. Swap/page faults có thể ảnh hưởng latency; không dùng swap để che memory leak.

Nguồn: [Linux Kernel – cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html).

## 6. Cgroup v1 có tên file và cách tính khác

Với cgroup v1, có thể gặp:

~~~text
memory.limit_in_bytes
memory.usage_in_bytes
memory.max_usage_in_bytes
memory.failcnt
memory.stat
memory.oom_control
~~~

Ví dụ path trên một kiểu Linux mount cũ:

~~~bash
cat /sys/fs/cgroup/memory/memory.limit_in_bytes
cat /sys/fs/cgroup/memory/memory.usage_in_bytes
cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes
cat /sys/fs/cgroup/memory/memory.failcnt
~~~

Không phải mọi host mount controller tại path này. `memory.limit_in_bytes` đôi khi dùng **giá trị sentinel rất lớn** khi không giới hạn; đừng coi đó là RAM thực. `memory.usage_in_bytes` có thể được kernel tính gần đúng bằng batching; `memory.failcnt` không phải số OOM kills. V1 `memory.stat` có field/semantics khác V2; không dùng parser chung rồi kết luận sai.

Hỗ trợ cgroups v2 trong HotSpot được bổ sung sau Java 10 và có backports tùy JDK update. Hãy kiểm đúng **JDK version/vendor/update + cgroup provider** thay vì suy cả Java 10 và Java 21 luôn có cùng khả năng.

## 7. JVM nhìn thấy memory limit như thế nào?

Trên HotSpot/Linux hỗ trợ:

~~~bash
java -version
java -XshowSettings:system -version
java -XshowSettings:vm -version
java -Xlog:os+container=trace -version
java -XX:+PrintFlagsFinal -version
~~~

- `-XshowSettings:system`: thông tin OS/cgroup metrics khi được JVM hỗ trợ.
- `-XshowSettings:vm`: thông tin VM/ước tính heap.
- `-Xlog:os+container=trace`: log chi tiết Linux container detection, có thể không có tag trên Windows.
- `-XX:+PrintFlagsFinal`: flags thực tế như `MaxHeapSize`, `MaxRAMPercentage` và `UseContainerSupport` nếu runtime expose.
- `-Xmx`: explicit heap max; `-XX:MaxRAMPercentage`: heap sizing theo tỷ lệ của RAM mà JVM dùng làm cơ sở ergonomics.

### 7.1. `UseContainerSupport=true` chưa chứng minh đã đọc đúng limit

Flag chỉ cho phép detection. Nếu JVM chạy trên host, Linux cgroup không có limit, Windows không có container metrics tương ứng hoặc JDK không hỗ trợ cgroups v2 version đang dùng, output có thể khác.

Không khuyên tắt `-XX:-UseContainerSupport` trong production chỉ để tăng heap: JVM có thể lấy giới hạn host không phù hợp với Pod.

### 7.2. `MaxRAMPercentage` không giới hạn RSS

~~~bash
java -XX:MaxRAMPercentage=50.0 -jar app.jar
~~~

Có thể khiến JVM chọn Java heap max theo tỷ lệ RAM/limit mà nó nhận diện. Nhưng nó **không** giới hạn code cache, native allocations, thread stacks, mmap, JNI hoặc page cache. Nếu đã đặt `-Xmx` rõ, kiểm final `MaxHeapSize` thay vì giả định ratio vẫn được dùng đúng như mong đợi.

**Quy trình hợp lý:** đọc cgroup limit → xem giá trị heap max JVM chọn → đo heap/native/cgroup dưới peak tải → chỉnh heap/thread/buffer limits theo chứng cứ.

## 8. Vì sao số platform threads rất quan trọng?

Một **platform thread** thường tương ứng native OS thread trong HotSpot, có thread stack và native bookkeeping. Khi app tạo nhiều workers, có thể tăng **stack virtual reservations**, một phần **committed/resident** và các objects gắn với từng request.

Ví dụ:

~~~bash
java -Xss512k -jar app.jar
~~~

`-Xss512k` điều khiển mức stack size theo VM/OS rules. **Không được suy** “100 threads × 512 KiB = chính xác 50 MiB RSS ngay khi tạo”. Stack **reserved**, **committed** và **resident** khác nhau; JVM còn có GC/JIT/service threads và guard pages. Hạ `-Xss` quá thấp có thể gây `StackOverflowError`.

### 8.1. Configured max không phải live thread count

Một thread pool max=100 có thể hiện chỉ tạo 12 threads; ngược lại app có thể có thêm HTTP workers, schedulers, database pools, GC threads, JIT/compiler threads. Đo:

- Max workers cấu hình.
- **Current/peak live platform threads**.
- Số requests/tasks active và queued.
- Thread stack config `-Xss` và native committed.
- Per-request Java heap data, direct buffers và ThreadLocal context.

### 8.2. Virtual threads Java 21+ khác platform threads

Virtual threads (JEP 444) không giữ một dedicated kernel thread/OS stack trong toàn bộ vòng đời; carrier platform threads chạy các virtual tasks. Vì vậy không nhân `virtualThreadCount × Xss` như native stacks. Nhưng **request state, byte arrays, continuation state và buffers vẫn chiếm heap/native memory**. Không có quyền mở concurrency vô hạn chỉ vì dùng virtual threads.

`ThreadMXBean.getThreadCount()` chỉ đếm **platform threads**, không phản ánh mọi virtual threads. Với workload Java 21+, cần thêm metric active virtual tasks/in-flight operations và application buffers.

## 9. Các nguồn memory ngoài heap dễ gây OOM

| Nguồn | Khi nào tăng | Quan sát |
| --- | --- | --- |
| Metaspace | Class loading, proxy/generated classes, classloader leaks | NMT Class, JFR/classloading |
| JIT/code cache | Hot methods, compiler data | NMT Code, VM flags |
| GC structures | Heap size/collector, remembered sets, marking | NMT GC, GC logs |
| Native thread stacks | Tăng live platform threads, call depths | NMT Thread + OS |
| Direct ByteBuffer | Network I/O, pools, binary processing | `BufferPoolMXBean`, NMT phù hợp |
| JNI/native libs | Native drivers/codecs/TLS, allocator arenas | OS RSS/maps; NMT không bao phủ hết |
| File-backed/CDS pages | Mapped files/class-data sharing | PSS, cgroup file accounting |
| Tmpfs/page cache | Disk I/O, shared memory, temporary files | `memory.stat file/shmem` |
| Sidecar/agent | Process khác trong phạm vi tính memory | cgroup/process tree |

### 9.1. `MaxDirectMemorySize`

~~~bash
-XX:MaxDirectMemorySize=16m
~~~

Giới hạn nhóm **NIO direct-buffer memory** theo JVM implementation, không phải mọi native allocation. Một app có thể bị `OutOfMemoryError` về direct buffer trong khi Java heap vẫn còn rảnh.

### 9.2. Số platform threads không dự báo mọi native memory

Nhiều threads làm tăng stack reservations và bookkeeping, nhưng mỗi worker còn có thể giữ mảng Java, request bodies, tracing context, connection buffer. Nếu tăng đồng thời thread count và request payload, phải **tách biến** trước khi kết luận “native stack là thủ phạm”.

## 10. Ma trận kiểm thử hợp lý

| Bài test | Live workers | Heap payload | Direct payload | Mục tiêu |
| --- | ---: | ---: | ---: | --- |
| A – Baseline | 4 | 8 MiB | 4 MiB | JVM, thread + native baseline |
| B – Chỉ thêm workers | 12 | 8 MiB | 4 MiB | Tác động thread count |
| C – Chỉ tăng heap | 4 | 16 MiB | 4 MiB | Heap live set/GC |
| D – Chỉ tăng direct | 4 | 8 MiB | 8 MiB | Off-heap/direct |
| E – Combined load | 12 | 16 MiB | 8 MiB | Tải tăng đồng thời |
| F – Realistic service | Theo SLO | Request live data thật | Pool buffers thật | Kiểm peak dưới traffic thực |
| G – Sustained/recovery | Theo production | Kéo dài rồi giảm | Kéo dài rồi giảm | Leak/pool retention và cooldown |

Đây là **ma trận thử nghiệm**, không phải benchmark production. Một workload thật cần đồng thời kiểm **CPU, request latency, GC, active/queued tasks, memory peak và OOM events**. Tăng từ 4 workers/8MiB/4MiB lên 12/16/8 làm đổi **ba biến cùng lúc**; đó không thể là phép đo riêng tác động của stacks.

### 10.1. Những điều cần cố định khi so sánh

Giữ cùng JDK build, JVM/GC flags, container limit, cgroup version, CPU budget, JAR/version, test duration, input distribution, node class, sampling interval, warm-up và metric definitions. Nếu NMT chỉ bật cho một test, overhead có thể khiến so sánh thiếu công bằng.

### 10.2. Vì sao phải test peak và sustained?

Một Pod có thể sử dụng 200Mi trung bình nhưng đạt 490Mi trong một burst ngắn sát limit 512Mi. Sau tải, native pools hoặc file cache có thể còn giữ memory. Test chỉ đo idle hoặc lấy mẫu mỗi phút có thể bỏ qua cả spike lẫn leak dài hạn.

## 11. Chương trình Java 17+ đã chạy kiểm chứng

Demo giữ **heap byte arrays**, một **direct ByteBuffer** và nhiều **platform threads** đang đợi trên latch. Nó nhận ba số: `workers`, `heapMiB`, `directMiB`, cùng tùy chọn `--observe` để giữ trạng thái 5 giây cho `jcmd` kiểm tra. Chương trình giới hạn đối số để tránh cấp phát cực lớn ngoài ý muốn.

Lưu file **`ContainerMemoryLoadDemo.java`**:

~~~java
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class ContainerMemoryLoadDemo {
    private static final int MiB = 1024 * 1024;
    private static final int LOCAL_BYTES = 256 * 1024;

    public static void main(String[] args) throws Exception {
        int workerCount = args.length > 0 ? Integer.parseInt(args[0]) : 4;
        int heapMiB = args.length > 1 ? Integer.parseInt(args[1]) : 8;
        int directMiB = args.length > 2 ? Integer.parseInt(args[2]) : 4;
        boolean observe = args.length > 3 && "--observe".equals(args[3]);
        if (args.length > 4 || workerCount < 1 || workerCount > 24
                || heapMiB < 1 || heapMiB > 32
                || directMiB < 1 || directMiB > 16
                || (args.length > 3 && !observe)) {
            throw new IllegalArgumentException(
                    "Allowed: workers 1..24, heapMiB 1..32, directMiB 1..16, [--observe]");
        }
        List<byte[]> heapBlocks = new ArrayList<>();
        for (int i = 1; i <= heapMiB; i++) {
            byte[] block = new byte[MiB];
            block[0] = (byte) i;
            heapBlocks.add(block);
        }
        ByteBuffer direct = ByteBuffer.allocateDirect(directMiB * MiB);
        direct.put(0, (byte) 42);
        CountDownLatch ready = new CountDownLatch(workerCount);
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> threads = new ArrayList<>();
        AtomicInteger workerResultBytes = new AtomicInteger();
        for (int i = 0; i < workerCount; i++) {
            Thread worker = new Thread(() -> {
                byte[] local = new byte[LOCAL_BYTES];
                local[0] = 7;
                ready.countDown();
                try {
                    release.await(20, TimeUnit.SECONDS);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    workerResultBytes.addAndGet(local.length);
                }
            }, "memory-worker-" + i);
            threads.add(worker);
            worker.start();
        }
        try {
            if (!ready.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not become ready");
            }
            long bytes = 0;
            int firstBytesSum = 0;
            for (byte[] block : heapBlocks) {
                bytes += block.length;
                firstBytesSum += block[0];
            }
            long aliveWorkers =
                    threads.stream().filter(Thread::isAlive).count();
            long maxHeap = Runtime.getRuntime().maxMemory();
            System.out.println("workers-configured=" + workerCount);
            System.out.println("workers-alive=" + aliveWorkers);
            System.out.println("heap-payload-bytes=" + bytes);
            System.out.println("heap-first-byte-sum=" + firstBytesSum);
            System.out.println("direct-buffer-bytes=" + direct.capacity());
            System.out.println("direct-first-byte=" + direct.get(0));
            System.out.println("worker-local-bytes=" + LOCAL_BYTES);
            System.out.println("worker-local-total-bytes=" +
                    (workerCount * LOCAL_BYTES));
            System.out.println("max-heap-positive=" + (maxHeap > 0));
            System.out.println("max-heap-at-most-128MiB=" +
                    (maxHeap <= 128L * MiB));
            System.out.println("jvm-thread-count-at-least-workers=" +
                    (ManagementFactory.getThreadMXBean().getThreadCount()
                            >= workerCount));
            if (observe) {
                TimeUnit.SECONDS.sleep(5);
            }
        } finally {
            release.countDown();
            for (Thread worker : threads) {
                worker.join(5000);
            }
        }
        System.out.println("workers-joined=" +
                threads.stream().noneMatch(Thread::isAlive));
        System.out.println("worker-result-bytes=" + workerResultBytes.get());
    }
}
~~~

**Lưu ý quan trọng:** `worker-local-total-bytes` là **Java heap byte[] payload** của mỗi worker, **không phải** tổng native stacks. Và code mô phỏng **memory pressure/concurrent live data**, không phát requests HTTP thực, không mô phỏng network/database latency; test production phải dùng service thật.

### 11.1. Compile và chạy case A

~~~bash
javac --release 17 -encoding UTF-8 ContainerMemoryLoadDemo.java
java -Xms64m -Xmx128m -Xss512k \
  -XX:MaxDirectMemorySize=16m \
  -XX:NativeMemoryTracking=summary \
  ContainerMemoryLoadDemo 4 8 4
~~~

Trên PowerShell, đặt lệnh `java` trên một dòng hoặc dùng cú pháp nối dòng đúng của PowerShell (POSIX `\` không hoạt động như vậy).

**Stdout đã kiểm thử chính xác trên OpenJDK 21/Linux:**

~~~text
workers-configured=4
workers-alive=4
heap-payload-bytes=8388608
heap-first-byte-sum=36
direct-buffer-bytes=4194304
direct-first-byte=42
worker-local-bytes=262144
worker-local-total-bytes=1048576
max-heap-positive=true
max-heap-at-most-128MiB=true
jvm-thread-count-at-least-workers=true
workers-joined=true
worker-result-bytes=1048576
~~~

### 11.2. Chạy case E (tải cao hơn nhưng vẫn giới hạn)

~~~bash
java -Xms64m -Xmx128m -Xss512k \
  -XX:MaxDirectMemorySize=16m \
  -XX:NativeMemoryTracking=summary \
  ContainerMemoryLoadDemo 12 16 8
~~~

**Stdout đã kiểm thử chính xác trên OpenJDK 21/Linux:**

~~~text
workers-configured=12
workers-alive=12
heap-payload-bytes=16777216
heap-first-byte-sum=136
direct-buffer-bytes=8388608
direct-first-byte=42
worker-local-bytes=262144
worker-local-total-bytes=3145728
max-heap-positive=true
max-heap-at-most-128MiB=true
jvm-thread-count-at-least-workers=true
workers-joined=true
worker-result-bytes=3145728
~~~

### 11.3. Giải thích output

- `workers-alive`: chỉ những worker objects do chương trình tạo, được kiểm đúng thời điểm sau `ready`; không phải total OS threads.
- `heap-payload-bytes`: 8 MiB hoặc 16 MiB do main giữ.
- `heap-first-byte-sum`: 1+...+8 = 36 hoặc 1+...+16 = 136, chứng minh mỗi block được ghi/đọc.
- `direct-buffer-bytes`: 4 MiB hoặc 8 MiB capacity ở direct ByteBuffer, không tính trong heap payload.
- `worker-local-bytes`: 256 KiB Java byte[]/worker.
- `worker-local-total-bytes`: 4×256 KiB = 1 MiB hoặc 12×256 KiB = 3 MiB.
- `max-heap-at-most-128MiB`: `Runtime.maxMemory()` không vượt mức `-Xmx128m`.
- `jvm-thread-count-at-least-workers`: Bean đang đếm ít nhất số platform threads mà bài tạo; nó còn có thể đếm các threads khác.
- `workers-joined` và `worker-result-bytes`: xác nhận workers kết thúc và tính dữ liệu họ đã giữ.

**Không suy:** cùng `-Xmx128m` thì hai process sẽ có giống RSS/cgroup memory. Trong bài, heap/direct/thread payload **đã khác nhau**.

## 12. Native Memory Tracking khi threads còn sống

Bật NMT từ startup:

~~~bash
-XX:NativeMemoryTracking=summary
~~~

Chạy demo giữ dữ liệu/threads trong 5 giây:

~~~bash
java -Xms64m -Xmx128m -Xss512k \
  -XX:MaxDirectMemorySize=16m \
  -XX:NativeMemoryTracking=summary \
  ContainerMemoryLoadDemo 4 8 4 --observe &
PID=$!
sleep 1
jcmd "$PID" VM.native_memory summary scale=MB
jcmd "$PID" Thread.print
wait "$PID"
~~~

Đây là **lệnh POSIX shell**, không phải PowerShell. `jcmd` yêu cầu JDK tooling, cùng user/namespace/attach permissions. Không mặc định `jcmd` có trong distroless image hoặc attach luôn được phép.

### 12.1. NMT đã đo trong test OpenJDK 21/Linux

Một lần chạy **4 workers, heap main payload 8 MiB, direct 4 MiB**:

~~~text
Total: reserved=1540MB, committed=137MB
- Java Heap (reserved=128MB, committed=66MB)
- Class     (reserved=1024MB, committed=0MB)
- Thread    (reserved=16MB, committed=1MB)
- Code      (reserved=242MB, committed=7MB)
- GC        (reserved=43MB, committed=42MB)
- Other     (reserved=4MB, committed=4MB)
~~~

Một lần chạy **12 workers, heap main payload 16 MiB, direct 8 MiB**:

~~~text
Total: reserved=1549MB, committed=142MB
- Java Heap (reserved=128MB, committed=66MB)
- Class     (reserved=1024MB, committed=0MB)
- Thread    (reserved=21MB, committed=2MB)
- Code      (reserved=242MB, committed=7MB)
- GC        (reserved=43MB, committed=42MB)
- Other     (reserved=8MB, committed=8MB)
~~~

**Đây là các dòng trích từ hai lần đo cụ thể**, làm tròn theo `scale=MB`, không phải stdout của demo hay expected NMT values trên mọi JVM. Các categories khác đã được lược để tập trung vào bài.

Phân tích:

1. Heap **reserved vẫn 128MB** vì `-Xmx` giữ nguyên.
2. Thread reserved tăng **16→21MB**, committed tăng **1→2MB** khi có thêm workers; bao gồm cả JVM system threads, không chỉ các worker do main tạo.
3. NMT `Other` tăng **4→8MB** trong workload có direct buffer tăng. Đây là **quan sát**, không phải luật rằng mọi native allocation/direct buffer đều thuộc `Other` trên mọi VM.
4. `Class reserved=1024MB` là địa chỉ ảo dành cho class metadata trên runtime thử, **không phải 1GiB resident RAM**.
5. Tổng reserved **1540MB/1549MB** vượt giới hạn heap rất nhiều nhưng **không đồng nghĩa process đã dùng 1.5GiB RAM vật lý**.

### 12.2. NMT không phải nguồn duy nhất

Oracle nêu NMT theo dõi allocations **nội bộ HotSpot VM**, không theo dõi đầy đủ third-party native code, một số JDK class libraries và CDS archive. `NMT committed` không bằng `RSS` hay `memory.current`. NMT cần được bật khi JVM khởi động; không thể khôi phục đầy đủ lịch sử trước đó chỉ bằng `jcmd`.

Dùng diff để phân tích một tải trong cùng process:

~~~bash
jcmd "$PID" VM.native_memory baseline
# Sau một khoảng tải được kiểm soát
jcmd "$PID" VM.native_memory summary.diff scale=MB
~~~

Bật NMT có overhead (Oracle nêu có thể 5–10% performance tùy workload); làm thí nghiệm A/B phải giữ NMT settings như nhau và cân nhắc quyền/dữ liệu debug.

Nguồn: [Oracle JDK 25 – Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html).

## 13. Đo heap/threads/buffers bằng API và công cụ

### 13.1. `jcmd`

~~~bash
jcmd PID VM.info
jcmd PID VM.flags
jcmd PID GC.heap_info
jcmd PID VM.native_memory summary scale=MB
jcmd PID Thread.print
~~~

Thay `PID` bằng PID thật. `VM.info` có thể hiện cgroup fields trên HotSpot/Linux hỗ trợ; `GC.heap_info` xem heap; `Thread.print` xem platform thread states/stacks, có thể chứa dữ liệu nhạy cảm. Kiểm `jcmd PID help` vì available commands tùy JDK.

### 13.2. Java heap metrics

~~~java
var mx = java.lang.management.ManagementFactory.getMemoryMXBean();
var usage = mx.getHeapMemoryUsage();
long used = usage.getUsed();
long committed = usage.getCommitted();
long max = usage.getMax();
~~~

Đoạn trên là **snippet trong một method**, không phải standalone Java file. Những biến này thuộc heap accounting, không phải toàn bộ container. Một số `MemoryUsage.getMax()` có thể là `-1` khi giới hạn không xác định theo contract.

### 13.3. Platform thread count

~~~java
int live = java.lang.management.ManagementFactory
        .getThreadMXBean().getThreadCount();
int peak = java.lang.management.ManagementFactory
        .getThreadMXBean().getPeakThreadCount();
~~~

Ở JDK hiện đại, API này **không bao gồm virtual threads**. Cần metric active business operations ngoài live platform threads.

### 13.4. Direct/mapped buffers

~~~java
var pools = java.lang.management.ManagementFactory
        .getPlatformMXBeans(java.lang.management.BufferPoolMXBean.class);
for (var pool : pools) {
    System.out.println(pool.getName() + ": " +
            pool.getCount() + ", bytes=" + pool.getMemoryUsed());
}
~~~

`BufferPoolMXBean` giúp quan sát những NIO buffer pools được JVM expose, nhưng **không** bao phủ mọi JNI/native allocation.

### 13.5. Linux RSS/PSS

~~~bash
cat /proc/PID/status
cat /proc/PID/smaps_rollup
~~~

`VmRSS`/`Rss`/`Pss`/`Private_Dirty` là metrics process-level; `memory.current` là cgroup-level. Shared page accounting có thể làm tổng RSS của nhiều JVM đếm trùng shared pages, nên PSS giúp hiểu footprint phân bổ giữa processes.

## 14. Kiểm memory trực tiếp trong Docker/Linux

Thử với một JDK image có runtime support:

~~~bash
docker run --rm --memory=512m \
  eclipse-temurin:21-jdk \
  java -XshowSettings:system -version
~~~

Đây là **lệnh minh họa**, không phải lệnh Docker đã được chạy trong bài; cần Docker image/permission thích hợp. Image tag nên được pin digest trong CI. Đọc `memory.max` thật để biết Docker/kernel áp quota nào và tránh nhầm Docker suffix `m` với Kubernetes `Mi`.

Kiểm sâu container detection:

~~~bash
docker run --rm --memory=512m \
  eclipse-temurin:21-jdk \
  java -Xlog:os+container=trace -version
~~~

Nếu runtime không có tag `os+container`, không khẳng định limit bằng 0: kiểm OS/JDK, cgroup mount và `java -Xlog:help`. Trên Windows HotSpot có thể không hỗ trợ Linux-specific tags.

### 14.1. Chạy demo trong container bằng JAR

Trên máy dev đã biên dịch demo:

~~~bash
javac --release 17 -encoding UTF-8 ContainerMemoryLoadDemo.java
jar --create --file memory-demo.jar ContainerMemoryLoadDemo.class
~~~

Trong thư mục chứa JAR (POSIX shell):

~~~bash
docker run --rm --memory=512m \
  -v "$PWD/memory-demo.jar:/app/memory-demo.jar:ro" \
  eclipse-temurin:21-jdk \
  java -Xms64m -Xmx128m -Xss512k \
  -XX:MaxDirectMemorySize=16m \
  -cp /app/memory-demo.jar ContainerMemoryLoadDemo 4 8 4
~~~

Đây là ví dụ thực hành **không** cố ý chạm OOM. File mount permissions và đường dẫn phụ thuộc Docker Desktop/OS; có thể cần điều chỉnh theo policy môi trường. Đo khi chạy bằng cách lấy `memory.current`/`peak` từ **đúng cgroup**, không đọc cgroup khác ở host rồi suy ra.

### 14.2. Có nên cố ép đến OOM?

**Không trên production.** Nếu cần kiểm ứng xử failure/restart, dùng staging/isolated node với memory quota, bounded load, alerting và cleanup phù hợp chính sách. Không chạy stress vô hạn hoặc ép node hết RAM chỉ để tạo được `OOMKilled`. Đây là bài **quan sát giới hạn dưới tải có kiểm soát**, không phải phá hệ thống.

## 15. Đối chiếu bốn nguồn memory thực tế

| Nguồn | Ví dụ | Điều chứng minh |
| --- | --- | --- |
| Pod spec | `limits.memory=512Mi` | Kubernetes yêu cầu hard cap ở mức này |
| Cgroup v2 `memory.max` | `536870912` | Kernel limit ở cấp cgroup đo |
| Java `Runtime.maxMemory()` | `128MiB` với `-Xmx128m` | Giới hạn Java heap, **không phải cgroup limit** |
| NMT `Thread` | reserved 16MB, committed 1MB | HotSpot thread-related tracking ở một thời điểm |
| Cgroup `memory.current` | 150MiB (giả định) | Tổng memory charged hiện tại |
| Cgroup `memory.peak` | 220MiB (giả định) | Peak theo mốc quan sát |
| `memory.events oom_kill` delta | `0` (giả định) | Không có event kill được ghi trong phạm vi/period này |
| App metric | 12 active workers | Concurrency app thật, không phải total JVM threads |

Những giá trị **150MiB/220MiB/delta 0** trong bảng là ví dụ minh họa, **không phải đo từ cùng container Docker**. NMT numbers là ví dụ quan sát từ process test trên OpenJDK 21, không gán nó cho Pod minh họa.

### 15.1. Không so các metric khác thời điểm

Nếu `memory.peak` lấy từ cgroup A, NMT từ process B hoặc `kubectl top` chụp sau khi tải kết thúc, không thể xác định nguyên nhân memory spike. Ghi **PID, container ID/cgroup, JDK build, timestamps, metric definitions** và load scenario kèm kết quả.

## 16. Java OOME khác kernel OOMKilled

| Triệu chứng | Nguyên nhân thường gặp | Kiểm ở đâu |
| --- | --- | --- |
| `java.lang.OutOfMemoryError: Java heap space` | Heap không đủ cho allocation/live set | Heap max/used, GC logs, allocation profile |
| `OutOfMemoryError: Cannot reserve ... direct buffer memory` | Direct-buffer limit/native allocation | Direct pool metrics, `MaxDirectMemorySize` |
| `OutOfMemoryError: unable to create native thread` | OS thread/pids/native stack/resources | Live threads, `pids.max`, ulimits, OS |
| Kubernetes `reason: OOMKilled` | Kernel OOM killer do memory pressure/limit | Pod lastState, cgroup events, kernel logs |
| Exit code 137 | Thường SIGKILL, có thể do OOM hoặc lý do khác | Termination reason, event provenance |
| RSS/cgroup tăng nhưng heap used ổn | Native buffers, file cache, sidecars, JNI | NMT, `memory.stat`, process OS metrics |

**Điểm mấu chốt:** kernel OOM killer có thể giết JVM **không kịp có Java exception hoặc heap dump**. `-XX:+HeapDumpOnOutOfMemoryError` có thể có ích cho Java-level OOME, nhưng **không bảo đảm** hoạt động trước SIGKILL; heap dumps còn lớn và có nguy cơ chứa dữ liệu nhạy cảm.

### 16.1. Error 137 không đủ để kết luận OOM

~~~text
lastState:
  terminated:
    reason: OOMKilled
    exitCode: 137
~~~

Đây là hình thức thường gặp, nhưng **exit code 137 đơn lẻ** cũng có thể do SIGKILL từ nguồn khác. Dùng `reason`, `memory.events`, kernel/node logs (khi có quyền) và memory peak để chốt nguyên nhân.

## 17. Memory budgeting và headroom

Với cgroup hard limit hữu hạn:

~~~text
headroom_now = memory.max - memory.current
headroom_peak = memory.max - measured_peak_memory
~~~

Chỉ số này **là phép trừ kế toán đơn giản**, không phải dự báo chắc chắn OOM: file cache có thể reclaim, memory charges và allocator peaks có thể thay đổi, còn `memory.max=max` không dùng được trong phép trừ.

Ví dụ 512 MiB memory limit với `-Xmx256m`:

~~~text
Java heap max:                   256 MiB
Direct buffers peak:             cần đo
JVM metaspace/code/GC/native:    cần đo
Platform thread stacks:         cần đo reserved + committed
Other process/file cache/kernel: cần đo
Remaining headroom:             không thể kết luận từ Xmx một mình
~~~

**Đừng tính:** `512−256=256 MiB, vậy native chắc chắn có đúng 256 MiB an toàn`. Headroom là tổng hợp theo **peak workload thật**, GC/native overhead, số concurrent tasks, số pod replicas và node memory constraints.

## 18. Kubernetes incident workflow

Khi một container Java bị restart hoặc có peak memory bất thường:

1. Xác minh **container/pod/process** thật; lấy `kubectl describe` và `lastState.terminated`.
2. Ghi JDK version/vendor, image/JAR, JVM flags, GC, memory request/limit.
3. Xác định **cgroup v1/v2** và đường dẫn memory của đúng process.
4. Đọc `memory.max`, `memory.current`/`peak` và delta `memory.events`.
5. Kiểm `memory.stat anon/file`, tmpfs, page cache và memory swap.
6. Kiểm Java heap used/committed/max, metaspace và GC.
7. Kiểm live/peak platform threads, worker pools, active/queued requests.
8. Kiểm direct buffers, JNI/native pools, NMT category changes.
9. Phân loại Java OOME vs kernel OOMKilled/SIGKILL; đừng suy từ mỗi exit code.
10. Nếu cần chỉnh, chỉ thay **một biến** rồi chạy lại load test cùng điều kiện.
11. Đánh giá cả **application p95/p99 latency** và memory peak, không chỉ tổng byte.
12. Ghi kết quả, quyết định config và rollback plan.

### 18.1. Khi heap ổn mà cgroup vẫn tăng

Có thể do **direct/native buffer leak, JNI allocator, ThreadLocal/threads tăng, file cache/tmpfs, other processes hoặc native memory retention**. Không gọi tất cả là “heap leak”. NMT chỉ theo dõi HotSpot internal memory, nên cần thêm OS/process/cgroup data để biết phần nào ngoài NMT.

### 18.2. Khi tăng concurrency làm memory tăng

Theo dõi **active requests/task queue**. Nếu requests bị I/O hoặc CPU throttling giữ lâu, cùng RPS có thể có nhiều in-flight operations hơn; per-request data sống lâu hơn làm memory peak tăng. Giải pháp có thể là **bounded concurrency, backpressure, streaming, buffer pooling có giới hạn, request size caps**, chứ không nhất thiết tăng heap.

## 19. Checklist ma trận CI/staging

Một bài kiểm thử có ý nghĩa cần:

1. Chạy đúng **JDK được hỗ trợ** và image production-equivalent.
2. Xác nhận cgroups v1/v2 và memory limit thật.
3. Dùng **tải tăng dần có giới hạn**, không tạo OOM production.
4. Đo baseline idle, moderate, peak, burst, sustained và cooldown.
5. Đo riêng tác động của worker count, heap payload và direct payload.
6. Báo configured max **và** actual live platform threads.
7. Báo active requests và queued tasks.
8. Giữ GC/heap/CPU/quota/settings khác cố định khi so.
9. Bật NMT ở các lần cần so native memory với cùng overhead.
10. Ghi RSS/PSS process và cgroup memory.current/peak khi phù hợp.
11. Lấy delta memory.events, OOM counters, restart reasons.
12. Không coi `kubectl top` tại một thời điểm là peak đầy đủ.
13. Ghi GC pauses và request latency/throughput cùng memory.
14. Kiểm swap/tmpfs/page cache nếu ảnh hưởng.
15. Thử rollout/restarts khi có nhiều replicas trên một node.
16. Khi dùng virtual threads, đo in-flight tasks chứ không chỉ ThreadMXBean.
17. Không tăng `-Xmx` sát limit mà không đo native headroom.
18. Ghi process/cgroup identity và timestamps để tái lập.
19. Bảo mật heap/thread dumps và diagnostic logs.
20. Có alert threshold và rollback criteria trước khi thay production settings.

## 20. Những hiểu lầm cần loại bỏ

| Nhận định sai | Điều đúng |
| --- | --- |
| “`-Xmx128m` nghĩa process chỉ dùng 128MiB” | JVM còn off-heap/native/stacks/cache |
| “Request memory là hard limit” | Request dùng cho scheduling/resource policy; limit riêng |
| “`memory.current` là Java heap used” | Cgroup charge bao gồm nhiều loại memory |
| “NMT reserved 1.5GB là 1.5GB RSS” | Reserved là virtual address space |
| “NMT committed bằng tổng container usage” | NMT không bao phủ mọi native/JNI/file cache/process |
| “`ThreadMXBean` đếm tất cả virtual threads” | Chỉ platform threads theo contract hiện đại |
| “100 threads × Xss chính xác bằng RSS threads” | Stack reserved/committed/resident khác nhau |
| “`MaxDirectMemorySize` giới hạn mọi native memory” | Chỉ NIO direct buffer group thích hợp |
| “OOMKilled bắt buộc in `OutOfMemoryError`” | Kernel có thể SIGKILL ngay |
| “Exit 137 luôn là OOM” | Cần reason/events/kernel evidence |
| “File `memory.max=max` nghĩa infinite RAM” | Có thể bị giới hạn bởi host/ancestor |
| “`memory.high` chính là hard OOM limit” | High là reclaim/throttle threshold |
| “`memory.events oom_kill` đếm Java OOME” | Đây là kernel kill counter |
| “Một giá trị `kubectl top` là peak của giờ qua” | Sample có thể bỏ lỡ transient spikes |
| “Thêm threads không ảnh hưởng memory nếu Xmx giữ nguyên” | Stacks/request-local/native memory có thể tăng |
| “Native memory chỉ cần NMT là đủ” | NMT không theo dõi mọi third-party/native allocations |
| “Giảm Xss luôn tốt” | Có thể StackOverflowError và OS/platform constraints |
| “Virtual threads làm mỗi request không tốn RAM” | Continuation/request data vẫn tồn tại |
| “Java 10 cgroup v2 như JDK hiện đại” | Support được phát triển/backport qua releases |
| “Benchmark combined 4→12 là đo riêng stacks” | Heap/direct/workers cùng đổi, cần tách biến |
| “Ép container OOM trên production để thử” | Cần isolated staging và safe limits |

## 21. Bài tập có đáp án

**1.** Java 10 cải tiến gì với Docker? — **Đáp án:** HotSpot container CPU/memory awareness (JDK-8146115), tạo nền tảng cho container-aware ergonomics.

**2.** Limit 512MiB và `-Xmx512m` đã bảo đảm không OOMKilled? — **Không**, native/off-heap/thread/page cache còn tiêu thụ memory.

**3.** `Runtime.maxMemory()` có phải cgroup limit? — **Không**, nó là Java heap max do JVM công bố.

**4.** `memory.max=536870912` bằng bao nhiêu? — **512MiB**.

**5.** `memory.max=max` nghĩa gì? — Không hard limit tại cgroup ấy; vẫn có host/ancestor limitations.

**6.** `memory.current` có gồm Java heap thôi? — Không, gồm cgroup charge theo kernel accounting.

**7.** `memory.high` và `memory.max` khác gì? — High kích reclaim/throttle, max hard limit.

**8.** `oom_kill=1` có bằng một Java exception OOME? — Không, là kernel OOM kill counter.

**9.** NMT `Class reserved=1024MB` có chắc chiếm 1GiB RAM? — Không, reserved virtual ≠ resident.

**10.** Tăng 4→12 workers ảnh hưởng memory thế nào? — Có thể tăng native stack reservation/commitment, Java per-worker data và runtime overhead.

**11.** Mỗi worker giữ 256KiB, 12 workers giữ bao nhiêu heap payload? — **3MiB = 3145728 bytes**.

**12.** Direct buffer 8MiB nằm trong `heap-payload-bytes`? — Không, đây là off-heap payload.

**13.** NMT `Other` tăng 4→8MB có là luật cho mọi ByteBuffer? — Không, chỉ là một quan sát trong JVM/workload này.

**14.** `ThreadMXBean` có bao gồm virtual threads Java 21? — Không.

**15.** “Unable to create native thread” luôn do cgroup memory.max? — Không, có thể do pids/ulimits/native resource exhaustion.

**16.** Exit code 137 đủ chứng minh OOMKilled không? — Không; cần termination reason và cgroup/kernel evidence.

**17.** NMT có thể bật sau khi JVM chạy bằng `jcmd` nếu trước đó tắt? — Không, tracking phải bật từ startup.

**18.** Vì sao lấy `memory.events` trước/sau test? — Counters tích lũy, delta mới liên hệ khoảng test.

**19.** Heap used ổn nhưng cgroup tăng thì kiểm gì? — Native/direct/threads/cache/JNI/other processes trước khi quy lỗi heap.

**20.** `Xss512k` nghĩa 512KiB RSS/thread ngay lúc start? — Không, stack reservation/commitment/residency khác nhau.

**21.** Combined 4→12 workers đồng thời tăng heap/direct có đo riêng thread cost? — Không, phải chạy ma trận chỉ thay một biến.

**22.** Kernel OOMKill luôn kích heap dump? — Không, JVM có thể không chạy được dump hook trước SIGKILL.

**23.** Virtual threads có chữa mọi memory pressure do concurrency? — Không, per-request objects/buffers vẫn tồn tại.

**24.** Khi nào có thể gọi container memory config an toàn? — Khi đã kiểm **peak cgroup/current/events, JVM heap/native, threads, workload và latency** trên các mức tải thực.

## 22. Tài liệu chính thức còn áp dụng

1. [Oracle JDK 10 Release Notes – Java Improvements for Docker Containers](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): mốc Java 10 và JDK-8146115.
2. [OpenJDK JDK-8146115](https://bugs.openjdk.org/browse/JDK-8146115): container resource awareness.
3. [Oracle Java SE 17 java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xmx`, `-Xss`, NMT/DirectMemory flags và unified logging.
4. [Oracle Java SE 25 java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): container-aware options và hiện hành JVM flags.
5. [Oracle Java SE 25 Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): NMT capabilities, reservations vs committed, limitations và `jcmd`.
6. [Oracle Java SE 17 jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.native_memory`/`Thread.print`/`GC.heap_info`.
7. [Linux Kernel – Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `memory.max/current/peak/high/events/stat`, swap và accounting.
8. [Kubernetes – Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): requests, limits, OOM kills và resource enforcement.
9. [Kubernetes – Assign Memory Resources](https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/): memory requests/limits, events và OOM.
10. [Java SE 17 Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `maxMemory()`/`totalMemory()`.
11. [Java SE 17 MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/nonheap metrics.
12. [Java SE 25 ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform thread counts và virtual thread caveat.
13. [Java SE 17 BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): NIO buffer metrics.
14. [OpenJDK JEP 444 Virtual Threads](https://openjdk.org/jeps/444): Java 21 virtual/platform thread model.
15. [Linux procfs `smaps`/PSS](https://man7.org/linux/man-pages/man5/proc_pid_smaps.5.html): resident/shared/private pages.

**Tóm tắt cuối:** Tính container-aware memory của HotSpot có nguồn gốc từ Java 10 nhưng cần kiểm trên một JDK còn được hỗ trợ. **Giới hạn memory container** do kernel/cgroup thực thi; **Java heap max** là một ràng buộc khác và không tính hết native/threads/direct buffers. Tăng số requests và platform threads có thể làm memory peak tăng ngay khi `-Xmx` giữ nguyên. Để kiểm thực sự, dùng **tải có kiểm soát**, giữ workers đang sống khi đo NMT, đọc **memory.current/peak/events**, phân biệt reserved/committed/RSS, theo dõi OOMKilled và request latency. Quyết định heap/thread/buffer sizing phải dựa **peak workload thực và safety headroom**, không dựa một tỷ lệ mặc định.
