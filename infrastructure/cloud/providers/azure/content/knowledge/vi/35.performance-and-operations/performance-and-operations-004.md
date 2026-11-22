# Tối ưu JVM, bộ nhớ và garbage collection trên Azure

Trong module **CLOUD_PROVIDERS_AZURE**, người học khám phá Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu, đồng thời học triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Azure. Thuộc chương **Hiệu năng và vận hành**, bài này trình bày cách tối ưu **Java Virtual Machine (JVM)**, sử dụng bộ nhớ và **garbage collection (GC)** trong các môi trường như **Azure Kubernetes Service (AKS), Azure App Service, Azure Container Apps và máy ảo Azure**.

**Tình huống xuyên suốt:** một ứng dụng Java 21/Spring Boot tiếp nhận đơn hàng qua REST API, gửi sự kiện đến Azure Service Bus và ghi Azure SQL Database. Ứng dụng chạy trong container AKS với giới hạn bộ nhớ 2 GiB; khi tăng traffic, độ trễ p99 tăng, thỉnh thoảng Pod bị `OOMKilled`, đôi khi heap dashboard lại cho thấy chỉ 900 MiB. Mục tiêu không phải chọn “cờ JVM thần kỳ”, mà xác định **bộ nhớ thực nằm ở đâu, GC có thực sự gây chậm, container có bị CPU throttling, và sự thay đổi nào tạo cải thiện đo được**.

Sau bài học, bạn có thể:

- Giải thích các vùng **heap, metaspace, thread stacks, direct buffers, code cache, native memory**, phân biệt JVM heap với RSS/container memory.
- Hiểu JVM hiện đại đọc **cgroup CPU/memory limits**, quan hệ giữa `-Xmx`, `-XX:MaxRAMPercentage`, Kubernetes `requests/limits`, CPU throttling và OOM.
- So sánh **G1 GC, ZGC, Parallel GC** theo throughput, latency, heap size, phiên bản JDK và điều kiện vận hành; chọn collector bằng thí nghiệm chứ không phỏng đoán.
- Bật **GC logs, Java Flight Recorder (JFR), `jcmd`, Native Memory Tracking (NMT), JMX/Micrometer/OpenTelemetry** phù hợp với mức nhạy cảm dữ liệu và overhead.
- Tối ưu bộ nhớ/GC trên AKS, App Service, Container Apps và VM; thiết kế **startup/readiness/liveness probes, graceful shutdown và autoscaling** không làm sự cố trầm trọng hơn.
- Dùng **load test, SLI/SLO, p95/p99, allocation rate, GC pause, CPU throttling và working set** để chứng minh hiệu quả.
- Xử lý **`OutOfMemoryError`, `OOMKilled`, heap leak, native-memory leak, GC thrashing, thread explosion, memory spike và noisy-neighbor** bằng runbook có thứ tự.
- Thiết lập **chi phí, bảo mật, rollback, production checklist và quy trình tuning có thể lặp lại**.

## 1. Tối ưu JVM bắt đầu từ mục tiêu dịch vụ, không phải từ cờ GC

Một ứng dụng Java có thể “GC rất ít” nhưng phản hồi chậm vì Azure SQL bị khóa, Service Bus tăng backlog, DNS/Key Vault chậm, connection pool cạn hoặc CPU container bị throttling. Ngược lại, có thể thấy nhiều young GC ngắn nhưng ứng dụng vẫn đạt SLO. Tối ưu đúng phải bắt đầu từ **trải nghiệm người dùng và khả năng phục vụ**.

### 1.1. Các mục tiêu thường gặp

| Mục tiêu | SLI/KPI cần đo | Bẫy dễ gặp |
|---|---|---|
| Độ trễ API | p50, p95, p99 và timeout rate | Lấy p95 trung bình của nhiều Pod |
| Throughput | Successful requests/s hoặc orders/s | Đếm requests 500 là thành công |
| Tính sẵn sàng | Good/eligible requests trên một cửa sổ SLO | Đồng nhất health endpoint với end-user availability |
| CPU efficiency | CPU usage, throttled periods, CPU/transaction | Chỉ xem CPU usage, bỏ qua throttling |
| Bộ nhớ | RSS/working set, heap used/committed, non-heap, direct/native | Coi heap used là toàn bộ Pod memory |
| GC | Pause distribution, GC time fraction, allocation/reclamation | Chỉ xem tổng số lần GC |
| Khởi động | Cold start, warm-up, readiness time | So runtime của app đã warm với phiên bản mới chưa warm |
| Chi phí | Cost per good transaction, instances, memory tier | Giảm RAM nhưng tăng CPU và số Pod |

### 1.2. Định nghĩa baseline cho hệ thống mẫu

Giả sử tiêu chí do nhóm ứng dụng **tự đặt** (không phải SLA Azure):

```text
Production SLO:
  API availability: >= 99.9% good requests / rolling 30 days
  p95 API latency under representative load: <= 250 ms
  p99 API latency under representative load: <= 800 ms
  OOMKilled in stable load: 0
  Capacity target: 400 good requests/s with agreed headroom
  Memory cost per good transaction: tracked weekly
```

Các số này là ví dụ để học; ngưỡng thực tế phải lấy từ yêu cầu nghiệp vụ, baseline và load test. **Độ trễ GC không bằng độ trễ HTTP**: một pause 30 ms không tự tạo request p99 900 ms, nhưng nhiều pauses hoặc scheduling effects có thể góp phần.

### 1.3. Quy trình điều tra hiệu năng

```text
Define user-facing SLO and workload mix
             |
             v
Collect baseline: latency, throughput, CPU, RSS, heap, GC
             |
             v
Find bottleneck and form one hypothesis
             |
             v
Choose one small, reversible change
             |
             v
Run comparable load test + diagnostics
             |
             v
Compare SLI, resource headroom and cost
             |
       +-----+-----+
       |           |
       v           v
   Improved     Not improved
       |           |
    Canary      Revert/rethink
       |           |
       +-----+-----+
             |
        Document result
```

Đừng tăng `-Xmx`, đổi GC, tăng Pod limit và đổi HTTP thread pool **đồng thời**: bạn sẽ không biết nguyên nhân cải thiện hay sự cố mới.

## 2. JVM memory model: heap chỉ là một phần

Trong HotSpot JVM, bộ nhớ của process thường gồm nhiều khu vực. Ranh giới chính xác phụ thuộc JDK, vendor, OS, configuration và workload.

```text
Container / process memory budget
┌───────────────────────────────────────────────────────────────┐
│ JVM process                                                   │
│ ┌───────────────────────────────┐ ┌─────────────────────────┐ │
│ │ Java Heap                     │ │ Native / Non-Heap       │ │
│ │ - Young generation            │ │ - Metaspace             │ │
│ │ - Old generation              │ │ - Thread stacks         │ │
│ │ - Live objects + free space   │ │ - Code cache / JIT      │ │
│ │ - GC-managed object memory    │ │ - Direct/NIO buffers    │ │
│ └───────────────────────────────┘ │ - GC structures         │ │
│                                   │ - JNI/native libraries  │ │
│                                   │ - Class data, malloc    │ │
│                                   └─────────────────────────┘ │
│ Native memory pages, mappings, allocations, runtime overhead  │
└───────────────────────────────────────────────────────────────┘
  Plus container-charged memory outside main JVM process:
  sidecars, shell/helper processes, some file cache/kernel charges...
```

### 2.1. Heap

**Heap** là nơi JVM quản lý phần lớn Java objects. `-Xms` kiểm soát heap size ban đầu, `-Xmx` giới hạn heap tối đa theo cấu hình/collector. `Used heap`, `Committed heap` và `Max heap` là ba đại lượng khác nhau:

| Metric | Ý nghĩa | Ví dụ |
|---|---|---|
| Heap used | Dung lượng được các đối tượng hiện dùng chiếm trong heap tại thời điểm đo | 950 MiB |
| Heap committed | Phần heap JVM đã cam kết với hệ thống, không nhất thiết đã dùng hết | 1.250 MiB |
| Max heap | Cận trên mà JVM có thể sử dụng theo cấu hình/ergonomics | 1.300 MiB |

Heap used chỉ là **ảnh chụp tức thời**. Sau full/old collection, used heap thường giảm, nhưng nếu used heap tăng theo thời gian dưới cùng tải và không giảm sau collection, có thể nghi ngờ **retained objects** hoặc cache tăng trưởng.

### 2.2. Metaspace

Metaspace chứa metadata về classes và class loaders, thường ở native memory. Ứng dụng dùng nhiều dynamic proxies, class generation, application reload hoặc plugin loaders có thể làm metaspace tăng. `-XX:MaxMetaspaceSize` có thể giới hạn mức sử dụng, nhưng **đặt quá thấp có thể tạo `OutOfMemoryError: Metaspace`**. Đừng cắt metaspace chỉ để làm dashboard trông thấp hơn nếu chưa hiểu nguyên nhân.

### 2.3. Thread stacks

Mỗi OS thread có stack và overhead riêng. JVM flag `-Xss` hoặc `-XX:ThreadStackSize` (theo cách JVM/version hỗ trợ) điều chỉnh kích thước stack; không nên giảm quá thấp vì có thể dẫn đến `StackOverflowError` hoặc lỗi native thread creation. Một app tạo hàng nghìn threads có thể tăng native memory dù heap ít thay đổi.

### 2.4. Direct/NIO buffers

`ByteBuffer.allocateDirect()`, Netty, TLS/network I/O và một số storage/database clients dùng **native/direct buffers** ngoài Java heap. Nếu direct allocations quá nhiều hoặc leak, process/container memory tăng mà biểu đồ heap vẫn có vẻ bình thường. `-XX:MaxDirectMemorySize` có thể điều chỉnh upper bound cho **một nhóm direct buffer allocations**, **không phải giới hạn tất cả native memory**.

### 2.5. Code cache và JIT

JIT compiler biên dịch hot methods thành machine code, lưu trong code cache; JIT threads và compiler structures cũng tốn memory/CPU. JVM warm-up có thể khiến CPU và latency ban đầu khác lúc ổn định. Tắt JIT bừa bãi để giảm memory thường làm throughput giảm mạnh.

### 2.6. JNI/native libraries, GC structures và memory mapping

Một ứng dụng Java sử dụng compression, cryptography, image processing, RocksDB, Netty hoặc native drivers có thể dùng memory do native libraries quản lý. GC implementation cũng tiêu thụ native structures riêng. Mapped files và OS page cache có semantics đo lường khác committed heap.

### 2.7. Những gì `-Xmx` không giới hạn

`-Xmx=1g` **không giới hạn toàn bộ RSS/Pod ở 1 GiB**. Nó không chặn mọi metaspace, stack, code cache, direct buffers hay sidecars. Nếu Pod có limit 1.5 GiB, heap 1 GiB có thể vẫn làm Pod `OOMKilled` khi native + sidecars + kernel/accounted cache vượt budget.

## 3. Phân biệt heap, RSS, working set, cgroup usage và OOM

Các tools/platform có nhiều cách đo bộ nhớ. Cần ghi **đơn vị, nguồn dữ liệu và định nghĩa** trước khi so sánh.

| Chỉ số | Thường lấy từ | Diễn giải |
|---|---|---|
| `jvm_memory_used_bytes{area="heap"}` | JVM/Micrometer/Prometheus | Heap currently used |
| `jvm_memory_committed_bytes` | JVM/Micrometer | Heap/non-heap committed theo pool |
| `process_resident_memory_bytes` | Process exporter/metrics | RSS của process theo collector |
| `container_memory_working_set_bytes` | Kubernetes/container metrics | Working set theo metric implementation, không đồng nhất heap |
| cgroup memory current/usage | Linux cgroups v1/v2 | Usage được kernel tính vào cgroup, có file/cache/kernel charges |
| `kubectl describe pod` OOMKilled | Kubernetes status | Container bị kill, thường do vượt limit/cgroup OOM |
| `java.lang.OutOfMemoryError` | JVM exception/log | JVM không cấp phát được loại memory cần thiết |

### 3.1. Hai kiểu OOM phải phân biệt

**JVM `OutOfMemoryError: Java heap space`:** heap không đủ cấp phát sau nỗ lực GC; JVM có thể ghi heap dump nếu được cấu hình, nhưng process có thể tiếp tục/chết tùy flags và application.

**Kubernetes `OOMKilled`:** kernel/container runtime kill process khi memory cgroup budget bị vi phạm. JVM **có thể không kịp in Java heap OOME hoặc tạo heap dump**, và event/exit code thường giúp xác định tình huống (ví dụ container exit code 137 có thể do SIGKILL, cần kiểm chứng `Reason: OOMKilled`, không chỉ dựa exit code).

Một Pod có `heap used=800 MiB`, `Xmx=1.2 GiB` vẫn có thể `OOMKilled` nếu native memory/cgroup cache/sidecar bổ sung làm tổng vượt container limit.

### 3.2. Vùng bộ nhớ ngoài heap cần nằm trong budget

Khi sizing, nên nghĩ:

```text
Container limit
  >= JVM max heap (Xmx or computed max heap)
   + metaspace
   + thread stacks
   + direct/native buffers
   + code cache/JIT/GC overhead
   + OS/runtime/process overhead
   + variation/headroom
```

Đây là **mô hình ngân sách**, không phải công thức đo tuyệt đối từng byte. Một số metric có thể overlap hoặc tính RSS/working-set khác nhau; đừng cộng các chỉ số từ nhiều nguồn khi chúng đã chứa nhau.

### 3.3. Process memory và Pod memory khác nhau

Trong Pod có **main Java container** và các **sidecar containers**, mỗi container có memory limit/usage riêng theo cấu hình. Pod-level accounting và eviction behavior phụ thuộc Kubernetes version/OS/resource configuration; **không lấy memory của main Java process làm tổng Pod cost**. Sidecar OOM có thể làm mất logging/network functionality dù Java process không bị kill.

## 4. JVM hiểu container/cgroup limits như thế nào?

HotSpot của các JDK hiện đại có hỗ trợ **container awareness**, thường bật bằng `-XX:+UseContainerSupport` theo JDK/version/build. Nó cho phép ergonomics của JVM xét các cgroup CPU/memory limits thay vì chỉ host total RAM/cores. Các bản JDK cũ, backports, vendor builds, cgroups v1/v2 và môi trường runtime có thể khác; **luôn kiểm tra JDK đang chạy**, không giả định mọi Java 8 hoặc base image nhìn container giống nhau.

### 4.1. Kiểm tra phiên bản JDK và flags thực tế

```bash
java -version
java -XX:+PrintFlagsFinal -version \
  2>&1 | grep -E 'UseContainerSupport|MaxHeapSize|MaxRAMPercentage|InitialRAMPercentage|ActiveProcessorCount'
```

Kết quả `PrintFlagsFinal` phụ thuộc JVM vendor/version, flags thực tế và format output. Trong môi trường production nên kiểm tra process JVM đang chạy (không chỉ chạy một JVM mới với flags khác).

### 4.2. In container detection information

Với HotSpot/JDK hỗ trợ:

```bash
# Diagnostic command cho JVM khởi động riêng trên môi trường thử nghiệm.
java -XshowSettings:system -version
```

Thông tin có thể bao gồm provider/cgroup limits; trường cụ thể tùy JDK và OS. Nếu JDK không nhận cgroups v2, có thể thấy nó tính theo host RAM, tạo cận heap không phù hợp. **Nâng JDK bản được hỗ trợ** thường an toàn hơn cố sửa bằng undocumented flags; pin image digest/version, test trên AKS node runtime thật.

### 4.3. Cgroup v1 và v2

Linux có thể dùng **cgroup v1 hoặc v2**, với tên file/metrics khác nhau. Trên cgroup v2, `memory.max` là limit có thể là số byte hoặc `max` (không giới hạn tại cấp đó); `memory.current` cho biết usage theo cgroup. Nhưng không dựa vào một path hard-code như `/sys/fs/cgroup/memory.max` trong mọi container: filesystem mount/namespace và JDK/runtime có thể khác.

### 4.4. Memory request không bằng memory limit

Trong Kubernetes:

- **`requests.memory`** ảnh hưởng scheduling và resource guarantees; không phải trần heap.
- **`limits.memory`** đặt trần cgroup/container theo cách Kubernetes/runtime thực thi.
- **`requests.cpu`** được scheduler dùng để đặt resource reservation/shares.
- **`limits.cpu`** có thể tạo CPU quota/throttling khi bị giới hạn.

Một Pod có `request.memory: 1Gi` và `limit.memory: 2Gi` có thể dùng tới giới hạn cao hơn request khi node đủ tài nguyên; JVM container-aware thường phải xem **limit** và container environment, không chỉ request.

## 5. Ví dụ sizing JVM trong container 2 GiB

Giả sử một JVM container AKS có memory limit **2 GiB = 2048 MiB**; nhóm muốn đặt heap khoảng **60%** của container limit. Đây là **điểm bắt đầu để thử**, không phải universal production setting.

```text
Container memory limit                 2048 MiB
Target maximum Java heap (60%)         ~1229 MiB
Remaining upper-level budget           ~819 MiB

Possible contributors to remainder:
  metaspace + code cache
  direct memory
  thread stacks
  JIT/GC/native structures
  malloc/memory mapping
  OS/runtime accounting + headroom
```

### 5.1. Cấu hình theo tỷ lệ

```bash
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0 -XX:+UseG1GC"
```

`-XX:MaxRAMPercentage=60.0` hướng JVM tính max heap theo **RAM được JVM coi là available**; nếu cgroup memory limit được phát hiện đúng, heap ~60% limit. Không tự hiểu rằng JVM chắc chắn cho đúng 1229 MiB trong mọi JDK/JVM: ergonomics, minimum/maximum constraints và runtime flags có thể ảnh hưởng.

### 5.2. Cấu hình bằng cận heap tuyệt đối

```bash
JAVA_TOOL_OPTIONS="-Xmx1200m -XX:+UseG1GC"
```

`-Xmx1200m` đặt một cap cụ thể; khi dùng trong container có limit thay đổi theo môi trường, phải đảm bảo không đem cận này sang Pod 1 GiB. Tránh cấu hình **đồng thời `-Xmx` và `MaxRAMPercentage` với mong đợi cả hai cùng là trần động học**: giá trị explicit max heap thường chi phối sizing heap, làm tài liệu khó hiểu.

### 5.3. `-Xms` có cần bằng `-Xmx`?

Không mặc định. `-Xms=-Xmx` có thể giảm một số lần heap resizing và phù hợp workload ổn định, nhưng tăng memory commitment/footprint khi startup, giảm mật độ Pods và có thể gây lãng phí ở workload bursty. Với microservices trên Azure scale-to-zero/scale-out, một `-Xms` vừa phải có thể có lợi cho **memory efficiency**. Hãy đo startup, GC pauses, RSS, CPU và cost trước khi chọn.

### 5.4. Những tỷ lệ JVM memory flags dễ hiểu sai

- `-XX:MaxRAMPercentage`: giới hạn heap theo tỷ lệ memory JVM xét.
- `-XX:InitialRAMPercentage`: ảnh hưởng initial heap sizing khi không có explicit `-Xms`.
- `-XX:MinRAMPercentage`: **không phải “minimum heap percent” phổ quát**; với HotSpot hiện đại flag này liên quan cách đặt max heap cho hệ thống có memory nhỏ. Đừng dùng nó như cách đặt Xms.
- `-XX:MaxDirectMemorySize`: điều chỉnh giới hạn direct buffer memory của JVM khi áp dụng; không phủ hết native allocations.
- `-XX:MaxMetaspaceSize`: giới hạn metaspace, nhưng quá thấp dễ gây OOME.

### 5.5. Không chọn một tỷ lệ heap chung cho mọi workload

Một REST API có nhiều native Netty buffers và connections có thể cần phần ngoài heap lớn hơn một batch process thuần Java objects. Ở container nhỏ, native overhead chiếm phần đáng kể. Ở container lớn, cận heap quá lớn có thể làm GC/latency/cost xấu. **Đo allocation/native memory trước khi chốt tỷ lệ**.

## 6. CPU limits và tác động tới garbage collection

GC cũng dùng CPU. Một ứng dụng bị CPU throttling có thể phản hồi chậm và GC không có thời gian xử lý đủ nhanh, làm heap live occupancy tăng hoặc tăng GC pressure.

### 6.1. CPU request và CPU limit

Ví dụ Kubernetes:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
  limits:
    cpu: "2"
    memory: "2Gi"
```

Đây là **fragment Kubernetes Pod container resources**, không phải manifest hoàn chỉnh. `500m` là nửa CPU core cho scheduling; `limits.cpu: "2"` đặt quota tới 2 CPUs theo runtime. Node core count và CPU quotas có ảnh hưởng khác nhau tới JVM ergonomics.

### 6.2. CPU throttling

Nếu workload có burst CPU ngắn, quota 1 CPU có thể khiến `container_cpu_cfs_throttled_periods_total` tăng (tên metric phụ thuộc Prometheus/cAdvisor setup), dù CPU usage trung bình chỉ 0.7 CPU. Những khoảng chặn scheduler có thể tạo **tail latency** cho request threads và GC threads.

Đừng thấy GC pause kéo dài rồi lập tức kết luận G1 sai. Kiểm tra:

- JVM CPU usage và container throttled periods/time.
- CPU requests/limits và số cores JVM nhận.
- GC worker threads và application runnable threads.
- Host/node pressure/noisy neighbors.
- Request p99 phân tách theo Pod và thời điểm throttling.

### 6.3. `ActiveProcessorCount`

HotSpot có flag `-XX:ActiveProcessorCount=N` để override processors JVM dùng cho một số ergonomics. Nó có thể ảnh hưởng GC worker pools và thread pools/frameworks tham khảo `availableProcessors()`. Đây là công cụ **có chủ đích**, không phải cờ mặc định cho mọi service. Đặt N cao hơn CPU quota thực tế có thể tăng contention; thấp quá làm giảm throughput.

### 6.4. Chọn scale-up hay scale-out?

Nếu service CPU-bound, tăng `limits.cpu`/instance size có thể giảm throttling; nếu workload stateless và song song tốt, thêm replicas cũng có ích. Nhưng thêm Pods tăng **heap baseline, connection pools, cache memory, CPU startup, DB connections và cost**. So sánh **good requests/s per vCPU và chi phí** thay vì chỉ nhìn latency của một instance.

## 7. Các loại workload Java và GC profile

| Workload | Đặc trưng memory/GC | Ưu tiên | Bẫy |
|---|---|---|---|
| REST API Java/Spring Boot | Objects ngắn hạn, thread pools, HTTP serialization | p95/p99 và good throughput | Nhiều tiny allocations, CPU throttling |
| Batch ETL/analytics | Large heaps, large arrays, long-running loops | Throughput và tổng thời gian | Full GC dài nhưng không ảnh hưởng user nếu window cho phép |
| Message consumer | Burst traffic, object queues, retries | Stable processing lag/idempotency | Unbounded in-memory queue |
| Reactive Netty service | Direct buffers, event loops | Low latency/low memory | Native/direct memory ngoài heap |
| JVM in container serverless | Cold starts, memory tier, scale | Startup và cost per request | Xms quá lớn, eager initialization |
| Search/cache engine | Live set lớn, caching | Memory utilization + predictable pause | Heap lớn/long-lived objects |

**Không có một GC tốt nhất cho mọi loại workload.** Collector choice phụ thuộc JDK vendor/version, allocation profile, latency SLO, heap size, CPU quota và available memory headroom.

## 8. Garbage collection hoạt động theo nguyên lý nào?

GC quản lý các Java objects không còn reachable. Những trình thu gom HotSpot hiện đại dùng các chiến lược như **generational collection, concurrent marking/relocation, evacuation và compaction** với trade-offs khác nhau.

### 8.1. Young và old generations

Nhiều ứng dụng tạo rất nhiều objects sống ngắn (request DTO, JSON fragments, temporary lists). Generational collectors tận dụng thực tế đó:

```text
New Java objects
       |
       v
Young generation (Eden / Survivor concepts)
       |
       +--> unreachable objects reclaimed
       |
       +--> surviving objects retained/promoted over time
                        |
                        v
                    Old generation
                        |
                        +--> long-lived caches/session/data structures
```

Đây là mô hình khái niệm, không phải layout áp dụng y hệt cho mọi collector hoặc JDK version. Chẳng hạn ZGC có tiến hóa hỗ trợ generational mode tùy JDK.

### 8.2. Stop-the-world (STW)

**STW pause** là khoảng thời gian JVM phải dừng một số/thường phần lớn application threads để thực hiện một pha GC/VM operation. Một collector concurrent giảm nhiều công việc STW nhưng thường vẫn có **các điểm đồng bộ/pause ngắn**. “Concurrent GC” không đồng nghĩa “zero pause”.

### 8.3. Throughput, latency và footprint

| Khái niệm | Mục tiêu | Trade-off |
|---|---|---|
| GC throughput | Phần thời gian/CPU dành cho application work | Collector/pause strategy có thể ưu tiên throughput |
| Pause latency | Thời gian dừng mỗi GC, thường đánh giá p95/p99/max | Concurrent work có thể cần CPU/memory |
| Footprint | Heap/native memory và RSS | Low footprint có thể tạo GC pressure |
| Allocation rate | Tốc độ cấp phát objects | Rate cao tăng số lần young GC, không phải lúc nào xấu |
| Live set | Dữ liệu còn reachable lâu dài | Live set lớn gần Xmx gây áp lực GC |
| Headroom | Free space để cấp phát/di chuyển | Thiếu headroom có thể trigger expensive GC/OOME |

### 8.4. Một chỉ số GC không đủ

GC frequency tăng có thể do traffic tăng, còn GC pauses vẫn ngắn và SLO đạt. Ngược lại, một full GC duy nhất 4 giây có thể phá p99 latency và readiness. Cần nhìn **pause distribution, GC CPU time, allocation rate, old-gen occupancy, RSS/cgroup usage, application p99 và throughput** cùng nhau.

## 9. Chọn GC collector: G1, ZGC hay Parallel?

HotSpot hỗ trợ nhiều collector. **Phiên bản JDK là một phần của lựa chọn**: bản LTS/vender-specific builds có thể có defaults và capabilities khác nhau. Ví dụ dưới đây hướng tới **HotSpot Java 17/21**; hãy đọc `java -version` và release notes của đúng runtime trước khi bật một flag.

| Collector | Mục tiêu thường gặp | Điểm mạnh | Rủi ro/cân nhắc |
|---|---|---|---|
| **G1 GC** | Cân bằng throughput và pause time trên nhiều server workloads | Region-based, generational, adaptive; thường là baseline hữu ích | Pause target chỉ là mục tiêu mềm, có thể có mixed/full GC |
| **ZGC** | Pause thấp và tính dự đoán độ trễ khi có đủ headroom | Nhiều pha concurrent, phù hợp service nhạy tail latency | Concurrent CPU/memory overhead, có thể cần tuning/capacity khác |
| **Parallel GC** | Throughput/batch workloads | Thu gom song song, có thể có throughput tốt | STW pauses có thể dài, không phù hợp API p99 chặt |
| **Serial GC** | Môi trường JVM nhỏ/đơn giản trong một số cấu hình | Overhead thấp trong tình huống phù hợp | Một GC thread, dễ pause dài khi heap/tải tăng |

**Không có “G1 luôn chậm” hay “ZGC luôn nhanh nhất”.** ZGC có thể cải thiện pause p99 nhưng tăng CPU; Parallel GC có thể hoàn thành batch nhanh hơn trong điều kiện thích hợp; default collector của từng JDK/image cần được xác minh.

### 9.1. G1 GC làm gì?

G1 chia heap thành các **regions**, ưu tiên thu gom những regions cho lợi ích thu hồi cao trong giới hạn pause target, kết hợp concurrent marking và các pha pause. Nó có young collections và mixed collections khi thích hợp.

```bash
# HotSpot; dùng trong test/staging trước production:
java -XX:+UseG1GC -jar orders-api.jar
```

G1 là lựa chọn khởi đầu thực tế cho nhiều Java APIs khi không có bằng chứng cần collector khác. Nhưng nếu heap quá nhỏ, native buffers lớn hoặc CPU throttling, đổi collector không chữa được căn nguyên.

### 9.2. ZGC và tính tương thích JDK

```bash
# HotSpot build hỗ trợ ZGC:
java -XX:+UseZGC -jar orders-api.jar
```

Ở **JDK 21**, Generational ZGC có thể được chọn trong HotSpot hỗ trợ bằng `-XX:+ZGenerational` cùng `-XX:+UseZGC`; ở các bản JDK sau, behavior/default của ZGC đã tiến hóa. **Không sao chép flag giữa JDK 17/21/các phiên bản mới mà không kiểm tra hỗ trợ và mode thực tế**.

```bash
# Ví dụ cho HotSpot JDK 21 hỗ trợ Generational ZGC:
java -XX:+UseZGC -XX:+ZGenerational -jar orders-api.jar
```

Một flag không được JVM nhận sẽ khiến startup fail. Verify bằng `java -XX:+PrintFlagsFinal -version`, startup logs và GC logs; ghi collector/mode thực trong run report.

### 9.3. Parallel GC

```bash
java -XX:+UseParallelGC -jar batch-worker.jar
```

Với batch job không có tail-latency SLO chặt, có thể cân nhắc collector throughput-oriented. Nhưng nếu job chạy trong Pod limit nhỏ/CPU quota thấp, pause và memory pressure vẫn phải được kiểm tra.

### 9.4. Bảng quyết định ngắn

```text
Is request p99 sensitive to GC pauses?
       |
       +-- No --> Benchmark default/G1 vs Parallel throughput
       |
       +-- Yes --> Start with G1 baseline
                        |
                        +-- SLO met, cost acceptable --> Keep
                        |
                        +-- GC proven dominant tail-latency cause
                                   |
                                   v
                              Benchmark ZGC
                              with sufficient CPU/memory headroom
```

**Đổi GC chỉ sau khi chứng minh GC là một bottleneck quan trọng**. Nếu p99 chậm do SQL query, connection pool, CPU quotas hoặc GC root scanning từ quá nhiều references, chọn ZGC có thể không đủ.

## 10. G1 GC tuning: đặt mục tiêu, không ép số liệu

G1 có nhiều ergonomics tự điều chỉnh; bắt đầu với **mặc định đã được JVM tuning** và chỉ thay vài tham số nếu có dữ liệu.

### 10.1. `MaxGCPauseMillis` là mục tiêu mềm

```bash
java -XX:+UseG1GC -XX:MaxGCPauseMillis=200 -jar orders-api.jar
```

`200` là **mục tiêu điều chỉnh** thời gian pause (ms), **không phải guarantee** mọi pause sẽ dưới 200 ms. JVM cân bằng work/pause; đặt `MaxGCPauseMillis=5` chỉ vì SLO HTTP là 5 ms có thể tăng số collections/CPU, không đem lại kết quả.

### 10.2. Đừng ép young generation bừa bãi

`-Xmn` hoặc các cờ sizing young generation cố định có thể hạn chế G1 tự chọn young size để đạt pause target. Nếu không có benchmark rõ, tránh override young generation. Young GC thường tốt cho objects sống ngắn; không nên cố “giảm số lần GC” bằng mọi giá.

### 10.3. Các dấu hiệu G1 gặp vấn đề

- Young GC pauses cao hơn target lặp lại, request p99 tương quan.
- Mixed collections kéo dài, old-gen occupancy không giảm đủ.
- **Humongous allocations** (đối tượng lớn so với region) tăng áp lực theo G1 region semantics.
- Full GC hiếm nhưng rất dài.
- To-space exhaustion/evacuation failure trong logs.
- Allocation/promotion quá nhanh khi live set gần max heap.

Kiểm tra **allocation profile, object sizes, cache retention, heap sizing và CPU headroom** trước khi thay các flags nâng cao như `G1HeapRegionSize` hay IHOP threshold.

### 10.4. Không tối ưu “số lần GC nhỏ nhất”

Giả sử A có 20 young GCs/giây, mỗi lần 4 ms, p99 API 180 ms; B có 2 GCs/giây nhưng mỗi lần 250 ms, p99 API 850 ms. Nếu SLO p99 là 500 ms, **A tốt hơn** dù GC frequency cao hơn. Tối ưu theo user impact và total cost, không theo số events.

## 11. ZGC: khi nào đáng dùng?

ZGC di chuyển phần lớn công việc sang concurrent phases để giảm độ dài STW pauses. Nó có thể hữu ích cho APIs yêu cầu tail latency rất thấp, nhất là khi G1 GC thực sự góp phần đáng kể vào p99.

### 11.1. Đo đủ ba mặt

Khi benchmark G1 vs ZGC, phải so:

1. **HTTP p95/p99/p99.9 và SLO** dưới cùng load mix.
2. **CPU per good request**, including background GC CPU.
3. **RSS/cgroup memory, allocation headroom và cost**.

Một collector có pause ngắn nhưng dùng thêm CPU khiến Pod bị throttled vẫn có thể làm **end-to-end latency tệ hơn**.

### 11.2. Concurrent collection cần headroom

Với collector concurrent, application tiếp tục cấp phát trong lúc GC xử lý dữ liệu. Nếu allocation rate quá cao, CPU quota quá thấp hoặc heap không đủ headroom, JVM có thể không theo kịp, xuất hiện **allocation stalls** hoặc thất bại cấp phát. Đừng chỉ tăng `-Xmx` mà không xét native/cgroup ceiling.

### 11.3. Đừng mix collectors

Một JVM process chỉ chọn **collector hợp lệ** theo combination flags. Không đặt `-XX:+UseG1GC` và `-XX:+UseZGC` đồng thời trong cùng deployment rồi đoán JVM chọn cái nào; cấu hình có thể bị từ chối. Khi benchmark, tạo các profile riêng, review `JAVA_TOOL_OPTIONS`, startup args và Helm variables.

### 11.4. Collector khác

Shenandoah GC có thể có trong một số OpenJDK/vendor builds nhưng không phải mọi Azure base image; Parallel/Serial đã nói ở trên. **Bám vào công cụ được runtime thực hỗ trợ** thay vì liệt kê collector như tính năng “Azure tự quản lý”.

## 12. GC logs: công cụ đầu tiên khi nghi GC gây chậm

Với HotSpot **JDK 9+**, unified logging hỗ trợ `-Xlog:gc...`. Đây là cách quan sát tương đối nhẹ trong nhiều môi trường, nhưng ghi log quá nhiều cũng tăng disk I/O, log volume/cost và có thể gây overhead.

### 12.1. Ghi GC logs ra stdout

```bash
java -Xlog:gc*:stdout:time,uptime,level,tags \
  -XX:MaxRAMPercentage=60 \
  -XX:+UseG1GC \
  -jar orders-api.jar
```

Container logs sẽ đi qua log collector của AKS/App Service/Container Apps khi logging đã cấu hình. **Không mặc định tất cả stdout đều được thu vào Log Analytics**; cần kiểm tra Container Insights/agent/diagnostic settings và chi phí ingestion.

### 12.2. Rotate GC log files

```bash
java -Xlog:gc*,safepoint:file=/var/log/java/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar orders-api.jar
```

File path phải tồn tại/ghi được, có đủ quota và container filesystem permissions; nếu ghi vào ephemeral disk thì logs mất khi Pod bị thay. Lưu bản cần thiết vào centralized logging qua phương án được duyệt, có **retention/cost** và không mount volume vô hạn.

### 12.3. Dấu hiệu trong GC logs

```text
[2026-11-20T...] [info][gc,start] GC(142) Pause Young ...
[2026-11-20T...] [info][gc,heap ] GC(142) Eden regions: ...
[2026-11-20T...] [info][gc      ] GC(142) Pause Young ... 72M->35M(...) 8.7ms
```

Đây là **log minh họa**, không phải output thực tế từ JDK/container. Cần nhìn:

- Event type (young/mixed/full/concurrent).
- Pause duration và timestamp/uptime.
- Heap before/after, capacity.
- Frequency và promotion/old occupancy.
- Safepoint data nếu bật.
- Các warnings khi GC thiếu headroom.

### 12.4. Java 8 khác cú pháp

Các JDK 8 trước unified logging có cờ khác như `-XX:+PrintGCDetails`, `-Xloggc:...` tùy vendor/build. **Không copy `-Xlog:gc*` vào Java 8 mà không kiểm tra**; ưu tiên JDK LTS được hỗ trợ, chuẩn hóa base images.

### 12.5. Dừng tại “có tương quan” chưa đủ

Nếu một HTTP request mất 1.2 giây khi có GC pause 10 ms, GC không giải thích phần còn lại. Correlate GC logs với **request traces, CPU throttling, database spans và thread dumps**. Cần phân biệt **pause do GC** với **VM safepoint hoạt động khác**.

## 13. Công cụ Java: `jcmd`, `jstat`, `jstack` và JFR

Những công cụ này được cung cấp theo **JDK distribution** hoặc image; slim JRE/container images có thể thiếu `jcmd`/`jfr` hoặc không đủ attach permissions. Trên production, truy cập JVM diagnostics là hoạt động nhạy cảm: cần least privilege, change/ticket, timebound và tránh xuất secrets.

### 13.1. `jcmd`

```bash
# Liệt kê Java processes trong namespace/container hiện tại.
jcmd -l

# Xem heap overview khi được JVM/OS cho phép.
jcmd <pid> GC.heap_info

# Xem flags được JVM process thực dùng.
jcmd <pid> VM.flags
```

`<pid>` là placeholder; không paste nguyên chuỗi vào shell. `jcmd` có thể yêu cầu **same OS user/namespace** và attach mechanism được JVM cho phép. Tránh dùng `kill -QUIT` tùy tiện nếu app logging không được quản lý vì nó có thể in dump vào logs.

### 13.2. `jstat`

```bash
jstat -gcutil <pid> 1000 10
```

Ví dụ lấy khoảng 10 samples cách nhau 1 giây. Các cột phụ thuộc JDK; đo young/old occupancy, GC count/time, không chỉ số `FGC`. Một process trong Pod khác không tự attach được nếu container namespaces/security policies ngăn cản.

### 13.3. Thread dump

```bash
jcmd <pid> Thread.print
```

Thread dump giúp thấy blocked/waiting/runnable threads, deadlocks và pool saturation. Nhiều thread WAITING là **bình thường** trong servers; không tự coi mọi WAITING là thread leak. Thread dump có thể chứa class/method names và context nhạy cảm; lưu tại nơi được phép.

### 13.4. Java Flight Recorder

**JFR** thu event-level profiling (GC, allocation, locks, CPU, thread scheduling, I/O...) với overhead thường phù hợp production khi cấu hình cẩn trọng. Tạo recording mẫu:

```bash
jcmd <pid> JFR.start name=orders-profile settings=profile duration=120s filename=/tmp/orders-2min.jfr
```

Hoặc bật qua startup:

```bash
java -XX:StartFlightRecording=duration=120s,filename=/tmp/startup.jfr,settings=profile \
  -jar orders-api.jar
```

JFR có thể chứa **class names, stack traces, method references, endpoints, allocation data và thông tin nội bộ**. Không upload raw recordings lên kênh công khai; hạn chế quyền truy cập và retention. `settings=profile` có thể overhead cao hơn `default`; chạy trong thời gian ngắn, kiểm tra disk space và đo tác động.

### 13.5. Xem JFR bằng Java Mission Control

**Java Mission Control (JMC)** phân tích recordings để tìm allocation hotspots, GC pauses, CPU method activity và threads/locks. Cần phân biệt **allocation profile** với **heap-retained graph**: nơi cấp phát nhiều nhất chưa chắc là nơi giữ objects lâu nhất.

### 13.6. Chọn công cụ theo triệu chứng

| Triệu chứng | Bước đo đầu |
|---|---|
| p99 spikes, nghi GC | GC logs + JFR GC events + request traces |
| CPU cao | JFR CPU profiling + thread analysis + CPU throttling |
| Heap tăng liên tục | Heap occupancy trend, class histogram, retained heap analysis |
| RSS tăng, heap ổn định | NMT/direct-buffer/native metrics |
| Thread count tăng | Thread dump + thread metrics |
| Startup chậm | JFR startup, class loading/JIT, dependency initialization |
| 403/SQL timeout sau deploy | Azure network/RBAC/dependency tracing; chưa chắc liên quan GC |

## 14. Native Memory Tracking (NMT) khi heap không giải thích RSS

**Native Memory Tracking** là khả năng HotSpot ghi nhận **các loại native memory allocations do JVM quản lý** (phụ thuộc JVM), hữu ích khi process RSS cao nhưng heap used không lớn.

### 14.1. Bật NMT cần restart process

```bash
JAVA_TOOL_OPTIONS="-XX:NativeMemoryTracking=summary"
```

Hoặc `detail` cho mức chi tiết hơn nếu cần; cả hai có **overhead CPU/memory và dữ liệu khác nhau**. Không bật detail vô thời hạn ở production nếu chưa đánh giá overhead.

### 14.2. Xem thống kê

```bash
jcmd <pid> VM.native_memory summary
```

NMT có thể phân loại memory theo Java Heap, Class/Metaspace, Thread, Code, GC, Compiler, Internal, Symbol, Arena... theo JDK/version. Nếu muốn so trước/sau:

```bash
jcmd <pid> VM.native_memory baseline
# Chạy workload tương ứng rồi:
jcmd <pid> VM.native_memory summary.diff
```

### 14.3. NMT không bằng tổng RSS

NMT chủ yếu quan sát native allocations do HotSpot/JVM ghi nhận, **không thể được xem là profiler hoàn chỉnh của mọi native allocation bên thứ ba, mapped files, page cache hoặc mọi cgroup charge**. Một số library allocations do bên ngoài JVM theo dõi không đầy đủ. Đối chiếu với OS process maps/smaps và container metrics khi cần.

### 14.4. Khi thread memory bất thường

Nếu NMT cho thấy Thread reserved/committed memory tăng, kiểm tra **thread count và stack usage**. Tối ưu thread pool sizes, tránh tạo thread mỗi request, dùng async I/O phù hợp hoặc concurrency limits; giảm `-Xss` chỉ sau khi đã test worst-case stack depth.

### 14.5. Direct buffer leak

Với Netty/ByteBuffer, kiểm tra direct memory gauges, pooling, buffer release behavior. `OutOfMemoryError: Direct buffer memory` khác `Java heap space`. Một số native libraries quản lý memory riêng ngoài direct buffer cap; cần profile đúng allocator, không chỉ tăng `-XX:MaxDirectMemorySize`.

## 15. Heap dump, class histogram và an toàn dữ liệu

### 15.1. Heap dump khi Java heap OOME

```bash
java -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/dumps \
  -jar orders-api.jar
```

Heap dump có thể chứa **passwords, tokens, customer PII, request payloads và application objects**. Chỉ bật khi có incident/data handling policy, disk đủ chỗ, storage mã hóa, access control/retention. Heap dump thường rất lớn, có thể làm đầy ephemeral disk và **không bảo đảm tạo được khi kernel `OOMKilled`**.

### 15.2. `jcmd GC.heap_dump` có chi phí

```bash
jcmd <pid> GC.heap_dump /dumps/orders-heap.hprof
```

Command có thể gây pause/overhead và tốn disk lớn; tùy flags/JDK có thể trigger full GC để dump live objects. Không chạy đồng loạt trên toàn bộ production fleet lúc hệ thống đang quá tải. Thực hiện theo runbook và canary một Pod với resource headroom đủ.

### 15.3. Class histogram

```bash
jcmd <pid> GC.class_histogram
```

Class histogram cho biết số instances và bytes theo class trong một thời điểm; **không chứng minh ai đang giữ reference**. Phân tích retained graph/GC roots từ heap dump khi nghi leak, chú ý khả năng histogram/dump gây pause và dữ liệu nhạy cảm.

### 15.4. Các nhóm leak phổ biến

- Cache không có eviction/TTL hoặc keys tăng vô hạn.
- Static collections giữ objects lâu dài.
- ThreadLocal không cleanup trong thread pool.
- Listeners/subscriptions/CompletableFuture references không release.
- ClassLoader leak khi dynamic reload/plugins.
- Unbounded queue/producer faster than consumer.
- Direct buffers/netty resources không được release.
- JDBC connections/streams/sockets không close, tạo native/resource pressure.

**Đừng sửa mọi trường hợp bằng tăng `-Xmx`**: tăng heap chỉ kéo dài thời gian trước khi leak chạm trần, tăng cost và có thể làm GC full cycle dài hơn.

## 16. Allocation profiling và cải thiện Java code

Nếu ứng dụng tạo 2 GB temporary objects/giây, collector phải xử lý lượng cấp phát lớn. Tối ưu allocation **có thể giảm GC CPU và memory**, nhưng cũng dễ làm code khó đọc hoặc tăng bugs nếu tối ưu mù quáng.

### 16.1. Đo allocation hotspots trước

JFR allocation events/profilers có thể cho biết:

- Phương thức tạo nhiều `String`/`byte[]`/DTO.
- JSON parsing/serialization tạo temporary buffers.
- Mapping từ database rows sang objects.
- Regex compilation trong hot path.
- Logging string concatenation khi log level thấp.
- In-memory collection copies/streams rất nhiều.

Đánh giá **bytes allocated per successful request**, không chỉ tổng bytes/sec; traffic tăng có thể giải thích total allocations tăng nhưng hiệu quả mỗi transaction vẫn ổn.

### 16.2. Anti-pattern: lập tức ghép chuỗi log

```java
// Tránh tạo chuỗi lớn khi DEBUG tắt và logger vẫn tính biểu thức.
logger.debug("Order payload: " + serializeOrder(order));
```

Thay bằng structured/lazy logging:

```java
if (logger.isDebugEnabled()) {
    logger.debug("Processing orderId={}", order.getId());
}
```

Đây là fragment dùng SLF4J-style logger. Không log raw order payload/PII/token để tối ưu allocation; phần lợi là **giảm serialization không cần thiết**, không chỉ thay string concatenation.

### 16.3. Tránh unbounded cache

```java
// Ý tưởng sai: bộ nhớ tăng theo mọi customer key từng được truy cập.
Map<String, Order> foreverCache = new ConcurrentHashMap<>();
```

Thay bằng **bounded cache** có maximum size/weight, eviction/TTL và metrics; thư viện/cache cụ thể (ví dụ Caffeine) cần thêm dependency/version theo dự án. Kiểm tra **cache hit rate, retention, eviction, stale-data policy** và heap dùng dưới peak traffic.

### 16.4. Đừng tối ưu thành sự cố chức năng

Object pooling tự viết cho short-lived objects có thể làm tăng contention, retention và bugs hơn là giảm GC; generational collectors vốn xử lý many short-lived allocations khá tốt. Chỉ tối ưu sau profiling khi hotspot đáng kể, và luôn có regression tests.

## 17. AKS: cấu hình CPU/memory JVM và Kubernetes

AKS dùng Kubernetes để quản lý Pods/Deployments. JVM chạy bên trong container nên chịu **container resource limit**, các cgroup policies và scheduling của node pool. Tuning có ít nhất hai lớp độc lập: **Java flags** và **Kubernetes resources**.

### 17.1. Deployment manifest mẫu

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: java-api
          image: <approved-acr>/orders-api:<pinned-image-tag>
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "2Gi"
          env:
            - name: JAVA_TOOL_OPTIONS
              value: >-
                -XX:MaxRAMPercentage=60
                -XX:+UseG1GC
                -Xlog:gc*:stdout:time,uptime,level,tags
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 6
      terminationGracePeriodSeconds: 45
```

**Đây là manifest minh họa**, cần namespace, image, ports, application endpoints, policy, identity, ingress/service và ConfigMaps/secrets do dự án triển khai. `<approved-acr>` và `<pinned-image-tag>` là placeholders. Không đưa manifest trực tiếp vào production mà chưa kiểm tra **Spring Boot Actuator health probes** có bật và đường dẫn thực tồn tại. Những ngưỡng 5s/10s/36/45s là ví dụ; đo startup và workload trước khi đặt.

### 17.2. `JAVA_TOOL_OPTIONS`

JVM đọc biến `JAVA_TOOL_OPTIONS` trong những launcher/embedding modes hỗ trợ, thường hữu ích khi container entrypoint chạy Java. Nhưng **cờ từ environment có thể không áp dụng như bạn nghĩ nếu entrypoint tự override args**. Kiểm tra logs/startup command và `jcmd VM.flags` trên JVM thực. Không vô tình chèn credential/token vào `JAVA_TOOL_OPTIONS` vì biến có thể xuất hiện trong process/environment diagnostics.

### 17.3. Heap max ~60% không chứng minh 2 GiB là đủ

Kubernetes memory limit 2Gi + JVM MaxRAMPercentage 60 chỉ là **giới hạn heap tương đối**. Đo direct buffer memory, metaspace, thread count, code cache, RSS và cgroup usage khi traffic peak. Nếu còn 800 MiB nhưng native dùng 900 MiB, Pod vẫn OOM. Cần giảm nguồn native memory hoặc tăng container limit hợp lý, không chỉ giảm heap ngẫu nhiên.

### 17.4. CPU limit trong AKS ảnh hưởng GC

Nếu đặt `limits.cpu: 500m` mà application load cần 2 cores cho JIT + GC + request threads, CPU throttling có thể làm p99 rất xấu. Điều chỉnh theo SLO và node capacity; một số workloads có thể chọn không đặt CPU limits theo policy, nhưng cần hiểu multi-tenant fairness/cost/quotas. Không coi “bỏ CPU limit” là một best practice chung cho mọi cluster.

### 17.5. Probe đúng tránh restart storm

Một STW GC tạm thời có thể khiến probe bị timeout. Nếu liveness quá nhạy, Kubernetes sẽ restart Pod trước khi nó tự phục hồi; ngay sau restart, classloading/JIT warm-up làm CPU và memory tăng rồi lại timeout – tạo **restart loop**.

Phân biệt:

- **Startup probe:** cho phép quá trình khởi động lâu hơn mà không bị liveness/readiness gây gián đoạn theo cơ chế hỗ trợ.
- **Readiness probe:** báo Pod có nên nhận traffic hay không, khi không ready sẽ được loại khỏi traffic routing theo Kubernetes service semantics.
- **Liveness probe:** xác định process cần restart; chỉ dùng khi có bằng chứng unrecoverable stall/hang.

Không đặt liveness check phụ thuộc trực tiếp mọi external dependency (Azure SQL/Key Vault/Service Bus) khiến toàn fleet restart khi dependency chung chập chờn. Readiness và circuit breaker cần thiết kế theo cách degraded operation của dịch vụ.

## 18. Startup, readiness và graceful shutdown của Spring Boot

### 18.1. JVM warm-up và JIT

Java service có thể cần:

1. Load classes và initialize frameworks.
2. Load Spring application context, validate configuration.
3. Initialize database connection pools, HTTP clients.
4. Warm JIT code paths khi có traffic.
5. Populate bounded caches.
6. Đạt mức ổn định memory/latency.

Không gộp “JVM đã listen port 8080” với “ứng dụng đã warm và sẵn sàng chịu peak traffic”.

### 18.2. Spring Boot health endpoints

Nếu dùng Spring Boot Actuator và đã cấu hình liveness/readiness probes:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Các endpoints cần exposure/configuration/security phù hợp với version Spring Boot. Không công khai `/actuator/heapdump`, `/env`, `/configprops` hoặc diagnostic endpoints nhạy cảm ra Internet. Chỉ health information cần thiết được phép công khai nội bộ.

### 18.3. Graceful shutdown

Khi Kubernetes scale down/rollout:

```text
SIGTERM to container
    |
    +--> stop accepting new traffic/readiness false
    +--> finish in-flight requests / commit offsets where safe
    +--> close DB pools, HTTP clients, telemetry exporters
    +--> exit within terminationGracePeriodSeconds
```

Ứng dụng cần xử lý SIGTERM và server graceful shutdown theo framework/runtime. Nếu Pod bị `SIGKILL` do vượt memory cgroup hoặc grace period hết, không thể trông chờ `finally`/shutdown hooks luôn chạy. Với Service Bus worker, áp dụng **idempotency + at-least-once handling**, không assume mọi message đã ACK.

### 18.4. Java framework settings

Spring Boot có cấu hình graceful shutdown và lifecycle timeout theo version. Không copy một property từ Boot 2.x sang Boot 3.x mà không verify docs và test deployment. Khi chạy health probes và shutdown, mục tiêu là **không đưa Pod chưa sẵn sàng vào load balancer** và **không giết Pods tạm pause bởi GC**.

## 19. HPA, VPA, Cluster Autoscaler và tác động JVM

Tăng replicas/size cũng là một phần hiệu năng, nhưng mỗi cơ chế giải quyết bài toán khác nhau.

### 19.1. Horizontal Pod Autoscaler (HPA)

HPA thường scale số Pod dựa trên CPU utilization hoặc custom/external metrics qua adapters theo configuration. Nếu `requests.cpu` quá thấp so với mức dùng thực, CPU utilization tương đối cao và HPA scale ra nhiều Pods không cần thiết. Nếu CPU-bound do GC thrashing, scale-out có thể giúp tạm thời nhưng cũng làm tổng memory/cost tăng và che vấn đề heap/caches.

### 19.2. Vertical Pod Autoscaler (VPA)

VPA có thể recommend/adjust requests theo policy, và trong những modes/version có thể yêu cầu recreate Pods. Không triển khai VPA auto changes và HPA cùng dùng CPU utilization mà không có thiết kế phối hợp rõ; tránh autoscaling “đánh nhau” hoặc resize gây app restarts.

### 19.3. Cluster Autoscaler

Cluster Autoscaler thêm/giảm nodes khi scheduling capacity cần theo constraints; nó không tự tối ưu `-Xmx` cho container. Một Pod memory request quá lớn có thể không schedule dù runtime heap nhỏ. **Requests ảnh hưởng bin packing, node pool SKU và chi phí**.

### 19.4. Autoscale theo queue workload

Với Service Bus consumers, có thể dùng external queue-length metrics hoặc KEDA-based scaling theo pattern được hỗ trợ. Phải giám sát **processing rate, oldest message age, DLQ, downstream Azure SQL capacity**; nếu scale 100 workers nhưng SQL có max connections thấp, tổng throughput có thể giảm vì contention.

### 19.5. Chi phí heap khi scale-out

Giả sử 6 Pods, mỗi Pod có heap committed 1.2 GiB, dù live-set nhỏ; tăng lên 18 Pods làm tổng heap reservations/committed memory của fleet tăng đáng kể. Khi so scale-up/scale-out, tính **cost per good transaction, node utilization, connection pressure và failure isolation**.

## 20. Azure App Service: tối ưu JVM theo Plan và runtime

Ứng dụng Java có thể chạy trên **Azure App Service** theo runtime stack hoặc container tùy cấu hình/plan/OS. App Service abstractions khác AKS: resource quotas, plan instance size, scale-out và cách truyền startup flags chịu ảnh hưởng loại hosting.

### 20.1. Managed Java runtime vs custom container

| Mô hình | JVM flags/configuration | Cần kiểm tra |
|---|---|---|
| App Service managed Java runtime | Startup settings/platform configuration theo OS/stack/version | JVM version, supported settings, plan memory, restarts |
| App Service custom container | Docker image entrypoint/`JAVA_TOOL_OPTIONS`/App Settings | Container memory constraints, image/JDK, logs |
| App Service plan scale-out | Nhiều worker instances của plan | Instance memory, shared plan contention, auto-scale |

Không giả định một biến môi trường/option dành cho Linux custom container có ý nghĩa y hệt Windows managed Java runtime. **Kiểm tra cách App Service startup Java thực tế**.

### 20.2. App Service Plan là boundary tài nguyên quan trọng

Nhiều apps có thể chia sẻ cùng App Service Plan instances. Một app Java dùng nhiều heap/native memory có thể ảnh hưởng các apps khác trên cùng plan. Nếu memory pressure, xét **tổng plan memory, workers/instances và các apps cùng chạy**, không chỉ heap của một web app.

### 20.3. Sizing trước khi scale plan

1. Xem App Service metrics: memory/CPU, HTTP queue, restarts và per-instance health theo features được hỗ trợ.
2. Xem Application Insights requests/dependencies/p95.
3. Xem JVM heap/GC/native metrics từ app.
4. Kiểm tra connection pools/threads/native memory.
5. Chọn tăng Plan SKU, scale-out, hay tối ưu JVM theo bottleneck.

Không nâng SKU gấp đôi nếu bottleneck chính là SQL queries hoặc memory leak không giới hạn.

### 20.4. Warm-up và slot swap

Deployment slots và slot swap có thể giúp giảm interruption nếu cấu hình đúng, nhưng **JVM warm-up, cached state, slot-specific settings, Key Vault references và database connections** cần được kiểm tra. Không coi slot swap là phương pháp “tự tránh mọi cold start”. Một app được cấu hình `Xms=Xmx` quá lớn có thể mất thời gian/memory khi warm-up hoặc gây memory pressure trên plan.

### 20.5. Log và dump trên App Service

GC logs/JFR/heap dumps phải được thu bằng cách nền tảng hỗ trợ và tuân thủ access/data retention. App Service filesystem path/quota/per-instance lifecycle khác AKS; không hard-code `/dumps` rồi mặc định có persistent volume. Heap dump chứa PII/secrets; đừng dùng unauthenticated diagnostic endpoint.

## 21. Azure Container Apps: memory tier, revision và scale

**Azure Container Apps** chạy container workloads có CPU/memory resources và revision/scale behavior do nền tảng quản lý; JVM vẫn chịu budget của container.

### 21.1. Sizing giống về nguyên lý, khác cách vận hành

Khi cấu hình Container Apps CPU/memory, chọn memory tier được hỗ trợ bởi workload profile/plan hiện hành. **Không giả định mọi kết hợp CPU/memory đều hợp lệ**. JVM flags như `MaxRAMPercentage` vẫn cần kiểm tra bằng runtime JDK/container detection.

### 21.2. Scale-to-zero và startup latency

Với workload có scale-to-zero, **JVM cold start** có thể ảnh hưởng request latency và cost; tăng heap/Xms quá lớn, classloading, spring context, network authentication và dependency warm-up đều góp phần. Cân nhắc min replicas theo availability/SLO và chi phí; nếu ứng dụng buộc phản hồi trong 200 ms cho request đầu tiên, scale-to-zero có thể không phù hợp nếu startup không đạt.

### 21.3. Revision rollout

Một JVM flag change tạo container revision/config change theo cơ chế nền tảng. Dùng **traffic splitting/canary/revision health** khi được hỗ trợ, so p95/GC/memory trước/sau. Không scale toàn bộ traffic sang revision chưa chạy warm-load test chỉ vì container healthy.

### 21.4. Secrets và identity

Khi dùng Azure Key Vault/managed identity để lấy config trong startup, network/identity failures có thể gây cold start chậm hoặc restart loop. **Đừng gọi mọi key vault secret trên mỗi request** nếu không cần. Tách GC diagnostics với dependency startup/connection errors.

## 22. Azure Virtual Machines: khi nào có quyền tuning sâu hơn?

Trên Azure VM, bạn có thể kiểm soát OS/JDK, memory, CPU, GC logs, NMT, profilers và disk layout nhiều hơn managed PaaS, nhưng cũng phải quản lý patching, identity, scaling, backup và bảo mật.

### 22.1. Không có cgroup limit chưa chắc JVM sizing phù hợp

Nếu chạy Java trực tiếp trên VM không bị container limit, JVM có thể xét **VM physical memory**; một VM còn chạy SQL agent, monitoring, reverse proxy và nhiều Java processes. `MaxRAMPercentage=75` trên từng process có thể tạo tổng memory overcommit. Với nhiều JVM trong một VM, **đặt `-Xmx` theo tổng resource budget của VM**.

### 22.2. NUMA và instance sizes

Ở những VM lớn/multi-socket/NUMA, placement/memory locality và GC threads có thể ảnh hưởng performance. Đừng bật các NUMA flags chỉ theo “best practice” chung; benchmark đúng VM SKU/OS/JDK. Với multi-tenant host, Azure VM vCPU và burstable SKU credits/host contention có thể ảnh hưởng CPU throughput.

### 22.3. Disk cho dumps và logs

Heap dump/JFR/GC logs có thể rất lớn. Chọn disk path, encryption, IO budget, retention và export; tránh ghi đầy OS disk hoặc temporary disk mà tưởng persistent. Khi VM scale set thay instance, logs/dumps trên local disk có thể mất nếu không được thu tập trung.

### 22.4. Cấu hình service

Nếu dùng `systemd` hoặc process supervisor, JVM args/`JAVA_TOOL_OPTIONS`, memory limits và restart policy cần được khai báo version-controlled, không chỉnh tay giữa incidents rồi quên IaC. Lưu ý runtime flags có thể bị override bởi entrypoint/systemd environment.

## 23. Dockerfile và Java container image production

Một image ổn định cần **JDK version pinning, non-root user, minimal dependencies, observability** và runtime flags có thể kiểm tra.

### 23.1. Dockerfile mẫu

```dockerfile
# Replace placeholders with approved, pinned runtime image/digest.
FROM <approved-jre-21-base-image>

WORKDIR /app
COPY --chown=10001:10001 orders-api.jar /app/orders-api.jar
USER 10001:10001

ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60 -XX:+UseG1GC -Xlog:gc*:stdout:time,uptime,level,tags"
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
```

**Không thể build nguyên văn** vì `<approved-jre-21-base-image>` là placeholder. Chọn base image JDK/JRE đã được security team approve và pin digest/tag phù hợp; nếu cần `jcmd`/JFR diagnostics, slim runtime image có thể cần provisioning/debug workflow riêng.

### 23.2. Không hard-code heap chỉ bằng memory request

Nếu environment đặt container limit 1Gi ở dev và 4Gi ở prod, `MaxRAMPercentage` có thể hữu ích khi JVM detect cgroup đúng, nhưng nếu native memory rất khác theo traffic, vẫn phải benchmark. Một image không phù hợp mọi plan size/instance. Values nên override bằng controlled deployment configuration/Helm với review.

### 23.3. JDK và security patching

Pin **JDK major/build** để tránh GC behavior drift giữa environments, nhưng có kế hoạch cập nhật **security patches**. Upgrade JDK có thể thay GC defaults, TLS libraries, cgroup interpretation và JIT optimizations; cần load test/metrics so trước khi production rollout.

### 23.4. JDK runtime vs diagnostic tools

Một Java runtime tối giản giảm attack surface và image size nhưng có thể thiếu `jcmd`, `jfr`, shell, `nslookup`. Thiết kế **ephemeral debug container hoặc pre-approved diagnostic image** có permissions phù hợp; không chạy production service as root chỉ để attach profiler.

## 24. Azure Monitor, Application Insights, Prometheus và JVM telemetry

Một giải pháp observability hiệu quả phải nối **JVM internals** với **user request SLI** và **Azure infrastructure signals**.

```text
JVM/Spring Boot
    |     |
    |     +--> OpenTelemetry / Application Insights traces
    |             requests, dependencies, exceptions
    |
    +--> Micrometer/JMX JVM metrics
          heap, non-heap, GC pause, threads, CPU
             |
             v
      Metrics exporter / Prometheus scrape / Azure Monitor integration
             |
             v
Azure Monitor / Log Analytics / Azure Monitor workspace
             |
             +--> Workbook: request latency + GC + RSS
             +--> Alerts: error-rate, OOM, throttling, leak pattern
             +--> Grafana dashboard (when integrated)
```

### 24.1. Các nguồn Azure

| Nguồn | Đo cái gì | Lưu ý |
|---|---|---|
| **Application Insights** | Java requests, exceptions, dependencies, traces theo instrumentation | Không tự chứa mọi JVM/native/cgroup metric nếu chưa instrument |
| **Azure Monitor Metrics** | Platform metrics CPU/memory/restarts theo resource và khả năng hỗ trợ | Units/aggregation/data delay khác JMX |
| **AKS Container Insights** | Container/node logs và một số performance inventory/metrics theo config | Tính năng có thể thay đổi theo agent/collection mode |
| **Managed Prometheus + Azure Monitor workspace** | Prometheus-style metrics từ cluster/app exporters | Cần cấu hình scraping, ingestion, labels, RBAC |
| **Azure Managed Grafana** | Trực quan hóa Prometheus/other sources | Viewer cần quyền datasource |
| **Log Analytics/KQL** | Logs/GC events khi đã được thu | Không tự có các JVM metrics dưới dạng table |
| **JFR/heap dump** | Diagnostics mức JVM | Không thay metrics liên tục; nhạy cảm và có overhead |

### 24.2. JVM metrics thường gặp

Tùy Micrometer/Prometheus naming/version:

```text
jvm_memory_used_bytes{area="heap"}
jvm_memory_committed_bytes{area="heap"}
jvm_gc_pause_seconds_count
jvm_gc_pause_seconds_sum
jvm_threads_live_threads
process_cpu_usage
process_resident_memory_bytes
```

**Các metric names trên mang tính minh họa theo một số exporters**, không đảm bảo xuất hiện y hệt trong mọi Micrometer/OTel/Prometheus setup. Dùng metric discovery/exposition thực; không viết Grafana chart dựa trên metric chưa có.

### 24.3. Spring Boot Actuator + Micrometer

Với dependencies và config tương ứng, Spring Boot Actuator có thể expose health/metrics. Một endpoint Prometheus thường:

```text
GET /actuator/prometheus
```

Điều kiện: đã thêm Micrometer Prometheus registry/Actuator và cấu hình endpoint exposure/security. **Không public exporter endpoint** nếu metrics có thông tin nhạy cảm; cho scraper trong network được phép, giới hạn cardinality/labels và runtime overhead.

### 24.4. OpenTelemetry không tự đọc mọi metric

Java OpenTelemetry instrumentation/exporter có thể gửi JVM/runtime metrics theo agent/version/config phù hợp, nhưng không đồng nghĩa tự có GC pause histogram chính xác trong Log Analytics. Đánh giá **schema, exporter, sampling, collection interval và backend** trước khi xây SLO.

### 24.5. Dữ liệu GC trong stdout cần labeling

Với nhiều Pod, log `GC(42)` chỉ có nghĩa trong process và uptime đó, không phải global GC ID. Log collector nên gắn **cluster, namespace, workload, pod, container, image version và timestamp**. Trong Workbook, phân biệt Pod cũ mới sau rollout, tránh so “GC count” của process trước và sau restart như một chuỗi liên tục.

## 25. Dashboard: nối GC, memory, CPU throttling với API latency

Một trang Workbook/Grafana cho hiệu năng Java nên hiển thị **business impact trước**, JVM internals sau.

```text
Orders API — production, southeastasia, last 60 minutes
┌────────────────────────┬────────────────────────┬────────────────────┐
│ Good requests/s        │ Error rate / timeouts  │ HTTP p95/p99       │
├────────────────────────┴────────────────────────┴────────────────────┤
│ CPU utilization / throttled time   | Container working set / limit   │
├────────────────────────┬────────────────────────┬────────────────────┤
│ Heap used / committed  │ GC pause p95/max       │ GC CPU / time %    │
├────────────────────────┴────────────────────────┴────────────────────┤
│ Thread count | Native/direct memory | JVM old-gen occupancy         │
├────────────────────────┬────────────────────────┬────────────────────┤
│ Pod restarts / OOMKilled│ Deployment version    │ Data freshness     │
└────────────────────────┴────────────────────────┴────────────────────┘
     Drill-down: trace ID / GC log segment / JFR / runbook / cost
```

### 25.1. Đặt cùng trục thời gian

Xem một spike HTTP p99 ở 10:03, đối chiếu GC pause at ~10:03, throttling, request queues, SQL duration và Pod restart. Traces/GC logs/Prometheus có **scrape intervals, timestamps, clock skew và ingestion latency** khác nhau; dùng cửa sổ đủ rộng, không áp tương quan nhân quả chỉ vì hai dots gần nhau.

### 25.2. CPU usage bình thường nhưng throttling cao

Mức sử dụng CPU trung bình 70% của limit không phủ định burst throttling. Khi thấy `container_cpu_cfs_throttled_seconds_total` tăng, cần nhìn **throttled time / CPU periods / API request latency** theo Pod, nhất là thời điểm tăng load/JIT/GC. Platform metric thiếu throttling có thể cần managed Prometheus/cAdvisor/other collector.

### 25.3. Heap used thấp nhưng RSS cao

Đặt `heap used` cạnh `heap committed`, NMT categories và `container working set`. Nếu heap vẫn 800 MiB trong khi cgroup usage tăng 1.2 → 1.9 GiB, điều tra native/direct, threads, sidecars, page cache trước khi đặt lại Xmx.

### 25.4. GC pause từ counters và histograms

Một Prometheus exporter thường cho `jvm_gc_pause_seconds_count` và `jvm_gc_pause_seconds_sum` (tùy setup). Có thể xem:

```promql
# Số GC pause events/second (trong scope đã chọn).
rate(jvm_gc_pause_seconds_count{application="orders-api"}[5m])

# Tổng GC pause wall-clock seconds/second, không phải CPU usage.
rate(jvm_gc_pause_seconds_sum{application="orders-api"}[5m])
```

Không gọi ratio thứ hai là “CPU % GC”, vì **tổng pause wall-clock duration** không phản ánh đầy đủ concurrent GC worker CPU. Một GC có các threads chạy song song, tính wall-clock và CPU-seconds khác nhau. Metrics cụ thể phải xác minh exposition.

### 25.5. p95 GC pause từ histogram

Nếu exporter thực sự có histogram `jvm_gc_pause_seconds_bucket` với labels phù hợp, có thể dùng:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(jvm_gc_pause_seconds_bucket{application="orders-api"}[5m])
  )
)
```

**Không đảm bảo `jvm_gc_pause_seconds_bucket` luôn tồn tại.** Một số exporter chỉ có count/sum hoặc SLO buckets khác, và instrumentation có thể đo pause types khác nhau. Để tính percentile đáng tin, cần histogram buckets đủ độ phân giải và method phù hợp; không lấy average từ count/sum rồi đặt tên p95.

### 25.6. Dashboard trạng thái dữ liệu

Nếu một Pod đã bị OOMKilled, JVM metrics có thể biến mất. Dashboard phải hiển thị **missing data / Pod terminated** chứ không kết luận `heap used=0` là “đã tối ưu”. Tách “không có GC events” (có thể bình thường) khỏi “không có exporter data”.

## 26. KQL và log correlation trên Azure

Các truy vấn KQL sau là ví dụ khi **workspace-based Application Insights** tạo tables như `AppRequests` và `AppDependencies`. Schema/table names có thể khác theo instrumentation, SDK và workspace configuration; kiểm tra schema explorer trước khi dùng. KQL không trực tiếp truy vấn mọi Prometheus metrics nếu chưa có query integration phù hợp.

### 26.1. API latency và errors theo 5 phút

```kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| summarize
    Requests = count(),
    Failed = countif(Success == false),
    P95Ms = percentile(DurationMs, 95),
    P99Ms = percentile(DurationMs, 99)
  by bin(TimeGenerated, 5m)
| extend ErrorPct = iff(
    Requests > 0, 100.0 * todouble(Failed) / Requests, real(null))
| order by TimeGenerated asc
```

**`Success=false` chưa chắc đúng business error SLI** (cách đếm client 4xx, 429, timeouts và sampling cần định nghĩa). Để so giữa collector versions, phải kiểm tra `DurationMs` units và trace sampling weighting.

### 26.2. SQL/Service Bus dependency latency

```kusto
AppDependencies
| where TimeGenerated >= ago(2h)
| where AppRoleName == "orders-api"
| summarize
    Calls = count(),
    Failures = countif(Success == false),
    P95Ms = percentile(DurationMs, 95)
  by Target, Type
| order by P95Ms desc
```

Nếu `Target` có full URLs chứa PII/order IDs, cần sanitize/canonicalize trước khi chia sẻ. Nếu thấy SQL p95 tăng cùng request p99 nhưng GC pause không đổi, **tập trung điều tra SQL/pool trước**.

### 26.3. GC log ingestion

Nếu GC logs stdout được collector gửi vào một Log Analytics table của cluster, schema có thể là `ContainerLogV2` hoặc table khác tùy collection mode. KQL dưới đây chỉ minh họa:

```kusto
ContainerLogV2
| where TimeGenerated >= ago(1h)
| where PodName has "orders-api"
| where LogMessage has "gc"
| project TimeGenerated, PodName, ContainerName, LogMessage
| top 100 by TimeGenerated desc
```

**Đây là query phụ thuộc table/columns thực**. Không coi `LogMessage has "gc"` là parser pause duration chuẩn, vì unified logging format, tags và version khác nhau. Để tính p95 pause chuẩn, dùng **structured metrics/JFR hoặc parser đã kiểm thử**.

### 26.4. Resource/Pod correlation

Đối chiếu Java metrics/traces với Azure resources bằng **service name, environment, pod UID/name, container ID, deployment revision, image digest**, không chỉ `orders-api` string. Một Pod có thể bị thay tên khi restart; query cần timeline tương ứng.

## 27. Thiết kế load test để đánh giá GC tuning

Tuning JVM chỉ có ý nghĩa khi **so sánh trước/sau trên workload tương đương**, không chỉ chạy benchmark toy program.

### 27.1. Các biến phải cố định

- Cùng Java source/build/dependencies và **container image/JDK**.
- Cùng AKS node SKU, CPU/memory request/limit, cluster background load khi có thể.
- Cùng API endpoints, request mix, payload size/shape và authentication scenario.
- Cùng Azure SQL/Service Bus tiers/connection limits hoặc test doubles với mục đích rõ.
- Cùng concurrency/RPS/ramp-up/duration và warm-up protocol.
- Cùng sampling/metrics collection, dashboard time range, comparison method.
- Cùng database dataset size và cache state theo thiết kế test.

Nếu đồng thời nâng database tier, kết quả không đủ để quy cải thiện p99 cho collector.

### 27.2. Test phases

```text
Preflight
  validate JDK/container flags and resource limits
        |
Warm-up
  app startup, JIT, caches, connection pools
        |
Steady state
  realistic request mix at target load
        |
Ramp-up / peak
  gradually increase concurrency and throughput
        |
Soak test
  30-120 min or workload-defined duration for leaks/GC trends
        |
Failure/recovery
  restart a Pod, pause dependency, traffic burst, scale event
        |
Analysis
  compare user SLO, GC, RSS/native, CPU, OOM, cost
```

Thời lượng **soak test** phải tương ứng tốc độ leak/cycle workload; 30 phút không chắc phát hiện leak tăng 10 MiB/ngày. Tách metrics warm-up và steady state khi tính baseline.

### 27.3. Tải mở và tải đóng

**Closed-loop test** giữ số virtual users cố định và chờ response trước request tiếp; khi server chậm, tổng request rate có thể giảm và giấu overload. **Open-loop test** gửi requests theo arrival rate định trước, giúp thấy queueing/timeouts khi đến ngưỡng; nhưng cần load generator không bị nghẽn và kiểm soát backpressure. Dùng phù hợp SLO, không cố tạo traffic “đánh sập” subscription production.

### 27.4. Kết quả chuẩn

| Tín hiệu | Baseline G1 | Thử ZGC | Cách đọc |
|---|---:|---:|---|
| Good RPS | 390 | 405 | Gần target 400 |
| API p95 | 230 ms | 215 ms | Cải thiện nhẹ |
| API p99 | 720 ms | 440 ms | Cải thiện rõ |
| Max GC pause | 180 ms | 12 ms | Pause giảm, cần xác minh loại events |
| CPU cores used | 1,2 | 1,7 | CPU tăng đáng kể |
| cgroup memory peak | 1,65 GiB | 1,85 GiB | Headroom ít hơn |
| OOMKilled | 0 | 0 | Cần soak dài hơn |

**Số liệu hoàn toàn minh họa**, không phải benchmark Azure thực. ZGC cải thiện p99 nhưng tiêu thụ CPU/memory hơn; nếu mục tiêu chính là cost/throughput, G1 có thể vẫn hợp lý. Quyết định dựa **SLO, capacity và cost**, không chỉ một cột.

### 27.5. Quy tắc thống kê

- Đo nhiều lần, công bố **median/range/confidence** phù hợp; một run không đủ.
- Dùng đủ số samples để đo p99, không tính p99 từ 20 requests.
- Giữ fixed windows và units; tránh average-of-percentiles.
- Loại các runs bị tác động bởi deployment/database maintenance không tương đương.
- Ghi image digest, flags, memory/CPU limits, region/VM SKU và thời gian.

### 27.6. Regression gates

Một CI performance gate có thể fail nếu:

- p99 vượt target đáng kể dưới representative load.
- OOMKilled hoặc native memory leak xuất hiện.
- Good throughput giảm dưới acceptance threshold.
- CPU cost/good transaction tăng quá mức được phê duyệt.
- GC pauses tăng so baseline và tương quan user impact.

Đừng để noisy shared CI runner quyết định production release bằng một test performance 30 giây không có isolation.

## 28. Chỉ số memory leak và retention

### 28.1. “Sawtooth” heap bình thường

Heap used thường tăng trong lúc cấp phát rồi giảm sau GC, tạo dạng răng cưa:

```text
Heap used
 ^
 |      /\       /\       /\       /\
 |     /  \     /  \     /  \     /  \
 |____/    \___/    \___/    \___/    \___
 |
 +------------------------------------------> time
```

Sawtooth tự nó **không chứng minh leak**. Cần xem **post-GC live set** qua nhiều chu kỳ dưới tải ổn định. Nếu baseline sau collection leo dần mà không đạt steady state, nghi retained objects.

### 28.2. Leak có thể xuất hiện ngoài heap

```text
Heap post-GC live set: stable ~600 MiB
Direct/native memory: grows 200 -> 800 MiB
Container usage: grows 1.0 -> 1.8 GiB
Observed result: OOMKilled at 2 GiB limit
```

Đây là ví dụ; điều tra Netty buffers, JNI/mmap, threads, direct memory pools và NMT. GC tuning không giải quyết native allocator leak.

### 28.3. Không kết luận từ warm-up

Trong vài phút đầu, Spring/ORM/JIT/cache có thể tăng heap và committed memory khi khởi tạo. So retained baseline **sau warm-up** và cùng traffic phase; nếu thật sự leak, đường tăng tiếp tục qua nhiều chu kỳ, cùng cache cardinality/workload.

### 28.4. Leak detection thực hành

1. Xác nhận workload + deployment version ổn định.
2. Thu heap used/old-gen after GC, committed, RSS và direct memory metrics.
3. Xác nhận request rate, cache key cardinality và thread count.
4. Chạy soak test hoặc quan sát production canary có headroom.
5. Nếu heap leak, lấy class histogram/JFR, cân nhắc heap dump theo policy.
6. Tìm GC roots/retained objects bằng analyzer.
7. Nếu native leak, dùng NMT/allocator-specific diagnostics.
8. Sửa root cause, chạy regression soak, compare cost.

## 29. Tối ưu thread pools và connection pools

Nhiều “GC problems” thực ra là **quá nhiều concurrent work**.

### 29.1. HTTP thread pool

Trong servlet container, mỗi request có thể cần một worker thread. Nếu DB latency tăng và thread pool phình to, stack/native memory và request queue đều tăng; tăng heap không làm database nhanh hơn. Đặt **max threads và request queue/backpressure** theo đo tải.

### 29.2. HikariCP / JDBC connection pools

Một Java service có 50 database connections mỗi Pod, scale từ 5 lên 30 Pods, tạo lý thuyết **1.500 connections** – có thể vượt Azure SQL tier/network/identity limits. Giảm heap không giúp. Chọn pool size dựa **DB capacity, query duration, concurrency, retries và tổng fleet**.

### 29.3. Service Bus consumer concurrency

Tăng `maxConcurrentCalls` hoặc số worker có thể tăng throughput ban đầu, nhưng nếu handler tạo payloads lớn và không có backpressure, **heap live set và queue in-memory** tăng cùng lúc. Sử dụng bounded processing queues, idempotency, controlled prefetch/batch sizes và monitor processing lag/DLQ.

### 29.4. Reactive không tự bảo đảm dùng ít memory

Reactive I/O giảm số threads chờ blocking operations trong các use cases phù hợp nhưng có thể gây **buffer accumulation, direct-memory pressure và event-loop blocking** nếu code sai. Chuyển từ servlet sang reactive không phải “fix GC” tự động.

### 29.5. Virtual threads (JDK 21) và bộ nhớ

Java 21 có **virtual threads** (theo supported release) giúp biểu diễn nhiều concurrent blocking tasks hiệu quả hơn platform threads trong những tình huống phù hợp. Tuy nhiên virtual threads **không làm CPU/database throughput trở nên vô hạn**; mỗi task vẫn có heap/stack chunks và downstream capacity. Đặt concurrency limits, monitor pinning/locks/blocked operations theo JDK/tooling; không tạo hàng triệu tasks không có backpressure.

## 30. Khởi động và memory của Spring Boot trên Azure

### 30.1. Phân tách startup phases

Khi Pod mất 80 giây mới ready, xem:

- Pull image/container start.
- JVM initialization/class loading.
- Spring context and bean creation.
- Database migrations/connection validation.
- Key Vault/config retrieval.
- JIT warm-up và cache initialization.
- Readiness checks.

Phân tách bằng startup logs/traces/JFR; không mặc định “GC khiến Spring Boot khởi động chậm” khi GC logs không có pauses đáng kể.

### 30.2. Giảm dependency work ở startup

Một số startup tasks có thể lazy initialize hoặc background warm-up khi semantics cho phép. Nhưng nếu endpoint cần schema migration hoặc secret, readiness không được chuyển thành true trước khi dependency tối thiểu đạt yêu cầu. Cân bằng **fast startup** và **correct readiness**.

### 30.3. CDS/AppCDS và JVM class metadata

Class Data Sharing (CDS) và AppCDS có thể cải thiện startup/class-loading footprint trong các JDK/build/config phù hợp. Hiệu quả cần được benchmark; không coi CDS là cách chữa live-heap leak hoặc SQL latency.

### 30.4. Native image là lựa chọn kiến trúc khác

GraalVM Native Image có trade-offs riêng về startup/footprint, reflection/configuration và runtime memory management; **không dùng các HotSpot G1/ZGC flags y hệt native image**. Bài học tập trung vào **JVM HotSpot**, nên việc chuyển native image cần dự án benchmark/compatibility độc lập.

### 30.5. Cold start và Azure plans

Trên Azure Container Apps scale-to-zero hoặc App Service/Functions hosting modes có cold start, tối ưu thời gian khởi tạo có thể ảnh hưởng UX đáng kể. Nhưng nếu workload chạy 24/7 và đã warm, tối ưu startup 5 giây chưa chắc có giá trị bằng giảm p99 từ 1s xuống 400ms.

## 31. Bảo mật JVM diagnostics trên Azure

Khi tối ưu JVM, nhiều công cụ phân tích cho phép đọc dữ liệu nội bộ process. Đây không chỉ là vấn đề hiệu năng mà còn là **bảo mật dữ liệu và quyền vận hành**.

### 31.1. Những artifact cần phân loại

| Artifact | Có thể chứa | Kiểm soát |
|---|---|---|
| Heap dump `.hprof` | Plaintext credentials, secrets, tokens, customer PII, request payloads | Encryption, restricted access, retention |
| JFR `.jfr` | Stack/method/class names, I/O events, endpoints, metadata nội bộ | Scope/retention/redaction policy |
| Thread dump | Class names, stack traces, operation context | Masking, restricted access |
| GC logs | Uptime, memory sizes, process behavior | Tránh log flooding, lifecycle quản lý |
| Environment variables | App settings, có thể chứa secrets nếu thiết kế sai | Không dump all env values |
| JVM system properties | Endpoints, config, sometimes secrets | Tránh `-Dpassword=...`; giới hạn quyền |

### 31.2. Không bật remote JMX không bảo mật

JMX có thể expose runtime internals và management operations. Một JMX port công khai không có authentication/TLS là rủi ro cao. Trên AKS/VM, ưu tiên **local diagnostics/secured exporter**, truy cập qua network segment và identity được phê duyệt, không mở JMX trên public load balancer.

### 31.3. Diagnostic permissions trong Kubernetes

Để chạy `jcmd`/JFR, có thể cần exec vào Pod, debug container, attach capability và JDK tools. Dùng **Kubernetes RBAC/Entra integration, audit, just-in-time privileges**, không thêm `privileged: true` hoặc chạy mọi container as root chỉ để chẩn đoán. Debug session nên giới hạn thời gian và tài nguyên.

### 31.4. Heap dump theo incident policy

Một phương án:

1. Security/incident owner chấp thuận snapshot.
2. Ghi Pod/image version, thời gian, size dự kiến.
3. Chọn one canary replica, disk/volume có headroom.
4. Thu dump vào storage đã mã hóa, private access.
5. Chỉ những người có nhiệm vụ được đọc.
6. Redact findings trong issue/report; không đính kèm raw dump công khai.
7. Xóa artifact theo retention policy, audit access.

### 31.5. Java flags có thể lộ qua process metadata

Tránh đưa password/JWT vào command line `-Dsecret=...` hoặc `JAVA_TOOL_OPTIONS`. Dùng **managed identity, Azure Key Vault references hoặc secure runtime injection** theo Azure service phù hợp, và xác định chính xác ai được đọc process environment/config.

## 32. Tối ưu chi phí JVM và Azure capacity

Tối ưu JVM không chỉ để giảm `heap used`; mục tiêu kinh tế là đạt **good throughput và độ ổn định** với chi phí chấp nhận được.

### 32.1. Những khoản chi liên quan

| Thành phần | Chi phí tác động | Hành động |
|---|---|---|
| AKS nodes/VMs | vCPU/RAM và node-hours | Chọn instance/node size, requests/limits |
| App Service Plan | Tier/instance count | Sizing, caching, warm-up, scale-out |
| Container Apps | CPU/memory usage, replicas/workload profile | Giảm cold starts/overprovision |
| Azure SQL/Service Bus | Tier, throughput, connection pressure | Tối ưu pool/backpressure |
| Log Analytics/managed metrics | Ingestion/retention/query | Sampling, labels, data lifecycle |
| Diagnostics artifacts | JFR/dump/log storage và egress | Rotate, encrypt, retention |
| Resilience | Extra replicas/headroom | Đối chiếu SLO và RTO |

### 32.2. Một phép so sánh chi phí

Giả sử:

```text
Configuration A
  8 Pods x 2 GiB limit
  400 good RPS
  measured monthly node and observability cost: C_A

Configuration B
  6 Pods x 3 GiB limit
  430 good RPS
  measured monthly cost: C_B

Compare:
  cost per million successful requests
  p95/p99
  OOM/restart rate
  operational headroom
```

Chỉ giảm số Pods không chắc giảm bill nếu node SKU vẫn giữ nguyên hoặc VPA/HPA làm tăng reserved capacity. So **actual Azure Cost Management** với cùng thời kỳ/baseline; giá VM/AKS/App Service/Container Apps và tính phí logs thay đổi theo region/tier, không nên đưa “đơn giá chuẩn” cố định.

### 32.3. Đánh đổi heap vs density

Heap lớn hơn giúp một số workloads giảm GC pressure nhưng tăng memory requests và có thể khiến scheduler cần thêm node. Heap nhỏ hơn tăng pod density nhưng có thể làm GC CPU cao hoặc OOM, gây cost vì retries/incident. Chọn **điểm hiệu năng–chi phí** qua thử nghiệm.

### 32.4. Observability overhead

GC logging `debug/trace` liên tục, JFR profile không có hạn mức, exporter có labels high cardinality và heap dump tự động mọi OOME có thể tăng storage/IO/ingestion. Giữ **những tín hiệu hỗ trợ quyết định**, giới hạn data volume và đúng retention. Không tắt logs bắt buộc cho security/compliance chỉ để giảm phí.

### 32.5. Tuning thay đổi số resource

Một collector cần nhiều CPU hơn có thể đẩy AKS lên node size lớn hơn; một Xms thấp hơn có thể giúp tăng replicas nhưng tăng startup GC. Việc so sánh cần dùng **tổng fleet cost + SLO + recovery**, không chỉ CPU% của một Pod.

## 33. Quy trình tuning JVM có khả năng kiểm toán

Tạo một **tuning record** cho mỗi thay đổi, lưu cùng incident/performance review (trong hệ thống được phê duyệt):

```yaml
# Minh họa một bản ghi phân tích; không phải cấu hình Azure.
experimentId: jvm-orders-20261120-01
service: orders-api
environment: staging
region: southeastasia
jdk: "OpenJDK 21 build recorded by CI"
container:
  memoryLimit: "2Gi"
  cpuLimit: "2"
baseline:
  gc: G1
  maxHeap: "60% of detected container memory"
candidate:
  gc: ZGC
  flags: ["-XX:+UseZGC"]
load:
  requestMix: "recorded synthetic profile v3"
  duration: "after warmup + steady + soak"
metrics:
  - goodRps
  - httpP99Ms
  - gcPauseP99Ms
  - memoryPeakMiB
  - cpuThrottledRate
  - oomKills
decision: "pending measurement"
reviewer: "orders-platform"
```

### 33.1. Thực hiện theo vòng khép kín

1. **Mục tiêu:** ví dụ giảm HTTP p99 từ 850 xuống 500 ms, không tăng cost hơn giới hạn định trước.
2. **Baseline:** đo JVM/JDK flags thực, memory/CPU constraints, request mix và resource metrics.
3. **Hypothesis:** GC STW pauses chiếm phần đáng kể p99, không phải SQL latency.
4. **Candidate:** đổi đúng một nhóm flags (ví dụ G1 → ZGC), giữ các yếu tố khác.
5. **Validate:** startup/JDK compatibility và runtime logs confirm collector.
6. **Benchmark:** warm-up, steady, peak, soak, failure.
7. **Analyze:** compare SLO/GC/native memory/CPU throttling/cost.
8. **Canary:** rollout nhỏ có rollback; theo dõi user impact.
9. **Decide:** keep/revert, ghi nguyên nhân và risk.
10. **Update runbook:** phản ánh settings, dashboard, triggers và version.

### 33.2. Kết quả thất bại vẫn hữu ích

Nếu đổi collector mà p99 không cải thiện nhưng CPU tăng 25%, **revert** và ghi nhận rằng GC không là bottleneck chính. Đó là kết quả thí nghiệm tốt vì loại bỏ giả thuyết; không cố sửa metric để chứng minh lựa chọn ban đầu.

### 33.3. Một thay đổi JVM có thể cần thay deployment

Thay `JAVA_TOOL_OPTIONS` có thể cần **restart/revision rollout**; không coi flag environment được tự áp vào process đang chạy. Kiểm tra zero-downtime strategy, health probes, PodDisruptionBudget/replicas và deployment window.

## 34. Runbook 1: AKS Pod bị `OOMKilled` nhưng heap không đầy

**Triệu chứng:** Java API container 2Gi memory limit, Pod restart và `Reason: OOMKilled`. Heap metrics trước đó chỉ ~900 MiB.

### 34.1. Triage và kiểm tra chứng cứ

1. Xác nhận **Pod/container name, namespace, image digest, last termination reason và timestamp**.
2. Xem `kubectl describe pod` events/`lastState.terminated.reason`, memory limits và restart count.
3. Xem container **memory working set/cgroup usage** trước OOM, không chỉ heap.
4. Xem process RSS, heap used/committed/max, metaspace, direct memory và thread count.
5. Xác định container còn sidecars/other processes không.
6. Nếu đã bật NMT, xem category growth và so baseline.
7. Kiểm tra spike do batch payload, direct buffers, logging, large classloader hoặc thread explosion.
8. Kiểm tra node pressure/eviction riêng; `Evicted` vì node pressure khác với container OOMKilled.
9. Chọn mitigation: bounded caches, thread pool, buffer release, giảm Xmx/tăng limit có cân đối.
10. Test dưới load/soak, chạy canary rồi theo dõi OOM restarts.

### 34.2. Lệnh Kubernetes tham khảo

```bash
kubectl -n orders get pods -l app=orders-api -o wide
kubectl -n orders describe pod <pod-name>

kubectl -n orders get pod <pod-name> \
  -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'

# Requires Kubernetes metrics API/metrics-server.
kubectl -n orders top pod <pod-name> --containers
```

`<pod-name>` là placeholder. `kubectl top` chỉ hiển thị số liệu hiện tại nếu metrics collection hỗ trợ, **không lưu lịch sử trước lần crash**. Cần centralized monitoring để xem peak leading indicators.

### 34.3. Cách xử lý dễ sai

- Tăng `-Xmx` từ 1.2 lên 1.8 GiB trong limit 2Gi mà không đo native headroom.
- Xem exit code 137 là chứng cứ duy nhất cho OOM.
- Mong `HeapDumpOnOutOfMemoryError` luôn chạy khi Linux kernel SIGKILL.
- Giảm memory request nhưng không thay limit để “tiết kiệm”, rồi node bin-packing/eviction xấu hơn.
- Xóa dump/log ngay trước khi có forensic approval và root cause.

### 34.4. Tiêu chí phục hồi

Không có OOMKilled qua representative peak/soak test, memory high-watermark thấp hơn budget với headroom phù hợp, GC/application p99 đạt SLO và cost không tăng ngoài chính sách.

## 35. Runbook 2: `OutOfMemoryError: Java heap space`

**Triệu chứng:** logs ghi `java.lang.OutOfMemoryError: Java heap space`; heap committed/max gần Xmx, GC liên tục nhưng không thu hồi đủ.

### 35.1. Điều tra theo thứ tự

1. Xác định Xmx thực tế và JDK/container detection từ process flags.
2. Xem heap after-GC live set, old-generation occupancy và allocation rate.
3. Kiểm tra payload sizes, cache cardinality, queues và retained session data.
4. Nếu được phê duyệt, lấy JFR/class histogram/heap dump của **một** instance.
5. Phân tích dominant classes, GC roots và retained references; phân biệt cache warm-up vs leak.
6. Kiểm tra memory cap đủ cho workload thực hay quá thấp.
7. Sửa bounded data structures hoặc tăng heap/container memory có cơ sở.
8. Chạy regression/soak, compare GC/latency/cost.

### 35.2. Ví dụ heap retention

```java
// Anti-pattern minh họa (không phải code sản xuất).
final Map<String, byte[]> payloadCache = new ConcurrentHashMap<>();
void handle(String orderId, byte[] payload) {
    payloadCache.put(orderId, payload); // Không có eviction.
}
```

Nếu mỗi payload 100 KiB và 100.000 keys được giữ lâu dài, riêng dữ liệu có thể xấp xỉ **9,8 GiB**, chưa tính object/map overhead. Tăng Xmx từ 2Gi lên 4Gi chỉ trì hoãn OOME. Sửa thành cache có size/weight/TTL hoặc lưu Blob/DB theo business requirement.

### 35.3. Khi nào tăng Xmx hợp lý?

Nếu heap live set ổn định, không có leak, workload cần nhiều memory hơn dự kiến và container có **sufficient native headroom**, tăng Xmx (cùng container limit/node sizing nếu cần) có thể giảm GC frequency và OOME. Luôn test throughput/latency/committed memory và cost; không tăng đến sát cgroup ceiling.

### 35.4. Recovery evidence

Heap after-GC không tăng vô hạn dưới same load, no OOME, API/worker SLO đạt và traffic peak có margin; fix được giao owner và regression suite.

## 36. Runbook 3: p99 tăng mạnh cùng GC pauses

**Triệu chứng:** HTTP p99 tăng 400 → 1.600 ms, GC logs có nhiều pauses 200–500 ms.

### 36.1. Khoanh vùng nguyên nhân

1. Xác minh p99 từ application/request metrics có đủ mẫu, không phải percentile tính từ sample quá ít.
2. So GC pause timestamps với request latency/traces.
3. Xem GC type: young/mixed/full, frequency, heap before/after, promotion pressure.
4. Xem CPU throttling/CPU quota và node resource pressure.
5. Xem request mix/payload sizes/allocations, burst traffic/deployment.
6. Xem dependency latency để loại SQL/Service Bus là nguyên nhân chính.
7. Xem heap live set/cap, native headroom.
8. Thử điều chỉnh allocation/heap hoặc collector trên staging, không thay nhiều flags cùng lúc.
9. Canary version cải thiện p99, giới hạn CPU/memory cost.
10. Cập nhật alert thresholds và runbook.

### 36.2. Tối ưu đúng thứ tự

**Bắt đầu từ nguyên nhân**, thường theo thứ tự:

- Giảm allocation lớn hoặc không cần thiết.
- Sửa cache/retention và unbounded queues.
- Đảm bảo CPU quota không throttling nghiêm trọng.
- Đặt heap và native memory headroom phù hợp.
- Chỉ sau đó thử collector/GC tuning.

Nếu GC pauses rất ngắn nhưng HTTP p99 dài, đổi GC không phải bước ưu tiên. Nếu GC chiếm phần lớn p99, mới benchmark ZGC/G1.

### 36.3. Đừng giảm `MaxGCPauseMillis` vô hạn

G1 có pause target mềm, không phải SLA. Đặt target quá thấp có thể tăng GC work/CPU; p99 overall có thể không cải thiện. Dùng test data để chọn threshold và flag, không lấy số từ “tuning cheat sheet”.

## 37. Runbook 4: CPU throttling khiến GC/JIT và API chậm

**Triệu chứng:** latency tăng khi traffic burst; CPU usage trung bình không quá cao, nhưng throttled periods/time tăng.

### 37.1. Các bước

1. Kiểm tra Pod CPU request/limit thực qua manifest và runtime.
2. Đo CPU throttled periods/time per Pod/node với metric nguồn phù hợp.
3. Xem JVM `availableProcessors()`/`ActiveProcessorCount` và GC worker behavior.
4. Xem JFR CPU hotspots và thread contention.
5. Xem số request workers và DB/Service Bus concurrency.
6. Thử tăng quota, bỏ quota theo policy hoặc scale replicas (một biến mỗi lần).
7. Quan sát good RPS, p95/p99, GC CPU và cost.
8. Kiểm tra node sizing/quotas, AKS HPA response.
9. Giữ cấu hình tốt và thiết lập alert khi throttling có user impact.

### 37.2. Đừng diễn giải sai CPU cores

`requests.cpu=500m` không có nghĩa JVM chỉ được dùng 0.5 CPU mọi lúc, và `limits.cpu=2` không có nghĩa có đúng hai physical cores dedicated. Đó là reservation/quota semantics của Kubernetes. **CPU throttling cùng request p99** quan trọng hơn một giá trị CPU percentage riêng lẻ.

## 38. Runbook 5: RSS tăng, NMT/direct memory không ổn

**Triệu chứng:** container memory tăng trong 2 giờ từ 1.0 lên 1.9 GiB, heap/old-gen sau GC ổn định ~700 MiB.

### 38.1. Chẩn đoán

1. So heap committed/used với process RSS và cgroup usage.
2. Xem NMT summary/diff nếu đã bật.
3. Xem thread count, `jvm_threads_live_threads` và thread dump.
4. Xem direct buffers/pooling, Netty/TLS/mmap/native JNI libraries.
5. Xem OS page cache/file IO/container sidecars/GC logs.
6. Kiểm tra memory growth theo payload/concurrency/deploy version.
7. Bật profiler native-specific trên staging nếu NMT không ghi nhận allocations.
8. Sửa resource lifecycle/close operations hoặc chọn bounded direct memory settings.
9. So RSS high-watermark và performance; không chỉ chỉnh Xmx.

### 38.2. NMT không thể chứng minh 100% native memory

Một native library tự malloc ngoài HotSpot accounting có thể không được NMT phản ánh đầy đủ. Khi NMT categories không giải thích RSS, điều tra process maps/allocators/cgroup file cache và sidecars. **Không kết luận leak không tồn tại chỉ vì NMT report ổn định.**

## 39. Runbook 6: Startup chậm hoặc restart loop sau rollout

**Triệu chứng:** rollout AKS/App Service/Container Apps phiên bản mới làm readiness trễ, Pod liên tục restart và latency tăng.

### 39.1. Triage

1. Kiểm tra image digest/JDK version/flags có thay không.
2. Kiểm tra startup/readiness/liveness thresholds và actual startup duration.
3. Xem memory request/limit, Xms/Xmx, CPU limit và startup throttling.
4. Xem GC logs, classloading/JIT/JFR startup khi được phép.
5. Xem DB migrations, Key Vault/Entra token, DNS/private endpoint và app config errors.
6. Kiểm tra HPA/scale-out/revision/slot behavior và có bao nhiêu instances cùng khởi động.
7. Không vội tắt probes hoàn toàn; điều chỉnh startup window đúng.
8. Nếu release gây mất dịch vụ, rollback/forward-fix theo change plan.
9. So warm-start/cold-start SLI và cost, thêm test khởi động.

### 39.2. Khi probe đánh nhầm STW pause

Liveness threshold quá chặt có thể kill Pod qua SIGTERM/SIGKILL trong lúc JVM đang tạm dừng. Phân biệt:

- **JVM OOME**: Java-level allocation failure.
- **OOMKilled**: cgroup/kernel kill.
- **Liveness kill**: kubelet quyết định restart vì probe failure.
- **Normal rollout termination**: Pod bị thay phiên bản.

Bốn trường hợp có triệu chứng “Pod restart” nhưng runbook và fix khác nhau.

## 40. Case study: giảm p99 và OOMKilled cho Orders API trên AKS

### 40.1. Bối cảnh

Nhóm Orders Platform chạy **Spring Boot 3.x trên HotSpot JDK 21** với 6 replicas AKS, mỗi container có memory limit 2 GiB và CPU limit 1 core. Java app sử dụng Azure SQL qua HikariCP và Azure Service Bus SDK. Trong traffic peak:

```text
Traffic                  420 requests/second
HTTP p95                 310 ms
HTTP p99                 1,400 ms
Java heap max            ~1.54 GiB (example of 75% setting)
Heap used at snapshot    900 MiB
Container working set    up to ~1.95 GiB
GC pause p99             75 ms
CPU throttling           elevated during bursts
Restart reason           OOMKilled on two Pods
```

**Tất cả số liệu là giả định**, nhằm minh họa cách lý giải chứ không phải benchmark thực tế trên Azure.

### 40.2. Phân tích ban đầu

Ba dấu hiệu quan trọng:

1. **Heap used 900 MiB không lý giải 1.95 GiB container usage** → cần xem heap committed/native/sidecars.
2. **GC pause p99 75 ms không giải thích toàn bộ HTTP p99 1.4s** → cần xem SQL/CPU throttling/thread queues.
3. **CPU limit 1 core với peak 420 RPS** → có thể tạo bottleneck, nhưng cần so throttled metrics và request traces.

### 40.3. Thu dữ liệu

Đội ứng dụng:

- Kiểm tra `kubectl describe pod` và Pod OOM event timestamps.
- Xem `-Xmx`/`MaxRAMPercentage` và HotSpot container detection.
- Xem GC logs: young/mixed/full, max pause và heap after GC.
- Thu NMT/JFR trên **staging replica**, kiểm soát overhead.
- Phân tích JVM threads/Hikari pool/Netty buffer metrics.
- Xem App Insights SQL dependency p95 và Service Bus operations.
- Đối chiếu cgroup memory/CPU throttling với p99.

### 40.4. Tìm căn nguyên

Giả sử evidence cho thấy:

```text
Heap live set                stable ~650-850 MiB
Hikari connection pool       50 per Pod, many blocked threads
Direct buffers              rising with excess prefetch
Container memory peak       near limit
CPU throttling               high at load bursts
GC pauses                   moderate, not dominant
Azure SQL dependency p95    900 ms during peak
```

**Root cause hypothesis**: service concurrency vượt khả năng database; blocked requests giữ objects/threads/buffers lâu hơn, native memory tăng, một số containers OOM. GC đang phải xử lý áp lực nhưng **không phải nguyên nhân duy nhất**.

### 40.5. Can thiệp đúng thứ tự

**Thay đổi A – Giới hạn xử lý đồng thời:**

- Chọn Hikari pool/concurrency tổng theo Azure SQL capacity.
- Giới hạn Service Bus prefetch/handler concurrency.
- Thiết lập bounded queues và request/backpressure policy.
- Benchmark again; xem good RPS, SQL p95, thread count, memory.

**Thay đổi B – Điều chỉnh heap/headroom:**

- Thử giảm max heap tỷ lệ 75% → khoảng 60% của 2 GiB sau khi xác minh live set.
- Đo native headroom và GC behavior; nếu heap trở nên thiếu và full GC tăng, không giữ thay đổi.
- Nếu native memory thực vẫn cần nhiều, chọn tăng container limit/instance size có đánh giá cost.

**Thay đổi C – CPU quota/replicas:**

- Benchmark tăng CPU limit hoặc thay HPA settings theo quota/node capacity.
- Theo dõi throttling, API p99, GC CPU và cost/transaction.
- Không bật scale-out vô hạn nếu SQL vẫn nghẽn.

**Thay đổi D – Collector:**

- Giữ G1 nếu GC pause không chi phối p99.
- Chỉ benchmark ZGC khi p99 còn chịu GC impact rõ sau các sửa trên.

### 40.6. Kết quả benchmark minh họa

| Metric | Baseline | Sau thay đổi A–C | Mục tiêu |
|---|---:|---:|---:|
| Good RPS | 385 | 425 | >= 400 |
| HTTP p95 | 310 ms | 205 ms | <= 250 ms |
| HTTP p99 | 1.400 ms | 530 ms | <= 800 ms |
| GC pause p99 | 75 ms | 60 ms | Phù hợp tail SLO |
| Container peak memory | 1,95 GiB | 1,55 GiB | Có headroom |
| OOMKilled/soak test | 2 | 0 | 0 |
| SQL p95 | 900 ms | 290 ms | Cải thiện |

Đây **không phải kết quả thực nghiệm đã được đo**. Nó minh họa một bài học: tối ưu đúng có thể làm p99 tốt lên mà không cần đổi collector, nhờ giảm concurrency pressure, native memory và CPU throttling.

### 40.7. Triển khai production

1. Chạy staging load test với memory/CPU và Azure SQL tier gần production.
2. Soak đủ lâu để native memory leak/queue pressure bộc lộ.
3. Canary một phần traffic/replicas, giữ rollback config/image digest.
4. Quan sát App Insights SLO, GC logs, working set, CPU throttling, SQL p95 và Service Bus DLQ.
5. Nếu p99 hoặc OOM tăng, rollback/forward-fix theo runbook; không tự tăng Xmx để che.
6. Sau rollout, cập nhật resource requests/limits và chi phí theo số good transactions.
7. Viết incident/postmortem, thêm regression performance test và dashboard alert.

### 40.8. Bài học có thể tái sử dụng

**Heap, GC, CPU, native memory và downstream concurrency phải được tối ưu như một hệ thống**. Một metric riêng hiếm khi đủ kết luận. Với Azure, node/plan SKU, network latency, connection limits, autoscaling và chi phí có vai trò ngang các flags JVM.

## 41. Bài tập thực hành

### Bài tập A — Phân loại bộ nhớ của Java process

**Đề bài:** một JVM Pod có Xmx 1,2 GiB, heap used 850 MiB, metaspace 130 MiB, direct buffers 300 MiB, 400 OS threads và container memory ~1,8 GiB.

**Nhiệm vụ:** nêu ít nhất năm memory contributors ngoài heap và giải thích vì sao heap used không bằng cgroup usage.

**Tiêu chí đạt:** phân biệt heap used/committed, metaspace, thread stacks, direct, code cache, native libs, OS/file cache; không cộng các metrics chồng lặp.

### Bài tập B — Sizing container 2 GiB

**Đề bài:** Pod limit 2Gi và nhóm thử `MaxRAMPercentage=60`.

**Nhiệm vụ:** ước lượng max heap, phần còn lại cho native memory, các điều kiện cần kiểm tra trong JDK/cgroup.

**Hướng giải:** ~1229 MiB heap và ~819 MiB remainder trước các điều chỉnh thực tế; verify JVM max heap flags và container detection.

### Bài tập C — Phân biệt requests và limits

**Đề bài:** `request.memory=1Gi`, `limit.memory=2Gi`; memory working set 1.7 GiB.

**Nhiệm vụ:** trả lời liệu Pod đã vượt hard limit chưa, scheduling/capacity có vấn đề gì, JVM theo limit nào.

**Hướng giải:** chưa vượt 2Gi limit nhưng đã vượt request; node placement/eviction/QoS có thể quan trọng, JVM sizing cần verify cgroup limit.

### Bài tập D — G1 hay ZGC?

**Đề bài:** G1 p99 GC pause 60 ms, API p99 1.2s, SQL dependency p95 900ms.

**Nhiệm vụ:** đề xuất bước điều tra trước khi chuyển sang ZGC.

**Hướng giải:** GC pause chưa giải thích toàn bộ latency; kiểm tra SQL/connection pool/cpu throttling, dùng JFR/traces rồi mới benchmark collector.

### Bài tập E — GC logs HotSpot Java 21

**Đề bài:** thiết lập GC logs cho ứng dụng Java 21, thu về stdout hoặc file rotation.

**Nhiệm vụ:** nêu cách ghép log timestamp với request p99, giới hạn log volume và so young/mixed/full pauses.

**Hướng giải:** `-Xlog:gc*` với tags/time/uptime, có collection labels/retention; parse format theo version.

### Bài tập F — Phân biệt Java OOME và OOMKilled

**Đề bài:** một Pod exit 137, không có `OutOfMemoryError` logs nhưng `kubectl describe` báo `Reason: OOMKilled`.

**Nhiệm vụ:** giải thích vì sao heap dump có thể không được tạo, cách tìm cause.

**Hướng giải:** kernel SIGKILL theo cgroup; xem historical memory, native/sidecar usage, requests/limits; `HeapDumpOnOutOfMemoryError` không bảo đảm chạy.

### Bài tập G — Bật NMT

**Đề bài:** heap sau GC ổn định, RSS tăng 500 MiB trong 45 phút.

**Nhiệm vụ:** nêu cách bật NMT summary, baseline/diff và điều gì NMT không thể nhìn thấy.

**Hướng giải:** bật khi startup, dùng `jcmd VM.native_memory baseline/summary.diff`, đối chiếu process RSS/cgroup và native libraries ngoài HotSpot accounting.

### Bài tập H — Thread explosion

**Đề bài:** service tăng từ 100 lên 2.000 OS threads sau release; native memory + p99 tăng.

**Nhiệm vụ:** kiểm tra thread pool, `jcmd Thread.print`, stack memory và cách giới hạn concurrency.

**Hướng giải:** tìm pool leak/unbounded thread creation, ưu tiên bounded pools/backpressure; không chỉ giảm `-Xss`.

### Bài tập I — Direct buffers

**Đề bài:** Netty service có heap 700 MiB ổn định nhưng container liên tục OOM.

**Nhiệm vụ:** phân biệt `MaxDirectMemorySize` với native memory toàn bộ và cách kiểm tra resource release.

**Hướng giải:** monitor direct buffer pool and native allocators, NMT/Netty metrics, ref-counted buffers đúng, test load.

### Bài tập J — CPU throttling

**Đề bài:** AKS Pod có CPU limit 500m, request 100m; latency cao khi burst nhưng CPU usage trung bình 300m.

**Nhiệm vụ:** giải thích CPU CFS throttling, cách xem throttled periods và benchmark quota/replicas.

**Hướng giải:** bursts có thể vượt quota dù average thấp; compare request latency/GC CPU/throttled time, scale theo node/SQL capacity.

### Bài tập K — Probe và GC pause

**Đề bài:** mỗi GC pause 700 ms khiến liveness endpoint timeout, Pod restart liên tục.

**Nhiệm vụ:** điều chỉnh startup/readiness/liveness và phân biệt một pause tạm với deadlock.

**Hướng giải:** startup probe/timeouts phù hợp, readiness cho traffic routing, liveness chỉ cho unrecoverable state; test under load, không disable mọi probe.

### Bài tập L — Load test before/after

**Đề bài:** thử `G1` và `ZGC` trên Java 21, cùng heap cap 60%, Pod 2Gi, CPU 2 cores.

**Nhiệm vụ:** thiết kế test phases, fixed load, sampling, SLO và cost measurements; lưu JDK build/flags.

**Hướng giải:** warm-up, steady, peak, soak, failure, nhiều runs; compare good RPS, HTTP p99, GC pause, RSS/CPU throttling và cost.

### Bài tập M — Đánh giá leak

**Đề bài:** heap sawtooth 400→900→450 MiB lặp đều trong 10 phút; khác test heap sau GC 450→550→700 MiB qua 1 giờ.

**Nhiệm vụ:** phân biệt pattern bình thường với suspicious retention, điều gì cần thêm trước khi kết luận.

**Hướng giải:** test sau warmup cùng workload, old-gen live set trend, cache keys, allocation/retained heap, dài hơn khi cần.

### Bài tập N — JFR trên staging

**Đề bài:** profiling startup Spring Boot 100 giây.

**Nhiệm vụ:** dùng JFR duration/settings, tìm classloading/JIT/dependencies, lưu recording an toàn.

**Hướng giải:** `-XX:StartFlightRecording` hoặc `jcmd JFR.start` với filename/duration và access control; không public heap/JFR artifacts.

### Bài tập O — HPA và heap commitment

**Đề bài:** HPA scale 5→25 Pods, mỗi Pod Xms=Xmx=1.5 GiB; API latency giảm nhưng node cost tăng mạnh.

**Nhiệm vụ:** đánh giá Xms/replica, CPU/memory requests, connection pool tổng và cost per transaction.

**Hướng giải:** scale-out tăng fleet footprint; benchmark Xms thấp hơn và pool limits, vẫn giữ SLO/headroom.

### Bài tập P — Azure App Service

**Đề bài:** hai Java apps chia sẻ App Service Plan; app A tăng native RSS sau release, app B chậm.

**Nhiệm vụ:** điều tra shared plan capacity, per-app resource usage và cân nhắc tách plan/scale vs sửa leak.

**Hướng giải:** không chỉ tăng Xmx app B; xem plan contention, process RSS, heap/native metrics và deployment history.

### Bài tập Q — Container Apps cold start

**Đề bài:** Container Apps scale-to-zero, Java process khởi động 40 giây; cần phản hồi nhanh hơn.

**Nhiệm vụ:** xác định tác nhân startup/JIT/context/Key Vault và đánh đổi min replicas/cost.

**Hướng giải:** benchmark warm/cold, xem startup phases, min replicas hoặc image/runtime optimizations, không mặc định ZGC chữa cold start.

### Bài tập R — Spring Boot + Azure SQL

**Đề bài:** tăng App Service replicas từ 4 lên 16; mỗi instance Hikari pool 40 connections, SQL báo quá tải.

**Nhiệm vụ:** tính max potential connections, chọn pool/concurrency/scale policy và dự báo memory.

**Hướng giải:** tối đa lý thuyết 640 connections nếu mọi pools đầy; giảm per-instance pool hoặc nâng SQL capacity khi có chứng cứ, kiểm tra timeouts/latency.

### Bài tập S — Security của heap dump

**Đề bài:** một engineer muốn upload `.hprof` production lên public issue tracker để hỏi hỗ trợ.

**Nhiệm vụ:** đánh giá secrets/PII risk và quy trình forensic an toàn.

**Hướng giải:** không upload public; encrypted private storage, access approvals/retention/redacted findings, sanitize artifacts.

### Bài tập T — Incident review

**Đề bài:** production có `OOMKilled`, GC logs bình thường, CPU throttling cao và Azure SQL p99 tăng.

**Nhiệm vụ:** viết incident timeline, hypotheses, remediation/rollback, monitoring improvements và ownership.

**Hướng giải:** tách JVM/non-heap/container/dependency symptoms; đo lại representative load và cập nhật alerts; không kết luận collector là nguyên nhân chỉ vì process Java bị kill.

## 42. Câu hỏi tự kiểm tra

**1. Vì sao không bắt đầu tối ưu bằng `-Xmx`?** Vì p99/throughput có thể bị SQL, Service Bus, CPU throttling hoặc native memory chi phối; cần SLO và baseline.

**2. Java heap used và committed khác nhau?** Used là phần heap đang chứa object data theo metric, committed là memory JVM cam kết cho heap; committed có thể lớn hơn used.

**3. `-Xmx` có chặn container RSS?** Không. Nó chặn phần heap theo JVM semantics; metaspace, direct buffers, stacks và native memory nằm ngoài.

**4. Metaspace là gì?** Khu vực native memory chứa metadata của classes/classloaders theo HotSpot.

**5. Vì sao thread explosion gây memory pressure?** Mỗi OS thread có stack và native overhead, cùng CPU scheduling/context switching.

**6. Direct memory thường đến từ đâu?** NIO direct buffers, Netty/networking, TLS và một số native/client libraries.

**7. `MaxDirectMemorySize` có giới hạn mọi native allocation không?** Không; nó tác động đến direct-buffer allocations thuộc phạm vi HotSpot/JVM hỗ trợ.

**8. `OutOfMemoryError: Java heap space` khác `OOMKilled`?** OOME là JVM-level allocation failure; OOMKilled là kernel/container cgroup kill, có thể không có Java exception.

**9. Exit code 137 có đủ chứng minh OOMKilled?** Không; cần kiểm tra termination reason/events và context, vì SIGKILL có nhiều nguyên nhân.

**10. `requests.memory` có là trần runtime không?** Không; `limits.memory` mới là cgroup limit khi được cấu hình và thực thi.

**11. `requests.cpu=500m` có nghĩa JVM dùng tối đa nửa core?** Không; đó là scheduling reservation, còn quota phụ thuộc `limits.cpu`/runtime.

**12. Container-aware JVM nghĩa là gì?** JVM xét cgroup CPU/memory constraints cho ergonomics khi JDK/version/build hỗ trợ.

**13. JDK 8 và JDK 21 có cgroup detection giống nhau mặc định không?** Không chắc; phụ thuộc bản backport/build/cgroups v1-v2.

**14. `MaxRAMPercentage=60` trong Pod limit 2Gi nghĩa gì?** Với JVM nhận đúng limit và không có override khác, max heap mục tiêu khoảng 60% = 1.2 GiB.

**15. `MinRAMPercentage` có phải Xms percent?** Không; không dùng nó như “minimum heap” phổ quát trên HotSpot.

**16. Có nên đặt `Xms=Xmx` luôn?** Không; trade-off heap commitment/startup/scale density cần đo.

**17. G1 là collector loại gì?** Region-based, generational collector tối ưu cân bằng throughput/pause với heuristics/ergonomics.

**18. `MaxGCPauseMillis=200` bảo đảm không pause quá 200ms?** Không; là mục tiêu mềm của collector.

**19. ZGC phù hợp nhất khi nào?** Khi GC pause là nguyên nhân đáng kể của tail latency và có đủ CPU/memory headroom, đã benchmark.

**20. ZGC có zero stop-the-world pauses?** Không. Concurrent GC vẫn có synchronization/STW phases ngắn.

**21. `-XX:+ZGenerational` dùng y hệt trên mọi JDK?** Không; mode và flag support thay đổi theo JDK.

**22. Parallel GC có phù hợp batch?** Có thể khi throughput quan trọng hơn pause tail, nhưng phải đo.

**23. Tăng young generation cố định có luôn tốt cho G1?** Không; có thể phá adaptive pause sizing.

**24. Vì sao full GC thường cần quan sát kỹ?** Có thể kéo dài, làm ứng dụng ngừng xử lý request và gây p99 spikes.

**25. GC frequency cao luôn xấu?** Không; nhiều young GCs ngắn có thể vẫn tốt hơn ít pauses dài.

**26. GC pause p99 là HTTP request p99?** Không; là hai phân phối khác nhau cần tương quan nhưng không đồng nhất.

**27. `-Xlog:gc*` dùng trên Java 8 mặc định?** Không; unified logging thuộc JDK 9+ và Java 8 có flags khác tùy build.

**28. Vì sao GC logs phải có Pod/instance labels?** Vì process/restart có GC IDs/uptime riêng; không ghép lẫn thành một chuỗi.

**29. JFR dùng cho gì?** Thu profiling events về allocation, GC, locks/threads, CPU và các event runtime được hỗ trợ.

**30. Heap dump có thể chứa bí mật không?** Có: tokens, passwords, PII và payloads có thể nằm trong objects.

**31. `jcmd GC.class_histogram` có xác định đầy đủ GC roots?** Không; histogram là counts/bytes theo classes, cần retained reference analysis để tìm giữ objects.

**32. NMT có thể dùng ngay nếu chưa bật lúc khởi động không?** Thường cần bật tracking khi startup để có dữ liệu; không giả định có thể bật đầy đủ không restart.

**33. NMT summary có bằng RSS process?** Không. Nó chỉ ghi nhận các loại allocations do JVM theo dõi; RSS/cgroup usage bao gồm nhiều yếu tố khác.

**34. Sawtooth heap có là leak?** Không nhất thiết; thường là bình thường. Cần theo dõi post-GC live set sau warm-up.

**35. Leak heap phổ biến từ đâu?** Unbounded caches/collections, ThreadLocal, retained listeners, queues và classloader references.

**36. Native leak có thể xảy ra khi heap bình thường?** Có, do direct buffers/JNI/native libraries/threads.

**37. Vì sao phải nhìn CPU throttling khi GC pause tăng?** GC threads và application threads cần CPU; throttling có thể kéo dài processing/p99.

**38. `ActiveProcessorCount` có nên đặt bằng host cores trong Pod limit 1 CPU?** Không mặc định; đặt quá cao gây contention, test theo quota.

**39. HPA có tự chỉnh Xmx?** Không; HPA scale replicas theo metrics; JVM heap sizing là cấu hình runtime riêng.

**40. VPA và HPA có thể xung đột?** Có nếu cả hai kiểm soát resource/metrics không được thiết kế phối hợp.

**41. Startup probe giúp gì?** Cho ứng dụng thời gian khởi động phù hợp trước khi liveness/readiness gây restart/routing, theo cơ chế probe.

**42. Liveness có nên phụ thuộc toàn bộ Azure SQL/Service Bus services?** Thường không; dependency outage chung có thể gây restart storm.

**43. `terminationGracePeriodSeconds` có bảo đảm shutdown hooks chạy khi kernel OOMKilled?** Không; SIGKILL không cho application shutdown bình thường.

**44. Vì sao App Service Plan có thể khiến một app Java ảnh hưởng app khác?** Các apps có thể chia sẻ worker resources trong cùng plan.

**45. Container Apps scale-to-zero ảnh hưởng gì?** Cold start và JVM warm-up có thể làm tăng latency của request đầu.

**46. Vì sao không tự tin rằng stdout GC logs vào Azure Monitor?** Cần cấu hình log collector/diagnostic pipeline và kiểm tra tables/retention.

**47. `jvm_gc_pause_seconds_sum/count` là CPU usage GC?** Không; pause wall-clock sum/count không bao gồm đúng mọi concurrent GC CPU.

**48. Vì sao không tính p95 GC từ average pause?** Average không phải percentile; cần histogram/event samples phù hợp.

**49. Một test G1 vs ZGC cần cố định gì?** JDK/build, app code, load mix, CPU/memory, dependencies, warm-up, metrics.

**50. Khi p99 chậm cùng SQL p95 tăng, ưu tiên gì?** Xem SQL/network/connection pools và saturation trước khi đổi GC.

**51. Khi memory leak xuất hiện, có nên tăng Xmx mãi?** Không; chỉ kéo dài thời gian trước OOME và làm tăng cost.

**52. Vì sao heap thấp vẫn OOMKilled?** Non-heap/native/sidecar/cache/cgroup charges làm tổng vượt memory limit.

**53. Vì sao `OOMKilled` không luôn tạo heap dump?** Process có thể bị kernel kill mà không qua Java OOME handler.

**54. CPU utilization trung bình thấp có loại trừ burst throttling?** Không; cần throttled time/period metrics tương quan latency.

**55. Vì sao nâng số Pod có thể làm Azure SQL chậm hơn?** Tổng JDBC connection pools và concurrency tăng, tạo downstream contention.

**56. Java virtual threads có cho phép concurrency vô hạn?** Không; CPU/memory/downstream concurrency vẫn hữu hạn.

**57. Tại sao không bật remote JMX công khai?** Có thể lộ thông tin/management operations, yêu cầu authentication/TLS/network controls.

**58. Metrics nào chứng minh JVM tối ưu hơn?** Good requests/SLO, GC, RSS/headroom, CPU throttling và chi phí, cùng workload.

**59. Tại sao benchmark một lần chưa đủ?** Noise/warm-up/host contention có thể ảnh hưởng; cần repeated runs và thống kê.

**60. Điều quan trọng nhất trong tối ưu JVM trên Azure?** Đưa ra giả thuyết dựa dữ liệu, thay đổi có thể rollback, đo cả app SLO và budget hạ tầng, không chạy theo “magic flags”.

## 43. Checklist triển khai production

### 43.1. Mục tiêu và môi trường

- [ ] Dịch vụ có owner/SLO xác định cho latency p95/p99, error rate và throughput.
- [ ] Có baseline representative load, request mix, warm-up và soak.
- [ ] Đã pin/ghi JDK major/build/vendor, container image và Azure compute tier.
- [ ] Nắm đúng AKS/App Service/Container Apps/VM runtime model.
- [ ] Đã kiểm tra JVM container awareness/cgroup v1-v2 compatibility.
- [ ] So sánh resource requests/limits với JVM flags thực.
- [ ] Có target cost per good transaction và canary/rollback plan.

### 43.2. Heap, native memory và GC

- [ ] `-Xmx` hoặc `MaxRAMPercentage` có cơ sở đo; không cấu hình mâu thuẫn.
- [ ] Max heap để đủ headroom cho metaspace/direct/thread/code/native/runtime.
- [ ] Heap used/committed/max được theo dõi riêng.
- [ ] Container RSS/working set và cgroup high-watermark có monitoring.
- [ ] Có metric thread count và direct buffer/native memory khi workload dùng.
- [ ] Collector mặc định/G1/ZGC/Parallel được chọn bằng benchmark.
- [ ] Cờ GC hỗ trợ trên đúng JDK, không trộn incompatible collectors.
- [ ] G1 `MaxGCPauseMillis` được hiểu là soft goal.
- [ ] Không cố định young generation hoặc tối ưu deep flags khi chưa có evidence.
- [ ] GC logs có timestamps, rolling/retention/Pod labeling.
- [ ] GC pause được liên hệ với request p99, CPU và dependency latency.
- [ ] Có thời gian soak test đủ phát hiện memory leak.

### 43.3. AKS, CPU và autoscaling

- [ ] Memory request/limit phù hợp node capacity và JVM native budget.
- [ ] CPU limits/requests có giám sát throttled time/periods.
- [ ] `ActiveProcessorCount` không override sai CPU quota.
- [ ] Node pool SKU, AKS HPA/VPA/Cluster Autoscaler được xem cùng nhau.
- [ ] Readiness/startup/liveness probes test dưới pause/load thật.
- [ ] Liveness không restart toàn bộ fleet khi một dependency chung chậm.
- [ ] Graceful shutdown xử lý requests/messages đang chạy và timeout.
- [ ] HPA scale không vượt Azure SQL/Service Bus downstream capacity.
- [ ] Sidecar và logging overhead được tính vào capacity.
- [ ] Pod restart reason phân biệt OOMKilled/eviction/probe/redeploy.

### 43.4. Spring Boot/App Service/Container Apps/VM

- [ ] Spring Actuator health/metrics endpoints được bảo vệ và đúng version.
- [ ] HikariCP/HTTP/worker thread pools và retries có giới hạn.
- [ ] Cache bounded theo size/TTL/weight và business rotation policy.
- [ ] App Service Plan/shared apps memory consumption có giám sát.
- [ ] Container Apps startup/cold start/min replicas có mục tiêu chi phí.
- [ ] VM multiple JVMs không overcommit heap theo host RAM.
- [ ] Docker image pin JDK patch, chạy non-root và không dùng secret trong flags.
- [ ] Runtime configs `JAVA_TOOL_OPTIONS`/entrypoint thật được xác minh.
- [ ] Diagnostic paths và log persistence phù hợp hosting plan/runtime.

### 43.5. Observability và diagnostics

- [ ] Application Insights requests/dependencies/traces được instrument và xác minh.
- [ ] Micrometer/Prometheus JVM metrics exporter hoạt động nếu sử dụng.
- [ ] Azure Monitor/Container Insights collection pipeline có dữ liệu thật.
- [ ] Dashboard có API SLI, CPU throttling, memory, GC pause và OOM counters.
- [ ] Heap/RSS/working set không bị nhầm hoặc cộng chồng các metrics.
- [ ] No data/Pod termination khác 0 GC pause hoặc healthy.
- [ ] JFR/NMT/heap dump có runbook, access controls và retention.
- [ ] Không có JMX/Actuator diagnostics nhạy cảm exposed public.
- [ ] GC/debug logs không gây log ingestion cost bất thường.
- [ ] Có alert khi p99/error-rate, OOM/restarts hoặc memory trend nguy hiểm.

### 43.6. Tối ưu và release governance

- [ ] Mỗi tuning change có hypothesis, baseline, candidate, test và conclusion.
- [ ] Không đổi GC, heap, CPU, replicas và pools cùng một lúc nếu có thể tách.
- [ ] Load tests theo cùng JDK/build/limits/traffic/dependency tiers.
- [ ] Repeated benchmark runs, ghi percentile sample size và variation.
- [ ] Canaries có rollback/forward-fix rõ, không gây production outage không cần thiết.
- [ ] Không chạy GC profiling/heap dumps lên mọi production Pod cùng lúc.
- [ ] Native/heap leak fixes có regression tests và post-deploy soak.
- [ ] Cost per good transaction và Azure Cost Management được review.
- [ ] Security team review heap dump/JFR/credentials/PII handling.
- [ ] Incident runbooks cho OOME, OOMKilled, GC pause, throttling, native leak, restart loop.

## 44. Kết luận

**Tối ưu JVM, bộ nhớ và garbage collection trên Azure** không chỉ là chỉnh `-Xmx` hoặc đổi từ G1 sang ZGC. JVM thực thi bên trong một **ngân sách CPU/memory có thật**: heap, metaspace, thread stacks, direct buffers, native libraries, code cache và GC overhead đều góp phần vào process/container footprint. Trên AKS/Container Apps, **cgroup limits, CPU throttling, readiness/liveness và autoscaling** ảnh hưởng trực tiếp đến hiệu năng; trên App Service/VM, Plan/instance sizing và các processes chia sẻ tài nguyên cũng phải được kiểm soát.

Muốn cải thiện một ứng dụng Java/Spring Boot trên Azure, hãy đo **end-user SLI/SLO, p95/p99, GC pauses, allocation rate, heap live set, RSS, native memory và dependency latency** trên cùng workload. Dùng **GC logs, JFR, `jcmd`, NMT, Azure Monitor/Application Insights và Prometheus** để tìm đúng bottleneck. **`OutOfMemoryError` trong JVM khác `OOMKilled` do kernel**, và nhiều sự cố nhìn giống GC thực ra đến từ queues, SQL connection pools, CPU quotas hoặc network dependencies. Những sự phân biệt đó quyết định cách khắc phục an toàn.

Quy trình bền vững là **baseline → giả thuyết → một thay đổi có kiểm soát → load/soak test → canary → xác minh SLO/chi phí → ghi lại kết quả**. Bằng cách kết hợp JVM tuning với thiết kế application, managed identities, observability, AKS/App Service/Container Apps capacity và Azure cost governance, đội phát triển có thể đạt **độ trễ ổn định, throughput cao, mức sử dụng bộ nhớ hợp lý và khả năng phục hồi tốt** mà không phụ thuộc vào những cờ JVM “thần kỳ”.
