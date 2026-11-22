# Phân biệt bộ nhớ máy chủ, giới hạn container và Java heap trong ứng dụng Java 10+

## 1. Ba con số khác nhau, ba câu hỏi khác nhau

Khi đưa ứng dụng Java vào Docker hoặc Kubernetes, rất dễ thấy các con số như:

- Máy chủ Linux có **16 GiB RAM**.
- Container được đặt **memory limit = 1 GiB**.
- JVM được cấu hình **`-Xmx640m`**.

Ba con số **không phải ba cách đo cùng một vùng bộ nhớ**:

1. **Bộ nhớ máy chủ (host physical memory):** tổng RAM vật lý của máy chạy workload; nó được chia sẻ giữa hệ điều hành, nhiều container và các tiến trình khác.
2. **Giới hạn bộ nhớ container:** giới hạn áp dụng bởi **Linux cgroups** cho một nhóm tiến trình, thường bao gồm phần bộ nhớ có thể bị tính phí cho Java heap, native memory, file cache và các thành phần khác.
3. **Java heap:** vùng do JVM quản lý để cấp phát phần lớn Java objects và arrays; mức **tối đa** thường được điều khiển bằng `-Xmx` hoặc được JVM tính qua các tùy chọn ergonomics như `-XX:MaxRAMPercentage`.

**Ví dụ:**

```text
Host RAM = 16 GiB
+-------------------------------------------------------------+
| Hệ điều hành, kernel, tiến trình và các container khác      |
|                                                             |
|       Container (memory limit = 1 GiB)                      |
|       +-----------------------------------------------+     |
|       | Java process:                                |     |
|       |   Java heap tối đa = 640 MiB (-Xmx640m)      |     |
|       |   Metaspace, code cache, thread stacks       |     |
|       |   Native libraries, direct buffers, GC...    |     |
|       |                                               |     |
|       | Các khoản khác trong cgroup: cache, kernel,   |     |
|       | tiến trình phụ / thành phần được tính phí     |     |
|       +-----------------------------------------------+     |
+-------------------------------------------------------------+
```

**Không suy ra rằng JVM được dùng đủ 16 GiB chỉ vì host có 16 GiB.** Nếu cgroup hard limit chỉ 1 GiB, nó có thể gây reclaim hoặc OOM-kill khi mức sử dụng trong phạm vi cgroup vượt giới hạn theo điều kiện kernel.

**Cũng không suy ra rằng `-Xmx640m` là “giới hạn RAM của JVM”.** Nó giới hạn **Java heap**, nhưng JVM còn cấp phát nhiều loại bộ nhớ ngoài heap.

> Quy tắc nhớ: **Host RAM ≠ cgroup memory limit ≠ Java heap max ≠ Java heap used ≠ process RSS**.

Đây là kiến thức trọng tâm của chủ đề **Bộ nhớ trong container** trong module Java 10. Java 10 đưa vào cơ chế container awareness mặc định của HotSpot trên nền tảng hỗ trợ; các hướng dẫn ở đây tập trung vào API và cơ chế **vẫn còn hiệu lực trong JDK hiện đại**. Hỗ trợ **cgroup v2** đến ở các JDK mới hơn Java 10, nên phải kiểm phiên bản runtime thực tế.

## 2. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt host RAM, giới hạn cgroup, JVM heap max và bộ nhớ đang dùng.
2. Giải thích tại sao `-Xmx` không phải memory limit của cả container.
3. Kể tên các vùng bộ nhớ ngoài Java heap có thể làm tiến trình tăng RAM.
4. Đọc những khái niệm `reserved`, `committed`, `used`, `free` và `max`.
5. Hiểu HotSpot `-XX:+UseContainerSupport` trong môi trường Linux hỗ trợ.
6. Phân biệt `-Xmx`, `-Xms`, `-XX:MaxRAMPercentage` và `-XX:MaxRAM`.
7. Biết khác nhau giữa cgroups v1 và v2; đọc `memory.max`/`memory.current`/`memory.events` khi đúng môi trường.
8. Nhận diện tính phân cấp của cgroup: giới hạn tại parent cũng có thể chi phối child.
9. Hiểu `memory request` và `memory limit` của Kubernetes không giống nhau.
10. Phân biệt `java.lang.OutOfMemoryError` do JVM ném với container **OOMKilled** bởi hệ điều hành.
11. Hiểu tại sao hệ điều hành có thể giết JVM dù heap chưa đạt `-Xmx`.
12. Dùng `Runtime`, `MemoryMXBean` và công cụ JVM để xem bộ nhớ heap.
13. Dùng `-XshowSettings:vm`, `-XshowSettings:system`, `-Xlog:os+container=trace` theo nền tảng.
14. Sử dụng `jcmd VM.native_memory` với điều kiện bật Native Memory Tracking.
15. Thiết kế budget bộ nhớ có headroom cho native/non-heap, page cache và tải đột biến.
16. Kiểm thử một ví dụ Java 17+ độc lập mà không cần Docker trên máy cá nhân.
17. Biết giới hạn của các số đo RSS, NMT, heap usage và cgroup usage.
18. Có checklist điều tra sự cố memory trong container thay vì chỉ tăng `-Xmx`.

## 3. Bộ nhớ máy chủ là gì?

**Host RAM** là tài nguyên vật lý mà hệ điều hành có thể quản lý cho mọi workload trên một node. Khi xem thông số máy chủ:

```bash
free -h
cat /proc/meminfo
```

trên Linux, bạn quan sát góc nhìn về bộ nhớ hệ điều hành. Những con số này **không tự chứng minh** phần RAM mà một container cụ thể được phép tiêu thụ.

Nếu node có 16 GiB và đang chạy 10 container, một container không mặc nhiên được dùng tới 16 GiB. Các container khác, hệ điều hành, kernel caches và các tiến trình ngoài container đều có thể tiêu thụ RAM.

### Vì sao `free -h` bên trong container dễ gây hiểu lầm?

Trong nhiều môi trường, `/proc/meminfo` và các công cụ đọc nó vẫn có thể phản ánh **host-level memory**, thay vì hard limit của cgroup chứa tiến trình. Một shell bên trong container có thể hiển thị “16 GiB total” ngay khi container bị giới hạn 1 GiB.

Do đó:

- Muốn biết **RAM của host**: dùng thông tin node hoặc OS metrics.
- Muốn biết **memory limit thật của workload**: kiểm container/orchestrator và cgroup tương ứng.
- Muốn biết **Java heap max**: kiểm JVM settings và `Runtime.getRuntime().maxMemory()`.
- Muốn biết **process resident footprint**: dùng RSS/PSS từ OS metrics, không lấy `Runtime.maxMemory()` thay thế.

### Không phải mọi host đều có một mức RAM “sẵn cho container”

Kernel còn quản lý reclaim, swap, huge pages, memory pressure và ưu tiên cgroups. Giới hạn cgroup là một rào tài nguyên; nó **không bảo đảm** rằng đúng lượng RAM đó đang trống vật lý trên host tại mọi thời điểm. Một node đang áp lực memory có thể ảnh hưởng latency, reclaim và OOM policy ngay cả khi container chưa dùng hết hạn mức của mình.

## 4. Giới hạn container thực chất là giới hạn cgroup

Trên Linux, **cgroups** nhóm tiến trình theo một hệ thống phân cấp, có thể giới hạn và theo dõi tài nguyên. Docker và Kubernetes sử dụng cơ chế này để áp dụng chính sách cho container và workload.

**Container memory limit** thường không phải giá trị JVM tự đặt. Đó là giới hạn do platform ghi vào các tệp hoặc cấu hình **memory controller** của cgroup.

### Với cgroup v2

Các interface quan trọng:

| Tệp | Ý nghĩa |
| --- | --- |
| `memory.max` | Hard limit của memory controller; `max` nghĩa là không đặt hard limit tại cgroup đó |
| `memory.current` | Tổng memory hiện đang được tính phí cho cgroup **và các descendants** |
| `memory.peak` | Mức memory cực đại được ghi nhận; khả năng reset/phạm vi phụ thuộc interface |
| `memory.high` | Ngưỡng gây reclaim/throttling; **không tự là OOM-kill hard limit** |
| `memory.events` | Các bộ đếm áp lực bộ nhớ, `high`, `max`, `oom`, `oom_kill`... |
| `memory.events.local` | Event counters cục bộ của cgroup hiện tại |
| `memory.stat` | Thành phần bộ nhớ đang bị tính phí, ví dụ `anon`, `file`, `kernel` |
| `memory.swap.current` / `memory.swap.max` | Theo dõi và giới hạn swap theo cơ chế riêng |

Theo tài liệu Linux kernel, `memory.max` là **hard memory limit**. Khi memory usage tới ngưỡng và không giảm được nhờ reclaim theo điều kiện kernel, **OOM killer** của cgroup có thể được gọi.

### `memory.max` là số byte, không phải MiB

Ví dụ file chứa:

```text
1073741824
```

thì đây là `1,073,741,824` byte = **1 GiB = 1.024 MiB**, không phải 1.073.741.824 MB.

Nếu chứa:

```text
max
```

thì cgroup **đó** không đặt hard limit; nhưng **ancestor cgroup** vẫn có thể có limit, và host vẫn có giới hạn vật lý. Không diễn giải `max` là “vô hạn RAM thực tế”.

### Khi cgroup v1

Những đường dẫn thường thấy trong mount layout tương ứng:

```text
memory.limit_in_bytes
memory.usage_in_bytes
memory.failcnt
memory.stat
```

Tuy nhiên đường dẫn mount và cách phân cấp khác nhau theo distro/runtime. Không hardcode rằng mọi hệ thống Linux mới có tệp tại `/sys/fs/cgroup/memory/memory.limit_in_bytes`: cgroup v2 có interface khác và mount namespace của container có thể khác.

**Giữ kiến thức hiện hành:** cgroup v1 có thể vẫn tồn tại trên một số môi trường, nhưng không nên dùng hướng dẫn v1 như cấu hình mặc định của Linux hiện đại. Bài dùng v2 để giải thích chính và nhắc v1 để đọc hệ thống đang chạy đúng.

## 5. Cgroup là phân cấp, không phải nhãn “container” đơn lẻ

Một cây cgroup có thể trông như:

```text
Parent workload / slice        memory.max = 2 GiB
   |
   +-- Pod hoặc service group  memory.max = 1 GiB
          |
          +-- Java container   memory.max = max
          |
          +-- Helper process/container (nếu thuộc cùng parent)
```

Nếu child ghi `memory.max=max`, nó **không được quyền phá giới hạn 1 GiB** ở parent. Linux kernel xác định giới hạn và accounting theo **phân cấp**, nên effective memory budget có thể nhỏ hơn một số bạn đọc tại node cgroup hiện tại.

Cần phân biệt **ba phạm vi**:

1. **JVM process:** một process với heap/native/thread stacks và các mappings riêng.
2. **Container cgroup:** có thể chứa một hoặc nhiều process; accounting không chỉ là Java process.
3. **Parent cgroup / Pod / service:** có thể thêm ràng buộc chung theo cách runtime/orchestrator cấu hình.

**Không phải lúc nào Pod cgroup và container cgroup đều trùng nhau.** Nếu cần giải thích một memory event chính xác, phải xem **cgroup thực tế của PID JVM**, ancestor limits và event counters trên đúng nhánh.

### Vì sao điều này ảnh hưởng việc chọn `-Xmx`?

Giả sử JVM nhìn thấy một giới hạn nhưng parent có hạn mức thấp hơn hoặc có tiến trình khác tiêu thụ đáng kể, budget thực tế cho heap vẫn có thể nhỏ hơn dự đoán. Tính năng container awareness giúp JVM đọc các giới hạn được hỗ trợ, **không phải giấy phép vượt các ràng buộc phân cấp, RAM host hoặc các tiến trình khác**.

## 6. Java heap: một phần của bộ nhớ JVM

Java heap là vùng runtime cấp phát đa số instance/array Java. JVM có thể quản lý nó bằng các garbage collectors như G1, ZGC, Parallel GC tùy cấu hình.

```bash
java -Xms128m -Xmx640m -jar app.jar
```

Trong lệnh ví dụ:

- `-Xms128m`: cấu hình **initial Java heap size** khoảng 128 MiB theo đơn vị JVM.
- `-Xmx640m`: đặt **maximum Java heap size** ở mức 640 MiB.
- **Không cờ nào đặt hard limit của toàn process**, càng không đặt container cgroup limit.
- Các khoản metaspace, JIT code cache, thread stacks, direct/native buffers vẫn tồn tại bên ngoài phạm vi heap mà `-Xmx` giới hạn.

`-Xmx` cũng không có nghĩa JVM **ngay lập tức dùng 640 MiB RAM vật lý**. JVM có thể reserve address space, commit các vùng cần thiết và chạm physical pages theo nhu cầu collector/flags.

### Java heap bao gồm những gì?

Ví dụ:

- Đối tượng tạo bằng `new`.
- Phần lớn array Java như `byte[]`.
- Nhiều object của collections, domain model, JSON parser.
- Một số backing objects và cấu trúc trung gian mà thư viện cấp phát trên heap.

Cẩn thận với một số object đại diện cho **bộ nhớ ngoài heap**: bản thân object Java của `ByteBuffer.allocateDirect(...)` có thể có metadata trên heap, nhưng vùng bytes trực tiếp do nó quản lý thuộc **native/direct memory**.

### Java heap không phải mọi “memory của Java”

Một ứng dụng Java có thể bị container OOM-kill khi heap dùng ít, nếu:

- Có nhiều thread và stack allocations.
- JIT code cache/metaspace tăng.
- JNI hoặc native library dùng rất nhiều memory.
- Direct buffers hoặc memory-mapped files gây áp lực memory.
- File/page cache, kernel memory hay process khác trong cgroup cùng chiếm tài nguyên.

Vì vậy việc chỉ xem heap usage trong dashboard **không đủ** để khẳng định toàn container còn nhiều RAM.

## 7. Reserved, committed, used, free và max khác nhau thế nào?

Các từ thường xuất hiện trong JVM metrics:

| Tên | Diễn giải |
| --- | --- |
| **Reserved** | Khoảng **địa chỉ ảo** JVM dành riêng cho một vùng, không phải toàn bộ đã dùng RAM vật lý |
| **Committed** | Phần vùng nhớ được cam kết theo hợp đồng JVM/OS, có khả năng được backing khi truy cập; không đồng nghĩa toàn bộ là private RSS |
| **Used** | Dung lượng đang được báo sử dụng trong vùng JVM tương ứng; đối với heap có thể còn object rác chưa GC |
| **Free within committed heap** | Khoảng trống theo accounting JVM trong heap đang có; không phải RAM host còn trống |
| **Max heap** | Cận trên heap mà JVM sẽ cố tuân thủ; không phải memory.current của cgroup |
| **RSS (resident set size)** | Số trang bộ nhớ của process đang resident theo OS; có thể gồm shared mappings và không trực tiếp cộng được với một số khác |
| **Cgroup memory.current** | Tổng memory **được tính phí** cho cgroup theo Linux memory controller, gồm những thành phần ngoài một JVM |
| **Host available memory** | Chỉ số hệ điều hành về khả năng cấp phát trên host, không phải budget cgroup |

### Ví dụ về heap reporting

Giả sử một thời điểm:

```text
-Xmx (max)         640 MiB
Heap committed     256 MiB
Heap used          170 MiB
Heap free ~         86 MiB (trong committed)
```

Không thể từ đó suy ra “container chỉ đang dùng 170 MiB”. RSS còn có committed heap đã chạm trang, metaspace, stacks, JIT, direct buffers; cgroup có thể tính cả page cache và process khác.

**Phân biệt các phép trừ:**

- `committed - used` là phần heap trống theo accounting hiện tại, khi hai giá trị dùng cùng nguồn/định nghĩa.
- `max - used` không phải lượng RAM vật lý còn lại của container.
- `container limit - memory.current` cho biết **headroom tức thời** theo cgroup accounting (bỏ qua thay đổi động/reclaim/throttle), không đồng nghĩa còn heap trống có thể cấp phát tùy ý.

## 8. Ngoài Java heap còn có những loại bộ nhớ nào?

| Khoản | Ví dụ / diễn giải | Có bị `-Xmx` trực tiếp giới hạn không? |
| --- | --- | --- |
| **Metaspace** | Metadata class, method, classloader | **Không** |
| **Code cache** | Machine code do JIT tạo | **Không** |
| **Thread stacks** | Stack của các platform threads | **Không** |
| **GC/native VM structures** | Structures phục vụ collector/JVM runtime | **Không** |
| **Direct/native buffers** | `ByteBuffer.allocateDirect`, networking buffers | **Không** |
| **JNI và native library** | `malloc` bên ngoài heap, thư viện C/C++ | **Không** |
| **Memory-mapped files** | File-backed mappings có trang resident | **Không** |
| **Page cache / tmpfs** | Cached file pages, một số dữ liệu file trong memory controller | **Không** |
| **Kernel memory** | Page tables, kernel stacks, slab, socket buffers theo cgroup accounting | **Không** |
| **Process khác cùng cgroup** | Helper process, worker phụ thuộc vào packaging | **Không** |

**Một số loại có giới hạn riêng** như `-XX:MaxMetaspaceSize` hoặc `-XX:MaxDirectMemorySize`, nhưng đặt những cờ đó **không** khiến toàn process đột nhiên bị giới hạn ở `-Xmx`, và cũng không nên cấu hình chúng ngẫu nhiên chỉ để tránh OOM.

### MemoryMXBean non-heap không phải mọi native memory

`ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage()` chỉ báo **non-heap memory mà JVM quản lý/giám sát qua interface này**. Nó không phải một “tổng tuyệt đối mọi byte nằm ngoài heap”, không bao gồm tất cả native library allocations, page cache hay memory của tiến trình khác.

Do đó:

```text
Heap usage + Non-heap MemoryMXBean usage
             ≠ chắc chắn process RSS
             ≠ cgroup memory.current
```

Đây là lý do cần **nhiều tầng metrics** khi điều tra memory.

## 9. Một budget giả định: host 16 GiB, cgroup 1 GiB, heap 640 MiB

Giả sử một workload có:

| Khoản | Dung lượng giả định |
| --- | ---: |
| Host physical memory | 16.384 MiB |
| Container hard limit | 1.024 MiB |
| Maximum Java heap (`-Xmx`) | 640 MiB |
| JVM non-heap/native tiêu thụ ở peak giả định | 220 MiB |
| Các khoản cgroup khác tại peak giả định | 80 MiB |
| **Tổng được tính trong mô hình** | **940 MiB** |
| **Khoảng dư so với hard limit** | **84 MiB** |

Phép tính:

```text
1.024 MiB (container memory limit)
- 640 MiB (heap giả định đã sử dụng tối đa)
- 220 MiB (JVM memory ngoài heap, giả định)
-  80 MiB (các khoản cgroup khác, giả định)
=  84 MiB headroom
```

**Đây là minh họa thiết kế**, không phải một phép đo trên Docker/Kubernetes; các khoản phải **không trùng lặp** trong mô hình. Không lấy một RSS đã bao gồm heap rồi cộng lại với `-Xmx`, vì sẽ **double-count**.

Nếu tăng heap tối đa lên **960 MiB** mà giữ các khoản khác:

```text
960 + 220 + 80 = 1.260 MiB > 1.024 MiB
```

Mô hình trở nên **không đủ budget khi các khoản cùng đạt peak** dù heap 960 MiB vẫn **nhỏ hơn** host RAM 16 GiB.

**Không khẳng định một heap 640 MiB luôn an toàn với container 1 GiB.** Headroom 84 MiB có thể quá thấp nếu JIT, direct buffers, thread stacks hoặc cache tăng mạnh. Budget thực tế phải dựa vào **peak/percentile workload đo được** và margin cho đột biến.

### Một hệ quả không hiển nhiên

Một quy trình chỉ nhìn host memory có thể đề xuất `-Xmx8g` vì máy có 16 GiB. Trong container 1 GiB, đó là cách sizing nguy hiểm ngay cả khi JVM khởi động được: việc thực sự sử dụng heap gần 8 GiB sẽ xung đột với hạn mức cgroup.

Ngược lại, heap có `-Xmx640m` không có nghĩa JVM được bảo đảm sử dụng 640 MiB: các khoản khác có thể chiếm budget trước.

## 10. Vì sao Java 10 quan trọng: HotSpot nhận diện container

Trước khi JVM có container awareness phù hợp, các **ergonomic defaults** về kích thước heap và số processor có thể dựa vào tài nguyên host thay vì giới hạn container.

**Java 10** đưa vào hỗ trợ nhận diện Docker/cgroup resource constraints của HotSpot trên nền tảng được hỗ trợ. Cơ chế được bật mặc định khi thích hợp qua flag:

```text
-XX:+UseContainerSupport
```

Tài liệu launcher **JDK 26** mô tả `UseContainerSupport` cho **Linux**, bật mặc định trong môi trường hỗ trợ; vô hiệu hóa bằng:

```text
-XX:-UseContainerSupport
```

**Không dùng flag vô hiệu hóa như cách sửa memory trong container.** Nếu tắt nó, JVM có thể lấy host resources làm cơ sở cho ergonomic sizing và có nguy cơ chọn heap/GC threads không phù hợp cgroup.

### Cgroup v1 và v2 là vấn đề khác với “Java 10 đã container-aware”

Hỗ trợ đầu tiên của Java 10 tập trung vào cgroup khả dụng thời điểm đó. **Cgroup v2** được đưa vào HotSpot dòng JDK chính từ **JDK 15**, rồi được backport sang các dòng JDK được bảo trì khác. Không được mặc định **JDK 10 nguyên gốc** hiểu đầy đủ cgroup v2 của Linux mới.

Vì vậy trên môi trường vận hành thực:

1. Kiểm **JDK release, update và vendor build**.
2. Kiểm cgroup v1 hay v2.
3. Kiểm JVM có nhận ra đúng memory controller không.
4. Đọc log container detection hoặc launcher settings.
5. Quan sát memory limits và heap max thực tế trước khi tuning.

Cùng một tag “Java 11” nhưng các bản update cũ/mới có khả năng hỗ trợ cgroups khác nhau. Không dùng version number feature duy nhất để suy luận đầy đủ khả năng container detection.

## 11. `-Xmx` so với `-XX:MaxRAMPercentage`

Có hai cách phổ biến để đặt maximum heap:

### Cách A — đặt mức tuyệt đối

```bash
java -Xms128m -Xmx640m -jar app.jar
```

Ưu điểm: hợp đồng heap max rõ ràng, dễ dự tính và audit. Nhược điểm: khi chạy cùng image trên container có nhiều limit khác nhau, mức 640 MiB không tự thay đổi.

### Cách B — dùng tỷ lệ theo memory mà JVM dùng làm cơ sở

```bash
java -XX:MaxRAMPercentage=60.0 -jar app.jar
```

Trên **HotSpot Linux container-aware**, nếu JVM phát hiện đúng container limit ~1 GiB thì mức mục tiêu tính theo tỷ lệ thường gần **60% của cơ sở memory** (khoảng 614,4 MiB trước các điều chỉnh ergonomic). Kết quả cuối có thể khác do rounding, compressed references, GC, kích thước nhỏ, flag khác hoặc các giới hạn JVM.

**Không khẳng định `MaxRAMPercentage=60.0` luôn tạo heap chính xác 614.400.000 bytes.** Phần trăm tác động tới **quá trình ergonomics xác định heap max**, không phải hard limit độc lập của cgroup hay tổng RSS.

### So sánh nhanh

| Đặc tính | `-Xmx640m` | `-XX:MaxRAMPercentage=60.0` |
| --- | --- | --- |
| Đơn vị | Mức byte/memory size | Tỷ lệ % trên cơ sở memory của JVM |
| Thích hợp | Container có size cố định, cấu hình minh bạch | Image dùng cho nhiều memory limits |
| Tự thích nghi khi container limit đổi lúc JVM khởi động? | Không | Có thể, nếu detection và ergonomics hỗ trợ |
| Tự bảo đảm tránh OOMKilled? | Không | Không |
| Có tính native memory vào heap limit? | Không | Không |
| Cần kiểm giá trị max heap thực tế? | Có | **Càng cần** |

Nếu đồng thời cấu hình `-Xmx` và một tỷ lệ max, **`-Xmx` là lựa chọn đặt mức heap tối đa tường minh**; không kỳ vọng hai cờ tạo ra hai “hàng rào bộ nhớ” cộng dồn. Tránh cấu hình chồng chéo khi không có lý do rõ ràng.

### `-XX:MaxRAM` không phải giới hạn container

`-XX:MaxRAM` có thể thay đổi **giá trị memory cơ sở mà JVM dùng để tính heap ergonomics**. Nó không ghi lại `memory.max` và không tạo hard memory limit cấp kernel. Nếu cgroup thực sự giới hạn 1 GiB, việc truyền một `MaxRAM` lớn hơn không nâng được hạn mức cgroup.

## 12. `-Xms` và committed heap: đừng nhầm initial với maximum

`-Xms` điều chỉnh initial heap size; `-Xmx` điều chỉnh upper bound của heap.

Ví dụ:

```bash
java -Xms128m -Xmx640m -jar app.jar
```

JVM có thể mở rộng hoặc điều chỉnh committed heap theo collector và workload. Cần phân biệt:

- **Initial heap / reserved virtual address space**.
- **Heap committed hiện tại**.
- **Heap used** (gồm cả rác chưa thu gom).
- **Physical resident pages** của process.

Một số GC và flags (ví dụ `-XX:+AlwaysPreTouch` trên HotSpot) có thể làm nhiều pages được chạm sớm, ảnh hưởng RSS/startup. Vì vậy không thể khẳng định “`-Xms640m -Xmx640m` chỉ là khai báo, hoàn toàn không ảnh hưởng tài nguyên thực tế”.

**Không tự động đặt `-Xms=-Xmx` chỉ vì chạy trong container.** Cấu hình đó có trade-off startup, commit, resident memory và GC ergonomics. Cần đo theo mục tiêu sản phẩm.

## 13. Chỉ số từ `Runtime.getRuntime()`

Java cung cấp API sẵn có:

```java
Runtime r = Runtime.getRuntime();

long maxHeap = r.maxMemory();
long currentTotal = r.totalMemory();
long freeWithinCurrentTotal = r.freeMemory();

long usedEstimate = currentTotal - freeWithinCurrentTotal;
```

Theo ý nghĩa API:

- `maxMemory()`: upper bound Java heap mà JVM sẽ cố sử dụng; trên một số JVM có thể là `Long.MAX_VALUE` nếu không có giới hạn.
- `totalMemory()`: tổng memory hiện được báo trong JVM heap (thường tương ứng committed heap theo khái niệm JVM).
- `freeMemory()`: memory trống **trong phần heap hiện có** theo định nghĩa JVM.
- `totalMemory()-freeMemory()`: ước lượng heap memory đang dùng theo API.
- `maxMemory()` **không phải** RAM host, cgroup limit, RSS, total process memory hay remaining memory.

**Sai lầm thường gặp:**

```java
// Sai về ý nghĩa:
long containerFree = Runtime.getRuntime().maxMemory()
                   - Runtime.getRuntime().freeMemory();
```

Phép trừ này không đo container remaining RAM. Nó còn trộn **maximum heap** với **free memory trong total heap hiện tại**, nên không phải số “heap used” đúng.

Muốn ước tính heap used bằng Runtime, dùng `totalMemory() - freeMemory()` cùng thời điểm; và vẫn hiểu đó không phải process RSS.

## 14. `MemoryMXBean`: used, committed và max của heap

API tiêu chuẩn:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryUsage heap =
        ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

System.out.println(heap.getUsed());
System.out.println(heap.getCommitted());
System.out.println(heap.getMax());
```

`MemoryUsage` phân biệt:

- `getInit()`: initial size, hoặc `-1` nếu không xác định.
- `getUsed()`: lượng đang dùng theo accounting memory pool.
- `getCommitted()`: lượng JVM đã committed cho memory pool.
- `getMax()`: upper limit, hoặc `-1` nếu không xác định.

**Heap used có thể bao gồm đối tượng đã chết nhưng GC chưa thu hồi.** Không dùng một snapshot heap used để kết luận bao nhiêu đối tượng còn reachable hay một leak đã tồn tại.

API khác:

```java
MemoryUsage nonHeap =
        ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage();
```

`nonHeap` hữu ích cho những JVM-managed non-heap pools nhưng **không** là tổng mọi native allocation, và không thay thế NMT hay cgroup metrics.

### Vì sao API Java không tự cho biết hard limit của container?

`Runtime.maxMemory()` và `MemoryMXBean.getHeapMemoryUsage()` được thiết kế cho **heap**, không cung cấp một Java SE API chuẩn với hợp đồng “trả đúng memory.max của cgroup đang chứa PID này, đã xét tổ tiên, swap và orchestrator”.

Do đó, để chẩn đoán container cần kết hợp:

- JVM APIs → **heap behavior**.
- HotSpot diagnostics → **JVM internal/native allocation**.
- Linux cgroup metrics → **hard limit và usage trong scope cgroup**.
- Orchestrator/container status → **memory limit khai báo, OOMKilled, restart/events**.

## 15. Kiểm giá trị mà JVM đang dùng khi khởi động

Trên runtime hỗ trợ, chạy:

```bash
java -XshowSettings:vm -version
```

Launcher có thể in **Max. Heap Size** ước lượng và runtime information. Đây là thông tin do **JVM đang chạy** báo, không phải số bạn tự dự đoán bằng 25% RAM host.

Để xem operating system/container metrics khi platform hỗ trợ:

```bash
java -XshowSettings:system -version
```

Một JVM Linux có hỗ trợ cgroups có thể cho thấy provider, effective memory limit/processor counts. Tuy nhiên, trên một số nền tảng (ví dụ **Windows JDK 24 trong lab**) lệnh có thể báo:

```text
Operating System Metrics:
    No metrics available for this platform
```

**Điều đó không mâu thuẫn với dữ liệu heap**: `-XshowSettings:system` là chẩn đoán theo platform/provider, không phải hợp đồng luôn cung cấp cgroup metrics trên mọi OS.

### Xem container detection chi tiết bằng HotSpot logging

Trong **Linux HotSpot hỗ trợ tag**:

```bash
java -Xlog:os+container=trace -version
```

Log có thể trình bày cgroup version, controller, limit và cách VM phát hiện tài nguyên. Bật `trace` chủ yếu cho chẩn đoán vì log có thể dài.

**Không chạy thử rồi cho rằng cờ luôn hoạt động trên Windows:** tài liệu JDK 26 nói `UseContainerSupport` chỉ áp dụng Linux. Trong môi trường thử nghiệm Windows JDK 24, `-XX:+UseContainerSupport` không được nhận diện. Cần kiểm JVM/platform trước khi sử dụng cờ tùy chọn.

### Xem flags cuối cùng

```bash
java -XX:+PrintFlagsFinal -version
```

Tìm `MaxHeapSize`, `InitialHeapSize`, `MaxRAMPercentage` và `UseContainerSupport` **khi runtime tương ứng có các flag đó**. Những giá trị này là một phần bằng chứng để hiểu JVM ergonomics, nhưng không thay cgroup `memory.current` hoặc số đo process RSS.

## 16. Kiểm Linux cgroup v2 từ bên trong container

Trên hệ thống mà đường dẫn cgroup được mount tại `/sys/fs/cgroup` theo bố cục trực tiếp:

```bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.stat
```

**Không mặc định tất cả container đều có đúng path này.** Trong một số runtime, tiến trình nằm ở cgroup con, mount namespace khác hoặc cần đọc `/proc/self/cgroup` và `/proc/self/mountinfo` để xác định đường dẫn tương ứng.

```bash
cat /proc/self/cgroup
cat /proc/self/mountinfo
```

Muốn đo **chính xác cgroup chứa JVM process**, không lấy chỉ số của shell thuộc một cgroup khác nếu hệ thống đã dịch chuyển process hoặc lồng thêm group. Kiểm đúng PID/cgroup và ancestor constraints.

### Cách đọc ngắn một ví dụ

```text
memory.max       = 1073741824 bytes (1 GiB)
memory.current   = 734003200 bytes (700 MiB)
```

Khoảng dư theo phép trừ ở đúng thời điểm là:

```text
1.024 MiB - 700 MiB = 324 MiB
```

Đây **không phải** “324 MiB heap còn có thể dùng”. JVM còn cần natives, OS có reclaim, các khoản memory thay đổi liên tục và cgroup hierarchy có thể áp dụng limit ở parent.

### `memory.events` cho thấy điều gì?

Một file có thể chứa các bộ đếm:

```text
low 0
high 0
max 12
oom 3
oom_kill 1
```

Giá trị trên là **ví dụ giả lập**, không phải số đo trên máy của người học:

- `high`: số lần cgroup bị throttle/reclaim vì vượt memory.high.
- `max`: số lần cgroup đụng ngưỡng hard boundary và cần thử reclaim.
- `oom`: số lần cgroup vào tình huống OOM theo định nghĩa kernel.
- `oom_kill`: số process thuộc phạm vi cgroup bị OOM killer giết.

**Đừng dùng chỉ `oom_kill` để biết ngay JVM nào bị giết** nếu cgroup chứa nhiều process/child. Kết hợp timestamp, logs và container status. `memory.events` thường có counters theo **hierarchy**, còn `memory.events.local` phản ánh cgroup cục bộ.

## 17. Docker: memory limit là ràng buộc của runtime, không của `-Xmx`

Một ví dụ môi trường thử nghiệm Linux (cần Docker và image JDK tương ứng):

```bash
docker run --rm --memory=1024m eclipse-temurin:21-jdk \
    java -XshowSettings:vm -XshowSettings:system -version
```

Ở đây:

- `--memory=1024m` do **Docker** áp dụng cho container bằng kernel mechanisms.
- Các `-XshowSettings` là tùy chọn để **JVM báo những gì nó nhận thấy**.
- JVM hiện đại ở Linux có thể dùng hard limit đó làm cơ sở cho heap ergonomics.
- Giá trị Max Heap Size **không nhất thiết bằng 1.024 MiB**; `-Xmx`/ergonomics vẫn giới hạn riêng Java heap.
- Nếu container bị chạy trong một hệ thống có hạn mức khác ở parent cgroup, cần kiểm thêm giới hạn hiệu lực.

### Khi cần chỉ định budget heap rõ

```bash
docker run --rm --memory=1024m eclipse-temurin:21-jdk \
    java -Xms128m -Xmx640m -XshowSettings:vm -version
```

Ví dụ này không yêu cầu tạo application JAR, vì `-version` khởi động VM đủ để xem settings. Với một ứng dụng thực, JVM options sẽ đứng **trước `-jar app.jar`**.

**Không dùng ví dụ Docker như một phép đo RAM đã xác minh trên máy hiện tại:** các câu lệnh này minh họa cách làm trong một môi trường Linux container. Code QA của bài được chạy bằng một JVM độc lập trên Windows, không giả vờ đã kiểm chứng Docker runtime tại đây.

### Docker stats có tương đương `memory.current` không?

Không nhất thiết. `docker stats` trình bày metrics theo phiên bản Docker/cgroup và có thể áp dụng quy tắc hiển thị đã trừ một số loại cache. Hãy dùng kết hợp Docker stats, raw cgroup files và process/heap metrics thay vì bắt các số này phải bằng nhau.

## 18. Kubernetes: requests khác limits

Ví dụ manifest bộ nhớ:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: memory-example
spec:
  containers:
    - name: app
      image: eclipse-temurin:21-jdk
      command: ["java", "-Xms128m", "-Xmx640m", "-version"]
      resources:
        requests:
          memory: "512Mi"
        limits:
          memory: "1Gi"
```

**Ý nghĩa:**

- `requests.memory = 512Mi`: giá trị scheduler sử dụng khi xếp workload, ảnh hưởng chính sách tài nguyên/QoS; **không phải Java heap** và **không phải hard memory limit**.
- `limits.memory = 1Gi`: hạn mức memory mà runtime/kernel thực thi đối với container theo cơ chế đang dùng.
- `-Xmx640m`: Java heap upper bound, **không phải tổng memory limit**.
- `-Xms128m`: initial heap size theo JVM.
- Image `eclipse-temurin:21-jdk` là một ví dụ JDK Linux, không biểu thị phiên bản runtime đang dùng để QA trên Windows.

Kubernetes có nhiều scope: container, Pod, node, Quality of Service và eviction policy. **OOMKilled** do container vượt memory limit không phải cùng sự kiện với **Pod eviction** vì áp lực tài nguyên node; cần đọc reason thực tế.

### Điều tra Pod bị kill

```bash
kubectl describe pod memory-example
kubectl get pod memory-example -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'
```

Các lệnh đọc thông tin status/events của Pod. **Không suy luận chỉ từ “exit code 137”** rằng nguyên nhân duy nhất là vượt cgroup memory limit: 137 thường thể hiện tiến trình bị `SIGKILL`, nhưng SIGKILL cũng có thể do những nguồn khác. Cần kiểm `OOMKilled` reason, `memory.events`/node logs và bối cảnh restart.

## 19. Ví dụ Java 17+ độc lập, deterministic: model + đo JVM thật

Tạo tệp **`ContainerMemoryBoundariesDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public final class ContainerMemoryBoundariesDemo {
    private static final long MIB = 1024L * 1024L;

    record Budget(long hostMiB, long containerLimitMiB,
                  long maxHeapMiB, long otherJvmMiB,
                  long otherChargesMiB) {
        Budget {
            if (hostMiB <= 0 || containerLimitMiB <= 0
                    || maxHeapMiB < 0 || otherJvmMiB < 0
                    || otherChargesMiB < 0) {
                throw new IllegalArgumentException("invalid budget");
            }
        }

        long totalChargedMiB() {
            return Math.addExact(
                    Math.addExact(maxHeapMiB, otherJvmMiB),
                    otherChargesMiB);
        }

        long headroomMiB() {
            return containerLimitMiB - totalChargedMiB();
        }

        boolean fits() {
            return totalChargedMiB() <= containerLimitMiB;
        }
    }

    public static void main(String[] args) {
        // Mô hình minh họa, KHÔNG phải số đo của host/container.
        Budget sample = new Budget(16_384, 1_024, 640, 220, 80);
        Budget tooLarge = new Budget(16_384, 1_024, 960, 220, 80);

        System.out.println("modelHostMiB=" + sample.hostMiB());
        System.out.println("modelContainerLimitMiB="
                + sample.containerLimitMiB());
        System.out.println("modelMaxHeapMiB=" + sample.maxHeapMiB());
        System.out.println("modelOtherJvmMiB=" + sample.otherJvmMiB());
        System.out.println("modelOtherChargesMiB="
                + sample.otherChargesMiB());
        System.out.println("modelTotalChargedMiB="
                + sample.totalChargedMiB());
        System.out.println("modelHeadroomMiB=" + sample.headroomMiB());
        System.out.println("modelWithinLimit=" + sample.fits());
        System.out.println("oversizedHeapWithinLimit=" + tooLarge.fits());
        System.out.println("heapIsNotContainerLimit="
                + (sample.maxHeapMiB() != sample.containerLimitMiB()));

        Runtime runtime = Runtime.getRuntime();
        long maxHeap = runtime.maxMemory();
        long committed = runtime.totalMemory();
        long usedEstimate = committed - runtime.freeMemory();

        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        MemoryUsage nonHeap =
                ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage();

        System.out.println("runtimeMaxHeapPositive=" + (maxHeap > 0));
        System.out.println("runtimeHeapWithin128MiB="
                + (maxHeap <= 128 * MIB));
        System.out.println("runtimeCommittedWithinMax="
                + (committed <= maxHeap));
        System.out.println("runtimeUsedWithinCommitted="
                + (0 <= usedEstimate && usedEstimate <= committed));
        System.out.println("mxbeanHeapUsedWithinCommitted="
                + (heap.getUsed() >= 0
                && heap.getUsed() <= heap.getCommitted()));
        System.out.println("mxbeanNonHeapUsedWithinCommitted="
                + (nonHeap.getUsed() >= 0
                && nonHeap.getUsed() <= nonHeap.getCommitted()));
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 -encoding UTF-8 ContainerMemoryBoundariesDemo.java
java -Xms32m -Xmx128m ContainerMemoryBoundariesDemo
```

**Stdout dự kiến chính xác trên HotSpot/JDK lab đã kiểm:**

```text
modelHostMiB=16384
modelContainerLimitMiB=1024
modelMaxHeapMiB=640
modelOtherJvmMiB=220
modelOtherChargesMiB=80
modelTotalChargedMiB=940
modelHeadroomMiB=84
modelWithinLimit=true
oversizedHeapWithinLimit=false
heapIsNotContainerLimit=true
runtimeMaxHeapPositive=true
runtimeHeapWithin128MiB=true
runtimeCommittedWithinMax=true
runtimeUsedWithinCommitted=true
mxbeanHeapUsedWithinCommitted=true
mxbeanNonHeapUsedWithinCommitted=true
```

### Hai nhóm số liệu trong ví dụ có nguồn hoàn toàn khác nhau

**Nhóm `model...`** là dữ liệu **giả định** do chương trình tự đặt để minh họa phân bổ:

- Host = 16.384 MiB.
- Container limit = 1.024 MiB.
- Heap cap = 640 MiB.
- Other JVM memory = 220 MiB.
- Other cgroup charges = 80 MiB.
- Tổng = 940 MiB; headroom = 84 MiB.
- Nếu heap cap đổi thành 960 MiB mà các khoản khác không đổi thì vượt budget.

Đây **không** phải kết quả đọc cgroup, host RAM hay container memory thật.

**Nhóm `runtime...`/`mxbean...`** đọc chính xác những API của **JVM đang chạy**. Ví dụ chỉ in các **điều kiện boolean** để không phụ thuộc số heap đã committed hoặc GC schedule theo máy. Khi chạy với `-Xmx128m`, `runtimeHeapWithin128MiB=true` được kiểm chứng trên HotSpot JDK 24. Không nên coi điều kiện exact heap cap này là cam kết về mọi JVM implementation nếu chúng có cách diễn giải launcher flags khác nhau.

### Vì sao không in “containerLimitMiB” bằng Runtime?

Bởi vì `Runtime.getRuntime().maxMemory()` chỉ cung cấp **maximum Java heap**, không phải hard memory limit của cgroup. Việc tự gắn nhãn maxMemory là container limit tạo ra thông tin monitoring **sai**.

Khi thực hành trên Linux container, hãy bổ sung các lệnh cgroup ở mục 16 để đo **cgroup memory.max/current**, thay vì sửa định nghĩa của Runtime API.

### Vì sao sử dụng `Math.addExact`?

Để cộng các khoản budget kiểu `long` và phát hiện overflow thay vì âm thầm tràn số. Điều này đặc biệt quan trọng khi xử lý memory bytes của hệ thống lớn. Mô hình dùng MiB cho dễ đọc; API JVM trả đơn vị **bytes**, cần đổi đơn vị nhất quán trước khi so sánh.

## 20. Phân tích mỗi dòng output của chương trình

1. `modelHostMiB=16384`: host có 16 GiB **trong dữ liệu giả lập**, không nói môi trường thử nghiệm thật.
2. `modelContainerLimitMiB=1024`: cgroup được giả định có hard limit 1 GiB.
3. `modelMaxHeapMiB=640`: upper bound heap được chọn trong ngân sách.
4. `modelOtherJvmMiB=220`: phần JVM memory ngoài heap ở mức giả định.
5. `modelOtherChargesMiB=80`: các khoản khác bị tính phí ở cgroup, **không trùng** hai khoản trước.
6. `modelTotalChargedMiB=940`: 640 + 220 + 80.
7. `modelHeadroomMiB=84`: 1.024 - 940.
8. `modelWithinLimit=true`: budget giả lập chưa vượt limit.
9. `oversizedHeapWithinLimit=false`: đổi heap thành 960 MiB thì tổng dự kiến vượt 1 GiB.
10. `heapIsNotContainerLimit=true`: 640 khác 1.024, thể hiện hai phạm vi.
11. `runtimeMaxHeapPositive=true`: JVM đang chạy báo heap max dương.
12. `runtimeHeapWithin128MiB=true`: launcher đã giới hạn heap bằng `-Xmx128m` trên runtime thử.
13. `runtimeCommittedWithinMax=true`: bộ nhớ heap hiện báo không vượt upper bound.
14. `runtimeUsedWithinCommitted=true`: lượng used tính từ Runtime nằm trong committed hiện tại.
15. `mxbeanHeapUsedWithinCommitted=true`: phép đo MemoryMXBean heap used ≤ committed.
16. `mxbeanNonHeapUsedWithinCommitted=true`: phép đo MemoryMXBean non-heap used ≤ committed.

Một số invariant là **kiểm thử mẫu**, không phải định nghĩa của toàn OS memory accounting. Ví dụ non-heap MemoryMXBean có thể không biết mọi native buffer. Đừng trình bày các boolean này như bằng chứng container không bao giờ OOMKilled.

## 21. `OutOfMemoryError` của JVM và `OOMKilled` của container khác nhau

Đây là hai sự kiện thường bị nhầm nhất.

### Trường hợp A — Java heap hết chỗ

Ví dụ JVM có:

```text
-Xmx = 512 MiB
Container limit = 1 GiB
```

Ứng dụng cố giữ nhiều object hơn mức heap có thể cấp phát. Collector không thu hồi đủ, JVM có thể ném:

```text
java.lang.OutOfMemoryError: Java heap space
```

Điều này có thể xảy ra **ngay cả khi cgroup memory.current chưa tới 1 GiB**.

- Ngoại lệ do JVM/Java memory subsystem báo.
- Có thể nhìn thấy stack trace `OutOfMemoryError`.
- `-XX:+HeapDumpOnOutOfMemoryError` có thể giúp thu heap dump **nếu còn đủ quyền/bộ nhớ/disk** và cấu hình phù hợp.
- Container có thể tiếp tục hoặc ứng dụng dừng tùy cách lỗi được xử lý.

**Không nói mọi `OutOfMemoryError` đều là heap space**: còn có `Direct buffer memory`, `Metaspace`, `unable to create native thread` hoặc những nguyên nhân khác.

### Trường hợp B — Linux OOM-kill vì cgroup memory

Ví dụ:

```text
-Xmx = 640 MiB
Container hard limit = 1 GiB
Heap used hiện tại = 500 MiB
JVM + native + cache + những khoản khác tăng mạnh
```

Khi tổng memory được tính phí cho cgroup đạt giới hạn và reclaim không đủ, **kernel có thể kill một process**. Trong Kubernetes, trạng thái thường được quan sát là:

```text
Reason: OOMKilled
Exit Code: 137
```

Trường hợp này có thể xảy ra **khi heap vẫn dưới `-Xmx`** vì killer kiểm **cgroup usage**, không kiểm riêng Java heap.

- JVM có thể bị `SIGKILL` và **không kịp ném/catch một Java exception**.
- `-XX:+HeapDumpOnOutOfMemoryError` không bảo đảm tạo dump khi kernel kill tiến trình.
- Thông tin cần xem gồm Pod/container terminated reason, cgroup `memory.events`, logs node và biểu đồ cgroup memory.
- `exit code 137` **không đủ một mình** để kết luận OOMKilled; cần kiểm reason/signal/infra events.

### Trường hợp C — Node pressure hoặc Pod eviction

Kubernetes còn có eviction khi node chịu memory pressure hoặc có chính sách quản trị tương ứng. Đây **không nhất thiết** là một lần process bị cgroup OOM-kill.

**Chẩn đoán đúng là phân loại nguyên nhân trước**; tăng `-Xmx` trong trường hợp B có thể làm tình hình **tệ hơn**.

## 22. Vì sao heap chỉ chiếm 50% nhưng container đã sát limit?

Một bài toán thực tế:

```text
Container memory limit   1.024 MiB
Java heap maximum          640 MiB
Java heap used             330 MiB
Non-heap/JVM native        280 MiB
Direct buffers/native      170 MiB
File cache/kernel/etc      200 MiB
Total mô hình              980 MiB
Headroom                    44 MiB
```

Số liệu này chỉ là **minh họa**, không phải phép đo. Lưu ý các nhóm phải tránh overlap: direct buffers/native ở đây được tách khỏi dòng `Non-heap/JVM native` nhằm minh họa một budget **không trùng lặp**.

Dù heap mới dùng 330 MiB trong mức cho phép 640 MiB, cgroup đã gần 1 GiB. Một burst cấp phát direct buffers hoặc page cache khác có thể đẩy vượt giới hạn.

**Không xử lý bằng cách chỉ tăng heap max**. Trước tiên hãy hỏi:

- JVM có quá nhiều platform threads không?
- Có nhiều direct buffers hoặc native allocations bất thường không?
- Ứng dụng đọc/ghi file hoặc dùng tmpfs nhiều không?
- Có process khác cùng cgroup không?
- Metaspace/code cache có tăng hay leak classloader không?
- Cgroup memory.current có tăng theo traffic dù heap used đã ổn định sau GC không?

### Cần thận trọng với phép cộng memory metrics thật

**Không cộng process RSS + Java heap used**: heap pages resident đã **nằm trong RSS** ở nhiều trường hợp. Cũng không cộng `memory.current + RSS`: process pages trong cgroup đã được tính phí vào memory.current theo cơ chế kernel.

Budget toán học ở trên dùng **những khoản định nghĩa tách biệt**, không phải khuyến nghị lấy trực tiếp năm biểu đồ tùy ý rồi cộng.

## 23. Native Memory Tracking (NMT): khi nào hữu ích?

HotSpot hỗ trợ **Native Memory Tracking** để quan sát nhiều hạng mục cấp phát native **do JVM quản lý**.

Bật tại thời điểm khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Sau đó, từ JDK tools có quyền attach vào process:

```bash
jcmd <pid> VM.native_memory summary
```

`<pid>` ở đây là cú pháp biến thay thế bằng **PID thật**, không phải một lệnh có thể chạy nguyên xi. Tùy môi trường container, `jcmd` có thể không nằm trong runtime image chỉ chứa JRE; cần JDK tools và quyền phù hợp.

Cách xem thay đổi theo thời gian:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

**Giới hạn quan trọng của NMT:**

- Theo dõi **JVM native allocations do JVM quản lý**, không bao quát mọi native memory cấp phát bởi **third-party/JNI library** ngoài phạm vi tracking.
- Không phải một số đo trực tiếp thay cho process RSS hay cgroup memory.current.
- Output có `reserved` và `committed`; đừng cộng các khoản reserved rồi gọi đó là RAM vật lý đã dùng.
- Có overhead về hiệu năng và memory; bật `summary`/`detail` ở production cần cân nhắc.
- Không bật NMT giữa chừng trên một process đã chạy nếu lúc startup không bật tracking tương ứng.
- Nếu process bị OOMKilled tức thời, công cụ có thể không kịp attach; cần chủ động thu metrics hoặc lặp lại trên môi trường đủ tài nguyên.

### Một cách phân tích thực tế

Nếu heap used sau GC ổn định nhưng RSS/cgroup usage tăng:

1. Kiểm `NativeMemoryTracking=summary` nếu đã bật.
2. Xem `Thread`, `Class`/Metaspace, `Code`, `GC`, `Internal` và các hạng mục xuất hiện.
3. Đối chiếu thread count, native direct buffer pools, JNI allocations và memory-mapped files.
4. So với `memory.stat` `anon/file/kernel` để phân biệt cgroup file/cache và anonymous memory.
5. Đừng kết luận “NMT không tăng nên chắc chắn không có native leak”: third-party allocations có thể nằm ngoài NMT.

## 24. GC tuning không thể thay thế cgroup memory budget

Một số kỹ thuật GC có thể thay đổi **heap commitment/residency**, nhưng không làm container hard limit tăng lên.

Ví dụ bạn có thể lựa chọn:

```bash
java -XX:+UseG1GC -Xms128m -Xmx640m -jar app.jar
```

G1 quản lý Java heap với chiến lược riêng; nó không thể thu hồi JNI allocations hoặc kernel page cache chỉ bằng cách chạy young/full GC.

Nếu container bị OOMKilled vì **native memory**, thêm `-XX:MaxGCPauseMillis` hoặc bắt JVM GC thường xuyên không chắc giúp được. Nếu container bị kill vì heap + native cộng lại vượt budget, giảm heap max đôi khi tạo headroom; nhưng nếu live heap thật cần gần 640 MiB, giảm quá mức lại gây Java OOME hoặc GC thrashing.

**Hai câu hỏi phải kiểm riêng:**

1. **Ứng dụng cần bao nhiêu live Java heap?** → heap profiling, heap after GC, allocation rate.
2. **Cgroup cần bao nhiêu tổng memory để vận hành an toàn?** → memory.current/peak/events, RSS/native/file/cache, workload concurrency.

Nếu chỉ trả lời câu 1, có thể vẫn bị OOMKilled. Nếu chỉ trả lời câu 2, có thể đặt `-Xmx` quá nhỏ làm JVM liên tục GC.

## 25. Lựa chọn heap budget thực tế

Không có một tỷ lệ `-Xmx / memory limit` phù hợp cho mọi ứng dụng. Ví dụ “heap = 60% container memory” là **giả định để thử**, không phải khuyến nghị bắt buộc.

Một quy trình có căn cứ:

1. **Chốt workload:** request rate, concurrency, batch size, data structures, request payload.
2. **Xác định effective cgroup limit:** runtime flags, `memory.max`/ancestors hoặc container configuration.
3. **Đo peak heap used sau GC** và biến thiên theo tải.
4. **Đo native/non-heap:** NMT, thread stacks, direct buffers, code cache, metaspace, JNI.
5. **Đo mức tính phí cgroup:** `memory.current`, `memory.peak`, `memory.stat`, page cache/tmpfs.
6. **Tính margin:** startup spikes, class loading, scale event, traffic burst, garbage chưa được thu, cache.
7. **Chọn `-Xmx` hoặc `MaxRAMPercentage`** sao cho live-set có chỗ và cgroup còn headroom.
8. **Chạy load test** trên chính OS/JDK/container setup dự kiến.
9. **Theo dõi OOME/OOMKilled và GC pauses**, không chỉ average memory.
10. **Điều chỉnh** sau khi có số liệu thực tế, không dựa vào một “rule of thumb” bất biến.

### Nếu dùng percentage cho nhiều môi trường

```bash
java -XX:MaxRAMPercentage=60.0 -XX:InitialRAMPercentage=10.0 -jar app.jar
```

Tùy collector/JVM ergonomics và container limit được nhận diện, hai tỷ lệ ảnh hưởng tới **heap sizing** tương ứng. Đây không phải phân bổ đầy đủ native memory. Lệnh này còn cần **kiểm tra chính xác output trên runtime thực**; với container quá nhỏ hoặc quá lớn, mục tiêu percentage có thể không phù hợp và những flag khác cũng tác động.

### Nếu chọn mức tuyệt đối

```bash
java -Xms128m -Xmx640m -jar app.jar
```

Dễ audit khi container limit cố định, nhưng nếu deployment chuyển từ container 1 GiB sang 512 MiB thì phải **xem lại cấu hình**. Không giữ nguyên `-Xmx640m` trong môi trường nhỏ hơn mà không thẩm định budget.

## 26. Tình huống 1: đổi JDK, cùng Docker limit nhưng max heap thay đổi

Một image cũ có thể dùng JDK không hiểu cgroup version của host; nó lấy RAM host làm cơ sở rồi chọn heap max lớn không phù hợp. Sau khi nâng lên JDK hiện đại, JVM đọc effective container limit và chọn heap ergonomics nhỏ hơn.

**Triệu chứng:**

- Cùng Docker `--memory=1g`.
- `Runtime.maxMemory()` hoặc `-XshowSettings:vm` khác nhau giữa hai JDK builds.
- Có thể giảm OOMKilled khi JVM nhận đúng limit, nhưng không bảo đảm tuyệt đối.

**Cách xử lý:**

1. Ghi lại JDK release/vendor/build và cgroup v1/v2.
2. Kiểm `UseContainerSupport` trên Linux.
3. So `-XshowSettings:vm`, `-XshowSettings:system` và `-Xlog:os+container=trace`.
4. Kiểm flags khác như `-Xmx` hoặc `MaxRAMPercentage`.
5. Chạy load test với memory.current/peak và native usage.

**Không cố dùng lại cờ legacy từ một bài viết JDK 8/10 cũ** nếu JDK mới đã có container support mặc định. Trọng tâm là **xác minh runtime hiện hành**.

## 27. Tình huống 2: Java heap chưa đầy nhưng Pod OOMKilled

Ví dụ:

```text
Pod restart reason: OOMKilled
Container memory limit: 1024 MiB
Xmx: 640 MiB
Heap after GC: 300 MiB
Cgroup memory.current trước kill: ~1024 MiB
```

**Không kết luận sai rằng “Java heap metrics có lỗi”.** Các số có thể cùng đúng vì đo ở **những tầng khác nhau**.

Chuỗi điều tra nên là:

1. Xác nhận reason/exit code và thời điểm restart.
2. Đọc cgroup `memory.events` hoặc metrics container memory và pressure.
3. So memory growth với heap used sau GC.
4. Kiểm native allocations, direct buffers, thread count, JNI, mmap, page cache và tiến trình khác.
5. Kiểm memory limits của parent cgroups/Kubernetes.
6. Kiểm có process khác bị OOM-kill trong cùng cgroup không.
7. Chọn sửa phần memory lớn thực sự thay vì chỉ tăng/giảm `-Xmx` theo cảm tính.

Nếu native library dùng nhiều memory mà NMT không theo dõi, có thể cần OS profiler hoặc công cụ native phù hợp, không chỉ Java heap dump.

## 28. Tình huống 3: Java OOME trong khi container còn nhiều RAM

Ví dụ:

```text
Container memory limit: 2 GiB
Xmx: 512 MiB
Heap after full GC: ~510 MiB
Container memory.current: 900 MiB
Exception: java.lang.OutOfMemoryError: Java heap space
```

Vì Java heap là một vùng có **giới hạn riêng**, JVM có thể OOME khi heap không chứa được live objects, trong khi container vẫn chưa tới hard limit.

Cách tiếp cận:

- Kiểm memory leak/retention hoặc cache quá lớn.
- Đo live set và heap dump.
- Nếu ứng dụng thực sự cần thêm Java heap và container còn headroom, cân nhắc tăng `-Xmx`.
- Luôn kiểm lại native budget và memory.current sau khi tăng heap.
- Không nghĩ rằng OOME chỉ xảy ra nếu host đã dùng hết RAM.

**Hai lỗi OOME và OOMKilled cần hai chiến lược chẩn đoán**, dù cả hai có thể cùng xuất hiện trong một hệ thống cấu hình quá sát giới hạn.

## 29. Những lỗi phổ biến khi cấu hình container memory cho JVM

### Lỗi A — “Host có 32 GiB, JVM trong container có thể dùng 32 GiB”

Sai nếu cgroup/parent có giới hạn nhỏ hơn. **Sửa:** đọc effective cgroup memory limit và JVM settings riêng.

### Lỗi B — “`-Xmx` là max RAM toàn JVM”

Sai. Nó chỉ giới hạn **Java heap**. **Sửa:** budget cả native/non-heap, file/cache và các process được tính phí.

### Lỗi C — “Heap used thấp là không thể OOMKilled”

Sai. Container limit áp dụng trên tổng memory charged cho cgroup. **Sửa:** kiểm memory.current/events cùng RSS/native.

### Lỗi D — “`memory.max=max` nghĩa là process có RAM vô hạn”

Sai. Có thể có ancestor limit và host physical pressure. **Sửa:** kiểm phân cấp và node constraints.

### Lỗi E — “`MaxRAMPercentage=75` nghĩa là container chỉ dùng tối đa 75% RAM”

Sai. Cờ điều chỉnh **heap ergonomics**, không giới hạn mọi memory allocations. **Sửa:** đo native/cgroup và thiết lập headroom phù hợp.

### Lỗi F — “`free -h` trong container là hard memory limit”

Không chắc. **Sửa:** dùng cgroup memory controller và launcher detection.

### Lỗi G — “`MemoryMXBean` non-heap là toàn bộ native memory”

Sai. Nó không bao quát mọi thư viện/JNI hoặc kernel memory. **Sửa:** NMT + OS + cgroup metrics.

### Lỗi H — “NMT cộng `reserved` cho biết JVM dùng bao nhiêu RAM vật lý”

Sai. Reserved là virtual address space. **Sửa:** phân biệt committed/resident và scope metrics.

### Lỗi I — “Cộng heap used với RSS để tính container usage”

Sai vì có thể **double-count** những pages heap đã resident. **Sửa:** dùng `memory.current` cho total cgroup; phân rã các khoản bằng công cụ thích hợp.

### Lỗi J — “Java 10 chắc chắn hiểu cgroup v2 của Linux hiện nay”

Không đúng; hỗ trợ cgroup v2 xuất hiện sau Java 10 và được backport khác nhau. **Sửa:** chạy JDK đã được bảo trì, kiểm release/update và log thực tế.

### Lỗi K — “Thấy exit code 137 là chắc chắn cgroup OOMKilled”

Không đủ chứng cứ; 137 thường tương ứng `SIGKILL`. **Sửa:** xác nhận Kubernetes/Docker/node event và cgroup counters.

### Lỗi L — “Bật HeapDumpOnOutOfMemoryError sẽ có heap dump sau kernel OOM-kill”

Không bảo đảm; JVM có thể bị kill ngay. **Sửa:** chủ động thu profiling và quan sát cgroup; xử lý native pressure.

### Lỗi M — “Kubernetes memory request là memory cap”

Sai. Memory request chủ yếu dùng cho scheduling/resource management. **Sửa:** đọc `limits.memory` và effective kernel controller limit.

### Lỗi N — “Tăng Xmx luôn chữa mọi lỗi memory”

Không. Nó có thể tạo **ít headroom native hơn** và tăng nguy cơ OOMKilled. **Sửa:** phân loại Java OOME với OS kill rồi điều chỉnh đúng tầng.

### Lỗi O — “Cho MaxRAMPercentage=100% là tận dụng RAM tối đa”

Rất rủi ro vì native memory, thread stacks, GC structures và cache còn cần budget. **Sửa:** chừa margin có bằng chứng từ load tests.

### Lỗi P — “Cứ dùng `UseContainerSupport` option trên mọi OS”

Không. Hỗ trợ và nhận diện cờ phụ thuộc HotSpot/platform; tài liệu Java 26 mô tả tính năng này cho Linux. **Sửa:** kiểm release và platform, không bắt Windows/Mac cư xử như cgroup Linux.

### Lỗi Q — “Không thấy NMT tăng nghĩa là không thể có native leak”

Không đúng; allocations của thư viện native/JNI ngoài phạm vi NMT có thể không được ghi. **Sửa:** dùng công cụ OS/native profiling phù hợp.

## 30. Checklist review và vận hành trước khi release

1. **Host RAM thực tế** là bao nhiêu? Có node/container khác cùng dùng không?
2. **Giới hạn cgroup hiện hành** là gì? Có ancestor limits không?
3. Kernel dùng **cgroup v1 hay v2**? Có kiểm đúng tệp/mount path không?
4. JDK version/vendor/build có **container awareness phù hợp** không?
5. `UseContainerSupport` có đang bật mặc định trên Linux được hỗ trợ không?
6. JVM có đọc đúng limit qua `-XshowSettings:system`/container logs không?
7. Đã biết heap max thật từ `Runtime.maxMemory` hoặc VM settings chưa?
8. Sử dụng `-Xmx` hay `MaxRAMPercentage`? Có flag ghi đè/chồng chéo không?
9. Đã phân biệt `-Xms`, committed heap và heap used chưa?
10. Có để headroom cho **metaspace, code cache, thread stacks, GC, JNI, direct buffers** không?
11. Có tính đến **page cache/tmpfs/kernel memory** và process khác cùng cgroup không?
12. Có tránh cộng trùng heap và RSS trong dashboard không?
13. Đã đo `memory.current`/`memory.peak` đúng scope chưa?
14. Có theo dõi `memory.events`, nhất là `high`, `max`, `oom` và `oom_kill` chưa?
15. Đã phân biệt **Java OOME**, **container OOMKilled** và **Pod eviction** chưa?
16. Có đo **peak theo workload** chứ không chỉ average/idle memory không?
17. Có kiểm after-GC live heap để xác định nhu cầu thật không?
18. Nếu có NMT, đã hiểu giới hạn của NMT và overhead chưa?
19. Có giới hạn hoặc đánh giá direct buffers/threads/classloading bất thường không?
20. Có chạy integration/load tests với cùng OS/JDK/container memory limit dự kiến chưa?
21. Có thiết kế ứng dụng không bị data loss khi JVM bị OOMKilled/restart không?
22. Có health checks, retry policy, graceful degradation và monitoring cần thiết không?
23. Có kế hoạch xử lý incident bằng logs/metrics đúng tầng thay vì tăng Xmx ngẫu nhiên không?
24. Có xác nhận không dùng các JVM flags đã legacy hoặc không được runtime hỗ trợ không?

## 31. Bài tập và đáp án

**Câu 1.** Host có 32 GiB RAM, container limit 1 GiB, `-Xmx512m`. Ba giá trị này có bằng nhau không?

**Câu 2.** `Runtime.getRuntime().maxMemory()` đo giới hạn nào?

**Câu 3.** Khi heap used = 250 MiB và max heap = 512 MiB, có suy ra container chỉ dùng 250 MiB không?

**Câu 4.** `memory.max` trong cgroup v2 chứa `max` có nghĩa là toàn bộ máy có RAM vô hạn không?

**Câu 5.** `memory.current` đo chỉ mỗi Java heap hay toàn memory được tính phí cho cgroup?

**Câu 6.** `-XX:MaxRAMPercentage=60` giới hạn cả native memory không?

**Câu 7.** `-Xms` và `-Xmx` khác nhau về ý nghĩa gì?

**Câu 8.** Vì sao không được cộng `RSS + heap used` để báo total usage?

**Câu 9.** Cgroup v2 có file nào theo dõi số lần OOM-kill?

**Câu 10.** Java heap đầy và ném `java.lang.OutOfMemoryError: Java heap space` có nhất thiết dẫn tới container OOMKilled không?

**Câu 11.** Nếu container OOMKilled, `-XX:+HeapDumpOnOutOfMemoryError` có bảo đảm tạo heap dump không?

**Câu 12.** Kubernetes `requests.memory` có phải hard limit không?

**Câu 13.** Có thể đặt `-Xmx1024m` trong container limit 1 GiB mà không cần chừa native memory không?

**Câu 14.** Vì sao `memory.high` và `memory.max` không tương đương?

**Câu 15.** Hỗ trợ cgroup v2 có được coi là chắc chắn có ở mọi JDK 10 build không?

**Câu 16.** Tại sao `MemoryMXBean.getNonHeapMemoryUsage()` không thay thế NMT và OS metrics?

**Câu 17.** Trong mô hình 1.024 MiB container, heap 640 MiB, otherJvm 220 MiB, otherCharges 80 MiB, headroom bằng bao nhiêu?

**Câu 18.** Nếu đổi heap thành 960 MiB, tổng các khoản theo mô hình bằng bao nhiêu và còn phù hợp không?

**Câu 19.** Vì sao cgroup parent có thể giới hạn workload dù child `memory.max=max`?

**Câu 20.** Cách nào phân biệt JVM heap OOME với cgroup OOMKilled khi điều tra sự cố?

**Câu 21.** `-XshowSettings:system` có bắt buộc hiển thị cgroup data trên Windows không?

**Câu 22.** Khi `Runtime.totalMemory()-freeMemory()` thấp nhưng RSS cao, nên xem thêm những khoản nào?

**Câu 23.** `-XX:MaxRAM` có ghi thay kernel cgroup memory.max không?

**Câu 24.** Vì sao không có một tỷ lệ heap/container chung thích hợp cho mọi hệ thống?

**Đáp án:**

1. Không. Host RAM, hard limit cgroup và upper bound Java heap có scope khác nhau.
2. Java heap maximum được JVM báo, không phải host RAM hoặc container hard limit.
3. Không. Native, non-heap, file/page cache và tiến trình khác có thể dùng memory.
4. Không; chỉ cgroup ấy không đặt hard limit, còn ancestors và host vẫn có giới hạn.
5. Tổng memory được tính phí cho cgroup và descendants theo Linux controller.
6. Không. Nó ảnh hưởng heap ergonomics, không phải toàn process RSS/cgroup.
7. `-Xms` là initial heap; `-Xmx` là maximum heap.
8. Heap resident pages thường đã nằm trong process RSS; cộng là double-count.
9. `memory.events` hoặc `memory.events.local` với key `oom_kill` theo scope.
10. Không. JVM có thể ném/catch lỗi heap ngay cả khi container vẫn dưới limit.
11. Không. Kernel có thể SIGKILL mà JVM không kịp xử lý hoặc dump.
12. Không. Request phục vụ resource scheduling/management; limit là ràng buộc khác.
13. Không nên; JVM và hệ thống còn cần nhiều memory ngoài Java heap.
14. `memory.high` thường gây reclaim/throttling; `memory.max` là hard limit có thể dẫn đến OOM kill.
15. Không. Hỗ trợ cgroup v2 xuất hiện sau Java 10, cần kiểm runtime.
16. MemoryMXBean chỉ đo những memory pools JVM quản lý; NMT/OS cung cấp góc nhìn khác và cũng có giới hạn.
17. 84 MiB.
18. 960 + 220 + 80 = **1.260 MiB**, vượt 1.024 MiB.
19. Cgroups phân cấp; giới hạn ở parent không thể bị child bỏ qua.
20. Kiểm exception/stack trace Java so với container reason, exit status, cgroup events và node logs.
21. Không. Lệnh có thể báo `No metrics available for this platform`.
22. JVM thread stacks, metaspace/JIT, native/direct buffers, JNI, file mappings và page cache.
23. Không. Nó chỉ ảnh hưởng cơ sở tính heap ergonomics của JVM.
24. Vì live heap, native allocations, thread count, cache, GC và traffic spikes khác nhau.

## 32. Tổng kết: bốn số cần đặt cạnh nhau

Một dashboard/troubleshooting cho Java container nên có ít nhất:

1. **Effective cgroup memory limit** — ngân sách mà kernel áp dụng.
2. **Cgroup current/peak memory** — mức sử dụng thực đang được tính phí.
3. **Java heap max/used/committed** — tình trạng vùng Java heap.
4. **JVM/native/process memory và OOM events** — giúp tìm phần vượt ngoài heap.

**Những điều cần nhớ:**

- **Host physical RAM** là tài nguyên node, không đồng nhất với hạn mức của container.
- **Container limit** thường do cgroup thực thi, có phân cấp và accounting riêng.
- **`-Xmx` đặt maximum Java heap**, không đặt hard cap cho toàn JVM, native, cache hay cgroup.
- **`-XX:MaxRAMPercentage`** là cách tính heap max theo memory JVM dùng làm cơ sở, không là giới hạn tổng RAM.
- **`-Xms`, `committed`, `used`, `max`, `RSS` và `memory.current` có nghĩa khác nhau**; không lấy phép trừ/cộng giữa chúng khi scope không khớp.
- **Java OOME** có thể xảy ra khi container còn RAM; **OOMKilled** có thể xảy ra khi Java heap chưa đầy.
- Java 10 đánh dấu bước tiến về container awareness; JDK hiện đại còn cần hỗ trợ đúng **cgroup v2** của Linux được triển khai.
- Để chọn budget, phải đo cả **heap, native, cache, concurrency và cgroup peak** trên workload thật.
- Không dựa vào JVM options legacy hoặc giả định rằng metrics được hiển thị giống nhau trên Windows, Linux và các vendor JDK.

## 33. Nguồn chính thức và tài liệu tiếp tục áp dụng

1. [Oracle Java SE 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): `-Xmx`, `-Xms`, `-XX:MaxRAMPercentage`, `-XX:MaxRAM`, `UseContainerSupport`, `-Xlog:os+container`, NMT.
2. [Oracle Java SE 26 — MemoryMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap và non-heap management; các số `used/committed/max`.
3. [Oracle Java SE 26 — MemoryUsage](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryUsage.html): `init`, `used`, `committed`, `max`.
4. [Oracle Java SE 26 — Runtime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Runtime.html): `maxMemory()`, `totalMemory()`, `freeMemory()`.
5. [Oracle Java SE 26 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html): Native Memory Tracking và `jcmd VM.native_memory`.
6. [Linux Kernel — Control Group v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html): `memory.max`, `memory.current`, `memory.events`, `memory.stat`, `memory.high` và hierarchy.
7. [Oracle Java SE 10 — java launcher options](https://docs.oracle.com/javase/10/tools/java.htm): bối cảnh xuất hiện `UseContainerSupport` và nhận diện container trên nền tảng được hỗ trợ.
8. [OpenJDK JDK-8230305 — Cgroups v2 support](https://bugs.openjdk.org/browse/JDK-8230305): tiến trình bổ sung hỗ trợ cgroup v2 sau Java 10.
9. [OpenJDK JDK-8146115 — Improve docker container detection](https://bugs.openjdk.org/browse/JDK-8146115): nền tảng container memory awareness của HotSpot.
10. [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): phân biệt requests, limits và quản lý resource của container.
11. [Kubernetes — Pod Quality of Service Classes](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/): ảnh hưởng resource requests/limits tới QoS.
