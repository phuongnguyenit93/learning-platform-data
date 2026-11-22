# 3.7 Đối chiếu giới hạn CPU, bộ nhớ và tài nguyên nhìn thấy từ JVM với môi trường triển khai

## Mục tiêu học tập

Khi một dịch vụ Java chạy ổn trên máy phát triển nhưng bị chậm, thiếu bộ nhớ hoặc tự thoát trong container, câu hỏi đầu tiên không nhất thiết là “đoạn code nào sai?”. Cần xác định **môi trường triển khai cho phép tiến trình sử dụng tài nguyên nào**, **hệ điều hành/container thực sự đang áp giới hạn nào** và **JVM đã phát hiện, cấu hình và sử dụng các tài nguyên đó ra sao**.

Sau bài này, bạn có thể:

- Phân biệt tài nguyên **máy chủ/node**, **pod/container**, **process** và **JVM**; không nhầm request/limit với lượng tài nguyên JVM chắc chắn có.
- Giải thích CPU quota, CPU affinity/cpuset, số processor JVM nhìn thấy, CPU throttling và ảnh hưởng đến GC, thread pool hoặc throughput.
- Phân biệt **memory limit của container** với **Java heap tối đa**, heap đang commit/đang dùng, native memory, thread stacks, direct buffers, metaspace và page cache.
- Đọc và đối chiếu thông tin từ **deployment spec**, **cgroup**, **JVM runtime/flags** và **metrics trong cùng khoảng thời gian**.
- Phân tích các kịch bản CPU throttling, `OutOfMemoryError` trong Java, kernel OOM kill, giới hạn PID/file descriptor mà không kết luận nguyên nhân quá sớm.
- Ghi một báo cáo chẩn đoán có chứng cứ, nêu rõ nguồn số liệu, thời điểm, khác biệt cấu hình và giới hạn suy luận.

## 1. Bốn góc nhìn tài nguyên cần đối chiếu

Trong hệ thống triển khai Java, “máy có 16 CPU và 64 GiB RAM” **không** bảo đảm JVM được quyền dùng toàn bộ số đó. Một container có thể bị giới hạn 1,5 CPU và 1 GiB RAM; JVM có thể thấy số processor khác con số CPU vật lý, đồng thời heap được đặt nhỏ hơn memory limit.

| Lớp quan sát | Có gì ở lớp đó? | Có thể đọc từ đâu? | Điều không nên suy ra |
| --- | --- | --- | --- |
| **Host/node** | CPU logic, RAM, kernel, áp lực tài nguyên của máy, workload khác cùng node | OS/node metrics, thông tin máy | Toàn bộ CPU/RAM của node đều thuộc về container |
| **Orchestrator/deployment** | CPU/memory **requests và limits**, số replicas, image, cấu hình và chính sách vận hành | Kubernetes Pod/Deployment spec, Docker/VM config | “Request = limit” hoặc “spec đã khai báo = giới hạn thực tế tại mọi thời điểm” |
| **Container/process** | cgroup CPU quota, cpuset, memory limit/current, PID limit, file descriptors, process RSS, CPU usage/throttling | `/sys/fs/cgroup`, `/proc`, container/runtime metrics | cgroup memory usage đồng nghĩa Java heap; CPU quota đồng nghĩa số core chuyên dụng |
| **JVM** | `availableProcessors()`, max/committed/used heap, GC threads, JVM flags, native allocation, thread count | Java API, `java -XshowSettings`, `jcmd`, JFR, GC logs | JVM nhìn thấy bao nhiêu thì hệ thống đang sử dụng bấy nhiêu |

Đường suy luận đúng có dạng:

```text
Host/node capacity
    |
    v
Deployment: CPU/memory requests & limits, replicas, placement
    |
    v
Kernel/container: cgroup, cpuset, affinity, PID/FD constraints
    |
    v
JVM: resource detection + startup flags + memory allocation
    |
    v
Actual process usage, GC/threads, latency, errors, OOM/throttling
```

**Lưu ý:** đây là mô hình khái niệm. Giới hạn có thể được kế thừa từ cgroup cha; nhiều container trong cùng pod có giới hạn khác nhau; một môi trường VM không có Kubernetes thì tầng orchestration tương ứng có thể là cấu hình hypervisor hoặc systemd. Khi điều tra phải ghi **đúng container chứa tiến trình Java** và **cùng một thời điểm quan sát**.

## 2. CPU: giới hạn thời gian chạy khác với số processor

### 2.1 CPU vật lý, logical CPU, quota và cpuset

Các đại lượng thường bị nhầm:

- **Host logical CPUs:** số processor logic mà OS nhìn thấy trên máy chủ. Đây là tài nguyên tổng của node, không nhất thiết thuộc về container.
- **CPU request** trong Kubernetes: lượng CPU dành cho scheduling/đảm bảo tương đối khi có tranh chấp; chẳng hạn `500m` tương đương yêu cầu 0,5 CPU. Request tự nó không phải mức trần cứng về thời gian CPU.
- **CPU limit:** mức CPU time được phép tiêu thụ theo cơ chế quota khi có limit; ví dụ `1500m` nghĩa là bình quân tương đương 1,5 CPU theo chu kỳ giới hạn, **không phải** có đúng 1,5 lõi vật lý độc quyền.
- **CPU quota/period** (Linux cgroup): quota thời gian CPU cho một chu kỳ. Trong cgroup v2, `cpu.max` thường có dạng `quota period` với đơn vị microsecond hoặc `max period` nếu không đặt quota tại cấp đó.
- **cpuset/affinity:** danh sách CPU logic mà tiến trình/luồng được phép chạy. Có thể hẹp hơn tài nguyên host và kết hợp với quota.
- **`Runtime.availableProcessors()`:** số processor **dạng số nguyên** mà JVM báo đang khả dụng cho chương trình; giá trị chịu ảnh hưởng bởi container detection, affinity, phiên bản JDK, flags và đôi khi cập nhật khi môi trường thay đổi.

Giả sử Linux cgroup v2 có:

```text
cpu.max = 150000 100000
```

Quy đổi giới hạn trung bình:

```text
150000 microsecond CPU / 100000 microsecond period
= 1.5 CPU-equivalents
```

Nghĩa là container có thể chạy trên nhiều CPU logic (tùy affinity/cpuset), nhưng tổng thời gian CPU tiêu thụ bị kiểm soát theo quota. Khi hết ngân sách trong chu kỳ, các thread có thể bị **throttled** đến kỳ tiếp theo. Vì `availableProcessors()` chỉ trả số nguyên và còn phụ thuộc chính sách phát hiện, **không được mặc định** nó nhất thiết sẽ trả `1` hay `2` chỉ dựa vào phép chia 1,5.

Trường hợp:

```text
cpu.max = max 100000
```

chỉ cho biết **không có giới hạn quota được đặt bởi chính `cpu.max` ở cgroup đó**. Nó không loại trừ giới hạn do cgroup cha, affinity/cpuset, CPU shares/weight hoặc tải cạnh tranh trên node.

### 2.2 CPU JVM thấy tác động đến hành vi gì?

Số processor JVM phát hiện có thể được dùng bởi runtime và các thư viện để chọn mức song song mặc định, chẳng hạn kích thước hoặc chiến lược một số thread pool và số luồng GC/JIT. Tuy nhiên:

- Số thread đang tạo **không bằng** số CPU được cấp.
- Một pool 64 worker trên container quota thấp có thể làm tăng contention, context switch hoặc queueing; nhưng nếu nhiều worker đang chờ I/O thì không thể kết luận 64 worker tự động là quá nhiều.
- CPU throttling có thể làm tăng wall-clock latency dù thuật toán tiêu tốn cùng lượng CPU time.
- Khi dùng `-XX:ActiveProcessorCount=N`, JVM có thể dùng giá trị override cho số processor mà nó báo và một số heuristic. Flag này **không tăng** quota CPU thật do kernel áp đặt.
- CPU utilization đo bởi JVM, container, node và monitoring platform có thể dùng **mẫu số khác nhau** (một core, toàn node, quota, request...), nên “100% CPU” phải đi cùng định nghĩa metric.

Trong JDK 17 HotSpot phổ biến trên Linux, container support thường được bật mặc định, nhưng cách đọc cgroup v1/v2 và xử lý quota/cpuset có thể khác theo bản JDK/vendor/patch hoặc flags. Hãy xác nhận **bản JDK đang chạy** và những gì **tiến trình thực sự phát hiện**; đừng chỉ suy từ documentation của một phiên bản khác.

### 2.3 Dấu hiệu CPU throttling

Trong cgroup v2, `cpu.stat` có thể chứa các bộ đếm như `nr_periods`, `nr_throttled` và `throttled_usec` (cùng các trường khác tùy kernel). Phải quan sát **mức tăng của counter trong cùng cửa sổ** với latency/throughput thay vì đọc một giá trị tích lũy rồi kết luận.

Ví dụ: khi offered load giữ ổn định, `nr_throttled` tăng mạnh, throughput hoàn tất đứng yên, backlog và p99 tăng. Điều này **ủng hộ giả thuyết** quota gây nghẽn. Cần đối chiếu thêm CPU usage, runnable threads, downstream waits, GC và thời gian bắt đầu hiện tượng; một bộ đếm throttling khác 0 tự nó chưa chứng minh nguyên nhân gốc.

## 3. Memory: giới hạn container không phải kích thước Java heap

### 3.1 Cấu trúc bộ nhớ của một tiến trình JVM

Trong Java, `-Xmx` hay `Runtime.maxMemory()` chủ yếu đề cập đến **giới hạn tối đa của Java heap**. Tiến trình còn có rất nhiều phần dùng bộ nhớ khác:

| Thành phần | Vai trò và ví dụ | Vì sao quan trọng |
| --- | --- | --- |
| **Java heap** | Objects, arrays do GC quản lý | Giới hạn bởi `-Xmx` hoặc lựa chọn heap tự động; có thể gây `OutOfMemoryError: Java heap space` |
| **Metaspace** | Metadata của class, classloader | Có thể tăng khi load nhiều class; không nằm trong giới hạn heap |
| **Thread stacks** | Stack của các thread nền tảng, call frames | Nhiều platform threads có thể tạo áp lực native memory; kích thước phụ thuộc OS/JVM/flags |
| **Code cache/JIT** | Mã máy do JIT tạo và metadata liên quan | Tiêu thụ tài nguyên ngoài Java heap |
| **Direct/off-heap buffers** | `ByteBuffer.allocateDirect`, một số thư viện networking/storage | Không tính vào heap used, nhưng vẫn tiêu thụ bộ nhớ thực |
| **GC/JVM native structures** | GC metadata, bookkeeping, compiler/runtime allocations | Heap nhỏ không có nghĩa tổng bộ nhớ tiến trình nhỏ |
| **Native/JNI/library allocations** | Thư viện native, allocator của OS | Có thể không được phản ánh đầy đủ bởi các chỉ số heap/NMT |
| **Memory-mapped files & page cache** | Các trang map, filesystem cache tính theo cơ chế kernel | Có thể góp vào memory accounting cgroup; khác với object trên heap |

Giả sử container có memory limit **1 GiB** và JVM được đặt `-Xmx768m`. Khoảng chênh **256 MiB** không phải “bộ nhớ chắc chắn còn trống”: metaspace, stacks, direct buffers, JIT, thư viện native, page cache và tiến trình phụ có thể cũng cần RAM. Trong một workload cụ thể, tổng bộ nhớ được kernel tính vào cgroup có thể chạm ngưỡng **dù heap chưa chạm `-Xmx`**.

Ngược lại, `heap used` tăng trước một lần GC không tự chứng minh rò rỉ: GC có thể thu hồi phần lớn objects. Cần theo dõi xu thế sau GC, tốc độ allocation, retained references và bối cảnh tải.

### 3.2 Ba khái niệm từ `Runtime` rất dễ bị nhầm

Java cung cấp:

```java
Runtime rt = Runtime.getRuntime();
int processors = rt.availableProcessors();
long heapMaxBytes = rt.maxMemory();
long heapCommittedBytes = rt.totalMemory();
long freeWithinCommittedBytes = rt.freeMemory();
long approximateUsedHeapBytes = heapCommittedBytes - freeWithinCommittedBytes;
```

Giải thích:

- `availableProcessors()`: số processor JVM trình bày cho chương trình, không phải chỉ số CPU usage hiện tại.
- `maxMemory()`: giới hạn heap tối đa JVM cố gắng sử dụng; **không phải** total RAM của container hay RSS.
- `totalMemory()`: lượng heap hiện JVM đã cấp phát/commit cho mục đích của mình; không phải total memory của node.
- `freeMemory()`: dung lượng trống **trong phần heap đã commit**, không phải RAM trống của OS/container.
- `totalMemory() - freeMemory()`: ước lượng heap đang dùng tại thời điểm đọc; các giá trị có thể thay đổi đồng thời với GC và allocation.

Còn ở Linux cgroup v2:

- `memory.max`: hard memory limit tại cgroup đó, hoặc `max` nếu không giới hạn tại cấp đó.
- `memory.current`: lượng memory kernel đang hạch toán cho cgroup, có thể gồm nhiều loại memory/page cache; **không bằng** Java heap used.
- `memory.high`: ngưỡng pressure/reclaim ở cấp cgroup khi được cấu hình, khác hard cap `memory.max`.
- `memory.events`: counter như `high`, `max`, `oom`, `oom_kill`; xem thay đổi theo khoảng thời gian và phạm vi cgroup.

Các metric `RSS`, container memory working set, `memory.current`, heap committed và heap used **không cùng định nghĩa**. Trước khi trừ hoặc cộng, cần biết mỗi metric đếm những trang nào, phạm vi nào (process/container/pod) và có bao gồm cache hay không.

### 3.3 JVM `OutOfMemoryError` khác kernel OOM kill

| Triệu chứng | Cách hiểu ban đầu | Bằng chứng cần đối chiếu |
| --- | --- | --- |
| `java.lang.OutOfMemoryError: Java heap space` | JVM không thể đáp ứng một allocation trên heap theo ràng buộc hiện tại | Heap usage, GC logs, `-Xmx`, allocation/retained objects, stack trace |
| `OutOfMemoryError: Metaspace` | Không đáp ứng được metadata class trong metaspace | Class loading/classloader, metaspace metrics, flags, native memory |
| `OutOfMemoryError: unable to create native thread` | Không tạo được platform thread mới; có thể liên quan native memory, PID/thread limits hoặc tài nguyên OS | Thread count, stack size, `pids.max/current`, process limits, memory |
| Container bị `OOMKilled` | Kernel/cgroup chọn kill process khi chạm điều kiện memory; tiến trình có thể biến mất đột ngột | Pod/container termination reason, exit status, `memory.events`, memory.current/peak metrics, container logs |
| Exit code `137` | Thường biểu thị process bị `SIGKILL` (128 + 9) | Cần xác minh ai gửi SIGKILL; **không** dùng riêng code 137 để khẳng định OOM |

Kernel kill có thể không cho JVM cơ hội in `OutOfMemoryError` hoặc ghi heap dump. Một `OutOfMemoryError` do JVM ném cũng chưa chắc dẫn đến kernel kill. Sự khác biệt này rất quan trọng khi phân loại nguyên nhân và chọn cách thu bằng chứng.

### 3.4 Heap sizing tự động và các flag

Trong JVM container-aware, khi **không** chỉ định `-Xmx`, JVM có thể dùng các heuristic như `-XX:MaxRAMPercentage` để chọn giới hạn heap theo lượng memory mà nó phát hiện. Các tỷ lệ, giới hạn và cách làm tròn có thể phụ thuộc JDK/vendor/loại workload. Khi `-Xmx` được cấu hình tường minh, cần xem **effective flags** của tiến trình thay vì suy ra từ tỷ lệ mặc định.

Ví dụ khởi động:

```bash
java -Xmx768m -jar app.jar
```

Lệnh trên đặt mục tiêu giới hạn heap khoảng 768 MiB; nó **không** đặt hard limit 768 MiB cho cả tiến trình. Nếu container chỉ có 1 GiB, phải dành headroom cho non-heap/native memory và account thêm những phần khác theo hệ điều hành. Headroom cần bao nhiêu phụ thuộc số thread, direct buffers, GC/JIT, thư viện, memory-mapped files, sidecar/cgroup boundary và đặc tính tải, **không có một tỷ lệ đúng cho mọi dịch vụ**.

## 4. Kubernetes: requests/limits và thực tế chạy

Giả sử một container Java có mô tả tài nguyên:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1500m"
    memory: "1Gi"
```

Cách diễn giải trên Kubernetes/Linux thường là:

- **CPU request 500m:** input để scheduler quyết định đặt workload và cơ chế chia tài nguyên khi có tranh chấp. Không phải “JVM chỉ thấy 0,5 CPU”.
- **CPU limit 1500m:** có thể được triển khai thành quota trung bình 1,5 CPU-equivalents; khi tải CPU vượt ngân sách, container có thể bị throttled. Số CPU logic được phép chạy đồng thời còn phụ thuộc cpuset/affinity.
- **Memory request 512Mi:** input scheduling và một số quyết định quản lý tài nguyên; không phải hard memory cap.
- **Memory limit 1Gi:** ràng buộc memory của container; vượt giới hạn có thể bị OOM kill. Giới hạn memory không thể so trực tiếp với heap used của Java.
- **Các container trong cùng pod:** sidecar có requests/limits riêng. Khi so resource của Java, phải xác định tên container và các giới hạn kế thừa/thực tế; không được nhầm memory của cả pod với JVM riêng lẻ.

Spec triển khai cho biết **ý định**; cgroup đang áp dụng cho biết **cơ chế giới hạn tại runtime**; JVM API và effective flags cho biết **JVM đã nhìn nhận giới hạn đó ra sao**; metrics cho biết **ứng dụng đã tiêu thụ tài nguyên như thế nào trong khoảng quan sát**.

Một thay đổi autoscaling, sidecar, JDK patch, node placement hoặc chính sách cgroup cũng có thể làm hành vi khác nhau ngay khi code và `-Xmx` không đổi.

## 5. Thu thập bằng chứng từ đúng tiến trình Java

Những lệnh dưới đây là **mẫu Linux/cgroup v2 và JDK 17+**, cần chạy trong đúng môi trường/container có quyền đọc tương ứng. Với Windows, macOS, cgroup v1 hoặc runtime container khác, tệp/lệnh hệ thống sẽ khác. Với image tối giản, container có thể không có shell, `cat`, `ps` hoặc `jcmd`; cần thu từ công cụ tương ứng hoặc môi trường chẩn đoán được phép.

### 5.1 Bước 1 — Xác nhận deployment và giới hạn đã cấu hình

Ở Kubernetes, trước hết xem cấu hình và trạng thái thực của **đúng container**:

```bash
kubectl -n "$NAMESPACE" get pod "$POD" -o yaml
kubectl -n "$NAMESPACE" describe pod "$POD"
kubectl -n "$NAMESPACE" top pod "$POD" --containers
```

Ở đây `NAMESPACE` và `POD` là biến shell đã được đặt theo workload đang điều tra. Lệnh `top` phụ thuộc việc có Metrics Server; output là số đo theo ngữ nghĩa của hệ thống quan sát, **không** thay thế đọc cgroup/JVM. Từ mô tả pod, đối chiếu **requests/limits, image, container name, restart count, termination reason, node** và thời điểm. Trong nhiều tình huống cần đọc thêm Deployment/ReplicaSet và các phiên bản spec đã rollout để biết tiến trình đang chạy thật sự thuộc lần triển khai nào.

Không kết luận tài nguyên chỉ từ manifest trong Git: pod đang chạy có thể mang spec của một bản rollout khác; chính sách cluster có thể thêm limit/default hoặc thay đổi cấu hình trước khi tạo pod.

### 5.2 Bước 2 — Đọc giới hạn kernel đang áp dụng

Trong **đúng container Linux dùng cgroup v2**, các tệp thường có ích:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/pids.max
cat /sys/fs/cgroup/pids.current
```

Ghi lại **raw output** và timestamp, đặc biệt `cpu.stat` và `memory.events` ở ít nhất hai thời điểm để có delta counter.

Tùy hệ thống, `/sys/fs/cgroup` có thể không phải cgroup v2 được mount theo cấu trúc trên. Đọc `/proc/self/cgroup` và mount information để xác định đúng controller/hierarchy. Với **cgroup v1**, CPU quota thường xuất hiện qua `cpu.cfs_quota_us`/`cpu.cfs_period_us`, memory limit qua `memory.limit_in_bytes`; mount path có thể khác và một số giá trị “rất lớn” biểu thị không giới hạn thực tế. Đừng lấy một đường dẫn v2 không tồn tại rồi suy ra “container không bị limit”.

Nếu container chịu ràng buộc từ **cgroup cha** hoặc OS-level affinity, chỉ một tệp ở thư mục hiện tại có thể chưa cho toàn bộ effective constraints. Cần đối chiếu phạm vi mount và hierarchy tương ứng.

### 5.3 Bước 3 — Đọc JVM đang nhìn thấy gì

Ở thời điểm khởi động, JDK 17+ thường hỗ trợ các công cụ:

```bash
java -version
java -XshowSettings:system -version
java -XshowSettings:vm -version
java -XX:+PrintFlagsFinal -version
```

Lưu ý: đây là output của **một JVM mới** được khởi động bằng lệnh, có thể khác process ứng dụng do flags, container, classpath và môi trường. Dùng nó để khảo sát **mặc định tại môi trường đó**; để xác nhận ứng dụng đang chạy, cần lấy **effective arguments và JVM flags của chính PID**. Trên platform không hỗ trợ system container metrics, `-XshowSettings:system` có thể không cung cấp thông tin cần thiết.

Với `jcmd` có trong JDK và attach được vào process Java mục tiêu:

```bash
jcmd -l
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" GC.heap_info
```

`PID` phải là process Java thực tế (trong container có thể là PID 1, nhưng không luôn như vậy). Attach phụ thuộc quyền user, process namespace, JVM flags và việc có JDK tools hay không. `jcmd -l` không nhất thiết nhìn thấy mọi JVM bên ngoài namespace hiện tại.

Khi cần điều tra native memory và **Native Memory Tracking (NMT) đã được bật từ lúc JVM khởi động**, có thể sử dụng:

```bash
jcmd "$PID" VM.native_memory summary
```

Ví dụ bật NMT trong **một lần chạy được chuẩn bị để chẩn đoán**:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

NMT có chi phí và không bao quát mọi allocation của các thư viện native bên thứ ba. Nếu chưa bật từ đầu, lệnh `VM.native_memory summary` có thể chỉ báo NMT chưa enabled. Không diễn giải “NMT thấp” thành “RSS/container memory chắc chắn thấp”.

Khi cần tìm cơ chế GC/CPU/container detection, có thể lập kế hoạch thu GC logs hoặc JFR với cấu hình phù hợp. Một số JDK/HotSpot trên Linux hỗ trợ log lúc khởi động như:

```bash
java -Xlog:os+container=debug -jar app.jar
```

Đây là cách tạo **một tiến trình mới với instrumentation bổ sung**; không phải lệnh attach tự động vào JVM đang chạy. Mức độ chi tiết và tag hỗ trợ cần xác minh trên bản JDK/vendor dùng thực tế.

### 5.4 Bước 4 — So sánh tại cùng thời điểm và cùng phạm vi

Tối thiểu, ghi một bảng như sau:

| Thuộc tính | Deployment | cgroup/OS | JVM | Kết quả cần làm rõ |
| --- | --- | --- | --- | --- |
| CPU | Request 500m; limit 1500m | `cpu.max=150000 100000`; cpuset và throttling delta | `availableProcessors()`, `ActiveProcessorCount`, GC/thread config | JVM có phản ánh CPU hiệu dụng đúng theo version/flags không? Có throttling khi chậm không? |
| Memory | Request 512Mi; limit 1Gi | `memory.max=1073741824`, `memory.current`, `memory.events` | `-Xmx`, max/used heap, metaspace, native/direct, stacks | Bộ nhớ ngoài heap và cgroup accounting có giải thích memory pressure/kill không? |
| PID/thread | Giới hạn runtime nếu có | `pids.max/current`, process limits | Thread count, thread dumps | Lỗi tạo thread có liên quan PID/native memory không? |
| Process file descriptors | Giới hạn OS/container | `/proc/<pid>/limits`, FD usage | Sockets/files, errors | Có đạt `nofile` limit hoặc leak descriptor không? |

**Đây là bảng minh họa**, không phải kết quả từ một cluster có thật. Chỉ điền “khớp”, “không khớp” hoặc “chưa đủ dữ liệu” sau khi xác minh phạm vi đo và mốc thời gian.

## 6. Ví dụ Java 17+ chạy được: tách phép tính quota và quan sát JVM thật

Để tránh kết quả không ổn định theo máy, ví dụ có hai chế độ:

1. `fixture`: tính từ **chuỗi cgroup v2 giả định**, in output **hoàn toàn xác định** để kiểm tra cách quy đổi.
2. Không có argument: in **giá trị JVM thực** và raw cgroup files nếu đọc được; kết quả thay đổi theo OS, JDK, container và startup flags.

Tạo tệp `JvmResourceViewDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class JvmResourceViewDemo {
    private static final long MIB = 1024L * 1024L;

    static String cpuLimit(String raw) {
        String[] fields = raw.trim().split("\\s+");
        if (fields.length != 2) {
            throw new IllegalArgumentException("cpu.max requires two fields");
        }
        if (fields[0].equals("max")) {
            return "unlimited by cpu.max";
        }
        long quota = Long.parseLong(fields[0]);
        long period = Long.parseLong(fields[1]);
        if (quota <= 0 || period <= 0) {
            throw new IllegalArgumentException("invalid cpu.max values");
        }
        return String.format(Locale.ROOT, "%.2f CPU-equivalents",
                (double) quota / period);
    }

    static String memoryLimit(String raw) {
        String value = raw.trim();
        if (value.equals("max")) {
            return "unlimited by memory.max";
        }
        long bytes = Long.parseLong(value);
        if (bytes <= 0) {
            throw new IllegalArgumentException("invalid memory.max value");
        }
        return (bytes / MIB) + " MiB";
    }

    static String readIfPossible(String filename) {
        try {
            return Files.readString(Path.of(filename)).trim();
        } catch (IOException | SecurityException e) {
            return "not available";
        }
    }

    public static void main(String[] args) {
        if (args.length == 1 && args[0].equals("fixture")) {
            System.out.println("cpu.max 150000 100000 -> "
                    + cpuLimit("150000 100000"));
            System.out.println("cpu.max max 100000 -> "
                    + cpuLimit("max 100000"));
            System.out.println("memory.max 1073741824 -> "
                    + memoryLimit("1073741824"));
            System.out.println("memory.max max -> "
                    + memoryLimit("max"));
            return;
        }
        if (args.length != 0) {
            throw new IllegalArgumentException("use no args or fixture");
        }

        Runtime runtime = Runtime.getRuntime();
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("availableProcessors="
                + runtime.availableProcessors());
        System.out.println("heap.max.MiB=" + runtime.maxMemory() / MIB);
        System.out.println("heap.committed.MiB=" + runtime.totalMemory() / MIB);
        System.out.println("heap.used.approx.MiB="
                + (runtime.totalMemory() - runtime.freeMemory()) / MIB);
        System.out.println("cgroup.v2.cpu.max="
                + readIfPossible("/sys/fs/cgroup/cpu.max"));
        System.out.println("cgroup.v2.memory.max="
                + readIfPossible("/sys/fs/cgroup/memory.max"));
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac JvmResourceViewDemo.java
java JvmResourceViewDemo fixture
```

Stdout **chính xác** của chế độ `fixture`:

```text
cpu.max 150000 100000 -> 1.50 CPU-equivalents
cpu.max max 100000 -> unlimited by cpu.max
memory.max 1073741824 -> 1024 MiB
memory.max max -> unlimited by memory.max
```

Bây giờ chạy:

```bash
java JvmResourceViewDemo
```

Chế độ này in `pid`, `availableProcessors`, heap max/committed/used xấp xỉ và nội dung raw của **hai đường dẫn cgroup v2** nếu có. **Không có stdout cố định** cho chế độ này vì mọi số đều phụ thuộc môi trường/điều kiện chạy; `not available` chỉ có nghĩa là Java không đọc được đường dẫn đó, không chứng minh không có giới hạn.

Để quan sát ảnh hưởng của cấu hình heap trong một JVM **mới**:

```bash
java -Xmx256m JvmResourceViewDemo
```

Lúc này `heap.max.MiB` thường gần giá trị heap yêu cầu sau các quy tắc của VM, nhưng đừng giả định là **chính xác** 256 ở mọi bản JDK. Tương tự, `availableProcessors` có thể khác trên host/container/JDK khác nhau.

**Điều code minh họa không làm:** nó không tự tìm cgroup v1, không giải toàn bộ hierarchy/cpuset, không tính RSS/native usage, không lấy Kubernetes spec, không xác minh JVM đã tiêu thụ hết quota và không đo performance. Đây là công cụ **đối chiếu ban đầu**, phải kết hợp metrics/cgroup/JVM flags và đúng PID khi điều tra thật.

## 7. Phân tích tình huống thực tế: thấy lệch thì hỏi gì?

### 7.1 “Node có 16 CPU nhưng JVM chỉ báo 2”

Đây chưa chắc là lỗi. Kiểm tra:

1. Container CPU limit, quota/period; cpuset và CPU affinity của tiến trình.
2. `-XX:ActiveProcessorCount` và `-XX:+UseContainerSupport`/các flags ảnh hưởng phát hiện.
3. Bản JDK/vendor/patch thực tế, namespace/cgroup của PID.
4. CPU throttling và workload có đang chạy đủ tải hay không.

Nếu deployment limit tương đương 1,5 CPU, `availableProcessors=2` **có thể** phù hợp với cách JVM báo một số nguyên; không kết luận chính xác chỉ từ hai con số. Nếu JVM báo 16 và workload bị throttled dưới 1,5 quota, cần xem override/container detection; thread/GC heuristics có thể khác kỳ vọng.

**Hành động:** so sánh effective limits, runtime detection và triệu chứng trước khi đổi flag hoặc kích thước pool. Thay `ActiveProcessorCount` chỉ làm thay đổi cách JVM nhìn số processor, không làm kernel tăng CPU budget.

### 7.2 “Heap không đầy nhưng pod vẫn OOMKilled”

Ví dụ minh họa: memory limit container 1 GiB, `-Xmx768m`, heap used lúc đo 600 MiB; sau đó container bị kill. Có thể có metaspace, direct buffers, thread stacks, GC/JIT native structures, mmap/page cache hoặc trạng thái memory đỉnh giữa hai lần lấy mẫu.

Các bước xác minh:

- Xem termination reason `OOMKilled`, exit status và timestamp của **container cụ thể**; kiểm tra memory events/usage trên đúng cgroup.
- Đối chiếu peak/working-set/RSS với phạm vi và tần suất đo; đừng suy RAM trống từ `heap.max - heap.used`.
- Thu heap, metaspace, direct buffer, thread count và native information phù hợp; NMT hữu ích nếu đã bật và hiểu phạm vi của nó.
- Kiểm tra thay đổi về payload, concurrency, thread pool, cache, direct memory hoặc sidecar/process phụ.
- Đánh giá headroom và can thiệp dựa trên cơ chế; tăng `-Xmx` khi container cap giữ nguyên có thể **tệ hơn** nếu thiếu native headroom.

Không cần một `java.lang.OutOfMemoryError` trong log mới xác minh được kernel OOM kill. Ngược lại, không coi mọi exit 137 là bằng chứng OOM khi chưa có termination reason/cgroup evidence.

### 7.3 “CPU của JVM không cao mà latency vẫn tăng”

CPU process có thể thấp vì phần lớn thread đang chờ DB/network/lock. Hoặc CPU đã bị throttled, metric CPU% có mẫu số khác, hoặc đo ở một cửa sổ quá thưa.

Điều tra bằng cách nối **client latency, throughput, in-flight/queue, process/container CPU usage, cpu.stat delta, thread dump/JFR, downstream timings** theo cùng khoảng thời gian. Việc CPU usage không đạt 100% của node không chứng minh container còn đủ CPU budget.

### 7.4 “Không tạo được thread dù heap còn trống”

Lỗi `unable to create native thread` có thể xuất hiện khi giới hạn PID/thread, native memory hoặc process limits bị chạm. Kiểm tra:

- Số platform threads đang tồn tại và growth theo thời gian.
- `pids.max`, `pids.current`; `ulimit`, `/proc/<pid>/limits`.
- Thread stack size và memory accounting; các thread pool/cấu hình concurrency.
- Có leak thread hoặc tác vụ blocking kéo dài không.

Đừng tăng `-Xmx` theo phản xạ: heap lớn hơn có thể còn làm giảm headroom cho native allocations. Với virtual threads (nếu dùng trên JDK hỗ trợ phù hợp), cần phân biệt số virtual threads với số platform/carrier threads; không suy chi phí native stack 1:1 theo số virtual threads.

### 7.5 “Cùng image Java nhưng một cluster xử lý nhanh hơn”

Khả năng khác biệt gồm node/CPU architecture, JDK vendor/build patch, CPU request/limit và cpuset, memory limit, GC flags, autoscaling, dependency latency, payload/data distribution, noisy neighbors, kernel/cgroup version và cách cấu hình observability. Ghi **cả cấu hình khai báo lẫn hiệu lực đo được** ở hai môi trường. Một image giống nhau chưa chứng minh điều kiện chạy giống nhau.

## 8. Quy trình chẩn đoán có thể lặp lại

### Bước 1 — Khoanh vùng triệu chứng và đúng tiến trình

Ghi service, instance/pod, container, PID, image digest, JDK vendor/patch, JVM startup flags, timestamp có timezone và loại bất thường: timeout, p99 tăng, OOM kill, JVM `OutOfMemoryError`, thread creation failure hay CPU-bound workload chậm.

### Bước 2 — Xác nhận deployment spec đang có hiệu lực

Đọc CPU/memory requests/limits của đúng container, số replica, node placement, restart/exit reason. Đối chiếu bản spec với pod thực sự chạy thay vì chỉ nhìn file cấu hình cũ.

### Bước 3 — Thu cgroup và OS constraints

Đọc `cpu.max`, cpuset, `cpu.stat`, `memory.max/current/events`, `pids.max/current` (hoặc đường tương đương của cgroup v1/OS). Kiểm tra giới hạn thừa kế, affinity và việc container có nhìn thấy các đường dẫn đúng hay không. Lưu raw values.

### Bước 4 — Thu JVM effective settings và metrics

Lấy `availableProcessors()`, `-Xmx`/effective max heap, heap committed/used, GC/thread/native allocation, JVM arguments. Khi cần, dùng GC log/JFR/NMT/stack trace. Phải lấy từ **đúng JVM/PID** và gắn mốc thời gian.

### Bước 5 — Đặt các chỉ số cùng ranh giới và cửa sổ

So sánh **per-process**, **per-container**, **per-pod** và **per-node** đúng nguồn; ví dụ container memory khác heap. Đo delta CPU throttling và memory events trong thời gian p95/p99 hoặc errors thay đổi. Đặt workload (RPS/concurrency/mix/payload) cạnh resource metrics.

### Bước 6 — Lập và kiểm tra giả thuyết

Ví dụ:

```text
Giả thuyết:
CPU limit thấp gây throttling vào lúc peak, làm p99 tăng.

Điều kiện cần:
- offered/received/completed load đã đo;
- cpu.max thực = quota đang nghi vấn;
- cpu.stat nr_throttled/throttled_usec tăng trong cửa sổ p99 tăng;
- không có dependency/queue/GC khác giải thích toàn bộ hiện tượng.

Thử nghiệm có kiểm soát:
- giữ workload và dữ liệu tương đương;
- chỉ thay đổi quota ở môi trường kiểm thử khi phù hợp;
- đo lại p99, throughput, throttling và CPU chi phí.

Giới hạn:
- một lần giảm p99 chưa chứng minh nguyên nhân trong mọi môi trường.
```

Tương tự, giả thuyết OOM do native memory cần đối chiếu memory accounting, heap/native và events; giả thuyết leak thread cần chứng cứ thread count tăng/không giải phóng và PID limit. Không gán nguyên nhân chỉ vì một metric cùng tăng.

### Bước 7 — Kết luận và bàn giao

Phân biệt kết luận **đã xác nhận**, **được ủng hộ nhưng cần kiểm chứng**, và **chưa đủ dữ liệu**. Ghi phạm vi, resource budget, rủi ro, biện pháp khắc phục, tiêu chí xác minh và theo dõi sau thay đổi.

## 9. Mẫu bảng báo cáo đối chiếu

```text
ISSUE
- Triệu chứng, mức ảnh hưởng, thời gian và timezone:
- Service, image digest, container, pod/node, PID:
- Java vendor/version/patch và command line:
- Workload: offered/received/completed RPS, concurrency, data:

DEPLOYMENT (đúng container)
- CPU request / limit:
- Memory request / limit:
- Pod/container restart, termination reason:
- Config, replica count, node placement:

KERNEL / OS
- cgroup version, scope/path, ancestor constraints:
- cpu.max, cpuset/affinity:
- cpu.stat counters/delta trong cùng cửa sổ:
- memory.max/current/events, RSS/working-set:
- pids.max/current và process limits nếu liên quan:

JVM
- availableProcessors, ActiveProcessorCount/UseContainerSupport:
- Heap max/committed/used, -Xms/-Xmx/MaxRAMPercentage:
- Metaspace/direct/native/thread and GC evidence:
- JFR/GC/thread dumps/metrics (ID và timestamp):

ANALYSIS
- Khớp/chênh giữa deployment, cgroup, JVM:
- Giả thuyết, cơ chế, bằng chứng hỗ trợ/phản bác:
- Kết quả thử nghiệm cùng workload:
- Sai khác phạm vi đo và yếu tố chưa kiểm soát:

CONCLUSION
- Xác nhận / ủng hộ / chưa đủ dữ liệu:
- Phạm vi áp dụng và giới hạn:
- Hành động đề xuất, owner, tiêu chí xác minh:
```

Trong báo cáo chính thức, thay dấu mô tả bằng **số đo thật kèm thời điểm**, không nhập những con số minh họa thành dữ liệu hệ thống. Một bảng so sánh tốt giúp người đọc hiểu ngay vì sao “node còn RAM” vẫn có thể đi cùng container OOM, hay vì sao `availableProcessors()` không bằng CPU của máy chủ.

## 10. Sai lầm phổ biến

1. **Lấy `freeMemory()` làm RAM còn lại của container.** Đây là phần trống trong heap đã commit; cần xem cgroup/OS memory riêng.
2. **So `-Xmx` trực tiếp với memory limit rồi kết luận an toàn.** Còn native/off-heap, stacks, metaspace, JIT, page cache và overhead khác.
3. **Đọc CPU host và suy JVM được dùng hết.** Quota, cpuset, affinity, container support và override có thể giới hạn.
4. **Cho rằng CPU request là hard cap.** Request chủ yếu dùng cho scheduling/chia tài nguyên; CPU limit mới thường thành quota enforce.
5. **Xem `availableProcessors()` là số CPU đang dùng.** Đây là số processor mà JVM báo, không phải usage hoặc số core vật lý độc quyền.
6. **Thấy `cpu.max=max` rồi kết luận vô hạn CPU.** Có thể còn cpuset, cgroup cha, affinity hoặc tải cạnh tranh.
7. **Đọc `nr_throttled` hoặc `oom_kill` một lần rồi suy sự cố mới.** Đó là counter tích lũy; cần delta và đúng time window.
8. **Nhầm `OOMKilled` với `OutOfMemoryError`.** Một bên do kernel/cgroup, một bên là Java exception/error; phương pháp thu evidence khác nhau.
9. **Chỉ dùng output của `java -XshowSettings` trên JVM mới để kết luận ứng dụng đang chạy.** Startup flags/PID/namespace khác có thể làm kết quả khác.
10. **Gán toàn bộ cgroup memory usage cho heap.** Cgroup accounting không cùng phạm vi/khái niệm với heap used hoặc NMT.
11. **Bỏ qua cgroup version và parent hierarchy.** Đường dẫn/controller hoặc inherited limits có thể khác; không có file v2 không có nghĩa không giới hạn.
12. **Tăng `ActiveProcessorCount` hoặc heap để “mở khóa” tài nguyên kernel.** Flag JVM không cấp thêm CPU quota hay container memory limit.
13. **Đo các lớp vào thời điểm khác nhau.** Một lần GC, burst hoặc restart có thể làm các số liệu lệch lớn; giữ timestamp và run ID.
14. **Chốt nguyên nhân từ một correlation.** CPU throttling, GC pause, DB wait và latency có thể cùng tăng; cần kiểm tra cơ chế và giả thuyết đối lập.
15. **Thay đổi nhiều cấu hình cùng lúc.** Không thể biết mức cải thiện đến từ yếu tố nào nếu không có thiết kế đối chứng.

## 11. Tự kiểm tra kiến thức

1. Một node có 32 logical CPU, container đặt CPU limit 1500m. Vì sao `Runtime.availableProcessors()` có thể nhỏ hơn 32 và vẫn không phải bằng chứng JVM bị lỗi?
2. Nếu `cpu.max=150000 100000`, hãy giải thích 1,5 CPU-equivalents và vì sao nó **không** tương đương 1,5 lõi độc quyền.
3. Java có `-Xmx768m` và container memory limit 1Gi. Pod bị `OOMKilled` khi heap used đo gần nhất chỉ 500MiB. Hãy nêu ít nhất năm nguồn memory khác cần xem.
4. `Runtime.totalMemory()` và `Runtime.freeMemory()` đo cái gì? Có dùng chúng để tính memory available trên node được không?
5. `cpu.max` hiện `max 100000`. Những giới hạn nào vẫn có thể khiến Java không dùng được toàn bộ CPU của host?
6. Thread pool tạo không được thread mới nhưng GC heap còn trống. Bạn sẽ đối chiếu `pids.max/current`, native memory và thread count thế nào?
7. Vì sao cùng một application image và cùng JDK major version vẫn có `availableProcessors`, heap max hoặc throughput khác nhau trên hai cluster?
8. Một monitoring dashboard báo “CPU 100%”, JVM báo 4 processors, cgroup cho 2 CPU-equivalents. Cần xác minh mẫu số của từng metric và những flags nào trước khi kết luận?
9. Lệnh `java -XshowSettings:vm -version` chạy trong container cho heap max A, còn ứng dụng đã chạy cho heap max B. Vì sao hai kết quả có thể khác?
10. Điều gì trong một báo cáo đủ để phân biệt “đã xác nhận OOM kill do cgroup” với “mới nghi ngờ memory pressure” hoặc “Java đã ném OutOfMemoryError”?

**Ghi nhớ:** Khi chẩn đoán Java, phải đối chiếu **resource đã khai báo → giới hạn kernel thực thi → tài nguyên JVM phát hiện/cấu hình → sử dụng thực tế trong cùng workload và cửa sổ thời gian**. CPU quota khác số processor, Java heap khác tổng container memory, và bằng chứng từ một lớp không thể tự động thay thế bằng chứng từ lớp khác.