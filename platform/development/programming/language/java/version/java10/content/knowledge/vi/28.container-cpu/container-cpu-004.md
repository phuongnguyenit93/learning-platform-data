# cpuset, quota và số bộ xử lý JVM có thể sử dụng (Java 10+)

## 1. Vì sao container có 1,5 CPU nhưng Java lại báo 2?

Một container có thể nhận **CPU quota** tương đương 1,5 CPU nhưng lời gọi:

```java
int n = Runtime.getRuntime().availableProcessors();
```

lại trả `2`. **Đây có thể là kết quả đúng.** Linux quản lý ngân sách CPU dưới dạng **thời gian sử dụng CPU theo chu kỳ**, còn `Runtime.availableProcessors()` trả **số nguyên** dùng để JVM và thư viện lập kế hoạch song song.

Ví dụ:

```text
cpuset hiệu lực:      0-3             => 4 CPU logic được phép
CPU quota / period:   150000 / 100000 => 1,5 CPU theo thời gian
Processor count JVM:                  => min(4, ceil(1,5)) = 2
```

Điểm mấu chốt: **2 processors JVM báo không bảo đảm container được cấp riêng 2 lõi vật lý**. Linux vẫn có thể **throttle** khi các luồng tiêu thụ hết quota 1,5 CPU trong kỳ.

Bài thuộc chủ đề cha **CPU trong container** của module Java 10, tập trung ba cơ chế rất dễ nhầm:

- **cpuset / CPU affinity:** process được phép chạy trên những CPU IDs nào.
- **CPU quota / period:** cgroup được tiêu thụ tổng bao nhiêu thời gian CPU.
- **active processor count:** số nguyên HotSpot dùng để tự điều chỉnh GC, ForkJoinPool và những thành phần dựa vào `availableProcessors()`.

**Mục tiêu học tập:** đọc cgroup v1/v2, hiểu phép tính và làm tròn, phân biệt requests/limits/shares, kiểm tra `UseContainerSupport` và `ActiveProcessorCount`, chạy ví dụ Java 17+, chẩn đoán throttling cũng như tránh những cờ JVM cũ đã lỗi thời.

**Nguyên tắc vận hành:** khi xử lý một container thật, hãy xem dữ liệu Linux và log của **chính JVM đang chạy**. Công thức trong bài là mô hình giải thích hành vi HotSpot hiện hành, không phải một lời bảo đảm cố định cho mọi bản JDK, mọi container runtime và mọi platform.

## 2. Java 10 và khả năng nhận biết giới hạn container

Trên Linux, HotSpot từ **Java 10** đã có cơ chế container awareness để dùng giới hạn tài nguyên của cgroups thay vì chỉ nhìn toàn bộ cấu hình của host. Tùy chọn:

```text
-XX:+UseContainerSupport
```

được bật mặc định trên môi trường HotSpot Linux được hỗ trợ và vẫn có trong tài liệu **Java SE 27**.

Điều đó giúp JVM lựa chọn kích cỡ một số cấu trúc, thread pools và GC worker counts dựa trên tài nguyên mà process container có thể sử dụng. Nhưng có những điều kiện:

1. JVM phải có phiên bản và implementation hỗ trợ kiểu **cgroups** đang dùng.
2. Linux phải cung cấp controller và namespace/mount information mà JVM đọc được.
3. Các giới hạn **quota/cpuset/affinity** có thể kết hợp theo nhiều cách.
4. Cờ người dùng như `-XX:ActiveProcessorCount` có thể **override** phép suy luận.
5. Việc một flag mặc định bật không chứng minh mọi giới hạn được phát hiện chính xác; phải kiểm tra thực tế.

### 2.1. Lịch sử ngắn và Special Note

- **Java 10:** container detection của HotSpot được bật mặc định trên Linux ở môi trường được hỗ trợ.
- **Java 15:** hỗ trợ **cgroups v2** được tích hợp vào OpenJDK; một số dòng LTS nhận backport qua các update releases thích hợp.
- **JDK 18.0.2 / JDK 19 và các backport:** theo **JDK-8281181**, CPU shares không còn mặc định bị diễn giải như số CPUs cố định, tránh tạo quá ít worker threads.
- **JDK 21 trở đi:** cơ chế flag legacy để khôi phục cách tính CPU shares đã bị loại bỏ, không còn là cách cấu hình được khuyến nghị.
- **JDK 25–27:** `UseContainerSupport`, `ActiveProcessorCount`, `Runtime.availableProcessors()` vẫn là cơ chế/khái niệm cần hiểu.

**Không khuyên chạy JDK 10 cũ trong production** chỉ vì bài học xuất phát từ Java 10. Dùng bản JDK hiện hành, có bản vá bảo mật, hỗ trợ cgroups tương ứng và kiểm tra release notes của distribution đó.

**Không khuyên dùng những cờ lỗi thời** như `-XX:+UseContainerCpuShares` hay các tùy chọn container experimental đời cũ. Muốn chủ động đặt processor count, dùng `-XX:ActiveProcessorCount=N`, có lý do và benchmark.

## 3. CPU logic, CPU vật lý và tập affinity

Các CPU IDs mà Linux liệt kê là **logical processors**. Tùy host có SMT/Hyper-Threading hay không, hai logical CPUs có thể chia sẻ tài nguyên của một physical core. Vì vậy:

```text
cpuset = 0-3       => 4 CPU logic
cpuset = 0-3,7     => 5 CPU logic
cpuset = 1,3,5-6   => 4 CPU logic
```

Nó **không** chứng minh workload đã nhận số lõi vật lý tương ứng hoặc độc quyền.

### 3.1. Ý nghĩa của cpuset

Cpuset là một tập CPU logic mà task/cgroup có thể được scheduler chạy trên đó. Ví dụ:

```text
CPU host: 0,1,2,3,4,5,6,7
cpuset:   0,1,2,3
```

Process không được chạy trên 4–7 theo cpuset này. Nhưng CPU 0–3 vẫn có thể chạy tasks thuộc các cgroups khác, trừ khi người quản trị áp dụng chính sách cách ly/phân vùng thực sự.

**Không đồng nhất “CPU có thể chạy” với “CPU được đặt riêng”.**

### 3.2. Affinity còn phụ thuộc OS và parent cgroup

Ngoài cpuset cgroup, Linux có task affinity từ `sched_getaffinity`, `taskset` hoặc `numactl`. Parent cgroup cũng giới hạn tài nguyên của child; CPUs có thể online/offline.

Với cgroup v2:

```text
cpuset.cpus            => CPU set được yêu cầu, có thể trống
cpuset.cpus.effective  => CPU set thực sự được hệ thống cấp
```

Nếu `cpuset.cpus` trống, **không** phải process có 0 CPU. Linux có thể cho kế thừa cpuset từ ancestor. Hãy đọc `cpuset.cpus.effective`.

Ví dụ:

```text
cpuset.cpus:
cpuset.cpus.effective: 0-3
```

Dòng đầu rỗng và dòng hai là `0-3` hoàn toàn có thể hợp lệ.

### 3.3. Không dùng `lscpu` của host làm CPU count container

`lscpu` trên host có thể báo 32 logical CPUs, trong khi container có cpuset chỉ 0–3. Hãy kiểm tra **bên trong container** và đối chiếu với affinity/cgroup thay vì suy ra từ tổng CPUs của máy.

## 4. CPU quota/period: giới hạn tổng thời gian CPU

Linux CPU bandwidth controller dùng quota và period để định nghĩa CPU budget.

```text
CPU capacity = quota_us / period_us
```

Ví dụ:

```text
quota_us  = 150000
period_us = 100000
capacity  = 1,5 CPU
```

Điều đó có nghĩa các threads thuộc cgroup có tổng ngân sách tương đương 150 ms thời gian CPU trong chu kỳ 100 ms wall-clock. Nhiều threads có thể chạy đồng thời trong một đoạn ngắn và dùng hết budget, sau đó bị **throttling**.

Không nên hiểu thành “một lõi cố định chạy 100% và nửa lõi cố định chạy 50%” hoặc “container chỉ có đúng 1,5 hardware threads”.

### 4.1. Ví dụ với fractional CPU

| Quota (µs) | Period (µs) | CPU capacity |
| ---: | ---: | ---: |
| 25000 | 100000 | 0,25 |
| 50000 | 100000 | 0,5 |
| 100000 | 100000 | 1,0 |
| 150000 | 100000 | 1,5 |
| 200000 | 100000 | 2,0 |
| 350000 | 100000 | 3,5 |

Thời gian CPU sử dụng thực tế còn phụ thuộc scheduler và khối lượng công việc. Bảng là **giới hạn ngân sách lý thuyết**, không phải throughput có thể bảo đảm.

### 4.2. Không có quota và parent cgroup

Trong cgroups v1, giá trị `cpu.cfs_quota_us=-1` thường nghĩa là không có quota tại controller đó.

Trong cgroups v2:

```text
cpu.max = max 100000
```

biểu thị không đặt quota ở cgroup này. Tuy nhiên, **ancestor/parent cgroup** có thể vẫn đặt CPU bandwidth limit. Affinity/cpuset và CPU contention cũng có thể hạn chế công việc.

Do đó, không bao giờ suy luận “`max` = không thể bị giới hạn CPU bởi bất cứ thứ gì”.

## 5. Từ quota/cpuset tới `availableProcessors()`

`Runtime.getRuntime().availableProcessors()` trả `int`. HotSpot container-aware trên Linux trong cấu hình phổ biến tính số processors từ quota và OS affinity. Mô hình đơn giản:

```text
quotaCpuCount = ceil(quota_us / period_us)
activeCount   = min(effectiveAffinityCpuCount, quotaCpuCount)
```

Nếu **không có quota**, hệ thống thường dựa vào effective affinity/online CPUs. Nếu có `ActiveProcessorCount=N`, override được áp dụng trước những phép tính tự động này.

### 5.1. Cách làm tròn

HotSpot làm tròn lên quota phân số để trả số CPU nguyên, ví dụ:

```text
ceil(0,25) = 1
ceil(1,0)  = 1
ceil(1,5)  = 2
ceil(2,1)  = 3
```

Quy tắc này giúp JVM định kích thước một số công việc song song. Nó **không đổi CFS quota mà Linux thực thi**.

### 5.2. Các trường hợp kết hợp

| Effective CPUs | Quota/period | Capacity | Count mô hình |
| --- | --- | ---: | ---: |
| `0-3` = 4 IDs | `150000/100000` | 1,5 | **2** |
| `0-1` = 2 IDs | `350000/100000` | 3,5 | **2** |
| `0-7` = 8 IDs | `25000/100000` | 0,25 | **1** |
| `0-7` = 8 IDs | `200000/100000` | 2,0 | **2** |
| `0-3` = 4 IDs | Không quota | không giới hạn riêng | **4** |

**Đây không phải cam kết output của mọi JVM**, vì cgroups/hotspot revisions, nested groups, OS affinity, unsupported controllers và override có thể làm khác. Cách xác minh cuối cùng là **chạy đúng JDK trong đúng container**.

### 5.3. Khi `Runtime.availableProcessors()` khác con số bạn tính

Kiểm tra:

- `-XX:ActiveProcessorCount` có được đặt không?
- `UseContainerSupport` có bị tắt không?
- Hệ thống dùng cgroups v1 hay v2?
- JDK có nhận diện đúng cgroup hiện tại không?
- Cpuset effective khác cpuset requested không?
- `taskset`/affinity process có thêm giới hạn không?
- Parent cgroup có ràng buộc khác không?
- CPU shares/weight có bị nhầm thành quota không?
- Cấu hình quota có thực sự được áp dụng cho **đúng container đang chạy** không?

**Không sửa kết quả bằng cách lấy max thay cho min**: quota cao hơn không cấp phép chạy trên CPU IDs ngoài affinity.

## 6. cgroups v2: các file cần biết

Trên Linux với cgroups v2 được mount theo layout thường gặp:

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpu.stat
```

Ví dụ đầu ra:

```text
cpu.max:               150000 100000
cpuset.cpus:           0-3
cpuset.cpus.effective: 0-3
```

Đây là **ví dụ minh họa**, không phải log được lấy từ máy chạy chương trình Java bên dưới.

**`cpu.max`:** cặp giá trị `quota period`, hoặc `max PERIOD` nếu không có quota tại cgroup. Đơn vị thời gian là microseconds.

**`cpuset.cpus`:** tập CPU yêu cầu. File có thể trống vì kế thừa; đừng đọc “trống” thành “không có CPU”.

**`cpuset.cpus.effective`:** tập CPU được phép thực tế, sau khi xét parent và CPU online.

**`cpu.stat`:** cung cấp bộ đếm thời gian CPU, cùng statistics về bandwidth throttling nếu controller hỗ trợ/được bật.

### 6.1. Nhận diện throttling

Một `cpu.stat` minh họa:

```text
usage_usec 128000000
user_usec 100000000
system_usec 28000000
nr_periods 20000
nr_throttled 4100
throttled_usec 710000000
```

Các giá trị trên **không phải số đo của bài thực hành**.

- `usage_usec`: CPU time đã được tính.
- `nr_periods`: số chu kỳ của bandwidth controller.
- `nr_throttled`: số kỳ đã xảy ra throttling.
- `throttled_usec`: thời lượng throttling tích lũy theo kernel.

Cần **đo hiệu số các counter giữa hai thời điểm**, không dựa vào một giá trị tích lũy duy nhất. Kết hợp CPU quota, request latency, GC logs và CPU utilization. Không coi `throttled_usec` là số milliseconds bị block của một request HTTP cụ thể.

### 6.2. Nested cgroups và mount namespace

Linux cgroup là một **cây phân cấp**: child cgroup không thể vượt qua giới hạn của parent. Một container runtime còn có cgroup namespace và có thể mount cgroup FS ở vị trí riêng.

Nếu file tại `/sys/fs/cgroup` vắng mặt hoặc không thể đọc:

- xem `/proc/self/cgroup` và `/proc/self/mountinfo`;
- kiểm tra cgroup version của node;
- hỏi platform/cluster configuration;
- dùng `java -XshowSettings:system -version` và `-Xlog:os+container=trace` để quan sát những gì JVM nhận diện.

**Không tự động kết luận không có CPU limit chỉ vì file path mặc định không đọc được.**

## 7. cgroups v1 và khác biệt đường dẫn

Cgroups v1 sử dụng nhiều mounts cho các controllers. Các file thường gặp:

```text
cpu.cfs_quota_us
cpu.cfs_period_us
cpu.stat
cpuset.cpus
cpu.shares
```

Trong v1, **không** dùng `cpu.max`; đó là interface của v2. Đường dẫn chính xác tới các file có thể nằm trong controller mounts khác nhau, tùy `/proc/self/cgroup` và `mountinfo`.

Vì vậy một hướng dẫn chỉ viết:

```bash
cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us
```

có thể phù hợp một hệ thống v1 nhưng **không phải đường dẫn bảo đảm ở mọi distro/container**.

**Đối với Java 10:** vì cgroups v2 support được bổ sung ở JDK mới hơn, không nên kỳ vọng một JDK 10 cổ tự hiểu `cpu.max` trên node Linux hiện đại. Lựa chọn tốt là nâng lên một JDK còn được bảo trì và hỗ trợ phiên bản cgroup của node.

## 8. CPU shares và CPU weight không phải hard quota

Linux còn có cơ chế phân chia CPU dựa trên **trọng số tương đối** giữa các cgroups:

| Mục tiêu | cgroups v1 | cgroups v2 |
| --- | --- | --- |
| Hard CPU bandwidth cap | `cpu.cfs_quota_us` và `cpu.cfs_period_us` | `cpu.max` |
| CPU IDs được phép | `cpuset.cpus` | `cpuset.cpus.effective` |
| Relative CPU scheduling weight | `cpu.shares` | `cpu.weight` |

Shares/weight chỉ có ý nghĩa so với các cgroups khác **khi tài nguyên tranh chấp**. Nếu host còn dư CPU, cgroup có relative weight thấp vẫn có thể dùng nhiều CPU hơn mức “shares/1024” mà ai đó tính nhầm thành quota.

### 8.1. Sự thay đổi ở JDK mới

Những JDK trước từng dùng `cpu.shares` để suy ra số processors, khiến JVM có lúc chọn ít workers không cần thiết. JDK-8281181 (được công bố trong Oracle JDK 19 Release Notes và những bản cập nhật/backport phù hợp) điều chỉnh hành vi này: **mặc định không suy số CPU khả dụng từ shares**.

Cờ lịch sử `-XX:+UseContainerCpuShares` từng tồn tại như cách khôi phục hành vi cũ, nhưng đã deprecated rồi bị loại bỏ trong JDK hiện đại. **Không khuyến nghị sử dụng**.

Với workload muốn số worker JVM được giới hạn rõ mà nền tảng chỉ cung cấp shares/weight, dùng `-XX:ActiveProcessorCount=N` sau khi đã kiểm thử, hoặc cấu hình application concurrency riêng.

### 8.2. Ví dụ Docker

Các tham số Docker:

```text
--cpus=1.5
--cpu-quota=150000 --cpu-period=100000
--cpuset-cpus=0-3
--cpu-shares=512
```

**Không phải các tùy chọn tương đương:**

- `--cpus=1.5` và cặp quota/period tương ứng đặt mức **CPU bandwidth cap**.
- `--cpuset-cpus=0-3` giới hạn CPU **IDs**.
- `--cpu-shares=512` thiết lập **relative weight**, không phải 0,5 CPU hard limit.

Không tự bật tất cả cùng lúc. Chọn cấu hình khớp workload và tài nguyên node.

## 9. `-XX:ActiveProcessorCount`: override có chủ đích

JVM option vẫn được tài liệu launcher JDK 27 mô tả:

```text
-XX:ActiveProcessorCount=N
```

điều chỉnh số CPUs mà HotSpot báo/đưa vào một số quyết định về pool sizing. Nó cũng ảnh hưởng kết quả `Runtime.getRuntime().availableProcessors()`.

```bash
java -XX:ActiveProcessorCount=2 ContainerCpuDemo
```

Đây là cách hữu ích để **tái lập một bài test về processor count** hoặc quản lý parallelism của JVM trong một môi trường có resource weighting khó suy ra.

### 9.1. Flag này không thay đổi cgroup

`ActiveProcessorCount` **không**:

- sửa `cpu.max`;
- sửa `cpuset.cpus.effective`;
- gắn thêm physical cores cho JVM;
- tăng quota/CPU time mà scheduler thực thi;
- ngăn container bị throttling;
- bảo đảm các libraries dùng đúng N threads.

Có thể đặt `N=4` khi container chỉ có quota 1,5 CPU, và Java sẽ báo 4. Nhưng Linux vẫn giới hạn CPU time theo 1,5 CPU. Nếu vì thế JVM tạo quá nhiều workers, tail latency thậm chí có thể xấu hơn.

### 9.2. Có hiệu lực ngay cả khi tắt container support

Theo Oracle JDK launcher guide, `ActiveProcessorCount` vẫn được tôn trọng ngay cả nếu `UseContainerSupport` không bật. Đó là lý do cách kiểm thử processor count trên Windows trong bài vẫn đáng tin, dù Windows không có Linux cgroups.

Nhưng **không dùng `-XX:-UseContainerSupport` như một cách tuning mặc định**: tắt detection có thể khiến heap/CPU ergonomics không phản ánh resource limits. Nếu cần override CPU count, chỉ đặt `ActiveProcessorCount` và để container detection hoạt động bình thường.

### 9.3. Khi nào nên cân nhắc?

- Container chỉ có CPU shares/weight, không có CPU quota, và sizing JVM quá lớn so với ngân sách mong muốn.
- Dự án chạy nhiều JVM trên một node nhưng cần kiểm soát mức parallelism từng JVM.
- CI cần mô phỏng processor count 2 hoặc 4 một cách tái lập.
- Có lỗi detection đã xác minh trên một phiên bản JDK cụ thể và cần workaround trong khi nâng runtime.
- Benchmark cho thấy cấu hình worker mặc định gây overparallelism/CPU throttling.

**Không hard-code một giá trị duy nhất cho mọi production pod** nếu requests/limits và workload thay đổi theo deployment.

## 10. Vì sao số CPUs JVM thấy ảnh hưởng performance?

Nhiều thành phần dùng số processors khả dụng để chọn **mặc định**:

- GC threads, ví dụ số worker cho một số giai đoạn G1/Parallel GC;
- `ForkJoinPool.commonPool()` và parallel tasks;
- một số pool/heuristics của JIT;
- thư viện hoặc framework tự tính thread pool theo `Runtime.availableProcessors()`.

Ví dụ thông thường:

```text
Runtime.availableProcessors = 2
ForkJoinPool.common parallelism = 1

Runtime.availableProcessors = 4
ForkJoinPool.common parallelism = 3
```

Hai cặp trên đã được kiểm chứng trong **OpenJDK 24.0.2** với các JVM flags phù hợp. `ForkJoinPool` có thể bị override bởi thuộc tính riêng hoặc thay đổi implementation; không coi mọi thư viện đều dùng cùng công thức.

### 10.1. Không phải giới hạn tổng Java threads

Một JVM báo `availableProcessors=2` vẫn có thể có hàng trăm hoặc hàng nghìn threads/tasks. Số processors **không phải max thread count**.

Phân biệt:

- **CPU-bound tasks:** song song vượt xa CPU budget có thể gây context switching/throttling.
- **I/O-bound tasks:** có thể cần concurrency lớn hơn CPU count, nhưng vẫn phải giới hạn memory, socket và downstream.
- **Virtual threads:** có thể có số lượng lớn tasks chờ I/O; điều đó không có nghĩa có nhiều CPU resources để chạy tính toán.
- **GC workers:** tính từ JVM ergonomics và flags, không nhất thiết bằng available processors.

### 10.2. Thay đổi limits khi JVM đang chạy

Ngay cả nếu JVM có thể quan sát trạng thái cgroup thay đổi, một số thread pools hoặc cấu hình GC đã được tính khi startup. Không hứa tất cả tự resize ngay sau khi cập nhật CPU limit trong Kubernetes.

Khi điều chỉnh resources, đo trên pod mới với cấu hình đúng; nếu cần, restart/recreate những thành phần đã được sized từ trước. Không xem `Runtime.availableProcessors()` tại một thời điểm là bằng chứng pool hiện tại đã thay đổi.

## 11. Kubernetes CPU requests và limits

Ví dụ YAML:

```yaml
resources:
  requests:
    cpu: "500m"
  limits:
    cpu: "1500m"
```

**Requests 500m** dùng trong scheduling và resource weighting; nó **không tự mang nghĩa quota cứng 0,5 CPU**.

**Limits 1500m** trong các môi trường Kubernetes Linux thông dụng được áp qua cơ chế CPU quota, tương đương khoảng **1,5 CPU**. Quota thường có thể làm cho JVM reported CPU count bằng 2 khi cpuset/affinity cho phép.

### 11.1. Pod không có CPU limit

Nếu chỉ có request/weight, không có hard quota của chính pod, JVM hiện đại có thể thấy nhiều CPUs qua affinity. **CPU weight không còn mặc định ép reported processors theo request**.

Vì vậy, một pod request 500m nhưng `availableProcessors=16` **có thể hợp lý** nếu affinity cho phép 16 CPUs và không có quota chặt hơn.

Điều cần làm:

1. Xem thực tế `cpu.max`/cgroup.
2. Đọc reported CPUs bằng Java.
3. Quan sát CPU contention và throttling.
4. Nếu muốn sizing khác, cân nhắc limits hoặc `ActiveProcessorCount` với thử nghiệm cụ thể.

### 11.2. CPU Manager static và cpuset

Một số cluster dùng **CPU Manager static policy** để gán CPU IDs chuyên biệt cho những workloads đủ điều kiện, chẳng hạn containers Guaranteed có integer CPU requests/limits phù hợp.

Điều này phụ thuộc policy, cấu hình node, CPU topology và điều kiện Kubernetes. **Không phải pod nào có CPU limit cũng được pin vào CPU độc quyền**.

### 11.3. Vì sao tăng limit không luôn cải thiện latency?

Có thể vì ứng dụng bị nghẽn network/DB, pool đã bị ghim từ startup, CPU limit mới chưa được áp dụng, parent cgroup giới hạn, JVM có `ActiveProcessorCount` cố định, hoặc workload không đủ CPU-bound concurrency.

Đừng coi chênh lệch `availableProcessors()` là bằng chứng duy nhất về hiệu năng. Cần benchmark cùng workload, đo p95/p99, CPU throttling, GC log/JFR và thread pool metrics.

## 12. Ví dụ Java 17+ runnable: minh họa phép tính và override

Chương trình sau cố ý có **hai phần tách biệt**:

1. Mô phỏng số học từ cpuset/quota do code truyền vào.
2. Đọc số processors thật mà **JVM hiện tại báo**, không giả vờ đã đọc cgroups Linux.

**Mã ví dụ lưu ở file `ContainerCpuDemo.java`:**

```java
import java.util.concurrent.ForkJoinPool;

public final class ContainerCpuDemo {
    static int countCpuSet(String ids) {
        int count = 0;
        for (String part : ids.split(",")) {
            String[] ends = part.split("-", -1);
            if (ends.length == 1) {
                Integer.parseInt(ends[0]);
                count++;
            } else if (ends.length == 2) {
                int first = Integer.parseInt(ends[0]);
                int last = Integer.parseInt(ends[1]);
                if (first < 0 || last < first) throw new IllegalArgumentException(part);
                count += last - first + 1;
            } else {
                throw new IllegalArgumentException(part);
            }
        }
        return count;
    }

    static int quotaCpuCeiling(long quota, long period) {
        if (quota == -1) return -1; // Quota khong gioi han.
        if (quota <= 0 || period <= 0) throw new IllegalArgumentException();
        return Math.toIntExact(1L + (quota - 1L) / period);
    }

    static int modeledCpuCount(int effectiveCpuSetSize, long quota, long period) {
        int quotaLimit = quotaCpuCeiling(quota, period);
        return quotaLimit == -1
                ? effectiveCpuSetSize
                : Math.min(effectiveCpuSetSize, quotaLimit);
    }

    public static void main(String[] args) {
        int cpusetCount = countCpuSet("0-3,7");
        int quotaCpus = quotaCpuCeiling(150_000, 100_000);

        System.out.println("cpusetCount=" + cpusetCount);
        System.out.println("quotaMilliCores=" + (150_000L * 1_000 / 100_000));
        System.out.println("quotaRoundedUp=" + quotaCpus);
        System.out.println("modeledCpuCount=" +
                modeledCpuCount(cpusetCount, 150_000, 100_000));
        System.out.println("fractionalQuarterRoundsUp=" +
                quotaCpuCeiling(25_000, 100_000));
        System.out.println("noQuotaModel=" +
                modeledCpuCount(cpusetCount, -1, 100_000));
        System.out.println("runtimeAvailableProcessors=" +
                Runtime.getRuntime().availableProcessors());
        System.out.println("commonPoolParallelism=" +
                ForkJoinPool.getCommonPoolParallelism());
        System.out.println("java17OrNewer=" +
                (Runtime.version().feature() >= 17));
    }
}
```

### 12.1. Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 ContainerCpuDemo.java
java -XX:ActiveProcessorCount=2 ContainerCpuDemo
```

**Stdout đã kiểm chứng chính xác trên OpenJDK 24.0.2:**

```text
cpusetCount=5
quotaMilliCores=1500
quotaRoundedUp=2
modeledCpuCount=2
fractionalQuarterRoundsUp=1
noQuotaModel=5
runtimeAvailableProcessors=2
commonPoolParallelism=1
java17OrNewer=true
```

**Giải thích:**

- `cpusetCount=5` vì `0-3,7` là các IDs `0,1,2,3,7`.
- `quotaMilliCores=1500` và `quotaRoundedUp=2` vì `150000/100000=1,5`.
- `modeledCpuCount=2` vì `min(5,ceil(1,5)) = 2`.
- `fractionalQuarterRoundsUp=1` vì `ceil(0,25) = 1`.
- `noQuotaModel=5` vì mô hình bỏ ràng buộc quota, còn 5 effective CPUs.
- `runtimeAvailableProcessors=2` đến từ **`ActiveProcessorCount=2`**, không phải giả định có cgroup Linux.
- `commonPoolParallelism=1` là mặc định quan sát trên JDK thử nghiệm.
- `java17OrNewer=true` xác nhận runtime hỗ trợ code Java 17+.

`countCpuSet` là **parser tối giản của bài tập**: giả định danh sách CPU IDs không âm, không chồng lắp và có cú pháp hợp lệ. Không dùng nó như một library đọc cấu hình cgroup production đầy đủ hoặc chứng chỉ Linux affinity.

### 12.2. Đổi override sang 4

```bash
java -XX:ActiveProcessorCount=4 ContainerCpuDemo
```

**Hai dòng thay đổi đã kiểm chứng:**

```text
runtimeAvailableProcessors=4
commonPoolParallelism=3
```

Các dòng mô phỏng `cpusetCount` và `quotaRoundedUp` **không đổi** vì dữ liệu mẫu trong code không đổi. Chỉ nhận thức JVM về processor count được override.

### 12.3. Bỏ override

```bash
java ContainerCpuDemo
```

Kết quả `runtimeAvailableProcessors` và `commonPoolParallelism` **phụ thuộc host/container/JDK đang chạy**, không có một stdout cố định để chép vào tài liệu.

Đặc biệt, chạy trên Windows với `ActiveProcessorCount` chỉ kiểm thử **flag JVM**, không kiểm thử **Linux cgroup detection**. Muốn kiểm tra container detection, chạy trên Linux image thực và so cgroup files với `-Xlog:os+container=trace`.

## 13. Chẩn đoán bằng lệnh JVM và Linux

Trong Linux container, chạy:

```bash
java --version
java -XshowSettings:system -version
java -Xlog:os+container=trace -version
```

Lưu ý:

- `-XshowSettings:system` được tài liệu launcher mô tả cho **Linux**; trên Windows không thể dùng nó để xem Linux cgroups.
- `-Xlog:os+container=trace` in chẩn đoán container detection của HotSpot. Có thể khá dài; không bật mức trace vô thời hạn trong production.
- `java --version` giúp kiểm tra đúng JDK vendor/update đang chạy.

Kiểm tra các cờ JVM:

```bash
java -XX:+PrintFlagsFinal -version |
    grep -E 'UseContainerSupport|ActiveProcessorCount'
```

Với JVM đang chạy, `jcmd <pid> VM.flags` cũng có thể hỗ trợ nếu có quyền và ở đúng PID namespace. Kiểm tra startup scripts, `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS` vì có thể override cấu hình ngoài ý muốn.

### 13.1. Kiểm tra cgroups v2

```bash
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/cpuset.cpus.effective
cat /sys/fs/cgroup/cpu.stat
```

Đối chiếu quota/period và effective cpuset với con số `availableProcessors()`. Đừng quên parent cgroup, task affinity và `ActiveProcessorCount`.

### 13.2. Theo dõi throttling

Lấy hai snapshot `cpu.stat` cách nhau một khoảng workload đại diện. So hiệu số `nr_periods`, `nr_throttled`, `throttled_usec`, `usage_usec`. Cùng lúc thu:

- request latency histogram;
- CPU utilization;
- garbage collection logs hoặc JFR;
- số workers/pool parallelism;
- container CPU limits/requests.

Một giá trị `nr_throttled` tuyệt đối không cho biết latency request cụ thể; cần **timeline và rate**.

### 13.3. Cgroup hierarchy và quyền đọc

Nếu `cpu.max` trả `max` nhưng pod vẫn có dấu hiệu throttle, xem **ancestor cgroup** và namespace. Không giả định đường dẫn cố định `/sys/fs/cgroup` luôn được mount/cho đọc. Hỏi platform administrator hoặc dùng node-level metrics khi container không thể nhìn hết hierarchy.

## 14. Các tình huống thực tế

### Trường hợp A: `limits.cpu=1500m`, Java báo 2

**Có thể đúng.** 1,5 CPU budget được làm tròn lên khi báo processor count. Đo throttling trước khi giảm parallelism thủ công.

### Trường hợp B: chỉ có `requests.cpu=500m`, Java báo 16

**Có thể đúng.** Requests/weight không phải hard quota; nếu affinity cho phép 16 CPU logic và không có quota chặt hơn, số reported có thể lớn.

### Trường hợp C: cpuset 2 CPU IDs, quota 4

Không thể dùng CPU IDs ngoài cpuset. Mô hình active count cho ra 2. `ActiveProcessorCount=4` có thể đổi JVM-reported value nhưng **không vượt qua Linux affinity**.

### Trường hợp D: container có 1 CPU quota, `ActiveProcessorCount=8`

JVM vẫn có thể báo 8 và lập nhiều workers; kernel chỉ cho quota tương đương 1 CPU. Kết quả có thể là contention và throttling nhiều hơn. Đây là ví dụ vì sao không chọn override chỉ theo “số cores host”.

### Trường hợp E: CPU limit tăng nhưng JVM thread pool vẫn nhỏ

Pool có thể đã được sized lúc startup hoặc bị ghim bởi application configuration. Kiểm tra CPU limit thực, restart policy và nguồn khởi tạo thread pool, rồi đo lại.

### Trường hợp F: JDK cũ gặp cgroups v2

Nếu JDK không đọc đúng controller, `availableProcessors()` có thể khác mong đợi. Hướng bền vững: **nâng JDK còn được bảo trì có cgroups v2 support**, thay vì trông chờ một bản Java 10 cổ trên host mới.

## 15. Checklist QA trước khi quyết định sizing

| Mục | Cần xác minh |
| --- | --- |
| JVM | JDK vendor/version/build trong **container thực** |
| OS | Linux/kernel và cgroups v1/v2 |
| Support | `UseContainerSupport` có bật và hoạt động không |
| Cpuset | `cpuset.cpus.effective`/affinity thực tế |
| CPU budget | `cpu.max` hoặc quota/period v1 |
| Parent | Có inherited quota/cpuset khác không |
| Shares | Có nhầm `cpu.weight` với quota không |
| Override | `ActiveProcessorCount` có đang đặt không |
| Count | `Runtime.availableProcessors()` thật |
| Pools | GC, ForkJoin, framework thread pool settings |
| CPU pressure | `nr_throttled`/`throttled_usec` deltas |
| Performance | Throughput và p95/p99 latency theo workload |
| Deployment | Kubernetes requests/limits và CPU Manager |
| Lifecycle | JDK có support cgroup version và security updates không |

Quy trình thử nghiệm: **lấy baseline → đổi từng biến → đo CPU/throttling/latency → kiểm tra regression → ghi nhận cấu hình được chọn**. Không dùng một phép thử nhỏ để kết luận một cấu hình sẽ tối ưu trên mọi pod.

## 16. Lỗi phổ biến

**Lỗi 1: “cpuset `0-3` nghĩa có 4 physical cores dành riêng.”**  
Sai: đó là 4 CPU logic IDs, không tự chứng minh exclusivity.

**Lỗi 2: “Quota 1,5 CPU thì Java phải trả 1,5.”**  
Sai: `availableProcessors()` trả `int`, HotSpot có thể làm tròn lên 2.

**Lỗi 3: “Java báo 2 processors nên quota không throttle.”**  
Sai: Linux vẫn thực thi 1,5 CPU time budget.

**Lỗi 4: “`cpu.shares=512` = 0,5 CPU hard limit.”**  
Sai: shares/weight là ưu tiên tương đối.

**Lỗi 5: “CPU request là CPU limit.”**  
Sai: Kubernetes requests và limits có vai trò khác.

**Lỗi 6: “`cpuset.cpus` rỗng là 0 CPU.”**  
Sai: xem `cpuset.cpus.effective` và inheritance.

**Lỗi 7: “`ActiveProcessorCount` cấp thêm CPU cho container.”**  
Sai: chỉ đổi nhận thức của JVM.

**Lỗi 8: “Số processor JVM báo là maximum Java threads.”**  
Sai: không giới hạn `Thread` hoặc `ExecutorService` theo cách đó.

**Lỗi 9: “JDK 10 hiểu mọi cgroups v2 node.”**  
Sai: cgroups v2 support được bổ sung ở JDK mới hơn.

**Lỗi 10: “Mọi thread pool tự thay đổi khi tăng CPU limit.”**  
Không bảo đảm: nhiều pools đã sized lúc khởi động.

**Lỗi 11: “Đọc host `lscpu` đủ để chẩn đoán pod.”**  
Không: cần xem container cgroup/affinity thực tế.

**Lỗi 12: “Cờ CPU shares cũ là phương án tốt nhất trên JDK mới.”**  
Không: cách diễn giải cũ đã deprecated/removed.

**Lỗi 13: “`cpu.max=max` chứng minh toàn bộ hệ thống không hạn chế CPU.”**  
Sai: ancestor cgroup và affinity vẫn có thể ràng buộc.

**Lỗi 14: “Thấy số threads bằng CPU count thì chắc chắn không có contention.”**  
Sai: CPU quota, các workload cùng host và OS scheduling vẫn có ảnh hưởng.

## 17. Bài tập tự kiểm tra

**Câu 1.** Cpuset `1,3,5-7` có mấy logical CPUs?  
**Đáp án:** 5 IDs: 1,3,5,6,7.

**Câu 2.** Quota 150000 và period 100000 tương đương bao nhiêu CPU?  
**Đáp án:** 1,5 CPU time capacity.

**Câu 3.** Với cpuset 4 IDs và quota 1,5, mô hình count cho ra bao nhiêu?  
**Đáp án:** `min(4,ceil(1,5)) = 2`.

**Câu 4.** Vì sao 2 reported CPUs vẫn có thể bị throttle?  
**Đáp án:** Kernel thực thi quota 1,5 CPU, không phải số nguyên JVM báo.

**Câu 5.** Với cpuset 2 IDs và quota tương đương 4 CPUs, count mô hình là bao nhiêu?  
**Đáp án:** 2; affinity giới hạn tập CPU chạy được.

**Câu 6.** `cpu.max=max 100000` nghĩa gì?  
**Đáp án:** Không có quota tại cgroup ấy, nhưng ancestor/affinity vẫn có thể giới hạn.

**Câu 7.** `cpu.shares` có phải số CPU cứng không?  
**Đáp án:** Không, là relative scheduling weight.

**Câu 8.** `ActiveProcessorCount=4` có tự sửa `cpu.max` không?  
**Đáp án:** Không. Chỉ override processor count của JVM.

**Câu 9.** Vì sao `Runtime.availableProcessors()` của Linux container có thể khác `lscpu` host?  
**Đáp án:** Vì cpuset, affinity, quota và container detection.

**Câu 10.** Một pod chỉ có CPU request 500m, không limit, JVM báo 8. Có chắc là bug không?  
**Đáp án:** Không, request không phải hard quota.

**Câu 11.** File nào phản ánh CPU IDs được cấp thực sự ở cgroups v2?  
**Đáp án:** `cpuset.cpus.effective`.

**Câu 12.** Dấu hiệu nào giúp xác định throttling tăng theo workload?  
**Đáp án:** Delta `nr_throttled`/`throttled_usec` trong `cpu.stat` kết hợp throughput và latency.

**Câu 13.** Nếu JDK rất cũ không nhận cgroups v2, nên làm gì?  
**Đáp án:** Nâng JDK có support và security updates; cân nhắc override có kiểm thử nếu cần tạm thời.

**Câu 14.** Có thể đảm bảo common pool luôn bằng `availableProcessors-1` không?  
**Đáp án:** Không trong mọi môi trường, vì có giới hạn dưới và cấu hình pool riêng.

## 18. Ghi nhớ

1. **cpuset/affinity** xác định các CPU IDs được phép; **quota/period** xác định ngân sách CPU time.
2. `Runtime.availableProcessors()` là **số nguyên cho JVM sizing**, không phải physical cores độc quyền hay hard cap threads.
3. Quota phân số có thể được làm tròn lên: **1,5 CPU → 2 reported processors**, miễn không bị affinity giới hạn thấp hơn.
4. Linux **vẫn throttle** theo quota thật; `ActiveProcessorCount` không cấp thêm tài nguyên kernel.
5. **`cpu.shares` và `cpu.weight` không phải hard quota**. JDK hiện đại không dùng shares mặc định để suy CPU count.
6. `UseContainerSupport` được bật mặc định trên HotSpot Linux hiện hành; nếu không phát hiện đúng, kiểm tra JDK/cgroup/flags.
7. Cgroups v2 dùng `cpu.max`, `cpuset.cpus.effective`, `cpu.stat`; phải xét **parent hierarchy và namespace**.
8. Kubernetes **requests khác limits**; CPU Manager static không áp cho mọi pod.
9. GC/ForkJoin/framework pools có thể dựa vào processor count nhưng **không nhất thiết bằng count đó**; resize sau thay limit không được đảm bảo.
10. Tối ưu CPU concurrency cần **đo CPU throttling, throughput, latency và GC/JFR trên runtime thật**, không chỉ so một số nguyên.

## Tài liệu tham khảo chính thức và hiện hành

- **Oracle Java SE 27 — The java Command**, `UseContainerSupport` (default true trên Linux), `ActiveProcessorCount`, `-XshowSettings:system` và `-Xlog:os+container=trace`: https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- **Oracle Java 10 — java launcher options**, container awareness và `ActiveProcessorCount`: https://docs.oracle.com/javase/10/tools/java.htm
- **OpenJDK Linux HotSpot source**, triển khai active processor count, CPU quota và affinity: https://github.com/openjdk/jdk/blob/master/src/hotspot/os/linux/os_linux.cpp
- **Oracle JDK 19 Release Notes (JDK-8281181)**, CPU shares bị bỏ khỏi phép tính processor count mặc định: https://www.oracle.com/java/technologies/javase/19-relnote-issues.html
- **Linux Kernel — Control Group v2**, `cpu.max`, `cpu.weight`, `cpuset.cpus.effective`, `cpu.stat`: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
- **Docker — Resource constraints**: https://docs.docker.com/engine/containers/resource_constraints/
- **Kubernetes — Resource Management for Pods and Containers**: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- **Kubernetes — CPU Management Policies**: https://kubernetes.io/docs/tasks/administer-cluster/cpu-management-policies/
- **Kubernetes — cgroup v2**: https://kubernetes.io/docs/concepts/architecture/cgroups/
- **AWS Containers (2026) — JVM memory, CPU and classpath best practices for Java containers**: https://aws.amazon.com/blogs/containers/jvm-memory-cpu-and-classpath-best-practices-for-java-containers-on-aws/
- **Java SE 27 API — `Runtime`**: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Runtime.html
- **Java SE 27 API — `ForkJoinPool`**: https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
