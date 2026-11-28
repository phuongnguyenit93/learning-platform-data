# Giới hạn bộ nhớ container và phân bổ ngân sách cho toàn tiến trình trong Java 27

Một dịch vụ Java chạy trong Docker hoặc Kubernetes có thể bị dừng với trạng thái **`OOMKilled` dù biểu đồ heap vẫn chưa chạm `-Xmx`**. Ngược lại, ứng dụng có thể ném `java.lang.OutOfMemoryError: Java heap space` trong khi container còn nhiều bộ nhớ. Hai hiện tượng này không mâu thuẫn: **heap chỉ là một phần bộ nhớ của JVM**, còn giới hạn container áp dụng cho tài nguyên mà kernel tính vào cgroup.

Trong **Java 27**, HotSpot có khả năng nhận diện tài nguyên container trên Linux theo mặc định, nhưng việc tự nhận diện **không tự lập ngân sách đầy đủ cho mọi thành phần**. Người vận hành cần tính cả Java heap, bộ nhớ JVM ngoài heap, NIO direct buffers, bộ nhớ native do thư viện cấp phát, các luồng, page cache và khoảng dự phòng.

Bài thuộc chương **JVM, bộ nhớ và thu gom rác** của module **Java 27 và các kiến thức liên quan**. Nội dung tập trung vào API và công cụ HotSpot/JDK hiện hành cùng cơ chế Linux cgroup v2 và Kubernetes, không dựa vào cờ JVM đã bị loại bỏ hay hướng dẫn tùy chỉnh heap theo thói quen của JDK cũ.

## 1. Ba giới hạn khác nhau: heap, tiến trình và container

Xét một Pod có container chạy ứng dụng Java với:

```text
Kubernetes memory limit:  2 GiB
JVM maximum heap (-Xmx): 1 GiB
Java heap đang used:      600 MiB
```

Không thể kết luận container chỉ dùng 600 MiB hay còn chính xác 1.400 MiB. Có ít nhất ba miền cần tách biệt:

1. **Giới hạn heap của JVM:** `-Xmx`, hoặc kích thước tối đa JVM tự chọn bằng ergonomics. Đây là giới hạn không gian dành cho **đối tượng Java trên heap**, không phải hard cap tổng tiến trình.
2. **Bộ nhớ của tiến trình Java:** bao gồm heap **và** các vùng non-heap/native được tiến trình cấp phát, commit và sử dụng; ở mức OS thường theo dõi RSS/working set hoặc chỉ số tương đương.
3. **Bộ nhớ được tính cho container/cgroup:** có thể gồm bộ nhớ của **nhiều tiến trình trong cùng cgroup**, anonymous pages, page cache, memory-backed volumes, một số bộ nhớ kernel và các thành phần khác theo quy tắc accounting.

Sơ đồ tư duy:

```text
┌────────────────────────── container / cgroup ──────────────────────────┐
│  ┌────────────────────────── Java process ──────────────────────────┐  │
│  │  ┌────────── Java heap ──────────┐                              │  │
│  │  │ Objects, arrays, VT stack ... │                              │  │
│  │  └───────────────────────────────┘                              │  │
│  │  Metaspace, code cache, GC native, thread stacks, direct        │  │
│  │  buffers, FFM/JNI allocations, libc/native libraries ...        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  Các tiến trình con (nếu có), cache được charge, tmpfs, kernel ...    │
└───────────────────────────────────────────────────────────────────────┘
                         ↑
          memory limit áp dụng ở cấp cgroup
```

**Quy tắc cốt lõi:** `-Xmx=1g` **không có nghĩa** tiến trình Java tối đa 1 GiB, và `limit: 2Gi` **không có nghĩa** 2 GiB đều sẵn cho Java heap.

## 2. Kubernetes memory request không phải memory limit

Trong Kubernetes:

| Cấu hình | Vai trò chính | Điều không nên suy ra |
| --- | --- | --- |
| `resources.requests.memory` | Tài nguyên yêu cầu để scheduler quyết định bố trí Pod; liên quan QoS/eviction | Không phải hard cap bộ nhớ của container |
| `resources.limits.memory` | Giới hạn bộ nhớ được kernel/container runtime thực thi | Không phải giới hạn riêng cho Java heap |
| `-Xmx` hoặc `-XX:MaxRAMPercentage` | Xác định trần Java heap theo JVM | Không chặn mọi vùng native |
| `-XX:MaxDirectMemorySize` | Giới hạn một nhóm NIO direct-buffer allocations | Không giới hạn tất cả FFM/JNI/native memory |

Một container có request 512 MiB và limit 2 GiB có thể sử dụng **hơn 512 MiB** nếu node và chính sách cho phép. Nhưng khi mức sử dụng chịu giới hạn cgroup, kernel có thể reclaim bộ nhớ; nếu áp lực không được giải quyết, container có thể bị **OOM kill**.

Việc thực thi memory limit thường **mang tính phản ứng**: không nên mong container luôn thất bại đúng tại phép cấp phát vượt qua một con số không đổi. Kernel, page reclaim, swap policy và cgroup accounting quyết định lúc nào cần kill.

### 2.1. Đơn vị phải được ghi rõ

```yaml
resources:
  requests:
    memory: "1Gi"
  limits:
    memory: "2Gi"
```

Đây là **đoạn YAML minh họa** trong phần `resources` của container, chưa phải một Deployment manifest đầy đủ.

Trong Kubernetes:

- `1Gi` = 1.024 MiB (đơn vị nhị phân).
- `1Mi` = 1.048.576 byte.
- `M` và `G` là suffix đơn vị thập phân, **khác** `Mi` và `Gi`.
- Không dùng một số MiB tính nhẩm với `M` rồi mong hai giới hạn đúng bằng nhau.

Tùy chính sách namespace như `LimitRange`, Kubernetes còn có thể bổ sung giá trị request/limit mặc định. Khi chẩn đoán, kiểm tra **cấu hình thực sự của Pod sau admission**, không chỉ file YAML ban đầu.

## 3. Linux cgroup v2: nguồn sự thật về quota và mức sử dụng

Trên Linux với **cgroup v2**, các tệp thường dùng trong thư mục cgroup tương ứng là:

| Tệp | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `memory.max` | Hard memory limit; `max` nghĩa là không giới hạn tại mức cgroup này | Parent cgroup vẫn có thể đặt giới hạn |
| `memory.current` | Mức bộ nhớ **đang được charge** cho cgroup và hậu duệ | Không đồng nghĩa RSS riêng JVM |
| `memory.peak` | Mức sử dụng đỉnh nếu kernel hỗ trợ | Cần quan sát vòng đời counter |
| `memory.events` | Các bộ đếm như `high`, `max`, `oom`, `oom_kill` | Có thể gồm sự kiện ở cgroup con tùy tệp |
| `memory.events.local` | Bộ đếm sự kiện cục bộ của cgroup | Hữu ích khi cần phân biệt kế thừa |
| `memory.stat` | Thống kê các loại bộ nhớ như `anon`, `file`, `kernel` | Không cộng mọi dòng một cách máy móc |
| `memory.swap.max` | Chính sách giới hạn swap theo cgroup | Không thay `memory.max` |

Ví dụ kiểm tra bên trong một Linux container, **nếu đường dẫn root cgroup được mount tại vị trí phổ biến**:

```sh
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.stat
```

Nếu `memory.max` trả về:

```text
2147483648
```

thì hard limit tương ứng 2 GiB (2.147.483.648 byte).

**Không mặc định** mọi container đều có đúng đường dẫn `/sys/fs/cgroup/memory.max`. Cần xác định cgroup của tiến trình, mount path, parent cgroups và môi trường cgroup v1/v2 đang sử dụng. Trên cgroup v1, các tệp và tên thống kê **khác**.

### 3.1. cgroup memory.current không phải “heap đang dùng”

`memory.current` có thể bao gồm:

- Anonymous memory của tiến trình.
- File-backed pages/page cache được charge cho cgroup.
- Bộ nhớ trong filesystem dùng RAM, chẳng hạn `tmpfs`.
- Một số thành phần kernel theo cơ chế accounting của Linux.
- Các tiến trình con cùng cgroup hoặc hậu duệ được tính vào cgroup đó.

Do đó có thể xảy ra:

```text
JVM heap used:       750 MiB
JVM heap committed:  1.024 MiB
Java process RSS:    1.350 MiB
cgroup memory.current: 1.510 MiB
```

Các con số này là **ví dụ**, không phải quy luật phải giữ theo thứ tự như vậy. Chúng đo **những đại lượng khác nhau**. Page sharing, page cache, tiến trình con và cách kernel charge memory đều có thể tạo độ lệch.

### 3.2. Giới hạn của parent cgroup

Nếu cgroup tiến trình có `memory.max=max` nhưng một **ancestor cgroup** có hard limit, ứng dụng vẫn có thể chịu áp lực/giới hạn từ ancestor. Không kết luận “container không có giới hạn” chỉ từ một tệp ở cấp con nếu runtime tổ chức cgroup hierarchy khác với giả định.

Kubernetes còn có ngữ nghĩa giới hạn theo container/Pod tùy cấu hình. **Sidecar trong container khác** thường có cgroup giới hạn riêng; không cộng RSS của sidecar vào **container limit** của Java như thể luôn cùng cgroup. Tuy nhiên, tổng tài nguyên ở **cấp Pod/node** vẫn cần được quản lý.

## 4. Java 27 nhận diện container thế nào?

Trên **HotSpot Linux**, `-XX:+UseContainerSupport` được **bật mặc định**. JVM có thể dùng thông tin container được hỗ trợ để suy ra lượng bộ nhớ và CPU có sẵn, từ đó lựa chọn heap size và một số nguồn lực của runtime.

Điều này hữu ích nhưng có giới hạn:

1. JVM phải chạy trên một bản build và nền tảng hỗ trợ cơ chế phát hiện container tương ứng.
2. Các con số JVM quan sát được có thể khác giới hạn trong file YAML do cgroup hierarchy, việc không đặt limit, hoặc cấu hình môi trường.
3. Container awareness giúp tính kích thước **mặc định**; nó **không phải bộ điều khiển tổng RSS**.
4. Nếu người dùng đặt `-Xmx` cố định, JVM không tự hạ kích thước đó chỉ vì container hiện có limit thấp hơn.

Có thể kiểm tra trong image Linux đang chạy:

```sh
java -version
java -XshowSettings:system -version
java -XshowSettings:vm -version
java -Xlog:os+container=trace -version
```

- `-XshowSettings:system` hiển thị thông tin hệ thống/container (Linux).
- `-XshowSettings:vm` hiển thị cài đặt JVM, gồm thông tin heap.
- `-Xlog:os+container=trace` giúp chẩn đoán **cách HotSpot phát hiện** CPU/memory container; dùng mức trace khi điều tra, tránh log quá nhiều thường trực.

Tùy container image, cgroup mounts và cấu hình quyền, không phải mọi lệnh giám sát bên trong image đều có sẵn. Không bật `-XX:-UseContainerSupport` chỉ để “sửa” heap mà chưa xác minh nguyên nhân: tắt nhận diện container có thể làm JVM tính theo host RAM và tăng rủi ro OOMKilled.

## 5. Heap ergonomics: `-Xmx` và `-XX:MaxRAMPercentage`

Khi **không đặt `-Xmx`**, HotSpot dùng các quy tắc *ergonomics* để tính maximum heap theo tài nguyên phát hiện được và các cờ liên quan.

Các cờ quan trọng:

| Cờ | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `-Xmx<size>` | Chỉ định kích thước tối đa của Java heap | Đặt theo ngân sách, không phải bằng nguyên container limit |
| `-Xms<size>` | Chỉ định kích thước heap ban đầu/tối thiểu theo chính sách JVM | Kéo theo ảnh hưởng tới committed memory/GC |
| `-XX:MaxRAMPercentage=<percent>` | Chọn trần heap theo tỷ lệ của bộ nhớ khả dụng mà JVM phát hiện, trước các ràng buộc ergonomics | Trên JDK 27 HotSpot, mặc định là 25% |
| `-XX:InitialRAMPercentage=<percent>` | Tác động tới initial heap khi tính tự động | Đừng coi nó là giới hạn RSS |
| `-XX:MinRAMPercentage=<percent>` | Dùng trong quy tắc sizing cho **heap nhỏ** | Không có nghĩa “kích thước heap tối thiểu” |
| `-XX:MaxRAM=<size>` | Tham số ảnh hưởng mức RAM dùng bởi heap ergonomics | Không phải giới hạn bộ nhớ tiến trình ở OS |

Ví dụ hai chiến lược thay thế nhau cho container có limit 2 GiB:

**Chiến lược A: cố định rõ trần heap**

```sh
java -Xms256m -Xmx1024m -jar app.jar
```

**Chiến lược B: chọn tỷ lệ theo tài nguyên JVM nhận diện**

```sh
java -XX:MaxRAMPercentage=50.0 -jar app.jar
```

Nếu JVM thực sự thấy khoảng 2 GiB và các heuristic khác cho phép, tỷ lệ 50% sẽ **xấp xỉ** 1 GiB heap. Nhưng **không coi phép nhân này là bảo đảm kích thước chính xác** cho mọi collector, heap nhỏ, kiến trúc hoặc flag khác.

**Đừng dùng `-Xmx` và `MaxRAMPercentage` như hai trần độc lập cùng chia ngân sách.** Khi đã chỉ định `-Xmx`, đó là cấu hình trực tiếp của maximum heap; tỷ lệ sẽ không “giảm thêm” maximum heap lần nữa.

### 5.1. Mặc định 25% không phải khuyến nghị cho mọi service

Tài liệu lệnh `java` của JDK 27 mô tả mặc định `MaxRAMPercentage=25`. Điều này không có nghĩa 25% luôn là lựa chọn tốt nhất: ứng dụng heap-heavy có thể cần phần lớn RAM cho heap, trong khi ứng dụng dùng JNI/FFM/direct buffers có thể cần **tỷ lệ heap nhỏ hơn nhiều**.

Chọn dựa trên **live set, peak heap, GC behavior và non-heap/native memory thực đo**. Đừng thay mặc định bằng 80–90% chỉ vì service “chạy Java”.

### 5.2. Tự động chọn collector không phải cách giải quyết OOM

Theo hướng dẫn GC JDK 27, HotSpot mặc định chọn **G1** nếu không cấu hình collector khác. G1, ZGC hay collector khác có điểm mạnh riêng nhưng **collector nào cũng cần tài nguyên ngoài payload ứng dụng**.

Việc đổi collector có thể thay **native/GC overhead, mức commit và latency**, không tự biến container limit thành Java heap limit. Nên giữ collector mặc định trước khi tuning nếu không có bằng chứng cần thay.

## 6. Ngân sách bộ nhớ phải bao phủ toàn bộ tiến trình

Một mô hình lập kế hoạch thực dụng:

```text
M_limit
  >= M_heap
   + M_direct_buffers
   + M_class_metadata_and_code
   + M_thread_stacks
   + M_gc_and_other_native
   + M_extra_cgroup_charges
   + M_safety_headroom
```

Trong đó:

- `M_limit` là **giới hạn cgroup/container thực tế** cần tuân thủ.
- `M_heap` nên đặt mục tiêu theo **heap có thể committed ở đỉnh**, không chỉ heap used sau GC.
- `M_direct_buffers` là phần ngân sách cho NIO direct buffers và những vùng tương tự đã được kiểm kê.
- `M_class_metadata_and_code` gồm metaspace, class metadata và JIT code cache.
- `M_thread_stacks` là chi phí các platform thread stacks và thông tin thread liên quan.
- `M_gc_and_other_native` gồm cấu trúc GC, compiler/runtime, malloc, native libraries, FFM/JNI allocations...
- `M_extra_cgroup_charges` gồm những phần bị charge ngoài tiến trình Java khi có, như `tmpfs`, file cache, tiến trình con trong cgroup.
- `M_safety_headroom` để hấp thụ burst, chênh lệch ước lượng và yêu cầu vận hành.

**Đây là sơ đồ ngân sách, không phải công thức kế toán cộng trực tiếp các dashboard metrics.** Một số chỉ số có thể **chồng lấn** (ví dụ direct buffers đã nằm trong RSS hoặc trong một số thống kê native; heap committed cũng thuộc tổng NMT). Để tránh đếm đôi, xây dự toán từ **các nhóm không trùng nhau**, rồi xác minh bằng metric cấp tiến trình/cgroup.

## 7. Ví dụ phân bổ ngân sách cho container 2 GiB

Giả sử có **một Java service chính**, không có tiến trình native lớn, memory limit **2 GiB = 2.048 MiB**. Ta phác thảo một **ngân sách ban đầu để kiểm thử tải**, chưa phải cấu hình production đã được tối ưu:

| Nhóm | Ngân sách minh họa |
| --- | ---: |
| Java heap tối đa | 1.024 MiB |
| NIO direct buffers | 192 MiB |
| Class metadata/metaspace | 160 MiB |
| JIT code cache và vùng liên quan | 96 MiB |
| Platform thread stacks và thread-native | 128 MiB |
| GC structures, JVM runtime, JNI/FFM/other native | 128 MiB |
| File cache, tmpfs hoặc tiến trình phụ được charge | 64 MiB |
| **Dự phòng (headroom)** | **256 MiB** |
| **Tổng ngân sách** | **2.048 MiB** |

Các con số trên được cộng để thể hiện **một phương pháp hoạch định theo nhóm**, không phải cấu hình mặc định của Java 27 hay một bảo đảm rằng từng nhóm bị giới hạn cứng ở con số đó.

Một cấu hình JVM để **thử nghiệm** có thể là:

```sh
java \
  -Xms256m \
  -Xmx1024m \
  -XX:MaxDirectMemorySize=192m \
  -jar app.jar
```

Lưu ý:

- Cờ `-Xmx1024m` đặt trần heap, `MaxDirectMemorySize=192m` giới hạn một nhóm NIO direct-buffer allocations.
- **Không có cờ nào ở trên** đặt hard cap cho **tất cả** metaspace, thread stacks, GC overhead, FFM memory hoặc page cache.
- Hàng “Metaspace 160 MiB” là **dự toán theo kiểm thử**, không phải lệnh `-XX:MaxMetaspaceSize=160m`. Nếu tùy tiện đặt cap quá thấp, có thể gây `OutOfMemoryError: Metaspace`.
- Nếu peak RSS/cgroup usage vẫn tới sát 2 GiB, phải điều chỉnh ngân sách và concurrency chứ không giả định headroom trên giấy có thật.

### 7.1. Cách tính ngược từ hạn mức

Một cách ra quyết định dễ dùng hơn:

```text
Giới hạn:                      2048 MiB
Trừ non-heap/native/cache ước tính: 768 MiB
Trừ headroom mong muốn:         256 MiB
------------------------------------------------
Ngân sách heap có thể thử:      1024 MiB
```

Nếu đo thực tế cho thấy phần non-heap cần **1.050 MiB** ở peak, ngân sách heap 1.024 MiB sẽ không còn phù hợp. Cần thay cấu hình, giảm mức sử dụng, tăng giới hạn container hoặc đổi kiến trúc tác vụ.

### 7.2. Tỷ lệ heap là quyết định theo workload

| Workload | Khả năng cần cân nhắc |
| --- | --- |
| API đơn giản, nhiều Java objects, ít direct/native | Có thể dành tỷ lệ tương đối cao hơn cho heap |
| Nhiều TLS/network direct buffers | Đặt dự toán direct/native rõ ràng, không để heap chiếm gần hết |
| JNI, FFM, thư viện xử lý ảnh/media | Cần đo native memory riêng; `MaxDirectMemorySize` không kiểm soát toàn bộ |
| Nhiều platform threads | Dự trù stacks và runtime overhead |
| Nhiều virtual threads | Stack chunks chủ yếu ở heap, nhưng task-local objects, native I/O và downstream resources vẫn tốn memory |
| Java agent, dynamic class loading, proxy/code generation | Theo dõi metaspace, code cache và class loaders |
| Có `tmpfs` hoặc memory-backed `emptyDir` | Tính phần file-backed được charge vào container/cgroup |

Không có “phần trăm heap tốt nhất” dùng cho mọi tình huống.

## 8. Heap used, committed, maximum và RSS: không dùng thay nhau

Ở cấp JVM, các thông số có ý nghĩa khác nhau:

```text
Heap used       = bộ nhớ đang được các Java objects chiếm theo thống kê JVM
Heap committed  = phần dung lượng heap JVM đã commit từ hệ điều hành
Heap max        = trần heap mà JVM có thể sử dụng
Native reserved = khoảng địa chỉ ảo dành riêng, có thể chưa commit/đụng trang
RSS             = các trang cư trú trong RAM được OS tính cho một tiến trình
```

Ví dụ:

```text
Heap max:       1024 MiB
Heap committed: 768 MiB
Heap used:      420 MiB
Process RSS:    990 MiB
```

Đây là bốn con số **không bắt buộc bằng nhau**. Heap committed không đồng nghĩa toàn bộ trang đều đang resident, và RSS có thể bao gồm **native, shared mappings và heap pages**.

### 8.1. Reserved không đồng nghĩa consumed memory

Native Memory Tracking (NMT) phân biệt **reserved** và **committed**:

- `reserved`: vùng **không gian địa chỉ ảo** được dành để có thể dùng sau.
- `committed`: vùng được JVM cam kết sử dụng theo hệ thống cấp phát bộ nhớ của nó.

Không cộng mọi số `reserved` rồi kết luận tiến trình đã sử dụng chừng đó RAM thực. Ngược lại, committed cao cũng **không phải phép đo RSS tuyệt đối**: residency, sharing, page cache và memory mapping còn ảnh hưởng mức sử dụng thực tế.

### 8.2. Dùng heap after GC để đánh giá live set

Nếu ứng dụng chạy GC thường xuyên nhưng **heap used sau GC** tăng dần theo thời gian, có thể có live data tăng thật hoặc memory retention. Nếu heap used ổn định mà container memory vẫn tăng, cần điều tra native, direct, page cache hoặc tiến trình phụ.

Một lần đo duy nhất sau startup **không đủ**. Cần so sánh startup, warmup, steady state, peak và giai đoạn shutdown.

## 9. Những phần bộ nhớ ngoài heap hay bị bỏ sót

| Thành phần | Ví dụ sử dụng | Quan sát/giới hạn |
| --- | --- | --- |
| Metaspace/class metadata | Classes, class loaders, framework proxies | NMT Class/Metaspace, class loading metrics; `MaxMetaspaceSize` nếu có lý do |
| Code cache | JIT-compiled code | NMT Code, `jcmd Compiler.codecache` nếu được hỗ trợ |
| GC native structures | Collector bookkeeping, marking/remset, worker state | NMT GC; phụ thuộc collector và heap |
| Platform thread stacks | Request/worker/GC/JIT threads | NMT Thread, OS thread count; `-Xss` ảnh hưởng stack Java platform threads |
| Direct `ByteBuffer` | Networking, NIO, framework buffers | `BufferPoolMXBean`, `MaxDirectMemorySize` |
| Memory-mapped files | `FileChannel.map`, native mappings | OS/process mappings, page cache, RSS/cgroup |
| FFM/JNI/native allocations | `Arena.allocate`, C libraries | NMT chỉ nhìn phần JVM theo dõi; OS/native profiler cho thư viện ngoài |
| Java agent/profiler | Instrumentation, tracing, sampling | Có thể tăng heap, metaspace hoặc native |
| Process phụ | Shell helper, codec, CLI trong cùng cgroup | OS/cgroup metrics |
| `tmpfs`/memory-backed volume | File tạm trên RAM | `memory.stat`, kích thước volume, quota |

Một thực tế quan trọng: **không phải tất cả mục trong bảng đều có một JVM flag kiểm soát cứng**. Với native code bên thứ ba, có thể cần cấu hình thư viện hoặc cơ chế hạn chế ở tầng ứng dụng.

## 10. Direct memory khác FFM/JNI memory

`-XX:MaxDirectMemorySize` được tài liệu JDK 27 mô tả là giới hạn tổng kích thước các **NIO direct-buffer allocations** do cơ chế `java.nio` liên quan quản lý.

Ví dụ:

```sh
java -Xmx1024m -XX:MaxDirectMemorySize=192m -jar app.jar
```

Không suy ra giới hạn này chặn được:

- Mọi vùng do `java.lang.foreign.Arena.allocate(...)` cấp phát.
- Mọi `malloc` bên trong JNI/C libraries.
- Memory mappings/file cache dưới mọi hình thức.
- Metaspace, code cache và platform thread stacks.

Những vùng này có hợp đồng khác nhau. Nếu ứng dụng dùng FFM với nhiều native segments, **quản lý lifetime** (ví dụ confined/shared `Arena` được đóng đúng lúc) và hạn chế số tác vụ/khối dữ liệu đồng thời quan trọng hơn việc chỉ đặt một cờ cho NIO buffers.

### 10.1. Direct buffer metric cũng không phải toàn bộ native memory

`BufferPoolMXBean` có thể cung cấp `count`, `memoryUsed` và `totalCapacity` cho các buffer pools mà JVM quan sát được (như `direct` hoặc `mapped`).

Nhưng:

- Không phải mọi malloc/JNI/FFM allocation đều đi qua các buffer pools này.
- `memoryUsed` và `totalCapacity` đo các đại lượng khác nhau.
- Cần tránh cộng cả direct buffer memory vào một mục native memory vốn đã bao gồm nó khi lập bảng chi tiết.

## 11. Threads và stack memory: platform khác virtual

### 11.1. Platform thread stacks

Platform thread thường có stack gắn với luồng OS. Một ước lượng ban đầu:

```text
Stack budget ≈ number_of_platform_threads × per_thread_stack_footprint
```

Nhưng **footprint thực** không nhất thiết bằng `-Xss` nhân số thread vì reserved, committed và RSS khác nhau; còn có guard pages, native thread metadata và overhead.

`-Xss` cho phép cấu hình kích thước stack Java thread theo HotSpot. **Giảm quá thấp** có thể khiến `StackOverflowError`; giữ nhiều thread sống vẫn có overhead. Khi tăng concurrency, theo dõi thread count và NMT Thread thay vì chỉ xem heap.

### 11.2. Virtual thread stacks không tính đơn giản như platform stack

Virtual threads trong Java hiện đại lưu phần lớn **stack frames/stack chunks** dưới dạng đối tượng trên Java heap. Vì vậy không lấy `số virtual threads × -Xss` để suy ra native memory.

Tuy nhiên, mỗi virtual thread vẫn có:

- Thông tin về tác vụ, trạng thái, đối tượng và stack chunks.
- Dữ liệu capture, `ThreadLocal`/context nếu ứng dụng dùng.
- I/O state, futures, timeout, buffers hoặc thông tin framework.
- Các tài nguyên downstream mà tác vụ đang giữ hoặc chờ.

**Hàng chục nghìn virtual threads không miễn phí về bộ nhớ.** Nếu mỗi task giữ một buffer lớn hoặc đang chờ một connection, heap/native/cgroup memory vẫn có thể tăng nhanh.

## 12. Metaspace, class loading, JIT và GC overhead

**Metaspace** quản lý class metadata bên ngoài Java heap. Một hệ thống dùng nhiều class loaders, dynamic proxies hoặc sinh bytecode có thể tăng metaspace ngay cả khi heap used ổn định.

`-XX:MaxMetaspaceSize=<size>` giới hạn metadata space theo contract HotSpot; đây là **tùy chọn có rủi ro** nếu đặt thấp hơn nhu cầu thực tế.

`-XX:MetaspaceSize` chủ yếu liên quan ngưỡng khởi đầu gây thu gom rác vì áp lực class metadata; **không phải hard cap** giống `MaxMetaspaceSize`.

**Code cache** lưu mã máy do JIT biên dịch. **GC native structures** phục vụ collector, có thể tăng/giảm theo heap layout và collector đang dùng.

Khi tính ngân sách:

1. Đo metaspace/class loading ở steady state và sau giai đoạn warmup.
2. Tính thêm khi ứng dụng có agent hoặc hot-reload/dynamic class loading.
3. Theo dõi NMT Code và GC thay vì giả định mọi overhead là 10% của heap.
4. Đừng tự hạ trần metaspace/code cache cực thấp để “tiết kiệm RAM” nếu chưa kiểm thử workload.

## 13. Page cache, tmpfs và memory-backed volumes

Container memory không chỉ phục vụ tiến trình Java:

- File-backed pages được kernel cache có thể được charge vào cgroup.
- `tmpfs` hoặc memory-backed `emptyDir` trong Kubernetes có thể tiêu thụ bộ nhớ tính vào limit container/Pod theo quy tắc sử dụng.
- Một chương trình tạo nhiều file tạm trong RAM có thể khiến `memory.current` tăng mà Java heap used gần như không thay đổi.

Điều này quan trọng với:

- HTTP upload/download có staging vào file tạm.
- Giải nén archive, build artifacts, generated reports.
- Xử lý ảnh, video hoặc machine learning có intermediate files.
- Java service ghi heap dump, thread dump hoặc profiler output vào vùng filesystem dùng RAM.

Không coi “dùng file” là không chiếm memory. Nhưng cũng không coi **mọi page cache đều không thể reclaim**: kernel có thể giải phóng một phần cache dưới áp lực, tùy loại trang và chính sách.

Nếu dùng `emptyDir.medium: Memory`, cân nhắc cấu hình `sizeLimit` và giám sát volume thực tế; một volume RAM lớn có thể làm container bị OOM ngay cả khi JVM heap chưa cao.

## 14. Quan sát bộ nhớ từ bên trong Java bằng API chuẩn

Để có phép đo nhẹ và tự chứa, dùng `MemoryMXBean` và `BufferPoolMXBean`. Hai interface này không đo toàn bộ cgroup, nhưng cung cấp bức tranh JVM có ích.

Tạo file `MemoryBudgetProbe.java`:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.util.List;

public final class MemoryBudgetProbe {

    private MemoryBudgetProbe() {}

    private static String mib(long bytes) {
        if (bytes < 0) {
            return "unknown";
        }
        return String.format("%.1f MiB",
                bytes / (1024.0 * 1024.0));
    }

    private static void showUsage(String label, MemoryUsage usage) {
        System.out.printf(
                "%s: used=%s, committed=%s, max=%s%n",
                label,
                mib(usage.getUsed()),
                mib(usage.getCommitted()),
                mib(usage.getMax())
        );
    }

    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

        System.out.println("Available processors: "
                + runtime.availableProcessors());
        System.out.println("Runtime.maxMemory(): "
                + mib(runtime.maxMemory()));

        showUsage("Heap", memory.getHeapMemoryUsage());
        showUsage("Non-heap", memory.getNonHeapMemoryUsage());

        List<BufferPoolMXBean> pools =
                ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class);

        for (BufferPoolMXBean pool : pools) {
            System.out.printf(
                    "Buffer pool %s: count=%d, used=%s, capacity=%s%n",
                    pool.getName(),
                    pool.getCount(),
                    mib(pool.getMemoryUsed()),
                    mib(pool.getTotalCapacity())
            );
        }

        System.out.println("Heap used is not container memory!");
    }
}
```

Biên dịch/chạy bằng JDK 27:

```sh
javac -encoding UTF-8 MemoryBudgetProbe.java
java -Xms128m -Xmx512m MemoryBudgetProbe
```

**Kết quả phụ thuộc vào môi trường**, ví dụ `Runtime.maxMemory()` có thể gần 512 MiB, còn `heap committed` và `heap used` thường khác nhau. Không có output số cố định vì giá trị thay đổi theo JDK build, class loading, heap ergonomics và thời điểm chạy.

### 14.1. Giới hạn của phép đo này

`MemoryMXBean` không bao phủ toàn bộ native allocations. `BufferPoolMXBean` không đo toàn bộ JNI/FFM memory. `Runtime.maxMemory()` không phải “bộ nhớ còn trống của container”. Vì vậy kết quả cần được so với:

- JVM NMT/GC metrics.
- Process RSS và thread count ở hệ điều hành.
- cgroup `memory.current`, `memory.stat`, `memory.events`.
- Kubernetes metrics/trạng thái Pod trong suốt vòng đời workload.

## 15. Native Memory Tracking (NMT): nhìn vào bên trong JVM

**Native Memory Tracking** giúp HotSpot báo cáo những vùng bộ nhớ mà JVM theo dõi: Java heap, Class, Thread, Code, GC, Compiler và các phân loại khác.

Bật khi khởi động để chẩn đoán:

```sh
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Hoặc với yêu cầu phân tích sâu hơn:

```sh
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Khi tiến trình còn chạy, từ môi trường có công cụ `jcmd` và quyền attach phù hợp:

```sh
jcmd -l
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

`<pid>` là placeholder để thay bằng PID Java thực tế. `summary.diff` so mức sử dụng với baseline. Cần lấy baseline ở thời điểm có ý nghĩa như **sau warmup** rồi so tại các mốc tải.

**NMT không được bật mặc định.** Oracle ghi nhận NMT có thể gây overhead hiệu năng/metadata đáng kể (tài liệu nêu khoảng 5–10% trong trường hợp điển hình), nên cân nhắc bật ở môi trường điều tra thay vì luôn bật `detail` trong production.

### 15.1. NMT không phải công cụ đo toàn bộ RSS

NMT theo dõi những vùng JVM quản lý và biết cách ghi nhận; nó **không quan sát đầy đủ** memory mà mã native bên thứ ba cấp phát ngoài JVM.

Nếu:

```text
cgroup memory.current tăng
NMT committed gần như không đổi
```

có thể cần kiểm tra thêm:

- JNI/C libraries tự `malloc`.
- Memory-mapped files và page cache.
- `tmpfs`/memory-backed volume.
- Tiến trình phụ.
- Độ lệch giữa committed, resident và cgroup accounting.

**Không lấy `NMT Total reserved` trừ `RSS` rồi coi chênh lệch đó là “memory leak”.** Hai số đo không cùng ngữ nghĩa.

## 16. Công cụ jcmd, GC log và JVM flags

Một số lệnh chẩn đoán thường dùng với JDK 27:

```sh
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
jcmd <pid> VM.native_memory summary
```

Các lệnh này **phụ thuộc JVM/JDK, quyền attach và cấu hình image**. Có thể kiểm tra:

```sh
jcmd <pid> help
```

Để xem những cờ mà HotSpot thực sự tính được trên **cùng image/container runtime**:

```sh
java -XX:+PrintFlagsFinal -version
```

Trong output, tìm các cờ như `MaxHeapSize`, `InitialHeapSize`, `MaxRAMPercentage`, `UseContainerSupport`, `MaxDirectMemorySize`. Một số cờ có thể là giá trị được tự động suy ra hoặc chưa được đặt tường minh; diễn giải cùng mức container limit.

### 16.1. GC log giúp giải thích áp lực heap

Ví dụ bật GC logging bằng Unified Logging hiện hành:

```sh
java -Xlog:gc*:stdout:time,level,tags -Xmx1024m -jar app.jar
```

Quan sát:

- Heap used trước/sau các đợt GC.
- Tần suất/chi phí của GC.
- Heap occupancy ở peak.
- Pause time/throughput và các cảnh báo liên quan.

GC log **không thay** cgroup metrics: OOMKilled có thể xảy ra dù GC log không có `OutOfMemoryError`, và một JVM có thể báo heap OOME trước khi cgroup memory.max bị đụng tới.

## 17. Phân biệt Java OutOfMemoryError và container OOMKilled

Đây là hai đường lỗi quan trọng:

| Tín hiệu | Ý nghĩa thường gặp | Cần xem |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Không thể cấp phát object trong giới hạn heap | Heap occupancy, GC, live set, `-Xmx` |
| `OutOfMemoryError: Metaspace` | Không đủ không gian class metadata theo giới hạn/điều kiện | Class loaders, dynamic generation, metaspace budget |
| `OutOfMemoryError: Direct buffer memory` | NIO direct-buffer allocation không đáp ứng yêu cầu | NIO buffer pools, direct cap, cleanup/references |
| `unable to create native thread` hoặc lỗi native allocation | OS/native resource, thread/memory quota bị giới hạn | Thread count, stacks, ulimit, native budget |
| Kubernetes `OOMKilled` | Kernel/container runtime báo tiến trình bị kill dưới áp lực cgroup memory | `kubectl describe pod`, container last state, cgroup events |
| Exit code `137` | Thường tương ứng tiến trình chết bởi SIGKILL (128 + 9) | **Không đủ để kết luận nguyên nhân chắc chắn là OOM** |

**Java OOME** có thể được JVM ném dưới dạng exception; ứng dụng có thể ghi lại stack trace nếu còn khả năng. **Container OOM kill** là hành vi bên ngoài JVM: tiến trình có thể bị kết thúc đột ngột, **không có heap dump hay Java exception**.

### 17.1. Quy trình phân loại khi Pod restart

```sh
kubectl get pod <pod-name> -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
```

Các placeholder trong dấu ngoặc nhọn cần được thay bằng tên thật khi chạy.

Đọc:

1. `Last State: Terminated` và `Reason: OOMKilled` có xuất hiện không?
2. Memory limit/request thực tế của container là bao nhiêu?
3. Memory usage/working set/peak trước restart là gì?
4. JVM có log `OutOfMemoryError`, `GC overhead limit exceeded` hay lỗi native allocation không?
5. Có file tạm, native memory, nhiều tasks hoặc child processes tăng mạnh không?
6. Có thay đổi rollout, GC, thread/concurrency, thư viện native hoặc class loading ngay trước sự cố không?

Khi cần bằng chứng kernel-level, có thể dùng `memory.events` hoặc log node qua công cụ vận hành được cấp quyền. Không giả định container image nào cũng có `kubectl` hay có quyền đọc kernel log.

## 18. Heap dump và crash artifacts cũng tiêu thụ tài nguyên

Các cờ hiện hành:

```sh
java \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/diagnostics \
  -jar app.jar
```

Heap dump có thể rất lớn, mang dữ liệu nhạy cảm và tiêu thụ disk hoặc memory-backed filesystem. Cần:

- Chọn nơi lưu có dung lượng đủ và chính sách bảo vệ dữ liệu.
- Không ghi vào `tmpfs` thiếu giới hạn rồi khiến cgroup bị memory pressure nặng hơn.
- Không kỳ vọng dump luôn sinh được khi container bị kernel SIGKILL.
- Cân nhắc kiểm soát retention và quyền truy cập.

Cờ liên quan như `-XX:+ExitOnOutOfMemoryError` có thể hữu ích trong chính sách khởi động lại dịch vụ, nhưng **không phải cách chữa lỗi sử dụng bộ nhớ**. Khi thay đổi hành vi OOME, phải kiểm tra hợp đồng availability, restart policy và log/dump trong môi trường thực tế.

## 19. Tối ưu bộ nhớ phải xem cả số tác vụ đồng thời

Một service có `-Xmx1024m` có thể chạy ổn ở 100 concurrent requests nhưng OOMKilled ở 20.000 requests. Nguyên nhân có thể là:

- Mỗi request giữ buffer 64 KiB, session objects hoặc cached response.
- Nhiều virtual threads đang chờ downstream I/O, giữ request body và task-local data.
- NIO direct buffers tăng theo số kết nối.
- Connection pool, TLS/session state hoặc native I/O tăng.
- File tạm/stream buffering lớn trong `tmpfs`.

Ví dụ sơ bộ:

```text
20.000 concurrent requests × 64 KiB buffered/request
  = 1.250 MiB dữ liệu đệm lý thuyết
```

Con số trên **chỉ là phép tính dung lượng**, không tính object headers, metadata và các bản sao dữ liệu. Nó cho thấy điều chỉnh `-Xmx` đơn độc không giải quyết được mô hình concurrency giữ quá nhiều dữ liệu.

Cách ứng phó:

1. Giới hạn kích thước request/response và buffering.
2. Giới hạn concurrency theo **năng lực downstream** và ngân sách bộ nhớ.
3. Dùng backpressure/admission control ở ranh giới tiếp nhận.
4. Stream dữ liệu thay vì luôn giữ toàn bộ payload trong RAM khi phù hợp.
5. Đóng tài nguyên native/FFM/files/connections đúng lifetime.
6. Thử tải tại mức concurrent requests/queue depth tương đương production.

### 19.1. CPU quota cũng gián tiếp ảnh hưởng RAM

CPU bị giới hạn có thể khiến GC/worker threads tiến triển chậm, requests hoàn thành chậm hơn và tăng số công việc đang chờ. Vì vậy CPU throttling có thể làm **live objects và số in-flight tasks tăng**, dù mỗi request không dùng thêm bộ nhớ.

Khi điều tra memory pressure, theo dõi cùng lúc CPU limit/throttling, request latency, queue depth, GC logs và downstream latency.

## 20. Chiến lược sizing theo hai lần đo

**Vòng đầu — lập ngân sách trước khi chạy:**

1. Lấy memory limit/request thực của Pod/container.
2. Xác nhận JDK 27 nhận diện container đúng.
3. Chọn trần heap có để phần cho native/non-heap/cache.
4. Liệt kê thành phần native đặc thù: direct buffers, FFM, JNI, stacks, agents.
5. Chừa headroom cho peak và thay đổi khi deploy.

**Vòng sau — kiểm chứng bằng dữ liệu tải:**

1. Chạy warmup tới khi class loading và JIT ổn định.
2. Đo heap used/committed/max, NMT committed, direct buffers, RSS, cgroup memory.current.
3. Đo peak ở tải dự kiến và burst; chạy nhiều thời điểm, không chỉ mẫu đơn lẻ.
4. Theo dõi memory.events, GC latency, throughput và memory sau tải giảm.
5. Nếu heap thiếu nhưng native còn nhiều, cân nhắc điều chỉnh heap. Nếu native/cgroup tăng, không chỉ tăng heap.
6. Điều chỉnh container limit/requests và concurrency đồng thời; kiểm tra khả năng scheduling và chi phí.
7. Lưu lại cấu hình, biểu đồ và điều kiện tải làm baseline cho lần rollout tiếp theo.

Tối ưu đúng là **tìm một bộ giới hạn bền vững**, không chỉ làm ứng dụng chạy qua một lần benchmark.

## 21. Sơ đồ chẩn đoán khi bộ nhớ vượt dự kiến

```text
Service chậm / restart / memory tăng
              │
              ▼
   Container có OOMKilled?
        ┌─────┴─────┐
       Có          Không
        │            │
        ▼            ▼
 So cgroup peak   Có Java OOME?
 với limit         ┌─────┴─────┐
        │         Có          Không
        ▼          │            │
 Heap cao?         ▼            ▼
 ├─ Có → GC,    Đọc loại    Đo heap, NMT,
 │  live set,   OOME        direct, RSS,
 │  Xmx         (heap,      cgroup trend
 └─ Không →     meta,           │
    native,     direct...)       ▼
    direct,       │        Tìm memory tăng
    tmpfs,       ▼         theo throughput /
    page cache,  Chọn      thời gian / tasks
    child proc   đúng
                 subsystem
```

Bài toán cần đo **đúng miền bộ nhớ** trước khi thay cờ JVM. Nếu nguyên nhân là memory-backed file hay native allocation, tăng `-Xmx` thậm chí có thể làm container sớm OOMKilled hơn.

## 22. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt `-Xmx=limit container` | Không còn ngân sách cho JVM native/OS charges | Chừa non-heap, native và headroom |
| Đọc `heap used` như RSS | Bỏ sót heap committed và vùng khác | Dùng JVM + OS + cgroup metrics |
| Nghĩ `MaxRAMPercentage` giới hạn tổng tiến trình | Native allocation vẫn vượt ngân sách | Dùng công thức toàn tiến trình, đo cgroup |
| Giả định `request.memory` là hard cap | Hiểu sai scheduler/QoS | Phân biệt request với limit |
| Dùng `-XX:-UseContainerSupport` để “chữa” OOM | JVM có thể tính theo host | Xác nhận container detection đúng |
| Mặc định mọi container có cgroup v2 path cố định | Script monitoring sai môi trường | Phát hiện mount/cgroup path thực tế |
| Coi `memory.current` bằng RSS Java | Chênh do page cache/child process | Theo dõi memory.stat và process metrics |
| Cộng NMT Total + RSS + direct memory | Đếm trùng bộ nhớ | Phân nhóm, dùng NMT để drill down |
| Nhìn NMT reserved và coi đó là RAM đã dùng | Nhầm address space với RAM resident | Phân biệt reserved/committed/RSS |
| Giả định NMT thấy toàn bộ JNI/native malloc | Bỏ sót external allocations | Kết hợp OS/native profiler |
| Dùng `MaxDirectMemorySize` làm cap FFM | Off-heap ngoài NIO vẫn tăng | Quản lý Arena/native memory theo scope |
| Nhầm `MaxMetaspaceSize` với `MetaspaceSize` | Chọn sai giới hạn | Đọc đúng mục đích cờ |
| Giảm `-Xss` cực thấp cho mọi thread | StackOverflowError/khó debug | Đo platform threads; tuning có kiểm thử |
| Nhân virtual threads × `-Xss` để dự đoán native stacks | Mô hình sai | Tính VT stack chunks và task data trên heap |
| Tăng `-Xmx` khi memory.current đang sát limit | Tăng rủi ro OOMKilled | Tìm nguyên nhân native/cache và tăng limit nếu cần |
| Kết luận exit 137 luôn là OOMKilled | Có thể do SIGKILL nguyên nhân khác | Xem Last State/cgroup events/node logs |
| Chờ Java stack trace khi kernel OOM kill | Có thể không có exception/dump | Dùng kernel/cgroup/Kubernetes evidence |
| Ghi heap dump vào tmpfs không kiểm soát | Có thể tiêu thụ giới hạn memory | Chọn nơi lưu và quota phù hợp |
| Chỉ test một request, không test burst | Bỏ sót buffer/task memory peak | Load test theo concurrency thực |
| Cho rằng GC collector nào cũng có overhead như nhau | Sai dự toán native/latency | Đo theo collector và JDK thực tế |
| Dùng một tỷ lệ heap chung cho mọi service | Thiếu bộ nhớ native với workload đặc thù | Dựa trên memory profile từng service |

## 23. Checklist trước khi phát hành Java 27 trong container

1. **Đã biết memory limit thực của container chưa?** Xem cấu hình Pod sau admission và cgroup limit.
2. **JDK đã nhận diện container đúng chưa?** Kiểm tra `-XshowSettings:system` và HotSpot container logs.
3. **Đang dùng `-Xmx` cố định hay percentage?** Không nhầm hai chiến lược.
4. **Heap max bao nhiêu so với container limit?** Có còn không gian cho native/GC và headroom?
5. **Đã ước tính metaspace, code cache, direct buffers, stacks chưa?** Đo thay vì đoán từ heap.
6. **Ứng dụng dùng FFM/JNI hay mmap không?** Quản lý lifetime, đo OS metrics.
7. **Có memory-backed volume hoặc process phụ không?** Tính phần charge tương ứng.
8. **Số platform/virtual threads và concurrency đỉnh?** Theo dõi task-local buffers, queue và downstream.
9. **Có GC log và NMT khi điều tra không?** Biết chi phí của NMT.
10. **Cgroup memory.current, peak, events được thu thập không?** Đối chiếu cùng timestamps với JVM metrics.
11. **Đã phân biệt Java OOME với kernel OOM kill?** Có playbook thu thập bằng chứng.
12. **Heap dump/crash files có nơi lưu an toàn không?** Tránh tạo áp lực mới vào RAM.
13. **Đã thử tải ở mức burst và sau warmup?** Peak memory có thể xuất hiện sau class loading/JIT.
14. **Có headroom cho rollout, thay đổi workload và độ lệch đo lường không?** Không đặt kế hoạch sát limit.
15. **Đã thử với đúng image/JDK/collector/container runtime?** Kết quả ở host không thay test trong container.
16. **Có cảnh báo theo cả cgroup memory pressure lẫn heap occupancy?** Một dashboard heap đơn độc là không đủ.

**Kết luận:** Trong Java 27, giới hạn bộ nhớ của container là **ngân sách cho toàn bộ tài nguyên bị charge vào cgroup**, còn `-Xmx` chỉ kiểm soát **Java heap**. Quy trình đáng tin là: **xác nhận giới hạn cgroup → chọn heap hợp lý → dành chỗ cho native/non-heap và page cache → đo ở peak → giữ headroom**. Chỉ sau khi biết miền bộ nhớ nào tăng mới nên điều chỉnh GC hoặc các cờ JVM liên quan.

## 24. Tài liệu chính thức và nguồn tham khảo

- [The `java` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): `-Xmx`, `-Xms`, `-XshowSettings:system`, `-XX:MaxRAMPercentage`, `-XX:+UseContainerSupport`, `-XX:MaxDirectMemorySize`, `-XX:MaxMetaspaceSize`, `-XX:NativeMemoryTracking`, container logs.
- [Java SE 27 Garbage Collection Tuning Guide — Ergonomics](https://docs.oracle.com/en/java/javase/27/gctuning/ergonomics.html): lựa chọn collector/heap mặc định và nguyên tắc tuning theo hành vi.
- [Java SE 27 Troubleshooting Guide — Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html): NMT categories, reserved/committed, `jcmd` và phân tích memory usage.
- [Java SE 27 Troubleshoot Memory Leaks](https://docs.oracle.com/en/java/javase/27/troubleshoot/troubleshooting-memory-leaks.html): bật NMT, baseline/summary.diff và giới hạn với allocations ngoài JVM.
- [The `jcmd` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): các lệnh `VM.flags`, `GC.heap_info` và `VM.native_memory`.
- [`java.lang.management.MemoryMXBean` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap memory usage.
- [`java.lang.management.BufferPoolMXBean` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): NIO buffer pool count, memory used và capacity.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): requests, limits, cgroup/OOM kill và page cache/tmpfs.
- [Kubernetes — Assign Memory Resources to Containers and Pods](https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/): đơn vị Mi/Gi, scheduling và ví dụ OOMKilled.
- [Linux kernel documentation — Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `memory.max`, `memory.current`, `memory.stat`, `memory.events` và accounting theo cgroup.
