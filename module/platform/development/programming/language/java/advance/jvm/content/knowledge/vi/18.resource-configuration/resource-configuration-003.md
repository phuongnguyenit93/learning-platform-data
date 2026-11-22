# `-Xms` và `-Xmx`: dung lượng heap ban đầu, tối đa và chi phí đánh đổi

**`-Xms`** và **`-Xmx`** là hai tham số JVM thường được dùng để định kích thước **Java heap**, nơi nhiều objects/arrays của ứng dụng được cấp phát và quản lý bởi garbage collector (GC). Chúng trả lời **hai câu hỏi khác nhau**:

- **`-Xms<size>`:** heap **ban đầu** mà HotSpot chuẩn bị/quản lý lúc khởi động; liên quan mức cam kết bộ nhớ và khả năng mở rộng/thu hẹp heap sau đó.
- **`-Xmx<size>`:** **giới hạn tối đa** của Java heap mà JVM được phép sử dụng, không phải lượng heap đã thực sự dùng và càng **không phải giới hạn tổng RAM** của process.

Ví dụ:

```bash
java -Xms256m -Xmx1g -jar application.jar
```

Yêu cầu JVM bắt đầu với heap gần mức 256 MiB và cho phép heap tăng tới khoảng 1 GiB, tùy rounding, vùng nhớ, collector và cách runtime báo kích thước. **Không nên diễn giải** lệnh này là “ứng dụng cấp phát ngay 256 MiB objects” hay “process không bao giờ dùng quá 1 GiB RAM”.

Bài thuộc nhóm **cấu hình tài nguyên** trong Java/JVM: trọng tâm là hiểu đúng các khái niệm và quan sát được đánh đổi giữa **startup, độ ổn định pause/latency, GC frequency, memory footprint, container OOM và headroom dành cho native memory**. Ví dụ chạy với Java 17+; cờ `-XX` và các chi tiết ergonomics nói tới chủ yếu là **HotSpot JVM**.

## 1. Nhận diện nhanh: hai cờ nhưng bốn lớp kích thước

Một heap có thể có nhiều thước đo tại cùng thời điểm:

| Khái niệm | Tên trong Java Management API | Ý nghĩa |
| --- | --- | --- |
| **Initial** | `MemoryUsage.getInit()` | Dung lượng ban đầu JVM yêu cầu dành cho heap management; có thể không được xác định |
| **Used** | `MemoryUsage.getUsed()` | Bộ nhớ hiện được dùng trong vùng heap theo VM management view |
| **Committed** | `MemoryUsage.getCommitted()` | Dung lượng mà VM đã được bảo đảm có thể sử dụng cho vùng này |
| **Max** | `MemoryUsage.getMax()` | Giới hạn tối đa có thể dùng cho heap, có thể không được xác định ở một số memory pools/VMs |

**`-Xms` gần với Initial**, **`-Xmx` gần với Max**. Nhưng số do API trả có thể được **điều chỉnh theo alignment/GC region size**, không phải luôn khớp từng byte với chuỗi command line. Xem `java.lang.management.MemoryUsage` để hiểu contract API.

Quan hệ thường quan sát trên Java heap:

```text
0 ≤ used ≤ committed ≤ max       (khi max được xác định)

               Max heap (-Xmx)
┌────────────────────────────────────────────────┐
│        Committed (VM đã cam kết)                │
│  ┌──────────────────────────────────────────┐  │
│  │       Used (object/heap occupancy)       │  │
│  │  ┌───────────────────────────────┐       │  │
│  │  │ Live objects + allocations    │       │  │
│  │  └───────────────────────────────┘       │  │
│  │                  committed - used       │  │
│  └──────────────────────────────────────────┘  │
│              max - committed                   │
└────────────────────────────────────────────────┘
```

Hình minh họa **không tỉ lệ**. Với collectors có heap address-space mappings đặc thù và những pools khác nhau, chi tiết `reserved`, `committed` hay cách báo virtual memory khác nhau. Nhưng distinction cơ bản **initial/used/committed/max** là thứ bắt buộc phải nắm.

### Hai đối tượng hay bị nhầm

- **Heap used:** số liệu VM về heap objects và vùng đã dùng.
- **Resident Set Size (RSS):** số trang bộ nhớ vật lý của **toàn tiến trình** đang cư trú theo thống kê OS, có thể gồm heap, native memory, code, stacks, file mappings...
- **Virtual memory reserved:** vùng địa chỉ ảo VM đặt trước, không có nghĩa toàn bộ đã có physical RAM backing.
- **Container memory usage:** chỉ số của cgroup có thể gồm những thành phần khác process RSS, ví dụ page cache; xem metric definition.

**Không lấy `heap used`, `heap committed`, `RSS`, `container memory.current` làm những tên gọi khác nhau của cùng một con số.**

## 2. Cú pháp cơ bản và cách hiểu đơn vị

Các cách ghi phổ biến:

```bash
java -Xms128m -Xmx512m Main
java -Xms1g -Xmx4g Main
java -Xmx1024m Main
```

Trong cờ sizing của HotSpot, suffix `k`, `m`, `g` thường tương ứng các bội **1024**; tài liệu `java` của đúng release là nguồn chuẩn về cú pháp và giới hạn hợp lệ. Với giao diện vận hành, nên ghi rõ **MiB/GiB** thay vì dùng “MB/GB” không nhất quán.

| Option | Mục tiêu |
| --- | --- |
| `-Xms128m` | Yêu cầu initial heap gần 128 MiB |
| `-Xmx512m` | Giới hạn heap tối đa gần 512 MiB |
| `-Xms1g -Xmx1g` | Yêu cầu initial và maximum bằng nhau: “fixed-size heap policy” theo cách dùng phổ biến |
| Chỉ `-Xmx512m` | Max heap được chỉ định; initial heap do VM ergonomics/flags khác quyết định |
| Không chỉ định cả hai | JVM tính sizing theo memory, collector, JVM/version/container ergonomics |

**Quy tắc hợp lệ:** Initial heap không được lớn hơn maximum heap; cấu hình `-Xms2g -Xmx1g` sẽ gây lỗi startup trên HotSpot thay vì tự động đảo các giá trị cho bạn.

### Lệnh đứng trước application entrypoint

```bash
java -Xms128m -Xmx512m -jar app.jar
```

Đúng khi `app.jar` có Main-Class manifest và build tương ứng. Những JVM options đứng **trước** `-jar`/main class. Ví dụ:

```bash
java -jar app.jar -Xmx512m
```

không tương đương: `-Xmx512m` lúc đó thường được chuyển thành **application argument**, không còn là launcher JVM option. Với nhiều script/container wrappers, kiểm tra command line **đúng process**, vì cấu hình tưởng đã truyền có thể bị lược bỏ hoặc chuyển sai vị trí.

## 3. “Ban đầu” không phải “đã dùng”

Nếu chạy:

```bash
java -Xms256m -Xmx1g MyApp
```

ở lúc process mới lên, ứng dụng có thể chỉ có vài chục MiB objects đang sống. **Heap committed** có thể đã gần initial setting; **heap used** thấp hơn rất nhiều. Collector có thể GC/điều chỉnh committed heap khi workload tăng hoặc giảm theo policy.

Một cách diễn đạt đúng:

> “`-Xms256m` yêu cầu kích thước heap ban đầu và chi phối hành vi cam kết/điều chỉnh heap của HotSpot; nó không khởi tạo 256 MiB đối tượng nghiệp vụ và không có nghĩa ứng dụng cần từng ấy live data.”

Điều này đặc biệt quan trọng với môi trường có **nhiều JVM processes**: nếu đặt initial heap quá cao cho hàng trăm processes, aggregate committed/resident footprint có thể làm máy thiếu tài nguyên, kể cả khi mỗi service chỉ giữ một live set nhỏ.

### Reserved, committed và actual physical pages

HotSpot có thể **reserve** một vùng địa chỉ ảo lớn cho heap tối đa, rồi **commit** theo nhu cầu. OS và page allocator quyết định việc backing memory/physical pages, có thể lazy fault. Do đó:

- Reserve địa chỉ ảo không đồng nghĩa RSS tăng tới Xmx.
- Commit không nhất thiết đồng nghĩa tất cả các trang đã **được chạm** ngay ở startup trên mọi nền tảng/collector.
- `-XX:+AlwaysPreTouch` (nếu HotSpot build hỗ trợ) có thể chạm các heap pages đã commit lúc startup, dời một phần chi phí page faults từ runtime sang startup.
- Large pages, GC và OS mapping policy có thể đổi chi tiết.

**Không nên dùng `-Xms` như công cụ “đặt số GB RSS chính xác”**; phải đo RSS/container metrics từ OS và heap data từ JVM.

## 4. “Tối đa” không phải “giới hạn bộ nhớ tiến trình”

Java heap chỉ là một phần JVM process. Mô hình:

```text
CONTAINER / PROCESS MEMORY BUDGET
├─ Java heap (thường giới hạn bởi -Xmx)
├─ Metaspace và class metadata
├─ Code cache / JIT compiled machine code
├─ Thread stacks
├─ Direct ByteBuffers, NIO/native allocations
├─ GC metadata, remembered sets, marking structures
├─ JVM runtime internal native data
├─ Native libraries, JNI, libc arenas, TLS, mmap
├─ Process executable / shared libraries / stacks
└─ Những khoản OS/cgroup accounting liên quan
```

Nếu container limit là **1 GiB** và bạn đặt `-Xmx1g`, **tổng process memory hoàn toàn có thể vượt 1 GiB** khi cộng thêm non-heap. Kernel/container runtime có thể **OOM-kill process** mặc dù JVM chưa ném `OutOfMemoryError: Java heap space`.

### Ngân sách ví dụ để lập kế hoạch

Giả sử container memory limit **1024 MiB**. Bạn thử `-Xmx512m`, để lại **512 MiB headroom danh nghĩa** cho native/JVM/OS-related overhead.

**Đây là phép phân bổ ban đầu, không phải tỷ lệ mặc định bắt buộc.** Service có 1.000 threads, nhiều direct buffers hoặc JNI có thể cần nhiều headroom hơn. Service nhỏ, ít threads và dependency đơn giản có thể dùng heap fraction khác, nhưng đều phải đo.

Cần theo dõi **peak RSS/cgroup usage**, không chỉ heap after GC. Nếu measurement cho thấy non-heap peak 450 MiB và heap gần 512 MiB, tổng có thể tiến sát giới hạn 1024 MiB; chưa tính mọi overhead/uncertainty. Chừa khoảng an toàn cho bursts và hoạt động chẩn đoán.

## 5. Tăng `-Xmx` mang lại điều gì?

Tăng maximum heap có thể giúp:

- Giảm frequency của collections do heap thiếu không gian.
- Cho phép app xử lý **live set lớn hơn**.
- Có headroom cho allocation bursts và các GC concurrency phases.
- Giảm rủi ro `OutOfMemoryError: Java heap space` nếu nguyên nhân thực là heap pressure.
- Tăng throughput trong một số workload vì giảm công việc GC/expansion.

Nhưng đổi lại:

- Có thể tăng memory footprint và tăng cạnh tranh RAM với processes khác.
- Với một số collectors/workloads, chu kỳ collection hoặc **tail latency** có thể khác theo dung lượng và live data, không có quy luật chung “gấp đôi heap → pause gấp đôi”.
- Nếu bật pre-touch/fixed large heap, startup có thể nặng hơn.
- GC log/heap dump lớn hơn; quá trình chẩn đoán tốn resource hơn.
- Nếu JVM process ở container nhỏ, dễ bị OOMKilled do native headroom quá thấp.
- **Memory leak không được sửa**: tăng heap chỉ kéo dài thời gian tới khi out-of-memory.

### Khi nào tăng `-Xmx` thực sự hợp lý?

Nếu thấy nhiều collections dưới tải mà after-GC live heap vẫn có khoảng cần thiết cho ứng dụng, hoặc GC liên tục lấy lại quá ít không gian vì heap nhỏ, tăng max heap **có thể** là một phương án. Nhưng phải phân biệt:

- **Healthy allocation churn:** nhiều objects ngắn hạn; collector xử lý được và SLO đạt.
- **Large legitimate live set:** dữ liệu cần giữ thật sự lớn hơn budget.
- **Memory leak/unbounded retention:** references không được giải phóng theo vòng đời; tăng Xmx chỉ trì hoãn lỗi.
- **Non-heap OOM:** metaspace/direct buffers/native threads; tăng Xmx không giải quyết và có thể làm thiếu headroom hơn.

**Đừng chọn Xmx bằng cảm giác “RAM máy có 16 GB nên cấp cả 16 GB”.** Xem cgroup limit và toàn bộ process/system budget.

## 6. Giảm `-Xmx` có lợi gì và hại gì?

Giảm maximum heap có thể:

- Giảm upper bound Java heap memory của mỗi JVM.
- Cho phép chạy nhiều instance hơn trên cùng node nếu non-heap phù hợp.
- Làm GC bắt đầu thu gom sớm hơn; đôi khi giảm lượng công việc retained/old-generation scan trong một số trường hợp.
- Bộc lộ unbounded retention ở môi trường thử nghiệm nhanh hơn.

Nhưng cũng có thể:

- Tăng GC frequency và GC CPU.
- Làm tăng allocation stalls, promotion failures, evacuation failures hoặc Full GC theo collector.
- Dẫn tới `OutOfMemoryError: Java heap space` khi live data/allocations không còn vừa.
- Giảm throughput, tăng tail latency vì collector thiếu headroom.
- Tăng CPU/energy do thu gom quá thường xuyên.

**Không nên mặc định** giảm Xmx luôn làm p99 tốt hơn vì “GC phải quét ít bộ nhớ”. Một bộ thu gom thiếu không gian có thể rất vất vả, khiến p99 xấu đi.

### Một quy tắc kinh nghiệm đúng hơn

**Xmx phải đủ chứa live set cộng headroom cho allocations và hoạt động GC** của **collector/workload** đang chạy. Dung lượng cần thiết không chỉ là số live objects trong một heap dump duy nhất.

## 7. `-Xms` nhỏ: startup nhẹ hơn, runtime có thể phải mở heap

Nếu initial heap thấp hơn max:

```bash
java -Xms64m -Xmx512m MyApp
```

VM có thể bắt đầu với committed heap nhỏ hơn, rồi **tăng committed heap** khi allocation demand tăng (kèm ràng buộc collector). Những đánh đổi:

**Ưu điểm tiềm năng:**

- Ban đầu giữ ít tài nguyên hơn nếu workload cold/light.
- Có thể phù hợp CLI, short-lived batch, serverless hoặc nhiều JVM trên một node.
- Cho phép VM co giãn/return unused memory nếu collector/VM support.

**Chi phí tiềm năng:**

- Heap expansion/commit có thể gây overhead/latency.
- Initial heap nhỏ có thể tạo nhiều collections ở giai đoạn startup/warm-up.
- JVM có thể phải commit/touch pages khi allocation tăng.
- Startup benchmark có thể trông nhanh hơn nhưng **first useful request** hoặc vài phút đầu lại xấu hơn.

**Quan trọng:** không có bảo đảm “-Xms nhỏ luôn startup nhanh” hoặc “-Xms lớn luôn giảm GC”. Class loading, framework initialization, compiler activity, page faults và filesystem cache cũng ảnh hưởng.

### Chọn initial heap dựa trên gì?

Nếu startup cần load vài trăm MiB objects thật, Xms quá nhỏ có thể dẫn tới churn/expansion. Nếu service chỉ có live heap 50 MiB nhưng đặt Xms nhiều GiB, có thể giữ footprint không cần thiết. Đo **startup class loading/allocation**, **initial GC logs**, **container RSS** và latency để quyết định.

## 8. `-Xms` bằng `-Xmx`: fixed-size heap policy

Cấu hình phổ biến:

```bash
java -Xms512m -Xmx512m MyApp
```

Lợi ích có thể có:

- Giảm một phần overhead do heap resizing/commit tại runtime.
- Có thể làm runtime behavior ổn định hơn trong workload có footprint tương đối cố định.
- Dễ dự tính upper bound Java heap; giảm một biến khi benchmark.
- Với **ZGC**, khi Xms = Xmx thì cơ chế uncommit heap trống bị vô hiệu theo semantics được tài liệu mô tả.

Đánh đổi:

- JVM có thể **commit** nhiều bộ nhớ từ startup dù workload chưa dùng.
- Nếu kết hợp `-XX:+AlwaysPreTouch`, có thể **touch** một vùng heap lớn lúc startup và tăng đáng kể startup latency/RSS.
- Không trả lại nhiều heap memory cho OS trong một số collector/mode.
- Trên node chạy nhiều services, memory pressure tổng có thể xấu hơn.
- Fixed-size **heap** không làm toàn JVM process memory fixed-size.

### Ba nhận định phải phân biệt

1. **`Xms = Xmx`**: yêu cầu initial/maximum heap bằng nhau.
2. **`AlwaysPreTouch`**: yêu cầu JVM touch committed heap pages trước khi cấp phát cho Java application (nếu được hỗ trợ).
3. **`RSS bằng Xmx`**: **không thể suy ra** chỉ từ hai điều trên nếu chưa xét OS, GC, memory mappings và đo thực tế.

Hãy tránh câu “Xms=Xmx sẽ chiếm toàn bộ 4 GB RAM vật lý ngay lập tức” dưới dạng định luật cho mọi collector/OS. Thay bằng số `committed`, `used`, RSS quan sát thực tế.

## 9. G1, Parallel, Serial, ZGC: cùng flags nhưng behavior khác

`-Xms`/`-Xmx` thiết lập các giới hạn tổng quan, **không chọn collector**. GC được lựa chọn bằng JVM ergonomics hoặc option khác, ví dụ `-XX:+UseG1GC` trên HotSpot.

| Collector | Mối quan tâm khi chọn heap |
| --- | --- |
| **Serial GC** | Một GC worker, STW; heap lớn/live set lớn có thể làm pauses đáng kể tùy workload |
| **Parallel GC** | Hướng throughput; dung lượng heap ảnh hưởng GC frequency, promotion và pause/throughput tradeoff |
| **G1 GC** | Phân vùng heap thành regions; Xmx ảnh hưởng số/kích thước regions và space budgets; pause target là mục tiêu, không bảo đảm deadline |
| **ZGC** | Concurrent low-pause collector; cần enough headroom theo allocation rate để tránh stalls, có uncommit khi Xms < Xmx |
| **Shenandoah (nếu build hỗ trợ)** | Concurrent collection, cần điều kiện/space cho concurrent work; flags và availability tùy release |

**Không có “Xmx 2g tối ưu cho mọi GC”**. Khi đổi GC, giữ nguyên heap/CPU/workload để so trước khi thay thêm 5 tham số cùng lúc.

### G1 và ergonomics

- G1 có young/old generations theo regions; nhiều hoạt động phụ thuộc live set/allocations, không chỉ Xmx.
- Heap region sizing và collector heuristics có thể thay khi đổi maximum heap.
- Một Xmx lớn hơn cho phép bớt GC cycles trong một số trường hợp, nhưng cũng có thể thay heap layout/footprint.
- **`-XX:MaxGCPauseMillis` là mục tiêu mềm**, không phải lời hứa pauses luôn dưới threshold.

### ZGC và `-Xms`

Trên HotSpot JDK 17 ZGC hỗ trợ theo platform, tài liệu mô tả cơ chế **uncommit unused heap pages**, nhưng không uncommit xuống dưới Xms. Nếu **Xms = Xmx**, uncommit bị vô hiệu theo cấu hình đó; nếu Xms nhỏ hơn, ZGC có thể trả lại bộ nhớ ít dùng sau delay.

Ví dụ:

```bash
java -XX:+UseZGC -Xms128m -Xmx1g MyApp
```

Chỉ là **lệnh minh họa cho HotSpot JDK/OS/architecture hỗ trợ ZGC**; một số collector/release có lower bound hoặc tính khả dụng khác. Mức heap trong ví dụ **không là khuyến nghị production**.

Flags khác:

```text
-XX:+ZUncommit
-XX:-ZUncommit
-XX:ZUncommitDelay=300
-XX:SoftMaxHeapSize=512m
```

`SoftMaxHeapSize` là **mục tiêu mềm** của ZGC trong những bản hỗ trợ; không thay hard max `-Xmx` và có thể bị vượt khi JVM cần memory để tránh stalls/OOM. **Đừng giả định** ý nghĩa và flags này áp dụng giống hệt cho Serial/Parallel/G1.

## 10. Container-aware heap sizing và phần trăm RAM

HotSpot JDK 17 phổ biến có nhận biết container resource limits thông qua `UseContainerSupport`, nhưng phải kiểm tra bản patch, cgroup version và runtime thật. Nếu không đặt Xmx rõ, VM có thể dùng memory ergonomics theo lượng RAM mà JVM nhận diện.

Một số options HotSpot:

| Flag | Ý nghĩa |
| --- | --- |
| `-XX:MaxRAMPercentage=...` | Dùng tỷ lệ RAM khả dụng theo logic VM để tính maximum heap nếu không có explicit Xmx |
| `-XX:InitialRAMPercentage=...` | Tính initial heap theo tỷ lệ RAM khi không có explicit Xms |
| `-XX:MinRAMPercentage=...` | **Tên dễ gây hiểu nhầm**: chủ yếu tham gia max-heap ergonomics trên cấu hình RAM nhỏ, không đơn giản là “minimum heap percentage” |
| `-XX:+UseContainerSupport` | Cho phép JVM sử dụng thông tin container constraints khi được hỗ trợ |
| `-XX:ActiveProcessorCount=...` | Override số processors VM coi là active; ảnh hưởng ergonomics GC/JIT khác ngoài heap |

Ví dụ trên environment/container phù hợp:

```bash
java -XX:InitialRAMPercentage=10 -XX:MaxRAMPercentage=60 -jar app.jar
```

Điều này không nói heap chắc chắn bằng chính xác 10%/60% từng byte vì alignment và heuristics. Các con số **10%/60% chỉ minh họa**, không là lựa chọn tối ưu chung cho mọi service.

### Explicit flags thường có ưu tiên

Khi đã dùng `-Xmx512m`, đừng kỳ vọng `-XX:MaxRAMPercentage=60` vẫn tự kéo Xmx lên 60% RAM. Trên HotSpot, **explicit Xmx thường có precedence** so với default ergonomic percentage. Tương tự với Xms so với initial percentage; hãy xem `PrintFlagsFinal` để kiểm chứng giá trị cuối.

### Container request khác container limit

- Kubernetes **memory request** phục vụ lập lịch/đảm bảo tương ứng, không nhất thiết là memory limit JVM được dùng để tính max.
- **Memory limit** được cgroup áp đặt và có thể dẫn tới OOMKilled nếu process/cgroup vượt.
- Nếu container **không có memory limit**, JVM có thể tính theo host/node hoặc policy khác; không được suy nó sẽ chia đều RAM node cho số pods.
- Ghi cả container `requests`, `limits` và JVM effective flags vào báo cáo.

**Thực hành:** đo real memory usage của container và headroom thay vì mặc định “60% heap có nghĩa 40% đủ mọi native overhead”.

## 11. Lệnh kiểm tra JVM thật và effective heap

### Nhận diện runtime

```bash
java -version
java --version
```

Ghi rõ **JDK major/update/build, vendor và VM implementation**. Với OpenJ9 hoặc Native Image, flags/diagnostics có thể khác; bài chủ yếu nói HotSpot.

### In flags trên HotSpot

```bash
java -Xms128m -Xmx512m -XX:+PrintFlagsFinal -version
```

Tìm các names như `InitialHeapSize`, `MaxHeapSize`, `MinHeapSize` và những cờ liên quan tới GC. Output gồm rất nhiều flags, đơn vị thường là bytes. Xem **effective values** thay vì chỉ suy từ câu lệnh.

Lưu ý `MinHeapSize` là một giá trị nội bộ/tuning trong HotSpot, **không được đồng nhất máy móc** với mọi điều kiện co heap của mọi collector/JVM port.

### Kiểm tra container support

```bash
java -XshowSettings:system -version
```

Trên HotSpot JDK 17 hỗ trợ option này, output có thể mô tả provider/container constraints, CPUs và memory. Cách in/nhãn biến động theo build; nếu VM không hỗ trợ, đọc chính xác `java --help-extra` hoặc tài liệu của distribution.

## 12. Java 17+ runnable: quan sát initial, used, committed và max

Tạo file **`HeapSizingDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.util.ArrayList;
import java.util.List;

public final class HeapSizingDemo {
    private static final int BLOCK_SIZE = 128 * 1024;

    public static void main(String[] args) {
        if (args.length != 0) {
            throw new IllegalArgumentException("No arguments expected");
        }

        MemoryUsage before = ManagementFactory
                .getMemoryMXBean()
                .getHeapMemoryUsage();

        List<byte[]> retained = new ArrayList<>();
        int checksum = 0;

        for (int i = 0; i < 64; i++) {
            byte[] block = new byte[BLOCK_SIZE];
            block[0] = (byte) i;
            retained.add(block);
            checksum += Byte.toUnsignedInt(block[0]);
        }

        MemoryUsage after = ManagementFactory
                .getMemoryMXBean()
                .getHeapMemoryUsage();

        System.out.println("arrays: " + retained.size());
        System.out.println("payload bytes: "
                + (retained.size() * BLOCK_SIZE));
        System.out.println("checksum: " + checksum);
        System.out.println("first: "
                + Byte.toUnsignedInt(retained.get(0)[0]));
        System.out.println("last: "
                + Byte.toUnsignedInt(retained.get(63)[0]));
        System.out.println("done");

        // Những số này CỐ Ý biến động theo collector/JVM/run.
        System.err.println("heap init (bytes): " + after.getInit());
        System.err.println("heap max (bytes): " + after.getMax());
        System.err.println("heap used before (bytes): "
                + before.getUsed());
        System.err.println("heap committed before (bytes): "
                + before.getCommitted());
        System.err.println("heap used after (bytes): "
                + after.getUsed());
        System.err.println("heap committed after (bytes): "
                + after.getCommitted());
    }
}
```

Biên dịch bằng JDK 17+:

```bash
javac -encoding UTF-8 HeapSizingDemo.java
```

Chạy trên HotSpot với **hai cấu hình riêng**:

```bash
java -Xms32m -Xmx128m HeapSizingDemo
java -Xms128m -Xmx128m HeapSizingDemo
```

**Standard output phần chức năng của cả hai lần chạy bình thường:**

```text
arrays: 64
payload bytes: 8388608
checksum: 2016
first: 0
last: 63
done
```

**Standard error không có giá trị số cố định.** Ví dụ chỉ để hiểu format:

```text
heap init (bytes): [giá trị từ VM]
heap max (bytes): [giá trị từ VM]
heap used before (bytes): [giá trị runtime]
heap committed before (bytes): [giá trị runtime]
heap used after (bytes): [giá trị runtime]
heap committed after (bytes): [giá trị runtime]
```

Đây **không phải literal stderr**: các chuỗi trong ngoặc vuông là diễn giải của các số mà API in thật. Dữ liệu phụ thuộc VM, collector, alignment, background GC và thời điểm thu thập.

### Kiểm tra phép tính được xác định

- Mỗi array có `128 × 1024 = 131072` bytes.
- Có `64` arrays, tổng **8.388.608 bytes** payload.
- Byte đầu của array thứ `i` được gán `i` cho `i=0..63`, không có overflow; tổng `0+1+...+63 = 63×64/2 = 2016`.
- Phần tử đầu là `0`, phần tử cuối là `63`.
- `retained` còn được dùng sau vòng lặp, nên references được giữ tới các phép đọc rõ ràng.

**Không cần `System.gc()`** để quan sát heap sizing. Thuật toán GC và hoạt động nền có thể khiến `used after` không tăng đúng bằng 8.388.608 bytes so với `used before`; còn headers, metadata, các allocations khác và GC events.

### Cần so sánh điều gì?

Với `-Xms32m -Xmx128m`, kỳ vọng *initial heap* nhỏ hơn cấu hình `-Xms128m -Xmx128m`. **Đừng bắt stdout đổi:** cùng code/inputs phải cho cùng kết quả tính toán. Đọc `heap init`, `heap committed` và `heap max`, sau đó nếu muốn so footprint hãy đo **RSS/container memory** từ OS ngoài chương trình.

Vì chương trình nhanh, không nên kết luận “cấu hình B có startup time nhanh hơn” chỉ bằng hai lần dùng stopwatch. Hãy đo nhiều process launches và startup marker có định nghĩa.

## 13. Lab 2: tạo áp lực heap có kiểm soát

Để thấy maximum heap có thể trở thành giới hạn, viết **`HeapPressureDemo.java`**. Mẫu này có giới hạn số blocks, không cần làm ứng dụng bị OOM để chứng minh heap pressure.

```java
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;

public final class HeapPressureDemo {
    public static void main(String[] args) {
        List<byte[]> blocks = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 32; i++) {
            byte[] data = new byte[256 * 1024];
            data[0] = (byte) (i + 1);
            blocks.add(data);
            checksum += Byte.toUnsignedInt(data[0]);
        }

        System.out.println("blocks: " + blocks.size());
        System.out.println("payload bytes: "
                + (blocks.size() * 256 * 1024));
        System.out.println("checksum: " + checksum);

        long max = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getMax();
        System.err.println("heap max bytes (dynamic): " + max);
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 HeapPressureDemo.java
java -Xms32m -Xmx64m HeapPressureDemo
java -Xms64m -Xmx128m HeapPressureDemo
```

**Standard output phần chức năng nếu process hoàn tất bình thường:**

```text
blocks: 32
payload bytes: 8388608
checksum: 528
```

Giải thích: `32 × 256 × 1024 = 8.388.608` bytes; các giá trị byte đầu từ `1` đến `32` có tổng `32×33/2 = 528`. Đây là **retained payload**, không phải tổng bộ nhớ JVM thực sự dùng.

**Không cố ý tạo OOM trên shared machine**. Nếu cần kiểm thử OOME, dùng môi trường cô lập, giới hạn tài nguyên, có giám sát và tách khỏi production traffic. Không tạo vòng lặp không giới hạn chỉ để chờ crash.

### Quan sát GC thay vì đoán

Với HotSpot:

```bash
java -Xms32m -Xmx64m -Xlog:gc*=info HeapPressureDemo
java -Xms64m -Xmx128m -Xlog:gc*=info HeapPressureDemo
```

GC logs có format/duration khác theo collector/JDK/hardware; **không có expected log cố định**. Vì demo ngắn và retention chỉ vài MiB, **có thể không thấy collection event nào**. Điều đó không làm demo sai.

## 14. Đọc GC logs để hiểu heap sizing

Trên HotSpot JDK 17:

```bash
java -Xms128m -Xmx512m -Xlog:gc*=info:file=gc.log:uptime,level,tags -jar app.jar
```

Lưu ý `app.jar` phải là ứng dụng thật và có main manifest. Log có thể chứa những thông tin về heap trước/sau collection, collectors, regions, promotion, pauses, concurrent phases.

### Bảng thông số cần quan sát

| Metric | Nếu tăng/giảm có thể báo gì? | Điều KHÔNG nên kết luận |
| --- | --- | --- |
| **Heap used before GC** | Allocation pressure/lượng dữ liệu trước collection | Không tự là live set |
| **Heap used after GC** | Dữ liệu còn retained và cấu trúc heap sau collection | Một event riêng lẻ chưa là bằng chứng leak |
| **GC pause duration** | Delay STW ở event đó | Không phải toàn bộ request latency |
| **GC frequency** | Số collections per time hoặc per requests | Nhiều young GCs không luôn xấu |
| **Allocation rate** | Bytes allocated per second | Không phải live heap growth |
| **Promotion/old occupancy** | Objects đi qua generations, pressure old region | Không tự là leak |
| **Committed heap trend** | JVM tăng/giảm committed capacity | Không bằng RSS trên mọi collector |
| **Full GC / evacuation failure** | Dấu hiệu memory pressure hoặc collector-specific event | Không đủ để quy cho Xms nhỏ mà bỏ qua live-set |

Cần ghép **timestamp + workload + app latency + CPU/container memory**. Ví dụ việc giảm số GC events bằng cách tăng Xmx chưa đủ nếu latency p99 không tốt hơn hoặc memory footprint vượt giới hạn.

### Không dùng GC pause trung bình thay p99

Vài pauses dài có thể làm tail latency xấu dù mean thấp. Hãy báo **distribution** của request latency và GC pause, có căn cứ time alignment giữa request spans với GC events.

## 15. Quan sát process đang chạy với `jcmd` và JMX

Trên HotSpot có tool attach hỗ trợ:

```bash
jcmd -l
jcmd PID VM.flags
jcmd PID VM.command_line
jcmd PID GC.heap_info
jcmd PID VM.native_memory summary
```

`PID` là placeholder cho process ID thật. `VM.native_memory summary` cần **Native Memory Tracking** được bật từ startup để có dữ liệu có ích:

```bash
java -XX:NativeMemoryTracking=summary -Xms128m -Xmx512m -jar app.jar
```

**Lưu ý NMT:** thống kê phạm vi internal HotSpot/JDK, không phải tất cả memory OS có thể account; không giả định `NMT total = RSS`. Bật NMT có overhead và thường không thể kích hoạt đầy đủ một cách hồi tố nếu JVM chưa bật từ lúc start.

### Vì sao JMX hữu ích?

`MemoryMXBean.getHeapMemoryUsage()` cho phép ứng dụng/monitoring theo dõi `init/used/committed/max` qua thời gian, thay vì suy từ một lệnh launch đã cách đây nhiều giờ. Một heap có thể lớn lên/co xuống tùy collector và config; cần xem **diễn biến** chứ không chỉ snapshot.

### JVM flags có nhiều nguồn

Flags có thể đến từ:

- Command line được wrapper/script truyền.
- `JAVA_TOOL_OPTIONS` hoặc `JDK_JAVA_OPTIONS`.
- Container entrypoint và orchestrator.
- Tooling như build runners/app servers.
- JVM ergonomics khi cờ không đặt tường minh.

Hãy lưu **effective JVM command line/flags** từ process, đừng chỉ nhìn deployment YAML rồi cho rằng VM chắc chắn nhận các cờ y hệt.

## 16. `AlwaysPreTouch`: chuyển một phần chi phí sang lúc khởi động

Trên HotSpot hỗ trợ:

```bash
java -Xms512m -Xmx512m -XX:+AlwaysPreTouch -jar app.jar
```

`AlwaysPreTouch` yêu cầu VM touch heap pages lúc startup sau commit. Điều này có thể:

- Tăng startup duration và mức RSS ban đầu.
- Giảm một phần page faults/touch work trong thời gian phục vụ.
- Giúp phát hiện memory allocation/commit problems ở giai đoạn khởi động.
- Làm container nhỏ hoặc hệ thống đông JVM processes căng RAM sớm hơn.

**Không bảo đảm** luôn giảm tail latency; nếu workload nhỏ và JVM ít đụng heap, pre-touch nhiều pages có thể chỉ tốn công. Nếu bật pre-touch nhưng Xms rất nhỏ, chỉ initial committed heap có thể được chuẩn bị theo config; đừng mặc định toàn Xmx đã được touched.

### Một phép thử có ý nghĩa

So:

```bash
java -Xms512m -Xmx512m -XX:-AlwaysPreTouch -jar app.jar
java -Xms512m -Xmx512m -XX:+AlwaysPreTouch -jar app.jar
```

Chỉ thay **một flag**, đo cả **startup, RSS, CPU page faults, first-request latency và steady-state**. Đưa ra kết luận trong phạm vi OS/collector/kernel đang dùng.

## 17. `-Xms` bằng Xmx có cần thiết cho latency thấp?

Không phải mọi dịch vụ low-latency đều cần fixed heap. Cân nhắc:

- **Workload ổn định, memory đủ:** fixed heap có thể giảm resize overhead và predictability tốt hơn.
- **Workload theo chu kỳ/ngủ nhiều:** expandable/shrinkable heap có thể giảm footprint khi idle, nếu collector hỗ trợ.
- **Serverless/cold-start:** large initial heap + pre-touch có thể làm startup xấu.
- **Container memory nhỏ:** dành heap cố định quá lớn có thể gây OOMKilled dù used Java objects không cao.
- **ZGC:** uncommit có cost commit/uncommit; cần cân nhắc latency với khả năng trả lại pages cho OS.
- **Batch jobs:** thời gian từ launch tới kết quả cuối khác mục tiêu long-running server p99.

**Một chiến lược thường đúng:** bắt đầu bằng default/ergonomic sizing đủ an toàn, đo allocation/live set/GC/latency, rồi tối ưu có đối chứng. Không sao chép một “Xms=Xmx luôn tốt nhất” từ benchmark không cùng workload.

## 18. Cách chọn Xmx dựa trên live set và budget

### Bước 1 — Đo live set

Quan sát **used after representative collections** trong các giai đoạn tải khác nhau, heap histograms/heap dumps khi cần, object retention và allocation rate.

Một snapshot ngay sau startup chưa đại diện traffic peak; sau full/business cycle có thể khác nhiều.

### Bước 2 — Đo allocation bursts

Một service có live set 200 MiB nhưng có thể tạo 300 MiB short-lived buffers trong peak window. Không nên đặt `Xmx=220m` chỉ vì “live objects khoảng 200 MiB”. Collector cần không gian cho allocations và hoạt động thu gom/evacuation.

### Bước 3 — Dành headroom cho GC

Các collectors khác nhau cần space cho copying, old-gen pressure, concurrent allocations và marking/relocation. Không có một công thức duy nhất `Xmx = live × 1.2` dùng cho mọi G1/ZGC/Parallel workloads.

### Bước 4 — Tính native memory

Threads, metaspace, code cache, direct buffers và JNI có thể chiếm đáng kể. Đặt Xmx thấp hơn container limit, xét peak native usage và cgroup overhead.

### Bước 5 — Thử vài cấu hình và so sánh

Ví dụ A/B:

```text
A: -Xms128m -Xmx512m
B: -Xms256m -Xmx512m
C: -Xms512m -Xmx512m
D: -Xms128m -Xmx768m

Từng run giữ JDK, collector, workload, CPU/cgroup limits
tương đương, và báo số liệu thực.
```

Các số là **kịch bản thử**, không phải khuyến nghị universal. So A/B/C để tập trung effect **Xms**, so A/D để tập trung effect **Xmx**. Tránh vừa đổi collector vừa đổi Xms/Xmx rồi suy cái nào tạo speedup.

## 19. Lỗi hay gặp và cách chẩn đoán

### 19.1. `OutOfMemoryError: Java heap space`

Ý nghĩa thường là Java heap không còn đáp ứng allocation sau các biện pháp cần thiết. Hướng kiểm tra:

- Xmx hiệu lực đúng mong đợi chưa?
- Heap live set và retained paths có tăng không?
- Có unbounded cache, queue, collection hoặc large arrays không?
- Có allocation burst không phù hợp limit?
- GC logs có promotion/evacuation pressure hay Full GC không?
- Thay heap có đúng là fix bền vững không?

Không tăng Xmx vô hạn để che một leak. Heap dump có thể chứa secrets, cần quyền/phương án an toàn.

### 19.2. `OutOfMemoryError: GC overhead limit exceeded`

Có thể xuất hiện ở những collector/config phù hợp khi JVM tốn quá nhiều thời gian GC mà thu hồi quá ít heap. Thông báo không phải định nghĩa chung cho mọi GC; cần đọc logs và collector đang dùng. Chỉ tăng Xmx có thể che symptoms nếu retention không được sửa.

### 19.3. Container `OOMKilled` / exit 137

Process có thể bị OS/cgroup terminate mà JVM **không có cơ hội** ném `Java heap space`. Dấu hiệu:

- Pod `Last State: OOMKilled`.
- Container memory peak gần limit.
- JVM heap used chưa chạm Xmx.
- RSS/native memory cao, hoặc cgroup metrics gồm page cache.

**Cần điều tra process/container memory budget**, không chỉ Java heap. Exit code 137 cũng có thể do SIGKILL vì nguyên nhân khác; dùng pod events/OS logs để xác minh OOM, đừng suy từ số 137 đơn lẻ.

### 19.4. `OutOfMemoryError: Metaspace`

Metaspace thuộc non-heap. Xmx lớn lên không tự giải quyết; có thể làm giảm headroom cho metaspace. Cần xem class loading/class loaders, maximum metaspace nếu cấu hình và retention.

### 19.5. `OutOfMemoryError: Direct buffer memory`

Direct buffers thường dùng bộ nhớ ngoài Java heap (native backing), dù đối tượng wrapper vẫn ở heap. Cần xem `MaxDirectMemorySize`/NIO usage và lifecycle. Đổi Xmx có thể ảnh hưởng ergonomic default/direct buffer budget trong một số HotSpot releases nhưng không thay thế phân tích native allocations.

### 19.6. `unable to create native thread`

Có thể hết process/thread resource, address space/stack memory, OS limits hoặc cgroup PID limits. Tăng Xmx có thể càng làm ít memory dành cho native threads. Giảm leak threads/thread pool size hoặc điều chỉnh resources theo bằng chứng.

### 19.7. “Heap committed cao nhưng used thấp”

Không tự kết luận memory leak. Committed capacity có thể giữ lại để phục vụ allocations tương lai hoặc do Xms/fixed heap policy. So **after-GC used trend**, retained objects và actual native/OS footprint.

### 19.8. “Tăng Xmx mà ứng dụng vẫn chậm”

Xmx không chữa:

- Lock contention.
- Database/network I/O.
- CPU throttling.
- Memory leak.
- Over-allocation causing GC CPU even with plenty of heap.
- Slow startup class loading/JIT when heap không phải bottleneck.

Dùng JFR, request tracing, profiler và metrics thích hợp để phân biệt.

## 20. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`-Xms` là dung lượng objects đã dùng.” | Xms thiết lập initial heap, không phải current used |
| “`-Xmx` là RAM tối đa của JVM process.” | Xmx là Java heap maximum; còn non-heap/native |
| “Đặt Xmx 2 GiB có nghĩa JVM dùng 2 GiB ngay startup.” | Có thể chỉ reserve/commit một phần tùy settings |
| “`-Xms=Xmx` chắc chắn khiến RSS bằng Xmx ngay.” | Cần xét commit/touch/OS/GC mapping |
| “Heap used, committed, RSS là một.” | Khác metric và accounting scopes |
| “Heap đủ lớn thì không thể OOMKilled.” | Native/cgroup memory vẫn có thể vượt limit |
| “Xmx càng lớn thì pauses luôn càng ngắn.” | GC frequency/pauses/CPU trade-off phụ thuộc collector |
| “Xmx càng nhỏ thì CPU luôn giảm.” | GC pressure có thể tăng |
| “Cùng Xmx nghĩa cùng GC behavior.” | GC, Xms, live set, CPU và VM ergonomics còn khác |
| “Xms nhỏ luôn có startup tốt.” | Allocation/heap expansions có thể gây overhead |
| “Xms lớn luôn tốt cho throughput.” | Footprint/startup/memory contention có thể xấu |
| “`AlwaysPreTouch` luôn giảm latency.” | Có thể chỉ tăng startup and RSS nếu không cần |
| “Volatile/heap size liên quan trực tiếp nhau.” | Đồng bộ bộ nhớ/JMM khác heap capacity |
| “`MaxRAMPercentage` vẫn override explicit Xmx.” | Explicit heap sizing thường có precedence trong HotSpot |
| “`MinRAMPercentage` là initial/minimum heap %.” | Nó tham gia maximum ergonomic sizing cho bộ nhớ thấp |
| “Kubernetes request chính là cgroup memory limit.” | Requests phục vụ scheduling; limits mới là cap thường gặp |
| “`-Xmx` có thể truyền sau `-jar`.” | Sau `-jar` là application arguments |
| “`System.gc()` là cách đáng tin để đo Xms/Xmx.” | GC scheduling không tạo heap sizing đúng và có overhead |
| “OOMKilled 137 chắc chắn là heap OOME.” | Có thể do native/cgroup/signal; cần kiểm chứng events |
| “Used tăng liên tục một lúc chắc chắn memory leak.” | Có thể GC chưa chạy hoặc live workload tăng hợp lệ |
| “Heap dump không cần bảo mật.” | Có thể chứa secrets/PII/session state |
| “Một lần đo startup có thể chọn Xms tối ưu.” | Cần nhiều runs, workload/GC/CPU equivalent |
| “Một tỷ lệ Xmx/container chuẩn cho mọi ứng dụng.” | Native footprint và workload rất khác nhau |

## 21. Bài tập tự kiểm tra có đáp án

**Bài 1.** `-Xms256m -Xmx1g` nghĩa là ứng dụng tạo sẵn 256 MiB business objects?  
**Đáp án:** Không. Xms điều khiển initial heap sizing, còn used objects phụ thuộc execution.

**Bài 2.** `-Xmx1g` có giới hạn tổng RSS tiến trình không?  
**Đáp án:** Không. Metaspace, code cache, thread stacks, direct buffers, native memory nằm ngoài heap.

**Bài 3.** Committed heap lớn hơn used heap có bất thường không?  
**Đáp án:** Không. Committed capacity có thể chứa free space cho allocations tiếp theo.

**Bài 4.** Tại sao không đặt Xmx đúng bằng container limit?  
**Đáp án:** Vì process còn non-heap/native/OS-accounted memory, có nguy cơ cgroup OOM.

**Bài 5.** `-Xms2g -Xmx1g` có hợp lệ không?  
**Đáp án:** Không trên HotSpot; initial không được vượt max heap.

**Bài 6.** `-Xms1g -Xmx1g` có bảo đảm OS RSS 1 GiB ngay tại startup không?  
**Đáp án:** Không. Commit, touch và OS mapping khác nhau; cần đo.

**Bài 7.** `-XX:+AlwaysPreTouch` tác động chủ yếu vào giai đoạn nào?  
**Đáp án:** Chạm heap pages đã commit ở startup, tăng upfront cost và có thể giảm page-fault work khi dùng sau.

**Bài 8.** Nếu tăng Xmx, memory leak có hết không?  
**Đáp án:** Không. Nếu có unbounded retention, leak vẫn tồn tại, thường chỉ chậm OOM hơn.

**Bài 9.** Tăng Xms nhưng giữ Xmx có thể cải thiện điều gì?  
**Đáp án:** Giảm nhu cầu heap expansion/initial pressure trong một số workload, đổi lại footprint/startup cost.

**Bài 10.** Giảm Xmx có thể làm frequency GC tăng không?  
**Đáp án:** Có; mức độ phụ thuộc live set, allocations, collector và heuristics.

**Bài 11.** `MaxRAMPercentage` có áp khi explicit `-Xmx` đã được truyền trên HotSpot không?  
**Đáp án:** Thông thường không quyết định Xmx nữa; explicit max heap option được ưu tiên.

**Bài 12.** `MinRAMPercentage` là phần trăm tối thiểu của heap ban đầu?  
**Đáp án:** Không. Nó liên quan maximum heap ergonomics trên hệ thống RAM nhỏ.

**Bài 13.** `java -jar app.jar -Xmx512m` có thật sự cấu hình heap không?  
**Đáp án:** Thường không; đó là application argument do vị trí sau `-jar`.

**Bài 14.** Trong `HeapSizingDemo`, payload arrays tổng bao nhiêu bytes?  
**Đáp án:** **8.388.608 bytes**, vì 64 × 128 KiB.

**Bài 15.** Checksum của `HeapSizingDemo` là gì?  
**Đáp án:** **2016**, tổng 0..63.

**Bài 16.** Hai cấu hình Xms khác nhau có làm stdout logic demo khác không?  
**Đáp án:** Không khi chạy thành công; timing và runtime heap metrics có thể khác.

**Bài 17.** `HeapPressureDemo` giữ bao nhiêu arrays và checksum?  
**Đáp án:** **32 arrays**, checksum **528**.

**Bài 18.** ZGC trên JDK 17 có thể trả heap pages chưa dùng về OS không?  
**Đáp án:** Có trên build hỗ trợ, theo `ZUncommit`; không uncommit xuống dưới Xms.

**Bài 19.** Với ZGC, Xms=Xmx ảnh hưởng uncommit thế nào?  
**Đáp án:** Vô hiệu hóa khả năng trả unused heap về OS theo cơ chế uncommit của ZGC.

**Bài 20.** `SoftMaxHeapSize` là hard limit?  
**Đáp án:** Không. Soft target có thể được vượt khi cần, còn Xmx là hard maximum heap.

**Bài 21.** Pod bị OOMKilled nhưng heap used chưa tới Xmx. Cần xem gì?  
**Đáp án:** RSS/cgroup memory, native/metaspace/direct/threads, GC/native allocations, pod/OS events.

**Bài 22.** G1 có cam kết giữ mọi pause dưới `MaxGCPauseMillis` không?  
**Đáp án:** Không. Đó là ergonomic target, không phải hard deadline.

**Bài 23.** Một phép đo heap used tăng trong 5 phút chứng minh leak?  
**Đáp án:** Không; cần live-set/retained-path trends qua collections và workloads tương đương.

**Bài 24.** Nếu startup là KPI chính, fixed large Xms + AlwaysPreTouch có thể gây bất lợi gì?  
**Đáp án:** Tăng startup work/memory commitment và RSS sớm, nhất là khi workload nhẹ.

**Bài 25.** Bạn muốn thay Xmx từ 512m thành 768m; giữ Xms hay đổi cả hai?  
**Đáp án:** Để cô lập tác động Xmx, trước hết giữ Xms, collector, workload và CPU/memory budget tương tự; kiểm tra headroom container rồi A/B.

## 22. Checklist tuning heap có trách nhiệm

- [ ] Xác định đúng HotSpot/JVM implementation, vendor, JDK version/build.
- [ ] Biết Xms, Xmx **thực sự có hiệu lực** (không chỉ trong YAML).
- [ ] Phân biệt initial, used, committed, max, virtual reserve, RSS và cgroup usage.
- [ ] Đã kiểm tra container memory **limits** và CPU quotas?
- [ ] Đã tính non-heap: metaspace, code cache, direct buffers, thread stacks, JNI, GC metadata?
- [ ] Có baseline live set ở nhiều workload phases, nhất là peak traffic?
- [ ] Có đo allocation rate và headroom cho bursts/collector?
- [ ] Có biết GC đang dùng (Serial/Parallel/G1/ZGC/...)?
- [ ] Có log GC events/pauses, heap occupancy trước/sau GC?
- [ ] Có đánh giá latency p99, throughput và error rates?
- [ ] Có thử Xms thay đổi **riêng** khỏi Xmx để cô lập tác động?
- [ ] Có thử Xmx thay đổi **riêng** khỏi GC choice?
- [ ] Có thử startup với/không AlwaysPreTouch khi KPI yêu cầu?
- [ ] Nếu fixed heap, đã kiểm tra idle memory/host density chưa?
- [ ] Nếu Xmx lớn gần memory limit, đã test native headroom và peak cgroup memory?
- [ ] Nếu OOMKilled, đã xem Kubernetes events/cgroup/OS logs?
- [ ] Nếu heap OOME, đã xem retained-path evidence và application object lifecycles?
- [ ] Có security/retention policy khi dump heap/thu diagnostic artifacts?
- [ ] Có nhiều A/B runs cùng inputs/JDK/container constraints?
- [ ] Có rollback criteria cho thay đổi sizing khi p99 hoặc memory xấu hơn?

## 23. Tóm tắt và quy tắc quyết định

```text
- Xms = initial heap sizing
- Xmx = maximum Java heap sizing
- used ≠ committed ≠ reserved ≠ RSS ≠ cgroup usage

Đặt Xms thấp:
  có thể nhẹ footprint/startup
  nhưng VM có thể resize/commit thêm khi tải lên

Đặt Xms cao hoặc Xms=Xmx:
  có thể giảm resizing/churn
  nhưng giữ footprint lớn hơn, nhất là khi pre-touch

Đặt Xmx quá thấp:
  nhiều GC / allocation stalls / heap OOME

Đặt Xmx quá cao gần RAM/container cap:
  native headroom thiếu / OOMKilled / cạnh tranh bộ nhớ

Mục tiêu:
  đủ heap cho live data + allocation bursts + GC
  và đủ native/container headroom cho process
```

**Không có kích thước heap tốt nhất trong mọi trường hợp.** Giá trị tốt được xác định bằng workload, GC, startup/latency SLO, native footprint và khả năng quản lý tài nguyên của OS/container. Bắt đầu từ thiết lập có căn cứ, đo các đại lượng đúng tên, thay **một biến mỗi lần** và chỉ giữ thay đổi khi benefit đủ mạnh, không làm rủi ro OOM/latency xấu đi.

### Nguồn tham khảo

1. **Oracle JDK 17 — `java` command, `-Xms` / `-Xmx` / `AlwaysPreTouch` / RAM percentages:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
2. **Oracle JDK 17 — Garbage Collection Tuning Guide:** https://docs.oracle.com/en/java/javase/17/gctuning/
3. **Oracle JDK 17 — Z Garbage Collector, heap sizing và uncommit:** https://docs.oracle.com/en/java/javase/17/gctuning/z-garbage-collector1.html
4. **Java SE 17 — `MemoryUsage` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html
5. **Java SE 17 — `MemoryMXBean` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html
6. **Oracle JDK 17 — `jcmd` diagnostic command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
7. **Oracle JDK 17 — Native Memory Tracking:** https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html
8. **Inside Java — How ZGC allocates memory for Java heap (2025):** https://inside.java/2025/04/17/zgc-deep-dive/
9. **Inside Java — ZGC `SoftMaxHeapSize`:** https://inside.java/2020/07/02/zgc-softmaxheapsize/
10. **Red Hat — Java 17 container awareness and RAM percentage flags:** https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness
11. **AWS — JVM memory/CPU/container recommendations (2026):** https://aws.amazon.com/blogs/containers/jvm-memory-cpu-and-classpath-best-practices-for-java-containers-on-aws/

**Bài học cốt lõi:** `-Xms` quyết định điểm bắt đầu của heap, `-Xmx` quyết định hard ceiling của Java heap; chúng điều chỉnh cân bằng **resizing/GC/startup/footprint**, nhưng không thay thế việc đo **used vs committed vs RSS** và dành bộ nhớ cho toàn bộ JVM process.