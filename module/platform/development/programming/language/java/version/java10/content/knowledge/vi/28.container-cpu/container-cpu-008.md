# Phân biệt số CPU JVM nhận biết với giới hạn thực thi của hệ điều hành trong container

> **Java 10 — CPU trong container.** Từ **JDK 10**, HotSpot trên Linux có khả năng nhận biết một số giới hạn tài nguyên của container, trong đó có CPU, nhờ cải tiến JDK-8146115 và tùy chọn `-XX:+UseContainerSupport`. Nhưng **`Runtime.getRuntime().availableProcessors()` trả một số nguyên mô tả số processor JVM được cho là có thể sử dụng**; nó **không phải** phép đo CPU đang rảnh, **không phải** số lõi vật lý độc quyền, cũng **không phải** một thay đổi đối với giới hạn mà Linux kernel thực thi. Kernel vẫn quyết định các CPU được phép chạy, ngân sách CPU theo cgroup và thời điểm tiến trình bị throttling. Bài hướng dẫn diễn giải đúng những lớp giới hạn đó trên JDK hiện đại, tránh suy luận dựa trên hành vi legacy của các bản Java cũ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **CPU logic của host**, **CPU IDs được phép dùng** theo affinity/cpuset, **số CPU-equivalent theo quota**, **CPU count JVM nhìn thấy** và **CPU thực sự sử dụng trong một khoảng thời gian**.
2. Hiểu cải tiến container-awareness của **JDK 10** và ý nghĩa hiện tại của `-XX:+UseContainerSupport` trên HotSpot Linux.
3. Hiểu `Runtime.availableProcessors()` trả một **`int` ít nhất là 1** để JVM và ứng dụng quyết định tài nguyên, không hứa có đúng chừng ấy lõi vật lý độc quyền.
4. Phân biệt cgroup v2 `cpu.max` (ngân sách CPU), `cpu.weight` (trọng số tranh chấp), `cpuset.cpus.effective` (tập CPU cho phép) và `cpu.stat` (thống kê).
5. Đọc cấu hình cgroup v1 `cpu.cfs_quota_us`, `cpu.cfs_period_us`, `cpu.shares` và `cpuset.cpus` trong những môi trường vẫn sử dụng phiên bản này, nhưng không áp đặt chính sách tính CPU shares legacy lên các JDK hiện đại.
6. Tính **CPU-equivalent = quota / period**, hiểu tại sao 1,5 CPU-equivalent không thể được biểu diễn trực tiếp bằng `availableProcessors()` vốn trả số nguyên.
7. Biết `-XX:ActiveProcessorCount=N` thay đổi **CPU count HotSpot dùng cho các quyết định nội bộ**, nhưng **không nới** quota, cpuset, affinity hay CPU quota của Kubernetes.
8. Giải thích tại sao một JVM nhìn thấy 8 CPU vẫn có thể bị throttling dưới quota tương đương 1,5 CPU.
9. Chẩn đoán bằng `-XshowSettings:system`, `-Xlog:os+container=trace`, `Runtime.availableProcessors()`, file cgroup và số liệu monitoring phù hợp.
10. Phân biệt Kubernetes `resources.requests.cpu` với `resources.limits.cpu` và cách CPU request/weight ảnh hưởng đến lịch chạy khi có tranh chấp.
11. Thiết kế benchmark đủ điều kiện để không kết luận sai về throughput/latency từ một số processor JVM reported.
12. Chạy một chương trình Java 17+ độc lập có **21 dòng stdout chính xác**, dùng dữ liệu **giả lập rõ ràng** để tách JVM planning hint khỏi giới hạn do OS kiểm soát.
13. Giải thích các tình huống thay đổi cgroup lúc runtime, số lượng thread pool, GC/JIT và máy chủ đa container.
14. Áp dụng checklist và bài tập để sửa những ngộ nhận vận hành thông dụng.

## 2. Năm khái niệm CPU khác nhau — không gộp thành một số

| Đại lượng | Câu hỏi nó trả lời | Lấy từ đâu | Không có nghĩa |
| --- | --- | --- | --- |
| **Host logical CPUs** | Host có bao nhiêu logical processing units, gồm SMT/hyper-threading nếu có? | Thông tin OS/hardware, ví dụ `lscpu` | Số CPU mà container được phép dùng |
| **Affinity / effective cpuset** | Thread/process có thể được kernel scheduling trên **những CPU IDs nào**? | Linux affinity mask, cgroup cpuset hierarchy | Thời gian CPU được bảo đảm liên tục |
| **Quota / period (CPU-equivalents)** | Trong mỗi chu kỳ scheduling, cgroup có ngân sách CPU-time tối đa bao nhiêu? | cgroup `cpu.max` hoặc v1 `cpu.cfs_quota_us`/`cpu.cfs_period_us` | Số lõi vật lý được dành riêng hoặc số thread có thể tạo |
| **JVM active processor count** | HotSpot và API `availableProcessors()` đang dùng số CPU nguyên bao nhiêu làm đầu vào cho ergonomics? | JVM container detection/OS + options `-XX:ActiveProcessorCount` | Một kernel hard limit có hiệu lực |
| **CPU consumption / throttling thực tế** | Workload dùng bao nhiêu CPU-time, bị throttled bao lâu, latency ra sao? | `cpu.stat`, CPU metrics, APM, profiler | Chỉ có thể suy ra từ `availableProcessors()` |

### 2.1. CPU “nhìn thấy” và CPU “chạy được” không đồng nghĩa

Giả sử một host có **32 logical CPUs**, một container có:
- effective cpuset gồm các CPU IDs `0-3,8-9`: được phép chạy trên **6 logical CPUs**;
- cgroup v2 `cpu.max` đặt `150000 100000`: ngân sách trung bình tương đương **1,5 CPU** trên mỗi period;
- JVM startup với `-XX:ActiveProcessorCount=8`: JVM dùng **8** làm gợi ý cho những quyết định liên quan active processor count.

Ba giá trị **6, 1,5 và 8** là ba điều khác nhau:
- **6** giới hạn **nơi có thể chạy** nếu cpuset hiệu lực và không có ràng buộc khác.
- **1,5** giới hạn **tổng thời gian CPU** theo bandwidth quota, được kernel điều phối cho tất cả tác vụ trong cgroup.
- **8** là một **con số do HotSpot được cấu hình để nhận biết/điều chỉnh thread pools**. Nó không cấp thêm CPU-time cho container.

Có thể có 8, 80 hoặc 8.000 Java threads, nhưng kernel vẫn kiểm soát CPU scheduling; phần lớn threads có thể phải chờ. Số thread tồn tại không đồng nghĩa số core thực thi cùng lúc.

### 2.2. SMT, physical cores và logical CPUs

`availableProcessors()` thường phản ánh khái niệm **logical processor có thể sử dụng** theo VM/OS, không phải số physical core. Một host 8 physical cores có SMT x2 có thể báo 16 logical CPUs; cgroup lại có thể cho phép một tập con.

Không nên đặt “1 processor được báo” bằng “một core vật lý chạy 100% liên tục”. Một CPU-equivalent là **đơn vị ngân sách thời gian xử lý** trong kịch bản quota; performance thực tế còn chịu ảnh hưởng workload, tần số CPU, SMT, NUMA, memory bandwidth, contention và resource throttling.

### 2.3. Công thức tối giản để ghi nhớ

\[
\text{CPU-equivalents}=\frac{\text{CPU quota (time)}}{\text{CPU period (time)}}
\]

Nếu `cpu.max = 150000 100000` (microseconds):

\[
\text{CPU-equivalents}=\frac{150000}{100000}=1.5
\]

Đây là **giới hạn CPU-time trung bình của cgroup** theo quota, không phải lệnh chỉ chạy một thread rưỡi hay giới hạn CPU ID “1,5 lõi”.

**Chú ý:** khi quota và period cho giá trị không nguyên, một số cơ chế sizing của JVM có thể chọn **số nguyên làm tròn**. Nhưng tài liệu ứng dụng không nên tự khẳng định mọi JDK/vendor đều luôn tính `ceil(quota/period)` trong mọi môi trường và khi có đủ cpuset/affinity/overrides. Hãy quan sát CPU count thực tế trên JDK mục tiêu.

## 3. Lịch sử từ Java 10 và điều gì còn áp dụng

### 3.1. JDK 10: VM nhận biết container

**Oracle JDK 10 Release Notes** ghi nhận thay đổi `JDK-8146115`:
- HotSpot trên **Linux** nhận biết cấu hình Docker container.
- VM lấy tài nguyên được phân bổ cho container thay vì chỉ nhìn host, gồm số CPU và memory.
- Bật container awareness mặc định bằng `UseContainerSupport`.
- Có `-XX:-UseContainerSupport` để tắt nhận biết container ở VM.
- Có `-XX:ActiveProcessorCount=count` để người vận hành chỉ định con số VM dùng cho tính toán nội bộ, thay vì dựa hoàn toàn vào auto-detection.

Đây là **cải tiến JDK 10**, không có nghĩa class `java.lang.Runtime` hay `availableProcessors()` mới xuất hiện trong Java 10. `availableProcessors()` đã có từ Java 1.4; thay đổi nằm ở cách một JVM implementation xác định giá trị phù hợp với tài nguyên container.

### 3.2. Hành vi CPU shares đã thay đổi trên các JDK hiện đại

**Không áp dụng máy móc mọi mô tả JDK 10 về `cpu.shares` cho JDK 21/25.** Oracle JDK 19 Release Notes (JDK-8281181) nêu rõ: từ JDK 19, VM **mặc định không còn dùng CPU shares** để quyết định active processor count, vì CPU shares là **trọng số tương đối**, không phải giới hạn hard CPU-time. Thay đổi này cũng được backport vào một số bản cập nhật các nhánh JDK trước đó, phụ thuộc distribution/build.

Do vậy:
- `cpu.shares=512` hay cgroup v2 `cpu.weight` **không được hiểu đơn giản là “chỉ có 0,5 CPU”**.
- Không đoán số processor HotSpot nhận biết chỉ từ requests/CPU shares.
- Khi quan sát JVM có giá trị khác tài liệu cũ, kiểm tra bản JDK cụ thể, các backports và flags.
- Không khuyên bật lại flag cũ `-XX:+UseContainerCpuShares` làm giải pháp mặc định: JDK 19 ghi nhận nó deprecated và có thể bị loại bỏ.

**Kiến thức còn áp dụng:** CPU quota, cpuset, CPU affinity, ActiveProcessorCount và Linux scheduling vẫn cần được phân biệt; còn thuật toán kết hợp từng nguồn nên tra cứu đúng JDK và kiểm chứng bằng log thực tế.

### 3.3. cgroup v1 và cgroup v2 không có cùng tên file

Linux container có thể dùng cgroup **v1** hoặc **v2**, tùy kernel, runtime và cấu hình node. Các JDK hiện đại hỗ trợ nhận biết cgroup v2 trong các môi trường đã hỗ trợ; JDK/version/vendor vẫn cần được xác nhận.

| Khái niệm | Cgroup v1 | Cgroup v2 |
| --- | --- | --- |
| CPU bandwidth quota | `cpu.cfs_quota_us` | `cpu.max`, trường thứ nhất |
| CPU period | `cpu.cfs_period_us` | `cpu.max`, trường thứ hai |
| Không đặt CPU hard bandwidth cap | quota v1 thường `-1` | `max` trong `cpu.max` |
| Trọng số CPU khi có tranh chấp | `cpu.shares` | `cpu.weight` |
| Các CPU được phép | `cpuset.cpus` và hiệu lực theo hierarchy | `cpuset.cpus.effective` |
| Đo CPU throttling | `cpu.stat` với các trường version-specific | `cpu.stat`, có thể có `nr_throttled`, `throttled_usec` |

Không giả định trong mọi container đều tồn tại đường dẫn host đơn giản `/sys/fs/cgroup/cpu.max`. Cgroup v1 có controller mount và cây hierarchy riêng; trong cgroup v2, đường dẫn hiệu dụng phụ thuộc **mountpoint, cgroup namespace và cgroup path** của tiến trình.

## 4. cgroup v2: ba loại giới hạn cần đọc đúng

### 4.1. `cpu.max` là quota CPU-time, không phải CPU affinity

Linux kernel mô tả `cpu.max` dạng:

```text
$MAX $PERIOD
```

Các số tính theo **microseconds**. Ví dụ:

| `cpu.max` | CPU-equivalent gần đúng | Ý nghĩa |
| --- | ---: | --- |
| `100000 100000` | 1,0 | Cgroup dùng tối đa ~1 CPU-period thời gian CPU mỗi period 100 ms |
| `50000 100000` | 0,5 | Trong mỗi period 100 ms, tối đa 50 ms CPU-time tổng |
| `150000 100000` | 1,5 | Trong mỗi period 100 ms, tối đa 150 ms CPU-time tổng từ các tasks cùng cgroup |
| `250000 100000` | 2,5 | Giới hạn tương đương 2,5 CPU-time |
| `max 100000` | Không đặt cap ở cgroup này | Vẫn có thể bị giới hạn bởi ancestor, cpuset, affinity và tài nguyên host |

Với **1,5 CPU-equivalent**, có thể tưởng tượng hai threads chạy song song khoảng 75 ms trong period 100 ms rồi cgroup hết quota (chỉ là mô hình minh họa; scheduling thực tế khác). Kernel có thể **throttle** task cho tới khi ngân sách được cấp lại.

Quota không đồng nghĩa:
- một CPU core vật lý được dành riêng;
- cố định chỉ được có 1 hoặc 2 Java threads;
- chỉ dùng CPU 0 và CPU 1;
- được bảo đảm chạy 1,5 CPU mọi giây dù node contention;
- tự động thay đổi theo `Runtime.availableProcessors`.

**Cgroup quota** áp dụng cho toàn nhóm tác vụ trong cgroup, gồm JVM worker threads, GC/JIT threads và các process khác cùng hierarchy. Cũng có thể còn cap ở ancestor, vì vậy một file local “max” **không đủ kết luận** không có giới hạn CPU-time hiệu dụng.

### 4.2. `cpu.weight` là trọng số, không phải hard limit

`cpu.weight` của cgroup v2 thường có miền 1–10000 (mặc định 100). Nó là **trọng số phân chia CPU khi có các cgroup cạnh tranh**, chứ không phải giá trị CPU-equivalent.

Ví dụ:
- Cgroup A có weight 100.
- Cgroup B có weight 200.
- Khi cả hai cùng tranh chấp CPU dưới scheduler áp dụng cơ chế này, B có thể được phần CPU cao hơn A theo trọng số tương đối.
- Khi B idle, A có thể sử dụng tài nguyên khả dụng lớn hơn; weight không cố định trần “A chỉ được 1/3 CPU”.

Đừng viết công thức `CPU count = cpu.weight / 100` hoặc `cpu.shares / 1024` rồi gọi đó là quota. Ở JDK hiện đại, CPU shares thường **không được dùng** để tính active processor count mặc định.

### 4.3. `cpuset.cpus.effective` là danh sách CPU IDs thực sự có thể dùng

Ví dụ:

```text
cpuset.cpus.effective = 0-3,8-9
```

Đếm các ID:
- `0-3` gồm 4 CPUs.
- `8-9` gồm 2 CPUs.
- Tổng **6 logical CPU IDs được phép**.

Đây là **CPU placement constraint**. Nếu quota bằng 1,5 CPU-equivalent, cgroup có thể bị throttle dù có tới 6 CPU IDs eligible. Nếu quota không giới hạn nhưng effective cpuset chỉ có 2 CPUs, CPU-bound workload không thể tận dụng 6 CPU IDs ngoài tập được phép.

Linux kernel cũng phân biệt `cpuset.cpus` (yêu cầu, có thể rỗng để kế thừa) với `cpuset.cpus.effective` (tập CPU được cấp hiệu lực sau khi xét parent/hotplug). Khi chẩn đoán, ưu tiên effective cpuset hoặc affinity thực tế của tiến trình.

### 4.4. CPU affinity là một tầng giới hạn khác

Một tiến trình có thể có affinity mask chỉ cho phép một tập con CPU IDs, ví dụ do `taskset`/`sched_setaffinity` hoặc ràng buộc hệ thống.

Một cgroup cho phép `0-3` nhưng một Java process được gắn affinity `0-1` thì process ấy **không tự dùng CPU 2 và 3** chỉ vì cpuset cgroup có bốn CPUs. Tài nguyên hiệu lực là kết hợp của các cơ chế, không chỉ một số file.

Trên Linux, có thể quan sát affinity process bằng:

```bash
taskset -pc "$PID"
grep '^Cpus_allowed_list:' /proc/"$PID"/status
```

**Thay `PID` bằng PID thật** và chỉ chạy khi công cụ/đường `/proc` truy cập được. Không suy từ host `lscpu` hay `nproc` của một tiến trình khác ra affinity của JVM mục tiêu mà không kiểm chứng.

### 4.5. `cpu.stat` giúp biết kernel có throttling không

Cgroup v2 có file `cpu.stat`, thường chứa các trường như:

```text
usage_usec       <value>
user_usec        <value>
system_usec      <value>
nr_periods       <value>
nr_throttled     <value>
throttled_usec   <value>
```

Các bộ đếm là **tích lũy**, không phải số phần trăm hiện tại. Để quan sát interval:
1. Đọc mẫu A ở thời điểm `t0`.
2. Đọc mẫu B sau một khoảng thời gian có tải.
3. Tính **delta = B - A** cho từng trường.
4. Ghi time interval, workload, cấu hình quota/cpuset.
5. Phân tích cùng CPU utilization, p95/p99 latency và throughput.

`nr_throttled` tăng cho thấy cgroup đã gặp sự kiện throttling trong khoảng đo; `throttled_usec` ghi thời gian theo cách kernel controller định nghĩa. **Đừng lấy `throttled_usec / wall_time` làm “% CPU lost” một cách ngây thơ** vì có nhiều threads, nhiều cấu hình scheduling và giới hạn ở parent. Tài liệu kernel còn phân biệt thống kê non-hierarchical của một số trường với throttling kế thừa từ ancestor.

**Thiếu `nr_throttled` không nhất thiết có nghĩa “VM không bao giờ chậm vì CPU”**: còn run queue contention, affinity, host steal time, quota ở ancestor và dạng scheduler/metrics khác.

## 5. `Runtime.availableProcessors()`: hợp đồng Java API và giới hạn của nó

### 5.1. API chính xác

```java
int active = Runtime.getRuntime().availableProcessors();
```

Theo Javadoc Java SE 25:
- Trả số processor mà JVM **có sẵn để sử dụng** dưới dạng **`int`**.
- Giá trị **không nhỏ hơn 1**.
- Có thể **thay đổi trong cùng thời gian chạy JVM**; ứng dụng nhạy với số processor có thể cần kiểm tra lại và điều chỉnh cấu hình khi phù hợp.

Nó **không** trả:
- danh sách CPU IDs;
- CPU-equivalent dạng số thực như `1.5`;
- phần trăm CPU sử dụng ở hiện tại;
- số lượng core vật lý mà container sở hữu riêng;
- đo throughput hoặc thời gian throttle;
- một hard quota được cài vào OS.

### 5.2. JVM reported count có thể ảnh hưởng tới quyết định bên trong JVM

HotSpot có thể dùng active processor count cho **ergonomics**:
- chọn quy mô một số GC worker threads;
- tính số lượng threads cho một số công việc trong JIT/runtime;
- kích thước thread pools ở một số thư viện và cấu hình mặc định;
- `ForkJoinPool.commonPool()` và parallelism của một số framework tùy implementation/config.

**Không bảo đảm mọi thư viện đều dùng `Runtime.availableProcessors()` trực tiếp.** Một executor được tạo với `Executors.newFixedThreadPool(64)` vẫn có thể tạo 64 worker threads dù VM báo 2 CPUs. Một HTTP server có thể có cấu hình thread pool riêng; ForkJoinPool có chính sách và tham số riêng.

Nếu JVM báo 2 mà kernel đang cho 1,5 CPU-equivalent, application phải cân nhắc throughput/latency với quota thật, không chỉ trông đợi thread pools tự tối ưu hoàn hảo.

### 5.3. Không đồng nhất với CPU utilization

Một JVM có `availableProcessors()==8` vẫn có thể:
- gần như idle, dùng rất ít CPU;
- dùng tổng CPU-time tương đương 1,5 core do quota;
- có 100 thread runnable đang tranh CPU và bị throttled;
- chạy nhanh trên các CPU hiệu năng khác nhau khi host không đồng nhất.

Đo CPU utilization cần sampling theo thời gian và hiểu chuẩn hóa denominator (host logical CPU, quota, cpuset hay process CPU-time). Không lấy số 8 làm bằng chứng “JVM đã dùng 8 CPU”.

### 5.4. CPU count có thể thay đổi khi cgroup thay đổi

Kubernetes có thể thay đổi giới hạn bằng cơ chế triển khai/điều phối, hoặc workload di chuyển, hay CPU affinity/cpuset thay đổi. Javadoc nói giá trị processor available **có thể thay đổi** trong lifetime JVM.

Tuy vậy:
- JVM và thư viện có thể đọc giá trị ở **thời điểm khởi động** và cache một cấu hình pool.
- Không bảo đảm thay quota khi đang chạy sẽ tự resize mọi executor hoặc GC worker.
- Không nên thiết kế logic phụ thuộc vào việc mọi JDK cập nhật `availableProcessors()` theo cùng một thời điểm khi container limit thay đổi.
- Đối với thay đổi tài nguyên quan trọng, cần kiểm tra behavior trên bản JDK đang chạy và cân nhắc restart/reconfigure theo cơ chế deployment được hỗ trợ.

## 6. Hai cờ HotSpot quan trọng và điểm giới hạn

### 6.1. `-XX:+UseContainerSupport`

Trên **HotSpot Linux JDK hiện đại**, container support được **bật mặc định** trong các điều kiện được hỗ trợ. Oracle JDK 25 manpage ghi:

```text
-XX:-UseContainerSupport
```

để **tắt** cơ chế VM dùng thông tin container khi tự cấu hình. Mục đích thường là **chẩn đoán** chứ không phải “nới quyền CPU”. Kể cả khi bạn tắt VM container-awareness:
- Linux kernel vẫn **áp** quota/cpuset/affinity.
- JVM có thể tính pool sizes dựa trên thông tin khác và tạo thêm threads.
- Quota thực vẫn là quota kernel.

**Cảnh báo:** đừng dùng `-XX:-UseContainerSupport` làm mẹo giải quyết throttling trong production; nó dễ khiến VM ước lượng CPU/memory sai so với môi trường container.

### 6.2. `-XX:ActiveProcessorCount=N`

Theo Oracle JDK 25 `java` launcher:

```text
-XX:ActiveProcessorCount=2
```

tạo override **số processor VM dùng cho việc tính quy mô các thread pools**, chẳng hạn GC và ForkJoinPool. Tài liệu cũng nói flag được tôn trọng **ngay cả khi** `UseContainerSupport` bị tắt.

Ví dụ đối chiếu (giả sử chạy trên HotSpot JDK hỗ trợ flag):

```bash
java -XX:ActiveProcessorCount=2 CpuRuntimeProbe
java -XX:ActiveProcessorCount=8 CpuRuntimeProbe
```

Với mã probe ở phần 8, HotSpot có thể báo `availableProcessors()` lần lượt **2** và **8**. **Nhưng** nếu cả hai lệnh đều ở một cgroup `cpu.max=150000 100000`, thì CPU-time quota của OS **vẫn tương đương 1,5 CPU**. Flag không chỉnh `cpu.max`, không mở rộng effective cpuset hoặc OS affinity.

Nếu muốn thay **hard resource limit**, cần thay cấu hình container/orchestrator/cgroup theo quyền quản trị, không sửa `ActiveProcessorCount`.

### 6.3. Flag override không phải ép Java tạo đúng N threads

`ActiveProcessorCount=8` không đồng nghĩa JVM luôn tạo chính xác 8 threads cho mọi pool, hoặc chỉ được phép tồn tại 8 threads. Từng thành phần GC/JIT/ForkJoin hoặc ứng dụng có công thức và giới hạn riêng.

Ví dụ:
- Một GC có thể có nhiều loại worker và biến điều khiển khác.
- Executor pool do ứng dụng tự cấu hình 32 threads có thể không đổi.
- Virtual threads có semantics scheduling khác platform worker threads; số task đồng thời không tương đương số CPU cores.
- Các thư viện có thể cấu hình parallelism theo memory, connection pool hoặc I/O thay vì CPU count.

Do vậy, để đánh giá hiệu quả đổi `ActiveProcessorCount`:
1. Ghi giá trị JVM reporting.
2. Ghi flags GC và pool settings liên quan.
3. Đo mức sử dụng CPU-time thực, throttling, RPS, p95/p99 latency, GC pauses.
4. Lặp lại A/B trên cùng cgroup và workload.
5. Chỉ quyết định dựa trên mục tiêu sản phẩm, không lấy số 2/8 làm kết luận hiệu năng.

### 6.4. Không nên bật lại CPU shares như một cách phân bổ “hard CPU”

Các bản Java cũ từng sử dụng CPU shares để tính active processor count, dẫn tới JVM báo quá ít CPUs dù cgroup có thể tận dụng tài nguyên rảnh. Trên JDK 19 và các bản có backport fix, cách mặc định đã thay đổi. Hãy xem **JDK build thực tế** và ưu tiên quota/cpuset đúng nghĩa; không xây bài tập dựa trên khuyến nghị khôi phục cách tính shares legacy.

## 7. Docker và Kubernetes: CPU request khác CPU limit

### 7.1. Docker quota và cpuset

Một ví dụ Docker (chỉ khi máy có Docker và image JDK phù hợp):

```bash
docker run --rm --cpus=1.5 eclipse-temurin:25-jdk \
  java -XshowSettings:system -version
```

`--cpus=1.5` thường được chuyển thành cấu hình CPU bandwidth quota của container trên Linux; nó **không** có nghĩa chỉ tạo được 1,5 thread hoặc được khóa riêng 1,5 core.

Ví dụ khác, nếu host có các CPU IDs 0–3:

```bash
docker run --rm --cpuset-cpus=0-3 eclipse-temurin:25-jdk \
  java -XshowSettings:system -version
```

`--cpuset-cpus=0-3` ràng buộc CPU placement của container; nó không tự quy định tổng CPU-time quota bằng 4 CPU-equivalents. Một container cpuset 4 IDs có thể còn bị quota 1,5 CPU hoặc bị tranh chấp.

**Lệnh dùng dấu `\` nối dòng dành cho Bash/sh.** Nếu sử dụng Windows PowerShell hãy đặt toàn bộ lệnh trên **một dòng** hoặc dùng cú pháp nối dòng riêng; trong Docker Desktop, JVM vẫn chạy bên trong **Linux VM/container** và nên quan sát giới hạn tại đó. Các flag hoạt động thực tế tùy container runtime và OS.

### 7.2. Kubernetes CPU request

Trong Kubernetes, `resources.requests.cpu` thường được scheduler dùng để quyết định mức **đặt chỗ tài nguyên khi bố trí Pod**, đồng thời ảnh hưởng đến **trọng số CPU shares** dưới contention theo cấu hình runtime. Đây **không phải** mặc định một hard CPU-time cap.

Ví dụ yêu cầu:

```yaml
resources:
  requests:
    cpu: "500m"
```

`500m` biểu thị **0,5 CPU theo đơn vị Kubernetes** cho scheduling/request. Trong một node còn CPU rảnh, workload có thể dùng **hơn 0,5 CPU** nếu không có hard limit khác và scheduler cho phép.

**Không** viết “requests.cpu=500m → HotSpot chắc chắn thấy availableProcessors()==1” cho mọi JDK, vì shares/weight không còn mặc định là CPU-count limit trên các bản JDK đã cập nhật.

### 7.3. Kubernetes CPU limit

Ví dụ có hard cap CPU bandwidth tương đương 1,5 CPU:

```yaml
resources:
  requests:
    cpu: "500m"
  limits:
    cpu: "1500m"
```

Trong những môi trường Kubernetes Linux CPU CFS quota enforcement thường dùng:
- `request=500m`: tham gia scheduling/relative sharing.
- `limit=1500m`: có thể chuyển thành CPU bandwidth quota tương đương **1,5 CPU**.
- `availableProcessors()`: **số nguyên VM báo**, có thể phản ánh quota/cpuset theo JDK và flags; không phải con số 1,5.

**Giới hạn phụ thuộc cấu hình cluster:** CPU Manager, cgroup driver, quota enforcement settings và tính năng CPU burst có thể làm hành vi thực tế khác. Không suy từ YAML riêng mà bỏ qua cấu hình runtime/cgroup và thống kê kernel.

### 7.4. Không nhầm CPU millicores với percent CPU

`1000m=1 CPU` trong biểu diễn Kubernetes. `500m=0,5 CPU`, `1500m=1,5 CPU`. Nhưng **CPU usage %** ở dashboard có thể dùng mẫu số:
- 1 CPU;
- CPU limit;
- CPU request;
- tổng host CPUs;
- tổng CPUs được phép.

“CPU 150%” trên một chart có thể chỉ nói rằng workload sử dụng khoảng 1,5 core trong đơn vị CPU-percentage tương ứng, không nhất thiết vượt hard limit. Luôn kiểm tra mẫu số và nguồn số liệu.

## 8. Đo số CPU HotSpot thực sự báo

### 8.1. Program Java nhỏ `CpuRuntimeProbe.java`

Lưu file sau:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;

public class CpuRuntimeProbe {
    public static void main(String[] args) {
        int runtime = Runtime.getRuntime().availableProcessors();
        OperatingSystemMXBean os =
                ManagementFactory.getOperatingSystemMXBean();

        System.out.println("Runtime.availableProcessors: " + runtime);
        System.out.println("MXBean.availableProcessors: "
                + os.getAvailableProcessors());
        System.out.println("OS name: "
                + System.getProperty("os.name"));
        System.out.println("Java feature: "
                + Runtime.version().feature());
        System.out.println("Java vendor: "
                + System.getProperty("java.vendor"));
    }
}
```

Biên dịch và chạy:

```bash
javac CpuRuntimeProbe.java
java CpuRuntimeProbe
```

**Không có stdout con số cố định cho probe này.** CPU count, OS, feature version và vendor thực tế tùy máy và container. API `java.lang.management.OperatingSystemMXBean.getAvailableProcessors()` là một nguồn thông tin tương ứng về môi trường VM; đừng dùng nó làm công cụ đo CPU utilization hoặc hard quota.

### 8.2. So với ActiveProcessorCount

Trên HotSpot hỗ trợ cờ:

```bash
java -XX:ActiveProcessorCount=2 CpuRuntimeProbe
java -XX:ActiveProcessorCount=8 CpuRuntimeProbe
```

**Kỳ vọng về VM reporting** khi flag được tôn trọng:
- Lệnh đầu báo JVM active processors là 2.
- Lệnh sau báo JVM active processors là 8.
- Đây **không** phải bằng chứng OS nâng quota hoặc thay cpuset.

Nếu cần so chính xác, chạy cả hai **trong cùng container** với cùng cgroup quota, rồi đọc CPU OS-level từ `cpu.max`/`cpu.stat` ở cùng container.

### 8.3. Diagnostics không cần tự viết chương trình

Trên HotSpot Linux JDK 25, các lệnh được tài liệu hóa:

```bash
java -XshowSettings:system -version
java -Xlog:os+container=trace -version
java -XX:+PrintFlagsFinal -version
```

- `-XshowSettings:system`: hiển thị cấu hình host/container được Java nhận biết trên **Linux**.
- `-Xlog:os+container=trace`: log chi tiết quá trình container detection; hữu ích khi thấy số processor không như kỳ vọng.
- `-XX:+PrintFlagsFinal`: xem giá trị flags HotSpot, có thể tìm `ActiveProcessorCount`, `UseContainerSupport` theo cách phù hợp với shell.
- `-version`: in version rồi thoát; diagnostics có thể được viết ra `stderr` nên không lẫn với kết quả ứng dụng.

**Không bật trace logs dài dòng trong benchmark đo throughput/latency** nếu không bật tương đương ở baseline; overhead/log I/O có thể làm lệch kết quả. Dùng một pha diagnosis riêng.

### 8.4. Đọc cgroup đúng phạm vi

Trong Linux/container có cgroup v2 mount đúng tại `/sys/fs/cgroup` và process ở root của namespace đó, có thể quan sát:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpu.weight
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpu.stat
```

**Đây là ví dụ đường dẫn thông dụng, không bảo đảm mọi host/container có các file tại đúng đường đó.** Có thể tìm cgroup membership và mounts bằng `/proc/self/cgroup` cùng `/proc/self/mountinfo`; xem cả ancestor hierarchy khi cần tìm quota kế thừa. Không đổi nội dung các file kernel chỉ để chạy bài học trên hệ thống production.

Nếu môi trường dùng cgroup v1, cần đọc controller-specific paths và các file `cpu.cfs_quota_us`/`cpu.cfs_period_us`/`cpu.shares`/`cpuset.cpus` tương ứng.

### 8.5. Một bảng so sánh vận hành nên có

| Nguồn | Ví dụ giá trị | Kết luận trực tiếp |
| --- | --- | --- |
| `Runtime.availableProcessors()` | `2` | HotSpot/reporting nhìn thấy 2 processors |
| `cpu.max` | `150000 100000` | Cap CPU-time khoảng 1,5 CPU-equivalent |
| `cpuset.cpus.effective` | `0-3,8-9` | Có 6 logical CPU IDs eligible |
| `cpu.weight` | `100` | Trọng số relative, không đặt hard CPU cap |
| `cpu.stat.nr_throttled` | Delta dương | Có sự kiện throttling trong interval |
| `java -XX:+PrintFlagsFinal` | `ActiveProcessorCount=0` | VM không có explicit override bằng số dương (cần xem cờ/nguồn khác) |
| `top`/`pidstat`/APM | Thay đổi theo thời gian | CPU usage thực tế; cần hiểu denominator |

Không thể thay một dòng của bảng cho dòng khác, cũng không tự kết luận “JVM báo 2 nên không bị throttle” hoặc “cpuset 6 nên quota 1,5 không còn hiệu lực”.

## 9. Java lab đầy đủ: CPU-equivalent khác JVM planning hint

### 9.1. Mục đích

Chương trình dưới đây là **bộ mô hình số liệu**:
- `cpu.max = 150000 100000` → 1,5 CPU-equivalents.
- `cpuset.cpus.effective = 0-3,8-9` → 6 allowed IDs.
- Host minh họa có 32 logical processors.
- Một **planning hint minh họa** làm tròn quota lên 2 (đây **không** là lời hứa mọi JVM luôn làm thế).
- `ActiveProcessorCount` minh họa bằng **8**, nhưng quota vẫn **1,5**.
- Các validation chỉ xử lý input giả định; nó **không tự sửa cgroup**.
- Program kiểm tra vài trường hợp invalid, `availableProcessors()>=1` và `ForkJoinPool.commonPool().getParallelism()>=1`.

### 9.2. Mã nguồn `ContainerCpuLimitsLab.java`

Lưu file đúng tên:

```java
import java.util.BitSet;
import java.util.Locale;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.concurrent.ForkJoinPool;

public class ContainerCpuLimitsLab {
    static OptionalDouble quotaCpus(String cpuMax) {
        Objects.requireNonNull(cpuMax, "cpuMax");

        String[] parts = cpuMax.strip().split("\\s+");
        if (parts.length != 2) {
            throw new IllegalArgumentException("expected MAX PERIOD");
        }

        long period = Long.parseLong(parts[1]);
        if (period <= 0) {
            throw new IllegalArgumentException("period must be positive");
        }

        if (parts[0].equals("max")) {
            return OptionalDouble.empty();
        }

        long quota = Long.parseLong(parts[0]);
        if (quota <= 0) {
            throw new IllegalArgumentException("quota must be positive");
        }

        return OptionalDouble.of((double) quota / period);
    }

    // Parser MINH HỌA cho danh sách CPU IDs nhỏ trong bài học.
    // Không phải parser cpuset production; không xử lý mọi kernel format.
    static int cpusetCount(String spec) {
        Objects.requireNonNull(spec, "cpuset");

        if (!spec.matches(
                "[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*")) {
            throw new IllegalArgumentException("invalid cpuset");
        }

        BitSet ids = new BitSet();

        for (String token : spec.split(",")) {
            String[] range = token.split("-", -1);
            int lo = Integer.parseInt(range[0]);
            int hi = range.length == 2
                    ? Integer.parseInt(range[1]) : lo;

            if (hi < lo || hi > 8191) {
                throw new IllegalArgumentException(
                        "out of demo range");
            }

            for (int id = lo; id <= hi; id++) {
                if (ids.get(id)) {
                    throw new IllegalArgumentException("overlap");
                }
                ids.set(id);
            }
        }

        return ids.cardinality();
    }

    static void expectRejected(String label, Runnable runnable) {
        try {
            runnable.run();
            System.out.println(label + ": false");
        } catch (IllegalArgumentException ex) {
            System.out.println(label + ": true");
        }
    }

    public static void main(String[] args) {
        double quota =
                quotaCpus("150000 100000").orElseThrow();
        int cpus =
                cpusetCount("0-3,8-9");
        int hostLogical = 32;

        // Chỉ là gợi ý hoạch định minh họa, không phải
        // thuật toán VM chung hoặc thay đổi OS hard limit.
        int roundedPlanningHint =
                (int) Math.ceil(quota);
        int selectedPlanningHint =
                Math.min(cpus, roundedPlanningHint);
        int overriddenJvmHint = 8;

        System.out.printf(Locale.ROOT,
                "quota cpu equivalents: %.2f%n", quota);
        System.out.println("quota rounded planning hint: "
                + roundedPlanningHint);
        System.out.println("quota absent: "
                + quotaCpus("max 100000").isEmpty());
        System.out.println("cpuset logical IDs: " + cpus);
        System.out.println(
                "host logical processors example: " + hostLogical);
        System.out.println(
                "illustrative planning hint: " + selectedPlanningHint);
        System.out.println(
                "JVM override example: " + overriddenJvmHint);
        System.out.printf(Locale.ROOT,
                "OS quota after override: %.2f%n", quota);
        System.out.println(
                "OS limit unchanged: " + (quota == 1.5));
        System.out.println(
                "override greater than quota equivalent: "
                        + (overriddenJvmHint > quota));

        // Hai dòng sau là mô tả ngữ nghĩa OS trong ví dụ,
        // không phải phép đo scheduler đang chạy.
        System.out.println("quota shared across tasks: true");
        System.out.println(
                "CPU weight is not a hard quota: true");

        System.out.println(
                "one CPU equivalent: "
                        + quotaCpus("100000 100000").orElseThrow());
        System.out.println(
                "two effective cpuset CPUs: "
                        + cpusetCount("2-3"));

        expectRejected("zero quota rejected",
                () -> quotaCpus("0 100000"));
        expectRejected("zero period rejected",
                () -> quotaCpus("100000 0"));
        expectRejected("duplicate cpuset rejected",
                () -> cpusetCount("0-2,2"));
        expectRejected("blank cpuset rejected",
                () -> cpusetCount(""));

        System.out.println(
                "JVM availableProcessors positive: "
                        + (Runtime.getRuntime()
                            .availableProcessors() >= 1));
        System.out.println(
                "common pool parallelism positive: "
                        + (ForkJoinPool.commonPool()
                            .getParallelism() >= 1));
        System.out.println(
                "samples modeled, not host measurements: true");
    }
}
```

### 9.3. Biên dịch và chạy

Sử dụng **JDK 17+ còn được hỗ trợ và nhận cập nhật bảo mật**, chẳng hạn JDK 21/25 theo chính sách tổ chức:

```bash
javac ContainerCpuLimitsLab.java
java ContainerCpuLimitsLab
```

Không cần Docker, Kubernetes, Linux hoặc root privileges cho chương trình thuần mô hình này. Mã dùng `record`? **Không**: dùng `OptionalDouble`, `BitSet`, `Locale.ROOT`, `ForkJoinPool` và API Java SE hiện hành, nên JDK 17+ đầy đủ đều phù hợp.

### 9.4. Stdout chính xác — 21 dòng

```text
quota cpu equivalents: 1.50
quota rounded planning hint: 2
quota absent: true
cpuset logical IDs: 6
host logical processors example: 32
illustrative planning hint: 2
JVM override example: 8
OS quota after override: 1.50
OS limit unchanged: true
override greater than quota equivalent: true
quota shared across tasks: true
CPU weight is not a hard quota: true
one CPU equivalent: 1.0
two effective cpuset CPUs: 2
zero quota rejected: true
zero period rejected: true
duplicate cpuset rejected: true
blank cpuset rejected: true
JVM availableProcessors positive: true
common pool parallelism positive: true
samples modeled, not host measurements: true
```

**Đã kiểm thử 21 dòng** từ các dữ liệu hằng và điều kiện API dương trên JDK hiện đại. Chúng không phụ thuộc máy chạy có 1, 4 hay 64 CPU; hai phép kiểm cuối chỉ yêu cầu số JVM reported và parallelism luôn lớn hơn hoặc bằng 1.

### 9.5. Giải thích từng nhóm output

**Dòng 1–3: `cpu.max`**. `150000/100000=1,5` CPU-equivalent; hàm model sử dụng `ceil(1,5)=2` làm ví dụ gợi ý đếm CPU nguyên. `max 100000` nghĩa là **không đặt quota tại cgroup đang mô tả**, không phải khẳng định mọi ancestor không giới hạn.

**Dòng 4–6: cpuset và host.** `0-3,8-9` có 6 CPU IDs; host giả định 32. `Math.min(6,ceil(1,5))=2` là **minh họa hoạch định**, không phải công thức bắt buộc của mọi JDK. Không dùng nó làm validator của bản HotSpot đã cài.

**Dòng 7–10: CPU override và OS limit.** Một gợi ý VM 8 không biến quota kernel 1,5 thành 8. `OS limit unchanged: true` minh họa sự tách biệt giữa cấu hình JVM và cgroup enforcement.

**Dòng 11–12:** chương trình **in trực tiếp** hai mệnh đề đúng về mô hình CPU controller: quota áp dụng cho tổng tác vụ của cgroup và CPU weight là trọng số mềm. Đó **không phải kết quả đo kernel**; việc ghi riêng giúp người học tránh hiểu lầm.

**Dòng 13–14:** quota `100000/100000=1.0` CPU-equivalent và cpuset `2-3` có 2 CPU IDs eligible. Đây tiếp tục là hai dimension khác nhau.

**Dòng 15–18:** helper validation từ chối quota 0, period 0, cpuset trùng CPU ID và chuỗi cpuset trống. Các quy tắc này là chính sách **của parser demo**, không tuyên bố đó là một thư viện parser cgroup đầy đủ hay một lỗi VM thực tế.

**Dòng 19–20:** API `availableProcessors()` trả ít nhất 1 theo Javadoc, và common pool parallelism của `ForkJoinPool` ít nhất 1 theo hợp đồng. Không in số CPU/pool thực tế nên stdout vẫn ổn định.

**Dòng 21:** xác nhận bộ dữ liệu là giả lập. Muốn đo chính OS/container cần run probe tại phần 8 và lấy cgroup snapshots.

## 10. CPU throttling: tại sao báo “2 CPU” vẫn chậm?

### 10.1. Ví dụ quota 1,5 CPU với nhiều runnable threads

Giả sử container có `cpu.max=150000 100000` và effective cpuset có 6 CPUs. App tạo 8 worker threads đều CPU-bound.

Trong một period 100 ms, tổng CPU-time ngân sách bằng **150 ms**. Nếu kernel scheduling cho 3 threads chạy trên 3 CPUs đồng thời 50 ms, ngân sách 150 ms có thể cạn trước hết period, sau đó threads bị throttle/chờ theo luật controller. Đây chỉ là một **ví dụ chia ngân sách CPU**, scheduling thực tế tùy kernel/cpu.max.burst/ancestor/competing workloads.

Một JVM có thể báo `availableProcessors()==2` cho quota 1,5 theo chính sách sizing đã chọn, nhưng kernel vẫn **không bảo đảm** hai threads CPU-bound chạy liên tục 100 ms mỗi period (tương đương 200 ms CPU-time). Đây là điểm mấu chốt của bài.

### 10.2. CPU burst và thời gian quan sát

Một số môi trường hỗ trợ burst behavior; tài liệu kernel cgroup v2 có `cpu.max.burst`. Điều này có thể thay đổi cách CPU-time được phân phối trong các khoảng ngắn, nên một interval có thể thấy công suất tức thời cao hơn mức quota-equivalent trung bình, trong khi dài hạn vẫn chịu giới hạn.

**Không** dùng một spike CPU utilization vượt số “1,5” làm bằng chứng quota đã bị JVM phá vỡ. Kiểm tra đúng controller flags, số liệu kernel, interval measurement và dạng CPU visualization của dashboard.

### 10.3. Throttling làm tăng latency dù JVM nghĩ còn CPU

Khi JVM có nhiều runnable tasks hơn ngân sách CPU được phép:
- Request ở queue có thể chờ.
- GC/JIT workers và application workers tranh CPU-time.
- Container có thể bị throttled trước khi hoàn tất công việc trong period.
- Tail latency, timeout hoặc backpressure có thể tăng.
- Throughput không tăng tuyến tính theo số worker threads.

Việc tăng `-XX:ActiveProcessorCount` có thể khiến một số thread pools lớn hơn, tạo thêm concurrency nhưng **không tăng hard quota**. Nó có thể hữu ích hoặc gây hại tùy workload; cần A/B đo thay vì giả định “CPU count lớn hơn luôn nhanh hơn”.

### 10.4. I/O-bound và CPU-bound khác nhau

**CPU-bound:** nhiều tasks cùng cần CPU-time; quota/throttling dễ là giới hạn chính. Tăng số CPU threads quá cao có thể làm tăng context switching và queueing.

**I/O-bound:** nhiều tasks chờ network/disk/DB; concurrency có thể lớn hơn số CPU-equivalent mà vẫn hiệu quả. Nhưng threads đang runnable vẫn dùng ngân sách CPU, và external service cũng có giới hạn.

**Virtual threads** giúp mã blocking I/O có số lượng concurrent tasks lớn mà không yêu cầu một platform thread cho mỗi task; chúng **không làm quota CPU của container biến mất**. Khi xử lý CPU-intensive code trên virtual threads, kernel vẫn giới hạn CPU-time dùng cho carriers/JVM.

## 11. Monitoring: số nào đo thật, số nào chỉ là thông số cấu hình?

### 11.1. Nhóm cấu hình

| Metric/công cụ | Bản chất | Tần suất quan sát |
| --- | --- | --- |
| `Runtime.availableProcessors` | JVM reported/ergonomic CPU count, số nguyên | Startup và khi cấu hình thay đổi |
| `ActiveProcessorCount` | Override HotSpot nếu set | Ghi ở deployment/flags |
| `cpu.max` hoặc quota v1 | CPU bandwidth hard cap tại cgroup | Khi deploy/thay resource |
| `cpu.weight` hoặc shares v1 | Relative scheduling weight | Khi deploy/thay request/weight |
| `cpuset.cpus.effective` / affinity | CPUs mà tasks được phép chạy | Khi cgroup/CPU hotplug/affinity đổi |
| `lscpu` | Host/hardware topology được công cụ quan sát | Không thay cgroup limits |
| `/proc/self/cgroup`, `/proc/self/mountinfo` | Cgroup membership và mount | Để xác định đúng path |

### 11.2. Nhóm số liệu sử dụng thật

| Metric | Cách diễn giải |
| --- | --- |
| `usage_usec` | CPU-time cgroup đã sử dụng tích lũy, tính delta |
| `nr_periods` | Số chu kỳ controller ghi nhận, nếu có |
| `nr_throttled` | Số sự kiện/chu kỳ throttling theo controller và version, tính delta |
| `throttled_usec` | Thời gian throttled tích lũy theo semantics kernel, tính delta |
| Process CPU-time | Tổng CPU-time JVM tiêu thụ; không phải elapsed wall-clock |
| CPU load / process load | Một tỷ lệ được implementation tính trên khoảng sampling |
| RPS/QPS | Số request xử lý thành công trong interval |
| p50/p95/p99 | Phân phối latency; cần giữ request mix và offered load |
| Run queue/pressure | Tác vụ runnable phải chờ CPU; xem dashboard và PSI `cpu.pressure` nếu phù hợp |

**Không** lấy `availableProcessors` làm nguồn duy nhất cho dashboard autoscaling, hoặc lấy `usage_usec` tích lũy một lần rồi gọi đó là CPU% hiện tại.

### 11.3. Tính CPU consumption từ delta

Nếu trong 5 giây, `cpu.stat.usage_usec` tăng 7.500.000 microseconds thì **CPU-equivalent tiêu thụ trung bình** xấp xỉ:

\[
\frac{7{,}500{,}000\,\mu s}{5{,}000{,}000\,\mu s}
=1.5
\]

Đó là **CPU-time consumed / wall-time** của cgroup đo được; nó khác với hard cap được cấu hình. Nếu cgroup vừa chứa nhiều processes, CPU-time tổng phản ánh tất cả những processes ấy. Nếu host hoặc quota làm nhiệm vụ chờ, consumed thấp hơn cap là chuyện bình thường.

Khi quy đổi thành `%`, nói rõ denominator: **100% của 1 CPU**, **100% của quota 1,5 CPU**, hay **100% của host 32 CPU** là ba số đo khác nhau.

### 11.4. Diễn giải throttling cùng latency

Một cgroup có `nr_throttled` tăng khi workload CPU-bound và p99 latency xấu thì có **bằng chứng đáng điều tra** về CPU bandwidth cap. Tuy nhiên cần kiểm tra:
- có đủ offered load không;
- GC pauses/JIT contention có thay đổi không;
- tài nguyên DB/network có bị giới hạn không;
- throttling nằm ở child hay ancestor;
- CPU requests/weights cạnh tranh với workload khác không;
- cgroup burst/CPU Manager configuration thế nào.

Không chứng minh nguyên nhân trực tiếp chỉ bằng một counter tăng trong một khoảng ngắn. Kết hợp tracing, profiling và A/B thay quota/cpu pool size có kiểm soát.

## 12. Benchmark A/B: kiểm tra JVM count và OS limit độc lập

### 12.1. Xây ma trận thay một biến mỗi lượt

Một matrix hợp lý trên cùng **JDK, ứng dụng, kernel, CPU affinity, memory, GC và workload**:

| Trial | cgroup quota | JVM ActiveProcessorCount | Câu hỏi |
| --- | --- | --- | --- |
| A | 1,5 CPU-equivalent | Mặc định auto | HotSpot auto-sizing ra sao? |
| B | 1,5 CPU-equivalent | 2 | Override 2 có khác auto không? |
| C | 1,5 CPU-equivalent | 8 | Thêm VM parallelism có lợi/hại dưới cùng quota? |
| D | 3 CPU-equivalent | Mặc định auto | Tác động tăng **OS quota thật** khi các biến khác cố định? |
| E | 3 CPU-equivalent | 2 | VM hint 2 có giới hạn tự chọn pool dù OS cho nhiều thời gian hơn? |

Các trial chỉ có ý nghĩa nếu cgroup files và VM flags thực sự phản ánh điều bạn cấu hình. Một bài test đổi đồng thời JDK và request mix sẽ không tách được nguyên nhân.

### 12.2. Thu thập và công bố các chỉ số

Cho mỗi trial:
1. Ghi `Runtime.availableProcessors()` và các flags JVM.
2. Ghi `cpu.max`, effective cpuset và ancestor limits nếu có.
3. Chạy warmup theo quy tắc đã công bố.
4. Chạy tải nhất quán, ghi RPS thành công, error rate, p95/p99 latency.
5. Chụp `cpu.stat` đầu/cuối interval, tính delta usage/throttling.
6. Ghi CPU quota, memory limit, CPU Manager, OS, JDK build/vendor.
7. Lặp nhiều lần và đảo thứ tự trial để giảm bias.
8. Kết luận **trong điều kiện thí nghiệm**, không khái quát quá mức.

**Đừng chỉ nhìn số thread pool do `ForkJoinPool` tạo và suy ra CPU limit của OS đã thay đổi.** Kết quả pool size là JVM/ứng dụng behavior; quota enforcement ở kernel.

### 12.3. Những quan sát có thể xảy ra

- **B và C cùng throughput, C p99 xấu hơn:** nhiều workers có thể gây contention/throttling hơn; cần profiling để xác nhận.
- **B và C khác rất ít:** workload có thể không dùng thêm pool hoặc quota là bottleneck.
- **D tăng RPS khi tăng OS quota:** có bằng chứng trước đó bị CPU-constrained, nếu các điều kiện khác như nhau.
- **D không tăng RPS:** bottleneck có thể ở DB, network, locks, algorithm hoặc request generator.
- **JVM báo 8 khi quota 1,5:** đây là cấu hình hợp lệ về mặt flag; kernel không vì vậy nới cap.

Không có công thức chung `throughput = availableProcessors × constant`; thread pools, tasks, scheduler, throttling và latency làm quan hệ phi tuyến.

## 13. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`availableProcessors()==8` nghĩa container có 8 CPU dedicated” | API mô tả số VM nhìn thấy, không cam kết lõi độc quyền | Đọc cgroup/affinity và usage |
| “Quota 1,5 có nghĩa kernel chỉ tạo được một thread” | Quota là ngân sách thời gian, không phải thread-count cap | Phân biệt concurrency và CPU-equivalent |
| “`cpu.max=150000 100000` nghĩa có 150000 CPUs” | Hai số là microseconds quota/period | Chia 150000/100000=1,5 |
| “`cpuset.cpus.effective=0-3` bảo đảm 4 CPU liên tục” | Placement không phải băng thông CPU | Xem quota, weight, contention |
| “`cpu.weight=50` là hard 0,5 CPU” | Weight là relative scheduling priority | Không quy đổi weight thành hard cap |
| “JDK 10 CPU shares behavior giống JDK 25” | JDK 19 và backports thay đổi cách tính shares | Dựa vào JDK version/build và log |
| “`ActiveProcessorCount=8` mở rộng quota Linux” | Chỉ override VM ergonomic count | Sửa resource limit ở orchestration nếu cần |
| “Tắt `UseContainerSupport` làm container có thêm CPU” | Kernel vẫn áp cgroup | Không dùng làm resource-limit workaround |
| “Docker `--cpus=1.5` nghĩa đúng 1,5 CPUs được JVM trả về” | Java API trả số nguyên | Quan sát JVM count; quota là số thực |
| “Không có limit trong cpu.max con nghĩa không có limit” | Parent cgroup có thể giới hạn | Kiểm tra hierarchy |
| “JVM chạy trong container nên đọc `/sys/fs/cgroup/cpu.max` luôn đúng” | Mount/cgroup namespace có thể khác | Dựa vào membership/mountinfo |
| “`cpu.stat` là CPU% ngay lúc đọc” | Là các bộ đếm tích lũy | Tính delta/time |
| “JVM báo nhiều CPU nên GC luôn nhanh hơn” | Thêm workers có thể đụng quota và tăng contention | Benchmark GC pause/cpu.stat |
| “Thread pool size bằng hard CPU cap” | Pool là concurrency config, OS là scheduler | Tách hai nguồn thông tin |
| “Request 500m trong Kubernetes là hard 0,5 CPU” | Requests chủ yếu scheduling/share weight | Phân biệt limits |
| “Limit 1500m bảo đảm 1,5 CPU mọi lúc” | Là upper bound, không bảo đảm được dùng đủ khi có contention | Đo usage và node pressure |
| “Host lscpu 64 nghĩa JVM có 64 CPUs trong container” | Container/affinity có thể ràng buộc | Đọc VM/OS limits |
| “Một sample throttled_usec tăng chứng minh bug JVM” | Có thể do workload và config hợp lệ | Lấy delta, kiểm tra quota/latency |
| “Tăng thread count tới 100 để dùng hết 1,5 CPU” | Có thể tăng queueing/context switch | Chọn theo workload và đo |
| “Virtual threads loại bỏ CPU quota” | Carriers vẫn chạy dưới kernel scheduler | Dùng để tối ưu blocking I/O, không phá hard cap |
| “Số processor JVM nhận biết không bao giờ thay đổi” | Javadoc cho phép thay đổi | Tính đến reconfiguration và kiểm tra runtime |
| “Mọi JDK đều dùng chung thuật toán round quota” | Implementation, version và overrides khác nhau | Dùng log và `availableProcessors()` thật |

## 14. Bài tập có đáp án

### Bài 1 — Tính quota 1,5 CPU

**Đề:** Linux cgroup v2 có `cpu.max = 150000 100000`. CPU-equivalent là bao nhiêu?

**Đáp án:** `150000/100000 = 1,5` CPU-equivalents. Đây là ngân sách CPU-time cgroup theo period, không phải 1,5 threads hay CPU ID.

### Bài 2 — CPU count JVM 2 nhưng quota 1,5

**Đề:** JVM trong cgroup trên báo `availableProcessors()==2`. Có mâu thuẫn không?

**Đáp án:** Không. API trả **số nguyên**; VM có thể dùng quy tắc sizing làm tròn hoặc nguồn dữ liệu khác. Kernel vẫn giới hạn CPU-time tương đương 1,5.

### Bài 3 — Override 8

**Đề:** Với cùng cgroup 1,5 CPU, chạy `java -XX:ActiveProcessorCount=8 ...`. CPU hard quota biến thành 8 không?

**Đáp án:** Không. Override thay con số VM dùng để tính pool sizes; OS vẫn áp quota/cpuset/affinity.

### Bài 4 — Host vs cpuset

**Đề:** Host có 32 logical CPUs; effective cpuset `0-3,8-9`. Cgroup có thể dùng các CPU IDs nào?

**Đáp án:** Các IDs 0,1,2,3,8,9 — **6 logical CPUs**. Không tự dùng 26 IDs còn lại nếu cpuset/affinity ràng buộc.

### Bài 5 — Placement không phải bandwidth

**Đề:** Cpuset có 6 IDs, quota tương đương 1 CPU. Có thể chạy CPU-bound liên tục trên 6 CPUs mà không bị quota ảnh hưởng không?

**Đáp án:** Không. Có thể scheduling trên các CPUs trong tập được phép nhưng tổng CPU-time của cgroup vẫn phải tuân quota.

### Bài 6 — CPU weight

**Đề:** Cgroup v2 có `cpu.weight=100`. Có thể suy ra hard CPU limit bằng 1 CPU không?

**Đáp án:** Không. `cpu.weight` là trọng số chia CPU khi tranh chấp. Hard CPU bandwidth cap nằm ở `cpu.max` hoặc ở ancestor tương ứng.

### Bài 7 — Cgroup không đặt cap tại con

**Đề:** `cpu.max` của cgroup hiện tại là `max 100000`. Có bảo đảm workload có không giới hạn CPU-time không?

**Đáp án:** Không. Nó chỉ nói cgroup này không đặt cap trực tiếp. Parent quota, cpuset, affinity, scheduler và tài nguyên host vẫn có thể giới hạn.

### Bài 8 — Kubernetes requests và limits

**Đề:** Pod request `500m`, limit `1500m`. Hai số có nghĩa gì?

**Đáp án:** Request 0,5 CPU dùng cho scheduling/relative shares; limit 1,5 CPU là CPU bandwidth cap khi enforced. JVM processor count là số nguyên riêng, không phải hai giá trị này.

### Bài 9 — Shares và JDK 25

**Đề:** Tài liệu cũ nói `cpu.shares=512` khiến JVM báo ít processor hơn. Có nên áp dụng trực tiếp cho JDK 25?

**Đáp án:** Không. Từ JDK 19, JDK không còn mặc định dùng CPU shares để quyết định active count; có backports theo build. Hãy quan sát runtime và đọc tài liệu version cụ thể.

### Bài 10 — CFS throttling

**Đề:** `nr_throttled` tăng 200 trong một cửa sổ. Có thể kết luận `availableProcessors()` sai không?

**Đáp án:** Không. Bộ đếm cho thấy quota throttling xảy ra, không chứng minh JVM detection bug. Cần xem quota, load, scheduler, affinity, GC/JIT và latency cùng interval.

### Bài 11 — CPU-time tiêu thụ

**Đề:** Trong 5 giây, `cpu.stat.usage_usec` tăng 7.500.000. Mức CPU-time consumption trung bình xấp xỉ bao nhiêu core?

**Đáp án:** `7.500.000 / 5.000.000 = 1,5` CPU-equivalent trung bình. Nó không chứng minh hard quota là 1,5; có thể chỉ là usage.

### Bài 12 — Tuning thread pool

**Đề:** JVM báo 2 processors nhưng app tạo fixed thread pool 64 threads. JDK có buộc pool chỉ được 2 threads không?

**Đáp án:** Không. Application đã yêu cầu 64 threads; kernel sẽ scheduling theo CPU constraints. Pool size nên dựa workload và benchmark chứ không chỉ một số.

### Bài 13 — Thay đổi runtime

**Đề:** Orchestrator tăng CPU quota khi JVM đang chạy. Có bảo đảm mọi executor tự resize ngay không?

**Đáp án:** Không. Javadoc cho phép CPU count có thể thay đổi, nhưng các thư viện/pools có thể giữ cấu hình đã đọc lúc tạo; kiểm thử JDK/framework cụ thể, cấu hình lại hoặc restart nếu cần.

### Bài 14 — Diễn giải output mô hình

**Đề:** Lab có `quota cpu equivalents: 1.50`, `illustrative planning hint: 2` và `JVM override example: 8`. Con số nào là kernel budget?

**Đáp án:** `1.50` là CPU-equivalent quota đã khai báo trong dữ liệu giả định. Hai số `2` và `8` là hint/override minh họa, không phải actual available physical CPUs hay limit do kernel đổi.

### Bài 15 — Đo trên Windows host dùng Docker Desktop

**Đề:** Host chạy Windows, Docker Desktop chạy Linux container. Nên đọc `cpu.max` ở host PowerShell hay bên trong Linux container?

**Đáp án:** Đọc **bên trong Linux environment**/cgroup mount đúng scope container và đồng thời xem `-XshowSettings:system`/JVM flags ở process Java đó. Windows host không có trực tiếp cùng cgroup namespace.

### Bài 16 — Đổi active processor count có tăng throughput chắc chắn không?

**Đề:** Cùng quota 1,5 CPU, đổi `ActiveProcessorCount=2` sang `8`. Có được kết luận RPS tăng 4 lần?

**Đáp án:** Không. Tăng VM hint không tăng quota. Tùy workload, pool/JIT/GC và throttling, throughput có thể tăng, giảm hoặc gần như không đổi. Cần benchmark và đo latency/CPU-time thật.

## 15. Checklist trước khi đưa vào hệ thống

- [ ] Ghi rõ **JDK distribution/build**, host OS, kernel, container runtime và cgroup version.
- [ ] Biết từ Java 10 HotSpot Linux có container awareness, không suy rằng `availableProcessors` mới xuất hiện ở JDK 10.
- [ ] Đọc `Runtime.availableProcessors` như số nguyên JVM nhận biết, không là CPU utilization hoặc dedicated cores.
- [ ] Phân biệt host logical CPUs, affinity/effective cpuset và quota/period.
- [ ] Biết `cpu.max` là bandwidth quota; `cpu.weight` là trọng số.
- [ ] Biết quota 1,5 CPU-equivalent không phải JVM báo số thực 1,5.
- [ ] Không dùng CPU shares/weight làm hard limit và không tái áp dụng thuật toán legacy cho JDK25.
- [ ] Đọc tài liệu cgroup v1/v2 đúng phiên bản kernel, không giả định tên/path chung cho mọi container.
- [ ] Xem ancestor limits và affinity nếu kết quả trái kỳ vọng.
- [ ] Hiểu `-XX:ActiveProcessorCount` không sửa OS quota/cpuset.
- [ ] Không dùng `-XX:-UseContainerSupport` như giải pháp “nới CPU”.
- [ ] Nếu debug, dùng `-XshowSettings:system` và `-Xlog:os+container=trace` trên HotSpot Linux có hỗ trợ.
- [ ] Không dùng VM trace logs nặng chỉ ở một bên benchmark.
- [ ] Phân biệt Kubernetes CPU `requests` và `limits`, kiểm tra cgroup enforcement thực tế.
- [ ] Tính delta `cpu.stat`/CPU-time trên cùng interval, không gọi tích lũy thành usage%.
- [ ] Ghi rõ dashboard CPU% dùng denominator nào.
- [ ] Đo process CPU, throttling, RPS, p95/p99 latency và GC khi tối ưu.
- [ ] Không cho rằng tất cả libraries/thread pools cập nhật tự động khi quota thay đổi.
- [ ] Không giả định tăng concurrency hoặc virtual threads có thể vượt kernel CPU bandwidth cap.
- [ ] Chạy `CpuRuntimeProbe.java` để quan sát số CPU/JVM thật; không chốt cứng stdout.
- [ ] Chạy `ContainerCpuLimitsLab.java` và đối chiếu chính xác **21 dòng stdout giả lập**.
- [ ] Ra quyết định theo kết quả đo trên workload thật, có đối chứng cùng JDK và limits.

## 16. Tổng kết

**Số CPU JVM nhận biết là một chỉ số **quản trị tài nguyên/ergonomics** trong VM, còn giới hạn thực thi CPU do **Linux kernel, cgroup và affinity** quản lý.** Từ Java 10, HotSpot biết nhiều hơn về CPU trong Linux container để chọn cấu hình thích hợp, nhưng không được đồng nhất `Runtime.availableProcessors()` với quota hoặc số physical cores.

Một container có **host 32 logical CPUs, effective cpuset 6 CPU IDs và quota 1,5 CPU-equivalent** vẫn có thể có **JVM active count = 2** hoặc được cấu hình override thành **8**. Kernel **không cấp thêm CPU-time** khi override. Vì thế khi ứng dụng chậm, phải đọc đúng **cgroup CPU quota, cpuset, CPU weights, CPU usage/throttling và RPS/latency thực tế**, không chỉ in một số từ JVM.

Đây là kiến thức **vẫn áp dụng trên JDK hiện đại**; riêng cách VM xem CPU shares đã thay đổi từ JDK 19/các bản backport, nên tránh khuyến nghị legacy dựa vào shares. Nếu cần tối ưu, điều chỉnh OS resource limits và VM/thread-pool configuration theo **hai trục độc lập**, kiểm thử có đối chứng rồi đánh giá trên metric nghiệp vụ.

## 17. Tài liệu tham khảo chính thức

- [Oracle JDK 10 — Release Notes, Java Improvements for Docker Containers](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): JDK-8146115, Linux container CPU/memory detection từ JDK 10; `UseContainerSupport` và `ActiveProcessorCount`.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:ActiveProcessorCount`, `-XX:-UseContainerSupport`, `-XshowSettings:system` và `-Xlog:os+container=trace`.
- [Oracle Java SE 25 — java.lang.Runtime.availableProcessors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#availableProcessors()): hợp đồng CPU count JVM, luôn lớn hơn hoặc bằng một và có thể thay đổi.
- [Oracle JDK 19 — Release Notes, CPU Shares Ignored When Computing Active Processor Count](https://www.oracle.com/java/technologies/javase/19-relnote-issues.html): JDK-8281181, lý do CPU shares không nên được coi là hard processor count.
- [Linux Kernel — Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.max`, `cpu.weight`, `cpu.stat`, `cpuset.cpus.effective` và tính hierarchical.
- [Linux Kernel — The /proc Filesystem](https://docs.kernel.org/filesystems/proc.html): `/proc/PID/status`, affinity và thông tin tiến trình.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): `requests`/`limits` CPU và memory, resource scheduling/quota behavior.
- [Docker Docs — Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): `--cpus`, `--cpu-quota`, `--cpu-period`, `--cpu-shares` và `--cpuset-cpus`.
- [Oracle Java SE 25 — java.lang.management.OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html): `getAvailableProcessors` và quản lý thông tin OS theo JVM.
- [Oracle Java SE 25 — ForkJoinPool](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool parallelism, tách pool behavior khỏi hard CPU limit.